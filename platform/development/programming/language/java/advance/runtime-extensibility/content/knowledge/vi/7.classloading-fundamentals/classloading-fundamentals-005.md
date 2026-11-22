# Phân biệt `loadClass` và `Class.forName` với tùy chọn khởi tạo

## 1. Vì sao cần phân biệt?

Trong Java, có được một đối tượng `Class<?>` đại diện cho một lớp **không đồng nghĩa** với việc các khối `static` hay phép gán trường `static` của lớp ấy đã chạy. Điều này đặc biệt quan trọng khi xây dựng cơ chế mở rộng ứng dụng: host có thể cần tìm lớp plugin, kiểm tra tên hoặc chữ ký trước khi quyết định có kích hoạt plugin hay không.

Hai cách thường gặp là:

- `loader.loadClass("com.example.Plugin")`: yêu cầu một `ClassLoader` tìm/nạp lớp, thông thường **không khởi tạo lớp** chỉ vì lời gọi này.
- `Class.forName("com.example.Plugin")`: nạp, liên kết và **khởi tạo lớp** nếu lớp chưa được khởi tạo, theo overload một tham số.
- `Class.forName("com.example.Plugin", false, loader)`: cho phép chọn bộ nạp lớp và **không chủ động khởi tạo** lớp đích.
- `Class.forName("com.example.Plugin", true, loader)`: chọn bộ nạp lớp và **yêu cầu khởi tạo** lớp đích nếu cần.

Tùy chọn `initialize` là tham số `boolean` của `Class.forName(String, boolean, ClassLoader)`. Không có overload công khai tương ứng `ClassLoader.loadClass(name, initialize)`: tham số `boolean` trong phiên bản `loadClass(name, resolve)` được bảo vệ (`protected`) có ý nghĩa **resolve liên kết**, không phải bật/tắt `<clinit>`.

**Đích học tập:** hiểu ranh giới giữa loading, linking, initialization; quan sát thứ tự bằng chương trình Java 17 chạy được; chọn overload phù hợp với plugin/classloader và xử lý đúng các lỗi phổ biến.

## 2. Ba giai đoạn của vòng đời lớp trong JVM

Một lớp có thể trải qua các bước sau, dù JVM có quyền thực hiện một số chi tiết liên kết theo thời điểm riêng miễn vẫn tuân thủ đặc tả:

1. **Loading (nạp):** tìm biểu diễn của lớp (thường là bytecode `.class`) và tạo đối tượng `Class` đại diện. Classloader có thể ủy quyền cho loader cha; hai lớp cùng tên nhưng do hai *defining classloader* khác nhau định nghĩa là hai kiểu khác nhau.
2. **Linking (liên kết):** bao gồm *verification* (kiểm tra bytecode), *preparation* (chuẩn bị bộ nhớ và giá trị mặc định cho các trường static) và *resolution* (chuyển các tham chiếu ký hiệu thành tham chiếu thực khi cần). Resolution có thể xảy ra sớm hoặc muộn tùy JVM và đường thực thi.
3. **Initialization (khởi tạo):** thực thi logic khởi tạo lớp, tức phương thức đặc biệt `<clinit>` được JVM tạo từ các phép khởi tạo trường static có mã thực thi và các khối `static { ... }`, theo thứ tự trong mã nguồn. JVM đảm bảo việc khởi tạo cho một lớp đã được định nghĩa chỉ thành công một lần, có đồng bộ thích hợp.

Ví dụ khái niệm:

~~~java
class Demo {
    static int counter; // Giá trị mặc định 0 từ preparation.
    static int port = readConfig(); // Phép gọi này xảy ra khi initialization.

    static {
        System.out.println("INIT Demo");
    }

    private static int readConfig() {
        return 8080;
    }
}
~~~

