# Truy cập static field có thể kích hoạt khởi tạo lớp trong Java Reflection

## 1. Vấn đề: lấy Field và đọc Field là hai thời điểm khác nhau

Trong Java Reflection, có sự khác biệt quan trọng giữa **tìm metadata của một field** và **thực sự đọc hoặc ghi giá trị của field đó**. Với field `static`, việc đọc hoặc ghi qua `java.lang.reflect.Field` có thể khiến JVM **khởi tạo lớp khai báo field** trước khi trả về giá trị hoặc thực hiện phép gán.

```java
Class<?> type = Sample.class;                       // Chưa yêu cầu khởi tạo Sample
Field field = type.getDeclaredField("value");       // Chỉ lấy metadata
Object value = field.get(null);                     // Nếu Sample chưa init: kích hoạt init
```

Đoạn mã trên là **minh họa**, yêu cầu có lớp `Sample` với field `value` và cần `import java.lang.reflect.Field;`; quyền truy cập cũng phải hợp lệ. Với field `static`, đối số receiver của `Field.get(Object)` có thể là `null` vì giá trị thuộc về lớp, không thuộc về một đối tượng cụ thể.

Điểm cần phân biệt: việc khởi tạo lớp xảy ra **trước lần truy cập giá trị đầu tiên cần khởi tạo**, không nhất thiết ngay khi JVM load class, khi Java tạo đối tượng `Class<?>` hoặc khi Reflection tạo đối tượng `Field`.

### Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vì sao `getDeclaredField()` chỉ tìm metadata nhưng `Field.get(null)` hay `Field.set(null, value)` có thể chạy các static initializer.
- Phân biệt **loading, linking, initialization**, và cách đọc `static final` compile-time constant so với đọc bằng Reflection.
- Dự đoán thứ tự output khi lớp có `static` block và phép gán field `static`.
- Xác định **lớp khai báo field** bằng `Field.getDeclaringClass()` khi có kế thừa.
- Tránh vô tình kích hoạt side effect, lỗi khởi tạo hoặc rủi ro khi framework quét metadata.

## 2. Ba giai đoạn: loading, linking và initialization

Một lớp thường trải qua các bước cơ bản sau trong vòng đời JVM:

| Giai đoạn | Ý nghĩa | Có nhất thiết chạy code `static` do người dùng viết? |
| --- | --- | --- |
| **Loading** | JVM tìm/đọc biểu diễn class và tạo đối tượng runtime `Class` tương ứng | Không |
| **Linking** | Verification, preparation và resolution (resolution có thể diễn ra muộn); preparation cấp phát và đặt giá trị mặc định cho các field `static` | Không chạy phần thân static initializer như khi initialization |
| **Initialization** | JVM thực thi phương thức khởi tạo lớp `<clinit>` do compiler tổng hợp từ static field initializer và static initializer block | **Có**, nếu lớp có code khởi tạo tương ứng |

Ví dụ:

```java
class Config {
    static int port = parsePort();  // Lệnh này chạy khi initialize Config

    static {
        System.out.println("Config initialized");
    }

    private static int parsePort() {
        return 8080;
    }
}
```

Khi initialization của `Config` diễn ra, câu lệnh gán `port = parsePort()` và static block được thực thi theo **thứ tự văn bản xuất hiện trong lớp**. Trong ví dụ này `parsePort()` chạy trước thông báo `Config initialized`.

**Không nên coi “class đã được load” là “class đã được initialize”.** Một framework có thể load lớp để kiểm tra tên, annotation hoặc thành viên mà chưa yêu cầu chạy logic khởi tạo; nhưng khi framework truy cập giá trị field `static`, ranh giới này thay đổi.

JVM quản lý initialization cho từng định nghĩa lớp ở runtime (gắn với class loader xác định). Một lần initialization thành công chỉ diễn ra một lần cho định nghĩa lớp đó; đó không đồng nghĩa mọi lần dùng tên lớp trong source đều gây khởi tạo lại.

## 3. Các thao tác Reflection nào có thể kích hoạt initialization?

Xét:

```java
class Settings {
    static int timeout = computeTimeout();

    private static int computeTimeout() {
        System.out.println("Calculating timeout");
        return 10;
    }
}
```

