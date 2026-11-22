# Dependency verification bằng checksum và chữ ký trong Gradle

## 1. Mục tiêu: bảo đảm artifact được tải là artifact đã chấp thuận

Khi Gradle resolve một dependency như `org.apache.commons:commons-lang3:3.14.0`, tọa độ `group:name:version` chỉ cho biết **module được yêu cầu**. Nó không tự bảo đảm JAR, POM hoặc plugin tải xuống có đúng bytes đã được nhóm dự án duyệt, cũng không chứng minh ai thực sự ký artifact.

Trong chuỗi cung ứng phần mềm, có nhiều đường gây lỗi:

- Một repository, mirror, proxy hoặc cache bị xâm nhập rồi trả về JAR khác dưới **cùng tọa độ và version**.
- Artifact được publish lại với cùng version nhưng bytes thay đổi; build local và CI nhận kết quả khác nhau.
- Metadata POM/Gradle Module Metadata bị sửa, làm phát sinh **dependency bắc cầu** không mong muốn.
- Plugin hoặc buildscript dependency bị thay đổi trước khi code ứng dụng chạy.
- Một public key được tìm thấy trên key server nhưng **không thuộc publisher dự kiến**, dù chữ ký toán học vẫn hợp lệ.
- Dependency mới chứa lỗ hổng đã công bố, dù artifact đến đúng từ nhà phát hành.

Gradle **Dependency Verification** giải quyết chủ yếu hai vấn đề đầu của tính toàn vẹn và xác thực nguồn ký, bằng cách so sánh **checksum** và/hoặc xác minh **PGP signature** với chính sách được commit vào repository. Nó **không** tự quét CVE, tự sửa library độc hại vốn do đúng publisher phát hành, hoặc thay thế xét duyệt source code.

Sau bài này bạn có thể:

1. Phân biệt checksum SHA-256/SHA-512 và chữ ký PGP, biết mỗi cách bảo vệ điều gì.
2. Tạo `gradle/verification-metadata.xml` từ một build Java 17 chạy được.
3. Hiểu `--write-verification-metadata sha256`, `pgp,sha256`, cách bootstrap và review trust-on-first-use.
4. Thiết lập trusted public keys, keyring, key servers và fallback checksum.
5. Đọc lỗi thiếu metadata, sai checksum, signature untrusted hoặc mismatch, biết xử lý an toàn.
6. Áp dụng ở Gradle multi-project, plugins, CI và phân biệt với dependency locking/Wrapper verification.
7. Duy trì policy chặt chẽ khi nâng versions, thay repositories hoặc thêm transitives.

**Nguyên tắc quan trọng:** câu hỏi không phải “artifact có cùng tên/phiên bản không?” mà là “bytes và người ký artifact có khớp nguồn tin cậy đã được xác thực độc lập không?”.

## 2. So sánh checksum, chữ ký và kiểm tra lỗ hổng

| Cơ chế | Dữ liệu kiểm tra | Bảo đảm chính | Không bảo đảm |
| --- | --- | --- | --- |
| **SHA-256/SHA-512 checksum** | Digest mong đợi của **bytes artifact** | File nhận được không đổi so với giá trị hash đã chấp thuận | Ai tạo file; publisher có đáng tin; không có CVE |
| **PGP signature** | Chữ ký `.asc` và public key phù hợp | File được ký bằng private key tương ứng public key; kiểm tra integrity theo thuật toán chữ ký | Public key tự động là của publisher mong đợi; không có mã độc |
| **Dependency locking** | Phiên bản/module được chọn khi resolve graph | Giữ selected versions ổn định giữa các lần build | Cùng version có cùng bytes; đúng người phát hành |
| **Vulnerability scanning** | Module/version, database advisories | Phát hiện một số rủi ro đã biết (CVE/advisory) | Bytes không bị tráo; không tồn tại lỗ hổng chưa biết |
| **Trusted repository + content filtering** | Nguồn truy cập module/GAV | Giảm rủi ro dependency confusion, repository shadowing | Repository hoàn toàn không thể bị xâm nhập |

**Checksum bảo vệ integrity nhưng không tự tạo authenticity.** Nếu bootstrap bằng cách lấy hash của một file đã bị thay trước đó, Gradle sẽ bảo vệ **chính file độc hại ấy** ở các lần sau. Vì vậy nguồn của checksum ban đầu phải được xem xét.

**PGP signature ràng buộc artifact với một cặp khóa**, không ràng buộc tự động khóa với tổ chức. Nếu attacker tự tạo key có tên “Official Team”, ký artifact rồi đăng key lên server, việc signature “valid” chỉ chứng minh đúng key đã ký. Bạn phải **xác minh fingerprint qua kênh chính thức độc lập** và giới hạn phạm vi trust.

**Nên dùng cả hai** khi có thể: checksum SHA-256/SHA-512 mạnh cho integrity; trusted PGP fingerprint cho provenance. Khi publisher không cung cấp signature, dùng **checksum đã kiểm chứng** làm fallback. Chữ ký dùng hash yếu vẫn có thể có giá trị kiểm tra khóa, nhưng không thay cho hash mạnh của file.

## 3. Phạm vi Gradle thực sự xác minh

Khi một build có `gradle/verification-metadata.xml` hợp lệ, Gradle tự kích hoạt dependency verification cho những artifact được resolve qua **dependency management engine**, chẳng hạn:

- JAR, ZIP và các binary artifacts tải từ Maven/Ivy repositories.
- POM, Ivy descriptor và Gradle Module Metadata khi `verify-metadata` được bật.
- Dependencies bắc cầu, không chỉ các dòng `implementation(...)` trực tiếp.
- **Gradle plugins** được resolve qua plugin repositories, bao gồm plugins ở settings.
- `buildscript` classpath và nhiều plugin/advanced configurations.
- Dependencies của root project, subprojects và `buildSrc` trong phạm vi build.

Trong **composite/included builds**, tài liệu Gradle quy định **verification metadata của build hiện tại** được dùng cho resolution; verification file riêng của included build có thể bị bỏ qua khi included. Khi thêm một included build, cần review những dependencies mới mà nó kéo theo.

