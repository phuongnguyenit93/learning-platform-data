# Các thuộc tính project, settings và biến môi trường env trong Maven

## 1. Mục tiêu: hiểu Maven lấy giá trị từ đâu

Khi đọc **pom.xml**, bạn thường gặp các biểu thức như **${project.version}**, **${settings.localRepository}** hoặc **${env.JAVA_HOME}**. Dấu **${...}** là cú pháp tham chiếu giá trị trong những ngữ cảnh Maven có hỗ trợ nội suy (interpolation). Chúng giúp dùng lại dữ liệu từ mô hình dự án, cấu hình Maven hoặc môi trường đang chạy mà không phải gõ lại nhiều lần.

Ba nhóm trong bài có nguồn khác nhau:

- **project.\***: lấy giá trị từ **Project Object Model (POM)** đã được Maven dựng cho module, bao gồm giá trị mặc định và giá trị có thể được kế thừa hoặc chịu ảnh hưởng của profile.
- **settings.\***: lấy giá trị từ **cấu hình Maven hiệu lực** (settings), chẳng hạn repository cục bộ hoặc trạng thái offline.
- **env.\***: lấy **biến môi trường** của tiến trình hệ điều hành dùng để khởi chạy Maven; không phải property tự định nghĩa trong POM.

Ngoài ra còn có thuộc tính không có prefix như **${build.stage}**, thuộc tính hệ thống Java như **${user.home}**, và **user properties** được truyền bằng tham số **-Dkey=value**. Phân biệt các loại này giúp xử lý đúng lỗi "không tìm thấy property", sai đường dẫn, khác biệt giữa local và CI, và cấu hình bị vô tình ghi đè.

**Điểm quan trọng:** không phải mọi tệp chứa chuỗi **${...}** đều được Maven thay thế. **pom.xml**, **settings.xml**, các file resource và mã Java có **cơ chế xử lý khác nhau**. Muốn thay placeholder trong một resource khi build, cần bật **resource filtering**.

## 2. Bảng tổng quan các nhóm thuộc tính

| Nhóm | Ví dụ | Nguồn giá trị | Dùng để làm gì |
| --- | --- | --- | --- |
| **project.\*** | **${project.groupId}**, **${project.version}**, **${project.build.directory}** | Mô hình POM hiệu lực của module đang build. | Tham chiếu tọa độ, tên artifact, đường dẫn build. |
| **settings.\*** | **${settings.localRepository}**, **${settings.offline}** | Cấu hình Maven settings hiệu lực. | Tham chiếu repository cục bộ, chế độ offline và những trường settings được hỗ trợ. |
| **env.\*** | **${env.JAVA_HOME}**, **${env.CI}** | Biến môi trường của tiến trình Maven. | Dùng thông tin của shell, CI và đường dẫn công cụ đã cấu hình. |
| **Java system properties** | **${user.home}**, **${java.home}** | Thuộc tính JVM/System.getProperties() của tiến trình Maven. | Thông tin người dùng, runtime Java và hệ thống. |
| **POM properties** | **${build.stage}**, **${maven.compiler.release}** | Khối **<properties>** trong POM/parent/profile hiệu lực. | Giá trị do dự án đặt tên và quản lý. |
| **User properties (-D)** | **-Dbuild.stage=ci** | Đối số dòng lệnh Maven. | Tùy biến một lần build hoặc cấu hình CI. |

Ví dụ **${project.version}** là giá trị **version của module** trong model, còn **${java.version}** không phải luôn là một Java system property mặc định; nhiều dự án tự định nghĩa **java.version** trong POM để cấu hình compiler. Với Java runtime, **${java.home}** là system property có sẵn; với version JVM, dùng thông tin thực tế từ **java -version**, **mvn --version** hoặc biểu thức hệ thống phù hợp như **${java.version}** nếu đang xét JVM property, nhưng đừng nhầm nó với khóa POM trùng tên có thể được dự án đặt riêng.

## 3. project.*: đọc dữ liệu của Project Object Model

Mỗi module Maven có POM hiệu lực riêng, được dựng từ POM nguồn, parent, Super POM, dependency/plugin management và các profile đã kích hoạt. Biểu thức dạng **${project.x}** tham chiếu một trường đơn trị phù hợp trong mô hình đó.

Các ví dụ thường dùng:

| Biểu thức | Ý nghĩa điển hình |
| --- | --- |
| **${project.groupId}** | groupId của module; có thể được kế thừa từ parent. |
| **${project.artifactId}** | artifactId của module. |
| **${project.version}** | Version hiệu lực của module; có thể kế thừa. |
| **${project.name}** | Tên hiển thị nếu POM định nghĩa. |
| **${project.packaging}** | Kiểu packaging, ví dụ **jar** hoặc **pom**. |
| **${project.basedir}** | Thư mục gốc của module/POM đang xét. |
| **${project.build.directory}** | Thư mục output build; thường là **target** của module. |
| **${project.build.outputDirectory}** | Output chứa class/resource chính, thường là **target/classes**. |
| **${project.build.finalName}** | Tên cơ sở artifact khi đóng gói; mặc định thường kết hợp artifactId và version. |
| **${project.build.sourceDirectory}** | Thư mục nguồn chính, mặc định **src/main/java**. |

Giả sử POM có:

~~~xml
<groupId>vn.example</groupId>
<artifactId>property-demo</artifactId>
<version>1.0.0</version>
<packaging>jar</packaging>
~~~

thì **${project.groupId} = vn.example**, **${project.artifactId} = property-demo** và **${project.version} = 1.0.0** khi biểu thức được đánh giá trong ngữ cảnh phù hợp. Những đoạn XML ở đây **chỉ là phần tử minh họa**, không phải một POM hoàn chỉnh; mục 9 có ví dụ chạy được.

**Thư mục của module rất quan trọng.** Trong multi-module build, mỗi module con có thể có artifactId/version hoặc đường dẫn target riêng. **${project.basedir}** không mặc nhiên là thư mục gốc của toàn bộ repository. Khi chạy build từ reactor, không nên dùng một output directory của module A để giả định đường dẫn module B.

Maven cũng thường chấp nhận bí danh lịch sử **${pom.version}**, nhưng nên ưu tiên dạng **project.\*** để tên nguồn dễ hiểu và nhất quán.

### Project fields không phải biến môi trường

**${project.version}** được lấy từ Maven model, không phải từ biến môi trường tên **PROJECT_VERSION**. Việc tạo biến môi trường **PROJECT_VERSION** không tự đổi version của POM. Nếu muốn version CI-friendly hay thay đổi version theo quy trình phát hành, cần dùng cơ chế versioning được Maven hỗ trợ và được dự án thiết kế rõ ràng; không tùy tiện thay trường tọa độ bằng một biến môi trường chưa được bảo đảm có giá trị.

## 4. settings.*: cấu hình Maven không thuộc riêng mã nguồn dự án

Maven có cấu hình **settings.xml** dùng cho máy/người dùng/hệ thống build. Với Maven 3.x thường gặp:

- **Global settings**: **${maven.home}/conf/settings.xml** (vị trí cài Maven thực tế có thể khác).
- **User settings**: **${user.home}/.m2/settings.xml**.
- Có thể chọn file khác bằng **-s** (user settings thay thế) hoặc **-gs** (global settings thay thế).

Khi cùng tồn tại, Maven hợp nhất các cấu hình liên quan; **user settings thường ưu tiên** so với global settings tại những mục có xung đột. Maven 4 có thêm một số khả năng quản lý settings theo dự án; cần dùng tài liệu của phiên bản đang chạy khi áp dụng tính năng mới.

**Ví dụ nội dung settings.xml độc lập, tối giản:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <localRepository>${user.home}/.m2/repository</localRepository>
    <offline>false</offline>
</settings>
~~~

Trong file này, **${user.home}** được nội suy từ thuộc tính hệ thống Java. **localRepository** chỉ định nơi Maven lưu dependency/plugin/artifact tải về hoặc cài vào kho cục bộ; **offline** cho biết Maven có chạy ở chế độ không truy cập repository từ xa hay không.

Trong **pom.xml** hoặc ngữ cảnh plugin expression có hỗ trợ, có thể tham chiếu:

- **${settings.localRepository}**: vị trí repository cục bộ hiệu lực;
- **${settings.offline}**: trạng thái offline hiệu lực.

**Không đồng nhất settings với properties do nhóm tự đặt.** Chẳng hạn **${settings.localRepository}** là một trường thuộc settings model, còn **${my.local.repo}** là custom property nếu được định nghĩa riêng. Đừng tự suy ra rằng có thể đặt bất kỳ thẻ XML tự chế nào dưới **<settings>** và truy cập bằng **${settings.tên-thẻ}**.

### Những nơi đặt cấu hình nên nhớ

| Nơi | Phù hợp để chứa |
| --- | --- |
| **pom.xml** | Tọa độ dự án, dependency, plugin, giá trị build có thể chia sẻ. |
| **~/.m2/settings.xml** | Mirror, proxy, server credentials và thông tin máy/người dùng. |
| **settings.xml của CI** | Cấu hình registry/repository theo hạ tầng CI, được cấp bảo mật. |
| **Biến môi trường** | Thông tin tiến trình build và thông số môi trường được cấp từ hệ điều hành/CI. |

