# Làm mới có mục tiêu thay vì xóa toàn bộ kho .m2 trong Maven

## 1. Vấn đề thực tế: tại sao Maven có thể dùng dữ liệu cũ?

Khi build dự án Java, Apache Maven phân giải POM, parent POM, BOM, dependencies và plugins qua các repository. Để tránh tải đi tải lại, Maven lưu những artifact đã tải xuống và artifact được build/cài cục bộ trong **local repository** (kho cục bộ).

Mặc định trên Maven 3, local repository thường là:

```text
${user.home}/.m2/repository
```

Trong đó `${user.home}` là Java system property của tài khoản thực sự đang chạy Maven. Ví dụ Linux có thể là `/home/developer/.m2/repository`; Windows có thể là `C:\Users\Developer\.m2\repository`. Đây chỉ là giá trị mặc định: `settings.xml` hoặc tham số `-Dmaven.repo.local` có thể thay đổi kho thực tế.

Một số triệu chứng khiến lập trình viên nghi ngờ cache:

- Maven báo **“was cached in the local repository, resolution will not be reattempted until the update interval ...”** sau một lần tải thất bại.
- Một dependency `-SNAPSHOT` đã được deploy phiên bản mới, nhưng build vẫn dùng bản được tải trước.
- Artifact cụ thể bị hỏng hoặc bị tải thiếu trong kho cục bộ.
- Đổi proxy/mirror/repository server rồi Maven vẫn báo không tìm thấy một POM/plugin.
- Project có parent/BOM mới nhưng local repo đang chứa dữ liệu tương ứng với một lần thử trước.
- Một nhóm module build được ở máy khác, riêng máy này lỗi resolve dependency.

Phản ứng phổ biến nhưng rất tốn kém là **xóa toàn bộ `~/.m2` hoặc `~/.m2/repository`**. Bài này hướng dẫn tìm **đối tượng lỗi thật** rồi chọn phạm vi làm mới nhỏ nhất, thay vì xóa tất cả.

**Nguyên tắc:** trước tiên hãy xác định bạn đang sửa lỗi **metadata/update policy, artifact trong cache, version/dependency graph, quyền repository hay mạng**. Không có một lệnh purge nào chữa được tất cả các nguyên nhân.

## 2. Phân biệt ba nhóm dữ liệu trước khi xóa

### 2.1. `~/.m2` không chỉ chứa artifact

Trong home của người chạy Maven, cấu trúc thường gặp:

```text
~/.m2/
├── settings.xml                 # tùy chọn: mirrors, proxies, servers, profiles
├── settings-security.xml        # tùy chọn: cấu hình mã hóa credentials ở Maven 3
├── toolchains.xml               # tùy chọn: toolchains theo người dùng
├── wrapper/                     # có thể có cache do Maven Wrapper quản lý
└── repository/                  # local repository artifact/metadata
```

Các file ngoài `repository/` có thể chứa cấu hình repository, mirror, proxy, server và **thông tin xác thực**. Xóa `~/.m2` nguyên thư mục có nguy cơ mất cấu hình và làm hỏng pipeline hoặc môi trường phát triển, ngoài việc bắt Maven tải lại artifact.

**Không nhầm:** `mvn clean` thông thường xóa **output của project** (như `target/`), không xóa local repository và không phải thao tác “làm mới dependency cache”.

### 2.2. Local repository có hai vai trò

Apache Maven mô tả local repository vừa:

1. **Cache artifact tải về** từ remote repository (dependency, plugin, POM, metadata);
2. **Lưu artifact được `mvn install` cài cục bộ** từ những project trên máy.

Ví dụ một bản `com.example:internal-helper:1.0-SNAPSHOT` chỉ từng được `install` ở máy lập trình viên có thể **không tồn tại** trên Maven Central hoặc server nội bộ. Xóa toàn bộ cache sẽ xóa luôn artifact này; muốn dùng lại phải build và install lại từ source.

Maven Resolver còn hỗ trợ metadata, locking, và ở một số cấu hình là **split local repository**. Vì vậy không nên lập script xóa trực tiếp các file trong kho theo đường dẫn suy đoán: cấu trúc nội bộ có thể thay đổi và thao tác thủ công có thể bỏ qua các cơ chế đồng bộ hóa của Resolver.

### 2.3. Local metadata không giống artifact JAR

Một artifact Maven thường được định danh bằng tọa độ `groupId:artifactId:version` và các biến thể `type/classifier`. Trong layout cổ điển, cùng artifact có thể có:
- `.jar`: binary;
- `.pom`: mô tả dependency/parent;
- `maven-metadata*.xml`: metadata về version/SNAPSHOT;
- `*.lastUpdated`: dấu vết của lần kiểm tra/tải chưa thành công ở một số phiên bản Resolver;
- `_remote.repositories`: metadata về nguồn repository của artifact trong một số triển khai;
- checksum/metadata phụ khác.

**Không tự tạo/sửa/xóa riêng `.lastUpdated` hoặc `_remote.repositories` như một “bản sửa chuẩn” có hiệu lực trên mọi Maven.** Chúng là chi tiết implementation. Ưu tiên lựa chọn có hỗ trợ chính thức như `-U`, chỉnh đúng remote repository và `dependency:purge-local-repository`.

## 3. Quy tắc chọn biện pháp: từ nhẹ nhất tới mạnh hơn

