# Plugin prefix và cách Maven tìm plugin tương ứng

## 1. Khái niệm và mục tiêu

Khi chạy các lệnh Maven như:

~~~bash
mvn help:effective-pom
mvn dependency:tree
mvn compiler:compile
mvn exec:java
~~~

`help`, `dependency`, `compiler` và `exec` là **plugin prefix**; phần sau dấu hai chấm là **goal** do plugin cung cấp. Prefix là tên ngắn để Maven tìm plugin thật, chứ không phải tên đầy đủ của artifact hoặc một phase của lifecycle.

Ví dụ:

~~~text
mvn help:effective-pom
     │        │
     │        └── goal = effective-pom
     └─────────── prefix = help
                  │
                  ▼
org.apache.maven.plugins:maven-help-plugin
                  │
                  ▼
       chọn plugin version
                  │
                  ▼
        thực thi goal
~~~

Trong bài học thuộc nhóm **Plugin và goal** này, bạn sẽ:

- Phân biệt plugin prefix, plugin artifact, plugin goal/Mojo và lifecycle phase.
- Biết Maven ánh xạ `prefix:goal` sang `groupId:artifactId:version:goal` như thế nào.
- Hiểu thứ tự tra cứu plugin trong POM và metadata của `pluginGroups`.
- Biết ý nghĩa của `maven-metadata.xml` cấp group, `<pluginRepositories>` và `pluginManagement`.
- Nắm cách plugin bên thứ ba công bố prefix và cách tránh trùng prefix.
- Chạy ví dụ Maven + Java 17, dùng cả prefix và tọa độ plugin đầy đủ.
- Phân biệt lỗi prefix mapping, plugin version/artifact resolution, goal lookup và lifecycle phase.
- Có quy trình chẩn đoán ngắn gọn, phù hợp với terminal, IDE và CI.

Phạm vi chủ yếu là Maven 3.x với mô hình POM 4.0.0. Các phiên bản plugin trong ví dụ được chốt để người học dễ tái hiện; không mặc định là phiên bản mới nhất.

## 2. Đừng nhầm phase với goal

| Thuật ngữ | Ví dụ | Vai trò |
| --- | --- | --- |
| **Lifecycle phase** | `compile`, `test`, `package`, `install` | Một giai đoạn Maven chạy theo lifecycle. |
| **Plugin** | `maven-compiler-plugin` | Artifact cung cấp các tác vụ build. |
| **Goal/Mojo** | `compile`, `jar`, `effective-pom` | Một thao tác cụ thể của plugin. |
| **Plugin prefix** | `compiler`, `jar`, `help` | Bí danh CLI dùng để nhận diện plugin. |

So sánh:

~~~bash
mvn compile
mvn compiler:compile
~~~

`mvn compile` chạy tới phase `compile` của default lifecycle: Maven thực hiện các goal đã bind với những phase cần chạy, chẳng hạn xử lý tài nguyên trước compile. `mvn compiler:compile` **gọi trực tiếp goal compile** của Maven Compiler Plugin; không tự động bảo đảm các goal ở phase trước đã chạy.

Tương tự:

~~~bash
mvn clean
mvn clean:clean
~~~

`clean` trong lệnh đầu là **phase** của clean lifecycle, còn `clean:clean` là **goal** của Maven Clean Plugin. Dự án đơn giản có thể nhận kết quả giống nhau, nhưng cơ chế điều phối khác nhau.

Và:

~~~bash
mvn package
mvn jar:jar
~~~

`package` đi qua các phase trước để có class/resources phù hợp. Gọi `jar:jar` đơn lẻ không nhất thiết biên dịch source hoặc sinh resource. Vì vậy lệnh ngắn có dấu hai chấm không phải bản thay thế tùy ý cho lifecycle phase.

**Quy tắc nhận diện nhanh:** một token CLI như `package` thường chỉ phase, trong khi `jar:jar` yêu cầu plugin goal. Một plugin có thể có **nhiều goal**, tất cả cùng sử dụng một prefix.

## 3. Prefix thông dụng và tọa độ plugin thật

| Prefix:goal | groupId:artifactId | Goal |
| --- | --- | --- |
| `help:effective-pom` | `org.apache.maven.plugins:maven-help-plugin` | `effective-pom` |
| `help:describe` | `org.apache.maven.plugins:maven-help-plugin` | `describe` |
| `dependency:tree` | `org.apache.maven.plugins:maven-dependency-plugin` | `tree` |
| `compiler:compile` | `org.apache.maven.plugins:maven-compiler-plugin` | `compile` |
| `resources:resources` | `org.apache.maven.plugins:maven-resources-plugin` | `resources` |
| `jar:jar` | `org.apache.maven.plugins:maven-jar-plugin` | `jar` |
| `clean:clean` | `org.apache.maven.plugins:maven-clean-plugin` | `clean` |
| `surefire:test` | `org.apache.maven.plugins:maven-surefire-plugin` | `test` |
| `exec:java` | `org.codehaus.mojo:exec-maven-plugin` | `java` |

