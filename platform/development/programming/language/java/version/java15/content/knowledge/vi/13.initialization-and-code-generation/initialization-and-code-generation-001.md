# Lookup.ensureInitialized và khởi tạo lớp theo yêu cầu trong Java 15+

## 1. Bài toán và mục tiêu

Java Virtual Machine (JVM) phân biệt **tải lớp (loading)**, **liên kết (linking)** và **khởi tạo lớp (initialization)**. Có một đối tượng `Class<?>` không có nghĩa khối `static { ... }` và bộ khởi tạo các trường `static` của lớp đó đã chạy.

Từ **Java 15**, `java.lang.invoke.MethodHandles.Lookup` cung cấp phương thức:

```java
Class<?> ensureInitialized(Class<?> targetClass) throws IllegalAccessException
```

Phương thức này bảo đảm lớp đích được khởi tạo theo quy tắc của JVM nếu trước đó chưa khởi tạo, với điều kiện lớp đó **truy cập được** từ đối tượng `Lookup`. Nó vẫn hiện diện trong JDK hiện đại; đây không phải API legacy hay preview. Trong Javadoc mới hơn, chữ ký có thể được trình bày với tham số kiểu generic `<T> Class<T>`, nhưng ý nghĩa và yêu cầu về quyền truy cập là như nhau.

Bạn học cách:

- Phân biệt tải, liên kết, khởi tạo và các tình huống có/không kích hoạt `<clinit>`.
- Gọi `lookup.ensureInitialized(type)` một cách có kiểm soát khi **đã có `Class<?>`**.
- Nhận biết trường hợp khởi tạo một lần, khởi tạo lại cùng thread, đồng bộ giữa các thread và lớp đã ở trạng thái lỗi.
- Xử lý `IllegalAccessException`, `IllegalArgumentException`, `ExceptionInInitializerError` và lỗi do trạng thái khởi tạo thất bại.
- Kết hợp `Lookup.defineHiddenClass(bytes, false)` với `ensureInitialized(...)` để **hoãn khởi tạo hidden class** đến đúng thời điểm.
- Viết bài kiểm chứng Java 15 chạy độc lập, có stdout xác định và không cần thư viện bên ngoài.

Lưu ý: `ensureInitialized` làm cho **khởi tạo xảy ra**, chứ không phải một API định nghĩa lớp mới, không thay thế dependency injection và không được dùng để vượt quyền truy cập.

## 2. Loading, linking và initialization khác nhau

Theo Java Language Specification §12:

| Giai đoạn | Việc xảy ra | Có chạy `static { ... }` không? |
| --- | --- | --- |
| **Loading** | JVM tìm/nhận bytecode và tạo đối tượng `Class` tương ứng | Không tự động chỉ vì loading |
| **Linking** | Kiểm tra bytecode (*verification*), chuẩn bị trường static (*preparation*), có thể giải quyết tham chiếu (*resolution*) | Không tự động chỉ vì linking |
| **Initialization** | Thực thi static field initializers và static initializer blocks theo thứ tự quy định | **Có** |

Ví dụ:

```java
public final class ServiceConfig {
    static {
        System.out.println("ServiceConfig initialized");
    }

    static int port = 8080;
}
```

Đây là **một định nghĩa lớp minh họa**, không có `main`. Việc biên dịch hoặc đơn thuần lấy `ServiceConfig.class` không bắt buộc phải chạy khối static. Nhưng dùng `ServiceConfig.port` (trường không phải compile-time constant), khởi tạo instance nếu có constructor phù hợp, gọi static method khai báo bởi lớp, hoặc chủ động gọi `ensureInitialized(ServiceConfig.class)` sẽ yêu cầu JVM khởi tạo lớp theo quy tắc tương ứng.

Điểm dễ nhầm: **`Class<?>` là metadata/đại diện kiểu, không phải trạng thái “chắc chắn đã khởi tạo”.** JVM không có API công khai đơn giản để hỏi “đã khởi tạo hay chưa?” mà vẫn bảo đảm không ảnh hưởng trạng thái. Thực tế ta quan sát static side effects trong môi trường test, hoặc dùng `ensureInitialized` khi hợp đồng đòi hỏi lớp đã được khởi tạo trước bước tiếp theo.

## 3. Cú pháp và hợp đồng `Lookup.ensureInitialized`

Giả sử bạn có `Class<?> target` và một đối tượng `MethodHandles.Lookup` đủ quyền:

```java
import java.lang.invoke.MethodHandles;

MethodHandles.Lookup lookup = MethodHandles.lookup();
Class<?> initializedType = lookup.ensureInitialized(target);
```

Đoạn trên thuộc một phương thức đã khai báo hoặc xử lý `IllegalAccessException` và đã có biến `target`; không phải chương trình Java độc lập.

Phương thức có ba điểm cần đọc đúng:

1. **Mục tiêu là đối tượng `Class`:** truyền `Class<?>` đã nhận; không truyền tên chuỗi và không phải gọi lại `Class.forName(...)`.
2. **Kiểm tra quyền của `Lookup`:** lớp đích phải **accessible** đối với lookup class và các access modes của `Lookup`. Nếu không, ném `IllegalAccessException`; có một reference `Class<?>` chưa đồng nghĩa có quyền khởi tạo tùy ý.
3. **Bảo đảm khởi tạo theo JVMS §5.5:** nếu chưa được khởi tạo, JVM thực hiện công việc khởi tạo; nếu đã hoàn tất, không thực thi lại `<clinit>`. Giá trị trả về là **cùng đối tượng `Class` đích**.

Javadoc hiện hành mô tả một ngoại lệ quan trọng: phương thức trở về khi class **đã khởi tạo đầy đủ** *hoặc đang được chính thread hiện tại khởi tạo*. Trường hợp thứ hai là khởi tạo đệ quy, được JVM xử lý theo quy tắc đồng bộ; vì vậy không nên diễn giải kết quả trong tình huống reentrant là bằng chứng `<clinit>` đã hoàn tất trước khi stack hiện tại trở về.

### Những đối số không hợp lệ

`ensureInitialized` cần **class/interface thực**, không dùng cho primitive, `void` hoặc array class:

```java
lookup.ensureInitialized(int.class);     // IllegalArgumentException
lookup.ensureInitialized(void.class);    // IllegalArgumentException
lookup.ensureInitialized(String[].class); // IllegalArgumentException
```

Đây là **các lời gọi cố ý ném ngoại lệ** khi có `Lookup lookup` hợp lệ. Array type không có bộ khởi tạo lớp riêng mà API này cần chạy. Với interface, JVM cũng thực hiện theo quy tắc khởi tạo interface, không mặc định rằng các superinterface đều bị khởi tạo cùng lúc.

### So sánh một số thao tác tương tự

| Thao tác | Công dụng | Có chủ động khởi tạo target? |
| --- | --- | --- |
| `ServiceConfig.class` | Lấy class literal | Không chỉ vì biểu thức này |
| `obj.getClass()` | Lấy Class của instance đang tồn tại | Instance đã đòi hỏi các điều kiện khởi tạo liên quan trước đó; `getClass()` không phải API khởi tạo |
| `Class.forName(name, false, loader)` | Tra cứu lớp thông thường theo binary name nhưng không yêu cầu initialization | **Không** nếu chỉ vì lời gọi này |
| `Class.forName(name)` | Tra cứu lớp thông thường theo tên và yêu cầu khởi tạo | **Có**, nếu cần và tìm thấy lớp |
| `lookup.accessClass(type)` | Xác nhận quyền truy cập lớp từ Lookup | Không có mục đích bảo đảm khởi tạo |
| `lookup.ensureInitialized(type)` | Khởi tạo class/interface **đã có tham chiếu Class** | **Có**, nếu chưa khởi tạo |
| `lookup.defineHiddenClass(bytes, false)` | Định nghĩa hidden class, hoãn khởi tạo | **Không yêu cầu khởi tạo ngay** |
| `lookup.defineHiddenClass(bytes, true)` | Định nghĩa và khởi tạo hidden class | **Có**, tại bước định nghĩa |

Các API trên giải quyết các mục tiêu khác nhau. **`ensureInitialized` đặc biệt hữu ích khi lớp đã có từ một cơ chế sinh mã/runtime, hoặc từ API trả `Class<?>` mà ứng dụng muốn điều khiển thời điểm chạy static initializer.**

## 4. Khởi tạo khi nào: những yếu tố kích hoạt thông thường

Theo JLS §12.4.1, việc khởi tạo xảy ra ngay trước một số **active uses**, tiêu biểu:

- Tạo instance của lớp.
- Gọi static method được khai báo bởi lớp đó.
- Gán giá trị cho static field của lớp.
- Đọc static field không phải compile-time constant, với quy tắc lớp thực sự khai báo field.
- Một số thao tác reflection và lời gọi API chủ động khởi tạo.

Ngược lại, đoạn này không phải bảo đảm khởi tạo:

```java
Class<?> type = ServiceConfig.class;
String typeName = type.getName();
```

Đặc biệt dễ nhầm với **compile-time constants**:

```java
public final class Constants {
    public static final int PORT = 8080; // Compile-time constant.
    static {
        System.out.println("Constants initialized");
    }
}
```

Nếu mã khác chỉ đọc `Constants.PORT` và compiler đã inline hằng, thao tác đó **không nhất thiết khởi tạo `Constants`**. Nhưng `lookup.ensureInitialized(Constants.class)` thì chủ động yêu cầu khởi tạo. Cần nhớ sự khác nhau giữa static field initializer có biểu thức tính ở runtime và `static final` primitive/String được gán bằng constant expression.

### Thứ tự và mối quan hệ với lớp cha

Khi khởi tạo class, JVM phải xử lý các superclass chưa được khởi tạo, và những superinterfaces được quy định cần khởi tạo (ví dụ interface có default method) theo luật JVMS/JLS. Sau đó static initializers và field initializers của chính class được thực thi theo thứ tự văn bản của chúng, trong khuôn khổ quy tắc ngôn ngữ.

Vì thế `ensureInitialized(Child.class)` không có nghĩa “chỉ chạy đúng một khối static của Child”. Nó có thể dẫn đến khởi tạo các kiểu liên quan theo quy tắc chuẩn. Khi side effect trong static initialization phụ thuộc vào hệ thống ngoài, cần thiết kế rõ thứ tự, khả năng thất bại và tránh vòng phụ thuộc.

## 5. Chương trình Java 15 đầy đủ: khởi tạo theo yêu cầu và hidden class

Ví dụ này kiểm tra **bốn nhóm tình huống**:

1. Lấy `Normal.class` nhưng không khởi tạo; sau đó gọi `ensureInitialized` làm static block chạy **một lần**.
2. Truyền primitive hoặc dùng lookup không có quyền: nhận ngoại lệ cụ thể.
3. Định nghĩa một **hidden class** với `initialize=false`; chính `ensureInitialized` của lookup trả về từ `defineHiddenClass` mới kích hoạt static initializer.
4. Static initializer thất bại: lần đầu có `ExceptionInInitializerError`, lần tiếp theo trên cùng class đã bị đánh dấu lỗi nhận `NoClassDefFoundError`.

Lưu trọn tệp **`EnsureInitializedDemo.java`**:

```java
import java.io.InputStream;
import java.lang.invoke.MethodHandles;

public final class EnsureInitializedDemo {
    private static final class Normal {
        static {
            System.out.println("Normal.<clinit>");
        }

        static final int COMPUTED =
                40 + Integer.getInteger("example.delta", 2);
    }

    public static final class Template {
        static {
            System.out.println("Template.<clinit> (hidden copy)");
        }

        public static String message() {
            return "hello";
        }
    }

    private static final class Restricted {
        static {
            System.out.println("Restricted.<clinit>");
        }
    }

    public static final class Broken {
        static final int VALUE = fail();

        private static int fail() {
            throw new IllegalStateException("boom");
        }
    }

    public static void main(String[] args) throws Exception {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        Class<Normal> normalClass = Normal.class;
        System.out.println("got Normal.class");
        System.out.println("returned same class: "
                + (lookup.ensureInitialized(normalClass) == normalClass));
        System.out.println("normal computed: " + Normal.COMPUTED);
        lookup.ensureInitialized(normalClass);
        System.out.println("normal ensured again");

        try {
            lookup.ensureInitialized(int.class);
        } catch (IllegalArgumentException expected) {
            System.out.println("primitive: IllegalArgumentException");
        }

        try {
            MethodHandles.publicLookup().ensureInitialized(Restricted.class);
        } catch (IllegalAccessException expected) {
            System.out.println("inaccessible: IllegalAccessException");
        }

        byte[] bytes;
        try (InputStream in = EnsureInitializedDemo.class.getResourceAsStream(
                "EnsureInitializedDemo$Template.class")) {
            if (in == null) {
                throw new IllegalStateException("Template.class bytes missing");
            }
            bytes = in.readAllBytes();
        }

        MethodHandles.Lookup hiddenLookup =
                lookup.defineHiddenClass(bytes, false);
        Class<?> hiddenClass = hiddenLookup.lookupClass();

        System.out.println("hidden class defined: " + hiddenClass.isHidden());
        System.out.println("before hidden ensure");
        System.out.println("returned same hidden class: "
                + (hiddenLookup.ensureInitialized(hiddenClass) == hiddenClass));
        System.out.println("after hidden ensure");
        hiddenLookup.ensureInitialized(hiddenClass);
        System.out.println("hidden ensured again");

        try {
            lookup.ensureInitialized(Broken.class);
        } catch (ExceptionInInitializerError expected) {
            System.out.println("first failure: "
                    + expected.getCause().getClass().getSimpleName());
        }

        try {
            lookup.ensureInitialized(Broken.class);
        } catch (NoClassDefFoundError expected) {
            System.out.println("second failure: NoClassDefFoundError");
        }
    }
}
```

