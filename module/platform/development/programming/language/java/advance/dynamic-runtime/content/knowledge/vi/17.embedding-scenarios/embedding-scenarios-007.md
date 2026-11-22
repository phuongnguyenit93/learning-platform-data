# 17.7. Nashorn đã bị loại khỏi JDK: khai báo rõ engine ngoài khi xây ví dụ

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định chính xác mốc **Nashorn bị deprecated for removal từ JDK 11 và bị loại khỏi JDK kể từ JDK 15**, trong khi API chuẩn `javax.script` / module `java.scripting` **không bị loại bỏ** bởi quyết định đó.
2. Hiểu vì sao `new ScriptEngineManager().getEngineByName("JavaScript")` hoặc `getEngineByName("nashorn")` **có thể trả `null` trên Java 17+** và vì sao việc chạy được JVM không chứng minh có JavaScript engine.
3. Phân biệt **JSR 223 API** với **một engine implementation cụ thể**; mô tả cơ chế `ScriptEngineFactory`, `ServiceLoader`, tên alias, class loader và module path.
4. Viết ví dụ Java 17+ có **dependency được khai báo rõ ràng**: `org.openjdk.nashorn:nashorn-core:15.7`, không giả vờ đây là thành phần mặc định của JDK 17.
5. Chạy cùng một chương trình với và không có external engine; kiểm tra điều kiện `engine == null`, truyền `Bindings`, gọi `eval` và `Invocable` đúng cách.
6. Nhận biết lựa chọn khác như **GraalJS** (dependency bên ngoài, có thể dùng `ScriptEngine` hoặc `org.graalvm.polyglot.Context`) và giới hạn tương thích của cú pháp/API khi chuyển engine.
7. Thiết kế ví dụ/bài test đúng môi trường triển khai, module graph và vấn đề bảo mật khi chạy script không tin cậy.

**Phạm vi:** Chủ đề nằm trong chương **17. Kịch bản nhúng**, tập trung vào khả năng cung cấp **script engine** và cách khai báo dependency cho ví dụ. Không coi một JDK hiện đại là môi trường đã tích hợp JavaScript engine. Ví dụ minh họa chính dùng **Nashorn độc lập với JDK**, không phải Nashorn tích hợp đã bị loại bỏ.

## 1. Đính chính quan trọng: Nashorn của JDK đã bị loại bỏ

Nashorn từng là một JavaScript engine được đóng gói trong JDK, xuất hiện từ Java 8. Nó cung cấp:
- implementation của **`javax.script.ScriptEngine`** để chạy JavaScript;
- những API riêng thuộc `jdk.nashorn.api.scripting` và các package Nashorn;
- công cụ `jjs` để chạy script từ dòng lệnh.

Lịch sử cần nhớ:

| Phiên bản Java | Trạng thái của Nashorn được đóng gói trong JDK |
| --- | --- |
| JDK 8–10 | Nashorn tích hợp sẵn trong các bản JDK có tính năng này. |
| JDK 11–14 | Nashorn tích hợp đã **deprecated for removal** theo JEP 335; dùng nó đồng nghĩa phụ thuộc một engine sắp biến mất. |
| **JDK 15 trở đi** | **JEP 372 đã loại bỏ** engine tích hợp, các Nashorn-specific APIs và `jjs` khỏi JDK. |
| Java 17+ | **Không được giả định** có Nashorn hoặc một JavaScript `ScriptEngine` mặc định; muốn chạy JavaScript phải cung cấp engine phù hợp từ ngoài. |

**JEP 372 không loại bỏ `javax.script`.** JSR 223 là một API chung để nhúng **nhiều ngôn ngữ scripting**, không chỉ JavaScript. Module `java.scripting` và các interface chuẩn vẫn có mặt trong những JDK/runtime images có chứa module ấy; điều bị loại bỏ là implementation Nashorn **được phát hành cùng JDK**.

Sơ đồ:

```text
Trước JDK 15 (một JDK có Nashorn tích hợp):
  java.scripting / javax.script API
          |
          +-- ScriptEngineManager
                  |
                  +-- Nashorn JDK provider -> chạy JavaScript

JDK 17+ không thêm engine:
  java.scripting / javax.script API
          |
          +-- ScriptEngineManager
                  |
                  +-- Không thấy JavaScript provider -> trả null

JDK 17+ có dependency engine bên ngoài:
  java.scripting / javax.script API
          |
          +-- ScriptEngineManager
                  |
                  +-- Standalone Nashorn / GraalJS provider -> chạy script
```

Lưu ý: Một **custom runtime image** do `jlink` tạo còn có thể thiếu cả module `java.scripting`. Khi đó chương trình trực tiếp tham chiếu `javax.script` có thể không khởi động/load được. Đây là trạng thái **khác** với “API có mặt nhưng không tìm thấy JavaScript engine”.

### 1.1. Những câu khẳng định sai cần tránh trong bài học

Sai:

```java
ScriptEngine engine =
        new ScriptEngineManager().getEngineByName("JavaScript");
Object result = engine.eval("1 + 2"); // Có thể NullPointerException.
```

Đây là **phản ví dụ**, giả định đã import `javax.script.*` và thực hiện trong method có xử lý `ScriptException`. Không có engine JavaScript nào được khai báo hoặc cài đặt; code có thể compile nhưng thất bại khi chạy vì `engine == null`.

Sai:
- “JDK 17 có Nashorn mặc định, không cần dependency.”
- “`javax.script` còn tồn tại nên JavaScript chắc chắn chạy được.”
- “Chỉ cần thêm `requires java.scripting` là có Nashorn.”
- “Mọi ScriptEngine đều là JavaScript engine.”
- “Có lệnh `java` nghĩa là hệ thống có engine `jjs`.”

Đúng: **Khai báo rõ engine cụ thể**, phiên bản, cách đưa nó vào runtime classpath/module path, cách tìm đúng tên engine và xử lý thiếu provider.

## 2. API và implementation là hai tầng riêng

JSR 223 nằm trong package `javax.script`, thuộc module `java.scripting`:

| Thành phần | Vai trò |
| --- | --- |
| `ScriptEngineManager` | Khám phá factories, đăng ký alias, tạo ScriptEngine theo tên/extension/MIME type. |
| `ScriptEngineFactory` | Mô tả engine name, aliases, language name/version và cách khởi tạo engine. |
| `ScriptEngine` | Interface chung để `eval` source và làm việc với `Bindings`/`ScriptContext`. |
| `Bindings` | Bảng giá trị từ host Java đưa vào script scope. |
| `ScriptException` | Lỗi do đánh giá script hoặc các lỗi engine báo thông qua JSR 223. |
| `Invocable` | Capability tùy engine để Java gọi hàm/method do script định nghĩa. |
| `Compilable` | Capability tùy engine để compile script trước, nếu provider hỗ trợ. |
| `CompiledScript` | Biểu diễn script đã compile theo `Compilable`, dùng lại khi phù hợp. |

**Không có class nào trong bảng là một JavaScript engine implementation.** `ScriptEngineManager` không tự thông dịch cú pháp JavaScript; nó cần tìm được một `ScriptEngineFactory` cung cấp implementation từ runtime.

### 2.1. Engine được tìm như thế nào?

Tạo manager:

```java
ScriptEngineManager manager = new ScriptEngineManager();
ScriptEngine engine = manager.getEngineByName("nashorn");
```

Đây là đoạn minh họa trong method có import `javax.script.ScriptEngineManager` và `javax.script.ScriptEngine`.

Theo Java SE 17 API:
- `ScriptEngineManager` dùng **cơ chế service provider** (dựa trên `ServiceLoader`) để phát hiện các `ScriptEngineFactory` nhìn thấy được qua class loader phù hợp.
- Constructor không đối số tương đương với dùng **thread context class loader** của thread hiện tại. Vì thế class loader trong ứng dụng plugin/container ảnh hưởng kết quả discovery.
- `getEngineByName(shortName)` so tên với các alias mà factory khai báo và có thể trả **`null` khi không có factory phù hợp**.
- `getEngineByExtension("js")` và `getEngineByMimeType("application/javascript")` là các cách chọn khác, nhưng **cũng có thể null**.
- `getEngineFactories()` trả danh sách factories được phát hiện, hữu ích khi debug classpath/module path.

Không nên giả định chuỗi `"JavaScript"` hay `"js"` luôn trỏ đến cùng implementation. Khi có nhiều providers, alias có thể trùng; chọn tên provider rõ ràng hoặc cấu hình/khởi tạo factory cụ thể nếu yêu cầu tính nhất quán nghiêm ngặt.

### 2.2. Chẩn đoán providers trước khi đánh giá script

```java
ScriptEngineManager manager = new ScriptEngineManager();

for (ScriptEngineFactory factory : manager.getEngineFactories()) {
    System.out.println(factory.getEngineName());
    System.out.println(factory.getEngineVersion());
    System.out.println(factory.getLanguageName());
    System.out.println(factory.getNames());
}

ScriptEngine engine = manager.getEngineByName("nashorn");
if (engine == null) {
    throw new IllegalStateException(
            "External Nashorn engine missing from runtime classpath/module path");
}
```

Đây là **đoạn minh họa** trong method, cần import `ScriptEngineFactory`, `ScriptEngineManager`, `ScriptEngine`. Không có stdout cố định cho phần duyệt factories: kết quả phụ thuộc vào **providers thực sự có trong tiến trình**, JDK, dependencies và class loader.

Một `ScriptEngineFactory` được tìm thấy không chứng minh engine đó hỗ trợ đầy đủ mọi cú pháp JavaScript, `Invocable`, `Compilable` hay chính sách host interoperability mà ứng dụng cần. Phải kiểm thử các tính năng thực.

### 2.3. Maven dependency ở build-time chưa đủ nếu runtime bị loại bỏ

Maven/Gradle có thể compile code dùng `javax.script` ngay cả khi không có provider. Nếu bỏ runtime artifact khỏi gói deploy, `ScriptEngineManager` có thể trở lại `null`.

Kiểm tra:
1. `pom.xml` hoặc Gradle dependencies có **engine artifact** (không chỉ API).
2. Maven scopes không vô tình là `test` hoặc `provided` nếu production cần engine.
3. Deploy artifact/runtime classpath thực sự bao gồm engine và **transitive dependencies**.
4. Nếu dùng JPMS module path, module provider đã được **resolve** trong module graph.
5. Thread context class loader nhìn thấy service provider, hoặc manager được tạo với loader có thể nhìn thấy provider.
6. Chạy một script nhỏ trên **đúng runtime image/container cuối**, không chỉ trong IDE.

## 3. Lựa chọn cho Java 17+: standalone Nashorn bên ngoài JDK

OpenJDK duy trì **standalone Nashorn** tại dự án `openjdk/nashorn`. Đây là một **thư viện bên ngoài** có thể dùng trên Java 11 trở đi và được phát hành qua Maven Central.

Ví dụ trong bài cố định dependency:

```xml
<dependency>
    <groupId>org.openjdk.nashorn</groupId>
    <artifactId>nashorn-core</artifactId>
    <version>15.7</version>
</dependency>
```

Đây là **dependency rõ ràng** được sử dụng và kiểm thử trong ví dụ bên dưới. Nó **không** biến Nashorn trở lại thành module tích hợp của JDK 17; application chịu trách nhiệm đóng gói, cập nhật và kiểm tra security/compatibility của dependency này.

### 3.1. Đừng nhầm standalone package với JDK cũ

Nashorn tích hợp trước JDK 15 từng sử dụng những package như `jdk.nashorn.api.scripting`. Khi code dựa trên Nashorn-specific API và chuyển sang standalone, package đặc thù tương ứng dùng namespace **`org.openjdk.nashorn.api.scripting`**. Nếu chỉ dùng `javax.script` cho ví dụ cơ bản, bạn có thể không phải import package engine-specific nào.

Dùng `javax.script` có lợi cho thiết kế:
- một phần code chạy được với nhiều provider khác nhau;
- việc thiếu engine có thể phát hiện bằng `null`;
- có thể thay implementation với ít thay đổi hơn nếu script dùng cú pháp tương thích.

