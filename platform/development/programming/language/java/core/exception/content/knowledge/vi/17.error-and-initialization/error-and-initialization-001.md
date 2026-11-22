# Khi nào `Error` được phát sinh và phạm vi xử lý phù hợp trong Java

Trong Java, `Error` là một nhánh của `Throwable`, thường biểu thị **tình trạng nghiêm trọng** mà phần lớn ứng dụng **không nên cố bắt và tiếp tục chạy như một lỗi nghiệp vụ thông thường**. Ví dụ: JVM không thể cấp phát thêm bộ nhớ (`OutOfMemoryError`), ngăn xếp lời gọi cạn (`StackOverflowError`), một lớp không thể liên kết với định nghĩa đã biên dịch (`LinkageError`) hoặc việc khởi tạo lớp tĩnh thất bại (`ExceptionInInitializerError`).

Tuy nhiên, cần tránh hai phát biểu cực đoan:

- **“Mọi `Error` đều do JVM tự ném và chắc chắn kết thúc toàn bộ tiến trình.”** Sai. Mã Java hoặc thư viện cũng có thể chủ động ném `AssertionError`; một `Error` không được bắt thường làm kết thúc **luồng đang thực thi**, nhưng các luồng khác và tiến trình có thể vẫn tiếp tục.
- **“Đã là `Throwable` thì có thể `catch` rồi retry/tiếp tục bình thường.”** Cũng sai. Nhiều `Error` báo rằng môi trường thực thi, liên kết lớp hoặc một bất biến quan trọng đang không đáng tin cậy. Việc nuốt lỗi và tiếp tục có thể làm hỏng dữ liệu hoặc gây lỗi khó điều tra hơn.

Cách tiếp cận phù hợp: **hiểu loại `Error`, nguồn phát sinh, trạng thái sau lỗi và ranh giới quản lý**. Trong nghiệp vụ thường chỉ xử lý `Exception` phù hợp; ở ranh giới rất hẹp như giám sát một tác vụ/worker, có thể **ghi nhận hoặc thực hiện cleanup tối thiểu rồi chuyển tiếp/để lỗi lan truyền**, thay vì hứa rằng hệ thống đã phục hồi.

Bài học Java 17+ này giải thích phân cấp `Error`, các nhóm lỗi, quan hệ với khởi tạo lớp, phạm vi `catch`, `finally`, `try-with-resources`, hành vi nhiều luồng và hướng xử lý an toàn. Tất cả ví dụ chạy được đều **mô phỏng bằng những lỗi an toàn như `AssertionError`**, không cố tạo `OutOfMemoryError` hoặc `StackOverflowError` thật.

## 1. Vị trí của `Error` trong hệ thống ngoại lệ

Phân cấp rút gọn:

~~~text
java.lang.Object
└── java.lang.Throwable
    ├── java.lang.Exception
    │   ├── IOException                         checked
    │   ├── SQLException                        checked
    │   └── java.lang.RuntimeException          unchecked
    │       ├── IllegalArgumentException
    │       └── IllegalStateException
    └── java.lang.Error                         unchecked
        ├── java.lang.VirtualMachineError
        │   ├── OutOfMemoryError
        │   ├── StackOverflowError
        │   └── InternalError
        ├── java.lang.LinkageError
        │   ├── ExceptionInInitializerError
        │   ├── NoClassDefFoundError
        │   ├── NoSuchMethodError
        │   └── UnsupportedClassVersionError
        ├── AssertionError
        └── ThreadDeath
~~~

Những điểm cần nhớ:

1. `Exception` **không phải** superclass của `Error`; cả hai là các nhánh trực tiếp dưới `Throwable`.
2. `RuntimeException` cũng **không phải** superclass của `Error`.
3. `Error` và mọi lớp con được coi là **unchecked** trong kiểm tra ngoại lệ của compiler; không cần `throws Error` và không buộc caller phải `catch`.
4. `catch (Exception ex)` **không bắt được** một đối tượng `Error` thực sự.
5. `catch (Throwable t)` có thể bắt `Error` vì `Throwable` là superclass của cả `Error` và `Exception`, nhưng điều đó không làm việc bắt rộng trở thành giải pháp đúng.
6. Một `Error` vẫn là đối tượng `Throwable`: nó có `message`, `cause`, stack trace và có thể có `suppressed exceptions`, tùy loại và cấu hình đối tượng.

Theo tài liệu Java SE 17, `Error` mô tả những vấn đề nghiêm trọng mà ứng dụng hợp lý thông thường không nên cố bắt. Đây là **định hướng xử lý mặc định**, không phải luật JVM cấm viết `catch (Error)`.

## 2. Khi nào các loại `Error` có thể phát sinh?

| Nhóm/tên | Tình huống tiêu biểu | Phản ứng thường phù hợp |
| --- | --- | --- |
| `OutOfMemoryError` | JVM không thể đáp ứng một yêu cầu cấp phát do giới hạn bộ nhớ/tài nguyên liên quan | Xem đây là sự cố nghiêm trọng; ghi nhận bằng giám sát ngoài tiến trình, phân tích heap và giới hạn tài nguyên |
| `StackOverflowError` | Một luồng vượt quá khả năng ngăn xếp, thường do đệ quy quá sâu/vòng lặp đệ quy | Điều tra đệ quy, điều kiện dừng, cấu trúc dữ liệu chu kỳ và cấu hình stack; không đơn giản retry |
| `InternalError` | JVM báo sự cố nội bộ nghiêm trọng | Xem xét JVM, thư viện native và môi trường; không tự xử lý như validation |
| `LinkageError` | Các lớp/thành phần nhị phân không tương thích hoặc không thể liên kết | Sửa dependency, bytecode, version, classloader, quy trình build/deploy |
| `NoSuchMethodError` | Runtime không tìm thấy method tương thích mà bytecode đã tham chiếu | Kiểm tra sự lệch giữa phiên bản biên dịch và phiên bản chạy |
| `UnsupportedClassVersionError` | Runtime không hỗ trợ phiên bản class file được nạp | Chạy bằng JDK phù hợp hoặc biên dịch `--release` tương thích |
| `ExceptionInInitializerError` | Quá trình khởi tạo static của class/interface thất bại bằng một `Throwable` không thuộc `Error` | Kiểm tra `getCause()` và initializer/factory tĩnh; sửa cấu hình hoặc code |
| `NoClassDefFoundError` | JVM/ClassLoader không tìm/nạp được định nghĩa cần thiết, hoặc lớp đang ở trạng thái khởi tạo lỗi | Phân biệt thiếu class/dependency với lỗi khởi tạo lớp trước đó |
| `AssertionError` | Một câu `assert` được bật thất bại hoặc code chủ động `throw new AssertionError(...)` | Sửa bất biến/giả định sai; thường không coi là lỗi đầu vào có thể khôi phục |
| `ThreadDeath` | Tình huống legacy liên quan đến cơ chế dừng luồng | Không bắt/nuốt; tránh cơ chế dừng luồng không an toàn |

