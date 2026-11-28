# Phân biệt phiên bản công cụ biên dịch, mức --release và hành vi của JVM chạy chương trình

> **Chương:** Phạm vi và nền tảng  
> **Module:** `JAVA_VERSION_JAVA18`  
> **Mục tiêu:** Hiểu rõ ba phiên bản có thể khác nhau trong một dự án Java: phiên bản của `javac`, phiên bản nền tảng được chọn khi biên dịch bằng `--release` và phiên bản JVM thực sự chạy chương trình. Biết cách chọn đúng mức tương thích, đọc class file, kiểm tra API theo phiên bản và kiểm thử hành vi runtime của các thay đổi Java 18 trên JDK hiện đại.

## 1. Ba câu hỏi khác nhau thường bị gộp thành một

Một dự án có thể được biên dịch bởi JDK 27, nhắm API và class file Java 18, rồi chạy trên JVM Java 25. Điều này hoàn toàn có thể là chủ đích hợp lệ.

Cần tách ba câu hỏi:

1. **Compiler nào biên dịch mã?** Trả lời bằng `javac --version`, đường dẫn executable, vendor và build.
2. **Mã được biên dịch theo nền tảng Java nào?** Trả lời bằng `javac --release N` và kiểm tra class file/API.
3. **JVM nào thực sự thực thi chương trình?** Trả lời bằng `java --version`, `java.home` và runtime properties.

Ví dụ:

~~~text
JDK dùng để build:       27
javac:                   27.0.x
--release:               18
Class file major version: 62
JVM chạy ứng dụng:       25.0.x
~~~

Diễn giải đúng:

- Compiler là javac 27.
- Source được kiểm tra theo quy tắc ngôn ngữ Java 18, tham chiếu API nền tảng Java 18 và sinh class file tương thích mức Java 18.
- Chương trình được thực thi bởi JVM 25; runtime behavior là behavior của JDK 25, không phải một bản JVM 18 được mô phỏng.

**`--release 18` không cài Java 18, không đổi `java -version`, không chọn JVM chạy và không giả lập toàn bộ hành vi runtime của Java 18.**

Điều này đặc biệt quan trọng khi học các thay đổi của Java 18:

| Chủ đề | Thành phần quyết định |
|---|---|
| Cú pháp và quy tắc biên dịch | Compiler cùng source/release level |
| API có được tham chiếu lúc compile hay không | API platform được chọn qua `--release` |
| Phiên bản định dạng class file | Compiler target/release level |
| Default charset UTF-8 (JEP 400) | JVM/runtime thực thi |
| Simple Web Server (JEP 408) | Bộ JDK cung cấp và chạy `jwebserver` |
| `{@snippet}` trong Javadoc (JEP 413) | Bộ JDK cung cấp và chạy `javadoc`/standard doclet |
| Resolver SPI (JEP 418) | API có trong nền tảng biên dịch và resolver được khởi tạo ở JVM runtime |
| Core reflection dùng MethodHandle (JEP 416) | Cách triển khai reflection của JDK runtime; API public vẫn theo đặc tả |

## 2. Phiên bản compiler và runtime có thể khác nhau

### 2.1. `javac --version` không phải `java --version`

`javac` là compiler, còn `java` là launcher khởi chạy JVM. Hai lệnh có thể đến từ các JDK khác nhau nếu PATH, JAVA_HOME, IDE hoặc build tool được cấu hình không đồng bộ.

~~~shell
javac --version
java --version
~~~

Ví dụ:

~~~text
javac 27.0.x
openjdk 25.0.x 2026-...
OpenJDK Runtime Environment ...
OpenJDK 64-Bit Server VM ...
~~~

Kết quả này có thể có nghĩa compiler là JDK 27 trong khi runtime mặc định là JDK 25. Nó không tự động là lỗi. Cần xác định dự án có chủ ý dùng toolchain khác nhau hay đang vô tình lấy executable từ hai bộ cài.

Để biết runtime thực tế mà JVM đang dùng:

~~~shell
java -XshowSettings:properties -version
~~~

Các property quan trọng:

| Property | Ý nghĩa |
|---|---|
| `java.version` | Phiên bản Java runtime |
| `java.runtime.version` | Phiên bản runtime đầy đủ, thường gồm patch/build |
| `java.vendor` | Nhà cung cấp runtime |
| `java.home` | Runtime home của JVM đang chạy |
| `os.arch` | Kiến trúc được runtime báo cáo |

Có thể in các giá trị này ngay trong chương trình:

~~~java
public class RuntimeIdentity {
    public static void main(String[] args) {
        System.out.println("java.version = "
                + System.getProperty("java.version"));
        System.out.println("java.runtime.version = "
                + System.getProperty("java.runtime.version"));
        System.out.println("java.vendor = "
                + System.getProperty("java.vendor"));
        System.out.println("java.home = "
                + System.getProperty("java.home"));
    }
}
~~~

Đoạn mã này cho biết **JVM đã chạy class**. Nó không cho biết compiler nào đã tạo class file; muốn biết điều đó cần xem log build, version của javac và bytecode output.

### 2.2. Vì sao không nên chỉ nhìn số major version?

Một compiler mới có thể tạo class file cho release cũ. Ngược lại, một compiler cũ không thể tự động hiểu mọi cú pháp hoặc API mới chỉ vì runtime máy khác đã được nâng cấp.

| Compiler | Mức biên dịch | Runtime | Kết quả có thể có |
|---|---|---|---|
| JDK 27 | Mặc định Java 27 | JDK 27 | Biên dịch và chạy theo nền tảng hiện tại |
| JDK 27 | `--release 18` | JDK 25 | Có thể chạy nếu code/dependency không yêu cầu runtime mới hơn Java 25 và không vi phạm điều kiện khác |
| JDK 27 | `--release 18` | JDK 18 | Class file/API nhắm Java 18; runtime 18 có thể chạy, nhưng không nên dùng làm môi trường cập nhật thường ngày vì dòng 18 đã hết hỗ trợ thông thường |
| JDK 25 | `--release 18` | JDK 25 | Mô hình phù hợp để build và chạy ứng dụng nhắm API Java 18 trên runtime LTS hiện đại |
| JDK 25 | Mặc định Java 25 | JDK 18 | Không chạy được nếu class file có major version mới hơn JVM 18 hỗ trợ |

Khi nâng cấp, hãy ghi rõ **compiler version**, **release target** và **runtime version** trong log CI. Nếu chỉ ghi “project dùng Java 18”, người review không biết bạn đang nói về compiler, API baseline, class file hay runtime.

## 3. Phân biệt `--source`, `--target` và `--release`

Đây là phần quan trọng nhất khi cấu hình tương thích.

### 3.1. `--source`: quy tắc ngôn ngữ được chấp nhận

`--source N` yêu cầu compiler phân tích và kiểm tra mã nguồn theo quy tắc ngôn ngữ của release N. Nó kiểm soát các tính năng cú pháp và ngữ nghĩa ngôn ngữ ở mức source.

Ví dụ, compiler mới có thể nhận mã Java 18:

~~~shell
javac --source 18 Example.java
~~~

Tùy chọn này **không tự giới hạn API thư viện** mà compiler nhìn thấy. Nếu compiler chạy trên JDK 27, mặc định nó vẫn có thể nhìn thấy API của JDK 27.

### 3.2. `--target`: định dạng class file được sinh ra

`--target N` yêu cầu compiler sinh class file phù hợp với release N:

~~~shell
javac --target 18 Example.java
~~~

Nó không tự chọn bộ API Java 18. Class file có thể mang version 18 nhưng vẫn chứa tham chiếu tới phương thức chỉ xuất hiện ở Java 21 hoặc 27 nếu compiler đã biên dịch dựa trên API của JDK mới.

