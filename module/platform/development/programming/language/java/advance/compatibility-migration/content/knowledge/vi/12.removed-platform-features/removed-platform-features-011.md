# Xác minh danh mục bị xóa theo từng JDK thay vì suy ra từ cảnh báo cũ

Trong dự án **Java Advance Compatibility Migration**, cảnh báo deprecated là tín hiệu cần điều tra, không phải bằng chứng cuối cùng rằng một API hoặc công cụ đã bị xóa. Một thành phần từng được đánh dấu deprecated có thể còn tồn tại qua nhiều bản Java; ngược lại, một API đã bị loại bỏ có thể không còn xuất hiện trong báo cáo deprecation của JDK mới. Khi runtime từ chối truy cập một class nội bộ, nguyên nhân cũng có thể là strong encapsulation thay vì class đã biến mất.

Vì vậy, cần xây dựng danh mục dựa trên **JDK nguồn, JDK đích, bản phân phối, loại thành phần, nguồn thay đổi và bằng chứng thực tế**, thay vì sao chép một danh sách cảnh báo từ bản Java cũ. Bài học trình bày cách phân loại, kiểm tra và ghi nhận những API, module, công cụ và tùy chọn JVM có khả năng ảnh hưởng tới nâng cấp Java.

## 1. Câu hỏi cần trả lời trước khi kết luận API bị xóa

Một kết luận hữu ích phải nói rõ:

- **Thành phần nào?** Tên đầy đủ của class, method, module, executable hay VM option.
- **Từ phiên bản nào sang phiên bản nào?** Ví dụ JDK 8 sang JDK 17, không chỉ ghi Java mới.
- **Bản phân phối và môi trường nào?** JDK đầy đủ hay custom runtime image, OS và kiến trúc CPU.
- **Điều gì đã xảy ra?** Không biên dịch, không nạp được class, không thấy công cụ, bị từ chối truy cập hay thay đổi hành vi.
- **Bằng chứng là gì?** Release notes, JEP, API docs, lệnh trên JDK đích, log hoặc test.
- **Consumer nào bị ảnh hưởng?** Ứng dụng, thư viện, plugin, code generator, build script hoặc Java agent.

Câu “API X không chạy trên Java 17” không đủ để quyết định cách sửa. Nếu API đã bị loại khỏi JDK thì cần phương án thay thế; nếu API vẫn tồn tại nhưng package chưa được mở, cần xử lý quyền truy cập JPMS hoặc bỏ reflection nội bộ. Hai trường hợp này khác bản chất.

## 2. Phân biệt các trạng thái thường bị nhầm lẫn

| Trạng thái | Ý nghĩa | Hướng xác minh |
|---|---|---|
| Available | Thành phần có mặt trên JDK được kiểm tra | API docs, module list, kiểm tra tool và compile |
| Deprecated | Thành phần còn tồn tại nhưng được khuyến cáo không dùng cho code mới | Annotation, Javadoc và deprecation report |
| Deprecated for removal | Nhà cung cấp công bố ý định loại bỏ ở tương lai | Tài liệu deprecation và release notes, không tự suy ra ngày xóa |
| Removed | Thành phần không còn được cung cấp trong bản JDK đang xét | Release notes/JEP và kiểm tra trực tiếp target JDK |
| Strongly encapsulated | Member hoặc package vẫn tồn tại nhưng bị giới hạn truy cập | Thông báo JPMS, exports, opens và reflection test |
| Unbundled | Thành phần không còn đi kèm JDK mặc định, có thể dùng gói bên ngoài | Release notes và dependency độc lập |
| Disabled hoặc unsupported | API/tool vẫn có dấu vết nhưng cơ chế cũ không còn hoạt động hay được hỗ trợ | Tài liệu và runtime behavior |
| Vendor-specific | Thành phần phụ thuộc JDK distribution hoặc bản build | Chính sách vendor, package list và phiên bản chính xác |

Một item có thể đổi trạng thái qua nhiều release. Nhưng **deprecated for removal** không có nghĩa “removed ở release kế tiếp”, và “không còn trong runtime image” không có nghĩa “đã bị xóa khỏi đặc tả Java SE”.

### 2.1. Ví dụ deprecated chưa bị xóa