Đây là **tình huống phổ biến**, không phải bảng ánh xạ một-một cho mọi trường hợp. Chẳng hạn `NoClassDefFoundError` không chứng minh ngay rằng một file `.class` bị thiếu; trước đó một lớp có thể đã **thất bại khi khởi tạo**. Và `OutOfMemoryError` không luôn đơn giản là “heap đang đầy”; thông điệp và dữ liệu chẩn đoán cụ thể có thể chỉ ra vùng tài nguyên khác.

## 3. JVM `Error` khác với `Exception` thông thường ở điểm nào?

Một `IOException` từ thao tác đọc file là tình huống chương trình có thể dự kiến, xử lý, thông báo người dùng hoặc thử một đường đọc khác nếu hợp đồng cho phép. Một `IllegalArgumentException` từ đầu vào sai có thể được xử lý ở ranh giới validation.

Ngược lại, nếu hệ thống gặp `OutOfMemoryError` trong lúc xử lý:

- Ngay cả thao tác **ghi log** có thể cần cấp phát đối tượng/buffer mới và tiếp tục thất bại.
- Trạng thái của một thao tác đang thực hiện có thể chưa hoàn chỉnh; ứng dụng chưa biết giao dịch đã commit hay chưa.
- Việc trả một HTTP response thông thường có thể cần tài nguyên không còn sẵn.
- Retry lập tức có thể lặp lại lỗi hoặc tăng áp lực bộ nhớ.
- Một luồng bị ảnh hưởng không nhất thiết là toàn bộ tiến trình; nhưng các luồng khác còn chạy cũng **không tự chứng minh hệ thống khỏe mạnh**.

Do đó, không nên viết một quy tắc `catch (Throwable)` cho mọi method nghiệp vụ rồi tiếp tục như thể request thất bại đã được khôi phục. Hãy đặt **giới hạn phục hồi ở nơi thật sự có đủ thông tin về trạng thái và quyền sở hữu tài nguyên**.

## 4. `Error` là unchecked nhưng vẫn có thể xuất hiện ở runtime

Một method có thể ném `AssertionError` mà không ghi `throws`:

~~~java
static void verify() {
    throw new AssertionError("bất biến bị vi phạm");
}
~~~

Cả việc tạo đối tượng lẫn `throw` là hành vi Java hợp lệ. Caller không bị compiler buộc:

~~~java
try {
    verify();
} catch (AssertionError err) {
    System.out.println(err.getMessage());
}
~~~

**Không phải cứ compile được thì nên catch.** Khi `AssertionError` báo một bất biến lập trình bị phá vỡ, cách xử lý đáng tin thường là **ngừng thao tác không an toàn, lưu thông tin chẩn đoán và sửa bug**. Bắt lỗi để chứng minh cơ chế hoạt động có thể hợp lý trong chương trình học hoặc test, nhưng không nên là quy tắc mặc định của hệ thống sản phẩm.

`throws Error` trong chữ ký method cũng không làm compiler áp đặt catch-or-declare. Các công bố `throws` nên tập trung vào những checked exception mà caller có nghĩa vụ xử lý.

## 5. Ví dụ Java 17: `catch (Exception)` không bắt `Error`

Tệp `CatchErrorDemo.java`:

~~~java
public class CatchErrorDemo {
    static void validateInvariant() {
        throw new AssertionError("bất biến bị vi phạm");
    }

    public static void main(String[] args) {
        try {
            validateInvariant();
        } catch (Exception ex) {
            System.out.println("Bắt Exception");
        } catch (AssertionError err) {
            System.out.println("Bắt AssertionError: " + err.getMessage());
        }
        System.out.println("Chương trình minh họa tiếp tục");
    }
}
~~~

Lệnh chạy:

~~~bash
javac --release 17 -encoding UTF-8 CatchErrorDemo.java
java CatchErrorDemo
~~~

Stdout chính xác:

~~~text
Bắt AssertionError: bất biến bị vi phạm
Chương trình minh họa tiếp tục
~~~

Giải thích:

- `validateInvariant()` ném **đối tượng `AssertionError`**, không phải một `Exception`.
- `catch (Exception ex)` không khớp với loại runtime `AssertionError`.
- `catch (AssertionError err)` khớp, nên ví dụ in đúng thông báo.
- Sau `catch`, `main` tiếp tục vì **chương trình minh họa đã cố ý xử lý lỗi và không ném lại**.
- Không suy từ đó rằng production nên nuốt mọi `AssertionError`; ví dụ chỉ chứng minh **phân cấp và dispatch của `catch`**.

Nếu viết một `catch (Throwable)`, nó có thể bắt `AssertionError`, `OutOfMemoryError` và cả `Exception`. Nhưng nhánh quá rộng dễ làm lẫn lỗi khôi phục được với tình trạng nghiêm trọng; cần phân biệt mục đích **quan sát** và **phục hồi**.

## 6. `VirtualMachineError`: dấu hiệu điều kiện thực thi nghiêm trọng

`VirtualMachineError` là một nhánh `Error` dành cho những vấn đề cho thấy JVM không thể tiếp tục làm việc bình thường theo yêu cầu trong một số điều kiện.

Các ví dụ quan trọng:

- **`OutOfMemoryError`**: không cấp phát được do giới hạn tài nguyên. Có thể cần heap dump hoặc dữ liệu giám sát đã được cấu hình **trước khi lỗi xảy ra**.
- **`StackOverflowError`**: stack của một luồng bị cạn, thường do đệ quy quá sâu, điều kiện dừng sai hoặc dữ liệu chứa chu trình khi dùng đệ quy.
- **`InternalError`**: JVM phát hiện điều kiện lỗi nội bộ; cần xem thông điệp, phiên bản JVM, native code và các log chẩn đoán liên quan.

