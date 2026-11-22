# Không định nghĩa lại cùng một tên trong cùng ClassLoader

## 1. Quy tắc phải nhớ

Trong Java, một **ClassLoader cụ thể không được tạo lại một định nghĩa class mới với cùng binary name** sau khi loader đó đã là *initiating loader* của class có tên ấy. Nếu cố gọi `defineClass` một lần nữa cho cùng tên trong cùng loader, JVM từ chối, thường bằng **`LinkageError`** (thông báo điển hình chứa `attempted duplicate class definition`).

Đây không phải do file `.class` đã biến mất và cũng không phải do bytecode mới có nội dung giống bytecode cũ. Đó là quy tắc về **định danh kiểu ở runtime** của JVM.

~~~text
ClassLoader L1
  ├── defineClass("demo.plugin.Entry", bytes-v1) -> Class Entry#1
  └── defineClass("demo.plugin.Entry", bytes-v2) -> LinkageError
      (kể cả bytes-v2 giống hệt bytes-v1)

ClassLoader L2 (đối tượng loader mới)
  └── defineClass("demo.plugin.Entry", bytes-v2) -> Class Entry#2

Entry#1 != Entry#2 vì defining loaders khác nhau.
~~~

**Hai nguyên tắc tưởng đối lập nhưng đều đúng:**

1. **Cùng binary name + cùng defining loader** là cùng một danh tính runtime class; không thể tạo hai định nghĩa khác nhau bằng cách gọi `defineClass` lặp lại.
2. **Cùng binary name + hai defining loaders khác nhau** có thể đại diện **hai runtime types khác nhau**. Những class ấy có thể không ép kiểu qua lại và có thể bị ràng buộc thêm bởi **loading constraints** khi chúng tương tác qua API.

Bài này thuộc chủ đề **Loader tùy chỉnh**. Trọng tâm là hiểu vì sao `loadClass` nên trả về class đã được nạp, vì sao gọi `defineClass` trực tiếp lần thứ hai sai, và cách tổ chức loader cho cơ chế plugin/reload.

### Kết quả học tập

Sau bài, bạn có thể:

- Phân biệt **binary name**, **defining loader**, **initiating loader** và **`Class<?>` object**.
- Giải thích nhiệm vụ của `findLoadedClass` trong thuật toán `loadClass` mặc định.
- Dự đoán khi nào có cùng `Class<?>`, khi nào phát sinh `LinkageError`.
- Tự chạy ví dụ Java 17+ tạo một custom loader, gọi `loadClass` hai lần, thử `defineClass` lại và so sánh với một loader mới.
- Hiểu rủi ro nếu override `loadClass` sai, nhất là với thread concurrency.
- Phân biệt **nạp lại bằng loader khác** với **class redefinition/retransformation** thông qua instrumentation.

## 2. Định danh runtime type: tên không đứng một mình

### 2.1. Class name là một phần của định danh

Một class file chứa tên nhị phân như:

~~~text
demo.plugin.Entry
~~~

Khi JVM tạo class từ định nghĩa do một loader cung cấp, **defining loader** của class là thành phần làm nên runtime identity. Có thể mô tả:

~~~text
RuntimeClassIdentity = (binaryName, definingClassLoader)
~~~

Hai class cùng tên nhưng loader khác nhau có thể là hai loại khác nhau:

~~~java
Class<?> a = loaderA.loadClass("demo.plugin.Entry");
Class<?> b = loaderB.loadClass("demo.plugin.Entry");

System.out.println(a.getName().equals(b.getName())); // có thể true
System.out.println(a == b);                           // có thể false
~~~

Đây là **snippet minh họa**, cần hai loader được cấu hình tìm được class đúng nguồn. `a == b` mới trực tiếp kiểm tra class identity, còn `getName()` chỉ kiểm tra chuỗi binary name.

### 2.2. Hai vai trò loader khác nhau

- **Defining loader:** loader đã thực sự định nghĩa một class, thể hiện qua `Class.getClassLoader()` (với bootstrap-defined classes, API có thể trả `null`).
- **Initiating loader:** loader đã yêu cầu JVM load một class theo tên và được JVM ghi nhận là khởi xướng việc tìm lớp đó; loader có thể nhận class do parent định nghĩa theo delegation.

Ví dụ:

~~~text
L_child.loadClass("java.lang.String")
    -> ủy quyền lên bootstrap
    -> trả về java.lang.String.class

