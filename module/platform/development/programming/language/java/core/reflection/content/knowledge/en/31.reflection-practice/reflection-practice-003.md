# Tạo factory từ constructor có kiểu và thông báo lỗi rõ ràng — Java Reflection

## 1. Bài toán thực hành

Giả sử hệ thống có nhiều implementation của interface `Report` và muốn tạo instance tương ứng tại runtime. Mỗi implementation có một **constructor nhận `String title`**. Caller cần:

- Yêu cầu factory tạo instance với **đúng kiểu `T extends Report`**, không phải nhận `Object` rồi ép kiểu tràn lan.
- Kiểm tra constructor mong đợi **một lần khi tạo factory**, thay vì tìm lại metadata trong mọi request.
- Nêu rõ lỗi thiếu class, sai contract, thiếu chữ ký constructor, constructor không public, không thể instantiate, hay **lỗi xuất phát từ chính thân constructor**.
- Giữ nguyên `cause` và stack trace khi bọc exception, giúp người vận hành biết sai do cấu hình/Reflection hay do mã nghiệp vụ.

Thiết kế mong muốn:

```java
TypedFactory<PdfReport> factory = TypedFactory.forClass(PdfReport.class);
PdfReport report = factory.create("Monthly");
System.out.println(report.render()); // PDF: Monthly
```

Đây là mảnh minh họa dùng các class được định nghĩa đầy đủ ở phần 5. `TypedFactory<PdfReport>` giúp trình biên dịch biết `create(...)` trả về `PdfReport`, còn Reflection chỉ được dùng trong lớp factory.

**Ý tưởng:** gom rủi ro Reflection vào một ranh giới nhỏ, biểu diễn phần còn lại của ứng dụng qua interface và kiểu generic. Factory không cần biến mọi lệnh gọi Java thành `Method.invoke`; sau khi tạo đối tượng, dùng đa hình thông thường.

## 2. “Constructor có kiểu” nghĩa là gì?

API `java.lang.reflect.Constructor<T>` giữ thông tin kiểu instance sẽ được tạo:

```java
Class<PdfReport> type = PdfReport.class;
Constructor<PdfReport> ctor = type.getConstructor(String.class);
PdfReport report = ctor.newInstance("Monthly");
```

Đoạn minh họa trên cần `import java.lang.reflect.Constructor;` và các class từ ví dụ đầy đủ bên dưới; nó phát sinh checked reflection exceptions nên phương thức bao quanh phải `throws` hoặc `catch` thích hợp.

Các thành phần:

| Thành phần | Ý nghĩa |
|---|---|
| `Class<T>` | Runtime token đại diện cho kiểu cụ thể `T` |
| `Constructor<T>` | Metadata constructor tạo instance tương ứng với `T` |
| `type.getConstructor(String.class)` | Tra constructor **public**, có **chính xác một** tham số khai báo kiểu `String` |
| `constructor.newInstance(title)` | Kiểm tra điều kiện gọi và chạy thân constructor, trả `T` nếu thành công |
| `TypedFactory<T extends Report>` | Gói constructor và cung cấp API tạo mới có kiểu, ràng buộc kiểu trả về theo `Report` |

Trong factory generic:

```java
public final class TypedFactory<T extends Report> {
    private final Constructor<T> constructor;
    // Các thành viên khác...
}
```

Đây là mảnh khai báo thiết kế; class chạy đầy đủ nằm ở phần 5.

### Điều type safety đảm bảo — và không đảm bảo

`TypedFactory<PdfReport>.create(...)` trả về `PdfReport` tại compile time. Dùng `Class<T>` lấy từ literal `PdfReport.class` giúp các bước tra cứu an toàn hơn kiểu `Class<?>` và cast `(T) rawObject` không được kiểm soát.

Tuy nhiên, **generic không làm runtime lookup biến thành compile-time lookup**:

- Lớp có thể thiếu constructor `public PdfReport(String)`.
- Constructor có thể nằm ở phạm vi `private` hoặc `protected`.
- Thân constructor có thể ném `IllegalArgumentException`, `IOException`, `Error`, v.v.
- Trong các môi trường module/class loader, vẫn có thể có lỗi access, linkage hoặc class initialization.

Factory phải chẩn đoán rõ ràng các điểm này. Không hứa rằng vì sử dụng `Constructor<T>` nên Reflection không thể lỗi tại runtime.

## 3. Chọn đúng constructor: public, declared, signature và class hợp lệ

Hai API thường gặp:

```java
type.getConstructor(String.class);
type.getDeclaredConstructor(String.class);
```

- `getConstructor(...)` tìm **constructor public** với parameter types được chỉ định.
- `getDeclaredConstructor(...)` tìm constructor khai báo ngay trong class, bao gồm non-public.
- Constructor **không được kế thừa** từ superclass: không có cơ chế tìm public inherited constructor như method.
- Hai API tra cứu trên dựa vào **danh sách kiểu tham số chính xác**. Chúng không tự boxing `int` thành `Integer`, không tự chọn overload hoặc convert `CharSequence` thành `String`.
- `Class.getConstructor(...)` ném `NoSuchMethodException` khi không có constructor public đúng signature, kể cả khi tồn tại private constructor cùng signature.
- Constructor không phải method thông thường; không tra bằng `getMethod("ClassName", ...)`.

Với parameter `String`:

| Constructor thực tế | `getConstructor(String.class)` |
|---|---|
| `public PdfReport(String title)` | Tìm được |
| `private PdfReport(String title)` | Ném `NoSuchMethodException` |
| `public PdfReport(CharSequence title)` | Ném `NoSuchMethodException` |
| `public PdfReport()` | Ném `NoSuchMethodException` |
| `public PdfReport(String title, int version)` | Ném `NoSuchMethodException` |
| `public PdfReport(String... values)` | Ném `NoSuchMethodException` nếu tìm bằng `String.class`, vì kiểu tham số ở bytecode là `String[].class` |

**Không tự động “thử tất cả constructor cho tới khi một cái chạy được”**: điều đó khiến API factory khó đoán và có thể thực thi code không mong muốn. Quy định rõ chữ ký contract; khi không khớp, báo lỗi cấu hình có hành động sửa cụ thể.

Trước khi tạo instance cần lưu ý `abstract class` và `interface` không thể được instantiate theo cách này. Ví dụ chọn kiểm tra sớm trong factory để sinh thông báo rõ ràng. Với enum, record, member class không static, anonymous/local class hoặc lớp từ JPMS module, cấu trúc/khả năng khởi tạo có các ràng buộc riêng; không ép mọi class vào hợp đồng `(String)`.

## 4. Thiết kế factory và các nhóm lỗi

Ở bài thực hành, ta chia lỗi thành hai ngoại lệ runtime riêng:

- `FactoryConfigurationException`: thiết lập factory không hợp lệ — class không tồn tại, không implement `Report`, trừu tượng, không có constructor public `(String)`, hoặc kiểm tra metadata bị chặn. Đây thường là lỗi của deploy/config/plugin contract.
- `FactoryCreationException`: factory đã được tạo nhưng **tạo instance thất bại** — constructor đích ném lỗi, hoặc bước invocation gặp vấn đề về access/arguments/instantiation.

Cả hai giữ một `Throwable cause`, không chỉ thông báo chuỗi. Mẫu thông điệp nên nêu **loại lỗi, class, signature và nguyên nhân gốc**:

```text
Missing public constructor (String) on WrongConstructor
Constructor of FailingReport failed: IllegalArgumentException: invalid title
```

Không nên viết duy nhất `"Cannot create object"` hoặc `"Reflection failed"`: người sửa không biết phải đổi cấu hình, sửa constructor, hay sửa input.

### Ba giai đoạn có trách nhiệm khác nhau