| Triệu chứng/mục tiêu | Biện pháp đầu tiên | Khi nào mới mạnh tay hơn? |
| --- | --- | --- |
| SNAPSHOT mới chưa được nhìn thấy | `mvn -U ...` | Nếu vẫn lỗi, kiểm tra server/metadata; purge có chọn lọc |
| Lỗi tải thiếu release đã được cache | `mvn -U ...` | Nếu còn lỗi, purge đúng artifact và kiểm tra mirror |
| Một dependency cụ thể có JAR/POM hỏng | `dependency:purge-local-repository` + `-Dinclude=groupId:artifactId` | Mở rộng sang dependency liên quan nếu bằng chứng chỉ ra |
| Một parent POM, BOM hoặc plugin cần refresh | `-DmanualInclude=groupId:artifactId` khi phù hợp | Resolve/build lại sau purge; chú ý phạm vi xóa |
| Mọi dependency của **một project** cần kiểm tra lại | Purge project tree có giới hạn hoặc cache thử biệt lập | Không xóa cache của project khác |
| Nghi ngờ cache cũ của toàn môi trường | Build thử với `-Dmaven.repo.local` trỏ vào kho mới, trống | Chỉ dọn cache cũ sau khi xác minh và có phương án sao lưu |
| Lỗi DNS/TLS/HTTP 401/403/proxy hoặc mirror sai | Sửa repository/settings/quyền trước | Purge không chữa được lỗi server hoặc mạng |
| Muốn chọn version dependency khác | Sửa version/POM/BOM/`dependencyManagement` | Xóa cache không tự đổi tọa độ dependency |

**Không nên bắt đầu bằng `rm -rf ~/.m2` hay `Remove-Item -Recurse ~/.m2`.** Bài này không coi các lệnh đó là thao tác phục hồi tiêu chuẩn.

## 4. Bước 0: xác định Maven đang dùng local repository nào

Trước khi thay đổi dữ liệu, kiểm tra chính xác tiến trình Maven và configuration.

```bash
mvn -version
```

Nếu dùng Maven Wrapper:

```bash
./mvnw -version
```

Lưu ý `Maven home`, `Java home` và phiên bản Maven. IDE, terminal, CI và container có thể chạy Maven dưới **tài khoản hoặc bản cài khác nhau**, dẫn đến local repository khác nhau.

### 4.1. Kiểm tra effective settings

```bash
mvn help:effective-settings -Doutput=effective-settings.xml
```

Tìm phần tử `<localRepository>` trong `effective-settings.xml` và kiểm tra các mục repository/mirror/proxy liên quan. **Không công khai file này** trước khi kiểm tra và loại bỏ thông tin nhạy cảm.

Nếu command build dùng `-Dmaven.repo.local=/some/path`, đường dẫn được override qua user property có thể khác thông tin trong effective settings; cần đối chiếu **lệnh thực tế** và, khi cần, log debug.

### 4.2. Debug đường dẫn kho và repository được truy vấn

```bash
mvn -X -B -ntp validate
```

Trong log debug của Maven 3, tìm đường dẫn local repository và các remote repositories/mirrors mà Maven thực sự xét. Không mặc định `~/.m2/repository` nếu debug cho thấy Maven dùng một kho khác.

**Bảo mật:** `-X` có thể in nhiều chi tiết cấu hình và kết nối do plugin/môi trường sinh ra. Chỉ dùng ở môi trường chẩn đoán phù hợp, lưu log có kiểm soát và không gửi nguyên văn ra kênh công khai.

## 5. Cách nhẹ nhất: -U yêu cầu kiểm tra lại theo chính sách Maven

Cú pháp Maven 3:

```bash
mvn -U -B -ntp clean verify
```

`-U`, tên dài `--update-snapshots`, có tác dụng yêu cầu **kiểm tra các release trước đó không tìm thấy và các SNAPSHOT được cập nhật trên remote repository**.

Đây thường là cách nên thử trước khi xóa một artifact vì:
- không xóa toàn bộ kho;
- Maven vẫn dùng cơ chế Resolver và repository policy;
- nếu vấn đề chỉ là cache kết quả “chưa tìm thấy” hoặc metadata SNAPSHOT cần cập nhật, một lần kiểm tra mới có thể đủ.

**Giới hạn quan trọng:**

1. `-U` **không có nghĩa bắt buộc tải lại mọi release JAR đã tồn tại và hợp lệ** trong cache. Release version được kỳ vọng là bất biến trong repository chuẩn.
2. `-U` **không tự nâng phiên bản** từ `1.0.0` lên `2.0.0` nếu POM khóa version `1.0.0`.
3. `-U` không cấp lại quyền truy cập cho server, không sửa proxy/TLS và không tạo một artifact chưa từng được publish.
4. `-U` không bảo đảm code sẽ compile/test thành công; cần phân biệt lỗi resolve với lỗi source/test.
5. Nếu đang ở `--offline`/`-o`, Maven không thể liên hệ remote để tải những artifact còn thiếu.

### 5.1. Ví dụ lỗi tải thiếu release

Giả sử lần build trước Maven báo:

```text
Could not find artifact com.example:shared-api:jar:1.0.0 in ...
...
was cached in the local repository, resolution will not be reattempted ...
```

Đoạn trên chỉ là **mô tả dạng thông báo**, không phải output đầy đủ của một build cụ thể. Nếu artifact sau đó được publish đúng tọa độ lên server, thử:

```bash
mvn -U -B -ntp verify
```

