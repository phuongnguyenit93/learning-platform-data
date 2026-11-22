# Nashorn rời JDK từ Java 15: nhúng JavaScript phải cung cấp engine riêng

Từ **JDK 15**, ứng dụng Java không còn được bảo đảm có JavaScript engine Nashorn đi kèm bộ JDK. Những dòng mã đã quen thuộc trên Java 8–14, ví dụ `new ScriptEngineManager().getEngineByName("nashorn")`, có thể nhận **`null`** khi chuyển sang Java 15/17/21 trở lên mà ứng dụng chưa mang theo một scripting engine riêng.

Điều này **không có nghĩa Java đã xóa khả năng nhúng scripting**. API chuẩn **JSR-223 / `javax.script`** nằm trong module `java.scripting` vẫn có mặt. Thứ bị loại khỏi JDK là **triển khai Nashorn tích hợp sẵn, những API đặc thù của Nashorn và công cụ `jjs`**, không phải hợp đồng `ScriptEngine` dùng chung. Muốn đánh giá mã JavaScript trong tiến trình Java, ứng dụng phải **chọn, khai báo, đóng gói và cấu hình một engine độc lập**, sau đó kiểm tra khả năng khám phá engine khi khởi động.

Bài này giải thích chính xác thay đổi tại JDK 15 (JEP 372), cách phát hiện thiếu engine, cách thêm **Nashorn standalone** bằng Maven, các lựa chọn thay thế, tình huống JPMS/module path, rủi ro khi migration và các kiểm thử bắt buộc cho ứng dụng nhúng JavaScript.

## 1. Mốc phiên bản và phạm vi JEP 372

| Phiên bản Java | Trạng thái Nashorn trong JDK | Tác động đến ứng dụng |
| --- | --- | --- |
| **Java 8** | Nashorn được tích hợp vào JDK (JEP 174) | Thường có thể tìm JavaScript engine của JDK bằng `ScriptEngineManager` |
| **Java 9–10** | Nashorn vẫn có trong JDK | Engine còn tồn tại nhưng ứng dụng JPMS cần hiểu module/service discovery |
| **Java 11** | Nashorn và `jjs` được **đánh dấu deprecated for removal** theo JEP 335 | Có cảnh báo và phải lập kế hoạch thay thế; engine chưa bị xóa ở phiên bản này |
| **Java 12–14** | Nashorn tích hợp vẫn tồn tại, đang trên lộ trình bị xóa | Không nên xây kiến trúc dài hạn dựa vào engine bundled |
| **Java 15 trở lên** | JEP 372 **loại Nashorn tích hợp ra khỏi JDK** | Cần cung cấp implementation engine riêng nếu ứng dụng cần chạy JavaScript |

**JEP 372 – Remove the Nashorn JavaScript Engine** đưa ra các thay đổi cụ thể:

- Loại module JDK `jdk.scripting.nashorn`, gồm các gói API Nashorn trước đây như `jdk.nashorn.api.scripting` và `jdk.nashorn.api.tree`.
- Loại module shell `jdk.scripting.nashorn.shell` và công cụ dòng lệnh **`jjs`**.
- Không xóa `javax.script`, `ScriptEngineManager`, `ScriptEngine`, `ScriptEngineFactory` hay module **`java.scripting`**.

**Phân biệt quan trọng:** `jjs` là shell đi kèm Nashorn đã bị loại; không nên suy diễn mọi CLI của JDK hay toàn bộ công cụ Java scripting đã bị xóa. Nếu một công cụ Java còn cung cấp cách chạy script thông qua JSR-223, nó vẫn cần engine có thể khám phá được tại runtime.

Kết luận lịch sử: **“Nashorn rời JDK” khác với “dự án Nashorn ngừng tồn tại”**. Nhóm OpenJDK duy trì một bản **Nashorn standalone** độc lập để ứng dụng có thể tự thêm dependency, nhưng bản đó không tự xuất hiện chỉ vì bạn cài một JDK hiện đại.

## 2. Hai tầng cần hiểu: API chuẩn và engine implementation

Hình dung kiến trúc nhúng script:

~~~text
Java application / host
       |
       | javax.script (module java.scripting)
       v
ScriptEngineManager
       |
       | discovers ScriptEngineFactory via service-provider mechanism
       v
+-------------------------------+
| Third-party engine provider   |
| Nashorn standalone / GraalJS  |
| Rhino / another implementation|
+-------------------------------+
       |
       v
ScriptEngine.eval(...) -> JavaScript result
~~~

Phân vai:

- **`javax.script.ScriptEngine`:** hợp đồng đánh giá script, quản lý `Bindings`/`ScriptContext` và trả kết quả Java tương ứng. Không có JavaScript parser/compiler mặc định trong interface này.
- **`javax.script.ScriptEngineFactory`:** cung cấp tên, bí danh, ngôn ngữ, phiên bản, đặc tính và tạo `ScriptEngine`.
- **`ScriptEngineManager`:** tìm các `ScriptEngineFactory` mà môi trường runtime nhìn thấy bằng cơ chế service provider, rồi tạo engine theo tên/ngôn ngữ/file extension/MIME type. Manager **không tải dependency từ Maven hay Internet**.
- **Engine implementation:** thư viện độc lập thật sự phân tích và chạy JavaScript, phải nằm ở nơi JVM/class loader/module graph có thể phát hiện.
- **`java.scripting`:** module tiêu chuẩn của JDK chứa JSR-223, tiếp tục có trên Java 17. Khi viết explicit named Java module dùng `javax.script`, consumer cần `requires java.scripting;`.

Vì thế mã sau **vẫn biên dịch** trên Java 17:

~~~java
import javax.script.ScriptEngineManager;
ScriptEngineManager manager = new ScriptEngineManager();
~~~

Đây là *đoạn minh họa phải đặt bên trong class/method*, không phải file Java độc lập. Nhưng việc biên dịch thành công **không chứng minh** đã có `JavaScript` engine.

### 2.1. Trường hợp `getEngineByName` trả null

~~~java
ScriptEngine engine = new ScriptEngineManager().getEngineByName("nashorn");
~~~

Theo Javadoc, `getEngineByName` trả **`null` nếu không tìm thấy factory đăng ký tên được yêu cầu**. Các nguyên nhân thường gặp:

1. Không có JavaScript engine trong runtime.
2. Có thư viện trên disk nhưng **chưa nằm trên runtime classpath/module path**, hoặc module chưa được resolve.
3. Class loader được dùng để tìm provider không nhìn thấy `ScriptEngineFactory` của thư viện.
4. Engine có mặt nhưng **không đăng ký bí danh** `"nashorn"` mà ứng dụng dùng.
5. Lỗi trong việc nạp provider/dependencies dẫn tới khám phá không hoàn chỉnh; cần đọc log/exception liên quan.

Do đó, không nên bắt một `NullPointerException` xuất hiện ở `engine.eval(...)` rồi kết luận “Java 17 không hỗ trợ JavaScript”. Vấn đề ban đầu thường là **engine lookup không tìm thấy implementation**.

### 2.2. Tên `"JavaScript"` không phải engine bắt buộc

Ứng dụng đời cũ có thể viết:

~~~java
manager.getEngineByName("js");
manager.getEngineByName("JavaScript");
manager.getEngineByName("nashorn");
~~~

Các alias này phụ thuộc vào `ScriptEngineFactory.getNames()` của engine thực tế được cài. Không phải mọi implementation đều cung cấp cả ba tên. Nếu một engine có nhiều alias, mỗi alias có thể tìm được cùng loại engine; tuy nhiên không có quy tắc “JDK sẽ tự chọn JavaScript engine tốt nhất” khi không có provider phù hợp.

Hãy liệt kê `manager.getEngineFactories()`, đọc `factory.getNames()` và chọn tên đã được engine hỗ trợ. Trong production, nên **cố định provider/phiên bản mong muốn** và fail-fast khi không đáp ứng, thay vì âm thầm chạy script trên một engine khác có ngữ nghĩa không tương đương.

## 3. Ví dụ 1 — chẩn đoán trên JDK 17 không có JS engine

Tệp `EngineProbe.java` độc lập, chỉ cần JDK 17; **không thêm dependency JavaScript**:

~~~java
import javax.script.ScriptEngineManager;

public final class EngineProbe {
    public static void main(String[] args) {
        ScriptEngineManager manager = new ScriptEngineManager();
        System.out.println("factoryCount=" + manager.getEngineFactories().size());
        System.out.println("nashornFound=" + (manager.getEngineByName("nashorn") != null));
        System.out.println("javascriptFound=" + (manager.getEngineByName("JavaScript") != null));
    }
}
~~~

Biên dịch và chạy (JDK 17+):

~~~bash
javac --release 17 EngineProbe.java
java -cp . EngineProbe
~~~

Trên một bản **Corretto JDK 17.0.15 sạch, không bổ sung script engine**, kết quả đã kiểm chứng là:

~~~text
factoryCount=0
nashornFound=false
javascriptFound=false
~~~

**Đây là kết quả của môi trường kiểm chứng, không phải stdout bất biến của mọi JDK 17.** Nếu ứng dụng có GraalJS, Nashorn standalone hoặc provider khác trên classpath/module path, `factoryCount` có thể lớn hơn 0, một hoặc cả hai alias có thể tìm thấy engine. Chính sự khác nhau đó cho thấy `javax.script` là cơ chế **khám phá plug-in runtime**, không phải cam kết JDK luôn cung cấp implementation JavaScript.

