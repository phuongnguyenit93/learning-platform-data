# 1.7. Kiến thức nền và môi trường thực hành với các API chuẩn Java 21

> **Bối cảnh:** Đây là bài nhập môn của nhóm **Tổng quan** thuộc Java Advance – dynamic-runtime. Bài dùng các API và công cụ **chuẩn JDK 21** để hình thành nền tảng về kiểu tại runtime, nạp lớp, khám phá metadata, gọi phương thức động và dựng môi trường thử nghiệm. Không cần framework, bytecode generator hay thư viện bên ngoài.

## 1. Mục tiêu học tập và điều kiện tiên quyết

Sau bài học, bạn có thể:

1. Giải thích **compile time** khác **runtime**, phân biệt đa hình thông thường với tra cứu/gọi thành viên bằng tên lúc chạy.
2. Phân biệt các giai đoạn **loading – linking – initialization**, ý nghĩa của `Class<?>`, class loader và module.
3. Nhận diện đúng các nhóm API `Class`, `java.lang.reflect`, `java.lang.invoke`, `Proxy`, `ServiceLoader` và chọn công cụ tương ứng.
4. Tự cài/kiểm tra JDK 21, biên dịch và chạy ví dụ thuần Java, sử dụng `jshell`, `javap`, `jdeps` và log class loading.
5. Chẩn đoán lỗi do thiếu class, sai chữ ký, access control, module path và bytecode không tương thích.

Bạn nên biết class/interface, overriding, ngoại lệ, `static`, Java generics cơ bản và cách dùng terminal. Hai lab có mã nguồn độc lập, không phụ thuộc Spring, Maven hoặc Gradle.

## 2. Java “động” ở runtime theo nghĩa nào?

Xem lời gọi quen thuộc:

```java
Greeter greeter = new Greeter();
String message = greeter.greet("An");
```

Compiler kiểm tra kiểu `Greeter` và lời gọi `greet`. Nếu phương thức instance có override, JVM có thể chọn implementation theo **kiểu thực của đối tượng** khi chạy (*dynamic dispatch*). Đây vẫn là chương trình Java có kiểm tra kiểu tĩnh.

Ở những cơ chế như plugin, serializer, dependency injection, test runner hoặc RPC adapter, tên lớp hay tên phương thức đôi khi chỉ được biết từ cấu hình hoặc metadata. Chương trình cần thêm khả năng **tìm lớp**, **đọc cấu trúc**, **gọi thành viên gián tiếp** hoặc **tạo implementation của interface lúc chạy**. Đó là các nhu cầu thường gọi là *dynamic runtime*.

```text
Nguồn .java --javac--> bytecode .class
                              |
                              v
                    JVM tải và liên kết lớp
                              |
                              v
                    Class<?> / metadata / Module
                         /         \
                        v           v
                  Reflection    MethodHandle
                         \         /
                          v       v
                      Gọi thành viên
                              |
                       Proxy / SPI khi cần
```

Sơ đồ chỉ mô tả hướng học. JVM không bắt buộc tải, resolve và khởi tạo mọi class cùng lúc.

### 2.1. Loading, linking và initialization

- **Loading:** JVM tìm định nghĩa nhị phân của một lớp và tạo đối tượng biểu diễn kiểu tương ứng. *Binary name* của lớp và class loader định nghĩa nó là thành phần quan trọng của **danh tính runtime**.
- **Linking:** gồm *verification* (kiểm tra cấu trúc/tính hợp lệ), *preparation* (cấp phát bộ nhớ và giá trị mặc định cho biến `static`) và *resolution* (giải các symbolic references; có thể thực hiện theo nhu cầu). Linking không đồng nghĩa việc chạy mọi static initializer của ứng dụng.
- **Initialization:** JVM thực thi việc khởi tạo kiểu theo quy tắc ngôn ngữ/JVM, trong đó có các khối `static`. Ví dụ `Class.forName("java.lang.String")` yêu cầu khởi tạo lớp; phiên bản `Class.forName(name, false, loader)` không yêu cầu khởi tạo ngay.

Không suy rằng `Class<?>` cho phép tự ý sửa mọi class đang chạy. Nó chủ yếu đại diện cho **kiểu và metadata**, vẫn chịu ràng buộc của type system, access control và Java Platform Module System (JPMS).

### 2.2. Tên lớp trong mã và tên nhị phân

