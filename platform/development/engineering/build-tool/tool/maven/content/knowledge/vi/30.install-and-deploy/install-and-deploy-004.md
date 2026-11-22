# repository, snapshotRepository và chính sách chia tách trong Maven

## 1. Bài toán: vì sao phải tách repository phát hành?

Trong chủ đề **Install và Deploy** của Apache Maven, điều quan trọng không chỉ là lệnh `mvn deploy` tải artifact lên đâu, mà còn là **artifact đó thuộc kênh phát triển SNAPSHOT hay kênh phát hành RELEASE**.

Một nhóm thường có hai loại bản dựng:

- **SNAPSHOT**: bản đang phát triển, ví dụ `1.4.0-SNAPSHOT`. Nội dung có thể thay đổi giữa các lần build/deploy; thích hợp cho môi trường tích hợp, thử nghiệm với nhánh phát triển.
- **RELEASE**: bản phát hành chính thức, ví dụ `1.4.0`. Nên bất biến sau khi publish, có quy trình phê duyệt, kiểm tra và truy vết nguồn rõ ràng.

Nếu cùng đẩy cả hai vào một kho mà không có chính sách, consumer có thể tải nhầm phiên bản thử nghiệm, người quản trị khó quản lý retention, quyền ghi và tính bất biến; quy trình rollback, audit hoặc promotion cũng dễ nhầm. Maven có cấu hình **`distributionManagement`**, trong đó:

- **`<repository>`**: đích deploy thông thường, thường được dùng cho RELEASE.
- **`<snapshotRepository>`**: đích deploy riêng dành cho phiên bản kết thúc bằng `-SNAPSHOT`.
- Nếu **không có `snapshotRepository`**, Maven có thể dùng `repository` làm đích cho cả SNAPSHOT. Do đó muốn **chia tách thực sự** cần khai báo đúng cả hai và cấu hình chính sách ở repository manager.

Sơ đồ:

```text
Maven project, groupId/artifactId/version
            |
            v
       mvn deploy
            |
            +-- 1.4.0-SNAPSHOT ----> snapshotRepository
            |                         (snapshots repository)
            |
            +-- 1.4.0 -----------> repository
                                      (releases repository)
```

**Đừng lẫn `distributionManagement/repository` với `project/repositories/repository`.** Một bên định nghĩa **đích tải lên artifacts của dự án**, một bên định nghĩa **nguồn tải xuống dependencies**. Đây là khác biệt cốt lõi của bài học.

## 2. Install, deploy và consumption khác nhau thế nào?

| Hoạt động | Maven phase/cơ chế | Nơi dữ liệu đi đến hoặc được đọc |
| --- | --- | --- |
| Compile/test/package | `mvn package` | Output dưới `target/` |
| Kiểm tra đầy đủ | `mvn verify` | Kết quả QA/test, chưa mặc nhiên publish |
| Install | `mvn install` | **Local Maven repository** của máy/runner |
| Deploy | `mvn deploy` | **Remote deployment repository** theo `distributionManagement`/override |
| Consumer resolve dependency | `<dependencies>` cùng danh sách download repos | Local cache trước, rồi remote repositories cho phép |
| Upload site docs | `distributionManagement/site` với plugin/site deployment phù hợp | **Khác** artifact deployment |
| Deploy file lẻ | `deploy:deploy-file` | Một artifact độc lập theo tham số plugin; khác project deploy lifecycle |

Theo default lifecycle, gọi `mvn deploy` cũng đi qua các phase trước nó, trong đó có package, verify và install (trừ cấu hình/flags/plugin behavior thay đổi). **`mvn deploy` không phải cách viết khác của `mvn install`**.

Local repository mặc định thường ở `~/.m2/repository` nhưng có thể được đặt bằng `settings.xml` hoặc `-Dmaven.repo.local`. Một JAR trong `target/` **chưa phải** artifact đã deploy.

Maven Deploy Plugin có trách nhiệm publish nhiều thành phần nhất quán với artifact: JAR/WAR, POM, attached artifacts, metadata, checksums tương ứng tùy cấu hình và repository implementation. Nó không chỉ copy một file JAR thủ công.

## 3. Cấu trúc distributionManagement

Mẫu chính sách hai kênh trong `pom.xml`:

```xml
<distributionManagement>
    <repository>
        <id>company-releases</id>
        <name>Company Maven Releases</name>
        <url>https://repo.example.invalid/repository/maven-releases/</url>
    </repository>

    <snapshotRepository>
        <id>company-snapshots</id>
        <name>Company Maven Snapshots</name>
        <url>https://repo.example.invalid/repository/maven-snapshots/</url>
    </snapshotRepository>
</distributionManagement>
```

**Đây là đoạn cấu hình minh họa cho repository manager, không phải địa chỉ máy chủ thật**. Domain `example.invalid` không dùng để deploy. Trong project thực tế, thay bằng HTTPS URL của repository manager đã được quản trị cấp phép.

Giải thích các phần:

| Element | Vai trò |
| --- | --- |
| `distributionManagement` | Cấu hình thông tin **phát hành** artifact/site |
| `repository` | Đích deploy release; cũng có thể là fallback cho snapshot nếu thiếu snapshotRepository |
| `snapshotRepository` | Đích deploy riêng cho versions kiểu SNAPSHOT |
| `id` | Định danh ổn định của đích; dùng để khớp `settings.xml/servers/server/id` |
| `name` | Tên mô tả cho con người đọc log/POM |
| `url` | Đường dẫn upload, do repository manager cung cấp; có thể là HTTPS hoặc file transport |
| `uniqueVersion` | Trường model liên quan tạo unique timestamped snapshot; mặc định nên dùng cơ chế unique snapshots |
| `site` | Đích riêng cho documentation/site, không thay cho JAR/POM repository |

**Không đặt username, password, access token vào POM**. POM thường được commit và xuất bản cùng artifact; credentials phải nằm ở môi trường người dùng/CI, thường qua `settings.xml` và secret store.

### 3.1. Maven chọn đích nào?

Cho cùng POM chứa hai đích:

| Version của project | Đích deploy được chọn (khi không override) |
| --- | --- |
| `1.0.0-SNAPSHOT` | `distributionManagement/snapshotRepository` |
| `2.0.0-SNAPSHOT` | `distributionManagement/snapshotRepository` |
| `1.0.0` | `distributionManagement/repository` |
| `1.0.1` | `distributionManagement/repository` |
| `2.0.0-RC1` | Thông thường không phải snapshot theo quy tắc hậu tố `-SNAPSHOT`, nên đi release destination |
| `1.0.0-SNAPSHOT` nhưng POM không có snapshotRepository | **Fallback** sang `distributionManagement/repository` |