Không nên cố tình tạo các lỗi này bằng cách:

~~~java
// KHÔNG CHẠY: minh họa anti-pattern nguy hiểm.
// while (true) {
//     buffers.add(new byte[100_000_000]); // Cố làm cạn heap.
// }
~~~

Hoặc:

~~~java
// KHÔNG CHẠY: cố tình dùng đệ quy vô hạn.
// static void recurseForever() { recurseForever(); }
~~~

Những thử nghiệm này có thể làm chậm, treo hoặc cạn tài nguyên máy chạy và **không cần thiết** để học cách xử lý `Error`. Bài dùng `AssertionError` được tạo có chủ đích để minh họa cơ chế ném/bắt mà không gây hại tài nguyên.

Khi điều tra lỗi thực tế, nên thu thập phiên bản Java, cờ JVM, tài nguyên, metric, stack trace, dump thích hợp và thời điểm phát sinh. Việc tự động bắt và retry `OutOfMemoryError` trong mọi request thường không có cơ sở an toàn.

## 7. `LinkageError`: lỗi tương thích nhị phân, classpath và classloader

Một nhóm `Error` quan trọng khác xuất hiện **không phải do dữ liệu đầu vào sai**, mà do chương trình đã biên dịch và môi trường runtime không còn tương thích.

Ví dụ:

- `NoSuchMethodError`: code đã biên dịch tham chiếu tới một method không tìm thấy theo định nghĩa runtime đang được nạp.
- `NoSuchFieldError`: tương tự cho field.
- `IncompatibleClassChangeError`: phát hiện một dạng thay đổi class/interface không tương thích.
- `UnsupportedClassVersionError`: JVM hiện tại không hỗ trợ phiên bản class file.
- `VerifyError`: class file vi phạm điều kiện verification.
- `NoClassDefFoundError`: không tìm nạp được định nghĩa class cần thiết hoặc class đã rơi vào trạng thái khởi tạo lỗi.

Ví dụ tình huống thực tế:

~~~text
Biên dịch Module A với Library X phiên bản mới
                  ↓
Triển khai Module A với Library X phiên bản cũ
                  ↓
Lúc chạy gọi method chỉ có trong bản mới
                  ↓
             NoSuchMethodError
~~~

Hướng khắc phục thường là **sửa version dependency, classpath/module path, classloader hoặc build/deployment artifact**, rồi triển khai lại. Bắt `NoSuchMethodError` rồi trả dữ liệu mặc định có thể che một deployment lỗi và làm hệ thống vận hành ở trạng thái sai.

**Phân biệt** `ClassNotFoundException` (checked exception có thể được API nạp lớp/reflective lookup công bố) với `NoClassDefFoundError` (lỗi linkage/runtime). Dù thông điệp có vẻ gần nhau, chúng thuộc những nhánh và hoàn cảnh phát sinh khác nhau.

## 8. `ExceptionInInitializerError`: một `Error` gắn với khởi tạo lớp

Khi một class được **khởi tạo lần đầu**, Java chạy các **static field initializers** và **static initializer blocks** thích hợp. Nếu quá trình đó hoàn tất bất thường bằng một `Throwable` **không phải `Error`**, JVM thông thường tạo `ExceptionInInitializerError` bao nguyên nhân đó.

Ví dụ một static field gọi factory:

~~~java
static final String VALUE = initialize();

static String initialize() {
    throw new IllegalStateException("thiếu cấu hình");
}
~~~

Nếu phương thức này được dùng làm initializer của lớp, một lần truy cập kích hoạt khởi tạo sẽ làm `initialize()` ném `IllegalStateException`. JVM phản ánh lỗi khởi tạo class bằng `ExceptionInInitializerError`, có `getCause()` trỏ tới `IllegalStateException`.

**Hai lớp thông tin cần đọc:**

1. **Ngoại lệ ngoài cùng `ExceptionInInitializerError`**: thao tác khởi tạo lớp thất bại.
2. **Cause của nó**: lý do thực tế ở phần code đang khởi tạo, ví dụ `IllegalStateException("thiếu cấu hình")`.

Với phiên bản Java hiện đại, ưu tiên `getCause()`. API `ExceptionInInitializerError.getException()` tồn tại vì lịch sử và vẫn được hỗ trợ, nhưng không cần thiết cho hầu hết code mới.

Một điểm đặc biệt: nếu static initializer **trực tiếp ném một `Error`**, theo JLS, `Error` đó thường được truyền ra **mà không bị bọc trong `ExceptionInInitializerError`**. Cả hai đường thất bại đều có thể khiến lớp được đánh dấu không thể khởi tạo lại trong cùng ngữ cảnh classloader.

## 9. Java 17: lần khởi tạo đầu và lần dùng lớp tiếp theo

Tệp `ClassInitializationErrorDemo.java`:

~~~java
public class ClassInitializationErrorDemo {
    static final class BrokenConfig {
        static final String VALUE = initialize();

        static String initialize() {
            System.out.println("Bắt đầu khởi tạo lớp");
            throw new IllegalStateException("thiếu cấu hình");
        }
    }

    public static void main(String[] args) {
        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                System.out.println(BrokenConfig.VALUE);
            } catch (ExceptionInInitializerError err) {
                System.out.println("Lần " + attempt + ": "
                        + err.getClass().getSimpleName());
                System.out.println("Nguyên nhân: "
                        + err.getCause().getClass().getSimpleName()
                        + " - " + err.getCause().getMessage());
            } catch (NoClassDefFoundError err) {
                System.out.println("Lần " + attempt + ": "
                        + err.getClass().getSimpleName());
            }
        }
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 -encoding UTF-8 ClassInitializationErrorDemo.java
java ClassInitializationErrorDemo
~~~

Stdout chính xác:

~~~text
Bắt đầu khởi tạo lớp
Lần 1: ExceptionInInitializerError
Nguyên nhân: IllegalStateException - thiếu cấu hình
Lần 2: NoClassDefFoundError
~~~

**Giải thích chi tiết:**

