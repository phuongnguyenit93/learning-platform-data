# Quan hệ parent là quan hệ đối tượng, không phải kế thừa lớp Java

Khi học cơ chế ủy quyền của **Java ClassLoader**, một nhầm lẫn rất dễ gặp là xem *parent class loader* như một lớp cha trong Java. Hai khái niệm này hoàn toàn khác nhau:

- **Parent của một class loader** là **một đối tượng `ClassLoader` khác** được tham chiếu để phục vụ cơ chế ủy quyền tìm lớp/tài nguyên. Có thể kiểm tra bằng `loader.getParent()`.
- **Superclass của một lớp Java** là **một kiểu Java** mà lớp đó khai báo kế thừa qua `extends` (hoặc kế thừa ngầm), được kiểm tra bằng `SomeLoader.class.getSuperclass()`.

Một đối tượng của lớp `PluginLoader` hoàn toàn có thể lấy **một đối tượng** của lớp `HostLoader` làm parent, **dù `PluginLoader` không kế thừa `HostLoader`**. Ngược lại, `ChildLoader extends BaseLoader` không tự động làm cho mọi instance của `BaseLoader` trở thành parent của instance `ChildLoader`.

Bài học này dùng thuật ngữ **quan hệ parent của loader instance** và **quan hệ kế thừa giữa Java classes** nhất quán, giải thích cách chúng ảnh hưởng đến `loadClass`, và đưa ra các chương trình Java 17+ có thể chạy để kiểm chứng.

## 1. Hai sơ đồ khác nhau

### 1.1. Cây kiểu Java (inheritance / type hierarchy)

```text
java.lang.Object
      │
      └── java.lang.ClassLoader
                 ├── HostLoader
                 └── PluginLoader
```

Ví dụ: `HostLoader extends ClassLoader` và `PluginLoader extends ClassLoader`. Hai lớp này cùng kế thừa `ClassLoader`; **không** có quan hệ `PluginLoader extends HostLoader`.

Sơ đồ trên mô tả:

- `PluginLoader` có thể thừa hưởng các API từ `ClassLoader` như `loadClass`, `getParent` và những phương thức `protected` liên quan.
- Một instance `PluginLoader` có kiểu `PluginLoader`, đồng thời là `ClassLoader` và `Object`.
- Tính hợp lệ của phép gán/ép kiểu trong Java phụ thuộc type hierarchy này.
- Thay đổi tham chiếu `parent` của loader **không thể thay đổi superclass** của Java class đang được định nghĩa.

### 1.2. Chuỗi các đối tượng class loader (delegation / object graph)

```text
pluginLoader (instance của PluginLoader)
      │ getParent()
      ▼
hostLoader   (instance của HostLoader)
      │ getParent()
      ▼
platformLoader (instance của built-in platform class loader)
      │ getParent()
      ▼
bootstrap loader (thường được biểu diễn bằng null trong Java)
```

Sơ đồ này mô tả những **đối tượng đang tồn tại tại runtime**. Kết nối `pluginLoader.getParent() == hostLoader` được thiết lập bằng constructor của `ClassLoader`, không bằng từ khóa `extends`.

Hai sơ đồ có thể tồn tại đồng thời nhưng trả lời **hai câu hỏi khác nhau**:

| Câu hỏi | Hỏi về | API/biểu thức |
| --- | --- | --- |
| "`PluginLoader` kế thừa lớp nào?" | Kiểu Java, lúc viết/biên dịch chương trình | `PluginLoader.class.getSuperclass()` |
| "Đối tượng `pluginLoader` ủy quyền cho loader nào?" | Quan hệ giữa các instance, lúc chạy | `pluginLoader.getParent()` |
| "Đối tượng `pluginLoader` thuộc kiểu nào?" | Runtime class của chính loader object | `pluginLoader.getClass()` |
| "`Class<?>` của `demo.Item` được loader nào định nghĩa?" | Định danh runtime của **lớp được nạp** | `itemClass.getClassLoader()` |
| "Một loader có thể tìm thấy lớp này không?" | Class lookup/delegation | `loader.loadClass("demo.Item")` |

**Đặc biệt tránh nhầm:** `ClassLoader.getParent()` gọi trên **loader object**, còn `Class.getSuperclass()` gọi trên **Class object**. Trùng từ "parent/cha" trong cách giải thích đời thường không làm chúng trở thành một quan hệ.

## 2. `extends` xác định lớp cha, còn constructor xác định parent object

Hãy so sánh ba đoạn mã:

```java
class HostLoader extends ClassLoader {
    HostLoader(ClassLoader parent) {
        super(parent);
    }
}

class PluginLoader extends ClassLoader {
    PluginLoader(ClassLoader parent) {
        super(parent);
    }
}
```