Dùng JDK hỗ trợ đích Java 15:

```bash
javac --release 15 EnsureInitializedDemo.java
java EnsureInitializedDemo
```

**Stdout chính xác khi không đặt system property `example.delta`:**

```text
got Normal.class
Normal.<clinit>
returned same class: true
normal computed: 42
normal ensured again
primitive: IllegalArgumentException
inaccessible: IllegalAccessException
hidden class defined: true
before hidden ensure
Template.<clinit> (hidden copy)
returned same hidden class: true
after hidden ensure
hidden ensured again
first failure: IllegalStateException
second failure: NoClassDefFoundError
```

Kết quả trên đã được kiểm chứng bằng **biên dịch `javac --release 15` và chạy trên JDK hiện đại**. Không cần JUnit hay cơ sở dữ liệu. Nếu bạn chạy với `-Dexample.delta=5`, giá trị `normal computed` sẽ là `45` thay vì `42`; đó là phần cố ý cho thấy giá trị được tính ở runtime, không phải constant expression.

### 5.1. Vì sao `Normal.class` không in initializer?

Dòng:

```java
Class<Normal> normalClass = Normal.class;
```

chỉ lấy đối tượng `Class`. Dòng đầu trong console là `got Normal.class`. Đến lúc thực thi:

```java
lookup.ensureInitialized(normalClass)
```

JVM mới chạy `Normal.<clinit>`, in `Normal.<clinit>`. Sau đó, phép so sánh `== normalClass` trả `true`, và đọc `Normal.COMPUTED` cho `42` khi system property mặc định.

Lần gọi `ensureInitialized(normalClass)` tiếp theo **không chạy lại khối static**, nên giữa `normal computed: 42` và `normal ensured again` không có dòng `Normal.<clinit>` nào nữa.

### 5.2. Vì sao `publicLookup()` không khởi tạo `Restricted`?

`Restricted` là private nested class. `MethodHandles.publicLookup()` không có quyền cần thiết để truy cập lớp private này, do đó:

```java
MethodHandles.publicLookup().ensureInitialized(Restricted.class);
```

ném `IllegalAccessException`. Bạn sẽ không thấy dòng `Restricted.<clinit>` trong output, vì lần yêu cầu đó bị từ chối. Một Class reference **không tự biến một public lookup thành lookup có đặc quyền**.

Đoạn ví dụ chạy hoàn chỉnh đã bắt lỗi để minh họa. Trong dự án thật, bạn phải xem Lookup được tạo từ đâu, có những access modes nào, module/package của target có truy cập được không, và nơi nào được phép dùng lookup đó.

### 5.3. Hidden class: định nghĩa trước, khởi tạo sau

Khi chương trình chạy:

```java
MethodHandles.Lookup hiddenLookup = lookup.defineHiddenClass(bytes, false);
Class<?> hiddenClass = hiddenLookup.lookupClass();
```

nó **định nghĩa** hidden class nhưng không yêu cầu chạy static initializer ngay, vì `initialize=false`. Dòng `hidden class defined: true` và `before hidden ensure` được in **trước** `Template.<clinit> (hidden copy)`.

Chỉ khi chạy:

```java
hiddenLookup.ensureInitialized(hiddenClass);
```

JVM mới chạy static initializer của hidden class. Sau đó, gọi lại lần nữa không lặp static initializer.

**Chi tiết đáng chú ý:** Bytecode được đọc từ file `EnsureInitializedDemo$Template.class` đã biên dịch, nhưng hidden class được định nghĩa là **kiểu runtime riêng**, không phải chính `EnsureInitializedDemo.Template.class` thông thường. Lời gọi đọc resource classfile không tự khởi tạo bản class thông thường, và static initializer in ở ví dụ này thuộc về **hidden copy**. Nếu chỉ nhìn tên chuỗi được in, bạn dễ nhầm hai class; nên dùng `Class.isHidden()` hoặc so sánh Class identity khi debug.

