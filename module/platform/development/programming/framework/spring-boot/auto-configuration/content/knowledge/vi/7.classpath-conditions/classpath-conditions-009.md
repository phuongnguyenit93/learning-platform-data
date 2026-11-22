# Phân biệt thiếu lớp, thiếu dependency bắc cầu và sai phiên bản thư viện

> **Bối cảnh:** Spring Boot Auto Configuration — nhóm **Điều kiện classpath**. Bài học tập trung vào cách phân biệt triệu chứng trên classpath với nguyên nhân trong đồ thị dependency và tính tương thích nhị phân của thư viện. Các ví dụ sử dụng Java 17+.

## 1. Mô hình tư duy: ba trường hợp liên quan nhưng không đồng nghĩa

**Classpath lúc chạy (runtime classpath)** là tập thư mục/JAR mà JVM và class loader thực sự có thể tìm thấy khi ứng dụng khởi động và thực thi. Nó có thể khác **compile classpath** được sử dụng khi biên dịch. Có một class lúc biên dịch không bảo đảm class đó còn được đóng gói hoặc nạp đúng phiên bản lúc chạy.

| Trường hợp | Vấn đề gốc | Biểu hiện thường gặp | Hướng xác minh đầu tiên |
| --- | --- | --- | --- |
| **Thiếu lớp (missing class)** | JVM/class loader không tìm thấy một lớp cần dùng ở thời điểm nạp hoặc liên kết | ClassNotFoundException, NoClassDefFoundError | Lớp có thật trong JAR nào? JAR đó có trên classpath **lúc chạy** không? |
| **Thiếu dependency bắc cầu (missing transitive dependency)** | Thư viện A được đưa vào ứng dụng, nhưng thư viện B mà A cần lúc chạy lại vắng mặt | Thường cũng là NoClassDefFoundError, đôi khi ClassNotFoundException | A có mặt nhưng B bị exclude, khai báo sai scope, optional hoặc không được đóng gói? |
| **Sai phiên bản thư viện (incompatible library version)** | Lớp được nạp nhưng API/ABI thực tế không khớp với phiên bản đã dùng để biên dịch; đôi khi phiên bản mới không còn lớp cũ | NoSuchMethodError, NoSuchFieldError, AbstractMethodError, IncompatibleClassChangeError; cũng có thể NoClassDefFoundError | Đúng phiên bản JAR nào được chọn và nạp? Method/field với **đúng chữ ký** có trong JAR đó không? |

**Điểm phân biệt cốt lõi:** “Thiếu lớp” là một **triệu chứng ở mức class loading**; thiếu dependency bắc cầu là **một nguyên nhân** có thể làm xuất hiện triệu chứng đó. Sai phiên bản đôi khi cũng làm thiếu lớp nếu bản mới đã di chuyển/xóa lớp. Vì vậy **không thể kết luận chỉ từ tên exception**; phải nối exception với lớp lỗi, JAR chứa lớp đó và đồ thị dependency ở runtime.

Ví dụ một ứng dụng trực tiếp phụ thuộc SDK A, còn A phụ thuộc thư viện B:

~~~text
Ứng dụng
  └── SDK A                 (dependency trực tiếp)
        └── Thư viện B      (dependency bắc cầu)
              └── class B.Helper
~~~

- Thiếu **SDK A**: một lớp của A có thể không nạp được.
- Có **A** nhưng thiếu **B**: một lớp thuộc B không nạp được khi A gọi tới B.
- Có **A** và **B**, nhưng B bị thay bằng bản không tương thích: lớp B.Helper có thể vẫn tồn tại, song lời gọi method của A có thể gây NoSuchMethodError.

## 2. Hiểu đúng tín hiệu lỗi của JVM

### 2.1. ClassNotFoundException và NoClassDefFoundError