~~~java
/**
 * @deprecated Use the replacement method instead.
 */
@Deprecated(since = "2.1", forRemoval = true)
public void oldOperation() {
    // Existing implementation.
}
~~~

Trong phiên bản chứa khai báo trên, method vẫn tồn tại và caller có thể tiếp tục gọi nếu thỏa các điều kiện truy cập. Annotation cho công cụ biết ý định deprecation; nó không tự loại method khỏi class file.

Nếu release sau thực sự xóa method, source consumer có thể không biên dịch lại, còn bytecode consumer cũ có thể gặp `NoSuchMethodError` khi gọi. Danh mục migration nên ghi riêng **mốc bắt đầu deprecated** và **mốc xác nhận removed**.

### 2.2. Ví dụ không truy cập được nhưng chưa chắc đã xóa

~~~java
import java.lang.reflect.Field;

Field field = String.class.getDeclaredField("value");
field.setAccessible(true);
~~~

Trên một JDK hiện đại, `setAccessible(true)` có thể ném `InaccessibleObjectException` do `java.base` không mở `java.lang` cho module gọi. Đây là vấn đề **access restriction**. Không nên ghi private field đó “đã bị xóa” chỉ vì thiếu quyền deep reflection.

Nếu `getDeclaredField` ném `NoSuchFieldException`, đó lại là một dấu hiệu khác: member với tên được tìm không tồn tại theo cách tìm kiếm ấy. Chi tiết nội bộ của `String` có thể thay đổi giữa JDK, nên việc dựa vào field nội bộ không được khuyến nghị.

## 3. Cảnh báo cũ chỉ phản ánh một thời điểm

Một cảnh báo compiler có thể trông như sau:

~~~text
[removal] oldMethod() has been deprecated and marked for removal
~~~

Điều đó mô tả cách compiler của release đang dùng xem oldMethod, không phải lịch sử đầy đủ của nó. Đặc biệt:

1. API có thể mới chỉ deprecated mà vẫn chạy.
2. API có thể đã bị xóa ở JDK đích dù trước đây chỉ có warning.
3. API có thể không còn trong tập API để `jdeprscan` báo cáo.
4. Warning có thể đến từ dependency bên thứ ba, không phải API JDK.
5. Một tool bị xóa có thể không tạo warning compile vì pipeline chỉ gọi executable.
6. Reflection theo tên class trong string có thể không tạo symbolic reference để static analysis tìm được.

Do đó, cảnh báo phải trở thành **candidate trong danh mục điều tra**, không phải nhãn “REMOVED” có sẵn.

## 4. Không dùng một số phiên bản Java chung cho mọi thành phần

Java SE feature release, JDK update/build và bản phân phối JDK là các thông tin khác nhau. Chẳng hạn, Java 17 xác định thế hệ nền tảng, nhưng những JDK 17 được phát hành bởi các vendor có thể khác bản vá, công cụ đóng gói và phạm vi OS được hỗ trợ.

Khi ghi lại kết quả, tối thiểu cần:

~~~yaml
source:
  javaFeature: 8
  vendor: "record actual vendor"
target:
  javaFeature: 17
  updateBuild: "record exact build"
  vendor: "record actual vendor"
  os: "linux-x64"
subject:
  kind: "jdk-module"
  name: "example.module"
~~~

Ví dụ YAML này chỉ mô tả cấu trúc hồ sơ, không phải bằng chứng một module cụ thể đã bị xóa.

Cũng phải phân biệt JDK đầy đủ với runtime image tạo bằng `jlink`. Một module bị lược khỏi runtime image của ứng dụng có thể vẫn được cung cấp trong JDK đầy đủ cùng release.

## 5. Đối chiếu tài liệu phát hành theo từng JDK

Các nguồn quan trọng gồm:

| Nguồn | Dùng để xác minh | Không nên suy diễn |
|---|---|---|
| Release notes của JDK đích | Các tính năng, công cụ, module, option bị thay đổi hoặc xóa | Không phải danh mục mọi vấn đề của consumer |
| JDK Migration Guide | Những điểm cần chú ý và hướng chuyển đổi | Không đảm bảo bao phủ mọi API ngoài Java SE |
| JDK Enhancement Proposal (JEP) | Phạm vi, lý do, thiết kế của thay đổi | Một proposal chưa chắc đã được triển khai đúng release dự kiến |
| Java SE API docs | Class/method còn có, deprecated hoặc for removal | Sự vắng mặt không xác định chính xác mốc removed đầu tiên |
| Module descriptor và JDK module list | Module, package export/open ở runtime cụ thể | Không chứng minh toàn bộ API hoặc behavior |
| Release notes của vendor | Khác biệt build, đóng gói và hỗ trợ | Không thay thế kiểm thử consumer thực tế |
| Log, compiler và test | Tác động trên ứng dụng cụ thể | Chỉ bao phủ JDK, code path và môi trường đã thử |

Khi dùng JEP, cần xác nhận nó được tích hợp vào release nào, thay vì lấy JEP đang được thảo luận làm bằng chứng API đã biến mất. Với thay đổi trong tương lai, dùng trạng thái **planned** hoặc **proposed**, không dùng **removed**.

## 6. Các mốc lịch sử minh họa: phân loại cho đúng

Bảng sau chỉ minh họa các loại thay đổi thường gặp; **không phải danh mục đầy đủ của từng JDK**.

| Release | Thành phần | Bản chất thay đổi |
|---|---|---|
| JDK 9 | `rt.jar` và `tools.jar` theo cấu trúc JDK 8 | Thay đổi layout runtime/tooling khi chuyển sang modular runtime image |
| JDK 11, JEP 320 | Các module Java EE và CORBA từng được kèm trong JDK | Loại bỏ module và những thành phần liên quan khỏi JDK |
| JDK 14, JEP 367 | Pack200 API cùng công cụ pack200/unpack200 | Loại bỏ API và công cụ đóng gói Pack200 |
| JDK 15, JEP 372 | Nashorn JavaScript engine và công cụ jjs | Loại bỏ engine/tool; không phải xóa toàn bộ Java Scripting API |
| JDK 17, JEP 407 | RMI Activation | Loại bỏ RMI Activation, không phải toàn bộ Java RMI |
| JDK 17, JEP 403 | Strong encapsulation của JDK internals | Siết chặt quyền truy cập, không tự đồng nghĩa xóa class |

Một số ví dụ cho thấy vì sao phải viết trạng thái chính xác.

### 6.1. JDK 9 và runtime layout

Trong nhiều JDK 8, script có thể dùng đường dẫn như:

~~~text
$JAVA_HOME/jre/lib/rt.jar
$JAVA_HOME/lib/tools.jar
~~~

Sang JDK 9, runtime image đã được tổ chức theo module. Đường dẫn JAR cũ không còn phù hợp, nhưng điều đó **không có nghĩa mọi class từng nằm trong rt.jar đã bị xóa**. Thay đổi có thể nằm ở cách build tool hoặc script tìm runtime class.

Giải pháp là dùng compiler, API và cơ chế module/classpath được hỗ trợ thay vì phụ thuộc trực tiếp vào cấu trúc cài đặt JDK cũ.

### 6.2. JDK 11 và các module Java EE/CORBA

Một ứng dụng JDK 8 có thể dùng:

~~~java
import javax.xml.bind.JAXBContext;

JAXBContext context = JAXBContext.newInstance(Customer.class);
~~~

Các module từng tích hợp trong JDK bị loại bỏ theo JEP 320 ở JDK 11. Nếu không thêm dependency phù hợp, consumer có thể gặp lỗi compile như:

~~~text
package javax.xml.bind does not exist
~~~

hoặc lỗi runtime như:

~~~text
java.lang.NoClassDefFoundError: javax/xml/bind/JAXBContext
~~~

Điều này không chứng minh công nghệ JAXB hoàn toàn không còn sử dụng được. Có thể chọn một API và implementation JAXB được phân phối độc lập, kiểm tra version, classpath, module path và compatibility. Cần lưu ý namespace `javax.xml.bind` khác `jakarta.xml.bind` ở một số thế hệ mới; đổi dependency không nhất thiết là phép thay thế nhị phân một-một.

### 6.3. JDK 14 và Pack200

Nếu pipeline dùng executable `pack200` hoặc `unpack200`, hoặc tham chiếu API `java.util.jar.Pack200`, hãy xác minh thay đổi theo JEP 367 và trên JDK đích. Vì đây là công cụ đóng gói, ứng dụng Java chính có thể vẫn biên dịch nhưng pipeline build/release lại hỏng.

