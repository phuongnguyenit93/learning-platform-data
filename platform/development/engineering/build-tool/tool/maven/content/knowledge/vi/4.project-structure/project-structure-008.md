# Thư mục báo cáo và các artifact được đính kèm trong dự án Maven

## 1. Mục tiêu và các khái niệm cần phân biệt

Sau khi chạy Maven, dự án Java thường sinh ra nhiều tệp nằm ngoài thư mục mã nguồn: lớp `.class`, JAR/WAR, báo cáo kiểm thử, dữ liệu coverage, tài liệu Javadoc, và một số archive bổ sung. Hiểu vị trí và vai trò của các tệp này giúp người học đọc kết quả build, cấu hình CI và phân phối thư viện đúng cách.

Có **ba loại đầu ra khác nhau**:

1. **Build artifact chính**: sản phẩm được xác định bởi `<packaging>` trong `pom.xml`, chẳng hạn `my-lib-1.0.0.jar` với `packaging=jar` hoặc WAR với `packaging=war`. Đây là tệp Maven dùng làm artifact chính của dự án.
2. **Báo cáo (reports)**: kết quả kiểm tra/chẩn đoán như XML của Surefire, XML của Failsafe, HTML/XML của JaCoCo, website báo cáo trong `target/site/`. Chúng phục vụ con người hoặc công cụ đọc, **không tự động trở thành Maven artifact được publish**.
3. **Attached artifacts (artifact đính kèm của Maven)**: các tệp **bổ sung được plugin gắn vào cùng dự án trong quá trình build**, ví dụ `my-lib-1.0.0-sources.jar`, `my-lib-1.0.0-javadoc.jar` và `my-lib-1.0.0-tests.jar`. Các file này có thể được cài đặt hoặc triển khai cùng artifact chính khi chạy lifecycle phù hợp.

Một khái niệm khác là **CI artifacts**: tệp hoặc thư mục mà GitHub Actions, GitLab CI, Jenkins... giữ lại sau job (ví dụ zip test reports). CI artifact là cơ chế lưu/trao đổi tệp của hệ thống CI. Nó **khác** attached artifact trong Maven, dù một tệp có thể đồng thời được Maven tạo ra và CI upload.

Đường dẫn ở các mục sau là **mặc định thường gặp** của dự án Maven thông thường; kết quả thực tế phụ thuộc `pom.xml`, loại packaging, plugin, cấu hình riêng và phase đã chạy.

## 2. Cây thư mục target/ sau quá trình build

Theo mặc định, thuộc tính `${project.build.directory}` trỏ đến `<thư-mục-dự-án>/target`. Những thư mục sinh từ quá trình build được đặt dưới đây. Ví dụ minh họa cho dự án JAR có chạy unit test và cấu hình thêm các plugin phù hợp:

~~~text
my-lib/
├── pom.xml
├── src/
│   ├── main/java/
│   └── test/java/
└── target/                         # Thư mục build mặc định (được sinh ra)
    ├── classes/                    # .class và resource sau compile
    ├── test-classes/               # .class và resource sau testCompile
    ├── generated-sources/          # Có thể có nếu plugin sinh mã
    ├── generated-test-sources/     # Có thể có nếu plugin sinh mã test
    ├── maven-status/               # Metadata một số plugin dùng
    ├── surefire-reports/           # Kết quả unit test (nếu Surefire chạy test)
    │   ├── TEST-org.example.CalculatorTest.xml
    │   └── org.example.CalculatorTest.txt
    ├── failsafe-reports/           # Chỉ khi Failsafe được cấu hình và thực thi
    │   ├── TEST-org.example.CalculatorIT.xml
    │   └── failsafe-summary.xml
    ├── jacoco.exec                 # Dữ liệu coverage, nếu JaCoCo agent hoạt động
    ├── site/                       # Chỉ có khi chạy report/site tương ứng
    │   ├── index.html              # Chẳng hạn sau site generation
    │   └── jacoco/
    │       ├── index.html
    │       └── jacoco.xml
    ├── my-lib-1.0.0.jar            # Main artifact (packaging jar)
    ├── my-lib-1.0.0-sources.jar    # Attached artifact nếu Source Plugin tạo/attach
    ├── my-lib-1.0.0-javadoc.jar    # Attached artifact nếu Javadoc Plugin tạo/attach
    └── my-lib-1.0.0-tests.jar      # Attached artifact nếu JAR Plugin tạo test-jar
