# Tệp .lastUpdated và kết quả tải thất bại được lưu cục bộ trong Maven

Khi Maven không tìm được một dependency, parent POM, BOM hoặc plugin từ remote repository, vấn đề đôi khi không biến mất ngay cả khi artifact đã được publish sau đó. Nguyên nhân có thể là Maven đã **lưu kết quả tra cứu thất bại** trong local repository để tránh liên tục gửi cùng một request đến remote repository. Với Maven 3, kết quả **artifact không tồn tại (not found)** thường được cache và để lại dấu vết ở tệp có hậu tố `.lastUpdated`.

Dấu vết này thường được gọi là **negative cache**: local repository ghi nhớ *lần kiểm tra trước không thấy artifact*, chứ không phải đã tải thành công một JAR. Trong một khoảng thời gian do **update policy** quyết định, Maven có thể không hỏi lại remote repository mà báo lỗi tương tự:

```text
... was not found in ... during a previous attempt.
This failure was cached in the local repository and resolution is
not reattempted until the update interval ... has elapsed or updates are forced.
```

Đây là **mẫu thông báo minh họa đã rút gọn**, không phải log nguyên văn cố định trên mọi Maven version. Khi gặp lỗi này, cần phân biệt chính xác **artifact chưa từng tồn tại**, **remote repository/mirror trả kết quả không tìm thấy**, **lỗi mạng/xác thực** và **negative cache phía máy client**. Xóa cache hoặc chạy `mvn -U` không thể tạo ra một artifact không tồn tại.

## 1. Maven lưu điều gì trong local repository?

Local repository thường ở `~/.m2/repository` trên Linux/macOS hoặc `%USERPROFILE%\.m2\repository` trên Windows, trừ khi bị thay bằng `settings.xml` hoặc tham số `-Dmaven.repo.local`.

Kho này có nhiều vai trò:

1. **Cache thành công**: lưu các file `.jar`, `.pom` và artifacts/metadata tải từ remote repositories.
2. **Artifact được cài cục bộ**: các artifact mà project tạo ra và cài bằng `mvn install`.
3. **Metadata và trạng thái phân giải**: ghi dấu nguồn remote, thời điểm/check trạng thái metadata và, khi chính sách cho phép, **kết quả tải thất bại**.

Local repository không chỉ là “thư mục chứa mọi JAR”. Maven Resolver có logic riêng về origin, repository ID, metadata và update policy. Vì vậy **không nên sửa hoặc xóa hàng loạt local repository** chỉ dựa trên việc thấy các file lạ. Khi xây công cụ tích hợp Maven, ưu tiên API của Resolver thay vì tự suy layout filesystem.

Giả sử ứng dụng yêu cầu dependency:

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>9999.0.0-NOT-PUBLISHED</version>
</dependency>
```

Đây là **đoạn POM** có version được tạo riêng để minh họa lỗi thiếu artifact, không phải phiên bản Commons Lang được phát hành. Với layout local repository cổ điển, Maven có thể tạo những file như:

```text
~/.m2/repository/
└── org/apache/commons/commons-lang3/
    └── 9999.0.0-NOT-PUBLISHED/
        ├── commons-lang3-9999.0.0-NOT-PUBLISHED.pom.lastUpdated
        └── commons-lang3-9999.0.0-NOT-PUBLISHED.jar.lastUpdated