Lệnh kiểm tra module Java Scripting có thể dùng:

~~~bash
java --list-modules
~~~

Tìm module `java.scripting` trong danh sách. Việc module này có mặt chỉ chứng minh **API JSR-223** còn tồn tại, không chứng minh một JavaScript engine đã được lắp.

## 4. Cung cấp engine riêng: các hướng lựa chọn

Tùy mục tiêu, có ba hướng phổ biến:

| Hướng | Phù hợp nhất khi | Điểm cần kiểm tra |
| --- | --- | --- |
| **OpenJDK Nashorn standalone** | Ứng dụng đang chạy script có cú pháp/hành vi Nashorn cũ, cần đường migration ít thay đổi | Tương thích runtime, `nashorn-core` và ASM dependencies, cú pháp JS đời cũ, các API Nashorn-specific đã đổi package |
| **GraalJS / GraalVM JavaScript** | Ứng dụng cần JavaScript hiện đại hoặc hệ sinh thái polyglot và host access được cấu hình rõ | Phải chọn đúng thư viện, phiên bản và JSR-223 adapter nếu còn dùng `ScriptEngine`; API/polyglot security khác Nashorn |
| **Rhino hoặc engine JSR-223 khác** | Hệ thống có ràng buộc compatibility/footprint riêng | Có thật sự cung cấp `ScriptEngineFactory` trong phiên bản đang dùng không; mức hỗ trợ ECMAScript và Java interop |

**Không có một “engine JavaScript chính thức mới” tự động thay Nashorn trong mọi bộ JDK**. Lựa chọn là quyết định của ứng dụng: kiểm tra license, lộ trình cập nhật bảo mật, tính tương thích script, độ tin cậy, khả năng chạy theo JDK hiện có và cách đóng gói khi deploy.

Với dự án có nhiều script Nashorn cũ, dùng Nashorn standalone có thể là một bước chuyển tiếp. Với dự án mới, nên đánh giá một engine được duy trì và mức ECMAScript cần hỗ trợ, kể cả khả năng dùng API polyglot chuyên dụng thay vì buộc mọi use case vào JSR-223.

## 5. Ví dụ 2 — thêm Nashorn standalone thật sự bằng Maven

Dự án OpenJDK cung cấp artifact Maven **`org.openjdk.nashorn:nashorn-core`**, không phải module Nashorn từng được ship trong JDK. Tại thời điểm bài này dùng phiên bản đã đối chiếu từ dự án OpenJDK và Maven Central là **`15.7`**. Version trong ví dụ được **pin rõ ràng** để có thể build lại; khi dùng production cần theo dõi release và kiểm thử nâng cấp theo quy trình dependency của dự án.

### 5.1. Cấu trúc dự án

~~~text
embedded-js/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── EmbeddedJs.java
~~~

### 5.2. Tệp pom.xml đầy đủ

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>training.demo</groupId>
    <artifactId>embedded-js</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.openjdk.nashorn</groupId>
            <artifactId>nashorn-core</artifactId>
            <version>15.7</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tại sao không chỉ tải `nashorn-core.jar` rồi thêm một file vào classpath? Artifact Nashorn phụ thuộc **các thư viện ASM** dùng cho xử lý/generating bytecode; Maven giải quyết các dependencies transitively. Chỉ mang một JAR khi chạy thủ công dễ phát sinh `NoClassDefFoundError` hoặc lỗi khởi tạo. Maven/Gradle giúp đóng gói toàn bộ dependency graph có thể kiểm tra.

### 5.3. Tệp Java đầy đủ

`src/main/java/demo/EmbeddedJs.java`:

~~~java
package demo;

import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;

public final class EmbeddedJs {
    public static void main(String[] args) throws ScriptException {
        ScriptEngineManager manager = new ScriptEngineManager();
        ScriptEngine engine = manager.getEngineByName("nashorn");
        if (engine == null) {
            throw new IllegalStateException("Nashorn provider is missing");
        }
        System.out.println("nashornAvailable=" + (engine != null));
        Object result = engine.eval("function doubleIt(x) { return x * 2; } doubleIt(21);");
        System.out.println("result=" + ((Number) result).intValue());
    }
}
~~~

**Giải thích thiết kế:**

