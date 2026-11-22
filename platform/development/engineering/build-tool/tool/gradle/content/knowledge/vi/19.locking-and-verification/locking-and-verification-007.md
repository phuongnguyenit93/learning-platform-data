# Xử lý lỗi xác minh mà không vô hiệu hóa kiểm tra toàn cục trong Gradle

## Mục tiêu bài học

Gradle **dependency verification** giúp phát hiện thư viện, plugin hoặc metadata bị thay đổi so với checksum/chữ ký mà build chấp nhận. Một lỗi xác minh không chỉ là vấn đề “thiếu cấu hình để build chạy”: có thể là dependency mới hợp lệ, lỗi mirror, cache hỏng, publisher thay bytes dưới cùng version, hoặc một sự cố supply chain. **Không sửa lỗi của một artifact bằng cách tắt xác minh cho toàn bộ build.**

Sau bài này, bạn có thể:

1. Phân biệt **checksum missing**, **checksum mismatch**, **PGP untrusted key**, **key unavailable**, **invalid signature** và lỗi mạng/repository không thuộc verification.
2. Đọc báo cáo Gradle để xác định chính xác **group:name:version**, filename, configuration, repository, expected/actual checksum và fingerprint của key.
3. Hiểu **gradle/verification-metadata.xml**, phạm vi toàn build, verify-metadata, verify-signatures, strict/lenient/off.
4. Tạo metadata bằng **--write-verification-metadata sha256** và **sha256,pgp**, review diff, xác minh từ nguồn độc lập và không tin máy móc những hashes mới sinh.
5. Thêm hash chính xác cho một artifact; dùng **also-trust** chỉ khi cả hai biến thể bytes thật sự được chứng minh hợp lệ.
6. Tin đúng PGP key theo phạm vi phù hợp, phân biệt public key trong **keyring** với **trusted-key**, sử dụng **--refresh-keys**, **--export-keys**.
7. Hiểu trường hợp bất thường cần **ignored-key + SHA-256 đã kiểm chứng** mà không bỏ bảo vệ những artifact khác.
8. Thực hành lỗi checksum trên một **Maven repository cục bộ** có chương trình Java 17 runnable; khôi phục strict mà không chuyển sang off.
9. Vận hành CI với checklist điều tra, ghi nhận bằng chứng, review XML và gỡ exception khi không cần.

Ví dụ dùng Gradle **Groovy DSL**, Java **17+** và Gradle Wrapper. Nội dung Markdown này là bài học độc lập; các GAV **demo:** do người học tự tạo, không phải dependencies ngoài Internet.

## 1. Checksum, signature và artifact provenance

Một module Maven thường có:

~~~text
org/example/engine/1.0/
├── engine-1.0.pom
├── engine-1.0.jar
├── engine-1.0.module         (nếu publisher phát hành)
├── engine-1.0.jar.asc       (nếu publisher ký)
└── engine-1.0.pom.asc       (nếu publisher ký POM)
~~~

**POM/Gradle Module Metadata** có thể chứa các dependency bắc cầu. Vì vậy metadata cũng phải được kiểm tra: một POM bị thay có thể kéo mã lạ vào graph dù JAR chính vẫn giữ nguyên. Gradle verification còn áp dụng với plugin artifacts và các tệp tải qua cơ chế dependency management.

### 1.1. Checksums giải quyết vấn đề nào?

**SHA-256** băm bytes của một tệp. Khi build khai báo SHA-256 của file và Gradle tính ra giá trị khác, **file hiện tại khác với bản đã được chấp nhận**.

Điều này chưa cho biết ngay nguyên nhân. Có thể là:

- Cache download bị lỗi.
- Mirror trả POM có whitespace hoặc timestamp khác.
- Publisher đăng lại JAR dưới cùng tọa độ/version.
- Repository lạ đứng trước và shadow module chính thức.
- Một tệp bị sửa có chủ ý hoặc tấn công chuỗi cung ứng.

Checksum **không tự xác nhận publisher**. Nếu bạn tính hash của file độc hại rồi lưu nó làm giá trị chuẩn, Gradle sẽ xác minh thành công file độc hại trong các lần sau. Bởi vậy, **nguồn độc lập và bước review khi thêm hash** là cốt lõi.

### 1.2. PGP signature khác với SHA-256

PGP sử dụng **chữ ký trên file** và public key. Nó kiểm tra bytes có khớp chữ ký từ private key tương ứng không. Nhưng:

- Chữ ký hợp lệ không chứng minh người giữ key có quyền publish module đó.
- Tên/email trong public key có thể do bất kỳ người tạo key nào tự chọn.
- Key trong keyserver chưa mặc nhiên là key chính thức của publisher.
- Key trong local keyring chỉ cung cấp public-key material, không đồng nghĩa key được **trusted** cho mọi module.

Vì thế PGP đúng cần ba khâu: **cryptographic signature check**, **full fingerprint identity verification** và **trust policy giới hạn theo artifact/publisher**.

### 1.3. Scope của verification

Gradle kiểm tra các artifacts được tải qua dependency resolution engine, gồm JAR/ZIP, POM, Ivy descriptors, Gradle Module Metadata, plugin artifacts và transitives. Tài liệu Gradle nêu các ngoại lệ cho **changing dependencies**, đặc biệt SNAPSHOT, và artifacts sản sinh trong chính build. Không được tuyên bố verification thay thế tất cả kiểm tra build output hoặc bảo mật runtime.

