# Chọn cách kiểm chứng khi thiết kế Java toolchain

Thiết kế Java toolchain không chỉ là chọn một JDK và cấu hình Maven hoặc Gradle. Nhóm cần chứng minh rằng compiler, API mục tiêu, bytecode, runtime, dependency và quy trình build đều đáp ứng yêu cầu của sản phẩm. Mỗi yêu cầu cần một loại bằng chứng phù hợp; một lệnh java -version hoặc một cấu hình POM đúng cú pháp không thể chứng minh toàn bộ toolchain hoạt động đúng.

Cách chọn phép kiểm chứng bắt đầu từ điều cần chứng minh và rủi ro nếu điều đó sai. Sau đó chọn kiểm tra cấu hình, compile-time, bytecode, runtime, test hành vi, tương thích dependency hoặc reproducibility. Bài này trình bày cách lập ma trận bằng chứng, dùng javac và các công cụ JDK, kiểm tra Maven/Gradle, thiết kế CI matrix và xác định khi nào cần kiểm tra sâu hơn.

## 1. Kiểm chứng điều gì trong một Java toolchain?

Một toolchain Java có nhiều thành phần độc lập:

- JDK được dùng để chạy Maven, Gradle hoặc script.
- JDK/compiler được dùng để biên dịch source.
- Java release mà source được phép sử dụng.
- Class-file version được tạo ra.
- Runtime thấp nhất được sản phẩm hỗ trợ.
- Dependency và annotation processor tương thích.
- Test, package và artifact được tạo ra đúng cách.
- Hệ điều hành, kiến trúc CPU và môi trường CI.
- Tính tái lập của kết quả build.

Trước khi chọn cách kiểm chứng, viết rõ các yêu cầu thành những mệnh đề có thể xác nhận. Ví dụ:

| Yêu cầu | Mệnh đề cần chứng minh |
|---|---|
| Build dùng JDK 17 | Compiler thực tế được chọn là JDK 17 |
| Sản phẩm hỗ trợ Java 17 | Source chỉ dùng API và bytecode tương thích Java 17 |
| Runtime tối thiểu là 17 | Artifact chạy được trên JVM 17 thật |
| Có hỗ trợ Windows và Linux | Build/test pass trên runner của cả hai hệ điều hành |
| Dependency tương thích | Các thư viện cần thiết hoạt động trên runtime mục tiêu |
| Build tái lập | Cùng source và toolchain tạo artifact tương đương theo tiêu chí đã định |

Tránh dùng một kiểm tra để trả lời nhiều câu hỏi khác nhau. Ví dụ, class-file major version 61 chứng minh bytecode có version Java 17; nó không chứng minh code chỉ dùng API Java 17 hoặc chạy được trên mọi hệ điều hành.

## 2. Chọn kiểm chứng theo rủi ro

Một cách thực tế là xếp hạng rủi ro theo tác động và khả năng xảy ra. Những thay đổi liên quan JDK, compiler, dependency nền tảng hoặc runtime tối thiểu thường cần nhiều lớp bằng chứng hơn một thay đổi cấu hình nhỏ.

| Rủi ro | Phép kiểm chứng phù hợp |
|---|---|
| Maven/Gradle chọn sai JDK | In runtime version, Java home và toolchain selection |
| Dùng nhầm API mới hơn release mục tiêu | Compile bằng javac --release |
| Tạo sai bytecode target | Kiểm tra javap -verbose |
| Chạy lỗi trên runtime tối thiểu | Chạy test/smoke test trên JDK tối thiểu |
| Dependency gọi API nội bộ JDK | jdeps --jdk-internals và kiểm tra dependency |
| Khác biệt giữa OS | CI matrix theo OS/architecture |
| Build output thay đổi ngoài ý muốn | Build hai lần và so sánh artifact |
| Hành vi nghiệp vụ sai | Unit, integration và acceptance tests |

Không phải dự án nào cũng cần mọi phép kiểm chứng ở mọi lần commit. Hãy đặt kiểm tra rẻ và nhanh ở mỗi pull request; kiểm tra tốn thời gian hơn có thể chạy theo lịch, khi release hoặc khi nâng JDK/dependency.

## 3. Phân biệt cấu hình, kiểm tra và bằng chứng thực thi

Ba loại bằng chứng thường bị nhầm lẫn:

1. Cấu hình khai báo cho biết nhóm muốn toolchain làm gì. Ví dụ POM khai báo release 17 hoặc Gradle yêu cầu JavaLanguageVersion 17.
2. Kiểm tra cấu hình và lựa chọn toolchain cho biết công cụ đã đọc và chọn cấu hình nào. Ví dụ effective POM, Maven toolchain log hoặc Gradle javaToolchains.
3. Bằng chứng thực thi cho biết compiler/runtime thật sự đã làm gì. Ví dụ compile bằng javac, kiểm tra class file, chạy test trên JDK 17 và đọc kết quả.

Một cấu hình hợp lệ vẫn có thể không được áp dụng do parent POM, profile, Gradle property, IDE hoặc CI override. Vì vậy cần kiểm tra cả giá trị khai báo lẫn công cụ đã chọn.

## 4. Xác định JDK thực tế của shell và build tool

Bắt đầu bằng cách ghi lại version và đường dẫn:

Windows PowerShell:

~~~powershell
$env:JAVA_HOME
Get-Command java -All | Select-Object Source
Get-Command javac -All | Select-Object Source
java -version
javac -version
mvn -version
~~~

Linux/macOS:

~~~bash
printf 'JAVA_HOME=%s\n' "${JAVA_HOME:-<unset>}"
command -v java
command -v javac
java -version
javac -version
mvn -version
~~~

mvn -version hiển thị Java version và Java home mà Maven runtime đang dùng. Gradle Wrapper --version hiển thị JVM chạy Gradle. Đây là kiểm tra runtime của build tool; compiler toolchain có thể được chọn riêng.

Lưu output trong CI để khi build thay đổi, nhóm có thể so sánh JDK vendor, version, Java home, Maven/Gradle version và OS. Chỉ in những biến cần thiết; không dump toàn bộ environment vì có thể chứa secret.

## 5. Kiểm tra JDK compiler và Java release

Nếu sản phẩm hỗ trợ Java 17, cách kiểm chứng API mục tiêu đáng tin cậy là biên dịch với --release 17:

~~~powershell
javac --release 17 -Xlint:all -Werror -encoding UTF-8 -d out src\main\java\demo\App.java
~~~

--release kiểm soát ngôn ngữ Java, class-file target và tập API Java SE được phép sử dụng cho release đó. Đây là điểm khác biệt quan trọng so với chỉ đặt -source và -target.

Ví dụ:

~~~powershell
javac -source 17 -target 17 App.java
~~~

Hai tùy chọn trên điều khiển cú pháp và bytecode target, nhưng khi compiler chạy trên JDK mới hơn, code vẫn có thể tham chiếu API mới hơn Java 17. Kết quả có thể biên dịch được nhưng lỗi khi chạy trên JVM 17.

Dùng --release để compiler kiểm tra cả API mục tiêu. Nếu dự án cần kiểm chứng một JDK compiler cụ thể, ghi rõ JDK thực tế qua mvn -version, javac -version hoặc toolchain log.

## 6. Kiểm tra class-file version bằng javap

Mỗi class file có major version. Một số mốc phổ biến:

| Java release | Class-file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 24 | 68 |

Sau khi compile, dùng:

~~~powershell
javap -verbose out\demo\App.class | Select-String "major version"
~~~

Nếu build nhắm Java 17, kết quả mong đợi là:

~~~text
major version: 61
~~~

Kiểm tra bytecode hữu ích khi xác minh artifact, nhất là khi build có nhiều module hoặc plugin. Tuy nhiên, major version đúng chưa đủ để chứng minh API compatibility. Một class file version 61 vẫn có thể chứa tham chiếu tới API không tồn tại trên Java 17 nếu được biên dịch theo cấu hình source/target không phù hợp.

## 7. Kiểm chứng API và phụ thuộc JDK

Một số API được thêm vào sau release mục tiêu. Ví dụ List.getFirst() thuộc SequencedCollection API từ Java 21. Nếu sản phẩm hỗ trợ Java 17, source gọi API này phải bị từ chối khi compile với --release 17.

Kiểm tra dependency và tham chiếu JDK nội bộ bằng jdeps:

~~~powershell
jdeps --jdk-internals app.jar
~~~

Lệnh này giúp phát hiện việc phụ thuộc vào JDK internal APIs, vốn có thể thay đổi hoặc bị đóng quyền truy cập ở JDK mới. Nó không thay thế việc chạy test trên runtime mục tiêu.

