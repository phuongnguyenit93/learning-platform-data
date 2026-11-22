# `install-file` và `deploy-file` cho thư viện chưa có quy trình phát hành Maven chuẩn

## 1. Tình huống: bạn có một JAR, nhưng Maven không tìm được artifact

Một dự án Java 17 dùng một thư viện cũ của nhà cung cấp. Nhà cung cấp gửi `vendor-greeter-1.0.0.jar` qua kênh được công ty cho phép, nhưng không có artifact trên Maven Central, không có Maven repository công khai và chưa có pipeline CI/CD chính thức tạo/publish thư viện ấy.

Nếu thêm vào `pom.xml`:

~~~xml
<dependency>
    <groupId>com.acme.legacy</groupId>
    <artifactId>vendor-greeter</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Maven sẽ tìm artifact có tọa độ `com.acme.legacy:vendor-greeter:1.0.0` trong những repository được cấu hình. Maven **không tự quét thư mục Downloads hoặc `lib/` trong project** để ghép file JAR bất kỳ với một dependency declaration.

Đó là lúc hai goal được dùng **như giải pháp có kiểm soát cho một artifact ngoại sinh**:

- **`install:install-file`** của Maven Install Plugin: cài file JAR/POM đã có vào **local Maven repository** của môi trường đang chạy.
- **`deploy:deploy-file`** của Maven Deploy Plugin: đưa file JAR/POM đã có lên **một Maven repository đích**, thường là repository manager nội bộ, để các máy build khác có thể resolve.

Hai goal này giải quyết **vấn đề phân phối artifact**, không tự biên dịch/test nguồn của thư viện, không bảo đảm tương thích nhị phân, không cấp quyền sở hữu bản quyền và không tự kiểm tra malware/CVE. Chúng cũng không thay thế một pipeline phát hành chuẩn nếu nhóm có quyền sửa source và triển khai CI/CD.

Mục tiêu của bài: hiểu khi nào dùng từng goal, tạo tọa độ Maven đúng, xử lý POM/transitive dependencies, làm một bài lab Java 17 chạy được từ JAR tạo thủ công, thử publication vào `file://` repository cục bộ, và biết điều kiện an toàn trước khi công bố lên repository nội bộ.

## 2. So sánh các cách cung cấp dependency

| Trường hợp | Cách phù hợp | Phạm vi tác động |
| --- | --- | --- |
| Thư viện đã có ở Maven Central | Khai báo `<dependency>` với GAV | Maven tự resolve từ repository được phép |
| Thư viện nằm trong internal Maven repository | Khai báo dependency và repository/mirror | Mọi build được cấp quyền có thể resolve |
| JAR vendor có trên máy developer, thử nghiệm một lần | `install:install-file` | Chỉ local repository của máy đó |
| JAR vendor cần dùng trong CI/team, chưa có pipeline | `deploy:deploy-file` sau review vào hosted repository | Các consumer kết nối repository đích |
| Thư viện do team kiểm soát source và POM | `mvn clean verify` rồi `mvn deploy` | Chuỗi build/test/publish chuẩn |
| Cần build đồng thời các sibling modules | Maven Reactor từ aggregator | Artifact được tạo/resolve trong cùng reactor |
| Đường dẫn JAR vật lý trong source tree | Chỉ khi có policy đặc biệt | Tránh `system`/`systemPath` vì khó tái tạo |

**Không chọn `install-file` là quy trình CI lâu dài** chỉ vì nó làm máy cá nhân “chạy được”. CI agent sạch và đồng nghiệp sẽ không có local artifact này trừ khi provisioning được lặp lại một cách đáng tin.

**Không chọn `deploy-file` chỉ để thử một thư viện trên máy mình.** Deployment là hành động công bố artifact tới một repository; có thể ảnh hưởng người khác, snapshots/releases, audit và quyền sử dụng nội dung.

## 3. GAV, type và classifier: Maven quản lý artifact bằng tọa độ

Maven thường định danh dependency bằng:

~~~text
groupId:artifactId:version[:type[:classifier]]
~~~

Ví dụ:

~~~text
com.acme.legacy:vendor-greeter:1.0.0:jar
~~~

Từ đó, Maven repository layout mặc định tương ứng:

~~~text
com/acme/legacy/vendor-greeter/1.0.0/
    vendor-greeter-1.0.0.jar
    vendor-greeter-1.0.0.pom
~~~

Mỗi thành phần có vai trò:

- `groupId`: namespace của tổ chức hoặc nhóm sở hữu artifact, ví dụ `com.acme.legacy`.
- `artifactId`: tên module/library, ví dụ `vendor-greeter`.
- `version`: phiên bản **thực sự** của binary, ví dụ `1.0.0`.
- `packaging`/`type`: thường là `jar` cho Java library, nhưng có thể là `pom`, `war`, `zip` tùy mục tiêu.
- `classifier`: nhãn cho artifact phụ như `sources`, `javadoc`, `tests`, `linux-x86_64`.

**Đừng đổi version một cách tùy tiện để che khác biệt bytes.** Nếu vendor cung cấp bản vá mới, nên định danh release mới rõ ràng. Ghi đè một release artifact cùng GAV nhưng nội dung khác phá tính có thể tái tạo và gây cache conflict.

### 3.1. `packaging` khác `classifier`

Main library:

~~~text
com.acme.legacy:vendor-greeter:1.0.0:jar
~~~

Sources artifact:

~~~text
com.acme.legacy:vendor-greeter:1.0.0:jar:sources
~~~

Một artifact có classifier `sources` thường **không** phải JAR chứa compiled classes để dùng ở runtime. Nếu vô tình chỉ publish sources JAR vào vị trí main artifact, downstream compiler sẽ không tìm thấy `VendorGreeter.class`.

Khi dùng `install-file`/`deploy-file` cho JAR chính, **không đặt `-Dclassifier=sources`**. Chỉ dùng classifier khi thật sự phát hành artifact thứ cấp.

## 4. `install-file` khác `install` ở đâu?

Maven lifecycle:

~~~bash
mvn clean install
~~~

chạy các phases tới `install`, thông thường gồm compile/test/package rồi **cài artifact do project hiện tại build** vào local repository.

Goal trực tiếp:

~~~bash
mvn org.apache.maven.plugins:maven-install-plugin:3.2.0:install-file ...
~~~

cài **một file đã tồn tại** vào local repository theo GAV và metadata được khai báo. Nó không tự biết source của JAR, không biên dịch Java, không chạy tests của nhà sản xuất và không phát hành lên server.

So sánh:

| | `mvn install` | `install:install-file` |
| --- | --- | --- |
| Nguồn artifact | Project Maven đang build | File JAR/POM có sẵn |
| Biên dịch/test project | Theo lifecycle tới install | Không thực hiện build/test của file nhập |
| Nơi lưu | Local Maven repository | Local Maven repository |
| Dùng khi | Bạn sở hữu project/POM build chuẩn | Artifact bên ngoài chưa có trong repository |
| Hệ quả với CI mới | Dự án có source/pipeline build lại được | Phải cung cấp lại file/provision local repo |

**Phiên bản plugin trong bài** là `maven-install-plugin:3.2.0`. Gọi bằng **fully qualified goal** giúp hành vi ổn định hơn so với viết trần `mvn install:install-file`, nơi plugin version có thể chịu plugin resolution/configuration.

## 5. `deploy-file` khác `deploy` ở đâu?

Maven lifecycle:

~~~bash
mvn clean deploy
~~~

dành cho một Maven project có quy trình build/test/package và cấu hình `distributionManagement` phù hợp; khi tới phase `deploy`, Maven Deploy Plugin công bố project artifacts, POM và attachments vào remote repository đã chọn.

Goal trực tiếp:

~~~bash
mvn org.apache.maven.plugins:maven-deploy-plugin:3.2.0:deploy-file ...
~~~

dành cho **file có sẵn**. Nó cần:

- `-Dfile=...`: đường dẫn file nguồn.
- `-Durl=...`: URL repository nhận.
- `-DrepositoryId=...`: id dùng để tìm credentials trong Maven settings khi cần.
- GAV/packaging hoặc `-DpomFile=...`.
- Quyền deploy phù hợp, đặc biệt với release repository.

**`deploy-file` không tự chạy `clean`, `test` hay `verify` của project đã tạo JAR.** Trước khi công bố phải có quy trình kiểm nguồn, xác minh checksum/signature, license, security và dependency metadata riêng.

Tài liệu hiện hành có Maven Deploy Plugin **3.2.0**; tránh copy nguyên các lệnh của plugin 2.x dùng options/layout đã thay đổi mà không đối chiếu tài liệu tương ứng.

## 6. Local repository và remote repository: hai lớp khác nhau

Ví dụ trên Linux/macOS, local Maven repo mặc định thường là:

~~~text
~/.m2/repository/
    com/acme/legacy/vendor-greeter/1.0.0/
        vendor-greeter-1.0.0.jar
        vendor-greeter-1.0.0.pom
~~~

Trên Windows, local repository mặc định nằm dưới user home tương ứng, thường là:

~~~text
%USERPROFILE%\.m2\repository\
~~~

Có thể cấu hình khác qua Maven settings hoặc một Maven invocation dùng `-Dmaven.repo.local=...`.

Một **remote Maven repository** là endpoint Maven Repository Manager hoặc repository tuân theo Maven layout, ví dụ:

~~~text
https://repository.example.invalid/repository/thirdparty-releases/
~~~

Địa chỉ `.invalid` trên chỉ là **ví dụ không tồn tại**, không thể deploy thực; phải dùng URL nội bộ đã được người quản trị cấp phép. Đừng thử upload artifact vào Maven Central hoặc một repository bất kỳ nếu bạn không sở hữu/quản lý namespace và quyền xuất bản.

### 6.1. `install-file` không giải quyết CI sạch

Nếu cài một JAR vào local repo trên laptop:

~~~text
Laptop A: dependency resolve PASS
Laptop B: artifact missing
CI agent sạch: artifact missing
~~~

Các máy khác không tự nhìn thấy nội dung laptop A. Muốn team dùng lại:

1. Nên có repository manager nội bộ chuẩn (Nexus/Artifactory/managed Maven repository).
2. Publish JAR + POM đã kiểm duyệt vào repository đó.
3. Cấp repository read permissions cho consumers.
4. Cấu hình Maven settings/mirror hoặc `<repositories>` tùy policy.
5. Dùng version bất biến; lưu provenance, checksums và thông tin license.
6. Kiểm từ local repo sạch trước khi chốt rằng artifact đã phân phối thành công.

## 7. Lab Java 17: tạo JAR không có Maven project, rồi cài bằng `install-file`

Để minh họa mà không cần một binary vendor thực hay quyền upload server, ta tự tạo một “thư viện vendor” tối giản bằng `javac`/`jar`. Sau đó giả lập tình huống **chỉ nhận được JAR**, không có Maven POM.

### 7.1. Cấu trúc lab

~~~text
thirdparty-lab/
├── vendor-src/
│   └── com/acme/legacy/
│       └── VendorGreeter.java
├── vendor/                       (JAR được tạo tại đây)
│   └── vendor-greeter-1.0.0.jar
├── build/                        (class output trung gian)
│   └── vendor-classes/...
└── consumer/
    ├── pom.xml
    └── src/
        ├── main/java/com/example/consumer/App.java
        └── test/java/com/example/consumer/AppTest.java
~~~

Folder `vendor/` và `build/` trước tiên có thể chưa tồn tại. **Không commit JAR third-party vào Git chỉ vì lab có folder `vendor/`**; project thực cần policy binary artifact và giấy phép riêng.

### 7.2. Source thư viện giả lập

Tạo `vendor-src/com/acme/legacy/VendorGreeter.java`:

~~~java
package com.acme.legacy;

public final class VendorGreeter {

    private VendorGreeter() {
    }

    public static String hello(String name) {
        String cleaned = name == null ? "" : name.trim();

        if (cleaned.isEmpty()) {
            cleaned = "guest";
        }

        return "Hello, " + cleaned + "!";
    }
}
~~~

Đây là Java 17-compatible code không phụ thuộc library ngoài JDK. `hello(" Maven ")` trả `"Hello, Maven!"`, còn `hello(null)` trả `"Hello, guest!"`. Điều này cho phép test **một behavior cụ thể**, không chỉ xác nhận class tồn tại.

### 7.3. Biên dịch và tạo JAR bằng JDK tools

Đứng trong `thirdparty-lab/`. POSIX shell:

~~~bash
mkdir -p build/vendor-classes vendor
javac --release 17 -d build/vendor-classes vendor-src/com/acme/legacy/VendorGreeter.java
jar --create --file vendor/vendor-greeter-1.0.0.jar -C build/vendor-classes .
jar tf vendor/vendor-greeter-1.0.0.jar
~~~

Trên Windows PowerShell, bước tạo thư mục:

~~~powershell
New-Item -ItemType Directory -Force -Path "build/vendor-classes" | Out-Null
New-Item -ItemType Directory -Force -Path "vendor" | Out-Null
javac --release 17 -d build/vendor-classes vendor-src/com/acme/legacy/VendorGreeter.java
jar --create --file vendor/vendor-greeter-1.0.0.jar -C build/vendor-classes .
jar tf vendor/vendor-greeter-1.0.0.jar
~~~

Danh sách JAR có mục:

~~~text
META-INF/
META-INF/MANIFEST.MF
com/
com/acme/
com/acme/legacy/
com/acme/legacy/VendorGreeter.class
~~~

Output của `jar tf` có thể thay đổi chút ít về thứ tự/entries theo JDK, nhưng phải có **`com/acme/legacy/VendorGreeter.class`**. Đây là bằng chứng JAR chứa compiled class cần dùng; chưa phải bằng chứng class chạy đúng hay JAR an toàn.

### 7.4. Cài JAR vào local Maven repository

Đứng ở `thirdparty-lab/`:

~~~bash
mvn -B org.apache.maven.plugins:maven-install-plugin:3.2.0:install-file -Dfile=vendor/vendor-greeter-1.0.0.jar -DgroupId=com.acme.legacy -DartifactId=vendor-greeter -Dversion=1.0.0 -Dpackaging=jar -DgeneratePom=true
~~~

Phân tích đầy đủ:

| Option | Giá trị | Vai trò |
| --- | --- | --- |
| `-Dfile` | `vendor/vendor-greeter-1.0.0.jar` | File có thật cần cài |
| `-DgroupId` | `com.acme.legacy` | Maven group namespace |
| `-DartifactId` | `vendor-greeter` | Tên artifact |
| `-Dversion` | `1.0.0` | Version của binary được nhập |
| `-Dpackaging` | `jar` | Artifact type/extension |
| `-DgeneratePom` | `true` | Tạo POM tối giản vì vendor không cung cấp |

Sau khi goal hoàn thành, local Maven repository có artifact theo layout GAV. File POM tối giản có thể chỉ mang metadata cần thiết như GAV/packaging; **nó không tự suy ra tất cả transitive dependencies** từ các references trong bytecode.

**Không chạy `mvn clean install` ở folder `thirdparty-lab` để cài vendor JAR.** Folder đó không phải Maven project có POM của vendor. Goal `install-file` nhận **file trực tiếp**.

