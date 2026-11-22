# JDK internal API và cảnh báo migration

## 1. Mục tiêu

JDK cung cấp các API công khai để ứng dụng và thư viện sử dụng lâu dài. Bên cạnh đó, mã nguồn JDK còn có nhiều lớp, package và cơ chế chỉ phục vụ việc triển khai bên trong nền tảng. Những thành phần này thường được gọi là **JDK internal APIs**.

Ứng dụng có thể từng dùng được internal API trên một phiên bản JDK cũ, nhưng việc nâng cấp JDK có thể làm mã không biên dịch, không khởi chạy hoặc lỗi khi truy cập lúc runtime. Từ Java 9, module system tạo ranh giới rõ hơn giữa API được công khai và phần triển khai nội bộ. JDK 17 tiếp tục áp dụng strong encapsulation mặc định và vô hiệu hóa cơ chế nới lỏng tổng quát trước đó.

Bài này giải thích internal API là gì, vì sao chúng gây rủi ro, cách nhận biết cảnh báo và lỗi khi migration, cách dùng công cụ phân tích dependency, và cách thay thế bằng API được hỗ trợ.

Sau bài học, bạn có thể:
- Phân biệt Java SE API, JDK-specific API được hỗ trợ và JDK internal API.
- Hiểu các mốc thay đổi từ JDK 9 đến JDK 17.
- Nhận biết lỗi biên dịch, lỗi truy cập runtime và lỗi reflection do strong encapsulation.
- Dùng **jdeps --jdk-internals** để tìm dependency tĩnh vào JDK internals.
- Nhận ra giới hạn của phân tích tĩnh và kiểm tra thêm reflection ở runtime.
- Lập kế hoạch thay thế API nội bộ và kiểm thử ứng dụng sau khi nâng cấp JDK.

## 2. JDK internal API là gì?

Một API công khai là phần giao diện được tài liệu hóa và cam kết hỗ trợ theo chính sách tương thích của nền tảng hoặc nhà cung cấp. Java SE API nằm trong các package như **java.lang**, **java.util**, **java.io**, **java.nio** và nhiều package khác. Những API này là lựa chọn mặc định cho ứng dụng Java.

JDK cũng chứa các thành phần triển khai nội bộ. Chúng có thể nằm trong package mang tên **sun.***, **com.sun.*** hoặc **jdk.internal.***, nhưng không nên chỉ dựa vào prefix để kết luận. Cần xem tài liệu API, module descriptor, trạng thái export và chính sách hỗ trợ của nhà cung cấp.

Ví dụ về các thành phần nội bộ hoặc không phải API Java SE được hỗ trợ:

- **sun.nio.ch**: các lớp triển khai nội bộ liên quan đến channel và bộ đệm.
- **sun.security.x509**: các lớp triển khai nội bộ cho cấu trúc certificate và security.
- **jdk.internal.misc**: các tiện ích nội bộ của JDK.
- **sun.misc.BASE64Encoder**: lớp cũ không thuộc API Java SE được hỗ trợ; đã có API chuẩn thay thế.
- **sun.misc.Unsafe**: một API đặc biệt được duy trì vì lý do tương thích, nhưng các method của nó không phải API được hỗ trợ để ứng dụng phụ thuộc lâu dài.

Không phải mọi API có tên bắt đầu bằng **sun.** đều có cùng trạng thái. Một số package quan trọng như **sun.misc** và **sun.reflect** vẫn được mở cho một số hình thức sử dụng vì lý do tương thích. Điều đó không biến chúng thành API Java SE ổn định. Hãy xác minh trạng thái của từng lớp và từng method trong tài liệu của JDK mục tiêu.

Điểm quan trọng là: **một lớp có thể tồn tại trong JDK nhưng vẫn không phải API được hỗ trợ cho ứng dụng**. Việc mã nguồn biên dịch được hoặc lớp có thể nạp ở một phiên bản không bảo đảm nó tiếp tục hoạt động ở phiên bản kế tiếp.

## 3. Vì sao JDK đóng gói các API nội bộ?

Internal API cho phép nhóm phát triển JDK thay đổi cách triển khai mà không phải duy trì mọi chi tiết như một hợp đồng công khai. Nếu ứng dụng phụ thuộc trực tiếp vào lớp nội bộ, JDK sẽ khó sửa lỗi bảo mật, thay đổi cấu trúc dữ liệu, tối ưu hiệu năng hoặc thay thế thuật toán mà không làm hỏng ứng dụng bên ngoài.