- `java.util.ArrayList` là tên nhị phân của lớp `ArrayList`.
- Một lớp lồng nhau `Outer.Inner` thường có binary name dạng `Outer$Inner`.
- Tên hiển thị của kiểu, simple name, canonical name và binary name không phải lúc nào cũng thay thế được cho nhau. Khi gọi `Class.forName`, phải dùng tên được API yêu cầu.

## 3. Bản đồ các API và công cụ JDK 21

| Nhiệm vụ | API chuẩn | Điểm cần nhớ |
| --- | --- | --- |
| Biểu diễn và tìm kiếm kiểu | `java.lang.Class`, `ClassLoader` | `Class.forName` tra cứu bằng tên; loader có thể ảnh hưởng danh tính kiểu. |
| Xem method, field, constructor, annotation | `java.lang.reflect.Method`, `Field`, `Constructor`, `Annotation` | Phân biệt `getMethod` với `getDeclaredMethod`; quyền truy cập vẫn được áp dụng. |
| Gọi method hay constructor linh hoạt | `Method.invoke`, `Constructor.newInstance` | Kết quả thường là `Object`; lỗi trong method đích được bọc bởi `InvocationTargetException`. |
| Tham chiếu/gọi phương thức với chữ ký có kiểu | `java.lang.invoke.MethodHandle`, `MethodHandles.Lookup`, `MethodType` | `invokeExact` yêu cầu kiểu ở vị trí gọi khớp chính xác kiểu handle. |
| Truy cập biến thông qua handle | `java.lang.invoke.VarHandle` | Cho phép các access mode được định nghĩa cho loại biến, gồm các thao tác liên quan bộ nhớ/concurrency; không cần dùng cho lab cơ bản. |
| Tạo runtime implementation của interface | `java.lang.reflect.Proxy`, `InvocationHandler` | Proxy chuẩn JDK **dựa vào interface**; lời gọi được chuyển qua handler. |
| Khám phá plugin theo hợp đồng service | `java.util.ServiceLoader` | Chỉ tìm provider đã **đăng ký** qua cấu hình SPI hoặc JPMS, không tự quét mọi class. |
| Thông tin module và khả năng truy cập | `java.lang.Module`, `ModuleLayer` | Phân biệt `exports`, `opens`, classpath và module path. |
| Liên kết động cấp JVM | `java.lang.invoke.CallSite`, `invokedynamic` | Chủ đề nền tảng cho các cơ chế nâng cao, không cần tự tạo bytecode trong bài. |
| Chẩn đoán bytecode/runtime | Công cụ `java`, `javac`, `jshell`, `javap`, `jdeps`, `jcmd` | Đây là executable của JDK, không phải package Java để import. |

Một số bài về dynamic runtime sẽ đi sâu `java.lang.instrument` hoặc cơ chế nạp agent. Agent là môi trường triển khai riêng; bạn **không** cần agent cho hai lab và không nên nhầm reflection với sửa bytecode. Ưu tiên Java SE API công khai, tránh dựa vào `sun.*`/`jdk.internal.*`.

## 4. Chuẩn bị môi trường thực hành Java 21

### 4.1. JDK, JAVA_HOME và PATH

Cài một bản phân phối **JDK 21** phù hợp hệ điều hành. `JAVA_HOME` nên trỏ tới thư mục JDK; biến `PATH` cần chứa thư mục `bin` của chính JDK đó. Mở terminal mới và chạy:

```sh
java -version
javac -version
jshell --version
```

Cả `java` và `javac` phải hiện phiên bản chính **21**; số bản vá và tên nhà phân phối có thể khác nhau. Nếu có nhiều JDK, kiểm tra executable thật sự được chọn:

| Hệ điều hành | Lệnh |
| --- | --- |
| Windows PowerShell/CMD | `where.exe java` và `where.exe javac` |
| macOS/Linux | `command -v java` và `command -v javac` |

`java` dùng để chạy, `javac` dùng để biên dịch, `jshell` là REPL. Không được nhầm “đã cài JDK 21” với “terminal đang chạy Java 21”.

### 4.2. Tổ chức thư mục làm lab

Tạo thư mục `dynamic-runtime-lab` ở vị trí thực hành của bạn. Lưu hai file độc lập `RuntimeBasicsLab.java` và `ProxyLab.java` vào đó, định dạng UTF-8. Mỗi lab có một `public class` trùng tên file. Chạy lệnh bên dưới **từ thư mục này**.