Defining loader của String: bootstrap
L_child: có thể được JVM ghi nhận là initiating loader cho tên đó.
~~~

Điểm tinh tế này giải thích vì sao quy tắc trong [JVMS §5.3.5](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3.5) **không chỉ là** “nếu loader đã từng gọi trực tiếp `defineClass` thì cấm lần thứ hai”. JVM kiểm tra trạng thái loading theo **initiating loader và binary name**. Nếu loader đã khởi xướng và được ghi nhận một class cùng tên qua parent, cố tự định nghĩa lại tên ấy trong cùng loader cũng là một hướng vi phạm.

### 2.3. Từ khóa “cùng loader” nghĩa là cùng đối tượng

Hai instance khác nhau của **cùng một subclass ClassLoader** không phải là một loader:

~~~java
ByteLoader loaderOne = new ByteLoader(path);
ByteLoader loaderTwo = new ByteLoader(path);
~~~

Dù cả hai dùng cùng đường `path` và cùng bytes, `loaderOne != loaderTwo`. Nếu mỗi loader tự định nghĩa `demo.plugin.Entry`, JVM có thể tạo hai `Class<?>` riêng. Đừng dùng tên class của loader (`getClass().getName()`), hash string hay `toString()` để thay thế so sánh identity `==`.

## 3. `loadClass` và `defineClass` không có cùng nhiệm vụ

### 3.1. `loadClass(String)` là cổng tìm class theo tên

Theo [Java SE 21 `ClassLoader` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html), triển khai mặc định của `loadClass(name, resolve)` làm việc theo thứ tự cơ bản:

1. Gọi **`findLoadedClass(name)`** để xem loader đã được JVM ghi nhận là initiating loader cho class cùng tên chưa. Nếu đã có, **trả lại class đó**.
2. Nếu chưa có, thử **parent delegation** (hoặc bootstrap loader khi parent là `null`).
3. Nếu parent không tìm ra, gọi **`findClass(name)`** của loader.
4. Nếu yêu cầu `resolve == true`, gọi `resolveClass` với kết quả theo hợp đồng.

Giả mã để hình dung (không phải mã nguồn nguyên văn của JDK):

~~~java
protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException {
    synchronized (getClassLoadingLock(name)) {
        Class<?> result = findLoadedClass(name);

        if (result == null) {
            try {
                result = (getParent() == null)
                        ? findBootstrapClassSomehow(name)
                        : getParent().loadClass(name);
            } catch (ClassNotFoundException notFound) {
                result = findClass(name);
            }
        }

        if (resolve) {
            resolveClass(result);
        }
        return result;
    }
}
~~~

**Lưu ý:** `findBootstrapClassSomehow` là **tên giả để mô tả bước ủy quyền**, không phải method Java có sẵn. Đoạn mã này chỉ nhằm giải thích thuật toán; bạn **không được copy để biên dịch**. Trong thực hành hãy giữ triển khai `loadClass` chuẩn rồi override `findClass`.

Đặc biệt, **`findLoadedClass` có thể trả class do parent định nghĩa** nếu loader hiện tại là *initiating loader* của class đó. Tên phương thức dễ gây hiểu nhầm rằng chỉ trả những class đã được loader này trực tiếp `defineClass`.

### 3.2. `defineClass` tạo định nghĩa mới từ bytes

Họ phương thức protected như:

~~~java
protected final Class<?> defineClass(
        String name, byte[] bytes, int offset, int length)
~~~

nhận một biểu diễn class file hợp lệ để JVM tạo class. `defineClass` **không được thiết kế thành API idempotent kiểu “nếu có rồi thì trả class cũ”**.

Khác biệt:

| Hoạt động | Ý định | Khi class cùng tên đã được loader khởi xướng |
|---|---|---|
| `loader.loadClass(name)` theo triển khai mặc định | Tìm class theo tên, tái sử dụng kết quả nếu đã nạp | Thường trả lại cùng `Class<?>` |
| `findLoadedClass(name)` trong subclass | Kiểm tra trạng thái JVM đã ghi nhận đối với initiating loader | Trả class tương ứng hoặc `null` |
| `defineClass(name, bytes, ...)` | **Định nghĩa** class mới từ bytecode | Cố định nghĩa trùng → **`LinkageError`** |
| `findClass(name)` do bạn override | Tìm bytecode nguồn riêng rồi thường gọi `defineClass` khi cần | Nên chỉ được gọi trong đường có kiểm tra/cache phù hợp |
| `new AnotherLoader(...).loadClass(name)` | Loader **khác** có thể định nghĩa type mới cùng binary name | Có thể có `Class<?>` khác (theo nguồn, delegation và constraints) |