Những ví dụ này mô tả mapping thông dụng. `exec` thuộc **groupId `org.codehaus.mojo`**, không thuộc `org.apache.maven.plugins`. Tên artifact của nó là **`exec-maven-plugin`**, không phải một suy luận máy móc như `maven-exec-plugin`.

Prefix không nhất thiết đủ để chỉ ra một plugin duy nhất trong mọi môi trường. Một plugin tùy biến có thể công bố prefix trùng tên với plugin khác; Maven sử dụng thông tin của project và thứ tự plugin groups để quyết định.

## 4. Ba cách gọi plugin goal từ CLI

Lấy Help Plugin làm ví dụ, cùng goal `effective-pom` có thể được gọi bằng ba dạng.

### 4.1. Dạng `prefix:goal`

~~~bash
mvn help:effective-pom -Doutput=effective-short.xml
~~~

Maven cần **tìm ánh xạ** `help` → plugin artifact, rồi chọn plugin version.

### 4.2. Dạng `groupId:artifactId:goal`

~~~bash
mvn org.apache.maven.plugins:maven-help-plugin:effective-pom -Doutput=effective-ga.xml
~~~

Không cần tra prefix, vì plugin GA đã được chỉ rõ. Nhưng vì chưa có version, Maven vẫn phải **giải quyết phiên bản plugin** theo cấu hình project/repository.

### 4.3. Dạng `groupId:artifactId:version:goal`

~~~bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Doutput=effective-pinned.xml
~~~

Plugin và version đều tường minh. Maven không cần tìm prefix và không cần chọn plugin version. Tuy nhiên plugin POM/JAR và plugin dependencies vẫn phải có trong local cache hoặc được tải từ repository phù hợp.

| Dạng CLI | Bỏ qua prefix lookup? | Version đã chốt? |
| --- | --- | --- |
| `help:effective-pom` | Không | Tùy POM/version resolution. |
| `org.apache.maven.plugins:maven-help-plugin:effective-pom` | Có | Chưa ghi trên CLI. |
| `org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom` | Có | Có. |

**Dùng full coordinates là cách tốt để chẩn đoán lỗi prefix**. Nếu full coordinates chạy nhưng `help:effective-pom` lỗi, hãy kiểm tra POM/pluginGroups/metadata thay vì vội quy lỗi cho code Java. Full coordinates vẫn không giải quyết thay bạn vấn đề quyền truy cập repository hay goal không tồn tại.

## 5. Maven thực sự tìm prefix ở đâu?

Khi nhận token `foo:bar`, Maven cần tìm plugin GA trước. Trong Maven 3, cách hiểu thực dụng là:

### Bước 1 — Xét plugin có trong effective POM

Maven có thể tìm mapping trong các plugin được khai báo ở `<build><plugins>` hoặc `<build><pluginManagement>` của project đang chạy. Ví dụ mảnh POM:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-help-plugin</artifactId>
            <version>3.5.2</version>
        </plugin>
    </plugins>
</build>
~~~

Khi project khai báo plugin rõ ràng, Maven có thể dùng thông tin đó để nhận diện plugin và version. Parent POM và active profiles có thể làm **effective POM** khác file POM nguồn của module.

**Không nhầm:** `pluginManagement` quản lý cấu hình/phiên bản plugin; nó không tự thực thi mọi plugin được liệt kê. Việc goal được chạy còn phụ thuộc lifecycle binding, plugin execution hoặc lệnh trực tiếp.

### Bước 2 — Nếu chưa nhận diện được, xét các `pluginGroups`

Maven tìm groupId của những plugin groups được cấu hình. Hai group phổ biến được Maven 3 hỗ trợ mặc định là:

~~~text
org.apache.maven.plugins
org.codehaus.mojo
~~~

Maven **không quét toàn bộ Maven Central theo tên gần giống** khi người dùng gõ một prefix tùy ý. Nó xét các groupId thích hợp và metadata của các group đó.

### Bước 3 — Đọc metadata cấp group

Với `org.apache.maven.plugins`, đường dẫn metadata là:

~~~text
org/apache/maven/plugins/maven-metadata.xml
~~~

Ở Maven Central, một URL có dạng:

~~~text
https://repo.maven.apache.org/maven2/org/apache/maven/plugins/maven-metadata.xml
~~~