Khi dùng `--source` và `--target` cho release 9 trở lên, tài liệu javac yêu cầu cung cấp platform classes phù hợp bằng tùy chọn `--system`. Nếu không, compiler có thể sử dụng API của JDK đang cài và tạo ra class file không chạy được trên nền tảng đích.

### 3.3. `--release`: chọn đồng thời source, class file và API platform

`--release N` là cách được khuyến nghị khi muốn biên dịch cho một release Java cụ thể:

~~~shell
javac --release 18 Example.java
~~~

Theo tool specification của javac, compiler:

- Áp dụng quy tắc ngôn ngữ Java của release được chỉ định.
- Sinh class file nhắm release đó.
- Biên dịch với API Java SE và JDK API được export của release đó.

Vì vậy, `--release` giải quyết vấn đề mà chỉ ghép `--source` với `--target` không tự giải quyết: **không cho mã vô tình tham chiếu API mới hơn release đích**.

| Tùy chọn | Kiểm soát source language | Kiểm soát class file | Giới hạn API nền tảng theo release |
|---|---:|---:|---:|
| `--source N` | Có | Không | Không, nếu dùng độc lập |
| `--target N` | Không | Có | Không |
| `--source N --target N` | Có | Có | Không tự giới hạn; phải cung cấp platform classes phù hợp |
| `--release N` | Có | Có | Có, theo API của release N |

Không kết hợp `--release` với `--source`/`-source` hoặc `--target`/`-target` trong cùng lệnh javac.

### 3.4. Ví dụ về một cấu hình sai dễ lọt qua compile

Giả sử dùng JDK 27 để biên dịch, nhưng ứng dụng cần chạy trên Java 18. Phương thức `List.getFirst()` chỉ có từ Java 21:

~~~java
import java.util.List;

public class UsesJava21Api {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Bình");
        System.out.println(names.getFirst());
    }
}
~~~

Nếu chỉ dùng source/target 18 trên compiler mới:

~~~shell
javac --source 18 --target 18 UsesJava21Api.java
~~~

Compiler có thể chấp nhận vì API `List.getFirst()` hiện diện trong JDK 27 mà compiler đang dùng. Class file được sinh ra vẫn nhắm version 18. Nếu chạy trên Java 18, JVM có thể nạp class file nhưng lúc liên kết/lời gọi phương thức không có trong `List` của Java 18 sẽ gặp `NoSuchMethodError`.

Nếu dùng đúng mức release:

~~~shell
javac --release 18 UsesJava21Api.java
~~~

Compiler từ chối vì API `List.getFirst()` không thuộc nền tảng Java 18. Đây là lỗi được phát hiện sớm, ngay trong bước build.

**Kết luận:** Class file target cũ không đồng nghĩa API tương thích cũ. Dùng `--release` để giới hạn cả source, bytecode và API platform.

## 4. Chứng minh API được giới thiệu từ Java 18

`java.net.spi.InetAddressResolverProvider` là API được đưa vào Java 18 qua JEP 418. Ví dụ tối thiểu:

~~~java
import java.net.spi.InetAddressResolverProvider;

public class ResolverApiSince18 {
    public static void main(String[] args) {
        System.out.println(
                InetAddressResolverProvider.class.getName());
    }
}
~~~

Trên JDK mới, thử hai mức biên dịch:

~~~shell
javac --release 17 ResolverApiSince18.java
javac --release 18 ResolverApiSince18.java
~~~

Kết quả dự kiến:

| Lệnh | Kết quả | Giải thích |
|---|---|---|
| `javac --release 17` | Compile thất bại | API chưa tồn tại trong Java 17 |
| `javac --release 18` | Compile thành công | API có trong Java 18 và compiler hỗ trợ release 18 |

Nếu compile bằng `--release 18`, class file nhắm major version 62. JVM Java 17 chỉ hỗ trợ tối đa major 61, nên khi chạy bằng Java 17, chương trình sẽ bị từ chối với `UnsupportedClassVersionError` trước khi thực thi logic.

