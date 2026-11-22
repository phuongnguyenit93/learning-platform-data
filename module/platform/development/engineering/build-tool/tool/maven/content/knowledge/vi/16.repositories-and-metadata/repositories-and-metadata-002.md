# Cấu trúc đường dẫn kho theo `groupId`, `artifactId` và `version` trong Maven

## 1. Vì sao Maven tìm được một JAR mà không cần biết tên thư mục thủ công?

Khi khai báo một dependency trong `pom.xml`, bạn thường chỉ viết ba tọa độ:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.14.0</version>
</dependency>
~~~

Maven có thể chuyển những tọa độ này thành đường dẫn chuẩn trong repository:

~~~text
org/apache/commons/commons-lang3/3.14.0/commons-lang3-3.14.0.jar
~~~

Tại repository Maven Central, URL tương ứng có dạng:

~~~text
https://repo.maven.apache.org/maven2/org/apache/commons/commons-lang3/3.14.0/commons-lang3-3.14.0.jar
~~~

Maven gọi quy tắc này là **repository layout**. Nó là cách ánh xạ tọa độ artifact sang đường dẫn trong kho Maven, giúp các công cụ build và repository manager hiểu cùng một cấu trúc, thay vì phải khai báo đường dẫn tùy ý cho từng JAR.

Bài học thuộc nhóm **Kho và metadata**, tập trung vào:

- Cách biến `groupId:artifactId:version` thành thư mục và tên file theo layout mặc định (*maven2/default*).
- Vai trò của `classifier`, phần mở rộng file và `type`, ngoài ba tọa độ GAV.
- Phân biệt `target/`, **local repository** và **remote repository**.
- Khác biệt tên file giữa release, SNAPSHOT được cài cục bộ và SNAPSHOT phát hành có timestamp.
- Vị trí và chức năng của `maven-metadata.xml`, POM và các file phụ trợ trong repository.
- Thực hành Maven + Java 17 để tạo artifact, cài vào local repository và kiểm tra đúng đường dẫn.
- Các lỗi thường gặp khi đoán đường dẫn, dùng sai repository, đổi version/classifier hoặc tự sao chép file bằng tay.

**Giới hạn phạm vi:** bài dựa trên Maven 3.x, POM 4.0.0 và layout mặc định `maven2`. Vị trí vật lý local repository có thể được tùy chỉnh; một số Maven Resolver mới còn có cách tổ chức cache/installed artifacts riêng. Công thức đường dẫn ở đây mô tả **layout chuẩn**, không phải giấy phép để một chương trình bất kỳ tự thao tác trực tiếp với internals của Maven local cache.

## 2. Tọa độ Maven GAV là gì?

Một artifact Maven thường được định danh bằng:

~~~text
groupId:artifactId:version
~~~

Ba thành phần có vai trò riêng:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `groupId` | `com.example.training` | Nhóm/tổ chức hoặc namespace của project, thường viết dạng tên miền đảo ngược. |
| `artifactId` | `repo-layout-demo` | Tên artifact trong nhóm. |
| `version` | `1.2.3` | Phiên bản artifact, có thể là release hoặc `-SNAPSHOT`. |

Ví dụ:

~~~text
com.example.training:repo-layout-demo:1.2.3
~~~

Tọa độ **không chứa URL máy chủ**. Cùng GAV có thể tồn tại ở một local repository, một repository manager nội bộ hoặc một remote repository khác. Maven dùng cấu hình repositories/mirrors, cache và resolution policy để quyết định **nguồn nào** được truy cập.

Điểm quan trọng: GAV giúp xác định **artifact logic**, còn để chỉ chính xác một file có thể cần thêm:

- **`extension`**: phần mở rộng như `jar`, `pom`, `war`, `zip` hoặc `tar.gz`.
- **`classifier`**: phần định danh phụ như `sources`, `javadoc` hoặc `tests`.
- **`baseVersion`**: đặc biệt quan trọng với SNAPSHOT được phát hành ở dạng timestamp.

Vì vậy cách nói “GAV quyết định toàn bộ filename” chỉ đúng với **trường hợp đơn giản**, chẳng hạn artifact JAR chính của một phiên bản release không có classifier.

## 3. Công thức repository layout mặc định

Maven 3.x dùng repository layout hiện đại, thường gọi là **`maven2`** hoặc **`default`**. Quy tắc cơ bản:

1. Lấy `groupId`, thay mỗi dấu chấm `.` thành dấu gạch chéo `/`.
2. Giữ nguyên `artifactId` làm tên thư mục tiếp theo.
3. Thêm thư mục `baseVersion`. Với bản release, `baseVersion` chính là `version`.
4. Đặt tên file: `artifactId-version.extension`.
5. Nếu có classifier, đặt nó **sau version, trước extension**: `artifactId-version-classifier.extension`.

Công thức khái niệm cho file **không có classifier**:

~~~text
{groupId-with-dots-replaced-by-slashes}/{artifactId}/{baseVersion}/{artifactId}-{version}.{extension}
~~~

Có classifier:

~~~text
{groupId-with-dots-replaced-by-slashes}/{artifactId}/{baseVersion}/{artifactId}-{version}-{classifier}.{extension}
~~~

Ở công thức trên, `baseVersion` và `version` khác nhau chủ yếu đối với SNAPSHOT timestamped. Với release bình thường, chúng có cùng giá trị.

### Ví dụ từng bước

Cho artifact:

~~~text
groupId    = com.example.training
artifactId = repo-layout-demo
version    = 1.2.3
extension  = jar
classifier = (không có)
~~~

Chuyển `groupId`:

~~~text
com.example.training
       ↓ thay dấu "." bằng "/"
com/example/training
~~~

Ghép thư mục:

~~~text
com/example/training/repo-layout-demo/1.2.3/
~~~

Ghép tên tệp chính:

~~~text
repo-layout-demo-1.2.3.jar
~~~

Đường dẫn tương đối cuối cùng:

~~~text
com/example/training/repo-layout-demo/1.2.3/repo-layout-demo-1.2.3.jar
~~~