Đây là **metadata cấp groupId** dùng cho mapping prefix, không phải POM của một plugin riêng.

### Bước 4 — Dùng entry prefix để lấy artifactId

Trong metadata có thể có:

~~~xml
<plugin>
    <name>Maven Help Plugin</name>
    <prefix>help</prefix>
    <artifactId>maven-help-plugin</artifactId>
</plugin>
~~~

GroupId đã biết từ group đang xét: `org.apache.maven.plugins`. Maven ghép được:

~~~text
org.apache.maven.plugins:maven-help-plugin
~~~

Nếu nhóm này không chứa `foo`, Maven xét group tiếp theo. Nếu không có mapping ở những nguồn thích hợp, lệnh thất bại với lỗi không tìm được prefix.

### Bước 5 — Giải quyết version, tải plugin và tìm goal

Prefix mapping trả về **GA**, chưa đủ để thực thi. Maven còn phải chọn plugin version, tải plugin artifact/POM/dependencies, đọc danh sách goal và thực thi goal `bar`.

~~~text
CLI: mvn foo:bar
     │
     ▼
Tìm plugin tương ứng trong effective POM
     ├── có → groupId:artifactId
     └── không
            │
            ▼
       Plugin groups theo thứ tự
            │
            ▼
       Group-level maven-metadata.xml
            ├── thấy foo → groupId:artifactId
            └── không → nhóm tiếp theo
                         │
                         └── hết nhóm → prefix lookup lỗi

Có groupId:artifactId
      ↓
chọn version → tải plugin → đọc goal descriptor → thực thi bar
~~~

Sơ đồ thể hiện các **bước logic**, không phải pseudocode đầy đủ của Maven Resolver. Cache metadata, profiles, parent POM và phiên bản Maven có thể ảnh hưởng một số chi tiết.

## 6. `maven-metadata.xml` cấp group có nội dung thế nào?

Đây là XML **minh họa rút gọn** về metadata cho nhóm plugin chính thức:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<metadata>
    <groupId>org.apache.maven.plugins</groupId>
    <plugins>
        <plugin>
            <name>Maven Help Plugin</name>
            <prefix>help</prefix>
            <artifactId>maven-help-plugin</artifactId>
        </plugin>
        <plugin>
            <name>Maven Compiler Plugin</name>
            <prefix>compiler</prefix>
            <artifactId>maven-compiler-plugin</artifactId>
        </plugin>
    </plugins>
</metadata>
~~~

File thật trên repository có thể chứa nhiều entry và khác về định dạng. **Metadata prefix không nhất thiết ghi plugin version**.

### Phân biệt metadata theo vị trí

| Cấp metadata | Vị trí ví dụ | Vai trò |
| --- | --- | --- |
| **Group** | `org/apache/maven/plugins/maven-metadata.xml` | Ánh xạ `prefix → artifactId`. |
| **Artifact** | `org/apache/maven/plugins/maven-help-plugin/maven-metadata.xml` | Thông tin các version của artifact plugin. |
| **Snapshot version** | `.../maven-help-plugin/1.0-SNAPSHOT/maven-metadata.xml` | Thông tin timestamped snapshot nếu có. |

Maven 3 có thể cache metadata remote tại:

~~~text
~/.m2/repository/org/apache/maven/plugins/maven-metadata-central.xml
~~~

`central` ở đây là **repository ID** thường gặp. Khi dùng repository manager khác, file cache có thể là `maven-metadata-<repoId>.xml`. Một số metadata cục bộ do Maven install tạo có thể mang tên `maven-metadata-local.xml`. Maven có thể ghép các nguồn metadata để tìm mapping theo cấu hình.

**Không chỉnh sửa file cache trực tiếp** để thêm prefix. Đó không phải API ổn định và cache có thể bị cập nhật/ghi đè. Cách đúng là sửa cấu hình group/repository hoặc build/publish plugin và metadata theo quy trình chuẩn.

### Descriptor của plugin không đồng nghĩa group metadata

Bên trong một Maven plugin JAR thường có:

~~~text
META-INF/maven/plugin.xml
~~~

Plugin descriptor mô tả prefix, goals/Mojos, tham số và metadata dùng để thực thi plugin. Còn metadata ở **đường dẫn groupId** phục vụ bước **tìm plugin từ prefix**. Đừng nhầm hai loại dữ liệu.

~~~text
Group-level metadata  → prefix map đến plugin artifact nào?
Artifact/version info → version/plugin JAR nào tải được?
Plugin descriptor     → plugin có goal và parameter nào?
~~~

## 7. Cấu hình `pluginGroups` trong `settings.xml`