Nhưng **không nên tuyên bố** rằng mọi script Nashorn sẽ chạy không cần sửa trên GraalJS hay ngược lại. Java host interop, global variables, các API riêng, mức hỗ trợ ECMAScript và security defaults có thể khác.

### 3.2. Standalone Nashorn không phải modern JavaScript engine đầy đủ

Nashorn có nguồn gốc từ ECMAScript 5.1 và hỗ trợ một số phần của ES6. Nếu ví dụ cần nhiều tính năng ECMAScript mới, hãy đánh giá **GraalJS** hoặc engine khác với version tương thích, thay vì thêm Nashorn rồi giả định nó hỗ trợ mọi cú pháp hiện đại.

Standalone Nashorn là một lựa chọn hữu ích để **minh họa quá trình thay dependency bị xóa**, đặc biệt khi ứng dụng cũ đã dùng Nashorn. Nó không đồng nghĩa là lựa chọn tốt nhất cho một runtime JavaScript mới cần đầy đủ ECMAScript hiện đại.

### 3.3. JPMS và transitive dependencies

Standalone Nashorn được phân phối như một **JPMS module**, có những dependencies như **ASM**. Nếu chạy trên classpath qua Maven, cơ chế quản lý dependency thông thường có thể kéo các JAR cần thiết. Nếu tự copy một file `nashorn-core-15.7.jar` rồi bỏ qua các thư viện ASM, engine có thể lỗi class loading hoặc không được phát hiện.

Nếu dùng `--module-path`, phải bảo đảm module Nashorn và dependencies được đưa vào và được resolve phù hợp. Có trường hợp cần `--add-modules org.openjdk.nashorn` tùy cách khởi chạy. Không tự sửa `module-info.java` bằng một tên module không có thật trong deployed image.

## 4. Ví dụ runnable: một Java class, hai môi trường

Mục tiêu: Dùng **cùng một file Java 17**, chạy:
- **Không có external JavaScript provider:** in `engine=UNAVAILABLE` và thoát một cách có kiểm soát.
- **Có Maven dependency `nashorn-core:15.7`:** tìm được provider, chạy code JavaScript đơn giản, truyền dữ liệu host qua `Bindings` và gọi hàm script qua `Invocable`.

Ví dụ tránh JavaScript APIs riêng của Nashorn để tập trung vào JSR 223. Đây là **mã demo tin cậy**, không nhận source do người dùng bất kỳ gửi vào.

### 4.1. Cấu trúc thư mục

```text
external-script-engine-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── ExternalEngineDemo.java
```

Maven dependency dùng đúng file name `ExternalEngineDemo.java` và class public `ExternalEngineDemo`.

### 4.2. File pom.xml đầy đủ

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>external-script-engine-demo</artifactId>
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
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.0</version>
        <configuration>
          <mainClass>ExternalEngineDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

**Tại sao khai báo cụ thể?**
- `nashorn-core:15.7` là **provider JavaScript bên ngoài JDK**. Không có nó, đoạn Java ở phần kế tiếp vẫn compile nhưng không tự có engine Nashorn ở JDK 17+.
- `maven.compiler.release=17` đặt target language/platform Java 17 cho chương trình host.
- Maven compiler và exec plugins cố định phiên bản để tránh phụ thuộc mơ hồ vào mặc định của môi trường build.
- Maven giải quyết các dependencies của `nashorn-core` theo POM, thay vì yêu cầu chép từng ASM JAR thủ công.

Đây là cấu hình đã được chạy kiểm chứng với Maven 3.9.x và OpenJDK 24 khi biên dịch target `--release 17`. Trong môi trường không có Maven hoặc bị chặn Maven Central, phải cung cấp artifacts qua repository nội bộ đáng tin và kiểm tra checksum/quyền sử dụng theo policy tổ chức.

### 4.3. File ExternalEngineDemo.java đầy đủ

```java
import javax.script.Bindings;
import javax.script.Invocable;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;

public class ExternalEngineDemo {
    public static void main(String[] args) throws Exception {
        ScriptEngineManager manager = new ScriptEngineManager();
        ScriptEngine engine = manager.getEngineByName("nashorn");
        if (engine == null) {
            System.out.println("engine=UNAVAILABLE");
            return;
        }

        System.out.println("engine=AVAILABLE");
        Bindings bindings = engine.createBindings();
        bindings.put("name", "Java");
        System.out.println("greeting=" + engine.eval("'Hello, ' + name", bindings));
        System.out.println("answer=" + ((Number) engine.eval("6 * 7")).intValue());

        if (!(engine instanceof Invocable invocable)) {
            throw new IllegalStateException("Invocable not supported");
        }
        engine.eval("function add(a,b) { return a + b; }");
        System.out.println("add="
                + ((Number) invocable.invokeFunction("add", 2, 3)).intValue());
    }
}
```

**Giải thích từng bước:**

1. `new ScriptEngineManager()` tìm các script-engine factories mà context class loader của thread nhìn thấy.
2. `getEngineByName("nashorn")` yêu cầu một provider có alias `nashorn`; nếu thiếu, `null` là kết quả bình thường. Code **không gọi `eval` trên `null`**.
3. Nếu engine sẵn có, `Bindings` chứa key `"name"` và giá trị `"Java"` để script tham chiếu. Phép nối chuỗi `'Hello, ' + name` tạo `"Hello, Java"`.
4. `eval("6 * 7")` trả một `Object`; kết quả numeric được xử lý qua interface `Number` rồi `intValue()`, tránh giả định chính xác wrapper class của mọi JavaScript engine.
5. `Invocable` là capability tùy engine. Code kiểm tra `instanceof` trước khi gọi `invokeFunction`.
6. Hàm script `add(a,b)` được định nghĩa bằng `engine.eval` rồi Java gọi qua `invocable.invokeFunction("add",2,3)`. Kết quả `5` được hiển thị.