**Điểm cốt lõi:** nếu mục đích là lấy class đã tồn tại, gọi `loadClass`; **không gọi lại `defineClass` để “refresh” class cũ**.

## 4. Điều gì thực sự gây `LinkageError`?

### 4.1. Quy tắc của JVM

Theo JVMS `5.3.5, khi derive một class từ class-file representation cho tên `N` theo loader `L`, JVM kiểm tra xem `L` đã là initiating loader của một class/interface tên `N` hay chưa. Nếu đã ghi nhận, phép derive mới là **không hợp lệ** và ném **`LinkageError`**.

Ví dụ:

~~~text
L = ByteLoader@1
N = demo.plugin.Entry

L.loadClass(N)        -> Class<?> C1
L.loadClass(N)        -> chính C1
L.defineClass(N, ...) -> LinkageError
~~~

Thông báo cụ thể của `LinkageError` phụ thuộc JVM; bài chỉ dựa vào **loại lỗi và quy tắc**, không phụ thuộc vào nguyên văn message có thể khác theo runtime/vendor.

### 4.2. Nếu bytes mới y hệt thì sao?

Vẫn **không** được định nghĩa lại cùng tên trong cùng initiating loader. Quy tắc dựa trên runtime loading identity, **không phải so hash của file**.

- Bytes giống hệt → không trở thành “định nghĩa trùng nhưng hợp lệ”.
- Bytes đã đổi → không được tự động thay definition cũ.
- Đổi một file `.class` hoặc thay nội dung JAR trên disk → một `Class<?>` đã load trong JVM không bị viết đè.
- Gọi `ClassLoader.loadClass(name)` lần nữa sau khi thay file → mặc định thường vẫn nhận `Class<?>` cũ vì cache theo initiating loader.

Điều này giải thích tại sao cơ chế hot reload không thể đơn giản là “ghi đè JAR rồi gọi `loadClass`”.

### 4.3. Khác `ClassNotFoundException`

Nếu tìm bytecode theo tên nhưng **không có file**, một custom `findClass` hợp lý sẽ ném `ClassNotFoundException`.

Nếu có bytes nhưng **cố định nghĩa trùng**, lỗi là **`LinkageError`**; JVM không nói rằng class không tồn tại, mà ngược lại **một class tương ứng đã được ghi nhận**.

Các lỗi khác có thể xảy ra khi define class: `ClassFormatError` (class file không hợp lệ), `UnsupportedClassVersionError` (classfile version không được JVM hỗ trợ), `NoClassDefFoundError` nếu tên truyền không tương thích với tên mà bytes khai báo, `SecurityException` trong những trường hợp package/security constraints. Không nên gom tất cả vào “duplicate class definition”.

## 5. Thực hành Java 17+: lặp `loadClass`, cố `defineClass` lại và dùng loader mới

Chương trình sau chỉ cần Java 17 trở lên, không cần Gradle/Maven, không tải network. Nó tạo:

- **Một class `demo.plugin.Entry`** được biên dịch thành file `.class` trong thư mục plugin, tách khỏi app classpath.
- **Một `ByteLoader`** custom subclass chỉ override `findClass` để đọc class bytes và gọi `defineClass`.
- **Một method `forceDefineAgain`** chỉ dùng trong phòng thí nghiệm để thử cố ý định nghĩa trùng và quan sát `LinkageError`.
- **Hai instance loader độc lập** để đối chiếu identity.

### 5.1. Cây thư mục

~~~text
demo/
  src/
    plugin/
      demo/
        plugin/
          Entry.java
    app/
      DuplicateDemo.java
  build/
    plugin/                 # output riêng của Entry
    app/                    # output riêng của DuplicateDemo
~~~

**Quan trọng:** khi chạy, chỉ để `build/app` trong `-cp`. Nếu thêm `build/plugin` vào system classpath, parent-first delegation có thể tìm `Entry` trước; như vậy thí nghiệm custom `ByteLoader` không còn đo đúng việc nó tự định nghĩa class.

### 5.2. Tệp `src/plugin/demo/plugin/Entry.java`

~~~java
package demo.plugin;

public class Entry {
    public String id() {
        return "entry";
    }
}
~~~

`Entry` là một class bình thường. Không có logic static đặc biệt vì chủ đề bài là **class definition** chứ không phải class initialization.

### 5.3. Tệp `src/app/DuplicateDemo.java`

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class DuplicateDemo {
    static final String NAME = "demo.plugin.Entry";

    static class ByteLoader extends ClassLoader {
        private final Path root;

        ByteLoader(Path root) {
            super(DuplicateDemo.class.getClassLoader());
            this.root = root;
        }

        private byte[] bytes(String name) throws IOException {
            return Files.readAllBytes(
                    root.resolve(name.replace('.', '/') + ".class"));
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!NAME.equals(name)) {
                throw new ClassNotFoundException(name);
            }
            try {
                byte[] data = bytes(name);
                return defineClass(name, data, 0, data.length);
            } catch (IOException ex) {
                throw new ClassNotFoundException(name, ex);
            }
        }

        Class<?> forceDefineAgain(String name) throws IOException {
            byte[] data = bytes(name);
            return defineClass(name, data, 0, data.length);
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Path.of("build/plugin");
        ByteLoader firstLoader = new ByteLoader(root);

        Class<?> first = firstLoader.loadClass(NAME);
        Class<?> again = firstLoader.loadClass(NAME);
        System.out.println("repeatSameClass=" + (first == again));
        System.out.println("firstLoaderOwnsClass="
                + (first.getClassLoader() == firstLoader));

        try {
            firstLoader.forceDefineAgain(NAME);
            System.out.println("duplicateDefinition=UNEXPECTED");
        } catch (LinkageError expected) {
            System.out.println("duplicateDefinition="
                    + expected.getClass().getSimpleName());
        }

        ByteLoader secondLoader = new ByteLoader(root);
        Class<?> other = secondLoader.loadClass(NAME);
        System.out.println("sameBinaryName="
                + first.getName().equals(other.getName()));
        System.out.println("differentClassObjects=" + (first != other));
        System.out.println("secondLoaderOwnsClass="
                + (other.getClassLoader() == secondLoader));
    }
}
~~~

**Giới hạn của ví dụ:** `forceDefineAgain` **cố ý vi phạm điều kiện JVM** để minh họa lỗi. Không sao chép method đó vào production loader với mục tiêu “cập nhật class”. Trong loader thật, `findClass` thường phụ trách tra bytecode, còn `loadClass` thực hiện cached/delegation lookup.

### 5.4. Biên dịch/chạy

Đứng ở thư mục `demo` trên Linux/macOS:

~~~sh
mkdir -p build/plugin build/app
javac --release 17 -d build/plugin src/plugin/demo/plugin/Entry.java
javac --release 17 -d build/app src/app/DuplicateDemo.java
java -cp build/app DuplicateDemo
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/plugin, build/app | Out-Null
javac --release 17 -d build/plugin src/plugin/demo/plugin/Entry.java
javac --release 17 -d build/app src/app/DuplicateDemo.java
java -cp build/app DuplicateDemo
~~~

**Stdout chính xác**, đã biên dịch với `javac --release 17` và kiểm chứng bằng Java:

~~~text
repeatSameClass=true
firstLoaderOwnsClass=true
duplicateDefinition=LinkageError
sameBinaryName=true
differentClassObjects=true
secondLoaderOwnsClass=true
~~~

### 5.5. Giải thích từng dòng

| Output | Ý nghĩa |
|---|---|
| `repeatSameClass=true` | Hai lần `firstLoader.loadClass(NAME)` trả **cùng object `Class<?>`**, không tạo definition mới |
| `firstLoaderOwnsClass=true` | `Entry` lần đầu do instance `firstLoader` thực sự định nghĩa |
| `duplicateDefinition=LinkageError` | `forceDefineAgain` cố gọi `defineClass` lần hai trên **chính loader cũ**, JVM từ chối |
| `sameBinaryName=true` | Hai runtime class đều mang tên `demo.plugin.Entry` |
| `differentClassObjects=true` | Hai instance loader khác nhau có thể tạo hai runtime classes khác identity |
| `secondLoaderOwnsClass=true` | Class thứ hai thực sự do `secondLoader` định nghĩa, không chỉ được parent trả về |

**Điều cần học, không phải chỉ nhớ output:** loader cache làm `loadClass` có tính ổn định; `defineClass` không phải phép thay đổi class; muốn một definition mới cùng tên, phải có điều kiện cho loader **khác** định nghĩa, hoặc dùng cơ chế instrumentation đặc biệt theo hợp đồng riêng.

### 5.6. Tự thử các biến thể

**Thử A — Gọi `loadClass` lần thứ ba:** sau khi bắt `LinkageError`, gọi lại `firstLoader.loadClass(NAME)` và so với `first`. Kết quả vẫn là cùng `Class<?>`, vì phép thử định nghĩa trùng thất bại không tạo được định nghĩa mới.

**Thử B — Thay bytes sau khi đã load:** nếu bạn đổi `Entry.id()` trong `Entry.java` rồi biên dịch lại trong một tiến trình chạy khác, class được loader cũ trong JVM đang chạy **không được cập nhật tự động**. Với JVM mới và loader mới, class mới có thể được định nghĩa từ bytes mới. Để thử trong cùng JVM phải tổ chức bước cập nhật file và loader sao cho có thể quan sát được thời điểm đọc bytes; đừng gán cho class đã load một hành vi tự làm mới.

**Thử C — Gọi `findClass` trực tiếp liên tục:** `findClass` thường đọc bytes rồi gọi `defineClass`; nếu tự cho phép code bên ngoài gọi đi gọi lại, bạn có thể lại gặp duplicate definition. Thiết kế tốt là cung cấp API `loadClass` có kiểm tra `findLoadedClass`/delegation của JDK, không expose `findClass` như “reloader”.

**Thử D — Đưa `build/plugin` vào application classpath:** parent có thể định nghĩa `Entry`, làm `firstLoader.loadClass(NAME)` trả class parent thay vì tạo class bằng `ByteLoader.findClass`. `firstLoader.getClass().getName()` vẫn như cũ, nhưng `first.getClassLoader()` đổi. Khi đã có initiated record với tên đó, cố tự define class trùng trong child vẫn không phải cơ chế hợp lệ.

## 6. Đồng thời (concurrency): vì sao phải khóa quá trình load?

Một custom loader có thể bị nhiều threads gọi `loadClass("demo.plugin.Entry")` cùng lúc. Nếu cả hai cùng thấy “chưa được load” rồi cùng định nghĩa, một thread có thể thành công còn thread kia chạm `LinkageError`. Đây là rủi ro nếu override `loadClass` một cách bất cẩn, không giữ cơ chế đồng bộ đúng.

### 6.1. Thiết kế khuyến nghị

**Ưu tiên override `findClass`, không override `loadClass`** nếu không có nhu cầu đặc biệt. Phương thức `loadClass(String, boolean)` mặc định có cơ chế đồng bộ theo **`getClassLoadingLock(name)`**, đồng thời kiểm tra `findLoadedClass` trước khi ủy quyền/tìm bytes.

~~~text
Thread T1: loadClass(N)
  -> lock dành cho N
  -> findLoadedClass(N) == null
  -> parent delegation thất bại
  -> findClass(N) -> defineClass(N) thành công
  -> release lock

Thread T2: loadClass(N)
  -> lock dành cho N
  -> findLoadedClass(N) trả C1
  -> return C1; KHÔNG define lại
~~~

Sơ đồ mô tả đường load có kết quả do loader này định nghĩa; khi parent có class, bước `findClass` có thể không được gọi.

### 6.2. Parallel-capable ClassLoader

Nếu subclass được đăng ký parallel-capable bằng `ClassLoader.registerAsParallelCapable()` theo đúng quy tắc (các superclasses liên quan cũng phải đáp ứng điều kiện), `getClassLoadingLock(name)` có thể dùng **khóa riêng theo tên class** để nhiều tên class được xử lý đồng thời.

Điều này **không cho phép cùng loader định nghĩa hai class trùng binary name**. Nó chỉ thay chiến lược đồng bộ và throughput. Nếu override `loadClass`, cần kiểm tra cache, delegation, locking và loading constraints; nếu làm sai, `LinkageError` có thể chỉ xuất hiện trong tình huống nhiều threads.

Không nên bỏ qua khóa rồi cố catch `LinkageError` như cách sửa race. Đó là che dấu nguyên nhân, dễ khiến các threads có kết quả class resolution không ổn định.

## 7. Kế thừa, delegation và “định nghĩa trùng”

### 7.1. Parent đã định nghĩa class: child thường không tự định nghĩa lại

Trong mô hình parent-first thông thường:

~~~text
Parent loader P:
  defines demo.api.Service

Child loader C:
  C.loadClass("demo.api.Service")
     -> P.loadClass(...), trả Service của P
     -> C không gọi findClass/defineClass cho tên này
~~~

Đây là cách phổ biến để chia sẻ **cùng API type** giữa host và plugin. Nếu sau đó child cố gọi `defineClass("demo.api.Service", bytes)` để tạo class cùng tên trong chính child đã initiated load đó, nó có thể vi phạm quy tắc JVMS `5.3.5.