Maven xem loại version từ project model, **không dựa vào tên Git branch**. Một branch tên `release` nhưng POM version còn `-SNAPSHOT` thì kết quả vẫn là SNAPSHOT. Một branch tên `develop` nhưng POM version là release sẽ cố deploy vào đích release nếu hệ thống cho phép.

**Quy tắc an toàn:** trước khi chạy deploy, đọc version hiệu lực, đích upload và policy chặn ở server. Không suy đoán từ tên job CI.

## 4. SNAPSHOT là phiên bản phát triển như thế nào?

Version `1.0.0-SNAPSHOT` thường biểu thị nội dung có thể thay đổi trước release cuối cùng. Khi deploy vào Maven repository chuẩn với unique snapshots, một bản snapshot có thể được lưu bằng tên file **có timestamp và build number**; version yêu cầu của consumer vẫn là `1.0.0-SNAPSHOT`.

Ví dụ minh họa, **không phải timestamp thật**:

```text
repository path:
dev/course/channel-demo/1.0.0-SNAPSHOT/

deployed files (ví dụ):
channel-demo-1.0.0-20261110.090000-1.jar
channel-demo-1.0.0-20261110.090000-1.pom
maven-metadata.xml
...
```

Sau lần deploy khác có thể có thêm build number mới và metadata trỏ đến phiên bản được publish tương ứng. Tên file/timestamp cụ thể do Maven repository, thời gian và quy trình triển khai xác định.

Consumer vẫn khai báo:

```xml
<dependency>
    <groupId>dev.course</groupId>
    <artifactId>channel-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>
</dependency>
```

Maven dùng metadata/cache/update policy để xác định snapshot có thể tải. **Không tự chép timestamped filename vào dependency version** chỉ để tránh hiểu cơ chế SNAPSHOT; hãy dùng tọa độ và metadata đúng.

### 4.1. Khác với RELEASE

Khi đổi project version thành `1.0.0`, release artifact trong Maven 2-style repository layout thường có đường dẫn:

```text
dev/course/channel-demo/1.0.0/
    channel-demo-1.0.0.jar
    channel-demo-1.0.0.pom
    ...
```

**RELEASE nên bất biến:** với cùng GAV, những consumers khác nhau kỳ vọng tải **cùng bytes**. Các repository managers như Nexus Repository hoặc Artifactory có thể áp đặt chính sách không cho redeploy release; đó thường là **chính sách server**, không phải chỉ một điều kiện XML của Maven Deploy Plugin.

Việc release đã publish nhưng phát hiện lỗi thường nên dẫn đến **một version mới**, không âm thầm ghi đè version cũ.

### 4.2. uniqueVersion không phải công tắc phân loại

Maven model có trường `uniqueVersion` liên quan cách đặt tên snapshot phiên bản duy nhất; mặc định phù hợp thông thường là tạo timestamp/build number. **Không chỉnh `<uniqueVersion>false</uniqueVersion>` để biến snapshot thành release hoặc để ép ghi đè theo ý muốn**. Đây không phải mục tiêu chính của việc tách kênh. Một số repository manager và versions mới còn có những ràng buộc riêng với hành vi non-unique snapshots.

Để quản lý phát hành đáng tin, giữ cơ chế unique snapshot hiện hành và để repository manager quản lý retention, cleanup, immutability đúng loại kho.

## 5. Ba nhóm repository dễ bị nhầm

Trong Maven có ít nhất ba lớp cấu hình cần phân biệt:

### 5.1. Deployment destination

```xml
<distributionManagement>
    <repository>
        <id>releases-write</id>
        <url>https://repo.example.invalid/repository/releases/</url>
    </repository>
    <snapshotRepository>
        <id>snapshots-write</id>
        <url>https://repo.example.invalid/repository/snapshots/</url>
    </snapshotRepository>
</distributionManagement>
```

Khi `mvn deploy`, Maven Deploy Plugin sử dụng đích này (trừ khi command line/plugin overrides). Đây là **upload configuration**.

### 5.2. Download dependency repositories

```xml
<repositories>
    <repository>
        <id>releases-read</id>
        <url>https://repo.example.invalid/repository/releases/</url>
        <releases>
            <enabled>true</enabled>
        </releases>
        <snapshots>
            <enabled>false</enabled>
        </snapshots>
    </repository>
    <repository>
        <id>snapshots-read</id>
        <url>https://repo.example.invalid/repository/snapshots/</url>
        <releases>
            <enabled>false</enabled>
        </releases>
        <snapshots>
            <enabled>true</enabled>
            <updatePolicy>always</updatePolicy>
        </snapshots>
    </repository>
</repositories>
```

Đây là **download configuration** cho dependencies. Nó không tự thay `distributionManagement`. POM có `<repositories>` mà không có `distributionManagement` vẫn có thể không có đích hợp lệ để `mvn deploy`.

### 5.3. pluginRepositories và mirrors

- `<pluginRepositories>`: nguồn tải Maven plugins như Compiler, Surefire và Deploy Plugin. Không phải đích upload artifact project.
- `<mirrors>` trong `settings.xml`: đổi nơi Maven tìm/tải artifacts hoặc plugins từ repositories theo `mirrorOf`, có thể trỏ tới internal repository group/proxy.
- **Mirror phục vụ resolution/download; không phải cơ chế tự động redirect `distributionManagement` upload**. Để thay đích publish, cấu hình đích deployment hoặc dùng override phù hợp.
- Một repository manager có thể cung cấp **read-only group URL** cho consumers, cùng các **hosted release/snapshot URLs** để publishers upload. Không upload vào URL group/download trừ khi repository manager thực sự cho phép.

Bảng tổng hợp:

| Cấu hình | Hướng dữ liệu | Trách nhiệm |
| --- | --- | --- |
| `distributionManagement/repository` | Build → remote | Publish releases |
| `distributionManagement/snapshotRepository` | Build → remote | Publish snapshots |
| `repositories` | Remote → local cache | Resolve dependencies |
| `pluginRepositories` | Remote → local cache | Resolve plugins |
| `settings.xml/servers` | Credentials cho kết nối | Xác thực theo `id` |
| `settings.xml/mirrors` | Thay/định tuyến repository downloads | Cache/proxy đọc |
| `~/.m2/repository` | Local filesystem | Cache/install artifacts |