```

Sơ đồ là **ví dụ các tệp có thể xuất hiện**, không bảo đảm mọi lần thất bại đều có đủ cả hai marker: Maven có thể chưa yêu cầu JAR khi POM đã thất bại, và layout/phương thức cache tùy Resolver version. Dù nhìn thấy file `.jar.lastUpdated`, **đó không phải là JAR có thể chạy**.

## 2. Vì sao Maven cần ghi nhớ lỗi tải trước đó?

Hãy tưởng tượng hệ thống CI có 200 project cùng đòi một artifact chưa được publish. Nếu mỗi project đều truy vấn remote repository nhiều lần cho cùng một GAV (groupId, artifactId, version), số request thất bại sẽ tăng vô ích, làm chậm build và gây tải lên Nexus/Artifactory/Central.

Negative caching có ba mục đích:

- Tránh request lặp lại khi khả năng kết quả vẫn là “not found”.
- Giữ build dễ dự đoán trong khoảng thời gian update policy của repository.
- Giảm lưu lượng và tải lên hệ thống lưu trữ artifact.

Nhưng negative cache cũng tạo **độ trễ quan sát**: artifact đã xuất hiện trên remote nhưng client chưa re-check vì lần tra trước báo 404. Đây là trade-off có chủ đích.

Không phải mọi lần tải thất bại đều là 404. Việc phân loại là yếu tố quan trọng hơn tên file `.lastUpdated`.

## 3. Phân biệt “not found” với lỗi truyền tải/xác thực

Apache Maven Resolver phân loại thất bại phân giải thành hai nhóm chính:

| Nhóm | Ý nghĩa | Ví dụ | Chính sách thường gặp |
| --- | --- | --- | --- |
| **Type 1 — Not found** | Artifact hoặc metadata không tồn tại ở remote repository đang xét | HTTP 404 cho một tọa độ/version chưa được publish | **Maven 3 luôn cache lỗi loại này** theo Resolver; kiểm tra lại khi update policy hết hạn hoặc buộc re-check |
| **Type 2 — Other errors** | Không thể truy cập/tải vì lỗi khác | 401, 403, timeout, lỗi proxy/TLS/transport | **Maven 3 mặc định không cache lỗi loại này** theo chính sách của Resolver |
 
Đây là mô tả hành vi của Maven 3 theo tài liệu *Maven Resolver — Local Repository, Error Handling and Caching*. Tài liệu cũng nêu Maven 4 mặc định vẫn cache type 1, và cung cấp tùy chọn `-canf false` để tắt cache not-found; **không dùng tùy chọn này với Maven 3** vì CLI không có cùng tính năng.

**Điều dễ nhầm:** tên `.lastUpdated` gợi ý “Maven lưu mọi thất bại”. Thực tế, file dấu vết được tạo/cập nhật khi **chính sách caching được bật đối với loại lỗi tương ứng**. Không được khẳng định 401/timeout luôn bị cache chỉ vì một ví dụ trên Internet từng có `.lastUpdated`. Ngay cả khi thấy marker từ lần chạy cũ, nó chưa chứng minh request mới đang bị chặn bởi cached error.

### 3.1. Not found: sai tọa độ hoặc artifact chưa được publish

Ví dụ POM tham chiếu `com.example.internal:invoice-api:1.5.0` nhưng repository chưa có bản này. Maven hỏi remote, nhận “không tìm thấy” và ghi negative cache. Nếu sau đó team publish `1.5.0`, client có thể vẫn nhìn vào kết quả cũ cho đến khi đủ điều kiện re-check.

Việc đầu tiên cần xác minh là **artifact thực sự đã tồn tại ở repository/mirror Maven đang dùng**, không chỉ “đã có trên một repository nào đó”.

### 3.2. Authentication, proxy và network: không cùng loại lỗi

Ví dụ:

- HTTP 401: thông tin đăng nhập thiếu/sai.
- HTTP 403: tài khoản không đủ quyền đọc.
- HTTP 407: proxy yêu cầu xác thực.
- TLS handshake failure, DNS failure, timeout: mạng hoặc endpoint không thể dùng.

Cách giải quyết bắt đầu từ `settings.xml`, mirror, `<servers>`, `<proxies>`, certificate hoặc repository availability, **không phải xóa marker**. Với chính sách mặc định của Maven 3, những lỗi type 2 này không thuộc negative cache not-found như 404; sửa cấu hình mạng/xác thực thường là cần thiết.

**Ngoại lệ vận hành:** một repository proxy nội bộ có thể **trả 404** vì upstream không truy cập được, artifact bị chặn hoặc repository group thiếu nguồn. Từ góc nhìn client, response là “not found” và có thể bị cache type 1, dù nguyên nhân sâu xa ở repository manager chứ không phải thiếu artifact toàn Internet.

## 4. Tệp .lastUpdated là gì? Không phải ngày phát hành artifact

Khi Resolver bật error caching, nó có thể lưu một tệp Java Properties tại đường dẫn local repository tương ứng với file artifact nhưng thêm hậu tố `.lastUpdated`.

Ví dụ tên file:

```text
some-lib-1.2.0.jar.lastUpdated
some-lib-1.2.0.pom.lastUpdated
```

Hãy hiểu phần mở rộng:

- `some-lib-1.2.0.jar` là **đường dẫn dự kiến của artifact JAR thành công**.
- `.lastUpdated` là **marker / trạng thái tra cứu remote**, không phải định dạng JAR hay một file build output.
- Một artifact có thể cần cả POM lẫn JAR; chúng được resolve riêng và có thể có marker riêng.
- File có thể tồn tại sau một số trạng thái lịch sử; **không dùng sự hiện diện của nó làm bằng chứng duy nhất** rằng phiên bản hiện tại không thể tải.

Theo tài liệu Resolver, file chứa property với khóa dạng `<canonical-remote-url>.error` cho remote repository đã kiểm tra. Khi lỗi type 1 được cache, giá trị `.error` tương ứng là chuỗi rỗng; khi chính sách khác bật caching cho type 2, giá trị có thể chứa thông tin lỗi.

Ví dụ **sơ đồ khái niệm**, không phải snapshot thực tế hay format ổn định để parse bằng script:

```properties
https://repo.example.org/repository/maven-public/.error=
```

Khóa phụ thuộc canonical URL của repository mà Resolver đã xét (có thể là URL của mirror), và thực tế file có thể chứa thông tin timestamp, property escaping và nhiều repository entries khác. Đừng giả định tên khóa luôn đúng như ví dụ, hoặc chỉ cần đổi nội dung `.error` bằng tay là Maven “hết lỗi”.

### 4.1. Vì sao có nhiều file marker cho cùng một dependency?

Dependency resolution thường cần nhiều bước, tùy tình huống:

1. Đọc POM (artifact descriptor) để biết dependency bắc cầu, parent, dependency management.
2. Phân giải metadata nếu dùng SNAPSHOT, version range, plugin prefix hoặc version cần metadata.
3. Tải artifact chính, chẳng hạn JAR.
4. Có thể tải thêm sources/javadoc/test classifier nếu tool yêu cầu.

Mỗi bước là một tài nguyên khác nhau. Vì vậy marker cho POM, JAR và metadata **không tương đương**. Một JAR đã có cũng không bảo đảm POM descriptor hoặc parent POM có thể resolve đúng.

Đặc biệt, thiếu parent POM có thể làm Maven dừng **trước khi compile**; thiếu plugin POM có thể làm build thất bại dù toàn bộ dependencies ứng dụng đã cache.

## 5. Phân biệt .lastUpdated với _remote.repositories, metadata và artifacts đã tải

Khi chẩn đoán trong local repository, có thể gặp các loại tệp:

| Tệp hoặc pattern | Ý nghĩa thường gặp | Có phải dấu hiệu cache lỗi tải không? |
| --- | --- | --- |
| `library-1.0.0.jar` | Binary artifact được lưu hoặc cài cục bộ | **Không** |
| `library-1.0.0.pom` | Project descriptor của artifact | **Không** |
| `library-1.0.0.jar.lastUpdated` | Dấu vết kiểm tra tải JAR khi Resolver dùng error/update tracking | **Có thể** |
| `library-1.0.0.pom.lastUpdated` | Dấu vết kiểm tra tải POM | **Có thể** |
| `_remote.repositories` | Theo dõi artifact được cache từ remote repository/origin hoặc local install theo enhanced Local Repository Manager | **Không phải** log 404 |
| `maven-metadata-<repoId>.xml` | Metadata versions/SNAPSHOT hoặc thông tin artifact từ repository | **Không** |
| `resolver-status.properties` | Trạng thái/check timestamp cho một số hoạt động metadata resolution trong các cấu hình Maven | **Không đồng nghĩa** marker 404 JAR |

**Không xóa `_remote.repositories` để xử lý lỗi 404 theo thói quen.** Maven Resolver enhanced local repository manager dùng thông tin origin để phân biệt artifact đã tải từ R1 với artifact từ R2. Khi repository đang active thay đổi, cùng một file vật lý trong cache có thể không được coi là artifact phù hợp cho context mới; đó là bảo vệ integrity, không phải chỉ một bug ở marker.

Một số phiên bản Resolver có split local repository hoặc chiến lược tổ chức cache khác; layout ví dụ ở bài mang tính minh họa của Maven 3.x thông dụng. Với tool chuyên dụng, ưu tiên API Maven Resolver và không hardcode giả định về tệp nội bộ.

## 6. updatePolicy ảnh hưởng thời điểm Maven thử tải lại

`updatePolicy` áp dụng cho repository policy và quyết định tần suất Maven kiểm tra remote artifact/metadata. Các giá trị thường được tài liệu Maven mô tả:

| Giá trị | Ý nghĩa gần đúng |
| --- | --- |
| `always` | Cho phép Maven thường xuyên kiểm tra cập nhật |
| `daily` | Theo chu kỳ ngày; thường là giá trị mặc định |
| `interval:X` | Sau khoảng X phút, ví dụ `interval:15` |
| `never` | Không kiểm tra cập nhật theo chu kỳ thông thường; cần hiểu tương tác với artifact chưa có và các CLI flags |

Ví dụ đoạn POM repository policy:

```xml
<repositories>
    <repository>
        <id>internal-releases</id>
        <url>https://repo.example.org/repository/maven-releases/</url>
        <releases>
            <enabled>true</enabled>
            <updatePolicy>daily</updatePolicy>
        </releases>
        <snapshots>
            <enabled>false</enabled>
        </snapshots>
    </repository>