- Code Java chỉ import **API `javax.script` tiêu chuẩn**. Không hardcode class nội bộ của Nashorn, nên adapter Java này dễ thay đổi engine hơn.
- Dependency Maven đưa một implementation của `ScriptEngineFactory` vào runtime. `ScriptEngineManager` tra tên `nashorn` và lấy một `ScriptEngine`.
- Nếu không tìm được provider, `IllegalStateException` báo thiếu engine ngay tại điểm cấu hình, thay vì gây lỗi null về sau.
- Script JavaScript đơn giản được chọn để chạy trên Nashorn (nó không cần cú pháp ECMAScript hiện đại).
- `eval` trả `Object`. Ví dụ lấy `Number.intValue()` thay vì ép thẳng sang `Integer` để tránh giả định kiểu wrapper cụ thể.
- Đây là **ví dụ nhúng script đã được kiểm chứng**, không phải cách chạy mã JavaScript từ người dùng chưa tin cậy trong production.

### 5.4. Chạy Maven với Java 17

Từ thư mục `embedded-js`:

~~~bash
mvn -q -DskipTests compile
mvn -q exec:java '-Dexec.mainClass=demo.EmbeddedJs'
~~~

Lệnh thứ hai cho phép Maven dựng runtime classpath bao gồm các dependency. Trong PowerShell, việc đặt toàn bộ tham số `-Dexec.mainClass=...` trong dấu nháy đơn cũng giúp tránh sai cách tách tham số qua shell.

Stdout của chương trình sau khi Maven khởi động ứng dụng:

~~~text
nashornAvailable=true
result=42
~~~

Ví dụ đã được **biên dịch và chạy trên Amazon Corretto JDK 17.0.15** với dependency `nashorn-core:15.7`; kết quả ở trên khớp chính xác. Build cần Maven và quyền truy cập artifact (hoặc dependency đã có trong cache nội bộ).

**Nếu viết file bằng Windows PowerShell 5.1:** `Set-Content -Encoding UTF8` có thể ghi UTF-8 BOM vào đầu tệp `.java`, làm `javac` báo ký tự BOM không hợp lệ. Nên dùng IDE/editor ghi UTF-8 không BOM hoặc cách ghi file phù hợp; lỗi encoding này **không liên quan đến việc thiếu JavaScript engine**.

### 5.5. Tại sao bản standalone cần quản lý riêng?

Từ Java 15, bản JDK không còn là nơi bảo đảm phiên bản Nashorn, ASM dependencies hoặc cập nhật của nó. Vì vậy đội ngũ vận hành phải:

1. Khai báo dependency ở build và runtime, không chỉ lúc compile.
2. Pin version, ghi nhận SBOM, license và quy trình theo dõi bản vá.
3. Test trên đúng JDK/JRE thực tế dùng deploy; không suy từ `java -version` rằng engine sẽ có.
4. Đóng gói tất cả transitive dependencies trong container, fat JAR hoặc distribution tương ứng.
5. Nếu dùng JPMS/module path, xử lý module resolution và phụ thuộc ASM cùng module của Nashorn đúng cách.

## 6. Đặt engine trên classpath hay module path trong JPMS?

### 6.1. Ứng dụng trên classpath

Ví dụ Maven phía trên là ứng dụng chạy trên classpath. `ScriptEngineManager` sử dụng cơ chế service provider để tìm các `ScriptEngineFactory` mà class loader liên quan có thể nhìn thấy. Runtime classpath do Maven plugin tạo chứa `nashorn-core` và transitive dependencies, nên việc tìm provider thành công.

Không nên chỉ kiểm tra xem JAR tồn tại trên ổ đĩa. Sự tồn tại của file JAR **khác** với việc class loader dùng cho script engine lookup thực sự nhìn thấy JAR và service metadata.

Nếu hệ thống container có nhiều class loader, `new ScriptEngineManager()` mặc định dựa vào **thread context class loader** để khám phá factories. Khi gặp hiện tượng test đơn lẻ chạy nhưng app server/plugin host báo thiếu engine, cần kiểm tra context loader, loader của provider và module graph. API `new ScriptEngineManager(ClassLoader)` giúp đưa loader cụ thể vào discovery khi phù hợp.

### 6.2. Ứng dụng explicit named module

Module consumer dùng `javax.script` khai báo:

~~~java
module embedded.host {
    requires java.scripting;
}
~~~

Đây là **module-info.java minh họa**. Nếu engine module và các module ASM được đặt trên module path, chúng phải **được resolve** và service provider phải được nhìn thấy trong graph. Nashorn standalone có tên JPMS là **`org.openjdk.nashorn`** (khác module cũ `jdk.scripting.nashorn`).

Theo hướng dẫn của dự án OpenJDK, cần đưa Nashorn standalone và **các phụ thuộc bắc cầu** của nó vào module path hoặc một `ModuleLayer` phù hợp. Với từng cấu hình launcher, có thể cần đưa engine module vào danh sách root modules hoặc dùng cơ chế service binding thích hợp. Ví dụ tùy chọn khi phân phối theo module path:

~~~bash
java --module-path libs --add-modules org.openjdk.nashorn -m embedded.host/demo.EmbeddedJs
~~~