- **ClassNotFoundException** là checked exception thường phát sinh khi code chủ động tìm lớp theo tên, chẳng hạn Class.forName("com.example.Plugin") hoặc ClassLoader.loadClass(...), nhưng loader không tìm thấy. Có thể vì thiếu JAR, sai tên lớp, sai class loader hoặc tính năng tùy chọn chưa được cài.
- **NoClassDefFoundError** là LinkageError thường xuất hiện khi bytecode cần một lớp mà JVM không thể định nghĩa/tìm được lúc thực thi, dù code đã được biên dịch thành công ở môi trường khác. Tên lớp trong thông báo là **manh mối trực tiếp** để truy ra JAR sở hữu lớp.
- **NoClassDefFoundError: Could not initialize class ...** có thể là hậu quả của **lần khởi tạo tĩnh trước đó đã thất bại** (ví dụ ExceptionInInitializerError), không đơn thuần là thiếu JAR. Hãy đọc phần **Caused by** và lỗi đầu tiên theo thứ tự thời gian.
- Lỗi có thể được bọc bên ngoài trong BeanCreationException, IllegalStateException hoặc UnsatisfiedDependencyException của Spring. Cần đi đến nguyên nhân gốc trong stack trace thay vì chỉ nhìn dòng trên cùng.

Ví dụ:

~~~text
java.lang.NoClassDefFoundError: com/example/transport/Codec
~~~

Đây là bằng chứng JVM cần lớp Codec nhưng không dùng được. Nó **chưa** chứng minh ứng dụng quên khai báo dependency trực tiếp hay dependency bắc cầu: phải tìm lớp Codec trong thư viện nào và tại sao thư viện đó vắng mặt.

### 2.2. Dấu hiệu lệch phiên bản API/ABI

- **NoSuchMethodError**: một lời gọi đã được biên dịch với tên, kiểu tham số và kiểu trả về nhất định nhưng method tương ứng không tồn tại trong lớp thực tế ở runtime.
- **NoSuchFieldError**: field đã được tham chiếu lúc biên dịch nhưng không tồn tại với dạng mong đợi ở runtime.
- **AbstractMethodError / IncompatibleClassChangeError**: quan hệ interface/class hoặc hợp đồng nhị phân đã thay đổi, thường liên quan bản thư viện hoặc các bản bị trộn.
- **UnsupportedClassVersionError**: bytecode được tạo cho phiên bản Java mới hơn JVM đang chạy; phải kiểm tra phiên bản JDK/JRE trước, không gộp nhầm vào “thiếu dependency”.
- **ExceptionInInitializerError**: code khởi tạo tĩnh ném lỗi; có thể là cấu hình, tài nguyên hoặc lỗi trong thư viện, không mặc định là sai phiên bản.

Cùng một class có tên đầy đủ (FQCN) tồn tại **không đủ** để chứng minh tương thích. Với NoSuchMethodError, cần so **chữ ký bytecode** (descriptor) gồm cả kiểu trả về, không chỉ tên method trên tài liệu.

## 3. Phân biệt bằng câu hỏi chẩn đoán theo thứ tự

1. **Lấy lỗi gốc:** ghi lại loại lỗi, tên lớp/method/field, stack trace và chuỗi Caused by; xác định lỗi xảy ra khi khởi động, tạo bean hay gọi API.
2. **Xác định lớp/JAR sở hữu:** tìm group/artifact/version chứa FQCN được báo lỗi; không đoán theo tên starter hay tên bean.
3. **Kiểm tra classpath runtime thực tế:** dependency có được resolve cho runtimeClasspath? Nó có nằm trong executable JAR/container hoặc lệnh java -cp thực tế không? Có class loader riêng không?
4. **Nếu JAR cần thiết vắng mặt:** nó là dependency trực tiếp chưa khai báo, hay dependency bắc cầu của một thư viện đã có? Tìm exclusions, optional, compileOnly/provided, cấu hình Gradle/Maven và lỗi packaging.
5. **Nếu JAR có mặt:** kiểm tra JAR chứa đúng class không; nếu có, dùng javap đối chiếu method/field với phiên bản đã biên dịch, phiên bản được resolve và thứ tự classpath/class loader.
6. **Đối chiếu với Spring Boot condition report:** @ConditionalOnClass không match có thể là **hành vi tùy chọn bình thường**. Nếu một bean đáng ra phải có hoặc app thực sự crash, điều tra nguyên nhân tiếp; đừng coi mọi negative match là lỗi.
7. **Sửa đúng nguyên nhân và chạy lại đúng môi trường:** test cùng JDK, profile, cách đóng gói, lệnh chạy và đồ thị dependency đã gây lỗi.

