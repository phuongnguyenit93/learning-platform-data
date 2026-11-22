# Tên lớp giống nhau nhưng khác defining loader trong Java

Hai lớp Java có thể cùng tên, thậm chí được nạp từ **cùng một file `.class` có bytecode giống hệt**, nhưng JVM vẫn coi chúng là **hai kiểu khác nhau** nếu chúng được **định nghĩa bởi hai class loader khác nhau**. Đây là điểm quan trọng khi dùng Reflection để nhận diện kiểu: chỉ so sánh `Class.getName()` hoặc tên hiển thị là chưa đủ.

Bài học thuộc chủ đề **Tên và định danh kiểu**. Ta sẽ phân biệt **tên lớp (binary name)**, **defining class loader**, **initiating class loader** và **định danh runtime của `Class<?>`**; sau đó quan sát hệ quả đối với ép kiểu, gọi phương thức và thiết kế plugin.

## 1. Một tên lớp không bảo đảm chỉ có một kiểu runtime

Trong mã Java bình thường, bạn thường nghĩ `com.example.Plugin` là một kiểu duy nhất. Suy nghĩ này có vẻ đúng vì phần lớn ứng dụng dùng mô hình **ủy quyền về parent class loader**, khiến một bản định nghĩa được dùng chung.

Nhưng JVM cho phép nhiều class loader tạo ra các định nghĩa lớp riêng. Với lớp tham chiếu thông thường, danh tính runtime có thể hiểu qua cặp:

**(binary name, defining class loader)**

Ví dụ hai loader khác nhau cùng định nghĩa lớp có binary name `com.example.Plugin`:

```text
PluginLoader A                            PluginLoader B
      |                                         |
      | defineClass("com.example.Plugin", ...)  | defineClass("com.example.Plugin", ...)
      v                                         v
Class<?> A                                 Class<?> B

A.getName() == "com.example.Plugin"        B.getName() == "com.example.Plugin"

A.getName().equals(B.getName())  == true
A == B                            == false
A.isAssignableFrom(B)             == false
```

Các nhận định quan trọng:

- **Tên bằng nhau**: `Class.getName()` của hai lớp có thể trả về đúng cùng một chuỗi.
- **`Class` khác nhau**: `A == B` là `false`; chúng đại diện hai định nghĩa kiểu.
- **Không tương thích kiểu chỉ vì tên trùng**: đối tượng của `A` không tự trở thành đối tượng của `B`.
- **Bytecode không quyết định đồng nhất kiểu**: ngay cả cùng nội dung `.class`, một loader mới định nghĩa bản riêng thì danh tính kiểu vẫn khác.
- **Cùng loader định nghĩa + cùng binary name**: trong phạm vi một loader, định nghĩa lớp thành công chỉ có một lần cho mỗi binary name; cố định nghĩa trùng thường gây `LinkageError`.

Quy tắc này liên quan đến **lớp tham chiếu do class loader định nghĩa**. Kiểu nguyên thủy do JVM xác lập và không được nạp bằng `defineClass` như lớp thông thường.

## 2. Phân biệt defining loader và initiating loader

**Defining loader** là class loader trực tiếp **định nghĩa** lớp, điển hình qua `defineClass(...)` hoặc cơ chế định nghĩa tương ứng. `Class.getClassLoader()` trả về loader đã định nghĩa lớp (có thể là `null` với lớp do bootstrap loader định nghĩa).

**Initiating loader** là loader mà JVM đã dùng để **bắt đầu một yêu cầu tải lớp** và qua đó ghi nhận quan hệ initiating. Loader này có thể ủy quyền sang parent, nên **không nhất thiết** là loader thực sự định nghĩa class.

### Trường hợp A: hai child loader ủy quyền cho cùng parent

```text
ChildLoader 1 ----\
                   \ delegate
                    -> ParentLoader -> define "com.example.Plugin"
                   /                       |
ChildLoader 2 ----/                        v
                                        Cùng Class<?>
```

Dù có hai child loader object, cả hai đều nhận lại **cùng một `Class<?>`** do parent định nghĩa. Không thể kết luận có hai kiểu khác nhau chỉ vì có hai loader ở điểm bắt đầu lời gọi.

### Trường hợp B: mỗi child loader tự định nghĩa lớp

```text
ChildLoader 1 -> define "com.example.Plugin" -> Class A
ChildLoader 2 -> define "com.example.Plugin" -> Class B
                                               
Class A != Class B
```

Kết quả là hai kiểu runtime khác nhau. Hai lớp có thể cùng tên binary, cùng API, cùng bytes; việc xác định danh tính vẫn phụ thuộc vào loader **định nghĩa thực sự**.