Không nên commit file settings chứa username, password, access token hoặc thông tin hạ tầng nhạy cảm vào repository công khai. **settings.xml** không thay thế POM; POM vẫn là mô hình dự án mà Maven build.

## 5. env.*: biến môi trường của tiến trình Maven

Biểu thức **${env.X}** lấy giá trị biến môi trường **X** mà tiến trình Maven nhìn thấy lúc khởi chạy. Ví dụ:

- **${env.JAVA_HOME}**: biến JAVA_HOME nếu môi trường có đặt.
- **${env.PATH}**: đường dẫn tìm chương trình của hệ điều hành.
- **${env.CI}**: biến CI mà nhiều dịch vụ CI tự thiết lập, **không bắt buộc** có trên mọi máy.
- **${env.DEMO_STAGE}**: biến do người dùng tự tạo cho ví dụ.
- **${env.HOME}**: thường có trên Linux/macOS; không nên giả định luôn có với đúng tên trên Windows.

**Biến shell và biến môi trường không giống nhau hoàn toàn.** Trên Linux/macOS, một biến cục bộ của shell có thể **không được truyền tới tiến trình con** nếu chưa export:

~~~bash
DEMO_STAGE=qa
export DEMO_STAGE
mvn help:evaluate -Dexpression=env.DEMO_STAGE -q -DforceStdout
~~~

Khi biến đã được export như trên và Maven Help Plugin hỗ trợ các tùy chọn đã chỉ định, biểu thức được đánh giá thành **qa**. Có thể viết gọn:

~~~bash
export DEMO_STAGE=qa
mvn help:evaluate -Dexpression=env.DEMO_STAGE -q -DforceStdout
~~~

Ở Windows PowerShell:

~~~powershell
$env:DEMO_STAGE = 'qa'
mvn help:evaluate -Dexpression=env.DEMO_STAGE -q -DforceStdout
~~~

Ở Command Prompt (cmd.exe):

~~~bat
set "DEMO_STAGE=qa"
mvn help:evaluate -Dexpression=env.DEMO_STAGE -q -DforceStdout
~~~

Các lệnh trên chỉ đặt biến cho shell/tiến trình liên quan. Cách đặt biến vĩnh viễn hoặc vào CI pipeline tùy hệ điều hành và nhà cung cấp CI.

**Lưu ý chữ hoa/thường:** cú pháp truy cập property của Maven phân biệt hoa/thường. Trên Windows, dù tên biến môi trường được shell đối xử không phân biệt hoa/thường, Maven chuẩn hóa tên env property về chữ hoa nhằm tăng tính nhất quán. Vì vậy ưu tiên **${env.PATH}** thay vì **${env.Path}**. Trên môi trường POSIX, biến môi trường vốn phân biệt hoa/thường; **DEMO_STAGE** khác **demo_stage**.

**Không phải mọi biến thường gặp đều mặc định tồn tại.** JAVA_HOME có thể chưa được đặt ngay cả khi **java** chạy được qua PATH. Nếu cần đường dẫn bắt buộc, kiểm tra và fail sớm trong script/CI thay vì để Maven tiếp tục với placeholder chưa được giải quyết.

## 6. Property trong POM, Java System Properties và tham số -D

Trong POM, dự án có thể khai báo các giá trị tự đặt tên ở **<properties>**:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <build.stage>local</build.stage>
</properties>
~~~

Sau đó dùng **${build.stage}** trong những phần POM/plugin configuration hỗ trợ property interpolation hoặc trong resource đã bật filtering. Những thuộc tính này là **dữ liệu cấu hình của Maven build**, không tự xuất hiện như Java environment variable hoặc Java System property của chương trình được chạy sau khi build.

**Java System Properties** có các khóa như:

- **${user.home}**: home directory của người dùng chạy JVM Maven.
- **${java.home}**: thư mục Java runtime mà JVM đang sử dụng.
- **${os.name}**: tên hệ điều hành theo JVM.

Chúng khác với env variables: **${user.home}** không đồng nghĩa máy nào cũng có **${env.HOME}**; **${java.home}** cũng không luôn giống **${env.JAVA_HOME}** vì JAVA_HOME thường trỏ JDK gốc, còn java.home là vị trí runtime theo JVM.

**User property** có thể truyền vào Maven bằng **-D**:

~~~bash
mvn -Dbuild.stage=ci clean package
~~~

Với resource filtering thông thường, **-Dbuild.stage=ci** có ưu tiên cao hơn **<build.stage>local</build.stage>** trong POM cho khóa tùy biến đó. Điều này hữu ích khi CI cần thay đổi stage của một build mà không sửa POM. **Đừng tổng quát hóa rằng -D tùy ý sẽ ghi đè mọi project field**: biểu thức **project.version** và những trường mô hình có cơ chế riêng; cần dùng kỹ thuật được Maven hỗ trợ khi muốn đổi tọa độ dự án.