Strong encapsulation giúp:
- **Tăng độ an toàn:** ứng dụng ít có khả năng can thiệp vào chi tiết triển khai nhạy cảm của JDK.
- **Giữ khả năng tiến hóa:** JDK có thể thay đổi phần nội bộ mà không phải bảo toàn mọi class và method chưa từng được công bố là API.
- **Giảm phụ thuộc chéo:** ứng dụng giao tiếp qua API công khai thay vì dựa vào cấu trúc bên trong của một implementation cụ thể.
- **Làm rõ ranh giới module:** module descriptor cho biết package nào được export và package nào chỉ dùng nội bộ.

Ví dụ, nếu thư viện dựa vào một lớp nội bộ để đọc trực tiếp cấu trúc của String, thư viện có thể hỏng khi JDK thay đổi cách biểu diễn chuỗi. Nếu thư viện dùng API công khai của String, nó ít bị ảnh hưởng bởi thay đổi nội bộ đó hơn.

## 4. Các mốc strong encapsulation từ JDK 9 đến JDK 17

Module system được giới thiệu từ JDK 9. Để giảm tác động lên ứng dụng cũ, các phiên bản đầu tiên vẫn cho phép một số truy cập reflective bất hợp pháp tới package JDK từng tồn tại trong JDK 8, đồng thời phát cảnh báo.

Các mốc chính:

| Phiên bản | Thay đổi |
|---|---|
| JDK 9–15 | Module system xuất hiện; một số truy cập reflective tới API nội bộ cũ vẫn được nới lỏng mặc định và phát cảnh báo |
| JDK 16 | Strong encapsulation trở thành mặc định; tùy chọn tương thích vẫn có thể được dùng để nới lỏng một số truy cập cũ |
| JDK 17 trở đi | Strong encapsulation được áp dụng mặc định; **--illegal-access** trở thành tùy chọn lỗi thời và không còn tác dụng |

Trong JDK 9 đến JDK 16, launcher có tùy chọn **--illegal-access** với các chế độ như **permit**, **warn**, **debug** và **deny**. Các chế độ này phục vụ giai đoạn chuyển đổi. Từ JDK 17, truyền tùy chọn đó chỉ tạo cảnh báo rằng tùy chọn bị bỏ qua; nó không khôi phục quyền truy cập nội bộ.

Ví dụ sau không phải cách sửa lỗi cho JDK hiện đại:

~~~bash
java --illegal-access=permit -jar app.jar
~~~

Trên JDK 17 trở lên, không nên kỳ vọng lệnh này mở lại các package. Hãy nâng cấp thư viện, thay thế internal API, hoặc nếu chưa thể migration ngay thì chỉ cấp quyền cụ thể bằng tùy chọn phù hợp.

Strong encapsulation áp dụng cho phần nội bộ của JDK, nhưng cần nhớ các ngoại lệ tương thích. Tài liệu migration của Oracle ghi nhận **sun.misc** và **sun.reflect** không bị strong encapsulation theo cùng cách như các package nội bộ khác. Tuy vậy, những API trong các package này vẫn có thể không được hỗ trợ và có thể bị deprecate hoặc thay đổi chính sách theo từng method.

## 5. Dấu hiệu khi ứng dụng phụ thuộc internal API

Lỗi có thể xuất hiện ở nhiều giai đoạn. Hãy đọc thông báo lỗi để xác định đó là lỗi compile, lỗi truy cập module, lỗi reflection hay API đã bị loại bỏ.

| Giai đoạn | Dấu hiệu thường gặp | Ý nghĩa có thể có |
|---|---|---|
| Biên dịch | package không tồn tại, package không được export, type không truy cập được | Mã nguồn tham chiếu package nội bộ mà compiler không được phép truy cập |
| Khởi chạy hoặc liên kết bytecode | **IllegalAccessError** | Bytecode truy cập một type/member mà module system không cho phép |
| Reflection | **InaccessibleObjectException** hoặc **IllegalAccessException** | Framework cố mở hoặc truy cập thành viên không public trong package chưa được mở |
| Nạp lớp | **ClassNotFoundException** hoặc **NoClassDefFoundError** | Lớp nội bộ đã bị chuyển, bị loại bỏ hoặc không còn được cung cấp |
| Liên kết method/field | **NoSuchMethodError** hoặc **NoSuchFieldError** | API nội bộ đã thay đổi chữ ký hoặc cấu trúc giữa các bản JDK |

