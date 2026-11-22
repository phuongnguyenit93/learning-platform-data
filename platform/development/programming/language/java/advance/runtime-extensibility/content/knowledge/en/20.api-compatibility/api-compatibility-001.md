# Phân biệt tương thích mã nguồn, nhị phân và hành vi của hợp đồng API

## 1. Một thay đổi API có thể “tương thích” theo ba nghĩa khác nhau

Trong Java, thư viện hoặc plugin host thường có một **hợp đồng (contract)** giữa bên cung cấp API/SPI và bên sử dụng. Khi nâng phiên bản của hợp đồng, nói “thay đổi này backward compatible” là **chưa đủ chính xác**: phải nói rõ **loại tương thích**, **chiều thay thế phiên bản** và **những thành phần đã hoặc chưa được biên dịch lại**.

Ba mức quan trọng:

1. **Tương thích mã nguồn (source compatibility):** mã nguồn của consumer/provider viết cho API cũ còn **biên dịch được** khi chuyển sang API mới trong một môi trường biên dịch xác định hay không?
2. **Tương thích nhị phân (binary compatibility):** các file `.class` hoặc JAR **đã biên dịch từ trước** có liên kết và hoạt động với phiên bản API mới mà **không bắt buộc biên dịch lại** không, ít nhất với những tham chiếu cũ?
3. **Tương thích hành vi (behavioral compatibility):** dù mã biên dịch và JVM liên kết thành công, kết quả, tác dụng phụ và cam kết nghiệp vụ có **giữ đúng kỳ vọng mà client cũ đang dựa vào** không?

Đây là ba câu hỏi độc lập. **Biên dịch thành công không chứng minh binary compatibility cho bytecode cũ; bytecode tải và liên kết thành công không chứng minh behavior compatibility.**

Ví dụ, một plugin host công bố:

~~~java
public interface PricePolicy {
    int fee(int amount);
}
~~~

Đây chỉ là **một chữ ký Java**, chưa mô tả hết hợp đồng: `fee(100)` phải trả bao nhiêu, tham số âm xử lý thế nào, có được đổi trạng thái không, có thể gọi đồng thời không, lỗi được báo bằng loại exception nào? Các quy tắc đó có thể nằm trong Javadoc, specification hoặc test contract; thay đổi chúng có thể phá vỡ client **dù interface vẫn giữ nguyên**.

## 2. Bảng so sánh: kiểm tra cái gì và phá vỡ như thế nào?

| Khía cạnh | Câu hỏi kiểm tra | Phương pháp thử điển hình | Dấu hiệu không tương thích |
|---|---|---|---|
| **Source** | Mã nguồn cũ có build lại được với API mới? | `javac`/Maven/Gradle compile **source cũ** với API mới | Lỗi compiler: không có method, overload mơ hồ, type không khớp, method không được override |
| **Binary** | JAR/class **đã biên dịch** có chạy với API mới? | Giữ nguyên bytecode client/provider cũ; chỉ thay runtime API JAR rồi chạy | `NoSuchMethodError`, `NoSuchFieldError`, `IllegalAccessError`, `IncompatibleClassChangeError`, `AbstractMethodError` hoặc lỗi linkage liên quan |
| **Behavior** | Kết quả và các bảo đảm hợp đồng còn đúng? | Contract tests, integration tests, golden outputs, concurrency/error-path tests | Trả kết quả khác, thứ tự/exception khác, mất invariant, vi phạm thread-safety/idempotence/timeout đã cam kết |

**Quan hệ giữa ba loại không phải phép kéo theo một chiều:**

- Có thể **binary-compatible nhưng source-incompatible**: thêm overload có thể làm lệnh gọi `method(null)` mơ hồ khi build lại; bytecode cũ vẫn gọi đúng descriptor đã chọn.
- Có thể **source-compatible cho client nhưng binary-incompatible**: đổi return type `int` sang `long`, client gán vào `long` vẫn biên dịch, nhưng bytecode cũ gọi descriptor `()I` có thể gặp `NoSuchMethodError`.
- Có thể **source- và binary-compatible nhưng behavior-incompatible**: thay thuật toán tính phí từ 10% thành 20% trong khi chữ ký public giữ nguyên.
- Có thể một thay đổi **giữ được hành vi hiện tại** nhưng phá source/binary compatibility (ví dụ đổi tên method rồi thêm migration code chỉ ở một phía). Vì vậy kiểm tra hành vi không thay thế kiểm tra build/linkage.

### Cần xác định rõ “chiều” của phép thử

Ký hiệu:

- `API v1`: phiên bản cũ của hợp đồng.
- `API v2`: phiên bản mới.
- `Client v1.class`: bytecode đã biên dịch dựa trên API v1.
- `Provider v1.class`: bytecode plugin đã implement SPI v1.

Hai kịch bản khác nhau:

~~~text
Kiểm tra SOURCE:
    client-v1.java + API v2  --> javac có thành công không?

Kiểm tra BINARY:
    client-v1.class + API v2 --> JVM có tìm được method/field/type cũ không?

Kiểm tra BEHAVIOR:
    client-v1.class + API v2 --> kết quả có còn đúng specification v1 không?
~~~

Đối với plugin, phải thử **cả hai hướng** khi chính sách version của hệ thống yêu cầu: *host mới chạy plugin cũ* và *host cũ chạy plugin mới*. Hai hướng có thể cho kết quả khác nhau; “v2 tương thích với v1” không tự động là quan hệ hai chiều.

## 3. Source compatibility: khi biên dịch lại code cũ

Ở cấp source, compiler đánh giá toàn bộ cú pháp, overload resolution, access control, type inference, generics, annotation processors, module readability và nhiều quy tắc khác của Java tại **thời điểm build**.

Ví dụ source break dễ nhận biết:

- Xóa hoặc đổi tên public method mà mã nguồn client gọi.
- Thêm một abstract method vào interface SPI khiến source của implementation cũ không còn implement đủ.
- Đổi tên package hoặc class và không cung cấp lớp/adapter tương ứng.
- Thêm overload tạo ra lựa chọn mơ hồ tại compile time.
- Siết visibility/access của API mà client import.
- Thay đổi generic bounds hoặc chữ ký làm source cũ không type-check.
- Thêm checked exception vào `throws` khiến code client chưa catch/declare không còn build được; thay đổi `throws` cũng có thể ảnh hưởng mã nguồn bắt một checked exception không còn được khai báo.
- Thay đổi module descriptor `exports`/`requires` khiến named module client không còn được đọc hoặc truy cập package.

**Điểm tinh tế:** source compatibility không chỉ là “những method cũ còn tồn tại”. Thêm một overload **có thể làm client cũ không build được** vì compiler phải chọn lại giữa nhiều overload, trong khi bytecode cũ đã lưu lựa chọn từ lần compile trước.

Ngoài ra, kết quả build phụ thuộc **classpath/module path, JDK release, compiler options, module graph**. Test “code v1 build trên máy mình” không đủ; cần test source thực tế với dependency và cấu hình sản xuất, ví dụ `javac --release 17` khi cam kết hỗ trợ Java 17.

## 4. Binary compatibility: JVM liên kết theo tham chiếu đã biên dịch

Java source được biên dịch thành bytecode chứa **symbolic references** tới các class, field và method, được giải quyết khi cần. Ở mức JVM, method descriptor bao gồm **kiểu tham số và kiểu trả về**. Ví dụ:

~~~text
Java source                    JVM method descriptor
public static int max()        max:()I
public static long max()       max:()J
public String greet(String x)  greet:(Ljava/lang/String;)Ljava/lang/String;
~~~

Vì `()I` và `()J` khác nhau, thay return type mà **không giữ method cũ** có thể phá client bytecode đã ghi tham chiếu `max:()I`. Trình biên dịch mã nguồn mới có thể tự chuyển từ `int` sang `long` ở assignment; nhưng JVM **không tự viết lại method reference trong class client cũ**.

Một số dấu hiệu thông thường:

- `NoSuchMethodError`: bytecode gọi method descriptor không còn được tìm thấy trong class/interface theo cách JVM cần.
- `NoSuchFieldError`: field mà bytecode tham chiếu không còn tồn tại theo tên/descriptor cũ.
- `IllegalAccessError`: liên kết tới class/member từng truy cập được nhưng nay bị chặn.
- `IncompatibleClassChangeError`: class/interface/static/instance shape không còn khớp cách bytecode cũ sử dụng.
- `AbstractMethodError`: có call site hợp lệ nhưng implementation được dispatch tới không cung cấp phương thức cụ thể cần thiết.
- `NoClassDefFoundError`: type mà mã đã biên dịch phụ thuộc không có sẵn hoặc không thể được định nghĩa/khởi tạo ở môi trường runtime; cần kiểm tra cause, không mặc định mọi trường hợp là API version.

Các lỗi này thuộc hệ `LinkageError` hoặc vấn đề tải/liên kết tương ứng, **khác** với compiler diagnostic và khác với exception nghiệp vụ từ implementation.

### Binary compatibility không đồng nghĩa “mọi cách gọi mới đều chạy”

Một số thay đổi được JLS coi là tương thích nhị phân với **các tham chiếu đã có**. Tuy nhiên nếu một host mới gọi một method **mới được thêm** vào interface trên plugin implementation cũ, có thể vẫn gặp `AbstractMethodError`. Vì vậy compatibility ở mức JLS không thay cho ma trận hỗ trợ “host-v2 ↔ provider-v1” trong vận hành.

### Bytecode và generic types

Thông tin generics ở source không phải lúc nào cũng xuất hiện nguyên dạng trong method descriptor do **type erasure**. Một số thay đổi generic signature chỉ tác động source, nhưng thay bound/erasure, bridge methods hoặc các phương thức override có thể tác động binary dispatch. Không nên phân loại “đổi generic luôn binary-compatible” nếu chưa so descriptor thực tế và test compiled artifacts.

## 5. Behavioral compatibility: giữ đúng lời hứa của hợp đồng

Các loại tương thích trên chỉ nói mã có thể **biên dịch và liên kết**, không nói chương trình có còn đúng về nghiệp vụ.

Một hợp đồng hành vi có thể bao gồm:

- **Preconditions:** đầu vào nào hợp lệ, `null` có được chấp nhận, phạm vi giá trị ra sao, khi nào throw exception.
- **Postconditions:** đầu ra có ý nghĩa gì; tỷ lệ, đơn vị, rounding, chuỗi format, encoding, thứ tự kết quả.
- **Invariants:** trạng thái không được vi phạm sau lời gọi, tính nhất quán giữa các phương thức.
- **Side effects:** ghi file, gửi mạng, gọi callback, tạo transaction, cập nhật state hay phát event.
- **Error semantics:** loại exception, điều kiện lỗi, retry behavior, mapping mã lỗi, có được bỏ qua lỗi hay không.
- **Ordering và concurrency:** có bảo đảm thứ tự trả kết quả, tính thread-safe, visibility/happens-before, callback được gọi một hay nhiều lần.
- **Idempotence và transaction semantics:** gọi lại cùng request có tạo thêm tác động hay không; rollback có thay đổi không.
- **Performance/resource promises:** độ trễ, bộ nhớ, timeout, blocking/non-blocking, backpressure nếu những yếu tố này đã được cam kết như một phần API.
- **Protocol/data compatibility:** định dạng JSON/serialization/schema và khả năng client cũ đọc dữ liệu mới.

Ví dụ `int fee(int amount)` giữ nguyên source và JVM descriptor, nhưng thay từ 10% sang 20% sẽ phá ứng dụng đã dựa vào quy tắc 10%. Nếu đổi cách làm tròn, thứ tự plugin providers, lỗi khi input âm hoặc khả năng thread-safe, đó cũng có thể là behavior break — kể cả tất cả integration tests chỉ kiểm tra “không throw exception” đều pass.