Cũng cần phân biệt **-D** là tham số Maven với cấu hình JVM: ví dụ **mvn -Dbuild.stage=ci ...** truyền user property cho Maven; còn **java -Dbuild.stage=ci ...** đặt System property của JVM Java được gọi. Hai thao tác có thể liên quan trong một số plugin nhưng **không tự động là một**.

## 7. Nội suy có giới hạn ngữ cảnh: POM, settings, resources và Java

Mặc dù cùng có cú pháp **${...}**, Maven không xử lý mọi nơi giống nhau.

| Nơi đặt biểu thức | Maven xử lý ra sao? |
| --- | --- |
| **pom.xml** | Maven hỗ trợ nội suy property trong các phần phù hợp của model và plugin configuration; **project**, **settings**, **env**, system và user/POM properties tùy ngữ cảnh. |
| **settings.xml** | Nội suy được **Java system properties** và **env.\***. **Property định nghĩa trong profile settings không được dùng để nội suy chính settings.xml**. |
| **src/main/resources/...** | Resource được copy bình thường **không tự nội suy**. Chỉ thay token khi resource filtering được bật và plugin xử lý. |
| **Java source (.java)** | Trình biên dịch Java **không thay** chuỗi **${project.version}** chỉ vì Maven đang chạy. Cần code generation, filtering có kiểm soát hoặc truyền giá trị runtime theo thiết kế. |
| **Lệnh shell** | Shell dùng cú pháp của riêng nó (**$VAR**, **$env:VAR**, **%VAR%**); **${env.X}** là cú pháp Maven, không phải cú pháp chung cho mọi shell. |
| **Tên file / log / plugin parameter** | Chỉ biểu thức tại vị trí được Maven/plugin hỗ trợ mới được giải quyết; phải kiểm tra cấu hình plugin thực tế. |

**Ví dụ dễ sai:** đặt **${project.version}** trong file **src/main/resources/build-info.properties** rồi chạy **mvn package**, nhưng POM không bật filtering. File đi vào **target/classes** hoặc JAR có thể vẫn chứa nguyên văn **${project.version}**; Java đọc được chuỗi đó nhưng **không biết thay giúp bạn**.

Trong **settings.xml**, cũng không nên viết **${project.version}** để tạo repository path: settings được xử lý ở giai đoạn riêng và tài liệu Maven chỉ bảo đảm nội suy **system properties** và **environment variables** tại đây. Tương tự, một thuộc tính do settings profile cung cấp có thể được đưa vào POM sau khi profile kích hoạt, nhưng không thể dùng property đó để tự tham chiếu và nội suy các trường khác trong cùng settings file.

Nếu giá trị không có hoặc không được giải quyết, cách xử lý tùy nơi sử dụng và plugin. Có thể còn nguyên token, plugin có thể từ chối cấu hình, hoặc build thất bại. **Không dựa vào hành vi placeholder chưa được giải quyết như một giá trị mặc định**.

## 8. Thực hành đọc từng nhóm property bằng Maven Help Plugin

Maven Help Plugin có goal **help:evaluate** để đánh giá expression. Các ví dụ dùng lệnh **mvn** cho máy đã cài Maven. Nếu dự án có Maven Wrapper, thay bằng **./mvnw** trên Linux/macOS hoặc **.\mvnw.cmd** trong PowerShell.

Chạy từ thư mục có POM:

~~~bash
mvn help:evaluate -Dexpression=project.groupId -q -DforceStdout
mvn help:evaluate -Dexpression=project.artifactId -q -DforceStdout
mvn help:evaluate -Dexpression=project.version -q -DforceStdout
mvn help:evaluate -Dexpression=project.build.directory -q -DforceStdout
~~~

Đối với bản demo ở mục 9, ba expression đầu trả về **vn.example**, **property-demo**, **1.0.0** tương ứng. Đường dẫn build phụ thuộc module và máy thực tế, nên **không có một stdout cố định** để sao chép.

Kiểm tra settings model và system property:

~~~bash
mvn help:evaluate -Dexpression=settings.localRepository -q -DforceStdout
mvn help:evaluate -Dexpression=settings.offline -q -DforceStdout
mvn help:evaluate -Dexpression=user.home -q -DforceStdout
mvn help:evaluate -Dexpression=java.home -q -DforceStdout
~~~

Để kiểm tra env, trước tiên **đặt biến trong cùng shell**:

~~~bash
export DEMO_STAGE=qa
mvn help:evaluate -Dexpression=env.DEMO_STAGE -q -DforceStdout
~~~

