# 6.7 Tạo getter, setter và chuyển Method hoặc Constructor sang handle bằng unreflect

Trong Java, `MethodHandle` là một tham chiếu có kiểu rõ ràng tới thao tác có thể thực thi: gọi method, khởi tạo đối tượng, đọc hoặc ghi field. `MethodHandles.Lookup` cung cấp hai lối tạo handle quan trọng:

- **Tra trực tiếp theo class + tên + kiểu**: `findGetter`, `findSetter`, `findStaticGetter`, `findStaticSetter`, `findVirtual`, `findStatic` và `findConstructor`.
- **Chuyển từ metadata Reflection đã có**: `unreflectGetter(Field)`, `unreflectSetter(Field)`, `unreflect(Method)` và `unreflectConstructor(Constructor<?>)`.

Bài này tập trung vào cách **tạo getter/setter cho field** và **chuyển Field, Method hoặc Constructor thành MethodHandle**, rồi sử dụng đúng `MethodType`, receiver, kiểu trả về, quyền truy cập và lỗi. Đây là kỹ năng cần thiết trong mapper, serializer, framework DI, bộ gọi plugin hay hệ thống chạy mã theo cấu hình lúc runtime.

Mục tiêu: khi cầm `Field`, `Method` hoặc `Constructor<?>` trên tay, bạn biết chọn phép `unreflect` thích hợp, hiểu đúng chữ ký handle thu được và tránh sai lầm như đưa receiver vào getter static, tưởng setter trả về giá trị, hoặc gọi `invokeExact` với kiểu không khớp.

## 1. Tư duy nền: MethodHandle có MethodType riêng

`MethodHandle` không mang tên phương thức để người gọi lựa chọn overload ở mỗi lần gọi. Khi được tạo, nó có **một `MethodType` xác định**: danh sách kiểu tham số và một kiểu trả về. Đọc bằng `handle.type()`.

Ví dụ có lớp:

```java
class Counter {
    public int count;
    public static int total;
    public Counter(String label, int count) { this.count = count; }
    public String describe(String prefix) { return prefix + count; }
}
```

Đây là khai báo minh họa, không phải tệp Java độc lập. Các thao tác tương ứng có kiểu handle:

| Thao tác | `MethodType` của handle | Đối số khi gọi |
| --- | --- | --- |
| Đọc `count` của instance | `(Counter)int` | Một `Counter` receiver, trả `int` |
| Ghi `count` của instance | `(Counter,int)void` | Receiver rồi giá trị mới, không trả kết quả |
| Đọc `static total` | `()int` | Không receiver, không tham số |
| Ghi `static total` | `(int)void` | Chỉ giá trị mới |
| Gọi `describe(String)` | `(Counter,String)String` | Receiver trước tham số gốc |
| Gọi static method `static String category(int)` | `(int)String` | Không có receiver |
| Gọi constructor `Counter(String,int)` | `(String,int)Counter` | Các đối số constructor; **trả về instance mới** |

Với method instance, receiver trở thành **tham số đầu tiên** trong handle. Với constructor, `java.lang.reflect.Constructor` đại diện cho thao tác xây đối tượng; handle sinh ra trả **kiểu lớp được khởi tạo**, khác descriptor khởi tạo `<init>` trong JVM vốn có kiểu trả về `void`.

**Lưu ý:** `MethodHandle.type()` dùng các đối tượng `Class<?>` thực; `(Counter,int)void` là dạng chuỗi thân thiện của `MethodType.toString()`. Khi lập trình không dựa vào chuỗi, hãy dùng `type().parameterType(i)`, `returnType()` và `parameterCount()`.

## 2. Tạo getter và setter khi biết class, tên field, kiểu field

Bốn phương thức `Lookup` dành cho thao tác field theo tên:

| API | Nhắm tới | Kiểu handle thông thường |
| --- | --- | --- |
| `findGetter(C.class, "f", T.class)` | Field instance `T f` | `(C)T` |
| `findSetter(C.class, "f", T.class)` | Field instance `T f` có thể ghi | `(C,T)void` |
| `findStaticGetter(C.class, "f", T.class)` | Field static `static T f` | `()T` |
| `findStaticSetter(C.class, "f", T.class)` | Field static `static T f` có thể ghi | `(T)void` |

Trong bảng, `C` là kiểu receiver thực tế của handle (thông thường là kiểu lớp bạn tra cứu; một số trường hợp `protected` có thể hẹp hơn do quy tắc truy cập), còn `T` là kiểu chính xác của field.

Ví dụ trực tiếp với một lớp có field public:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodHandle getCount =
        lookup.findGetter(Counter.class, "count", int.class);
