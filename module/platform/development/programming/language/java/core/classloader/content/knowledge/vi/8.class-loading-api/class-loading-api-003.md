# findLoadedClass và việc tái sử dụng lớp đã được loader ghi nhận

## 1. Vì sao một ClassLoader cần kiểm tra lớp đã nạp?

Khi JVM hoặc ứng dụng yêu cầu nạp một class, bộ nạp lớp cần biết tên đó đã được xử lý trong phạm vi loader liên quan hay chưa. Nếu mỗi yêu cầu đều tạo một định nghĩa class mới có cùng binary name trong cùng defining loader, hệ thống kiểu sẽ thiếu nhất quán và có thể vi phạm quy tắc JVM.

Java cung cấp phương thức:

```java
protected final Class<?> findLoadedClass(String name)
```

Phương thức này trả lại `Class<?>` tương ứng với tên nhị phân `name` **nếu JVM đã ghi nhận loader hiện tại là một initiating loader của class mang tên đó**. Nếu chưa có ghi nhận phù hợp, phương thức trả `null`.

Điều quan trọng: `findLoadedClass` là **tra cứu trạng thái đã có**, không phải yêu cầu đọc một file `.class`, gọi loader cha, thực hiện `findClass`, khởi tạo lớp hay tạo đối tượng.

Một quy tắc thực hành:

- **`findLoadedClass(name)`:** “JVM đã ghi nhận loader này là initiating loader của class tên `name` chưa?”
- **`loadClass(name)`:** “Hãy tìm/lấy class mang tên `name`, thông thường kiểm tra lớp đã có, ủy quyền tới cha rồi mới tìm bằng loader hiện tại.”
- **`findClass(name)`:** “Nếu cơ chế tìm ở parent chưa cung cấp class, hãy để loader hiện tại thử tìm và định nghĩa class theo cách riêng.”
- **`defineClass(...)`:** “Định nghĩa runtime class từ bytes phù hợp, với loader hiện tại làm defining loader.”
- **`resolveClass(c)`:** “Yêu cầu JVM liên kết class theo API, nếu cần”; không đồng nghĩa thực thi static initializer.

Trong một loader được thiết kế đúng, `findLoadedClass` là bước đầu quan trọng để tránh cố định nghĩa lặp class và để những lần tra cứu tiếp theo sử dụng lại runtime type đã ghi nhận.

## 2. Chính xác phương thức trả về điều gì?

Theo Java SE 17 API, `findLoadedClass(String)`:

1. Nhận **binary name** như `com.example.Plugin` hoặc `java.lang.String`.
2. Xem loader object mà trên đó method được gọi có được JVM ghi nhận là **initiating loader** của class mang tên đó hay không.
3. Trả một `Class<?>` nếu đã có ghi nhận; nếu không trả `null`.

Phương thức là **`protected final`**:

- `protected`: code bên ngoài không được gọi tự do qua một `ClassLoader` bất kỳ; subclass có thể dùng trong cơ chế nạp của mình.
- `final`: subclass không thể override và tự thay đổi ý nghĩa việc tra cứu JVM đã ghi nhận.
- Không có checked `ClassNotFoundException`: nó chỉ tra cứu, không tự tìm file/module trên đường nạp.
- Giá trị `null` có nghĩa **loader này chưa được VM ghi nhận là initiating loader của tên đó**; không có nghĩa class ấy vắng mặt ở mọi loader trong JVM.

Ví dụ, nếu application loader đã biết `com.example.Service` nhưng một custom loader mới chưa từng tham gia nạp tên đó, `custom.findLoadedClass("com.example.Service")` có thể trả `null` dù class hoàn toàn tồn tại trong ứng dụng. Sau khi custom loader yêu cầu parent nạp, việc ghi nhận initiating loader chịu quy tắc VM và ngữ cảnh yêu cầu; không được suy rằng một lời gọi Java trực tiếp đã tạo bản sao class hoặc bắt buộc cache kết quả theo cách tùy ý.

### Hai từ “đã nạp” dễ gây hiểu lầm

`findLoadedClass` được đặt tên theo cách dùng thực tế trong thuật toán `loadClass`, nhưng contract chính xác đề cập tới **initiating loader được JVM ghi nhận**, không chỉ “class mà loader này tự `defineClass`”.