Đây là **đường dẫn bên trong repository**, không nhất thiết là đường dẫn file tính từ thư mục chứa `pom.xml`. Muốn biết đường dẫn đầy đủ, phải đặt nó dưới **repository root** tương ứng.

### Dấu phân tách

Trong URI của remote repository, Maven layout sử dụng dấu `/`. Trên Windows, khi bạn xem filesystem thông qua Explorer/PowerShell, các cấp thư mục có thể hiển thị bằng `\`. Đó là hai cách thể hiện **cùng cây thư mục**, không phải hai dạng tọa độ khác nhau.

Không thay dấu chấm trong `artifactId` hoặc `version` bằng dấu slash. Quy tắc thay `.` thành `/` chỉ áp dụng cho **`groupId`** trong đường dẫn.

## 4. Ví dụ thực tế: Commons Lang trên Maven Central

Một thư viện phổ biến có tọa độ:

~~~text
org.apache.commons:commons-lang3:3.14.0
~~~

Từng phần ánh xạ:

| Phần | Giá trị | Đường dẫn |
| --- | --- | --- |
| `groupId` | `org.apache.commons` | `org/apache/commons` |
| `artifactId` | `commons-lang3` | `commons-lang3` |
| `version` | `3.14.0` | `3.14.0` |
| Artifact JAR chính | `jar` | `commons-lang3-3.14.0.jar` |
| POM của artifact | `pom` | `commons-lang3-3.14.0.pom` |

Cây giản lược:

~~~text
org/
└── apache/
    └── commons/
        └── commons-lang3/
            ├── maven-metadata.xml
            └── 3.14.0/
                ├── commons-lang3-3.14.0.jar
                └── commons-lang3-3.14.0.pom
~~~

Cây này minh họa **bố cục logic**. Các file checksum, signatures, source/javadoc JAR hoặc metadata khác có thể tồn tại; không nên xem hai file ở thư mục version là toàn bộ mọi file phải có.

URL của JAR chính:

~~~text
https://repo.maven.apache.org/maven2/org/apache/commons/commons-lang3/3.14.0/commons-lang3-3.14.0.jar
~~~

URL POM:

~~~text
https://repo.maven.apache.org/maven2/org/apache/commons/commons-lang3/3.14.0/commons-lang3-3.14.0.pom
~~~

Điểm đáng chú ý: Maven không lấy `commons-lang3` làm **tên nhóm**. Nhóm là `org.apache.commons`, sau đó mới đến thư mục `commons-lang3`. Nếu người học bỏ cấp `commons-lang3` hoặc lặp `org/apache/commons` sai vị trí, đường dẫn sẽ không đúng layout.

## 5. Local repository, remote repository và `target` không phải một

Ba vị trí thường xuất hiện trong một quy trình Maven:

| Vị trí | Chức năng | Ví dụ |
| --- | --- | --- |
| **Build output** | Nơi plugin tạo class, JAR/WAR, report của project hiện tại. | `project/target/repo-layout-demo-1.2.3.jar` |
| **Local repository** | Cache dependency/plugin tải xuống, đồng thời chứa artifact được `mvn install` cài cục bộ. | `~/.m2/repository/com/example/training/repo-layout-demo/1.2.3/...` |
| **Remote repository** | Repository trên máy chủ hoặc repository manager cho việc tải/triển khai artifact. | Maven Central hoặc repository doanh nghiệp. |

### 5.1. `mvn package` không đồng nghĩa `mvn install`

- `mvn package` chạy lifecycle đến phase `package`, thường tạo JAR ở `target/`.
- `mvn install` chạy tiếp đến phase `install`, **đưa artifact và POM vào local repository**. Đây là lúc bạn thường có thể quan sát thư mục GAV của project mới build trong kho cục bộ.
- `mvn deploy` có thể đưa artifact ra **remote repository** được cấu hình; việc deploy cần đích và quyền phù hợp, không phải công việc của một ví dụ học tập nếu chưa có hệ thống thật.

Một file JAR được tạo ở `target/` không tự là một artifact đã được cài trong local repository, dù filename hai nơi giống nhau.

### 5.2. Local repository mặc định và cấu hình riêng

Với Maven 3 thông thường, local repository mặc định ở:

~~~text
~/.m2/repository/
~~~

Đối với Windows, một dạng thường gặp:

~~~text
C:\Users\<user>\.m2\repository\
~~~

Đây là **ví dụ có ký hiệu `<user>` thay cho tên người dùng**, không phải đường dẫn máy của bạn. `settings.xml` có thể đổi `<localRepository>`; lệnh Maven có thể dùng `-Dmaven.repo.local`; một số cách tổ chức local repository còn phụ thuộc implementation/configuration của Maven Resolver.

**Không viết chương trình nghiệp vụ dựa trên việc tự tạo hoặc sửa file trong `~/.m2/repository`.** Apache Maven khuyến nghị dùng Maven/Resolver API vì local repository còn quản lý cache origin, lock, tracking và có thể có cách layout riêng. Việc duyệt file trong bài này chỉ nhằm **quan sát và học quy tắc**, không phải thay thế công cụ quản lý artifact.

### 5.3. Remote repository URL là root để ghép path

Nếu repository root là:

~~~text
https://repo.maven.apache.org/maven2/
~~~

và artifact path là:

~~~text
org/apache/commons/commons-lang3/3.14.0/commons-lang3-3.14.0.jar
~~~

thì URL download là phép ghép hai phần. Tuy nhiên Maven thường dùng cấu hình **`<repositories>`**, `<pluginRepositories>`, `settings.xml` và mirrors để phân giải artifact; URL thực tế nó gọi có thể là repository manager của tổ chức chứ không phải Central trực tiếp.

Với HTTPS, **không có bảo đảm web server hỗ trợ liệt kê thư mục**. Một URL file cụ thể có thể tải được dù URL thư mục mẹ không có trang danh sách. Maven không cần duyệt folder trên trình duyệt mới tải được artifact theo tọa độ.

## 6. Cùng GAV nhưng có thể có nhiều file

Một phiên bản artifact thường có POM và file chính; các artifact bổ sung có **classifier**:

~~~text
com/example/training/repo-layout-demo/1.2.3/
├── repo-layout-demo-1.2.3.pom
├── repo-layout-demo-1.2.3.jar
├── repo-layout-demo-1.2.3-sources.jar
└── repo-layout-demo-1.2.3-javadoc.jar
~~~

Phân biệt:

| Tên file | `extension` | `classifier` | Nội dung/ý nghĩa |
| --- | --- | --- | --- |
| `repo-layout-demo-1.2.3.jar` | `jar` | Không có | Artifact JAR chính. |
| `repo-layout-demo-1.2.3.pom` | `pom` | Không có | POM descriptor liên quan tọa độ đó. |
| `repo-layout-demo-1.2.3-sources.jar` | `jar` | `sources` | Source JAR được attach/publish nếu đã tạo. |
| `repo-layout-demo-1.2.3-javadoc.jar` | `jar` | `javadoc` | Javadoc JAR được attach/publish nếu đã tạo. |
| `repo-layout-demo-1.2.3-tests.jar` | `jar` | `tests` | Test JAR được attach nếu project cấu hình tạo. |

**Các file `-sources.jar`, `-javadoc.jar`, `-tests.jar` không tự xuất hiện chỉ vì bạn chạy `mvn package` trên POM JAR tối thiểu.** Chúng cần plugin/execution hoặc quy trình publishing tương ứng. Không xem thiếu các file phụ là lỗi nếu dự án chưa yêu cầu.

### `classifier` không phải version

Trong tên:

~~~text
repo-layout-demo-1.2.3-sources.jar
~~~

`sources` là **classifier**; thư mục version vẫn là `1.2.3`. Nó không tạo một version `1.2.3-sources`. Tương tự, artifact test JAR có classifier `tests`, nhưng không phải release version mới.

### `type` không phải lúc nào trùng extension

Trong `pom.xml`, dependency có `<type>`, thường mặc định là `jar`. Maven ánh xạ một số type tới extension/classifier thông qua artifact handler. Ví dụ dependency type `test-jar` thường có **extension `jar` và classifier mặc định `tests`**, không có file `.test-jar`.

Mảnh cấu hình minh họa:

~~~xml
<dependency>
    <groupId>com.example.training</groupId>
    <artifactId>repo-layout-demo</artifactId>
    <version>1.2.3</version>
    <classifier>sources</classifier>
    <type>jar</type>
</dependency>
~~~

Maven sẽ tìm file `repo-layout-demo-1.2.3-sources.jar` **nếu artifact đó đã được tạo và xuất bản/cài vào repository**. Việc sử dụng source JAR làm dependency runtime thông thường là không phù hợp; đoạn trên chỉ minh họa mapping tọa độ. Với `test-jar`, Maven có thể dùng cấu hình khác để lấy classifier mặc định.

Đừng tự thay mọi `<type>war</type>` hoặc `<type>pom</type>` thành extension `.jar`. Loại artifact được giải quyết có thể khác, và file đích cần khớp artifact đã được publish.

## 7. Khác biệt đặc biệt của `SNAPSHOT`

Một version kết thúc bằng `-SNAPSHOT`, ví dụ:

~~~text
1.2.4-SNAPSHOT
~~~

là phiên bản dùng trong giai đoạn phát triển. Các lần build/triển khai có thể khác nội dung dù version khai báo trong POM giống nhau.

### 7.1. Thư mục version dùng `baseVersion`

Theo Maven repository layout, snapshot version directory dùng **base version**:

~~~text
com/example/training/repo-layout-demo/1.2.4-SNAPSHOT/
~~~

Phần thư mục này **không đổi thành timestamp** chỉ vì remote repository tạo các bản SNAPSHOT có timestamp.

### 7.2. File của SNAPSHOT trên remote có thể mang timestamp

Ví dụ một repository snapshot có thể chứa:

~~~text
com/
└── example/
    └── training/
        └── repo-layout-demo/
            └── 1.2.4-SNAPSHOT/
                ├── maven-metadata.xml
                ├── repo-layout-demo-1.2.4-20261110.091501-2.jar
                └── repo-layout-demo-1.2.4-20261110.091501-2.pom
~~~

Tên file `1.2.4-20261110.091501-2` ở đây là **ví dụ cấu trúc timestamp + build number**, không khẳng định artifact/URL này tồn tại trên Internet. Maven Resolver dùng metadata snapshot để biết bản timestamp nào tương ứng với `1.2.4-SNAPSHOT`.

Công thức khái niệm:

~~~text
Đường dẫn thư mục: groupPath/artifactId/1.2.4-SNAPSHOT/
Tên file remote: artifactId-1.2.4-YYYYMMDD.HHMMSS-N.jar
~~~

Không phải remote SNAPSHOT nào cũng buộc tạo đúng hai file như cây trên; repository có thể chứa nhiều bản timestamp, classifier hoặc checksums, và chính sách lưu trữ/cleanup thay đổi theo server.

### 7.3. SNAPSHOT được `mvn install` cài ở local

Nếu đổi version project thành `1.2.4-SNAPSHOT` và chạy:

~~~bash
mvn clean install
~~~

artifact **do bạn tự build và install** thường nằm ở đường dẫn local dạng:

~~~text
~/.m2/repository/com/example/training/repo-layout-demo/1.2.4-SNAPSHOT/repo-layout-demo-1.2.4-SNAPSHOT.jar
~~~

Khi Maven **tải snapshot timestamped từ remote**, một local repository có thể cache file tên đầy đủ timestamped, ví dụ `repo-layout-demo-1.2.4-20261110.091501-2.jar`. Vì vậy đừng suy luận “mọi SNAPSHOT local luôn có tên `-SNAPSHOT.jar`” hoặc “mọi file snapshot trên local luôn timestamped”: nguồn file và cách resolver lưu cache có thể khác nhau.

**Cần đặc biệt nhớ:** `baseVersion` dùng cho **thư mục version**; file name có thể dùng **resolved version** khi đó là snapshot timestamped.

### 7.4. SNAPSHOT update policy

Việc Maven kiểm tra có bản SNAPSHOT mới hay không còn phụ thuộc `updatePolicy`, metadata, cache và lựa chọn CLI, ví dụ `-U` yêu cầu Maven kiểm tra cập nhật theo khả năng phù hợp. Nó **không đảm bảo** một repository chưa có bản mới sẽ tạo ra bản mới; không nên coi lệnh `-U` là thao tác deploy.

Ngược lại, **release** như `1.2.3` thường được kỳ vọng bất biến. Đưa hai file có nội dung khác nhau dưới cùng tọa độ release trong các kho khác nhau dễ làm build thiếu tái hiện.

## 8. Metadata: thông tin giúp Maven tìm phiên bản và SNAPSHOT

Repository không chỉ chứa JAR/POM. Maven dùng **repository metadata** để phục vụ các thao tác khám phá và phân giải, thường dưới tên:

~~~text
maven-metadata.xml
~~~

Trong local repository, metadata nhận từ remote có thể được lưu với tên gắn repository ID như:

~~~text
maven-metadata-central.xml
~~~

Và metadata do Maven local install tạo ra có thể mang tên:

~~~text
maven-metadata-local.xml
~~~

Tên file chính xác và việc có tồn tại hay không phụ thuộc loại metadata, nguồn repository, phiên bản Maven và implementation. Không phải mỗi thư mục artifact/version đều bắt buộc có một metadata file.

### Ba cấp metadata

| Cấp | Vị trí tương đối | Chức năng |
| --- | --- | --- |
| **G level** | `groupPath/maven-metadata.xml` | Đặc biệt phục vụ mapping prefix của Maven plugins sang artifactId trong plugin group. |
| **A/GA level** | `groupPath/artifactId/maven-metadata.xml` | Liệt kê/cung cấp thông tin về các version của artifact. |
| **V/GAV level** | `groupPath/artifactId/baseVersion/maven-metadata.xml` | Trên remote snapshot repository: thông tin bản snapshot và mapping tới các file timestamped. |

Ghi nhớ: V-level metadata cho timestamped SNAPSHOT **không phải một file bắt buộc của mọi thư mục release**. G-level metadata **không giống** metadata version bình thường ở cấp artifactId.

### 8.1. Metadata cấp artifactId

Tại đường dẫn:

~~~text
com/example/training/repo-layout-demo/maven-metadata.xml
~~~

remote repository có thể có nội dung dạng **minh họa**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<metadata>
    <groupId>com.example.training</groupId>
    <artifactId>repo-layout-demo</artifactId>
    <versioning>
        <latest>1.2.3</latest>
        <release>1.2.3</release>
        <versions>
            <version>1.2.2</version>
            <version>1.2.3</version>
        </versions>
        <lastUpdated>20261110110000</lastUpdated>
    </versioning>
</metadata>
~~~

Đây **không phải bản trích của một repository thật** và timestamp chỉ là ví dụ. `versions` cho Maven biết những version mà repository công bố; `latest`/`release` có thể xuất hiện theo cách repository duy trì metadata; không dùng chúng như một chiến lược thay thế việc **chốt dependency version** của build tái hiện được.

Chú ý: `maven-metadata.xml` ở cấp artifactId nằm **bên cạnh các thư mục version**, chứ không nhất thiết nằm bên trong `1.2.3`.

### 8.2. Metadata cấp SNAPSHOT version

Trong remote snapshot repository:

~~~text
com/example/training/repo-layout-demo/1.2.4-SNAPSHOT/maven-metadata.xml
~~~

Nó có thể có cấu trúc đại diện:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<metadata>
    <groupId>com.example.training</groupId>
    <artifactId>repo-layout-demo</artifactId>
    <version>1.2.4-SNAPSHOT</version>
    <versioning>
        <snapshot>
            <timestamp>20261110.091501</timestamp>
            <buildNumber>2</buildNumber>
        </snapshot>
        <lastUpdated>20261110091501</lastUpdated>
        <snapshotVersions>
            <snapshotVersion>
                <extension>jar</extension>
                <value>1.2.4-20261110.091501-2</value>
                <updated>20261110091501</updated>
            </snapshotVersion>
            <snapshotVersion>
                <extension>pom</extension>
                <value>1.2.4-20261110.091501-2</value>
                <updated>20261110091501</updated>
            </snapshotVersion>
        </snapshotVersions>
    </versioning>
</metadata>
~~~

Đây cũng là **XML minh họa**, không yêu cầu bạn tạo thủ công. Với artifact có classifier, metadata có thể có `classifier` để phân biệt source/Javadoc/sản phẩm phụ. Resolver dùng cấu trúc này để chọn đúng file phiên bản timestamp.

### 8.3. Metadata không phải POM descriptor

| Tệp | Chức năng chính |
| --- | --- |
| `repo-layout-demo-1.2.3.pom` | Mô tả project và dependency/parent/BOM metadata liên quan artifact đã publish. |
| `maven-metadata.xml` | Metadata cấp kho: danh sách version, mapping snapshot, plugin prefix tùy vị trí. |
| `repo-layout-demo-1.2.3.jar` | Bytecode và resources của sản phẩm JAR chính. |
| `*.sha1`, `*.sha256`, `*.sha512` (nếu có) | Checksums phục vụ xác minh truyền tải/toàn vẹn theo chính sách repository. |
| `*.asc` (nếu có) | Chữ ký detached cho file artifact/metadata theo hệ thống phát hành. |

Đừng mở metadata rồi kết luận nó chứa dependencies của artifact: **POM là nơi chứa model dependency**. Ngược lại, POM một version không phải nguồn đầy đủ của danh sách mọi version hiện có ở remote repository.

## 9. Những file phụ trong local repository

Khi duyệt `~/.m2/repository`, bạn có thể thấy các file không giống mẫu `artifactId-version.jar`:

~~~text
_remote.repositories
*.lastUpdated
resolver-status.properties
maven-metadata-local.xml
maven-metadata-<repo-id>.xml
~~~

Các file này có thể phục vụ:

- Theo dõi artifact được lấy từ repository nào.
- Ghi nhận lần tải/metadata lookup thất bại hoặc trạng thái cập nhật.
- Ghi metadata cục bộ hoặc metadata nhận từ repository khác.
- Hỗ trợ resolver quản lý cache.

Đây là **chi tiết triển khai**, không phải các artifact do người dùng khai báo GAV. Không sửa những file này bằng tay để “ép Maven thấy JAR”, không chép một thư mục từ máy khác rồi kỳ vọng mọi tracking metadata còn chính xác.

Nếu cache có vấn đề, ưu tiên:

1. Xác nhận tọa độ và đường dẫn repository đúng.
2. Xem cấu hình `settings.xml`, mirrors/proxies và repository policies.
3. Thử Maven resolution bằng lệnh tiêu chuẩn.
4. Chỉ thực hiện thao tác cleanup có mục tiêu sau khi hiểu tác động; tránh xóa toàn bộ `~/.m2/repository` trên máy đang dùng cho nhiều dự án.

Trong Maven Resolver mới, local repository còn có thể hỗ trợ **split local repository**. Vì vậy công thức maven2 trên remote là điều cần biết; còn việc truy cập file cache trực tiếp không phải API ổn định để viết công cụ quản trị artifact.

## 10. Ví dụ Java 17 thực hành: tự tạo tọa độ và xem JAR nằm ở đâu

Ta tạo một project độc lập, **không cần dependency ngoài JDK**. Code Java sẽ in GAV và đường dẫn repository đúng công thức release; Maven sẽ tạo artifact và cài nó vào local repository bằng `mvn install`.

Cây thư mục:

~~~text
repo-layout-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── training/
                        └── App.java
~~~

### 10.1. POM hoàn chỉnh

Tạo `repo-layout-demo/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.training</groupId>
    <artifactId>repo-layout-demo</artifactId>
    <version>1.2.3</version>
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
                <artifactId>maven-install-plugin</artifactId>
                <version>3.1.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

