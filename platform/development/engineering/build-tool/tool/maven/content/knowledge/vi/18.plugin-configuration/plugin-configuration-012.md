# Lựa chọn phase phù hợp cho một bước tự động hóa mới trong Maven

## 1. Vì sao chọn phase lại quan trọng?

Giả sử bạn cần thêm một bước tự động hóa vào build Maven. Bước đó có thể tạo mã Java, sinh file cấu hình, xác minh quy ước, kiểm tra JAR đã đóng gói hoặc khởi động môi trường để chạy integration test. Cùng một plugin goal nhưng **đặt ở phase khác nhau có thể làm kết quả khác hẳn**:

- Đặt bước **tạo resource** sau khi Maven đã copy resources: file được sinh nhưng không nằm trong classpath ứng dụng.
- Đặt bước **kiểm tra JAR** trước khi packaging: build fail vì chưa có JAR, dù mã nguồn hoàn toàn đúng.
- Đặt kiểm tra chính sách vào `verify` trong khi nó có thể fail sớm ở `validate`: làm mất thời gian compile/test không cần thiết.
- Đặt integration-test cleanup vào phase không được pipeline chạy tới: để lại container, port hoặc tài nguyên tạm.
- Đặt bước có tác dụng phụ như upload vào `package`: mỗi lần lập trình viên chỉ định đóng gói cũng vô tình gọi API hoặc publish dữ liệu.
- Chỉ khai báo plugin trong `<pluginManagement>`, quên cấu hình execution thực: tưởng đã bật automation nhưng goal chưa hề chạy.

**Quy tắc trung tâm:** Đừng bắt đầu bằng câu hỏi “plugin này có goal nào?”. Hãy bắt đầu từ **bước tự động hóa cần dữ liệu gì, tạo ra dữ liệu gì, và dữ liệu đó phải sẵn sàng trước bước nào**. Từ quan hệ trước–sau ấy mới chọn phase.

Trong Maven, **phase** là một cột mốc trong lifecycle, **goal** là tác vụ cụ thể của plugin, và **execution binding** nối một goal với một phase.

## 2. Mô hình tư duy: đầu vào → bước mới → đầu ra → bước tiếp theo

Xem ba tình huống:

~~~text
Tình huống A — tạo source Java
   mô hình/schema
         |
         v
  [generate-sources]  sinh *.java
         |
         v
  [compile]           javac đọc source được đăng ký

Tình huống B — tạo resource
   thông tin build
         |
         v
  [generate-resources] sinh build-info.properties
         |
         v
  [process-resources] copy vào target/classes
         |
         v
  [test/package]      ứng dụng/test đọc resource

Tình huống C — kiểm tra artifact
   mã nguồn và test
         |
         v
  [package]           tạo JAR/WAR
         |
         v
  [verify]            kiểm tra artifact và quality gates
         |
         v
  [install/deploy]    đưa artifact sang local/remote repository
~~~

Chọn đúng phase là xác định **đầu ra của bước mới xuất hiện trước khi một goal khác cần đến nó**, nhưng **không làm quá sớm khi prerequisite chưa có**.

Đừng dùng việc “chạy được một lần trên laptop” làm tiêu chuẩn. Cache, file `target` còn sót hoặc lệnh Maven khác có thể che lỗi thứ tự. Bước tự động hóa phải chạy được **từ trạng thái sạch**, trong CI và trên những module mà nó dự kiến áp dụng.

## 3. Lifecycle và phase: nắm phần khung trước

Maven có ba lifecycle tích hợp: `default`, `clean` và `site`.

- **Default lifecycle**: chuẩn bị, biên dịch, kiểm thử, đóng gói, kiểm chứng, cài đặt và deploy artifact.
- **Clean lifecycle**: dọn những output do build tạo.
- **Site lifecycle**: tạo và phát hành site/báo cáo dự án.

Dưới đây là các mốc đáng quan tâm của **default lifecycle** theo thứ tự cơ bản:

~~~text
validate
initialize
generate-sources
process-sources
generate-resources
process-resources
compile
process-classes
generate-test-sources
process-test-sources
generate-test-resources
process-test-resources
test-compile
process-test-classes
test
prepare-package
package
pre-integration-test
integration-test
post-integration-test
verify
install
deploy
~~~

Danh sách trên không liệt kê toàn bộ phase trung gian, nhưng thể hiện các mốc quan trọng để chọn vị trí automation.

### 3.1. Gọi phase không giống gọi goal trực tiếp

~~~bash
mvn compile
mvn compiler:compile
~~~

Với Maven 3 và packaging `jar` thông thường:

- `mvn compile` yêu cầu Maven đi qua các phase từ đầu default lifecycle đến `compile`, chạy các goal được bind ở những phase ấy.
- `mvn compiler:compile` yêu cầu goal Compiler Plugin trực tiếp, **không mặc nhiên thực thi toàn bộ các phase phía trước**.

Một goal đặc biệt có thể fork lifecycle theo metadata riêng; do đó cũng không đúng khi khẳng định mọi direct goal đều tuyệt đối không chạy thêm phase nào.

### 3.2. Gọi phase đích cao hơn kéo theo những phase trước nó

~~~bash
mvn clean verify
~~~

Maven chạy clean lifecycle đến `clean`, rồi default lifecycle đến `verify`. Không cần chỉ định `compile test package verify` thành chuỗi riêng. Nếu pipeline cần kiểm chứng trước khi phát hành, `verify` thường là mốc phù hợp, **với điều kiện các plugin/check thực sự đã được bind**.

### 3.3. Ghi chú quan trọng về Maven 3 và Maven 4

Các ví dụ thực hành bên dưới lấy **Maven 3.9.x + JDK 17** làm mốc giải thích về thứ tự phase. Tài liệu Maven 4 có thay đổi liên quan các phase `before:`/`after:` và hành vi gọi một số phase trung gian. Chẳng hạn trên Maven 4, gọi `compile` có thể bao gồm goals ở `process-classes` sau nó; gọi `prepare-package` có thể đã tạo JAR, và gọi `integration-test` có thể xử lý cleanup mà Maven 3 không tự làm khi dừng tại mốc ấy.

Vì vậy, **đừng chuyển một mẹo dùng riêng cho Maven 3 thành kết luận tuyệt đối cho mọi Maven 4**. Lựa chọn theo dữ liệu đầu vào/đầu ra vẫn là nguyên tắc tốt ở cả hai, nhưng phải xem phiên bản và lifecycle execution plan thực tế:

~~~bash
mvn -version
~~~

## 4. Bảng quyết định: nên đặt bước tự động hóa ở đâu?