~~~text
Có lỗi liên quan classpath?
  |
  +-- Chỉ là @ConditionalOnClass không match, app vẫn chạy?
  |     +-- Có thể là tính năng tùy chọn bị bỏ qua đúng thiết kế.
  |
  +-- ClassNotFoundException / NoClassDefFoundError?
  |     +-- Tìm class -> JAR sở hữu -> có mặt lúc chạy?
  |           +-- Không: xem direct dependency hay transitive dependency,
  |           |          exclusions, scope, packaging, class loader.
  |           +-- Có: kiểm tra class thật trong JAR, lớp phụ thuộc khác,
  |                      lỗi khởi tạo tĩnh và bản được nạp thực tế.
  |
  +-- NoSuchMethodError / NoSuchFieldError / AbstractMethodError?
        +-- Lớp có mặt nhưng ABI không khớp:
              so phiên bản compile và runtime, dependency resolution,
              signature bằng javap và thứ tự classpath.
~~~

## 4. Phòng thí nghiệm Java 17+: cùng một chương trình, ba kết quả khác nhau

Lab này mô phỏng **App → SDK → Helper**. App gọi SDK trực tiếp; SDK được biên dịch dựa trên Helper v1. Không cần Spring Boot hoặc công cụ build để tái hiện, nhờ đó có thể quan sát lỗi JVM độc lập với framework.

Tạo các tệp theo cấu trúc:

~~~text
src/
  helper/v1/demo/Helper.java
  helper/v2/demo/Helper.java
  sdk/demo/Sdk.java
  app/App.java
~~~

**Tệp src/helper/v1/demo/Helper.java**

~~~java
package demo;

public final class Helper {
    public static String text() {
        return "helper-v1";
    }
}
~~~

**Tệp src/helper/v2/demo/Helper.java** — cùng tên lớp nhưng thay đổi API, bỏ method text():

~~~java
package demo;

public final class Helper {
    public static String renamed() {
        return "helper-v2";
    }
}
~~~

**Tệp src/sdk/demo/Sdk.java** — SDK gọi API của Helper v1:

~~~java
package demo;

public final class Sdk {
    public static String call() {
        return Helper.text();
    }
}
~~~

**Tệp src/app/App.java** — ứng dụng chỉ cần biết SDK:

~~~java
import demo.Sdk;

public class App {
    public static void main(String[] args) {
        System.out.println(Sdk.call());
    }
}
~~~

Dùng terminal Bash/Git Bash tại thư mục chứa src; cần **JDK 17+**. Để dễ nhìn sự khác biệt, mỗi thư mục output được dùng như một thành phần classpath riêng:

~~~bash
mkdir -p out/helper-v1 out/helper-v2 out/sdk out/app
javac -d out/helper-v1 src/helper/v1/demo/Helper.java
javac -cp out/helper-v1 -d out/sdk src/sdk/demo/Sdk.java
javac -cp out/sdk -d out/app src/app/App.java
javac -d out/helper-v2 src/helper/v2/demo/Helper.java
~~~

**Ca 1 — đủ class và đúng bản:** App, SDK và Helper v1 đều hiện diện.

~~~bash
java -cp out/app:out/sdk:out/helper-v1 App
~~~

Stdout chính xác:

~~~text
helper-v1
~~~

**Ca 2 — thiếu lớp của dependency trực tiếp:** bỏ out/sdk, dù còn Helper v1.

~~~bash
java -cp out/app:out/helper-v1 App
~~~

Chương trình dừng với lỗi có tên **NoClassDefFoundError: demo/Sdk** (stack trace đầy đủ có thể khác nhau). Class của chính SDK không có trong runtime classpath.