### 7.5. Vì sao `generatePom=true` chỉ hợp với JAR độc lập hoặc đã kiểm dependency?

`VendorGreeter` trong demo chỉ dùng JDK nên generic POM đủ cho dependency resolution của consumer.

Nhưng trong thư viện thực tế:

~~~text
vendor-analytics.jar
    uses org.slf4j.Logger
    uses com.fasterxml.jackson.databind.ObjectMapper
    uses another-native-library...
~~~

Nếu chỉ publish generic POM với GAV, Maven **không tự nhận ra** vendor JAR còn cần SLF4J, Jackson hoặc native component. Consumer có thể compile hoặc start một phần rồi lỗi:

~~~text
java.lang.NoClassDefFoundError: org/slf4j/Logger
~~~

Giải pháp đúng là **lấy POM chính thức từ nhà cung cấp** khi có, hoặc xây POM mô tả dependency metadata chính xác đã được phê duyệt, test runtime classpath trong clean environment. Không khai báo bừa transitive versions chỉ để Maven không báo `ClassNotFoundException` ở một trường hợp thử.

## 8. Project consumer dùng JAR vừa cài

Sau khi install-file thành công, tạo project Maven có dependency GAV tương ứng. Project này là một ứng dụng **độc lập** với thư viện vendor.

### 8.1. consumer/pom.xml đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>consumer</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>com.acme.legacy</groupId>
            <artifactId>vendor-greeter</artifactId>
            <version>1.0.0</version>
        </dependency>
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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.7.0</version>
                <configuration>
                    <mainClass>com.example.consumer.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Các điểm quan trọng:**

- `com.acme.legacy:vendor-greeter:1.0.0` phải khớp **đúng GAV** mà `install-file` đã sử dụng.
- Scope mặc định là `compile`, phù hợp vì chương trình chạy cần `VendorGreeter`.
- JUnit 5 là dependency `test` riêng, không liên quan tới vendor JAR.
- Compiler plugin 3.13.0 dùng `--release 17` qua property.
- Surefire 3.5.2 chạy JUnit Jupiter ở phase `test`.
- Exec Plugin được chỉ rõ main class và chạy bằng `exec:java` khi gọi CLI.
- Dự án **không dùng** `systemPath` hay tự thêm vendor JAR qua Java compiler classpath.
- `mvn -f consumer/pom.xml clean verify` kiểm ứng dụng với library ở Maven repository; **không build source vendor**.

### 8.2. consumer/src/main/java/com/example/consumer/App.java

~~~java
package com.example.consumer;

import com.acme.legacy.VendorGreeter;

public final class App {

    private App() {
    }

    public static String message(String name) {
        return VendorGreeter.hello(name);
    }

    public static void main(String[] args) {
        System.out.println(message("Maven"));
    }
}
~~~

### 8.3. consumer/src/test/java/com/example/consumer/AppTest.java

~~~java
package com.example.consumer;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {

    @Test
    void greetsNamedCaller() {
        assertEquals("Hello, Linh!", App.message(" Linh "));
    }

    @Test
    void greetsGuestWhenNameMissing() {
        assertEquals("Hello, guest!", App.message(null));
    }
}
~~~

Hai assertions giúp kiểm tra behavior của vendor class từ JAR, bao gồm nhánh tên rỗng/`null`. Điều này **không thay QA/supply-chain audit của thư viện ngoài**, nhưng chứng minh consumer kết nối đúng class và hành vi mẫu.

### 8.4. Build, test, chạy ứng dụng

Đứng tại `thirdparty-lab/`:

~~~bash
mvn -B -f consumer/pom.xml clean verify
mvn -q -f consumer/pom.xml exec:java
~~~

**Stdout của ứng dụng `App`**:

~~~text
Hello, Maven!
~~~

Maven/Exec Plugin có thể in thêm log/diagnostics nếu không dùng chế độ quiet tương ứng, nhưng Java main chỉ in dòng này với một newline cuối.

Expected build behavior:

- Maven resolve `com.acme.legacy:vendor-greeter:1.0.0` từ local repository.
- Compiler tìm `com.acme.legacy.VendorGreeter`.
- Surefire chạy **2 test methods** và kiểm hai expected strings.
- `verify` hoàn thành nếu tests pass.
- Exec Plugin chạy `App.main` với dependency classpath.

**Không chạy `java -jar consumer/target/consumer-1.0.0.jar` và kỳ vọng chạy độc lập**: POM demo không tạo fat JAR/manifest Main-Class. Để đóng gói standalone cần cấu hình riêng (ví dụ Shade Plugin/distribution with dependencies); đó là vấn đề khác với `install-file`.

## 9. Đọc local repository và kiểm tra artifact

Tọa độ Maven biến thành đường dẫn theo nhóm:

~~~text
com.acme.legacy:vendor-greeter:1.0.0
    -> com/acme/legacy/vendor-greeter/1.0.0/
         vendor-greeter-1.0.0.jar
         vendor-greeter-1.0.0.pom
~~~

Maven local repository mặc định thường là `${user.home}/.m2/repository`, nhưng settings có thể thay đổi. Trên POSIX:

~~~bash
ls -l ~/.m2/repository/com/acme/legacy/vendor-greeter/1.0.0/
~~~

Trên Windows PowerShell:

~~~powershell
Get-ChildItem "$env:USERPROFILE\.m2\repository\com\acme\legacy\vendor-greeter\1.0.0"
~~~

Các lệnh này chỉ đúng khi local repository đang dùng đường dẫn mặc định. Nếu CI hoặc người dùng đặt `-Dmaven.repo.local`, hãy xem chính thư mục được cấu hình, **không kết luận artifact thiếu chỉ vì `.m2` mặc định trống**.

Để xem project consumer đang dùng GAV nào:

~~~bash
mvn -B -f consumer/pom.xml dependency:tree
~~~

Một nhánh đáng tìm có ý nghĩa:

~~~text
com.example:consumer:jar:1.0.0
  com.acme.legacy:vendor-greeter:jar:1.0.0:compile
~~~

Đây là **dạng rút gọn minh họa**, không phải toàn bộ stdout của Dependency Plugin vì còn JUnit test dependencies.

### 9.1. Kiểm chứng bytes và provenance

Trước khi cài hoặc deploy thư viện thật:

- Ghi tên nhà cung cấp, version, nguồn download nội bộ được phép.
- Kiểm chữ ký số khi vendor phát hành signature có thể xác minh.
- So sánh SHA-256 của file với giá trị phát hành qua kênh tin cậy.
- Quét malware/vulnerability theo chính sách.
- Kiểm giấy phép redistributing nội bộ; license mua không luôn đồng nghĩa quyền tái phân phối.
- Ghi Java bytecode target/API compatibility.
- Lưu những dependencies cần thiết cùng version constraints.

POSIX:

~~~bash
sha256sum vendor/vendor-greeter-1.0.0.jar
~~~

PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 vendor/vendor-greeter-1.0.0.jar
~~~

**Hash một mình chỉ chứng minh bytes giống một tham chiếu**, không chứng minh nguồn đáng tin nếu checksum cũng được lấy từ cùng nguồn không tin cậy. Cần một kênh tin cậy cho checksum/signature/provenance.

## 10. Dùng `pomFile`: khi vendor cung cấp POM tốt hơn generic POM

Nếu nhận được `vendor-greeter-1.0.0.pom` chính thức hoặc đã được review, ưu tiên:

~~~bash
mvn -B org.apache.maven.plugins:maven-install-plugin:3.2.0:install-file -Dfile=vendor/vendor-greeter-1.0.0.jar -DpomFile=vendor/vendor-greeter-1.0.0.pom
~~~

