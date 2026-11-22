# Tìm API nội bộ bằng `jdeps --jdk-internals`

Khi nâng cấp Java, một nguồn rủi ro quan trọng là ứng dụng hoặc thư viện đang sử dụng API nội bộ của JDK. Những API này có thể đã tồn tại và hoạt động trong nhiều năm, nhưng không thuộc hợp đồng Java SE công khai mà nhà cung cấp cam kết duy trì tương thích cho mọi phiên bản. Khi JDK thay đổi cách đóng gói module, đóng gói package hoặc áp dụng cơ chế đóng gói mạnh, các phụ thuộc như vậy có thể phát sinh cảnh báo, lỗi truy cập hoặc không còn hoạt động.

`jdeps` là công cụ phân tích dependency tĩnh được cung cấp trong JDK. Tùy chọn `--jdk-internals` giúp tìm các tham chiếu trong bytecode tới API nội bộ của JDK. Đây là một bước hữu ích trong quá trình kiểm kê và migration, đặc biệt trước khi nâng từ các phiên bản Java cũ lên Java 9 trở lên hoặc khi chuẩn bị sử dụng một feature release mới.

## 1. API nội bộ của JDK là gì?

JDK có những package và lớp được cung cấp như API tiêu chuẩn của Java SE. Đây là bề mặt mà ứng dụng có thể dựa vào theo đặc tả và chính sách tương thích của nền tảng. Bên cạnh đó, JDK còn có các API phục vụ chính implementation của JVM, công cụ JDK hoặc thành phần nội bộ của thư viện nền tảng.

Các API nội bộ thường có một hoặc nhiều đặc điểm:

- Không được mô tả như API công khai của Java SE.
- Có thể thay đổi hoặc bị loại bỏ giữa các feature release.
- Có thể nằm trong package/module không được export cho ứng dụng thông thường.
- Có thể chỉ được giữ lại để tương thích với một số công cụ hoặc thành phần cũ.
- Có thể yêu cầu cờ mở quyền truy cập trong một số phiên bản JDK trước đây, rồi bị đóng gói mạnh hơn ở phiên bản mới.

Ví dụ về những API từng được nhiều ứng dụng sử dụng gồm `sun.misc.Unsafe`, `sun.misc.BASE64Encoder`, `sun.reflect.Reflection` hoặc các lớp trong những package nội bộ khác. Danh sách cụ thể phụ thuộc vào JDK và phiên bản đang phân tích.

Không nên kết luận mọi package bắt đầu bằng `com.sun` hoặc `sun` đều có cùng trạng thái. Một số API có tên package lịch sử nhưng vẫn là API được tài liệu hóa trong một module JDK cụ thể; ngược lại, một số API nội bộ không dễ nhận diện chỉ bằng tên package. Hãy dùng kết quả phân tích của JDK và tài liệu chính thức để xác định trạng thái của từng API.

## 2. Vì sao API nội bộ gây rủi ro khi migration?

Ứng dụng dùng API nội bộ đang phụ thuộc vào một chi tiết của implementation JDK. Nhà cung cấp JDK có thể thay đổi chi tiết đó khi sửa lỗi, cải thiện bảo mật, thay đổi kiến trúc hoặc loại bỏ thành phần cũ.

Rủi ro thường xuất hiện theo các dạng sau:

1. **Không biên dịch được:** lớp hoặc method nội bộ không còn tồn tại hay không còn truy cập được.
2. **Không liên kết được khi chạy:** bytecode tham chiếu tới một lớp hoặc method đã bị loại bỏ, dẫn đến lỗi linkage như `NoClassDefFoundError`, `NoSuchMethodError` hoặc lỗi liên quan.
3. **Không truy cập được do đóng gói module:** package không được export/open cho module đang gọi, có thể phát sinh `IllegalAccessError` hoặc lỗi reflective access.
4. **Hành vi thay đổi:** API vẫn tồn tại nhưng hành vi, giới hạn, thread-safety hoặc chi tiết thực thi thay đổi.
5. **Khó chuyển vendor hoặc runtime:** ứng dụng phụ thuộc vào một hành vi chỉ có ở một bản build, cấu hình hoặc implementation cụ thể.

Từ Java 9, Java Platform Module System (JPMS) tạo ranh giới module rõ ràng. JEP 260 đặt định hướng đóng gói phần lớn API nội bộ. JEP 403, được áp dụng trong Java 17, hoàn tất việc đóng gói mạnh phần lớn nội bộ JDK. Một số package được giữ trong module `jdk.unsupported` để hỗ trợ các API như `sun.misc.Unsafe`, nhưng sự tồn tại đó không biến chúng thành API Java SE ổn định.