Trên JVM Java 21/25/27, class file version 62 được hỗ trợ. Tuy nhiên, nếu ứng dụng có dependency hoặc cấu hình đòi hỏi tính năng runtime mới hơn, việc class file được chấp nhận không bảo đảm toàn bộ ứng dụng chạy thành công.

### 4.1. Kiểm tra class file bằng `javap`

Sau khi compile thành công:

~~~shell
javap -verbose ResolverApiSince18
~~~

Tìm dòng:

~~~text
major version: 62
~~~

Bảng đối chiếu thường dùng:

| Java release | Class file major version |
|---|---:|
| Java 17 | 61 |
| Java 18 | 62 |
| Java 21 | 65 |
| Java 25 | 69 |
| Java 27 | 71 |

Class file version là một phần của định dạng bytecode được JVMS quy định. JVM có thể từ chối class file có major version cao hơn mức nó hỗ trợ. Ngược lại, class file cũ hơn thường có thể được JVM mới hơn chấp nhận, nhưng điều đó không bảo đảm các API mà class file tham chiếu vẫn tồn tại hoặc mọi hành vi runtime không đổi.

## 5. Class file tương thích không đồng nghĩa runtime tương thích hoàn toàn

Có ít nhất ba lớp tương thích cần kiểm tra:

### 5.1. Tương thích định dạng bytecode

JVM phải hiểu major/minor version của class file. Ví dụ:

- Java 18 sinh class file major 62.
- Java 17 không hỗ trợ major 62.
- Java 21 trở lên hỗ trợ major 62.

Nếu class file quá mới, lỗi thường xuất hiện ngay khi JVM tải lớp:

~~~text
UnsupportedClassVersionError
~~~

Đây là vấn đề **class file version**, chưa phải lỗi API hay logic ứng dụng.

### 5.2. Tương thích API khi liên kết

Một class file có thể mang version phù hợp với JVM nhưng vẫn tham chiếu phương thức hoặc lớp không có trên runtime đó.

Ví dụ `List.getFirst()`:

- Class file target 18 có thể được tạo khi compiler mới nhìn thấy API Java 21.
- JVM 18 chấp nhận class file major 62.
- Khi lời gọi tới `List.getFirst()` được liên kết/thực thi, runtime 18 không có phương thức ấy.
- Chương trình gặp `NoSuchMethodError`.

Tương tự, tham chiếu đến lớp API không tồn tại có thể gây `NoClassDefFoundError`. Đó là lý do kiểm tra API bằng `--release` quan trọng hơn việc chỉ hạ class file target.

### 5.3. Hành vi runtime

Ngay cả khi bytecode và API đều tương thích, hành vi vẫn được quyết định bởi runtime đang thực thi, cấu hình JVM, hệ điều hành và môi trường.

Một số thay đổi từ Java 18 minh họa rõ:

| Thay đổi | Compiler/release có quyết định không? | Runtime/tool có quyết định không? |
|---|---|---|
| JEP 400 — default charset | Không; `--release 18` không đổi charset của JVM | Có; `Charset.defaultCharset()` và cấu hình runtime quyết định |
| JEP 408 — Simple Web Server | Không; compiler release không chọn tool | Có; `jwebserver` được gọi từ JDK nào và module nào có mặt |
| JEP 413 — Javadoc snippet | Không; compile release không chọn doclet | Có; phiên bản `javadoc`/standard doclet xử lý comment |
| JEP 418 — resolver SPI | Có; API có/không có trong API platform của release | Có; provider được đăng ký, lựa chọn và sử dụng trong JVM |
| JEP 416 — core reflection | Không tạo API mới cho source | Có; runtime JDK quyết định triển khai core reflection bên trong |

Vì thế, `javac --release 18` không có nghĩa “mọi hành vi chương trình sẽ giống hệt Java 18”. Nó chỉ tạo **giới hạn tương thích ở compile time** theo hợp đồng mà tùy chọn này quy định.

## 6. Ví dụ: cùng bytecode, default charset phụ thuộc JVM runtime