**Đây là sơ đồ lệnh phụ thuộc vào cách đóng gói, không phải lệnh đã chạy cho dự án Maven classpath ở mục 5**: `libs` phải chứa module/JAR của Nashorn và dependencies, `embedded.host` phải được biên dịch thực sự thành named module và có mặt trên module path. Không chép lệnh đó vào dự án classpath ở trên rồi kỳ vọng chạy ngay. Phương thức phổ quát là kiểm tra resolved modules, provider factories và chạy integration test trong đúng môi trường đóng gói.

Trong custom runtime image tạo bằng `jlink`, API `java.scripting` phải được giữ nếu host dùng nó, và engine cùng modules phụ thuộc phải có trong image hoặc được phân phối phù hợp. Không suy rằng `jlink` tự đưa một scripting engine vào image chỉ vì `java.scripting` được đưa vào.

### 6.3. Trường hợp dùng ScriptEngineFactory trong hệ plugin

Một engine provider có thể nằm trong plugin loader thay vì class loader của host. Nếu host gọi:

~~~java
new ScriptEngineManager().getEngineByName("nashorn");
~~~

nhưng context loader không thấy provider, kết quả vẫn có thể là `null`. Thay đổi alias nhiều lần không sửa được vấn đề visibility. Cách chẩn đoán:

- Quan sát `Thread.currentThread().getContextClassLoader()`.
- Liệt kê `getEngineFactories()` của manager dùng loader mong muốn.
- Kiểm tra module providers đã được resolve và dependency không bị thiếu.
- Nếu host/engine giao tiếp qua interface, xác nhận cả hai dùng **cùng identity** của `javax.script.ScriptEngineFactory` và các SPI types.
- Không trao cho plugin tự tiện chọn class loader hoặc cung cấp script với host privileges nếu không có chính sách trust.

## 7. Migration các ứng dụng dùng API Nashorn đặc thù

Dùng lại `javax.script` càng nhiều càng tốt, nhưng việc chuyển engine không chỉ là thay một tên dependency.

| Loại code cũ | Vấn đề sau JDK 15 | Hướng xử lý |
| --- | --- | --- |
| `getEngineByName("nashorn")` và giả định chắc có engine | Trả null nếu không có provider | Add dependency runtime; verify factory name và fail-fast |
| Import `jdk.nashorn.api.scripting.*` | Nashorn-specific API trong JDK đã bị xóa | Nếu chọn Nashorn standalone, kiểm tra API đổi sang `org.openjdk.nashorn.api.scripting`; nếu đổi engine, thiết kế adapter mới |
| Dùng công cụ `jjs` để chạy script/build | `jjs` đã bị gỡ | Viết launcher riêng dùng engine đã chọn hoặc dùng công cụ của vendor mới |
| Dùng `Java.type`, `Java.extend`, `Packages`, Java bridge đặc thù | Khả năng tương thích và kiểm soát host interop khác nhau theo engine | Kiểm tra script thực tế, refactor bridge, cấu hình host access rõ ràng |
| Dùng cú pháp JavaScript quá mới | Nashorn standalone không nhất thiết tương thích toàn bộ ECMAScript hiện đại | Xác định dialect/feature matrix, test từng script hoặc chọn runtime JS phù hợp |
| Phụ thuộc vào kiểu trả về `ScriptEngine.eval` cụ thể | Number/object/mapping có thể khác giữa engines | Dùng hợp đồng data conversion rõ ràng, không cast tùy tiện |
| Dùng Nashorn-specific sandbox/filter tùy biến | Thay engine có mô hình quyền truy cập khác | Review chính sách bảo mật từ đầu, không coi thiết lập cũ tự tương đương |
| Chạy script trong nhiều thread trên cùng engine | `ScriptEngine` không mặc định thread-safe | Kiểm tra `ScriptEngineFactory.getParameter("THREADING")` và quản lý instance/state |

API tương thích `javax.script` chỉ giúp host có **hợp đồng Java chung**. Nó **không cam kết** hai engine giống nhau về cú pháp JS, kiểu biến, Java interoperability, object lifecycle, security policy, encoding, locale/timezone, Promise/async hay kết quả serialization.

### 7.1. Đừng xóa lỗi bằng fallback ngầm

Một pattern không nên dùng:

~~~java
ScriptEngine engine = manager.getEngineByName("nashorn");
if (engine == null) {
    engine = manager.getEngineByName("JavaScript");
}
// Không xác nhận đã chọn engine gì và nó tương thích hay không.
~~~

Đây là **đoạn minh họa cách làm rủi ro**, không phải chương trình chạy độc lập. Nếu alias thứ hai trỏ một engine có khác biệt ngữ nghĩa, kết quả business có thể sai mà không báo lỗi.