POM dùng Java release 17 và khai báo các plugin với version cụ thể để tránh phụ thuộc plugin version mà Maven chọn ngầm định. Chưa có `Main-Class` trong manifest, vì vậy lệnh chạy Java sẽ dùng `-cp` và tên class.

### 10.2. Chương trình Java tính đường dẫn

Tạo `src/main/java/com/example/training/App.java`:

~~~java
package com.example.training;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        String groupId = "com.example.training";
        String artifactId = "repo-layout-demo";
        String version = "1.2.3";
        String extension = "jar";

        String groupPath = groupId.replace('.', '/');
        String fileName = artifactId + "-" + version + "." + extension;
        String relativePath =
                groupPath + "/" + artifactId + "/" + version + "/" + fileName;

        System.out.println("GAV: " + groupId + ":" + artifactId + ":" + version);
        System.out.println("Repository path: " + relativePath);
    }
}
~~~

Đây là Java 17 hợp lệ, không yêu cầu thư viện khác. Nó minh họa **release JAR không classifier**, không cố xây dựng một Maven Resolver đầy đủ: không xử lý timestamped SNAPSHOT, custom type handlers, mirrors, constraints hoặc metadata lookup. `groupId`, `artifactId` và `version` trong code được ghi lại có chủ đích để **trùng POM ví dụ**; Maven không tự chèn GAV vào các biến của chương trình.