**Ca 3 — thiếu dependency bắc cầu:** có out/sdk nhưng bỏ Helper mà SDK đã biên dịch dựa vào.

~~~bash
java -cp out/app:out/sdk App
~~~

Chương trình dừng với lỗi có tên **NoClassDefFoundError: demo/Helper**. SDK tồn tại, nhưng thành phần nó cần khi thực thi lại vắng mặt. Trong build thật, trường hợp tương ứng có thể do exclusion, scope hoặc metadata dependency của SDK.

**Ca 4 — sai phiên bản dependency:** thay Helper v1 bằng Helper v2, giữ nguyên SDK đã biên dịch với v1.

~~~bash
java -cp out/app:out/sdk:out/helper-v2 App
~~~

Chương trình dừng với **NoSuchMethodError** liên quan **demo.Helper.text()**. JVM tìm thấy demo.Helper nhưng phiên bản runtime không còn method mà Sdk.class yêu cầu. Đây là lệch **tương thích nhị phân**, không phải thiếu lớp.

**Trên Windows CMD/PowerShell**, dấu phân tách các mục classpath là dấu chấm phẩy **;** thay cho dấu hai chấm **:**, ví dụ: java -cp "out/app;out/sdk;out/helper-v1" App. Lệnh mkdir -p ở trên dành cho Bash/Git Bash; có thể tạo các thư mục bằng trình quản lý tệp hoặc PowerShell trước khi chạy javac.

Bài học rút ra từ lab: **cùng một App.class** nhưng kết quả thay đổi hoàn toàn theo **runtime classpath**. Vì vậy dòng dependency được khai báo trong mã nguồn chỉ là điểm khởi đầu, không thay thế việc kiểm tra thứ JVM thực sự nạp.

## 5. Đọc đồ thị dependency với Gradle và Maven

### 5.1. Gradle: phải xem cấu hình runtime

Với module ứng dụng giả định có task Gradle, dùng:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight --dependency helper-lib --configuration runtimeClasspath
~~~

Với Windows, dùng gradlew.bat thay cho ./gradlew; thay :app và helper-lib theo tên module/artifact thực tế.

- **dependencies** cho biết thư viện nào được resolve vào runtimeClasspath và quan hệ cha–con của chúng.
- **dependencyInsight** giải thích vì sao một module/phiên bản được chọn, gồm đường đi phụ thuộc và quy tắc giải quyết xung đột khi có.
- So tiếp với **compileClasspath** khi nghi compile chạy được nhưng runtime thiếu; không kết luận chỉ từ dependency tree nếu lệnh triển khai thực tế hoặc packaging đã làm thay đổi classpath.

Ví dụ cấu hình **chỉ để minh họa ý tưởng** (tọa độ com.example dưới đây là giả định):

~~~groovy
dependencies {
    implementation 'com.example:client-sdk:1.2.0'
}

// Nếu SDK cần com.example:helper-lib lúc chạy mà đường phụ thuộc bị exclude
// hoặc đánh dấu sai phạm vi, runtime có thể thiếu lớp của helper-lib.
~~~

Cần phân biệt:
- **implementation**: dependency của module có mặt ở compile và thường đi vào runtime của module ứng dụng.
- **runtimeOnly**: cần khi chạy nhưng không cần để biên dịch source trực tiếp.
- **compileOnly**: chỉ tham gia compile; dùng sai cho thư viện thật sự cần runtime sẽ làm runtime thiếu.
- **exclude**: loại một đường dependency bắc cầu; nếu không có đường khác cung cấp module cần thiết, ứng dụng có thể crash.
- **api** trong java-library plugin: làm lộ dependency cho người tiêu thụ ở compile API; khi SDK công bố class qua API công khai, lựa chọn giữa api/implementation phải đúng. Không dùng api bừa chỉ để làm biến mất lỗi runtime.

Nếu xuất hiện nhiều phiên bản cùng thư viện, kiểm tra **phiên bản được resolve**; Gradle có cơ chế giải quyết xung đột phiên bản và có thể bị chi phối bởi constraints, platform hoặc force. Một dòng khai báo mong muốn **không bảo đảm** đó là bản cuối cùng được dùng.

