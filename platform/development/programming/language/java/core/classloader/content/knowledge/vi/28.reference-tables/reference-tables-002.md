# Bảng thao tác kích hoạt khởi tạo lớp hoặc interface trong Java

## 1. Cần phân biệt “đã nạp lớp” và “đã khởi tạo lớp”

Khi phân tích Java ClassLoader, câu hỏi **“lớp này đã được load chưa?”** không đồng nghĩa **“static initializer của lớp đã chạy chưa?”**. JVM có nhiều giai đoạn riêng:

1. **Loading:** tìm biểu diễn nhị phân, tạo runtime class/interface và đối tượng `Class<?>` tương ứng, với defining ClassLoader được xác định.
2. **Linking:** verification, preparation và resolution (thời điểm resolution có thể thay đổi theo chiến lược JVM).
3. **Initialization:** thực thi mã khởi tạo class/interface, đặc biệt các static field initializers và static initialization blocks (nếu có).

Ví dụ:

```java
class Sample {
    static {
        System.out.println("Sample initialized");
    }

    static int number = 123;
}
```

Đây là **đoạn source minh họa** không có `main`. Việc nhận được `Sample.class` hay kết quả của một lời gọi `loadClass("Sample")` chưa có nghĩa dòng `Sample initialized` đã được in. Ngược lại, khi code thực sự đọc `Sample.number` lần đầu mà class chưa khởi tạo, JVM phải khởi tạo `Sample` trước khi trả giá trị.

Trong Java, “class initialization” có ý nghĩa rất cụ thể. **Static initialization** của class không phải “chạy constructor” của từng instance và cũng không phải quá trình JVM nạp bytecode từ file. Bài này tập trung vào **bảng thao tác nào kích hoạt initialization, thao tác nào không, và các ngoại lệ quan trọng với interface, superclass, hằng compile-time và reflection**.

## 2. Quy tắc gốc theo JLS 17 §12.4.1

JLS 17 nêu rằng một class hoặc interface `T` cần được khởi tạo trước lần đầu xảy ra một trong các thao tác khởi tạo chủ động phù hợp. Các nhóm nền tảng là:

- **Tạo instance của class `T`**, ví dụ `new T()`.
- **Gọi static method được khai báo bởi `T`**.
- **Gán một static field được khai báo bởi `T`**.
- **Đọc một static field do `T` khai báo mà field ấy không phải *constant variable*.**
- **Một số thao tác phản chiếu** qua `java.lang.Class` hoặc `java.lang.reflect` theo hợp đồng API.

Khi JVM khởi tạo **class**, nó còn khởi tạo các **superclass** chưa được khởi tạo và những **superinterface có khai báo default method** liên quan theo quy tắc JLS/JVMS. Ngược lại, khi khởi tạo **interface**, việc đó **không tự động khởi tạo toàn bộ superinterface** của interface ấy.

Thứ tự thực thi các static field initializers và `static { ... }` trong một class/interface tuân theo **thứ tự xuất hiện trong source** và các quy tắc ngôn ngữ; mỗi runtime class/interface được JVM quản lý trạng thái initialization riêng. Một class đã khởi tạo thành công không chạy lại `<clinit>` chỉ vì có thêm một lời gọi `getstatic` hoặc `new`.

**Điểm cần nhớ:** cùng một thao tác có thể kéo theo initialization của **một class khác** mà không khởi tạo class xuất hiện trong biểu thức source. Ví dụ, `Sub.inheritedField` có thể thực sự là field do `Parent` khai báo; lúc ấy **Parent** là nơi được khởi tạo vì truy cập field, còn **Sub** không tự khởi tạo bởi việc ấy.

## 3. Bảng tra cứu nhanh: thao tác và initialization

Bảng dưới dùng giả định class/interface tương ứng **chưa được khởi tạo trước đó**, không có lỗi class file, và class member đang nói tới thực sự được khai báo ở kiểu đã nêu. “Có” nghĩa **thao tác đó trực tiếp đòi hỏi initialization** theo ngữ nghĩa Java. “Không” nghĩa **không chỉ vì riêng thao tác ấy**, dù việc nạp/link hoặc khởi tạo lớp liên quan có thể phát sinh từ ngữ cảnh khác.

