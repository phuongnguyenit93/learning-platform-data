# Quản lý phiên bản, URL phân phối và checksum của Wrapper

## Mục tiêu và bối cảnh

Trong chủ đề **Java và Wrapper** của Spring Boot Build Tooling Packaging, `Wrapper` là bộ script/cấu hình để cả lập trình viên lẫn CI chạy **đúng phiên bản công cụ build mà dự án lựa chọn**. Với Maven, ta thường gọi `./mvnw`; với Gradle là `./gradlew`. Bài học này tập trung vào ba việc phải được quản lý đồng bộ: **phiên bản**, **URL phân phối (distribution URL)** và **checksum SHA-256**.

Sau bài học, bạn cần có thể xác định Maven/Gradle thực chạy phiên bản nào, đọc được `distributionUrl` và `distributionSha256Sum`, hiểu sự khác nhau giữa ZIP công cụ build và Wrapper JAR, thay đổi phiên bản một cách kiểm chứng được, rồi chẩn đoán lỗi tải/checksum mà không nhầm với lỗi Java hoặc Spring Boot.

**Điểm cốt lõi:** Wrapper quản lý phiên bản **Maven/Gradle**; `pom.xml` hoặc `build.gradle[.kts]` quản lý build; Java toolchain/JDK quản lý Java; Spring Boot parent/plugin quản lý phiên bản Spring Boot. Bốn loại phiên bản này liên quan về tương thích, nhưng không phải một giá trị.

## 1. Cơ chế Wrapper: từ script đến bản phân phối

```text
Lập trình viên / CI
    |
    +---- ./mvnw hoặc mvnw.cmd
    |              |
    |              +--> .mvn/wrapper/maven-wrapper.properties
    |                         |
    |                         +--> distributionUrl (Maven ZIP)
    |                         +--> distributionSha256Sum (SHA-256 ZIP)
    |
    +---- ./gradlew hoặc gradlew.bat
                   |
                   +--> gradle/wrapper/gradle-wrapper.properties
                              |
                              +--> distributionUrl (Gradle ZIP)
                              +--> distributionSha256Sum (SHA-256 ZIP)
```

Script Wrapper tìm bản phân phối công cụ build đã được tải hoặc tải từ `distributionUrl` khi cần. Khi cơ chế checksum được hỗ trợ, nó so giá trị SHA-256 đã ghim với byte của bản ZIP mới tải. Sau bước chuẩn bị công cụ, Maven/Gradle mới thực hiện các công việc như đọc dependency, chạy test, biên dịch và đóng gói Spring Boot.

Điều này giúp giảm sai lệch kiểu **máy A dùng Maven 3.x, máy B dùng Maven phiên bản khác** hoặc **CI dùng một bản Gradle khác với máy phát triển**. Nhưng Wrapper **không tự cài JDK phù hợp**, không tự làm Spring Boot tương thích với mọi Gradle/Maven và không xác minh tất cả dependency của ứng dụng.

### Những tệp liên quan

| Maven Wrapper | Gradle Wrapper | Vai trò |
| --- | --- | --- |
| `mvnw`, `mvnw.cmd` | `gradlew`, `gradlew.bat` | Script khởi động Wrapper trên Unix/macOS và Windows |
| `.mvn/wrapper/maven-wrapper.properties` | `gradle/wrapper/gradle-wrapper.properties` | URL, checksum và thông tin bản phân phối |
| `.mvn/wrapper/maven-wrapper.jar`, nếu có | `gradle/wrapper/gradle-wrapper.jar` | Chương trình Wrapper; Maven `only-script` có thể không dùng JAR |
| `pom.xml` | `build.gradle` / `build.gradle.kts` | Khai báo plugin, dependency và cách build |

Nên commit bộ Wrapper chuẩn vào Git để người khác chạy cùng phiên bản. Không commit thư mục cache tải xuống như `~/.gradle/wrapper/dists` hoặc `~/.m2/wrapper/dists`. Tệp JAR/script được commit vẫn là mã thực thi nên phải được review khi thay đổi.

## 2. `distributionUrl` là nơi pin phiên bản công cụ

