# Thư mục `.mvn` và các tệp cấu hình gắn với dự án Maven

## 1. Vì sao dự án Maven có thêm thư mục `.mvn`?

Khi mới học Maven, bạn thường thấy `pom.xml`, `src/main/java`, `src/test/java` và `target/`. Nhưng một dự án làm việc theo nhóm còn cần câu trả lời cho những câu hỏi khác: **dùng phiên bản Maven nào, các lệnh Maven mặc định mang theo tùy chọn gì, JVM chạy Maven cần cấu hình gì, và những người chưa cài Maven sẽ build dự án ra sao?** Nhiều thiết lập đó có thể đi cùng mã nguồn trong thư mục ẩn `.mvn/`.

Cần phân biệt ngay ba loại cấu hình:

- **`pom.xml`**: mô tả dự án Maven và quá trình build: tọa độ artifact, dependency, plugin, profile, module, phiên bản Java dành cho biên dịch.
- **`.mvn/` ở gốc dự án**: chứa một số tùy chọn **để khởi động/chạy Maven cho dự án này**, cấu hình Maven Wrapper, và tùy chọn cơ chế mở rộng Maven. Các tệp ở đây **không bắt buộc phải xuất hiện trong mọi dự án**.
- **`~/.m2/` của người dùng**: thường là nơi có `settings.xml` cá nhân, cache dependency (`repository/`), cache bản Maven mà Wrapper tải về (`wrapper/dists/`). Đây là dữ liệu riêng của máy/người dùng; không phải thư mục `.mvn` nằm trong dự án.

Bài này tập trung vào **cấu trúc dự án và ranh giới trách nhiệm của các tệp**, sử dụng Maven 3.9.x và JDK 17 làm môi trường thực hành. Các ví dụ được viết để người học có thể tự tạo dự án nhỏ, chạy và quan sát.

Mục tiêu sau khi học: giải thích công dụng của `.mvn/maven.config`, `.mvn/jvm.config`, `.mvn/extensions.xml`, `.mvn/wrapper/maven-wrapper.properties`, `mvnw` và `mvnw.cmd`; phân biệt cấu hình dự án với thiết lập người dùng; biết nên commit tệp nào; và chẩn đoán được lỗi cấu hình hay gặp.

## 2. Đọc sơ đồ thư mục trước khi đi vào từng tệp

Một dự án Java đơn có cấu hình kèm theo có thể trông như sau:

~~~text
config-demo/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/
│   ├── maven.config
│   ├── jvm.config
│   └── wrapper/
│       └── maven-wrapper.properties
├── src/
│   ├── main/java/vn/example/configdemo/App.java
│   └── test/java/vn/example/configdemo/AppTest.java
└── target/                          # Sinh ra khi build
~~~

Đó là **một cấu trúc ví dụ**, không phải yêu cầu mọi dự án phải có đầy đủ các tệp. Nếu dự án không cần cấu hình JVM riêng, không cần `jvm.config`. Nếu không dùng core extension, không cần `extensions.xml`. Maven Wrapper đời mới với kiểu `only-script` cũng **không cần** tệp `.mvn/wrapper/maven-wrapper.jar`.

| Tệp hoặc thư mục | Ai sử dụng? | Vai trò chính | Có phải luôn bắt buộc? |
| --- | --- | --- | --- |
| `pom.xml` | Maven | Mô hình và quy tắc build dự án | Có với dự án Maven thông thường |
| `.mvn/maven.config` | Bộ khởi chạy/Maven CLI | Lựa chọn Maven CLI mặc định theo dự án | Không |
| `.mvn/jvm.config` | Script khởi chạy Maven | Tham số JVM chạy **chính Maven** | Không |
| `.mvn/extensions.xml` | Maven Core | Khai báo core extensions tải/nạp lúc khởi động | Không |
| `.mvn/wrapper/maven-wrapper.properties` | Maven Wrapper | Bản phân phối Maven, URL tải về, checksum nếu cấu hình | Có khi dùng Wrapper |
| `mvnw` | Shell trên Linux/macOS, v.v. | Chạy Maven Wrapper trên hệ Unix | Có khi dùng Wrapper |
| `mvnw.cmd` | Windows CMD/PowerShell | Chạy Maven Wrapper trên Windows | Có khi dùng Wrapper |
| `.mvn/wrapper/maven-wrapper.jar` | Một số loại Wrapper | Mã bootstrap Maven Wrapper khi dùng kiểu tương ứng | **Tùy kiểu Wrapper** |
| `target/` | Maven plugins | Nơi chứa kết quả biên dịch, báo cáo test, artifact | Được tạo khi build |
| `~/.m2/settings.xml` | Maven | Thiết lập người dùng: mirror, proxy, server credentials, repository, v.v. | Không; và nằm ngoài dự án |