Mẫu này phù hợp với công cụ sinh mã cần xây bytecode/class trước, rồi hoãn khởi tạo đến khi toàn bộ dữ liệu và môi trường cần thiết đã sẵn sàng.

## 6. Quyền truy cập và ngoại lệ: hiểu đúng từng trường hợp

| Tình huống | Ngoại lệ / hành vi | Cách xử lý |
| --- | --- | --- |
| `targetClass` là primitive, `void` hoặc array | `IllegalArgumentException` | Kiểm tra loại trước khi gọi; không áp dụng API cho các loại đó |
| Target không accessible từ `Lookup` | `IllegalAccessException` | Tạo/sử dụng Lookup có nguồn và quyền hợp lệ; không bypass module |
| Static initializer ném runtime exception (như `IllegalStateException` trong demo) | Trong lần khởi tạo đầu có thể được JVM bọc bằng `ExceptionInInitializerError` | Đọc `getCause()`, sửa lỗi root cause; không mặc định retry sẽ cứu được |
| Class đã ở trạng thái erroneous sau khi initialization thất bại | Lần yêu cầu sau thường gặp `NoClassDefFoundError` | Không xem là lỗi thiếu file class; sửa nguyên nhân và quản lý vòng đời class loader |
| JVM gặp linkage/verification problem | Có thể có `LinkageError` và các lỗi JVM liên quan | Kiểm tra classfile, version, phụ thuộc, class loader và package |
| Class đã khởi tạo | Không chạy lại `<clinit>` | Đừng dùng `ensureInitialized` làm “reload config” |
| Class đang khởi tạo từ thread hiện tại | JVM cho phép tình huống đệ quy theo quy tắc khởi tạo | Tránh suy rằng toàn bộ static state đã được thiết lập xong |

### Phân biệt `ExceptionInInitializerError` với `NoClassDefFoundError`

Trong demo:

```java
private static int fail() {
    throw new IllegalStateException("boom");
}
```

Lần đầu `lookup.ensureInitialized(Broken.class)` làm JVM chạy static initialization, rồi `fail()` ném `IllegalStateException`. JVM bọc ngoại lệ không phải `Error` này trong `ExceptionInInitializerError`. Demo bắt ngoại lệ và in **loại nguyên nhân** `IllegalStateException`.

Sau lỗi đó, `Broken` được đánh dấu **erroneous** trong class loader hiện tại. Lần gọi tiếp theo trên cùng `Class<?>` bị lỗi `NoClassDefFoundError` (thường mô tả không thể khởi tạo class), dù bytecode không hề biến mất. **Không nên bắt lỗi này rồi thử `ensureInitialized` trong vòng lặp**: đây không phải thao tác có thể khởi tạo lại `<clinit>` của class lỗi theo ý muốn.

Nếu một static initializer ném trực tiếp một `Error`, JLS quy định cách lan truyền khác với trường hợp ngoại lệ không phải `Error`. Không nên hứa hẹn rằng mọi kiểu thất bại initialization đều được bọc trong `ExceptionInInitializerError`; quan sát nguyên nhân cụ thể của JVM.

### Có nên bắt `Throwable` để cứu mọi lỗi?

Thông thường **không**. `LinkageError`, `ExceptionInInitializerError` và `NoClassDefFoundError` phản ánh lỗi triển khai hoặc khởi tạo nghiêm trọng. Việc bắt chúng chỉ để tiếp tục như không có gì xảy ra có thể khiến hệ thống hoạt động trên trạng thái nửa vời. Trong bài demo, bắt riêng các loại lỗi nhằm minh họa; ứng dụng thật nên xác định cách khởi động thất bại, rollback tài nguyên liên quan và quan sát log.

## 7. Khởi tạo một lần, đồng bộ giữa các thread và vòng đệ quy

Theo **JVMS §5.5** và **JLS §12.4.2**, initialization có cơ chế đồng bộ theo từng class/interface:

1. Nếu chưa khởi tạo, thread có quyền thực hiện quy trình khởi tạo.
2. Nếu **thread khác** đang khởi tạo class đó, caller có thể phải đợi đến khi quy trình kia hoàn tất hoặc thất bại.
3. Nếu **chính thread hiện tại** đang khởi tạo class đó và đệ quy yêu cầu khởi tạo thêm lần nữa, JVM giải quyết theo quy tắc reentrant mà không chạy lặp vô hạn static initializer.
4. Nếu class đã khởi tạo, lệnh yêu cầu tiếp theo không chạy lại khối static.
5. Nếu class đã đánh dấu lỗi do lần khởi tạo trước thất bại, các yêu cầu về sau không tự làm nó sống lại.