**-Dexpression** chỉ nhận phần bên trong, chẳng hạn **project.version** — **không cần** thêm dấu **${...}**. Tham số **-q -DforceStdout** giúp lấy giá trị gọn trong các phiên bản Maven Help Plugin có hỗ trợ.

Muốn hiểu parent/profile, dùng:

~~~bash
mvn help:effective-pom -Doutput=effective-pom.xml
mvn help:active-profiles
~~~

Muốn hiểu **settings hiệu lực** sau khi hợp nhất user/global settings:

~~~bash
mvn help:effective-settings
~~~

**Cảnh báo bảo mật:** settings và environment có thể chứa đường dẫn nội bộ hoặc thông tin nhạy cảm. Đừng đưa toàn bộ output **help:system**, **help:effective-settings** hoặc log debug của CI lên kênh công khai mà không kiểm tra và loại bỏ secrets. Một số công cụ có cơ chế che mật khẩu nhưng không nên xem đó là bảo đảm dữ liệu khác đã được an toàn.

## 9. Dự án mẫu Java 17 chạy được: project property và resource filtering

Ví dụ này minh họa rõ ràng một giá trị đến từ **project.\*** và một giá trị do POM hoặc tham số **-D** đặt. Biến môi trường và settings sẽ được kiểm tra bổ sung bằng những lệnh ở mục 10 và 11.

Tạo cấu trúc:

~~~text
property-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── vn/example/props/Main.java
        └── resources/
            └── build-info.properties
~~~

### 9.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>property-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <build.stage>local</build.stage>
    </properties>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>true</filtering>
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
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Ở đây **maven-resources-plugin** xử lý resource của dự án, và **filtering=true** cho phép thay token trong file text. **maven-compiler-plugin** biên dịch Java theo release 17. **maven-jar-plugin** đóng gói JAR. Đây là dự án mẫu chạy được khi Maven có thể tải các plugin và JDK đáp ứng yêu cầu.

### 9.2. src/main/resources/build-info.properties

~~~properties
artifact.id=${project.artifactId}
artifact.version=${project.version}
build.stage=${build.stage}
~~~

Nếu không bật filtering, ba giá trị phía sau dấu **=** sẽ còn nguyên placeholder. Với POM ở mục 9.1, Maven sẽ lọc resource thành **target/classes/build-info.properties**, có nội dung:

~~~properties
artifact.id=property-demo
artifact.version=1.0.0
build.stage=local
~~~

### 9.3. src/main/java/vn/example/props/Main.java

~~~java
package vn.example.props;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws IOException {
        Properties properties = new Properties();

        try (InputStream stream =
                 Main.class.getResourceAsStream("/build-info.properties")) {
            if (stream == null) {
                throw new IOException("Missing build-info.properties");
            }
            properties.load(stream);
        }

        System.out.println("artifact.id=" + properties.getProperty("artifact.id"));
        System.out.println("artifact.version=" + properties.getProperty("artifact.version"));
        System.out.println("build.stage=" + properties.getProperty("build.stage"));
    }
}
~~~

Lớp **Main** không tự đọc **pom.xml**. Nó đọc **resource đã được Maven lọc và đưa vào JAR** từ classpath. Vì các giá trị mẫu chỉ chứa ký tự ASCII, việc dùng **Properties.load(InputStream)** cho file properties này không gặp vấn đề mã hóa ký tự; nếu resource thực tế có Unicode, cần cân nhắc encoding và API đọc phù hợp.

### 9.4. Build và chạy

Từ thư mục gốc **property-demo**:

~~~bash
mvn -B clean package
java -cp target/property-demo-1.0.0.jar vn.example.props.Main
~~~

**Stdout chính xác của riêng lệnh Java thứ hai**:

~~~text
artifact.id=property-demo
artifact.version=1.0.0
build.stage=local
~~~

Bây giờ cho CI đặt giá trị stage khác bằng **user property**:

~~~bash
mvn -B -Dbuild.stage=ci clean package
java -cp target/property-demo-1.0.0.jar vn.example.props.Main
~~~

**Stdout của riêng lệnh Java sau lần build này**:

~~~text
artifact.id=property-demo
artifact.version=1.0.0
build.stage=ci
~~~

Lý do là resource filtering nhận giá trị **build.stage** từ **-Dbuild.stage=ci** thay cho default **local** trong POM. Hai giá trị **project.artifactId** và **project.version** không thay đổi. POM chưa cấu hình **Main-Class** trong manifest, nên ví dụ sử dụng **java -cp ... vn.example.props.Main**, không dùng **java -jar**.

## 10. Kết nối env.* với ví dụ thực hành

Giả sử hệ thống CI cung cấp biến môi trường **DEMO_STAGE=qa**. Có hai hướng sử dụng, cần hiểu rõ khác nhau.

**Cách A — truyền biến môi trường vào user property tường minh (dễ kiểm soát):**