**Các giới hạn phải nhớ:**

1. Gradle **không áp dụng dependency verification với changing dependencies**, đặc biệt các version `SNAPSHOT` mà tài liệu nêu, hoặc artifacts được sinh local bởi build (ví dụ JAR vừa compile).
2. File local `files("libs/local.jar")` không phải artifact tải qua external dependency resolution cùng mô hình checksum metadata; muốn kiểm soát vendor JAR local phải có quy trình checksum/provenance riêng hoặc publish nó thành module đúng chuẩn.
3. Cơ chế này **không xác minh Gradle distribution do Wrapper tải trước khi Gradle chạy**. Dùng `distributionSha256Sum` trong `gradle/wrapper/gradle-wrapper.properties` và xác minh `gradle-wrapper.jar` riêng.
4. Không tự xác minh mọi binary được tải bởi `curl`, `wget`, `ProcessBuilder` hoặc một task plugin tự viết đi ngoài Gradle dependency management. Những đường tải đó cần policy riêng.
5. Không phát hiện lỗ hổng bảo mật trong **nội dung hợp lệ** của artifact; cần thêm kiểm tra SCA/SBOM và test.
6. Nếu chỉ bootstrap những configuration đã được resolve tại thời điểm đó, có thể **bỏ sót dependency chỉ resolve trong task action hoặc đường code ít chạy**; phải kiểm thử đủ các task/workflows.

## 4. File chính sách `gradle/verification-metadata.xml`

Gradle tìm file tại **root của build**:

```text
my-gradle-project/
├── settings.gradle.kts
├── build.gradle.kts
├── gradle/
│   ├── verification-metadata.xml
│   ├── verification-keyring.keys   (nếu dùng PGP và keyring ASCII)
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── gradlew
└── gradlew.bat
```

Khi file `verification-metadata.xml` tồn tại, Gradle tự bật kiểm tra; **không cần thêm plugin đặc biệt** trong `plugins { }`. Một file XML tối thiểu theo schema Gradle:

```xml
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
```

**Đây là skeleton hợp lệ để hiểu cấu trúc, không phải policy sẵn dùng:** `<components/>` chưa có checksum nên build có external dependencies sẽ fail ở chế độ strict. Thay vì cố tự điền một giá trị digest giả, hãy chạy bootstrapping để Gradle tạo phần `<components>` gồm `group`, `name`, `version`, tên artifacts và checksum theo file đã resolve.

### 4.1. Cấu trúc các entry sau khi bootstrap

Giả sử Gradle sinh metadata cho artifact `example-lib-1.0.jar`, ý nghĩa các phần là:

```text
verification-metadata
  configuration
    verify-metadata
    verify-signatures
    trusted-keys/key-servers/keyring-format (khi cần PGP)
  components
    component group="..." name="..." version="..."
      artifact name="...jar"
        sha256 value="digest được Gradle sinh"
        pgp value="fingerprint được chấp thuận" (khi có)
      artifact name="...pom"
        sha256 ...
```

Sơ đồ trên **là mô tả, không phải XML để copy**. Trong XML thật, `sha256.value` phải là chuỗi hex SHA-256 đúng 64 ký tự cho **bytes của chính artifact**, không phải hash của tên file, class Java hay tọa độ GAV. Một module có thể có nhiều artifacts và metadata files được xác minh riêng.

**`<verify-metadata>true</verify-metadata>`** có ý nghĩa an ninh: nếu POM bị sửa để đưa thêm dependency độc hại, kiểm tra chỉ JAR của module trực tiếp là chưa đủ. Nếu tắt verification metadata, dependency graph có thể bị ảnh hưởng trước khi JAR cuối được chọn.

## 5. Demo chạy được: Java 17, Commons Lang 3, checksum SHA-256

Tạo một Gradle Kotlin DSL project nhỏ có **Gradle Wrapper** và JDK 17 hoặc phiên bản phù hợp. Gradle Wrapper là bộ file `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar` và `gradle/wrapper/gradle-wrapper.properties` đã được tạo/commit trước đó. Nếu tự tạo mới hoàn toàn, cần Gradle đã cài tạm để chạy `gradle wrapper` lần đầu.

### 5.1. Cây thư mục

```text
verification-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── src/main/java/demo/Main.java
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
├── gradlew
└── gradlew.bat
```

`settings.gradle.kts`:

```kotlin
rootProject.name = "verification-demo"
```

`build.gradle.kts`:

```kotlin
plugins {
    application
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}

application {
    mainClass.set("demo.Main")
}
```

`src/main/java/demo/Main.java`:

```java
package demo;

import org.apache.commons.lang3.StringUtils;

public final class Main {
    private Main() {}

    public static void main(String[] args) {
        System.out.println(StringUtils.reverse("Gradle"));
    }
}
```

Ví dụ không cần plugin Gradle bên ngoài: `application` là core plugin và tự áp dụng Java plugin. Máy chạy cần JDK được Wrapper hỗ trợ, kết nối Maven Central lần đầu hoặc các artifacts tương ứng đã có trong cache.

### 5.2. Bootstrap checksum

Linux/macOS:

```bash
./gradlew --version
./gradlew --write-verification-metadata sha256 run
```

Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat --write-verification-metadata sha256 run
```

Gradle resolve project dependencies, chạy ứng dụng và **tạo hoặc cập nhật**:

```text
gradle/verification-metadata.xml
```

Lưu ý rằng bootstrapping là một **lượt ghi vào policy**, không phải phép chứng minh artifact đã an toàn. Nó ghi checksum của bytes tìm thấy ở repositories/cache lúc ấy. **Không commit ngay khi chưa review.**

Ứng dụng `Main` in dòng:

```text
eldarG
```

Đây là **stdout từ Java program**, không phải toàn bộ stdout của Gradle trong lệnh bootstrap (lệnh đó còn có thông báo task, download hoặc cảnh báo).

### 5.3. Kiểm tra sau khi có verification metadata

Linux/macOS:

```bash
./gradlew -q clean run
```

Windows PowerShell:

```powershell
.\gradlew.bat -q clean run
```

Nếu artifacts thực tế khớp các checksum đã chấp thuận, chương trình vẫn in:

```text
eldarG
```

Mọi artifact mới chưa có verification metadata sẽ cần được xét duyệt; nếu không, với mode strict Gradle có thể báo **missing checksum** và dừng thay vì tự tin nhận dependency mới.

### 5.4. Quan sát metadata sinh ra

Mở `gradle/verification-metadata.xml`. Kiểm tra:

- Có entry cho các module/artifacts mà build thật sự resolve; không chỉ JAR chính nếu có metadata POM/`.module` được resolve.
- Các digest có thuật toán `sha256`, đúng cấu trúc component/artifact.
- Các dependency/plugin transitive được bao phủ khi đã được resolve.
- Trường `origin` do Gradle sinh (thường có tiền tố `Generated by Gradle`) **chưa có nghĩa đã được review**.
- Nếu metadata/XML quá lớn, xem xét tại sao build kéo nhiều dependencies; đừng xóa entries tùy ý trước khi hiểu nguyên nhân.

Có thể quan sát graph của Java application:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
```

Đây là **lệnh phân tích graph và version**, không kiểm tra chữ ký bằng chính nó. Verification chạy khi artifacts được resolve theo cơ chế của Gradle; cùng một GAV có thể kéo metadata files/variants khác nhau tùy Gradle và repository.

### 5.5. Mô phỏng checksum mismatch an toàn

Chỉ thực hiện trong một **bản sao/sandbox của demo**, không chỉnh verification metadata production:

1. Lưu bản gốc của `verification-metadata.xml`.
2. Tìm entry `sha256` cho `commons-lang3-3.14.0.jar`.
3. Thay **một ký tự hex** của digest mong đợi bằng ký tự hex khác, giữ độ dài 64.
4. Chạy `./gradlew --dependency-verification strict clean run`.
5. Kỳ vọng Gradle **dừng với dependency verification failure** và chỉ ra checksum expected khác actual; program không chạy đến dòng in output.
6. Phục hồi bản metadata trước thí nghiệm, không bootstrap lại để “chấp nhận” giá trị sai.

**Không cần sửa JAR thật**, không cần làm bẩn Gradle cache. Trong những phiên bản/configurations nhất định, lệnh `clean` vẫn có thể chạy phần riêng trước khi task resolve; điều cần xác nhận là **artifact không được dùng thành công khi checksum sai**, không phải thứ tự mọi log lifecycle.

**Điều này kiểm tra enforcement chứ không kiểm tra nguồn trust:** nếu ai đó sửa cả JAR lẫn digest thành hash của JAR mới rồi commit, Gradle vẫn thấy hợp lệ. Bởi vậy `verification-metadata.xml` phải được code review/bảo vệ nhánh như một file chính sách an ninh.

## 6. Khởi tạo kết hợp SHA-256 và PGP

Khi publisher công bố ASCII-armored signature files `.asc` bên cạnh artifacts, Gradle có thể xác minh chữ ký PGP.

Cách sinh metadata cho checksum và chữ ký:

```bash
./gradlew --write-verification-metadata pgp,sha256 run
```

Hoặc trình tự **ưu tiên integrity của mọi artifact**:

```bash
# Lượt 1: tạo checksum cho những artifact thực sự resolve
./gradlew --write-verification-metadata sha256 run

# Lượt 2: bổ sung thông tin chữ ký/keys
./gradlew --write-verification-metadata pgp,sha256 run
```

Lý do có hai lượt: theo tài liệu Gradle, khi bootstrap PGP + SHA cùng một lần, Gradle có thể ưu tiên chữ ký và **chỉ tự sinh checksum fallback cho artifact không có chữ ký hoặc bị ignored key**. Nếu muốn **cả checksum mạnh và PGP** cho artifacts được ký, hãy bootstrap checksum trước, rồi bổ sung chữ ký; kiểm tra XML cuối cùng, không chỉ nhìn các flags.

**Khi bootstrap PGP, Gradle có thể:**

- Tìm `.asc` signature của artifact ở remote repository.
- Tải public key từ key server nếu cần.
- Thêm trusted keys/ignored keys theo kết quả tự động.
- Tạo checksum fallback cho artifact không có signature khả dụng.
- Ghi nhận nhóm key ở cấp group để giảm độ dài policy.

Các bước tự động này là **đề xuất cần review**, không phải bằng chứng khóa tin cậy. Đặc biệt khi key chưa có ở server, `ignored-key` do Gradle tự tạo phải được điều tra, không dùng làm cách mặc định lờ lỗi.

**Giới hạn:** Gradle hiện hỗ trợ xác minh chữ ký của artifacts được publish dưới dạng ASCII-armored `.asc` trên **remote repositories**. Không phải module nào cũng ký artifacts; việc bật PGP không biến một artifact unsigned thành signed. Khi thiếu `.asc`, policy phải có **checksum đã tin cậy** để fallback.

## 7. Tính hợp lệ của chữ ký không đồng nghĩa danh tính người ký được xác thực

Quy trình cơ bản:

```text
Publisher có private key ── ký bytes artifact ──> file .asc
             |
             v
Public key/fingerprint được công bố
             |
   Người dùng xác minh qua nguồn đáng tin độc lập
             |
             v
Gradle có artifact + .asc + public key + verification policy
             |
             v
Kiểm tra cryptographic signature + trust policy + checksum nếu có
             |
         PASS hoặc FAIL
```

**Trusted key phải được kiểm tra danh tính:**

1. Lấy **full fingerprint 40 ký tự hex** từ kênh chính thức: website/documentation/release notes/KEYS file của chính publisher qua nguồn đáng tin, hoặc thông tin được tổ chức xác nhận riêng.
2. Đối chiếu fingerprint với public key thực nhận; **đừng chỉ xem User ID/email/tên người ký**, vì chuỗi này có thể tự khai báo.
3. Xác định khóa đó được dùng cho **group/module nào**, không trust toàn bộ repositories và mọi modules.
4. Xem liệu khóa đã rotate, revoke hoặc có cảnh báo compromised không; nếu cần trust khóa mới thì phải review.
5. Chỉ sau các bước ấy mới đưa fingerprint vào `verification-metadata.xml` hoặc keyring/public-key policy.

