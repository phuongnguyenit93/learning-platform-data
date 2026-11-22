# Phân biệt API được hỗ trợ với package sun.*, com.sun.* và jdk.internal.*

Khi nâng cấp Java, các lời gọi tới API của JDK thường cần được xem xét ở hai góc độ: **lớp hoặc phương thức có tồn tại trong JDK hiện tại hay không**, và **ứng dụng có được phép phụ thuộc lâu dài vào API đó hay không**. Hai câu hỏi này không tương đương. Một lớp tồn tại trong runtime, có thể import, thậm chí có thể gọi được khi thêm JVM flag, vẫn có thể thuộc API nội bộ không có cam kết tương thích.

Trong các dự án lâu năm, mã nguồn hoặc thư viện bên thứ ba có thể sử dụng những package bắt đầu bằng `sun.*`, `com.sun.*` hoặc `jdk.internal.*`. Đây là những dấu hiệu cần điều tra, nhưng **không nên kết luận rằng mọi `com.sun.*` đều là API nội bộ**. Một số API JDK có tên `com.sun.*` được công bố và hỗ trợ trong phạm vi JDK, chẳng hạn API HTTP server hoặc API cây cú pháp của compiler. Ngược lại, nhiều package `sun.*` và `jdk.internal.*` không dành cho ứng dụng thông thường, có thể đổi hoặc bị hạn chế khi nâng Java.

Bài học này trình bày cách xác định API được hỗ trợ, những ngoại lệ quan trọng, tác động của Java Platform Module System (JPMS), cách phát hiện phụ thuộc nội bộ bằng công cụ và hướng chuyển đổi mã để migration ít rủi ro hơn.

## 1. "Có trong JDK" không có nghĩa "được hỗ trợ"

JDK bao gồm nhiều thành phần hơn tập API Java SE mà lập trình viên thường sử dụng. Ngoài những package quen thuộc như `java.lang`, `java.util`, `java.nio` hoặc `java.net`, một bản JDK còn có compiler, debugger, monitoring tools, implementation classes, native integration và các tiện ích riêng của JDK.

Có thể phân biệt bốn tầng như sau:

| Tầng | Ví dụ | Mức độ cam kết |
|---|---|---|
| API Java SE chuẩn hóa | `java.util.List`, `java.nio.file.Files`, `java.lang.invoke.MethodHandles` | Có hợp đồng API qua Java SE specification và tài liệu tương ứng |
| API JDK được tài liệu hóa nhưng không thuộc Java SE | `com.sun.source.tree`, `com.sun.net.httpserver`, một số `com.sun.management` | Có API contract trong phạm vi JDK, nhưng cần cân nhắc tính di động giữa các JDK và môi trường |
| API mang tính triển khai hoặc nội bộ | Nhiều `sun.*`, `com.sun.*.internal.*`, `jdk.internal.*` | Không nên xem là hợp đồng công khai ổn định của ứng dụng |
| Cơ chế truy cập tạm thời | `--add-exports`, `--add-opens` hoặc API trong `jdk.unsupported` | Có thể giúp chạy mã legacy nhưng không tự tạo cam kết ổn định cho API nội bộ |

Không dùng một quy tắc đơn giản như “tên bắt đầu bằng `com.sun` là sai” hoặc “có thể import là an toàn”. Kết luận cần dựa vào **tài liệu chính thức của phiên bản JDK mục tiêu, module sở hữu package, export/open policy và hợp đồng API**.

Khái niệm “được hỗ trợ” cũng cần đặt trong phạm vi cụ thể:

- **Java SE portable API:** thường phù hợp cho ứng dụng muốn chạy trên nhiều JDK tuân thủ Java SE.
- **Documented JDK-specific API:** có thể phù hợp cho công cụ hoặc ứng dụng chủ đích phụ thuộc JDK, nhưng không nhất thiết portable sang mọi môi trường Java.
- **Implementation detail:** có thể tồn tại nhưng không được bảo đảm cho mã ứng dụng, kể cả khi compiler đang cho phép truy cập.

## 2. Ba họ package dễ nhầm

### 2.1. sun.*

Nhiều lớp `sun.*` xuất phát từ implementation của JDK hoặc HotSpot. Ví dụ các mã cũ thường tham chiếu `sun.misc.Unsafe`, `sun.security.x509` hoặc những tiện ích không được công bố như Java SE API.

Đặc điểm cần nhớ:

- Package có thể hiện diện trên một JDK nhưng không có trên JDK hoặc vendor khác.
- Chữ ký và cách hoạt động có thể thay đổi không theo quy tắc tương thích API công khai.
- JPMS có thể không export hoặc open package cho ứng dụng.
- Một số **critical internal APIs** được giữ có thể truy cập qua module `jdk.unsupported` để hỗ trợ chuyển tiếp; điều đó không làm chúng trở thành API Java SE ổn định.

Ví dụ, `sun.misc.Unsafe` có thể được nhìn thấy trong `jdk.unsupported` trên nhiều JDK hiện đại. Tuy nhiên, đây vẫn là API nguy cơ cao và không nên được chọn làm phương án mặc định cho dự án mới.

### 2.2. com.sun.*

`com.sun.*` là trường hợp cần phân loại thận trọng nhất. Có cả **API JDK được tài liệu hóa** và **implementation internals** dùng tiền tố này.

Ví dụ:

| Package/API | Bối cảnh | Cách đánh giá |
|---|---|---|
| `com.sun.net.httpserver.HttpServer` | HTTP server API trong module `jdk.httpserver` | API JDK được tài liệu hóa, không thuộc API Java SE phổ quát |
| `com.sun.source.tree.Tree` | Compiler Tree API trong module `jdk.compiler` | API JDK được tài liệu hóa dành cho công cụ phân tích mã |
| `com.sun.source.util.JavacTask` | API hỗ trợ phân tích với compiler | API công khai được tài liệu hóa trong phạm vi JDK |
| `com.sun.management.OperatingSystemMXBean` | Mở rộng management API trong `jdk.management` | JDK-specific management API được tài liệu hóa |
| `com.sun.tools.javac.tree.JCTree` | Cấu trúc cây nội bộ của javac | Không nên xem là hợp đồng ổn định như `com.sun.source.tree` |
| `com.sun.org.apache.xerces.internal.*` | Lớp triển khai XML nội bộ, được đóng gói trong JDK | Không phụ thuộc trực tiếp như API ứng dụng |

Từ bảng có thể thấy: **tiền tố `com.sun` không quyết định API có được hỗ trợ hay không**. Phải xác định package cụ thể và xem tài liệu API dành cho release đang chạy.

Đặc biệt, `com.sun.source.*` và `com.sun.tools.javac.*` không đồng nghĩa. Một bên có các compiler API được tài liệu hóa; bên kia chứa nhiều cấu trúc nội bộ mà công cụ như annotation processor/AST transformer có thể phụ thuộc và dễ bị vỡ khi nâng JDK.

### 2.3. jdk.internal.*

Package `jdk.internal.*` thể hiện rõ mục đích triển khai nội bộ của JDK. Các thành phần trong đó không nên được ứng dụng thông thường import hoặc truy cập qua reflection.

Ví dụ tên lớp bắt đầu với `jdk.internal.misc` có thể gợi ý việc truy cập JDK internals. Dù tìm thấy chúng trong runtime image, ứng dụng không nên dựa vào sự tồn tại hoặc layout của các lớp này.

Các vấn đề có thể xuất hiện:

- Compiler báo package không visible vì module không export.
- Runtime gây `IllegalAccessError` hoặc lỗi liên kết khác.
- Reflection ném `InaccessibleObjectException` do package không open.
- Lớp hoặc field nội bộ thay đổi qua JDK version.

Không nên “sửa” bằng cách đổi từ `sun.misc.*` sang `jdk.internal.*` chỉ vì cùng chức năng bên trong JDK. Đây thường là chuyển từ một phụ thuộc nội bộ sang phụ thuộc nội bộ khác, không phải migration sang API được hỗ trợ.

## 3. Phương pháp nhận biết API được hỗ trợ

Thay vì xét tên package, hãy xác định năm thông tin.

### 3.1. API có tài liệu và hợp đồng công khai không?

Tra cứu API documentation của JDK mục tiêu. Một API được tài liệu hóa có mô tả hành vi, phạm vi dùng, điều kiện ngoại lệ và module/package chính thức thường là lựa chọn đáng tin cậy hơn một implementation class tìm được qua decompiler.

Nếu API thuộc Java SE, có thêm căn cứ về tính chuẩn hóa. Nếu là JDK-specific, cần ghi rõ yêu cầu phụ thuộc vào JDK và những môi trường triển khai được hỗ trợ.

### 3.2. Package thuộc module nào?

Ví dụ:

- `java.util` thuộc `java.base`.
- `com.sun.net.httpserver` thuộc `jdk.httpserver`.
- `com.sun.source.tree` thuộc `jdk.compiler`.
- `com.sun.management` có API trong `jdk.management`.
- `sun.misc.Unsafe` nằm trong `jdk.unsupported` ở những JDK có module này.

Biết module giúp xem nó có trong runtime image, có được resolve và package có export/open phù hợp không.

### 3.3. Package có export cho caller không?

Một named module có thể export package cho tất cả module hoặc chỉ một tập module được chỉ định. Package không export không phải API mà ứng dụng có thể truy cập trực tiếp từ ngoài theo quy tắc JPMS.

Tuy nhiên, **export không tự biến mọi lớp thành hợp đồng Java SE**. Một package xuất hiện trong module `jdk.unsupported` là ví dụ cần cân nhắc: quyền truy cập và sự ổn định của API là hai chuyện khác nhau.

### 3.4. API có phụ thuộc implementation/vendor không?

Nếu dùng JDK-specific API, cần xác định nó tồn tại và được hỗ trợ trên những JDK vendor/runtime nào. Một custom runtime image có thể không chứa module JDK tùy chọn như `jdk.httpserver`, dù ứng dụng build được trên full JDK.

### 3.5. Có public API thay thế không?

Khi phát hiện API nội bộ, hãy hỏi mục đích kỹ thuật mà nó đang phục vụ: Base64, reflection, truy cập memory, certificate, XML parser, class loading, management hay compiler AST. Thường có API Java SE/JDK documented hoặc thư viện được duy trì thay thế.

## 4. Khác biệt giữa module readability, exports và opens

Từ Java 9, JPMS thêm ranh giới module. Ba khái niệm thường bị nhầm:

- **Readability:** module A có thể đọc module B trong module graph.
- **Exports:** package trong module B có thể được module A truy cập ở mức public API, nếu Java access rules khác cũng cho phép.
- **Opens:** package cho phép deep reflection từ module khác theo phạm vi khai báo.

Ví dụ module ứng dụng:

~~~java
module com.example.orders {
    requires java.sql;

    exports com.example.orders.api;
    opens com.example.orders.model;
}
~~~

Ở đây `requires java.sql` liên quan readability, `exports` công bố public API trong package `api`, còn `opens` cho phép reflective access tới package `model`.

