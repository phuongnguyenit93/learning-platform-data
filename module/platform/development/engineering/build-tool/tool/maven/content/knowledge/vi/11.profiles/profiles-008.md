# Dùng help:active-profiles và effective POM để chẩn đoán profile Maven

## 1. Vấn đề: cùng một dự án, vì sao hai máy build khác nhau?

Maven profile cho phép thay đổi một phần cấu hình build theo môi trường. Nhờ profile, cùng một `pom.xml` có thể dùng property, repository, plugin hoặc thiết lập build khác nhau trên máy phát triển, CI và một môi trường kiểm thử. Nhưng đây cũng là nguồn gây lỗi khó tìm:

- Máy A build thành công, máy B lại dùng phiên bản dependency hoặc cấu hình plugin khác.
- Lệnh `mvn package` tạo ra resource có giá trị `LOCAL`, còn CI cho ra `CI`.
- Người viết POM tin rằng profile `dev` luôn bật, nhưng profile đó bị tắt khi một profile khác kích hoạt.
- Profile nằm trong user `settings.xml` của một máy, nên đồng đội không thấy trong POM.
- Một dự án nhiều module có cấu hình hiệu lực khác nhau giữa parent và từng module.
- Người dùng chạy `-Pci` nhưng không xác định được nó có thực sự được Maven áp dụng hay không.

Cách chẩn đoán hiệu quả nhất là **tách hai câu hỏi**:

1. **Profile nào đang active?** Dùng `mvn help:active-profiles`.
2. **Cấu hình POM thực tế sau khi áp dụng các profile là gì?** Dùng `mvn help:effective-pom`.

Hai goal này thuộc **Maven Help Plugin**. Chúng là công cụ *đọc/giải thích mô hình build*; bản thân việc gọi chúng không tương đương với chạy compile/test/package và không tự sửa POM.

## 2. So sánh nhanh các lệnh chẩn đoán

| Lệnh | Trả lời câu hỏi | Điểm cần hiểu |
| --- | --- | --- |
| `mvn help:active-profiles` | Profile nào được kích hoạt ở lần gọi Maven hiện tại? | Liệt kê ID/profile source, không trình bày toàn bộ cấu hình mà profile đóng góp |
| `mvn help:all-profiles` | Có những profile nào được khai báo/khả dụng trong ngữ cảnh project? | Hữu ích khi profile mong đợi không active |
| `mvn help:effective-pom` | Project POM hiệu lực trông như thế nào sau inheritance, defaults và active profiles? | Dùng để kiểm tra `properties`, `dependencies`, `build/plugins`, repository... |
| `mvn help:effective-pom -Dverbose=true` | Có thể truy vết nhiều phần tử hiệu lực tới tệp/vị trí nguồn không? | Với Help Plugin hỗ trợ `verbose`, thêm comment XML về nguồn của phần tử |
| `mvn help:evaluate -Dexpression=app.mode -q -DforceStdout` | Biểu thức/property cụ thể được Maven đánh giá thành giá trị nào? | Nhanh hơn đọc cả effective POM khi chỉ cần một giá trị |
| `mvn help:effective-settings` | Cấu hình settings đã hợp nhất là gì? | Khác effective POM; có thể chứa dữ liệu riêng, phải bảo vệ |
| `mvn -version` | Maven, JVM, Java home, OS đang được dùng? | Cần thiết khi nghi profile kích hoạt theo JDK/OS |

Lưu ý cách gọi: `help:active-profiles` và `help:effective-pom` là **goal** của plugin, không phải phase trong default lifecycle như `test` hay `verify`. Muốn chẩn đoán đúng cấu hình của một lần build cụ thể, phải dùng cùng POM, settings, JDK, user properties và các tùy chọn `-P`, `-D` liên quan với lần build đó.

## 3. Profile được định nghĩa và kích hoạt ở đâu?

Một số nguồn profile phổ biến:

| Nguồn | Nơi định nghĩa | Điều dễ nhầm |
| --- | --- | --- |
| Project profile | `<profiles>` trong `pom.xml` | Có trong file không có nghĩa nó đang active |
| User settings profile | `~/.m2/settings.xml` | Chỉ tác động trên môi trường đọc settings đó |
| Global settings profile | `conf/settings.xml` của bản Maven tương ứng | Dễ khác nhau giữa máy hoặc Maven Wrapper |
| Parent POM profile | Profile trong một POM cha | Các profile không được kế thừa nguyên dạng; phần cấu hình **đã được profile active áp dụng** có thể đi vào mô hình kế thừa |
| CLI | `-Pprofile-id` | Kích hoạt tường minh theo ID nếu profile có trong ngữ cảnh phù hợp |

Ngoài `-P`, Maven hỗ trợ kích hoạt theo các điều kiện `<activation>` như `activeByDefault`, JDK, OS, system/CLI property và sự tồn tại của file. Profile trong settings còn có thể được chọn qua `<activeProfiles>`.

**Profile active không đồng nghĩa mọi module đều nhận cùng một kết quả.** Mỗi POM có ngữ cảnh kế thừa, tính toán property và cách áp dụng profile riêng. Khi so sánh multi-module, cần đọc mô hình của đúng module đang có vấn đề.

### 3.1. Ví dụ profile bật mặc định

~~~xml
<profile>
    <id>local</id>
    <activation>
        <activeByDefault>true</activeByDefault>
    </activation>
    <properties>
        <app.mode>LOCAL</app.mode>
    </properties>
</profile>
~~~

`activeByDefault` là trạng thái mặc định **trong container profile của POM đó**. Khi một profile khác trong cùng POM được kích hoạt (qua CLI hoặc activation phù hợp), profile `local` ở chế độ active-by-default thường bị vô hiệu hóa. Đây là nguyên nhân phổ biến khiến giá trị mặc định biến mất khi chạy `-Pci`.

### 3.2. Ví dụ kích hoạt khi có CLI property

~~~xml
<profile>
    <id>ci</id>
    <activation>
        <property>
            <name>build.ci</name>
            <value>true</value>
        </property>
    </activation>
    <properties>
        <app.mode>CI</app.mode>
    </properties>
</profile>
~~~

