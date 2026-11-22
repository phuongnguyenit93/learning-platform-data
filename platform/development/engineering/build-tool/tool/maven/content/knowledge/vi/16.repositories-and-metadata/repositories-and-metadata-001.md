# Kho cục bộ, kho từ xa và vai trò của Maven Central

Mỗi khi chạy `mvn compile`, `mvn test` hoặc `mvn package`, Maven có thể cần nhiều thứ hơn mã nguồn của dự án: JAR thư viện, POM mô tả dependency bắc cầu, các plugin build, parent POM và metadata về phiên bản. Maven lưu và truy xuất những artifact đó qua **repository (kho Maven)**.

Có ba khái niệm nền tảng cần phân biệt:

1. **Local repository (kho cục bộ)** nằm trên máy chạy Maven: lưu cache artifact đã tải từ xa, đồng thời lưu artifact mà bạn chủ động cài bằng `mvn install` hoặc `install:install-file`.
2. **Remote repository (kho từ xa)** được truy cập qua mạng hoặc giao thức repository được cấu hình, cung cấp artifact mà Maven cần tải hoặc nhận artifact được phép deploy.
3. **Maven Central** là một remote repository công khai quan trọng trong hệ sinh thái Java, được Maven cấu hình làm nguồn mặc định thông qua **Super POM**. Nó không phải thư mục local, không phải toàn bộ Internet và không chứa mọi thư viện của mọi tổ chức.

Trong cấu hình thông thường, Maven cố gắng giải quyết dependency bằng local repository và những remote repositories thích hợp khi cần; nếu Maven Central được chọn và không bị mirror thay thế, artifact công khai có thể được tải từ đó, rồi được cache tại kho cục bộ để dùng cho các lần build tiếp theo.

```text
                          Dự án Maven
                           pom.xml
                              |
                              v
                   Maven Resolver / Core
                              |
                    +---------+---------+
                    |                   |
                    v                   v
           Local repository     Remote repository
          ~/.m2/repository       (nếu cần tải)
                    ^                   |
                    |          +--------+---------+
                    |          |                  |
                    |          v                  v
                    |     Maven Central       Kho riêng/manager
                    |      hoặc mirror       (theo cấu hình)
                    |          |                  |
                    +----------+------------------+
                       cache artifact hợp lệ
```

Sơ đồ mang tính khái niệm: Maven Resolver còn xét nguồn gốc artifact trong cache, mirror selection, repository policy, metadata và trạng thái offline. **Không nên hiểu “có file trong `~/.m2/repository`” là Maven luôn sẽ sử dụng file đó ở mọi cấu hình repository.**

Bài học giải thích vai trò từng loại kho, cách ánh xạ tọa độ artifact thành đường dẫn repository, thực hành tải thư viện thật từ Maven Central bằng ví dụ Java 17, cùng cách tổ chức mirror, private repository, CI và xử lý sự cố.

## 1. Maven repository chứa những gì?

Repository Maven là một kho artifact được sắp xếp theo **tọa độ** và **layout** xác định, không đơn thuần là thư mục chứa JAR ngẫu nhiên.

Một dependency thường được định danh bằng:

```text
groupId:artifactId:version
```

Ví dụ một artifact công khai:

```text
org.apache.commons:commons-lang3:3.14.0
```

Ý nghĩa:

| Thành phần | Giá trị ví dụ | Vai trò |
| --- | --- | --- |
| `groupId` | `org.apache.commons` | Nhóm định danh hoặc namespace của artifact. |
| `artifactId` | `commons-lang3` | Tên artifact trong nhóm. |
| `version` | `3.14.0` | Phiên bản cụ thể của artifact. |
| `type` | `jar` (mặc định cho dependency thông thường) | Dạng artifact được yêu cầu. |
| `classifier` | Không có trong ví dụ | Có thể chỉ biến thể của artifact, ví dụ nguồn hoặc tài liệu. |

Theo layout Maven phổ biến, một JAR release có thể nằm ở:

```text
org/apache/commons/commons-lang3/3.14.0/
    commons-lang3-3.14.0.jar
    commons-lang3-3.14.0.pom
```

Các dấu chấm trong `groupId` được thay bằng dấu `/` ở đường dẫn layout. Mỗi version có thư mục riêng; tên artifact gồm `artifactId-version` cùng phần mở rộng và classifier nếu có.

Repository còn chứa:

- **JAR, POM và artifact khác:** mã bytecode, cấu hình dự án, ZIP, các artifact kiểu `pom`, JAR có classifier, v.v.
- **Metadata:** thông tin về các version có sẵn, snapshot và những dữ liệu cần cho version resolution.
- **Checksum/chữ ký khi được publish:** hỗ trợ xác nhận integrity, tùy chính sách repository và công cụ.
- **Thông tin đi kèm:** POM dependencies, parent, license, SCM hoặc plugin metadata có liên quan.

Không phải mọi file ở đường dẫn repository đều là dependency classpath. **POM có thể đóng vai trò artifact** (parent POM, BOM) dù nó không chứa lớp Java. Maven plugins cũng được phân phối như artifact và có dependencies riêng của chúng.

### 1.1. Vì sao POM metadata quan trọng?

Khi POM của ứng dụng khai báo:

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.14.0</version>
</dependency>
```

Maven không chỉ cần file `commons-lang3-3.14.0.jar`; nó còn cần mô hình POM thích hợp để biết artifact có dependency bắc cầu nào, điều kiện/metadata ra sao. Nếu một thư viện A phụ thuộc B và C, Maven có thể đọc POM của A để thu thập các nhánh đó.

Một JAR được chép thủ công vào thư mục dự án **không tự trở thành dependency Maven**. Để Maven giải quyết theo tọa độ, cần metadata/repository hoặc cơ chế đặc biệt được khai báo hợp lệ.

## 2. Kho cục bộ: nơi Maven cache và install artifact

Trên Maven 3.x, vị trí local repository thông thường là:

```text
Linux/macOS: ~/.m2/repository
Windows:     C:\Users\<user>\.m2\repository
```

Đây là đường dẫn minh họa theo môi trường mặc định. Ký hiệu `<user>` là tên tài khoản thực tế của máy, không phải chuỗi phải ghi nguyên vào cấu hình. Vị trí có thể được thay đổi qua settings hoặc tùy chọn Maven.

Local repository có **hai chức năng độc lập nhưng cùng sử dụng một hệ thống lưu trữ**:

1. **Cache tải về:** Maven đã giải quyết JAR/POM/plugin từ remote repository, lưu bản phù hợp để lần sau không cần tải lại trong những điều kiện phù hợp.
2. **Lưu artifact cài tại chỗ:** chạy `mvn install` với một project sẽ đưa artifact của project vào local repository, cho phép những project khác trên cùng máy tham chiếu qua tọa độ.

Ví dụ:

```bash
mvn clean install
```

Khi lệnh hoàn thành thành công với một project JAR, Maven thường đã tạo artifact dưới `target` và cài nó vào local repository theo tọa độ dự án. **`install` không đồng nghĩa `deploy`**: nó không tự publish file lên Maven Central hoặc repository của công ty.

Nếu project có tọa độ:

```text
com.example.training:demo-core:1.0.0
```

bạn có thể quan sát layout truyền thống như:

```text
~/.m2/repository/
└── com/example/training/demo-core/1.0.0/
    ├── demo-core-1.0.0.pom
    └── demo-core-1.0.0.jar
