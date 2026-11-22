# `ClassLoader.loadClass` và ý nghĩa của tham số `resolve`

## 1. Mục tiêu bài học

Trong Java, phương thức `ClassLoader.loadClass` trả về đối tượng `Class<?>` tương ứng với một tên lớp hoặc interface. Tuy nhiên, cần phân biệt rõ:

- **Loading**: JVM tìm hoặc tạo định nghĩa kiểu runtime.
- **Linking**: JVM kiểm tra, chuẩn bị và phân giải các tham chiếu cần thiết của định nghĩa kiểu.
- **Initialization**: JVM chạy mã khởi tạo static theo quy tắc active use.

Đối với `ClassLoader`, có hai overload quan trọng:

~~~java
public Class<?> loadClass(String name) throws ClassNotFoundException;

protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException;
~~~

Overload **một tham số** hoạt động tương đương gọi **`loadClass(name, false)`**. Trong overload hai tham số, **`resolve == true`** yêu cầu bước **`resolveClass(c)`** trong thuật toán mặc định, tức yêu cầu liên kết đối tượng `Class` được tìm thấy; nó **không phải cờ khởi tạo lớp**.

Bài học trả lời những câu hỏi thực tế:

1. `loadClass` tìm lớp qua cơ chế parent delegation như thế nào?
2. Cờ `resolve` tác động ở bước nào?
3. Tại sao `resolve=true` vẫn có thể chưa chạy static block?
4. Khi nào nên dùng `Class.forName` với cờ `initialize` thay vì `loadClass`?
5. Làm sao viết và kiểm tra subclass `ClassLoader` mà không nhầm loading, linking, initialization?

## 2. Chữ ký và hợp đồng của hai overload

| API | Phạm vi truy cập | Hành vi quan trọng |
| --- | --- | --- |
| `loadClass(String name)` | `public` | Nạp/tìm class theo binary name; mặc định gọi overload hai tham số với `resolve=false`. |
| `loadClass(String name, boolean resolve)` | `protected` | Trong cài đặt mặc định, thực hiện delegation và khi `resolve=true` gọi `resolveClass(c)` trên kết quả. |
| `resolveClass(Class<?> c)` | `protected final` | Yêu cầu JVM liên kết class nếu chưa được liên kết; lớp có thể do loader khác định nghĩa. |
| `findLoadedClass(String name)` | `protected final` | Kiểm tra lớp JVM đã ghi nhận loader là initiating loader, giúp tránh làm lại việc tải cùng tên. |
| `findClass(String name)` | `protected` | Điểm mở rộng để loader tự tìm/định nghĩa khi delegation không tìm thấy. |

**Lưu ý về visibility:** code ứng dụng thông thường **không thể trực tiếp gọi** `loader.loadClass("a.B", true)` nếu không nằm trong phạm vi truy cập `protected`. Ví dụ biên dịch được là gọi **`loader.loadClass("a.B")`**, hoặc tạo subclass có wrapper public cho mục đích giảng dạy.

`name` thường là **binary name** như `java.lang.String` hoặc `demo.Widget`. Với member class lồng có tên nhị phân `example.Outer$Inner`, ký hiệu `$` là thành phần của binary name. Không nhầm tên binary này với resource path `example/Outer$Inner.class`.

## 3. Thuật toán mặc định của `loadClass(name, resolve)`

Tài liệu `ClassLoader` mô tả cài đặt mặc định theo hướng parent-first. Lược đồ:

~~~text
loadClass(name, resolve)
          │
          ▼
getClassLoadingLock(name)
          │
          ▼
findLoadedClass(name)
          │
          ├──── class đã được ghi nhận ───────────────┐
          │                                          │
          └─ null                                    │
               │                                     │
               ▼                                     │
       hỏi parent loader (hoặc bootstrap)            │
               │                                     │
         ┌─────┴─────┐                               │
         │ tìm được  │───────────────────────────────┤
         │           │                               │
         └─ không có ┘                               │
               │                                     │
               ▼                                     │
         findClass(name)                              │
               │                                     │
               └────────── Class<?> c ────────────────┘
                                                      │
                                                      ▼
                                         resolve == true?
                                           │        │
                                          Có       Không
                                           │        │
                                           ▼        │
                                      resolveClass(c)
                                           │        │
                                           └────┬───┘
                                                ▼
                                         return Class<?> c