`distributionUrl` trỏ tới **tệp ZIP bản phân phối Maven/Gradle cụ thể**. Hãy đọc đủ ba phần: **host**, **phiên bản**, **kiểu ZIP**.

Ví dụ Maven:

```properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.11/apache-maven-3.9.11-bin.zip
```

Đây là ZIP của **Maven 3.9.11** từ host Maven Central chính thống. Phiên bản nằm trong cả đoạn đường dẫn lẫn tên ZIP. Đây là một **ví dụ phiên bản cố định**, không phải chỉ thị nâng mọi dự án lên 3.9.11.

Ví dụ Gradle:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.14.3-bin.zip
```

Đây là ZIP của **Gradle 8.14.3** với kiểu `bin`. Gradle có kiểu `-all.zip` bổ sung nguồn và tài liệu; **ZIP `bin` và ZIP `all` khác nhau**, ngay cả khi cùng phiên bản, nên checksum không thể dùng thay cho nhau. Ký tự `\://` là cách escape dấu hai chấm trong tệp Java properties do Gradle sinh ra.

**Quy tắc đọc URL:** dùng HTTPS, một phiên bản và tên ZIP xác định; kiểm tra domain chính thức hoặc mirror được tổ chức kiểm soát. Một URL chứa `latest`, SNAPSHOT thay đổi thường xuyên, hoặc đường dẫn trỏ tới máy chủ không rõ nguồn khiến khả năng lặp lại và kiểm chứng yếu đi. Mirror nội bộ phải được xác minh rằng artifact được đưa vào khớp bản phát hành chính thức. HTTPS bảo vệ kênh truyền, nhưng không thay cho checksum của nội dung.

### Vì sao không đổi mỗi chuỗi phiên bản?

Ví dụ đổi `gradle-8.14.3-bin.zip` sang `gradle-8.14.3-all.zip` nhưng giữ checksum cũ sẽ khiến xác minh thất bại khi bản `all` được tải mới. Đổi Maven `3.9.11` thành một bản khác cũng tương tự: phải cập nhật **cả URL lẫn checksum của ZIP mới**.

Tăng phiên bản Spring Boot trong POM/build script **không đồng nghĩa** Wrapper tự nâng Maven/Gradle. Ngược lại, nâng Gradle/Maven cũng có thể cần cập nhật JDK, plugin hoặc build script để tương thích.

## 3. SHA-256 và `distributionSha256Sum`

SHA-256 là hàm băm tạo chuỗi **64 ký tự hex** từ byte của tệp. Hai ZIP có nội dung khác nhau gần như chắc chắn tạo digest khác nhau. `distributionSha256Sum` là checksum kỳ vọng cho **toàn bộ ZIP tại `distributionUrl`**, không phải cho thư mục giải nén, `build.gradle`, `pom.xml` hay dependency Java.

```text
distributionUrl --> tải ZIP cụ thể ----> SHA-256(ZIP vừa tải)
                                                |
distributionSha256Sum ----------------------> so sánh
                                                |
                           trùng: tiếp tục / khác: dừng vì không tin ZIP
```

Một checksum chỉ hữu ích khi được lấy từ **nguồn đáng tin cậy độc lập với bản tải cần kiểm tra**: trang release chính thức, tệp checksum/chữ ký được xác thực, kho artifact nội bộ đã thẩm định. Không nên tải tệp từ host không đáng tin rồi lấy SHA-256 của chính tệp đó và ghim vào properties: lúc đó bạn chỉ xác nhận nó không đổi so với tệp đã nghi ngờ.

**Phân biệt giới hạn:** checksum bảo vệ tính toàn vẹn của ZIP được ghim, không đảm bảo tính an toàn tuyệt đối của mã nguồn công cụ, không kiểm tra tính đúng của ứng dụng, và không thay thế review mã/script build.

### Lấy checksum từ đâu?

