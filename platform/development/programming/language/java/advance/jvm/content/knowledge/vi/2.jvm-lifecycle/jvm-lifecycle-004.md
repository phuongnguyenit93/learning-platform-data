# Khởi động JVM, khởi tạo lớp đầu tiên và gọi main theo phiên bản Java

## 1. Bức tranh tổng thể

Khi chạy lệnh `java ...`, **JVM không nhảy ngay vào dòng đầu tiên của `main`**. Java launcher xác định chương trình cần chạy, thiết lập JVM và môi trường runtime; VM nạp, liên kết, khởi tạo initial class/interface rồi mới gọi một phương thức `main` hợp lệ. Dù `main` là điểm bắt đầu logic của ứng dụng, một số lớp của JDK và các `static initializer` cần thiết có thể thực thi trước đó.

~~~text
Shell / OS
   |
   | java [VM options] <main-class | -jar JAR | -m module[/class] | File.java> [app args]
   v
Java launcher: chọn cách khởi chạy, chuẩn bị JVM và môi trường
   |
   v
Xác định initial class / interface
   |
   v
Load class -> Link (Verify + Prepare + Resolve khi cần)
   |
   v
Initialize initial class (và superclasses / superinterfaces cần thiết)
   |   thực thi static field initializers, static blocks
   v
Chọn candidate main theo phiên bản Java
   |
   +---- static main ------> gọi trực tiếp
   |
   +---- instance main ---> tạo object với constructor không tham số
   |                         rồi gọi main trên object
   v
Ứng dụng chạy; các class khác có thể được load/initialize khi cần
~~~

Trong sơ đồ, **initial class** có nghĩa là loại ứng dụng được chọn làm đầu vào, **không phải lớp đầu tiên được JVM nạp trên toàn bộ đời process**. JVM đã có thể tải, liên kết hoặc khởi tạo nhiều lớp nền tảng trước khi ứng dụng được gọi. Cách chọn initial class có thể khác giữa class path, JAR, module, source-file launcher, và cả các môi trường nhúng JVM.

Bài học cần phân biệt ba thao tác:

- **Loading:** tìm/định nghĩa biểu diễn runtime của class hoặc interface.
- **Linking:** xác minh bytecode, chuẩn bị bộ nhớ trạng thái tĩnh, giải quyết tham chiếu biểu tượng theo quy tắc JVM.
- **Initialization:** chạy các biểu thức khởi tạo `static` và `static { ... }`, có thể kích hoạt khởi tạo các lớp liên quan.

Loading hoặc linking **không tự động đồng nghĩa** các `static initializer` đã chạy.

## 2. Ai chọn lớp ban đầu?

Theo **JLS `12.1** và **JVMS `5.2**, JVM bắt đầu thực thi chương trình bằng cách sử dụng một **initial class or interface** và gọi `main` tương ứng. Cách xác định initial class là chuyện của môi trường khởi chạy, thông dụng nhất là công cụ `java` thuộc JDK.

| Cách khởi chạy | Ví dụ | Cách chọn ứng dụng |
| --- | --- | --- |
| Class path | `java -cp out demo.App alpha beta` | Tên nhị phân của lớp `demo.App` |
| Executable JAR | `java -jar app.jar alpha` | `Main-Class` trong manifest của JAR |
| Named module | `java -m demo.app/demo.App alpha` | Main class được chọn trong module; có thể dùng main class được ghi trong module nếu bỏ `/demo.App` |
| Source-file mode, Java 11+ | `java App.java alpha` | Launcher biên dịch source rồi chọn lớp đầu vào từ file source |
| Compact source, Java 25+ | `java Hello.java` với `void main() { ... }` | Compiler tạo implicit class để JVM gọi `main` |

Ở class path:

~~~bash
java -Xmx256m -Dapp.mode=test -cp out demo.App first second
~~~

`-Xmx256m` là VM option, `-Dapp.mode=test` là system property, `-cp out` là đường tìm class, `demo.App` là lớp ban đầu. Hai token `first`, `second` đứng **sau tên lớp** là đối số ứng dụng: `args[0]` và `args[1]` nếu phương thức `main(String[])` được gọi. `-Xmx256m` đặt sau `demo.App` sẽ bị hiểu là đối số ứng dụng, không còn là tùy chọn khởi động VM.

