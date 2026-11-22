# Maven checksumPolicy và xử lý lỗi toàn vẹn khi tải xuống

> **Build Tool Maven · Kho và metadata**  
> Bài học tập trung vào cấu hình **`checksumPolicy`**, cách Maven Resolver kiểm tra artifact/metadata khi tải từ repository, phân biệt các loại lỗi, và quy trình khôi phục **không hy sinh tính toàn vẹn**.

## 1. Vấn đề: tải được file chưa có nghĩa file đúng

Một project Maven thường cần tải POM, JAR, plugin và metadata từ **remote repository** hoặc **repository manager/mirror** của tổ chức. Nếu dữ liệu được tải thiếu byte, hỏng trên đường truyền, proxy cache giữ bản không nhất quán hoặc artifact bị thay thế mà checksum không cập nhật tương ứng, Maven cần cách phát hiện **lỗi toàn vẹn (integrity error)**.

**Checksum** là một giá trị băm được tính từ **bytes** của file, thường được repository công bố bên cạnh artifact, hoặc trả về theo cơ chế metadata/transport được Resolver hỗ trợ. Maven Resolver tính checksum của dữ liệu nhận về rồi so sánh với checksum **kỳ vọng**. Nếu hai bên khác nhau, dữ liệu **không khớp với giá trị kiểm tra**. Lỗi này khác với tình huống file có version sai, địa chỉ repository sai hoặc Internet bị ngắt.

Ví dụ, một repository có thể chứa:

```text
org/example/demo-lib/1.2.3/
├── demo-lib-1.2.3.pom
├── demo-lib-1.2.3.pom.sha1
├── demo-lib-1.2.3.jar
├── demo-lib-1.2.3.jar.sha1
└── ... các metadata/checksum khác tùy repository
```

Đây là **cấu trúc minh họa**; không phải repository nào cũng buộc có đúng từng file sidecar `.sha1`. Resolver hiện đại có nhiều cách lấy checksum kỳ vọng: dữ liệu cung cấp sẵn trong transport, checksum kèm response hoặc file checksum riêng. Sự hiện diện của sidecar tùy repository, transport và cấu hình.

**`checksumPolicy`** quy định Maven phải làm gì khi checksum bị thiếu hoặc không khớp. Nó **không tự xác minh tác giả đã xuất bản artifact**, không thay thế chữ ký số/chuỗi tin cậy, và không tự sửa bytes bị hỏng.

### Mục tiêu sau bài học

1. Hiểu checksum được tính và so sánh như thế nào; phân biệt **integrity** với **authenticity**.
2. Phân biệt chính xác `fail`, `warn`, `ignore` và lựa chọn an toàn trong CI.
3. Cấu hình checksum policy cho **release** và **snapshot**, cho **dependency repositories** lẫn **plugin repositories**.
4. Sử dụng Maven CLI `-C`/`--strict-checksums` và `-c`/`--lax-checksums` đúng ngữ cảnh.
5. Chẩn đoán checksum mismatch, missing checksum, 404 artifact, timeout, lỗi TLS/401/403 và cache local khác nhau.
6. Xác minh bằng dự án Java 17 có dependency thực tế; biết giới hạn của kiểm thử không có repository hỏng.
7. Khôi phục bằng cách kiểm tra nguồn, cache và repository manager **có phạm vi**, không vô hiệu hóa chính sách để “build xanh”.

Bài diễn giải các chức năng phổ biến của **Maven 3.9.x** và Maven Resolver; khác biệt phiên bản/transport có thể thay đổi log hoặc thuật toán checksum được hỗ trợ. Khi chạy thực tế, luôn xem `mvn -version`.

## 2. Checksum và phép so sánh byte

Giả sử repository xuất bản artifact JAR có bytes là `B`, kèm một giá trị băm `H(B)`. Sau khi tải xuống, Maven Resolver tính `H(B')` từ bytes nhận được. Nếu:

```text
H(B') == H(B)  -> dữ liệu khớp checksum kỳ vọng
H(B') != H(B)  -> dữ liệu không khớp: checksum mismatch
không có H(B) -> không có checksum kỳ vọng: missing checksum
```

Lựa chọn **hash algorithm** có thể là SHA-1, MD5 hoặc thuật toán khác được Maven Resolver/remote hỗ trợ. Các Maven repositories truyền thống phổ biến với file `.sha1` và `.md5`; tuy nhiên điều này **không có nghĩa Maven chỉ hỗ trợ hai thuật toán**, hoặc mọi repo đều cung cấp cả hai.

**Checksum không giống kích thước file:** Hai file cùng số byte vẫn có thể có checksum khác. **Checksum không giống tên file:** Một file vẫn tên `demo-lib-1.2.3.jar` nhưng bị thay nội dung sẽ có checksum khác. **Checksum không đồng nghĩa chữ ký số:** nếu kẻ tấn công thay cả artifact **và** checksum kỳ vọng từ cùng nguồn không đáng tin, phép so sánh vẫn có thể khớp.

### 2.1. Vì sao SHA-1/MD5 chưa đủ cho bảo đảm nguồn gốc

Trong hệ thống Maven truyền thống, checksum sidecar chủ yếu bảo vệ **toàn vẹn truyền tải** (đặc biệt phát hiện lỗi upload/download/cache). Nếu artifact và file `.sha1` cùng được lấy từ một nguồn bị kiểm soát bởi kẻ tấn công, checksum khớp vẫn **không xác minh được publisher**. SHA-1 và MD5 còn có các điểm yếu về khả năng kháng va chạm; không dùng chúng làm bằng chứng xác thực mật mã duy nhất.

Đối với build nhạy cảm:

- Tải qua **HTTPS** từ repository tin cậy và mirror được quản lý.
- Bật **strict checksum validation** để lỗi hoặc thiếu checksum phù hợp chính sách làm build dừng.
- Cân nhắc **trusted checksums** từ nguồn độc lập hoặc xác minh chữ ký/publisher khi quy trình bảo mật yêu cầu.
- Có quy trình quản lý artifact bất biến (*immutable releases*), logging, kiểm tra quyền xuất bản và kiểm soát supply chain.

Maven Resolver có tài liệu riêng về **trusted checksums**. Không đánh đồng `checksumPolicy=fail` trên cùng nguồn truyền tải với một cơ chế xác minh chữ ký số độc lập.

## 3. Ba giá trị checksumPolicy

`checksumPolicy` có ba lựa chọn chính: **`fail`**, **`warn`**, **`ignore`**.

| Giá trị | Khi checksum thiếu hoặc sai | Rủi ro/hệ quả | Thực hành phù hợp |
| --- | --- | --- | --- |
| `fail` | Enforce checksum; resolution/build có thể **thất bại** | Dừng pipeline nếu repository không cung cấp checksum hợp lệ | **Ưu tiên cho CI/release** và repository tin cậy có checksum đầy đủ |
| `warn` | Ghi cảnh báo và có thể tiếp tục dùng file | Artifact có thể không được xác minh đầy đủ | Tương thích hệ thống cũ; phải điều tra warning |
| `ignore` | Bỏ qua hiện diện/kiểm tra checksum theo policy | Mất tín hiệu phát hiện file tải xuống bị sai/thiếu | Tránh dùng cho production; chỉ cân nhắc tình huống được kiểm soát rõ |

Theo Maven Settings/POM Reference và API `RepositoryPolicy` của Maven Resolver, `warn` là **mặc định phổ biến**. Mặc định ấy ưu tiên khả năng tương thích với nhiều repository nhưng **không phải mức kiểm soát tốt nhất cho CI cần toàn vẹn nghiêm ngặt**.