Plugin sẽ đọc GAV/packaging từ POM khi có. Đường dẫn POM phải tồn tại và nội dung phải khớp binary. **Nếu POM chưa được phê duyệt hoặc sai coordinates/transitives, dùng `pomFile` không tự khiến nó đúng.**

### 10.1. Ví dụ POM metadata tối giản nhưng chủ động

Với thư viện demo **không có dependency ngoài JDK**, một POM đầy đủ tối giản có thể là:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.acme.legacy</groupId>
    <artifactId>vendor-greeter</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
    <name>Vendor Greeter</name>
    <description>Java 17 demonstration artifact for an internal Maven lab</description>
</project>
~~~

Đặt file này ở `vendor/vendor-greeter-1.0.0.pom` **nếu muốn chọn cách install-with-pom**. Không cần `-DgeneratePom=true` khi đã cung cấp `-DpomFile`.

POM này phù hợp **chỉ** với JAR tự tạo trong lab. Đối với vendor thật, cần dùng đúng metadata, SCM/license information nếu có, và **không khai báo một license giả** để làm compliance report xanh.

### 10.2. Ví dụ lý do phải mô tả transitive dependency

Một binary thật có thể cần:

~~~java
// Trích code minh họa một vendor implementation khác:
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
~~~

Nếu class vendor tham chiếu SLF4J API ở runtime, POM do nhà phát hành cung cấp có thể cần dependency:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.slf4j</groupId>
        <artifactId>slf4j-api</artifactId>
        <version>2.0.16</version>
    </dependency>
</dependencies>
~~~

**Đây chỉ là fragment minh họa cho một JAR khác có dùng SLF4J**, không phải dependency bắt buộc của `VendorGreeter` trong lab. Với artifact thật, version, scope, exclusions và các runtime dependencies phải được xác nhận từ nhà sản xuất, source, documentation hoặc kiểm thử.

Nếu chỉ tạo generic POM, Maven không thể biết những dependencies này. Lỗi có thể chỉ xuất hiện khi consumer gọi một method sau khi deploy, vì class loading có thể trì hoãn.

### 10.3. Không lấy POM nhặt từ Internet làm source of truth

POM đi kèm JAR có thể có URL repositories, transitive dependencies, plugin/build metadata hoặc license/SCM information. Với artifact lạ, cần review các references và chính sách resolution trước khi đưa vào CI production. Đặc biệt tránh tin tuyệt đối vào một POM không rõ nguồn chỉ vì tên file khớp JAR.

## 11. `deploy-file`: thử công bố vào file-based Maven repository an toàn

Không cần tài khoản artifact server để hiểu deploy-file. Một Maven repository có thể có URL `file://` trỏ đến thư mục cục bộ; đây là **bài thử về Maven repository layout**, không phải remote server thật hay production publish.

### 11.1. Chuẩn bị thư mục đích

Trên POSIX/Linux/macOS, dùng ví dụ:

~~~bash
mkdir -p /tmp/maven-thirdparty-repo
~~~

Repo URL tương ứng:

~~~text
file:///tmp/maven-thirdparty-repo
~~~

Trên Windows, ví dụ thư mục riêng được cho phép:

~~~powershell
New-Item -ItemType Directory -Force -Path "C:\temp\maven-thirdparty-repo" | Out-Null
~~~

Repo URL tương ứng:

~~~text
file:///C:/temp/maven-thirdparty-repo
~~~

Đây là **hai ví dụ độc lập theo hệ điều hành**, không phải lúc nào cũng chạy được nguyên cả hai trên một máy. Hãy chọn một đường dẫn được phép dùng, không trỏ vào thư mục Maven local cache mặc định hoặc một server production.

### 11.2. Deploy bản JAR demo vào POSIX file repository

Đứng ở `thirdparty-lab/`, với POSIX URL:

~~~bash
mvn -B org.apache.maven.plugins:maven-deploy-plugin:3.2.0:deploy-file -Dfile=vendor/vendor-greeter-1.0.0.jar -DgroupId=com.acme.legacy -DartifactId=vendor-greeter -Dversion=1.0.0 -Dpackaging=jar -DgeneratePom=true -DrepositoryId=training-file-repo -Durl=file:///tmp/maven-thirdparty-repo
~~~

Thay `-Durl` bằng `file:///C:/temp/maven-thirdparty-repo` trên Windows nếu dùng đúng thư mục Windows ở trên.

**Giải thích:**

- `-Dfile`: binary cần publish.
- `-DgroupId`, `-DartifactId`, `-Dversion`, `-Dpackaging`: coordinates/metadata.
- `-DgeneratePom=true`: tạo POM tối giản vì lab JAR không có POM upstream.
- `-DrepositoryId=training-file-repo`: id repo dùng để lookup server credentials khi cần; file repo local thông thường không cần user/password.
- `-Durl=file:///...`: repository layout đích.
- Maven Deploy Plugin có thể tạo Maven metadata/checksums theo cơ chế repository, tùy version và transport.

Đây là một **lệnh ghi ra filesystem cục bộ**: chỉ thực hiện trong lab khi đường dẫn đích được phép. Không dùng lệnh tương tự với URL release server nội bộ nếu chưa được chủ sở hữu cho phép upload.

### 11.3. Kiểm kết quả ở file repository

Với POSIX:

~~~bash
find /tmp/maven-thirdparty-repo/com/acme/legacy/vendor-greeter -type f
~~~

Các mục chính phải gồm:

~~~text
.../com/acme/legacy/vendor-greeter/1.0.0/vendor-greeter-1.0.0.jar
.../com/acme/legacy/vendor-greeter/1.0.0/vendor-greeter-1.0.0.pom
~~~

Có thể còn các checksum hoặc `maven-metadata.xml`; tên file phụ thuộc triển khai repository và phiên bản plugin. **Không dùng việc thấy một JAR ở thư mục đích làm bằng chứng duy nhất**: kiểm cả POM, đúng version, bytes và khả năng consumer resolve từ repository đó.

### 11.4. Cài vào local repository không giống deploy tới file repository

Hai đường dẫn sau khác nhau:

~~~text
~/.m2/repository/com/acme/legacy/vendor-greeter/1.0.0/...
/tmp/maven-thirdparty-repo/com/acme/legacy/vendor-greeter/1.0.0/...
~~~

Bản đầu là local Maven repository của consumer; bản sau là **repository đích** được Maven Deploy Plugin publish theo URL `file://`. Dù cả hai nằm trên cùng một máy lab, chúng có vai trò khác nhau. Trong doanh nghiệp, repository đích thường là HTTPS hosted Maven repository.

## 12. Consumer resolve từ repository vừa deploy

Một consumer muốn đọc artifact từ `file://` repository phải được cấu hình nguồn resolve. Khi chạy với Maven local repo đã có artifact từ phần 7, Maven có thể dùng cache và **không kiểm chứng repository đích**.

Để thử đúng hành vi remote resolution, cấu hình một `<repository>` có **id/url khớp file repo thử nghiệm**.

Mảnh POM dưới đây đặt trực tiếp trong `<project>` của `consumer/pom.xml` chỉ cho lab POSIX:

~~~xml
<repositories>
    <repository>
        <id>training-file-repo</id>
        <url>file:///tmp/maven-thirdparty-repo</url>
        <releases>
            <enabled>true</enabled>
        </releases>
        <snapshots>
            <enabled>false</enabled>
        </snapshots>
    </repository>
</repositories>
~~~

Trong lab Windows, URL tương ứng là `file:///C:/temp/maven-thirdparty-repo`. Đây là **mảnh POM để thêm vào project**, không phải một POM thứ hai độc lập.

### 12.1. Dùng local repo cách ly để tránh false positive

POSIX shell:

~~~bash
mvn -B -Dmaven.repo.local=/tmp/maven-isolated-local-repo -f consumer/pom.xml clean verify
~~~

