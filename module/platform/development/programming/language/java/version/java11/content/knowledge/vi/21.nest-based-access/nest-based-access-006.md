# Nest-based access: Kiểm tra truy cập của Reflection và MethodHandles.Lookup trong Java 11+

> **Chủ đề cha:** Nest-based access. **Trọng tâm:** Cách JVM từ Java 11 nhận biết những lớp thuộc cùng một *nest*, ảnh hưởng tới kiểm tra quyền truy cập private của **Core Reflection** và **MethodHandles.Lookup**, và vì sao quyền truy cập sâu vẫn phải tôn trọng **Java Platform Module System (JPMS)**. Bài chỉ sử dụng API hiện còn được hỗ trợ: `Class.getNestHost`, `Class.isNestmateOf`, `AccessibleObject.canAccess`, `trySetAccessible`, `MethodHandles.lookup` và `MethodHandles.privateLookupIn`. Không dựa vào việc mở quyền truy cập JDK nội bộ bằng cơ chế cũ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **cùng nest** với **cùng package**, **cùng module**, **kế thừa** hoặc đơn giản là tên lớp có ký tự `$`.
2. Mô tả JEP 181 và hai class-file attributes `NestHost`/`NestMembers` giúp JVM cho các *nestmate* truy cập private của nhau trong Java 11.
3. Dùng `Class.getNestHost()`, `getNestMembers()`, `isNestmateOf(...)` để kiểm tra quan hệ nest ở runtime.
4. Lấy thông tin private bằng `getDeclaredField`/`getDeclaredMethod` mà không nhầm việc *tìm thấy member* với quyền *sử dụng member*.
5. Hiểu `Field.canAccess(target)` và `Method.canAccess(target)` theo **caller** thật, tại thời điểm kiểm tra, không dùng API `isAccessible()` đã deprecated.
6. Hiểu khi nào `trySetAccessible()` thành công/thất bại và vì sao **module mở package** mới cho phép deep reflection qua module boundary.
7. Tạo `MethodHandle` bằng `MethodHandles.Lookup.findGetter`/`findVirtual` để truy cập private trong cùng nest.
8. Nhận biết `MethodHandles.lookup()` là **caller-sensitive capability**, khác `publicLookup()` và `Lookup.in(...)`.
9. Dùng `MethodHandles.privateLookupIn(targetClass, callerLookup)` khi có quyền hợp lệ; không coi nó là công cụ vượt mọi ranh giới bảo mật.
10. Thực hành hai ví dụ chạy được bằng **`javac --release 11`**: một chương trình cùng nest/lớp độc lập; một ứng dụng hai named modules so sánh `exports` với `opens`.
11. Hiểu thời điểm thực hiện access check, xử lý exception chính xác, tránh lộ `MethodHandle`/`Lookup` có quyền private.
12. Thiết kế test cho thư viện reflection, serialization, DI và runtime code generation mà không dựa vào bypass đã lỗi thời.

## 2. Nest-based access là gì?

Một **nest** là tập lớp/interface mà JVM cho phép tham chiếu trực tiếp tới **private member** của nhau. Thông thường khi viết Java:

~~~java
public class Account {
    private int balance = 100;

    static class Auditor {
        static int read(Account account) {
            return account.balance;
        }
    }
}
~~~

Đây là **đoạn minh họa**. `Account` và `Account.Auditor` được javac Java 11+ biên dịch thành các class files riêng nhưng cùng nest. `Auditor` có thể đọc trực tiếp `private balance` của `Account` theo quy tắc Java, và JVM Java 11 hiểu quan hệ đó nhờ **nest attributes**.

### JEP 181 thay đổi điều gì?

Trước Java 11, compiler thường phải tạo **synthetic accessor methods** để một nested class gọi private member của outer class mà JVM cũ vốn không cho class files khác truy cập trực tiếp. JEP 181 (Java 11) đưa quyền truy cập nestmates vào **JVM access-control model**, nhờ đó compiler không cần sinh các accessors nhân tạo chỉ để mô phỏng quan hệ private giữa những lớp cùng nest.

Trong class files mới:

- **Nest host** liệt kê members bằng attribute `NestMembers`.
- **Nest member** có thể trỏ về host bằng attribute `NestHost`.
- JVM kiểm nhất quán quan hệ và điều kiện runtime package theo quy tắc class-file verifier/linker; không tin chỉ vào tên source hoặc chuỗi chứa dấu `$`.
- Nếu một class không có `NestHost` thì nó là host của chính nest chứa nó (có thể là một nest đơn lẻ).
- **Một class không được tự quyết định gia nhập nest khác** chỉ bằng cách đổi tên hay sử dụng reflection.
- JVM vẫn kiểm class/module/package visibility, method descriptor, invocation mode và các điều kiện khác khi member được truy cập.

### Sơ đồ

~~~text
Nest host: Account
    |
    +-- Account$Auditor           (nestmate)
    |
    +-- Account$Rules             (nestmate)
    |
    +-- Account$Nested$Inside     (có thể là nestmate, tùy class-file metadata)

Top-level class OtherAccount     (KHÔNG mặc định là nestmate)
Top-level class AuditorService   (KHÔNG mặc định là nestmate)
~~~

**Cùng package không đủ để vào cùng nest.** Một class cùng package có thể truy cập package-private members, nhưng **không** có quyền private của class khác chỉ vì cùng package.

## 3. Nhận diện nestmate tại runtime trong Java 11

Java 11 có ba API trên `java.lang.Class`:

| API | Ý nghĩa | Ghi chú |
| --- | --- | --- |
| `getNestHost()` | Trả `Class<?>` đại diện nest host | Trên một class đơn lẻ thường là chính nó |
| `getNestMembers()` | Trả mảng các class thuộc nest | Không suy đoán thứ tự phần tử làm hợp đồng ổn định |
| `isNestmateOf(Class<?> other)` | Kiểm hai class có thuộc cùng nest | Đúng dựa trên JVM metadata/runtime, không dựa tên |

Ví dụ trong một method có các class:

~~~java
boolean sameNest =
        Account.Auditor.class.isNestmateOf(Account.class);

Class<?> host = Account.Auditor.class.getNestHost();

System.out.println("same=" + sameNest);
System.out.println("host=" + host.getSimpleName());
~~~

**Đoạn minh họa**, `Account` là class ở mục 2; nếu biên dịch bằng Java 11+, giá trị mong đợi là `same=true`, host `Account`. Demo chạy độc lập ở mục 7 cung cấp stdout đã kiểm chứng.

### Không dựa vào Class.getEnclosingClass để cấp quyền

`getEnclosingClass()` mô tả quan hệ **lexical/enclosing class** theo metadata; `getNestHost()` nói về **nest ở mức JVM access control**. Chúng phục vụ hai câu hỏi khác nhau. Đối với private access giữa class files, hãy kiểm `isNestmateOf` hoặc dùng trực tiếp cơ chế access checks của Reflection/MethodHandles, không tự dựng một quy tắc cho phép từ chuỗi tên hoặc `getEnclosingClass()`.

### Class file Java 8 chạy trên Java 11?

Một nested class được biên dịch target Java cũ có thể sử dụng synthetic accessors và **không có** NestHost/NestMembers attributes. Việc source code có nested class **không bảo đảm** mọi file cũ khi chạy trên JVM mới sẽ đột nhiên có metadata nest mới.