| Thao tác | Có yêu cầu initialize `Settings` nếu chưa được initialize? | Vì sao |
| --- | --- | --- |
| `Settings.class` | Không | Class literal lấy đối tượng `Class`, không phải truy cập giá trị `static` |
| `Settings.class.getDeclaredField("timeout")` | Không | Tìm metadata của field |
| `Settings.class.getDeclaredFields()` | Không | Liệt kê metadata của các field khai báo trực tiếp |
| `field.getName()`, `field.getType()`, `field.getModifiers()` | Không phải thao tác đọc giá trị field | Xem đặc điểm member; một số kiểu phụ thuộc có thể được load/resolved |
| `field.get(null)` | **Có** | Đọc giá trị field `static` qua Reflection |
| `field.getInt(null)` | **Có** | Đọc chuyên biệt kiểu nguyên thủy `int` |
| `field.set(null, value)` | **Có** nếu phép ghi được phép | Ghi giá trị field `static` |
| `field.setInt(null, value)` | **Có** nếu phép ghi được phép | Ghi `static int` bằng API chuyên biệt |
| `Settings.timeout` | **Có** vì `timeout` không phải compile-time constant | Dùng field `static` không-constant trong code thường |
| `Class.forName("...", false, loader)` | Không yêu cầu initialization | Lấy/load class với cờ `initialize=false` |
| `Class.forName("...")` | **Có**, đối với lớp chưa được initialize | Biến thể một tham số chủ động yêu cầu khởi tạo lớp được đặt tên |

Bảng này giả định thao tác thực sự đi tới lần truy cập hợp lệ; nếu field không tồn tại, caller không có quyền, loại đối số sai hoặc một lỗi xảy ra sớm hơn, đừng suy ra rằng initialization **nhất định** đã diễn ra. Mục tiêu là nêu tác dụng của **thao tác thành công trên field static**.

Không nhầm `Class.getDeclaredField` với `Field.get`: hai phương thức khác lớp và khác ý nghĩa. `getDeclaredField` có thể tìm cả member `private` được khai báo ngay trong class; điều đó **không cấp quyền tự động** để sau này gọi `get` hoặc `set`.

## 4. Ví dụ Java 17+: thấy rõ thời điểm khởi tạo

Lưu nguyên chương trình vào tệp **`StaticFieldInitDemo.java`**. Bốn trường hợp được tách rõ: đọc constant bình thường, tra cứu metadata, đọc static field bằng Reflection và ghi static field bằng Reflection.

```java
import java.lang.reflect.Field;

public class StaticFieldInitDemo {
    static class Target {
        static {
            System.out.println("Target: <clinit> block");
        }

        public static int number = loadNumber();
        public static final int COMPILE_CONSTANT = 42;

        private static int loadNumber() {
            System.out.println("Target: loadNumber()");
            return 7;
        }
    }

    static class Constants {
        static {
            System.out.println("Constants: <clinit> block");
        }

        public static final String TEXT = "hello";
    }

    static class Writable {
        static {
            System.out.println("Writable: <clinit> block");
        }

        public static int value = 1;
    }

    public static void main(String[] args) throws Exception {
        // Compile-time constant đọc trực tiếp có thể được inline.
        System.out.println("direct constant: " + Target.COMPILE_CONSTANT);

        // Lấy Class và metadata Field chưa đọc giá trị static.
        Class<?> clazz = Target.class;
        Field number = clazz.getDeclaredField("number");
        System.out.println("metadata: " + number.getName());
        System.out.println("before first Field.getInt");

        // Field.getInt(null) bắt đầu initialize Target.
        System.out.println("reflected number: " + number.getInt(null));
        System.out.println("reflected number again: " + number.getInt(null));

        // Đọc constant bằng Java thông thường không initialize Constants.
        System.out.println("direct other constant: " + Constants.TEXT);

        // Reflection vẫn chủ động đọc field static, nên initialize Constants.
        Field constant = Constants.class.getDeclaredField("TEXT");
        System.out.println("reflected constant: " + constant.get(null));

        // Lấy Field không init Writable, nhưng việc ghi qua Field.setInt có.
        Field writable = Writable.class.getDeclaredField("value");
        System.out.println("before Field.setInt");
        writable.setInt(null, 25);
        System.out.println("updated value: " + writable.getInt(null));
    }
}
```