```

Đường dẫn trên chỉ minh họa layout. Maven Resolver hiện đại hỗ trợ **split local repository**, phân biệt vùng artifact được tải từ xa và vùng artifact được cài tại chỗ. Vì vậy không nên viết script phụ thuộc vào một cấu trúc file nội bộ duy nhất như thể đó là API ổn định.

### 2.1. Không dùng local repository như thư mục thư viện phải tự quản lý

Các thao tác sai thường gặp:

- Kéo-thả JAR vào `~/.m2/repository` và tưởng Maven đã cài artifact đúng.
- Đổi tên thư mục version hoặc chỉnh POM bên trong cache bằng tay.
- Commit cả `.m2/repository` vào Git để “chia sẻ dependencies”.
- Đọc một file cache rồi xem nó là bằng chứng duy nhất rằng Maven sẽ dùng artifact đó.
- Xóa toàn bộ cache khi gặp lỗi nhỏ mà chưa kiểm tra nguyên nhân.

Apache Maven khuyến cáo không thao tác trực tiếp trên nội dung local repository bằng các thao tác file đơn giản để thay thế resolver API. Việc truy xuất/phân phối nội bộ của Resolver có thể liên quan trạng thái nguồn gốc, cache lỗi, locking và nhiều implementation khác nhau.

**Thực hành đúng:** dùng Maven goals để cài/tải artifact, dùng repository manager để chia sẻ và chỉ dọn cache có chủ đích khi biết hậu quả.

### 2.2. Thay local repository mà không sửa mọi POM

Maven cho phép đặt vị trí kho cục bộ trong `settings.xml`:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0
                              https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <localRepository>/work/maven-cache</localRepository>
</settings>
```

Đây là tệp settings Maven 3.x mang tính minh họa; chọn một đường dẫn tuyệt đối hợp lệ trên máy thực. Trên Windows hãy dùng đường dẫn thích hợp, ví dụ `C:/maven-cache`.

Hoặc chỉ định cho một lần chạy:

```bash
mvn -Dmaven.repo.local=/work/maven-cache clean package
```

Tùy chọn `maven.repo.local` giúp tách cache của một phiên build; những đường dẫn này phải có quyền ghi phù hợp. Nếu đưa vào CI, quyết định có tái dùng cache giữa job, có phân tách theo JDK/Maven/profile và có kiểm soát nội dung cache hay không.

**Phân biệt đường dẫn:**

| Thư mục | Mục đích |
| --- | --- |
| `project/target` | Output build của project, có thể xóa khi `mvn clean`. |
| `~/.m2/repository` | Cache và artifact cài tại máy theo tọa độ Maven. |
| `~/.m2/settings.xml` | Cấu hình Maven cho user, có thể chứa thông tin nội bộ/xác thực. |
| `MAVEN_HOME/conf/settings.xml` | Global settings của bản Maven đang sử dụng. |
| Thư mục chứa `pom.xml` | Nguồn cấu hình riêng của dự án. |

Xóa `target` **không dọn local repository**. Ngược lại, dọn local repository không xóa source hoặc build output hiện có trong `target`.

## 3. Remote repository: nguồn artifact có thể truy cập ngoài kho máy

**Remote repository** là kho được Maven truy cập từ một endpoint phù hợp để **tải** artifact hoặc, khi cấu hình publishing/permission cho phép, **đẩy** artifact lên.

Ví dụ remote repository có thể là:

- Maven Central, chứa rất nhiều thư viện Java và Maven plugins công khai.
- Repository manager nội bộ của tổ chức, cung cấp artifact riêng và proxy/cache artifact công khai.
- Repository của một nhà cung cấp hoặc đối tác, khi artifact cần thiết không được công bố trên Central.
- Repository phục vụ releases hoặc snapshots với chính sách khác nhau.

Maven phân biệt hai hướng:

**Resolution (download):** lấy JAR/POM/metadata/plugins để build. Cấu hình liên quan có thể nằm ở `<repositories>`, `<pluginRepositories>`, settings profiles và mirrors.

**Publishing (upload/deploy):** phát hành artifact mà project tạo ra lên repository do bạn có quyền quản lý. Cấu hình thường nằm ở `<distributionManagement>`; `mvn deploy` thực hiện công việc phù hợp.

Đừng nhầm **“repository có trong POM”** với **“repository mà Maven deploy artifact vào”**. Cấu hình `<repositories>` chủ yếu mô tả nguồn để giải quyết dependencies, không tự cấp quyền upload.

### 3.1. Ví dụ thêm một repository từ xa cho dependency

Nếu artifact riêng đã được phân phối ở endpoint do tổ chức quản lý và có quyền truy cập:

```xml
<repositories>
    <repository>
        <id>company-public-group</id>
        <url>https://repo.example.invalid/repository/maven-public/</url>
        <releases>
            <enabled>true</enabled>
        </releases>
        <snapshots>
            <enabled>false</enabled>
        </snapshots>
    </repository>
</repositories>
```

Đây là **đoạn XML đặt trong `<project>`**, không phải POM hoàn chỉnh. Domain `example.invalid` chỉ để học; lệnh build thực tế sẽ không thể kết nối tới endpoint giả này.

Những phần quan trọng:

- `id`: định danh repository, được sử dụng trong chính sách, mirror và cấu hình liên quan.
- `url`: endpoint có layout Maven phù hợp.
- `releases`: điều khiển việc dùng repository cho release artifacts.
- `snapshots`: điều khiển việc dùng repository cho SNAPSHOT artifacts.
- `updatePolicy`, `checksumPolicy` và các thiết lập khác có thể ảnh hưởng cập nhật metadata và kiểm tra artifact, theo tài liệu Maven.