Source-file launcher (`java App.java`) **biên dịch Java source trong khi khởi chạy rồi chạy class kết quả**, không có nghĩa JVM trực tiếp thông dịch source text `.java`. Còn khi chạy class đã biên dịch (`java App`), JVM lấy bytecode phù hợp từ class path/module path.

## 3. Nạp, liên kết và khởi tạo initial class

### Loading: tìm và định nghĩa lớp

Runtime có thể tải một class từ JAR, module, file `.class`, nguồn code được compiler sinh, hoặc custom class loader. Identity của một runtime class dựa trên **tên nhị phân và defining class loader**; vì vậy hai loader khác nhau có thể định nghĩa hai class cùng tên nhưng là hai class runtime riêng biệt.

Loading chỉ tạo điều kiện cho những bước tiếp theo; không đủ để khẳng định `static { System.out.println("loaded"); }` đã chạy. Tên class không tìm thấy, class file bị hỏng hoặc phiên bản class file không được VM hỗ trợ có thể làm startup thất bại ở giai đoạn này hoặc các giai đoạn liên quan.

### Linking: Verify, Prepare, Resolve

- **Verify:** class file/bytecode đáp ứng các quy tắc về định dạng và tính hợp lệ của máy ảo.
- **Prepare:** cấp phát và gán **giá trị mặc định** cho các biến `static` (`0`, `false`, `null`…), xử lý các hằng compile-time theo đặc tả. Đừng hiểu “prepare” là đã chạy mọi biểu thức khai báo field.
- **Resolve:** ánh xạ symbolic references (các chỉ mục/tên tượng trưng trong constant pool) sang các tham chiếu runtime cụ thể. Runtime có thể làm sớm hoặc trì hoãn; **không nhất thiết toàn bộ references đều resolve trước `main`**.

Ví dụ:

~~~java
static int count = calculate();
~~~

Khi prepare, `count` có giá trị mặc định của `int`. Biểu thức `calculate()` chỉ chạy tại thời điểm class **initialize** (trong quá trình initialization theo quy tắc Java), không phải vì loading vừa hoàn tất.

### Initialization: trước main và có thứ tự

Với class thông thường, các quy tắc chính:

1. Khởi tạo các **superclass** cần thiết trước class con. Một số superinterface khai báo default method cũng có thể cần khởi tạo theo quy tắc JLS `12.4`.
2. Chạy static field initializers và static initialization blocks của class **theo thứ tự văn bản nguồn**.
3. Với mỗi runtime class identity, initialization thành công không được chạy lại chỉ vì có thêm lời gọi method hoặc tạo object mới.
4. VM đồng bộ hoá quá trình initialization khi nhiều thread cố sử dụng class lần đầu. Thread có thể đợi thay vì đồng thời chạy `static` initialization hai lần.

Compiler có thể sinh phương thức đặc biệt `<clinit>` trong class file để thực thi logic khởi tạo class. `<clinit>` **khác** `<init>` (constructor/khởi tạo object) và **khác** `main` (phương thức điểm vào ứng dụng).

Không phải mọi class trong class path đều phải được initialize trước `main`. Class không được sử dụng có thể vẫn chưa khởi tạo; một class khác có thể được khởi tạo trước/sau `main` do active use như `new`, gọi `static` method hoặc đọc `static` field không phải compile-time constant.

## 4. Theo phiên bản Java, main hợp lệ ra sao?

### Java 8–20: chữ ký truyền thống

Mẫu được chấp nhận rộng nhất trong các Java release cũ:

~~~java
public class TraditionalMain {
    public static void main(String[] args) {
        System.out.println("Hello Java");
    }
}
~~~

Có thể viết `String... args` thay cho `String[] args` vì varargs có kiểu mảng `String[]`. Tên biến `args` có thể đổi. Chữ ký truyền thống yêu cầu **`public static`**, trả về **`void`**, và **một tham số `String[]`**. `int main`, `main(int[])` hoặc `static void main()` không phải điểm vào truyền thống.

Mẫu trên vẫn được Java 25+ chấp nhận, và nên dùng trong ứng dụng muốn hỗ trợ rộng các JDK hoặc build tool khác nhau.

### Java 21–24: những lần preview

Java bắt đầu thử nghiệm các cách viết entry `main` ngắn hơn và source file đơn giản hơn:

| Phiên bản | Tình trạng | JEP |
| --- | --- | --- |
| Java 21 | Preview lần đầu | JEP 445 |
| Java 22 | Preview tiếp theo | JEP 463 |
| Java 23 | Preview tiếp theo | JEP 477 |
| Java 24 | Preview lần thứ tư | JEP 495 |
| **Java 25+** | **Ổn định, không cần bật preview cho tính năng này** | **JEP 512** |

Với bản preview 21–24, cần đối chiếu chính xác cú pháp của bản đó, thường biên dịch với `--enable-preview --release N` hoặc `--enable-preview --source N` và chạy bytecode preview với `--enable-preview` trên runtime tương ứng. Không mặc định rằng mọi biến thể syntax preview đều như bản ổn định Java 25.

### Java 25+: ứng viên main mở rộng

Theo **JLS `12.1.4, Java SE 25 trở lên**, candidate `main` khai báo hoặc kế thừa trong initial class/interface phải trả về `void`, tên `main`, access `public` / `protected` / package access (**không phải `private`**), và nhận **một `String[]` hoặc `String...`**, hoặc **không có tham số**. Candidate có thể là **`static` hoặc instance method**, có thể có `throws`.

Các ví dụ chữ ký độc lập có thể dùng làm entry phù hợp:

~~~java
public static void main(String[] args) { } // truyền thống
static void main(String[] args) { }        // package access
protected static void main() { }           // không tham số
void main() { }                            // instance method
public void main(String... args) { }       // instance + varargs
~~~

Đây là **tập hợp chữ ký minh họa**, không phải một file Java chạy độc lập: khi ghép nhiều chữ ký vào cùng một class phải xét overload và quy tắc chọn `main`.

**Luật ưu tiên:** nếu có candidate `main(String[])` thì runtime chọn phiên bản nhận `String[]`. Chỉ khi không có candidate đó, mới chọn `main()` không tham số. Vì thế một **instance `main(String[])` có thể được chọn thay vì `static main()`**; `static` không phải tiêu chí ưu tiên cao hơn tham số. Trong cùng class, static và instance method **cùng chữ ký** không thể đồng thời tồn tại.

Nếu phương thức được chọn là instance `main`, VM tạo một instance initial class bằng constructor không tham số theo quy tắc tương ứng, rồi mới invoke method. Class initialization vẫn **đi trước**; constructor và instance field/block initializers chạy **trước** thân instance `main`. Nếu không thể tạo instance hợp lệ thì startup thất bại trước khi method chạy.

## 5. Ví dụ Java 17+: static initialization trước main

Tạo file `BootOrder.java`:

~~~java
class Parent {
    static int parentValue = mark("1. Parent static field");

    static {
        System.out.println("2. Parent static block");
    }

    static int mark(String message) {
        System.out.println(message);
        return 1;
    }
}

public class BootOrder extends Parent {
    static int childValue = mark("3. Child static field");

    static {
        System.out.println("4. Child static block");
    }

    {
        System.out.println("6. Instance initializer");
    }

    BootOrder() {
        System.out.println("7. Constructor");
    }

    public static void main(String[] args) {
        System.out.println("5. main args = " + String.join(",", args));
        new BootOrder();
    }
}
~~~

Lệnh biên dịch/chạy:

~~~bash
javac BootOrder.java
java BootOrder A B
~~~

**Stdout chính xác:**

~~~text
1. Parent static field
2. Parent static block
3. Child static field
4. Child static block
5. main args = A,B
6. Instance initializer
7. Constructor
~~~

**Giải thích:** Để invoke `BootOrder.main`, VM initialize `BootOrder`. Nó phải initialize `Parent` trước, nên các mốc 1–2 xuất hiện trước 3–4. Sau đó mới gọi `static main`, in mốc 5. Không cần instance `BootOrder` để gọi static main; chính câu lệnh `new BootOrder()` trong main mới gây ra mốc 6–7.

Nếu bỏ `new BootOrder()`, hai dòng cuối biến mất. Kết quả này phân biệt rõ:

- Class initialization: `static` initializer chạy trước `main`.
- Object initialization: instance initializer và constructor chạy khi `new`, **không mặc định** chạy trước một `static main`.
- Thứ tự trên chỉ mô tả các dấu in của class tự viết. Nó không liệt kê mọi lớp nội bộ mà JVM/JDK đã khởi tạo.

Quan sát bytecode:

~~~bash
javap -p -c BootOrder
javap -p -c Parent
~~~

`javap` giúp bạn nhận ra code khởi tạo class (hiện tương ứng `static {}`/`<clinit>`), code constructor và `main`. Không mặc định bytecode offsets/constant-pool indexes giống hệt mọi phiên bản compiler.

## 6. Ví dụ Java 17+: load không phải initialize

Tạo file `LazyInit.java`:

~~~java
class Configuration {
    static final String LABEL = "constant";

    static int PORT = initPort();

    static {
        System.out.println("Configuration static block");
    }

    static int initPort() {
        System.out.println("Configuration initPort");
        return 8080;
    }
}

public class LazyInit {
    public static void main(String[] args) {
        System.out.println("Before: " + Configuration.LABEL);
        System.out.println("Port: " + Configuration.PORT);
    }
}
~~~

~~~bash
javac LazyInit.java
java LazyInit
~~~

**Stdout chính xác:**

~~~text
Before: constant
Configuration initPort
Configuration static block
Port: 8080
~~~

`Configuration.LABEL` là **constant variable** có giá trị literal, có thể được compiler inline nên việc tham chiếu hằng này không bắt buộc class `Configuration` phải initialize. Khi đọc `Configuration.PORT` (field static không phải constant variable), VM khởi tạo class: gọi `initPort()`, chạy `static block` rồi mới in giá trị 8080.

Đừng áp dụng kết luận trên cho mọi `static final`. `static final String V = System.getenv("X")` không phải compile-time constant, nên lần active use field có thể kích hoạt initialization. Tương tự, `Configuration.class` chỉ lấy class literal, không tự khẳng định các static initializer đã chạy.

## 7. Ví dụ Java 25+: instance main và compact source

### A. Instance main buộc tạo object

Tạo `InstanceEntry.java` bằng **JDK 25+**:

~~~java
class InstanceEntry {
    static {
        System.out.println("1. static init");
    }

    {
        System.out.println("2. instance init");
    }

    InstanceEntry() {
        System.out.println("3. constructor");
    }

    void main() {
        System.out.println("4. instance main");
    }
}
~~~

~~~bash
javac InstanceEntry.java
java InstanceEntry
~~~

**Stdout:**

~~~text
1. static init
2. instance init
3. constructor
4. instance main
~~~

Ở đây runtime initialize class trước (mốc 1), **tạo object** bằng constructor không tham số (mốc 2–3), cuối cùng gọi instance `main()` (mốc 4). Không nên diễn đạt “JVM luôn gọi constructor trước `main`”: kết luận đó **chỉ đúng khi entry được chọn là instance main**.

### B. Main nhận String[] thắng main không tham số

Tạo `MainChoice.java` trên JDK 25+:

~~~java
class MainChoice {
    static void main() {
        System.out.println("static no-arg main");
    }

    void main(String[] args) {
        System.out.println("instance args main: " + String.join(",", args));
    }
}
~~~

~~~bash
javac MainChoice.java
java MainChoice x y
~~~

**Stdout:**

~~~text
instance args main: x,y
~~~

Runtime chọn `main(String[])` dù phương thức đó là instance và dù có `static main()`: **dạng có tham số được ưu tiên**. Runtime tạo instance bằng constructor không tham số mặc định; ví dụ không in dấu vết constructor. Nếu xóa `main(String[])`, `static main()` trở thành entry.

### C. Compact source file: Java source ngắn, VM vẫn chạy class

Tạo `Hello.java` (Java 25+):

~~~java
void main() {
    System.out.println("Hello from compact source");
}
~~~

~~~bash
java Hello.java
~~~

**Stdout:**

~~~text
Hello from compact source
~~~

Compiler tạo một **implicitly declared class** bao lấy `main`, source-file launcher biên dịch rồi VM thực thi class đó. Java 25 đưa cú pháp này ra khỏi preview (JEP 512). Không cần `--enable-preview` cho riêng tính năng này trên JDK 25+. Java 21–24 có những bản preview cần kiểm tra tùy release.

## 8. Lỗi khởi tạo và sự khác nhau giữa class với object

Nếu static initializer của **initial class** ném exception, chương trình có thể dừng **trước khi vào thân `main`**. Nếu class phụ được lần đầu sử dụng bên trong main rồi lỗi, main đã bắt đầu nhưng thao tác active use ấy thất bại. Theo JLS `12.4.2, lỗi khởi tạo bởi một exception thông thường có thể được bọc thành `ExceptionInInitializerError`; runtime class rơi vào trạng thái lỗi và những lần truy cập sau thường nhận `NoClassDefFoundError`.