- **Gradle:** https://gradle.org/release-checksums/ công bố SHA-256 của mỗi bản ZIP `-bin`/`-all` và cả Gradle Wrapper JAR. Phải chọn **đúng phiên bản và kiểu ZIP**.
- **Maven:** xem thông tin phát hành/chữ ký hoặc checksum của Apache Maven; tài liệu Maven Wrapper hỗ trợ `distributionSha256Sum`. Một số nguồn phát hành Apache ưu tiên SHA-512: có thể xác minh artifact bằng checksum/chữ ký phát hành, sau đó **tự tính SHA-256 của ZIP đã xác thực** để ghim vào Wrapper.
- Với mirror nội bộ, đối chiếu artifact mirror với upstream bằng một quy trình tin cậy **trước khi** cho các máy khác tải nó.

Đừng dán chuỗi SHA-512 (128 ký tự hex) vào trường SHA-256 (64 ký tự hex); cũng đừng dán giá trị có tiền tố `sha256:` hoặc kèm tên tệp vào properties.

## 4. Maven Wrapper: phiên bản Maven và phiên bản Wrapper là hai thứ khác nhau

Một cấu hình Maven Wrapper **kiểu `script`** minh họa đầy đủ cặp URL–checksum:

```properties
# .mvn/wrapper/maven-wrapper.properties
wrapperVersion=3.3.4
distributionType=script
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.11/apache-maven-3.9.11-bin.zip
distributionSha256Sum=0d7125e8c91097b36edb990ea5934e6c68b4440eef4ea96510a0f6815e7eeadb
wrapperUrl=https://repo.maven.apache.org/maven2/org/apache/maven/wrapper/maven-wrapper/3.3.4/maven-wrapper-3.3.4.jar
wrapperSha256Sum=4e2fbf6554bc8a4702cdfdd3bef464f423393d784ddbb037216320ce55d5e4e1
```

Các giá trị SHA-256 cụ thể ở đây tương ứng với **Maven 3.9.11 ZIP** và **Maven Wrapper JAR 3.3.4**. Chúng chỉ đúng cho đúng hai artifact được nêu; không dùng lại cho phiên bản khác. Trong dự án thực, kiểu Wrapper có thể khác và tệp này có thể chỉ chứa vài thuộc tính.

| Thuộc tính | Công dụng |
| --- | --- |
| `distributionUrl` | Chọn ZIP và **phiên bản Maven thực chạy** |
| `distributionSha256Sum` | SHA-256 mong đợi của **Maven ZIP** |
| `wrapperVersion` | Phiên bản phần mềm **Maven Wrapper**, không phải Maven |
| `distributionType` | Cách chạy Wrapper: `only-script`, `script`, `bin`, `source` |
| `wrapperUrl` | URL tải `maven-wrapper.jar` khi kiểu Wrapper cần JAR |
| `wrapperSha256Sum` | SHA-256 kỳ vọng của **Maven Wrapper JAR được tải** |

**Điểm khác biệt của `only-script`:** đây là kiểu mặc định trong nhiều phiên bản Maven Wrapper hiện đại. Script tự xử lý việc tải Maven, không yêu cầu `maven-wrapper.jar`. Vì vậy thiếu JAR có thể hoàn toàn bình thường; `wrapperSha256Sum` không có ý nghĩa xác minh JAR khi kiểu Wrapper không dùng JAR. Đừng tự đổi kiểu để ép có JAR.

Ngược lại, ở kiểu cần tải JAR như `script`, `wrapperUrl` và `wrapperSha256Sum` có thể bảo vệ **bản Wrapper JAR được tải**. Đó là checksum **khác** với `distributionSha256Sum` bảo vệ Maven ZIP. Nếu JAR đã nằm trong Git, hãy kiểm tra tính toàn vẹn của nó so với nguồn phát hành đáng tin, không chỉ dựa vào dòng properties.

### Nâng Maven được Wrapper sử dụng

Theo tài liệu Apache Maven Wrapper, trên môi trường **đã tin cậy và có Maven** có thể yêu cầu cài/đổi phiên bản công cụ qua plugin:

```bash
mvn -N wrapper:wrapper -Dmaven=3.9.11
```