Với ứng dụng chạy classpath, các class thường thuộc unnamed module. Chúng không cần `module-info.java` để chạy, nhưng vẫn phải tuân thủ việc package nội bộ của **JDK named modules** có được export/open cho caller hay không.

Bảng phân biệt:

| Tình huống | `exports` | `opens` |
|---|---|---|
| Compile code truy cập public type qua import | Cần package được export phù hợp | Không thay cho export thông thường |
| Code thường truy cập public method | Cần khả năng access theo Java/JPMS | Không phải giải pháp chính |
| Reflection gọi public member của public type trong exported package | Có thể đủ nếu các điều kiện Java khác thỏa | Không nhất thiết cần |
| `setAccessible(true)` vào private field của package trong named module | Export đơn thuần thường không đủ | Cần package open phù hợp hoặc cơ chế được cho phép |

Điều này giải thích tại sao thay `--add-exports` bằng `--add-opens` hoặc ngược lại mà không hiểu lỗi thường không hiệu quả.

## 5. Ví dụ: cùng một ứng dụng nhưng hành vi reflection khác

Ví dụ minh họa:

~~~java
import java.lang.reflect.Field;

public class ReflectionExample {
    public static void main(String[] args) throws Exception {
        Field field = String.class.getDeclaredField("value");
        field.setAccessible(true);
        System.out.println(field.getType());
    }
}
~~~

Trên JDK hiện đại có strong encapsulation, `setAccessible(true)` ở đây có thể thất bại với thông báo tương tự:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make field ... accessible:
module java.base does not "opens java.lang" to unnamed module
~~~

Đây không phải lỗi thiếu class hay lỗi source syntax. Vấn đề là ứng dụng cố truy cập một thành viên private bên trong `java.base` từ ngoài module.

Cách khắc phục đúng không phải mặc định mở `java.lang`. Cần xét **vì sao ứng dụng cần đọc dữ liệu private của `String`**. Nếu mục tiêu chỉ là xử lý chuỗi, hãy dùng public methods trên `String`. Với những thư viện serializer cũ cần deep reflection, ưu tiên nâng bản đã tương thích JDK trước.

Một workaround ở mức JVM:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED \
     -cp "app.jar:lib/*" com.example.Main
~~~

Flag có thể cho phép deep reflection trong điều kiện cụ thể, nhưng cũng làm tăng quyền truy cập vào package. Nó không cam kết layout private của `String` sẽ giữ nguyên trong tương lai.

## 6. --add-exports và --add-opens không làm API nội bộ thành API ổn định

Trong giai đoạn chuyển tiếp, các tùy chọn JVM có thể giúp một dependency cũ hoạt động.

### 6.1. --add-exports

Ví dụ một thư viện legacy dùng public type trong package không export:

~~~bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED \
     -cp "app.jar:lib/*" com.example.Main
~~~

Tùy chọn mở quyền truy cập tới public types của package được chỉ rõ cho unnamed modules. Nó không tự cho phép truy cập private member bằng deep reflection.

Nếu mã nguồn trực tiếp import package nội bộ, bước compile có thể cũng yêu cầu cấu hình export tương ứng. Một cấu hình compile có thể khác cấu hình runtime; chỉ có compile thành công chưa chứng minh class được nạp hợp lệ trên production JVM.

### 6.2. --add-opens

Ví dụ:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED \
     -cp "app.jar:lib/*" com.example.Main
~~~

Tùy chọn cho phép deep reflection theo phạm vi đã chỉ định. Nó không thay thế một public API đã bị xóa hoặc đảm bảo cấu trúc field/method private còn tồn tại.

### 6.3. ALL-UNNAMED nghĩa là gì?

`ALL-UNNAMED` nhắm tới unnamed modules, thường gồm mã được nạp từ classpath. Điều này hữu ích trong ứng dụng legacy chưa có `module-info.java`. Nhưng nó cũng có nghĩa quyền được cấp cho **tất cả** unnamed modules theo cơ chế đó, không chỉ một JAR cụ thể.

Nếu hệ thống đã modularize, có thể chọn tên module đích cụ thể thay cho `ALL-UNNAMED` để thu hẹp phạm vi, khi kiến trúc và công cụ hỗ trợ.

### 6.4. Giới hạn và rủi ro

- Flags là thay đổi cấu hình quyền truy cập, không phải thay thế API.
- Package nội bộ có thể đổi, vì vậy flag cũ không đảm bảo thư viện vẫn hoạt động.
- Các flags cần thống nhất giữa local, CI, integration test và production.
- Một workaround không được để ẩn vĩnh viễn trong IDE hoặc launch script cá nhân.
- Mục tiêu dài hạn vẫn là cập nhật thư viện hoặc loại bỏ dependency vào internals.
- Với javac, việc dùng `--release` có các ràng buộc với `--add-exports` của system modules; không nên dựa vào cách “vừa ép release cũ, vừa mở JDK internals” để tạo artifact portable.

## 7. Java 8, Java 9, Java 16 và Java 17: vì sao migration gặp lỗi?

Khi nâng JDK, đặc biệt từ JDK 8 lên các release mới, hành vi truy cập API nội bộ có những thay đổi quan trọng:

| Giai đoạn | Ý nghĩa với ứng dụng legacy |
|---|---|
| JDK 8 | Chưa có JPMS; nhiều thư viện từng truy cập internals mà không bị module boundary chặn |
| JDK 9 | JPMS xuất hiện, phân biệt modules/exports/opens; có cơ chế nới lỏng cho một số reflective access trong giai đoạn chuyển tiếp |
| JDK 11 | Một số Java EE/CORBA modules từng được JDK 8 cung cấp đã bị loại bỏ; phải bổ sung dependency phù hợp |
| JDK 16 | Strong encapsulation trở thành mặc định ở phạm vi rộng hơn, làm lộ thêm lỗi deep reflection |
| JDK 17 | JEP 403 siết strong encapsulation đối với nhiều JDK internals; không còn dựa vào `--illegal-access` để khôi phục nới lỏng như trước |

Điều này không có nghĩa mọi API `sun.*` biến mất vào JDK 17. Một số critical internals vẫn được cung cấp qua `jdk.unsupported`. Nhưng **khả năng truy cập được** không đồng nghĩa **hợp đồng tương thích được hỗ trợ**.

Một ứng dụng có thể chạy trên JDK 11 với cảnh báo illegal reflective access, rồi thất bại khi chuyển JDK 17. Việc loại bỏ warnings bằng cách im lặng log không giải quyết bản chất vấn đề; cần sửa đường truy cập hoặc dependency.

## 8. Các ví dụ thay thế API nội bộ thường gặp

Thay thế cần dựa trên **chức năng thực sự**, không dựa vào tên lớp gần giống. Bảng sau mô tả hướng ưu tiên:

| Phụ thuộc cũ hoặc mục đích | Hướng thay thế | Lưu ý |
|---|---|---|
| `sun.misc.BASE64Encoder` / decoder nội bộ | `java.util.Base64` | Chọn Basic, URL-safe hoặc MIME theo định dạng dữ liệu |
| `sun.misc.Unsafe` để đọc/ghi biến đồng thời | `VarHandle`, `Atomic*`, `java.util.concurrent` | Kiểm tra memory ordering và atomicity |
| `sun.misc.Cleaner` hoặc cơ chế dọn tài nguyên nội bộ | `java.lang.ref.Cleaner` và `AutoCloseable` | Ưu tiên đóng tài nguyên chủ động; cleaner chỉ là backstop |
| `sun.security.x509.*` để thao tác certificate | `java.security`, `java.security.cert`, `javax.net.ssl` và thư viện X.509 được duy trì | Java SE có API đọc/kiểm chứng, nhưng thao tác phát hành certificate có thể cần thư viện chuyên dụng |
| `com.sun.org.apache.xerces.internal.*` | `javax.xml.parsers`, `org.w3c.dom`, `javax.xml.transform` hoặc thư viện XML công khai | Không phụ thuộc vào parser implementation được đóng gói trong JDK |
| `com.sun.tools.javac.tree.JCTree` để duyệt source | `com.sun.source.tree` / `com.sun.source.util` và `javax.lang.model` | API cây dành cho phân tích; việc sửa AST nội bộ có thể không có API công khai tương đương |
| Internal direct-buffer hoặc off-heap API | `ByteBuffer`, `VarHandle`, Foreign Function & Memory API hoặc thư viện phù hợp | Lựa chọn phụ thuộc mức Java, yêu cầu native memory và vòng đời vùng nhớ |
| Internal thread/class-loading helpers | `Thread`, `ClassLoader`, `ServiceLoader`, `MethodHandles` | Không phải mọi internal primitive đều có thay thế 1-1 |

Bảng chỉ nêu **đường hướng migration**, không có nghĩa mọi API thay thế luôn tương đương từng bit về semantics. Với concurrent code, native memory, cryptography và serialization, khác biệt về ordering, lifecycle hoặc security có thể rất quan trọng.

## 9. Ví dụ chuyển từ sun.misc.BASE64Encoder sang java.util.Base64

Một mã legacy có thể phụ thuộc vào encoder nội bộ để tạo Base64. Giải pháp hiện đại là API Java SE `java.util.Base64`.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public final class TokenEncoding {

    public static String encode(String input) {
        byte[] raw = input.getBytes(StandardCharsets.UTF_8);

        return Base64.getEncoder().encodeToString(raw);
    }

    public static String decode(String encoded) {
        byte[] raw = Base64.getDecoder().decode(encoded);

        return new String(raw, StandardCharsets.UTF_8);
    }
}
~~~

`Base64` được cung cấp từ Java 8. Nếu định dạng cũ có xuống dòng hoặc dùng ký tự URL-safe, hãy chọn:

- `Base64.getMimeEncoder()` hoặc `getMimeDecoder()` cho trường hợp cần xử lý dòng theo MIME.
- `Base64.getUrlEncoder()` hoặc `getUrlDecoder()` cho bảng ký tự URL-safe.
- `Base64.getEncoder()` cho dạng Basic không chèn xuống dòng.

Không thay encoder mà bỏ qua định dạng cũ trong database, token hoặc giao thức bên ngoài. Nên có test round-trip và test với dữ liệu thực tế từ version trước, vì khác biệt whitespace/padding có thể làm client không đọc được payload.

## 10. Ví dụ thay Unsafe bằng VarHandle khi phù hợp

Một số thư viện cũ dùng `sun.misc.Unsafe` để làm compare-and-swap trên field. Java cung cấp `VarHandle` từ Java 9 và các primitive đồng thời khác trong `java.util.concurrent`.

Ví dụ class đếm truy cập:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public final class VisitCounter {
    private volatile int count;

    private static final VarHandle COUNT;

    static {
        try {
            COUNT = MethodHandles.lookup()
                    .findVarHandle(
                        VisitCounter.class,
                        "count",
                        int.class
                    );
        } catch (ReflectiveOperationException error) {
            throw new ExceptionInInitializerError(error);
        }
    }

    public void increment() {
        COUNT.getAndAdd(this, 1);
    }

    public int value() {
        return (int) COUNT.getVolatile(this);
    }
}
~~~