Linux/macOS:

~~~bash
export DEMO_STAGE=qa
mvn -B "-Dbuild.stage=$DEMO_STAGE" clean package
java -cp target/property-demo-1.0.0.jar vn.example.props.Main
~~~

Windows PowerShell:

~~~powershell
$env:DEMO_STAGE = 'qa'
mvn "-Dbuild.stage=$env:DEMO_STAGE" -B clean package
java -cp target/property-demo-1.0.0.jar vn.example.props.Main
~~~

Windows Command Prompt:

~~~bat
set "DEMO_STAGE=qa"
mvn -B -Dbuild.stage=%DEMO_STAGE% clean package
java -cp target/property-demo-1.0.0.jar vn.example.props.Main
~~~

Ở cả ba ví dụ, nếu biến được đặt như trên và build thành công, **dòng cuối của stdout Java là build.stage=qa**. Shell mở rộng biến rồi truyền tham số **-Dbuild.stage=qa** cho Maven. **Đây là một chuyển đổi tường minh**, không phải vì Maven tự suy ra **build.stage** từ **DEMO_STAGE**.

**Cách B — tham chiếu trực tiếp env trong một cấu hình Maven:**

~~~xml
<properties>
    <build.stage>${env.DEMO_STAGE}</build.stage>
</properties>
~~~

Đây chỉ là **đoạn POM thay thế cho khai báo build.stage**, không phải một POM hoàn chỉnh. Maven có thể nội suy biến môi trường khi xử lý property này. **Nhược điểm:** nếu **DEMO_STAGE** không tồn tại thì giá trị có thể không được giải quyết, dẫn tới resource chứa placeholder hoặc plugin từ chối giá trị tùy ngữ cảnh. Vì vậy, với build cần chạy ổn định trên mọi máy, thường tốt hơn nếu POM có default **local** và CI chủ động truyền **-Dbuild.stage=...**.

Không tạo POM khác nhau giữa hai hệ điều hành chỉ để chọn tên biến. Hãy thống nhất một tên chuẩn (ví dụ **DEMO_STAGE**) và kiểm tra cả local/CI trước khi build.

## 11. Property từ profile trong settings.xml: hữu ích nhưng có giới hạn

Một **profile đã kích hoạt trong settings.xml** có thể cung cấp custom property để POM sử dụng. Điều này thường dùng cho các giá trị riêng của máy/người dùng, như nhánh repository hoặc đường dẫn chương trình được cài tại máy.

Ví dụ nội dung **custom-settings.xml** độc lập để minh họa:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <profiles>
        <profile>
            <id>local-channel</id>
            <properties>
                <release.channel>internal</release.channel>
            </properties>
        </profile>
    </profiles>
    <activeProfiles>
        <activeProfile>local-channel</activeProfile>
    </activeProfiles>
</settings>
~~~

Khi Maven dùng file settings trên, profile **local-channel** đang active và property **release.channel** có thể được đưa vào không gian property khi nội suy POM. Một plugin trong POM có thể tham chiếu **${release.channel}** nếu thiết kế yêu cầu.

Kiểm tra mà không cần sửa POM:

~~~bash
mvn -s custom-settings.xml help:active-profiles
mvn -s custom-settings.xml help:evaluate -Dexpression=release.channel -q -DforceStdout
~~~

Với profile đang active như ví dụ, expression **release.channel** sẽ cho giá trị **internal** trong ngữ cảnh phù hợp.

**Giới hạn rất dễ nhầm:** dù **release.channel** được cung cấp cho POM, **không được dùng ${release.channel} để nội suy các trường khác của chính settings.xml**. Maven Settings Reference nêu rõ property định nghĩa trong settings profiles không dùng để interpolate settings file. Muốn đặt một đường dẫn trong settings.xml có placeholder, ưu tiên system property như **${user.home}** hoặc environment property như **${env.MAVEN_REPO}** (với điều kiện biến này đã tồn tại).

**Khác biệt giữa hai cách đặt tên:**

- **${settings.localRepository}**: đọc một trường thuộc settings model.
- **${release.channel}**: đọc custom property mà profile settings đã kích hoạt đưa vào POM.
- **${settings.release.channel}**: **không** phải tự động là cách đọc custom property ở ví dụ trên.

Nếu giá trị có ảnh hưởng trực tiếp tới tính tái lập của artifact hoặc behavior quan trọng của ứng dụng, nên cân nhắc đặt chính sách trong POM/parent và truyền giá trị CI minh bạch, thay vì phụ thuộc hoàn toàn vào settings riêng của từng người.

## 12. Kế thừa, profile và ưu tiên giá trị