Một **behavioral contract** nên được biểu đạt trong Javadoc, acceptance criteria và **contract tests có assertions**; nếu chỉ để trong đầu lập trình viên thì rất khó chứng minh backward compatibility.

## 6. Ví dụ A: thêm overload — binary vẫn chạy, source cũ không build lại

Tình huống thứ nhất minh họa một thay đổi *mở rộng API* nhưng vẫn gây source incompatibility.

Giả sử dự án `case-a/` có ba vùng source. Các file Java sau đều hợp lệ trên Java 17.

### API v1 — `v1/src/demo/api/Selector.java`

~~~java
package demo.api;

public final class Selector {
    private Selector() {}

    public static String select(String value) {
        return "string";
    }
}
~~~

### API v2 — `v2/src/demo/api/Selector.java`

~~~java
package demo.api;

public final class Selector {
    private Selector() {}

    public static String select(String value) {
        return "string";
    }

    public static String select(Integer value) {
        return "integer";
    }
}
~~~

Chữ ký `select(String)` **vẫn được giữ nguyên** ở v2. Nhưng compiler Java có hai overload không có quan hệ “cụ thể hơn” khi đối số là `null`: `String` và `Integer`.

### Client cũ — `client/src/demo/app/Client.java`

~~~java
package demo.app;

import demo.api.Selector;

public final class Client {
    public static void main(String[] args) {
        System.out.println("selected=" + Selector.select(null));
    }
}
~~~

Từ thư mục `case-a/` dùng Bash:

~~~bash
mkdir -p out/v1 out/v2 out/client-old out/client-new

javac --release 17 -d out/v1 v1/src/demo/api/Selector.java
javac --release 17 -d out/v2 v2/src/demo/api/Selector.java

# Biên dịch client cũ against API v1
javac --release 17 -cp out/v1 -d out/client-old \
  client/src/demo/app/Client.java

# Không biên dịch lại client: chạy với từng API runtime
java -cp "out/v1:out/client-old" demo.app.Client
java -cp "out/v2:out/client-old" demo.app.Client

# Thử build lại đúng source cũ, nhưng với API v2
javac --release 17 -cp out/v2 -d out/client-new \
  client/src/demo/app/Client.java
~~~

Với Linux/macOS, `:` phân tách entries trong classpath; trên Windows đổi `:` thành `;`. Hai lệnh `java` có output giống nhau:

~~~text
selected=string
selected=string
~~~

Mỗi dòng là kết quả của **một lần chạy riêng**. Lệnh `javac` cuối **thất bại**, với diagnostic mang nội dung chính:

~~~text
reference to select is ambiguous
both method select(String) and method select(Integer) match
~~~

Dòng/đường dẫn chính xác trong diagnostic phụ thuộc file và compiler, nên không coi đây là stdout cố định của Java application.

**Giải thích:** bytecode `Client.class` cũ đã chứa tham chiếu tới `Selector.select:(Ljava/lang/String;)Ljava/lang/String;`. API v2 vẫn cung cấp method này nên nó liên kết và chạy. Nhưng khi biên dịch lại `Selector.select(null)`, compiler phải phân giải lại overload và thấy hai ứng viên mơ hồ.

**Bài học:** “chỉ thêm một overload” không mặc nhiên bảo đảm *source compatibility*. Cách tiến hóa an toàn hơn khi cần mở rộng API: đặt tên khác, dùng factory/option object, hoặc kiểm tra compile-time cả source client cũ trong CI.

## 7. Ví dụ B: đổi kiểu trả về — client source vẫn biên dịch, binary cũ hỏng

Tình huống thứ hai cố ý đổi chữ ký **JVM** trong khi một client cụ thể vẫn build lại được từ source do Java cho phép widening từ `int` sang `long`.

Cấu trúc độc lập `case-b/`:

### API v1 — `v1/src/demo/api/Quota.java`

~~~java
package demo.api;

public final class Quota {
    private Quota() {}

    public static int max() {
        return 10;
    }
}
~~~

### API v2 — `v2/src/demo/api/Quota.java`

~~~java
package demo.api;

public final class Quota {
    private Quota() {}

    public static long max() {
        return 10L;
    }
}
~~~

### Client — `client/src/demo/app/Client.java`

~~~java
package demo.app;

import demo.api.Quota;

public final class Client {
    public static void main(String[] args) {
        try {
            long q = Quota.max();
            System.out.println("quota=" + q);
        } catch (NoSuchMethodError e) {
            System.out.println("linkage=NoSuchMethodError");
        }
    }
}
~~~

`catch` trong ví dụ **chỉ để minh họa lỗi linkage một cách ổn định**. Ở ứng dụng thực tế, không nên coi `NoSuchMethodError` như một exception nghiệp vụ và tiếp tục chạy bình thường; hãy sửa phối hợp phiên bản runtime API/implementation.

Lệnh Bash tại `case-b/`:

~~~bash
mkdir -p out/v1 out/v2 out/client-old out/client-new

javac --release 17 -d out/v1 v1/src/demo/api/Quota.java
javac --release 17 -d out/v2 v2/src/demo/api/Quota.java

javac --release 17 -cp out/v1 -d out/client-old \
  client/src/demo/app/Client.java

java -cp "out/v1:out/client-old" demo.app.Client
java -cp "out/v2:out/client-old" demo.app.Client

# Recompile source cũ against v2
javac --release 17 -cp out/v2 -d out/client-new \
  client/src/demo/app/Client.java

java -cp "out/v2:out/client-new" demo.app.Client
~~~

Kết quả tương ứng từng lệnh `java`:

~~~text
quota=10
linkage=NoSuchMethodError
quota=10
~~~

Vì sao?