Một plugin bên thứ ba không thuộc hai group mặc định có thể cần khai báo groupId trong Maven settings:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.0.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.0.0 https://maven.apache.org/xsd/settings-1.0.0.xsd">
    <pluginGroups>
        <pluginGroup>com.example.build</pluginGroup>
    </pluginGroups>
</settings>
~~~

Đây là **settings mẫu có cấu trúc đúng**; group `com.example.build` chỉ là **giả định**, không tự có plugin nào. Đừng dùng nó để thay settings thật rồi cho rằng `mvn audit:check` chắc chắn chạy được.

Vị trí settings thông thường:

~~~text
~/.m2/settings.xml
<MAVEN_HOME>/conf/settings.xml
~~~

`-s` chọn một user settings file khác, ví dụ:

~~~bash
mvn -s custom-settings.xml help:effective-pom
~~~

File `custom-settings.xml` phải tồn tại và chứa cấu hình hợp lệ. Cấu hình `pluginGroups` nằm **trực tiếp dưới root `<settings>`**, không nằm trong `<profile>`, `<activeProfiles>` hay POM `<project>`.

### Thứ tự plugin group quan trọng

Những group được người dùng cấu hình có thể được tra **trước** nhóm mặc định. Nếu nhiều plugin công bố cùng prefix như `clean`, prefix resolution có thể ánh xạ sang plugin ngoài dự tính. Vì thế:

- Chọn prefix riêng, không chiếm `clean`, `compiler`, `help` của nhóm chính thức.
- Hạn chế thêm plugin group không tin cậy vào settings dùng chung.
- Trong CI, ghi rõ plugin group và POM version để tái hiện build.
- Với thao tác nhạy cảm, ưu tiên `groupId:artifactId:version:goal`.

## 8. `pluginRepositories` khác `pluginGroups` ra sao?

**`pluginGroups`** trả lời “tìm prefix trong những groupId nào?”. **`pluginRepositories`** trả lời “Maven tải metadata và plugin artifact từ repository nào?”.

Ví dụ một **mảnh POM** để chỉ plugin repository nội bộ:

~~~xml
<pluginRepositories>
    <pluginRepository>
        <id>company-plugins</id>
        <url>https://repo.example.org/maven/plugins</url>
    </pluginRepository>
</pluginRepositories>
~~~

URL `example.org` là **minh họa**, không phải repository đang hoạt động. Khi cần repository nội bộ thật, dùng URL và credentials do quản trị viên cung cấp.

| Cấu hình | Vai trò |
| --- | --- |
| `<repositories>` | Nguồn cho project dependencies. |
| `<pluginRepositories>` | Nguồn cho Maven plugins và metadata liên quan. |
| `<pluginGroups>` | Những groupId để tra prefix. |
| `<mirrors>` | Điều hướng yêu cầu repository qua mirror/proxy repository manager. |
| `<servers>` | Thông tin xác thực theo ID được Maven sử dụng. |

Nếu Maven không thể tải Help Plugin, **không đồng nghĩa** thư viện dependency của app bị lỗi. Plugin repositories và dependency repositories có mục đích khác nhau. Mặt khác, một groupId đã được thêm vào pluginGroups nhưng repository không chứa plugin/metadata tương ứng cũng không giúp mapping thành công.

**Vấn đề bảo mật:** không đưa token vào `pom.xml` hay tài liệu; không chia sẻ nguyên `settings.xml` hoặc log `mvn -X` khi chưa kiểm duyệt secrets/URL nội bộ.

## 9. Prefix được xác định như thế nào khi phát triển plugin?

Maven Plugin Plugin có quy ước suy ra prefix từ artifactId:

- **Plugin chính thức Apache Maven:** `maven-${prefix}-plugin`, ví dụ `maven-help-plugin` → `help`.
- **Plugin bên thứ ba:** `${prefix}-maven-plugin`, ví dụ `exec-maven-plugin` → `exec`.

Nhóm ngoài Apache Maven được khuyến nghị dùng dạng `${prefix}-maven-plugin`. Dạng `maven-${prefix}-plugin` dành cho các plugin chính thức của Apache Maven, không nên dùng để đặt tên plugin tùy biến.

Quy ước tên là **cách công cụ phát triển plugin suy ra prefix**, không có nghĩa Maven khi chạy CLI sẽ tự đoán tất cả artifactId trên remote repository.

### Chỉ định `goalPrefix` tường minh