Tốt hơn là xác định rõ policy: “chỉ hỗ trợ Nashorn standalone 15.7” hoặc “hỗ trợ GraalJS bản đã xác minh” rồi kiểm tra `getEngineFactories()`, engine name/version và chạy smoke test trước khi nhận request.

### 7.2. Khi dùng GraalJS

GraalJS có adapter **JSR-223** được phân phối riêng. Không phải cứ cài một JDK mang thương hiệu GraalVM là chắc chắn `ScriptEngineManager.getEngineByName("JavaScript")` luôn hoạt động trong mọi thế hệ sản phẩm: các bản GraalVM mới yêu cầu thêm **`js-scriptengine`** riêng khi dùng adapter. Nếu xây ứng dụng mới, tài liệu GraalJS khuyến nghị cân nhắc API **`org.graalvm.polyglot.Context`** để điều khiển quyền truy cập và lifecycle tốt hơn. Đừng sao chép cấu hình interop/sandbox của Nashorn sang GraalJS mà không kiểm chứng các đặc tính mới.

## 8. Quản lý Bindings, state và vòng đời khi nhúng script

Không nên dừng kiểm thử ở “engine tìm thấy và tính được `21 * 2`”. Khi script được nhúng vào host thật, cần xem xét:

- **Bindings:** `ScriptEngine` có `ENGINE_SCOPE`/`GLOBAL_SCOPE`; dữ liệu đưa vào có thể được script nhìn thấy. `manager.put(...)` thiết lập global scope trên manager cho những engine nó tạo ra. Không đặt secrets/objects quyền cao vào global bindings một cách tùy tiện.
- **Cách ly phiên:** mỗi request/tenant nên có context/bindings riêng nếu script được phép sửa biến. Reuse engine chỉ khi hiểu hợp đồng thread safety và state isolation của implementation.
- **Ownership:** nếu engine/factory tạo thread, context, cache hoặc tài nguyên native, host phải thiết kế cleanup theo API thực tế của vendor. `javax.script.ScriptEngine` không có phương thức `close()` chuẩn.
- **Timeout/cancellation:** `ScriptEngine.eval` không bảo đảm cơ chế timeout hoặc dừng an toàn trên mọi engine. Không coi `Future.cancel(true)` là cách chắc chắn ngắt một script vô hạn. Chọn runtime/kiến trúc có giới hạn tài nguyên phù hợp, hoặc cô lập trong process nếu chạy code không tin cậy.
- **Exception:** `eval` có thể ném `ScriptException` do syntax/runtime evaluation; lỗi cấu hình provider thường xảy ra sớm hơn khi discovery/khởi tạo. Ghi log riêng **engine missing**, **script failure** và **resource exhaustion**.
- **Kết quả:** interface trả `Object`; dùng chuyển đổi giá trị tường minh, kiểm tra `null`, dải số, encoding và JSON nếu dữ liệu đi qua biên giới hệ thống.

Ví dụ dùng bindings theo một lần đánh giá (đoạn minh họa đặt trong code đã có `engine`):

~~~java
javax.script.Bindings vars = engine.createBindings();
vars.put("base", 10);
Object result = engine.eval("base + 5", vars);
~~~

Không nên chia sẻ cùng `Bindings` có thể chỉnh sửa cho nhiều user/tenant. Với dữ liệu và object host đưa vào script, bảo đảm chỉ cấp đúng tính năng cần thiết. Cơ chế injection kiểu script variable **không giống** hệ dependency injection và không tự cô lập object Java nguy hiểm.

## 9. Bảo mật: đừng coi Nashorn hay JSR-223 là sandbox

Chạy JavaScript nhúng **trong cùng JVM** có thể dẫn đến quyền truy cập vào object và capability mà host cung cấp. Những tính năng Java interop của engine cũ có thể cho phép script gọi API Java mà ứng dụng không lường trước nếu không cấu hình chặn. Việc một engine bị gỡ khỏi JDK là vấn đề dependency/migration, **không phải** lý do bỏ qua kiểm tra bảo mật.

Đối với script không tin cậy:

1. **Không chạy trực tiếp mã script tùy ý của người dùng** trong JVM phục vụ các quyền nghiệp vụ quan trọng nếu chưa có threat model, chính sách host access và giới hạn runtime được chứng minh.
2. Giới hạn hoặc vô hiệu Java host interop theo khả năng của engine được chọn; không coi một cấu hình generic `javax.script` là đủ để khóa engine.
3. Giới hạn CPU, memory, thời gian, I/O, network và số job; những giới hạn này thường cần cơ chế ngoài `ScriptEngine`.
4. Nếu dùng chung process, giảm quyền hệ điều hành của process và tránh đưa credentials/secret/handle vào bindings.
5. Với mức tin cậy thấp, cân nhắc chạy script trong **process/container độc lập** có quota, giao tiếp qua IPC/API và chấp nhận chi phí cô lập.
6. Cập nhật engine và thư viện ASM/transitive theo quy trình dependency security; Java runtime được vá không tự bảo đảm Nashorn standalone đang ở bản an toàn.