Gradle yêu cầu **full 40-character fingerprint** cho `<pgp>` và `<trusted-key>`. Short key IDs dễ bị collision; không copy chuỗi 8/16 ký tự từ log rồi coi đó là định danh đủ mạnh.

### 7.1. XML trusted-keys minh họa

Mẫu Gradle hỗ trợ trusted public key ở cấp group/module:

```xml
<trusted-keys>
    <trusted-key
        id="06D34ED6FF73DE368A772A781063FE98BCECB758"
        group="com.puppycrawl.tools"
        name="checkstyle"/>
</trusted-keys>
```

Đây là **một đoạn XML minh họa đặt bên trong `<configuration>` theo tài liệu Gradle**, không phải policy cho demo Commons Lang 3, và **không phải mệnh lệnh trust fingerprint này trong dự án của bạn**. Chỉ thêm key sau khi xác minh fingerprint đúng với publisher/artifact thực.

Khi trust theo group, giới hạn `group`, `name`, thậm chí version/artifact tùy chính sách. Tránh global key quá rộng: nếu private key của publisher bị đánh cắp, quyền trust mọi artifact trong group có thể khuếch đại tác động.

### 7.2. Chữ ký sai, key sai và thiếu chữ ký là ba tình huống khác

| Tình huống | Ý nghĩa | Cách phản ứng |
| --- | --- | --- |
| Có `.asc`, signature toán học hợp lệ nhưng **key untrusted** | Chưa xác thực publisher/key identity | Xác minh fingerprint độc lập; sau đó mới thêm trust |
| Có `.asc` nhưng signature **không khớp artifact** | File hoặc chữ ký sai/corrupt/compromised | Dừng, điều tra repository, checksum và publisher |
| **Không có `.asc`** | Publisher có thể không ký artifact | Yêu cầu checksum đã review để fallback |
| Public key chưa tải được | Key server/network/cache/format có vấn đề | Thử nguồn chính thức, keyring local, refresh key cache theo chính sách |
| Nhiều chữ ký nhưng một chữ ký fail | Không thể coi toàn bộ artifact là “verified” | Điều tra từng signature; Gradle kiểm tra các chữ ký liên quan |

Một chữ ký được tính trên digest của artifact và metadata theo cơ chế PGP; khả năng bảo vệ integrity phụ thuộc thuật toán ký, nên checksum SHA-256/SHA-512 bổ sung là lựa chọn tốt.

## 8. Key servers và keyring: làm việc ổn định trên CI

Mỗi lần CI runner mới tải keys từ nhiều key servers có thể chậm hoặc gặp lỗi network. Gradle hỗ trợ **keyring công khai** được commit cùng project:

- `gradle/verification-keyring.keys` — ASCII-armored public keys, dễ code review.
- `gradle/verification-keyring.gpg` — binary public keyring, gọn hơn.
- `gradle/verification-metadata.xml` — policy: keys nào được trust cho artifact/group nào.

**Public keyring không chứa private signing key**. Không commit private key hoặc passphrase của publisher vào Git.

Chọn định dạng ASCII trong phần `<configuration>` của XML:

```xml
<keyring-format>armored</keyring-format>
```

Đây là **một phần tử được chèn vào `<configuration>`**, không phải một file XML độc lập. Các giá trị hỗ trợ là `armored` hoặc `binary`.

Export keys đã dùng:

```bash
./gradlew --export-keys
```

Hoặc kết hợp khi bootstrap:

```bash
./gradlew --write-verification-metadata pgp,sha256 --export-keys run
```

Gradle có thể tạo cả định dạng binary và armored nếu không quy định `keyring-format`; **chỉ commit định dạng đã chọn**, tránh hai file không đồng bộ. Với format `armored`, kiểm tra `gradle/verification-keyring.keys`. Khi không có key trong keyring, Gradle thường thử key servers nếu được bật.

### 8.1. CI không muốn liên hệ key servers

Trong `<configuration>`:

```xml
<key-servers enabled="false"/>
```

Khi dùng local keyring đầy đủ, điều này giúp CI kiểm tra dựa trên keys đã review trong repository. Nếu thiếu key, build **fail**, không tự tải từ server. Theo Gradle, khi **bootstrapping** còn bật việc sinh metadata, flag tắt key server có thể được bỏ qua để tải keys thiếu — cần đọc log và không suy rằng bootstrap offline hoàn toàn.

### 8.2. Không dùng key server làm nguồn trust

Key server là kênh **phân phối public key**, không phải cơ quan xác nhận publisher. Một attacker có thể đăng key mới mang email/tên gần giống tác giả. Policy chỉ nên trust fingerprint đã kiểm chứng với publisher, không trust key chỉ vì key server trả về nó.

Nếu một key bị mất trên key servers nhưng có bản public key được xác thực từ nguồn chính thức, có thể đưa vào `.keys`/`.gpg`. Gradle cache thông tin “key missing” trong khoảng 24 giờ; có tùy chọn:

```bash
./gradlew build --refresh-keys
```

Lệnh này yêu cầu thử lại việc tìm keys, **không biến untrusted key thành trusted**.

## 9. Những mode strict, lenient và off

Gradle có ba chế độ:

| Mode | Hành vi | Khuyến nghị |
| --- | --- | --- |
| `strict` (mặc định) | Verification failure làm build fail càng sớm càng có thể | **Mặc định cho CI và release** |
| `lenient` | Build vẫn có thể chạy dù verification failures; ghi warnings/errors | Chỉ cho chẩn đoán có kiểm soát, không dùng để gate release |
| `off` | Bỏ hoàn toàn verification | Không dùng trong build đáng tin trừ trường hợp đặc biệt được phê duyệt |

Cú pháp CLI:

```bash
./gradlew --dependency-verification strict build
./gradlew --dependency-verification lenient build
./gradlew --dependency-verification off build
```

Hoặc property được Gradle hỗ trợ:

```properties
org.gradle.dependency.verification=strict
```

