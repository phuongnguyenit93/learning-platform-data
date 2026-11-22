# Vì sao bytecode nhắm JDK cũ vẫn có thể gọi nhầm API mới

Một ứng dụng Java có thể được biên dịch bằng JDK mới nhưng tạo ra class file mang phiên bản bytecode của JDK cũ. Điều đó thường khiến nhóm nghĩ rằng artifact chắc chắn chạy được trên runtime cũ. Kết luận này chưa đủ cơ sở: **phiên bản bytecode và phiên bản API mà class file tham chiếu là hai vấn đề khác nhau**.

Ví dụ, compiler của JDK 21 có thể tạo class file major version 61 (định dạng bytecode của Java 17) nếu build đặt `-source 17 -target 17`. Nhưng compiler vẫn nhìn thấy các class và method của JDK 21. Source có thể gọi `Thread.ofVirtual()`, một API chỉ xuất hiện từ Java 21, rồi được biên dịch thành class file major 61. JVM Java 17 có thể đọc định dạng class file đó, nhưng khi đường chạy thực thi lời gọi tới method không tồn tại trong `java.lang.Thread` của Java 17, ứng dụng có thể thất bại với `NoSuchMethodError`.

Vấn đề này thường được gọi là sử dụng nhầm API mới khi target runtime cũ. Cách giải quyết ở tầng compiler là dùng `--release` đúng phiên bản, chẳng hạn `--release 17`, thay vì chỉ đặt riêng source level và target bytecode. Tuy nhiên, `--release` cũng có phạm vi giới hạn: nó kiểm soát API Java nền tảng mà source của lần biên dịch đó được phép tham chiếu, nhưng không tự chứng minh mọi thư viện bên thứ ba, plugin, generated binary hay runtime production đều tương thích với JDK 17.

## 1. Ba khái niệm cần tách biệt

### 1.1. Source language level

Source level quy định compiler chấp nhận cú pháp và tính năng ngôn ngữ nào. Ví dụ, `-source 17` yêu cầu `javac` phân tích mã nguồn theo quy tắc ngôn ngữ Java 17. Nó kiểm soát các tính năng cú pháp như record, sealed class, pattern matching ở mức được hỗ trợ cho release đó.

Source level không tự giới hạn những class và method mà compiler nhìn thấy trong thư viện chuẩn của JDK đang chạy. Nếu compiler chạy bằng JDK 21, classpath hệ thống mặc định của nó chứa API JDK 21. Vì thế, một lời gọi method mới vẫn có thể được chấp nhận dù cú pháp source bị giới hạn ở Java 17.

### 1.2. Class-file target

Target level quy định phiên bản định dạng class file mà compiler tạo ra. Ví dụ, `-target 17` tạo class file có major version 61. JVM Java 17 hiểu định dạng này.

Target level không biến một lời gọi API Java 21 thành lời gọi API Java 17. Compiler chỉ ghi các tham chiếu symbolic tới class, method và field vào bytecode. Compiler không tự thay thế method mới bằng một cách triển khai cũ tương đương, cũng không kiểm tra đầy đủ rằng mọi tham chiếu sẽ được runtime mục tiêu cung cấp.

### 1.3. Platform API level

Platform API level là tập API Java nền tảng mà chương trình được phép tham chiếu. Khi mục tiêu là chạy trên Java 17, source cần được biên dịch với tập API Java 17, kể cả khi compiler thực thi bằng JDK 21.

Đây là phần mà `--release 17` giải quyết. Tùy chọn `--release` kết hợp mức ngôn ngữ, phiên bản class file và tập API nền tảng tương ứng với release được chọn. Nó giúp ngăn source vô tình tham chiếu API chỉ có trong JDK đang chạy compiler.

| Khái niệm | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| Source level | Source được phép dùng cú pháp Java nào? | `-source 17` |
| Target bytecode | Class file được tạo theo định dạng nào? | `-target 17`, major version 61 |
| Platform API level | Source được phép gọi API Java nền tảng của release nào? | `--release 17` |
| Runtime thực tế | JVM nào sẽ nạp và thực thi artifact? | Java 17 hoặc Java 21 |

Một cấu hình build đúng cần thống nhất cả bốn khái niệm theo mục tiêu sản phẩm. Không thể suy ra platform API level chỉ từ class-file major version.

## 2. Cơ chế lỗi: class file cũ tham chiếu method mới

Giả sử máy build dùng JDK 21, còn sản phẩm phải tiếp tục chạy trên JDK 17. Đoạn code sau dùng API virtual thread:

```java
public class ApiLevelExample {
    public static void main(String[] args) {
        Thread thread = Thread.ofVirtual().start(() ->
            System.out.println("Hello from a virtual thread")
        );
    }
}
```

`Thread.ofVirtual()` được bổ sung chính thức trong Java 21. Nếu compile bằng JDK 21 với cấu hình chỉ giới hạn source và target:

```bash
javac -source 17 -target 17 ApiLevelExample.java
```

compiler có thể chấp nhận lời gọi trên vì nó đang đọc API `java.lang.Thread` của JDK 21. Class file được tạo có major version 61, tương ứng Java 17. Kiểm tra bằng:

```bash
javap -verbose ApiLevelExample
```

Phần header sẽ thể hiện `major version: 61`. Điều này chỉ nói class file dùng định dạng Java 17. Nó không chứng minh method `Thread.ofVirtual()` có trong Java 17.

Khi chạy trên JDK 21, method tồn tại nên lời gọi có thể hoạt động. Khi chạy cùng class file trên JDK 17, JVM có thể nạp class vì major version hợp lệ. Đến lúc liên kết lời gọi method không có trong runtime, JVM phát sinh lỗi linkage, điển hình là:

```text
java.lang.NoSuchMethodError:
  'java.lang.Thread$Builder java.lang.Thread.ofVirtual()'
```

Thông báo cụ thể có thể khác theo bytecode, cách biên dịch và thời điểm JVM phân giải tham chiếu. Điểm cốt lõi là runtime không tìm thấy method mà bytecode yêu cầu.

Đây không phải `UnsupportedClassVersionError`. Hai lỗi thể hiện hai vấn đề khác nhau:

| Lỗi | Nguyên nhân | Ví dụ |
|---|---|---|
| `UnsupportedClassVersionError` | Runtime quá cũ để đọc định dạng class file | Class major 65 được nạp trên Java 17 chỉ hỗ trợ tới major 61 |
| `NoSuchMethodError` | Class file đọc được nhưng method được tham chiếu không có trong runtime | Bytecode major 61 gọi `Thread.ofVirtual()` trên Java 17 |
| `NoClassDefFoundError` / `ClassNotFoundException` | Class được tham chiếu không có trong runtime hoặc không được tìm thấy qua class loader | Code dùng `java.util.SequencedCollection` trên Java 17 |
| `NoSuchFieldError` | Field được tham chiếu không có trong class runtime thực tế | Dependency biên dịch với version thư viện khác version lúc chạy |
| `IllegalAccessError` | Tham chiếu tồn tại nhưng không thể truy cập theo quy tắc access/module | Thư viện truy cập thành phần bị đóng gói hoặc không export |

JVM có thể phân giải một số symbolic reference theo nhu cầu khi đường chạy được thực thi. Vì vậy, ứng dụng có thể khởi động bình thường và chỉ lỗi khi người dùng gọi đúng endpoint hoặc chức năng có chứa API mới. Một smoke test chỉ kiểm tra startup sẽ không phát hiện được mọi trường hợp.

## 3. Vì sao `-source` và `-target` không đủ?

Khi dùng:

```bash
javac -source 17 -target 17 App.java
```

compiler nhận hai chỉ dẫn:

- Phân tích source theo ngôn ngữ Java 17.
- Tạo class file theo định dạng Java 17.

Không có chỉ dẫn nào nói rằng compiler phải giới hạn các API nền tảng nhìn thấy ở Java 17. Vì compiler đang chạy trên JDK 21, nó có thể tìm thấy class và method mới của JDK 21.

Điều này cũng giải thích vì sao một source không dùng cú pháp Java mới vẫn có thể không chạy trên runtime cũ. Cú pháp source và API runtime là hai trục độc lập.

Ví dụ, source Java 17 hoàn toàn có thể dùng cú pháp quen thuộc nhưng tham chiếu API Java 21:

```java
import java.util.List;

public class CollectionExample {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Bình");
        System.out.println(names.getFirst());
    }
}
```

`List.getFirst()` thuộc nhóm Sequenced Collections được bổ sung trong Java 21. Mã nguồn không dùng cú pháp mới nào của Java 21, nhưng vẫn cần API Java 21. Nếu target bytecode 17 bằng `-source` và `-target`, class file vẫn có thể tham chiếu method mới.

Đặt source/target thấp hơn chỉ giải quyết khả năng đọc cú pháp và định dạng class file. Nó không phải bộ kiểm tra API tương thích.

## 4. `--release` ngăn lỗi gọi API mới như thế nào?

JEP 247 bổ sung `--release` cho `javac` từ JDK 9. Tùy chọn này cho compiler biết release nền tảng đích. Khi biên dịch với JDK 21 nhưng cần tương thích Java 17:

```bash
javac --release 17 -d out src/main/java/example/App.java
```

Compiler sẽ dùng các signature API của Java 17 thay vì toàn bộ API của JDK 21, đồng thời tạo bytecode phù hợp với release 17 và áp dụng quy tắc ngôn ngữ tương ứng. Lời gọi `Thread.ofVirtual()` hoặc `List.getFirst()` sẽ không được tìm thấy trong platform API 17, nên compile thất bại ngay tại source thay vì để lỗi xuất hiện ở production.

Ví dụ lỗi biên dịch có dạng:

```text
error: cannot find symbol
    Thread.ofVirtual();
          ^
  symbol:   method ofVirtual()
  location: class Thread
```

Các signature API lịch sử được lưu trong dữ liệu nền tảng mà compiler sử dụng, thường được cung cấp trong JDK qua `ct.sym`. Người dùng không cần tự tạo boot classpath cho từng phiên bản khi dùng `--release`.

So sánh ba lệnh:

```bash
# Chỉ giới hạn cú pháp và bytecode; API vẫn có thể đến từ JDK 21.
javac -source 17 -target 17 App.java

# Giới hạn đồng bộ ngôn ngữ, bytecode và API Java SE ở release 17.
javac --release 17 App.java

# Cho phép dùng ngôn ngữ, bytecode và API Java 21.
javac --release 21 App.java
```

Trong các JDK hiện đại, không nên kết hợp `--release` với `-source` hoặc `-target` cho cùng một lần biên dịch. `--release` đã bao gồm các ràng buộc đó.

### 4.1. Phạm vi bảo vệ của `--release`

`--release 17` giúp kiểm soát các tham chiếu trực tiếp trong source được biên dịch tới API nền tảng Java SE của release 17. Nó đặc biệt hữu ích khi:

- JDK cài trên máy lập trình viên hoặc CI mới hơn runtime tối thiểu của sản phẩm.
- Nhiều module cùng build trên JDK 21 nhưng một số artifact phải tiếp tục hỗ trợ Java 17.
- Một thư viện muốn phát hành artifact có thể dùng trên nhiều runtime Java.
- Source được tạo bởi annotation processor hoặc generator và cần tuân theo API target.

Khi generated source được đưa vào cùng compilation task, compiler áp dụng `--release` cho source đó và có thể từ chối API mới. Tuy nhiên, nếu generator tạo trực tiếp class file, đóng gói sẵn binary, hoặc chạy một compilation task riêng không có `--release`, tham chiếu API mới vẫn có thể lọt qua. Cần kiểm tra mọi task tạo bytecode, không chỉ task `compileJava` quen thuộc.

### 4.2. Những gì `--release` không đảm bảo

`--release 17` không tự động:

- Kiểm tra bytecode và API mà mọi dependency bên thứ ba đã tham chiếu.
- Đảm bảo dependency runtime có thể chạy trên Java 17.
- Kiểm tra plugin Gradle/Maven hoặc annotation processor chạy được trên JDK của build.
- Kiểm soát source được biên dịch bởi Kotlin, Scala, Groovy hoặc compiler riêng nếu các task đó không có cấu hình tương đương.
- Kiểm soát class file được tải động, sinh trực tiếp bằng bytecode library hoặc tải từ dịch vụ ngoài.
- Bảo đảm reflection theo tên chuỗi không tham chiếu class/method chỉ có trên JDK mới.
- Đảm bảo runtime production thực sự là Java 17.

Do đó, `--release` là một cổng kiểm soát quan trọng ở compiler, nhưng cần kết hợp với dependency analysis, test trên runtime đích và kiểm tra artifact.

## 5. Ví dụ tái hiện và xác nhận lỗi

Tạo file `ApiLevelExample.java`:

```java
public class ApiLevelExample {
    public static void main(String[] args) {
        System.out.println(Thread.ofVirtual().name("worker").factory());
    }
}
```

Trên máy cài JDK 21, xác nhận compiler đang dùng:

```bash
javac -version
java -version
```

Biên dịch với source/target 17:

```bash
javac -source 17 -target 17 ApiLevelExample.java
javap -verbose ApiLevelExample
```

Nếu compiler chấp nhận code, kiểm tra `major version` trong output. Kết quả dự kiến là 61. Sau đó chạy class bằng JDK 21 để xác nhận API có trong runtime 21.

Tiếp theo, dùng JDK 17 thực sự để chạy class file vừa tạo:

```bash
<JDK17_HOME>/bin/java ApiLevelExample
```

