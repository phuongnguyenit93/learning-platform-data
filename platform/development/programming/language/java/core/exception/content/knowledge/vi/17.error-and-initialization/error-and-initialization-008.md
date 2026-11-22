# NoClassDefFoundError trong lần sử dụng sau một lần khởi tạo thất bại

> **Java Core – Exception** · Nhóm: **Error và khởi tạo** · Java **17+**. Bài học tập trung vào một hiện tượng rất dễ chẩn đoán sai: lớp **đã được JVM tìm thấy**, nhưng khởi tạo tĩnh thất bại; ở lần sử dụng đầu tiên bạn có thể thấy `ExceptionInInitializerError` (hoặc một `Error` gốc), còn những lần sử dụng chủ động tiếp theo đối với **cùng lớp trong cùng cơ chế nạp lớp** lại nhận `NoClassDefFoundError`.

## 1. Hiện tượng thường gặp

Một chương trình đang chạy xuất hiện stack trace dạng:

~~~text
java.lang.ExceptionInInitializerError
    ...
Caused by: java.lang.IllegalStateException: invalid configuration
    ...
~~~

Sau đó, khi gọi lại chính class ấy:

~~~text
java.lang.NoClassDefFoundError: Could not initialize class com.example.Settings
    ...
~~~

Người đọc có thể lập tức nghĩ “file `Settings.class` đã biến mất khỏi classpath”. **Đó không phải kết luận đúng trong mọi trường hợp.** Một nguyên nhân khác rất quan trọng là: JVM đã tìm được class, nhưng **class initialization trước đó hoàn thành bất thường**; JVM đánh dấu class ấy ở trạng thái lỗi (*erroneous state*).

Khi mã tiếp tục thực hiện một thao tác cần class đã được khởi tạo, JVM **không chạy lại static initializer như thể chưa có gì xảy ra**. Với trạng thái erroneous, một lần sử dụng sau có thể dẫn tới `NoClassDefFoundError`, cho biết class này **không thể được khởi tạo thành công** trong bối cảnh đó.

### Ba khái niệm phải tách riêng

1. **Class loading (nạp lớp):** tìm và tạo biểu diễn runtime của class từ class file/nguồn do class loader cung cấp.
2. **Linking (liên kết):** verification, preparation và resolution theo quy tắc JVM.
3. **Initialization (khởi tạo):** chạy các phần khởi tạo biến tĩnh và khối `static { ... }` của class, sau khi đáp ứng những điều kiện liên quan tới superclass.

`NoClassDefFoundError` có thể phát sinh từ nhiều loại thất bại ở giai đoạn liên quan tới class. **Một trường hợp đặc biệt** của bài này là class **đã load/link đủ để đi vào initialization**, initialization hỏng, và các lần active use về sau thất bại.

**Ý chính:** Đừng chỉ nhìn exception ở cuối chuỗi. Hãy tìm **lỗi đầu tiên xảy ra trong quá trình initialization**.

## 2. Phân cấp exception/error liên quan

~~~text
java.lang.Throwable
├── java.lang.Error
│   └── java.lang.LinkageError
│       ├── java.lang.ExceptionInInitializerError
│       └── java.lang.NoClassDefFoundError
└── java.lang.Exception
    └── java.lang.RuntimeException
        └── java.lang.IllegalStateException
~~~

Cần phân biệt:

| Kiểu | Nhóm | Vai trò trong tình huống này |
| --- | --- | --- |
| `IllegalStateException` | Unchecked `RuntimeException` | Lỗi gốc minh họa, được ném khi static initialization không hợp lệ |
| `ExceptionInInitializerError` | Unchecked `Error`, thuộc nhánh `LinkageError` | Có thể được JVM dùng để bọc exception **không thuộc Error** khiến class initialization thất bại |
| `NoClassDefFoundError` | Unchecked `Error`, thuộc nhánh `LinkageError` | Có thể báo việc class không thể sẵn sàng cho lần sử dụng sau do trạng thái khởi tạo lỗi; cũng có nguyên nhân khác như thiếu định nghĩa class |
| `ClassNotFoundException` | **Checked** `Exception` | API nạp lớp theo tên, ví dụ `Class.forName`, không tìm được định nghĩa class được yêu cầu |

`ExceptionInInitializerError` **không phải** subclass của `RuntimeException`. Nếu chỉ dùng `catch (RuntimeException)`, bạn **không bắt được** Error này. Tương tự, `catch (Exception)` không bắt các nhánh Error nói trên.

**Đừng biến bảng thành lời khuyên bắt mọi Error.** Trong ứng dụng thông thường, lỗi initialization là vấn đề nghiêm trọng về khả năng hoạt động của class; cách khắc phục thường là sửa cấu hình hoặc code, không phải nuốt Error rồi tiếp tục.

## 3. Vì sao lần đầu và lần sau lại ném hai loại khác nhau?

Xét:

~~~java
class BrokenSettings {
    static final String NAME = "app";
    static int VALUE = initialize();

    private static int initialize() {
        throw new IllegalStateException("configuration missing");
    }
}
~~~

Đây là khai báo Java hợp lệ để minh họa, nhưng bản thân chưa có `main`. Khi có một **active use** yêu cầu khởi tạo `BrokenSettings`, JVM thực hiện code khởi tạo static field `VALUE` bằng cách gọi `initialize()`.

Quy trình khái quát:

1. Một thread đầu tiên thực hiện thao tác yêu cầu class được khởi tạo.
2. JVM kiểm tra trạng thái initialization của class và các ràng buộc phụ thuộc.
3. JVM bắt đầu thực thi initializer tĩnh (và phần khởi tạo superclass phù hợp nếu cần).
4. `initialize()` ném `IllegalStateException`.
5. Vì Throwable gốc **không thuộc `Error`**, thuật toán khởi tạo của JVM cố tạo `ExceptionInInitializerError` với nguyên nhân đó (theo JLS 12.4.2).
6. Class bị đánh dấu là **erroneous** và lần sử dụng đang gây initialization kết thúc bất thường.
7. Một lần active use sau của class erroneous gặp `NoClassDefFoundError` thay vì chạy lại initializer.
8. Các lời gọi khác trong bối cảnh nạp lớp tương tự tiếp tục gặp vấn đề cho tới khi thay đổi bối cảnh class loading/chạy lại ứng dụng bằng giải pháp phù hợp; chỉ gọi lại method không làm trạng thái erroneous trở thành bình thường.

