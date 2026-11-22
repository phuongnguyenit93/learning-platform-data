# 2.8 Phân biệt nạp lớp, liên kết và khởi tạo; kiểm soát khởi tạo qua `Class.forName`

Khi Java gặp một kiểu tại thời điểm chạy, JVM không nhất thiết thực hiện ngay mọi công việc liên quan đến kiểu đó. **Loading (nạp lớp), linking (liên kết) và initialization (khởi tạo lớp)** là các giai đoạn khác nhau; phân biệt chúng giúp kiểm soát thời điểm chạy mã `static`, thiết kế cơ chế nạp plugin và chẩn đoán lỗi runtime.

## 1. Kết quả cần nắm

Sau bài này, bạn có thể:

- Giải thích việc tìm/định nghĩa lớp khác gì việc xác minh, chuẩn bị và phân giải tham chiếu, và khác gì việc chạy bộ khởi tạo `static`.
- Dự đoán các hành động như `Target.class`, đọc hằng số, `new Target()`, `ClassLoader.loadClass(...)` và từng overload của `Class.forName(...)` có khởi tạo `Target` hay không.
- Chủ động trì hoãn hoặc yêu cầu khởi tạo, đồng thời hiểu giới hạn của lựa chọn này.
- Phân tích thứ tự khởi tạo cha–con, giá trị mặc định của trường `static` và lỗi khởi tạo.

## 2. Ba giai đoạn trong vòng đời một kiểu

Một cách nhìn thực dụng về vòng đời là:

```text
Tên lớp / bytecode
       |
       v
LOADING            Tìm biểu diễn lớp và tạo đối tượng Class tương ứng
       |
       v
LINKING            Verification -> Preparation -> Resolution (*)
       |
       v
INITIALIZATION     Thực thi phần khởi tạo static của lớp/interface
       |
       v
Sử dụng kiểu đã được khởi tạo
```

`(*)` Resolution không nhất thiết hoàn tất ngay cùng verification/preparation: JVM được phép phân giải tham chiếu sớm hoặc khi thực sự cần. **Trước khi bắt đầu initialization, lớp phải đã được nạp, xác minh và chuẩn bị**; điều này không có nghĩa mọi tham chiếu tượng trưng của nó đã được phân giải. Các bước có thể kéo theo việc nạp hoặc liên kết thêm kiểu khác.

| Giai đoạn | JVM làm gì? | Có chạy `static { ... }` của lớp đang xét? |
| --- | --- | --- |
| **Loading** | Tìm bytecode/biểu diễn nhị phân bằng class loader, định nghĩa kiểu runtime và đối tượng `Class<?>` của nó. | Không, chỉ vì lớp được nạp. |
| **Linking: verification** | Kiểm tra cấu trúc bytecode, kiểu dữ liệu, tính hợp lệ của các lệnh và ràng buộc JVM. | Không. |
| **Linking: preparation** | Cấp phát/trang bị trạng thái cho các trường `static` và gán **giá trị mặc định** ban đầu (`0`, `false`, `null`...); có thể chuẩn bị cấu trúc nội bộ. | Không chạy biểu thức gán `static` do người viết. |
| **Linking: resolution** | Biến tham chiếu tượng trưng tới lớp, trường, phương thức... thành thực thể runtime và kiểm tra các ràng buộc liên kết/quyền truy cập. | Không tự nó đồng nghĩa chạy `<clinit>`. |
| **Initialization** | Thực hiện bộ khởi tạo lớp: giá trị `static` tính lúc chạy và các khối `static` theo thứ tự khai báo. | Có, nếu lớp có phần khởi tạo cần chạy. |

### 2.1. Loading: biết kiểu tồn tại chưa có nghĩa kiểu đã được khởi tạo

Class loader (bootstrap, platform, application hoặc loader tùy biến) tham gia tìm và định nghĩa lớp. JVM xác định **danh tính runtime của lớp bằng tên nhị phân kết hợp với defining class loader**: hai loader có thể định nghĩa hai lớp cùng tên nhưng khác kiểu runtime. Vì vậy trong hệ plugin, tên lớp đúng chưa đủ; chọn đúng loader cũng quan trọng.