**Lưu ý:** `<repositories>` dành cho dependency của dự án; plugin có cơ chế nguồn riêng là `<pluginRepositories>`. Một build thất bại khi tải plugin không nhất thiết được sửa chỉ bằng cách thêm `<repositories>`.

### 3.2. Tại sao cần pluginRepositories?

Maven plugins, chẳng hạn Maven Compiler Plugin hoặc Maven Surefire Plugin, cũng là artifact Maven. Để chạy goal, Maven cần giải quyết plugin và dependency riêng của plugin.

Ví dụ cấu hình thêm plugin repository, nếu tổ chức thực sự yêu cầu:

```xml
<pluginRepositories>
    <pluginRepository>
        <id>company-plugin-group</id>
        <url>https://repo.example.invalid/repository/maven-plugins/</url>
    </pluginRepository>
</pluginRepositories>
```

Đây là ví dụ minh họa, không phải lời khuyên phải thêm plugin repository cho mọi dự án. Trong phần lớn dự án dùng artifact công khai, cấu hình mặc định hoặc repository manager tập trung là đủ.

Nếu một plugin không tải được, cần kiểm tra **plugin repositories, mirror, settings, mạng và version plugin**, thay vì chỉ xem dependencies của ứng dụng.

## 4. Vai trò của Maven Central

**Maven Central** là kho artifact công khai quan trọng của hệ sinh thái JVM, được sử dụng rộng rãi bởi Maven và những build tools khác. Trong cấu hình Maven thông thường, Central được khai báo mặc định thông qua **Super POM**, nên một dự án có thể tải dependency công khai **mà không cần tự viết phần tử `<repositories>` trỏ Central**.

Thông tin thường gặp:

```text
Repository ID: central
Repository URL: https://repo.maven.apache.org/maven2
```

Đây là endpoint Central được tài liệu Apache Maven chính thức mô tả. Maven có thể đi qua CDN, mirror hoặc repository manager, nên log build trên máy doanh nghiệp **không nhất thiết hiện chính URL đó**.

Các vai trò của Central:

1. **Nguồn công khai mặc định** cho nhiều thư viện phát hành, ví dụ Apache Commons, thư viện logging và nhiều Maven plugins.
2. **Giúp đồng bộ tọa độ artifact:** dự án tham chiếu dependency theo GAV thay vì tải JAR bằng tay rồi lưu trong Git.
3. **Cung cấp POM metadata:** Maven biết dependencies bắc cầu, version, parent và thông tin cần cho giải quyết.
4. **Hỗ trợ hệ sinh thái CI/developer:** những máy có mạng và chính sách truy cập phù hợp có thể giải quyết cùng release artifact.
5. **Làm nguồn upstream cho repository manager:** tổ chức có thể proxy/cache Central để kiểm soát truy cập, băng thông và chính sách bảo mật.

**Nhưng Central không phải là:**

- Thư mục local `.m2` của bạn.
- Kho lưu mọi JAR thương mại, nội bộ hoặc proprietary.
- Nơi mặc định nhận `mvn deploy` từ mọi project không có quyền.
- Một service bảo đảm mọi tọa độ bạn tự nghĩ ra đều tồn tại.
- Công cụ tự động đánh giá rằng dependency an toàn, không có lỗ hổng và tương thích với ứng dụng của bạn.

Central chủ yếu phục vụ các **release artifacts công khai**. Với snapshots của một dự án trong quá trình phát triển hoặc artifact riêng, thường cần repository phù hợp khác, chẳng hạn snapshots repo của tổ chức.

### 4.1. Tại sao POM mới tạo có thể không khai báo repository nào?

Maven có **Super POM** cung cấp nhiều mặc định, trong đó có repository với ID `central` và plugin repository mặc định. Effective POM của một project có thể cho thấy những giá trị này ngay cả khi tệp `pom.xml` nguồn không có `<repositories>`.

Lệnh kiểm tra:

```bash
mvn help:effective-pom
```

Đừng nhầm “POM nguồn không khai báo repository” với “Maven không thể truy cập repository”. Cần xét Super POM, settings, profiles, mirrors và các chính sách mạng.

### 4.2. Tại sao Maven Central có thể không phải URL cuối của request?

Một repository manager hoặc mirror có thể thay endpoint của `central`. Ví dụ:

```text
POM cần: org.apache.commons:commons-lang3:3.14.0
Repository logic: central
Mirror có hiệu lực: company-mirror
Kết nối HTTP thực: repository manager nội bộ
Nguồn upstream mà manager proxy: Maven Central
```

Đây là **luồng giả định**, không phải địa chỉ mạng của người học. Nó cho thấy việc thay tuyến tải về không nhất thiết thay đổi dependency coordinates trong `pom.xml`.

## 5. Thực hành Java 17: tải thư viện thực từ Central

Ví dụ bên dưới tạo một project nhỏ dùng **Apache Commons Lang 3.14.0**. Đây là dependency công khai có tọa độ:

```text
org.apache.commons:commons-lang3:3.14.0
```

Mục tiêu là quan sát Maven giải quyết artifact theo GAV, tải qua remote repository khi cần và lưu vào local repository; sau đó chạy ứng dụng có dependency đó trên classpath.

Yêu cầu: **JDK 17+**, Maven phiên bản tương thích với các plugin được khai báo, mạng truy cập repository khi local cache chưa có, và quyền ghi thư mục build/cache. Nếu máy dùng mirror công ty, cấu hình mạng/phân quyền của mirror cũng phải hợp lệ.

### 5.1. Cấu trúc

```text
central-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── org/example/repository/
                └── App.java
```

Linux/macOS:

```bash
mkdir -p central-demo/src/main/java/org/example/repository
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path "central-demo/src/main/java/org/example/repository" | Out-Null
```

### 5.2. POM hoàn chỉnh: `central-demo/pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.training</groupId>
    <artifactId>central-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
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
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.8.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**Điểm cần quan sát:**

- POM **không có `<repositories>`**. Maven dùng repository mặc định và những cấu hình môi trường thích hợp.
- Dependency trỏ đến **tọa độ công khai** của Commons Lang, không trỏ tới một file `.jar` trên đĩa.
- Scope của dependency không được viết, nên là `compile` mặc định.
- Phiên bản Maven Compiler Plugin được ghi rõ; `maven.compiler.release=17` cấu hình mục tiêu Java 17.
- Maven Dependency Plugin được khai báo phiên bản để lệnh `dependency:copy-dependencies` có thể hoạt động nhất quán.
- Project có `packaging=jar`; việc tạo một JAR mặc định **không tự nhúng Commons Lang vào JAR app**.

### 5.3. Java source: `central-demo/src/main/java/org/example/repository/App.java`