Tác giả plugin có thể cấu hình Maven Plugin Plugin:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-plugin-plugin</artifactId>
            <version>3.16.0</version>
            <configuration>
                <goalPrefix>auditx</goalPrefix>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Đây chỉ là **mảnh POM cho dự án phát triển Maven plugin**, không phải POM của ứng dụng sử dụng plugin. Dự án plugin cần `<packaging>maven-plugin</packaging>`, Mojo implementation, plugin tooling và quy trình đóng gói/publish hợp lệ.

Nếu một plugin có prefix `auditx`, goal `check` và metadata được công bố đầy đủ, người dùng có thể gọi `mvn auditx:check` sau khi Maven tìm được group tương ứng. **Không coi đó là lệnh có sẵn** nếu chưa có plugin thật.

### Có thể dùng tọa độ đầy đủ thay prefix

Giả sử plugin minh họa có tọa độ:

~~~text
com.example.build:audit-maven-plugin:1.0.0
~~~

và goal `check`, lệnh dạng đầy đủ là:

~~~text
mvn com.example.build:audit-maven-plugin:1.0.0:check
~~~

Dạng này **không cần đăng ký prefix** cho lời gọi đó, nhưng Maven vẫn phải tìm/tải plugin artifact thực và plugin phải cung cấp goal `check`.

## 10. Prefix mapping và plugin version là hai quyết định

Ngay cả sau khi đã giải quyết:

~~~text
help → org.apache.maven.plugins:maven-help-plugin
~~~

Maven vẫn cần biết **plugin version** nếu CLI chưa ghi nó.

Ví dụ parent POM có thể chốt:

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-help-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

`pluginManagement` quản lý plugin được sử dụng; nó không tự chạy goal. Khi dự án dùng plugin, Maven có thể lấy version/config từ mục quản lý này.

**`dependencyManagement` không tương đương `pluginManagement`.** DependencyManagement quản lý dependencies của project, không dùng để chốt Maven Help/Compiler/Dependency Plugin versions.

Nếu version không được chốt trong invocation hoặc POM/parent, Maven có thể dùng các nguồn version khác, bao gồm repository metadata. Việc chọn version khi đó phụ thuộc cấu hình, môi trường và các quy tắc của Maven. Để build ổn định, nên ghim phiên bản plugin quan trọng bằng POM hoặc dùng full coordinates.

## 11. Ví dụ Java 17 chạy được: quan sát prefix và goal

### 11.1. Tạo dự án

Cây thư mục:

~~~text
plugin-prefix-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── org/
                └── example/
                    └── learning/
                        └── App.java
~~~

Có thể tạo bằng IDE hoặc terminal. Ví dụ Bash:

~~~bash
mkdir -p plugin-prefix-demo/src/main/java/org/example/learning
cd plugin-prefix-demo
~~~

PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path "plugin-prefix-demo\src\main\java\org\example\learning" | Out-Null
Set-Location plugin-prefix-demo
~~~

### 11.2. POM hoàn chỉnh

