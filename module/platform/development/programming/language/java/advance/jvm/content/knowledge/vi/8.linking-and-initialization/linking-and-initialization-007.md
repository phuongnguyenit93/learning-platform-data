# Các thao tác kích hoạt khởi tạo và các trường hợp chỉ nạp lớp trong JVM

Một lớp Java có thể **đã được JVM nạp và có đối tượng `Class<?>`**, nhưng **chưa chạy static initializer**. Đến khi chương trình thực hiện một thao tác yêu cầu khởi tạo (initialization), JVM mới thực hiện thủ tục khởi tạo lớp/interface đó. Nhầm hai thời điểm sẽ gây lỗi khó tìm: log static xuất hiện ngoài dự đoán, plugin tự khởi động quá sớm, đọc field trả giá trị chưa như kỳ vọng, hoặc một lớp thất bại ở `<clinit>` rồi không thể khởi tạo lại.

Bài tập trung vào câu hỏi: **thao tác nào bắt buộc kích hoạt initialization và thao tác nào có thể chỉ loading/linking mà chưa chạy `<clinit>`?** Phần giải thích dựa trên **JLS Java SE 17 `12.4** và **JVMS Java SE 17 `5.5**, có ví dụ Java 17 chạy độc lập, đối chiếu bytecode và checklist điều tra lỗi.

**Quy tắc mở đầu:** “Lớp được nhắc đến” không đủ để kết luận “lớp đã khởi tạo”. Cần biết **loại thao tác**, **lớp/interface thực sự khai báo thành viên**, trạng thái initialization trước đó, và những phụ thuộc như superclass hoặc superinterface có default methods.

## 1. Ba giai đoạn không được đồng nhất

JVM phân biệt các khái niệm sau:

| Giai đoạn | JVM thực hiện | Có nhất thiết chạy static initializer của lớp đích? |
| --- | --- | --- |
| **Loading** | Tìm/định nghĩa biểu diễn runtime của class/interface từ tên và dữ liệu nhị phân; tạo đối tượng `Class` tương ứng | **Không** |
| **Linking: verification** | Kiểm tra định dạng, bytecode, kiểu và các ràng buộc hợp lệ | **Không** |
| **Linking: preparation** | Cấp vùng lưu static fields và thiết lập giá trị ban đầu theo quy tắc VM; có xử lý đặc biệt cho `ConstantValue` attributes | **Không chạy `<clinit>`** |
| **Linking: resolution** | Phân giải symbolic references (class, field, method...) khi JVM quyết định thực hiện theo đặc tả | **Không nhất thiết** |
| **Initialization** | Thực thi thủ tục khởi tạo class/interface, bao gồm code static field initializers và static blocks do compiler tạo | **Có**, nếu có công việc khởi tạo |

Đối với một lớp bình thường, compiler thường gom các lệnh khởi tạo static vào một **class initialization method `<clinit>`**. Nếu lớp không có code cần chạy thì không nhất thiết có method `<clinit>` trong class file, nhưng JVM vẫn có **trạng thái khởi tạo** cho lớp.

Sơ đồ khái niệm:

```text
chưa được nạp
     |
     | ClassLoader / JVM yêu cầu lớp
     v
LOADING --------> đã có Class<?> và định danh runtime
     |
     v
LINKING --------> verification / preparation / resolution
     |             (một phần resolution có thể diễn ra khi cần)
     |
     | thao tác active use yêu cầu khởi tạo
     v
INITIALIZATION --> khởi tạo lớp cha / một số superinterface nếu phải làm
     |             --> thực hiện static initializers / <clinit>
     v
đã khởi tạo thành công; các active uses tiếp tục
```

Không xem sơ đồ như timeline bắt buộc mọi bước resolution hoàn tất tại đúng một điểm duy nhất: JLS/JVMS cho phép JVM giải quyết symbolic references ở những thời điểm phù hợp trong phạm vi ràng buộc của đặc tả.

### Initialization khác construction

- **Initialization của class** là thủ tục ở cấp kiểu, thường xảy ra **một lần** đối với mỗi runtime class đã được định nghĩa bởi một defining class loader.
- **Instance construction** là tạo và khởi tạo **từng object**, có thể thực hiện nhiều lần; constructor `<init>` khác method `<clinit>`.
- Lời gọi `new Example()` thường dẫn tới class initialization nếu class chưa initialized, rồi mới tiếp tục tạo và xây dựng object theo quy tắc Java.
- Gọi `Class.forName("Example")` có thể khởi tạo class nhưng **không tạo bất kỳ instance Example nào**.

## 2. Bốn thao tác active use tiêu biểu trong JLS `12.4.1

Đối với một class `T`, JLS xác định việc khởi tạo diễn ra **ngay trước lần đầu** một số thao tác được thực hiện, trong đó các trường hợp quan trọng nhất là:

1. **Tạo instance của `T`**, chẳng hạn `new T()`; cũng có thể thực hiện qua reflection.
2. **Gọi một static method được khai báo bởi `T`**, chẳng hạn `T.perform()`.
3. **Gán giá trị cho một static field được khai báo bởi `T`**, chẳng hạn `T.count = 3`.
4. **Đọc một static field được khai báo bởi `T` mà field ấy không phải constant variable**, chẳng hạn `System.out.println(T.dynamicValue)`.