Điểm quan trọng đối với API: Javadoc hiện hành mô tả `ensureInitialized` trả về khi **đã khởi tạo đầy đủ hoặc đang được khởi tạo bởi chính thread hiện tại**. Vì thế, nếu gọi nó từ một đường thực thi phát sinh **ngay trong `<clinit>`**, cần cân nhắc static state còn đang trong quá trình thiết lập.

Tránh viết static initializer gọi qua lại phức tạp giữa nhiều class hoặc giữ lock rồi chờ những thao tác có thể kích hoạt khởi tạo class khác; bạn có thể gây vòng phụ thuộc, deadlock hoặc quan sát trạng thái chưa hoàn chỉnh. Với những hệ thống nhiều thread, ưu tiên khởi tạo tường minh ở điểm bắt đầu đã xác định, giữ static initialization nhỏ gọn và không để side effects bất ngờ.

**Không nhầm “một lần” với “một lần cho mọi ứng dụng”:** cùng tên binary class có thể được định nghĩa bởi những class loaders khác nhau, tạo các Class objects và trạng thái initialization riêng. Các hidden classes được định nghĩa nhiều lần từ cùng bytecode cũng là các class riêng và có lifecycle độc lập. Cơ chế once tính **theo từng class runtime**, không theo chuỗi tên nguồn.

## 8. So sánh với cách dùng Class.forName và reflection

### 8.1. Khi đã có `Class<?>` thì không cần tìm lại bằng tên

Đối với class thông thường, code có thể dùng:

```java
Class<?> type = Class.forName(
        "com.example.Plugin", false, loader);
// false: không yêu cầu khởi tạo ngay tại lời gọi Class.forName.
lookup.ensureInitialized(type);
```

Đây là đoạn minh họa, giả định đã có `ClassLoader loader`, `MethodHandles.Lookup lookup` đủ quyền, và lớp `com.example.Plugin` tồn tại. Cách làm này có thể hữu ích khi cần tách **khám phá** class khỏi **kích hoạt** initializer.

Nhưng nếu bạn **đã có** một `Class<?>` do framework trả về, không cần chuyển nó thành tên rồi gọi `Class.forName`. Việc tìm lại theo tên có thể chọn class loader sai, gây `ClassNotFoundException` hoặc mất identity của class. Với hidden class, cách tìm lại đó vốn không hoạt động vì hidden class không có binary name discoverable.

### 8.2. Reflection cũng có thể kích hoạt khởi tạo

Một số thao tác phản chiếu như tạo instance qua constructor hay gọi static member có thể yêu cầu khởi tạo class trước khi thực thi. Vì vậy không nên giả định rằng cứ dùng Reflection thì có thể quan sát class trước/đang khởi tạo mà không tạo side effect.

Nếu mục tiêu thật sự là bảo đảm `<clinit>` hoàn tất **trước** khi gọi những thành viên đó, `lookup.ensureInitialized(target)` diễn đạt ý định rõ ràng. Ngược lại, nếu chỉ muốn đọc metadata như tên class hoặc danh sách method, việc chủ động khởi tạo có thể không cần thiết và tạo side effects ngoài ý muốn.

### 8.3. Khác `Lookup#defineHiddenClass` ở cờ `initialize`

`defineHiddenClass(bytes, true)` nghĩa là khởi tạo ngay trong quy trình định nghĩa hidden class. Với `false`, bạn có thể:

```java
MethodHandles.Lookup classLookup =
        trustedLookup.defineHiddenClass(bytes, false);
Class<?> generated = classLookup.lookupClass();

// Tiếp tục chuẩn bị registry, metadata và thành phần phụ thuộc phù hợp.

classLookup.ensureInitialized(generated);
```

Mã minh họa trong phương thức đã có `Lookup trustedLookup` đủ quyền và `byte[] bytes` hợp lệ; **không phải chương trình Java đứng độc lập**. Để hoãn khởi tạo có giá trị thực tế, tránh kích hoạt class bằng thao tác active use khác trước lời gọi `ensureInitialized`.

**Phân biệt khái niệm:** `defineHiddenClass` tạo một loại runtime class mới; `ensureInitialized` chỉ yêu cầu initialize một class **đã tồn tại**. Không phải cứ tạo được hidden class thì mọi lookup khác cũng có thể gọi `ensureInitialized` trên nó: vẫn phải xét quyền truy cập của Lookup.