**Giới hạn có chủ đích:** `main throws Exception` để demo gọn. Trong production, nên catch cụ thể `ScriptException`, `NoSuchMethodException`, lỗi provider/discovery và lỗi hợp đồng dữ liệu, rồi chuyển thành lỗi domain thích hợp. Code không sử dụng `org.openjdk.nashorn.*` trực tiếp, nên phần Java host chỉ compile với `java.scripting` chuẩn; engine implementation được thêm ở runtime bởi Maven.

### 4.4. Chạy không có engine ngoài

Để quan sát “JDK 17+ không tự có Nashorn”, chạy **chỉ với class đã biên dịch**, không đặt dependencies engine lên classpath:

```bash
javac --release 17 ExternalEngineDemo.java
java -cp . ExternalEngineDemo
```

Với JDK sạch không có JavaScript provider khác, **stdout**:

```text
engine=UNAVAILABLE
```

Kết quả này đã được kiểm chứng trên JDK 24 khi chỉ chạy class Java host, không có external JSR 223 engine trên classpath.

**Không được dùng output này để khẳng định rằng mọi JDK 17+ đều trả null với tất cả engine names:** một ứng dụng đã khai báo GraalJS, standalone Nashorn hoặc nhà cung cấp khác vẫn có thể khám phá được engine. Điều đúng là **bản thân JDK 17+ không đóng gói Nashorn mặc định**, và `getEngineByName` phải được xử lý như phép lookup có thể thất bại.

### 4.5. Chạy với dependency Nashorn rõ ràng

Từ thư mục có `pom.xml` và `src/main/java/ExternalEngineDemo.java`:

```bash
mvn -B -q -DskipTests compile exec:java
```

**Stdout do chương trình in ra (đã kiểm chứng):**

```text
engine=AVAILABLE
greeting=Hello, Java
answer=42
add=5
```

Maven trong một số môi trường có thể in log, warning hoặc thông tin build ra terminal; bảng trên là **các dòng do demo in**, không phải lời hứa toàn bộ console của công cụ Maven có đúng bốn dòng.

Đây là minh chứng rằng **cùng một mã Java host** chỉ thay đổi cách **đóng gói provider** là có thể:
- trả `UNAVAILABLE` an toàn khi thiếu engine;
- hoặc tìm engine bên ngoài và đánh giá JavaScript khi provider được phân phối đầy đủ.

### 4.6. Vì sao không gọi trực tiếp Nashorn factory trong demo?

Có thể dùng class engine-specific như `org.openjdk.nashorn.api.scripting.NashornScriptEngineFactory` để kiểm soát implementation rõ hơn, nhưng việc đó tạo **compile-time dependency** vào Nashorn. Bài này giữ host code trên `javax.script` để nhấn mạnh cơ chế SPI và lỗi missing-provider, còn POM định nghĩa engine thật.

Nếu một production service **bắt buộc** dùng đúng Nashorn implementation cụ thể, cần thêm bước xác thực `engine.getFactory()` (name, version, factory class, provider origin) hoặc khởi tạo factory trực tiếp bằng dependency cố định. Chỉ dựa vào alias chung `"JavaScript"` khi có nhiều providers là chưa đủ chắc chắn.

## 5. Cách nhận diện engine thực tế khi deploy

Nếu trong IDE demo chạy nhưng deployment trả `null`, hãy quan sát các thông số **của chính tiến trình deploy**:

```java
ScriptEngineManager manager = new ScriptEngineManager();
System.out.println("engineFactories=" + manager.getEngineFactories().size());
for (ScriptEngineFactory f : manager.getEngineFactories()) {
    System.out.println("engine=" + f.getEngineName());
    System.out.println("aliases=" + f.getNames());
    System.out.println("language=" + f.getLanguageName());
}
```

Đây là đoạn minh họa với các import `javax.script` cần thiết, **không có stdout cố định**. `getEngineFactories()` dùng để debug providers, không phải cách đếm số script languages JVM bắt buộc hỗ trợ.

Kiểm tra các tầng:

| Tầng | Câu hỏi | Lỗi thường gặp |
| --- | --- | --- |
| Dependency | Đã khai báo engine artifact đúng group/version? | Chỉ có `java.scripting` API hoặc một artifact giao diện. |
| Dependency scope | Artifact có đi vào runtime thật không? | `test`/`provided` scope bị loại khỏi production. |
| Transitive libraries | Các ASM/JAR liên quan có được đóng gói không? | Chỉ copy một Nashorn jar, còn dependencies biến mất. |
| Classpath | Provider JAR có trong classpath của process đang chạy? | IDE classpath khác executable jar/container. |
| Module path | Provider module có trong graph đã resolve? | Module JAR nằm trên path nhưng chưa được resolve. |
| Class loader | Manager đang dùng context loader nào? | App-server/plugin loader khác loader giữ engine. |
| Alias | `getNames()` của factory có `"nashorn"`? | Dùng tên không được provider đăng ký hoặc alias đã thay. |
| Engine API | Engine có hỗ trợ `Invocable`, `Compilable`? | Cứ cast trực tiếp gây `ClassCastException`. |
| Runtime capability | Engine có hỗ trợ syntax/interop thực tế không? | Script Nashorn-specific không chạy trên engine khác. |
| JVM image | `java.scripting` có được đóng gói và resolved? | Custom `jlink` image thiếu API, lỗi module/class loading. |

**Bẫy:** `ScriptEngineManager.getEngineByName("JavaScript")` có thể thành công nhờ **một engine khác**, không phải Nashorn. Nếu bài học muốn minh họa Nashorn độc lập, giữ đúng `"nashorn"` và dependency `nashorn-core`; đừng đổi alias rồi gọi mọi JavaScript engine là “Nashorn”.

### 5.1. Nhận diện module java.scripting

`ScriptEngineManager` là API thuộc module `java.scripting`, không phải `java.base`. Với một **named module** dùng `javax.script`, module descriptor tối thiểu có thể khai báo:

```java
module example.script.host {
    requires java.scripting;
}
```

Đây là file **`module-info.java` minh họa**, không nằm trong Maven project chạy trên classpath ở phần 4. Nếu runtime image không có `java.scripting`, một named module có `requires java.scripting` có thể **không khởi động** được vì module resolution thất bại. Bổ sung standalone Nashorn dependency không thể thay thế việc đóng gói **module API** cần thiết.