Biên dịch và chạy bằng **JDK 17+**:

```bash
javac StaticFieldInitDemo.java
java StaticFieldInitDemo
```

**Kết quả chính xác** khi chạy chương trình độc lập:

```text
direct constant: 42
metadata: number
before first Field.getInt
Target: <clinit> block
Target: loadNumber()
reflected number: 7
reflected number again: 7
direct other constant: hello
Constants: <clinit> block
reflected constant: hello
before Field.setInt
Writable: <clinit> block
updated value: 25
```

### 4.1. Vì sao hai dòng đầu chưa in `Target: <clinit> block`?

`Target.COMPILE_CONSTANT` là **constant variable**: field `final` có kiểu primitive/String và được khởi tạo bằng **constant expression**. Java compiler có thể dùng trực tiếp hằng số trong bytecode của caller thay vì lệnh đọc field ở runtime. Lệnh `Target.class` cũng không tự yêu cầu initialization. `clazz.getDeclaredField("number")` chỉ tạo metadata.

Vì thế trước lời gọi `Field.getInt(null)`, chương trình đã in thông tin về field nhưng `Target` vẫn chưa initialize.

### 4.2. Vì sao output static initializer chen giữa hai dòng khi đọc field?

Biểu thức:

```java
System.out.println("reflected number: " + number.getInt(null));
```

phải đánh giá `number.getInt(null)` trước khi in cả chuỗi. Lần đầu đọc này yêu cầu initialize `Target`; JVM chạy static block trước, tiếp đến initializer của `number` gọi `loadNumber()`. Sau khi khởi tạo thành công, `getInt(null)` trả `7` và Java mới in `reflected number: 7`.

Lần đọc thứ hai thấy `Target` đã initialize nên **không chạy lại** static block hoặc `loadNumber()`.

### 4.3. Vì sao đọc một constant qua Reflection vẫn làm lớp initialize?

`Constants.TEXT` là constant variable được compiler inline khi đọc trực tiếp, nên dòng `direct other constant: hello` không khởi tạo `Constants`. Tuy nhiên:

```java
Field constant = Constants.class.getDeclaredField("TEXT");
System.out.println(constant.get(null));
```

gọi `Field.get(null)` thật sự. Quy tắc truy cập reflective vào field `static` yêu cầu initialize **lớp khai báo field**, kể cả khi field là compile-time constant. Do đó `Constants: <clinit> block` xuất hiện trước `reflected constant: hello`.

**Hệ quả:** Một framework chỉ “đọc giá trị hằng số” bằng Reflection vẫn có thể chạy code `static` bên cạnh hằng số đó. Đừng dựa vào việc field có `final` để suy ra rằng lần đọc reflective luôn vô hại.

### 4.4. Vì sao ghi cũng làm lớp initialize?

`writable.setInt(null, 25)` trước tiên đảm bảo `Writable` được initialize (ban đầu `value=1`), rồi thực hiện phép ghi được phép. Sau đó `getInt(null)` đọc `25`. Không có dòng in thứ hai từ static block của `Writable` vì initialization không diễn ra lại.

## 5. Compile-time constant và static final không hằng là hai trường hợp khác nhau

Không phải mọi `static final` đều được coi là constant variable.

```java
class Flags {
    static {
        System.out.println("Flags initialized");
    }

    static final int FIXED = 100;                 // Constant expression
    static final String TITLE = "core" + "-api";  // Constant expression
    static final Integer BOXED = 100;             // Không phải primitive/String
    static final int COMPUTED = Integer.parseInt("100");
                                                  // Không phải constant expression
    static int DYNAMIC = 100;                     // Không final
}
```

| Truy cập bằng code Java bình thường | Thông thường yêu cầu initialize `Flags`? |
| --- | --- |
| `Flags.FIXED` | Không; compile-time constant có thể được inline |
| `Flags.TITLE` | Không; constant expression kiểu `String` |
| `Flags.BOXED` | Có; `Integer` không phải kiểu cho constant variable |
| `Flags.COMPUTED` | Có; `Integer.parseInt(...)` không phải constant expression |
| `Flags.DYNAMIC` | Có; `static` field không phải constant variable |