Cấu hình này cho phép bật profile `ci` bằng `-Dbuild.ci=true`, **không cần** `-Pci`. Nếu chỉ gõ `-Dbuild.ci=false`, điều kiện `value=true` không đạt nên profile này không được kích hoạt theo điều kiện property đó.

Ngược lại, nếu dùng `-Pci`, profile `ci` được yêu cầu kích hoạt tường minh; giá trị `build.ci` không bắt buộc phải tồn tại để thỏa điều kiện implicit activation.

## 4. Dự án thực hành Java 17: thấy rõ thay đổi của profile

Tạo thư mục dự án:

~~~text
profile-diagnostics/
├── pom.xml
└── src/
    └── main/
        ├── java/example/ProfileApp.java
        └── filtered-resources/build.properties
~~~

Ta muốn file `build.properties` được Maven biến đổi lúc build, để Java đọc cấu hình đã được profile chọn. Bài này dùng delimiter `@name@` trong resource filtering nhằm tránh nhầm giữa ký hiệu Maven ở lúc build với placeholder của framework ở runtime.

### 4.1. Toàn bộ `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>profile-diagnostics</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <app.banner>BASE</app.banner>
        <app.mode>base</app.mode>
    </properties>

    <build>
        <resources>
            <resource>
                <directory>src/main/filtered-resources</directory>
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
                <configuration>
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
        </plugins>
    </build>

    <profiles>
        <profile>
            <id>local</id>
            <activation>
                <activeByDefault>true</activeByDefault>
            </activation>
            <properties>
                <app.banner>LOCAL</app.banner>
                <app.mode>local</app.mode>
            </properties>
        </profile>
        <profile>
            <id>ci</id>
            <activation>
                <property>
                    <name>build.ci</name>
                    <value>true</value>
                </property>
            </activation>
            <properties>
                <app.banner>CI</app.banner>
                <app.mode>ci</app.mode>
            </properties>
        </profile>
    </profiles>
</project>
~~~

Giải thích:

- Các property `app.banner=BASE` và `app.mode=base` ở cấp project là fallback khi không profile nào ghi đè.
- `local` bật mặc định và đặt `LOCAL/local`; `ci` đặt `CI/ci` khi kích hoạt.
- `<maven.compiler.release>17</maven.compiler.release>` chọn ngôn ngữ/API target Java 17 cho Compiler Plugin. Cần JDK 17+ và Maven tương thích.
- Resources Plugin chỉ lọc đúng file text `build.properties`; nó không tự thay literal string trong Java. Các phiên bản plugin được khai báo rõ để ví dụ ổn định, không ngụ ý là phiên bản mới nhất.
- `app.mode` là property do project đặt tên, không phải một chế độ chạy được Maven tự hiểu; ứng dụng chỉ đọc giá trị đã được lọc.

### 4.2. Tệp tài nguyên trước khi Maven lọc

Tạo `src/main/filtered-resources/build.properties`:

~~~properties
banner=@app.banner@
mode=@app.mode@
version=@project.version@
~~~

Trong file nguồn, đây là các placeholder. Khi Maven chạy pha `process-resources` hoặc pha sau nó như `package`, plugin tạo `target/classes/build.properties` sau filtering. `@project.version@` được thay bởi version của project hiện hành.

Nếu build không có profile `ci`, file đích dự kiến là:

~~~properties
banner=LOCAL
mode=local
version=1.0.0
~~~

Nếu kích hoạt `ci`, file đích dự kiến là:

~~~properties
banner=CI
mode=ci
version=1.0.0
~~~

### 4.3. Java 17 đọc resource đã được lọc

Tạo `src/main/java/example/ProfileApp.java`:

~~~java
package example;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public final class ProfileApp {
    private ProfileApp() {
    }

    public static void main(String[] args) throws IOException {
        Properties props = new Properties();

        try (InputStream input =
                     ProfileApp.class.getResourceAsStream("/build.properties")) {
            if (input == null) {
                throw new IllegalStateException("Missing build.properties");
            }
            try (InputStreamReader reader =
                         new InputStreamReader(input, StandardCharsets.UTF_8)) {
                props.load(reader);
            }
        }

        System.out.println("banner=" + props.getProperty("banner"));
        System.out.println("mode=" + props.getProperty("mode"));
        System.out.println("version=" + props.getProperty("version"));
    }
}
~~~

Sử dụng `Properties.load(Reader)` với UTF-8 là cách chủ động kiểm soát encoding; overload nhận `InputStream` truyền thống có quy tắc giải mã khác. Ở ví dụ này toàn bộ output là ASCII, nhưng cách đọc vẫn phù hợp nếu sau này banner có dấu tiếng Việt.

Ứng dụng không gọi Maven để hỏi profile nào active. Nó chỉ nhìn thấy file đã được Maven tạo trong classpath. Vì vậy kết quả chạy Java giúp kiểm tra **artifact/resource nhận cấu hình gì**, còn `help:active-profiles` và `effective-pom` giúp xác định **Maven đã chọn gì khi build**.

## 5. Lượt 1: chẩn đoán build mặc định

Đứng ở thư mục chứa `pom.xml` và chạy:

~~~bash
mvn -version
mvn -B -ntp help:active-profiles
~~~

Với POM ví dụ, trong điều kiện không có settings/CLI nào kích hoạt profile khác, hãy tìm profile ID **`local`** trong kết quả `help:active-profiles`. Tên project, các dòng INFO và định dạng thông báo phụ thuộc Maven Help Plugin, vì vậy không học thuộc trích đoạn log theo số dòng.

Tiếp theo tạo POM hiệu lực vào file:

~~~bash
mvn -B -ntp help:effective-pom -Doutput=effective-local.xml
~~~

Mở `effective-local.xml` và tìm `<properties>`; kỳ vọng thấy property kết quả đại loại:

~~~xml
<app.banner>LOCAL</app.banner>
<app.mode>local</app.mode>
~~~

Đây là **trích đoạn** của effective POM, không phải XML độc lập. File effective POM thường dài hơn POM gốc nhiều vì có cả super POM, parent inheritance, defaults và plugin configuration mà Maven đã tính.

Sau đó chạy build và chương trình:

~~~bash
mvn -B -ntp clean package
java -cp target/classes example.ProfileApp
~~~