Các thao tác cụ thể khác như một số phương thức reflection hoặc lần gọi đầu của các method handles thích hợp cũng có thể buộc initialization. Việc khởi tạo superclass và một số superinterfaces của một class còn được kích hoạt **gián tiếp** bởi initialization của class ấy.

### Bảng quyết định nhanh

| Thao tác | Có chủ động yêu cầu initialize lớp liên quan? | Điều kiện cần nhớ |
| --- | --- | --- |
| `new T()` | **Có** | Trước khi tạo và xây dựng object của `T` nếu chưa khởi tạo |
| `T.staticMethod()` | **Có** | Khởi tạo **lớp/interface khai báo method** được gọi, không nhất thiết class viết ở bên trái dấu chấm |
| `T.nonConstantStaticField` | **Có** | Đọc field không phải constant variable |
| `T.staticField = value` | **Có** | Gán field static của lớp/interface khai báo |
| `T.COMPILE_TIME_CONSTANT` | **Không vì riêng phép đọc này** | Nếu là **constant variable** được khai báo phù hợp và truy cập theo quy tắc constant |
| `T.class` | **Không** | Lấy class literal không tự khởi tạo `T` |
| `new T[10]` | **Không cho component `T`** | Tạo array class/object; không tạo một instance `T` |
| `obj instanceof T` | **Không vì riêng phép kiểm tra này** | Có thể phải resolution kiểu nhưng không chủ động chạy `T.<clinit>` |
| `(T) obj` | **Không vì riêng cast này** | Checkcast có thể lỗi cast; không phải trigger initialize |
| `ClassLoader.loadClass("p.T")` | **Không theo contract mặc định** | Nạp lớp, không yêu cầu initialize `T` |
| `Class.forName("p.T", false, loader)` | **Không** | Yêu cầu nạp/liên kết nhưng không chủ động initialize |
| `Class.forName("p.T")` | **Có** | Overload một tham số mặc định yêu cầu initialization |
| `Class.forName("p.T", true, loader)` | **Có** | Có thể chọn loader và chủ động yêu cầu initialization |
| `Class.forName(module, "p.T")` | **Không** | Overload theo `Module` có contract khác và có thể trả `null` |
| `T[].class` | **Không cho `T`** | Lấy class literal của array type |
| Reflection: gọi static method qua `Method.invoke` | **Có** | Nếu cần, initialize declaring class trước invocation |
| Reflection: tạo instance qua `Constructor.newInstance` | **Có** | Nếu cần, initialize declaring class trước khi tạo |
| Reflection: đọc/ghi static field qua `Field.get`/`set` | **Có** | Kiểm tra access và trạng thái field có thể phát sinh lỗi |
| `Class.getDeclaredMethods()` | **Không do riêng metadata lookup** | Có thể nạp/resolve kiểu phụ thuộc; không đồng nghĩa gọi method |

Đây là bảng cho **nguyên nhân trực tiếp**. Nếu một thao tác thụ động gọi tới thư viện có side effects, hoặc thread khác đồng thời active-use cùng lớp, bạn vẫn có thể quan sát thấy class đã được initialized; không được kết luận rằng API thụ động là trigger chỉ vì log xuất hiện gần đó.

## 3. Chương trình Java 17: nạp, lấy `Class<?>`, rồi mới khởi tạo

Tạo file **`ActiveUseMatrix.java`**:

```java
public class ActiveUseMatrix {
    public static class Target {
        public static final int CONSTANT = 7;

        static {
            System.out.println("Target.<clinit>");
        }

        public static int dynamic = compute();

        private static int compute() {
            System.out.println("Target.compute");
            return 42;
        }

        public static void ping() {
            System.out.println("Target.ping");
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader = ActiveUseMatrix.class.getClassLoader();
        String name = ActiveUseMatrix.class.getName() + "$Target";

        System.out.println("01 constant=" + Target.CONSTANT);

        Class<?> literal = Target.class;
        System.out.println("02 literal=" + literal.getSimpleName());

        Class<?> viaLoader = loader.loadClass(name);
        System.out.println("03 loadClass same=" + (viaLoader == literal));

        Class<?> viaForName = Class.forName(name, false, loader);
        System.out.println("04 forName(false) same=" + (viaForName == literal));

        Class<?> arrayType = Class.forName("[L" + name + ";", false, loader);
        System.out.println("05 array=" + arrayType.isArray());

        Class.forName(name, true, loader);
        System.out.println("06 after forName(true)");

        Target.ping();
        System.out.println("07 done");
    }
}
```

Chạy với JDK có `javac` hỗ trợ Java 17:

```bash
javac --release 17 ActiveUseMatrix.java
java ActiveUseMatrix
```

**Stdout chính xác**:

```text
01 constant=7
02 literal=Target
03 loadClass same=true
04 forName(false) same=true
05 array=true
Target.<clinit>
Target.compute
06 after forName(true)
Target.ping
07 done
```

Diễn giải theo từng mốc:

- `Target.CONSTANT` là **constant variable** vì `static final int` được gán constant expression. Việc dùng giá trị 7 có thể được compiler nhúng vào caller; dòng 01 không khiến `Target` phải initialize.
- `Target.class` lấy một `Class<Target>` nhưng **không** chủ động chạy static block; dòng 02 đến trước `Target.<clinit>`.
- `loader.loadClass(name)` và `Class.forName(name, false, loader)` cùng xác định runtime class do cùng defining loader; hai kết quả so sánh identity với class literal là `true`, nhưng `Target` vẫn chưa initialize.
- Lệnh `Class.forName("[L" + name + ";", false, loader)` lấy **array class** có component `Target`; nó không tạo instance Target hoặc khởi tạo component class. Dòng 05 vẫn đến trước static block.
- `forName(name, true, loader)` yêu cầu initialization. Static block được thực hiện trước rồi static field `dynamic` gọi `compute()`. Thứ tự này xuất phát từ **thứ tự textual của static initializers** trong `Target`.
- `Target.ping()` chạy sau khi lớp đã initialized nên không tái thực thi `<clinit>`. Dòng `Target.ping` xuất hiện đúng một lần từ method `ping`.