~~~

**Không phải lần chạy nào cũng tạo mọi mục trong cây.** Ví dụ, `mvn package` với dự án JAR cơ bản thường sinh JAR chính và các thư mục compile/test; `target/site/`, `failsafe-reports/`, `jacoco.exec` hoặc các JAR `-sources`/`-javadoc` sẽ không xuất hiện nếu plugin/goal tương ứng chưa được kích hoạt.

| Đường dẫn | Chứa gì? | Sinh ra khi nào? |
| --- | --- | --- |
| `target/classes/` | Bytecode và resource ứng dụng. | Sau `compile`, khi có nguồn/resource để xử lý. |
| `target/test-classes/` | Bytecode và resource cho test. | Sau `test-compile` với mã nguồn test. |
| `target/surefire-reports/` | Báo cáo unit test Surefire ở định dạng text/XML; tên file phụ thuộc test. | Surefire chạy trong phase `test` và có kết quả báo cáo. |
| `target/failsafe-reports/` | Báo cáo integration test và `failsafe-summary.xml`. | Failsafe được cấu hình và chạy các goal liên quan. |
| `target/site/` | Site HTML và một số báo cáo của plugin. | Chạy `site` hoặc goal/report được cấu hình tạo dữ liệu tại đây. |
| `target/site/jacoco/` | Báo cáo coverage HTML/XML/CSV. | JaCoCo report goal được chạy với dữ liệu execution phù hợp. |
| `target/*.jar` hoặc `*.war` | Main artifact và đôi khi attached artifacts. | Phase `package` và plugin đóng gói tương ứng. |

Maven đa module có một `target/` **riêng cho từng module con**. Đừng giả định toàn bộ báo cáo luôn ở `target/` của parent POM. Nếu tạo báo cáo tổng hợp (aggregate), vị trí do plugin/module chạy tác vụ aggregate quy định.

## 3. Cách xác định thư mục output trong POM

Maven POM có các thuộc tính và biểu thức thường dùng:

- `${project.basedir}`: thư mục gốc của module có POM đang xét.
- `${project.build.directory}`: nơi đặt đầu ra build, mặc định là `target` dưới module.
- `${project.build.outputDirectory}`: nơi đặt class/resource chính, mặc định `target/classes`.
- `${project.build.testOutputDirectory}`: nơi đặt class/resource test, mặc định `target/test-classes`.
- `${project.build.finalName}`: tên cơ sở của sản phẩm package (thông thường `artifactId-version`, chưa kèm extension).
- `${project.reporting.outputDirectory}`: thư mục báo cáo/website mặc định `target/site`.

Trong `pom.xml` có thể cấu hình các điểm này, ví dụ:

~~~xml
<build>
    <directory>target</directory>
    <finalName>my-lib-custom</finalName>
</build>
<reporting>
    <outputDirectory>${project.build.directory}/site</outputDirectory>
</reporting>
~~~

Đoạn XML là **mảnh cấu hình đặt trong `<project>`**, không phải POM độc lập. Khi đổi `finalName`, file JAR trên đĩa có thể đổi tên; **tọa độ artifact trong repository vẫn dựa trên** `groupId`, `artifactId`, `version`, `packaging/type` và `classifier`. Không suy ra Maven coordinates chỉ từ tên file trong `target/`.

Có thể xem giá trị thực tế mà Maven đã tính:

~~~bash
mvn help:evaluate -Dexpression=project.build.directory -q -DforceStdout
mvn help:evaluate -Dexpression=project.reporting.outputDirectory -q -DforceStdout
mvn help:effective-pom
~~~

`help:evaluate` yêu cầu Maven Help Plugin; lần đầu có thể cần tải plugin. `help:effective-pom` tổng hợp cấu hình từ POM hiện tại, parent, profile và default; phù hợp để tìm plugin đã đổi đường dẫn báo cáo. Trên dự án nhiều module, kiểm tra đúng module và profile đang chạy.

