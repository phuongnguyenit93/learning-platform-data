# Vì sao biên dịch thành công không tạo ra môi trường chạy an toàn

## 1. Ý nghĩa của câu “biên dịch thành công”

Trong Java, `javac` phân tích mã nguồn, kiểm tra các quy tắc ngôn ngữ, kiểu, tên, quyền truy cập và nhiều ràng buộc được xác định tại thời điểm biên dịch. Nếu không có lỗi làm dừng biên dịch, nó tạo ra bytecode (thường là tệp `.class`) để JVM có thể nạp và thực thi sau này.

**Biên dịch thành công chứng minh rằng mã đã vượt qua những phép kiểm tra của compiler trong đúng bối cảnh biên dịch đó. Nó không chứng minh rằng mọi đường chạy đều đúng, an toàn, có tài nguyên, có quyền truy cập hoặc dùng đúng thư viện lúc chạy.**

Hãy tách ba câu hỏi:

1. **Có biên dịch được không?** Mã nguồn và các phụ thuộc mà compiler nhìn thấy có hợp lệ với JDK/flags hiện tại không?
2. **Có khởi chạy và vận hành được không?** JVM có nạp, xác minh và liên kết được lớp cần thiết; môi trường, thư viện, cấu hình, tệp và dịch vụ có phù hợp không?
3. **Có chạy an toàn, đúng và ổn định không?** Dữ liệu đầu vào, luồng xử lý, quyền truy cập, trạng thái đồng thời, bộ nhớ, tài nguyên và ngoại lệ có được kiểm soát không?

Một chương trình có thể trả lời “có” ở câu 1 nhưng “không” ở câu 2 hoặc 3. Ngược lại, một chương trình chạy được trong máy phát triển cũng không tự chứng minh nó an toàn trong production.

### Ví dụ trực giác

```java
public class Greeting {
    public static void main(String[] args) {
        System.out.println("Hello, " + args[0]);
    }
}
```

Lưu thành `Greeting.java` và chạy trên Java 17+:

```powershell
javac Greeting.java
java Greeting World
```

Output:

```text
Hello, World
```

Nhưng nếu chạy `java Greeting` mà không truyền đối số, chương trình ném `ArrayIndexOutOfBoundsException` tại biểu thức `args[0]`. `javac` không thể biết trước mảng đối số lúc chạy sẽ có bao nhiêu phần tử.

Đây là sự khác biệt cơ bản giữa **hợp lệ về kiểu** và **hợp lệ theo điều kiện runtime**.

## 2. Compiler đảm bảo những gì, và giới hạn ở đâu?

| Điều `javac` có thể kiểm tra | Điều nó không thể khẳng định cho mọi lần chạy |
| --- | --- |
| Cú pháp, tên và khai báo hợp lệ theo phiên bản ngôn ngữ | Người dùng luôn nhập đúng dữ liệu |
| Tính tương thích kiểu tĩnh ở những nơi có đủ thông tin | Mọi giá trị runtime đều thỏa ràng buộc nghiệp vụ |
| Những điều kiện như definite assignment và mã không thể tới theo quy tắc Java | Mọi nhánh thực tế đều được kiểm thử |
| Sự tồn tại/chữ ký API trên compile classpath hiện tại | Runtime có cùng phiên bản dependency và môi trường |
| Một số cảnh báo về raw type, unchecked operation, deprecated API khi bật lint phù hợp | Mã không có lỗi logic, race condition hay lỗ hổng bảo mật |
| Tạo bytecode theo target/version được chỉ định | JVM đích có đúng các lớp, tài nguyên, quyền và cấu hình cần thiết |

Java là ngôn ngữ có kiểu tĩnh, nhưng kiểu tĩnh không diễn đạt hết quy tắc dữ liệu: `int` cho phép giá trị 0; `String` có thể trống, chứa ký tự nguy hiểm hoặc không đúng định dạng; một tham chiếu kiểu `User` có thể là `null` ở nơi Java cho phép.

Ví dụ `10 / divisor` hợp lệ về kiểu dù `divisor` có thể bằng 0. `Files.readString(path)` hợp lệ về API dù tệp có thể không tồn tại. `List<String>` giúp compiler kiểm soát cách dùng danh sách ở mã nguồn nhưng không có nghĩa ứng dụng không thể nhận dữ liệu sai kiểu qua reflection, raw types, serialization hoặc một ranh giới tích hợp thiếu kiểm tra.

**Đừng nhầm ba lớp kiểm soát:** kiểm tra compile-time, kiểm tra runtime tại ranh giới và kiểm thử hành vi. Mỗi lớp xử lý một tập rủi ro khác nhau.

## 3. Vòng đời từ mã nguồn tới JVM: vẫn còn nhiều điểm có thể thất bại

Một đường đi thông thường:

```text
.java + compile dependencies
          |
          v
javac: parse / kiểm tra tĩnh / tạo .class
          |
          v
Build: test / package / tạo JAR hoặc image
          |
          v
Deploy: chuyển artifact + cấu hình + dependency
          |
          v
JVM: load -> link (verify/prepare/resolve) -> initialize
          |
          v
Execute: xử lý dữ liệu, thread, I/O, mạng, tài nguyên
          |
          v
Kết quả runtime: đúng / sai / exception / treo / hết tài nguyên
```