Một loader có thể:

- **Tự định nghĩa** một class: nó là defining loader và được VM ghi nhận liên quan tới việc nạp class.
- **Ủy quyền** cho loader cha: class trả về có thể do cha định nghĩa; loader khởi xướng và defining loader có thể khác nhau.
- Không hề biết class: `findLoadedClass` trả `null` trong phạm vi loader đó, dù parent hoặc loader khác có thể tìm được class.

Đặc tả JVMS mô tả sự khác biệt này bằng khái niệm **defining loader** và **initiating loader**.

## 3. Đặt findLoadedClass vào luồng loadClass mặc định

Với `ClassLoader.loadClass(String, boolean)` mặc định, logic chính có thể đọc như sau:

```text
loadClass(binaryName, resolve)
          |
          v
findLoadedClass(binaryName)
          |
          +-- Có Class<?> ----------> reuse Class<?> đã ghi nhận
          |
          +-- null
                |
                v
      Parent.loadClass(binaryName)
       (hoặc bootstrap nếu parent null)
                |
                +-- Thành công -----> dùng Class<?> được parent cung cấp
                |
                +-- Không tìm thấy
                        |
                        v
                   findClass(binaryName)
                        |
                        +-- Thành công -> dùng Class<?> tìm/định nghĩa được
                        |
                        +-- Thất bại -> ClassNotFoundException

Nếu resolve == true: gọi resolveClass(classFound).
Trả Class<?> cho bên yêu cầu.
```

Viết theo mã giả:

```text
Class c = findLoadedClass(name);
if (c == null) {
    try {
        c = parent != null
                ? parent.loadClass(name)
                : askBootstrapLoader(name);
    } catch (ClassNotFoundException ignored) {
        // tiếp tục cơ chế loader hiện tại
    }
    if (c == null) {
        c = findClass(name);
    }
}
if (resolve) {
    resolveClass(c);
}
return c;
```

**Đây là mã giả giải thích luồng, không phải code Java biên dịch độc lập**: `askBootstrapLoader` không phải method công khai trong Java API. Luồng thực tế còn bao gồm đồng bộ hóa bằng `getClassLoadingLock(name)` và chi tiết lookup của VM.

Ý nghĩa chính:

- `findLoadedClass` được gọi **trước khi** parent delegation hoặc `findClass` trong thuật toán mặc định.
- Nếu trả một `Class<?>`, loader không cần cố tìm/định nghĩa lại kiểu đó trong lần gọi ấy.
- Nếu trả `null`, cơ chế vẫn tiếp tục qua parent/bootstrap và/hoặc `findClass`.
- `loadClass(name)` tương đương `loadClass(name, false)`; giá trị `false` không làm mất bước `findLoadedClass`.

Một subclass có thể override `loadClass` để thực hiện child-first, selective delegation hoặc cơ chế riêng; trong trường hợp đó cần giữ việc tránh nạp trùng một cách chính xác.

## 4. Tên class, định danh kiểu và giới hạn vùng tra cứu

Java runtime class/interface identity dựa trên **binary name và defining loader**. Vì vậy:

```text
com.example.Widget + LoaderA  -> runtime Class A
com.example.Widget + LoaderB  -> runtime Class B
```

Hai `Class<?>` trên khác nhau nếu LoaderA và LoaderB thực sự định nghĩa hai class độc lập, dù tên string `com.example.Widget` giống nhau.

`findLoadedClass` **không tìm toàn JVM** để trả một class bất kỳ trùng tên. Nó kiểm tra class mà loader **hiện tại** đã được VM ghi nhận là initiating loader. Vì thế:

- LoaderA có thể tìm thấy bản `Widget` riêng của A.
- LoaderB có thể chưa ghi nhận `Widget`, nên trả `null`.
- Sau đó LoaderB có thể ủy quyền và nhận `Widget` của một parent, hoặc tự định nghĩa `Widget` của B, tùy chính sách và loading constraints liên quan.
- Không được suy từ `findLoadedClass(name) == null` rằng tên đó chưa xuất hiện ở class path hoặc chưa được loader khác định nghĩa.

### Binary name khác descriptor