Tạo `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>org.example.learning</groupId>
    <artifactId>plugin-prefix-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
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
                <artifactId>maven-help-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`maven.compiler.release=17` chốt Java target. Compiler, JAR và Help Plugin được khai báo phiên bản cụ thể. Mục Help Plugin được thêm vào `<build><plugins>` nhằm minh họa một plugin mà project đã chỉ rõ, không có nghĩa mọi project bắt buộc phải khai báo Help Plugin trước khi gọi.

### 11.3. Mã Java 17

Tạo `src/main/java/org/example/learning/App.java`:

~~~java
package org.example.learning;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        int sum = 2 + 4;
        System.out.println("Plugin prefix demo: " + sum);
    }
}
~~~

Không dùng dependency bên ngoài JDK. Java file, package và tên class khớp với cấu trúc thư mục.

### 11.4. Build, chạy, đối chiếu stdout

Đứng trong `plugin-prefix-demo/`:

~~~bash
mvn --version
java -version
mvn clean package
java -cp target/plugin-prefix-demo-1.0-SNAPSHOT.jar org.example.learning.App
~~~

**Stdout chính xác của lệnh Java cuối:**

~~~text
Plugin prefix demo: 6
~~~

Log Maven có thể in `BUILD SUCCESS` và thông tin plugin; đó không phải stdout của chương trình `App`. POM chưa khai báo `Main-Class` trong manifest nên dùng `java -cp`, không mặc định `java -jar` chạy được.

### 11.5. Gọi cùng một goal bằng hai cách

~~~bash
mvn help:effective-pom -Doutput=effective-short.xml
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Doutput=effective-full.xml
~~~

Cả hai gọi goal `effective-pom` của Maven Help Plugin và ghi báo cáo XML ra file khác nhau. Lệnh 1 dùng prefix; lệnh 2 nêu đầy đủ plugin và version. Hai file không cần được khẳng định byte-identical trong mọi môi trường; hãy kiểm tra model build và phiên bản plugin.

### 11.6. Dùng `help:describe`

~~~bash
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-compiler-plugin -Dgoal=compile -Ddetail=true
~~~

Lệnh này **không biên dịch** ứng dụng. Nó yêu cầu Help Plugin mô tả goal `compile` của Compiler Plugin, bao gồm các tham số/thuộc tính mà goal hỗ trợ.

So sánh:

~~~bash
mvn compile
mvn compiler:compile
mvn org.apache.maven.plugins:maven-compiler-plugin:3.13.0:compile
~~~

Lệnh đầu là lifecycle phase; hai lệnh sau trực tiếp gọi compiler goal. Với dự án thật, direct goal có thể không chạy resource generation và các phase trước như lifecycle.

### 11.7. Một plugin bên thứ ba thực tế

Maven Exec Plugin có:

~~~text
groupId    = org.codehaus.mojo
artifactId = exec-maven-plugin
prefix     = exec
goal       = java
~~~

Sau khi `mvn package` đã biên dịch class, có thể chạy:

~~~bash
mvn org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=org.example.learning.App
~~~

Dòng do code Java in khi chạy thành công:

~~~text
Plugin prefix demo: 6
~~~

Đó không phải toàn bộ log Maven; Exec Plugin có thể in thêm thông tin. Dạng ngắn tương ứng:

~~~bash
mvn exec:java -Dexec.mainClass=org.example.learning.App
~~~

Nhóm `org.codehaus.mojo` nằm trong nhóm được Maven 3 hỗ trợ mặc định, nhưng vẫn cần tải được plugin/version. Dạng tọa độ đầy đủ có lợi khi muốn tránh prefix collision hoặc lựa chọn version khác môi trường.

## 12. Plugin prefix bị trùng: vì sao nguy hiểm?

Giả sử hai plugin **giả định**:

~~~text
com.example.build:audit-maven-plugin
org.example.tools:audit-maven-plugin
~~~

đều công bố prefix `audit`. Settings chứa:

~~~xml
<pluginGroups>
    <pluginGroup>com.example.build</pluginGroup>
    <pluginGroup>org.example.tools</pluginGroup>
</pluginGroups>
~~~

Thứ tự tìm group và các khai báo plugin trong POM có thể làm cùng `audit:check` trỏ đến plugin khác trên hai môi trường. Người dùng không thể chắc chắn một lệnh ngắn sẽ chọn cùng artifact nếu settings/group metadata khác.

Tránh:

- Đặt prefix trùng `clean`, `compiler`, `jar`, `help` hoặc prefix của plugin được sử dụng rộng rãi.
- Thêm plugin groups không được kiểm soát nguồn vào settings dùng chung.
- Dựa vào version ngầm định cho thao tác build/release quan trọng.

Nên:

- Ghim version trong POM/parent.
- Kiểm tra plugin GA và version trên log Maven.
- Dùng `groupId:artifactId:version:goal` khi cần chắc chắn plugin nào được thực thi.

## 13. Ba loại lỗi thường bị lẫn

### 13.1. Không tìm được prefix

Một lỗi thường có dạng:

~~~text
No plugin found for prefix 'auditx' in the current project
and in the plugin groups ...
~~~

Đây là **trích đoạn đại diện**, không phải stack trace cố định. Nguyên nhân có thể:

- Prefix viết sai.
- Plugin không được cấu hình trong project và groupId không ở `pluginGroups`.
- Metadata cấp group chưa công bố mapping hoặc bị lỗi.
- Plugin repository không được cấu hình đúng.
- Mirror, proxy, permissions hoặc metadata download thất bại.
- Plugin chưa được install/deploy kèm metadata phù hợp.

Thử full coordinates của **plugin đã biết thật**, kiểm tra POM, settings và group metadata. Không tự thêm ngẫu nhiên nhiều groupId để đoán plugin.

### 13.2. Có GA nhưng không tải được plugin

Nếu Maven biết plugin tọa độ/version nhưng không lấy được artifact, đó là **plugin artifact/version resolution**. Kiểm tra:

1. Plugin version có tồn tại?
2. `pluginRepositories`/mirror có trỏ tới kho phù hợp?
3. Credential trong settings có ID tương ứng?
4. Có dùng offline mode `-o` khi cache chưa có file?
5. Repository policy có cho phép release/snapshot đó không?

Dùng full coordinates không giải quyết thay lỗi HTTP 401/403, timeout, sai repository hoặc plugin chưa publish.

### 13.3. Plugin đã tải được nhưng goal không tồn tại

Một lệnh cố ý sai:

~~~bash
mvn compiler:not-a-real-goal
~~~

Maven có thể tìm được Compiler Plugin, nhưng goal `not-a-real-goal` không có. Đây **không phải lỗi prefix**.

Xem danh sách goal thật bằng:

~~~bash
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-compiler-plugin -Ddetail=true
~~~

hoặc mô tả riêng compile goal:

~~~bash
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-compiler-plugin -Dgoal=compile -Ddetail=true
~~~

### 13.4. Sai lifecycle phase

~~~bash
mvn compilee
~~~

`compilee` không có dấu hai chấm và không phải lifecycle phase hợp lệ; lỗi thuộc **phase recognition**. Lệnh:

~~~bash
mvn compiler:compilee
~~~

lại yêu cầu tìm prefix `compiler` rồi tìm goal `compilee`, một lỗi thuộc **goal lookup** nếu prefix đã được resolve.

## 14. Quy trình xử lý có thứ tự

Khi một lệnh `prefix:goal` không chạy:

1. **Xác nhận chính xác lệnh, POM và Maven/JDK:** dùng `mvn --version`, kiểm tra `-f`, Maven Wrapper và IDE.
2. **Phân biệt phase/goal:** có dấu `:` không, prefix/goal có đúng tên không?
3. **Tìm tọa độ plugin thật:** groupId, artifactId, version từ tài liệu plugin đáng tin.
4. **Thử full coordinates** với một goal chắc chắn tồn tại để phân lập prefix lookup.
5. **Xem effective POM:** `build/plugins`, `pluginManagement`, parent/profile đã cấu hình plugin nào?
6. **Kiểm tra settings thực tế:** `pluginGroups`, `pluginRepositories`, mirrors, server IDs và file `-s` nếu có.
7. **Kiểm tra group metadata:** repository có `maven-metadata.xml` chứa ánh xạ prefix đúng không?
8. **Kiểm tra plugin version/artifact:** plugin đã publish, download được và tương thích Maven/JDK chưa?
9. **Kiểm tra goal descriptor:** dùng `help:describe` cho đúng goal và phiên bản.
10. **Khi cần, dùng `mvn -X ...`** nhưng lọc bí mật/URL nội bộ trước khi chia sẻ log.

Các lệnh chẩn đoán hữu ích:

~~~bash
mvn --version
mvn help:effective-pom -Doutput=effective.xml
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-compiler-plugin -Dgoal=compile -Ddetail=true
mvn -X help:effective-pom
~~~

`-X` chỉ để debug; log có thể chứa thông tin nhạy cảm. Không chỉnh metadata/cache trong `~/.m2/repository` bằng tay để “sửa” prefix.

## 15. Triệu chứng và cách hiểu đúng

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `help:effective-pom` chỉ lỗi ở một máy. | Khác Maven, settings, cache, mirror hoặc repository. | So invocation, POM, effective settings, plugin log. |
| `dependency:tree` không chạy dù dependency đã có. | Dependency Plugin chưa tải được. | Kiểm tra `pluginRepositories` và mạng. |
| Custom `audit:check` không được nhận diện. | Thiếu group lookup hoặc prefix metadata. | Xem pluginGroups/POM/publish; thử full coordinates. |
| `compiler:compile` chạy nhưng thiếu resource. | Direct goal không chạy toàn bộ lifecycle. | Dùng `mvn compile` hoặc `mvn package`. |
| `jar:jar` xuất JAR thiếu class. | Chưa compile trước khi gọi goal đóng gói. | Dùng lifecycle chuẩn và kiểm tra `target/classes`. |
| Prefix gọi plugin lạ. | Prefix collision hoặc settings/POM khác. | Kiểm tra GA/version, dùng full coordinates. |
| Version plugin thay đổi. | Parent/pluginManagement hoặc version resolution khác. | Ghim version và xem effective POM. |
| Đã tải plugin nhưng goal báo lỗi. | Goal không được plugin hỗ trợ hoặc cấu hình sai. | Dùng `help:describe`, đọc tài liệu của goal. |
| Lệnh báo phase không tồn tại. | Gõ phase sai hoặc nhầm cú pháp. | Phân biệt `mvn compile` và `mvn compiler:compile`. |
| HTTP 401/403 khi tải plugin. | Quyền hoặc server ID không khớp. | Kiểm tra settings và credential an toàn. |
| Build offline thiếu plugin. | Plugin/dependencies chưa được cache. | Chuẩn bị cache hoặc dùng mạng phù hợp. |

## 16. Bài tập và tự kiểm tra

### Bài A — Phân loại lệnh

Với các lệnh:

~~~bash
mvn compile
mvn compiler:compile
mvn package
mvn jar:jar
mvn help:effective-pom
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom
~~~

**Đáp án:** `compile` và `package` không có dấu hai chấm là phase. Bốn lệnh còn lại gọi plugin goals. Lệnh `help:effective-pom` dùng prefix; lệnh cuối chỉ rõ groupId/artifactId/version.

### Bài B — Thực hành với Java 17

1. Tạo `plugin-prefix-demo` từ mục 11.
2. Build bằng `mvn clean package` và chạy Java; xác nhận stdout `Plugin prefix demo: 6`.
3. Gọi `help:effective-pom` bằng prefix và full coordinates; giải thích các bước resolution khác nhau.
4. Dùng `help:describe` xem các parameters của goal compile.
5. Gọi `mvn compiler:compile` và giải thích vì sao không đồng nghĩa với `mvn compile`.
6. Quan sát group metadata ở đường dẫn `org/apache/maven/plugins/maven-metadata.xml`; tìm ánh xạ `help → maven-help-plugin`.
7. Dùng Exec Maven Plugin bản ghim version để chạy App, phân biệt stdout Java với log plugin.
8. Giải thích vì sao CI nên ghim plugin version.

### Bài C — Plugin tùy biến

Giả sử tổ chức viết plugin `com.example.build:audit-maven-plugin:1.0.0` với goal `check`.

- Prefix mặc định hợp lý theo quy ước tên là gì?
- Vì sao chỉ khai báo `pluginGroups` mà chưa publish plugin vẫn không chạy được?
- `pluginRepositories` phải trỏ tới đâu khi plugin nằm ở repository nội bộ?
- Metadata cấp group cần mapping gì?
- Lệnh nào bỏ được prefix lookup?
- Vì sao không nên chiếm prefix `clean`?

Lệnh **minh họa, chỉ chạy khi artifact/goal thực sự tồn tại**:

~~~text
mvn com.example.build:audit-maven-plugin:1.0.0:check
~~~

### Câu hỏi tự đánh giá

1. `plugin prefix` có phải tên artifactId hay tên goal không?
2. Maven có tự quét mọi artifact của Maven Central khi thấy một prefix lạ không?
3. Group metadata và plugin descriptor có chức năng gì khác nhau?
4. Có thể chạy goal của plugin chưa khai báo trong POM không?
5. `pluginGroups` và `pluginRepositories` khác nhau ở điểm nào?
6. Dùng GA không có version còn cần resolution nào?
7. Vì sao `dependencyManagement` không quản lý build plugins?
8. Lệnh `mvn compiler:compile` có đảm bảo chạy `process-resources` không?
9. Nếu plugin tải được nhưng goal không tồn tại, phải điều tra ở tầng nào?
10. Khi nào nên dùng full coordinates thay cho prefix?

## 17. Tổng kết

**Plugin prefix là bí danh giúp Maven tìm plugin artifact trước khi gọi goal**, không phải tên lifecycle phase hay plugin version. Maven có thể xem plugin trong project, sau đó tra các **pluginGroups** và **metadata cấp group** để ánh xạ prefix thành `groupId:artifactId`. Cuối cùng Maven chọn version, tải plugin, đọc danh sách goals và thực thi goal.

~~~text
CLI phase hay plugin goal?
    ↓
Nếu goal: prefix → plugin GA?
    ↓
Plugin version nào?
    ↓
Repository nào cung cấp plugin?
    ↓
Plugin có goal đó không?
    ↓
Goal chạy thành công?
~~~

Với build quan trọng, hãy **chốt phiên bản plugin**, kiểm soát nguồn plugin và sử dụng `groupId:artifactId:version:goal` khi cần loại bỏ sự mơ hồ. Khi gặp lỗi, xác định đúng bước thất bại thay vì tùy tiện sửa POM, settings hoặc cache.

## Tài liệu chính thức

- Apache Maven — Introduction to Plugin Prefix Resolution: https://maven.apache.org/guides/introduction/introduction-to-plugin-prefix-mapping.html
- Apache Maven — Maven Metadata: https://maven.apache.org/repositories/metadata.html
- Apache Maven — Settings Reference: https://maven.apache.org/settings.html
- Apache Maven — Guide to Developing Java Plugins: https://maven.apache.org/guides/plugin/guide-java-plugin-development.html
- Apache Maven — Introduction to Plugins: https://maven.apache.org/guides/introduction/introduction-to-plugins.html
- Apache Maven — POM Reference: https://maven.apache.org/pom.html
- Maven Help Plugin — `help:describe`: https://maven.apache.org/plugins/maven-help-plugin/describe-mojo.html
- Apache Maven — Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