Sơ đồ là cách nhìn tổng quan. Theo JVMS, việc liên kết bao gồm xác minh (*verification*), chuẩn bị (*preparation*) và phân giải (*resolution*); một số bước phân giải có thể thực hiện muộn, khi tham chiếu thực sự được dùng. Việc khởi tạo lớp có thể xảy ra khi lớp được dùng lần đầu theo những điều kiện cụ thể.

### 3.1. Nạp và liên kết lớp

Compiler biên dịch một lời gọi như `service.execute()` dựa vào chữ ký phương thức và các lớp có trên **compile classpath/module path**. Đến runtime, JVM phải tìm đúng lớp và liên kết những tham chiếu cần thiết.

Nếu dependency runtime thiếu hoặc khác bản compile, chương trình có thể gặp:

- `NoClassDefFoundError` khi JVM cần một định nghĩa lớp nhưng không thể tìm/khôi phục lớp đó (có thể do thiếu dependency hoặc một lần khởi tạo trước đã lỗi).
- `NoSuchMethodError` khi bytecode tham chiếu phương thức không còn có chữ ký tương ứng ở runtime.
- `NoSuchFieldError` hoặc `IncompatibleClassChangeError` khi cấu trúc binary thay đổi không tương thích.
- `UnsupportedClassVersionError` nếu JVM quá cũ so với định dạng bytecode của lớp cần nạp.

Những lỗi này thuộc họ `LinkageError` hoặc các loại `Error` liên quan đến nạp/liên kết; nhiều lỗi chỉ xuất hiện khi đường chạy thực sự sử dụng lớp/thành viên liên quan. Build thành công của artifact A không chứng minh bản dependency mà JVM chạy là bản compiler đã thấy.

### 3.2. Bytecode verification không phải kiểm thử nghiệp vụ

JVM có bước xác minh bytecode để bảo vệ các ràng buộc cấu trúc và type safety của máy ảo. Điều này rất quan trọng nhưng **không kiểm tra tính đúng đắn của thuật toán, tính hợp lệ của dữ liệu người dùng, tính bảo mật của endpoint hoặc sự tồn tại của dịch vụ ngoài**.

Một chương trình có bytecode được xác minh hợp lệ vẫn có thể ném `NullPointerException`, tính tiền sai, khóa chết hoặc ghi đè dữ liệu. Verification và kiểm thử hành vi thực hiện hai công việc khác nhau.

### 3.3. Khởi tạo lớp vẫn có thể thất bại

Java cho phép khởi tạo trường static thông qua mã chạy tại runtime:

```java
public class Settings {
    static final int PORT = Integer.parseInt(
        System.getProperty("service.port")
    );
}
```

Đây là **mảnh mã minh họa**, không phải chương trình có `main`. Mã biên dịch được, nhưng nếu lúc khởi tạo `Settings` mà thuộc tính `service.port` thiếu hoặc không phải số nguyên hợp lệ, lời gọi `Integer.parseInt` có thể ném ngoại lệ; lỗi trong quá trình khởi tạo có thể xuất hiện với `ExceptionInInitializerError`. Những lần truy cập tiếp theo tới lớp đã khởi tạo thất bại có thể gặp `NoClassDefFoundError`.

Compiler không thể bảo đảm mọi system property cần thiết sẽ tồn tại khi triển khai.

## 4. Thí nghiệm: biên dịch thành công nhưng lỗi do dữ liệu runtime

**Tệp `UnsafeDivide.java` chạy độc lập trên Java 17+:**

```java
public class UnsafeDivide {
    public static void main(String[] args) {
        int divisor = Integer.parseInt(args[0]);
        System.out.println(100 / divisor);
    }
}
```

Lệnh:

```powershell
javac --release 17 UnsafeDivide.java
java UnsafeDivide 4
```

Stdout:

```text
25
```

Cùng tệp `.class` đó, các đối số sau tạo kết quả khác:

| Lệnh | Hành vi runtime |
| --- | --- |
| `java UnsafeDivide 4` | In `25`, kết thúc bình thường |
| `java UnsafeDivide` | `ArrayIndexOutOfBoundsException` vì thiếu `args[0]` |
| `java UnsafeDivide abc` | `NumberFormatException` vì `abc` không phải số nguyên |
| `java UnsafeDivide 0` | `ArithmeticException: / by zero` |
| `java UnsafeDivide 3` | In `33` do phép chia số nguyên, có thể không phù hợp nếu bài toán cần số thập phân |

Thông báo và stack trace đầy đủ phụ thuộc JDK/vị trí mã; bảng tập trung vào loại sự cố và kết quả. Không có thay đổi nào ở mã nguồn hay bytecode giữa các lần chạy. Điều thay đổi là **đầu vào runtime**.

Thành công của `javac` chỉ nói rằng `args[0]` là một biểu thức kiểu `String`, `parseInt` trả về `int` khi thành công, và phép chia hai số nguyên được ngôn ngữ cho phép. Nó không thể chứng minh `args.length >= 1`, giá trị parse được hoặc mẫu số khác 0.

