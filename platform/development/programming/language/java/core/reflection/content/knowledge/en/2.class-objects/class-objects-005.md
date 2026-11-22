# Nạp lớp khác khởi tạo lớp như thế nào trong Java?

Khi làm việc với **đối tượng `Class<?>`** và Reflection, hai thao tác rất dễ bị nhầm là **nạp lớp (class loading)** và **khởi tạo lớp (class initialization)**. Một lớp có thể đã được JVM nhận diện, có đối tượng `Class` và có thể được kiểm tra metadata mà **chưa thực thi bất kỳ khối `static` nào** của chính lớp đó.

Mục tiêu bài học: phân biệt loading, linking, initialization và tạo đối tượng; dự đoán thời điểm khối `static` chạy; chọn đúng API `Class.forName`/`ClassLoader.loadClass`; và nhận biết các tình huống Reflection vô tình kích hoạt khởi tạo lớp.

## 1. Bốn việc khác nhau trong vòng đời lớp

| Hoạt động | JVM làm gì? | Có bắt buộc chạy `static { ... }` của lớp đích? |
|---|---|---|
| **Loading (nạp)** | Tìm định nghĩa nhị phân của lớp, đọc/diễn giải dữ liệu class và tạo biểu diễn runtime tương ứng, trong đó có đối tượng `Class`. | **Không**. |
| **Linking (liên kết)** | Verify bytecode; prepare bộ nhớ cho các biến `static` và gán giá trị mặc định; resolve tham chiếu ký hiệu khi thích hợp. Resolution có thể thực hiện muộn. | **Không**. |
| **Initialization (khởi tạo lớp)** | Chạy phương thức khởi tạo lớp `<clinit>`: các biểu thức khởi tạo trường `static` và khối `static`, theo thứ tự trong mã nguồn. | **Có**: đây chính là giai đoạn thực thi phần khởi tạo tĩnh. |
| **Instance initialization (khởi tạo đối tượng)** | Tạo một instance, thực hiện quy trình khởi tạo instance và constructor `<init>`. | Lớp thích hợp phải được khởi tạo trước khi tạo instance; constructor là công việc **riêng**, có thể chạy nhiều lần. |

Các giá trị mặc định trong bước **preparation** không đồng nghĩa với việc đã chạy biểu thức khởi tạo trong mã nguồn. Ví dụ, với `static int count = calculate();`, bước preparation chuẩn bị giá trị mặc định `0`; lời gọi `calculate()` thuộc initialization. Một số trường là **constant variable** có cách xử lý đặc biệt; xem mục 4.

Một điểm quan trọng về thứ tự: JVM có thể chủ động nạp, verify hoặc resolve lớp sớm hơn thời điểm chương trình chủ động dùng lớp. Vì vậy, **thấy một đối tượng `Class` tồn tại không chứng minh khối `static` đã chạy**. Quy tắc về thời điểm initialization được ràng buộc chặt hơn bởi ngữ nghĩa ngôn ngữ.

### Đối tượng `Class` đại diện cho điều gì?

`Class<?>` là đối tượng runtime đại diện cho kiểu: có thể đọc tên, superclass, interface, annotation, constructor, field và method. Các đường lấy tham chiếu thường gặp là:

- `MyType.class`: lấy đối tượng `Class` cho kiểu đã biết khi biên dịch; **không tự kích hoạt initialization** của `MyType`.
- `object.getClass()`: lấy lớp runtime của **một đối tượng đã tồn tại**; thao tác lấy metadata này không tự khởi tạo lại lớp.
- `ClassLoader.loadClass("pkg.MyType")`: yêu cầu loader nạp lớp theo **binary name**; bản thân lời gọi thông thường không khởi tạo lớp.
- `Class.forName("pkg.MyType")`: phiên bản một tham số **yêu cầu khởi tạo lớp** sau khi tìm/nạp lớp thành công.
- `Class.forName(name, false, loader)`: tìm/nạp lớp với yêu cầu **chưa khởi tạo**.
- `Class.forName(name, true, loader)`: tìm/nạp và **yêu cầu khởi tạo** lớp.