| Thao tác | Khởi tạo loại nào? | Kết luận | Ghi chú chính xác |
| --- | --- | --- | --- |
| `new T()` với `T` là class | `T` cùng superclass/default-method superinterfaces cần thiết | **Có** | Trước khi tạo instance thành công, class `T` phải được initialization |
| Gọi `T.staticMethod()` do `T` khai báo | Class hoặc interface `T` | **Có** | Static method invocation là active use |
| Gán `T.staticField = ...` | Kiểu **khai báo field** | **Có** | Với field có thể gán; `putstatic` cần initialization |
| Đọc `T.staticField` không là constant variable | Kiểu **khai báo field** | **Có** | `getstatic` cho non-constant field là active use |
| Đọc `T.CONST` là *constant variable* | Thường không cần initialization chỉ để lấy hằng | **Không** | Giá trị có thể được đưa vào constant pool của caller |
| Tham chiếu `T.class` | `T` | **Không** | Class literal có thể dẫn đến loading/linking, không phải initialization |
| Tạo mảng `new T[n]` | Element class `T` | **Không** | Có thể tạo array class mà chưa initialize component class |
| `x instanceof T` | `T` | **Không** | Kiểm tra kiểu không phải active-use trigger của `T` |
| Ép kiểu `(T) x` | `T` | **Không** | `checkcast` không tự chạy static initializer của target type |
| Khai báo `T variable;` hoặc gán `T ref = null` | `T` | **Không** | Chỉ dùng tên kiểu ở source không khiến `T` khởi tạo |
| `ClassLoader.loadClass("pkg.T")` mặc định | `T` | **Không** | Load class không đồng nghĩa initialize; custom code có thể làm việc khác |
| `Class.forName(name, false, loader)` | `T` | **Không** | Tìm/nạp/link theo API nhưng không yêu cầu initialize |
| `Class.forName(name)` | `T` | **Có** đối với class/interface thông thường | Overload 1 tham số yêu cầu initialize |
| `Class.forName(name, true, loader)` | `T` | **Có** | Tham số boolean chọn initialization |
| `Class.forName(name, false, loader)` với tên array class | Component class | **Không** | Array type không đòi hỏi component initialization |
| `T.class.getName()` / `getClassLoader()` | `T` | **Không** | Đọc class metadata không đủ để kích hoạt `<clinit>` |
| `T.class.getDeclaredMethod("run")` | `T` | **Không** theo thao tác lookup | Có thể load/resolve metadata khác; không gọi method |
| `method.invoke(null)` với static method thuộc `T` | `T` | **Có** | Reflection invocation kích hoạt initialization khi cần |
| `field.get(null)` đọc static field thuộc `T` | `T` | **Có** theo reflection API | Kể cả field có giá trị compile-time constant trong thí nghiệm |
| `constructor.newInstance(...)` | Declaring class | **Có** | Tạo instance phản chiếu |
| `MethodHandle.invokeExact(...)` cho static method/field `T` | `T` | **Có** khi thực sự thực hiện thao tác | Lấy handle không đồng nghĩa gọi handle |
| Chỉ `lookup.findStatic(T.class, ...)` | `T` | **Không** trong ví dụ | Chưa invoke; xét API cụ thể, đừng gộp tìm handle với gọi handle |
| `MethodHandles.Lookup.ensureInitialized(T.class)` | `T` | **Có** | API yêu cầu đảm bảo class được khởi tạo khi quyền cho phép |
| `new ImplementsPlain()` với interface không có default method | Interface `Plain` | **Không** chỉ bởi việc khởi tạo class con | Class implementation vẫn được khởi tạo |
| `new ImplementsDefault()` với interface có khai báo default method | Superinterface `HasDefault` | **Có** trước class tương ứng theo quy tắc | Quan trọng với static field initializers của interface |
| Đọc static field không phải hằng trong interface `I` | `I` | **Có** | Truy cập owner interface; không mặc nhiên init các superinterfaces |
| Khởi tạo `Sub` extends `Parent` | `Parent` | **Có** nếu chưa khởi tạo | Parent được khởi tạo trước Sub |
| Chỉ đọc `Sub.field` nhưng field thật do Parent khai báo | `Parent`, không nhất thiết Sub | **Chỉ owner** | Tên `Sub` trong biểu thức không quyết định initialization |
| Tạo lambda `() -> T.staticMethod()`, chưa gọi lambda | `T` | **Không vì body chưa chạy** | Lambda linkage có chi tiết riêng; nếu body thực sự chạy sẽ có active use |
| Chỉ xuất hiện `T` trong generic type/type token | `T` | **Không** chỉ vì cú pháp kiểu | Phụ thuộc biểu thức runtime có gọi API kích hoạt khác hay không |

Bảng là công cụ tra cứu **trigger**, không phải lời khẳng định class luôn còn ở trạng thái uninitialized đến thời điểm đó: JVM có thể đã khởi tạo nó do code khác, một class phụ thuộc hoặc thao tác trước đó. Thêm nữa, trong môi trường custom loader, chính phương thức `loadClass` do framework override có thể chủ động gọi `Class.forName(..., true, ...)` hoặc thực thi code tạo side effect; bảng mô tả **hợp đồng API chuẩn**, không bảo đảm custom method không làm việc phụ.

## 4. Bảng riêng cho static fields và compile-time constants

Một nguồn nhầm lẫn rất phổ biến là suy từ chữ `static final` rằng field “không làm class khởi tạo”. Điều này **không luôn đúng**. Khái niệm trong JLS là **constant variable**: một biến `final` có kiểu primitive hoặc `String`, được khởi tạo bằng **constant expression**.

| Khai báo | Constant variable? | Đọc bằng Java source thường làm owner initialize? |
| --- | --- | --- |
| `static final int A = 10;` | Có | **Không** chỉ vì đọc `A` |
| `static final String S = "Java";` | Có | **Không** chỉ vì đọc `S` |
| `static final long L = 1L + 2L;` | Có | **Không** khi biểu thức là compile-time constant |
| `static final int X = Integer.parseInt("7");` | Không | **Có** nếu owner chưa init |
| `static final String T = new String("Java");` | Không | **Có** |
| `static final Integer I = 7;` | Không: reference wrapper không phải primitive/String | **Có** |
| `static int count = 5;` | Không | **Có** |
| `static final Object O = new Object();` | Không | **Có** |
| `static final int[] NUMBERS = {1, 2};` | Không: array reference | **Có** |

Ví dụ:

```java
final class Settings {
    static {
        System.out.println("init=Settings");
    }

    static final int PORT = 8080;
    static final String HOST = "localhost";
    static final int DYNAMIC_PORT = Integer.parseInt("8080");
}
```

Đây là **class minh họa** không có main. `System.out.println(Settings.PORT)` và `Settings.HOST` có thể được compiler thay bằng literal/constant pool, nên **không** đòi hỏi `Settings` initialization. Nhưng `Settings.DYNAMIC_PORT` không phải constant variable: đọc nó sẽ yêu cầu khởi tạo Settings trước.

