# Đóng gói mạnh JDK internals từ Java 17

Từ Java 17, Java áp dụng **đóng gói mạnh (strong encapsulation)** đối với các API nội bộ của JDK. Những package nội bộ không được module JDK export không còn mặc nhiên truy cập được từ ứng dụng, kể cả khi ứng dụng chạy trên classpath. Việc một thư viện từng truy cập được bằng reflection hoặc import một lớp `sun.*` không có nghĩa cách làm đó vẫn được hỗ trợ.

Thay đổi này được hoàn tất theo **JEP 403 – Strongly Encapsulate JDK Internals** trong Java 17. Mục tiêu là bảo vệ ranh giới module, cho phép JDK thay đổi implementation nội bộ mà không phải duy trì các phụ thuộc ngoài hợp đồng công khai.

Bài này giải thích ý nghĩa của strong encapsulation, phân biệt `exports` với `opens`, cách xử lý `IllegalAccessError` và `InaccessibleObjectException`, cách dùng `--add-exports`/`--add-opens` khi cần chuyển tiếp, và cách tìm thư viện còn phụ thuộc JDK internals. Nội dung tập trung vào cơ chế hiện hành của Java 17; không dùng `--illegal-access` như giải pháp mở lại quyền truy cập.

## 1. JDK internals là gì?

JDK cung cấp các API công khai được tài liệu hóa trong Java SE, ví dụ:

- `java.lang.String`, `java.util.List`, `java.time.Instant`.
- `java.nio.file.Files`, `java.net.http.HttpClient`.
- `java.lang.invoke.MethodHandles`, `java.lang.invoke.VarHandle`.

Ngoài các API đó, JDK còn có những lớp và package phục vụ việc triển khai bên trong. Chúng có thể mang tên như `sun.*`, `com.sun.*`, `jdk.internal.*`, hoặc nằm trong package khác nhưng không được module tương ứng export.

Ví dụ thường gặp trong mã cũ:

~~~java
import sun.misc.Unsafe;
import sun.nio.ch.DirectBuffer;
import jdk.internal.misc.Unsafe;
~~~

Đây là các API nội bộ hoặc không phải hợp đồng Java SE công khai. Tên package là dấu hiệu cần điều tra, nhưng không nên chỉ dựa vào prefix để kết luận: một số package có tên `com.sun.*` được tài liệu hóa và export như API công khai. Cần kiểm tra module, tài liệu API và trạng thái hỗ trợ thực tế.

**Nguyên tắc:** Chỉ dựa vào API được tài liệu hóa và hỗ trợ cho ứng dụng. Lớp nội bộ có thể đổi tên, chuyển package, thay chữ ký hoặc bị loại bỏ giữa các bản JDK mà không cần bảo đảm tương thích nguồn hay nhị phân.

## 2. Module system và ranh giới truy cập

Từ Java 9, JDK được tổ chức thành các module. Mỗi module có thể khai báo:

- Những module mà nó phụ thuộc bằng `requires`.
- Những package công khai cho module khác bằng `exports`.
- Những package cho phép truy cập reflection sâu bằng `opens`.

Ứng dụng chạy trên classpath thường thuộc **unnamed module**. Các JAR chạy trên module path có thể trở thành named module nếu có `module-info.class` hoặc được xác định là automatic module.

Strong encapsulation áp dụng với cả ứng dụng trên classpath lẫn module path. Chạy ứng dụng trên classpath không làm cho package nội bộ của module JDK trở thành công khai.

### 2.1. Export và open có ý nghĩa khác nhau

| Cơ chế | Cho phép điều gì? | Dùng ở giai đoạn nào? |
| --- | --- | --- |
| `exports package` | Module khác truy cập các kiểu và thành viên `public` được phép trong package | Biên dịch và runtime |
| `opens package` | Cho phép reflection sâu vào các kiểu trong package, kể cả thành viên không `public`, theo quy tắc module | Runtime |
| `exports package to module` | Chỉ export package cho một số module được chỉ định | Biên dịch và runtime |
| `opens package to module` | Chỉ mở package cho reflection từ các module được chỉ định | Runtime |
| `open module` | Mở tất cả package của module cho reflection sâu | Runtime |