Với dependency, kiểm tra cây thư viện:

Maven:

~~~powershell
.\mvnw.cmd dependency:tree
~~~

Gradle:

~~~powershell
.\gradlew.bat dependencies
~~~

Khi nâng JDK hoặc thư viện nền tảng, xem release notes, compatibility matrix và cảnh báo từ dependency. Một ứng dụng compile được không có nghĩa mọi thư viện đều chạy đúng trên runtime mới.

## 8. Kiểm chứng runtime tối thiểu

Compile bằng JDK mới với --release 17 không chứng minh ứng dụng chạy trên JVM 17. Runtime có thể khác compiler và một số lỗi chỉ xuất hiện khi class được load hoặc khi code thực thi.

Cách kiểm chứng trực tiếp là chạy artifact trên JDK thấp nhất được hỗ trợ:

~~~powershell
$env:JAVA_HOME = 'C:\Java\jdk-17'
$env:PATH = "$env:JAVA_HOME\bin;$env:PATH"
java -version
.\mvnw.cmd clean verify
~~~

Nếu sản phẩm hỗ trợ Java 17 và 21, CI nên có job chạy test trên cả hai runtime. Với ứng dụng server, bổ sung smoke test khởi động ứng dụng, health check và một request đại diện.

Không dùng JDK hiện tại làm bằng chứng cho runtime cũ hơn. Nếu môi trường local chỉ có JDK 24, việc compile --release 17 và chạy trên JDK 24 chỉ chứng minh artifact hoạt động trên JDK 24; vẫn cần runner JDK 17 để xác nhận runtime tối thiểu.

## 9. Kiểm chứng hành vi bằng unit, integration và smoke test

Chọn cấp độ test theo phạm vi rủi ro:

| Loại test | Khi nên dùng | Điều nó chứng minh |
|---|---|---|
| Unit test | Logic class/method độc lập | Quy tắc nhỏ hoạt động đúng |
| Integration test | Kết nối DB, filesystem, HTTP hoặc messaging | Các thành phần phối hợp đúng |
| Smoke test | Khởi động app và gọi luồng chính | Artifact có thể khởi chạy trong môi trường đại diện |
| End-to-end test | Luồng người dùng qua nhiều service | Hệ thống đáp ứng kịch bản từ đầu tới cuối |
| Compatibility test | Nâng JDK hoặc dependency | Hành vi được hỗ trợ trên runtime/version mục tiêu |

Một toolchain có thể compile thành công nhưng test fail vì reflection, serialization, locale, timezone, TLS, encoding hoặc native library. Chọn test dựa trên các điểm có rủi ro khi đổi JDK.

Giữ test ổn định và độc lập môi trường nhất có thể. Nếu test phụ thuộc clock, timezone hoặc filesystem, cấu hình giá trị rõ ràng và ghi nhận giả định trong CI.

## 10. Cấu hình và kiểm chứng Maven Toolchains

Maven runtime và compiler JDK có thể khác nhau. Maven Toolchains cho phép chọn JDK compiler dựa trên yêu cầu của project.

Ví dụ settings toolchains.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>17</version>
      <vendor>any</vendor>
    </provides>
    <configuration>
      <jdkHome>C:\Java\jdk-17</jdkHome>
    </configuration>
  </toolchain>
</toolchains>
~~~

Đây là ví dụ cho Windows; trên Linux/macOS, jdkHome phải là path JDK thực tế của runner. File toolchains.xml thường nằm trong thư mục .m2 của user build.

POM có thể yêu cầu JDK toolchain và đặt release:

~~~xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
</properties>

<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-toolchains-plugin</artifactId>
      <version>3.2.0</version>
      <executions>
        <execution>
          <goals>
            <goal>toolchain</goal>
          </goals>
        </execution>
      </executions>
      <configuration>
        <toolchains>
          <jdk>
            <version>17</version>
          </jdk>
        </toolchains>
      </configuration>
    </plugin>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>3.13.0</version>
      <configuration>
        <release>${maven.compiler.release}</release>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Kiểm chứng Maven:

~~~powershell
.\mvnw.cmd -version
.\mvnw.cmd help:effective-pom
.\mvnw.cmd -X clean verify
~~~

- -version cho biết JVM chạy Maven.
- effective-pom cho biết cấu hình compiler sau khi kế thừa parent/profile.
- -X giúp xem chi tiết toolchain/compiler selection trong log debug.

