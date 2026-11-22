# Thay API nội bộ bằng API chuẩn hoặc thư viện được duy trì

Trong một dự án Java Advance Compatibility Migration, code có thể chạy ổn định nhiều năm nhờ các class hoặc method không được Java SE cam kết hỗ trợ, như `sun.misc.Unsafe`, `sun.misc.BASE64Encoder`, `sun.security.x509`, `jdk.internal.reflect.*` hoặc `com.sun.org.apache.xerces.internal.*`. Những API đó thường là chi tiết triển khai của một phiên bản JDK hoặc một nhà cung cấp JVM. Khi nâng JDK, thay vendor hoặc bật mô hình module JPMS, code sử dụng chúng có thể không còn biên dịch, không truy cập được ở runtime hoặc thay đổi hành vi.

**Thay API nội bộ bằng API chuẩn hoặc thư viện được duy trì** là quá trình xác định phần code phụ thuộc vào giao diện không ổn định, hiểu nhu cầu thực sự của phần code đó, rồi chuyển sang API công khai có hợp đồng hỗ trợ rõ ràng hoặc dependency bên thứ ba được bảo trì. Mục tiêu không chỉ là làm mất cảnh báo compiler mà là **giảm phụ thuộc vào implementation detail của JDK**, giữ hợp đồng quan sát được của ứng dụng và đảm bảo nâng cấp trong tương lai dễ kiểm soát.

Bài học đặt trong bối cảnh **Reflection và API nội bộ**: vì sao Java 9+ thay đổi cơ chế truy cập, cách điều tra những dependency ẩn, ví dụ chuyển đổi API thường gặp, tiêu chí chọn thư viện thay thế, cách kiểm thử và phạm vi chấp nhận các tùy chọn bypass trong lúc migration.

## 1. Nhận diện đúng API nội bộ, API chuẩn và API bị loại bỏ

Không nên quyết định API có được hỗ trợ chỉ dựa vào tên package. Trong Java, có nhiều nhóm khác nhau:

| Nhóm | Ví dụ | Khả năng tương thích |
|---|---|---|
| API công khai thuộc Java SE | `java.util.Base64`, `java.util.concurrent.atomic.AtomicLong`, `java.lang.invoke.VarHandle` | Có đặc tả, tài liệu và chính sách tương thích của nền tảng |
| API công khai của một JDK/vendor cụ thể | Một số API `com.sun.*` hoặc công cụ mở rộng có tài liệu chính thức | Có thể được hỗ trợ trong phạm vi JDK/vendor xác định, nhưng không mặc nhiên portable |
| API nội bộ của JDK | `jdk.internal.*`, nhiều loại `sun.*`, `com.sun.*.internal.*` | Không có cam kết API Java SE ổn định; có thể bị đóng hoặc thay đổi |
| API công khai bị deprecated | Method/class có annotation `@Deprecated` | Có thể vẫn được hỗ trợ; cần đọc thông báo và kế hoạch loại bỏ cụ thể |
| API/module đã bị loại bỏ | Một số module Java EE/CORBA từng được phân phối cùng JDK cũ | Cần tìm dependency/API thay thế; khác với lỗi JPMS encapsulation |
| API bên thứ ba | ASM, Byte Buddy, thư viện XML, JSON, crypto | Do maintainer thư viện quy định support matrix và vòng đời |

### 1.1. Tên package không phải bằng chứng tuyệt đối

- Không phải cứ `com.sun` là API nội bộ và không phải cứ `javax` là API công khai của mọi JDK.
- Một package được export bởi module không đồng nghĩa toàn bộ API bên trong là giao diện Java SE ổn định.
- Một API public ở cấp ngôn ngữ Java vẫn có thể nằm trong package không được module export cho code khác.
- Một class vẫn còn bên trong JDK image không có nghĩa ứng dụng được phép liên kết trực tiếp vào nó.

Để đánh giá, kiểm tra tài liệu API chính thức, module chứa package, trạng thái export/open, release note, cảnh báo compiler và kết quả phân tích dependency trên đúng JDK đích.

### 1.2. Không đồng nhất deprecated với internal

`@Deprecated` là một tín hiệu về vòng đời API công khai; nó không tự có nghĩa API đã bị xóa hoặc không thể dùng. API nội bộ có thể **không hề có annotation deprecated** nhưng vẫn không được hỗ trợ. Ngược lại, một API công khai bị deprecated vẫn có thể là lối migration ổn định hơn một reflection hack vào field private của JVM.

Phân biệt ít nhất ba câu hỏi:

1. API có công khai và được đặc tả cho consumer không?
2. API có bị deprecated, bị giới hạn phiên bản hoặc dự kiến loại bỏ không?
3. Code của mình sử dụng nó bằng cách chuẩn hay đang bypass encapsulation?

Việc xử lý khác nhau: một internal API cần thay đường phụ thuộc; một public API deprecated cần đánh giá thời hạn và API kế nhiệm; một API công khai còn hoạt động nhưng được truy cập bằng reflection không cần thiết có thể thay bằng lời gọi trực tiếp.

## 2. Vì sao migration Java 9+ làm lộ vấn đề?

Từ Java 9, **Java Platform Module System (JPMS)** tổ chức JDK thành named modules và áp dụng quy tắc readability, exports và opens. Những package nội bộ từng có thể được dùng trên classpath của một số JDK cũ không còn mặc nhiên accessible.

Các mốc quan trọng:

- **JDK 9:** đưa JPMS vào JDK, bắt đầu giai đoạn siết truy cập nội bộ, đồng thời cung cấp các công cụ và tùy chọn chuyển tiếp.
- **JDK 16:** mặc định cơ chế encapsulation chặt hơn so với nhiều giai đoạn Java 9–15.
- **JDK 17:** strong encapsulation của JDK internals được siết theo JEP 403. Tùy chọn `--illegal-access` không còn là cơ chế mở quyền hữu hiệu như các release trước.
- Các API nội bộ vẫn được một số thành phần hỗ trợ đặc biệt, chẳng hạn nhóm `sun.misc.Unsafe` qua module `jdk.unsupported`, nhưng điều này **không biến chúng thành API Java SE ổn định**.