### 3.1. `fail` có phải lúc nào cũng “không tải gì xuống” không?

`fail` là **hành vi thực thi chính sách khi Resolver kiểm tra checksum trong quá trình resolve/transport**. Maven có thể đã nhận dữ liệu hoặc thử lấy checksum trước khi quyết định thất bại. Đừng diễn giải rằng `fail` luôn ngăn mọi byte không đúng xuất hiện tạm thời trên máy. Quan trọng là **không coi bản tải không được xác minh là kết quả resolution thành công**.

Phân tích log để xác định artifact/metadata nào bị lỗi. Một lỗi ở **POM của dependency**, **plugin JAR** hoặc **maven-metadata.xml** có thể gây build dừng **trước phase compile**, dù Java source không có lỗi.

### 3.2. `warn` có nghĩa gì?

`warn` thường ghi thông tin như “checksum validation failed” hoặc “checksum missing”, nhưng Maven có thể tiếp tục. Điều đó **không chứng minh file an toàn**. Warning vẫn là tín hiệu cần xem xét, đặc biệt khi bản release vốn phải bất biến.

Nếu team đang sử dụng `warn`, hãy ít nhất thu thập/giám sát warning, tìm repository gây lỗi và chuyển dần sang `fail` sau khi sửa nguồn. Không coi `BUILD SUCCESS` là một chứng nhận integrity khi log có checksum warnings.

### 3.3. Vì sao không dùng `ignore` để chữa lỗi?

Nếu checksum không khớp vì proxy trả một JAR khác với `.sha1`, đổi `checksumPolicy` sang `ignore` chỉ **che dấu triệu chứng**. Project có thể tải class khác mong đợi, gây `ClassNotFoundException`, API mismatch hoặc rủi ro bảo mật. Cách sửa là đối chiếu artifact gốc, metadata, mirror và cache.

**Không copy `<checksumPolicy>ignore</checksumPolicy>` vào POM chỉ để qua CI.** Việc này làm mất một hàng rào phát hiện lỗi mà chưa làm đúng nội dung repository.

## 4. Checksum policy được đặt ở đâu?

Maven có thể lấy repository definitions từ `pom.xml`, parent POM, super POM hoặc `settings.xml` (ví dụ profile trong settings). Mỗi repository có các chính sách dành cho **releases** và **snapshots**, và trong các chính sách đó có `checksumPolicy`.

### 4.1. Fragment trong pom.xml: repositories

```xml
<repositories>
    <repository>
        <id>company-artifacts</id>
        <url>https://repo.example.org/maven/public</url>
        <releases>
            <enabled>true</enabled>
            <updatePolicy>daily</updatePolicy>
            <checksumPolicy>fail</checksumPolicy>
        </releases>
        <snapshots>
            <enabled>true</enabled>
            <updatePolicy>always</updatePolicy>
            <checksumPolicy>fail</checksumPolicy>
        </snapshots>
    </repository>
</repositories>
```

Đây là **fragment** đặt trong `<project>` của POM, **không phải POM đầy đủ**. `https://repo.example.org/maven/public` là **URL minh họa**, cần thay bằng repository thật mà tổ chức kiểm soát. Không thử tải từ domain ví dụ rồi nhầm lỗi DNS thành checksum mismatch.

Ý nghĩa:

- `<releases>` quy định cách xử lý artifact có version release.
- `<snapshots>` quy định cách xử lý version kết thúc bằng `-SNAPSHOT` và metadata snapshot.
- `<enabled>` bật/tắt loại artifact ở repository đó.
- `<updatePolicy>` quyết định thời điểm Maven kiểm tra cập nhật metadata/artifact theo chính sách.
- `<checksumPolicy>` quyết định phản ứng khi checksum thiếu hoặc không khớp.

Hai nhóm `<releases>` và `<snapshots>` **độc lập**: một repository có thể chỉ cho phép releases hoặc chỉ snapshots. Không đặt `<checksumPolicy>` ở mức `<dependency>` từng artifact trong `<dependencies>` như thể đó là thuộc tính của dependency.

### 4.2. Fragment cho pluginRepositories

Maven còn cần tải **build plugins** như `maven-compiler-plugin`, `maven-surefire-plugin`, `maven-resources-plugin`, và các dependency của plugin.

```xml
<pluginRepositories>
    <pluginRepository>
        <id>company-plugins</id>
        <url>https://repo.example.org/maven/plugins</url>
        <releases>
            <enabled>true</enabled>
            <checksumPolicy>fail</checksumPolicy>
        </releases>
        <snapshots>
            <enabled>false</enabled>
        </snapshots>
    </pluginRepository>
</pluginRepositories>
```

Đây cũng chỉ là **fragment POM**. Một cấu hình strict chỉ trong `<repositories>` **không nhất thiết** đã mô tả đầy đủ mọi nguồn plugin. Khi kiểm tra integrity của một build, cần biết **repository nào thực sự phân phối dependencies và plugins**.

### 4.3. Đặt repository trong settings.xml

Nhiều tổ chức muốn dùng một repository manager cho tất cả projects. Khi đó cấu hình repository có thể nằm trong **user/global settings** thay vì lặp lại ở từng POM:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0
                              https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <profiles>
        <profile>
            <id>checksum-strict</id>
            <repositories>
                <repository>
                    <id>company-artifacts</id>
                    <url>https://repo.example.org/maven/public</url>
                    <releases>
                        <enabled>true</enabled>
                        <checksumPolicy>fail</checksumPolicy>
                    </releases>
                    <snapshots>
                        <enabled>true</enabled>
                        <checksumPolicy>fail</checksumPolicy>
                    </snapshots>
                </repository>
            </repositories>
            <pluginRepositories>
                <pluginRepository>
                    <id>company-plugins</id>
                    <url>https://repo.example.org/maven/plugins</url>
                    <releases>
                        <enabled>true</enabled>
                        <checksumPolicy>fail</checksumPolicy>
                    </releases>
                    <snapshots>
                        <enabled>false</enabled>
                    </snapshots>
                </pluginRepository>
            </pluginRepositories>
        </profile>
    </profiles>
    <activeProfiles>
        <activeProfile>checksum-strict</activeProfile>
    </activeProfiles>
</settings>
```

Đây là **một ví dụ settings.xml cấu trúc đầy đủ tối thiểu**, nhưng sử dụng **URL không có thật**. Muốn sử dụng cần thay URLs bằng endpoint hoạt động, hòa vào settings hiện có và kiểm tra quyền truy cập. **Không ghi đè settings cá nhân/CI chỉ để chạy ví dụ** nếu nó đã có proxies, mirrors và credentials khác.

Profile trong `<profiles>` **phải được kích hoạt** để các repository được dùng; ví dụ trên kích hoạt tường minh bằng `<activeProfiles>`. Nếu profile không active, những dòng `<checksumPolicy>` trong nó **không tự có hiệu lực**.

**Cảnh báo về cấu hình:** `settings.xml` còn có `<mirrors>` và `<servers>`. Mirror thay đổi endpoint thực tế mà Maven sử dụng; credentials có thể được gắn theo repository/mirror ID. Xem effective settings và log để chắc chắn file được tải từ nơi bạn đang cấu hình, không tự kết luận URL ở POM là URL kết nối cuối cùng.

### 4.4. Khác nhau giữa repositories và mirrors

`<repositories>` / `<pluginRepositories>` định nghĩa nguồn mà Maven có thể dùng; `<mirrors>` có thể **thay thế** một hoặc nhiều endpoint theo `<mirrorOf>`. Nếu doanh nghiệp cấu hình mirror toàn bộ với `mirrorOf=*`, lỗi checksum có thể đến từ **repository manager/mirror**, không phải Central dù POM không nhắc đến repository nội bộ.

Ví dụ **fragment mirror** trong settings:

```xml
<mirrors>
    <mirror>
        <id>company-mirror</id>
        <mirrorOf>*</mirrorOf>
        <url>https://repo.example.org/maven/proxy</url>
    </mirror>