| Bước mới cần làm gì? | Phase thường phù hợp | Vì sao? |
| --- | --- | --- |
| Kiểm tra JDK/Maven version, chính sách nền của project | `validate` | Fail sớm trước chi phí compile/test |
| Khởi tạo thuộc tính hoặc chuẩn bị trạng thái chung của build | `initialize` | Sẵn sàng trước các bước tạo source/resource |
| Sinh mã Java từ schema, OpenAPI hoặc mô hình | `generate-sources` | Mã được sinh trước `compile` |
| Biến đổi nguồn Java trước khi compile | `process-sources` | Xử lý đầu vào sau khi source được tạo, trước compiler |
| Sinh file cấu hình hoặc dữ liệu cần đóng gói | `generate-resources` | File tồn tại trước `process-resources` |
| Copy/filter resources và chuẩn bị classpath resource | `process-resources` | Đưa file tới output directory |
| Chuyển đổi class/bytecode sau biên dịch | `process-classes` | Chỉ chạy khi `.class` đã tồn tại |
| Sinh mã chỉ dùng trong unit tests | `generate-test-sources` | Sẵn sàng trước `test-compile` |
| Sinh test resource | `generate-test-resources` | Sẵn sàng trước `process-test-resources` |
| Copy/filter test resources | `process-test-resources` | Đưa dữ liệu test vào test classpath |
| Chạy unit tests | `test` | Main và test classes đã được biên dịch |
| Sắp xếp/chuẩn bị nội dung trước packaging | `prepare-package` | Các file được chuẩn bị trước khi tạo artifact |
| Tạo artifact phát hành | `package` | Maven package plugin đóng JAR/WAR |
| Khởi động service phục vụ integration test | `pre-integration-test` (Maven 3), hoặc hook tương ứng Maven 4 | Môi trường tồn tại trước integration tests |
| Chạy integration tests trên hệ thống đã dựng | `integration-test` | Đã có artifact/môi trường phù hợp |
| Dọn service, thu thập dữ liệu sau integration test | `post-integration-test` (Maven 3), hoặc hook tương ứng Maven 4 | Thực hiện sau test |
| Kiểm tra kết quả kiểm thử, artifact và quality gate sau packaging | `verify` | Fail trước `install`/`deploy` |
| Cài artifact vào Maven local repository | `install` | Chỉ khi cần cho project cục bộ khác |
| Phát hành artifact lên remote repository | `deploy` | Chỉ trong quy trình đã được cấp quyền |

Bảng là **điểm khởi đầu**, không phải luật cứng cho mọi goal. Một plugin goal có thể có default phase khác hoặc tự chạy các bước chuẩn bị. Nếu check chỉ cần POM metadata, `validate` hợp lý; nếu check cần file JAR đã đóng gói, phải chọn thời điểm sau khi artifact thật đã tồn tại.

## 5. Năm câu hỏi trước khi chọn phase

Trước khi thêm một execution, ghi rõ:

1. **Đầu vào là gì?** POM metadata, Java sources, generated sources, test classes, JAR/WAR hay một dịch vụ đã khởi động?
2. **Ai tạo đầu vào đó?** Goal/plugin nào, ở phase nào? Nó có thể không chạy nếu profile hoặc packaging khác?
3. **Đầu ra của automation là gì?** File, source root, test report, artifact bổ sung, kết quả kiểm chứng, hay tác dụng phụ bên ngoài?
4. **Ai dùng đầu ra và vào lúc nào?** Compiler, Resources Plugin, Surefire, JAR Plugin, Failsafe hay deploy?
5. **Nếu chạy lại hai lần từ cùng state thì sao?** Có ghi đè không, có phá file, dùng path phụ thuộc máy, làm lộ secret hoặc gây side effects không?

Một ví dụ trả lời đầy đủ:

> “Tôi cần tạo `build-info.properties` để chương trình đọc từ classpath. Nó lấy property build, tạo text file dưới `target/generated-resources/...`, và Maven Resources Plugin phải copy file ấy vào `target/classes` trước khi compile/test/package. Vì vậy nên bind bước tạo ở `generate-resources`, rồi cấu hình `<resources>` để Resources Plugin nhận thư mục ấy trong `process-resources`.”

Đây là câu trả lời dựa trên **quan hệ dependency giữa các bước**, không chỉ dựa trên tên “resources”.

## 6. Ví dụ Java 17: sinh resource trước khi Maven copy resource

Ta dựng một project có **hai bước tự động hóa**:

- Bước A: tạo `build-info.properties` ở `generate-resources`.
- Bước B: ở `verify`, kiểm tra file resource đã được copy vào classpath và JAR đã được tạo.

Project có một class Java đọc resource và một JUnit test xác nhận kết quả. Ví dụ này dùng Maven AntRun Plugin để minh họa timing bằng các task Ant đơn giản; dự án thật nên ưu tiên plugin chuyên dụng khi có sẵn.

### 6.1. Cấu trúc dự án

~~~text
phase-choice-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/phase/App.java
    │   └── resources/app.properties
    └── test/
        └── java/demo/phase/AppTest.java
~~~

Không tạo `src/main/resources/build-info.properties` thủ công. File này được **sinh trong `target`** bởi Maven.

### 6.2. POM đầy đủ: `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo.phase</groupId>
    <artifactId>phase-choice-lab</artifactId>
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
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>false</filtering>
            </resource>
            <resource>
                <directory>${project.build.directory}/generated-resources/demo</directory>
                <filtering>false</filtering>
            </resource>
        </resources>

        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
                <version>3.1.0</version>
                <executions>
                    <execution>
                        <id>generate-build-info</id>
                        <phase>generate-resources</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                        <configuration>
                            <target>
                                <mkdir dir="${project.build.directory}/generated-resources/demo"/>
                                <echo
                                    file="${project.build.directory}/generated-resources/demo/build-info.properties"
                                    message="channel=generated"
                                    encoding="UTF-8"/>
                            </target>
                        </configuration>
                    </execution>
                    <execution>
                        <id>verify-outputs</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                        <configuration>
                            <target>
                                <available
                                    file="${project.build.outputDirectory}/build-info.properties"
                                    property="resource.ready"/>
                                <fail unless="resource.ready"
                                      message="Copied build-info.properties is missing"/>
                                <available
                                    file="${project.build.directory}/${project.build.finalName}.jar"
                                    property="jar.ready"/>
                                <fail unless="jar.ready"
                                      message="Expected JAR is missing"/>
                                <echo message="VERIFY: generated resource and JAR exist"/>
                            </target>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Các điểm thiết kế quan trọng:**

- `<packaging>jar</packaging>` giúp Maven dùng binding mặc định của dự án JAR.
- `generate-build-info` gắn vào `generate-resources`: tạo file trước khi Resources Plugin chạy ở `process-resources`.
- `<resources>` khai báo **cả** thư mục tài nguyên chuẩn lẫn thư mục sinh dưới `target`. Nếu chỉ khai báo thư mục sinh và quên `src/main/resources`, bạn có thể vô tình bỏ resource nguồn tiêu chuẩn khỏi build.
- `maven-resources-plugin` được ghim version 3.3.1; goal `resources:resources` được Maven bind theo packaging ở `process-resources`.
- `verify-outputs` gắn tại `verify`: kiểm tra **sau** phase `package`. Phép kiểm tra đặt trên file `target/classes/build-info.properties` và JAR thành phẩm.
- Các Ant tasks `mkdir`, `echo`, `available` và `fail` là các thao tác có thật của Ant. `echo` tạo file nội dung ASCII; việc chỉ định UTF-8 giúp rõ ý định nếu sau này nội dung có ký tự không phải ASCII.
- Hai executions có ID khác nhau nên dễ theo dõi trong log và có thể được gọi trực tiếp bằng cú pháp `goal@executionId` khi cần chẩn đoán.