| Loại | Ví dụ | Dùng với findLoadedClass? |
|---|---|---|
| Binary name class | `java.lang.String` | Có |
| Binary name nested class | `java.util.Map$Entry` | Có |
| Internal name bytecode | `java/lang/String` | Không |
| Field descriptor class | `Ljava/lang/String;` | Không |
| Source-style array | `String[]` | Không phải binary name của ordinary class |
| Primitive name | `int` | Không phải class được nạp từ ordinary class file |

Đối với array, JVM có quy tắc riêng để tạo array class khi cần; không dùng `findLoadedClass("[I")` như một API phổ quát tạo/truy vấn array classes bằng descriptor. Với kiểu mảng, dùng class literal (`int[].class`) hoặc `Class.forName` với array name được tài liệu hỗ trợ, nếu yêu cầu lookup bằng chuỗi.

## 5. Java 17: minh họa chính xác việc định nghĩa một lần và tái sử dụng

Ví dụ sau cố ý thiết kế **một custom loader tự định nghĩa một class cụ thể**. Điều này giúp chứng minh `findLoadedClass` tránh định nghĩa lại class mà không phụ thuộc vào cách ghi nhận một đường parent delegation.

Tạo file **`FindLoadedDemo.java`** chứa cả public class và package-private class ở cuối file:

```java
import java.io.IOException;
import java.io.InputStream;

public class FindLoadedDemo {
    static final String TARGET = "LocalPayload";

    static class CopyLoader extends ClassLoader {
        private int definitions;

        CopyLoader(ClassLoader parent) {
            super(parent);
        }

        Class<?> peek(String binaryName) {
            return findLoadedClass(binaryName);
        }

        int definitions() {
            return definitions;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!TARGET.equals(name)) {
                return super.loadClass(name, resolve);
            }

            synchronized (getClassLoadingLock(name)) {
                Class<?> type = findLoadedClass(name);
                if (type == null) {
                    type = findClass(name);
                }
                if (resolve) {
                    resolveClass(type);
                }
                return type;
            }
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!TARGET.equals(name)) {
                throw new ClassNotFoundException(name);
            }

            String resource = name.replace('.', '/') + ".class";

            try (InputStream input =
                         getParent().getResourceAsStream(resource)) {
                if (input == null) {
                    throw new ClassNotFoundException(name);
                }

                byte[] bytes = input.readAllBytes();
                Class<?> type =
                        defineClass(name, bytes, 0, bytes.length);
                definitions++;
                return type;
            } catch (IOException error) {
                throw new ClassNotFoundException(name, error);
            }
        }
    }

    public static void main(String[] args)
            throws ClassNotFoundException {
        ClassLoader app = FindLoadedDemo.class.getClassLoader();
        CopyLoader custom = new CopyLoader(app);

        System.out.println("Before load: "
                + (custom.peek(TARGET) == null));

        Class<?> first = custom.loadClass(TARGET);
        Class<?> second = custom.loadClass(TARGET);

        System.out.println("Same Class object: " + (first == second));
        System.out.println("Found by peek: "
                + (custom.peek(TARGET) == first));
        System.out.println("Definitions: " + custom.definitions());
        System.out.println("Owned by custom: "
                + (first.getClassLoader() == custom));

        Class<?> appCopy = app.loadClass(TARGET);
        System.out.println("Different from app: "
                + (first != appCopy));
    }
}

class LocalPayload {
}
```

Trong thư mục chứa file này, chạy trên JDK 17 trở lên:

```bash
javac FindLoadedDemo.java
java FindLoadedDemo
```

Kết quả stdout:

```text
Before load: true
Same Class object: true
Found by peek: true
Definitions: 1
Owned by custom: true
Different from app: true
```

**Giải thích từng bước:**