### 5.2. Maven: xem cây và scope

~~~bash
mvn dependency:tree
mvn dependency:tree -Dscope=runtime
mvn dependency:tree -Dincludes=com.example:helper-lib
~~~

- Xem nhánh dependency nào mang helper-lib vào dự án, nó có bị loại do exclusion/optional hay bị bản khác chiếm ưu tiên không.
- **provided** thường không được đóng gói như thư viện runtime thông thường; **test** không được dùng cho ứng dụng production; **optional** hạn chế tính bắc cầu cho consumer.
- Dependency mediation của Maven có thể chọn một phiên bản theo đường khai báo/độ gần; kiểm tra phiên bản hiệu lực thay vì chỉ nhìn pom.xml của SDK.
- Với Spring Boot, nên dùng hệ quản lý phiên bản tương thích của **Spring Boot BOM** theo cách build đang cấu hình, hạn chế tự ép phiên bản riêng lẻ của Spring Framework, Jackson, Netty hoặc thư viện hạ tầng mà Boot đã quản lý.

### 5.3. Kiểm tra JAR thực tế và API trong JAR

~~~bash
jar tf path/to/library.jar
javap -classpath path/to/library.jar -s -p com.example.Helper
java -version
~~~

- Dùng **jar tf** để xác nhận tên đường dẫn bytecode (ví dụ com/example/Helper.class) có thật.
- Dùng **javap -s -p** để kiểm tra tên method/field và descriptor thực tế; so sánh JAR compile với JAR runtime.
- Với **Spring Boot executable JAR**, xem các dependency được đóng gói dưới BOOT-INF/lib và class ứng dụng dưới BOOT-INF/classes. Khi chạy bằng java -jar, Boot launcher xử lý nested JAR; không giả định java -cp app.jar sẽ tự nạp các nested dependency.
- Với Docker/container, IDE, plugin framework hoặc ứng dụng có nhiều class loader, phải kiểm tra **artifact và lệnh chạy cuối cùng**. Dependency xuất hiện trên máy develop vẫn có thể vắng ở image triển khai.

## 6. Liên hệ trực tiếp với Spring Boot Auto Configuration

**@ConditionalOnClass** là điều kiện cho phép auto-configuration kích hoạt **khi các class được chỉ định hiện diện**. Nếu dependency tùy chọn không được cài, điều kiện không match và cấu hình có thể được bỏ qua **đúng thiết kế**. Khi đọc báo cáo condition, phân biệt:

| Hiện tượng | Ý nghĩa | Nên làm gì |
| --- | --- | --- |
| @ConditionalOnClass báo **did not find required class** và ứng dụng chạy bình thường | Auto-configuration cho tính năng tùy chọn không được áp dụng | Chỉ bổ sung dependency nếu ứng dụng thực sự cần tính năng đó |
| Bean cần dùng không xuất hiện và class được báo thiếu | Một điều kiện classpath đã chặn cấu hình cần thiết | Xác định dependency sở hữu class, kiểm tra runtimeClasspath và điều kiện khác |
| Startup ném NoClassDefFoundError trong lúc phân tích/tạo bean | Class cần nạp thật sự không dùng được; có thể là dependency bắc cầu, tham chiếu quá sớm hoặc lỗi khởi tạo | Truy Caused by, kiểm tra classpath/JAR, tách cấu hình tùy chọn khi thích hợp |
| @ConditionalOnClass match nhưng gọi SDK gây NoSuchMethodError | Điều kiện chỉ chứng minh **sự hiện diện của lớp**, không chứng minh tương thích toàn bộ API | So chữ ký API và phiên bản thực nạp |

Ví dụ cấu trúc auto-configuration có điều kiện classpath (đây là **đoạn mã thành phần** trong dự án Spring Boot, không phải chương trình độc lập chạy bằng javac thuần):

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class VendorAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.sdk.Client")
    static class ClientPresentConfiguration {

        @Bean
        ClientFeature clientFeature() {
            return new ClientFeature();
        }
    }

    public static final class ClientFeature {
    }
}
~~~