Đây là một POM đầy đủ, không cần parent tùy chỉnh hay repository giả định. Các plugin và JUnit ở những version đã chỉ định được Maven resolve từ repository hợp lệ (thường Maven Central).

### 6.3. Tài nguyên nguồn `src/main/resources/app.properties`

~~~properties
app.name=phase-lab
~~~

File này tồn tại trước build. Maven Resources Plugin copy nó vào `target/classes/app.properties`.

### 6.4. `src/main/java/demo/phase/App.java`

~~~java
package demo.phase;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class App {
    private App() {
    }

    public static String get(String resource, String key) throws IOException {
        Properties values = new Properties();

        try (InputStream input =
                     App.class.getResourceAsStream("/" + resource)) {
            if (input == null) {
                throw new IOException("Resource not found: " + resource);
            }
            values.load(input);
        }

        String result = values.getProperty(key);
        if (result == null) {
            throw new IOException("Property not found: " + key);
        }
        return result;
    }

    public static void main(String[] args) throws IOException {
        System.out.println("app=" + get("app.properties", "app.name"));
        System.out.println("channel=" + get("build-info.properties", "channel"));
    }
}
~~~

Class này dùng Java standard library, biên dịch được với Java 17. `Properties.load(InputStream)` thích hợp với hai file ASCII trong ví dụ. Nếu sau này lưu giá trị Unicode tiếng Việt UTF-8, nên dùng `Properties.load(Reader)` với một `InputStreamReader(..., UTF_8)` để chủ động kiểm soát encoding.

**Java không tự gọi Maven** khi chạy `main`. Ứng dụng chỉ thấy resources đã được Maven copy vào classpath của artifact hoặc `target/classes`.

### 6.5. `src/test/java/demo/phase/AppTest.java`

~~~java
package demo.phase;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.IOException;
import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void readsStandardResource() throws IOException {
        assertEquals("phase-lab", App.get("app.properties", "app.name"));
    }

    @Test
    void readsGeneratedResource() throws IOException {
        assertEquals("generated",
                     App.get("build-info.properties", "channel"));
    }
}
~~~

Test thứ hai có giá trị học tập: nếu chọn phase sai khiến generated resource chưa được copy, Surefire có thể phát hiện bằng `Resource not found: build-info.properties` thay vì để lỗi xuất hiện ở production.

## 7. Chạy bản đúng: `clean verify`

Từ thư mục `phase-choice-lab`:

~~~bash
mvn -version
mvn -B -ntp clean verify
~~~

Trên **Maven 3.9.x** với project demo, chuỗi chủ yếu là:

~~~text
[clean]                  xóa target của lần build cũ
[generate-resources]     antrun:run (generate-build-info)
[process-resources]      resources:resources (default-resources)
[compile]                compiler:compile (default-compile)
[process-test-resources] resources:testResources
[test-compile]           compiler:testCompile
[test]                   surefire:test
[package]                jar:jar
[verify]                 antrun:run (verify-outputs)
~~~

Đây là **sơ đồ thứ tự thực thi**, không phải bản sao nguyên log. Những phase trống có thể không xuất hiện trong log; version Maven/plugin và một số goal phụ khác có thể làm output khác nhau.

Các artifact kỳ vọng:

~~~text
target/
├── generated-resources/
│   └── demo/
│       └── build-info.properties
├── classes/
│   ├── app.properties
│   ├── build-info.properties
│   └── demo/phase/App.class
├── test-classes/demo/phase/AppTest.class
└── phase-choice-lab-1.0.0.jar
~~~

**Hai test JUnit** PASS. AntRun ở `verify` in một dòng đại ý:

~~~text
[echo] VERIFY: generated resource and JAR exist
~~~

Đây là **log AntRun**, không phải stdout của Java main. Khi build đã thành công, chạy riêng:

~~~bash
java -cp target/classes demo.phase.App
~~~

Stdout chính xác của chương trình:

~~~text
app=phase-lab
channel=generated
~~~

Có thể kiểm tra JAR cuối:

~~~bash
jar tf target/phase-choice-lab-1.0.0.jar
~~~

Trong danh sách entry nên có `app.properties` và `build-info.properties` cùng `demo/phase/App.class`. JAR của project demo là JAR bình thường, không cần nhúng JUnit hay AntRun Plugin vào runtime.

## 8. Cố ý chọn phase sai: hậu quả thế nào?

### 8.1. Nếu sinh resource ở `process-resources`

Giả sử chuyển `generate-build-info` từ `generate-resources` sang `process-resources` mà không thay gì khác. Trên Maven 3 với packaging `jar`, binding mặc định `resources:resources` thường được chạy **trước** các goal do POM thêm vào cùng phase.

Hệ quả có thể là:

1. Maven Resources Plugin duyệt thư mục `target/generated-resources/demo` khi file chưa được sinh.
2. AntRun tạo file sau đó trong cùng phase.
3. File nguồn sinh ra tồn tại ở `target/generated-resources/demo` nhưng **chưa được copy** vào `target/classes`.
4. Unit test đọc `build-info.properties` thất bại.

Vì vậy không nên nghĩ “đặt cùng phase với Resources Plugin là đủ”. Nếu bước mới **sinh đầu vào cho** `resources:resources`, cần đặt nó **ở phase trước**, chẳng hạn `generate-resources`.

Có những kỹ thuật điều khiển execution order trong một phase, nhưng khi có phase tự nhiên dành cho producer, dùng **phase khác sớm hơn** dễ hiểu và ít phụ thuộc thứ tự hơn.

### 8.2. Nếu sinh resource ở `compile`

`compiler:compile` cần source và classpath đã chuẩn bị. Resources Plugin thường xử lý main resources trước compile. Sinh resource ở `compile` có thể quá muộn với mục đích đưa resource vào `target/classes` trước khi test/package, trừ khi bạn tự thiết kế thêm bước copy. **Chọn `generate-resources` cho việc tạo resource, không dựa vào `compile` chỉ vì nó xảy ra trong mọi build Java.**

### 8.3. Nếu kiểm tra JAR ở `validate`

Ở `validate`, chưa có artifact đóng gói của **lần build sạch hiện tại**. Bước kiểm tra `target/phase-choice-lab-1.0.0.jar` sẽ báo lỗi dù project không hỏng. Nếu không clean, một JAR cũ có thể khiến check **false pass**.

Do đó check cần **artifact cuối** nên chạy sau khi packaging đã hoàn tất, thường là `verify`. Ngược lại, kiểm tra sơ đồ cấu hình, phiên bản JDK hoặc một property bắt buộc không cần đợi JAR; chọn `validate` để fail sớm.

### 8.4. Nếu kiểm tra JAR ở `package`

Với Maven 3/JAR packaging, goal `jar:jar` thường được bind mặc định tại `package`. Goal tự khai báo cùng phase thường được thực thi **sau** binding mặc định theo quy tắc documented. Vì vậy check có thể chạy được ngay tại `package`. Tuy nhiên khi yêu cầu về mặt nghiệp vụ là **“kiểm tra artifact trước khi xác nhận build”**, `verify` diễn đạt ý định rõ hơn, tránh phụ thuộc thứ tự/packaging đặc thù và tương thích với kiểm tra sau integration tests.