## 2. File gradle/verification-metadata.xml

Gradle tự kích hoạt verification khi phát hiện file:

~~~text
PROJECT_ROOT/gradle/verification-metadata.xml
~~~

Một XML khung:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<verification-metadata
    xmlns="https://schema.gradle.org/dependency-verification"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="https://schema.gradle.org/dependency-verification https://schema.gradle.org/dependency-verification/dependency-verification-1.4.xsd">
    <configuration>
        <verify-metadata>true</verify-metadata>
        <verify-signatures>false</verify-signatures>
    </configuration>
    <components/>
</verification-metadata>
~~~

**Đây chỉ là khung, không phải file đủ dùng cho một project có external dependencies.** Vì chưa có checksum, strict build thường thất bại khi tải artifacts. Khi làm việc thật, dùng file sinh bởi Gradle và được review, không thay nguyên file đang có bằng khung.

- **verify-metadata=true** bảo vệ metadata artifacts được resolve.
- **verify-signatures=false** có nghĩa chưa dùng PGP signature verification; SHA-256 đã cấu hình vẫn có thể được Gradle kiểm tra.
- **components** ghi group/name/version, filename và hash/key riêng từng artifact.
- **trusted-keys** mô tả những signing keys được chấp nhận.
- **trusted-artifacts** là cơ chế miễn verification cho matched files và có rủi ro.
- **ignored-keys** loại bỏ các signing keys ở phạm vi đã cấu hình; phải dùng rất hạn chế.

### 2.1. Phạm vi không chỉ là :app

Một file verification metadata áp dụng cho root project, subprojects, **buildSrc** và các trường hợp included build theo quy tắc Gradle. Một plugin mới hoặc thư viện test-only có thể khiến build fail dù implementation dependencies của app không đổi.

Vì đây là cấu hình bảo vệ rộng cho build, **thay đổi trust entries phải được review như một thay đổi bảo mật**, không chỉ là chỉnh lỗi biên dịch.

### 2.2. JAR và POM là hai tệp khác nhau

Ví dụ module **demo:parser:2.0** có:

~~~text
parser-2.0.jar
parser-2.0.pom
~~~

Hash của JAR không thể dùng làm hash POM. Nếu Gradle báo thiếu metadata cho POM, bổ sung checksum POM sau khi xác minh; không tắt verify-metadata chỉ để bỏ qua một POM.

## 3. Modes: strict, lenient, off

| Mode | Hành vi | Có là cách sửa chính không? |
| --- | --- | --- |
| **strict** | Fail khi dependency không đạt verification | **Có**, duy trì mặc định cho CI/release |
| **lenient** | Cảnh báo nhưng vẫn cho build tiếp tục | **Không**, có thể dùng code chưa được tin |
| **off** | Không thực hiện dependency verification | **Không**, làm mất hàng rào bảo vệ |

Lệnh strict:

~~~bash
./gradlew --dependency-verification strict build
~~~

Hoặc trong gradle.properties:

~~~properties
org.gradle.dependency.verification=strict
~~~

Hai lựa chọn **lenient** và **off** không sửa artifact sai. Chúng chỉ thay cách Gradle phản ứng. Một JAR đã bị thay đổi vẫn có thể đi vào compiler, test runner hoặc runtime. **Không commit mode off/lenient vào CI để làm build xanh.**

### 3.1. Không thực hiện những điều sau

- Xóa, đổi tên hoặc bỏ file **verification-metadata.xml**.
- Chuyển toàn build sang off vì một dependency.
- Dùng verify-metadata=false chỉ để qua POM.
- Bỏ verify-signatures toàn build vì một signature sai chưa được điều tra.
- Trust tất cả artifacts thuộc repository hoặc group vì một lỗi cục bộ.
- Thêm actual hash từ error log vào allowed hashes mà không có chứng cứ từ nguồn độc lập.
- Tắt verification trên các configurations chạy code như compileClasspath/runtimeClasspath.

## 4. Đọc và phân loại lỗi trước khi sửa

| Loại lỗi | Dấu hiệu thường gặp | Hành động ưu tiên |
| --- | --- | --- |
| Thiếu checksum | **checksum is missing from verification metadata** | Xác minh artifact mới và thêm hash |
| Checksum mismatch | **expected sha256 ... but was ...** | Điều tra bytes/source; không auto accept |
| Untrusted signing key | **passed verification but key isn't trusted** | Kiểm tra fingerprint/owner, rồi trust scope hẹp |
| Không tải được key | **key wasn't found in any key server** | Keyring, network, keyserver, refresh-keys |
| Signature không khớp | **signature didn't match** | Nghiêm trọng; điều tra publisher, mirror, .asc |
| Không có module/JAR | **Could not find module/artifact** | Sửa publishing/repositories, không phải thêm SHA |
| Lỗi mạng/auth | HTTP 401/403/5xx, timeout | Sửa credentials/proxy/repo |

### 4.1. Triage checklist

Ghi:

1. **Gradle Wrapper/JDK version**.
2. Task và configuration thất bại.
3. **group:name:version** và **artifact filename**, gồm POM/JAR/classifier.
4. Repository phục vụ artifact và repository mà build mong muốn.
5. Expected/actual SHA-256 hoặc key ID/fingerprint.
6. Gần đây ai đổi dependencies, plugin versions, repos, lockfile, XML.
7. Nguồn độc lập có thể xác minh bytes/key.
8. Metadata nào có thể bị lộ qua log, như private repository URL hoặc token.