Đây là **các khai báo minh họa**; để chạy độc lập xem ví dụ đầy đủ ở phần 4. Chúng có hai dạng quan hệ:

1. `extends ClassLoader` xác định **superclass của kiểu** `HostLoader` và `PluginLoader`. Quyết định này nằm trong khai báo class, được compiler ghi vào class file và là một phần của cấu trúc kiểu Java.
2. `super(parent)` gọi **constructor của `ClassLoader`** và chuyển **tham chiếu đến một loader instance** làm parent cho instance đang được tạo. Không phải "chọn superclass" bằng tham số.

Ví dụ về cách tạo instance:

```java
ClassLoader platform = ClassLoader.getPlatformClassLoader();
HostLoader host = new HostLoader(platform);
PluginLoader plugin = new PluginLoader(host);
```

Kết quả về quan hệ:

```text
host.getParent()   == platform     → true
plugin.getParent() == host         → true

host.getClass().getSuperclass()    → ClassLoader.class
plugin.getClass().getSuperclass()  → ClassLoader.class
```

`plugin` không có kiểu `HostLoader`. **`HostLoader.class.isInstance(plugin)` trả `false`**, dù đối tượng `host` là parent của `plugin`.

Một constructor chứa tham số `ClassLoader parent` cho phép parent có **bất kỳ subclass `ClassLoader` thích hợp** nào — thường là built-in system/platform loader hoặc một loader tùy biến. Java kiểm tra kiểu tham số `ClassLoader`; nó không yêu cầu "instance parent có class là superclass của class con".

## 3. Ba constructor của `ClassLoader` và ý nghĩa tham số parent

Trên Java 17+, `java.lang.ClassLoader` có các constructor `protected` thường dùng:

| Constructor | Parent được chọn | Khi nào dùng |
| --- | --- | --- |
| `ClassLoader()` | `ClassLoader.getSystemClassLoader()` | Loader tùy biến dùng parent mặc định là system loader. |
| `ClassLoader(ClassLoader parent)` | Đúng đối tượng `parent` truyền vào | Cần điều khiển rõ chuỗi delegation. |
| `ClassLoader(String name, ClassLoader parent)` | Parent truyền vào; đồng thời đặt **tên loader** | Muốn đặt tên hỗ trợ chẩn đoán trên Java 9+. |

**`parent == null`** thường biểu diễn **bootstrap loader** làm parent trong cơ chế `ClassLoader` chuẩn, chứ không có nghĩa chọn một lớp cha Java là `null`. Từ Java 9 trở đi, không bảo đảm mọi platform class đều nhìn thấy qua bootstrap; nếu cần Java platform APIs rộng hơn, cân nhắc `ClassLoader.getPlatformClassLoader()`.

Một số chi tiết cần nhớ:

- `ClassLoader.getParent()` là phương thức **`final`** trong JDK API: subclass không override phương thức này để giả mạo parent được trả về.
- Không có API công khai `setParent(...)` để đổi parent tùy ý sau khi tạo loader. Hãy thiết kế quan hệ khi xây dựng instance.
- `ClassLoader` vẫn là **lớp có thể kế thừa**: chương trình viết một subclass rồi override `findClass` để hỗ trợ nguồn class bytes riêng.
- `ClassLoader(String name, ClassLoader parent)` đặt **tên của loader instance**; tên này không phải tên Java class và không phải binary name của lớp nó nạp.
- Một số JVM có security-manager checks trong API tạo/kiểm tra loader; điều này không làm thay đổi sự phân biệt giữa hai quan hệ.

### `super(parent)` không đồng nghĩa parent là superclass

Trong constructor:

```java
PluginLoader(ClassLoader parent) {
    super(parent);
}
```

`super(...)` về mặt **ngôn ngữ Java** luôn gọi một constructor của **superclass** `ClassLoader`, nên từ `super` ở đây là cú pháp kế thừa. Nhưng **đối số `parent`** chính là **loader object** sẽ được `ClassLoader` giữ để ủy quyền. Vì cùng dòng có cả hai khái niệm, nó rất dễ gây nhầm.

Đọc câu này đúng là: "Gọi constructor của Java superclass `ClassLoader`, truyền vào tham chiếu parent loader mà ta muốn instance mới sử dụng." Không phải: "biến đối tượng được truyền thành superclass của `PluginLoader`."

## 4. Thực hành A — hai lớp loader không kế thừa nhau vẫn tạo quan hệ parent

Tạo một tệp Java duy nhất:

```text
parent-object-lab/
└── src/
    └── demo/
        └── ParentVsInheritance.java
```

**`src/demo/ParentVsInheritance.java`:**

