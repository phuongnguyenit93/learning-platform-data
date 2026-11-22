# Maven Profile: kích hoạt theo JDK, hệ điều hành, thuộc tính hoặc tệp

## 1. Bài toán và mục tiêu

Một dự án Java có thể được build trên laptop Windows, máy Linux của CI, JDK 17 hoặc JDK 21; mỗi môi trường có thể cần thêm một cấu hình build khác nhau. **Maven build profile** cho phép thay đổi một phần mô hình build dựa trên những điều kiện được khai báo, thay vì giữ nhiều bản `pom.xml` và chỉnh tay trước mỗi lần chạy.

Các tình huống thường gặp:

- Khi Maven chạy bằng JDK 17 trở lên, bật một cấu hình Java mới.
- Khi chạy trên Windows, chọn cấu hình công cụ tương thích.
- Khi người dùng truyền `-Ddemo.mode=dev`, bật thiết lập dành cho dev.
- Khi một file marker tồn tại (hoặc bị thiếu), bật tác vụ tương ứng.
- Khi đồng thời thỏa điều kiện JDK, property và file, bật một cấu hình thử nghiệm.

Sau bài học, bạn sẽ biết viết đúng bốn loại `<activation>`, hiểu khi nào profile được bật, kiểm tra kết quả bằng Maven Help Plugin, xử lý các trường hợp phủ định/kết hợp điều kiện, và tránh để build khác nhau ngoài ý muốn giữa các máy.

**Điều quan trọng nhất:** profile activation được Maven đánh giá **trong quá trình dựng model trước khi chạy lifecycle**. Nó không phải một lệnh `if` được chạy lại sau mỗi goal. Bật profile cũng **không đồng nghĩa** đã kiểm tra xong hoặc bảo đảm môi trường đáp ứng tất cả điều kiện để build thành công.

## 2. Vị trí profile và các cách kích hoạt

Một profile đặt trong `pom.xml` có dạng:

~~~xml
<profiles>
    <profile>
        <id>dev-mode</id>
        <activation>
            <property>
                <name>demo.mode</name>
                <value>dev</value>
            </property>
        </activation>
        <properties>
            <example.mode>development</example.mode>
        </properties>
    </profile>
</profiles>
~~~

Đây là **đoạn XML bên trong thẻ `<project>`**, không phải POM độc lập. Khi Maven nhận system/user property `demo.mode=dev`, profile `dev-mode` tự active và property `example.mode` được ghép vào effective POM.

Profile có thể được định nghĩa ở:

| Nơi định nghĩa | Đặc điểm | Lưu ý |
| --- | --- | --- |
| `pom.xml` của dự án | Chứa build logic có thể version control | Phù hợp nhất với các thay đổi dự kiến chung cho nhóm |
| `~/.m2/settings.xml` | Cấu hình theo người dùng | Thường thích hợp cho properties, repositories; không thể thay toàn bộ phần build plugin như POM profile |
| `$MAVEN_HOME/conf/settings.xml` | Cấu hình toàn cục theo bản cài Maven | Có thể khác nhau giữa developer và CI |

Có hai nhóm cách bật:

1. **Explicit activation**: chỉ định `-Pdev-mode` trên CLI hoặc thêm `<activeProfile>` trong settings.
2. **Implicit activation**: Maven tự kiểm tra điều kiện `jdk`, `os`, `property`, `file` trong `<activation>`; ngoài ra có `activeByDefault` với quy tắc đặc biệt.

**Profile không được kế thừa nguyên khối** từ parent POM xuống child. Maven xử lý những profile được kích hoạt trong ngữ cảnh POM chứa chúng, rồi kế thừa **tác động đã áp dụng** theo quy tắc model. Hai profile trùng ID trong parent và child không tự biến thành cùng một profile. Muốn debug phải chọn đúng module.

## 3. Cách Maven đánh giá activation

~~~text
mvn / ./mvnw
      |
      +--> JDK đang chạy Maven (java.version)
      +--> OS JVM nhìn thấy (os.name, os.arch, os.version)
      +--> User/system properties (-D..., env.CI)
      +--> File system (file có/không có)
      +--> POM / parent / settings
      |
      v
Maven dựng project model
      |
      +--> xét các <profile><activation>...</activation>
      +--> ghép tác động profile active
      |
      v
Effective POM
      |
      v
Thực hiện lifecycle / plugin goals
~~~

Mọi điều kiện implicit **khác loại** trong một profile được kết hợp theo **AND** trên các phiên bản Maven hiện đại (từ Maven 3.2.2). Nếu bạn đặt `<jdk>`, `<property>` và `<file>` cùng lúc, **cả ba đều phải đúng** để profile tự active.

Không dùng hai thẻ `<property>` hoặc hai thẻ `<jdk>` cùng cấp trong một `<activation>` để mô phỏng OR; trùng cùng loại không được hỗ trợ như danh sách điều kiện. Nếu yêu cầu “JDK đạt **hoặc** file tồn tại”, hãy thiết kế nhiều profile/tác động thích hợp thay vì đoán Maven sẽ dùng OR.

