# Maven là gì và Maven giải quyết những vấn đề nào khi build Java?

## 1. Bối cảnh: từ mã nguồn Java đến một bản build có thể dùng được

Viết xong các tệp `.java` chưa có nghĩa là đã tạo được một ứng dụng hoặc thư viện sẵn sàng bàn giao. Một quy trình build Java thực tế có thể cần:

1. Kiểm tra cấu hình và phiên bản Java.
2. Tải các thư viện bên ngoài, bao gồm cả thư viện mà chúng phụ thuộc.
3. Biên dịch mã nguồn và tài nguyên theo đúng classpath.
4. Biên dịch, chạy kiểm thử và báo lỗi khi kiểm thử thất bại.
5. Đóng gói các tệp thành JAR/WAR, tạo báo cáo, thực hiện kiểm tra chất lượng.
6. Cung cấp cùng một quy trình cho máy lập trình viên và môi trường CI.
7. Đưa artifact đã build lên kho nội bộ hoặc kho phân phối khi cần.

Với chương trình chỉ có một tệp Java, ta có thể làm thủ công:

```bash
javac -d out src/main/java/com/example/App.java
java -cp out com.example.App
```

Tuy nhiên, khi dự án có nhiều lớp, JUnit, thư viện JSON, JDBC, nhiều module hoặc hàng loạt bước kiểm tra, các lệnh thủ công trở nên khó duy trì. Một máy có thể build được vì có sẵn JAR trong IDE; máy khác có thể thất bại vì thiếu thư viện, chọn sai phiên bản hoặc dùng khác JDK. Đây là nhóm vấn đề Maven được thiết kế để giải quyết.

## 2. Maven là gì?

**Apache Maven** là công cụ **tự động hóa build và quản lý dependency** cho dự án, đặc biệt phổ biến trong hệ sinh thái Java. Thay vì mỗi lập trình viên tự nhớ các lệnh biên dịch, tải JAR và đóng gói, dự án mô tả cấu hình trong **Project Object Model (POM)**, thường là tệp `pom.xml` ở thư mục gốc. Maven dựa vào cấu hình đó, một cấu trúc dự án theo quy ước và hệ thống plugin để thực hiện các bước build.

Có bốn ý tưởng nền tảng:

- **Project model:** `pom.xml` khai báo danh tính, dependency, plugin, cấu hình build và có thể là quan hệ module/parent.
- **Convention over configuration:** Maven hiểu các thư mục chuẩn như `src/main/java` và `src/test/java` mà không cần cấu hình lại từng đường dẫn.
- **Build lifecycle:** các bước từ kiểm tra đến biên dịch, test, đóng gói, xác minh và phân phối được gọi bằng những phase thống nhất.
- **Dependency repository:** Maven tự giải quyết, tải và lưu đệm artifact cùng dependency dựa trên tọa độ, phiên bản và các kho đã cấu hình.

Maven **không phải** JDK, trình biên dịch Java, máy ảo JVM, IDE hay framework ứng dụng. Maven điều phối compiler/plugin và thư viện cần thiết; `javac` vẫn là công cụ biên dịch Java thông dụng bên dưới.

## 3. Các vấn đề cụ thể Maven giải quyết

| Vấn đề khi làm thủ công | Maven hỗ trợ như thế nào | Lợi ích thực tế |
| --- | --- | --- |
| Phải liệt kê từng tệp, đường dẫn khi biên dịch | Quy ước thư mục và Compiler Plugin | Cùng một cách build khi dự án mở rộng |
| Sao chép JAR bằng tay, tự ghép classpath | Khai báo `dependencies` và tự phân giải artifact | Ít lỗi thiếu thư viện, dễ đọc danh sách dependency |
| Một thư viện còn phụ thuộc thư viện khác | Phân giải dependency bắc cầu (transitive) | Không cần truy tìm toàn bộ JAR con bằng tay |
| Mỗi máy sử dụng lệnh build khác nhau | Lệnh phase chuẩn như `mvn test`, `mvn verify` | Quy trình nhất quán giữa máy cá nhân và CI |
| Dễ quên chạy test trước khi đóng gói | Plugin test gắn vào lifecycle | Bản build có thể bị chặn khi test thất bại |
| Khó thống nhất đầu ra JAR/WAR và metadata | `packaging` và plugin đóng gói | Artifact có tên, phiên bản, cấu trúc dự đoán được |
| Chia sẻ thư viện nội bộ khó khăn | `mvn install` hoặc `mvn deploy` theo đúng mục đích | Module khác có thể dùng artifact qua repository |
| Nhiều module cần cấu hình chung | Parent POM, aggregator, `dependencyManagement` và `pluginManagement` | Giảm cấu hình lặp và lệch phiên bản |