Nếu vẫn thiếu, kiểm tra version, repository ID/URL, mirror trong `settings.xml`, credentials và trạng thái publish trên server. Đừng lặp lại purge liên tục khi URL hoặc quyền truy cập vẫn sai.

### 5.2. SNAPSHOT thay đổi có nghĩa gì?

Với version `1.0-SNAPSHOT`, Maven có thể sử dụng metadata để biết bản timestamp nào mới hơn và khi nào cần kiểm tra remote. `-U` phù hợp khi bạn **cần kiểm tra lại ngay** thay vì đợi kỳ update hiện tại.

Với **release** `1.0.0`, không nên thay nội dung file trên repository mà vẫn giữ cùng tọa độ. Nếu server đã vô tình bị sửa release, giải pháp bền vững là sửa chính sách phát hành/đổi version, không xây workflow phụ thuộc vào việc xóa cache trên mọi máy.

## 6. updatePolicy: vì sao Maven không kiểm tra remote mỗi lần?

Maven có chính sách kiểm tra cập nhật riêng cho `releases` và `snapshots` của repository. Các giá trị được hỗ trợ gồm:

| Giá trị | Ý nghĩa |
| --- | --- |
| `always` | Kiểm tra cập nhật mỗi khi chính sách yêu cầu |
| `daily` | Kiểm tra theo ngày; là mặc định thông dụng |
| `interval:60` | Kiểm tra lại theo khoảng thời gian tối thiểu 60 phút |
| `never` | Không chủ động kiểm tra cập nhật khi artifact đã có trong cache |

Một đoạn cấu hình repository trong POM có thể là:

```xml
<repositories>
    <repository>
        <id>company-snapshots</id>
        <url>https://repo.example.org/maven-snapshots</url>
        <releases>
            <enabled>false</enabled>
        </releases>
        <snapshots>
            <enabled>true</enabled>
            <updatePolicy>daily</updatePolicy>
        </snapshots>
    </repository>
</repositories>
```

**Đây chỉ là đoạn XML để hiểu chính sách**, không phải một repository có thật để sử dụng; URL `repo.example.org` là địa chỉ minh họa, cần thay bằng repository được tổ chức cấp nếu dùng trong dự án thực.

Nếu repository manager đã publish SNAPSHOT mới, `-U` yêu cầu Maven kiểm tra lại. Việc thay `updatePolicy` thành `always` cho mọi project **không phải bước mặc định nên làm**: có thể tăng lượng truy vấn mạng, làm chậm build, và không sửa được lỗi artifact không tồn tại.

**Maven metadata** (như `maven-metadata.xml`) giúp xác định các version và bản SNAPSHOT. Trong các tình huống hỏng metadata, ưu tiên xem log lỗi thực tế, kiểm tra remote policy và chọn purge trong phạm vi nhỏ khi thật cần.

## 7. Công cụ chính: dependency:purge-local-repository

Apache Maven Dependency Plugin cung cấp goal **`dependency:purge-local-repository`**, cho phép xóa **dependency artifact trong local repository** theo một phạm vi đã chọn, rồi tùy chọn tải/phân giải lại.

Thay vì xóa toàn bộ `~/.m2/repository`, sử dụng **goal plugin được tài liệu Maven hỗ trợ**. Dưới đây dùng phiên bản Maven Dependency Plugin `3.11.0` để giữ cú pháp tham số nhất quán:

```bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:purge-local-repository
```

**Cảnh báo:** nếu không đặt bộ lọc, goal trên có thể **purge toàn bộ dependency tree của project hiện tại**, bao gồm transitive dependencies, rồi tải lại. Nó *không* phải lệnh “chỉ xóa một file lỗi”. Đừng chạy không lọc khi mục tiêu chỉ là làm mới một artifact.

Goal này có những tham số quan trọng:

| Tham số | Mặc định / mục đích | Tác động cần lưu ý |
| --- | --- | --- |
| `-Dinclude=groupId:artifactId` | Chỉ lấy các artifact matching trong dependency tree project | Giúp tập trung purge vào một GA |
| `-Dexclude=groupId:artifactId` | Loại một hoặc nhiều GA khỏi phạm vi purge | Hữu ích khi cần giữ một dependency |
| `-DactTransitively=true/false` | Mặc định `true` | `false` hạn chế vào direct dependencies, thay vì cả transitive tree |
| `-DreResolve=true/false` | Mặc định `true` | `true` cố gắng tải/phân giải lại sau khi xóa |
| `-DresolutionFuzziness=...` | Mặc định `version` ở plugin 3.11.0 | Kiểm soát độ rộng xóa theo file/version/artifactId/groupId |
| `-DmanualInclude=groupId:artifactId` | Chọn thủ công GA không nhất thiết thuộc tree | Chỉ purge mục manual; không purge tree thường |
| `-DsnapshotsOnly=true` | Mặc định `false` | Giới hạn vào snapshot artifacts |
| `-Dverbose=true` | In thêm chi tiết | Hỗ trợ quan sát thao tác |

**Không dùng `include` và `manualInclude` như hai cách lọc cộng dồn trong cùng một command.** Theo tài liệu plugin, bật `manualInclude` sẽ chuyển sang chế độ purge thủ công và không nên kết hợp cùng `include/exclude`.

**Trước khi purge:** kiểm tra đầy đủ tọa độ dependency, xác định bản cài cục bộ có thể khôi phục từ remote/source hay không, và đảm bảo không có một Maven process khác đang dựa vào chính artifact đó khi thao tác.

## 8. Làm mới đúng một dependency trong project

