# findGetter(), findSetter(), findStaticGetter() và findStaticSetter(): đọc ghi field bằng handle

## 1. Mục tiêu bài học

Trong Java, `java.lang.invoke.MethodHandle` là một tham chiếu có kiểu được kiểm tra chặt tới một thao tác có thể được JVM thực thi. Ngoài lời gọi method, một `MethodHandle` còn có thể đại diện cho việc **đọc hoặc ghi field**. Thay vì tìm `Field` rồi gọi `get()/set()` của Core Reflection, ta có thể tạo handle trực tiếp bằng bốn phương thức trên `MethodHandles.Lookup`:

- `findGetter()`: đọc field của **instance**.
- `findSetter()`: ghi field của **instance**.
- `findStaticGetter()`: đọc field **static**.
- `findStaticSetter()`: ghi field **static**.

Mỗi handle có chữ ký cụ thể dưới dạng `MethodType`: có hay không có tham số **receiver**, có hoặc không có tham số **giá trị mới**, và kiểu trả về của thao tác. Đó là điều phải hiểu rõ trước khi gọi `invokeExact()` hoặc `invoke()`.

Bài thuộc chương **MethodHandle** của module `JAVA_VERSION_JAVA18`. Module tìm hiểu các thay đổi từ Java 18 vẫn hữu ích trên JDK hiện đại, gồm UTF-8 mặc định, Simple Web Server, Javadoc snippets và hợp đồng API liên quan đến phân giải tên, reflection, MethodHandle. JEP 416 trong Java 18 thay đổi cách Core Reflection được triển khai dựa trên method handles; tuy nhiên, bốn phương thức lookup trong bài là **public API ổn định, vẫn dùng được trên JDK hiện đại**, không phải mẹo khai thác chi tiết triển khai cũ.

Theo yêu cầu chỉ học kiến thức còn áp dụng hiện nay, bài không dùng Java internals, `Unsafe`, mẹo sửa field `final`, hoặc cơ chế bỏ qua module boundaries đã lỗi thời.

Sau bài học, bạn có thể:

1. Chọn đúng factory giữa instance/static và getter/setter.
2. Suy ra `MethodType` của handle từ class chứa field và kiểu field.
3. Gọi `invokeExact()` đúng kiểu tham số và kiểu trả về.
4. Đọc được handle từ `lookup()` và phân biệt quyền của `publicLookup()`, `privateLookupIn()`.
5. Dự đoán các lỗi khi sai tên, sai kiểu, sai static/instance, sai quyền hoặc field `final`.
6. Giải thích khởi tạo class khi gọi static field handle.
7. Biết lúc nào `VarHandle` thích hợp hơn `MethodHandle` cho `volatile`/atomic operations.
8. Viết một chương trình kiểm chứng bằng JDK thực tế.

## 2. Bốn factory trên `MethodHandles.Lookup`

Chữ ký public API:

~~~java
MethodHandle findGetter(
        Class<?> refc, String name, Class<?> type)
        throws NoSuchFieldException, IllegalAccessException;

MethodHandle findSetter(
        Class<?> refc, String name, Class<?> type)
        throws NoSuchFieldException, IllegalAccessException;

MethodHandle findStaticGetter(
        Class<?> refc, String name, Class<?> type)
        throws NoSuchFieldException, IllegalAccessException;

MethodHandle findStaticSetter(
        Class<?> refc, String name, Class<?> type)
        throws NoSuchFieldException, IllegalAccessException;
~~~

Tham số ở cả bốn phương thức đều mang cùng ý nghĩa:

| Tham số | Ý nghĩa |
| --- | --- |
| `refc` | `Class<?>` dùng để phân giải field, ví dụ `Counter.class`. |
| `name` | Tên field, ví dụ `"value"`; phân biệt chữ hoa/chữ thường. |
| `type` | **Kiểu của field**, ví dụ `int.class`, `String.class` hoặc `int[].class`. |
| Giá trị trả về | Một `MethodHandle` với `MethodType` xác định được từ thao tác đọc/ghi. |

**Tham số `type` không phải `MethodType`.** Ta truyền kiểu của field là một `Class<?>`. `MethodType` là chữ ký **kết quả** của handle có thể hỏi qua `handle.type()`.

### 2.1. Suy ra chữ ký handle

Giả sử có hai field:

~~~java
final class Counter {
    int value;
    static String state;
}
~~~

Gọi `C` là lớp chứa field, `T` là kiểu field:

| Factory | Field | Kiểu `MethodHandle.type()` | Tương đương Java |
| --- | --- | --- | --- |
| `findGetter(C, "value", int.class)` | Instance | `(C)int` | `int x = c.value;` |
| `findSetter(C, "value", int.class)` | Instance | `(C, int)void` | `c.value = n;` |
| `findStaticGetter(C, "state", String.class)` | Static | `()String` | `String s = C.state;` |
| `findStaticSetter(C, "state", String.class)` | Static | `(String)void` | `C.state = s;` |

**Chỉ handle cho instance field có receiver** làm tham số đầu tiên. Static field gắn với class, vì thế getter không có tham số còn setter chỉ nhận một giá trị mới.

Chữ ký `(C)int` và `(C, int)void` ở bảng là ký hiệu khái niệm: JVM dùng các đối tượng `Class` và `MethodType`, không dùng tên biến receiver hay tên field trong `MethodType`.

