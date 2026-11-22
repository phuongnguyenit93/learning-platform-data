# Chế độ ngoại tuyến -o và yêu cầu có đủ phụ thuộc, plugin trong Maven

Khi mạng không ổn định, làm việc trên máy không có Internet hoặc chạy CI trong môi trường giới hạn kết nối, Maven có thể build ở **chế độ ngoại tuyến** bằng tùy chọn `-o` hoặc `--offline`. Tuy nhiên, ngoại tuyến **không có nghĩa Maven tự có đủ thư viện**: mọi artifact và metadata cần cho lần build đó phải có sẵn trong local repository, hoặc được cung cấp bởi các module cùng reactor theo đúng quy trình.

Bài học tập trung vào cách `-o` hoạt động, những gì cần chuẩn bị (dependency, dependency bắc cầu, parent POM, plugin và dependency của plugin), quy trình làm nóng cache, kiểm thử trên máy hoàn toàn ngắt mạng, cùng cách xác định chính xác thứ đang thiếu.

## 1. `-o`/`--offline` thực sự làm gì?

Lệnh cơ bản:

```bash
mvn -o package
# Tương đương:
mvn --offline package
```

Nếu dự án có Maven Wrapper, dùng đúng phiên bản Maven dự án:

```bash
# Linux/macOS
./mvnw -o package
```

```powershell
# Windows PowerShell
.\mvnw.cmd -o package
```

Trong chế độ offline, **Maven Resolver** không liên hệ remote artifact repositories để tải artifact/metadata bị thiếu hay tìm bản cập nhật; nó phải giải quyết bằng dữ liệu đang có trong local repository và các artifact được build từ reactor. `-o` chỉ đặt hành vi giải quyết repository của **lần gọi Maven hiện tại**; bản thân nó không sinh dependency, không tự tải plugin và không đổi cấu trúc `pom.xml`.

Phân biệt các tùy chọn:

| Tùy chọn | Ý nghĩa | Có giúp tải dependency thiếu khi offline? |
| --- | --- | --- |
| `-o` / `--offline` | Không truy cập remote repository để resolve artifacts | **Không**; cần cache sẵn |
| `-B` / `--batch-mode` | Chạy không tương tác, hữu ích trên CI | Không |
| `-U` / `--update-snapshots` | Khi online, buộc kiểm tra cập nhật snapshot và một số tình huống metadata | Không; không khắc phục thiếu artifact trong offline |
| `-DskipTests` | Bỏ chạy test theo cấu hình plugin nhưng vẫn có các bước build liên quan | Không; plugin có thể vẫn cần được resolve |
| `-Dmaven.repo.local=...` | Chọn một local repository khác | Chỉ khi kho này thực sự chứa đủ artifacts |

**Giới hạn:** offline của Maven chủ yếu điều khiển **artifact resolution qua Maven**. Plugin hoặc chương trình build tự gửi HTTP, gọi dịch vụ bên ngoài, download Node/runtime, hay kiểm tra link có thể vẫn cần mạng; một số goal yêu cầu online và từ chối chạy offline. Vì vậy, `mvn -o verify` thành công là bằng chứng đáng tin cậy hơn việc chỉ nhìn thấy tùy chọn `-o`.

## 2. Điều kiện tiên quyết: có đúng artifact cần thiết ở local repository

Maven thường dùng thư mục local repository:

```text
Linux/macOS: ~/.m2/repository
Windows:     C:\Users\<ten-user>\.m2\repository
```

Thư mục có thể được thay bằng `<localRepository>` trong `settings.xml` hoặc `-Dmaven.repo.local=...`. Local repository có cấu trúc theo tọa độ artifact (`groupId`, `artifactId`, `version`, `type`, `classifier`), không đơn giản là một nơi chứa các JAR tùy ý.

Ví dụ dependency `org.junit.jupiter:junit-jupiter:5.11.0` có thể dẫn đến các file (liệt kê minh họa, không đầy đủ):

```text
~/.m2/repository/
└── org/junit/jupiter/junit-jupiter/5.11.0/
    ├── junit-jupiter-5.11.0.pom
    └── junit-jupiter-5.11.0.jar
```