**Không chia sẻ debug log chưa che secrets** với dịch vụ công khai.

### 4.2. HTML report và verbose console

Gradle thường tạo một **HTML verification report** sau thất bại. Trên CI khó mở HTML, có thể đặt:

~~~properties
org.gradle.dependency.verification.console=verbose
~~~

Property này chỉ thay mức độ chi tiết của báo cáo, **không giảm verification**. Khi cần, dùng **--info** để xem thêm bối cảnh; **--debug** thường rất nhiều output và có thể nhạy cảm.

## 5. Thiếu checksum cho dependency mới

Ví dụ log rút gọn:

~~~text
Dependency verification failed for configuration ':compileClasspath':
On artifact parser-3.0.jar (org.example:parser:3.0):
checksum is missing from verification metadata.
~~~

Đây thường là việc cập nhật dependency hoặc transitive dependency mới, **không tự động kết luận bị tấn công**, nhưng cũng không tự kết luận an toàn.

### 5.1. Quy trình khắc phục đúng

1. Xem graph và xác định dependency/plugin nào kéo module vào.
2. Xác nhận tọa độ, version, repository và publisher chính thức.
3. Lấy SHA-256 qua kênh tin cậy độc lập hoặc signature có fingerprint đã được kiểm chứng.
4. Thêm checksum đúng **component và artifact file** vào XML.
5. Nếu có nhiều artifacts mới, dùng bootstrap để tạo **candidate entries** rồi review.
6. Chạy strict cho những tasks/configurations thực tế cần artifact.
7. Commit diff nhỏ nhất cùng bằng chứng review.

### 5.2. Bootstrap không có nghĩa đã tin artifact

Các lệnh Gradle:

~~~bash
./gradlew --write-verification-metadata sha256 help
~~~

~~~bash
./gradlew --write-verification-metadata sha256 build
~~~

Gradle có thể resolve nhiều configurations và ghi hashes. Tuy nhiên, một custom task chỉ resolve dependency lúc execution có thể khiến **help không đủ bao phủ**; khi đó dùng task thực sự phù hợp.

**Bootstrap đọc bytes đang ở repository.** Nếu nguồn đã bị thay trước bootstrap, Gradle có thể ghi hash của bytes độc hại. Do đó bắt buộc **review changes và chứng minh nguồn**.

### 5.3. Preview mà không overwrite file chính

~~~bash
./gradlew --write-verification-metadata sha256 help --dry-run
~~~

Gradle có thể sinh **verification-metadata.dryrun.xml** để review. Vì dry-run không thực thi các task, nó có thể thiếu artifacts chỉ resolve trong task execution. Không dùng preview làm bằng chứng mọi dependency đã được kiểm tra.

### 5.4. Review XML sau bootstrap

- Chạy **git diff -- gradle/verification-metadata.xml**.
- Xem artifact filenames, các versions và transitive modules mới.
- Đối chiếu SHA được sinh với nguồn publisher/tin cậy.
- Các entries có **origin="Generated by Gradle"** không phải bằng chứng reviewer đã kiểm chứng.
- Khi đã xác minh, có thể ghi **origin="Verified"** và **reason** mô tả quy trình; đây là metadata thông tin, Gradle không dùng chúng làm phép kiểm tra mật mã.
- Review mọi **trusted keys/ignored keys** do bootstrap PGP tự thêm.
- Không chấp nhận một diff rộng khi chỉ thêm một dependency mà chưa giải thích những thay đổi còn lại.

### 5.5. XML entry ví dụ

~~~xml
<component group="antlr" name="antlr" version="2.7.7">
    <artifact name="antlr-2.7.7.jar">
        <sha256
            value="88fbda4b912596b9f56e8e12e580cc954bacfb51776ecfddd3e18fc1cf56dc4c"
            origin="Verified"
            reason="Artifact bytes reviewed against a trusted distribution"/>
    </artifact>
</component>
~~~

Đoạn trên minh họa cấu trúc dựa theo tài liệu Gradle; **không được lấy hash này áp cho artifact khác**. Đây là fragment được thêm vào phần components của XML thực tế, không phải nguyên file.

## 6. Checksum mismatch: ưu tiên điều tra trước sửa

Thông báo có dạng:

~~~text
expected a 'sha256' checksum of '...'
but was '...'
~~~

Gradle đang báo bytes không khớp giá trị đã được phê duyệt. Các nguyên nhân có thể gồm cache lỗi, mirror trả bản khác, publisher republish, nguồn shadowing, hoặc compromise.

### 6.1. Runbook 10 bước

1. Không dùng artifact đáng ngờ để publish/deploy.
2. Lưu GAV, filename, expected/actual, repo và thời gian.
3. So sánh repo order, mirror, local Maven, credentials, content filters.
4. Kiểm tra có release/re-publish chính thức không.
5. Tính SHA-256 độc lập cho file thực tế, nếu được phép.
6. Lấy official checksum/signature từ nguồn publisher đáng tin.
7. Nếu nghi local cache hỏng, thử **Gradle User Home riêng** thay vì xóa toàn bộ cache và mất dấu vết.
8. Nếu mirror cung cấp bytes sai, sửa mirror hoặc routing.
9. Chỉ khi artifact mới được phê duyệt, chỉnh **đúng checksum của đúng file**, có lý do.
10. Chạy lại strict và tests trên môi trường kiểm soát.