```java
package demo;

public class ParentVsInheritance {

    static final class HostLoader extends ClassLoader {
        HostLoader(ClassLoader parent) {
            super(parent);
        }
    }

    static final class PluginLoader extends ClassLoader {
        PluginLoader(ClassLoader parent) {
            super(parent);
        }
    }

    public static void main(String[] args) {
        ClassLoader platform = ClassLoader.getPlatformClassLoader();
        HostLoader host = new HostLoader(platform);
        PluginLoader plugin = new PluginLoader(host);

        System.out.println("plugin parent is host: " +
                (plugin.getParent() == host));
        System.out.println("host parent is platform: " +
                (host.getParent() == platform));
        System.out.println("plugin is HostLoader: " +
                HostLoader.class.isInstance(plugin));
        System.out.println("same Java superclass: " +
                (host.getClass().getSuperclass()
                        == plugin.getClass().getSuperclass()));
        System.out.println("superclass is ClassLoader: " +
                (PluginLoader.class.getSuperclass() == ClassLoader.class));
    }
}
```

Dùng JDK 17+ từ thư mục `parent-object-lab`:

```sh
javac --release 17 -d out src/demo/ParentVsInheritance.java
java -cp out demo.ParentVsInheritance
```

**Stdout chính xác:**

```text
plugin parent is host: true
host parent is platform: true
plugin is HostLoader: false
same Java superclass: true
superclass is ClassLoader: true
```

**Tại sao dòng thứ ba là `false`?** `plugin` là instance của `PluginLoader`, vốn chỉ `extends ClassLoader`. Quan hệ `plugin.getParent() == host` không tạo thêm quan hệ `PluginLoader extends HostLoader`.

**Tại sao dòng thứ tư là `true`?** Cả hai Java classes kế thừa trực tiếp `ClassLoader`. So sánh `getSuperclass()` so sánh các đối tượng `Class<?>` biểu diễn **kiểu cha**, chứ không so sánh loader parent.

**Vì sao dùng `HostLoader.class.isInstance(plugin)`?** Nó minh họa kiểm tra kiểu tại runtime an toàn cho hai lớp anh em. Không cần viết một phép cast bất hợp lệ từ `PluginLoader` sang `HostLoader`.

**Lưu ý:** Hai subclasses chưa override `findClass` nên chỉ giúp minh họa *parent object*, chưa tự tải bytecode đặc biệt. Khả năng ủy quyền vốn có được thừa hưởng từ `ClassLoader`.

## 5. Thực hành B — hai đối tượng cùng một Java class vẫn là parent và child

Một nhầm lẫn ngược lại là cho rằng phải có **hai Java subclasses khác nhau** để có quan hệ parent/child. Không cần: chỉ cần **hai instance** có liên kết phù hợp.

Tạo `src/demo/SameTypeChain.java`:

```java
package demo;

public class SameTypeChain {

    static final class NamedLoader extends ClassLoader {
        NamedLoader(String name, ClassLoader parent) {
            super(name, parent);
        }
    }

    public static void main(String[] args) {
        ClassLoader platform = ClassLoader.getPlatformClassLoader();

        NamedLoader first = new NamedLoader("first", platform);
        NamedLoader second = new NamedLoader("second", first);

        System.out.println("same class: " +
                (first.getClass() == second.getClass()));
        System.out.println("different objects: " + (first != second));
        System.out.println("second parent is first: " +
                (second.getParent() == first));
        System.out.println("first parent is platform: " +
                (first.getParent() == platform));
        System.out.println("names: " +
                first.getName() + ", " + second.getName());
    }
}
```

Từ thư mục thực hành chứa `src`:

```sh
javac --release 17 -d out src/demo/SameTypeChain.java
java -cp out demo.SameTypeChain
```

**Stdout chính xác:**

```text
same class: true
different objects: true
second parent is first: true
first parent is platform: true
names: first, second
```

`first` và `second` đều có Java class là `NamedLoader`; **không có khái niệm "`second` extends `first`"**, vì `extends` áp dụng cho kiểu chứ không áp dụng cho hai object.

Hai đối tượng cùng class cũng có thể là **hai sibling loaders** nếu cùng dùng platform làm parent. Quan hệ object parent được lựa chọn **cho từng instance**, không tự sinh từ tên class hay cách khai báo class.

Sự khác nhau này là thiết yếu khi một ứng dụng tạo một loader instance cho **mỗi plugin/version/tenant**. Một subclass loader duy nhất có thể tạo nhiều namespace độc lập vì mỗi instance định nghĩa các class khác nhau.

## 6. Parent được dùng thế nào trong cơ chế ủy quyền nạp lớp?

Đối với các subclass dùng triển khai mặc định của `ClassLoader.loadClass(String, boolean)`, hành vi tổng quát gồm ba bước:

1. Kiểm tra `findLoadedClass(name)` để xem lớp theo tên ấy đã được loader ghi nhận là loaded trước đó chưa.
2. Nếu chưa, thử `parent.loadClass(name)`; khi parent là `null`, cơ chế của VM được sử dụng để tra cứu qua bootstrap.
3. Nếu parent không tìm được, gọi `findClass(name)` của chính loader. Nếu tìm thấy và tham số `resolve` là `true`, yêu cầu liên kết bằng `resolveClass`.

Ví dụ luồng điển hình:

```text
plugin.loadClass("demo.Feature")
          │
          ├── findLoadedClass("demo.Feature") ?
          │       └── có → trả về Class<?> đã biết
          │
          └── plugin.getParent() là host
                     │
                     └── host.loadClass("demo.Feature")
                               ├── host/ancestor tìm thấy → trả về
                               └── không tìm thấy → thử
                                   plugin.findClass("demo.Feature")
                                               │
                                       tự định nghĩa hoặc
                                       ClassNotFoundException
```

**Điểm cốt lõi:** Việc tìm **parent để gọi `loadClass`** dựa vào **trường tham chiếu của loader object**, không dùng `getSuperclass()` để tìm Java class của parent. Mã triển khai inherited `loadClass` trong `ClassLoader` vẫn có thể gọi một **đối tượng** `HostLoader` làm parent của instance `PluginLoader`.

Quan hệ `extends` chỉ quyết định **mã Java được thừa hưởng/override**. Ví dụ subclass `PluginLoader` có thể override `findClass` để đọc bytecode từ plugin JAR, còn parent object `host` có thể là subclass hoàn toàn khác dùng cơ chế tra cứu riêng.

**Không đồng nhất:** "parent không tìm thấy" chỉ là kết quả lookup phù hợp để fallback `findClass`. Một lỗi `LinkageError`, `SecurityException` hoặc bytecode không hợp lệ không phải lúc nào cũng là `ClassNotFoundException` được phép bỏ qua rồi thử vô điều kiện.

### Parent-first là hành vi mặc định, không phải định nghĩa của `extends`

Triển khai mặc định của `ClassLoader` là **parent-first delegation**. Subclass có thể override `loadClass` để triển khai chiến lược khác, nhưng phải kiểm soát concurrency, type identity, package/module constraints, protected JDK classes và tính nhất quán với resource loading. Javadoc khuyến nghị subclass thường **override `findClass`** thay vì tự viết lại toàn bộ `loadClass`.

Trên JDK 9+, các built-in loaders còn có cơ chế tương tác với **JPMS**; một vài trường hợp upgraded module khiến việc tìm lớp không khớp với một sơ đồ parent chain tuyến tính tuyệt đối. Ví dụ trong bài nhằm giải thích **quan hệ object parent của custom `ClassLoader` sử dụng mặc định**, không giả định mọi class loader trong thế giới Java đều tuân thủ đúng một thuật toán.

## 7. Thực hành C — quan sát parent-first và `findClass` bằng log có kiểm soát

Tạo `src/demo/DelegationTrace.java`:

```java
package demo;

public class DelegationTrace {

    static final class TracingLoader extends ClassLoader {
        TracingLoader(ClassLoader parent) {
            super(parent);
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            System.out.println("findClass called: " + name);
            throw new ClassNotFoundException(name);
        }
    }

    public static void main(String[] args)
            throws ClassNotFoundException {
        TracingLoader child =
                new TracingLoader(ClassLoader.getPlatformClassLoader());

        Class<?> stringClass = child.loadClass("java.lang.String");
        System.out.println("String reused: " +
                (stringClass == String.class));

        try {
            child.loadClass("demo.MissingForLesson");
        } catch (ClassNotFoundException expected) {
            System.out.println("missing class: " +
                    expected.getClass().getSimpleName());
        }
    }
}
```

Từ thư mục bài thực hành:

```sh
javac --release 17 -d out src/demo/DelegationTrace.java
java -cp out demo.DelegationTrace
```

**Stdout chính xác trên runtime Java 17+ thông thường:**

```text
String reused: true
findClass called: demo.MissingForLesson
missing class: ClassNotFoundException
```

Vì sao `findClass` **không in** khi nạp `java.lang.String`?

- `TracingLoader` dùng triển khai mặc định của `loadClass`.
- Parent được truyền là platform loader, vốn nhìn thấy `java.lang.String` qua bootstrap.
- Parent trả về lớp `String`. Loader con **không cần** gọi `findClass` cho tên này.
- `String.class.getClassLoader()` thường là `null`, do bootstrap định nghĩa; không có bản sao `String` tự định nghĩa trong `TracingLoader`.

Vì sao `findClass` **có in** cho `demo.MissingForLesson`?