Có JAR trực tiếp **chưa chắc đủ**: Maven thường cần POM của artifact để đọc các dependency bắc cầu; resolver có thể cần metadata và thông tin nguồn repository. Bản JAR chỉ là một phần của cây phụ thuộc.

### Những nhóm cần được chuẩn bị

| Loại | Ví dụ | Vì sao offline có thể thiếu? |
| --- | --- | --- |
| **Dependency trực tiếp** | `junit-jupiter`, `slf4j-api` | Chưa tải JAR/POM phiên bản đúng |
| **Dependency bắc cầu** | thư viện mà dependency khác cần | Không liệt kê trực tiếp trong `pom.xml`, nhưng Maven vẫn resolve |
| **Parent POM** | `spring-boot-starter-parent` hoặc parent nội bộ | Maven phải đọc parent để dựng effective POM trước cả khi compile |
| **BOM / import POM** | BOM trong `dependencyManagement` | Maven cần POM import để xác định phiên bản |
| **Build plugin** | `maven-compiler-plugin`, `maven-surefire-plugin` | Lifecycle chỉ chạy được nếu plugin và descriptor có sẵn |
| **Dependency của plugin** | các thư viện nội bộ của Surefire, Compiler, Checkstyle... | Plugin cũng có cây dependency riêng |
| **Build/core extension** | khai báo ở `.mvn/extensions.xml`, plugin extension | Có thể được nạp rất sớm, trước các goal thông thường |
| **Artifact theo profile / module / phase** | `-Pci`, `integration-test`, `site` | Chỉ xuất hiện khi profile/goal tương ứng được bật |
| **Plugin metadata** | `maven-metadata.xml` để map prefix hoặc chọn version | Dùng tên goal rút gọn/dynamic version có thể cần metadata chưa cache |

Trong dự án nhiều module, `mvn -pl module-b -am verify` có thể build module phụ thuộc nội bộ từ **reactor**. Nếu chạy riêng `module-b` mà không có artifact nội bộ đã cài trong local repository, offline có thể thất bại. Dùng `-am` để build các module Maven cần trong cùng reactor, hoặc cài đặt artifact cần thiết trước.

### Phải có đúng phiên bản, classifier và scope

`demo:1.0.0` và `demo:1.0.1` là hai artifact khác nhau. File `tests`, `sources`, `javadoc` và JAR chính cũng có classifier hoặc type khác nhau. Cache được bản `1.0.0` không tự thỏa yêu cầu `1.0.1`.

Các dependency `test` cũng cần nếu chạy test; `provided` có thể vẫn được dùng khi compile; dependency của plugin có thể cần kể cả khi mã nguồn không import thư viện đó. Maven chỉ dùng những artifact phù hợp với dependency graph, scope và goal thực sự được gọi.

## 3. Những gì `-o` không đảm bảo: Maven Wrapper và kho Maven là hai tầng cache

Maven Wrapper (`mvnw`/`mvnw.cmd`) có thể cần tải **bản phân phối Maven** trước khi khởi chạy Maven. Mặc định, bản phân phối Wrapper tải thường nằm ở:

```text
~/.m2/wrapper/dists/
```

Trong khi Maven Resolver lưu plugin và dependency trong:

```text
~/.m2/repository/
```

Đây là **hai thư mục phục vụ hai mục đích khác nhau**. Nếu một máy sạch chưa có Maven distribution mà dùng `./mvnw -o verify`, Wrapper có thể cố tải ZIP trước khi Maven nhận được `-o`. Chỉ cache `~/.m2/repository` sẽ không giải quyết lỗi này.

Trước khi mang dự án vào môi trường không mạng:

1. Trên máy còn mạng, chạy `./mvnw --version` hoặc `.\mvnw.cmd --version` để Wrapper tải/khởi động bản Maven đã ghim.
2. Xác minh bản Maven và Java sử dụng; nếu copy cache, bảo toàn chính xác đường dẫn, phiên bản và quyền cần thiết.
3. Làm nóng local repository cho **chính project và tập goals** cần chạy.
4. Kiểm thử offline lại bằng Wrapper và cùng phiên bản JDK.