**Cẩn thận với JAR versioning:** nếu client đã biên dịch và inline `Settings.PORT`, đổi giá trị PORT trong JAR ở runtime chưa chắc làm client hiện giá trị mới. Đây là đặc điểm binary compatibility của constant variables, không phải bằng chứng ClassLoader đã chọn sai class.

**Cẩn thận với reflection:** `Field.get(null)` đọc static field qua reflection có thể kích hoạt initialization ngay cả khi khai báo source là constant variable. Vì vậy không thể áp dụng quy tắc “hằng compile-time không init” cho mọi **cách truy cập**; cần phân biệt bytecode/biểu thức thường với reflection.

## 5. Ví dụ Java 17 đầy đủ: quan sát 21 thao tác và trạng thái khởi tạo

Ví dụ dưới đây gom các trường hợp thành một chương trình duy nhất, nhưng mỗi trường hợp sử dụng **một class/interface riêng chưa được đụng đến** khi cần đo thời điểm initialization. Điều này tránh lỗi khi test: nếu class đã khởi tạo ở dòng trước, dòng sau không thể in lại `init=...` dù thao tác đó vốn là active use.

Lưu mã vào file **`InitActionsDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public final class InitActionsDemo {
    private static String trace(String message) {
        System.out.println(message);
        return message;
    }

    static final class Passive {
        static { trace("init=Passive"); }
        static final int CONST = 42;
        static int number = 7;
        static String echo() { return "ok"; }
    }
    static final class WriteTarget {
        static { trace("init=WriteTarget"); }
        static int number;
    }
    static final class Constructed {
        static { trace("init=Constructed"); }
        String value() { return "object"; }
    }
    static class Parent {
        static { trace("init=Parent"); }
    }
    static final class Child extends Parent {
        static { trace("init=Child"); }
        static String value = "child";
    }
    static class FieldOwner {
        static { trace("init=FieldOwner"); }
        static int inherited = 11;
    }
    static final class Derived extends FieldOwner {
        static { trace("init=Derived"); }
    }
    interface Plain {
        String MARK = trace("init=Plain");
    }
    static final class ImplementsPlain implements Plain {
        static { trace("init=ImplementsPlain"); }
    }
    interface HasDefault {
        String MARK = trace("init=HasDefault");
        default String value() { return "default"; }
    }
    static final class ImplementsDefault implements HasDefault {
        static { trace("init=ImplementsDefault"); }
    }
    interface Base {
        String MARK = trace("init=Base");
    }
    interface Extended extends Base {
        String MARK = trace("init=Extended");
    }
    static final class ForNameTarget {
        static { trace("init=ForNameTarget"); }
    }
    static final class MethodTarget {
        static { trace("init=MethodTarget"); }
        public static String run() { return "method"; }
    }
    static final class FieldTarget {
        static { trace("init=FieldTarget"); }
        public static final int VALUE = 99;
    }
    static final class HandleTarget {
        static { trace("init=HandleTarget"); }
        public static String run() { return "handle"; }
    }

    public static void main(String[] args) throws Throwable {
        System.out.println("01 literal=" + Passive.class.getSimpleName());
        System.out.println("02 constant=" + Passive.CONST);
        System.out.println("03 array=" + (new Passive[2]).length);
        System.out.println("04 forNameFalse=" +
                (Class.forName(Passive.class.getName(), false,
                        InitActionsDemo.class.getClassLoader()) == Passive.class));
        System.out.println("05 getstatic=" + Passive.number);
        System.out.println("06 invokestatic=" + Passive.echo());
        WriteTarget.number = 9;
        System.out.println("07 putstatic=" + WriteTarget.number);
        System.out.println("08 new=" + new Constructed().value());
        System.out.println("09 subclass=" + Child.value);
        System.out.println("10 inherited=" + Derived.inherited);
        System.out.println("11 plainImplement=" + new ImplementsPlain().getClass().getSimpleName());
        System.out.println("12 plainField=" + Plain.MARK);
        System.out.println("13 defaultImplement=" + new ImplementsDefault().value());
        System.out.println("14 extendedField=" + Extended.MARK);
        Class<?> named = Class.forName(ForNameTarget.class.getName(), true,
                InitActionsDemo.class.getClassLoader());
        System.out.println("15 forNameTrue=" + named.getSimpleName());
        Method method = MethodTarget.class.getDeclaredMethod("run");
        System.out.println("16 reflectedMethodFound=" + (method != null));
        System.out.println("17 methodInvoke=" + method.invoke(null));
        Field field = FieldTarget.class.getDeclaredField("VALUE");
        System.out.println("18 fieldFound=" + (field != null));
        System.out.println("19 fieldGet=" + field.get(null));
        MethodHandle handle = MethodHandles.lookup().findStatic(
                HandleTarget.class, "run", MethodType.methodType(String.class));
        System.out.println("20 handleFound=" + (handle != null));
        System.out.println("21 handleInvoke=" + (String) handle.invokeExact());
    }
}
```

Biên dịch và chạy với **JDK 17 trở lên**:

```bash
javac --release 17 InitActionsDemo.java
java InitActionsDemo
```

Không cần Maven, Gradle, file JAR ngoài hoặc custom ClassLoader. Mã đã được biên dịch bằng `javac 21 --release 17` và chạy thử trên Java 21; các thao tác là API/syntax tương thích Java 17. **Stdout thực tế của chương trình:**

