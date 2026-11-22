# Phạm vi cấu hình theo dự án trong .mvn/maven.config và .mvn/jvm.config

## 1. Tại sao Maven có hai tệp cấu hình trong thư mục .mvn?

Trong một nhóm phát triển, mỗi người có thể chạy Maven theo cách khác nhau: một người dùng `mvn -B clean verify`, người khác quên `-B`; CI cần giới hạn heap để tránh dùng quá nhiều RAM; một máy phải bật một thuộc tính build trong khi máy khác không bật. Nếu các thiết lập đó là **chính sách dùng chung của một repository**, Maven cho phép đặt chúng trong thư mục `.mvn/` ở cấp gốc dự án:

- **`.mvn/maven.config`**: chứa các **đối số của Maven CLI** (những tham số thường gõ sau `mvn`), ví dụ `-B`, `-Ddemo.mode=ci`, `-Pprofile-name`, `-T1`.
- **`.mvn/jvm.config`**: chứa **đối số khởi động JVM chạy Maven** (các tham số thường đặt trong `MAVEN_OPTS`), ví dụ `-Xmx512m`, `-Djava.awt.headless=true`, `-XX:+UseG1GC` khi tương thích JDK.

Cả hai tệp nằm cạnh hoặc phía dưới `pom.xml` ở vùng cấu hình dự án:

```text
project-root/
├── .mvn/
│   ├── maven.config
│   └── jvm.config
├── pom.xml
└── src/
    └── ...
```

Maven hỗ trợ cấu hình theo dự án bằng các tệp này từ Maven **3.3.1**. Chúng có thể được commit vào Git để thành viên và CI dùng cùng mặc định, thay vì ai cũng phải nhớ gõ một chuỗi lệnh dài. Tuy nhiên, **không phải mọi thiết lập Maven đều thuộc hai tệp**: dependency và plugin thuộc POM; mirror/credentials thường thuộc `settings.xml`; bí mật không nên đưa vào Git.

Điều cốt lõi của bài học là hiểu **phạm vi tác động**: “tham số của chương trình Maven” khác “tham số của JVM dùng để chạy Maven”, và cả hai đều khác “cấu hình JVM của ứng dụng sau khi build”.

## 2. So sánh hai tệp theo nơi nhận cấu hình

| Tiêu chí | `.mvn/maven.config` | `.mvn/jvm.config` |
| --- | --- | --- |
| Đích nhận | Trình phân tích tham số lệnh Maven | JVM khởi chạy chính Maven |
| Dạng giá trị | Tùy chọn Maven CLI, nhất là `-B`, `-P...`, `-D...`, `-T...` | Tùy chọn Java launcher, như `-Xms...`, `-Xmx...`, `-D...`, `--add-opens=...` khi cần |
| Thời điểm tác động | Khi Maven phân tích lệnh và điều phối build | Khi tiến trình Java chạy Maven được tạo |
| Ví dụ phù hợp | `-B`, `--fail-at-end`, `-Ddemo.channel=staging` | `-Xmx768m`, `-Djava.awt.headless=true` |
| Ví dụ đặt sai chỗ | `-Xmx768m` không phải tùy chọn Maven CLI | `-B` không phải tùy chọn JVM |
| Có làm thay đổi `pom.xml` trên đĩa? | Không | Không |
| Có thể tác động đến plugin? | Có, khi plugin đọc tùy chọn/user property tương ứng | Có, khi plugin/Maven đọc JVM system property hoặc bị giới hạn tài nguyên |
| Tự áp dụng cho ứng dụng Java chạy sau build? | Không | Không |
| Mức chia sẻ thường thấy | Theo repository/project root | Theo repository/project root |

**Hai loại `-D` trông giống nhau nhưng không đồng nhất.** `-Ddemo.flag=value` trong `maven.config` là đối số Maven để đặt **user property của Maven**. Cùng chuỗi trong `jvm.config` được Java launcher xử lý thành **JVM system property** của tiến trình Maven. Một số cơ chế của Maven/plugin có thể truy cập cả hai loại qua biểu thức cấu hình; điều đó không biến user property thành system property và không khiến mọi tiến trình Java con kế thừa tự động. Maven 3.9 cũng đã thay đổi/cải thiện cách tách user properties và system properties, nên tránh dựa vào giả định chúng luôn hoán đổi cho nhau.