Chúng ta đang dùng **classpath mặc định** (unnamed module), chưa viết `module-info.java`, vì mục tiêu là hiểu API trước khi thêm ràng buộc module. Dùng `javac --release 21` để compiler giới hạn cú pháp/API theo Java 21; muốn chạy ổn định vẫn cần Java runtime phù hợp.

### 4.3. Thử ngay bằng JShell

Chạy `jshell`, sau đó nhập từng biểu thức:

```java
Class.forName("java.lang.String").getName()
String.class.getModule().getName()
String.class.getClassLoader()
```

Bạn sẽ thấy tên `java.lang.String`, module `java.base` và giá trị `null` cho class loader của `String`. `null` ở đây biểu thị **bootstrap class loader**, không phải lỗi. Dòng prompt, số biến tạm và cách JShell hiển thị kết quả có thể thay đổi. Gõ `/exit` để kết thúc.

## 5. Lab 1: Reflection và MethodHandle gọi cùng một phương thức

Lưu đầy đủ nội dung sau vào **`RuntimeBasicsLab.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;

public class RuntimeBasicsLab {
    public static class Welcome {
        public String greet(String name) {
            return "Xin chào, " + name + "!";
        }
    }

    public static void main(String[] args) throws Throwable {
        Class<?> type = Class.forName("RuntimeBasicsLab$Welcome");
        Object instance = type.getDeclaredConstructor().newInstance();

        Method reflected = type.getMethod("greet", String.class);
        String viaReflection = (String) reflected.invoke(instance, "An");

        MethodHandle handle = MethodHandles.lookup().findVirtual(
            Welcome.class,
            "greet",
            MethodType.methodType(String.class, String.class)
        );
        String viaHandle =
            (String) handle.invokeExact((Welcome) instance, "Bình");

        System.out.println("Class: " + type.getName());
        System.out.println("Reflection: " + viaReflection);
        System.out.println("MethodHandle: " + viaHandle);
    }
}
```

Biên dịch/chạy:

```sh
javac --release 21 RuntimeBasicsLab.java
java RuntimeBasicsLab
```

**Stdout chính xác:**

```text
Class: RuntimeBasicsLab$Welcome
Reflection: Xin chào, An!
MethodHandle: Xin chào, Bình!
```

### 5.1. Giải thích từng dòng có ý nghĩa động

1. `Class.forName("RuntimeBasicsLab$Welcome")` dùng **binary name** của nested class để lấy `Class<?>` trong lúc chạy. Dấu `$` ở đây là một phần tên lớp, không phải biến shell.
2. `getDeclaredConstructor().newInstance()` lấy constructor không tham số rồi tạo object. Ở đây nested class `Welcome` là `public static`, không cần một receiver của outer class.
3. `getMethod("greet", String.class)` chỉ định tên method và danh sách kiểu tham số; phương thức đang tìm là `public`. `reflected.invoke(instance, "An")` trả `Object` nên chúng ta cast về `String`.
4. `MethodHandles.lookup()` tạo đối tượng `Lookup` mang quyền của lớp gọi; `findVirtual` nhận class, tên method và `MethodType` gồm kiểu trả về + kiểu các tham số được khai báo. Vì là method instance, **handle** nhận receiver `Welcome` làm đối số đầu, tạo chữ ký thực tế `(Welcome, String)String`.
5. `invokeExact` là lời gọi *signature-polymorphic*: compiler ghi nhận kiểu tại điểm gọi. Cast `(Welcome) instance` và cast `(String)` cho kết quả giúp kiểu receiver/return type khớp chính xác với handle. Nếu đổi kiểu không tương thích, có thể phát sinh `WrongMethodTypeException`.
6. Cả hai cách đều gọi `Welcome.greet`. Khác nhau là cách tra cứu, mô hình chữ ký, quy tắc gọi và xử lý lỗi.

Trong lab, `main throws Throwable` giúp tập trung vào API. Mã production cần xử lý ngoại lệ có phạm vi rõ ràng; tránh dùng `throws Throwable` tùy tiện.

### 5.2. Khi nào dùng cách nào?

- **Gọi trực tiếp** khi compile time đã biết interface/class và phương thức; mã rõ ràng, refactor được và compiler kiểm tra tốt nhất.
- **Reflection** khi cần khám phá metadata, annotation, tên method từ cấu hình, mapping động.
- **MethodHandle** khi cần lưu một lời gọi có kiểu, thích nghi chữ ký, kết hợp các thao tác trong `java.lang.invoke` hoặc xử lý logic gọi động mức thấp.