Đường dẫn trên là placeholder, cần thay bằng đường dẫn JDK 17 trên máy kiểm thử. Nếu method mới được thực thi, runtime 17 sẽ không phân giải được method và có thể ném `NoSuchMethodError`.

Xóa output và biên dịch lại bằng `--release 17`:

```bash
rm -f ApiLevelExample.class
javac --release 17 ApiLevelExample.java
```

Lần này compiler phải từ chối lời gọi `Thread.ofVirtual()` vì method không tồn tại trong API Java 17. Đây là kết quả mong muốn: phát hiện vi phạm ngay ở build.

Để kiểm tra một API mới khác, có thể thay lời gọi bằng `List.of("A").getFirst()`. Cùng nguyên tắc áp dụng: nếu API không có trong Java 17, `--release 17` phải từ chối source.

Lưu ý: ví dụ chỉ dùng để minh họa cơ chế compiler/runtime. Không dùng file thử nghiệm này làm bằng chứng duy nhất cho khả năng tương thích của ứng dụng thực tế.

## 6. Cấu hình Gradle đúng khi build bằng JDK 21 nhưng target Java 17

Gradle có thể dùng một JDK toolchain để chạy compiler và một mức release để giới hạn API/bytecode. Ví dụ với Groovy DSL:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Trong cấu hình này:

- Compiler được chọn từ toolchain JDK 21.
- `options.release = 17` yêu cầu `javac --release 17`.
- Source được biên dịch theo ngôn ngữ/API Java 17 và tạo class file phù hợp Java 17.