1. Với API v1, compiler ghi bytecode gọi `Quota.max:()I` rồi widening `int` sang `long` để lưu vào biến `q`.
2. Khi thay **chỉ API runtime** bằng v2, method `Quota.max:()I` không còn; v2 chỉ có `Quota.max:()J`. Bytecode cũ không được viết lại → `NoSuchMethodError`.
3. Khi **build lại client source** against v2, compiler sinh lời gọi `max:()J`; lệnh compile thành công và chương trình lại in `quota=10`.

**Kết luận cho thay đổi này:** source của client minh họa **tương thích** khi biên dịch lại; binary của client cũ **không tương thích** khi thay API runtime. Source compatibility phải được đánh giá theo từng tập source và ngữ cảnh, không suy rộng rằng mọi source khác đều tương thích.

Nếu thư viện bắt buộc phải nâng kiểu giá trị từ `int` lên `long` mà cần giữ binary cũ, một lộ trình thường là **giữ method cũ** và thêm method tên mới, ví dụ `maxLong()`, sau đó deprecate method cũ theo kỳ phát hành.

## 8. Ví dụ C: source và binary không lỗi, nhưng hợp đồng hành vi bị phá

Giả sử specification v1 cam kết: **`fee(amount)` bằng 10% của `amount` khi amount là bội số 10 không âm**. Client có test dựa vào quy tắc này.

### API v1 — `v1/src/demo/api/Policy.java`

~~~java
package demo.api;

public final class Policy {
    private Policy() {}

    public static int fee(int amount) {
        return amount / 10;
    }
}
~~~

### API v2 — `v2/src/demo/api/Policy.java`

~~~java
package demo.api;

public final class Policy {
    private Policy() {}

    public static int fee(int amount) {
        return amount / 5;
    }
}
~~~

### Client — `client/src/demo/app/Client.java`

~~~java
package demo.app;

import demo.api.Policy;

public final class Client {
    public static void main(String[] args) {
        int fee = Policy.fee(100);
        System.out.println("fee=" + fee);
        System.out.println("rule-ok=" + (fee == 10));
    }
}
~~~

Lệnh Bash tại `case-c/`:

~~~bash
mkdir -p out/v1 out/v2 out/client-old out/client-new

javac --release 17 -d out/v1 v1/src/demo/api/Policy.java
javac --release 17 -d out/v2 v2/src/demo/api/Policy.java

javac --release 17 -cp out/v1 -d out/client-old \
  client/src/demo/app/Client.java

java -cp "out/v1:out/client-old" demo.app.Client
java -cp "out/v2:out/client-old" demo.app.Client

javac --release 17 -cp out/v2 -d out/client-new \
  client/src/demo/app/Client.java

java -cp "out/v2:out/client-new" demo.app.Client
~~~

Kết quả từng lần chạy:

~~~text
fee=10
rule-ok=true
fee=20
rule-ok=false
fee=20
rule-ok=false
~~~

Không có compiler error hay `LinkageError`; method vẫn là `Policy.fee:(I)I`. Tuy nhiên, đầu ra `fee=20` **không đáp ứng specification cũ 10%**. Bất kể client có build lại hay không, hành vi vẫn thay đổi.

Trong hệ thống thật, thay đổi như vậy có thể khiến hóa đơn, báo cáo, cache key hoặc quy trình thanh toán sai dù deployment/test khởi động đều xanh. Để tránh: tạo **contract test** thể hiện quy tắc không được phá; nếu phải đổi quy tắc thì phát hành chính sách/endpoint/version mới và có kế hoạch migration rõ ràng.

> Đừng dùng “không gặp exception” làm tiêu chí duy nhất cho behavior compatibility. Một hệ thống trả **kết quả sai nhưng hợp lệ về type** có thể nguy hiểm hơn một lỗi linkage dễ phát hiện.

## 9. Ví dụ D: SPI interface thêm abstract method — plugin cũ gặp `AbstractMethodError`

Đây là tình huống quan trọng nhất khi thiết kế hệ thống **runtime extensibility**. Host và plugin được build riêng, cùng dùng một service interface. Người phát triển SPI v2 thêm method mới:

### SPI v1 — `spi-v1/src/demo/spi/Plugin.java`

~~~java
package demo.spi;

public interface Plugin {
    String id();
}
~~~

### SPI v2 — `spi-v2/src/demo/spi/Plugin.java`

~~~java
package demo.spi;

public interface Plugin {
    String id();
    String description();
}
~~~

### Provider cũ — `provider/src/demo/provider/OldPlugin.java`

~~~java
package demo.provider;

import demo.spi.Plugin;

public final class OldPlugin implements Plugin {
    @Override
    public String id() {
        return "old";
    }
}
~~~

### Host mới — `host/src/demo/host/Main.java`

~~~java
package demo.host;

import demo.spi.Plugin;
import demo.provider.OldPlugin;

public final class Main {
    public static void main(String[] args) {
        Plugin p = new OldPlugin();
        System.out.println("id=" + p.id());
        try {
            System.out.println("description=" + p.description());
        } catch (AbstractMethodError e) {
            System.out.println("failure=AbstractMethodError");
        }
    }
}
~~~

Các lệnh sau chạy từ thư mục chứa bốn cây source nêu trên; dùng Bash:

~~~bash
mkdir -p out/spi-v1 out/spi-v2 out/provider-old out/host

javac --release 17 -d out/spi-v1 \
  spi-v1/src/demo/spi/Plugin.java
javac --release 17 -d out/spi-v2 \
  spi-v2/src/demo/spi/Plugin.java

# Plugin đã được build theo interface v1
javac --release 17 -cp out/spi-v1 -d out/provider-old \
  provider/src/demo/provider/OldPlugin.java

# Host mới build với SPI v2 và bytecode plugin cũ
javac --release 17 -cp "out/spi-v2:out/provider-old" -d out/host \
  host/src/demo/host/Main.java

java -cp "out/spi-v2:out/provider-old:out/host" demo.host.Main