Đối với automation nội bộ có script tin cậy, vẫn nên áp dụng code review, danh sách script được phép chạy, logging, versioning và resource limits. Chạy bằng JSR-223 không tạo ra “vùng an toàn” chỉ bằng việc chuyển đổi ngôn ngữ.

## 10. Checklist chẩn đoán khi nâng Java 8/11 lên 17+

Nếu một hệ thống gặp `NullPointerException` tại `engine.eval(...)` hoặc log “Nashorn not found”, kiểm tra có thứ tự:

| Bước | Cần quan sát | Cách sửa đúng |
| --- | --- | --- |
| 1. Java version | `java -version` thực tế của process | Xác định có thuộc Java 15+ và image bị tối giản không |
| 2. API presence | Module `java.scripting`; code `javax.script` compile không | Nếu dùng custom jlink image, đưa API cần thiết vào runtime |
| 3. Factory discovery | `new ScriptEngineManager().getEngineFactories()` | Không có factory thì kiểm tra dependency/class loader/module graph |
| 4. Engine names | `factory.getNames()`, `getEngineName()`, `getEngineVersion()` | Dùng tên nhà cung cấp thực sự quảng bá; tránh alias đoán mò |
| 5. Runtime dependency | Maven dependency tree, packaged JAR, ASM transitive | Đảm bảo engine **tồn tại lúc chạy**, không chỉ lúc compile/test |
| 6. Class loader | TCCL, web container/plugin loader, `ScriptEngineManager(loader)` | Đảm bảo provider metadata nhìn thấy từ loader khám phá |
| 7. JPMS resolution | module path, service provider module, parent/child layer | Resolve module engine đúng cách, không chỉ copy JAR vào directory |
| 8. Script compatibility | syntax, native object, API JS–Java, return values | Chạy regression suite bằng đúng engine phiên bản pin |
| 9. Trust and limits | Host access, bindings, concurrency, timeout, data isolation | Thiết kế sandbox/process isolation và lifecycle đúng mức |
| 10. Deployment parity | CI, container, IDE, staging, production | Chạy smoke test engine discovery/eval ở môi trường cuối cùng |

Đặc biệt, một IDE có thể đưa thư viện engine lên classpath lúc chạy test nhưng fat JAR/container production lại bỏ sót vì cấu hình packaging. Mọi đường deploy phải chạy cùng một integration test.

### 10.1. Smoke test nên làm gì?

Một smoke test có giá trị phải xác nhận:

- Factory mong muốn **được khám phá**, có name/version nằm trong danh sách được chấp thuận.
- `getEngineByName(...)` trả non-null.
- Một script nhỏ dùng đúng cú pháp và API interop của hệ thống thực tế **chạy được**.
- Kết quả data conversion đúng (number/string/list/JSON), không chỉ không ném exception.
- Trường hợp **engine absent** phải fail-fast với thông báo rõ ràng.
- Các script chính có regression tests khi nâng version JVM/engine.
- Các trường hợp script lỗi và script chạy lâu được xử lý theo chính sách resource/lifecycle.

Ví dụ smoke test ở mục 5 in `nashornAvailable=true` và `result=42`; bài kiểm tra đó chứng minh cách đóng gói Maven đã đem engine tới runtime, **không** tự chứng minh toàn bộ business scripts hay cấu hình bảo mật đều tương thích.

### 10.2. Những lỗi phổ biến và cách phân biệt

**`getEngineByName(...) == null`:** chưa tìm thấy factory cho alias. Kiểm tra dependency runtime, class loader, module resolution và `factory.getNames()`. Không gọi `eval` trên null.

**`ClassNotFoundException` hoặc `NoClassDefFoundError`:** thư viện engine/transitive dependency không nằm trên runtime path hoặc có xung đột loading. Kiểm tra Maven dependency tree và cách đóng gói, không chỉ thêm `requires java.scripting`.

**`ScriptException`:** engine đã được tạo nhưng script có lỗi cú pháp/đánh giá. Kiểm tra engine dialect, script, bindings và nội dung exception; không gán nhầm cho JEP 372.

**`IllegalAccessException` / `InaccessibleObjectException`:** script hoặc engine cố reflective access vào API Java bị JPMS encapsulation. Không dùng `--add-opens=ALL-UNNAMED` tràn lan; chỉ mở đúng package/target khi đã kiểm tra rủi ro và lựa chọn engine phù hợp.

**`ClassCastException` sau `eval`:** kết quả Java wrapper/vendor object không có kiểu như code mong đợi. Kiểm tra `result.getClass()` và chuyển đổi theo hợp đồng tường minh.