Mục kiểm kê cần thể hiện owner của script đóng gói và phương án thay thế, thay vì chỉ kiểm tra import Java.

### 6.4. JDK 15 và Nashorn

Java Scripting API có thể được dùng như sau:

~~~java
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;

ScriptEngine engine = new ScriptEngineManager()
        .getEngineByName("nashorn");
~~~

Khi Nashorn không còn đi kèm JDK, Java Scripting API không nhất thiết biến mất; method `getEngineByName("nashorn")` có thể trả `null` nếu không có engine phù hợp trên classpath/module path. Do đó, báo cáo chính xác là **Nashorn engine/tool bị loại bỏ**, không phải `ScriptEngineManager` bị xóa.

### 6.5. JDK 17 và RMI Activation

JEP 407 loại bỏ RMI Activation. Một ứng dụng dùng RMI cần phân biệt có thật sự dùng cơ chế activation hay chỉ dùng những chức năng RMI khác. Viết “Java RMI bị xóa ở Java 17” là đánh đồng phạm vi và có thể dẫn tới thay đổi không cần thiết.

### 6.6. JDK 17 và strong encapsulation

JEP 403 áp dụng strong encapsulation chặt chẽ cho các nội bộ JDK. Một thư viện cũ có thể thất bại ở `setAccessible(true)` dù class vẫn còn. Cần ghi trạng thái **access restricted**, không phải **removed**, sau đó cân nhắc nâng thư viện hoặc bỏ truy cập private internals.

## 7. Bước đầu: xác định JDK thực sự được dùng

Chạy các lệnh thích hợp cho đúng tiến trình/môi trường:

~~~bash
java -version
javac -version
jdeps --version
~~~

Nếu build dùng Gradle, kiểm tra runtime Gradle:

~~~bash
./gradlew -version
~~~

Tuy nhiên, Java toolchain cho compile, Gradle daemon, test JVM và production JVM có thể khác nhau. Một danh mục migration cần ghi đủ:

- Java feature/update/build và vendor của compiler.
- Java feature/update/build và vendor của runtime thực tế.
- OS, architecture, container image hoặc custom runtime image.
- Phiên bản build tool/plugin/agent có khả năng dùng internal JDK API.
- Classpath/module path và dependency graph.

Không sử dụng một kết quả `java -version` ở máy cá nhân để tuyên bố production đã được xác minh.

## 8. Tạo danh sách ứng viên từ source, dependency và script

Trước khi tra release notes, xác định dự án thực sự sử dụng gì:

- Import và method call tới API JDK cũ.
- Class được nạp bằng `Class.forName`.
- Truy cập private field qua `getDeclaredField` và `setAccessible`.
- Tool JDK được gọi từ Gradle/Maven, shell script hoặc CI.
- JVM option trong Dockerfile, startup script, service manager.
- JNI/native code hoặc Java agent.
- Dependency nhị phân và shaded/fat JAR.

Ví dụ tìm kiếm sơ bộ bằng ripgrep, nếu có cài đặt:

~~~bash
rg -n "javax\.xml\.bind|javax\.xml\.ws|java\.util\.jar\.Pack200" src
rg -n "sun\.|jdk\.internal\.|Class\.forName|setAccessible" src
rg -n "rt\.jar|tools\.jar|pack200|jjs|--illegal-access" .
~~~

Kết quả chỉ là **ứng viên**. Code nằm trong JAR bên ngoài có thể không xuất hiện trong source repository, trong khi comment hoặc tài liệu có thể gây false positive. Khi cần, bổ sung kiểm kê dependency, module và code được sinh tự động.

## 9. Kiểm tra module trực tiếp trên JDK đích

Các lệnh dưới đây phải chạy trên **JDK/runtime image đang được đánh giá**:

~~~bash
java --list-modules
~~~

Có thể xem mô tả module cụ thể:

~~~bash
java --describe-module java.xml
~~~

Nếu một module không tồn tại trong runtime, điều đó chứng minh **runtime đang kiểm tra không cung cấp module đó**. Muốn biết release đầu tiên loại bỏ, phải đối chiếu thêm tài liệu lịch sử. Nếu chỉ kiểm trên một image tạo bằng `jlink`, module vắng mặt có thể do người tạo image cố tình không đóng gói.