## 3. .mvn/maven.config: các tùy chọn chung khi gọi Maven

### 3.1. Một ví dụ dùng được với Maven 3.9+

Giả sử dự án muốn chạy ở chế độ batch, bật một thuộc tính ứng dụng lúc build và kiểm soát màu log. Nội dung `.mvn/maven.config`:

```text
-B
-Ddemo.label=from-maven-config
-Dstyle.color=never
```

Với tệp này, khi đứng tại dự án và gọi:

```bash
mvn clean verify
```

Maven nhận thêm các tùy chọn tương đương về mặt ý nghĩa với:

```bash
mvn -B -Ddemo.label=from-maven-config -Dstyle.color=never clean verify
```

Đây là cách giải thích về các đối số bổ sung, **không phải mô tả toàn bộ thứ tự ưu tiên nội bộ** của mọi phiên bản Maven. Khi truyền cùng một thuộc tính thêm lần nữa trên lệnh trực tiếp, ví dụ `-Ddemo.label=from-terminal`, Maven hiện đại cho phép tùy chọn người gọi ghi đè mặc định project-level đó. Nên kiểm chứng phiên bản Maven thực tế khi thiết kế chính sách override có ảnh hưởng lớn tới CI.

- `-B`/`--batch-mode`: chế độ phù hợp CI và log không tương tác.
- `-Ddemo.label=...`: user property có thể được POM, plugin hoặc resource filtering sử dụng nếu có cấu hình tương ứng.
- `-Dstyle.color=never`: ví dụ giảm mã màu trong console theo cách Maven hỗ trợ; khác với tùy chọn heap của JVM.

**Không phải mọi thuộc tính `-D...` đều có tác dụng mặc định.** Nếu POM/plugin không đọc `demo.label`, thêm property này chỉ tạo ra một giá trị cấu hình; không làm chương trình Java đổi hành vi một cách tự động.

### 3.2. Chú ý cú pháp giữa các phiên bản Maven

Bắt đầu từ **Maven 3.9.0**, mỗi dòng `.mvn/maven.config` được hiểu là **một đối số duy nhất**. Vì vậy phải viết:

```text
-B
-U
--fail-at-end
```

Không nên viết mọi tham số trên một dòng theo thói quen cũ:

```text
-B -U --fail-at-end
```

Ở Maven 3.9+, dòng này có thể bị coi là một đối số dài không hợp lệ, thay vì ba tham số riêng. Đây là thay đổi không tương thích với một số cấu hình Maven 3.8.x trở về trước. Khi nhóm có nhiều phiên bản Maven, cần thống nhất phiên bản Maven/Wrapper rồi chọn định dạng phù hợp, kiểm chứng trên CI sạch.

**Dòng comment cũng có khác biệt phiên bản**:

- Maven **3.9.3 trở lên** hỗ trợ dòng bắt đầu bằng `#` trong `maven.config` như chú thích.
- Maven **3.8.x trở về trước** không hỗ trợ dạng comment đó.
- Với phiên bản Maven cũ hoặc khi cần tương thích rộng, tránh comment trong file này cho đến khi đã xác minh phiên bản được hỗ trợ.

Tệp `maven.config` thường nên chứa **các tùy chọn chung**, tránh nhét mặc định `clean package`, `deploy` hoặc các goal gây tác động ngoài ý muốn vào mọi lượt chạy. Các goal và phase có thể để người gọi chọn theo ngữ cảnh.

### 3.3. Những lựa chọn cần cân nhắc trước khi commit