Tên nhị phân của nested class dùng ký tự `$`, ví dụ `demo.Outer$Inner`, không dùng `demo.Outer.Inner` trong lời gọi `Class.forName` thông thường.

## 2. Ví dụ Java 17+: nhìn thấy chính xác lúc khối static chạy

Lưu toàn bộ chương trình sau thành tệp **`ClassLifecycleDemo.java`**:

```java
import java.lang.reflect.Method;

public class ClassLifecycleDemo {
    static class Target {
        static {
            System.out.println("Target <clinit>");
        }

        Target() {
            System.out.println("Target constructor");
        }

        static void hello() {
            System.out.println("Target.hello()");
        }
    }

    public static void main(String[] args) throws Exception {
        String binaryName = ClassLifecycleDemo.class.getName() + "$Target";
        ClassLoader loader = ClassLifecycleDemo.class.getClassLoader();

        System.out.println("1. class literal");
        Class<?> fromLiteral = Target.class;
        System.out.println(fromLiteral.getSimpleName());

        System.out.println("2. loadClass");
        Class<?> fromLoader = loader.loadClass(binaryName);
        System.out.println(fromLoader == fromLiteral);

        System.out.println("3. Class.forName(false)");
        Class<?> fromForName = Class.forName(binaryName, false, loader);
        System.out.println(fromForName == fromLiteral);

        System.out.println("4. getDeclaredMethod");
        Method method = fromForName.getDeclaredMethod("hello");
        System.out.println(method.getName());

        System.out.println("5. Class.forName(true)");
        Class.forName(binaryName, true, loader);

        System.out.println("6. Method.invoke");
        method.invoke(null);

        System.out.println("7. Constructor.newInstance");
        fromForName.getDeclaredConstructor().newInstance();
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac ClassLifecycleDemo.java
java ClassLifecycleDemo
```

**Stdout dự kiến (chạy trên Java 17+):**

```text
1. class literal
Target
2. loadClass
true
3. Class.forName(false)
true
4. getDeclaredMethod
hello
5. Class.forName(true)
Target <clinit>
6. Method.invoke
Target.hello()
7. Constructor.newInstance
Target constructor
```

**Giải thích từng mốc:**

1. `Target.class` cho phép lấy tên lớp, nhưng chưa chạy `Target <clinit>`.
2. `loadClass(binaryName)` trả về cùng đối tượng `Class` do cùng kiểu và cùng defining class loader, vẫn chưa có initializer tĩnh được chạy.
3. `Class.forName(..., false, ...)` cũng lấy đối tượng `Class` mà chưa yêu cầu initialization.
4. `getDeclaredMethod("hello")` đọc thông tin method, chưa **gọi** method.
5. `Class.forName(..., true, ...)` là điểm đầu tiên **kích hoạt khởi tạo lớp**; `<clinit>` in ra đúng một lần.
6. `method.invoke(null)` gọi method `static` (đối số receiver `null`); lúc này lớp đã được khởi tạo nên không chạy lại `<clinit>`.
7. `Constructor.newInstance()` tạo một đối tượng và gọi constructor, vì vậy xuất hiện `Target constructor`, **không phải** một lần khởi tạo lớp nữa.

Lưu ý: `Target` ở đây là **static nested class**. Vì mã gọi và `Target` cùng một nest, ví dụ có thể gọi method/constructor bằng Reflection mà không cần thay đổi quyền truy cập. Với lớp ở package/module khác, kiểm tra khả năng truy cập riêng.

## 3. Những thao tác thực sự kích hoạt initialization

Theo quy tắc về initialization của Java (JLS §12.4.1), các tình huống chủ động sử dụng thường gặp gồm:

- Tạo instance bằng `new SomeClass()`.
- Gọi phương thức `static` được khai báo trong lớp (`SomeClass.run()`).
- Gán hoặc đọc một trường `static` được khai báo trong lớp, **ngoại trừ** trường là *constant variable* theo định nghĩa của Java.
- Yêu cầu khởi tạo qua `Class.forName(name)` hoặc `Class.forName(name, true, loader)`.
- Một số thao tác Reflection tương ứng với việc sử dụng chủ động, chẳng hạn `Method.invoke` cho static method, `Field.get`/`Field.set` cho static field, hoặc `Constructor.newInstance`.

Những thao tác **không tự yêu cầu khởi tạo lớp đích**:

- Lấy `SomeClass.class`.
- Dùng `ClassLoader.loadClass(name)` thông thường.
- Dùng `Class.forName(name, false, loader)`.
- Chỉ kiểm tra metadata qua các phương thức như `getName()`, `getDeclaredMethods()`, `getDeclaredFields()`, `getDeclaredConstructors()`, `getAnnotations()`.
- Khai báo biến tham chiếu kiểu `SomeClass`, ép kiểu, kiểm tra `instanceof` hoặc tạo mảng `new SomeClass[3]` mà chưa tạo instance `SomeClass`.

**Cẩn thận với sự khác nhau giữa “tìm method” và “gọi method”:** `getDeclaredMethod` chỉ cung cấp đối tượng `Method`; `invoke` mới thực hiện invocation. Khi invocation là phương thức `static`, lớp khai báo method sẽ được khởi tạo trước nếu chưa khởi tạo.

**Cẩn thận với quyền sở hữu trường `static`:** truy cập `Child.inheritedField` có thể chỉ khởi tạo `Parent` nếu trường thật sự **được khai báo** ở `Parent`. Không suy ra “tên lớp xuất hiện trước dấu chấm” luôn là lớp cần khởi tạo.

Khi khởi tạo một class, JVM bảo đảm superclass cần thiết được khởi tạo trước; các superinterface có khai báo default method cũng có quy tắc khởi tạo liên quan. Không được suy rộng rằng mọi interface mà class implements đều sẽ được khởi tạo ngay.

## 4. Ngoại lệ quan trọng: hằng compile-time không kích hoạt initialization

Một `static final` chưa chắc là hằng lúc biên dịch. Một *constant variable* phải có kiểu primitive hoặc `String`, được khai báo `final`, và được khởi tạo bằng *constant expression*.

Lưu chương trình độc lập sau thành **`ConstantsDemo.java`**:

```java
public class ConstantsDemo {
    static class Config {
        static {
            System.out.println("Config initialized");
        }

        static final String LABEL = "DEV"; // constant variable
        static final Integer PORT = 8080;  // KHÔNG là constant variable
    }

    public static void main(String[] args) {
        System.out.println(Config.LABEL);
        System.out.println("after constant");
        System.out.println(Config.PORT);
    }
}
```

Chạy:

```bash
javac ConstantsDemo.java
java ConstantsDemo
```

Stdout:

```text
DEV
after constant
Config initialized
8080
```

`Config.LABEL` là compile-time constant nên code sử dụng có thể được compiler thay trực tiếp bằng `"DEV"`; cách truy cập này **không khởi tạo** `Config`. Trong khi đó `Config.PORT` là một đối tượng `Integer`, không phải constant variable; đọc trường `static` này kích hoạt `Config` initialization trước khi in `8080`.

Vì vậy, câu “đọc một `static final` sẽ khởi tạo class” **không đúng cho mọi trường hợp**. Đừng dựa riêng vào hai từ khóa `static final`; phải xét kiểu và biểu thức khởi tạo.

## 5. Cách dùng đúng trong Reflection và hệ thống plugin

### Trường hợp chỉ muốn khám phá metadata

Ví dụ loader đang có một tên lớp plugin và cần kiểm tra interface hoặc constructor trước khi quyết định sử dụng:

```java
Class<?> candidate = Class.forName(pluginClassName, false, pluginLoader);

if (!Runnable.class.isAssignableFrom(candidate)) {
    throw new IllegalArgumentException("Plugin must implement Runnable");
}

var constructor = candidate.getDeclaredConstructor();
```

Đây là **đoạn minh họa** đặt trong luồng xử lý đã có biến `pluginClassName` và `pluginLoader`, không phải chương trình độc lập. Kiểm tra `isAssignableFrom` và lấy metadata constructor không tự yêu cầu chạy khối `static` của candidate. Việc nạp/link có thể vẫn xảy ra, nên các lỗi class/dependency vẫn có thể xuất hiện trước initialization.

### Trường hợp thực sự cần tạo plugin

Sau khi xác thực metadata và bảo đảm quyền truy cập:

```java
Runnable plugin = (Runnable) constructor.newInstance();
plugin.run();
```

`newInstance()` là bước có khả năng kích hoạt **initialization class**, sau đó mới tạo instance. Ví dụ giả định class có constructor không tham số mà mã gọi được phép truy cập. Nếu plugin không có constructor thích hợp, bị giới hạn module/package hoặc có lỗi trong constructor, cần xử lý riêng.

Nếu chỉ cần tra cứu cấu trúc class, hãy chủ động chọn `Class.forName(name, false, loader)`. Nếu mục tiêu là thực thi logic khởi tạo, phiên bản `true` hoặc một thao tác sử dụng chủ động là thích hợp hơn. Tránh dùng `Class.forName(name)` chỉ để “lấy metadata” trong ứng dụng có static initializer gây side effect (đăng ký driver, mở kết nối, nạp cấu hình, thao tác file...).

## 6. Lỗi và hiện tượng thường gặp

| Hiện tượng / exception | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| `ClassNotFoundException` | Loader không tìm được tên nhị phân được yêu cầu qua API nạp lớp. | Kiểm tra binary name, classpath/module path và loader được truyền vào. |
| `NoClassDefFoundError` | Định nghĩa cần thiết không sẵn sàng ở runtime hoặc JVM đã đánh dấu lớp bị lỗi khởi tạo ở lần trước. | Kiểm tra dependency runtime và lỗi gốc xuất hiện trước đó. |
| `ExceptionInInitializerError` | Logic khởi tạo tĩnh ném exception không phải `Error`; lỗi được JVM bọc khi initialization thất bại. | Xem cause và code trong field initializer / `static` block. |
| `IllegalAccessException` hoặc `InaccessibleObjectException` | Reflection truy cập member không phù hợp access rules hay module encapsulation. | Kiểm tra visibility, module `exports`/`opens`; không mặc định rằng `setAccessible(true)` luôn thành công. |
| `InvocationTargetException` | Method hoặc constructor được gọi qua Reflection đã ném exception. | Đọc `getCause()` để biết lỗi của code được gọi. |

Nếu `<clinit>` thất bại, JVM coi class ở trạng thái khởi tạo lỗi; lần sử dụng tiếp theo có thể nhận `NoClassDefFoundError`, chứ không tự chạy lại toàn bộ `static` initializer như chưa có chuyện gì xảy ra.

JVM phối hợp initialization giữa các thread: khi một thread đang khởi tạo lớp, thread khác cần dùng chủ động thường phải chờ. Với một đối tượng `Class` đã khởi tạo thành công, `<clinit>` không chạy lại ở mỗi lần gọi method hay tạo instance. Tuy nhiên, cùng **binary name** nhưng được định nghĩa bởi **hai class loader khác nhau** là hai runtime class khác nhau và mỗi class có vòng đời khởi tạo riêng.

Để chẩn đoán thời điểm JVM nạp/khởi tạo lớp, Java hiện đại có unified logging:

```bash
java -Xlog:class+load=info ClassLifecycleDemo
```