Nếu đặt provider trên **module path**, phải bảo đảm JSR 223 service provider thực sự được resolve hoặc được cấu hình đúng. Với standalone Nashorn, dự án OpenJDK ghi rõ provider và dependencies ASM cần nằm trên module path/module layer hoặc được cấu hình phù hợp. Đừng kết luận “Maven tải jar” là đủ trong mọi JPMS deployment.

### 5.2. Class loaders trong containers và plugin systems

`ScriptEngineManager()` sử dụng thread context class loader. Khi ứng dụng chạy trong framework hoặc app server:
- một plugin có thể dùng child loader chứa engine;
- request thread có context loader chỉ thấy classes của host;
- manager được tạo trước khi engine được nạp có thể đã khám phá một tập factories khác.

Có thể tạo manager với loader rõ ràng:

```java
ClassLoader loader = plugin.getClass().getClassLoader();
ScriptEngineManager manager = new ScriptEngineManager(loader);
```

Đây là **đoạn minh họa** với biến `plugin` của framework; không phải chương trình độc lập. Cần đảm bảo loader thực sự có quyền nhìn thấy `ScriptEngineFactory` và dependencies. Tránh tự ý sửa global context class loader của thread pool cho mọi request; dùng mô hình loader lifecycle và cleanup phù hợp.

### 5.3. Không dùng `registerEngineName` để “tạo” engine từ hư không

`ScriptEngineManager.registerEngineName(name, factory)` có thể đăng ký **một factory đã tồn tại** dưới tên mong muốn. Nó không tải JavaScript engine hay thêm compiler/runtime implementation tự động. Nếu không có `ScriptEngineFactory` hợp lệ, không có gì để đăng ký.

## 6. GraalJS: một lựa chọn bên ngoài khác, nhưng cần khai báo riêng

Nếu dự án cần JavaScript hiện đại hơn hoặc muốn kiểm soát host access kỹ hơn, có thể cân nhắc **GraalJS**. Từ các phiên bản GraalVM hiện đại, không nên giả định một `ScriptEngine` được đóng sẵn trong bản phân phối: **GraalJS ScriptEngine cũng phải được thêm dependency riêng**, và có những yêu cầu tương thích Java/GraalVM cụ thể.

Với cách tiếp cận JSR 223, tài liệu GraalJS mô tả:
- JAR provider **`org.graalvm.js:js-scriptengine`**;
- language implementation/dependencies qua **`org.graalvm.polyglot:js`** hoặc artifact tương ứng, được quản lý theo cùng bộ version;
- thường dùng alias **`"graal.js"`**.

Một ví dụ Maven dành cho dự án đã xác nhận **JDK/GraalJS version compatibility** có thể dùng tọa độ cụ thể dưới đây:

```xml
<dependency>
    <groupId>org.graalvm.js</groupId>
    <artifactId>js-scriptengine</artifactId>
    <version>25.0.3</version>
</dependency>
<dependency>
    <groupId>org.graalvm.polyglot</groupId>
    <artifactId>js</artifactId>
    <version>25.0.3</version>
    <type>pom</type>
</dependency>
```

Đây là **ví dụ cấu hình một lựa chọn khác**, **không** phải POM của chương trình Java 17 đã chạy ở phần 4. Với các dòng GraalJS hiện đại, phải kiểm tra **JDK được hỗ trợ** (tài liệu hiện hành hướng tới các JDK mới hơn), dependencies chính xác, chính sách license và phiên bản đồng bộ trước khi dùng; không tuyên bố GraalJS 25.x trong cấu hình này chạy được trên mọi JDK 17.

Dùng GraalJS qua JSR 223:

```java
ScriptEngine engine =
        new ScriptEngineManager().getEngineByName("graal.js");
if (engine == null) {
    throw new IllegalStateException("GraalJS ScriptEngine provider missing");
}
```

Đây là snippet minh họa với import `javax.script`. Nó **không tự hoạt động** khi thiếu dependency provider/language runtime. Nếu cần tùy chỉnh quyền Java host interoperability và isolation, tài liệu GraalVM **khuyến nghị `org.graalvm.polyglot.Context`** thay vì coi `ScriptEngine` cũ là API ưu tiên cho dự án mới.

### 6.1. Migration không đồng nghĩa thay chuỗi tên engine

Không thay:

```java
manager.getEngineByName("nashorn");
```

thành:

```java
manager.getEngineByName("graal.js");
```

rồi giả định toàn bộ script cũ có cùng behavior. Một checklist migration cần đánh giá:
- Phiên bản ECMAScript và cú pháp được hỗ trợ.
- Cách JavaScript nhìn thấy Java objects/classes và policy `Java.type`/host access.
- Dữ liệu trở lại từ `eval`: `Number`, boolean, strings, collections và polyglot values có thể khác.
- Các Nashorn-specific globals và package/API như `Java.extend`, `Java.to`, `Java.from`, object mirroring hoặc class filters.
- Thread-safety, concurrency và cách tạo engine/context.
- Sandbox, filesystem/network access, dependencies và runtime packaging.

Nếu chỉ cần **đọc JSON**, dùng Java JSON parser đáng tin thay vì khởi tạo full JavaScript engine; JSON và JavaScript execution là hai nhu cầu khác nhau.

## 7. Error handling: phân biệt thiếu provider với lỗi script

Có ít nhất bốn lớp lỗi khác nhau.

| Pha | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Discovery | `manager.getEngineByName("nashorn") == null` | Báo thiếu dependency/provider rõ ràng, không `eval` |
| Provider loading | Thiếu transitive JAR, lỗi module/class loading, `ServiceConfigurationError` | Kiểm tra packaging/loader/module graph, không chữa bằng cách thay script |
| Script evaluation | Cú pháp script sai, lỗi runtime từ script | Catch `ScriptException`, ghi vị trí/dòng/nguồn phù hợp |
| Host/script function invocation | Hàm không tồn tại hoặc `Invocable` không hỗ trợ | Kiểm tra capability, xử lý `NoSuchMethodException`/`ScriptException` |