`exports` không tự cho phép reflection vào trường `private`. `opens` không biến các lớp `private` thành API Java có thể import và gọi trực tiếp trong mã nguồn.

## 3. Strong encapsulation thay đổi điều gì từ Java 17?

Lịch sử ngắn giúp hiểu vì sao một ứng dụng từng chạy trên JDK cũ có thể lỗi khi nâng lên Java 17:

| Phiên bản | Thay đổi liên quan |
| --- | --- |
| Java 9 | Module system xuất hiện; JDK bắt đầu đóng gói module và có cơ chế tương thích tạm thời cho truy cập nội bộ |
| Java 9–15 | Cơ chế relaxed encapsulation cho phép một số truy cập phản chiếu cũ tiếp tục hoạt động; `--illegal-access` được dùng trong giai đoạn chuyển tiếp |
| Java 16 | Strong encapsulation trở thành mặc định theo JEP 396; tùy chọn chuyển tiếp vẫn còn khả năng nới lỏng trong một số cấu hình |
| **Java 17** | **JEP 403** hoàn tất strong encapsulation; `--illegal-access` không còn khôi phục quyền truy cập relaxed cho các package nội bộ |

Từ Java 17, thêm `--illegal-access=permit` vào lệnh chạy không phải cách mở lại các package JDK. Tùy chọn này đã lỗi thời và không còn tác dụng nới lỏng encapsulation; runtime có thể phát cảnh báo về việc sử dụng nó.

Không nên tiếp tục đưa `--illegal-access=permit` vào script, cấu hình build hoặc tài liệu triển khai. Cần nâng cấp thư viện hoặc xác định chính xác package và module cần mở trong giai đoạn chuyển tiếp.

### 3.1. Có ngoại lệ đối với một số API nội bộ

JEP 403 vẫn giữ khả năng truy cập một số API nội bộ quan trọng, ví dụ `sun.misc.Unsafe`, thông qua module `jdk.unsupported`. Điều này **không biến chúng thành API Java SE được hỗ trợ ổn định**. Khả năng truy cập hiện tại không phải cam kết rằng implementation, chữ ký hoặc hành vi sẽ giữ nguyên ở các bản JDK sau.

Vì vậy, đừng kết luận rằng mọi tên `sun.*` đều bị chặn tuyệt đối; cũng đừng kết luận rằng một lớp còn truy cập được là an toàn để dùng lâu dài. Hãy phân biệt rõ **có thể truy cập trong runtime này** với **API công khai được hỗ trợ**.

## 4. Các lỗi thường thấy khi ứng dụng đụng JDK internals

Có nhiều kiểu lỗi khác nhau tùy cách truy cập.

### 4.1. Lỗi biên dịch do package không được export

Khi source import một kiểu thuộc package không được export từ module JDK, compiler có thể báo package không hiển thị hoặc module không export package đó.

Ví dụ minh họa việc dùng kiểu nội bộ `sun.nio.ch.DirectBuffer`:

~~~java
import java.nio.ByteBuffer;
import sun.nio.ch.DirectBuffer;

public class InternalAccessDemo {
    public static long addressOf(ByteBuffer buffer) {
        return ((DirectBuffer) buffer).address();
    }
}
~~~

Biên dịch bình thường trên Java 17 có thể bị từ chối vì `java.base` không export `sun.nio.ch` cho ứng dụng.

Đây là dấu hiệu source đang phụ thuộc implementation nội bộ. Đừng mặc định thêm flag là cách sửa lâu dài; trước hết cần xác định có API công khai nào đáp ứng nhu cầu hay không.

### 4.2. IllegalAccessError khi chạy

Một chương trình có thể đã biên dịch trong môi trường được mở package, nhưng khi chạy trên runtime không có quyền tương ứng, JVM có thể ném `IllegalAccessError`.

Đây là lỗi truy cập ở cấp liên kết/runtime. Nó khác với lỗi thiếu class hoặc method như `NoClassDefFoundError` và `NoSuchMethodError`.

### 4.3. InaccessibleObjectException khi dùng reflection

Một thư viện có thể dùng `setAccessible(true)` để cố truy cập trường hoặc method `private` của JDK:

~~~java
import java.lang.reflect.Field;