</repositories>
```

Đây là **đoạn XML đặt trong `<project>` hoặc một POM profile**, không phải POM độc lập. URL `repo.example.org` là ví dụ, không phải repository có thật. Các policy tương tự cũng có thể khai báo trong repository definitions ở **settings profiles**.

Những lưu ý:

- Với release artifact đã có trong local repo, updatePolicy **không có nghĩa Maven tự tải lại mọi JAR đã lưu trong mỗi build**; release versions về nguyên tắc bất biến.
- Với missing artifact hoặc SNAPSHOT metadata, update policy ảnh hưởng việc Maven re-check remote.
- Mirror từ settings có thể điều hướng URL repository thực tế; cấu hình `updatePolicy` và repository ID nên được kiểm tra bằng effective POM/settings.
- Plugin repositories có policy riêng; không phải mọi lỗi plugin đều được giải quyết bằng thay `<repositories>` dùng cho dependencies.
- Một repository manager có **negative cache phía server** riêng: client hết cache hoặc chạy `-U` chưa chắc làm server proxy truy vấn upstream lập tức.

Không đặt `<updatePolicy>always</updatePolicy>` trong mọi repository chỉ để né lỗi cá biệt: sẽ tăng request và có thể làm build chậm hoặc gây tải không cần thiết.

## 7. mvn -U thực sự giúp gì?

Trong Maven 3, `-U` (CLI option `--update-snapshots`, tên lịch sử) được tài liệu mô tả là **buộc kiểm tra lại missing releases và updated snapshots ở remote repositories**.

Ví dụ:

```bash
mvn -U clean verify
```

Nếu artifact trước đó bị cache là “not found” nhưng **hiện đã tồn tại ở đúng remote repository**, và máy có kết nối/credentials hợp lệ, `-U` là cách ít phá hủy nhất để yêu cầu Maven kiểm tra lại.

**`-U` không làm được những việc sau:**

- Không tạo ra một artifact/version mà repository chưa có.
- Không tự sửa sai groupId, artifactId, version, type/classifier.
- Không cấp quyền 401/403, không sửa proxy/TLS/DNS.
- Không phá vỡ quy tắc offline của `-o`; offline không truy cập remote.
- Không bảo đảm repository manager phía server bỏ negative cache hoặc proxy lại upstream.
- Không đồng nghĩa xóa sạch local repository và tải lại mọi release artifact đang có.
- Không thay phiên bản dependency được Maven chọn từ dependency management/BOM.

Ví dụ sau **vẫn phải thất bại** nếu tọa độ không hề được publish:

```bash
mvn -U -B clean package
```

Bởi `-U` chỉ yêu cầu kiểm tra lại. Nếu remote tiếp tục trả 404, Maven tiếp tục báo không tìm thấy và có thể cập nhật dấu vết lỗi.

**Khác biệt Maven 4:** Maven 4 còn có các cờ cập nhật chi tiết trong tài liệu CLI mới như `-UA` (artifact checks) và `-UM` (metadata updates), cùng tùy chọn `-canf false` trong tài liệu Resolver về cache not-found. Đừng sao chép chúng vào script Maven 3 mà không kiểm tra `mvn --version` và `mvn --help`.

## 8. Ví dụ Java 17: tạo lỗi not-found có chủ đích và quan sát marker

Ví dụ này có hai lần build:

1. **Bản POM sai**: yêu cầu một version không tồn tại của Apache Commons Lang và build **dự kiến thất bại**.
2. **Bản POM đã sửa**: thay version bằng một release thực tế, build thành công và Java in stdout cố định.

Không phụ thuộc vào việc tạo repository manager giả và không yêu cầu xóa cache. Để quan sát marker, cần Maven online với Central hoặc mirror trả kết quả not-found đúng cho tọa độ sai.

### 8.1. Cấu trúc project

```text
negative-cache-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── vn/example/cache/App.java
```

### 8.2. POM ban đầu cố ý sai version

File `negative-cache-demo/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>negative-cache-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>9999.0.0-NOT-PUBLISHED</version>
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