Có hai lỗi khác nhau thường gặp:

**Lỗi truy cập tại compile time** khi code import package không được export:

~~~text
package jdk.internal.misc is not visible
(package jdk.internal.misc is declared in module java.base,
 which does not export it to the unnamed module)
~~~

**Lỗi reflection tại runtime** khi code cố gọi `setAccessible(true)` vào thành viên thuộc module không open package phù hợp:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make ... accessible:
module java.base does not "opens java.lang" to unnamed module ...
~~~

Cách khắc phục bền vững phải dựa vào mục tiêu mà code đang cố đạt, không chỉ thêm flag để tắt lỗi.

## 3. Kiểm kê nơi dự án dùng API nội bộ

Trước khi thay thế, xác định cả dependency trực tiếp lẫn sử dụng gián tiếp. API nội bộ có thể nằm trong source chính, test, công cụ build, generated code, agent/profiler hoặc dependency bắc cầu.

### 3.1. Dùng jdeps để tìm phụ thuộc vào JDK internal APIs

Với một JAR đã build, có thể dùng:

~~~bash
jdeps --jdk-internals app.jar
~~~

Nếu JAR cần các dependency khác để phân tích đầy đủ:

~~~bash
jdeps \
  --class-path "lib/*" \
  --jdk-internals \
  app.jar
~~~

Với multi-release JAR, chỉ định view phù hợp với JDK cần kiểm tra:

~~~bash
jdeps \
  --multi-release 17 \
  --jdk-internals \
  --class-path "lib/*" \
  app.jar
~~~

`jdeps` phân tích dependency tĩnh từ class file. Nó thường giúp phát hiện các tham chiếu như:

~~~text
com.example.FastAccess -> sun.misc.Unsafe          JDK internal API
com.example.CertificateUtil -> sun.security.x509   JDK internal API
~~~

Kết quả cần được diễn giải theo JDK và version của tool. Một cảnh báo không tự chứng minh ứng dụng đã lỗi, nhưng là bằng chứng rằng code đang phụ thuộc API có rủi ro. Một kết quả không phát hiện vấn đề cũng **không chứng minh hoàn toàn sạch API nội bộ**, vì reflection theo chuỗi và dynamic class loading có thể không được công cụ phát hiện.

### 3.2. Tìm import, reflection theo chuỗi và method truy cập bất thường

Có thể tìm trong repository:

~~~bash
rg -n --glob '*.java' \
  'import (sun\.|com\.sun\.|jdk\.internal\.)' .

rg -n --glob '*.java' \
  'Class\.forName|setAccessible|trySetAccessible|privateLookupIn|getDeclaredField|getDeclaredMethod|Unsafe|defineClass' .
~~~

Tìm thêm trong file cấu hình:

~~~bash
rg -n --hidden -g '!**/.git/**' \
  'jdk\.internal|sun\.misc|sun\.security|--add-opens|--add-exports|--illegal-access|JAVA_TOOL_OPTIONS|JDK_JAVA_OPTIONS' .
~~~

Đây là **heuristic tìm kiếm**, không phải bộ phân tích đầy đủ. Một codebase có thể gọi `Class.forName` với tên class được ghép động hoặc lấy từ YAML, XML, annotation, database, service descriptor. Thư viện có thể load implementation bằng reflection mà source project không import lớp nội bộ nào.

Nếu dự án dùng nhiều module, chạy phân tích trên artifact đúng bản release, không chỉ source của một module. Cần quan sát cả bytecode trong JAR được publish và các dependency runtime thực sự được resolve.

### 3.3. Kết hợp jdeprscan để phân biệt deprecated public API

Ví dụ:

~~~bash
jdeprscan --release 17 app.jar
~~~

`jdeprscan` giúp tìm tham chiếu tới các API Java SE bị deprecated ở release được chọn. Nó giải quyết một câu hỏi **khác** với `jdeps --jdk-internals`: deprecated public API không đồng nhất với JDK internal API. Kết hợp hai nguồn giúp nhóm không xử lý nhầm cùng một loại rủi ro.

### 3.4. Dùng runtime log và stack trace

Khi chạy ứng dụng trên JDK đích, ghi lại đầy đủ exception và đường nạp class. Các lỗi cần phân biệt gồm:

| Lỗi | Nguyên nhân thường gặp | Việc cần kiểm tra |
|---|---|---|
| `InaccessibleObjectException` | Deep reflection vào package chưa open | Module/package owner, reflection API, khả năng bỏ reflection |
| `IllegalAccessError` | Bytecode truy cập type/member bị cấm | Export rules, class/module được nạp thực tế |
| `NoClassDefFoundError` | Class không tồn tại trong runtime hoặc class init thất bại | Artifact, class loader, root cause |
| `ClassNotFoundException` | Dynamic lookup không tìm được class | Tên class, classpath/module path, vendor |
| `NoSuchMethodError` | Bytecode gọi method không còn trong class runtime | Dependency version và method descriptor |
| `UnsupportedClassVersionError` | Class-file version cao hơn JVM | JDK runtime và major/minor version |
| `ExceptionInInitializerError` | Khởi tạo static thất bại, có thể do nội bộ hoặc cấu hình | Cause gốc và stack trace |

Không nên tự động thêm `--add-opens` cho mọi lỗi. Ví dụ `NoSuchMethodError` thường liên quan binary compatibility hoặc dependency version, không phải JPMS access.

## 4. Phân loại usage theo nhu cầu thực sự

Trước khi sửa một lời gọi nội bộ, hãy hỏi: code cần **kết quả gì** mà API đó đang cung cấp?