| Tùy chọn | Có thể hữu ích khi | Rủi ro nếu luôn bật |
| --- | --- | --- |
| `-B` | CI và nhóm muốn log ổn định | Một số thao tác tương tác không còn phù hợp |
| `-T1C` | Build nhiều module và plugin hỗ trợ chạy song song | Plugin không thread-safe, thứ tự log, tranh chấp tài nguyên |
| `-U` | Cần kiểm tra cập nhật snapshot/metadata theo chính sách | Tăng kết nối mạng, khó tái lập nếu snapshot thay đổi |
| `-o` | Môi trường offline đã chuẩn bị đủ cache | Lỗi khi plugin/dependency/metadata chưa có trong local repository |
| `-DskipTests` | Một bước trung gian có lý do rõ ràng | Che lấp chất lượng nếu mặc định bỏ test cho toàn dự án |
| `-Pprofile-id` | Có profile phù hợp được nhóm chấp thuận | Build thay đổi âm thầm nếu profile làm khác dependency hoặc plugin |

Không nên xem việc được đưa vào `maven.config` là sự bảo đảm mọi tham số đều an toàn. Ví dụ một project có test quan trọng không nên commit `-DskipTests` làm mặc định chỉ để build nhanh; nó khiến cả nhóm tưởng đã chạy test trong khi thực tế bỏ qua.

## 4. .mvn/jvm.config: cấu hình JVM đang chạy Maven

### 4.1. Mục đích và ví dụ

Maven được chạy bên trong một JVM. Heap, chế độ headless, module access và một số system property của chính tiến trình đó phải được đặt **trước khi JVM khởi động**. Nội dung `.mvn/jvm.config` có thể là:

```text
-Xms128m
-Xmx512m
-Ddemo.jvm.marker=from-jvm-config
```

Ý nghĩa:

- `-Xms128m`: đặt heap khởi tạo được yêu cầu cho JVM chạy Maven.
- `-Xmx512m`: đặt giới hạn heap tối đa được yêu cầu cho JVM chạy Maven; không có nghĩa tổng bộ nhớ tiến trình hoặc toàn bộ máy bị giới hạn ở 512 MB.
- `-Ddemo.jvm.marker=...`: tạo một **Java system property** trong tiến trình chạy Maven để phục vụ minh họa và cho thành phần thực sự đọc thuộc tính này.

Các giá trị bộ nhớ chỉ là ví dụ; cần điều chỉnh theo kích thước Reactor, đặc tính plugin và RAM của môi trường. Không nên tự động tăng heap để chữa mọi lỗi build: lỗi biên dịch, lỗi dependency, memory leak và lỗi fork test là các nguyên nhân khác nhau.

Trong Maven 3, **không đặt dòng bắt đầu bằng `#` vào `jvm.config`**: launcher Maven 3 không hỗ trợ cú pháp comment này và có thể báo lỗi khởi chạy Java. Tài liệu Maven 4 có hỗ trợ dòng comment, nhưng nếu dự án cần chạy cả Maven 3 thì nên giữ tệp chỉ chứa các JVM options hợp lệ, không có chú thích. Cú pháp tách tham số cho `jvm.config` là đầu vào của launcher JVM; **không áp dụng máy móc quy tắc mỗi dòng một Maven CLI argument** từ `maven.config`. Với tùy chọn không có dấu cách, mỗi dòng một tùy chọn vẫn dễ đọc và an toàn.

### 4.2. Tác động tới đâu, không tác động tới đâu?

Nếu `mvn` được khởi chạy bằng script Maven tiêu chuẩn và tìm được project root, `.mvn/jvm.config` tham gia cấu hình **JVM đang thực thi Maven**. Điều này có thể ảnh hưởng quá trình phân giải POM, plugin và các goal chạy trong tiến trình Maven.

Nhưng cần phân biệt ba JVM trong một chuỗi công việc Java:

1. **JVM chạy Maven:** do `mvn` hoặc Maven Wrapper khởi chạy; đọc `jvm.config` qua cơ chế launcher tương ứng.
2. **JVM được plugin fork:** ví dụ quá trình test độc lập do Maven Surefire tạo, hoặc Java được một plugin tự khởi chạy. Tham số heap của JVM Maven **không tự động truyền sang mọi JVM fork**. Với Surefire, cấu hình riêng như `argLine` và chính sách fork mới là nơi kiểm soát các JVM test tương ứng.
3. **JVM chạy ứng dụng sau build:** ví dụ người dùng gọi `java -cp target/classes ...`, IDE chạy ứng dụng, hoặc container chạy JAR. Chúng có tham số Java riêng; file `.mvn/jvm.config` **không tự cấp `-Xmx` hoặc `-D` cho JVM này**.