Không kết luận compiler dùng JDK 17 chỉ từ mvn -version; lệnh đó báo JVM của Maven. Hãy kiểm tra log toolchain và compiler plugin để xác nhận JDK dùng cho compile.

## 11. Cấu hình và kiểm chứng Gradle Java Toolchains

Gradle có thể chọn JDK cho compile và test qua Java toolchain.

Groovy DSL:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Kotlin DSL:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Kiểm chứng:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat javaToolchains
.\gradlew.bat clean test
~~~

--version cho biết JVM chạy Gradle; javaToolchains liệt kê toolchain mà Gradle phát hiện; test xác nhận task thực tế chạy. Kiểm tra thêm org.gradle.java.home, Gradle JVM trong IDE và toolchain config nếu kết quả khác mong đợi.

Gradle daemon có thể tiếp tục chạy bằng JVM đã khởi động trước đó. Sau khi thay đổi môi trường, có thể dừng daemon rồi chạy lại:

~~~powershell
.\gradlew.bat --stop
~~~

## 12. Kiểm tra annotation processor và generated source

Annotation processor chạy trong quá trình compile và có thể phụ thuộc JDK/compiler API. Khi nâng JDK hoặc đổi toolchain, kiểm chứng:

- Processor version có hỗ trợ JDK/compiler mục tiêu không.
- Processor có được khai báo trong annotationProcessorPath hoặc cấu hình tương ứng không.
- Generated source có compile sạch không.
- Generated source có warning hoặc API mới hơn release mục tiêu không.
- Build có kết quả ổn định giữa các lần chạy không.

Không sửa generated file bằng tay rồi coi đó là bằng chứng. Hãy sửa cấu hình hoặc version processor, sau đó chạy clean build để source được sinh lại từ đầu.

## 13. Kiểm chứng dependency và module compatibility

Toolchain mới có thể làm lộ vấn đề trong dependency:

- Thư viện sử dụng JDK internal APIs.
- Thư viện chưa hỗ trợ runtime mới.
- Module descriptor yêu cầu module không có trong runtime image.
- Native library không có binary phù hợp OS/architecture.
- Multi-release JAR chọn implementation khác theo Java version.

Dùng dependency tree, jdeps và test integration để xác định nguồn vấn đề. Nếu ứng dụng dùng JPMS, kiểm tra module path và module descriptors bằng javac/java với đúng module options.

Với native dependency, cần CI matrix theo OS và architecture thật sự hỗ trợ. Một build pass trên Windows x64 không chứng minh native library hoạt động trên Linux ARM64.

## 14. Kiểm chứng tính tái lập của build

Reproducible build là khả năng tạo artifact giống nhau theo tiêu chí đã xác định khi dùng cùng source và môi trường toolchain tương đương.

Một quy trình cơ bản:

1. Checkout cùng commit vào hai workspace sạch.
2. Dùng cùng JDK, Maven/Gradle và dependency lock/version.
3. Chạy clean build ở cả hai workspace.
4. So sánh checksum artifact.
5. Nếu khác, kiểm tra timestamp, file ordering, generated metadata, absolute path và environment-dependent content.

Với Maven, có thể đặt project.build.outputTimestamp để chuẩn hóa timestamp của archive khi plugin hỗ trợ:

~~~xml
<properties>
  <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Ví dụ timestamp trên chỉ minh họa một giá trị cố định; dự án nên chọn chính sách timestamp phù hợp, thường lấy từ source-control commit metadata.

Không phải mọi artifact đều phải byte-for-byte giống nhau. Xác định trước tiêu chí: checksum giống hoàn toàn, nội dung archive giống sau khi bỏ metadata biến đổi, hay chỉ API/behavior tương đương.

## 15. Chọn CI matrix phù hợp

CI matrix nên bao phủ các tổ hợp có ý nghĩa với sản phẩm:

| Trục | Ví dụ lựa chọn |
|---|---|
| Runtime Java | Minimum supported JDK, current supported LTS |
| OS | Windows, Linux, macOS nếu có hỗ trợ |
| Architecture | x64, ARM64 nếu có native dependency |
| Build tool | Maven Wrapper hoặc Gradle Wrapper |
| Test scope | Unit ở mọi commit; integration/smoke ở PR hoặc release |