| Nhu cầu thật | Cách cũ dễ gặp | Thay thế ưu tiên |
|---|---|---|
| Base64 encode/decode | `sun.misc.BASE64Encoder` / `BASE64Decoder` | `java.util.Base64` |
| Atomic counter / compare-and-set | `sun.misc.Unsafe` trực tiếp | `AtomicInteger`, `AtomicLong`, `VarHandle` |
| Truy cập byte trực tiếp/buffer | Unsafe/field nội bộ của ByteBuffer | `ByteBuffer`, `FileChannel` hoặc API memory công khai phù hợp với JDK |
| Kiểm tra thuộc tính class/method | Reflection vào metadata nội bộ | `java.lang.Class`, `java.lang.reflect`, `java.lang.invoke` |
| Tạo/định nghĩa class động | Reflection vào `ClassLoader#defineClass` hoặc API nội bộ | API `MethodHandles.Lookup` phù hợp, `java.lang.instrument`, công cụ bytecode được duy trì |
| Đọc XML | JDK-internal Xerces implementation | `javax.xml.parsers`, `org.w3c.dom`, `javax.xml.transform` |
| Dùng thuật toán bảo mật | Concrete provider nội bộ của JDK | `java.security`, `javax.crypto`, provider được duy trì |
| Sinh/chỉnh X.509 | `sun.security.x509` | API công khai nếu đủ cho use case; nếu phải tạo certificate, dùng thư viện crypto có support matrix |
| Biến đổi bytecode | ASM được nhúng bên trong JDK | Artifact ASM/Byte Buddy được duy trì, version pin rõ |
| Bắt tín hiệu OS | `sun.misc.Signal` | Shutdown hook/API lifecycle khi semantics phù hợp; cơ chế OS hoặc thư viện riêng nếu cần xử lý signal đặc thù |

Một API công khai có thể không có khả năng thay thế 1:1 mọi thao tác nội bộ. Ví dụ `VarHandle` giải quyết nhiều truy cập biến có thứ tự bộ nhớ và thao tác atomic, nhưng không tự thay thế mọi use case cấp phát native memory hoặc định nghĩa class động từ `Unsafe`. Phải tách nhu cầu, không áp một recipe cho mọi lần xuất hiện của tên class.

## 5. Ví dụ: sun.misc.BASE64Encoder sang java.util.Base64

Đây là phép chuyển dễ thấy nhưng vẫn cần giữ semantics về encoding và line breaks.

### 5.1. Cách cũ

Trong code chạy trên một số JDK cũ:

~~~java
import sun.misc.BASE64Encoder;

import java.nio.charset.StandardCharsets;

public class TokenEncoder {
    public String encode(String value) {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        return new BASE64Encoder().encode(bytes);
    }
}
~~~

`sun.misc.BASE64Encoder` là API nội bộ, không nên tiếp tục dùng trong code mục tiêu trên JDK mới.

### 5.2. Cách mới dùng API chuẩn

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class TokenEncoder {
    public String encode(String value) {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        return Base64.getEncoder().encodeToString(bytes);
    }

    public String decode(String encoded) {
        byte[] decoded = Base64.getDecoder().decode(encoded);
        return new String(decoded, StandardCharsets.UTF_8);
    }
}
~~~

`java.util.Base64` có từ Java 8 và cung cấp các biến thể encoder/decoder theo những quy ước khác nhau:

- `getEncoder()` và `getDecoder()` cho Base64 cơ bản.
- `getUrlEncoder()` và `getUrlDecoder()` cho biến thể URL-safe.
- `getMimeEncoder()` và `getMimeDecoder()` cho quy tắc MIME có xử lý dòng phù hợp.

Không được chọn một biến thể chỉ vì chúng đều tạo chuỗi có vẻ hợp lệ. Code cũ có thể xuống dòng sau một số ký tự hoặc chấp nhận whitespace theo cách khác. Chênh lệch đó có thể ảnh hưởng file, protocol, token hoặc chữ ký số.

### 5.3. Kiểm tra hợp đồng

Thiết kế ví dụ test:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

class TokenEncoderTest {
    @Test
    void roundTripUtf8() {
        String original = "Xin chào Java";
        String encoded = Base64.getEncoder()
                .encodeToString(original.getBytes(StandardCharsets.UTF_8));

        String decoded = new String(
                Base64.getDecoder().decode(encoded),
                StandardCharsets.UTF_8
        );

        assertEquals(original, decoded);
    }

    @Test
    void basicEncoderDoesNotInsertLineBreaks() {
        byte[] data = new byte[100];
        String result = Base64.getEncoder().encodeToString(data);
        assertFalse(result.contains("\n"));
        assertFalse(result.contains("\r"));
    }
}
~~~

Nếu dữ liệu từ hệ thống cũ còn được đọc, cần test compatibility với fixture thật: output Base64 cũ, input có padding/không padding, khoảng trắng, dữ liệu nhị phân, giá trị trống và chuỗi Unicode. Có thể cần chọn MIME decoder hoặc thêm lớp chuẩn hóa dữ liệu nếu hợp đồng cũ thực sự cho phép khoảng trắng. Không làm lỏng parser một cách mặc định nếu dữ liệu thuộc ngữ cảnh bảo mật.

## 6. Ví dụ: dùng AtomicLong hoặc VarHandle thay Unsafe

`sun.misc.Unsafe` thường được dùng để truy cập field theo offset, thực hiện compare-and-swap, đọc/ghi với memory ordering cụ thể hoặc thao tác bộ nhớ off-heap. Một số chức năng có public API thay thế rõ ràng, một số khác cần thiết kế lại.

### 6.1. Với một bộ đếm atomic, ưu tiên AtomicLong

Thay vì lấy offset của field và gọi API Unsafe, dùng:

~~~java
import java.util.concurrent.atomic.AtomicLong;

public final class SequenceGenerator {
    private final AtomicLong next = new AtomicLong();

    public long allocate() {
        return next.getAndIncrement();
    }

    public long current() {
        return next.get();
    }
}
~~~