**Đừng chọn phase chỉ vì một log cụ thể cho thấy file đã có**. Hãy chọn theo hợp đồng: nếu cần JAR thành phẩm, phase `verify` là điểm kiểm chứng hợp lý; nếu cần chuẩn bị thành phần trước khi đóng gói, `prepare-package` mới có ý nghĩa.

## 9. Thử direct goal để thấy việc thiếu prerequisite

Dù execution được bind vào lifecycle, bạn vẫn có thể **gọi trực tiếp** goal theo execution ID khi Maven hỗ trợ cú pháp `goal@executionId`.

### 9.1. Gọi riêng bước sinh resource

~~~bash
mvn -B -ntp clean antrun:run@generate-build-info
~~~

Sau lệnh này, file `target/generated-resources/demo/build-info.properties` được tạo. Nhưng chưa có yêu cầu chạy default lifecycle qua `process-resources` nên **không được giả định** có `target/classes/build-info.properties`. Project cũng chưa biên dịch Java và chưa tạo JAR.

Lệnh hữu ích khi debug logic tạo file, nhưng **không thay thế** `mvn compile` hoặc `mvn verify` nếu mục tiêu là xây dựng project đầy đủ.

### 9.2. Gọi riêng bước verify sau clean

~~~bash
mvn -B -ntp clean antrun:run@verify-outputs
~~~

Đây là **phép thử thất bại có chủ ý**:

- `clean` xóa `target`.
- `antrun:run@verify-outputs` gọi riêng cấu hình `verify-outputs`.
- Maven **không tự chạy** `generate-resources`, `process-resources` và `package` chỉ vì execution này được bind tại `verify`.
- Ant task `fail` phát hiện file `build-info.properties` đã copy chưa tồn tại hoặc JAR chưa được tạo.

Thông điệp dự kiến có phần:

~~~text
Copied build-info.properties is missing
BUILD FAILURE
~~~

Nếu bạn chạy check trên state đã có resource nhưng chưa có JAR, thông báo có thể là `Expected JAR is missing`. Điều quan trọng là **direct goal không tự bảo đảm những prerequisite của phase**.

### 9.3. Gọi riêng `antrun:run` không có execution ID

~~~bash
mvn -B -ntp antrun:run
~~~

Trong POM demo, `<target>` chỉ được đặt ở những executions `generate-build-info` và `verify-outputs`. Invocation CLI không có `@id` thường dùng execution ID `default-cli` và plugin-level configuration, **không mặc nhiên lấy cấu hình một trong hai executions trên**. Với AntRun 3.1.0, goal có thể chạy mà không có target hữu ích. Vì vậy lúc cần kiểm tra đúng một execution, chọn nó bằng `goal@executionId` hoặc chạy lifecycle phase thích hợp.

## 10. Có thể sinh mã Java thay vì resource không?

Có, nhưng phải chọn **phase khác** và thường có thêm bước **đăng ký source root**.

Nếu dùng một generator tạo các file `.java` từ schema, vị trí phổ biến là `generate-sources`. Compiler Plugin không tự quét mọi thư mục trong `target/generated-sources`; generator có thể tự đăng ký source root, hoặc bạn dùng Maven Build Helper Plugin.

Ví dụ đoạn XML minh họa (không thuộc POM demo ở mục 6):

~~~xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>build-helper-maven-plugin</artifactId>
    <version>3.6.0</version>
    <executions>
        <execution>
            <id>add-generated-source-folder</id>
            <phase>generate-sources</phase>
            <goals>
                <goal>add-source</goal>
            </goals>
            <configuration>
                <sources>
                    <source>${project.build.directory}/generated-sources/custom</source>
                </sources>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Đoạn này chỉ **đăng ký** thư mục nguồn, không sinh code. Bạn vẫn cần một plugin/code generator thực sự tạo `.java` ở đường dẫn ấy trước khi `compile`. Nếu generator đã tự đăng ký source root thì không cần thêm goal này.

Sự khác nhau:

| Đầu ra cần tạo | Phase sinh | Bước tiêu thụ |
| --- | --- | --- |
| `*.java` dùng cho mã chính | `generate-sources` | Compiler ở `compile`, sau khi source root được đăng ký |
| `*.java` chỉ cho test | `generate-test-sources` | Test compiler ở `test-compile` |
| `*.properties`, template hoặc resource chính | `generate-resources` | Resources Plugin ở `process-resources` |
| Dữ liệu test `*.json`, `*.properties` | `generate-test-resources` | Test Resources Plugin ở `process-test-resources` |
| Bytecode enhancement trên `.class` | `process-classes` | Packaging/test sau khi class đã được sửa |

Không đặt bước sinh Java vào `verify` nếu code đó cần tham gia compile của cùng build. Đến `verify` là quá muộn.

## 11. Đặt kiểm tra ở `validate` hay `verify`?

Đây là câu hỏi hay nhất khi thêm một **quality gate**.

### 11.1. `validate` — fail nhanh khi không cần output build

Các điều kiện phù hợp:

- JDK chạy Maven có thuộc phạm vi cho phép không?
- Maven version tối thiểu có đạt không?
- Tên groupId, project properties hay cấu hình bắt buộc có hợp lệ không?
- Một dependency policy có thể kiểm tra bằng metadata/resolved graph mà không cần artifact cuối không?

Ví dụ đoạn Maven Enforcer Plugin có thể bind ở `validate`:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.5.0</version>
    <executions>
        <execution>
            <id>check-java-version</id>
            <phase>validate</phase>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <requireJavaVersion>
                        <version>[17,)</version>
                    </requireJavaVersion>
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Đây là **đoạn cấu hình riêng để minh họa**, không phải POM độc lập. Nó yêu cầu JDK chạy Maven đáp ứng Java 17 trở lên. Một build không đáp ứng có thể fail trước compile, tiết kiệm thời gian.

Cần phân biệt **JDK chạy Maven**, **JDK được toolchains chọn** và `maven.compiler.release`. Nếu chính sách yêu cầu toolchain cũng đúng, chỉ dùng rule `requireJavaVersion` chưa đủ chứng minh compiler thực sự dùng đúng JDK.

### 11.2. `verify` — đánh giá output và các test đã chạy

Các tình huống phù hợp:

- Kiểm tra JAR/WAR cuối có một file bắt buộc.
- Kiểm tra kết quả integration test và fail build nếu có test thất bại.
- Xác minh báo cáo kiểm thử/quality report đã được sinh.
- Kiểm tra artifact signature, SBOM hoặc file kết quả có được tạo (tùy plugin).

Một goal gắn vào `verify` có thể quyết định cho fail build **trước khi `install` hoặc `deploy`**. Nhưng nếu goal kiểm tra chỉ cần POM metadata thì chờ đến verify có thể làm build tốn kém vô ích.

**Quy tắc:** Việc kiểm tra cần **dữ liệu sẵn ở đầu build** → cân nhắc `validate`. Việc kiểm tra cần **test/report/artifact đã tạo** → cân nhắc `verify`.

## 12. Chọn `prepare-package`, `package` hay `verify`

Ba phase này thường bị đặt sai.

