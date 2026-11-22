# Phát hiện API nội bộ, API bị bỏ và tùy chọn JVM không còn hợp lệ khi nâng cấp lên Java 17

Khi nâng cấp ứng dụng lên Java 17, cần tìm các dependency đang dựa vào API nội bộ của JDK, API đã bị deprecated hoặc loại bỏ, và JVM option không còn được hỗ trợ. Những phụ thuộc này có thể khiến mã nguồn không biên dịch, ứng dụng lỗi khi khởi động, hoặc chỉ thất bại khi chạy một nhánh chức năng ít được sử dụng.

Cần phân biệt ba tình huống:

- **API nội bộ (internal API):** API thuộc implementation của JDK, không phải hợp đồng Java SE ổn định cho ứng dụng. Ví dụ các package `sun.*` hoặc `com.sun.*` nội bộ.
- **API deprecated / for removal:** API vẫn tồn tại nhưng được đánh dấu không nên dùng; một số API còn được đánh dấu dự kiến loại bỏ.
- **API hoặc JVM option đã bị loại bỏ:** thành phần không còn trong JDK 17. Mã nguồn hoặc script khởi động còn phụ thuộc vào nó cần được thay thế.

Bài này tập trung vào cách kiểm tra dự án và dependency bằng công cụ JDK 17, hiểu strong encapsulation của JPMS, lựa chọn phương án thay thế và xác nhận cấu hình JVM sau khi migration.

## 1. Vì sao cần kiểm tra trước khi nâng cấp?

Một ứng dụng chạy được trên JDK cũ chưa chắc chạy được trên JDK 17. Có thể nó đang:

- Import một class nội bộ mà JDK cũ vô tình cho phép truy cập.
- Dùng Reflection để truy cập private member của package JDK không mở.
- Gọi API đã deprecated hoặc đã bị loại bỏ.
- Truyền JVM option chỉ hợp lệ ở một phiên bản trước.
- Phụ thuộc một thư viện cũ tự sử dụng các API trên, dù source ứng dụng không nhắc đến chúng.

Những phụ thuộc này thường ẩn trong thư viện bên thứ ba, plugin build, agent, framework, script Docker hoặc tham số cấu hình môi trường.

### 1.1. Ba nhóm rủi ro

| Nhóm | Ví dụ | Triệu chứng có thể gặp |
|---|---|---|
| Internal API | Dùng class trong package JDK nội bộ | Compile error, `IllegalAccessError`, lỗi liên kết hoặc lỗi Reflection |
| Deprecated / for removal | Gọi API đã đánh dấu deprecated | Compiler warning, runtime warning; có thể cần thay thế trước bản JDK tương lai |
| Removed API / JVM option | Dùng class, module hoặc flag đã bị xóa | `cannot find symbol`, `ClassNotFoundException`, `Unrecognized VM option` |

Không phải mọi warning đều đồng nghĩa ứng dụng sẽ lỗi ngay trên Java 17. Tuy nhiên, warning là tín hiệu để đánh giá rủi ro và lập kế hoạch thay thế.

### 1.2. Kiểm tra cả source, dependency và cách khởi chạy

Một lần audit nên bao gồm:

1. Source code của ứng dụng.
2. Dependency trực tiếp và bắc cầu (transitive).
3. Plugin và annotation processor chạy lúc build.
4. Java agent, native library và framework.
5. Dockerfile, shell script, service definition và cấu hình JVM ở môi trường triển khai.
6. Test, integration test và các profile chỉ chạy ở production.

Chỉ biên dịch source thành công chưa đủ. Một dependency có thể dùng Reflection hoặc tải class động nên vấn đề chỉ xuất hiện ở runtime.

## 2. API nội bộ của JDK là gì?

Java SE định nghĩa các API công khai được hỗ trợ cho ứng dụng. Bên cạnh đó, JDK có nhiều class và package phục vụ triển khai nội bộ của compiler, runtime, networking, security, collections và các thành phần khác.

Các package có tên như `sun.*` hoặc `com.sun.*` thường là dấu hiệu cần kiểm tra, nhưng không nên kết luận chỉ từ prefix. Một số API có tên `com.sun.*` được công bố chính thức trong JDK; hãy xác minh module, tài liệu API và kết quả của `jdeps`.

Ví dụ các loại phụ thuộc không nên dùng trong ứng dụng:

~~~java
import sun.misc.Unsafe;
import sun.reflect.Reflection;
~~~

Các API nội bộ có thể thay đổi giữa các bản JDK, bị đóng gói trong module không export, hoặc bị encapsulate mạnh hơn theo thời gian. Ứng dụng không có bảo đảm tương thích như khi dùng API Java SE công khai.

### 2.1. Internal API và public API khác nhau thế nào?

| Tiêu chí | Java SE public API | JDK internal API |
|---|---|---|
| Hợp đồng | Được đặc tả trong Java SE/JDK API | Phụ thuộc implementation của JDK |
| Tương thích | Có cam kết tương thích theo chính sách Java | Có thể đổi hoặc bị đóng bất cứ lúc nào |
| Module access | Package public được export theo module descriptor | Nhiều package không export cho ứng dụng |
| Khuyến nghị | Dùng trong ứng dụng | Tránh phụ thuộc; tìm API thay thế |

Ví dụ, dùng `java.nio.file.Files` để đọc file là sử dụng API công khai. Dựa vào một class nội bộ để truy cập cấu trúc file descriptor của HotSpot là phụ thuộc vào implementation.

### 2.2. Không phải mọi API có tên sun đều có cùng trạng thái

Một ví dụ cần hiểu đúng là `sun.misc.Unsafe`. Trong HotSpot/OpenJDK 17, class này vẫn tồn tại trong module `jdk.unsupported` và được duy trì như một API nội bộ đặc biệt để hỗ trợ một số thư viện nền tảng. Điều đó không biến nó thành API Java SE ổn định hoặc khuyến nghị cho mã ứng dụng mới.

Nếu một thư viện vẫn dùng `Unsafe`, cần kiểm tra phiên bản thư viện và hướng migration do chính thư viện cung cấp. Không tự thay bằng Reflection sâu vào JDK internals.

## 3. Strong encapsulation trong Java 17

Java Platform Module System (JPMS) tạo ranh giới module và package. Module có thể export package cho module khác; package không export được xem là implementation detail đối với truy cập thông thường.