Giả sử project có dependency `org.apache.commons:commons-lang3`. Trước tiên, xác minh nó đang được giải quyết dưới phiên bản nào:

```bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dincludes=org.apache.commons:commons-lang3
```

Sau khi xác định dependency đang có trong tree và cần refresh, dùng:

```bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:purge-local-repository -Dinclude=org.apache.commons:commons-lang3 -DactTransitively=false -DresolutionFuzziness=version -DreResolve=true
```

Giải thích:
- `include` chỉ giới hạn vào GA `org.apache.commons:commons-lang3` trong dependency tree của project;
- `actTransitively=false` tránh quét toàn bộ transitive tree cho thao tác được chủ đích vào direct dependency;
- `resolutionFuzziness=version` làm mức purge theo version của artifact thay vì xóa mọi version thuộc cùng artifactId;
- `reResolve=true` yêu cầu plugin phân giải lại artifact sau khi purge.

**Điều kiện:** ví dụ lệnh trên giả định `commons-lang3` là dependency **được khai báo trực tiếp** của project. Nếu nó chỉ xuất hiện bắc cầu, `actTransitively=false` có thể khiến nó không thuộc tập được xét. Khi đó, xem dependency tree rồi dùng lựa chọn thích hợp: bỏ giới hạn `actTransitively=false` trong phạm vi được kiểm soát, hoặc dùng manual purge ở mục 9.

Sau khi goal báo thành công, kiểm tra lại:

```bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dincludes=org.apache.commons:commons-lang3
mvn -B -ntp verify
```

**Không tự kết luận rằng mọi bản version của `commons-lang3` đã bị xóa.** Với `resolutionFuzziness=version`, mục tiêu là version(s) khớp trong tập artifact đã chọn; log của plugin và cache metadata sẽ quyết định chi tiết thực tế theo cách plugin giải quyết.

### 8.1. Tại sao dùng full goal coordinate?

Cú pháp `mvn dependency:purge-local-repository` có thể dùng được khi Maven phân giải plugin prefix `dependency`. Tuy nhiên, khi đang chẩn đoán lỗi plugin/cache, dùng tọa độ đầy đủ với version ghim sẵn:
- giúp kiểm soát phiên bản plugin và tên goal;
- giúp đối chiếu tài liệu tham số đúng version;
- giảm nhầm lẫn khi repository có cấu hình quản lý plugin khác.

**Nhưng** nếu plugin version được ghim chưa hề có trong cache và mạng đang lỗi, Maven vẫn cần tải plugin trước khi purge. Khi đó phải sửa kết nối/repository hoặc dùng plugin đã có, không thể kỳ vọng purge chạy khi chính nó chưa resolve được.

## 9. Làm mới parent POM, BOM hoặc plugin bằng manualInclude

Một số artifact gây lỗi **không nằm trong dependency tree thông thường của project**:
- parent POM;
- BOM `<type>pom</type>` với `scope=import`;
- Maven plugin;
- artifact dùng trong plugin classpath khác với dependency của source code.

Maven Dependency Plugin hỗ trợ **manual purge**:

```bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:purge-local-repository -DmanualInclude=com.example:company-parent -DreResolve=false
```

Đây là **lệnh minh họa**, chỉ dùng khi biết chính xác GA `com.example:company-parent` tồn tại trong local repo và thật sự cần purge. Nó không ép Maven tải lại ngay, vì `reResolve=false`.

Tài liệu Maven giải thích rằng `manualInclude`:
1. chuyển sang việc **purge chỉ các artifact được chọn thủ công**;
2. **không purge dependency tree thông thường** của project;
3. không nên kết hợp với `include`/`exclude`;
4. các artifact bị purge thủ công **thường không tự được re-resolve cho đến khi chúng thật sự cần trong một build sau**.

**Cẩn trọng:** manualInclude nhận tọa độ `groupId:artifactId`, không phải bộ `groupId:artifactId:version` dùng để cam kết một file release duy nhất. Nếu local repo có nhiều version của cùng GA hoặc artifact nội bộ, phải kiểm tra phạm vi thực tế và cân nhắc sao lưu/đảm bảo khả năng phục hồi trước khi purge.

Để tác động ít hơn, người học nên bắt đầu từ phiên build với `-U` và xác minh repository; manual purge chỉ dùng khi có bằng chứng file POM/plugin cụ thể trong cache bị vấn đề.

### Vì sao `reResolve=false` thường hợp lý với manual purge?

Với một parent POM hoặc plugin, việc purge trực tiếp có thể làm mất file cần thiết cho **chính tiến trình build hiện tại**; yêu cầu re-resolution ngay không phải lúc nào tương ứng với nhu cầu thực. Cách an toàn là:
1. xác nhận artifact có thể lấy lại từ remote hoặc source build;
2. purge artifact đã chọn và **dừng goal purge**;
3. chạy lại lệnh Maven cần parent/BOM/plugin với mạng và cấu hình hợp lệ;
4. đọc log resolve và verify build kết quả.

Không đưa goal purge tùy tiện vào mọi phase của lifecycle: việc xóa dependency ở giữa một build có thể ảnh hưởng những bước phía sau. Tài liệu Maven cảnh báo thao tác này trong build bình thường cần được cân nhắc.

## 10. Độ rộng xóa: resolutionFuzziness

Tham số `resolutionFuzziness` quyết định mức Maven Dependency Plugin mở rộng phạm vi xóa khi đã chọn artifact:

| Giá trị | Ý nghĩa khái quát | Mức rủi ro |
| --- | --- | --- |
| `file` | Xóa đúng file artifact được chọn | Hẹp nhất trong các giá trị |
| `version` | Xóa các file gắn với **version** của artifact đã chọn | Mặc định ở plugin 3.11.0 |
| `artifactId` | Xóa phạm vi các version của cùng artifactId | Có thể ảnh hưởng nhiều version |
| `groupId` | Mở rộng tới groupId tương ứng | Rộng nhất, có thể ảnh hưởng nhiều artifact |

Với một JAR/POM cụ thể bị lỗi, **`version`** là điểm khởi đầu dễ giải thích vì cũng cho phép refresh metadata gắn với version đó. Tuy nhiên mức xóa thật sự còn do plugin và repository manager quyết định; không viết script dựa vào những folder phỏng đoán để thay thế plugin.

**Không chọn `-DresolutionFuzziness=groupId` như cách sửa mặc định.** Nếu groupId là `org.apache.commons`, phạm vi có thể bao trùm nhiều thư viện không liên quan trực tiếp đến lỗi bạn đang xử lý.

Tương tự, `artifactId` có thể xóa các version release và snapshot mà các project khác cần. Chọn mức rộng chỉ khi đã đo được nguyên nhân nằm ở tầng metadata đó và có cách khôi phục.

## 11. Ví dụ Java 17 thực hành: so sánh -U và purge có chọn lọc

Tạo project nhỏ:

```text
maven-cache-refresh-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/cache/App.java
```

### 11.1. pom.xml đầy đủ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>maven-cache-refresh-demo</artifactId>
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
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Maven đọc POM để resolve `commons-lang3:3.14.0`, rồi Compiler Plugin biên dịch code Java 17. POM khai báo artifact cụ thể nên **không có nhu cầu nâng version** trong bài này: ta chỉ kiểm chứng khả năng tải lại **cùng tọa độ artifact**.

### 11.2. src/main/java/com/example/cache/App.java

```java
package com.example.cache;

import org.apache.commons.lang3.StringUtils;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        String input = "Maven";
        System.out.println("Reverse: " + StringUtils.reverse(input));
        System.out.println("Upper: " + StringUtils.upperCase(input));
    }
}
```

Đây là một Java 17 class hợp lệ, thật sự sử dụng `commons-lang3`. Khi classpath có dependency đúng, stdout chương trình:

```text
Reverse: nevaM
Upper: MAVEN
```

Nếu chỉ chạy `java -cp target/classes com.example.cache.App` mà **không** thêm Commons Lang vào classpath, ứng dụng có thể lỗi `NoClassDefFoundError`. Ví dụ bên dưới dùng Maven Exec Plugin để dựng classpath dựa vào dependency đã resolve.

### 11.3. Bước A — build bình thường và xem dependency tree

Trong thư mục project:

```bash
mvn -version
mvn -B -ntp clean package
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dincludes=org.apache.commons:commons-lang3
```

Phiên bản được chọn cần là `org.apache.commons:commons-lang3:jar:3.14.0:compile`. Đây là tọa độ **dự kiến của dependency** trong cây, không phải toàn bộ log hoặc một câu khẳng định thời điểm tải file.

Chạy chương trình:

```bash
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=com.example.cache.App
```

Phần do chương trình in trên stdout:

```text
Reverse: nevaM
Upper: MAVEN
```

Nếu plugin/remote repository lỗi, hãy sửa lỗi phân giải trước. Không cần purging một kho đang hoạt động bình thường chỉ để “đảm bảo sạch”.

### 11.4. Bước B — thử -U, không xóa cache

```bash
mvn -U -B -ntp verify
```

Vì `commons-lang3:3.14.0` là **release đã tồn tại**, `-U` **không có nghĩa Java archive sẽ được tải lại từ đầu**. Lượt này phù hợp để kiểm tra updated SNAPSHOT và missing releases nếu có. Nếu `jar` release đang hỏng thật, chuyển sang bước C.

### 11.5. Bước C — purge riêng commons-lang3 theo version

```bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:purge-local-repository -Dinclude=org.apache.commons:commons-lang3 -DactTransitively=false -DresolutionFuzziness=version -DreResolve=true
```

Bài thực hành cố tình chọn dependency **trực tiếp** và một `groupId:artifactId` chính xác, nên phạm vi nhỏ hơn rất nhiều so với xóa cả `repository/`. Plugin có thể thông báo xóa/tải lại artifact. Khi remote ổn và artifact tồn tại, thực hiện kiểm tra cuối:

```bash
mvn -B -ntp clean verify
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dincludes=org.apache.commons:commons-lang3
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=com.example.cache.App
```

Mục tiêu sau purge: graph vẫn dùng `3.14.0`, build thành công và Java in hai dòng `Reverse`/`Upper` như cũ. Purge là để làm mới bản cache của artifact, **không phải để nâng version hoặc thay logic ứng dụng**.

**Chú ý về chạy lệnh:** Đây là các **lượt Maven độc lập**. Bước C thực sự xóa dữ liệu cache của artifact được chọn; chỉ chạy khi muốn quan sát hoặc cần khắc phục vấn đề. Đừng chạy bước C mỗi khi build thường ngày.

## 12. Kho thử biệt lập: cách đối chiếu mà không phá cache chung

Nếu nghi local repository hiện tại hỏng nhưng chưa chắc artifact nào gây lỗi, một phương pháp mạnh về chẩn đoán và thường an toàn hơn là dùng **local repository mới chỉ cho một lượt build**.