Đoạn trên **chỉ minh họa** ba khái niệm, không phải một chương trình độc lập. Ở preparation, trường `counter` và `port` có giá trị mặc định là `0`; khi initialization thực sự diễn ra, `readConfig()` được gọi và khối `static` chạy. Với các trường hằng có `ConstantValue`, JVM có thể gán giá trị hằng ngay trong preparation; không được suy luận rằng mọi trường static đều đợi `<clinit>` để có giá trị cuối.

Một quy tắc then chốt: **loading hoặc linking có thể diễn ra mà chưa initialization**. Ngược lại, trước khi khởi tạo, JVM phải hoàn tất những điều kiện nạp và liên kết bắt buộc; việc chỉ nhìn thấy đối tượng `Class` không phải bằng chứng rằng mọi mã static đã được chạy.

## 3. So sánh các API

| Lời gọi | Classloader được dùng | Có yêu cầu khởi tạo lớp đích không? | Dùng khi nào? |
| --- | --- | --- | --- |
| `loader.loadClass(name)` | Chính `loader`, với quy tắc delegation của nó | **Không**, theo đường mặc định; thường chưa chủ động resolve | Tìm kiểu bằng loader đã chọn, muốn hoãn static initialization |
| `Class.forName(name)` | Defining loader của lớp **đang gọi** `forName` | **Có**, nếu chưa khởi tạo | Muốn nạp và sẵn sàng sử dụng lớp, thường từ code cùng không gian nạp |
| `Class.forName(name, false, loader)` | `loader` chỉ định; `null` nghĩa là bootstrap loader | **Không** | Tìm/link kiểu nhưng hoãn hiệu ứng khởi tạo |
| `Class.forName(name, true, loader)` | `loader` chỉ định | **Có**, nếu chưa khởi tạo | Chủ động kích hoạt static initialization bằng loader mong muốn |

Điểm tinh tế:

- `ClassLoader.loadClass(String)` của JDK thường gọi `loadClass(name, false)`. Tham số `resolve=false` của phương thức được bảo vệ quyết định có yêu cầu `resolveClass` ngay trong con đường này hay không. Điều đó **khác** tham số `initialize` của `Class.forName`. JVM và loader tùy biến vẫn có thể thực hiện thêm việc nạp/liên kết ở những thời điểm khác; chỉ cần hiểu rằng không nên dựa vào `loadClass` để kích hoạt logic static.
- `Class.forName(String, boolean, ClassLoader)` có thể phát sinh lỗi **loading/linking** ngay cả khi `initialize=false`. Giá trị `false` không có nghĩa kiểm tra metadata thuần túy và không hứa mọi dependency đều hợp lệ.
- Một lần `Class.forName(..., true, ...)` sau khi lớp đã khởi tạo thành công **không chạy lại** khối `static`. Tương tự, gọi `false` sau khi lớp đã khởi tạo không thể đưa lớp trở về trạng thái chưa khởi tạo.
- `Class.forName(name)` **không mặc định dùng** `Thread.currentThread().getContextClassLoader()`. Đây là điểm dễ nhầm với một số API phát hiện provider như `ServiceLoader.load`, vốn thường dùng thread context classloader trong overload thông dụng.

### Khi nào JVM tự khởi tạo lớp?

Theo các trường hợp sử dụng chủ động quan trọng của Java/JVM, khởi tạo lớp có thể được kích hoạt bởi: tạo đối tượng bằng `new`, gọi phương thức static do lớp khai báo, đọc/ghi trường static không phải constant variable theo quy tắc ngôn ngữ, thao tác phản xạ yêu cầu kích hoạt lớp, hoặc `Class.forName` với `initialize=true`. Khi khởi tạo một lớp, JVM còn phải tuân thủ quan hệ khởi tạo với superclass và một số superinterface liên quan; ví dụ thực hành bên dưới không có kế thừa phức tạp để output dễ kiểm chứng.

Trái lại, lấy class literal `Demo.class`, tham chiếu kiểu trong khai báo, hoặc lấy `Class<?> ` qua `loadClass`/ `forName(..., false, ...)` **không tự nó** yêu cầu chạy `<clinit>` của lớp đích.