Cần phân biệt:

- Không tìm thấy module.
- Module có nhưng package không được export.
- Package được export nhưng không mở cho deep reflection.
- API nằm trong dependency bên ngoài chứ không thuộc module JDK.

Mỗi trường hợp dẫn tới giải pháp khác nhau.

## 10. Kiểm tra bằng compiler và runtime của target JDK

Một source probe có thể giúp xác minh một API có sẵn để biên dịch:

~~~java
import javax.xml.bind.JAXBContext;

public class ApiProbe {
    JAXBContext context;
}
~~~

Nếu mục đích là xem full JDK đích còn cung cấp package hay không, thử biên dịch **không thêm dependency bên ngoài**:

~~~bash
javac ApiProbe.java
~~~

Lỗi `package ... does not exist` là một quan sát cụ thể. Nhưng nó không cho biết API chưa từng có, đã bị xóa, thiếu dependency hay chỉ chưa được resolve. Cần đối chiếu tài liệu và classpath/module path.

Nếu dùng compiler mới hơn để chọn tập API Java SE của release thấp hơn:

~~~bash
javac --release 17 ApiProbe.java
~~~

`--release` đặt language level, class-file target và tập API Java SE mà compiler cho phép. Nó không chứng minh mọi thư viện ngoài Java SE, module JDK ngoài phạm vi đó hoặc runtime image production đều tương thích. Để xác nhận một tool/module cụ thể được cung cấp trên JDK đích, dùng JDK đó kiểm tra riêng.

### 10.1. Binary và runtime evidence

Nếu bytecode cũ gọi một member không còn ở JDK mới, lỗi có thể là `NoSuchMethodError` hoặc `NoSuchFieldError`. Khi một class không nạp được, có thể gặp `NoClassDefFoundError`. Nhưng những lỗi này cũng có thể đến từ thư viện ngoài hoặc classpath sai.

Một số lỗi dễ bị gộp nhầm:

| Lỗi | Hướng kiểm tra đầu tiên |
|---|---|
| `cannot find symbol` | Source signature, compiler, API và dependency |
| `NoClassDefFoundError` | Classpath/module path, missing dependency, class loading |
| `NoSuchMethodError` | Binary API thay đổi hoặc version conflict |
| `InaccessibleObjectException` | JPMS opens và deep reflection |
| `IllegalAccessError` | JVM access/linkage và exports |
| `UnsupportedClassVersionError` | Class-file version cao hơn JVM runtime |
| `Unrecognized VM option` | Tùy chọn JVM không được build hiện tại nhận diện |

Không nên chuyển tất cả thành một nhãn “removed JDK API”.

## 11. `jdeprscan`: phát hiện deprecation, không tái dựng lịch sử loại bỏ

`jdeprscan` hỗ trợ tìm các tham chiếu bytecode tới API Java SE deprecated theo dữ liệu release mà công cụ cung cấp.

Ví dụ:

~~~bash
jdeprscan --release 17 app.jar
~~~

Để tập trung vào API được đánh dấu for removal:

~~~bash
jdeprscan --release 17 --for-removal app.jar
~~~

Trước khi chạy, xem các release và option mà phiên bản tool hỗ trợ:

~~~bash
jdeprscan --help
~~~

Công cụ này hữu ích để biết consumer nào đang phụ thuộc API được cảnh báo ở mức deprecation. Nhưng cần nhớ:

1. `--for-removal` không cung cấp một ngày xóa chắc chắn.
2. API đã bị xóa khỏi release được phân tích không nhất thiết xuất hiện trong danh mục deprecated.
3. Reflection động và native code có thể không được phát hiện.
4. Công cụ không thay thế kiểm tra executable, JVM option hoặc dependency ngoài Java SE.
5. Kết quả phụ thuộc artifact và dependency path đưa vào.

Do đó, nhãn phù hợp là **deprecated / deprecated for removal detected**, không tự đổi thành **removed in target**.

## 12. `jdeps`: tìm tham chiếu tĩnh tới API JDK nội bộ

Để kiểm kê phụ thuộc bytecode vào JDK internals:

~~~bash
jdeps --jdk-internals app.jar
~~~

Với thư viện runtime trong classpath:

~~~bash
jdeps --jdk-internals --recursive \
  --class-path "lib/*" app.jar
~~~

Một cảnh báo tới `sun.misc.Unsafe` cho thấy ứng dụng phụ thuộc internal API được công cụ nhận diện. Nó **không tự khẳng định class đã biến mất**. Một số critical internal API có thể còn được cung cấp qua module `jdk.unsupported` trên những release hiện đại, nhưng không có hợp đồng Java SE công khai như API tiêu chuẩn.

Ngoài ra, `jdeps` là static analysis. Nó không đảm bảo phát hiện code chỉ truy cập thông qua string/reflection, bytecode phát sinh động, JNI hoặc plugin không đưa vào tập quét.

Có thể dùng:

~~~bash
jdeps --list-deps app.jar
~~~

để hỗ trợ kiểm tra module dependencies. Danh sách này cũng không bao phủ mọi dependency chỉ được tải động.

## 13. Kiểm tra executable và JVM option riêng với API Java

Một build pipeline có thể dùng các tool JDK cũ nhưng source code không hề import API liên quan. Do đó cần kiểm tra trực tiếp thư mục bin của JDK đích.

Ví dụ Linux/macOS:

~~~bash
"$JAVA_HOME/bin/java" -version
ls "$JAVA_HOME/bin"
~~~

Ví dụ PowerShell:

~~~powershell
& "$env:JAVA_HOME\bin\java.exe" -version
Get-ChildItem "$env:JAVA_HOME\bin"
~~~

Đừng chỉ gọi `pack200` hoặc `jjs` qua PATH vì PATH có thể trỏ tới một bản JDK khác hoặc executable cài riêng. Ghi rõ JDK và đường dẫn được dùng để kiểm.

Tương tự, JVM option có thể được deprecated, obsolete, bỏ qua, đổi tên hoặc từ chối. Ví dụ cơ chế `--illegal-access` trong giai đoạn chuyển tiếp JPMS không còn hoạt động như cách bật truy cập toàn cục ở JDK 17 trở lên. Đây là **thay đổi khả năng của option**, không có nghĩa toàn bộ Java reflection API bị xóa.

Khi đọc một log “Unrecognized VM option”, xác nhận option, vendor/build, command line khởi động và tài liệu runtime. Không sửa import Java nếu lỗi thực chất nằm ở startup script.

## 14. Phân biệt thay đổi JDK với thay đổi thư viện bên ngoài

Một số API mang tên package `javax.*` nhưng không nhất thiết thuộc Java SE. Khi một module từng được đóng gói cùng JDK không còn có sẵn, giải pháp có thể là chọn thư viện ngoài được hỗ trợ và kiểm tra namespace.

Ví dụ:

~~~java
import javax.xml.bind.JAXBContext;
~~~

và:

~~~java
import jakarta.xml.bind.JAXBContext;
~~~

không phải hai tên mặc nhiên binary-compatible. Khi chuyển sang một phiên bản Jakarta mới, cần đánh giá import, dependency, serializer behavior và module/classpath.

Nếu một method bị xóa bởi framework hoặc ORM khi nâng dependency, phải ghi là **third-party API change**, không gắn sai cho một Java feature release. Nếu một JAR không nằm trong container mới nhưng còn trong hệ thống cũ, đó có thể là **packaging/deployment change**. Phân loại đúng giúp chọn owner xử lý.

## 15. Mẫu danh mục trạng thái theo từng target JDK

Bản ghi nên đủ cụ thể để người khác kiểm tra lại:

| Trường | Dữ liệu cần lưu |
|---|---|
| Component | Fully qualified name hoặc tool/flag chính xác |
| Kind | Java SE API, JDK internal, JDK module, executable, VM option, third-party |
| Source JDK | Feature, update/build, vendor |
| Target JDK | Feature, update/build, vendor, runtime image |
| First removed in | Chỉ điền khi có bằng chứng lịch sử xác nhận |
| Status on target | Present, deprecated, for-removal, removed, encapsulated, unbundled, unsupported, unknown |
| Consumer | Module, ứng dụng, plugin, script |
| Evidence reference | Release notes/JEP/API docs và log test |
| Impact | Compile, linkage, runtime, build, behavior |
| Replacement | API, dependency, tool hoặc thiết kế mới |
| Owner | Nhóm chịu trách nhiệm và thời hạn xử lý |