MethodHandle setCount =
        lookup.findSetter(Counter.class, "count", int.class);
MethodHandle getTotal =
        lookup.findStaticGetter(Counter.class, "total", int.class);
MethodHandle setTotal =
        lookup.findStaticSetter(Counter.class, "total", int.class);
```

Đoạn trên dùng lớp `Counter` minh họa cùng import `MethodHandle`, `MethodHandles`. Phương thức tìm handle kiểm tra quyền **ngay khi tạo**. Nếu tên hoặc kiểu field sai, `NoSuchFieldException` là trường hợp điển hình; nếu thiếu quyền, sai static/instance, hoặc cố tìm setter cho field `final` bằng `findSetter`/`findStaticSetter`, `IllegalAccessException` có thể phát sinh.

Không có phương thức tên `findFieldGetter` trong API này; hãy dùng đúng bốn tên ở bảng.

### 2.1. Kiểu của field phải chính xác

Field `int count` được tìm bằng `int.class`, **không** bằng `Integer.class` hay `Object.class`. Tương tự, `String[] names` phải dùng `String[].class`, không phải `String.class`. Đây là tra cứu thành viên theo kiểu khai báo, không phải cơ chế chọn overload bằng phép gán tương thích.

Nếu đã có `Field`, cách đáng tin hơn là lấy trực tiếp `field.getType()` hoặc gọi `unreflectGetter(field)`, vì bạn không cần tự nhập lại tên và kiểu.

### 2.2. Khác biệt đọc/ghi instance và static

Với instance field, receiver là tham số đầu tiên: `getCount.invokeExact(counter)` cần kết quả với kiểu `int`, còn `setCount.invokeExact(counter, 7)` trả `void`. Với static field, không được đưa receiver vào: `getTotal.invokeExact()` và `setTotal.invokeExact(99)`.

Việc gọi handle của static field có thể kích hoạt khởi tạo lớp nếu lớp chưa được khởi tạo. `MethodHandle` không biến field thành thuộc tính ảo hoặc gọi một method “getter” JavaBeans; nó truy cập trực tiếp field tương ứng, tuân thủ ngữ nghĩa field của Java.

## 3. Từ Field sang getter/setter: unreflectGetter và unreflectSetter

Giả sử một thư viện đã duyệt các `Field` bằng Reflection. Thay vì lấy tên rồi tra lần nữa, hãy chuyển chính metadata đó thành handle:

```java
Field field = Counter.class.getField("count");
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle getter = lookup.unreflectGetter(field);
MethodHandle setter = lookup.unreflectSetter(field);
```

Đây là đoạn minh họa, không phải chương trình độc lập. `getField` tìm field public (kể cả public inherited field phù hợp); `getDeclaredField` tìm field khai báo ngay trên lớp, kể cả private, nhưng **chỉ tìm thấy không đồng nghĩa có quyền truy cập**.

Các API `unreflectGetter` và `unreflectSetter`:

- Dùng trực tiếp một `Field` hiện hữu. Không yêu cầu tên hay loại dữ liệu nhập lần thứ hai.
- Tạo handle có kiểu phụ thuộc `field.getType()`, `Modifier.isStatic(field.getModifiers())` và kiểu lớp khai báo của field.
- Kiểm tra quyền của `Lookup` khi tạo handle nếu cờ suppress-access của `Field` chưa bật. Cờ `setAccessible` không bảo đảm vượt được giới hạn module hoặc quy tắc đối với final field.
- Getter đọc được cả field `final` nếu đủ quyền. Setter chỉ tạo thành công cho trường hợp **pháp luật truy cập và tính final cho phép ghi**. Với field `static final`, không được tạo setter có thể ghi theo đường này.

**Dấu hiệu lựa chọn**: có `Field` từ công cụ scan/annotation/serialization thì dùng `unreflectGetter`/`unreflectSetter`; chỉ có class, tên, kiểu chính xác thì dùng `findGetter`/`findSetter`. Cả hai cuối cùng cho thao tác đọc/ghi field tương ứng, nhưng quy tắc cờ accessible của một `Field` đã được chỉnh là khác với tra theo tên.

### 3.1. Final field không phải setter thông thường

`findSetter` và `findStaticSetter` từ chối field `final`. `unreflectSetter` chỉ có ngoại lệ hẹp nếu một `Field` đáp ứng điều kiện ghi theo `Field.set` và đã được mở quyền phù hợp. Đó không phải giấy phép chung để sửa trạng thái bất biến: một số field final không thể ghi qua Reflection, như **static final**, final field trong **record** và field trong **hidden class**. Việc sửa field final sau khởi tạo còn có rủi ro về ngữ nghĩa, tối ưu hóa JVM và tính nhất quán.

Khi xây mapper hoặc DI, hãy ưu tiên constructor để gán trạng thái final; chỉ tạo setter cho field thực sự có thể ghi. Nếu cần thao tác đồng bộ/atomic theo bộ nhớ, xem `VarHandle` thay vì kỳ vọng getter/setter handle tự tạo ra `compareAndSet`.

## 4. Chuyển Method và Constructor sang handle

### 4.1. unreflect(Method)

Khi đã có một `java.lang.reflect.Method` chính xác, hãy gọi:

```java
Method reflected = Counter.class.getMethod("describe", String.class);
MethodHandle handle = MethodHandles.lookup().unreflect(reflected);
```

Nếu `describe` là instance method `String describe(String prefix)`, handle có kiểu `(Counter,String)String`. Nếu method là static, **không có receiver**. Với phương thức instance có thể override, `unreflect(Method)` duy trì **dynamic dispatch** thông thường: implementation được chọn theo receiver khi gọi, không đóng băng implementation theo một đối tượng `Method` kiểu cha.

`unreflect(Method)` là lựa chọn tự nhiên khi API đã trả về `Method` (từ `getMethod`, `getDeclaredMethod`, quét annotation hoặc chọn overload). Nếu chỉ biết class + tên + `MethodType`, các phương thức `findVirtual`/`findStatic` thường trực tiếp và rõ ràng hơn.

**Khác biệt khi gọi:** `Method.invoke` trả `Object`, đóng gói primitive và bọc lỗi **do method đích ném** trong `InvocationTargetException`. `MethodHandle.invokeExact`/`invoke` có chữ ký mạnh hơn; exception từ method đích **truyền ra trực tiếp**, không tự bọc như Reflection.

### 4.2. unreflectConstructor(Constructor<?>)

`java.lang.reflect.Constructor<?>` mô tả một constructor cụ thể, không phải `Method` và không được đưa vào `unreflect(Method)`. Dùng:

```java
Constructor<Counter> ctor =
        Counter.class.getConstructor(String.class, int.class);