### 2.2. Nhận diện bằng `MethodType.methodType`

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle getter =
        lookup.findGetter(Counter.class, "value", int.class);

MethodHandle setter =
        lookup.findSetter(Counter.class, "value", int.class);

MethodHandle staticGetter =
        lookup.findStaticGetter(Counter.class, "state", String.class);

MethodHandle staticSetter =
        lookup.findStaticSetter(Counter.class, "state", String.class);

System.out.println(getter.type().equals(
        MethodType.methodType(int.class, Counter.class))); // true

System.out.println(setter.type().equals(
        MethodType.methodType(void.class, Counter.class, int.class))); // true

System.out.println(staticGetter.type().equals(
        MethodType.methodType(String.class))); // true

System.out.println(staticSetter.type().equals(
        MethodType.methodType(void.class, String.class))); // true
~~~

`MethodType.methodType(returnType, parameterTypes...)` đặt **return type trước**, khác với thứ tự khi gọi setter hoặc getter. Với getter instance, kiểu trả về là `int.class` và tham số receiver là `Counter.class`.

Nếu `Counter` không thể truy cập với quyền của `lookup` hiện tại, phương thức tìm handle sẽ thất bại. Phần trên giả định code có đủ quyền để tra cứu field.

## 3. `findGetter()`: đọc instance field

Với field:

~~~java
public class Reading {
    public int count = 10;
}
~~~

Một lookup có quyền phù hợp:

~~~java
MethodHandle getCount = MethodHandles.lookup()
        .findGetter(Reading.class, "count", int.class);
~~~

Tạo instance rồi gọi:

~~~java
Reading reading = new Reading();
int current = (int) getCount.invokeExact(reading);
System.out.println(current); // 10
~~~

Handle nhận **một đối số** kiểu `Reading` và trả về primitive `int`. Không dùng `getCount.invokeExact()` vì thiếu receiver; cũng không truyền `Reading.class` thay receiver.

### 3.1. Receiver không phải tên class

~~~java
int x = (int) getCount.invokeExact(reading);
~~~

`reading` là một object được tạo từ `Reading`, không phải đối tượng `Class<Reading>`. Với method handle instance field, JVM thao tác trên instance được truyền tới.

Nếu receiver là `null`, lời gọi đọc instance field sẽ thất bại khi truy cập field, thường là `NullPointerException`, tương tự việc đọc `reading.count` khi `reading == null`.

### 3.2. Kiểu getter có thể là reference hoặc primitive

~~~java
class Person {
    public String name;
    public long id;
    public int[] scores;
}
~~~

Các lookup:

~~~java
MethodHandle name = lookup.findGetter(
        Person.class, "name", String.class);
MethodHandle id = lookup.findGetter(
        Person.class, "id", long.class);
MethodHandle scores = lookup.findGetter(
        Person.class, "scores", int[].class);
~~~

Chữ ký tương ứng: `(Person)String`, `(Person)long` và `(Person)int[]`. Kiểu mảng `int[].class` là **một kiểu field**, không có nghĩa getter nhận thêm tham số index.

## 4. `findSetter()`: ghi instance field

Với field thay đổi được:

~~~java
public class Reading {
    public int count = 10;
}
~~~

Tạo setter và dùng:

~~~java
MethodHandle setCount = MethodHandles.lookup()
        .findSetter(Reading.class, "count", int.class);

Reading reading = new Reading();
setCount.invokeExact(reading, 42);
System.out.println(reading.count); // 42
~~~

Handle có chữ ký `(Reading, int)void`:

- Đối số thứ nhất: receiver là `Reading`.
- Đối số thứ hai: giá trị `int` cần ghi.
- Kiểu trả về: `void`, **không trả lại giá trị vừa ghi**.

Nếu cần đọc giá trị trước/sau khi ghi, tạo getter riêng hoặc dùng API khác phù hợp. Setter handle không tự cung cấp compare-and-set.

### 4.1. Setter không dành cho field `final`

~~~java
public class ImmutableItem {
    public final int id = 7;
}
~~~

Lệnh sau không được phép chỉ vì lookup có thể thấy field:

~~~java
MethodHandle setId = lookup.findSetter(
        ImmutableItem.class, "id", int.class);
~~~

Theo hợp đồng `Lookup.findSetter`, nếu field là `final`, lookup **thất bại với `IllegalAccessException`**. Tương tự `findStaticSetter` cũng từ chối `static final`.

Có một số cơ chế Reflection với điều kiện riêng để thao tác field trong các bối cảnh rất hạn chế, nhưng **không nên chuyển sang mẹo sửa `final`**. Trong bài này, hãy coi `findSetter` và `findStaticSetter` là thao tác ghi các field **không final**. Với state bất biến, thay object hoặc sử dụng constructor/factory đúng thiết kế.

## 5. `findStaticGetter()`: đọc static field

Với khai báo:

~~~java
public class Settings {
    public static String mode = "idle";
}
~~~

Tìm và gọi:

~~~java
MethodHandle getMode = MethodHandles.lookup()
        .findStaticGetter(Settings.class, "mode", String.class);

String current = (String) getMode.invokeExact();
System.out.println(current); // idle
~~~

Không có receiver. `Settings.class` chỉ xuất hiện ở **thời điểm lookup**, không phải một đối số của `invokeExact()`.