Không mặc định `MethodHandle` luôn nhanh hơn Reflection; tối ưu JIT, cache, warm-up và kiểu benchmark quyết định kết quả. Không so sánh hiệu năng bằng vài vòng lặp thủ công rồi đưa kết luận tổng quát.

## 6. Lab 2: Dynamic proxy chuẩn JDK

Lưu nội dung sau vào **`ProxyLab.java`**:

```java
import java.lang.reflect.Proxy;

public class ProxyLab {
    public interface Greeting {
        String say(String name);
    }

    public static void main(String[] args) {
        Greeting proxy = (Greeting) Proxy.newProxyInstance(
            Greeting.class.getClassLoader(),
            new Class<?>[] { Greeting.class },
            (instance, method, arguments) -> {
                if (method.getName().equals("say")) {
                    return "Chào, " + arguments[0] + "!";
                }
                if (method.getName().equals("toString")) {
                    return "GreetingProxy";
                }
                throw new UnsupportedOperationException(method.toString());
            }
        );

        System.out.println(proxy.say("Mai"));
    }
}
```

Chạy:

```sh
javac --release 21 ProxyLab.java
java ProxyLab
```

**Stdout:**

```text
Chào, Mai!
```

`Proxy.newProxyInstance` trả về object thực thi interface `Greeting` dù bạn không khai báo `GreetingImpl`. Lời gọi `proxy.say("Mai")` được định tuyến đến `InvocationHandler` cùng metadata `Method` và mảng đối số; handler trả `String` theo hợp đồng interface. Đây là cách dựng runtime implementation của **interface**, không tự động tạo subclass tùy ý.

Trong ứng dụng thật, handler phải xử lý đúng `equals`, `hashCode`, `toString` và phương thức mặc định của interface khi liên quan; cần đảm bảo kết quả đúng kiểu và ngoại lệ không bị che giấu. Lab chỉ cài các nhánh cần minh họa.

## 7. ClassLoader và JPMS: hai yếu tố thay đổi kết quả runtime

### 7.1. Danh tính một lớp

Trong Java, hai lớp có **cùng binary name** nhưng được *defining class loaders* khác nhau định nghĩa có thể là **hai runtime types khác nhau**. Đây là lý do plugin hoặc ứng dụng nhúng có thể gặp `ClassCastException` dù log hiển thị “cùng tên lớp”.

Những API cần phân biệt:

| Lệnh/API | Cách hiểu đúng |
| --- | --- |
| `obj.getClass()` | Lấy runtime class của object đã có. |
| `SomeType.class` | Lấy đối tượng `Class` khi kiểu được biết trực tiếp ở compile time. |
| `Class.forName(name)` | Tra cứu bằng tên và yêu cầu class initialization. |
| `Class.forName(name, false, loader)` | Tra cứu với loader cụ thể, không yêu cầu initialize tại lời gọi này. |
| `ClassLoader.loadClass(name)` | Tải/tìm class theo hợp đồng loader; không đồng nghĩa luôn initialize class. |
| `Thread.currentThread().getContextClassLoader()` | Context loader do môi trường/caller cung cấp, thường hữu ích cho SPI/framework; không mặc định trùng loader của class đang chạy. |

Phần lớn loader của Java dùng cơ chế ủy quyền cho parent trong quá trình tìm class, nhưng không nên coi mọi hệ thống loader tùy biến đều vận hành giống nhau. Đối với `Class.getClassLoader()`, giá trị `null` hợp lệ cho class do bootstrap loader định nghĩa.

### 7.2. Classpath khác module path

Hai lab đang chạy trên **classpath** và thuộc *unnamed module*. Trong ứng dụng JPMS với `module-info.java`, cần thêm ngữ nghĩa:

- `requires`: khai báo module phụ thuộc.
- `exports`: cho phép module khác truy cập các public types theo quy tắc module; không phải giấy phép phản chiếu sâu vào private members.
- `opens`: mở package cho deep reflection có kiểm soát; có thể giới hạn phạm vi với `opens ... to ...`.
- `Module.isExported` và `Module.isOpen`: giúp kiểm tra quyền truy cập module lúc chạy.