Nếu mục tiêu thực sự là chuyển sản phẩm sang Java 21, đổi release thành 21:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
```

### 6.1. Không chỉ cấu hình task `compileJava`

Trong dự án nhiều module hoặc có nhiều source set, cần kiểm tra mọi task `JavaCompile`, chẳng hạn:

- `compileJava` của main source set.
- `compileTestJava` của test source set.
- Task compile cho integration test, functional test hoặc source set tùy chỉnh.
- Task do plugin tạo ra để compile generated source.
- Task compile của included build hoặc convention plugin.

Đặt cấu hình ở root có thể không ảnh hưởng đến included build độc lập hoặc module dùng build logic khác. Hãy xác nhận từng task thực sự nhận `--release` bằng log compiler hoặc cấu hình task, không chỉ đọc một đoạn build script.

### 6.2. Phân biệt toolchain với target release

`java.toolchain.languageVersion = 21` xác định compiler JDK 21. Nó không tự động có nghĩa output phải là Java 21. `options.release = 17` mới là giới hạn platform API và bytecode 17.

Ngược lại, chỉ đặt `sourceCompatibility = 17` và `targetCompatibility = 17` không tạo cùng mức bảo vệ API như `options.release = 17`. Khi yêu cầu tương thích Java 17, nên dùng `options.release` nếu compiler hỗ trợ.

### 6.3. Kotlin, Groovy và các ngôn ngữ khác

`options.release` chỉ áp dụng cho task `JavaCompile`. Nếu module có Kotlin, Groovy, Scala hoặc source generator riêng, cần cấu hình compiler tương ứng và kiểm tra khả năng giới hạn JDK API của công cụ đó. Ví dụ, Kotlin có các tùy chọn JVM target và tùy chọn JDK release ở các phiên bản compiler hỗ trợ; chỉ đặt `jvmTarget` không nên được coi là bằng chứng rằng API Java 17 đã được giới hạn.

Các module hỗn hợp phải được kiểm tra theo task graph. Một lớp Java được compile với `--release 17` vẫn có thể phụ thuộc vào class Kotlin/Groovy hoặc thư viện binary được tạo theo JDK mới.

## 7. Cấu hình Maven Compiler Plugin

Với Maven, dùng thuộc tính `maven.compiler.release` hoặc cấu hình `<release>` trong Maven Compiler Plugin. Ví dụ:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

Hoặc khai báo rõ plugin và cấu hình:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>${maven-compiler-plugin.version}</version>
            <configuration>
                <release>17</release>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Property version plugin trong ví dụ là placeholder; cần dùng version cụ thể đã được kiểm tra với Maven và JDK chạy build. Maven Compiler Plugin hỗ trợ cấu hình `release` từ các phiên bản có hỗ trợ JDK 9 trở lên; hãy đối chiếu tài liệu của plugin đang dùng, không dựa vào version ngầm định của Maven super POM.

Nếu dùng JDK 21 để chạy Maven nhưng compiler release là 17, compiler sẽ giới hạn source/API/bytecode theo Java 17. Tuy nhiên, Surefire/Failsafe, annotation processor và các plugin khác vẫn chạy trong môi trường riêng của chúng. Cần xác nhận JDK của từng forked process và plugin execution.

## 8. Vì sao dependency bên thứ ba vẫn có thể phá vỡ cam kết Java 17?

Đây là giới hạn quan trọng nhất cần hiểu sau khi đã cấu hình `--release` đúng. Compiler chỉ kiểm soát source được biên dịch trong compilation đó và API Java nền tảng mà source được phép tham chiếu. Nó không biên dịch lại hay phân tích toàn bộ dependency binary để bảo đảm chúng không gọi API mới.

### 8.1. Dependency có bytecode mới hơn

Nếu một thư viện được biên dịch cho Java 21, class file của nó thường có major version 65. Ứng dụng có thể compile trên JDK 21 vì compiler đọc được class đó, nhưng khi chạy trên Java 17, JVM không thể nạp class và ném `UnsupportedClassVersionError`.

Đây là trường hợp dễ nhận diện bằng class-file version. Nó khác với trường hợp bytecode cũ nhưng tham chiếu API mới.

### 8.2. Dependency có bytecode cũ nhưng tham chiếu API mới

Một thư viện có thể được biên dịch bằng JDK 21 với source/target 17 nhưng không dùng `--release 17`. Kết quả là class file major version 61 nhưng constant pool chứa symbolic reference tới API chỉ có trong Java 21.

Ứng dụng của bạn có thể biên dịch hoàn toàn thành công với `--release 17`, bởi compiler không kiểm tra implementation bên trong dependency như source của chính dự án. Khi runtime 17 thực thi đường code trong thư viện đó, lỗi linkage có thể xuất hiện.

Ví dụ, thư viện `legacy-compatible-client.jar` có class major 61 nhưng method nội bộ gọi `Thread.ofVirtual()`. Ứng dụng của bạn không gọi API Java 21 trực tiếp; nó chỉ gọi `client.execute()`. Khi `execute()` đi vào nhánh tạo virtual thread trên Java 17, JVM có thể ném `NoSuchMethodError`.

Do đó, kiểm tra major version của dependency chưa đủ. Cần kiểm tra nhà cung cấp công bố runtime support, release notes và chạy integration test trên Java 17 nếu đó là runtime tối thiểu.

### 8.3. Dependency dùng reflection hoặc tên class dạng chuỗi

Compiler khó phát hiện các tham chiếu được tạo động như:

```java
Class<?> type = Class.forName("java.util.SequencedCollection");
```

Tên class chỉ là string trong source. `--release 17` không thể suy ra rằng chương trình sẽ cố nạp class Java 21 khi chạy. Tương tự, method được tìm bằng reflection, service provider được nạp động, scripting engine hoặc plugin được tải từ ngoài có thể tham chiếu API mới mà compiler không thấy.

Các vùng cần rà soát:

- `Class.forName`, `ClassLoader.loadClass` và reflection theo tên.
- `MethodHandles.Lookup` hoặc dynamic proxy.
- ServiceLoader và file `META-INF/services`.
- Plugin/module được tải từ thư mục bên ngoài artifact.
- Cấu hình tên class trong YAML, properties, XML hoặc database.
- Script, expression engine và code được biên dịch tại runtime.

Các trường hợp này cần test runtime và rà soát cấu hình, không thể chỉ dựa vào compile gate.

### 8.4. Generated bytecode và công cụ instrumentation

Byte Buddy, ASM, Javassist, CGLIB, agent hoặc generator có thể tạo bytecode trực tiếp mà không đi qua task `javac` có `--release 17`. Một plugin có thể sinh class major 61 nhưng ghi tham chiếu tới API mới, hoặc sinh class major 65 ngoài dự kiến.

Kiểm kê tất cả đường tạo bytecode:

- `javac`/JavaCompile thông thường.
- Annotation processor sinh source rồi compiler biên dịch.
- Generator tạo `.class` trực tiếp.
- Runtime instrumentation/agent biến đổi class.
- Kotlin/Scala/Groovy compiler và compiler task riêng.
- Build plugin đóng gói hoặc tải binary sinh từ nơi khác.

Nếu generated source được compile trong cùng task `--release 17`, compiler sẽ kiểm tra tham chiếu API trực tiếp. Nếu generator tự tạo binary hoặc task riêng không dùng release 17, cần kiểm tra artifact đầu ra bằng công cụ phù hợp và test trên runtime 17.

### 8.5. Multi-release JAR

Một JAR có thể chứa implementation khác nhau cho các phiên bản Java trong thư mục `META-INF/versions/`. Manifest có thuộc tính `Multi-Release: true` cho phép JVM chọn class phù hợp với runtime.

Ví dụ:

```text
library.jar
├── META-INF/MANIFEST.MF
├── com/example/Feature.class
└── META-INF/versions/
    ├── 17/com/example/Feature.class
    └── 21/com/example/Feature.class