**Dấu chấm ở đầu `.mvn`** khiến đây là thư mục ẩn theo quy ước Unix. Trong IDE hoặc File Explorer, bạn có thể cần bật hiển thị file ẩn. Các tập tin `mvnw`/`mvnw.cmd` nằm **cùng cấp với `pom.xml`**, không nằm trong `.mvn/`.

## 3. `.mvn/maven.config`: tham số mặc định của lệnh Maven

Đây là nơi định nghĩa các **lựa chọn CLI** nên được dùng nhất quán trong một dự án. Chẳng hạn nhóm muốn log build dễ đọc ở CI mà không buộc mỗi người gõ thêm các cờ vào mọi lệnh.

Ví dụ nội dung file `config-demo/.mvn/maven.config`:

~~~text
-B
--no-transfer-progress
~~~

Khi chạy từ gốc dự án:

~~~bash
mvn clean verify
~~~

Maven nhận những tùy chọn đã cấu hình trong `maven.config` cùng với các tham số gõ ở terminal. `-B` yêu cầu chế độ không tương tác (batch mode); `--no-transfer-progress` giảm thông báo tiến độ tải dependency. Hai tùy chọn này **không tự thay đổi nội dung Java hoặc tạo thêm artifact**.

**Quy tắc cú pháp cần nhớ:** từ **Maven 3.9.0**, **mỗi tham số Maven phải ở một dòng riêng** trong `.mvn/maven.config`. Ví dụ dưới đây là cách viết đúng khi có nhiều tùy chọn:

~~~text
-B
-U
--fail-at-end
~~~

`-U` yêu cầu Maven kiểm tra cập nhật snapshot và một số metadata liên quan; `--fail-at-end` thường có tác dụng đáng chú ý với reactor nhiều module: cố tiếp tục các module có thể build, sau đó báo lỗi. Đừng bật `-U` hoặc `--fail-at-end` theo thói quen nếu dự án chưa thật sự cần. Từ Maven **3.9.3**, dòng bắt đầu bằng `#` có thể là comment trong file này; Maven 3.8.x và cũ hơn **không hỗ trợ comment theo cùng cách**. Để dễ dùng xuyên các bản, ví dụ của bài không đặt comment trong file.

Có thể dùng `-Dten=gia-tri` như một tham số trên một dòng khi muốn truyền property cho Maven, nhưng cần hiểu rằng nó có thể làm thay đổi profile, plugin hoặc test tùy dự án. Đặc biệt, **không** cài sẵn `-DskipTests`, `-o` (offline), `-q` (quiet) hay các tùy chọn có tác động lớn vào `maven.config` mà không thống nhất mục đích và hệ quả.

**Cách kiểm tra:** tạo `.mvn/maven.config` như trên, chạy `mvn -version` và `mvn clean verify` từ gốc dự án. Nếu một lựa chọn gây lỗi, tạm loại đúng dòng đó để cô lập nguyên nhân. Không nhầm với `.mvn/jvm.config`: `-B` và `--no-transfer-progress` là **tùy chọn Maven**, không phải tùy chọn JVM như `-Xmx`.

## 4. `.mvn/jvm.config`: cấu hình JVM đang chạy Maven

Maven bản thân là một chương trình Java. Bộ khởi chạy Maven (như `mvn`/`mvn.cmd` hoặc Maven Wrapper) khởi động một **JVM để chạy Maven** trước khi Maven đọc POM và thực hiện các plugin. `.mvn/jvm.config` dành cho những tham số JVM đó.

Ví dụ file `config-demo/.mvn/jvm.config`:

~~~text
-Xmx1024m -Djava.awt.headless=true
~~~

Giải thích:

- `-Xmx1024m` giới hạn heap tối đa của **JVM chạy Maven** khoảng 1 GiB.
- `-Djava.awt.headless=true` đặt một Java system property cho JVM đó. Đây chỉ là ví dụ về cách truyền property, không phải yêu cầu bắt buộc với mọi dự án.