public class ReflectStringDemo {
    public static void main(String[] args) throws Exception {
        Field value = String.class.getDeclaredField("value");
        value.setAccessible(true);
    }
}
~~~

Trên Java 17, truy cập sâu vào `java.lang` của module `java.base` bị đóng đối với ứng dụng thông thường. Lời gọi `setAccessible(true)` có thể ném `InaccessibleObjectException`.

Nếu chỉ muốn kiểm tra khả năng mở quyền mà không ném exception khi không thể, dùng `trySetAccessible()`:

~~~java
boolean opened = value.trySetAccessible();
System.out.println("opened = " + opened);
~~~

Nếu package không được mở cho module của caller, kết quả thường là `false`. Không nên dựa vào reflection vào private field của JDK để xây dựng chức năng ứng dụng.

## 5. Phân biệt --add-exports và --add-opens

Java 17 cung cấp các tùy chọn cụ thể để mở một ranh giới module khi có nhu cầu tương thích tạm thời.

### 5.1. --add-exports: truy cập kiểu public trong package

Cú pháp:

~~~text
--add-exports <source-module>/<package>=<target-module>
~~~

Ví dụ, để cho code trên classpath truy cập kiểu `public` trong package `sun.nio.ch`:

~~~bash
javac --add-exports java.base/sun.nio.ch=ALL-UNNAMED -d out InternalAccessDemo.java
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED -cp out InternalAccessDemo
~~~

`ALL-UNNAMED` chỉ các unnamed module, thường là code chạy trên classpath.

Với ứng dụng là named module, chỉ định tên module đích thay cho `ALL-UNNAMED`:

~~~text
--add-exports java.base/sun.nio.ch=com.example.app
~~~

Cần cấu hình phù hợp ở cả compiler và runtime nếu source trực tiếp tham chiếu kiểu trong package đó. `--add-exports` chỉ cấp quyền truy cập đến các kiểu/thành viên `public` theo quy tắc export; nó không mở trường `private` để reflection sâu.

### 5.2. --add-opens: cho phép reflection sâu ở runtime

Cú pháp:

~~~text
--add-opens <source-module>/<package>=<target-module>
~~~

Ví dụ mở `java.lang` của `java.base` cho code classpath:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp out ReflectStringDemo
~~~

Tùy chọn này cho phép deep reflection từ module đích vào package được chỉ định. Nó **không** cho phép import trực tiếp các kiểu không public hoặc dùng chúng trong source như một API đã export.

`--add-opens` là tùy chọn runtime, không phải tùy chọn thay thế `--add-exports` khi biên dịch source cần truy cập kiểu public trong package chưa export.

### 5.3. So sánh nhanh

| Tình huống | Tùy chọn cần xem xét |
| --- | --- |
| Source import một kiểu `public` trong package chưa export | `javac --add-exports ...` |
| Ứng dụng cần truy cập kiểu `public` đó lúc chạy | `java --add-exports ...` |
| Framework dùng reflection vào trường/method `private` của package JDK | `java --add-opens ...` |
| Muốn reflection sâu vào package của module ứng dụng | Khai báo `opens` trong `module-info.java` hoặc cấu hình mở phù hợp |
| Muốn khôi phục toàn bộ relaxed encapsulation cũ | Không có cách tổng quát bằng `--illegal-access` trong Java 17 |

Chỉ mở đúng package, đúng module đích và trong thời gian cần thiết. Tránh mở rộng toàn bộ module cho `ALL-UNNAMED` nếu chỉ một framework named module cần quyền reflection.

## 6. Mở package của module ứng dụng bằng module-info.java

Strong encapsulation không chỉ liên quan JDK. Ứng dụng modular cũng cần thiết kế ranh giới package rõ ràng.

Giả sử module `com.example.app` có package API và package model cần framework đọc/ghi bằng reflection:

~~~java
module com.example.app {
    requires com.fasterxml.jackson.databind;

    exports com.example.api;

    opens com.example.model to com.fasterxml.jackson.databind;
}
~~~

Ý nghĩa:

- `requires com.fasterxml.jackson.databind` khai báo phụ thuộc vào module framework.
- `exports com.example.api` cho module khác truy cập API public trong package.
- `opens com.example.model to com.fasterxml.jackson.databind` cho framework được chỉ định thực hiện deep reflection vào model.