### 7.2. Child-first có thể hợp lệ với tên chưa khởi xướng

Một số containers dùng child-first cho namespace được cô lập. Nếu `C` **chưa** là initiating loader của `com.plugin.Widget`, và parent chưa được C dùng để ghi nhận class này, C có thể tự define class tên ấy theo chính sách child-first. Nhưng:

- Cần hiểu rõ các protected packages và package sealing/certificates khi define class.
- Một class tên giống class parent ở **hai defining loaders** là hai runtime types khác nhau.
- Type identity khác nhau có thể gây `ClassCastException` và loading-constraint `LinkageError` khi signature xuyên qua loader boundaries.
- Các lớp platform lõi như `java.lang.*` không được tùy tiện định nghĩa bởi custom loader.

Vì vậy, **“định nghĩa cùng binary name ở hai loaders khác nhau có thể được” không đồng nghĩa “mọi trường hợp shadow class đều an toàn”**.

### 7.3. Loading constraints giữa loaders

JVM đặt các **loading constraints** khi liên kết tham chiếu qua các type signature, bảo đảm một tên kiểu dùng ở những vị trí nhất định phải biểu diễn cùng runtime class khi có tương tác tương ứng. Nếu hai loaders đã định nghĩa hai classes khác nhau cho tên cần thống nhất, JVM có thể ném `LinkageError`.