```java
package org.example.repository;

import org.apache.commons.lang3.StringUtils;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("blank=" + StringUtils.isBlank(" \t"));
        System.out.println("reverse=" + StringUtils.reverse("Maven"));
    }
}
```

`StringUtils` là class của Commons Lang; project Java này không thể compile chỉ bằng standard JDK nếu Commons Lang không có trên classpath. Maven sẽ dùng dependency đã khai báo để cung cấp class đó trong compile.

Hai lời gọi có kết quả xác định:
- `isBlank(" \t")` trả về `true` vì chuỗi chỉ gồm khoảng trắng và ký tự tab.
- `reverse("Maven")` trả về `nevaM`.

### 5.4. Build và quan sát việc tải artifact

Đứng ở **thư mục cha của `central-demo`**:

```bash
mvn -version
mvn -B -ntp -f central-demo/pom.xml clean package dependency:copy-dependencies
```

Khi local repository chưa có các artifact cần thiết, Maven có thể tải:
- Maven plugins và dependencies của chính plugins.
- POM/JAR của Commons Lang.
- Những thông tin phụ thuộc/metadata khác nếu có.

Đường dẫn/tên của mỗi log tải và thời gian thực hiện phụ thuộc Maven version, local cache, mirror và mạng. **Không khẳng định mỗi lần chạy đều phải tải lại từ Central.**

Sau khi thành công, project thường có:

```text
central-demo/
└── target/
    ├── classes/org/example/repository/App.class
    ├── central-demo-1.0.0.jar
    └── dependency/commons-lang3-3.14.0.jar
```

`dependency:copy-dependencies` là goal riêng, được gọi trong lệnh trên để đặt JAR dependency vào `target/dependency`; nó **không phải bước tự động của mọi `mvn package`**.

### 5.5. Chạy chương trình: classpath phải có dependency

Linux/macOS:

```bash
java -cp "central-demo/target/classes:central-demo/target/dependency/*" org.example.repository.App
```

Windows PowerShell:

```powershell
java -cp "central-demo\target\classes;central-demo\target\dependency\*" org.example.repository.App
```

**Stdout chính xác** nếu build và lệnh chạy thành công:

```text
blank=true
reverse=nevaM
```

Dấu `:` là classpath separator trên Linux/macOS; `;` là separator trên Windows. Ký tự `*` trong thư mục dependency được **Java launcher** hỗ trợ để mở rộng các file JAR trực tiếp trong thư mục đó.

Đừng thử chạy `java -jar central-demo/target/central-demo-1.0.0.jar` rồi kết luận dependency thiếu do Maven Central hỏng: JAR mặc định thường chưa có `Main-Class` trong manifest và không tự chứa dependency. Đây là vấn đề launcher/packaging, không phải vấn đề Maven Central.

### 5.6. Quan sát dependency tree và local repository

Sau build, chạy từ thư mục cha:

```bash
mvn -f central-demo/pom.xml dependency:tree
```

Phần liên quan của cây dependency được kỳ vọng có tọa độ dạng:

```text
org.example.training:central-demo:jar:1.0.0
\- org.apache.commons:commons-lang3:jar:3.14.0:compile
```

Đây là **đoạn cây minh họa**, không phải toàn bộ log; phiên bản plugin có thể định dạng khác.

Với layout local repository mặc định truyền thống, Commons Lang có thể nằm dưới:

```text
~/.m2/repository/org/apache/commons/commons-lang3/3.14.0/
```

Việc kiểm tra đường dẫn phục vụ học tập; **không sửa file cache bằng tay**. Nếu local repository được cấu hình khác hoặc dùng cơ chế layout/split khác, đường dẫn thực có thể khác ví dụ.

### 5.7. Thử chế độ offline

Sau khi toàn bộ dependencies và plugins **cần cho lệnh thử** đã có sẵn trong local repository phù hợp:

```bash
mvn -o -f central-demo/pom.xml package
```

`-o` là offline mode. Nếu thành công, nó minh họa Maven có thể dùng artifact local khi không cần truy cập remote repository.

**Nhưng không bảo đảm offline sẽ thành công trên máy khác.** Nó có thể thất bại nếu máy còn thiếu plugin, artifact, POM, metadata hoặc cache không đáp ứng repository context. Hai máy không có local cache giống nhau dù dùng chung Git commit.

Tránh kết luận “dự án không còn phụ thuộc remote repository” chỉ vì một lần offline build thành công trên máy cá nhân.

## 6. Local cache khác artifact tự cài bằng Maven install

Giả sử bạn tạo một thư viện nội bộ:

```text
com.example.training:math-tools:1.0.0
```

Nếu dự án thư viện có POM đúng tọa độ và chạy:

```bash
mvn clean install
```

artifact được cài vào local repository của **máy đang chạy lệnh**. Project khác trên cùng máy có thể tham chiếu:

```xml
<dependency>
    <groupId>com.example.training</groupId>
    <artifactId>math-tools</artifactId>
    <version>1.0.0</version>
</dependency>
```

Đây là đoạn XML minh họa trong POM consumer. Việc cài library trên máy A **không tự cài nó trên máy B hoặc CI runner**. Nếu mã nguồn consumer được push lên Git, những người khác vẫn cần một nguồn artifact có thể truy cập.

**So sánh:**

| Hành động | Artifact đến đâu? | Máy khác tự có ngay không? |
| --- | --- | --- |
| `mvn package` | `target` của project. | Không. |
| `mvn install` | `target` và local Maven repository của máy chạy. | Không. |
| `mvn deploy` | Remote repository được cấu hình để publish, khi có quyền. | Máy khác có thể tải theo tọa độ khi được cấp quyền. |
| Tải dependency từ Central | Local cache của máy đang build. | Máy khác tải riêng khi cần hoặc đi qua proxy cache. |
| Chép JAR vào `lib/` bằng tay | Thư mục do người dùng chọn. | Không trở thành artifact Maven theo tọa độ chỉ nhờ chép file. |

### 6.1. Nếu chỉ có JAR bên ngoài Maven

Maven Install Plugin có goal `install:install-file` để cài một JAR có quyền sử dụng vào local repository dưới tọa độ chỉ định.

Ví dụ cú pháp một dòng:

```bash
mvn org.apache.maven.plugins:maven-install-plugin:3.2.0:install-file -Dfile=/path/to/approved-library.jar -DgroupId=com.example.training -DartifactId=approved-library -Dversion=1.0.0 -Dpackaging=jar
```