Nạp lớp có thể gây I/O, nạp thêm lớp hoặc thực hiện công việc của chính class loader. Điều quan trọng ở đây là **loading riêng nó không phải lệnh chạy khối `static` của lớp mục tiêu**. Không nên suy diễn rằng thao tác nạp luôn hoàn toàn không có tác dụng phụ ở toàn bộ ứng dụng.

### 2.2. Linking: kiểm tra và chuẩn bị, nhưng chưa thực hiện logic khởi tạo

Xét một lớp có `static int count = 7;`. Tại preparation, bộ nhớ cho `count` được chuẩn bị với mặc định `0`; biểu thức gán `7` thuộc initialization. Trường `static final` là hằng biểu thức biên dịch có xử lý riêng theo đặc tả, vì vậy đừng dùng việc đọc hằng số đã inline để suy ra trình tự thực thi của mọi initializer.

Verification có thể phát hiện `VerifyError`. Resolution có thể phát hiện `NoSuchMethodError`, `NoSuchFieldError`, `IllegalAccessError` hoặc lỗi tương thích nhị phân khác. **Thời điểm báo lỗi resolution có thể khác nhau giữa các JVM**, vì resolution có thể diễn ra khi liên kết ban đầu hoặc khi sử dụng một tham chiếu cụ thể.

### 2.3. Initialization: chạy mã của lớp, một lần cho mỗi định nghĩa lớp

JVM chạy các biểu thức gán trường `static` không phải hằng compile-time và các khối `static` theo thứ tự văn bản; javac thường gom chúng vào phương thức nội bộ `<clinit>` nếu cần. Khi khởi tạo một class, superclass chưa khởi tạo sẽ được khởi tạo trước; các superinterface khai báo default method cũng có thể phải khởi tạo theo quy tắc của JVM. Khởi tạo một interface **không mặc nhiên** khởi tạo mọi superinterface của nó.

Với một định nghĩa lớp đã khởi tạo thành công, các yêu cầu khởi tạo tiếp theo không chạy lại initializer. JVM đồng bộ hóa quá trình khởi tạo giữa các thread; một thread khác cần khởi tạo cùng lớp phải đợi thay vì chạy cùng lúc thêm một lần. “Một lần” tính cho từng định nghĩa lớp gắn với class loader, không có nghĩa mọi loader chia sẻ một biến `static` toàn cục.

## 3. Khi nào lớp thực sự được khởi tạo?

Đối với lớp `Target` chưa được khởi tạo, hãy phân biệt các hành động sau:

| Hành động | Có yêu cầu khởi tạo `Target`? | Lý do |
| --- | --- | --- |
| `Target.class` | **Không**, chỉ vì lấy class literal | Nhận `Class` không phải active use kích hoạt initializer. |
| `ClassLoader.loadClass("pkg.Target")` | **Thông thường không** | Cơ chế mặc định nạp lớp, không yêu cầu chạy initializer; custom loader có thể làm công việc khác. |
| `Class.forName("pkg.Target", false, loader)` | **Không** | Yêu cầu tìm/nạp; `initialize=false` không bắt đầu khởi tạo mục tiêu. Nó vẫn có thể liên kết và phân giải các phụ thuộc. |
| `Class.forName("pkg.Target")` | **Có** | Tương đương overload ba tham số với `initialize=true` và loader của lớp gọi. |
| `Class.forName("pkg.Target", true, loader)` | **Có** | Bảo đảm lớp được khởi tạo nếu chưa khởi tạo trước đó. |
| `new Target()` | **Có** | Tạo instance cần class được khởi tạo trước. |
| `Target.staticMethod()` | **Có**, nếu phương thức được khai báo tại `Target` | Gọi phương thức `static` là active use. |
| Đọc/ghi trường `static` không phải constant variable khai báo ở `Target` | **Có** | JVM phải khởi tạo lớp thực sự khai báo trường. |
| Đọc `Target.COMPILE_TIME_CONSTANT` (hằng nguyên thủy/`String` đủ điều kiện constant expression) | **Không**, chỉ vì thao tác đó | Compiler có thể inline giá trị; không phải active use khởi tạo lớp. |
| Tạo `new Target[10]` | **Không**, chỉ vì tạo mảng | Tạo kiểu mảng không bắt buộc khởi tạo kiểu phần tử. |
| `type.getDeclaredConstructor().newInstance()` | **Có**, khi thực sự tạo instance | Reflection dẫn tới tạo đối tượng và khởi tạo class nếu cần. |