**Lưu ý:** `ClassLoader.loadClass(...)` theo triển khai mặc định thường kiểm tra lớp đã tải, sau đó ủy quyền lên parent và cuối cùng mới dùng `findClass(...)` nếu chưa tìm thấy. Chỉ viết subclass của `ClassLoader` hoặc tạo hai instance class loader **chưa bảo đảm** sẽ có hai `Class` khác nhau. Muốn chủ động định nghĩa một bản riêng phải triển khai chiến lược nạp phù hợp.

## 3. Ví dụ Java 17+: cùng tên, khác defining loader, ép kiểu thất bại

Ví dụ chạy được dưới đây cố ý tạo **hai class loader định nghĩa riêng `DemoPlugin`** nhưng đều ủy quyền lên parent để dùng chung `PluginApi`. Nhờ đó ta quan sát cả vấn đề danh tính và một cách giao tiếp giữa các loader.

Tạo ba file trong **cùng thư mục**.

**File 1 — `PluginApi.java`**

```java
public interface PluginApi {
    String greet();
}
```

**File 2 — `DemoPlugin.java`**

```java
public class DemoPlugin implements PluginApi {
    @Override
    public String greet() {
        return "Xin chào từ plugin";
    }
}
```

**File 3 — `LoaderIdentityDemo.java`**

```java
import java.io.IOException;
import java.io.InputStream;

public class LoaderIdentityDemo {

    // Chỉ DemoPlugin được định nghĩa riêng trong mỗi loader.
    // Các kiểu khác, gồm PluginApi, vẫn được ủy quyền về parent.
    static final class IsolatedPluginLoader extends ClassLoader {
        private static final String TARGET = "DemoPlugin";

        IsolatedPluginLoader(ClassLoader parent) {
            super(parent);
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!TARGET.equals(name)) {
                return super.loadClass(name, resolve);
            }

            synchronized (getClassLoadingLock(name)) {
                Class<?> result = findLoadedClass(name);
                if (result == null) {
                    String resource = name.replace('.', '/') + ".class";

                    try (InputStream stream =
                                 getParent().getResourceAsStream(resource)) {
                        if (stream == null) {
                            throw new ClassNotFoundException(name);
                        }
                        byte[] bytes = stream.readAllBytes();
                        result = defineClass(name, bytes, 0, bytes.length);
                    } catch (IOException e) {
                        throw new ClassNotFoundException(name, e);
                    }
                }

                if (resolve) {
                    resolveClass(result);
                }
                return result;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader parent = LoaderIdentityDemo.class.getClassLoader();

        IsolatedPluginLoader loaderA = new IsolatedPluginLoader(parent);
        IsolatedPluginLoader loaderB = new IsolatedPluginLoader(parent);

        Class<?> classA = Class.forName("DemoPlugin", true, loaderA);
        Class<?> classB = Class.forName("DemoPlugin", true, loaderB);
        Object first = classA.getDeclaredConstructor().newInstance();

        System.out.println("Cùng tên: "
                + classA.getName().equals(classB.getName()));
        System.out.println("Cùng Class: " + (classA == classB));
        System.out.println("Đúng defining loader: "
                + (classA.getClassLoader() == loaderA
                && classB.getClassLoader() == loaderB));
        System.out.println("A gán được từ B: "
                + classA.isAssignableFrom(classB));
        System.out.println("Là DemoPlugin từ parent: "
                + DemoPlugin.class.isInstance(first));

        System.out.println("Là PluginApi chung: "
                + (first instanceof PluginApi));
        PluginApi api = (PluginApi) first;
        System.out.println("Gọi qua interface: " + api.greet());

        try {
            DemoPlugin wrong = (DemoPlugin) first;
            System.out.println(wrong.greet());
        } catch (ClassCastException e) {
            System.out.println("Ép về DemoPlugin: ClassCastException");
        }

        // Hai loader bình thường cùng ủy quyền cho parent.
        ClassLoader childA = new ClassLoader(parent) {};
        ClassLoader childB = new ClassLoader(parent) {};
        System.out.println("Ủy quyền parent, cùng Class: "
                + (childA.loadClass("DemoPlugin")
                == childB.loadClass("DemoPlugin")));
    }
}
```

Biên dịch và chạy từ thư mục chứa cả ba file, dùng JDK 17 trở lên:

```bash
javac PluginApi.java DemoPlugin.java LoaderIdentityDemo.java
java LoaderIdentityDemo
```

**Stdout mong đợi** (không in tên/địa chỉ loader phụ thuộc môi trường):