Ví dụ lỗi reflection thường gặp:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make field private ... accessible:
module java.base does not "opens java.lang" to unnamed module
~~~

Thông báo này cho biết mã đang cố truy cập reflective vào một thành viên không public trong **java.lang**, nhưng module **java.base** không mở package đó cho module đích. Đây là lỗi về quyền mở package cho deep reflection; chỉ thêm export thông thường không giải quyết được trường hợp này.

Không nên chỉ tìm một chuỗi lỗi cụ thể. Thư viện có thể bắt và bỏ qua exception, khiến ứng dụng chỉ thể hiện hành vi sai hoặc cảnh báo ở log. Hãy chạy kiểm thử đại diện và quan sát cả log JVM lẫn log framework.

## 6. Phân biệt export, open và API nội bộ

Ba khái niệm sau thường bị nhầm:

- **Export package:** cho module đích truy cập các public type và public/protected member của package theo quy tắc module.
- **Open package:** cho phép deep reflection vào package ở runtime, bao gồm việc truy cập reflective tới thành viên không public theo các quy tắc reflection.
- **Internal API:** phần triển khai không được cam kết như API công khai; việc mở package không làm API đó trở nên ổn định.

Các tùy chọn tương thích có mục đích khác nhau:

~~~text
--add-exports source-module/package=target-module
--add-opens source-module/package=target-module
~~~

**--add-exports** phù hợp khi mã cần truy cập public type trong package chưa được export. Nó có thể được dùng lúc biên dịch và lúc chạy.

**--add-opens** phù hợp khi thư viện cần deep reflection vào package chưa được mở. Nó là tùy chọn runtime.

Cả hai chỉ là cách nới lỏng ranh giới cụ thể. Chúng không biến package nội bộ thành API được hỗ trợ và không đảm bảo tương thích khi nâng cấp JDK. Không nên thay mọi lỗi strong encapsulation bằng một tùy chọn mở rộng cho **ALL-UNNAMED**; cách đó có thể cấp quyền rộng cho toàn bộ mã chạy trong unnamed module.

Nếu module đích còn thiếu readability tới module nguồn, cần kiểm tra **requires** hoặc **--add-reads**. Export không tự tạo quan hệ đọc module.

## 7. Tìm dependency tĩnh bằng jdeps

**jdeps** là công cụ phân tích dependency đi kèm JDK. Tùy chọn **--jdk-internals** tìm các dependency ở cấp class tới JDK internal APIs.

Ví dụ kiểm tra một JAR:

~~~bash
jdeps --jdk-internals app.jar
~~~

Nếu ứng dụng dùng thư viện ngoài, có thể đưa chúng vào classpath phân tích:

~~~bash
jdeps --jdk-internals --class-path "lib/*" app.jar
~~~

Kết quả có thể liệt kê lớp ứng dụng, API nội bộ mà nó tham chiếu và gợi ý thay thế khi công cụ có dữ liệu tương ứng. Ví dụ minh họa từ tài liệu Oracle:

~~~text
Sample.class -> JDK removed internal API
Sample -> sun.misc.BASE64Encoder
JDK Internal API: sun.misc.BASE64Encoder
Suggested Replacement: java.util.Base64
~~~

Khi có nhiều JAR, hãy phân tích từng artifact của ứng dụng và dependency. Một dependency bậc ba có thể chứa internal API dù mã nguồn của ứng dụng không import trực tiếp package đó.

Có thể dùng kết quả để lập danh sách công việc:

| Thành phần | Internal API | Nơi tham chiếu | Hành động |
|---|---|---|---|
| Ứng dụng | sun.misc.BASE64Encoder | Mã xử lý dữ liệu | Thay bằng java.util.Base64 |
| Thư viện cũ | sun.misc.Cleaner | Thành phần quản lý tài nguyên | Nâng cấp hoặc chuyển sang java.lang.ref.Cleaner |
| Thư viện native-memory | sun.misc.Unsafe | Quản lý vùng nhớ | Đánh giá VarHandle, ByteBuffer hoặc Foreign Function & Memory API |
| Framework reflection | Thành viên private của java.* | Cấu hình/serialization | Nâng cấp framework hoặc thiết kế lại phần tích hợp |