```

Java 17 sẽ chọn base entry hoặc phiên bản phù hợp cao nhất không vượt quá 17; Java 21 có thể chọn implementation trong `versions/21`. Vì vậy, cùng một artifact có thể thực thi code khác nhau trên hai runtime. Cần kiểm tra manifest, nội dung JAR và test trên từng runtime mục tiêu. Đừng giả định kiểm tra một class ở thư mục gốc đại diện cho implementation được Java 21 chọn.

## 9. Cách kiểm tra dependency có gọi API mới hay không

Không có một lệnh đơn giản duy nhất chứng minh mọi binary đều tương thích Java 17. Kết hợp nhiều lớp bằng chứng sẽ đáng tin cậy hơn.

### 9.1. Kiểm tra class-file version

Dùng `javap -verbose` trên class đại diện:

```bash
javap -verbose -classpath path/to/library.jar com.example.LibraryClass
```

Đọc `major version`. Một dependency có major version lớn hơn 61 không thể được nạp trực tiếp bởi Java 17. Nhưng major version 61 hoặc thấp hơn chỉ chứng minh định dạng class file phù hợp, không chứng minh API linkage.

Với JAR lớn, có thể liệt kê class và dùng script/tool kiểm tra major version cho toàn bộ class, bao gồm cả các entry trong `META-INF/versions`. Phải xử lý multi-release JAR theo đúng runtime đang xét.

### 9.2. Kiểm tra API tham chiếu

Có thể dùng công cụ phân tích bytecode và API signature để phát hiện class của dự án tham chiếu API không có trong Java 17. Ví dụ, Animal Sniffer cung cấp signature theo phiên bản Java và plugin cho Maven/Gradle để kiểm tra API sử dụng.

Khi áp dụng, xác nhận:

- Signature đúng là Java 17 và đúng profile cần hỗ trợ.
- Plugin version tương thích với JDK/build tool đang dùng.
- Phạm vi class được kiểm tra có bao gồm source set cần thiết.
- Generated source/class và module con có được đưa vào kiểm tra không.
- Báo cáo phân biệt API Java SE với API bên thứ ba.

Animal Sniffer hoặc công cụ tương đương là một lớp kiểm tra bổ sung. Không nên mặc định rằng nó đã phân tích mọi dependency binary trong runtime graph. Kiểm tra artifact bên thứ ba cần được thực hiện theo khả năng công cụ và chính sách của dự án.

### 9.3. Dùng jdeps đúng mục đích

`jdeps` giúp phân tích dependency giữa class, package và module, đồng thời phát hiện tham chiếu tới API nội bộ của JDK. Ví dụ:

```bash
jdeps --jdk-internals application.jar
jdeps -summary application.jar
```

`jdeps` hữu ích để tìm dependency nội bộ và module phụ thuộc. Tuy nhiên, không nên coi `jdeps --jdk-internals` là bộ kiểm tra toàn bộ API mới so với Java 17. Nó tập trung vào API nội bộ, không chứng minh rằng mọi method Java SE được tham chiếu đều có trong release 17.

`jdeprscan` có thể hỗ trợ tìm API deprecated trong bytecode:

```bash
jdeprscan --release 17 application.jar
```

Đây cũng không phải phép kiểm tra đầy đủ API linkage theo baseline. Cần kết hợp signature checker, dependency metadata và runtime tests.

### 9.4. Chạy artifact trên runtime tối thiểu

Nếu sản phẩm cam kết Java 17, chạy artifact cuối trên JDK 17 là bằng chứng quan trọng nhất về khả năng thực thi của tổ hợp thực tế. Nên chạy:

- Smoke test khởi động ứng dụng.
- Test endpoint/luồng nghiệp vụ quan trọng.
- Integration test với database, broker và dịch vụ ngoài.
- Test các nhánh dùng dependency ít được gọi.
- Test serializer, reflection, plugin loader và dynamic class loading.
- Test trên đúng container image/runtime đã dự kiến phát hành.

Chỉ kiểm tra startup là chưa đủ vì lỗi linkage có thể xuất hiện khi method/class được sử dụng lần đầu. Cần tạo coverage cho các luồng quan trọng hoặc gọi trực tiếp các chức năng liên quan.

## 10. Kiểm soát cấu hình build để không tái phát

### 10.1. Gradle

Ví dụ build bằng JDK 21 nhưng target Java 17:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Điểm cần nhớ:

- Toolchain chọn JDK compiler.
- `options.release` giới hạn source/API/bytecode Java 17.
- `sourceCompatibility` và `targetCompatibility` đơn lẻ không thay thế hoàn toàn `--release`.
- Cần cấu hình cả `compileTestJava`, custom source set và các task JavaCompile do plugin tạo.
- Included build và `buildSrc` có thể có build riêng, không tự động kế thừa cấu hình root.
- Kotlin/Groovy/Scala cần cấu hình tương đương theo compiler của chúng.

Xác minh compiler args qua log task hoặc chạy:

```bash
./gradlew compileJava --info
```

Không chỉ nhìn build script rồi kết luận; plugin có thể ghi đè compiler options hoặc tạo task mới.

### 10.2. Maven

Ví dụ Maven Compiler Plugin:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Hoặc cấu hình trực tiếp:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>${maven-compiler-plugin.version}</version>
    <configuration>
        <release>17</release>
    </configuration>
</plugin>
```