### 4.1. Phiên bản có kiểm tra điều kiện đầu vào

**Tệp `ValidatedDivide.java`:**

```java
public class ValidatedDivide {
    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println("ERROR: expected one integer argument");
            return;
        }

        final int divisor;
        try {
            divisor = Integer.parseInt(args[0]);
        } catch (NumberFormatException ex) {
            System.err.println("ERROR: argument is not an integer");
            return;
        }

        if (divisor == 0) {
            System.err.println("ERROR: divisor must not be zero");
            return;
        }

        System.out.println("RESULT=" + (100 / divisor));
    }
}
```

Chạy:

```powershell
javac --release 17 ValidatedDivide.java
java ValidatedDivide 4
java ValidatedDivide 0
java ValidatedDivide abc
```

Kết quả tương ứng:

```text
RESULT=25
```

Hai lệnh sau ghi ra **stderr**, mỗi lệnh một dòng:

```text
ERROR: divisor must not be zero
ERROR: argument is not an integer
```

Phiên bản mới xử lý đầu vào xấu có chủ đích thay vì để ngoại lệ không bắt được thoát ra từ `main`. Tuy nhiên đây **chưa phải bảo đảm toàn bộ ứng dụng an toàn**: ví dụ đã giới hạn ở phép chia nguyên, không tự giải quyết yêu cầu làm tròn, quyền truy cập, tài nguyên hệ thống hay trạng thái đồng thời. Trong CLI production, cần thêm exit code khác 0 cho nhánh lỗi để script/CI nhận biết thất bại; các lệnh `return` trong `main` ở đây chủ yếu minh họa kiểm tra dữ liệu.

### 4.2. Kiểm tra điều kiện là hợp đồng runtime

Các bước cần hỏi tại ranh giới nhận dữ liệu:

1. Có **đủ** dữ liệu không? Có thể `null`, thiếu field, thiếu đối số hoặc thiếu key?
2. Đúng **định dạng** không? Parse ngày/số, charset, mã định danh?
3. Đúng **miền giá trị** không? Số khác 0, khoảng từ 1 đến 100, số tiền không âm?
4. Có đúng **quan hệ** giữa các trường không? Ngày bắt đầu không muộn hơn ngày kết thúc?
5. Có phù hợp **quyền và trạng thái hệ thống** không? Tài nguyên tồn tại, người gọi được phép, trạng thái giao dịch cho phép chuyển?
6. Nếu điều kiện không đạt, ứng dụng **báo lỗi có kiểm soát** hay rơi vào hành vi bất ngờ?

Không nên thay validation bằng một phép cast ép kiểu, `@SuppressWarnings` hoặc một lần compile thành công.

## 5. An toàn về kiểu ở compile-time không loại bỏ mọi lỗi kiểu runtime

Java generic giúp compiler ngăn nhiều phép gán sai, nhưng có **type erasure** và những ranh giới mà kiểu tĩnh không đủ thông tin.

Ví dụ sau không phải cách làm được khuyến nghị:

```java
import java.util.ArrayList;
import java.util.List;

public class UnsafeGeneric {
    public static void main(String[] args) {
        @SuppressWarnings({"rawtypes", "unchecked"})
        List<String> words = new ArrayList();

        @SuppressWarnings({"rawtypes", "unchecked"})
        List raw = words;
        raw.add(123);

        System.out.println(words.get(0).length());
    }
}
```

Mã có thể biên dịch với Java 17+, kể cả khi đã suppression những cảnh báo tương ứng. Nhưng runtime có thể gặp `ClassCastException` lúc `words.get(0)` được đưa vào ngữ cảnh `String`. Compiler đã chấp nhận giả định kiểu do code cung cấp, trong khi danh sách thực tế chứa `Integer`.

**Suppress warning không chữa lỗi kiểu.** Muốn an toàn, hãy loại bỏ raw type, kiểm tra ranh giới dữ liệu và ưu tiên API thể hiện chính xác kiểu dữ liệu. Tương tự, reflection, deserialization hoặc thư viện bên ngoài có thể cung cấp giá trị ngoài giả định tĩnh; cần kiểm tra giá trị thực nhận.

Lưu ý: trường hợp trên ném ngoại lệ vì cast sang `String` được chèn theo ngữ nghĩa generics; lỗi thường xảy ra khi đọc phần tử qua `List<String>` chứ không phải lúc chèn `123` qua raw view.

## 6. Biên dịch với một thư viện, chạy với thư viện khác

Đây là nguyên nhân đặc biệt thường gặp trong ứng dụng Java nhiều module và pipeline CI/CD.

```text
Thời điểm compile             Thời điểm runtime
------------------            ---------------------
app source                     app.jar
  + library-v2.jar   --->        + library-v1.jar
  |                               |
javac kiểm chữ ký v2           JVM nạp và liên kết với v1
  |                               |
compile PASS                    lỗi linkage hoặc hành vi cũ
```

Ví dụ một client được biên dịch để gọi `Api.newFeature()` có trong thư viện v2. Nếu runtime lại nạp bản v1 không có phương thức với đúng tên/chữ ký tương ứng, khi lời gọi được liên kết có thể xảy ra `NoSuchMethodError`. Tất nhiên, điều kiện cụ thể phụ thuộc tên, descriptor, tính static/instance và bytecode thực tế.