Tạo file `InitFailure.java`:

~~~java
class BrokenConfig {
    static int VALUE = fail();

    static int fail() {
        throw new IllegalStateException("bad configuration");
    }
}

public class InitFailure {
    public static void main(String[] args) {
        for (int i = 1; i <= 2; i++) {
            try {
                System.out.println(BrokenConfig.VALUE);
            } catch (LinkageError error) {
                System.out.println(i + ": " + error.getClass().getSimpleName());
            }
        }
    }
}
~~~

~~~bash
javac InitFailure.java
java InitFailure
~~~

**Stdout:**

~~~text
1: ExceptionInInitializerError
2: NoClassDefFoundError
~~~

Vì `BrokenConfig` không phải initial class, `InitFailure.main` chạy được và đã chủ động truy cập `BrokenConfig.VALUE`. Truy cập đầu tiên khiến `<clinit>` thất bại; lần thứ hai cố sử dụng class đã ở erroneous state. Nếu lỗi nằm trong static initializer của `InitFailure`, bản thân `InitFailure.main` có thể chưa chạy.

Trong ứng dụng đồng thời, các thread không tự ý khởi tạo cùng một runtime class độc lập hai lần: VM quản lý initialization synchronization và trạng thái khởi tạo. Tuy nhiên, cùng tên class nhưng do **khác defining class loader** có thể là các runtime class khác nhau, với static state riêng.

