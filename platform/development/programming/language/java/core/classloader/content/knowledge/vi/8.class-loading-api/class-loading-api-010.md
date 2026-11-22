# Phân biệt nạp lớp, tạo đối tượng và gọi constructor bằng reflection

Trong Java, những câu như “nạp class”, “khởi tạo class”, “tạo object” và “gọi constructor” diễn tả **những hành động khác nhau**. Chúng thường xuất hiện gần nhau khi chương trình dùng reflection, nên rất dễ hiểu nhầm rằng `Class.forName("...")` đã tạo một instance, hoặc `getDeclaredConstructor()` đã chạy constructor. Thực tế, một class có thể đã được JVM nạp và liên kết mà chưa khởi tạo; một đối tượng `Class<?>` có thể tồn tại trước bất kỳ instance nào; và việc **tra cứu constructor** khác với **thực thi constructor**.

Bài học tập trung vào **API nạp lớp và reflection** trong Java 17+: `ClassLoader.loadClass`, các overload `Class.forName`, `Class.getConstructor`/`getDeclaredConstructor`, `Constructor.newInstance`, cách dùng `new` thông thường và việc phân biệt các lỗi xảy ra ở mỗi bước. Các ví dụ cố tình in ra dấu mốc để thấy rõ **điều gì đã xảy ra** và **điều gì chưa xảy ra**.

## 1. Năm khái niệm cần tách biệt

| Hoạt động | Ý nghĩa | Ví dụ | Có tự tạo instance của lớp nghiệp vụ? |
| --- | --- | --- | --- |
| **Loading** (nạp lớp) | JVM xác định một class/interface runtime từ tên và loader, có thể cần đọc class-file bytes | `loader.loadClass("demo.Widget")` | **Không** |
| **Linking** (liên kết) | Verification, preparation và resolution theo quy tắc JVM | JVM thực hiện khi cần để có thể dùng class | **Không** |
| **Initialization** (khởi tạo *lớp*) | Thực thi static initializers/`<clinit>` khi có active use | `Class.forName(name, true, loader)` | **Không** |
| **Instantiation** (tạo *đối tượng*) | Có một object mới của lớp, cấp phát và chạy trình tự khởi tạo instance thích hợp | `new Widget()` hoặc `constructor.newInstance()` | **Có** |
| **Constructor lookup / invocation** | Tìm metadata constructor khác với gọi constructor để tạo instance | `getDeclaredConstructor()` / `newInstance()` | **Chỉ invocation tạo instance** |

**Lưu ý thuật ngữ:** trong tiếng Việt, cả *class initialization* và *object initialization* thường được gọi là “khởi tạo”, nhưng chúng không giống nhau:

- **Class initialization:** chạy các phép gán `static` và khối `static { ... }` theo quy tắc JVM, thường một lần cho mỗi định nghĩa class trong vòng đời loader. Chưa nhất thiết có object `Widget`.
- **Object initialization:** khi có instance mới, JVM thực hiện quá trình khởi tạo đối tượng, gồm constructor superclass, instance field initializers, instance initializer blocks và constructor body theo thứ tự được Java quy định.
- **Đối tượng `Class<?>`:** là đối tượng Java đại diện cho runtime type. Nó **không phải** instance của `Widget` mà ứng dụng dùng làm dữ liệu nghiệp vụ.

### Đọc luồng tổng quan

```text
Widget.java
    │ javac
    ▼
Widget.class
    │ ClassLoader.loadClass / Class.forName(..., false, ...)
    ▼
Class<?> của Widget  ── có thể đã loading/linking
    │
    ├─ getName(), getDeclaredConstructor()  → metadata, chưa gọi constructor
    │
    ├─ Class.forName(..., true, ...)         → yêu cầu class initialization
    │
    └─ Constructor.newInstance(args)
            │
            ├─ đảm bảo class initialization khi cần
            ├─ cấp phát instance mới
            ├─ thực hiện object initialization
            └─ trả về object mới hoặc exception
```

Sơ đồ là mô hình khái niệm, không phải cam kết JVM sẽ thực hiện resolution vào đúng một dòng source. JVM có thể nạp/liên kết sớm và phân giải tham chiếu theo nhu cầu, nhưng **side effect của class initialization** phải tuân thủ thời điểm được Java cho phép.

## 2. `ClassLoader.loadClass` làm được và không làm được gì?

Ví dụ:

```java
ClassLoader loader = MyApplication.class.getClassLoader();
Class<?> type = loader.loadClass("demo.Widget");
```

Đây là **snippet**, muốn biên dịch phải có `MyApplication` và `demo.Widget`. Ý nghĩa chính:

1. `loadClass` nhận **binary name** của class, không nhận đường dẫn `demo/Widget.class`.
2. Class loader tra cứu một định nghĩa đã biết hoặc tìm/ủy quyền nạp class qua parent và cơ chế `findClass`.
3. Kết quả trả về là `Class<?>`, một **đối tượng mô tả kiểu**. Phép gọi **không có lời gọi constructor `Widget()`**.
4. `ClassLoader.loadClass(String)` thông thường **không yêu cầu class initialization**. Những hành động liên quan tới linking có thể diễn ra theo lựa chọn của JVM.
5. Loader được gọi có thể **khác defining loader**. Nếu ủy quyền về parent, class được parent định nghĩa vẫn được trả về như bình thường.

Ví dụ `loader.loadClass("java.lang.String")` thường nhận về đúng `String.class` qua bootstrap, mặc dù loader nhận yêu cầu là application loader.

**Không thể** dựa trên kết quả `loadClass` để nói “đã chạy static block” hoặc “đã có một object nghiệp vụ”. Cách kiểm tra lớp đã initialized hay chưa trong ví dụ học tập là đặt side effect đơn giản trong static initializer và quan sát thứ tự, nhưng **đừng dùng side effect tốn kém để kiểm tra production**.

### Phân biệt lỗi tra cứu

`loadClass("demo.Missing")` có thể ném **checked exception** `ClassNotFoundException` nếu không tìm thấy class. Nếu tìm thấy bytes nhưng định dạng sai, phụ thuộc thiếu hoặc liên kết thất bại, lỗi có thể thuộc họ `LinkageError`. Việc loader không tìm thấy class khác với constructor của class ném exception.