</mirrors>
```

Đây là placeholder endpoint. Mirror làm thay đổi đường tải thực tế; không phải lệnh `checksumPolicy=ignore` và không sửa được checksum đang sai trên repository manager. Với mirror, phải đối chiếu **effective repository policy** và server logs tại endpoint thực tế, đặc biệt khi POM, settings, super POM và profile cùng định nghĩa repositories.

### 4.5. Release và snapshot khác nhau khi kiểm tra cập nhật

Một **release** như `1.2.3` thường được kỳ vọng là bất biến. Nếu server **ghi đè nội dung** `demo-lib-1.2.3.jar` nhưng chưa cập nhật `.sha1`, checksum mismatch có thể xuất hiện.

Một **snapshot** như `1.2.4-SNAPSHOT` có thể được xuất bản lại qua metadata timestamped snapshots và update policies. Maven dùng `maven-metadata.xml` để chọn snapshot thực tế. Nếu metadata, POM, JAR và các checksum được proxy cache **không đồng bộ**, bạn có thể thấy lỗi thiếu artifact hoặc checksum mismatch.

`updatePolicy` và `checksumPolicy` là **hai chính sách khác nhau**:

| Cấu hình | Câu hỏi được giải quyết |
| --- | --- |
| `updatePolicy` | Khi nào Maven kiểm tra metadata/artifact có phiên bản cập nhật? |
| `checksumPolicy` | Khi file được kiểm tra, thiếu/sai checksum thì xử lý thế nào? |
| `<enabled>` | Có cho phép truy cập releases/snapshots từ repository này không? |

**Đổi `updatePolicy=always` không tự sửa checksum sai.** Nó chỉ tác động thời điểm kiểm tra/cập nhật; nguồn artifact vẫn phải nhất quán.

## 5. Maven CLI: -C và -c

Maven hỗ trợ các lựa chọn CLI:

```text
-C, --strict-checksums  Fail the build if checksums don't match
-c, --lax-checksums     Warn if checksums don't match
```

Cách chạy một project bình thường trong chế độ kiểm tra nghiêm ngặt:

```bash
mvn -B -C clean verify
```

Trong đó:

- `-B` bật **batch mode** cho CI/log không tương tác.
- `-C` hoặc `--strict-checksums` yêu cầu **fail khi checksum mismatch** trong resolution.
- `clean verify` chạy build lifecycle tới phase verify, không tự là một công cụ quét chữ ký số.

Trong môi trường đang điều tra tương thích với kho cũ:

```bash
mvn -B -c clean verify
```

`-c` chuyển sang **cảnh báo** cho mismatch thay vì strict fail. **Không dùng -c như giải pháp vĩnh viễn** khi một artifact bị nghi hỏng. `-C` và `-c` là **lựa chọn khác nhau**; đừng truyền cả hai trong một command rồi suy đoán cái nào thắng.

Nếu đã cấu hình `checksumPolicy=fail` trong repository policies, vẫn nên ghi nhận **cờ CLI thực tế** khi chẩn đoán. Các bản Maven/Resolver, profile, mirrors và session configuration có thể ảnh hưởng chính sách hiệu lực; không suy diễn rằng một dòng XML trong repository chưa được dùng đã kiểm soát toàn bộ phiên build. Với CI, ưu tiên có quy tắc nhất quán và kiểm chứng trên máy dùng Maven version thật.

### 5.1. Các flags liên quan nhưng không phải chính sách checksum

| Flag | Tác dụng | Không nên hiểu là |
| --- | --- | --- |
| `-C` / `--strict-checksums` | Fail khi kiểm tra checksum không đạt | Chữ ký số xác thực publisher |
| `-c` / `--lax-checksums` | Cảnh báo checksum mismatch | Bảo đảm artifact lành mạnh |
| `-U` | Yêu cầu Maven kiểm tra cập nhật theo chế độ áp dụng; hữu ích với snapshots và cached failure | Tự chữa server đang trả JAR/checksum không nhất quán |
| `-o` | Offline: không tải từ remote | Xác minh mọi artifact cached có chữ ký đáng tin |
| `-e` | In thông tin lỗi/stacktrace sâu hơn | Thay thế điều tra URL và bytes |
| `-X` | Debug log chi tiết | Dữ liệu có thể công khai an toàn |
| `-s` | Dùng user settings file được chỉ định | Tự bật tất cả profiles trong file |
| `-Dmaven.repo.local=...` | Chọn local repository riêng cho build | Tự thay checksum policy của remote |

Nếu chạy `mvn -C -o verify`, mọi dependency/plugin chưa cache không được tải; Maven có thể fail **vì offline**, chứ không phải vì checksum mismatch. Nếu một artifact đã cache, strict flag **không đảm bảo buộc tải lại mọi artifact và kiểm tra với nguồn độc lập** trong tất cả tình huống; Resolver có cơ chế riêng cho cache và kiểm tra nội bộ. Không coi lần chạy offline thành công là bằng chứng rằng mọi file local đã được so sánh lại với checksum remote hiện tại.

## 6. Một quy trình tải và xác minh artifact

Dòng xử lý điển hình ở mức khái niệm:

```text
Maven cần artifact G:A:V
          |
          v
Kiểm tra local repository và metadata cache
          |
      đã usable?  ----- có -----> Dùng dữ liệu local phù hợp
          |
         không
          v
Chọn effective repository/mirror và policy
          |
          v
Kết nối HTTPS / tải POM, JAR hoặc metadata
          |
          v
Lấy checksum kỳ vọng (sidecar / headers / cơ chế được hỗ trợ)
          |
          v
Tính checksum từ dữ liệu tải về
          |
    +-----+----------------------+----------------------+
    | match                      | mismatch             | missing
    v                            v                      v
Chấp nhận dữ liệu       Áp checksumPolicy       Áp checksumPolicy
                           fail / warn / ignore     fail / warn / ignore