Đây là lệnh minh họa với **phiên bản mục tiêu 3.9.11**, không bắt buộc dùng phiên bản này. Nếu dự án có cấu hình Wrapper riêng, task/plugin có thể ghi lại script và properties khác với ví dụ. Sau lệnh, hãy xem diff của `mvnw`, `mvnw.cmd`, `.mvn/wrapper/`, cập nhật checksum chính thức của **Maven ZIP mục tiêu** và, nếu đổi Wrapper JAR, checksum đúng của JAR mục tiêu. Apache cũng cho phép sửa `distributionUrl` để chuyển bản Maven, nhưng khi làm phải thay cặp URL–checksum cùng nhau.

Đừng nhầm `-Dmaven` với `wrapperVersion`: tham số đầu tiên chọn phiên bản **Maven**; trường thứ hai nói về **Maven Wrapper**.

## 5. Gradle Wrapper: phiên bản, checksum ZIP, nơi lưu cache

Ví dụ tệp Gradle Wrapper được cấu hình cho **Gradle 8.14.3 `bin`**:

```properties
# gradle/wrapper/gradle-wrapper.properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-8.14.3-bin.zip
distributionSha256Sum=bd71102213493060956ec229d946beee57158dbd89d0e62b91bca0fa2c5f3531
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
```

Digest `bd71102213493060956ec229d946beee57158dbd89d0e62b91bca0fa2c5f3531` khớp checksum **được Gradle công bố cho gradle-8.14.3-bin.zip**. Đường dẫn kiểm tra: https://gradle.org/release-checksums/. Với ZIP `all` của cùng phiên bản, digest là một giá trị **khác**.

| Thuộc tính Gradle | Nghĩa |
| --- | --- |
| `distributionUrl` | Host, bản Gradle, tên/kiểu ZIP |
| `distributionSha256Sum` | SHA-256 của ZIP khi tải mới và xác minh |
| `distributionBase`, `distributionPath` | Nơi đặt bản Gradle đã giải nén |
| `zipStoreBase`, `zipStorePath` | Nơi lưu ZIP được tải |
| `networkTimeout` nếu có | Thời gian chờ khi Wrapper kết nối để tải |

Các giá trị `GRADLE_USER_HOME` và `wrapper/dists` là **đường dẫn cache**, không phải version hoặc URL. `gradle/wrapper/gradle-wrapper.jar` là chương trình Wrapper được chạy trước khi tải ZIP; checksum của tệp JAR này **không được `distributionSha256Sum` xác minh**.

### Nâng Gradle qua task `wrapper`

Khi checkout/Wrapper hiện tại đã được kiểm tra và dự án hỗ trợ Gradle đích, ví dụ cú pháp cập nhật:

```bash
./gradlew wrapper --gradle-version 8.14.3 --distribution-type bin --gradle-distribution-sha256-sum bd71102213493060956ec229d946beee57158dbd89d0e62b91bca0fa2c5f3531
```

Trên Windows PowerShell, dùng `.\gradlew.bat wrapper` và giữ các tham số phía sau. Đây là **ví dụ cách gọi**, không có nghĩa 8.14.3 là bản phù hợp nhất với mọi dự án. Khi đổi phiên bản, nếu Gradle thấy `distributionSha256Sum` cũ nhưng task không cung cấp digest mới phù hợp, task `wrapper` có thể từ chối chạy; đừng xóa checksum để né lỗi.

Sau lần cập nhật properties, Gradle khuyến nghị trong tình huống nâng bản **chạy lại task `wrapper` với phiên bản Gradle mới** để cập nhật đầy đủ `gradle-wrapper.jar` và các script khi cần. Hãy xem diff `gradle-wrapper.properties`, `gradle-wrapper.jar`, `gradlew`, `gradlew.bat`; xác minh SHA-256 Wrapper JAR theo danh sách chính thức, kiểm tra lệnh phiên bản và build trước khi commit.

Một cách làm sai là chỉnh mỗi `distributionUrl` trong file rồi cho rằng mọi tệp Wrapper đã được cập nhật. URL quyết định bản Gradle tải về; JAR/script Wrapper thuộc một lớp khác và có thể cần cập nhật riêng khi nâng cấp.