## 4. Báo cáo kiểm thử đơn vị: Surefire

Maven Surefire Plugin thường được gắn vào phase `test` của dự án JAR với lifecycle mặc định. Sau khi có unit test và chạy lệnh, Surefire sinh các tệp ở:

~~~text
target/surefire-reports/
├── TEST-org.example.CalculatorTest.xml
└── org.example.CalculatorTest.txt
~~~

- `TEST-*.xml`: nội dung test suite, số test/failed/skipped, thời gian và thông tin lỗi; CI thường phân tích theo chuẩn báo cáo JUnit XML tương thích.
- `*.txt`: bản tóm tắt dễ xem trong môi trường terminal/IDE.
- File báo cáo cụ thể có thể khác tùy engine test, cấu hình redirect output và cách chạy.

Lệnh phổ biến:

~~~bash
mvn -B -ntp test
mvn -B -ntp clean test
~~~

`test` chạy lifecycle đến phase `test`; `clean test` trước tiên xóa sản phẩm build của lần trước rồi chạy lại test. Nếu không có test, test bị skip hoặc Surefire không chạy, có thể **không có** file báo cáo mong đợi. Chỉ việc thấy thư mục `target/surefire-reports/` tồn tại không chứng minh mọi test của dự án đã được chạy thành công; cần đọc nội dung và exit code của build.

**Báo cáo HTML không mặc định là kết quả bắt buộc của lệnh `mvn test`.** Maven Surefire Report Plugin có thể chuyển dữ liệu XML thành báo cáo HTML/website, thường được đặt trong `target/site/` khi chạy goal/report phù hợp. Phân biệt plugin **Surefire chạy test** với **Surefire Report trình bày kết quả**.

## 5. Báo cáo integration test: Failsafe

Maven Failsafe Plugin dùng cho integration test, khác với Surefire ở mục đích và cách xử lý phase. Thông thường:

- `failsafe:integration-test` thực thi integration test tại phase `integration-test`.
- `failsafe:verify` đánh giá kết quả tại phase `verify`.
- Các phase `pre-integration-test` và `post-integration-test` có thể được dùng để khởi tạo/dọn dẹp môi trường kiểm thử tích hợp.

Khi được cấu hình, Failsafe sinh báo cáo XML/text trong:

~~~text
target/failsafe-reports/
├── TEST-org.example.DatabaseIT.xml
├── org.example.DatabaseIT.txt
└── failsafe-summary.xml
~~~

Chạy:

~~~bash
mvn -B -ntp verify
~~~

Dùng `verify` thay vì dừng ở `integration-test` khi cần thực thi đầy đủ chu trình setup → test → teardown → verify. **Failsafe không mặc nhiên chạy** chỉ vì dự án gọi `mvn verify`: bạn phải cấu hình plugin và binding phù hợp.

Ví dụ đoạn plugin tích hợp test (đặt trong `<build><plugins>...` của POM):

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.5.2</version>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Khi thêm đoạn này, Failsafe sẽ tham gia build theo lifecycle với bộ test phù hợp (quy ước thường gặp: `*IT.java`, `IT*.java`, `*ITCase.java`). Đoạn plugin **không thay thế việc viết integration test** và cũng không tự tạo cơ sở dữ liệu hay dịch vụ bên ngoài.

## 6. Báo cáo site, Javadoc và code coverage

### 6.1. Site/reporting: target/site/

Maven có cơ chế **site lifecycle** và mục `<reporting>` trong POM. Khi chạy `mvn site` và cấu hình plugin thích hợp, `target/site/` có thể chứa `index.html` cùng các báo cáo dự án. Các báo cáo như dependencies, plugins, test và coverage phụ thuộc vào bộ reporting plugins được bật.

~~~bash
mvn -B -ntp site
~~~

Cần phân biệt:

- `mvn site` tạo website báo cáo (theo cấu hình plugin và khả năng truy xuất dependencies).
- `mvn package` đóng gói ứng dụng/thư viện.
- `mvn deploy` đưa artifact của dự án lên **artifact repository** nếu cấu hình truy cập hợp lệ.
- `mvn site-deploy` là hoạt động khác, dùng để xuất bản site nếu đã cấu hình; nó không tương đương deploy Maven artifact.