- **`prepare-package`**: dùng để chuẩn bị các đầu vào cuối trước packaging, như copy/generate thành phần cho bundle. Không nên giả định JAR cuối đã tồn tại ở đầu phase trong Maven 3.
- **`package`**: Maven đóng gói phân phối phù hợp packaging, ví dụ JAR/WAR. Một số packaging/plugin có mapping riêng, không nhất thiết đều gọi `jar:jar`.
- **`verify`**: kiểm tra kết quả, đặc biệt sau artifact và integration-test phases.

Ví dụ yêu cầu “thêm file manifest metadata vào input packaging” không nên chờ đến `verify`, vì JAR đã tạo rồi. Ngược lại, yêu cầu “kiểm tra JAR chứa chính metadata ấy” nên kiểm tra **sau** packaging, thường `verify`.

Trong Maven 4, có các thay đổi về pha `before:`/`after:` và điều được thực thi khi người dùng chỉ định phase trung gian. Khi chuyển POM/phần tự động hóa giữa Maven 3 và Maven 4, hãy kiểm tra execution plan chứ không chỉ dựa vào tên phase.

## 13. Integration tests: tránh bỏ qua bước dọn và đánh giá

Một chuỗi integration-test theo Maven 3 thường:

~~~text
pre-integration-test  → chuẩn bị máy chủ/container/test environment
integration-test      → thực thi integration tests
post-integration-test → dọn môi trường, thu thập kết quả
verify                → kiểm tra kết quả và quyết định build PASS/FAIL
~~~

Với Maven Failsafe Plugin, goals `failsafe:integration-test` và `failsafe:verify` có vai trò khác nhau. Đừng bind goal phát hành hoặc báo thành công ngay sau `integration-test` nếu phần đánh giá lỗi thực sự ở `verify`.

Đặc biệt trên Maven 3, **không nên lấy `mvn integration-test` làm lệnh CI hoàn chỉnh** nếu môi trường cần `post-integration-test` để dọn; một số container có thể bị để lại đang chạy. Thường chọn `mvn verify`.

**Khác biệt Maven 4:** tài liệu lifecycle mới có mô tả các phase `before:`/`after:` và cách Maven 4 bao gồm các bước dọn sau khi chạy một phase; đừng áp dụng nguyên trạng cảnh báo “`integration-test` luôn không dọn” cho mọi Maven 4. Tuy vậy, chọn `verify` vẫn có ích để bảo đảm các goal đánh giá kết quả/check cuối được chạy.

Nếu cần test tích hợp trên môi trường khác CI (staging, production), Maven lifecycle không thay thế quyền hạn và quy trình triển khai riêng; có thể tổ chức workflow ở CI/CD thay vì lạm dụng goal Maven để thực hiện thay đổi hạ tầng không an toàn.

## 14. Không nhầm `clean` và `site` với default lifecycle

**`clean`** nằm trong clean lifecycle. Nếu bước mới cần tạo file build, hãy ghi nó vào `target` và để Maven Clean Plugin xử lý. Không nên hook một script xóa thư mục tùy ý vào `validate` mỗi lần build; nó dễ phá output và tài liệu người dùng.

Ví dụ:

~~~bash
mvn clean verify
~~~

Lệnh này chạy clean rồi default lifecycle. `mvn verify` **không mặc nhiên chạy clean**. Nếu bạn cần dữ liệu từ build trước, phải cân nhắc incremental build/idempotence; nếu cần build sạch trong CI, `clean verify` giúp giảm ảnh hưởng của output cũ.

**`site`** thuộc site lifecycle, phù hợp với báo cáo và site documentation. Một plugin chỉ xuất hiện dưới `<reporting>` thường tham gia công việc site, **không tự chạy ở default lifecycle** mỗi lần `mvn verify`. Nếu báo cáo cần là gate bắt buộc trong verify, phải cấu hình build plugin/goals phù hợp, không chỉ bật reporting.

## 15. `<pluginManagement>` không tự tạo bước mới

Một bẫy khác: dự án khai báo plugin trong parent nhưng goal chưa hề thực thi.

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
                <version>3.1.0</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

Đoạn này **chỉ quản lý plugin version/configuration** để các module dùng theo cách thích hợp. Nó không tự sinh execution tại `generate-resources` hay `verify`.

Để tham gia build, plugin/goal phải được sử dụng bởi lifecycle mapping, một execution được khai báo trong `<build><plugins>` tương ứng, hoặc được gọi trực tiếp. `<dependencies>` và `<dependencyManagement>` của project cũng không dùng để gắn Maven plugin goal vào phase.

Nếu tưởng một bước đang chạy nhưng `mvn verify` không có log về goal ấy, kiểm tra effective POM, vị trí `<plugins>`, profile active và execution ID.

## 16. Default phase của goal: có cần viết `<phase>` không?

Một Maven plugin goal có thể công bố **default lifecycle phase** trong descriptor. Khi execution hợp lệ khai báo goal mà không chỉ định `<phase>`, Maven có thể áp dụng default phase được công bố. Nếu goal không có default phase và execution không có `<phase>`, execution có thể không chạy khi gọi lifecycle phase thông thường.

Vì vậy:

~~~xml
<execution>
    <id>my-automation</id>
    <goals>
        <goal>run</goal>
    </goals>
</execution>
~~~

không phải bằng chứng nó sẽ chạy tại `verify`. Với plugin AntRun ví dụ, ta chỉ định **rõ** `<phase>generate-resources</phase>` hoặc `<phase>verify</phase>` để tránh suy đoán.

Đọc tài liệu goal, đặc biệt các thông tin `Binds by default to lifecycle phase`, `Requires dependency resolution`, `threadSafe` và yêu cầu output. Default phase trong descriptor **không tự làm plugin chạy trong mọi project chỉ vì plugin tồn tại**.

## 17. Cùng phase có nhiều goals: thứ tự nào?

Một phase có thể có nhiều goals. Với Maven 3 và packaging `jar`, **default goals từ packaging thường được thực hiện trước goals bổ sung từ POM trong cùng phase**; nhiều executions tùy chỉnh thường theo thứ tự khai báo trong mô hình hiệu lực. Parent POM và profiles có thể thay đổi mô hình này.

Ví dụ nếu sinh resource ở **cùng phase `process-resources`** với `resources:resources`, có rủi ro resource được tạo sau khi Maven đã copy. Đó là lý do nên dùng `generate-resources` cho producer.

Với hai kiểm tra cùng phase `verify`, có thể đặt nhiều executions với ID khác nhau. Nhưng nếu check B **phụ thuộc vào output check A**, tốt hơn là xem có phase phân tách tự nhiên hay một plugin có khả năng điều phối rõ ràng; đừng xây dựng hợp đồng quan trọng chỉ dựa vào thứ tự không được kiểm chứng.

Maven 4 có bổ sung một số cú pháp/thứ tự execution nâng cao; cấu hình Maven 4 không nên sao chép vô điều kiện vào Maven 3. Với project được dùng ở nhiều môi trường, chốt Maven version qua Maven Wrapper và test execution plan.

## 18. Module đa thành phần: phase nào chạy ở module nào?

Dự án Reactor có cấu trúc:

~~~text
company-app/
├── pom.xml
├── api/pom.xml
├── service/pom.xml
└── integration-tests/pom.xml
~~~