Lệnh trên khiến consumer sử dụng local repository **khác** repository cá nhân đã nhận `install-file`. Với internet/plugin repositories khả dụng, Maven sẽ tải build plugins/JUnit từ nguồn hợp lệ và tải vendor artifact từ file repository đã khai báo.

Nếu project chỉ build được khi `~/.m2/repository` có JAR nhưng **không** build từ local repo cách ly, chưa chứng minh publication/repository configuration đã đúng.

**Lưu ý:** việc cấp `-Dmaven.repo.local` cách ly tất cả artifacts, bao gồm Maven plugins và JUnit. Máy không có network/cached artifacts trong repo cách ly có thể fail vì thiếu plugin từ Central. Phải phân biệt lỗi kết nối repository/plugin với lỗi vendor artifact.

### 12.2. Không commit file URL cá nhân vào POM production

Ví dụ `file:///tmp/...` chỉ để học. Production consumer nên dùng:

- Repository URL nội bộ ổn định.
- Repository manager/mirror theo policy tổ chức.
- Access control đọc.
- Credentials trong settings/CI secret infrastructure khi cần.
- Build reproducibility từ CI agent sạch.

Một đường dẫn `file:///C:/temp/...` commit trong POM sẽ không chạy trên Linux CI. Không xem việc copy cả `~/.m2/repository` của developer thành artifact cache là một cách quản trị dependency chuẩn.

## 13. `deploy-file` vào hosted Maven repository nội bộ

Sau khi có quyền của repository owner, có thể dùng HTTPS hosted repo, ví dụ **URL minh họa không hoạt động**:

~~~text
https://repo.example.invalid/repository/thirdparty-releases/
~~~

Lệnh dạng:

~~~bash
mvn -B org.apache.maven.plugins:maven-deploy-plugin:3.2.0:deploy-file -Dfile=vendor/vendor-greeter-1.0.0.jar -DgroupId=com.acme.legacy -DartifactId=vendor-greeter -Dversion=1.0.0 -Dpackaging=jar -DgeneratePom=true -DrepositoryId=thirdparty-hosted -Durl=https://repo.example.invalid/repository/thirdparty-releases/
~~~

**Không chạy nguyên lệnh này để publish**: URL `.invalid` là chỗ minh họa và cần thay bằng repository thật được phép. Khi thực hiện hành động ghi lên repository, phải có authorization, checksums, POM metadata, legal/compliance approval và version policy.

### 13.1. `repositoryId` và `settings.xml`

Maven nhận thông tin xác thực từ `<servers>` trong user/CI `settings.xml`. Dùng cùng id với `-DrepositoryId`:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <servers>
        <server>
            <id>thirdparty-hosted</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
    </servers>
</settings>
~~~

Đây là **settings.xml mẫu cho môi trường kiểm soát**, dùng environment placeholders thay vì mật khẩu thật. Maven hỗ trợ environment property interpolation trong settings theo phiên bản hỗ trợ; CI có thể dùng cơ chế sinh settings bằng secret store. Nếu environment variables chưa được thiết lập, authentication thất bại; đừng để Maven deploy với giá trị placeholder chưa resolve.

**Không commit settings.xml chứa secrets vào Git**, không in mật khẩu/token trong Maven command, và không gửi credentials trong chat/log. Nên dùng TLS/HTTPS, short-lived token và quyền write chỉ cho hosted repo cần thiết.

### 13.2. Bẫy `repositoryId` trùng nhưng URL sai

Theo Maven, `repositoryId` được dùng để tìm server credentials. Ở những versions/configurations, nếu id bị dùng cùng một URL khác với repo được cấp quyền, có nguy cơ gửi credentials tới endpoint ngoài ý muốn. Maven mới có cơ chế ràng buộc server credential origins, nhưng **đừng dựa hoàn toàn vào default**.

Trước deploy:
- Xác nhận `https://` URL chính xác từ repository admin.
- Xác nhận `repositoryId` và `<server><id>` tương ứng.
- Không để untrusted project/POM quyết định một URL mang cùng id dùng credentials.
- Tách read token và write token, chọn minimal scope.
- Kiểm host/certificate, không tắt TLS verification để “chữa” lỗi.
- Dùng approval và audit log cho publication.

### 13.3. `distributionManagement` có bắt buộc với deploy-file?

**Không** cho goal `deploy:deploy-file` khi bạn cung cấp `-Durl` và `-DrepositoryId` trực tiếp. `distributionManagement` quan trọng cho **project lifecycle `mvn deploy`**.

Một cấu hình chuẩn cho project do team build:

~~~xml
<distributionManagement>
    <repository>
        <id>releases-hosted</id>
        <url>https://repo.example.invalid/repository/releases/</url>
    </repository>
    <snapshotRepository>
        <id>snapshots-hosted</id>
        <url>https://repo.example.invalid/repository/snapshots/</url>
    </snapshotRepository>
</distributionManagement>
~~~

Đây là **mảnh POM**, dùng khi team sở hữu nguồn và release flow chuẩn; không cần đưa vào project consumer của lab chỉ để đọc thư viện.

**`<repositories>` là nơi consumer tìm dependency; `<distributionManagement>` là nơi project được publish theo lifecycle.** Đừng dùng cái này thay cái kia.

## 14. `pomFile` khi deploy để bảo toàn transitive metadata

Nếu có POM vendor đúng:

~~~bash
mvn -B org.apache.maven.plugins:maven-deploy-plugin:3.2.0:deploy-file -Dfile=vendor/vendor-greeter-1.0.0.jar -DpomFile=vendor/vendor-greeter-1.0.0.pom -DrepositoryId=training-file-repo -Durl=file:///tmp/maven-thirdparty-repo
~~~

Đây là **bản thay thế** lệnh dùng GAV/generic POM khi POM đã chứa metadata. Không chạy hai lệnh publish **cùng tọa độ release** vào cùng repo nếu repository có immutability policy; hãy chọn một phương án metadata đúng **trước khi publish**.

### 14.1. Vì sao không mặc định bật `generatePom=false`?

- Có `pomFile`: plugin đã có metadata.
- Không có `pomFile`: plugin có thể tạo generic POM khi `generatePom=true`.
- Nếu tắt generation mà không cung cấp POM, consumer có thể thiếu Maven descriptor cần thiết hoặc repository chứa một artifact khó resolve đầy đủ.

Không nên dùng `-DgeneratePom=false` chỉ để tắt warnings mà chưa hiểu hệ quả. Với JAR độc lập, generic POM là tối thiểu; với JAR có transitives, **POM mô tả dependencies đúng** là thiết yếu.

### 14.2. Khi POM vendor có parent/BOM không công khai

Một vendor POM có thể tham chiếu parent/BOM trong private repository. Nếu bạn deploy mỗi JAR+POM mà không có những parent/BOM POMs được consumer resolve, downstream build vẫn lỗi.

Cần kiểm:
- Parent POM coordinates và nơi lấy.
- Imported BOM.
- Transitive dependencies và repository access.
- Java/platform requirements.
- Classifiers/extension nếu vendor phát hành nhiều artifacts.
- License terms cho việc host POM/binary.

Đừng sửa POM để bỏ toàn bộ dependency/parent rồi tuyên bố lỗi đã được giải; điều đó chỉ có thể trì hoãn lỗi đến runtime.

## 15. Sources, Javadoc và classifier

Ngoài JAR chính, vendor có thể giao:

~~~text
vendor-greeter-1.0.0.jar
vendor-greeter-1.0.0-sources.jar
vendor-greeter-1.0.0-javadoc.jar
~~~

Install Plugin có optional parameters `sources`, `javadoc`, `classifier`; Deploy Plugin cũng có các tham số cho attachments.