- `BrokenConfig.VALUE` **không phải compile-time constant**, vì nó lấy giá trị từ lời gọi method. Truy cập nó kích hoạt quá trình khởi tạo `BrokenConfig`.
- Lần đầu, `initialize()` in thông báo rồi ném `IllegalStateException`.
- JVM bọc lỗi này thành `ExceptionInInitializerError`; `getCause()` giữ lại lỗi thực tế.
- Lớp bị đánh dấu **erroneous** trong ngữ cảnh tải lớp đang xét.
- Lần thứ hai, JVM **không thử chạy lại initializer**; nó báo `NoClassDefFoundError` vì lớp đang ở trạng thái khởi tạo lỗi.
- Chỉ có một dòng `Bắt đầu khởi tạo lớp`, cho thấy initializer không được thực thi lại ở lượt tiếp theo.

**Đây là lý do không nên `catch(ExceptionInInitializerError)` rồi thử lại `BrokenConfig.VALUE` như một cơ chế phục hồi.** Việc sửa file cấu hình ngay trong tiến trình không tự đảo ngược trạng thái class initialization đã thất bại. Phục hồi có thể đòi hỏi tái thiết lập môi trường/lifecycle hoặc một classloader mới có kiểm soát; với ứng dụng thông thường, sửa lỗi và khởi động lại tiến trình là hướng an toàn hơn.

`NoClassDefFoundError` cũng có thể có nguyên nhân khác (ví dụ thiếu dependency), vì vậy không được kết luận mọi `NoClassDefFoundError` đều là “đã từng khởi tạo thất bại”. Hãy xem log và lỗi đầu tiên.

## 10. Nếu static initializer ném `Error` ngay từ đầu?

Tệp `DirectErrorInitializerDemo.java`:

~~~java
public class DirectErrorInitializerDemo {
    static final class BrokenPlugin {
        static final Object INSTANCE = create();

        static Object create() {
            System.out.println("Đang khởi tạo plugin");
            throw new AssertionError("hợp đồng plugin sai");
        }
    }