Đặc biệt: dùng `static final int TIMEOUT = 5;` để kiểm tra init có thể gây hiểu sai. Đây là **constant variable** và Java thường inline giá trị tại nơi dùng; đọc nó có thể không khởi tạo lớp. Hãy quan sát `static { System.out.println(...) }` hoặc gọi một phương thức static như ví dụ tiếp theo.

## 4. Ví dụ Java 17 chạy được: in ra đúng thời điểm `<clinit>`

Tạo hai file sau. Ví dụ dùng tên lớp đích dưới dạng chuỗi trong `Main`, tránh `Main` chủ động sử dụng `Target` trước thời điểm cần quan sát.

~~~text
src/
  demo/
    loading/
      Target.java
      Main.java
out/                (được tạo sau khi biên dịch)
~~~

**File `src/demo/loading/Target.java`:**

~~~java
package demo.loading;

public final class Target {
    static {
        System.out.println("INIT Target");
    }

    public static String greet() {
        return "Hello";
    }
}
~~~

Khối `static` in `INIT Target` khi lớp **được khởi tạo**, không đơn giản khi bytecode vừa được tìm thấy. `greet()` là phương thức static thật sự; việc gọi nó bằng reflection có thể khiến JVM khởi tạo lớp nếu chưa khởi tạo.

**File `src/demo/loading/Main.java`:**

~~~java
package demo.loading;

public final class Main {
    private static final String NAME = "demo.loading.Target";

    private Main() {
    }

    public static void main(String[] args) throws Exception {
        String mode = args.length == 0 ? "stages" : args[0];
        ClassLoader loader = Main.class.getClassLoader();

        switch (mode) {
            case "stages" -> stages(loader);
            case "one" -> oneArgument();
            case "invoke" -> invokeAfterFalse(loader);
            default -> throw new IllegalArgumentException("Unknown mode: " + mode);
        }
    }

    private static void stages(ClassLoader loader) throws Exception {
        System.out.println("A loadClass");
        Class<?> loaded = loader.loadClass(NAME);
        System.out.println("name=" + loaded.getName());

        System.out.println("B forName false");
        Class<?> notInitialized = Class.forName(NAME, false, loader);
        System.out.println("same=" + (loaded == notInitialized));

        System.out.println("C forName true");
        Class<?> initialized = Class.forName(NAME, true, loader);
        System.out.println("same=" + (loaded == initialized));

        System.out.println("D forName true again");
        Class.forName(NAME, true, loader);
        System.out.println("done");
    }

    private static void oneArgument() throws Exception {
        System.out.println("A forName(String)");
        Class<?> type = Class.forName(NAME);
        System.out.println("name=" + type.getName());
    }

    private static void invokeAfterFalse(ClassLoader loader) throws Exception {
        System.out.println("A forName false");
        Class<?> type = Class.forName(NAME, false, loader);
        System.out.println("name=" + type.getName());

        System.out.println("B reflective invocation");
        Object result = type.getMethod("greet").invoke(null);
        System.out.println("result=" + result);
    }
}
~~~

Trong chế độ `stages`, `loadClass` và `Class.forName(..., false, ...)` trả về **cùng một đối tượng `Class`** vì cùng tên và cùng classloader định nghĩa. `Class.forName(..., true, ...)` kích hoạt khối `static` lần đầu. Lần gọi `true` thứ hai không khởi tạo lại.

Chế độ `one` dùng overload một tham số. Chế độ `invoke` chứng minh rằng `false` chỉ **hoãn** initialization: khi gọi phương thức static bằng reflection, lớp vẫn được khởi tạo trước khi method body thực thi.

### 4.1. Biên dịch

Mở terminal ở thư mục chứa `src`. Với JDK 17 trở lên:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out   src/demo/loading/Target.java   src/demo/loading/Main.java
~~~

Trên PowerShell có thể dùng:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out src/demo/loading/Target.java src/demo/loading/Main.java
~~~