**Cũng không có kích hoạt lại giữa build:** một file được sinh tại phase `generate-sources` sẽ không làm `<file><exists>` tự được đánh giá lại trong lượt Maven đang chạy. Muốn kích hoạt dựa trên file, file cần ở đúng trạng thái **khi Maven khởi tạo model**.

## 4. Kích hoạt theo JDK: `<jdk>`

### 4.1. Prefix matching

Ví dụ:

~~~xml
<profile>
    <id>jdk17-prefix</id>
    <activation>
        <jdk>17</jdk>
    </activation>
    <properties>
        <example.jdk17>on</example.jdk17>
    </properties>
</profile>
~~~

`<jdk>17</jdk>` so khớp **tiền tố chuỗi phiên bản JDK** chạy Maven. JDK `17.0.12` khớp; JDK `21.0.5` không khớp. **Nó không có nghĩa JDK >=17**.

### 4.2. Version range

Khi muốn JDK 17 trở lên:

~~~xml
<profile>
    <id>jdk17-or-newer</id>
    <activation>
        <jdk>[17,)</jdk>
    </activation>
    <properties>
        <example.jdk>on</example.jdk>
    </properties>
</profile>
~~~

Bảng ví dụ:

| Giá trị `<jdk>` | Cách hiểu |
| --- | --- |
| `17` | Version JDK có prefix `17` |
| `[17,)` | JDK từ 17 trở lên, bao gồm 17 |
| `[17,21)` | JDK từ 17 đến trước 21 |
| `[21,)` | JDK 21 trở lên |
| `!17` | Phủ định prefix `17` |

` [17,) ` ở bảng là khoảng từ 17 không giới hạn trên; trong XML phải viết **không chèn khoảng trắng vào biểu thức**. Cú pháp `[` hoặc `]` bao gồm đầu mút, `(` hoặc `)` loại trừ đầu mút. Khi kiểm tra các bản JDK có qualifier/patch phức tạp, hãy xác nhận bằng Maven chạy trên JDK thật thay vì suy từ nhãn ngắn.

`<jdk>!17</jdk>` **không có nghĩa JDK cũ hơn 17**; cả JDK 11 và 21 đều không bắt đầu bằng `17`.

### 4.3. JDK nào được Maven dùng?

Maven profile activation dựa trên **JVM đang khởi chạy Maven**, không phải mức Java đích của Compiler Plugin và không tự đổi sang JDK được Maven Toolchains chọn để compile.

Kiểm tra:

~~~bash
java -version
mvn -version
~~~

Hoặc dùng Maven Wrapper:

~~~bash
./mvnw -version
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd -version
~~~

`mvn -version` thường hiển thị Java version và Java home đang chạy Maven. `JAVA_HOME` và `PATH` có thể khác; hãy đọc kết quả của **lệnh Maven**. Ví dụ một module có `<maven.compiler.release>21</maven.compiler.release>` không làm profile `<jdk>[21,)</jdk>` active khi Maven đang chạy bằng JDK 17. Nếu JDK là điều kiện **bắt buộc**, nên kết hợp Maven Enforcer Plugin hoặc Toolchains thay vì chỉ bật/tắt profile.

## 5. Kích hoạt theo hệ điều hành: `<os>`

### 5.1. OS family

Ví dụ bật trên Windows:

~~~xml
<profile>
    <id>windows</id>
    <activation>
        <os>
            <family>windows</family>
        </os>
    </activation>
    <properties>
        <example.os>on</example.os>
    </properties>
</profile>
~~~

Ví dụ family kiểu UNIX:

~~~xml
<profile>
    <id>unix-family</id>
    <activation>
        <os>
            <family>unix</family>
        </os>
    </activation>
    <properties>
        <example.unix>on</example.unix>
    </properties>
</profile>
~~~

Maven sử dụng những giá trị OS mà **JVM chạy Maven** nhìn thấy. Một người dùng Windows nhưng chạy Maven **bên trong WSL, container Linux hoặc remote Linux** có thể không thỏa `family=windows`.

### 5.2. Tên, family, kiến trúc và phiên bản

`<os>` có các thuộc tính:

| Thẻ | Dùng để so sánh | Ví dụ |
| --- | --- | --- |
| `<name>` | `os.name` | `Windows 10`, `Linux` |
| `<family>` | Nhóm OS được Maven suy ra | `windows`, `unix` |
| `<arch>` | `os.arch` | `amd64`, `aarch64` |
| `<version>` | `os.version` | `10.0` hoặc giá trị của OS/JVM |

Ví dụ Windows/amd64:

~~~xml
<activation>
    <os>
        <family>windows</family>
        <arch>amd64</arch>
    </os>
</activation>
~~~