Ở đây điều kiện dùng **tên class dưới dạng chuỗi**. Nếu com.vendor.sdk.Client không có, lớp cấu hình lồng nhau được bỏ qua; code không trực tiếp tham chiếu type Client để buộc JVM liên kết type đó ở vị trí không an toàn. Khi một method @Bean dùng **kiểu trả về hoặc tham số của thư viện tùy chọn**, nên cô lập method đó trong lớp @Configuration được bảo vệ bởi điều kiện classpath, tránh phân tích chữ ký method quá sớm khi dependency vắng mặt. Để auto-configuration của thư viện được phát hiện, dự án phải đăng ký class tương ứng theo cơ chế AutoConfiguration.imports phù hợp phiên bản Spring Boot đang dùng.

**Giới hạn của @ConditionalOnClass:** nó không tự kiểm tra dependency bắc cầu, method signature, phiên bản tương thích của SDK, bean được tạo thành công hay runtime class loader đặc thù. Do đó một positive match **không** bảo đảm không có NoSuchMethodError hoặc NoClassDefFoundError về sau.

**Xem báo cáo condition:** chạy ứng dụng với tùy chọn --debug hoặc xem condition evaluation report qua endpoint actuator **conditions** khi actuator được cài và endpoint được bật/expose theo cấu hình vận hành. Báo cáo cho biết lý do match/did not match; nó **không thay thế stack trace** khi JVM đã ném lỗi. Không mở actuator chẩn đoán ra môi trường công khai khi chưa kiểm soát quyền truy cập.

## 7. Ba ca điều tra thực tế trong ứng dụng Spring Boot

### Tình huống A — lớp của SDK không có

**Quan sát:** ứng dụng yêu cầu một bean tích hợp nhưng startup báo NoClassDefFoundError: com/vendor/sdk/Client. Condition report cũng có thể cho thấy auto-configuration tương ứng bị bỏ qua.

**Xác minh:** tìm JAR sở hữu Client; nếu ứng dụng thực sự gọi SDK, xác nhận dependency trực tiếp và JAR runtime có mặt trong BOOT-INF/lib hoặc classpath triển khai.

**Sửa:** khai báo đúng artifact với scope/runtime configuration phù hợp, bảo đảm artifact có trong gói triển khai. Nếu SDK là tính năng tùy chọn và app không dùng, việc condition không match có thể là kết quả mong đợi.

### Tình huống B — SDK có nhưng thiếu thư viện mà SDK dùng

**Quan sát:** com.vendor.sdk.Client đã nạp được; đến lúc tạo bean/gọi SDK thì xuất hiện NoClassDefFoundError: com/vendor/transport/Codec.

**Xác minh:** xác định Codec thuộc artifact nào; đọc dependency tree để tìm xem nó có phải dependency bắc cầu của SDK hay không. Kiểm tra exclusions, optional/provided/compileOnly và nội dung JAR/container. Đừng cố xử lý bằng cách đổi @ConditionalOnClass sang điều kiện khác: điều kiện không tạo ra class còn thiếu.

**Sửa:** khôi phục đường dependency hợp lệ, bỏ exclusion sai hoặc khai báo trực tiếp dependency runtime cần thiết với phiên bản tương thích. Sau đó thử lại **đúng hành vi** trước đây gây lỗi (tạo bean, kết nối, xử lý request), không chỉ kiểm tra startup.

### Tình huống C — class vẫn có, method không còn

**Quan sát:** lỗi NoSuchMethodError: com.vendor.transport.Codec.encode(...) sau khi một thư viện được nâng cấp hoặc bị resolve về phiên bản khác.

**Xác minh:** dependencyInsight/dependency:tree cho phiên bản hiệu lực; jar tf xác nhận Codec.class; javap đối chiếu method và descriptor giữa bản SDK mong đợi với bản transport được nạp. Cần chú ý các dependency cùng họ hoặc BOM bị trộn phiên bản.