Bảng này là ví dụ về cách ghi nhận công việc; API thay thế phải được chọn theo chức năng thực tế mà mã đang dùng.

## 8. Giới hạn của jdeps và kiểm tra reflection

**jdeps là công cụ phân tích tĩnh**. Nó tìm các tham chiếu có thể suy ra từ bytecode, nhưng không thể phát hiện đầy đủ những lần truy cập được tạo động.

Ví dụ, công cụ có thể không nhận ra trường hợp:

~~~java
Class<?> type = Class.forName(classNameFromConfig);
Field field = type.getDeclaredField(fieldNameFromConfig);
field.setAccessible(true);
~~~

Tên class và field được đọc từ cấu hình lúc runtime, nên bytecode không nhất thiết chứa một tham chiếu trực tiếp tới API nội bộ cần tìm.

Ngoài **jdeps**, hãy tìm trong source code và cấu hình các dấu hiệu:
- Import hoặc tên package **sun.***, **com.sun.***, **jdk.internal.***.
- **Class.forName**, **getDeclaredField**, **getDeclaredMethod**, **getDeclaredConstructor**.
- **setAccessible(true)**, **trySetAccessible()**, **MethodHandles.privateLookupIn**.
- Cấu hình reflection, serialization, dependency injection, mocking, ORM hoặc framework truy cập field.
- JVM arguments như **--add-exports**, **--add-opens** và **--illegal-access** trong script, container, CI hoặc cấu hình IDE.

Các dấu hiệu này cần được xem xét theo ngữ cảnh. Reflection không phải lúc nào cũng sai; vấn đề là truy cập thành viên nội bộ của module khác mà không có hợp đồng API hoặc quyền mở phù hợp.

Sau khi kiểm tra tĩnh, chạy ứng dụng và test suite trên JDK mục tiêu. Bao gồm các luồng thực tế dùng reflection, serialization, native memory, logging, networking, framework và plugin. Nếu framework bắt exception rồi tiếp tục, hãy kiểm tra log và hành vi đầu ra, không chỉ trạng thái process.

## 9. Chọn API thay thế được hỗ trợ

Mục tiêu migration là giữ nguyên hành vi cần thiết của ứng dụng bằng API có hợp đồng công khai. Không phải lúc nào cũng có một thay thế một-một; cần xác định mã đang sử dụng internal API để làm gì.

Một số ví dụ:

| API cũ hoặc nội bộ | Hướng thay thế | Ghi chú |
|---|---|---|
| **sun.misc.BASE64Encoder / BASE64Decoder** | **java.util.Base64** | API chuẩn có từ Java 8 |
| **sun.misc.Cleaner** | **java.lang.ref.Cleaner** | API chuẩn cho cleanup khi object không còn được tham chiếu; với tài nguyên có thể đóng rõ ràng, ưu tiên AutoCloseable và try-with-resources |
| Các thao tác atomic/field/array qua **sun.misc.Unsafe** | **VarHandle**, Atomic classes hoặc API concurrent phù hợp | Chọn theo memory ordering, atomicity và loại dữ liệu thực sự cần |
| Truy cập vùng nhớ native qua **sun.misc.Unsafe** | **Foreign Function & Memory API**, MemorySegment và Arena trên JDK hỗ trợ API này | FFM được chuẩn hóa trong JDK 22; kiểm tra phiên bản JDK mục tiêu |
| Thao tác byte/buffer thông thường qua implementation nội bộ | **ByteBuffer** và API **java.nio** | Dùng API public nếu không cần hành vi nội bộ đặc thù |

Ví dụ thay Base64:

~~~java
import java.util.Base64;

byte[] data = "Java modules".getBytes(java.nio.charset.StandardCharsets.UTF_8);

String encoded = Base64.getEncoder().encodeToString(data);
byte[] decoded = Base64.getDecoder().decode(encoded);
~~~

Đoạn mã dùng API chuẩn và không phụ thuộc vào **sun.misc.BASE64Encoder** hoặc **sun.misc.BASE64Decoder**.