Những biến thể đáng điều tra:

- Dependency thiếu khỏi runtime classpath.
- Có nhiều JAR chứa cùng tên lớp; class loader chọn một bản khác với dự tính.
- Một dependency được đổi cấu trúc mà client chưa được biên dịch/phát hành lại.
- Dự án biên dịch với JDK mới nhưng server chạy JVM cũ.
- Artifact đã build đúng nhưng pipeline triển khai dùng image/JAR cũ.
- Service nạp phiên bản cấu hình/tệp khác so với máy phát triển.

### 6.1. Cách kiểm tra lớp và phiên bản đang được nạp

Các lệnh hữu ích:

```powershell
java -version
javac -version
jar tf path/to/app.jar
javap -classpath path/to/app.jar -verbose example.Main
```

`jar tf` cho biết những entry đóng gói; `javap -verbose` cho biết thông tin lớp, constant pool và major version của bytecode. Chúng hỗ trợ điều tra artifact, không tự chứng minh tiến trình đang chạy đúng tệp đó.

Để theo dõi lớp được JVM nạp trên Java 17+:

```powershell
java -Xlog:class+load=info -cp "app.jar;libs/*" example.Main
```

Đây là **lệnh mẫu**: thay `example.Main`, `app.jar` và thư mục libs theo ứng dụng thực tế. Trên Windows dùng `;` để phân tách nhiều thành phần classpath; Linux/macOS dùng `:`. Log thường dài; cần lọc những lớp liên quan.

Trong mã chẩn đoán, một lớp có thể lấy nguồn `CodeSource`:

```java
System.out.println(
    SomeLibraryClass.class.getProtectionDomain().getCodeSource()
);
```

Đây là **mã minh họa đặt bên trong phương thức**, không phải chương trình độc lập. `CodeSource` có thể `null` tùy class loader/chính sách bảo vệ, nên đối chiếu thêm log nạp lớp và artifact thực tế.

### 6.2. Ý nghĩa và giới hạn của `--release`

`javac --release 17` yêu cầu compiler biên dịch theo ngôn ngữ, class-file target và API chuẩn Java được cung cấp cho release 17. Nó giúp ngăn việc vô tình gọi API chuẩn chỉ có trong Java mới hơn. Tuy nhiên tùy chọn này **không tự xác minh tất cả thư viện bên thứ ba**, không bảo đảm server có đủ tài nguyên và không kiểm tra hành vi runtime.

Ví dụ, tệp lớp biên dịch cho Java 21 có thể không chạy trên JVM 17 vì định dạng class file không được hỗ trợ. Biên dịch với `--release 17` giúp đặt baseline phù hợp, nhưng vẫn cần **thử chạy trên chính JRE/JDK đích** và kiểm tra những thư viện đi kèm.

## 7. Tài nguyên I/O, môi trường và dịch vụ ngoài

Một lời gọi hợp lệ như:

```java
String text = java.nio.file.Files.readString(
    java.nio.file.Path.of("config.txt")
);
```

chỉ là **mã minh họa cần đặt trong phương thức** có xử lý/khai báo `IOException`. Khi chạy, nó có thể thất bại nếu tệp không tồn tại, đường dẫn sai, không có quyền, thiết bị lưu trữ lỗi hoặc charset/nội dung không phù hợp.

Kết nối DB, HTTP, queue và dịch vụ bên thứ ba cũng có cùng bài toán: compiler nhìn thấy API/client library, nhưng không biết mạng có kết nối được không, chứng chỉ TLS có hợp lệ không, server có phản hồi kịp không, credential có đúng không.

### Ví dụ đọc tệp có xử lý lỗi