Ví dụ minh họa một thao tác atomic trên field với API công khai. Trong nhiều ứng dụng, `AtomicInteger` hoặc `LongAdder` sẽ đơn giản hơn:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public final class SimpleCounter {
    private final AtomicInteger count = new AtomicInteger();

    public void increment() {
        count.incrementAndGet();
    }

    public int value() {
        return count.get();
    }
}
~~~

Không được thay mọi thao tác `Unsafe` một cách máy móc. `Unsafe` bao gồm nhiều khả năng khác nhau: native memory, array layout, object field offset, fence, constructor bypass và các thao tác chuyên biệt. Chuyển đổi phải xem xét chính xác memory ordering, race condition, lifecycle và baseline Java được hỗ trợ.

## 11. Cleaner, tài nguyên native và vòng đời đối tượng

Legacy code đôi khi dùng API cleanup nội bộ để giải phóng tài nguyên khi đối tượng không còn được tham chiếu. Có thể cân nhắc `java.lang.ref.Cleaner` từ Java 9 khi cần fallback cleanup, nhưng nguyên tắc trước tiên là **đóng tài nguyên chủ động**.

Ví dụ ưu tiên `AutoCloseable`:

~~~java
public final class ResourceClient implements AutoCloseable {
    private boolean closed;

    public void use() {
        if (closed) {
            throw new IllegalStateException("Client is closed");
        }
        // Thao tác trên tài nguyên
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            // Giải phóng tài nguyên thật tại đây
        }
    }
}
~~~

Phía gọi:

~~~java
try (ResourceClient client = new ResourceClient()) {
    client.use();
}
~~~

Cleaner có thể hỗ trợ khi tài nguyên bị quên đóng, nhưng không đảm bảo chạy ngay lập tức hoặc đúng thời điểm để đáp ứng tính đúng đắn nghiệp vụ. Nếu dọn tài nguyên là điều kiện an toàn, nên thiết kế ownership và close semantics rõ ràng.

## 12. Compiler APIs: com.sun.source khác com.sun.tools.javac

Trong chương Reflection và API nội bộ, nhóm công cụ đọc source Java thường gây nhầm lẫn vì cùng tiền tố `com.sun`.

Một công cụ phân tích source có thể sử dụng các API được tài liệu hóa:

~~~java
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.Tree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.TreeScanner;
~~~

Các API thuộc `jdk.compiler` giúp truy cập mô hình cây của source trong phạm vi hợp đồng đã công bố. Cần compiler/JDK phù hợp và có thể cần khai báo `requires jdk.compiler;` khi viết named module.

Trong khi đó, các loại như:

~~~java
import com.sun.tools.javac.tree.JCTree;
~~~

thường nằm trong phần implementation javac. Một annotation processor hoặc plugin truy cập chúng có thể lỗi khi compiler đổi field hoặc AST representation, kể cả khi source nghiệp vụ không đổi.

Ví dụ rủi ro:

~~~text
java.lang.NoSuchFieldError: ...
    at some.processor.compiler.InternalAdapter...
~~~

Lỗi có thể do bản processor cũ không hỗ trợ JDK mới. Không nên sửa bằng cách thêm một package export vô điều kiện; nếu field nội bộ đã biến mất, flag export không thể khôi phục field đó.

Khi cần sinh source, ưu tiên annotation processing API `javax.annotation.processing`, `javax.lang.model` và `Filer`. Khi cần phân tích cú pháp, dùng `com.sun.source.*` trong phạm vi API được hỗ trợ hoặc một thư viện parser được duy trì. Khi cần biến đổi AST sâu, xác định rõ sự phụ thuộc phiên bản compiler và kế hoạch nâng cấp tool tương ứng.

## 13. Đừng đánh đồng javax.*, jakarta.* với JDK internals

Trong migration framework, có thể gặp package `javax.*` hoặc `jakarta.*`. Đây không phải cùng phép phân loại với `sun.*` và `jdk.internal.*`.

- Một số `javax.*` thuộc API Java SE, ví dụ `javax.net.ssl` hoặc `javax.crypto`.
- Một số `javax.*` khác thuộc API từng có trong Java EE hoặc thư viện bên ngoài và có thể không còn được đóng gói trong JDK hiện đại.
- `jakarta.*` thuộc hệ sinh thái Jakarta EE và các artifact dependency tương ứng.
- Việc chuyển `javax.persistence` sang `jakarta.persistence` là thay đổi version/framework, không phải dấu hiệu package trước đó là JDK internals.

Ví dụ, ứng dụng dùng JAXB qua `javax.xml.bind` khi còn ở JDK 8 cần tìm dependency phù hợp khi nâng JDK 11+. Không thể dùng `--add-opens` để tạo lại API đã bị loại bỏ. Đồng thời cũng không thể tự đổi mọi `javax` sang `jakarta` mà không kiểm tra framework compatibility.

Việc phân loại chính xác API giúp không quy nhầm lỗi dependency thành lỗi module access.

## 14. Khảo sát source code và dependency bằng tìm kiếm tĩnh

Bước đầu của migration là tìm tham chiếu tới các họ package đáng chú ý trong source và cấu hình:

~~~bash
rg -n "sun\\.|com\\.sun\\.|jdk\\.internal\\." src build.gradle settings.gradle pom.xml
~~~

`rg` là ví dụ dùng ripgrep; đường dẫn và shell phải điều chỉnh theo dự án. Kết quả tìm kiếm chỉ là danh sách nghi vấn, không phải danh sách lỗi đã xác nhận.