Ví dụ về cleanup tài nguyên bằng API chuẩn:

~~~java
try (var input = java.nio.file.Files.newInputStream(path)) {
    // Đọc và xử lý dữ liệu.
}
~~~

Nếu tài nguyên có vòng đời rõ ràng, **try-with-resources** thường dễ kiểm soát hơn cơ chế cleanup dựa vào garbage collection. **Cleaner** phù hợp cho một số tình huống cleanup dự phòng, nhưng không nên dùng nó để thay thế việc đóng tài nguyên một cách chủ động.

Với **sun.misc.Unsafe**, không nên thay mọi lời gọi bằng một API duy nhất. Nếu cần truy cập biến với memory ordering, hãy đánh giá **VarHandle**. Nếu cần quản lý vùng nhớ native hoặc gọi hàm native, hãy đánh giá **Foreign Function & Memory API**. Nếu chỉ xử lý byte, **ByteBuffer** có thể đã đủ. Các method của Unsafe không phải API được hỗ trợ; nhiều method đã được thay thế bởi API chuẩn và bị deprecated for removal trong JDK 23. JDK 24 trở đi phát cảnh báo runtime khi gọi các memory-access method đã bị thay thế.

## 10. Nâng cấp dependency trước khi viết workaround

Internal API thường xuất hiện trong thư viện bên thứ ba hơn là trong mã ứng dụng trực tiếp. Một framework cũ có thể dùng reflection hoặc class nội bộ để tối ưu serialization, quản lý buffer, tạo proxy hay kiểm tra cấu trúc JDK.

Quy trình ưu tiên:

1. Xác định dependency và phiên bản thực sự được nạp ở runtime.
2. Kiểm tra nhà phát triển thư viện đã phát hành bản hỗ trợ JDK mục tiêu chưa.
3. Nâng cấp thư viện và plugin build/test liên quan.
4. Đọc release notes để biết thay đổi tương thích và cách cấu hình mới.
5. Chạy lại kiểm thử trên JDK mục tiêu.
6. Nếu thư viện chưa có bản sửa, liên hệ maintainer hoặc lập kế hoạch thay thế dependency.

Không chỉ cập nhật dependency khai báo trực tiếp. Maven/Gradle có thể kéo theo nhiều dependency bậc ba. Hãy xem dependency tree và đảm bảo artifact được chạy thực sự là phiên bản đã nâng cấp.

Nếu buộc phải giữ thư viện cũ trong thời gian ngắn, chỉ dùng **--add-exports** hoặc **--add-opens** cho package và target module cụ thể mà lỗi yêu cầu. Ghi lại lý do, dependency sở hữu workaround, phiên bản cần nâng cấp và điều kiện gỡ bỏ. Một workaround không có chủ sở hữu dễ trở thành phụ thuộc vĩnh viễn.

## 11. Quy trình migration thực tế

Có thể tổ chức migration theo các bước sau:

1. **Chốt JDK mục tiêu.** Ghi nhận vendor, feature release, update version, hệ điều hành và cách triển khai.
2. **Chạy ứng dụng hiện tại trên JDK mục tiêu.** Ghi lại lỗi khởi động, cảnh báo JVM, lỗi test và khác biệt hành vi trước khi thay đổi mã.
3. **Nâng cấp dependency.** Kiểm tra framework, driver, plugin, build tool, test runner và thư viện native.
4. **Quét dependency tĩnh.** Chạy **jdeps --jdk-internals** trên ứng dụng và các JAR phụ thuộc.
5. **Tìm reflection động.** Tìm các lời gọi reflection, MethodHandles, cấu hình class name và các JVM flags đang mở package.
6. **Lập danh sách migration.** Với mỗi API, ghi chức năng đang dùng, nơi gọi, dependency sở hữu, API thay thế, rủi ro và test cần có.
7. **Thay thế theo từng nhóm chức năng.** Giữ thay đổi nhỏ để dễ kiểm tra và rollback. Tạo adapter nội bộ nếu nhiều nơi đang gọi cùng một chức năng.
8. **Giảm workaround.** Xóa các cờ **--illegal-access** đã lỗi thời; chỉ giữ cờ add-exports/add-opens nếu đã chứng minh cần thiết và có thời hạn gỡ bỏ.
9. **Biên dịch và kiểm thử lại.** Chạy unit, integration, packaging và startup tests trên JDK mục tiêu.
10. **Kiểm tra triển khai thật.** Xác nhận script, service manager, container và JVM options trong production giống với cấu hình đã kiểm thử.

