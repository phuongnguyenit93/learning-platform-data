# Giới hạn của jdeps với reflection, cấu hình chuỗi và lớp sinh động

**jdeps** là công cụ phân tích dependency tĩnh của JDK. Công cụ đọc các file class, thư mục class và JAR để tìm quan hệ phụ thuộc ở mức package, class hoặc module. Nó rất hữu ích khi rà soát JDK internal API, chuẩn bị module hóa và xác định các module cần cho một runtime image.

Tuy nhiên, jdeps không thực thi ứng dụng và không quan sát mọi cách một lớp có thể được tìm thấy trong lúc chạy. Những dependency chỉ xuất hiện qua reflection, tên lớp được lưu trong file cấu hình hoặc bytecode được sinh trong bộ nhớ có thể không xuất hiện trong báo cáo. Vì vậy, kết quả không phải danh sách đầy đủ mọi lớp mà ứng dụng có thể tải.

Bài học này giải thích ranh giới của phân tích tĩnh, minh họa các trường hợp jdeps bỏ sót và trình bày cách kết hợp quét bytecode, kiểm tra cấu hình, kiểm thử runtime và theo dõi class loading để đánh giá dependency đáng tin cậy hơn.

## 1. jdeps phân tích điều gì?

jdeps đọc các class file có trong đầu vào và xác định những dependency mà bytecode thể hiện. Đầu vào có thể là:

- Một file .class.
- Một thư mục chứa class file.
- Một JAR.
- Một module hoặc các artifact được chỉ định qua class path và module path.

Các kết quả thường được dùng để:

- Xem dependency ở mức package hoặc class.
- Tìm tham chiếu tới JDK internal API.
- Phát hiện dependency tĩnh còn thiếu.
- Xem quan hệ phụ thuộc giữa các module.
- Tạo danh sách module làm đầu vào cho jlink.

Ví dụ kiểm tra dependency tới JDK internal API:

~~~bash
jdeps --jdk-internals app.jar
~~~

Ví dụ xem dependency class-level chi tiết, kể cả các dependency trong cùng archive:

~~~bash
jdeps -verbose:class -filter:none app.jar
~~~

Ví dụ phân tích đệ quy và cung cấp các thư viện ngoài:

~~~bash
jdeps --recursive --class-path "lib/*" app.jar
~~~

Các lệnh trên phân tích những class file mà jdeps được cung cấp và có thể tìm thấy qua class path hoặc module path. Chúng không chạy ứng dụng để khám phá mọi lớp sẽ được tải trong runtime.

## 2. Vì sao phân tích tĩnh không thể nhìn thấy mọi dependency?

Một class file có thể chứa tham chiếu kiểu rõ ràng tới class khác, ví dụ kiểu của field, tham số, giá trị trả về, lệnh tạo object hoặc lời gọi method. Những tham chiếu này tạo ra dấu vết mà công cụ phân tích bytecode có thể đọc.

Nhưng ứng dụng Java còn có thể chọn lớp tại runtime. Tên lớp có thể đến từ:

- Một chuỗi được ghép từ nhiều giá trị.
- File properties, YAML, JSON hoặc XML.
- Cơ sở dữ liệu hoặc biến môi trường.
- Danh sách plugin hoặc service provider.
- Một class loader tùy chỉnh.
- Một framework dùng reflection hoặc method handle.
- Bytecode được sinh trong bộ nhớ từ dữ liệu runtime.

Trong những trường hợp đó, class file của ứng dụng có thể chỉ chứa lời gọi tới API tổng quát như Class.forName, ClassLoader.loadClass hoặc MethodHandles.Lookup.findClass. Tên class đích không nhất thiết xuất hiện dưới dạng tham chiếu class trong bytecode.

jdeps không thực thi những lời gọi này, không đọc và diễn giải mọi file cấu hình của ứng dụng, cũng không dự đoán được giá trị mà hệ thống bên ngoài sẽ cung cấp lúc chạy.

