# `Class.getClassLoader()`, `getParent()` và cách đặt tên class loader trong Java

Java cho phép nhiều bộ nạp lớp cùng tồn tại, ủy quyền cho nhau hoặc định nghĩa các kiểu riêng. Ba API thường được dùng để hiểu cấu trúc này:

- `Class.getClassLoader()`: xác định **loader đã định nghĩa kiểu** đang được đối tượng `Class<?>` đại diện.
- `ClassLoader.getParent()`: xác định **loader cha dùng để ủy quyền** của một instance `ClassLoader`.
- `ClassLoader.getName()`: lấy **tên chẩn đoán** của instance loader, nếu loader được đặt tên.

Ba API trả lời ba câu hỏi khác nhau. Đặc biệt, **loader cha không nhất thiết là loader định nghĩa một class**, và **tên loader không phải danh tính duy nhất của loader**.

Bài này thuộc chủ đề API nạp lớp; mục tiêu là đọc đúng runtime identity, quan hệ delegation, loader name và các trường hợp `null`. Các ví dụ áp dụng với Java 17+, đồng thời giải thích điểm khác biệt giữa Java platform, application/system loader và custom loader.

## 1. Mô hình ba lớp thông tin

```text
Class<?> type = Widget.class
       |
       | type.getClassLoader()
       v
Defining loader của Widget
       |
       | getParent()
       v
Parent loader dùng cho delegation
       |
       | getParent()
       v
... đến bootstrap loader (thường không có
     một object ClassLoader Java đại diện)

Mỗi ClassLoader instance:
    loader.getName() -> tên hoặc null
```

| API | Đối tượng gọi | Kiểu kết quả | Ý nghĩa |
|---|---|---|---|
| `Class.getClassLoader()` | `Widget.class`, `obj.getClass()` | `ClassLoader` hoặc `null` | Loader **đã định nghĩa** lớp/interface runtime |
| `ClassLoader.getParent()` | `someLoader` | `ClassLoader` hoặc `null` | Parent dùng cho delegation, không phải class loader của chính object `someLoader` |
| `ClassLoader.getName()` | `someLoader` | `String` hoặc `null` | Tên loader được đặt khi tạo, phục vụ nhận diện/chẩn đoán |
| `ClassLoader.getSystemClassLoader()` | ClassLoader API tĩnh | `ClassLoader` | System loader, thường là application loader |
| `ClassLoader.getPlatformClassLoader()` | ClassLoader API tĩnh | `ClassLoader` | Platform loader trong JVM hiện đại |

Một loader là **đối tượng Java**, và chính đối tượng ấy cũng có kiểu runtime. Do đó:

```java
ClassLoader loader = ClassLoader.getSystemClassLoader();
Class<?> loaderImplementationType = loader.getClass();

ClassLoader definingLoaderOfLoaderClass =
        loaderImplementationType.getClassLoader();
```

Dòng cuối hỏi **ai định nghĩa lớp triển khai loader**, khác với chính biến `loader` đang nắm giữ instance. Không được gộp hai ý nghĩa này.

## 2. `Class.getClassLoader()` trả về điều gì?

`java.lang.Class<T>` là biểu diễn một kiểu ở runtime. Với class hoặc interface thông thường, `getClassLoader()` cho biết **defining loader** của kiểu đó.

```java
Class<?> type = com.example.Widget.class;
ClassLoader definingLoader = type.getClassLoader();
```

Đây là đoạn minh họa, chỉ biên dịch độc lập khi `com.example.Widget` tồn tại và khả dụng. Nó **không** tìm tên lớp dưới dạng String và **không** tạo instance Widget. `Widget.class` cung cấp một `Class<?>` cho kiểu mà JVM đã nạp theo bối cảnh đang chạy.

### Defining loader khác initiating loader

Giả sử `PluginLoader` có parent là `AppLoader`:

```text
PluginLoader.loadClass("org.example.Api")
                    |
       parent-first delegation
                    v
AppLoader.loadClass("org.example.Api")
                    |
        AppLoader defines Api
                    |
                    v
          Class<org.example.Api>
```

Khi đó:

- Lời gọi bắt đầu ở `PluginLoader`.
- Loader thực sự **định nghĩa** `Api` là `AppLoader`.
- `apiClass.getClassLoader() == appLoader` là `true`.
- `apiClass.getClassLoader() == pluginLoader` là `false`.