```

Sơ đồ này **đơn giản hóa** nội bộ Maven Resolver: không khẳng định Maven luôn mở URL `.sha1` tách biệt, luôn theo đúng một thứ tự tải file hay luôn xử lý cache y hệt giữa Maven 3 và Maven 4. Tùy transport, checksum có thể được cung cấp theo nhiều cách; session có thể có chính sách bổ sung.

### 6.1. Những file nào có thể cần checksum?

- Artifact chính: `.jar`, `.war`, `.zip`, `.pom`, hoặc packaging khác.
- POM metadata cần đọc để tính dependency graph.
- `maven-metadata.xml` dùng giải quyết versions/snapshots.
- Plugin artifacts và plugin dependencies.
- Các resource/artifact khác được Resolver xử lý theo cùng cơ chế.

Do Maven phải giải quyết POM, parent/BOM và build plugins **trước khi compile** trong nhiều build, lỗi checksum có thể xảy ra **ngay khi `mvn validate` hoặc goal plugin khởi chạy**. Không phải Java compiler đã làm sai nội dung JAR trong mọi lỗi download.

### 6.2. `missing checksum` khác `checksum mismatch`

**Missing checksum**: Resolver không lấy được checksum kỳ vọng bằng các phương thức hỗ trợ. Có thể server không công bố sidecar, proxy chặn response checksum hoặc repository chưa xuất bản đủ metadata. Nếu policy `fail` yêu cầu checksum phải có, resolution có thể dừng.

**Checksum mismatch**: Resolver có checksum kỳ vọng, nhưng hash tính từ dữ liệu nhận về **khác**. Hướng điều tra là consistency của bytes và checksum: upload bị cắt, cache không đồng bộ, proxy trả sai file, repository đã ghi đè artifact mà sidecar chưa đổi, hoặc bị can thiệp.

**404 artifact**: POM/JAR yêu cầu **không có tại đường dẫn GAV** trên repository đã chọn. Đây là *not found*, không tự động là checksum mismatch. Có thể có 404 khi Maven tìm một **sidecar checksum** nhưng artifact chính vẫn tải được; cần xem **URL bị 404** trước khi kết luận.

## 7. Dự án Java 17 để thực hành checksum strict

Bài thực hành dùng một dependency JAR thật từ Maven Central, để Maven có lý do **tải dependency và các POM/plugin liên quan**. Đồng thời, mã Java tính SHA-256 cho một chuỗi đã biết để minh họa nguyên lý hash.

**Hai tầng không được nhầm:**

1. **`mvn -C`**: Maven Resolver kiểm tra checksum khi nó resolve các artifact từ repository. Đây là tính năng chúng ta đang học.
2. **`MessageDigest` trong Java**: chương trình tự tính hash của dữ liệu trong bộ nhớ, **chỉ để giải thích nguyên lý**. Nó không cấu hình hay thay thế `checksumPolicy` của Maven.

### 7.1. Cấu trúc project

```text
checksum-policy-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── org/
                └── example/
                    └── ChecksumApp.java
```

Điều kiện: Java 17+, Maven 3.9.x (hoặc bản tương thích) và có quyền tải artifacts từ repository tin cậy. Không cần file dữ liệu nhạy cảm.

### 7.2. File pom.xml đầy đủ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>checksum-policy-demo</artifactId>
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
        </plugins>
    </build>
</project>
```

**Giải thích:**

- POM khai báo artifact JAR `commons-lang3:3.14.0` để Maven thực sự **resolve/tải** từ repository.
- Không tự khai báo repository URL trong POM này: nó dùng Maven Central hoặc mirror/settings mà môi trường đã cấu hình.
- Project dùng `maven.compiler.release=17`, và Compiler Plugin có version xác định.
- Project **không** cần chỉnh `checksumPolicy` trong POM để thử `-C`; cờ strict được áp dụng trên phiên chạy Maven.
- Không có plugin build phức tạp hoặc server nội bộ; phù hợp làm bài học tái hiện trên một máy có kết nối mạng.

### 7.3. File src/main/java/org/example/ChecksumApp.java

```java
package org.example;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import org.apache.commons.lang3.StringUtils;

public final class ChecksumApp {
    private ChecksumApp() {
    }

    private static String sha256(String value)
            throws NoSuchAlgorithmException {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        return HexFormat.of().formatHex(digest.digest(bytes));
    }

    public static void main(String[] args)
            throws NoSuchAlgorithmException {
        String message = StringUtils.upperCase("maven checksum demo");
        String expected =
                "ba7816bf8f01cfea414140de5dae2223"
                + "b00361a396177a9cb410ff61f20015ad";

        System.out.println(message);
        System.out.println("sha256(abc)=" + sha256("abc"));
        System.out.println("unchanged=" + expected.equals(sha256("abc")));
        System.out.println("tampered=" + expected.equals(sha256("abd")));
    }
}
```

Các class `MessageDigest`, `StandardCharsets`, `HexFormat` là API **JDK 17**. `StringUtils` được import trực tiếp từ `commons-lang3`. Tên file, package và class trùng với cấu trúc thư mục. Hash SHA-256 của chuỗi ASCII `"abc"` là **test vector đã biết**, nên kết quả không phụ thuộc timezone, hệ điều hành hay locale.

### 7.4. Chạy Maven ở strict mode

Tại thư mục project:

```bash
java -version
javac -version
mvn -version
mvn -B -C clean package
```

Đối với kho Maven Central/mirror hợp lệ cung cấp artifact/checksum nhất quán, lệnh trên **kỳ vọng build thành công**. `-C` không cố tạo lỗi: nó chỉ làm checksum mismatch trở thành lỗi nếu xảy ra.

Để chạy chương trình với dependency classpath, dùng Maven Exec Plugin có version cố định:

```bash
mvn -B -C -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=org.example.ChecksumApp
```

**Stdout chính xác của mã Java** (không tính Maven logs):

```text
MAVEN CHECKSUM DEMO
sha256(abc)=ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
unchanged=true
tampered=false
```

Giải thích:

1. `"abc"` nguyên bản tạo checksum đúng với `expected`, nên `unchanged=true`.
2. `"abd"` khác một byte nên checksum khác, dẫn tới `tampered=false`.
3. Phần Java **không phá hỏng artifact** và không phải test kiểm chứng Maven thực sự gặp checksum mismatch; nó chứng minh ý nghĩa toán học của việc so sánh checksum.
4. Maven trước đó đã resolution POM/JAR/plugin theo policy khi chạy build với `-C`.

**Không** chạy `java -cp target/classes org.example.ChecksumApp` mà không bổ sung JAR ngoài: `commons-lang3` sẽ thiếu ở runtime. Maven Exec Plugin sử dụng project dependency classpath cho main class.

### 7.5. Thử với local repository riêng, không động vào cache chính

Nếu muốn quan sát Maven **tải lại** dependencies/plugins từ repository trên một cache độc lập:

```bash
mvn -B -C -Dmaven.repo.local=.m2-checksum-lab clean package
```

Thư mục `.m2-checksum-lab` là một **local Maven repository thử nghiệm**, đường dẫn tương đối theo môi trường chạy. Dùng một thư mục mới chưa có cache để Maven phải tải artifact; không thêm thư mục này vào Git. Các build khác của bạn sử dụng `~/.m2/repository` không bị buộc thay đổi.

Trên Windows PowerShell, Linux và macOS, Maven nhận tùy chọn `-D` ở cùng dạng. Đường dẫn relative có thể được diễn giải theo process working directory; hãy chạy từ thư mục project như hướng dẫn. Khi cần CI tái lập, chọn một đường dẫn tuyệt đối rõ ràng trong workspace/cache do CI quản lý.

**Cảnh báo:** local repository riêng cũng tải lại toàn bộ plugins/dependencies cần thiết; lệnh không được dùng như cách “tẩy” tất cả cache sản xuất. Nếu repository có **lỗi integrity thật**, strict mode sẽ phát hiện và không có lệnh nào trong bài buộc nó vượt lỗi.

### 7.6. Quan sát file cache chỉ để chẩn đoán

Với layout repository thông thường, sau khi tải thành công, artifact có thể nằm tại:

```text
~/.m2/repository/org/apache/commons/commons-lang3/3.14.0/
    commons-lang3-3.14.0.jar
    commons-lang3-3.14.0.pom
    ... metadata/checksum/tracking files tùy Resolver
```