# Thử biên dịch lại source provider cũ với SPI v2
javac --release 17 -cp out/spi-v2 -d out/provider-new \
  provider/src/demo/provider/OldPlugin.java
~~~

Lệnh `java` in:

~~~text
id=old
failure=AbstractMethodError
~~~

Lệnh `javac` cuối không thành công: `OldPlugin` không còn implement method trừu tượng `description()` được thêm ở interface v2.

**Phân biệt hai hiện tượng:**

- **Source compatibility cho implementation cũ:** bị phá vì class Java cụ thể phải implement đủ abstract methods khi build lại.
- **Binary compatibility với các tham chiếu cũ:** việc thêm abstract method vào interface được JLS mô tả là binary-compatible theo nghĩa những tham chiếu cũ vẫn có thể liên kết; thực tế `id()` vẫn chạy với provider bytecode v1. **Nhưng host v2 bắt đầu gọi method mới** `description()` trên implementation v1 thì dispatch không có implementation → `AbstractMethodError`.

Nói “thêm abstract method vào SPI là binary-compatible nên an toàn với mọi plugin cũ” sẽ dẫn tới sai lầm. Đối với rollout host/plugin, sự an toàn còn phụ thuộc **method nào được host mới gọi** và plugin cũ có đáp ứng được không.

### Dùng `default method` có thể giảm rủi ro — nhưng cần xét hành vi

Một cách tiến hóa interface là:

~~~java
package demo.spi;

public interface Plugin {
    String id();

    default String description() {
        return id();
    }
}
~~~

Khi không có override, implementation cũ có thể kế thừa default implementation, giúp tránh nhu cầu buộc plugin cũ triển khai method mới. Tuy nhiên:

- Default phải có **semantics hợp lệ** cho mọi provider cũ. `description()` trả `id()` có thể đủ hoặc không, tùy hợp đồng.
- Thêm default method có thể gây **xung đột kế thừa** khi class đã implement nhiều interface có method trùng chữ ký, hoặc tương tác bất ngờ với hierarchy cũ. Cần test source và binary thực tế.
- Default method không bảo đảm các provider cũ đáp ứng một tính năng hoàn toàn mới; method nên thiết kế fallback rõ (hoặc dùng capability interface tùy chọn).
- Không dùng default chỉ để né `AbstractMethodError` nếu hành vi fallback là sai.

Một phương án khác là thêm interface mở rộng:

~~~java
public interface PluginV2 extends Plugin {
    String description();
}
~~~

Đây là **đoạn minh họa**: khi triển khai phải đặt trong package/module phù hợp, giữ `Plugin` gốc không thay đổi, để host kiểm tra `instanceof PluginV2` trước khi sử dụng chức năng mới. Plugin cũ tiếp tục cung cấp contract cũ; plugin mới có thể tự chọn capability mới. Điều này giúp tránh ép mọi provider cũ áp dụng thay đổi cùng một lúc.

## 10. Áp dụng vào hợp đồng host–plugin và SPI thực tế

Trong một hệ thống plugin Java, có thể tồn tại các bên độc lập:

~~~text
Host v2
  |
  +-- public SPI/API artifact v2
  |
  +-- Plugin A (JAR build against SPI v1)
  +-- Plugin B (JAR build against SPI v2)
  |
  +-- class loader hoặc module layer
  |
  +-- ServiceLoader / factory / discovery registry
~~~

Để plugin cũ hoạt động khi host được nâng cấp, cần xác minh:

1. **Type identity:** host và plugin chia sẻ đúng **một runtime class object** của interface SPI. Hai class có cùng binary name nhưng do hai defining class loaders khác nhau tạo ra **không phải một type**.
2. **Binary signatures:** host v2 vẫn cung cấp những class/method/field descriptors mà plugin v1 được compile để gọi.
3. **Instantiation:** constructor, provider factory, `ServiceLoader` service descriptor hoặc `module-info.java` `provides` vẫn tương thích.
4. **Module readability/exports:** nếu dùng JPMS, package API còn được export đến các module plugin phù hợp; host/plugin modules đọc đúng dependency.
5. **Provider capabilities:** host mới không yêu cầu plugin cũ có method bắt buộc mới nếu chưa có fallback hoặc version-gating.
6. **Behavior contract:** các callback, thứ tự gọi, lifecycle, thread-safety, exception semantics và resource ownership mà provider v1 dựa vào vẫn được giữ hoặc có migration tường minh.

Đặc biệt, “thay class trong plugin directory mà không restart host” là một vấn đề **class loading/lifecycle**, tách biệt nhưng có thể che lỗi compatibility. JVM không tự cập nhật bytecode của class đã được một loader định nghĩa. Thường cần dừng plugin cũ, loại bỏ tham chiếu và tạo class loader/module layer mới cho phiên bản mới; nếu không, test có thể đang chạy trên class cũ.

### Source compatibility có thể khác nhau giữa consumer và provider

Một thay đổi SPI có thể không phá source client chỉ *gọi* `Plugin.id()`, nhưng lại phá source của provider cũ đang `implements Plugin`. Ngược lại, thêm một overload vào API host có thể phá code của consumer do overload resolution dù implementation plugin không đổi.

Vì vậy báo cáo compatibility nên luôn ghi rõ:

~~~text
Đối tượng kiểm tra:
  host API consumer source
  plugin provider source
  old host bytecode
  old plugin bytecode
  module/ServiceLoader metadata
  runtime behavior contract

Chiều thử:
  host v2 + plugin v1
  host v1 + plugin v2 (nếu được hỗ trợ)
~~~

Không nên gộp tất cả thành một nhãn boolean duy nhất.

## 11. Một số thay đổi API dễ bị đánh giá sai

