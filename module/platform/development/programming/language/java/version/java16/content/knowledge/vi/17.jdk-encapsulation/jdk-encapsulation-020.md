# Xác minh ứng dụng chạy bằng API công khai sau khi bỏ ngoại lệ không cần thiết

Khi ứng dụng được nâng lên JDK hiện đại, các tùy chọn như `--add-exports`, `--add-opens` và `--add-reads` đôi khi vẫn còn trong script khởi chạy từ giai đoạn migration. Một số tùy chọn là workaround hợp lý trong thời gian chuyển đổi, nhưng nếu giữ lại mà không biết lý do, chúng có thể che giấu dependency vào JDK internal API hoặc mở quyền truy cập rộng hơn mức ứng dụng cần.

Mục tiêu của việc xác minh là chứng minh ứng dụng và thư viện của nó hoạt động với API được hỗ trợ, sau khi bỏ từng ngoại lệ không còn cần thiết. Hãy kết hợp phân tích bytecode bằng `jdeps`, rà soát reflection và JVM flags, rồi chạy build/test/integration test trên đúng JDK mục tiêu mà không có các workaround đã loại bỏ.

## 1. Phân biệt public Java API với class có modifier `public`

Một class có modifier `public` chưa chắc là API công khai được Java SE bảo đảm. Ví dụ, class trong package `sun.*` hoặc `jdk.internal.*` có thể nhìn thấy được trong một cấu hình module cụ thể, nhưng đó vẫn là JDK internal API. Nhà phát triển không nên phụ thuộc vào nó như phụ thuộc vào API được mô tả trong Java SE API Specification.

Khi đánh giá một API, hãy kiểm tra cả ba điều:

1. **Package và module:** package có thuộc module được hỗ trợ và được export cho ứng dụng không?
2. **Tài liệu API:** kiểu và phương thức có được mô tả trong Java SE API hoặc tài liệu công khai, có cam kết tương thích phù hợp không?
3. **Cách truy cập:** ứng dụng đang gọi public API bình thường hay đang dùng reflection để truy cập implementation detail/private member?

Ví dụ `java.util.Base64` là API công khai của Java SE. Ngược lại, việc có thể truy cập một class `sun.*` nhờ `--add-exports` không biến class đó thành Java SE API.

## 2. Lập danh sách tất cả ngoại lệ module đang được sử dụng

Trước khi thay đổi, tìm mọi nơi có thể truyền JVM options:

- Script chạy ứng dụng như `.bat`, `.ps1`, `.sh`.
- Dockerfile, image entrypoint, Kubernetes manifest và cấu hình container.
- Service manager, systemd unit, Windows service wrapper và CI/CD variables.
- IDE run configuration, application server và test runner.
- Biến môi trường `JDK_JAVA_OPTIONS`, `JAVA_TOOL_OPTIONS` và `_JAVA_OPTIONS`.
- Cấu hình build/test truyền JVM arguments cho forked process.

Tìm các tùy chọn thường dùng làm workaround:

| Tùy chọn | Mục đích | Câu hỏi khi audit |
| --- | --- | --- |
| `--add-reads` | Bổ sung readability giữa các module. | Dependency nào cần cạnh đọc này? Có thể khai báo `requires` hoặc đóng gói dependency đúng module path không? |
| `--add-exports` | Export package cho module khác ở compile/runtime. | Package đó có phải API được hỗ trợ không? Có thể thay bằng API công khai không? |
| `--add-opens` | Cho phép deep reflection vào package ở runtime. | Framework nào cần reflection, trên package nào, và có thể dùng qualified `opens` không? |
| `--illegal-access` | Tùy chọn tương thích cũ cho truy cập nội bộ JDK. | Có đang dựa vào một tùy chọn đã mất tác dụng không? |

Ghi lại từng option cùng module nguồn, package, target module, thư viện liên quan và người chịu trách nhiệm. Đừng xóa hàng loạt trước khi hiểu lý do nó được thêm vào.

## 3. Dùng `jdeps --jdk-internals` để tìm tham chiếu JDK nội bộ

`jdeps` là công cụ phân tích dependency ở cấp class và module, đi kèm JDK. Tùy chọn `--jdk-internals` báo cáo các tham chiếu tới JDK internal API có thể phát hiện trong bytecode.

Với ứng dụng chạy trên classpath và thư viện trong thư mục `lib`:

```powershell
jdeps --jdk-internals --recursive --class-path "lib/*" app.jar
```

Với ứng dụng modular nằm trên module path:

```powershell
jdeps --jdk-internals --recursive --module-path mods --module com.example.app
```

Nếu ứng dụng phát hành multi-release JAR, chỉ định phiên bản runtime cần phân tích bằng `--multi-release` để công cụ xét đúng các class version tương ứng:

```powershell
jdeps --jdk-internals --multi-release 17 --class-path "lib/*" app.jar
```

Thay `17` bằng phiên bản Java mục tiêu của sản phẩm. Dùng cùng JDK toolchain với môi trường kiểm thử hoặc một JDK tương thích có hỗ trợ phân tích class version đó.

Kết quả có thể chỉ ra class nào tham chiếu package nội bộ và gợi ý API thay thế khi có. Hãy phân tích cả dependency trực tiếp lẫn thư viện bên thứ ba; ứng dụng có thể không gọi internal API trực tiếp nhưng một thư viện cũ vẫn có thể làm điều đó.

`jdeps` là bước rà soát tĩnh, không phải chứng minh đầy đủ rằng không còn truy cập nội bộ. Nó không thể phát hiện chắc chắn mọi trường hợp reflection được dựng từ tên class dạng chuỗi, class được sinh động lúc chạy, native code hoặc hành vi của agent/framework. Vì vậy, kết quả không có cảnh báo là tín hiệu tốt, nhưng vẫn phải kiểm thử runtime.

## 4. Phân tích module dependency và descriptor

Với ứng dụng modular, dùng `jdeps --check` để xem module descriptor, dependency và các cảnh báo liên quan:

```powershell
jdeps --check com.example.app --module-path mods
```

Lệnh này hỗ trợ kiểm tra cấu hình module của ứng dụng. Kết hợp với `jdeps --jdk-internals` để tìm internal API; hai lệnh trả lời hai câu hỏi khác nhau:

- `--check`: module dependency và descriptor có phù hợp với các module được resolve không?
- `--jdk-internals`: bytecode có tham chiếu tới JDK internal API không?

Đọc lại `module-info.java` và chỉ khai báo dependency mà module thực sự sử dụng. `requires transitive` chỉ nên dùng khi API public của module hiện tại làm lộ kiểu từ dependency đó cho consumer. Tránh thêm `requires` chỉ để làm cho một lỗi runtime biến mất mà không hiểu quan hệ module.

## 5. Rà soát API deprecated riêng với internal API

API deprecated và JDK internal API là hai nhóm khác nhau. Một API Java SE có thể được đánh dấu deprecated nhưng vẫn là API công khai; ngược lại, một API internal có thể chưa deprecated nhưng vẫn không được bảo đảm tương thích.

Dùng `jdeprscan` để rà soát việc sử dụng API deprecated:

```powershell
jdeprscan --release 17 --class-path "lib/*" app.jar
```

Thay `17` bằng release mục tiêu. Kết quả này bổ sung cho `jdeps --jdk-internals`; không dùng nó thay thế việc tìm internal API. Với cảnh báo deprecated, đọc tài liệu API để biết API có bị đánh dấu for removal hay có phương án thay thế nào được khuyến nghị.

## 6. Kiểm tra reflection và truy cập động

`jdeps` chủ yếu phân tích tham chiếu có thể nhận diện trong bytecode. Reflection có thể giấu tên class hoặc package trong chuỗi, cấu hình XML/JSON, annotation, file service hoặc metadata của framework.

Rà soát các điểm thường gặp:

```java
Class.forName(className);
type.getDeclaredField("value");
field.setAccessible(true);
method.trySetAccessible();
MethodHandles.privateLookupIn(targetType, lookup);
```

Các API trên không mặc định là sai. Chúng trở thành vấn đề khi code cần vượt qua ranh giới module để truy cập implementation detail hoặc thành viên không được mở.

Hãy kiểm tra:

- Tên class/package có thuộc JDK internal package như `sun.*` hoặc `jdk.internal.*` không?
- Framework có dùng `setAccessible(true)` để truy cập private field của JDK class không?
- `privateLookupIn` có cần package được mở cho module caller không?
- Framework có phiên bản mới dùng public API hoặc module descriptor rõ ràng không?
- Cấu hình serializer/ORM có thể chuyển sang constructor, accessor hoặc adapter công khai không?