## 3. `Class.forName`: overload quyết định có khởi tạo lớp ngay hay không

Hai dạng quan trọng:

```java
Class<?> a = Class.forName("demo.Widget");
Class<?> b = Class.forName("demo.Widget", false, loader);
Class<?> c = Class.forName("demo.Widget", true, loader);
```

Đoạn này là **snippet**, giả sử `loader` đã được khai báo. Theo API:

- `Class.forName(String className)` tìm, nạp/liên kết và **yêu cầu initialization** của class được đặt tên. Loader được lựa chọn theo ngữ cảnh của lớp gọi.
- `Class.forName(String name, boolean initialize, ClassLoader loader)` cho phép chỉ định **loader** và cờ `initialize`. Với `false`, method tìm/nạp/liên kết class nhưng **không yêu cầu initialization**; với `true`, yêu cầu initialization.
- `Class.forName(Module module, String name)` là overload khác trên Java 9+, phục vụ tìm class trong module và **không yêu cầu initialization**; kết quả có thể là `null` nếu không tìm được class đúng module. Nó **không giống** các overload ném `ClassNotFoundException`.

Điều cần nhớ: **`Class.forName(name)` không gọi constructor** của class được tìm. Nó có thể kích hoạt **static initializer** nhưng không tạo `new Widget()`.

### Class literal: `Widget.class`

```java
Class<Widget> type = Widget.class;
```

Đây là snippet cần định nghĩa `Widget`. Class literal cung cấp đối tượng `Class<Widget>` và **không tự yêu cầu initialize `Widget`**. JVM có thể tải hoặc liên kết class để xử lý biểu thức; không nên đồng nhất các bước nội bộ này với việc chạy khối `static`.

### Một chú ý về tên lớp lồng nhau

Trong ví dụ bên dưới, một `static nested class` tên `Target` trong `LifecycleDemo` có **binary name** là:

```text
demo.LifecycleDemo$Target
```

Không truyền tên dạng `demo.LifecycleDemo.Target` cho `Class.forName`/`loadClass`, bởi đó không phải binary name của member class. `$` là cách javac thường tạo tên binary cho nested classes; `Target.class.getName()` giúp lấy tên chuẩn thay vì tự nối chuỗi.

## 4. Thực hành A — loading, metadata, class initialization và instance initialization

Chạy chương trình độc lập với **Java 17+**.

Cây tệp:

```text
lifecycle-lab/
└── src/
    └── demo/
        └── LifecycleDemo.java
```

Tệp **`src/demo/LifecycleDemo.java`**:

```java
package demo;

import java.lang.reflect.Constructor;

public final class LifecycleDemo {
    public static class Target {
        static {
            System.out.println("Target <clinit>");
        }

        public Target() {
            System.out.println("Target <init>");
        }

        public void work() {
            System.out.println("Target.work()");
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("1. main started");

        ClassLoader loader = LifecycleDemo.class.getClassLoader();
        Class<?> fromLoader =
                loader.loadClass("demo.LifecycleDemo$Target");
        System.out.println("2. loaded: " + fromLoader.getSimpleName());

        Class<?> noInit = Class.forName(
                "demo.LifecycleDemo$Target", false, loader);
        System.out.println("3. same Class: " + (fromLoader == noInit));

        Constructor<?> ctor = noInit.getDeclaredConstructor();
        System.out.println("4. constructor found");

        Object first = ctor.newInstance();
        System.out.println("5. first instanceof Target: " +
                (first instanceof Target));

        ((Target) first).work();

        Object second = ctor.newInstance();
        System.out.println("6. different instances: " +
                (first != second));
    }
}
```

Từ thư mục `lifecycle-lab`, chạy:

```sh
javac --release 17 -d out src/demo/LifecycleDemo.java
java -cp out demo.LifecycleDemo
```

**Stdout chính xác trong một tiến trình mới:**

```text
1. main started
2. loaded: Target
3. same Class: true
4. constructor found
Target <clinit>
Target <init>
5. first instanceof Target: true
Target.work()
Target <init>
6. different instances: true
```

Phân tích theo từng mốc:

1. `main` thuộc `LifecycleDemo` đã được JVM chuẩn bị/khởi tạo trước khi bắt đầu chạy. Điều này **không tự buộc** static initializer của `LifecycleDemo.Target` phải chạy.
2. `loadClass` trả `Class<?>` của nested class `Target`; dòng thứ hai chỉ in tên kiểu. Không có object `Target` được tạo.
3. `Class.forName(name, false, loader)` trả đúng cùng `Class<?>`; không yêu cầu khởi tạo lớp.
4. `getDeclaredConstructor()` **tra cứu metadata constructor không tham số**; không cấp phát `Target` và không gọi body constructor. Việc lấy metadata có thể kéo theo một số bước resolution nhưng không phải active use làm `Target` phải initialized.
5. `ctor.newInstance()` yêu cầu có một instance mới. JVM thực hiện class initialization nếu chưa hoàn tất, nên `Target <clinit>` xuất hiện **trước** `Target <init>`.
6. `first instanceof Target` là kiểm tra type của object đã tạo. Nó không thực hiện constructor mới; ở đây kết quả là `true` vì class trong chương trình là cùng định nghĩa runtime.
7. `((Target) first).work()` gọi instance method và in thông báo riêng; không phải constructor call.
8. `ctor.newInstance()` lần hai tạo **một object khác**, nên constructor lại in `Target <init>`, nhưng static initializer **không chạy lại**.

Dấu `<clinit>` và `<init>` ở output được dùng như **chuỗi minh họa** do code tự in. Trên bytecode JVM, `<clinit>` là class initialization method đặc biệt và `<init>` là instance initialization method tên đặc biệt, song câu `System.out.println(...)` chỉ đang giúp quan sát thứ tự.

Nếu class initializer thất bại, lời gọi reflective construction có thể thất bại **trước khi constructor body bắt đầu**. Đọc nguyên nhân trên stacktrace để phân biệt lỗi initialization của class và lỗi trong constructor.