**Quan trọng:** Quy tắc dùng `ExceptionInInitializerError` ở bước 5 không áp dụng giống vậy nếu Throwable do initialization ném ra vốn là một subclass của `Error`. Trường hợp đó, `Error` có thể được truyền trực tiếp trong lần đầu, nhưng class vẫn bị đánh dấu erroneous nếu initialization thất bại.

### 3.1. Sơ đồ trạng thái

~~~text
Lớp chưa khởi tạo
      |
      | first active use
      v
Đang khởi tạo (initialization in progress)
      |
      +-- thành công --> Đã khởi tạo --> các lần active use tiếp tục bình thường
      |
      +-- ném Throwable
              |
              +-- không thuộc Error --> JVM bọc bằng ExceptionInInitializerError
              |
              +-- là Error ----------> có thể truyền Error gốc
              |
              v
       Lớp erroneous
              |
              | active use sau
              v
       NoClassDefFoundError
~~~

Đây là **mô hình rút gọn** tập trung vào thất bại initializer; thuật toán JVM thực tế còn xử lý khóa đồng bộ, recursive initialization, superclass/superinterface, trình tự báo lỗi và nhiều chi tiết khác.

### 3.2. Vì sao JVM không thử khởi tạo lại class ngay?

Class initialization thiết lập trạng thái dùng chung và có thể tạo **side effect**: đăng ký service, tạo singleton, kết nối tài nguyên, ghi log, mutate cấu trúc dữ liệu hoặc nạp native library. Nếu initializer chạy một phần rồi lỗi, JVM không có cơ chế tổng quát bảo đảm rollback mọi side effect ấy.

Việc nhớ rằng initialization đã thất bại giúp tránh giả định “gọi lại lần nữa là class tự hồi phục”. Theo [JLS §12.4.2](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2), một class được đánh dấu erroneous khi initialization không thành công và các yêu cầu khởi tạo tiếp theo không được thực hiện như một lần khởi tạo mới bình thường.

Đây là lý do **không nên đặt các tác vụ môi trường dễ lỗi, có khả năng cần retry, vào static initializer** nếu ứng dụng kỳ vọng khôi phục lúc runtime.

## 4. Chương trình Java 17 hoàn chỉnh: quan sát lần đầu và lần sau

Lưu tệp **`FailedInitializationDemo.java`**, giữ nguyên tên public class.

~~~java
public class FailedInitializationDemo {
    static class Broken {
        static final String LABEL = "constant";
        static int VALUE = initialize();

        private static int initialize() {
            System.out.println("broken-initializer");
            throw new IllegalStateException("invalid configuration");
        }

        static void ping() {
            System.out.println("broken-ping");
        }
    }

    static class BrokenByError {
        static int VALUE = initialize();

        private static int initialize() {
            System.out.println("error-initializer");
            throw new AssertionError("broken invariant");
        }
    }

    static class Healthy {
        static int VALUE = initialize();

        private static int initialize() {
            System.out.println("healthy-initializer");
            return 7;
        }
    }