`jvm.config` nhận các JVM arguments theo cách bộ khởi chạy Maven hỗ trợ; ví dụ một dòng nhiều tham số cách nhau bằng khoảng trắng là cách viết đơn giản cho Maven 3. **Không đặt các cờ như `mvn clean`, `-pl`, `-B` ở đây**: chúng là tham số Maven CLI. Với Maven 3, **đừng thêm dòng comment bắt đầu bằng `#` vào `jvm.config`**; comment được hỗ trợ riêng trong Maven 4, còn Maven 3 có thể hiểu `#` như một argument không hợp lệ khi khởi động JVM.

Cấu hình `jvm.config` thường được bộ khởi chạy dùng bên cạnh biến môi trường `MAVEN_OPTS`. Nếu cần tham số chỉ dành cho máy của bạn, môi trường người dùng vẫn phù hợp hơn việc commit thay đổi làm ảnh hưởng tất cả đồng đội.

**Phân biệt Java biên dịch với JVM chạy Maven.** Hai cấu hình dưới đây giải quyết hai việc khác nhau:

~~~text
.mvn/jvm.config               → -Xmx1024m
pom.xml (compiler settings)  → <maven.compiler.release>17</maven.compiler.release>
~~~

`maven.compiler.release` bảo Maven Compiler Plugin biên dịch mã ứng dụng cho Java 17. Nó **không chọn hoặc cài JDK đang chạy Maven**. `jvm.config` đặt heap cho Maven; nó **không đảm bảo ứng dụng mà bạn chạy sau đó có cùng heap**, và không tự áp dụng cho mọi JVM test/fork do plugin tự khởi chạy. Khi gặp lỗi “release version 17 not supported”, hãy kiểm tra `mvn -version`/`./mvnw -version` và `JAVA_HOME`.

## 5. `.mvn/wrapper/` và hai script `mvnw`, `mvnw.cmd`

### 5.1. Maven Wrapper giải quyết vấn đề gì?

Nếu dự án yêu cầu một bản Maven cụ thể, không nên chỉ dựa vào phiên bản `mvn` đang tình cờ có trên máy. **Maven Wrapper** mang theo các script và file chỉ định bản phân phối Maven; khi cần, nó tải và chạy phiên bản Maven đã được chọn. Điều này giúp máy phát triển và CI dùng cùng phiên bản công cụ.

Cần phân biệt rõ: **Wrapper quản lý phiên bản Maven, không tự cài JDK hay sửa `JAVA_HOME`.** Máy chạy vẫn phải có JDK thích hợp (hoặc CI cài JDK từ bước chuẩn bị riêng).

Các file thường thấy:

~~~text
config-demo/
├── mvnw
├── mvnw.cmd
└── .mvn/
    └── wrapper/
        └── maven-wrapper.properties
~~~

Trong `maven-wrapper.properties`, thuộc tính quan trọng là `distributionUrl`: URL chỉ bản phân phối Maven sẽ dùng. Các cấu hình nâng cao có thể gồm `distributionSha256Sum` để xác minh SHA-256 của Maven đã tải về, và `wrapperSha256Sum` đối với wrapper JAR khi kiểu Wrapper có dùng nó.

### 5.2. Cài Wrapper vào một dự án đã có POM

Nếu máy hiện đã có Maven chạy được, mở terminal **trong thư mục gốc dự án** và chạy:

~~~bash
mvn wrapper:wrapper -Dmaven=3.9.14 -Dtype=only-script
~~~

Lệnh này gọi goal `wrapper` của Maven Wrapper Plugin, thiết lập cấu hình để dùng Maven 3.9.14 trong ví dụ và chọn kiểu `only-script`. Nó cần mạng để tải plugin trong lần đầu nếu chưa có sẵn. Không cần chạy lại lệnh khởi tạo cho mọi lần build; sau đó dùng các script wrapper đã được đưa vào dự án.

Kiểu `only-script` sử dụng script để tải trực tiếp bản Maven và **không cần `maven-wrapper.jar`**. Đây là kiểu mặc định của Maven Wrapper phiên bản hiện đại. Các kiểu khác có thể là:

| Kiểu Wrapper | File bổ sung thường thấy | Cơ chế |
| --- | --- | --- |
| `only-script` | Không cần wrapper JAR | Script tải bản Maven và chạy Maven trực tiếp |
| `bin` | `.mvn/wrapper/maven-wrapper.jar` | Bootstrap bằng wrapper JAR có sẵn trong dự án |
| `script` | Có thể tải `maven-wrapper.jar` khi cần | Script tải wrapper JAR trước |
| `source` | `.mvn/wrapper/MavenWrapperDownloader.java` | Mã nguồn hỗ trợ tải wrapper JAR, tùy môi trường |