JEP 403, được áp dụng trong JDK 17, hoàn tất việc strong encapsulation của các internal elements trong JDK. Một số API nội bộ đặc biệt vẫn có ngoại lệ tương thích, nhưng ứng dụng không nên dựa vào ngoại lệ đó làm hợp đồng lâu dài.

Hệ quả khi nâng cấp:

- Truy cập mã nguồn đến package JDK không export có thể bị compiler từ chối.
- Truy cập bytecode đã biên dịch có thể thất bại với lỗi truy cập liên kết.
- Reflection sâu vào package không mở có thể thất bại khi gọi `setAccessible(true)` hoặc `trySetAccessible()`.
- Cấu hình cũ từng mở rộng quyền truy cập trong các JDK trước có thể không còn tác dụng.

### 3.1. --illegal-access không còn là cách khắc phục trên JDK 17

Trong các JDK trước 17, option `--illegal-access` từng hỗ trợ chế độ tương thích cho một số truy cập phản chiếu bất hợp pháp vào package JDK. Từ JDK 17, option này đã trở nên obsolete và không còn mở các package theo cơ chế cũ; JVM phát cảnh báo rằng option bị bỏ qua.

Ví dụ cấu hình cũ:

~~~bash
java --illegal-access=permit -jar app.jar
~~~

Không nên giữ option này với kỳ vọng nó sẽ khôi phục quyền truy cập cũ trên Java 17. Hãy xóa nó khỏi script sau khi xác nhận ứng dụng không còn phụ thuộc vào cơ chế cũ, rồi thay thế truy cập nội bộ bằng API được hỗ trợ.

Nếu cần một ngoại lệ migration tạm thời, dùng `--add-exports` hoặc `--add-opens` với package và module đích cụ thể, như phần tiếp theo. Đây là quyền truy cập được cấp rõ ràng; chúng không biến internal API thành public API ổn định.

## 4. Phân biệt --add-exports và --add-opens

Hai option này đều điều chỉnh ranh giới module, nhưng giải quyết hai nhu cầu khác nhau.

| Option | Mục đích | Trường hợp sử dụng |
|---|---|---|
| `--add-exports` | Export package cho module đích | Mã cần tham chiếu public type/member trong package chưa được export |
| `--add-opens` | Mở package cho deep reflection lúc runtime | Framework cần truy cập private field/method bằng Reflection |
| `--add-reads` | Thêm quan hệ readability giữa module | Module cần đọc module khác nhưng graph hiện tại chưa khai báo quan hệ phù hợp |

### 4.1. Cú pháp --add-exports

~~~bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED -jar app.jar
~~~

Cú pháp tổng quát:

~~~text
--add-exports source-module/package=target-module
~~~

Trong ví dụ:

- `java.base` là module nguồn.
- `sun.nio.ch` là package cần export.
- `ALL-UNNAMED` chỉ các class thuộc unnamed module, thường là ứng dụng chạy trên classpath.

`--add-exports` có thể được dùng với `javac` khi cần biên dịch mã tham chiếu public type trong package đó, và với `java` khi chạy ứng dụng cần quyền truy cập tương ứng.

Chỉ export đúng package và đúng module tiêu thụ. Không dùng wildcard để mở rộng hàng loạt package nội bộ.

### 4.2. Cú pháp --add-opens

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

Cú pháp tổng quát:

~~~text
--add-opens source-module/package=target-module
~~~

Option này phục vụ Reflection runtime. Nó cho phép module đích thực hiện deep reflection trên package được mở, theo các quy tắc của JPMS.

`--add-opens` không thay thế `--add-exports` để biên dịch mã nguồn import public type. Ngược lại, `--add-exports` cũng không tự cấp quyền deep reflection vào private member.

### 4.3. ALL-UNNAMED không phải lựa chọn mặc định cho mọi trường hợp

`ALL-UNNAMED` cấp quyền cho tất cả code nằm trong unnamed module. Nếu ứng dụng có module name rõ ràng, hãy chỉ định module đích cụ thể:

~~~bash
java --add-opens java.base/java.lang=com.example.application -m com.example.application/com.example.Main
~~~

Càng mở rộng module đích, phạm vi quyền càng lớn. Ưu tiên sửa dependency để nó dùng API được hỗ trợ; nếu chưa thể, chỉ mở package cần thiết và có kế hoạch loại bỏ ngoại lệ.

### 4.4. Các option này là giải pháp tương thích có kiểm soát

Dùng `--add-exports` hoặc `--add-opens` có thể giúp một dependency cũ tiếp tục hoạt động trong giai đoạn chuyển đổi. Nhưng chúng có các giới hạn:

- Chỉ áp dụng cho package và module được nêu.
- Không bảo đảm API nội bộ tồn tại trong JDK tương lai.
- Không sửa được API đã bị xóa.
- Không giải quyết lỗi logic do dependency không tương thích.
- Có thể làm giảm mức encapsulation và tăng rủi ro bảo trì.

Không thêm option chỉ vì thấy một exception có chữ module. Trước tiên cần xác định module nguồn, package, module caller và loại thao tác đang bị từ chối.

## 5. Phát hiện internal API bằng jdeps

`jdeps` là công cụ phân tích dependency của class file và JAR. Trên JDK 17, tùy chọn `--jdk-internals` giúp phát hiện dependency vào JDK internal APIs.

### 5.1. Quét một JAR

~~~bash
jdeps --jdk-internals app.jar
~~~

Có thể quét nhiều artifact hoặc thư mục class đã build:

~~~bash
jdeps --jdk-internals build/libs/
~~~

Với multi-release JAR, chỉ định phiên bản cần phân tích:

~~~bash
jdeps --jdk-internals --multi-release 17 app.jar
~~~

Kết quả có thể cho biết:

- Class ứng dụng nào phụ thuộc vào internal API.
- Internal API nào đang được tham chiếu.
- Module chứa API đó.
- Gợi ý migration nếu JDK cung cấp thay thế được nhận diện.

### 5.2. Phân tích dependency bắc cầu

Nếu ứng dụng không trực tiếp import internal API, dependency bên thứ ba vẫn có thể sử dụng nó. Hãy quét các JAR trong dependency graph, không chỉ JAR do nhóm ứng dụng tự build.