**Chú ý:** `static final` không đồng nghĩa compile-time constant. Ví dụ `static final int A = 10;` là constant variable; còn `static final int B = Integer.parseInt("10");` cần chạy biểu thức lúc khởi tạo. Nếu truy cập một trường `static` được khai báo ở class cha thông qua tên class con, JVM khởi tạo **lớp thực sự khai báo trường**, không nhất thiết khởi tạo class con.

## 4. Kiểm soát chủ động bằng `Class.forName`

### 4.1. Hai overload quan trọng nhất

```java
Class<?> a = Class.forName("com.example.Plugin");
Class<?> b = Class.forName("com.example.Plugin", false, pluginLoader);
Class<?> c = Class.forName("com.example.Plugin", true, pluginLoader);
```

Đây là **đoạn minh họa API**, giả định `com.example.Plugin` tồn tại và `pluginLoader` đã được khai báo.

- `forName(String)` tìm lớp bằng defining loader của **lớp gọi API** và yêu cầu khởi tạo (`true`); nó không mặc định chọn thread context class loader.
- `forName(String, boolean, ClassLoader)` cho phép chọn **loader** và thời điểm khởi tạo. `false` thích hợp cho giai đoạn khám phá kiểu hoặc kiểm tra metadata; `true` thích hợp khi chủ ý kích hoạt logic `static`.
- `initialize=false` **không hoàn tác** một lớp đã khởi tạo từ trước, và cũng không ngăn một active use khác trong ứng dụng khởi tạo lớp sau đó. Nó không phải “khóa” giữ lớp ở trạng thái chưa khởi tạo.
- `loader == null` trong overload ba tham số nghĩa là dùng bootstrap class loader, **không phải** tự suy ra application loader.
- Overload `Class.forName(Module module, String name)` (Java 9+) có hợp đồng khác: chỉ cố tìm/nạp lớp trong module được chỉ định, **không liên kết hoặc khởi tạo lớp**, và trả `null` nếu không tìm thấy. Đừng nhầm nó với overload trả lỗi `ClassNotFoundException`.

### 4.2. Tên lớp phải là binary name

Với class thông thường, dùng `com.example.Plugin`; với member class `Outer.Inner`, tên nhị phân thường là `com.example.Outer$Inner`. Tên class nhập từ cấu hình phải được kiểm tra chính xác, bao gồm package và loader.

```java
Class<?> nested = Class.forName("java.util.Map$Entry", false,
        ClassLoader.getSystemClassLoader());
Class<?> strings = Class.forName("[Ljava.lang.String;", false,
        ClassLoader.getSystemClassLoader());
Class<?> matrix = Class.forName("[[I", false,
        ClassLoader.getSystemClassLoader());
Class<?> primitive = int.class;
```

Với mảng, chuỗi tên theo dạng JVM descriptor: `[Ljava.lang.String;` là `String[]`, `[[I` là `int[][]`. `Class.forName` cho lớp mảng có thể nạp kiểu phần tử nhưng **không khởi tạo kiểu phần tử**, kể cả khi `initialize=true`. Không dùng `Class.forName("int")` để lấy kiểu nguyên thủy; dùng `int.class` hoặc `Integer.TYPE`.

## 5. Thực hành 1: quan sát thời điểm chạy `static`

Tạo tệp **`LoadLinkInitDemo.java`** với nội dung độc lập sau:

```java
public class LoadLinkInitDemo {
    static class Parent {
        static {
            System.out.println("Parent init");
        }
    }

    static class Target extends Parent {
        static final int CONST = 42;
        static int counter = createCounter();

        static {
            System.out.println("Target static block");
        }

        static int createCounter() {
            System.out.println("Target static field");
            return 7;
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader = LoadLinkInitDemo.class.getClassLoader();

        System.out.println("A. Class literal: " + Target.class.getSimpleName());
        System.out.println("B. Compile-time const: " + Target.CONST);

        System.out.println("C. forName(false)");
        Class<?> loaded = Class.forName(
                "LoadLinkInitDemo$Target", false, loader);
        System.out.println(loaded.getName());

        System.out.println("D. forName(true)");
        Class.forName("LoadLinkInitDemo$Target", true, loader);

        System.out.println("E. static value=" + Target.counter);

        System.out.println("F. forName(true) again");
        Class.forName("LoadLinkInitDemo$Target", true, loader);
    }
}
```

Biên dịch và chạy bằng Java 17+:

```bash
javac LoadLinkInitDemo.java
java LoadLinkInitDemo
```

Đầu ra:

```text
A. Class literal: Target
B. Compile-time const: 42
C. forName(false)
LoadLinkInitDemo$Target
D. forName(true)
Parent init
Target static field
Target static block
E. static value=7
F. forName(true) again
```

**Giải thích theo thứ tự:**

1. `Target.class` lấy đối tượng `Class` và `getSimpleName()` đọc tên, không yêu cầu chạy initializer của `Target`.
2. `Target.CONST` là `static final int` với literal `42`, đủ điều kiện constant variable, nên được compiler sử dụng như hằng compile-time và không kích hoạt khởi tạo.
3. `forName(..., false, ...)` trả thông tin kiểu (`LoadLinkInitDemo$Target`). Không có dòng `Parent init` hay `Target ...`.
4. `forName(..., true, ...)` lần đầu yêu cầu initialization. JVM khởi tạo `Parent` trước, sau đó xử lý trường `counter` (in `Target static field`), rồi khối `static` kế tiếp.
5. Đọc `Target.counter` có giá trị `7`; tại đây class đã khởi tạo nên không in thêm dòng khởi tạo.
6. Gọi `forName(..., true, ...)` lần nữa không thực thi lại initializer.

Thí nghiệm thêm: chuyển `D. forName(true)` xuống sau câu lệnh đọc `Target.counter`. Khi đó **việc đọc trường `static`** trở thành thao tác khởi tạo đầu tiên và dòng log khởi tạo xuất hiện trước khi in giá trị `counter`.

## 6. Thực hành 2: preparation khác initialization ở điểm nào?

Tạo tệp **`PreparationDemo.java`**:

```java
public class PreparationDemo {
    static class Example {
        static int first = readSecond();
        static int second = 9;

        static int readSecond() {
            System.out.println("second before assignment=" + second);
            return 5;
        }
    }

    public static void main(String[] args) {
        System.out.println("first=" + Example.first
                + ", second=" + Example.second);
    }
}
```

```bash
javac PreparationDemo.java
java PreparationDemo
```

Đầu ra:

```text
second before assignment=0
first=5, second=9
```

Khi class `Example` được chuẩn bị, cả `first` và `second` có giá trị mặc định `0`. Lúc initialization, biểu thức gán `first` chạy trước và gọi `readSecond()`; thời điểm đó lệnh `second = 9` chưa được thực thi, nên in `0`. Sau đó `second` nhận `9`. Ví dụ cố ý đọc trường qua phương thức để minh họa thứ tự; trong code thực tế hãy tránh các phụ thuộc vòng quanh hoặc phụ thuộc vào biến `static` chưa gán.

## 7. Lỗi và đặc điểm nâng cao cần xử lý đúng

### 7.1. Initialization có thể thất bại và lớp rơi vào trạng thái lỗi

Tạo tệp **`InitializationFailureDemo.java`**:

```java
public class InitializationFailureDemo {
    static class Broken {
        static int value = fail();

        static int fail() {
            throw new IllegalStateException("boom");
        }
    }

    public static void main(String[] args) throws Exception {
        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                Class.forName("InitializationFailureDemo$Broken");
            } catch (LinkageError error) {
                System.out.println(attempt + ". "
                        + error.getClass().getSimpleName());
            }
        }
    }
}
```