## 9. Khi nào nên sử dụng chủ động?

`ensureInitialized` hữu ích nhất trong những tình huống đã sở hữu một `Class<?>` cụ thể và cần **thời điểm khởi tạo có chủ ý**:

| Tình huống | Cách tiếp cận |
| --- | --- |
| Framework đã nhận `Class<?> pluginType` qua scanning/registry | Chỉ gọi `ensureInitialized` nếu plugin contract thực sự cần static initializer trước bước dùng tiếp |
| Runtime sinh hidden class từ bytecode và cần đăng ký cấu hình trước khi chạy `<clinit>` | Tạo bằng `defineHiddenClass(bytes, false)`, chuẩn bị trạng thái, rồi dùng lookup hợp lệ để bảo đảm khởi tạo |
| Đang kiểm tra class bằng tên/metadata nhưng chưa muốn side effect | Chưa gọi `ensureInitialized`; đọc metadata không yêu cầu chủ động initialization |
| Muốn reset static state mỗi request | **Không dùng** `ensureInitialized`; API này không chạy lại initializer |
| Muốn mở quyền class private/module đóng | **Không dùng để bypass**; phải thiết kế quyền lookup và module access đúng |
| Muốn tạo class mới từ bytecode | Dùng API định nghĩa class tương ứng, không dùng `ensureInitialized` |
| Muốn bắt lỗi initialization sớm ở startup thay vì xảy ra giữa request | Có thể yêu cầu khởi tạo chủ động trong giai đoạn startup và xử lý lỗi startup thích hợp |

Khi cần plugin lifecycle, constructor injection, giao dịch hoặc khởi tạo tài nguyên có thể retry, **đừng lạm dụng static initializer**. Thường một phương thức khởi tạo tường minh ở tầng dịch vụ đem lại kiểm soát tốt hơn. `ensureInitialized` là công cụ để thực hiện quy tắc initialization của JVM, không phải framework điều phối toàn bộ vòng đời ứng dụng.

## 10. Những hiểu nhầm thường gặp

1. **“Có `Class<?>` nghĩa là class đã chạy static initializer.”** Sai: class literal và một số cách lấy class metadata không kích hoạt initialization.
2. **“`ensureInitialized` sẽ chạy lại `static { ... }` mỗi lần gọi.”** Sai: với class đã khởi tạo thành công, không có lần chạy lại.
3. **“Bất kỳ Lookup nào cũng khởi tạo mọi class được.”** Sai: target phải accessible từ Lookup; `publicLookup` không có quyền với lớp private trong demo.
4. **“Dùng nó để khởi tạo `int.class` hay `String[].class` được.”** Sai: primitive, void và array bị từ chối bằng `IllegalArgumentException`.
5. **“`ensureInitialized` luôn trả về sau khi mọi static field đã thiết lập xong trong mọi tình huống.”** Thiếu điều kiện: Javadoc cho phép trở về khi current thread chính là thread đang khởi tạo class (reentrant).
6. **“Static initialization lỗi thì gọi lại sẽ thử lại.”** Sai: JVM đánh dấu class erroneous; lần sau thường thấy `NoClassDefFoundError`.
7. **“`NoClassDefFoundError` chắc chắn do thiếu file `.class`.”** Sai: cũng có thể do class đã bị lỗi khi khởi tạo trước đó.
8. **“Hidden class không có Class object nên không gọi `ensureInitialized` được.”** Sai: `defineHiddenClass` trả Lookup và `lookupClass()` cho Class object cụ thể.
9. **“`initialize=false` làm hidden class không bao giờ khởi tạo.”** Sai: nó chỉ không yêu cầu khởi tạo **ở thời điểm định nghĩa**; `ensureInitialized` hoặc active use thích hợp vẫn có thể kích hoạt.
10. **“`Class.forName(hidden.getName())` lấy lại hidden class.”** Sai: hidden class không thể discover theo binary name như class thông thường.
11. **“Khởi tạo class là cách thực hiện một tác vụ có thể chạy nhiều lần.”** Sai: JVM initialization là một lần cho class runtime đã khởi tạo thành công, không phải task scheduler.
12. **“Khởi tạo chính là loading/linking.”** Sai: initialization có ý nghĩa riêng và có thể xảy ra muộn hơn sau khi Class object đã tồn tại.

## 11. Bài tập tự kiểm tra (có đáp án)