**Stdout chính xác của riêng lệnh `java` ở cấu hình mặc định trong ví dụ**:

~~~text
banner=LOCAL
mode=local
version=1.0.0
~~~

`mvn package` không tự gọi `main` của `ProfileApp`. Dấu vết cần đối chiếu là profile `local` đang active, effective POM có `LOCAL/local`, resource đã lọc cùng giá trị và Java in ra đúng hai giá trị đó.

## 6. Lượt 2: kích hoạt `-Pci` và so sánh

Chạy cùng ngữ cảnh project, chỉ thêm cờ `-Pci`:

~~~bash
mvn -B -ntp -Pci help:active-profiles
mvn -B -ntp -Pci help:effective-pom -Doutput=effective-ci.xml
mvn -B -ntp -Pci clean package
java -cp target/classes example.ProfileApp
~~~

Kỳ vọng khi không có profile khác được kích hoạt ngoài ý muốn:

- `help:active-profiles` liệt kê **`ci`**, không còn `local` active-by-default trong cùng POM.
- `effective-ci.xml` có `app.banner=CI` và `app.mode=ci` ở mô hình hiệu lực.
- Maven tạo lại `target/classes/build.properties` sau `clean package` với `CI/ci`.
- Java in chính xác:

~~~text
banner=CI
mode=ci
version=1.0.0
~~~

**Điểm cần tránh:** nếu chỉ chạy `mvn -Pci help:active-profiles` rồi sau đó `mvn package` **không có `-Pci`**, việc xem profile ở lệnh thứ nhất **không làm profile đó được ghi nhớ cho lệnh thứ hai**. Cờ `-P` áp dụng cho tiến trình Maven được gọi, không tự thay `pom.xml` hay tạo trạng thái cố định cho terminal.

Do đó khi debug một build CI, hãy lấy **chính command line mà CI đã chạy** và dùng cùng `-P`, `-D`, `-s` cho lệnh Help Plugin.

## 7. Lượt 3: profile được bật bởi `-D`, không cần `-P`

Trong ví dụ, profile `ci` có điều kiện:

~~~xml
<activation>
    <property>
        <name>build.ci</name>
        <value>true</value>
    </property>
</activation>
~~~

Chạy:

~~~bash
mvn -B -ntp -Dbuild.ci=true help:active-profiles
mvn -B -ntp -Dbuild.ci=true help:effective-pom -Doutput=effective-property.xml
mvn -B -ntp -Dbuild.ci=true clean package
java -cp target/classes example.ProfileApp
~~~

Kết quả dự kiến là `ci` active, `local` bị vô hiệu do một profile khác trong cùng POM được kích hoạt, và Java lại in:

~~~text
banner=CI
mode=ci
version=1.0.0
~~~

Đổi `-Dbuild.ci=true` thành `-Dbuild.ci=false` rồi kiểm tra lại, profile `ci` không được kích hoạt bằng điều kiện `value=true`; nếu không có điều kiện khác, `local` trở lại.

**Phân biệt rất rõ:**

- `-Pci`: yêu cầu Maven chọn **profile có ID `ci`**.
- `-Dbuild.ci=true`: đặt **user property**; profile `ci` trong ví dụ tình cờ dùng property này làm điều kiện kích hoạt.
- `-Dapp.banner=CLI`: đặt một property; nó **không tự động** kích hoạt profile `ci` vì POM không có activation condition nào kiểm tra `app.banner`.

Với một profile kích hoạt theo property, hãy kiểm tra đúng **tên key và giá trị** trong phần `<activation>`, không chỉ tìm tên profile.

## 8. `help:active-profiles`: cách đọc kết quả cho đúng

Mục tiêu của goal là liệt kê các profile **đang active cho lần build hiện tại**, có thể có thông tin về nguồn khai báo. Một mẫu đầu ra đơn giản hóa:

~~~text
The following profiles are active:
 - ci (source: ...)
~~~

Dòng trên chỉ là **minh họa định dạng**, không cam kết Maven nào cũng in đúng văn bản. Khi đọc kết quả, hãy trả lời:

1. **ID nào đang active?** Ví dụ `local`, `ci` hoặc profile từ settings.
2. **Profile có nguồn nào?** Project POM, settings, hoặc source được Help Plugin trình bày. Cùng ID xuất hiện ở hai nơi có thể không đồng nghĩa cùng cấu hình.
3. **Mình đã tái hiện đúng lệnh chưa?** So sánh `-P`, `-D`, `-s`, JDK, working directory và các profile settings.
4. **Lệnh có chạy ở đúng module không?** Ở multi-module, `help:active-profiles` là goal kiểu aggregator; phải chú ý output theo project/context chứ không được mặc nhiên suy rằng mọi module có cùng profile active.
5. **Profile mong đợi có tồn tại không?** Nếu không thấy, dùng `mvn help:all-profiles` và kiểm tra file cấu hình liên quan.

Có thể lưu output thay vì chỉ đọc màn hình. Goal `active-profiles` của Maven Help Plugin có tham số `output`:

~~~bash
mvn -B -ntp -Pci help:active-profiles -Doutput=active-ci.txt
~~~

File `active-ci.txt` hữu ích khi so sánh hai lần chạy hoặc gửi bug report đã rà soát. Dù đây chủ yếu là danh sách profile, tên project, đường dẫn hoặc thông tin hạ tầng trong ngữ cảnh log vẫn có thể là dữ liệu nội bộ.

**Không kết luận một profile “không hoạt động” chỉ vì giá trị cuối trùng với mặc định.** Nó có thể active nhưng không override property bạn đang xem, hoặc một profile khác đã override kết quả. Ngược lại, không kết luận profile active chỉ vì có property giống tên profile. Hãy dùng output `help:active-profiles` để xác nhận ID trực tiếp.

## 9. `help:effective-pom`: quan sát cấu hình thực tế

Một lệnh cơ bản:

~~~bash
mvn help:effective-pom
~~~

Maven tính **effective POM** theo mô hình dự án: POM hiện hành, parent, super POM, plugin/dependency management, các profile active và nhiều mặc định. Tài liệu của Help Plugin mô tả goal là hiển thị effective POM của lần build, có tính đến các profile đang kích hoạt.