Đó là hành vi bình thường của parent delegation. Không suy luận `getClassLoader()` từ biến mà ta đã gọi `loadClass(...)`. Nếu cần biết loader nào thực sự nhận yêu cầu, phải quan sát luồng gọi hoặc công cụ ghi log; `getClassLoader()` cho câu trả lời về **định nghĩa kiểu**.

### Vì sao defining loader quan trọng?

Trong JVM, danh tính của một class hoặc interface runtime phụ thuộc vào **tên nhị phân + defining loader**:

```text
Type identity = (binary name, defining class loader)
```

Hai loader khác nhau có thể tự định nghĩa cùng tên `org.example.Api`, tạo ra hai kiểu không tương thích dù in cùng `getName()`. Điều này giải thích những lỗi `ClassCastException` hoặc lỗi liên kết trong kiến trúc plugin/hot reload. Ngược lại, hai loader con cùng delegate về một defining loader ở cha sẽ cùng nhìn thấy một kiểu runtime.

Khi chẩn đoán:

```java
Class<?> actual = value.getClass(); // value khác null
System.out.println(actual.getName());
System.out.println(actual.getClassLoader());
```

Đây chỉ là mảnh minh họa; nếu `value == null` thì `value.getClass()` gây `NullPointerException`.

## 3. Vì sao `getClassLoader()` đôi khi trả `null`?

**`null` không có nghĩa lớp chưa được nạp.** Trong các JDK thông thường, bootstrap loader được JVM biểu diễn qua `null` thay vì một object `ClassLoader` Java.

```java
System.out.println(String.class.getClassLoader() == null);
System.out.println(Object.class.getClassLoader() == null);
```

Với Java 17+ chạy trên JDK thông thường, cả hai dòng in `true` vì `java.lang.String` và `java.lang.Object` là các lớp cốt lõi do bootstrap loader định nghĩa.

Tài liệu `Class.getClassLoader()` cũng nói rõ:

- Nếu `Class` biểu diễn **kiểu primitive** hoặc `void`, `getClassLoader()` trả `null`.
- Đối với một **array class**, Java runtime tự tạo array type khi cần. Loader của array class được báo cáo là loader của **kiểu phần tử cuối cùng** (*element type*); nếu phần tử là primitive, kết quả là `null`.
- `null` ở đây có thể biểu diễn bootstrap loader hoặc trường hợp kiểu primitive/`void` không có defining loader Java như class thông thường.

Ví dụ:

```java
String[].class.getClassLoader()        // thường null
int[][].class.getClassLoader()         // null
int.class.getClassLoader()             // null
void.class.getClassLoader()            // null
Widget[].class.getClassLoader()        // loader của Widget
Widget[][].class.getClassLoader()      // cùng loader của Widget
```

Đây là các biểu thức minh họa; hai dòng cuối yêu cầu có class `Widget` trong phạm vi truy cập. Đừng xem `Widget[].class` là một tệp `Widget[].class` được loader tự đọc từ đĩa; JVM tạo array class, còn loader trả về phản ánh element type.

### Phân biệt `Class.getClassLoader()` và `ClassLoader.getClass()`

Xét:

```java
Class<?> type = Widget.class;
ClassLoader a = type.getClassLoader();
ClassLoader b = type.getClass().getClassLoader();
```

- `a` là loader định nghĩa `Widget`.
- `type.getClass()` chính là `java.lang.Class.class`, bởi `type` bản thân nó là một object `Class`.
- `b` vì vậy hỏi loader định nghĩa **`java.lang.Class`**, thông thường là bootstrap loader (`null`).

Hai biểu thức này giải quyết hai câu hỏi khác nhau, và `a` có thể khác `b`.

## 4. `ClassLoader.getParent()`: mối quan hệ ủy quyền

`ClassLoader.getParent()` là instance method trả về **loader cha được sử dụng trong delegation**. Đối với `ClassLoader.loadClass(String, boolean)` mặc định, JVM/Java runtime thường tuân theo:

1. Kiểm tra một class đã được nạp theo thông tin loader hay chưa (`findLoadedClass`).
2. Thử ủy quyền cho parent; nếu parent là `null` thì dùng cơ chế bootstrap.
3. Nếu parent không tìm thấy, loader mới gọi `findClass` của mình.
4. Nếu `resolve=true` thì yêu cầu liên kết kiểu trả về.

Quy tắc trên mô tả **implementation mặc định** của `ClassLoader.loadClass`. Một subclass có thể tùy chỉnh `loadClass` hoặc các hook liên quan để hỗ trợ chiến lược khác. Không được suy luận rằng mọi loader của mọi framework đều phải parent-first tuyệt đối.

```text
NamedPluginLoader
     |
     | getParent()
     v
Application/System loader
     |
     v
Platform loader
     |
     v
Bootstrap (thường biểu diễn là null)
```

Sơ đồ trên là một kiến trúc phổ biến. Đừng xem nó như một định lý về mọi JVM hoặc mọi launcher: bộ nạp custom, classpath/module path và môi trường đóng gói có thể khác.

### `getParent() == null` nói gì?

`getParent()` có thể trả `null` khi parent là bootstrap loader trong cách biểu diễn của JVM. Nó **không** chứng minh current loader là bootstrap loader hoặc current loader không thể nạp lớp Java nền tảng.

Ví dụ `ClassLoader.getPlatformClassLoader().getParent()` thường là `null` trong kiến trúc JDK hiện đại, vì platform loader ủy quyền tới bootstrap. Bootstrap bản thân không phải một instance `ClassLoader` Java thông thường để gọi `getParent()`.

**Quan trọng:** Parent **không phải** superclass trong ngôn ngữ Java. Nếu `class NamedLoader extends ClassLoader`, parent của instance `NamedLoader` là tham số được truyền vào constructor, không phải `ClassLoader.class`. Một quan hệ là **instance delegation**, quan hệ còn lại là **class inheritance**.

### Parent không cho biết ai thực sự định nghĩa từng class

Khi gọi:

```java
ClassLoader loader = new MyLoader(ClassLoader.getSystemClassLoader());
Class<?> type = loader.loadClass("java.lang.String");
```

Đây là mảnh minh họa, cần định nghĩa `MyLoader` với constructor phù hợp. Với loader dùng delegation mặc định, `type.getClassLoader()` thường là `null` (bootstrap). `loader.getParent()` là system loader, không phải bootstrap. Cả hai kết quả đều đúng vì hỏi hai sự thật khác nhau.

## 5. Đặt tên class loader trong Java 9+

Từ Java 9, `ClassLoader` cung cấp protected constructor:

```java
protected ClassLoader(String name, ClassLoader parent)
```

Một subclass có thể gọi constructor này để tạo loader có tên:

```java
public final class NamedPluginLoader extends ClassLoader {
    public NamedPluginLoader(String name, ClassLoader parent) {
        super(name, parent);
    }
}
```

Đây là class hoàn chỉnh cần lưu thành `NamedPluginLoader.java` nếu biên dịch riêng, chưa phải một chương trình chạy có `main`. `name` có thể là `null` để tạo loader không đặt tên, nhưng **chuỗi rỗng** `""` không hợp lệ và gây `IllegalArgumentException`. Tên được truy xuất bằng `loader.getName()`.

Nếu muốn dùng default system loader làm parent:

```java
ClassLoader app = ClassLoader.getSystemClassLoader();
NamedPluginLoader plugin =
        new NamedPluginLoader("payments-plugin", app);
System.out.println(plugin.getName());          // payments-plugin
System.out.println(plugin.getParent() == app); // true
```

Code trên là mảnh minh họa có class `NamedPluginLoader` đã biên dịch.

### Tên loader dùng để làm gì?

Tên là metadata dành cho con người và công cụ chẩn đoán. Ví dụ `payments-plugin`, `script-runner`, `test-sandbox` có thể giúp log dễ đọc hơn, phân biệt loader trong dump hoặc quan sát vòng đời khi dự án có nhiều plugin.

Tuy nhiên:

- Tên **không bắt buộc duy nhất**; hai instance có thể cùng `getName()` nhưng vẫn là hai đối tượng loader khác nhau.
- Tên **không quyết định parent**; `getParent()` mới trả quan hệ delegation.
- Tên **không quyết định type identity**; JVM dùng chính **defining loader object**, không dùng chuỗi `getName()`.
- Đặt tên **không thay đổi** thuật toán `loadClass` hoặc khiến loader tìm thêm thư mục/JAR nào.
- `getName() == null` chỉ cho biết loader **không được đặt tên**; nó không chứng tỏ object là bootstrap loader.
- `getName()` không phải định danh bảo mật hoặc cơ chế cấp quyền; không nên dùng tên loader làm khóa phân quyền.

API `getName()` không phải `final` để tương thích ngược; nếu subclass override, theo tài liệu JDK nó **phải trả về đúng tên đã chỉ định khi loader được tạo**. Với chương trình thông thường, giữ implementation kế thừa đơn giản sẽ tránh sai lệch trong log.

### So sánh loader theo tên hay theo object?

```java
ClassLoader one = new NamedPluginLoader("plugin", parent);
ClassLoader two = new NamedPluginLoader("plugin", parent);

boolean sameName = one.getName().equals(two.getName()); // true
boolean sameObject = one == two;                        // false
```

Đây là mảnh minh họa, biến `parent` đã được cung cấp. Nếu xác định **hai class có defining loader giống nhau**, so sánh `classA.getClassLoader() == classB.getClassLoader()` (object identity), **không** so chuỗi tên loader.

Không cố ý override `equals()` để tạo cảm giác hai loader “bằng nhau”: JVM phân biệt defining loader bằng danh tính runtime thực của instance, không bằng một phép so sánh tên.

## 6. Ví dụ Java 17+ biên dịch và chạy được

Tạo một file **`LoaderApiDemo.java`** với mã nguồn dưới đây. Chương trình dùng các kiểm tra boolean để stdout không phụ thuộc tên class triển khai loader tích hợp trên từng JDK.

```java
public class LoaderApiDemo {
    static class Sample {
    }

    static final class NamedLoader extends ClassLoader {
        NamedLoader(String name, ClassLoader parent) {
            super(name, parent);
        }
    }

    public static void main(String[] args)
            throws ClassNotFoundException {
        ClassLoader app = LoaderApiDemo.class.getClassLoader();

        NamedLoader first = new NamedLoader("plugin-a", app);
        NamedLoader second = new NamedLoader("plugin-a", app);

        System.out.println("first name: " + first.getName());
        System.out.println("parent is app: " + (first.getParent() == app));
        System.out.println("same names: "
                + first.getName().equals(second.getName()));
        System.out.println("same loader instance: " + (first == second));

        Class<?> sample = first.loadClass(Sample.class.getName());

        System.out.println("delegated class identical: "
                + (sample == Sample.class));
        System.out.println("sample defined by app: "
                + (sample.getClassLoader() == app));
        System.out.println("sample defined by first: "
                + (sample.getClassLoader() == first));

        System.out.println("String bootstrap: "
                + (String.class.getClassLoader() == null));
        System.out.println("primitive null: "
                + (int.class.getClassLoader() == null));
        System.out.println("String array null: "
                + (String[].class.getClassLoader() == null));
        System.out.println("Sample array same defining loader: "
                + (Sample[].class.getClassLoader()
                   == Sample.class.getClassLoader()));

        System.out.println("Class mirror loader bootstrap: "
                + (Sample.class.getClass().getClassLoader() == null));
    }
}
```

Chạy từ thư mục chứa file với JDK 17+:

```bash
javac LoaderApiDemo.java
java LoaderApiDemo
```

**Stdout chuẩn khi chạy chương trình độc lập theo cách trên trên JDK thông thường:**

```text
first name: plugin-a
parent is app: true
same names: true
same loader instance: false
delegated class identical: true
sample defined by app: true
sample defined by first: false
String bootstrap: true
primitive null: true
String array null: true
Sample array same defining loader: true
Class mirror loader bootstrap: true
```

### Phân tích kết quả