Thư viện `org.apache.commons:commons-lang3` **có thật**, nhưng version `9999.0.0-NOT-PUBLISHED` được chọn để **không tồn tại trong Maven Central**. Ví dụ kỳ vọng nhận 404 và negative cache cho version đó. Nếu mạng chặn Central, proxy trả 401/503 hoặc offline, failure mode sẽ khác và marker không bảo đảm xuất hiện.

### 8.3. Java source hợp lệ khi dùng bản dependency thật

File `src/main/java/vn/example/cache/App.java`:

```java
package vn.example.cache;

import org.apache.commons.lang3.StringUtils;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        String input = " \t ";
        String state = StringUtils.isBlank(input) ? "READY" : "ERROR";
        System.out.println("Maven negative cache demo: " + state);
    }
}
```

`StringUtils.isBlank` là API của Apache Commons Lang. Chương trình sẽ in `READY` khi được biên dịch và chạy với một bản Commons Lang phù hợp.

### 8.4. Chạy lần đầu: cố ý thất bại

Từ thư mục `negative-cache-demo`, với Maven 3.9.x, JDK 17+, mạng online, và plugins có thể tải từ repository:

```bash
java -version
mvn --version
mvn -B clean package
```

**Kết quả mong đợi:** build thất bại vì không phân giải được `commons-lang3:9999.0.0-NOT-PUBLISHED`. Đây là kết quả được thiết kế, không phải lỗi trong mã Java. Không có output `Maven negative cache demo: READY` vì chương trình chưa được chạy.

Chạy lại **cùng POM**:

```bash
mvn -B clean package
```

Ở lần hai, với same repository context và updatePolicy chưa hết hạn, Maven có thể phát lại thông tin lỗi từ local negative cache mà không gửi request giống hệt đến remote. Thông báo thường chứa từ khóa `cached in the local repository` hoặc `not reattempted until the update interval`.

**Quan trọng:** lệnh thứ hai chỉ minh họa cơ chế khi negative cache được dùng; không cam kết byte-for-byte log, số request hoặc marker giống nhau trên mọi Maven/mirror/version.

### 8.5. Quan sát tệp .lastUpdated đúng thư mục

Nếu local repository ở vị trí mặc định, thư mục cần xem (với version cố ý sai) là:

```text
org/apache/commons/commons-lang3/9999.0.0-NOT-PUBLISHED/
```

Linux/macOS:

```bash
ls -la ~/.m2/repository/org/apache/commons/commons-lang3/9999.0.0-NOT-PUBLISHED/
```

Windows PowerShell:

```powershell
Get-ChildItem "$env:USERPROFILE\.m2\repository\org\apache\commons\commons-lang3\9999.0.0-NOT-PUBLISHED" -ErrorAction SilentlyContinue
```

Tìm file kết thúc bằng `.pom.lastUpdated` hoặc `.jar.lastUpdated`. Nếu không thấy, **đừng tự tạo marker bằng tay**; kiểm tra xem Maven thực tế dùng `settings.xml` khác, local repo tùy chỉnh, split local repository, repository proxy có lỗi khác hoặc request chưa đến giai đoạn tương ứng.

Đọc marker khi cần có thể giúp tìm canonical repository URL/check status, nhưng file có thể chứa thông tin endpoint nội bộ. Không copy nguyên file vào issue công khai. Thay đổi nội dung marker bằng tay là hành động không được khuyến khích.

### 8.6. Dùng -U với tọa độ sai: vẫn lỗi