**Không mặc định coi `target/site/` là nơi có mọi loại báo cáo**: test XML của Surefire/Failsafe mặc định nằm ở các thư mục riêng.

### 6.2. JaCoCo: target/site/jacoco/

JaCoCo là plugin đo mức độ thực thi mã trong quá trình test. Khi có agent thu thập dữ liệu và goal `jacoco:report` được thực hiện, các vị trí thường gặp:

~~~text
target/
├── jacoco.exec             # Dữ liệu execution (binary)
└── site/
    └── jacoco/
        ├── index.html      # Báo cáo HTML
        ├── jacoco.xml      # Dành cho công cụ phân tích/CI
        └── jacoco.csv      # Dữ liệu dạng CSV
~~~

`jacoco:prepare-agent` chuẩn bị Java agent; cần chạy test thực sự để có dữ liệu coverage. `jacoco:report` đọc dữ liệu đã thu thập và tạo báo cáo. Một ví dụ cấu hình plugin là:

~~~xml
<plugin>
    <groupId>org.jacoco</groupId>
    <artifactId>jacoco-maven-plugin</artifactId>
    <version>0.8.13</version>
    <executions>
        <execution>
            <goals>
                <goal>prepare-agent</goal>
            </goals>
        </execution>
        <execution>
            <id>report</id>
            <phase>verify</phase>
            <goals>
                <goal>report</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Phiên bản trong ví dụ là một phiên bản phát hành cụ thể để học; khi dùng thực tế cần chọn bản được nhóm hỗ trợ. Các plugin chạy test có thể dùng tham số JVM (`argLine`); nếu tùy chỉnh nó, cần phối hợp đúng để tránh vô hiệu hóa JaCoCo agent. Báo cáo coverage chỉ phản ánh các test thực sự chạy, không tự chứng minh mã không có lỗi.

### 6.3. Javadoc

`maven-javadoc-plugin` có thể tạo tài liệu API HTML (thường dưới `target/reports/apidocs` hoặc thư mục do plugin/reporting quyết định), và goal `javadoc:jar` đóng gói Javadoc thành **artifact phụ có classifier `javadoc`**. HTML trong `target/site/` và `-javadoc.jar` phục vụ hai mục đích: đọc tài liệu tại site và phân phối tài liệu kèm thư viện.

Vị trí đầu ra Javadoc thay đổi theo goal và cách gọi; kiểm tra cấu hình `outputDirectory`/`reportOutputDirectory` thay vì mặc định đoán một vị trí cho mọi plugin.

## 7. Attached artifacts là gì? Tọa độ và classifier

Maven quản lý artifact theo các phần chính: `groupId`, `artifactId`, `version`, `extension/type` và tùy chọn `classifier`. **Classifier** giúp phân biệt nhiều sản phẩm cùng một dự án, cùng phiên bản.

Giả sử POM của thư viện khai báo:

~~~xml
<groupId>org.example</groupId>
<artifactId>my-lib</artifactId>
<version>1.0.0</version>
<packaging>jar</packaging>
~~~

Các file có thể xuất hiện tại `target/`:

| File | Vai trò | Classifier |
| --- | --- | --- |
| `my-lib-1.0.0.jar` | Main artifact chứa class/resource chính. | Không có |
| `my-lib-1.0.0-sources.jar` | Attached artifact chứa source. | `sources` |
| `my-lib-1.0.0-javadoc.jar` | Attached artifact chứa Javadoc API. | `javadoc` |
| `my-lib-1.0.0-tests.jar` | Attached artifact chứa class/resource test. | `tests` |
| `my-lib-1.0.0-dist.zip` | Một assembly phụ nếu plugin tạo với classifier `dist`. | `dist` |

**Tên có hậu tố không đủ để chứng minh đã attach.** Maven cần plugin goal thực sự gọi cơ chế attach vào project, thường qua cấu hình `attach=true`. Một file `.jar` hay `.zip` do script đặt ở `target/` nhưng không được attach sẽ **không tự động được Maven Install/Deploy Plugin coi là artifact phụ**.