Linux/macOS, tại thư mục project:

```bash
mkdir -p "$HOME/maven-cache-diagnostic"
mvn -B -ntp "-Dmaven.repo.local=$HOME/maven-cache-diagnostic" clean verify
```

Windows PowerShell:

```powershell
$cache = Join-Path $HOME 'maven-cache-diagnostic'
New-Item -ItemType Directory -Force -Path $cache | Out-Null
mvn "-Dmaven.repo.local=$cache" -B -ntp clean verify
$code = $LASTEXITCODE
Write-Host "Maven exit code: $code"
```

Đường dẫn mới chứa cache **riêng**; lệnh này không đổi `settings.xml` và không xóa cache cũ. Do plugin/dependency chưa có, lần chạy đầu có thể tải nhiều dữ liệu và cần mạng. Hãy cân nhắc dung lượng và các mirror/proxy của môi trường.

Cách diễn giải:

| Kết quả khi dùng kho thử biệt lập | Kết luận phù hợp |
| --- | --- |
| Cache cũ lỗi nhưng kho mới build thành công | Có dấu hiệu vấn đề nằm ở cache/metadata local repo hoặc dữ liệu chỉ có trong kho cũ; điều tra artifact cụ thể |
| Cả hai đều lỗi giống nhau | Khả năng cao là POM/version/repository/server/JDK hoặc source; không nên tiếp tục xóa cache |
| Kho mới lỗi offline vì thiếu artifact | Đây là kết quả bình thường nếu cache chưa được nạp, không chứng minh kho mới sai |
| Kho mới tải artifact từ mirror khác | Kiểm tra lại settings/environment; phép thử không còn chỉ khác về cache |

**Không tự động xóa thư mục diagnostic bằng một lệnh phá hủy mù** khi chưa xác nhận đây đúng là kho thử do bạn tạo và không chứa artifact có giá trị. Trong môi trường CI, dùng thư mục job-specific và cơ chế cleanup an toàn của runner.

## 13. Trường hợp có SNAPSHOT và bản chỉ install cục bộ

### 13.1. SNAPSHOT đã được deploy lên remote

Với `com.example:shared-core:1.0-SNAPSHOT` trên server, lần build sau có thể cần kiểm tra metadata để lấy bản mới. Thử:

```bash
mvn -U -B -ntp verify
```

Nếu server không cho phép truy cập, hoặc chưa deploy SNAPSHOT thực sự, `-U` vẫn không làm artifact xuất hiện. Kiểm tra Maven repository manager, chính sách snapshots, version chính xác và credentials trước khi purge.

### 13.2. SNAPSHOT chỉ được mvn install trên máy này

Một thư viện nội bộ có thể được build từ source rồi cài local:

```bash
mvn -B -ntp install
```

Ở trường hợp đó, bản local installed là **sản phẩm build từ source**, không nhất thiết tồn tại trên remote. Nếu một purge hoặc thay local repository làm mất artifact đó, khắc phục bằng cách **build và install lại đúng project/version**, không cố bắt Maven tải từ Central.

### 13.3. Không so sánh snapshot như release bất biến

Metadata SNAPSHOT và file timestamped được remote publish có thể khác với cách local repository ghi artifact snapshot vừa install. Không nên sửa tên file, timestamp hoặc metadata thủ công để “làm Maven chọn bản mới”; dùng lệnh build/deploy theo vòng đời chuẩn và dependency resolution.

## 14. Plugin, parent và BOM: lỗi nào purge dự án thường không chạm tới?

Một dependency của mã Java và dependency của Maven plugin **không nhất thiết nằm cùng graph**. Tương tự, một parent POM/BOM import được dùng từ giai đoạn dựng Maven model, trước khi Maven có thể resolve tất cả project dependencies.

Khi gặp lỗi:

```text
Non-resolvable parent POM
Non-resolvable import POM
Plugin ... or one of its dependencies could not be resolved
```

hãy:
1. Kiểm tra **tọa độ và remote repository** mà Maven đang dùng;
2. Xác minh parent/BOM/plugin thật sự tồn tại trong nguồn đó;
3. Thử `-U` nếu liên quan cached missing release/update interval;
4. Chỉ khi có bằng chứng artifact cache thật sự có vấn đề mới cân nhắc `manualInclude` cho GA đúng, kèm `-DreResolve=false` và bước resolve/build lại sau đó.

**Không nhầm `dependency:purge-local-repository -Dinclude=...` với công cụ chắc chắn purge mọi plugin, parent hay BOM**. Chế độ `include` hoạt động dựa trên dependency tree của project; manual purge mới dành cho artifact không nằm trong tree cần quét.

## 15. Remote repository, mirror và metadata: khi purge không phải lời giải

Maven truy vấn remote repository theo cấu hình POM, parent, profiles/settings và áp dụng mirrors trước khi tải. Nếu cấu hình có vấn đề, xóa local cache có thể **làm lỗi nghiêm trọng hơn** vì Maven mất bản artifact cũ nhưng vẫn không tải lại được.

Kiểm tra nhanh:
- `settings.xml` có mirror URL đúng không?
- Repository ID, URL và credentials có khớp không?
- Có bật profile chứa repository đó không?
- Repository có cho phép `releases` hoặc `snapshots` phù hợp không?
- Mạng, proxy, TLS, chứng chỉ có hợp lệ không?
- Người dùng có quyền tải artifact không?
- Artifact đúng `groupId:artifactId:version:type:classifier` đã thật sự publish chưa?

