# Đọc stack trace để xác định thư viện đang phụ thuộc JDK internal

## 1. Vì sao cần đọc stack trace khi gặp lỗi JDK internal?

Từ Java 9, hệ thống module của JDK xác định package nào được export cho module khác và package nào được mở để reflection sâu. Java 16 thay đổi mặc định theo hướng đóng gói mạnh các thành phần nội bộ của JDK bằng JEP 396. Từ Java 17, JEP 403 tiếp tục củng cố việc đóng gói này và loại bỏ cơ chế tương thích cũ dựa trên `--illegal-access`.

Vì vậy, một thư viện từng truy cập class hoặc field nội bộ của JDK có thể chạy được trên JDK cũ nhưng phát sinh lỗi khi ứng dụng chạy trên JDK hiện đại. Stack trace giúp xác định:

- Thao tác nào bị chặn: truy cập trực tiếp hay reflection.
- Module JDK nào chứa package đang bị truy cập.
- Package nào chưa được export hoặc open.
- Module hoặc thư viện nào đang cố truy cập package đó.
- Frame nào trong stack trace dẫn đến lời gọi gây lỗi.
- Cần nâng cấp thư viện, thay API hay tạm cấu hình module.

Một số package nội bộ có tên như `sun.*`, `com.sun.*` hoặc `jdk.internal.*`, nhưng không nên chỉ dựa vào tiền tố package để kết luận. Hãy đọc exception message, module name và stack frame để xác định chính xác vấn đề.

Mục tiêu bài học:

- Nhận diện lỗi do strong encapsulation của JDK.
- Phân biệt `InaccessibleObjectException`, `IllegalAccessError` và các lỗi khác.
- Đọc module, package và caller module trong exception message.
- Tìm thư viện liên quan từ các frame của stack trace.
- Dùng `jdeps --jdk-internals` để tìm tham chiếu tĩnh đến JDK internal API.
- Phân biệt `--add-opens` với `--add-exports`.
- Chọn cách sửa có thể duy trì trên các phiên bản Java hiện đại.

## 2. Bối cảnh strong encapsulation từ Java 16

JDK có các API công khai được tài liệu hóa và các thành phần nội bộ phục vụ việc triển khai. Những thành phần nội bộ không phải hợp đồng API ổn định; tên class, field, package và cách triển khai có thể thay đổi giữa các phiên bản.

Hệ thống module phân biệt hai cơ chế:

- `exports`: cho phép module khác truy cập các kiểu public trong package được export theo quy tắc module.
- `opens`: cho phép reflection sâu vào các thành viên của package, trong phạm vi module được mở.

JEP 396 đặt strong encapsulation làm mặc định trong Java 16 đối với phần lớn các package nội bộ của JDK. Một số API nội bộ quan trọng vì lý do tương thích vẫn có ngoại lệ, nhưng chúng vẫn không nên được xem là API được bảo đảm ổn định cho ứng dụng mới.

JEP 403 trong Java 17 tiếp tục đóng gói mạnh các thành phần nội bộ và làm cho tùy chọn tương thích `--illegal-access` không còn là cách mở lại các package như trước. Vì vậy, khi điều tra lỗi trên JDK hiện đại, không nên dựa vào hướng dẫn cũ yêu cầu bật `--illegal-access=permit`.

Điều cần nhớ:

- Java 16 là mốc thay đổi mặc định quan trọng.
- Java 17 trở đi tiếp tục duy trì strong encapsulation và loại bỏ lối nới lỏng cũ.
- `--add-opens` và `--add-exports` vẫn là tùy chọn cấu hình module có phạm vi cụ thể, nhưng chỉ nên dùng như giải pháp chuyển tiếp khi hiểu rõ rủi ro.
- Thư viện nên chuyển sang API công khai được hỗ trợ thay vì phụ thuộc chi tiết triển khai của JDK.

## 3. Hai dấu hiệu lỗi quan trọng trong stack trace

Hai loại lỗi thường gặp khi một thư viện truy cập package JDK không được mở hoặc export là:

| Exception/Error | Tình huống thường gặp | Dấu hiệu trong message |
| --- | --- | --- |
| `InaccessibleObjectException` | Reflection sâu, ví dụ gọi `setAccessible(true)` trên field hoặc method trong package chưa được open. | `module ... does not "opens package" to ...` |
| `IllegalAccessError` | Bytecode truy cập trực tiếp một class hoặc member trong package không được export cho caller module. | `module ... does not export package to ...` |