**Tệp `ReadConfig.java`:**

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ReadConfig {
    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println("ERROR: expected one file path");
            return;
        }

        try {
            String content = Files.readString(
                Path.of(args[0]), StandardCharsets.UTF_8
            );
            System.out.println("CHARS=" + content.length());
        } catch (IOException | SecurityException ex) {
            System.err.println("ERROR: unable to read file");
        }
    }
}
```

Chạy:

```powershell
javac --release 17 ReadConfig.java
java ReadConfig missing-config.txt
```

Nếu tệp không tồn tại tại thư mục hiện hành, chương trình in trên stderr:

```text
ERROR: unable to read file
```

Ví dụ cố ý không in đường dẫn tuyệt đối, nội dung tệp hoặc thông tin nhạy cảm vào thông báo lỗi. Với hệ thống thực tế, log nội bộ nên ghi ngữ cảnh đủ để vận hành nhưng tránh tiết lộ secret. Ngoài ra, `Path.of` có thể ném `InvalidPathException` (một unchecked exception) nếu đường dẫn đầu vào không hợp lệ, và lỗi tài nguyên nghiêm trọng khác vẫn có thể xảy ra. Việc bắt hai loại ở đây minh họa **xử lý một tập thất bại dự kiến**, không phải bảo đảm không lỗi.

Thực hành tốt cho I/O và tài nguyên:

- Kiểm tra cấu hình bắt buộc ở startup (fail fast), thông báo cấu hình nào thiếu nhưng không lộ giá trị bí mật.
- Xử lý timeout, retry có giới hạn và backoff ở các thao tác từ xa khi phù hợp với tính idempotent.
- Dùng `try-with-resources` đối với stream, connection và các tài nguyên cần đóng, kể cả khi có exception.
- Đặt giới hạn kích thước dữ liệu, số kết nối và thời gian chờ để giảm rủi ro hết tài nguyên.
- Kiểm tra quyền truy cập và whitelist đường dẫn/host dựa trên nhu cầu nghiệp vụ. Không xem kiểm tra `Files.exists` trước khi mở tệp là bảo đảm chống race (TOCTOU), vì trạng thái tệp có thể thay đổi giữa hai lần.
- Với dịch vụ ngoài, dùng health/readiness checks, metrics và cảnh báo lỗi thay vì dựa vào “compile xanh”.

## 8. Biên dịch thành công không ngăn lỗi đồng thời

Compiler cho phép nhiều luồng cùng truy cập một biến mutable. Nó không tự biến `counter++` thành phép cộng nguyên tử (*atomic*). Vì `counter++` gồm nhiều bước đọc/tính/ghi, hai thread có thể ghi đè tiến độ của nhau; nếu thiếu cơ chế đồng bộ, còn có vấn đề về visibility theo Java Memory Model.

Ví dụ **có nguy cơ data race**:

```java
public class RacyCounter {
    static int count = 0;