~~~

Mã giả gần với ý nghĩa của JDK, nhưng không phải mã nguồn JDK nguyên văn:

~~~java
// Pseudocode: các bước JVM/parent được rút gọn cho dễ học.
synchronized (getClassLoadingLock(name)) {
    Class<?> c = findLoadedClass(name);
    if (c == null) {
        try {
            c = parentOrBootstrapLoad(name);
        } catch (ClassNotFoundException e) {
            c = findClass(name);
        }
    }
    if (resolve) {
        resolveClass(c);
    }
    return c;
}
~~~

Các điểm cần ghi nhớ:

1. **Cache/tracking trước:** `findLoadedClass(name)` giúp trả về định nghĩa mà JVM đã ghi nhận là được initiate bởi loader tương ứng.
2. **Delegation:** cài đặt mặc định trao cơ hội cho parent trước khi tự tìm.
3. **Fallback:** chỉ khi parent/bootstrap không tìm được mới cần `findClass(name)` ở loader đang xét.
4. **Cờ resolve được xử lý sau khi có `Class`:** chọn `true` không biến việc tìm bytecode thành một thuật toán tra cứu khác.
5. **Kết quả là `Class<?>`, không phải instance** của lớp đó. `loadClass` không gọi constructor để tạo object của lớp được nạp.

Một custom loader có thể override `loadClass` và dùng chính sách khác, ví dụ child-first có điều kiện. Bởi vậy đây là mô hình cho **implementation mặc định** và những subclass kế thừa nó, không là lời hứa về mọi ClassLoader tùy biến trên thế giới.

## 4. `resolve=true` thực sự có nghĩa gì?

Tên tham số dễ gây hiểu nhầm. Trong `loadClass(name, true)`, `resolve` mang nghĩa “**yêu cầu liên kết class được trả về**” trong thuật toán mặc định. Bước này gọi `resolveClass(c)`.

Ở mức JVM, liên kết gồm các hoạt động lớn:

| Giai đoạn linking | Mục đích |
| --- | --- |
| **Verification** | Xác minh định nghĩa/bytecode hợp lệ đối với các quy tắc JVM. |
| **Preparation** | Chuẩn bị lưu trữ cho static fields và thiết lập giá trị ban đầu theo đặc tả (không chạy tùy ý static initializer Java). |
| **Resolution** | Chuyển symbolic references thành các tham chiếu runtime tương ứng khi JVM thực hiện phân giải. |

**Không đồng nhất** tên `resolveClass` với lời cam kết “mọi symbolic reference trong constant pool đã được phân giải đầy đủ ngay bây giờ”. JVM Specification cho phép **resolution theo nhu cầu (lazy)**; nhiều lỗi resolution có thể xuất hiện khi một tham chiếu cụ thể lần đầu được sử dụng. `resolveClass` là yêu cầu linking đối với class theo hợp đồng ClassLoader, không phải API liệt kê hoặc ép phân giải toàn bộ dependencies của class.

Một số hệ quả:

- `resolve=false` **không bảo đảm** class chưa từng được link. JVM có thể đã thực hiện một phần hoặc toàn bộ linking vì nhu cầu khác.
- `resolve=true` **không chạy static initializer** chỉ do cờ đó được chọn.
- `resolve=true` **không bắt buộc nạp mọi class** xuất hiện trong mọi tên phương thức, field hoặc constant pool của lớp ngay lập tức.
- Nếu class đã được liên kết, gọi `resolveClass` không tạo định nghĩa class mới hay chạy mã static một lần nữa.
- Một lỗi xác minh hoặc liên kết có thể lộ ra trong quá trình này, nhưng **thời điểm chính xác của một số lỗi resolution** còn phụ thuộc quy tắc JVM và việc sử dụng thực tế.

### 4.1 Đọc `resolve` là “kết nối class” vẫn chưa đủ

Nói “`resolve=true` = resolve mọi reference” là quá mạnh. Nói “`resolve=true` chỉ đổi Boolean nhưng chẳng ảnh hưởng gì” lại bỏ sót phần liên kết mà loader yêu cầu.

Cách hiểu đúng: **sau khi tìm được `Class<?> c`, overload mặc định có thể yêu cầu JVM link `c` bằng `resolveClass(c)` khi cờ true**. Nó không thay đổi quy tắc khởi tạo và không hứa rằng mọi tham chiếu biểu tượng trong toàn bộ ứng dụng đều được xử lý ngay.