1. `first.getName()` trả `plugin-a` vì constructor `NamedLoader(String, ClassLoader)` gọi `super(name, parent)`.
2. `first.getParent() == app` là `true` vì constructor sử dụng đúng parent đã truyền.
3. Hai loader cùng tên nhưng `first == second` là `false`. Chúng là **hai instance riêng biệt**.
4. `first.loadClass(Sample.class.getName())` sử dụng delegation mặc định. `Sample` thuộc mã ứng dụng hiện có nên parent `app` định nghĩa (hoặc đã định nghĩa) Sample và trả lại cho child.
5. Vì vậy `sample == Sample.class` là `true`, `sample.getClassLoader() == app` là `true`, còn `sample.getClassLoader() == first` là `false`.
6. `String.class` là class nền tảng của `java.base` được bootstrap loader phục vụ trong JDK thông thường; `int.class` biểu diễn primitive, nên cả hai cho `null` khi hỏi `getClassLoader()`.
7. `String[].class` có element type `String`, còn `Sample[].class` có element type `Sample`. Loader của array class được báo cáo theo element type.
8. `Sample.class.getClass()` là `java.lang.Class.class`. Lớp `java.lang.Class` do bootstrap định nghĩa nên biểu thức cuối là `true`.

Ví dụ **không nạp hai phiên bản riêng của `Sample`**. Nó minh họa parent delegation và so sánh bằng identity. Muốn child thực sự định nghĩa một bản riêng, phải có cơ chế `findClass`/`defineClass` hoặc loader thư viện được cấu hình bytecode riêng; điều này sẽ làm thay đổi đáp án identity.

### Một thử nghiệm bổ sung về loader không đặt tên

```java
NamedLoader unnamed = new NamedLoader(null, app);
System.out.println(unnamed.getName() == null);
```

Nếu thêm hai dòng này vào `main`, kết quả là `true`. Đây là biến thể **không thuộc stdout chuẩn bên trên**.

Ngược lại, `new NamedLoader("", app)` không phải cách tạo loader không tên: constructor cơ sở từ Java 9 sẽ ném `IllegalArgumentException` vì tên rỗng.

## 7. Các câu hỏi thường gặp khi thấy `null` hoặc loader lạ

### Vì sao `ClassLoader.getSystemClassLoader()` không bằng `SomeClass.class.getClassLoader()`?

System loader thường dùng để khởi động ứng dụng và là parent mặc định của nhiều custom loaders. Nhưng class có thể được định nghĩa bởi:

- bootstrap loader;
- platform loader;
- system/application loader;
- một loader riêng trong framework, plugin hoặc launcher.

Không thể lấy một system loader rồi cho rằng nó định nghĩa mọi class. Hãy kiểm tra trực tiếp `SomeClass.class.getClassLoader()`.

### Vì sao tên loader trùng nhau nhưng cast thất bại?

Vì hai instance có cùng tên vẫn là hai defining loader khác nhau. Nếu chúng tự định nghĩa cùng tên nhị phân của một interface/lớp, JVM coi hai định nghĩa là **hai kiểu khác nhau**. `ClassCastException` hoặc lỗi linkage có thể xuất hiện dù chuỗi class name và loader name trông giống nhau.

Log nên chứa cả thông tin class, class loader object/identity và module khi cần:

```java
Class<?> type = obj.getClass(); // obj != null
ClassLoader defining = type.getClassLoader();

System.out.println("class=" + type.getName());
System.out.println("loader=" + defining);
System.out.println("module=" + type.getModule());
```

Lưu ý: `toString()` của loader không phải một định danh duy nhất được bảo đảm qua các lần khởi động. Trong một tiến trình, hãy dùng identity/đối tượng `ClassLoader` thực tế để so sánh.

### `getParent()` có thể dùng để duyệt lên tới bootstrap không?

Có thể duyệt những object loader Java trong chuỗi parent:

```java
ClassLoader current = SomeClass.class.getClassLoader();

while (current != null) {
    System.out.println(current.getClass().getName()
            + " name=" + current.getName());
    current = current.getParent();
}
```

Đây là **mảnh minh họa**; cần `SomeClass` tồn tại. Vòng lặp kết thúc ở `null`, thường đại diện ranh giới bootstrap. Nó **không in một instance bootstrap loader Java**; bootstrap không nhất thiết là một object giống các subclass thông thường.

Nếu `SomeClass` do bootstrap định nghĩa, vòng lặp không chạy lần nào. Không dùng đoạn này để khẳng định có thể truy ngược tất cả loader tham gia bất kỳ thao tác tải lớp nào, nhất là khi implementation hỗ trợ ủy quyền không thuần chuỗi parent.