    public static void main(String[] args) throws InterruptedException {
        Runnable task = () -> {
            for (int i = 0; i < 100_000; i++) {
                count++;
            }
        };

        Thread first = new Thread(task);
        Thread second = new Thread(task);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println(count);
    }
}
```

Lưu thành `RacyCounter.java`, chạy `javac --release 17 RacyCounter.java` và `java RacyCounter`. Chương trình **biên dịch được**, nhưng kết quả có thể nhỏ hơn 200000 do mất cập nhật. Có những lần vẫn in đủ 200000; **không được dùng một lần chạy may mắn để chứng minh không có race condition**. Kết quả biến thiên tùy scheduling/JIT/phần cứng.

Một cách sửa đúng cho bài toán bộ đếm đơn giản là `AtomicInteger`:

**Tệp `AtomicCounter.java`:**

```java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCounter {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger count = new AtomicInteger();

        Runnable task = () -> {
            for (int i = 0; i < 100_000; i++) {
                count.incrementAndGet();
            }
        };

        Thread first = new Thread(task);
        Thread second = new Thread(task);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println(count.get());
    }
}
```

Chạy:

```powershell
javac --release 17 AtomicCounter.java
java AtomicCounter
```

Stdout sau khi cả hai thread kết thúc:

```text
200000
```

Ở đây `incrementAndGet()` đảm bảo thao tác tăng nguyên tử, còn `join()` giúp main đợi đủ hai luồng. Với trạng thái phức tạp hơn, chỉ thay từng biến bằng atomic chưa chắc bảo toàn bất biến liên quan nhiều biến; có thể cần khóa, immutable state, transaction hoặc thiết kế ownership rõ ràng.

Compiler cũng không tự phát hiện mọi deadlock, livelock, starvation, lỗi thứ tự giao dịch hay race giữa các request. Cần test đồng thời, review Java Memory Model và quan sát hệ thống thật.

## 9. An toàn bảo mật không xuất phát từ việc compile thành công

Mã nguy hiểm hoặc thiếu kiểm tra quyền vẫn có thể là Java hợp lệ. Ví dụ chương trình dùng JDBC nối chuỗi input trực tiếp vào SQL có thể biên dịch hoàn toàn nhưng tạo lỗ hổng SQL injection.

**Minh họa cách làm sai (không chạy như chương trình độc lập):**

```java
String sql = "SELECT * FROM users WHERE username = '" + username + "'";
```

Nếu `username` đến từ nguồn không tin cậy, thao tác nối chuỗi biến dữ liệu người dùng thành một phần cú pháp SQL. Cách xử lý đúng với JDBC là dùng parameterized query:

```java
String sql = "SELECT * FROM users WHERE username = ?";
try (java.sql.PreparedStatement statement =
         connection.prepareStatement(sql)) {
    statement.setString(1, username);
    try (java.sql.ResultSet rows = statement.executeQuery()) {
        // Xử lý kết quả có kiểm tra quyền và dữ liệu.
    }
}
```

Đoạn JDBC là **mã minh họa nằm trong phương thức có `connection` và `username` hợp lệ, có xử lý `SQLException`**; không phải chương trình độc lập. Parameter binding tách input khỏi cú pháp truy vấn. Tuy nhiên query an toàn hơn không thay thế authorization: người dùng có thể vẫn không được phép xem bản ghi được trả về.

Những kiểm soát runtime cần xem xét tùy ứng dụng:

- **Xác thực và phân quyền:** mỗi request/operation phải được kiểm tra quyền dựa trên danh tính và tài nguyên cụ thể.
- **Validation và encoding theo ngữ cảnh:** kiểm tra format, miền giá trị, output encoding và parameter binding phù hợp; đừng chỉ “lọc ký tự lạ” một cách chung chung.
- **Bảo vệ secret:** lấy thông tin nhạy cảm từ nguồn cấu hình được quản lý, giới hạn quyền đọc, tránh ghi secret vào log/stack trace phản hồi bên ngoài.
- **Dependency và cấu hình:** theo dõi lỗ hổng thư viện, kiểm soát phiên bản, TLS và quyền truy cập; compiler không kiểm tra mức độ tin cậy của dependency.
- **Giới hạn tài nguyên:** size/timeouts/rate limits/concurrency limits để tránh input làm cạn bộ nhớ, CPU hoặc kết nối.
- **Dữ liệu và transaction:** kiểm tra bất biến nghiệp vụ, quyền sở hữu bản ghi và ranh giới commit/rollback.

Các lỗi bảo mật đòi hỏi threat modeling, kiểm thử và review cấu hình; không thể suy ra “an toàn” chỉ vì `javac` tạo `.class` không báo lỗi.

## 10. Tài nguyên và ngoại lệ: không phải cứ bắt hết là an toàn

Java phân biệt `Exception` và `Error`; nhiều sự cố runtime là unchecked exception hoặc các loại error liên quan hệ thống. `NullPointerException`, `IndexOutOfBoundsException`, `IllegalArgumentException` là ví dụ unchecked exception; `OutOfMemoryError`, `StackOverflowError` và các lỗi linkage thuộc nhóm `Error`.

Không nên xử lý mọi lỗi bằng `catch (Throwable t)` rồi tiếp tục như bình thường. Sau một lỗi nghiêm trọng của VM, bộ nhớ hoặc class initialization, trạng thái còn lại có thể không phù hợp để tiếp tục xử lý an toàn. Hãy xác định lỗi nào có thể phục hồi, lỗi nào cần thất bại có kiểm soát, ghi log và kết thúc/khởi động lại thành phần phù hợp.

**Checked exception** (như `IOException`) buộc code phải bắt hoặc khai báo `throws` ở những lời gọi tương ứng; điều này không bảo đảm lỗi sẽ được xử lý đúng về mặt nghiệp vụ. Ví dụ `throws IOException` làm chương trình hợp lệ về compile nhưng thao tác đọc file vẫn có thể thất bại trong production.

Với tài nguyên hỗ trợ `AutoCloseable`, ưu tiên:

```java
try (var input = java.nio.file.Files.newInputStream(path)) {
    // Đọc dữ liệu trong phạm vi sử dụng.
} // input được đóng khi ra khỏi khối, cả khi ném exception.
```

Đây là **mảnh mã minh họa**, cần định nghĩa `path` và xử lý/khai báo `IOException`. `try-with-resources` giúp đóng tài nguyên, nhưng vẫn có thể gặp ngoại lệ khi mở, đọc hoặc đóng; cần xử lý theo chính sách ứng dụng.

## 11. Kiểm thử và xác minh sau biên dịch

Để từ “compile được” tiến tới “đáng tin khi chạy”, nên xây nhiều tầng kiểm soát. Mỗi tầng phát hiện một loại sai sót, không có tầng nào thay thế mọi tầng còn lại.

| Tầng | Kiểm tra chính | Điểm mù còn lại |
| --- | --- | --- |
| `javac`, `-Xlint`, `-Werror` | Cú pháp/kiểu/cảnh báo do compiler cung cấp | Logic nghiệp vụ, môi trường runtime |
| Static analysis và dependency scan | Một số lỗi mẫu, lỗ hổng đã biết, coding patterns | Hành vi dưới dữ liệu và cấu hình thực |
| Unit test | Nhánh logic, trường hợp biên, exception | Kết nối thật, classpath/deploy thực |
| Integration/contract test | Sự phối hợp các module, DB/API, serialization | Tải lớn, một số lỗi chỉ có ở production |
| Kiểm thử runtime trên đúng JDK/JAR/image | Linkage, classpath, khởi tạo lớp, cấu hình | Dữ liệu và tải chưa được mô phỏng |
| Load/stress/concurrency test | Race, throughput, độ trễ, sử dụng tài nguyên | Mọi cách schedule đều không thể bao phủ |
| Security test/review | Authorization, injection, quản lý secret, cấu hình | Mối đe dọa mới hoặc bề mặt chưa bao phủ |
| Quan sát sản xuất | Log, metrics, traces, alerts, crash evidence | Phát hiện sau khi sự cố xảy ra nếu thiếu phòng ngừa |

### 11.1. Ma trận dữ liệu cho một phép toán

Ví dụ với `ValidatedDivide`:

| Nhóm dữ liệu | Input mẫu | Điều cần xác minh |
| --- | --- | --- |
| Bình thường | `4` | Kết quả `25` |
| Biên lỗi | `0` | Lỗi có kiểm soát, không crash |
| Sai định dạng | `abc` | Thông báo parse không thành công |
| Thiếu | Không có tham số | Báo thiếu đối số |
| Nhiều hơn dự kiến | `4 5` | Báo sai số lượng đối số |
| Giá trị âm | `-4` | Kết quả phép chia nguyên đúng theo yêu cầu |
| Giá trị rất lớn | `999999999999` | Không vượt qua parse như thể hợp lệ |

Nếu nghiệp vụ đòi phép chia số thập phân, việc Java in `33` với `100 / 3` là **kết quả ngôn ngữ đúng nhưng nghiệp vụ có thể sai**. Test cần mô tả hợp đồng mong đợi (ví dụ dùng `BigDecimal` và quy tắc làm tròn) chứ không chỉ xác minh code không ném ngoại lệ.

### 11.2. Các lớp cấu hình cần xác minh

- **Build:** JDK, `--release`, cờ compiler, compile classpath, dependency graph, generated sources.
- **Artifact:** nội dung JAR, metadata/version, file cấu hình được đóng gói, thư viện runtime.
- **Runtime:** `java -version` thật trên host/container, classpath/module path và nguồn lớp thực sự nạp.
- **Infrastructure:** quyền file/mạng, DNS, chứng chỉ, database, resource limits, clock/timezone, cấu hình environment.
- **Operations:** startup checks, readiness, health, log lỗi, alert, timeout, rollback và quy trình triển khai.

Không chỉ chạy unit test từ IDE: cần thử chạy **cùng artifact được phát hành** trong môi trường gần với đích triển khai nhất có thể.

## 12. Quy trình chẩn đoán khi “build xanh nhưng chạy hỏng”

Thực hiện tuần tự để tránh sửa nhầm nguyên nhân:

1. **Ghi rõ triệu chứng:** lệnh chạy, môi trường, JDK, artifact/version, input, thời điểm, exception/error và stack trace đầu tiên có ý nghĩa.
2. **Phân loại giai đoạn lỗi:** startup/load/link/init hay lỗi trong một request/worker sau khi ứng dụng đã chạy?
3. **Xác nhận artifact và dependency thật:** hash/phiên bản JAR, classpath/module path, log nạp lớp, bản image/container và cấu hình ở runtime.
4. **Nếu lỗi do input:** thử dữ liệu tối thiểu tái hiện, xác định precondition bị thiếu, bổ sung validation/contract test.
5. **Nếu lỗi do môi trường:** so sánh quyền, biến môi trường, file, DNS, credential, port, dịch vụ ngoài, quota và timeout.
6. **Nếu lỗi đồng thời:** kiểm tra shared mutable state, ranh giới đồng bộ, transaction, thread dump và test có tải. Một test chạy đúng không loại bỏ data race.
7. **Nếu lỗi bảo mật:** kiểm tra đường đi của dữ liệu không tin cậy, xác thực, phân quyền, parameter binding và tài nguyên có quyền tối thiểu.
8. **Sửa nguyên nhân rồi kiểm chứng:** biên dịch lại, chạy test phù hợp và chạy đúng artifact sau build trong môi trường gần production, theo dõi dấu hiệu lỗi tái phát.

Một bảng phân loại nhanh:

| Triệu chứng | Nơi ưu tiên điều tra |
| --- | --- |
| `NoClassDefFoundError` khi gọi chức năng | Dependency thiếu, lỗi khởi tạo lớp hoặc class loader |
| `NoSuchMethodError` | Lệch compile/runtime dependency, thay đổi binary API |
| `UnsupportedClassVersionError` | JDK chạy cũ hơn class-file target |
| `ExceptionInInitializerError` | Lỗi trong static initializer hoặc khởi tạo static field |
| `NumberFormatException`, `IndexOutOfBoundsException` | Input validation và giả định trong code |
| `IOException`, connection timeout | File, quyền, mạng, dịch vụ phụ thuộc |
| Kết quả ngẫu nhiên sai khi tải đồng thời | Data race, thiếu đồng bộ, transaction conflict |
| `OutOfMemoryError` | Giới hạn bộ nhớ, leak, input quá lớn, backpressure |
| Truy cập dữ liệu trái phép nhưng không có exception | Authorization và logic bảo mật |
| Chạy đúng trên máy cá nhân, sai ở server | Khác artifact, JDK, cấu hình hoặc môi trường |

**Đừng xử lý LinkageError bằng cách bắt ngoại lệ chung và bỏ qua.** Đối với vấn đề phiên bản và classpath, sửa dependency/deploy mới là cách xử lý gốc. Với lỗi dữ liệu, sửa precondition và xác định hành vi lỗi rõ ràng. Với lỗi tài nguyên, cần giới hạn sử dụng và chính sách vận hành.

## 13. Những ngộ nhận phổ biến

**“Java có kiểu tĩnh nên không thể gặp `ClassCastException`.”** Sai. Cast runtime, generics erasure, raw type và reflection vẫn có thể tạo ra lỗi kiểu khi chạy.

**“Không có warning nghĩa là không có lỗi.”** Sai. Các chẩn đoán compiler chỉ bao phủ những mẫu mà nó kiểm tra; `-Xlint:all` cũng không chứng minh business logic hoặc security.

**“Dùng `--release` đúng là deploy chắc chắn chạy được.”** Sai. Nó giúp đặt baseline compile cho API chuẩn và bytecode, nhưng không kiểm tra dependency ngoài, cấu hình hay các dịch vụ cần thiết.

**“JVM đã verify bytecode thì code đã an toàn.”** Sai. Verification bảo vệ quy tắc cấu trúc/type safety của máy ảo, không đảm bảo đáp ứng nghiệp vụ, quyền truy cập hay độ sẵn sàng dịch vụ.

**“Bắt `Exception` là chặn hết mọi sự cố.”** Sai. Có những loại `Error`; ngay cả exception đã bắt cũng có thể để lại trạng thái nghiệp vụ không đúng nếu xử lý không thận trọng.

**“Code đã chạy đúng một lần nên không có race.”** Sai. Scheduling không quyết định trước theo một trật tự cố định; lỗi đồng thời có thể chỉ lộ ra dưới tải hoặc trong thời điểm hiếm.

**“Có kiểm tra `exists` là tệp chắc chắn còn khi mở.”** Sai. Đó là lỗi kiểm tra rồi mới dùng (TOCTOU); môi trường có thể thay đổi sau khi kiểm tra.

**“Compile PASS có nghĩa phần mềm bảo mật.”** Sai. Compiler không tự thực thi authorization, không quét mọi dependency vulnerability và không biết dữ liệu nào người dùng được quyền xem.

## 14. Bài tập tự đánh giá

1. **`args[0]` có kiểu `String`. Vì sao code vẫn ném lỗi khi thiếu tham số?**  
   Vì kiểu tĩnh không khẳng định kích thước thực tế của mảng args. Cần kiểm tra `args.length`.

2. **Code gọi phương thức mới của thư viện đã compile được, nhưng deploy ném `NoSuchMethodError`. Nên kiểm tra gì?**  
   Kiểm tra dependency đã dùng để compile và JAR thực sự được nạp lúc chạy, cùng chữ ký bytecode tương ứng.

3. **`@SuppressWarnings("unchecked")` có làm một cast generic an toàn không?**  
   Không. Nó chỉ ảnh hưởng chẩn đoán compiler; vẫn cần dữ liệu đúng kiểu hoặc validation tại ranh giới.

4. **Vì sao `counter++` không an toàn dù `int` và cả hai thread đều có kiểu đúng?**  
   Phép tăng không nguyên tử, có thể mất cập nhật; đồng bộ/atomic semantics là trách nhiệm thiết kế runtime.

5. **API đọc file khai báo `throws IOException`, compile được. Điều đó bảo đảm gì?**  
   Chỉ bảo đảm quy tắc xử lý checked exception đã được tôn trọng tại compile time. Tệp/quyền/thiết bị vẫn có thể lỗi.

6. **Một thao tác trả dữ liệu của người dùng khác nhưng không ném exception. Đây là lỗi thuộc nhóm nào?**  
   Lỗi authorization/logic bảo mật. Biên dịch và vận hành bình thường không chứng minh có kiểm soát truy cập.

7. **Muốn giảm rủi ro “build xanh nhưng production hỏng”, cần bổ sung gì?**  
   Validation, unit/integration/contract/security/load tests thích hợp, kiểm tra JDK và runtime dependencies, chạy đúng artifact, cấu hình môi trường và quan sát vận hành.

## 15. Checklist áp dụng trước phát hành

- [ ] Compiler và JDK/toolchain của CI được xác định; dùng `--release` khi cần baseline runtime.
- [ ] Build có xử lý các cảnh báo liên quan; không đánh đồng `javac` PASS với chất lượng toàn hệ thống.
- [ ] Mọi input không tin cậy có kiểm tra định dạng, giới hạn, tính nhất quán và quyền truy cập.
- [ ] Các trường hợp thiếu/trống/không hợp lệ/biên đã được test; đường lỗi có thông báo và trạng thái phù hợp.
- [ ] Dependency/runtime classpath, class loader và JDK trên môi trường đích được kiểm tra.
- [ ] Cấu hình bắt buộc, quyền, secret, đường dẫn và dịch vụ ngoài được xác minh.
- [ ] I/O/connection có giới hạn tài nguyên, timeout và xử lý ngoại lệ hợp lý.
- [ ] Shared mutable state và giao dịch có cơ chế đồng bộ/atomic/transaction đúng.
- [ ] Test và smoke check chạy trên artifact thực sự dự kiến phát hành.
- [ ] Có log/metrics/alert và phương án rollback khi hành vi runtime vượt giả định.

**Điểm cốt lõi:** `javac` kiểm tra được tính hợp lệ tĩnh của mã trong môi trường biên dịch. **An toàn khi chạy** còn phụ thuộc dữ liệu, bytecode và thư viện thực nạp, khởi tạo lớp, cấu hình, tài nguyên, đồng thời, bảo mật và kiểm thử. Hãy dùng compiler như lớp phòng vệ đầu tiên, rồi chứng minh các hợp đồng runtime bằng validation, test và quan sát thực tế.

## Tài liệu đọc thêm

- [Java Language Specification — §12: Execution](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html)
- [Java Virtual Machine Specification — §5: Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html)
- [Java SE 21 — javac Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [Java SE 21 — java Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [Java SE 21 — Throwable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Throwable.html)
- [Java SE 21 — AtomicInteger](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html)