Một execution được cấu hình ở parent và kế thừa sang mọi module có thể khiến cùng goal chạy **nhiều lần**, có thể đúng hoặc sai tùy mục tiêu.

Cần xác định:

- Goal nên chạy **mỗi module** hay chỉ một lần ở aggregator/root?
- Plugin goal có cờ aggregator hoặc hỗ trợ Reactor không?
- Packaging ở module có phải `pom`, `jar` hay `war`?
- Execution có được parent truyền cho child không? Có cần `<inherited>false</inherited>`?
- File output có dùng `${project.build.directory}` (riêng từng module) hay một đường dẫn root dùng chung?
- Khi CI chỉ chọn `-pl :service`, goal có đủ prerequisite từ module khác không? Có cần `-am` hoặc bước build/install trước?

Ví dụ, một AntRun execution kiểm tra `${project.build.finalName}.jar` được kế thừa sang **module packaging `pom`** sẽ sai, vì module đó không tạo JAR thông thường. Không bind một kiểm tra JAR cho mọi module mà không xem packaging. Có thể cấu hình riêng ở các module tạo JAR, hoặc dùng property/plugin skip phù hợp.

Khi nhiều modules cùng ghi vào một đường dẫn chung, build song song có thể xảy ra tranh chấp. Ưu tiên đường dẫn theo `${project.build.directory}` ở mỗi module, xác định plugin có thread-safe hay không và tránh script ghi file shared không có cơ chế đồng bộ.

## 19. Profile và CI: bước tự động hóa có thực sự active?

Một execution có thể được khai báo trong profile:

~~~xml
<profiles>
    <profile>
        <id>strict-checks</id>
        <build>
            <plugins>
                <!-- Plugin và execution kiểm tra phù hợp ở đây -->
            </plugins>
        </build>
    </profile>
</profiles>
~~~

Đây chỉ là **đoạn mô tả cấu trúc**, không phải một POM đầy đủ với plugin cụ thể. Nếu profile `strict-checks` không active, execution bên trong **không góp vào effective build model**.

Chẩn đoán:

~~~bash
mvn -B -ntp -Pstrict-checks help:active-profiles
mvn -B -ntp -Pstrict-checks help:effective-pom -Doutput=effective-strict.xml
mvn -B -ntp -Pstrict-checks verify
~~~

Ba lệnh phải dùng **cùng flags/profile/settings/JDK** với build cần tái hiện. Chạy `help:active-profiles` rồi quên `-Pstrict-checks` ở lệnh `verify` không làm Maven “nhớ” profile.

Khi chạy CI, nên lưu thông tin không nhạy cảm như Maven version, commit/build ID, execution ID, phase và kết quả gate. Không đưa password, token hay thông tin server nội bộ vào log nếu không cần.

## 20. Cách xác minh bước mới thật sự được Maven chạy

Không kết luận “đã cấu hình đúng” chỉ vì POM có plugin.

### 20.1. Xem effective POM

~~~bash
mvn -B -ntp help:effective-pom -Doutput=effective-pom.xml
~~~

Tìm:

- Plugin `maven-antrun-plugin` và version.
- Execution ID `generate-build-info` và `verify-outputs`.
- `<phase>generate-resources</phase>` và `<phase>verify</phase>`.
- Goals `run` và cấu hình `<target>`.
- Những profile, parent hoặc overrides có thể thay đổi configuration.

Với Help Plugin hỗ trợ:

~~~bash
mvn -B -ntp help:effective-pom -Dverbose=true -Doutput=effective-verbose.xml
~~~

Verbose có thể bổ sung comment truy nguồn cấu hình. **Effective POM cho biết mô hình hiệu lực, không tự chứng minh execution đã chạy**; bằng chứng thực thi phải đến từ log và đầu ra.

### 20.2. Đọc execution ID trong log

Lệnh:

~~~bash
mvn -B -ntp clean verify
~~~

Các dòng log liên quan thường có dạng tương tự:

~~~text
... antrun:3.1.0:run (generate-build-info) ...
... resources:3.3.1:resources (default-resources) ...
... compiler:3.13.0:compile (default-compile) ...
... surefire:3.2.5:test (default-test) ...
... jar:3.4.2:jar (default-jar) ...
... antrun:3.1.0:run (verify-outputs) ...
[echo] VERIFY: generated resource and JAR exist
~~~

Đây là **trích đoạn minh họa**, không phải bản log thực từ một máy đã chạy. Điều cần quan sát là **thứ tự execution ID**, chứ không học thuộc format của dấu gạch hoặc version trong log.

### 20.3. Kiểm chứng file/report thay vì chỉ đọc `BUILD SUCCESS`

Trong demo, kiểm tra cả:

- `target/generated-resources/demo/build-info.properties` tồn tại.
- `target/classes/build-info.properties` tồn tại.
- Unit test `readsGeneratedResource` PASS.
- JAR chứa `build-info.properties`.
- AntRun ở `verify` in thông báo khi hai điều kiện đạt.

Mỗi bằng chứng kiểm tra **một tầng khác nhau**: generator output, resource copy, test classpath, packaging và final gate. Nếu `BUILD SUCCESS` nhưng file không đúng, có thể goal được skip, execution không active hoặc test chưa bao phủ tình huống.

### 20.4. Describe goal

~~~bash
mvn -B -ntp help:describe -Dplugin=org.apache.maven.plugins:maven-antrun-plugin -Dgoal=run -Ddetail
~~~

Giúp xem tham số/metadata của goal. Đừng tự giả định mọi tham số XML đều được hỗ trợ qua `-D<sameName>`; tên user property cần đọc từ tài liệu plugin.

## 21. Checklist chất lượng của một automation mới

| Tiêu chí | Câu hỏi trước khi merge |
| --- | --- |
| Đúng lúc | Execution chạy sau khi đầu vào có và trước người tiêu thụ? |
| Phạm vi | Chạy mỗi module, mỗi Reactor hay chỉ trên CI/release? |
| Tái lập | `mvn clean verify` có tạo ra cùng output về mặt hợp đồng? |
| Idempotence | Chạy lại cùng phase có phá file/gây gọi API trùng không? |
| Cleanup | Output có nằm dưới `target` và được Maven clean xử lý? |
| Thứ tự | Có phụ thuộc mong manh vào nhiều goals cùng phase không? |
| Versioning | Plugin version và Maven/JDK đã được khóa phù hợp? |
| Chính sách | Goal fail có thực sự làm Maven build FAIL khi điều kiện sai? |
| Tests | Có test hoặc phép kiểm chứng chứng minh output hữu ích? |
| Bảo mật | Không ghi token, secret, đường dẫn nhạy cảm hoặc gọi nguồn không tin cậy? |
| Chi phí | Có thể fail sớm ở `validate` thay vì để tới `verify` không? |
| Portability | Có chạy được trên Windows/Linux, CI và local khi cần? |
| Side effects | Nếu goal publish/gửi email/cập nhật hạ tầng, có được ràng buộc vào release workflow thích hợp không? |
| Observability | Log ghi rõ execution ID, kết quả và nguyên nhân thất bại? |