```text
input Class<T> hoặc configured class name
             |
             v
[1] xác minh class + contract T extends Report
             |
             v
[2] resolve và cache public Constructor<T>(String)
             |
             v
[3] create(title) -> Constructor.newInstance(title)
             |
     +-------+-----------------------+
     |                               |
     v                               v
Reflection invocation lỗi      Constructor body ném Throwable
IllegalAccessException,        InvocationTargetException
InstantiationException, ...                |
     |                                  getCause()
     v                                      v
FactoryCreationException       FactoryCreationException
(với cause gốc)                  (với cause của target)
```

Việc **tra cứu constructor được thực hiện trước** giúp lỗi thiếu constructor xuất hiện ngay tại `forClass`, thay vì chờ tới request đầu tiên. Đây là kiểu **fail fast** hữu ích khi factory được tạo trong bước bootstrap.

## 5. Ví dụ Java 17+ hoàn chỉnh, có thông báo lỗi rõ ràng

Tạo file duy nhất **`TypedFactoryDemo.java`**:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Modifier;
import java.util.Objects;

public class TypedFactoryDemo {
    public interface Report {
        String render();
    }

    public static final class PdfReport implements Report {
        private final String title;

        public PdfReport(String title) {
            this.title = Objects.requireNonNull(title, "title");
        }

        @Override
        public String render() {
            return "PDF: " + title;
        }
    }

    public static final class WrongConstructor implements Report {
        public WrongConstructor(int pages) {}

        @Override
        public String render() {
            return "unavailable";
        }
    }

    public static final class PrivateReport implements Report {
        private PrivateReport(String title) {}

        @Override
        public String render() {
            return "private";
        }
    }

    public abstract static class AbstractReport implements Report {
        public AbstractReport(String title) {}
    }

    public static final class FailingReport implements Report {
        public FailingReport(String title) {
            throw new IllegalArgumentException("invalid title");
        }

        @Override
        public String render() {
            return "unavailable";
        }
    }