Do đó, việc một ứng dụng chạy được trên JDK cũ không chứng minh nó sẽ chạy trên JDK mới. Cần tìm và xử lý phụ thuộc trước khi chuyển môi trường production.

## 3. `jdeps` làm gì?

`jdeps` phân tích dependency ở cấp class/package/module dựa trên bytecode Java. Khi bật `--jdk-internals`, công cụ tìm những tham chiếu tĩnh tới API nội bộ mà nó nhận diện trong JDK.

Lệnh cơ bản:

```bash
jdeps --jdk-internals path/to/application.jar
```

Đầu vào có thể là file `.class`, thư mục chứa class đã biên dịch hoặc file JAR. Có thể phân tích từng thư viện riêng hoặc artifact ứng dụng. Nên dùng `jdeps` từ JDK mục tiêu hoặc JDK có cơ sở phân tích phù hợp với phiên bản đang migration, vì tập API nội bộ và thông tin module thay đổi theo phiên bản JDK.

Ví dụ trên Linux/macOS:

```bash
"$JAVA_HOME/bin/jdeps" --jdk-internals build/libs/application.jar
```

Ví dụ trên Windows PowerShell:

```powershell
& "$env:JAVA_HOME\bin\jdeps.exe" --jdk-internals .\build\libs\application.jar
```

Nếu lệnh `jdeps` đã nằm trên `PATH`, có thể gọi trực tiếp mà không cần chỉ rõ đường dẫn tới thư mục `bin`.

## 4. Đọc kết quả `--jdk-internals`

Khi tìm thấy tham chiếu, `jdeps` thường nhóm kết quả dưới phần có tên `JDK Internal API`. Tùy phiên bản JDK, đầu ra có thể thể hiện class của ứng dụng, API nội bộ được tham chiếu, module liên quan và gợi ý thay thế.

Ví dụ minh họa về dạng thông tin cần chú ý:

```text
JDK Internal API
   com.example.buffer.LegacyBuffer -> sun.misc.Unsafe
   com.example.codec.LegacyCodec   -> sun.misc.BASE64Encoder

Warning: JDK internal APIs are unsupported and may be removed
```

Đây là ví dụ rút gọn để giải thích cách đọc; nội dung, cách nhóm và thông báo chính xác phụ thuộc phiên bản `jdeps` cùng các class được phân tích.

Khi đọc một kết quả, cần xác định:

- **Class sử dụng API:** lớp nào trong ứng dụng hoặc thư viện đang tạo tham chiếu.
- **API nội bộ:** lớp, interface hoặc method nào của JDK đang bị sử dụng.
- **Nguồn phụ thuộc:** tham chiếu nằm trong mã nguồn của dự án hay trong một dependency bên thứ ba.
- **Gợi ý thay thế:** công cụ có đưa ra API công khai hoặc module thay thế hay không.
- **Mức độ ảnh hưởng:** API có còn tồn tại trong JDK mục tiêu không, có bị đóng gói mạnh không, và có đường thay thế phù hợp với hành vi hiện tại không.

Không nên xem cảnh báo là kết luận rằng ứng dụng chắc chắn sẽ lỗi ngay. Cảnh báo cho biết có phụ thuộc vào API không được bảo đảm ổn định. Cần kết hợp kết quả với phiên bản JDK mục tiêu, cách truy cập API và kiểm thử runtime để xác định rủi ro cụ thể.

## 5. Các tùy chọn thường dùng khi phân tích

### 5.1. Phân tích JAR ứng dụng

```bash
jdeps --jdk-internals build/libs/application.jar
```

Đây là điểm bắt đầu đơn giản. Nó giúp phát hiện tham chiếu nội bộ trong bytecode của artifact được chỉ định.

### 5.2. Phân tích dependency đệ quy

```bash
jdeps --jdk-internals --recursive \
  --class-path "lib/*" \
  build/libs/application.jar
```

`--recursive` yêu cầu phân tích dependency theo phạm vi classpath được cung cấp. `--class-path` giúp `jdeps` tìm các dependency bên ngoài mà ứng dụng tham chiếu. Trên Windows, dấu phân cách các phần tử classpath là dấu chấm phẩy (`;`); trên Linux/macOS thường là dấu hai chấm (`:`). Wildcard classpath như `lib/*` giúp đưa các JAR trong thư mục vào phạm vi phân tích.