    public static void main(String[] args) {
        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                System.out.println(BrokenPlugin.INSTANCE);
            } catch (AssertionError err) {
                System.out.println("Lần " + attempt + ": "
                        + err.getClass().getSimpleName());
            } catch (NoClassDefFoundError err) {
                System.out.println("Lần " + attempt + ": "
                        + err.getClass().getSimpleName());
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 DirectErrorInitializerDemo.java
java DirectErrorInitializerDemo
~~~

Stdout chính xác:

~~~text
Đang khởi tạo plugin
Lần 1: AssertionError
Lần 2: NoClassDefFoundError
~~~

So với ví dụ trước:

| Đường khởi tạo static thất bại | Lần dùng đầu | Lần dùng tiếp trong cùng ngữ cảnh |
| --- | --- | --- |
| Initializer ném `IllegalStateException` | `ExceptionInInitializerError` với cause là `IllegalStateException` | `NoClassDefFoundError` |
| Initializer ném `AssertionError` | Chính `AssertionError` được truyền ra | `NoClassDefFoundError` |

JLS có những chi tiết đặc biệt, chẳng hạn việc không cấp phát được đối tượng lỗi bọc trong điều kiện thiếu bộ nhớ. Bảng mô tả **đường thực thi bình thường được kiểm chứng trong ví dụ**, không phải bảo đảm tuyệt đối của mọi JVM trong mọi điều kiện sự cố.

Lưu ý phạm vi: tên `BrokenPlugin` trong ví dụ chỉ là tên class lồng để minh họa, không yêu cầu hệ thống plugin thật.

## 11. Khởi tạo lớp và khởi tạo đối tượng là hai quá trình khác nhau

Một constructor hoặc instance field initializer có thể ném `IllegalStateException` khi tạo đối tượng:

~~~java
class UserSession {
    UserSession() {
        throw new IllegalStateException("phiên không hợp lệ");
    }
}
~~~

Nếu `new UserSession()` thất bại, điều đó **không tự động** có nghĩa class `UserSession` ở trạng thái class initialization lỗi. Các lần gọi constructor tiếp theo có thể vẫn được phép và có thể lại thất bại vì cùng nguyên nhân.

Ngược lại, lỗi từ một **static initializer** có thể dẫn tới `ExceptionInInitializerError` hoặc truyền một `Error` ra ngoài, rồi class bị đánh dấu erroneous.

Bảng phân biệt:

| Nơi thất bại | Lỗi người gọi thường quan sát | Có tự làm lớp thành erroneous? |
| --- | --- | --- |
| Thân instance constructor | Ngoại lệ được ném từ constructor | Không, chỉ vì constructor thất bại |
| Instance field initializer | Ngoại lệ từ quá trình tạo object | Không, chỉ vì instance initializer thất bại |
| Static field initializer | Có thể là `ExceptionInInitializerError` hoặc một `Error` gốc | Có thể, nếu class initialization kết thúc bất thường |
| Static initializer block | Tương tự static field initializer | Có thể |
| Liên kết/nạp class thất bại | Một loại `LinkageError` phù hợp | Tùy loại lỗi và giai đoạn JVM đang thực hiện |

Một static initializer **không được để checked exception thoát trực tiếp** theo cách công bố `throws` trên constructor. Nếu nó gọi API ném `IOException`, phải xử lý hoặc chuyển thành một unchecked exception đúng hợp đồng; khi unchecked exception đó thoát trong class initialization, nó có thể được bọc thành `ExceptionInInitializerError`.

## 12. `AssertionError` và từ khóa `assert`

`AssertionError` là một lớp `Error` thường gắn với kiểm tra **bất biến lập trình**. Java có cú pháp:

~~~java
assert condition : "thông điệp kiểm tra";
~~~

Khi assertion **được bật** cho lớp tương ứng, nếu `condition` là `false`, Java ném `AssertionError`. Khi assertions bị tắt, câu lệnh `assert` không thực hiện kiểm tra đó.

Vì vậy **không dùng `assert` cho validation đầu vào bắt buộc**, ví dụ xác thực mật khẩu, quyền truy cập, số tiền hoặc ràng buộc dữ liệu bên ngoài. Những kiểm tra ấy phải hoạt động dù JVM có bật assertions hay không.

Với tiền điều kiện API, thường dùng:

~~~java
static void pay(int amount) {
    if (amount <= 0) {
        throw new IllegalArgumentException("amount phải dương");
    }
}
~~~

`IllegalArgumentException` là loại unchecked thuộc nhánh `RuntimeException` và phù hợp cho đầu vào sai. Một bug bất biến nội bộ có thể được biểu diễn bằng `AssertionError` hoặc ngoại lệ khác theo chính sách dự án, nhưng nó không thay thế validation.

Không đặt side effect bắt buộc trong biểu thức `assert` vì side effect có thể không xảy ra khi assertions bị tắt.

## 13. Java 17: so sánh `assert` bật và tắt

Tệp `AssertionsModeDemo.java`:

~~~java
public class AssertionsModeDemo {
    static void check(int value) {
        assert value >= 0 : "giá trị âm";
        System.out.println("Tiếp tục với: " + value);
    }

    public static void main(String[] args) {
        System.out.println("Assertions bật: "
                + AssertionsModeDemo.class.desiredAssertionStatus());
        try {
            check(-1);
        } catch (AssertionError err) {
            System.out.println("AssertionError: " + err.getMessage());
        }
    }
}
~~~

Biên dịch một lần:

~~~bash
javac --release 17 -encoding UTF-8 AssertionsModeDemo.java
~~~

Chạy với assertions **tắt**:

~~~bash
java -da AssertionsModeDemo
~~~

Stdout:

~~~text
Assertions bật: false
Tiếp tục với: -1
~~~

Chạy với assertions **bật**:

~~~bash
java -ea AssertionsModeDemo
~~~

Stdout:

~~~text
Assertions bật: true
AssertionError: giá trị âm
~~~

`-ea` là tùy chọn bật assertions, `-da` là tùy chọn tắt. Khi chạy trên môi trường khác, các cài đặt assertion có thể được cấu hình theo package/class; ví dụ dùng cờ minh bạch để giữ kết quả ổn định.

Phần quan trọng nhất là **cùng một mã nguồn có thể không chạy kiểm tra `assert` khi bị tắt**. Đó là lý do assertion chỉ nên dùng cho giả định/bất biến nội bộ thích hợp, không cho mọi điều kiện bắt buộc của hệ thống.

## 14. Phạm vi `catch` phù hợp: quan sát, thu dọn và khôi phục

Khi xử lý `Error`, cần tách ba mục tiêu:

| Mục tiêu | Có thể phù hợp? | Cảnh báo |
| --- | --- | --- |
| **Quan sát**: ghi nhận loại, stack trace, metric, trạng thái tác vụ | Có, ở ranh giới rất rõ; ưu tiên cơ chế giám sát đáng tin | Việc log có thể thất bại khi hết bộ nhớ hoặc tài nguyên |
| **Thu dọn**: giải phóng resource trong `finally` hoặc `try-with-resources` | Thường thích hợp trong luồng thoát Java thông thường | Không bảo đảm nếu JVM/process dừng cưỡng bức, `Runtime.halt` hoặc lỗi nghiêm trọng khiến tiến trình không thể tiếp tục |
| **Khôi phục**: nuốt `Error` rồi cho request/worker tiếp tục như không có gì | Thường không nên | Chỉ xem xét cho những lỗi được thiết kế có ranh giới, đã chứng minh trạng thái còn hợp lệ |

Đừng nhầm việc **có thể bắt một `Error`** với việc **đã khôi phục nguyên nhân gây lỗi**. Ví dụ một `NoSuchMethodError` do deployment lệch version không được khắc phục chỉ bằng một nhánh `catch (NoSuchMethodError)`.

Phần lớn code nghiệp vụ nên chỉ bắt các loại `Exception` cụ thể có thể xử lý. Ở một bộ điều phối tác vụ, nếu thực sự cần ghi lại lỗi nghiêm trọng, có thể có tầng giám sát ngoài luồng/ngoài tiến trình; việc phục hồi tài nguyên/chạy lại cần đánh giá riêng theo loại lỗi và trạng thái hệ thống.

## 15. `finally` và `try-with-resources` khi một `Error` được ném

Khi Java thực hiện đường thoát bất thường bình thường vì một `Error`, các cơ chế cleanup trong ngôn ngữ vẫn có thể được thực thi:

~~~java
try {
    throw new AssertionError("sự cố");
} finally {
    System.out.println("Cleanup trong finally");
}
~~~

Thông thường, dòng trong `finally` được thực hiện **trước khi `AssertionError` tiếp tục lan truyền**. Điều này không có nghĩa bạn nên catch Error.

Tương tự, `try-with-resources` gọi `close()` khi thoát, kể cả khi phần thân ném `Error`. Nếu `close()` còn ném ngoại lệ, ngoại lệ đóng có thể được đính kèm thành **suppressed** của `Error` chính.

Điều cần lưu ý khi soạn ví dụ: nếu `close()` công bố `throws IOException`, compiler vẫn xét **checked exception từ implicit call tới `close()`**. Dù phần thân ví dụ cố ý ném `AssertionError`, bạn vẫn cần bắt hoặc khai báo `IOException` có thể phát sinh từ cleanup.

## 16. Java 17: `Error` vẫn có thể nhận suppressed exception từ cleanup

Tệp `ErrorCleanupDemo.java`:

~~~java
import java.io.IOException;

public class ErrorCleanupDemo {
    static final class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("Đóng tài nguyên");
            throw new IOException("không đóng được");
        }
    }