Một server có thể dùng chung hạ tầng/host cho nhiều URL nhưng **kênh và quyền ghi** vẫn nên khác nhau.

## 6. Chính sách chia tách ở server quan trọng hơn chỉ thêm XML

Chỉ khai báo hai URL trong POM **chưa đảm bảo** không có release lẫn snapshot. Cần repository manager và CI cùng thực thi chính sách:

| Tiêu chí | SNAPSHOT repository | RELEASE repository |
| --- | --- | --- |
| Mục đích | Tích hợp/dev/test liên tục | Phiên bản phát hành ổn định |
| Chấp nhận version | `-SNAPSHOT` | Phiên bản release không có `-SNAPSHOT` |
| Redeploy cùng GAV | Có thể cho phép nhiều unique snapshot builds | Nên cấm overwrite/immutable |
| Retention | Dọn snapshot cũ theo tuổi/số lượng | Lưu theo release/audit/retention policy |
| Quyền ghi | Build/dev CI riêng, giới hạn scope | Release pipeline/maintainers được phê duyệt |
| Consumer | Integration/test environments | Staging/production theo chính sách |
| Cách đặt tên | Timestamped unique snapshot và metadata | Stable version files |
| CI trigger | Thường nhánh phát triển | Tag/release approval/signing |
| Audit | Commit/build run metadata | Release provenance, approval, checksums, signatures khi cần |

**Phân tách quyền truy cập** là một lớp bảo vệ thực tế. Nếu mọi build developer đều có quyền deploy release, một POM version bị sửa nhầm có thể đưa artifact thử nghiệm vào kho chính thức dù POM có hai URL đúng.

Repository manager có thể bật **repository-specific version policy** để từ chối upload sai loại. Maven client phân luồng theo version, còn server làm bước từ chối cuối cùng đối với artifact không phù hợp.

### 6.1. Download policies không phải upload gate

Trong `<repositories>` hoặc profile của `settings.xml`, hai phần:

```xml
<releases>
    <enabled>true</enabled>
    <updatePolicy>daily</updatePolicy>
</releases>
<snapshots>
    <enabled>false</enabled>
</snapshots>
```

quyết định **consumer có tìm loại artifact tương ứng ở remote repository này không** và tần suất cập nhật cache/metadata. Chúng **không thay thế** quyền ghi/upload policy của `distributionManagement` hay repository manager.

Ví dụ `<snapshots><enabled>false</enabled></snapshots>` trong một download repository không tự khiến Maven Deploy Plugin bị cấm upload snapshot vào một URL khác. Muốn chặn sai kênh, dùng server-side version policy và CI checks.

### 6.2. updatePolicy cho SNAPSHOT

Khi đọc/download, Maven repository policy có thể dùng:

- `always`: kiểm tra cập nhật mỗi lần theo quy tắc resolver.
- `daily`: mặc định phổ biến, kiểm tra theo ngày.
- `interval:X`: số phút giữa các lần kiểm tra.
- `never`: hạn chế kiểm tra phiên bản mới khi đã có locally.

`mvn -U` có thể yêu cầu update snapshot metadata/artifacts từ remote, nhưng **không tạo deploy mới**, không build lại source của dependency bên ngoài reactor và không sửa sai URL/credentials.

Một CI production nên tránh dependency `-SNAPSHOT` nếu yêu cầu reproducible immutable builds. Chỉ tăng tần suất kiểm tra không làm SNAPSHOT trở thành bất biến.

## 7. Thực hành an toàn: deploy vào hai repository thư mục cục bộ

Để học cơ chế chia tách **mà không cần thông tin đăng nhập hay remote server**, dùng **file transport** tới hai thư mục riêng trong máy. Maven Deploy Plugin vẫn dùng deployment lifecycle và tạo Maven-style repository metadata; đích của bài chỉ là thư mục lab.

Cấu trúc:

```text
workspace-lab/
├── channel-demo/
│   ├── pom.xml
│   └── src/
│       ├── main/java/dev/course/
│       │   ├── Greeter.java
│       │   └── App.java
│       └── test/java/dev/course/
│           └── GreeterTest.java
├── consumer-demo/
│   ├── pom.xml
│   └── src/main/java/dev/consumer/ConsumerApp.java
└── repo-lab/
    ├── releases/     (Maven sẽ tạo khi deploy bản release)
    └── snapshots/    (Maven sẽ tạo khi deploy bản snapshot)
```

**Điều kiện:** JDK 17+, Apache Maven 3.9.x hoặc tương thích, internet hoặc local cache để tải plugins/JUnit lần đầu. Các lệnh ví dụ sử dụng **đường dẫn `file:../repo-lab/...` tương đối**; hãy chạy từ đúng thư mục `channel-demo` hay `consumer-demo` như chỉ dẫn. Với môi trường/URI không hỗ trợ relative file URL, dùng một **file URI tuyệt đối hợp lệ** theo OS, ví dụ `file:///home/user/workspace-lab/repo-lab/releases` trên Unix. Không dùng đường dẫn máy khác bằng cách copy nguyên văn.

**Không chạy các lệnh này để upload vào repository công ty**. Toàn bộ POM ví dụ đặt đích ghi vào local filesystem.

## 8. POM mẫu đầy đủ: channel-demo/pom.xml

Tạo `workspace-lab/channel-demo/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.course</groupId>
    <artifactId>channel-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>
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
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-install-plugin</artifactId>
                <version>3.1.4</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-deploy-plugin</artifactId>
                <version>3.1.4</version>
            </plugin>
        </plugins>
    </build>

    <distributionManagement>
        <repository>
            <id>lab-releases</id>
            <name>Local Lab Releases</name>
            <url>file:../repo-lab/releases</url>
        </repository>
        <snapshotRepository>
            <id>lab-snapshots</id>
            <name>Local Lab Snapshots</name>
            <url>file:../repo-lab/snapshots</url>
        </snapshotRepository>
    </distributionManagement>
</project>
```

Mặc dù gọi là `lab-releases` và `lab-snapshots`, đây chỉ là **hai thư mục trên máy**, không phải những kho thương mại có policy chặn ghi đè. Cấu hình này cho phép **quan sát lựa chọn đích upload**; còn việc server từ chối release/snapshot sai kênh phải được kiểm tra trên repository manager thật trong môi trường được cấp quyền.