Bước tự động hóa tốt phải có **mục đích và điều kiện hoàn thành rõ ràng**. Ví dụ nếu chỉ cần xác nhận file tồn tại, Ant `available`/`fail` phù hợp cho demo; nếu cần xác minh cấu trúc JAR, signature hay SBOM, phải dùng plugin/check thực sự kiểm tra nội dung đó, không đổi tên execution thành “security-gate” rồi coi như an toàn.

## 22. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| Chọn `verify` cho generator mà compiler cần | Generator chạy quá muộn | Bind ở `generate-sources` hoặc `generate-resources` thích hợp |
| Chọn `validate` cho check JAR | JAR chưa tạo từ build hiện tại | Bind check sau packaging, thường `verify` |
| Sinh resource ở cùng `process-resources` rồi chờ Maven copy | Default Resources Plugin có thể chạy trước generator | Sinh ở `generate-resources` |
| Bind kiểm tra sớm nhưng nó cần test report | Report chưa có | Chờ phase sau khi test/analysis hoàn tất |
| Đặt upload ở `package` | Mỗi build package có thể vô tình publish | Dùng release workflow/`deploy` được cấp quyền |
| Đặt bước mới ở `install` chỉ vì “đây là bước sau package” | `mvn verify` sẽ không chạy nó, quality gate bị bỏ qua | Nếu phải kiểm chứng trước publish, dùng `verify` |
| Chỉ ghi plugin trong `<pluginManagement>` | Không tự tạo execution | Khai báo plugin/execution thực ở nơi được áp dụng |
| Không đặt `<phase>` rồi đoán goal chạy ở `verify` | Goal có thể không có defaultPhase | Đọc descriptor và chọn phase rõ ràng |
| Dùng direct `plugin:goal` để chứng minh lifecycle đúng | Có thể bỏ qua prerequisites | Chạy phase đích từ clean và kiểm tra output |
| Không đăng ký generated Java source root | Compiler không thấy thư mục nguồn mới | Dùng generator hỗ trợ hoặc Build Helper Plugin |
| Kiểm tra `target` nhưng không `clean` | Artifact cũ che lỗi | Thử clean build và kiểm tra timestamp/nội dung |
| Thừa kế execution kiểm tra JAR vào `pom` module | Module không có JAR | Giới hạn scope/module/packaging |
| Chỉ chạy `integration-test` trong Maven 3 | Có thể bỏ dọn môi trường và gate ở verify | Dùng `verify` khi cần chuỗi hoàn chỉnh |
| Không đọc log execution | Có thể goal chưa từng chạy | So effective POM, log và artifact |
| Dùng JDK 17 nhưng plugin quá cũ | Plugin có thể không hỗ trợ `--release`/JUnit 5 | Ghim plugin versions phù hợp và chạy test thật |

## 23. Các tình huống lựa chọn phase thực tế

### 23.1. Sinh OpenAPI client trước compile

- **Đầu vào:** OpenAPI specification.
- **Đầu ra:** Java client classes.
- **Người tiêu thụ:** Compiler Plugin.
- **Phase hợp lý:** `generate-sources`.
- **Kiểm tra thêm:** generated source root, tốc độ/khả năng tái lập, generator version và đầu ra dưới `target`.

Nếu generator chỉ tạo file nhưng compiler không có source root đó, build sẽ không compile mã được sinh. Không sửa bằng cách gắn generator vào `compile` muộn mà bỏ qua nguồn gốc vấn đề.

### 23.2. Tạo thông tin version cho ứng dụng đọc lúc chạy

- **Đầu vào:** project version/build properties.
- **Đầu ra:** `build-info.properties` hoặc file text tương tự.
- **Người tiêu thụ:** Resources Plugin và runtime classpath.
- **Phase hợp lý:** `generate-resources`, hoặc dùng resource filtering trong `process-resources` nếu chỉ thay giá trị trong file có sẵn.
- **Kiểm tra thêm:** generated file có mặt trong JAR; không nhét credential hay internal CI secret vào artifact.

### 23.3. Kiểm tra quy tắc version JDK/dependency

- **Đầu vào:** POM/JDK properties và đôi khi dependency graph.
- **Đầu ra:** PASS/FAIL kèm lý do rõ ràng.
- **Phase hợp lý:** `validate` với plugin như Maven Enforcer, nếu rule có thể kiểm tra sớm.
- **Kiểm tra thêm:** không tạo tác dụng phụ; rule hoạt động trong Reactor và CI.

### 23.4. Quét artifact sau packaging

- **Đầu vào:** JAR/WAR/SBOM đã sinh hoặc report từ các bước trước.
- **Đầu ra:** báo cáo/gate; build fail nếu vi phạm policy.
- **Phase hợp lý:** `verify`, với goal phù hợp.
- **Kiểm tra thêm:** scanner thực sự xử lý đúng artifact cuối; nếu scanner chỉ chạy trên source, có thể chọn phase sớm hơn.

### 23.5. Chạy test dùng database tạm

- **Đầu vào:** packaged app, database/container được chuẩn bị.
- **Đầu ra:** integration-test report.
- **Phase hợp lý:** chuẩn bị trước integration-test, chạy tại `integration-test`, dọn sau đó, đánh giá ở `verify`.
- **Kiểm tra thêm:** timeout, port, quyền network, cleanup khi lỗi và Maven 3/4 semantics.

### 23.6. Chuyển artifact sang remote repository

- **Đầu vào:** artifact đã vượt quality gates.
- **Đầu ra:** artifact được publish.
- **Phase hợp lý:** `deploy` hoặc CI release stage rõ ràng.
- **Kiểm tra thêm:** release permission, `distributionManagement`, server credential, provenance và rollback. Không gắn việc publish vào `package` nếu chỉ build local cũng sẽ thực thi nó.

## 24. Bài tập có đáp án

1. **Cần sinh một Java class mà mã trong `src/main/java` import trực tiếp. Chọn phase nào?**  
   **Đáp án:** `generate-sources`, đồng thời bảo đảm compiler nhìn thấy source root chứa class được sinh.

2. **Cần sinh `build-info.properties` để Maven Resources Plugin copy vào JAR. Chọn phase nào?**  
   **Đáp án:** `generate-resources`; sau đó cấu hình resource directory đúng để `process-resources` copy.

3. **Cần kiểm tra JAR đã được đóng gói. Chọn `validate` hay `verify`?**  
   **Đáp án:** `verify` thường phù hợp vì packaging đã hoàn tất; `validate` quá sớm.

4. **Cần fail ngay khi build dùng JDK sai. Chọn phase nào?**  
   **Đáp án:** `validate` với goal kiểm tra phù hợp như Enforcer; không cần chờ `compile`.

5. **Tại sao `mvn clean antrun:run@verify-outputs` cố ý thất bại trong demo?**  
   **Đáp án:** Nó gọi goal trực tiếp sau clean, chưa tạo/copied resources hoặc JAR theo lifecycle.

6. **`goal@executionId` có tự chạy các phase trước execution đó không?**  
   **Đáp án:** Không mặc nhiên. Nó chọn cấu hình execution để gọi goal trực tiếp; cần xét cả hành vi đặc biệt/forked lifecycle của goal.

7. **`<pluginManagement>` có tự chạy một goal mới trong `verify` không?**  
   **Đáp án:** Không. Cần plugin/execution được áp dụng hoặc lifecycle mapping tương ứng.