| Thay đổi | Source compatibility | Binary compatibility | Behavioral contract |
|---|---|---|---|
| Thêm overload `select(Integer)` cạnh `select(String)` | **Có thể phá** source gọi `select(null)` do ambiguous | Các call sites cũ tới `select(String)` thường vẫn liên kết | Method cũ còn giữ có thể hành xử như cũ |
| Đổi `int max()` → `long max()` | Một số source vẫn build do widening; source khác có thể hỏng | **Phá** method descriptor cũ `()I` | Kết quả số có thể giữ giá trị nhưng đó chưa đủ |
| Đổi implementation của `int fee(int)` | Thường không đổi source | Thường không đổi ABI | Có thể phá quy tắc nghiệp vụ |
| Thêm abstract method vào interface SPI | **Phá** source của concrete providers chưa implement | Việc thêm method có thể binary-compatible cho tham chiếu cũ; **call site mới** trên provider cũ có thể `AbstractMethodError` | Capability mới không được bảo đảm |
| Thêm default method vào interface | Thường thuận lợi hơn nhưng có thể có xung đột source/override | Cần xem xét xung đột dispatch và hierarchy thực tế | Fallback phải đúng semantics |
| Xóa public method/field đang được dùng | Source cũ thường hỏng | Bytecode cũ có thể `NoSuchMethodError`/`NoSuchFieldError` | Không đảm bảo |
| Giảm quyền truy cập public → package-private/private | Source ngoài package/module hỏng | Bytecode cũ có thể `IllegalAccessError` | Không đảm bảo |
| Thay static method bằng instance method (hoặc ngược lại) | Call syntax cũ có thể hỏng | Có thể `IncompatibleClassChangeError` | Không đảm bảo |
| Thêm checked exception vào khai báo `throws` | Có thể buộc caller catch/declare, phá source | `throws` không nằm trong JVM method descriptor nên không trực tiếp phá linkage | Error behavior có thể đổi |
| Thay `public static final` constant compile-time | Source thường còn hợp lệ | Old binary có thể vẫn dùng giá trị đã **inline** | Các client có thể thấy **giá trị khác nhau theo thời điểm compile** |
| Thay generic type parameters/bounds | Có thể gây lỗi compile hoặc warning | Phụ thuộc erasure, bridge methods và descriptors cụ thể | Có thể phát sinh cast lỗi ở runtime |
| Thay `exports` hoặc module dependency | Source của named modules có thể không truy cập được | Runtime access/linkage có thể hỏng do cấu hình module graph | Có thể đổi discovery/access |
| Đổi tên package/class | Source import cũ hỏng | Old symbolic references tới tên cũ không resolve nếu không có compatibility shim | Không đảm bảo |

Bảng có các từ **“thường”, “có thể”, “phụ thuộc”** có chủ đích: nhiều thay đổi có ngoại lệ theo JLS/JVMS, compiler và cách các client đang dùng API. Với public library cần chứng minh bằng **mã nguồn + bytecode thực tế + runtime tests**, không chỉ dựa vào heuristic “tên method giống nhau”.

### Compile-time constants và hành vi quan sát được

Ví dụ:

~~~java
public static final String VERSION = "v1";
~~~

Nếu `VERSION` là *constant variable* được sử dụng trong constant expression, javac có thể nhúng trực tiếp `"v1"` vào bytecode client. Sau khi đổi field sang `"v2"`, client cũ **có thể vẫn in `"v1"`** dù runtime chứa API mới; client build lại mới dùng `"v2"`. Đây là tình huống “binary không ném lỗi nhưng behavior version skew xuất hiện”. Nếu giá trị là dữ liệu runtime cần cập nhật, cân nhắc cung cấp method accessor thay vì phụ thuộc constant inlining.

### Checked exceptions và binary descriptor

Thông tin checked `throws` không tham gia method descriptor `(parameterTypes)returnType` trong JVM. Vì vậy thay `throws IOException` ở source không giống đổi return type hoặc parameter type. Tuy nhiên source compiler vẫn kiểm tra checked exceptions; một client đã bắt riêng exception cũ hoặc chưa xử lý exception mới có thể không build lại. Runtime behavior về loại lỗi được ném cũng có thể thay đổi.

## 12. Đặt tiêu chuẩn tương thích trong versioning và rollout

Không có một phép kiểm duy nhất phù hợp cho mọi public API. Một kế hoạch phát hành cụ thể nên gồm:

### 12.1. Định nghĩa chính sách

Ví dụ chính sách tương thích cho một SPI:

- Host v2 phải tiếp tục **chạy** plugin JAR đã build với SPI v1, không yêu cầu build lại.
- Mã plugin v1 khi rebuild với API v2 phải biên dịch không lỗi (nếu cam kết source compatibility).
- Các method đã được công bố ở v1 phải giữ các postconditions, exception semantics và lifecycle hooks quan trọng.
- Các tính năng mới chỉ bật cho plugin khai báo capability/version tương ứng.
- Những thay đổi cố ý phá hợp đồng phải có deprecation/migration guide và version boundary rõ.

**Semantic Versioning** là một quy ước về version number và mức độ phá API, **không tự phát hiện** mọi source/binary/behavior break. Ngay cả tăng minor version, một thay đổi được coi là “bổ sung” vẫn có thể làm overload resolution mơ hồ hoặc gây xung đột default methods. Phải kiểm tra contract thực tế, không suy luận từ số version.

### 12.2. Chiến lược tiến hóa an toàn hơn

- **Thêm method mới bằng tên mới** thay vì sửa descriptor public method đang được dùng; giữ shim method cũ nếu có thể.
- **Deprecate trước khi remove**: cho client thời gian chuyển; deprecation không xóa method nên không tự làm hỏng binary.
- **Dùng interface capability mở rộng** hoặc default method với fallback hợp lệ khi muốn bổ sung khả năng cho SPI.
- **Dùng request/config object** để thêm tùy chọn thay vì thêm overload không kiểm soát; thiết kế object cũng cần versioning hợp lý.
- **Version-gate theo capability thực tế** chứ không chỉ so chuỗi version; kiểm tra `instanceof`/feature negotiation khi thích hợp.
- **Tách contract behavior khỏi implementation detail**: kiểm tra đầu ra, errors, state transitions và side effects được công bố, tránh kiểm tra những chi tiết không hứa hẹn.
- **Thêm integration tests theo matrix** khi host/client/provider được triển khai hoặc nâng cấp độc lập.
- **Giữ một bản SPI chung cho class loader**: nếu plugin đóng gói riêng bản API trùng binary name và child-first loader nạp nó, có thể gặp `ClassCastException`, không phải lỗi semver đơn thuần.