```text
01 literal=Passive
02 constant=42
03 array=2
04 forNameFalse=true
init=Passive
05 getstatic=7
06 invokestatic=ok
init=WriteTarget
07 putstatic=9
init=Constructed
08 new=object
init=Parent
init=Child
09 subclass=child
init=FieldOwner
10 inherited=11
init=ImplementsPlain
11 plainImplement=ImplementsPlain
init=Plain
12 plainField=init=Plain
init=HasDefault
init=ImplementsDefault
13 defaultImplement=default
init=Extended
14 extendedField=init=Extended
init=ForNameTarget
15 forNameTrue=ForNameTarget
16 reflectedMethodFound=true
init=MethodTarget
17 methodInvoke=method
18 fieldFound=true
init=FieldTarget
19 fieldGet=99
20 handleFound=true
init=HandleTarget
21 handleInvoke=handle
```

**Lưu ý về dòng `12 plainField=init=Plain`:** hàm `trace("init=Plain")` vừa in thông điệp, vừa **trả về chính chuỗi ấy** làm giá trị field `MARK`. Vì vậy dòng kết quả chứa `init=Plain` hai lần theo hai ý nghĩa khác nhau: một dòng độc lập báo lúc interface init và một giá trị string được in sau `plainField=`. Tương tự với `Extended.MARK`. Đây là output có chủ ý, không phải in nhầm/khởi tạo interface hai lần.

### 5.1. Phân tích nhóm thao tác không khởi tạo ngay

Bốn dòng đầu có liên quan tới class `Passive`:

```text
01 literal=Passive
02 constant=42
03 array=2
04 forNameFalse=true
```

**Chưa có** `init=Passive` trong bốn dòng này, vì:

- `Passive.class` lấy `Class<?>` mirror nhưng không yêu cầu chạy `<clinit>`.
- `Passive.CONST` là compile-time constant `42`, được dùng mà không cần đọc field runtime qua `getstatic`.
- `new Passive[2]` tạo **mảng chứa tham chiếu Passive**, không gọi `new Passive()` cho từng phần tử. Các ô của mảng lúc đầu là `null`.
- `Class.forName(name, false, loader)` yêu cầu tải/link class thích hợp nhưng **không chủ động initialization**.

Ở dòng 05 mới xuất hiện:

```text
init=Passive
05 getstatic=7
```

Đọc `Passive.number` là active use của static field không phải constant variable, nên initialization xảy ra trước khi giá trị `7` được in. Dòng 06 gọi static method `Passive.echo()` nhưng không in lại `init=Passive` vì class này đã khởi tạo.

### 5.2. Gán static field và tạo object

Các dòng:

```text
init=WriteTarget
07 putstatic=9
init=Constructed
08 new=object
```

cho thấy:

- **Gán** `WriteTarget.number = 9` yêu cầu initialize class trước khi phép gán hoàn tất, dù field chưa được đọc.
- `new Constructed()` yêu cầu initialize class trước việc tạo instance. Method `value()` được gọi trên instance đã có.

Đừng nhầm `new Constructed[5]` với `new Constructed()`: thao tác thứ nhất chỉ tạo **mảng**, không tạo năm đối tượng Constructed.

### 5.3. Superclass trước subclass, nhưng static field thuộc owner nào?

Khi truy cập `Child.value`, class Child phải khởi tạo và JVM bảo đảm superclass `Parent` được khởi tạo trước:

```text
init=Parent
init=Child
09 subclass=child
```

Ngược lại, khi truy cập `Derived.inherited`, field thực sự được khai báo trong `FieldOwner`. Kết quả:

```text
init=FieldOwner
10 inherited=11
```

**Không có `init=Derived`.** Đây là bằng chứng rằng tên subclass xuất hiện trong biểu thức source không tự làm subclass khởi tạo nếu member là static field do superclass khai báo. JLS §12.4.1 có ví dụ đúng trường hợp này.

### 5.4. Interface không có default method và interface có default method

Dòng 11:

```text
init=ImplementsPlain
11 plainImplement=ImplementsPlain
```

Khi khởi tạo `ImplementsPlain`, interface `Plain` không tự init chỉ do class implementing nó khởi tạo, vì Plain **không khai báo default method**. Khi code thật sự đọc `Plain.MARK`, vì MARK là field không phải constant variable, `Plain` mới init:

```text
init=Plain
12 plainField=init=Plain
```

Đối với interface `HasDefault`, nó khai báo `default String value()`. Khi class `ImplementsDefault` cần khởi tạo, JVM xử lý việc khởi tạo superinterface có default method cần thiết **trước** class:

```text
init=HasDefault
init=ImplementsDefault
13 defaultImplement=default
```

Không được suy rộng “tất cả interface được khởi tạo khi một class implements chúng”. Chỉ những superinterface thuộc nhóm được quy tắc JLS/JVMS yêu cầu khởi tạo cùng class. Một compiler đôi khi còn sinh **synthetic default methods** có liên quan đến việc xác định interface cần khởi tạo; vì vậy khi phân tích bytecode biến đổi, hãy xét định nghĩa class/interface thực tế.

### 5.5. Interface extends interface không tự init interface cha

Trong demo:

```java
interface Base {
    String MARK = trace("init=Base");
}
interface Extended extends Base {
    String MARK = trace("init=Extended");
}
```

Khi đọc `Extended.MARK`, chỉ interface **Extended** cần initialization cho field do nó khai báo:

```text
init=Extended
14 extendedField=init=Extended
```

**Không có `init=Base`.** Khởi tạo một interface **không tự kéo theo initialization của các superinterfaces**. Nếu sau đó thật sự đọc `Base.MARK`, Base có thể được khởi tạo vào thời điểm ấy.

### 5.6. Reflection: lấy metadata không giống invoke/get field

`Class.forName(..., true, ...)` chủ động initialize:

```text
init=ForNameTarget
15 forNameTrue=ForNameTarget
```

Nhưng `MethodTarget.class.getDeclaredMethod("run")` chỉ tra metadata nên dòng:

```text
16 reflectedMethodFound=true
```