### `getParent()` có cho biết superclass của loader không?

Không. Phân biệt:

```java
Class<?> loaderClass = first.getClass();
Class<?> superclass = loaderClass.getSuperclass();
ClassLoader delegationParent = first.getParent();
```

- `superclass` là quan hệ **class inheritance**, ví dụ `ClassLoader.class`.
- `delegationParent` là **instance loader** nhận ủy quyền tìm class.
- `loaderClass.getClassLoader()` là loader **định nghĩa lớp triển khai NamedLoader**, một thông tin khác nữa.

Có thể trùng tên hoặc gần giống trong log nhưng không được coi các đại lượng này là một.

## 8. Tên loader và logging/diagnostics

Đặt tên có ý nghĩa giúp theo dõi multi-loader systems:

```text
PluginLoader("billing-plugin")
    parent -> AppLoader
    defines -> billing implementation classes

PluginLoader("reporting-plugin")
    parent -> AppLoader
    defines -> reporting implementation classes

AppLoader
    defines -> common public API
```

Giả định plugin API dùng chung được parent định nghĩa, hai plugin có thể giao tiếp qua API ấy mà không vô tình tạo hai bản của interface. Tên loader là thông tin **hỗ trợ theo dõi**; ranh giới định nghĩa thực phải kiểm tra bằng `Class.getClassLoader()`.

Khi phân tích `ClassCastException` trong plugin:

1. Thu thập tên binary của kiểu nguồn và kiểu đích.
2. Thu thập `getClassLoader()` của **từng** `Class` liên quan.
3. So loader object bằng `==`; xem cả parent chain bằng `getParent()` nếu cần.
4. Dùng `getName()` để log dễ hiểu hơn, không dùng nó làm tiêu chí cuối cùng cho type identity.
5. Kiểm tra delegation policy, JAR trùng, API chung bị plugin định nghĩa lại, hot reload hoặc việc giữ reference tới loader cũ.

Nếu đang làm việc với named modules (JPMS), thêm `Class.getModule()` vì module readability/exports cũng tác động tới quyền truy cập. Loader identity và module access giải quyết những vấn đề liên quan nhưng khác nhau.

### Quan sát tải lớp qua JVM

Ở HotSpot/JDK 17+:

```bash
java -Xlog:class+load=info LoaderApiDemo
```

Lệnh bật Unified Logging cho hoạt động nạp lớp. Dòng log và thời điểm hiển thị phụ thuộc implementation; không lấy nội dung log ấy làm stdout chuẩn ở phần demo.

Có thể sử dụng `jcmd` hoặc công cụ profiler để xem lớp/loader đã được JVM ghi nhận, tùy khả năng hỗ trợ của JDK/runtime và quyền truy cập tiến trình. Khi debug một môi trường thực, so sánh kết quả API trong tiến trình với log runtime, không suy đoán chỉ từ classpath.

## 9. Các bẫy thường gặp

**Bẫy 1 — `type.getClassLoader() == null` nghĩa là class chưa load.** Sai. Lớp bootstrap và các kiểu primitive/void có thể trả `null` theo API.

**Bẫy 2 — Một lớp có loader bằng loader đã gọi `loadClass`.** Sai khi delegation cho parent.

**Bẫy 3 — `loader.getParent()` là loader định nghĩa `loader.getClass()`.** Sai. Đó là parent delegation của **instance**; loader định nghĩa implementation class được lấy bằng `loader.getClass().getClassLoader()`.

**Bẫy 4 — `getParent() == null` nghĩa là loader không có cách nào nạp core Java classes.** Sai. Khi parent là `null`, implementation mặc định có thể dùng bootstrap lookup.

**Bẫy 5 — `getName()` chỉ có từ Java 17.** Sai. API đặt tên loader và `getName()` có từ **Java 9**, vì thế Java 17+ dùng được.

**Bẫy 6 — Đặt tên loader giống nhau tức cùng loader.** Sai. Danh tính runtime được xác định bởi đối tượng defining loader, không bởi label.

**Bẫy 7 — Một loader không tên là bootstrap loader.** Sai. `new NamedLoader(null, parent)` tạo một **instance loader thông thường** không tên.