### 7.1. Một API boundary đơn giản và rõ ràng

```java
static Object evaluateConfiguredScript(String source)
        throws javax.script.ScriptException {
    ScriptEngine engine = new ScriptEngineManager()
            .getEngineByName("nashorn");
    if (engine == null) {
        throw new IllegalStateException(
                "Nashorn provider unavailable: add nashorn-core at runtime");
    }
    return engine.eval(source);
}
```

Đây là **method minh họa**, đặt trong một class có import `javax.script.ScriptEngine`, `javax.script.ScriptEngineManager`. Nó phân loại:
- `IllegalStateException`: deployment/capability lỗi (không có provider);
- `ScriptException`: đã có engine, nhưng quá trình đánh giá script báo lỗi.

**Không đưa source không tin cậy** vào method này mà không có architecture isolation phù hợp. Mẫu chỉ minh họa phân biệt lỗi, không phải API an toàn cho remote code execution.

### 7.2. ScriptException chứa vị trí source

```java
try {
    engine.eval("function (");
} catch (ScriptException ex) {
    System.err.println("script failed: " + ex.getMessage());
    System.err.println("line: " + ex.getLineNumber());
    System.err.println("column: " + ex.getColumnNumber());
}
```

Đây là snippet minh họa trong method có biến `engine` không null. `getLineNumber()`/`getColumnNumber()` có thể không biết vị trí; không assume mọi provider đều có đầy đủ thông tin. Đừng log nguyên văn source người dùng nếu source chứa secrets; hệ thống logging nên gắn script ID/correlation ID và redaction.

### 7.3. Đừng nuốt ServiceConfigurationError

Nếu service provider metadata bị lỗi hoặc thiếu class, có thể xảy ra `ServiceConfigurationError`/`LinkageError` trong quá trình load. Một manager có thể không khám phá được provider, và log của Java có thể cho biết lý do. Đừng luôn gom **mọi Throwable** thành “không có script engine”; điều đó che hỏng packaging và các `Error` nghiêm trọng. Log nguyên nhân hợp lý, fail-fast nếu đây là capability bắt buộc.

## 8. API quan trọng khi nhúng script

### 8.1. Bindings và ScriptContext

`Bindings` là map từ tên biến sang object Java mà engine có thể nhìn thấy theo quy tắc của nó:

```java
Bindings input = engine.createBindings();
input.put("name", "Java");
Object value = engine.eval("'Hello, ' + name", input);
```

Đây là snippet minh họa với `engine` đã tồn tại. Tránh dùng dữ liệu người dùng để nối string code theo kiểu:

```java
String script = "lookup('" + userInput + "')";
engine.eval(script);
```

Đây là **phản ví dụ** nếu `userInput` là dữ liệu không tin cậy: có thể dẫn đến script injection. Dùng `Bindings` hoặc interface có tham số rõ ràng thay vì ghép source code khi có thể; vẫn phải kiểm soát host object access vì một script có thể gọi method trên object được expose.

### 8.2. Invocable là optional

```java
if (engine instanceof Invocable invocable) {
    engine.eval("function add(a,b) { return a+b; }");
    Object sum = invocable.invokeFunction("add", 2, 3);
}
```

`Invocable` không được mọi engine đảm bảo. Nếu script không định nghĩa function `add`, invocation có thể ném `NoSuchMethodException`. Không bắt `ClassCastException` bằng cách ép kiểu trực tiếp `(Invocable) engine` rồi cho rằng JSR 223 bắt buộc mọi provider hỗ trợ.

### 8.3. Compilable là optional

```java
if (engine instanceof Compilable compilable) {
    CompiledScript compiled = compilable.compile("6 * 7");
    Object value = compiled.eval();
}
```

Đây là snippet minh họa cần import `javax.script.Compilable`, `CompiledScript` và xử lý `ScriptException`. Khi đánh giá cùng script nhiều lần, một số engines có thể hưởng lợi từ compile trước. Tuy nhiên:
- không phải tất cả providers implement `Compilable`;
- việc cache compiled scripts phải phù hợp engine/context lifecycle;
- **không share script engine cho nhiều thread** trừ khi factory/provider documentation xác nhận semantics an toàn.

### 8.4. Thread safety không được bảo đảm chung

Một `ScriptEngineFactory` có thể cung cấp `getParameter("THREADING")` để mô tả threading support theo JSR 223 convention. Không có thông số hoặc giá trị `null` không thể được diễn giải là “thread-safe” theo mặc định.

Cho production service nhiều requests:
- cân nhắc một engine/context riêng cho mỗi task/thread, pooling có kiểm soát hoặc cấu trúc được vendor hỗ trợ;
- tránh cho nhiều request cùng sửa `ENGINE_SCOPE`/global bindings trên một shared engine khi không có synchronization;
- không cho code người dùng truy cập vô hạn vào các Java objects đã inject.

## 9. Bảo mật: script engine không phải sandbox

Đây là điểm đặc biệt quan trọng khi di chuyển từ Nashorn tích hợp sang external engine. Việc pin dependency **không tự bảo vệ** việc chạy script tùy ý.

Một JavaScript engine nhúng trong JVM có thể có nhiều cách giao tiếp với Java host, ví dụ truy cập các class/method Java thông qua cơ chế host interoperability. Cấu hình không đúng có thể cho phép script:
- đọc file, truy cập network, gọi lệnh OS nếu host cung cấp quyền;
- đọc thông tin nhạy cảm được đặt trong bindings/global scope;
- gây CPU/memory exhaustion, vòng lặp vô hạn;
- tác động đến state của chính ứng dụng.

### 9.1. Cách dùng an toàn hơn

- Chỉ chạy scripts **được tin cậy/được kiểm duyệt** trong demo học tập.
- Với code từ user, cân nhắc **process/container sandbox riêng**, timeout, memory/CPU limits, filesystem/network policy, hạn chế quyền của OS account.
- Không expose arbitrary Java objects, class loaders, `ProcessBuilder` hoặc filesystem APIs cho script nếu không cần.
- Áp dụng host class access policy của engine cụ thể theo tài liệu provider; GraalVM `Context` cung cấp các lựa chọn policy rõ hơn so với việc chỉ dùng JSR 223 generic.
- Giới hạn script size, cache và concurrency; giữ audit trail, quét dependencies và cập nhật bản vá.
- Không coi SecurityManager (đã bị hạn chế/deprecated và thay đổi trong các JDK mới) là giải pháp sandbox mặc định.