### 6.2. Lệnh tính SHA-256

Linux:

~~~bash
sha256sum path/to/library.jar
~~~

macOS:

~~~bash
shasum -a 256 path/to/library.jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath .\path\to\library.jar
~~~

Hash giúp so sánh bytes nhưng **không thay thế xác minh nguồn**: ngay cả file độc hại cũng có hash hợp lệ.

### 6.3. --refresh-dependencies không sửa lỗi trust

~~~bash
./gradlew --dependency-verification strict --refresh-dependencies build
~~~

Flag này yêu cầu tái kiểm tra metadata/artifacts theo cache policy. Nó **không tự cập nhật expected hash**, không nhất thiết tải lại toàn bộ files và không biến file sai hash thành hợp lệ.

### 6.4. also-trust cho hai bản đã kiểm chứng

Khi một POM từ hai repositories có bytes khác nhau nhưng cả hai đã được kiểm chứng là publication hợp lệ, Gradle hỗ trợ nhiều hashes:

~~~xml
<component group="org.apache" name="apache" version="13">
    <artifact name="apache-13.pom">
        <sha256 value="2fafa38abefe1b40283016f506ba9e844bfcf18713497284264166a5dbf4b95e">
            <also-trust value="ff513db0361fd41237bef4784968bc15aae478d4ec0a9496f811072ccaf3841d"/>
        </sha256>
    </artifact>
</component>
~~~

Đây là ví dụ cú pháp từ Gradle, không phải chỉ dẫn chấp nhận hash chưa biết. **Không tự động thêm every actual hash vào also-trust**. Với JAR bị đổi binary dưới cùng GAV, ưu tiên kiểm tra publisher/mirror và release version mới.

## 7. PGP chữ ký hợp lệ nhưng key chưa trusted

Thông báo mẫu:

~~~text
Artifact was signed with key ... and passed verification,
but the key isn't in your trusted keys list.
~~~

Phân biệt:

- **Signature valid**: phép tính PGP khớp.
- **Key trusted**: project đã xác minh quyền ký của key cho artifact.
- **Publisher official**: key fingerprint được xác nhận qua website/release docs chính thức hoặc nguồn tin cậy độc lập.

**Tên/email trong key không đủ.**

### 7.1. Quy trình xác minh key

1. Lấy fingerprint **đầy đủ 40 ký tự hex** cho PGP/trusted-key, không dùng ID ngắn.
2. Đối chiếu với maintainer website, KEYS hoặc release source chính thức.
3. Kiểm tra có key rotation hợp pháp không.
4. Chọn phạm vi trust theo group/name/version/file nhỏ nhất phù hợp.
5. Lưu nguồn và reason trong review.
6. Chạy strict trên artifact và build.

### 7.2. Entry cho một artifact

~~~xml
<component group="com.github.javaparser" name="javaparser-core" version="3.6.11">
    <artifact name="javaparser-core-3.6.11.jar">
        <pgp value="8756c4f765c9ac3cb6b85d62379ce192d401ab61"
             reason="Fingerprint independently verified"/>
    </artifact>
</component>
~~~

Key trên là ví dụ của tài liệu Gradle; **không được mặc nhiên tin key ấy cho các artifacts của dự án thật**.

### 7.3. Giới hạn trusted-keys theo module

Trong phần configuration của XML:

~~~xml
<trusted-keys>
    <trusted-key
        id="8756c4f765c9ac3cb6b85d62379ce192d401ab61"
        group="com.github.javaparser"
        name="javaparser-core"
        reason="Publisher key ownership reviewed"/>
</trusted-keys>
~~~

Các thuộc tính phù hợp có thể gồm **group, name, version, file, regex, origin, reason**. Hạn chế trust đúng publisher/artifact; không đặt fingerprint tin cậy toàn cục chỉ vì một module mới có signature.

## 8. PGP key không tìm được

Lỗi thường nêu **key wasn't found in any key server**. Nguyên nhân có thể là keyserver không hoạt động, firewall/proxy, key chưa được publisher công bố, local keyring thiếu key hoặc Gradle đã cache việc không tìm thấy.

### 8.1. Thử lại khi đã xử lý mạng/keyserver

Gradle có thể cache kết quả key thiếu khoảng **24 giờ**. Lệnh thử lại:

~~~bash
./gradlew --refresh-keys --dependency-verification strict build
~~~

**--refresh-keys không tự tin key**: nó chỉ điều khiển việc refresh public-key lookup. Sau khi tải được key, vẫn cần xác minh fingerprint với publisher.

### 8.2. Dùng public keyring được review

Gradle có thể đọc:

~~~text
gradle/verification-keyring.keys
gradle/verification-keyring.gpg
~~~

Có thể export public keys:

~~~bash
./gradlew --export-keys
~~~

Keyring có ích cho CI mạng hạn chế và giảm lượt gọi keyserver. Nhưng **có key trong keyring không đồng nghĩa được trusted**, vì metadata XML mới quyết định key nào được phép ký artifact nào. Review keyring cùng XML khi commit.

## 9. Signature mismatch: đây không phải chỉ là key thiếu