Maven không xóa bỏ mọi vấn đề. Dependency vẫn có thể xung đột, test vẫn có thể viết sai, và build chỉ thực sự lặp lại đáng tin cậy nếu quản lý tốt phiên bản plugin, JDK, repository, cấu hình môi trường và đầu vào.

## 4. Những khái niệm cần nắm trước khi chạy Maven

### 4.1. POM và tọa độ của artifact

Ba trường cơ bản nhận diện một artifact là:

- `groupId`: tên nhóm/tổ chức, ví dụ `com.example`;
- `artifactId`: tên dự án/artifact, ví dụ `hello-maven`;
- `version`: phiên bản, ví dụ `1.0.0`.

Bộ này thường được gọi là **GAV** (`groupId:artifactId:version`). Với `packaging=jar`, bản build minh họa có thể tạo `target/hello-maven-1.0.0.jar`. `modelVersion=4.0.0` là phiên bản **mô hình POM** thường dùng, không có nghĩa là đang chạy Maven bản 4.0.0. Nếu không khai báo `packaging`, kiểu đóng gói mặc định của dự án Maven thông thường là `jar`.

Trong `pom.xml`, **`dependencies`** mô tả thư viện mà dự án sử dụng; **`build/plugins`** mô tả công cụ thực hiện thao tác build. Chẳng hạn JUnit là dependency dùng để viết/chạy test, còn Surefire là plugin kích hoạt việc chạy test trong lifecycle. Hai vai trò này khác nhau.

### 4.2. Quy ước thư mục

```text
hello-maven/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── com/example/App.java
    └── test/
        └── java/
            └── com/example/AppTest.java
```

- `src/main/java`: mã Java của ứng dụng/thư viện.
- `src/main/resources`: tài nguyên runtime (nếu có).
- `src/test/java`: mã kiểm thử.
- `src/test/resources`: tài nguyên kiểm thử (nếu có).
- `target/`: các tệp tạo ra khi build, gồm class biên dịch, báo cáo test và JAR/WAR; không nên xem là mã nguồn.

Dùng cấu trúc chuẩn giúp plugin và IDE tìm đúng nguồn/test mà không phải viết những script đường dẫn riêng.

### 4.3. Repository và dependency bắc cầu

Maven thường lấy dependency từ repository được cấu hình (ví dụ Maven Central), lưu bản đã tải vào repository cục bộ mặc định `~/.m2/repository` (trên Windows thường nằm trong thư mục người dùng tại `.m2\repository`). Lần build tiếp theo có thể tái sử dụng các artifact đã có. Các tổ chức thường dùng thêm mirror hoặc repository manager nội bộ.

Ví dụ dự án A phụ thuộc B; B lại phụ thuộc C. Maven có thể phân giải C như **transitive dependency** mà A không phải khai báo C chỉ để B hoạt động. Tuy vậy, nếu mã của A **trực tiếp import** API thuộc C, A nên khai báo C rõ ràng để tránh phụ thuộc ngầm vào cấu trúc nội bộ của B.

Khi gặp nhiều phiên bản của cùng artifact, Maven áp dụng quy tắc hòa giải dependency (thường ưu tiên đường phụ thuộc gần dự án hơn; nếu cùng độ sâu, thứ tự khai báo có thể quyết định). Do đó, “Maven tự tải đúng tất cả thư viện” không có nghĩa là mọi xung đột phiên bản đã biến mất. Lệnh `mvn dependency:tree` giúp nhìn thấy cây dependency.

**Dependency scope** xác định thư viện có mặt ở giai đoạn nào:

| Scope | Ý nghĩa điển hình |
| --- | --- |
| `compile` (mặc định) | Dùng khi biên dịch và chạy; có thể truyền sang dự án phụ thuộc |
| `test` | Chỉ phục vụ biên dịch/chạy kiểm thử, ví dụ JUnit |
| `runtime` | Cần lúc chạy và test, không cần ở classpath biên dịch |
| `provided` | Có khi compile/test nhưng môi trường chạy dự kiến cung cấp, ví dụ Servlet API trong container |