Tên module của framework phải đúng với tên module thực tế trong runtime; hãy kiểm tra metadata của thư viện thay vì đoán từ tên artifact Maven.

### 6.1. Qualified exports và qualified opens

Có thể giới hạn quyền cho một module cụ thể:

~~~java
exports com.example.api to com.example.client;
opens com.example.model to com.example.json;
~~~

Cách này giúp tránh công khai package hoặc mở reflection cho mọi module.

### 6.2. open module

Khai báo:

~~~java
open module com.example.app {
    requires some.framework;
}
~~~

sẽ mở tất cả package của module cho deep reflection tại runtime. Cách này có thể tiện cho framework cũ, nhưng phạm vi rộng hơn cần thiết trong nhiều ứng dụng. Ưu tiên `opens package to module` nếu chỉ một vài package và framework cần quyền truy cập.

Không thể sửa `module-info.java` của `java.base` hoặc module JDK để biến package nội bộ thành API công khai. Với JDK modules, các tùy chọn launcher/compiler chỉ tạo ngoại lệ truy cập cho tiến trình cụ thể.

## 7. Đặt tùy chọn mở module ở đâu?

Nếu một thư viện chưa thể nâng cấp ngay, các tùy chọn cần được đặt ở nơi thực sự khởi chạy JVM.

Ví dụ ứng dụng chạy bằng classpath:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar application.jar
~~~

Với named module:

~~~bash
java --add-opens java.base/java.lang=com.example.app --add-exports java.base/sun.nio.ch=com.example.app -m com.example.app/com.example.Main
~~~

Khi dùng Maven hoặc Gradle, cấu hình test JVM và JVM chạy ứng dụng có thể là hai nơi khác nhau. Thêm flag vào test không có nghĩa tiến trình production cũng đã được cấu hình, và ngược lại.

Một số điểm cần kiểm tra:

- Lệnh chạy thực tế trong container, service manager hoặc script triển khai.
- Cấu hình JVM của test runner.
- Cấu hình IDE nếu lỗi chỉ xuất hiện khi chạy từ IDE.
- Module đích là named module hay unnamed module.
- Flag áp dụng đúng module nguồn và package cần truy cập.

Không nên thêm một danh sách dài `--add-opens` theo kiểu thử từng package đến khi hết lỗi. Mỗi flag cần gắn với một dependency và một lý do cụ thể.

## 8. Tìm phụ thuộc JDK internals bằng jdeps

JDK 17 có công cụ `jdeps` để phân tích phụ thuộc ở cấp bytecode. Tùy chọn `--jdk-internals` giúp phát hiện tham chiếu đến JDK internal APIs trong class hoặc JAR.

Ví dụ:

~~~bash
jdeps --jdk-internals application.jar
~~~

Với JAR đa phiên bản, có thể chỉ rõ phiên bản cần phân tích:

~~~bash
jdeps --jdk-internals --multi-release 17 application.jar
~~~

Kết quả có thể cho biết:

- Class nào tham chiếu API nội bộ.
- Package hoặc module chứa API đó.
- Gợi ý thay thế nếu công cụ có thông tin tương ứng.

Có thể kết hợp với:

~~~bash
jdeps --print-module-deps application.jar
~~~

Lệnh này hỗ trợ xác định các module JDK cần thiết cho ứng dụng, hữu ích khi chuẩn bị runtime image theo module. Nó không thay thế việc tìm internal API; dùng `--jdk-internals` cho mục tiêu đó.

### 8.1. Giới hạn của phân tích tĩnh

`jdeps` phân tích phụ thuộc mà nó có thể nhận diện từ bytecode. Nó không thể bảo đảm phát hiện mọi trường hợp truy cập động, chẳng hạn:

- Reflection với tên class/package được tạo từ chuỗi runtime.
- Tên lớp được tải qua class loader tùy chỉnh.
- Truy cập từ native code/JNI.
- Hành vi bên trong dependency chưa được đưa vào phạm vi phân tích.

Vì vậy, kết quả không có cảnh báo không chứng minh ứng dụng hoàn toàn không đụng JDK internals. Kết hợp phân tích dependency, test trên JDK 17 và kiểm tra cấu hình runtime.