**Điểm tinh tế:** JVM có thể đã **loading** `Target` từ trước, kể cả do verifier cần tới kiểu ấy, nhưng điều quan sát được ở đây là **chưa có yêu cầu initialization** trước khi gọi `forName(true)`. Không được lấy dòng đầu log `Target.<clinit>` để suy ra chính xác thời điểm đầu tiên class file được đọc từ disk.

## 4. Static field: vì sao `static final` chưa chắc “không kích hoạt”?

Cần phân biệt **constant variable** trong JLS với một field chỉ mang modifiers `static final`.

Theo JLS `4.12.4, một constant variable phải là `final`, có kiểu **primitive hoặc `String`**, và được khởi tạo bằng **constant expression** theo JLS `15.29. Ví dụ:

```java
static final int LIMIT = 100;            // constant variable
static final String TITLE = "JVM";       // constant variable
static final int SUM = 2 + 3;            // constant variable

static final int RUNTIME = calculate();  // KHÔNG là constant variable
static final Integer WRAPPED = 100;      // KHÔNG là constant variable
static final Object OBJECT = new Object(); // KHÔNG là constant variable
```

Đây là **fragment trong một class**, không phải chương trình độc lập. Cần phân biệt:

- `LIMIT`, `TITLE`, `SUM` đáp ứng điều kiện constant variable.
- `RUNTIME` dùng method call nên không phải constant expression.
- `WRAPPED` có kiểu `Integer` reference, không phải primitive hay `String`.
- `OBJECT` là reference tới object được tạo ở runtime.
- Khi code **đọc** một trong các nonconstant static fields này, trường hợp active use thông thường khiến **declaring class** được initialize.
- `ConstantValue` attribute trong class file là một phần cơ chế cấp giá trị cho constant variable ở thời điểm preparation; không suy rằng việc đọc constant ấy buộc JVM chạy `<clinit>`.

### Một chương trình để quan sát constant và nonconstant field

Tạo **`ConstantVsRuntime.java`**:

```java
public class ConstantVsRuntime {
    static class Holder {
        static final String LABEL = "ready";
        static final int FIXED = 5;
        static final Integer BOXED = Integer.valueOf(8);

        static {
            System.out.println("Holder.<clinit>");
        }

        static final int COMPUTED = 10 + runtimeValue();

        private static int runtimeValue() {
            System.out.println("Holder.runtimeValue");
            return 2;
        }
    }

    public static void main(String[] args) {
        System.out.println("label=" + Holder.LABEL);
        System.out.println("fixed=" + Holder.FIXED);

        System.out.println("boxed=" + Holder.BOXED);
        System.out.println("computed=" + Holder.COMPUTED);
    }
}
```

```bash
javac --release 17 ConstantVsRuntime.java
java ConstantVsRuntime
```

**Stdout**:

```text
label=ready
fixed=5
Holder.<clinit>
Holder.runtimeValue
boxed=8
computed=12
```

Khi `Holder.BOXED` được đọc, JVM phải khởi tạo `Holder`. Trong quá trình `<clinit>`, các field initializers và static blocks chạy theo thứ tự source: `BOXED` nhận 8, rồi in `Holder.<clinit>`, sau đó khởi tạo `COMPUTED` bằng `runtimeValue()` và in `Holder.runtimeValue`. Khi tiếp tục, việc đọc `Holder.COMPUTED` không tái thực hiện initialization.

### Có cách nào đọc field mà không khởi tạo class không?

Lấy **metadata** của field bằng `Holder.class.getDeclaredField("BOXED")` không đồng nghĩa **đọc giá trị** field. Nhưng `Field.get(null)` của field static sẽ yêu cầu initialization khi cần. Đừng dùng metadata lookup và value access như hai hành vi đồng nhất.

## 5. Lớp khai báo static member mới là lớp quan trọng

Một điều đặc biệt dễ gây nhầm: biểu thức `Subclass.staticField` **không nhất thiết** khởi tạo `Subclass` nếu field ấy thực sự được khai báo ở `Superclass`.

Tạo **`DeclaringClassRules.java`**:

```java
public class DeclaringClassRules {
    static class Parent {
        static {
            System.out.println("Parent.<clinit>");
        }

        static int value = 10;

        static void show() {
            System.out.println("Parent.show");
        }
    }

    static class Child extends Parent {
        static {
            System.out.println("Child.<clinit>");
        }
    }

    public static void main(String[] args) {
        System.out.println("field=" + Child.value);
        Child.show();
        System.out.println("after inherited members");

        new Child();
        System.out.println("after instance");
    }
}
```

```bash
javac --release 17 DeclaringClassRules.java
java DeclaringClassRules
```

**Stdout**:

```text
Parent.<clinit>
field=10
Parent.show
after inherited members
Child.<clinit>
after instance
```

Giải thích:

1. `Child.value` có cú pháp nhắc tới Child nhưng field `value` do **Parent** khai báo. Phép đọc yêu cầu initialize **Parent**, không trực tiếp buộc Child initialize.
2. `Child.show()` cũng trỏ tới static method do Parent khai báo, nên gọi `Parent.show`. Parent đã initialized; Child vẫn chưa.
3. `new Child()` là active use của Child. Superclass Parent đã initialized, vì vậy lần này chỉ thấy log `Child.<clinit>`.

Đừng nhầm **static hiding** với **instance overriding**. Tên lớp ở bên trái dấu chấm trong source có thể khác với **declaring class** cuối cùng mà compiler/VM liên kết tới. Khi không rõ, dùng `javap -c -v` xem `getstatic` hoặc `invokestatic` đang tham chiếu tới field/method nào.

## 6. Những thao tác không tự khởi tạo component class

### Class literal và kiểm tra kiểu

- `SomeType.class` là **class literal**; việc đánh giá biểu thức này không tự kích hoạt initialization của `SomeType`.
- `obj instanceof SomeType` và cast `(SomeType) obj` có thể đòi hỏi VM kiểm tra/resolve kiểu; chúng **không** phải active-use trigger để chạy `SomeType.<clinit>`.
- `someClass.getName()`, `getSimpleName()` hay các thao tác đọc metadata tương đương không có nghĩa phải chạy static initializer của target class.
- Các metadata APIs **có thể** liên quan tới resolution và loading những kiểu khác. Không đồng nhất “không initialize target” với “hoàn toàn không có công việc VM”.

### Mảng `new T[n]`

`new T[3]` **tạo object array**, không tạo ba object `T` và không buộc `T` initialize. Những phần tử reference ban đầu là `null`. Ngược lại, code `new T[] {new T()}` **có** tạo một instance `T` bên trong array initializer, nên nó sẽ kích hoạt initialization khi cần.

### Ví dụ Java 17

Tạo **`PassiveOperations.java`**:

```java
public class PassiveOperations {
    static class Element {
        static {
            System.out.println("Element.<clinit>");
        }

        static int DATA = 5;
    }

    public static void main(String[] args) {
        System.out.println("class=" + Element.class.getSimpleName());

        Element[] elements = new Element[2];
        System.out.println("arrayLength=" + elements.length);
        System.out.println("firstIsNull=" + (elements[0] == null));

        Object item = "not an Element";
        System.out.println("instanceof=" + (item instanceof Element));

        System.out.println("before active read");
        System.out.println("data=" + Element.DATA);
    }
}
```

```bash
javac --release 17 PassiveOperations.java
java PassiveOperations
```

**Stdout**:

```text
class=Element
arrayLength=2
firstIsNull=true
instanceof=false
before active read
Element.<clinit>
data=5
```

Không có hoạt động nào trước `Element.DATA` chủ động yêu cầu initialization của Element. Phép đọc static field không phải constant variable mới khiến `Element.<clinit>` được thực hiện.

### Vì sao `Class.forName("[Lpkg.Type;")` cần phân biệt?

Với dạng **array descriptor-like name**, `Class.forName` nhận biết một **array class**. Ngay cả overload yêu cầu initialize, **component class vẫn không được initialize chỉ vì nạp array class**. Nếu sau đó chương trình `new pkg.Type()` thì đó là một active use khác, cần xét riêng.

Đừng thay tùy ý `pkg.Type[]` (cú pháp source) bằng string nạp class; đối với mảng reference, định dạng tên dùng kiểu `[Lpkg.Type;`; đối với mảng primitive `int[]` dùng `[I`. Tên primitive `int` tự nó không phải một binary class name để nạp như class thông thường.

## 7. `Class.forName` và `ClassLoader.loadClass`: chọn đúng overload

| Cách gọi | Loader được chọn | Có chủ động yêu cầu initialize? |
| --- | --- | --- |
| `Class.forName(name)` | Loader của **lớp gọi** `Class.forName` (caller-sensitive) | **Có** |
| `Class.forName(name, true, loader)` | Loader truyền vào, `null` là bootstrap loader | **Có** |
| `Class.forName(name, false, loader)` | Loader truyền vào | **Không** |
| `loader.loadClass(name)` | Chính đối tượng loader được gọi | **Không** theo triển khai/contract mặc định |
| `Class.forName(module, name)` | Tìm trong module chỉ định | **Không**, có thể trả `null` nếu không tìm thấy |

Một số điểm quan trọng:

- `ClassLoader.loadClass(String name)` thông thường ủy quyền tới `loadClass(name, false)`; tham số `resolve` của overload protected liên quan tới **linking/resolution**, **không phải** cờ initialize.
- `Class.forName(name, false, loader)` yêu cầu nạp và liên kết nhưng không chủ động initialize. Một luồng khác có thể đồng thời initialize cùng class, vì vậy `initialize=false` **không phải một cam kết trạng thái lớp vẫn “chưa khởi tạo” mãi**.
- `Class.forName(name)` **không tự sử dụng Thread Context ClassLoader**. Framework có thể lấy `Thread.currentThread().getContextClassLoader()` rồi truyền loader đó vào overload ba tham số nếu cần tìm provider theo bối cảnh.
- Với cùng **runtime class** và defining loader, initializer chạy theo quy tắc trạng thái initialization, không chạy lại mỗi lần gọi `forName(true)`. Cùng tên class nhưng **định nghĩa bởi hai defining loaders khác nhau** là hai kiểu runtime riêng, mỗi kiểu có trạng thái initialization riêng.
- `Class.forName(module, name)` là API khác, không thay thế cơ học `forName(name, true, loader)` khi cần chạy static initializer.

