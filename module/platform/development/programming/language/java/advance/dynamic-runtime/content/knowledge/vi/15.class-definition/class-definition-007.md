# 15.7. Truy cập thành phần lớp ẩn bằng Lookup trả về và MethodHandle

## Mục tiêu

Bài học thuộc Java Advance – dynamic-runtime, mục **15. Định nghĩa lớp**. Sau khi học, bạn có thể:

- Nêu đúng đặc điểm của hidden class và giải thích tại sao không thể lấy lại một hidden class bằng cách ghép tên rồi gọi `Class.forName`.
- Dùng `MethodHandles.Lookup.defineHiddenClass` từ class-file bytes hợp lệ và giữ **Lookup được trả về** thay vì chỉ lưu một chuỗi tên.
- Dùng `lookupClass()`, `findConstructor`, `findVirtual`, `findStatic`, `findGetter` và `findSetter` để làm việc với constructor, field, method **private** của lớp ẩn.
- Chuyển `MethodHandle` có receiver là một runtime class không thể gọi tên trực tiếp trong source thành handle có chữ ký `Object` hoặc interface thông qua `asType`.
- Phân biệt quyền private mà returned Lookup có đối với chính hidden class với quyền truy cập private của **lớp chủ (host)** khi có/không có `ClassOption.NESTMATE`.
- Phân biệt định nghĩa class, khởi tạo class (`initialize` / `ensureInitialized`), danh tính class, và lựa chọn lifetime với `ClassOption.STRONG`.
- Chẩn đoán lỗi lookup, classfile, package/module, `WrongMethodTypeException`, lỗi cast, và `IllegalAccessError` bên trong bytecode target.
- Thiết kế cache và kiểm soát phạm vi quyền truy cập, không coi hidden class như một sandbox cho bytecode không tin cậy.

Ví dụ được viết cho **Java 17+**, có lệnh biên dịch và stdout rõ ràng. Các đoạn có nhãn *fragment* chỉ minh họa API và không chạy độc lập; hai chương trình hoàn chỉnh dùng Java source tự chứa, không cần ASM/Byte Buddy.

## 1. Lớp ẩn giải quyết vấn đề gì?

Một framework runtime có thể muốn tạo implementation riêng cho một lời gọi hoặc một dạng dữ liệu. Implementation đó cần một `Class<?>` thực và có thể có constructor, field, instance/static method. Tuy nhiên, framework không muốn tên của implementation trở thành một điểm liên kết bằng tên nhị phân dành cho `Class.forName`, loader hoặc code bên ngoài.

Java có **hidden class**: class được định nghĩa ở runtime, không thể tìm theo tên bằng cơ chế class lookup thông thường, nhưng **vẫn là một class thật** và vẫn thực thi bytecode Java có access checks.

~~~text
Trusted class-file bytes
        |
        v
Lookup của code được quyền định nghĩa
        |
        | defineHiddenClass(bytes, initialize, options)
        v
Lookup trả về (lookupClass = lớp ẩn mới)
        |
        +--> lookupClass() --------> Class<?> hiddenType
        |
        +--> findConstructor() ----> MethodHandle để tạo instance
        |
        +--> findVirtual() --------> MethodHandle cho instance method
        |
        +--> findStatic() ---------> MethodHandle cho static method
        |
        +--> findGetter/Setter() --> MethodHandle cho field
~~~

Điểm quan trọng: **`defineHiddenClass` trả về `MethodHandles.Lookup`, không trả trực tiếp một `Class<?>`**. Returned Lookup chính là “chìa khóa” cho phần lớn các thao tác mà bài này cần.

### 1.1. Hidden class không có nghĩa là class không thể tương tác

Một hidden class:

- Có đối tượng `Class<?>` được truy xuất bằng `returnedLookup.lookupClass()`.
- Có thể tạo instance, gọi method, đọc/ghi field nếu dùng đúng `MethodHandle` và đủ quyền.
- Có thể implement interface mà ứng dụng biết trước; khi đó có thể tương tác với instance qua interface đó.
- Có thể chứa member `private`, `public`, `static`, hoặc instance member như class thông thường, trong phạm vi classfile hợp lệ.
- Có thể được định nghĩa nhiều lần từ **cùng một mảng bytes**, tạo **những runtime classes khác nhau**.
- Không cho phép code lấy lại class bằng `Class.forName(hiddenType.getName())`. Một tên runtime có hậu tố đặc biệt không phải binary name dùng để load thông thường.

Hidden class không phải “một phiên bản khác của private nested class”. Một private nested class bình thường vẫn có binary name và classfile riêng; `private` quyết định **quyền truy cập**, còn `hidden` là đặc điểm **cách class được định nghĩa và tìm kiếm trong JVM**.

### 1.2. Không phải sandbox

Nạp và chạy hidden class là chạy bytecode JVM. Tính chất “không tìm bằng tên” **không tự giới hạn** I/O, network, CPU, truy cập tài nguyên hoặc các side effects của code. Chỉ định nghĩa bytecode tin cậy hoặc có cơ chế kiểm soát an toàn độc lập. Không xây API cho người dùng tùy ý gửi bytes rồi tin rằng chữ “hidden” đã cô lập code độc hại.

## 2. API `defineHiddenClass` và returned Lookup

Chữ ký trung tâm:

~~~java
// Chữ ký API rút gọn để tra cứu, không phải một chương trình độc lập:
MethodHandles.Lookup defineHiddenClass(
        byte[] bytes,
        boolean initialize,
        MethodHandles.Lookup.ClassOption... options)
        throws IllegalAccessException;
~~~

| Thành phần | Ý nghĩa | Điều phải kiểm chứng |
| --- | --- | --- |
| `bytes` | Nội dung **class-file bytes**, không phải Java source | Class file hợp lệ, đúng package/context, tương thích JVM |
| `initialize` | Có yêu cầu khởi tạo class ngay trong lúc định nghĩa hay không | Phân biệt define với chạy static initializer |
| `options` | Tùy chọn `NESTMATE`, `STRONG` | Quyền nest và lifetime; không phải quyền tùy ý |
| Returned `Lookup` | Có `lookupClass()` là hidden class mới | Giữ quyền cần dùng hoặc lấy handles trước khi bỏ lookup |