Đây là **một dòng cấu hình cho `gradle.properties`**, không phải dependency của ứng dụng. Có thể truyền system property `-Dorg.gradle.dependency.verification=strict` khi cần.

**Cẩn thận:** nếu CI dùng `lenient` hoặc `off` để “tạm sửa” vấn đề thiếu checksum, build có thể hoàn tất dù dependency verification cảnh báo, làm mục tiêu bảo vệ không còn. Khi policy cần chặt, hãy giữ strict, bổ sung checksum/key sau review thay vì bypass.

### 9.1. Báo cáo chi tiết trên console

Gradle có thể tạo HTML verification report bên cạnh summary. Trên CI, đọc file HTML không luôn thuận tiện. Trong `gradle.properties`:

```properties
org.gradle.dependency.verification.console=verbose
```

Setting này giúp hiển thị lý do verification failures rõ hơn trên console; nó **không** đổi policy hoặc làm lỗi biến mất.

## 10. Từ bootstrap đến baseline được tin cậy

Bootstrap thuận tiện vì có thể resolve nhiều configurations trong toàn bộ build, nhưng nó áp dụng logic **trust on first use (TOFU)**: ghi lại bytes hiện tại.

Quy trình onboarding nên gồm:

1. **Pin Gradle Wrapper** và source repositories; hạn chế public repo cho internal groups bằng content filtering khi phù hợp.
2. Chạy `./gradlew --write-verification-metadata sha256 build` hoặc task đủ bao phủ modules muốn bảo vệ.
3. Nếu muốn PGP, chạy thêm `./gradlew --write-verification-metadata pgp,sha256 build`; kiểm tra keyrings.
4. Mở `gradle/verification-metadata.xml` và xem mọi entry được thêm, nhất là modules/plugins nhạy cảm.
5. Kiểm tra nguồn artifact/POM qua publisher chính thức, approved repository, release checksum/signature độc lập hoặc quy trình nội bộ.
6. Xác minh trusted PGP fingerprints **qua kênh độc lập**, review group/module scope.
7. Điều tra `ignored-key`, unsigned artifacts và checksum fallback; không auto-trust toàn bộ.
8. Theo quy trình review, cập nhật `origin` từ `Generated by Gradle` sang `Verified` khi thật sự đã đối chiếu; ghi lý do/nguồn phù hợp.
9. Commit `verification-metadata.xml` và public keyring đã chọn vào Git, kèm peer review/branch protections.
10. Chạy CI clean ở chế độ **strict** với đủ task test/build/publish được tổ chức cho phép.
11. Thiết lập quy trình cập nhật khi thêm dependency, version, plugin hoặc repository.

**Không bootstrap trên nguồn đã biết đáng ngờ.** Nếu security alert liên quan repository/credential đang dùng, dừng để điều tra và xác minh artifact ngoài bối cảnh ấy trước khi chấp nhận checksum.

### 10.1. Lệnh preview thay đổi

Gradle hỗ trợ preview:

```bash
./gradlew --write-verification-metadata sha256 help --dry-run
```

Theo tài liệu, thay vì overwrite `verification-metadata.xml`, Gradle tạo `gradle/verification-metadata.dryrun.xml` để review. **`--dry-run` không chạy task actions**, nên không thấy dependencies chỉ resolve ở execution; coi đây là preview hữu ích chứ không phải bằng chứng mọi dependency đều có hash.

### 10.2. Cập nhật không phải reset toàn bộ policy

`--write-verification-metadata` có tính **incremental**: thông tin đã có thường được giữ lại, thêm entries mới. Sau một lần update dependency:

- Kiểm tra Git diff cho **module mới, version mới, artifact metadata mới, trusted keys mới**.
- Xóa entries cũ không còn dùng nếu đã xác nhận không còn workflows cần; Gradle không tự biết chắc entry nào “obsolete”.
- Xác minh checksum/key mới độc lập, đừng tự động đánh dấu mọi `Generated by Gradle` thành `Verified`.
- Giữ cùng checksum/signature parameters đã chọn cho những lần bootstrap sau, tránh policy không nhất quán.
- Nếu cần xét bản policy hoàn toàn mới, làm trên bản sao/bản branch riêng, không xóa metadata sản xuất trước khi đảm bảo review.

Một plugin thêm nhiều dependencies bắc cầu là chuyện bình thường; đó không phải lý do bỏ qua metadata chỉ vì file dài.

## 11. Khi kiểm tra thất bại: ba loại bằng chứng quan trọng

### 11.1. Thiếu verification entry

Ví dụ lỗi (diễn giải, không chép nguyên log):

```text
Dependency verification failed:
  artifact commons-logging-1.2.jar
  no checksum/signature verification metadata
```

Có thể xảy ra khi mới thêm một direct/transitive dependency, bật IDE download sources/Javadoc hoặc một plugin resolve dependency ở task action.

**Xử lý:**

1. Xác định module GAV và artifact filename thực sự mới.
2. Xem nó xuất hiện vì dependency/plugin/version nào (`dependencies`, `dependencyInsight`).
3. Xác nhận repo và publisher tin cậy.
4. Sinh thêm entry bằng bootstrapping hoặc điền thủ công sau khi có checksum chính thức.
5. Review diff, CI strict lại.

Không chọn ngay `off` hoặc thêm `<trusted-artifacts>` toàn nhóm để vượt kiểm tra.

### 11.2. Sai checksum — expected khác actual

```text
Artifact: example-lib-1.0.jar
Expected SHA-256: (giá trị trong policy)
Actual SHA-256:   (giá trị Gradle tính được)
```

Đây là **mẫu báo cáo khái niệm**, không phải digest của artifact thật.

Nguyên nhân khả dĩ: artifact/cache bị sửa, mirror trả bytes khác, publisher tái xuất bản cùng version, artifact từ repo khác, POM khác newline/timestamp hoặc một sự cố security.

**Xử lý theo thứ tự an toàn:**