### Mẫu plugin: tra metadata trước, chủ động initialize sau

```java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
Class<?> candidate = Class.forName("com.example.Plugin", false, loader);

// Kiểm tra các metadata/quan hệ kiểu theo contract của ứng dụng...
// Khi quyết định bắt đầu sử dụng lớp:
Class.forName("com.example.Plugin", true, loader);
```

Đây là **đoạn minh họa**, class `com.example.Plugin` và loader phải tồn tại trong ứng dụng thật; cần kiểm tra `loader` có thể null hay không. Chủ động tách bước tìm lớp với bước khởi tạo giúp giảm side effects khi quét nhiều plugin, nhưng không loại bỏ tất cả việc loading/linking metadata dependencies.

## 8. Reflection: đọc metadata không giống gọi method/tạo instance

Reflection dùng `Class<?>` làm “đối tượng mô tả kiểu”, nhưng mỗi thao tác có một mức active use khác nhau.

- `type.getDeclaredMethods()`, `getDeclaredFields()`, `getDeclaredConstructor(...)` thường là **metadata lookup**, không tự yêu cầu chạy `<clinit>` của lớp đích.
- `method.invoke(null, ...)` với **static method** yêu cầu JVM initialize declaring class trước invocation nếu cần.
- `constructor.newInstance(...)` yêu cầu class được khởi tạo trước khi tạo instance.
- `field.get(null)` hoặc `field.set(null, value)` trên **static field** yêu cầu initialization theo contract của reflection trước khi đọc/ghi giá trị, khác với chỉ lấy metadata của `Field`.
- Reflection còn kiểm tra **accessibility** và module boundaries. Một method tìm được có thể vẫn không gọi được vì `IllegalAccessException` hoặc chính sách module; các lỗi đó không thể sửa bằng cách cố gọi `Class.forName(true)`.

### Ví dụ metadata trước, active use sau

Tạo file **`ReflectionInitialization.java`**:

```java
import java.lang.reflect.Method;

public class ReflectionInitialization {
    public static class Service {
        static {
            System.out.println("Service.<clinit>");
        }

        public static void hello() {
            System.out.println("Service.hello");
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader = ReflectionInitialization.class.getClassLoader();
        String name = ReflectionInitialization.class.getName() + "$Service";

        Class<?> type = Class.forName(name, false, loader);
        Method hello = type.getDeclaredMethod("hello");
        System.out.println("metadata acquired");

        hello.invoke(null);
        System.out.println("invocation completed");
    }
}
```

```bash
javac --release 17 ReflectionInitialization.java
java ReflectionInitialization
```

**Stdout**:

```text
metadata acquired
Service.<clinit>
Service.hello
invocation completed
```

`Class.forName(false)` và `getDeclaredMethod` cho phép lấy metadata trước; `Method.invoke` với static method khiến Service được initialize nếu chưa initialized. `Method.invoke` có thể gói lỗi **bên trong body method** thành `InvocationTargetException`, trong khi **initialization failure** có thể biểu hiện bằng `ExceptionInInitializerError`; cần đọc cause/stack trace thật, không gộp mọi lỗi reflection thành một loại.

## 9. Khởi tạo lớp con kéo theo superclass và một số superinterfaces

Không chỉ những thao tác nhắm trực tiếp `T` mới làm lớp/interface khác được initialized. Khi JVM initialization một **class**:

1. Nó thực hiện thủ tục bảo đảm superclass cần thiết đã được initialized.
2. Nó cũng initialization các **superinterfaces khai báo default methods** theo các quy tắc trong JVMS `5.5, kể cả một số superinterfaces gián tiếp theo thứ tự xác định.
3. Sau đó lớp đích mới hoàn tất phần khởi tạo của chính nó.

Không được diễn dịch thành “khởi tạo class luôn khởi tạo mọi interface được implements”: một interface **không có default methods** không nhất thiết được initialized chỉ vì có class implements nó. Những quy tắc interface còn khác với thứ tự superclass của class.

### Ví dụ minh họa có default method

Tạo **`DefaultInterfaceInitialization.java`**:

```java
public class DefaultInterfaceInitialization {

    static int announce(String message) {
        System.out.println(message);
        return 1;
    }

    static class Base {
        static {
            System.out.println("Base.<clinit>");
        }
    }

    interface WithDefault {
        int FLAG = announce("WithDefault.<clinit>");

        default void action() {
            // Không cần được gọi để WithDefault phải initialize khi Derived initialize.
        }
    }

    static class Derived extends Base implements WithDefault {
        static {
            System.out.println("Derived.<clinit>");
        }
    }