### 12.3. Ma trận kiểm thử tối thiểu

| Tổ hợp | Mục tiêu |
|---|---|
| API v1 + source client/provider v1 | Baseline: mẫu cũ build được |
| API v2 + **source** client/provider v1 | Đánh giá **source compatibility** |
| API v2 runtime + **.class/JAR client/provider v1**, không rebuild | Đánh giá **binary compatibility** và khả năng nạp plugin cũ |
| API v2 runtime + implementation mới | Xác nhận chức năng v2 |
| Host v2 + plugin v1 | Tương thích ngược trong triển khai plugin |
| Host v1 + plugin v2 (nếu chính sách cam kết) | Tương thích tiến về trước hoặc graceful rejection |
| Contract tests chạy trên các tổ hợp được hỗ trợ | Đánh giá **behavior** với input/output, side effects, errors và concurrency |

**Không được vô tình recompile plugin cũ trong test binary.** Nếu build tool tự compile lại toàn bộ workspace theo API v2, bạn đã thử source compatibility và có thể không còn tái hiện `NoSuchMethodError`/`AbstractMethodError` của artifact thực tế đang chạy ở khách hàng.

## 13. Công cụ Java 17+ giúp chứng minh thay đổi

### `javac`: thử source compatibility

Lấy **mã nguồn v1**, đổi compile classpath/module path sang API v2, rồi chạy:

~~~bash
javac --release 17 -cp path/to/api-v2.jar -d out/client-rebuild \
  client/src/demo/app/Client.java
~~~

Hoặc áp dụng cùng logic trong Maven/Gradle CI. Với module source cần giữ module graph tương ứng; dùng `--module-path` và `--module`/`--module-source-path` đúng thiết kế, không ép hệ JPMS vào ví dụ classpath này.

### `javap`: xem bytecode signature và method descriptors

Giả sử đã biên dịch các class từ ví dụ B:

~~~bash
javap -classpath out/v1 -s -public demo.api.Quota
javap -classpath out/v2 -s -public demo.api.Quota
javap -classpath out/client-old -c -p demo.app.Client
~~~

Điều cần tìm là `descriptor: ()I` ở API v1, `descriptor: ()J` ở v2 và lời gọi đã compile trong client cũ. `javap -s` xem JVM descriptors; `javap -c` xem lệnh bytecode; `-p` bao gồm cả member private của class đang được kiểm tra.

Không chỉ so source diff: một thay đổi trông nhỏ ở Java có thể biến đổi JVM descriptor hoặc sinh/xóa bridge method. Đặc biệt với covariant return type, compiler có thể sinh synthetic **bridge methods** để hỗ trợ dispatch binary; phải kiểm tra artifact thực tế thay vì mặc định mọi đổi return type đều có tác động hệt nhau.

### `jdeps` và module metadata: kiểm tra dependency

`jdeps` phân tích các dependency cấp class/module của JAR, giúp phát hiện các class tham chiếu dependency không còn có mặt. Với JPMS, `java --describe-module` hoặc `jar --describe-module` cũng hữu ích để đối chiếu `requires`, `exports`, `uses` và `provides`.

Tuy nhiên, công cụ phân tích static dependency không chứng minh được các đường đi reflection, tên class dựng bằng string, `ServiceLoader` provider nằm ở layer runtime hoặc behavior contract. Phải kết hợp **runtime test**.

### Contract tests và differential tests

Dùng cùng một tập test nghiệp vụ chạy với API v1/v2. Các assertions phải phản ánh specification, ví dụ:

~~~java
int fee = Policy.fee(100);
if (fee != 10) {
    throw new AssertionError("10% fee contract broken: " + fee);
}
~~~

Đây là **đoạn kiểm thử tích hợp**, giả định có import `demo.api.Policy` từ ví dụ C. Chạy test against v1 sẽ pass; với v2 trả `20` sẽ fail. Đây là tín hiệu behavior regression rõ ràng hơn so với việc test chỉ xác nhận method trả về một `int`.

Đối với API có concurrency, contract tests phải kiểm tra cả race conditions, ordering và resource ownership, không chỉ một lời gọi tuần tự.

## 14. Hướng xử lý khi phát hiện lỗi ở môi trường sản xuất

| Triệu chứng | Khía cạnh nghi vấn | Điều cần kiểm tra |
|---|---|---|
| Client build lại lỗi vì `method(null)` ambiguous | Source | Các overload mới và quá trình overload resolution; thử cùng JDK/compiler flags |
| `NoSuchMethodError: ...()I` | Binary | Runtime JAR có còn method descriptor chính xác không; thứ tự classpath và class loader |
| `NoSuchFieldError` | Binary | Field name/type/static-ness cũ có còn đúng không; compile-time constant có bị inline không |
| `IncompatibleClassChangeError` | Binary | Class/interface shape, static/instance invocations, inherited defaults/dispatch |
| `AbstractMethodError` khi host mới gọi plugin cũ | SPI evolution | Method mới có abstract không? Plugin cũ có implementation? Capability negotiation đúng chưa? |
| `IllegalAccessError` trên module/class | Module access / binary | Public visibility, JPMS `exports`/`opens`, module graph, class loader |
| `ClassCastException` dù class name giống nhau | Loader identity | Hai copies của SPI có bị loader khác nhau định nghĩa không? |
| Plugin chạy được nhưng tính toán khác bản trước | Behavior | Contract tests, semantics, rounding/units/exceptions, feature flags và data |
| Client cũ đọc hằng số cũ dù API đã đổi | Build-time constant | Hằng `static final` có bị inline lúc compile client không? |
| Chỉ một số plugin fail | Mixed-version matrix | Plugin build bằng SPI nào, host/API runtime nào, loader nào và capability nào được gọi |