Nếu các file phụ **thật sự tồn tại và license cho phép**, có thể cài cùng main artifact:

~~~bash
mvn -B org.apache.maven.plugins:maven-install-plugin:3.2.0:install-file -Dfile=vendor/vendor-greeter-1.0.0.jar -DgroupId=com.acme.legacy -DartifactId=vendor-greeter -Dversion=1.0.0 -Dpackaging=jar -DgeneratePom=true -Dsources=vendor/vendor-greeter-1.0.0-sources.jar -Djavadoc=vendor/vendor-greeter-1.0.0-javadoc.jar
~~~

**Lệnh trên chỉ chạy khi đã có cả hai file phụ**. Trong lab mặc định, chúng **chưa được tạo**, nên đừng copy và chạy nguyên lệnh khi chưa tạo/provision.

Các quy tắc:
- `sources`/`javadoc` artifacts không tự tạo ra từ compiled JAR nếu vendor không cung cấp.
- Đừng đổi main JAR thành classifier `sources`.
- Với Deploy Plugin, nếu dùng các tham số `files`, `types`, `classifiers` cho nhiều attachments, **ba danh sách phải có số phần tử tương ứng**; mismatch sẽ fail.
- Thường nên phát hành main artifact, POM, sources/javadoc cùng một quá trình được review nếu source redistribution hợp lệ.

## 16. GAV/type/classifier phải khớp consumer

Giả sử bạn cài:

~~~text
com.acme.legacy:vendor-greeter:1.0.0:jar
~~~

nhưng consumer khai báo:

~~~xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>vendor-greeter</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

`com.acme` **khác** `com.acme.legacy`; Maven sẽ tìm artifact khác. Sự khác biệt này không được tự sửa bằng tên file `vendor-greeter-1.0.0.jar`.

Tương tự, nếu deploy một classified artifact:

~~~text
com.acme.legacy:vendor-greeter:1.0.0:jar:tests
~~~

consumer không thể tự dùng nó như main library mà không có khai báo type/classifier phù hợp.

**Không tự đổi artifact group namespace của vendor đã có Maven coordinates chính thức** khi không có lý do migration có tài liệu. Nếu tổ chức buộc repackaging nội bộ, cần quy định alias/GAV, versioning và phạm vi sử dụng; tránh khiến nhiều module dùng hai tọa độ đại diện cùng một binary gây class duplication.

## 17. `system` scope và `systemPath`: tại sao không nên dùng thay install-file?

Một anti-pattern:

~~~xml
<dependency>
    <groupId>com.acme.legacy</groupId>
    <artifactId>vendor-greeter</artifactId>
    <version>1.0.0</version>
    <scope>system</scope>
    <systemPath>C:/Users/developer/Downloads/vendor-greeter-1.0.0.jar</systemPath>
</dependency>
~~~

Đây là **mảnh POM không khuyến nghị**. Nó chỉ chạy khi file có đúng ở đường dẫn local, khó tái hiện trên CI/Linux và làm Maven transitive dependency resolution không hoạt động theo cách repository chuẩn.

Các vấn đề:

1. Đường dẫn phụ thuộc user/OS.
2. File ở Downloads có thể bị thay thế mà không đổi Git commit.
3. Không có repository metadata/provenance chuẩn.
4. Không có cách publish/share artifact trong team.
5. License/compliance/audit khó thực hiện.
6. Scope `system` bị Maven khuyến nghị tránh dùng.
7. Mang JAR vào source tree rồi trỏ `systemPath` vẫn không giải quyết transitive dependencies.

Nếu chỉ cần một local spike, `install-file` rõ nghĩa hơn. Nếu team/CI dùng, một **hosted Maven repository có quản lý** tốt hơn.

## 18. Repository managers và policy phát hành

Một repository manager nội bộ có thể có:

~~~text
thirdparty-releases (hosted, immutable)
thirdparty-snapshots (hosted, controlled)
maven-central-proxy (proxy)
maven-public (group)
~~~

Tên này chỉ là **mô hình tổ chức**, không phải endpoint thật. Để publish một JAR bên thứ ba cần:

- Hosted repository chấp nhận Maven2 layout, đúng loại release/snapshot.
- Quyền upload riêng.
- Quyền đọc riêng cho CI/consumers.
- Phê duyệt bản quyền và security.
- POM dependencies và checksums.
- Release immutability, không overwrite GAV.
- Retention/backup/audit policy.
- Cơ chế rollback bằng **version mới** hoặc disable/quarantine artifact theo policy, không sửa bytes của một release đã được sử dụng.

**Không publish third-party JAR vào một namespace mà bạn không có quyền sử dụng.** Cần kiểm upstream coordinates và quy định internal namespace. Một Maven repository manager có thể lưu những binary mà Maven Central không cho phép upload, nhưng điều đó không tự biến việc tái phân phối thành hợp pháp.

## 19. Version `-SNAPSHOT` và release khác nhau

Nếu vendor giao một bản preview chưa ổn định, việc đặt version:

~~~text
1.0.0-SNAPSHOT
~~~

có thể làm repository xử lý snapshot metadata/timestamp và retention khác release. Nhưng **không nên tự gắn `-SNAPSHOT` chỉ vì file chưa có POM**. Version nên phản ánh identity/release status của binary.

| Kiểu | Ví dụ | Policy thường gặp |
| --- | --- | --- |
| Release | `1.0.0` | Immutable; không ghi đè |
| Snapshot | `1.0.1-SNAPSHOT` | Có thể update, không phù hợp làm release dependency bất biến |
| Vendor hotfix rõ danh tính | `1.0.0-acme.1` | Chỉ khi có versioning policy/tọa độ nội bộ chính thức |

Nếu lỡ publish bytes sai ở GAV release, **đừng âm thầm deploy lại cùng version** dù server cho phép. Hãy quarantine, điều tra downstream consumers và phát hành corrected version có tên/traceability rõ theo policy.

## 20. Rủi ro supply chain: `install-file`/`deploy-file` không xác thực code

Maven goals này **đưa một file vào repository**, chúng không biến file đó thành artifact an toàn.

Một checklist bảo mật trước publish:

1. Nhận file từ kênh vendor được xác thực.
2. Ghi URL/source, hash, release notes và ngày nhận.
3. Kiểm signed checksum/signature qua kênh tin cậy nếu có.
4. Quét malware và vulnerability.
5. Kiểm licenses, export controls và redistribution rights.
6. Kiểm Java target version/classfile compatibility.
7. Kiểm API usage/ABI và runtime dependencies.
8. Kiểm JAR manifest, service providers, native libs, resource conflicts.
9. Kiểm POM/parent/BOM/repositories có nguồn đáng tin.
10. Chạy isolated integration tests với application consumer thực.
11. Không chạy mã không tin cậy bằng tài khoản có repository write/secrets.
12. Có owner chấp thuận và rollback/quarantine procedure.
13. Dùng repository audit logs, checksum policy, immutability.
14. Không dán tokens vào Maven CLI hoặc commit `settings.xml` chứa secrets.
15. Ghi SBOM/provenance cho release artifacts nếu policy yêu cầu.

**SHA-256 trùng** chỉ khẳng định tính toàn vẹn so với baseline; không chứng minh tính hợp pháp hoặc không có mã độc.

### 20.1. Tránh che lấp dependency provenance

Một JAR có thể đã tồn tại trong Central dưới GAV chính thức. Nếu không tìm thấy vì doanh nghiệp chặn Internet hoặc mirror bị cấu hình sai, cần điều tra **repository/mirror/credentials** trước khi tự đóng gói lại binary dưới GAV mới.