MethodHandle make = MethodHandles.lookup().unreflectConstructor(ctor);
```

Với constructor `Counter(String,int)`, `make.type()` là `(String,int)Counter`. Gọi handle tạo **Counter mới**. Không có receiver đầu tiên ở constructor, vì chưa có instance; khác `(Counter,String)String` của instance method.

So với `Lookup.findConstructor(Counter.class, MethodType.methodType(void.class, String.class, int.class))`, `unreflectConstructor` phù hợp khi bạn đã có đối tượng `Constructor`. Đừng nhầm: tham số `MethodType` truyền vào `findConstructor` dùng **return type là `void`**, còn `MethodType` của handle trả về lại là `Counter`.

### 4.3. Bản đồ chuyển đổi nhanh

| Metadata hoặc dữ kiện sẵn có | Chọn API | Phần tử được gọi |
| --- | --- | --- |
| `Field f` để đọc | `lookup.unreflectGetter(f)` | Đọc instance/static field |
| `Field f` để ghi | `lookup.unreflectSetter(f)` | Ghi instance/static field có thể sửa |
| Tên + kiểu field instance | `lookup.findGetter` / `lookup.findSetter` | Đọc/ghi field instance |
| Tên + kiểu field static | `lookup.findStaticGetter` / `lookup.findStaticSetter` | Đọc/ghi field static |
| `Method m` | `lookup.unreflect(m)` | Gọi chính phương thức đó |
| `Constructor<?> c` | `lookup.unreflectConstructor(c)` | Tạo đối tượng bằng constructor đó |
| Tên + signature method | `lookup.findVirtual` hoặc `lookup.findStatic` | Chọn member qua `MethodType` |
| Kiểu + signature constructor | `lookup.findConstructor` | Tạo instance theo chữ ký |

Đừng dùng `unreflectSpecial` để thay `unreflect` một cách mặc định. `unreflectSpecial(method, specialCaller)` mô phỏng ngữ nghĩa `invokespecial` (có thể bỏ qua override) và yêu cầu quyền/caller đặc thù, chỉ thích hợp khi thực sự muốn lời gọi special.

## 5. Ví dụ Java 17+ đầy đủ: getter, setter, method, constructor

Tạo tệp **`LookupHandlesDemo.java`** với toàn bộ nội dung dưới đây:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class LookupHandlesDemo {
    public static class Counter {
        public String label;
        public int count;
        public static int total = 10;
        public final String id;

        public Counter(String label, int count) {
            this.label = label;
            this.count = count;
            this.id = "X-" + label;
        }

        public String describe(String prefix) {
            return prefix + label + ":" + count;
        }

        public static String category(int number) {
            return "C" + number;
        }

        public String explode() {
            throw new IllegalStateException("boom");
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle getter = lookup.findGetter(Counter.class, "count", int.class);
        MethodHandle setter = lookup.findSetter(Counter.class, "count", int.class);

        Field field = Counter.class.getField("count");
        MethodHandle reflectedGetter = lookup.unreflectGetter(field);
        MethodHandle reflectedSetter = lookup.unreflectSetter(field);
        MethodHandle staticGetter = lookup.findStaticGetter(Counter.class, "total", int.class);
        MethodHandle staticSetter = lookup.findStaticSetter(Counter.class, "total", int.class);

        MethodHandle constructor = lookup.unreflectConstructor(
                Counter.class.getConstructor(String.class, int.class));
        Method method = Counter.class.getMethod("describe", String.class);
        MethodHandle described = lookup.unreflect(method);
        MethodHandle staticMethod = lookup.unreflect(Counter.class.getMethod("category", int.class));

        Counter counter = (Counter) constructor.invokeExact("alpha", 2);
        System.out.println("ctor type=" + constructor.type());
        System.out.println("getter type=" + getter.type());
        System.out.println("setter type=" + setter.type());
        System.out.println("static getter type=" + staticGetter.type());
        System.out.println("static setter type=" + staticSetter.type());
        System.out.println("method type=" + described.type());
        System.out.println("before=" + (int) getter.invokeExact(counter));
        setter.invokeExact(counter, 7);
        System.out.println("after=" + (int) reflectedGetter.invokeExact(counter));
        reflectedSetter.invokeExact(counter, 9);
        System.out.println("after unreflect setter=" + (int) getter.invokeExact(counter));
        System.out.println("method=" + (String) described.invokeExact(counter, "item="));
        System.out.println("static method=" + (String) staticMethod.invokeExact(4));
        System.out.println("static before=" + (int) staticGetter.invokeExact());
        staticSetter.invokeExact(99);
        System.out.println("static after=" + (int) staticGetter.invokeExact());

        MethodHandle boundGetter = getter.bindTo(counter);
        System.out.println("bound type=" + boundGetter.type());
        System.out.println("bound value=" + (int) boundGetter.invokeExact());

        MethodHandle objectGetter = getter.asType(MethodType.methodType(Object.class, Object.class));
        System.out.println("adapted=" + objectGetter.invokeExact((Object) counter));

        try {
            lookup.findSetter(Counter.class, "id", String.class);
        } catch (IllegalAccessException exception) {
            System.out.println("final setter=" + exception.getClass().getSimpleName());
        }

        MethodHandle exploding = lookup.unreflect(Counter.class.getMethod("explode"));
        try {
            String unused = (String) exploding.invokeExact(counter);
        } catch (IllegalStateException exception) {
            System.out.println("exception=" + exception.getClass().getSimpleName()
                    + ":" + exception.getMessage());
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp bằng JDK 17 trở lên:

```bash
javac --release 17 LookupHandlesDemo.java
java LookupHandlesDemo
```

Kết quả `stdout` đã được kiểm tra:

```text
ctor type=(String,int)Counter
getter type=(Counter)int
setter type=(Counter,int)void
static getter type=()int
static setter type=(int)void
method type=(Counter,String)String
before=2
after=7
after unreflect setter=9
method=item=alpha:9
static method=C4
static before=10
static after=99
bound type=()int
bound value=9
adapted=9
final setter=IllegalAccessException
exception=IllegalStateException:boom
```

### 5.1. Từng nhóm kết quả chứng minh điều gì?

1. **Constructor handle**: `unreflectConstructor` nhận `Constructor<Counter>` và tạo handle `(String,int)Counter`. Ép kiểu kết quả của `invokeExact` thành `Counter` khiến chữ ký tại call site khớp.
2. **Instance field**: `findGetter` và `unreflectGetter` đều đọc cùng field; `findSetter` và `unreflectSetter` đều ghi cùng field. Kết quả `before=2` → `after=7` → `after unreflect setter=9` xác minh hoạt động đúng.
3. **Static field**: `staticGetter.type()` là `()int`, `staticSetter.type()` là `(int)void`; không xuất hiện receiver. Sau khi set `99`, đọc lại trả `99`.
4. **Method**: `unreflect(Method)` của instance nhận `Counter` trước `String`, còn method static chỉ nhận `int`.
5. **Bind receiver**: `getter.bindTo(counter)` giữ sẵn receiver và tạo handle không tham số `()int`. Đây không phải getter static; nó vẫn gắn với `counter` cụ thể.
6. **Adapt kiểu**: `asType(MethodType.methodType(Object.class, Object.class))` làm kiểu handle trở thành `(Object)Object`. Khi gọi, runtime cast `Object` sang `Counter` và box `int` thành `Integer` nếu hợp lệ; kết quả in ra `9`.
7. **Final field**: `findSetter` cho `id` trả `IllegalAccessException` ngay lúc tạo. Không có đường đi hợp lệ bằng `findSetter` dù `id` là public.
8. **Exception**: method `explode` ném `IllegalStateException("boom")`; khi gọi qua handle, nhận trực tiếp `IllegalStateException`. Không cần bóc `InvocationTargetException` như với `Method.invoke`.

**Chi tiết cú pháp của `invokeExact`:** trong dòng `System.out.println((int) getter.invokeExact(counter))`, ép kiểu `(int)` là một phần của chữ ký compile-time mà JVM kiểm tra. Với getter `int`, viết `(long) getter.invokeExact(counter)` sẽ yêu cầu handle có return type `long` và gây `WrongMethodTypeException`, dù Java thông thường có thể widening `int` thành `long`. Muốn chuyển đổi có kiểm soát, dùng `invoke` hoặc `asType` đúng cách.

## 6. Truy cập thành viên private và quyền của Lookup

`getDeclaredField("code")`, `getDeclaredMethod("reveal", String.class)` hay `getDeclaredConstructor(String.class)` chỉ cung cấp **metadata**, không cấp đặc quyền tự động. `Lookup` mang danh tính của lớp tạo lookup và tập quyền truy cập. Khi tạo một method handle, quyền truy cập được kiểm tra **ngay khi tạo**; handle đã tạo là một capability có thể được gọi về sau, vì vậy không nên chia sẻ handle tới private member với mã không đáng tin cậy.

### 6.1. privateLookupIn cho lớp đích phù hợp

`MethodHandles.privateLookupIn(targetClass, callerLookup)` có thể tạo lookup với quyền private trong lớp đích nếu quan hệ module, quyền `PRIVATE`/`MODULE` của caller và yêu cầu package `opens` liên quan cho phép. Đây không phải cách vượt mọi giới hạn bảo mật. Với module khác, package của target cần được mở cho module gọi theo quy định.

Ví dụ độc lập **`PrivateLookupDemo.java`** sau hoạt động trên cùng module/classpath, dùng một nested class để minh họa private constructor, field và method:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class PrivateLookupDemo {
    public static class SecretBox {
        private String code;

        private SecretBox(String code) {
            this.code = code;
        }

        private String reveal(String prefix) {
            return prefix + code;
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup privileged = MethodHandles.privateLookupIn(
                SecretBox.class, MethodHandles.lookup());
        Field field = SecretBox.class.getDeclaredField("code");
        Constructor<SecretBox> ctor = SecretBox.class.getDeclaredConstructor(String.class);
        Method method = SecretBox.class.getDeclaredMethod("reveal", String.class);

        MethodHandle getter = privileged.unreflectGetter(field);
        MethodHandle setter = privileged.unreflectSetter(field);
        MethodHandle make = privileged.unreflectConstructor(ctor);
        MethodHandle reveal = privileged.unreflect(method);

        SecretBox box = (SecretBox) make.invokeExact("hidden");
        System.out.println("getter type=" + getter.type());
        System.out.println("before=" + (String) getter.invokeExact(box));
        setter.invokeExact(box, "visible");
        System.out.println("after=" + (String) getter.invokeExact(box));
        System.out.println("method=" + (String) reveal.invokeExact(box, "code="));
    }
}
```