Các scope khác như `system` và `import` có trường hợp sử dụng đặc biệt; `system` thường nên tránh trong cấu hình mới vì ràng buộc đường dẫn máy cục bộ, còn `import` chỉ dùng cho POM trong `dependencyManagement` (ví dụ BOM).

### 4.4. Lifecycle, phase và plugin goal

Maven có các lifecycle chuẩn, trong đó `default` phục vụ build/phân phối, `clean` dọn đầu ra build và `site` tạo site tài liệu dự án.

Các phase hay dùng trong lifecycle `default`:

| Phase | Việc thực hiện chủ yếu |
| --- | --- |
| `validate` | Kiểm tra tính hợp lệ/cấu hình cần thiết của dự án |
| `compile` | Biên dịch mã nguồn chính |
| `test` | Biên dịch và chạy unit test bằng plugin/framework phù hợp |
| `package` | Đóng gói JAR/WAR tùy `packaging` |
| `verify` | Thực hiện các bước xác minh đã cấu hình (có thể gồm kiểm tra tích hợp/chất lượng) |
| `install` | Đưa artifact vào **repository cục bộ** để dự án khác trên máy dùng |
| `deploy` | Đưa artifact lên **repository từ xa** được cấu hình |

Gọi một phase sẽ chạy các phase trước nó trong **cùng lifecycle**. Ví dụ `mvn package` thường biên dịch, chạy test và đóng gói; `mvn verify` chạy các phase đến `verify`. Riêng `clean` thuộc lifecycle khác: `mvn clean verify` trước tiên dọn đầu ra build cũ rồi chạy lifecycle `default` đến `verify`.

**Phase** là mốc của quy trình; **goal** là tác vụ cụ thể do plugin thực hiện. Ví dụ trong dự án JAR, Compiler Plugin có goal `compiler:compile` gắn vào phase `compile`, Surefire Plugin có `surefire:test` gắn vào phase `test`. Có thể gọi trực tiếp goal như `mvn dependency:tree` mà không cần gọi phase.

**Lưu ý:** `verify` không tự tạo một bộ kiểm thử tích hợp hay bộ quy tắc chất lượng; các kiểm tra bổ sung cần được cấu hình plugin thích hợp.

## 5. Ví dụ chạy được với Java 17: Maven quản lý compile, JUnit và đóng gói

Ví dụ sau cho thấy cùng một dự án nhỏ được biên dịch, kiểm thử và tạo JAR bằng một lệnh Maven. Chuẩn bị **JDK 17 trở lên**, Maven tương thích hoặc Maven Wrapper do dự án cung cấp. Kiểm tra JDK mà Maven thực tế sử dụng bằng `mvn -version`.

Tạo cấu trúc thư mục ở mục 4.2 với ba tệp sau.

### 5.1. Tệp `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>hello-maven</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Các phiên bản JUnit/plugin trong ví dụ là phiên bản minh họa có thể phân giải từ repository; khi sử dụng thực tế cần rà soát phiên bản được tổ chức hỗ trợ và bản sửa lỗi bảo mật. `maven.compiler.release=17` yêu cầu biên dịch theo API và bytecode mục tiêu Java 17 (với JDK hỗ trợ `--release`), không có tác dụng tự tải/cài JDK 17. Phạm vi `test` bảo đảm JUnit không trở thành dependency runtime của ứng dụng.

### 5.2. Mã ứng dụng — `src/main/java/com/example/App.java`