Để đọc dễ hơn, xuất ra file:

~~~bash
mvn -B -ntp -Pci help:effective-pom -Doutput=effective-ci.xml
~~~

Không nên copy một file effective POM vào `pom.xml` rồi coi đó là bản sửa cuối: nó là **đầu ra chẩn đoán**, chứa nhiều cấu hình phát sinh từ kế thừa và defaults, có thể khác theo môi trường.

### 9.1. Những phần nên kiểm tra trong effective POM

| Triệu chứng | Phần XML nên tìm | Câu hỏi |
| --- | --- | --- |
| App nhận sai property | `<properties>` | `<app.mode>`, `<app.banner>` có giá trị nào? |
| Build dùng Java version không đúng | `<properties>`, `<build><plugins>` | `maven.compiler.release`, compiler plugin configuration có đúng? |
| Plugin execution chỉ có ở CI | `<build><plugins><plugin><executions>` | Execution và goal thực sự có trong mô hình hiệu lực không? |
| Dependency dùng version lạ | `<dependencies>`, `<dependencyManagement>` | Version đến từ khai báo trực tiếp, parent hay BOM? |
| Repository bị đổi | `<repositories>`, `<pluginRepositories>` | Có repository nào được thêm bởi profile/settings không? |
| Tham số test bị thay | `<plugin><configuration>`, property skip | `skipTests` hoặc config của Surefire/Failsafe có đúng? |
| Resource filtering không xảy ra | `<build><resources>`, Resources Plugin | Directory, filtering và delimiter có thực sự được áp dụng? |

**Giới hạn của effective POM:** mô hình hiệu lực không phải nhật ký các goal đã thực thi. Ví dụ thấy plugin declaration không chứng minh goal kiểm tra đã chạy; phải xem lifecycle binding, execution, build log và report thực tế. Effective POM cũng không phải bản dump hoàn chỉnh của mọi giá trị do CLI, môi trường, transport hay plugin tính ra lúc thực thi.

### 9.2. Dùng `-Dverbose=true` để truy vết nguồn

Theo Maven Help Plugin, `verbose` thêm comment về nguồn của các phần tử XML:

~~~bash
mvn -B -ntp -Pci help:effective-pom -Dverbose=true -Doutput=effective-ci-verbose.xml
~~~

Với Help Plugin hỗ trợ tham số `verbose` (tài liệu mục tiêu của phiên bản 3.5.2 có tham số này), comment trong XML có thể chỉ ra phần tử đến từ POM hiện hành, parent hoặc nguồn mặc định. Đây là **trợ giúp truy nguồn**, không phải bằng chứng rằng profile active do một lý do duy nhất hay mọi property được override đúng.

Nếu cần độ lặp lại cao, có thể gọi plugin với version rõ ràng:

~~~bash
mvn -B -ntp -Pci org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=effective-ci-verbose.xml
~~~

Điểm cộng của cách này là không phụ thuộc việc Maven resolve alias `help` thành phiên bản plugin khác nhau giữa hai môi trường; tuy nhiên vẫn cần so JDK, Maven, settings, parent/dependencies và các input khác.

Không dùng `-Dverbose=true` như một flag toàn cục để buộc **mọi** plugin khác in debug. Ở ví dụ, nó là tham số `verbose` được Help Plugin xử lý. Muốn debug quá trình Maven, `-X` là một mục đích khác và có rủi ro lộ dữ liệu trong log.

## 10. Khi chỉ cần một giá trị: `help:evaluate`

Để kiểm tra một property, đôi khi không cần đọc hàng nghìn dòng XML. Ví dụ với dự án trên:

~~~bash
mvn -q -Pci help:evaluate -Dexpression=app.mode -DforceStdout
~~~

Đầu ra chính dự kiến cho biểu thức là:

~~~text
ci
~~~

Với cấu hình mặc định:

~~~bash
mvn -q help:evaluate -Dexpression=app.mode -DforceStdout
~~~

Kết quả dự kiến:

~~~text
local
~~~

Có thể kiểm tra các giá trị tích hợp trong mô hình:

~~~bash
mvn -q help:evaluate -Dexpression=project.version -DforceStdout
mvn -q help:evaluate -Dexpression=project.artifactId -DforceStdout
~~~

Ở ví dụ này, lần lượt là `1.0.0` và `profile-diagnostics`. Hãy chạy hai lệnh **riêng biệt**; câu trả lời của mỗi lần là một giá trị. Tùy phiên bản Help Plugin, log tải plugin lần đầu và cách hiển thị khi bật quiet có thể ảnh hưởng console, nên tập trung vào giá trị thực được đánh giá.

Một property được đánh giá đúng chưa chứng minh plugin sử dụng nó. Để chẩn đoán đầu ra của chương trình, hãy đối chiếu `help:evaluate` → `effective-pom` → file `target/classes/build.properties` → Java runtime như ở ví dụ.

## 11. Phân biệt effective POM và effective settings

Một lỗi thường gặp: effective POM đã đúng nhưng Maven vẫn lấy artifact từ repository khác hoặc dùng credentials không mong đợi. Nguyên nhân có thể nằm ở **settings**, không chỉ POM.

- `help:effective-pom` giải thích **mô hình project**: properties, dependencies, build, plugin, profile effects...
- `help:effective-settings` giải thích **settings được hợp nhất**: mirrors, servers, proxies, activeProfiles và cấu hình từ user/global settings.

Lệnh:

~~~bash
mvn help:effective-settings
~~~

Nếu dùng một settings file riêng cho CI:

~~~bash
mvn -s path/to/ci-settings.xml help:effective-settings
mvn -s path/to/ci-settings.xml -Pci help:active-profiles
mvn -s path/to/ci-settings.xml -Pci help:effective-pom -Doutput=effective-with-ci-settings.xml
~~~

Với ba lệnh này, Maven được yêu cầu dùng **cùng user settings**. Nếu không truyền `-s` khi chẩn đoán mà CI đã truyền, kết quả so sánh có thể đánh lạc hướng.

