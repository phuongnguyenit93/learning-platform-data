# Tham chiếu tới Class, instance và MethodHandle trong vòng đời hidden class (Java 15)

> **Mục tiêu:** Nắm vững cách các tham chiếu tới `Class<?>`, instance, `MethodHandles.Lookup` và `MethodHandle` ảnh hưởng đến **vòng đời (liveness)** của hidden class; phân biệt hidden class mặc định có thể unload độc lập với class loader và hidden class dùng `ClassOption.STRONG`; thiết kế cache không vô tình giữ class quá lâu. Kiến thức dựa trên **JEP 371 và API ổn định từ Java 15 vẫn còn được dùng trong Java hiện đại**, ví dụ chạy với **Java 17+**, không dùng preview hay cơ chế legacy.

## 1. Vì sao hidden class có vòng đời khác class thông thường?

Hidden class được chuẩn hóa trong **JDK 15** qua [JEP 371](https://openjdk.org/jeps/371). Framework có thể dùng `MethodHandles.Lookup.defineHiddenClass(...)` để định nghĩa một implementation từ bytecode mà không tạo ra một class mang tên nhị phân thông thường để tìm bằng `Class.forName`.

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodHandles.Lookup hiddenLookup =
        lookup.defineHiddenClass(classBytes, true);

Class<?> hiddenType = hiddenLookup.lookupClass();
~~~

Đây là **đoạn mã đặt trong một phương thức**; `classBytes` phải là một class file hợp lệ có package phù hợp với lookup class, và lookup cần **full privilege access**. Chương trình hoàn chỉnh nằm ở mục 6.

Một class có tên bình thường thường gắn chặt vòng đời với **defining class loader**: theo mô hình class unloading của JVM, class đó có thể unload khi defining loader trở nên không còn reachable. Hidden class có lựa chọn khác:

- **Mặc định (không truyền `STRONG`):** hidden class **có thể được unload** ngay cả khi defining class loader của nó **vẫn reachable**, miễn các ràng buộc về khả năng truy cập/liveness không còn giữ class lại. Điều này có ích khi sinh nhiều lớp ngắn hạn.
- **Có `ClassOption.STRONG`:** hidden class có **strong relationship với defining class loader** tương tự class thường. Nó có thể được unload **khi và chỉ khi** defining loader không còn reachable và có thể được GC thu hồi. Nếu loader sống suốt vòng đời ứng dụng, rất nhiều hidden classes `STRONG` cũng có thể tồn tại rất lâu.

**“Có thể unload” không có nghĩa “sẽ unload ngay”.** Quyết định và thời điểm thực tế thuộc JVM và garbage collector, không phải lời gọi `System.gc()` hay việc gán một biến thành `null`. API Java không cung cấp lệnh bảo đảm unload một hidden class ngay lập tức.

## 2. Hai trục cần phân biệt: class identity và liveness

Khi định nghĩa hidden class, nhận được một `Class<?>` thực sự và có thể tạo instance, phản chiếu thông tin class hoặc method handles:

~~~java
MethodHandles.Lookup hiddenLookup =
        MethodHandles.lookup().defineHiddenClass(bytes, true);
Class<?> type = hiddenLookup.lookupClass();

System.out.println(type.isHidden()); // true
~~~

**Class identity:** Mỗi lần `defineHiddenClass` thành công với cùng `byte[]` có thể tạo **một hidden class khác nhau**. Giống nhau về nội dung class file không có nghĩa là cùng `Class<?>`. Hai class có thể do cùng class loader định nghĩa nhưng vẫn khác danh tính.

**Liveness:** Một hidden class **đang reachable từ các tham chiếu mạnh có liên quan** không thể bị thu hồi như thể nó đã hoàn toàn không còn được sử dụng. Bạn cần phân biệt việc code còn *biết tới* nó qua object/handle/cache với việc còn *dùng* đường dẫn tìm tên class.

Thí dụ:

~~~java
Class<?> first = firstLookup.lookupClass();
Class<?> second = secondLookup.lookupClass();

System.out.println(first == second); // thường là false nếu định nghĩa 2 lần
~~~

Đây là mã **minh họa trong phương thức**, giả định `firstLookup` và `secondLookup` là kết quả của **hai lần gọi `defineHiddenClass` độc lập**. Không được suy diễn rằng chỉ cần cùng class file bytes thì hai class tương đương về type identity: instance của hidden class lần thứ nhất **không** phải instance của hidden class lần thứ hai.

## 3. Những tham chiếu giữ hidden class reachable

| Tham chiếu mà ứng dụng giữ | Quan hệ tới hidden class | Hệ quả khi còn reachable |
| --- | --- | --- |
| `Class<?> hiddenType` | `Class` object đại diện trực tiếp cho hidden class | Là **strong reference trực tiếp**; có thể ngăn class unload |
| Instance `Object obj` của hidden class | Instance có runtime class tương ứng | Giữ instance còn sống đồng nghĩa JVM phải bảo toàn class cần thiết để thao tác với nó |
| `MethodHandles.Lookup hiddenLookup` | Lookup trả về bởi `defineHiddenClass` lưu ngữ cảnh **lookup class** | Giữ lookup trong cache có thể giữ hidden class reachable |
| `MethodHandle` tới constructor/method/field của hidden class | Handle trực tiếp và `MethodType` có thể chứa tham chiếu tới class thành viên và kiểu receiver/return | Cache handle có thể giữ class sống; không nên mặc định nó “chỉ là con trỏ code yếu” |
| `MethodHandle` đã `bindTo(instance)` | Handle gắn sẵn receiver là **instance** | Giữ bound handle thường giữ **instance**, qua đó giữ class |
| `WeakReference<Class<?>>` | Chỉ là tham chiếu **yếu** tới `Class` | **Không tự ngăn** đối tượng `Class` bị GC thu hồi |
| `WeakReference<Object>` tới instance | Tham chiếu yếu tới instance | Không tự giữ instance còn sống |
| `byte[]` chứa class file đầu vào | Dữ liệu bytecode trước khi JVM định nghĩa class | **Không phải** tham chiếu tới một hidden class đã được định nghĩa; có thể dùng bytes để định nghĩa lớp mới |

Chú ý rằng Java GC xét **toàn bộ đồ thị reachable**, không phải chỉ một biến mà lập trình viên nhìn thấy. Bạn xóa `Class<?>` trong một collection nhưng vẫn giữ `MethodHandle`, `Lookup`, instance hoặc wrapper phản chiếu ở collection khác thì class vẫn có thể được giữ lại.

**Không phải mọi MethodHandle được bảo đảm có cùng cấu trúc nội bộ.** Điều có ý nghĩa với thiết kế là: handle tới hidden method/constructor có liên hệ với class và `MethodType`; **không dựa vào chi tiết GC nội bộ để coi cache handle là weak reference**. Nếu ứng dụng giữ một handle để gọi hành vi của hidden class trong tương lai, class phải còn đủ khả năng sử dụng tại thời điểm đó.

## 4. Tham chiếu mạnh và yếu không đồng nghĩa với option `STRONG`

Tên gọi có thể gây nhầm:

- **Strong reference (GC):** quan hệ từ một object đang reachable đến object khác, ví dụ trường `Map<String, Class<?>>` lưu value là `Class`.
- **WeakReference:** wrapper `java.lang.ref.WeakReference<T>`; nếu đối tượng đích không còn strongly reachable, referent có thể được GC thu hồi.
- **`Lookup.ClassOption.STRONG`:** **chính sách vòng đời hidden class đối với defining class loader**, được quyết định **lúc định nghĩa class**. Nó **không** biến mọi field hoặc mọi local reference thành strong reference, cũng không có phương thức tắt `STRONG` sau đó.

Một hidden class **không `STRONG`** vẫn có thể sống rất lâu nếu một static cache giữ `Class`, instance, lookup hoặc handle của nó. Ngược lại, bỏ toàn bộ các tham chiếu ứng dụng tới hidden class **`STRONG`** không cho phép JVM thu hồi nó độc lập khi defining loader còn sống.

Ví dụ chọn policy:

~~~java
MethodHandles.Lookup shortLived =
        lookup.defineHiddenClass(bytes, true);

MethodHandles.Lookup loaderBound =
        lookup.defineHiddenClass(
                bytes,
                true,
                MethodHandles.Lookup.ClassOption.STRONG);
~~~

Hai lệnh đều định nghĩa hidden classes. Chúng khác **chính sách unloading**, không khác quy tắc package hay quyền lookup. `STRONG` không làm class có tên nhị phân thường, không khiến `Class.forName` tìm ra nó và không tự cấp quyền truy cập private.

**Thiết kế thực tế:** Nếu framework tạo vô số implementation tạm thời, chế độ mặc định thường phù hợp với mục đích đó. Nếu hidden class phải sống cùng một class/loader ổn định vì cấu trúc liên kết hoặc thiết kế runtime, cân nhắc `STRONG` **sau khi** hiểu tác động tới footprint Metaspace. Không chọn chỉ vì “STRONG chắc nhanh hơn”.

## 5. Cách MethodHandle liên quan đến Class và instance

`java.lang.invoke.MethodHandle` là object biểu diễn thao tác có thể gọi; từ một lookup trên hidden class, ta có thể tạo handles cho:

~~~java
Class<?> type = hiddenLookup.lookupClass();

MethodHandle ctor = hiddenLookup.findConstructor(
        type, MethodType.methodType(void.class, String.class));

MethodHandle greet = hiddenLookup.findVirtual(
        type, "greet",
        MethodType.methodType(String.class, String.class));

MethodHandle twice = hiddenLookup.findStatic(
        type, "twice", MethodType.methodType(int.class, int.class));
~~~

Giả sử class file đầu vào khai báo constructor nhận `String`, instance method `String greet(String)` và static method `int twice(int)`. Khi đó:

- `ctor.type().returnType() == type`: method handle constructor có **return type là hidden class**.
- `greet.type().parameterType(0) == type`: handle cho virtual method có **receiver type là hidden class** ở tham số đầu.
- `twice.type()` chứa tham số và kết quả kiểu `int`, không có receiver; dù chữ ký hiển thị không chứa hidden type, handle vẫn gắn với **member** thuộc hidden class.
- `greet.bindTo(instance)` tạo handle **gắn sẵn receiver**, vì vậy handle này có thể giữ instance. Sau bind, số tham số của handle giảm đi một.

Phân biệt hai cách gọi:

~~~java
String a = (String) greet.invoke(instance, "Java");

MethodHandle bound = greet.bindTo(instance);
String b = (String) bound.invoke("Java");
~~~

Cả hai có thể trả cùng kết quả. Với **`invoke`**, JVM được phép thực hiện một số chuyển đổi kiểu `MethodHandle` hợp lệ; `invokeExact` yêu cầu descriptor ở call site khớp chính xác. Vì hidden type không có tên source thông thường để đặt vào một biểu thức Java rõ kiểu, ví dụ bài học dùng `invoke` cho dễ chạy và giải thích.

**Đừng nghĩ `bindTo` làm copy dữ liệu của receiver.** Nó gắn **tham chiếu receiver**, nên nếu giữ bound handle trong cache lâu dài, instance có thể còn sống lâu theo cache.

## 6. Ví dụ đầy đủ: hai hidden classes và những đường tham chiếu

Mục này sử dụng **hai source files** cùng package `demo.hiddenlife`. `javac` tạo class file bình thường từ `Payload`; chương trình `HiddenLifeDemo` đọc bytes và định nghĩa thành hai **hidden class độc lập** — một theo chế độ mặc định, một với `STRONG`.

Cấu trúc:

~~~text
demo/
  hiddenlife/
    Payload.java
    HiddenLifeDemo.java
~~~

### 6.1. `demo/hiddenlife/Payload.java`

~~~java
package demo.hiddenlife;

public class Payload {
    private final String prefix;

    public Payload(String prefix) {
        this.prefix = prefix;
    }

    public String greet(String name) {
        return prefix + name;
    }

    public static int twice(int number) {
        return number * 2;
    }
}
~~~

### 6.2. `demo/hiddenlife/HiddenLifeDemo.java`

~~~java
package demo.hiddenlife;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.ref.WeakReference;
import java.nio.file.Files;
import java.nio.file.Path;

public class HiddenLifeDemo {
    record Handles(
            Class<?> type,
            Object instance,
            MethodHandles.Lookup hiddenLookup,
            MethodHandle constructor,
            MethodHandle greet,
            MethodHandle boundGreet,
            MethodHandle twice) {}

    private static Handles define(byte[] bytes, boolean strong) throws Throwable {
        MethodHandles.Lookup original = MethodHandles.lookup();
        MethodHandles.Lookup hiddenLookup = strong
                ? original.defineHiddenClass(bytes, true,
                    MethodHandles.Lookup.ClassOption.STRONG)
                : original.defineHiddenClass(bytes, true);
        Class<?> type = hiddenLookup.lookupClass();
        MethodHandle constructor = hiddenLookup.findConstructor(
                type, MethodType.methodType(void.class, String.class));
        Object instance = (Object) constructor.invoke("Hi, ");
        MethodHandle greet = hiddenLookup.findVirtual(
                type, "greet", MethodType.methodType(String.class, String.class));
        MethodHandle boundGreet = greet.bindTo(instance);
        MethodHandle twice = hiddenLookup.findStatic(
                type, "twice", MethodType.methodType(int.class, int.class));
        return new Handles(type, instance, hiddenLookup, constructor,
                greet, boundGreet, twice);
    }

    public static void main(String[] args) throws Throwable {
        byte[] bytes = Files.readAllBytes(
                Path.of("out/demo/hiddenlife/Payload.class"));
        Handles standard = define(bytes, false);
        Handles strong = define(bytes, true);
        System.out.println("defaultHidden=" + standard.type().isHidden());
        System.out.println("strongHidden=" + strong.type().isHidden());
        System.out.println("distinctIdentity=" + (standard.type() != strong.type()));
        System.out.println("sameLoader=" + (standard.type().getClassLoader()
                == strong.type().getClassLoader()));
        System.out.println("crossInstance=" + strong.type().isInstance(
                standard.instance()));
        System.out.println("instanceClassMatches="
                + (standard.instance().getClass() == standard.type()));
        System.out.println("constructorReturnsHidden="
                + (standard.constructor().type().returnType() == standard.type()));
        System.out.println("virtualReceiverHidden="
                + (standard.greet().type().parameterType(0) == standard.type()));
        System.out.println("boundArity=" + standard.boundGreet().type()
                .parameterCount());
        System.out.println("lookupTargetsHidden="
                + (standard.hiddenLookup().lookupClass() == standard.type()));
        System.out.println("directCall="
                + (String) standard.greet().invoke(standard.instance(), "Java"));
        System.out.println("boundCall="
                + (String) standard.boundGreet().invoke("team"));
        System.out.println("staticCall=" + (int) standard.twice().invoke(21));

        WeakReference<Class<?>> classObserver = new WeakReference<>(standard.type());
        WeakReference<Object> objectObserver = new WeakReference<>(standard.instance());
        System.out.println("classWhileHeld="
                + (classObserver.get() == standard.type()));
        System.out.println("instanceWhileHeld="
                + (objectObserver.get() == standard.instance()));
        try {
            Class.forName(standard.type().getName());
            System.out.println("byName=UNEXPECTED");
        } catch (ClassNotFoundException expected) {
            System.out.println("byName=ClassNotFoundException");
        }
    }
}
~~~

**Vì sao cần `record Handles`?** Nó gom các tham chiếu để quan sát được cùng lúc. `record` đã chính thức từ Java 16, nên chương trình sử dụng `--release 17`. Khi object `Handles` vẫn reachable, các field của nó là **strong references** đến `Class`, instance, lookup và handles; thí nghiệm này **cố ý không làm hidden class unload**.

### 6.3. Lệnh biên dịch và chạy

Đứng tại thư mục chứa `demo`:

~~~bash
javac --release 17 -encoding UTF-8 -d out demo/hiddenlife/Payload.java demo/hiddenlife/HiddenLifeDemo.java
java -cp out demo.hiddenlife.HiddenLifeDemo
~~~

Phần `-d out` tạo `out/demo/hiddenlife/Payload.class`; chương trình đọc file này bằng đường dẫn tương đối. Không cần `--enable-preview`, `--add-opens` hoặc API `jdk.internal`.

**Stdout chính xác đã được chạy kiểm chứng:**

~~~text
defaultHidden=true
strongHidden=true
distinctIdentity=true
sameLoader=true
crossInstance=false
instanceClassMatches=true
constructorReturnsHidden=true
virtualReceiverHidden=true
boundArity=1
lookupTargetsHidden=true
directCall=Hi, Java
boundCall=Hi, team
staticCall=42
classWhileHeld=true
instanceWhileHeld=true
byName=ClassNotFoundException
~~~

### 6.4. Diễn giải kết quả theo vòng đời

1. `defaultHidden=true` và `strongHidden=true`: cả hai đều là hidden classes; `STRONG` chỉ thay đổi quan hệ tới defining loader.
2. `distinctIdentity=true`: hai lần định nghĩa từ **cùng bytes** tạo ra **hai `Class<?>` khác nhau**.
3. `sameLoader=true`: dùng cùng loader không làm hai class trở thành cùng danh tính.
4. `crossInstance=false`: instance của hidden class thứ nhất không phải instance của hidden class thứ hai.
5. `instanceClassMatches=true`: instance có runtime class chính là `Class<?>` nhận từ lookup lần thứ nhất.
6. `constructorReturnsHidden=true`: return type của constructor method handle chứa hidden class.
7. `virtualReceiverHidden=true`: receiver của virtual method handle cũng là hidden class. `boundArity=1` vì receiver đã được gắn vào handle.
8. `lookupTargetsHidden=true`: lookup trả về hướng tới chính hidden class.
9. `directCall=Hi, Java`, `boundCall=Hi, team`, `staticCall=42`: method handles còn có thể sử dụng class khi các tham chiếu vẫn sống.
10. `classWhileHeld=true` và `instanceWhileHeld=true`: weak references **quan sát thấy** hai object hiện vẫn có strong references trong `standard`. **Không có test GC**, và không nên xem hai dòng này là bằng chứng về thời điểm unload.
11. `byName=ClassNotFoundException`: hidden class không thể được tìm lại theo tên runtime bằng cơ chế `Class.forName` thông thường.

**Điều chương trình không kiểm chứng:** Nó **không** khẳng định class mặc định đã unload, không chứng minh `STRONG` luôn tồn tại vô hạn và không đo tốc độ GC. Các điều đó là quy tắc/lifecycle có điều kiện, không phải stdout ổn định có thể lấy từ một lần chạy.

## 7. Sơ đồ reachability để hiểu vì sao cache có thể giữ class

Giả sử ứng dụng giữ một `MethodHandle` đã `bindTo(instance)` trong cache:

~~~text
GC root (static field, cache hoặc stack frame còn sống)
    |
    v
Map / object giữ MethodHandle
    |
    v
Bound MethodHandle
    |
    v
Instance của hidden class
    |
    v
Runtime Class / metadata cần cho instance
~~~

Nếu cache giữ trực tiếp `Class<?>` thì đường đi ngắn hơn:

~~~text
GC root -> Cache -> Class<?> của hidden class
~~~

Một cache lưu `Lookup` hoặc unbound method handle cũng có thể giữ class/member liên quan; **không được suy luận** rằng đổi `Class<?>` thành `MethodHandle` sẽ tự giải phóng hidden class.

Khi **không còn strong references** từ các GC roots theo những đường này, một hidden class mặc định **có thể** trở thành ứng viên unloading ngay cả khi loader của nó còn sống. Tuy nhiên, các tham chiếu khác như callback, task đang chạy, static cache, reflection object, method type hoặc dữ liệu của framework vẫn có thể giữ class lại.

**Đừng chỉ gán một biến thành `null` rồi cho rằng class đã được giải phóng.** Biến local không phải hình ảnh đầy đủ của đồ thị tham chiếu, và JVM không có nghĩa vụ thu hồi ngay.

### Ví dụ cache cần giới hạn vòng đời

~~~java
import java.lang.invoke.MethodHandle;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

final class GeneratedCodeCache {
    private final Map<String, MethodHandle> methods =
            new ConcurrentHashMap<>();

    void put(String key, MethodHandle handle) {
        methods.put(key, handle);
    }

    void evict(String key) {
        methods.remove(key);
    }
}
~~~

Đây là **một class minh họa**, không phải chương trình độc lập; nó có thể nằm trong hệ thống không chỉ dùng hidden classes. Khi cache lưu method handles tới các lớp sinh động, entry còn giữ handle có thể làm class/instance liên quan tiếp tục reachable. `evict` chỉ **gỡ một nguồn tham chiếu**; nếu nơi khác còn giữ handle, instance hay lookup, class vẫn có thể sống.

Nếu cache phải có vòng đời ngắn, cân nhắc giới hạn số entries, thời hạn sống, eviction có chủ đích và ranh giới ownership. Đừng chỉ thêm `WeakReference` vào một vị trí rồi giả định mọi đường tham chiếu khác biến mất.

## 8. `WeakReference` để quan sát, không phải “lệnh unload”

Java có `java.lang.ref.WeakReference<T>`. Ví dụ:

~~~java
WeakReference<Class<?>> observer =
        new WeakReference<>(hiddenType);
~~~

`observer` **không phải strong reference** tới `hiddenType`. Nếu không còn strong roots khác và JVM thu hồi referent, `observer.get()` có thể trả `null`. Nhưng điều này **không** xảy ra theo deadline cố định.

Một đoạn diagnostic (đặt trong phương thức) có thể dùng:

~~~java
WeakReference<Class<?>> ref = new WeakReference<>(type);

// Ở các bước khác của hệ thống: bỏ mọi strong reference liên quan,
// bao gồm Class, instance, Lookup, MethodHandle, cache và tác vụ đang chạy.
// Không thể chứng minh việc đã bỏ mọi root chỉ bằng một dòng type = null.

Class<?> observed = ref.get();
if (observed == null) {
    System.out.println("Class object no longer available through this weak ref");
} else {
    System.out.println("Class object still observable");
}
~~~

Đây là **mã minh họa**, không phải script kiểm thử có stdout cố định; `type` được giả định là `Class<?>` đã có. Đặc biệt trong một method đang còn sử dụng `type`, việc gọi `ref.get()` có thể thấy class vẫn reachable. Không nên nhúng đoạn này vào unit test với assert rằng sau một vòng `System.gc()` chắc chắn phải trả `null`.

**Vì sao không nên test `System.gc()`?**

- Đây chỉ là **yêu cầu gợi ý** GC; JVM có thể không thu gom ngay hoặc có thể bỏ qua.
- Điều kiện unload của một class có thể chưa thỏa do các references ẩn/khác vẫn reachable.
- Runtime có thể cần nhiều pha GC/class unloading; thời gian không ổn định theo JDK, GC và workload.
- Nếu test dùng `WeakReference.get() == null` với timeout ngắn, test dễ flaky mà không phản ánh lỗi logic.

Với kiểm thử unit, hãy kiểm tra **identity, behavior và ownership cleanup** một cách xác định. Để đánh giá khả năng unload ngoài môi trường chạy thật, dùng profiler/JFR/JVM diagnostics thích hợp và quan sát trong tải thực tế, thay vì phụ thuộc một lần gọi GC.

## 9. `STRONG` thay đổi điều gì và không thay đổi điều gì?

Tùy chọn:

~~~java
MethodHandles.Lookup strongLookup = lookup.defineHiddenClass(
        bytes,
        true,
        MethodHandles.Lookup.ClassOption.STRONG);
~~~

Theo Javadoc, một hidden class có `STRONG` có **strong relationship với class loader được đánh dấu là defining loader** tương tự class bình thường. Điều này có nghĩa:

- Nếu loader còn reachable, hidden class `STRONG` không được unload độc lập như hidden class mặc định.
- Nếu loader không còn reachable và GC có thể thu hồi nó, class mới có thể unload theo các điều kiện của JVM.
- Lựa chọn này được đặt **lúc class được định nghĩa**; không có thao tác chuyển một hidden class mặc định sang `STRONG` sau đó.
- Dùng `STRONG` cho hàng nghìn/hàng triệu class sinh động có thể khiến metadata/class footprint tăng giống việc tạo nhiều class thường với một loader sống lâu.

`STRONG` **không**:

- Biến hidden class thành class tra cứu được qua `Class.forName`.
- Tự giữ một **instance** nào còn sống nếu không có reference tới instance đó.
- Đồng nghĩa với `NESTMATE`; `NESTMATE` là quan hệ quyền truy cập **nest/private members**, không phải chính sách unloading.
- Bỏ quy tắc **bytes cùng package**, **full privilege lookup** hoặc bytecode hợp lệ.
- Chứng minh class luôn ở trong bộ nhớ đến hết tiến trình khi class loader có vòng đời ngắn và không còn reachable.

**Chọn `STRONG` có chủ đích**, không theo tên gọi hấp dẫn. Nếu framework muốn hidden class độc lập với việc loader ứng dụng sống lâu, default behavior chính là một trong các lý do hidden classes được thiết kế.

## 10. Giữ `Class<?>` và `MethodHandle` để gọi lại sau này

Hidden class không có tên nhị phân thông thường; đoạn sau sẽ không làm cách lookup lại lâu dài hoạt động:

~~~java
String runtimeName = hiddenType.getName();

// Với hidden class, đây không phải binary name nạp bình thường.
Class.forName(runtimeName); // ClassNotFoundException
~~~

Vì thế ứng dụng muốn gọi code về sau phải giữ một **capability tham chiếu thực tế**: `Class<?>`, `Lookup`, instance, MethodHandle hoặc wrapper cấu hình phù hợp.

| Nhu cầu | Nên giữ | Điều cần quản lý |
| --- | --- | --- |
| Tạo nhiều instances trong một khoảng thời gian | Constructor `MethodHandle` hoặc `Class<?>` + quyền tạo thích hợp | Retention của hidden class qua handle/class; đóng cache khi hết nhu cầu |
| Gọi một phương thức trên instances khác nhau | Unbound instance `MethodHandle` | Handle có liên kết với method và receiver type |
| Tạo callback gắn với một instance cụ thể | Bound `MethodHandle` | Bound receiver được giữ sống cùng handle |
| Khám phá và tạo handles mới | `MethodHandles.Lookup` trả về | Lookup là capability có quyền; chỉ trao cho code đáng tin |
| Kiểm tra kiểu ở runtime | `Class<?>` trả về | `Class.isInstance()` đúng cho **class identity cụ thể** |
| Không còn dùng code được sinh | Gỡ các cache/listener/callback tham chiếu | Không thể bảo đảm GC tức thì; chỉ tạo điều kiện unload |

**Không dùng tên runtime hidden class làm khóa tái dựng**. Tên có thể chứa hậu tố đặc biệt của JVM, không phải tên nạp bình thường. Nếu framework cần cache lookup logic, dùng ID nghiệp vụ riêng cho metadata và giữ trực tiếp capability trong thời gian thực sự cần; khi phát hành/evict, tránh giữ thêm references không cần thiết.

Cũng cần nhớ rằng **hai hidden classes từ cùng bytes không cùng kiểu**: `someOtherHiddenClass.isInstance(instanceOfFirst)` có thể `false`, ngay cả khi interfaces/methods có vẻ giống nhau. Khi cần đa hình, cân nhắc interface có tên bình thường làm kiểu chung được thiết kế từ trước.

## 11. Ví dụ vòng đời framework: tránh giữ vô hạn các callbacks

Một hệ thống sinh class cho callback hoặc adapter có thể đi qua các bước:

~~~text
1. Sinh bytecode trong package được ủy quyền
2. defineHiddenClass(bytes, initialize, options)
3. Tạo MethodHandle / instance cần dùng
4. Gắn vào task, listener hoặc cache có vòng đời cụ thể
5. Thực thi; trả kết quả theo contract
6. Gỡ đăng ký listener, hủy cache entry, ngắt tham chiếu task
7. Để JVM tự quyết định khi nào GC/unload thực sự xảy ra
~~~

Trong bước 4, không nên giữ một `MethodHandle` bound tới instance trong static field mãi mãi nếu callback chỉ phục vụ một request. Ngược lại, nếu một callback phải sống trong suốt vòng đời subsystem, **đừng** sử dụng weak reference không kiểm soát khiến callback biến mất trước khi hoàn thành nghĩa vụ.

**Ownership rõ ràng quan trọng hơn “ép GC”:** Hãy ghi rõ ai được giữ lookup, ai sở hữu cache, ai được phép evict, và thời điểm nào một job đang chạy phải kết thúc. Dùng thực thể quản lý tài nguyên của ứng dụng (scope/request/session/plugin lifecycle) để điều khiển các strong references; JVM xử lý GC còn lại.

**Không coi class unloading là cơ chế đóng tài nguyên nghiệp vụ.** Nếu class/instance mở file, socket, native memory hoặc tài nguyên khác, hãy đóng chúng theo `AutoCloseable`/try-with-resources hoặc lifecycle có chủ đích. Không chờ hidden class unload để đảm bảo file descriptor hay connection được giải phóng.

## 12. Vấn đề bảo mật và khả năng truy cập

Đối tượng `Lookup` không chỉ là tham chiếu ảnh hưởng tới liveness mà còn là **capability kiểm soát quyền method handles**. `defineHiddenClass` yêu cầu full privilege lookup và class bytes cùng package. Lưu lookup trong một object mà plugin bên ngoài có thể truy cập không chỉ kéo dài vòng đời class, mà còn có thể làm lộ quyền truy cập mà framework không định trao.

Cách xử lý:

- Giữ lookup trong thành phần đáng tin cậy; chỉ công khai **MethodHandle đã chọn** hoặc interface nghiệp vụ khi thật sự cần.
- Không nhận bytecode không đáng tin rồi định nghĩa nó dưới quyền của ứng dụng với kỳ vọng hidden class tự sandbox. Hidden class **không phải security boundary**.
- Không dùng `ClassOption.NESTMATE` nếu không cần quyền truy cập private qua nest. Tùy chọn này **không liên quan** đến việc có unload nhanh hơn.
- Không đổi `ClassLoader` hoặc module chỉ để ép lifetime; thiết kế loading/unloading phải phục vụ đúng nhu cầu và tôn trọng quy tắc package/module.

**Một điểm ít thấy:** `MethodHandle` có thể được gọi về sau mà không lặp lại quá trình access checking giống reflection mỗi lần. Do đó nếu ứng dụng chia sẻ handle tới member nhạy cảm, nó đang trao một capability gọi hành vi; cần bảo vệ handle theo kiến trúc như bảo vệ lookup.

## 13. Những lỗi thường gặp

1. **“Hidden class sẽ biến mất ngay khi hàm tạo class kết thúc.”** Sai: nếu còn `Class`, instance, lookup, handle hoặc reference từ cache, class vẫn có thể reachable.
2. **“Class loader còn sống thì hidden class mặc định luôn sống.”** Sai: mặc định hidden class **có thể unload độc lập** với loader.
3. **“`STRONG` nghĩa là object instance không bao giờ được GC.”** Sai: `STRONG` ràng buộc **class với loader**, không tự giữ mọi instance.
4. **“Bỏ `Class<?>` là đủ.”** Sai: method handles, instance, `Lookup` hoặc reflection wrapper vẫn có thể giữ class.
5. **“Chỉ lưu bound MethodHandle thì instance chắc chắn được giải phóng.”** Sai: `bindTo(instance)` giữ receiver trong handle.
6. **“Unbound handle không có tham chiếu tới class nếu descriptor chỉ có primitive.”** Không nên suy đoán nội bộ: handle vẫn đại diện member của class. Cache handle có thể duy trì reachability.
7. **“`WeakReference<Class<?>>` sẽ xóa class ngay.”** Sai: weak ref không quyết định GC; nó chỉ không giữ referent theo strong reference.
8. **“`System.gc()` luôn làm class unload ngay và test có thể assert điều đó.”** Sai: nondeterministic; unit test như vậy dễ flaky.
9. **“Hai lần định nghĩa cùng bytes sinh cùng `Class<?>`.”** Sai: identity là của lần định nghĩa mới; chúng là hai hidden classes khác nhau.
10. **“Đã có `Class.getName()` thì `Class.forName` tìm được.”** Sai: hidden class không có binary name bình thường để tra cứu.
11. **“`STRONG` giúp `Class.forName` hoặc `NESTMATE` tự hoạt động.”** Sai: loading policy, naming và nest access là cơ chế độc lập.
12. **“Dựa vào class unloading để đóng file/socket.”** Sai: tài nguyên ứng dụng phải được đóng chủ động.
13. **“Giữ hết mọi generated handles trong static map để tăng tốc, không có giá phải trả.”** Sai: có thể giữ class metadata, objects và bytecode/runtime structures lâu hơn cần thiết.
14. **“Unloading được thấy trong một GC run chứng minh mọi JDK/GC đều cùng hành vi.”** Sai: quy tắc có điều kiện, phụ thuộc reachability và cấu hình runtime.

## 14. Kiểm thử và theo dõi phù hợp

**Unit test xác định được** nên kiểm tra:

- Hai class được định nghĩa từ cùng bytes có `Class<?>` identity khác nhau.
- `isHidden()` là `true` với cả default và `STRONG`.
- Instance được tạo bằng constructor handle có `getClass() == hiddenType`.
- `findVirtual` và `findStatic` gọi được hành vi với input/output mong đợi.
- `constructor.type().returnType()`, receiver type của unbound method handle và `lookup.lookupClass()` tham chiếu đúng hidden class.
- Bound method handle có ít tham số hơn và vẫn gọi được instance.
- `Class.forName(hiddenType.getName())` thất bại theo đặc tính hidden class.
- Mã cleanup thực sự **gỡ các cache/listener/registry entries** mà hệ thống tự tạo.

**Integration/performance test**, nếu tính năng unload là yêu cầu quan trọng, có thể quan sát JFR/profiler hỗ trợ sự kiện class unloading và xu hướng Metaspace sau nhiều vòng tạo/dùng/bỏ generated classes. Chạy với workload đại diện và định nghĩa ngưỡng phù hợp, không yêu cầu “GC trong 1 giây” như một điều kiện bắt buộc của API.

Ví dụ bài kiểm thử **không nên** viết:

~~~java
// Không dùng đây làm unit test quyết định đúng/sai:
Class<?> oldType = hiddenLookup.lookupClass();
WeakReference<Class<?>> ref = new WeakReference<>(oldType);
oldType = null;
hiddenLookup = null;
System.gc();
// assert ref.get() == null;  // Sai: GC/unload không được đảm bảo.
~~~

Đây là **mã minh họa chống mẫu kiểm thử**. Nếu code xung quanh vẫn giữ `MethodHandle` hoặc instance, việc đặt `oldType = null` lại càng không chứng minh class đã đủ điều kiện unload.

## 15. Bài tập và tiêu chí đánh giá

**Bài 1 — Sơ đồ tham chiếu.** Vẽ đồ thị GC root → static cache → bound MethodHandle → instance → hidden class. **Đạt** khi giải thích được vì sao chỉ bỏ biến `Class<?>` có thể chưa cho phép unload.

**Bài 2 — Hai class từ cùng bytes.** Chạy thí nghiệm, dự đoán `distinctIdentity` và `crossInstance`. **Đạt** khi được `true` và `false`; nêu rõ class identity độc lập với bytes và cùng loader.

**Bài 3 — MethodType và receiver.** Xác định return type của constructor handle, receiver type của virtual method handle và số tham số sau `bindTo`. **Đạt** khi chúng lần lượt tham chiếu hidden class, hidden class và một tham số còn lại.

**Bài 4 — Mặc định và `STRONG`.** Giả sử một loader sống suốt ứng dụng nhưng mọi references trực tiếp đến generated classes được giải phóng. **Đạt** khi giải thích default hidden class **có thể unload** độc lập với loader, còn `STRONG` thì gắn vòng đời với loader, nhưng không khẳng định thời điểm GC.

**Bài 5 — WeakReference không phải phép unload.** Tạo `WeakReference<Class<?>>` và xóa các references do mình kiểm soát. **Đạt** khi chỉ ra tại sao `get()` có thể khác nhau giữa các lần chạy và không dùng `System.gc()` để tạo assertion cứng về thời gian.

**Bài 6 — Kiểm tra cache.** Thiết kế một bounded cache cho generated method handles, có thao tác eviction và lý giải lifetime của bound receivers. **Đạt** khi mô tả cách gỡ tất cả các nguồn giữ mạnh mà ứng dụng sở hữu, không hứa class unload tức thì.

**Bài 7 — Dùng lại hidden class.** Nêu cách tạo instance/gọi method ở thời điểm sau khi `defineHiddenClass` đã trả về. **Đạt** khi giữ `Class` hoặc handles/capabilities cần thiết thay vì dựa vào `Class.forName`.

**Bài 8 — Tài nguyên ngoài heap.** Một generated instance giữ socket, sau khi xong request thì làm gì? **Đạt** khi yêu cầu đóng tài nguyên chủ động, gỡ callback/cache và để JVM tự quản lý unloading sau đó.

## 16. Tài liệu chính thức

- [JEP 371 — Hidden Classes, JDK 15](https://openjdk.org/jeps/371): mục đích, mô hình hidden class và vòng đời.
- [Oracle Java SE 25 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): hợp đồng `defineHiddenClass`, hidden class có thể unload độc lập loader mặc định, full privilege access, option `STRONG`.
- [Oracle Java SE 25 — Lookup.ClassOption](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html): ý nghĩa chính thức của `NESTMATE` và `STRONG`.
- [Oracle Java SE 25 — MethodHandle](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandle.html): `invoke`, `invokeExact`, `bindTo`, `type` và member invocation.
- [Oracle Java SE 25 — MethodType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodType.html): `returnType()`, `parameterType()` và mô tả chữ ký của method handles.
- [Oracle Java SE 25 — WeakReference](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ref/WeakReference.html): hành vi tham chiếu yếu và GC.
- [Java Language Specification `12.7 — Unloading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.7): nguyên tắc class unloading trong JVM.

**Ghi nhớ:** Hidden class **không tự biến mất** chỉ vì phương thức định nghĩa đã kết thúc. `Class<?>`, instance, `Lookup` và `MethodHandle` đều là những **đường tham chiếu cần xét** khi quản lý liveness. Mặc định hidden class **có thể unload khi loader vẫn sống**, còn `ClassOption.STRONG` gắn class với vòng đời loader như class thường. Hãy quản lý ownership và eviction của code sinh động; đừng dùng `System.gc()` hay tên hidden class để giả lập lifecycle có thể dự đoán chính xác.