xuất hiện mà chưa có `init=MethodTarget`. Khi gọi:

```java
method.invoke(null);
```

để thực thi **static method** được khai báo trong MethodTarget, reflection kích hoạt initialization trước:

```text
init=MethodTarget
17 methodInvoke=method
```

Tương tự, `getDeclaredField("VALUE")` không tự init, nhưng `Field.get(null)` trên static field dẫn đến:

```text
18 fieldFound=true
init=FieldTarget
19 fieldGet=99
```

Mặc dù `VALUE` là `public static final int VALUE = 99` (compile-time constant), **reflection read** vẫn có hợp đồng khởi tạo khác với biểu thức Java source được compiler inline. Đây là tình huống thường bị bỏ sót trong bảng tra cứu ngắn.

### 5.7. MethodHandle: phân biệt tìm handle và gọi handle

`MethodHandles.lookup().findStatic(HandleTarget.class, "run", ...)` **lấy method handle**. Thí nghiệm chưa in `init=HandleTarget` ở bước này:

```text
20 handleFound=true
```

Khi gọi `handle.invokeExact()`, JVM thực sự thực hiện static invocation, yêu cầu initialization:

```text
init=HandleTarget
21 handleInvoke=handle
```

**Không đánh đồng mọi thao tác của MethodHandles**: có API truy vấn handle, API đảm bảo initialized và API thực thi handle. Các thao tác có ngữ nghĩa khác nhau. Khi giải thích một call site cụ thể, nên xem invocation kind (static field getter/setter, static method, constructor), target và thời điểm thực thi, thay vì kết luận “thấy MethodHandle là init ngay”.

## 6. ClassLoader.loadClass, Class.forName và khởi tạo class

Một điểm cốt lõi với chủ đề ClassLoader:

```java
Class<?> loaded = loader.loadClass("pkg.Widget");
```

Với hành vi chuẩn, API `loadClass` **nạp/tìm** runtime class, có thể thực hiện linking theo các quy tắc liên quan, nhưng **không tự yêu cầu initialization**. Còn:

```java
Class<?> type = Class.forName("pkg.Widget", true, loader);
```

chủ động yêu cầu khởi tạo class `pkg.Widget`. Nếu class ấy chưa được initialized, code static liên quan sẽ được thực thi trước khi lời gọi hoàn thành bình thường.

Ba cách dùng:

| API | Chủ đích | Lưu ý |
| --- | --- | --- |
| `loader.loadClass("pkg.Widget")` | Tìm/nạp qua loader | Không tự init theo contract chuẩn; custom override có thể side effects |
| `Class.forName("pkg.Widget", false, loader)` | Tra class qua loader mà không init | Hữu ích cho scanner, kiểm tra metadata trước |
| `Class.forName("pkg.Widget", true, loader)` | Tra và bảo đảm initialization | Có thể gây side effect từ static initializer |

Với overload:

```java
Class.forName("pkg.Widget");
```

Java dùng ngữ cảnh caller để chọn loader phù hợp và **initialize class** theo hợp đồng. Không tự giả định lời gọi này luôn dùng `Thread.currentThread().getContextClassLoader()`. Để kiểm soát loader/initialization trong hệ plugin, dùng overload ba tham số với loader rõ.

### Vì sao false không bảo đảm “không có bất kỳ class nào khác initialized”?

`initialize=false` chỉ nói rằng **API không yêu cầu initialize chính class được yêu cầu**. Trong quá trình load/link, VM có thể load class phụ thuộc hoặc code custom ClassLoader thực thi side effects. Nếu custom loader **tự gọi** một static method của class khác, class khác có thể initialized. Bởi vậy:

- Không suy từ `Class.forName(... false ...)` rằng “không có initialization nào trong cả JVM”.
- Đừng lấy log constructor của một đối tượng khác làm bằng chứng class mục tiêu initialized.
- Khi cần kiểm thử sạch, dùng class riêng chưa đụng tới và log static initializer của chính nó.
- Xem stack trace/cause khi API thất bại ở linking hoặc initialization; hai nhóm lỗi khác nhau.

### Parent delegation không thay quy tắc initialization

Child loader có thể trả class do parent đã định nghĩa. Việc child trả class ấy **không chạy `<clinit>` một lần nữa**. Initialization gắn với **runtime class thật** được JVM quản lý, tức cùng binary name + defining loader. Nếu hai loader **tự định nghĩa hai runtime classes khác nhau** cùng binary name, chúng có trạng thái initialization riêng và có thể khởi tạo vào hai thời điểm khác nhau.

## 7. Bytecode liên quan: new, getstatic, putstatic, invokestatic

Khi đối chiếu source với bytecode, các instruction thường gắn với active use:

| Instruction | Mục đích | Có thể yêu cầu initialize? |
| --- | --- | --- |
| `new` | Tạo instance của class | **Có** đối với class được tạo |
| `getstatic` | Đọc static field | **Có** với field không phải constant variable / bytecode thực sự đọc field |
| `putstatic` | Gán static field | **Có** |
| `invokestatic` | Gọi static method | **Có** |
| `ldc` với String/int literal | Nạp hằng từ constant pool | **Không** tự init owner của constant variable từng xuất hiện trong source |
| `ldc` class literal | Nhận Class mirror | **Không** tự init class được biểu diễn |
| `anewarray` / `multianewarray` | Tạo array | **Không** tự init component class chỉ vì array creation |
| `checkcast` / `instanceof` | Kiểm tra/ép kiểu | **Không** tự init target class |
| `invokevirtual` cho instance method | Gọi instance method | **Không** tự init theo cùng nghĩa static active use | 
| `invokeinterface` cho instance method | Gọi method của instance qua interface | **Không** chỉ do instance call; object đã tồn tại và class thường đã init |