Các plugin thường thực hiện việc này:

- **Maven Source Plugin**: goal `source:jar-no-fork`, mặc định tạo `-sources.jar` và attach với classifier `sources`.
- **Maven Javadoc Plugin**: goal `javadoc:jar` tạo `-javadoc.jar` và có thể attach với classifier `javadoc`.
- **Maven JAR Plugin**: goal `jar:test-jar` tạo `-tests.jar`, mặc định classifier `tests`.
- **Maven Assembly Plugin** (khi được cấu hình): có thể tạo archive hoặc package riêng kèm classifier, tùy assembly descriptor và thiết lập `attach`.

Giới hạn quan trọng: nhiều artifact **cùng tọa độ đầy đủ** (cùng groupId/artifactId/version/type/classifier) sẽ xung đột khi install/deploy; mỗi artifact phụ nên có classifier và/hoặc extension phân biệt rõ.

## 8. Ví dụ Java 17 có thể chạy: test report + JAR chính + sources JAR

Ví dụ sau tạo được đầu ra để quan sát, thay vì chỉ giả định thư mục có sẵn. Cấu trúc dự án:

~~~text
reports-and-artifacts/
├── pom.xml
└── src/
    ├── main/
    │   └── java/org/example/Greeting.java
    └── test/
        └── java/org/example/GreetingTest.java
~~~