```java
package com.example;

public final class App {
    private App() {
    }

    public static String message() {
        return "Hello, Maven!";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

### 5.3. Unit test — `src/test/java/com/example/AppTest.java`

```java
package com.example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void messageReturnsExpectedText() {
        assertEquals("Hello, Maven!", App.message());
    }
}
```

Test đặt tên `AppTest` để Surefire nhận diện theo các mẫu tên test thông dụng. JUnit Jupiter cung cấp annotation `@Test` và assertion; Surefire thực hiện test trong phase `test`.

### 5.4. Build và chạy

Mở terminal trong thư mục chứa `pom.xml`:

```bash
mvn -version
mvn clean verify
java -cp target/classes com.example.App
```

Dòng cuối xuất ra **chính xác**:

```text
Hello, Maven!
```

Sau khi `mvn clean verify` thành công, Maven đã chạy một unit test ở trên và tạo `target/hello-maven-1.0.0.jar`; báo cáo test thông thường nằm ở `target/surefire-reports/`. Các thông báo console khi Maven chạy, thời gian và trạng thái tải dependency tùy môi trường, nên không nên coi log Maven toàn bộ là stdout cố định.

Vì ví dụ không có dependency runtime bên ngoài JDK, cũng có thể chạy lớp main từ JAR bằng:

```bash
java -cp target/hello-maven-1.0.0.jar com.example.App
```

**Không mặc định dùng `java -jar target/hello-maven-1.0.0.jar`**: JAR thông thường được tạo ở đây chưa khai báo `Main-Class` trong manifest, và Maven không tự gói các dependency ngoài vào một “fat JAR”. Ứng dụng cần dependency runtime có thể phải cung cấp classpath hoặc cấu hình plugin đóng gói thích hợp.

### 5.5. So sánh hành động thủ công và Maven

Nếu chỉ biên dịch `App.java`, `javac` có thể đủ. Nhưng muốn chạy `AppTest` bằng tay, ta phải tự lấy JUnit và các thư viện liên quan, tạo classpath test, gọi trình chạy JUnit, kiểm tra exit code, rồi đóng gói JAR. Maven biến các công việc lặp lại đó thành cấu hình POM và lệnh `mvn verify`; IDE và CI cùng sử dụng được quy trình này.

Chính **test có thể fail** mới tạo ra giá trị kiểm soát: sửa assertion mong đợi thành chuỗi sai sẽ làm test thất bại và Maven trả exit code khác 0, từ đó pipeline CI có thể chặn việc phát hành.

## 6. Luồng làm việc thường gặp trong dự án và CI

Một luồng có thể áp dụng từ máy cá nhân lên CI:

1. Clone dự án, kiểm tra yêu cầu JDK và Maven (`mvn -version` hoặc wrapper).
2. Chỉnh mã nguồn và test, khai báo/thay đổi dependency trong `pom.xml` khi cần.
3. Chạy `mvn test` để lấy phản hồi nhanh; `mvn clean verify` để xác minh bản build từ trạng thái sạch.
4. Lưu artifact ở `target/` hoặc cung cấp artifact cho bước phát hành khi build thành công.
5. Dùng `mvn install` nếu muốn module/dự án **trên chính máy đó** truy cập artifact từ repository cục bộ; dùng `mvn deploy` chỉ khi đã cấu hình và có quyền xuất bản lên repository từ xa.

Trong dự án có Maven Wrapper (`mvnw` / `mvnw.cmd`) đã được commit cùng các tệp wrapper cần thiết, dùng `./mvnw clean verify` trên macOS/Linux hoặc `mvnw.cmd clean verify` trên Windows giúp cả nhóm chạy cùng bản phân phối Maven mà wrapper quy định. Wrapper **không tự đồng bộ JDK, hệ điều hành hay dịch vụ ngoài**.

Ví dụ job CI cơ bản thường gồm các bước: thiết lập JDK phù hợp, checkout mã, chạy wrapper/Maven, kiểm tra exit code và lưu artifact/report. Cache repository cục bộ có thể tăng tốc, nhưng cache không thay thế việc quản lý phiên bản. Nếu có nhiều module, POM aggregator khai báo `modules` giúp Maven tính thứ tự build theo quan hệ phụ thuộc; parent POM và `dependencyManagement` hỗ trợ chia sẻ cấu hình/phiên bản.

## 7. Những giới hạn và hiểu lầm phổ biến

- **“Maven thay thế Java compiler.”** Sai. Maven gọi compiler (thường là `javac`) qua plugin và cần JDK phù hợp; Maven không tự cung cấp Java runtime cho ứng dụng.
- **“Có `pom.xml` là build chắc chắn giống hệt ở mọi máy.”** Chưa đủ. Cần cố định/kiểm soát phiên bản dependency, plugin và JDK; lưu ý bản `SNAPSHOT` có thể thay đổi, cấu hình máy, tài nguyên ngoài, thời gian và các bước không xác định.
- **“Maven tải dependency thì không còn xung đột.”** Sai. Cần kiểm tra dependency tree, scope, quản lý phiên bản, loại trừ dependency khi có lý do cụ thể. Không nên tùy tiện loại dependency mà chưa hiểu nhu cầu runtime.
- **“`mvn install` là cài phần mềm vào hệ điều hành.”** Sai. Nó cài artifact vào **local Maven repository**; `deploy` mới là bước xuất bản tới repository từ xa.
- **“`mvn package` chỉ đóng gói, không chạy test.”** Theo lifecycle thông thường, phase `package` đi qua `test` trước. Chỉ khi cấu hình/flag làm bỏ qua test thì hành vi mới khác.
- **“Build ra JAR là chạy được bằng `java -jar`.”** Chưa chắc: còn cần điểm vào `Main-Class` và cách cấp dependency runtime.
- **“Maven chỉ làm được compile và package.”** Plugin có thể thực hiện tạo source, kiểm tra mã, test tích hợp, tạo báo cáo, ký artifact và các bước khác, nhưng phải cấu hình rõ khi vượt hành vi mặc định.

## 8. Lỗi thường gặp và hướng kiểm tra

| Triệu chứng | Kiểm tra trước tiên |
| --- | --- |
| Không nhận lệnh `mvn` | Maven đã cài và có trong `PATH` chưa, hoặc dự án có wrapper không? |
| `invalid target release: 17` / lỗi compiler | Xem JDK thực tế trong `mvn -version`, `JAVA_HOME` và yêu cầu `maven.compiler.release` |
| Không tải được dependency/plugin | Kiểm tra mạng, Maven Central/mirror, proxy, credentials, artifact coordinates/phiên bản; đọc dòng lỗi `Could not resolve` |
| `ClassNotFoundException` / `NoClassDefFoundError` | Kiểm tra tên lớp, output và classpath runtime; xem scope, dependency bị loại và cách chạy JAR |
| Test chạy trong IDE nhưng không chạy/không được nhận trong Maven | Kiểm tra `src/test/java`, tên test, engine JUnit, Surefire version và report |
| Build chạy trên máy cá nhân nhưng CI fail | So sánh JDK/Maven, dependency, plugin, biến môi trường, hệ điều hành, file ngoài và bước build thực tế |

Một số lệnh chẩn đoán hữu ích:

```bash
mvn -version
mvn dependency:tree
mvn help:effective-pom
mvn -e test
```

`mvn help:effective-pom` cho thấy POM sau kế thừa/profile; `mvn -e` in thêm stack trace khi lỗi. Các plugin chẩn đoán có thể được tải vào lần chạy đầu. Tránh giải pháp cực đoan như xóa toàn bộ `.m2` hay bỏ test hàng loạt trước khi biết nguyên nhân.

## 9. Thực hành tốt để Maven thực sự giải quyết vấn đề build

1. Đưa `pom.xml` và Maven Wrapper (nếu có) vào quản lý phiên bản; ghi rõ yêu cầu JDK.
2. Khai báo trực tiếp những dependency có API mà mã của dự án dùng; sử dụng `test` scope cho thư viện chỉ phục vụ test.
3. Chọn phiên bản plugin/dependency có chủ đích; ưu tiên quản lý thống nhất bằng parent/BOM khi dự án lớn.
4. Để CI chạy lifecycle thích hợp, thường là `verify`, và xử lý exit code khác 0 là lỗi build.
5. Giữ mã nguồn tách khỏi `target/`; không commit đầu ra build thông thường.
6. Quản lý quyền repository và secret bên ngoài mã nguồn; cập nhật dependency để xử lý lỗi/bảo mật theo quy trình.
7. Không nhầm một build “thành công” với ứng dụng đã đúng nghiệp vụ: chất lượng còn phụ thuộc vào test và tiêu chí xác minh đã thiết kế.

## 10. Tự kiểm tra mức độ hiểu bài

- Vì sao dự án có thư viện bên ngoài thường khó build ổn định chỉ bằng vài lệnh `javac`?
- Khi chạy `mvn verify`, Maven dựa vào đâu để biết phải compile, test và package?
- `dependencies`, `plugins`, `test` scope và `dependencyManagement` khác vai trò thế nào?
- Sự khác nhau giữa `mvn package`, `mvn install` và `mvn deploy` là gì?
- Vì sao JAR được tạo thành công vẫn có thể không chạy được bằng `java -jar`?

Nếu trả lời được các câu hỏi trên, bạn đã nắm được giá trị cốt lõi của Maven: **mô tả cách build bằng cấu hình dùng chung, tự động quản lý phần lớn dependency, thực thi quy trình build/test/đóng gói có thể lặp lại và tạo artifact dễ tích hợp với CI hoặc dự án khác**.

### Tài liệu tham khảo chính thức

- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Maven in 5 Minutes](https://maven.apache.org/guides/getting-started/maven-in-five-minutes.html)
- [Maven Surefire Plugin — JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