    public static void main(String[] args) {
        System.out.println("before new");
        new Derived();
        System.out.println("after new");
    }
}
```

```bash
javac --release 17 DefaultInterfaceInitialization.java
java DefaultInterfaceInitialization
```

**Stdout**:

```text
before new
Base.<clinit>
WithDefault.<clinit>
Derived.<clinit>
after new
```

Giải thích: `new Derived()` yêu cầu initialization của Derived. Base là superclass và phải được initialize trước; `WithDefault` khai báo một default method, vì vậy initialization của Derived còn kéo theo interface thích hợp; cuối cùng mới in `Derived.<clinit>`.

Một interface vẫn có thể được initialized **trực tiếp** bằng cách đọc một field static **không phải constant variable** của interface hoặc gọi một static method của interface. Trạng thái initialization của interface **không** nên suy ra chỉ từ việc code đã khai báo `implements`.

### Gọi default method và việc nạp interface

Tuy interface default method có body, lời gọi `interfaceRef.action()` có dispatch theo receiver và các quy tắc JVMS về method selection. Nó không có nghĩa mọi interface đã được load ở startup đều chạy initializer. Sự có mặt của default method trong chuỗi superinterface **liên quan đến** quy tắc khởi tạo khi khởi tạo class thực hiện, không phải lời gọi `action()` lần đầu mới luôn là trigger.

## 10. Method handles cũng có thể là active use

Một điểm nâng cao từ JVMS `5.5: **lần invocation đầu** của `MethodHandle` được phân giải từ một số **symbolic method handle kinds** có thể kích hoạt initialization của class/interface khai báo member tương ứng. Các reference kinds đáng nhớ:

- `REF_getStatic`
- `REF_putStatic`
- `REF_invokeStatic`
- `REF_newInvokeSpecial`

Không kết luận “lấy một `MethodHandle`” luôn chạy static initializer. Cần xem **loại symbolic reference, thời điểm resolution và invocation**, cùng contract của API liên quan. Lấy/tra `MethodHandle` và **thực thi handle** là hai sự kiện cần phân biệt.

Ngược lại, chỉ tạo một `MethodType` hay lấy `Class` metadata không phải “gọi static method” chỉ vì tên method nằm trong chuỗi lookup.

### Vì sao không nên học cơ chế này bằng ví dụ `staticMethod()` thường?

Compiler có thể trực tiếp dùng `invokestatic` và `getstatic` cho những lời gọi thông thường. Method handles là một lớp biểu diễn lời gọi khác, có cơ chế lookup và adaptation riêng. Nếu đang phân tích class file có `invokedynamic`, bootstrap method có thể gián tiếp truy cập method handles; luôn xem bootstrap owner, constant pool và semantics cụ thể thay vì giả định mọi `invokedynamic` có cùng điều kiện khởi tạo.

## 11. Bytecode cho biết trigger nào, nhưng không buộc đã khởi tạo ngay lúc resolve

Một bảng liên hệ source–bytecode:

| Java source | Opcode/biểu diễn thường thấy | Tại sao liên quan initialization |
| --- | --- | --- |
| `new Target()` | `new` + `dup` + `invokespecial <init>` | `new` tạo instance, yêu cầu initialization của Target khi cần |
| `Target.staticMethod()` | `invokestatic` | Target **declaring class** phải initialized theo quy tắc |
| `Target.dynamicField` | `getstatic` | Static field không phải constant variable đòi active use |
| `Target.dynamicField = x` | `putstatic` | Ghi static field đòi active use |
| `Target.class` | `ldc` class constant hoặc cách biểu diễn hợp lệ | Class literal không tự initialize Target |
| `Target.CONSTANT` | Có thể thành hằng literal trực tiếp, `bipush`/`ldc`... | Constant variable có thể được inline, không cần `getstatic` |
| `new Target[3]` | `anewarray` (thường) | Tạo array, **không** tạo instance Target |
| `obj instanceof Target` | `instanceof` | Kiểm tra kiểu, không phải active use của Target |
| `(Target) obj` | `checkcast` | Type check, không phải initialization trigger |
| `loader.loadClass(name)` | Gọi API thư viện qua `invokevirtual` | API loader không trực tiếp đòi init target |
| `Class.forName(name)` | `invokestatic Class.forName` | Hành vi init do API `Class.forName` yêu cầu đối với target |

**Đặc biệt:** một opcode `ldc` cho class constant, và một opcode `invokestatic` gọi method static của class **khác nhau về ngữ nghĩa**. Không suy ra “nếu lớp có mặt trong constant pool thì đã chạy static block”.

Lệnh `javap` để soi ví dụ:

```bash
javap -c -v -p ActiveUseMatrix
javap -c -v -p ConstantVsRuntime
javap -c -v -p DeclaringClassRules
```

Trong output, tìm `ldc ... class`, `getstatic`, `invokestatic`, `new`, `anewarray` cùng các constant-pool references. BCI và constant-pool indices do compiler sinh, không được chuẩn JLS cố định theo số thứ tự.

### Mẫu bytecode minh họa, không phải nguyên văn output

```text
ldc #ClassTarget     // lấy Class<Target>, không tự yêu cầu <clinit>
anewarray #Target    // tạo mảng reference Target, không initialize component
getstatic #Target.x  // đọc nonconstant static field, có thể kích hoạt <clinit>
invokestatic #Target.m // gọi static method, có thể kích hoạt <clinit>
new #Target          // tạo instance, có thể kích hoạt <clinit>
```

Các nhãn `#ClassTarget`, `#Target` là **chỗ đứng cho index constant pool**, không phải cú pháp output `javap` chính xác. Kết luận “có thể kích hoạt” là vì nếu lớp **đã initialized thành công** trước đó, cùng active use **không chạy lại initializer**.

## 12. Class initialization thất bại: trạng thái erroneous và đường lỗi

Một initialization có thể thất bại, ví dụ static field initializer gọi code ném exception. Khi JVM đánh dấu class là **erroneous** trong loader ấy, lần yêu cầu initialization tiếp theo không thực hiện lại `<clinit>` như thể class hoàn toàn mới.