Đừng trộn hai tình huống:

1. **Duplicate definition trong cùng initiating loader:** JVM từ chối cố derive/define tên trùng theo `5.3.5`.
2. **Loading constraint violation giữa các loaders:** mỗi loader có thể đã có class riêng, nhưng việc liên kết giữa chúng đòi cùng identity và phát hiện mâu thuẫn theo `5.3.4`.

Cả hai liên quan `LinkageError`, nhưng **điểm sửa khác nhau**. Tình huống đầu thường sửa bằng cache/delegation đúng; tình huống hai phải thiết kế classpath, shared API và ranh giới loaders.

## 8. Nếu cần hot reload/hot deploy thì làm thế nào?

### 8.1. Cách phổ biến: tạo ClassLoader mới

Một hệ plugin có thể dùng:

~~~text
Version 1:
  PluginLoader_v1 -> defines plugin.Feature
  application giữ Feature_v1 và instance_v1

Version 2:
  tạo PluginLoader_v2 (instance loader mới)
  PluginLoader_v2 -> defines plugin.Feature từ bytes phiên bản 2
  application đổi tham chiếu hoạt động sang instance_v2
  giải phóng tham chiếu cũ khi an toàn
~~~

Lúc này `plugin.Feature` từ loader v1 và từ loader v2 là **hai runtime types** khác nhau. Framework thường cần một interface API chung do parent loader định nghĩa để trao đổi:

~~~java
// Mã minh họa: interface API được host và plugin nhìn qua loader chung
package demo.api;

public interface FeatureService {
    String run();
}
~~~

Plugin implementations ở những loader khác nhau đều có thể triển khai `FeatureService` nếu cùng dùng đúng interface runtime của parent. Host nên giữ object theo **type API chung** thay vì ép kiểu giữa implementation class của hai loader versions.

Đây là cách đổi **định nghĩa class thông qua loader isolation**, không phải `defineClass` đè lên một `Class<?>` đã tồn tại.

### 8.2. Điều kiện để class loader cũ có thể được thu gom

Tạo loader v2 **không tự unload v1**. Loader v1 và các class của nó có thể còn sống vì:

- Instance cũ được singleton/static cache giữ.
- `Thread Context ClassLoader` của một worker thread còn trỏ tới v1.
- Thread do plugin tạo vẫn đang chạy.
- `ServiceLoader`/reflection/proxy/callback caches còn tham chiếu class v1.
- Resource/JAR file handles chưa được đóng.

Muốn retire plugin đúng cách cần dừng hoặc chuyển tác vụ, xóa tham chiếu/caches, khôi phục TCCL, đóng URLClassLoader nếu thích hợp và để GC làm việc theo điều kiện JVM. **Không có lời hứa rằng class unload ngay khi `close()` được gọi**.

### 8.3. Instrumentation là một cơ chế khác