8. **Nếu generator tạo file ở `process-resources` sau default Resources Plugin, chuyện gì xảy ra?**  
   **Đáp án:** File mới sinh có thể không được copy vào `target/classes` trong lần build ấy.

9. **Muốn copy/filter tài nguyên có sẵn từ `src/main/resources`, có bắt buộc tự viết generator ở `generate-resources` không?**  
   **Đáp án:** Không. Maven Resources Plugin ở `process-resources` đã có mục đích copy/filter.

10. **Nếu bước mới chỉ cần mã test được biên dịch, có nên đặt ở `generate-test-sources`?**  
    **Đáp án:** Không, đó là quá sớm. Chọn sau `test-compile` hoặc goal test/report phù hợp dựa vào đầu ra thật.

11. **Một goal kiểm tra security chỉ được gắn ở `install`. `mvn verify` có chạy nó không?**  
    **Đáp án:** Không. Nếu gate phải chạy trước phát hành, nên gắn ở một phase thích hợp không muộn hơn `verify`.

12. **Trong multi-module, vì sao check JAR có thể fail ở parent packaging `pom`?**  
    **Đáp án:** Parent đó không tạo JAR như module `jar`; execution được kế thừa hoặc áp dụng sai phạm vi.

13. **`mvn clean package` có tự chạy check custom ở `verify` trong demo không?**  
    **Đáp án:** Không. `verify` nằm sau `package`.

14. **Muốn biết custom execution thật sự đã được gọi, xem gì?**  
    **Đáp án:** Build log/execution ID và output/report; effective POM chỉ xác nhận cấu hình.

15. **Vì sao không nên chỉ định `integration-test` làm điểm cuối CI trên Maven 3 khi có container setup/cleanup?**  
    **Đáp án:** Có thể bỏ qua `post-integration-test` và gate ở `verify`, khiến tài nguyên bị bỏ lại hoặc kết quả chưa được kiểm chứng.

16. **Maven 4 có thể khiến một số nhận định về phase trung gian của Maven 3 thay đổi không?**  
    **Đáp án:** Có. Phải đọc tài liệu lifecycle tương ứng version, kiểm tra execution plan và chạy test với Maven thực tế.

17. **Maven `plugin:goal` chỉ định version rõ ràng bằng cú pháp nào?**  
    **Đáp án:** `groupId:artifactId:version:goal`, ví dụ `org.apache.maven.plugins:maven-compiler-plugin:3.13.0:compile`.

18. **Một file được generator tạo dưới `target` có tự trở thành resource Java không?**  
    **Đáp án:** Không. Phải có resource definition/copy phù hợp để file đi vào `target/classes`/artifact.

19. **Nếu goal thứ hai phụ thuộc output goal thứ nhất, nên làm gì?**  
    **Đáp án:** Chọn phase phù hợp bảo đảm thứ tự, kiểm tra goal execution plan và tránh dựa vào file cũ/cache.

20. **Đầu ra quan trọng nhất của quy trình chọn phase là gì?**  
    **Đáp án:** Một execution có prerequisite và output rõ ràng, chạy đúng trước–sau trong clean build, được kiểm chứng bằng tests/log/artifact.

## 25. Checklist trước khi merge bước tự động hóa

- [ ] Tôi đã mô tả chính xác đầu vào và đầu ra của bước mới.
- [ ] Tôi biết plugin/goal nào tạo đầu vào và goal nào dùng đầu ra.
- [ ] Tôi đã chọn phase **không quá sớm và không quá muộn**.
- [ ] Với generated sources, đã đăng ký source root đúng.
- [ ] Với generated resources, đã cấu hình `<resources>` và kiểm tra thứ tự copy.
- [ ] Nếu check cần JAR/WAR, đã đặt sau packaging.
- [ ] Nếu check fail được từ POM/JDK metadata, đã cân nhắc `validate`.
- [ ] Nếu liên quan integration tests, đã bảo đảm setup, cleanup và verify.
- [ ] Đã phân biệt default lifecycle, clean lifecycle và site lifecycle.
- [ ] Đã cấu hình `<executions>`, execution ID, phase và goals rõ ràng.
- [ ] Đã kiểm tra goal defaultPhase và hành vi forked lifecycle nếu có.
- [ ] Plugin được áp dụng thực sự, không chỉ nằm ở `<pluginManagement>`.
- [ ] Đã ghim Maven/JDK/plugin versions thích hợp cho CI.
- [ ] Đã xác minh profile, parent inheritance và phạm vi multi-module.
- [ ] Đã chạy `mvn clean verify` và kiểm tra báo cáo/output thật.
- [ ] Đã kiểm tra `mvn -version` và những khác biệt Maven 3 so với Maven 4.
- [ ] Script không phụ thuộc file cũ hoặc đường dẫn chỉ tồn tại trên máy cá nhân.
- [ ] Mọi file sinh ra có chỗ lưu và cơ chế cleanup có kiểm soát.
- [ ] Goal không vô tình publish/ghi đè dữ liệu bên ngoài khi local build.
- [ ] Log/test artifacts không chứa token, password hoặc secret.

## Tài liệu tham khảo chính thức

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): định nghĩa phase, mục đích của từng phase, thứ tự thực thi, packaging binding và khác biệt Maven 3/Maven 4.
- [Apache Maven — Guide to Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html): `<executions>`, goal, phase, defaultPhase, inheritance và direct invocation.
- [Apache Maven — Guide to Configuring Default Mojo Executions](https://maven.apache.org/guides/mini/guide-default-execution-ids.html): `default-cli`, `default-compile` và cách áp cấu hình.
- [Apache Maven — Maven AntRun Plugin 3.1.0](https://maven.apache.org/plugins-archives/maven-antrun-plugin-3.1.0/): `antrun:run`, Ant targets và ví dụ.
- [Apache Maven — Resources Plugin](https://maven.apache.org/plugins/maven-resources-plugin/): `resources:resources` và `resources:testResources`.
- [Apache Maven — Specifying Resource Directories](https://maven.apache.org/components/plugins/maven-resources-plugin-4.x/examples/resource-directory.html): cách đưa nhiều thư mục resource vào build.
- [Apache Maven — Maven Failsafe Plugin](https://maven.apache.org/surefire/maven-failsafe-plugin/): integration-test goals và bước verify.
- [Apache Maven — Maven Enforcer Plugin](https://maven.apache.org/enforcer/maven-enforcer-plugin/): chính sách phát hiện lỗi môi trường/dependency sớm.
- [Apache Maven — Maven Help Plugin](https://maven.apache.org/plugins/maven-help-plugin/): `help:effective-pom`, `help:active-profiles`, `help:describe` để chẩn đoán execution.

**Ghi nhớ:** Phase được chọn đúng khi **bước mới nhận đủ đầu vào, tạo output đúng thời điểm cho bước kế tiếp và được kiểm chứng trong clean build**. `generate-sources` dành cho mã trước compiler; `generate-resources` dành cho dữ liệu trước Resources Plugin; `validate` dành cho check sớm; `verify` dành cho kiểm chứng sau test/packaging. Hãy mô tả prerequisite/output trước khi bind goal, rồi xác nhận bằng log, test và artifact thực tế.