## 5. Thực hành B — cờ `initialize` của `Class.forName` và thời điểm `static` chạy

Một chương trình độc lập thứ hai giúp so sánh hai tiến trình JVM khác nhau. Tạo tệp **`src/demo/ForNameDemo.java`** trong thư mục riêng hoặc cùng `src/demo` của bài thực hành, sau đó biên dịch.

```java
package demo;

public final class ForNameDemo {
    public static class Ready {
        static {
            System.out.println("Ready static initialization");
        }

        public Ready() {
            System.out.println("Ready constructor");
        }
    }

    public static void main(String[] args) throws Exception {
        boolean eager = Boolean.parseBoolean(args[0]);

        System.out.println("initialize flag: " + eager);
        Class<?> type = Class.forName(
                "demo.ForNameDemo$Ready",
                eager,
                ForNameDemo.class.getClassLoader());

        System.out.println("Class returned");
        type.getDeclaredConstructor().newInstance();
        System.out.println("Object created");
    }
}
```

Biên dịch:

```sh
javac --release 17 -d out src/demo/ForNameDemo.java
```

**Lượt thứ nhất**, dùng `initialize=false`:

```sh
java -cp out demo.ForNameDemo false
```

**Stdout:**

```text
initialize flag: false
Class returned
Ready static initialization
Ready constructor
Object created
```

**Lượt thứ hai**, dùng `initialize=true`:

```sh
java -cp out demo.ForNameDemo true
```

**Stdout:**

```text
initialize flag: true
Ready static initialization
Class returned
Ready constructor
Object created
```

Kết luận quan sát: với `false`, class đã được tra cứu trước nhưng initializer chỉ chạy khi `Constructor.newInstance()` tạo object. Với `true`, `Class.forName` yêu cầu initialization trước lúc trả `Class<?>`. Cả hai trường hợp đều cần **một lần gọi constructor khi tạo object**. Mỗi lệnh `java` ở đây tạo tiến trình JVM riêng, tránh việc lần chạy trước đã initialized class làm sai bài đo.

**Không diễn giải sai:** cờ `initialize=true` không đồng nghĩa “khởi tạo một instance”. Nó chỉ nói về **class initialization**; chỉ câu `newInstance()` ở sau mới tạo object cụ thể.

## 6. Reflection constructor: tìm đúng constructor khác với thực thi nó

Lớp `java.lang.reflect.Constructor<T>` đại diện cho **khai báo constructor** của một class. Các API thường dùng:

| API | Tìm gì? | Có chạy constructor? |
| --- | --- | --- |
| `type.getConstructor(Class<?>... parameterTypes)` | **Public constructor** theo danh sách parameter types | Không |
| `type.getConstructors()` | Mọi public constructor | Không |
| `type.getDeclaredConstructor(Class<?>... parameterTypes)` | Constructor khai báo trực tiếp trong class, **kể cả non-public** | Không |
| `type.getDeclaredConstructors()` | Tất cả constructor khai báo trong class ấy | Không |
| `constructor.getParameterTypes()` | Thông tin kiểu tham số | Không |
| `constructor.canAccess(target)` | Kiểm tra khả năng truy cập hiện tại; target cho constructor là `null` | Không |
| `constructor.trySetAccessible()` | Thử bỏ các kiểm tra truy cập khi module rules cho phép | Không |
| **`constructor.newInstance(args...)`** | **Tạo instance và gọi constructor được chọn** | **Có** |

Với constructor, **không có kế thừa constructor** như method. `getDeclaredConstructor` chỉ tìm constructors được khai báo của chính class, không lấy constructors của superclass rồi cho rằng chúng có thể được gọi như constructor của subclass.

Hai điểm tinh tế:

- **`getDeclaredConstructor()` không tham số** tìm đúng **constructor có 0 tham số**. Nếu chỉ có `Widget(String)`, nó ném `NoSuchMethodException`; JVM **không tự tạo no-arg constructor** khi class đã khai báo constructor khác.
- `getDeclaredConstructor(String.class, int.class)` đòi **chữ ký parameter types chính xác**. Không truyền `Integer.class` thay `int.class` lúc **tra cứu**. Việc chuyển đổi đối số khi **invocation** có quy tắc riêng.

### Constructor lookup không phải method lookup

`getMethod("run")` tìm method công khai, có thể bao gồm method kế thừa. `getDeclaredConstructor()` tìm constructor với signature chỉ định. Đừng cố dùng `getMethod("<init>")`; `<init>` là tên đặc biệt trong class file JVM, không phải method Java bình thường có thể được gọi qua `getMethod`.

## 7. Thực hành C — constructor overload, argument matching và phản chiếu kiểu đối số

Tệp **`src/demo/ConstructorChoice.java`**:

```java
package demo;

import java.lang.reflect.Constructor;

public final class ConstructorChoice {
    public static class Job {
        private final String id;
        private final int attempts;

        public Job() {
            this("default", 1);
        }

        public Job(String id, int attempts) {
            this.id = id;
            this.attempts = attempts;
            System.out.println("constructor: " + id + "/" + attempts);
        }

        public String summary() {
            return id + ":" + attempts;
        }
    }

    public static void main(String[] args) throws Exception {
        Class<Job> type = Job.class;

        Constructor<Job> noArgs = type.getConstructor();
        Constructor<Job> withArgs =
                type.getConstructor(String.class, int.class);

        System.out.println("constructors found");
        Job first = noArgs.newInstance();
        Job second = withArgs.newInstance("batch", 3);

        System.out.println("first: " + first.summary());
        System.out.println("second: " + second.summary());
        System.out.println("distinct: " + (first != second));
    }
}
```

Biên dịch và chạy từ thư mục chứa `src`:

```sh
javac --release 17 -d out src/demo/ConstructorChoice.java
java -cp out demo.ConstructorChoice
```

**Stdout chính xác:**

```text
constructors found
constructor: default/1
constructor: batch/3
first: default:1
second: batch:3
distinct: true
```

Tại sao `"constructor: default/1"` chỉ in **một lần**, dù constructor mặc định gọi `this("default", 1)`? Vì thực tế nó ủy quyền tới body của overload hai tham số, nơi có đúng một lệnh in; khi dùng `this(...)`, constructor được gọi cùng thuộc một lần khởi tạo instance.