**Bảo mật:** `effective-settings` và file `settings.xml` có thể chứa repository nội bộ, server ID, tên tài khoản và dữ liệu nhạy cảm. Một số phiên bản Help Plugin mặc định che password, nhưng **không thể mặc nhiên coi toàn bộ output là an toàn để công khai**. Đừng bật `showPasswords=true`, đừng gửi nguyên file settings và đừng dán token trong log. Nếu cần hỗ trợ, chỉ chia sẻ phần đã được rà soát, che host/path/credential khi chúng thuộc thông tin riêng.

## 12. Các kiểu kích hoạt profile cần rà soát

`help:active-profiles` cho biết kết quả; để hiểu **vì sao** profile active, phải xem điều kiện activation và môi trường.

### 12.1. Theo JDK

Đoạn profile minh họa **không phải một file POM đầy đủ**:

~~~xml
<profile>
    <id>jdk17plus</id>
    <activation>
        <jdk>[17,)</jdk>
    </activation>
    <properties>
        <build.jdk.group>modern</build.jdk.group>
    </properties>
</profile>
~~~

Range `[17,)` nghĩa là JDK 17 trở lên. Để kiểm tra JDK đang chạy Maven, xem `mvn -version`; `JAVA_HOME`, Maven Toolchains và JDK dùng để chạy compiler có thể tạo ra sự khác biệt cần phân tích. Activation theo `jdk` xét JDK chạy Maven, không phải chỉ mức `maven.compiler.release` trong POM.

### 12.2. Theo OS

~~~xml
<profile>
    <id>windows-only</id>
    <activation>
        <os>
            <family>Windows</family>
        </os>
    </activation>
    <properties>
        <build.platform>windows</build.platform>
    </properties>
</profile>
~~~

Hãy kiểm tra hệ điều hành và tên profile bằng `mvn -version` cùng `help:active-profiles`. Các môi trường CI Linux/Windows có thể kích hoạt profile khác nhau dù POM và source code không đổi.

### 12.3. Theo property

~~~xml
<profile>
    <id>run-analysis</id>
    <activation>
        <property>
            <name>analyze</name>
        </property>
    </activation>
    <properties>
        <analysis.enabled>true</analysis.enabled>
    </properties>
</profile>
~~~

Với cấu hình này, `-Danalyze` có thể kích hoạt profile bởi **sự tồn tại** của property, khác với yêu cầu value chính xác `true` trong ví dụ `build.ci`.

Không nên dùng các property do chính POM khai báo bên trong `<properties>` làm cơ chế kích hoạt vòng tròn. Property activation được Maven đánh giá từ những nguồn điều kiện phù hợp ở giai đoạn sớm (như system/CLI property), không phải cứ khai báo một key trong profile rồi profile đó tự bật.

### 12.4. Theo sự tồn tại của file

~~~xml
<profile>
    <id>local-config</id>
    <activation>
        <file>
            <exists>local.build.flag</exists>
        </file>
    </activation>
    <properties>
        <local.config.detected>true</local.config.detected>
    </properties>
</profile>
~~~

Đoạn trên minh họa một file marker mà người dùng tự quản lý. Nếu file có mặt ở nơi Maven đánh giá điều kiện, profile có thể active; nếu không, nó sẽ không active bởi điều kiện ấy. Việc chẩn đoán cần xem đường dẫn tương đối/absolute, cách CI checkout/cleanup, tên file và chính sách file permission. Không suy diễn rằng Maven tự tạo `local.build.flag`.

**Cảnh báo về interpolation khi kích hoạt file:** ở bước kích hoạt profile, nhiều property của POM chưa có sẵn; không nên phụ thuộc vào `${project.build.directory}` trong `<activation><file>` để tính đường dẫn. Khi cần sự ổn định, dùng đường dẫn rõ ràng hoặc nguồn biến mà tài liệu Maven cho phép.

### 12.5. Profile mặc định, nhiều profile và thứ tự khai báo

Nếu profile `local` dùng `activeByDefault=true` rồi `ci` active trong **cùng POM**, profile mặc định bị tắt. Nếu hai profile **cùng active** và cùng đặt một property, Maven có quy tắc thứ tự/ưu tiên riêng cho phần tử khi merge; thứ tự khai báo của profile trong cùng nguồn có thể ảnh hưởng giá trị cuối. Đừng đoán bằng cảm giác “-P đặt sau nên thắng”: hãy kiểm tra `help:active-profiles` và `effective-pom` với cùng lệnh.

Khi nhiều profile active, chúng được **kết hợp** vào mô hình project, không nhất thiết có nghĩa profile sau thay toàn bộ profile trước. Từng loại phần tử (property, plugin, repository) có quy tắc hợp nhất tương ứng.

## 13. Kích hoạt trong settings và sự khác nhau giữa các máy

User settings có thể chứa:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <profiles>
        <profile>
            <id>corp-repo</id>
            <repositories>
                <repository>
                    <id>team-deps</id>
                    <url>https://repo.example.org/repository/internal</url>
                </repository>
            </repositories>
        </profile>
    </profiles>
    <activeProfiles>
        <activeProfile>corp-repo</activeProfile>
    </activeProfiles>
</settings>
~~~

Đây là file **minh họa**; URL `repo.example.org` chỉ đại diện cho repository nội bộ, không thể sử dụng để build thực nếu không thay bằng server hoạt động. Một settings profile có thể thêm repository, pluginRepository và properties theo các phần Maven cho phép. Nó không có toàn bộ khả năng sửa POM như project profile; ví dụ không thể tùy ý nhét một cấu trúc `<build>` hoàn chỉnh vào settings profile theo ý muốn.

Khi máy A dùng user settings chứa profile `corp-repo`, máy B không có, cả hai có thể dùng repository khác nhau dù cùng checkout một commit.

Cách kiểm tra:

~~~bash
mvn help:active-profiles
mvn help:effective-settings
mvn help:effective-pom -Doutput=effective.xml
~~~

Nếu CI có settings riêng, lặp lại với `-s` đúng file. Không giả định file `settings.xml` ở dự án là user settings đang được Maven tự đọc; vị trí mặc định thường là `~/.m2/settings.xml`, trừ khi có `-s`.

## 14. Trong dự án nhiều module: kiểm tra đúng POM

Giả sử:

~~~text
company-project/
├── pom.xml
├── core/
│   └── pom.xml
└── service/
    └── pom.xml