Nếu ứng dụng sử dụng module path, cung cấp đường dẫn module phù hợp bằng `--module-path`:

```bash
jdeps --jdk-internals --recursive \
  --module-path "mods:lib" \
  --module com.example.application
```

Tên module, đường dẫn và cú pháp cần điều chỉnh theo cách đóng gói thực tế. Với ứng dụng classpath thông thường, không cần thêm `--module-path`.

### 5.3. Phân tích thư mục class đã biên dịch

```bash
jdeps --jdk-internals build/classes/java/main
```

Lệnh này hữu ích khi muốn kiểm tra output biên dịch trước khi tạo JAR. Với dự án đa module, cần phân tích từng output directory hoặc artifact tương ứng; một lần chạy trên một module không đại diện cho toàn bộ repository.

### 5.4. Phân tích multi-release JAR

JAR đa phiên bản có thể chứa các class khác nhau theo phiên bản Java trong các thư mục như `META-INF/versions/9/` hoặc cao hơn. Khi cần phân tích view của một runtime cụ thể, có thể dùng `--multi-release`:

```bash
jdeps --jdk-internals --multi-release 21 library.jar
```

Chọn giá trị phù hợp với phiên bản JDK đang đánh giá và cấu trúc multi-release JAR. Nếu không chỉ định đúng phiên bản, kết quả có thể không phản ánh class variant được JVM mục tiêu lựa chọn.

### 5.5. Lưu kết quả để so sánh

```bash
jdeps --jdk-internals application.jar > jdeps-internals.txt 2>&1
```

Lưu output giúp so sánh trước/sau migration và gắn bằng chứng với commit, JDK build, artifact hash và môi trường phân tích. Không nên chỉ lưu ảnh chụp màn hình hoặc chép vài dòng cảnh báo mà bỏ mất thông tin phiên bản công cụ.

## 6. Quy trình tìm API nội bộ trong một dự án thực tế

Một lần chạy `jdeps` trên JAR chính thường chưa đủ. Ứng dụng có thể dùng API nội bộ thông qua một thư viện thứ ba, plugin hoặc một module nội bộ khác.

### Bước 1: Chọn JDK dùng để phân tích

Xác định feature release mục tiêu và chạy `jdeps` từ JDK tương ứng. Ghi lại phiên bản công cụ:

```bash
jdeps --version
java -version
```

Nếu cần kiểm tra khả năng chạy trên nhiều feature release, thực hiện phân tích riêng cho từng JDK mục tiêu và giữ output tách biệt.

### Bước 2: Xác định đầy đủ artifact cần quét

Liệt kê:

- JAR do module hiện tại tạo ra.
- Các module nội bộ mà ứng dụng phụ thuộc.
- Dependency bên thứ ba nằm trong runtime classpath.
- Plugin hoặc agent được nạp trong môi trường thực tế nếu chúng nằm trong phạm vi migration.
- Các artifact được tải động hoặc triển khai tách khỏi ứng dụng chính.

Đừng giả định dependency không nằm trong source repository thì không cần kiểm tra. Một thư viện bên thứ ba vẫn có thể chứa tham chiếu tới API nội bộ và làm ứng dụng gặp lỗi trên JDK mục tiêu.

### Bước 3: Chạy phân tích với dependency path phù hợp

Chạy `jdeps --jdk-internals` trên artifact chính, sau đó mở rộng sang classpath hoặc module path cần thiết. Nếu dependency không thể resolve, xác minh đường dẫn và artifact trước khi diễn giải kết quả. Không nên bỏ qua lỗi phân giải rồi kết luận rằng báo cáo đã bao phủ toàn bộ dependency graph.

### Bước 4: Ghi nhận từng phát hiện

Tạo danh sách có các trường: artifact, class sử dụng, API nội bộ, dependency owner, JDK phát hiện, JDK mục tiêu, gợi ý thay thế, mức độ ưu tiên và trạng thái xử lý.

### Bước 5: Xác định chủ sở hữu

Nếu tham chiếu nằm trong mã nguồn của nhóm, nhóm có thể chủ động thay thế. Nếu nó nằm trong thư viện bên thứ ba, cần kiểm tra phiên bản mới, issue tracker và release notes của thư viện. Nếu chưa có bản sửa, cân nhắc nâng cấp, thay thư viện, cô lập dependency hoặc trì hoãn migration có thời hạn.

