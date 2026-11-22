# Tách mã nguồn chính, kiểm thử và mã được sinh trong dự án Java

## 1. Vì sao phải tách các loại mã nguồn?

Một dự án Java có thể chứa ba loại mã nhìn bề ngoài đều là tệp `.java`, nhưng có vai trò và vòng đời khác nhau:

- **Mã nguồn chính (main/production sources)**: do lập trình viên duy trì, tạo nên ứng dụng hoặc thư viện được phân phối.
- **Mã kiểm thử (test sources)**: dùng để xác minh hành vi của mã chính; chỉ cần trong quá trình kiểm thử và phát triển, thường không đi vào JAR sản phẩm.
- **Mã được sinh (generated sources)**: do annotation processor, bộ sinh API client, bộ sinh mã từ schema hoặc một công cụ build tạo ra từ đầu vào xác định. Không chỉnh tay bản đầu ra vì lần sinh tiếp theo có thể ghi đè.

Việc tách đúng không đơn thuần là đặt tệp vào ba thư mục. Công cụ build phải biết **nguồn đầu vào, thứ tự sinh/biên dịch, classpath và thư mục đầu ra** của từng loại. Nhờ vậy có thể tái lập bản build, chỉ chạy phần cần thiết khi mã đổi, tránh để thư viện kiểm thử lọt vào ứng dụng và ngăn mã sinh cũ che giấu lỗi.

Một mô hình tổng quát:

```text
Mã nguồn đầu vào / cấu hình generator
             │
             ▼
       Chạy generator
             │
             ▼
   generated sources (.java) ─────┐
                                  │
src/main/java ────────────────────┼──► compile main ──► classes/main ──► JAR
                                  │
src/main/resources ───────────────┘                   (resources được copy)
                                         │
src/test/java ───────────────────────────┼──► compile test ──► classes/test ──► run tests
src/test/resources ──────────────────────┘
```

Ở sơ đồ này, mã kiểm thử **phụ thuộc vào kết quả biên dịch của main**. Chiều ngược lại không được tồn tại: một class trong `src/main/java` không nên import class chỉ nằm trong `src/test/java`.

## 2. Quy ước bố trí thư mục

Với một dự án Java theo thông lệ Gradle/Maven:

```text
project/
├── src/
│   ├── main/
│   │   ├── java/example/             # Java do người viết, dùng trong sản phẩm
│   │   └── resources/                # cấu hình, mẫu, tài nguyên sản phẩm
│   └── test/
│       ├── java/example/             # mã test, test fixtures đơn giản
│       └── resources/                # dữ liệu kiểm thử
├── tools/                             # mã công cụ sinh mã, nếu dự án có
├── build/                             # kết quả do Gradle tạo, không phải mã nguồn gốc
│   ├── generated/sources/.../         # Java do công cụ sinh
│   ├── classes/java/main/
│   ├── classes/java/test/
│   ├── resources/main/
│   └── resources/test/
└── build.gradle
```

Đây là ví dụ bố trí **Gradle**. Trong Maven, thư mục đầu ra tương ứng thường ở `target/`, ví dụ `target/classes`, `target/test-classes`, `target/generated-sources`. Không cố định đường dẫn đầu ra theo suy đoán khi dự án hoặc plugin đã cấu hình khác.

| Nguồn | Ai sở hữu? | Thường nằm ở đâu? | Có trong sản phẩm? |
| --- | --- | --- | --- |
| Production Java | Lập trình viên | `src/main/java` | Có, dưới dạng `.class` |
| Production resources | Lập trình viên | `src/main/resources` | Thường có |
| Test Java | Lập trình viên | `src/test/java` | Thường không |
| Test resources | Lập trình viên | `src/test/resources` | Không |
| Generated Java cho main | Generator/build | `build/generated/sources/.../java` | Class đã biên dịch có thể có |
| Generated Java cho test | Generator/build | Khu vực generated riêng cho test | Chỉ phục vụ test |
| Compiled output | Compiler | `build/classes/...` | Class main dùng để đóng gói |

**Source root khác package.** Tệp `src/main/java/example/App.java` có thể khai báo `package example;`. Khi đặt một nguồn sinh ở `build/generated/sources/buildInfo/java/example/BuildInfo.java`, cả hai class cùng package `example` nhưng ở **hai source root** khác nhau. Package name quyết định namespace Java; source root cho build tool biết nơi tìm tệp nguồn. Thư mục `build/classes/java/main/example` là **đầu ra nhị phân**, không được dùng làm source root.