Bài học về reflection:

- `getConstructor` chỉ tìm **public constructors**. Ở đây cả hai constructor `public`.
- `getConstructor(String.class, int.class)` trả metadata constructor có parameter types **String, int**, không tự cấp phát object.
- `withArgs.newInstance("batch", 3)` tạo một `Job` và gọi constructor đã chọn. Khi truyền argument, reflection hỗ trợ boxing/unboxing và widening primitive conversions theo quy tắc; không nên dựa vào việc tìm overload tự động như compiler Java source.
- `Class<Job>` và `Constructor<Job>` giữ thông tin generic thuận tiện, nên biến trả về có kiểu `Job` mà không cần cast thủ công.
- `new Job()` trực tiếp và `noArgs.newInstance()` đều tạo object nhưng có khác nhau về thời điểm xác định constructor, kiểm tra access và cách ném exception.

### Tra cứu constructor với primitive và wrapper

`int.class` biểu diễn primitive type `int`. `Integer.class` là **reference type** khác. Với constructor `Job(String, int)`:

```java
type.getConstructor(String.class, int.class);      // tìm được
type.getConstructor(String.class, Integer.class);  // NoSuchMethodException
```

Đây là snippet để đặt vào method có `throws NoSuchMethodException` và biến `type` trong bài trên. **Signature lookup là so exact types**; khi gọi `newInstance("batch", Integer.valueOf(3))` thì reflection có thể unbox đối số thành `int` vì constructor đã được chọn.

Nếu class có nhiều overloaded constructors cùng nhận số, người viết code phải **chọn chính xác** overload qua `getConstructor(parameterTypes...)`. `newInstance` không chạy thuật toán overload resolution ở compile time giống cú pháp `new Job(...)` trong Java source.

## 8. `new` thông thường và `Constructor.newInstance` khác nhau ở đâu?

Hai cách có thể cùng gọi một constructor:

```java
Job direct = new Job();
Job reflective = Job.class.getConstructor().newInstance();
```

Đoạn này giả sử `Job` là public accessible type với public no-arg constructor, và method bao có xử lý `ReflectiveOperationException`.

| Tiêu chí | `new Job()` | `getConstructor().newInstance()` |
| --- | --- | --- |
| Chọn class/constructor | Compiler biết Java type và chọn overload từ source | Chương trình có thể chọn type/signature theo runtime metadata |
| Kiểm tra kiểu và access | Chủ yếu tại compile time, JVM còn runtime checks | Có thêm runtime lookup/access checks |
| Tạo instance | Có | Có |
| Yêu cầu class initialization | Có nếu chưa initialized | Có nếu chưa initialized |
| Constructor body | Chạy | Chạy |
| Type result | `Job` | `Job` với `Constructor<Job>`; `Object` nếu dùng `Constructor<?>` |
| Constructor ném checked exception | Java source phải tuân thủ `throws`/`catch` | Constructor-thrown exception được bọc trong `InvocationTargetException` |
| Sai signature | Compiler báo trước (thường) | `NoSuchMethodException` tại runtime |
| Sai arguments khi invocation | Compiler giúp phát hiện | `IllegalArgumentException` có thể xuất hiện khi chạy |

Reflection hữu ích khi class/constructor chỉ xác định ở runtime: DI container, serialization frameworks, plugin discovery, annotation processors chạy runtime, test frameworks. Tuy nhiên nếu type và constructor đã biết chắc lúc compile, cú pháp `new` hoặc factory thường rõ ràng, ít lỗi runtime và dễ bảo trì hơn.

### Reflection không tự giải quyết mọi vấn đề nạp lớp

Nếu chỉ có tên class nhưng không biết loader phù hợp, `Class.forName(...)` có thể nạp một bản class ở loader khác với bản ứng dụng muốn dùng. Sau khi có `Class<?>`, constructor được lấy từ **chính runtime type ấy**. Hai class cùng tên nhưng do hai defining loaders khác nhau định nghĩa sẽ có những `Constructor<?>` gắn với **hai runtime classes khác nhau**. Không thể tự cast object từ type của plugin loader thành type của host chỉ vì tên class giống.

## 9. Khởi tạo instance: thứ tự các bước dễ bị nhầm với `static`

Một lần gọi constructor không chỉ là thực hiện những dòng nằm trong thân constructor cuối cùng. Với đối tượng class thông thường, chương trình tuân theo trình tự khởi tạo instance:

1. JVM cần class hợp lệ, đã được initialized theo quy tắc (nếu chưa).
2. Cấp phát một object mới và đặt **giá trị mặc định** cho instance fields trước khi các initializer cụ thể chạy.
3. Thực hiện chuỗi constructor của superclass (`super(...)`) theo Java language rules.
4. Thực hiện các instance field initializers và instance initializer blocks của lớp tương ứng theo thứ tự nguồn.
5. Thực hiện phần thân constructor phù hợp, sau những lời gọi `this(...)`/`super(...)` bắt buộc trong quá trình khởi tạo.

Ví dụ độc lập, tệp **`src/demo/OrderDemo.java`**:

```java
package demo;

class Parent {
    static {
        System.out.println("Parent static");
    }

    {
        System.out.println("Parent instance block");
    }

    Parent() {
        System.out.println("Parent constructor");
    }
}

class Child extends Parent {
    static {
        System.out.println("Child static");
    }

    {
        System.out.println("Child instance block");
    }

    Child() {
        System.out.println("Child constructor");
    }
}

public final class OrderDemo {
    public static void main(String[] args) {
        System.out.println("before new");
        new Child();
        System.out.println("after first");
        new Child();
    }
}
```

Chạy:

```sh
javac --release 17 -d out src/demo/OrderDemo.java
java -cp out demo.OrderDemo
```

**Stdout chính xác:**

```text
before new
Parent static
Child static
Parent instance block
Parent constructor
Child instance block
Child constructor
after first
Parent instance block
Parent constructor
Child instance block
Child constructor
```