JEP 400 đưa default charset về UTF-8 trên cấu hình mặc định từ Java 18. Đây là hành vi runtime. Có thể minh họa bằng một class không gọi API mới:

~~~java
import java.nio.charset.Charset;
import java.util.Arrays;

public class RuntimeCharset {
    public static void main(String[] args) {
        System.out.println(Charset.defaultCharset());
        System.out.println(Arrays.toString("é".getBytes()));
    }
}
~~~

Biên dịch bằng compiler mới nhưng nhắm API Java 17:

~~~shell
javac -encoding UTF-8 --release 17 RuntimeCharset.java
~~~

Sau đó chạy class file bằng hai JVM khác nhau:

~~~shell
/path/to/jdk-17/bin/java RuntimeCharset
/path/to/jdk-25/bin/java RuntimeCharset
~~~

Trong cấu hình Java 17 thông thường, default charset phụ thuộc môi trường. Trên JDK 18 trở lên, default charset thông thường là UTF-8, trừ khi có cấu hình tương thích được hỗ trợ. Vì vậy cùng một class file có thể in ra giá trị charset khác nhau khi chạy trên các runtime khác nhau.

Phép thử dùng `Arrays.toString` để quan sát byte, tránh phụ thuộc việc terminal hiển thị ký tự có dấu thế nào. Kết quả Java 17 cụ thể phụ thuộc hệ điều hành/locale; không mặc định mọi máy Java 17 đều dùng Windows-1252 hoặc một charset cố định khác.

**Điều được chứng minh:** `--release 17` không mô phỏng hành vi default charset của Java 17. JVM đang chạy mới là nơi quyết định.

## 7. Runtime version quyết định triển khai JDK của reflection

JEP 416 tái triển khai core reflection dựa trên method handles trong JDK 18. Tuy nhiên:

- `Method` và `Method.invoke` đã có từ trước Java 18.
- `MethodHandle` đã có từ Java 7.
- Hợp đồng public của `Method.invoke` vẫn trả `Object` và bọc ngoại lệ từ phương thức đích trong `InvocationTargetException`.
- Việc JDK dùng MethodHandle bên trong là chi tiết triển khai của runtime.

Nếu build trên JDK 27 với `--release 18`, class file vẫn có thể gọi `Method.invoke` theo hợp đồng. Khi chạy trên JDK 25, phần triển khai core reflection là của JDK 25. Compiler không thể buộc runtime quay về nội bộ Java 18.

Không dùng cờ lịch sử `-Djdk.reflect.useDirectMethodHandle=false` để yêu cầu JDK hiện đại chạy triển khai reflection cũ: từ JDK 22, triển khai cũ đã bị loại bỏ và cờ đó không còn tác dụng. Khi debug, tập trung vào hợp đồng public, quyền truy cập module và runtime thực tế.

## 8. Preview features là trường hợp đặc biệt, không phải compatibility baseline

Preview feature có vòng đời khác API ổn định:

- Cần bật rõ ràng khi compile và runtime.
- Gắn với release cụ thể.
- Có thể thay đổi, được hoàn thiện hoặc bị loại bỏ.
- Class file phụ thuộc preview của một release không phải artefact tương thích chung cho mọi JDK mới hơn.

Ví dụ trên JDK 27, nếu thực sự học một preview feature của chính Java 27:

~~~shell
javac --enable-preview --release 27 PreviewExample.java
java --enable-preview PreviewExample
~~~

Cả compiler lẫn runtime phải hỗ trợ preview của cùng release. Không lấy class file preview Java 21 rồi kỳ vọng chạy trên JVM Java 25 chỉ vì runtime mới hơn. Đặc tả JVMS quy định class file có minor version `65535` phụ thuộc preview bị ràng buộc với release tương ứng.

Với module này, ưu tiên các thay đổi Java 18 đã được phát hành ổn định và còn áp dụng. Không lấy các ví dụ preview/incubator lịch sử của một release cũ làm kiến thức nền bắt buộc cho JDK hiện đại.

## 9. Chọn đúng mức biên dịch trong Maven và Gradle