**Không thể gọi `jjs`:** công cụ đã rời JDK. Đây là lỗi khác với việc `ScriptEngineManager` không tìm thấy engine; phải thay workflow CLI/build nếu vẫn dùng `jjs`.

## 11. Hướng migration đề xuất cho ứng dụng nhúng hiện hữu

Lộ trình ít rủi ro:

1. **Inventory** mọi nơi sử dụng `ScriptEngineManager`, `ScriptEngine`, `Invocable`, `Compilable`, `jjs` và API `jdk.nashorn.*`; liệt kê script được chạy và loại dữ liệu trao đổi.
2. **Chọn engine** theo yêu cầu tương thích và trust. Nếu dùng Nashorn standalone, khai báo dependency như mục 5; nếu chuyển GraalJS/Rhino, lập feature matrix và thay host-interop adapters.
3. **Cô lập tại một lớp adapter** chịu trách nhiệm tạo engine, đọc factory metadata, fail-fast, chuyển đổi giá trị, quản lý context/bindings, lifecycle và error reporting. Không để business code khắp nơi tự `new ScriptEngineManager()` rồi đoán tên provider.
4. **Pin và test version** engine/dependencies song song với JDK target (ví dụ Java 17); dùng compiler release target tương ứng.
5. **Kiểm thử script thực tế**: syntax, Unicode, number handling, exceptions, async/timer, Java bridge, reflection, host objects và serialization.
6. **Cấu hình deployment**: Maven dependency graph, fat JAR/container image, class loader visibility, module path/layer và jlink runtime nếu có.
7. **Thử nhánh thất bại** engine bị thiếu hoặc không được resolve; kết quả phải là lỗi cấu hình dễ hiểu, không phải NPE tại điểm xử lý nghiệp vụ.
8. **Đánh giá bảo mật** trước khi mở script cho user/tenant hoặc cho phép bridge tới Java. Đặt giới hạn tài nguyên và chính sách input/output.
9. **Phát hành có quan sát**: log engine name/version, tỷ lệ `ScriptException`, thời gian/chỉ số tài nguyên chạy script và khả năng rollback khi engine version mới khác hành vi.

Việc JDK 15 loại Nashorn là một thay đổi **đóng gói trách nhiệm của platform**: ứng dụng nhúng script phải sở hữu rõ dependency và policy thay vì dựa vào một implementation ngầm định bên trong JDK.

## 12. Ghi nhớ nhanh

~~~text
JDK 8–14:
    java.scripting / javax.script API  +  Nashorn bundled (JDK)
                                            |
                                            +-- getEngineByName("nashorn") thường có engine

JDK 15+:
    java.scripting / javax.script API  +  KHÔNG có Nashorn bundled
                                            |
                                            +-- getEngineByName("nashorn") có thể null
                                            |
                                            +-- cung cấp engine độc lập tại runtime
                                                    |
                                                    +-- Nashorn standalone
                                                    +-- GraalJS adapter
                                                    +-- Rhino / provider khác
                                                    |
                                                    +-- test discovery, eval, packaging
~~~

**Nguyên tắc kết luận:** từ Java 15, **muốn nhúng JavaScript thì ứng dụng phải tự bảo đảm có một engine implementation phù hợp ở runtime**. `javax.script` vẫn tồn tại như một SPI; `ScriptEngineManager` có thể **tìm** engine đã được đăng ký, nhưng **không phải bản thân engine**. Hãy khai báo dependency, xác minh visibility và phiên bản, fail-fast nếu thiếu, kiểm thử script thực tế và quản lý an toàn dữ liệu/host access.

### Nguồn tài liệu đối chiếu

- [JEP 372 – Remove the Nashorn JavaScript Engine](https://openjdk.org/jeps/372): phạm vi loại bỏ và xác nhận API `javax.script` không bị ảnh hưởng.
- [JEP 335 – Deprecate the Nashorn JavaScript Engine](https://openjdk.org/jeps/335): giai đoạn deprecated for removal từ Java 11.
- [Java SE 17 – ScriptEngineManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html): service-provider discovery, factory names, `getEngineByName` và trường hợp không có engine.
- [OpenJDK Nashorn standalone](https://github.com/openjdk/nashorn): module độc lập, dependency graph, Java 11+, hướng dẫn chạy trên JPMS.
- [Maven Central – nashorn-core](https://central.sonatype.com/artifact/org.openjdk.nashorn/nashorn-core): tọa độ dependency và phiên bản 15.7 đã dùng trong ví dụ.
- [GraalVM JavaScript embedding / ScriptEngine](https://www.graalvm.org/jdk17/reference-manual/js/RhinoMigrationGuide/): hướng migration và adapter JSR-223.