Khi `Child` phải được initialized, JVM khởi tạo superclass `Parent` trước khi khởi tạo chính `Child`; vì vậy hai khối static xuất hiện trước object constructor. Mỗi lần `new Child()` tiếp theo vẫn chạy **instance blocks và constructor chain** nhưng **không chạy lại static initializers**. Nếu thay hai biểu thức `new Child()` bằng một `Constructor<Child>.newInstance()` thích hợp, nguyên tắc thứ tự static và instance vẫn được bảo toàn.

Trình tự đầy đủ có thêm các quy tắc riêng cho interface khởi tạo liên quan và constructor chaining; ví dụ cố ý dùng các class thông thường để minh họa trục chính. Không dùng `ClassLoader.loadClass` như cơ chế "chạy constructor Parent trước" — đó là việc khác.

## 10. Một class có thể initialized mà không hề có instance

Đọc static field hoặc gọi static method thuộc một class có thể yêu cầu **class initialization**, dù không tạo object nào.

Ví dụ snippet minh họa:

```java
class Settings {
    static {
        System.out.println("Settings initialized");
    }

    static int getPort() {
        return 8080;
    }
}
```

Nếu một chương trình khác gọi `Settings.getPort()`, JVM có thể phải thực hiện static initializer nhưng không gọi `new Settings()`, không gọi constructor `Settings()`, và không cần bất kỳ Settings instance nào.

Ngược lại, một **constant variable** như `public static final int PORT = 8080` có thể được compiler inline vào caller. Đọc nó từ class khác không nhất thiết yêu cầu initialize class khai báo. Đó là lý do muốn kiểm tra chính xác thời điểm static initializer, không nên chỉ dựa vào việc đọc một compile-time constant.

Các thao tác như `SomeClass.class`, `someClass.getName()` và tra cứu constructor metadata thường **không phải** active use. Nhưng static method invocation, đọc static field không phải constant variable, tạo object và một số hoạt động reflection có thể là active use. Đặc biệt, `Class.forName(name, true, loader)` yêu cầu initialization ngay cả khi không gọi constructor.

## 11. Sai lầm phổ biến với `Class.newInstance()`

API cũ:

```java
Object instance = type.newInstance();
```

`Class.newInstance()` đã **deprecated từ Java 9**. Mã Java 17+ nên dùng:

```java
Object instance = type.getDeclaredConstructor().newInstance();
```

Cả hai là **snippets**; biến `type` có kiểu `Class<?>` và method phải xử lý exceptions phù hợp.

Lý do kỹ thuật đáng nhớ: `Class.newInstance()` có cơ chế exception handling kém trực quan, vì nó có thể **truyền ra checked exception do constructor ném** mà signature không thể hiện đầy đủ. Cách `getDeclaredConstructor().newInstance()` trả `InvocationTargetException` giúp caller phân biệt **lỗi gọi reflective API** với **exception phát sinh bên trong constructor**.

Ngoài ra, lựa chọn constructor qua `getDeclaredConstructor(Class<?>...)` giúp chỉ định chính xác overload; không tự hạn chế vào public zero-argument constructor mà `Class.newInstance()` vốn cố gắng dùng.

Không dùng `Class.newInstance()` trong ví dụ mới chỉ vì ngắn hơn một chút. Đặc biệt với code framework, việc truy xuất `InvocationTargetException.getCause()` quan trọng để giữ nguồn gốc lỗi.

## 12. Thực hành D — lỗi bên trong constructor và `InvocationTargetException`

Tạo tệp **`src/demo/ConstructorErrorDemo.java`**:

```java
package demo;

import java.lang.reflect.InvocationTargetException;

public final class ConstructorErrorDemo {
    public static class Broken {
        public Broken() {
            System.out.println("constructor entered");
            throw new IllegalStateException("bad config");
        }
    }

    public static void main(String[] args) throws Exception {
        Class<?> type = Class.forName(
                "demo.ConstructorErrorDemo$Broken",
                false,
                ConstructorErrorDemo.class.getClassLoader());

        System.out.println("Class found");
        try {
            type.getDeclaredConstructor().newInstance();
        } catch (InvocationTargetException e) {
            Throwable original = e.getCause();
            System.out.println("reflection wrapper: " +
                    e.getClass().getSimpleName());
            System.out.println("constructor cause: " +
                    original.getClass().getSimpleName());
            System.out.println("message: " + original.getMessage());
        }
    }
}
```

Chạy với JDK 17+:

```sh
javac --release 17 -d out src/demo/ConstructorErrorDemo.java
java -cp out demo.ConstructorErrorDemo
```

**Stdout chính xác:**

```text
Class found
constructor entered
reflection wrapper: InvocationTargetException
constructor cause: IllegalStateException
message: bad config
```

Điểm kiểm chứng:

- `Class.forName(..., false, ...)` tìm class mà chưa yêu cầu initialization; không có output từ constructor trước khi gọi `newInstance`.
- Constructor **đã bắt đầu thực thi**, vì đã in `constructor entered`, sau đó chính constructor ném `IllegalStateException`.
- `Constructor.newInstance` bọc exception do constructor ném trong `InvocationTargetException`; `getCause()` trả về exception gốc.
- Nếu class static initializer ném exception **trước khi constructor body chạy**, JVM có thể báo `ExceptionInInitializerError` hoặc lỗi initialization liên quan. Đây là **trường hợp khác**, không nên mặc định mọi lỗi construction đều là `InvocationTargetException`.

Trong ứng dụng thật, logging phải giữ cả stacktrace/cause, không chỉ gọi `getSimpleName()`. Ví dụ trên in tên exception để kiểm tra thứ tự và nội dung một cách xác định.

## 13. Ma trận lỗi theo từng thao tác