Đường dẫn `/path/to/approved-library.jar` là ví dụ Linux/macOS và **phải thay bằng file thật**; trên Windows dùng đường dẫn phù hợp. Lệnh không tạo JAR từ hư không, không kiểm tra quyền phân phối thay bạn và **không upload lên Central**. Nếu nhà cung cấp có POM mô tả dependencies, cần dùng metadata hợp lệ thay vì giả định JAR không phụ thuộc gì.

**Đừng dùng install-file để che giấu một quy trình phân phối thiếu chuẩn**: trong team lớn, repository manager có phân quyền là lựa chọn tốt hơn nếu được phép publish.

## 7. Remote repository nội bộ và repository manager

Trong tổ chức, nhiều máy CI và developer có thể cần:
- Artifact private không tồn tại ở Central.
- Proxy/cache cho Maven Central để tiết kiệm bandwidth.
- Kiểm soát license, lỗ hổng, provenance và nguồn artifact.
- Phân quyền cho deploy releases/snapshots.
- Tính sẵn sàng và logging truy cập.

Một **repository manager** thường gom các vai trò này lại và cung cấp một endpoint dùng chung cho Maven:

```text
                  Developer / CI
                         |
                         v
               Repository manager
                 (endpoint nhóm)
                /      |       \
               /       |        \
              v        v         v
     Hosted releases  Hosted      Proxy/cache
       riêng          snapshots   Maven Central
                                      |
                                      v
                                 Maven Central
```

Cách cấu hình cụ thể phụ thuộc sản phẩm và chính sách tổ chức. Maven client có thể dùng một endpoint group để resolve, trong khi repository manager quản lý nhiều kho upstream. Đây là mô hình thường được chọn hơn việc cấu hình vô số URL riêng trong từng POM.

**Không phải mọi repository manager đều là Maven Central.** Nó có thể **proxy Central**; vai trò proxy/cache không biến artifact private thành artifact được publish công khai lên Central.

### 7.1. Dùng mirror trong settings.xml

Ví dụ settings khai báo thay tuyến tải từ repository logic `central`:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0
                              https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <mirrors>
        <mirror>
            <id>company-mirror</id>
            <name>Example corporate Maven mirror</name>
            <url>https://repo.example.invalid/repository/maven-public/</url>
            <mirrorOf>central</mirrorOf>
        </mirror>
    </mirrors>
</settings>
```

Đây là **tệp minh họa không thể kết nối thực tế** do sử dụng miền `example.invalid`. Trong thực tế, URL phải được bộ phận quản trị cung cấp; ID là tên logic. Với `mirrorOf=central`, Maven có thể dùng endpoint đó khi cần truy cập repository có ID `central`.

Cần hiểu đúng:
- `mirrorOf` **khớp repository ID**, không phải substring trong URL.
- `mirrorOf=central` chỉ thay tuyến những repository có ID `central`.
- `mirrorOf=*` có thể áp dụng rộng cho các repository; endpoint group được chọn phải phục vụ được toàn bộ artifact cần thiết hoặc proxy những nguồn thích hợp.
- `external:*` thường áp dụng các repository không phải localhost/file; cần dùng theo chính sách mạng.
- Maven **không cộng tất cả mirror phù hợp như nhiều nguồn tìm kiếm độc lập**; mirror selection có quy tắc matching, mỗi remote repository được gắn với một mirror được chọn.
- Nếu mirror nội bộ gặp lỗi, Maven có thể không tự “bỏ qua mirror để tải thẳng Central”; đó có thể là chính sách mạng cố ý.

Điều này cho phép tổ chức giữ POM không chứa URL private không cần thiết, đồng thời quản lý mạng trong settings/user hoặc CI runner.

### 7.2. Phân biệt mirror và thêm repository

**Mirror:** thay endpoint mà Maven sử dụng cho một repository hiện có được match theo ID/quy tắc `mirrorOf`.

**Thêm repository:** khai báo một nguồn artifact bổ sung qua `<repositories>` hoặc settings profiles.

Maven không mặc định “thử mọi mirror theo thứ tự” như một danh sách fallback. Nếu muốn gộp nhiều kho upstream thành một endpoint có chính sách thống nhất, dùng repository manager thay vì tạo nhiều mirror cho cùng một repository.

## 8. Deploy artifact: đích publish không phải nguồn download

Để publish release của một project Maven, cấu hình thường là:

```xml
<distributionManagement>
    <repository>
        <id>company-releases</id>
        <url>https://repo.example.invalid/repository/maven-releases/</url>
    </repository>
    <snapshotRepository>
        <id>company-snapshots</id>
        <url>https://repo.example.invalid/repository/maven-snapshots/</url>
    </snapshotRepository>
</distributionManagement>
```

Đây là **đoạn bên trong POM của project được phép publish**. Endpoint `example.invalid` chỉ dùng để giải thích. Khi chạy:

```bash
mvn clean deploy
```

Maven Deploy Plugin có thể upload artifact và POM theo repository tương ứng, **nếu cấu hình và quyền đều hợp lệ**. Nó không biến project thành artifact public trên Central chỉ vì Maven Central là nguồn tải về mặc định.

Thông tin xác thực thường liên kết qua `server.id` trong settings:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <servers>
        <server>
            <id>company-releases</id>
            <username>EXAMPLE_USER_NOT_REAL</username>
            <password>EXAMPLE_PASSWORD_NOT_REAL</password>
        </server>
    </servers>
</settings>
```

Đây là **dữ liệu giả minh họa**, tuyệt đối không sao chép password thật vào ví dụ, Git, screenshot hoặc log. Trong môi trường làm việc, lưu credentials bằng cơ chế được phê duyệt và cấp cho Maven trong settings/CI secrets một cách hạn chế quyền.

**ID phải khớp đúng mục tiêu kết nối** mà Maven đang dùng. Với mirror, server ID dùng cho xác thực download qua mirror thường liên quan đến **ID của mirror đã chọn**; với deploy, ID trong `distributionManagement` cần có cấu hình server phù hợp.

### Publish lên Maven Central có phải chỉ chạy `mvn deploy`?

Không. Quy trình đưa artifact công khai lên Maven Central cần **quyền sở hữu namespace, tài khoản/authorization, metadata và quy trình publish hợp lệ** thông qua hệ thống được Central chấp nhận. Không thể mặc định upload được bằng lệnh Maven bất kỳ mà không cấu hình/được cấp quyền.

Trong doanh nghiệp, phần lớn mã private nên được publish vào repository nội bộ theo chính sách; không upload mã/bytecode độc quyền lên Central.

## 9. Chính sách release, SNAPSHOT và metadata

Maven phân biệt release và snapshot ở nhiều ngữ cảnh repository.