Cấu trúc file có thể khác nếu Maven Resolver dùng **split local repository** hoặc cấu hình cache khác. Vì vậy không viết script sản xuất giả định nội bộ local repo cố định; tài liệu Maven khuyên dùng API Resolver để thao tác kho ở quy mô tool.

Đừng sửa trực tiếp `.jar`, `.pom` hay sidecar checksum để thử ép lỗi trên máy làm việc; làm vậy có thể phá cache của dự án khác. Nếu muốn kiểm nghiệm lỗi checksum end-to-end trong phòng lab, dùng **repository HTTP thử nghiệm do bạn kiểm soát**, artifact test không nhạy cảm và local repo hoàn toàn riêng, không tái sử dụng mirror/credentials thật.

## 8. Phân biệt một số thông báo lỗi khi tải xuống

Một số dấu hiệu có thể xuất hiện trong log Maven:

| Dấu hiệu | Loại vấn đề khả dĩ | Hướng điều tra |
| --- | --- | --- |
| `Checksum validation failed` | Bytes tải về khác expected checksum | Repository/mirror/proxy cache, artifact và checksum sidecar |
| `Checksum failure` | Strict policy đã chặn dữ liệu không hợp lệ | Xác nhận nguồn chính và xử lý mismatch, không hạ policy |
| `Checksum not available` / missing | Không nhận được expected checksum | Server publish, sidecar/headers, proxy path, checksum policy |
| `Could not find artifact ...` | Artifact không tồn tại tại repo/version được chọn | GAV, version, releases/snapshots enabled, repository URL |
| `401 Unauthorized` | Chưa có credentials hoặc credentials sai | `settings.xml` servers, ID, repo manager permissions |
| `403 Forbidden` | Bị cấm truy cập | ACL, token scopes, mirror/repository permissions |
| `407 Proxy Authentication Required` | Proxy yêu cầu xác thực | Proxy settings, mạng doanh nghiệp |
| `Unknown host` / DNS error | Không phân giải hostname | URL, DNS, VPN, mạng |
| TLS/PKIX handshake error | TLS trust/chain/certificate vấn đề | JDK truststore, CA, endpoint cert; không bỏ TLS validation |
| Timeout / connection reset | Network hoặc server bị ngắt | Kết nối, proxy, repository status, retry có kiểm soát |
| `maven-metadata.xml` không tải được | Metadata index/version/snapshot lỗi | Repository metadata/proxy cache, updatePolicy |
| `.lastUpdated` liên quan artifact | Resolver ghi thông tin caching của lần resolution thất bại | GAV/URL, loại lỗi cached, thời điểm update; không tự kết luận mismatch |
| SHA mismatch ở một máy, máy khác OK | Local cache/mirror/route khác nhau hoặc artifact không nhất quán | So sánh URL thực, hash, settings, cache |
| `Unsupported checksum algorithm` | Resolver/transport/config kỳ vọng thuật toán không hỗ trợ | Maven/Resolver version, checksum algorithms, cấu hình server |

**Log thực tế có thể khác hẳn cách viết trong bảng**, tùy Maven 3/4, Resolver transport, plugin và server. Không chẩn đoán chỉ bằng một từ `checksum`; đọc **URL, artifact GAV, loại file, repository ID, nguyên nhân gốc**.

### 8.1. `.lastUpdated` có phải checksum bị hỏng?

Không. Maven Resolver có cơ chế **cache kết quả resolution lỗi**. Với một số lỗi *not found*, nó có thể tạo file `.lastUpdated` trong local repository để ghi trạng thái truy vấn trước. Thông tin đó **không phải** checksum file và không tự chứng minh artifact có byte bị hỏng.

Ở Maven 3, lỗi loại artifact not found thường được cache theo policy; lỗi transfer/network có quy tắc caching khác. Vì vậy kiểm tra chính xác **dòng lỗi gốc** trước khi xóa bất kỳ cache nào.

### 8.2. Missing artifact và missing checksum dễ bị nhầm

Giả sử Maven thử tải:

```text
https://repo.example.org/maven/public/org/example/lib/1.2.3/lib-1.2.3.jar
https://repo.example.org/maven/public/org/example/lib/1.2.3/lib-1.2.3.jar.sha1
```

Đây là **URL minh họa**. Nếu URL thứ hai 404 nhưng URL JAR đầu vẫn trả đủ bytes, đó là tình huống **checksum sidecar không có**. Nếu URL JAR đầu 404, đó là **artifact không có**, không phải “checksum mismatch”. Chính sách fail/warn/ignore có thể quyết định điều gì xảy ra với expected checksum bị thiếu, nhưng không tự tạo artifact không tồn tại.

### 8.3. Release bị ghi đè là tín hiệu đáng chú ý

Nếu một release version `1.2.3` đã được cache trước đó nhưng repository bỗng trả JAR khác dưới **cùng GAV**, hãy điều tra khả năng deploy overwrite, lỗi proxy cache hoặc publisher compromise. Trong mô hình quản lý artifact hiện đại, **release immutable** là thực hành đáng ưu tiên. Không chỉ chọn `warn` để chấp nhận hai bản `1.2.3` khác nhau.

## 9. Runbook xử lý checksum mismatch theo thứ tự an toàn

### Bước 1 — Ghi nhận sự kiện đủ thông tin

Từ log Maven ghi lại:

- Maven/JDK version: `mvn -version`.
- Lệnh thật và flags: `-C`, `-c`, `-U`, `-o`, `-s`, profiles.
- Project/module và tọa độ artifact: `groupId:artifactId:version:type`.
- Đường dẫn remote thực tế, repository ID và mirror ID nếu có.
- File bị lỗi: JAR, POM, plugin, BOM hay `maven-metadata.xml`.
- Checksum được **mong đợi** và checksum **tính được** nếu log cung cấp; không chia sẻ secrets.

**Không đăng toàn bộ debug log** lên issue công khai nếu nó chứa token, URL nội bộ hoặc thông tin xác thực.

### Bước 2 — Xác minh Maven đang dùng repository nào

Kiểm tra:

```bash
mvn -version
mvn help:effective-settings
mvn help:effective-pom -Doutput=effective-pom.xml
```

Những goal Help Plugin có thể cần resolve plugin trước; nếu chính plugin đó gặp checksum error, Help Plugin cũng có thể không chạy. Khi đó đọc trực tiếp `settings.xml`, POM, parent, `.mvn/maven.config` và log sẵn có.

Xác định:

- Project `<repositories>` và `<pluginRepositories>`.
- User/global `settings.xml` và các profile đang active.
- Mirrors với `<mirrorOf>` đang thay thế repository URL.
- Release/snapshot `enabled` và `checksumPolicy` hiệu lực.
- Repository manager đang proxy Maven Central hay đang serve artifact nội bộ.
- Quyền truy cập và TLS của endpoint.

**Nhớ:** repository URL trong POM không nhất thiết là endpoint thực sự nếu đang có mirror.

### Bước 3 — Phân loại lỗi trước khi thay đổi

Kiểm tra có phải:

1. **Mismatched checksum**: cùng file được nhận nhưng hash khác giá trị server.
2. **Missing checksum**: server không cung cấp expected hash.
3. **Missing artifact**: URL chính trả 404.
4. **Auth/network/TLS**: không tải file đúng cách.
5. **Metadata/cache stale**: dùng metadata hoặc cached failure không còn phản ánh remote.
6. **Artifact version không nhất quán**: bản release bị ghi đè hoặc snapshot metadata chưa đồng bộ.