Khi một tên property được định nghĩa ở nhiều nơi, phải xem **ngữ cảnh** và **bước xử lý** thay vì ghi nhớ một quy tắc ưu tiên tuyệt đối cho mọi biểu thức.

**Trong resource filtering** thông thường, property từ dòng lệnh **-D** có ưu tiên cao hơn POM property cùng tên. Maven Resources Plugin cũng có thể dùng system properties và filter files, với thứ tự ưu tiên cụ thể theo tài liệu plugin.

**Trong POM**: mô hình sau kế thừa có thể nhận property từ parent, rồi child/profile cung cấp giá trị hiệu lực. Tài liệu Maven mô tả interpolation xảy ra sau inheritance: nếu parent tham chiếu một variable mà child định nghĩa lại, giá trị child có thể là giá trị được áp dụng trong mô hình cuối.

**Trong settings**: global/user settings được hợp nhất, user settings thường chiếm ưu tiên trong các trường xung đột, nhưng cách merge của từng phần tử như mirror, server, profile không nên suy đoán chỉ bằng cách nhìn hai file rời rạc.

**Với env.\***: giá trị đến từ môi trường của tiến trình Maven, không tự động là project property có cùng tên. Dùng **${env.DEMO_STAGE}** khác với **${DEMO_STAGE}** và khác với **${build.stage}**.

**Với project.\***: các trường thuộc Maven model được đánh giá qua cơ chế dự án, không nên mặc định **-Dproject.version=...** sẽ thay hợp lệ version artifact được phát hành.

Để truy tìm giá trị cuối cùng, hãy dùng **help:evaluate**, **help:effective-pom**, **help:effective-settings**, **help:active-profiles** và đọc log Maven tương ứng. Trong CI, chạy bằng cùng POM, Maven/JDK và profile với môi trường thực tế.

## 13. Các lỗi thường gặp và cách chẩn đoán

### 13.1. Placeholder không được thay trong resource

**Triệu chứng:** file **target/classes/build-info.properties** vẫn ghi **${project.version}**.

**Nguyên nhân thường gặp:** resource filtering chưa bật, file không nằm trong resource directory được plugin xử lý, cú pháp token sai, hoặc property không tồn tại.

**Cách kiểm tra:** xác nhận **<filtering>true</filtering>** trong cấu hình resource, chạy **mvn clean process-resources**, xem file đã sinh trong **target/classes**. Đừng sửa trực tiếp file trong target, vì Maven sẽ ghi lại ở build sau.

### 13.2. Expression env không có giá trị trên CI hoặc Windows

**Triệu chứng:** **${env.DEMO_STAGE}** không được giải quyết.

**Kiểm tra:** biến có được export/khai báo ở **đúng tiến trình chạy Maven** hay không; trong Windows, dùng tên env property chuẩn hóa chữ hoa. Kiểm tra **${env.DEMO_STAGE}** bằng Maven Help Plugin. Một biến ở terminal A không mặc nhiên có trong terminal B, container, IDE hoặc runner CI.

### 13.3. Nhầm user.home với HOME/JAVA_HOME

**Triệu chứng:** repository cục bộ hoặc tool path khác dự đoán.

**Kiểm tra:** **${user.home}** và **${java.home}** từ JVM, so với **${env.HOME}** hoặc **${env.JAVA_HOME}** do shell cung cấp. Chúng có thể khác nhau; đừng nối đường dẫn thủ công nếu Maven có sẵn biểu thức thích hợp.

### 13.4. Dùng property trong settings.xml mà Maven không hiểu

**Triệu chứng:** trong settings.xml viết **${project.version}** hoặc **${release.channel}** và giá trị không được nội suy.

**Giải thích:** settings.xml chỉ hỗ trợ nội suy system properties và environment variables theo tài liệu Settings Reference. Một property do settings profile định nghĩa có thể dùng trong POM sau khi kích hoạt, **không** dùng để nội suy chính settings.

### 13.5. Dùng -D không thay đổi kết quả như mong đợi

**Kiểm tra:** khóa truyền qua **-D** có trùng đúng tên custom property trong POM/resource không, script shell có mở rộng/escape tham số đúng không, và plugin có nhận user property đó không. Phân biệt **${build.stage}** với **${project.version}** hoặc một tham số plugin tự định nghĩa.

### 13.6. Profile hoạt động khác giữa local và CI

**Kiểm tra:** **mvn help:active-profiles**, tham số **-P**, điều kiện kích hoạt profile, user/global settings và file settings được truyền bằng **-s**. So sánh effective POM của hai môi trường **sau khi loại bỏ dữ liệu nhạy cảm**.

### 13.7. Biên dịch Java thành công nhưng chương trình không thấy property