1. `javac` tạo `FindLoadedDemo.class`, các class file phụ tương ứng và `LocalPayload.class`. Hai runtime class identities `LocalPayload` chỉ được tạo **lúc chương trình chủ động nạp**.
2. `custom.peek("LocalPayload")` gọi `findLoadedClass` từ trong subclass. Ban đầu custom loader chưa định nghĩa/được VM ghi nhận cho tên đó, nên trả `null`.
3. Lần `custom.loadClass(TARGET)` đầu tiên vào nhánh override chỉ dành cho `LocalPayload`; `findLoadedClass` trả `null` và `findClass` đọc bytes `LocalPayload.class`, gọi `defineClass`. Bộ đếm `definitions` tăng lên một.
4. Lần gọi thứ hai, `findLoadedClass` trả về đúng `Class<?>` đã được custom loader định nghĩa, nên không gọi `findClass` lần nữa.
5. `first == second` chứng minh cùng một runtime class object; `definitions == 1` chứng minh class đã được custom loader **định nghĩa một lần**.
6. `first.getClassLoader() == custom` cho biết custom loader là **defining loader** của bản class này.
7. `app.loadClass(TARGET)` cung cấp một runtime `LocalPayload` riêng do application loader định nghĩa. Hai class có cùng binary name nhưng khác defining loaders, nên `first != appCopy`.

**Phạm vi minh họa:** đoạn override thực hiện child-first **chỉ với `LocalPayload`**. Các tên khác đi qua `super.loadClass` theo cơ chế mặc định. Không áp dụng mẫu child-first không kiểm soát cho package lõi hoặc shared API của plugin.

Không có instance nào của `LocalPayload` được tạo trong ví dụ; nạp định nghĩa class và tạo object là hai hoạt động khác nhau.

## 6. Khi class được parent nạp: reuse và owner là hai câu hỏi khác nhau

Xét một loader con ủy quyền bình thường:

```java
ClassLoader app = MyMain.class.getClassLoader();
ClassLoader child = new ClassLoader(app) { };
Class<?> type = child.loadClass("java.lang.String");
```

Đoạn này là **mã minh họa**, cần có class `MyMain`. `type` thường chính là `String.class`, có defining loader là bootstrap. Loader con **không** tạo thêm một `String` mới.

Ở đây nên phân biệt:

- **Kết quả lookup:** `child.loadClass(...)` có thể trả về một `Class<?>` do parent/bootstrap định nghĩa.
- **Defining loader:** `type.getClassLoader()` mô tả loader sở hữu định nghĩa; với `String` chuẩn sẽ là `null`.
- **Initiating loader:** JVM có thể ghi nhận các loader tham gia quá trình nạp/resolve một class; `findLoadedClass` xét **ghi nhận của VM**, không xét đơn giản bằng việc “đã từng gọi Java method nào”.
- **Tái sử dụng:** khi nhận lại chính `Class<?>` của parent, không có bản sao class được tự động tạo thêm.

Điểm cần cẩn trọng với ví dụ trực tiếp `child.loadClass(...)`: **đừng khẳng định bất kể ngữ cảnh JVM nào, sau mỗi lần Java code trực tiếp gọi `loadClass` để lấy class từ parent, `child.findLoadedClass(name)` nhất định phải khác `null`.** Contract chính xác của `findLoadedClass` yêu cầu JVM đã ghi nhận loader là initiating loader; hoạt động JVM loading/resolution và một method call do Java code chủ động gọi không nên bị đồng nhất trong phần suy luận của chương trình.

### Ví dụ Java 17: xác nhận cùng runtime class sau delegation

Tạo file **`ParentReuseDemo.java`**:

```java
public class ParentReuseDemo {
    public static void main(String[] args)
            throws ClassNotFoundException {
        ClassLoader parent = ParentReuseDemo.class.getClassLoader();
        ClassLoader child = new ClassLoader(parent) { };

        Class<?> a = child.loadClass("ParentReuseDemo");
        Class<?> b = child.loadClass("ParentReuseDemo");

        System.out.println("Same Class returned: " + (a == b));
        System.out.println("Same as source class: "
                + (a == ParentReuseDemo.class));
        System.out.println("Owner is parent: "
                + (a.getClassLoader() == parent));
        System.out.println("Child does not define it: "
                + (a.getClassLoader() != child));

        Class<?> core = child.loadClass("java.lang.String");
        System.out.println("String from bootstrap: "
                + (core == String.class
                   && core.getClassLoader() == null));
    }
}
```

Chạy:

```bash
javac ParentReuseDemo.java
java ParentReuseDemo
```

Stdout trên JDK 17 trong cấu hình class path thông thường:

```text
Same Class returned: true
Same as source class: true
Owner is parent: true
Child does not define it: true
String from bootstrap: true
```

Hai lần `child.loadClass("ParentReuseDemo")` trả cùng class identity do **parent** định nghĩa. Chương trình không yêu cầu một đảm bảo không có trong API về số lần hàm parent được gọi bên trong hoặc trạng thái ghi nhận nội bộ của `child`; nó chỉ quan sát điều chắc chắn từ kết quả.

## 7. Khi findLoadedClass trả null: hiểu đúng khả năng xảy ra

`null` có thể xuất hiện khi:

1. Loader đó chưa tham gia nạp/được VM ghi nhận cho binary name yêu cầu.
2. Một class cùng tên có ở loader khác nhưng chưa được loader này ghi nhận là initiating loader.
3. Loader đã được tạo nhưng chương trình chưa yêu cầu nạp một class thuộc phạm vi của nó.
4. Tên truyền vào không phù hợp với contract của API, ví dụ dùng descriptor thay vì binary name; không nên dùng trả `null` để suy ra đó là cú pháp tên hợp lệ.

**Không thể suy ra chỉ từ `null` rằng:**

- Class không tồn tại trong JVM.
- Parent/bootstrap không thể tìm được class.
- Class file không nằm trên class path.
- Class chưa từng được load bởi bất cứ class loader nào.
- Phải gọi `defineClass` ngay lập tức, bỏ qua chính sách delegation của loader.

Nếu loader đang thực hiện thuật toán mặc định, kết quả `null` khiến nó tiếp tục parent delegation trước. Chỉ khi bước parent không tìm được, `findClass` mới được yêu cầu.

## 8. Nếu bỏ findLoadedClass hoặc định nghĩa trùng thì sao?

Giả sử một custom loader override `loadClass` và mỗi lần đều tự đọc bytes, gọi `defineClass` cho **cùng binary name**. Trong một defining loader, không được định nghĩa hai runtime classes có cùng tên; hành vi có thể dẫn tới `LinkageError` do nỗ lực định nghĩa lặp, thay vì cho ra “hai bản mới” có cùng defining loader.

Một ví dụ mã giả **không nên dùng trong ứng dụng**:

```text
// Sai: không kiểm tra class đã định nghĩa hoặc ghi nhận
loadClass(name):
    bytes = readClassFile(name)
    return defineClass(name, bytes, ...)
```

Khi cùng tên được yêu cầu lại, loader có thể tiếp tục gọi `defineClass` và thất bại. Ngược lại, phần 5 đã cho thấy một cách kiểm tra `findLoadedClass` trước khi định nghĩa.

**Quan hệ với identity:** hai class cùng binary name nhưng khác **defining loader** có thể tồn tại. Hai định nghĩa trùng tên bởi **cùng defining loader** không tạo thành hai class hợp lệ. Hai tình huống không mâu thuẫn nhau.

**Quan hệ với lỗi khác:** `ClassNotFoundException` nghĩa lookup không tìm thấy class; `LinkageError` có thể xảy ra khi class data/constraints/linking không hợp lệ. Không gọi mọi `LinkageError` là “class đã load hai lần” mà phải xét thông báo và stack trace cụ thể.

## 9. findLoadedClass không đồng nghĩa initialize hoặc tạo object

Mỗi một việc sau là khác nhau:

| Hoạt động | Ý nghĩa |
|---|---|
| `findLoadedClass(name)` | Tra cứu class đã được JVM ghi nhận cho initiating loader này |
| `loadClass(name)` | Yêu cầu nạp/lấy class, thường không yêu cầu initialization |
| `defineClass(...)` | Định nghĩa runtime class từ bytes |
| `resolveClass(c)` | Yêu cầu linking class theo API |
| `Class.forName(name)` | Tra cứu class; overload một tham số thường yêu cầu initialization |
| `new SomeClass()` | Tạo một instance mới, bảo đảm class đã initialized theo quy tắc |
| `getDeclaredConstructor().newInstance()` | Dùng reflection để tạo instance nếu truy cập/constructor phù hợp |

Vì `findLoadedClass` chỉ trả `Class<?>` đã ghi nhận:

- Không thực thi constructor.
- Không chủ động chạy static initializer `<clinit>`.
- Không chứng minh class đã initialized thành công; loading, linking và initialization là những giai đoạn khác nhau.
- Không đảm bảo class có thể được sử dụng với mọi phương thức hoặc dependency ở bất kỳ thời điểm nào; linking/resolution và access rules vẫn có thể gây lỗi.

Ví dụ:

```java
Class<?> existing = custom.peek("LocalPayload");
```

Nếu chương trình đã tạo/ghi nhận class bằng loader `custom` như phần 5, dòng trên chỉ lấy metadata class. Đó không phải một lần `new LocalPayload()`.

## 10. Thread-safety: vì sao phải gắn với getClassLoadingLock?

Trong môi trường nhiều thread, hai thread có thể đồng thời yêu cầu loader nạp cùng binary name:

```text
Thread A: findLoadedClass("Plugin") -> null
Thread B: findLoadedClass("Plugin") -> null
Thread A: defineClass("Plugin", ...) -> thành công
Thread B: defineClass("Plugin", ...) -> nguy cơ định nghĩa trùng/LinkageError
```

Nếu tự override `loadClass`, cần đồng bộ phần **kiểm tra đã nạp → nạp/định nghĩa → resolve** cho cùng tên. API `ClassLoader.getClassLoadingLock(name)` hỗ trợ lock phù hợp với cơ chế class loading.

Hình mẫu:

```java
@Override
protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException {
    synchronized (getClassLoadingLock(name)) {
        Class<?> type = findLoadedClass(name);
        if (type == null) {
            // Áp dụng chính sách delegation của loader;
            // nếu parent không cung cấp, mới tìm/định nghĩa class.
            type = findClass(name);
        }
        if (resolve) {
            resolveClass(type);
        }
        return type;
    }
}
```

Đây là **khung minh họa**, không phải một implementation parent-first hoàn chỉnh vì nó không ủy quyền cho parent. Muốn dùng chính sách thông thường, hãy ưu tiên **chỉ override `findClass`** và để `loadClass` kế thừa thực hiện các bước kiểm tra, delegation và đồng bộ hóa.

### Parallel-capable class loaders

Các subclass có thể đăng ký `registerAsParallelCapable()` theo contract của Java để cho phép những class name khác nhau được nạp đồng thời theo cách thích hợp. Nếu không, implementation mặc định có thể dùng lock rộng hơn trên loader object. Không phải cứ gọi `getClassLoadingLock(name)` là loader tự động parallel-capable.

Khi tự override `loadClass`, việc dùng lock phải nhất quán với cấu hình parallel-capable và các shared mutable state trong `findClass`. Bộ đếm minh họa trong phần 5 chỉ được truy cập theo luồng tuần tự trong `main`; nếu đưa vào hệ thống nhiều thread thực tế, cần thiết kế đồng bộ/quan sát state riêng.

## 11. Vì sao không tự viết một cache Map<String, Class<?>> thay cho findLoadedClass?

Một số custom loader muốn lưu:

```java
Map<String, Class<?>> cache;
```

Cache ứng dụng có thể hữu ích để quản lý metadata hoặc tài nguyên phụ trợ, nhưng **không thay thế contract của JVM về class identity và initiating loader**.

Các rủi ro nếu chỉ dựa trên một map tự tạo:

- Map có thể sai lệch so với trạng thái class mà VM đã ghi nhận.
- Nếu class được giải quyết từ parent, việc tự bỏ/mất key trong map không làm định nghĩa parent biến mất.
- Hai thread không được đồng bộ đúng có thể vẫn đua nhau đọc bytes và `defineClass`.
- Nếu giữ reference mạnh tới `Class<?>` hoặc custom loader lâu hơn cần thiết, cache có thể cản class unloading trong mô hình plugin/hot-reload.
- Map không tự kiểm tra loading constraints hoặc package/module access rules mà VM phải áp dụng.

Vì vậy, sử dụng `findLoadedClass` làm tra cứu chuẩn trong logic nạp lớp. Chỉ thêm cache nếu có **mục tiêu tách biệt**, lifecycle rõ ràng và không gây sai khác với VM.

### findLoadedClass và findClass khác chỗ nào?

Hai tên dễ nhầm:

- `findLoadedClass`: **kiểm tra đã được ghi nhận**; `protected final`, trả `Class<?>` hoặc `null`.
- `findClass`: **móc tìm và định nghĩa class mới** do subclass triển khai; có thể đọc bytes/JAR/resource rồi gọi `defineClass` hoặc ném `ClassNotFoundException`.

Không thay `findClass` bằng lời gọi `findLoadedClass` rồi kỳ vọng một class chưa tồn tại sẽ tự được tạo ra.

## 12. Trường hợp thực tế: plugin loader và hot reload

Một ứng dụng host tải plugin bằng custom class loader. Trong vòng đời của **một loader object**:

1. Plugin `com.example.ReportPlugin` được yêu cầu lần đầu.
2. Parent không cung cấp class plugin; custom `findClass` định nghĩa nó.
3. Những yêu cầu về cùng tên qua loader đó cần tái sử dụng định nghĩa đã ghi nhận.
4. Khi hot reload phiên bản mới, thường cần **tạo một loader mới** cho phiên bản plugin mới, vì class đã được định nghĩa không được thay thế chỉ bằng cách gọi lại `defineClass` cùng tên ở loader cũ.

Thực tế, có thể thực hiện cơ chế redefinition/retransformation đặc biệt qua instrumentation, nhưng đó là một API khác có giới hạn riêng, không làm `findLoadedClass` trở thành cơ chế reload bytes.

Ngược lại, class loader mới cũng không đảm bảo loader cũ được GC/unload ngay: các thread, callbacks, `ThreadLocal`, caches, instances hoặc `Class<?>` references vẫn có thể giữ loader cũ reachable.

Khi debug lỗi plugin:

- Quan sát class loader object và `clazz.getClassLoader()`.
- So sánh các `Class<?>` bằng `==` khi muốn biết runtime type có cùng identity không.
- Kiểm tra liệu loader chủ động định nghĩa hay ủy quyền sang parent.
- Nếu xung đột, xem `ClassCastException` và `LinkageError` theo ngữ cảnh loader/descriptor.
- Đừng suy rằng việc có hai class cùng binary name trên hai loader khác nhau tự động là lỗi; thường đó là cơ chế cách ly mong muốn, miễn các shared API types được resolve thống nhất.

## 13. Các lỗi phổ biến và cách tránh

| Nhận định sai | Cách hiểu đúng |
|---|---|
| “`findLoadedClass` sẽ load class nếu chưa có.” | Nó chỉ tra cứu và trả `null` nếu không có ghi nhận phù hợp. |
| “`findLoadedClass` chỉ tìm class mà chính loader tự định nghĩa.” | API dựa trên **initiating loader** được JVM ghi nhận, không đơn giản là defining loader. |
| “`findLoadedClass(name) == null` chứng minh class chưa có ở đâu trong JVM.” | Nó chỉ phản ánh trạng thái VM liên quan đến **loader hiện tại**. |
| “Cùng binary name nghĩa là cùng class.” | Runtime identity còn phụ thuộc defining loader. |
| “`loadClass` mỗi lần tạo một định nghĩa class mới.” | Loader đúng cách tái sử dụng class đã ghi nhận hoặc định nghĩa do parent cung cấp. |
| “`findClass` và `findLoadedClass` là tên khác của cùng việc.” | Một bên tìm/định nghĩa mới, một bên tra cứu đã nạp. |
| “Lặp `defineClass` cùng tên trong một loader là cách cập nhật class.” | Có thể gây `LinkageError`; hot reload thường cần loader mới hoặc cơ chế instrumentation phù hợp. |
| “`findLoadedClass` làm chạy static initializer.” | Nó không yêu cầu initialization hay tạo instance. |
| “Chỉ dùng `findLoadedClass` đủ để tránh race.” | Cần đồng bộ đúng chuỗi kiểm tra-nạp/định nghĩa, thường qua `getClassLoadingLock`. |
| “Parent trả về class thì child chắc chắn là defining loader.” | Defining loader là nơi thực sự định nghĩa class, thường là parent hoặc bootstrap trong tình huống delegation. |
| “Cache `Map<String,Class<?>>` tự thay thế được VM state.” | Map riêng không điều khiển JVM initiating-loader records hoặc class identity. |