Giữ nguyên version `9999.0.0-NOT-PUBLISHED` rồi chạy:

```bash
mvn -B -U clean package
```

**Kết quả mong đợi vẫn là build FAILED**, vì artifact chưa tồn tại dù Maven đã re-check. Nếu chỉ nhìn thấy build failed mà kết luận `-U` “không hoạt động”, đó là chẩn đoán thiếu: nó có thể đã hoạt động đúng bằng cách hỏi lại rồi nhận 404 mới.

### 8.7. Sửa đúng nguyên nhân: đổi về release có thật

Trong cùng `pom.xml`, thay **chỉ** dòng dependency version:

```xml
<version>9999.0.0-NOT-PUBLISHED</version>
```

thành:

```xml
<version>3.14.0</version>
```

Đây là **hai đoạn XML để thay thế trong dependency `commons-lang3`**, không phải hai POM hoàn chỉnh. Version `3.14.0` là một release có thật của Apache Commons Lang.

Chạy lại:

```bash
mvn -B clean package
```

Nếu Maven có quyền lấy đúng `commons-lang3:3.14.0` và các build plugins, build thành công, tạo:

```text
target/negative-cache-demo-1.0.0.jar
```

JAR mặc định không nhúng Commons Lang dependency, nên chạy với đầy đủ classpath. Linux/macOS:

```bash
java -cp "target/negative-cache-demo-1.0.0.jar:$HOME/.m2/repository/org/apache/commons/commons-lang3/3.14.0/commons-lang3-3.14.0.jar" vn.example.cache.App
```

Windows PowerShell:

```powershell
java.exe -cp "target/negative-cache-demo-1.0.0.jar;$env:USERPROFILE\.m2\repository\org\apache\commons\commons-lang3\3.14.0\commons-lang3-3.14.0.jar" vn.example.cache.App
```

**Stdout chính xác của chương trình**:

```text
Maven negative cache demo: READY
```

**Tại sao sửa version giải quyết được?** Negative cache của `9999.0.0-NOT-PUBLISHED` không phải “lệnh cấm toàn bộ dependency `commons-lang3`”. Nó liên quan resource/version/repository được tra cứu. Khi project chuyển sang version hợp lệ `3.14.0`, Maven resolve artifact mới và build bình thường.

Nếu tổ chức dùng `-Dmaven.repo.local=/path/to/custom-repo` hoặc cấu hình `<localRepository>`, hãy sửa đường dẫn Java classpath theo local repo thật. Những lệnh trên dùng layout cổ điển mặc định và không nhằm hỗ trợ mọi kiểu split local repository.

## 9. Các trường hợp xử lý thực tế theo thứ tự ưu tiên

### 9.1. Artifact vừa được publish nhưng Maven vẫn báo cache cũ

**Triệu chứng:**

```text
Could not find artifact com.example:report-api:jar:1.5.0
... failure was cached in the local repository ...
```

**Giả thuyết:** request trước gặp not-found và bị cache; artifact nay đã xuất hiện trong repository đúng, Maven chưa tới kỳ re-check.

Thứ tự xử lý:

1. Kiểm tra tọa độ `groupId:artifactId:version[:type[:classifier]]`, scope và POM đang chạy.
2. Xác minh artifact **POM và file binary tương ứng** đã publish hoàn tất ở endpoint Maven đang dùng.
3. Kiểm tra mirror/`mirrorOf` trong settings, repository ID và quyền của CI user.
4. Chạy `mvn -U -B verify` **một lần** sau khi sửa nguồn hoặc xác nhận publish.
5. Nếu vẫn báo 404, kiểm tra negative cache ở Nexus/Artifactory proxy (phía server), propagation delay, snapshot/release repository policy và chính tên version.

Không nên xóa `~/.m2/repository` của cả người dùng chỉ vì một release vừa được publish.

### 9.2. Dependency bị typo hoặc version không tồn tại

Nếu POM khai báo `com.example:lib:2.0.00` trong khi repository chỉ có `2.0.0`, cached miss là **hệ quả đúng** của dữ liệu sai. Sửa tọa độ hoặc version là giải pháp. `mvn -U` với version sai chỉ làm lặp lại 404.

Nếu Maven dùng BOM/parent management, version thực tế có thể đến từ `dependencyManagement` chứ không xuất hiện trực tiếp trong `<dependencies>`. Dùng effective POM và `dependency:tree` để xác định version đã chọn.

### 9.3. Missing plugin hoặc parent POM

Ví dụ log:

```text
Plugin org.apache.maven.plugins:maven-jar-plugin:... could not be resolved
Non-resolvable parent POM ...
```

Không nên chỉ chạy `dependency:tree` rồi kết luận mọi thứ đầy đủ: lỗi có thể thuộc **pluginRepositories**, parent POM, imported BOM hoặc extension chưa resolve được.

- Kiểm tra `<parent>` hoặc BOM `<type>pom</type><scope>import</scope>`.
- Kiểm tra plugin version và pluginRepositories/mirror.
- Parent/BOM/plugin POM là artifact có thể để lại `.lastUpdated` nếu request not-found được cache.
- `mvn -U` sẽ re-check missing artifacts trong context phù hợp, nhưng không sửa version hoặc repository sai.

### 9.4. Snapshot vừa được deploy

Với `1.5.0-SNAPSHOT`, Maven có thể cần metadata để biết bản timestamped SNAPSHOT hiện có. Lỗi cần phân biệt:

- SNAPSHOT repository chưa được cấu hình hoặc policy `snapshots.enabled` là false;
- snapshot chưa publish hoàn tất hoặc metadata chưa cập nhật;
- local metadata/updatePolicy chưa đến kỳ re-check;
- repository proxy phía server còn cache dữ liệu cũ.

`mvn -U` thường dùng để yêu cầu kiểm tra snapshot updates theo Maven CLI 3. Nhưng đừng nhầm **metadata snapshot** với marker `.lastUpdated` của một JAR cụ thể. Kiểm tra repository và metadata theo yêu cầu thực tế.

### 9.5. Offline mode

Nếu chạy:

```bash
mvn -o clean package
```

Maven không được phép truy cập remote repositories theo Maven Resolver. Nếu dependency hoặc plugin chưa có đủ trong local cache, build có thể thất bại. `-U` không làm xuất hiện artifact khi vẫn offline.

Ví dụ **không phải lệnh sửa negative cache**:

```bash
mvn -o -U clean package
```

Hai cờ có mục đích khác nhau; khi offline, không có remote request mới để re-check. Muốn tải artifact thiếu, cần một lần build online với nguồn remote hợp lệ trước.

## 10. Đọc đúng lỗi và xác định repository được hỏi

Không chỉ tìm chuỗi `.lastUpdated` trong filesystem; trước tiên đọc thông báo Maven và tìm:

- **Artifact coordinates**: `groupId`, `artifactId`, version, extension/type, classifier.
- **Artifact kind**: dependency JAR, POM parent, BOM, Maven plugin hay metadata.
- **Remote repository ID và URL**: Central, mirror nội bộ hoặc repository riêng.
- **Failure class**: not found / 404, authentication 401/403, proxy 407, timeout/TLS.
- **Update policy / “cached” wording**: lỗi có nói sẽ không reattempt cho đến lúc interval hết hoặc update bị forced?
- **Đúng profile/settings**: repository có thể được khai báo trong parent, POM profile hoặc settings profile; mirror có thể thay endpoint.
- **Local repository thật**: lấy từ `settings.xml`/CLI options; đừng đoán luôn là `~/.m2/repository`.

Các lệnh hỗ trợ:

```bash
mvn --version
mvn help:effective-settings
mvn help:effective-pom -Doutput=effective-pom.xml
mvn dependency:tree
```

Các goal `help:*` và `dependency:tree` yêu cầu plugin tương ứng. Khi chính plugin bị cache miss, những lệnh chẩn đoán đó **cũng có thể thất bại**; hãy đọc log root cause, không xem sự thất bại của lệnh Help Plugin là bằng chứng ứng dụng sai source.

Trong CI nội bộ, có thể tạm bật log chi tiết:

```bash
mvn -B -X -U verify
```

**Bảo mật:** log `-X` và effective-settings có thể lộ repository URLs, file paths, headers/metadata hoặc chi tiết credential tùy plugin/transport/version. Chỉ chạy khi được phép và **lọc secrets** trước khi gửi log cho người khác.

## 11. Có nên xóa .lastUpdated thủ công?

**Thứ tự can thiệp từ ít đến nhiều rủi ro:**

1. Sửa tọa độ/POM hoặc publish artifact cần thiết.
2. Sửa mirror/repositories, credentials và proxy.
3. Khi online và remote đã đúng, chạy `mvn -U` một lần.
4. Nếu thật sự còn một marker cũ cản trở, xác định **đúng artifact/version** và cân nhắc thao tác **targeted cleanup** sau khi dừng các Maven processes đang dùng cùng local repository.
5. Chỉ trong trường hợp có kế hoạch quản trị cache, mới cân nhắc rebuild cache riêng. **Không xoá toàn bộ `~/.m2/repository` theo phản xạ.**

### 11.1. Targeted cleanup bằng Maven Dependency Plugin