`trySetAccessible()` trả `false` khi quyền truy cập không thể được bật; đừng bỏ qua giá trị này rồi giả định reflection đã thành công. Với `setAccessible(true)`, truy cập sâu bị module system chặn có thể ném `InaccessibleObjectException`.

## 7. Thay internal API bằng API được hỗ trợ

Không có một API thay thế chung cho mọi JDK internal API. Hãy chọn theo chức năng thực sự mà ứng dụng cần:

| Phụ thuộc cũ | Hướng thay thế |
| --- | --- |
| `sun.misc.BASE64Encoder` hoặc `sun.misc.BASE64Decoder` | `java.util.Base64` với encoder/decoder phù hợp. |
| Truy cập file qua class trong `sun.nio.*` | Dùng `java.nio.file.Path`, `Files`, `FileSystem` và các API NIO công khai. |
| Dùng `sun.misc.Unsafe` cho thao tác kiểu dữ liệu/atomic được hỗ trợ | Xem xét `VarHandle`, `ByteBuffer` hoặc API Java SE phù hợp; không giả định có thay thế drop-in cho mọi khả năng của `Unsafe`. |
| Reflection vào private field của JDK collection/date/time | Dùng public accessor, constructor, factory hoặc API chuyển đổi được tài liệu hóa. |
| Dựa vào implementation class cụ thể của JDK | Dựa vào interface/API công khai như `List`, `Map`, `Path`, `ExecutorService`. |

Ví dụ thay Base64 cũ bằng Java SE API:

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

class Base64Example {
    static String encode(String value) {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        return Base64.getEncoder().encodeToString(bytes);
    }

    static String decode(String encoded) {
        byte[] bytes = Base64.getDecoder().decode(encoded);
        return new String(bytes, StandardCharsets.UTF_8);
    }
}
```

Đừng thay một internal API bằng một API khác chỉ vì API mới cũng public trong một package nội bộ. Xác nhận package và kiểu được mô tả trong Java SE API hoặc tài liệu chính thức của nhà cung cấp thư viện.

## 8. Phân biệt quyền mở package của ứng dụng với việc truy cập JDK internals

Không phải mọi `--add-opens` đều có nghĩa ứng dụng đang dùng JDK internal API. Framework có thể cần reflection vào model do chính ứng dụng sở hữu. Ví dụ module ứng dụng có thể mở package model có chọn lọc cho module serializer:

```java
module com.example.app {
    requires com.example.json;