Khi khảo sát, nên phân loại từng kết quả:

1. **Direct import:** mã ứng dụng trực tiếp import `sun.*`, `com.sun.*` hoặc `jdk.internal.*`.
2. **Reflection string:** `Class.forName("...")` hoặc tên class trong file cấu hình.
3. **Code generation:** template và source generated có tham chiếu tới internal type.
4. **Dependency bytecode:** JAR bên ngoài có static reference tới internal classes.
5. **Documentation/test data:** tên package chỉ xuất hiện trong comment, log mẫu hoặc dữ liệu test.

Không xóa hay thay code chỉ vì regex tìm thấy một chuỗi `com.sun`: có thể đó là API JDK documented hoặc thậm chí không phải tham chiếu code.

### 14.1. Công cụ jdeps

`jdeps` hỗ trợ phân tích phụ thuộc tĩnh của class/JAR, đặc biệt hữu ích để phát hiện internal JDK APIs:

~~~bash
jdeps --jdk-internals app.jar
~~~

Với dependency trên classpath, có thể dùng:

~~~bash
jdeps --recursive --jdk-internals \
      --class-path "lib/*" \
      app.jar
~~~

Khi artifact là multi-release JAR, chỉ định release thích hợp:

~~~bash
jdeps --multi-release 17 \
      --jdk-internals \
      library.jar
~~~

Tùy cấu trúc JAR và phiên bản công cụ, cần cung cấp classpath hoặc module path đầy đủ để xử lý dependencies. Với executable fat JAR có nested JAR (chẳng hạn kiểu đóng gói framework), phải xem xét cách extract/analyze các JAR lồng; `jdeps` không mặc nhiên mô phỏng mọi launcher hoặc class loader đặc thù.

### 14.2. Hạn chế của jdeps

Phân tích tĩnh không nắm hết reflection hoặc dynamic class loading. Ví dụ:

~~~java
String name = System.getProperty("internal.helper.class");
Class<?> helper = Class.forName(name);
~~~

Tên lớp chỉ có trong cấu hình runtime có thể không tạo static bytecode reference. `jdeps` không thể suy ra mọi giá trị cấu hình thực tế. Cần bổ sung kiểm thử runtime, log và rà soát file cấu hình.

`jdeps` cũng không chứng minh API là “ổn định” chỉ vì nó không báo internal dependency. Nó phân tích loại phụ thuộc nhất định, không thay thế việc đọc tài liệu API chính thức.

## 15. Một quy trình kiểm kê có thể thực hiện trong dự án lớn

Hệ thống nhiều module nên tạo một bảng kiểm kê thay vì sửa rải rác theo stack trace:

| Trường | Ý nghĩa |
|---|---|
| Nguồn | Module, class, dependency hoặc template chứa tham chiếu |
| Symbol | Package/class/method cụ thể |
| Loại API | Java SE, JDK documented, internal, chưa xác định |
| Bằng chứng | Import, jdeps output, stack trace, reflection config |
| Mục đích | Base64, bytecode, native memory, XML, compiler AST... |
| JDK hiện tại/đích | Ví dụ 8 -> 17 hoặc 17 -> 21 |
| Rủi ro | Compile failure, reflection error, semantic change |
| Hướng xử lý | Public API, nâng thư viện, workaround, loại bỏ |
| Owner | Nhóm/code owner chịu trách nhiệm |
| Trạng thái | Chưa phân tích, đang xử lý, đã xác minh |

Việc tách **direct dependency** và **transitive dependency** rất quan trọng. Nếu symbol nội bộ nằm trong JAR framework, ứng dụng có thể không sửa được import; nên tìm bản phát hành framework/agent tương thích JDK mới.

Bảng kiểm kê cũng nên ghi chú trường hợp `com.sun.*` thuộc documented JDK API để tránh báo lỗi giả và không buộc nhóm thay API một cách không cần thiết.

## 16. Khi stack trace báo lỗi access: điều tra thế nào?

Một quy trình chẩn đoán hiệu quả gồm:

### Bước 1: Xác định exception gốc

Đọc `Caused by` sâu nhất hoặc lỗi đầu tiên khi JVM nạp class/khởi tạo thư viện. Phân biệt:

- `InaccessibleObjectException`: deep reflection bị hạn chế.
- `IllegalAccessError`: bytecode/linkage không được phép truy cập một type/member.
- `NoSuchMethodError` hoặc `NoSuchFieldError`: runtime version khác hoặc API nội bộ đã đổi.
- `ClassNotFoundException`: class không tìm thấy theo class loader đang dùng.
- `UnsupportedClassVersionError`: class-file version không tương thích.

### Bước 2: Xác định caller

Lớp nào đang truy cập JDK internal API? Mã ứng dụng, annotation processor, Java agent hay JAR bên thứ ba? Nếu là dependency, ghi artifact/version và tra release notes hoặc compatibility matrix của nhà phát hành.

### Bước 3: Xác định module và package bị hạn chế

Thông báo như “module `java.base` does not open `java.lang` to unnamed module” mô tả module đích, package và caller. Không nên đoán tên package rồi thêm nhiều flags tùy ý.

### Bước 4: Ưu tiên cập nhật hoặc thay API

Nếu có bản library hỗ trợ JDK đích, ưu tiên nâng library. Nếu là code tự quản lý, thay bằng API công khai. Chỉ cân nhắc override khi chưa có giải pháp ngay và rủi ro chấp nhận được.

### Bước 5: Xác minh lại artifact trên runtime đích