    private static void attempt(String label, Runnable work) {
        System.out.println("== " + label + " ==");
        try {
            work.run();
        } catch (ExceptionInInitializerError ex) {
            System.out.println("type=ExceptionInInitializerError");
            Throwable cause = ex.getCause();
            System.out.println("cause=" + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage());
        } catch (NoClassDefFoundError ex) {
            System.out.println("type=NoClassDefFoundError");
        } catch (AssertionError ex) {
            System.out.println("type=AssertionError: " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        System.out.println("== non-initializing references ==");
        System.out.println("constant=" + Broken.LABEL);
        System.out.println("class-literal=" + Broken.class.getSimpleName());

        attempt("first broken use",
                () -> System.out.println("value=" + Broken.VALUE));
        attempt("second broken use", () -> Broken.ping());
        attempt("reflective broken use", () -> {
            try {
                Class.forName("FailedInitializationDemo$Broken", true,
                        FailedInitializationDemo.class.getClassLoader());
            } catch (ClassNotFoundException ex) {
                throw new AssertionError(ex);
            }
        });

        attempt("first Error use",
                () -> System.out.println("value=" + BrokenByError.VALUE));
        attempt("second Error use",
                () -> System.out.println("value=" + BrokenByError.VALUE));

        attempt("healthy first use",
                () -> System.out.println("value=" + Healthy.VALUE));
        attempt("healthy second use",
                () -> System.out.println("value=" + Healthy.VALUE));
    }
}
~~~

### 4.1. Cách biên dịch và chạy

Sử dụng JDK 17 hoặc phiên bản mới hơn:

~~~bash
javac --release 17 -encoding UTF-8 FailedInitializationDemo.java
java FailedInitializationDemo
~~~

**Stdout chính xác được kiểm chứng bằng cách biên dịch `javac --release 17` và chạy chương trình:**

~~~text
== non-initializing references ==
constant=constant
class-literal=Broken
== first broken use ==
broken-initializer
type=ExceptionInInitializerError
cause=IllegalStateException: invalid configuration
== second broken use ==
type=NoClassDefFoundError
== reflective broken use ==
type=NoClassDefFoundError
== first Error use ==
error-initializer
type=AssertionError: broken invariant
== second Error use ==
type=NoClassDefFoundError
== healthy first use ==
healthy-initializer
value=7
== healthy second use ==
value=7
~~~

Chương trình chỉ sử dụng Java SE và cố ý không in message mặc định của `NoClassDefFoundError`, vì thông điệp do JVM cung cấp có thể khác giữa các phiên bản và implementation. Các nhánh đã được bắt **chỉ trong chương trình dạy học** để có thể trình diễn tiếp những trường hợp còn lại.

### 4.2. Vì sao hai dòng đầu chưa chạy initializer của Broken?

~~~java
System.out.println("constant=" + Broken.LABEL);
System.out.println("class-literal=" + Broken.class.getSimpleName());
~~~

`Broken.LABEL` là một **compile-time constant**: `static final String` có initializer là biểu thức hằng `"constant"`. Việc dùng giá trị hằng này từ source có thể được compiler inline và **không kích hoạt initialization của lớp Broken**.

`Broken.class` lấy đối tượng `Class<?>` đại diện class; riêng việc lấy class literal và gọi `getSimpleName()` trong ví dụ này **không kích hoạt static initializer của Broken**.

Vì thế stdout chưa có `broken-initializer` ở hai dòng đầu. Nó chỉ xuất hiện khi đọc field `Broken.VALUE` — một static field không phải constant variable theo JLS.

### 4.3. Lần đầu: IllegalStateException trở thành ExceptionInInitializerError

Lời gọi:

~~~java
System.out.println("value=" + Broken.VALUE);
~~~

yêu cầu khởi tạo Broken. Static field `VALUE` gọi `initialize()`, in `broken-initializer` rồi ném `IllegalStateException("invalid configuration")`.

Vì exception gốc là RuntimeException (không phải Error), quá trình khởi tạo theo JLS tạo `ExceptionInInitializerError`. Handler ở ví dụ đọc `getCause()` và thấy:

~~~text
type=ExceptionInInitializerError
cause=IllegalStateException: invalid configuration
~~~

**Tập trung vào nguyên nhân gốc:** Sửa cấu hình hoặc logic khiến initializer ném `IllegalStateException`. Nếu chỉ tìm class file vì thấy `NoClassDefFoundError` ở log đến sau, rất dễ đi sai hướng.

### 4.4. Lần hai: NoClassDefFoundError thay vì chạy lại initializer

Sau lần đầu, Broken đã ở trạng thái erroneous. Lời gọi:

~~~java
Broken.ping();
~~~

là một active use của class. Kết quả:

~~~text
== second broken use ==
type=NoClassDefFoundError
~~~

Dòng `broken-ping` **không xuất hiện**, vì method body không được thực thi. JVM phải đảm bảo class được initialized trước khi xử lý invocation này; quá trình kiểm tra gặp class đã erroneous.

Lưu ý: nếu bạn xem stack trace của NoClassDefFoundError, thông tin còn lại có thể trỏ đến lỗi initialization trước đó. **Không dựa vào chính xác cấu trúc cause/message của NCDFE trên mọi JVM**; log đầu tiên và cause của EIIE gốc vẫn là bằng chứng chẩn đoán quan trọng nhất.

### 4.5. Class.forName(..., true, loader) cũng không “thử lại” initializer

Phần phản chiếu:

~~~java
Class.forName("FailedInitializationDemo$Broken", true,
        FailedInitializationDemo.class.getClassLoader());
~~~

truyền `initialize = true`, yêu cầu initialization khi cần. Vì Broken đã erroneous nên lỗi là:

~~~text
== reflective broken use ==
type=NoClassDefFoundError
~~~

Lệnh `Class.forName` không reset trạng thái. Một lần gọi lại thông qua reflection không phải đường đi khác để khôi phục class đã hỏng.

### 4.6. Nếu initializer ném Error gốc thì sao?

Class `BrokenByError` ném `AssertionError("broken invariant")` từ initializer. Nó là subclass của Error. Theo thuật toán initialization, trong tình huống này Error có thể **được truyền trực tiếp** khi class thất bại lần đầu:

~~~text
== first Error use ==
error-initializer
type=AssertionError: broken invariant
~~~

Lần hai:

~~~text
== second Error use ==
type=NoClassDefFoundError
~~~

Vì vậy câu “lần đầu **luôn** là ExceptionInInitializerError” là **sai**. Quy tắc chính xác hơn: khi initialization kết thúc bất thường, Throwable **không thuộc Error** được JVM bọc bằng ExceptionInInitializerError theo JLS; nếu vốn là Error, lỗi có thể đi ra trực tiếp.

### 4.7. Khởi tạo thành công chỉ chạy một lần

Class Healthy có field `VALUE = initialize()`; method in `healthy-initializer` rồi trả số 7.

Truy cập lần đầu:

~~~text
== healthy first use ==
healthy-initializer
value=7
~~~

Truy cập lần sau:

~~~text
== healthy second use ==
value=7
~~~

Đây là trường hợp bình thường: initializer hoàn tất thành công, class ở trạng thái initialized và không cần chạy lại ở mỗi active use.

## 5. Những thao tác nào kích hoạt khởi tạo class?

Theo [JLS §12.4.1](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1), initialization được yêu cầu trước một số thao tác **active use**. Với class thông thường, cần chú ý:

- Tạo instance bằng `new SomeClass()`.
- Gọi một **static method** thực sự được khai báo bởi class.
- Gán giá trị vào **static field** được khai báo bởi class.
- Đọc **static field không phải constant variable** được khai báo bởi class.
- Một số thao tác reflection có yêu cầu initialization, trong đó có `Class.forName(name)` và `Class.forName(name, true, loader)` khi tìm class phù hợp.
- Khởi tạo một class con có thể yêu cầu khởi tạo superclass và một số superinterface theo quy tắc ngôn ngữ trước khi chạy initializer của class con.

Ngược lại, nhiều thao tác tham chiếu class **không tự kích hoạt initialization**:

| Biểu thức/tác vụ | Có buộc init class ví dụ không? | Lý do |
| --- | --- | --- |
| `Broken.class` | Không chỉ vì class literal | Nhận metadata Class |
| `Broken.LABEL` với compile-time constant | Không chỉ vì đọc hằng | Constant variable có thể inline |
| `Broken.VALUE` | Có | Đọc static field không phải compile-time constant |
| `Broken.ping()` | Có | Invokestatic active use |
| `new Broken()` | Có | Tạo instance yêu cầu class initialized |
| `Class.forName("...Broken", false, loader)` | Không yêu cầu khởi tạo do flag false | Chỉ nạp/liên kết theo API; các hoạt động khác không được tùy tiện suy diễn |
| `Class.forName("...Broken", true, loader)` | Có yêu cầu init khi cần | Flag true yêu cầu initialization |
| `obj instanceof Broken` | Không được xem là trigger init chỉ vì kiểm tra kiểu | Kiểm tra runtime type không nhất thiết chạy static initializer |

Bảng dựa trên trường hợp đơn giản và quy tắc ngôn ngữ. Những thao tác có thể gây **loading/linking** không đồng nghĩa chắc chắn **initialization**. Ngoài ra, trong một chương trình thực tế, class có thể đã được khởi tạo trước đó bởi một thao tác khác.

### 5.1. Constant variable không giống mọi static final field

~~~java
class Constants {
    static final int LIMIT = 10;
    static final String NAME = "demo";
    static final Integer BOXED = 10;
    static final int COMPUTED = Integer.parseInt("10");
}
~~~

Đây là class Java minh họa hợp lệ. Hai field đầu là constant variables theo điều kiện JLS: primitive hoặc String `final` được khởi tạo bằng constant expression.

`BOXED` không phải constant variable vì kiểu `Integer` là reference wrapper; `COMPUTED` dùng lời gọi method, không phải constant expression. Việc đọc `Constants.BOXED` hoặc `Constants.COMPUTED` có thể kích hoạt initialization nếu class chưa được khởi tạo.

Khi xử lý lỗi “tại sao truy cập field A không chạy static block nhưng field B có?”, đây là khác biệt quan trọng hơn việc cả hai cùng có từ khóa `static final`.

## 6. Những nguyên nhân thực tế khiến static initialization thất bại

Không chỉ có `throw new IllegalStateException(...)` trong một method tự viết. Lỗi có thể bắt đầu từ nhiều nơi:

1. **Static field initializer** chạy code đọc cấu hình không hợp lệ.
2. **Khối `static { ... }`** gọi một method rồi method ném unchecked exception.
3. **Dependency tĩnh** hoặc superclass cần khởi tạo trước bị lỗi.
4. **Nạp driver/native library** qua code static không thành công.
5. **Singleton static** dùng giá trị môi trường không tồn tại rồi dereference null.
6. **Cấu trúc dữ liệu tĩnh** được tạo với tham số không hợp lệ.
7. **Code initialization có side effect** đã chạy một phần trước khi ném Error/RuntimeException.
8. **Lỗi runtime khó phục hồi**, ví dụ một Error liên quan resource, có thể phát sinh trong quá trình initialization.

Ví dụ:

~~~java
class Config {
    static final int PORT = Integer.parseInt(
            System.getProperty("demo.port"));
}
~~~

Đây là class minh họa. Nếu property không được cung cấp, `System.getProperty("demo.port")` trả null; `Integer.parseInt(null)` ném `NumberFormatException` (subclass của IllegalArgumentException) trong quá trình khởi tạo tĩnh. Khi active use yêu cầu initialization lần đầu, JVM có thể báo `ExceptionInInitializerError`; lần sau class erroneous có thể cho `NoClassDefFoundError`.

Điểm quan trọng không phải luôn là NumberFormatException — tùy đoạn code gốc có thể là NPE, IllegalArgumentException hoặc một Error khác. Hãy đọc **cause gốc** chứ không đoán nguyên nhân từ riêng NCDFE.

## 7. Static initialization chạy theo thứ tự nào?

Đối với một class, các **static field initializers** và **static initializer blocks** được thực hiện theo **thứ tự văn bản** trong lúc khởi tạo, với các quy tắc JVM bổ sung về superclass/superinterfaces.

Ví dụ:

~~~java
class Order {
    static int a = first();

    static {
        System.out.println("static-block");
    }

    static int b = second();

    private static int first() {
        System.out.println("first");
        return 1;
    }

    private static int second() {
        System.out.println("second");
        return 2;
    }
}
~~~

Đây là một class minh họa hợp lệ. Nếu một active use khiến `Order` được khởi tạo thành công, phần code trong class in:

~~~text
first
static-block
second
~~~

Nếu `first()` ném exception, các bước phía sau **không được chạy** trong lần khởi tạo đó. Không có một cơ chế chung tự động hoàn tác những side effect mà `first()` có thể đã thực hiện trước khi ném lỗi.

Một hệ quả cần lưu ý: nếu static initializer đã ghi file hoặc đăng ký listener rồi ném exception, trạng thái ngoài JVM class có thể đã thay đổi. Việc “thử init lại” bằng cách thay đổi logic gọi không giải quyết nhất quán những side effect đó.

## 8. Không nhầm với ClassNotFoundException hoặc class file thực sự thiếu

Cả ba trường hợp có thể liên quan tới tên class, nhưng **khác nguyên nhân và đường phát sinh**.

### 8.1. ClassNotFoundException

Ví dụ:

~~~java
try {
    Class.forName("example.DoesNotExist");
} catch (ClassNotFoundException ex) {
    System.out.println("Class not found by lookup");
}
~~~

Đây là đoạn minh họa đặt trong method phù hợp. `Class.forName(String)` có thể ném checked `ClassNotFoundException` khi class loader **không tìm được định nghĩa có tên được yêu cầu**.

### 8.2. NoClassDefFoundError do thiếu định nghĩa trong lúc linking/loading

Một class được biên dịch có thể tham chiếu tới một class khác có mặt khi build nhưng **không còn có mặt ở runtime classpath/module path**. Khi JVM cần giải quyết tham chiếu này, nó có thể ném `NoClassDefFoundError`.

Đây là nhánh nguyên nhân **khác** với “class đã được tìm thấy nhưng initialization trước đó hỏng”.

### 8.3. NoClassDefFoundError do class erroneous

Trong bài này, `Broken.class` đã tồn tại, runtime nạp được class, initializer còn **in `broken-initializer`** trong lần đầu. Do đó không thể giải thích lần NoClassDefFoundError thứ hai đơn giản là “thiếu bytecode class”.

### 8.4. Bảng phân biệt nhanh

| Dấu hiệu | Nhóm nguyên nhân nên kiểm tra |
| --- | --- |
| `ClassNotFoundException` khi Class.forName theo tên | Class loader không tìm thấy định nghĩa được yêu cầu |
| `NoClassDefFoundError` kèm thông tin định nghĩa class thiếu | Classpath/module/dependency, tên class và lỗi linkage |
| `ExceptionInInitializerError` xuất hiện trước đó | Static initialization đã thất bại do Throwable không thuộc Error |
| `AssertionError`/Error từ initializer xuất hiện lần đầu | Static initialization cũng có thể lỗi mà **không qua EIIE** |
| `NoClassDefFoundError: Could not initialize class ...` trong lần gọi sau | Nghi class đã bị đánh dấu erroneous; tìm log lần lỗi đầu |
| Lỗi biến mất khi chạy trong class loader mới / process mới | Có thể phù hợp với trạng thái initialization gắn với identity của class ở loader cũ; vẫn phải sửa lỗi gốc |

**Không dựa tuyệt đối vào chuỗi `Could not initialize class`.** Message của LinkageError không được dùng như một format có thể parse ổn định giữa mọi JVM. Hãy xem stack trace, exception đầu tiên, runtime classpath và toàn bộ cause chain.

## 9. Class loader và định danh thực của một class

Trong JVM, khái niệm “cùng class” gắn với **tên nhị phân và defining class loader**. Hai loader khác nhau có thể định nghĩa hai lớp có tên giống nhau nhưng với identity khác nhau, nếu cơ chế loading/ủy quyền cho phép.

Điều đó giải thích vì sao:

- Một class đã erroneous trong **một class loader** không được làm như thể có thể reset bằng cách gọi `new` hoặc `Class.forName(..., true, sameLoader)`.
- Một class khác cùng tên được load/định nghĩa trong **một loader khác** có thể có trạng thái initialization riêng, nếu thực sự được định nghĩa mới ở loader đó.
- Tạo class loader mới **không bảo đảm** sẽ có định nghĩa mới nếu loader vẫn delegate cho loader cha vốn sở hữu class cũ.
- Trong ứng dụng thông thường, cách thực tế để khôi phục thường là **sửa nguyên nhân** rồi **khởi động lại ứng dụng/process hoặc thực hiện cơ chế reload đúng nghĩa** của nền tảng.

Không nên biến “đổi class loader để chạy lại initializer” thành mẹo chữa lỗi mặc định. Cơ chế plugin reload, app server redeploy hay hot-reload có thể liên quan thêm đến rò rỉ class loader, tham chiếu static và cấu trúc dependency.

## 10. Điều gì xảy ra khi nhiều thread cùng chạm vào một class?

Class initialization được JVM điều phối với cơ chế đồng bộ để không có hai thread độc lập đồng thời chạy toàn bộ initializer của **cùng class identity**.

Tình huống:

1. Thread A bắt đầu khởi tạo class.
2. Thread B cũng cần active use của class trong lúc A đang init.
3. B có thể phải đợi quá trình khởi tạo do A thực hiện.
4. Nếu A khởi tạo thành công, B có thể tiếp tục với class đã initialized.
5. Nếu A khởi tạo thất bại, class bị đánh dấu erroneous; B và các lần active use về sau có thể nhận `NoClassDefFoundError` theo thuật toán trạng thái.

Điều này lý giải một pattern trong log hệ thống đa luồng: **chỉ một thread thấy Error initialization gốc**, còn các thread khác sau đó thấy NoClassDefFoundError, khiến vấn đề trông như mất class đột ngột.

**Không viết code phụ thuộc thứ tự thread nào sẽ thấy EIIE hay NCDFE** trong một cuộc đua initialization. Đây là chi tiết scheduling; khi điều tra, cần tổng hợp log theo mốc thời gian và đối tượng class.

### Recursive initialization

Nếu một thread trong quá trình khởi tạo class lại tham chiếu tới chính class ấy theo cách Java cho phép, JVM có quy tắc riêng cho **recursive initialization bởi cùng thread**; không đơn giản chạy initializer vô hạn. Tuy nhiên, static field có thể còn ở trạng thái mặc định hoặc chưa được gán xong, tạo bug “partial initialization” khó nhận ra.

Ví dụ này nằm ngoài đường chính của bài, nhưng củng cố nguyên tắc **tránh thiết kế các static initializer phức tạp có phụ thuộc vòng**.

## 11. Superclass và phụ thuộc static hỏng có thể lan ra sao?

Khi JVM khởi tạo một class, nó cần bảo đảm superclass tương ứng được khởi tạo theo quy tắc. Nếu một superclass có static initializer thất bại, quá trình khởi tạo subclass cũng không thể tiếp tục bình thường.

Ví dụ minh họa:

~~~java
class Parent {
    static int value = load();

    static int load() {
        throw new IllegalStateException("parent init failed");
    }
}

class Child extends Parent {
    static int other = 10;
}
~~~

Đây là hai class Java hợp lệ nhưng không có main. Khi lần đầu active use đòi khởi tạo Child, JVM phải khởi tạo Parent trước. Nếu Parent ném lỗi, Child cũng không thể đi vào trạng thái initialized bình thường theo đường này.

**Cần kiểm tra đúng class gốc trong stack trace:** Một NoClassDefFoundError xuất hiện ở điểm gọi Child có thể bắt nguồn từ Parent hoặc một dependency tĩnh khác. Đừng sửa Child chỉ vì đó là tên class ở dòng business gọi cuối cùng.

### Tương tự với static holder/singleton

Pattern:

~~~java
class ServiceHolder {
    static final Service INSTANCE = new Service(readConfig());
}
~~~

Đây là đoạn minh họa, cần class Service và method readConfig phù hợp. Nếu constructor Service hoặc readConfig thất bại không được xử lý hợp lệ, initialization của ServiceHolder cũng thất bại. Mọi caller sử dụng `ServiceHolder.INSTANCE` về sau có thể thấy NCDFE ngay cả khi code caller không biết đến readConfig.

Một singleton holder cho **lazy initialization** vẫn dùng class initialization; “lazy” chỉ nói thời điểm khởi tạo, không có nghĩa tự hỗ trợ retry khi khởi tạo hỏng.

## 12. Kiểm tra lỗi gốc trước khi kết luận thiếu dependency

Checklist điều tra khi gặp NoClassDefFoundError:

1. **Xem exception đầy đủ**, không chỉ dòng đầu: message, stack trace, cause chain.
2. **Tìm trong log mốc thời gian trước đó** các `ExceptionInInitializerError`, `AssertionError`, `Error` khác xảy ra khi class được active use lần đầu.
3. **Xác định class đang erroneous**: nó có khối static/field initializer không? Có superclass hoặc dependency tĩnh nào bị lỗi?
4. **Kiểm tra root cause**: IllegalStateException, NumberFormatException, NPE, initializer truy cập cấu hình, driver, native library hoặc dữ liệu đầu vào.
5. Nếu không có dấu hiệu initialization hỏng, **kiểm tra classpath/module path**, packaging, dependency versions, loader isolation.
6. **Ghi nhận class loader** nếu môi trường plugin/container phức tạp; hai class cùng tên ở loader khác nhau không đồng nghĩa cùng identity.
7. **Tái hiện từ process sạch** để bắt được lỗi **lần đầu**, vì một process chạy lâu có thể chỉ còn log NCDFE.
8. **Sửa nguyên nhân trong initializer**, không chỉ catch NCDFE ở caller.
9. Kiểm tra các side effect đã xảy ra **trước thời điểm khởi tạo hỏng**.
10. **Kiểm thử lại fresh start**, bao gồm trường hợp cấu hình thiếu và cấu hình hợp lệ.

Nếu log chỉ có:

~~~text
java.lang.NoClassDefFoundError: Could not initialize class app.Config
~~~

hãy tìm một stack trace **sớm hơn** thay vì khẳng định rằng jar chứa `app.Config` bị xóa. Ngược lại, nếu package/class thực sự không được deploy, chạy lại static initializer không giải quyết được vấn đề classpath.

## 13. Lưu trữ và trình bày lỗi để không mất root cause

Khi debug, exception object quan trọng hơn message ngắn. Ví dụ minh họa ở tầng chẩn đoán:

~~~java
try {
    useComponent();
} catch (ExceptionInInitializerError ex) {
    logger.error("Component initialization failed", ex);
    throw ex;
}
~~~

Đây là đoạn minh họa cần `useComponent()` và logger thích hợp. Nó giữ nguyên Error sau khi log, không tạo kết quả thành công giả. Ở môi trường không có logging framework, có thể dùng `ex.printStackTrace()` để chẩn đoán cục bộ.

Với `ExceptionInInitializerError`:

- `getCause()` thường cung cấp Throwable đã khiến initializer thất bại.
- `getException()` là API lịch sử của lớp này, được giữ vì tương thích; dùng cause chain chung khi có thể.
- Nếu một lập trình viên tự tạo EIIE hoặc dùng constructor không có cause, không được giả định `getCause()` luôn khác null.
- Stack trace có thể cho thấy lần khởi tạo đầu tiên, sau đó là nhiều NoClassDefFoundError. **Giữ log theo thời gian** để liên kết đúng sự kiện.

Với `NoClassDefFoundError`, đừng dựa vào việc `getCause()` chắc chắn chứa bản sao của Error đầu tiên: việc tạo message/cause chi tiết có thể phụ thuộc implementation. Lỗi đầu trong log là nguồn đáng tin cậy để điều tra.

## 14. Tránh đặt kết nối và cấu hình dễ lỗi trong static initializer

Một anti-pattern:

~~~java
class DatabaseGateway {
    static final Connection CONNECTION = connect();

    private static Connection connect() {
        // Nếu kết nối thất bại bằng unchecked exception,
        // class có thể rơi vào trạng thái erroneous.
        throw new IllegalStateException("database unavailable");
    }
}
~~~

Đây là mã minh họa, cần `Connection` từ java.sql hoặc một kiểu dữ liệu tương ứng. Mục đích chỉ ra rằng **tạo tài nguyên có thể thất bại bởi môi trường** trong static initialization làm lớp không có đường retry tự nhiên.

Ngoài ra, một database connection tĩnh chia sẻ lâu dài có thể vi phạm chính sách thread safety, vòng đời kết nối và pooling. Đây không phải lựa chọn mặc định tốt cho production.

### 14.1. Giải pháp: khởi tạo tường minh ở lifecycle phù hợp

Thay vì để static class initialization mang toàn bộ lỗi môi trường, đưa việc tạo tài nguyên vào một component có lifecycle rõ:

~~~java
import java.io.IOException;

final class ConfigurableService {
    private String config;

    void initialize(String path) throws IOException {
        this.config = readConfig(path);
    }

    private String readConfig(String path) throws IOException {
        if (path == null || path.isBlank()) {
            throw new IOException("configuration path missing");
        }
        return path;
    }

    String currentConfig() {
        if (config == null) {
            throw new IllegalStateException("service not initialized");
        }
        return config;
    }
}
~~~

Class trên là minh họa Java hợp lệ có thể đặt trong file phù hợp. Nó làm cho lỗi cấu hình xảy ra trong một **method có hợp đồng checked IOException**, không làm class bị erroneous chỉ vì một lần dùng.

Tất nhiên, service object vẫn cần thiết kế đồng bộ/lifecycle, không cho truy cập trước khi initialized, và xử lý trạng thái partial initialization. Nhưng nó cho phép ứng dụng **chủ động quyết định** có retry, sửa cấu hình, báo lỗi cho vận hành hay dừng khởi động.

### 14.2. Lazy initialization có kiểm soát

Nếu cần trì hoãn kết nối hoặc tải cấu hình cho tới lúc sử dụng:

- Có thể dùng method/factory với result hoặc checked exception rõ ràng.
- Cần định nghĩa policy cache thành công/thất bại, thời gian retry và concurrency.
- Tránh cache một thất bại vĩnh viễn nếu nghiệp vụ yêu cầu hồi phục; ngược lại, đừng retry vô hạn thao tác có thể gây side effect.
- Nếu vẫn dùng static holder, hãy nhớ **initializer failure vẫn làm holder class erroneous**.
- Dùng dependency injection/lifecycle hooks của framework nếu dự án có, nhưng kiểm tra cách framework báo và cache lỗi.

**Điểm then chốt:** chuyển lỗi môi trường dễ xảy ra ra khỏi class initialization khi cần một đường phục hồi hợp lệ; điều này giúp tránh vòng “lần đầu EIIE, về sau NCDFE”.

## 15. Có thể catch Error để phục hồi class đã lỗi không?

Một caller **có thể** viết:

~~~java
try {
    Broken.VALUE = 5;
} catch (ExceptionInInitializerError ex) {
    System.err.println("initialization failed");
}
~~~

Đây là minh họa cần class Broken có trường static phù hợp; trong ví dụ chính, không nên gán trường VALUE như một cách cố sửa class.

Việc catch Error ở caller **không reset trạng thái class**, không chạy lại static initialization và không chứng minh các side effect đã rollback. Những lần active use sau vẫn có thể gặp NCDFE.

**Vì sao không nên catch Error rộng?**

- Các Error như LinkageError, OutOfMemoryError hoặc lỗi khởi tạo có thể khiến ứng dụng không còn ở trạng thái vận hành đáng tin.
- Nuốt Error làm mất dấu lỗi gốc và khiến hệ thống tiếp tục ở trạng thái sai.
- Một số lỗi có nguyên nhân không thể khôi phục tại điểm gọi.

Có thể catch cụ thể ở **test/demo hoặc top-level diagnostic boundary** để ghi log và kết thúc/chuyển trạng thái, nhưng không dùng `catch (Error) { }` làm chính sách chạy tiếp mặc định.

## 16. Khi nào NoClassDefFoundError có thể xảy ra ngay lần đầu?

Cần tránh diễn giải quá mức một quy tắc của bài. `NoClassDefFoundError` không **chỉ** là “dấu hiệu lớp hỏng lần trước”. Nó còn là một LinkageError gắn với thất bại nạp/định nghĩa class, hoặc có thể xuất hiện khi một class cần được sử dụng nhưng đang ở trạng thái erroneous do một thread khác đã thử khởi tạo trước đó.

Ví dụ:

- Class A tham chiếu class B, nhưng định nghĩa B thiếu trong runtime environment → NCDFE có thể xuất hiện **ngay tại lần đầu** sử dụng đường mã đó.
- Thread A đang chạy initializer class X và thất bại; thread B là thread đầu tiên trong log riêng của nó được gọi X nhưng lúc đó X đã erroneous → thread B có thể thấy NCDFE mà không từng thấy EIIE.
- Một module/plugin đã init class trước khi request handler bắt đầu → request đầu tiên được ghi log có thể chỉ thấy NCDFE.

Vì vậy để xác định nguyên nhân phải xem **toàn bộ process/log và loader**, không chỉ thứ tự lỗi trong một thread.

## 17. Những hiểu nhầm thường gặp

1. **“NoClassDefFoundError luôn nghĩa là thiếu file .class.”** Sai; có thể class đã được tìm thấy nhưng initialization thất bại trước đó.
2. **“Nếu mã đã biên dịch thì static initialization chắc chắn thành công.”** Sai; khởi tạo có thể ném exception ở runtime.
3. **“Lần đầu hỏng static init luôn là NoClassDefFoundError.”** Sai; có thể là ExceptionInInitializerError hoặc Error gốc.
4. **“Lần đầu hỏng luôn là ExceptionInInitializerError.”** Sai; Error ném trực tiếp không buộc được bọc theo cùng quy tắc.
5. **“ExceptionInInitializerError là RuntimeException.”** Sai; nó là Error dưới nhánh LinkageError.
6. **“NoClassDefFoundError là checked exception.”** Sai; đó là Error unchecked.
7. **“Catch Exception sẽ bắt được EIIE/NCDFE.”** Sai vì các lớp này thuộc nhánh Error.
8. **“Chỉ cần gọi lại method static là initializer sẽ thử chạy lại.”** Sai trong cùng trạng thái erroneous.
9. **“Class.forName(..., true, sameLoader) là nút retry static initializer.”** Sai.
10. **“Truy cập static final nào cũng chắc chắn khởi tạo class.”** Sai với compile-time constant variables.
11. **“Lấy Broken.class luôn chạy static block.”** Sai; class literal tự nó không phải active use buộc init.
12. **“Class loading và initialization là cùng một hành động.”** Sai; các giai đoạn có quy tắc khác nhau.
13. **“Static initializer không thể có side effect trước khi thất bại.”** Sai; một phần code có thể đã chạy.
14. **“JVM tự rollback side effect khi initializer ném lỗi.”** Không có cơ chế rollback tổng quát như vậy.
15. **“Một class đã erroneous sẽ tự hoạt động trở lại khi cấu hình ngoài được sửa.”** Không chỉ nhờ sửa cấu hình; class cần bối cảnh nạp/chạy thích hợp mới có cơ hội init mới.
16. **“Class loader mới chắc chắn định nghĩa lại class.”** Không nếu vẫn delegate về loader đã định nghĩa class ấy.
17. **“Thread nào dùng class cũng nhìn thấy cùng loại Error đầu tiên.”** Sai; các thread khác có thể nhận NCDFE sau khi init thất bại.
18. **“Nếu static initializer ném AssertionError thì lần sau cũng AssertionError.”** Không; class erroneous làm active use sau có thể nhận NCDFE.
19. **“Message của NoClassDefFoundError luôn đủ để tìm root cause.”** Sai; thường cần log lần khởi tạo đầu tiên.
20. **“Cứ catch NCDFE, trả null và tiếp tục là an toàn.”** Sai; có thể che trạng thái không khởi tạo được của component.
21. **“Superclass init thất bại không ảnh hưởng subclass.”** Sai; khởi tạo subclass có phụ thuộc phù hợp.
22. **“Một singleton holder static luôn có thể retry nếu constructor thất bại.”** Sai; holder cũng có thể erroneous.
23. **“Lỗi classpath và lỗi initialization luôn phân biệt được chỉ từ tên class ở exception.”** Sai; phải xem nguyên nhân, thời điểm và cấu hình runtime.
24. **“Thông điệp ‘Could not initialize class’ là contract parse ổn định.”** Không nên; nội dung message có thể khác implementation.
25. **“Sửa code static initialization trong source khi process đang chạy sẽ tự phục hồi class lỗi.”** Không; process/loader còn sử dụng định nghĩa đã load, trừ khi có cơ chế reload chuyên biệt thực sự.

## 18. Câu hỏi và bài tập tự kiểm tra

**Câu 1.** Một class có field static khởi tạo bằng method ném `IllegalStateException`. Lần active use đầu thường nhận gì?

*Đáp án:* Nếu initialization thất bại do RuntimeException không thuộc Error, JVM bọc theo thuật toán JLS thành `ExceptionInInitializerError`.

**Câu 2.** Active use thứ hai của class đã erroneous sẽ nhận gì?

*Đáp án:* `NoClassDefFoundError` thay vì khởi tạo lại bình thường.

**Câu 3.** Static initializer trực tiếp ném `AssertionError`. Lần đầu có bắt buộc qua EIIE không?

*Đáp án:* Không. Error có thể được truyền trực tiếp; sau thất bại class bị erroneous và lần sau có thể nhận NCDFE.

**Câu 4.** Vì sao `Broken.LABEL` không chạy initializer trong chương trình chính?

*Đáp án:* LABEL là một compile-time constant variable và cách dùng đó không kích hoạt khởi tạo class.

**Câu 5.** `Broken.class.getSimpleName()` có chứng minh class đã initialized thành công không?

*Đáp án:* Không. Class literal/metadata access không buộc chạy static initializer như việc đọc non-constant static field.

**Câu 6.** `Class.forName(name, true, sameLoader)` có khởi tạo lại class erroneous không?

*Đáp án:* Không; nếu JVM đã đánh dấu class erroneous, active use sau nhận NCDFE.

**Câu 7.** Phân biệt ClassNotFoundException và NCDFE trong tình huống bài học?

*Đáp án:* ClassNotFoundException là checked exception thường do API lookup class theo tên không tìm được định nghĩa; NCDFE là LinkageError có thể do thiếu định nghĩa lúc runtime hoặc do class đã hỏng initialization.

**Câu 8.** Vì sao không nên đặt kết nối database bên trong static initializer nếu cần retry?

*Đáp án:* Một lỗi môi trường tạm thời có thể làm class erroneous cho cả các lần dùng sau, thay vì cho ứng dụng tái thử có kiểm soát.

**Câu 9.** Khi chỉ nhìn thấy NCDFE ở request thứ hai, bước debug quan trọng nhất là gì?

*Đáp án:* Tìm lỗi initialization đầu tiên trên toàn process/log, gồm EIIE hoặc Error gốc, và xem stack trace/cause.

**Câu 10.** Cùng một class binary name được define bởi hai loader khác nhau có phải luôn là cùng runtime class identity?

*Đáp án:* Không. Identity có liên quan tới defining loader. Nhưng class loader mới không bảo đảm định nghĩa mới nếu tiếp tục delegation về loader cha.

**Câu 11.** Một thread B có thể chỉ thấy NCDFE dù không thấy lỗi initialization ban đầu không?

*Đáp án:* Có, nếu thread A đã cố init class và thất bại, JVM đánh dấu class erroneous trước khi B có thể tiếp tục active use.

**Câu 12.** Catch Exception có đủ để bao cả EIIE và NCDFE không?

*Đáp án:* Không. Cả hai đều là Error, không phải subclass của Exception.

**Câu 13.** Nếu initializer thay đổi một registry chung rồi ném exception, JVM có tự rollback registry không?

*Đáp án:* Không có rollback tổng quát. Phải thiết kế initializer và lifecycle để tránh/kiểm soát partial side effects.

**Câu 14.** Đổi `static final int VALUE = 42;` thành `static final int VALUE = Integer.parseInt("42");` có thể thay đổi thời điểm class initialization không?

*Đáp án:* Có. Trường hợp đầu là constant variable; trường hợp thứ hai có lời gọi method, không phải compile-time constant expression.

**Câu 15.** Có nên catch NoClassDefFoundError rồi cố gán lại field static để cứu class?

*Đáp án:* Không. Class erroneous không thể trở thành initialized chỉ bằng thao tác gán field; cần sửa nguyên nhân và quản lý lifecycle/class loading phù hợp.

**Câu 16.** Một class Child khởi tạo lỗi vì Parent static initializer lỗi. Nên xem class nào trước?

*Đáp án:* Xem stack trace và cause gốc; nếu Parent là nơi initialization thất bại đầu tiên, xử lý lỗi ở Parent/dependency trước thay vì chỉ sửa nơi dùng Child.

## 19. Checklist phòng ngừa lỗi class initialization trong production

- **Giảm công việc trong static initializer:** ưu tiên hằng số thuần và cấu trúc dữ liệu ổn định.
- **Không đặt tác vụ cần retry trong static init** nếu ứng dụng có yêu cầu phục hồi runtime.
- **Kiểm tra cấu hình đầu vào** ở lifecycle rõ ràng thay vì tạo singleton ẩn mà khó đoán.
- **Tài liệu hóa và theo dõi lỗi startup**: log cause, stack trace, class/module/source, không chỉ message ngắn.
- **Phân biệt dependent class failure** với missing runtime dependency.
- **Xem cùng class loader** khi điều tra trạng thái erroneous và khả năng reload.
- **Test từ process sạch** để thấy exception đầu tiên, sau đó test active use thứ hai để xác nhận đường NCDFE.
- **Tránh side effect không idempotent** trong static initializer hoặc phải quản lý rollback tại nơi phù hợp.
- **Đừng catch Error rồi im lặng**; tại boundary chẩn đoán cần báo sự cố và dừng component nếu không đáng tin.
- **Đảm bảo classpath/module path đúng** nếu evidence cho thấy NoClassDefFoundError do thiếu định nghĩa thực sự.
- **Kiểm thử concurrency** khi nhiều thread có thể kích hoạt init gần như đồng thời; không dựa vào thứ tự thông báo Error tuyệt đối.
- **Kiểm thử các đường gọi không kích hoạt init** như compile-time constants và metadata để tránh kết luận sai khi tạo reproduce case.

## 20. Tài liệu chính thức Java 17

- [JLS Java SE 17 §12.4.1 — When Initialization Occurs](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1): các thao tác gây initialization và ngoại lệ của compile-time constant.
- [JLS Java SE 17 §12.4.2 — Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2): trạng thái initialization, synchronization, Error wrapping, erroneous state và các yêu cầu khởi tạo sau khi thất bại.
- [JVMS Java SE 17 §5.5 — Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5): khởi tạo trong JVM.
- [Java SE 17 API — ExceptionInInitializerError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ExceptionInInitializerError.html): class Error báo lỗi trong static initializer và cách truy xuất exception gốc.
- [Java SE 17 API — NoClassDefFoundError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html): lớp LinkageError có nhiều nguồn phát sinh, không chỉ lỗi initialization.
- [Java SE 17 API — LinkageError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/LinkageError.html): nhóm vấn đề liên quan đến loading/linking/khả năng tương thích class.
- [Java SE 17 API — ClassNotFoundException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassNotFoundException.html): checked exception của một số phương thức lookup class.
- [Java SE 17 API — Class.forName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)): lựa chọn initialize true/false khi lookup class.
- [JLS Java SE 17 §4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): điều kiện xác định constant variable.
- [JLS Java SE 17 chương 11 — Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): phân cấp checked/unchecked và xử lý Throwable.

**Ghi nhớ cuối:** Một class có thể **tồn tại trên classpath** nhưng bị JVM đánh dấu **erroneous** sau static initialization thất bại. **Lần đầu** thường thấy `ExceptionInInitializerError` khi nguyên nhân là RuntimeException, hoặc Error gốc khi initializer ném Error; **lần sử dụng chủ động sau** thấy `NoClassDefFoundError`. Không nhầm nó với thiếu class file nếu có log initialization failure sớm hơn. Hãy sửa lỗi gốc, tránh static initializer phụ thuộc môi trường dễ hỏng và đừng cho rằng gọi lại class sẽ tự hồi phục trong cùng class loader.