Tài liệu migration của Oracle khuyến nghị thử chạy ứng dụng trên JDK mới trước khi biên dịch lại, cập nhật thư viện, biên dịch khi cần và chạy jdeps. Migration thường là quá trình lặp: một lỗi được sửa có thể làm lộ ra dependency khác ở bước tiếp theo.

## 12. Dùng --add-exports và --add-opens như cầu nối tạm thời

Nếu chưa thể nâng cấp một thư viện, có thể tạm cấp quyền cho đúng package.

Ví dụ cấp export cho public type của package nội bộ:

~~~bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED -cp app.jar com.example.Main
~~~

Ví dụ mở package cho deep reflection:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp app.jar com.example.Main
~~~

Trong hai ví dụ:
- **java.base** là module nguồn.
- **sun.nio.ch** hoặc **java.lang** là package cần cấp quyền.
- **ALL-UNNAMED** áp dụng cho mã trong unnamed module, thường là ứng dụng chạy trên classpath.

Chọn **--add-exports** cho truy cập public type/member; chọn **--add-opens** khi framework cần reflection sâu vào thành viên không public. Cờ runtime không nhất thiết giải quyết lỗi biên dịch; nếu mã nguồn trực tiếp tham chiếu internal type, compiler cũng cần được cấu hình tương ứng.

Không dùng **--illegal-access=permit** để thay thế hai tùy chọn trên ở JDK 17+. Tùy chọn này không còn hiệu lực. Cũng không nên thêm hàng loạt package vào **ALL-UNNAMED** để làm mọi lỗi biến mất: quyền truy cập càng rộng thì ranh giới module càng yếu và càng khó loại bỏ sau này.

## 13. Kiểm thử và tiêu chí hoàn tất migration

Một lần chạy thành công chưa đủ để chứng minh migration đã hoàn tất. Internal API có thể chỉ được gọi trong một luồng hiếm hoặc bởi một plugin khi có dữ liệu đặc biệt.

Nên kiểm tra:

- **Build:** biên dịch bằng JDK mục tiêu, không còn import internal API không được hỗ trợ.
- **Static analysis:** kết quả **jdeps --jdk-internals** được xử lý; mọi dependency còn lại có lý do rõ ràng.
- **Reflection:** test các luồng dùng serialization, ORM, DI, proxy, mocking và framework reflection.
- **Runtime:** chạy cả ứng dụng classpath và module path nếu sản phẩm hỗ trợ cả hai.
- **Packaging:** kiểm tra script, Docker image, service config, test runner và IDE launch options.
- **Behavior:** so sánh đầu ra, hiệu năng, xử lý tài nguyên và lỗi với phiên bản trước.
- **Future JDK:** chạy thử trên bản JDK tiếp theo hoặc CI matrix phù hợp với lịch nâng cấp.
- **Workaround:** mỗi cờ add-exports/add-opens còn lại có owner, package, target module, lý do và kế hoạch gỡ bỏ.

**jdeps không phát hiện đầy đủ reflection động**, vì vậy tiêu chí hoàn tất phải kết hợp phân tích tĩnh và kiểm thử runtime. Nếu kết quả jdeps sạch nhưng ứng dụng vẫn ném InaccessibleObjectException, hãy điều tra các đường reflection và dependency framework.

## 14. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| javac báo package nội bộ không được export | Source code tham chiếu JDK internal API | Tìm API public thay thế; dùng --add-exports chỉ như cầu nối |
| IllegalAccessError khi chạy | Bytecode truy cập package chưa export | Kiểm tra module nguồn/đích và export runtime |
| InaccessibleObjectException | Reflection sâu vào package chưa mở | Nâng cấp framework hoặc mở package cụ thể bằng --add-opens tạm thời |
| --illegal-access=permit không còn tác dụng | Đang chạy JDK 17 trở lên | Gỡ cờ lỗi thời; migration hoặc cấp quyền cụ thể nếu thực sự cần |
| jdeps không báo dependency nhưng runtime vẫn lỗi reflection | Truy cập được tạo động hoặc tên class lấy từ cấu hình | Tìm reflection trong source/dependency và chạy test đại diện |
| NoClassDefFoundError sau khi nâng cấp | API hoặc class nội bộ đã bị loại bỏ/di chuyển | Xác định dependency cũ và thay thế bằng API được hỗ trợ |
| NoSuchMethodError sau khi nâng cấp | Thư viện phụ thuộc vào method nội bộ đã thay đổi | Nâng cấp thư viện hoặc thay phần tích hợp |
| Lỗi chỉ xảy ra trong container | JVM options hoặc dependency thực tế khác môi trường local | Kiểm tra image, command line, classpath/module path và cấu hình deploy |