### 8.2. Đọc module descriptor của JAR

Với một JAR modular, có thể xem descriptor:

~~~bash
jar --describe-module --file application.jar
~~~

Nếu JAR không có module descriptor tường minh, công cụ có thể mô tả automatic module hoặc báo thông tin tương ứng. Metadata này giúp xác định tên module để dùng trong `exports`, `opens` hoặc tùy chọn `--add-exports`/`--add-opens`.

## 9. Thay thế API nội bộ bằng API được hỗ trợ

Cách sửa bền vững là thay phụ thuộc vào implementation bằng API công khai có hợp đồng rõ ràng.

| Phụ thuộc hoặc mục đích cũ | Hướng thay thế cần xem xét |
| --- | --- |
| `sun.misc.BASE64Encoder` / `BASE64Decoder` | `java.util.Base64` |
| Lưu metadata theo class mà không cần map có khóa class | `ClassValue<T>` khi phù hợp |
| Truy cập biến có kiểu hoặc thao tác nguyên tử với `Unsafe` | `VarHandle`, `MethodHandles`, `ByteBuffer` hoặc API concurrency phù hợp |
| Reflection vào private field của lớp JDK để đọc trạng thái | Tìm public accessor hoặc API công khai được thiết kế cho nhu cầu đó |
| Truy cập implementation nội bộ của NIO | Dùng `java.nio`, `ByteBuffer`, `FileChannel` và API được tài liệu hóa |
| Tự truy cập nội bộ để xử lý ngày giờ | Dùng `java.time` |

Đây là hướng thay thế theo **mục đích**, không phải ánh xạ một-một. Ví dụ `VarHandle` có thể thay một số thao tác truy cập biến kiểu thấp, nhưng không phải bản sao tổng quát của mọi chức năng `Unsafe`.

### 9.1. Ví dụ: Base64

Code cũ có thể phụ thuộc lớp nội bộ/không được hỗ trợ. Với Java hiện hành, dùng `java.util.Base64`:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

byte[] input = "Java 17".getBytes(StandardCharsets.UTF_8);

String encoded = Base64.getEncoder().encodeToString(input);
byte[] decoded = Base64.getDecoder().decode(encoded);

System.out.println(encoded);
System.out.println(new String(decoded, StandardCharsets.UTF_8));
~~~

API này là API Java SE chính thức và không cần mở package JDK.

### 9.2. Ví dụ: VarHandle