`setAccessible(true)` không cho phép phá mọi ranh giới; có thể gặp `InaccessibleObjectException` khi package thuộc module không mở. Sửa bằng thiết kế public SPI, điều chỉnh module descriptor hoặc quyền `Lookup` phù hợp. Cờ JVM `--add-opens` chỉ nên dùng có chủ đích khi tương thích/chẩn đoán, không phải giải pháp mặc định.

### 7.3. ServiceLoader và kiến trúc plugin

`ServiceLoader.load(Service.class)` chỉ phát hiện nhà cung cấp **đã khai báo hợp đồng service**: thông thường bằng file `META-INF/services/<fully-qualified-service-name>` trên classpath, hoặc `uses`/`provides ... with ...` khi dùng named modules. Nó không tự động quét toàn bộ class.

Nhớ ba câu hỏi riêng:

- **Reflection:** “Class này có metadata và method nào; có quyền truy cập/gọi không?”
- **Proxy:** “Có thể dựng implementation của interface và chuyển lời gọi vào handler không?”
- **ServiceLoader:** “Những provider nào đã đăng ký thực hiện interface/service này?”

Nhiều framework dùng phối hợp các cơ chế, nhưng mục tiêu không trùng nhau.

## 8. Quan sát lớp và runtime bằng công cụ JDK 21

Sau khi biên dịch Lab 1, chạy các lệnh sau:

```sh
javap -p RuntimeBasicsLab
javap -c RuntimeBasicsLab
jdeps RuntimeBasicsLab.class
java -Xlog:class+load=info RuntimeBasicsLab
```

| Công cụ | Ý nghĩa | Cảnh báo diễn giải |
| --- | --- | --- |
| `javap -p` | Xem chữ ký và thành viên class file, kể cả non-public. | Không nói phương thức nào đã thực sự chạy. |
| `javap -c` | Xem bytecode đã biên dịch; đối chiếu lời gọi API trong `main`. | Bytecode không cho biết mọi tối ưu runtime của JIT. |
| `jdeps` | Phân tích phụ thuộc bytecode/class/module nhìn thấy tĩnh. | Không thể bảo đảm thấy mọi class chỉ nạp bằng tên chuỗi tại runtime. |
| `-Xlog:class+load=info` | Bật JVM unified logging cho việc nạp lớp. | Log có thể rất dài và khác giữa các bản JVM; không xem đó là stdout cố định của lab. |
| `jcmd -l` | Liệt kê tiến trình JVM mà công cụ có thể phát hiện. | Kết quả phụ thuộc quyền và các JVM đang chạy. |
| `java --list-modules` | Liệt kê module observable của runtime image. | Ứng dụng trên classpath vẫn có thể thuộc unnamed module. |

Đừng trộn lẫn **stdout của chương trình**, **stderr**, **dòng log JVM** và **output của công cụ** khi ghi kết quả thí nghiệm. Chạy lại không có cờ log để xác nhận stdout chuẩn của Lab 1.

## 9. Bảng chẩn đoán các lỗi phổ biến

| Lỗi/hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| `ClassNotFoundException` | Tên binary sai hoặc loader/classpath không tìm được định nghĩa. | Kiểm tra tên, dấu `$` của nested class, vị trí `.class`, classpath/module path và loader. |
| `NoClassDefFoundError` | Class phụ thuộc thiếu lúc chạy hoặc lần initialization trước đã thất bại. | Xem thông báo và *cause gốc*, kiểm tra dependency runtime và lỗi xảy ra đầu tiên. |
| `NoSuchMethodException` | Sai tên, overload, kiểu tham số hoặc dùng nhầm public/declared lookup. | So `getMethod` với `getDeclaredMethod`, in parameter types và kiểm tra `javap`. |
| `IllegalAccessException` / `InaccessibleObjectException` | Java access rule hoặc JPMS không cho phép truy cập. | Kiểm tra member visibility, `Lookup`, `exports` và `opens`. |
| `InvocationTargetException` | Target method được gọi qua reflection đã ném exception. | Xem `getCause()` để tìm lỗi thật của target. |
| `WrongMethodTypeException` | Kiểu đối số/kiểu trả về ở điểm gọi handle không phù hợp, đặc biệt với `invokeExact`. | In `handle.type()`; kiểm tra receiver, số tham số và kiểu return. |
| `UnsupportedClassVersionError` | Runtime không hiểu class file version vừa biên dịch. | Kiểm tra `java -version` thực tế; class file Java 21 có major version **65**. |
| Proxy trả kết quả sai | Handler xử lý thiếu method hoặc trả kiểu không đúng. | Kiểm tra `method.getName()`, chữ ký và hợp đồng interface. |