~~~

Parent POM có `<modules>`, mỗi module có thể khai báo parent và profile của riêng mình. Một profile `ci` định nghĩa trong parent **không nhất thiết tồn tại như một profile có thể kích hoạt trong các POM con** chỉ vì các POM đó kế thừa parent. Maven xử lý profile sớm và có thể kế thừa **tác động** của profile active, chứ không kế thừa nguyên khối định nghĩa profile.

Hãy phân biệt hai câu hỏi:

1. “Profile ID `ci` có đang active trong project/module cần kiểm tra không?”
2. “Module `service` cuối cùng có plugin/property gì sau inheritance và profile effects?”

Ví dụ kiểm tra từ project root:

~~~bash
mvn -f service/pom.xml -Pci help:effective-pom -Doutput=service-effective.xml
~~~

Lệnh này chỉ **minh họa chọn đúng POM đích**; cần bảo đảm parent path/dependency có thể resolve, profile `ci` tồn tại trong ngữ cảnh hợp lệ và môi trường tương tự build thực tế. Khi build Reactor với `-pl service` hoặc `-am`, tùy chọn chọn module và profile cũng có thể ảnh hưởng phạm vi; không đánh đồng `help:active-profiles` chạy ở aggregator root với mọi kết quả trong từng module.

Nếu dùng `-f service/pom.xml`, các path `-Doutput=...` và thư mục làm việc cần được kiểm tra thực tế; đừng suy ra vị trí file output từ trực giác khi Maven đổi ngữ cảnh project. Đọc log hoặc chỉ định đường dẫn rõ ràng khi cần.

## 15. Kỹ thuật đối chiếu hai effective POM

Một lỗi phổ biến là “CI có dependency khác local”. Quy trình có thể tái lập:

~~~bash
mvn -B -ntp help:active-profiles -Doutput=profiles-local.txt
mvn -B -ntp help:effective-pom -Doutput=effective-local.xml

mvn -B -ntp -Pci help:active-profiles -Doutput=profiles-ci.txt
mvn -B -ntp -Pci help:effective-pom -Doutput=effective-ci.xml
~~~

Sau đó so sánh:

- **Danh sách ID active** trong `profiles-local.txt` với `profiles-ci.txt`.
- **`<properties>`**: các key liên quan tới Java, dependency/plugin versions và môi trường.
- **`<dependencies>` / `<dependencyManagement>`**: phụ thuộc có được khai báo và version quản lý khác nhau?
- **`<build><plugins>`**: plugin/execution/configuration đã đổi ra sao?
- **`<repositories>` / `<pluginRepositories>`**: có profile nào thêm nguồn tải riêng?
- **`<build><resources>`**: đường dẫn, filtering và delimiter có đổi?
- **`<profiles>`** trong file nguồn: điều kiện kích hoạt có khác với giả định không?

Dùng công cụ diff của hệ điều hành hoặc IDE để so hai XML. Do effective POM có thể bổ sung comment và nhiều mặc định, tập trung vào **phần tử liên quan lỗi**, không đòi hai file phải giống tuyệt đối nếu mục tiêu build khác nhau.

Nếu muốn biết một trường lấy từ đâu, xuất bản verbose:

~~~bash
mvn -B -ntp -Pci help:effective-pom -Dverbose=true -Doutput=effective-ci-verbose.xml
~~~

Một điểm quan trọng: **effective POM chỉ phản ánh mô hình tại lần gọi đó**. Nếu lần build thật có `-DskipTests`, `-Dmaven.compiler.release=21` hoặc Maven `settings.xml` khác, diff ở đây chưa đủ cho kết luận. Ghi lại chính xác toàn bộ yếu tố có thể tác động, nhưng phải che secret trước khi lưu/chia sẻ.

## 16. Cách chẩn đoán từng triệu chứng thường gặp

### 16.1. Lệnh `-Pci` không làm config đổi

1. Chạy `mvn -Pci help:active-profiles` để xác nhận ID.
2. Chạy `mvn help:all-profiles` nếu nghi sai tên profile hoặc profile ở file khác.
3. Mở `effective-ci.xml` để tìm property/plugin thực sự bị thay.
4. Nếu ID active nhưng config không đổi, kiểm tra liệu profile có khai báo phần tử muốn đổi không, có bị profile khác override không, hoặc config có được build/plugin dùng tới không.
5. Kiểm tra command build thật cũng có `-Pci`.

### 16.2. Local dùng `local`, CI lại dùng `ci`

1. So sánh `-P`, `-Dbuild.ci=true`, environment và settings.
2. Kiểm tra `<activeByDefault>` của `local` và `<activation>` của `ci`.
3. Chạy `help:active-profiles` trong cả hai môi trường, **không chỉ chạy một máy rồi suy ra máy kia**.
4. Xuất effective POM cùng input và so property/plugin liên quan.

### 16.3. Profile active nhưng file JAR vẫn chứa giá trị cũ

1. Đọc `help:effective-pom` để xác nhận property cuối.
2. Chạy `mvn clean package` **với đúng các cờ profile** nhằm loại bỏ artifact cũ.
3. Kiểm tra `target/classes/build.properties` là file được filtering.
4. Kiểm tra resource directory, `<filtering>true</filtering>` và delimiter `@...@`.
5. Kiểm tra đúng classpath/JAR đang được chạy; đừng chạy một bản artifact cũ.
6. Xem stdout chương trình; với ví dụ, phải có `banner=CI` khi build `-Pci`.

### 16.4. Dependency hoặc plugin version khác nhau

1. Xem `<properties>`, `<dependencyManagement>` và `<pluginManagement>` ở effective POM.
2. Chú ý parent/BOM và profile trong POM hiện tại hoặc settings.
3. Xác định dependency version **được khai báo** khác với dependency version cuối **được resolve**. Khi cần đồ thị thực tế, dùng công cụ như Maven Dependency Plugin `dependency:tree`; chỉ nhìn effective POM không nói hết xung đột dependency transitives.
4. Kiểm tra plugin execution thật qua build log và report tương ứng.

### 16.5. Profile theo JDK hoặc OS bật sai