Maven Dependency Plugin có goal `purge-local-repository` để loại một nhóm dependencies ở local repository và tùy chọn resolve lại. Ví dụ khi đã xác định artifact cần làm mới:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.11.0:purge-local-repository -DmanualInclude=org.apache.commons:commons-lang3 -DreResolve=false
```

**Cảnh báo trước khi chạy:**

- Đây là lệnh **xóa cache của artifact được chỉ định**, không chỉ xóa file `.lastUpdated`.
- Tùy tham số, scope và plugin version, có thể xóa một hoặc nhiều version dưới group/artifact. Đừng chạy trên local repository được chia sẻ nếu không có phối hợp.
- `manualInclude` chỉ định artifact được purge; khi dùng tham số này plugin không thực hiện purge theo dependency tree bình thường.
- `reResolve=false` ngăn plugin tự resolve lại ngay sau purge; build sau sẽ phải tải artifact khi cần.
- Plugin này cũng phải được resolve; nếu môi trường offline/mirror lỗi, bản thân lệnh purge có thể thất bại.

Thông thường, **`mvn -U` đủ** khi vấn đề đơn thuần là cached not-found và artifact nay đã tồn tại. Không cần purge chỉ để “phòng xa”.

### 11.2. Nếu buộc phải xóa một marker bằng thao tác filesystem

Chỉ thực hiện sau khi:

1. Xác định **local repository thật** bằng cấu hình Maven đang chạy.
2. Xác định đúng tọa độ và đường dẫn artifact bị lỗi.
3. Dừng các Maven processes có thể đang dùng cùng local repository.
4. Kiểm tra chính xác file là `<artifact>.pom.lastUpdated` hoặc `<artifact>.jar.lastUpdated`, không phải JAR/POM hợp lệ.
5. Có bản sao hoặc kế hoạch rollback trong môi trường CI quan trọng.

Ví dụ đường dẫn cần **kiểm tra**, không phải lệnh xóa tự động:

```text
~/.m2/repository/com/example/report-api/1.5.0/report-api-1.5.0.pom.lastUpdated
```

Maven Resolver docs cảnh báo việc dựa vào thao tác filesystem trực tiếp có thể phá vỡ logic origin/locking và không phù hợp với local repository kiểu split. Đừng xây script tự động xóa mọi `*.lastUpdated` trên máy dev hoặc CI: dấu vết lỗi ở một repository không chứng minh toàn bộ cache sai.

Nếu cần cách chắc chắn kiểm tra khác biệt môi trường, một job CI có thể dùng **local repository riêng biệt**:

```bash
mvn -Dmaven.repo.local=/tmp/maven-cache-diagnosis -B -U verify
```

Thư mục trên là ví dụ Unix; Maven sẽ tải lại plugins/dependencies cần thiết nên thời gian và dung lượng có thể tăng. Cách này hữu ích để xác minh liệu local cache cũ có liên quan; vẫn không khắc phục được tọa độ sai hay upstream/mirror trả 404.

## 12. Negative cache ở client và negative cache của repository manager

Trong tổ chức, thường có ít nhất hai lớp:

```text
Ứng dụng Maven trên laptop/CI
    |
    |  local repository / .lastUpdated
    v
Repository manager: Nexus / Artifactory / mirror công ty
    |
    |  server-side proxy cache / negative cache
    v