Một ví dụ hồ sơ:

~~~yaml
component: "javax.xml.bind.JAXBContext"
kind: "historically bundled JDK module API"
sourceJdk:
  feature: 8
  vendor: "to be filled"
targetJdk:
  feature: 17
  vendor: "to be filled"
statusOnTarget: "not bundled with target JDK"
historicalReference: "JDK 11 release notes / JEP 320"
consumer:
  name: "example-service"
  owner: "example-team"
evidence:
  compileWithoutExternalDependency: "NOT_YET_RUN"
  compileWithReplacementDependency: "NOT_YET_RUN"
replacement: "supported JAXB API/implementation"
~~~

Dữ liệu minh họa này chưa phải kết quả kiểm thử. Khi kiểm thật, cần lưu command, log, artifact checksum, dependency version, OS và ngày thực hiện.

### 15.1. Ma trận JDK

| Thành phần | JDK 8 | JDK 11 | JDK 17 | JDK 21 | Chú ý |
|---|---|---|---|---|---|
| `rt.jar` layout cũ | Có ở JDK 8 thông dụng | Không còn layout cũ | Không còn layout cũ | Không còn layout cũ | Không suy ra toàn bộ API mất |
| JAXB được đóng gói trong JDK | Có trong nhiều JDK 8 | Đã loại khỏi JDK | Không đi kèm JDK | Không đi kèm JDK | Có thể cần external dependency |
| Pack200 của JDK | Có | Có nhưng đã được định hướng loại bỏ | Đã loại khỏi JDK | Đã loại khỏi JDK | Ảnh hưởng tooling |
| Nashorn tích hợp | Có ở JDK 8 | Có | Đã loại khỏi JDK | Đã loại khỏi JDK | API scripting là vấn đề riêng |
| RMI Activation | Có trong các release cũ | Còn trước mốc loại bỏ | Bị loại theo JEP 407 | Không có cơ chế cũ | Không đồng nghĩa toàn bộ RMI mất |
| JPMS strong encapsulation | Chưa có JPMS | Có JPMS với cơ chế chuyển tiếp | Hạn chế chặt hơn | Tiếp tục áp dụng | Phân biệt permission và removal |

Bảng chỉ minh họa những thành phần đã thảo luận, không phải chứng nhận cho tất cả JDK distribution. Nếu mục tiêu là một JDK khác, phải kiểm chứng riêng, không tự sao chép cột JDK 21 sang phiên bản mới hơn.

## 16. Quy trình xác minh có thể lặp lại

### Bước 1: Chốt nguồn và đích

Ghi JDK feature/update, distribution, OS, Java compiler/runtime và cách đóng gói. Nếu hệ thống hỗ trợ cả JDK 17 và 21, cần có bằng chứng tương ứng với cả hai.

### Bước 2: Thu thập candidate

Quét source, dependency, JAR, plugin, build script, runtime flags và log warning. Không đánh dấu removed ngay ở bước này.

### Bước 3: Phân loại

Phân biệt deprecated, for-removal, removed, unbundled, encapsulated, disabled và third-party change. Ghi thành phần cùng owner.

### Bước 4: Tra đúng tài liệu release

Đối chiếu release notes, migration guide, JEP và API/module docs để xác định thay đổi diễn ra ở phiên bản nào và phạm vi ra sao.

### Bước 5: Kiểm tra bằng JDK đích

Chạy module/tool inventory, compile probe, `jdeprscan`, `jdeps` và runtime test tùy loại. Ghi lệnh, version và log.

### Bước 6: Kiểm thử consumer

Biên dịch lại source để kiểm source compatibility; giữ bytecode consumer cũ thử trên runtime mới để kiểm linkage; chạy integration/contract test để kiểm hành vi. Đảm bảo test thực thi code path dùng thành phần nghi ngờ.

### Bước 7: Chọn giải pháp thay thế

Ưu tiên API được hỗ trợ, external library phù hợp hoặc công cụ mới. Nếu dùng `--add-opens` như workaround, ghi rõ đây là giải pháp access tạm thời, không phải phục hồi hợp đồng ổn định cho API nội bộ.