## 5. Khác biệt giữa `resolve` và `initialize`

Đây là điểm quan trọng nhất đối với người học Java ClassLoader.

- **Resolve / link:** liên quan đến tính hợp lệ và trạng thái liên kết kiểu.
- **Initialize:** thực thi mã khởi tạo static của class/interface theo JLS §12.4.

Hai thao tác có thời điểm và trigger khác nhau. Với class:

~~~java
class Target {
    static {
        System.out.println("Target initialized");
    }
}
~~~

Sau `loader.loadClass("Target")`, JVM đã có `Class` nhưng không nhất thiết chạy static block. Kể cả khi có lời gọi `loadClass("Target", true)` thông qua subclass, bản thân cờ này vẫn **không phải** trigger initialization.

Ngược lại, `Class.forName` cung cấp overload với tham số khác:

~~~java
Class<?> a = Class.forName("java.lang.String");
Class<?> b = Class.forName("java.lang.String", false, loader);
Class<?> c = Class.forName("java.lang.String", true, loader);
~~~

**`Class.forName(name, initialize, loader)`** có cờ **`initialize`**: khi `true`, yêu cầu initialization nếu class chưa initialized. Dạng một đối số `Class.forName(name)` mặc định yêu cầu initialization. Đó là khác biệt ngữ nghĩa cơ bản với cờ `resolve` của ClassLoader.

| Tác vụ | Tìm/nạp `Class` | Liên kết | Yêu cầu initialization |
| --- | --- | --- | --- |
| `loader.loadClass(name)` | Có | Khi JVM cần; không chủ động yêu cầu `resolveClass` trong overload mặc định. | **Không** |
| `loadClass(name, false)` trong subclass | Có | Tương tự trên. | **Không** |
| `loadClass(name, true)` trong subclass kế thừa thuật toán mặc định | Có | Gọi `resolveClass` trên Class được trả về. | **Không** |
| `Class.forName(name, false, loader)` | Có | API yêu cầu locate/load/link. | **Không** |
| `Class.forName(name, true, loader)` | Có | Có | **Có** |
| `new Target()` | Có kiểu đã sẵn sàng cho sử dụng | JVM làm linking cần thiết | **Có**, nếu chưa init |
| Đọc `Target.nonConstantStatic` | Có kiểu đã sẵn sàng cho sử dụng | JVM làm linking cần thiết | **Có**, nếu field do Target khai báo và chưa init |

**Đọc constant variables:** ví dụ `static final int MAX = 10` với compile-time constant expression là trường hợp riêng; phép đọc hằng có thể được compiler in-line và **không tự** gây initialization. Điều này không liên quan trực tiếp đến tham số resolve nhưng giúp tránh suy luận “cứ dùng tên class là init”.

## 6. Ví dụ chạy được số 1: so sánh `resolve=false` và `resolve=true`

Lưu file **ResolveFlagDemo.java**:

~~~java
public class ResolveFlagDemo {
    static class Target {
        static {
            System.out.println("Target: static block");
        }

        static int value = compute();

        static int compute() {
            System.out.println("Target: compute");
            return 42;
        }
    }

    static class InspectingLoader extends ClassLoader {
        InspectingLoader(ClassLoader parent) {
            super(parent);
        }