Nếu khai báo nhiều thành phần bên trong `<os>`, **tất cả thành phần đã khai báo phải đúng**. So khớp chuỗi thông thường là **không phân biệt hoa thường**. Có thể dùng `!` để phủ định một giá trị, ví dụ `<family>!windows</family>`.

Đừng đoán `amd64` và `x86_64` luôn tương đương: chúng là các chuỗi JVM có thể báo khác nhau. Đừng dựa vào tên OS trong giao diện desktop để suy ra `os.version` của Java.

### 5.3. Regex cho OS version

Từ **Maven 3.9.7**, giá trị `<os><version>` hỗ trợ tiền tố `regex:` để so khớp Java regex với chuỗi `os.version` đã chuyển chữ thường. Ví dụ minh họa:

~~~xml
<activation>
    <os>
        <family>windows</family>
        <version>regex:`10[.].*</version>
    </os>
</activation>
~~~

Đoạn này chỉ khớp nếu JVM báo OS Windows với chuỗi version bắt đầu `10.`; **không phải tất cả Windows mới đều được bảo đảm khớp**. `regex:` được hỗ trợ ở trường **version**, không nên tự giả định áp dụng được với `family`, `arch` hay `name`. Khi dùng phiên bản Maven cũ hơn, tránh dựa vào tính năng này.

### 5.4. Kiểm tra giá trị OS thực tế

Chạy:

~~~bash
mvn -version
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
~~~

Nếu cần quan sát system properties của Java, tạo `OsProbe.java`:

~~~java
public class OsProbe {
    public static void main(String[] args) {
        System.out.println("name=" + System.getProperty("os.name"));
        System.out.println("arch=" + System.getProperty("os.arch"));
        System.out.println("version=" + System.getProperty("os.version"));
    }
}
~~~

Lệnh chạy trên JDK 17+:

~~~bash
javac OsProbe.java
java OsProbe
~~~

Không có stdout cố định cho probe vì mỗi máy có OS/JVM khác nhau. Hãy dùng `help:active-profiles` làm bằng chứng profile thực sự active.

## 6. Kích hoạt theo thuộc tính: `<property>`

Property activation thường xét **system property** hoặc **CLI user property** (được truyền bằng `-D`), và các biến môi trường mà Maven cung cấp dưới dạng `env.NAME`. Đừng cho rằng một property do chính `<properties>` của POM đang dựng khai báo chắc chắn có thể được dùng để tự kích hoạt profile đó: activation được thực hiện rất sớm trong model building.

### 6.1. Chỉ kiểm tra sự tồn tại

~~~xml
<profile>
    <id>debug-present</id>
    <activation>
        <property>
            <name>debug</name>
        </property>
    </activation>
    <properties>
        <example.debug>on</example.debug>
    </properties>
</profile>
~~~

Profile này tự active khi có property `debug`, chẳng hạn:

~~~bash
mvn help:active-profiles -Ddebug
mvn help:active-profiles -Ddebug=true
mvn help:active-profiles -Ddebug=false
~~~

Với ví dụ **chỉ xét sự hiện diện**, cả ba lệnh đều có `debug`, dù giá trị logic khác nhau.

### 6.2. So khớp giá trị chính xác

~~~xml
<profile>
    <id>dev-mode</id>
    <activation>
        <property>
            <name>demo.mode</name>
            <value>dev</value>
        </property>
    </activation>
    <properties>
        <example.mode>on</example.mode>
    </properties>
</profile>
~~~

Khi gọi `mvn help:active-profiles -Ddemo.mode=dev`, profile tự active. Nếu `-Ddemo.mode=prod` hoặc không khai báo property thì điều kiện này không đúng. **Giá trị so khớp phân biệt chữ hoa/thường**: `dev` khác `DEV`.

### 6.3. Phủ định tên và phủ định giá trị

Maven cho phép:

~~~xml
<!-- Active khi thuộc tính debug hoàn toàn không được định nghĩa -->
<activation>
    <property>
        <name>!debug</name>
    </property>
</activation>
~~~

Hoặc:

~~~xml
<!-- Active khi debug vắng mặt HOẶC khác true -->
<activation>
    <property>
        <name>debug</name>
        <value>!true</value>
    </property>
</activation>
~~~

Hai cách khác nhau: `!debug` kiểm tra **không có tên property**; `value=!true` kiểm tra **không bằng true**, và còn có thể khớp khi property vắng mặt theo quy tắc Maven. Nếu muốn bật chỉ khi người dùng bật cờ, dùng `<name>debug</name><value>true</value>`; `-Ddebug` không kèm giá trị được Maven xem là cờ true ở trường hợp này.

### 6.4. Dùng biến môi trường

Maven đưa biến môi trường vào không gian property `env.`. Ví dụ chỉ bật khi `CI=true`:

~~~xml
<profile>
    <id>ci-environment</id>
    <activation>
        <property>
            <name>env.CI</name>
            <value>true</value>
        </property>
    </activation>
    <properties>
        <example.ci>on</example.ci>
    </properties>
</profile>
~~~

Linux/macOS:

~~~bash
CI=true mvn help:active-profiles
~~~

Windows PowerShell:

~~~powershell
$env:CI = 'true'
mvn help:active-profiles
~~~

Trên Windows, tên biến môi trường được Maven chuẩn hóa sang chữ hoa, nên `env.CI` thường an toàn hơn `env.ci`. Không phải CI nào cũng tự đặt `CI=true`, hãy xem môi trường thật. **Không hiển thị biến bí mật** vào `effective-pom`, log công khai hoặc README chỉ để chứng minh profile hoạt động.

### 6.5. Trường hợp đặc biệt: packaging

Từ Maven **3.9.0**, activation có thể kiểm tra property đặc biệt `packaging` của POM, ví dụ:

~~~xml
<activation>
    <property>
        <name>packaging</name>
        <value>war</value>
    </property>
</activation>
~~~

Điều này hữu ích trong parent POM dùng chung cho dự án WAR và JAR. Đây không phải một cơ chế tự biến `<packaging>` của dự án thành WAR bằng `-Dpackaging=war`; mục đích là xét packaging hiện có.

## 7. Kích hoạt theo file: `<file>`

`<file>` có hai điều kiện phổ biến:

| Cấu hình | Tự active khi |
| --- | --- |
| `<exists>path</exists>` | Đường dẫn tồn tại khi Maven xét activation |
| `<missing>path</missing>` | Đường dẫn không tồn tại khi Maven xét activation |

### 7.1. Khi file tồn tại

~~~xml
<profile>
    <id>marker-present</id>
    <activation>
        <file>
            <exists>config/enable.marker</exists>
        </file>
    </activation>
    <properties>
        <example.file>on</example.file>
    </properties>
</profile>
~~~

File `config/enable.marker` phải có **trước khi gọi Maven** nếu muốn profile tự active. Đường dẫn tương đối được giải quyết trong ngữ cảnh POM/project phù hợp; với multi-module, phải kiểm tra đúng module và đường dẫn thực.

### 7.2. Khi file thiếu

~~~xml
<profile>
    <id>needs-generated-file</id>
    <activation>
        <file>
            <missing>config/generated.flag</missing>
        </file>
    </activation>
    <properties>
        <example.generate>on</example.generate>
    </properties>
</profile>
~~~

Nếu `config/generated.flag` không tồn tại khi dựng model, profile có thể bật một plugin để tạo file. **Không có vòng lặp tự đánh giá lại** khi plugin tạo xong file trong lượt build đó. Lượt chạy Maven mới có thể kích hoạt khác lượt trước, khiến kết quả không ổn định nếu phụ thuộc output cũ.

### 7.3. Biến dùng trong đường dẫn

File activation hỗ trợ một số biến như system property `user.home`, biến môi trường `env.HOME` và `project.basedir` trong những ngữ cảnh/phiên bản Maven phù hợp. Ví dụ:

~~~xml
<activation>
    <file>
        <exists>${user.home}/.config/demo/enabled.flag</exists>
    </file>
</activation>
~~~

Không dùng `${project.build.directory}` hoặc một property tùy ý khai báo trong `<properties>` của chính POM như thể nó chắc chắn khả dụng ở giai đoạn file activation. Tài liệu Maven lưu ý `project.build.directory` **không được nội suy theo cách đó**; nếu kiểm tra thư mục output, có thể dùng literal `target/...` nhưng phải hiểu rủi ro kết quả từ lần build trước.

### 7.4. Vì sao `mvn clean verify` có thể gây nhầm?

Maven xét profile activation **trước khi** phase `clean` chạy. Do đó nếu `target/marker` đang tồn tại khi bắt đầu build, profile `<exists>target/marker</exists>` có thể bật dù `clean` xóa marker ngay sau đó. Ngược lại, marker tạo ở phase `package` không tự làm profile bật giữa lượt chạy. Đừng dùng trạng thái file sinh ngẫu nhiên để quyết định dependency/version quan trọng.

## 8. POM hoàn chỉnh minh họa bốn kiểu kích hoạt

Dự án mẫu dùng Java 17+ và Maven 3.9.x. Mỗi profile sửa **một property riêng** để khi nhiều profile cùng active không ghi đè nhau. Dùng Maven Help Plugin để xem kết quả; không cần Spring Boot, database hay plugin đặc biệt.

Cấu trúc:

~~~text
profile-activation-demo/
├── pom.xml
├── config/
│   └── enable.marker          (chỉ tạo khi thử)
└── src/main/java/dev/example/App.java
~~~

Tạo toàn bộ `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>profile-activation-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <example.jdk>off</example.jdk>
        <example.os>off</example.os>
        <example.mode>off</example.mode>
        <example.file>off</example.file>
        <example.combined>off</example.combined>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>

    <profiles>
        <profile>
            <id>jdk-17-plus</id>
            <activation><jdk>[17,)</jdk></activation>
            <properties><example.jdk>on</example.jdk></properties>
        </profile>

        <profile>
            <id>windows</id>
            <activation>
                <os><family>windows</family></os>
            </activation>
            <properties><example.os>on</example.os></properties>
        </profile>

        <profile>
            <id>dev-mode</id>
            <activation>
                <property>
                    <name>demo.mode</name>
                    <value>dev</value>
                </property>
            </activation>
            <properties><example.mode>on</example.mode></properties>
        </profile>

        <profile>
            <id>marker-present</id>
            <activation>
                <file><exists>config/enable.marker</exists></file>
            </activation>
            <properties><example.file>on</example.file></properties>
        </profile>

        <profile>
            <id>jdk-dev-with-marker</id>
            <activation>
                <jdk>[17,)</jdk>
                <property>
                    <name>demo.mode</name>
                    <value>dev</value>
                </property>
                <file><exists>config/enable.marker</exists></file>
            </activation>
            <properties><example.combined>on</example.combined></properties>
        </profile>
    </profiles>