Version ban đầu `1.0.0-SNAPSHOT` để lần deploy đầu đi vào `snapshotRepository`. Plugin `maven-deploy-plugin:3.1.4` được ghim để các cú pháp hướng dẫn thống nhất; không cần thêm execution vì goal deploy đã bind với phase `deploy` cho Maven default lifecycle của JAR project.

## 9. Java 17 source và ba unit tests

### 9.1. Greeter.java

Tạo `channel-demo/src/main/java/dev/course/Greeter.java`:

```java
package dev.course;

public final class Greeter {
    private Greeter() {
    }

    public static String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "Tên không hợp lệ");
        }
        return "Xin chào, " + name.strip() + "!";
    }
}
```

### 9.2. App.java

Tạo `channel-demo/src/main/java/dev/course/App.java`:

```java
package dev.course;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("APP: " + Greeter.greet(" Maven "));
    }
}
```

Sau khi compile, stdout do main tạo **chính xác**:

```text
APP: Xin chào, Maven!
```

### 9.3. GreeterTest.java

Tạo `channel-demo/src/test/java/dev/course/GreeterTest.java`:

```java
package dev.course;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreeterTest {
    @Test
    void trimsName() {
        assertEquals("Xin chào, Maven!",
                Greeter.greet(" Maven "));
    }

    @Test
    void rejectsBlank() {
        assertThrows(IllegalArgumentException.class,
                () -> Greeter.greet("   "));
    }

    @Test
    void rejectsNull() {
        assertThrows(IllegalArgumentException.class,
                () -> Greeter.greet(null));
    }
}
```

**3 tests** kiểm tra Unicode, blank và null. Tất cả chỉ phụ thuộc Java/JUnit; không cần mạng sau khi dependencies đã được resolve.

## 10. Build, verify và install trước khi deploy

Đứng tại `workspace-lab`, chuyển vào project:

```bash
cd channel-demo
mvn -version
mvn clean verify
java -cp target/classes dev.course.App
```

Expected:

```text
APP: Xin chào, Maven!
```

Log Surefire kỳ vọng có:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Đây là log **rút gọn chỉ các dấu hiệu**, không phải toàn bộ output Maven.

Sau `verify`, JAR ở:

```text
channel-demo/target/channel-demo-1.0.0-SNAPSHOT.jar
```

Thử:

```bash
mvn clean install
```

Lệnh này cài artifact + POM vào **local Maven repository** của user/runner. Nó **chưa thực thi deploy phase**, vì thế không dùng kết quả `install` để suy luận `repo-lab/snapshots` đã có remote-style published artifacts.

**Không chạy `java -jar target/channel-demo-1.0.0-SNAPSHOT.jar`** khi POM không có `Main-Class` trong manifest. Dùng `java -cp target/classes dev.course.App` cho runnable demo; đóng gói executable JAR là chủ đề khác.

## 11. Deploy SNAPSHOT vào thư mục snapshotRepository

Khi đang ở `workspace-lab/channel-demo`:

```bash
mvn clean deploy
```

Chú ý lệnh này **có tác dụng ghi filesystem vào repo-lab**. Trong bài, các URLs là `file:../repo-lab/...` nên hoàn toàn không có remote upload đến máy chủ công ty.

Lúc project version vẫn là `1.0.0-SNAPSHOT`:

1. Maven chạy compile, test, package, verify, install.
2. Deploy Plugin nhận project SNAPSHOT.
3. Nó chọn đích `lab-snapshots` dưới `distributionManagement/snapshotRepository`.
4. Nó publish JAR/POM/metadata vào `../repo-lab/snapshots` theo Maven repository layout.
5. Thư mục `../repo-lab/releases` **không phải đích của artifact SNAPSHOT này**.

Đường dẫn xuất hiện điển hình:

```text
workspace-lab/repo-lab/snapshots/dev/course/channel-demo/1.0.0-SNAPSHOT/
    channel-demo-1.0.0-<timestamp>-<build>.jar
    channel-demo-1.0.0-<timestamp>-<build>.pom
    maven-metadata.xml
    ...
```

Các dấu `<timestamp>` và `<build>` trong sơ đồ chỉ là **chỗ diễn giải tên do Maven sinh**, không phải tên file người học phải gõ. Khi kiểm tra thực tế, hãy xem output `Uploading to lab-snapshots` và `ls/dir` thư mục đích.

Trên Bash/zsh (tại `channel-demo`):

```bash
find ../repo-lab/snapshots -type f
```

Trên PowerShell:

```powershell
Get-ChildItem -Path ..\repo-lab\snapshots -Recurse -File
```

Kiểm tra metadata giúp xác nhận đây là published snapshot repository, chứ không chỉ một JAR nằm trong `target`.

## 12. Chuyển sang RELEASE và quan sát routing khác

Để làm thí nghiệm release, sửa **duy nhất** version trong `channel-demo/pom.xml`:

```xml
<version>1.0.0</version>
```

Đây là thao tác trong **bản project lab**, không phải yêu cầu sửa POM một dự án đang dùng ở production. Cần tránh thay nhầm version của dependency/plugin khác.

Từ `channel-demo`:

```bash
mvn clean verify
mvn clean deploy
```

Bởi vì version bây giờ là `1.0.0` (không có `-SNAPSHOT`), Deploy Plugin chọn **`lab-releases`**. Output dự kiến:

```text
workspace-lab/repo-lab/releases/dev/course/channel-demo/1.0.0/
    channel-demo-1.0.0.jar
    channel-demo-1.0.0.pom
    ...
```

Snapshot đã deploy trước đó nằm trong `repo-lab/snapshots` và không biến thành release chỉ vì bạn đổi POM version. Maven tạo **artifact version mới** với GAV release; nó không “promote” hoặc di chuyển file snapshot sang kho release theo mặc định.

**Chú ý quan trọng:** Trong file-based lab không có policy immutable release của repository manager, lặp lại `mvn deploy` cùng release GAV có thể ghi đè. Trên hệ thống phát hành thật, cấu hình server để **reject redeploy releases** và dùng quy trình phát hành được kiểm soát.

Sau thử nghiệm có thể đổi version lab lại thành `1.0.0-SNAPSHOT` nếu muốn làm tiếp bài học trên kênh phát triển, nhưng **không chỉnh những artifacts đã publish trong kho bằng tay**.