Không nên xử lý mọi trường hợp bằng cách thêm **--add-opens**. Nếu lớp đã bị loại bỏ, mở package không thể tạo lại lớp đó. Nếu lỗi là dependency version conflict, cần sửa dependency graph. Nếu API đã thay đổi, phải thay mã hoặc nâng cấp thư viện.

## 15. Tự kiểm tra

**1. Vì sao một lớp public vẫn có thể không truy cập được từ module khác?**

Vì module system còn kiểm tra package có được export cho module đích hay không. Modifier public trong Java không tự vượt qua ranh giới module.

**2. Từ JDK 17, --illegal-access=permit có mở lại các package nội bộ không?**

Không. Từ JDK 17, tùy chọn này bị bỏ qua và chỉ phát cảnh báo. Cần migration sang API được hỗ trợ hoặc cấp quyền cụ thể bằng add-exports/add-opens trong giai đoạn tương thích.

**3. jdeps --jdk-internals có phát hiện mọi lần dùng reflection tới JDK internal API không?**

Không. jdeps là phân tích tĩnh và có thể bỏ sót tên class/field được tạo động, reflection hoặc tra cứu qua cấu hình. Cần kiểm tra source/dependency và chạy test runtime.

**4. Khi nào dùng --add-exports và khi nào dùng --add-opens?**

Dùng add-exports khi mã cần truy cập public type/member của package chưa export. Dùng add-opens khi cần deep reflection vào thành viên không public trong package chưa mở.

**5. Vì sao nâng cấp thư viện bên thứ ba thường là bước migration quan trọng?**

Vì internal API có thể được gọi bên trong framework hoặc dependency mà ứng dụng không trực tiếp import. Phiên bản mới có thể đã chuyển sang API chuẩn và xử lý strong encapsulation.

**6. sun.misc.Unsafe có thể coi là API được hỗ trợ vì vẫn còn trong JDK không?**

Không. Sự tồn tại vì tương thích không biến các method thành API được hỗ trợ. Nhiều method đã được thay thế bởi VarHandle hoặc Foreign Function & Memory API và bị deprecated for removal.

## 16. Ghi nhớ

JDK internal API là chi tiết triển khai, không phải hợp đồng ổn định cho ứng dụng. Strong encapsulation giúp JDK tiến hóa an toàn hơn, nhưng làm lộ ra những dependency cũ khi nâng cấp. Hãy dùng **jdeps --jdk-internals** để tìm tham chiếu tĩnh, kiểm tra thêm reflection động, nâng cấp dependency và thay thế bằng API công khai.

**--add-exports** và **--add-opens** có thể giúp ứng dụng cũ tiếp tục chạy trong giai đoạn chuyển đổi, nhưng không thay thế migration. Mỗi workaround cần được giới hạn đúng package, có người sở hữu và có kế hoạch loại bỏ.

## Tài liệu tham khảo

- [Oracle JDK 27 Migration Guide — Migrating from JDK 8 to Later JDK Releases](https://docs.oracle.com/en/java/javase/27/migrate/migrating-from-jdk-8-later-jdk-releases.html)
- [Oracle JDK 25 Migration Guide — Preparing for Migration](https://docs.oracle.com/en/java/javase/25/migrate/preparing-migration.html)
- [The jdeps Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)
- [JEP 403: Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403)
- [JEP 396: Strongly Encapsulate JDK Internals by Default](https://openjdk.org/jeps/396)
- [JEP 454: Foreign Function & Memory API](https://openjdk.org/jeps/454)
- [JEP 498: Warn upon Use of Memory-Access Methods in sun.misc.Unsafe](https://openjdk.org/jeps/498)