### 10.3. Build và chạy

Từ thư mục chứa `pom.xml`:

~~~bash
mvn --version
mvn clean package
java -cp target/repo-layout-demo-1.2.3.jar com.example.training.App
~~~

**Stdout chính xác của lệnh Java cuối:**

~~~text
GAV: com.example.training:repo-layout-demo:1.2.3
Repository path: com/example/training/repo-layout-demo/1.2.3/repo-layout-demo-1.2.3.jar
~~~

Lệnh `mvn clean package` có thể in nhiều dòng log Maven; hai dòng trên **chỉ là stdout của chương trình Java**, không phải toàn bộ output terminal của cả ba lệnh.

Đến đây, file JAR ở:

~~~text
repo-layout-demo/target/repo-layout-demo-1.2.3.jar
~~~

Nếu chưa chạy `mvn install`, **không kết luận** JAR của project chắc chắn đã được cài trong local repository. Đó là bước tiếp theo.

### 10.4. Cài artifact vào local repository

Chạy:

~~~bash
mvn install
~~~

Khi thành công, Maven cài POM và JAR của project vào local repository đang cấu hình. Với **layout local thông thường** và `~/.m2/repository` làm root, file có đường dẫn:

~~~text
~/.m2/repository/
└── com/
    └── example/
        └── training/
            └── repo-layout-demo/
                └── 1.2.3/
                    ├── repo-layout-demo-1.2.3.jar
                    └── repo-layout-demo-1.2.3.pom