Tạo **`InitializationFailure.java`**:

```java
public class InitializationFailure {
    static class Broken {
        static final int VALUE = compute();

        private static int compute() {
            throw new IllegalStateException("boom");
        }
    }

    public static void main(String[] args) throws Exception {
        String name = InitializationFailure.class.getName() + "$Broken";

        try {
            Class.forName(name);
        } catch (ExceptionInInitializerError error) {
            System.out.println("first=ExceptionInInitializerError");
        }

        try {
            Class.forName(name);
        } catch (NoClassDefFoundError error) {
            System.out.println("second=NoClassDefFoundError");
        }
    }
}
```

```bash
javac --release 17 InitializationFailure.java
java InitializationFailure
```

**Stdout**:

```text
first=ExceptionInInitializerError
second=NoClassDefFoundError
```

- Lần đầu, `Class.forName(name)` yêu cầu initialization. `compute()` ném `IllegalStateException`, làm initialization không hoàn thành; runtime báo `ExceptionInInitializerError` đối với exception được bọc theo quy tắc.
- Lần tiếp theo, cùng lớp trong cùng defining loader đang erroneous, nên nỗ lực khởi tạo lại thường nhận `NoClassDefFoundError` (“Could not initialize class ...”).
- `ClassNotFoundException` là checked exception cho việc **không tìm được class theo tên**; nó không đồng nghĩa `NoClassDefFoundError` do **class initialization thất bại trước đó** hoặc do lỗi liên kết/dependency.

**Không dùng “thử gọi lại `forName`” làm cơ chế khôi phục mặc định**. Nếu startup logic có nguy cơ thất bại, thiết kế việc retry ở tầng service hoặc tài nguyên ứng dụng, không giấu quá nhiều side effects vào static initializers.

## 13. Khởi tạo trong môi trường đa luồng và class loader riêng