Ví dụ một profile settings cho repository là **cấu hình minh họa**, không phải file để chép nguyên:

```xml
<profiles>
    <profile>
        <id>company-repos</id>
        <repositories>
            <repository>
                <id>company-releases</id>
                <url>https://repo.example.org/maven-releases</url>
            </repository>
        </repositories>
    </profile>
</profiles>
<activeProfiles>
    <activeProfile>company-repos</activeProfile>
</activeProfiles>
```

Các thẻ trên thuộc **`settings.xml`**, không phải POM, và cần đứng trong phần tử gốc `<settings>`. URL dùng để minh họa, không phải repository phục vụ bài thực hành.

Có thể chẩn đoán cấu hình qua:

```bash
mvn help:effective-settings -Doutput=effective-settings.xml
mvn help:effective-pom -Doutput=effective-pom.xml
```

Kiểm tra đúng repository đã được cấu hình và profile đã được kích hoạt. Hãy xử lý thiếu quyền/mirror/snapshot policy ở nguồn; **không dùng xóa toàn bộ local repository để thay cho việc sửa cấu hình remote**.

## 16. Cảnh báo với CI, build song song và cache chia sẻ

Local repository có thể đang được nhiều project, IDE, Maven process hoặc CI job dùng chung. Việc purge trong lúc build khác đang resolve dependency có thể gây tác động khó dự đoán.

Các nguyên tắc:
- Không chạy purge hàng loạt trên thư mục cache chia sẻ khi nhiều job đang dùng.
- Với CI, ưu tiên cache riêng theo workspace/job hoặc cơ chế quản lý cache/concurrency được runner hỗ trợ.
- Chỉ purge đúng artifact và khi không có tiến trình đang cần ghi/đọc chính tập artifact đó.
- Không đặt goal purge vào một phase chạy tự động trong mọi lần build trừ khi có lý do và hiểu rủi ro.
- Không dùng tài khoản root/admin để “vượt lỗi quyền” mà chưa xác định nguyên nhân.
- Lưu log của lệnh purge khi điều tra: artifact nào bị purge, có được resolve lại không, exit code thế nào.
- Không chia sẻ debug logs hoặc effective settings nội bộ chưa rà soát vì chúng có thể lộ URL server, cấu hình và thông tin nhạy cảm.

Trong container, home có thể là `/root` hoặc một user khác; cache mount có thể khác host. Với `-Dmaven.repo.local`, luôn xác nhận đường dẫn mà tiến trình **bên trong container** thực sự nhìn thấy, không suy từ host file manager.

## 17. Những lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Xử lý ít tác động hơn xóa hết .m2 |
| --- | --- | --- |
| `was cached in the local repository` | Một lần resolve thất bại đã bị cache tới kỳ update | Thử `mvn -U`; kiểm tra remote thực sự có artifact |
| SNAPSHOT vẫn cũ | Chưa tới update interval, chưa deploy snapshot mới hoặc mirror sai | Thử `-U`, xem metadata/remote policy |
| Một dependency cụ thể bị hỏng | Artifact/pom cache bị lỗi hoặc không nhất quán | `purge-local-repository` với `include` chính xác rồi resolve lại |
| Purge chạy nhưng không chạm dependency cần sửa | Artifact chỉ xuất hiện bắc cầu hoặc không thuộc project tree | Kiểm tra `dependency:tree` và `actTransitively`; cân nhắc manual |
| `manualInclude` xóa xong build sau vẫn lỗi | Artifact không còn trên remote hoặc lỗi mạng/quyền vẫn tồn tại | Sửa repository/credentials hoặc install lại nguồn nội bộ |
| Bị xóa nhiều version hơn dự tính | Chọn fuzziness quá rộng hoặc manual GA rộng | Chỉ định scope nhỏ, kiểm tra log trước khi dùng trên cache dùng chung |
| `mvn clean` không thay đổi lỗi dependency | `clean` chỉ xóa output build, không đổi local repo | Dùng `-U` hoặc purge đúng artifact |
| `-U` vẫn dùng JAR release cũ | Release đã cache hợp lệ, `-U` không ép tải lại mọi release | Nếu file thực sự hỏng, purge có mục tiêu; nếu cần version mới, sửa POM |
| Xóa `~/.m2` làm mất mirror/server settings | Xóa cả cấu hình người dùng | Khôi phục settings an toàn, không xóa thư mục gốc |
| Maven chạy bằng IDE dùng cache khác | IDE cấu hình user settings/local repo khác | Xem Maven runtime và `-Dmaven.repo.local` trong IDE |
| Kho thử trống build không chạy offline | Thiếu plugins/dependencies cần tải từ remote | Cho phép mạng, dùng mirror đúng, hoặc chuẩn bị cache |
| Lỗi `401 Unauthorized`/`403 Forbidden` | Thiếu credentials/quyền truy cập server | Sửa settings/server/account, purge không giải quyết |
| Lỗi `PKIX path building failed` | Truststore/certificate/proxy TLS có vấn đề | Sửa CA/truststore/proxy; không xóa cache mù |
| `mvn dependency:purge-local-repository` không tải được plugin | Chính Dependency Plugin chưa có trong cache và mạng lỗi | Sửa network/repository trước; không thể purge khi goal không chạy |
| Local-only `SNAPSHOT` biến mất | Artifact chỉ tồn tại sau `mvn install` cục bộ | Build và install lại đúng project/source |
| Có artifact nhưng Maven vẫn từ chối dùng | Repository provenance, version, type/classifier, metadata khác | Xem tọa độ và cấu hình repository/Resolver, không chỉnh file metadata tay |