Lưu ý phải biên dịch cả hai file, để lớp `Target` tồn tại trên runtime classpath. Đoạn code không dùng thư viện ngoài JDK.

### 4.2. Quan sát đường `loadClass` → `forName(false)` → `forName(true)`

~~~bash
java -cp out demo.loading.Main stages
~~~

**Stdout chính xác:**

~~~text
A loadClass
name=demo.loading.Target
B forName false
same=true
C forName true
INIT Target
same=true
D forName true again
done
~~~

Hai dòng đầu sau `loadClass` không có `INIT Target`: tên lớp đã biết, nhưng initializer chưa chạy. Sau `forName(false)` cũng chưa có. Khi gọi `forName(true)`, `INIT Target` in ra **trước** khi chương trình in `same=true` của câu lệnh tiếp theo, đúng thời điểm Java khởi tạo lớp. Khi gọi `true` lần nữa, không thấy `INIT Target` lần thứ hai.

### 4.3. Overload một tham số chủ động khởi tạo

Chạy trong **một tiến trình Java mới**, không tái sử dụng JVM của lệnh trước:

~~~bash
java -cp out demo.loading.Main one
~~~

Stdout:

~~~text
A forName(String)
INIT Target
name=demo.loading.Target
~~~

Trong chương trình này, overload `Class.forName(NAME)` sử dụng classloader của `Main` và yêu cầu initialization; vì vậy `INIT Target` xuất hiện trước khi `getName()` được in. Chú ý: `getName()` không phải nguyên nhân kích hoạt init; lời gọi `forName` ngay trước đó mới là nguyên nhân.

### 4.4. Hoãn bằng `false`, rồi kích hoạt qua reflection

Lại khởi động một JVM mới:

~~~bash
java -cp out demo.loading.Main invoke
~~~

Stdout:

~~~text
A forName false
name=demo.loading.Target
B reflective invocation
INIT Target
result=Hello
~~~

Lấy `Class` và tên lớp không khởi tạo `Target`. Khi `Method.invoke(null)` gọi phương thức static `greet`, runtime phải khởi tạo lớp trước, nên `INIT Target` xuất hiện trước `result=Hello`.

Ba lệnh `java` ở trên là **ba tiến trình khác nhau**. Nếu chạy chúng trong cùng một JVM theo thứ tự khác, kết quả liên quan đến `<clinit>` sẽ thay đổi vì một lớp đã khởi tạo thành công không khởi tạo lại trong cùng danh tính lớp.

## 5. Cách hiểu `ClassLoader.loadClass` chuẩn xác

`ClassLoader` sở hữu nhiệm vụ tìm/nạp lớp theo quy tắc của loader và thường dùng delegation đến parent. Với implementation thông dụng, đoạn:

~~~java
Class<?> clazz = loader.loadClass("demo.loading.Target");
~~~

là cách yêu cầu loader trả về `Class` cho tên nhị phân `demo.loading.Target`. Nó có thể tìm lớp đã nạp hoặc nạp mới, nhưng **không bảo JVM chạy khối static** của `Target`. Nhiều hướng dẫn nói ngắn gọn “`loadClass` chỉ load, `forName` sẽ initialize”; cách nhớ này hữu ích nhưng chưa hoàn toàn chính xác khi nói về *linking*, classloader tùy biến hoặc các overload khác của `forName`.

Cụ thể:

- `ClassLoader.loadClass(String)` của JDK tương đương đường gọi `loadClass(name, false)`. Cờ `false` liên quan đến **resolve**, không liên quan đến `initialize`.
- Java có thể **verify/prepare/resolve** một phần hoặc toàn bộ lớp hay dependency ở những thời điểm khác nhau. Không nên hứa rằng một `loadClass` thành công sẽ bảo đảm mọi tham chiếu phụ thuộc được resolve thành công sau này.
- Classloader do ứng dụng viết có thể override `loadClass` và có tác dụng phụ riêng; hành vi “không khởi tạo lớp đích do chính lời gọi” phải hiểu theo hợp đồng phổ biến và quy tắc JVM, không phải lời hứa mọi mã loader tùy biến đều vô hại.
- Tên thường là **binary name**. Ví dụ lớp nested `Outer.Inner` có tên nhị phân dạng `pkg.Outer$Inner`; nhập sai tên là một nguyên nhân của `ClassNotFoundException`.