| Hành động | Lỗi có thể gặp | Ý nghĩa |
| --- | --- | --- |
| `loader.loadClass(name)` | `ClassNotFoundException` | Loader không tìm được class yêu cầu; không nói constructor có lỗi. |
| `Class.forName(name, ..., loader)` | `ClassNotFoundException`, `LinkageError`, lỗi initialization nếu `true` | Tên/loader không hợp lệ, liên kết không thành công hoặc static initialization có vấn đề. |
| `type.getConstructor(types...)` | `NoSuchMethodException` | Không có **public constructor** đúng parameter list. |
| `type.getDeclaredConstructor(types...)` | `NoSuchMethodException` | Class không khai báo constructor có signature ấy, kể cả sau khi xét non-public. |
| `ctor.newInstance(args...)` | `InstantiationException` | Declaring class là abstract hoặc không thể instantiated theo hợp đồng API. |
| `ctor.newInstance(args...)` | `IllegalAccessException` | Caller không có quyền truy cập constructor dưới access/module rules. |
| `ctor.newInstance(args...)` | `IllegalArgumentException` | Số lượng/kiểu arguments không hợp lệ hoặc chuyển đổi không được hỗ trợ. |
| `ctor.newInstance(args...)` | `InvocationTargetException` | Code **bên trong constructor** ném exception; đọc `getCause()`. |
| Reflection mở quyền private | `InaccessibleObjectException` hoặc `trySetAccessible() == false` | Module/package không mở đúng hoặc quyền reflection không được phép. |
| Class initialization khi construction | `ExceptionInInitializerError`/`NoClassDefFoundError` | Static initialization thất bại lần đầu hoặc class đã mang trạng thái initialization lỗi. |
| Cast object vừa tạo | `ClassCastException` | Runtime object không assignable với type đích, có thể do class loader identity. |

Lỗi liệt kê theo **ngữ cảnh chính**, không có nghĩa mỗi API chỉ có đúng loại lỗi đó. Một số lỗi như `LinkageError`, `SecurityException` hoặc `ExceptionInInitializerError` là unchecked và có thể phát sinh trong nhiều giai đoạn khác nhau. Nếu log chỉ in “Cannot instantiate”, cần truy lại **giai đoạn nào**: không tìm được class, không tìm được constructor, không thể truy cập, class initialized lỗi, hay body constructor đã ném exception.

### `InstantiationException` và abstract classes

Reflection không cho tạo instance trực tiếp của một **abstract class**, dù abstract class có constructor hợp lệ (constructor đó được subclass gọi khi khởi tạo subclass). Interface không có constructor Java để tra cứu qua `getDeclaredConstructor()` theo cách tạo object thông thường. Enum constructors không dùng để tạo tùy ý enum constants bằng reflection; `Constructor.newInstance` sẽ từ chối enum instantiation.

Một **record** có constructor (thường là canonical constructor) và vẫn có thể được tạo qua reflection nếu constructor/access/arguments hợp lệ; đừng áp đặt giả định “mọi class có no-arg constructor”. Một record khai báo components thường cần truyền đúng tham số canonical constructor.

## 14. Phân biệt access modifier với khả năng dùng reflection

Trong code bình thường, Java compiler kiểm tra `public`, `protected`, package-private và `private`. Reflection có thể tìm **private constructor** qua `getDeclaredConstructor` nhưng **tìm thấy không đồng nghĩa được phép gọi**.

Ví dụ minh họa:

```java
Constructor<?> ctor = type.getDeclaredConstructor();
boolean changed = ctor.trySetAccessible();
if (changed) {
    Object value = ctor.newInstance();
}
```

Đây là **snippet**, cần biến `type` và xử lý exceptions. `trySetAccessible()` cố bỏ Java language access checks trong giới hạn module rules; nếu không được, trả `false` (hoặc có thể phát sinh lỗi bảo mật tùy môi trường). `setAccessible(true)` có thể ném `InaccessibleObjectException` khi deep reflection vào package mà named module không mở.

**Không nên** mặc định mọi JDK-internal private constructor có thể được gọi bằng `setAccessible(true)`. Từ Java 9+, Java Platform Module System phân biệt **exports** (public API access) và **opens** (deep reflection), và từ các bản JDK mới mạnh hơn trong việc đóng gói nội bộ JDK. Khi thiết kế API cho framework/DI, nên công bố public constructor/factory hoặc khai báo `opens ... to ...` đúng nhu cầu thay vì phụ thuộc các mẹo phá đóng gói.

Nếu code caller và target là **nestmates** trong cùng nest Java, các quyền truy cập private có quy tắc riêng. Nhưng ví dụ học tập ở trên dùng public nested classes/constructors để tránh phụ thuộc thao tác mở quyền reflection.

### `getDeclaredConstructor` không tự động có quyền cao hơn `getConstructor`

- `getDeclaredConstructor` thấy constructors khai báo, **kể cả private**.
- `getConstructor` chỉ thấy public constructors.
- **Chính lệnh `newInstance`** còn kiểm tra quyền truy cập của caller và module. Vì vậy nhìn thấy metadata private không đủ để suy luận sẽ gọi được.

## 15. Reflection và classloader identity: tạo được object vẫn có thể cast sai

Khi class được nạp qua loader riêng, `type.getDeclaredConstructor().newInstance()` tạo object có **runtime class `type` đó**. Nó không biến object thành class cùng tên mà host đã biết.

Hình dung:

```text
HostLoader defines api.Task
PluginLoader defines api.Task

Class<?> hostType    → (api.Task, HostLoader)
Class<?> pluginType  → (api.Task, PluginLoader)

pluginType.getDeclaredConstructor().newInstance()
          → instance của pluginType
          → KHÔNG tự cast được về hostType
```

Hãy kiểm tra:

```java
Class<?> actualType = instance.getClass();
System.out.println(actualType.getName());
System.out.println(actualType.getClassLoader());
System.out.println(expectedType.isInstance(instance));
```

Snippet cần khai báo `instance` và `expectedType`. Nếu `isInstance` trả `false`, reflection constructor có thể hoàn toàn thành công, nhưng hai types ở ranh giới loaders vẫn không tương thích.

**Cách thiết kế đúng trong plugin system:** interface/service API cần được host và plugin resolve về **cùng `Class<?>`**, thường qua parent/shared-API loader, rồi implementation do plugin loader định nghĩa riêng. Khi ấy host có thể ép instance implementation thành interface chung mà không cần tự tải implementation trên application classpath.

### Nếu loader chưa biết class nhưng có bytes thì sao?