Tệp `pom.xml` hoàn chỉnh:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>reports-and-artifacts</artifactId>
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
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-source-plugin</artifactId>
                <version>3.4.0</version>
                <executions>
                    <execution>
                        <id>attach-sources</id>
                        <phase>package</phase>
                        <goals>
                            <goal>jar-no-fork</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/org/example/Greeting.java`:

~~~java
package org.example;

/** A small Java class used to inspect Maven build outputs. */
public final class Greeting {
    private Greeting() {
    }

    /** Creates a Vietnamese greeting for the given name. */
    public static String hello(String name) {
        return "Xin chào, " + name + "!";
    }

    public static void main(String[] args) {
        System.out.println(hello("Maven"));
    }
}
~~~

Tệp `src/test/java/org/example/GreetingTest.java`:

~~~java
package org.example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class GreetingTest {
    @Test
    void returnsExpectedGreeting() {
        assertEquals("Xin chào, Maven!", Greeting.hello("Maven"));
    }
}
~~~

Dùng JDK 17+ và Maven tương thích, chạy ở thư mục gốc:

~~~bash
mvn -B -ntp clean verify
java -cp target/reports-and-artifacts-1.0.0.jar org.example.Greeting
~~~

**stdout chính xác của lệnh `java`** (lệnh Maven trước đó có log riêng, không đưa vào đoạn output):

~~~text
Xin chào, Maven!
~~~

Sau khi build thành công:

~~~text
target/
├── classes/org/example/Greeting.class
├── test-classes/org/example/GreetingTest.class
├── surefire-reports/
│   ├── TEST-org.example.GreetingTest.xml
│   └── org.example.GreetingTest.txt
├── reports-and-artifacts-1.0.0.jar
└── reports-and-artifacts-1.0.0-sources.jar
~~~

Các tệp khác do compiler/resource/plugin tạo ra có thể cũng xuất hiện; cây trên chỉ liệt kê **những đầu ra trọng tâm**. `maven-source-plugin` với goal `jar-no-fork` chạy ở phase `package` và mặc định attach source JAR. `mvn verify` đi qua `package` nên tạo JAR chính và source JAR, nhưng **không tự cài chúng vào local repository**.

Bạn có thể kiểm tra JAR trực tiếp bằng công cụ của JDK:

~~~bash
jar tf target/reports-and-artifacts-1.0.0.jar
jar tf target/reports-and-artifacts-1.0.0-sources.jar
~~~

Kiểm tra kết quả:

- JAR chính có `org/example/Greeting.class`; không mặc định chứa `GreetingTest.class`.
- Source JAR có `org/example/Greeting.java`; đó là mã nguồn, không phải bytecode đã biên dịch.
- XML trong `surefire-reports/` cho biết test `GreetingTest` được thực hiện; cần đọc nội dung nếu muốn kiểm tra số test/failures.
- Lệnh chạy `java -cp ... org.example.Greeting` hoạt động vì class có phương thức `main`; JAR trong ví dụ không khai báo `Main-Class` nên không giả định `java -jar` hoạt động.

## 9. Gắn thêm Javadoc JAR và test JAR khi thật sự cần

### 9.1. Javadoc JAR

Nếu phát hành thư viện cho lập trình viên khác dùng, source/Javadoc JAR giúp IDE hiển thị nguồn và tài liệu API. Có thể bổ sung plugin sau vào `<build><plugins>` của POM ở mục 8:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-javadoc-plugin</artifactId>
    <version>3.11.2</version>
    <executions>
        <execution>
            <id>attach-javadocs</id>
            <phase>package</phase>
            <goals>
                <goal>jar</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Sau khi chạy `mvn clean package`, nếu Javadoc tạo thành công thì thường có:

~~~text
target/reports-and-artifacts-1.0.0-javadoc.jar
~~~

Kết quả Javadoc còn phụ thuộc mã nguồn, JDK, doclint và tham số plugin. Việc có `-javadoc.jar` **không đồng nghĩa** site đã được xuất bản lên website.

### 9.2. Test JAR

Một số nhóm cần chia sẻ test utilities hoặc test fixtures giữa các module. Bổ sung Maven JAR Plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-jar-plugin</artifactId>
    <version>3.4.2</version>
    <executions>
        <execution>
            <id>attach-tests</id>
            <phase>package</phase>
            <goals>
                <goal>test-jar</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Khi có compiled tests và goal chạy thành công, kết quả thường là:

~~~text
target/reports-and-artifacts-1.0.0-tests.jar
~~~

Dự án khác có thể khai báo dependency vào test JAR này như sau:

~~~xml
<dependency>
    <groupId>org.example</groupId>
    <artifactId>reports-and-artifacts</artifactId>
    <version>1.0.0</version>
    <type>test-jar</type>
    <classifier>tests</classifier>
    <scope>test</scope>
</dependency>
~~~

Để dependency này resolve được ở máy/dự án khác, test JAR cần được install/deploy vào repository mà dự án dùng có thể truy cập. **Test JAR không tự động kéo các dependency `test` của dự án phát hành sang dự án tiêu thụ**; bên dùng phải khai báo framework và dependencies cần thiết theo trường hợp thực tế. Cân nhắc tạo module test-fixtures riêng nếu chia sẻ nhiều logic/nguồn test.

## 10. Từ target/ đến local/remote repository: package, install, deploy

Có ba mốc khác nhau:

~~~text
mvn package
  └─ target/my-lib-1.0.0.jar
     target/my-lib-1.0.0-sources.jar (nếu đã tạo + attach)
          |
          v
mvn install
  └─ ~/.m2/repository/org/example/my-lib/1.0.0/
        my-lib-1.0.0.pom
        my-lib-1.0.0.jar
        my-lib-1.0.0-sources.jar (nếu attached)
          |
          v
mvn deploy
  └─ Remote artifact repository được cấu hình và cấp quyền
     (Maven phối hợp deploy plugin để chuyển các artifact)
~~~

- **`package`**: tạo ra sản phẩm và attached artifacts từ plugin trong build hiện tại.
- **`install`**: cài main artifact, POM và các attached artifacts mà plugin đã gắn vào dự án vào repository Maven cục bộ.
- **`deploy`**: phân phối chúng lên repository từ xa khi cấu hình `distributionManagement`/quyền truy cập phù hợp.
- **`target/` là build output**; **`~/.m2/repository/` là local artifact repository**. Không nhầm hai nơi và không commit nội dung của cả hai vào Git.
- **Report XML/HTML thông thường không được install/deploy kèm**. Nếu muốn phân phối báo cáo theo cơ chế Maven, phải có bước đóng gói/attach tương ứng; nếu chỉ cần kiểm tra CI thì upload report với CI là lựa chọn riêng.

Một file `-sources.jar` đã được tạo nhưng người dùng chỉ chạy `mvn package` thì **chưa chứng minh** artifact đó đã có trên repository remote. Ngược lại, chạy `mvn install` không tự tạo `sources.jar` nếu trước đó chưa có plugin/goal tạo và attach.

## 11. CI: lưu báo cáo và sản phẩm build sau mỗi lần chạy

Trong CI thường có hai thao tác riêng:

1. **Chạy Maven** để compile/test/package và trả mã thoát; job có thể thất bại khi test fail.
2. **Lưu kết quả build** trên hệ thống CI để mọi người tải về hoặc xem báo cáo, kể cả khi test thất bại (nếu pipeline được cấu hình).

Ví dụ đoạn workflow GitHub Actions (cần đặt trong job đã có bước checkout, thiết lập JDK và một dự án Maven phù hợp):

~~~yaml
- name: Verify
  run: ./mvnw -B -ntp clean verify

- name: Upload test reports
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: surefire-xml
    path: target/surefire-reports/*.xml
    if-no-files-found: warn

- name: Upload build JARs
  if: success()
  uses: actions/upload-artifact@v4
  with:
    name: build-jars
    path: target/*.jar
    if-no-files-found: warn
~~~

Đây là **đoạn steps minh họa**, yêu cầu `./mvnw` đã commit và chạy được trên runner Linux; nếu dự án dùng `mvn` thay Wrapper, thay đúng theo quy ước nhóm. `if: always()` giúp bước upload report có thể thực thi sau một test failure; bước upload vẫn cần các điều kiện thực tế của runner và có file phù hợp. `path` phải đổi cho module trong dự án đa module, ví dụ `module-a/target/surefire-reports/*.xml`.

**Quan trọng:** `actions/upload-artifact` lưu file vào hệ thống artifact của GitHub Actions; nó không thay `mvn deploy`, không tự đăng ký coordinates vào Maven Central hoặc repository nội bộ, và không biến XML test thành Maven attached artifact.

Ví dụ này lưu XML riêng, vì đó là dạng nhiều hệ thống CI phân tích trực tiếp. Nếu CI có chức năng “Publish JUnit test results”, cấu hình nó đọc đúng `TEST-*.xml`; đừng nhầm với việc chỉ upload ZIP chứa log.

## 12. Vệ sinh build, Git và khả năng tái lập

Nội dung trong `target/` thường là đầu ra có thể tái tạo. Mẫu `.gitignore` cơ bản:

~~~gitignore
target/
**/target/
~~~