Một artifact bị cache `404` trong local Maven repo có thể cần refresh metadata phù hợp; đừng coi mọi `Could not find artifact` là lý do phải `install-file`.

## 21. Kiểm chứng publication từ một máy sạch

Mục tiêu cuối không phải “lệnh deploy trả BUILD SUCCESS” mà là **consumer khác thực sự tải và dùng được artifact**.

Các bước:

1. Kiểm có JAR và POM đúng GAV ở repository đích.
2. Kiểm binary checksum/provenance.
3. Kiểm POM đã publish có parent/BOM/transitives mà consumer resolve được.
4. Cấu hình read repository (settings/mirror/POM) trong một consumer sạch.
5. Dùng local Maven repository cách ly để tránh cache giả xanh.
6. Chạy `mvn clean verify` trên consumer.
7. Đọc `dependency:tree` để biết version/scope resolved.
8. Chạy smoke test/`exec:java` hoặc runtime test theo ứng dụng.
9. Ghi test reports và checksum.
10. Nếu release, xác nhận immutability/audit log và không publish vào Central ngoài quyền.

Trong lab, test `AppTest` thể hiện consumer đọc class và hành vi đầu ra. Trong thực tế, còn cần tests cho error handling, concurrency, input boundaries, binary APIs và integration components mà vendor cung cấp.

## 22. Cách chẩn đoán lỗi `install-file`

| Triệu chứng | Nguyên nhân có thể | Cách kiểm |
| --- | --- | --- |
| `The specified file ... does not exist` | `-Dfile` sai đường dẫn/cwd | `ls`, `Get-ChildItem`, chọn đúng folder |
| `Invalid artifactId/groupId/version` | Tọa độ sai hoặc thiếu | Xem GAV được phê duyệt, tránh đặt tùy tiện |
| Install thành công nhưng consumer vẫn báo missing | Consumer GAV khác, local repo khác | So GAV và `maven.repo.local` |
| Compiler không thấy `VendorGreeter` | JAR không chứa class hoặc POM dependency thiếu | `jar tf`, dependency tree, Java package |
| `NoClassDefFoundError` lúc chạy | JAR thiếu transitive runtime dependency | Lấy/review POM upstream, kiểm runtime graph |
| Artifact cũ vẫn được dùng | Local repo chứa cùng GAV với bytes khác | So SHA-256 và versioning policy |
| `generatePom=true` nhưng dependency metadata thiếu | Generic POM chỉ chứa minimal fields | Cung cấp vetted `pomFile` |
| IDE xanh nhưng CLI đỏ | IDE manual classpath khác Maven | Build bằng Maven CLI từ clean |
| CI đỏ dù laptop xanh | Laptop đã install local artifact | Publish vào hosted repo và clean-consumer test |
| JAR chạy trong JDK 17 nhưng CI dùng JDK 11 | Classfile version không tương thích | `java -version`, target compatibility |

**Không chữa sai bằng cách copy vendor JAR vào thư mục plugin Maven hoặc `JAVA_HOME/lib`.** Đó là classpath khác và có thể làm Maven toolchain bất ổn.

## 23. Cách chẩn đoán lỗi `deploy-file`

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| HTTP 401 | Không có/không đúng credentials | `repositoryId` ↔ settings server id, token |
| HTTP 403 | Đủ auth nhưng không có quyền ghi | Repository ACL/policy |
| HTTP 404 | URL endpoint sai hoặc hosted repository không có path đó | Xác minh URL từ repo admin |
| HTTP 409/400 khi release | Artifact/version đã tồn tại, immutability hoặc metadata policy | Không overwrite; dùng version mới qua quy trình |
| SSL/TLS error | Certificate/proxy/trust configuration | Sửa truststore/proxy; không disable validation |
| Timeout/network error | Repo unavailable, DNS/proxy/firewall | Kiểm network; tránh retry mù publish |
| `UnknownHostException` | Host URL sai | Kiểm URL, DNS, approved endpoint |
| POM upload sai version | `pomFile` mismatch hoặc GAV overrides | So artifact metadata trước deploy |
| Deploy success nhưng consumer fail | Consumer thiếu repo config, repo permissions, POM transitives | Clean-resolve từ consumer |
| Release lẫn Snapshot | Publish vào repository loại sai | Chọn release/snapshot hosted theo policy |
| Same GAV nhưng bytes khác | Có binary bị thay ở nguồn hoặc overwrite | So checksum, quarantine, không coi artifact cũ là an toàn |
| Sources/Javadoc attachment lỗi | File không tồn tại hoặc classifier/type mismatch | Kiểm paths và optional inputs |
| Credentials lộ trong logs | Đưa password vào CLI/POM | Thu hồi token, chuyển secrets vào settings/CI vault |

Một số lỗi remote xảy ra **sau khi một phần dữ liệu đã tới repository**. Không nên retry publish mù với cùng GAV rồi giả định lần đầu thất bại hoàn toàn; kiểm repository metadata, audit/log và artifacts trước khi quyết định xử lý.

## 24. `deploy-file` không thay được release pipeline chuẩn

Khi sở hữu source thư viện, quy trình đáng tin thường là:

~~~text
Git commit/tag
   -> reproducible Maven build
   -> unit tests + integration tests
   -> static analysis/security/license checks
   -> generate POM/sources/javadoc/SBOM/signature
   -> checksum/provenance
   -> staging/approval
   -> mvn deploy vào repository chính thức
   -> verify consumer from clean repo
~~~

`deploy-file` chỉ là **bước publish binary/POM có sẵn**. Nếu dùng nó liên tục thay cho pipeline, cần tự bổ sung mọi bước kiểm chứng ở ngoài goal.

Nếu source code thật **không có POM**, cân nhắc xây Maven POM chuẩn và pipeline trước, thay vì hàng năm upload binary thủ công. Nếu vendor artifact độc quyền không được phép sửa source, `deploy-file` có thể là cách hợp lý trong **quy trình tiếp nhận artifact bên thứ ba có owner, approval và audit**.

## 25. Khi nào lựa chọn nào là hợp lý nhất?

Dùng **`install-file`** khi:
- Đang thử một JAR được cấp phép trên máy local.
- Chưa cần chia sẻ artifact cho người khác.
- Muốn kiểm API và compiler behavior trước khi lập metadata/publish.
- Chấp nhận rằng việc cài này không tái tạo tự động trên CI mới.

Dùng **`deploy-file`** khi:
- Artifact đã qua bước tiếp nhận và compliance kiểm tra.
- Có hosted Maven repository nội bộ được phê duyệt.
- Có GAV/version policy ổn định và POM metadata phù hợp.
- Team/CI cần resolve từ repository, không phụ thuộc local cache của developer.
- Có người chịu trách nhiệm publish, audit, rollback/quarantine.

Dùng **`mvn deploy`** khi:
- Bạn có project Maven/POM/source được quản lý.
- CI build và test artifact theo một release workflow chuẩn.
- `distributionManagement` và credentials được cấu hình an toàn.
- Muốn publish project artifacts cùng POM/attachments/reports theo lifecycle.

## 26. Bài tập kiểm tra kiến thức

**Câu 1.** `install-file` cài artifact vào đâu?

**Đáp:** Local Maven repository của invocation đang chạy, không tự đưa lên repository team.

**Câu 2.** `deploy-file` có tự compile nguồn Java của vendor không?

**Đáp:** Không. Nó nhận file có sẵn và publish theo metadata/endpoint đã khai báo.

**Câu 3.** GAV `com.acme.legacy:vendor-greeter:1.0.0` có tự map từ tên `vendor-greeter-1.0.0.jar` không?

**Đáp:** Không theo nghĩa đủ tin cậy. Dùng `groupId`, `artifactId`, `version`/`pomFile` để xác định coordinates chính xác.