Oracle lưu ý rõ rằng jdeps là công cụ phân tích tĩnh và có thể không đưa ra danh sách dependency đầy đủ. Ví dụ, nếu code dùng reflection để gọi JDK internal API thì jdeps không cảnh báo dependency đó. Xem [hướng dẫn migration của Oracle](https://docs.oracle.com/en/java/javase/26/migrate/preparing-migration.html) và [tài liệu jdeps của JDK 16](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jdeps.html).

## 3. Giới hạn với reflection và Class.forName

Reflection cho phép ứng dụng tìm lớp, constructor, field hoặc method khi chương trình đang chạy. Đây là kỹ thuật hợp lệ và vẫn được dùng trong framework, serializer, dependency injection và hệ thống plugin hiện đại.

Ví dụ:

~~~java
String implementationName =
    System.getProperty("codec.implementation");

Class<?> implementationClass =
    Class.forName(implementationName);

Object implementation =
    implementationClass.getDeclaredConstructor().newInstance();
~~~

Bytecode của đoạn code trên có dependency trực tiếp tới các API như:

- java.lang.System.
- java.lang.Class.
- java.lang.reflect.Constructor.

Nhưng lớp được nạp phụ thuộc giá trị của property codec.implementation. Nếu cấu hình chứa tên com.example.codec.FastCodec, jdeps không thể suy ra rằng FastCodec chắc chắn sẽ được tải chỉ từ lời gọi Class.forName tổng quát.

Ngay cả khi tên lớp được ghi trực tiếp thành string literal:

~~~java
Class<?> type =
    Class.forName("com.example.codec.FastCodec");
~~~

tên này vẫn là dữ liệu chuỗi. Không nên coi nó tương đương với một tham chiếu class tĩnh như:

~~~java
Class<?> type = com.example.codec.FastCodec.class;
~~~

Dạng class literal tạo tham chiếu class rõ ràng trong bytecode. Dạng chuỗi yêu cầu runtime diễn giải tên lớp, nên không cung cấp cho jdeps cùng một dấu vết dependency.

### Reflection tới JDK internal API

Giới hạn này đặc biệt quan trọng khi kiểm tra việc đóng gói JDK:

~~~java
Class<?> type =
    Class.forName("sun.someinternal.InternalType");
~~~

Lệnh sau rất hữu ích để tìm các tham chiếu tĩnh tới JDK internal API:

~~~bash
jdeps --jdk-internals app.jar
~~~

Nhưng nếu tên internal class chỉ xuất hiện trong chuỗi và được dùng qua reflection, kết quả có thể không cảnh báo. Vì vậy, báo cáo không có internal dependency không chứng minh ứng dụng không truy cập internal API bằng reflection. Đây cũng là giới hạn được nêu trong [hướng dẫn migration của Oracle](https://docs.oracle.com/en/java/javase/26/migrate/preparing-migration.html).

## 4. Reflection có thể thất bại dù jdeps không báo lỗi

Việc jdeps không tìm thấy dependency không có nghĩa runtime chắc chắn cho phép truy cập.

Từ JDK 17, strong encapsulation của JDK được áp dụng chặt hơn. Những truy cập reflective vào thành phần không công khai của các API JDK có thể thất bại với InaccessibleObjectException nếu package không được mở phù hợp. Các cơ chế mở package có chủ đích vẫn tồn tại, nhưng cần xem đó là quyết định cấu hình có phạm vi rõ ràng, không phải bằng chứng rằng dependency đã được phân tích đầy đủ. Xem [hướng dẫn migration về strong encapsulation](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html).

Ví dụ:

~~~java
Field field = SomeJdkType.class.getDeclaredField("internalState");
field.setAccessible(true);
~~~

jdeps có thể nhìn thấy tham chiếu tĩnh tới SomeJdkType nếu class được ghi trực tiếp trong bytecode. Nhưng việc truy cập field private bằng reflection là hành vi khác; báo cáo dependency class-level không xác nhận rằng thao tác setAccessible sẽ được phép trong runtime.

Nếu class và member đều được tìm qua chuỗi, cả class đích lẫn member đích có thể không được biểu diễn như dependency tĩnh.

Khi nâng cấp JDK, cần chạy integration test trên đúng runtime mục tiêu để phát hiện lỗi encapsulation. Không dùng kết quả jdeps thay cho kiểm thử quyền truy cập module.

## 5. Giới hạn với tên lớp nằm trong cấu hình chuỗi

Nhiều ứng dụng không ghi tên implementation trực tiếp trong source code. Thay vào đó, cấu hình chọn implementation theo môi trường hoặc tính năng.

Ví dụ file cấu hình:

~~~yaml
codec:
  implementation: com.example.codec.FastCodec
~~~

Code đọc cấu hình:

~~~java
String className = configuration.get("codec.implementation");
Class<?> type = Class.forName(className);
Object codec = type.getDeclaredConstructor().newInstance();
~~~

jdeps có thể tìm dependency tới thư viện cấu hình và reflection API, nhưng không tự hiểu rằng chuỗi trong YAML là tên class phải được đóng gói cùng ứng dụng.

Các nguồn cấu hình tương tự gồm:

| Nguồn | Ví dụ giá trị chứa tên lớp | Vì sao dễ bị bỏ sót |
| --- | --- | --- |
| Properties | codec.class=com.example.FastCodec | Tên lớp là nội dung text |
| YAML | implementation: com.example.FastCodec | Không phải class reference trong bytecode |
| JSON | {"handler":"com.example.JsonHandler"} | Giá trị chỉ được diễn giải lúc chạy |
| XML | class="com.example.XmlHandler" | Tên lớp nằm trong resource |
| Environment variable | APP_PLUGIN=com.example.NativePlugin | Giá trị có thể khác giữa các môi trường |
| Database | Tên adapter được lưu trong bảng cấu hình | Dependency không nằm trong artifact được quét |
| Script hoặc expression | Tên class được tạo từ input runtime | Tên đích có thể không tồn tại trước khi chạy |

Nếu ứng dụng hỗ trợ nhiều profile cấu hình, một lần quét bytecode không thể xác định tất cả implementation được chọn trong từng profile. Cần kiểm kê các cấu hình triển khai và kiểm thử những lựa chọn có thể xảy ra.

## 6. ServiceLoader và plugin provider

ServiceLoader là API chuẩn để tìm implementation của một service tại runtime. Ứng dụng chỉ tham chiếu service interface; provider có thể được triển khai và đóng gói riêng.

Ví dụ:

~~~java
ServiceLoader<CodecProvider> providers =
    ServiceLoader.load(CodecProvider.class);

for (CodecProvider provider : providers) {
    provider.register();
}
~~~

Class file của ứng dụng thể hiện dependency tới CodecProvider và ServiceLoader. Tuy nhiên, provider thực tế có thể được tìm từ các artifact khác nhau.

Trên class path, provider có thể được khai báo bằng resource:

~~~text
META-INF/services/com.example.CodecProvider
~~~

Nội dung file có thể liệt kê:

~~~text
com.example.codec.FastCodecProvider
com.example.codec.LegacyFormatProvider
~~~

Tên provider nằm trong resource chứ không nhất thiết xuất hiện dưới dạng tham chiếu class trong bytecode của ứng dụng. ServiceLoader đọc các provider-configuration file và tải provider một cách lazy khi cần. Chi tiết được mô tả trong [ServiceLoader API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html).

Với named module, module descriptor có thể khai báo:

~~~java
module com.example.codec.fast {
    requires com.example.codec.api;

    provides com.example.CodecProvider
        with com.example.codec.fast.FastCodecProvider;
}
~~~

Ứng dụng tiêu thụ service khai báo:

~~~java
module com.example.application {
    requires com.example.codec.api;

    uses com.example.CodecProvider;
}
~~~

Các directive uses và provides là metadata của module và cần được quản lý cùng module descriptor. Dù vậy, khi kiểm kê provider, vẫn cần kiểm tra module path, class path và các resource triển khai thực tế. Không suy ra rằng chỉ quét JAR ứng dụng đã bao phủ mọi provider có thể được nạp ở runtime. Xem [ServiceLoader API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html).

## 7. Lớp được sinh động trong runtime

Một số framework tạo class mới trong lúc chạy bằng bytecode generation. Ví dụ thường gặp:

- Dynamic proxy.
- Bytecode enhancement cho ORM entity.
- Proxy cho dependency injection hoặc interception.
- Class được tạo bởi Byte Buddy, ASM hoặc framework tương tự.
- Hidden class được định nghĩa từ bytecode trong bộ nhớ.

Ví dụ tạo dynamic proxy:

~~~java
Object proxy = Proxy.newProxyInstance(
    serviceInterface.getClassLoader(),
    new Class<?>[] { serviceInterface },
    invocationHandler
);
~~~

jdeps có thể nhìn thấy dependency tới Proxy API và serviceInterface nếu interface được tham chiếu tĩnh. Nhưng class proxy được sinh ra khi gọi newProxyInstance không nhất thiết tồn tại trong JAR hoặc thư mục class file tại thời điểm quét.

Tương tự, framework có thể đọc metadata của một class, sinh subclass hoặc adapter rồi định nghĩa bytecode trong JVM. jdeps nhìn thấy dependency tới framework và những class reference đã có trong artifact; nó không thể phân tích một class chỉ được tạo sau đó trong heap.

### Class sinh lúc build và class sinh lúc chạy

Cần phân biệt hai trường hợp:

| Loại class | Có thể được jdeps phân tích? | Điều kiện |
| --- | --- | --- |
| Class được annotation processor sinh khi build | Có | File .class đã được biên dịch và nằm trong thư mục/JAR được quét |
| Class được framework sinh và ghi ra đĩa | Có thể | Phải đưa artifact sinh ra vào đầu vào phân tích |
| Proxy class chỉ tồn tại trong bộ nhớ | Không qua lần quét artifact ban đầu | Class chưa tồn tại trong đầu vào tĩnh |
| Hidden class được định nghĩa từ bytecode runtime | Không qua lần quét artifact ban đầu | Không có class file tương ứng trong artifact được quét |
| Plugin JAR được tải từ thư mục bên ngoài | Có thể | Phải quét cả plugin JAR đó |

Nếu framework có chế độ dump generated class ra thư mục, có thể dùng jdeps quét thư mục đó sau khi chạy test. Cách này hữu ích để phân tích những class đã được sinh trong kịch bản kiểm thử; nó vẫn không bao phủ các class chỉ có thể được sinh trong cấu hình hoặc nhánh runtime khác.

## 8. Những dependency khác nằm ngoài phạm vi phân tích bytecode

Reflection, cấu hình chuỗi và generated class không phải các trường hợp duy nhất cần chú ý.

jdeps phân tích dependency của class file. Do đó, một số thông tin không thể suy ra chỉ từ bytecode:

- Native library được nạp qua System.load hoặc System.loadLibrary.
- Tên file cấu hình hoặc tài nguyên chỉ được truy cập bằng tên chuỗi.
- Class được tải từ plugin directory bên ngoài artifact chính.
- Dependency được lấy từ database, remote registry hoặc network.
- Class chỉ được tạo khi một feature flag hoặc profile cụ thể được bật.
- Điều kiện quyền truy cập module, filesystem hoặc security policy tại runtime.

Các trường hợp này cần công cụ và kiểm thử bổ sung. jdeps không phải runtime tracer, không phải scanner toàn bộ resource và cũng không phải bộ xác minh cấu hình triển khai.

## 9. Các tùy chọn jdeps có thể làm phạm vi báo cáo hẹp hơn

Ngay cả dependency tĩnh cũng có thể không xuất hiện trong báo cáo nếu phạm vi đầu vào hoặc filter chưa đúng.

| Tùy chọn | Tác dụng | Rủi ro khi diễn giải |
| --- | --- | --- |
| **-apionly** | Chỉ phân tích dependency từ public/protected API signature | Có thể bỏ qua dependency trong phần triển khai private |
| **--class-path** | Chỉ định vị trí tìm class ngoài | Thiếu thư viện ở đây có thể làm kết quả thiếu hoặc báo unresolved |
| **--module-path** | Chỉ định module path | Không bao gồm module/plugin ở vị trí khác |
| **--no-recursive** | Không đi sâu dependency bắc cầu | Chỉ thấy lớp dependency trực tiếp trong phạm vi đã chọn |
| **-include** | Giới hạn class được phân tích bằng pattern | Class bị loại khỏi phạm vi sẽ không có trong báo cáo |
| **-filter** | Lọc dependency theo pattern | Có thể ẩn các cạnh dependency cần xem |
| **--multi-release** | Chọn phiên bản class trong multi-release JAR | Chọn sai target có thể phân tích nhầm implementation |
| **--ignore-missing-deps** | Bỏ qua dependency bị thiếu | Có thể che khuất vấn đề cần xử lý |

Các tùy chọn này hữu ích khi muốn trả lời một câu hỏi cụ thể. Nhưng khi rà soát toàn ứng dụng, cần ghi lại chính xác đầu vào, class path, module path, phiên bản multi-release và filter đã dùng. Đừng coi báo cáo rút gọn là toàn bộ dependency graph.

## 10. Quy trình quét tĩnh có phạm vi rõ ràng

Một quy trình cơ bản để rà soát dependency của ứng dụng:

### Bước 1: Xác định artifact sẽ triển khai

Thu thập:

- JAR ứng dụng hoặc thư mục class đã build.
- Toàn bộ thư viện runtime.
- Plugin JAR được phân phối cùng ứng dụng.
- Module path nếu ứng dụng dùng named module.
- Các multi-release JAR và phiên bản Java mục tiêu.
- File module descriptor và resource service provider.

Không chỉ quét một JAR nếu ứng dụng thực tế chạy với nhiều thư viện hoặc plugin.

### Bước 2: Tìm JDK internal API

~~~bash
jdeps --jdk-internals --recursive --class-path "lib/*" app.jar
~~~

Kết quả giúp tìm các class reference tĩnh tới internal API trong đầu vào và class path đã chỉ định. Vẫn phải rà soát reflection và cấu hình chuỗi riêng.

### Bước 3: Tìm dependency class-level

~~~bash
jdeps -verbose:class -filter:none --recursive --class-path "lib/*" app.jar
~~~

Dùng kết quả để hiểu quan hệ class-level và phát hiện dependency trong implementation. Đối với dự án lớn, có thể xuất DOT để xem graph:

~~~bash
jdeps --dot-output dependency-graph --recursive --class-path "lib/*" app.jar
~~~

### Bước 4: Kiểm tra dependency bị thiếu

~~~bash
jdeps --missing-deps --class-path "lib/*" app.jar
~~~

Đây là kiểm tra các dependency tĩnh mà jdeps không phân giải được trong phạm vi đã cung cấp. Nó không phát hiện class name chỉ nằm trong cấu hình hoặc reflection.

### Bước 5: Xác định module cần cho runtime image

~~~bash
jdeps --print-module-deps --recursive --class-path "lib/*" app.jar
~~~

Danh sách module có thể dùng làm đầu vào cho jlink. Trước khi tạo image tối giản, phải bổ sung những module cần thiết nhưng chỉ được tham chiếu động, ví dụ module của plugin được chọn từ cấu hình.

Các option và đầu ra trên được mô tả trong [tài liệu jdeps của JDK 16](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jdeps.html) và [tài liệu jdeps của JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html).

## 11. Rà soát tên lớp trong resource và cấu hình

Sau khi quét bytecode, kiểm tra những nơi chứa tên lớp hoặc tên module ở dạng dữ liệu.

Danh sách cần rà soát:

- META-INF/services trong tất cả JAR.
- application.properties và các file cấu hình theo profile.
- YAML, JSON, XML.
- Script hoặc expression được ứng dụng thực thi.
- Biến môi trường và tham số JVM.
- Plugin directory và manifest.
- File cấu hình framework, ORM, serializer và dependency injection.
- Cơ sở dữ liệu hoặc registry lưu tên implementation.

Có thể tìm tên package của ứng dụng trong resource bằng công cụ tìm kiếm văn bản hoặc script kiểm kê. Nhưng tìm kiếm chuỗi chỉ hỗ trợ rà soát; tên lớp có thể được tạo từ nhiều mảnh, mã hóa hoặc lấy từ nguồn ngoài nên không thể bảo đảm tìm thấy tất cả.

Với hệ thống plugin, nên duy trì một danh sách provider được hỗ trợ và xác minh từng provider có mặt trong artifact triển khai. Nếu cấu hình cho phép nạp plugin tùy ý, cần thiết kế cơ chế phân phối và kiểm tra dependency cho plugin đó riêng.

## 12. Kiểm tra runtime để bổ sung những gì jdeps không thấy

Sau quét tĩnh, hãy chạy ứng dụng trên JDK mục tiêu với các profile cấu hình quan trọng. Kiểm thử nên kích hoạt:

- Mỗi plugin hoặc provider được hỗ trợ.
- Mỗi profile có thể chọn implementation khác nhau.
- Các đường code dùng reflection.
- Những tính năng tạo proxy hoặc generated class.
- Các luồng xử lý phụ thuộc vào module hoặc native library.
- Những cấu hình triển khai thực tế.

Có thể bật unified logging để quan sát class loading trong môi trường kiểm thử:

~~~bash
java -Xlog:class+load=info -jar app.jar
~~~

Log cho biết các class đã được JVM nạp trong lần chạy đó và nguồn class tương ứng nếu runtime cung cấp. Đây là dữ liệu bổ sung để đối chiếu với danh sách class file đã quét.

Tuy nhiên, log runtime chỉ cho biết những class đã được tải trong kịch bản vừa chạy. Một plugin chưa được chọn, một nhánh hiếm hoặc một profile khác vẫn có thể chưa xuất hiện. Vì vậy, cần chạy đủ kịch bản kiểm thử và ghi nhận profile/configuration đã sử dụng.

## 13. Không dùng kết quả jdeps đơn lẻ để quyết định jlink

**jlink** tạo custom runtime image từ các module JDK và dependency module của chúng. jdeps có thể tạo danh sách module qua **--print-module-deps**, nhưng danh sách đó dựa trên dependency tĩnh trong các artifact được phân tích.

Ví dụ:

~~~bash
jdeps --print-module-deps --recursive --class-path "lib/*" app.jar
~~~

Giả sử kết quả có:

~~~text
java.base,java.logging,java.sql
~~~

Danh sách này có thể phù hợp với đường chạy đã được biểu diễn trong bytecode. Nhưng nếu ứng dụng tải provider JDBC, serializer hoặc plugin qua reflection và cấu hình, module cần cho provider đó có thể không xuất hiện trong kết quả tĩnh. Tài liệu jdeps mô tả đầu ra này là danh sách module dependency được suy ra từ phân tích dependency của artifact, có thể dùng làm đầu vào cho jlink.

Trước khi tạo runtime image tối giản:

1. Quét tất cả class file và thư viện runtime.
2. Kiểm kê provider và plugin trong module path, class path và resource.
3. Kiểm tra tên lớp được cấu hình hoặc tải qua reflection.
4. Xác định module JDK mà các plugin đó cần.
5. Bổ sung module cần thiết vào danh sách jlink.
6. Chạy integration test trên chính image vừa tạo, không chỉ trên JDK đầy đủ.

Nếu ứng dụng hỗ trợ plugin được cài sau khi đóng gói image, cần xác định rõ module runtime nào được phép mở rộng và kiểm thử quy trình đó. Không nên giả định một image chỉ chứa kết quả jdeps sẽ chạy được mọi plugin có thể được cấu hình sau này. Tham khảo [jdeps command reference](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html) và [jlink command reference](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html).

## 14. Checklist đánh giá mức độ đầy đủ của dependency report

| Câu hỏi | Nếu chưa xác nhận |
| --- | --- |
| Đã quét tất cả JAR và thư mục class trong runtime chưa? | Dependency từ thư viện ngoài có thể bị bỏ sót |
| Class path và module path có giống môi trường triển khai không? | jdeps có thể không phân giải đúng dependency |
| Đã chọn đúng phiên bản cho multi-release JAR chưa? | Có thể phân tích sai class variant |
| Đã kiểm tra reflection và Class.forName chưa? | Target class có thể không xuất hiện trong graph |
| Đã kiểm tra class name trong properties, YAML, JSON, XML chưa? | Dependency từ cấu hình có thể bị bỏ sót |
| Đã kiểm tra META-INF/services và module provides chưa? | Provider có thể chưa được kiểm kê |
| Đã kiểm tra plugin được tải từ thư mục ngoài chưa? | Artifact plugin có thể nằm ngoài phạm vi scan |
| Đã xem xét class được sinh trong runtime chưa? | Generated class có thể không tồn tại trong đầu vào tĩnh |
| Đã kiểm tra native library chưa? | Dependency native không được biểu diễn đầy đủ bằng class graph |
| Đã chạy các profile và plugin quan trọng chưa? | Đường tải lớp động có thể chưa được kích hoạt |
| Đã thử chạy custom runtime image chưa? | Danh sách module có thể chưa đủ |

## 15. Kết luận

jdeps là công cụ phân tích dependency tĩnh quan trọng trong quy trình đóng gói JDK. Nó đọc class file, thư mục và JAR để phát hiện dependency class/package/module, tìm tham chiếu tĩnh tới JDK internal API và hỗ trợ tạo danh sách module cho jlink.

Giới hạn của công cụ nằm ở những dependency chỉ được xác định trong runtime: reflection với tên lớp dạng chuỗi, class name trong file cấu hình hoặc resource, provider được phát hiện động và bytecode được sinh trong bộ nhớ. Oracle cũng cảnh báo rằng phân tích tĩnh có thể không đầy đủ và jdeps không cảnh báo được một số trường hợp gọi internal API qua reflection.

Hãy kết hợp quét jdeps với kiểm kê resource/configuration, rà soát plugin, kiểm thử trên JDK mục tiêu và theo dõi class loading trong các kịch bản đại diện. Chỉ dùng kết quả sau khi đã kiểm tra các dependency động để quyết định module cần giữ trong custom runtime image. Cách làm này giúp tránh đóng gói thiếu module hoặc bỏ sót dependency chỉ xuất hiện trong một profile triển khai.

## Tài liệu tham khảo

- [The jdeps Command — Java SE 16](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jdeps.html)
- [The jdeps Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)
- [Preparing for Migration — Run jdeps on Your Code, Java SE 26](https://docs.oracle.com/en/java/javase/26/migrate/preparing-migration.html)
- [ServiceLoader — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html)
- [JDK Migration Guide — Strong Encapsulation in the JDK](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html)
- [The jlink Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html)