**Lưu ý về `getstatic` và constant variable:** biểu thức Java source `Settings.PORT` đối với hằng compile-time thường được compiler **inline**, nên bytecode của caller có thể không chứa `getstatic Settings.PORT`. Khi phân tích bytecode được sinh thủ công, không được bỏ qua ngữ nghĩa kích hoạt của một instruction `getstatic` thực sự được thực thi chỉ vì field trong class file mang `final`. Bảng JLS nói về cách truy cập thông thường từ Java source và JVMS mô tả kích hoạt ở mức instruction — phân biệt hai mức để tránh mâu thuẫn giả.

**Cách tự quan sát bytecode của ví dụ:**

```bash
javap -c -p InitActionsDemo
javap -c -p 'InitActionsDemo$Passive'
```

Hai lệnh dùng cú pháp trích dẫn single-quote phù hợp với Linux/macOS/Git Bash. Trên Windows PowerShell, cũng có thể quote tên nested class để dấu `$` không bị shell xử lý như biến; với `javap` nên chạy trong thư mục chứa các file `.class`.

Trong output `javap -c`, tìm `ldc`/constant, `getstatic`, `putstatic` và `invokestatic` theo đoạn tương ứng. Không suy initialization chỉ từ việc **constant pool có tham chiếu tới class**: cần xem instruction nào thực sự được thực thi và quy tắc JVM.

## 8. Thứ tự khởi tạo và tác động từ superclass/default interface

Khi class `Child` được khởi tạo, JVM tuân theo quy trình:

```text
Yêu cầu initialize Child
    |
    +-- Parent chưa init? -> initialize Parent
    |
    +-- superinterfaces khai báo default methods
    |   chưa init? -> initialize theo thứ tự quy định
    |
    +-- Child chạy static field initializers và static blocks
```

Một class có thể kế thừa nhiều interface gián tiếp. Trật tự và tập interface cần init được JLS 12.4.2 xác định chi tiết; không nên vẽ đơn giản “mọi interface trước mọi superclass”. Điều quan trọng trong thực hành là:

- **Superclass phải initialized trước subclass**.
- Khi class khởi tạo, những **superinterfaces khai báo default methods** thuộc phạm vi quy định phải initialized theo trình tự.
- Class implements một interface **chỉ có static field/abstract methods**, không có default methods, không bắt buộc init interface ấy chỉ vì class con khởi tạo.
- Khởi tạo interface **không tự** init superinterfaces.
- **Static field được khai báo ở kiểu nào thì chính kiểu đó** được init khi đọc field non-constant, không phải kiểu dùng để viết biểu thức.

Các tình huống này xuất hiện nhiều ở framework: interface khai báo biến static tạo singleton/registry có side effect; code có thể kích hoạt nó khi khởi tạo một implementation **nếu interface khai báo default method**, ngay cả trước khi phương thức default được gọi.

### Thứ tự khai báo static fields và static blocks

```java
class Ordering {
    static int a = print("a", 1);
    static {
        System.out.println("static block");
    }
    static int b = print("b", 2);

    static int print(String name, int value) {
        System.out.println(name);
        return value;
    }
}
```

Đây là source **minh họa**. Lần active use của Ordering dẫn tới chuỗi:

```text
a
static block
b
```

Static fields **không phải constant variables** được khởi tạo bằng các biểu thức thực thi theo source order. Đừng trộn điều này với **preparation**, giai đoạn runtime cấp các static fields giá trị mặc định trước initialization.

## 9. Đồng thời nhiều thread: chỉ một lượt initialization thành công

Khi hai thread lần đầu chạm cùng runtime class:

```text
Thread T1                            Thread T2
   |                                    |
   +-- yêu cầu initialize X              +-- yêu cầu initialize X
   |                                    |
   +-- JVM đánh dấu đang init X          +-- JVM chờ initialization của X
   |
   +-- chạy static fields / <clinit>
   |
   +-- hoàn thành thành công
                                        +-- tiếp tục sau khi X đã initialized
```

JLS 12.4.2 quy định **đồng bộ initialization theo từng runtime class/interface**, có trạng thái “chưa init”, “đang init”, “đã init” và “erroneous”. Nếu initialization cùng class được yêu cầu đệ quy bởi **chính thread đang thực hiện initialization**, JVM có quy tắc xử lý reentrant request; không đơn giản chạy `<clinit>` vô hạn lần.

Hệ quả:

- Static initialization của class thành công **chỉ diễn ra một lần cho định nghĩa runtime ấy**, không phải một lần mỗi thread.
- Hai defining ClassLoader khác nhau định nghĩa cùng binary name có thể dẫn tới **hai lượt initialization riêng**, vì đó là hai runtime classes.
- Nếu static initializer block mãi mãi hoặc đợi khóa theo chu trình giữa thread, chương trình có thể treo; ClassLoader không tự là hàng rào xử lý deadlock.
- Không dựa vào việc `System.out.println` trong static block luôn phản ánh toàn bộ ordering khi nhiều thread và nhiều lớp độc lập khởi tạo song song; mỗi class có quy tắc ordering riêng.

### Khi static initializer thất bại

Một class có static initializer ném exception:

```java
class Broken {
    static final int X = fail();

    static int fail() {
        throw new IllegalStateException("boom");
    }
}
```

Đây là mã **minh họa**. Lần đầu thực hiện một thao tác yêu cầu khởi tạo Broken (ví dụ truy cập `Broken.X`) thường có thể dẫn tới `ExceptionInInitializerError` bao bọc exception không phải Error. Class bị đánh dấu **erroneous** theo quy trình JLS, những yêu cầu initialize tiếp theo có thể nhận `NoClassDefFoundError` liên quan tới trạng thái lỗi.