## 6. Cần kiểm tra hai thứ: ZIP công cụ và chương trình Wrapper

Hãy phân biệt rõ hai mục tiêu bảo vệ:

**A. Bản phân phối công cụ build (ZIP).** `distributionSha256Sum` nhằm phát hiện ZIP được tải không khớp byte kỳ vọng. URL chính thống mà checksum sai vẫn là lỗi; checksum đúng cho một ZIP khác vẫn là lỗi.

**B. Chương trình tải/khởi động (Wrapper JAR và script).** Gradle JAR thường đã được commit và chạy trước khi so checksum ZIP; cần so SHA-256 của JAR với danh sách phát hành chính thức hoặc dùng quy trình kiểm tra Wrapper JAR trong CI. Với Maven, `wrapperSha256Sum` hỗ trợ JAR được Wrapper tải trong kiểu phù hợp; `only-script` không có JAR để kiểm tra nhưng chính các script vẫn cần review. Một kẻ xấu có thể thay đồng thời URL và checksum trong cùng PR; vì vậy **code review và nguồn checksum độc lập** vẫn thiết yếu.

### Giới hạn cache

Tài liệu Gradle nêu rõ rằng `distributionSha256Sum` được kiểm tra khi Wrapper cần **tải bản phân phối mới**. Nếu bản Gradle đã tồn tại hợp lệ trong cache, lượt chạy tiếp theo có thể bỏ qua tải và không tính lại checksum của ZIP. Vì vậy chạy `./gradlew --version` thành công sau khi sửa checksum **không đủ chứng minh** checksum vừa được kiểm tra lại. Muốn kiểm chứng đường tải/checksum, hãy dùng môi trường mới hoặc thư mục cache riêng, thay vì phá cache chung của đồng nghiệp.

Maven Wrapper cũng có nhiều kiểu và phiên bản thực thi; cơ chế xác minh cụ thể phụ thuộc kiểu đang dùng. Đừng mặc định mọi phiên bản script Maven Wrapper cũ đều xử lý checksum hệt nhau.

### Tự tính và đối chiếu checksum ZIP

Sau khi lấy đúng `gradle-8.14.3-bin.zip` từ nguồn tin cậy, có thể tính SHA-256 bằng:

```bash
# Linux
sha256sum gradle-8.14.3-bin.zip

# macOS
shasum -a 256 gradle-8.14.3-bin.zip
```

```powershell
# Windows PowerShell
(Get-FileHash .\gradle-8.14.3-bin.zip -Algorithm SHA256).Hash.ToLowerInvariant()
```

Kết quả SHA-256 cho đúng ZIP Gradle ở ví dụ phải là:

```text
bd71102213493060956ec229d946beee57158dbd89d0e62b91bca0fa2c5f3531
```

So **đủ 64 ký tự**, không chỉ vài chữ đầu. Đối với Maven ZIP, cách tính hash tương tự, chỉ thay đúng tên tệp. Nếu nguồn Apache cung cấp SHA-512, hãy kiểm tra/đối chiếu theo hướng dẫn phát hành trước khi tự tính SHA-256 để pin; không tự thay digest bằng hash của tệp vừa tải đáng ngờ.

## 7. Quy trình quản lý thay đổi từ đầu đến cuối