Không suy ra “dự án bị thiếu file” chỉ vì không thấy `.mvn/wrapper/maven-wrapper.jar`. Hãy xem **kiểu Wrapper được tạo** và các script thực tế. Tránh tự copy wrapper JAR từ dự án khác mà không hiểu phiên bản và nguồn gốc.

### 5.3. Chạy trên Windows và Linux/macOS

Từ thư mục `config-demo`, trên **Windows PowerShell**:

~~~powershell
.\mvnw.cmd -version
.\mvnw.cmd clean verify
~~~

Trên **Windows CMD**:

~~~bat
mvnw.cmd -version
mvnw.cmd clean verify
~~~

Trên **Linux/macOS**:

~~~bash
./mvnw -version
./mvnw clean verify
~~~

Trên Linux/macOS, nếu script chưa có quyền thực thi, cần cấp quyền cho `mvnw` một lần:

~~~bash
chmod +x mvnw
~~~

Nếu lưu dự án trong Git, nhớ duy trì execute bit của script `mvnw` để người khác không phải sửa thủ công. Khi Wrapper chạy lần đầu, Maven được tải về cache, thường dưới `~/.m2/wrapper/dists/`, rồi được dùng cho build. Các lần sau có thể tái sử dụng bản đã tải.

**Không nhầm** `mvn clean verify` với `./mvnw clean verify`: lệnh đầu dùng bản Maven tìm thấy trên `PATH`, lệnh sau dùng Wrapper của dự án. Nếu đang hướng dẫn đồng đội/CI, ưu tiên lệnh Wrapper khi dự án đã chọn cách này.

### 5.4. Cập nhật Wrapper đúng cách

Khi cần đổi bản Maven, có thể chạy lại goal Wrapper với bản Maven mong muốn hoặc cập nhật `distributionUrl` theo tài liệu Wrapper. Sau khi thay đổi, thử `./mvnw -version`/`.\mvnw.cmd -version`, rồi chạy đủ `clean verify` trong môi trường được hỗ trợ. Cân nhắc thêm checksum công bố từ nguồn phân phối tin cậy; **không tự điền một chuỗi SHA-256 đoán mò**.

Bộ Wrapper giúp thống nhất bản Maven nhưng **không bảo đảm toàn bộ build tái lập** nếu plugin/dependency dùng version linh động, CI khác JDK, hay repository thay đổi nội dung. Vẫn cần kiểm soát POM, JDK, repository và môi trường CI.

## 6. `.mvn/extensions.xml`: core extension, dùng khi thật sự cần

Maven hỗ trợ **core extension** để mở rộng hành vi của Maven ở mức hệ thống build, thay vì chỉ thực hiện một plugin goal ở một phase. File `.mvn/extensions.xml` có thể khai báo danh sách phần tử `<extension>`, trong đó mỗi extension được xác định bằng `<groupId>`, `<artifactId>` và `<version>`; Maven sẽ tìm artifact trong các repository được cấu hình.

**Không cần tạo `extensions.xml` trong dự án Java/Maven thông thường.** Chỉ thêm khi dự án thực sự cần một core extension cụ thể và đã kiểm tra tính tương thích với bản Maven đang dùng.

Cần phân biệt:

- `pom.xml → <build><plugins>`: plugin thực hiện goal (ví dụ compiler, surefire); không đồng nghĩa với core extension.
- `pom.xml → <build><extensions>` hoặc plugin có `<extensions>true</extensions>`: cơ chế build extension được Maven hỗ trợ, nhưng không giống cách nạp **core extension** sớm từ `.mvn/extensions.xml`.
- `.mvn/extensions.xml`: nạp core extension cho dự án, có thể ảnh hưởng cách Maven khởi động hoặc xử lý build, nên phải chọn dependency và phiên bản một cách có chủ đích.

Không đưa một tọa độ extension không tồn tại vào ví dụ chỉ để lấp file. Một dự án không cần extension sẽ **không có file này** và Maven vẫn hoạt động bình thường.

## 7. Thực hành: dựng một dự án dùng `.mvn` và Wrapper

Ví dụ sau tạo một dự án Java 17 nhỏ, sau đó thêm các file gắn với dự án. Bạn có thể tự tạo file thủ công bằng IDE/text editor. Chạy các lệnh từ thư mục chứa `pom.xml`.