Tương tự, `-Dmaven.compiler.release=17` (hay cấu hình compiler trong POM) không tự cài hoặc chọn JDK mới. JDK Maven chạy dùng liên quan `JAVA_HOME`, launcher, và Maven Toolchains nếu dự án cấu hình; version Java mà code được biên dịch nhắm tới là vấn đề khác với dung lượng heap chạy Maven.

### 4.3. So sánh với MAVEN_OPTS

`MAVEN_OPTS` là biến môi trường mang JVM options cho Maven ở phạm vi **người dùng, shell hoặc agent CI**. `.mvn/jvm.config` lưu cùng loại thông tin ở phạm vi **dự án**, để chia sẻ qua version control.

Ví dụ môi trường có:

```bash
export MAVEN_OPTS="-Xmx1g"
mvn --version
```

Phần `export` dùng cho shell POSIX, không chạy nguyên văn trong PowerShell/Command Prompt. Trên Windows PowerShell có thể đặt `$env:MAVEN_OPTS = "-Xmx1g"` rồi gọi Maven.

Tài liệu cấu hình Apache Maven lưu ý **thứ tự ưu tiên khi cùng một tùy chọn JVM được khai báo cả hai nơi có thể khác theo major version**: Maven 3 thường lấy giá trị từ `MAVEN_OPTS`, còn Maven 4 ưu tiên `.mvn/jvm.config` theo mô tả của tài liệu hiện hành. Để tránh khó dự đoán trên nhiều hệ điều hành và phiên bản, **đừng khai báo xung đột cùng một tham số heap ở cả hai nơi**. Chọn một nguồn chính sách và kiểm chứng trên đúng launcher/version của dự án.

Các lựa chọn như `MAVEN_ARGS` (hỗ trợ từ Maven 3.9) lại mang **đối số Maven CLI**, không phải JVM options. Đừng nhầm `MAVEN_ARGS` với `MAVEN_OPTS`.

## 5. Ví dụ hoàn chỉnh Java 17: phân biệt thuộc tính Maven và JVM trong một dự án

Ví dụ này dùng một dự án Java 17 nhỏ. Khi Maven build, Maven Resources Plugin sao chép và **filter** file resource, lấy một user property từ `maven.config` và một system property từ `jvm.config`. Sau đó, ta chạy ứng dụng bằng một JVM mới để thấy JVM của ứng dụng **không tự thừa hưởng** system property của tiến trình Maven.

Điều kiện: JDK 17+, Maven tương thích (khuyến nghị dùng cùng phiên bản Maven 3.9.3+ khi thực hành cú pháp mẫu), có khả năng tải plugin lần đầu từ repository được cho phép.

### 5.1. Cây thư mục

```text
config-scope-demo/
├── .mvn/
│   ├── maven.config
│   └── jvm.config
├── pom.xml
└── src/
    └── main/
        ├── java/demo/config/ConfigApp.java
        └── resources/build.properties
```

Tạo `.mvn/maven.config`:

```text
-B
-Ddemo.label=from-maven-config
```

Tạo `.mvn/jvm.config`:

```text
-Xms128m
-Xmx512m
-Ddemo.jvm.marker=from-jvm-config
```

Hai file dùng các tùy chọn không có khoảng trắng trong giá trị, nhằm tránh vấn đề quoting/splitting giữa các launcher và shell. Không đưa comments vào file để tập trung vào sự khác biệt loại tham số.

### 5.2. POM hoàn chỉnh

Tệp `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>config-scope-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>true</filtering>
                <includes>
                    <include>build.properties</include>
                </includes>
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
        </plugins>
    </build>
</project>
```