Cả hai đều có thể liên quan đến module encapsulation, nhưng chúng thể hiện hai loại truy cập khác nhau.

Ngoài ra, reflection có thể phát sinh `IllegalAccessException` khi thao tác reflective không có quyền truy cập cần thiết. `trySetAccessible()` có thể trả về `false` khi không thể bật quyền truy cập sâu. Không nên gộp mọi lỗi reflection thành cùng một loại exception.

## 4. Đọc InaccessibleObjectException

Ví dụ stack trace:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make field private final byte[] java.lang.String.value accessible:
module java.base does not "opens java.lang" to unnamed module @4a54c0de
    at java.base/java.lang.reflect.AccessibleObject.checkCanSetAccessible(AccessibleObject.java:...)
    at java.base/java.lang.reflect.Field.checkCanSetAccessible(Field.java:...)
    at java.base/java.lang.reflect.Field.setAccessible(Field.java:...)
    at com.vendor.legacy.ReflectionHelper.inspect(ReflectionHelper.java:42)
    at com.vendor.serializer.ObjectMapper.readValue(ObjectMapper.java:118)
    at com.example.app.RequestHandler.handle(RequestHandler.java:57)
~~~

Cách đọc:

1. `InaccessibleObjectException` cho biết thao tác bật quyền truy cập reflection sâu đã bị từ chối.
2. `java.base` là module chứa package bị truy cập.
3. `java.lang` là package đang bị yêu cầu mở.
4. `unnamed module` cho biết caller thuộc classpath, không phải một named module.
5. `ReflectionHelper.inspect` là frame thư viện thực hiện lời gọi reflection.
6. `ObjectMapper.readValue` cho thấy đường gọi đi qua thư viện serializer.
7. `RequestHandler.handle` là frame ứng dụng gọi vào thư viện.

Trong ví dụ, thư viện serializer đang cố truy cập field triển khai bên trong `java.lang.String`. Đây không phải lỗi do chuỗi đầu vào có nội dung sai; đây là lỗi quyền truy cập vào implementation detail của JDK.

### Tìm frame cần điều tra

Các frame đầu thường thuộc `java.lang.reflect` hoặc một phần của JDK vì JDK thực hiện kiểm tra quyền truy cập. Hãy tiếp tục đọc xuống dưới để tìm frame đầu tiên thuộc thư viện hoặc ứng dụng.

Frame đó giúp xác định vị trí gọi reflection. Nếu frame thuộc thư viện bên thứ ba, ghi lại:

- Tên class và method.
- File và số dòng nếu có.
- Tên artifact chứa class.
- Phiên bản artifact đang chạy.

Không phải lúc nào frame đầu tiên ngoài JDK cũng là thư viện gây ra vấn đề. Ứng dụng có thể tự gọi reflection, hoặc một framework có thể gọi thư viện khác. Đọc toàn bộ chuỗi frame và phần `Caused by` để tìm caller thực sự.

## 5. Hiểu module, package và caller trong exception message

Một message điển hình có cấu trúc:

~~~text
module java.base does not "opens java.lang" to unnamed module @4a54c0de
~~~

Có thể tách thành ba phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `java.base` | Module sở hữu package đang được truy cập. |
| `java.lang` | Package cần được mở để reflection sâu. |
| `unnamed module` | Module của caller; thường là code được nạp từ classpath. |

Nếu caller là named module, message có thể hiển thị tên module đó, ví dụ `com.example.serializer`.

Khi cần cấu hình `--add-opens`, module ở bên trái là module chứa package, còn module ở bên phải là module cần được cấp quyền reflection sâu:

~~~text
--add-opens java.base/java.lang=com.example.serializer
~~~

Không đảo hai module. Cũng không nhầm package đích với class gọi reflection.

Với caller ở classpath, target thường được ghi là `ALL-UNNAMED` trong tùy chọn JVM. Điều này mở package cho tất cả unnamed modules trong phạm vi JVM đó, nên rộng hơn việc mở cho một named module cụ thể.

## 6. Đọc IllegalAccessError khi truy cập trực tiếp

Không phải mọi lỗi encapsulation đều xuất phát từ reflection. Một thư viện có thể tham chiếu trực tiếp đến class trong package nội bộ.

Ví dụ:

~~~text
java.lang.IllegalAccessError:
class com.vendor.crypto.LegacyCertReader (in unnamed module @2f92e0f4)
cannot access class sun.security.x509.X509CertImpl (in module java.base)
because module java.base does not export sun.security.x509
to unnamed module @2f92e0f4
    at com.vendor.crypto.LegacyCertReader.read(LegacyCertReader.java:81)
    at com.vendor.crypto.CertificateLoader.load(CertificateLoader.java:35)
    at com.example.app.Startup.initialize(Startup.java:24)
~~~

Cách đọc:

- `IllegalAccessError` là lỗi liên kết/runtime khi bytecode cố truy cập một kiểu không được phép.
- `com.vendor.crypto.LegacyCertReader` là caller.
- `sun.security.x509.X509CertImpl` là class đích trong package nội bộ.
- `java.base` là module chứa package.
- `does not export sun.security.x509` cho biết package chưa được export tới caller module.
- Frame `LegacyCertReader.read` chỉ ra vị trí trong thư viện cần nâng cấp hoặc thay thế.

Khác với `InaccessibleObjectException`, message ở đây nói `does not export`, không phải `does not opens`. Đây là dấu hiệu quan trọng để chọn đúng hướng xử lý.

## 7. Phân biệt lỗi encapsulation với lỗi khác

Không nên kết luận mọi lỗi liên quan class hoặc reflection đều là do JDK internal.

| Lỗi | Ý nghĩa thường gặp | Cần kiểm tra |
| --- | --- | --- |
| `InaccessibleObjectException` | Không thể bật quyền truy cập sâu bằng reflection. | Module, package, caller và lời gọi `setAccessible`. |
| `IllegalAccessError` | Bytecode truy cập kiểu/member không được export hoặc không truy cập được. | Module descriptor, package đích và thư viện gọi. |
| `IllegalAccessException` | Một thao tác reflection không có quyền truy cập theo quy tắc hiện tại. | Cách lấy `Method`/`Field`, modifier và quyền truy cập. |
| `NoSuchFieldException` | Không tìm thấy field được yêu cầu. | Field có bị đổi tên/xóa hoặc implementation đã thay đổi không. |
| `NoSuchMethodException` | Không tìm thấy method được yêu cầu. | Chữ ký method và phiên bản thư viện/JDK. |
| `NoClassDefFoundError` | Class cần lúc runtime không được nạp hoặc khởi tạo thành công. | Classpath, module path và dependency runtime. |
| `NoSuchMethodError` | Bytecode được biên dịch với method không có trong phiên bản class đang chạy. | Xung đột hoặc lệch phiên bản dependency. |

Ví dụ, `NoSuchFieldException` khi thư viện tìm field `value` không tự chứng minh module đã chặn truy cập. Có thể field đã thay đổi hoặc không tồn tại trên JDK đang chạy.

Một lỗi encapsulation thường có thông tin rõ về module/package hoặc exception chuyên biệt. Nếu message không có dấu hiệu đó, hãy kiểm tra thêm khả năng lệch phiên bản hoặc thiếu dependency trước khi thêm tùy chọn module.

## 8. Tìm thư viện sở hữu frame trong stack trace

Tên package trong frame thường giúp nhận ra nhà cung cấp, nhưng tên package không luôn trùng tên artifact Maven hoặc module name.

Ví dụ frame:

~~~text
at com.vendor.serializer.ReflectionHelper.inspect(ReflectionHelper.java:42)
~~~

Quy trình xác định thư viện:

1. Ghi lại class đầy đủ `com.vendor.serializer.ReflectionHelper`.
2. Kiểm tra dependency tree để biết artifact nào được đưa vào runtime.
3. Đối chiếu phiên bản artifact đang chạy, kể cả dependency bắc cầu.
4. Nếu có nhiều JAR chứa class tương tự, kiểm tra thứ tự classpath và nguồn class được nạp.
5. Kiểm tra release note của thư viện để tìm bản đã hỗ trợ strong encapsulation hoặc JDK hiện tại.

Với Maven:

~~~bash
mvn dependency:tree
~~~

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Nếu class được nạp từ JAR cụ thể, có thể kiểm tra vị trí nguồn trong môi trường debug:

~~~java
Class<?> type = com.vendor.serializer.ReflectionHelper.class;
java.security.CodeSource source =
    type.getProtectionDomain().getCodeSource();

System.out.println(
    source == null ? "Code source unavailable" : source.getLocation()
);
~~~

`CodeSource` có thể không có trong mọi môi trường class loader hoặc khi class được nạp theo cách đặc biệt. Khi đó, kết hợp dependency tree, log class loading và việc kiểm tra nội dung JAR.