### Bước 6: Sửa và kiểm thử

Thay API nội bộ bằng API tiêu chuẩn hoặc API được hỗ trợ phù hợp. Sau đó chạy build, test và integration test trên JDK mục tiêu. Chạy lại `jdeps --jdk-internals` để xác nhận tham chiếu tĩnh đã được loại bỏ trong phạm vi quét.

### Bước 7: Lưu bằng chứng migration

Lưu phiên bản JDK, distribution, lệnh đã chạy, artifact được quét, classpath/module path, output và danh sách ngoại lệ đã được chấp thuận. Báo cáo phải nêu rõ những vùng chưa được phân tích để tránh tạo cảm giác bao phủ tuyệt đối.

## 7. Ví dụ thay thế một số API nội bộ phổ biến

`jdeps` có thể gợi ý API thay thế cho một số phát hiện. Gợi ý cần được đánh giá theo mục đích sử dụng và phiên bản Java tối thiểu của dự án.

| API nội bộ thường gặp | API/cách tiếp cận được hỗ trợ nên xem xét | Lưu ý migration |
|---|---|---|
| `sun.misc.BASE64Encoder` và `sun.misc.BASE64Decoder` | `java.util.Base64` | Chọn encoder/decoder cơ bản, URL-safe hoặc MIME đúng định dạng dữ liệu cũ. |
| `sun.misc.Cleaner` | `java.lang.ref.Cleaner` | Đánh giá lifecycle, thời điểm cleanup và cách quản lý resource; cleanup không thay thế `close()` xác định. |
| `sun.reflect.Reflection` để lấy caller | `StackWalker` | Xác định mục đích thực sự, vì stack inspection có thể thay đổi về hiệu năng và cách biểu diễn frame. |
| `sun.misc.Unsafe` cho truy cập bộ nhớ/field | `VarHandle`, các API `java.lang.invoke`, hoặc Foreign Function & Memory API khi phù hợp | Không phải mọi thao tác đều có phép thay thế một-một; cần kiểm tra memory ordering, alignment, lifetime và hiệu năng. |
| `com.sun.image.codec.jpeg` | `javax.imageio.ImageIO` | Kiểm tra chất lượng ảnh, metadata, color model và hành vi encode/decode. |

Ví dụ chuyển Base64 sang API chuẩn:

```java
import java.util.Base64;

public final class TokenCodec {
    public String encode(byte[] value) {
        return Base64.getEncoder().encodeToString(value);
    }

    public byte[] decode(String encoded) {
        return Base64.getDecoder().decode(encoded);
    }
}
```

Nếu dữ liệu cũ dùng MIME line wrapping hoặc URL-safe alphabet, cần chọn `getMimeEncoder()` hoặc `getUrlEncoder()` tương ứng. Chỉ thay tên lớp mà không kiểm tra định dạng có thể làm token, file hoặc message không tương thích với dữ liệu đã lưu.

Ví dụ dùng `StackWalker` thay cho API nội bộ để quan sát caller:

```java
import java.lang.StackWalker;

public final class CallerInspector {
    private static final StackWalker WALKER =
            StackWalker.getInstance(StackWalker.Option.RETAIN_CLASS_REFERENCE);

    public Class<?> callerClass() {
        return WALKER.walk(frames -> frames
                .skip(1)
                .findFirst()
                .map(StackWalker.StackFrame::getDeclaringClass)
                .orElse(Object.class));
    }
}
```

Ví dụ này chỉ minh họa cách truy cập stack bằng API công khai. Cần điều chỉnh số frame bị bỏ qua theo call path thật và cân nhắc liệu logic nghiệp vụ có nên phụ thuộc vào caller hay không.

## 8. Trường hợp `sun.misc.Unsafe` và module `jdk.unsupported`

`sun.misc.Unsafe` là ví dụ quan trọng vì nó vẫn có thể xuất hiện trong JDK hiện đại thông qua module `jdk.unsupported`. Một số thư viện hiệu năng cao từng sử dụng lớp này cho thao tác bộ nhớ, atomic operation hoặc truy cập field.

Việc lớp còn tồn tại không có nghĩa nó là API Java SE được hỗ trợ ổn định. `jdeps --jdk-internals` vẫn có thể báo cáo tham chiếu này để cảnh báo consumer đang dựa vào API nội bộ.