## 14. Tự kiểm tra

**Câu 1.** `findLoadedClass("com.example.Task")` trả `null`. Có thể kết luận file `Task.class` không nằm trên class path không?

**Đáp án:** Không. Chỉ biết loader hiện tại chưa được JVM ghi nhận làm initiating loader cho binary name ấy; parent/loader khác có thể thấy được class.

**Câu 2.** Tại sao `findLoadedClass` là `protected final`?

**Đáp án:** Subclass sử dụng được trong logic nạp class, nhưng không thể override thay đổi ý nghĩa tra cứu trạng thái được JVM ghi nhận.

**Câu 3.** Một class được custom loader định nghĩa lần đầu bằng `defineClass`. Lần sau cùng loader yêu cầu lại, phương thức nào nên được dùng để kiểm tra class đã có?

**Đáp án:** `findLoadedClass(binaryName)`, dưới đồng bộ hóa thích hợp trong `loadClass`, sẽ giúp tái sử dụng `Class<?>`.

**Câu 4.** Hai loader độc lập định nghĩa `com.example.Task` với cùng bytes. `Class<?>` của chúng có bằng nhau không?

**Đáp án:** Không. Cùng binary name nhưng khác defining loader tạo hai runtime identities khác nhau.

**Câu 5.** `child.loadClass("java.lang.String")` trả `String.class`. `String.class.getClassLoader() == null` nghĩa gì?

**Đáp án:** `String` có defining loader là bootstrap trong cấu hình JDK thông thường. Không có nghĩa child loader đã tự định nghĩa `String`.

**Câu 6.** Điều gì nguy hiểm nếu hai thread cùng thấy `findLoadedClass(name) == null` rồi cùng gọi `defineClass`?

**Đáp án:** Có thể cố định nghĩa lặp cùng binary name ở một loader, dẫn đến lỗi liên kết. Cần lock thích hợp quanh toàn bộ đoạn kiểm tra và định nghĩa, hoặc dùng implementation `loadClass` mặc định.

**Câu 7.** `findLoadedClass` có đảm bảo class đã initialized không?

**Đáp án:** Không. Loading/recording và initialization là các giai đoạn khác nhau; phương thức chỉ tra cứu.

**Câu 8.** Vì sao trong `FindLoadedDemo` hai lần gọi `custom.loadClass("LocalPayload")` chỉ làm `definitions` tăng một lần?

**Đáp án:** Sau lần `defineClass` đầu, JVM ghi nhận class với loader đó. Lần thứ hai, `findLoadedClass` trả `Class<?>` đã có nên không đi vào `findClass`.

## 15. Ghi nhớ và tham khảo

- **`findLoadedClass(String)` là tra cứu:** trả class đã được VM ghi nhận theo **initiating loader**, hoặc `null`.
- **`loadClass` mặc định kiểm tra lớp đã nạp trước** rồi mới ủy quyền và gọi `findClass` nếu cần.
- **Tái sử dụng `Class<?>` là điều kiện của một loader nhất quán**, giúp tránh `defineClass` trùng cùng tên trong một defining loader.
- **Defining loader khác initiating loader:** class lấy từ parent thường có owner là parent; cần phân biệt kết quả lookup và nơi định nghĩa.
- **Thread-safety và lifecycle:** dùng `getClassLoadingLock` khi override `loadClass`; không coi `findLoadedClass` là công cụ initialization, garbage collection hay hot reload.

Tài liệu chính thức:

1. [Java SE 17 — ClassLoader.findLoadedClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#findLoadedClass(java.lang.String)): định nghĩa theo initiating loader và giá trị trả về.
2. [Java SE 17 — ClassLoader.loadClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#loadClass(java.lang.String,boolean)): thuật toán mặc định, `findLoadedClass`, parent delegation, `findClass` và synchronization.
3. [Java SE 17 — ClassLoader.getClassLoadingLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#getClassLoadingLock(java.lang.String)): khóa nạp lớp và parallel-capable loaders.
4. [JVMS 17 — 5.3 Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3): defining loader, initiating loader và class identity.
5. [JVMS 17 — 5.3.4 Loading Constraints](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.4): ràng buộc tính nhất quán kiểu giữa loaders.