    exports com.example.app.api;
    opens com.example.app.model to com.example.json;
}
```

Đây là quyền mở package của ứng dụng cho framework đã biết; nó khác với mở `java.base/java.lang` hoặc `java.base/java.util` cho mọi code trên classpath. Nếu framework nằm trên classpath trong giai đoạn migration, `--add-opens com.example.app/com.example.app.model=ALL-UNNAMED` có thể là cầu nối tạm thời. Khi framework trở thành named module, thu hẹp quyền sang tên module cụ thể.

Nếu mục tiêu là ứng dụng chỉ dùng public API, hãy bỏ các quyền mở vào package JDK nội bộ. Giữ một qualified `opens` vào package model của chính ứng dụng khi framework thực sự cần deep reflection có thể vẫn là thiết kế hợp lệ; ghi rõ lý do và phạm vi quyền đó.

## 9. Bỏ workaround theo từng bước có thể kiểm soát

Thực hiện migration trong nhánh thay đổi có thể review và chạy test sau mỗi bước:

1. **Chụp baseline:** lưu JVM flags hiện tại, kết quả build/test, startup log và các luồng nghiệp vụ quan trọng.
2. **Chạy phân tích tĩnh:** chạy `jdeps --jdk-internals` trên app và dependency; chạy `jdeprscan` riêng nếu cần rà deprecated API.
3. **Phân loại từng flag:** xác định flag đang mở package JDK, package ứng dụng hay tạo readability cho dependency classpath.
4. **Nâng thư viện:** cập nhật framework/driver/serializer có hỗ trợ JDK mục tiêu và module system.
5. **Thay API nội bộ:** sửa code sang API công khai, kiểm tra hành vi tương đương và các khác biệt dữ liệu.
6. **Gỡ từng flag:** bỏ một nhóm workaround, chạy test và xác nhận lỗi nếu có; không xóa toàn bộ flags cùng lúc.
7. **Kiểm thử không workaround:** chạy đúng artifact với JVM flags đã loại bỏ, trên JDK mục tiêu.
8. **Rà lại cấu hình triển khai:** xác nhận không có biến môi trường hoặc wrapper tự thêm lại flags.
9. **Ghi nhận phần còn lại:** với ngoại lệ thật sự cần thiết, ghi module nguồn, package, target, lý do, owner và kế hoạch loại bỏ.

Khi một flag bị bỏ làm ứng dụng lỗi, stack trace và module/package trong lỗi sẽ giúp xác định dependency còn lại. Không khôi phục ngay một quyền `ALL-UNNAMED` rộng; hãy xác định consumer cụ thể và chọn `requires`, `exports` hoặc `opens` đúng loại.

## 10. Chạy ứng dụng trên JDK mục tiêu mà không có ngoại lệ

Tạo một cấu hình kiểm thử sạch, bỏ các tùy chọn đã xác định là không cần thiết. Ví dụ ứng dụng trên classpath:

```powershell
java --class-path "app.jar;lib/*" com.example.Main
```

Ứng dụng modular:

```powershell
java --module-path mods -m com.example.app/com.example.app.Main
```

Các lệnh trên minh họa cách khởi chạy không kèm `--add-reads`, `--add-exports` hoặc `--add-opens`. Thay đường dẫn và main class theo ứng dụng. Nếu môi trường production có JVM options hợp lệ khác như heap size, GC hoặc system property nghiệp vụ, giữ chúng nhất quán giữa baseline và lượt xác minh.

Kiểm tra các nguồn option ngầm:

- `JDK_JAVA_OPTIONS` được launcher `java` thêm vào command line.
- `JAVA_TOOL_OPTIONS` được JVM đọc khi khởi tạo.
- `_JAVA_OPTIONS` là biến được một số bản phân phối JVM hỗ trợ; kiểm tra nếu môi trường đang dùng.
- Wrapper/service/container có thể nối thêm flags dù script ứng dụng không thể hiện.

Không dùng `--illegal-access=deny` làm phép thử trên JDK hiện đại. Từ Java 17, `--illegal-access` không còn khôi phục cơ chế truy cập cũ và không phải công cụ xác minh. Hãy chạy thực sự mà không có flag này và không có các quyền mở/export cần loại bỏ.

## 11. Kiểm thử đủ các đường chạy, không chỉ startup

Ứng dụng có thể khởi động thành công nhưng chỉ lỗi khi một tính năng hiếm dùng thực hiện reflection. Bộ kiểm thử nên bao gồm:

- Startup, shutdown và health check.
- Serialization/deserialization của mọi loại model quan trọng.
- ORM mapping, proxy generation, dependency injection và annotation processing runtime nếu có.
- Logging, monitoring, metrics, tracing và agent/APM.
- Plugin loading, `ServiceLoader` và extension module.
- Các đường code chỉ chạy theo môi trường production hoặc theo cấu hình bảo mật.
- Integration test với database, message broker, filesystem và các dịch vụ liên quan.

Chạy trên đúng JDK vendor/build và OS được hỗ trợ. Nếu sản phẩm hỗ trợ nhiều JDK release, chạy matrix trên từng release mục tiêu; `jdeps` sạch trên một JDK không thay thế kiểm thử runtime trên các release khác.

## 12. Kiểm tra tính tương thích ở compile time

Với code trên classpath, biên dịch bằng `--release` tương ứng với baseline mà sản phẩm hỗ trợ:

```powershell
$sources = Get-ChildItem -Path src -Recurse -Filter *.java | ForEach-Object { $_.FullName }
javac --release 16 -d out $sources
```

Với dự án modular, biên dịch cùng module path và module source path theo cấu trúc build của dự án. `--release` giới hạn API Java SE và ngôn ngữ được phép dùng theo release mục tiêu; nó không chứng minh code không dùng reflection vào internal API ở runtime.

Nếu module descriptor cần public API của module khác, khai báo `requires` và đặt dependency trên module path. Không dùng `--add-opens` để chữa lỗi compile-time package visibility; `opens` phục vụ deep reflection ở runtime.

## 13. Xử lý `--illegal-access` và các flag cũ

`--illegal-access` từng hỗ trợ giai đoạn chuyển tiếp sau khi JPMS được giới thiệu. Java 16 đã áp dụng strong encapsulation theo mặc định cho phần lớn JDK internals; Java 17 tiếp tục đóng gói mạnh hơn theo JEP 403. Từ Java 17, `--illegal-access` bị vô hiệu hóa về mặt chức năng và chỉ còn được giữ như tùy chọn tương thích/hiển thị cảnh báo trên các bản JDK tương ứng.

Do đó:

- Không thêm `--illegal-access=permit` để sửa lỗi trên Java 17 trở lên.
- Không dùng `--illegal-access=deny` làm bằng chứng ứng dụng sạch internal API.
- Tìm và thay dependency thực sự đang truy cập internal API.
- Chỉ giữ `--add-exports` hoặc `--add-opens` có lý do cụ thể, target hẹp và kế hoạch loại bỏ.

## 14. Tiêu chí xác minh hoàn tất

Ứng dụng có thể được xem là đã xác minh cho cấu hình mục tiêu khi:

| Tiêu chí | Bằng chứng cần có |
| --- | --- |
| Không còn tham chiếu internal API đã biết | `jdeps --jdk-internals` không báo dependency chưa xử lý trong app và thư viện được phân tích. |
| Dependency module hợp lệ | `jdeps --check` và module resolution không còn lỗi cần workaround. |
| Không cần quyền mở JDK rộng | Các `--add-opens` vào package JDK đã được loại bỏ hoặc có exception được giải thích rõ. |
| Không cần export JDK internal | Các `--add-exports` vào package nội bộ đã được thay bằng API hỗ trợ. |
| Không còn read edge classpath ngoài ý muốn | Các `--add-reads ...=ALL-UNNAMED` đã được gỡ hoặc có dependency migration được ghi nhận. |
| Reflection hoạt động theo thiết kế | Test serialization/ORM/framework chạy qua public API hoặc qualified opens hợp lệ của module ứng dụng. |
| Runtime sạch | Startup và integration tests chạy trên JDK mục tiêu mà không cần workaround đã bỏ. |
| Cấu hình triển khai sạch | Không có environment variable, wrapper hoặc container lén thêm flags cũ. |

`jdeps` không thể chứng minh mọi trường hợp reflection hoặc native access đều không tồn tại. Vì vậy, kết luận nên ghi rõ phạm vi artifact và runtime đã kiểm tra, cùng những ngoại lệ còn được giữ lại.

## 15. Những điểm cần nhớ

- Modifier `public` không đồng nghĩa API được Java SE bảo đảm; hãy kiểm tra package, module và tài liệu API.
- Dùng `jdeps --jdk-internals` để tìm tham chiếu JDK internal trong bytecode và phân tích cả dependency.
- Dùng `jdeps --check` cho module dependency; `jdeprscan` cho API deprecated. Đây là các mục tiêu audit khác nhau.
- Rà reflection và cấu hình framework vì phân tích tĩnh không phát hiện đầy đủ truy cập động.
- Thay internal API bằng Java SE API phù hợp với chức năng; không giả định mọi internal API có drop-in replacement.
- Phân biệt mở package JDK với qualified `opens` package model của ứng dụng.
- Gỡ workaround theo từng bước, chạy test sau mỗi thay đổi và xác minh không có flags bị thêm lại từ môi trường.
- `--illegal-access` không còn là giải pháp trên Java 17 trở lên.
- Chỉ kết luận sau khi chạy build, integration test và các luồng nghiệp vụ trên JDK mục tiêu mà không có ngoại lệ không cần thiết.

Xác minh module encapsulation là một quy trình kiểm kê, thay thế và kiểm thử. Khi ứng dụng chạy ổn định trên JDK mục tiêu mà không cần mở package JDK hoặc export internal API, dependency của nó đã rõ ràng hơn và ít bị ảnh hưởng bởi thay đổi implementation trong các bản JDK tiếp theo.

## Tài liệu tham khảo

- [JEP 396: Strongly Encapsulate JDK Internals by Default](https://openjdk.org/jeps/396)
- [JEP 403: Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403)
- [jdeps – Java SE 26 Tools Reference](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)
- [jdeprscan – Java SE 26 Tools Reference](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeprscan.html)
- [java launcher options – Java SE 26 Tools Reference](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [Java Platform Module System – Java Language Specification](https://docs.oracle.com/javase/specs/jls/se26/html/jls-7.html)