```bash
javac InitializationFailureDemo.java
java InitializationFailureDemo
```

Đầu ra:

```text
1. ExceptionInInitializerError
2. NoClassDefFoundError
```

Lần đầu, biểu thức khởi tạo ném `IllegalStateException`, JVM bọc nguyên nhân bằng `ExceptionInInitializerError`. Sau thất bại, định nghĩa lớp `Broken` ở trạng thái lỗi; nỗ lực khởi tạo lại định nghĩa đó dẫn đến `NoClassDefFoundError` (thường kèm dấu vết nguyên nhân trước đó). Nếu initializer ném một `Error` thích hợp, JVM có thể truyền chính `Error` đó ra ngoài thay vì bọc. **Không “retry” khởi tạo cùng class bằng cách gọi `forName(true)` liên tục.** Cần sửa nguyên nhân, tạo môi trường/loader mới nếu kiến trúc cho phép, hoặc khởi động lại quy trình thích hợp.

### 7.2. Đừng gộp mọi lỗi vào “không tìm thấy lớp”

| Lỗi / nhóm lỗi | Hướng điều tra |
| --- | --- |
| `ClassNotFoundException` | Loader được yêu cầu không tìm được binary name; xem tên, classpath/module path, deployment và loader. |
| `NoClassDefFoundError` | Lỗi khi JVM cần định nghĩa/phụ thuộc đã từng khả dụng hoặc class đã khởi tạo thất bại; đọc `cause` và log **lần lỗi đầu tiên**. |
| `VerifyError`, `ClassFormatError` | Bytecode lỗi hoặc không hợp lệ so với ràng buộc JVM. |
| `NoSuchMethodError`, `NoSuchFieldError`, `IllegalAccessError` | Khác biệt phiên bản thư viện, chữ ký API, module/access hoặc lỗi khi resolution. |
| `ExceptionInInitializerError` | Mã khởi tạo `static` đã ném lỗi; kiểm tra initializer và nguyên nhân gốc. |

`ClassNotFoundException` là checked exception từ API tìm lớp; nhiều lỗi linkage/initialization là `Error`. Bắt riêng các loại lỗi phục vụ chẩn đoán, không nuốt `LinkageError` rồi tiếp tục coi hệ thống đã hoạt động bình thường.

### 7.3. Tính đồng thời, thứ tự và tác dụng phụ

- JVM bảo đảm một định nghĩa lớp không bị hai thread thực hiện initializer cùng lúc; thread đợi có thể gặp lỗi nếu initializer của thread đầu thất bại.
- Một initializer có thể mở kết nối, tạo thread, đọc cấu hình hoặc gọi mã ở lớp khác. `forName(true)` vì vậy có thể là thao tác **có tác dụng phụ**, dù không có `new` trong code người gọi.
- Class loading, linking và resolution có thể xảy ra ở thời điểm khác với suy luận từ log. Tránh phụ thuộc vào thứ tự chi tiết không được đặc tả; chỉ dựa vào các bảo đảm về khởi tạo và active use.
- Với các hệ có nhiều class loader, kiểu cùng tên nhưng loader khác có thể có trạng thái `static` khác nhau và không ép kiểu qua lại được.

## 8. Áp dụng trong hệ thống nạp plugin hoặc cấu hình động

Giả sử cấu hình chứa tên lớp của plugin. Có hai nhu cầu riêng:

1. **Khám phá/kiểm tra trước khi kích hoạt:** chọn đúng class loader, dùng `Class.forName(name, false, loader)` để lấy `Class<?>` và kiểm tra tên, interface, annotation hay constructor cần thiết. Các thao tác reflection nhất định có thể kéo theo việc nạp hoặc phân giải kiểu liên quan; tránh giả định “chưa khởi tạo” có nghĩa toàn bộ thao tác metadata là vô tác dụng phụ.
2. **Kích hoạt tại thời điểm đã quyết định:** có thể gọi `Class.forName(name, true, loader)` trước khi sử dụng, để thời điểm khởi tạo và lỗi khởi tạo rõ ràng. Nếu ngay sau đó dùng reflection để gọi constructor tạo instance thì hành động tạo instance cũng sẽ yêu cầu khởi tạo; không bắt buộc gọi `true` riêng nếu không cần một ranh giới kích hoạt tường minh.