        public Class<?> loadWithResolve(String name, boolean resolve)
                throws ClassNotFoundException {
            System.out.println("request resolve = " + resolve);
            return super.loadClass(name, resolve);
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            System.out.println("child findClass called");
            throw new ClassNotFoundException(name);
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader app = ResolveFlagDemo.class.getClassLoader();
        InspectingLoader child = new InspectingLoader(app);

        String targetName = Target.class.getName();

        Class<?> first = child.loadWithResolve(targetName, false);
        System.out.println("false: same Class = " + (first == Target.class));

        Class<?> second = child.loadWithResolve(targetName, true);
        System.out.println("true: same Class = " + (second == Target.class));

        System.out.println("before active use");
        System.out.println("value = " + Target.value);
    }
}
~~~

Chạy trên JDK 17+:

~~~bash
javac ResolveFlagDemo.java
java ResolveFlagDemo
~~~

Stdout:

~~~text
request resolve = false
false: same Class = true
request resolve = true
true: same Class = true
before active use
Target: static block
Target: compute
value = 42
~~~

### 6.1 Giải thích từng dòng

1. `Target.class.getName()` lấy binary name của nested class, không chủ động initialization Target.
2. Cả hai lời gọi `child.loadWithResolve(...)` dùng **`super.loadClass(name, resolve)`**. Implementation mặc định tìm lớp qua application parent loader. Child không phải defining loader của Target.
3. Lần đầu `resolve=false` trả về `Class`; lần sau `resolve=true` yêu cầu `resolveClass` trên cùng Class nếu cần. Cả hai so sánh `==` với `Target.class` đều đúng.
4. Dòng **child findClass called** không xuất hiện vì parent tìm được Target. Điều này cho thấy cờ `resolve` không làm bỏ qua delegation.
5. Sau hai lời gọi loadClass vẫn chưa có dòng **Target: static block**. Initialization chỉ bắt đầu khi chương trình lần đầu đọc trường runtime `Target.value`.
6. Theo thứ tự khai báo, Target in static block rồi gọi `compute()` để gán 42 cho value, sau đó mới in dòng cuối.

**Giới hạn của ví dụ:** stdout chứng minh rằng cả `resolve=false` và `resolve=true` **không chủ động initialization**. Nó không có cách trực tiếp in thời điểm verification/resolution của từng symbolic reference. Vì thế không nên dùng sự vắng mặt của log để tuyên bố chắc chắn JVM chưa linking lúc `resolve=false`.

### 6.2 Tại sao phải viết wrapper `loadWithResolve`?

Overload hai tham số được khai báo **`protected`**. Code bên ngoài không thể viết tùy tiện:

~~~java
// KHÔNG biên dịch trong mã ứng dụng thông thường:
// new ClassLoader().loadClass("demo.Target", true);
~~~

Trong ví dụ runnable, subclass `InspectingLoader` truy cập method protected thông qua `super.loadClass(name, resolve)`, và cung cấp **public wrapper** chỉ để minh họa ý nghĩa cờ. Phương thức public `loadClass(name)` của ClassLoader vẫn là API thông thường mà code bên ngoài sử dụng.

## 7. Ví dụ chạy được số 2: parent không tìm thấy, `findClass` mới được gọi

Cờ `resolve` không thay đổi chuỗi tìm class, nhưng để thấy toàn bộ hành trình bạn có thể thử một loader đọc file `.class` riêng.

Tạo cấu trúc:

~~~text
project/
├── DirectoryLoaderDemo.java
└── src/
    └── plugin/
        └── Greeter.java
~~~

**src/plugin/Greeter.java**:

~~~java
package plugin;

public class Greeter {
    static {
        System.out.println("Greeter initialized");
    }