    public static final class FactoryConfigurationException extends RuntimeException {
        public FactoryConfigurationException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static final class FactoryCreationException extends RuntimeException {
        public FactoryCreationException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static final class TypedFactory<T extends Report> {
        private final Class<T> type;
        private final Constructor<T> constructor;

        private TypedFactory(Class<T> type, Constructor<T> constructor) {
            this.type = type;
            this.constructor = constructor;
        }

        public static <T extends Report> TypedFactory<T> forClass(Class<T> type) {
            Objects.requireNonNull(type, "type");
            if (type.isInterface() || Modifier.isAbstract(type.getModifiers())) {
                throw new FactoryConfigurationException(
                        "Cannot instantiate abstract type: " + type.getSimpleName(), null);
            }
            try {
                return new TypedFactory<>(type, type.getConstructor(String.class));
            } catch (NoSuchMethodException e) {
                throw new FactoryConfigurationException(
                        "Missing public constructor (String) on " + type.getSimpleName(), e);
            } catch (SecurityException e) {
                throw new FactoryConfigurationException(
                        "Constructor lookup denied for " + type.getSimpleName(), e);
            }
        }

        public T create(String title) {
            try {
                return constructor.newInstance(title);
            } catch (InvocationTargetException e) {
                Throwable cause = e.getCause();
                throw new FactoryCreationException(
                        "Constructor of " + type.getSimpleName() + " failed: "
                                + cause.getClass().getSimpleName() + ": " + cause.getMessage(),
                        cause);
            } catch (InstantiationException | IllegalAccessException | IllegalArgumentException e) {
                throw new FactoryCreationException(
                        "Cannot create " + type.getSimpleName() + " with (String)", e);
            }
        }

        public static TypedFactory<? extends Report> fromName(String className) {
            Objects.requireNonNull(className, "className");
            try {
                Class<? extends Report> type =
                        Class.forName(className).asSubclass(Report.class);
                return forClass(type);
            } catch (ClassNotFoundException e) {
                throw new FactoryConfigurationException(
                        "Cannot load class: " + className, e);
            } catch (ClassCastException e) {
                throw new FactoryConfigurationException(
                        "Configured class " + className + " does not implement Report", e);
            }
        }
    }

    public static void main(String[] args) {
        TypedFactory<PdfReport> pdf = TypedFactory.forClass(PdfReport.class);
        PdfReport created = pdf.create("Monthly");
        System.out.println("success: " + created.render());

        try {
            TypedFactory.forClass(WrongConstructor.class);
        } catch (FactoryConfigurationException e) {
            System.out.println("wrong signature: " + e.getMessage());
        }

        try {
            TypedFactory.forClass(PrivateReport.class);
        } catch (FactoryConfigurationException e) {
            System.out.println("private constructor: " + e.getMessage());
        }

        try {
            TypedFactory.forClass(AbstractReport.class);
        } catch (FactoryConfigurationException e) {
            System.out.println("abstract class: " + e.getMessage());
        }

        try {
            TypedFactory.forClass(FailingReport.class).create("bad");
        } catch (FactoryCreationException e) {
            System.out.println("target failure: " + e.getMessage());
            System.out.println("target cause: " + e.getCause().getClass().getSimpleName());
        }

        try {
            TypedFactory.fromName("java.lang.String");
        } catch (FactoryConfigurationException e) {
            System.out.println("wrong type: " + e.getMessage());
        }

        try {
            TypedFactory.fromName("demo.NotFound");
        } catch (FactoryConfigurationException e) {
            System.out.println("missing type: " + e.getMessage());
        }
    }
}
```

Chạy tại thư mục chứa file:

```bash
javac --release 17 TypedFactoryDemo.java
java TypedFactoryDemo
```

**Stdout thực tế** khi biên dịch/chạy chương trình:

```text
success: PDF: Monthly
wrong signature: Missing public constructor (String) on WrongConstructor
private constructor: Missing public constructor (String) on PrivateReport
abstract class: Cannot instantiate abstract type: AbstractReport
target failure: Constructor of FailingReport failed: IllegalArgumentException: invalid title
target cause: IllegalArgumentException
wrong type: Configured class java.lang.String does not implement Report
missing type: Cannot load class: demo.NotFound
```

Mã đã được biên dịch bằng `javac --release 17` và chạy thành công. Nó sử dụng public nested classes trong một file để tiện sao chép; trong ứng dụng thực tế nên tách `TypedFactory` và implementation thành các class/package được quản lý rõ ràng.

## 6. Đọc kết quả: phân loại đúng từng trường hợp

**Đường thành công:** `TypedFactory.forClass(PdfReport.class)` nhận một `Class<PdfReport>`; `getConstructor(String.class)` tìm constructor public đúng chữ ký. `create("Monthly")` trả một đối tượng kiểu `PdfReport`; caller gọi `render()` bình thường, không cần `Method.invoke`.

**Sai chữ ký:** `WrongConstructor` chỉ có constructor `(int)`. Đây không phải lỗi “tham số runtime không chuyển được”; factory phát hiện **thiếu constructor `(String)` ngay tại lookup**, bắt `NoSuchMethodException` và chuyển thành `FactoryConfigurationException` có thông tin rõ ràng.

**Constructor private:** `PrivateReport` có `(String)` nhưng private. `getConstructor(String.class)` không trả constructor này; thông báo “missing public constructor” chính xác theo contract của factory. Không tự tìm private constructor rồi `setAccessible(true)` vì điều đó làm đổi hợp đồng truy cập và có thể vi phạm giới hạn JPMS.

**Abstract class:** `AbstractReport` là một type hợp lệ theo `T extends Report` nhưng không instantiate trực tiếp được. Chặn trước bằng `Modifier.isAbstract` để báo lỗi cấu hình thay vì để `Constructor.newInstance` thất bại muộn.

**Lỗi trong thân constructor:** `FailingReport(String)` hợp lệ, nhưng khi chạy ném `IllegalArgumentException("invalid title")`. `Constructor.newInstance` **bọc lỗi của mã đích trong `InvocationTargetException`**. Factory dùng `e.getCause()` để lấy lại `IllegalArgumentException`, tạo `FactoryCreationException` với cause gốc và thông báo có loại lỗi + nội dung.

**Class sai contract:** `Class.forName("java.lang.String")` tìm được class, nhưng `String` không implement `Report`. `asSubclass(Report.class)` ném `ClassCastException`; factory chuyển sang thông báo cấu hình “does not implement Report”. Không ép kiểu `(Class<Report>)` bằng unchecked cast để che mất lỗi.

**Class không tồn tại:** `Class.forName("demo.NotFound")` ném `ClassNotFoundException`. Đây là lỗi **tìm class**, khác với `NoSuchMethodException` khi class tồn tại nhưng constructor không khớp.

## 7. Vì sao factory cần giữ nguyên cause?

Nếu chỉ ghi:

```java
catch (Exception e) {
    throw new RuntimeException("Create failed");
}
```

thì stack trace của lỗi gốc bị mất khỏi **chuỗi nguyên nhân**; rất khó biết nguyên nhân là constructor thiếu, security restriction, null input hay bug bên trong implementation.

Giữ cause:

```java
catch (InvocationTargetException e) {
    Throwable targetFailure = e.getCause();
    throw new FactoryCreationException(
            "Constructor of " + type.getName() + " failed",
            targetFailure);
}
```

Đoạn này là **mảnh code minh họa** nằm trong `TypedFactory<T>`, với biến `type` và `FactoryCreationException` đã tồn tại. Khi log exception được ném ra, stack trace có đường đi qua lớp factory rồi đến lỗi của constructor. Không chỉ log `getMessage()` nếu cần phân tích stack trace.

### Phân biệt wrapper ngoài và nguyên nhân bên trong

| Giai đoạn | Exception gốc/quan sát | Nên báo |
|---|---|---|
| `getConstructor` không tìm thấy chữ ký public | `NoSuchMethodException` | Cấu hình sai: thiếu public constructor `(String)` |
| `Class.forName` không tìm thấy class | `ClassNotFoundException` | Cấu hình sai: class name/class loader/classpath |
| `asSubclass` không thỏa contract | `ClassCastException` | Cấu hình sai: implementation không phải subtype của interface |
| `Constructor.newInstance` thiếu quyền | `IllegalAccessException` | Không thể gọi constructor do access control/module |
| Constructor body ném exception | `InvocationTargetException` bọc Throwable | Thất bại khi tạo object: **nguyên nhân thực trong `getCause()`** |
| Lỗi không tương thích lớp/runtime | `LinkageError`, `ExceptionInInitializerError` ... | Lỗi linkage/khởi tạo JVM, không nhất thiết là lỗi từ body constructor |

**Điểm quan trọng:** `InvocationTargetException` là wrapper của Reflection invocation; `FactoryCreationException` trong ví dụ là **wrapper do ứng dụng tự định nghĩa**. Hai lớp này không phải một. Người sử dụng factory chỉ phải hiểu contract do ứng dụng công bố; người bảo trì có thể xem cause để điều tra gốc.

Trong production, quyết định có bọc hay **truyền tiếp `Error` nghiêm trọng** (ví dụ `OutOfMemoryError`) phải có chính sách riêng. Ví dụ chọn một loại exception đầu ra dễ hiểu cho mục đích học, nhưng không nên nuốt `Error` hoặc biến mọi lỗi JVM nghiêm trọng thành lỗi nghiệp vụ có thể retry.

## 8. Factory có kiểu khi class được cấu hình bằng String

Khi runtime nhận tên implementation từ file cấu hình, `Class.forName(className)` trả `Class<?>`. Để bảo toàn contract `Report`, dùng:

```java
Class<? extends Report> reportType =
        Class.forName(configuredName).asSubclass(Report.class);
TypedFactory<? extends Report> factory =
        TypedFactory.forClass(reportType);
Report report = factory.create("Monthly");
```

Đây là **mảnh code minh họa** với `configuredName` do ứng dụng cung cấp và các class ở ví dụ đầy đủ. Khi class được quyết định từ chuỗi runtime, compiler không thể biết trước nó là `PdfReport` hay `OtherReport`; do đó kiểu trả về an toàn là `? extends Report` hoặc `Report`, **không phải `PdfReport`**.

Nếu cần caller nhận chính xác `PdfReport`, truyền `PdfReport.class` trực tiếp hoặc kiểm tra/ép subtype một cách tường minh trước khi dùng.

**Không nạp class từ chuỗi do người dùng không tin cậy gửi lên mà không kiểm soát.** `Class.forName(String)` mặc định có thể **khởi tạo class**; initializer có thể chạy code dù bạn chưa gọi constructor. Với hệ plugin, nên dùng allowlist/registry, tên implementation được xác minh, class loader được phép, và tránh tiết lộ toàn bộ classpath qua message trả cho client.

Nếu muốn tách load class khỏi initialization, overload:

```java
Class<?> rawType = Class.forName(
        configuredName,
        false,
        Thread.currentThread().getContextClassLoader());
```

Đây là mảnh code minh họa. `initialize=false` chỉ trì hoãn initialization; khi instantiate về sau, class có thể vẫn bị initialize và phát sinh lỗi. Thread context class loader có thể không phù hợp trong mọi ứng dụng: quyết định loader theo kiến trúc plugin/module, không mặc định luôn đúng. Trong hệ JPMS và khi dùng nhiều class loader, kiểm tra visibility, module boundaries và hành vi load thực tế.

## 9. Vì sao chọn resolve constructor một lần, rồi cache?

Thiết kế giữ:

```java
private final Class<T> type;
private final Constructor<T> constructor;
```

Trong mỗi `TypedFactory<T>` instance, `getConstructor(String.class)` chỉ chạy trong `forClass`; `create` dùng lại `Constructor<T>`. Cách này:

1. **Fail fast** khi cấu hình implementation không thỏa constructor contract.
2. Tránh lặp lại lookup metadata mỗi lần tạo object.
3. Gom logging/exception translation một chỗ.
4. Tăng khả năng test vì mỗi trường hợp lỗi đi qua một API factory nhất quán.

Tuy nhiên, **constructor body vẫn chạy cho mỗi `create(...)`** và có thể thất bại theo dữ liệu đầu vào. Cache metadata không phải cache instance, không đồng nghĩa factory singleton hay thread-safe của chính object được tạo.

Một factory bất biến chỉ giữ `Class<T>` và `Constructor<T>` có thể được tái sử dụng từ nhiều thread; nhưng nếu implement constructor tạo shared mutable state hoặc chạm tài nguyên dùng chung, thread safety của quá trình tạo vẫn phụ thuộc implementation và resource.

### Tránh memory leak với plugin/class loader

Một biến `static Map<Class<?>, TypedFactory<?>>` sống suốt vòng đời ứng dụng có thể giữ strong reference tới `Class`/`Constructor` và class loader plugin. Trong hệ có unload/redeploy, cân nhắc:

- Đặt factory trong vòng đời plugin rồi giải phóng registry khi plugin dừng.
- Gắn metadata theo class bằng `ClassValue` nếu phù hợp.
- Cẩn trọng khi dùng `WeakHashMap<Class<?>, ...>` vì value có thể tham chiếu ngược tới class, làm yếu key không còn hữu ích.
- Không cache bằng duy nhất chuỗi `getName()` khi có nhiều class loader, vì cùng binary name có thể là hai runtime classes khác nhau.

Việc cache cần cân nhắc theo profiling; với số lần khởi tạo rất ít, class factory đơn giản và kiểm tra chuẩn xác thường quan trọng hơn tối ưu vi mô.

## 10. Thông báo lỗi tốt: đủ dữ kiện nhưng không lộ bí mật

Thông báo cấu hình tốt có thể có mẫu:

```text
Cannot construct report implementation com.example.PdfReport:
expected public constructor (java.lang.String)
```

Trong hệ thống thực, nên có:

- **Thao tác:** load/verify constructor/create.
- **Class:** tên đầy đủ (`type.getName()`) để phân biệt package.
- **Expected signature:** ví dụ `(java.lang.String)`, không chỉ tên method chung chung.
- **Loại lỗi:** `NoSuchMethodException`, `IllegalAccessException`, hoặc failure từ target.
- **Root cause:** giữ bằng constructor exception nhận `cause`.
- **Ngữ cảnh có kiểm soát:** operation ID, plugin/module, class loader nếu cần điều tra.

Ví dụ sử dụng `getSimpleName()` cho stdout ngắn và ổn định; khi logging production có nhiều class cùng tên, nên dùng `getName()`, kèm module/loader khi cần.

Không đưa vào thông báo/log các giá trị nhạy cảm như password, token, dữ liệu khách hàng hoặc chuỗi đầu vào bí mật chỉ để debug. Có thể nói “constructor argument validation failed” và giữ root cause trong log nội bộ, thay vì phản chiếu nguyên văn input từ người dùng qua API công khai.

### Không nuốt lỗi thành null

Tránh:

```java
try {
    return constructor.newInstance(title);
} catch (Exception ignored) {
    return null;
}
```

Đây là **phản ví dụ** trong method trả `T`. Nếu object `null` được dùng về sau, caller sẽ nhận `NullPointerException` ở nơi không liên quan, làm mất stack trace của nguyên nhân ban đầu. Hãy ném lỗi có cấu trúc hoặc dùng kết quả kiểu `Result<T, Error>` được định nghĩa rõ theo hợp đồng ứng dụng.

## 11. Những lỗi thường gặp khi thiết kế factory Reflection

**1. Dùng raw type `Constructor` hoặc ép `(T) ctor.newInstance(...)` vô điều kiện.** Raw type loại bỏ thông tin compile-time; dùng `Class<T>` và `Constructor<T>`, hoặc `asSubclass(BaseType.class)` khi type đến từ runtime name.

**2. Gọi `getDeclaredConstructor` rồi mặc định nó gọi được.** Declared lookup có thể tìm private constructor, nhưng `newInstance` vẫn kiểm tra quyền. `setAccessible(true)` không bảo đảm vượt module access và không nên dùng chỉ để “lách” contract public constructor.

**3. Nhầm lookup error với target error.** Thiếu constructor là `NoSuchMethodException` lúc resolve; lỗi do code constructor ném thường nằm trong `InvocationTargetException.getCause()`. Xử lý chúng ở hai nhánh khác nhau.

**4. Bắt `Exception` chung rồi in `"Factory failed"`.** Loại bỏ chi tiết actionable; giữ nguyên cause và tách configuration vs creation.

**5. Dùng `type.newInstance()` đã deprecated.** Dùng `getDeclaredConstructor().newInstance()` hoặc `getConstructor(...).newInstance(...)`; hợp đồng exception của `Class.newInstance()` khác, đặc biệt khi constructor ném checked exceptions.

**6. Cho caller truyền danh sách `Object... args` mà không định nghĩa signature.** Dễ xuất hiện mismatched arity, boxing, varargs hoặc ép kiểu sai. Với factory `create(String)`, caller biết chính xác input contract.

**7. Không kiểm tra `interface`/`abstract`, constructor signature và service contract trước khi phục vụ request.** Lỗi bị phát hiện muộn, khó xác định cấu hình sai. Validate tại bootstrap khi có thể.

**8. Tưởng `Class.forName` chỉ “đọc metadata”.** Overload một tham số có thể kích hoạt class initialization. Class name từ input không đáng tin cần kiểm soát.

**9. Cache factory toàn cục qua strong Class key trong hệ plugin reload.** Có thể giữ class loader cũ. Chọn ownership và lifecycle cache rõ ràng.

**10. Tự retry constructor đích sau khi nó ném exception.** Constructor có thể đã tạo side effects trước khi thất bại (mở file, ghi DB, gửi request). Chỉ retry khi action idempotent và có chính sách retry cụ thể.

**11. Nhận thông báo từ Reflection là hợp đồng ổn định.** JDK/compiler có thể thay text message; test nên kiểm tra **loại exception, cause và phần message ứng dụng tự kiểm soát**.

## 12. Bài tập mở rộng

### Bài 1 — Factory không tham số

Thử viết `TypedFactory<T>` với `getConstructor()` và `create()`, rồi so sánh với interface `Supplier<T>`. Nếu toàn bộ implementation biết lúc compile time, factory bằng method reference (`PdfReport::new` khi constructor signature phù hợp) thường đơn giản hơn Reflection.

### Bài 2 — Factory nhận nhiều tham số

Đổi contract thành `create(String title, int pages)`; tra `type.getConstructor(String.class, int.class)`. Viết test cho trường hợp class chỉ có constructor `(String, Integer)`: Reflection **không tự tìm overload đó**.

### Bài 3 — Viết assertion trên exception

Dùng JUnit hoặc test harness của dự án để kiểm tra:
- `forClass(WrongConstructor.class)` ném `FactoryConfigurationException` với cause `NoSuchMethodException`.
- `forClass(PrivateReport.class)` báo **thiếu public constructor**.
- `forClass(AbstractReport.class)` báo abstract type.
- `forClass(FailingReport.class).create("bad")` ném `FactoryCreationException` với `getCause() instanceof IllegalArgumentException`.
- `fromName("java.lang.String")` báo class không thuộc `Report`.
- `forClass(PdfReport.class).create("ok")` trả đúng `PdfReport` và nội dung mong đợi.

### Bài 4 — Đăng ký plugin theo interface

Thay nhận tên class tùy ý bằng registry `Map<String, Class<? extends Report>>` đã validate. Client chọn một ID như `"pdf"` thay vì tên Java binary class trực tiếp; phần registry có thể được xây từ `ServiceLoader` khi cần plugin registration.

## 13. Checklist trước khi dùng trong hệ thống

1. **Contract rõ:** factory tạo kiểu `T extends Report` và cần đúng public constructor `(String)`.
2. **Typed metadata:** dùng `Class<T>`, `Constructor<T>`, không dùng raw casts tùy tiện.
3. **Fail fast:** kiểm tra class cụ thể, tính abstract, constructor signature khi tạo factory.
4. **Tách lỗi:** configuration/lookup khác create/invocation và exception do constructor đích ném.
5. **Preserve cause:** luôn giữ cause khi bọc, dùng thông báo có class + signature.
6. **Không bypass access vô điều kiện:** ưu tiên public constructor và API rõ, tôn trọng JPMS.
7. **An toàn runtime class name:** validate, allowlist và quản lý class loader; không nhận tùy ý input không tin cậy.
8. **Cache có vòng đời:** tránh lookup lặp, nhưng không giữ class loader plugin vô thời hạn.
9. **Test cả đường thành công và thất bại:** chú ý primitive/wrapper, abstract, private, target runtime exception.
10. **Giữ log có ích nhưng tối thiểu:** không rò rỉ input nhạy cảm và không nuốt root cause.

## 14. Tóm tắt

- `Class<T>` + `Constructor<T>` là nền tảng để tạo **factory Reflection có kiểu trả về**.
- `getConstructor(String.class)` ràng buộc rõ **public constructor với chính xác một tham số String**, và kiểm tra sớm ngay lúc cấu hình factory.
- `Constructor.newInstance` có thể bọc exception từ **thân constructor đích** trong `InvocationTargetException`; giữ `getCause()` khi chuyển sang exception ứng dụng.
- Thông báo lỗi tốt phân biệt **lỗi class/contract/constructor lookup** với **lỗi tạo instance/target logic**, không chỉ nói “Reflection failed”.
- Sau khi tạo thành công, gọi qua `Report`/`PdfReport` bình thường. Reflection nên nằm trong lớp factory nhỏ, có trách nhiệm và test rõ ràng.