### 5.1. Static getter cũng đọc được field `final`

~~~java
public class Settings {
    public static final String APP_NAME = "demo";
}
~~~

~~~java
MethodHandle getAppName = lookup.findStaticGetter(
        Settings.class, "APP_NAME", String.class);

String name = (String) getAppName.invokeExact();
~~~

Việc **đọc** `final` là hợp lệ nếu quyền truy cập cho phép. Chỉ thao tác **ghi** bằng `findStaticSetter` mới bị từ chối.

### 5.2. Class initialization

Theo đặc tả, khi static getter handle được **gọi**, lớp khai báo field sẽ được khởi tạo nếu chưa khởi tạo. Tương tự với static setter handle.

Đừng hiểu “tìm handle” và “thực hiện field access” là cùng một thời điểm. Nếu class có static initializer làm I/O hoặc có side effects, hãy phân biệt lookup với việc gọi getter/setter khi kiểm chứng.

## 6. `findStaticSetter()`: ghi static field

Với mutable static field:

~~~java
public class Settings {
    public static String mode = "idle";
}
~~~

~~~java
MethodHandle setMode = MethodHandles.lookup()
        .findStaticSetter(Settings.class, "mode", String.class);

setMode.invokeExact("active");
System.out.println(Settings.mode); // active
~~~

Chữ ký là `(String)void`: một đối số giá trị mới, không có receiver và không có giá trị trả về.

### 6.1. Static setter không phải lời gọi method

`findStaticSetter(Settings.class, "mode", String.class)` tạo handle tương đương thao tác ghi static field, không gọi một method tên `mode`. Vì vậy:

- Không dùng `findStatic(...)` để tìm field.
- Không truyền `MethodType` vào `findStaticSetter`; tham số thứ ba là `String.class`.
- Không truyền `Settings.class` hay một instance `Settings` khi invoke static setter.

### 6.2. Với `static final`

~~~java
public static final int LIMIT = 100;
~~~

`findStaticGetter(..., "LIMIT", int.class)` có thể đọc giá trị nếu có quyền; `findStaticSetter(..., "LIMIT", int.class)` phải bị từ chối bằng `IllegalAccessException`.

Đừng dựa vào việc mở module hoặc có private lookup để tránh quy tắc này. `final` là một điều kiện access riêng trong hợp đồng factory setter.

## 7. Ví dụ Java hoàn chỉnh: bốn factory và các lỗi cần thấy