```bash
javac --release 17 PrivateLookupDemo.java
java PrivateLookupDemo
```

`stdout`:

```text
getter type=(SecretBox)String
before=hidden
after=visible
method=code=visible
```

Chương trình trên không cần gọi `setAccessible(true)` vì đã dùng `Lookup` có quyền với `SecretBox`. `privateLookupIn` có thể ném `IllegalAccessException` nếu đặt ví dụ sang một module không mở package thích hợp. Với mã ứng dụng thực, cấp quyền truy cập có chủ đích (public API hoặc `opens` phù hợp) và hạn chế phân phối lookup/handle đặc quyền.

### 6.2. So sánh publicLookup, lookup và privateLookupIn

| Cách tạo Lookup | Ý nghĩa |
| --- | --- |
| `MethodHandles.publicLookup()` | Quyền công khai giới hạn, phù hợp API public có thể truy cập từ mọi nơi theo module |
| `MethodHandles.lookup()` | Quyền dựa trên **caller class** nơi thực sự gọi `lookup()`; có thể truy cập private member của caller theo quy định |
| `MethodHandles.privateLookupIn(Target.class, callerLookup)` | Yêu cầu lookup có quyền private trên `Target`, phụ thuộc năng lực caller và các ràng buộc module |

**Hai lưu ý quan trọng:**