**Điều kiện quyền quan trọng:** `Lookup` gọi `defineHiddenClass` cần **full privilege access**. Bytecode dùng để định nghĩa phải có class thuộc **cùng package phù hợp với lookup class**, theo hợp đồng của API. Không lấy `MethodHandles.publicLookup()` rồi dùng nó để định nghĩa class private trong package/module bất kỳ.

Một quy trình minh họa:

~~~java
// Fragment: classBytes là class-file bytes đáng tin, hợp lệ trong đúng package.
MethodHandles.Lookup defining = MethodHandles.lookup();
MethodHandles.Lookup hiddenLookup =
        defining.defineHiddenClass(classBytes, false);
Class<?> hiddenType = hiddenLookup.lookupClass();
~~~

Ba biến có chức năng khác nhau:

1. `defining` đại diện context quyền **của class đang gọi**.
2. `hiddenLookup` là Lookup **mới**, có lookup class chính là hidden class vừa được tạo; nó có quyền private đối với hidden class theo API.
3. `hiddenType` là runtime Class object đúng của hidden class; đó **không** phải một tên có thể lưu rồi dùng `Class.forName`.

`lookupClass()` giúp đưa chính Class object vào `findConstructor`/`findVirtual`. Từ đó ta có thể dùng MethodHandle để gọi member mà Java source không thể gọi bằng tên hidden class.

### 2.1. Tại sao cần giữ returned Lookup?

Giả sử bạn tạo xong hidden class rồi chỉ lưu `hiddenType.getName()`. Code khác cố làm:

~~~java
// Fragment SAI về cách tìm hidden class:
Class<?> type = Class.forName(hiddenType.getName());
~~~

Hidden class không thể được tìm bằng tên như vậy. Ngược lại, giữ `hiddenLookup` hoặc ít nhất giữ `hiddenType` và các MethodHandle đã tạo sẽ giữ được reference runtime cần thiết. API `Lookup` còn xác định **quyền** khi tìm private members, chứ không chỉ cung cấp tên class.

### 2.2. Returned Lookup là một capability

`Lookup` không chỉ là metadata; nó cho phép code sở hữu nó tìm các member trong phạm vi access modes tương ứng. Returned Lookup từ `defineHiddenClass` mang quyền với **private members của hidden class**. Nếu chuyển Lookup này cho code bên ngoài, bạn có thể vô tình mở các implementation details không muốn công khai.

Nên phân tách:

~~~text
Trusted runtime component:
    defineHiddenClass -> hidden Lookup
    -> findConstructor/findVirtual/findStatic...
    -> tạo interface hoặc adapted MethodHandle cần thiết

Client code:
    nhận interface / một MethodHandle có chữ ký đã thiết kế
    không mặc nhiên nhận full-privilege Lookup
~~~

Ngay cả MethodHandle được xuất bản cũng là một callable capability: method bên trong có thể có side effects. Đừng xuất bản handle tới private method nếu code ngoài không được phép thực hiện thao tác đó.

## 3. Tạo bytes cho bài thực hành mà không cần thư viện ngoài

Để tập trung vào `Lookup` và `MethodHandle`, ta sẽ biên dịch **một file Java chứa hai top-level classes**:

~~~text
HiddenMembersDemo.java --javac--> HiddenMembersDemo.class
                                  SecretBlueprint.class
~~~

`SecretBlueprint` là bản mẫu bình thường, có:

- Constructor private nhận `int`.
- Field private `int code`.
- Instance method private `String describe(String)`.
- Static method private `String label()`.

Chương trình sẽ đọc bytes của `SecretBlueprint.class` bằng `getResourceAsStream` rồi dùng `defineHiddenClass` để JVM định nghĩa **một hidden class mới**. Class này khác với `SecretBlueprint.class` thường, mặc dù xuất phát từ cùng classfile bytes.

Cách làm này giúp ví dụ tự chứa; trong hệ thống thật, bytes có thể đến từ một code generator **đáng tin**. Không đọc Java source text rồi truyền trực tiếp vào `defineHiddenClass`; API nhận **class-file bytes đã biên dịch**.

## 4. Ví dụ hoàn chỉnh 1: truy cập private constructor, field và method

Lưu file **HiddenMembersDemo.java**:

~~~java
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Objects;

public class HiddenMembersDemo {
    private static byte[] bytesOf(String resource) throws Exception {
        try (InputStream stream = HiddenMembersDemo.class.getResourceAsStream(resource)) {
            return Objects.requireNonNull(stream, resource).readAllBytes();
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup owner = MethodHandles.lookup();
        byte[] classBytes = bytesOf("SecretBlueprint.class");
        MethodHandles.Lookup hiddenLookup = owner.defineHiddenClass(classBytes, false);
        Class<?> hiddenType = hiddenLookup.lookupClass();

        System.out.println("hidden=" + hiddenType.isHidden());
        System.out.println("nameHasSlash=" + hiddenType.getName().contains("/"));
        System.out.println("differentFromOrdinary=" + (hiddenType != SecretBlueprint.class));
        System.out.println("lookupClassMatches=" + (hiddenLookup.lookupClass() == hiddenType));
        System.out.println("fullPrivilege=" + hiddenLookup.hasFullPrivilegeAccess());
        try {
            Class.forName(hiddenType.getName());
        } catch (ClassNotFoundException ex) {
            System.out.println("classForName=" + ex.getClass().getSimpleName());
        }

        MethodHandle constructor = hiddenLookup.findConstructor(
                hiddenType, MethodType.methodType(void.class, int.class));
        MethodHandle createAsObject = constructor.asType(
                MethodType.methodType(Object.class, int.class));
        Object instance = (Object) createAsObject.invokeExact(41);
        System.out.println("instanceType=" + (instance.getClass() == hiddenType));

        MethodHandle getCode = hiddenLookup.findGetter(
                hiddenType, "code", int.class).asType(
                MethodType.methodType(int.class, Object.class));
        MethodHandle setCode = hiddenLookup.findSetter(
                hiddenType, "code", int.class).asType(
                MethodType.methodType(void.class, Object.class, int.class));
        MethodHandle describe = hiddenLookup.findVirtual(
                hiddenType, "describe",
                MethodType.methodType(String.class, String.class)).asType(
                MethodType.methodType(String.class, Object.class, String.class));
        MethodHandle label = hiddenLookup.findStatic(
                hiddenType, "label", MethodType.methodType(String.class));

        System.out.println("initialCode=" + (int) getCode.invokeExact(instance));
        System.out.println("initialText=" + (String) describe.invokeExact(instance, "!"));
        setCode.invokeExact(instance, 73);
        System.out.println("updatedCode=" + (int) getCode.invokeExact(instance));
        System.out.println("updatedText=" + (String) describe.invokeExact(instance, "?"));
        System.out.println("staticLabel=" + (String) label.invokeExact());

        try {
            owner.findVirtual(hiddenType, "describe",
                    MethodType.methodType(String.class, String.class));
        } catch (IllegalAccessException ex) {
            System.out.println("otherLookupPrivate=" + ex.getClass().getSimpleName());
        }
    }
}

final class SecretBlueprint {
    private int code;

