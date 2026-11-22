# Kiểm tra hành vi ứng dụng và metadata sau khi gộp hoặc đóng bộ bằng Maven Shade và Assembly

## 1. Vì sao `mvn package` thành công vẫn chưa đủ?

Một dự án Java có thể biên dịch và vượt qua mọi unit test nhưng **artifact phát hành** vẫn không chạy được. Điều này đặc biệt dễ xảy ra khi dùng **Maven Shade Plugin** để tạo uber/fat JAR hoặc **Maven Assembly Plugin** để tạo bộ phân phối ZIP/TAR chứa chương trình và dependency.

Các lỗi thường chỉ xuất hiện **sau khi đóng gói**:

- Shaded JAR có các class cần thiết nhưng **thiếu `Main-Class`**, dẫn đến `no main manifest attribute`.
- JAR đã có manifest nhưng **thiếu dependency hoặc resource**; chạy thật ném `ClassNotFoundException`, `NoClassDefFoundError` hoặc `MissingResourceException`.
- `META-INF/services/...` của nhiều thư viện bị ghi đè hoặc không được chỉnh theo relocation, khiến **`ServiceLoader` không tìm thấy provider**.
- **Chữ ký JAR cũ** nằm trong uber JAR dù bytes đã bị gộp/thay đổi; runtime có thể báo lỗi verification.
- Shade relocation đổi package nhưng một file cấu hình, tên service hoặc chuỗi reflection vẫn trỏ tới class cũ.
- `minimizeJar` loại bỏ class chỉ được tải qua reflection, JNI hoặc ServiceLoader.
- Assembly ZIP có `bin/run.sh` nhưng thiếu **`lib/*.jar`**, hoặc script gọi sai classpath khi chạy từ thư mục khác.
- File trong Assembly bị đổi đường dẫn, thiếu quyền thực thi trên Unix, hoặc một bộ phân phối chứa **bản JAR không cùng version**.
- Các license/NOTICE, metadata phiên bản, service descriptor, resource hoặc SBOM bị mất, trùng hoặc không mô tả đúng sản phẩm mới.
- Unit tests chỉ chạy với `target/classes` và Maven test classpath; **không bao giờ kiểm tra đúng file `.jar`/`.zip` sẽ được phát hành**.

Vì vậy chất lượng đóng gói phải trả lời được **ba câu hỏi độc lập**:

1. **Cấu trúc:** artifact chứa đúng class, resource, metadata, dependency, script và đường dẫn không?
2. **Hành vi:** ứng dụng có chạy với đúng artifact, classpath và môi trường triển khai không; stdout, exit code và chức năng quan trọng có đúng không?
3. **Phát hành:** artifact có version, classifier, bản quyền, checksum, policy bảo mật và khả năng tái lập phù hợp không?

**Nguyên tắc:** *build được không đồng nghĩa chạy được; chạy được trong IDE không đồng nghĩa chạy được từ artifact cuối; JAR chạy được không đồng nghĩa ZIP/TAR phát hành đầy đủ.*

## 2. Phân biệt hai kiểu đầu ra phải kiểm tra

| Đặc điểm | Shade / uber JAR | Assembly / bộ phân phối |
| --- | --- | --- |
| Ý tưởng | **Gộp** class/resource từ app và dependency vào một JAR. | **Đóng bộ** một tập file: JAR, thư viện, script, cấu hình, tài liệu, license… |
| Hình thức phổ biến | `app-1.0.0-all.jar`. | `app-1.0.0-dist.zip`, `.tar.gz` hoặc một JAR tạo từ descriptor đặc biệt. |
| Cách chạy | `java -jar ...` nếu manifest hợp lệ. | `java -cp "lib/*" ...` hoặc script trong `bin/`. |
| Dependency | Thường được **unpack** vào cùng JAR. | Có thể giữ mỗi dependency là **JAR riêng** trong `lib/`. |
| Metadata cần quan sát | `MANIFEST.MF`, `META-INF/services`, chữ ký, license, module metadata. | Cây thư mục, script, file modes, dependency filenames/versions, manifest của từng JAR. |
| Lỗi hay gặp | Service metadata không merge, relocation, duplicate resource, invalid signatures. | Thiếu lib, sai classpath, thiếu script, lỗi executable bit, sai relative path. |
| Cần smoke test? | **Có**: chạy JAR độc lập. | **Có**: giải nén rồi chạy từ bộ phân phối. |

**Assembly `jar-with-dependencies` không tương đương toàn bộ tính năng Shade.** Descriptor dựng sẵn của Assembly có thể unpack dependency vào một JAR nhưng không cung cấp cùng mức kiểm soát relocation, resource transformers và ServiceLoader. Nếu cần quản lý va chạm resource hoặc đổi package, thường chọn Shade. Nếu cần một bộ đầy đủ gồm `bin/`, `lib/`, `conf/` và tài liệu, Assembly là công cụ phù hợp.

Một dự án **có thể tạo cả hai** cho hai kịch bản sử dụng, nhưng phải đặt **tên/classifier rõ ràng** để không nhầm JAR chính, JAR có dependency và ZIP.

## 3. Tư duy xác minh: kiểm tra artifact, không kiểm tra giả định

Hãy xem pipeline theo mốc:

~~~text
Mã Java + resource + POM + dependencies
             |
             v
mvn test -> tests trên classes và test classpath
             |
             v
mvn package
    |
    +-- maven-jar-plugin  -> thin JAR
    +-- maven-shade-plugin -> shaded JAR kèm dependencies
    +-- maven-assembly-plugin -> ZIP chứa thin JAR + lib/ + bin/
             |
             v
mvn verify
    |
    +-- Failsafe: mở đúng shaded JAR, kiểm tra manifest, resource, SPI
    +-- Failsafe: chạy `java -jar shaded.jar` như người dùng
    +-- Failsafe: mở ZIP, kiểm tra entry, giải nén vào temp riêng
    +-- Failsafe: chạy Java với classpath từ ZIP đã giải nén
             |
             v
Chỉ publish khi cả kiểm tra cấu trúc và hành vi đều PASS
~~~

**Không nên chỉ kiểm tra `target/classes`.** Tại thời điểm này Maven chưa thực hiện Shade/Assembly. Có thể class chính và tất cả dependency đều chạy tốt nhờ classpath mà Maven xây cho test, trong khi shaded JAR lại thiếu `META-INF/services` hoặc bộ phân phối thiếu một dependency runtime.

Một test artifact đáng tin cần:

- Đọc **đúng tên file** từ cấu hình build.
- Kiểm tra **exit code** của process, không chỉ việc process có in gì đó.
- Kiểm tra **stdout hoặc hành vi cụ thể** có thể tái lập.
- Kiểm tra **manifest và metadata** bên trong artifact, không chỉ sự tồn tại của file.
- Chạy trên một **thư mục giải nén tạm**, không dựa vào file trong project workspace.
- Có **timeout hữu hạn** và đóng process/tài nguyên trong trường hợp lỗi.
- Gắn vào phase **`verify`** hoặc một CI stage sau `package`, để fail build trước khi publish.

## 4. Những metadata quan trọng của JAR và ZIP

| Thành phần | Ý nghĩa | Cách kiểm tra |
| --- | --- | --- |
| `META-INF/MANIFEST.MF` | `Main-Class`, version và các manifest attributes khác. | `jar xf`/`unzip -p` hoặc `java.util.jar.JarFile#getManifest`. |
| `META-INF/services/<interface>` | Tên các provider cho Java `ServiceLoader`. | `jar tf`, đọc file rồi chạy hành vi SPI thật. |
| `app/build.properties` hoặc metadata riêng | Phiên bản, build marker và thuộc tính mà app đọc. | Mở resource trong JAR, đối chiếu version phát hành. |
| Class file | Phải có class chính và dependency cần dùng. | `jar tf`, `javap`, smoke test. |
| `META-INF/*.SF`, `*.RSA`, `*.DSA` | Chữ ký JAR cũ nếu dependency từng được ký. | Kiểm tra chính sách chữ ký sau shade; signature cũ có thể vô hiệu. |
| `META-INF/LICENSE`, NOTICE và legal notices | Nghĩa vụ bản quyền của dependency/sản phẩm. | Kiểm tra nội dung thực, đối chiếu license policy. |
| `META-INF/maven/...` | POM/properties của artifact gốc, có thể phản ánh dependency metadata. | Đọc theo ngữ cảnh, không coi chúng là bằng chứng duy nhất cho shaded content. |
| Assembly `lib/*.jar` | Runtime classpath của bộ phân phối. | Mở ZIP, liệt kê JAR và chạy với classpath thật. |
| Assembly `bin/run.sh` / `run.cmd` | Entrypoint cho người dùng. | Kiểm tra đường dẫn, file mode, line endings và chạy trên OS tương ứng. |
| Checksum/SBOM/provenance | Hỗ trợ truy nguyên artifact được phát hành. | Tính hash file cuối và tạo/kiểm tra SBOM theo công cụ/policy của tổ chức. |

**Không phải mọi file nằm trong `META-INF` đều được xóa.** Thư mục này chứa cả metadata cần thiết: service descriptors, manifest, legal notices và có thể là cấu hình framework. Filter rộng chỉ để “dọn JAR” có thể làm ứng dụng lỗi.

## 5. Ví dụ hoàn chỉnh: một app, hai dạng đóng gói, một bộ kiểm tra

Bài thực hành dùng:

- **JDK 17+** và Maven 3.x phù hợp với plugin versions được pin.
- **Apache Commons Lang 3.14.0** làm dependency runtime thật.
- Một giao diện `MessageSource` và provider được đăng ký qua **`ServiceLoader`**.
- `app/build.properties` có version được **Maven resource filtering** điền.
- **Shade Plugin 3.6.1** tạo **attached shaded JAR classifier `all`**, thêm `Main-Class` và `ServicesResourceTransformer`.
- **Assembly Plugin 3.7.1** tạo ZIP gồm **thin JAR**, Commons Lang JAR, `bin/run.sh` và `bin/run.cmd`.
- **Failsafe 3.2.5 + JUnit Jupiter 5.10.2** ở phase `verify` kiểm tra cấu trúc và thực thi **cả hai artifact**.

Các version được cố định để minh họa một cấu hình cụ thể, **không khẳng định đây là bản mới nhất** và không thay thế kiểm tra security/compatibility của dự án thực tế.

Cấu trúc thư mục:

~~~text
shade-assembly-verify/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── vn/example/packageqa/
│   │   │       ├── PackagedApp.java
│   │   │       └── spi/
│   │   │           ├── MessageSource.java
│   │   │           └── DefaultMessageSource.java
│   │   └── resources/
│   │       ├── app/build.properties
│   │       └── META-INF/services/
│   │           └── vn.example.packageqa.spi.MessageSource
│   ├── test/java/vn/example/packageqa/
│   │   ├── PackagedAppTest.java
│   │   └── PackagedArtifactIT.java
│   ├── dist/bin/
│   │   ├── run.sh
│   │   └── run.cmd
│   └── assembly/distribution.xml
~~~

**Không cần Docker hay database**. Test mở các artifact đã tạo bằng API JDK 17 (`JarFile`, `ZipFile`), khởi động Java child process và dùng JUnit `@TempDir`. Đây là bài kiểm tra **bộ phân phối thật**, không phải giả lập Shade/Assembly bằng mock.

