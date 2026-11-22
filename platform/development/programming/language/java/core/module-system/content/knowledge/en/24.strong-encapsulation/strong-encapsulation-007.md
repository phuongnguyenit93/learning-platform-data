# Giảm phụ thuộc vào internal API bằng API công khai

Internal API là các lớp, interface, phương thức hoặc package thuộc phần triển khai nội bộ của JDK, không được cam kết là API công khai ổn định cho ứng dụng. Việc phụ thuộc vào chúng có thể khiến chương trình biên dịch hoặc chạy được trên một JDK nhưng hỏng khi nâng cấp sang JDK khác.

Java Module System tăng cường ranh giới giữa module và package. Từ Java 9, nhiều package nội bộ của JDK không được export cho code bên ngoài. Quá trình đóng gói được siết chặt qua các phiên bản; từ JDK 17, cơ chế mở rộng để truy cập trái phép các package nội bộ đã bị loại bỏ. Cách bền vững là thay thế dependency nội bộ bằng API công khai được hỗ trợ.

## 1. Vì sao cần tránh internal API?

Internal API thường có tên package như sun.*, jdk.internal.* hoặc một số package com.sun.*. Tuy nhiên, không thể kết luận chỉ dựa vào tiền tố package: JDK cũng có những API công khai, được tài liệu hóa trong các package com.sun.*. Cần kiểm tra module, tài liệu API và trạng thái hỗ trợ của từng kiểu.

Rủi ro khi dùng internal API:

- **Không có cam kết tương thích:** JDK có thể đổi tên, di chuyển hoặc xóa kiểu nội bộ giữa các bản phát hành.
- **Bị chặn bởi module system:** package không được export hoặc open có thể gây lỗi biên dịch, IllegalAccessError hoặc InaccessibleObjectException.
- **Phụ thuộc vào chi tiết triển khai:** code có thể dựa trên layout object, field riêng tư, cấu trúc class loader hoặc hành vi không được đặc tả.
- **Khó nâng cấp và kiểm thử:** mỗi lần đổi JDK có thể phải sửa workaround và thêm tùy chọn mở quyền truy cập.
- **Tăng rủi ro bảo mật:** truy cập sâu vào trạng thái nội bộ có thể phá vỡ tính đóng gói và giả định an toàn của thư viện.

Một ứng dụng chạy thành công trên một JDK không chứng minh dependency đó được hỗ trợ. Hãy xem API có được tài liệu hóa trong Java SE API hay JDK API chính thức, module có export package hay không, và tài liệu có cam kết hỗ trợ cho ứng dụng hay không.

## 2. Phân biệt API công khai, API nội bộ và API deprecated

| Loại API | Đặc điểm | Cách xử lý |
|---|---|---|
| Java SE API công khai | Được đặc tả và tài liệu hóa; có cam kết tương thích theo chính sách Java SE | Ưu tiên sử dụng |
| JDK API công khai nhưng không thuộc Java SE | Có tài liệu trong JDK nhưng phạm vi hỗ trợ có thể khác Java SE | Kiểm tra tài liệu và cam kết của API |
| Internal API | Chi tiết triển khai, không có cam kết ổn định cho ứng dụng | Tìm API công khai thay thế |
| Deprecated API | API vẫn có thể công khai nhưng được đánh dấu không nên dùng hoặc có lộ trình loại bỏ | Tìm API thay thế và lập kế hoạch chuyển đổi |

Deprecated không đồng nghĩa với internal. Một API deprecated có thể vẫn là API công khai; ngược lại, internal API có thể chưa được đánh dấu deprecated nhưng vẫn không được hỗ trợ như hợp đồng cho ứng dụng.

Không nên dùng một package name đơn lẻ làm tiêu chí duy nhất. Kiểm tra tài liệu Javadoc, module descriptor, JEP liên quan và kết quả công cụ phân tích dependency.

## 3. Tìm dependency vào JDK internals

### Dùng jdeps