Với dự án Maven đa module, `**/target/` giúp bỏ qua output trong module con. Chỉ đưa file report/artifact vào Git nếu có lý do đặc biệt được nhóm quy định; trong đa số dự án, **commit `pom.xml`, `src/`, cấu hình plugin/CI và Maven Wrapper** rồi tái tạo `target/` trên môi trường khác.

Các lệnh dọn và rebuild:

~~~bash
mvn clean
mvn -B -ntp clean verify
~~~

`mvn clean` xóa đầu ra mặc định trong thư mục build (thường là `target/`). Điều này có thể xóa cả logs/reports/JAR của lần chạy trước. Nếu cần giữ báo cáo để so sánh, **lưu hoặc xuất bản chúng trước bước clean**.

Để kiểm soát khả năng lặp lại, nên pin phiên bản Maven/Wrapper, JDK, plugin và dependencies quan trọng; tránh phụ thuộc vào trạng thái cache hoặc file build cũ. Khi chạy song song hoặc nhiều module, các plugin có thể ghi báo cáo ở các thư mục khác nhau; đừng trộn report của những lần build khác nhau rồi kết luận sai kết quả.

## 13. Chẩn đoán nhanh các tình huống thường gặp

| Hiện tượng | Kiểm tra trước tiên | Lý do thường gặp |
| --- | --- | --- |
| Không thấy `target/surefire-reports/` | `mvn test` có chạy Surefire? Có test phù hợp? | Không có test, skip test, khác plugin hoặc reportsDirectory đã đổi. |
| Không thấy `target/failsafe-reports/` | Failsafe có khai báo execution `integration-test`/`verify`? | `mvn verify` không tự kích hoạt Failsafe nếu không cấu hình. |
| Không thấy `target/site/` | Đã chạy `mvn site` hay report goal phù hợp? | `mvn package` không mặc định sinh toàn bộ website. |
| Không thấy `target/site/jacoco/index.html` | Có JaCoCo agent, test chạy và goal report? | Mới có `jacoco.exec` hoặc chưa chạy report; có thể test chưa thu coverage. |
| Có `-sources.jar` nhưng bên dùng không tải được | Đã `install`/`deploy` và repository cho phép truy cập? | File chỉ có trong `target/`, hoặc không được attach. |
| `-javadoc.jar` không tạo | Plugin goal chạy chưa, JDK/doclint có lỗi không? | Chưa cấu hình Javadoc Plugin, chạy sai phase hoặc JavaDoc thất bại. |
| CI “không có artifact” dù `mvn package` thành công | Đường dẫn `path` trong bước upload và working directory. | CI upload chỉ những file khớp mẫu; Maven không tự upload. |
| Build báo hai plugin cùng tạo JAR chính | Các goal có classifier riêng chưa? | Nhiều plugin tranh cùng main artifact, thiếu phân biệt classifier. |