- Gọi `MethodHandles.lookup()` trong helper không làm nó trở thành lookup của class đích mà helper nhận vào. Muốn quyền target khác, sử dụng cơ chế thích hợp; tránh đưa `Lookup` có đặc quyền cho plugin bên ngoài.
- `Field.trySetAccessible()`/`setAccessible(true)` là cơ chế suppress access riêng của Reflection và có thể thất bại vì module. Một `Field` có cờ accessible được mở hợp lệ có thể tác động đến phép `unreflectGetter`/`unreflectSetter`, nhưng không làm mọi final field ghi được, cũng không tạo cho caller quyền tổng quát đối với tất cả members trong module.

## 7. invokeExact, invoke, asType và invokeWithArguments

Để dùng handle, phải phân biệt **kiểu của handle** và **kiểu biểu thức gọi ở source code**.

### 7.1. invokeExact yêu cầu chữ ký trùng khớp

Giả sử `MethodHandle getCount` có kiểu `(Counter)int`:

```java
int count = (int) getCount.invokeExact(counter);
```

Đoạn trên tham chiếu các biến trong ví dụ `LookupHandlesDemo`. Tham số receiver phải có **kiểu compile-time đúng `Counter`**, và giá trị trả về cũng phải được dùng dưới kiểu `int`. Viết `Object value = getCount.invokeExact(counter);` làm call site kỳ vọng `Object` thay `int` và ném `WrongMethodTypeException` khi chạy. Tương tự, setter có return type `void`, nên thường gọi thành một statement:

```java
setCount.invokeExact(counter, 42);
```

Khi không biết kiểu tại compile time, `invokeExact` không tự suy ra từ `handle.type()`; bạn cần thiết kế adapter hoặc API động phù hợp.

### 7.2. invoke cho chuyển kiểu có giới hạn

`invoke` có thể áp dụng các chuyển đổi mà `MethodHandle.asType` hỗ trợ, chẳng hạn boxing/unboxing và một số chuyển đổi primitive hợp lệ. Nó **không** tùy tiện sửa thứ tự/số lượng tham số, và không chuyển chuỗi `"42"` thành số nguyên như một parser nghiệp vụ.

`asType` xây một handle với `MethodType` khác theo phép chuyển đổi hợp lệ. Trong ví dụ, `getter.asType((Object)Object)` biến setter/getter typed thành một callable kiểu tổng quát cho framework; runtime vẫn sẽ kiểm tra receiver thực tế trước khi truy cập field.

### 7.3. invokeWithArguments cho danh sách động

`invokeWithArguments(Object...)` thuận tiện khi số và kiểu đối số chỉ có thể ghép thành một `Object[]` lúc runtime. Nó có chi phí thích nghi/boxing và không đảm bảo mọi đối số đều hợp lệ. Đừng coi nó là lựa chọn mặc định cho đường gọi nóng mà đã biết chữ ký.

`MethodHandle` cũng hỗ trợ các adapter như `bindTo` để gắn receiver, `asSpreader` để nhận mảng đối số và `asCollector` cho thao tác mảng tương ứng. Chỉ dùng chúng khi có hợp đồng kiểu cụ thể, tránh tự tạo “đường tắt” dựa trên phép cast ngẫu nhiên.

### 7.4. Reflection và handle có đường lỗi khác nhau

| Tình huống | Reflection truyền thống | Method handle |
| --- | --- | --- |
| Gọi method instance | `method.invoke(receiver, args...)` | Receiver là tham số đầu của handle |
| Gọi constructor | `constructor.newInstance(args...)` | `handle.invokeExact(args...)` trả instance đúng kiểu |
| Đọc/ghi field | `field.get(receiver)` / `field.set(receiver, value)` | Getter/setter handle có `MethodType` cụ thể |
| Quyền truy cập | Kiểm tra khi gọi theo luật Reflection; có cờ suppress-access | Kiểm tra khi tạo handle từ `Lookup` |
| Lỗi do code đích ném | `InvocationTargetException` bao lỗi từ method/constructor | Exception đích truyền ra trực tiếp |
| Sai kiểu gọi | `IllegalArgumentException`, lỗi liên quan Reflection | `WrongMethodTypeException`, `ClassCastException` hoặc lỗi chuyển đổi liên quan |
| Kiểu trả về | `Object`, primitive được boxed | Theo `MethodType`, có thể là primitive hoặc `void` |