**Câu 4.** `generatePom=true` có tự phát hiện tất cả transitive dependencies không?

**Đáp:** Không. Nó tạo generic POM tối giản khi không có POM; phải có POM chính thức/chính xác cho dependencies thật.

**Câu 5.** Nếu JAR chứa class `com.acme.legacy.VendorGreeter`, consumer cần khai báo gì?

**Đáp:** Một dependency GAV/type tương ứng artifact đã install/deploy, để Maven bổ sung JAR vào classpath.

**Câu 6.** Vì sao laptop build được mà CI sạch fail?

**Đáp:** Có thể JAR chỉ được `install-file` vào local repository của laptop; CI không có cùng artifact/repository.

**Câu 7.** `-DrepositoryId` làm gì?

**Đáp:** Chỉ định id để Maven đối chiếu server credentials trong settings khi deploy, không thay thế `-Durl`.

**Câu 8.** Có nên đưa token deploy vào `-Dpassword=...` hay POM trong Git?

**Đáp:** Không. Dùng Maven settings/CI secret management với quyền hạn tối thiểu.

**Câu 9.** `distributionManagement` có bắt buộc khi gọi `deploy:deploy-file` với explicit URL không?

**Đáp:** Không. `deploy-file` dùng `-Durl`/`-DrepositoryId`; `distributionManagement` là cơ chế quan trọng cho `mvn deploy` lifecycle.

**Câu 10.** Vì sao cần thử local repo cách ly khi test publication?

**Đáp:** Để không vô tình dùng JAR cũ từ cache cá nhân thay vì tải artifact từ repository vừa publish.

**Câu 11.** Có nên ghi đè binary release dưới cùng GAV nếu sửa được một lỗi nhỏ không?

**Đáp:** Không. Nên dùng version mới theo policy, giữ artifact identity/immutability.

**Câu 12.** `pomFile` có thể giúp điều gì?

**Đáp:** Cung cấp GAV và dependency metadata chính xác cho artifact, thay vì generic POM chỉ có thông tin tối thiểu.

**Câu 13.** `systemPath` trỏ vào Downloads có làm CI reproducible không?

**Đáp:** Không, vì phụ thuộc vào một file local không được repository quản lý.

**Câu 14.** SHA-256 của JAR khớp một giá trị thì file chắc chắn an toàn không?

**Đáp:** Không. Nó chỉ kiểm bytes so với baseline; nguồn baseline/signature, license, malware và dependencies vẫn cần được đánh giá.

**Câu 15.** File-based Maven repository `file:///tmp/...` có phải public Maven repository không?

**Đáp:** Không. Đây là URL tới thư mục theo Maven repository layout, thích hợp lab/certain internal workflows, không tự là HTTPS repository manager.

**Câu 16.** Deploy Plugin báo HTTP 409 khi release đã tồn tại, có nên retry 10 lần không?

**Đáp:** Không. Kiểm repo immutability/GAV và artifact provenance, không retry mù.

**Câu 17.** Khi nào nên dùng classifier `sources`?

**Đáp:** Khi phát hành sources JAR như artifact phụ của cùng GAV, không phải main runtime JAR.

**Câu 18.** Nếu vendor POM tham chiếu private parent POM bị thiếu, deploy JAR+POM đã đủ chưa?

**Đáp:** Chưa. Consumer vẫn phải resolve được parent/BOM và các dependencies cần thiết.

**Câu 19.** Vì sao `mvn clean install` của consumer không tạo ra vendor JAR?

**Đáp:** Consumer build artifact của chính nó và resolve vendor dependency. Vendor JAR được cung cấp riêng qua install-file hoặc repository.

**Câu 20.** Quality gate nào cần bổ sung trước khi `deploy-file` binary thật?

**Đáp:** Xác minh nguồn/chữ ký/hash, legal/license, security scans, runtime compatibility, POM/dependencies đúng, consumer integration tests và approval.

## 27. Checklist khi tiếp nhận một JAR chưa có quy trình Maven

1. Xác định library **thực sự chưa có** trong Maven repository được cho phép.
2. Kiểm từ vendor có POM chính thức hoặc Gradle module metadata tương ứng không.
3. Xác định có quyền sử dụng/tái phân phối nội bộ JAR không.
4. Tải/nhận artifact từ nguồn được xác thực, lưu provenance.
5. Kiểm chữ ký/checksum theo một nguồn tin cậy.
6. Quét malware/CVEs, kiểm JDK/platform compatibility.
7. Quyết định GAV dựa trên namespace/version policy, không đặt ngẫu nhiên.
8. Kiểm `jar tf` xem main classes thật sự tồn tại.
9. Kiểm dependencies/parent POM/BOM của vendor trước khi tạo POM.
10. Nếu JAR độc lập, generic POM có thể đủ cho lab.
11. Nếu vendor có transitives, ưu tiên reviewed `pomFile`.
12. Với local spike, dùng `install:install-file` và GAV đầy đủ.
13. Không dùng `systemPath` trỏ Downloads để thay thế.
14. Dùng fully qualified plugin goal/version đã được test.
15. Tạo Maven consumer nhỏ để compile/test thực tế.
16. Dùng JUnit assertions cho behavior, không chỉ class loading.
17. Khi team cần dùng lại, yêu cầu hosted Maven repository có quyền hợp lệ.
18. Thử `deploy-file` vào file-based repository sandbox trước khi publish thật.
19. Kiểm URL/`repositoryId`/credentials/certificates trước remote deploy.
20. Không cho untrusted URL nhận token từ Maven settings.
21. Phân biệt hosted releases và hosted snapshots.
22. Không overwrite cùng release GAV bằng bytes mới.
23. Kiểm repo có JAR và POM, không chỉ một file.
24. Dùng isolated local Maven repo để test remote resolution.
25. Kiểm `dependency:tree` và runtime classpath của consumer.
26. Thử integration trên JDK/OS/service môi trường mục tiêu.
27. Đảm bảo sources/javadoc/classifier đúng và được phép phân phối.
28. Lưu SBOM/audit/change ticket theo policy.
29. Khi có thể, lập pipeline build/test/deploy chuẩn thay upload thủ công.
30. Không công bố artifact production khi chưa được owner phê duyệt.

## Tài liệu chính thức

- [Apache Maven Install Plugin — install:install-file](https://maven.apache.org/plugins/maven-install-plugin/install-file-mojo.html)
- [Apache Maven Install Plugin — Generating a Generic POM](https://maven.apache.org/plugins/maven-install-plugin/examples/generic-pom-generation.html)
- [Apache Maven Install Plugin — Installing Artifact with Custom POM](https://maven.apache.org/plugins/maven-install-plugin/examples/custom-pom-installation.html)
- [Apache Maven Deploy Plugin — deploy:deploy-file](https://maven.apache.org/plugins/maven-deploy-plugin/deploy-file-mojo.html)
- [Apache Maven Deploy Plugin — File Deployment](https://maven.apache.org/plugins/maven-deploy-plugin/examples/deploying-with-repository-file.html)
- [Apache Maven — Guide to Installing 3rd Party JARs](https://maven.apache.org/guides/mini/guide-3rd-party-jars-local.html)
- [Apache Maven — Guide to Deploying 3rd Party JARs](https://maven.apache.org/guides/mini/guide-3rd-party-jars-remote.html)
- [Apache Maven — Configuring Maven, Security and Deployment](https://maven.apache.org/guides/mini/guide-configuring-maven.html)
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven — Setting up Multiple Repositories](https://maven.apache.org/guides/mini/guide-multiple-repositories.html)
- [Apache Maven — Introduction to Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven Dependency Plugin — dependency:get](https://maven.apache.org/plugins/maven-dependency-plugin/get-mojo.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)