## 6. pom.xml hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>shade-assembly-verify</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>true</filtering>
                <includes>
                    <include>app/build.properties</include>
                </includes>
            </resource>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>false</filtering>
                <includes>
                    <include>META-INF/services/**</include>
                </includes>
            </resource>
        </resources>

        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
                <configuration>
                    <encoding>UTF-8</encoding>
                    <delimiters>
                        <delimiter>@</delimiter>
                    </delimiters>
                    <useDefaultDelimiters>false</useDefaultDelimiters>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-shade-plugin</artifactId>
                <version>3.6.1</version>
                <executions>
                    <execution>
                        <id>make-shaded-jar</id>
                        <phase>package</phase>
                        <goals>
                            <goal>shade</goal>
                        </goals>
                        <configuration>
                            <shadedArtifactAttached>true</shadedArtifactAttached>
                            <shadedClassifierName>all</shadedClassifierName>
                            <createDependencyReducedPom>false</createDependencyReducedPom>
                            <minimizeJar>false</minimizeJar>
                            <filters>
                                <filter>
                                    <artifact>*:*</artifact>
                                    <excludes>
                                        <exclude>META-INF/*.SF</exclude>
                                        <exclude>META-INF/*.DSA</exclude>
                                        <exclude>META-INF/*.RSA</exclude>
                                    </excludes>
                                </filter>
                            </filters>
                            <transformers>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                                    <mainClass>vn.example.packageqa.PackagedApp</mainClass>
                                </transformer>
                            </transformers>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-assembly-plugin</artifactId>
                <version>3.7.1</version>
                <executions>
                    <execution>
                        <id>make-distribution</id>
                        <phase>package</phase>
                        <goals>
                            <goal>single</goal>
                        </goals>
                        <configuration>
                            <descriptors>
                                <descriptor>src/assembly/distribution.xml</descriptor>
                            </descriptors>
                            <appendAssemblyId>true</appendAssemblyId>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.2.5</version>
                <executions>
                    <execution>
                        <id>verify-packaged-artifacts</id>
                        <goals>
                            <goal>integration-test</goal>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                    <systemPropertyVariables>
                        <artifact.target>${project.build.directory}</artifact.target>
                    </systemPropertyVariables>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### Giải thích những lựa chọn có chủ đích

1. **`shadedArtifactAttached=true`** giữ **thin JAR** là project main artifact và gắn shaded JAR dưới classifier **`all`**. Vì vậy hai file có vai trò khác nhau.
2. **`createDependencyReducedPom=false`** được đặt cho bài tập để giữ POM đơn giản. Trong sản phẩm thật, việc bật/tắt dependency-reduced POM ảnh hưởng metadata dependency khi publish shaded artifact; phải quyết định theo cách artifact sẽ được tiêu thụ.
3. **`minimizeJar=false`** tránh làm ví dụ phức tạp bởi pruning class trong môi trường có ServiceLoader. Không bật giảm kích thước chỉ vì muốn JAR nhỏ nếu chưa có integration tests bao phủ code dùng reflection/SPI.
4. **`ServicesResourceTransformer`** là cơ chế của Shade để **gộp các entry `META-INF/services`** và sửa tên khi relocation áp dụng. Ở ví dụ này có **một provider do project tự khai báo**: test chứng minh descriptor được giữ và hoạt động, chứ **không chứng minh việc gộp hai provider trùng đường dẫn**; muốn test merge thực sự phải thêm nhiều provider từ nhiều dependency.
5. **`ManifestResourceTransformer`** đặt `Main-Class`. Class chính có đầy đủ package name, không phải tên file hay Maven artifactId.
6. Ba mẫu `META-INF/*.SF`, `*.DSA`, `*.RSA` loại **signature metadata cũ** thường không còn hợp lệ sau khi unpack/ghép signed JAR. Không hiểu đây là thao tác ký lại JAR.
7. Assembly Plugin gắn descriptor để tạo ZIP ở phase `package` **sau khi thin JAR đã được tạo**. Nội dung ZIP sẽ được định nghĩa trong file descriptor ở mục 10.
8. Failsafe chạy **sau package** nên có cơ hội mở file artifact cuối. `mvn test` chỉ chạy Surefire, **không thực hiện phần kiểm tra artifact**.
9. Cấu hình Resources Plugin chỉ filter `app/build.properties`, không filter dữ liệu SPI. Delimiter `@` tránh thay nhầm placeholder của framework.

Không đổi các phiên bản và classifier tùy hứng rồi giữ nguyên tên file hardcode trong test. Khi thay version sản phẩm, nên truyền artifact identity qua Maven properties hoặc API metadata của build để kiểm tra đúng file mới.

## 7. Các file mã nguồn và resource

### 7.1. src/main/java/vn/example/packageqa/spi/MessageSource.java

~~~java
package vn.example.packageqa.spi;

public interface MessageSource {
    String message();
}
~~~

Đây là SPI đơn giản: ứng dụng không khởi tạo provider bằng `new`, mà dùng `ServiceLoader` đọc tên class từ resource `META-INF/services`.

### 7.2. src/main/java/vn/example/packageqa/spi/DefaultMessageSource.java

~~~java
package vn.example.packageqa.spi;

public final class DefaultMessageSource implements MessageSource {
    @Override
    public String message() {
        return "maven";
    }
}
~~~

Provider có constructor không tham số mặc định và implement đúng interface. Nó sẽ được ServiceLoader tìm khi service descriptor đúng.

### 7.3. src/main/resources/META-INF/services/vn.example.packageqa.spi.MessageSource

~~~text
vn.example.packageqa.spi.DefaultMessageSource
~~~

**Tên file phải là full class name của service interface**. Nội dung là **full class name của provider**. Sai một ký tự, để file vào sai đường dẫn hoặc bị Shade overwrite/loại bỏ có thể khiến ServiceLoader không tìm được implementation.

### 7.4. src/main/resources/app/build.properties

~~~properties
app.version=@project.version@
app.kind=packaged-application
~~~

Đây là **metadata công khai**. Resource filtering điền Maven project version tại build time. **Không đưa password, token, private key hoặc dữ liệu cá nhân vào resource được đóng gói**; người nhận JAR có thể đọc dễ dàng.

Với `project.version=1.0.0`, file trong **JAR đã build** kỳ vọng là:

~~~properties
app.version=1.0.0
app.kind=packaged-application
~~~

Nếu kiểm tra file nguồn mà vẫn thấy `@project.version@` là bình thường. Cần kiểm tra **bản trong artifact**, không phải bản gốc trước filtering.

### 7.5. src/main/java/vn/example/packageqa/PackagedApp.java

~~~java
package vn.example.packageqa;

import org.apache.commons.lang3.StringUtils;
import vn.example.packageqa.spi.MessageSource;

import java.io.IOException;
import java.io.InputStream;
import java.util.Iterator;
import java.util.Properties;
import java.util.ServiceLoader;

public final class PackagedApp {
    private PackagedApp() {
    }

    public static String describe() throws IOException {
        Properties metadata = new Properties();

        try (InputStream in = PackagedApp.class.getResourceAsStream(
                "/app/build.properties")) {
            if (in == null) {
                throw new IOException("Missing resource app/build.properties");
            }
            metadata.load(in);
        }

        Iterator<MessageSource> providers =
                ServiceLoader.load(MessageSource.class).iterator();

        if (!providers.hasNext()) {
            throw new IllegalStateException("No MessageSource provider");
        }

        String word = providers.next().message();
        return "PACKAGED OK | " + StringUtils.capitalize(word)
                + " | version=" + metadata.getProperty("app.version");
    }

    public static void main(String[] args) throws IOException {
        System.out.println(describe());
    }
}
~~~

**Ba khả năng lỗi được làm lộ có chủ đích:**

- Thiếu Commons Lang runtime: `StringUtils` không có trong classpath.
- Thiếu `app/build.properties`: chương trình ném `IOException` rõ ràng.
- Thiếu service descriptor/provider: `ServiceLoader` không trả được implementation.

Vì thế smoke test đi qua **mã ứng dụng, library bên thứ ba và service metadata**, không chỉ in một chuỗi cố định từ `main`.

### 7.6. src/test/java/vn/example/packageqa/PackagedAppTest.java

~~~java
package vn.example.packageqa;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PackagedAppTest {
    @Test
    void worksOnMavenTestClasspath() throws Exception {
        assertEquals(
                "PACKAGED OK | Maven | version=1.0.0",
                PackagedApp.describe());
    }
}
~~~

Đây là **unit-level baseline**. Nó kiểm tra mã với classpath do Surefire/Maven cấp từ `target/classes` và dependencies; **không thay cho kiểm tra shaded JAR hoặc Assembly ZIP**.

Khi `mvn test` thành công, mới chứng minh rằng mã và resource trên **test classpath** đúng. Phần Failsafe ở mục 12 mới kiểm tra artifact cuối.

## 8. Vì sao cần kiểm tra ServiceLoader sau Shade?

Java `ServiceLoader` tìm resource có tên:

~~~text
META-INF/services/<fully-qualified-service-interface-name>
~~~

Tệp đó thường chứa các dòng provider class names. Nếu hai dependency JAR cùng có `META-INF/services/javax.example.Factory`, một thao tác gộp JAR không biết merge có thể **chỉ giữ một file**, khiến một số provider biến mất.

**ServicesResourceTransformer** của Shade được thiết kế để:

- Gom các nội dung service descriptors cùng đường dẫn thành **một descriptor hợp nhất**.
- Điều chỉnh tên class/service khi **Shade relocation** áp dụng.
- Giúp `ServiceLoader` thấy các provider có trong dependency graph sau khi đóng gói.

**Tuy nhiên:** cấu hình transformer **không tự chứng minh kết quả đúng**. Hãy kiểm tra `jar tf`, đọc resource và quan trọng nhất là **chạy ServiceLoader trong shaded JAR thật**. Với nhiều providers, viết assertion rằng **tất cả provider kỳ vọng** có thể được tìm thấy, không chỉ `iterator().hasNext()`.

Một thư viện có thể lưu plugin registry dưới `META-INF/spring`, `META-INF/native-image`, `META-INF/services`, `META-INF/plexus` hoặc file JSON/XML khác. **Không có một transformer mặc định xử lý mọi metadata.** Nếu framework có registry riêng, xem plugin transformer tương ứng và viết integration tests dựa trên chức năng của framework sau shade.

## 9. Manifest: `Main-Class`, `Class-Path` và runtime thực tế

Trong shaded JAR có manifest:

~~~text
Manifest-Version: 1.0
Main-Class: vn.example.packageqa.PackagedApp
~~~

Đây là **hai dòng quan trọng minh họa**, không phải toàn bộ manifest, và thứ tự/trường bổ sung có thể khác. `ManifestResourceTransformer` cấu hình entrypoint; Java launcher đọc `Main-Class` khi gọi:

~~~bash
java -jar target/shade-assembly-verify-1.0.0-all.jar
~~~

**Stdout chính xác của lệnh trên**, khi chạy bản đúng:

~~~text
PACKAGED OK | Maven | version=1.0.0
~~~

**Không nhầm với thin JAR** `target/shade-assembly-verify-1.0.0.jar`. Bài cố tình không cấu hình `Main-Class` cho thin JAR, vì Assembly sẽ khởi động nó qua **classpath gồm nhiều JAR**. Do đó `java -jar` trực tiếp trên thin JAR không phải lệnh được hỗ trợ trong ví dụ.

Khi dùng `java -jar`, Java launcher **không dùng `-cp` để thêm tùy ý thư viện cho ứng dụng theo cách chạy class trực tiếp**; launcher dựa vào JAR và manifest. Nếu shaded JAR thiếu dependency, không nên tạm sửa lỗi bằng cách chạy nó với **test classpath** rồi coi artifact là đạt.

Với Assembly, sử dụng:

~~~bash
java -cp "lib/*" vn.example.packageqa.PackagedApp
~~~

Dấu `*` trong classpath có nghĩa Java launcher mở rộng các JAR trong **thư mục `lib`**, không phải shell wildcard thông thường nếu đã được quote. Lệnh phải chạy từ thư mục có `lib`; script ở mục 11 tự xác định đường dẫn nên không phụ thuộc current working directory.

## 10. Descriptor Assembly tạo ZIP riêng

Tạo **src/assembly/distribution.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<assembly xmlns="http://maven.apache.org/ASSEMBLY/2.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/ASSEMBLY/2.2.0 https://maven.apache.org/xsd/assembly-2.2.0.xsd">
    <id>dist</id>
    <formats>
        <format>zip</format>
    </formats>
    <includeBaseDirectory>true</includeBaseDirectory>
    <baseDirectory>${project.build.finalName}</baseDirectory>

    <fileSets>
        <fileSet>
            <directory>${project.basedir}/src/dist/bin</directory>
            <outputDirectory>bin</outputDirectory>
            <fileMode>0755</fileMode>
            <includes>
                <include>run.sh</include>
                <include>run.cmd</include>
            </includes>
        </fileSet>
        <fileSet>
            <directory>${project.build.directory}</directory>
            <outputDirectory>lib</outputDirectory>
            <includes>
                <include>${project.build.finalName}.jar</include>
            </includes>
        </fileSet>
    </fileSets>

    <dependencySets>
        <dependencySet>
            <useProjectArtifact>false</useProjectArtifact>
            <useProjectAttachments>false</useProjectAttachments>
            <unpack>false</unpack>
            <scope>runtime</scope>
            <outputDirectory>lib</outputDirectory>
        </dependencySet>
    </dependencySets>
</assembly>
~~~

### Vì sao descriptor không chọn toàn bộ `target/*.jar`?

Trong ví dụ có hai JAR:

~~~text
shade-assembly-verify-1.0.0.jar       thin, không gộp dependency
shade-assembly-verify-1.0.0-all.jar   shaded, có dependency
~~~

Nếu Assembly copy **mọi JAR trong `target/`**, ZIP có thể chứa **cả thin và shaded JAR**, gây trùng class/dependency trong runtime `lib/*` và làm người dùng không biết phải chạy file nào.

Descriptor trên cố ý:

1. Copy **chính xác thin JAR** bằng tên `${project.build.finalName}.jar`.
2. Đưa dependency `runtime` chưa unpack vào **`lib/`**.
3. **Không đưa attached shaded JAR** vào dependencySet vì `useProjectAttachments=false`.
4. Đưa script vào `bin/`.
5. Đặt `id=dist`, nên Assembly Plugin với `appendAssemblyId=true` sinh ZIP có classifier/name `dist`.
6. Tạo **một thư mục gốc** theo finalName, giúp giải nén không rải file vào thư mục đang làm việc.

**Trong dự án phức tạp**, cần kiểm tra các dependency thực được chọn cho scope runtime, những classifier đặc biệt và artifact attachments. Quy tắc trên phù hợp với demo một dependency runtime; không nên sao chép mà không xem archive thực tế.

### ZIP kết quả dự kiến

Sau `mvn package`, file:

~~~text
target/shade-assembly-verify-1.0.0-dist.zip
~~~

có những entry chính:

~~~text
shade-assembly-verify-1.0.0/
├── bin/
│   ├── run.sh
│   └── run.cmd
└── lib/
    ├── shade-assembly-verify-1.0.0.jar
    └── commons-lang3-3.14.0.jar
~~~

Đây là **cây rút gọn**; ZIP có thể còn entry thư mục riêng. Vì Commons Lang là dependency `compile`, nó thuộc runtime dependency set và được đưa vào `lib`. JUnit Jupiter có scope `test`, **không thuộc bộ phân phối runtime**.

**Không dùng `jar-with-dependencies` để kiểm chứng kịch bản ZIP này**: đó là descriptor dựng sẵn tạo JAR khác, không phải một thư mục `bin` + `lib` theo custom descriptor.

## 11. Hai launcher độc lập với current directory

### 11.1. src/dist/bin/run.sh (Linux/macOS)

~~~sh
#!/usr/bin/env sh
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
exec java -cp "$HERE/../lib/*" vn.example.packageqa.PackagedApp "$@"
~~~

Chương trình nhận đường dẫn script, xác định thư mục `bin` rồi lấy JAR từ `../lib`. Vì vậy người dùng có thể khởi động từ thư mục khác mà không cần `cd` vào root giải nén.

`fileMode=0755` trong assembly descriptor yêu cầu quyền thực thi theo archive metadata cho script. Khi kiểm tra thật trên Unix, cần xác nhận **ZIP extractor có bảo tồn mode**; không phải mọi công cụ giải nén đều bảo toàn file permissions. Nếu quyền bị mất, có thể chạy `sh bin/run.sh` (không cần executable bit) hoặc đặt lại permission theo quy trình cài đặt.

**`set -eu` và `exec`** giúp script fail khi lệnh lỗi và thay thế shell bằng Java process. Điều này hữu ích cho exit code và signal propagation khi được runtime hỗ trợ.

### 11.2. src/dist/bin/run.cmd (Windows)

~~~bat
@echo off
set "HERE=%~dp0"
java -cp "%HERE%..\lib\*" vn.example.packageqa.PackagedApp %*
exit /b %ERRORLEVEL%
~~~

`%~dp0` là thư mục của chính file `.cmd`. Cú pháp lớp `vn.example.packageqa.PackagedApp` và path `lib\*` được Java launcher nhận trên Windows. Chạy bằng `cmd.exe` hoặc mở file `.cmd` trong môi trường Windows tương ứng.

**Khác biệt Windows/Unix:** không thể đánh giá đầy đủ hai launcher chỉ bằng một job Linux. CI có thể dùng ma trận OS hoặc tối thiểu smoke test Java classpath không phụ thuộc script, kết hợp kiểm tra script tồn tại và mode/line endings.

### 11.3. Chạy sau khi giải nén

**Linux/macOS** (nếu đã cài `unzip`):

~~~bash
unzip -q target/shade-assembly-verify-1.0.0-dist.zip -d target/unpacked
sh target/unpacked/shade-assembly-verify-1.0.0/bin/run.sh
~~~

**Windows PowerShell:**

~~~powershell
Expand-Archive -LiteralPath target/shade-assembly-verify-1.0.0-dist.zip -DestinationPath target/unpacked
& target\unpacked\shade-assembly-verify-1.0.0\bin\run.cmd
~~~

**Stdout chính xác của ứng dụng qua cả hai launcher khi môi trường đúng:**

~~~text
PACKAGED OK | Maven | version=1.0.0
~~~

`Expand-Archive` và `unzip` là thao tác hệ điều hành khác nhau; nếu thư mục output đã tồn tại và chứa file cũ, nên dùng một thư mục trống mới cho mỗi lượt kiểm tra. Không được coi file cũ trong `target/unpacked` là bằng chứng của ZIP mới.

## 12. Tự động kiểm tra hai artifact bằng Failsafe và Java 17

Tạo **src/test/java/vn/example/packageqa/PackagedArtifactIT.java**.

Test này chạy **sau phase package**, xác minh manifest và entry trong shaded JAR, gọi `java -jar`, mở ZIP, giải nén vào `@TempDir` an toàn và **chạy Java với `lib/*` lấy từ đúng ZIP đã giải nén**.

~~~java
package vn.example.packageqa;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.List;
import java.util.Properties;
import java.util.concurrent.TimeUnit;
import java.util.jar.Attributes;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

class PackagedArtifactIT {
    private static final String NAME = "shade-assembly-verify-1.0.0";
    private static final String MAIN =
            "vn.example.packageqa.PackagedApp";
    private static final String EXPECTED =
            "PACKAGED OK | Maven | version=1.0.0";

    private static Path artifact(String suffix) {
        String target = System.getProperty("artifact.target");
        if (target == null || target.isBlank()) {
            throw new IllegalStateException("Missing artifact.target");
        }
        return Path.of(target).resolve(NAME + suffix);
    }

    private static String launch(String... args) throws Exception {
        String executable = System.getProperty("os.name")
                .toLowerCase(java.util.Locale.ROOT)
                .contains("win") ? "java.exe" : "java";

        Path java = Path.of(System.getProperty("java.home"),
                "bin", executable);

        List<String> command = new ArrayList<>();
        command.add(java.toString());
        command.addAll(List.of(args));

        Process process = new ProcessBuilder(command)
                .redirectErrorStream(true)
                .start();

        if (!process.waitFor(20, TimeUnit.SECONDS)) {
            process.destroyForcibly();
            process.waitFor(5, TimeUnit.SECONDS);
            fail("Java child process timed out");
        }

        String output = new String(
                process.getInputStream().readAllBytes(),
                StandardCharsets.UTF_8).strip();

        assertEquals(0, process.exitValue(), "Java output: " + output);
        return output;
    }

    @Test
    void shadedJarHasMetadataAndRuns() throws Exception {
        Path shaded = artifact("-all.jar");
        assertTrue(Files.isRegularFile(shaded));

        try (JarFile jar = new JarFile(shaded.toFile())) {
            assertNotNull(jar.getManifest());
            assertEquals(MAIN, jar.getManifest()
                    .getMainAttributes().getValue(
                            Attributes.Name.MAIN_CLASS));

            assertNotNull(jar.getJarEntry(
                    "org/apache/commons/lang3/StringUtils.class"));

            assertNotNull(jar.getJarEntry(
                    "META-INF/services/"
                    + "vn.example.packageqa.spi.MessageSource"));

            JarEntry metadata = jar.getJarEntry("app/build.properties");
            assertNotNull(metadata);

            Properties props = new Properties();
            try (InputStream in = jar.getInputStream(metadata)) {
                props.load(in);
            }

            assertEquals("1.0.0", props.getProperty("app.version"));
            assertEquals("packaged-application",
                    props.getProperty("app.kind"));

            assertFalse(jar.stream().map(JarEntry::getName).anyMatch(
                    n -> n.startsWith("META-INF/")
                            && (n.endsWith(".SF")
                            || n.endsWith(".DSA")
                            || n.endsWith(".RSA"))));
        }

        assertEquals(EXPECTED, launch("-jar", shaded.toString()));
    }

    @Test
    void distributionZipContainsLibsAndRuns(
            @TempDir Path temp) throws Exception {
        Path zipPath = artifact("-dist.zip");
        assertTrue(Files.isRegularFile(zipPath));

        String rootName = NAME + "/";
        Path root = temp.toAbsolutePath().normalize();

        try (ZipFile zip = new ZipFile(zipPath.toFile())) {
            assertNotNull(zip.getEntry(rootName + "bin/run.sh"));
            assertNotNull(zip.getEntry(rootName + "bin/run.cmd"));
            assertNotNull(zip.getEntry(rootName + "lib/" + NAME + ".jar"));
            assertNotNull(zip.getEntry(
                    rootName + "lib/commons-lang3-3.14.0.jar"));

            assertFalse(zip.stream().map(ZipEntry::getName).anyMatch(
                    n -> n.equals(rootName + "lib/" + NAME + "-all.jar")));

            Enumeration<? extends ZipEntry> entries = zip.entries();
            while (entries.hasMoreElements()) {
                ZipEntry entry = entries.nextElement();
                Path output = root.resolve(entry.getName()).normalize();

                // Không cho entry vượt khỏi thư mục giải nén của test.
                assertTrue(output.startsWith(root),
                        "Unsafe zip entry: " + entry.getName());

                if (entry.isDirectory()) {
                    Files.createDirectories(output);
                } else {
                    Files.createDirectories(output.getParent());
                    try (InputStream in = zip.getInputStream(entry)) {
                        Files.copy(in, output,
                                StandardCopyOption.REPLACE_EXISTING);
                    }
                }
            }
        }

        Path lib = root.resolve(NAME).resolve("lib");
        assertTrue(Files.isRegularFile(lib.resolve(NAME + ".jar")));
        assertEquals(EXPECTED,
                launch("-cp", lib.resolve("*").toString(), MAIN));
    }
}
~~~

### Những gì test thực sự chứng minh

**`shadedJarHasMetadataAndRuns`:**

1. File shaded JAR tồn tại.
2. Manifest có `Main-Class` đúng.
3. Class bên thứ ba `StringUtils` có mặt trong JAR.
4. Service descriptor có mặt.
5. Metadata `app/build.properties` đã được filter và mang version đúng.
6. Không còn các signature files `.SF`, `.DSA`, `.RSA` ở root `META-INF` theo quy tắc audit mẫu.
7. Một **process Java độc lập** chạy shaded JAR và thoát mã 0.
8. Stdout thực của chương trình là chuỗi kỳ vọng.

**`distributionZipContainsLibsAndRuns`:**

1. ZIP tạo bởi Assembly có `bin/run.sh` và `bin/run.cmd`.
2. Có **thin JAR** và Commons Lang runtime JAR đúng version.
3. Không vô tình kèm **attached shaded JAR** trong `lib/`.
4. Từng ZIP entry được giải nén vào thư mục JUnit `@TempDir`; kiểm tra đường dẫn đã normalize để tránh **Zip Slip**.
5. Java child process chỉ dùng **classpath từ thư mục giải nén**, không dùng Maven test classpath.
6. Output và exit code khớp với shaded JAR.

**Giới hạn test:** Nó chưa chạy **file script `.sh`/`.cmd` trực tiếp**, chưa kiểm tra Unix executable bits, container startup, TLS, resource config phức tạp hoặc giấy phép của tất cả dependencies. Những bước đó phải có kiểm chứng riêng theo hệ điều hành và cách phân phối thực tế.

**Không nhầm `@TempDir` với cleanup toàn bộ CI.** Nó dọn file tạm thuộc test bình thường; nếu agent bị kill cưỡng bức có thể còn file. Dùng cơ chế workspace cleanup/retention của CI bổ sung.

### Vì sao Java process có timeout?

Một chương trình có thể treo khi tìm provider, chờ network hoặc mắc lỗi startup. `waitFor(20, TimeUnit.SECONDS)` tránh test treo vô hạn, nhưng **20 giây là giá trị ví dụ** cho app nhỏ này, không phải mức tối ưu cho mọi service. Nếu timeout, test cưỡng bức dừng process. Trong sản phẩm thật, nên thu thập log có kiểm soát, giới hạn dung lượng output và dừng tiến trình con theo chính sách để tránh zombie processes.

Vì app mẫu chỉ in **một dòng rất ngắn**, việc đọc output sau `waitFor` là chấp nhận được. Với ứng dụng tạo **rất nhiều stdout/stderr**, nên tiêu thụ output **đồng thời** hoặc ghi vào file log giới hạn dung lượng; nếu buffer output đầy trước khi process exit, chờ exit rồi mới đọc có thể tạo deadlock.

## 13. Lệnh build và đầu ra kỳ vọng

Từ thư mục chứa POM:

~~~bash
mvn --version
mvn -B -ntp clean verify
~~~

Trong lifecycle:

- **Surefire** chạy `PackagedAppTest` (baseline với test classpath).
- `package` tạo **thin JAR**, **attached shaded JAR** và **Assembly ZIP**.
- **Failsafe** ở `integration-test` chạy **hai method của `PackagedArtifactIT`** trên artifact cuối.
- Goal **`failsafe:verify`** đưa kết quả test vào quyết định `BUILD SUCCESS` hoặc `BUILD FAILURE`.

Nếu tất cả pass, ba file kết quả quan trọng là:

~~~text
target/shade-assembly-verify-1.0.0.jar
target/shade-assembly-verify-1.0.0-all.jar
target/shade-assembly-verify-1.0.0-dist.zip
~~~

Chạy shaded JAR theo cách người dùng:

~~~bash
java -jar target/shade-assembly-verify-1.0.0-all.jar
~~~

**Stdout chính xác của lệnh `java -jar` đó:**

~~~text
PACKAGED OK | Maven | version=1.0.0
~~~

Các dòng log Maven/Surefire/Failsafe và thứ tự chúng xuất hiện **không cố định** vì môi trường, plugin logs và cache. Không so toàn bộ stdout của `mvn verify` với một mẫu giả.

### Quan sát reports

**Linux/macOS:**

~~~bash
ls target/surefire-reports
ls target/failsafe-reports
~~~

**Windows PowerShell:**

~~~powershell
Get-ChildItem target\surefire-reports
Get-ChildItem target\failsafe-reports
~~~

Maven Surefire/Failsafe tạo báo cáo test thông thường. Nếu bạn xóa hoặc đổi tên `PackagedArtifactIT`, `failIfNoTests=true` có thể giúp phát hiện suite IT không được chạy, thay vì cho pipeline xanh một cách sai lệch.

### Vì sao phải dùng `verify`, không chỉ `package`?

`mvn package` tạo JAR/ZIP nhưng **chưa chạy Failsafe IT**, vì chúng được gắn với các phase sau package. Nếu CI publish ngay sau `mvn package`, bạn đã bỏ qua bộ kiểm chứng artifact cuối. Nên chạy:

~~~bash
mvn -B -ntp clean verify
~~~

và chỉ publish khi goal `verify` thành công, đồng thời các bước secret/license/SBOM checks theo chính sách cũng pass.

## 14. Kiểm tra thủ công bằng `jar`, `javap` và ZIP tools

JUnit kiểm tra tự động không ngăn được mọi lỗi. Khi debug, nên biết kiểm tra thủ công đúng artifact.

### 14.1. Liệt kê JAR entries

~~~bash
jar tf target/shade-assembly-verify-1.0.0-all.jar
~~~

Tìm:

~~~text
vn/example/packageqa/PackagedApp.class
vn/example/packageqa/spi/DefaultMessageSource.class
org/apache/commons/lang3/StringUtils.class
META-INF/services/vn.example.packageqa.spi.MessageSource
app/build.properties
META-INF/MANIFEST.MF
~~~

Đây là **các entry kỳ vọng**, không phải toàn bộ kết quả `jar tf`. Nếu `StringUtils.class` không có mặt, phần gộp dependency có thể sai, và lệnh `java -jar` có khả năng lỗi dù `mvn test` đã pass.

### 14.2. Đọc manifest

**Linux/macOS có unzip:**

~~~bash
unzip -p target/shade-assembly-verify-1.0.0-all.jar META-INF/MANIFEST.MF
~~~

**Dùng JDK thuần:** `java.util.jar.JarFile` như trong `PackagedArtifactIT`. `jar xf` cũng có thể giải nén, nhưng hãy thực hiện ở **thư mục tạm** để không tạo/sửa file không chủ đích trong source tree.

Đọc `Main-Class` và kiểm tra chính xác class có tồn tại, có method `public static void main(String[] args)` hợp lệ. Một manifest có Main-Class nhưng class không còn sau relocation cũng là artifact hỏng.

### 14.3. Kiểm tra ServiceLoader

~~~bash
unzip -p target/shade-assembly-verify-1.0.0-all.jar META-INF/services/vn.example.packageqa.spi.MessageSource
~~~

Trong ví dụ kỳ vọng có dòng:

~~~text
vn.example.packageqa.spi.DefaultMessageSource
~~~

Cách kiểm tra mạnh hơn là **chạy chương trình** để Java `ServiceLoader` thực sự khởi tạo provider. Nếu chỉ xem file có tồn tại mà provider class đã bị relocate sai hoặc không có constructor phù hợp, `ServiceLoader` vẫn có thể ném `ServiceConfigurationError`.

### 14.4. Kiểm tra Assembly ZIP

~~~bash
jar tf target/shade-assembly-verify-1.0.0-dist.zip
~~~

JDK `jar` có thể liệt kê các entry ZIP theo định dạng ZIP/JAR; trên Windows và Linux đều có thể dùng nếu JDK hiện diện. Đối chiếu `bin/`, `lib/`, filenames và version. Không kỳ vọng các OS khác nhau xử lý permission bits giống nhau.

### 14.5. Kiểm tra class-file version

~~~bash
javap -verbose -classpath target/shade-assembly-verify-1.0.0-all.jar vn.example.packageqa.PackagedApp
~~~

Với `maven.compiler.release=17`, class ứng dụng được biên dịch theo Java 17 có **major version 61**. Lưu ý **không phải mọi class trong shaded JAR đều tự động trở thành major 61**: class dependency giữ bytecode ban đầu của chúng trừ khi một công cụ khác biến đổi.

Một JAR có entrypoint Java 17 mà được chạy bằng Java 11 có thể báo `UnsupportedClassVersionError`, dù manifest/Main-Class hoàn toàn đúng. Vì vậy **kiểm thử metadata phải đi kèm kiểm thử trên JVM thấp nhất được hỗ trợ**.

## 15. Kiểm tra dependency và runtime classpath sau Assembly

Một bộ phân phối kiểu `lib/` có hai nguồn class:

1. **Thin JAR của ứng dụng:** `PackagedApp`, SPI classes và resource.
2. **Dependency JARs:** `commons-lang3-3.14.0.jar` và các runtime dependencies khác của dự án thực tế.

Khi gọi:

~~~bash
java -cp "lib/*" vn.example.packageqa.PackagedApp
~~~

Java launcher sẽ tìm class trên các JAR trong thư mục `lib`; không cần tự thêm từng JAR bằng cách nối `:` trên Unix hay `;` trên Windows cho ví dụ này.

**Tuy nhiên:** thứ tự mở rộng wildcard `lib/*` **không nên được coi là quy tắc ổn định để ưu tiên class khi nhiều JAR chứa cùng class**. Nếu ZIP chứa cả shaded JAR lẫn thin JAR/dependencies, classpath có duplicate classes và hành vi có thể phụ thuộc thứ tự không dự đoán được. Đó là lý do test yêu cầu **không có `-all.jar` trong `lib/`**.

Nếu ứng dụng có nhiều version của một thư viện, hãy xem:

~~~bash
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree
~~~

Đây là lệnh để hiểu **graph Maven được giải quyết**, nhưng **chưa chứng minh ZIP chứa đúng những JAR đã được chọn**. Phải kiểm tra cả ZIP và thực thi chương trình từ ZIP.

**`dependency:tree` + `jar tf`/ZIP inspection + smoke test** là ba góc nhìn bổ sung cho nhau.

## 16. Shaded JAR và vấn đề chữ ký

Một JAR từ repository có thể có signature metadata dưới `META-INF`:

~~~text
META-INF/SOMELIB.SF
META-INF/SOMELIB.RSA
~~~

Sau Shade, class/resource bytes và cấu trúc JAR đã thay đổi, nên **chữ ký gốc không còn xác nhận nội dung JAR mới**. Nếu giữ signature files mà không phù hợp, JVM có thể phát sinh `SecurityException` hoặc lỗi xác thực signature.

Filter trong POM ví dụ:

~~~xml
<filters>
    <filter>
        <artifact>*:*</artifact>
        <excludes>
            <exclude>META-INF/*.SF</exclude>
            <exclude>META-INF/*.DSA</exclude>
            <exclude>META-INF/*.RSA</exclude>
        </excludes>
    </filter>
</filters>
~~~

Đây là **đoạn cấu hình Shade**, không phải POM độc lập. Nó **loại các file signature cũ** khi tạo JAR mới. **Không đồng nghĩa shaded JAR đã được ký hợp lệ**, cũng không phải giấy phép để bỏ xác minh nguồn gốc dependency.

Nếu môi trường cần artifact signing, quy trình là **kiểm tra dependency nguồn → shade/package → ký artifact cuối theo chính sách → xác minh chữ ký mới trước phát hành**. Đừng copy chữ ký của JAR gốc rồi coi chúng có hiệu lực với JAR đã gộp.

## 17. Relocation: kiểm tra class name lẫn resource references

**Relocation** là chức năng Shade giúp đổi namespace package của một dependency để tránh xung đột classpath. Ví dụ **minh họa, không áp dụng trong POM chạy được ở mục 6**:

~~~xml
<relocations>
    <relocation>
        <pattern>com.vendor.internal</pattern>
        <shadedPattern>vn.example.hidden.vendor</shadedPattern>
    </relocation>
</relocations>
~~~

Khi relocation thực sự được dùng:

- Class files và một số references có thể được viết lại trong shaded artifact.
- `ServicesResourceTransformer` có thể đổi service names và providers trong `META-INF/services`.
- Reflection theo tên class **dạng chuỗi**, serialization type ID, resource path, framework scan config hoặc JNI có thể không được biến đổi đúng trong mọi trường hợp.
- Public API/stack trace có thể mang package mới; tính tương thích nhị phân và debug phải được xem xét.

**Test cần kiểm tra** rằng package cũ không còn ở những chỗ cần được relocate, package mới có class hợp lệ, và **hành vi qua ServiceLoader/reflection** vẫn đúng. Không được chỉ nhìn class file tên mới rồi kết luận framework sẽ tìm được service.

Với môi trường multi-module, relocation một module mà không đồng bộ consumers có thể tạo class identity mismatch. Cần kiểm tra module boundary và artifact publication, không chỉ chỉnh một `shadedPattern`.

## 18. Minimize JAR và những entrypoint động

Shade có `<minimizeJar>true</minimizeJar>` và tùy chọn `entryPoints` trong những phiên bản hỗ trợ. Cơ chế này phân tích dependency graph ở mức class để loại class được cho là không cần.

**Rủi ro:** những class chỉ được tải qua:

- Java `ServiceLoader`.
- Reflection `Class.forName(...)`.
- JSON serialization/deserialization dựa trên annotation/type name.
- Framework DI hoặc plugin discovery.
- JNI/native libraries.
- Resource config hoặc tên class dưới dạng string.

có thể **không xuất hiện như một lời gọi class trực tiếp** trong static analysis.

**Chỉ bật minimize khi đã có test thực thi đúng shaded artifact** trên những nhánh tính năng dùng dynamic loading. Nếu sau minimize app báo `ClassNotFoundException` trong một đường chạy ít dùng, cần xác định class bị loại và điều chỉnh entrypoints/filters hoặc tắt minimize.

Bài demo cố ý đặt **`minimizeJar=false`** để test về manifest/service/resource không bị nhiễu bởi cơ chế pruning.

## 19. Duplicate resources, license và NOTICE

Khi Shade gộp nhiều JAR, có thể gặp các đường dẫn trùng:

~~~text
META-INF/services/...
META-INF/LICENSE
META-INF/NOTICE
reference.conf
application.properties
log4j2.xml
META-INF/spring/...
~~~

**Không nên dập mọi cảnh báo overlap bằng cách loại tất cả duplicate paths**. Tùy resource:

- **Service descriptors** thường cần **merge**, không ghi đè.
- **License/NOTICE** cần bảo toàn thông tin pháp lý phù hợp; Shade có transformers hỗ trợ các tình huống nhất định nhưng không thay trách nhiệm legal review.
- **Framework registry** có thể cần transformer chuyên dụng hoặc cơ chế append.
- **Config file** có thể cần ưu tiên theo chính sách hoặc bị loại khỏi artifact vì không nên là cấu hình chung.
- **Chữ ký cũ** thường không hợp lệ khi gộp, cần xử lý khác license.

Các trường hợp duplicate classes khó hơn: một JAR có hai version khác nhau của cùng class có thể vẫn tạo shaded JAR mà hành vi không ổn định. Giải quyết nguyên nhân qua **dependency graph, exclusions, dependencyManagement và relocation nếu cần**, không chỉ bỏ warning.

Trong Assembly, nếu giữ JAR riêng ở `lib/`, có thể có **hai JAR chứa class giống nhau** dù ZIP trông đầy đủ. Smoke test dựa vào chức năng quan trọng vẫn cần; thêm dependency convergence/duplicate-class analysis bằng công cụ được duyệt nếu dự án có rủi ro.

## 20. `dependency-reduced-pom.xml` và tọa độ phát hành

Shade có thể tạo **dependency-reduced POM** để phản ánh rằng một số dependency đã được nhúng vào shaded JAR. Mặc định của plugin có thể bật tính năng này; trong bài demo nó được **tắt** để giữ main artifact và attached shaded artifact trong một project dễ giải thích.

Điều cần phân biệt:

- **ArtifactId/groupId/version** định danh project và artifact chính.
- **Classifier** phân biệt biến thể, ví dụ `all` cho shaded JAR, `dist` cho ZIP.
- **Thin JAR** có thể được các consumer dùng như thư viện kèm dependency graph Maven.
- **Attached shaded JAR** có thể là một biến thể tự chứa nhiều thư viện, cần kiểm tra metadata dependency phù hợp với cách tiêu thụ.
- **Dependency-reduced POM** nếu được tạo và áp dụng ảnh hưởng cách dependencies xuất hiện khi install/deploy/consume artifact.

**Không khẳng định cứ đặt `createDependencyReducedPom=true` là tự có POM đúng cho mọi chiến lược publish.** Nếu project dùng shaded JAR làm main artifact, reduced POM có thể hợp lý; nếu shade chỉ là classifier đính kèm còn main JAR vẫn thin, phải kiểm tra hệ quả với người dùng classifier, compile/runtime scopes, transitive deps và repository publication.

Trước khi publish, nên thử trong **một project consumer độc lập** hoặc một local Maven repository tách biệt:

1. Cài/triển khai artifact theo chính sách.
2. Khai báo đúng GAV/classifier/type của artifact cần tiêu thụ.
3. Xem effective dependency graph.
4. Chạy consumer thật, không dựa vào classpath của project producer.

**Không tự deploy bài tập demo vào repository tổ chức**. Phần hướng dẫn này chỉ nhằm làm rõ nguyên tắc xác minh metadata khi phát hành.

## 21. Phân biệt lỗi manifest, classpath, SPI và metadata version

| Hiện tượng | Nguyên nhân hay gặp | Kiểm tra đúng |
| --- | --- | --- |
| `no main manifest attribute` | JAR thiếu `Main-Class` hoặc chạy nhầm thin JAR. | `JarFile#getManifest`, tên file/classifier và cấu hình ManifestResourceTransformer. |
| `Could not find or load main class` | Main-Class sai package, thiếu class hoặc classpath sai. | `jar tf`, manifest, `java -jar` hoặc `java -cp` theo từng artifact. |
| `NoClassDefFoundError` cho dependency | Shade thiếu dependency hoặc Assembly thiếu JAR trong lib. | So artifact entries, dependency tree, runtime smoke test. |
| `ServiceConfigurationError` | Sai descriptor, provider không có trong JAR, relocation sai. | Đọc `META-INF/services`, kiểm tra class và chạy ServiceLoader thật. |
| Không tìm được driver/framework plugin | Registry resource bị overwrite/loại hoặc provider bị minimize. | Transformers, minimizeJar, runtime integration test. |
| `Invalid signature file digest` | Signature files của dependency không hợp lệ sau Shade. | Kiểm tra `.SF/.RSA/.DSA`, signing policy và re-sign artifact cuối nếu cần. |
| Phiên bản trong app sai | `build.properties` chưa filter hoặc lấy nhầm JAR cũ. | Đọc metadata trong JAR, so Maven project version và filename. |
| Thin JAR chạy bằng `java -jar` lỗi | Thin JAR không có manifest/dependency; thiết kế chỉ hỗ trợ classpath. | Chạy script/`java -cp lib/*` của Assembly thay vì nhầm artifact. |
| ZIP thiếu thư viện | Assembly dependencySet scope/excludes chưa đúng. | `jar tf` ZIP và Failsafe smoke test trên thư mục giải nén sạch. |
| ZIP có cả thin và fat JAR trong `lib` | FileSet copy rộng, classifier bị chọn nhầm. | Thu hẹp includes, `useProjectAttachments=false`, đọc archive cuối. |
| Script chỉ chạy khi đứng trong thư mục gốc | Đường dẫn tương đối phụ thuộc current directory. | Dùng script directory, test từ working directory khác. |
| Script không chạy trên Linux | File mode/shebang/line endings hoặc extractor không bảo tồn permissions. | Kiểm tra ZIP metadata và chạy script trên runner Linux. |
| `UnsupportedClassVersionError` | Java runtime thấp hơn class major version. | `mvn --version`, `javap -verbose`, chạy trên JVM hỗ trợ. |
| Code chạy trong IDE nhưng crash khi shade | IDE có dependency/test classpath rộng hơn artifact thật. | Chạy child process chỉ với shaded JAR hoặc ZIP lib. |
| CI xanh nhưng file đã publish lỗi | CI chỉ gọi `package`, không chạy IT sau package; publish nhầm classifier. | Bắt buộc `verify`, kiểm tra file được upload có hash đúng. |

**Không sửa lỗi runtime bằng cách chèn thêm `target/classes` hoặc `.m2/repository` vào classpath smoke test**. Cách đó vô tình che chính vấn đề thiếu file trong bộ phân phối.

## 22. Kiểm soát checksum và khả năng tái lập

Một bước phát hành cần xác định **chính xác bytes** được đưa vào repository/download page. Có thể tính SHA-256 cho các file cuối:

**Linux/macOS:**

~~~bash
shasum -a 256 target/shade-assembly-verify-1.0.0-all.jar
shasum -a 256 target/shade-assembly-verify-1.0.0-dist.zip
~~~

**Windows PowerShell:**

~~~powershell
Get-FileHash target\shade-assembly-verify-1.0.0-all.jar -Algorithm SHA256
Get-FileHash target\shade-assembly-verify-1.0.0-dist.zip -Algorithm SHA256
~~~

Hash giúp so sánh **hai bản file cụ thể**, phát hiện upload nhầm hoặc bytes bị sửa trong quá trình phân phối. Không có một SHA-256 “chuẩn” được bịa sẵn cho bài này: hash thực tế phụ thuộc inputs/plugin/metadata/timestamp và phải được tính từ artifact đã build.

### Reproducible builds

Nếu tổ chức yêu cầu builds tái lập, nên:

- Pin dependencies/plugin versions và JDK/OS inputs khi cần.
- Dùng `project.build.outputTimestamp` và hỗ trợ reproducible archive của các plugin tương ứng.
- Tránh đưa timestamp hiện thời, random ID hoặc đường dẫn máy cá nhân vào manifest/resource.
- Kiểm tra thứ tự archive entries, file modes, line endings và metadata bên trong ZIP/TAR.
- Build hai lần trong **môi trường tương đương** rồi so sánh SHA-256.

**Không kết luận reproducible chỉ vì hai lần chạy cùng `mvn verify` đều PASS.** Một JAR có thể chạy đúng nhưng bytes khác vì timestamps; ngược lại hai file có cùng hash không chứng minh chức năng trên mọi runtime tương lai.

## 23. Security, privacy, license và SBOM sau khi gộp

Shading biến nhiều dependency JAR thành **một artifact duy nhất**, nhưng không làm mất trách nhiệm quản lý:

- Lỗ hổng của dependency vẫn có thể tồn tại trong code đã gộp.
- Artifact scanner không phải lúc nào cũng suy ra chính xác GAV từ class đã relocate; cần **SBOM/metadata phù hợp với final artifact**.
- LICENSE và NOTICE không tự biến mất khỏi nghĩa vụ pháp lý chỉ vì class đã đổi package.
- Không được nhúng `.env`, keystore, private key, token hoặc cấu hình mật vào shaded resource hay ZIP fileSet.
- Các thư viện ký số có thể yêu cầu verify **trước** khi gộp; ký mới final artifact là bước khác.
- Generated POM, SBOM và provenance phải phản ánh đúng **biến thể** được publish (thin, shaded hay dist).

Ví dụ blacklist tên file để kiểm tra nhanh là một lớp phòng vệ, **không thay thế secret scan theo nội dung**. Một secret có thể nằm trong `app/build.properties` hoặc trong một resource được đặt tên hoàn toàn vô hại. Review nguồn dữ liệu/CI environment vẫn bắt buộc.

Nếu lỡ publish secret trong artifact, cần **rotate/revoke secret và xử lý bản phát hành đã lộ** theo quy trình sự cố, không chỉ xóa source rồi build lại.

## 24. Assembly và những điều dễ bị bỏ sót ngoài JAR

### 24.1. File mode và line endings

ZIP/TAR có thể lưu metadata quyền nhưng công cụ extract có thể xử lý khác nhau. Một shell script Unix có **CRLF** có thể lỗi ở shebang hoặc tại runtime; một `.cmd` cần cú pháp Windows. Trong repo nhiều OS, thiết lập `.gitattributes`/quy trình build để line endings phù hợp, không phụ thuộc editor của từng developer.

`<fileMode>0755</fileMode>` không làm script chắc chắn có quyền thực thi sau khi mọi công cụ ZIP trên mọi OS giải nén. Kiểm thử **trên OS mục tiêu** là bằng chứng tốt nhất.

### 24.2. Base directory và đường dẫn

`includeBaseDirectory=true` giúp ZIP có một thư mục gốc rõ ràng; bộ cài nên có cấu trúc ổn định. Đừng vô tình làm bản phát hành giải nén trực tiếp vào thư mục hiện tại rồi ghi đè file người dùng.

### 24.3. Thứ tự file/metadata và file dư

Nếu Assembly descriptor copy rộng thư mục `target`, có thể đưa vào **JAR của lần build trước**, báo cáo test, dump/log hoặc file config không cần thiết. **Chạy `mvn clean verify`** và ưu tiên `includes` cụ thể cho những thứ được phép phát hành.

### 24.4. Script runtime

Nếu script phụ thuộc `JAVA_HOME`, `PATH`, thư mục config hoặc biến môi trường, phải mô tả contract rõ. Ví dụ chỉ gọi `java` từ PATH, phù hợp demo nhưng sản phẩm thật nên kiểm tra minimum JDK và thông báo lỗi khi không tìm thấy Java.

### 24.5. TAR và executable bit

Nếu phát hành `.tar.gz`, phải kiểm tra tương tự file modes, symlink và owner metadata. ZIP và TAR không giống nhau hoàn toàn về permission/symlink semantics. Không dùng một file ZIP đã test để khẳng định TAR cũng đúng nếu TAR có packaging rules khác.

## 25. Multi-module: kiểm đúng module, classifier và artifact phụ thuộc

Trong reactor nhiều module, có thể có:

~~~text
parent/
├── api/            thin library
├── engine/         dependency của app
├── cli/            nơi chạy Shade và tạo executable JAR
└── distribution/   nơi tạo Assembly ZIP toàn sản phẩm
~~~

Đây là **sơ đồ kiến trúc**, không phải cấu trúc project runnable ở mục 5. Nếu Shade trong `cli`, Assembly trong `distribution`, thứ tự reactor phải bảo đảm artifact mà Assembly cần đã được build và resolution đúng.

### Những điều cần làm

1. Bảo đảm modules khai báo quan hệ dependencies hợp lệ, để reactor có thứ tự đúng.
2. **Không mặc định parent packaging `pom`** có cùng Shade/Assembly output với module CLI.
3. Pin plugin versions tại parent `pluginManagement`, nhưng bind goals ở đúng modules cần tạo artifact.
4. Đọc `effective-pom` của module bị lỗi để biết executions, profiles, skip flags.
5. Chạy Failsafe IT ở module có artifact cuối, hoặc một module QA chuyên dụng phụ thuộc đúng output.
6. Kiểm tra **classifier** `all`/`dist` khi `install`, `deploy` hoặc consumer yêu cầu.
7. Nếu multi-module tạo shaded dependencies và lại assembly chúng, rà soát duplicate class/version trong ZIP.
8. Sau refactor module names, sửa test artifact identity và scripts; không cho test tiếp tục đọc file cũ do `target` còn tồn tại.

Trong CI, `mvn -T` có thể cho các module độc lập chạy đồng thời, nhưng những plugins ghi vào cùng thư mục hoặc cùng path `dependency-reduced-pom.xml` có thể va chạm nếu thiết kế kém. Dùng output path và module isolation rõ ràng; tránh share `target/` giữa runners.

## 26. CI pipeline: thứ tự kiểm tra trước publish

Một pipeline đề xuất:

~~~text
1. Checkout đúng commit/tag
2. Chọn đúng JDK và Maven Wrapper/version
3. Kiểm tra dependency/security policy
4. mvn -B -ntp clean verify
   - test trên classes
   - package thin, shaded, assembly
   - Failsafe IT trên artifact cuối
5. Kiểm tra ZIP script trên runner OS đích nếu cần
6. License/NOTICE/SBOM/secret scanning trên output thực
7. Tính SHA-256, ghi release metadata
8. Upload đúng shaded JAR + dist ZIP được duyệt
9. Kiểm tra lại checksum file đã upload/download
~~~

**Lệnh CI chính:**

~~~bash
mvn -B -ntp clean verify
~~~

Không chỉ gọi `mvn test`, vì chưa tới packaging; cũng không chỉ gọi `mvn package`, vì đã sinh file nhưng chưa chạy Failsafe IT.

### Bắt lỗi quá trình kiểm thử bị bỏ qua

Một pipeline có thể xanh nếu:

- `-DskipTests` hoặc một profile bỏ IT.
- Test class không khớp quy ước `*IT`/`IT*`.
- Surefire/Failsafe bị tắt hoặc không bind goals.
- Job publish có điều kiện sai, chạy trước bước verify.
- CI nạp artifact từ cache cũ thay vì file vừa tạo.
- Người cấu hình artifact upload chọn `*.jar` và lấy nhầm **thin JAR**.
- Script chỉ test bằng Maven classpath chứ không mở ZIP đã đóng gói.

Đặt **`failIfNoTests=true`** cho Failsafe ở module bắt buộc có IT là hữu ích, nhưng nó không thay việc kiểm tra **số lượng test và danh sách artifacts** kỳ vọng. Theo dõi báo cáo Failsafe và rule publish.

### Đừng dùng cache che lỗi

`mvn clean` dọn output thông thường dưới `target/`, nhưng dependency cache `.m2` vẫn tồn tại. Smoke test shaded JAR và ZIP **không được lấy class runtime từ `.m2`**, mới chứng minh artifact có đủ dependency. CI có thể cache Maven dependencies cho tốc độ, không làm thay đổi nguyên tắc này.

## 27. Quy trình chẩn đoán một lỗi đóng gói

**Tình huống A — IDE chạy được, shaded JAR fail:**

1. Xác nhận chính xác file `-all.jar` đang chạy.
2. Mở manifest, kiểm tra `Main-Class`.
3. `jar tf` để xem class/resource/dependency.
4. Đọc Failsafe report và stderr của child process (đã loại dữ liệu nhạy cảm).
5. Nếu lỗi ServiceLoader, đọc service descriptor và class provider.
6. Nếu lỗi class missing, xem Shade filters, artifactSet/minimize và dependency tree.
7. Nếu chỉ lỗi sau relocation, xem registry/reflection và transformer.
8. Build sạch và chạy `java -jar` lại, không thêm test classpath.

**Tình huống B — shaded JAR chạy, Assembly ZIP fail:**

1. Mở ZIP, xác nhận đường dẫn gốc và `bin/`, `lib/`.
2. Kiểm tra có thin JAR và tất cả runtime JARs.
3. Kiểm tra có chứa nhầm `-all.jar` trong `lib/` gây duplicate classes.
4. Giải nén vào thư mục trống.
5. Chạy `java -cp "lib/*" ...` từ root giải nén để tách lỗi classpath khỏi lỗi script.
6. Chạy `run.sh`/`run.cmd` trên OS phù hợp.
7. Kiểm tra script permission/line endings và biến môi trường.
8. Kiểm tra assembly descriptor `fileSets`/`dependencySets`, `scope`, `unpack`, `outputDirectory`.

**Tình huống C — artifact chạy nhưng metadata sai:**

1. Đọc **metadata trong JAR cuối**, không phải source properties.
2. Xác định token filtering, delimiter và build version.
3. Kiểm tra manifest attributes, resource collision và classifier.
4. Kiểm tra metadata ký số/legal/SBOM của final artifact.
5. So checksum giữa file vừa build và file đã upload.
6. Nếu metadata thay đổi ngoài dự kiến, rà soát timestamps, reproducibility và packaging plugin version.

## 28. Checklist đánh giá hoàn chỉnh sau Shade/Assembly

1. **Định danh đầu ra**: project GAV, phiên bản, classifier `all`/`dist` và file cuối rõ ràng.
2. **Build sạch** với Maven/JDK/plugin versions được pin.
3. **Đọc manifest** của executable JAR, kiểm `Main-Class` và các entry bắt buộc.
4. **Kiểm tra class** chính và dependency quan trọng trong shaded JAR.
5. **Đọc service descriptors** và chạy thực tế `ServiceLoader`.
6. **Kiểm tra filtered metadata** như app/version trong JAR cuối.
7. **Loại invalid signature metadata** nhưng vẫn áp chính sách signing cuối nếu cần.
8. **Kiểm tra duplicate resources/classes** và nguy cơ relocation/minimize.
9. **Chạy `java -jar` shaded JAR** bằng JVM mục tiêu; assert exit code và stdout/hành vi.
10. **Mở Assembly ZIP/TAR** xác nhận structure `bin`, `lib`, `conf`, docs theo hợp đồng.
11. **Chỉ đóng gói đúng runtime JARs**; tránh hai version hoặc vừa thin vừa shaded trong cùng classpath.
12. **Giải nén tới thư mục sạch** và chạy bằng classpath/script từ output đó.
13. **Kiểm tra file modes, shebang, line endings** trên OS được hỗ trợ.
14. **Kiểm soát `dependency-reduced-pom.xml` và classifier** khi install/deploy.
15. **Kiểm tra Java class major** và chạy trên JDK thấp nhất cam kết.
16. **Quét secrets, license, NOTICE, SBOM** theo nội dung artifact cuối.
17. **Tính checksum SHA-256** và so sau upload/download.
18. **Dùng Failsafe ở `verify`**, không publish trước artifact IT.
19. **Kiểm tra test discovery**, số IT đã chạy và các fail/skip.
20. **Giữ log lỗi đủ chẩn đoán** nhưng không lộ token/internal credentials.
21. **Rà multi-module/CI cache** để không dùng output cũ hoặc nhầm file từ module khác.
22. **Kiểm thử đường chạy đặc biệt**: plugin discovery, config loading, reflection, native dependencies nếu sản phẩm dùng.
23. **Lập kế hoạch cập nhật plugin/dependencies** và test lại khi thay version.
24. **Tài liệu hóa contract phân phối**: lệnh chạy, cấu trúc file, JDK tối thiểu và biến môi trường.

## 29. Bài tập thực hành

**Bài 1 — build hai artifact.** Tạo POM và toàn bộ source ở mục 5–12. Chạy `mvn -B -ntp clean verify`. Giải thích tại sao Surefire có **1 unit test**, còn Failsafe có **2 integration test methods**.

**Bài 2 — xem manifest.** Mở `target/shade-assembly-verify-1.0.0-all.jar`, đọc Main-Class, chạy `java -jar` và so stdout chính xác với **PACKAGED OK | Maven | version=1.0.0**.

**Bài 3 — phân biệt thin/shaded.** So sánh entries của `shade-assembly-verify-1.0.0.jar` và `-all.jar`. Tìm `org/apache/commons/lang3/StringUtils.class` và giải thích vì sao thin JAR cần runtime dependency ngoài.

**Bài 4 — ServiceLoader.** Đọc descriptor trong shaded JAR. Trên một bản sao thử nghiệm, loại resource đó khỏi build rồi chạy Failsafe để thấy test phát hiện provider missing. Khôi phục descriptor và giải thích vai trò transformer.

**Bài 5 — ZIP thực sự tự chứa runtime classpath.** Giải nén `-dist.zip` vào thư mục mới; không dùng `.m2` hoặc `target/classes`. Chạy `java -cp "lib/*" ...` từ thư mục gốc đã giải nén. Sau đó thử script tương ứng với OS.

**Bài 6 — thiếu dependency.** Trên bản sao của ZIP thử nghiệm, bỏ `commons-lang3-3.14.0.jar` khỏi `lib` và thử chạy. Phân biệt lỗi thiếu runtime JAR với lỗi `Main-Class`.

**Bài 7 — classifier và metadata.** Giải thích vì sao có ba tên `plain.jar`, `-all.jar`, `-dist.zip`; khi publish phải ghi rõ artifact nào được hỗ trợ cho từng nhóm người dùng.

**Bài 8 — dependency-reduced POM.** Trong môi trường thử nghiệm riêng, thay chính sách `createDependencyReducedPom`, xem POM sinh và kiểm tra một consumer độc lập. Không tự đẩy thử nghiệm lên repository phát hành chung.

**Bài 9 — license/signatures.** Liệt kê signature-related entries trong JAR, thảo luận vì sao ký của dependency không còn xác nhận shaded bytes. Kiểm tra legal notices theo dependency/licenses thực tế.

**Bài 10 — CI release gate.** Thiết kế pipeline chỉ upload sau `mvn clean verify`, kiểm đúng tên file/classifier, secret scan, SBOM và checksum. Nêu cách pipeline vẫn có thể xanh giả nếu Failsafe không có test hoặc script bỏ qua phase verify.

### Tổng kết

**Shade và Assembly thay đổi thứ mà người dùng thật sự chạy hoặc tải.** Kiểm thử trên `target/classes` chỉ chứng minh mã và dependency của **môi trường build**; kiểm thử sau package mới chứng minh artifact có manifest, service descriptors, metadata, dependencies và entrypoint hợp lệ.

Đối với **Shade**, phải kiểm tra **`java -jar`**, `Main-Class`, `ServiceLoader`, signature metadata, relocation và nguy cơ minimize làm mất class động. Đối với **Assembly**, phải kiểm tra **ZIP/TAR thật**, thin JAR và runtime JARs, đường dẫn scripts, file modes và hành vi sau giải nén. **Maven Failsafe ở phase `verify`** là nơi phù hợp để tự động hóa những kiểm chứng này trước publish; checksum, SBOM, license và secret scanning giúp hoàn thiện kiểm soát phát hành.

### Tài liệu chính thức

- [Apache Maven Shade Plugin — Introduction](https://maven.apache.org/plugins/maven-shade-plugin/)
- [Apache Maven Shade Plugin — Executable JAR](https://maven.apache.org/plugins/maven-shade-plugin/examples/executable-jar.html)
- [Apache Maven Shade Plugin — Usage and Resource Transformers](https://maven.apache.org/plugins/maven-shade-plugin/usage.html)
- [Apache Maven Shade Plugin — Selecting Contents for Uber JAR](https://maven.apache.org/plugins/maven-shade-plugin/examples/includes-excludes.html)
- [Apache Maven Shade Plugin — shade:shade Parameters](https://maven.apache.org/plugins/maven-shade-plugin/shade-mojo.html)
- [Apache Maven Assembly Plugin — Predefined Descriptors](https://maven.apache.org/plugins/maven-assembly-plugin/descriptor-refs.html)
- [Apache Maven Assembly Plugin — Descriptor Reference](https://maven.apache.org/plugins/maven-assembly-plugin/assembly.html)
- [Apache Maven Assembly Plugin — assembly:single Parameters](https://maven.apache.org/plugins/maven-assembly-plugin/single-mojo.html)
- [Apache Maven Failsafe Plugin 3.2.5 — Introduction](https://maven.apache.org/surefire-archives/surefire-3.2.5/maven-failsafe-plugin/)
- [Apache Maven Failsafe Plugin 3.2.5 — Usage](https://maven.apache.org/surefire-archives/surefire-3.2.5/maven-failsafe-plugin/usage.html)
- [Oracle Java SE 17 — JarFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html)
- [Oracle Java SE 17 — ZipFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipFile.html)