Vì thế, nếu cần kiểm semantics của JEP 181, biên dịch ví dụ với:

~~~bash
javac --release 11 NestAccessDemo.java
~~~

Tham số `--release 11` yêu cầu javac hiện đại dùng API và class-file target phù hợp Java 11. Nếu dùng JDK 11 trực tiếp, có thể chỉ cần `javac NestAccessDemo.java`. Khi gỡ lỗi, có thể xem class-file attributes bằng `javap -v` trên tệp class được biên dịch, không sửa chúng bằng tay.

## 4. Các loại quyền truy cập cần phân biệt

Nest-based access **không xóa** các mức visibility khác của Java.

| Quyền hoặc quan hệ | Có tự cho truy cập private của class khác không? | Ý nghĩa |
| --- | --- | --- |
| Cùng class khai báo member | **Có** | Quyền private thông thường |
| Hai class **cùng nest** | **Có**, theo JEP 181 và các kiểm tra JVM khác | Outer/member/sibling có metadata nest hợp lệ |
| Hai top-level class cùng package | **Không** | Chỉ có package-private và các quyền khác phù hợp |
| Hai class cùng named module | **Không tự động** | Module boundary khác Java private visibility |
| Class con `extends Parent` | **Không** đối với private của parent | Private không trở thành member truy cập trực tiếp của subclass |
| Package `exports` cho module khác | **Không** cho private | Chủ yếu cho truy cập API public tương ứng |
| Package `opens` cho module khác | **Không tạo quan hệ nest** | Cho phép cơ chế deep reflection/Lookup hợp lệ, không phải quyền bytecode private tự phát |
| `trySetAccessible()` thành công | **Có thể** cho phép truy cập qua reflected object đó | Có điều kiện theo module/package access policy |
| `privateLookupIn` thành công | Tạo Lookup có khả năng truy cập private target | Yêu cầu đủ privileges, module readability và openness |

**Chỗ dễ nhầm nhất:** nếu hai class **không cùng nest**, một class có thể vẫn lấy được private field của class kia bằng **reflection được cấp phép** khi module cho phép. Điều đó **không biến chúng thành nestmates**. Nest membership và deep-reflection permission là **hai cơ chế khác nhau**.

## 5. Core Reflection: tìm member không đồng nghĩa có quyền truy cập

Ví dụ:

~~~java
Field field = SomeClass.class.getDeclaredField("secret");
~~~

`getDeclaredField("secret")` có thể trả đối tượng mô tả một private field, miễn member tồn tại theo chữ ký và class metadata có sẵn. Nhưng `field.get(receiver)` hoặc `field.set(receiver, value)` vẫn phải thực hiện **access check** theo điều kiện của Reflect API.

Cần phân biệt:

- **Discovery:** `getDeclaredField`, `getDeclaredMethod`, `getDeclaredConstructor` liệt kê/tìm khai báo, gồm non-public member.
- **Invocation/use:** `Field.get`/`set`, `Method.invoke`, `Constructor.newInstance` kiểm quyền khi dùng.
- **Caller:** class đang gọi thao tác access, không phải class đã gọi `getDeclaredField` hoặc nhận Field từ nơi khác.
- **Accessible flag:** nếu đã được bật hợp lệ, các kiểm tra Java language access thông thường cho reflected object đó được **suppressed**.
- **JPMS:** khi muốn bật accessible flag, giới hạn module/package vẫn áp dụng; không thể mở mọi private member của JDK tùy ý.

### API không nên dùng để kiểm quyền: isAccessible()

`AccessibleObject.isAccessible()` đã **deprecated từ Java 9** vì tên gây hiểu lầm: nó chỉ báo **flag “suppress access checks”**, không trả lời “caller hiện tại có quyền gọi member này hay không”.

Thay vào đó:

~~~java
Field field = Example.class.getDeclaredField("secret");

// Với instance field, receiver phải thuộc declaring class.
boolean allowedNow = field.canAccess(example);
~~~

**Đoạn minh họa**, cần `example` đúng kiểu. `canAccess` mới phản ánh caller/access flag theo API. Một private member được dùng hợp lệ bởi nestmate có thể có `canAccess()==true` dù chưa từng gọi `trySetAccessible`.

## 6. canAccess(Object) và quy tắc truyền receiver

`AccessibleObject.canAccess(Object obj)` (Java 9+) kiểm quyền của **caller thực tế** tại thời điểm gọi.

| Thành phần được phản chiếu | Đối số đúng cho `canAccess` | Ghi chú |
| --- | --- | --- |
| Instance field | Object thuộc declaring class hoặc subtype hợp lệ | Ví dụ `field.canAccess(target)` |
| Instance method | Object thuộc declaring class hoặc subtype hợp lệ | Ví dụ `method.canAccess(target)` |
| Static field | `null` | Ví dụ `staticField.canAccess(null)` |
| Static method | `null` | Ví dụ `staticMethod.canAccess(null)` |
| Constructor | `null` | Ví dụ `constructor.canAccess(null)` |

Với đối số sai, `canAccess` có thể ném **`IllegalArgumentException`**, không phải chỉ trả false.

Ví dụ lớp lồng được biên dịch cùng nest với class chứa private field:

~~~java
Field f = NestAccessDemo.class.getDeclaredField("code");
boolean allowed = f.canAccess(target);

if (allowed) {
    int code = f.getInt(target);
    System.out.println(code);
}
~~~

Đây là **đoạn minh họa** nằm trong phương thức của `NestAccessDemo.Member`; biến `target` là instance của `NestAccessDemo`. Trong ví dụ đầy đủ, `allowed==true` dù không gọi `setAccessible`.

### Method.invoke bọc exception như thế nào?

- `IllegalAccessException`: caller không được phép truy cập member theo Reflect API.
- `InvocationTargetException`: **phương thức đích đã được gọi nhưng ném exception**; dùng `getCause()` để tìm lỗi nghiệp vụ thực.
- `IllegalArgumentException`: receiver hoặc đối số không phù hợp.
- `NoSuchMethodException`: tên/chữ ký khi lookup metadata không tồn tại.

Không bắt tất cả exception rồi im lặng trả `null`: đó có thể che lỗi quyền truy cập hoặc lỗi trong chính code ứng dụng.

## 7. Chương trình Java 11+ chạy được: nestmate so với lớp độc lập

Chương trình `NestAccessDemo.java` gồm **một public top-level class** với member class `Member`, và **một top-level class độc lập** `ExternalProbe` trong cùng file/package mặc định.

Để so sánh công bằng, cả hai cách truy cập đều cùng hướng đến private field `code=73` và private method `reveal()` của `NestAccessDemo`.