Java có `java.lang.instrument.Instrumentation.redefineClasses(...)` và `retransformClasses(...)` khi JVM hỗ trợ và agent có capability cần thiết. Những API này có thể **thay đổi định nghĩa của class đã nạp theo giới hạn JVM**, nhưng:

- **Không tạo một `Class<?>` mới bằng `defineClass` lần hai trong cùng loader**.
- Phụ thuộc công cụ/JVM/agent và thường có giới hạn về thay đổi cấu trúc class/schema.
- Cần thiết kế, kiểm thử compatibility và vòng đời instrumentation riêng.

Do đó, **Java agent hot swap** và **plugin reload bằng ClassLoader mới** là hai hướng khác nhau; không dùng một lệnh `defineClass` lặp lại để thay thế cả hai.

## 9. Bảng lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Khả năng nguyên nhân | Cách kiểm tra |
|---|---|---|
| `LinkageError: attempted duplicate class definition` | Cùng loader đang bị gọi `defineClass` lại cho tên đã initiated | Trace code override `loadClass`/`findClass` và số lần `defineClass` |
| Thay file `.class` xong gọi `loadClass` vẫn thấy hành vi cũ | Loader đã có class, trả lại `Class<?>` cũ | So `first == second`, source bytes, lifecycle loader |
| Hai class cùng tên nhưng ép kiểu lỗi | Defining loaders khác nhau | So `a.getClassLoader() == b.getClassLoader()` và `a == b` |
| `LinkageError: loader constraint violation` | Hai loaders không thống nhất identity của type trong signature dùng chung | Xem call signatures, shared API, loader hierarchy |
| `ClassNotFoundException` | Loader không tìm được bytes/class theo tên | Kiểm tra binary name, đường JAR/directory và delegation |
| `NoClassDefFoundError` | JVM không có class cần thiết ở runtime hoặc class từng lỗi initialization | Xem `Caused by`, classpath/JAR, lỗi ban đầu |
| `ClassFormatError` | Bytes đầu vào không hợp lệ theo classfile format | Kiểm tra bytes đọc được và compiler/JDK |
| `UnsupportedClassVersionError` | Class file version vượt JVM đang chạy | So `javac --release` và `java -version` |
| `SecurityException` khi define class ở package hạn chế | Package/signer/security condition bị vi phạm | Không tự define `java.*`, kiểm tra protection domain |
| Chỉ lỗi khi chạy đồng thời | Override `loadClass` sai cache/lock dẫn đến hai luồng cùng define | Giữ `getClassLoadingLock`/`findLoadedClass` hoặc dùng loadClass mặc định |

### Checklist trước khi sửa custom ClassLoader

1. Có đúng **binary name** của class chưa?
2. Một class đã được loader này initiated/load chưa? Trong subclass, `findLoadedClass(name)` là công cụ kiểm tra hữu ích.
3. Code có đang **gọi `defineClass` trực tiếp mỗi lần** thay vì đi qua `loadClass` không?
4. Parent delegation có định nghĩa class cùng tên trước không?
5. Loader có được dùng từ nhiều threads? Locking/cache có đúng?
6. Loader và class có phải của đúng plugin/version không?
7. Có vô tình đưa plugin classes vào parent/system classpath không?
8. Có đang nhầm `ClassNotFoundException` với `LinkageError`?
9. Nếu mục tiêu là reload, nên tạo loader mới và hợp đồng API chung thay vì redefine trùng?
10. Có chỗ giữ reference tới loader cũ làm class unloading chậm không?

## 10. Những nhận định dễ sai

1. **“`defineClass` lần hai sẽ cập nhật implementation cũ.”** Sai; JVM không coi đó là update.
2. **“Bytes giống nhau thì định nghĩa trùng được.”** Sai; JVM xét trạng thái class theo name/loader.
3. **“`loadClass` lần hai cũng gọi `defineClass` lần hai.”** Sai đối với thuật toán mặc định khi class đã có.
4. **“`findLoadedClass` chỉ thấy những class do loader này tự định nghĩa.”** Chưa đủ; method dựa trên trạng thái *initiating loader* được JVM ghi nhận.
5. **“Nếu tạo hai đối tượng loader cùng subclass, chúng phải dùng chung `Class<?>`.”** Sai nếu mỗi loader tự định nghĩa class; phải xét delegation.
6. **“Cùng binary name là cùng Java type.”** Sai khi defining loader khác nhau.
7. **“Đổi JAR trên disk là JVM tự load lại class cùng tên.”** Sai với class đã định nghĩa.
8. **“Catch `LinkageError` rồi gọi `defineClass` lại sẽ sửa được.”** Sai; lặp lại thao tác vi phạm không giải quyết identity.
9. **“Child-first luôn giải quyết được mọi trùng class.”** Sai; có thể sinh loading constraint violations hoặc khác API type.
10. **“Có loader mới thì plugin cũ tự unload ngay.”** Sai khi object/thread/cache vẫn giữ loader cũ.
11. **“Java instrumentation đơn giản chỉ gọi `defineClass` lần hai.”** Sai; đó là cơ chế cập nhật theo hợp đồng khác.
12. **“Một class loader có thể làm mới mọi method bằng cách gọi `loadClass` lại.”** Sai; phải phân biệt class lookup với thay đổi definition.