Khi xử lý phát hiện `Unsafe`, cần tìm đúng thao tác đang dùng:

- Atomic access và memory ordering có thể phù hợp với `VarHandle`.
- Truy cập field theo offset cần đánh giá `VarHandle`, reflection được hỗ trợ hoặc thiết kế lại abstraction.
- Quản lý bộ nhớ ngoài heap cần xem xét Foreign Function & Memory API theo feature release mục tiêu.
- Các thao tác phụ thuộc vào layout hoặc hành vi đặc thù của JVM có thể cần thiết kế lại và kiểm thử hiệu năng.

Không nên thay toàn bộ `Unsafe` bằng một API khác theo kiểu máy móc. Đặc biệt, Foreign Function & Memory API đã thay đổi qua các phiên bản Java trước khi trở thành API ổn định; phải dùng tài liệu của đúng JDK mục tiêu để chọn API phù hợp.

## 9. Giới hạn của `jdeps --jdk-internals`

`jdeps` là công cụ phân tích bytecode tĩnh. Nó rất hữu ích, nhưng không chứng minh rằng ứng dụng hoàn toàn không phụ thuộc vào API nội bộ.

### 9.1. Không phát hiện đầy đủ truy cập reflection động

Ví dụ:

```java
Class<?> type = Class.forName("sun.misc.Unsafe");
```

Tên lớp là một chuỗi. Bytecode có thể không chứa symbolic reference theo cách mà `jdeps` nhận diện như một dependency lớp thông thường. Tương tự, các lời gọi `Class.getDeclaredMethod`, `setAccessible`, method handle được tạo từ tên chuỗi hoặc cấu hình reflection có thể không được phát hiện đầy đủ.

### 9.2. Không phân tích mã native

JNI, thư viện native, mã C/C++ hoặc agent native có thể truy cập chi tiết JVM và hệ điều hành ngoài phạm vi bytecode Java mà `jdeps` phân tích.

### 9.3. Không thể biết mọi class được tải động

Plugin, script engine, class loader tùy chỉnh, bytecode được sinh trong runtime hoặc artifact tải từ xa có thể không nằm trong tập file đầu vào. Nếu không đưa chúng vào phạm vi quét, kết quả không thể phản ánh dependency của chúng.

### 9.4. Không chứng minh hành vi runtime

Một tham chiếu tĩnh được tìm thấy không cho biết code path đó có được thực thi trong production hay không. Ngược lại, không tìm thấy tham chiếu cũng không chứng minh mọi luồng chạy đều an toàn. Cần kết hợp static analysis với test và quan sát runtime.

### 9.5. Không đánh giá đầy đủ dependency chưa resolve

Nếu classpath thiếu JAR hoặc module cần thiết, phân tích có thể không bao phủ dependency graph như mong muốn. Phải xử lý cảnh báo hoặc lỗi resolve, ghi rõ phần bị thiếu và chạy lại với đường dẫn chính xác.

### 9.6. Không phân loại mọi API ngoài Java SE

`--jdk-internals` tập trung vào API nội bộ của JDK. Một dependency bên thứ ba, API của framework, API `javax.*` cũ hoặc API độc quyền của vendor không nhất thiết được báo cáo như JDK internal API. Các nhóm phụ thuộc này cần công cụ và quy trình kiểm kê riêng.

## 10. Bổ sung kiểm tra ngoài `jdeps`

Để tăng độ bao phủ, kết hợp `jdeps` với các phương pháp sau:

| Phương pháp | Mục đích |
|---|---|
| Source search | Tìm import `sun.*`, package nội bộ, tên lớp trong string và lời gọi reflection. |
| Dependency inventory | Xác định toàn bộ JAR, plugin, agent và thư viện native đi cùng ứng dụng. |
| API compatibility tool | Kiểm tra thay đổi API công khai giữa các phiên bản thư viện. |
| Static analysis/forbidden API rule | Ngăn mã nguồn mới tham chiếu các package/API nội bộ đã cấm. |
| Integration test trên JDK mục tiêu | Phát hiện lỗi truy cập, linkage và hành vi chỉ xuất hiện lúc chạy. |
| Runtime observation | Theo dõi lỗi reflective access, linkage, class loading và cảnh báo JVM trong môi trường gần production. |

Có thể dùng tìm kiếm source như một bước sàng lọc:

```bash
rg -n "sun\\.|com\\.sun\\.|Class\.forName|setAccessible" src
```