### 9.1. Maven Compiler Plugin

Khi dự án cần API baseline Java 18 nhưng dùng JDK mới để build, cấu hình release:

~~~xml
<properties>
    <maven.compiler.release>18</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

`maven.compiler.release` yêu cầu Maven Compiler Plugin chuyển mức release phù hợp cho compiler. Cần dùng phiên bản plugin hỗ trợ JDK/compiler hiện tại và kiểm tra log build để biết compiler thực tế. Nếu dùng Maven Toolchains, toolchain có thể chọn JDK compiler khác với JVM chạy Maven.

Kiểm tra:

~~~shell
mvn -version
mvn -X compile
~~~

Output debug giúp nhận diện compiler, toolchain và tham số được truyền. Không cần dùng `maven.compiler.source` và `maven.compiler.target` riêng lẻ nếu mục tiêu là giới hạn API platform; ưu tiên `maven.compiler.release`.

### 9.2. Gradle Java Toolchain và release

Ví dụ Groovy DSL với JDK 25 làm toolchain, nhưng API baseline Java 18:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 18
}
~~~

Hai cấu hình có vai trò khác nhau:

- `toolchain.languageVersion` chọn JDK compiler/toolchain.
- `options.release` chọn nền tảng đích mà compiler phải tuân theo.

Kiểm tra phiên bản Gradle có hỗ trợ JDK toolchain đã chọn và xem:

~~~shell
./gradlew --version
./gradlew compileJava --info
~~~

Không chỉ đặt `sourceCompatibility`/`targetCompatibility` rồi cho rằng API đã bị giới hạn theo release. Hãy dùng `options.release` khi cần đảm bảo code không gọi API mới hơn baseline.

### 9.3. Build JVM và runtime JVM của ứng dụng

Maven hoặc Gradle có thể chạy trên một JDK, dùng toolchain khác để compile, rồi ứng dụng được deploy trên một JDK thứ ba. Đây là các vai trò khác nhau:

~~~text
JDK chạy Maven/Gradle
        |
        v
Toolchain javac 27
        |
        | --release 18
        v
Class file major 62 + API baseline 18
        |
        v
Ứng dụng được chạy bởi JVM 25
        |
        v
Runtime behavior của JDK 25
~~~

Cấu hình này hợp lệ nếu dependency, plugin, bytecode và runtime đều tương thích. Nếu build tool tự chạy trên JDK 17 nhưng compiler toolchain là JDK 27, đó cũng có thể là thiết kế hợp lệ; cần kiểm tra yêu cầu của build tool và plugin.

## 10. Kiểm thử ma trận compile/runtime

Một dự án nhắm Java 18 nhưng triển khai trên nhiều runtime nên kiểm tra ít nhất hai chiều:

| Chiều | Cần kiểm tra | Cách thực hiện |
|---|---|---|
| Compile baseline | Không tham chiếu API mới hơn Java 18 | `javac --release 18` |
| Class file | Bytecode đúng mức 18 | `javap -verbose`, major version 62 |
| Runtime hiện đại chính | Chạy đúng trên LTS của dự án | Smoke/integration tests trên JDK 21/25 |
| Runtime feature mới | Phát hiện thay đổi sớm | Job bổ sung trên JDK feature release nếu cần |
| JDK tool | Javadoc và Simple Web Server đúng bộ JDK dự kiến | `javadoc --version`, `jwebserver --version` |
| Runtime behavior | Charset, resolver, reflection theo JVM thật | Test trên đúng runtime và cấu hình mục tiêu |

Một ma trận mẫu:

~~~text
Compiler: JDK 27
Compile API/source/class target: --release 18
Primary runtime: JDK 25 LTS
Additional runtime: JDK 21 LTS (nếu dự án còn hỗ trợ)
Optional early compatibility: JDK 27
Javadoc tool: ghi version riêng
jwebserver tool: ghi version riêng
Preview features: không dùng trong baseline
~~~