Ví dụ chính sách:

- Mỗi pull request: compile với --release mục tiêu, unit test và lint.
- Mỗi pull request: chạy test trên runtime tối thiểu được hỗ trợ.
- Theo lịch: chạy trên JDK LTS mới hơn để phát hiện deprecation/removal sớm.
- Trước release: full integration, smoke test, dependency analysis và reproducible build check.
- Khi nâng JDK: chạy toàn bộ OS/architecture matrix liên quan.

Không cần chạy mọi tổ hợp ở mọi commit nếu thời gian CI quá lớn. Chọn ma trận dựa trên rủi ro, sau đó đưa các kiểm tra còn lại vào lịch nightly hoặc release gate.

## 16. Ví dụ Java probe cho toolchain

Tạo file ToolchainProbe.java:

~~~java
public final class ToolchainProbe {
    private ToolchainProbe() {
    }

    public static void main(String[] args) {
        int feature = Runtime.version().feature();
        if (feature < 17) {
            throw new IllegalStateException("Java 17 or newer is required");
        }
        System.out.println("Toolchain check OK");
    }
}
~~~

Biên dịch với API và bytecode Java 17:

~~~powershell
javac --release 17 -Xlint:all -Werror -encoding UTF-8 -d out ToolchainProbe.java
~~~

Chạy:

~~~powershell
java -cp out ToolchainProbe
~~~

Stdout:

~~~text
Toolchain check OK
~~~

Kiểm tra bytecode:

~~~powershell
javap -verbose out\ToolchainProbe.class | Select-String "major version"
~~~

Với release 17, major version mong đợi là 61. Chương trình kiểm tra runtime feature tối thiểu, nhưng để xác nhận runtime 17 thật sự, vẫn phải chạy trên JDK/JRE 17 trong CI.

## 17. Kiểm tra âm tính: chứng minh API mới bị từ chối

Tạo file NewerApiProbe.java:

~~~java
import java.util.List;

public final class NewerApiProbe {
    public static void main(String[] args) {
        List<String> names = List.of("Java");
        System.out.println(names.getFirst());
    }
}
~~~

List.getFirst() được thêm từ Java 21. Khi sản phẩm nhắm Java 17, lệnh sau phải thất bại:

~~~powershell
javac --release 17 NewerApiProbe.java
~~~

Nếu chạy compiler mới với chỉ -source 17 -target 17, API trên JDK compiler có thể vẫn được nhìn thấy. Đó là lý do phép kiểm chứng API cần dùng --release chứ không chỉ kiểm tra class-file version.

Kiểm tra âm tính rất hữu ích: nó chứng minh compiler policy thực sự chặn một API vượt release mục tiêu, thay vì chỉ chứng minh một ví dụ hợp lệ biên dịch được.

## 18. Ma trận chọn phép kiểm chứng

| Câu hỏi | Kiểm tra tối thiểu | Bằng chứng mạnh hơn |
|---|---|---|
| Tool chạy bằng JDK nào? | java -version, mvn/gradle --version | Log compiler toolchain selection |
| Compiler có đúng release? | POM/Gradle config | Compile bằng --release và kiểm tra âm tính |
| Bytecode đúng version? | javap major version | Kiểm tra artifact của mọi module |
| API có tương thích? | javac --release | Dependency analysis và runtime test |
| Runtime tối thiểu có chạy? | Smoke test | Full test suite trên JDK tối thiểu |
| Dependency tương thích? | Dependency tree | jdeps, integration test, vendor matrix |
| OS/architecture có hỗ trợ? | CI matrix | Native integration tests trên từng runner |
| Build có tái lập? | Build hai lần | So sánh checksum từ hai clean workspace |

Nếu rủi ro thấp, chọn phép kiểm tra tối thiểu có thể chứng minh yêu cầu. Nếu rủi ro cao hoặc thay đổi có phạm vi rộng, kết hợp nhiều bằng chứng độc lập.

## 19. Những sai lầm khi kiểm chứng toolchain