~~~

Các file metadata có thể xuất hiện ở thư mục artifactId hoặc các cấp khác; cây chỉ nêu hai tệp chính để đối chiếu công thức.

**Bash (Linux/macOS), kiểm tra sự tồn tại:**

~~~bash
ls "$HOME/.m2/repository/com/example/training/repo-layout-demo/1.2.3/"
~~~

**PowerShell (Windows), kiểm tra sự tồn tại:**

~~~powershell
Get-ChildItem "$env:USERPROFILE\.m2\repository\com\example\training\repo-layout-demo\1.2.3"
~~~

Các lệnh kiểm tra file trên **chỉ đúng nếu local repository dùng vị trí mặc định**. Nếu máy bạn đặt `<localRepository>` hoặc `maven.repo.local` khác, hãy thay phần root bằng giá trị thực.

Để tiếp tục kiểm chứng, chạy Java từ bản JAR trong local repository:

**Bash:**

~~~bash
java -cp "$HOME/.m2/repository/com/example/training/repo-layout-demo/1.2.3/repo-layout-demo-1.2.3.jar" com.example.training.App
~~~

**PowerShell:**

~~~powershell
java -cp "$env:USERPROFILE\.m2\repository\com\example\training\repo-layout-demo\1.2.3\repo-layout-demo-1.2.3.jar" com.example.training.App
~~~

**Stdout chính xác vẫn là:**