1. **Đọc cấu hình hiện tại.** Ghi lại `distributionUrl`, `distributionSha256Sum`, kiểu Wrapper, tệp JAR/script; chạy `./mvnw -v` hoặc `./gradlew --version` trên một checkout đã tin cậy để biết bản công cụ đang dùng.
2. **Chọn phiên bản mục tiêu và kiểm tra tương thích.** Spring Boot/plugin, JDK dùng bởi Gradle/Maven, các task và CI có thể đặt yêu cầu riêng. Không nâng chỉ vì có bản mới hơn.
3. **Lấy bản phát hành chính thức.** Chọn ZIP phiên bản cố định, `bin`/`all` theo nhu cầu; quyết định URL chính thức hay mirror nội bộ đã thẩm định.
4. **Tìm checksum độc lập của đúng ZIP.** Với Gradle, dùng trang checksum phát hành; với Maven, dùng thông tin phát hành/chữ ký/chứng thực của Apache và cơ chế wrapper tương ứng.
5. **Cập nhật Wrapper bằng công cụ tin cậy.** Maven dùng Maven Wrapper Plugin hoặc sửa URL đúng hướng dẫn; Gradle dùng task `wrapper` với phiên bản và SHA-256 đã xác thực. Cập nhật checksum JAR riêng nếu Wrapper JAR thay đổi.
6. **Xem lại tất cả thay đổi trong Git.** Kiểm tra chính xác URL, digest, phiên bản JAR/script, tên host và các tệp phát sinh; review cả script vì đó là mã chạy trước build.
7. **Xác minh từ môi trường mới/cache riêng.** Test download + kiểm tra SHA-256, rồi chạy `-v`/`--version` để xác nhận phiên bản công cụ thực tế.
8. **Thử một lệnh kiểm thử và build.** Với Maven: `./mvnw test`, `./mvnw package`; với Gradle: `./gradlew test`, `./gradlew build`. Chạy lệnh tương ứng với build system của repo, không bắt buộc cả hai.
9. **Ghi thay đổi rõ trong commit/PR.** Nêu bản cũ → mới, URL, nguồn checksum, lý do, kiểm thử và chi tiết wrapper JAR/script đổi. CI phải dùng Wrapper của repo để tôn trọng phiên bản đã ghim.

Lệnh nhanh cho dự án Maven hoặc Gradle:

```bash
# Chạy từ thư mục gốc dự án Maven tin cậy
./mvnw -v
./mvnw test

# Hoặc, nếu đây là dự án Gradle
./gradlew --version
./gradlew test
```

Trên Windows PowerShell, thay bằng `.\mvnw.cmd -v` / `.\mvnw.cmd test` hoặc `.\gradlew.bat --version` / `.\gradlew.bat test`. Nếu shell Unix báo `Permission denied` vì thiếu quyền thực thi trên script đã tin cậy, kiểm tra bit executable trước khi sửa.

## 8. Chẩn đoán vấn đề thường gặp

| Hiện tượng | Kiểm tra | Xử lý |
| --- | --- | --- |
| `distributionSha256Sum` không khớp | Có đổi phiên bản/kiểu ZIP? Mirror trả đúng tệp? Digest đúng nguồn? | Dừng dùng ZIP đó, kiểm tra lại URL và digest từ nguồn chính thức; không ghim hash của tệp đang nghi ngờ. |
| HTTP 404 khi Wrapper tải | Đường dẫn/phiên bản ZIP không tồn tại, mirror chưa đồng bộ | Xác nhận URL phát hành chính thức và phiên bản hợp lệ. |
| Lỗi TLS/chứng thư/proxy | Cấu hình mạng, chứng thư tin cậy của JDK/máy, proxy doanh nghiệp | Sửa kết nối/chứng thư đúng cách; không tắt xác minh TLS. |
| `gradlew --version` vẫn chạy khi vừa sửa checksum sai | Bản phân phối Gradle đã có trong cache | Dùng môi trường mới/cache riêng để chứng minh việc tải và so SHA-256. |
| Maven không có `maven-wrapper.jar` | `distributionType=only-script` có thể cố ý không dùng JAR | Đọc `distributionType`, đừng tự coi là mất file. |
| Wrapper JAR Gradle đổi không rõ lý do | JAR có thể bị thay đổi hoặc sinh bởi phiên bản khác | So hash JAR với https://gradle.org/release-checksums/ và xem diff cùng lý do thay đổi. |
| `./mvnw -v` khác `mvn -v` | Wrapper và Maven cài toàn cục là hai lựa chọn độc lập | Kiểm tra `distributionUrl`; dùng Wrapper theo dự án. |
| `./gradlew --version` khác `gradle --version` | Wrapper và Gradle cài toàn cục khác phiên bản | Dùng Wrapper, tránh phụ thuộc môi trường máy. |
| Build lỗi "Java version" dù checksum đúng | Java/JDK, phiên bản Gradle/Maven, plugin hoặc Spring Boot không tương thích | Kiểm tra `java -version`, JDK được IDE/CI chọn, ma trận tương thích. |
| Test/build lỗi sau khi Wrapper tải đúng | Lỗi dependency, plugin, cấu hình ứng dụng hoặc mã | Phân loại lỗi build sau bước tải, không gán nhầm cho checksum. |