Trong cơ chế plugin, chọn đúng classloader còn quan trọng hơn việc chỉ chọn phương thức. Nếu plugin nằm trong loader riêng mà host dùng loader mặc định không nhìn thấy nó, `Class.forName(name)` có thể không tìm thấy provider. Khi đó nên truyền rõ loader:

~~~java
Class<?> candidate =
        Class.forName("com.example.plugin.MyPlugin", false, pluginLoader);
~~~

Đây là **mã minh họa**, đòi hỏi biến `pluginLoader` đã được tạo và nhìn thấy lớp thực tế. Không thể chạy độc lập. `Class.forName(..., false, pluginLoader)` cho phép trì hoãn static initialization của lớp đích trong lúc kiểm tra, nhưng không thay thế việc xác minh JAR, API compatibility hoặc chính sách tin cậy.

## 6. Tùy chọn `initialize` hoạt động ra sao?

### `initialize=false`: chưa kích hoạt logic static

Ví dụ:

~~~java
Class<?> type = Class.forName(
        "demo.loading.Target", false, Main.class.getClassLoader());
~~~

Nếu `Target` chưa khởi tạo, câu lệnh này chưa yêu cầu `<clinit>` của nó chạy. Host có thể lấy tên, modifier hoặc kiểm tra các quan hệ kiểu để quyết định bước tiếp theo. Tuy nhiên việc đọc kiểu bằng reflection cũng có thể dẫn tới việc tải các kiểu khác được tham chiếu trong chữ ký; và loader tùy biến vẫn có thể có tác dụng phụ. **Không coi `false` là sandbox hay đảm bảo không có I/O, không có lỗi, không có dependency liên quan.**

Khi thực sự quyết định sử dụng plugin, việc gọi phương thức static hoặc tạo instance sẽ khiến JVM khởi tạo lớp theo quy tắc thông thường. Vì thế `initialize=false` là lựa chọn để **trì hoãn khởi tạo**, không phải để vô hiệu hóa vĩnh viễn.

### `initialize=true`: yêu cầu init nếu cần

Ví dụ:

~~~java
Class<?> type = Class.forName(
        "demo.loading.Target", true, Main.class.getClassLoader());
~~~

Nếu `Target` chưa khởi tạo, JVM khởi tạo theo quy tắc của lớp đó; khối `static` và các phép khởi tạo static chạy. Nếu lớp đã khởi tạo thành công, không chạy lại. Điều này hữu ích khi ứng dụng thực sự muốn kích hoạt thành phần và kiểm tra lỗi initialization trước khi dùng.

Nhưng cần cân nhắc: static initializer có thể thực hiện I/O, đọc cấu hình, mở kết nối hoặc ném lỗi. Không nên gọi `forName(true)` chỉ để xem một lớp có tồn tại hay không, nếu không muốn tác dụng phụ đó.

### Overload `Class.forName(String)`

Cách viết `Class.forName(name)` ngắn hơn, nhưng chủ động initialize. Loader dùng là **defining classloader của lớp gọi phương thức**, khác với ý tưởng “luôn dùng system classloader” hay “luôn dùng context classloader”. Khi hệ thống có nhiều loader (application server, plugin container), lựa chọn loader ngầm định dễ khiến kết quả khác mong đợi.

Nếu chỉ cần tìm thông tin qua một loader xác định mà chưa muốn khởi tạo, viết rõ `Class.forName(name, false, loader)` giúp ý định người đọc và hành vi tương ứng minh bạch hơn.

## 7. Các lỗi cần phân biệt khi nạp và khởi tạo

Các API cùng có thể thất bại, nhưng **giai đoạn** thất bại giúp chẩn đoán:

| Lỗi | Ý nghĩa thường gặp | Kiểm tra gì? |
| --- | --- | --- |
| `ClassNotFoundException` | Không tìm thấy lớp theo tên và loader được chọn; đây là checked exception của các API nêu trên | Tên nhị phân, spelling/package, classpath/module path, loader thực tế |
| `NoClassDefFoundError` | JVM cần một định nghĩa lớp khi liên kết/sử dụng nhưng không có, hoặc lớp đã bị đánh dấu khởi tạo thất bại trước đó | Cause và stack trace, dependency runtime, trạng thái init trước đó |
| `ExceptionInInitializerError` | Static initialization ném exception không phải `Error`; lỗi được gói khi JVM khởi tạo lớp | `getCause()`, logic `static`, cấu hình/IO/biến môi trường |
| `LinkageError` cùng các dạng con | Không thể liên kết lớp thích hợp, ví dụ lỗi định dạng bytecode, phiên bản lớp hoặc bất tương thích nhị phân | JDK version, các JAR trùng lớp, dependency versions, binary contract |
| `ClassCastException` khi ép kiểu sau load | Kiểu thực tế không phải loại mà host kỳ vọng, có thể do lớp trùng tên được định nghĩa bởi loader khác | Defining classloader của cả hai kiểu, API JAR bị đóng gói trùng |

Đặc biệt, `Class.forName(name, false, loader)` vẫn có thể gặp `ClassNotFoundException` hoặc lỗi liên kết. Cờ `false` **không đồng nghĩa** “phải thành công nếu chỉ cần metadata”. Mặt khác, `Class.forName(name, true, loader)` có thể gây `ExceptionInInitializerError` khi static initializer lỗi. Một lần khởi tạo đã thất bại khiến lớp đó bị đánh dấu erroneous trong defining loader; những lần cố sử dụng/khởi tạo tiếp theo thường phát sinh `NoClassDefFoundError`, không tự chạy lại initializer.

### Ví dụ độc lập quan sát lỗi initialization

Để làm rõ lỗi này, có thể thêm hai file bên dưới vào ví dụ Java 17. Chúng độc lập với các chế độ của `Main`.

**`src/demo/loading/Broken.java`:**

~~~java
package demo.loading;

public final class Broken {
    static {
        System.out.println("INIT Broken");
        fail();
    }

    private static void fail() {
        throw new IllegalStateException("demo failure");
    }
}
~~~

**`src/demo/loading/FailureDemo.java`:**

~~~java
package demo.loading;

public final class FailureDemo {
    public static void main(String[] args) throws Exception {
        String name = "demo.loading.Broken";
        ClassLoader loader = FailureDemo.class.getClassLoader();

        Class<?> type = Class.forName(name, false, loader);
        System.out.println("loaded=" + type.getSimpleName());

        try {
            Class.forName(name, true, loader);
        } catch (ExceptionInInitializerError ex) {
            System.out.println("first=ExceptionInInitializerError");
        }

        try {
            Class.forName(name, true, loader);
        } catch (NoClassDefFoundError ex) {
            System.out.println("second=NoClassDefFoundError");
        }
    }
}
~~~

Biên dịch và chạy trong một JVM mới:

~~~bash
javac --release 17 -encoding UTF-8 -cp out -d out   src/demo/loading/Broken.java   src/demo/loading/FailureDemo.java
java -cp out demo.loading.FailureDemo
~~~

Stdout:

~~~text
loaded=Broken
INIT Broken
first=ExceptionInInitializerError
second=NoClassDefFoundError
~~~

Lần `forName(false)` chưa chạy `Broken` initializer. Lần `forName(true)` đầu khiến `fail()` ném `IllegalStateException`, được JVM gói trong `ExceptionInInitializerError`. Vì class initialization đã thất bại, lần `true` kế tiếp không thử chạy lại `<clinit>`; lỗi `NoClassDefFoundError` cho biết class không thể được khởi tạo thành công trong loader hiện tại.