Kiểm tra version plugin thực tế, parent POM, profile và execution. Đảm bảo compiler plugin nhận release 17 cho mọi module và source set. Test JVM và các plugin chạy forked process vẫn cần kiểm tra riêng.

### 10.3. Khóa và truy xuất dependency

Để build tái lập, quản lý dependency bằng BOM/platform, version catalog, constraints hoặc dependency management có chủ đích. Nếu dùng dependency locking, cập nhật lock state cùng thay đổi được duyệt. Nếu dùng dependency verification, cập nhật checksum/signature sau khi xác nhận artifact.

Không dùng `--release` để thay thế quản lý dependency. Một dependency có thể thay đổi version mà không có thay đổi source; khi đó API hoặc bytecode của dependency cũng có thể thay đổi.

## 11. Ma trận runtime và chính sách hỗ trợ

Nếu sản phẩm phải hỗ trợ cả Java 17 và Java 21, hãy xây dựng ma trận chạy rõ ràng:

| Build JDK | Compiler release | Runtime test | Kết quả cần chứng minh |
|---|---:|---|---|
| 21 | 17 | 17 | Artifact dùng được trên runtime tối thiểu |
| 21 | 17 | 21 | Artifact target 17 vẫn hoạt động trên runtime mới |
| 21 | 21 | 21 | Nhánh artifact chỉ hỗ trợ Java 21 nếu sản phẩm có chính sách này |
| 17 | 17 | 17 | Có thể giữ làm baseline hoặc đối chứng trong giai đoạn chuyển tiếp |

Không phải dự án nào cũng cần chạy đủ bốn tổ hợp. Ma trận phải phản ánh cam kết sản phẩm, nhưng mọi runtime được công bố hỗ trợ cần có ít nhất một pipeline kiểm chứng định kỳ.

Đối với thư viện dùng chung, cần test consumer compile trên Java 17 và runtime integration trên Java 17. Với ứng dụng, test artifact đã đóng gói trong container cùng JRE/JDK đích. Với plugin, test trực tiếp plugin trên JDK chạy build và phiên bản Gradle/Maven được hỗ trợ.

## 12. Ví dụ xuyên suốt: dependency target 17 nhưng gọi API Java 21

Giả sử ứng dụng `order-service` cần hỗ trợ Java 17. Một thư viện `order-client` được biên dịch trên JDK 21 bằng `-source 17 -target 17`. Thư viện gọi `List.getFirst()` để lấy phần tử đầu tiên.

Quy trình phát hiện và xử lý:

1. **Kiểm tra class file:** `javap -verbose` cho thấy class của `order-client` có major version 61. Điều này loại trừ lỗi định dạng class file nhưng chưa chứng minh Java 17 API compatibility.
2. **Kiểm tra dependency metadata:** xác nhận nhà cung cấp có cam kết Java 17 runtime hay không; đọc release notes và cách build artifact.
3. **Kiểm tra API reference:** dùng API signature checker hoặc phân tích bytecode để phát hiện method `List.getFirst()` không có trong Java 17.
4. **Tái hiện:** chạy một test gọi đúng method của `order-client` trên JDK 17. Lỗi có thể xuất hiện dưới dạng `NoSuchMethodError`.
5. **Sửa nguồn:** nếu có thể, thay API bằng cách tương thích Java 17 như `list.get(0)` sau khi bảo đảm list không rỗng; hoặc nâng version thư viện đã sửa và công bố hỗ trợ Java 17.
6. **Sửa pipeline thư viện:** biên dịch source của `order-client` bằng JDK 21 với `--release 17`, thêm API signature check và test runtime 17.
7. **Kiểm chứng consumer:** build lại `order-service`, chạy unit/integration test trên Java 17 và Java 21 theo ma trận hỗ trợ.
8. **Đóng vấn đề:** lưu artifact, checksum, commit, test result và cập nhật compatibility matrix.