Test startup, luồng tạo object, serialization, ORM, reflection, class loading và error paths. Một lỗi access có thể chỉ xuất hiện ở luồng ít được gọi hoặc khi điều kiện dữ liệu cụ thể được kích hoạt.

## 17. Build và runtime có thể khác cách nhìn thấy internals

Ba môi trường cần được tách:

1. **JDK chạy build tool** (Gradle/Maven daemon, plugin).
2. **JDK dùng để biên dịch source** (javac/toolchain).
3. **JDK chạy ứng dụng hoặc test** (JVM production/test launcher).

Một annotation processor có thể phụ thuộc `com.sun.tools.javac.*` và lỗi khi chạy trên compiler mới, dù generated bytecode nhắm Java cũ. Ngược lại, application source có thể compile thành công nhưng runtime framework dùng reflection vào JDK internals và thất bại.

Ví dụ cấu hình Gradle để chọn JDK 17 và release mục tiêu:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

`options.release` giúp kiểm soát source syntax, class-file target và tập API công khai cho release mục tiêu theo cơ chế compiler. Nhưng nó **không chứng minh toàn bộ dependency và code phản chiếu đều tương thích** và không thay thế test trên JVM đích.

Các options mở module dùng cho build process, test process và production launch có thể nằm ở vị trí cấu hình khác nhau. Không nên nhầm flag của Gradle daemon với flag sẽ được truyền cho ứng dụng trong container.

## 18. Phân biệt lỗi package không export với lỗi class đã bị gỡ

Hai lỗi sau có thể xuất hiện ở cùng thời điểm migration nhưng cần xử lý khác nhau.

### 18.1. Package tồn tại nhưng không export

Ví dụ khi code import internal package:

~~~java
import jdk.internal.misc.Unsafe;
~~~

Compiler có thể báo package không visible vì `java.base` không export package đó tới module hiện tại. Nguyên nhân là **access policy**. Hướng xử lý ưu tiên: dùng public API, không ép mở package chỉ để hoàn tất build.

### 18.2. Class/API không tồn tại trên JDK mới

Ví dụ một API từng được phân phối trong JDK cũ đã bị loại bỏ. Compiler báo cannot find symbol hoặc runtime báo `ClassNotFoundException`. Vấn đề lúc này là **thiếu class/dependency**, không phải package đang bị khóa.

Nếu component đã rời JDK, cách xử lý là thêm dependency hoặc thay thư viện. `--add-exports` và `--add-opens` không thể mang một class đã bị gỡ trở lại.

## 19. Kiểm tra thư viện bytecode, agent và generated code

Không phải mọi phụ thuộc tới JDK internals xuất hiện trong source viết tay. Các thành phần này cần được khảo sát riêng:

- **Annotation processor:** có thể truy cập javac internals hoặc sinh import tới API không phù hợp.
- **Bytecode generator:** có thể yêu cầu class-file version, JDK API hoặc runtime behavior cụ thể.
- **Java agent/profiler:** có thể instrument lớp JDK và cần module opens/exports hoặc phiên bản agent tương thích.
- **ORM/serialization framework:** có thể deep reflect vào JDK classes hoặc private members của ứng dụng.
- **Build plugin:** có thể chạy bằng JDK khác với ứng dụng và phụ thuộc internal API khi thao tác AST.
- **Shaded JAR:** có thể che nguồn gốc package hoặc đóng gói class phiên bản cũ.

Một ứng dụng không có direct `sun.*` import vẫn có thể thất bại vì dependency bắc cầu. Vì vậy, kế hoạch nâng JDK phải có bước rà soát phiên bản framework, agents, test runners và build plugins; không chỉ tìm kiếm trong `src/main/java`.

Khi dependency được cập nhật, cần kiểm tra cả hành vi. Một phiên bản mới có thể loại bỏ internal access nhưng đồng thời đổi semantics, format dữ liệu hoặc cách cấu hình.

## 20. Chính sách cho workaround tạm thời

Nếu không thể loại bỏ ngay internal dependency, có thể cần workaround được kiểm soát. Một bản ghi nên chứa:

~~~yaml
internalApiException:
  owner: platform-team
  component: legacy-serializer
  jdkTarget: "17"
  symptom: "InaccessibleObjectException during serialization"
  package: "java.base/java.lang"
  temporaryRuntimeFlag:
    - "--add-opens=java.base/java.lang=ALL-UNNAMED"
  justification: "No compatible dependency release currently deployed"
  mitigation: "Limit usage; integration-test on target JDK"
  removalPlan: "Upgrade serializer and remove runtime flag"
  status: "temporary"
~~~

Các giá trị trong ví dụ chỉ minh họa quy trình quản lý, không phải một workaround nên áp dụng mặc định. Không công bố secret hoặc thông tin nhạy cảm trong báo cáo.

Nên tránh:

- Thêm hàng loạt `--add-opens` theo một danh sách copy từ internet mà không có lỗi tương ứng.
- Chấp nhận “có thể khởi động” làm tiêu chí duy nhất; một nhánh reflection hiếm có thể vẫn lỗi.
- Giữ flags ở máy local nhưng quên CI/container/production.
- Cho phép một dependency không được hỗ trợ giữ nguyên vô thời hạn mà không có owner hoặc kế hoạch thay thế.
- Dựa vào internal API trong mã mới chỉ vì có workaround cho thư viện cũ.

## 21. Ví dụ quy trình migration của một ứng dụng legacy

Giả sử một ứng dụng Java 8 dùng:

- `sun.misc.BASE64Encoder` trong lớp utility tự viết.
- Một parser library có static reference tới `com.sun.org.apache.xerces.internal.*`.
- Một annotation processor cũ truy cập `com.sun.tools.javac.tree.JCTree`.
- Một serializer cũ dùng deep reflection vào private fields thuộc JDK.

Mục tiêu là chuyển runtime sang JDK 17 nhưng chưa chuyển ứng dụng sang named modules.

### Pha 1: Lập danh mục

Dùng tìm kiếm source/config và `jdeps --jdk-internals` trên artifact/JAR phù hợp. Xác định bốn thành phần khác nhau; không gộp thành một “lỗi JPMS”.

### Pha 2: Loại bỏ direct dependency dễ thay

Chuyển Base64 sang `java.util.Base64`. Kiểm tra định dạng dữ liệu hiện có. Với XML, dùng `javax.xml.parsers` hoặc thư viện parser công khai để tránh internal Xerces classes.

### Pha 3: Nâng toolchain liên quan compiler

Tìm annotation processor tương thích với javac/JDK 17. Nếu tool chủ động sửa AST nội bộ, nâng phiên bản công cụ hoặc thay cơ chế. Không kỳ vọng `--add-exports` chữa được khác biệt trong cấu trúc `JCTree`.

### Pha 4: Nâng framework và serializer

Tìm bản serializer không cần deep reflection vào các JDK private members. Nếu chưa thể nâng, định nghĩa temporary `--add-opens` chỉ cho package có bằng chứng rõ, ghi rõ phạm vi và kế hoạch loại bỏ.

### Pha 5: Chạy trên JDK 17

Kiểm tra clean build, startup, mapping, XML, serialization và các luồng nghiệp vụ; so sánh kết quả với baseline. Chạy trong môi trường có cùng JVM flags và dependency như production.

Kết quả cần được báo cáo theo từng API/dependency đã xử lý. Không chỉ ghi “Build success” vì phần lớn rủi ro internals nằm ở runtime hoặc phụ thuộc công cụ.

## 22. Mẫu kết luận khảo sát

Có thể lập bảng:

| Kết quả | Bằng chứng | Quyết định |
|---|---|---|
| `java.util.Base64` được sử dụng thay internal encoder | Source diff và test dữ liệu | Hoàn tất |
| JDK internals dependency trong parser đã loại bỏ | `jdeps` và test XML | Hoàn tất |
| Annotation processor phiên bản mới chạy với JDK đích | Clean compilation và generated source | Hoàn tất hoặc cần test thêm |
| Serializer còn cần `--add-opens` tạm thời | Stack trace, integration test, cấu hình launch | Có owner và kế hoạch loại bỏ |
| API `com.sun.net.httpserver` đang được dùng | Tài liệu module `jdk.httpserver` và compatibility policy | Đánh giá là JDK-specific documented API, không tự động xếp internal |
| Một helper `jdk.internal.*` còn trong code | Source inspection và build error | Chưa hoàn tất, cần thay API |

Dòng về `com.sun.net.httpserver` minh họa một ngoại lệ quan trọng: một báo cáo migration chất lượng phải nêu **vì sao API được chấp nhận hoặc bị loại bỏ**, không áp quy tắc tiền tố một cách máy móc.

## 23. Các nguyên tắc cần ghi nhớ

- **Hợp đồng API quan trọng hơn tên package.** Java SE API, JDK documented API và JDK internals có phạm vi hỗ trợ khác nhau.
- **`sun.*` và `jdk.internal.*` là dấu hiệu rủi ro cao**, nhưng cần xác định symbol, module và mục đích sử dụng cụ thể.
- **Không kết luận mọi `com.sun.*` là internal.** `com.sun.source.*`, `com.sun.net.httpserver` và một số `com.sun.management` là những ví dụ API JDK được tài liệu hóa.
- **Export/open không đồng nghĩa API ổn định.** JPMS kiểm soát access; tài liệu/specification quyết định phạm vi API contract.
- **`jdk.unsupported` không biến Unsafe thành lựa chọn mặc định an toàn.** Nó tồn tại nhằm đáp ứng các nhu cầu chuyển tiếp và tương thích đặc biệt.
- **Dùng public API thay thế khi có thể.** `Base64`, `VarHandle`, `Atomic*`, `Cleaner`, `java.security.cert` và compiler API được tài liệu hóa thường là những hướng đi thích hợp tùy nhu cầu.
- **`jdeps` là công cụ khảo sát, không phải bằng chứng tuyệt đối.** Reflection động, service loading và native code đòi hỏi xác minh thêm.
- **Ưu tiên nâng dependency hơn mở module hàng loạt.** Overrides phải có nguyên nhân, phạm vi và kế hoạch loại bỏ rõ ràng.
- **Build tool, compiler và runtime có thể dùng JDK khác nhau.** Cần kiểm tra cả ba và artifact cuối cùng.
- **Tương thích phải được kiểm chứng bằng hành vi.** Compile thành công không đủ chứng minh serializer, agent, XML parser hay compiler plugin chạy đúng trên JDK mới.

Khi thực hiện Java Advance Compatibility Migration, việc nhận biết API được hỗ trợ là bước quan trọng để giảm phụ thuộc vào chi tiết triển khai của JDK. Cách làm bền vững là **xác định đúng hợp đồng API, phân loại từng symbol thay vì chỉ nhìn tiền tố, thay thế internals bằng API công khai khi phù hợp và kiểm thử toàn bộ đường thực thi trên JDK mục tiêu**. Nhờ đó, nhóm không chỉ loại bỏ lỗi trước mắt mà còn giảm rủi ro cho những lần nâng cấp Java tiếp theo.