Không nên nâng cấp một dependency chỉ dựa trên tên package trong stack trace. Trước hết hãy xác nhận đúng artifact và phiên bản thực sự được nạp.

## 9. Dùng jdeps để tìm tham chiếu tĩnh đến JDK internal API

Stack trace chỉ cho thấy đường chạy đã gặp lỗi. `jdeps` có thể bổ sung một bước kiểm tra tĩnh để tìm bytecode tham chiếu đến các API nội bộ của JDK.

Lệnh cơ bản:

~~~bash
jdeps --jdk-internals app.jar
~~~

Nếu muốn phân tích phụ thuộc đệ quy và cung cấp classpath cho các thư viện runtime:

~~~bash
jdeps --jdk-internals --recursive --class-path "lib/*" app.jar
~~~

Kết quả có thể liệt kê:

- Class trong ứng dụng hoặc thư viện có tham chiếu API nội bộ.
- Tên JDK internal API được tham chiếu.
- Module chứa API đó.
- Gợi ý thay thế nếu JDK có API công khai tương ứng.

Có thể chạy lệnh trên từng JAR phụ thuộc để tìm thư viện bên thứ ba đang sử dụng internal API.

### Giới hạn của jdeps

`jdeps --jdk-internals` phân tích tham chiếu có thể nhận diện trong bytecode. Nó không phát hiện đầy đủ mọi truy cập được tạo động bằng reflection, tên class được ghép từ chuỗi, bytecode sinh lúc runtime hoặc hành vi native code.

Do đó:

- `jdeps` không báo lỗi không có nghĩa ứng dụng chắc chắn không truy cập JDK internals.
- Stack trace runtime và kiểm tra source/JAR vẫn cần thiết.
- Nên kết hợp static analysis với test trên JDK mục tiêu.

## 10. Quy trình điều tra từ stack trace đến dependency

Có thể thực hiện theo trình tự sau:

1. **Thu thập lỗi đầy đủ:** lấy exception đầu tiên, toàn bộ stack trace, `Caused by` và suppressed exceptions.
2. **Xác nhận runtime:** ghi nhận kết quả `java -version` của đúng tiến trình gặp lỗi.
3. **Nhận diện loại lỗi:** tìm `InaccessibleObjectException`, `IllegalAccessError` hoặc lỗi khác.
4. **Đọc module và package:** xác định module chứa package và package đang bị truy cập.
5. **Xác định caller module:** xem code gọi thuộc unnamed module hay named module.
6. **Tìm frame thư viện:** đi qua các frame JDK để xác định class/method của framework hoặc dependency.
7. **Tìm artifact và version:** dùng dependency tree, class loading hoặc kiểm tra JAR.
8. **Chạy jdeps:** kiểm tra tham chiếu tĩnh đến JDK internal API.
9. **Kiểm tra phiên bản mới:** xem thư viện đã thay cách truy cập hoặc có release hỗ trợ JDK mục tiêu chưa.
10. **Chọn cách sửa:** nâng cấp, thay thế dependency hoặc dùng API công khai.
11. **Chỉ cân nhắc mở package tạm thời:** nếu chưa thể thay thư viện và đã đánh giá phạm vi quyền cần cấp.
12. **Kiểm thử lại:** chạy trên đúng JDK triển khai và xác nhận không còn truy cập trái phép.

Khi báo lỗi cho nhóm phụ trách thư viện, cung cấp exception type, module/package, caller frame, artifact/version và JDK runtime. Các dữ liệu này hữu ích hơn việc chỉ gửi một dòng `InaccessibleObjectException`.

## 11. Chọn đúng --add-opens và --add-exports

Hai tùy chọn này không thay thế cho nhau.

| Tùy chọn | Mục đích | Trường hợp dùng |
| --- | --- | --- |
| `--add-opens` | Mở package cho deep reflection ở runtime. | Thư viện cần truy cập private field/method qua reflection. |
| `--add-exports` | Export package cho truy cập kiểu thông thường tới các kiểu public trong package. | Bytecode cần tham chiếu kiểu public trong package chưa export. |

### Ví dụ add-opens

Nếu thư viện thuộc classpath và cần reflection sâu vào `java.lang`:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

Nếu thư viện thuộc named module `com.example.serializer`:

~~~bash
java --add-opens java.base/java.lang=com.example.serializer --module-path mods --module com.example.app/com.example.app.Main
~~~

Cấp quyền cho đúng module gọi sẽ hẹp hơn việc mở cho `ALL-UNNAMED`.