## 8. Sử dụng trong một bộ ánh xạ dữ liệu runtime

Khi viết serializer/mapper, bạn thường khám phá field và annotation một lần, tạo handle tương ứng và dùng lại. Quy trình:

1. **Chọn field** theo chính sách rõ ràng: public hay declared, instance/static, có cần đọc hay ghi, có cho phép private không.
2. **Kiểm tra quyền** bằng lookup phù hợp. Có thể dùng `publicLookup` cho API public hoặc `privateLookupIn` khi ứng dụng thật sự được cấp quyền.
3. **Tạo getter** bằng `unreflectGetter(field)`; tạo setter chỉ nếu field có thể ghi và thao tác thuộc hợp đồng dữ liệu. Với field `final`, ưu tiên constructor hay factory để tạo instance đúng trạng thái.
4. **Đọc `getter.type()` / `setter.type()`** để lưu signature. Chọn cách gọi typed hoặc adapter `asType`, giữ nguyên quy tắc receiver/static.
5. **Cache handle** khi dùng nhiều lần cho cùng metadata, nhưng nhớ class loader có thể thay đổi trong ứng dụng plugin/hot reload; cache không kiểm soát vòng đời có thể giữ lớp và loader sống ngoài ý muốn.
6. **Khi có Method/Constructor từ quá trình chọn trước**, gọi `unreflect`/`unreflectConstructor` thay vì tìm lại bằng tên. Phân loại exception lúc tạo và lúc thực thi.

Một đoạn khung tạo getter cho field được lựa chọn từ metadata:

```java
static MethodHandle makeReadable(Field field, MethodHandles.Lookup lookup)
        throws IllegalAccessException {
    return lookup.unreflectGetter(field);
}
```

Đây là method minh họa cần import `Field`, `MethodHandle` và `MethodHandles`; nó **không tự nâng quyền**. Trong ứng dụng thực, caller quyết định field nào được truy cập và Lookup nào được phép dùng.

### 8.1. Khi nào nên dùng VarHandle?

Nếu bài toán chỉ cần đọc/ghi field qua handle, `unreflectGetter` và `unreflectSetter` là trực tiếp. Nếu muốn thao tác cập nhật đồng thời hay memory ordering (ví dụ volatile get/set, compare-and-set, get-and-add, acquire/release), cân nhắc `VarHandle`, được tạo qua `findVarHandle`, `findStaticVarHandle` hoặc `unreflectVarHandle`. Không tự viết `get` rồi `set` thành một thao tác atomic nếu có tranh chấp dữ liệu.

## 9. Các trường hợp đặc biệt và lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| `NoSuchFieldException` | Sai tên field, sai kiểu, gọi instance lookup cho static hoặc ngược lại cần phân loại | Kiểm tra `getDeclaredFields()`, `field.getType()`, `Modifier.isStatic` |
| `IllegalAccessException` lúc `findGetter/unreflect` | Lookup không có quyền với thành viên hoặc module | Xem modifier, lookup class, exports/opens; thiết kế quyền truy cập hợp lệ |
| `IllegalAccessException` lúc `findSetter` | Field `final` hoặc không truy cập được | Không cố tạo setter cho final; khởi tạo qua constructor |
| `WrongMethodTypeException` lúc `invokeExact` | Call site sai kiểu receiver, tham số hay kiểu trả về | In `handle.type()`, đối chiếu kiểu compile-time thực của biểu thức gọi |
| `ClassCastException` khi dùng handle đã thích nghi | Đối tượng thật không ép được về kiểu field/receiver | Kiểm tra đầu vào và kiểu metadata trước khi invoke |
| `NullPointerException` lúc gọi getter instance | Receiver null | Truyền đúng instance, không dùng null cho field instance |
| Handle đọc static có “thừa” receiver | Nhầm signature static với instance | `staticGetter.type()` không có receiver |
| Setter được dùng như hàm trả giá trị | Setter handle có return type `void` | Gọi như statement hoặc thích nghi hợp lệ nếu framework cần kết quả khác |
| `InvocationTargetException` chỉ xuất hiện ở luồng Reflection | Method/Constructor reflective wrapping | Với handle, bắt trực tiếp exception gốc; không đòi phải có wrapper |
| Đọc private field được nhưng unreflect thất bại | `getDeclaredField` lấy metadata, không trao quyền chạy | Dùng Lookup có quyền thích hợp, kiểm tra mở package của module |
| Handle thay đổi hành vi khi truyền plugin khác | Handle mang capability đã được cấp tại lúc tạo; dữ liệu/receiver có thể khác | Kiểm soát nơi lưu/chia sẻ handle, class loader và vòng đời cache |
| `findVirtual` không tìm constructor | Constructor không phải một virtual method tên “<init>” cho API này | Dùng `findConstructor` hay `unreflectConstructor` |