1. **Dừng release/CI** và giữ log, GAV, repository origin, checksum expected/actual.
2. So sánh bytes/checksum từ publisher đáng tin hoặc release checksum chính thức qua kênh độc lập.
3. Xem repository order, mirror, proxy, cache hoặc metadata redirect có thay đổi không.
4. Nếu có nghi vấn compromise, cô lập artifact và báo chủ sở hữu repository/security team.
5. Chỉ khi đã xác nhận bản khác là hợp lệ, cập nhật policy có review.
6. Chạy lại strict và kiểm thử thực thi phù hợp.

**Không tự động chạy `--write-verification-metadata sha256` để chấp nhận ngay “actual”**: làm vậy có thể biến artifact bị tráo thành baseline hợp lệ. `--refresh-dependencies` có thể yêu cầu kiểm tra lại resolution metadata/artifact theo chính sách, nhưng **không** chứng minh nguồn tải an toàn và không nhất thiết tải lại tất cả bytes.

### 11.3. PGP signature untrusted hoặc không khớp

**Untrusted signature:** chữ ký toán học có thể hợp lệ, nhưng key không được đánh dấu trusted. Cần xác minh full fingerprint qua nguồn publisher chính thức trước khi bổ sung `trusted-key`/`pgp` entry.

**Signature mismatch:** artifact hoặc `.asc` không cùng nội dung/ký sai; phải điều tra trước. Nếu xác minh publisher thật có signature không đúng trên một mirror hoặc POM bị thay whitespace, có thể thêm **artifact-level ignored key** kèm **checksum mạnh đã review**; không nên globally ignore key và vô tình disable verification nhiều modules.

Một số publisher rotate keys. Nên tìm thông báo chuyển khóa của publisher, so full fingerprints và scope theo group/module; không trust key mới chỉ vì Gradle hiển thị “signed by key X”.

## 12. Ignored keys và trusted artifacts: hiểu rủi ro của ngoại lệ

Gradle có các khối cấu hình để xử lý thực tế khó khăn:

- `<ignored-keys>`: bỏ qua một signing key trong phạm vi cấu hình; nếu không còn chữ ký hợp lệ thì phải **có checksum** để xác minh artifact.
- `<trusted-artifacts>`: cho phép một số artifacts theo group/name/version/file **khỏi cần verification**; tiện nhưng mở vùng không được bảo vệ.
- `<verify-metadata>false</verify-metadata>`: chỉ kiểm tra artifacts, bỏ qua kiểm tra POM/Ivy/`.module` — làm yếu bảo vệ dependency graph.
- `resolutionStrategy.disableDependencyVerification()`: tắt verification cho configuration đặc biệt; Gradle có cảnh báo, không phải bản sửa lỗi checksum.
- `--dependency-verification lenient/off`: thay đổi enforcement toàn lượt build.

Những công cụ này tồn tại để tương thích với workflows đặc thù, **không phải phương pháp chuẩn giải quyết mismatch**. Ngoại lệ cần: phạm vi tối thiểu, lý do, chủ sở hữu, hạn xem lại, bằng chứng nguồn độc lập và test.

### 12.1. Nên ưu tiên checksum fallback hơn trust mọi nguồn

Ví dụ publisher không ký Javadoc/sources. Theo Gradle, chúng vẫn có thể được verify khi IDE resolve. Một nhóm phát triển có thể tempted dùng wildcard trust tất cả `*-sources.jar` và `*-javadoc.jar`. Điều này **bỏ verification cho những file ấy**, không có nghĩa chúng an toàn. Nếu cần integrity, hãy tạo checksum đúng cho từng artifact thay vì tự động trust wildcard.

Nếu internal repository được quản trị tốt, cũng không nên mặc định `trust group=com.company` cho tất cả artifacts; internal repo và credentials vẫn có thể bị compromise.

## 13. Dependency locking bổ sung chứ không thay thế verification

Giả sử dependency graph có:

```text
application
  └─ lib-a:1.0
       └─ lib-b:2.0
```

- **Locking** kiểm soát module/version đã resolve (ví dụ giữ `lib-b:2.0`).
- **Verification** kiểm soát bytes của `lib-b-2.0.jar` và metadata đi cùng nếu đã khai báo.

Cùng một version `2.0` vẫn có thể bị publish lại với bytes khác; lock không phát hiện. Ngược lại, verification không ngăn một update PR hợp lệ đổi version theo policy nếu checksum mới cũng được chấp thuận; lock buộc bạn xác nhận graph version.

Cách triển khai hợp lý:

1. Dùng explicit versions/constraints và dependency locking ở những configurations cần tái lập.
2. Dùng dependency verification strict để đảm bảo bytes/signing keys đã review.
3. Dùng repository content filters để bảo vệ private groups.
4. Dùng dependency vulnerability scanning để phát hiện CVE/advisories.
5. Dùng Wrapper checksum verification cho chính công cụ build.
6. Dùng CI code review trên thay đổi lockfile và `verification-metadata.xml` **cùng một PR**.

Đừng coi Gradle dependency verification là công cụ quét malware toàn diện hay SCA database.

## 14. Wrapper và signing plugin là hai lớp khác

### 14.1. Wrapper distribution

File `gradle/wrapper/gradle-wrapper.properties` có thể chứa `distributionSha256Sum` để xác minh **ZIP phân phối Gradle** khi Wrapper tải lần đầu. Giá trị phải được lấy từ **Gradle release checksums chính thức** cho chính bản distribution đã chọn. `gradle-wrapper.jar` cũng cần được kiểm tra nguồn gốc/checksum riêng.

Không coi `gradle/verification-metadata.xml` là đủ để bảo vệ `gradlew`/`gradle-wrapper.jar`: chúng hoạt động **trước** khi Gradle chạy dependency verification.

### 14.2. Signing artifacts khi bạn là publisher

Gradle `signing` plugin và `maven-publish` có thể được dùng **bên producer** để ký những artifacts do bạn phát hành. Dependency verification là **phía consumer** kiểm tra chữ ký/bytes của artifact đã tải.

**Không nhầm:**

- Publisher có private key để ký; private key/phrasphrase phải nằm trong secure storage.
- Consumer chỉ cần **public key** và trust policy để verify.
- Thêm `signing` plugin vào application consumer **không tự bật dependency verification**.
- Có `.asc` bên cạnh artifact **không** có nghĩa consumer đã xác thực khóa của người ký.