## 13. Consumer: cấu hình nơi TẢI VỀ khác nơi DEPLOY

Một consumer độc lập muốn sử dụng JAR đã deploy vào repo-lab. Tạo project `workspace-lab/consumer-demo`, nằm cạnh `channel-demo`, không nằm trong reactor của channel-demo.

### 13.1. consumer-demo/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.consumer</groupId>
    <artifactId>channel-consumer</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>dev.course</groupId>
            <artifactId>channel-demo</artifactId>
            <version>1.0.0-SNAPSHOT</version>
        </dependency>
    </dependencies>

    <repositories>
        <repository>
            <id>lab-releases-read</id>
            <url>file:../repo-lab/releases</url>
            <releases>
                <enabled>true</enabled>
            </releases>
            <snapshots>
                <enabled>false</enabled>
            </snapshots>
        </repository>
        <repository>
            <id>lab-snapshots-read</id>
            <url>file:../repo-lab/snapshots</url>
            <releases>
                <enabled>false</enabled>
            </releases>
            <snapshots>
                <enabled>true</enabled>
                <updatePolicy>always</updatePolicy>
            </snapshots>
        </repository>
    </repositories>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Điểm đáng chú ý:

- Consumer dùng **`<repositories>`** chứ **không cần `distributionManagement`** vì consumer chỉ tải dependency và build chính nó.
- `lab-snapshots-read` chỉ cho snapshot downloads; `lab-releases-read` chỉ cho release downloads.
- Chính sách `updatePolicy=always` dành cho snapshot giúp thí nghiệm dễ quan sát cập nhật từ repo-lab; **không nên mặc định áp dụng vào production** khi yêu cầu reproducible builds.
- Consumer đang yêu cầu `1.0.0-SNAPSHOT`, đúng artifact đã được deploy ở mục 11. Nếu muốn dùng release, sửa dependency version thành `1.0.0` sau khi hoàn thành mục 12.

### 13.2. ConsumerApp.java

Tạo `consumer-demo/src/main/java/dev/consumer/ConsumerApp.java`:

```java
package dev.consumer;

import dev.course.Greeter;

public final class ConsumerApp {
    private ConsumerApp() {
    }

    public static void main(String[] args) {
        System.out.println(
                "CLIENT: " + Greeter.greet(" Kho lưu trữ "));
    }
}
```

Dòng stdout kỳ vọng:

```text
CLIENT: Xin chào, Kho lưu trữ!
```

### 13.3. Build consumer

Sau khi deploy snapshot, chuyển từ `workspace-lab/channel-demo` về `workspace-lab` rồi vào consumer:

```bash
cd ../consumer-demo
mvn clean package
mvn -q compile exec:java -Dexec.mainClass=dev.consumer.ConsumerApp
```

Maven tải dependency `dev.course:channel-demo:1.0.0-SNAPSHOT` qua `repositories` đã khai báo khi cần và có thể lưu vào local cache. Exec Maven Plugin chạy ConsumerApp với runtime classpath chứa dependency.

Nếu consumer đã từng có artifact cùng GAV trong local repository từ lần khác, Maven resolver có thể sử dụng/cập nhật nó theo metadata/policy. **Để chứng minh chắc chắn nguồn tải là repo-lab**, dùng một local Maven repository thử nghiệm riêng hoặc xem `mvn -X` log với kiểm soát thông tin nhạy cảm.

Nếu bạn đổi consumer dependency version thành `1.0.0` sau khi deploy release, Maven sẽ tìm ở `lab-releases-read` thay vì snapshot-only repository.

## 14. Credentials: khớp id với settings.xml, không ghi trong pom.xml

Khi chuyển từ thư mục file lab sang HTTPS repository manager thật, publishers thường cần xác thực. Đặt **đích deploy** trong POM:

```xml
<distributionManagement>
    <repository>
        <id>company-releases</id>
        <url>https://repo.example.invalid/repository/releases/</url>
    </repository>
    <snapshotRepository>
        <id>company-snapshots</id>
        <url>https://repo.example.invalid/repository/snapshots/</url>
    </snapshotRepository>
</distributionManagement>
```

Và đặt **thông tin đăng nhập** trong user/CI `settings.xml` được bảo vệ, ví dụ:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <servers>
        <server>
            <id>company-releases</id>
            <username>${env.MVN_RELEASE_USER}</username>
            <password>${env.MVN_RELEASE_TOKEN}</password>
        </server>
        <server>
            <id>company-snapshots</id>
            <username>${env.MVN_SNAPSHOT_USER}</username>
            <password>${env.MVN_SNAPSHOT_TOKEN}</password>
        </server>
    </servers>
</settings>
```

**Ví dụ chỉ minh họa cấu trúc**, không chứa secret thật và không dùng `example.invalid` để kết nối. Các environment variables cần được CI secret manager cung cấp đúng cách.

- `server/id` phải trùng chính xác `distributionManagement/repository/id` hoặc `snapshotRepository/id` tương ứng.
- Các `id` này **không phải username**; `id` xác định bộ credentials/connection settings dùng cho repository.
- Có thể cùng một account có hai quyền khác nhau; tốt hơn thường là tách roles/permissions release và snapshot.
- Không hardcode password/token vào POM, git history hoặc command-line arguments dễ bị log lại.
- Maven hỗ trợ quản lý/mã hóa credential theo phiên bản; vẫn phải bảo vệ settings và key material.
- Một số Maven releases mới bổ sung cơ chế giới hạn credential theo repository origin; khi nâng Maven, kiểm tra tài liệu bảo mật của version đang dùng.

**Không tự chạy deploy lên repo công ty khi chỉ thực hành bài học.** Nên dùng file lab hoặc một staging repository do quản trị cấp phép.

### 14.1. Vì sao 401 và 403 khác nhau?

- **401 Unauthorized**: thường thiếu/sai credentials hoặc challenge authentication.
- **403 Forbidden**: credentials có thể hợp lệ nhưng không có quyền ghi, repo bị khóa hoặc policy cấm hành động.
- **404 Not Found**: URL/path sai, endpoint không tồn tại hoặc một số hệ thống che giấu resource.
- **409 Conflict / 400 Bad Request**: có thể do version policy, release redeploy forbidden, wrong repository type hoặc repository manager kiểm tra metadata.

Cần đọc response body/log server cụ thể; không khẳng định mọi repository manager trả cùng một status cho tất cả trường hợp.

## 15. Khi thiếu snapshotRepository thì sao?

POM sau:

```xml
<distributionManagement>
    <repository>
        <id>company-releases</id>
        <url>https://repo.example.invalid/repository/releases/</url>
    </repository>