Ngược lại, `Field.get(null)` đối với **bất kỳ field static nào** ở bảng trên đều yêu cầu initialization của declaring class trước khi đọc, nếu lớp chưa được initialize và thao tác có quyền thực hiện.

Ngoài vấn đề initialization, việc inline constant còn liên quan tương thích binary: class đã biên dịch trước có thể giữ giá trị hằng cũ cho đến khi được biên dịch lại. Đây là lý do không nên dùng việc đổi một `public static final` constant rồi quan sát output để suy luận đơn giản về load/initialize.

## 6. Khởi tạo lớp nào khi có kế thừa?

Mục tiêu initialization là **lớp khai báo field static được truy cập**, không đương nhiên là lớp bạn dùng làm điểm xuất phát tra cứu.

```java
class ParentConfig {
    static {
        System.out.println("ParentConfig initialized");
    }

    public static int port = 8080;
}

class ChildConfig extends ParentConfig {
    static {
        System.out.println("ChildConfig initialized");
    }
}
```

Ví dụ các dòng trong một phương thức có `throws Exception`:

```java
Field field = ChildConfig.class.getField("port");
System.out.println(field.getDeclaringClass().getSimpleName());
System.out.println(field.getInt(null));
```

Nếu chưa lớp nào được initialize, ý nghĩa là:

- `getField("port")` có thể tìm field `public` được kế thừa; `getDeclaringClass()` cho biết field thật sự nằm ở `ParentConfig`.
- `field.getInt(null)` yêu cầu initialize `ParentConfig` (nơi field được khai báo).
- Chỉ vì lấy field qua `ChildConfig.class` không có nghĩa `ChildConfig` cần initialize. Đọc field static được thừa kế không tự buộc subclass phải chạy static block.

Với field bị ẩn (*field hiding*), luôn kiểm tra `getDeclaringClass()`. Nếu `ChildConfig` khai báo một field `port` khác, cần chọn chính xác `Field` nào muốn đọc; việc chọn sai owner có thể gây khởi tạo lớp khác dự kiến.

Khi initialize một **class**, JVM cũng phải đảm bảo superclass cần thiết đã được initialize theo quy tắc chuẩn; một số interface có default method cũng có thể tham gia quá trình. Vì vậy lần đọc field static khai báo ở subclass có thể kéo theo quá trình khởi tạo liên quan trong phân cấp, nhưng không nên đảo chiều suy luận rằng đọc field static của superclass luôn initialize mọi subclass.

## 7. Loading/metadata an toàn hơn initialization, nhưng cần hiểu giới hạn

Nếu nhiệm vụ chỉ là **khám phá cấu trúc lớp**, có thể trì hoãn initialization:

```java
String binaryName = "example.Settings";
ClassLoader loader = Thread.currentThread().getContextClassLoader();

Class<?> clazz = Class.forName(binaryName, false, loader);
Field field = clazz.getDeclaredField("timeout");

System.out.println(field.getName());
System.out.println(field.getDeclaringClass().getName());
```

Đây là đoạn minh họa, giả định có lớp `example.Settings` trong classpath/module path và quyền tra cứu phù hợp; cần import `java.lang.reflect.Field`. `Class.forName(name, false, loader)` không chủ động initialize lớp được gọi tên. Tương tự, việc xem metadata cơ bản của `Field` không đọc giá trị static. Dù vậy, loading, linking, resolution hay các hook/class-loader tùy chỉnh vẫn có thể làm các công việc khác: “chưa initialize lớp đích” **không có nghĩa mọi thao tác liên quan đều tuyệt đối không có side effect**.

Một số cách yêu cầu initialization một cách chủ động:

```java
Class.forName("example.Settings");      // Thông thường yêu cầu initialize
// Hoặc thực hiện một thao tác đọc/ghi static field hợp lệ.
```