Đặc biệt, không chuyển script từ JavaScript engine cũ sang engine mới rồi chỉ đổi alias mà không rà soát **quyền truy cập host**. Các defaults không nhất thiết tương đương.

### 9.2. Đừng trộn JSON parsing với JavaScript eval

Nếu yêu cầu chỉ là parse payload JSON, dùng JSON parser library phù hợp. `engine.eval(jsonString)` không phải cách chuẩn/safe để xử lý JSON vì có thể biến input thành code executable hoặc thay đổi semantics. Việc loại bỏ Nashorn không nên buộc hệ thống tạo một runtime JavaScript chỉ để giải mã dữ liệu.

## 10. Bảo đảm build và deployment

### 10.1. Classpath, fat JAR, shaded JAR

Maven `exec:java` trong bài dùng runtime classpath do Maven thiết lập. Khi đóng gói production:
- Nếu dùng “thin JAR”, phải triển khai đủ transitive dependency JAR và khai báo classpath đúng.
- Nếu dùng fat/shaded JAR, chú ý service provider metadata `META-INF/services/javax.script.ScriptEngineFactory`. Shading mà không merge service descriptors có thể khiến `ScriptEngineManager` **không thấy provider** dù implementation class ở trong JAR.
- Nếu dùng custom class loader, kiểm tra service resources và loader visibility.
- Nếu dùng JPMS module path, giữ module provider và dependencies nhất quán.

**Hệ quả vận hành:** Không test duy nhất bằng `mvn exec:java` rồi kết luận runnable JAR trong Docker sẽ chắc chắn tìm được engine. Phải chạy discovery + smoke eval trên **artifact đã package**.

### 10.2. java.scripting module trong runtime image

Ví dụ về một test cấu hình:

```bash
java --list-modules
java -version
```

`java --list-modules` cho biết modules có trong runtime image của binary được gọi. Nếu `java.scripting` không tồn tại trong custom image, Java host code có direct `javax.script` dependency có thể fail class/module loading. Nếu module có nhưng không có standalone engine, manager có thể chạy bình thường nhưng trả `null`.

**Giới hạn của cờ:** `--add-modules java.scripting` không thể tự cài module bị loại khỏi image. `--add-modules org.openjdk.nashorn` cũng không tự tải Nashorn JAR từ Maven Central; provider JAR và dependencies phải thực sự được cung cấp.

### 10.3. Kiểm soát versions

Trong production nên pin version và kiểm thử compatibility:
- Java language/runtime target;
- engine/provider artifact và transitives;
- Maven/Gradle plugin/toolchain;
- JDK/JVM implementation;
- JavaScript syntax level và host-interoperability policy.

Ví dụ chính pin `nashorn-core:15.7` và Java `--release 17`. Nếu ứng dụng chọn GraalJS, phải pin **các module GraalJS/GraalVM cùng bộ version** tương thích với runtime thực tế. Tránh dependency ranges không kiểm soát khi hành vi script có ý nghĩa nghiệp vụ quan trọng.

## 11. Ma trận kiểm thử nên có

| Tình huống | Cấu hình test | Kết quả mong đợi |
| --- | --- | --- |
| Không có external engine | Chỉ chạy `ExternalEngineDemo.class` trên JDK 17+ sạch | `engine=UNAVAILABLE`, không NPE |
| Provider Nashorn đầy đủ | Maven POM có `nashorn-core:15.7` và transitives | `engine=AVAILABLE`, `answer=42`, `add=5` |
| Sai alias | Lookup tên engine không nằm trong `factory.getNames()` | Trả `null` với alias đó |
| Thiếu Nashorn transitives | Bỏ một ASM dependency khi tự đóng gói | Provider không hoạt động đúng; cần khôi phục packaging |
| JPMS image thiếu `java.scripting` | Custom runtime module graph không chứa API | Module/class loading failure cần được chẩn đoán riêng |
| Engine phát hiện được nhưng syntax không hỗ trợ | Dùng cú pháp ngoài mức ECMAScript engine hỗ trợ | `ScriptException`/provider-specific failure |
| Engine có nhưng thiếu `Invocable` | Provider không implement interface tùy chọn | Code chủ động từ chối capability, không ép kiểu |
| Function name sai | Gọi `invokeFunction` với tên không tồn tại | `NoSuchMethodException` nếu engine hỗ trợ `Invocable` |
| Script ném lỗi | JS error trong `eval` | `ScriptException` có diagnostics nếu engine cung cấp |
| Shaded JAR mất SPI service descriptor | Provider JAR có class nhưng `ServiceLoader` không thấy factory | Khôi phục/merge service metadata, test packaged artifact |
| Nhiều engines cùng alias | Hai providers có tên chung `"JavaScript"` | Chọn provider tường minh, kiểm tra factory thực tế |
| Script không tin cậy | Input có vòng lặp vô hạn hoặc Java host access | Không chạy trong process không cô lập |

Đối với bản Maven demo, kiểm tra tối thiểu là **hai điều kiện độc lập**:
1. `javac --release 17` và `java -cp ...` **không có external Nashorn** → kết quả controlled-unavailable.
2. `mvn -B -q -DskipTests compile exec:java` trong project có Nashorn dependency → JavaScript thực thi đúng.

Nếu chưa chạy trường hợp (2) trên môi trường thật, đừng ghi trong README “đã dùng Nashorn trên Java 17” chỉ vì Java code compile: compiler của Java host không cần provider để compile.

## 12. Bài tập và đáp án

### Bài 1 — Nashorn và Java 17

Một sinh viên viết:

```java
ScriptEngine js =
        new ScriptEngineManager().getEngineByName("JavaScript");
System.out.println(js.eval("40 + 2"));
```

Tại sao ví dụ không thể được giới thiệu như “chạy trên JDK 17 thuần, không cần dependency”?