</distributionManagement>
```

**không tự ngăn SNAPSHOT được định tuyến vào release URL**. Theo Maven POM reference, khi `snapshotRepository` không được khai báo thì `repository` có thể được dùng cho snapshot distribution.

Điều có thể xảy ra:

- Maven client cố upload `1.0.0-SNAPSHOT` đến release URL.
- Repository manager có policy release-only có thể **từ chối**.
- Nếu server không áp chính sách, SNAPSHOT có thể bị đẩy vào nơi nhóm tưởng chỉ dành cho releases.

Vì thế việc “chỉ viết repository vì chúng ta chỉ release” phải đi kèm một **CI policy** từ chối project version còn `-SNAPSHOT` ở release pipeline. Muốn tách rõ nhất, khai báo cả hai đích và dùng server policy.

**Chiều ngược lại:** chỉ có `snapshotRepository` nhưng không có `repository` không đủ cho một bản RELEASE deploy thông thường; Maven Deploy Plugin cần đích release hoặc cấu hình override hợp lệ.

## 16. Override deployment repositories trên CLI

Maven Deploy Plugin 3.x hỗ trợ overrides, hữu ích cho staging/CI khi không muốn thay POM:

- `-DaltDeploymentRepository=id::url`: đích thay thế chung.
- `-DaltReleaseDeploymentRepository=id::url`: đích thay thế khi project version là release.
- `-DaltSnapshotDeploymentRepository=id::url`: đích thay thế khi project version là snapshot.

Ví dụ **chỉ publish vào thư mục local lab**:

```bash
mvn clean deploy "-DaltSnapshotDeploymentRepository=lab-staging::file:../repo-lab/staging-snapshots"
```

Chạy trong `channel-demo` với project version `1.0.0-SNAPSHOT`. Đây là một cách override snapshot destination cho một lần chạy.

**Cú pháp Maven Deploy Plugin 3.x là `id::url`.** Các hướng dẫn rất cũ cho Deploy Plugin 2.x có thể dùng `id::layout::url`; đừng trộn hai định dạng.

Vì override có thể thay URL publication của POM, phải coi nó là **tùy chọn có đặc quyền**:

1. Kiểm tra version thực tế của Deploy Plugin.
2. Xem effective project version.
3. Xác nhận URL và `id` thuộc môi trường publish có chủ đích.
4. Bảo vệ CI variables/credentials; không cho input không tin cậy quyết định URL upload.
5. Xem các logs `Uploading to...` và xác minh repository đích sau deploy.
6. Giữ repository manager policy không cho SNAPSHOT lọt vào releases và không cho ghi đè immutable releases.

**Maven mirror cho download không tương đương altDeploymentRepository cho upload.**

## 17. DeployPlugin settings: skip, retry và multi-module

Với Maven Deploy Plugin 3.x, một số tham số đáng biết:

| Tham số | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `maven.deploy.skip` | Bỏ qua deploy theo cấu hình, có thể chọn giá trị `true`, `releases` hoặc `snapshots` theo plugin version | Kiểm tra plugin version và job CI |
| `deployAtEnd` | Hoãn deploy trong multi-module reactor tới cuối phần deploy phù hợp | **Không làm transaction atomic** |
| `retryFailedDeploymentCount` | Cho phép retry khi upload lỗi mạng tạm thời | Không thay thế điều tra 401/403/policy |
| `altDeploymentRepository` | Override upload URL chung | `id::url` ở 3.x |
| `altReleaseDeploymentRepository` | Override release URL | Không tự bảo đảm server immutable |
| `altSnapshotDeploymentRepository` | Override snapshot URL | Không tự bảo đảm server chỉ nhận snapshot |
| `deploy-file` goal | Đẩy file tùy chọn lên Maven repo | Cần GAV và POM/metadata chính xác |

Một số team muốn không publish SNAPSHOT từ một job release. Có thể cấu hình plugin skip theo version phù hợp, nhưng **đừng dùng skip thay thế policy chặn sai version** ở pipeline/server: một job xanh vì đã bỏ deploy không phải bằng chứng artifact đã publish.

### 17.1. deployAtEnd không phải all-or-nothing

Trong reactor nhiều modules, mặc định plugin có thể deploy module khi từng module đến deploy phase. Nếu module sau fail, một số artifact trước đã được publish.

`deployAtEnd=true` có thể giảm nguy cơ này bằng cách đợi tới cuối phần build phù hợp trước khi triển khai. Nhưng:

- Không đảm bảo rollback artifacts đã upload.
- Nếu một request thuộc batch deploy lỗi sau các requests thành công, kho có thể bị publish một phần.
- Các modules/plugins không dùng cùng execution config có thể vẫn deploy ở thời điểm khác.
- Nếu code đang triển khai liên quan nhiều repositories, không có transaction phân tán tự động.

Vì vậy release pipeline multi-module cần **staging repository, validation, promotion và rollback policy** từ repository manager. Không nói `deployAtEnd=true` “đảm bảo toàn bộ modules được upload hoặc không module nào được upload”.

## 18. Quản lý repository ở multi-module parent POM

Thông thường cấu hình `distributionManagement` nằm trong parent POM để children kế thừa:

```xml
<project>
    <!-- minh họa phần liên quan trong parent -->
    <groupId>dev.course</groupId>
    <artifactId>parent-demo</artifactId>
    <version>2.0.0-SNAPSHOT</version>
    <packaging>pom</packaging>

    <distributionManagement>
        <repository>
            <id>company-releases</id>
            <url>https://repo.example.invalid/repository/releases/</url>
        </repository>
        <snapshotRepository>
            <id>company-snapshots</id>
            <url>https://repo.example.invalid/repository/snapshots/</url>
        </snapshotRepository>
    </distributionManagement>