Cần xem **cause và lần thất bại đầu tiên**, không tự sửa bằng cách gọi `Class.forName` lặp trên cùng defining loader rồi mong static block chạy lại. Với named class đã erroneous, thông thường phải sửa lỗi và quản lý lifecycle loader/class mới để có một định nghĩa runtime độc lập nếu kiến trúc cho phép.

## 10. Đọc log: lớp được “load” chưa đồng nghĩa được “initialized”

Nếu bật unified logging với JDK phù hợp:

```bash
java -Xlog:class+load=info -cp . InitActionsDemo
```

JVM ghi lại các sự kiện class loading. Log này hữu ích để thấy **lớp nào được nạp và có nguồn từ đâu**, nhưng không thay thế log static initialization. Một class có thể được load/link bởi reflection hoặc verifier mà chưa init. Muốn quan sát initialization qua logging, phải xác định tag/level hỗ trợ trên JVM đang dùng; không tự coi mọi dòng `class+load` là sự kiện `<clinit>`.

Trong ví dụ, chính các dòng `init=...` được in bởi static initializer hoặc initializer expression là bằng chứng rõ rằng **mã khởi tạo của lớp/interface đó thực sự chạy**.

### Một quy trình phân tích khi output bất ngờ

1. Xác định **runtime Class<?> và defining loader**, vì cùng tên class ở hai loader là hai trạng thái init khác nhau.
2. Kiểm tra class mục tiêu có static initializer hoặc static field initializer có side effect thật sự không. Class không có output không có nghĩa chưa initialized.
3. Xác định **thao tác active use đầu tiên**: `new`, static method, static field nonconstant, reflection hay Class.forName true.
4. Kiểm tra field thực sự do class/interface **nào khai báo**. Access qua subclass có thể init superclass chứ không init subclass.
5. Kiểm tra field có phải constant variable hay không; xem bytecode caller để nhận biết inline.
6. Nếu liên quan interface, kiểm tra default methods, synthetic defaults và quy tắc initialization của superinterfaces.
7. Phân biệt hành vi `getDeclaredMethod` với `Method.invoke`, `findStatic` với `invokeExact`, `forName false` với `forName true`.
8. Nếu class đã được initialized trước thí nghiệm, tạo **class khác** hoặc chạy một JVM mới; không kỳ vọng `<clinit>` tự chạy lại trong cùng runtime class.
9. Nếu có lỗi, đọc `ExceptionInInitializerError`/`NoClassDefFoundError` và original cause.
10. Nếu plugin nhiều classloader, bảo đảm không test một Class object từ parent rồi ghi nhận nó như định nghĩa của child.

## 11. Các lỗi hiểu nhầm phổ biến

| Nhận định sai | Sửa lại cho đúng |
| --- | --- |
| “ClassLoader.loadClass tức static block đã chạy.” | Loading khác initialization. Kiểm tra active use và `Class.forName` options. |
| “`T.class` chắc chắn kích hoạt `static {}`.” | Class literal không yêu cầu initialization. |
| “`static final` luôn không init khi đọc.” | Chỉ **constant variable** qua source access thường không init; reference values/runtime expressions khác. |
| “`new T[10]` tạo mười instance T.” | Tạo mảng chứa mười ô tham chiếu, thường ban đầu null. |
| “Có `getstatic` trong bytecode thì chắc chủ field được in trong source.” | Field declaring type mới là trọng tâm; source có thể dùng tên subclass để tham chiếu field owner khác. |
| “Khởi tạo một class luôn khởi tạo mọi interface nó implements.” | Chỉ những superinterface có default methods theo quy tắc. |
| “Khởi tạo một interface luôn khởi tạo interface cha.” | Không tự động. |
| “Đọc `Sub.parentField` bắt buộc init Sub.” | Có thể chỉ init Parent nếu field khai báo ở Parent. |
| “`Class.forName(name, false, loader)` chẳng làm gì.” | Nó có thể tải/link class nhưng không chủ động initialize target. |
| “`Class.forName(name)` giống hệt `loader.loadClass(name)`.” | Overload `forName` có hành vi initialization khác. |
| “Lấy Field/Method qua reflection đồng nghĩa thực thi code của owner.” | Lookup metadata khác với invoke/get/set runtime. |
| “Reading constant via Field.get không thể init.” | Reflection có hợp đồng initialization riêng; demo cho thấy `Field.get` init owner. |
| “Lấy MethodHandle static lập tức chạy class initializer.” | Tìm handle và invoke handle là hai việc khác nhau; xét API/call site. |
| “Static initializer chạy mỗi lần new object.” | Chỉ một lần khi init thành công cho một runtime class, không phải mỗi instance. |
| “Cùng class name ở hai loaders sẽ dùng chung static state.” | Hai defining loaders tạo hai runtime classes/statics riêng. |
| “JVM compile/link xong thì mọi static block của dependency chạy hết.” | Linking và initialization có quy tắc/timing khác nhau. |
| “ExceptionInInitializerError có thể chữa bằng gọi loadClass lại.” | Class ở trạng thái erroneous có quy tắc lỗi tiếp theo; tìm nguyên nhân khởi tạo. |

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `Sample.class` được lấy nhưng chưa có class static action nào. `<clinit>` đã chắc chắn chạy chưa?

**Đáp án:** Chưa. Class literal không phải trigger initialization.

**Câu 2.** `static final int X = 123;` và `static final Integer Y = 123;`. Đọc qua Java source thường có cùng tác động không?