Không nên “chữa” một class erroneous bằng cách gọi lặp lại `forName(true)` hoặc `loadClass`. Cần sửa nguyên nhân gốc và dùng một tiến trình mới hoặc loader/định nghĩa lớp mới theo cơ chế triển khai phù hợp.

## 8. Phạm vi riêng của classloader và quy tắc khởi tạo một lần

Initialization gắn với **danh tính lớp**. Trong JVM, danh tính đó bao gồm tên nhị phân cùng **defining classloader**, không đơn thuần là chuỗi tên lớp.

Ví dụ nếu có hai classloader thực sự **định nghĩa** hai bản `com.example.Plugin` khác nhau, đó là hai class identity riêng; mỗi bản có thể được khởi tạo độc lập. Chỉ tạo hai biến `ClassLoader` khác nhau nhưng cả hai cùng delegate về một parent định nghĩa lớp thì vẫn là **cùng lớp**, và không có hai lượt initialization.

Điều này giải thích tại sao reload plugin bằng classloader riêng phức tạp hơn việc gọi `Class.forName(name, true, loader)` lần nữa. Khi unload, phải bảo đảm không còn object, thread, static reference, callback hoặc tài nguyên sống giữ classloader cũ. Việc thay JAR trên đĩa hoặc gọi `ServiceLoader.reload()` không tự hoàn tất vòng đời ấy.

Đối với lớp mảng, `Class.forName` có thể nhận dạng mô tả mảng (chẳng hạn `[Ljava.lang.String;`); việc tìm lớp mảng không đồng nghĩa khởi tạo component type. Các tên primitive như `"int"` cũng không được tìm như một class bình thường bằng `Class.forName("int")`. Đây là những ngoại lệ quan trọng khi code làm việc với tên kiểu do người dùng nhập.

## 9. Chọn API nào trong thực tế?

| Tình huống | Lựa chọn phù hợp | Lý do |
| --- | --- | --- |
| Host đã có classloader và chỉ cần tra cứu lớp | `loader.loadClass(name)` hoặc `Class.forName(name, false, loader)` | Hoãn static initialization của lớp đích |
| Plugin container muốn dùng loader dành riêng cho plugin | `Class.forName(name, false, pluginLoader)` rồi xác thực | Loader được chỉ rõ, tránh phụ thuộc loader ngầm định của host |
| Muốn kiểm tra kiểu và chữ ký trước khi kích hoạt | Thường bắt đầu bằng `forName(..., false, loader)` | Có đối tượng `Class` để kiểm tra, giảm nguy cơ chạy `<clinit>` quá sớm |
| Muốn chủ động khởi tạo lớp đã chọn | `Class.forName(name, true, loader)` | Thể hiện ý định kích hoạt và quan sát lỗi init |
| Code đơn giản trong cùng môi trường loader cần lớp sẵn sàng | `Class.forName(name)` | Ngắn gọn, nhưng khởi tạo và dùng loader của lớp gọi |
| Thao tác qua tên service được công bố trong SPI | `ServiceLoader` khi có hợp đồng SPI | Tìm implementation theo descriptor thay vì tự hard-code FQCN |
| Chỉ cần đọc manifest/descriptor JAR **chưa tin cậy** | Đọc nội dung JAR như dữ liệu, chưa tải lớp | Tránh thực thi/khởi tạo mã plugin khi chưa có quyết định tin cậy |

**Quy trình ứng dụng cho plugin:**