Kết quả tìm kiếm có thể chứa false positive và cũng không bao phủ mã đã biên dịch trong dependency. Cần đọc từng phát hiện, phân biệt API nội bộ thực sự với API được hỗ trợ có tên package lịch sử.

Một rule như Forbidden APIs có thể giúp build thất bại khi mã nguồn mới tham chiếu tới API bị cấm. Rule cần được cấu hình theo chính sách dự án, feature release và ngoại lệ đã được duyệt. Không nên thêm danh sách cấm quá rộng khiến API công khai hợp lệ bị chặn.

## 11. Xử lý khi chưa thể loại bỏ API nội bộ

Đôi khi thư viện bên thứ ba chưa có phiên bản thay thế, hoặc việc thay thế API nội bộ đòi hỏi thay đổi kiến trúc và kiểm thử hiệu năng đáng kể. Khi đó, cần quản lý phát hiện như một khoản nợ kỹ thuật có chủ sở hữu và thời hạn.

Một bản ghi ngoại lệ nên có:

- Artifact và phiên bản chứa API nội bộ.
- Tên API và class tạo tham chiếu.
- JDK hiện tại và các JDK mục tiêu bị ảnh hưởng.
- Consumer và luồng nghiệp vụ liên quan.
- Lý do chưa thể thay thế và các lựa chọn đã xem xét.
- Biện pháp giảm thiểu, ví dụ pin phiên bản dependency hoặc cô lập module.
- Owner, ngày rà soát tiếp theo và điều kiện đóng ngoại lệ.

Không nên coi `--add-exports` hoặc `--add-opens` là giải pháp migration lâu dài mặc định. Các tùy chọn này có thể mở quyền truy cập cho một số trường hợp cụ thể, nhưng chúng tạo thêm cấu hình runtime/build và phụ thuộc vào cấu trúc module của JDK. Nếu phải dùng tạm, cần ghi rõ package/module, lý do, môi trường áp dụng, owner và kế hoạch loại bỏ.

Với Java 17 trở lên, cờ `--illegal-access` không còn khôi phục cơ chế mở rộng toàn cục như giai đoạn chuyển tiếp trước đó. Không nên dựa vào cờ này để xử lý lỗi truy cập nội bộ trên JDK hiện đại. Cần xác định chính xác package/module và chọn thay thế hoặc mở quyền có phạm vi tối thiểu nếu tình huống thật sự yêu cầu.

## 12. Checklist trước khi hoàn tất kiểm tra API nội bộ

- [ ] Đã chạy `jdeps --jdk-internals` bằng JDK mục tiêu và lưu phiên bản công cụ.
- [ ] Đã quét artifact chính, module nội bộ và dependency cần thiết.
- [ ] Đã cung cấp classpath hoặc module path chính xác; xử lý các dependency không resolve.
- [ ] Đã ghi nhận class sử dụng, API nội bộ, artifact owner và gợi ý thay thế.
- [ ] Đã phân biệt tham chiếu trong mã nguồn của dự án với tham chiếu từ thư viện bên thứ ba.
- [ ] Đã thay thế bằng API công khai phù hợp hoặc lập ngoại lệ có owner và thời hạn.
- [ ] Đã kiểm tra reflection, JNI, dynamic loading và các vùng `jdeps` không thể bao phủ.
- [ ] Đã chạy build, test và integration test trên JDK mục tiêu.
- [ ] Đã chạy lại phân tích sau khi sửa và lưu kết quả cuối cùng.
- [ ] Đã ghi rõ phạm vi chưa được quét và rủi ro còn lại.

## Kết luận

`jdeps --jdk-internals` giúp phát hiện tham chiếu tĩnh từ bytecode tới API nội bộ của JDK, qua đó hỗ trợ khoanh vùng rủi ro trước khi nâng cấp Java. Kết quả cần được đọc theo artifact, class sử dụng, API bị tham chiếu và JDK mục tiêu; sau đó xác định API thay thế, owner và kiểm thử phù hợp. Vì `jdeps` không bao phủ đầy đủ reflection động, JNI, class tải trong runtime hoặc mọi dependency chưa được resolve, nó phải là một phần của quy trình phân tích kết hợp source search, dependency inventory và kiểm thử trên JDK mục tiêu. Khi lưu cả lệnh, phiên bản công cụ, phạm vi quét và ngoại lệ, nhóm có thể biến việc tìm API nội bộ thành một bước kiểm soát migration có thể lặp lại.