### Bước 1 — Tạo `pom.xml`

Tạo file `config-demo/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>config-demo</artifactId>
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
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Không thêm thông số heap vào `pom.xml` chỉ vì cần JVM chạy Maven; nó thuộc `jvm.config` hoặc môi trường khởi động. `maven.compiler.release=17` xác định mức Java của mã sản phẩm.

### Bước 2 — Tạo mã Java có thể chạy

File `config-demo/src/main/java/vn/example/configdemo/App.java`:

~~~java
package vn.example.configdemo;

public final class App {
    private App() {
    }

    public static String message() {
        return "Maven project config OK";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

File `config-demo/src/test/java/vn/example/configdemo/AppTest.java`:

~~~java
package vn.example.configdemo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void returnsExpectedMessage() {
        assertEquals("Maven project config OK", App.message());
    }
}
~~~

Test JUnit sẽ chạy qua Surefire ở phase `test`. Nếu bạn đổi chuỗi trong `App.message()` mà không sửa kỳ vọng, test sẽ thất bại: đó là bằng chứng test thật sự được kích hoạt, không phải một kiểm tra hình thức.

### Bước 3 — Tạo hai file cấu hình trong `.mvn`

File `config-demo/.mvn/maven.config`:

~~~text
-B
--no-transfer-progress
~~~

File `config-demo/.mvn/jvm.config`:

~~~text
-Xmx1024m -Djava.awt.headless=true
~~~

Đây là hai file **text thuần UTF-8**; không đặt đoạn `~~~text` hoặc tên file vào nội dung. Một file định nghĩa **Maven CLI options**; file còn lại định nghĩa **JVM options khi chạy Maven**. Không cần tạo `.mvn/extensions.xml` vì ví dụ không dùng core extension.

### Bước 4 — Sinh Wrapper và build

Bạn cần `mvn` đã được cài để chạy **lần khởi tạo** Wrapper:

~~~bash
mvn wrapper:wrapper -Dmaven=3.9.14 -Dtype=only-script
~~~

Kiểm tra các file mới: `mvnw`, `mvnw.cmd` và `.mvn/wrapper/maven-wrapper.properties`. Đọc `distributionUrl` trong properties để biết bản Maven mà dự án đã chọn.

Sau đó, **trên Linux/macOS**:

~~~bash
./mvnw -version
./mvnw clean verify
java -cp target/config-demo-1.0.0.jar vn.example.configdemo.App
~~~

Hoặc **trên Windows PowerShell**:

~~~powershell
.\mvnw.cmd -version
.\mvnw.cmd clean verify
java -cp target\config-demo-1.0.0.jar vn.example.configdemo.App
~~~

Nếu build thành công, Maven tạo `target/config-demo-1.0.0.jar`. Chạy lệnh `java -cp` phía trên sẽ in **chính xác**:

~~~text
Maven project config OK
~~~

Tại sao dùng `java -cp` mà không dùng `java -jar`? Vì POM này chưa cấu hình `Main-Class` trong manifest; JAR mặc định không nhất thiết chạy được bằng `java -jar`. Ở đây ứng dụng không có dependency runtime ngoài JDK nên một JAR đặt trên classpath là đủ.

Một lần `clean verify` thành công với test ở trên thường hiển thị nội dung tương ứng “Tests run: 1, Failures: 0, Errors: 0, Skipped: 0”. Số giây, thứ tự và chi tiết log Maven có thể khác; hãy kiểm tra test report trong `target/surefire-reports/` và sự tồn tại của JAR thay vì phụ thuộc vào nguyên văn toàn bộ log.

### Bước 5 — Chứng minh vai trò của mỗi file

Làm từng thí nghiệm **một thay đổi tại một thời điểm**:

1. Mở `.mvn/maven.config`, tạm xóa riêng dòng `--no-transfer-progress`, sau đó chạy lại một lệnh Maven có tải artifact. Log tải có thể khác; khôi phục dòng ngay sau quan sát. Nếu artifact đã được cache, sự khác biệt có thể không rõ ràng.
2. Mở `.mvn/jvm.config`, đổi `-Xmx1024m` thành `-Xmx768m`, chạy lại `./mvnw -version` và `./mvnw test`. Ứng dụng vẫn dùng `maven.compiler.release=17`; bạn vừa chỉnh heap JVM chạy Maven, **không phải Java release**. Khôi phục `-Xmx1024m` nếu muốn giữ cấu hình mẫu.
3. Kiểm tra `.mvn/wrapper/maven-wrapper.properties` để xác nhận `distributionUrl`. So sánh `mvn -version` với `./mvnw -version`; nếu bản Maven cài sẵn khác bản Wrapper thì kết quả sẽ cho thấy sự khác biệt.
4. Xóa **chỉ thư mục `target/` sau khi đã lưu mã nguồn**, rồi chạy `./mvnw clean verify` để chứng minh `target/` là đầu ra có thể tạo lại; không xóa `.mvn/` hay script Wrapper để “dọn build”.
5. Tạm đổi một câu khẳng định trong `AppTest.java` cho sai, chạy `./mvnw test` rồi xem `target/surefire-reports/`. Khôi phục test và build lại để bảo đảm trạng thái cuối PASS.

**Các thay đổi trong thí nghiệm phải được khôi phục** trước khi commit dự án dùng chung.

## 8. Trường hợp dự án nhiều mô-đun

Trong dự án lớn, hãy giữ một cấu hình `.mvn/` và bộ Wrapper **ở gốc reactor** để dễ thống nhất cách build toàn bộ module:

~~~text
shop/
├── pom.xml                   # packaging pom, có <modules>
├── .mvn/
│   ├── maven.config
│   ├── jvm.config
│   └── wrapper/
│       └── maven-wrapper.properties
├── mvnw
├── mvnw.cmd
├── core/pom.xml
└── app/pom.xml
~~~

Chạy từ gốc:

~~~bash
./mvnw clean verify
./mvnw -pl :app -am test
~~~

Lệnh thứ nhất xây dựng reactor theo cấu hình cha/con; lệnh thứ hai chọn `app` cùng những module trong reactor mà `app` cần để build. Cấu hình trong `.mvn` phục vụ **cách chạy Maven cho toàn bộ dự án**, nhưng **không tự khai báo quan hệ phụ thuộc giữa module**. Quan hệ đó vẫn nằm trong các POM dưới dạng `<modules>`, `<parent>` và `<dependencies>`.

Khi làm việc trong thư mục con hoặc gọi trực tiếp một executable Maven khác, cách xác định thư mục gốc và nạp cấu hình có thể chịu ảnh hưởng cách khởi chạy. Để tránh mơ hồ cho bài thực hành/CI, hãy **chạy Wrapper từ gốc reactor** và đọc bản Maven thực tế bằng `./mvnw -version`.

## 9. So sánh `.mvn`, `.m2`, `settings.xml` và các cấu hình liên quan

| Vị trí | Thường thuộc về ai? | Dùng để làm gì? | Khuyến nghị |
| --- | --- | --- | --- |
| `<project>/.mvn/` | Dự án/nhóm | Quy ước CLI, JVM config, core extensions, Wrapper | Commit cấu hình an toàn cần thiết cho nhóm |
| `<project>/pom.xml` | Dự án/nhóm | Tọa độ, dependency, plugin, version, module, profiles | Luôn version-control |
| `<project>/mvnw` và `mvnw.cmd` | Dự án/nhóm | Điểm vào Maven Wrapper đa hệ điều hành | Commit nếu dùng Wrapper |
| `<user-home>/.m2/settings.xml` | Người dùng/môi trường CI | Mirror, proxy, server credentials, active profiles | Không đưa mật khẩu/token vào Git |
| `<user-home>/.m2/repository/` | Cache cục bộ | Artifact, POM, plugin đã tải | Không commit vào repo dự án |
| `<user-home>/.m2/wrapper/dists/` | Cache cục bộ | Các bản Maven do Wrapper tải | Không commit |
| `<user-home>/.m2/toolchains.xml` | Môi trường cá nhân/CI | Cấu hình JDK/toolchain cho plugin có hỗ trợ | Thường đặt theo từng máy/CI |
| `<project>/target/` | Đầu ra build | Class, test report, JAR | Thường ignore trong Git |

**Lưu ý phiên bản:** Maven **4** còn có hỗ trợ cấu hình `.mvn/settings.xml` ở cấp dự án; không được mặc định áp dụng hành vi này cho **Maven 3.9.x** trong bài. Với Maven 3, thiết lập môi trường người dùng phổ biến là `~/.m2/settings.xml`; có thể dùng `-s <đường-dẫn>` để chỉ rõ settings file nếu cần, nhưng những thông tin nhạy cảm vẫn không nên đưa vào repo.

Maven Wrapper **không thay thế** `settings.xml`: Wrapper chọn và chạy **bản Maven**, còn `settings.xml` cấu hình nơi tải artifact, proxy, máy chủ và quyền truy cập. `.mvn/maven.config` **không thay thế** POM: nó thêm tùy chọn CLI, còn POM mô tả mô hình build. `.mvn/jvm.config` **không thay thế** Maven Toolchains: một bên cấu hình JVM đang chạy Maven, bên kia có thể giúp plugin chọn JDK khác theo cấu hình toolchain.

## 10. Quy ước Git, CI và bảo mật cấu hình

Một bộ Wrapper đáng tin nên được đưa vào version control dưới dạng các file mà đúng kiểu Wrapper yêu cầu. Với `only-script`, tối thiểu thường gồm:

~~~text
pom.xml
mvnw
mvnw.cmd
.mvn/wrapper/maven-wrapper.properties
.mvn/maven.config          # nếu nhóm dùng
.mvn/jvm.config            # nếu nhóm dùng
~~~

Đừng mặc định xóa `maven-wrapper.jar` nếu dự án thật sự dùng kiểu `bin`; nó là một phần của bootstrap trong trường hợp đó. Ngược lại, đừng thêm một JAR tải từ nguồn không rõ ràng chỉ vì xem thấy trên blog hướng dẫn cũ.

Một đoạn `.gitignore` thường hữu ích:

~~~gitignore
target/
*.log
~~~

Quy tắc này tránh commit đầu ra Maven và file log, nhưng **không ignore `.mvn/` hoặc toàn bộ file `*.jar` một cách thiếu cân nhắc**: kiểu `bin` có thể cần theo dõi wrapper JAR. Với Linux/macOS, script `mvnw` cần giữ quyền thực thi trong Git.

Ở CI, quy trình tối thiểu thường là: checkout mã nguồn, cài JDK hỗ trợ, dùng Wrapper của dự án để build, chạy test và giữ kết quả/report. Ví dụ lệnh (trên runner Unix):

~~~bash
java -version
./mvnw -version
./mvnw clean verify
~~~

Không commit credentials vào `.mvn/maven.config`, `.mvn/jvm.config`, `maven-wrapper.properties`, `pom.xml` hoặc URL tải Maven. Dùng secrets của CI, cấu hình người dùng/runner và kho nội bộ được tổ chức quản lý. Khi dùng Wrapper, ưu tiên HTTPS, nguồn phân phối tin cậy và checksum SHA-256 hợp lệ cho bản phân phối nếu có thể.

Với team nhiều môi trường, điều nên thống nhất là: bản JDK tối thiểu, bản Maven qua Wrapper, plugin/dependency version ở POM, quy tắc tests, và cách cung cấp settings/secrets cho CI. Chỉ có Wrapper vẫn chưa bảo đảm mọi máy tạo ra artifact giống hệt nhau nếu các đầu vào khác thay đổi.

## 11. Lỗi thường gặp và cách xác định nguyên nhân

| Triệu chứng | Cần kiểm tra và xử lý |
| --- | --- |
| Không thấy `.mvn` trong IDE/Explorer | Bật hiển thị file/thư mục ẩn; kiểm tra đang mở đúng gốc dự án |
| Chạy `mvnw` hoặc `mvnw.cmd` nhưng “file not found” | Script đặt ở gốc dự án; đứng đúng thư mục, dùng `./mvnw` (Unix) hoặc `.\mvnw.cmd` (PowerShell) |
| `Permission denied` với `./mvnw` | Thiếu execute bit; kiểm tra permission và `chmod +x mvnw` trên môi trường Unix |
| Không thấy `maven-wrapper.jar` | Có thể đang dùng `only-script`; kiểm tra các file do Wrapper Plugin tạo và kiểu phân phối |
| Wrapper không tải được Maven | Kiểm tra mạng, proxy, URL trong `maven-wrapper.properties`, repository nội bộ và checksum nếu đã cấu hình |
| `mvn -version` khác `./mvnw -version` | Hai lệnh dùng hai cách chọn Maven; Wrapper ưu tiên bản đã khai báo trong dự án |
| Maven báo lỗi option khi nạp `maven.config` | Maven 3.9 yêu cầu một argument trên mỗi dòng; đừng gộp `-B -U` cùng một dòng |
| Maven 3 báo `Could not find or load main class #` | Có thể có dòng comment `#` trong `.mvn/jvm.config`; xóa comment kiểu này |
| `Unrecognized VM option` hoặc JVM không khởi động | Sai tham số trong `jvm.config` hoặc JDK không hỗ trợ tham số đó |
| `release version 17 not supported` | Maven đang chạy bằng JDK quá cũ; kiểm tra `mvn -version`/`./mvnw -version` và `JAVA_HOME` |
| `NoClassDefFoundError` khi chạy artifact | Runtime classpath/JAR thiếu dependency; Wrapper và `jvm.config` không tự tạo fat JAR |
| Đã thêm `.mvn/extensions.xml` rồi build lỗi ngay khi khởi động | Kiểm tra tọa độ, phiên bản và khả năng tương thích core extension; gỡ extension thử nghiệm khi không cần |
| CI chạy tốt trên máy A nhưng không trên máy B | So sánh JDK, Wrapper version, `settings.xml`/mirror, profile, biến môi trường, plugin và dependency versions |
| File `target` vẫn có JAR sau lệnh `compile` | Có thể JAR từ build cũ; dùng `./mvnw clean compile` để so sánh trên trạng thái sạch |