1. Phân biệt việc tìm **metadata** trong JAR với việc **nạp lớp** bằng JVM. Khi chỉ cần tên và phiên bản trong manifest hoặc descriptor, không nhất thiết phải load class.
2. Chọn classloader có khả năng nhìn thấy JAR và có **một danh tính API chung** với host. Tránh làm bản sao lớp hợp đồng ở mỗi loader.
3. Nếu cần kiểm tra một class bằng reflection trước khi dùng, chọn `forName(..., false, pluginLoader)`, kiểm tra subtype, constructor, method và compatibility. Nhớ rằng việc load/link/reflect vẫn có thể báo lỗi dependency.
4. Khi quyết định kích hoạt, hãy chủ động chấp nhận khả năng static initialization và xử lý lỗi tại ranh giới phù hợp; có thể để lần `new`/gọi method khởi tạo tự nhiên hoặc yêu cầu sớm với `forName(..., true, pluginLoader)`.
5. Tách lifecycle, timeout, logging và cleanup của plugin khỏi logic khám phá tên lớp. Không dùng `Class.forName(true)` như một giao thức bật/tắt hoàn chỉnh.

## 10. Lỗi tư duy thường gặp

- **“`loadClass` đã tải được nên chắc chắn `static` chạy.”** Sai. Ví dụ `stages` cho thấy `INIT Target` chưa xuất hiện sau `loadClass`.
- **“`Class.forName` luôn khởi tạo.”** Sai. Overload ba tham số với `initialize=false` hoãn khởi tạo lớp đích.
- **“`loadClass(name, false)` và `forName(name, false, loader)` có cùng boolean.”** Sai. Cờ trong `loadClass(name, resolve)` nói về resolve, trong `forName` nói về initialize.
- **“Gọi `Class.forName(true)` nhiều lần sẽ chạy lại `static`.”** Sai. Một class identity chỉ khởi tạo thành công một lần; muốn thử lại sau lỗi phải xét lại tiến trình/loader, không đơn giản gọi thêm.
- **“`initialize=false` nghĩa là tuyệt đối không có tác dụng phụ.”** Sai. Classloader tùy biến, việc tìm tài nguyên và linking có thể có lỗi hay tác động; đó không phải môi trường cô lập mã không tin cậy.
- **“Overload một tham số sẽ tự dùng plugin loader hoặc context loader.”** Không chắc. Nó dựa vào defining loader của lớp gọi; nên truyền loader tường minh trong hệ thống đa classloader.
- **“Cứ đọc trường `static final` là initializer chạy.”** Không đúng với constant variable có thể inline ở nơi dùng.
- **“Có `Class` nghĩa là có thể `newInstance` ngay.”** Việc khởi tạo instance bằng reflection có thể kích hoạt initialization, cần constructor phù hợp và xử lý lỗi; `Class.newInstance()` cũ đã deprecated, nên dùng `getDeclaredConstructor().newInstance()` khi thích hợp.

## 11. Tự kiểm tra nhanh

Giả sử một lớp chưa từng được khởi tạo, classloader mặc định đã có thể tìm thấy nó và không có tác động phụ đặc biệt từ custom loader:

1. Gọi `loader.loadClass(name)` rồi chỉ in `clazz.getName()`: lớp đích thường **chưa initialization**.
2. Gọi `Class.forName(name, false, loader)`: lớp đích **chưa phải khởi tạo**; các lỗi loading/linking vẫn có thể xảy ra.
3. Gọi `Class.forName(name, true, loader)`: lớp đích được **khởi tạo nếu chưa khởi tạo**, theo quy tắc JVM.
4. Gọi `Class.forName(name, false, loader)` sau bước 3: lớp **vẫn đã khởi tạo**.
5. Tạo một tiến trình Java mới và gọi `Class.forName(name)`: classloader của lớp gọi được dùng, và lớp đích **được khởi tạo** nếu chưa khởi tạo.
6. Dùng reflection gọi một phương thức static sau `forName(false)`: JVM **khởi tạo trước khi thực thi** method body nếu cần.

Điểm cốt lõi của bài: **`loadClass` chủ yếu giải quyết việc tìm/nạp lớp theo classloader; `Class.forName` có thể được yêu cầu khởi tạo hoặc không, tùy overload và cờ `initialize`.** Phân biệt chính xác loading, linking và initialization giúp đọc lỗi JVM đúng hơn và tránh kích hoạt sớm mã static của plugin khi host mới đang trong bước khám phá.