### Bước 8: Lưu kết luận và giới hạn

Mỗi mục nên có status, JDK đã kiểm, nguồn chứng minh, kết quả test, owner, rủi ro chưa xử lý và ngày rà soát. Các mục chưa đủ bằng chứng cần giữ nhãn **UNKNOWN** hoặc **NEEDS_VERIFICATION**, không xếp chung với REMOVED.

### Bước 9: Kiểm tra lại khi đổi JDK đích

Một kết luận trên JDK 17 không tự chứng minh trạng thái trên JDK 21 hoặc JDK 25. Khi đổi target JDK, đối chiếu release notes và chạy lại kiểm tra quan trọng.

## 17. Những sai lầm cần tránh

**“For removal” nghĩa là “đã xóa”.** Không đúng: phải xác minh trạng thái trên target release.

**“Không có warning nên không có API bị xóa”.** API bị xóa có thể đã biến mất khỏi tập deprecation.

**“InaccessibleObjectException nghĩa là class đã biến mất”.** Thường là deep reflection không được phép qua ranh giới module.

**“Không có rt.jar nghĩa là toàn bộ API trong rt.jar đã mất”.** Thay đổi runtime layout khác với removal API.

**“Không còn JAXB trong JDK nghĩa là không thể sử dụng JAXB”.** Có thể chọn dependency ngoài phù hợp và kiểm tương thích thực tế.

**“Nashorn bị xóa nghĩa là javax.script bị xóa”.** Engine/tool và API scripting là những phạm vi khác nhau.

**“JDK 17 xóa toàn bộ RMI”.** JEP 407 chỉ về RMI Activation.

**“jdeprscan --for-removal tạo được danh mục removal đầy đủ”.** Công cụ phát hiện một nhóm deprecation, không khôi phục toàn bộ lịch sử.

**“jdeps không báo thì chắc chắn không có internal API”.** Reflection động và dependency không đưa vào phân tích vẫn là khoảng trống.

**“Một lần kiểm trên máy dev đủ cho mọi JDK sau đó”.** Cần gắn kết luận với JDK/runtime và consumer đã thử.

## 18. Checklist trước khi chốt danh mục

- [ ] Đã ghi chính xác JDK nguồn, JDK đích, vendor/build và runtime image.
- [ ] Đã xác định đầy đủ class/method/module/tool/flag bị nghi ngờ.
- [ ] Đã phân biệt deprecated, for-removal, removed, encapsulated và unbundled.
- [ ] Đã tách JDK change khỏi third-party library và packaging change.
- [ ] Đã đối chiếu release notes/JEP/migration guide của đúng phiên bản.
- [ ] Không gán first removed release nếu chưa có bằng chứng lịch sử.
- [ ] Đã kiểm tra module/package/tool trên JDK đích.
- [ ] Đã kiểm tra compiler, runtime, classpath/module path và dependency.
- [ ] Đã hiểu giới hạn của `jdeprscan` và `jdeps`.
- [ ] Đã kiểm tra reflection, JNI, build scripts và JVM options khi liên quan.
- [ ] Đã chạy consumer test ở code path quan trọng.
- [ ] Đã lưu command, output, JDK build, owner và phương án thay thế.
- [ ] Những mục chưa đủ bằng chứng vẫn có trạng thái chờ xác minh rõ ràng.

## Kết luận

**Danh mục bị xóa phải được xác minh theo từng JDK chứ không suy ra từ cảnh báo cũ.** Deprecated, deprecated for removal, removed, unbundled, encapsulated và disabled là những trạng thái khác nhau, kéo theo những quyết định migration khác nhau. Cảnh báo của compiler và các công cụ tĩnh là đầu vào để điều tra; release notes, JEP, API/module inventory và kết quả compile/runtime trên JDK đích mới giúp xây dựng một kết luận có căn cứ.

Khi lưu rõ thành phần, JDK nguồn/đích, consumer, bằng chứng, phạm vi kiểm tra và giải pháp thay thế, nhóm có thể xử lý đúng các API và công cụ cũ, tránh thay đổi thừa và lặp lại kiểm tra đáng tin cậy trong những đợt nâng cấp Java tiếp theo.