### Mã nguồn toàn bộ

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class NestAccessDemo {
    private int code = 73;

    private String reveal() {
        return "private-ok";
    }

    static class Member {
        static void run(NestAccessDemo target) throws Throwable {
            // JEP 181: member class thuộc cùng nest.
            System.out.println("nest.same="
                    + Member.class.isNestmateOf(NestAccessDemo.class));
            System.out.println("nest.host="
                    + Member.class.getNestHost().getSimpleName());
            System.out.println("direct.member.read=" + target.code);

            // Reflection KHÔNG cần setAccessible khi caller là nestmate.
            Field field = NestAccessDemo.class.getDeclaredField("code");
            Method method = NestAccessDemo.class.getDeclaredMethod("reveal");

            System.out.println("reflect.member.canAccess="
                    + field.canAccess(target));
            System.out.println("reflect.member.read="
                    + field.getInt(target));
            System.out.println("reflect.member.invoke="
                    + method.invoke(target));

            // Lookup thuộc caller = Member, có quyền private của nest.
            MethodHandles.Lookup lookup = MethodHandles.lookup();

            MethodHandle getter = lookup.findGetter(
                    NestAccessDemo.class, "code", int.class);

            MethodHandle caller = lookup.findVirtual(
                    NestAccessDemo.class, "reveal",
                    MethodType.methodType(String.class));

            System.out.println("mh.member.read="
                    + (int) getter.invokeExact(target));
            System.out.println("mh.member.invoke="
                    + (String) caller.invokeExact(target));
        }
    }

    public static void main(String[] args) throws Throwable {
        NestAccessDemo target = new NestAccessDemo();
        Member.run(target);
        ExternalProbe.run(target);
    }
}

// Không phải nested class, nên không là nestmate của NestAccessDemo.
class ExternalProbe {
    static void run(NestAccessDemo target) throws Throwable {
        System.out.println("nest.outsider="
                + ExternalProbe.class.isNestmateOf(NestAccessDemo.class));

        Field field = NestAccessDemo.class.getDeclaredField("code");
        System.out.println("reflect.outsider.canAccess="
                + field.canAccess(target));

        boolean reflectDenied = false;
        try {
            field.getInt(target);
        } catch (IllegalAccessException expected) {
            reflectDenied = true;
        }
        System.out.println("reflect.outsider.denied=" + reflectDenied);

        // Trong unnamed module, package mở cho deep reflection.
        System.out.println("reflect.outsider.trySetAccessible="
                + field.trySetAccessible());
        System.out.println("reflect.outsider.afterAccess="
                + field.getInt(target));

        // Lookup mặc định của ExternalProbe không phải nestmate.
        MethodHandles.Lookup ordinary = MethodHandles.lookup();
        boolean lookupDenied = false;
        try {
            ordinary.findGetter(
                    NestAccessDemo.class, "code", int.class);
        } catch (IllegalAccessException expected) {
            lookupDenied = true;
        }
        System.out.println("mh.outsider.denied=" + lookupDenied);

        // Có thể yêu cầu deep lookup do cùng unnamed module.
        MethodHandles.Lookup deep =
                MethodHandles.privateLookupIn(
                        NestAccessDemo.class, ordinary);

        MethodHandle getter = deep.findGetter(
                NestAccessDemo.class, "code", int.class);

        System.out.println("mh.outsider.deepValue="
                + (int) getter.invokeExact(target));

        // publicLookup không đủ PRIVATE và MODULE privileges.
        boolean weakDenied = false;
        try {
            MethodHandles.privateLookupIn(
                    NestAccessDemo.class,
                    MethodHandles.publicLookup());
        } catch (IllegalAccessException expected) {
            weakDenied = true;
        }
        System.out.println("mh.publicLookup.deepDenied=" + weakDenied);
    }
}
~~~

### Biên dịch với target Java 11 và chạy

~~~bash
javac --release 11 NestAccessDemo.java
java NestAccessDemo
~~~

Nếu đang dùng trực tiếp JDK 11, `javac NestAccessDemo.java` cũng hợp lệ. Chương trình không cần mạng, database hoặc thư viện ngoài Java SE.

**Stdout đã được kiểm bằng biên dịch `javac --release 11` rồi chạy JDK thực:**

~~~text
nest.same=true
nest.host=NestAccessDemo
direct.member.read=73
reflect.member.canAccess=true
reflect.member.read=73
reflect.member.invoke=private-ok
mh.member.read=73
mh.member.invoke=private-ok
nest.outsider=false
reflect.outsider.canAccess=false
reflect.outsider.denied=true
reflect.outsider.trySetAccessible=true
reflect.outsider.afterAccess=73
mh.outsider.denied=true
mh.outsider.deepValue=73
mh.publicLookup.deepDenied=true
~~~

### Phân tích kết quả từng nhóm

**Nhóm 1 — nest membership:**

- `Member.class.isNestmateOf(NestAccessDemo.class)` trả `true`.
- `Member.class.getNestHost()` trả `NestAccessDemo.class`; host có simple name `NestAccessDemo`.
- `ExternalProbe.class.isNestmateOf(NestAccessDemo.class)` trả `false` vì `ExternalProbe` là top-level class độc lập, dù **cùng file nguồn, cùng package mặc định và cùng unnamed module**. Một file nguồn chứa hai class không tạo nest giữa hai top-level classes.

**Nhóm 2 — direct/private reflection của member:**

- `Member` đọc trực tiếp `target.code`. Java source cho phép, JVM Java 11 kiểm thấy cùng nest.
- `field.canAccess(target)==true` với caller `Member`, **không cần** `setAccessible(true)`.
- `field.getInt(target)` và `method.invoke(target)` trả lần lượt `73` và `private-ok`. Reflection tuân thủ nest-based private access.

**Nhóm 3 — MethodHandles.Lookup của member:**

- `MethodHandles.lookup()` nằm **trong code của `Member`**, nên lookup class là `Member`.
- `findGetter(NestAccessDemo.class, "code", int.class)` được phép vì hai lớp cùng nest.
- `findVirtual(...,"reveal", MethodType.methodType(String.class))` truy cập private method cùng nest.
- `invokeExact(target)` được gọi với receiver/return type đúng để tránh `WrongMethodTypeException`.

**Nhóm 4 — caller bên ngoài nest:**

- `ExternalProbe` không thể `field.getInt(target)` ngay lập tức; access check ném `IllegalAccessException`.
- `field.canAccess(target) == false` phản ánh quyền của caller trước khi bật accessible flag.
- `field.trySetAccessible() == true` **không phải vì cùng nest** mà vì class ở đây nằm trong **unnamed module**, các package của unnamed module mở cho deep reflection.
- Sau khi bật flag trên chính `Field` đó, `field.getInt(target)` đọc được `73`.
- `MethodHandles.lookup()` tạo trong `ExternalProbe` **không** có quyền private mặc định của `NestAccessDemo`; `findGetter` từ lookup này bị từ chối.
- `MethodHandles.privateLookupIn(NestAccessDemo.class, ordinary)` thành công **trong bối cảnh quyền/module hiện tại** và cấp Lookup phù hợp để tạo MethodHandle đọc private; nó không làm `ExternalProbe` trở thành nestmate.
- `MethodHandles.publicLookup()` không có đặc quyền cần thiết để dùng `privateLookupIn`, nên bị từ chối.

**Bản chất:** Quyền private trực tiếp giữa nestmate và deep reflection giữa hai class cùng/open module là **hai đường khác nhau**. Chương trình cho thấy cả hai, không dựa vào cơ chế mở JDK internals.

## 8. Tại sao Reflection và MethodHandles.Lookup khác nhau?

Hai API cùng có thể truy cập fields/methods/constructors, nhưng **thời điểm kiểm tra quyền khác nhau**.