JVMS `5.5 quy định thủ tục đồng bộ hóa để chỉ một thread thực hiện initialization của mỗi class/interface tại một thời điểm. Nếu thread A đang initialize T:

- Thread B yêu cầu active use của T có thể phải **đợi** T initialization hoàn thành.
- Nếu code `<clinit>` có khóa, I/O hoặc chờ lẫn nhau, startup có thể bị **block hoặc deadlock**. Stack trace/`jcmd Thread.print` có thể giúp điều tra nhưng không thay thế đọc logic.
- Nếu initialization thành công, các thread khác có thể sử dụng T theo các bảo đảm đồng bộ và memory model tương ứng.
- Nếu initialization thất bại, các thread khác có thể nhận lỗi khởi tạo/liên kết thích hợp chứ không tự chạy lại static initializer.

Class identity gồm **binary name + defining class loader**. Hai defining loaders có thể tạo hai runtime classes cùng tên, nhưng trạng thái initialization **riêng biệt**. Một plugin được load lại bằng loader mới có thể chạy static initializers riêng của lớp mới, nhưng đây **không** phải “reset class” trong loader cũ.

Đặc biệt trong kiến trúc plugin, `Thread.currentThread().getContextClassLoader()` là loader theo **ngữ cảnh thread**, không tự động thay defining loader của class đã nạp. `Class.forName(name)` không mặc định dùng TCCL; nếu muốn plugin loader thì truyền tường minh vào `Class.forName(name, initialize, pluginLoader)`.

## 14. Các lỗi suy luận phổ biến

| Ngộ nhận | Giải thích đúng |
| --- | --- |
| “Lấy `Class<?>` nghĩa là static block đã chạy” | Loading/metadata và initialization tách biệt |
| “`SomeClass.class` là active use giống `new SomeClass()`” | Class literal không buộc initialize component class |
| “`new SomeClass[10]` tạo 10 instances SomeClass” | Chỉ tạo array, mỗi phần tử reference khởi đầu là `null` |
| “`instanceof` hoặc cast kích hoạt `<clinit>` của target” | Đây là kiểm tra kiểu, không phải trigger initialize |
| “`ClassLoader.loadClass` luôn gọi static initializer” | Contract mặc định không yêu cầu initialization |
| “`Class.forName(name)` và `Class.forName(name,false,loader)` giống nhau” | Overload một tham số yêu cầu init, overload false không |
| “`Class.forName(...,false,...)` bảo đảm lớp vẫn chưa init khi method trả về” | Một luồng hoặc active use khác có thể init đồng thời |
| “Mọi `static final` đều là compile-time constant” | Chỉ field primitive/`String` final với constant expression |
| “`Child.staticField` luôn initialize Child” | JVM xét **declaring class** của member đã resolve |
| “Một class implements interface là interface đã initialize” | Phụ thuộc default methods và active uses, không đúng tổng quát |
| “Lấy reflection `Method` tương đương gọi method đó” | Metadata lookup không bằng invocation |
| “`getstatic` và `ldc` hằng số class tương đương nhau” | Một cái truy cập static field, cái kia tải constant/class metadata |
| “Class chỉ chạy `<clinit>` một lần toàn JVM dù có nhiều loaders” | Trạng thái theo runtime class và defining loader |
| “Init lỗi thì lần sau làm lại `<clinit>`” | Lớp có thể erroneous và ném lỗi khác lần sau |
| “Không thấy log static block tức lớp chưa load” | Loading có thể đã xảy ra từ trước mà chưa init |
| “`Class.forName(module,name)` cũng initialize” | Overload theo `Module` không có cùng contract đó |

## 15. Checklist khi thiết kế hoặc debug

1. **Lớp đích có được initialize trước chưa?** Đã có active use hoặc initialization gián tiếp qua superclass/default superinterface chưa?
2. **Thao tác trực tiếp là gì?** `new`, `invokestatic`, `getstatic`, `putstatic`, reflection invocation, hay chỉ `ldc` class literal, `loadClass`, `instanceof`, `anewarray`?
3. **Static field là constant variable thật hay chỉ `static final`?** Kiểm tra kiểu và constant expression; không dựa vào tên `FINAL`.
4. **Thành viên thực sự do lớp nào khai báo?** `Child.value` có thể liên kết tới `Parent.value`.
5. **Tên lớp và loader đúng chưa?** Binary name, nested class dấu `$`, module/classpath, defining loader và TCCL có thể khác nhau.
6. **Đang quét metadata hay bắt đầu chạy plugin?** Có cần `Class.forName(name,false,loader)` trước rồi mới tạo object/initialize tường minh không?
7. **Có đọc static field qua reflection hoặc gọi static method handle không?** Những thao tác này có semantics khác với chỉ lấy metadata.
8. **Class có static initializer chậm hoặc gây side effect không?** Tránh network/blocking lock/đăng ký tài nguyên không kiểm soát trong `<clinit>`.
9. **Nếu lỗi xảy ra lần thứ hai, lỗi đầu tiên là gì?** Lưu cause của `ExceptionInInitializerError`; đừng chỉ thấy `NoClassDefFoundError` rồi kết luận thiếu JAR.
10. **Mình đang đọc contract hay chi tiết compiler?** Dùng JLS/JVMS làm nguồn; `javap` hỗ trợ minh họa, không quyết định chính sách initialization.

## 16. Bài tập tự đánh giá

**Câu 1.** `Class<?> c = Widget.class;` có làm `Widget.<clinit>` chạy không?  
**Không**, không do riêng class literal.

**Câu 2.** `Widget[] xs = new Widget[100];` có làm `Widget` initialize không?  
**Không**, nếu chỉ tạo array of references; khi code thực sự tạo `new Widget()` thì khác.

**Câu 3.** `Class.forName("p.Widget", false, loader)` trả về `Class<?>`. Lớp đã chắc chắn khởi tạo chưa?  
**Không**. Lời gọi này không yêu cầu init; trạng thái thực tế còn phụ thuộc active uses khác.

**Câu 4.** `static final int X = 5;` và `static final int Y = compute();`, đọc field nào có thể kích hoạt initialization?  
**Y** là nonconstant static field; đọc Y yêu cầu init nếu chưa có. X là constant variable, phép đọc bình thường không.

**Câu 5.** `Sub extends Base`, `Sub.counter` tham chiếu field static khai báo trong Base. Lớp nào được initialize trực tiếp bởi phép đọc?  
**Base**, không nhất thiết Sub.

**Câu 6.** `Constructor.newInstance` tạo object qua reflection khi class chưa initialized. Có chạy initializer trước?  
**Có**, class cần được initialized theo thủ tục JVM trước khi instance construction.

**Câu 7.** `getDeclaredMethod` và `Method.invoke` có cùng điều kiện initialization?  
**Không**. Lấy metadata không giống thực thi static method qua reflection.

**Câu 8.** Nếu class vừa fail ở `<clinit>`, lần gọi `Class.forName(name)` tiếp theo trong cùng loader có khởi tạo lại từ đầu?  
**Không**; class erroneous, có thể báo `NoClassDefFoundError`.

**Câu 9.** Có thể lấy `Class<?>` của một interface mà chưa initialize interface đó?  
**Có**. Loading/metadata tách biệt với initialization; tuy nhiên đọc một static field khôngconstant hoặc các active uses khác có thể trigger.

## Nguồn chuẩn Java SE 17

- [JLS 12.2 — Loading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2): loading và class loader.
- [JLS 12.3 — Linking of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.3): verification, preparation, resolution.
- [JLS 12.4.1 — When Initialization Occurs](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1): các trigger bắt buộc và ví dụ superclass/static fields.
- [JLS 12.4.2 — Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2): đồng bộ, initialization trạng thái thành công/thất bại.
- [JLS 4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4) và [15.29 — Constant Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.29): định nghĩa constant variable.
- [JVMS 5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3): defining loader/initiating loader.
- [JVMS 5.4 — Linking](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4): verification, preparation và resolution.
- [JVMS 5.5 — Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5): chính xác các instruction active use, method handles, superclasses/default-method superinterfaces, initialization states.
- [`Class` API Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `forName`, class literal, reflection metadata.
- [`ClassLoader` API Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass` và `resolveClass`.
- [Java Reflection `Method`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html), [`Constructor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html) và [`Field`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html): metadata vs invocation/access.
- [`javap` Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): quan sát mã bytecode `new`/`getstatic`/`ldc`/`invokestatic`.

**Ghi nhớ:** **Loading giúp JVM biết một kiểu tồn tại; linking kiểm tra và chuẩn bị kiểu; initialization mới là bước kích hoạt static initialization code.** Muốn dự đoán `<clinit>`, hãy xác định **active use**, **declaring class**, **constant variable**, **superclass/default interface dependencies**, trạng thái initialization và loader — không chỉ nhìn xem tên lớp đã xuất hiện trong source hoặc constant pool hay chưa.