Không nhất thiết chạy mọi test trên mọi major JDK nếu chi phí lớn. Nhưng phải chạy ít nhất trên runtime production chính và có test tương thích cho những nền tảng còn cam kết hỗ trợ. Nếu code sử dụng API Java 18 như resolver SPI, không tuyên bố hỗ trợ runtime Java 17.

## 11. Lỗi thường gặp và cách phân loại

| Lỗi | Thời điểm | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|---|
| Compiler báo `cannot find symbol` cho API Java 18 khi dùng `--release 17` | Compile time | API chưa có trong release 17 | Dùng baseline từ Java 18 nếu dự án yêu cầu API đó |
| `UnsupportedClassVersionError` | Class loading | Class file mới hơn mức JVM hỗ trợ | Chọn runtime đủ mới hoặc biên dịch target thấp hơn bằng `--release` |
| `NoSuchMethodError` | Linkage/runtime | Bytecode tham chiếu method không có trong runtime | Kiểm tra API baseline; thay source/target bằng `--release` |
| `NoClassDefFoundError` | Loading/linkage | Lớp không có trong runtime/module path/classpath | Kiểm tra API availability, module và dependency |
| Code compile được nhưng charset khác khi chạy | Runtime | JVM runtime khác nhau, JEP 400 hoặc cấu hình charset | Kiểm tra `Charset.defaultCharset()` và dùng charset tường minh ở ranh giới dữ liệu |
| Snippet không render như mong đợi | Javadoc tool | `javadoc` quá cũ hoặc dùng doclet khác | Kiểm tra JDK/tool version và standard doclet |
| `jwebserver` không tìm thấy | Tool/runtime image | Gọi sai JDK hoặc image thiếu `jdk.httpserver` | Kiểm tra đường dẫn tool, module và JDK đầy đủ |
| Reflection có hành vi nội bộ khác sau nâng cấp | Runtime | Triển khai core reflection thay đổi theo JDK | Dựa vào hợp đồng `java.lang.reflect`, không phụ thuộc implementation detail |
| Preview class không chạy trên JDK khác | Class loading | Preview class file bị gắn với release đã biên dịch | Dùng API ổn định hoặc compile/run preview trên đúng release |

Cần phân loại lỗi trước khi sửa. Không giải quyết lỗi API bằng cách chỉ hạ class file target; cũng không đổi JVM runtime khi chưa xác định ứng dụng thực sự yêu cầu API hay hành vi nào.

## 12. Quy trình chẩn đoán một dự án “Java 18” đang chạy sai

Khi một ứng dụng báo lỗi trên máy dev hoặc production, thu thập các thông tin sau theo thứ tự:

1. `javac --version` và đường dẫn compiler thực tế.
2. Lệnh build đầy đủ, đặc biệt `--release`, `--source`, `--target` và `--enable-preview`.
3. `javap -verbose` của class gây lỗi để xem major/minor version.
4. `java --version` và `java.home` của tiến trình đang chạy.
5. API/method/class bị lỗi thuộc release nào; đối chiếu Javadoc của baseline.
6. Classpath/module path và version của dependency.
7. Nếu lỗi thuộc hành vi runtime, kiểm tra vendor, patch, JVM option, OS/locale và cấu hình.

Ví dụ kết luận có căn cứ:

> “Mã được compile bởi javac 27 với `--source 18 --target 18`, nên class file có major 62. Tuy nhiên source tham chiếu `List.getFirst()`, một API từ Java 21. JVM 18 chấp nhận major 62 nhưng không có phương thức đó, vì vậy phát sinh `NoSuchMethodError`. Cần chuyển sang `--release 18` và thay lời gọi bằng API thuộc baseline.”

Cách kết luận này chỉ rõ **compiler**, **target**, **API** và **runtime**, thay vì nói chung rằng “Java 18 không tương thích”.

## 13. Bài tập thực hành

### Bài 1 — Xác định ba phiên bản

Trên máy có JDK mới, chạy `javac --version`, `java --version` và chương trình `RuntimeIdentity`. Ghi lại compiler version, runtime version, vendor và `java.home`.