    private SecretBlueprint(int code) {
        this.code = code;
    }

    private String describe(String suffix) {
        return "code=" + code + suffix;
    }

    private static String label() {
        return "hidden-private";
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 -encoding UTF-8 HiddenMembersDemo.java
java HiddenMembersDemo
~~~

**Stdout chính xác**:

~~~text
hidden=true
nameHasSlash=true
differentFromOrdinary=true
lookupClassMatches=true
fullPrivilege=true
classForName=ClassNotFoundException
instanceType=true
initialCode=41
initialText=code=41!
updatedCode=73
updatedText=code=73?
staticLabel=hidden-private
otherLookupPrivate=IllegalAccessException
~~~

### 4.1. Class hidden thực sự khác class bản mẫu

`hiddenType.isHidden()` là true. `hiddenType != SecretBlueprint.class` cũng true. Mỗi lời gọi `defineHiddenClass` tạo một **runtime class mới**, không phải một alias tới class thường có cùng bytes. Kết quả `lookupClassMatches=true` chứng minh Lookup trả về trỏ đúng Class object của lớp ẩn vừa định nghĩa.

`hiddenType.getName().contains("/")` trong thử nghiệm là true vì hidden class có tên runtime với hậu tố đặc biệt. **Không phụ thuộc vào chính chuỗi hậu tố hoặc địa chỉ trong tên**; nó có thể khác giữa JVM/lần chạy. `Class.forName(hiddenType.getName())` ném `ClassNotFoundException`: đó là đặc tính quan trọng của hidden class.

### 4.2. Tạo instance bằng private constructor

Method mẫu:

~~~java
// Fragment từ SecretBlueprint:
private SecretBlueprint(int code) {
    this.code = code;
}
~~~

Ta tìm constructor:

~~~java
// Fragment, hiddenLookup/hiddenType đã có:
MethodHandle constructor = hiddenLookup.findConstructor(
        hiddenType, MethodType.methodType(void.class, int.class));
~~~

**Chú ý hai loại MethodType**:

| Việc đang làm | Chữ ký |
| --- | --- |
| `MethodType` truyền vào `findConstructor` | `(int)void` |
| MethodHandle trả về sau khi tìm được constructor | `(int)HiddenType` |
| MethodHandle sau khi `asType(Object,int)` | `(int)Object` |

Đó là do constructor ở Java được mô tả bằng kiểu trả về `void` trong yêu cầu lookup, nhưng khi **invoke constructor handle** thì nhận một instance mới. Tìm constructor với return type `HiddenType` ngay trong request là một lỗi hay gặp.

Ta không thể viết literal Java type như `SecretBlueprint/0x...` trong source. Thay vào đó:

~~~java
// Fragment:
MethodHandle createAsObject = constructor.asType(
        MethodType.methodType(Object.class, int.class));
Object instance = (Object) createAsObject.invokeExact(41);
~~~

Đối tượng vẫn là instance của **hiddenType**, không bị chuyển thành một lớp Java khác. `asType` chỉ điều chỉnh chữ ký và conversions của handle. Do vậy `instance.getClass() == hiddenType` là true.

### 4.3. Đọc/ghi field private bằng Getter/Setter MethodHandle

Field mẫu:

~~~java
// Fragment:
private int code;
~~~

Hai phép tìm:

~~~java
// Fragment:
MethodHandle getter = hiddenLookup.findGetter(hiddenType, "code", int.class);
MethodHandle setter = hiddenLookup.findSetter(hiddenType, "code", int.class);
~~~

Chữ ký handle gốc:

~~~text
getter: (HiddenType)int
setter: (HiddenType,int)void
~~~

Trong code hoàn chỉnh, ta thích ứng receiver sang `Object`:

~~~java
// Fragment:
MethodHandle getCode = getter.asType(
        MethodType.methodType(int.class, Object.class));
MethodHandle setCode = setter.asType(
        MethodType.methodType(void.class, Object.class, int.class));
~~~

Phép gọi được `invokeExact` nhận `Object` compile-time nên đúng signature, còn adapter kiểm tra receiver runtime có thực sự là instance của hidden class hay không. `setCode.invokeExact(instance,73)` thay đổi field private, sau đó `getCode` trả 73.

**Không nên nhầm `findGetter` với `findStaticGetter`.** Nếu field là static, dùng API static tương ứng, không truyền receiver. Nếu field là `final`, không giả định Lookup có quyền set như một field mutable; các quy tắc field access và handle creation vẫn áp dụng.

### 4.4. Gọi private instance method bằng findVirtual

Phương thức mẫu:

~~~java
// Fragment:
private String describe(String suffix) {
    return "code=" + code + suffix;
}
~~~

Tìm handle:

~~~java
// Fragment:
MethodHandle raw = hiddenLookup.findVirtual(
        hiddenType, "describe",
        MethodType.methodType(String.class, String.class));
~~~

`MethodType` truyền vào `findVirtual` mô tả kiểu **của method được khai báo**, không bao gồm receiver. Handle trả về mới có receiver:

~~~text
findVirtual request:  (String)String
MethodHandle result:  (HiddenType,String)String
~~~

Ta điều chỉnh receiver để source gọi được:

~~~java
// Fragment:
MethodHandle adapted = raw.asType(
        MethodType.methodType(String.class, Object.class, String.class));
String result = (String) adapted.invokeExact(instance, "!");
~~~

Kết quả là `code=41!`. Sau khi field thay thành 73, `describe(instance,"?")` cho `code=73?`. Handle không phải một bản snapshot bất biến của field; nó gọi code của instance thật.

### 4.5. Gọi private static method bằng findStatic

Static method không cần receiver:

~~~java
// Fragment:
MethodHandle label = hiddenLookup.findStatic(
        hiddenType, "label", MethodType.methodType(String.class));
String text = (String) label.invokeExact(); // "hidden-private"
~~~

Với kiểu trả về và tham số đều viết được trong Java source, không cần adapter chỉ để ẩn receiver. Returned Lookup có private access với hidden class nên tìm method này thành công.

### 4.6. Một private method nhưng hai Lookup cho kết quả khác nhau

Ví dụ gọi:

~~~java
// Fragment, owner là Lookup ban đầu của HiddenMembersDemo:
owner.findVirtual(hiddenType, "describe",
        MethodType.methodType(String.class, String.class));
~~~

và nhận `IllegalAccessException`. Lý do: hidden class thứ nhất được định nghĩa **không có `NESTMATE`**, nên Lookup của chủ không được phép truy cập private member của class đó. Returned Lookup thì được vì lookupClass của nó **chính là hidden class**.

**Kết luận:** tìm private member là vấn đề **Lookup access rights**, không phải chỉ cần giữ một `Class<?>` là có thể gọi mọi member. Đừng dùng `setAccessible` để che mất thiếu sót thiết kế quyền khi returned Lookup đã cung cấp đường chính thức.

## 5. asType, invokeExact và receiver không có tên source

### 5.1. MethodHandle vẫn giữ runtime type chính xác

Trong chương trình, kiểu gốc của các handle vẫn nhắc tới **hiddenType thực sự**:

| Handle | Signature nguyên thủy |
| --- | --- |
| Constructor | `(int)HiddenType` |
| Getter `code` | `(HiddenType)int` |
| Setter `code` | `(HiddenType,int)void` |
| Instance method `describe` | `(HiddenType,String)String` |
| Static method `label` | `()String` |

`HiddenType` là cách ghi chú minh họa, không phải tên class có thể gõ vào Java source. Chữ ký MethodHandle thực sự chứa `Class<?>` runtime của hidden class trong `MethodType`.

Nếu source chỉ có `Object instance`, gọi thẳng `raw.invokeExact(instance,"!")` với static signature `(Object,String)String` sẽ **không khớp** handle gốc `(HiddenType,String)String`. `invokeExact` yêu cầu trùng chữ ký call site, kể cả return type.

### 5.2. Adapter là cầu nối kiểu, không phải bỏ qua quyền

`MethodHandle.asType` có thể tạo một handle mới chấp nhận `Object`, rồi **cast reference theo runtime** tới hidden class khi gọi. Nhờ vậy:

~~~java
// Fragment:
MethodHandle adapted = raw.asType(
        MethodType.methodType(String.class, Object.class, String.class));
String answer = (String) adapted.invokeExact((Object) instance, "!");
~~~

Đoạn trên đúng khi `instance` thật là instance của hidden class. Nếu truyền một `new Object()` hoặc instance của **một hidden class khác tạo từ cùng bytes**, adapter có thể ném `ClassCastException`. `asType` không biến object thành instance của class khác và không thay đổi access rights của raw handle.

### 5.3. Vậy invokeWithArguments có dùng được không?

Có, khi bạn không thể xác định signature cần gọi tại thời điểm biên dịch:

~~~java
// Fragment: raw là instance method handle của hidden class.
Object created = constructor.invokeWithArguments(41);
Object result = raw.invokeWithArguments(created, "!");
~~~

`invokeWithArguments` chấp nhận nhiều tham số kiểu `Object` và thực hiện conversions/runtime adaptation cần thiết; nó có thể tạo boxing và overhead trên đường gọi thường xuyên. Với code generation hoặc dispatcher “hot path”, nên **tạo và cache adapter một lần** rồi thử `invokeExact` với chữ ký rõ ràng, đo bằng benchmark thật (ví dụ JMH) thay vì khẳng định luôn nhanh hơn.

### 5.4. Những lỗi chữ ký cần nhận biết

- `WrongMethodTypeException`: call-site descriptor không khớp `MethodHandle.type()` hoặc không thể thích ứng theo phép chuyển đổi yêu cầu. Kể cả return type cũng phải đúng.
- `ClassCastException`: reference chuyển sang hidden class không tương thích trong adapter/call path.
- `NullPointerException`: có thể xảy ra khi gọi instance method trên receiver null hoặc code target tự ném lỗi.
- `NoSuchMethodException`: `findConstructor`/`findVirtual`/`findStatic` không tìm được signature requested.
- `IllegalAccessException`: Lookup đang dùng không có quyền member access thích hợp.
- Exception do code hidden method ném: khác với lỗi lookup. Không nên bắt tất cả thành “không tìm thấy class”.

Một debug sequence ngắn:

~~~text
1. Kiểm tra hiddenLookup.lookupClass().isHidden().
2. In hiddenType + method parameter/return types (đừng hardcode runtime name).
3. Kiểm tra member thật và chữ ký đã yêu cầu.
4. In rawHandle.type() trước khi gọi.
5. In adaptedHandle.type() sau asType.
6. Đối chiếu signature tại chỗ invokeExact (cả return).
7. Kiểm tra receiver được tạo bởi đúng hidden class thế hệ đó.
8. Phân biệt lỗi findXxx với lỗi chạy bytecode trong target.
~~~

## 6. NESTMATE: hai hướng private access khác nhau

Điểm dễ nhầm nhất là coi returned Lookup và `ClassOption.NESTMATE` làm cùng việc. Thực tế chúng xử lý **hai ranh giới khác nhau**.

| Quan hệ | Cơ chế | Ví dụ |
| --- | --- | --- |
| Code chủ tìm private member **của hidden class** | Returned Lookup có private access với lớp mới | `hiddenLookup.findVirtual(hiddenType, "describe", ...)` |
| Bytecode **của hidden class** muốn truy cập private member **của host class** | Cần quan hệ nest/access hợp lệ; có thể dùng `ClassOption.NESTMATE` | Hidden method đọc `private static String token` của host |
| Client ít tin cậy muốn gọi một member nhất định | Chỉ xuất bản MethodHandle/interface đã chọn | Không phát tán returned Lookup bừa bãi |

`ClassOption.NESTMATE` gắn hidden class mới vào **nest của lookup class** theo quy tắc API. Khi đó Java private access trong cùng nest có thể hoạt động phù hợp. Không có tùy chọn này, việc cùng package thường **chưa đủ** cho private field/method của host.

Cũng không được hiểu `NESTMATE` là “được phép truy cập bất kỳ package/module nào”. `defineHiddenClass` vẫn yêu cầu Lookup đủ quyền, bytes hợp lệ, package đúng và các điều kiện liên quan.

## 7. Ví dụ hoàn chỉnh 2: NESTMATE và initialization

Chương trình dưới tạo hidden class từ bytecode của một nested class `HiddenNestDemo.Template`. Method private `readOwnerToken()` bên trong nó truy cập field private `HiddenNestDemo.token`. Ta cố ý khai báo field **không final** để phép đọc không bị javac constant-fold.

Lưu file **HiddenNestDemo.java**:

~~~java
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Objects;

public class HiddenNestDemo {
    private static String token = "nest-secret";
    private static int initEvents;

    public static void recordInit() {
        initEvents++;
    }

    private static byte[] templateBytes() throws Exception {
        try (InputStream stream = HiddenNestDemo.class.getResourceAsStream(
                "HiddenNestDemo$Template.class")) {
            return Objects.requireNonNull(stream).readAllBytes();
        }
    }

    static final class Template {
        static {
            HiddenNestDemo.recordInit();
        }

        private static String readOwnerToken() {
            return token;
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup hostLookup = MethodHandles.lookup();
        byte[] bytes = templateBytes();

        MethodHandles.Lookup deferred = hostLookup.defineHiddenClass(
                bytes, false, MethodHandles.Lookup.ClassOption.NESTMATE);
        Class<?> hiddenClass = deferred.lookupClass();
        System.out.println("isHidden=" + hiddenClass.isHidden());
        System.out.println("nestmate=" + hiddenClass.isNestmateOf(HiddenNestDemo.class));
        System.out.println("initBefore=" + initEvents);
        deferred.ensureInitialized(hiddenClass);
        System.out.println("initAfterEnsure=" + initEvents);

        MethodHandle read = deferred.findStatic(hiddenClass, "readOwnerToken",
                MethodType.methodType(String.class));
        System.out.println("ownerPrivate=" + (String) read.invokeExact());

        MethodHandles.Lookup immediate = hostLookup.defineHiddenClass(
                bytes, true, MethodHandles.Lookup.ClassOption.NESTMATE);
        System.out.println("distinctHiddenClass="
                + (immediate.lookupClass() != hiddenClass));
        System.out.println("initAfterImmediate=" + initEvents);

        MethodHandles.Lookup noNest = hostLookup.defineHiddenClass(bytes, false);
        System.out.println("noNestmate="
                + !noNest.lookupClass().isNestmateOf(HiddenNestDemo.class));
        try {
            MethodHandle readNoNest = noNest.findStatic(
                    noNest.lookupClass(), "readOwnerToken",
                    MethodType.methodType(String.class));
            System.out.println((String) readNoNest.invokeExact());
        } catch (IllegalAccessError ex) {
            System.out.println("accessWithoutNest=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 -encoding UTF-8 HiddenNestDemo.java
java HiddenNestDemo
~~~

**Stdout chính xác**:

~~~text
isHidden=true
nestmate=true
initBefore=0
initAfterEnsure=1
ownerPrivate=nest-secret
distinctHiddenClass=true
initAfterImmediate=2
noNestmate=true
accessWithoutNest=IllegalAccessError
~~~

### 7.1. Vì sao bản NESTMATE chạy được?

Hidden class được định nghĩa với `ClassOption.NESTMATE` nằm cùng nest với `HiddenNestDemo`; `isNestmateOf` trả true. Returned Lookup truy cập được method private **thuộc hidden class**. Khi method này chạy và đọc `token` (private field của host), quan hệ nest phù hợp giúp phép đọc thành công, trả `nest-secret`.

Đừng nghĩ `readOwnerToken` và `token` cùng một class. Chúng thuộc **hai class khác nhau** nhưng có thể truy cập private nhờ nest membership do option tạo. Nếu thiết kế runtime generator cần truy cập host private để tối ưu, phải xác định rõ vì sao quyền đó phù hợp với trusted code.

### 7.2. Vì sao bản không có NESTMATE thất bại?

Phần cuối code định nghĩa hidden class thứ ba:

~~~java
// Fragment:
MethodHandles.Lookup noNest = hostLookup.defineHiddenClass(bytes, false);
~~~

Với returned Lookup này, `findStatic(hiddenClass, "readOwnerToken",...)` **vẫn có thể thành công**, bởi method được tìm là private member của **chính hidden class**. Tuy nhiên, khi invoke method, bytecode của method cố truy cập `private static String token` trong host, lúc đó thiếu quyền nest và ném **`IllegalAccessError`**.

Đây là khác biệt rất có ích:

- `IllegalAccessException` thường xảy ra khi **Lookup tìm member** mà quyền không đủ.
- `IllegalAccessError` trong ví dụ xảy ra khi **bytecode thực thi phép truy cập member không hợp lệ**.

Thử nghiệm bắt `IllegalAccessError` để minh họa chính xác; code nghiệp vụ bình thường không nên nuốt lỗi linkage/access rồi cố tiếp tục như không có gì.

### 7.3. Tại sao token không thể là compile-time constant trong thí nghiệm?

Nếu khai báo:

~~~java
// Fragment KHÔNG phù hợp khi muốn đo quyền getstatic:
private static final String TOKEN = "nest-secret";
~~~

thì `TOKEN` là một **compile-time constant**. Javac có thể thay phép truy cập field bằng literal trong method của template. Kết quả “không NESTMATE mà vẫn in nest-secret” có thể chỉ phản ánh **không hề có thao tác getstatic tới private field**. Đó không phải bằng chứng access controls bị bỏ qua.

Ví dụ dùng `private static String token` không final, nên bytecode thực sự cần truy cập member của host. Khi kiểm chứng quyền giữa class, hãy dùng field không bị constant-fold hoặc xem output `javap -c` để xác nhận lệnh access thực tế.

## 8. initialize=false, ensureInitialized, initialize=true

Định nghĩa class và khởi tạo class là **hai giai đoạn**.

Trong ví dụ 2, `Template` có static initializer gọi `HiddenNestDemo.recordInit()`:

~~~java
// Fragment từ Template:
static {
    HiddenNestDemo.recordInit();
}
~~~

Chương trình tạo hidden class đầu tiên với `initialize=false`:

~~~java
// Fragment:
MethodHandles.Lookup deferred =
        hostLookup.defineHiddenClass(bytes, false,
                MethodHandles.Lookup.ClassOption.NESTMATE);
~~~

Ngay sau define, `initEvents=0`. Sau đó:

~~~java
// Fragment:
deferred.ensureInitialized(deferred.lookupClass());
~~~

ép khởi tạo hidden class đó; static initializer chạy một lần, `initEvents=1`.

Tiếp theo code gọi `defineHiddenClass(bytes,true,NESTMATE)` lần thứ hai. Vì đó là **một class mới**, static initializer của class thứ hai chạy riêng ngay trong quá trình định nghĩa, khiến `initEvents=2`.

**Không diễn giải `initialize=false` là “không bao giờ khởi tạo”.** Việc sử dụng chủ động sau này như gọi static method, tạo instance hoặc `ensureInitialized` có thể kích hoạt class initialization theo quy tắc JVM. Cũng không nên nhầm đọc file `Template.class` bằng `getResourceAsStream` với việc khởi tạo class bản mẫu thông thường.

### 8.1. Vì sao static state của hai hidden classes độc lập?

Khi gọi cùng bytes nhiều lần:

~~~text
defineHiddenClass(bytes, false, NESTMATE) -> HiddenA
defineHiddenClass(bytes, true,  NESTMATE) -> HiddenB

HiddenA != HiddenB

Mỗi class có class initialization và static storage riêng.
~~~

Các đối tượng `Class<?>` riêng này không phải alias, dù cùng logical template. Trong ví dụ, cả hai static initializers đều gọi **method của host** tăng một bộ đếm chung, vì thế ta quan sát được hai lần khởi tạo.

Nếu bạn cần một singleton logical implementation, phải thiết kế cache/canonicalization riêng; `defineHiddenClass` không tự gộp cùng bytes thành một class duy nhất.

## 9. Hidden class identity và MethodHandle identity

Một vấn đề lớn khi làm runtime class generation là **không được trộn instance/handle giữa các class generations**.

Giả sử:

~~~java
// Fragment: defining và bytes đã được chuẩn bị.
MethodHandles.Lookup a = defining.defineHiddenClass(bytes, false);
MethodHandles.Lookup b = defining.defineHiddenClass(bytes, false);
boolean same = a.lookupClass() == b.lookupClass(); // false
~~~

Cùng classfile bytes nhưng **runtime identity khác nhau**:

- Constructor handle của HiddenA tạo instance HiddenA.
- Instance method handle của HiddenA mong receiver HiddenA.
- Instance của HiddenB không tự nhiên là instance HiddenA.
- Một adapter dùng `Object` receiver vẫn cast về hidden type **chính xác** nằm trong handle gốc.
- `Class.isInstance` và `Class.cast` chỉ hoạt động nếu object có quan hệ runtime type đúng.

Do đó, nên cache cả `Class<?>`, các MethodHandle và metadata tương ứng **theo cùng một entry**. Không lấy raw handle của một phiên bản rồi áp dụng vào instance của phiên bản khác chỉ vì cùng tên gốc classfile.

### 9.1. Không lưu runtime name làm key bền vững

`Class.getName()` của hidden class thường có hậu tố do JVM tạo, ví dụ chứa `/0x...`. Đây không phải stable identifier. Không serialize tên để lần sau `Class.forName`, không tự parse suffix và không đưa tên đó thành contract cho người dùng.

Nếu cần registry runtime, dùng **logical key do ứng dụng định nghĩa**:

~~~text
Plugin ID + implementation version
         |
         v
Cache entry
  - returned Lookup (nếu còn cần tra cứu)
  - Class<?> hiddenType
  - constructor MethodHandle
  - private business MethodHandles
  - lifecycle / validation metadata
~~~

Dùng logical key để tra entry, không dùng generated runtime name. Khi phiên bản code thay đổi, tạo entry mới rồi chuyển routing có kiểm soát.

### 9.2. STRONG và vấn đề unloading

`ClassOption.STRONG` ảnh hưởng lifetime của hidden class:

| Chế độ | Đặc tính tổng quát |
| --- | --- |
| Không có `STRONG` | Hidden class thường có thể unload độc lập với defining class loader khi không còn reachable references phù hợp |
| Có `STRONG` | Lifetime gắn mạnh hơn với defining class loader; không mong unload độc lập như weak hidden class |

Không có bảo đảm GC sẽ unload ngay sau khi một biến local hết scope. `Lookup`, `MethodHandle`, `Class<?>`, `MethodType`, instance hoặc cache còn sống có thể giữ các đối tượng liên quan. Một cache static giữ hàng nghìn entries sẽ làm tăng pressure lên metadata/metaspace kể cả khi không có `STRONG`.

**Quyết định đúng:** chọn lifecycle/caching theo yêu cầu của runtime, kiểm tra memory thực tế. Không dùng `STRONG` chỉ để “an toàn hơn” nếu không có yêu cầu lifetime cụ thể.

## 10. Package, module, quyền và tính tin cậy của bytecode

### 10.1. Đúng package không có nghĩa được truy cập mọi private member

`defineHiddenClass` yêu cầu bytecode thuộc package thích hợp của lookup class; điều này không mở tất cả private members trong cùng package. Java private vẫn cần quyền private của chính class hoặc nest/access hợp lệ.

- Returned Lookup được tạo để truy cập hidden class mới.
- `NESTMATE` có thể cho phép bytecode hidden class tham gia nest của host.
- Không có `NESTMATE`, code hidden vẫn có thể đọc public/package-private members theo access rules, nhưng không mặc nhiên đọc host private.
- Module boundaries không bị bỏ qua chỉ vì một class là hidden.

### 10.2. Đừng dùng publicLookup() như công cụ bypass

`MethodHandles.publicLookup()` có phạm vi truy cập public; không cung cấp full privilege cần để định nghĩa hidden class. Cả `privateLookupIn` cũng có điều kiện module openness và quyền của caller; nó không phải master key.

Hãy xác định code component nào sở hữu class bytes, package nào được phép tạo runtime code, và Lookup nào có quyền thích hợp. Tránh truyền Lookup quyền cao qua các lớp abstraction mà chỉ cần một MethodHandle cụ thể.

### 10.3. Khi bytecode bị lỗi

Các nhóm lỗi chính:

| Giai đoạn | Dạng lỗi có thể gặp | Điều cần kiểm tra |
| --- | --- | --- |
| Đọc resource | `NullPointerException` từ requireNonNull | File `.class` có được build/đóng gói đúng không? |
| Define | `IllegalAccessException` | Full privilege Lookup, module/context |
| Define | `IllegalArgumentException` | Tên package bytes không phù hợp hoặc input/options vi phạm điều kiện API |
| Verify/link | `ClassFormatError`, `VerifyError`, `LinkageError` hoặc lỗi liên quan | Classfile bytes, target version, constant pool, dependency |
| Find member | `NoSuchMethodException` / `NoSuchFieldException` | Tên, kiểu return/parameter, static vs instance |
| Find member | `IllegalAccessException` | Lookup access quyền |
| Invoke | `WrongMethodTypeException` / `ClassCastException` | Descriptor, adapter, receiver runtime identity |
| Invoke hidden code | `IllegalAccessError` | Bytecode target tự truy cập member ngoài quyền |
| Initialize | Lỗi từ static initializer | Side effects, dependency, exception trong init |

Không nên gom mọi lỗi thành “không tìm thấy class”. Tách **resource**, **define**, **lookup**, **invoke**, **business exception** để việc chẩn đoán và xử lý có ý nghĩa.

### 10.4. Tạo hidden class từ input người dùng có an toàn không?

**Không mặc định.** Hidden class không cung cấp sandbox. Nếu bytecode không đáng tin, nó có thể thực thi các thao tác được phép bởi runtime context và gây tác động bên ngoài. Hệ thống chạy plugin tùy ý cần cơ chế bảo vệ ở cấp cao hơn: policy kiểm định, isolation, quyền thực thi và quản lý resource. Việc ẩn tên class không đủ để thay thế các cơ chế ấy.

## 11. Cache, concurrency và hiệu năng

### 11.1. Định nghĩa class không phải thao tác per-request rẻ

`defineHiddenClass` tạo một class identity mới. Nếu mỗi request đều tạo lại từ cùng bytes, framework có thể tốn class metadata, JIT warmup và công sức quản lý vòng đời. Đường thường hợp lý:

~~~text
1. Xác định logical implementation key.
2. Tìm cache entry đã có và còn hợp lệ.
3. Nếu thiếu, lấy classfile bytes tin cậy.
4. defineHiddenClass một lần cho key/version.
5. Lấy returned Lookup + Class<?>.
6. find private members và asType adapter một lần.
7. Cache entry cùng quyền/lifecycle phù hợp.
8. Các request sau gọi cached MethodHandle.
9. Evict khi không dùng nữa, tránh giữ reference vô hạn.
~~~

Nếu nhiều thread cùng muốn định nghĩa key, cần cơ chế tránh race: nếu cùng bytes được define song song, JVM vẫn tạo các class identity khác nhau. Cache phải quản lý initialization/failures theo đúng nhu cầu, không chỉ gọi `computeIfAbsent` rồi bỏ qua lỗi khởi tạo.

### 11.2. Getter/Setter MethodHandle không làm field thành volatile

Trong ví dụ 1, `code` là một `int` mutable bình thường. Dùng `findGetter/findSetter` không tự tạo thread-safety hoặc Java Memory Model guarantees cao hơn so với thao tác field tương ứng. Khi chia sẻ hidden instance giữa thread, phải dùng đồng bộ, volatile/VarHandle phù hợp hoặc immutable data design.

Tương tự, `initialize=true` điều khiển thời điểm class initialization, không biến toàn bộ object state bên trong thành thread-safe.

### 11.3. Không khẳng định hiệu năng khi chưa đo

Một MethodHandle đã cache và adapted có thể giúp tránh chi phí Reflection lặp lại trong nhiều trường hợp, nhưng chi phí còn phụ thuộc signature, dispatch, JIT, dynamic type, adapter chain, boxing và runtime. Để biết phương án có lợi:

- Tránh đo việc `defineHiddenClass` bên trong vòng lặp nếu ứng dụng định nghĩa một lần.
- Đo riêng thời gian define/lookup và thời gian invoke.
- Dùng JMH với warmup, dữ liệu đại diện và tránh dead-code elimination.
- So sánh cùng semantics với reflection và interface call, đừng chỉ so một microbenchmark không có side effects.
- Xem memory/metaspace và lifecycle, không chỉ throughput.

## 12. Checklist triển khai

Trước khi đưa code runtime hidden classes vào production:

1. **Nguồn bytes**: được sinh/đọc từ nguồn tin cậy, classfile version phù hợp, package hợp lệ.
2. **Lookup đầu vào**: đúng class, module và full privilege, không lấy bừa `publicLookup`.
3. **Lookup trả về**: giữ an toàn, dùng `lookupClass()`; không đoán runtime name.
4. **Member API**: constructor dùng `MethodType` trả `void`; `findVirtual` dùng signature không có receiver trong request; static khác instance.
5. **Private member access**: dùng returned Lookup, chỉ xuất bản capability cần thiết.
6. **NESTMATE**: chỉ bật khi hidden code có nhu cầu hợp lệ với host private, không dùng như một bước mặc định vô ý thức.
7. **Adapter**: kiểm tra `raw.type()` và `adapted.type()`; receiver thật đúng hidden runtime class.
8. **Initialization**: hiểu `initialize`, chủ động kiểm thử static initializer và lỗi init.
9. **Identity**: mỗi define tạo runtime type mới, không trộn handles/instances từ phiên bản khác.
10. **Lifetime**: chọn `STRONG` có căn cứ và cache có giới hạn.
11. **Concurrency**: định nghĩa/cache một lần theo key, xử lý race, đồng bộ mutable state.
12. **Observability**: log logical implementation key/version và lỗi theo giai đoạn, không dùng runtime hidden name làm ID bền vững.

## 13. Câu hỏi tự kiểm tra

**1.** `defineHiddenClass` trả về loại nào?

**Đáp án:** `MethodHandles.Lookup`, không phải `Class<?>` trực tiếp. Lấy Class object qua `returnedLookup.lookupClass()`.

**2.** Có thể gọi `Class.forName(hiddenType.getName())` để tìm lại lớp ẩn không?

**Đáp án:** Không. Hidden classes không được tìm bằng tên theo cơ chế class lookup thông thường. Phải giữ Class object/Lookup/handle đã có.

**3.** Muốn gọi private constructor nhận `int`, chữ ký truyền vào `findConstructor` có return type nào?

**Đáp án:** `void`. Lookup request là `MethodType.methodType(void.class,int.class)`; constructor MethodHandle trả về mới trả instance của hidden class.

**4.** Muốn tìm `private String describe(String)` thì MethodType của `findVirtual` có cần thêm receiver không?

**Đáp án:** Không. Request dùng `(String)String`; handle sau lookup mang `(HiddenType,String)String`.

**5.** Vì sao `asType(Object,... )` dùng được mà không phá private access?

**Đáp án:** Private access đã được kiểm tra khi dùng returned Lookup tìm member; `asType` tạo adapter chuyển reference và kiểm tra runtime cast, không tự thêm quyền.

**6.** Hai hidden classes định nghĩa từ cùng bytes có cùng identity không?

**Đáp án:** Không. Mỗi `defineHiddenClass` tạo runtime class riêng. Instance của class A không tự tương thích với handle nhận receiver là class B.

**7.** Returned Lookup giúp gọi private method của hidden class. Vậy bytecode của method đó có tự truy cập host private được không?

**Đáp án:** Không mặc nhiên. Truy cập host private cần quyền/nest relation hợp lệ, thường lựa chọn `ClassOption.NESTMATE` khi đúng mục đích.

**8.** Vì sao bản noNest vẫn `findStatic` thành công nhưng khi invoke lại có `IllegalAccessError`?

**Đáp án:** Lookup có quyền với **private method của chính hidden class**; lỗi xảy ra lúc bytecode bên trong method thử đọc **private field của host** mà không có nest access.

**9.** Vì sao không dùng `private static final String TOKEN = "x"` để kiểm chứng quyền private field trong demo?

**Đáp án:** Constant này có thể bị javac inline; việc không ném lỗi có thể do **không có lệnh getstatic truy cập field**.

**10.** `initialize=false` có nghĩa class không bao giờ khởi tạo không?

**Đáp án:** Không. Nó chỉ không yêu cầu khởi tạo ngay tại define; `ensureInitialized` hoặc active use sẽ làm class khởi tạo theo quy tắc JVM.

**11.** `STRONG` có tác dụng gì?

**Đáp án:** Gắn lifetime hidden class mạnh hơn với defining class loader. Không có `STRONG`, weak hidden class có thể được unload độc lập khi không còn reference phù hợp; không có bảo đảm unload ngay lập tức.

**12.** Có thể dùng hidden class làm sandbox cho bytecode không đáng tin?

**Đáp án:** Không. Hidden chỉ ảnh hưởng tới cơ chế định nghĩa/tìm class và liên quan tới lifetime/access; nó không tự ngăn I/O hoặc thực thi mã độc.

## Tóm tắt

- `defineHiddenClass` trả **Lookup trỏ tới hidden class mới**. Giữ Lookup hoặc các Class/MethodHandle cần thiết, đừng dựa vào runtime name.
- Dùng returned Lookup để gọi **private constructor, method, field** của hidden class: `findConstructor`, `findVirtual`, `findStatic`, `findGetter`, `findSetter`.
- Constructor lookup dùng **return type void**; instance method lookup **không** đưa receiver vào MethodType yêu cầu, nhưng MethodHandle nhận receiver.
- `asType` giúp biểu diễn receiver/return type là `Object` hoặc interface đã biết; `invokeExact` đòi signature đúng ở call site.
- **Private access của returned Lookup** khác với **NESTMATE** cho hidden bytecode truy cập private của host.
- `initialize` điều khiển khởi tạo; `STRONG` ảnh hưởng lifetime; mỗi lần define tạo **một runtime class identity mới**.
- Cache đúng Class/handles theo phiên bản, kiểm soát Lookup như capability và kiểm thử việc **gọi member thật**, không chỉ kiểm tra `findXxx` thành công.

## Tài liệu tham khảo

- Java SE 17, **MethodHandles.Lookup** — defineHiddenClass, lookupClass, findConstructor/findVirtual/findStatic/findGetter/findSetter, ensureInitialized: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- Java SE 17, **Lookup.ClassOption** — NESTMATE và STRONG: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html
- Java SE 17, **MethodHandle** — asType, invokeExact, invokeWithArguments: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html
- Java SE 17, **Class** — isHidden, isNestmateOf, getName: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- OpenJDK, **JEP 371 – Hidden Classes**: https://openjdk.org/jeps/371
- Java Virtual Machine Specification SE 17, **Class Loading, Linking, Initialization and Access Control**: https://docs.oracle.com/javase/specs/jvms/se17/html/index.html