- Không có class với tên ấy trên platform/ancestor trong cấu hình bài thực hành.
- Bước hỏi parent không tìm thấy, nên `loadClass` mặc định gọi `child.findClass(name)`.
- `findClass` chỉ in thông báo rồi ném `ClassNotFoundException`. Do đó đây là demo **quan sát fallback**, không phải custom bytecode loader hoàn chỉnh.

**Nội dung đã được JVM nạp ở bước nào?** Không thể suy ra một class được định nghĩa bởi loader nào chỉ vì có log "`findClass called`": `findClass` có thể thất bại. Khi thực sự nhận được `Class<?>`, kiểm tra `result.getClassLoader()` để xem **defining loader**.

## 8. Ba "cha/con" dễ bị lẫn trong một ứng dụng

Khi đọc code framework, thường có ít nhất ba quan hệ khác nhau:

### 8.1. Java class inheritance

```java
class BaseLoader extends ClassLoader { }

class SpecializedLoader extends BaseLoader { }
```

Đây là **hai class declarations minh họa**, không phải chương trình độc lập. Quan hệ kiểu là:

```text
SpecializedLoader.class.getSuperclass() == BaseLoader.class
```

Kế thừa cho phép `SpecializedLoader` tái sử dụng hoặc override hành vi của `BaseLoader`. **Không tự động tạo một object `BaseLoader` làm parent** khi tạo `SpecializedLoader`. Nếu constructor không gọi `super(parent)` theo thiết kế riêng và cuối cùng dùng constructor không tham số của `ClassLoader`, parent có thể là system loader mặc định.

### 8.2. Parent delegation giữa loader instances

```java
ClassLoader root = ClassLoader.getPlatformClassLoader();
ClassLoader child = new ClassLoader(root) { };
```

Đây là đoạn code hợp lệ có thể đặt trong `main`. `child.getParent() == root`, dù kiểu runtime của `child` là một anonymous subclass `ClassLoader`. Parent object là kết nối được chỉ định ở constructor, không phải superclass.

### 8.3. Java object được nạp và Java superclass của nó

Giả sử có class nghiệp vụ:

```java
class Animal { }
class Dog extends Animal { }
```

Việc `Dog.class.getSuperclass() == Animal.class` nói về **kế thừa của domain classes `Dog`/`Animal`**. Nó không cho biết `Dog.class.getClassLoader().getParent()` là gì.

Nói cách khác:

- `Dog.class.getSuperclass()` trả về `Class<Animal>`.
- `Dog.class.getClassLoader()` trả về **loader đã định nghĩa `Dog`**, hoặc `null` nếu bootstrap.
- `Dog.class.getClassLoader().getParent()` (khi loader khác `null`) trả về **parent của defining loader**, không phải loader định nghĩa `Animal` nhất thiết.

Hai class có quan hệ `extends` hoàn toàn có thể được **cùng một class loader** định nghĩa, hoặc được định nghĩa bởi các loaders khác nhau nhưng vẫn đáp ứng các quy tắc type safety và loader constraints. Đừng suy luận rằng "superclass của `Dog`" phải do "parent loader của loader nạp `Dog`" định nghĩa.

## 9. Định danh lớp runtime cũng phụ thuộc loader instance, không phụ thuộc subclass name

JVM xem một class/interface runtime được xác định bởi **(binary name, defining loader)**. Điều này kết nối trực tiếp với bài học:

- Hai **loader instances cùng một Java class** vẫn có thể định nghĩa **hai lớp runtime khác nhau** có cùng binary name.
- Hai loader instances **khác Java subclass** vẫn có thể cùng truy cập **một lớp runtime** nếu chúng ủy quyền và nhận về cùng `Class<?>` đã được parent định nghĩa.
- Chỉ so `loaderA.getClass() == loaderB.getClass()` **không đủ** để xác định hai loader instances là cùng một namespace.
- Chỉ so `classA.getName().equals(classB.getName())` **không đủ** để xác định hai runtime types là một; nên so `classA == classB` hoặc dùng `isAssignableFrom` phù hợp.

Ví dụ minh họa bằng sơ đồ:

```text
NamedLoader #1                   NamedLoader #2
(Java class giống nhau)          (Java class giống nhau)
    │ define "plugin.Task"           │ define "plugin.Task"
    ▼                                ▼
Class<?> task1                   Class<?> task2

task1.getName() == task2.getName()    → cùng tên
task1 == task2                        → false (nếu cả hai tự định nghĩa)
```

Đây là **mô hình khái niệm**: hai loader trong ví dụ B chưa tự thực hiện `defineClass`. Để minh họa cách ly thật cần triển khai `findClass`/`defineClass` hoặc dùng các loaders biết đọc JAR, xử lý dependency, package constraints và vòng đời. Không coi sơ đồ là stdout từ ví dụ B.