**Không nên nuốt lỗi** bằng cách bắt `Throwable` rồi bỏ qua: khi gọi `MethodHandle.invokeExact`, method đích có thể ném checked/unchecked exception hoặc error. Phân loại lỗi do tạo handle (`NoSuchFieldException`, `NoSuchMethodException`, `IllegalAccessException`) tách biệt với lỗi khi gọi (`WrongMethodTypeException`, exception gốc từ code đích). Trong ví dụ chạy độc lập, `main throws Throwable` nhằm giữ cú pháp ngắn; trong sản phẩm thật, xây chính sách xử lý lỗi ở biên phù hợp.

## 10. Bài tập tự kiểm tra

**Bài A.** Có `Field amount` của `long amount` trong `Account`. Một thư viện đã có `Field`, muốn tạo getter. Phải gọi gì? Kiểu handle là gì?

**Đáp án:** `lookup.unreflectGetter(amount)`; thông thường kiểu `(Account)long` nếu đây là field instance và không có sự hạn chế receiver đặc biệt do protected access.

**Bài B.** Field `static String mode`. Dùng `findGetter(Setting.class, "mode", String.class)` có đúng không?

**Đáp án:** Sai vì đây là static field. Dùng `findStaticGetter` để được `()String`, hoặc `unreflectGetter(field)` với metadata Field tương ứng.

**Bài C.** Có `Method` cho `String format(int width)` (instance) trong `Report`. Sau `lookup.unreflect(method)`, chữ ký handle là gì?

**Đáp án:** `(Report,int)String`. Receiver xuất hiện trước `width`. Nếu method là static, chỉ còn `(int)String`.

**Bài D.** Có `Constructor<User>` nhận (`String`, `int`). `unreflectConstructor` trả kiểu handle nào? Có cần receiver không?

**Đáp án:** `(String,int)User`; không cần receiver. Một `User` mới được tạo khi gọi handle.

**Bài E.** `MethodHandle getAge` có kiểu `(Person)int`, nhưng mã viết `Object age = getAge.invokeExact(person);`. Vì sao lỗi?

**Đáp án:** Call site của `invokeExact` đòi kết quả kiểu `Object`, không trùng `int` của handle. Dùng `int age = (int) getAge.invokeExact(person);` hoặc một adapter có kiểu phù hợp.

**Bài F.** Framework muốn thay đổi `public final String id` bằng `findSetter`. Có nên dựa vào `setAccessible` để bắt buộc thành công?

**Đáp án:** Không. `findSetter` từ chối final field; `unreflectSetter` cũng bị giới hạn rất chặt, đặc biệt static final và field trong record/hidden class. Thiết kế constructor hoặc factory để cung cấp giá trị đúng từ lúc tạo object.

## Tài liệu JDK 17 dùng để đối chiếu

- [`MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `findGetter`/`findSetter`/`findStaticGetter`/`findStaticSetter`, `unreflect`, `unreflectGetter`, `unreflectSetter`, `unreflectConstructor`, quy tắc truy cập.
- [`MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): `type()`, `invokeExact`, `invoke`, `asType`, `bindTo` và `invokeWithArguments`.
- [`MethodHandles`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `lookup()`, `publicLookup()` và `privateLookupIn`.
- [`java.lang.reflect.Field`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html): kiểu field, modifier, truy cập và điều kiện hạn chế ghi final field.
- [`java.lang.reflect.Method`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html) và [`Constructor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html): siêu dữ liệu thành viên và khác biệt so với handle.
- [`VarHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): thao tác field với access modes, memory ordering và atomic operations.

**Ghi nhớ:** `findGetter`/`findSetter` phù hợp khi biết class–tên–kiểu; `unreflectGetter`/`unreflectSetter` phù hợp khi đã có `Field`. `unreflect(Method)` chuyển method, `unreflectConstructor(Constructor<?>)` chuyển constructor thành handle tạo instance. Luôn đọc `handle.type()`, kiểm tra receiver/static, chỉ tạo setter trên field có thể ghi và coi `Lookup` là quyền truy cập được cấp có chủ đích.