</project>
~~~

**Vì sao cấu hình này phù hợp để học?**

- `jdk-17-plus` chỉ kiểm tra JDK runtime của Maven.
- `windows` chỉ kiểm tra OS, nên có thể active cùng profile JDK.
- `dev-mode` do CLI `-Ddemo.mode=dev` quyết định.
- `marker-present` do file thật quyết định.
- `jdk-dev-with-marker` là phép **JDK AND property AND file**.
- Các property `example.*` có giá trị mặc định `off` và chỉ chuyển sang `on` khi profile tương ứng active.
- Các plugin Maven Compiler và JAR được khai báo version để giảm sự khác biệt giữa môi trường.

### 8.1. Java 17 chạy được

Tạo `src/main/java/dev/example/App.java`:

~~~java
package dev.example;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Maven profile activation demo");
    }
}
~~~

Chạy tại thư mục dự án:

~~~bash
mvn -B -ntp clean package
java -cp target/classes dev.example.App
~~~

**Stdout chính xác của lệnh `java` cuối:**

~~~text
Maven profile activation demo
~~~

Chương trình Java in một chuỗi cố định; `example.*` là POM properties ở **build time**, không tự biến thành Java system properties ở runtime. Chúng ta sẽ đọc property qua Help Plugin ở phần tiếp theo.