## 11. Câu hỏi tự kiểm tra

1. Hai yếu tố nào định danh một runtime class thông thường của JVM?
2. `findLoadedClass(name)` có chức năng gì trong thuật toán `loadClass` mặc định?
3. Vì sao gọi `firstLoader.loadClass(NAME)` hai lần trong demo trả cùng `Class<?>`?
4. Vì sao `forceDefineAgain(NAME)` ném `LinkageError` dù bytes không đổi?
5. Phân biệt **defining** và **initiating** ClassLoader; khi child được parent trả class, ai định nghĩa class đó?
6. Khi nào hai loaders khác nhau có thể tạo hai `Class<?>` cùng binary name?
7. Vì sao `first.getName().equals(other.getName())` có thể là `true` nhưng `first == other` là `false`?
8. Tại sao không đưa `build/plugin` lên system classpath khi muốn chứng minh `ByteLoader` tự định nghĩa `Entry`?
9. Nếu custom loader dùng hai threads cùng tải `Entry`, cần giữ cơ chế nào để không define trùng?
10. `registerAsParallelCapable` có cho phép định nghĩa hai class cùng binary name trong cùng loader không?
11. Loader constraint violation khác duplicate definition trong cùng loader như thế nào?
12. Đổi file `Entry.class` trên disk rồi gọi `loadClass` lại có bảo đảm code mới được dùng không?
13. Khi muốn cập nhật plugin mà vẫn cùng tên class, vì sao tạo loader instance mới là một lựa chọn phổ biến?
14. Nếu host và plugin v1/v2 trao đổi object, vì sao một interface chung do parent định nghĩa có giá trị?
15. `URLClassLoader.close()` có bảo đảm class cũ bị unload ngay không?
16. Instrumentation `redefineClasses` khác phép gọi lại `defineClass` ở điểm căn bản nào?
17. Nếu một loader đã initiated class cùng tên nhờ parent delegation, vì sao cố define lại class đó trong cùng loader là một sai lầm?
18. Khi gặp `LinkageError`, những thông tin nào trong log nên ghi để phân biệt định nghĩa trùng với loading-constraint violation?

**Tiêu chí hoàn thành:** bạn tự chạy đúng demo, giải thích đủ sáu dòng stdout, phân biệt `loadClass` và `defineClass`, nêu được điều kiện làm nên class identity, hiểu nguyên nhân `LinkageError` và chọn được cách reload an toàn qua loader mới hoặc cơ chế instrumentation riêng khi phù hợp.

## 12. Tài liệu đặc tả và API chính thức

- [JVMS Java SE 21 §5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): class identity, defining/initiating loaders và quy trình tạo class.
- [JVMS Java SE 21 §5.3.5 — Deriving a Class from a Class File Representation](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3.5): điều kiện JVM từ chối derive class trùng tên đã initiated và các lỗi liên quan.
- [JVMS Java SE 21 §5.3.4 — Loading Constraints](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3.4): vì sao có ràng buộc type identity giữa các loaders khi liên kết.
- [Java SE 21 `ClassLoader` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findLoadedClass`, `findClass`, `defineClass`, `getClassLoadingLock` và parallel capable.
- [Java SE 21 `Instrumentation` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `redefineClasses`/`retransformClasses`, cách cập nhật class có giới hạn riêng.

Bài áp dụng cho Java 17+; chương trình minh họa đã biên dịch bằng `javac --release 17` và chạy độc lập, không cần build tool hoặc framework. Hãy dựa vào **Class object identity** và defining loader thực tế khi chẩn đoán, không chỉ dựa vào chuỗi tên class.