**Release** thường có version như `1.4.0`; một artifact release được quản trị tốt nên **bất biến tại tọa độ** đó. Không thay JAR đã công bố mà giữ nguyên GAV, vì nó phá kỳ vọng tái lập.

**SNAPSHOT** dùng version có hậu tố `-SNAPSHOT`, ví dụ `1.4.1-SNAPSHOT`. Remote repository có thể lưu snapshot với timestamp/build number để phân biệt các lần publish; local Maven repository có quy tắc xử lý version/baseVersion tương ứng.

Repository có thể đặt policy:

```xml
<repository>
    <id>company-snapshots</id>
    <url>https://repo.example.invalid/repository/maven-snapshots/</url>
    <releases>
        <enabled>false</enabled>
    </releases>
    <snapshots>
        <enabled>true</enabled>
        <updatePolicy>daily</updatePolicy>
    </snapshots>
</repository>
```

Đây là XML minh họa dùng trong `<repositories>` của một POM. Không chạy endpoint `example.invalid` như repository thật.

### Metadata có tác dụng gì?

Một thư mục artifact có thể có `maven-metadata.xml` liệt kê version hoặc metadata SNAPSHOT:

```text
org/example/training/demo-core/
    maven-metadata.xml
    1.0.0/
    1.1.0/
    1.2.0-SNAPSHOT/
```

Maven sử dụng metadata trong một số hoạt động version/snapshot resolution. Khi POM dùng một version range, những version thực sự khả dụng ở repository và metadata cache có thể ảnh hưởng kết quả.

### Update policy và cache

Tùy cấu hình, repository policy có thể gồm:
- `always`: xem xét cập nhật thường xuyên.
- `daily`: theo chu kỳ hằng ngày, là mặc định phổ biến.
- `interval:30`: theo chu kỳ khoảng 30 phút.
- `never`: không chủ động kiểm tra cập nhật theo policy đó.

Tùy phiên Maven, cache, repository/metadata và kiểu artifact, những quy tắc này ảnh hưởng thời điểm Maven thấy bản mới. **Không dùng `-U` như cách giải quyết mọi lỗi**, vì nó không tự tạo một artifact không tồn tại hoặc sửa credentials sai.

## 10. Hành trình một dependency: từ POM đến classpath