Hãy chọn chính sách rõ ràng: nếu plugin scanner chỉ lập danh sách field, không cần đọc mọi giá trị `static`. Nếu ứng dụng thực sự cần giá trị runtime, chấp nhận rằng đây là thao tác có thể khởi tạo class.

## 8. Thứ tự khởi tạo và giá trị mặc định

Trong **preparation**, JVM gán giá trị mặc định ban đầu cho các field `static`: `0` cho số nguyên, `false` cho `boolean`, `null` cho tham chiếu. Trong **initialization**, code do compiler tạo từ static initializer chạy theo thứ tự source; đây là lúc các phép gán tùy biến được thực thi.

Ví dụ:

```java
class Ordered {
    static int first = compute();
    static int later = 20;

    private static int compute() {
        return later + 1;
    }
}
```

Khi `Ordered` được initialize, phép gán `first = compute()` thực thi trước `later = 20`. Tại thời điểm `compute()` đọc `later`, field có giá trị mặc định `0`, nên `first` nhận `1`. Sau đó `later` trở thành `20`. Hai field đều là `static`, nhưng thứ tự initializer vẫn quan trọng.

Trong ví dụ này một lượt reflective đọc `Ordered.first` sau initialization sẽ nhận `1`. Đừng dùng Reflection để suy luận rằng các initializer chạy “cùng lúc” hoặc rằng một field luôn thấy mọi field khác đã được gán giá trị cuối cùng.

JLS có các chi tiết đặc biệt về constant variables, superclass initialization và interface initialization. Với trường hợp thông dụng trong bài, điều cốt lõi là JVM hoàn thành initialization cần thiết **trước khi truy cập static field phản chiếu thành công**.

## 9. Nếu static initialization thất bại thì sao?

Static initializer có thể gọi cấu hình, đọc file, tạo connection, gọi thư viện native hoặc thực hiện phép tính có thể lỗi. Khi Reflection là thao tác đầu tiên yêu cầu initialize lớp, lỗi có thể xuất hiện ngay tại `Field.get(null)` hoặc `Field.set(null, value)`, dù bản thân field hợp lệ.

Ví dụ một lớp có khởi tạo thất bại:

```java
class Broken {
    static int value = initialize();

    private static int initialize() {
        throw new IllegalStateException("missing configuration");
    }
}
```

Nếu là lần đầu code có quyền gọi:

```java
Field field = Broken.class.getDeclaredField("value");
field.getInt(null);
```

Việc tra cứu metadata ở dòng đầu có thể thành công; dòng thứ hai yêu cầu initialization, khiến lỗi khởi tạo lan ra. Khi initializer ném `RuntimeException` như ví dụ, lần khởi tạo đầu thường biểu hiện bằng `ExceptionInInitializerError` bao bọc nguyên nhân. JVM đánh dấu class ở trạng thái khởi tạo lỗi; các lần sử dụng chủ động về sau trong cùng định nghĩa class thường nhận `NoClassDefFoundError` cho class không thể initialize. Không thể “thử đọc lại Field” để class tự khởi tạo từ đầu. Một field khác của cùng class cũng không giải quyết được điều đó.

Nếu gặp tình huống này:

1. Kiểm tra stack trace và **cause** gốc của lỗi khởi tạo, đặc biệt phần chạy trong `<clinit>`.
2. Phân biệt lỗi **tra cứu metadata** (`NoSuchFieldException`), lỗi **quyền truy cập** (`IllegalAccessException`) và lỗi **initialization** (có thể là `ExceptionInInitializerError` hoặc `Error` liên quan).
3. Tránh bọc mọi lỗi thành “field không tồn tại”: cách đó che nguyên nhân thật và làm người đọc tưởng Reflection API bị lỗi.
4. Thiết kế static initialization nhẹ, xác định và ít phụ thuộc tài nguyên môi trường. Dời logic tốn kém/dễ lỗi sang pha khởi tạo có kiểm soát khi thích hợp.

Đoạn `Broken` trên là minh họa lỗi; **không** chạy trong chương trình ví dụ phần 4, để giữ stdout phần 4 xác định và thành công.

## 10. Quyền truy cập, final và class initialization là ba vấn đề khác nhau

`Field` có thể mô tả một field `public`, `private`, `static` hoặc `final`, nhưng các thuộc tính này liên quan đến những quy tắc riêng:

- **Khả năng tìm thấy:** `getDeclaredField` tìm field khai báo trực tiếp, bất kể `public`/`private`; `getField` tìm field `public` theo quy tắc phân cấp.
- **Khả năng đọc/ghi:** `Field.get`/`Field.set` áp dụng kiểm tra truy cập từ caller; `setAccessible`/`trySetAccessible` có quy tắc riêng, chịu giới hạn module trên Java hiện đại.
- **Thời điểm initialize:** Khi một thao tác đọc/ghi field `static` được phép thực hiện, lớp khai báo field được initialize khi cần.
- **Bất biến `final`:** Không được giả định `Field.set` có thể thay đổi `static final`. Trong Java hiện đại, static final là nhóm field không thể được Reflection cho phép ghi theo cách thông thường, kể cả khi cố bật accessible override.

Ví dụ đối với field `static int` công khai:

```java
Field f = MyType.class.getDeclaredField("counter");
int oldValue = f.getInt(null);
f.setInt(null, oldValue + 1);
```

Đây là đoạn minh họa trong phương thức có xử lý ngoại lệ và có lớp `MyType` phù hợp; lần `getInt(null)` sẽ initialize lớp khai báo field khi cần. Hai thao tác get-then-set này **không phải phép tăng nguyên tử**, vì còn những luồng khác có thể can thiệp.

Đối với `private static`, việc lấy metadata vẫn có thể thành công nhưng gọi `get`/`set` từ caller không có quyền sẽ thất bại. Không nên khẳng định class đã initialize chỉ vì một lệnh truy cập **bị từ chối trước khi đến giai đoạn đọc/ghi**; xác định lỗi xảy ra ở bước nào.

## 11. Vấn đề đồng thời: khởi tạo một lần không có nghĩa field thread-safe

JVM phối hợp việc khởi tạo class giữa các thread: khi một thread đang thực hiện initialization của một class, các thread khác cần sử dụng class đó phải tuân theo cơ chế chờ/đồng bộ khởi tạo theo quy tắc JVM. Khi initialization hoàn tất thành công, những thread dùng class không tự chạy lại static initializer.

Tuy nhiên, sau đó:

```java
// Hai thao tác tách biệt, không bảo đảm atomic increment:
int count = field.getInt(null);
field.setInt(null, count + 1);
```

một phép đọc rồi ghi qua Reflection vẫn có thể **race**. `static` không tự làm field `volatile`, không khiến phép cập nhật read-modify-write trở thành atomic, và không thay thế đồng bộ của ứng dụng.

Nếu nhiều thread cùng sửa trạng thái tĩnh, cân nhắc `synchronized`, `volatile` đúng mục tiêu visibility, `AtomicInteger` hoặc cơ chế đồng bộ phù hợp. Tránh dùng quá trình initialization như khóa bảo vệ cho toàn bộ vòng đời mutable static state.

Một mối nguy khác là **circular initialization**: initializer của lớp A dùng static state của B trong khi B dùng ngược static state của A. Khi đường đi phụ thuộc nhau, kết quả có thể bất ngờ do thứ tự gán và giá trị mặc định. Do vậy logic `<clinit>` nên tối giản.

## 12. Mẫu lựa chọn API theo mục đích

| Mục đích | Cách tiếp cận | Tác động cần lưu ý |
| --- | --- | --- |
| Liệt kê field phục vụ tài liệu | `type.getDeclaredFields()`, đọc tên/kiểu/modifier | Không yêu cầu đọc giá trị field, thường tránh init lớp đích |
| Xác định lớp sở hữu field | `field.getDeclaringClass()` | Giúp biết class nào sẽ là đối tượng initialization |
| Lấy giá trị `static int` | `field.getInt(null)` | Có thể initialize declaring class |
| Lấy giá trị `static` kiểu tham chiếu | `field.get(null)` | Có thể initialize declaring class |
| Ghi `static int` có quyền ghi | `field.setInt(null, value)` | Có thể initialize trước khi gán; cần đảm bảo thread safety riêng |
| Chỉ load để tra metadata | `Class.forName(name, false, loader)` | Chủ động tránh initialize class được đặt tên |
| Cố gọi vào `static final` bằng Reflection để sửa | **Không nên thiết kế theo hướng này** | Bị giới hạn quyền ghi, không bảo đảm hợp lệ hoặc an toàn |