## 9. Thực nghiệm kiểm tra từng loại activation

Maven Help Plugin cung cấp ba goal rất hữu ích:

- `help:active-profiles`: profile nào **đang active**.
- `help:effective-pom`: mô hình POM sau khi các profile active được ghép.
- `help:evaluate`: giá trị một property/expression trong ngữ cảnh build.

Ví dụ gọi plugin bằng tọa độ/version tường minh để không phụ thuộc cách resolver chọn plugin:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
~~~

### 9.1. Thử JDK và OS

~~~bash
mvn -version
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
mvn -q org.apache.maven.plugins:maven-help-plugin:3.5.2:evaluate -Dexpression=example.jdk -DforceStdout
mvn -q org.apache.maven.plugins:maven-help-plugin:3.5.2:evaluate -Dexpression=example.os -DforceStdout
~~~

Nếu Maven chạy bằng JDK 17+, `example.jdk` dự kiến là `on`. Trên Windows đúng family, `example.os` dự kiến `on`; trên Linux thường là `off`. **Không có một kết quả OS cố định cho mọi máy.**

### 9.2. Thử property

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles -Ddemo.mode=dev
mvn -q org.apache.maven.plugins:maven-help-plugin:3.5.2:evaluate -Ddemo.mode=dev -Dexpression=example.mode -DforceStdout
~~~

Giá trị `example.mode` dự kiến:

~~~text
on
~~~

Thử lại với `-Ddemo.mode=prod` hoặc không có `-Ddemo.mode`: `example.mode` là `off` nếu không có cấu hình khác ghi đè. So `dev` với `DEV` để thấy property matching phân biệt hoa/thường.

### 9.3. Thử file marker

Đứng ở gốc dự án. Linux/macOS:

~~~bash
mkdir -p config
touch config/enable.marker
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force .\config | Out-Null
New-Item -ItemType File -Force .\config\enable.marker | Out-Null
~~~

Sau đó:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
mvn -q org.apache.maven.plugins:maven-help-plugin:3.5.2:evaluate -Dexpression=example.file -DforceStdout
~~~

Giá trị `example.file` dự kiến là `on`. Xóa marker (Linux/macOS `rm -f config/enable.marker`; PowerShell `Remove-Item -LiteralPath .\config\enable.marker -ErrorAction SilentlyContinue`) rồi gọi Maven lần mới: property trở về `off`.

### 9.4. Thử điều kiện AND

Với **JDK 17+**, marker chưa có, chạy:

~~~bash
mvn -q org.apache.maven.plugins:maven-help-plugin:3.5.2:evaluate -Ddemo.mode=dev -Dexpression=example.combined -DforceStdout
~~~

Kết quả `off` vì thiếu marker. Tạo marker lại rồi chạy cùng lệnh: kết quả `on` khi cả ba điều kiện cùng đúng.

| `demo.mode` | Marker có? | `example.mode` | `example.file` | `example.combined` |
| --- | --- | --- | --- | --- |
| Không khai báo | Không | `off` | `off` | `off` |
| `dev` | Không | `on` | `off` | `off` |
| Không khai báo | Có | `off` | `on` | `off` |
| `dev` | Có | `on` | `on` | `on` |
| `prod` | Có | `off` | `on` | `off` |

Bảng áp dụng khi **JDK condition đúng** và không có nguồn khác ghi đè property. Nếu JDK runtime thấp hơn 17, `example.combined` không tự active dù property và marker đúng; nhưng đừng dùng dự án Java 17 này để yêu cầu biên dịch bằng JDK không hỗ trợ 17.

### 9.5. Xem effective POM để xác nhận nguồn

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Ddemo.mode=dev -Dverbose=true -Doutput=effective-profile.xml
~~~

Trong output, tìm các property `example.jdk`, `example.os`, `example.mode`, `example.file`, `example.combined`. `-Dverbose=true` có thể tạo comment nguồn trong XML theo hỗ trợ của phiên bản Help Plugin. Mục tiêu là **xác nhận model hiệu lực**, không thay thế việc kiểm tra plugin đã chạy.

So lần có/không marker và `-Ddemo.mode=dev`; có thể dùng `help:active-profiles` và `help:evaluate` trước vì kết quả gọn hơn. Đừng commit effective POM hay log chứa thông tin môi trường nội bộ nếu không thật sự cần.

## 10. Kích hoạt tường minh và activeByDefault: hai ngoại lệ quan trọng

### 10.1. `-P` ép bật theo ID

~~~bash
mvn -Pdev-mode help:active-profiles
mvn -Pdev-mode,marker-present help:active-profiles
~~~

` -Pdev-mode ` là yêu cầu **tường minh**. Profile có thể active kể cả khi người dùng **không** truyền `-Ddemo.mode=dev`; như vậy không còn là phép thử điều kiện implicit. Khi debug property/file activation, **bỏ `-P`** để biết profile có tự bật hay không.

Maven 4 có quy tắc chặt hơn với profile ID không tìm thấy: trong tình huống cho phép ID optional, dùng tiền tố `?` theo tài liệu Maven 4; không nên giả định `-P` với ID sai sẽ luôn bị bỏ qua.

### 10.2. `activeByDefault` không luôn active

~~~xml
<profile>
    <id>local-default</id>
    <activation>
        <activeByDefault>true</activeByDefault>
    </activation>
    <properties>
        <example.default>on</example.default>
    </properties>
</profile>
~~~

Trong **cùng POM**, profile `activeByDefault` chỉ làm mặc định khi chưa có profile khác của POM đó được kích hoạt qua cơ chế phù hợp. Nếu `jdk-17-plus` hoặc `windows` của chính POM đã được bật bởi môi trường, profile mặc định có thể bị vô hiệu. Vì thế trong ví dụ dùng JDK 17+, thêm `activeByDefault` không bảo đảm property `example.default` luôn `on`.

Nếu một giá trị **luôn cần tồn tại**, đặt nó ở `<project><properties>` ngoài profile; chỉ để profile ghi đè khi có tình huống đặc biệt.

### 10.3. Vô hiệu hóa profile

Để tắt profile có thể kích hoạt theo môi trường, Maven cho phép ký hiệu phủ định trong danh sách `-P`; dạng tránh vấn đề dấu `!` của shell thường dùng:

~~~bash
mvn -P=-jdk-17-plus help:active-profiles
~~~

Thử đúng cú pháp với phiên bản Maven của dự án. Việc vô hiệu profile không làm JDK đổi phiên bản; nó chỉ không áp dụng **tác động của profile đó**. Không nhầm `-P=-jdk-17-plus` với `<jdk>!17</jdk>` — hai cơ chế khác nhau.

## 11. Khi nhiều profile cùng active

Khi nhiều profile cùng khai báo một property hoặc cấu hình plugin/dependency, Maven phải merge chúng. Theo quy tắc profile order, trong một POM, profile active **định nghĩa sau** thường có ưu tiên hơn khi cùng chỉnh giá trị, không đơn giản theo thứ tự gõ `-P`.

Đoạn ví dụ **không nên thiết kế mơ hồ**:

~~~xml
<profile>
    <id>windows</id>
    <activation><os><family>windows</family></os></activation>
    <properties><example.mode>from-windows</example.mode></properties>