## 9. Chẩn đoán startup theo đúng nguyên nhân

| Dấu hiệu | Câu hỏi nên hỏi | Kiểm tra |
| --- | --- | --- |
| `Could not find or load main class` | Tên class đầy đủ, package, class path/module path đúng chưa? | `java -cp ... fully.qualified.MainClass` và JAR content |
| `Main method not found` | Chữ ký có hợp lệ trên JDK chạy không? | `java -version`; dùng mẫu `public static void main(String[])` nếu cần tương thích cũ |
| `UnsupportedClassVersionError` | Bytecode được biên dịch cho release mới hơn runtime? | `javap -verbose ClassName` để xem class major version; cân nhắc `javac --release` |
| `ExceptionInInitializerError` | Static initializer/field initializer nào ném exception? | Xem `Caused by` và stack trace ban đầu; tìm `<clinit>` |
| `NoClassDefFoundError` sau lỗi static | Class đã ở erroneous state? | Truy ngược lỗi khởi tạo lần đầu, class loader và dependency |
| `constructor chạy trước main` | Entry có là instance main trên Java 25+? | Đối chiếu chữ ký được chọn và `new` trong ứng dụng |
| Hai main cùng tồn tại | `main(String[])` hay `main()` được ưu tiên? | Java 25+: `main(String[])` ưu tiên; xem JLS `12.1.4` |
| Static block không chạy | Đây chỉ là class literal/compile-time constant? | Kiểm tra active use thay vì suy từ loading |

Lệnh xem phiên bản và bytecode:

~~~bash
java -version
javac -version
javap -p -c BootOrder
javap -verbose BootOrder
java -Xlog:class+load=info BootOrder
~~~

`-Xlog:class+load=info` minh họa unified logging của **HotSpot** trên JDK hiện đại. Dòng log cho biết các class được load, **không phải bằng chứng rằng static initializer của mỗi class cũng đã chạy**. Output có thể rất dài và phụ thuộc bản dựng; xem `java -Xlog:help` trước khi áp dụng trên VM/version cụ thể. Trường hợp lỗi chỉ xảy ra ở runtime, hãy lưu cả `java -version` và `javac -version` vì dùng JDK biên dịch khác runtime là nguồn lỗi thường gặp.

Đừng quên ranh giới vòng đời: việc `main` trả về **không luôn đồng nghĩa process lập tức kết thúc**. Các non-daemon thread còn chạy có thể giữ JVM sống, và shutdown hooks có thể thực hiện khi JVM shutdown. Đây là giai đoạn sau khi đã vào `main`.

## 10. Những hiểu nhầm hay gặp