Không nên xóa `~/.m2/wrapper/dists` hoặc `~/.m2/repository` ngay trước phiên build offline. Cần kiểm tra cả hai khi xử lý lỗi trên CI.

## 4. Vì sao plugin thiếu dù dependency đã đủ?

Một nhầm lẫn phổ biến:

> “Tôi đã tải tất cả dependency khai báo ở `<dependencies>` nên `mvn -o package` chắc chắn chạy.”

Điều này sai vì **lifecycle Maven gọi plugin**. Ví dụ đóng gói JAR có thể cần các plugin cho resources, compile, test và jar; gọi `clean verify` còn cần `maven-clean-plugin`. Mỗi plugin tự có phiên bản, POM và các dependency của chính nó.

Hai lệnh dưới đây có **tập yêu cầu khác nhau**:

```bash
mvn -o compile
mvn -o clean verify
```

`compile` không cần tất cả những gì `verify`, `clean` hoặc các integration/report goals cần. Một máy có thể chạy `mvn -o compile` thành công nhưng `mvn -o test`, `mvn -o package` hay `mvn -o site` thất bại do thiếu plugin.

Nên **ghim version plugin** ở `<build><plugins>` hoặc `<pluginManagement>` của parent POM để giảm phụ thuộc vào việc dò phiên bản mới hoặc default plugin khác nhau giữa các môi trường. Tuy vậy, chỉ khai báo version chưa đủ: artifact plugin vẫn phải có trong local repository.

### Plugin prefix cũng có thể phải được resolve

Khi chạy:

```bash
mvn -o dependency:tree
```

Maven phải xác định prefix `dependency` tương ứng plugin nào (thường là `org.apache.maven.plugins:maven-dependency-plugin`), chọn version và tìm plugin. Metadata map prefix trong repository có thể là một phần của quá trình này. Nếu local repository chưa đủ, sẽ thấy lỗi kiểu `No plugin found for prefix`, `PluginResolutionException` hoặc không tìm được version.

Có thể gọi plugin bằng tọa độ đầy đủ và phiên bản cụ thể để tránh bước suy đoán prefix/version:

```bash
mvn -o org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
```

Lệnh đầy đủ **không tự tạo ra plugin**: `maven-dependency-plugin:3.11.0` và dependencies của nó vẫn phải có trong local repository. Cách này chủ yếu giúp tên plugin/version được xác định tường minh.

## 5. Chuẩn bị trước khi mất mạng: dependency:go-offline

Apache Maven Dependency Plugin cung cấp goal **`dependency:go-offline`**, dùng để resolve dependency của project, build plugin, report plugin và dependencies của chúng khi còn kết nối.

Ví dụ tại thư mục dự án, trong môi trường **đang online**:

```bash
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.11.0:go-offline
```

Dùng Maven Wrapper trên Linux/macOS:

```bash
./mvnw -B org.apache.maven.plugins:maven-dependency-plugin:3.11.0:go-offline
```

Trên Windows PowerShell:

```powershell
.\mvnw.cmd -B org.apache.maven.plugins:maven-dependency-plugin:3.11.0:go-offline
```

Vì chỉ định đầy đủ `groupId:artifactId:version:goal`, lệnh này không phụ thuộc vào việc Maven tự suy đoán version của Dependency Plugin. Phiên bản `3.11.0` là một ví dụ đã công bố trên tài liệu chính thức; dự án có thể pin một phiên bản khác đã kiểm chứng.

**Lưu ý:** lần đầu chạy goal này, Maven **cũng phải tải chính Dependency Plugin cùng các phụ thuộc của nó**. Vì thế bắt buộc có mạng hoặc cache đủ trong lần chuẩn bị. Không chạy `-o` để mong goal `go-offline` đi lấy những artifact đang thiếu.

### Khi cần profile, module và repo nội bộ

Làm nóng đúng ngữ cảnh dự định sử dụng:

```bash
# Ví dụ chuẩn bị cho profile ci
./mvnw -B -Pci org.apache.maven.plugins:maven-dependency-plugin:3.11.0:go-offline
```

Nếu dự án thực tế dùng profile `ci`, chỉ khi đó mới chạy lệnh trên; `ci` là **tên profile minh họa**, không phải profile có sẵn trong mọi Maven project. Với project multi-module, chạy tại root reactor có khai báo `<modules>` để làm nóng các phần liên quan, và giữ nhất quán các tùy chọn `-P`, `-pl`, `-am` giữa lần warm và lần offline.

**Quan trọng: `dependency:go-offline` không bảo đảm 100% rằng mọi build sau này có thể offline.** Một số plugin chỉ resolve artifact động khi goal thực thi, tải provider ở thời điểm chạy (ví dụ môi trường test), cần toolchain riêng, hoặc có dependency theo profile/OS/JDK. Goal này cũng không tự tải trước mọi mục tiêu chưa được lựa chọn. Do đó phải chạy **đúng lifecycle/goal thực tế một lần khi online**, rồi kiểm chứng lại với `-o`.

### Trình tự có thể áp dụng trong dự án

1. **Ghim môi trường:** chốt POM/parent, version plugin, profile, Maven Wrapper, JDK, settings/mirrors và local repository sẽ sử dụng.
2. **Chuẩn bị khi online:** chạy Maven Wrapper `--version` và `dependency:go-offline`.
3. **Chạy đầy đủ goals dự kiến khi online:** ví dụ `clean verify`, và mọi goal đặc thù thực sự sẽ dùng trong mạng kín.
4. **Tắt mạng/giới hạn outbound và chạy lại với `-o`** trên cùng cache; thử riêng các profile/goal cần dùng.
5. **Đóng băng, phân phối hoặc cache dữ liệu đã kiểm chứng** cho máy offline/CI theo chính sách bảo mật và giấy phép sử dụng.

Phải thống nhất cả Maven settings và mirror: cache artifact tải từ một repository không phải lúc nào cũng được Maven chấp nhận như bản hợp lệ từ repository khác, nhất là khi có metadata/nguồn tải đi kèm. Nếu mang cache giữa môi trường, cần kiểm tra repository ID, mirror và quá trình resolve thay vì tự copy vài file JAR.

## 6. Ví dụ thực hành Java 17: build online rồi chạy offline

Đây là một dự án JAR nhỏ có source Java, dependency test JUnit và plugin build được ghim version. Nó minh họa rõ vì sao ngoài JUnit, Maven còn cần các plugin của vòng đời build. Dùng **JDK 17** và **Maven 3.9.x** (hoặc môi trường tương thích được xác minh) để thực hành.

Cây thư mục:

```text
offline-demo/
├── pom.xml
└── src/
    ├── main/java/vn/example/offline/App.java
    └── test/java/vn/example/offline/AppTest.java
```

Nội dung `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>offline-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.0</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.3.2</version>
            </plugin>
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
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Nội dung `src/main/java/vn/example/offline/App.java`:

```java
package vn.example.offline;