### Ví dụ add-exports

Nếu bytecode cần truy cập kiểu public trong package `sun.security.x509`:

~~~bash
java --add-exports java.base/sun.security.x509=ALL-UNNAMED -jar app.jar
~~~

`--add-exports` không làm cho private member có thể truy cập qua deep reflection. Với lỗi `InaccessibleObjectException`, hãy xác định package cần mở và cân nhắc `--add-opens` nếu thực sự phải dùng giải pháp chuyển tiếp.

Cả hai tùy chọn đều làm thay đổi ranh giới module của tiến trình. Chỉ cấp quyền cho package và caller cần thiết; không mở hàng loạt package nội bộ để làm cho ứng dụng khởi động bằng mọi giá.

## 12. Vì sao không nên dựa vào --illegal-access?

Các hướng dẫn cũ có thể đề nghị chạy:

~~~bash
java --illegal-access=permit -jar app.jar
~~~

Tùy chọn này từng phục vụ giai đoạn chuyển đổi từ cơ chế truy cập cũ sang strong encapsulation. Trong Java 16, strong encapsulation đã là mặc định; từ Java 17, `--illegal-access` không còn là cơ chế mở lại các package nội bộ.

Không dùng tùy chọn này như giải pháp sửa lỗi cho ứng dụng hiện đại. Nếu cần cấu hình chuyển tiếp, hãy chỉ rõ package và caller bằng `--add-opens` hoặc `--add-exports`, đồng thời lập kế hoạch bỏ cấu hình khi dependency đã được thay thế.

Một số API nội bộ quan trọng vẫn có ngoại lệ tương thích, ví dụ `sun.misc.Unsafe` trong module `jdk.unsupported`. Việc một API còn truy cập được không biến nó thành API công khai được bảo đảm ổn định. `jdeps` vẫn có thể cảnh báo về dependency kiểu này; tránh đưa nó vào code mới nếu có API được hỗ trợ đáp ứng nhu cầu.

## 13. Hướng sửa bền vững: nâng cấp hoặc thay dependency

Khi stack trace chỉ ra một thư viện đang truy cập field hoặc class nội bộ, thứ tự xử lý nên là:

1. Kiểm tra phiên bản mới của thư viện có hỗ trợ JDK mục tiêu.
2. Nâng cấp lên phiên bản đã loại bỏ truy cập nội bộ.
3. Nếu thư viện không còn được duy trì, tìm giải pháp thay thế có API công khai.
4. Nếu code thuộc quyền kiểm soát của nhóm, thay truy cập nội bộ bằng API chuẩn.
5. Chỉ dùng tùy chọn mở package có giới hạn như giải pháp chuyển tiếp đã được đánh giá.

Ví dụ thay API nội bộ bằng API công khai:

| Dependency cũ | API công khai nên xem xét |
| --- | --- |
| `sun.misc.BASE64Encoder` hoặc `sun.misc.BASE64Decoder` | `java.util.Base64` |
| Cơ chế cleanup nội bộ | `java.lang.ref.Cleaner` |
| Truy cập biến với thao tác nguyên tử/kiểu thấp | `VarHandle` và API concurrency phù hợp |
| Truy cập field private của implementation JDK | API công khai của class/module thay vì reflection vào field nội bộ |

Không phải mọi internal API đều có một thay thế một-một. Với trường hợp không có API tương đương, hãy xem lại mục tiêu thiết kế hoặc dùng thư viện được hỗ trợ chính thức thay vì phụ thuộc vào implementation detail.

## 14. Những điều cần kiểm tra trong môi trường triển khai

Một ứng dụng có thể chạy tốt trên máy phát triển nhưng lỗi ở production vì hai môi trường dùng JDK hoặc dependency khác nhau.

Khi so sánh môi trường, kiểm tra:

- Vendor và version của JDK.
- Module path và classpath.
- Phiên bản thực tế của thư viện bắc cầu.
- JVM arguments có `--add-opens`, `--add-exports` hoặc tùy chọn cũ hay không.
- Framework/plugin nào thực hiện reflection.
- Image/container có chứa cùng dependency set như môi trường build không.
- Có nhiều phiên bản JAR trùng class trên runtime classpath không.

Không giả định `javac` và `java` trong shell đang trỏ đến cùng JDK. Kiểm tra cả compiler và runtime nếu lỗi chỉ xuất hiện ở một môi trường.