## 15. CI/CD: từ baseline tới enforcement

Một pipeline nên dùng **Gradle Wrapper được xác minh** và chỉ build trong strict mode. Ví dụ lệnh chính (Linux/macOS):

```bash
./gradlew --version
./gradlew --dependency-verification strict clean test
./gradlew --dependency-verification strict build
```

Trong Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat --dependency-verification strict clean test
.\gradlew.bat --dependency-verification strict build
```

Lệnh `test`/`build` hợp lệ trong demo ở phần 5 nhờ `application` áp dụng Java plugin. Trên một build khác, phải dùng task thực có trong project.

**Khuyến nghị triển khai:**

- Commit `gradle/verification-metadata.xml` và public keyring nếu dùng PGP.
- Không bootstrap hoặc write verification metadata tự động trong **job build production**. PR nâng dependencies thực hiện ở workflow riêng, có review.
- CI job bắt buộc strict; policy XML và lockfiles không được tự động đổi trong job chính.
- Bảo vệ credentials của artifact repositories và key servers; dùng HTTPS/allowlist đúng.
- Kiểm tra full fingerprint theo nguồn tin cậy trước khi thêm trusted key, không rely vào email displayed.
- Nếu cần giảm network tới key servers, dùng public keyring đã review + tùy chọn disable key servers.
- Khi failure, lưu logs/HTML verification report làm artifact kiểm toán (theo chính sách) thay vì bật `off`.
- Chạy những tasks khác nhau (unit, integration, custom packaging) để phát hiện dependencies chỉ resolve ở execution.
- Khi Gradle Wrapper/plugin version thay đổi, review metadata mới có liên quan, đặc biệt plugin build dependencies.

### 15.1. Khác biệt giữa clean, cache và integrity

`clean` xóa outputs trong project build directory, **không có nghĩa xóa toàn bộ Gradle dependency cache**. Chạy Gradle với cache đã có vẫn phải tuân policy verification khi artifact được dùng qua engine, nhưng đừng coi “CI pass” trên một cache nóng là bằng chứng repository mới hoạt động được.

Nếu muốn kiểm tra fresh environment, dùng runner hoặc `GRADLE_USER_HOME` test riêng có network/quyền thích hợp; tránh xóa cache người khác. Khi cần xác minh artifact thực, đo SHA-256 ngoài Gradle trên **file đã xác định đúng nguồn** rồi so với nguồn chính thức. Không sửa cache để tạo “pass”.

## 16. Bảng troubleshooting thực tế

| Lỗi/triệu chứng | Nguyên nhân khả dĩ | Xử lý an toàn |
| --- | --- | --- |
| `Dependency verification failed: missing checksum` | Module/plugin/transitive/source/POM mới chưa có entry | Xác minh GAV, repo, publisher; thêm checksum sau review |
| Expected SHA khác Actual SHA | Bytes artifact hoặc metadata khác baseline | Dừng release, điều tra cache/repo/publisher; không auto-accept |
| Artifact có signature valid nhưng key untrusted | Fingerprint chưa được trust trong policy | Xác minh fingerprint qua nguồn publisher độc lập |
| PGP signature mismatch | Signature/corrupt file/mirror hoặc compromise | Cô lập, kiểm tra artifact và `.asc` từ nguồn chính thức |
| Key server timeout hoặc key unavailable | Network, cache missing key, publisher không public key | Dùng keyring public đã xác minh; thử `--refresh-keys` khi phù hợp |
| Không có `.asc` | Publisher không ký file | Dùng SHA-256/SHA-512 đã review để fallback |
| Bootstrapping tạo ignored-keys hàng loạt | Keys không tải được hoặc signatures không xác minh | Điều tra từng key, đừng coi ignored là trusted |
| CI pass dù có verification warning | `lenient`/`off` hoặc configuration exemption đang bật | Chuyển CI strict, xóa bypass không cần thiết |
| XML rất lớn | Ghi cả transitive dependencies, POM, plugins, metadata | Review/dọn entries cũ có căn cứ; không disable metadata vội |
| Nâng dependency xong build fail ngay | Version/artifacts mới chưa được trust | Tạo update PR, review diff metadata và locking |
| Gradle plugin mới fail verification | Plugin resolution nằm trong scope kiểm tra | Xác minh plugin ID/publisher/marker/dependencies, cập nhật metadata |
| Sources JAR tải bằng IDE gây lỗi | Sources/Javadocs cũng phải được verify | Bổ sung hash, không trust wildcard theo thói quen |
| Same GAV nhưng artifacts khác giữa mirrors | Repo mirror khác metadata bytes/artifact timestamp | Xác minh cả hai nguồn trước khi dùng `also-trust` |
| Cần nhiều giá trị checksum hợp lệ cho một artifact | Publisher phát hành bytes khác có căn cứ | Chỉ sau điều tra, thêm `also-trust` có review, tránh nới rộng mù quáng |
| Module SNAPSHOT vẫn thay đổi | Changing dependency không nằm trong bảo vệ như static artifacts | Hạn chế snapshot cho release, dùng version cố định |
| Task tải file bằng `curl` mà verification không báo | Tải ngoài Gradle dependency management | Thêm verification riêng hoặc thay bằng dependency resolution đúng |
| Wrapper ZIP/JAR bị thay nhưng dependency verification vẫn pass | Wrapper nằm ngoài phạm vi bảo vệ đó | Dùng `distributionSha256Sum` và Wrapper JAR validation |
| Security scanner báo CVE dù checksum pass | Artifact đúng bytes vẫn có lỗ hổng | Cập nhật library, SCA, test và chính sách bảo mật |
| Key rotation gây fail | Publisher đổi signing key | Xác minh thông báo và full fingerprint mới, cập nhật trust scope |
| `--write-verification-metadata` làm hết lỗi tạm thời | Đã ghi “actual” thành new baseline | Review độc lập, undo nếu chưa xác minh, không auto-commit |

## 17. Bài tập tự kiểm tra

1. **Hash SHA-256 khớp nhưng artifact không rõ nguồn gốc: có nên tin?** Chưa đủ. Hash chỉ chứng minh khớp một baseline; cần kiểm tra baseline đến từ publisher/nguồn tin cậy nào.
2. **PGP signature hợp lệ từ key có tên đúng email publisher: đã xác minh publisher chưa?** Chưa. Tên/email có thể giả; kiểm tra full fingerprint qua kênh chính thức.
3. **Tại sao `--write-verification-metadata sha256` không thể thay bước security review?** Vì nó ghi checksum của artifact đang tồn tại trong repo/cache, có thể đã bị thay.
4. **Đổi `org.apache.commons:commons-lang3:3.14.0` thành version khác nhưng lockfile chưa cập nhật thì chuyện gì xảy ra?** Resolution/locking có thể fail hoặc chọn version theo policy; metadata checksum cho version mới vẫn cần review riêng.
5. **Vì sao một POM bị thay có thể nguy hiểm dù JAR trực tiếp không đổi?** POM có thể thay dependency graph, kéo một transitive artifact không mong muốn.
6. **Plugin Gradle có được kiểm tra không?** Có khi được resolve qua Gradle dependency management/plugin resolution trong phạm vi verification.
7. **Nếu PGP key server không trả key, có nên thêm bất kỳ fingerprint trong error vào trusted-keys?** Không. Phải xác minh identity, có thể dùng local public keyring.
8. **Nếu ký artifact bằng private key của công ty, có cần commit private key vào consumer?** Không. Consumer chỉ commit/public key/fingerprint đã review; private key nằm ở publisher signing infrastructure.
9. **CI đang dùng `--dependency-verification lenient`: verification failure có chắc làm job fail không?** Không. Đặt strict để gate artifact.
10. **Có thể dùng `verification-metadata.xml` thay `distributionSha256Sum` của Wrapper?** Không. Wrapper chạy trước dependency verification.
11. **Một library vừa có chữ ký PGP vừa có SHA-256, vì sao kiểm cả hai?** Chữ ký giúp kiểm nguồn ký đã xác thực; SHA-256 mạnh giúp phát hiện thay bytes với thuật toán digest hiện đại.
12. **Artifact local do chính task compile ra có được cơ chế dependency verification này kiểm tra không?** Không như external downloaded dependencies; build outputs cần test/cache/reproducibility riêng.

## 18. Checklist áp dụng trong dự án thật

- [ ] Gradle Wrapper được pin và xác minh distribution checksum/Wrapper JAR riêng.
- [ ] File `gradle/verification-metadata.xml` tồn tại và được commit qua code review.
- [ ] `verify-metadata` bật, hash dùng SHA-256 hoặc SHA-512; không dùng MD5/SHA-1 làm bảo vệ chính.
- [ ] CI/release dùng mode **strict**, không duy trì `lenient`/`off` như default.
- [ ] Các direct/transitive dependencies, plugins, POM/`.module` được cover bởi workflow bootstrap/CI.
- [ ] Baseline checksum đã được review độc lập; `Generated by Gradle` không bị coi là `Verified` tự động.
- [ ] PGP trusted keys dùng full fingerprints đã xác minh và scopes đủ hẹp.
- [ ] Khi dùng PGP, public keyring được lưu an toàn, không chứa private key.
- [ ] Khi artifact không có `.asc`, có checksum mạnh đã xác nhận làm fallback.
- [ ] `ignored-key`/`trusted-artifacts`/verification exemptions có lý do, owner và giới hạn rõ.
- [ ] Repositories/credentials/content filtering được bảo vệ trước dependency confusion.
- [ ] Nâng dependencies có thay đổi locking/verification metadata được review trong cùng luồng.
- [ ] CI không auto-accept checksum mới khi verification fails.
- [ ] Có playbook khi checksum mismatch hoặc signature mismatch, lưu bằng chứng và escalation.
- [ ] Đã thử runner sạch và đủ tasks; không chỉ dựa vào cache local.
- [ ] Có quy trình SCA/SBOM/vulnerability scanning vì verification không quét CVE.

## 19. Ghi nhớ cốt lõi

- **Checksum** kiểm tra bytes artifact đã được chấp thuận; **PGP signature** xác minh key đã ký artifact; **fingerprint trust** mới là quyết định bạn tin ai.
- **`gradle/verification-metadata.xml`** là policy chung cho build và được tự kích hoạt khi tồn tại.
- **`--write-verification-metadata sha256`** bootstrap hashes; **`pgp,sha256`** bổ sung signatures. Phải review chứ không auto-trust.
- **`strict`** mới thực sự chặn build khi verification fail; `lenient` và `off` làm yếu enforcement.
- **POM/`.module` cũng cần verification**, không chỉ JAR.
- **Public keyring** có thể commit để CI đỡ phụ thuộc key servers; private keys không thuộc consumer repository.
- **Dependency locking** chọn versions, còn **dependency verification** xác minh bytes/keys của artifacts được nhận; hai cơ chế bổ trợ nhau.
- **Gradle Wrapper và files tải ngoài dependency engine** cần cơ chế integrity riêng.
- Khi mismatch, **điều tra nguồn**, không tự sinh lại checksum để tắt cảnh báo.

## Tài liệu chính thức

- [Gradle — Verifying Dependencies / Securing Dependencies](https://docs.gradle.org/current/userguide/dependency_verification.html): cấu hình SHA/PGP, bootstrap, modes, scope, trusted keys, keyrings và xử lý lỗi.
- [Gradle — Securing Dependencies](https://docs.gradle.org/current/userguide/securing_dependencies.html): mô hình integrity, provenance và supply-chain security.
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): `distributionSha256Sum` và verification của Wrapper JAR.
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): khóa versions và sự khác biệt với checksum verification.
- [Gradle — Best Practices for Security](https://docs.gradle.org/current/userguide/best_practices_security.html): integrity của Gradle distribution và dependencies.
- [Gradle — Declaring Repositories Basics](https://docs.gradle.org/current/userguide/declaring_repositories_basics.html): repository origins, phạm vi plugin/project repositories.
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): graph, transitive dependencies và dependencyInsight.
