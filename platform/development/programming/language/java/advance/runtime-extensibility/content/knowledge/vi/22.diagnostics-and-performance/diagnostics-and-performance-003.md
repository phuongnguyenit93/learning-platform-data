# Nhận diện NoSuchMethodError, AbstractMethodError và UnsupportedClassVersionError

## 1. Vì sao ba lỗi này hay xuất hiện trong hệ plugin?

Trong kiến trúc mở rộng lúc chạy, plugin thường được biên dịch và đóng gói riêng với ứng dụng host. Mã nguồn của plugin có thể hoàn toàn hợp lệ khi build, nhưng JVM thực tế lại nạp **một phiên bản class/API khác** hoặc chạy trên **JDK quá cũ**. Khi đó lỗi không nhất thiết xuất hiện lúc ứng dụng khởi động mà có thể chỉ nổ ở lần đầu gọi một phương thức hoặc định nghĩa một class.

Ba lỗi quan trọng:

| Lỗi | Ý nghĩa chính | Nguyên nhân thường gặp |
|---|---|---|
| \`NoSuchMethodError\` | Một lời gọi đã biên dịch tham chiếu method mà runtime không tìm thấy theo symbolic reference cần thiết | API/library runtime thiếu method đúng tên và descriptor |
| \`AbstractMethodError\` | Runtime cố gọi một method cần triển khai cụ thể nhưng method đích vẫn abstract hoặc không có implementation phù hợp | Provider cũ không triển khai method của interface/API mới |
| \`UnsupportedClassVersionError\` | JVM không đọc được class-file version được yêu cầu | Plugin build bằng Java mới hơn JVM đang chạy, hoặc class file có version không được hỗ trợ |

Cả ba thuộc nhóm \`LinkageError\` (trực tiếp hoặc qua \`IncompatibleClassChangeError\`), chứ không phải lỗi cú pháp Java thông thường. Cụ thể, \`NoSuchMethodError\` và \`AbstractMethodError\` đều kế thừa \`IncompatibleClassChangeError\`; \`UnsupportedClassVersionError\` kế thừa \`ClassFormatError\`.

**Phân biệt với exception nghiệp vụ:** \`try/catch (Exception)\` không bắt được chúng vì \`LinkageError\` thuộc \`Error\`. Trong plugin host, nên phát hiện tương thích trước khi công bố plugin; tại ranh giới cách ly có thể log/cô lập sự cố linkage, nhưng không nên bắt mọi \`Error\` rồi tiếp tục như không có gì xảy ra.

## 2. Tầng biên dịch khác tầng liên kết/runtime

\`\`\`text
Plugin source + API v2  --javac--> plugin.jar
                                    |
                                    v
                    Runtime host + API v1 / Java cũ
                                    |
                    class loading / verification / resolution
                                    |
                  invoke bytecode / resolve symbolic method
                                    |
                           LinkageError
\`\`\`

Java compiler kiểm tra method dựa trên những class nằm ở **compile classpath/module path**. Khi chạy, JVM lại dựa vào **runtime classpath/module path và class loader graph**. Hai môi trường có thể khác nhau do:

- Build dùng API mới, deployment đóng gói API cũ.
- Plugin mang theo thư viện riêng gây trùng class hoặc khác loader.
- Shading/fat JAR làm rơi hoặc ghi đè class.
- Module layer của plugin đọc API từ parent layer không đúng bản mong đợi.
- Hot reload giữ instance cũ nhưng công bố contract mới.
- Build sử dụng \`--release\` hoặc bytecode target không phù hợp runtime.

Không nên kết luận “compiler bị lỗi” chỉ vì source compile thành công nhưng runtime gặp linkage error. Nguyên nhân thường nằm ở **môi trường kết hợp artifact**.

## 3. NoSuchMethodError: phương thức không có ở runtime

Ví dụ stack trace:

\`\`\`text
java.lang.NoSuchMethodError:
  'java.lang.String com.example.api.GreetingService.greet(java.lang.String)'
    at com.example.plugin.GreetingPlugin.run(GreetingPlugin.java:12)
\`\`\`

JVM đang cố giải quyết lời gọi tới một method có tên và **descriptor bytecode** cụ thể. Descriptor bao gồm kiểu tham số và kiểu trả về; thay đổi kiểu trả về cũng có thể tạo ra lỗi binary compatibility dù tên method và danh sách tham số ở source trông gần giống nhau.

Các nguồn gây lỗi:

1. **Method mới chưa tồn tại ở runtime**: plugin được build theo API v2 có \`greet(String)\`, host cung cấp API v1 chưa có.
2. **Đổi signature**: \`greet(String)\` thành \`greet(Object)\` hoặc đổi kiểu trả về mà không giữ binary bridge tương ứng.
3. **Thay dependency phiên bản**: library trên runtime thiếu overload mà bytecode plugin đã gọi.
4. **Nạp sai class**: cùng FQCN nhưng được lấy từ JAR/version khác theo class loader.

Không phải cứ lỗi \`NoSuchMethodError\` là “không hề có method cùng tên”. Hãy so sánh **tên, parameter types, return type và class thực sự được nạp**. Generic erasure, bridge methods, static/instance change và covariant return types cũng có thể ảnh hưởng đến binary method descriptor.

### Cách chẩn đoán

- Đọc dòng đầu của stack trace: owner class, method name, parameter và return type JVM đang yêu cầu.
- Tìm class có owner đó trong runtime artifact thực tế, không chỉ trong source repository.
- Dùng \`javap -s -p\` để kiểm tra method descriptor:

\`\`\`bash
javap -classpath runtime-api.jar -s -p com.example.api.GreetingService
\`\`\`

- So sánh với artifact API dùng tại compile time.
- Bật JVM class loading log khi cần:

\`\`\`bash
java -Xlog:class+load=info -jar host.jar
\`\`\`

- Kiểm tra dependency tree, classpath/module path, class loader, shaded JAR và phiên bản đã deploy.

**Sửa đúng gốc:** chọn runtime API tương thích với bytecode plugin, hoặc build lại plugin theo API được host hỗ trợ. Chỉ đổi source rồi không rebuild/deploy đủ artifact sẽ không giải quyết mismatch.

## 4. AbstractMethodError: có lời gọi nhưng không có triển khai hợp lệ

Ví dụ tình huống:

**API v1**:

\`\`\`java
public interface Processor {
    String process(String input);
}
\`\`\`

Plugin cũ triển khai \`process\`. Sau đó **API v2** bổ sung:

\`\`\`java
public interface Processor {
    String process(String input);
    String description();
}
\`\`\`

Một plugin đã được biên dịch với API v1 có thể vẫn được nạp trong môi trường API v2, nhưng nếu host gọi \`description()\` trên instance cũ, runtime có thể ném \`AbstractMethodError\`. Lớp implementation cũ không có bytecode cho method mới; Java không yêu cầu compiler của plugin chạy lại tại thời điểm host deploy.

Thông điệp lỗi thường biểu thị class nhận cuộc gọi không định nghĩa hoặc kế thừa implementation phù hợp cho một method abstract mà JVM phải thực thi.

Lưu ý:

- Thêm abstract method vào interface có thể làm implementation cũ thất bại **khi method mới được gọi**.
- Một \`default\` method đôi khi hỗ trợ tương thích ngược, nhưng phải kiểm tra conflict giữa các interface và semantics mới.
- Thay đổi abstract/concrete method, hierarchy, bridge method hoặc biến đổi dependency có thể dẫn đến các lỗi linkage khác nhau.
- Không tự suy ra rằng mọi thay đổi interface đều chắc chắn gây \`AbstractMethodError\`; còn phụ thuộc call site và bytecode.

### Cách chẩn đoán

1. Xác định **receiver runtime class** và method bị gọi từ stack trace.
2. Kiểm tra interface/superclass đang được JVM nạp tại runtime.
3. Dùng \`javap -p -s\` với plugin JAR để xem implementation thực tế.
4. So với API compile-time của plugin và API mà host dùng.
5. Chạy contract test: tạo instance plugin và gọi tất cả method bắt buộc của service interface trước khi đưa plugin vào registry.

**Sửa đúng gốc:** build lại plugin để triển khai đầy đủ contract mới; hoặc giữ backward-compatible API/adapter có thiết kế rõ. Host không nên chờ đến request thật mới thử gọi method bắt buộc mới.

## 5. UnsupportedClassVersionError: class file mới hơn JVM

Mỗi \`.class\` có class-file major/minor version. Java 17 dùng **major version 61**; Java 21 dùng **major version 65**. Một class build cho Java 21 thường không thể được JVM Java 17 định nghĩa.

Ví dụ lỗi:

\`\`\`text
java.lang.UnsupportedClassVersionError:
  com/example/plugin/ReportPlugin has been compiled by a more recent
  version of the Java Runtime (class file version 65.0),
  this version of the Java Runtime only recognizes class file
  versions up to 61.0
\`\`\`

Bảng tham khảo:

| Java release | Class-file major |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Không nên suy luận target bytecode chỉ từ JDK dùng để chạy lệnh \`javac\`: compiler hiện đại có thể tạo bytecode cho version cũ nếu dùng \`--release\`. Ngược lại, class có major được hỗ trợ vẫn có thể thất bại khi gọi API không tồn tại trên runtime; class-file compatibility và API compatibility là hai bài toán khác nhau.

### Cách khắc phục

- Kiểm tra \`java -version\` **trong đúng process/container đang chạy host**.
- Kiểm tra \`javac -version\` và cấu hình build như Maven \`maven.compiler.release\` hoặc Gradle Java toolchain.
- Kiểm tra bytecode artifact thật bằng \`javap -verbose\`:

\`\`\`bash
javap -verbose -classpath plugin.jar com.example.plugin.ReportPlugin
\`\`\`

Tìm \`major version: ...\`. Nếu Java runtime quá cũ, nâng JDK chạy hoặc rebuild plugin với \`--release\` phù hợp nếu source và dependencies cho phép.

\`\`\`bash
javac --release 17 -d out src/com/example/plugin/ReportPlugin.java
\`\`\`

Đoạn lệnh giả định đường dẫn source tồn tại. \`--release 17\` giới hạn ngôn ngữ và public Java API theo Java 17; nó không tự bảo đảm mọi thư viện bên thứ ba runtime tương thích hoặc source plugin hoạt động đúng trên mọi môi trường.

## 6. Demo Java 17+ tái hiện NoSuchMethodError bằng hai API JAR

Ví dụ gồm API v1, API v2 và client được biên dịch với v2 nhưng chạy với v1.

Cấu trúc:

\`\`\`text
demo/
├── v1/api/Api.java
├── v2/api/Api.java
└── client/Client.java
\`\`\`

**\`v1/api/Api.java\`**:

\`\`\`java
package api;
public class Api {
    public String hello() { return "v1"; }
}
\`\`\`

**\`v2/api/Api.java\`**:

\`\`\`java
package api;
public class Api {
    public String hello() { return "v2"; }
    public String newMethod() { return "new"; }
}
\`\`\`

**\`client/Client.java\`**:

\`\`\`java
import api.Api;

public class Client {
    public static void main(String[] args) {
        System.out.println(new Api().newMethod());
    }
}
\`\`\`

Từ thư mục \`demo\`, chạy (shell POSIX):

\`\`\`bash
javac -d out/v1 v1/api/Api.java
javac -d out/v2 v2/api/Api.java
jar --create --file api-v1.jar -C out/v1 .
jar --create --file api-v2.jar -C out/v2 .
javac -cp api-v2.jar -d out/client client/Client.java
java -cp out/client:api-v1.jar Client
\`\`\`

Trên Windows, dùng \`;\` thay \`:\` làm dấu phân cách classpath.

Khi chạy với \`api-v1.jar\`, JVM nạp class \`api.Api\` không có \`newMethod()\`. Kết quả là \`NoSuchMethodError\`, với thông điệp có phần tương tự:

\`\`\`text
Exception in thread "main" java.lang.NoSuchMethodError:
  'java.lang.String api.Api.newMethod()'
    at Client.main(Client.java:5)
\`\`\`

Kết quả chính xác về số dòng/format phụ thuộc compiler/JDK, nhưng loại lỗi và symbolic reference \`api.Api.newMethod():String\` là trọng tâm của bài.

Nếu thay runtime JAR thành \`api-v2.jar\`:

\`\`\`bash
java -cp out/client:api-v2.jar Client
\`\`\`

Stdout:

\`\`\`text
new
\`\`\`

Bài học: **client build được không đồng nghĩa API runtime tương ứng**.

## 7. Demo Java 17+ tái hiện AbstractMethodError

Sử dụng cùng mô hình build riêng.

**\`v1/api/Action.java\`**:

\`\`\`java
package api;
public interface Action {
    String execute();
}
\`\`\`

**\`v1/impl/OldAction.java\`**:

\`\`\`java
package impl;
import api.Action;
public class OldAction implements Action {
    public String execute() { return "done"; }
}
\`\`\`

**\`v2/api/Action.java\`**:

\`\`\`java
package api;
public interface Action {
    String execute();
    String description();
}
\`\`\`

**\`client/TestAction.java\`**:

\`\`\`java
import api.Action;
import impl.OldAction;

public class TestAction {
    public static void main(String[] args) {
        Action action = new OldAction();
        System.out.println(action.description());
    }
}
\`\`\`

Trong một thư mục demo riêng với cấu trúc trên, chạy:

\`\`\`bash
javac -d out/v1 v1/api/Action.java v1/impl/OldAction.java
javac -d out/v2 v2/api/Action.java
javac -cp out/v2:out/v1 -d out/client client/TestAction.java
java -cp out/client:out/v2:out/v1 TestAction
\`\`\`

Với Windows, thay \`:\` bằng \`;\`. Runtime sẽ nạp \`api.Action\` từ \`out/v2\` trước, nhưng instance \`OldAction\` được biên dịch trước đó theo v1. Khi gọi \`description()\`, JVM có thể ném:

\`\`\`text
java.lang.AbstractMethodError: Receiver class impl.OldAction
does not define or inherit an implementation ...
\`\`\`

Phần message cụ thể phụ thuộc JDK. Cách sửa là triển khai \`description()\` và build lại \`OldAction\`, hoặc thiết kế hợp đồng API tương thích ngược như một default method có semantics phù hợp.

Lưu ý lệnh build \`TestAction\` dùng cả \`out/v2\` và \`out/v1\`; \`out/v2\` đứng trước để compiler thấy interface mới. Đây chỉ là thí nghiệm mô phỏng binary compatibility; dự án thực tế không nên phân phối hai bản API trùng tên trong cùng runtime search path.

## 8. Demo UnsupportedClassVersionError có điều kiện môi trường

Để tái hiện chuẩn, cần **hai phiên bản JDK**: một JDK mới để biên dịch và một JVM cũ để chạy. Ví dụ với JDK 21 và JDK 17:

\`\`\`java
public class NewerClass {
    public static void main(String[] args) {
        System.out.println("hello");
    }
}
\`\`\`

Biên dịch bằng JDK 21:

\`\`\`bash
/path/to/jdk21/bin/javac NewerClass.java
\`\`\`

Chạy class này bằng JDK 17:

\`\`\`bash
/path/to/jdk17/bin/java NewerClass
\`\`\`

Khi class được biên dịch mặc định cho Java 21, class file mang major 65; JVM 17 chỉ hỗ trợ tới major 61 và ném \`UnsupportedClassVersionError\`. Đường dẫn JDK ở trên là **ký hiệu minh họa**, không phải lệnh chạy nguyên xi trên mọi máy. Không thể tái hiện lỗi này chỉ bằng cách chạy một JDK 17 duy nhất nếu class đang được biên dịch với \`--release 17\` và không có bytecode version cao hơn.

## 9. Quy trình chẩn đoán nhanh khi nhận stack trace

\`\`\`text
LinkageError xảy ra
      |
      v
Đọc tên lỗi chính xác
      |
      +-- UnsupportedClassVersionError
      |       -> kiểm tra class major/JVM runtime
      |
      +-- NoSuchMethodError
      |       -> so method descriptor compile-time vs runtime
      |
      +-- AbstractMethodError
              -> tìm receiver class và method abstract còn thiếu
      |
      v
Xác định class/JAR/module/class loader thực tế
      |
      v
Kiểm tra dependency tree, packaging và API policy
      |
      v
Reproduce từ artifact đã deploy
      |
      v
Sửa version/contract + test lại
\`\`\`

Checklist tối thiểu:

1. Ghi **toàn bộ stack trace**, JDK version và artifact version.
2. Xác định method/class bị lỗi và class loader đã nạp class đó.
3. So sánh compile-time dependency với runtime dependency thật.
4. Dùng \`javap\` xem descriptor hoặc major version; không chỉ xem source.
5. Với plugin, kiểm tra parent delegation, duplicate class và JPMS module graph.
6. Xác minh bản fix trên **đúng artifact đóng gói cuối cùng**, không chỉ IDE.
7. Bổ sung contract tests và kiểm tra API compatibility trước khi kích hoạt plugin.

Một log chẩn đoán có ích nên bao gồm plugin ID, plugin version, host API version, JDK version, loader identity và nguồn class nếu có. Không ghi dữ liệu người dùng nhạy cảm chỉ để điều tra linkage.

## 10. Phòng ngừa trong hệ plugin runtime

**Định nghĩa API contract ổn định:** host cung cấp một shared API module/JAR, plugin build theo phiên bản đã công bố. Dùng \`provided\`/\`compileOnly\` khi thích hợp để plugin không đóng gói một bản copy của shared API gây sai class identity.

**Kiểm tra phiên bản trước kích hoạt:** module version một mình không đủ. Plugin cần khai báo API requirement và minimum Java version; host phải áp dụng version-range policy, kiểm tra capability và binary compatibility.

**Không dùng loader ngẫu nhiên:** xác định package nào được parent-first và package nào được isolate. Host API cần có defining loader thống nhất ở ranh giới giao tiếp.

**Thử provider trước publish:** chạy health checks và những method bắt buộc trong môi trường staging. Cẩn trọng vì một method chỉ được liên kết khi đường code đó chạy; smoke test không chứng minh mọi path đều an toàn.

**Có lifecycle rollback:** nếu nâng cấp plugin gây linkage failure, dừng cấp request mới, rollback registry/snapshot theo policy và xử lý in-flight requests. Không tự động retry thao tác nghiệp vụ đã có side effect.

**Quan sát theo build/deployment:** lưu dependency lock, build metadata, runtime API version và JDK release. Đối với plugin không tin cậy, nhớ rằng class loader/module layer không phải sandbox bảo mật.

## 11. Phân biệt với những lỗi họ hàng

| Lỗi | Gợi ý khác biệt |
|---|---|
| \`ClassNotFoundException\` | Loader không tìm thấy lớp khi lookup theo tên |
| \`NoClassDefFoundError\` | JVM không thể định nghĩa/liên kết class cần thiết hoặc class trước đó khởi tạo thất bại |
| \`ClassCastException\` | Object không thể ép sang expected type; có thể do duplicate class identity |
| \`NoSuchMethodError\` | Symbolic method reference không được runtime giải quyết đúng |
| \`AbstractMethodError\` | Không có concrete implementation phù hợp ở receiver |
| \`IllegalAccessError\` | Truy cập class/method/field không còn hợp lệ theo visibility |
| \`IncompatibleClassChangeError\` | Thay đổi quan hệ instance/static, inheritance hoặc binary contract |
| \`UnsupportedClassVersionError\` | Runtime không hỗ trợ version class file |

Không sửa tất cả bằng cách “thêm JAR vào classpath”. Việc thêm JAR có thể khiến class được nạp sai phiên bản và làm lỗi trầm trọng hơn.

## 12. Những lỗi thường gặp

- Nhầm \`NoSuchMethodError\` với \`NoSuchMethodException\`: loại thứ hai là checked exception của reflective API, khác việc JVM liên kết bytecode method call.
- Nhầm \`AbstractMethodError\` với lỗi source do quên override: compiler có thể ngăn source mới, nhưng binary cũ vẫn có thể được nạp.
- Cho rằng Java 17 compiler luôn tạo bytecode Java 17 dù dùng target/release khác.
- Bỏ qua version JDK **thực sự** trong container hoặc service process.
- Chỉ xem dependency tree build, không nhìn runtime classpath/shaded artifact.
- Dùng module version như phép bảo đảm binary compatibility.
- Hot-reload class loader nhưng để object cũ giao tiếp với API/class mới không tương thích.
- Bắt \`Exception\` rồi kỳ vọng xử lý được mọi \`LinkageError\`.
- Log “plugin failed” nhưng không lưu owner method, descriptor và class source.
- Tin rằng chạy thành công một test đơn giản chứng minh toàn bộ code path tương thích.

## 13. Checklist ghi nhớ

Nếu gặp:

- **\`NoSuchMethodError\`**: hỏi “bytecode đang yêu cầu **method descriptor nào**, và JAR/module runtime chứa đúng method đó không?”
- **\`AbstractMethodError\`**: hỏi “instance cụ thể có **implementation của method** mà API runtime yêu cầu không?”
- **\`UnsupportedClassVersionError\`**: hỏi “class-file major này có được **JVM đang chạy** hỗ trợ không?”

**Kết luận:** trong hệ Java mở rộng lúc chạy, ba lỗi trên thường tiết lộ **lệch hợp đồng giữa build và runtime**. Muốn khắc phục triệt để phải so sánh bytecode thực, dependency và loader thực tế, áp dụng chính sách tương thích trước kích hoạt và kiểm thử trên artifact deployment cuối cùng.