Nếu dùng container hoặc launcher, kiểm tra JVM arguments từ đúng entrypoint. Một tùy chọn được cấu hình trong IDE không tự động xuất hiện ở lệnh chạy production.

## 15. Lỗi thường gặp và cách khắc phục

1. **Chỉ đọc dòng exception mà bỏ qua stack frame:** tiếp tục đọc đến class/method của thư viện gọi reflection hoặc truy cập trực tiếp.
2. **Nhầm `opens` với `exports`:** deep reflection cần `opens`; truy cập kiểu public cần `exports`.
3. **Cho rằng `java.base` là thư viện gây lỗi:** đó thường là module chứa package đích; caller có thể là dependency bên ngoài.
4. **Coi `unnamed module` là tên một thư viện:** nó thường chỉ code chạy từ classpath; phải tìm class cụ thể trong stack trace.
5. **Kết luận `NoSuchFieldException` là strong encapsulation:** kiểm tra field có còn tồn tại và đúng phiên bản không.
6. **Dùng `--illegal-access=permit` trên JDK hiện đại:** tùy chọn cũ không còn mở lại package từ Java 17; xử lý dependency hoặc cấu hình mở package cụ thể nếu thật sự cần.
7. **Mở toàn bộ package cho `ALL-UNNAMED`:** cấp quyền rộng hơn cần thiết; ưu tiên target module cụ thể.
8. **Chỉ chạy jdeps rồi kết luận an toàn:** static analysis không phát hiện mọi reflection động.
9. **Nâng cấp nhầm dependency:** xác định artifact và phiên bản class thực sự được nạp trước khi thay đổi.
10. **Dùng internal API vì nó vẫn còn chạy:** khả năng truy cập hiện tại không phải cam kết tương thích trong tương lai.

## 16. Bài tập thực hành

1. Đọc một stack trace có `InaccessibleObjectException`; xác định module, package và caller module.
2. Tìm frame đầu tiên thuộc thư viện bên thứ ba và ghi lại class, method, file cùng số dòng.
3. Đọc một stack trace có `IllegalAccessError`; giải thích vì sao message dùng `does not export`.
4. So sánh `InaccessibleObjectException` với `IllegalAccessException`.
5. Dùng `mvn dependency:tree` hoặc Gradle runtime dependency report để tìm artifact chứa class trong stack trace.
6. Chạy `jdeps --jdk-internals` trên một JAR và giải thích kết quả.
7. Giải thích vì sao `jdeps` không phát hiện được mọi truy cập reflection động.
8. Viết lệnh `--add-opens` cho một package cụ thể và một named module caller.
9. Viết lệnh `--add-exports` cho một package cụ thể và giải thích vì sao nó không thay thế `--add-opens`.
10. Kiểm tra một dependency cũ và đề xuất cách thay bằng API công khai được hỗ trợ.
11. Giải thích vì sao `--illegal-access=permit` không phải cách sửa bền vững trên Java hiện đại.
12. Viết báo cáo ngắn cho nhóm phụ trách thư viện, gồm JDK version, exception, module/package, caller frame và artifact/version.

## Ghi nhớ

Khi JDK chặn truy cập vào thành phần nội bộ, hãy đọc exception message và stack trace để tìm module chứa package, package bị chặn, caller module và class/method của thư viện thực hiện truy cập. `InaccessibleObjectException` thường chỉ deep reflection vào package chưa được open; `IllegalAccessError` thường chỉ truy cập trực tiếp vào package chưa được export. `jdeps --jdk-internals` giúp phát hiện tham chiếu tĩnh nhưng không thay thế việc kiểm tra runtime reflection. Ưu tiên nâng cấp hoặc thay thư viện bằng API công khai. `--add-opens` dành cho deep reflection, `--add-exports` dành cho truy cập kiểu public; chỉ dùng với phạm vi hẹp như giải pháp chuyển tiếp. `--illegal-access` không còn là cách mở lại package nội bộ từ Java 17. Những quy tắc này tiếp tục quan trọng trên các JDK hiện đại sau Java 16.

**Tài liệu tham khảo chính thức:**

- [JEP 396 – Strongly Encapsulate JDK Internals by Default](https://openjdk.org/jeps/396)
- [JEP 403 – Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403)
- [Java API – InaccessibleObjectException](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html)
- [Java API – AccessibleObject](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [JDK Tool Specification – jdeps](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jdeps.html)
- [Java Platform Module System – Module directives](https://docs.oracle.com/javase/specs/jls/se16/html/jls-7.html#jls-7.7)