Điểm quan trọng: application của bạn có thể dùng `--release 17` hoàn toàn chính xác mà vẫn nhận một dependency binary lỗi. Cổng compiler của application không thể thay thế trách nhiệm kiểm soát compatibility của từng thư viện.

## 13. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách phòng tránh |
|---|---|---|
| Cho rằng major version 61 chứng minh Java 17 compatibility | Bỏ sót tham chiếu API mới | Kiểm tra API signature và runtime behavior |
| Chỉ đặt `-source 17 -target 17` | Compiler vẫn có thể thấy API JDK 21 | Dùng `--release 17` |
| Nghĩ `--release` kiểm tra mọi dependency | Dependency binary có thể gọi API mới | Kiểm tra vendor support, binary và runtime test |
| Chỉ chạy test trên JDK 21 | Không phát hiện lỗi trên runtime tối thiểu 17 | Chạy artifact trên JDK 17 nếu sản phẩm cam kết hỗ trợ |
| Chỉ kiểm tra startup | Linkage error có thể xuất hiện ở nhánh chạy muộn | Test endpoint/luồng nghiệp vụ và dependency ít dùng |
| Bỏ qua processor/generator | Generated class có thể không tuân theo release | Kiểm tra task sinh source/binary và compiler args |
| Chỉ cấu hình compileJava | Test/custom source set vẫn dùng API mới | Cấu hình tất cả task compile liên quan |
| Chỉ cấu hình JavaCompile | Kotlin/Groovy/Scala task có thể target khác | Dùng compiler-specific release/API constraints |
| Dùng jdeps để khẳng định không có API mới | jdeps không phải baseline API checker đầy đủ | Dùng signature checker và runtime test bổ sung |
| Không kiểm tra multi-release JAR | Runtime 17 và 21 có thể chọn class khác nhau | Kiểm tra manifest và versioned entries |

## 14. Hồ sơ kiểm chứng và tiêu chí đóng

Một quyết định “artifact target Java 17” cần có các bằng chứng sau:

1. **Build configuration:** JDK chạy build, compiler toolchain, `--release 17` và cấu hình cho mọi source set.
2. **Class-file evidence:** kiểm tra major version của class do dự án tạo và binary được đóng gói.
3. **API compatibility evidence:** kết quả signature checker hoặc phân tích bytecode theo Java 17.
4. **Dependency evidence:** danh sách dependency runtime, version được chọn, vendor support và các vấn đề chưa xác định.
5. **Generator evidence:** processor/generator version, input/output và task compile tương ứng.
6. **Runtime evidence:** test artifact trên JDK 17 trong môi trường đại diện.
7. **Regression evidence:** test các luồng có lazy linkage, reflection, plugin loading, serialization và integration.
8. **Release evidence:** commit, artifact checksum, runtime image và chính sách rollback.

### Checklist trước khi phát hành

- [ ] Đã xác định runtime tối thiểu mà sản phẩm cam kết hỗ trợ.
- [ ] Compiler chạy bằng JDK mới nhưng dùng `--release` theo runtime tối thiểu.
- [ ] Mọi task compile Java trong module đều nhận đúng release.
- [ ] Các compiler ngôn ngữ khác có cấu hình tương thích riêng.
- [ ] Dependency bên thứ ba có bằng chứng hỗ trợ runtime tối thiểu.
- [ ] Class file major version không vượt mức runtime tối thiểu.
- [ ] Đã kiểm tra tham chiếu API mới trong bytecode do dự án tạo.
- [ ] Generated source/binary, agent và instrumentation được kiểm tra.
- [ ] Multi-release JAR được xác minh trên từng runtime mục tiêu.
- [ ] Artifact cuối chạy được trên runtime tối thiểu, không chỉ build thành công.
- [ ] Các nhánh nghiệp vụ quan trọng đã được thực thi trong test.
- [ ] Có log, checksum, commit và báo cáo để truy nguyên kết quả.

Bytecode nhắm JDK cũ chỉ bảo đảm định dạng class file tương thích với JVM cũ. Muốn bảo đảm API tương thích, compiler phải bị giới hạn đúng platform release bằng `--release`, còn dependency binary, generator và đường chạy thực tế phải được kiểm tra riêng. Khi kết hợp kiểm soát compiler, phân tích API, quản lý dependency và runtime test trên phiên bản tối thiểu, nhóm mới có thể đưa ra cam kết tương thích có bằng chứng.