**Nguyên nhân:** Maven property không tự biến thành Java System property hoặc environment variable của chương trình. Nếu cần đọc runtime, hãy chủ động đưa cấu hình vào resource đã lọc, truyền **java -D...**, environment của runtime hoặc cơ chế cấu hình ứng dụng. Ví dụ mục 9 chọn resource filtering.

### 13.8. Lọc nhầm ảnh hoặc file nhị phân

**Triệu chứng:** hình ảnh, file nén hoặc certificate bị hỏng sau khi build.

**Nguyên nhân:** bật filtering cho mọi resource, kể cả tệp nhị phân. Maven Resources Plugin có cơ chế loại trừ định dạng nhị phân, nhưng cấu hình rộng vẫn dễ gây lỗi. Nên tách các tệp text cần lọc khỏi file binary; đừng đặt credentials vào resource đóng gói.

### 13.9. Thấy khác nhau giữa POM và giá trị dùng thực tế

**Cách kiểm tra:** parent, profile, filter files, **-D**, settings hiệu lực, system property và env. Chạy **help:evaluate** với biểu thức cụ thể rồi so với kết quả resource sau filtering, thay vì suy đoán từ một đoạn POM duy nhất.

## 14. Bảo mật và tính tái lập

Các biểu thức property giúp tái sử dụng giá trị nhưng cũng dễ dẫn tới rò rỉ:

- **Không ghi secret vào POM**, file resource được đóng JAR, log plugin hoặc output của **help:system**.
- **Không log toàn bộ environment** trong CI khi có token/password. Một biến môi trường không tự trở thành an toàn chỉ vì không nằm trong file.
- **Không mặc định dùng settings.xml làm kho cấu hình ứng dụng**. Settings phù hợp với hạ tầng Maven như mirror, repository credentials, proxy; business configuration cần cơ chế ứng dụng phù hợp.
- **Không để build phụ thuộc vào property cá nhân khó tái tạo** mà không có tài liệu hoặc kiểm tra. Cần có default an toàn, yêu cầu rõ ràng với CI hoặc bước validation.
- **Pin Maven/JDK/plugin version** phù hợp khi tính nhất quán quan trọng. Hai máy đọc cùng POM nhưng khác Maven/JDK, profile, settings, environment vẫn có thể cho kết quả build khác nhau.
- **Không sử dụng resource filtering một cách vô điều kiện** cho cấu hình bí mật hoặc tệp binary. Giá trị đã lọc có thể nằm trong **target/** và artifact phát hành.

Có thể kiểm tra sau build rằng file JAR chứa **build-info.properties** mong muốn mà **không chứa** credential, token hay dữ liệu chỉ dành cho CI. Nếu cần bí mật ở runtime, dùng cơ chế secret management của môi trường triển khai thay vì đóng sẵn vào artifact.

## 15. Checklist khi đọc một biểu thức Maven

Khi gặp một token **${...}**, hãy tự hỏi:

1. **Prefix là gì?** **project**, **settings**, **env**, system property hay custom property?
2. **Biểu thức nằm ở đâu?** POM, plugin configuration, settings.xml, resource đã bật filtering hay chuỗi Java thường?
3. **Giá trị thực đến từ đâu?** POM/parent, user settings, shell/CI, JVM, profile hay tham số **-D**?
4. **Giá trị có mặt trong đúng môi trường không?** Kiểm tra module, user, Maven/JDK, active profile và biến đã export.
5. **Có bước interpolation/filtering thật sự không?** Nếu không, placeholder chỉ là văn bản.
6. **Có dữ liệu nhạy cảm hoặc khác biệt giữa local và CI không?** Tránh log/đóng gói secrets; kiểm tra bằng các lệnh đánh giá cụ thể.
7. **Nếu thiếu giá trị, hành vi mong muốn là gì?** Thiết lập default an toàn hoặc từ chối build rõ ràng; không dựa vào token chưa được thay.

**Ghi nhớ:** **${project.*}** nói về **dự án/module Maven**, **${settings.*}** nói về **cấu hình Maven hiệu lực**, và **${env.*}** nói về **môi trường tiến trình chạy Maven**. Ba nguồn này cùng phục vụ cấu hình build nhưng không thể hoán đổi cho nhau. Khi biết rõ nguồn, ngữ cảnh và cơ chế nội suy, việc debug một POM trở nên dễ kiểm chứng thay vì đoán mò.

### Tài liệu tham khảo chính thức

- [Apache Maven — Introduction to the POM, Project Interpolation and Variables](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven — Example: Injecting POM Properties via Settings](https://maven.apache.org/examples/injecting-properties-via-settings.html)
- [Apache Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)
- [Apache Maven — Guide to Filtering Resources](https://maven.apache.org/guides/mini/guide-filtering-resources.html)
- [Maven Help Plugin — Usage](https://maven.apache.org/plugins/maven-help-plugin/usage.html)