    public String message() {
        return "Hello";
    }
}
~~~

**DirectoryLoaderDemo.java**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class DirectoryLoaderDemo {
    static final class DirectoryLoader extends ClassLoader {
        private final Path root;

        DirectoryLoader(Path root) {
            super(ClassLoader.getPlatformClassLoader());
            this.root = root.toAbsolutePath().normalize();
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            Path file = root.resolve(
                    name.replace('.', '/') + ".class"
            ).normalize();

            if (!file.startsWith(root)) {
                throw new ClassNotFoundException(name);
            }

            byte[] bytes;
            try {
                bytes = Files.readAllBytes(file);
            } catch (IOException ex) {
                throw new ClassNotFoundException(name, ex);
            }

            System.out.println("findClass: " + name);
            return defineClass(name, bytes, 0, bytes.length);
        }

        public Class<?> loadWithResolve(String name, boolean resolve)
                throws ClassNotFoundException {
            return super.loadClass(name, resolve);
        }
    }

    public static void main(String[] args) throws Exception {
        DirectoryLoader loader =
                new DirectoryLoader(Path.of("plugin-classes"));

        Class<?> loaded = loader.loadWithResolve("plugin.Greeter", false);
        System.out.println("defined by child = "
                + (loaded.getClassLoader() == loader));

        Class<?> linked = loader.loadWithResolve("plugin.Greeter", true);
        System.out.println("same Class = " + (loaded == linked));

        System.out.println("before instance");
        Object object = linked.getDeclaredConstructor().newInstance();
        String message = (String) linked.getMethod("message")
                .invoke(object);
        System.out.println("message = " + message);
    }
}
~~~

Chạy từ thư mục **project**:

~~~bash
javac -d plugin-classes src/plugin/Greeter.java
javac DirectoryLoaderDemo.java
java -cp . DirectoryLoaderDemo
~~~

Stdout:

~~~text
findClass: plugin.Greeter
defined by child = true
same Class = true
before instance
Greeter initialized
message = Hello
~~~

### 7.1 Tại sao lần thứ nhất đi vào `findClass`?

`DirectoryLoader` có platform loader làm parent. Trong lệnh chạy này, `plugin-classes` **không nằm trong application classpath**, nên platform parent không tìm được `plugin.Greeter`. Loader riêng phải đọc file `plugin-classes/plugin/Greeter.class`, gọi `defineClass`, rồi trả Class.

### 7.2 Tại sao lần thứ hai không gọi `findClass`?

JVM đã có định nghĩa `plugin.Greeter` gắn với loader. Lời gọi `loadWithResolve(..., true)` trả về cùng đối tượng `Class`; phần `findLoadedClass` đã tìm được nên không cần đọc lại file. Sau khi có kết quả, cờ true khiến implementation mặc định yêu cầu `resolveClass`.

### 7.3 Khi nào static block chạy?

**Greeter initialized** chỉ xuất hiện khi reflection tạo instance bằng `getDeclaredConstructor().newInstance()`. Đây là active use khiến class được initialized. `resolve=false` và `resolve=true` ở hai lời gọi trước đều không tự thực hiện bước này.

### 7.4 Lưu ý đối với custom loader thực tế

Code này là ví dụ dành cho thư mục đã biết. Hệ thống nạp class từ dữ liệu không tin cậy cần kiểm soát nguồn bytes, tên hợp lệ, kích thước file, đường dẫn symlink, các quyền truy cập và ràng buộc bảo mật. Tránh mở rộng trực tiếp đoạn minh họa thành cơ chế nạp plugin từ nguồn tùy ý mà không có kiểm soát.

**Đối chiếu quan trọng:** nếu bạn thêm `plugin-classes` vào `-cp` hoặc dùng một parent loader cũng thấy `plugin.Greeter`, parent-first có thể trả class do parent định nghĩa. Khi đó **không** có dòng `findClass: plugin.Greeter`; stdout kỳ vọng ở trên chỉ đúng với chính các lệnh đã cho.

## 8. Những điều `resolve=true` KHÔNG bảo đảm

Đây là phần nên đọc trước khi cố sử dụng cờ resolve làm “kiểm tra trước mọi lỗi”:

| Kết luận sai | Thực tế |
| --- | --- |
| “`resolve=true` chạy mọi `static {}`.” | Initialization là bước khác, với trigger riêng. |
| “`resolve=false` có nghĩa class chưa liên kết.” | JVM có thể đã liên kết vì sử dụng trước đó hoặc quyết định implementation. |
| “`resolve=true` tải mọi lớp dependency.” | Không có cam kết toàn bộ symbolic references được eager resolve ngay. |
| “`resolve=true` luôn phát hiện mọi NoSuchMethodError trước khi chạy.” | Resolution có thể lazy; lỗi có thể lộ ra khi method/field được sử dụng. |
| “`resolve=true` tạo class object mới.” | Cùng định nghĩa runtime được trả về; linking không phải một lượt define mới. |
| “`resolve=true` làm child loader ưu tiên trước parent.” | Cờ chỉ liên quan bước sau khi đã tìm được Class. |
| “Nếu `loadClass` trả về Class thì constructor đã chạy.” | Chỉ có metadata runtime của kiểu; constructor chạy khi thực sự tạo instance. |

Một class có thể tham chiếu tới các kiểu hoặc member khác chưa được giải quyết hoàn toàn tại thời điểm `loadClass` trả về. JVM bảo đảm những ràng buộc và lỗi theo điểm sử dụng do đặc tả quy định; đó là lý do không thể dùng một lời gọi loadClass để “chứng nhận” mọi nhánh thực thi của toàn bộ dependency graph.

## 9. ClassLoader `resolve` và việc phân giải trong JVM là hai lớp khái niệm

Tên `resolveClass` do API ClassLoader cung cấp dễ dẫn tới phát biểu thiếu chính xác:

~~~text
resolveClass(c) == eagerly resolve all constant-pool entries
~~~

Phát biểu này **không đúng**.

Class-file constant pool có nhiều loại symbolic reference; nhiều mục chỉ được sử dụng khi bytecode tương ứng chạy. JVM có thể lựa chọn **lazy** hoặc **eager** resolution theo quy tắc và thời điểm lỗi cần quan sát theo JVMS.

Khi một symbolic reference cụ thể được resolution, JVM có thể tìm method/field/class và kiểm tra access hoặc loại kiểu. Các lỗi như `NoSuchMethodError`, `NoSuchFieldError` hay `IllegalAccessError` có thể lộ ra tại một điểm runtime; chúng không nhất thiết xuất hiện ngay ở lệnh `loadClass(name, true)`.

Do đó, hãy dùng tên “**liên kết class**” để diễn đạt ý nghĩa tham số resolve của ClassLoader, đồng thời gọi “**symbolic-reference resolution**” khi muốn bàn riêng từng tham chiếu bên trong constant pool.

## 10. Quan hệ với defining loader và initiating loader

Giả sử object loader A nhận yêu cầu `A.loadClass("demo.Shared")`, nhưng parent B đã định nghĩa `demo.Shared`:

~~~text
caller
  │
  └─ A.loadClass(name, resolve)
         │
         ├─ parent B.loadClass(name)
         │          │
         │          └─ Class<?> do B định nghĩa
         │
         ├─ nếu resolve=true, yêu cầu resolveClass(c)
         │
         └─ trả về Class<?> của B
~~~

`Class.getClassLoader()` của kết quả trả về **B**, không phải A. B là **defining loader**, còn A có thể là **initiating loader** theo mô hình JVM loading. Cờ `resolve` không chuyển quyền sở hữu định nghĩa từ B sang A.

Nhiều child loader khác nhau có thể cùng delegate tới một parent và nhận **cùng Class**. Ngược lại, nếu hai loader khác nhau thực sự `defineClass` cho cùng binary name, đó là hai kiểu runtime khác nhau. Danh tính class thông thường phụ thuộc cặp **(binary name, defining loader)**.

Điểm thực hành: trong log bạn thấy `myLoader.loadClass("x.Y")` thành công, hãy kiểm tra **`returnedClass.getClassLoader()`** trước khi kết luận loader nào đã thực sự định nghĩa `x.Y`.

## 11. Đồng bộ và khả năng chạy đồng thời

Implementation mặc định của `ClassLoader.loadClass(name, boolean)` đồng bộ theo **`getClassLoadingLock(name)`**:

- Với loader không được đăng ký **parallel capable**, lock có thể là chính đối tượng ClassLoader.
- Với loader parallel capable, lock có thể riêng theo từng binary name, cho phép load các class khác nhau song song.
- Trạng thái đã load được kiểm tra trong critical section để tránh cố define trùng trong tình huống concurrent loading.

Nếu tùy biến toàn bộ `loadClass`, bạn phải hiểu quan hệ giữa `getClassLoadingLock`, `findLoadedClass`, parent delegation và defineClass. Một implementation không an toàn có thể gây đua giữa hai thread, `LinkageError` hoặc deadlock giữa các loader.

**Với bài toán chỉ muốn thêm nguồn bytecode, thường nên override `findClass` và giữ thuật toán `loadClass` mặc định**, bởi nó đã xử lý delegation, khóa và việc dùng lại Class.

## 12. Xử lý lỗi: lỗi nào thuộc lúc nào?

| Lỗi hoặc hiện tượng | Gợi ý nguyên nhân | Đọc thế nào trong bối cảnh `loadClass` |
| --- | --- | --- |
| `ClassNotFoundException` | Loader không tìm/không nạp được class theo tên yêu cầu. | Checked exception của API load; kiểm tra tên, nguồn bytes, parent và custom findClass. |
| `ClassFormatError` | Binary representation không hợp lệ. | Có thể xuất hiện khi define class, không phải trạng thái “không tìm thấy file”. |
| `UnsupportedClassVersionError` | Class-file version không được runtime hỗ trợ. | Kiểm tra JDK biên dịch/JDK chạy và class-file major version. |
| `VerifyError` | Vi phạm các quy tắc verifier. | Liên quan linking; đừng gọi nó là lỗi static initializer. |
| `NoClassDefFoundError` | Thiếu định nghĩa cần thiết ở runtime hoặc class từng bị initialization thất bại. | Có thể khác với `ClassNotFoundException`; xem cause và thời điểm. |
| `NoSuchMethodError` / `NoSuchFieldError` | Tham chiếu nhị phân không còn tương thích. | Có thể lộ ra khi resolution/use; `resolve=true` không bảo đảm bắt mọi lỗi sớm. |
| `ExceptionInInitializerError` | Exception phát sinh trong static initialization. | Không phải lỗi mà cờ `resolve` chủ động tạo; điều tra cause của mã static. |
| `LinkageError` do define trùng | Loader cố định nghĩa một lớp cùng tên thêm lần nữa. | Kiểm tra logic tải/cache/thread safety và nguồn class. |

Với custom loader, đừng bắt mọi `Throwable` rồi đổi thành `ClassNotFoundException`; như vậy che mất lỗi format, verify, linkage hoặc bug của loader. Nếu **không tìm thấy bytes**, hãy ném **`ClassNotFoundException`**, lý tưởng kèm cause khi I/O lỗi. Nếu bytes đã được tìm nhưng invalid, để lỗi thích hợp của JVM bộc lộ.

## 13. Chẩn đoán sự cố theo từng bước

Khi gặp lỗi liên quan `loadClass`, hãy thực hiện các kiểm tra theo thứ tự:

1. **Tên đầu vào:** giá trị `name` đúng binary name chưa? Với nested type, kiểm tra `$`.
2. **Nguồn class:** bytes được tìm ở classpath/module path/JAR/thư mục loader mong đợi không?
3. **Loader thực tế:** object nào nhận yêu cầu, parent của nó là ai, có override `loadClass` không?
4. **Defining loader:** `clazz.getClassLoader()` trả loader nào sau khi thành công? Class có bị parent định nghĩa trước không?
5. **Lúc nào xảy ra exception:** trong load/define, linking, hay lần active use gây initialization?
6. **Có sự khác biệt `resolve=false` và `resolve=true` không?** Nếu có, quan sát lỗi và nguyên nhân thực; đừng đồng nhất với khởi tạo.
7. **Có loader khác định nghĩa cùng binary name không?** So sánh chính đối tượng `Class`, không chỉ so `getName()`.
8. **Có thay đổi classpath/JDK không?** Kiểm tra đúng phiên bản runtime khi tái hiện.

Có thể dùng:

~~~bash
javap -verbose ResolveFlagDemo
java -Xlog:class+load=info ResolveFlagDemo
java -Xlog:help
~~~

`javap` đọc class file/bytecode đã biên dịch. Unified Logging giúp quan sát loading trên các JVM hỗ trợ (như HotSpot hiện đại). Các log này **không trực tiếp chứng minh** mọi symbolic reference đã resolution hoặc static initializer đã chạy; hãy dùng những dòng in riêng trong ví dụ để xác định initialization.

## 14. Những lỗi sử dụng API phổ biến

### 14.1 Gọi overload protected như thể nó là public

Câu lệnh sau không biên dịch trong code ứng dụng thông thường:

~~~java
// Ví dụ KHÔNG hợp lệ từ một class không phải subclass:
ClassLoader.getSystemClassLoader().loadClass("java.lang.String", true);
~~~

Nguyên nhân là `loadClass(String, boolean)` là **protected**. Dùng API public `loadClass(name)`, hoặc wrapper trong subclass như ví dụ khi cần kiểm tra cờ.

### 14.2 Tự override loadClass chỉ để đọc file

Nếu nhu cầu đơn thuần là “tìm bytecode ở nơi khác”, override **`findClass`** thường đủ. Override **`loadClass`** toàn bộ có thể làm sai thứ tự parent delegation, bỏ qua `findLoadedClass`, dẫn tới define trùng hoặc phá quy tắc class identity.

### 14.3 Coi resolve=true là cơ chế khởi tạo sớm

Muốn yêu cầu initialization theo API, cân nhắc **`Class.forName(name, true, loader)`**, biết rằng static initializer có thể gây side effects và lỗi. Dùng `loadClass(name, true)` (trong subclass) không có ý nghĩa đó.

### 14.4 Coi resolve=false là cam kết “Class chưa được kiểm tra”

Java không cho caller dùng flag false để buộc JVM tránh mọi việc verification/linking. Class đã được trả về có thể được VM xử lý theo chiến lược eager/lazy và theo yêu cầu sử dụng.

### 14.5 Coi mọi error khi chạy là phát sinh tại loadClass

Một thư viện có thể load thành công nhưng thiếu method được dùng ở nhánh logic sau; symbolic-reference resolution lúc đó mới báo lỗi. Hãy xác định stack trace và tình huống tạo lỗi, tránh dựa vào thời điểm người dùng nhìn thấy lỗi.

## 15. Tự kiểm tra

**Câu 1.** `ClassLoader.loadClass("pkg.Type")` tương đương overload hai tham số với cờ nào?

**Đáp án:** `resolve=false`, theo implementation của ClassLoader.

**Câu 2.** `resolve=true` có đảm bảo chạy `static {}` của Type không?

**Đáp án:** Không. Nó yêu cầu linking qua `resolveClass` trong thuật toán mặc định; initialization là bước riêng.

**Câu 3.** Vì sao code bình thường không gọi trực tiếp `loader.loadClass(name, true)` được?

**Đáp án:** Overload này là **protected**, chỉ truy cập được theo quy tắc `protected` của Java.

**Câu 4.** Nếu class được parent loader định nghĩa, cờ `resolve=true` có làm child loader định nghĩa lại class không?

**Đáp án:** Không. Child vẫn trả Class của parent; linking không chuyển defining loader.

**Câu 5.** Có thể có `NoSuchMethodError` sau khi `loadClass(name, true)` đã thành công không?

**Đáp án:** Có. Không có cam kết toàn bộ symbolic references được eager resolution ngay; lỗi có thể bộc lộ khi reference cụ thể được sử dụng.

**Câu 6.** Khi một custom loader chỉ cần nạp bytes từ thư mục riêng, thường nên override method nào?

**Đáp án:** `findClass(name)` để tìm bytes và `defineClass`; giữ lại `loadClass` mặc định nếu chính sách delegation đáp ứng yêu cầu.

**Câu 7.** `Class.forName(name, false, loader)` và `Class.forName(name, true, loader)` khác nhau quan trọng ở đâu?

**Đáp án:** Tham số **initialize** điều khiển yêu cầu initialization của class, không phải cờ resolve của ClassLoader.

**Câu 8.** Class loader đã trả Class, liệu constructor instance của Type chắc chắn được gọi chưa?

**Đáp án:** Chưa. `loadClass` trả class metadata; muốn tạo instance phải dùng thao tác tạo đối tượng thích hợp.

**Câu 9.** `resolve=false` có đảm bảo verifier chưa chạy không?

**Đáp án:** Không. JVM có thể thực hiện verification/linking theo các quy tắc và nhu cầu hợp lệ khác; cờ false không phải một cơ chế trì hoãn tuyệt đối.

## 16. Tóm tắt

~~~text
loadClass(name, false)
  └─ tìm/trả Class<?> theo delegation, không tự yêu cầu resolveClass
       └─ KHÔNG có nghĩa sẽ initialize class

loadClass(name, true) (protected)
  └─ tìm/trả Class<?> rồi yêu cầu resolveClass(Class<?>)
       └─ link class theo JVM
       └─ KHÔNG có nghĩa toàn bộ constant pool eager resolution
       └─ KHÔNG có nghĩa sẽ initialize class

Class.forName(name, true, loader)
  └─ tìm/load/link và yêu cầu initialize class
       └─ có thể chạy mã static và gây side effects
~~~

Hãy nhớ ba trục độc lập: **tìm Class**, **link Class**, **initialize Class**. Tham số `resolve` của `ClassLoader.loadClass` liên quan đến bước **link**, không điều khiển việc thực thi `static {}`. Để biết một Class thực sự do loader nào định nghĩa, xem `Class.getClassLoader()`; để biết static initializer đã chạy hay chưa, quan sát đúng trigger initialization thay vì suy đoán từ tham số resolve.

### Tài liệu chuẩn

- Java SE 21 **ClassLoader API**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 21 **Class.forName API**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)
- **JVM Specification §5.4 – Linking**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4
- **JVM Specification §5.5 – Initialization**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.5
- **Java Language Specification §12.2–12.4**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html