Mẹo phân tích: lỗi xảy ra **trước khi Maven chạy một plugin** thường liên quan khởi động JVM, file `.mvn`, Wrapper hoặc tải extension; lỗi trong phase `compile`/`test` có thể là POM/plugin/mã nguồn. Xác định bước đầu tiên thất bại giúp bạn sửa đúng lớp nguyên nhân.

## 12. Bài tập cuối bài và tiêu chí tự kiểm tra

**Bài tập A — Phân loại file:** Trong cấu trúc `config-demo`, chỉ ra file nào nằm trong project root, file nào nằm trong `.mvn`, file nào ở `~/.m2` và file nào do build tạo ra. Giải thích vì sao không thể thay thế `pom.xml` bằng `maven.config`.

**Bài tập B — Cấu hình CLI:** Tạo `.mvn/maven.config` có `-B` và `--no-transfer-progress` trên hai dòng. Chạy `./mvnw clean verify`. Giải thích Maven 3.9 xử lý mỗi dòng thế nào và vì sao không để `-DskipTests` làm mặc định khi học build.

**Bài tập C — Cấu hình JVM:** Tạo `.mvn/jvm.config` như mẫu, đọc giá trị `maven.compiler.release` trong POM. Nêu rõ cái nào tác động lên heap JVM đang chạy Maven, cái nào tác động lên cấp Java khi biên dịch.