1. **“Lớp chứa `main` chắc chắn là class đầu tiên VM đã tải.”** Sai. Initial class là điểm vào ứng dụng; VM đã có thể xử lý các lớp runtime.
2. **“Class loaded tức static block đã chạy.”** Sai. Loading khác initialization; linking resolution còn có thể trì hoãn.
3. **“Prepare đã chạy `static int x = f()`.”** Sai. Preparation đặt giá trị mặc định; initialization mới gọi `f()`.
4. **“Mỗi lần gọi static method lại chạy static block.”** Sai khi class đã khởi tạo thành công trong cùng runtime identity.
5. **“Mọi class ứng dụng đều được initialize trước main.”** Sai. Nhiều class chỉ initialize khi active use.
6. **“`main` bắt buộc luôn `public static void main(String[])`.”** Đây là mẫu truyền thống và tương thích rộng, nhưng Java 25+ có các dạng entry khác.
7. **“Java 17 chạy `void main()` như Java 25.”** Sai với entry tiêu chuẩn: khả năng mở rộng là preview 21–24 và ổn định từ 25.
8. **“Constructor luôn chạy trước main.”** Chỉ xảy ra khi runtime phải tạo object cho **instance main**, hoặc chương trình tự tạo object trước khi gọi một method.
9. **“Compact source nghĩa là JVM đọc source Java trực tiếp.”** Sai. Launcher biên dịch thành class và JVM chạy bytecode.
10. **“Main kết thúc là process phải đóng ngay.”** Sai nếu còn non-daemon threads hay quá trình shutdown tiếp tục.

## 11. Tự kiểm tra

**1. Vì sao static block của `Parent` chạy trước `BootOrder`?**  
Do khởi tạo superclass bắt buộc diễn ra trước initialization của subclass.

**2. Sự khác nhau giữa `<clinit>` và `<init>`?**  
`<clinit>` biểu diễn logic class initialization; `<init>` là constructor cho một object. Static main tự nó không tạo instance của initial class.

**3. Java 17 chạy `class App { void main() {} }` bằng `java App` được không?**  
Không theo luật entry main truyền thống. Cần `public static void main(String[] args)` hoặc biến thể varargs tương đương.

**4. Trong Java 25+, giữa `static void main()` và `void main(String[] args)` thì chọn gì?**  
Chọn `void main(String[] args)`; runtime tạo object để gọi instance method.

**5. Tham chiếu `static final String LABEL = "x"` luôn làm class initialized không?**  
Không. Constant variable với initializer là constant expression có thể được inline và không kích hoạt class initialization khi đọc.

**6. Nếu lỗi static initializer của initial class xảy ra, có thể main chưa hề chạy không?**  
Có. JVM phải initialize initial class thành công trước khi invoke main.

## 12. Nguồn tra cứu

- [JLS Java SE 25, Chapter 12 — Execution](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html): startup, initialize initial class, entry `main`, initialization triggers và lỗi.
- [JLS Java SE 26, Chapter 12 — Execution](https://docs.oracle.com/javase/specs/jls/se26/html/jls-12.html): quy tắc cập nhật về candidate main và class initialization.
- [Java Language Changes by Release, Java 26](https://docs.oracle.com/en/java/javase/26/language/java-language-changes-release.html): chuỗi preview JEP 445/463/477/495 và phiên bản ổn định JEP 512 ở Java 25.
- [Oracle Java 25 — Compact Source Files and Instance Main Methods](https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html): tài liệu tính năng ổn định.
- [Oracle Java 24 — Simple Source Files and Instance Main Methods](https://docs.oracle.com/en/java/javase/24/language/simple-source-files-and-instance-main-methods.html): tài liệu trạng thái preview của JDK 24.
- [Oracle Java 25 — java launcher](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): cú pháp class path, JAR, module, source-file mode và phân loại options. Đối với chữ ký `main` mở rộng, ưu tiên văn bản JLS `12.1.4` của release tương ứng.
- [Java SE Specifications](https://docs.oracle.com/javase/specs/): chọn bản **JVMS Chapter 5** phù hợp release để đọc chuẩn về loading/linking/initializing.

**Ghi nhớ:** JVM chuẩn bị môi trường và initial class **trước** khi invoke `main`; các block `static` có thể chạy trước thân `main`, còn constructor chỉ chạy khi cần object. Khi gặp lỗi “không vào main”, kiểm tra **launch mode, class path/module path, class-file version, static initialization và chữ ký main theo JDK đang dùng**.