Khi cần thao tác biến có kiểu và ngữ nghĩa truy cập xác định, `VarHandle` là một API công khai trong `java.lang.invoke`:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class Counter {
    private volatile int value;

    private static final VarHandle VALUE;

    static {
        try {
            VALUE = MethodHandles.lookup()
                    .findVarHandle(Counter.class, "value", int.class);
        } catch (ReflectiveOperationException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    public int incrementAndGet() {
        return (int) VALUE.getAndAdd(this, 1) + 1;
    }
}
~~~

`VarHandle` cung cấp các chế độ truy cập có ngữ nghĩa bộ nhớ rõ ràng. Chọn đúng mode (`get`, `set`, `getVolatile`, `compareAndSet`, `getAndAdd`...) theo yêu cầu đồng bộ hóa; không thay mọi thao tác bằng một mode duy nhất.

## 10. Vì sao không nên giữ --add-opens lâu dài?

Một tùy chọn mở module có thể giúp ứng dụng cũ hoạt động trong lúc nâng cấp, nhưng cũng làm giảm hiệu quả của ranh giới encapsulation.

Các rủi ro:

- Thư viện tiếp tục phụ thuộc implementation nội bộ của JDK.
- Nâng cấp JDK có thể làm package, field hoặc hành vi nội bộ thay đổi.
- Quyền reflection sâu rộng hơn mức ứng dụng cần.
- Cấu hình chạy production trở nên khó hiểu và khó kiểm soát.
- Test chỉ pass khi có flag, trong khi môi trường production có thể thiếu flag.

Nếu cần giữ một flag chuyển tiếp:

1. Ghi lại dependency và lỗi cụ thể mà flag giải quyết.
2. Giới hạn module nguồn/package và module đích ở mức hẹp nhất.
3. Đặt flag trong cấu hình khởi chạy có quản lý, không rải rác nhiều nơi.
4. Tạo công việc nâng cấp thư viện hoặc thay API.
5. Kiểm thử sau khi bỏ flag để xác nhận phụ thuộc đã được loại bỏ.
6. Xóa flag khi không còn cần thiết.

Không mở toàn bộ package của `java.base` hoặc tất cả module cho `ALL-UNNAMED` chỉ để làm cho ứng dụng hết lỗi. Cấu hình rộng có thể che giấu nhiều phụ thuộc không liên quan.

## 11. Đóng gói ứng dụng không làm mất strong encapsulation

Việc tạo fat JAR, shaded JAR, executable JAR hoặc runtime image không tự biến JDK internals thành API công khai.

- **Fat/shaded JAR:** gom dependency ứng dụng vào một artifact; không thay đổi module descriptor của `java.base`.
- **Classpath:** ứng dụng ở unnamed module; vẫn chịu ranh giới export/open của các module JDK.
- **Module path:** ứng dụng có module descriptor; quyền truy cập được kiểm soát qua `requires`, `exports`, `opens` và các tùy chọn runtime.
- **jlink runtime image:** tạo runtime chỉ chứa module cần thiết; không phải cơ chế mở các package nội bộ.
- **jpackage:** đóng gói ứng dụng và runtime; không thay thế việc sửa dependency truy cập JDK internals.

Nếu cần `--add-opens` hoặc `--add-exports` để chạy, hãy bảo đảm tùy chọn có mặt trong cấu hình launcher của artifact được triển khai. Đừng chỉ cấu hình trong terminal phát triển rồi giả định người dùng chạy JAR ở nơi khác cũng nhận được flag.

## 12. Quy trình xử lý khi nâng ứng dụng lên Java 17

Có thể áp dụng quy trình sau khi chuyển runtime từ JDK cũ lên JDK 17:

1. **Chạy trên đúng JDK mục tiêu.** Xác nhận cả `java -version` và `javac -version` là JDK 17 trong môi trường build/test/run.
2. **Tìm phụ thuộc nội bộ.** Chạy `jdeps --jdk-internals` trên ứng dụng và các thư viện có thể phân tích.
3. **Tái hiện lỗi.** Phân biệt lỗi biên dịch, `IllegalAccessError`, `InaccessibleObjectException`, lỗi thiếu class và lỗi thiếu method.
4. **Tìm API thay thế.** Ưu tiên API Java SE hoặc API công khai được nhà cung cấp thư viện hỗ trợ.
5. **Nâng cấp dependency.** Dùng phiên bản thư viện tương thích Java 17 và không còn cần truy cập package nội bộ.
6. **Chỉ dùng flag tạm thời nếu bắt buộc.** Chọn đúng `--add-exports` hoặc `--add-opens`, đúng package và module đích.
7. **Kiểm thử không có flag.** Xác nhận ứng dụng và test chạy được sau khi loại bỏ ngoại lệ truy cập.
8. **Kiểm tra artifact đóng gói.** Chạy bằng chính script/container/runtime image được dùng khi triển khai.

Ví dụ các lệnh chẩn đoán cơ bản:

~~~bash
java -version
javac -version
jdeps --jdk-internals application.jar
jar --describe-module --file application.jar
~~~

Không nên dùng `jdeprscan` như công cụ thay thế cho `jdeps --jdk-internals`: công cụ đó tập trung vào API deprecated, trong khi một API nội bộ có thể không được đánh dấu deprecated mà vẫn không được hỗ trợ.

## 13. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Compiler báo package không visible/not exported | Source import kiểu trong package module chưa export | Tìm API công khai; nếu thật sự cần chuyển tiếp, cấu hình `--add-exports` cho compiler |
| `IllegalAccessError` khi chạy | Runtime module không export package cho module của ứng dụng | Nâng dependency hoặc cấu hình `--add-exports` hẹp, tạm thời |
| `InaccessibleObjectException` từ reflection | Package không được mở cho deep reflection | Nâng framework; nếu chưa thể, cân nhắc `--add-opens` đúng package |
| `trySetAccessible()` trả `false` | Caller không có quyền mở thành viên | Kiểm tra module/package và thay cách truy cập |
| `--illegal-access=permit` không sửa được lỗi | Tùy chọn chuyển tiếp không còn mở relaxed access trong Java 17 | Bỏ tùy chọn; sửa dependency hoặc dùng flag cụ thể trong giai đoạn chuyển tiếp |
| Chạy được ở IDE nhưng lỗi trong container | JVM args hoặc JDK thực tế khác nhau | So sánh runtime version và toàn bộ VM options |
| `jdeps` không báo nhưng vẫn có lỗi reflection | Truy cập động không hiện rõ trong bytecode | Kiểm tra stack trace, dependency và cấu hình reflection |
| JAR đóng gói vẫn lỗi | Đóng gói không thay đổi ranh giới module JDK | Sửa dependency và launcher options |
| Một API `sun.*` vẫn truy cập được | Có ngoại lệ hoặc module export package đó | Kiểm tra hợp đồng hỗ trợ; khả năng truy cập không bảo đảm ổn định |
| Mở package quá rộng | Dùng `ALL-UNNAMED` hoặc mở nhiều package không cần thiết | Giới hạn module đích, package và thời gian sử dụng |

## 14. Bài tập thực hành

### Bài 1 — Phân biệt exports và opens

Viết module `com.example.app` có package `com.example.api` và `com.example.model`. Export package API, mở package model cho một module framework được chỉ định. Giải thích vì sao `exports` không thay thế `opens` khi framework cần đọc private field bằng reflection.

### Bài 2 — Quan sát lỗi reflection

Chạy ví dụ `ReflectStringDemo` trên JDK 17 không có VM option. Quan sát `InaccessibleObjectException`. Sau đó chạy với:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED ReflectStringDemo
~~~

Ghi nhận khác biệt và giải thích vì sao đây chỉ là ngoại lệ runtime cho package được chỉ định.

### Bài 3 — Kiểm tra internal API

Chạy:

~~~bash
jdeps --jdk-internals application.jar
~~~

Nếu kết quả có dependency nội bộ, xác định class ứng dụng hoặc thư viện gây ra, rồi tìm API công khai phù hợp.

### Bài 4 — So sánh add-exports và add-opens

Dùng ví dụ `InternalAccessDemo` để tìm hiểu vì sao truy cập kiểu `public` trong package chưa export cần `--add-exports`, còn truy cập private field qua reflection cần `--add-opens`.

### Bài 5 — Gỡ bỏ ngoại lệ

Tạm thêm một `--add-opens` cần thiết cho thư viện cũ, nâng cấp thư viện lên phiên bản hỗ trợ Java 17, rồi chạy lại test và ứng dụng mà không có flag. Xác nhận cấu hình ngoại lệ không còn cần thiết.

## 15. Nguyên tắc cần nhớ

- Java 17 hoàn tất strong encapsulation của JDK internals theo JEP 403.
- API nội bộ không phải hợp đồng tương thích cho ứng dụng; không dựa vào tên lớp hoặc hành vi implementation.
- `exports` cho phép truy cập kiểu/thành viên public; `opens` cho phép deep reflection ở runtime.
- `--add-exports` và `--add-opens` mở đúng package cho module đích được chỉ định; dùng như ngoại lệ chuyển tiếp có kiểm soát.
- `--illegal-access` không còn là cách khôi phục relaxed encapsulation trong Java 17.
- Dùng `jdeps --jdk-internals` để tìm phụ thuộc nội bộ, nhưng nhớ giới hạn của phân tích tĩnh.
- Ưu tiên API Java SE và nâng cấp thư viện để loại bỏ nhu cầu mở package.
- Fat JAR, classpath, module path, `jlink` hay `jpackage` không tự bỏ qua ranh giới module của JDK.

Strong encapsulation giúp ứng dụng phụ thuộc vào hợp đồng công khai thay vì chi tiết triển khai của JDK. Khi nâng lên Java 17, hãy xác định chính xác điểm truy cập bị chặn, thay bằng API được hỗ trợ và chỉ giữ ngoại lệ module ở phạm vi nhỏ trong giai đoạn chuyển tiếp.