jdeps là công cụ phân tích dependency ở cấp class hoặc module. Tùy chọn --jdk-internals giúp tìm tham chiếu tới JDK internal API trong class hoặc JAR đã biên dịch.

Ví dụ:

~~~bash
jdeps --jdk-internals app.jar
~~~

Phân tích một tập hợp JAR:

~~~bash
jdeps --jdk-internals lib/*.jar
~~~

Chỉ định phiên bản multi-release JAR cần phân tích:

~~~bash
jdeps --jdk-internals --multi-release 17 app.jar
~~~

Nếu ứng dụng có dependency bên ngoài, cung cấp class path phù hợp để jdeps phân tích đầy đủ:

~~~bash
jdeps --jdk-internals --class-path "lib/*" app.jar
~~~

Kết quả thường chỉ ra class nào tham chiếu tới API nội bộ, tên API và module/package chứa nó. Dùng kết quả đó để xác định dependency trực tiếp hay dependency đến từ thư viện bên thứ ba.

jdeps phân tích bytecode. Nó không thể phát hiện mọi trường hợp truy cập được tạo động bằng reflection, tên class ghép từ chuỗi, JNI hoặc native code. Vì vậy, hãy kết hợp với tìm kiếm source code và kiểm thử runtime.

### Tìm trong source code và cấu hình build

Tìm các import và tên thường gặp:

~~~text
sun.
com.sun.
jdk.internal.
Unsafe
ReflectionFactory
SharedSecrets
~~~

Tìm cả cấu hình compiler, JVM arguments và thư viện phụ thuộc. Một ứng dụng có thể không import internal API trực tiếp nhưng vẫn phụ thuộc vào một thư viện sử dụng chúng.

Kiểm tra dependency tree của Maven hoặc Gradle để xác định phiên bản thư viện kéo theo internal API. Nâng cấp thư viện lên phiên bản đã chuyển sang API công khai thường tốt hơn việc tự mở package của JDK cho toàn bộ ứng dụng.

### Kiểm tra lỗi lúc chạy

Một số dependency chỉ xuất hiện khi code chạy đến nhánh sử dụng reflection hoặc class nội bộ. Tìm các lỗi như:

- IllegalAccessError: code không có quyền truy cập kiểu hoặc thành viên theo quy tắc truy cập.
- InaccessibleObjectException: reflection sâu không thể mở thành viên của module/package.
- NoClassDefFoundError hoặc ClassNotFoundException: kiểu nội bộ không còn tồn tại hoặc không thể được tìm thấy.
- NoSuchMethodError hoặc NoSuchFieldError: API/chi tiết triển khai đã thay đổi.

Không nên xử lý các lỗi này bằng cách thêm hàng loạt tùy chọn mở module trước khi xác định class và package thực sự gây lỗi.

## 4. Quy trình thay thế bằng API công khai

Với mỗi internal API được phát hiện, ghi lại mục đích sử dụng thực tế trước khi chọn API thay thế. Hai API có tên gần giống nhau không nhất thiết có cùng ngữ nghĩa, hiệu năng, vòng đời tài nguyên hoặc mô hình bảo mật.

Quy trình đề xuất:

1. **Xác định điểm gọi:** tìm class, phương thức, field hoặc thao tác reflection đang sử dụng internal API.
2. **Hiểu mục đích:** code cần mã hóa dữ liệu, truy cập bộ nhớ, đọc metadata, thao tác class, theo dõi runtime hay làm việc với file?
3. **Tìm API được hỗ trợ:** tra Java SE API, JDK API và hướng dẫn migration chính thức.
4. **So sánh ngữ nghĩa:** kiểm tra cách xử lý lỗi, giới hạn dữ liệu, thread safety, quyền truy cập và vòng đời.
5. **Thay thế tại abstraction phù hợp:** ưu tiên sửa trong adapter hoặc module tích hợp thay vì để internal API lan khắp ứng dụng.
6. **Kiểm thử trên JDK mục tiêu:** xác minh cả kết quả, ngoại lệ, hiệu năng cần thiết và hành vi khi module bị đóng gói.
7. **Xóa workaround:** sau khi migration hoàn tất, bỏ các tùy chọn add-exports/add-opens và dependency không còn cần thiết.

## 5. Ví dụ các hướng thay thế phổ biến

Các ví dụ dưới đây là hướng migration thường gặp. Hãy xác minh yêu cầu cụ thể của ứng dụng trước khi thay thế.

| Internal API hoặc cách làm cũ | API công khai nên xem xét | Ghi chú |
|---|---|---|
| sun.misc.BASE64Encoder / BASE64Decoder | java.util.Base64 | Có encoder/decoder cho Basic, URL và MIME |
| com.sun.image.codec.jpeg | javax.imageio.ImageIO | Dùng ImageIO và ImageReader/ImageWriter phù hợp |
| sun.misc.Unsafe cho truy cập biến có kiểm soát | java.lang.invoke.VarHandle | Hỗ trợ truy cập biến với memory ordering và atomic operation |
| Unsafe cho cấp phát/truy cập bộ nhớ ngoài heap | java.lang.foreign.MemorySegment và Arena | Foreign Function & Memory API ổn định từ JDK 22; quản lý lifetime rõ ràng |
| Reflection vào field riêng tư của JDK | API công khai được thiết kế cho thao tác đó | Không có API thay thế chung cho mọi field nội bộ |
| Đọc cấu trúc class hoặc module bằng cách phân tích implementation | java.lang.classfile (nếu JDK mục tiêu hỗ trợ) hoặc công cụ bytecode có API được hỗ trợ | Chọn theo phiên bản JDK và yêu cầu tương thích |
| Theo dõi thống kê runtime bằng cấu trúc nội bộ | java.lang.management, JFR hoặc API monitoring được tài liệu hóa | Chọn API đúng loại dữ liệu cần quan sát |

### Base64

Code cũ có thể dùng lớp sun.misc.BASE64Encoder:

~~~java
// Cách cũ: phụ thuộc JDK internal API
// BASE64Encoder encoder = new BASE64Encoder();
// String encoded = encoder.encode(bytes);
~~~

Thay bằng API chuẩn:

~~~java
import java.util.Base64;

String encoded = Base64.getEncoder().encodeToString(bytes);
byte[] decoded = Base64.getDecoder().decode(encoded);
~~~

Nếu dữ liệu dùng trong URL, chọn getUrlEncoder() và getUrlDecoder(). Nếu cần định dạng MIME với line separator, chọn getMimeEncoder() và getMimeDecoder(). Đừng thay decoder một cách máy móc nếu định dạng đầu vào có quy tắc riêng.

### Image I/O

Thay các lớp JPEG codec cũ bằng javax.imageio:

~~~java
import java.awt.image.BufferedImage;
import java.io.File;
import javax.imageio.ImageIO;

BufferedImage image = ImageIO.read(new File("input.jpg"));
if (image == null) {
    throw new IllegalArgumentException("Không hỗ trợ định dạng ảnh");
}

boolean written = ImageIO.write(image, "jpg", new File("output.jpg"));
if (!written) {
    throw new IllegalStateException("Không có writer phù hợp");
}
~~~

ImageIO.read() có thể trả về null nếu không tìm được reader phù hợp. ImageIO.write() trả về boolean để biểu thị có writer hỗ trợ định dạng được yêu cầu hay không. Ứng dụng cần kiểm tra các trường hợp này thay vì giả định file luôn đọc/ghi thành công.

### Truy cập biến bằng VarHandle

Nếu code dùng Unsafe chỉ để đọc, ghi hoặc cập nhật biến với memory ordering, xem xét VarHandle:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

final class Counter {
    private volatile int value;

    private static final VarHandle VALUE;

    static {
        try {
            VALUE = MethodHandles.lookup()
                    .findVarHandle(Counter.class, "value", int.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    int incrementAndGet() {
        return (int) VALUE.getAndAdd(this, 1) + 1;
    }
}
~~~

VarHandle cung cấp các access mode như get, set, getVolatile, compareAndSet và getAndAdd tùy loại biến và kiểu truy cập được hỗ trợ. Hãy chọn đúng memory semantics; không phải mọi thao tác Unsafe đều có phép thay thế một-một bằng VarHandle.

### Bộ nhớ ngoài heap

Nếu mục tiêu là làm việc với vùng nhớ native, JDK 22 trở lên có Foreign Function & Memory API ổn định. MemorySegment biểu diễn vùng nhớ với giới hạn và lifetime rõ ràng; Arena quản lý thời gian sống của allocation.

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(8);

    segment.set(ValueLayout.JAVA_LONG, 0, 42L);
    long value = segment.get(ValueLayout.JAVA_LONG, 0);

    System.out.println(value);
}
~~~

Khi Arena đóng, các segment thuộc arena đó không còn được sử dụng. Điều này giúp thể hiện quyền sở hữu và vòng đời bộ nhớ rõ hơn. Không chuyển đổi sang MemorySegment nếu code chỉ cần mảng byte hoặc ByteBuffer; dùng abstraction đơn giản nhất đáp ứng yêu cầu.

## 6. Khi cần reflection, phân biệt exports và opens

Module system có hai khái niệm thường bị nhầm:

- **exports** cho phép module khác truy cập các kiểu public trong package theo quy tắc module.
- **opens** cho phép deep reflection vào thành viên không public của package ở runtime.

Một package được export không đồng nghĩa với việc private field của nó có thể được mở bằng reflection. Ngược lại, opens không làm cho package trở thành API có thể import và gọi trực tiếp lúc biên dịch.

Nếu cần mở package trong giai đoạn migration, có thể dùng:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

Tùy chọn này mở package java.lang của module java.base cho các class thuộc unnamed module. Nó chỉ ảnh hưởng quyền truy cập reflection sâu ở runtime cho package được chỉ định.

Nếu code cần truy cập các kiểu public trong package chưa export, --add-exports là tùy chọn khác:

~~~bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED -jar app.jar
~~~

Với javac, có thể truyền --add-exports tương ứng khi biên dịch:

~~~bash
javac --add-exports java.base/sun.nio.ch=ALL-UNNAMED \
      -d out src/example/Main.java
~~~

Các ví dụ trên chỉ minh họa cách tạo cầu nối tương thích. Không nên xem chúng là giải pháp migration cuối cùng. Mở package nội bộ không biến API đó thành API được hỗ trợ và có thể làm ứng dụng tiếp tục phụ thuộc vào chi tiết JDK.

Nếu caller là named module, thay ALL-UNNAMED bằng tên module đích phù hợp. Chỉ mở hoặc export đúng package và đúng module cần thiết; tránh cấp quyền rộng cho toàn bộ ứng dụng.

## 7. Vai trò và giới hạn của --illegal-access

Trong các JDK đầu tiên sau Java 9, tùy chọn --illegal-access từng hỗ trợ một giai đoạn chuyển tiếp cho một số truy cập reflection từ code cũ vào package nội bộ của JDK.

Từ JDK 16, strong encapsulation được áp dụng mặc định rộng hơn. Từ JDK 17, --illegal-access không còn khôi phục cơ chế mở rộng như trước; tùy chọn này chỉ được giữ để tương thích cú pháp và phát cảnh báo, không mở lại các package nội bộ.

Vì vậy, không nên thêm:

~~~bash
java --illegal-access=permit -jar app.jar
~~~

để sửa ứng dụng trên JDK hiện đại. Hãy xác định package cụ thể và chuyển sang API công khai. Nếu đang cần chạy tạm một ứng dụng cũ, dùng --add-exports hoặc --add-opens có phạm vi hẹp theo lỗi thực tế, sau đó lập kế hoạch loại bỏ chúng.

## 8. Lập kế hoạch migration cho ứng dụng lớn

Với ứng dụng có nhiều module hoặc thư viện bên thứ ba, không nên thay toàn bộ internal API trong một lần mà không có danh sách dependency và test.

Có thể phân chia công việc theo các nhóm:

| Nhóm | Việc cần làm |
|---|---|
| Source code của ứng dụng | Tìm import, reflection, MethodHandles và tên class nội bộ |
| Dependency trực tiếp | Nâng cấp thư viện hoặc thay thế implementation |
| Dependency bắc cầu | Xác định thư viện nào kéo theo internal API; trao đổi với nhà cung cấp nếu cần |
| JVM arguments | Liệt kê --add-exports, --add-opens và tùy chọn legacy |
| Kiểm thử | Chạy trên JDK thấp nhất và cao nhất được hỗ trợ |
| Phát hành | Xóa workaround không còn cần thiết, xác minh launch script và tài liệu triển khai |

Đưa việc kiểm tra internal API vào CI:

~~~bash
jdeps --jdk-internals --class-path "lib/*" build/app.jar
~~~

Có thể lưu output và thất bại build khi xuất hiện dependency mới, tùy chính sách của dự án. Nếu chưa thể chặn ngay, ít nhất hãy ghi nhận baseline và theo dõi các dependency tăng thêm.

Với thư viện bên thứ ba, ưu tiên nâng cấp lên phiên bản có hỗ trợ JDK mục tiêu. Nếu chưa có bản thay thế, cô lập thư viện trong adapter hoặc module riêng để phần còn lại của ứng dụng không phụ thuộc trực tiếp vào internal API.

## 9. Checklist kiểm thử sau migration

Sau khi thay thế, cần kiểm tra các hành vi mà code cũ từng cung cấp:

- Kết quả nghiệp vụ có tương đương với yêu cầu ban đầu không?
- Các trường hợp null, dữ liệu rỗng, dữ liệu lớn và dữ liệu lỗi được xử lý đúng không?
- Memory ordering, atomicity hoặc thread safety có còn đúng không nếu thay Unsafe?
- Native memory và resource có được giải phóng đúng lifetime không?
- Reflection có còn hoạt động trong môi trường module thực tế không?
- Ứng dụng chạy được trên các JDK đã cam kết hỗ trợ không?
- Có còn tham chiếu internal API trong output của jdeps không?
- Có thể bỏ các tùy chọn --add-exports và --add-opens không?
- Các launch script, container image và môi trường CI có dùng cùng cấu hình JDK không?

Đặc biệt, hãy chạy test với module path nếu ứng dụng là modular. Một ứng dụng chạy trên classpath có thể che giấu vấn đề readability, exports hoặc opens mà khi chuyển sang module path mới xuất hiện.

## 10. Ghi nhớ

Strong encapsulation bảo vệ ranh giới giữa API được hỗ trợ và chi tiết triển khai của JDK. Cách migration bền vững là phát hiện dependency bằng jdeps và tìm kiếm source, xác định mục đích sử dụng, rồi thay bằng API công khai phù hợp như Base64, ImageIO, VarHandle, MemorySegment hoặc API quản lý runtime.

--add-exports và --add-opens chỉ nên là cầu nối có phạm vi hẹp trong giai đoạn chuyển đổi. Chúng không tạo cam kết tương thích cho internal API. Sau migration, hãy bỏ workaround, kiểm tra bytecode và chạy test trên các JDK mục tiêu.

## Tài liệu tham khảo

- JEP 403 — Strongly Encapsulate JDK Internals: https://openjdk.org/jeps/403
- JEP 396 — Strongly Encapsulate JDK Internals by Default: https://openjdk.org/jeps/396
- Oracle Java Platform, jdeps tool: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html
- Java API — VarHandle: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/VarHandle.html
- Java API — Foreign Function & Memory: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/foreign/package-summary.html