## 3. Ranh giới phụ thuộc và classpath

Quy tắc cơ bản:

1. **Main compile classpath** gồm thư viện cần để biên dịch mã sản phẩm. Nó không được phụ thuộc vào thư viện chỉ dành cho test.
2. **Test compile classpath** cần các class main đã biên dịch, các thư viện main cần thiết và thư viện test như JUnit/Mockito khi dùng.
3. **Test runtime classpath** cần class test, class main, tài nguyên và dependency lúc chạy test.
4. **Generator** cần chạy trước nhiệm vụ biên dịch nào sử dụng kết quả của nó. Thư viện chạy generator có thể thuộc cấu hình riêng; không tự động biến chúng thành dependency runtime của sản phẩm.
5. **Generated sources** phải được khai báo cho đúng source set (`main` hoặc `test`), còn `generated .class` là đầu ra của compiler, không phải tệp nguồn cho lần compile kế tiếp.

Lỗi điển hình là thêm `src/test/java` vào source set `main` cho “biên dịch cho dễ”. Khi đó test helper và dependency kiểm thử có thể lọt vào đường build sản phẩm, đồng thời tạo vòng phụ thuộc. Cách đúng là sửa classpath của **test** hoặc trích logic dùng chung thật sự sang main/module dùng chung thích hợp.

## 4. Ví dụ chạy được với JDK 17+: main, test và generator

Ví dụ sau không cần thư viện ngoài. Mã chính gọi một class `BuildInfo` được sinh trước lúc biên dịch; một chương trình smoke test kiểm tra `App.greet`. Tạo đúng ba tệp *do người viết* dưới đây.

### 4.1. Công cụ sinh mã: `tools/BuildInfoGenerator.java`

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class BuildInfoGenerator {
    public static void main(String[] args) throws Exception {
        Path output = Path.of(
            "build/generated/sources/buildInfo/java/example/BuildInfo.java"
        );
        Files.createDirectories(output.getParent());

        String source = """
            package example;

            public final class BuildInfo {
                public static final String VERSION = "1.0-demo";

                private BuildInfo() {}
            }
            """;

        Files.writeString(output, source, StandardCharsets.UTF_8);
    }
}
```

`Path.of` và `Files.writeString` có từ Java 11; text block có sẵn trong Java 17. Generator ghi tệp có đường dẫn xác định, nội dung xác định và tự tạo thư mục cha. Trong bài này generator nằm dưới `tools/` để ranh giới với application code rõ ràng. Trong dự án thực tế, generator có thể là một plugin, annotation processor hoặc tác vụ build.

### 4.2. Mã chính: `src/main/java/example/App.java`

```java
package example;

public class App {
    public static String greet(String name) {
        return "Xin chào, " + name + "!";
    }

    public static void main(String[] args) {
        System.out.println(greet("Java"));
        System.out.println(BuildInfo.VERSION);
    }
}
```

`App` tham chiếu `BuildInfo` dù tệp đó chưa được lưu trong `src/main/java`. Nó sẽ được compiler nhìn thấy khi ta đưa **cả source root của main và tệp sinh** vào đầu vào biên dịch.

### 4.3. Mã kiểm thử: `src/test/java/example/AppSmokeTest.java`

```java
package example;

public class AppSmokeTest {
    public static void main(String[] args) {
        String actual = App.greet("Java");
        if (!"Xin chào, Java!".equals(actual)) {
            throw new AssertionError("Unexpected greeting: " + actual);
        }
        System.out.println("TEST OK");
    }
}
```

Đây là một **smoke test tự chạy bằng `main`**, không phải JUnit test và sẽ không tự được Gradle `test` phát hiện. Nó dùng `AssertionError` tường minh, vì thế không cần tùy chọn `-ea`. Trong hệ thống kiểm thử thông thường, đặt các phương thức `@Test` của JUnit trong `src/test/java` và để test runner chạy chúng.

### 4.4. Biên dịch theo từng pha

Từ thư mục `project/`, thực hiện trong shell kiểu Bash trên Linux/macOS hoặc Git Bash:

```bash
mkdir -p build/tools build/classes/java/main build/classes/java/test

# (1) Biên dịch và chạy công cụ sinh mã.
javac -d build/tools tools/BuildInfoGenerator.java
java -cp build/tools BuildInfoGenerator