```text
Cùng tên: true
Cùng Class: false
Đúng defining loader: true
A gán được từ B: false
Là DemoPlugin từ parent: false
Là PluginApi chung: true
Gọi qua interface: Xin chào từ plugin
Ép về DemoPlugin: ClassCastException
Ủy quyền parent, cùng Class: true
```

### Vì sao ví dụ đưa ra kết quả này?

1. `Class.forName("DemoPlugin", true, loaderA)` yêu cầu tải `DemoPlugin` qua `loaderA`. Với đúng tên đó, phương thức `loadClass` được override để dùng `defineClass(...)`; tương tự với `loaderB`. Vì vậy `classA` và `classB` có cùng binary name nhưng hai defining loader khác nhau.
2. `findLoadedClass(name)` tránh định nghĩa lại lớp cùng tên trong **mỗi** loader khi có nhiều lời gọi. Khóa `getClassLoadingLock(name)` giữ việc tra cứu/định nghĩa nhất quán khi có concurrency.
3. Đối với `PluginApi`, cả hai loader gọi `super.loadClass(...)` nên parent định nghĩa và cấp **cùng một kiểu interface**. Cả hai bản `DemoPlugin` đều triển khai đúng một `PluginApi` đó. Vì thế có thể ép instance của classA sang `PluginApi` và gọi `greet()` an toàn.
4. `DemoPlugin.class` trong mã chính tham chiếu bản do **parent** tải, khác với `classA`. Ép object của classA thành `DemoPlugin` từ parent gây `ClassCastException`, dù tên class giống hệt.
5. `childA` và `childB` ở cuối không định nghĩa riêng `DemoPlugin` mà dùng chiến lược ủy quyền mặc định. Cả hai tải thành công về **cùng `Class<?>`** của parent.

Đây là ví dụ đào tạo đơn giản: mã đọc bytes `DemoPlugin.class` từ resource của parent và cố ý thay đổi quy tắc ủy quyền cho **một** lớp. Một hệ thống plugin thực tế cần xử lý thêm package, dependency, nguồn JAR, tài nguyên, unload/lifecycle và chính sách bảo vệ.

## 4. Hệ quả trong Reflection và kiểm tra kiểu

### So sánh `Class<?>` đúng ý nghĩa

| Kiểm tra | Điều gì được so sánh? | Có chứng minh cùng kiểu runtime không? |
| --- | --- | --- |
| `a.getName().equals(b.getName())` | Chuỗi tên lớp | **Không** |
| `a == b` hoặc `a.equals(b)` | Danh tính `Class` | **Có** |
| `a.getClassLoader() == b.getClassLoader()` | Cùng defining loader | **Chưa đủ**; còn phải cùng binary name |
| `a.isAssignableFrom(b)` | Khả năng gán giá trị kiểu `b` cho biến kiểu `a` | Kiểm tra tương thích kiểu, không chỉ tên |
| `a.isInstance(object)` | Instance có tương thích với kiểu `a` không | Có, kiểm tra tương thích đối tượng |
| `a.cast(object)` | Thực hiện cast runtime theo `a` | Ném `ClassCastException` nếu không tương thích |

**`Class<?>` là đối tượng phản ánh định nghĩa kiểu cụ thể**, không phải một record chỉ chứa tên. Khi cần chứng minh cùng runtime class, ưu tiên so sánh trực tiếp đối tượng `Class`.

### Reflection có thể thất bại dù tên hiển thị giống nhau

Giả sử `Method` lấy từ `classA`, nhưng bạn cố gọi nó trên một instance của `classB`:

```java
// Minh họa thêm bên trong main của LoaderIdentityDemo;
// classA, classB đã được tạo như ví dụ trên.
Object second = classB.getDeclaredConstructor().newInstance();
var methodFromA = classA.getMethod("greet");

try {
    methodFromA.invoke(second);
} catch (IllegalArgumentException e) {
    System.out.println("Sai receiver runtime type");
}
```

Đây là **mảnh code minh họa bổ sung**, không phải file Java độc lập. `methodFromA` mô tả phương thức khai báo trên classA, nhưng `second` là đối tượng classB, không phải instance hợp lệ của classA; lời gọi phản chiếu bị từ chối với `IllegalArgumentException` về receiver.

Trong tình huống tương tự, một API lấy `Class<?>` từ loader này rồi dùng constructor/field/method hoặc cast với đối tượng của loader khác có thể lỗi bất ngờ. Không nên chỉ nhìn `getName()` mà cho rằng hai bên tương thích.

### `ClassCastException` “X cannot be cast to X” có nghĩa gì?