Lệnh sẽ tạo **rất nhiều** dòng log từ JVM/JDK; hãy lọc theo tên class quan tâm. Log `class+load` thể hiện sự kiện nạp, **không nên dùng riêng nó để kết luận lúc `<clinit>` thực thi**. Dòng `Target <clinit>` do ví dụ chủ động in ra là bằng chứng trực tiếp cho initialization của `Target`.

## 7. Những nhầm lẫn cần tránh

1. **“Đã gọi `SomeClass.class` nghĩa là khối `static` đã chạy.”** Sai: đó là thao tác lấy `Class` reference.
2. **“`ClassLoader.loadClass` và `Class.forName(String)` giống nhau.”** Sai về tác dụng mặc định: lời gọi `forName` một tham số yêu cầu initialization.
3. **“Đọc metadata bằng Reflection luôn thực thi code của class.”** Sai: tra cứu `Method`/`Field` khác với invocation hoặc truy cập giá trị trường tĩnh.
4. **“Mỗi lần tạo đối tượng thì khối `static` chạy lại.”** Sai: initializer tĩnh chạy theo vòng đời khởi tạo của runtime class; constructor chạy cho từng lần tạo instance.
5. **“Mọi `static final` đều kích hoạt class khi được đọc.”** Sai: constant variable có thể được inline, như `Config.LABEL`.
6. **“Tên class giống nhau nghĩa là cùng `Class`.”** Chưa đủ: định danh runtime phụ thuộc **binary name và defining class loader**.

## 8. Tự kiểm tra nhanh

**Câu 1.** `Class<?> c = Service.class;` rồi `c.getDeclaredMethods();` có bắt buộc chạy `Service` static block không?

**Trả lời:** Không. Hai bước này lấy đối tượng `Class` và metadata; chúng không phải hành động chủ động khởi tạo `Service`.

**Câu 2.** `Class.forName("demo.Service", false, loader)` trả về `Class` thành công. Khi nào static initializer sẽ chạy?

**Trả lời:** Khi có yêu cầu initialization sau đó, như `Class.forName(..., true, loader)`, gọi static method hay tạo instance; lớp cũng có thể được khởi tạo bởi hành động chủ động khác theo JLS.

**Câu 3.** Vì sao `Constructor.newInstance()` có thể in hai nhóm log: static initializer và constructor?

**Trả lời:** Nếu class chưa được khởi tạo, JVM thực hiện class initialization trước; tiếp theo Reflection tạo instance và gọi constructor. Các lần tạo instance kế tiếp vẫn gọi constructor nhưng không lặp lại static initializer thành công.

**Câu 4.** Cùng tên `demo.Plugin` được nạp bởi hai class loader độc lập có dùng chung một lần khởi tạo không?

**Trả lời:** Không, nếu mỗi loader thực sự **định nghĩa** một class riêng. Mỗi runtime class có đối tượng `Class` và trạng thái khởi tạo riêng; nếu loader chỉ ủy quyền và cùng nhận một class đã được loader cha định nghĩa thì chúng vẫn tham chiếu cùng runtime class.

## Tài liệu chuẩn

- **Java Language Specification §12.2–§12.4**: loading, linking, initialization; đặc biệt §12.4.1 về thời điểm initialization.
- **Java Virtual Machine Specification §5**: loading, linking, initialization và trạng thái runtime.
- Java SE API: `java.lang.Class` (đặc biệt `forName`), `java.lang.ClassLoader`, `java.lang.reflect.Method`, `java.lang.reflect.Constructor`.

**Ghi nhớ:** **Loading giúp JVM biết lớp là gì; linking chuẩn bị và kiểm tra định nghĩa; initialization mới chạy khối/biểu thức `static`; tạo instance mới chạy constructor.** Reflection có thể làm việc với metadata trước khi class được khởi tạo, nên hãy chọn API theo đúng mục đích.