Trong POM này, Resource Plugin sẽ dùng các property khả dụng khi filter `build.properties`. Cần chú ý `<filtering>true</filtering>` chỉ bật cho file văn bản minh họa. Không bật filtering tràn lan cho file nhị phân hoặc file phải giữ nguyên byte; không đưa secret production vào file resource được đóng gói.

### 5.3. Resource được filter trong quá trình build

Tệp `src/main/resources/build.properties` có nội dung nguồn:

```properties
demo.label=${demo.label}
demo.jvm.marker=${demo.jvm.marker}
```

Hai biểu thức `${...}` không phải biến Java runtime. Chúng là **placeholder của Maven Resources Plugin trong bước xử lý resources**, dự kiến được thay bằng giá trị cấu hình ở thời điểm build. Trong ví dụ:

- `${demo.label}` được giải quyết từ user property `-Ddemo.label=from-maven-config` do `maven.config` đưa vào lệnh Maven.
- `${demo.jvm.marker}` được giải quyết từ system property `-Ddemo.jvm.marker=from-jvm-config` mà `jvm.config` đưa vào JVM Maven.

Sau khi build, file `target/classes/build.properties` dự kiến chứa:

```properties
demo.label=from-maven-config
demo.jvm.marker=from-jvm-config
```

Đây là **kết quả resource đã được Maven xử lý**, không phải nội dung nguyên gốc mà ứng dụng tự truy vấn trực tiếp từ `.mvn`.

### 5.4. Mã Java 17 đọc file đã được xử lý

Tệp `src/main/java/demo/config/ConfigApp.java`:

```java
package demo.config;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class ConfigApp {
    private ConfigApp() {
    }

    public static void main(String[] args) throws IOException {
        Properties properties = new Properties();

        try (InputStream input =
                     ConfigApp.class.getResourceAsStream("/build.properties")) {
            if (input == null) {
                throw new IllegalStateException("Missing build.properties");
            }
            properties.load(input);
        }

        System.out.println("Build label: "
                + properties.getProperty("demo.label"));
        System.out.println("Build JVM marker: "
                + properties.getProperty("demo.jvm.marker"));
        System.out.println("App JVM marker: "
                + System.getProperty("demo.jvm.marker", "(unset)"));
    }
}
```

Mã dùng `Properties` của Java 17, đọc resource từ classpath. Nó chỉ cần Java chuẩn khi chạy và không yêu cầu ứng dụng phụ thuộc Maven API.

### 5.5. Chạy và đối chiếu kết quả

Từ thư mục `config-scope-demo/`:

```bash
mvn clean compile
java -cp target/classes demo.config.ConfigApp
```

Nếu các tệp đúng như ví dụ, hệ thống không có cấu hình ghi đè và build thành công, **stdout của lệnh `java` thứ hai** là:

```text
Build label: from-maven-config
Build JVM marker: from-jvm-config
App JVM marker: (unset)
```

Diễn giải:

1. `maven.config` đặt một **Maven user property** được dùng để filter resource.
2. `jvm.config` đặt một **system property trên JVM Maven** cũng có thể được dùng bởi quá trình filter.
3. Sau khi Maven đã kết thúc, lệnh `java -cp ...` khởi tạo **một JVM khác**: system property `demo.jvm.marker` không được tự truyền qua, nên `System.getProperty` trả giá trị dự phòng `(unset)`. Ứng dụng vẫn đọc giá trị đã được filter và lưu **bên trong resource đầu ra**.

Để xem tác dụng ghi đè ở **mức Maven CLI**:

```bash
mvn clean compile -Ddemo.label=from-terminal
java -cp target/classes demo.config.ConfigApp
```

Ở các bản Maven hiện đại theo chính sách override thông thường, dòng `Build label` đổi thành `from-terminal`; những dòng khác giữ nguyên nếu môi trường không thay đổi. Đây là phép thử trực tiếp tốt hơn việc chỉ đoán thứ tự ưu tiên của các nguồn cấu hình.

Nếu muốn đặt system property đó cho **chính JVM ứng dụng**, phải gọi riêng:

```bash
java -Ddemo.jvm.marker=from-app -cp target/classes demo.config.ConfigApp
```

Khi đó dòng cuối là `App JVM marker: from-app`; hai giá trị từ resource đã filter không tự thay đổi chỉ vì truyền `-D` khi chạy Java.

Với Maven Wrapper, các lệnh `mvn ...` được thay bằng `./mvnw ...` trên Linux/macOS hoặc `.\mvnw.cmd ...` trên Windows PowerShell khi dự án đã có Wrapper hợp lệ. Maven Wrapper chọn bản phân phối Maven; hai file `.mvn/maven.config` và `.mvn/jvm.config` tiếp tục phục vụ các vai trò cấu hình của project theo cơ chế launcher hỗ trợ.

## 6. Phạm vi trong dự án nhiều module và khi đổi nơi chạy lệnh

Giả sử cây dự án:

```text
multi-project/
├── .mvn/
│   ├── maven.config
│   └── jvm.config
├── pom.xml
├── core/pom.xml
└── app/pom.xml
```

Khi thực thi một Reactor build từ root, các tùy chọn ở `multi-project/.mvn/` là cấu hình **cho lần chạy Maven đó**, nên có thể ảnh hưởng cả `core` và `app`. Đây không phải quan hệ `<parent>` của POM: không cần cả hai module có `<parent>` trỏ về root để CLI options của một lần chạy Reactor ảnh hưởng tới chúng.

Đừng hiểu theo cách “mỗi module tự kế thừa một `maven.config` như kế thừa POM”. File này được phát hiện theo **project root/session và launcher** của lần chạy Maven; việc đứng trong một thư mục con hay dùng `-f` từ vị trí khác có thể làm thay đổi ngữ cảnh phát hiện theo phiên bản/cách khởi chạy. Khi cần chắc chắn, hãy chạy từ root với cùng Maven Wrapper và kiểm chứng thực tế. Đừng đặt `.mvn/` riêng trong mỗi module rồi giả định Maven sẽ tự tổng hợp mọi cấu hình theo cây.

Nếu mục tiêu là chỉ module `app` dùng Java release 21 hoặc thêm compiler flags, đó thường là **cấu hình POM của module hoặc plugin/compiler/toolchain**, không phải một JVM option toàn cục của build root. Nếu mục tiêu chỉ là bật profile cho một job CI, có thể truyền tham số CLI ở job thay vì commit mặc định áp dụng cho mọi thành viên.

## 7. Phân biệt với các nguồn cấu hình khác

| Nguồn | Phạm vi/chức năng | Không nên nhầm với |
| --- | --- | --- |
| `pom.xml` | Mô hình dự án: dependency, plugin, version, resources, build phases | Tùy chọn heap để khởi động Maven JVM |
| `.mvn/maven.config` | Đối số CLI Maven được dự án chia sẻ | Tham số khởi động Java launcher |
| `.mvn/jvm.config` | Tham số JVM chạy Maven | Runtime options của chương trình sau khi build |
| `settings.xml` | Cấu hình Maven theo người dùng/cài đặt: mirror, server credentials, proxy, repositories/profile theo khả năng | POM được commit chung hoặc file chứa logic ứng dụng |
| `MAVEN_OPTS` | JVM options ở môi trường shell/CI | `MAVEN_ARGS` |
| `MAVEN_ARGS` | Đối số Maven CLI qua biến môi trường (từ Maven 3.9) | `MAVEN_OPTS` |
| `JAVA_HOME` | Chỉ định JDK mà launcher Maven có thể sử dụng | Thuộc tính target Java release của Compiler Plugin |
| `.mvn/wrapper/*` | Thành phần Maven Wrapper: phân phối Maven được chọn và script khởi chạy | Các file `maven.config`/`jvm.config` |
| Surefire `argLine` | JVM arguments dành cho test process fork theo cấu hình Surefire | JVM chính đang chạy Maven |