Mẫu quyết định:

| Mục tiêu | Lựa chọn thường hợp lý |
| --- | --- |
| Chỉ đọc mô tả lớp/khám phá plugin | `forName(name, false, loader)` |
| Yêu cầu initializer chạy ngay ở bước activate | `forName(name, true, loader)` |
| Dùng loader riêng của ứng dụng/plugin | Overload ba tham số với loader đã xác minh |
| Muốn tạo instance ngay | Reflection constructor; nhớ rằng nó khởi tạo class |
| Muốn hoàn tác initializer đã chạy | Không có thao tác `forName` nào thực hiện điều này |

Trong production, kiểm tra độ tin cậy của nguồn tên lớp và class loader. Việc nạp một class không tự động làm class đó “an toàn”; đặc biệt `initialize=true` có thể thực thi mã `static` với quyền của ứng dụng. Nếu cần theo dõi nạp lớp trên HotSpot, có thể thử `java -Xlog:class+load=info ...`; log nạp lớp **không phải** bằng chứng lớp đó đã chạy `<clinit>`.

## 9. Các nhầm lẫn thường gặp và tự kiểm tra

- **“Loaded = initialized.”** Sai. Một `Class<?>` có thể tồn tại trước khi `static` chạy.
- **“Linking luôn phân giải hết các class/method một lần.”** Sai. Resolution có thể trì hoãn.
- **“`Class.forName(name)` giống `ClassLoader.loadClass(name)`.”** Sai về yêu cầu initialization của API thông thường.
- **“`forName(false)` chắc chắn tránh mọi công việc khác.”** Sai. Nó không khởi tạo *lớp mục tiêu* nhưng vẫn có loading/linking và mã của custom loader.
- **“Đọc bất kỳ `static final` nào cũng không khởi tạo lớp.”** Sai; chỉ constant variable theo quy tắc compile-time có ngoại lệ đó.
- **“`forName(true)` luôn in log lại.”** Sai; initializer thành công chỉ chạy một lần trên cùng định nghĩa lớp.

Tự trả lời trước khi xem gợi ý:

1. Vì sao `Target.class` có thể không in `static`, còn `Class.forName("Target")` lại in?
2. Khi `Child extends Parent` và gọi `Class.forName("Child", true, loader)` lần đầu, initializer class nào chạy trước?
3. Nếu `Target.X` là `static final int X = Integer.parseInt("8");`, việc đọc `Target.X` có yêu cầu initialization không?
4. Tại sao `Class.forName("[Lpkg.Target;", true, loader)` không phải cách chủ động chạy `pkg.Target`'s initializer?
5. Tại sao lỗi `NoClassDefFoundError` ở lần sử dụng thứ hai có thể bắt nguồn từ một `ExceptionInInitializerError` trước đó?

**Gợi ý đáp án:** (1) Class literal không phải active use, overload một tham số yêu cầu `initialize=true`. (2) `Parent` rồi `Child` nếu cả hai chưa khởi tạo. (3) Có, vì `parseInt` không phải constant expression. (4) Tên mô tả kiểu mảng, chỉ nạp kiểu phần tử chứ không khởi tạo nó. (5) JVM ghi nhận class đã khởi tạo thất bại và không chạy lại initializer cho cùng định nghĩa lớp.

## 10. Tài liệu chuẩn để đối chiếu

- [Java Language Specification 21, `12.2–12.4: Loading, Linking, Initialization](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html).
- [Java Virtual Machine Specification 21, Chapter 5: Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html).
- [Java SE 21 API: `java.lang.Class` và các overload `forName`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html).

Nắm được ranh giới **nạp → liên kết → khởi tạo**, bạn có thể dự đoán đúng khi nào logic `static` thực thi, sử dụng `Class.forName` đúng mục đích và khoanh vùng lỗi runtime mà không nhầm một kiểu đã được nạp với một kiểu đã được khởi tạo.