**Đáp án:** JEP 372 đã loại bỏ Nashorn tích hợp từ JDK 15. `java.scripting` chỉ cung cấp API, không mặc định có JavaScript implementation. `getEngineByName` có thể trả `null`, gây NPE. Phải **khai báo external engine** và kiểm tra lookup trước khi `eval`.

### Bài 2 — Hai lớp ToolProvider khác nhau

`javax.tools.ToolProvider` và `javax.script.ScriptEngineManager` có cùng chức năng không?

**Đáp án:** Không. `javax.tools.ToolProvider.getSystemJavaCompiler()` tìm Java compiler implementation (Java source → bytecode). `ScriptEngineManager` tìm script-engine factory để đánh giá code một ngôn ngữ nhúng, ví dụ JavaScript. Có Java compiler không tạo ra Nashorn. Hai API giải quyết hai bài toán khác nhau.

### Bài 3 — Build dependency và runtime classpath

POM có `nashorn-core` nhưng Docker image chỉ copy application JAR, bỏ transitive JARs. `getEngineByName("nashorn")` vẫn phải thành công vì source có import `javax.script`, đúng hay sai?

**Đáp án:** Sai. Script-engine discovery cần **provider implementation ở runtime**, các ASM/transitive dependencies, service registration và class loader/module visibility. Import API không tạo provider.

### Bài 4 — Thiết kế fallback

Một ứng dụng có tính năng optional cho phép chạy script để kiểm thử. Nếu không có engine, chính sách nào hợp lý?

**Đáp án:** Vô hiệu hóa tính năng có kiểm soát và trả trạng thái `SCRIPT_ENGINE_UNAVAILABLE` hoặc một thông báo yêu cầu cấu hình dependency. **Không** giả lập kết quả `eval` và không gọi lên `null`. Nếu tính năng là bắt buộc, fail fast khi khởi tạo service.

### Bài 5 — Migration engine

Đội phát triển thay alias `"nashorn"` bằng `"graal.js"`. Vì sao còn phải kiểm thử?

**Đáp án:** Engine mới có thể có khác biệt về ECMAScript syntax, global variables, Java interop, kết quả trả về, threading và security defaults. Cần thêm dependency GraalJS, chọn version/JDK tương thích và đối chiếu behavior của script thực tế.

### Bài 6 — Chính sách an toàn

Có thể nhận script tùy ý từ API rồi thực thi `engine.eval(source)` ngay trong Java web server vì “chỉ là scripting” không?

**Đáp án:** Không. Script có thể dùng CPU/bộ nhớ vô hạn hoặc tương tác với Java host nếu engine cấp quyền. Cần auth, giới hạn tài nguyên, host access policy, isolation/sandbox và quy tắc kiểm soát input. Phụ thuộc vào engine cụ thể, `ScriptEngine` generic không đủ để khẳng định an toàn.

### Bài 7 — Kiểm chứng độc lập

Hãy trình bày hai stdout mong đợi khi chạy đúng chương trình `ExternalEngineDemo`:
1. Chỉ dùng class đã biên dịch, **không external provider**.
2. Chạy qua Maven project với `nashorn-core:15.7`.

**Đáp án:** Trường hợp 1 in `engine=UNAVAILABLE`. Trường hợp 2 in `engine=AVAILABLE`, `greeting=Hello, Java`, `answer=42`, `add=5`. Cả hai trạng thái đã được chạy kiểm chứng bằng Java host code Java 17-compatible trên JDK 24.

## Tài liệu tham khảo

- [JEP 335 — Deprecate the Nashorn JavaScript Engine](https://openjdk.org/jeps/335): mốc deprecated for removal ở JDK 11.
- [JEP 372 — Remove the Nashorn JavaScript Engine](https://openjdk.org/jeps/372): loại bỏ trong JDK 15; **`javax.script` không bị ảnh hưởng**.
- [Java SE 17 — ScriptEngineManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html): cơ chế `ServiceLoader`, class loader, `getEngineByName` trả `null`, `getEngineFactories`.
- [Java SE 17 — ScriptEngine](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html): `eval`, `Bindings` và scopes.
- [Java SE 17 — ScriptEngineFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineFactory.html): tên/aliases, versions và khả năng provider.
- [Standalone OpenJDK Nashorn project](https://github.com/openjdk/nashorn): Nashorn bên ngoài JDK, hỗ trợ Java 11+ và JPMS/ASM dependencies.
- [Maven Central — nashorn-core 15.7](https://central.sonatype.com/artifact/org.openjdk.nashorn/nashorn-core/15.7): artifact cụ thể dùng trong chương trình runnable.
- [GraalJS documentation](https://www.graalvm.org/javascript/docs/): các lựa chọn embedding qua Java/JVM.
- [GraalVM ScriptEngine documentation](https://www.graalvm.org/jdk22/reference-manual/js/ScriptEngine/): provider `js-scriptengine` là dependency riêng; khuyến nghị `Context` khi cần fine-grained security.
- [Maven Central — GraalJS js-scriptengine 25.0.3](https://central.sonatype.com/artifact/org.graalvm.js/js-scriptengine/25.0.3): ví dụ tọa độ tham khảo cho engine khác, phải xác nhận JDK compatibility.

## Kết luận

**Nashorn đã bị loại khỏi JDK từ JDK 15**, nên ví dụ Java 17+ không được giả định `ScriptEngineManager.getEngineByName("JavaScript")` sẽ luôn có kết quả. **`javax.script` vẫn tồn tại như một API chung**; engine implementation phải được cung cấp **rõ ràng**. Với bài minh họa sử dụng Nashorn, POM khai báo `org.openjdk.nashorn:nashorn-core:15.7` và chương trình kiểm tra `engine == null` trước khi gọi `eval`. Với GraalJS hoặc một provider khác, cũng cần dependency/version và security policy riêng. Hãy luôn kiểm thử **cả môi trường có và không có provider** trên đúng runtime được triển khai, kiểm tra classpath/module path/SPI và tránh dùng một script engine in-process để chạy code không tin cậy mà không có isolation.