Một điểm dễ nhầm: `-Ddemo.label=value` trong `maven.config` có thể được dùng trong `pom.xml` thông qua `${demo.label}` nhưng không tự ghi một `<property>` mới vào POM nguồn. Tương tự, JVM system property ở `jvm.config` là thuộc tính của tiến trình Maven; nó **không trở thành biến môi trường** và không được bảo đảm xuất hiện như một property của chương trình triển khai.

`settings.xml` rất quan trọng cho proxy, mirror và credential; các file `.mvn` **không phải chỗ hợp lệ để commit mật khẩu hoặc token**. Vì Git thường được chia sẻ và log Maven có thể in một số giá trị cấu hình, hãy giữ thông tin bí mật trong cơ chế bảo mật của môi trường CI hoặc cấu hình người dùng được quản lý đúng.

## 8. Các lỗi phổ biến và cách chẩn đoán

### 8.1. “Maven báo Unrecognized option khi thêm -Xmx”

`-Xmx512m` là **JVM argument**, còn `-X` là một **tùy chọn CLI của Maven để bật log debug**. Đưa `-Xmx512m` vào `maven.config` dễ khiến Maven không nhận tham số. Chuyển cấu hình heap vào `jvm.config` hoặc `MAVEN_OPTS`; dùng `-X` của Maven chỉ khi cần debug.

### 8.2. “Một dòng có nhiều tham số chạy trên Maven cũ nhưng lỗi Maven 3.9”

Maven 3.9 yêu cầu mỗi **Maven argument** trong `maven.config` nằm riêng một dòng. Thay `-B -U` bằng hai dòng `-B` và `-U`; sau đó kiểm tra Maven version bằng `mvn --version`. Đừng kết luận lỗi do POM hoặc JDK nếu cú pháp file cấu hình đã sai.

### 8.3. “Thêm comment vào jvm.config rồi Maven không khởi động”

Với Maven 3, `jvm.config` không hỗ trợ dòng comment kiểu `# ...`. Hãy bỏ dòng đó; đặt hướng dẫn ở README hoặc quy trình nhóm. Maven 4 có thay đổi tương ứng, nhưng muốn hỗ trợ cả Maven 3 thì tránh comment để giữ tính tương thích.

### 8.4. “Đã tăng heap Maven nhưng test fork vẫn OutOfMemoryError”

`jvm.config` ảnh hưởng JVM Maven, không tự động tăng heap của JVM do Surefire fork để chạy test. Kiểm tra cấu hình Surefire/Failsafe, cách fork và `argLine`, cũng như tài nguyên thật của CI. Đừng tăng `-Xmx` quá cao khi container không đủ RAM tổng.

### 8.5. “-D được khai báo nhưng Java app không thấy”

`-D` trong `maven.config` là Maven user property. Nó không tự trở thành system property của JVM app được gọi bằng `java` sau khi build. Nếu cần truyền giá trị sang ứng dụng, chọn cơ chế rõ ràng: resource filtering có kiểm soát, file cấu hình runtime, biến môi trường runtime hoặc `java -D...` khi khởi chạy. Không lưu secrets qua resource filtering chỉ vì có sẵn phương tiện thay biến.

### 8.6. “Máy cá nhân khác CI dù đã commit hai file”

Kiểm tra có thực sự chạy Maven trong đúng project root và dùng cùng Maven/Wrapper không; có tùy chọn cùng tên được truyền trên CLI, `MAVEN_OPTS` hoặc `MAVEN_ARGS` không; có file bị bỏ qua bởi Git không; có các profile hoặc settings khác nhau không. Đọc lệnh gọi Maven thực tế trên CI thay vì dựa hoàn toàn vào README.

### 8.7. “Maven dùng đúng heap mà vẫn báo lỗi UnsupportedClassVersionError”

Đây là vấn đề phiên bản class/JDK hoặc plugin, không phải thiếu heap. Xem `mvn --version` để biết Java runtime Maven đang dùng, kiểm tra `maven.compiler.release`, cấu hình Toolchains và runtime Java đích. Tệp `jvm.config` không thể tự tải hoặc cài JDK phù hợp.

### 8.8. “Thêm -o vào maven.config khiến đồng nghiệp không tải được dependency”