| Sai lầm | Vì sao không đủ | Cách làm đúng |
|---|---|---|
| Chỉ chạy java -version | Không cho biết compiler JDK hoặc toolchain riêng | Kiểm tra compiler selection và build tool |
| Chỉ đọc POM/build.gradle | Parent, profile hoặc IDE có thể override | Xem effective config và log thực thi |
| Chỉ kiểm tra major version | Không chứng minh API tương thích | Compile bằng --release |
| Compile bằng JDK mới rồi chạy cùng JDK đó | Không chứng minh runtime tối thiểu | Chạy trên runtime thấp nhất được hỗ trợ |
| Chỉ chạy unit test | Có thể bỏ sót tích hợp, native library và startup | Thêm integration/smoke test theo rủi ro |
| Chỉ test trên Windows | Không chứng minh Linux/macOS | CI matrix cho OS mục tiêu |
| Chỉ kiểm tra dependency tree | Không chứng minh dependency chạy được | jdeps và integration test |
| Chỉ build một lần | Không phát hiện artifact biến đổi do môi trường | Build hai clean workspace và so sánh |
| Dùng source/target thay --release | Có thể tham chiếu API mới | Dùng --release |

## 20. Quy trình thiết kế verification plan

Khi bắt đầu thiết kế toolchain, thực hiện lần lượt:

1. Ghi runtime tối thiểu, compiler JDK, OS/architecture và build tool được hỗ trợ.
2. Xác định yêu cầu nào có thể xác minh bằng cấu hình và yêu cầu nào cần chạy thật.
3. Chọn kiểm tra nhanh cho mỗi pull request.
4. Chọn kiểm tra runtime/dependency/OS cho nightly hoặc release.
5. Thêm negative test để chứng minh policy chặn cấu hình/API sai.
6. Lưu version và log toolchain trong CI.
7. Định nghĩa artifact hoặc output nào phải được lưu làm evidence.
8. Ghi tiêu chí pass/fail rõ ràng cho từng kiểm tra.
9. Khi nâng JDK/plugin, chạy lại các kiểm tra bị ảnh hưởng.
10. Review verification plan cùng thay đổi toolchain, không chỉ review file cấu hình.

Verification plan tốt phải có owner, runner, command, expected result và nơi lưu log. Khi build fail, người khác có thể tái hiện và hiểu chính xác mệnh đề nào chưa được chứng minh.

## 21. Checklist chọn cách kiểm chứng

- [ ] Runtime tối thiểu và compiler JDK đã được xác định riêng.
- [ ] JDK thực tế của Maven/Gradle đã được ghi nhận.
- [ ] POM/Gradle effective config đã được kiểm tra.
- [ ] Compile dùng --release cho Java API mục tiêu.
- [ ] Có negative test cho API mới hơn release khi phù hợp.
- [ ] Class-file major version đã được kiểm tra ở artifact quan trọng.
- [ ] Runtime tối thiểu được chạy test thực tế.
- [ ] Dependency và JDK internal API được kiểm tra khi có rủi ro.
- [ ] Annotation processor và generated source được kiểm chứng.
- [ ] OS/architecture mục tiêu có CI runner phù hợp.
- [ ] Có unit/integration/smoke test theo rủi ro.
- [ ] Có quy trình kiểm tra reproducible build nếu yêu cầu.
- [ ] Log ghi JDK vendor/version, build tool và OS.
- [ ] Mỗi phép kiểm chứng có expected result và owner.
- [ ] Verification plan được chạy lại khi nâng JDK hoặc build plugin.

Chọn cách kiểm chứng bằng cách bắt đầu từ yêu cầu cần chứng minh. Cấu hình cho biết điều nhóm muốn; log lựa chọn toolchain cho biết công cụ đã chọn gì; compile, bytecode inspection, runtime tests và CI matrix cho biết kết quả thực tế. Kết hợp các lớp bằng chứng theo rủi ro giúp Java toolchain có thể giải thích, tái hiện và tin cậy khi thay đổi.

## Tài liệu tham khảo

- Oracle Java SE 17 — The javac Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- Oracle Java SE 17 — The javap Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
- Oracle Java SE 17 — The jdeps Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html
- Apache Maven — Guide to Using Toolchains: https://maven.apache.org/guides/mini/guide-using-toolchains.html
- Apache Maven Compiler Plugin: https://maven.apache.org/plugins/maven-compiler-plugin/
- Apache Maven — Guide to Reproducible Builds: https://maven.apache.org/guides/mini/guide-reproducible-builds.html
- Gradle — Java Toolchains: https://docs.gradle.org/current/userguide/toolchains.html
- Gradle — JavaCompile: https://docs.gradle.org/current/dsl/org.gradle.api.tasks.compile.JavaCompile.html