| Yếu tố | Core Reflection | MethodHandles.Lookup |
| --- | --- | --- |
| API khởi đầu | `Class.getDeclaredField`, `getDeclaredMethod` | `MethodHandles.lookup()`, `Lookup.findGetter`, `findVirtual` |
| Tìm metadata private | Có thể tìm được khi member tồn tại | Cần đủ quyền để tạo direct MethodHandle |
| Khi thực hiện access check quan trọng | `Field.get/Method.invoke`, `canAccess`; tùy accessible flag | **Khi tạo handle** bằng các factory methods của `Lookup` |
| Danh tính/quyền | Caller của thao tác reflection, và accessible flag | `lookupClass()`/`lookupModes()` đã gắn trong Lookup |
| Cách xin deep access | `trySetAccessible()`/`setAccessible(true)` khi policy cho phép | `MethodHandles.privateLookupIn(...)` khi quyền đủ |
| Sau khi tạo quyền | Reflected object có flag accessible có thể dùng trong phạm vi được cấp | MethodHandle là **capability**, kiểm access lúc tạo, có thể được gọi bởi code được trao handle |
| Kiểu dữ liệu lúc gọi | `Object`/boxing với reflective invocation | `MethodType` rõ ràng; `invokeExact` yêu cầu chữ ký chuẩn |
| Lỗi quyền truy cập | `IllegalAccessException`, `InaccessibleObjectException` | `IllegalAccessException` khi lookup/handle creation |
| Khác biệt hiệu năng | Reflection có thể được JVM tối ưu | MethodHandle cũng có thể được JVM tối ưu; không mặc nhiên luôn nhanh hơn |

### Một chi tiết bảo mật quan trọng

Javadoc `MethodHandles.Lookup` nói rõ: **MethodHandle sau khi tạo không lặp lại access check riêng cho từng caller mỗi khi invoke**. Nếu code tin cậy tạo handle tới private member rồi **phát tán handle cho code không tin cậy**, bên nhận có thể sử dụng capability đó.

Tương tự, truyền một `Lookup` có private access cho code không tin cậy là trao cho code ấy quyền tạo thêm nhiều method handles tới các member được phép. Do đó:

- Không lưu `Lookup` private mạnh trong registry công khai hoặc context mà plugin không tin cậy có thể lấy.
- Không log/serialize trực tiếp capability nội bộ ra API.
- Nếu phải trao quyền hạn chế, thiết kế API wrapper có validation và chỉ expose thao tác đã xét.
- Không gọi `Lookup.in(...)` như “cách sandbox chắc chắn” nếu chưa hiểu các access modes còn lại.

**Một public method trả MethodHandle đã có quyền private có thể vô tình phá encapsulation**, dù bản thân target member vẫn khai báo `private`.

## 9. MethodHandles.lookup(), publicLookup() và privateLookupIn()

### 9.1. MethodHandles.lookup() là caller-sensitive

~~~java
MethodHandles.Lookup here = MethodHandles.lookup();
System.out.println(here.lookupClass().getName());
~~~

Đây là đoạn minh họa. `lookup()` gắn **lookup class** với class gọi trực tiếp `MethodHandles.lookup()`, không phụ thuộc đối tượng mà bạn muốn truy cập sau đó.

Nếu gọi `MethodHandles.lookup()` trong helper thư viện, bạn nhận **Lookup của helper**, không tự nhiên nhận Lookup có quyền của class nghiệp vụ đã gọi helper. Đó là lý do một framework thường phải nhận `Lookup` từ caller hợp lệ hoặc sử dụng `privateLookupIn` với module openness thích hợp.

### 9.2. publicLookup() không thể đọc private

~~~java
MethodHandles.Lookup onlyPublic =
        MethodHandles.publicLookup();
~~~

Lookup này chỉ dành cho member public trong public types/packages đủ quyền theo module rules. Nó không có `PRIVATE` và `MODULE` để deep lookup private một class tùy ý. `privateLookupIn(target, publicLookup())` không được cấp phép.

### 9.3. privateLookupIn không phải bypass mọi boundary

~~~java
MethodHandles.Lookup deep =
        MethodHandles.privateLookupIn(
                Target.class, MethodHandles.lookup());
~~~

Đây là **đoạn minh họa**, cần có class `Target` và caller hợp lệ.

Trong Java 11, một caller Lookup được dùng để `privateLookupIn` phải có **PRIVATE** và **MODULE** access. Khi sang **module khác**, phải có:

- Quan hệ **readability**: module caller đọc được module target;
- Package chứa target được module target **opens** đến caller module (hoặc là open module);
- Các quyền khác theo API/module policy.

Nếu target ở **cùng module**, điều kiện deep access thường được thỏa mãn với một caller Lookup có đủ privileges; điều này **không** biến hai class thành nestmate.

Lỗi thường là `IllegalAccessException` khi module chưa open hoặc lookup không đủ quyền, không phải “chỉ cần đổi tên class/field”.

### 9.4. Lookup.in không tăng quyền

`lookup.in(NewClass.class)` thay đổi lookup class trong phạm vi quy tắc API, và có thể **mất bớt lookup modes** khi chuyển sang class/module/package khác. Nó **không** cấp tự động quyền private của mọi class.

Vì vậy:

~~~java
MethodHandles.Lookup moved =
        MethodHandles.lookup().in(Target.class);
~~~

**Đoạn minh họa**, không được xem là phép tương đương với `MethodHandles.privateLookupIn`. Kiểm `moved.lookupModes()` và thực hiện thử `findGetter`/`findVirtual` ở thời điểm thích hợp, thay vì suy ra quyền chỉ từ `lookupClass()`.

### 9.5. Lookup modes (Java 11)

Java 11 có các mode như `PUBLIC`, `PRIVATE`, `PROTECTED`, `PACKAGE` và `MODULE`. Khi cần chẩn đoán:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();