# (2) Biên dịch main cùng tệp Java đã sinh.
javac -d build/classes/java/main \
  src/main/java/example/App.java \
  build/generated/sources/buildInfo/java/example/BuildInfo.java

# (3) Biên dịch test: class main nằm trên test compile classpath.
javac -cp build/classes/java/main \
  -d build/classes/java/test src/test/java/example/AppSmokeTest.java

# (4) Chạy ứng dụng; class test không nằm trên classpath này.
java -cp build/classes/java/main example.App

# (5) Chạy smoke test với cả main classes và test classes.
java -cp build/classes/java/main:build/classes/java/test example.AppSmokeTest
```

Kết quả chính xác của hai lệnh `java` cuối:

```text
Xin chào, Java!
1.0-demo
TEST OK
```

Trên PowerShell/Windows, có thể dùng `New-Item -ItemType Directory -Force` để tạo thư mục hoặc để `javac` tự tạo thư mục đích khi các thư mục cha đã có. Quan trọng nhất là **dấu phân cách classpath trên Windows là `;`**, thay vì `:` trên Unix. Ví dụ lệnh smoke test:

```powershell
java -cp 'build/classes/java/main;build/classes/java/test' example.AppSmokeTest
```

Lưu ý lệnh `javac -d` ghi `.class` vào một cây thư mục khác nguồn vào; không dùng `-d src/main/java`. Với project lớn, công cụ build quản lý source roots, dependency và các tác vụ, không cần liệt kê từng tệp `.java` thủ công như bản minh họa này.

### 4.5. Thử tình huống sai thứ tự

Nếu bỏ bước sinh `BuildInfo.java` rồi cố biên dịch riêng `App.java` trong một cây build sạch, `javac` sẽ không tìm thấy symbol `BuildInfo`. Nếu biên dịch `AppSmokeTest.java` mà không đưa `build/classes/java/main` vào `-cp`, compiler sẽ không tìm thấy `App`. Đây là **hai lỗi khác nhau**: thiếu generated input trước main compile và thiếu main output trên test compile classpath. Việc test đã biên dịch thành công trước đó không chứng minh dependency graph hiện tại đúng nếu `build/` còn giữ file cũ.

## 5. Biểu diễn cùng nguyên tắc bằng Gradle

Với plugin Java, Gradle có sẵn source sets `main` và `test`, theo mặc định đọc `src/main/java`, `src/main/resources`, `src/test/java`, `src/test/resources`. Các tác vụ quen thuộc là `compileJava`, `processResources`, `classes`, `compileTestJava`, `processTestResources`, `testClasses` và `test`.

Ví dụ `build.gradle` dùng Groovy DSL: tác vụ tạo `BuildInfo.java` được khai báo là **producer của một thư mục đầu ra**, sau đó thư mục đó được đăng ký làm đầu vào Java của `main`.

```groovy
plugins {
    id 'java'
}

def generatedJavaDir =
    layout.buildDirectory.dir('generated/sources/buildInfo/java')

def generateBuildInfo = tasks.register('generateBuildInfo') {
    outputs.dir(generatedJavaDir)

    doLast {
        def output = generatedJavaDir.get()
            .file('example/BuildInfo.java').asFile
        output.parentFile.mkdirs()
        output.setText('''package example;

public final class BuildInfo {
    public static final String VERSION = "1.0-demo";
    private BuildInfo() {}
}
''', 'UTF-8')
    }
}