1. Chạy `mvn -version` trong chính shell/container/runner gặp lỗi.
2. Đối chiếu `<activation><jdk>` hoặc `<activation><os>` với thông tin thật.
3. Đừng giả định `<maven.compiler.release>17</maven.compiler.release>` làm profile `<jdk>[17,)</jdk>` active nếu Maven đang chạy dưới một JVM khác.
4. Nếu Toolchains được dùng, kiểm tra cả JDK dùng để build theo toolchain và JVM chạy Maven.

### 16.6. Mirror và repositories khó hiểu

1. Xem `help:effective-pom` để biết repositories được mô hình project đóng góp.
2. Xem `help:effective-settings` để biết mirrors, activeProfiles, servers và proxy ở cấu hình môi trường.
3. Nhớ mirror có thể thay đổi nơi request thực sự đi tới, dù effective POM vẫn hiển thị repository gốc.
4. Kiểm tra trong log đã che dữ liệu nhạy cảm, repository ID nào được chọn.
5. Không tự sửa credential hoặc tắt TLS khi chưa xác định rõ nguyên nhân.

## 17. Phân biệt “có profile”, “profile active” và “kết quả đã áp dụng”

Ba mức xác minh thường bị trộn lẫn:

| Mức | Bằng chứng chính | Điều chưa chắc |
| --- | --- | --- |
| **Được khai báo** | Có phần tử `<profile><id>ci</id>` hoặc `help:all-profiles` liệt kê | Chưa biết profile đang active |
| **Đã kích hoạt** | `help:active-profiles` liệt kê `ci` | Chưa biết property/plugin cuối bị override như thế nào |
| **Đã góp vào mô hình hiệu lực** | `effective-pom` có cấu hình mong đợi | Chưa biết goal đã chạy hoặc artifact runtime chứa đúng giá trị |
| **Đã được thực thi/đóng gói** | Build log, test report, filtered resources, artifact thực tế | Chưa chứng minh mọi kịch bản production đều đúng |

Khi debug, nên đi theo đúng thứ tự. Nếu chỉ nhìn POM nguồn mà bỏ qua active-profiles, rất dễ quy lỗi cho một profile thực tế chưa bao giờ được kích hoạt. Nếu chỉ nhìn active-profiles mà không xem effective-pom, lại không biết trường nào đang thắng khi nhiều profile cùng góp cấu hình.

## 18. Những lỗi phổ biến và cách tránh

| Lỗi suy luận | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| “Profile có trong POM nên đã bật” | Profile có thể inactive | `help:active-profiles` |
| “`activeByDefault` chắc chắn luôn bật” | Bị tắt khi profile khác trong cùng POM active | Xem activation + kết quả thực tế |
| “Chạy Help Plugin một lần sẽ nhớ profile cho các lệnh sau” | `-P`/`-D` chỉ áp dụng cho invocation đó | Truyền đủ cờ ở từng lần chạy |
| “Effective POM là POM gốc cần commit lại” | Là output hợp nhất dùng để chẩn đoán | Giữ POM nguồn, sửa đúng phần cần thiết |
| “Effective POM giống nhau thì build chắc chắn giống nhau” | JDK, settings, environment, CLI và repositories còn ảnh hưởng | Ghi nhận đầy đủ điều kiện |
| “`help:active-profiles` cho biết plugin nào đã chạy” | Nó chỉ liệt kê profile active | Xem build log/executions |
| “Profile parent được con kế thừa nguyên định nghĩa” | Maven chỉ có thể kế thừa tác động profile đã áp dụng | Xem effective POM module con |
| “`-Dbuild.ci=false` vẫn kích hoạt điều kiện `value=true`” | Điều kiện có so khớp giá trị | Xem activation XML |
| “Resource tự thay nếu `app.banner` đúng” | Resource cần filtering phù hợp | Xem `<resources>` và `target/classes` |
| “Có thể gửi nguyên effective settings khi hỏi lỗi” | Output có thể chứa dữ liệu riêng | Rà soát và ẩn trước khi chia sẻ |

Một lỗi tinh vi khác là **profile ID trùng nhau ở các nguồn khác nhau**. Đừng kết luận theo tên ID: profile settings và profile project không có cùng khả năng khai báo mọi trường; cần xem nguồn và hiệu quả cuối trong model.

## 19. Quy trình chẩn đoán chuẩn cho một lỗi build liên quan profile

Có thể dùng quy trình sau trong buổi pair programming hoặc khi điều tra CI:

1. **Ghi nhận triệu chứng cụ thể:** module, file output, plugin, dependency hoặc test nào khác kỳ vọng.
2. **Chốt bối cảnh:** commit/source revision, `mvn -version`, Maven Wrapper (nếu có), working directory, `-f`, `-pl`, `-am`, `-P`, `-D` và `-s`.
3. **Xác định profile active:** chạy `help:active-profiles` với **đúng** các cờ của lần build lỗi.
4. **Xác định profile sẵn có:** dùng `help:all-profiles` nếu cần.
5. **Tìm cấu hình cuối:** chạy `help:effective-pom -Doutput=...`, thêm `-Dverbose=true` nếu cần truy nguồn.
6. **Đánh giá key cụ thể:** dùng `help:evaluate` nếu một property là trọng tâm.
7. **Kiểm tra settings nếu repository/credential/mirror liên quan:** dùng `help:effective-settings` một cách bảo mật.
8. **Đối chiếu với build thật:** xem plugin execution, test report, filtered file và artifact. Không chỉ dựa vào mô hình.
9. **Sửa nguyên nhân tại nguồn:** profile activation, property, parent, plugin configuration, settings hoặc lệnh CI.
10. **Chạy lại cùng điều kiện:** bảo đảm kết quả đã thay đổi ở cả hai lớp — model và output thực tế.

Mẫu lệnh với project ví dụ, khi vấn đề xảy ra ở profile `ci`:

~~~bash
mvn -version
mvn -B -ntp -Pci help:active-profiles -Doutput=profiles-ci.txt
mvn -B -ntp -Pci help:effective-pom -Dverbose=true -Doutput=effective-ci.xml
mvn -q -Pci help:evaluate -Dexpression=app.mode -DforceStdout
mvn -B -ntp -Pci clean package
java -cp target/classes example.ProfileApp
~~~