Thông báo lỗi runtime trên một số phiên bản Java có thể hiển thị một class không thể cast sang class **cùng tên**, và kèm thông tin loader/module để phân biệt. Lỗi không hề mâu thuẫn: hai tên giống nhau nhưng hai `Class` khác nhau. Không nên dựa vào **toàn bộ văn bản** thông báo vì format và cách đặt tên loader có thể thay đổi theo JDK/môi trường.

## 5. Diagnosing: xác định đâu là class thực sự

Khi gặp lỗi cast hoặc Reflection ở plugin, servlet container, application server, hot reload hay test environment, hãy kiểm tra cả **tên**, **đối tượng `Class`** và **defining loader** ở hai phía.

Đoạn helper sau có thể đưa vào code chẩn đoán; nó **không phải một chương trình độc lập**:

```java
static void describe(String label, Object value) {
    Class<?> type = value.getClass();
    ClassLoader loader = type.getClassLoader();

    System.out.println(label + " name=" + type.getName());
    System.out.println(label + " loader=" + loader);
    System.out.println(label + " module=" + type.getModule().getName());
}
```

Khi so sánh hai đối tượng:

```java
Class<?> left = leftObject.getClass();
Class<?> right = rightObject.getClass();

System.out.println("Same name: " + left.getName().equals(right.getName()));
System.out.println("Same Class: " + (left == right));
System.out.println("Same defining loader: "
        + (left.getClassLoader() == right.getClassLoader()));
```

**Ghi chú đọc log:**

- `getClassLoader() == null` thường gặp với lớp được **bootstrap loader** định nghĩa; đừng diễn giải `null` là lỗi.
- `getModule().getName()` có thể là `null` đối với unnamed module; module name **không thay thế** defining loader để xác định kiểu.
- `ClassLoader.toString()`, tên loader và mã nhận diện dạng hash chỉ giúp điều tra. Muốn khẳng định cùng loader trong chương trình, so sánh đối tượng loader bằng `==`.
- Đối chiếu classpath, thứ tự nạp và JAR thực tế khi nghi lớp trùng; **nguồn bytecode giống nhau không làm hai `Class` đồng nhất**.
- `Thread.currentThread().getContextClassLoader()` là **context loader của thread**, được nhiều framework dùng để tìm tài nguyên/lớp; nó không nhất thiết là defining loader của đối tượng đang kiểm tra. Hãy ưu tiên `object.getClass().getClassLoader()` khi hỏi “ai định nghĩa kiểu này?”.

Khi xem stack trace, chẩn đoán hai phía của phép ép kiểu hoặc phương thức nhận tham số; nếu một API trả đối tượng từ loader riêng, bên nhận phải kiểm tra contract chung thay vì tự ép về bản class của mình.

## 6. Vì sao cơ chế này có ích và vì sao dễ gây lỗi?

### Ích lợi: namespace và lifecycle riêng cho plugin

Một host có thể dùng loader riêng cho từng plugin để tránh va chạm phiên bản thư viện hoặc thay thế plugin theo lifecycle. Hai plugin có thể phụ thuộc vào class cùng binary name nhưng mỗi plugin nhìn thấy định nghĩa riêng. Điều này giúp **cô lập kiểu/dependency**, dù **không phải cơ chế sandbox bảo mật**.

Một tính năng hot reload có thể tạo loader mới, nạp phiên bản mới của một lớp, trong khi đối tượng của loader cũ vẫn tồn tại. Các đối tượng cũ và mới **không nhất thiết** tương thích chỉ vì tên class không đổi.

### Rủi ro: “split-brain type”

Nếu host định nghĩa `com.example.api.PluginApi` bằng một loader, nhưng plugin cũng tự định nghĩa **bản riêng của chính interface đó**, thì câu lệnh:

```java
PluginApi api = (PluginApi) pluginObject;
```

có thể thất bại. Mỗi `PluginApi` mang một defining loader khác nhau, do đó hai loại interface không phải một contract runtime duy nhất, dù source code/interface method giống nhau.

**Cách tổ chức phổ biến:** host và plugin phải thống nhất những kiểu **dùng làm contract qua ranh giới** (interface, DTO cần chia sẻ...). Thường để parent/common loader định nghĩa API chung; child loader dùng phần riêng của plugin và ủy quyền những API chung lên parent.

Điều này không có nghĩa “mọi plugin đều phải parent-first toàn bộ”. Chiến lược child-first có thể cần thiết khi plugin mang dependency riêng. Quy tắc cốt lõi là **định nghĩa rõ những kiểu nào phải được chia sẻ cùng một danh tính runtime**.