Tạo một file `FieldHandlesDemo.java` với toàn bộ code sau. Ví dụ không cần framework hoặc thư viện ngoài JDK, và chạy được với Java hiện đại.

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public final class FieldHandlesDemo {

    private static final class Sample {
        private int value = 7;
        private static String label = "idle";

        private final long serial = 9L;
        private static final int LIMIT = 100;
    }

    public static void main(String[] args) throws Throwable {
        // Sample ở cùng module và cùng nest; đây là ví dụ
        // tạo lookup có quyền private trên class đích.
        MethodHandles.Lookup access =
                MethodHandles.privateLookupIn(
                        Sample.class, MethodHandles.lookup());

        MethodHandle getValue =
                access.findGetter(Sample.class, "value", int.class);
        MethodHandle setValue =
                access.findSetter(Sample.class, "value", int.class);

        MethodHandle getLabel =
                access.findStaticGetter(Sample.class, "label", String.class);
        MethodHandle setLabel =
                access.findStaticSetter(Sample.class, "label", String.class);

        // Xác minh bốn kiểu handle trước khi gọi.
        boolean getterType = getValue.type().equals(
                MethodType.methodType(int.class, Sample.class));
        boolean setterType = setValue.type().equals(
                MethodType.methodType(void.class, Sample.class, int.class));
        boolean staticGetterType = getLabel.type().equals(
                MethodType.methodType(String.class));
        boolean staticSetterType = setLabel.type().equals(
                MethodType.methodType(void.class, String.class));

        System.out.println("types: " + getterType + " "
                + setterType + " " + staticGetterType + " "
                + staticSetterType);

        Sample sample = new Sample();

        // Instance getter/setter: phải truyền receiver.
        int before = (int) getValue.invokeExact(sample);
        setValue.invokeExact(sample, 21);
        int after = (int) getValue.invokeExact(sample);

        System.out.println("instance before: " + before);
        System.out.println("instance after: " + after);

        // Static getter/setter: không có receiver.
        String labelBefore = (String) getLabel.invokeExact();
        setLabel.invokeExact("active");
        String labelAfter = (String) getLabel.invokeExact();

        System.out.println("static before: " + labelBefore);
        System.out.println("static after: " + labelAfter);

        // final instance field có thể đọc khi có quyền,
        // nhưng findSetter không cấp handle ghi.
        MethodHandle getSerial =
                access.findGetter(Sample.class, "serial", long.class);
        long serial = (long) getSerial.invokeExact(sample);
        System.out.println("final instance read: " + serial);

        try {
            access.findSetter(Sample.class, "serial", long.class);
        } catch (IllegalAccessException expected) {
            System.out.println("final instance setter blocked");
        }

        try {
            access.findStaticSetter(Sample.class, "LIMIT", int.class);
        } catch (IllegalAccessException expected) {
            System.out.println("final static setter blocked");
        }

        // Dùng factory instance cho field static: sai kind.
        try {
            access.findGetter(Sample.class, "label", String.class);
        } catch (IllegalAccessException expected) {
            System.out.println("wrong field kind blocked");
        }

        // Tên đúng nhưng kiểu field yêu cầu sai.
        try {
            access.findGetter(Sample.class, "value", long.class);
        } catch (NoSuchFieldException expected) {
            System.out.println("wrong field type not found");
        }

        // invokeExact đòi hỏi call-site type khớp hoàn toàn.
        try {
            int impossible = (int) getValue.invokeExact((Object) sample);
            System.out.println(impossible);
        } catch (WrongMethodTypeException expected) {
            System.out.println("invokeExact wrong signature");
        }

        // invoke cho phép thích ứng kiểu trong giới hạn asType.
        int adapted = (int) getValue.invoke((Object) sample);
        System.out.println("invoke adapted: " + adapted);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac FieldHandlesDemo.java
java FieldHandlesDemo
~~~

Kết quả dự kiến:

~~~text
types: true true true true
instance before: 7
instance after: 21
static before: idle
static after: active
final instance read: 9
final instance setter blocked
final static setter blocked
wrong field kind blocked
wrong field type not found
invokeExact wrong signature
invoke adapted: 21
~~~

### 7.1. Vì sao không dùng `publicLookup()` cho private fields?

Ví dụ có các field `private`. `MethodHandles.publicLookup()` chỉ hỗ trợ truy cập hạn chế vào public members của public classes trong package được export không điều kiện. Nó không có quyền truy cập private field của `Sample`. `MethodHandles.privateLookupIn(...)` trong ví dụ dựa trên một caller lookup có đủ quyền trong cùng module, vì vậy có thể tạo lookup phù hợp.

Ngay cả khi cùng một class có quyền truy cập private member, **không nên truyền một private lookup cho mã không tin cậy**: `Lookup` là capability cấp quyền, không phải chỉ một cấu hình vô hại.

### 7.2. Vì sao sai kind không phải lỗi sai tên?

`Sample.label` tồn tại và có đúng kiểu `String`, nhưng nó là **static**. Lệnh:

~~~java
access.findGetter(Sample.class, "label", String.class);
~~~

dùng sai factory. Hợp đồng `findGetter` nêu `IllegalAccessException` khi field là static. Muốn đọc `label` phải dùng `findStaticGetter`.

Tương tự:

- `findSetter` từ chối field static và field final.
- `findStaticGetter` từ chối field **không static**.
- `findStaticSetter` từ chối field **không static** hoặc **final**.

### 7.3. Vì sao `invokeExact((Object) sample)` thất bại?

Handle getter instance có type `(Sample)int`, nhưng call site:

~~~java
int x = (int) getValue.invokeExact((Object) sample);
~~~

mang type đối số tĩnh `Object`. `invokeExact` không tự downcast từ `Object` sang `Sample`, nên ném `WrongMethodTypeException`.

Cùng đối số đó, `invoke` có thể tạo adaptation tương đương `asType` nếu phép chuyển đổi hợp lệ:

~~~java
int x = (int) getValue.invoke((Object) sample);
~~~

Nhưng nếu object thực tế không phải `Sample`, phép cast runtime có thể thất bại. `invoke` linh hoạt hơn `invokeExact` nhưng không biến mọi chữ ký sai thành hợp lệ.

## 8. `invokeExact()`, `invoke()` và `handle.type()`

Mỗi MethodHandle có kiểu bất biến ở thời điểm tạo. Hãy đọc `handle.type()` trước khi viết call site.

### 8.1. `invokeExact` yêu cầu khớp tuyệt đối

Với handle `(Sample)int`:

~~~java
Sample sample = new Sample();
int value = (int) getValue.invokeExact(sample);
~~~

Phần cast `(int)` biểu thị kiểu trả về của **call site**. Nếu thay bằng:

~~~java
Object value = getValue.invokeExact(sample);
~~~

code có thể **biên dịch** (vì phương thức signature-polymorphic), nhưng call site lúc runtime yêu cầu return type `Object` thay vì `int`. Khi đó handle type không khớp và ném `WrongMethodTypeException`.

Tương tự, nếu getter handle có kiểu `(Sample)String`, viết `(Object) handle.invokeExact(sample)` yêu cầu return type `Object`; muốn gọi exact, dùng `(String)` rồi có thể gán lên biến `Object`:

~~~java
String name = (String) getName.invokeExact(sample);
Object boxed = name;
~~~

### 8.2. Setter trả `void`

Với `setValue.type() == (Sample, int)void`:

~~~java
setValue.invokeExact(sample, 24);
~~~

Đừng cố nhận return value từ setter. Một call site yêu cầu return type khác `void` không thể gọi `invokeExact` đúng chữ ký.

### 8.3. `invoke` có thích ứng, nhưng không tùy tiện

`MethodHandle.invoke` có thể thích ứng đối số và kiểu trả về theo `asType`. Ví dụ chuyển đổi kiểu reference có thể được thực hiện nếu an toàn tại runtime; boxing/unboxing và một số chuyển đổi primitive cũng có quy tắc cụ thể.

Nhưng `invoke` **không**:

- Tìm lại field khác nếu tên/kiểu field tra cứu sai.
- Tự chuyển getter thành setter.
- Bỏ qua access check đã diễn ra khi lookup.
- Ghi vào field `final` bị factory setter từ chối.
- Biến phép đọc-ghi nhiều bước thành atomic update.

Đối với đường gọi có thể kiểm soát type ở compile time, `invokeExact` làm hợp đồng rõ ràng nhất. Khi kiểu chỉ biết động, có thể dùng `invoke`, `asType` hoặc adapter phù hợp sau khi hiểu rõ `MethodType`.

## 9. Lookup quyết định quyền tại thời điểm tìm handle

### 9.1. `MethodHandles.lookup()`

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
~~~

`lookup()` trả một lookup gắn với **class thực sự gọi** phương thức đó, mang quyền truy cập phù hợp với caller. Nó không mặc định được phép đọc/ghi private field của mọi class trong JVM.

Ví dụ tìm một public instance field của public class trong package truy cập được:

~~~java
public class PublicData {
    public int number;
}
~~~

~~~java
MethodHandle getNumber = MethodHandles.lookup()
        .findGetter(PublicData.class, "number", int.class);
~~~

Nếu caller có quyền Java thông thường với `PublicData.number`, việc lookup tương ứng có thể thành công.

### 9.2. `MethodHandles.publicLookup()`

~~~java
MethodHandles.Lookup publicOnly = MethodHandles.publicLookup();
~~~

Lookup này có quyền hạn chế: truy cập public members của public classes trong các package được export vô điều kiện, theo hợp đồng module. Không dùng nó để tìm private field.

### 9.3. `MethodHandles.privateLookupIn()`

Khi phải truy cập private field trong một class khác mà caller được module policy cho phép, có thể tạo private lookup:

~~~java
MethodHandles.Lookup base = MethodHandles.lookup();

MethodHandles.Lookup privateAccess =
        MethodHandles.privateLookupIn(Target.class, base);

MethodHandle fieldGetter = privateAccess.findGetter(
        Target.class, "secret", String.class);
~~~

Điều kiện không đơn giản là “có tên class là được”. Với caller lookup ở module `M1` và target class ở module `M2` khác nhau, tài liệu `privateLookupIn` yêu cầu:

1. Caller lookup có đủ quyền `PRIVATE` và `MODULE`.
2. Module `M1` đọc được `M2`.
3. `M2` **mở package chứa target class cho M1** bằng `opens` thích hợp hoặc cấu hình runtime tương đương.

Vì vậy, `exports` của package không đủ để deep-reflect vào private field, và `privateLookupIn` không phải lối tắt vượt Java module boundaries.

Ví dụ descriptor khái niệm:

~~~java
// module-info.java của demo.data
module demo.data {
    exports demo.api;
    opens demo.model to demo.inspector;
}
~~~

~~~java
// module-info.java của demo.inspector
module demo.inspector {
    requires demo.data;
}
~~~

Module `demo.inspector` có thể được cấp quyền deep lookup vào class ở `demo.model` nếu đáp ứng đầy đủ hợp đồng. Việc dùng `opens demo.model to demo.inspector` cụ thể hơn mở rộng toàn bộ module.

### 9.4. Khi đã tạo handle

Factory methods kiểm tra access **ngay khi lookup**. MethodHandle đã được tạo là một capability có thể được gọi theo chữ ký mà không cần tra tên member lại trong mỗi lần gọi.

Từ đó:

- Không để lộ handle nhạy cảm hoặc private lookup cho code không tin cậy.
- Không cho rằng module khác có thể tự `findGetter` chỉ vì bạn đã tạo handle thành công trong module của mình.
- Khi một handle đã được chia sẻ, caller của handle vẫn phải tuân thủ `MethodType` nhưng không tự thực hiện lại access check như một lần lookup mới.

## 10. Field resolution, field hiding và receiver

Một field khác method ở chỗ **không có dynamic dispatch theo override**. Subclass có thể khai báo một field cùng tên với superclass (*field hiding*), nhưng đó là **hai field độc lập**. Handle được tạo để truy cập field nào sẽ tiếp tục truy cập field đó khi được gọi với receiver tương thích.

Ví dụ:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;

public class FieldHidingDemo {
    public static class Parent {
        public int size = 10;
    }

    public static class Child extends Parent {
        public int size = 20;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodHandle parentSize = lookup.findGetter(
                Parent.class, "size", int.class);
        MethodHandle childSize = lookup.findGetter(
                Child.class, "size", int.class);

        Child child = new Child();

        int fromParent = (int) parentSize.invokeExact((Parent) child);
        int fromChild = (int) childSize.invokeExact(child);

        System.out.println(fromParent); // 10
        System.out.println(fromChild);  // 20
    }
}
~~~

Hai handle đại diện cho hai field khác nhau:

- `parentSize.type()` là `(Parent)int`.
- `childSize.type()` là `(Child)int`.
- Dù receiver thực tế đều là `Child`, handle thứ nhất đọc `Parent.size`, handle thứ hai đọc `Child.size`.

Đừng dùng ví dụ từ `Method.invoke()` về method override để suy luận field handles có dynamic dispatch tương tự. Field được phân giải khi lookup tạo handle; receiver chỉ xác định **object** chứa phần field tương ứng.

### 10.1. Với inherited field và protected access

`refc` chỉ class hoặc interface dùng để phân giải field. Một field `public` kế thừa có thể được tìm thông qua subclass theo quy tắc phân giải của JVM. Tuy nhiên, quyền `protected` ở package khác có quy tắc riêng: receiver type của handle có thể bị **thu hẹp** về lookup class hoặc subclass của nó.

Vì thế, thay vì giả định receiver luôn đúng bằng `refc` trong mọi bối cảnh, hãy xem `handle.type()` sau khi lookup, đặc biệt với protected field và kế thừa. Quy tắc thu hẹp receiver là một phần của kiểm soát truy cập, không phải kiểu ép tự do của `invokeExact`.

## 11. So sánh field handle với Reflection và VarHandle

| API | Mục đích chính | Hợp đồng kiểu và quyền |
| --- | --- | --- |
| `java.lang.reflect.Field.get/set` | Đọc/ghi field qua Core Reflection | Dùng `Object` cho receiver/giá trị, cần xét access và boxing/unboxing |
| `Lookup.findGetter/findSetter` | Tạo direct field method handles cho instance | Chữ ký rõ receiver và kiểu field |
| `Lookup.findStaticGetter/findStaticSetter` | Tạo direct field method handles cho static field | Chữ ký không có receiver |
| `Lookup.findVarHandle/findStaticVarHandle` | Truy cập biến bằng các **access modes** khác nhau | Hỗ trợ `get`, `set`, `getVolatile`, `setVolatile`, `compareAndSet` và nhiều mode khác khi phù hợp |

Không nên khẳng định một API luôn nhanh hơn API khác trên mọi JVM. Hiệu năng phụ thuộc cách sử dụng handle, JIT, khả năng constant-fold, boxing, adapter và đặc tính workload. Lợi ích chắc chắn của `MethodHandle` là chữ ký `MethodType` rõ ràng và khả năng kết hợp thành các chuỗi thao tác bằng API method-handle.

### 11.1. Getter/setter không phải atomic read-modify-write

Giả sử hai thread cùng thực hiện:

~~~java
int before = (int) getValue.invokeExact(shared);
setValue.invokeExact(shared, before + 1);
~~~

Đây là **hai thao tác riêng**. Nó không tạo thành một phép cộng nguyên tử chỉ vì cả hai thao tác đều thông qua `MethodHandle`. Có thể xảy ra lost update khi nhiều thread thay đổi cùng field.

Nếu cần atomic compare-and-set, dùng `VarHandle` (hoặc abstraction đồng bộ/atomic phù hợp):

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class AtomicCounter {
    private volatile int count;

    public static void main(String[] args) throws Exception {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        VarHandle counter = lookup.findVarHandle(
                AtomicCounter.class, "count", int.class);

        AtomicCounter holder = new AtomicCounter();

        boolean updated = counter.compareAndSet(holder, 0, 1);
        int result = (int) counter.getVolatile(holder);

        System.out.println(updated); // true
        System.out.println(result);  // 1
    }
}
~~~

`VarHandle` có khái niệm **variable type** và **coordinate types**:

- Instance field `count` có variable type `int` và coordinate type `AtomicCounter`.
- Static field không có receiver coordinate.
- Access mode quyết định chữ ký và memory-ordering semantics của phép thao tác.

`compareAndSet` hỗ trợ phép cập nhật có điều kiện nguyên tử. Với field `final`, các write/atomic update modes không được hỗ trợ. Muốn đọc biến, read modes vẫn có thể được dùng nếu quyền lookup cho phép.

### 11.2. Khi field là `volatile`

Field method handles thực hiện thao tác bytecode tương đương đọc/ghi field. Nếu field khai báo `volatile`, thao tác field-access có những bảo đảm memory visibility tương ứng theo Java Memory Model. Tuy nhiên, nếu cần **chủ động chọn** các memory-ordering modes như `getAcquire`, `setRelease`, `getVolatile` hoặc update atomically, `VarHandle` diễn tả mục đích rõ ràng hơn.

Đừng suy rằng mọi field handle là atomic updater. Chỉ khi có primitive kết hợp hoặc đồng bộ rõ ràng mới có thể lập luận an toàn cho read-modify-write giữa nhiều thread.

## 12. Hợp đồng lỗi và cách chẩn đoán

Bốn factory được khai báo với hai checked exceptions quan trọng:

- `NoSuchFieldException`: lookup không tìm thấy field phù hợp với tên/kiểu đã yêu cầu.
- `IllegalAccessException`: access check không đạt hoặc dạng field không phù hợp với getter/setter được chọn; setter còn từ chối `final`.

Các tham số `null` trong lời gọi factory gây `NullPointerException` theo hợp đồng. Sau khi có handle, lỗi lúc **invoke** là vấn đề khác với lỗi lúc **lookup**.

| Triệu chứng | Giai đoạn | Nguyên nhân thường gặp | Kiểm tra / cách sửa |
| --- | --- | --- | --- |
| `NoSuchFieldException` | Lookup | Sai tên, sai kiểu `Class<?>`, không có field phù hợp | Kiểm tra field declaration và `type`, phân biệt `int.class`/`Integer.class` |
| `IllegalAccessException` khi `findGetter` | Lookup | Không đủ quyền hoặc dùng instance getter cho field static | Kiểm tra lookup class, JPMS và modifier `static` |
| `IllegalAccessException` khi `findSetter` | Lookup | Thiếu quyền, field static hoặc `final` | Dùng đúng factory; không tìm setter cho final |
| `IllegalAccessException` khi `findStaticGetter` | Lookup | Thiếu quyền hoặc field không static | Đổi sang `findGetter` nếu field instance |
| `IllegalAccessException` khi `findStaticSetter` | Lookup | Thiếu quyền, field không static hoặc `final` | Dùng đúng factory và chỉ ghi field mutable |
| `IllegalAccessException` từ `privateLookupIn` | Lookup | Không đủ lookup modes, thiếu readability/opens | Kiểm tra module graph, qualified opens và caller lookup |
| `WrongMethodTypeException` | Invoke | Call-site descriptor khác `handle.type()` khi `invokeExact` | Kiểm tra cả receiver, value và return type |
| `ClassCastException` | Invoke/adapter | `invoke` có thể thích ứng type nhưng actual object không ép kiểu được | Kiểm tra kiểu runtime của receiver/value |
| `NullPointerException` | Invoke | Receiver instance là null hoặc unboxing null khi adaptation | Truyền receiver hợp lệ |
| Lỗi khởi tạo class | Invoke static field | Static initialization thất bại ở lần sử dụng field | Kiểm tra static initializer, không mặc định lỗi do lookup |

**Không nên chỉ bắt `Exception` rồi bỏ qua.** Một framework phân giải field cần phân biệt sai tên/kiểu, sai quyền, sai loại static/instance và lỗi tại call site để trả thông báo chính xác cho người dùng.

### 12.1. Quy trình gỡ lỗi ngắn

1. Xác nhận field thật sự là **instance** hay **static**.
2. Xác nhận tên và kiểu **khai báo chính xác** của field (kể cả primitive/mảng).
3. Kiểm tra caller lookup có đủ quyền và package target có mở phù hợp không.
4. Với setter, xác nhận field không `final`.
5. Tạo handle và **in/so sánh `handle.type()`**.
6. Kiểm tra các đối số của `invokeExact` có đúng compile-time types không.
7. Nếu dùng `invoke`, xem adaptation có yêu cầu cast/boxing/unboxing nào có thể thất bại không.
8. Với static field, xem có side effects hoặc lỗi trong class initialization không.

## 13. Checklist thực hành với bốn field factories

Khi review code:

- [ ] Đã phân biệt field instance với static trước khi chọn factory.
- [ ] Tham số `type` là `Class<?>` đúng với kiểu field, không phải return type của một method.
- [ ] Đã dùng `MethodType` để xác nhận số lượng/thứ tự tham số và return type.
- [ ] Instance handle nhận receiver; static handle không nhận receiver.
- [ ] Getter trả về đúng kiểu field; setter trả `void`.
- [ ] Không tìm setter cho field `final`.
- [ ] `invokeExact` dùng đúng compile-time types, kể cả kiểu trả về tại call site.
- [ ] Access check đã được giải quyết bằng `Lookup` phù hợp, không tự động tin rằng `lookup()` truy cập mọi private member.
- [ ] Với cross-module private access, đã kiểm tra readability và `opens` theo hợp đồng `privateLookupIn`.
- [ ] Không phát tán private lookup/handle nhạy cảm cho code không tin cậy.
- [ ] Với atomic update hoặc memory ordering chuyên biệt, đã cân nhắc `VarHandle`.
- [ ] Đã kiểm chứng các negative cases: sai kind, sai type, final field, sai MethodType.
- [ ] Tránh coi `MethodHandle` là cách vượt qua Java access control hoặc JPMS.

## 14. Bài tập tự đánh giá

### Bài 1 — Suy ra chữ ký instance getter

Class:

~~~java
class Account {
    public long balance;
}
~~~

`lookup.findGetter(Account.class, "balance", long.class)` trả handle có `MethodType` nào?

**Đáp án:** `(Account)long`. Có một tham số receiver kiểu `Account`, trả primitive `long`.

### Bài 2 — Instance setter có trả lại giá trị không?

Với field `String title` trong `Book`, chữ ký handle từ `findSetter(Book.class, "title", String.class)` là gì?

**Đáp án:** `(Book, String)void`. Setter nhận receiver và giá trị mới, không trả giá trị được ghi.

### Bài 3 — Static getter có receiver không?

~~~java
class Flags {
    public static boolean enabled;
}
~~~

`findStaticGetter(Flags.class, "enabled", boolean.class)` có `MethodType` nào?

**Đáp án:** `()boolean`. Gọi `(boolean) handle.invokeExact()` mà không truyền instance hoặc `Flags.class`.

### Bài 4 — Static setter nhận bao nhiêu tham số?

`findStaticSetter(Flags.class, "enabled", boolean.class)` tạo handle kiểu gì?

**Đáp án:** `(boolean)void`. Chỉ truyền một boolean mới: `handle.invokeExact(true);`.

### Bài 5 — Lỗi sai static/instance

Có `public static int count`, nhưng code gọi `lookup.findGetter(C.class, "count", int.class)`. Kết quả lookup?

**Đáp án:** `IllegalAccessException` vì factory `findGetter` chỉ dành cho instance field. Dùng `findStaticGetter`.

### Bài 6 — Setter cho final

~~~java
class Config {
    final String name = "fixed";
    static final int MAX = 10;
}
~~~

Hai lệnh `findSetter(..., "name", String.class)` và `findStaticSetter(..., "MAX", int.class)` có tạo handle ghi được không?

**Đáp án:** Không. Hai factory setter từ chối field `final` bằng `IllegalAccessException`, kể cả khi lookup có thể đọc các field ấy.

### Bài 7 — Sai kiểu tại lookup

Field khai báo `int score`; code gọi `findGetter(C.class, "score", Integer.class)`. Có tự boxing để phân giải field không?

**Đáp án:** Không. `type` phải đúng với kiểu field `int.class`. Nếu không có field phù hợp với kiểu yêu cầu, lookup thất bại (`NoSuchFieldException`).

### Bài 8 — Sai kiểu tại invokeExact

Getter có kiểu `(Counter)int`. Code viết:

~~~java
Counter counter = new Counter();
Object result = getter.invokeExact(counter);
~~~

Vì sao có thể lỗi?

**Đáp án:** Call site yêu cầu return type `Object`, trong khi handle trả `int`. `invokeExact` đòi hỏi khớp tuyệt đối và ném `WrongMethodTypeException`. Sửa thành `int result = (int) getter.invokeExact(counter);`.

### Bài 9 — Field hiding

`Parent.size` và `Child.size` là hai field cùng tên. Handle đã tạo từ `Parent.class` có tự chuyển sang `Child.size` khi nhận receiver `Child` không?

**Đáp án:** Không. Nó tiếp tục đọc field được phân giải ở `Parent`. Field không có dynamic dispatch giống method override.

### Bài 10 — Thao tác atomic

Hai thread cùng dùng getter đọc `count`, tính `count+1`, rồi gọi setter. Có đảm bảo tổng tăng đúng hai đơn vị không?

**Đáp án:** Không. Đó là hai thao tác rời và có thể lost update. Hãy dùng `VarHandle.compareAndSet` với vòng retry hoặc một abstraction đồng bộ/atomic phù hợp.

### Bài 11 — Quyền cross-module

Module `demo.inspector` có `requires demo.data` nhưng `demo.data` không mở `demo.model`. `privateLookupIn(Model.class, MethodHandles.lookup())` từ inspector có bảo đảm hoạt động không?

**Đáp án:** Không. Khi khác module, `privateLookupIn` cần caller lookup có quyền phù hợp, module caller đọc được target, và target module **opens package cho caller**. Chỉ có `requires` hoặc `exports` không đủ cho deep private access.

### Bài 12 — Class initialization của static field

Nếu class chứa static initializer, chỉ tạo `findStaticGetter` đã đồng nghĩa giá trị field được đọc chưa?

**Đáp án:** Chưa. Lookup tạo handle; lúc gọi getter, lớp khai báo field sẽ được khởi tạo nếu cần rồi mới truy cập field. Đừng nhầm thời điểm lookup với thời điểm invoke.

## Tổng kết

- `findGetter`, `findSetter`, `findStaticGetter`, `findStaticSetter` là bốn public factory methods trên `MethodHandles.Lookup` để đọc/ghi field.
- Chữ ký handle lần lượt là **`(C)T`**, **`(C, T)void`**, **`()T`**, **`(T)void`**; `C` là receiver type và `T` là field type.
- Tham số `type` của factory là `Class<?>` biểu diễn **kiểu field**; dùng `handle.type()` để xem `MethodType` đã tạo.
- `invokeExact` cần kiểu đối số và return type của call site khớp tuyệt đối; `invoke` có thể thực hiện adaptation hợp lệ.
- Setter factories từ chối `final`; sai static/instance hoặc thiếu quyền dẫn đến `IllegalAccessException`. Sai field name/type gây `NoSuchFieldException`.
- Lookup gắn với quyền caller. `publicLookup()` bị hạn chế; `privateLookupIn()` chỉ hoạt động khi đáp ứng điều kiện truy cập và module policy.
- Truy cập field không có dynamic dispatch như method override; field hiding tạo các member độc lập.
- Static field handle khởi tạo lớp khai báo lúc invoke nếu cần, không mặc nhiên tại lookup.
- `MethodHandle` getter/setter không tự tạo atomic read-modify-write. Khi cần access modes như `getVolatile` hoặc `compareAndSet`, cân nhắc `VarHandle`.
- Kiến thức này vẫn hữu ích trên JDK hiện đại, không cần dựa vào internals hoặc kỹ thuật sửa `final` lỗi thời.

## Nguồn tham khảo chính thức

1. [Oracle — MethodHandles.Lookup, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): các factory `findGetter`, `findSetter`, `findStaticGetter`, `findStaticSetter`, return handle types, lỗi access và `final`.
2. [Oracle — MethodHandle, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandle.html): `type()`, `invokeExact()`, `invoke()`, signature polymorphism và `WrongMethodTypeException`.
3. [Oracle — MethodHandles, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.html): `lookup()`, `publicLookup()` và `privateLookupIn()`, quyền caller và yêu cầu JPMS.
4. [Oracle — MethodType, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodType.html): mô hình hóa kiểu trả về và danh sách tham số của MethodHandle.
5. [Oracle — VarHandle, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/VarHandle.html): variable/coordinate types, memory-ordering modes, `compareAndSet` và hạn chế trên field `final`.
6. [OpenJDK — JEP 416: Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): triển khai Core Reflection được tái cấu trúc trong Java 18; tránh phụ thuộc chi tiết triển khai.