Chỉ trường hợp 1 và 2 trực tiếp thuộc vấn đề checksum policy. Các trường hợp khác có thể cùng xuất hiện nhưng cần cách khắc phục khác.

### Bước 4 — Kiểm tra nguồn xuất bản và mirror/proxy cache

Với repository nội bộ:

- Kiểm tra bản phát hành gốc trên repository manager có artifact và checksum tương ứng.
- Đối chiếu hash của **artifact gốc** với hash **artifact proxy đang trả**.
- Kiểm tra lần deploy/upload có bị cắt ngang hoặc bị overwrite không.
- Với snapshot, xác minh metadata timestamped, POM/JAR/checksum có cùng một lần publish hợp lệ.
- Nếu proxy cache trả artifact cũ nhưng checksum mới, cần **invalidate cache tại proxy** theo quy trình của admin, không chỉ sửa POM.
- Nếu repository server không phát hành checksums, sửa cấu hình publish của server/deploy plugin và chính sách kho; **đừng tự hạ policy trên clients**.

Maven Central có thể là nguồn được proxy qua Nexus/Artifactory hoặc công cụ khác. Nếu người dùng có mirror, việc Central gốc đang khỏe **không chứng minh** mirror/cache trong công ty khỏe.

### Bước 5 — Loại trừ local cache mà không phá các dự án khác

Để so sánh với local repo hiện tại, chạy build **chỉ trên cache thử nghiệm riêng**:

```bash
mvn -B -C -Dmaven.repo.local=.m2-checksum-diagnostic clean verify
```

Nếu kết quả khác cache cũ, có thể có metadata/artifact đã cache hoặc khác biệt origin. Cần tiếp tục đối chiếu URL, artifact bytes và Resolver tracking trước khi khẳng định đã xác định nguyên nhân.

Nếu artifact cụ thể trong cache bị xác nhận hỏng, chỉ **quản lý/xóa mục đúng tọa độ** bằng quy trình được chấp thuận, sau khi bảo đảm không có build khác đang sử dụng, rồi tải lại từ repository đã sửa. Không làm theo kiểu:

```text
Không khuyến nghị:
  Xóa toàn bộ ~/.m2/repository
  Xóa toàn bộ repository manager cache
  Sửa nội dung .jar/.pom hoặc .sha1 bằng tay để ép checksum khớp
```

Local repository có thể dùng locking và layout nâng cao; thao tác thủ công có thể phá đồng bộ giữa các process. Tốt nhất dùng cache riêng cho chẩn đoán, hoặc công cụ quản lý artifact phù hợp.

### Bước 6 — Chạy lại strict sau khi sửa nguồn

```bash
mvn -B -C -U clean verify
```

`-U` có thể làm Maven kiểm tra lại snapshot/updates và một số cached-failure situations theo quy tắc version; nó **không sửa checksum sai trên server**. Nếu mismatch vẫn còn, tiếp tục xử lý nguồn/proxy. Nếu build thành công bằng cache riêng nhưng cache cũ thất bại, xác minh vì sao cache cũ khác thay vì đổi toàn bộ hệ thống sang `ignore`.

Chỉ công bố đã giải quyết khi:

- Lỗi checksum **không còn** dưới strict policy trên một **nguồn và cache được kiểm soát**.
- Artifact/version và repository origin đúng dự kiến.
- Unit/integration/build checks thành công sau thay đổi.
- Không còn workaround tạm kiểu `-c` hoặc `checksumPolicy=ignore` bị quên trong pipeline.

## 10. Lệnh hash thủ công dùng để điều tra (không thay Maven Resolver)

Nếu đã có bản artifact **được phép** kiểm tra trên đĩa, bạn có thể tính hash để so sánh. Các lệnh dưới đây chạy **trên file có thật**, không tự tải artifact và không xác minh nguồn gốc publisher.

### Linux

```bash
sha256sum path/to/artifact.jar
sha1sum path/to/artifact.jar
```

### macOS

```bash
shasum -a 256 path/to/artifact.jar
shasum -a 1 path/to/artifact.jar
```