~~~text
GAV: com.example.training:repo-layout-demo:1.2.3
Repository path: com/example/training/repo-layout-demo/1.2.3/repo-layout-demo-1.2.3.jar
~~~

Việc chạy trực tiếp từ local repository ở đây **chỉ nhằm thực hành quan sát**. Khi viết ứng dụng thật, hãy triển khai artifact bằng launcher/classpath được kiểm soát, không đặt đường dẫn `~/.m2` làm một yêu cầu production.

### 10.5. Kiểm tra bytecode trong JAR

Chạy:

~~~bash
jar tf target/repo-layout-demo-1.2.3.jar
~~~

Trong danh sách entry, bạn cần thấy:

~~~text
com/example/training/App.class
~~~

Đường dẫn entry **bên trong JAR** hoàn toàn khác với đường dẫn **tới file JAR trong repository**. Đây là hai tầng namespace:

~~~text
Repository path:
com/example/training/repo-layout-demo/1.2.3/repo-layout-demo-1.2.3.jar

JAR internal entry:
com/example/training/App.class
~~~

Đừng nhầm folder package Java của class với đường dẫn GAV của artifact. Hai đường có thể trông giống vì dự án đặt `groupId` theo Java package, nhưng **không có quy tắc bắt buộc chúng phải giống nhau**.

## 11. Quan sát thay đổi khi đổi version hoặc packaging

### 11.1. Đổi version release

Trong project mẫu, nếu đổi:

~~~xml
<version>1.2.4</version>
~~~

rồi chạy `mvn clean install`, artifact mới sẽ thường nằm ở:

~~~text
com/example/training/repo-layout-demo/1.2.4/repo-layout-demo-1.2.4.jar
~~~

**Lưu ý:** chương trình Java ở mục 10 hiện hard-code `1.2.3` để minh họa. Nếu chỉ đổi POM, stdout Java vẫn in `1.2.3`, vì Maven không tự sửa chuỗi trong Java source. Muốn stdout phản ánh version mới, hãy đổi code tương ứng hoặc thiết kế bước sinh build metadata có chủ đích. Điều này giúp tránh một sai lầm phổ biến: nhầm version của artifact với một giá trị tự động có sẵn cho application runtime.

Không phải cứ đổi version rồi build là Maven xóa thư mục version cũ trong local repository. Repository có thể giữ cả hai phiên bản cạnh nhau.

### 11.2. Đổi sang SNAPSHOT

Nếu đặt `<version>1.2.4-SNAPSHOT</version>`, cài cục bộ bằng `mvn install`, file có thể xuất hiện dạng:

~~~text
com/example/training/repo-layout-demo/1.2.4-SNAPSHOT/repo-layout-demo-1.2.4-SNAPSHOT.jar
~~~

Nếu artifact này được deploy thành timestamped SNAPSHOT lên remote repository theo cấu hình phù hợp, tên file remote có thể thay `SNAPSHOT` bằng timestamp/build number. **Không tự động giả định** `mvn install` làm việc triển khai ra remote; cũng không chạy `mvn deploy` trên repository sản xuất trong bài thực hành.

### 11.3. Packaging `pom` khác `jar`

Nếu project là parent/aggregator:

~~~xml
<packaging>pom</packaging>
~~~

thì artifact chính là POM descriptor. Đường dẫn repository vẫn theo GAV, nhưng không cần có một JAR ứng dụng cùng tên.

Tương tự, dự án `war` thường có artifact WAR; đường dẫn có dạng `artifactId-version.war` nếu không có classifier và dùng layout chuẩn. **Phần thư mục GAV giữ nguyên quy luật**, còn loại file phụ thuộc packaging/artifact thực sự xuất bản.

### 11.4. Classifier bổ sung

Nếu một plugin được cấu hình để attach source JAR mang classifier `sources`, file đi cùng release version:

~~~text
com/example/training/repo-layout-demo/1.2.3/repo-layout-demo-1.2.3-sources.jar
~~~

Đây là **một artifact phụ** chia sẻ GAV gốc và thêm classifier; `-sources` không trở thành cấp thư mục mới.

## 12. Tìm thư viện bằng Maven thay vì tự chép file

Khi muốn Maven tải một dependency đã được xuất bản, ưu tiên khai báo nó trong POM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.14.0</version>
    </dependency>
</dependencies>
~~~

Maven sẽ dùng resolution rules, repositories/mirrors, cache và tọa độ artifact để tìm file. Không cần tự tạo folder `org/apache/commons` rồi copy JAR vào.

Một công cụ học tập là Maven Dependency Plugin. Khi có POM hợp lệ và repository truy cập được:

~~~bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.7.1:get -Dartifact=org.apache.commons:commons-lang3:3.14.0
~~~

Lệnh dùng goal `dependency:get` để phân giải artifact theo tọa độ. Không nên suy luận Maven sẽ chỉ tải **một file duy nhất**: nó có thể tải POM, dependencies và plugin cần thiết tùy tham số/cấu hình. Sau đó, trong local repository thông thường bạn có thể quan sát cây `org/apache/commons/commons-lang3/3.14.0/`.

**Lưu ý khi chạy goal plugin trực tiếp:** plugin Maven cũng là artifact trong repository, vì thế trước tiên nó có thể phải được tải về. Một lỗi download plugin không đồng nghĩa GAV của thư viện ứng dụng sai.

### Kho local do bạn kiểm soát là một trường hợp khác

Nếu cần cài **JAR của bên thứ ba** chưa được xuất bản ở repository nào, Maven Install Plugin có goal `install:install-file` để cài có tọa độ đúng vào local repository. Đừng tự chép file JAR vào `~/.m2/repository` thay cho Maven; phương pháp copy có thể bỏ qua POM descriptor, metadata và tracking cần thiết. Việc cài file không đáng tin cậy từ nguồn không rõ ràng cũng có rủi ro bảo mật.

## 13. Repository metadata và tính tái hiện của build

Đường dẫn GAV giúp định vị **một tọa độ**, nhưng chưa đủ để chứng minh byte artifact an toàn và giống nhau ở mọi repository.