sourceSets {
    main {
        java.srcDir(generateBuildInfo)
    }
}
```

Ở ví dụ Gradle, chính tác vụ `generateBuildInfo` sinh class, nên **không cần chạy thêm `tools/BuildInfoGenerator.java`** của phần biên dịch thủ công. `sourceSets.main.java.srcDir(generateBuildInfo)` dùng output của task provider làm source directory và truyền quan hệ phụ thuộc tác vụ cho Gradle. `compileJava` nhận đầu ra task sinh mã; `compileTestJava` nhận output main và test source. `outputs.dir` giúp Gradle biết sản phẩm của generator và là một phần cơ sở để theo dõi up-to-date/cache.

Có thể kiểm tra bằng `./gradlew classes` trên Linux/macOS hoặc `gradlew.bat classes` trên Windows, khi dự án có Gradle Wrapper. Nếu muốn chạy `gradle test` theo cách chuẩn, viết JUnit test và khai báo dependency/test framework tương ứng; `AppSmokeTest.main` ở trên chỉ chạy bằng lệnh `java` riêng.

**Tránh hai lỗi cấu hình Gradle:**

- Không thêm output sinh mã dưới `src/main/java` để “Gradle tự nhìn thấy”. Điều đó trộn file do công cụ quản lý vào Git và khiến `clean` không tách bạch được.
- Không đưa đường dẫn build-generated vào source root dưới dạng chuỗi cố định mà quên khai báo quan hệ sinh mã. Một build có thể tình cờ chạy được nhờ file cũ, nhưng thất bại sau `clean` hoặc khi CI chạy song song.

Nếu generator thực tế cần annotation processing, dùng cấu hình processor thích hợp (ví dụ `annotationProcessor` cho Java source set main). Mã processor không mặc nhiên là runtime dependency của ứng dụng. Nếu sinh cả mã test, đầu ra đó phải thuộc source set `test`, không phải `main`. Các plugin generator khác nhau có cách đăng ký task và source roots riêng; luôn kiểm tra tài liệu plugin thay vì chỉ thêm một thư mục vào IDE.

## 6. Generated source, resources và compiled output không giống nhau

Ba kiểu đầu ra cần phân biệt:

- **Generated source**: tệp có cú pháp ngôn ngữ nguồn, như `BuildInfo.java`. Compiler còn phải đọc nó để tạo `.class`.
- **Generated resource**: JSON, YAML, XML, metadata, file bản địa hóa hoặc tài nguyên khác được tạo từ đầu vào. Chúng cần được nối vào quá trình `processResources` hoặc nhiệm vụ tài nguyên phù hợp, thường được copy chứ không biên dịch như Java.
- **Compiled output**: `.class` từ compiler hay bytecode producer. Không nên tự coi thư mục `.class` là một thư mục Java source. Chúng được dùng qua classpath hoặc đầu ra đóng gói.

Annotation processor có thể sinh mã trong lúc `compileJava`; nguồn được sinh khi đó thuộc một thư mục generated do compiler/build task quản lý. Không khẳng định mọi generator đều phải có một tác vụ riêng chạy **trước** `compileJava`: quan hệ chính xác phụ thuộc cơ chế sinh mã. Điều bắt buộc là build biết ai tạo đầu ra và ai tiêu thụ đầu ra.

**IDE đánh dấu “generated sources root” là tiện ích điều hướng**, không thay thế cấu hình build. Kiểm chứng sau `clean` và chạy build từ dòng lệnh/CI mới giúp phát hiện cấu hình source set hoặc task dependency bị thiếu.

## 7. Kiểm thử có loại nguồn riêng

Đối với test, việc phân tách còn gồm dữ liệu, dependency và phạm vi thực thi:

- Mã test có thể import public API và các API cấp package của main khi cùng package; không ép application code phụ thuộc ngược vào test utility.
- Dữ liệu giả, test fixtures và cấu hình phục vụ test nên ở `src/test/resources` hoặc một test-fixtures source set/module chuyên dụng nếu cần dùng chung rộng hơn.
- Những tệp generated chỉ phục vụ test (chẳng hạn test stubs) phải nằm trong output generator của test và vào **test compile classpath**.
- Unit tests nên độc lập với file sinh từ một build trước; integration tests có thể cần source set/task riêng, nhưng không gộp mọi thứ vào main.
- Một tệp test ở `src/test/java` **không bảo đảm sẽ được test runner phát hiện**: còn tùy naming, framework, annotations và cấu hình task. Ví dụ `AppSmokeTest` chạy tay minh họa chính điểm này.

Trong thư viện phát hành, main classes và main resources có thể được đóng vào JAR; test classes và test resources thường bị loại. Xác minh sản phẩm đóng gói thực tế khi cấu hình tùy chỉnh packaging, thay vì dựa hoàn toàn vào tên thư mục.

## 8. Tính tái lập, quản lý Git và an toàn khi sinh mã

Một pipeline sinh mã bền vững cần đáp ứng các nguyên tắc sau.

**Đầu vào rõ ràng:** generator nhận schema, interface, cấu hình, phiên bản công cụ và mọi input cần thiết. Nếu version/schema đổi, output cần được tạo lại. Không phụ thuộc vào trạng thái máy cá nhân, clock hay thư mục tạm không được khai báo nếu muốn output tái lập.

**Đầu ra tách biệt:** generator chỉ ghi vào thư mục do mình sở hữu, ví dụ `build/generated/sources/<tool>/java`; không đè file do người viết. Hai generator khác nhau cần output directory riêng để tránh ghi tranh nhau và để cleanup có phạm vi.

**Dọn build sạch:** chạy `clean` rồi `build` ở môi trường sạch để chứng minh không dựa vào generated file còn sót. Với Gradle, khai báo inputs/outputs và quan hệ task đúng để up-to-date checking, build cache và thực thi song song hoạt động đáng tin. Nếu generator không có đầu vào khai báo đầy đủ hoặc kết quả không ổn định, cache/up-to-date có thể sai dù có `outputs.dir`.

**Quy ước Git:** thường chỉ commit mã chính, test, schema và cấu hình generator; ignore `build/` hoặc `target/`. Có trường hợp chủ động commit generated source (ví dụ để phân phối SDK hoặc phục vụ công cụ không chạy generator), nhưng đó là quyết định của dự án: phải nêu nguồn chân lý, cách tái sinh và quy trình kiểm tra diff. Không sửa riêng tệp generated mà bỏ qua input sinh ra nó.

**Tránh lộ ranh giới:** không đưa secrets, đường dẫn máy cá nhân, dữ liệu nhạy cảm hay timestamp ngẫu nhiên vào generated artifacts nếu chúng sẽ được đóng gói hoặc công khai. Không để dependency test xuất hiện trong production runtime chỉ vì generator hoặc test cần chúng.

## 9. Những triệu chứng thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Kiểm tra/sửa |
| --- | --- | --- |
| `cannot find symbol BuildInfo` khi compile main | Chưa sinh tệp hoặc chưa khai báo generated source root | Kiểm tra generator output và dependency từ `compileJava` tới producer |
| Test compile báo không tìm thấy `App` | Thiếu main classes trên test compile classpath | Kiểm tra source set `test`, output `main` và classpath |
| Build chạy ở IDE nhưng hỏng trên CI | IDE nhận thư mục generated cũ; build task thiếu dependency | `clean` và build từ command line; khai báo producer/consumer trong build |
| Build chỉ qua khi không chạy `clean` | Đang dùng artifact cũ | Xóa output bằng task clean; tái tạo toàn bộ từ nguồn gốc |
| Mã sinh bị sửa rồi mất thay đổi | Chỉnh tay output | Sửa schema/template/generator rồi tái sinh |
| Test library xuất hiện trong JAR | Main lẫn test hoặc dependency scope sai | Kiểm tra source sets và dependency configurations, sau đó inspect JAR |
| Cùng class được định nghĩa hai lần | Mã sinh bị copy vào source chính hoặc hai generator cùng sinh một class | Chọn một nguồn sở hữu class; bỏ bản trùng ở source roots |
| Test không chạy dù compile thành công | Test runner không nhận diện test | Kiểm tra framework/annotation/naming, cấu hình `test` task |

## 10. Checklist để tự đánh giá một dự án

Một cấu hình tốt có thể trả lời được các câu hỏi:

1. File do người viết và file do generator có **owner** và thư mục riêng chưa?
2. Có phân biệt `main` và `test` về source roots, resources, classpath và sản phẩm đóng gói chưa?
3. Task nào tạo từng generated directory và task nào tiêu thụ nó? Quan hệ đó có được mô tả bằng cấu hình build thay vì thao tác thủ công trong IDE không?
4. Chạy từ checkout sạch (không có `build/`/`target/`) có tạo được tất cả nguồn sinh và compile/test thành công không?
5. Việc sửa input generator có làm cập nhật output phù hợp, còn không đổi input thì tránh sinh/biên dịch thừa không?
6. Có thể đọc JAR cuối và xác nhận **không chứa** test classes, test fixtures hoặc thư viện test ngoài ý muốn không?

**Bài thực hành:** thử xóa riêng thư mục `build/generated/sources/buildInfo/java` trong ví dụ, rồi chạy lại chuỗi lệnh bắt đầu từ generator; sau đó thử bỏ bước generator trên một build sạch để quan sát lỗi `javac`. Cuối cùng cấu hình `generateBuildInfo` trong Gradle và xác minh `classes` tự tạo mã. Ba phép thử này lần lượt kiểm chứng tính tái sinh, thứ tự dependency và việc build tool thực sự sở hữu generated source.