### Windows PowerShell

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath ".\path\to\artifact.jar"
Get-FileHash -Algorithm SHA1 -LiteralPath ".\path\to\artifact.jar"
```

Nếu repository phát hành checksum SHA-1, cần so **SHA-1 với SHA-1** của đúng bytes; đừng so hash SHA-256 với file `.sha1` rồi kết luận mismatch. Kết quả khác có thể vì lấy nhầm version, file được sửa hoặc response proxy không nhất quán. Nếu artifact chứa dữ liệu nội bộ, không upload nó lên dịch vụ kiểm tra hash bên ngoài khi chưa được phép.

### 10.1. Hash bằng Java 17

Trong ví dụ ở mục 7, Java:

```java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
byte[] bytes = "abc".getBytes(StandardCharsets.UTF_8);
String hex = HexFormat.of().formatHex(digest.digest(bytes));
```

Đây là **fragment** đã xuất hiện trong chương trình Java hoàn chỉnh. Nó minh họa nguyên lý tính digest. Ở thực tế, khi tính hash của file lớn, hãy dùng streaming bytes thay vì đọc toàn bộ file vào RAM; Maven Resolver tự thực hiện quy trình transport/integrity riêng.

### 10.2. Không “chữa” bằng cách tự sửa sidecar checksum

Nếu bạn tự viết `.sha1` mới cho một artifact đang hỏng để cho hash khớp, điều đó **không khôi phục được artifact đúng**. Nó chỉ biến “dữ liệu bất thường + checksum cũ” thành “dữ liệu bất thường + checksum vừa tạo”. Để bảo đảm integrity, cần so với bản **đúng từ nguồn tin cậy**, hoặc triển khai lại artifact chuẩn có chữ ký/quy trình được duyệt.

## 11. Tùy chọn nâng cao: trusted checksums

Checksum đi kèm dữ liệu từ **cùng remote repository** bảo vệ một phần sự cố truyền tải, nhưng không đủ để bảo vệ nếu repository **và checksum** cùng bị thay thế.

Maven Resolver có cơ chế **Expected/Trusted Checksums** cho các trường hợp cần **nguồn checksum tin cậy độc lập**. Ý tưởng:

1. Team giữ danh sách checksum expected của artifact ở nguồn được quản lý và kiểm soát thay đổi.
2. Maven Resolver tính checksum từ artifact đã nhận hoặc local bytes.
3. Resolver so khớp với danh sách **trusted**, thay vì chỉ tin checksum được server truyền cùng artifact.
4. Chính sách có thể fail khi mismatch hoặc khi checksum required bị thiếu, tùy cấu hình.

Ví dụ tài liệu Resolver mô tả option:

```text
-Daether.artifactResolver.postProcessor.trustedChecksums.failIfMissing=true
```

Đây là **một setting của trusted-checksum post-processor**, **không đủ để tự bật một hệ thống trusted checksums hoàn chỉnh**. Cần cấu hình source, thuật toán, dữ liệu checksum và tính tương thích Resolver theo tài liệu phiên bản đang chạy. Không chèn riêng dòng này vào build rồi tuyên bố mọi dependency đã được xác thực.

**Khi nào cần?** Các môi trường yêu cầu kiểm soát supply chain chặt, build nhạy cảm, artifact pinning hay repository bên thứ ba. Với project bình thường, bước đầu đáng giá vẫn là **HTTPS + repository manager đáng tin + strict checksum + releases immutable + CI logs**.

## 12. Một số bẫy vận hành và bảo mật

### 12.1. Maven có thể dùng cache; strict không đồng nghĩa quét toàn kho

Một build `mvn -C verify` có thể không tải một dependency vốn đã cache. Khi không diễn ra transport cho file đó, không nên mặc định nó luôn được đối chiếu với checksum mới từ remote. Maven Resolver có cơ chế kiểm tra local bytes trong một số ngữ cảnh, nhưng không có bảo đảm đơn giản kiểu “`-C` quét toàn bộ `~/.m2` trước mỗi build”.

Nếu đang điều tra artifact nghi bị hỏng, dùng **local repo kiểm thử mới** hoặc cơ chế trusted checksums; không dựa chỉ vào thành công của lần chạy sử dụng cache cũ.

### 12.2. Proxy có thể làm xuất hiện checksum mismatch dù source đúng

Repository proxy cache có thể giữ version artifact và checksum từ **hai thời điểm publish khác nhau**, nhất là nếu release bị overwrite. Do đó:

- Hỏi admin repository manager về khả năng invalidation/resync **đúng artifact**.
- So sánh origin và proxy bằng dữ liệu được phép truy cập.
- Kiểm tra policy chặn overwrite release và cấu hình snapshots.
- Không tắt strict trên clients để né một lỗi hạ tầng có thể ảnh hưởng toàn nhóm.

### 12.3. Lỗi SSL, credentials và checksum là các lớp khác nhau

- Lỗi TLS certificate cần kiểm tra truststore/CA, endpoint, JDK và proxy, **không tắt TLS validation**.
- Lỗi 401/403 cần cấu hình `servers`/credentials ID và quyền truy cập, **không sửa checksumPolicy**.
- Lỗi 404 của artifact cần kiểm tra GAV/URL/release snapshot policy, **không sửa checksumPolicy**.
- Checksum mismatch cần kiểm tra bytes và hash nguồn, **không sửa mật khẩu một cách vô căn cứ**.

### 12.4. Metadata và sidecar lỗi có thể che một vấn đề khác

`maven-metadata.xml` giúp Maven chọn snapshot timestamp, các versions hiện có và plugin metadata. Nếu metadata stale hoặc không tương ứng với files thật, lỗi có thể xuất hiện như artifact missing, metadata download warning hoặc checksum mismatch. Đừng kết luận ngay “JAR hỏng” khi **file được đề cập trong log là metadata**.

### 12.5. Một lỗi checksum không phải CVE scan

`checksumPolicy` không kiểm tra thư viện có lỗ hổng bảo mật, thư viện vi phạm license, bị thay đổi API hay publisher có đáng tin không. Một JAR có checksum hợp lệ vẫn có thể chứa mã độc **nếu nguồn checksum/artifact bị xâm nhập**. Tách các kiểm soát: artifact integrity, provenance/signatures, vulnerability scanning, dependency version pinning, SBOM và runtime testing.

## 13. Cách viết cấu hình cho team: CI, dev và repository manager

### 13.1. CI: giữ strict

Một pipeline tối giản:

```bash
mvn -B -C clean verify
```

Khi có môi trường cache riêng:

```bash
mvn -B -C -Dmaven.repo.local=.m2-ci-cache clean verify
```

Trên CI thật, nên gắn cache với workspace và chính sách cache key/locking của runner. Các công cụ pipeline có thể cung cấp Maven repository path sẵn; đừng buộc mọi runner dùng cùng một đường dẫn tùy tiện.

### 13.2. Developer: giữ khả năng chẩn đoán

Trong quá trình phát triển:

```bash
mvn -C clean test
```

Nếu lỗi, thử:

```bash
mvn -C -e clean test
mvn -C -X clean test
```

`-X` giúp xem repository/mirror resolution nhưng có thể in log rất dài. Không share log chứa dữ liệu nhạy cảm mà chưa kiểm tra.

### 13.3. Repository manager: sửa đúng nguồn

Admin cần bảo đảm:

- Release publish nhất quán và bất biến; snapshot metadata phù hợp.
- Artifact/POM/metadata/checksum được ghi và phục vụ đồng bộ.
- Mirror/proxy cache không trả file từ nhiều bản publish không khớp.
- HTTPS và quyền truy cập được cấu hình đúng.
- Trường hợp không cung cấp checksum thì có quy trình cập nhật server thay vì yêu cầu clients tắt kiểm tra.

**Một policy client nghiêm ngặt không thể thay thế kho phục vụ dữ liệu đúng.** Chỉ khi cả client và server được cấu hình có trách nhiệm thì integrity mới đáng tin.

## 14. Hỏi đáp và tình huống thực tế

### Tình huống 1: `checksumPolicy=fail`, nhưng một repository không có `.sha1`

**Phân tích:** Nếu Resolver không nhận được checksum expected bằng bất kỳ cách hỗ trợ nào, strict policy có thể dừng resolution. Tuy nhiên **không thấy file `.sha1` qua trình duyệt chưa đủ** để kết luận checksum hoàn toàn không tồn tại, vì transport có thể cung cấp checksum theo cách khác.

**Hành động:** xem log Maven/Resolver, xác minh checksum response/source, repository publishing policy; làm việc với admin repo. Không tự đổi fail sang ignore.

### Tình huống 2: `mvn package` OK, `mvn -C package` lỗi

**Phân tích:** Có khả năng default/warn policy đã cho tiếp tục khi artifact/checksum không đạt, còn strict flag chặn. Tuy nhiên cũng phải xem **đúng artifact nào được tải ở hai lần**, vì cache/updatePolicy và profile có thể khiến các lần chạy không tương đương.

**Hành động:** ghi lại Maven version, URLs, local repo, flags, hash expected/actual; dùng cache thử nghiệm khi cần để đối chiếu.

### Tình huống 3: CI chỉ fail trên máy khác

**Phân tích:** CI có thể dùng mirror, settings, JDK hoặc local repo khác. Cùng `pom.xml` không bảo đảm cùng đường tải artifact.

**Hành động:** so sánh `help:effective-settings`, mirror IDs, `-C`, repository policies, local cache và URLs thực tế trước khi thay đổi POM.

### Tình huống 4: Một release version bị thay bytes nhưng `.sha1` chưa đổi

**Phân tích:** Đây là mismatch đúng nghĩa. Không được tạo lại checksum bằng bản JAR mới nếu chưa xác minh bản nào là artifact đúng và ai được quyền đổi release.

**Hành động:** kiểm tra repository audit log, publisher, immutable release policy và bản artifact chuẩn; phục hồi từ nguồn tin cậy hoặc phát hành version mới.

### Tình huống 5: Metadata snapshot stale gây 404

**Phân tích:** Có thể Maven nhận metadata chỉ đến snapshot build đã bị dọn hoặc chưa replicate, rồi trả 404 cho JAR tương ứng. Không có cơ sở cho rằng lỗi bắt nguồn từ checksum của JAR.

**Hành động:** đồng bộ lại metadata và storage ở repository manager, xác định updatePolicy và clean cache có phạm vi nếu cần.

### Tình huống 6: Cảnh báo checksum khi build plugin, không phải dependency

**Phân tích:** Maven phải resolve cả plugins và dependencies. Nếu log chỉ `maven-compiler-plugin`, vấn đề có thể nằm ở plugin repository hoặc mirror được cấu hình.

**Hành động:** kiểm tra `<pluginRepositories>` và mirror/effective settings, không chỉ `<repositories>` trong POM.

### Tình huống 7: Tải qua HTTPS rồi còn cần checksum?

**Phân tích:** HTTPS bảo vệ transport giữa client và endpoint TLS; checksum phát hiện một số sai hỏng/không nhất quán của artifact được phục vụ và cache. Nhưng cả hai đều không thay thế publisher signature/trusted checksum nếu server bị kiểm soát.

**Hành động:** dùng kết hợp HTTPS, strict checksums, immutable releases, và kiểm soát trusted provenance khi cần.

## 15. Checklist điều tra checksum failure

- [ ] Xác định Maven/JDK version, lệnh và flags thật (`-C`, `-c`, `-U`, `-o`, `-s`).
- [ ] Phân biệt file bị lỗi là **JAR**, **POM**, **plugin** hay **metadata**.
- [ ] Ghi đúng artifact GAV, repository/mirror ID và URL đã tải.
- [ ] Phân biệt **missing checksum**, **mismatch**, **missing artifact**, mạng/TLS/auth và metadata stale.
- [ ] Kiểm tra chính sách `<releases>`/`<snapshots>` của repository tương ứng.
- [ ] Xem POM, settings và các active profiles, nhất là mirror doanh nghiệp.
- [ ] Không tin rằng `checksumPolicy=warn` hoặc `BUILD SUCCESS` xác nhận integrity.
- [ ] Không thay sang `ignore` để làm build qua lỗi mà chưa điều tra.
- [ ] So hash **cùng thuật toán** của file nguồn/proxy/client khi cần, không so nhầm SHA-1 và SHA-256.
- [ ] Không tự ghi lại sidecar checksum của artifact nghi hỏng để ép match.
- [ ] Kiểm tra repository manager publish/overwrite/replication và cache đồng bộ.
- [ ] Dùng local repository thử nghiệm riêng thay vì xóa toàn bộ `~/.m2/repository`.
- [ ] Sau khi sửa nguồn, chạy strict `mvn -B -C clean verify` trên cache và endpoint được kiểm soát.
- [ ] Với CI nhạy cảm, cân nhắc trusted checksums/chữ ký số cùng provenance/SBOM kiểm soát supply chain.
- [ ] Ghi lại root cause và hành động khắc phục, không chỉ tình trạng lệnh Maven thành công.

## 16. Tự kiểm tra kiến thức

**Câu 1.** `checksumPolicy` có ba giá trị nào?  
**Đáp án:** `fail`, `warn`, `ignore`. `fail` chặn khi thiếu/sai checksum theo policy; `warn` cảnh báo; `ignore` bỏ kiểm tra.

**Câu 2.** `-C` và `-c` khác nhau thế nào?  
**Đáp án:** `-C` yêu cầu checksum nghiêm ngặt, fail khi mismatch; `-c` ở chế độ cảnh báo.

**Câu 3.** Có đúng file `.jar.sha1` cạnh `.jar` là bằng chứng artifact có nguồn gốc đáng tin không?  
**Đáp án:** Không. Hash có thể giúp kiểm tra integrity; nếu cùng nguồn bị sửa cả artifact và checksum, cần chữ ký/trusted checksums/provenance độc lập.

**Câu 4.** `updatePolicy=always` có thay thế `checksumPolicy=fail` không?  
**Đáp án:** Không. Update policy quyết định khi nào kiểm tra cập nhật, còn checksum policy quyết định xử lý dữ liệu sai/thiếu hash.

**Câu 5.** Vì sao `mvn -C -o verify` không thể chứng minh mọi artifact đã so lại với remote checksum mới?  
**Đáp án:** Offline không truy cập remote, có thể dùng cache; strict không tự cam kết quét toàn bộ cached artifacts theo nguồn độc lập.

**Câu 6.** POM dùng Maven Central nhưng log cho biết URL repository nội bộ. Tại sao?  
**Đáp án:** `settings.xml` có thể có mirror hoặc repository profile thay đổi nguồn thực tế.

**Câu 7.** Checksum mismatch trên `.pom` có thể làm build fail trước compile không?  
**Đáp án:** Có. Maven phải đọc POM parent/BOM/dependency và plugin metadata để dựng build model.

**Câu 8.** File `.lastUpdated` trong local repository luôn có nghĩa checksum sai?  
**Đáp án:** Không. Resolver dùng nó để cache thông tin những lần resolution thất bại; phải đọc loại lỗi gốc.

**Câu 9.** Nếu proxy trả artifact cũ và checksum mới, sửa thế nào?  
**Đáp án:** Điều tra/invalidate proxy cache đúng artifact và nguồn publish; không hạ `checksumPolicy`.

**Câu 10.** Có nên đổi chính sách trên mọi project thành `ignore` để tránh cảnh báo checksum từ repo công ty?  
**Đáp án:** Không. Cần sửa repository publishing, checksum sidecars/headers hoặc proxy consistency; `ignore` che lỗi.

**Câu 11.** Nếu repository không trả checksum nhưng bạn muốn `fail`, bạn nên làm gì trước?  
**Đáp án:** Kiểm tra cách Resolver lấy expected checksums, cấu hình server và quy trình xuất bản; chuẩn hóa repository cung cấp checksums tin cậy.

**Câu 12.** Vì sao demo Java tính SHA-256 của `"abc"` không chứng minh Maven thực sự tải sai JAR?  
**Đáp án:** Java demo chỉ minh họa hash comparison ở dữ liệu nội bộ; chính Maven Resolver và `-C` mới kiểm tra artifact repository trong quá trình resolve.

## 17. Tài liệu chính thức và tham khảo

1. [Apache Maven — Settings Reference: repositories, releases/snapshots và checksumPolicy](https://maven.apache.org/settings.html)
2. [Apache Maven — POM Reference: repository checksumPolicy](https://maven.apache.org/pom.html)
3. [Apache Maven Embedder — CLI Options Reference (`-C`, `-c`)](https://maven.apache.org/ref/3.9.5/maven-embedder/cli.html)
4. [Apache Maven Resolver — Checksums](https://maven.apache.org/resolver/about-checksums.html)
5. [Apache Maven Resolver — Expected/Trusted Checksums](https://maven.apache.org/resolver/expected-checksums.html)
6. [Apache Maven Resolver — RepositoryPolicy API](https://maven.apache.org/resolver/apidocs/org/eclipse/aether/repository/RepositoryPolicy.html)
7. [Apache Maven Resolver — Local Repository and Error Caching](https://maven.apache.org/resolver/local-repository.html)
8. [Apache Maven — Guide to Multiple Repositories](https://maven.apache.org/guides/mini/guide-multiple-repositories.html)
9. [Apache Maven — Using Mirrors for Repositories](https://maven.apache.org/guides/mini/guide-mirror-settings.html)
10. [Apache Maven — Guide for Resolver Transport](https://maven.apache.org/guides/mini/guide-resolver-transport.html)
11. [Sonatype — Maven: The Complete Reference, Downloading and Verifying Dependencies](https://www.sonatype.com/maven-complete-reference/running-maven)

**Kết luận:** `checksumPolicy` điều khiển phản ứng của Maven trước checksum **thiếu hoặc không khớp**. Với build quan trọng, ưu tiên **`fail`/`-C`**, đồng thời duy trì repository và proxy nhất quán. Khi gặp lỗi, sửa **nguồn bytes/checksum hoặc cache có phạm vi**, không dùng `warn`/`ignore` như giải pháp lâu dài để chấp nhận artifact chưa được xác minh.