Quy trình gỡ lỗi hiệu quả: xác định exception và *cause* → tái hiện bằng lệnh cố định → kiểm tra phiên bản và classpath/module path → xác minh tên/chữ ký bằng metadata/`javap` → chỉ đổi một giả định → chạy lại.

## 10. Bài tập vận dụng

**Bài A — metadata:** Dùng `Class.forName("java.util.ArrayList")`, in `getName()`, `getSuperclass()`, `getInterfaces()`. Giải thích vì sao danh sách interface trực tiếp không nhất thiết gồm mọi interface kế thừa.

**Bài B — kiểm chứng initialization:** Tạo một class mới với `static { System.out.println("initialized"); }`. So sánh `Class.forName(name, false, loader)` và `Class.forName(name)` trong **hai JVM mới riêng biệt**. Việc class đã initialize trước đó trong cùng JVM sẽ làm sai kết luận nếu bỏ qua.

**Bài C — handle type:** In `handle.type()` của Lab 1, đối chiếu kiểu receiver + tham số + return. Thử thay sai một kiểu rồi ghi exception; cuối cùng hoàn nguyên và đối chiếu stdout chính xác.

**Bài D — proxy:** Thêm method `String farewell(String name)` vào `Greeting`, mở rộng handler để trả lời đúng cả `say` và `farewell`. Tự nêu stdout dự kiến trước khi chạy.

**Bài E — diagnostics:** Quan sát `javap -c RuntimeBasicsLab`, tìm vị trí gọi Reflection và MethodHandle; chạy lại với JVM class-load log. Phân biệt kết quả chương trình với log nạp class.

### Tự đánh giá

- [ ] `java` và `javac` đều thực sự là Java 21.
- [ ] Hai chương trình biên dịch bằng `javac --release 21` và có stdout như mô tả.
- [ ] Nêu được khác nhau giữa loading, linking, initialization.
- [ ] Giải thích tại sao một tên lớp có thể đại diện hai runtime types khi defining loader khác nhau.
- [ ] Phân biệt rõ Reflection, MethodHandle, Proxy, ServiceLoader.
- [ ] Nêu ít nhất ba lỗi điển hình và cách kiểm tra đúng nguyên nhân.
- [ ] Hiểu giới hạn JPMS khi truy cập reflective, không mặc định phá quyền truy cập.

## 11. Nguyên tắc thực hành an toàn

1. Khi tên lớp/method đến từ người dùng hay cấu hình ngoài, dùng danh sách cho phép và kiểm tra interface/contract; đừng khởi tạo hay gọi thứ gì chỉ từ một chuỗi không tin cậy.
2. Reflection và handle phải tôn trọng Java access control và ranh giới module. Thiết kế public extension point thích hợp trước khi nghĩ đến deep reflection.
3. Dynamic runtime tăng linh hoạt nhưng cũng tăng rủi ro sai tên, sai type và khó debug. Chọn cách gọi trực tiếp khi có thể, dùng cơ chế động khi yêu cầu thực sự cần.
4. Với plugin/class loader thực tế, chú ý reference/caches, thread context loader, resource lifecycle và unloadability. `System.gc()` không bảo đảm class được unload.
5. Cờ logging và chẩn đoán có thể tạo rất nhiều output, đôi khi chứa thông tin nhạy cảm của môi trường; gỡ chúng sau khi thử nghiệm.

## 12. Tài liệu chuẩn để tiếp tục tra cứu

- [Java SE 21 — Class](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html)
- [Java SE 21 — Reflection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/package-summary.html)
- [Java SE 21 — MethodHandles](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.html)
- [Java SE 21 — Dynamic Proxy](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Proxy.html)
- [Java SE 21 — ServiceLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html)
- [JDK 21 — javac](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html) và [JDK 21 — java](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)

**Kết nối với các bài sau:** Những lab này là đường chuẩn để phân tích sâu class loading, reflection, method handles, proxy, SPI hoặc liên kết động. Khi chuyển sang module/plugin thật, hãy đối chiếu mỗi hành vi mới với phiên bản thuần Java 21 đã chạy được.