**Signature didn't match** nghĩa là chữ ký và bytes không tương ứng. Có thể một file .asc sai ở mirror, POM bị rewrite, artifact bị thay, hoặc publisher có vấn đề. Nên dừng dùng artifact cho release và kiểm tra cả original artifact và signature.

### 9.1. Ngoại lệ hẹp khi publisher đã được xác nhận lỗi

Khi **đã độc lập chứng minh bytes đúng nhưng signature publication bị lỗi**, Gradle cho phép ignored key cho **đúng artifact** và thêm checksum được tin:

~~~xml
<component group="com.github.javaparser" name="javaparser-core" version="3.6.11">
    <artifact name="javaparser-core-3.6.11.pom">
        <ignored-keys>
            <ignored-key
                id="379ce192d401ab61"
                reason="Publisher signature mismatch independently investigated"/>
        </ignored-keys>
        <sha256 value="a2023504cfd611332177f96358b6f6db26e43d96e8ef4cff59b0f5a2bee3c1e1"/>
    </artifact>
</component>
~~~

Đây là ví dụ schema từ tài liệu Gradle, không phải phê duyệt ngoại lệ thực tế cho JavaParser. **Nếu chỉ ignore key mà không cung cấp checksum**, Gradle có thể tiếp tục fail vì artifact thiếu cơ chế xác minh tin cậy.

### 9.2. Không ignore cả nhóm vì một POM

Một POM có signature sai không có nghĩa mọi JAR cùng group đều sai. Ngoại lệ rộng làm che những thay đổi không mong muốn. Thích hợp hơn: sửa publisher/mirror, hoặc ignored-key+hash chính xác cho một artifact với owner, reason, review và điều kiện gỡ bỏ.

## 10. Trusted-artifacts và disable verification ở phạm vi hẹp

**trusted-artifacts** làm Gradle **bỏ xác minh** cho file match. Nó có thể nhắm group/name/version/file:

~~~xml
<trusted-artifacts>
    <trust group="demo" name="docs-only" version="1.0"
           file="docs-only-1.0-javadoc.jar"
           reason="Explicitly reviewed exception for a documentation artifact"/>
</trusted-artifacts>
~~~

Dù chỉ trust Javadoc, artifact ấy vẫn không được xác minh; nếu có thể hash, **checksum vẫn tốt hơn**. Không viết:

~~~xml
<trusted-artifacts>
    <trust group="demo"/>
</trusted-artifacts>
~~~

chỉ để sửa một JAR trong group. Đó là exception vượt xa phạm vi lỗi.

Gradle còn có API:

~~~groovy
configurations.named('versionDiscovery') {
    resolutionStrategy.disableDependencyVerification()
}
~~~

**Đây chỉ là ví dụ API** cho configuration đã tồn tại với mục đích khám phá versions chưa biết trước. Nó giảm mức bảo vệ và Gradle cảnh báo. Không dùng ở production compile/runtime/test classpaths hay coi nó là cách xử lý checksum mismatch. Với bài này, **không sử dụng scoped disable**: giải pháp chính là checksum/PGP metadata đúng.

## 11. Lab Java 17 có thể chạy: từ missing checksum tới strict PASS

Lab tạo module Maven **demo:verified-greeting:1.0** hoàn toàn cục bộ bằng Java 17, rồi dùng Gradle verification metadata. Ta gây lỗi có chủ đích bằng cách chỉnh **XML của lab**, không thay artifact thật. Không áp dụng trên build production.

### 11.1. Cây thư mục

~~~text
verification-lab/
├── settings.gradle
├── build.gradle
├── FixtureGenerator.java
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
├── src/main/java/demo/App.java
├── lab-repo/
│   └── demo/verified-greeting/1.0/
│       ├── verified-greeting-1.0.pom
│       └── verified-greeting-1.0.jar
└── gradle/verification-metadata.xml
~~~

**Wrapper** phải do Gradle sinh hoặc lấy từ project tin cậy, không tự tạo JAR Wrapper bằng tay. JDK 17+ và Gradle version tương thích được yêu cầu; chuẩn bị distribution/toolchain có thể cần mạng, còn dependencies fixture không cần Maven Central.

### 11.2. settings.gradle

~~~groovy
rootProject.name = 'verification-lab'
~~~

### 11.3. FixtureGenerator.java

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.jar.JarEntry;
import java.util.jar.JarOutputStream;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public final class FixtureGenerator {
    public static void main(String[] args) throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Requires JDK 17+");
        }

        Path source = Path.of(
                "fixture-build", "src", "demo", "Greeting.java"
        );
        Path classes = Path.of("fixture-build", "classes");
        Files.createDirectories(source.getParent());
        Files.createDirectories(classes);

        String body = """
                package demo;
                public final class Greeting {
                    public static String message() {
                        return "Verified local module";
                    }
                }
                """;
        Files.writeString(source, body, StandardCharsets.UTF_8);

        int exit = compiler.run(
                null, null, null,
                "--release", "17",
                "-d", classes.toString(),
                source.toString()
        );
        if (exit != 0) {
            throw new IOException("javac failed: " + exit);
        }

        Path module = Path.of(
                "lab-repo", "demo", "verified-greeting", "1.0"
        );
        Files.createDirectories(module);

        String pom = """
                <project xmlns="http://maven.apache.org/POM/4.0.0">
                  <modelVersion>4.0.0</modelVersion>
                  <groupId>demo</groupId>
                  <artifactId>verified-greeting</artifactId>
                  <version>1.0</version>
                  <packaging>jar</packaging>
                </project>
                """;
        Files.writeString(
                module.resolve("verified-greeting-1.0.pom"),
                pom,
                StandardCharsets.UTF_8
        );

        try (JarOutputStream jar = new JarOutputStream(
                Files.newOutputStream(
                        module.resolve("verified-greeting-1.0.jar")
                ))) {
            jar.putNextEntry(new JarEntry("demo/Greeting.class"));
            Files.copy(classes.resolve("demo/Greeting.class"), jar);
            jar.closeEntry();
        }

        System.out.println("Generated local Maven module.");
    }
}
~~~