Khi debug, ghi **version artifact, class loader, nguồn JAR/module và JVM descriptor**. Nếu có thể, lưu lại chính **plugin JAR cũ** gây lỗi để tái hiện mà không compile lại. Một log chỉ chứa method name không đủ xác định loại binary break.

## 15. Checklist quyết định khi review thay đổi hợp đồng

Trước khi merge/release một thay đổi public API/SPI, trả lời:

1. **Tập consumer nào đang sử dụng API?** Có source, bytecode hoặc plugin bên thứ ba được build độc lập không?
2. **Cam kết hỗ trợ chiều nào?** Host mới + plugin cũ, host cũ + plugin mới, hay cả hai?
3. **Source check:** source client/provider của phiên bản cũ có compile được với API mới trong đúng JDK/JPMS graph không?
4. **Binary check:** giữ nguyên `.class`/JAR cũ, thay duy nhất API/runtime mới, chạy những call sites cũ có gặp `LinkageError` không?
5. **Behavior check:** test đầu vào/đầu ra, side effects, exception, rounding, timing và concurrency có giữ cam kết không?
6. **SPI check:** nếu thay interface, provider cũ có còn khởi tạo và xử lý mọi lời gọi mới có thể xảy ra không?
7. **Reflection/ServiceLoader:** tên interface/provider, constructor/factory, `META-INF/services` hoặc `module-info.java` có phù hợp với lớp/loader mới không?
8. **Versioning:** có cần default method, adapter, capability API mới, deprecation hay major version không?
9. **Rollout:** có cách phát hiện plugin không tương thích và từ chối rõ ràng trước khi chạy nghiệp vụ không?
10. **Rollback:** có thể quay lại API/host v1 mà không làm hỏng dữ liệu hoặc plugin đã được cập nhật không?

Một release chỉ đạt mức “biên dịch được” **không** đồng nghĩa đã qua kiểm thử tương thích API. Khi môi trường hỗ trợ runtime extensibility, thử nghiệm phải giữ nguyên các artifacts cũ, vì nhiều lỗi chỉ xuất hiện ở thời điểm load/link/invoke.

## 16. Câu hỏi tự kiểm tra

1. **Thêm overload `select(Integer)` và giữ `select(String)` có chắc source-compatible không?** Không. `select(null)` có thể trở nên ambiguous khi biên dịch lại.
2. **Vì sao bytecode client cũ vẫn gọi `select(String)` đúng sau khi API thêm overload?** Vì call site đã chứa method reference/descriptor tới overload cũ, không thực hiện overload resolution lại khi runtime.
3. **`long q = Quota.max();` có thể compile với cả `int max()` và `long max()`, vậy binary cũ có luôn chạy được không?** Không. JVM descriptor có return type, `()I` khác `()J`.
4. **Vì sao `Policy.fee(int)` có thể phá hợp đồng mà `javac`/JVM không báo lỗi?** Bởi chữ ký không đổi nhưng tính phí 10% thành 20% là thay đổi semantics.
5. **Thêm abstract method vào interface SPI tác động thế nào đến plugin cũ?** Source provider cũ có thể không compile; bytecode cũ có thể vẫn chạy lời gọi cũ, nhưng host mới gọi method mới có thể gặp `AbstractMethodError`.
6. **Default method có bảo đảm mọi plugin cũ hoàn toàn tương thích không?** Không. Cần kiểm tra fallback behavior, method conflicts và provider lifecycle.
7. **`NoSuchMethodError` là lỗi source hay binary?** Lỗi linkage của bytecode ở runtime; source compatibility được thử bằng compile lại.
8. **Nếu `public static final String VERSION` đổi giá trị, client cũ có tự thấy giá trị mới?** Không nhất thiết, vì compile-time constant có thể đã được inline vào class client.
9. **Có thể dùng `jdeps` hoặc `javap` để chứng minh hợp đồng behavior không?** Không. Chúng chủ yếu giúp phân tích dependency/bytecode; cần contract tests chạy thực tế.
10. **Với host v2 + plugin v1, một lần build lại plugin v1 against SPI v2 có đủ chứng minh binary compatibility không?** Không. Phải chạy **đúng artifact plugin v1 đã biên dịch** với runtime v2.

**Ghi nhớ:** kiểm tra *source* bằng **biên dịch lại mã cũ**, kiểm tra *binary* bằng **chạy bytecode cũ không biên dịch lại** với API mới, và kiểm tra *behavior* bằng **assertions về ý nghĩa hợp đồng**. Cả ba cần ghi rõ chiều phiên bản và đối tượng host/consumer/provider. Đây là nền tảng để nâng cấp API/SPI mà không vô tình phá plugin đã phát hành.

## Tài liệu tham khảo

- [Java Language Specification 17 — Chapter 13: Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html): quy tắc binary compatibility khi thay class, interface, method và field.
- [Java Language Specification 17 — `15.12 Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): overload resolution và lý do thêm overload có thể gây source ambiguity.
- [Java Virtual Machine Specification 17 — `4.3 Descriptors](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3): field/method descriptors; method descriptor chứa kiểu trả về.
- [Java SE 17 — `NoSuchMethodError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoSuchMethodError.html) và [`AbstractMethodError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AbstractMethodError.html): lỗi linkage khi API/implementation không tương thích.
- [Java SE 17 — `ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): discovery và provider contracts trong ứng dụng mở rộng runtime.
- [JDK 17 — `javap`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): xem bytecode/descriptors; [`jdeps`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): kiểm tra dependency.