**Quy trình debug đề xuất:** kiểm tra `pom.xml` và effective POM → đọc log cho biết goal nào đã chạy → tìm đúng `target/` của module → xem report XML hoặc JAR bằng công cụ phù hợp → kiểm tra phase `package/install/deploy` và cấu hình lưu trên CI. Tránh kết luận “plugin lỗi” chỉ vì file mong đợi không có ở một đường dẫn mặc định.

## 14. Câu hỏi tự kiểm tra

1. **`mvn test` thành công có bắt buộc tạo `target/site/index.html` không?** Không. Site/report HTML là tác vụ khác; Surefire thông thường tạo báo cáo XML/text dưới `target/surefire-reports/` nếu thực sự chạy test.
2. **`target/my-lib-1.0.0-sources.jar` xuất hiện thì đã được publish lên remote repository chưa?** Chưa chắc. Cần kiểm tra việc attach và quá trình `install`/`deploy`, không suy luận chỉ từ tên tệp trên đĩa.
3. **Có thể upload `target/surefire-reports/*.xml` như CI artifact mà không gắn chúng vào Maven artifact không?** Có. Đó là tính năng lưu file của CI.
4. **Tại sao chạy `mvn clean` rồi không thấy báo cáo cũ?** Clean lifecycle đã xóa sản phẩm build mặc định; báo cáo cần được giữ ở nơi khác trước khi clean nếu muốn tra cứu.
5. **Trong dự án đa module, tìm Surefire XML ở đâu?** Thường tại `<module>/target/surefire-reports/` của từng module có chạy test, trừ khi báo cáo được tùy chỉnh/gom riêng.

## 15. Tài liệu tham khảo

- [Apache Maven: POM Reference — build directory, finalName, reporting](https://maven.apache.org/pom.html)
- [Apache Maven Surefire Plugin — XML/text reports](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [Apache Maven Failsafe Plugin — integration test và verify](https://maven.apache.org/surefire/maven-failsafe-plugin/)
- [Apache Maven Source Plugin — source:jar-no-fork](https://maven.apache.org/plugins/maven-source-plugin/jar-no-fork-mojo.html)
- [Apache Maven JAR Plugin — jar:test-jar](https://maven.apache.org/plugins/maven-jar-plugin/test-jar-mojo.html)
- [Apache Maven Install Plugin — main và attached artifacts](https://maven.apache.org/plugins/maven-install-plugin/)
- [JaCoCo Maven Plugin — jacoco:report](https://www.jacoco.org/jacoco/trunk/doc/report-mojo.html)

**Điểm cần nhớ:** `target/` lưu đầu ra build; `surefire-reports/`, `failsafe-reports/` và `site/` giữ các loại báo cáo khác nhau; attached artifacts như `-sources.jar`/`-javadoc.jar`/`-tests.jar` là sản phẩm bổ sung được plugin **gắn với dự án Maven**; CI artifacts là cơ chế lưu file của pipeline. Đọc đúng đường dẫn, plugin, lifecycle phase và classifier giúp kiểm tra, phân phối và gỡ lỗi chính xác.