**Sửa:** chọn tập phiên bản đã được kiểm chứng tương thích, ưu tiên quản lý đồng bộ bằng BOM/platform và xóa force/exclusion gây lệch nếu không còn lý do. Không tự ý “nâng tất cả lên mới nhất”: phiên bản mới nhất không nhất thiết phù hợp với SDK hoặc phiên bản Spring Boot đang chạy.

## 8. Những nhầm lẫn thường gặp

1. **“NoClassDefFoundError chắc chắn là thiếu dependency trực tiếp.”** Sai: lớp có thể nằm trong dependency bắc cầu, bị đóng gói thiếu, bị nạp bởi class loader khác hoặc đã thất bại ở static initialization.
2. **“Có JAR là đủ.”** Sai: JAR có thể sai version, thiếu class, bị thay bằng bản khác ở runtime, hoặc class có nhưng không còn method/field yêu cầu.
3. **“Biên dịch thành công thì chạy cũng thành công.”** Sai: compileClasspath và runtimeClasspath khác nhau; bytecode đã biên dịch có thể gặp ABI khác ở runtime.
4. **“Auto-configuration không match nghĩa là Spring Boot bị lỗi.”** Sai: negative match là bình thường với thư viện/tính năng tùy chọn; chỉ cần xử lý khi trái yêu cầu chức năng của ứng dụng.
5. **“Chỉ cần thêm bản dependency mới nhất.”** Sai: có thể tạo thêm xung đột nhị phân; phải tìm phiên bản tương thích với SDK, Boot BOM và các thư viện liên quan.
6. **“Log BeanCreationException chỉ là lỗi bean.”** Chưa đủ: mở chuỗi Caused by để tìm ClassNotFoundException, NoClassDefFoundError hoặc LinkageError thực sự.
7. **“Chạy được trong IDE thì JAR/Docker chắc chắn chạy được.”** Sai: IDE, test, executable JAR và container có thể dùng classpath, profile hoặc Java runtime khác nhau.

## 9. Checklist xử lý nhanh và tiêu chí kết luận

- [ ] Ghi **lỗi gốc**, FQCN hoặc signature cụ thể, thời điểm và môi trường phát sinh.
- [ ] Xác định **artifact sở hữu** class/method; kiểm tra JAR runtime có tồn tại và chứa class cần thiết.
- [ ] Xem dependency graph của **runtimeClasspath**, so với compileClasspath khi cần; truy đường dependency trực tiếp/bắc cầu, exclusions và scopes.
- [ ] Nếu thiếu JAR: phân loại **direct missing** hay **transitive missing** bằng quan hệ phụ thuộc; nếu JAR có mà method sai: kiểm tra **version/ABI**.
- [ ] Kiểm tra Java runtime, class loader và artifact thực triển khai; xác nhận BOOT-INF/lib nếu là Boot executable JAR.
- [ ] Dùng condition report để hiểu quyết định của @ConditionalOnClass; phân biệt “skip có chủ đích” với crash hoặc tính năng bắt buộc bị mất.
- [ ] Sửa dependency/scope/phiên bản theo nguyên nhân đã chứng minh; chạy lại tình huống thực tế và xác nhận lỗi gốc đã biến mất.

**Tự kiểm tra:** (1) SDK có mặt nhưng helper của SDK không được đóng gói — nguyên nhân nào? **Thiếu dependency bắc cầu**. (2) Helper.class có mặt nhưng SDK gọi method chỉ tồn tại trong Helper v1, còn runtime dùng v2 — nguyên nhân nào? **Sai phiên bản/ABI**. (3) @ConditionalOnClass không match cho SDK tùy chọn, ứng dụng vẫn chạy — có chắc là lỗi? **Không**; đó có thể là hành vi thiết kế. (4) NoClassDefFoundError: Could not initialize class ... có chứng minh thiếu JAR không? **Không**; phải tìm lỗi khởi tạo ban đầu.

Khi phân tích classpath cho Spring Boot, kết luận nên dựa trên **lớp/JAR thực nạp + đồ thị dependency runtime + dấu hiệu ABI + điều kiện auto-configuration**, không dựa duy nhất vào tên exception.