### Đọc diff để phát hiện lỗi

```diff
-distributionUrl=https\://services.gradle.org/distributions/gradle-8.14.3-bin.zip
+distributionUrl=https\://services.gradle.org/distributions/gradle-8.14.3-all.zip
 distributionSha256Sum=bd71102213493060956ec229d946beee57158dbd89d0e62b91bca0fa2c5f3531
```

Dòng checksum còn nguyên **thuộc bản `bin.zip`**, trong khi URL mới là `all.zip`: cần lấy đúng checksum chính thức của `all.zip` (hoặc quay về `bin.zip` nếu không định đổi loại). Việc chỉ sửa URL mà giữ checksum không tạo thành một cập nhật Wrapper hợp lệ.

Ngay cả nếu URL lạ và checksum mới khớp với tệp ở URL đó, vẫn cần kiểm tra nguồn phân phối và lý do đổi host. Một digest hợp lệ về mặt phép tính **không tự chứng minh** artifact được cấp bởi tổ chức phát hành.

## 9. Thực hành kiểm chứng

Dùng một dự án Spring Boot do Spring Initializr tạo, chọn **Maven hoặc Gradle** và làm các việc sau:

1. Xác định chính xác đường dẫn `*wrapper.properties` và danh sách script/JAR Wrapper trong repo. Chỉ ra phiên bản công cụ từ `distributionUrl`.
2. Tách URL thành host, phiên bản, tên tệp và kiểu ZIP. Phân biệt phiên bản công cụ này với phiên bản Java và Spring Boot của dự án.
3. Kiểm tra có `distributionSha256Sum` hay không. Nếu thiếu, tìm checksum của đúng ZIP ở nguồn phát hành đáng tin, **không tự bịa 64 ký tự hex**.
4. Nếu là Maven, xác định `distributionType` và xem `wrapperSha256Sum` có thể áp dụng ở đâu. Nếu là Gradle, giải thích vì sao checksum ZIP không xác minh `gradle-wrapper.jar`.
5. Chạy `./mvnw -v` hoặc `./gradlew --version` từ một checkout đã tin cậy; ghi rõ phiên bản và JDK được dùng.
6. Trong nhánh thực hành, chọn một phiên bản mục tiêu **tương thích**, cập nhật URL và checksum thành một cặp, xem diff Wrapper, thử trên cache riêng, chạy `test` và `build`.
7. Trình bày bằng lời: tại sao cache khiến kiểm tra checksum không nhất thiết diễn ra ở mọi lần chạy, và tại sao checksum do chính cùng người thay URL cung cấp vẫn cần review độc lập?

**Tiêu chí hoàn thành:** nêu đúng phiên bản công cụ chạy thực tế, URL ZIP và SHA-256 tương ứng; có bằng chứng cách chọn/kiểm tra digest; biết phân biệt checksum ZIP với JAR/script và lỗi build sau khi tải.

## Tài liệu gốc để đối chiếu

- Apache Maven Wrapper: https://maven.apache.org/tools/wrapper/
- Maven Wrapper Plugin, mục tiêu sinh/cập nhật Wrapper: https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/wrapper-mojo.html
- Gradle Wrapper: https://docs.gradle.org/current/userguide/gradle_wrapper.html
- Gradle security và các giới hạn xác minh: https://docs.gradle.org/current/userguide/securing_build_tool.html
- SHA-256 ZIP và Wrapper JAR chính thức của Gradle: https://gradle.org/release-checksums/

Những giá trị phiên bản/checksum trong ví dụ dùng để **giải thích cấu trúc và thao tác kiểm chứng**. Với dự án thật, phải tra phiên bản, URL và digest của **chính artifact mục tiêu**, đồng thời kiểm tra tương thích trước khi cập nhật.