Ví dụ, sau khi lấy danh sách dependency đã resolve:

~~~bash
jdeps --jdk-internals library-a.jar
jdeps --jdk-internals library-b.jar
~~~

Nếu kết quả chỉ ra một thư viện bên thứ ba:

1. Xác định phiên bản đang dùng.
2. Đọc release note và migration guide của thư viện.
3. Nâng lên phiên bản hỗ trợ JDK 17 nếu có.
4. Nếu chưa có bản sửa, đánh giá thay thư viện hoặc cô lập ngoại lệ module access.
5. Thêm test chạy trên JDK 17 để xác nhận đường chức năng liên quan.

### 5.3. Giới hạn của jdeps

`jdeps` phân tích dependency có thể suy ra từ bytecode. Nó không đảm bảo phát hiện mọi truy cập động:

- Tên class được ghép thành chuỗi rồi nạp bằng `Class.forName`.
- Reflection dựa trên tên package/member.
- Native code gọi vào JVM qua JNI.
- Dependency được tải ở runtime từ plugin hoặc thư mục ngoài.
- Mã được sinh hoặc tải sau khi ứng dụng khởi động.

Vì vậy, `jdeps` là một phần của audit, không phải bằng chứng tuyệt đối rằng ứng dụng không còn phụ thuộc internal API.

## 6. Phát hiện API deprecated và API for removal

API được đánh dấu `@Deprecated` vẫn có thể còn hoạt động. Annotation cho biết API không còn được khuyến nghị; nó không tự động có nghĩa API đã bị xóa.

Từ Java 9, annotation `@Deprecated` có thêm hai thuộc tính:

- `since`: phiên bản bắt đầu deprecated.
- `forRemoval`: cho biết API đã được đánh dấu dự kiến loại bỏ hay chưa.

Ví dụ:

~~~java
@Deprecated(since = "17", forRemoval = true)
public void oldOperation() {
}
~~~

Phân biệt:

| Trạng thái | Ý nghĩa | Cách xử lý |
|---|---|---|
| Deprecated, forRemoval = false | Không khuyến nghị sử dụng; chưa tuyên bố kế hoạch loại bỏ | Tìm API thay thế và lập kế hoạch cập nhật |
| Deprecated, forRemoval = true | API được đánh dấu dự kiến loại bỏ | Ưu tiên migration trước khi nâng cấp JDK tiếp theo |
| Removed | API đã bị xóa khỏi JDK | Thay thế dependency/API; không thể khắc phục chỉ bằng flag mở module |

### 6.1. Compiler warning khi dùng deprecated API

Dùng `javac` với lint:

~~~bash
javac --release 17 -Xlint:deprecation -d out src/example/*.java
~~~

Compiler sẽ báo vị trí sử dụng API deprecated. Với API được đánh dấu for removal, có thể bật thêm:

~~~bash
javac --release 17 -Xlint:deprecation -Xlint:removal -d out src/example/*.java
~~~

Có thể dùng `-Werror` trong build để chuyển warning thành lỗi khi dự án đã sẵn sàng áp dụng chính sách nghiêm ngặt:

~~~bash
javac --release 17 -Xlint:deprecation -Xlint:removal -Werror -d out src/example/*.java
~~~

Không nên bật `-Werror` một cách đột ngột trên codebase lớn có nhiều warning chưa phân loại. Trước tiên hãy thu thập warning, xử lý warning thuộc phạm vi dự án và sau đó đưa quy tắc vào CI.

### 6.2. Quét bytecode bằng jdeprscan

`jdeprscan` phân tích class file, JAR hoặc thư mục để phát hiện việc sử dụng API deprecated trong Java platform.

Quét một JAR theo API Java 17:

~~~bash
jdeprscan --release 17 app.jar
~~~

Chỉ tập trung API đã được đánh dấu for removal:

~~~bash
jdeprscan --release 17 --for-removal app.jar
~~~

Liệt kê deprecated API của release được chọn:

~~~bash
jdeprscan --release 17 --list
~~~

Quét thư mục chứa các class đã biên dịch:

~~~bash
jdeprscan --release 17 build/classes/
~~~

`jdeprscan` hữu ích khi source không đầy đủ hoặc cần rà soát thư viện đã biên dịch. Nó không thay thế compiler warning: source compilation có thể cho biết vị trí và ngữ cảnh sửa rõ hơn.

### 6.3. Kiểm tra annotation và Javadoc

Khi gặp warning, hãy xem Javadoc của API trên đúng phiên bản JDK mục tiêu:

- API được deprecated từ phiên bản nào?
- `forRemoval` có phải `true` không?
- Tài liệu có chỉ ra API thay thế không?
- Thay thế có cùng hành vi và cùng giới hạn bảo mật không?
- API thay thế có mặt trong Java 17 hay chỉ trong JDK mới hơn?

Không chọn API chỉ vì tên gần giống. Cần đọc hợp đồng, ngoại lệ, thread-safety, security behavior và điều kiện tương thích.

## 7. Ví dụ API deprecated hoặc for removal trong JDK 17

Một số API vẫn có mặt trong Java 17 nhưng không nên được đưa vào mã mới.

### 7.1. Security Manager

JEP 411 đánh dấu Security Manager để loại bỏ trong tương lai. Trong Java 17, các API như `System.setSecurityManager` và `System.getSecurityManager` vẫn tồn tại nhưng bị deprecated for removal.

Mã cũ có thể có:

~~~java
System.setSecurityManager(new SecurityManager());
~~~

Trên JDK 17, việc sử dụng Security Manager phát sinh warning liên quan đến trạng thái deprecated for removal. Việc đặt Security Manager cũng chịu các hạn chế của phiên bản JDK và có thể không còn phù hợp với thiết kế ứng dụng hiện đại.

Hướng xử lý:

- Xác định chính sách bảo mật mà ứng dụng từng dựa vào Security Manager.
- Chuyển kiểm soát quyền sang cơ chế bảo mật ở OS/container, process isolation, service identity, filesystem permission và network policy phù hợp.
- Nếu thư viện bên thứ ba tự cài Security Manager, nâng cấp hoặc thay thư viện.
- Không xóa cơ chế bảo vệ cũ trước khi xác định yêu cầu bảo mật mà nó đang đáp ứng.

Không coi việc bỏ Security Manager là đồng nghĩa có thể bỏ mọi biện pháp sandbox hoặc authorization. Thay thế cần dựa trên threat model của ứng dụng.

### 7.2. Applet API

JEP 398 deprecated Applet API for removal trong JDK 17. Applet là mô hình triển khai ứng dụng Java trong trình duyệt đã lỗi thời; các trình duyệt hiện đại không còn hỗ trợ plugin Java theo mô hình đó.

Nếu source còn tham chiếu `java.applet.Applet` hoặc `AppletContext`:

- Xác định chức năng người dùng thực sự cần.
- Chuyển chức năng sang web application, desktop application hoặc service phù hợp.
- Tách logic Java có thể tái sử dụng khỏi lifecycle và API đặc thù Applet.
- Không cố phục hồi plugin trình duyệt cũ bằng JVM option.

Trong Java 17, API có thể vẫn hiện diện nhưng đã được đánh dấu deprecated for removal. Điều này khác với một API đã bị xóa hoàn toàn.

### 7.3. Phân biệt deprecated với removed

Một API deprecated for removal vẫn có thể biên dịch trên Java 17 nếu API còn tồn tại. Một API đã removed sẽ không còn symbol để compiler liên kết.

Ví dụ, `Object.finalize()` là API legacy và được deprecated for removal từ JDK 18, không phải một API đã bị xóa trong Java 17. Khi target Java 17, cần kiểm tra chính xác trạng thái theo release mục tiêu thay vì áp dụng thông tin từ JDK mới hơn ngược về JDK 17.

## 8. Những API và thành phần đã bị loại bỏ trước Java 17

Khi nâng cấp lên JDK 17 từ các bản rất cũ, một số thành phần có thể đã biến mất từ JDK 11, 14 hoặc 15. Đây là lý do cần kiểm tra toàn bộ lịch sử phiên bản mà ứng dụng đã đi qua.

### 8.1. Java EE và CORBA modules

Các module Java EE và CORBA từng được đóng gói trong JDK đã bị loại bỏ khỏi JDK từ Java 11. Ví dụ các module:

- `java.xml.bind` (JAXB).
- `java.xml.ws` (JAX-WS).
- `java.xml.ws.annotation`.
- `java.activation`.
- `java.corba`.
- `java.transaction`.

Nếu ứng dụng dựa vào các package như `javax.xml.bind` vì trước đây chúng có sẵn trong JDK, compile trên Java 17 có thể báo thiếu package.

Cách xử lý phụ thuộc vào nhu cầu:

1. Nếu ứng dụng vẫn cần JAXB/JAX-WS, thêm implementation và API dependency được duy trì, tương thích với Java 17.
2. Xác định hệ sinh thái package namespace mà ứng dụng đang dùng: `javax.*` hay `jakarta.*`.
3. Không thay hàng loạt tên package bằng thao tác find/replace; phiên bản JAXB/Jakarta khác nhau có namespace và tương thích binary khác nhau.
4. Nếu chức năng không còn cần thiết, loại bỏ dependency và code liên quan.

Các module đã bị xóa không thể khôi phục bằng `--add-modules`. Phải cung cấp thư viện bên ngoài hoặc thay thế chức năng.

### 8.2. Nashorn JavaScript Engine

Nashorn và công cụ `jjs` đã bị loại bỏ trong JDK 15. Java 17 vẫn có package `javax.script`, nhưng không còn đảm bảo một JavaScript engine mặc định có sẵn trong JDK.

Mã cũ:

~~~java
ScriptEngine engine =
        new ScriptEngineManager().getEngineByName("JavaScript");
~~~

Có thể nhận về `null` nếu không có JavaScript engine phù hợp trên classpath/module path.

Nếu ứng dụng thực sự cần chạy JavaScript:

- Chọn một JavaScript engine được duy trì độc lập với JDK.
- Khai báo dependency engine tường minh.
- Kiểm tra khả năng tương thích JSR 223 nếu vẫn dùng `ScriptEngineManager`.
- Đánh giá sandbox, quyền truy cập host và giới hạn tài nguyên của engine.
- Viết test cho script, interop và behavior thực tế.

Nếu chỉ dùng Nashorn để xử lý một số chuỗi hoặc JSON, hãy cân nhắc API Java hoặc thư viện chuyên dụng thay vì kéo một engine scripting không cần thiết.

### 8.3. Pack200

Pack200 API và công cụ liên quan đã bị loại bỏ khỏi JDK 14. Nếu build hoặc deployment script còn gọi `pack200`/`unpack200`, lệnh có thể không còn tồn tại trên Java 17.

Hãy thay pipeline đóng gói bằng định dạng và công cụ artifact được hỗ trợ, thường là JAR thông thường cùng cơ chế nén/transfer hiện hành. Không giả định một option JVM có thể phục hồi command-line tool đã bị xóa.

### 8.4. CMS Garbage Collector

Concurrent Mark Sweep (CMS) collector đã bị loại bỏ khỏi HotSpot từ JDK 14. Cấu hình cũ:

~~~bash
java -XX:+UseConcMarkSweepGC -jar app.jar
~~~

sẽ không còn là cấu hình hợp lệ trên Java 17 và có thể dừng ngay khi JVM khởi động với thông báo option không được nhận diện.

Hãy chọn collector còn được hỗ trợ dựa trên workload và mục tiêu độ trễ/throughput. Trên Java 17, các lựa chọn phổ biến gồm G1 (mặc định trên nhiều cấu hình server), Parallel GC, ZGC và Shenandoah tùy bản phân phối JDK. Kiểm tra collector có sẵn trong JDK vendor và cấu hình triển khai cụ thể trước khi chọn.

Không thay CMS bằng một collector khác chỉ bằng cách đổi tên flag; hãy đo throughput, pause time, allocation rate và footprint trên workload đại diện.

## 9. Phát hiện JVM option cũ hoặc không hợp lệ

Các JVM option có thể nằm trong nhiều nơi:

- Lệnh `java` trong shell script.
- `JAVA_TOOL_OPTIONS` hoặc `JDK_JAVA_OPTIONS`.
- Docker `ENTRYPOINT`/`CMD`.
- Kubernetes manifest, Helm values hoặc service definition.
- Build tool, test task, application server hoặc monitoring agent.
- Script chạy migration, batch job và công cụ nội bộ.

Một flag bị loại bỏ có thể khiến tiến trình không khởi động. Một flag obsolete có thể được nhận diện nhưng bị cảnh báo hoặc không còn mang ý nghĩa như cấu hình cũ mong đợi.

### 9.1. Nhận diện lỗi Unrecognized VM option

Ví dụ:

~~~text
Unrecognized VM option 'UseConcMarkSweepGC'
Error: Could not create the Java Virtual Machine.
Error: A fatal exception has occurred. Program will exit.
~~~

Điều này thường xảy ra trước khi ứng dụng chạy. Cần kiểm tra flag trên đúng binary Java được dùng ở môi trường đó, vì máy developer, CI và production có thể đang chạy JDK khác nhau.

Xác nhận phiên bản:

~~~bash
java -version
javac -version
where java
~~~

Trên Linux/macOS, dùng `which java` thay cho `where java`. Khi có nhiều JDK, kiểm tra đường dẫn executable thật thay vì chỉ dựa vào biến môi trường hoặc tên lệnh.

### 9.2. Xem JVM flags được JVM nhận diện

Có thể in các flag và giá trị cuối cùng:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Lọc theo tên flag trên Linux/macOS:

~~~bash
java -XX:+PrintFlagsFinal -version 2>&1 | grep -i metaspace
~~~

Trên Windows PowerShell:

~~~powershell
java -XX:+PrintFlagsFinal -version 2>&1 | Select-String -Pattern 'Metaspace'
~~~

Kết quả hữu ích để xem flag tồn tại và giá trị đang áp dụng. Tuy nhiên, việc một flag xuất hiện trong danh sách không tự chứng minh rằng flag đó còn phù hợp hoặc có hiệu quả như mong đợi. Đọc mô tả và warning của đúng JDK vendor.

### 9.3. Phân biệt flag removed, obsolete và deprecated

| Trạng thái | Dấu hiệu | Cách xử lý |
|---|---|---|
| Removed / unrecognized | JVM báo `Unrecognized VM option` | Xóa và thay bằng cấu hình còn hỗ trợ |
| Obsolete / ignored | JVM cảnh báo option obsolete hoặc bị bỏ qua | Xóa khỏi cấu hình; không dựa vào tác dụng cũ |
| Deprecated | JVM cảnh báo flag deprecated nhưng có thể vẫn nhận | Tìm flag hoặc cơ chế thay thế; lên kế hoạch loại bỏ |
| Supported | JVM nhận và áp dụng flag | Vẫn cần xác minh flag phù hợp workload và vendor |

Một số option có thể thay đổi trạng thái qua các bản JDK. Không sao chép danh sách flag “còn dùng được” từ một phiên bản JDK khác mà không kiểm tra runtime mục tiêu.

### 9.4. Một số JVM option cũ thường gặp

| Option cũ | Trạng thái/liên quan trên Java 17 | Hướng xử lý |
|---|---|---|
| `-XX:+UseConcMarkSweepGC` | CMS đã bị loại bỏ từ JDK 14 | Chọn collector còn hỗ trợ và benchmark lại |
| `-XX:+UseParNewGC` | Collector liên quan CMS đã bị loại bỏ | Bỏ cấu hình cũ; kiểm tra cấu hình GC còn lại |
| `-XX:PermSize` / `-XX:MaxPermSize` | PermGen đã bị loại bỏ từ JDK 8 | Bỏ flag PermGen; nếu cần quản lý metadata, xem `-XX:MaxMetaspaceSize` |
| `--illegal-access` | Obsolete và bị bỏ qua từ JDK 17 | Bỏ option; sửa dependency hoặc dùng quyền module có mục tiêu trong giai đoạn chuyển tiếp |
| `-XX:+UseBiasedLocking` | Tính năng biased locking bị disable mặc định và deprecated từ JDK 15 | Không dựa vào flag này để tuning; đo workload và dùng cấu hình còn được hỗ trợ |
| `-XX:+PrintGCDetails` / `-XX:+PrintGCDateStamps` | Cách ghi GC log kiểu cũ; Unified Logging là cơ chế hiện hành | Chuyển sang `-Xlog:gc*` |

Bảng này nêu một số trường hợp phổ biến, không phải danh sách toàn bộ JVM option. Trạng thái flag phụ thuộc phiên bản JDK và nhà cung cấp; kiểm tra trực tiếp trên runtime đích.

### 9.5. Thay GC logging cũ bằng Unified Logging

Các script cũ có thể chứa:

~~~bash
java -XX:+PrintGCDetails -XX:+PrintGCDateStamps -Xloggc:gc.log -jar app.jar
~~~

Java 17 có Unified JVM Logging. Ví dụ cấu hình hiện hành:

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
~~~

Có thể giới hạn kích thước và số file log luân phiên:

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M -jar app.jar
~~~

Đọc cú pháp `-Xlog` theo tài liệu JDK 17 và điều chỉnh rotation theo dung lượng log của môi trường. Không giữ cả nhóm flag cũ và mới nếu chúng ghi log trùng hoặc tạo cấu hình khó hiểu.

### 9.6. Cẩn thận với IgnoreUnrecognizedVMOptions

JVM có option `-XX:+IgnoreUnrecognizedVMOptions` để bỏ qua một số option không nhận diện. Đây không phải cách sửa cấu hình migration.

Nếu dùng nó trong production, một flag quan trọng có thể bị bỏ qua mà tiến trình vẫn khởi động. Ví dụ, heap limit hoặc collector dự kiến có thể không được áp dụng.

Trong giai đoạn migration:

- Không thêm option này chỉ để che lỗi flag.
- Nếu một launcher hiện có đã dùng nó, xác định lý do và kiểm tra các flag được truyền.
- Xóa các flag không hợp lệ, xác nhận JVM khởi động với cấu hình mong muốn.
- Chỉ giữ cơ chế bỏ qua nếu có yêu cầu tương thích cụ thể, được kiểm soát và có kiểm thử.

## 10. Quy trình audit dự án khi nâng cấp lên Java 17

Một quy trình có thể lặp lại giúp phát hiện vấn đề sớm và xác định đúng chủ sở hữu dependency.

### Bước 1: Xác nhận JDK thực tế

Chạy trong môi trường build và môi trường chạy:

~~~bash
java -version
javac -version
jdeps --version
jdeprscan --version
~~~

Nếu dự án dùng toolchain, kiểm tra toolchain được build tool chọn. Không giả định lệnh `java` trong terminal chính là JDK mà Gradle/Maven dùng.

### Bước 2: Quét internal API

Trên artifact đã compile:

~~~bash
jdeps --jdk-internals --multi-release 17 app.jar
~~~

Lặp lại cho dependency quan trọng, đặc biệt framework, bytecode library, ORM, serialization, agent và thư viện networking.

Ghi nhận:

- Artifact và phiên bản.
- Class đang phụ thuộc internal API.
- Package nội bộ bị dùng.
- Có phiên bản thay thế hỗ trợ Java 17 hay không.
- Cần thay dependency hay chỉ sửa source ứng dụng.

### Bước 3: Quét deprecated API

~~~bash
jdeprscan --release 17 app.jar
jdeprscan --release 17 --for-removal app.jar
~~~

Kết hợp compile source với:

~~~bash
javac --release 17 -Xlint:deprecation -Xlint:removal ...
~~~

Nếu build tool biên dịch source, cấu hình tương đương trong compiler options của build tool thay vì chỉ chạy một lệnh javac riêng.

### Bước 4: Tìm JVM option trong toàn bộ cấu hình triển khai

Tìm các từ khóa trong repository và deployment config:

- `--illegal-access`
- `--add-exports`, `--add-opens`
- `UseConcMarkSweepGC`, `UseParNewGC`
- `PermSize`, `MaxPermSize`
- `PrintGCDetails`, `PrintGCDateStamps`, `Xloggc`
- `UseBiasedLocking`
- `IgnoreUnrecognizedVMOptions`

Sau đó kiểm tra biến môi trường và tham số khởi chạy được inject ở CI, container, orchestrator và service manager.

Đừng chỉ xóa option dựa trên kết quả tìm kiếm văn bản. Có thể cùng tên flag xuất hiện trong tài liệu hoặc script test không còn dùng. Xác định đường chạy thực tế trước khi chỉnh.

### Bước 5: Kiểm tra dependency và plugin

Xem dependency graph của ứng dụng, processor và plugin. Một processor hoặc plugin chạy trong build cũng có thể phụ thuộc JDK internal API, dù artifact ứng dụng không dùng nó khi runtime.

Với Gradle, có thể xem dependency configuration cụ thể:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration annotationProcessor
~~~

Với Maven, xem dependency tree và plugin configuration:

~~~bash
mvn dependency:tree
mvn help:effective-pom
~~~

Nâng cấp processor/plugin theo ma trận hỗ trợ Java 17 của nhà cung cấp.

### Bước 6: Chạy test trên JDK 17

Tối thiểu cần chạy:

- Compile toàn bộ source set.
- Unit test và integration test.
- Test đóng gói và khởi động artifact cuối cùng.
- Các chức năng dùng Reflection, serialization, scripting, XML binding hoặc native library.
- Startup/shutdown và các job chỉ chạy theo lịch.
- Smoke test trong cùng container/base image với production.

Một ứng dụng có thể compile thành công nhưng chỉ thất bại khi framework khởi tạo hoặc khi một endpoint hiếm được gọi.

### Bước 7: Xác nhận log và cấu hình JVM

Kiểm tra:

- Không còn `Unrecognized VM option`.
- Không có warning về option obsolete/ignored ngoài những trường hợp đã được chấp nhận có chủ đích.
- Không còn lỗi `IllegalAccessError`, `InaccessibleObjectException` hoặc `NoClassDefFoundError` liên quan migration.
- Các flag như heap size, GC và logging thực sự có hiệu lực.
- Startup command trong container giống cấu hình đã kiểm thử.


## 11. Cách xử lý khi dependency cần quyền truy cập nội bộ

Nếu audit phát hiện một thư viện cũ cần truy cập package nội bộ, không nên lập tức thêm hàng loạt `--add-opens`.

### 11.1. Ưu tiên theo thứ tự

1. Nâng cấp thư viện lên phiên bản hỗ trợ Java 17.
2. Dùng API công khai của Java SE thay cho internal API.
3. Thay thư viện nếu upstream không còn duy trì.
4. Nếu cần thời gian migration, cấp quyền module tối thiểu cho đúng package và module.
5. Ghi nhận ngoại lệ, owner và thời hạn loại bỏ.

### 11.2. Chọn đúng quyền

| Lỗi / nhu cầu | Cần xem xét |
|---|---|
| Source không truy cập được public type trong package chưa export | `--add-exports` cho compile và runtime nếu cần |
| Framework gọi `setAccessible` trên private member | `--add-opens` cho module framework ở runtime |
| Module chưa đọc module chứa API | `requires` hoặc `--add-reads`, sau đó vẫn kiểm tra export |
| Class hoặc module đã bị xóa | Thay dependency/API; add-exports/open không giúp được |
| JVM flag đã bị xóa | Xóa và thay cấu hình; module option không liên quan |

### 11.3. Không mở toàn bộ java.base

Một cấu hình mở nhiều package nội bộ cho `ALL-UNNAMED` làm suy yếu encapsulation của toàn ứng dụng.

Nếu một framework cụ thể cần package cụ thể, chỉ cấp quyền cho module đó:

~~~bash
java --add-opens java.base/java.lang=com.example.framework -jar app.jar
~~~

Tên module đích phải là module thực sự chứa code cần quyền. Nếu framework chạy trong unnamed module, có thể cần `ALL-UNNAMED`, nhưng phải hiểu rằng quyền được cấp cho toàn bộ unnamed modules trong tiến trình.

### 11.4. Ghi nhận ngoại lệ module access

Mỗi ngoại lệ nên có thông tin:

| Trường | Ví dụ nội dung |
|---|---|
| Package nguồn | `java.base/java.lang` |
| Module đích | Module framework hoặc `ALL-UNNAMED` |
| Option | `--add-opens` hoặc `--add-exports` |
| Dependency gây ra | Tên artifact và phiên bản |
| Lý do | Framework cần truy cập member cụ thể |
| Kế hoạch | Phiên bản thay thế hoặc issue migration |
| Điều kiện loại bỏ | Khi dependency không còn cần quyền |

Cách ghi nhận này giúp đội vận hành biết tại sao option tồn tại và tránh mang ngoại lệ cũ sang những hệ thống không còn cần nó.

## 12. Cấu hình build để kiểm tra Java 17 thường xuyên

### 12.1. Gradle toolchain và compiler lint

Ví dụ Groovy DSL:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.compilerArgs += [
        '-Xlint:deprecation',
        '-Xlint:removal'
    ]
}
~~~

Toolchain giúp chọn JDK phù hợp cho task compile. `options.release = 17` giới hạn API và language level theo Java 17. Lint khiến warning về deprecated/removal xuất hiện trong build log.

Nếu muốn warning trở thành lỗi sau khi đã dọn sạch warning, có thể thêm `-Werror` theo chính sách của dự án.

### 12.2. Maven Compiler Plugin

Ví dụ cấu hình:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
                <showWarnings>true</showWarnings>
                <compilerArgs>
                    <arg>-Xlint:deprecation</arg>
                    <arg>-Xlint:removal</arg>
                </compilerArgs>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Chọn phiên bản Maven Compiler Plugin tương thích với Maven/JDK được dùng trong build. Ví dụ trên là cấu hình minh họa cho Java 17; dự án có thể dùng phiên bản plugin khác đã được quản lý tập trung.

### 12.3. Đưa scan vào CI

Một pipeline có thể chạy các bước sau trên artifact được build:

~~~bash
jdeps --jdk-internals --multi-release 17 build/libs/app.jar
jdeprscan --release 17 build/libs/app.jar
jdeprscan --release 17 --for-removal build/libs/app.jar
~~~

Có thể lưu kết quả scan như build artifact và so sánh giữa các lần release. Khi dự án đã xử lý hết kết quả cần thiết, có thể đặt tiêu chí CI để không cho thêm internal API hoặc API for removal mới.

Đừng coi mọi kết quả scan của dependency bên thứ ba là lỗi do source ứng dụng. Hãy phân loại theo owner và theo dõi nâng cấp dependency tương ứng.



## 13. Một số hướng thay thế internal API thường gặp

Không có một thay thế chung cho mọi internal API. Hãy xác định hành vi mà code cần rồi chọn API công khai phù hợp.

| API nội bộ cũ | Nhu cầu thường gặp | Hướng thay thế công khai |
|---|---|---|
| `sun.misc.BASE64Encoder` / `BASE64Decoder` | Mã hóa và giải mã Base64 | `java.util.Base64` |
| `sun.reflect.Reflection.getCallerClass` | Xác định caller trong stack | `StackWalker` |
| `sun.misc.Cleaner` | Gắn hành động cleanup với object | `java.lang.ref.Cleaner` |
| Một số thao tác atomic qua `sun.misc.Unsafe` | Truy cập field và cập nhật atomic | `VarHandle`, `AtomicInteger`, `AtomicLong`, `AtomicReference` tùy trường hợp |
| Truy cập file qua class nội bộ | Đọc, ghi và thao tác file | `java.nio.file.Files`, `Path`, `FileChannel` |

Ví dụ thay Base64:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

String encoded = Base64.getEncoder()
        .encodeToString("Java 17".getBytes(StandardCharsets.UTF_8));

byte[] decoded = Base64.getDecoder().decode(encoded);
~~~

Ví dụ thay caller inspection bằng StackWalker:

~~~java
StackWalker walker = StackWalker.getInstance();

String caller = walker.walk(frames -> frames
        .skip(1)
        .findFirst()
        .map(StackWalker.StackFrame::getClassName)
        .orElse("<unknown>"));
~~~

Ví dụ dùng VarHandle cho một field:

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
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public int increment() {
        return (int) VALUE.getAndAdd(this, 1) + 1;
    }
}
~~~

Các ví dụ minh họa hướng thay thế, không phải lúc nào cũng tương đương hoàn toàn với hành vi internal API cũ. Đặc biệt với `Unsafe`, cần đối chiếu memory ordering, alignment, atomicity và lifecycle trước khi thay thế.

## 14. Đọc lỗi runtime để xác định loại vấn đề

Các exception sau có thể xuất hiện khi nâng cấp:

| Lỗi | Ý nghĩa thường gặp | Hướng điều tra |
|---|---|---|
| `IllegalAccessError` | Bytecode cố truy cập kiểu/thành viên không được phép | Kiểm tra exports, module graph và dependency |
| `InaccessibleObjectException` | Reflection không thể mở quyền truy cập sâu | Kiểm tra package có được opens cho caller không |
| `ClassNotFoundException` | Class không tìm thấy khi tải động | Kiểm tra dependency/runtime classpath và API đã bị xóa |
| `NoClassDefFoundError` | JVM không thể định nghĩa hoặc liên kết class cần thiết | Kiểm tra dependency thiếu, class initialization và thư viện không tương thích |
| `NoSuchMethodError` | Bytecode gọi method không có trong phiên bản class đang chạy | Kiểm tra version conflict và binary compatibility |
| `Unrecognized VM option` | JVM không nhận flag được truyền | Kiểm tra phiên bản JVM và loại bỏ/thay flag |
| `NoSuchFieldError` | Bytecode tham chiếu field không tồn tại trong runtime class | Kiểm tra dependency version mismatch |

Không kết luận mọi lỗi trên đều do Java 17. Ví dụ `NoSuchMethodError` thường do hai phiên bản thư viện không tương thích cùng xuất hiện trong runtime classpath. Hãy đọc stack trace, class loader và nguồn dependency trước khi chỉnh JVM options.

## 15. Checklist migration cho một lần phát hành

Có thể dùng danh sách dưới đây để theo dõi công việc nâng cấp:

- [ ] Build tool và runtime thực sự dùng JDK 17.
- [ ] Source compile với `--release 17`.
- [ ] Đã chạy `jdeps --jdk-internals` trên artifact ứng dụng và dependency quan trọng.
- [ ] Đã chạy `jdeprscan --release 17` và `--for-removal`.
- [ ] Đã xử lý warning từ `-Xlint:deprecation` và `-Xlint:removal`.
- [ ] Đã rà soát module Java EE/CORBA cũ, Nashorn, Pack200 và CMS nếu dự án từng sử dụng.
- [ ] Đã tìm JVM options trong script, container, CI và biến môi trường.
- [ ] Đã xóa `--illegal-access` khỏi cấu hình Java 17.
- [ ] Mọi `--add-exports`/`--add-opens` còn lại đều có package, module đích, owner và lý do cụ thể.
- [ ] Không còn `Unrecognized VM option` khi chạy đúng lệnh production.
- [ ] Đã chạy unit test, integration test, startup/shutdown và smoke test trên JDK 17.
- [ ] Đã kiểm tra dependency runtime, plugin, agent và annotation processor.
- [ ] Đã lưu lại kết quả scan và các ngoại lệ còn tồn tại để theo dõi ở release tiếp theo.

Checklist này là công cụ theo dõi migration. Các mục cần thiết tùy kiến trúc ứng dụng; không phải dự án nào cũng sử dụng scripting engine, Java EE modules, native library hoặc module path.

## 16. Bài tập thực hành

### Bài 1: Phát hiện internal API

Một JAR được build trên JDK cũ. Viết lệnh kiểm tra dependency vào JDK internal APIs khi chạy trên Java 17.

**Đáp án:**

~~~bash
jdeps --jdk-internals --multi-release 17 app.jar
~~~

### Bài 2: Quét API for removal

Viết lệnh tìm API deprecated for removal trong artifact.

**Đáp án:**

~~~bash
jdeprscan --release 17 --for-removal app.jar
~~~

### Bài 3: Phân biệt exports và opens

Một framework dùng Reflection để đọc private field trong package của ứng dụng. Nên xem xét directive nào?

**Đáp án:** `opens` package cho module framework hoặc option `--add-opens` ở runtime trong giai đoạn migration. `exports` chỉ cho phép truy cập API công khai theo quy tắc access modifier, không tự cấp deep reflection.

### Bài 4: Xử lý --illegal-access

Một script Java 17 vẫn chạy với `--illegal-access=permit`. Có nên giữ option này để tương thích?

**Đáp án:** Không. Từ Java 17, option đã obsolete và bị bỏ qua. Xác định dependency gây truy cập nội bộ, nâng cấp/thay thế nó hoặc cấp quyền module hẹp nếu cần tạm thời.

### Bài 5: CMS flag

Ứng dụng khởi động với `-XX:+UseConcMarkSweepGC` và JVM báo `Unrecognized VM option`.

**Đáp án:** CMS đã bị loại bỏ khỏi HotSpot từ JDK 14. Chọn collector còn được hỗ trợ trong JDK 17 và đo lại workload thay vì cố phục hồi flag.

### Bài 6: API không còn trong JDK

Một ứng dụng Java 8 import `javax.xml.bind.JAXBContext`, nhưng compile trên Java 17 báo thiếu package.

**Đáp án:** JAXB không còn được đóng gói trong JDK từ Java 11. Nếu vẫn cần chức năng, khai báo API và implementation JAXB bên ngoài với version phù hợp Java 17; kiểm tra namespace `javax`/`jakarta` và tương thích của các dependency.

### Bài 7: --add-opens có sửa API đã bị xóa không?

**Đáp án:** Không. `--add-opens` chỉ mở package còn tồn tại cho Reflection runtime. API hoặc module đã bị loại bỏ cần dependency thay thế hoặc thay đổi code.

### Bài 8: Vì sao compile thành công nhưng runtime lỗi?

Một thư viện dùng `Class.forName` với tên class nội bộ được tạo từ cấu hình. `jdeps` không phát hiện tham chiếu tĩnh.

**Đáp án:** `jdeps` phân tích dependency suy ra từ bytecode; truy cập động có thể không xuất hiện như dependency tĩnh. Cần chạy integration test và kiểm tra đường code tải class/Reflection thực tế.

## 17. Ghi nhớ

Khi nâng cấp lên Java 17, hãy phân loại rõ:

1. **Internal API:** phát hiện bằng `jdeps --jdk-internals`; thay bằng API công khai hoặc nâng cấp dependency.
2. **Deprecated API:** phát hiện bằng compiler lint và `jdeprscan`; ưu tiên xử lý API `forRemoval = true`.
3. **Removed API/module:** thay dependency hoặc chức năng; không thể phục hồi bằng module access flag.
4. **JVM option obsolete/removed:** rà soát startup scripts và kiểm tra trực tiếp với JDK 17.
5. **JPMS access exception:** chỉ dùng `--add-exports` hoặc `--add-opens` cho package và module cần thiết, có kế hoạch loại bỏ.

Strong encapsulation của Java 17 giúp phát hiện các phụ thuộc implementation vốn không có hợp đồng ổn định. Một migration tốt cần cập nhật source và dependency, kiểm tra JVM options ở tất cả môi trường, rồi xác nhận bằng test và công cụ scan trên chính JDK mục tiêu.

## 18. Tài liệu tham khảo

- [Oracle Java SE 17 — jdeps](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): phân tích dependency và tùy chọn `--jdk-internals`.
- [Oracle Java SE 17 — jdeprscan](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeprscan.html): quét việc sử dụng API deprecated.
- [Oracle Java SE 17 — javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `--release`, lint và compiler options.
- [Oracle Java SE 17 — java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): JVM options, module access và Unified Logging.
- [Oracle Java SE 17 — JDK Migration Guide](https://docs.oracle.com/en/java/javase/17/migrate/): thay đổi và lưu ý khi chuyển ứng dụng sang JDK 17.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): strong encapsulation trong JDK 17 và trạng thái `--illegal-access`.
- [JEP 411 — Deprecate the Security Manager for Removal](https://openjdk.org/jeps/411): thay đổi trạng thái Security Manager.
- [JEP 398 — Deprecate the Applet API for Removal](https://openjdk.org/jeps/398): trạng thái Applet API trong JDK 17.
- [JEP 363 — Remove the Concurrent Mark Sweep (CMS) Garbage Collector](https://openjdk.org/jeps/363): loại bỏ CMS.
- [JEP 372 — Remove the Nashorn JavaScript Engine](https://openjdk.org/jeps/372): loại bỏ Nashorn.
- [JEP 374 — Disable and Deprecate Biased Locking](https://openjdk.org/jeps/374): trạng thái biased locking từ JDK 15.
- [JEP 320 — Remove the Java EE and CORBA Modules](https://openjdk.org/jeps/320): các module Java EE và CORBA bị loại khỏi JDK 11.
- [JEP 367 — Remove the Pack200 Tools and API](https://openjdk.org/jeps/367): loại bỏ Pack200.