Đặt file chẩn đoán ngoài thư mục bị `clean` xóa nếu muốn giữ chúng sau khi build. `-B` là batch mode, `-ntp` tắt tiến độ truyền tải; chúng không chọn profile thay cho `-P`.

## 20. Giới hạn và an toàn khi dùng công cụ chẩn đoán

`help:effective-pom` có thể phát sinh XML lớn; `help:effective-settings` có thể chứa repository/mirror hostname, user name và cấu hình riêng. Trong tổ chức có hạ tầng nội bộ:

- Chỉ chia sẻ **đoạn phù hợp** với lỗi, không dán toàn bộ file nếu không cần.
- Che URL/token, đường dẫn nội bộ, username và dữ liệu nhạy cảm theo chính sách.
- Không bật flag hiển thị password trong các công cụ settings.
- Nếu phải dùng `-X`, nhớ log debug có thể lộ thông tin hơn log thường; rà soát trước khi gửi.
- Không commit các file `effective-*.xml` hoặc settings dump do CI tạo, trừ khi đã chắc chắn nội dung được phép công bố.
- Tránh đưa secret vào đối số `-Dsecret=...` vì có thể lộ qua shell history, process list và log.
- Hãy coi outputs chẩn đoán là snapshot của **lần gọi Maven cụ thể**, không phải chứng nhận cấu hình của mọi lần chạy sau đó.

Với profile mới không tìm thấy, Maven 4 có quy tắc chặt hơn về yêu cầu `-P` tới một ID không thể resolve; nó có cơ chế đánh dấu profile tùy chọn bằng dấu `?` trong danh sách ID. Không mang cú pháp này sang mọi bản Maven 3 rồi giả định hỗ trợ giống hệt. Khi điều tra, xem chính phiên bản Maven đang chạy và tài liệu tương ứng.

## 21. Câu hỏi tự kiểm tra

1. **Lệnh nào giúp biết profile `ci` có thực sự bật?** `mvn -Pci help:active-profiles`.
2. **Muốn biết `app.mode` hiệu lực là `local` hay `ci`, dùng gì?** `help:effective-pom` hoặc `help:evaluate -Dexpression=app.mode` với cùng cờ build.
3. **Vì sao `local` active-by-default tắt khi chạy `-Pci`?** Vì một profile khác trong cùng POM đã active.
4. **Lệnh `-Dbuild.ci=true` khác `-Pci` thế nào?** Lệnh đầu tạo user property đáp ứng điều kiện activation; lệnh sau yêu cầu bật profile theo ID.
5. **Vì sao chạy `mvn -Pci help:active-profiles` rồi `mvn package` vẫn ra `LOCAL`?** Lần package không truyền `-Pci`, nên trở lại activation mặc định.
6. **`effective-pom` có cho biết một goal test đã thực thi hay chưa?** Không đầy đủ; phải xem log và report.
7. **Có nên chẩn đoán CI bằng settings local khi CI dùng `-s ci-settings.xml`?** Không; cần dùng cùng settings để tái hiện.
8. **Vì sao Java in `banner=CI` sau `-Pci clean package`?** Maven filtering đã thay `@app.banner@` trong resource trước khi Java đọc từ classpath.
9. **Profile được định nghĩa ở parent có tự trở thành định nghĩa profile của mọi module con?** Không; Maven áp dụng profile sớm và chỉ các tác động phù hợp được kế thừa.
10. **Khi `help:active-profiles` đúng nhưng artifact sai, bước tiếp theo?** Kiểm tra effective POM, resource filtering, plugin execution, đúng JAR/classpath và build lại với cùng cờ.

## 22. Checklist trước khi kết luận nguyên nhân

- [ ] Đã kiểm tra `mvn -version`, JDK, working directory, project/module và lệnh thật.
- [ ] Đã liệt kê profile active với `help:active-profiles` ở đúng ngữ cảnh.
- [ ] Nếu thiếu profile, đã xem `help:all-profiles` và điều kiện activation.
- [ ] Đã xuất `help:effective-pom` với cùng `-P`, `-D`, `-s` và xem các phần tử liên quan.
- [ ] Khi cần truy nguồn parent/profile, đã bật `-Dverbose=true` cho Help Plugin hỗ trợ.
- [ ] Đã phân biệt POM profile, settings profile và chỉ các **tác động** được kế thừa.
- [ ] Đã kiểm tra giá trị cụ thể bằng `help:evaluate` khi phù hợp.
- [ ] Đã so sánh settings hiệu lực nếu có mirror/repository/credential.
- [ ] Đã xác nhận goal/build thật chạy và artifact/resource/test report mới.
- [ ] Không chia sẻ secret hoặc toàn bộ output nội bộ không cần thiết.
- [ ] Đã sửa đúng nguồn cấu hình và chạy lại trong điều kiện tái hiện.

## Tài liệu chính thức

- [Apache Maven Help Plugin — active-profiles](https://maven.apache.org/plugins/maven-help-plugin/active-profiles-mojo.html): goal liệt kê profile active, tham số `output`.
- [Apache Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html): effective POM, `output`, `verbose` và nguồn phần tử.
- [Apache Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html): nguồn profile, activation, inheritance, activeByDefault và lưu ý nhiều profile.
- [Apache Maven Help Plugin — Plugin Details](https://maven.apache.org/plugins/maven-help-plugin/plugin-info.html): vai trò `active-profiles`, `all-profiles`, `effective-pom`, `effective-settings`, `evaluate`.
- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html): project model, inheritance và cách Maven hình thành POM hiệu lực.
- [Apache Maven — Guide to Filtering Resources](https://maven.apache.org/guides/mini/guide-filtering-resources.html): đưa property build vào tệp resource có kiểm soát.

**Ghi nhớ:** `help:active-profiles` trả lời **“Maven đã bật những profile nào?”**; `help:effective-pom` trả lời **“Các profile đó cùng parent/defaults tạo ra cấu hình project cuối như thế nào?”**. Muốn chẩn đoán hoàn chỉnh, hãy đối chiếu tiếp với **lệnh build thật, report và artifact thực tế** — luôn sử dụng cùng bối cảnh môi trường ở mọi bước.