</profile>
<profile>
    <id>dev-mode</id>
    <activation>
        <property><name>demo.mode</name><value>dev</value></property>
    </activation>
    <properties><example.mode>from-dev</example.mode></properties>
</profile>
~~~

Nếu cả hai active, `example.mode` bị hai nơi cạnh tranh và kết quả có thể khác kỳ vọng của người mới. Ví dụ POM hoàn chỉnh ở mục 8 **cố ý dùng tên property khác nhau cho từng profile** để tránh xung đột. Trong dự án thật, nên ghi rõ quy tắc ưu tiên, kiểm tra effective POM với các combination và tránh dùng OS/file tình cờ để đổi version dependency quan trọng.

Các điểm bảo đảm khả năng tái lập:

1. Dùng Maven Wrapper để thống nhất Maven core.
2. Ghi rõ JDK/OS/CLI profile cần thiết trong README và CI.
3. Khai báo version plugin quan trọng, tránh version phụ thuộc mặc định nếu cần kết quả ổn định.
4. Để build logic dùng chung trong POM/parent có kiểm soát thay vì chỉ trong settings máy cá nhân.
5. Dùng marker có chủ đích, tránh file output `target/` còn sót.
6. Không đưa password, token, cấu hình nhạy cảm hoặc đường dẫn absolute cá nhân vào profile.
7. Nếu điều kiện là quy tắc bắt buộc (chẳng hạn JDK >=17), **Enforcer** có thể phù hợp hơn activation đơn thuần.

## 12. Chẩn đoán khi profile không hoạt động như mong đợi

| Triệu chứng | Nguyên nhân hay gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| `<jdk>17</jdk>` không bật trên JDK 21 | Prefix không phải >= | Dùng `[17,)` và kiểm tra `mvn -version` |
| Java release là 21 nhưng `jdk21` không active | `release` khác JDK chạy Maven | Đọc `mvn -version`; xem Toolchains nếu dùng |
| Windows profile không active | Maven chạy trong WSL/container/Linux hoặc OS attributes khác | `mvn -version`, `OsProbe`, `help:active-profiles` |
| `env.CI` không khớp | Sai tên/chữ hoa hoặc CI không đặt `CI=true` | Kiểm tra biến không nhạy cảm và điều kiện `value` |
| Property name đúng nhưng vẫn off | `-D` khác giá trị, phân biệt hoa/thường | Thử `help:active-profiles -Ddemo.mode=dev` |
| Kết hợp JDK + file nhưng chỉ một đúng | Logic AND | Đảm bảo **tất cả** điều kiện đúng hoặc tách profile |
| File plugin vừa tạo nhưng profile không bật | Activation được xét trước lifecycle | Tạo marker trước lệnh Maven hoặc dùng `-D` |
| `${project.build.directory}` trong file activation không chạy | Interpolation ở đây bị giới hạn | Dùng đường dẫn phù hợp hoặc system/request property |
| Default profile tự tắt | Profile khác cùng POM active | Dùng `help:active-profiles`; đặt default value ở `<properties>` |
| `-Pdev-mode` bật dù thiếu `demo.mode` | `-P` là explicit | Bỏ `-P` nếu muốn kiểm tra implicit |
| Parent/child cùng ID có kết quả khác | Profile không được kế thừa nguyên khối | Xem effective POM **của đúng module** |
| Cấu hình ở CI khác laptop | JDK/OS/settings/CLI/marker khác | Ghi nhận lệnh, environment, active profiles và POM hiệu lực |

Quy trình điều tra nhanh:

~~~bash
mvn -version
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=effective-profile.xml
~~~

Nếu build thực tế có `-Ddemo.mode=dev` hoặc `-P...`, phải **thêm chính xác các tham số đó vào lệnh điều tra**. Một effective POM tạo khi không có profile không chứng minh điều gì cho build CI chạy profile khác.

## 13. Những giới hạn cần nhớ

- Activation quyết định **cấu hình nào được đưa vào model**, không tự cài JDK, không tự tạo file, không tự đổi OS hoặc đảm bảo plugin đã làm việc.
- `<jdk>` đo JVM chạy Maven, không đo Compiler Plugin `release`/Toolchains.
- `<os>` xem OS mà Java thấy; lệnh trên host và lệnh chạy trong container có thể cho kết quả khác.
- Property activation phụ thuộc property hệ thống/user hoặc môi trường Maven cung cấp; không phải một biểu thức tùy ý theo mọi biến POM.
- File activation nhạy với thời điểm đọc file; output của build trước làm một profile có thể bật/tắt ngoài ý muốn.
- `activeByDefault` có quy tắc tự vô hiệu, không bảo đảm một profile luôn bật.
- `help:effective-pom` cho biết model, nhưng không phải toàn bộ dữ liệu resolver/plugin runtime.
- Maven 4 có một số khác biệt về xử lý profile ID và những khả năng activation mới; không dùng tính năng chỉ có ở Maven 4 rồi kỳ vọng POM chạy trên Maven 3.