</project>
```

Đây là **đoạn minh họa vai trò parent**, không phải một POM runnable: Maven project thực tế còn cần modelVersion, modules, parent declarations và những phần khác.

Khi root/children inherit distributionManagement, từng module có thể sử dụng cùng destination URL nhưng artifact GAV khác nhau. Maven Deploy Plugin publish POM của parent và artifacts của children tùy packaging/goals.

Đừng nhầm `<modules>` với inheritance: một aggregator không phải parent của child thì child không nhất thiết thừa kế distributionManagement. Xem:

```bash
mvn help:effective-pom
mvn help:active-profiles
```

để kiểm tra module nào đang dùng settings hiệu lực. Không deploy khi còn chưa rõ effective URLs hoặc project versions.

## 19. CI/CD: chính sách phân nhánh an toàn

Một release pipeline có thể quyết định đường đi theo **version thực tế**, **quyền** và **quy trình phê duyệt**:

```text
checkout source
     |
     v
mvn -B -ntp clean verify
     |
     +-- FAIL --> stop, báo lỗi/test/quality gate
     |
     +-- PASS
           |
           +-- version == *-SNAPSHOT ?
           |        |
           |        +-- yes -> snapshot publishing job
           |                  -> snapshot credential
           |                  -> snapshot-only repository
           |
           +-- version == stable release ?
                    |
                    +-- approval/tag/provenance checks
                    +-- release credential
                    +-- release-only repository
                    +-- immutable publication policy