**Đáp án:** Không. X là constant variable nếu biểu thức compile-time, thường được inline; Y là reference wrapper không thuộc kiểu primitive/String của constant variable, đọc Y là active use của owner.

**Câu 3.** `new Widget[3]` và `new Widget()` khác nhau thế nào đối với initialization?

**Đáp án:** Tạo array không bắt buộc Widget initialization; tạo instance Widget thì có.

**Câu 4.** `Child inheritedField` được truy cập qua tên Child nhưng field do Parent khai báo. Class nào được init do thao tác ấy?

**Đáp án:** Parent nếu chưa initialized; Child không tự init chỉ vì biểu thức field đó.

**Câu 5.** Interface I không khai báo default method. Khi khởi tạo class implements I, I có bắt buộc init không?

**Đáp án:** Không chỉ vì việc class implements nó. Nhưng đọc I.nonConstantField hoặc thao tác active use khác có thể init I.

**Câu 6.** Interface J extends I, đọc nonconstant static field do J khai báo. I có tự init theo không?

**Đáp án:** Không, initialization của J không tự kéo theo I.

**Câu 7.** `Class.forName(name, false, loader)` và `Class.forName(name, true, loader)` khác gì?

**Đáp án:** False không yêu cầu initialize target; true yêu cầu initialize target trước khi hoàn thành bình thường.

**Câu 8.** Vì sao reflection `Field.get(null)` của một `public static final int` có thể init owner dù source access thường không?

**Đáp án:** Reflection invocation có semantics yêu cầu initialize class trước khi lấy static field qua API; trong khi source constant variable có thể được compiler inline.

**Câu 9.** Nếu `getDeclaredMethod` trả Method object mà không in `init=Target`, nhưng `invoke(null)` lại in, có mâu thuẫn không?

**Đáp án:** Không. Tìm method metadata và thực thi method khác nhau.

**Câu 10.** Vì sao `HasDefault` init trước `ImplementsDefault` trong ví dụ?

**Đáp án:** Vì JVM khởi tạo những superinterface khai báo default methods theo JLS trước khi hoàn tất initialization của class.

**Câu 11.** Hai ClassLoaders độc lập định nghĩa cùng binary name T. Static initializer của T có dùng chung trạng thái không?

**Đáp án:** Không. Đó là hai runtime classes với hai defining loaders khác nhau, có trạng thái initialization riêng.

**Câu 12.** Khi Broken.<clinit> lỗi lần đầu, lần sau có chắc JVM thử chạy lại đầy đủ không?

**Đáp án:** Không. Class có thể ở trạng thái erroneous, và yêu cầu tiếp theo thường nhận NoClassDefFoundError. Cần phân tích nguyên nhân lần đầu.

## 13. Checklist khi lập bảng initialization cho ứng dụng thật

- [ ] Xác định class/interface **được khai báo** bởi thao tác, không chỉ tên dùng trong source.
- [ ] Tách loading, linking, initialization thành ba bước.
- [ ] Phân loại trigger: new, invokestatic, putstatic, getstatic nonconstant, reflection, MethodHandle invocation.
- [ ] Xác minh `static final` có thật là constant variable hay không.
- [ ] Kiểm tra class literal, array creation, cast, instanceof và `forName(false)` là các thao tác không tự init target.
- [ ] Kiểm tra parent class trước child class.
- [ ] Với interface, kiểm tra có default method và quan hệ superinterface.
- [ ] Không cho rằng interface initialization luôn kéo theo interface parent.
- [ ] Hiểu reflection lookup khác method/field invocation.
- [ ] Không nhầm static variable initialization với instance field/constructor initialization.
- [ ] Nếu cần test, dùng JVM mới và các class targets chưa khởi tạo.
- [ ] So sánh static output với bytecode qua `javap -c` khi nghi constant được inline.
- [ ] Khi có custom ClassLoader, ghi cả binary name và defining loader.
- [ ] Theo dõi lỗi init và trạng thái erroneous thay vì chỉ catch `ClassNotFoundException`.
- [ ] Không thiết kế side effect lớn/khó phục hồi trong static initializer.
- [ ] Xem JLS 12.4.1 và 12.4.2 là nguồn quyết định khi có tranh cãi về initialization timing.

## 14. Kết luận và tài liệu tham khảo

**Không phải mọi thao tác “đụng tới tên lớp” đều kích hoạt khởi tạo.** Java chỉ initialize class/interface khi các trigger cụ thể xảy ra hoặc khi có quan hệ initialization phụ thuộc theo quy tắc JVM. Trường hợp rõ nhất là `new T()`, static method, gán static field, đọc static field không phải constant variable và một số thao tác reflection. Ngược lại, `T.class`, `new T[n]`, `Class.forName(..., false, ...)`, đọc compile-time constant, cast và `instanceof` **không tự làm target initialized**.

Khi có kế thừa, điều kiện phụ thuộc trở nên tinh tế hơn: superclass trước subclass; superinterfaces có default methods được xét khi khởi tạo class; interface tự khởi tạo không có nghĩa mọi superinterface cũng khởi tạo. Cuối cùng, trạng thái init thuộc về **runtime class được định nghĩa bởi một defining loader**, không chỉ tên class trên giấy.

Nguồn chính thức để tra cứu:

- **JLS Java SE 17 §12.4.1 — When Initialization Occurs:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1
- **JLS Java SE 17 §12.4.2 — Detailed Initialization Procedure:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2
- **JVMS Java SE 17 §5.5 — Initialization:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5
- **JLS Java SE 17 §4.12.4 — final Variables and Constant Variables:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4
- **Java SE 17 `Class` API, `forName`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- **Java SE 17 `Field` API, `get`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html
- **Java SE 17 `MethodHandles.Lookup` API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