Ví dụ, hai repository A và B đều có:

~~~text
com/example/training/repo-layout-demo/1.2.3/repo-layout-demo-1.2.3.jar
~~~

Chúng **nên** chứa cùng nội dung nếu là cùng một bản release đã xuất bản. Tuy vậy, layout không phải một cơ chế mã hóa/hash hay chữ ký. Hai file có thể khác byte trong các repository không được quản trị tốt, dù có cùng GAV. Điều đó có thể làm build không tái hiện được.

Để quản lý tốt:

- Không thay thế artifact release đã publish dưới cùng version.
- Dùng repository manager, quyền upload và chính sách version rõ ràng.
- Xác minh checksum/signature theo công cụ và chính sách được hỗ trợ.
- Ghi nhận nguồn repository, dependency version và BOM/parent version của build.
- Đặc biệt cẩn thận với `-SNAPSHOT` vì bản SNAPSHOT có thể thay đổi theo thời gian.
- Tránh dùng một URL bản phát hành giả định nếu repository chưa thực sự có artifact.

Repository layout quy định **nơi Maven sẽ tìm**, không chứng minh artifact đó đã được xuất bản, có quyền đọc hoặc không bị thay đổi.

## 14. Những lỗi dễ gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Maven báo artifact not found dù đã đoán đúng tên JAR | Repository được cấu hình không chứa artifact, mirror/proxy sai, version/classifier/type chưa đúng. | Kiểm tra tọa độ đầy đủ, remote repository, logs và policy. |
| Không thấy `target/*.jar` trong local repository sau `mvn package` | `package` chỉ tạo build output, chưa `install`. | Dùng `mvn install` khi cần cài cục bộ. |
| Đổi version nhưng tìm ở folder version cũ | Maven tạo thư mục mới cho version mới. | Kiểm tra GAV trong effective POM và đường dẫn version tương ứng. |
| Đổi `groupId` mà Maven không tìm được file theo path cũ | Dấu chấm của groupId được ánh xạ thành nhiều cấp thư mục. | Tính lại `groupPath`, không tái sử dụng path cũ. |
| Nhầm `artifactId` với package Java | Java package và Maven GAV là hai namespace khác nhau. | Đọc thẻ POM thay vì dựa vào đường dẫn `src/main/java`. |
| Tìm `-sources.jar` nhưng không thấy | Artifact sources chưa được tạo/attach/publish. | Kiểm tra source plugin và quy trình publishing. |
| Tìm file `.test-jar` | Maven dependency type `test-jar` thường tương ứng file `.jar` và classifier `tests`. | Kiểm tra mapping type/classifier thực tế. |
| Tìm SNAPSHOT remote theo `artifactId-version-SNAPSHOT.jar` nhưng không thấy | Repository có file timestamped; metadata chỉ phiên bản hiệu lực. | Đọc version-level `maven-metadata.xml`; để Maven Resolver tự chọn. |
| Nhầm metadata cấp artifact và cấp snapshot | File cùng tên nhưng nằm ở các cấp khác nhau. | Xác định `GA` hay `GAV/baseVersion` trước khi đọc. |
| Chỉ có `maven-metadata.xml` mà không thấy JAR | Metadata có thể liệt kê version, không chứng minh file hiện tại tải được. | Kiểm tra đúng tọa độ, extension, classifier và remote policy. |
| `.lastUpdated` xuất hiện | Cache/resolver có thông tin lần lookup/download, có thể là lỗi trước đó. | Xem logs và cấu hình repo; không sửa cache files thủ công. |
| HTTP 401/403 | Thiếu credential/quyền truy cập repository. | Cấu hình server ID/credential trong settings theo hướng dẫn quản trị. |
| HTTP 404 | Sai GAV, version không tồn tại, repository không chứa hoặc path/classifier khác. | Kiểm tra repository root, GAV và metadata. |
| Java `ClassNotFoundException` dù JAR nằm trong repository | JVM launcher không tự đọc Maven local repository. | Tạo runtime classpath hoặc dùng launcher/packaging tương ứng. |
| Cùng GAV nhưng nội dung khác giữa máy | Artifact đã bị thay, SNAPSHOT thay đổi hoặc repo/mirror khác nguồn. | Kiểm tra nguồn, checksums, cache và release policy. |
| Build offline thất bại | Artifact hoặc plugin/POM cần thiết chưa ở cache phù hợp. | Build trực tuyến có kiểm soát trước; `-o` không tự bổ sung file thiếu. |

### Đừng đánh đồng lỗi 404 và việc “Maven thiếu dấu slash”

Khi Maven báo không tìm thấy artifact, việc tính đường dẫn layout là một bước chẩn đoán tốt, nhưng còn nhiều nguyên nhân: repository bị chặn, mirror đang dùng URL khác, credentials thiếu, version policy release/snapshot không cho phép, metadata cũ, hoặc chưa publish. Không nên bắt đầu bằng cách tạo thư mục thủ công trong local repository.

## 15. Quy trình chẩn đoán một tọa độ không tải được

Khi gặp lỗi resolution, làm theo thứ tự:

1. **Đọc đúng GAV** từ dependency/plugin/POM, bao gồm `type`, `classifier`, scope nếu có.
2. **Kiểm tra phiên bản hiệu lực**: parent, `dependencyManagement`, profiles và BOM có thể quyết định version cuối.
3. **Tính đường dẫn tương đối** theo công thức maven2, lưu ý SNAPSHOT baseVersion.
4. **Kiểm tra repository logic**: `repositories` và `pluginRepositories` có thể khác nhau; Maven plugin không nhất thiết dùng cùng nhóm repository như dependency.
5. **Kiểm tra mirror và settings**: Maven có thể đang truy cập repository manager riêng thay vì URL Central.
6. **Đọc log resolution**: Maven báo URL, trạng thái xác thực, transfer hoặc metadata lookup ra sao?
7. **Kiểm tra local repository theo cấu hình hiện tại**; việc có file không bảo đảm resolver coi nó dùng được nếu có tracking/metadata riêng.
8. **Xác minh artifact thực sự đã publish** và version/classifier/extension có tồn tại ở nguồn.
9. **Kiểm tra mạng, proxy, credential và chính sách snapshot/release** khi cần.
10. **Chạy lại resolution sau khi sửa đúng nguyên nhân**, không ghi đè file cache và không dùng lệnh upload production trong bài thực hành.