boolean hasPrivate =
        (lookup.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0;
boolean hasModule =
        (lookup.lookupModes() & MethodHandles.Lookup.MODULE) != 0;
~~~

Đoạn mã minh họa. **Không dùng API chỉ xuất hiện sau Java 11** để giải thích một chương trình Java 11, ví dụ dựa vào lookup mode bổ sung của JDK mới như thể đã tồn tại từ Java 11.

## 10. Reflection: trySetAccessible() khác setAccessible(true) thế nào?

Từ Java 9, `AccessibleObject.trySetAccessible()` trả boolean:

~~~java
Field f = Target.class.getDeclaredField("secret");

if (f.trySetAccessible()) {
    // Chỉ làm việc với member nếu deep access thật sự được cho phép.
} else {
    // Module/package không cho phép suppress access checks.
}
~~~

**Đoạn minh họa**, `Target` là một class có member tên `secret`.

So sánh:

| API | Khi bật quyền thành công | Khi module không cho bật |
| --- | --- | --- |
| `trySetAccessible()` | Trả `true` và bật flag | Thường trả **`false`** |
| `setAccessible(true)` | Bật flag | Thường ném `InaccessibleObjectException` |
| `canAccess(receiver)` | Kiểm quyền hiện tại | Trả false khi caller/flag không cho (nếu receiver hợp lệ) |
| `isAccessible()` | Chỉ trả accessible flag | **Deprecated**; không dùng làm phép kiểm quyền hiện đại |

**Không** dùng `trySetAccessible()` chỉ để “thử xem có lỗi không” rồi mặc định đọc private field nếu false. Phải có fallback hợp lý: dùng public API, thay module declaration, hoặc từ chối tác vụ.

### canAccess(true) của nestmate không cần suppress flag

Ví dụ Member trong mục 7 nhận `field.canAccess(target)==true` vì caller đã được Java/JVM cho quyền private theo **nest-based access**. Nó không có nghĩa `field` đã bật accessible flag. Đây là lý do `isAccessible()` trở nên gây hiểu nhầm và không còn là API kiểm quyền nên dùng.

### Same-module reflective access vẫn không đồng nghĩa bytecode access

Một class hoàn toàn độc lập trong cùng module có thể gọi `trySetAccessible` thành công cho private member của class khác **theo quy tắc Reflection**. Nhưng code Java trực tiếp như `target.secret` từ class đó vẫn **không biên dịch** vì private access của ngôn ngữ không được nới. Reflection có cơ chế xin deep access cụ thể.

## 11. JPMS: exports không bằng opens

Bên ngoài nest, vấn đề lớn nhất là **module boundary** của Java 9+.

Named module `lib.model` có package `demo.model`, chứa public class `Vault` với private field `secret`.

### Trường hợp 1: package chỉ exports

~~~java
// File: src/lib.model/module-info.java
module lib.model {
    exports demo.model;
}
~~~

`exports demo.model;` cho module khác đọc các **public types/members** phù hợp trong package, nhưng **không** cho deep reflection vào private field.

### Trường hợp 2: package opens có mục tiêu

~~~java
// File: src/lib.model/module-info.java
module lib.model {
    exports demo.model;
    opens demo.model to app.runner;
}
~~~

`opens demo.model to app.runner;` cho module `app.runner` dùng cơ chế deep reflection hợp lệ vào package, nhưng **không** cho một module khác không được liệt kê. Đây là **qualified opens** và thường hạn chế phạm vi hơn `opens demo.model;` cho mọi module.

**Mở package không tạo nest relationship**: `Vault` và `Main` vẫn không thể dùng Java bytecode để đọc trực tiếp `Vault.secret` nếu chúng không phải nestmates.

### Tóm tắt module rules

| Khai báo trong `lib.model` | Public API qua compile/access | Deep reflection private từ `app.runner` |
| --- | --- | --- |
| Không `exports`/`opens` | Không có public access thông thường qua module | Không |
| `exports demo.model;` | Có public access thích hợp | **Không**, chỉ exports |
| `opens demo.model to app.runner;` | Cho deep reflection; không thay exports như một API biên dịch tổng quát | Có nếu caller có quyền/reads module |
| `exports ...; opens ... to app.runner;` | Có public API và deep reflection cho app.runner | Có |
| `open module lib.model { ... }` | Tất cả package mở cho deep reflection; vẫn phân biệt exports/public access | Có theo các điều kiện API, phạm vi mở rất rộng |

Thực tế một dependency DI/ORM/JSON có thể yêu cầu `opens my.package to framework.module;` để tạo instance/đọc field private; điều này phải do **người sở hữu module** chủ đích cho phép, không phải thư viện tự phá module encapsulation.

## 12. Chương trình hai named modules đã chạy: exports so với opens

Ví dụ sau kiểm **phạm vi JPMS thực**, không chỉ dựng bảng lý thuyết.

Cấu trúc thư mục:

~~~text
src/
├── lib.model/
│   ├── module-info.java
│   └── demo/model/Vault.java
└── app.runner/
    ├── module-info.java
    └── demo/app/Main.java
~~~

### 12.1. Module lib.model

Tạo `src/lib.model/module-info.java`:

~~~java
module lib.model {
    exports demo.model;
}
~~~

Tạo `src/lib.model/demo/model/Vault.java`:

~~~java
package demo.model;

public class Vault {
    private int secret = 91;

    public String ping() {
        return "ok";
    }
}
~~~

### 12.2. Module app.runner

Tạo `src/app.runner/module-info.java`:

~~~java
module app.runner {
    requires lib.model;
}
~~~

Tạo `src/app.runner/demo/app/Main.java`:

~~~java
package demo.app;

import demo.model.Vault;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.Field;

public class Main {
    public static void main(String[] args) throws Throwable {
        Vault v = new Vault();
        Field f = Vault.class.getDeclaredField("secret");

        System.out.println(
                "reflect.canAccess=" + f.canAccess(v));
        System.out.println(
                "reflect.trySetAccessible=" + f.trySetAccessible());

        MethodHandles.Lookup caller = MethodHandles.lookup();
        boolean denied = false;

        try {
            MethodHandles.Lookup deep =
                    MethodHandles.privateLookupIn(Vault.class, caller);

            MethodHandle getter = deep.findGetter(
                    Vault.class, "secret", int.class);

            System.out.println(
                    "mh.deepValue=" + (int) getter.invokeExact(v));
        } catch (IllegalAccessException expected) {
            denied = true;
        }

        System.out.println("mh.denied=" + denied);
    }
}
~~~

**Lưu ý bảo mật:** `Main` chạy trong `app.runner`; `Vault` nằm trong `lib.model`. Code có `exports` cho public API và `requires` đọc module, nhưng **chưa có opens**. `getDeclaredField` vẫn tìm được metadata; dùng private member qua deep access phải bị từ chối.

### 12.3. Build và chạy với exports-only

Tại thư mục dự án có `src/`:

~~~bash
javac --release 11 -d mods --module-source-path src -m lib.model,app.runner
java --module-path mods -m app.runner/demo.app.Main
~~~

**Stdout đã kiểm qua biên dịch và chạy thực tế với Java target 11:**

~~~text
reflect.canAccess=false
reflect.trySetAccessible=false
mh.denied=true
~~~

Giải thích:

- `f.canAccess(v) == false` vì `Main` không phải nestmate của `Vault` và field private không truy cập trực tiếp được.
- `f.trySetAccessible() == false` vì `lib.model` chỉ `exports` package, **không opens** cho `app.runner`.
- `MethodHandles.privateLookupIn(Vault.class, caller)` ném `IllegalAccessException`: caller module đọc được library nhưng target package không được mở để deep lookup.

### 12.4. Chỉ thay module-info.java để mở đúng đích

Trong **cùng bài test**, thay nội dung `src/lib.model/module-info.java` thành:

~~~java
module lib.model {
    exports demo.model;
    opens demo.model to app.runner;
}
~~~

Biên dịch lại:

~~~bash
javac --release 11 -d mods --module-source-path src -m lib.model,app.runner
java --module-path mods -m app.runner/demo.app.Main
~~~

**Stdout đã kiểm thực tế sau khi mở package:**

~~~text
reflect.canAccess=false
reflect.trySetAccessible=true
mh.deepValue=91
mh.denied=false
~~~

Tại sao `reflect.canAccess=false` vẫn không đổi? Vì dòng này chạy **trước khi bật accessible flag**, và `opens` chỉ cho phép **xin deep reflection**, không biến `Main` thành nestmate hay thành caller có Java private access theo cú pháp nguồn. Sau `trySetAccessible() == true`, `Field` của chương trình được phép đọc private; phần demo chỉ in quyền chứ không gọi `getInt`.

`privateLookupIn` thành công sau khi package được mở, và handle đọc field trả `91`. Đây là bằng chứng **qualified opens** tác động đến Lookup deep access theo đúng module policy.

### Một số lưu ý khi tự chạy

- Tạo lại thư mục build nếu `mods/` còn class files từ bài thử khác; tránh nhầm kết quả do file cũ.
- Dùng đúng tên module `lib.model`/`app.runner` và đường dẫn source đã trình bày.
- `javac --release 11` buộc mã dùng API Java 11, và yêu cầu JDK đang chạy có hỗ trợ `--release` này.
- Đây là **hai lượt chạy** riêng với hai nội dung `module-info.java` khác nhau; không tồn tại cả hai khai báo cùng một lúc.
- Không đưa `--add-opens` vào lệnh để vượt case 1, vì mục tiêu của test là chứng minh module đóng chặn deep reflection.

## 13. Vì sao --add-opens không nên là giải pháp mặc định?

Trong một số tình huống migration, JVM cho phép startup option `--add-opens module/package=targetModule` để mở package có kiểm soát khi không thể sửa module nguồn. Tuy nhiên:

- Đây là **nới boundary tại runtime**, không làm code có quan hệ nestmates.
- Nó có thể tạo lỗ hổng nếu mở rộng quá mức (đặc biệt `ALL-UNNAMED` mà không có review).
- Không dùng các tùy chọn compatibility đã hết hiệu lực hoặc bị loại bỏ ở JDK mới để truy cập JDK internals.
- Java 17+ mặc định strong encapsulation của phần lớn JDK internals; không suy luận một thủ thuật chạy ở JVM rất cũ vẫn hợp lệ trên JDK hiện hành.
- Ưu tiên **public API**, qualified `opens` trong module mình kiểm soát hoặc cơ chế extension công khai của framework.
- Khi buộc dùng runtime opens tạm thời, ghi phạm vi, chủ sở hữu, lý do, thời hạn migration, test và security review.

**Không cố deep-reflect private fields của `java.lang.String` hay các lớp JDK nội bộ để làm việc thông thường.** Những implementation details có thể thay đổi và không phải public API ổn định.

## 14. Những lỗi phổ biến của MethodHandles.Lookup

### 14.1. Lookup tạo nhầm caller

~~~java
// Đây là Lookup của chính class gọi dòng code này:
MethodHandles.Lookup caller = MethodHandles.lookup();
~~~

Nếu bạn tạo lookup trong `ReflectionHelper` thay vì class nestmate, nó không tự có quyền private của target. Một lỗi thường là copy mẫu `MethodHandles.lookup()` từ ví dụ khác rồi đặt nó trong class không có quyền.

### 14.2. Tưởng privateLookupIn có thể bỏ qua opens

~~~java
MethodHandles.Lookup deep =
        MethodHandles.privateLookupIn(Target.class, caller);
~~~

**Mã minh họa**; nếu target module khác không mở package, phép gọi thất bại. Nếu caller lookup thiếu `MODULE` hoặc `PRIVATE`, cũng thất bại. Không retry vô hạn hoặc tắt encapsulation bằng flags cũ.

### 14.3. Tưởng publicLookup có thể truy cập mọi public type nội bộ

`publicLookup` chỉ có quyền công khai theo quy tắc module exports và accessibility. Public class trong package **không exported** của named module không trở thành public API có thể sử dụng tự do chỉ vì Java modifier là `public`.

### 14.4. Tưởng Lookup.in là phép nâng quyền

`Lookup.in` tạo lookup mới và thường chỉ **giữ nguyên hoặc giảm** quyền, tùy target class/module. Đừng dùng nó như thay thế cho một `privateLookupIn` đã được cấp đúng.

### 14.5. Nhầm findGetter với findStaticGetter

Với `private int code;` là instance field, dùng:

~~~java
MethodHandle getter =
        lookup.findGetter(NestAccessDemo.class, "code", int.class);
~~~

Với `private static int counter;` mới dùng:

~~~java
MethodHandle staticGetter =
        lookup.findStaticGetter(
                NestAccessDemo.class, "counter", int.class);
~~~

**Đây là các đoạn minh họa** trong method có lookup đủ quyền và class/members tương ứng. Nếu field không tồn tại theo tên/chữ ký hoặc member static/instance không đúng, có thể nhận `NoSuchFieldException` hoặc lỗi truy cập.

### 14.6. invokeExact với kiểu không khớp

`MethodHandle.invokeExact` dựa trên **MethodType** và loại đối số/return type ngay tại call site. Một getter kiểu `(NestAccessDemo)int` cần receiver đúng kiểu và mong đợi return `int`:

~~~java
int value = (int) getter.invokeExact(target);
~~~

Nếu gán trực tiếp sang `Object`/không cast đúng trong vị trí kỳ vọng, có thể gặp `WrongMethodTypeException`. `MethodHandle.invoke(...)` có khả năng chuyển đổi kiểu theo quy tắc method handles nhưng không sửa thiếu quyền hoặc sai chữ ký method được tìm.

## 15. Kết hợp Reflection và MethodHandles đúng cách

Một framework đôi khi tìm member bằng Reflection, rồi dùng MethodHandle để gọi nhanh/ổn định hơn sau khi đã tạo capability phù hợp.

### Tạo MethodHandle từ reflected Method

~~~java
Method method =
        Target.class.getDeclaredMethod("internalOperation");

MethodHandles.Lookup lookup = MethodHandles.lookup();

// Đòi hỏi lookup có quyền truy cập member hoặc
// reflected object đã được phép suppress checks theo hợp đồng.
MethodHandle handle = lookup.unreflect(method);
~~~

**Đoạn minh họa**, cần class `Target` và caller có quyền phù hợp. `unreflect` không làm mọi private method trở thành public. Nó vẫn phải giải quyết quyền theo Lookup/accessible object và các điều kiện liên quan.

### Từ reflected Field tạo MethodHandle

~~~java
Field f = Target.class.getDeclaredField("secret");
MethodHandle getter = lookup.unreflectGetter(f);
~~~

**Mã minh họa**, cần Lookup/field được cấp quyền. Nếu chỉ cần đọc/ghi field với semantics typed/atomic, có thể cân nhắc **`VarHandle`** (có từ Java 9) thay vì thao tác raw Reflection; quyền để lấy VarHandle vẫn do Lookup và JPMS kiểm tra.

### Không cache handle trong registry không tin cậy

Nếu library cache MethodHandle để tối ưu, giữ cache trong boundary được bảo vệ. Một handle đã được cấp quyền private có thể tiếp tục được invoke bởi code nhận nó; **đừng coi một lần check access tại thời điểm tạo là lý do để công khai handle**.

### Khi nào chọn API nào?

| Tình huống | Gợi ý |
| --- | --- |
| Code application có source hợp lệ và compile-time types | Truy cập Java trực tiếp trong phạm vi cho phép |
| Nested class cùng nest | Java direct private access hoặc Lookup từ nestmate theo nhu cầu |
| Introspection cấu trúc class/methods | Core Reflection + `canAccess`/`trySetAccessible` khi cần |
| Runtime invocation thường xuyên với signature rõ | `MethodHandle`/`VarHandle` có quyền hợp lệ |
| Thư viện cần deep access vào named module khác | Chủ module dùng `opens package to framework.module` khi chính sách cho phép |
| Plugin không đáng tin | Chỉ expose public/validated API, không cấp full-privilege Lookup |
| Muốn sửa workaround synthetic accessor trước Java 11 | Compile/run theo Java 11+; không giả định class cũ tự có nest metadata |

Không chọn MethodHandles chỉ vì “lúc nào cũng nhanh hơn Reflection”. Cả hai có thể được JIT tối ưu; lựa chọn phụ thuộc API, kiểu dữ liệu, tần suất, khả năng maintain và đo đạc thực.

## 16. Lỗi và ngoại lệ nên bắt đúng

| Lỗi | Thường gặp ở đâu | Cách xử lý |
| --- | --- | --- |
| `NoSuchFieldException` | `getDeclaredField`/`findGetter` sai tên hoặc kiểu | Kiểm class thực tế, field name, static/instance, signature |
| `NoSuchMethodException` | `getDeclaredMethod`/`findVirtual` sai tên hoặc MethodType | Kiểm danh sách parameter types và return type |
| `IllegalAccessException` | Reflection gọi private từ non-nestmate; Lookup thiếu quyền | Dùng public API, correct nest caller hoặc mở module hợp lệ |
| `InaccessibleObjectException` | `setAccessible(true)` bị JPMS từ chối | Qualified `opens`/sửa design thay vì bypass |
| `IllegalArgumentException` | `canAccess` sai receiver hoặc reflection wrong argument | Instance receiver đúng kiểu; static/constructor dùng null |
| `InvocationTargetException` | `Method.invoke` gọi được nhưng method đích ném lỗi | Lấy `getCause()`; không lẫn access failure |
| `WrongMethodTypeException` | `MethodHandle.invokeExact` sai call-site type | Khớp chính xác `MethodType` |
| `ClassCastException` | Kết quả Reflection ép kiểu sai | Dùng declared type/safe cast |
| `IllegalAccessError` / `IncompatibleClassChangeError` | Bytecode/linkage metadata/nest info không nhất quán | Kiểm lại class files, compiler và class-loader boundaries |
| `NoClassDefFoundError` | Runtime thiếu dependency | Sửa module/classpath/runtime distribution |

**Không** chuyển `IllegalAccessException` thành `null` rồi tiếp tục như member hợp lệ: điều đó có thể gây lỗi âm thầm và che cấu hình module sai.

## 17. Kiểm thử đúng các quyền khác nhau

### Ma trận kiểm thử ngắn gọn

| Case | Đầu vào/quan hệ | Kết quả mong đợi |
| --- | --- | --- |
| Nest member đọc private trực tiếp | `Outer.Inner` → `Outer.privateField` | Thành công trên class files Java 11+ cùng nest |
| Nest member reflection | `Field.canAccess` rồi `Field.get` | `true` và đọc được |
| Nest member MethodHandle | Lookup tạo trong `Inner`, `findGetter` | Tạo handle và invoke được |
| Top-level class độc lập cùng package | Direct private field | Không hợp lệ ở mức source/bytecode access |
| Top-level class độc lập Reflection | `canAccess` trước bật flag | `false` |
| Top-level class độc lập Reflection | `Field.get` trước bật flag | `IllegalAccessException` |
| Top-level class trong unnamed module | `trySetAccessible` private field | Có thể thành công do package open |
| Top-level class độc lập MethodHandles | `MethodHandles.lookup().findGetter(private)` | `IllegalAccessException` |
| Top-level class hợp quyền | `privateLookupIn(Target, caller)` cùng module | Có thể tạo deep lookup |
| Lookup yếu | `privateLookupIn(Target, publicLookup)` | `IllegalAccessException` |
| Named module chỉ exports | Cross-module `trySetAccessible` private | `false` |
| Named module chỉ exports | Cross-module `privateLookupIn` | `IllegalAccessException` |
| Named module qualified opens | `trySetAccessible`, `privateLookupIn` đúng target | Thành công nếu quyền/reads phù hợp |
| Wrong receiver cho `canAccess` | Instance member + null | `IllegalArgumentException` |
| Wrong MethodType | `invokeExact` với kiểu khác | `WrongMethodTypeException` |
| MethodHandle bị lộ | Caller khác nhận valid privileged handle | Có thể invoke; phải kiểm design bảo mật |
| Class file cũ không có nest metadata | Chạy trên JVM mới | Không suy luận phải có nest membership như class files mới |

### Test assertion cho demo đầu

Trong test có thể thay dòng console bằng:

~~~java
if (!NestAccessDemo.Member.class.isNestmateOf(NestAccessDemo.class)) {
    throw new AssertionError("Missing expected nest relationship");
}
if (ExternalProbe.class.isNestmateOf(NestAccessDemo.class)) {
    throw new AssertionError("Unexpected nest relationship");
}
~~~

**Đoạn minh họa** nằm trong cùng package/fixture với hai class. Nó kiểm runtime class metadata, không phụ thuộc tên source file là gì.

### Test modules và CI

- Biên dịch cả **source class** và **module-info.java** trên target Java phù hợp.
- Chạy test với **module path** cho phép thử JPMS thật; chỉ dùng classpath/unnamed module sẽ không tái hiện lỗi đóng package.
- Có cả test **exports-only (bị từ chối)** và **qualified opens (cho phép)**.
- Kiểm với JDK/vendor/bản vá production; tránh phụ thuộc một IDE tình cờ thêm `--add-opens`.
- Đừng ghi exception message đầy đủ làm expected stdout cố định; thông điệp có thể khác theo JDK.
- Với code generation, kiểm class loader, module/package và quan hệ nest được JVM chấp nhận, không chỉ tên class giống nhau.

## 18. Lỗi thiết kế thường gặp

| Ngộ nhận | Vì sao sai | Cách đúng |
| --- | --- | --- |
| “Private chỉ truy cập được trong một class file.” | Java 11 hỗ trợ nestmates across class files | Dùng JVM nest metadata và quy tắc JEP 181 |
| “Cùng package = cùng nest.” | Package không tự tạo NestHost/NestMembers | Kiểm `isNestmateOf` |
| “Hai top-level classes trong cùng file là nestmates.” | Quan hệ source file không xác lập nest | Chỉ nest metadata hợp lệ quyết định |
| “`getDeclaredField` thành công nghĩa là `get` cũng thành công.” | Discovery khác access check | Dùng `canAccess` hoặc catch IllegalAccessException |
| “`isAccessible()` cho biết có quyền.” | Deprecated; chỉ là suppress-access flag | Dùng `canAccess` |
| “Nestmate luôn phải gọi `setAccessible(true)`.” | JVM cho quyền private trực tiếp | Không suppress checks nếu caller đã đủ quyền |
| “Private field không thể được reflection đọc từ non-nestmate.” | Deep reflection hợp lệ có thể được cấp qua modules | Dùng `trySetAccessible` có kiểm soát |
| “exports cho quyền deep reflection.” | Public API export khác package openness | Dùng qualified opens khi policy cho phép |
| “opens biến hai class thành nestmates.” | Opens không đổi class-file metadata | Phân biệt module openness và nest membership |
| “privateLookupIn bỏ qua mọi module rule.” | Cần caller full privilege/reads/opens | Cấp quyền đúng, không bypass |
| “Lookup.in luôn tăng quyền.” | Có thể giảm modes, không nâng tùy ý | Dùng API đúng và kiểm lookupModes |
| “publicLookup tạo private handle.” | Không có PRIVATE/MODULE | Dùng trusted Lookup hợp pháp |
| “MethodHandle mỗi lần invoke đều kiểm caller.” | Access check quan trọng thực hiện lúc **tạo handle** | Giữ handle là capability nhạy cảm |
| “Đưa Lookup private cho plugin không có rủi ro.” | Plugin có thể tạo handles tới private members | Không lộ capability mạnh |
| “Bật opens ALL-UNNAMED cho mọi package là phương án lâu dài.” | Nới ranh giới quá rộng | Giới hạn qualified opens và migration plan |
| “Reflection luôn chậm hơn MethodHandles.” | Hiệu năng tùy JIT/workload | Benchmark nếu thực sự quan trọng |
| “Lỗi invokeExact luôn là lỗi access.” | Có thể do sai MethodType | Phân biệt lookup permission và call-site type |
| “Class files Java 8 tự có NestHost khi chạy Java 11.” | JVM không tự sinh class-file attributes | Compile theo target và kiểm bytecode |
| “Mở private member JDK bằng flag cũ là API ổn định.” | Strong encapsulation và internals thay đổi | Dùng public Java API hiện hành |

## 19. Checklist áp dụng vào dự án Java 11+

- [ ] Khi muốn dựa vào nestmates, class files được biên dịch với metadata Java 11+ phù hợp.
- [ ] Dùng `getNestHost`/`isNestmateOf` để xác minh, không suy luận từ tên có `$`.
- [ ] Không nhầm cùng package/module với cùng nest.
- [ ] Reflection discovery (`getDeclaredField`/`getDeclaredMethod`) được tách khỏi access/invoke.
- [ ] Dùng `canAccess` thay API `isAccessible` deprecated.
- [ ] Dùng `trySetAccessible` chỉ khi cần deep access và có hợp đồng module/security rõ.
- [ ] Không giả định `exports` tương đương `opens`.
- [ ] Với named modules, chỉ mở package đúng framework/module cần quyền khi được duyệt.
- [ ] Tạo `MethodHandles.lookup()` ở caller thật sự có quyền, không phải helper ngẫu nhiên.
- [ ] Chỉ dùng `privateLookupIn` với Lookup có PRIVATE+MODULE và ranh giới package/module cho phép.
- [ ] Không coi `Lookup.in` là công cụ tự cấp private privileges.
- [ ] Không truyền `MethodHandle` hoặc `Lookup` privileged tới code không tin cậy.
- [ ] Xử lý `IllegalAccessException`, `InaccessibleObjectException` và `WrongMethodTypeException` đúng nguồn.
- [ ] Nếu dùng `invokeExact`, xác minh type chính xác của receiver/parameters/return.
- [ ] Có test cùng nest, ngoài nest, unnamed module, named module exports-only và opens.
- [ ] Không dùng cờ bypass JDK internals đã lỗi thời; ưu tiên public APIs ổn định.
- [ ] Không sửa class/module accessibility chỉ vì một test vô tình chạy trên classpath.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Hai class cùng package và cùng module có chắc thuộc cùng nest không?

**Không.** Nest membership dựa trên thông tin runtime của JVM và `NestHost`/`NestMembers`. Hai top-level classes độc lập có thể cùng package nhưng không phải nestmates.

**Câu 2.** Với Java 11, một nested member class đọc private field của enclosing host có phải bật `setAccessible(true)` không?

**Không**, khi member là nestmate hợp lệ. JVM cho phép private access trong cùng nest, và Reflection/MethodHandles có thể áp dụng quyền này.

**Câu 3.** `Class.getDeclaredField("secret")` không ném exception nhưng `Field.get(instance)` ném `IllegalAccessException`; có mâu thuẫn không?

**Không.** Tìm metadata và dùng member là hai công đoạn với access checks khác nhau.

**Câu 4.** `Field.canAccess(instance) == true` có chứng minh accessible flag đã được bật không?

**Không.** Caller có thể đã đủ quyền, ví dụ là nestmate, dù chưa suppress access checks.

**Câu 5.** Vì sao `AccessibleObject.isAccessible()` không nên dùng để kiểm permission?

**Vì** nó đã deprecated và chỉ trả flag suppressing access checks; API hiện hành là `canAccess(...)`.

**Câu 6.** Named module `lib.model` `exports demo.model`, nhưng không `opens`. Một module khác có thể dùng `privateLookupIn(Vault.class, lookup)` để đọc private field không?

**Không**, nếu thiếu package openness tương ứng. `exports` không tự cấp deep reflection tới private members.

**Câu 7.** Nếu thêm `opens demo.model to app.runner`, hai class `Vault` và `Main` có trở thành nestmates không?

**Không.** Chỉ thay quyền deep reflection cho `app.runner`, không thay metadata nest.

**Câu 8.** `MethodHandles.lookup()` gọi từ `ExternalProbe` có tự có quyền private của `NestAccessDemo` không?

**Không.** Lookup gắn với caller `ExternalProbe`. Trong demo nó bị từ chối, nhưng `privateLookupIn` có thể thành công khi module policy cho phép.

**Câu 9.** Có nên gửi một private MethodHandle cho plugin không tin cậy vì “nó chỉ là object”?

**Không.** Handle là **capability đã được kiểm quyền lúc tạo**; plugin nhận nó có thể invoke ngay cả khi plugin không tự tạo được handle tương ứng.

**Câu 10.** Dùng `invokeExact(target)` với return type không khớp có gây lỗi access không?

**Không nhất thiết.** Nó thường dẫn tới `WrongMethodTypeException`; handle có thể đã được tạo hợp lệ và quyền truy cập hoàn toàn đúng.

## 21. Tài liệu chính thức và kiến thức còn áp dụng

1. [OpenJDK JEP 181 — Nest-Based Access Control](https://openjdk.org/jeps/181): thay đổi JVM access checks từ Java 11, metadata `NestHost`/`NestMembers` và lợi ích tránh synthetic accessors.
2. [Java SE 11 — `Class`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Class.html): `getNestHost()`, `getNestMembers()`, `isNestmateOf(...)`.
3. [Java SE 11 — `AccessibleObject`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `canAccess`, `trySetAccessible`, `setAccessible`, cách module openness ảnh hưởng deep reflection.
4. [Java SE 11 — `Field`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/reflect/Field.html): `getInt`, `get`, `set`, access checking.
5. [Java SE 11 — `Method`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/reflect/Method.html): `invoke`, `InvocationTargetException` và access control.
6. [Java SE 11 — `MethodHandles`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/MethodHandles.html): `lookup`, `publicLookup`, `privateLookupIn`.
7. [Java SE 11 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): lookup class, lookup modes, `findGetter`/`findVirtual`, access-check timing và nestmate access.
8. [Java SE 11 — `MethodHandle`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/MethodHandle.html): `invokeExact`, method type và capability security.
9. [Java SE 11 — `Module`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Module.html): readability/exports/opens.
10. [Java SE 11 — Java Platform Module System](https://docs.oracle.com/en/java/javase/11/docs/specs/jls/jls-7.html#jls-7.7): `module-info.java`, `requires`, `exports`, `opens`.
11. [Java SE 26 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): các nguyên tắc lookup/private access/nestmates vẫn được hỗ trợ trên JDK hiện đại.
12. [Java SE 26 — `AccessibleObject`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/AccessibleObject.html): API `canAccess`/`trySetAccessible` tiếp tục được dùng thay `isAccessible` deprecated.

**Ghi nhớ:** Java 11 đưa **nest-based access** vào JVM để các lớp cùng nest truy cập private của nhau. **Reflection** kiểm quyền khi dùng member và có `canAccess`/`trySetAccessible`; **MethodHandles.Lookup** kiểm quyền khi tạo handle, với quyền gắn vào caller/lookup modes. **exports ≠ opens**, `privateLookupIn` không bỏ qua module rules, và MethodHandle/Lookup privileged là capability cần được bảo vệ. Tách đúng ba lớp khái niệm **nest membership → access check → module openness** sẽ giúp bạn viết reflection và MethodHandles an toàn, hoạt động trên JDK hiện đại.