```

Đây là **sơ đồ chính sách**, không phải một script tự suy ra branch/tags để tự publish.

Gợi ý quản trị:

- Job pull request chưa được tin cậy **không có release token**.
- Snapshot publisher chỉ có quyền ghi snapshot hosted repository.
- Release publisher chỉ kích hoạt từ tag/approval/commit hợp lệ và có quyền ghi release hosted repository.
- Không ghi tokens trong `pom.xml`, output logs, artifacts hoặc workspace public.
- Ghim JDK/Maven/plugin versions, bật unit/integration tests và quality gates trước deploy.
- Xem server audit logs, checksum/signature khi có yêu cầu supply-chain, và artifact provenance.
- Nếu publish release đã tồn tại, **dừng và phát hành version mới** thay vì tự tắt immutability.
- Mỗi lần publish cần kiểm tra đúng repository ID, URL, GAV và metadata.

**Không đánh giá thành công chỉ bằng `BUILD SUCCESS`** nếu deploy bị skip hoặc đang dùng override sai URL. Hãy kiểm chứng remote repository thật, version và metadata.

## 20. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân nên xem | Cách xử lý |
| --- | --- | --- |
| `mvn deploy` báo thiếu repository | Chưa cấu hình `distributionManagement/repository` và không có alt repo phù hợp | Thêm đích hợp lệ theo quy trình |
| SNAPSHOT bị upload vào release URL | Thiếu `snapshotRepository` và fallback sang `repository` | Khai báo snapshotRepository và bật server policy |
| Release vào snapshot URL | CLI override sai, version/URL cấu hình nhầm | Kiểm tra POM, version, overrides, server rules |
| HTTP 401 | Thiếu/sai credentials, server ID không khớp | Kiểm tra `settings.xml/servers/server/id` |
| HTTP 403 | Tài khoản thiếu quyền publish hoặc repo policy chặn | Kiểm tra role/policy với quản trị |
| HTTP 404 | Endpoint/URL sai hoặc resource bị che | Kiểm tra đúng upload URL, không dùng group/read-only URL |
| HTTP 409 | Redeploy release bị cấm hoặc conflict metadata | Không ghi đè; nâng version/policy |
| Artifact ở `target/` nhưng không thấy remote | Mới chạy package/verify, chưa deploy | Chạy deploy đúng môi trường được phép |
| Artifact trong local repo nhưng remote trống | Mới chạy install | Phân biệt install với deploy |
| Consumer không tìm thấy snapshot | Consumer download repositories không cho snapshots | Bật đúng snapshot repository |
| Consumer thấy snapshot cũ | Metadata/update policy/local cache | Kiểm tra maven-metadata, `-U`, tọa độ repo |
| `-U` vẫn không dùng source mới | Dependency source không thuộc reactor và chưa deploy/install | Build/publish version phù hợp |
| Client tải dependency được nhưng deploy FAIL | Download mirror và upload destination khác | Kiểm tra `distributionManagement` |
| Deploy thành công nhưng consumer không thấy | Consumer dùng URL/repo policy/credential khác | So sánh read URL và write URL, permissions |
| Snapshot bị từ chối trong release repository | Repository manager áp policy release-only | Đúng hành vi; sửa version/đích |
| Release bị từ chối do redeploy | Immutable release policy | Tăng version, không tắt policy |
| Multi-module chỉ publish một phần | Lỗi giữa reactor deploy requests | Dùng staging/promotion, xem deployAtEnd |
| Pipeline xanh nhưng không có artifact | `maven.deploy.skip` hoặc deploy goal không chạy | Xác minh plugin invocation và logs |
| File URI path không đúng OS | Relative file: URL giải quyết sai thư mục | Chạy từ đúng cwd hoặc dùng URI tuyệt đối |
| Settings chứa secret nhưng vẫn 401 | Server ID khác hoặc credential scope / origin policy | Kiểm tra effective settings cẩn thận |
| Release branch vẫn xuất snapshot | POM version kết thúc bằng `-SNAPSHOT` | Kiểm tra effective version trước deploy |
| Có artifact JAR nhưng không có POM metadata | Upload thủ công thay vì Maven Deploy Plugin | Dùng deploy goal, không copy file bừa |

Khi có lỗi, nhìn theo thứ tự: **project version → effective distributionManagement → Maven goal → server ID/credentials → URL/type policy → logs/metadata**. Không tự retry hàng loạt trên release repository khi đã gặp 409; việc retry có thể tăng rủi ro hoặc che nguyên nhân.

## 21. Bộ lệnh kiểm tra có ích

Từ project chứa POM (chỉ đọc cấu hình hoặc build, không publish remote):

```bash
mvn -version
mvn help:effective-pom
mvn help:active-profiles
mvn clean verify
mvn dependency:tree
```

Để xem cấu hình Deploy Plugin:

```bash
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-deploy-plugin -Dgoal=deploy -Ddetail
```

Để xem local publish lab sau `mvn clean deploy` (chỉ dùng POM file transport):

```bash
find ../repo-lab -type f
```

Trong PowerShell:

```powershell
Get-ChildItem ..\repo-lab -Recurse -File
```

Nếu cần debug Maven:

```bash
mvn -X clean verify
```

Chú ý: **đừng chia sẻ raw verbose logs/effective settings** nếu chúng có token, server URLs nội bộ, paths hoặc thông tin nhạy cảm. Cũng **không gọi `mvn deploy` trong môi trường thật** chỉ để lấy log: deploy có side effects, nên phải có đích/staging và quyền rõ ràng.

## 22. Những câu hỏi tự kiểm tra

1. `<distributionManagement><repository>` khác `<repositories><repository>` ở chiều dữ liệu nào?
2. Vì sao `mvn install` không làm artifact tự xuất hiện trên máy chủ release?
3. Với version `1.2.0-SNAPSHOT` và đủ hai đích, Maven chọn repository nào?
4. Với version `1.2.0` và đủ hai đích, Maven chọn repository nào?
5. Nếu không khai báo `snapshotRepository`, SNAPSHOT sẽ đi đâu?
6. Vì sao release branch name không quyết định Maven snapshot/release routing?
7. Maven unique timestamped SNAPSHOT khác version `1.0.0-SNAPSHOT` ghi trong consumer POM thế nào?
8. Repository manager nên xử lý overwrite release khác overwrite snapshot thế nào?
9. Vì sao một download repository `<snapshots><enabled>false</enabled></snapshots>` không phải upload gate?
10. Settings `server/id` cần khớp với giá trị nào trong distributionManagement?
11. Tại sao credentials không nên nằm trong POM?
12. Vì sao Maven mirror không phải nơi tự động ghi artifacts khi `deploy`?
13. Build project lab bản SNAPSHOT, đọc đường dẫn `repo-lab/snapshots` và xác định JAR/POM/metadata.
14. Đổi version lab thành release rồi deploy. Kho nào xuất hiện `channel-demo-1.0.0.jar`?
15. Vì sao `file:../repo-lab/releases` không có policy immutability như một hosted release repo thật?
16. Consumer POM cần phần nào để tải SNAPSHOT từ repo-lab?
17. Khi consumer vẫn dùng snapshot cũ, `updatePolicy` hoặc `mvn -U` có ý nghĩa gì?
18. Vì sao `-U` không thay cho `mvn deploy` khi project library source vừa thay đổi?
19. Deploy Plugin 3.x dùng format `id::url` hay `id::layout::url`?
20. Ba tham số `altDeploymentRepository`, `altReleaseDeploymentRepository` và `altSnapshotDeploymentRepository` khác nhau thế nào?
21. Nếu 403/409 khi publish release, có nên tự xóa artifacts của release cũ để retry không?
22. Vì sao `deployAtEnd=true` không phải transaction atomic multi-module?
23. Một build xanh nhưng `maven.deploy.skip=true` thì artifact đã chắc chắn published chưa?
24. Release pipeline cần checks và permissions nào để không đẩy SNAPSHOT vào release repo?
25. Vì sao POM version và artifact GAV cần được xác nhận cùng provenance trước publish?

## 23. Checklist phát hành

- [ ] Effective project version đã đúng: `-SNAPSHOT` hoặc release.
- [ ] `distributionManagement/repository` trỏ tới **releases hosted URL** phù hợp.
- [ ] `distributionManagement/snapshotRepository` trỏ tới **snapshots hosted URL** phù hợp.
- [ ] Thiếu snapshotRepository không gây fallback ngoài ý muốn.
- [ ] Repo manager áp snapshot/release version policy riêng.
- [ ] Release không bị overwrite sau publication.
- [ ] Snapshot có retention và metadata policy phù hợp.
- [ ] DeployPlugin version và optional overrides đã được kiểm tra.
- [ ] `server/id` khớp repo ID, credentials trong CI secret store.
- [ ] Download repositories/proxies không bị nhầm với upload destination.
- [ ] CI chạy đầy đủ compile/tests/verify/quality gates.
- [ ] Publish job có quyền tối thiểu và approval cho release.
- [ ] Nếu dùng multi-module, đã thiết kế partial-deploy/staging recovery.
- [ ] Maven logs xác nhận đúng `Uploading to...` repository.
- [ ] Sau deploy, kiểm tra artifact POM, JAR, metadata, checksums ở đích.
- [ ] Consumer test dùng đúng version và read repository.
- [ ] Không thực hiện deploy production chỉ để thử nghiệm.

## 24. Tổng kết

Trong Maven, `distributionManagement` quản lý **phát hành artifacts**:

- **`repository`** là đích release, đồng thời có thể là fallback cho SNAPSHOT nếu không định nghĩa `snapshotRepository`.
- **`snapshotRepository`** là đích snapshot riêng, giúp tách luồng phát triển khỏi phát hành.
- **`repositories` / `pluginRepositories` / `mirrors`** phục vụ download/resolution, không thay cho cấu hình deploy.
- **`settings.xml/servers`** cung cấp credentials theo repository `id`; không ghi secrets trong POM.
- **Maven Deploy Plugin** upload artifact/POM/metadata; server policies quyết định điều kiện chấp nhận, quyền và immutability.

Dự án Java 17 mẫu có ba JUnit tests, in **`APP: Xin chào, Maven!`**, dùng hai file-based repositories `repo-lab/snapshots` và `repo-lab/releases` để quan sát routing. Một consumer riêng kiểm tra việc tải artifact và in **`CLIENT: Xin chào, Kho lưu trữ!`**.

**Chia tách an toàn phải làm ở cả ba nơi: POM routing, repository manager policy, và CI permissions/approval.** Chỉ thêm hai thẻ XML nhưng không kiểm soát việc publish sẽ chưa đủ.

## 25. Tài liệu chính thức

- [Apache Maven — POM Reference: Distribution Management](https://maven.apache.org/pom.html#distribution-management)
- [Apache Maven Deploy Plugin — Usage](https://maven.apache.org/plugins/maven-deploy-plugin/usage.html)
- [Apache Maven Deploy Plugin — deploy:deploy](https://maven.apache.org/plugins/maven-deploy-plugin/deploy-mojo.html)
- [Apache Maven Deploy Plugin — Deploying with Network Issues](https://maven.apache.org/plugins/maven-deploy-plugin/examples/deploy-network-issues.html)
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven — Security and Deployment Settings](https://maven.apache.org/guides/mini/guide-deployment-security-settings.html)
- [Apache Maven — Deploying over HTTP, FTP and SSH](https://maven.apache.org/guides/mini/guide-deployment-transports.html)
- [Apache Maven — Using Mirrors for Repositories](https://maven.apache.org/guides/mini/guide-mirror-settings.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html)