**Bẫy 8 — `new ClassLoader(...)` tạo loader biết đọc thêm mọi JAR.** Sai. Một subclass mặc định chưa bổ sung cách tìm bytecode. Muốn tải từ nguồn mới cần triển khai `findClass`, dùng `URLClassLoader` đúng cấu hình, hoặc API tương ứng.

**Bẫy 9 — `Class.getClassLoader()` chính là `Class.class.getClassLoader()`.** Sai: một cái hỏi loader của **kiểu được đại diện**, cái kia hỏi loader của **java.lang.Class**.

**Bẫy 10 — Cứ dùng `loader.toString()` là có định danh toàn cục ổn định.** Sai. Log biểu diễn giúp chẩn đoán nhưng không phải hợp đồng ID xuyên tiến trình.

**Bẫy 11 — Parent chain luôn giải thích mọi đường nạp trong Java.** Sai. Custom loaders/framework có thể override delegation; tài liệu `loadClass` mô tả mặc định nhưng không cấm mọi chính sách khác.

**Bẫy 12 — Tên loader được quyết định từ tên class của loader.** Sai. `NamedLoader.class.getName()` và `instance.getName()` là hai chuỗi có chức năng khác nhau; tên instance do constructor loader nhận.

## 10. Tự kiểm tra

**Câu 1.** Loader A gọi `loadClass("p.Service")`, parent B định nghĩa `p.Service`. `Service.class.getClassLoader()` là A hay B?

**Đáp án:** B, vì API cho **defining loader** của kiểu. A có thể là initiating loader.

**Câu 2.** Hai loader đặt tên `"plugin"` và `"plugin"` có được coi là một loader không?

**Đáp án:** Không. Hai instance là hai đối tượng riêng trừ khi thực sự cùng tham chiếu một instance; so bằng `==` để kiểm tra identity.

**Câu 3.** `int.class.getClassLoader()` trả gì và vì sao?

**Đáp án:** `null`. Primitive type không được định nghĩa bởi một class loader Java theo cơ chế thông thường.

**Câu 4.** `Widget[][].class.getClassLoader()` khác `Widget.class.getClassLoader()` không?

**Đáp án:** Không, loader được báo cáo theo **element type Widget**. Cần phân biệt array class do JVM tự tạo và component/element class runtime.

**Câu 5.** `getParent()` trên instance loader tùy biến trả `null` có nghĩa instance ấy là bootstrap loader không?

**Đáp án:** Không. Một loader tùy biến vẫn có thể có parent `null` để hướng tới bootstrap delegation. Điều đó không biến nó thành bootstrap.

**Câu 6.** `ClassLoader(String name, ClassLoader parent)` nhận `name=""` có hợp lệ không?

**Đáp án:** Không, nó ném `IllegalArgumentException`. Dùng tên không rỗng hoặc `null` khi cố ý tạo loader không tên.

**Câu 7.** Khi debug `ClassCastException` do duplicate API giữa plugin loaders, `getName()` có đủ chứng minh hai kiểu cùng định nghĩa không?

**Đáp án:** Không. Cần so trực tiếp `Class<?>` và defining loader object, đồng thời kiểm tra binary name, delegation và module nếu phù hợp.

## 11. Quy tắc ghi nhớ

```text
Làm rõ kiểu runtime T:
  T.getClassLoader()       -> Ai định nghĩa T?

Làm rõ loader instance L:
  L.getParent()            -> L ủy quyền cho ai?
  L.getName()              -> L được đặt tên gì?

Kiểm tra hai kiểu có cùng defining loader:
  A.getClassLoader() == B.getClassLoader()

Kiểm tra một kiểu có thực sự là cùng runtime type:
  A == B (đối tượng Class<?>)

Không suy ra loader identity chỉ từ getName().
Không suy ra defining loader chỉ từ getParent().
Không coi null ở getClassLoader() là lớp chưa nạp.
```

Khi viết hoặc debug classloader, trình tự hữu ích là **kiểm tra `Class` của kiểu đích → lấy defining loader → xem parent chain → dùng tên loader làm nhãn trong log**. Trình tự này tránh nhầm lẫn giữa loại loader, instance loader và quá trình delegation.

### Tài liệu chuẩn

- [Java SE 17 — ClassLoader API: getName, getParent, constructors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17 — Class.getClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getClassLoader())
- [JVMS 5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3)