**Câu 1.** Sau `Class<?> c = SomeType.class;`, có thể khẳng định khối static đã chạy chưa?

**Đáp án:** **Chưa thể**. Chỉ lấy class literal không bắt buộc initialization. Nếu class đã được active use trước đó, nó có thể đã khởi tạo vì lý do khác; câu lệnh lấy class literal không phải bằng chứng về thời điểm.

**Câu 2.** Gọi `lookup.ensureInitialized(c)` hai lần trên cùng class và class khởi tạo thành công. Static initializer chạy mấy lần?

**Đáp án:** Chạy **tối đa một lần cho class runtime đó**. Lần gọi sau không tự khởi tạo lại.

**Câu 3.** Có thể gọi `lookup.ensureInitialized(String[].class)` không?

**Đáp án:** Không, ném **`IllegalArgumentException`** vì array class không phải target hợp lệ của API.

**Câu 4.** Vì sao `MethodHandles.publicLookup().ensureInitialized(PrivateNested.class)` có thể ném `IllegalAccessException`?

**Đáp án:** Có Class object chưa đồng nghĩa có quyền từ lookup đang dùng. `publicLookup()` không có quyền truy cập lớp private đó; phương thức tuân theo access checks.

**Câu 5.** `defineHiddenClass(bytes, false)` có làm `<clinit>` chạy ngay không? Cần gọi gì nếu muốn khởi tạo lúc đã sẵn sàng?

**Đáp án:** Không yêu cầu chạy ngay. Dùng `Lookup` phù hợp và `Class<?>` của hidden class, sau đó gọi **`lookup.ensureInitialized(hiddenClass)`** để chủ động yêu cầu khởi tạo.

**Câu 6.** Nếu static initializer ném `IllegalStateException`, lần khởi tạo đầu và lần yêu cầu sau trên cùng class có thể báo lỗi nào?

**Đáp án:** Lần đầu **`ExceptionInInitializerError`** bọc nguyên nhân không phải `Error`; class trở nên erroneous, lần sau thường là **`NoClassDefFoundError`**. Không gọi retry vô hạn.

**Câu 7.** Khi dùng `Class.forName(name, false, loader)` rồi `ensureInitialized(type)`, lợi ích là gì?

**Đáp án:** Tách bước tra cứu một class thông thường **mà không yêu cầu initialize** khỏi thời điểm chủ động khởi tạo sau đó. Tuy nhiên phải có Lookup có quyền và đối với hidden class không thể tìm lại bằng tên.

**Câu 8.** Vì sao API có thể trả về khi target vẫn đang được khởi tạo?

**Đáp án:** Javadoc cho phép trường hợp **current thread** đang trong quy trình khởi tạo chính class ấy; JVM xử lý đệ quy theo cơ chế initialization mà không chạy lại `<clinit>`.

**Tiêu chí đạt:** bạn giải thích được loading/linking/initialization, chọn đúng thời điểm gọi `ensureInitialized`, dự đoán stdout của chương trình minh họa, phân biệt lỗi quyền truy cập và lỗi initialization, và chủ động hoãn khởi tạo hidden class khi có nhu cầu thực.

## 12. Nguồn chuẩn, còn phù hợp với Java hiện nay

- [Java SE 15 – `MethodHandles.Lookup` Javadoc](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `ensureInitialized` (**Since 15**), `defineHiddenClass`, `accessClass` và quyền của lookup.
- [Java SE 25 – `MethodHandles.Lookup` Javadoc](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): hợp đồng hiện đại của `ensureInitialized`, bao gồm trường hợp current-thread initialization.
- [JLS §12.4 – Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.4): những thao tác gây initialization và quy trình đồng bộ.
- [JVMS §5.5 – Initialization](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.5): quy tắc kiểm tra trạng thái initialized/being-initialized/erroneous.
- [Java SE 25 – `Class.forName` Javadoc](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html): các overload có/không yêu cầu initialize.
- [OpenJDK JEP 371 – Hidden Classes](https://openjdk.org/jeps/371): đặc điểm của hidden class và khả năng kiểm soát khởi tạo khi định nghĩa.

**Ghi nhớ:** `MethodHandles.Lookup.ensureInitialized(targetClass)` là cách tường minh, **có kiểm tra quyền**, để yêu cầu JVM khởi tạo một class/interface **đã có đối tượng `Class<?>`**. Với hidden class, `defineHiddenClass(bytes, false)` tạo lớp trước; `ensureInitialized(hiddenClass)` cho phép yêu cầu khởi tạo sau, khi hệ thống thật sự cần.