public class App {
    public static String message() {
        return "Maven offline OK";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

Nội dung `src/test/java/vn/example/offline/AppTest.java`:

```java
package vn.example.offline;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {
    @Test
    void messageIsStable() {
        assertEquals("Maven offline OK", App.message());
    }
}
```

File Java test dùng JUnit Jupiter API; dependency `junit-jupiter` kéo theo các module JUnit cần thiết, Surefire có thể phải resolve thêm provider của chính nó. Có mã nguồn test ở đây giúp bước `verify` thực sự kiểm tra đường test thay vì chỉ compile.

**Lần chuẩn bị có mạng**, từ thư mục `offline-demo`:

```bash
# Nếu có Maven Wrapper trong dự án, dùng ./mvnw thay mvn.
java -version
mvn --version
mvn -B org.apache.maven.plugins:maven-dependency-plugin:3.11.0:go-offline
mvn -B clean verify
```

Lệnh `clean verify` online là bước quan trọng: dù `go-offline` đã chạy, nó buộc các plugin thực tế của lifecycle và test runtime resolve khi cần. Khi dùng Wrapper, chạy `./mvnw --version` online trước để Maven distribution được cache.

**Lần kiểm thử không mạng**, không đổi POM/JDK/settings/cache:

```bash
mvn -B -o clean verify
java -cp target/offline-demo-1.0.0.jar vn.example.offline.App
```

Trên Windows PowerShell với Maven cài toàn cục:

```powershell
mvn.cmd -B -o clean verify
java -cp target/offline-demo-1.0.0.jar vn.example.offline.App
```

Nếu dự án cài Wrapper, thay lệnh Maven bằng `./mvnw -B -o clean verify` trên Unix hoặc `.\mvnw.cmd -B -o clean verify` trên Windows. Trong điều kiện các artifact và plugin đã có, test và packaging thành công; lệnh chạy ứng dụng in **chính xác**:

```text
Maven offline OK
```

Không áp đặt stdout cố định cho các lệnh Maven vì log, thời gian, phiên bản Maven, tên plugin, nguồn cache và kết quả test có thể khác nhau. Nếu build offline lỗi, xem artifact/plugin thiếu trong mục 7; không coi ví dụ này là cam kết dự án thực tế nào cũng dùng đúng các version trên.

## 7. Chẩn đoán lỗi offline theo thông báo thực tế

### 7.1. Không tìm thấy dependency trực tiếp hoặc bắc cầu

Lỗi thường có ý như:

```text
Cannot access <repository> in offline mode
and the artifact <groupId>:<artifactId>:<version> has not been downloaded before.
```

Đây là **mẫu ý nghĩa thông báo**, không phải stdout cố định giữa mọi bản Maven. Hãy tìm tọa độ artifact đầy đủ trong log, kể cả `type`/`classifier`, và xác định artifact đang được yêu cầu bởi project, parent, plugin hay dependency bắc cầu.

Cách xử lý: kết nối trở lại repository/mirror đúng quyền, gọi **đúng goal/profile** online để tải đủ artifact, rồi chạy `-o` lại. Tránh tự đặt file JAR vào cache mà thiếu POM/metadata hoặc chưa được Maven nhận diện đúng nguồn.

### 7.2. Thiếu plugin hoặc dependency của plugin

Nếu log báo `PluginResolutionException`, `PluginDescriptorParsingException`, `NoPluginFoundForPrefixException` hoặc thông báo Maven không tìm được plugin ở offline, kiểm tra:

- Plugin thực tế nào được gọi? `clean`, `compiler`, `surefire`, `jar`, `failsafe`, `site` hoặc plugin tùy biến.
- Version plugin đã ghim chưa? `pom.xml`, parent, `pluginManagement` và active profiles có thể quyết định version.
- Plugin JAR, POM và dependency của plugin có ở cache không?
- Nếu dùng prefix ngắn như `dependency:tree`, có cần metadata ánh xạ prefix? Có thể dùng tọa độ plugin đầy đủ, đã chốt version, để giảm mơ hồ.
- Goal này có tải thêm artifact ở thời điểm chạy không? Nếu có, phải warm bằng đúng goal online.

Ví dụ đã warm `mvn verify` nhưng offline lại chạy `mvn clean verify`: Maven có thể thiếu `maven-clean-plugin` nếu nó chưa được resolve trước đó. **Warm và test cùng tập goals**.

### 7.3. Parent POM hoặc BOM chưa có

Thông báo `Non-resolvable parent POM` hoặc `Non-resolvable import POM` thường xuất hiện **trước** khi vào plugin compile. Cần tải đúng parent/BOM online bằng cấu hình mirror phù hợp; nếu parent là một module cùng reactor, kiểm tra cấu trúc và `relativePath` thay vì chỉ copy dependency JAR. Đừng mặc định đây là lỗi Java source.

### 7.4. SNAPSHOT, dynamic version và metadata

Maven SNAPSHOT có thể liên quan metadata để ánh xạ bản theo timestamp; artifact dạng version range hoặc version không chốt cụ thể có thể cần metadata mới. Offline không kiểm tra có release/snapshot mới trên server.

Để build ngoại tuyến dễ tái lập:

- Ghim version release cụ thể cho dependency và plugin khi khả thi.
- Hạn chế version range, `LATEST`/`RELEASE` hoặc yêu cầu “bản mới nhất” phụ thuộc metadata remote.
- Nếu bắt buộc SNAPSHOT, đảm bảo chính xác bản snapshot, POM, artifact và metadata cần thiết đã có từ repository dự kiến.
- Đừng kết hợp `-o` với kỳ vọng `-U` sẽ lấy được snapshot mới.

### 7.5. Cache còn artifact nhưng Maven vẫn nói thiếu

Sự tồn tại của file `.jar` không chứng minh Maven Resolver dùng được nó. Local repository có thể chứa POM, metadata về nguồn repository như `_remote.repositories`, file đánh dấu lượt tải lỗi `*.lastUpdated` hoặc dữ liệu theo version/classifier khác. Một artifact tải từ repository khác hoặc được copy thủ công không phải lúc nào cũng được Maven công nhận theo cùng cách.

Kiểm tra trước:

1. Maven thực sự dùng local repository nào? `-Dmaven.repo.local`, `settings.xml` và môi trường CI có thể thay đường dẫn.
2. Tọa độ đầy đủ có khớp `groupId/artifactId/version/type/classifier` không?
3. Settings/mirror/repository ID của lần online và lần offline có khác nhau không?
4. POM của artifact, transitive dependencies hoặc plugin dependencies đã đủ chưa?
5. File cache có bị hỏng hoặc chỉ còn dấu vết tải lỗi không?

Khi còn mạng, chạy đúng goal online để Maven tự sửa/cache đúng artifact. Không xóa sạch `~/.m2` theo phản xạ; việc đó làm mất thêm các artifact khác và khiến offline càng không hoạt động.

### 7.6. Một goal thật sự cần online

Nếu plugin báo goal yêu cầu mạng, hoặc tự gọi một API ngoài repository, chỉ `-o` không thể thay thế dịch vụ đó. Cần đổi quy trình, dùng dữ liệu local được plugin hỗ trợ, tắt goal khi offline nếu phù hợp với yêu cầu nghiệp vụ, hoặc thực hiện bước đó ở môi trường online. Không báo build offline đầy đủ thành công nếu vô tình bỏ qua bước kiểm tra bắt buộc.

## 8. Cấu hình offline trong settings.xml và môi trường CI

Ngoài CLI, Maven settings có tùy chọn `<offline>`:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <offline>true</offline>
</settings>
```

Đây là **đoạn minh họa cấu trúc settings**, không phải yêu cầu ghi đè settings có sẵn. Không cần bật `<offline>true</offline>` vĩnh viễn chỉ để chạy thử một lệnh: `-o` rõ ràng hơn cho mỗi lần build và dễ gỡ khi cần tải artifact mới. Cài đặt offline trong settings áp dụng rộng hơn, có thể khiến các dự án khác trên máy bất ngờ không tải được dependency.

Với CI có bước chạy không mạng, cache cần chứa:

- Maven runtime distribution của Wrapper nếu pipeline dùng `mvnw`.
- Local repository Maven với **toàn bộ plugin và dependency** tương ứng những goals/profiles được phép chạy.
- Nếu có extension, toolchain, trình biên dịch hoặc công cụ ngoài Maven, chúng cũng phải được cung cấp sẵn.

Một cache key dựa trên `pom.xml`, `settings.xml`, `.mvn/extensions.xml` và phiên bản Wrapper giúp giảm dùng lại cache không phù hợp khi dependency hoặc plugin thay đổi. Cần phân biệt **cache của job** với một local repository tin cậy đã được chuẩn bị; việc một job có “cache hit” không bảo đảm chứa artifact cho một goal chưa từng chạy.

**Kiểm chứng tốt:** sau khi warm, chạy lại toàn bộ commands cần thiết bằng `-o` trong môi trường chặn truy cập mạng, với cùng Maven/JDK, settings và profiles. Nếu chỉ có `mvn -o validate` thành công thì chưa chứng minh `test`, `package`, `verify` hay `site` có thể chạy offline.

## 9. Các hiểu nhầm cần tránh

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “`-o` sẽ tải trước tất cả dependency.” | `-o` **ngăn truy cập remote** để resolve, không tự tải. |
| “Có tất cả `<dependencies>` là đủ.” | Còn parent/BOM, transitive dependencies, plugin, plugin dependencies, extension và metadata. |
| “`mvn -o compile` chạy được thì `mvn -o verify` chắc chắn chạy.” | Hai lifecycle cần các plugin và artifact khác nhau. |
| “Chỉ cần cache `~/.m2/repository` là Wrapper luôn khởi động.” | Wrapper distribution thường ở `~/.m2/wrapper/dists`, là tầng riêng. |
| “`dependency:go-offline` đảm bảo mọi goal offline sau này.” | Goal hỗ trợ warm dependency/plugin/report; vẫn cần chạy thử goals thật. |
| “`-U` kết hợp `-o` sẽ ép tải dependency thiếu.” | Offline không tải từ remote; `-U` không giải quyết vấn đề đó. |
| “JAR đang nằm trong cache nên Maven chắc chắn tìm thấy.” | Còn POM, tọa độ, classifier, metadata và nguồn repository. |
| “Build offline là hoàn toàn không có truy cập mạng.” | Maven Resolver không fetch remote artifacts, nhưng công cụ/plugin riêng có thể vẫn gọi mạng. |
| “Có thể xóa toàn bộ cache để chữa offline.” | Xóa cache khiến lần offline thiếu artifact hơn; chỉ xử lý đúng mục đã xác định lỗi. |

## 10. Checklist thực hành khi triển khai

1. **Xác định chính xác command cuối cùng:** `clean verify`, `package`, `site`, hoặc goal riêng; ghi lại các profile, module, JDK và settings liên quan.
2. **Chuẩn hóa phiên bản:** ưu tiên Maven Wrapper, pin plugin/dependency version và kiểm tra parent/BOM.
3. **Khi online:** khởi động Wrapper một lần, chạy Dependency Plugin `go-offline` và chạy **toàn bộ command thực tế** để tải phần còn thiếu.
4. **Kiểm thử:** ngắt mạng hoặc chặn outbound và chạy command với `-o`, ví dụ `./mvnw -B -o clean verify`.
5. **Nếu lỗi:** đọc log lấy tọa độ của artifact/plugin, phân biệt parent/BOM, plugin, dependency và cache Wrapper; chỉ bổ sung đúng phần thiếu khi được kết nối mạng.
6. **Trong CI/air-gapped:** chuyển cả hai tầng cache cần thiết bằng cách được tổ chức phê duyệt, bảo toàn integrity, dùng cùng mirror/repo settings và thử lại trên runner thật.

Có thể xem `-o` là một **bài kiểm tra tính sẵn sàng của build trong local repository**, nhưng kết quả chỉ có giá trị cho đúng code, Maven/JDK, settings, profiles và commands đã được kiểm chứng.

## Tài liệu tham khảo chính thức

- [Apache Maven — Introduction to Repositories, Building Offline](https://maven.apache.org/guides/introduction/introduction-to-repositories)
- [Apache Maven Dependency Plugin — dependency:go-offline](https://maven.apache.org/components/plugins/maven-dependency-plugin/go-offline-mojo.html)
- [Apache Maven Dependency Plugin — Goals Overview](https://maven.apache.org/plugins/maven-dependency-plugin/)
- [Apache Maven — Introduction to Plugin Prefix Mapping](https://maven.apache.org/guides/introduction/introduction-to-plugin-prefix-mapping.html)
- [Apache Maven — Maven Metadata](https://maven.apache.org/repositories/metadata.html)
- [Apache Maven — Maven Wrapper](https://maven.apache.org/tools/wrapper/)
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