**Bài tập D — Wrapper:** Từ một checkout sạch có đủ `mvnw`, `mvnw.cmd` và `maven-wrapper.properties`, chạy `./mvnw -version`/`.\mvnw.cmd -version` để xác nhận bản Maven. Giải thích bản Maven được chọn nằm ở đâu, và vì sao Wrapper vẫn cần JDK.

**Bài tập E — Kiểm chứng build:** Chạy `clean verify`, xem một test PASS và chạy JAR với `java -cp`. Tạm sửa test để thấy `BUILD FAILURE`, sau đó khôi phục test và build lại thành công.

Bạn hoàn thành bài khi có thể **đọc một cây thư mục Maven và biết đúng trách nhiệm của từng tệp**, tự cấu hình `maven.config`/`jvm.config`, sử dụng Wrapper đa hệ điều hành, phân biệt `.mvn` với `.m2` và xử lý được một lỗi khởi động Maven phổ biến.

## 13. Tài liệu chính thức để tra cứu

- [Apache Maven — Configuring Maven](https://maven.apache.org/configure): giải thích `.mvn/maven.config`, `.mvn/jvm.config`, `.mvn/extensions.xml`, `MAVEN_OPTS` và `settings.xml`.
- [Apache Maven Wrapper](https://maven.apache.org/tools/wrapper/): cách tạo Wrapper, các kiểu `only-script`/`bin`/`script`/`source`, và cách dùng `mvnw`.
- [Apache Maven Wrapper Plugin](https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/wrapper-mojo.html): tham số `-Dmaven`, `-Dtype` và cách xác minh distribution.
- [Using Extensions](https://maven.apache.org/guides/mini/guide-using-extensions.html): phân biệt core extension và build extension.
- [Maven 3.9.0 Release Notes](https://maven.apache.org/docs/3.9.0/release-notes.html): thay đổi cách đọc từng argument trong `.mvn/maven.config`.