**Tiêu chí đạt:** Phân biệt được compiler và runtime; giải thích được vì sao hai phiên bản có thể khác nhau.

### Bài 2 — So sánh `--source`/`--target` với `--release`

Dùng `UsesJava21Api.java` ở phần 3.4, biên dịch bằng compiler mới với:

~~~shell
javac --source 18 --target 18 UsesJava21Api.java
javac --release 18 UsesJava21Api.java
~~~

Ghi lại lệnh nào compile được và lệnh nào từ chối API mới.

**Tiêu chí đạt:** Giải thích được vì sao class file target cũ không tự giới hạn API; hiểu vai trò của `--release`.

### Bài 3 — Đọc class file version

Biên dịch `ResolverApiSince18.java` với `--release 18`. Dùng `javap -verbose` để xác nhận major version 62. Thử biên dịch với `--release 17`.

**Tiêu chí đạt:** Phân biệt lỗi API ở compile time với lỗi class file version khi chạy JVM cũ.

### Bài 4 — Chứng minh runtime quyết định default charset

Compile `RuntimeCharset.java` với `--release 17`. Chạy cùng class trên một runtime trước Java 18 nếu có môi trường kiểm thử phù hợp và một runtime Java 18+ được hỗ trợ.

**Tiêu chí đạt:** Giải thích vì sao byte output có thể thay đổi theo JVM mặc dù class file không đổi; không suy ra charset của mọi API chỉ từ một phép thử.

### Bài 5 — Kiểm tra công cụ build

Cấu hình Maven hoặc Gradle dùng JDK toolchain mới nhưng đặt release baseline 18. Ghi compiler version, tham số release, runtime test version và JDK của `javadoc`/`jwebserver`.

**Tiêu chí đạt:** Không nhầm toolchain với target; biết kiểm tra version của từng công cụ và JVM runtime riêng.

## 14. Tài liệu chính thức

1. [The javac Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html): mô tả `--release`, `--source`, `--target`, `--system` và `--enable-preview`.
2. [The java Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): runtime launcher và các tùy chọn thực thi.
3. [The Java Virtual Machine Specification — Java SE 27, Chapter 1](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-1.html): quan hệ giữa Java SE release và class file version.
4. [The Java Virtual Machine Specification — Java SE 27, Chapter 4](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-4.html): định dạng class file, major/minor version và điều kiện JVM chấp nhận.
5. [Java SE 27 ClassFile API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/ClassFile.html): hằng số class file version, bao gồm `JAVA_18_VERSION` và `PREVIEW_MINOR_VERSION`.
6. [JEP 247 — Compile for Older Platform Versions](https://openjdk.org/jeps/247): bối cảnh thiết kế tùy chọn `--release`.
7. [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): ví dụ về hành vi runtime thay đổi từ Java 18.
8. [JEP 408 — Simple Web Server](https://openjdk.org/jeps/408): công cụ JDK có version riêng.
9. [JEP 413 — Code Snippets in Java API Documentation](https://openjdk.org/jeps/413): standard doclet và Javadoc.
10. [JEP 418 — Internet-Address Resolution SPI](https://openjdk.org/jeps/418): API được giới thiệu từ Java 18.
11. [JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): thay đổi triển khai reflection, không phải thay đổi source/target level.
12. [Preview Features — JDK 27](https://docs.oracle.com/en/java/javase/27/language/preview-language-vm-features.html): điều kiện compile/run và vòng đời preview.

**Kết quả học tập cần đạt:** Khi một dự án nói “Java 18”, bạn phải hỏi rõ đang nói về compiler, API baseline, class file hay runtime. Dùng `--release 18` để giới hạn source, bytecode và API nền tảng; dùng JVM hiện đại được hỗ trợ để thực thi và kiểm thử hành vi runtime. Ghi riêng các phiên bản compiler, toolchain và runtime để kết quả build có thể tái hiện và lỗi tương thích có thể được phân loại chính xác.