Custom loader có thể đọc bytes trong `findClass` và dùng `defineClass` để tạo runtime class. Đó là **phần loading**, không phải gọi constructor của class được nạp. Sau khi có `Class<?>`, chương trình mới tra cứu constructor và tạo instance. Không biến `findClass` hoặc `defineClass` thành một hàm “khởi tạo plugin object” mà không phân biệt lifecycle.

## 16. Khi nào nên dùng `getDeclaredConstructor().newInstance()`?

Các tình huống hợp lý:

1. **Plugin registry:** tên binary class được cấu hình hoặc đọc từ metadata, không biết concrete implementation lúc biên dịch.
2. **Dependency injection container:** framework xác định constructor theo annotations/metadata và cung cấp arguments tương ứng.
3. **Serialization/deserialization tools:** có cơ chế khởi tạo object phù hợp, dù không phải mọi serializer đều gọi Java constructor thông thường.
4. **Test framework:** tạo test class và gọi lifecycle hooks dựa trên runtime metadata.
5. **Factory động:** người dùng chọn implementation qua configuration nhưng hệ thống muốn kiểm soát type/constructor access.

Một chuỗi thực hiện an toàn và dễ debug:

```text
Tên class / metadata cấu hình
        ↓ validate tên và chọn đúng ClassLoader
Class<?> type = Class.forName(name, false, loader)
        ↓ validate subtype/interface mong muốn
expectedInterface.isAssignableFrom(type)
        ↓ chọn constructor theo parameter types
type.getDeclaredConstructor(...)
        ↓ kiểm tra quyền truy cập phù hợp
constructor.newInstance(args...)
        ↓ cast về interface chung / bắt lỗi có phân loại
host sử dụng object qua contract
```

**Chú ý:** check `isAssignableFrom` giúp tránh cast sai, nhưng **không tự biến việc chạy plugin không tin cậy thành an toàn**. Constructor có thể mở tệp, khởi chạy thread, truy cập network hoặc có side effects. Class loader chỉ giải quyết visibility/definition; sandboxing cần những biện pháp bảo mật độc lập.

### Khi nào `new` hoặc factory thường tốt hơn?

Nếu ứng dụng biết sẵn `new Service(config)` ở compile time, direct construction thường minh bạch, đảm bảo compiler kiểm tra signature, ít exception reflection và thuận tiện refactor. Reflection nên giải quyết **nhu cầu runtime discovery thật**; không cần nó chỉ để tránh viết một lệnh `new`.

Nếu API có nhiều constructor overload hoặc yêu cầu cấu hình phức tạp, một **public static factory** hoặc plugin-provided factory trong shared API có thể giúp giữ hợp đồng ổn định hơn so với cho host tìm constructor concrete bằng tên. Factory cũng là phương án cho class có private constructor mà framework không cần mở quyền truy cập sâu.

## 17. Kiểm soát side effects và vòng đời khi tạo plugin object

Việc `Class.forName(..., false, loader)` chỉ tra cứu class chưa có nghĩa toàn bộ quá trình “vô hại”: loading, verification/linking hoặc chạy agent/loader code có thể có chi phí và side effects theo implementation. Tuy nhiên static initialization của target class được JVM kiểm soát theo quy tắc, và constructor body chưa chạy cho đến khi instance được tạo.

Một constructor không nên làm quá nhiều việc khó kiểm soát, đặc biệt trong plugin runtime:

- Không tự đăng ký global listener hoặc tạo background thread nếu không có cơ chế huỷ đăng ký/dừng rõ ràng.
- Cân nhắc đưa việc kết nối network/file, nạp cấu hình hoặc mở resource sang `start()`/factory lifecycle có thể báo lỗi rõ và cleanup an toàn.
- Nếu constructor throw sau khi side effect một phần, caller có thể nhận `InvocationTargetException` mà không có object hợp lệ để gọi `close()`; vì vậy cần thiết kế rollback/tài nguyên cẩn thận.
- Với plugin reload, object và `Class<?>` có thể giữ class loader sống. `URLClassLoader.close()` giải phóng tài nguyên mở của loader nhưng không đảm bảo unload class/object ngay; GC còn phụ thuộc reachability.

Phân biệt ba thao tác trong log vận hành: **load type**, **instantiate service**, **start service**. Dù cả ba có thể nằm liên tiếp, chúng là ba trạng thái khác nhau và nên có thông tin lỗi riêng.

## 18. Một quy trình chẩn đoán theo triệu chứng

**Nếu nói “không load được class”:** kiểm tra binary name, classpath/module path, parent loader, class file tồn tại và runtime JDK có hỗ trợ bytecode version không. Bắt `ClassNotFoundException` ở đoạn loader/`forName` khi thích hợp.

**Nếu “load được class nhưng không tạo được object”:** xác minh class có phải interface/abstract/enum không; constructor nào tồn tại; có đúng parameter types và access không. Ghi log `getDeclaredConstructors()` trong công cụ debug, nhưng tránh đưa metadata của các class không tin cậy ra log public.

**Nếu “constructor đã chạy nhưng trả lỗi”:** bắt `InvocationTargetException`, xem `getCause()`; phân biệt exception do body constructor với lỗi initialization xảy ra trước body.

**Nếu “tạo được object nhưng cast thất bại”:** kiểm tra `type.getClassLoader()`, `expectedInterface.getClassLoader()`, `isAssignableFrom` và shared API packaging. Đừng xem hai class cùng binary name là đủ.

**Nếu “static block chạy quá sớm”:** xem nơi gọi `Class.forName(name)` (mặc định initialize), việc tạo instance, gọi static method hoặc đọc static field không phải compile-time constant. Có thể thay bằng `Class.forName(name, false, loader)` khi chỉ cần metadata và API semantics cho phép.

**Nếu “static block không chạy khi gọi `loadClass`”:** hành vi đó đúng theo mục đích `loadClass(String)` thông thường; cần active use hoặc `Class.forName(..., true, ...)` khi thật sự muốn initialize target.

**Nếu “chạy lại mà static block không in nữa”:** class initialization thường chỉ diễn ra một lần đối với một runtime class. Muốn quan sát từ đầu, chạy một JVM mới; việc `Constructor.newInstance` nhiều lần không tự reset static state.

### Công cụ bổ trợ