**Cảnh báo thuật ngữ:** *initiating loader* là loader được dùng để yêu cầu nạp; *defining loader* là loader đã định nghĩa class. Nếu `child.loadClass("java.lang.String")` trả về `String.class` qua parent, defining loader vẫn có thể là bootstrap. `child` là điểm gọi API không tự nhiên trở thành defining loader.

## 10. Hậu quả thực tế khi thiết kế plugin và application server

### 10.1. Chọn parent theo API cần chia sẻ

Trong plugin system, giả sử host định nghĩa interface `com.example.spi.Plugin`. Một plugin implementation cần được nhận diện là subtype của interface **mà host đang dùng**.

Nếu plugin dùng một loader với parent là application/system loader (hoặc một shared-API loader khác), cả host và plugin có thể nhìn cùng `Class<?>` cho interface SPI. Nếu plugin tự định nghĩa bản sao của interface cùng tên, cast sang interface host có thể thất bại.

Điều quan trọng là lựa chọn **parent object và class lookup policy** để duy trì **cùng định danh interface runtime**. Việc tạo một subclass loader tên `PluginClassLoader` hay `HostClassLoader` không tự xử lý vấn đề đó.

### 10.2. Vì sao không tạo parent relationship dựa vào Java superclass?

Giả sử viết:

```java
class PluginLoader extends HostLoader { }
```

Khi ấy `PluginLoader` kế thừa code của `HostLoader`. Điều này **không tự bảo đảm** nó hỏi một **instance `HostLoader` riêng** trước khi tìm class. Muốn có quan hệ ấy phải truyền/thiết lập đúng object parent qua constructor.

Ngược lại, nếu muốn plugin có hành vi khác host, việc `extends HostLoader` có thể kéo theo code và state không mong muốn. Một lựa chọn khác là:

```java
class PluginLoader extends ClassLoader {
    PluginLoader(ClassLoader hostLoader) {
        super(hostLoader);
    }
}
```

Đây là lựa chọn về **thiết kế API và composition**, còn cơ chế ủy quyền được quyết định bởi object parent và hành vi `loadClass`. Đoạn class ở đây chỉ minh họa constructor, chưa đầy đủ mã nạp plugin.

### 10.3. Chọn platform, system hay custom loader làm parent?

| Parent object | Tác dụng thường thấy | Giới hạn cần nhớ |
| --- | --- | --- |
| `ClassLoader.getPlatformClassLoader()` | Có thể nhìn thấy các lớp nền tảng, ít phụ thuộc ứng dụng hơn | Không mặc nhiên thấy mọi class trong application classpath, đặc biệt shared SPI. |
| `ClassLoader.getSystemClassLoader()` | Thường nhìn thấy classpath của ứng dụng và nền tảng | Có thể ưu tiên dependency của host thay vì bản plugin cần cách ly. |
| Một shared-API loader tùy biến | Chia sẻ các kiểu giao tiếp đã chủ định | Phải thiết kế chính xác loader nào nạp API nào. |
| `null` trong constructor loader | Sử dụng bootstrap cho delegation mặc định | Từ Java 9 không bảo đảm thấy toàn bộ platform APIs. |

Không có lựa chọn tuyệt đối cho mọi plugin. Phải xác định trước những class nào **bắt buộc dùng chung runtime identity** và những class nào được phép cô lập.

### 10.4. Không nên thay parent động

`getParent()` là `final`, và parent được thiết lập trong quá trình tạo loader. Thiết kế đổi parent bất ngờ có thể vi phạm giả định đã dùng để resolve classes, nhất quán resource lookup và loading constraints. Nếu cần lớp dependency mới hoặc vòng đời plugin mới, cân nhắc tạo loader instance mới theo kiến trúc và quản lý tham chiếu/vòng đời cẩn thận.

Việc tạo loader instance mới **không có nghĩa Java class của loader được định nghĩa lại**. `PluginLoader.class` có thể vẫn là một `Class<?>` duy nhất, trong khi có hàng chục instance của nó đang nạp các tập plugin khác nhau.

## 11. Phân biệt parent loader với superclass loader và context loader khi debug

Một đoạn kiểm tra hữu ích trong một chương trình đã có `loader` và `loadedType`:

```java
System.out.println(loader.getClass().getName());
System.out.println(loader.getClass().getSuperclass());
System.out.println(loader.getParent());
System.out.println(loadedType.getClassLoader());
System.out.println(Thread.currentThread().getContextClassLoader());
```

Đây là **snippet minh họa**, chỉ biên dịch sau khi khai báo `ClassLoader loader` và `Class<?> loadedType`. Các dòng lần lượt hỏi:

1. **Java type cụ thể** của loader object.
2. **Java superclass** của kiểu loader.
3. **Parent object** cho delegation.
4. **Defining loader của một class đã nạp** (không nhất thiết bằng `loader` đang thử load).
5. **Thread Context Class Loader (TCCL)** của thread hiện tại — một tham chiếu loader phục vụ nhiều API discovery, không nhất thiết là parent của `loader`.

TCCL có thể được framework thay đổi theo thread; ví dụ một số overloads của `ServiceLoader.load(...)` sử dụng context loader để tìm providers. Nó **không tự thay đổi `getParent()`** của bất kỳ loader instance nào.

**Không nhầm `getClassLoader()` với `getClass().getClassLoader()`:**

- Với một đối tượng loader `myLoader`, `myLoader.getClass().getClassLoader()` trả về **loader đã định nghĩa Java class `MyLoader`**.
- Với một class nghiệp vụ `MyFeature.class`, `MyFeature.class.getClassLoader()` trả về loader định nghĩa **`MyFeature`**.
- `myLoader.getParent()` trả về object parent dùng cho **delegation từ `myLoader`**.

Tất cả cùng dùng từ "loader" nhưng nói về **ba đối tượng/quan hệ** khác nhau.

## 12. Các lỗi lập trình phổ biến

| Sai lầm | Vì sao sai | Cách suy nghĩ đúng |
| --- | --- | --- |
| "`PluginLoader extends ClassLoader` nên parent của nó là `ClassLoader.class`" | Parent là một **object**, `ClassLoader.class` là đối tượng mô tả kiểu | Parent được constructor chọn, kiểm tra qua `getParent()`. |
| "`PluginLoader extends HostLoader`, vậy parent của plugin instance là host instance" | Kế thừa chỉ xác định superclass/các method nhận được | Phải truyền host object nếu muốn delegation qua nó. |
| "`loader.getParent()` trả `null` thì loader không thể nạp JDK classes" | `null` thường biểu diễn bootstrap lookup | Nhưng có thể thiếu platform-defined classes trên JDK hiện đại. |
| "Hai loader cùng Java class nên có cùng loaded classes" | Mỗi instance có trạng thái/namespaces nạp lớp riêng | So `Class<?>` và defining loader thực tế. |
| "Loader `L` trả về `Foo.class` nên `L` đã define `Foo`" | Parent có thể định nghĩa và trả về | Xem `Foo.class.getClassLoader()`. |
| "Parent-first đi tìm Java superclass của loader rồi gọi `loadClass`" | Không phải lookup theo type hierarchy | Tìm **parent loader object**, gọi phương thức trên object ấy. |
| "`getParent() == null` nghĩa là root của toàn JVM không còn tìm nơi nào khác" | Bootstrap là cơ chế VM built-in, và built-in/module loaders có quy tắc riêng | Xem đặc tả loader và phiên bản JDK. |
| "Có thể sửa `parent` tùy lúc để thay JAR runtime" | Không có setter công khai, runtime linkage/type identity đã được tạo | Thiết kế lifecycle loader/module layer riêng. |
| "Cứ override `loadClass` để sửa thứ tự" | Dễ làm sai đồng bộ, cache, delegation và package/JDK class rules | Thường override `findClass` và dùng mặc định `loadClass`, trừ khi có yêu cầu rõ. |
| "`Thread.currentThread().getContextClassLoader()` chính là `getParent()`" | TCCL và parent phục vụ mục đích khác | Đọc riêng cả hai trong debug. |

### Lỗi dễ gây hiểu nhầm khi đọc stacktrace

- `ClassNotFoundException`: một loader không tìm thấy lớp với tên yêu cầu. Kiểm tra **loader instance thực sự được hỏi** và parent chain của nó; class có trong JAR của ứng dụng không có nghĩa platform parent nhìn thấy.
- `NoClassDefFoundError`: JVM cần class nhưng không thể định nghĩa/sử dụng; có thể do dependency hoặc lỗi initialization trước đó, nên cần đọc `Caused by`.
- `ClassCastException` giữa hai lớp **cùng tên**: có thể do hai defining loader instances khác nhau đã tạo hai kiểu runtime. Không chữa bằng cách thay `extends` của loader.
- `LinkageError`: có thể xuất phát từ loading constraints, binary API mismatch hoặc lỗi liên kết khác. Cần kiểm tra loader identity, classpath/module path và descriptor trước khi đoán nguyên nhân.

Việc nhận biết đúng **loại quan hệ** thường rút ngắn quá trình debug hơn việc chỉ nhìn tên class loader in trong log.

## 13. Một sơ đồ tổng hợp áp dụng cho hệ plugin

Giả sử có hai đối tượng của hai Java classes khác nhau:

```text
                    JAVA TYPE HIERARCHY
                              Object
                                 │
                            ClassLoader
                              /     \
                     HostLoader   PluginLoader

                    RUNTIME OBJECT GRAPH
              platformLoader
                    ▲
                 parent
                    │
              hostInstance : HostLoader
                    ▲
                 parent
                    │
              pluginInstance : PluginLoader

                    LOADING EXAMPLE
pluginInstance.loadClass("java.lang.String")
       → hostInstance
       → platformLoader
       → bootstrap finds/defines String
       → trả về cùng String.class
```

Trong sơ đồ:

- Dấu nối giữa `HostLoader` và `PluginLoader` ở phía type hierarchy đi qua **`ClassLoader`**: đây là hai Java subclasses anh em.
- Mũi tên trong object graph là kết quả của **tham chiếu parent được truyền vào constructor**.
- `pluginInstance` gọi `loadClass` không khiến `String` do `PluginLoader` định nghĩa.
- Trong một lần lookup khác, nếu parent không tìm được một plugin class, một `PluginLoader.findClass` có triển khai thật mới có thể tự định nghĩa class ấy.
- Nếu custom loader muốn dùng parent khác, chỉ việc chọn một object parent khác theo hợp đồng API; không cần thay `extends`.

## 14. Câu hỏi tự kiểm tra kèm đáp án

**1. Có thể tạo `PluginLoader` parent là `HostLoader` dù hai lớp không kế thừa nhau?** Có. Chúng chỉ cần cùng là `ClassLoader` hợp lệ; truyền instance `HostLoader` vào constructor `PluginLoader(ClassLoader parent)`.

**2. Hai instance của **cùng Java class** `NamedLoader` có tạo thành chuỗi parent được không?** Có. Ví dụ `new NamedLoader("second", first)` tạo quan hệ `second.getParent() == first`.

**3. `PluginLoader.class.getSuperclass()` có đổi khi truyền parent khác?** Không. Superclass do khai báo `extends` quyết định.

**4. Nếu `PluginLoader extends HostLoader` nhưng gọi constructor không tham số của `ClassLoader` qua các cấp, parent có mặc nhiên là một `HostLoader` object không?** Không. Constructor không tham số của `ClassLoader` đặt system loader làm parent theo API.

**5. `plugin.loadClass("java.lang.String")` trả về `String.class` có chứng minh `plugin` định nghĩa `String`?** Không. Parent/bootstrap có thể đã định nghĩa `String` và trả về.

**6. Muốn biết defining loader của `Foo.class` thì gọi gì?** `Foo.class.getClassLoader()`; giá trị `null` thường biểu diễn bootstrap.

**7. Muốn biết superclass của Java class chứa implementation loader thì gọi gì?** `loader.getClass().getSuperclass()`; không phải `loader.getParent()`.

**8. Vì sao override `findClass` thường an toàn hơn override `loadClass` để bổ sung khả năng đọc bytecode?** Nó giữ được cơ chế kiểm tra loaded class, parent-first delegation và phần đồng bộ của triển khai `loadClass` mặc định.

**9. Parent loader có phải là superclass của domain class mà loader đang nạp?** Không. Loader parent là quan hệ giữa **loader objects**; superclass của domain class là quan hệ giữa **Java types**.

**10. Hai loader cùng subclass nhưng khác instance có thể tạo hai `plugin.Task` không tương thích không?** Có, nếu mỗi loader tự định nghĩa một runtime class `plugin.Task` riêng; class identity phụ thuộc binary name và defining loader.

## 15. Nguồn chuẩn và nguyên tắc ghi nhớ

- [Java SE 17 `ClassLoader` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): các constructor, `getParent()`, `loadClass`, `findClass` và built-in loaders. Javadoc mô tả rõ "**Each instance of ClassLoader has an associated parent class loader**".
- [Java SE 17 `Class` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getSuperclass()`, `getClassLoader()`, `isInstance()`.
- [Java Virtual Machine Specification 17, Chapter 5: Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): vai trò loader, type identity, initiating/defining loader và linkage.
- [JDK 17 `ServiceLoader` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): ví dụ API có thể sử dụng thread context class loader, phân biệt với parent delegation.

**Cách nhớ chắc chắn nhất:**

> **`extends` nối các *kiểu Java*; `getParent()` nối các *đối tượng class loader*.** Constructor quyết định object parent; type declaration quyết định superclass. Cơ chế ủy quyền tra cứu dùng quan hệ object, còn kế thừa Java quyết định hành vi mà loader subclass nhận được từ superclass.

Khi gặp một bug classloading, luôn hỏi riêng ba câu: **"Instance loader nào đang được dùng?", "Parent *object* của nó là ai?", "Loader nào đã định nghĩa `Class<?>` được trả về?"** Trả lời xong mới dùng Java inheritance hierarchy để giải thích vì sao một loader có phương thức hoặc cách tra cứu cụ thể.