**Khi nào nên dùng profile?** Phù hợp cho cấu hình build có một khác biệt rõ ràng theo môi trường. **Khi nào không nên?** Khi muốn che lỗi điều kiện bắt buộc, khi profile phụ thuộc trạng thái máy khó tái hiện, hoặc khi bạn cần thay đổi mã nghiệp vụ mỗi lần chạy mà không thể kiểm chứng.

## 14. Bài tập và câu hỏi tự kiểm tra

**Bài 1 — phân biệt prefix/range.** `<jdk>17</jdk>` có tự bật trên JDK 21? **Không.** `<jdk>[17,)</jdk>` thì sao? **Có**, nếu chính Maven chạy trên JDK 21.

**Bài 2 — phép AND.** Profile có `<jdk>[17,)</jdk>`, `<property><name>demo.mode</name><value>dev</value>` và `<file><exists>config/enable.marker</exists>`. JDK 21, file có, `demo.mode=prod`. Có tự bật không? **Không**, vì property không khớp.

**Bài 3 — điều kiện file missing.** Một profile dùng `<missing>config/generated.flag</missing>`. Lần 1 file chưa có, lần 2 tạo file, lần 3 xóa file. Khi Maven được khởi động lại mỗi lần: **active → không active → active**, nếu không có cơ chế kích hoạt tường minh.

**Bài 4 — property phủ định.** Phân biệt `<name>!debug</name>` với `<name>debug</name><value>!true</value>`. Khi không có `debug`, hai điều kiện có thể cùng đúng; khi `debug=false`, chỉ điều kiện giá trị phủ định khớp.

**Bài 5 — OS.** Tạo và chạy `OsProbe.java` để xem `os.arch`. Viết một profile chỉ bật khi `family=windows` và `arch` khớp chuỗi thật trên máy; kiểm chứng bằng Help Plugin.

**Bài 6 — kiểm chứng thực hành.** Với POM ở mục 8, chạy không có marker, có marker, và kết hợp `-Ddemo.mode=dev`. So bảng kết quả mục 9.4. Nếu khác, đối chiếu JVM/OS/settings/profile mà môi trường đang dùng.

**Bài 7 — CI.** Một CI tự đặt `CI=true` nhưng laptop không có. Viết profile `env.CI`, giải thích vì sao một build chỉ dựa vào file `pom.xml` chưa mô tả đủ các điều kiện để tái hiện output. Nêu cách ghi lại điều kiện **không nhạy cảm** và dùng `help:active-profiles` để xác nhận.

## 15. Checklist trước khi áp dụng vào dự án thật

- [ ] Profile có ID và mục đích rõ ràng, đặt đúng nơi (POM hoặc settings).
- [ ] Biết JDK dùng trong `<jdk>` là JDK chạy Maven.
- [ ] Dùng range khi cần >= thay vì nhầm prefix.
- [ ] Điều kiện OS được thử trên JVM/runner thực, không chỉ từ tên OS bên ngoài.
- [ ] Property activation phân biệt có tên, đúng giá trị, phủ định và `env.`.
- [ ] File activation xác định rõ `exists` hay `missing`, đường dẫn và thời điểm tồn tại.
- [ ] Không phụ thuộc `project.build.directory` hoặc property POM không hỗ trợ interpolation file activation.
- [ ] Khi có nhiều loại activation, hiểu phép **AND**.
- [ ] Không lặp cùng activation type để tạo OR.
- [ ] Không hiểu `activeByDefault` là always-on.
- [ ] Khi test implicit activation, không dùng `-P` ép bật profile cần kiểm tra.
- [ ] Kiểm tra `help:active-profiles`, `help:evaluate` và effective POM trên đúng module.
- [ ] Không để profile cạnh tranh ghi đè property/dependency quan trọng ngoài ý muốn.
- [ ] CI và tài liệu hướng dẫn ghi rõ Maven/JDK/OS/profile/marker cần thiết.
- [ ] Với điều kiện bắt buộc, cân nhắc Maven Enforcer thay vì chỉ bật/tắt profile.

## 16. Tài liệu chính thức

1. [Apache Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html): cơ chế JDK, OS, property, file, phủ định, nhiều điều kiện, `-P` và `activeByDefault`.
2. [Apache Maven — Settings Reference](https://maven.apache.org/settings.html): profile và activation trong settings.
3. [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html): POM, parent và model.
4. [Maven Help Plugin — active-profiles](https://maven.apache.org/plugins/maven-help-plugin/active-profiles-mojo.html): profile active.
5. [Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html): mô hình POM sau khi profile được ghép.
6. [Maven Help Plugin — evaluate](https://maven.apache.org/plugins/maven-help-plugin/evaluate-mojo.html): đánh giá property/expression.
7. [Maven Enforcer Plugin — Require Java Version](https://maven.apache.org/enforcer/enforcer-rules/requireJavaVersion.html): kiểm tra bắt buộc phiên bản Java.