Maven Central hoặc kho upstream khác
```

**Client negative cache:** Maven quyết định chưa cần hỏi lại remote do cached not-found và updatePolicy. `-U` có thể buộc client re-check.

**Repository manager negative cache:** server từng hỏi upstream nhưng nhận 404, sau đó tạm lưu kết quả không tìm thấy. Khi client gửi request mới, server có thể vẫn trả 404 từ cache. `-U` phía client **không bắt buộc server xóa cache**; cần quản trị viên xác minh upstream proxy, TTL/cache invalidation và quyền theo từng repository manager.

Một tình huống thực tế:

1. Service A được build lúc 09:00 khi `com.example:orders-client:2.0.0` chưa publish.
2. Maven lưu negative cache cục bộ của “not found”.
3. Artifact được publish lúc 09:10; repository manager có thể nhìn thấy nó ngay hoặc sau thời gian đồng bộ/cache.
4. CI build lúc 09:15 có thể vẫn báo cached miss ở client.
5. Chạy `mvn -U` buộc client re-check. Nếu manager vẫn trả 404, điều tra cache/upstream phía server thay vì xóa toàn bộ local repository.
6. Khi repository manager trả file hợp lệ và client tải được, build chạy lại bình thường với đúng version.

Các mốc thời gian và tên artifact ở đây là **tình huống minh họa**, không phải log hoặc SLA thực tế.

## 13. Đừng nhầm .lastUpdated với lỗi compile, xung đột phiên bản hay tệp bị hỏng

Một số lỗi có triệu chứng giống “dependency không dùng được”, nhưng cơ chế khác hẳn:

| Triệu chứng | Bản chất | Hướng kiểm tra |
| --- | --- | --- |
| Maven báo `was cached ... not reattempted` cho missing artifact | Có thể là negative cache not-found | Tọa độ, remote tồn tại, `-U`, policy |
| `Could not find artifact` ngay sau lần thử đầu | Artifact bị thiếu hoặc remote trả not-found; marker có thể mới tạo | Tọa độ và repository |
| `401 Unauthorized` hoặc `403 Forbidden` | Quyền truy cập | Settings server ID/credentials, policy |
| `PKIX path building failed` | Chứng chỉ/TLS trust | Java truststore, proxy/certificate |
| `Connection timed out` | Network/endpoint/proxy | Mạng, VPN, proxy, repo status |
| `Non-resolvable parent POM` | Parent POM thiếu/không resolve được | Parent coordinates, `relativePath`, repository |
| `Plugin ... could not be resolved` | Plugin/POM/metadata/pluginRepository có vấn đề | Plugin versions, mirrors, pluginRepositories |
| `NoSuchMethodError` khi chạy Java | Binary API/version mismatch, classpath khác, duplicate class | Effective dependency tree, runtime classloading |
| `checksum validation failed` | File tải/metadata/checksum không hợp lệ | Artifact integrity, repository checksum policy |
| `mvn -o` báo artifact chưa được tải | Offline cache chưa đủ hoặc origin không hợp lệ | Chạy online khi có quyền, cache policy |
| Một JAR nằm trong `~/.m2/repository` nhưng Maven vẫn muốn tải | Có thể liên quan repository origin/context, layout hoặc artifact key | Enhanced LRM, `_remote.repositories`, settings |
| POM đã được Maven parse nhưng Java compile lỗi | Source/compiler/JDK hoặc API không phù hợp | Error compiler, `mvn --version`; không xóa marker vội |

**Không lấy việc có nhiều phiên bản trong local repository làm dấu hiệu âm tính.** Maven có thể lưu nhiều versions đã tải qua thời gian. Điều quan trọng là **version nào hiện được chọn**, file nào đã resolve, và repository context nào đã được xét.

## 14. Best practices khi vận hành build và CI

1. **Pin versions** của dependencies, parent BOM và build plugins phù hợp; release versions nên bất biến.
2. **Publish trước khi consumer build**: khi pipeline tạo library nội bộ, đừng chạy consumer song song trước khi library POM/JAR và metadata được publish hoàn tất.
3. **Quản lý repository manager**: mirrorOf, upstream proxy, snapshot/release policies, quyền đọc và cache TTL phải rõ.
4. **Giữ updatePolicy hợp lý**: mặc định theo chu kỳ là bình thường; chỉ dùng `-U` khi có lý do buộc re-check.
5. **Không đặt Maven local repository chung giữa CI jobs thiếu khóa và phân quyền**. Maven Resolver có cơ chế locking; vẫn cần cấu hình đúng khi nhiều processes/machines dùng chung filesystem.
6. **Lưu log đủ để truy dấu**: groupId, artifactId, version, repository ID, Maven version, profile/CLI flags; loại secrets.
7. **Tách project build với cache chẩn đoán**: một local repository sạch trong job điều tra giúp loại trừ state cũ nhưng làm tăng downloads.
8. **Không parse marker như API ổn định**: `.lastUpdated` và file metadata nội bộ phụ thuộc Resolver implementation và có thể thay đổi.
9. **Không cache kết quả lỗi 404 vô thời hạn ở CI** nếu pipeline publish artifacts mới thường xuyên; dùng repository policies/forced re-check đúng điểm, hoặc quản lý cache job theo vòng đời build.
10. **Theo dõi root cause**: nếu một library nội bộ chưa publish, sửa publish/dependency coordination thay vì xóa cache ở hàng trăm runners.

## 15. Tự kiểm tra và đáp án

**Câu 1.** Một library version `1.5.0` chưa có trên repository lúc bạn chạy Maven. Sau đó đồng đội publish nó, nhưng Maven vẫn báo “failure cached”. Có cần xóa toàn bộ `~/.m2/repository` không?

**Đáp án:** Không. Kiểm tra tọa độ/version và repository thật sự đã có file; chạy `mvn -U` online để client re-check. Nếu vẫn nhận 404, kiểm tra proxy repository manager và upstream/permissions. Chỉ cân nhắc targeted cleanup nếu có bằng chứng cache cũ gây vấn đề.

**Câu 2.** Lỗi timeout khi kết nối Nexus có được Maven 3 cache y như 404 theo chính sách mặc định không?

**Đáp án:** Không. Theo Maven Resolver, Maven 3 luôn cache type 1 not-found, còn type 2 như timeout/authentication mặc định không được cache theo cùng error-cache policy. Cần xử lý mạng/proxy/server, không chỉ xóa `.lastUpdated`.

**Câu 3.** Trong `~/.m2/repository` có file `lib-2.0.0.jar.lastUpdated`. Có thể dùng nó trong Java classpath không?

**Đáp án:** Không. Đó không phải JAR; nó là marker trạng thái phân giải. Chương trình cần file artifact JAR thật (hoặc classes thực sự), đúng runtime classpath.

**Câu 4.** `mvn -U verify` vẫn báo không tìm thấy dependency có version gõ sai. `-U` có hỏng không?

**Đáp án:** Không thể kết luận như vậy. `-U` có thể đã buộc Maven re-check, nhưng phiên bản sai vẫn không tồn tại. Phải sửa dependency coordinates/version hoặc publish artifact hợp lệ vào repository đúng.

**Câu 5.** Maven client chạy `-U` nhưng Nexus proxy vẫn trả 404 từ cache. Đang gặp lớp cache nào?

**Đáp án:** Có thể là **server-side negative cache** của repository manager. Maven client không bắt buộc xóa server cache; quản trị viên cần kiểm tra upstream/proxy cache TTL hoặc invalidate theo chính sách hệ thống.

**Câu 6.** Dự án đang dùng `mvn -o` và thiếu Maven Compiler Plugin. Có thể chạy `mvn -o -U` để tự tải plugin không?

**Đáp án:** Không. Offline không cho Maven Resolver tải remote artifacts. Phải chuẩn bị cache đầy đủ trong một bước online có quyền truy cập repository.

## Tài liệu chính thức

- [Apache Maven Resolver — Local Repository, Error Handling and Caching](https://maven.apache.org/resolver/local-repository.html)
- [Apache Maven — Maven Local Repositories](https://maven.apache.org/repositories/local.html)
- [Apache Maven 3 — CLI Options Reference (đặc biệt -U và -o)](https://maven.apache.org/ref/3-LATEST/maven-embedder/cli.html)
- [Apache Maven — POM Reference: repositories/updatePolicy](https://maven.apache.org/pom.html)
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven Dependency Plugin — purge-local-repository](https://maven.apache.org/plugins/maven-dependency-plugin/purge-local-repository-mojo.html)
- [Apache Maven Dependency Plugin — Purging local repository](https://maven.apache.org/plugins/maven-dependency-plugin/examples/purging-local-repository.html)
- [Apache Maven Resolver API — ResolutionErrorPolicy](https://maven.apache.org/resolver/apidocs/org/eclipse/aether/resolution/ResolutionErrorPolicy.html)