## 18. Quy trình chuẩn để áp dụng trong dự án

Một quy trình “làm mới có mục tiêu” có thể áp dụng trong code review hoặc tài liệu vận hành:

**Bước 1 — Thu thập bằng chứng.** Ghi lại lỗi Maven đầu tiên, tọa độ artifact, phase/goal thất bại, phiên bản Maven/JDK và đúng project/module. Đọc `dependency:tree` nếu Maven dựng được dependency graph.

**Bước 2 — Phân loại lỗi.** Đây là lỗi cached missing artifact/SNAPSHOT update, lỗi binary JAR, lỗi POM/BOM/plugin, hay lỗi mạng/quyền?

**Bước 3 — Chọn biện pháp nhỏ nhất.** Với SNAPSHOT/missing release, thử `-U`. Với một direct dependency bị hỏng, dùng `purge-local-repository` + `include`. Với parent/plugin ngoài tree, cân nhắc `manualInclude` sau khi bảo đảm khả năng resolve lại.

**Bước 4 — Giới hạn blast radius.** Kiểm tra `actTransitively`, `resolutionFuzziness`, `reResolve`, và việc cache có đang chia sẻ cho project/CI job khác không. Không mặc định purge groupId.

**Bước 5 — Kiểm chứng sau thay đổi.** Chạy lại đúng `dependency:tree`, `mvn verify`/test thích hợp và xem mã thoát. Kiểm tra artifact/version được chọn, không chỉ việc Maven đã in “Downloaded”.

**Bước 6 — Ghi lại nguyên nhân gốc.** Nếu remote repository cấu hình sai, chữa ở settings/POM/repository manager. Nếu release bị thay nội dung, sửa quy trình phát hành immutable. Nếu một SNAPSHOT liên tục thay đổi gây build thiếu ổn định, cân nhắc chốt release/version rõ ràng.

**Bước 7 — Cleanup có kiểm soát.** Chỉ dọn cache diagnostic/cũ sau khi xác nhận đây đúng thư mục cần dọn, không chứa artifact local-only và không được process khác dùng. Trong CI, để runner thực hiện theo quy tắc retention; trong máy phát triển, cân nhắc sao lưu trước.

## 19. Bài tập tự kiểm tra

1. Vì sao `~/.m2` và `~/.m2/repository` không phải một khái niệm?
2. Tại sao `mvn clean` không sửa lỗi artifact đã cache trong local repository?
3. `-U` có ép tải lại mọi release JAR đã có không? Nó thực sự tác động tới loại cập nhật nào?
4. Khi chỉ một artifact `org.apache.commons:commons-lang3` bị hỏng, có nên purge toàn bộ dependency tree không?
5. `-Dinclude` khác `-DmanualInclude` ra sao?
6. `-DactTransitively=false` có ý nghĩa gì nếu artifact bạn muốn xử lý chỉ là transitive dependency?
7. `-DreResolve=false` và `-DreResolve=true` khác nhau thế nào trong thao tác purge?
8. Vì sao `-DresolutionFuzziness=groupId` rủi ro hơn `version`?
9. Tại sao purge một parent POM/BOM/plugin đòi bảo đảm có thể tải/cài lại artifact đó?
10. Khi build với cache mới bằng `-Dmaven.repo.local` thành công, nên kết luận và kiểm tra gì tiếp theo?
11. Tại sao xóa cache không sửa được lỗi TLS, DNS, mirror hoặc HTTP 401/403?
12. Nếu một artifact chỉ từng được `mvn install` ở local mà chưa publish remote, cách phục hồi phù hợp là gì?

**Tổng kết:** Trong Apache Maven, local repository là cả **cache download** lẫn **kho artifact cài cục bộ**. Xóa toàn bộ `.m2` có phạm vi tác động quá lớn và có thể mất cả settings/credentials. Hãy bắt đầu bằng **`-U`** cho vấn đề SNAPSHOT/cached miss, dùng **`dependency:purge-local-repository` với `include` và độ rộng phù hợp** khi thật sự cần refresh một artifact, dùng **`manualInclude`** cho POM/plugin ngoài project dependency tree, và **`-Dmaven.repo.local`** để thử cache mới mà không phá kho đang dùng. Luôn xác minh version/tree, build và quyền remote sau mỗi thay đổi.

## Tài liệu Apache Maven chính thức

- [Apache Maven — Maven Local Repositories (hai vai trò cache/install, cảnh báo thao tác trực tiếp)](https://maven.apache.org/repositories/local.html)
- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories)
- [Apache Maven Dependency Plugin — dependency:purge-local-repository parameters (3.11.0)](https://maven.apache.org/plugins/maven-dependency-plugin/purge-local-repository-mojo.html)
- [Apache Maven Dependency Plugin — Purging Project Dependencies](https://maven.apache.org/plugins/maven-dependency-plugin/examples/purging-local-repository.html)
- [Apache Maven — Maven CLI Options Reference (3.9.x)](https://maven.apache.org/ref/3.9.16/maven-embedder/cli.html)
- [Apache Maven — Settings Reference (updatePolicy, mirrors, profiles)](https://maven.apache.org/settings.html)
- [Apache Maven — Setting up Multiple Repositories](https://maven.apache.org/guides/mini/guide-multiple-repositories.html)