`-o` bật chế độ offline của Maven. Nếu đặt làm mặc định của repository, mọi người có thể gặp lỗi khi plugin/artifact chưa nằm trong local repository. Chỉ dùng như chính sách có chủ đích cho môi trường đã chuẩn bị đủ cache; với nhu cầu chỉ một job, nên dùng tham số CLI trong job đó.

## 9. Quy trình áp dụng cho nhóm và CI

1. **Xác định phiên bản Maven chuẩn**: dùng Maven Wrapper khi phù hợp, ghi nhận Maven 3.9+ và đặc biệt quy tắc mỗi dòng trong `maven.config`.
2. **Tách đúng loại tham số**: tùy chọn sau `mvn` → `maven.config`; tùy chọn khởi động JVM Maven → `jvm.config`; cấu hình build/plugin/dependency → POM.
3. **Chọn mặc định chung an toàn**: `-B` hoặc user property có giá trị rõ ràng là ví dụ; tránh commit `skipTests`, `offline`, `deploy` như hành vi bắt buộc không được review.
4. **Giữ bí mật ngoài repository**: credentials/mirror trong nguồn cấu hình được quản lý phù hợp; không commit token vào `-D` hoặc resource filter.
5. **Kiểm tra sự khác biệt Maven 3/4**: comment trong `jvm.config`, thứ tự ưu tiên `MAVEN_OPTS` và `jvm.config`, cách xử lý từng argument trong `maven.config`.
6. **Chạy build sạch trên máy và CI**: `mvn clean verify`; xem Maven/JDK version, POM hiệu lực, kết quả test và tài nguyên sử dụng.
7. **Kiểm chứng đúng phạm vi**: nếu định giới hạn JVM Maven, đừng chỉ nhìn Java app; nếu định điều khiển plugin bằng user property, kiểm tra plugin thật sự đọc property; nếu chỉ một module cần thay đổi, ưu tiên thiết kế POM/module riêng.

Khi quản lý chính sách của một dự án, các file `.mvn` nên là **mặc định có thể đọc hiểu, có review, có kiểm chứng**. Mục tiêu không phải di chuyển mọi tùy chọn từ script vào file, mà là làm rõ cái gì thuộc **Maven CLI**, cái gì thuộc **JVM chạy Maven**, và cái gì thuộc **mô hình POM hoặc ứng dụng**.

## 10. Ghi nhớ và tài liệu tham khảo

- `.mvn/maven.config` cung cấp **Maven CLI arguments** dùng chung cho project. Từ Maven 3.9, viết mỗi argument trên một dòng.
- `.mvn/jvm.config` cung cấp **JVM arguments cho tiến trình Maven**, không tự truyền tới Java app hoặc mọi test fork.
- `-D` ở hai file có điểm bắt đầu khác nhau (Maven user property và Java system property), dù cả hai có thể ảnh hưởng quá trình xử lý POM/plugin/resource.
- Hai file không thay POM, `settings.xml`, Maven Wrapper hay cấu hình bảo mật; cũng không phải cơ chế inheritance theo mỗi module.
- Dùng một ví dụ chạy thật để kiểm tra cả giá trị filter ở thời điểm build và hành vi JVM riêng ở thời điểm runtime.

Nguồn chính thức:

- [Apache Maven — Configuring Apache Maven](https://maven.apache.org/configure.html)
- [Apache Maven — Maven 3.9.0 release notes và thay đổi cú pháp maven.config](https://maven.apache.org/docs/3.9.0/release-notes.html)
- [Apache Maven — Maven 3.9.3 release notes](https://maven.apache.org/docs/3.9.3/release-notes.html)
- [Apache Maven — Maven 4 configuring (JVM, launcher, properties)](https://maven.apache.org/ref/4-LATEST/configuring.html)
- [Apache Maven — Maven Resources Plugin: Filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html)
- [Apache Maven — Maven Surefire Plugin: Fork Options](https://maven.apache.org/surefire/maven-surefire-plugin/examples/fork-options-and-parallel-execution.html)