Trong công cụ khám phá plugin, serializer, dependency-injection container hoặc diagnostic scanner, “chỉ xem tên field” và “lấy giá trị static field để log” là hai quyết định rất khác nhau. Hãy đặt rõ ngưỡng cho phép kích hoạt khởi tạo, nhất là khi lớp có static block kết nối dịch vụ, đọc môi trường hay cấu hình.

## 13. Lỗi phổ biến và câu hỏi tự kiểm tra

### Lỗi thường gặp

1. **Nhầm `getDeclaredField` với `Field.get`:** tên gần giống nhưng một bên trả metadata, một bên truy cập giá trị và có thể trigger init.
2. **Tin rằng `static final` luôn vô hại:** đọc constant trực tiếp có thể được inline; reflective get vẫn có thể initialize class.
3. **Khởi tạo nhầm owner khi kế thừa:** field được lấy từ `Child.class` có thể thực sự thuộc `Parent`; kiểm tra `getDeclaringClass()`.
4. **Dùng `Class.forName(name)` khi chỉ cần cấu trúc:** biến thể mặc định yêu cầu initialization; dùng `Class.forName(name, false, loader)` khi chỉ cần xem metadata.
5. **Nuốt lỗi `ExceptionInInitializerError`:** kết luận “Reflection không đọc được” mà không xem nguyên nhân static initialization.
6. **Cho rằng initialization là đồng bộ mọi cập nhật `static`:** nó chỉ phối hợp quá trình initialization, không thay thế synchronization cho các thao tác tiếp theo.
7. **Cố ghi `static final`:** quyền tìm kiếm field không đồng nghĩa quyền sửa; static final không hỗ trợ ghi reflective thông thường.

### Tự kiểm tra

**Câu 1.** Nếu `Config.class.getDeclaredField("port")` trả về `Field`, điều đó chứng minh static block của `Config` đã chạy chưa?

**Đáp án:** Chưa. Truy vấn metadata không phải yêu cầu đọc/ghi giá trị `static`.

**Câu 2.** Vì sao đọc `public static final int VERSION = 3;` qua code Java thông thường có thể không initialize lớp, nhưng `field.getInt(null)` thì có?

**Đáp án:** `VERSION` là compile-time constant, compiler có thể inline giá trị; `Field.getInt(null)` vẫn là truy cập reflective thực sự tới field `static` và yêu cầu initialize declaring class.

**Câu 3.** `Field.setInt(null, 25)` chạy khi class chưa initialize thì static initializer diễn ra trước hay sau phép ghi?

**Đáp án:** Initialization cần thiết diễn ra **trước** khi phép ghi field thành công; static initializer có thể đặt giá trị ban đầu, sau đó `setInt` ghi đè thành `25`.

**Câu 4.** Nếu field `public static int port` khai báo ở `Parent` và tìm được bằng `Child.class.getField("port")`, lớp nào được initialize do reflective read field đó?

**Đáp án:** `Parent` là declaring class. Không mặc định rằng `Child` cũng initialize.

**Câu 5.** Nếu lần đầu `Field.get(null)` gây `ExceptionInInitializerError`, có nên thử lại ngay với một `Field` khác thuộc cùng class để khởi tạo lại không?

**Đáp án:** Không. Sau khi class initialization thất bại, class nằm ở trạng thái lỗi trong runtime; cần sửa nguyên nhân và có chiến lược khởi động/lifecycle thích hợp.

**Ghi nhớ:** Java Reflection có thể quan sát cấu trúc lớp mà chưa chạy mã khởi tạo, nhưng **đọc/ghi một field `static` bằng `Field.get`/`Field.set` là một hành động runtime có thể kích hoạt initialization của lớp khai báo field**. Kiểm tra `getDeclaringClass()`, phân biệt compile-time constant với reflective access, và chủ động quản lý side effect từ static initializer khi thiết kế công cụ dùng Reflection.