    public static void main(String[] args) throws IOException {
        try (Resource ignored = new Resource()) {
            throw new AssertionError("lỗi kiểm tra");
        } catch (AssertionError err) {
            System.out.println("Error chính: " + err.getMessage());
            System.out.println("Số suppressed: " + err.getSuppressed().length);
            System.out.println("Suppressed: "
                    + err.getSuppressed()[0].getMessage());
        } finally {
            System.out.println("Finally chạy");
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 ErrorCleanupDemo.java
java ErrorCleanupDemo
~~~

Stdout chính xác:

~~~text
Đóng tài nguyên
Error chính: lỗi kiểm tra
Số suppressed: 1
Suppressed: không đóng được
Finally chạy
~~~

Giải thích:

1. Phần thân `try` ném `AssertionError`.
2. Java tự gọi `Resource.close()`; method in `Đóng tài nguyên` rồi ném `IOException`.
3. `AssertionError` vẫn là lỗi chính; `IOException` từ cleanup được thêm như **suppressed exception**.
4. `catch (AssertionError)` của ví dụ in lỗi chính và lỗi phụ, rồi `finally` in thông báo kết thúc.
5. `main` khai báo `throws IOException` để đáp ứng quy tắc kiểm tra checked exception của `close()`. Đường thực thi cụ thể này vẫn giữ `AssertionError` làm lỗi chính và không để `IOException` thoát độc lập.
6. Trong code tổng quát phải kiểm tra độ dài của `getSuppressed()` trước khi truy cập `[0]`; ví dụ cố định biết chính xác có một lỗi đóng.

Ví dụ chỉ mô phỏng một `AssertionError` chủ động ném. Nó **không chứng minh** mọi lỗi JVM thảm khốc đều để `finally` hoàn tất. Nếu JVM chết/tiến trình bị `kill` hoặc `Runtime.halt`, Java không hứa cleanup sẽ được thực thi.

## 17. `Error` trong một worker thread có nhất thiết làm chết cả JVM?

Không. Khi một `Throwable` không được bắt thoát khỏi entry point của **một luồng**, luồng đó có thể kết thúc và cơ chế **uncaught exception handling** có thể nhận thông tin lỗi. Những luồng khác có thể vẫn chạy, tùy kiến trúc chương trình.

Ví dụ minh họa đơn luồng worker, không gây lỗi JVM thật.

Tệp `WorkerThreadErrorDemo.java`:

~~~java
public class WorkerThreadErrorDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(
                () -> { throw new AssertionError("worker thất bại"); },
                "worker-demo");

        worker.setUncaughtExceptionHandler((thread, error) ->
                System.out.println("Uncaught tại " + thread.getName()
                        + ": " + error.getClass().getSimpleName()));

        worker.start();
        worker.join();
        System.out.println("Main tiếp tục");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 WorkerThreadErrorDemo.java
java WorkerThreadErrorDemo
~~~

Stdout chính xác:

~~~text
Uncaught tại worker-demo: AssertionError
Main tiếp tục
~~~

Điều này chỉ chứng minh: **một `AssertionError` không bắt trong một worker có thể chấm dứt luồng worker, gọi handler và vẫn để luồng main tiếp tục**.

Không được suy ra rằng nếu luồng main còn sống thì hệ thống luôn có thể phục hồi. Worker có thể đang giữ lock, đang xử lý trạng thái nửa chừng, hoặc có giao dịch chưa nhất quán; cần phân tích ranh giới tác vụ và trạng thái trước khi chạy lại công việc.

Cũng không nên dùng `UncaughtExceptionHandler` làm nơi nỗ lực phục hồi đầy đủ sau `OutOfMemoryError`. Handler nên tối giản, không phụ thuộc giả định rằng còn đủ tài nguyên để thực hiện các thao tác phức tạp.

## 18. Nguyên tắc `catch` trong code nghiệp vụ

Các ví dụ thường nên theo mẫu:

~~~java
// Minh họa trong phương thức có thể ném IOException.
try {
    readData();
} catch (java.io.IOException ex) {
    // Xử lý tình huống I/O đã được hợp đồng công bố.
}
~~~

Hoặc đối với một request boundary cần phân loại nhiều lỗi recoverable:

~~~java
try {
    processRequest();
} catch (IllegalArgumentException ex) {
    // Phản hồi lỗi đầu vào theo hợp đồng của API.
} catch (Exception ex) {
    // Ghi nhận thất bại không dự kiến trong nhánh Exception.
    // Quyết định có trả response hoặc kết thúc tác vụ dựa trên trạng thái.
}
~~~

Đây là **mã minh họa không độc lập**, cần định nghĩa `readData()` và `processRequest()`. Điểm đáng nhớ: nhánh `catch (Exception)` **không bao gồm** `Error`. Đây thường là một ưu điểm vì nó tránh nuốt các lỗi nghiêm trọng ngoài phạm vi nghiệp vụ thông thường.

Chỉ thêm `catch (Error)` hoặc `catch (Throwable)` khi có lý do đặc biệt: ví dụ một **ranh giới giám sát**, một test framework, hoặc một thành phần hạ tầng cần tối thiểu hóa mất thông tin và **phải có chính sách sau khi bắt**. Không để một bộ xử lý HTTP tùy tiện chuyển `OutOfMemoryError` thành mã lỗi bình thường rồi tiếp tục nhận yêu cầu mới.

## 19. Nếu buộc phải quan sát `Error` ở ranh giới hạ tầng

Một ý tưởng cho ranh giới rất hẹp:

~~~java
// MÃ MINH HỌA, không phải chính sách recovery tổng quát.
try {
    runWorker();
} catch (Error err) {
    recordCriticalFailureMinimal(err);
    throw err;
}
~~~

`runWorker()` và `recordCriticalFailureMinimal(...)` là các hàm phụ thuộc hệ thống. Logic trên **không nuốt Error**: sau ghi nhận, nó ném lại để cấp cao hơn biết rằng tác vụ đã kết thúc bất thường.

Cảnh báo:

- `recordCriticalFailureMinimal` vẫn có thể thất bại vì thiếu bộ nhớ hoặc lỗi tương tự.
- Nếu ghi nhận lỗi ném lỗi mới, bạn có thể vô tình che `Error` gốc. Cần thiết kế đường giám sát riêng và tối giản.
- Bắt và ném lại một `Error` không tự rollback giao dịch hoặc hoàn nguyên các side effect.
- Với JVM crash/termination hoặc một số lỗi native, code Java có thể không còn cơ hội thực thi handler.
- Nếu mục tiêu chỉ là thu dọn resource thông thường, dùng `finally` hoặc `try-with-resources` thay vì catch rộng.

Trong nhiều ứng dụng, **không viết `catch(Error)`** mà dùng giám sát tiến trình/container, cơ chế restart có kiểm soát và logs/dumps được cấu hình sẵn là lựa chọn thực tế và an toàn hơn.

## 20. Một `Error` có thể được bọc bởi framework không?

Có những framework hoặc API không đưa nguyên đối tượng ra ngoài ở mọi tầng. Chúng có thể bọc `Throwable` hoặc chứa nó trong kết quả async, tùy hợp đồng của API.

Ví dụ các API `Future`/`Executor` có cơ chế nhận lỗi của tác vụ thông qua result hoặc một `ExecutionException` khi gọi `Future.get()`; cause bên trong có thể là `Error` gốc. Điều này không biến `Error` thành một lỗi nghiệp vụ recoverable.

Khi phân tích:

1. Xem **loại ngoài cùng** đang được bắt.
2. Kiểm tra **`getCause()`** (và những cause sâu hơn).
3. Xem **`getSuppressed()`** nếu có cleanup/close.
4. Đối chiếu stack trace và mã xử lý tại boundary.
5. Không thay đổi chính sách chỉ vì có một wrapper thuộc nhánh `Exception`.

Ví dụ nếu có `ExecutionException` bao `OutOfMemoryError`, việc caller bắt được `ExecutionException` không đồng nghĩa việc có thể lặp lại tác vụ an toàn. Cần đánh giá **nguyên nhân thực tế** và trạng thái tài nguyên.

## 21. Bảng quyết định: khi nào nên bắt, khi nào nên để lan truyền?

| Ngữ cảnh | Hướng tiếp cận ưu tiên | Giải thích |
| --- | --- | --- |
| Validation request sai | Dùng/bắt exception nghiệp vụ hoặc `IllegalArgumentException` thích hợp | Có thể phản hồi rõ ràng cho caller |
| File/network thất bại | Xử lý/bọc `IOException` theo hợp đồng | Có đường khôi phục hoặc báo lỗi được công bố |
| `AssertionError` trong test | Test runner/framework có thể bắt để ghi test thất bại | Đây là ranh giới được thiết kế để quan sát lỗi test |
| `AssertionError` về bất biến sản phẩm | Thường xem là bug nghiêm trọng; không nuốt | Trạng thái nghiệp vụ có thể không đáng tin |
| `NoSuchMethodError` sau deploy | Dừng/đánh dấu deployment lỗi, sửa dependency | Retry cùng code/dependency không sửa được liên kết |
| `ExceptionInInitializerError` | Đọc cause, sửa initializer/cấu hình; không retry class mù quáng | Class có thể đã thành erroneous |
| `OutOfMemoryError` | Giám sát/heap dump/restart có kiểm soát; không catch đại trà | Khả năng phục hồi trong cùng tiến trình không đáng tin |
| `StackOverflowError` | Sửa thuật toán/đệ quy, xem dữ liệu chu kỳ hoặc stack limit | Retry cùng lời gọi có thể tái hiện ngay |
| Ranh giới quản lý worker | Có thể ghi nhận tối thiểu, bảo toàn/rethrow hoặc để uncaught handler nhận | Chỉ phục hồi khi chứng minh được ranh giới trạng thái |
| `finally`/`try-with-resources` | Dùng cho cleanup bình thường | Không hứa cleanup trong mọi kiểu dừng tiến trình |

Bảng là hướng dẫn thực hành, không phải bảo đảm rằng mọi `Error` đều khiến hệ thống không thể tiếp tục. Mức độ xử lý phụ thuộc loại lỗi, lớp phần mềm và khả năng cô lập tác vụ thực tế.

## 22. Các nhầm lẫn phổ biến và cách sửa

| Nhầm lẫn | Thực tế |
| --- | --- |
| `Error` là subclass của `Exception` | Không. Chúng là hai nhánh dưới `Throwable`. |
| `catch(Exception)` xử lý cả OOM/StackOverflow | Không bắt được `OutOfMemoryError`/`StackOverflowError`. |
| `Error` luôn khiến cả JVM dừng ngay | Một `Error` không được bắt có thể chỉ chấm dứt luồng; không suy ra an toàn toàn tiến trình. |
| `Error` không thể bị người lập trình tạo | Code có thể `throw new AssertionError(...)` hoặc tạo Error khác. |
| `Error` bắt buộc phải khai báo `throws` | Không; `Error` thuộc unchecked. |
| Bắt và bỏ qua `OutOfMemoryError` giúp ứng dụng khỏe lại | Không có bảo đảm đó; còn có thể làm lỗi dữ liệu/trạng thái. |
| `NoClassDefFoundError` luôn là mất file JAR | Có thể do class initialization đã thất bại trước đó hoặc nguyên nhân linkage khác. |
| `ExceptionInInitializerError` xuất hiện sau mọi lỗi constructor instance | Nó gắn với **static/class initialization**, không phải mọi constructor exception. |
| Static initializer ném `AssertionError` thì JVM luôn bọc `ExceptionInInitializerError` | Nếu đối tượng gốc đã là `Error`, nó thường được truyền trực tiếp. |
| Sau khi bắt `ExceptionInInitializerError` có thể thử lại class y hệt và thành công | Class có thể ở trạng thái erroneous; lượt sau thường là `NoClassDefFoundError`. |
| `finally` chắc chắn chạy kể cả JVM bị kill/halt | Không có bảo đảm trong trường hợp process dừng cưỡng bức hoặc không thể tiếp tục. |
| `try-with-resources` không chạy `close()` khi body ném Error | Theo ngữ nghĩa Java bình thường, resource đã mở vẫn được đóng. |
| Mọi `AssertionError` đều do từ khóa `assert` | Code có thể chủ động ném `new AssertionError` dù assertions bị tắt. |
| Từ khóa `assert` phù hợp để xác thực input bắt buộc | Sai vì assertion có thể bị tắt. |
| Ghi log `ex.getMessage()` là đủ | Có thể mất stack trace, cause và suppressed exceptions. |

## 23. Checklist điều tra một `Error` trong ứng dụng Java

1. **Nhận diện đúng class**: `OutOfMemoryError`, `StackOverflowError`, `LinkageError`, `AssertionError`, v.v.
2. **Ghi lại thông điệp và stack trace** nếu môi trường còn đủ khả năng; không parse message JVM thành hợp đồng ổn định.
3. **Tìm cause**: đặc biệt `ExceptionInInitializerError.getCause()` và các wrapper async/framework.
4. **Kiểm tra suppressed** nếu xảy ra lỗi trong `try-with-resources` hoặc cleanup.
5. **Xác định thời điểm**: lúc nạp/liên kết class, khởi tạo static, tạo object, xử lý request, đóng tài nguyên hay chạy background worker?
6. Với `LinkageError`, **đối chiếu classpath/module path, JDK runtime, JAR dependencies, version build và deploy**.
7. Với `StackOverflowError`, kiểm tra **đệ quy, điều kiện dừng, chu trình dữ liệu** trước khi tăng stack size.
8. Với `OutOfMemoryError`, kiểm tra **heap/native memory, số lượng object, leak, cache, request size và tài nguyên của container** bằng dữ liệu giám sát phù hợp.
9. Với lỗi static initialization, xem **lần thất bại đầu tiên** trước khi lớp chuyển sang trạng thái erroneous.
10. **Kiểm tra tính nhất quán của dữ liệu/tác vụ** trước bất kỳ quyết định retry nào.
11. **Phân biệt tiếp tục một luồng với hệ thống thật sự khỏe mạnh**; việc một thread sống không đủ chứng minh recovery.
12. Xây dựng **giới hạn bộ nhớ/tài nguyên, health check, restart và giám sát ngoài tiến trình** trước sự cố, thay vì kỳ vọng code trong `catch (OutOfMemoryError)` cứu mọi tình huống.

Không chủ động làm cạn heap hoặc chạy đệ quy vô hạn trên môi trường chung để “kiểm thử xử lý Error”. Hãy dùng unit test mô phỏng `AssertionError` và các công cụ chẩn đoán được thiết kế cho môi trường thử nghiệm cô lập nếu thật sự cần kiểm thử khả năng chịu lỗi.

## 24. Câu hỏi tự kiểm tra

**Câu 1.** `Error` có thuộc `Exception` không?

**Đáp án:** Không. Cả hai là nhánh của `Throwable`.

**Câu 2.** `catch (Exception)` có bắt `OutOfMemoryError` không?

**Đáp án:** Không.

**Câu 3.** `Error` là checked hay unchecked?

**Đáp án:** Unchecked; Java không buộc `throws Error`.

**Câu 4.** `OutOfMemoryError` có chắc chắn khiến toàn bộ JVM dừng ngay không?

**Đáp án:** Không thể kết luận như vậy từ riêng kiểu lỗi. Nhưng đây vẫn là tình trạng nghiêm trọng, không nên mặc định ứng dụng còn an toàn để tiếp tục.

**Câu 5.** Static initializer ném `IllegalStateException` có thể xuất hiện với lỗi ngoài cùng nào?

**Đáp án:** `ExceptionInInitializerError`, với `getCause()` giữ lỗi gốc trong trường hợp thông thường.

**Câu 6.** Vì sao lượt dùng lớp kế tiếp sau một lần khởi tạo thất bại có thể là `NoClassDefFoundError`?

**Đáp án:** JVM đánh dấu class đang ở trạng thái khởi tạo lỗi (erroneous) và không chạy lại initializer trong cùng ngữ cảnh đó.

**Câu 7.** Nếu static initializer ném trực tiếp `AssertionError`, có nhất thiết bị bọc thành `ExceptionInInitializerError` không?

**Đáp án:** Không. `Error` gốc thường được truyền ra trực tiếp ở lượt đầu.

**Câu 8.** Có thể dùng từ khóa `assert` để kiểm tra số tiền phải dương cho mọi request không?

**Đáp án:** Không. Assertions có thể bị tắt; phải dùng validation hoạt động độc lập với cờ `-ea`.

**Câu 9.** Khi `try-with-resources` có `AssertionError` từ body và `IOException` từ `close()`, lỗi nào là chính?

**Đáp án:** Thường `AssertionError` từ body là lỗi chính, còn `IOException` đóng tài nguyên được gắn dưới dạng suppressed.

**Câu 10.** Tại sao `main` trong ví dụ cleanup vẫn ghi `throws IOException`?

**Đáp án:** Vì compiler phải kiểm tra checked exception mà `close()` có thể ném từ lời gọi cleanup ngầm, dù đường runtime cố định trong ví dụ có `AssertionError` làm lỗi chính.

**Câu 11.** Worker thread ném `AssertionError` không bắt thì main thread nhất thiết dừng theo không?

**Đáp án:** Không. Worker có thể kết thúc, uncaught handler được gọi, còn main tiếp tục. Nhưng tính an toàn để chạy tiếp vẫn cần được đánh giá.

**Câu 12.** Vì sao `catch (Throwable)` quanh mọi nghiệp vụ là một anti-pattern?

**Đáp án:** Vì nó gom cả lỗi recoverable và lỗi nghiêm trọng mà tiến trình có thể không còn trạng thái đáng tin; dễ nuốt lỗi và tiếp tục sai.

## 25. Tài liệu tham khảo chính thức

- [Java SE 17 API — `Error`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Error.html): ý nghĩa của Error, phân cấp và trạng thái unchecked.
- [Java SE 17 API — `VirtualMachineError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/VirtualMachineError.html), [`OutOfMemoryError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/OutOfMemoryError.html), [`StackOverflowError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StackOverflowError.html): những sự cố tài nguyên/VM.
- [Java SE 17 API — `LinkageError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/LinkageError.html), [`NoClassDefFoundError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html): lỗi liên kết và nạp lớp.
- [Java SE 17 API — `ExceptionInInitializerError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ExceptionInInitializerError.html): lỗi phát sinh khi khởi tạo static.
- [Java SE 17 API — `AssertionError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AssertionError.html): lỗi kiểm tra assertion.
- [Java Language Specification 17 — §11.2](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): ngoại lệ checked và unchecked.
- [Java Language Specification 17 — §12.4.2](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2): thủ tục khởi tạo class, `ExceptionInInitializerError` và trạng thái erroneous.
- [Java Language Specification 17 — §14.10](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.10): câu lệnh `assert`.
- [Java Language Specification 17 — §14.20](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): `try`, `catch`, `finally` và `try-with-resources`.
- [Java SE 17 API — `Thread.UncaughtExceptionHandler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.UncaughtExceptionHandler.html): quan sát lỗi không được bắt trong một luồng.

**Ghi nhớ:** `Error` là nhánh **unchecked** của `Throwable` và thường báo điều kiện nghiêm trọng ngoài phạm vi phục hồi của mã nghiệp vụ thông thường. Một số `Error` đến từ JVM, quá trình liên kết/khởi tạo lớp hoặc kiểm tra assertion; chúng không nhất thiết làm toàn bộ JVM dừng ngay, nhưng **bắt được không đồng nghĩa sửa được lỗi**. Ưu tiên xử lý các `Exception` có hợp đồng rõ, dùng cleanup chuẩn, giữ cause/suppressed, và chỉ quan sát `Error` ở những ranh giới hẹp với chính sách an toàn; không nuốt `Error` để tiếp tục như thể hệ thống vẫn bình thường.