Xét dependency:

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.14.0</version>
</dependency>
```

Quá trình có thể hiểu như sau:

1. Maven đọc POM của dự án, parent, profiles và dependency management để hình thành mô hình có hiệu lực.
2. Resolver cần tìm artifact `org.apache.commons:commons-lang3:3.14.0` và metadata phù hợp.
3. Resolver kiểm tra local repository theo **quy tắc nhận diện artifact đã cài/cache và nguồn gốc repository**.
4. Nếu còn thiếu hoặc cần cập nhật, Maven xác định remote repository phù hợp, áp dụng mirror/repository policy.
5. Maven tải POM/JAR/metadata cần thiết và cache vào local repository theo cơ chế được hỗ trợ.
6. Từ POM của dependency, Maven có thể thu thập các dependencies bắc cầu.
7. Với scope/conflict management, Maven xác định tập artifact cần cho compile/test/runtime.
8. Plugin compiler/test/package sử dụng classpath và cấu hình tương ứng để thực hiện goal.

**Thứ tự nội bộ không đơn giản là “có file thì bỏ qua mạng” cho mọi trường hợp.** Snapshot, metadata động, cache lỗi, repository origin và update policy có thể khiến Maven kiểm tra thông tin mới.

### POM có dependency không đồng nghĩa JAR đã trên runtime classpath

Một thư viện có `scope=test` chỉ xuất hiện trong ngữ cảnh test, một thư viện `provided` kỳ vọng runtime cung cấp bên ngoài, còn dependency `optional` hay `exclusions` có thể ảnh hưởng truyền bắc cầu.

Ngoài ra, Maven plugins có graph riêng. Một JAR cần bởi plugin có thể nằm trong cache dù không xuất hiện trong `dependency:tree` của dependencies ứng dụng.

## 11. Kiểm tra Maven đang thực sự dùng kho nào

### 11.1. Xác định Maven và JDK

```bash
mvn -version
```

Lệnh này giúp xác minh Maven version, Java version, Java home và hệ điều hành được báo. Nó không cho biết toàn bộ nội dung repository; muốn chẩn đoán phải kết hợp lệnh khác.

### 11.2. Xem effective POM

```bash
mvn -f central-demo/pom.xml help:effective-pom
```

Xem những phần `repositories`, `pluginRepositories` và dependency version trong mô hình. Có thể thấy Central do Super POM cung cấp hoặc những repository từ profile/parent.

**Nhưng effective POM không nói đầy đủ Maven kết nối tới URL nào cuối cùng sau mirror selection.** Một mirror trong settings có thể thay URL mà Maven thực sự truy cập.

### 11.3. Xem effective settings một cách an toàn

```bash
mvn help:effective-settings
```

Goal này giúp kiểm tra `localRepository`, `mirrors`, `servers`, `proxies` và các profile settings có hiệu lực. Theo tài liệu Maven Help Plugin, `showPasswords` mặc định là `false`, nhưng **output vẫn có thể chứa username, hostname nội bộ, URL riêng, path hoặc token trong trường khác**.

Không đính kèm toàn bộ effective settings hoặc `settings.xml` vào issue công khai. Khi chia sẻ sự cố, chỉ gửi bản tóm tắt đã kiểm duyệt, ví dụ “mirror ID X được chọn; artifact Y trả 401”, không gửi username/password/token.

### 11.4. Xem dependency tree

```bash
mvn -f central-demo/pom.xml dependency:tree
```

Goal này cho biết project đang dùng phiên bản dependency nào và nhánh bắc cầu tương ứng. Nó **không phải lệnh hiển thị mọi JAR đang nằm trong local repository**.

### 11.5. Chỉ xem log tải khi thật sự cần

Maven log có thể có dòng dạng:

```text
Downloading from central: ...
Downloaded from central: ...
```

Với mirror, repository ID hiện trong log có thể là tên mirror. **Không nên dùng log tải như bằng chứng duy nhất về độ tin cậy artifact**; nó chỉ giúp chẩn đoán nguồn resolution trong lần chạy.

Tùy chọn `-X` có thể thêm chi tiết debug, nhưng trước khi dùng trên CI hay gửi log ra ngoài, phải xem chính sách bảo mật: debug/log có thể chứa đường dẫn, URL nội bộ hoặc dữ liệu nhạy cảm khác.

## 12. Offline mode và CI cache: hiểu đúng khả năng của local repository

Sau khi một máy build thành công, `mvn -o ...` có thể dùng dependencies đã cache:

```bash
mvn -o -f central-demo/pom.xml package
```

Nhưng cần phân biệt:

- **Offline không có nghĩa build tái lập:** máy khác có thể có cache phiên bản khác hoặc thiếu POM/plugin.
- **Cache không phải kho artifact dùng chung:** job CI độc lập không tự nhìn thấy local cache trên máy developer.
- **Warm cache có thể che thiếu khai báo:** một artifact được cài thủ công từ trước có thể khiến dự án chạy được trên máy cá nhân dù remote repository không có nó.
- **Version range và SNAPSHOT có thể thay đổi:** cache/metadata làm kết quả giữa môi trường khác nhau, ngay cả khi POM không đổi.
- **Dọn cache có thể khiến lỗi xuất hiện trở lại:** không nên cho rằng lỗi mới sau khi dọn cache là lỗi của mã nguồn.
- **Cache không thay thế quyền truy cập:** artifact private cần quyền hợp lệ để download vào môi trường sạch.

Một pipeline tin cậy nên:

1. Pin hoặc quản lý phiên bản dependencies/plugins quan trọng.
2. Dùng repository manager được cấp quyền cho artifact private và proxy Central.
3. Xác định cache key/retention phù hợp; tránh chia sẻ cache ghi giữa những tiến trình không được phối hợp an toàn.
4. Định kỳ chạy build trên runner sạch để phát hiện dependency “chỉ có trên máy tôi”.
5. Kiểm tra license, checksum/provenance và quét lỗ hổng theo chính sách.
6. Không in credentials/repository settings nguyên bản vào CI logs.

**Không xóa cache của cả hệ thống CI bằng tay** khi chưa xác định tính chất shared/cross-job; việc này có thể ảnh hưởng những pipeline khác và gây tải lại lớn.

## 13. Những lỗi repository Maven thường gặp

### Lỗi A — `Could not find artifact` hoặc `Could not resolve dependencies`

Có thể do:
- GAV sai hoặc version chưa được publish.
- Artifact chỉ có ở private repository nhưng POM/settings không khai báo đúng nguồn.
- Mirror chặn truy cập kho đúng hoặc không proxy được artifact cần thiết.
- Release/SNAPSHOT policy không cho tải loại version đó.
- Metadata/cache lỗi hoặc repository đang tạm thời không sẵn sàng.

Cách xử lý: xác nhận GAV chính xác từ nguồn artifact có thẩm quyền, kiểm tra repository/mirror và thử resolve trong môi trường được cấp quyền. **Không sửa bằng cách tải JAR tùy ý từ website lạ rồi chép thẳng vào cache Maven.**

### Lỗi B — `401 Unauthorized` hoặc `403 Forbidden`

Đây là lỗi truy cập/quyền, không tự chứng minh artifact không tồn tại. Kiểm tra:
- Server ID và mirror ID thực sự được dùng.
- Credentials trong settings/CI secret store.
- Token hết hạn hoặc tài khoản thiếu quyền.
- Chính sách repository cho artifact/path cần tải hoặc deploy.

Không đăng `settings.xml` chứa secrets; khi gửi log, phải lược bỏ URL/token/username nội bộ nếu cần.

### Lỗi C — `PluginResolutionException` hoặc không tìm thấy plugin

Maven plugins cần được tải từ plugin repository. Kiểm tra `pluginRepositories`, mirror, repository manager và plugin version. Đừng chỉ thêm `<repositories>` rồi kỳ vọng plugin resolution chắc chắn được sửa.

### Lỗi D — Máy local build được, CI sạch không build được

Nguyên nhân thường gặp là:
- Artifact đã được cài bằng `mvn install` hoặc `install-file` chỉ trên máy cá nhân.
- CI runner chưa có cache và không truy cập được repository cần thiết.
- Settings/mirror/proxy của CI khác local.
- Dùng snapshot hoặc version range làm graph khác đi.
- CI bị hạn chế network/TLS/credentials.

Cách xử lý: xác định artifact nào chỉ có trong local repository, sau đó publish hợp lệ vào repository dùng chung hoặc điều chỉnh cấu hình resolution đúng. Không chép nguyên local repo từ laptop sang CI như một giải pháp quản trị lâu dài.

### Lỗi E — `Non-resolvable parent POM`

Maven cần giải quyết parent POM **trước khi hình thành đầy đủ mô hình con**. Parent có thể nằm ở `relativePath` hoặc repository thích hợp. Nếu parent chỉ được cài trong local repo máy A, máy B thiếu parent sẽ lỗi.

Kiểm tra parent `groupId:artifactId:version`, `relativePath` và chính sách publish parent. Không nhầm parent POM với dependency JAR compile.

### Lỗi F — SNAPSHOT không đổi hoặc thay bất ngờ

Snapshot metadata và update policy có thể khiến các môi trường nhìn thấy build timestamp khác nhau. Kiểm tra remote snapshot repository, Maven version, offline flag, metadata update và local cache. Với release cần tái lập, ưu tiên release artifacts bất biến.

### Lỗi G — HTTP/TLS/proxy/network

Một repository URL HTTP thuần túy có thể bị chặn bởi chính sách Maven hiện đại hoặc mạng doanh nghiệp. Kiểm tra HTTPS, certificate truststore, proxy, mirror và khả năng kết nối thực. **Không tắt kiểm tra TLS/chứng chỉ bừa bãi** chỉ để build qua được; yêu cầu người quản trị cung cấp certificate và cấu hình phù hợp.

### Lỗi H — Lỗi cache một lần trước đó bị ghi nhớ

Maven có thể cache thông tin một lần resolution thất bại và từ chối thử lại ngay tùy chính sách. Xem log về “resolution will not be reattempted until update interval...” và kiểm tra artifact/repository thực. `-U` có thể hữu ích trong một số tình huống cập nhật metadata/missing artifacts, nhưng **không chữa được GAV sai, thiếu quyền hay remote repository không có file**.

### Lỗi I — Khác biệt giữa dependency repository và deploy repository

Project có `<repositories>` để download nhưng `mvn deploy` không có `distributionManagement` thích hợp, hoặc server ID không có credentials upload. Hai hướng này cần cấu hình phù hợp riêng. Central là nguồn tải public mặc định, không phải đích deploy mặc định của một project private.

## 14. Cấu hình repo an toàn và dễ bảo trì

Một số nguyên tắc thực tế:

1. **Không khai báo lại Central ở mọi POM** nếu chỉ dùng mặc định; điều đó tăng lặp và có thể gây hiểu nhầm.
2. **Ưu tiên dùng HTTPS và repository manager đáng tin cậy** cho mạng doanh nghiệp; tránh các URL lạ có thể thay thế artifact cùng tọa độ.
3. **Đặt thông tin xác thực ở settings/CI secret manager**, không hardcode password hoặc token vào POM.
4. **Phân biệt repository để tải dependency, plugin repository và deploy repository.**
5. **Không publish artifact private lên Central** nếu tổ chức không có quyền/phê duyệt.
6. **Giữ release artifacts bất biến**; nếu phát hiện lỗi, phát hành version mới thay vì ghi đè binary cũ.
7. **Không phụ thuộc vào một local cache đặc biệt** để build được; thử từ môi trường sạch.
8. **Không sửa cache bằng tay** hoặc coi folder layout như API được bảo đảm.
9. **Pin phiên bản Maven plugins/dependencies quan trọng** để giảm khác biệt khi build.
10. **Theo dõi repository metadata, scopes, mirror và network** khi sự cố chỉ xảy ra trên một máy.
11. **Kiểm tra integrity và nguồn gốc artifact**, vì việc tải được từ repository không tự bảo đảm tính an toàn của thư viện.
12. **Dùng nguyên tắc ít đặc quyền**: tài khoản CI chỉ được đọc những kho cần dùng; quyền deploy cấp cho pipeline phù hợp, không dùng một tài khoản có mọi quyền cho mọi job.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Nếu POM không có `<repositories>`, Maven có mặc định không thể tải dependency từ mạng không?

**Đáp án:** Không. Maven thông thường có Maven Central trong cấu hình mặc định qua Super POM; settings/mirror có thể thay endpoint thực tế.

**Câu 2.** Artifact đã tải một lần từ Central được lưu ở đâu?

**Đáp án:** Trong local Maven repository theo cơ chế cache của Maven Resolver, mặc định thường dưới `~/.m2/repository`. Không nhầm nó với thư mục `target`.

**Câu 3.** `mvn install` và `mvn deploy` khác nhau ở đâu?

**Đáp án:** `install` cài artifact vào local repository trên máy chạy; `deploy` upload artifact lên remote repository được cấu hình và cấp quyền. Chạy install không tự publish công khai.

**Câu 4.** Tại sao cùng POM dùng Commons Lang nhưng máy A tải từ `repo.maven.apache.org` còn máy B truy cập repository nội bộ?

**Đáp án:** Máy B có thể đang dùng mirror hoặc repository manager proxy Central qua settings. Artifact coordinates trong POM vẫn có thể giống hệt.

**Câu 5.** Nếu tổ chức có một library chỉ được cài bằng `mvn install:install-file` trên laptop, CI runner mới có tự lấy được từ Central không?

**Đáp án:** Không, trừ khi library đó thực sự đã được publish dưới tọa độ đúng ở remote repository mà CI có quyền truy cập. Local install không phân phối artifact sang máy khác.

**Câu 6.** Vì sao `dependency:tree` không phải danh sách toàn bộ file trong `~/.m2/repository`?

**Đáp án:** Tree mô tả dependencies đã giải quyết cho một project, còn local repo có thể chứa artifact của nhiều project và Maven plugins từ nhiều lần build.

**Câu 7.** Mirror `mirrorOf=central` làm gì?

**Đáp án:** Nó thay endpoint truy cập repository có ID `central` theo mirror selection; không tự thêm một dependency và không có nghĩa mọi repository khác cũng bị mirror.

**Câu 8.** Khi `mvn -o package` thành công trên máy cá nhân, có thể khẳng định CI sạch offline cũng chạy được không?

**Đáp án:** Không. CI có thể thiếu cache hoặc có repository context khác; offline không tự phân phối dependencies.

**Câu 9.** Một dependency JAR đã có trong local repo nhưng không tải được parent POM. Maven có nhất thiết build được không?

**Đáp án:** Không. Maven có thể cần giải quyết parent/POM metadata để hình thành mô hình và dependency graph; chỉ có JAR chưa đủ.

**Câu 10.** Trong ví dụ `central-demo`, nếu chạy `java -jar target/central-demo-1.0.0.jar` mà không được, có thể kết luận Maven Central thiếu Commons Lang không?

**Đáp án:** Không. JAR mặc định chưa chắc có Main-Class và không tự chứa dependency. Cần launcher/classpath hoặc cấu hình packaging thích hợp.

**Câu 11.** `<repositories>` và `<distributionManagement>` có cùng chức năng không?

**Đáp án:** Không. `repositories` chủ yếu mô tả nguồn dependency download; `distributionManagement` mô tả đích publish artifact của project.

**Câu 12.** Vì sao repository manager nội bộ thường hữu ích khi có nhiều dự án và CI?

**Đáp án:** Nó có thể cung cấp cache/proxy Central, lưu artifact private, kiểm soát quyền, nguồn artifact, policy và tính sẵn sàng theo quy trình tổ chức.

## Tài liệu tham khảo chính thức

- [Apache Maven – Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html): local/remote repositories, mặc định tải từ Central, offline, deploy và internal repositories.
- [Apache Maven – Maven Repositories](https://maven.apache.org/repositories/): tổng quan kho artifact, tọa độ, metadata, layout và cách Maven tiếp cận remote.
- [Apache Maven – Maven Local Repositories](https://maven.apache.org/repositories/local.html): cache và installed artifacts, split local repository và lý do không thao tác trực tiếp nội dung cache.
- [Apache Maven – Using Mirrors for Repositories](https://maven.apache.org/guides/mini/guide-mirror-settings.html): `mirrorOf`, ID `central`, lựa chọn mirror và repository manager.
- [Apache Maven – Settings Reference](https://maven.apache.org/settings.html): `localRepository`, `mirrors`, `servers`, `proxies`, `profiles` và update policies.
- [Apache Maven – POM Reference](https://maven.apache.org/pom.html): `repositories`, `pluginRepositories`, `distributionManagement`, dependency coordinates và Super POM.
- [Apache Maven – Maven Central Repository](https://maven.apache.org/repository/): thông tin sử dụng và publish vào Central.
- [Apache Maven – Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): transitive dependencies và classpath.
- [Apache Maven Dependency Plugin – dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): xem đồ thị dependency đã được resolve.
- [Apache Maven Dependency Plugin – dependency:copy-dependencies](https://maven.apache.org/plugins/maven-dependency-plugin/copy-dependencies-mojo.html): sao chép JAR dependency đã giải quyết phục vụ quan sát runtime classpath.
- [Apache Maven Install Plugin – install:install-file](https://maven.apache.org/plugins/maven-install-plugin/install-file-mojo.html): cài JAR bên ngoài Maven vào local repository.