### Xung đột chữ ký phương thức và loader constraints

JVM còn áp đặt **loader constraints** để bảo đảm những kiểu xuất hiện trong chữ ký phương thức/field tương tác qua các loader được hiểu nhất quán trong các trường hợp nhất định. Khi các constraint bắt buộc đồng nhất kiểu nhưng hai loader đã định nghĩa lớp không tương thích, có thể xuất hiện `LinkageError`. Đây là vấn đề khác với `ClassCastException` tại câu lệnh cast, nhưng cùng xuất phát từ ranh giới class loader và định danh kiểu.

## 7. Những hiểu lầm phổ biến

| Hiểu lầm | Thực tế |
| --- | --- |
| “Tên class giống nhau tức là cùng kiểu.” | Danh tính lớp tham chiếu còn phụ thuộc defining loader. |
| “Hai loader instance luôn tạo hai kiểu khác nhau.” | Nếu cả hai ủy quyền về một defining loader, chúng nhận cùng một `Class`. |
| “Cùng JAR/bytecode thì cast được.” | Cùng bytecode vẫn có thể được định nghĩa hai lần bởi hai loader khác nhau. |
| “`getName()` đủ để kiểm tra kiểu.” | Chỉ dùng tên để hiển thị/tra cứu; dùng `Class`, `isInstance`, `isAssignableFrom` khi cần kiểm tra kiểu. |
| “`Class.forName(...)` lúc nào cũng dùng một loader.” | Có overload dùng loader rõ ràng; lựa chọn loader ảnh hưởng kết quả. |
| “Đổi TCCL sẽ đổi lớp của instance đang có.” | `Thread Context ClassLoader` không thay đổi defining loader của class đã được định nghĩa. |
| “ClassLoader là sandbox bảo mật.” | Cô lập namespace/dependency không tự tạo ranh giới bảo mật. |

## 8. Áp dụng khi thiết kế hệ thống

Khi chuẩn bị viết plugin framework hoặc API dùng Reflection, có thể đi theo quy trình:

1. **Xác định contract chung**: interface và những kiểu dữ liệu cần truyền từ plugin sang host và ngược lại.
2. **Đặt contract tại loader chia sẻ**: bảo đảm bên host và plugin cùng nhận một `Class<?>` cho mỗi kiểu của contract.
3. **Đặt implementation và dependency riêng tại loader phù hợp**: có thể là loader của từng plugin.
4. **Nạp plugin qua loader đã chọn** và kiểm tra `sharedApiClass.isAssignableFrom(implementationClass)` hoặc `sharedApiClass.isInstance(instance)` trước khi cast.
5. **Không lưu tên class làm bằng chứng tương thích**: dùng identity của `Class` và phép kiểm tra gán kiểu thực tế.
6. **Ghi thông tin hai loader khi lỗi**: chẩn đoán đầu nguồn và đầu nhận, nhất là khi `ClassCastException`/`LinkageError` xuất hiện.
7. **Quản lý vòng đời loader/instance**: tránh giữ reference, thread, static cache hoặc registration khiến loader/plugin cũ tiếp tục tồn tại ngoài dự tính khi hot reload.

Phần lớn code ứng dụng thông thường không cần tự tạo class loader. Hiểu quy tắc định danh lớp giúp đọc đúng metadata Reflection, lý giải lỗi ép kiểu “cùng tên”, và đưa ra quyết định có cơ sở khi gặp plugin/framework/container.

## 9. Ghi nhớ và tự kiểm tra

**Ghi nhớ:** Với lớp tham chiếu, **binary name + defining loader** mới quyết định danh tính kiểu runtime. Initiating loader có thể chỉ ủy quyền, nên số lượng loader bắt đầu tải lớp không nói lên số lượng định nghĩa. Hãy so sánh `Class<?>` trực tiếp, kiểm tra `isInstance`/`isAssignableFrom` và chia sẻ interface đúng loader khi trao đổi object qua ranh giới plugin.

Tự kiểm tra:

1. Hai object có `getClass().getName()` giống nhau nhưng cast thất bại. Bạn sẽ kiểm tra thêm những gì?
2. Hai child loader cùng gọi `loadClass("x.Plugin")` và trả về đúng một `Class<?>`. Ai có thể là defining loader?
3. Trong ví dụ chạy được, vì sao cast về `DemoPlugin` thất bại nhưng cast về `PluginApi` thành công?
4. Chỉ đổi thread context class loader có làm thay đổi `getClass().getClassLoader()` của object đã tạo không?
5. Nếu host/plugin cùng đưa một interface API vào loader riêng của mình, vấn đề gì có thể xảy ra?