Tệp Java độc lập, có thể biên dịch bằng JDK 17+:

~~~bash
javac FixtureGenerator.java
java FixtureGenerator
~~~

Stdout khi thành công:

~~~text
Generated local Maven module.
~~~

Generator biên dịch **demo.Greeting** và tạo JAR/POM theo Maven layout. **Không chạy lại generator sau khi đã lưu hash** nếu không có lý do, vì timestamps ZIP/JAR có thể thay đổi bytes ngay cả khi mã nguồn tương đương.

### 11.4. build.gradle

~~~groovy
plugins {
    id 'application'
}

repositories {
    maven {
        name = 'localLab'
        url = uri('lab-repo')
    }
}

dependencies {
    implementation 'demo:verified-greeting:1.0'
}

application {
    mainClass = 'demo.App'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

### 11.5. src/main/java/demo/App.java

~~~java
package demo;

public final class App {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
~~~

Trước khi có verification metadata:

~~~bash
./gradlew run
~~~

PowerShell:

~~~powershell
.\gradlew.bat run
~~~

Phần stdout do App in:

~~~text
Verified local module
~~~

Build thành công khi chưa có XML **không phải bằng chứng nó đã xác minh artifact**.

### 11.6. Sinh metadata, review và chạy strict

Chạy:

~~~bash
./gradlew --write-verification-metadata sha256 run
~~~

Tìm trong file sinh **gradle/verification-metadata.xml**:

- **component group=demo name=verified-greeting version=1.0**.
- Artifact **verified-greeting-1.0.pom** và **verified-greeting-1.0.jar**.
- SHA-256 của mỗi file, không nhầm một hash cho hai files.
- Bất kỳ entry khác do build thực sự cần, không có source lạ.

Với lab tự tạo, ta biết artifact được producer nội bộ là chương trình vừa chạy. Với dependency Internet, phải review thêm publisher/hash độc lập.

Chạy lại strict:

~~~bash
./gradlew --dependency-verification strict clean run
~~~

Windows:

~~~powershell
.\gradlew.bat --dependency-verification strict clean run
~~~

Phần stdout mong đợi:

~~~text
Verified local module
~~~

### 11.7. Cố tình tạo lỗi A: missing checksum

Sao lưu hoặc commit bản XML đúng. Tìm component **demo:verified-greeting:1.0** rồi **xóa duy nhất artifact entry cho verified-greeting-1.0.jar**, giữ phần POM và các entries khác nguyên vẹn.

Chạy:

~~~bash
./gradlew --dependency-verification strict clean run
~~~

Gradle phải fail verification vì JAR bị thiếu checksum/trust metadata. Log chính xác tùy version, nhưng sẽ chỉ rõ artifact bị thiếu.

**Sửa:** khôi phục entry JAR từ bản XML đã được review, chạy strict lại. Không tắt verify-metadata hay đổi mode off.

### 11.8. Cố tình tạo lỗi B: SHA-256 sai

Khi XML đã đúng, thay **một ký tự hex** trong SHA-256 của verified-greeting-1.0.jar bằng một ký tự hex khác, giữ 64 chữ số hex. Ví dụ nếu ký tự đầu là **a** đổi thành **b**, nếu là **b** đổi thành **a**. Không sửa JAR/POM.

Chạy strict:

~~~bash
./gradlew --dependency-verification strict clean run
~~~

Gradle phải phát hiện **expected != actual** và fail. **Khôi phục SHA từ bản XML đúng trước khi cố tình sửa**, chạy strict lại; phần App stdout là:

~~~text
Verified local module
~~~

Trong production, không sửa expected chỉ dựa vào actual; cần nguồn độc lập. Lab này cho thấy so khớp checksum hoạt động, không phải quy trình “approve hash” ngoài đời.

### 11.9. Tóm tắt kết quả lab

| Trạng thái | Kết quả |
| --- | --- |
| Không có verification-metadata.xml | Build có thể chạy, chưa bật verification |
| XML có SHA đã review | Strict pass, App chạy |
| Xóa JAR artifact entry | Strict fail vì missing metadata |
| Chỉnh một nibble SHA | Strict fail vì mismatch |
| Khôi phục XML đã review | Strict pass, App chạy lại |

**Không cần dùng lenient hoặc off trong bất kỳ bước nào**.

## 12. PGP bootstrap, keyring và review

Với artifacts có chữ ký từ publisher, có thể tạo metadata:

~~~bash
./gradlew --write-verification-metadata sha256,pgp build
~~~

Gradle có thể tạo trusted-keys hoặc ignored-keys khi bootstrap theo cách tiếp cận lạc quan. **Không auto commit những entries này.** Kiểm tra mọi key fingerprint, scope và hash fallback; đối chiếu publisher website/KEYS.

Một quy trình an toàn hơn cho dependencies quan trọng:

1. Bootstrap SHA-256, xác minh hashes độc lập.
2. Bootstrap PGP, xem các keys và signatures.
3. Giới hạn trust theo publisher group/module/file.
4. Export public keys và commit keyring đã review nếu CI cần.
5. Đảm bảo strict verification trong CI và không tin mọi keys tự động được sinh.

### 12.1. Public keyring không phải trust policy

- **verification-keyring.keys/.gpg** chứa public keys để Gradle kiểm tra signatures.
- **trusted-keys** trong XML quyết định những keys được tin cho artifact.
- **.asc** gắn signature với bytes.
- Website chính thức hoặc nguồn độc lập xác minh quyền sở hữu fingerprint.

Tất cả đều cần thiết trong quy trình PGP nghiêm túc.

## 13. Repository/mirror có thể làm hash khác

Một repository mirror có thể trả POM khác bytes so với Maven Central. Cũng có thể **mavenLocal()** chứa JAR tự publish khác CI. Không nên tự nhận actual hash là hợp lệ khi repo order thay.

Cách điều tra:

1. Xem effective repository list, URL, thứ tự, filters.
2. Xem **mavenLocal()** hoặc flatDir có chứa same-GAV binary không.
3. Xem mirror có rewrite POM hoặc serve stale artifact không.
4. Kiểm tra checksum/signature từ publisher chính thức.
5. Nếu group nội bộ, dùng **exclusiveContent** để chỉ tìm ở private repo.
6. Sửa publisher/mirror/routing rồi chạy lại strict, không mở trust quá rộng.

Ví dụ định tuyến group nội bộ trong **settings.gradle**:

~~~groovy
dependencyResolutionManagement {
    repositories {
        exclusiveContent {
            forRepository {
                maven {
                    url = uri('https://repo.company.example.invalid/releases')
                }
            }
            filter {
                includeGroup('com.company.internal')
            }
        }
        mavenCentral()
    }
}
~~~

URL **.invalid** chỉ để minh họa, không dùng trực tiếp. Exclusive content giảm shadowing, nhưng **không thay thế checksum/PGP verification**.

## 14. Locking, verification và cache

| Cơ chế | Mục tiêu |
| --- | --- |
| Version catalog | Yêu cầu dependencies/versions qua aliases |
| Dependency constraints/platform | Giới hạn version selection trong graph |
| Dependency locking | Giữ selected version đã được ghi |
| Dependency verification | Kiểm tra bytes/chữ ký của artifacts |
| Repository policy | Chỉ định nguồn được phép |
| Dependency cache | Lưu artifacts/metadata tải về |
| Build cache | Lưu task outputs |

Một lockfile ghi **demo:engine:2.0** không tự chứng minh JAR engine 2.0 là bytes đã phê duyệt. Nếu cùng GAV nhưng mirror trả file khác, **locking có thể vẫn chấp nhận version**, còn verification phát hiện hash mismatch. Khi debug, **không sửa lockfile để chữa SHA-256 mismatch**.

## 15. Runbook CI: từng bước không vô hiệu hóa global verification

### 15.1. Triage

- Dừng publish/deploy artifact chưa được xác minh.
- Ghi GAV, filename, task/configuration, repository, expected/actual, fingerprint.
- Lấy HTML report hoặc verbose console.
- Kiểm tra dependency/lock/verification XML diffs gần nhất.
- Chọn đúng loại lỗi: missing, mismatch, key, signature, network.

### 15.2. Xác minh độc lập

- Check publisher/maintainer chính thức, release notes, signed releases/KEYS.
- So SHA-256 từ kênh độc lập với downloaded file.
- So repository order/mirror/proxy/mavenLocal và cache.
- Không dựa vào tên PGP key/email hoặc hash actual duy nhất.
- Nếu nghi compromise, báo bộ phận xử lý sự cố.

### 15.3. Thay đổi nhỏ nhất

- Missing metadata: thêm SHA đúng file đã kiểm chứng.
- Untrusted key: verify full fingerprint rồi trust scope hẹp.
- Key unavailable: keyserver/keyring/refresh-keys.
- Wrong signature: sửa publisher hoặc exception artifact+SHA được review.
- Hai POM được xác nhận hợp lệ: also-trust đúng hashes/file.
- Repo sai: sửa filter/routing trước, không miễn verification mọi artifacts.

### 15.4. QA strict và review

~~~bash
./gradlew --dependency-verification strict clean test
./gradlew --dependency-verification strict build
~~~

Chạy thêm custom tasks có dependency resolution đặc biệt. Sau đó review:

~~~bash
git diff -- gradle/verification-metadata.xml
~~~

Review keyring nếu có. PR nên ghi bằng chứng độc lập, lý do, owner, người review, trường hợp gỡ exception và xác nhận CI strict.

## 16. Troubleshooting nhanh

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Missing checksum sau nâng dependency | Module/metadata mới | Review và thêm hash đúng artifact |
| JAR pass, POM fail | POM cần verified metadata | Hash POM riêng |
| expected khác actual | Mirror/cache/tampering/republish | Điều tra nguồn, không auto trust actual |
| Signature valid nhưng key untrusted | Chưa phê duyệt fingerprint | Verify publisher rồi trust scope hẹp |
| Missing keyserver key | Proxy, keyring, key cache | Refresh-keys/keyring đã xác minh |
| Invalid signature | Sai .asc/POM rewrite/compromise | Giữ strict, điều tra, ngoại lệ cực hẹp nếu cần |
| CI fail local pass | Mode/cache/repository/XML khác nhau | So config, bật strict local |
| Bootstrap sinh ignored-keys lạ | Key không tải được hoặc signature sai | Review từng ignored key |
| Refresh không sửa được lỗi | XML vẫn không chấp nhận artifact | Sửa nguồn/hash đúng |
| Trust cả group làm build xanh | Đã vô hiệu xác minh nhiều artifacts | Thay bằng hash/trust nhỏ nhất |
| HTTP 403 | Lỗi credentials | Sửa auth, không thêm hash |
| Lockfile không đổi mà verification fail | Version không đổi, bytes đổi | Xem checksum/provenance |
| Build chạy ở lenient nhưng strict fail | Đã che lỗi verification | Khôi phục strict, xử lý lỗi gốc |

## 17. Bài tập có đáp án

### Bài 1 — Missing SHA

Library mới **org.example:parser:3.0** thiếu SHA.

**Đáp án:** xác minh publisher/repository và hash thật của JAR/POM, thêm entry đã review vào XML, chạy strict. Không bật off.

### Bài 2 — Expected SHA khác actual

**Đáp án:** nghi bytes đã đổi, không tự cập nhật expected. Check maintainer/mirror/cache và nguồn độc lập; chỉ approve bytes khi có chứng cứ.

### Bài 3 — Signature hợp lệ, key chưa trusted

**Đáp án:** kiểm tra 40-hex fingerprint với publisher, thêm trusted key đúng group/name/file, chạy strict.

### Bài 4 — Key unavailable

**Đáp án:** kiểm tra proxy/keyserver và local keyring, dùng --refresh-keys khi thích hợp, không auto trust bất kỳ key tải được.

### Bài 5 — Sai PGP signature nhưng POM hợp lệ

**Đáp án:** xác minh POM và .asc qua nguồn chính thức. Chỉ khi chứng minh signature publication lỗi mới dùng ignored-key scoped to artifact và SHA đã kiểm chứng, cùng reason.

### Bài 6 — Two POM hashes

**Đáp án:** kiểm tra cả hai thật sự hợp lệ; dùng also-trust cho đúng artifact nếu chứng cứ cho phép; không trust cả repository.

### Bài 7 — Version khóa nhưng JAR bị thay

**Đáp án:** lock giữ version, verification kiểm tra bytes. Lock không thay verification.

### Bài 8 — CI muốn lenient

**Đáp án:** không. Lenient cho artifact chưa đạt tiếp tục đi vào build. Sửa nguyên nhân và giữ strict.

### Bài 9 — Bootstrap tự chứng minh an toàn?

**Đáp án:** không. Bootstrap có thể ghi hash của artifact đã bị thay. Phải review và xác minh độc lập.

### Bài 10 — Một group được trust toàn bộ

**Đáp án:** một exception rộng khiến nhiều artifacts không được verify. Giảm scope tới exact artifact hoặc dùng SHA/PGP.

## 18. Checklist trước khi merge

- [ ] GAV, artifact filename, configuration, repository đã rõ.
- [ ] Phân biệt missing checksum và actual mismatch.
- [ ] Hash/key mới có nguồn kiểm chứng độc lập.
- [ ] POM và JAR được xét riêng.
- [ ] Full fingerprint đã đối chiếu publisher.
- [ ] Keyring và trusted-keys không bị nhầm lẫn.
- [ ] Ignored-key chỉ áp đúng artifact, có checksum tin cậy.
- [ ] also-trust chỉ chứa nhiều hashes đều đã được xác minh.
- [ ] Không có trusted-artifacts quá rộng.
- [ ] Mirror/mavenLocal/repository order đã được xem xét.
- [ ] XML diff được review, không có secret bị lộ.
- [ ] CI/release giữ strict, không dùng off/lenient.
- [ ] Tasks/configurations bị ảnh hưởng đã chạy strict.
- [ ] Có owner và kế hoạch gỡ exception khi upstream sửa.

## Tài liệu chính thức

- [Gradle — Verifying Dependencies](https://docs.gradle.org/current/userguide/dependency_verification.html): cấu trúc XML, SHA-256, PGP, trusted keys, modes, bootstrap và troubleshooting.
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): --dependency-verification, --write-verification-metadata, --refresh-keys, --export-keys.
- [Gradle — Filtering Repository Content](https://docs.gradle.org/current/userguide/filtering_repository_content.html): content filters và exclusiveContent.
- [Gradle — Declaring Repositories](https://docs.gradle.org/current/userguide/declaring_repositories.html): repository definitions, Maven Local, mirrors.
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): khóa selected versions, không thay kiểm tra bytes.
- [Gradle — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html): --refresh-dependencies và cache.

**Kết luận:** Khi Gradle báo dependency verification failed, hãy **giữ strict**, xác định artifact và lý do chính xác, đối chiếu checksum/key từ nguồn đáng tin và thay đổi XML ở phạm vi nhỏ nhất. **Không sửa một lỗi cục bộ bằng cách bỏ xác minh cho toàn build.**