Các lệnh hữu ích:

~~~bash
mvn --version
mvn help:effective-pom -Doutput=effective-pom.xml
mvn dependency:tree
mvn -X dependency:tree
~~~

`-X` sinh log debug có thể chứa đường dẫn nội bộ, địa chỉ repository và cấu hình nhạy cảm. Chỉ chia sẻ những đoạn đã kiểm duyệt. `help:effective-pom`/`dependency:tree` có thể phải tải Help/Dependency Plugin nếu máy chưa cache chúng, nên lỗi khi gọi các goal này cũng có thể do chính repository/network setup.

## 16. Bài tập thực hành và đáp án kiểm chứng

### Bài A — Tính đường dẫn thủ công

Với các tọa độ sau, tự viết **đường dẫn tương đối tới file chính**:

| GAV và loại file | Đường dẫn kỳ vọng |
| --- | --- |
| `com.acme:billing-core:2.0.1`, JAR | `com/acme/billing-core/2.0.1/billing-core-2.0.1.jar` |
| `org.example.tools:build-utils:4.7`, POM | `org/example/tools/build-utils/4.7/build-utils-4.7.pom` |
| `com.acme:billing-core:2.0.1`, sources JAR | `com/acme/billing-core/2.0.1/billing-core-2.0.1-sources.jar` |
| `com.acme:billing-core:2.0.1`, WAR | `com/acme/billing-core/2.0.1/billing-core-2.0.1.war` |

Đây là **bài toán ánh xạ tọa độ**, không khẳng định các GAV minh họa đã tồn tại hoặc cung cấp đồng thời cả WAR/JAR.

### Bài B — Build, install và so hai nơi

1. Tạo project Java 17 `repo-layout-demo` như mục 10.
2. Chạy `mvn clean package`; kiểm tra JAR dưới `target`.
3. Chạy `java -cp target/repo-layout-demo-1.2.3.jar com.example.training.App` và đối chiếu **đúng hai dòng stdout**.
4. Chạy `mvn install`; kiểm tra file JAR/POM của project dưới local repository đang dùng.
5. So đường dẫn trong `target` với đường dẫn `com/example/training/repo-layout-demo/1.2.3/...`.
6. Giải thích vì sao folder `com/example/training` được tạo từ groupId, nhưng entry bên trong JAR vẫn do package Java quyết định.
7. Dùng `jar tf` xem `App.class` bên trong JAR; phân biệt path nội bộ JAR và path GAV.
8. Đổi version trong POM sang `1.2.4` trên **bản thực hành**, chạy lại build/install và ghi nhận folder version mới. Giải thích tại sao code Java vẫn in `1.2.3` nếu chưa đổi chuỗi hard-code trong class.

### Bài C — Hiểu metadata và SNAPSHOT

1. Với `1.2.4-SNAPSHOT`, viết đúng **thư mục baseVersion**.
2. Giải thích vì sao file timestamped có thể nằm trong thư mục `1.2.4-SNAPSHOT`.
3. Phân biệt `maven-metadata.xml` ở cấp artifactId và cấp snapshot version.
4. Giải thích vì sao không nên sửa `maven-metadata-local.xml` hay `_remote.repositories` bằng tay.
5. Nêu điều kiện để artifact `-sources.jar` tồn tại, và vì sao không phải mọi artifact có JAR nguồn.

### Câu hỏi tự đánh giá

- Chỉ `groupId` hay cả `artifactId` được thay dấu chấm thành slash?
- `version` của release và `baseVersion` có khác nhau không?
- Một JAR vừa build dưới `target` có tự xuất hiện trong local repository sau `mvn package` không?
- `mvn install` cài artifact vào đâu? `mvn deploy` làm gì khác?
- `sources` là classifier hay một version?
- `type=test-jar` có nghĩa file extension là `.test-jar` không?
- Vì sao bạn có thể thấy `maven-metadata.xml` ngoài thư mục version?
- Khi local cache có thư viện, JVM có tự thêm thư viện đó vào classpath không?
- Vì sao same GAV không chứng minh hai repository chắc chắn chứa file byte-identical?

## 17. Tổng kết

**Quy tắc cốt lõi của Maven repository layout là:**

~~~text
groupId có dấu chấm → thư mục phân cấp
artifactId → thư mục artifact
baseVersion → thư mục phiên bản
artifactId-version[-classifier].extension → tệp artifact
~~~

Với release JAR không classifier, phép ghép là trực tiếp. Với snapshot timestamped, **thư mục vẫn giữ `-SNAPSHOT`**, còn filename có thể mang timestamp/build number được điều khiển bởi metadata. Những file như `.pom`, `-sources.jar`, `maven-metadata.xml` và checksums có **vai trò khác nhau** trong cùng một cây repository.

**Hãy phân biệt ba vị trí:** `target/` là sản phẩm build của project; local repository là cache cộng với nơi cài artifact bằng `mvn install`; remote repository là nguồn/phía nhận artifact qua mạng. Khi cần lấy một thư viện, hãy để **Maven Resolver và repository manager** làm công việc phân giải thay vì tự chép file vào kho.

## Tài liệu chính thức

- Apache Maven — Repository Layout: https://maven.apache.org/repositories/layout.html
- Apache Maven — Maven Artifacts: https://maven.apache.org/repositories/artifacts.html
- Apache Maven — Maven Metadata: https://maven.apache.org/repositories/metadata.html
- Apache Maven — Maven Local Repositories: https://maven.apache.org/repositories/local.html
- Apache Maven — Configuring Maven / Local Repository: https://maven.apache.org/guides/mini/guide-configuring-maven.html
- Maven Dependency Plugin — Get: https://maven.apache.org/plugins/maven-dependency-plugin/get-mojo.html
- Maven Install Plugin — Usage: https://maven.apache.org/plugins/maven-install-plugin/usage.html