```sh
javap -classpath out -c -p demo.LifecycleDemo
javap -classpath out -v 'demo.LifecycleDemo$Target'
java -Xlog:class+load=info -cp out demo.LifecycleDemo
```

`javap` cho biết class file chứa constructor `<init>`, class initializer `<clinit>` và bytecode như `new`/`invokespecial`. Với nested class name có `$`, ở shell Unix hãy quote như ví dụ để tránh biến môi trường được thay thế; PowerShell cũng hiểu single quotes như literal. Unified class-load log trên HotSpot có output phụ thuộc runtime và **chỉ cung cấp tín hiệu loading**, không tự chứng minh constructor đã chạy; để biết constructor đã chạy thì quan sát output/stacktrace của chính ứng dụng.

## 19. Những câu khẳng định sai thường gặp

- **"`loadClass` chính là `new`."** Sai: nó trả về `Class<?>`, không tạo business instance.
- **"`Class.forName(name)` tự gọi constructor mặc định."** Sai: overload này yêu cầu **class initialization**, không tạo instance.
- **"`getDeclaredConstructor` chạy constructor."** Sai: nó chỉ trả về **constructor metadata**.
- **"Dùng `getDeclaredConstructor` thì constructor private gọi được luôn."** Sai: access và JPMS vẫn được kiểm tra lúc invocation.
- **"`getDeclaredConstructor(Integer.class)` sẽ tìm constructor nhận `int`."** Sai: lookup parameter types chính xác; chuyển đổi argument là bước khác.
- **"`Constructor.newInstance` chạy static block mỗi lần."** Sai: class initialization không lặp lại với mỗi object; constructor instance có thể chạy nhiều lần.
- **"Constructor throw sẽ luôn lộ trực tiếp `IllegalStateException`."** Sai: `Constructor.newInstance` thường bọc exception body trong `InvocationTargetException`; class initialization errors là nhóm khác.
- **"`Class.newInstance` là lựa chọn mới nhất."** Sai: đã deprecated; nên dùng `getDeclaredConstructor().newInstance()`.
- **"ClassLoader định nghĩa class thì tự có instance."** Sai: type metadata và object instances là hai khái niệm khác nhau.
- **"Reflection loại bỏ vấn đề identity giữa nhiều class loaders."** Sai: object vừa tạo mang đúng runtime type của class mà reflection dùng.
- **"Class đã load chắc chắn có constructor public không tham số."** Sai: có thể không có, hoặc là abstract/interface/enum/record với các ràng buộc riêng.
- **"Có thể chắc chắn thời điểm resolution chỉ bằng output của `javap`."** Sai: `javap` đọc file metadata; JVM được phép thực hiện resolution theo chiến lược runtime.

## 20. Tự kiểm tra: trả lời trước khi mở đáp án

**1. `ClassLoader.loadClass("demo.Target")` trả về loại đối tượng gì?** Một `Class<?>` đại diện cho target runtime class; nó không tự tạo target instance hoặc bắt buộc chạy target constructor.

**2. `Class.forName("demo.Target")` khác overload `Class.forName("demo.Target", false, loader)` ở đâu?** Dạng một yêu cầu class initialization; dạng có `false` tìm/nạp/liên kết mà không yêu cầu initialization, đồng thời chọn loader tường minh.

**3. Khi `getDeclaredConstructor()` thành công, có biết constructor body đã chạy không?** Không. Đây mới là tra cứu metadata.

**4. Tại sao `Constructor.newInstance()` in static block chỉ lần đầu, còn constructor in mọi lần?** Class initialization thông thường thực hiện một lần cho class đó, trong khi mỗi instance mới phải trải qua object initialization.

**5. Tại sao `getConstructor(int.class)` khác `getConstructor(Integer.class)`?** Primitive `int` và wrapper `Integer` là hai types khác nhau; constructor lookup yêu cầu parameter types chính xác.

**6. `Class.newInstance()` có còn được khuyến nghị cho Java 17+?** Không. API đã deprecated; dùng `getDeclaredConstructor().newInstance()` với exception handling rõ ràng.

**7. Nếu constructor ném `IllegalArgumentException` từ bên trong body, cần tìm nó ở đâu?** Khi gọi qua `Constructor.newInstance`, exception body thường là `cause` của `InvocationTargetException`. Nếu `newInstance` trực tiếp ném `IllegalArgumentException` do arguments sai, đó là vấn đề reflection invocation trước khi body constructor chạy.

**8. Class có constructor private được tìm bằng API nào?** `getDeclaredConstructor(...)`; việc có gọi được hay không phụ thuộc access rules, module openness và caller.

**9. Class có thể initialized nhưng chưa có instance nào không?** Có. Gọi một static method hoặc `Class.forName(..., true, ...)` có thể initialize class mà không tạo object.

**10. Vì sao reflection tạo đúng object tên `demo.Plugin` nhưng host cast sai?** Vì có thể object là instance của runtime class cùng binary name do một defining loader khác định nghĩa; cần dùng shared API identity.

## 21. Tài liệu chuẩn

- [Java SE 17 `ClassLoader` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, parent delegation và defining/initiating loaders.
- [Java SE 17 `Class` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): các overload `forName`, `getConstructor`, `getDeclaredConstructor`, class literal và `newInstance()` deprecated.
- [Java SE 17 `Constructor` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html): `Constructor.newInstance`, argument/access checks và `InvocationTargetException`.
- [Java SE 17 `InvocationTargetException` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html): cách truy xuất target exception.
- [The Java Language Specification, Java SE 17, 12](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html): loading, linking, initialization; tạo class instance và trình tự instance initialization.
- [The Java Virtual Machine Specification, Java SE 17, 5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): loading, linking, class initialization và ranh giới thực thi.

**Nguyên tắc nhớ:** **`loadClass` tìm một runtime *type*; `Class.forName` còn có lựa chọn yêu cầu *class initialization*; `getDeclaredConstructor` tìm *constructor metadata*; `Constructor.newInstance` mới tạo một *instance* và thực thi constructor.** Khi debug, xác định từng bước cùng class loader và runtime type cụ thể để tránh đánh đồng bốn hành động này.