API chuẩn này rõ nghĩa, tránh phụ thuộc layout của object và không yêu cầu code truy cập vào singleton Unsafe bằng reflection. Tuy nhiên, khi chuyển từ Unsafe sang AtomicLong, hãy kiểm tra semantics: phương thức nào trả giá trị trước/sau increment, kiểu overflow, visibility, tính atomic và yêu cầu hiệu năng.

### 6.2. Với field cụ thể, dùng VarHandle khi phù hợp

`VarHandle` thuộc `java.lang.invoke` từ Java 9, hỗ trợ nhiều thao tác variable access với memory ordering được xác định rõ.

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public final class Counter {
    private volatile long value;

    private static final VarHandle VALUE;

    static {
        try {
            VALUE = MethodHandles.lookup()
                    .findVarHandle(Counter.class, "value", long.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public long incrementAndGetOldValue() {
        return (long) VALUE.getAndAdd(this, 1L);
    }

    public long current() {
        return (long) VALUE.getVolatile(this);
    }
}
~~~

Trong ví dụ, `MethodHandles.lookup()` được gọi từ code của chính class sở hữu field, nên có quyền phù hợp để tìm private field đó. Không nên suy luận rằng lookup này có thể đọc mọi field private thuộc mọi class của JDK.

`getAndAdd` trả về giá trị cũ; `getVolatile` đọc theo semantics volatile. Nếu thay một thao tác Unsafe bằng VarHandle, cần chọn đúng access mode về memory ordering, không chỉ chọn method có tên tương tự. Các mode plain, opaque, acquire/release và volatile không đồng nhất về ràng buộc bộ nhớ.

### 6.3. Trường hợp không thể thay máy móc

Các use case sau cần thiết kế và kiểm chứng riêng:

- Cấp phát/giải phóng native memory: có thể cần `ByteBuffer.allocateDirect`, hoặc Foreign Function & Memory API công khai trên các JDK hỗ trợ như JDK 22+, tùy yêu cầu lifecycle và baseline runtime.
- Mapping file và IO: cân nhắc `FileChannel`, `MappedByteBuffer` hoặc API memory phù hợp.
- Sinh/định nghĩa class bytecode: cần xem package, class loader, module, lifetime và API định nghĩa class.
- Tối ưu lock-free phức tạp: cần đảm bảo linearizability, happens-before, publication và concurrency test.
- Serialization framework hoặc runtime agent: thường nên nâng dependency được duy trì thay vì tự thay các điểm gọi Unsafe bên trong nó.

Không hạ bytecode hoặc mở `jdk.internal.misc` như một giải pháp mặc định; JVM layout, GC và memory safety là những nơi rủi ro thay đổi hành vi rất cao.

## 7. Thay deep reflection vào JDK internals

### 7.1. Lỗi phổ biến với setAccessible

Ví dụ một đoạn code đọc implementation detail của `String`:

~~~java
import java.lang.reflect.Field;

public class UnsafeStringInspector {
    public static Object readBackingStorage(String text) throws Exception {
        Field field = String.class.getDeclaredField("value");
        field.setAccessible(true);
        return field.get(text);
    }
}
~~~

Cách làm này có nhiều rủi ro:

- Package `java.lang` thuộc module `java.base` và không open mặc định cho code bên ngoài với deep reflection trên JDK hiện đại.
- Field private của `String` là chi tiết triển khai, có thể đổi kiểu hoặc ý nghĩa giữa các JDK.
- Kết quả là storage nội bộ, **không phải public contract** để xử lý ký tự hay byte.
- Runtime có thể ném `InaccessibleObjectException` hoặc gặp vấn đề khi đổi vendor.

Nếu cần **mảng ký tự** để xử lý text, dùng `String.toCharArray()` hoặc `CharSequence`. Nếu cần **byte theo charset xác định**, dùng `String.getBytes(StandardCharsets.UTF_8)`. Nếu cần kiểm tra độ dài và vị trí ký tự Unicode, cần phân biệt UTF-16 code unit, code point và grapheme cluster. Không dùng field private làm lối tắt vì mục đích của code chưa được làm rõ.

### 7.2. Reflection công khai vẫn là API chuẩn

Không phải mọi reflection đều cần bỏ. Java cung cấp API công khai:

~~~java
import java.lang.reflect.Method;

public class PublicMethodLookup {
    public static Method findRunMethod(Class<?> type)
            throws NoSuchMethodException {
        return type.getMethod("run");
    }
}
~~~

`Class.getMethod` tìm public method theo quy tắc reflection. Với những API mà library cam kết hỗ trợ và package/module truy cập được, reflection công khai có thể là lựa chọn chính đáng, đặc biệt trong framework/plugin.

Điểm cần tránh là dùng reflection để bypass quyền truy cập vào private member không thuộc quyền sở hữu của code hoặc một package JDK không open.

### 7.3. Khi code sở hữu module cần cho framework reflection

Với ứng dụng tự viết module và một framework cần deep reflection vào entity của ứng dụng, giải pháp dài hạn có thể là mở **đúng package của mình** cho **đúng framework module**:

~~~java
module com.example.orders {
    requires com.example.framework;

    opens com.example.orders.model to com.example.framework;
}
~~~

Điều này khác hoàn toàn với mở private package của JDK cho tất cả classpath. Khi framework thực sự cần deep reflection, khai báo `opens` trong module mình quản lý là hợp đồng rõ ràng hơn một JVM option ẩn trong startup script.

Nếu framework đặt trên classpath hoặc sử dụng class loader đặc thù, quy tắc truy cập và tên module đích cần được kiểm tra theo deployment cụ thể. Mở package chỉ là một phần: framework còn phải hỗ trợ JDK, annotation và serialization semantics mới.

### 7.4. MethodHandles không phải bypass miễn phí

`java.lang.invoke.MethodHandles` cung cấp cách lookup và gọi method/field với access checking rõ ràng. Có thể dùng `MethodHandles.privateLookupIn` khi caller có quyền phù hợp và module chứa target package cho phép deep reflection tương ứng. Nó **không** tự vô hiệu hóa JPMS strong encapsulation.

Ví dụ một component của ứng dụng cần access nội bộ có kiểm soát thì có thể đưa logic vào chính module sở hữu member, expose public API hoặc khai báo mở package ở phạm vi hẹp. Không thay một lời gọi `setAccessible(true)` bằng `privateLookupIn` rồi mặc định rằng lỗi access sẽ biến mất.

## 8. Các nhóm JDK internal API khác và lựa chọn thay thế

### 8.1. XML: tránh JDK-internal parser implementation

Nếu code import class từ `com.sun.org.apache.xerces.internal.*` hoặc một implementation parser được JDK nhúng, có thể dùng API Java SE tiêu chuẩn:

~~~java
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;
import java.io.InputStream;

public final class XmlDocuments {
    public static Document parse(InputStream input) throws Exception {
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();

        factory.setFeature(
            "http://apache.org/xml/features/disallow-doctype-decl", true
        );
        factory.setExpandEntityReferences(false);

        return factory.newDocumentBuilder().parse(input);
    }
}
~~~

Đây là ví dụ dùng API factory công khai; cấu hình security của XML parser phải được lựa chọn theo nhu cầu. Các tính năng cụ thể như URI feature ở ví dụ có thể phụ thuộc implementation; cần kiểm tra parser thực tế hỗ trợ và thất bại an toàn khi tính năng bảo mật không được áp dụng. Không copy một vài cờ parser mà kết luận XML parsing đã chống mọi dạng XML External Entity (XXE) hay DoS.

Khi cần đặc tính riêng của Xerces, sử dụng artifact Xerces được duy trì với dependency quản lý rõ ràng, không import implementation nội bộ do JDK nhúng. Kiểm tra namespace, serialization và khả năng xử lý external entity trên đúng parser/version.

### 8.2. Mật mã và provider

Nếu code tham chiếu concrete implementation trong `com.sun.crypto.provider.*` hoặc `sun.security.*`, nên dùng Java Cryptography Architecture (JCA/JCE), chẳng hạn:

~~~java
import javax.crypto.Cipher;

public final class CryptoFactory {
    public static Cipher aesGcmCipher() throws Exception {
        return Cipher.getInstance("AES/GCM/NoPadding");
    }
}
~~~

Đây là ví dụ lấy instance qua API chuẩn, **chưa phải ví dụ mã hóa hoàn chỉnh**. Mã hóa thực tế cần key, IV/nonce, tag size, quản lý key và chống reuse nonce. API công khai giải quyết bài toán tách consumer khỏi implementation class, nhưng không tự bảo đảm cấu hình mật mã an toàn.

Nếu môi trường yêu cầu provider cụ thể hoặc FIPS, phải ghi rõ danh sách provider được cho phép, lựa chọn algorithm và test trên JDK/vendor/runtime đích. Không suy luận rằng mọi provider có cùng implementation hoặc cách xử lý input.

### 8.3. X.509: phân biệt xử lý certificate với phát hành certificate

Để **đọc** certificate X.509 và xác thực chain theo use case, Java SE có `CertificateFactory`, `KeyStore`, `CertPathValidator` và `SSLContext`. Ví dụ đọc certificate:

~~~java
import java.io.InputStream;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

public final class Certificates {
    public static X509Certificate readX509(InputStream input)
            throws Exception {
        CertificateFactory factory = CertificateFactory.getInstance("X.509");
        return (X509Certificate) factory.generateCertificate(input);
    }
}
~~~

Nhưng nếu code cũ dùng `sun.security.x509` để **tự phát hành hoặc ký** certificate, public API Java SE không cung cấp trực tiếp tất cả builder cần thiết cho cùng quy trình. Có thể cân nhắc thư viện crypto được duy trì như Bouncy Castle, một PKI service, công cụ CA được hỗ trợ hoặc thiết kế lại cách provision certificate.

Cần bảo toàn subject, issuer, SAN, key usage, extended key usage, validity, chain building và trust semantics theo hợp đồng thật. Việc biên dịch không lỗi sau khi đổi thư viện chưa chứng minh certificate mới được client chấp nhận.

### 8.4. Bytecode manipulation: bỏ ASM nhúng trong JDK

Một số framework/agent cũ import `jdk.internal.org.objectweb.asm.*` hoặc package implementation riêng bên trong JDK. Đó không phải là API ASM công khai ổn định cho application.

Lựa chọn:
- Dùng artifact **ASM** chính thức phù hợp với class-file version mà JDK mục tiêu tạo ra.
- Dùng **Byte Buddy** hoặc thư viện instrumentation được bảo trì khi logic thao tác bytecode ở mức cao hơn.
- Nếu chỉ cần Java agent lifecycle, dựa vào API công khai `java.lang.instrument` và dependency bytecode tương thích.

Cần pin version và kiểm tra support matrix của thư viện, không viết “dùng version mới nhất” trong build không tái lập được. Bytecode mới có thể thêm class-file attributes, constant pool tags hoặc features mà thư viện cũ không hiểu. Thử cả class loading, verification, stack map frames, instrumentation và rollback khi startup.

### 8.5. Dynamic class definition

Nếu code cũ dùng reflection vào `ClassLoader#defineClass` hoặc API nội bộ để định nghĩa class từ byte array, cần xem **class thuộc package/module nào**, **class loader nào sở hữu nó**, **lifetime thế nào** và **có cần class discoverable theo tên không**.

Các hướng thay thế:
- `MethodHandles.Lookup#defineClass` khi bytecode có binary name thuộc package phù hợp với lookup class.
- `MethodHandles.Lookup#defineHiddenClass` cho một số kiểu class runtime sinh động, theo mô hình hidden class trên JDK hỗ trợ.
- Một subclass của `ClassLoader` sử dụng protected API đúng ranh giới và lifecycle khi trường hợp tương ứng yêu cầu.
- Thư viện bytecode/instrumentation có hỗ trợ JDK đích.

Các phương án trên **không phải drop-in replacement**. Hidden class không có cùng đặc tính tra cứu theo tên như ordinary class; lookup chịu access/module constraints; class loader riêng ảnh hưởng identity, security, resource lifecycle và leak. Vì vậy cần test Class.forName, reflection, dependency injection, serialization và unloading nếu use case yêu cầu.

### 8.6. sun.misc.Signal

Nếu code bắt `sun.misc.Signal` để dọn tài nguyên khi process kết thúc, có thể cân nhắc `Runtime.getRuntime().addShutdownHook(...)` hoặc lifecycle hook của framework:

~~~java
public final class ShutdownLifecycle {
    public static void install() {
        Runtime.getRuntime().addShutdownHook(
            new Thread(() -> System.out.println("Shutting down"))
        );
    }
}
~~~

Shutdown hook không thay thế đầy đủ mọi cơ chế xử lý tín hiệu OS: không bảo đảm chạy khi process bị hủy cưỡng bức, gặp native crash nghiêm trọng hoặc theo mọi thứ tự shutdown. Nếu hệ thống thật sự cần xử lý một signal đặc thù với semantics rõ, phải thiết kế theo OS/process manager hoặc dùng thư viện/platform API có hỗ trợ, không tuyên bố shutdown hook là tương đương 1:1.

## 9. Khi nào chọn thư viện bên thứ ba được duy trì?

Không phải mọi khả năng cần thiết đều được Java SE cung cấp dưới dạng public API thuận tiện. Chọn một thư viện được duy trì có thể an toàn hơn việc tự viết parser, bytecode emitter, certificate builder hoặc network protocol stack.

Tuy nhiên, thay dependency là một cam kết vận hành mới. Cần thẩm định:

| Tiêu chí | Câu hỏi cụ thể |
|---|---|
| Java baseline | Thư viện mới hỗ trợ JDK thấp nhất mà sản phẩm cam kết không? |
| Maintenance | Có release, bugfix, security patch và quy trình disclosure hợp lý không? |
| Compatibility | Phiên bản API/ABI và hành vi có khớp contract của code cũ không? |
| Dependency graph | Có kéo thêm artifact, native library, split package hoặc phiên bản xung đột không? |
| License | License và yêu cầu phân phối có phù hợp sản phẩm không? |
| Security | Có known vulnerability và bản vá được hỗ trợ không? |
| Modularity | Có hoạt động ở classpath, module path, custom image và trong container không? |
| Performance | Allocation, memory, latency và throughput có chấp nhận được không? |
| Operations | Có metric/log/debug và khả năng cập nhật không? |
| Exit strategy | Có thể thay thư viện về sau mà không sửa toàn bộ business code không? |

Không nên mặc định “thư viện bên thứ ba” đồng nghĩa “được duy trì”. Có những thư viện cũ chỉ bọc API nội bộ và chưa hỗ trợ JDK mới. Cần xác minh chính phiên bản artifact đang đưa vào runtime, kể cả dependency bắc cầu.

### 9.1. Tạo abstraction tránh khóa chặt business code

Thay vì để mọi module gọi API nội bộ hoặc API thư viện thay thế trực tiếp, có thể đặt interface theo nhu cầu của domain:

~~~java
public interface TokenCodec {
    String encode(byte[] data);
    byte[] decode(String value);
}
~~~

Implementation bằng API chuẩn:

~~~java
import java.util.Base64;

public final class StandardBase64Codec implements TokenCodec {
    @Override
    public String encode(byte[] data) {
        return Base64.getEncoder().encodeToString(data);
    }

    @Override
    public byte[] decode(String value) {
        return Base64.getDecoder().decode(value);
    }
}
~~~

Nếu hệ thống cũ có biến thể encoding đặc thù, abstraction cho phép thêm adapter tương thích được test riêng. Đây là lớp bao bọc có chủ đích, không nên tạo abstraction cho mọi lời gọi Java SE đơn giản chỉ vì nguyên tắc chung.

### 9.2. Pin version và theo dõi dependency

Trong Gradle hoặc Maven, dùng artifact/version được chọn dựa trên support matrix; quản lý version qua catalog/BOM/dependency management theo conventions của project.

Ví dụ minh họa, không gán version giả làm phiên bản đã được xác minh:

~~~groovy
dependencies {
    implementation("org.ow2.asm:asm:<compatible-pinned-version>")
}
~~~

Tương tự, thư viện certificate hoặc instrumentation cần được khóa version và cập nhật theo policy của dự án. Tránh dynamic version không có kiểm soát trong pipeline release. Sau khi nâng, xác nhận class-file version và dependency graph thực tế của artifact đã resolve.

## 10. Các option --add-opens và --add-exports chỉ là giải pháp chuyển tiếp

JPMS cho phép một số tùy chọn điều chỉnh access tại launch time:

~~~bash
java \
  --add-opens java.base/java.lang=ALL-UNNAMED \
  -jar legacy-app.jar
~~~

Tùy chọn ví dụ này mở package `java.lang` của `java.base` cho deep reflection từ unnamed modules. Nó có thể giúp một thư viện legacy chưa được cập nhật chạy trong giai đoạn ngắn, nhưng cũng mở quyền rất rộng. Nó không nên trở thành cấu hình production mặc định chỉ vì stack trace đề cập `InaccessibleObjectException`.

Một ví dụ khác về exports tạm thời:

~~~bash
java \
  --add-exports java.base/jdk.internal.misc=ALL-UNNAMED \
  -jar legacy-app.jar
~~~

`--add-exports` hỗ trợ truy cập API package không export theo ranh giới module, còn `--add-opens` phục vụ deep reflection vào package ở runtime. Với compile-time access, compiler có thể cần option tương ứng cho code đang import package nội bộ. Các option này không bảo đảm symbol còn tồn tại, chữ ký không thay đổi hoặc semantics được giữ.

**Không phải cứ thêm cờ là đã sửa vấn đề.** Đó là thay đổi module-access policy của process, có thể che rủi ro API nội bộ chưa được thay thế.

### 10.1. Cách quản lý ngoại lệ

Với mỗi flag, lưu:

- Process/task chịu ảnh hưởng và JDK vendor/version.
- Module/package được mở hoặc export, module được cấp quyền.
- Stack trace hoặc trường hợp lỗi khiến flag cần thiết.
- Thư viện/source file đang yêu cầu access.
- Owner và phiên bản thư viện đích để loại bỏ bypass.
- Test chứng minh flag còn cần và test dùng để xác nhận khi bỏ flag.
- Hạn xem xét hoặc mốc migration cụ thể.

Thay `ALL-UNNAMED` bằng tên module cụ thể nếu kiến trúc cho phép. Trong trường hợp package thuộc **module của chính ứng dụng**, ưu tiên sửa module-info.java với `exports`/`opens` theo phạm vi cần thiết. Với private field của JDK, hướng lâu dài vẫn là bỏ lệ thuộc implementation detail.

### 10.2. Tránh --illegal-access trong kế hoạch migration mới

Các workflow từ Java 9–15 có thể từng dùng `--illegal-access=permit` hoặc mode tương tự để trì hoãn sửa reflection. Trên JDK 17, cơ chế này không còn làm JDK mở toàn bộ như trước. Đừng dùng nó như giải pháp thay thế cho việc cập nhật framework và sửa các internal API call.

## 11. Quy trình migration có kiểm soát

Một thay đổi lớn nên được chia theo nhu cầu, rủi ro và khả năng xác minh, thay vì tìm/thay mọi tên package nội bộ trong một lần.

### Bước 1: Chốt JDK và runtime floor

Ghi các phiên bản JDK cần hỗ trợ (ví dụ runtime sản phẩm thấp nhất, JDK build, JDK production), nhà cung cấp và cách triển khai. API chuẩn như VarHandle hay Foreign Function & Memory API chỉ dùng được nếu runtime mục tiêu hỗ trợ phiên bản cần thiết. Không chọn API Java mới hơn runtime floor mà sản phẩm còn công bố hỗ trợ.

### Bước 2: Lập inventory

Dùng `jdeps --jdk-internals`, tìm source/config và log runtime để ghi:
- Class/module hoặc JAR dùng internal API.
- API đang gọi và mục đích thật.
- Tần suất sử dụng, đường code, owner.
- Khả năng thay bằng public API hoặc dependency được duy trì.
- Cảnh báo và lỗi thực tế trên JDK đích.
- Mức độ critical và nhu cầu giữ semantics.

Nên phân biệt code của mình, generated code, dependency trực tiếp và transitive. Việc sửa source ứng dụng không tự sửa dependency đã đóng gói nội bộ một thư viện bên thứ ba.

### Bước 3: Chọn hướng xử lý

Dựa vào bản chất nhu cầu:

1. Có public Java SE API đáp ứng: ưu tiên API chuẩn.
2. Public API chưa đủ: cân nhắc thư viện được duy trì.
3. Nhu cầu đang phụ thuộc cơ chế runtime không portable: xem xét thiết kế lại, tạo adapter hoặc đưa chức năng ra process/service có contract rõ.
4. Chưa thể thay ngay: dùng ngoại lệ module-access ở phạm vi tối thiểu và có thời hạn.

Thay đổi không tương thích về output, exception hoặc lifecycle cần được ghi nhận trước khi viết code.

### Bước 4: Chia diff thành các nhóm có thể kiểm soát

Ví dụ:
- Chuyển Base64/parsing/encoding.
- Thay thao tác concurrency và Unsafe.
- Nâng framework để bỏ deep reflection vào JDK.
- Chuyển bytecode instrumentation sang version thư viện hỗ trợ JDK đích.
- Thay certificate/crypto internal provider.
- Bỏ --add-opens/--add-exports từng trường hợp.

Khi mỗi nhóm có build/test riêng, việc tìm nguyên nhân regression dễ hơn.

### Bước 5: Build và chạy trên đúng runtime

Sau khi thay, chạy:
- Compile với target Java SE phù hợp, ưu tiên `javac --release` khi dùng compiler mới cho runtime cũ.
- Unit test kiểm tra API/adapter.
- Integration test với framework, serialization, crypto, DB, XML và native dependency liên quan.
- Smoke test trên JDK/vendor và runtime image mục tiêu.
- Test các đường code dùng reflection/dynamic class loading, không chỉ startup.
- Kiểm tra performance/concurrency khi thay primitive cấp thấp.
- Dùng `jdeps --jdk-internals` trên artifact sau build để tìm những phụ thuộc tĩnh còn lại.

Đối với thư viện publish cho consumer, cần xem cả source/binary compatibility và hỗ trợ JDK thấp nhất, chứ không chỉ ứng dụng của mình chạy được.

### Bước 6: Gỡ bypass và cập nhật vận hành

Thử bỏ từng flag tạm thời; chạy lại các kịch bản liên quan. Nếu flag vẫn cần, phải có issue/owner hoặc cam kết nâng dependency. Cập nhật runbook, container args, build toolchain và các script diagnostic để không vô tình đưa flag cũ trở lại.

## 12. Kiểm tra hành vi sau khi thay API

Phép migration chỉ thành công khi **consumer quan sát được hợp đồng còn được giữ** hoặc thay đổi đã được công bố, không chỉ vì compiler im lặng.

| Thay đổi | Test nên có |
|---|---|
| Base64 | Byte fixture, padding, MIME line breaks, URL-safe, Unicode |
| Time/charset | Charset explicit, timezone/locale, đầu vào null/empty |
| Atomic/VarHandle | Atomicity, ordering, visibility, overflow, race condition |
| Reflection | Class discovery, DI, serialization, annotation, module boundary |
| Bytecode/agent | Class verification, runtime class-file version, instrumentation, startup |
| Certificate/crypto | Format, algorithm, key usage, chain validation, TLS integration |
| XML/parser | Dữ liệu mẫu, namespace, schema, external entities, lỗi invalid input |
| Native/direct memory | Lifecycle, leak, concurrency, platform/architecture và failure paths |

### 12.1. Ví dụ characterization test cho chuyển đổi codec

Nếu dữ liệu encoded đã được lưu trong database hoặc trao đổi với đối tác, lưu vài byte fixture từ phiên bản cũ. Khi migration, so sánh output của adapter mới với contract cũ. Nếu format cũ không theo Base64 chuẩn, quyết định rõ hai việc khác nhau:
- Có cần decode dữ liệu lịch sử không?
- Có cần tiếp tục tạo output theo format cũ cho consumer hiện tại không?

Không ép mọi hệ thống dùng một format mới chỉ vì API chuẩn cung cấp sẵn. Một codec có thể cần chế độ đọc tương thích dữ liệu cũ nhưng luôn ghi định dạng mới, với versioning được thỏa thuận.

### 12.2. Test regression cho reflection

Với framework sử dụng reflection, chạy các tình huống:
- Tạo object/bean từ annotation hoặc metadata.
- Serialize/deserialize object chứa field private.
- Nạp plugin/service qua đúng class loader.
- Truy cập constructor và member trên module path.
- Thử đường lỗi, không chỉ một đối tượng đơn giản.

Nếu đã loại bỏ `--add-opens`, hãy kiểm tra startup command thực tế ở staging/production. Một test chạy trên classpath có thể pass trong khi bản modular deployment vẫn lỗi.

### 12.3. Đo performance khi thay API cấp thấp

Thay Unsafe bằng AtomicLong/VarHandle có thể thay access pattern và performance. Nhưng một kết quả benchmark đơn lẻ không đủ để từ chối public API. Cần đo trong workload đại diện, phân biệt correctness requirement với micro-optimization, kiểm tra GC/memory/throughput và quyết định dựa trên ngưỡng vận hành đã công bố.

## 13. Những sai lầm thường gặp

- **Chỉ sửa lỗi bằng --add-opens:** ứng dụng chạy nhưng vẫn phụ thuộc JDK implementation detail.
- **Coi mọi com.sun.* là nội bộ:** có thể thay hoặc loại bỏ nhầm API công khai/vendor-specific được hỗ trợ.
- **Chỉ chạy jdeps một lần:** reflection qua string, generated code hoặc plugin có thể không hiện trong phân tích tĩnh.
- **Thay Unsafe bằng VarHandle theo tên method:** memory ordering và semantics có thể khác.
- **Đổi Base64 encoder nhưng quên line breaks/padding:** phá contract với client hoặc dữ liệu cũ.
- **Đọc String private value thay cho API text công khai:** dựa vào representation nội bộ có thể thay đổi.
- **Dùng privateLookupIn như một bypass của JPMS:** API này vẫn chịu access control.
- **Tự sửa code bytecode của dependency không được duy trì:** tạo maintenance burden và có thể lỗi trên class-file version mới.
- **Tin rằng thư viện mới luôn hỗ trợ JDK cũ:** cần kiểm tra minimum Java release của artifact và dependency graph.
- **Chỉ sửa compile errors:** lỗi reflection và linkage thường xuất hiện khi code path được chạy.
- **Không quản lý ngoại lệ:** flag internal access có thể bị copy vào container/CI cho nhiều process ngoài ý muốn.
- **Không phân biệt public API và thay đổi hành vi:** compile pass nhưng format/exception/transaction/serialization khác.
- **Bỏ qua security:** tự viết crypto, XML parser hoặc certificate handling thay thế có thể nguy hiểm hơn dependency cũ.

## 14. Checklist hoàn tất thay thế API nội bộ

- [ ] Đã xác định JDK/vendor/runtime floor và môi trường cần hỗ trợ.
- [ ] Đã quét artifact bằng jdeps --jdk-internals và tìm source/config reflection.
- [ ] Đã phân loại API nội bộ, public API deprecated và dependency bên thứ ba.
- [ ] Đã ghi nhu cầu thật, đường code và owner của từng usage.
- [ ] Đã ưu tiên public Java SE API nếu đáp ứng đúng hợp đồng.
- [ ] Nếu dùng thư viện ngoài, đã xác minh maintenance, security, license và Java baseline.
- [ ] Không còn dependency tĩnh vào JDK internal API ở những hạng mục đã migration.
- [ ] Các điểm deep reflection vào JDK đã được thay hoặc có ngoại lệ tạm thời được quản lý.
- [ ] Đã kiểm tra API, class-file và transitive dependency trên JDK thấp nhất còn hỗ trợ.
- [ ] Đã test output, exception, dữ liệu lịch sử và side effect của các API thay thế.
- [ ] Đã test concurrency/memory ordering nếu thay Unsafe hoặc primitive cấp thấp.
- [ ] Đã test module path, class loader, framework reflection và instrumentation nếu liên quan.
- [ ] Các --add-opens/--add-exports còn lại đều có phạm vi, owner và kế hoạch gỡ bỏ.
- [ ] Build, test, deployment và runbook phản ánh dependency và cấu hình mới.

## 15. Kết luận

API nội bộ của JDK có thể đem lại khả năng kỹ thuật hữu ích ở một phiên bản cụ thể, nhưng không phải hợp đồng ổn định cho ứng dụng. Khi Java migration làm lộ các lỗi như InaccessibleObjectException, IllegalAccessError hoặc class không còn tồn tại, hướng xử lý nên bắt đầu từ **mục đích thực sự của code**, sau đó chuyển sang **public Java SE API** hoặc **thư viện có vòng đời hỗ trợ rõ ràng**. Những giải pháp như --add-opens và --add-exports chỉ nên được dùng có giới hạn trong quá trình chuyển tiếp, không trở thành dependency ẩn trong production.

Kết hợp inventory bằng jdeps, tìm reflection ở source/config, lựa chọn replacement theo support matrix, kiểm thử hành vi trên JDK đích và gỡ dần bypass flag sẽ giúp hệ thống thoát khỏi sự phụ thuộc vào implementation detail, duy trì tính tương thích và giảm chi phí nâng cấp Java trong các release tiếp theo.
