# Vai trò của verification-metadata.xml và quy trình tin cậy artifact trong Gradle

## 1. Tại sao artifact cần được xác minh?

Một build Java dùng Gradle không chỉ biên dịch mã của nhóm. Nó thường tải JAR, POM, Gradle Module Metadata, plugins và các dependency bắc cầu từ Maven Central, kho nội bộ hoặc mirror. Mỗi artifact được dùng trong build có thể ảnh hưởng tới kết quả thực thi, thậm chí đưa mã bên thứ ba vào môi trường build hoặc ứng dụng.

Giả sử project yêu cầu một thư viện:

```groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
```

Thông tin `group:name:version` cho biết **thư viện nào được yêu cầu**, nhưng không chứng minh từng byte trong file `commons-lang3-3.17.0.jar` vừa tải là bản mà tổ chức đã phê duyệt. Một registry, proxy, mirror hoặc cache có thể bị tấn công, trả nhầm file hoặc phục vụ artifact bị thay đổi trong khi tọa độ vẫn giống nhau.

**Dependency verification** của Gradle giúp phát hiện sự thay đổi bất thường bằng cách so sánh artifact thực nhận với **checksum được phê duyệt**, hoặc kiểm tra **chữ ký PGP từ khóa được tin cậy**. Nơi lưu chính sách đó là:

```text
<root-build>/
├── settings.gradle
├── build.gradle
├── gradle/
│   ├── wrapper/...
│   └── verification-metadata.xml
└── src/...
```

`gradle/verification-metadata.xml` là **sổ cái các bằng chứng kiểm tra và quyết định tin cậy** của dependency, không phải một tập JAR, không phải dependency list thay cho `dependencies { }`, cũng không phải nơi khai báo repository.

Sau bài học, bạn sẽ:

1. Hiểu vai trò, phạm vi và nội dung quan trọng của `verification-metadata.xml`.
2. Phân biệt kiểm tra **integrity bằng SHA-256/SHA-512** và **provenance bằng chữ ký PGP/khóa công khai**.
3. Biết cách bật và tạo metadata bằng `--write-verification-metadata sha256`, phân tích rủi ro của bootstrapping và thiết lập quy trình phê duyệt artifact.
4. Hiểu các chế độ `strict`, `lenient`, `off` và vì sao production CI nên dùng strict.
5. Xử lý artifact mới, checksum thiếu, checksum sai, chữ ký không khớp, khóa chưa được tin cậy, metadata POM khác nhau và các ngoại lệ có phạm vi hẹp.
6. Thực hành một dự án Gradle Groovy DSL + Java 17+ và một chương trình Java tự tính SHA-256 với stdout kiểm chứng được.
7. Phân biệt **dependency locking** (khóa phiên bản) với **dependency verification** (xác minh file) và với công cụ quét CVE.

> Phạm vi ví dụ: Gradle Groovy DSL (`build.gradle`), Gradle Wrapper tương thích Java 17+ và các dependency từ repository được cấu hình. Các ví dụ Java chạy được; việc tải library lần đầu đòi hỏi kết nối repository, trừ khi đã có cache hợp lệ.

## 2. Ba câu hỏi bảo mật khác nhau: phiên bản, nội dung và độ an toàn

| Cơ chế | Câu hỏi mà nó trả lời | Điều nó **không** tự chứng minh |
| --- | --- | --- |
| Version catalog / khai báo dependency | Project *yêu cầu* module và version nào? | Bytes artifact nhận được là chính xác. |
| **Dependency locking** | Gradle *đã chọn* và cần giữ những module versions nào trong graph? | JAR cùng tọa độ có bị thay thế hay không. |
| **Checksum verification** | Bytes JAR/POM hiện tại có khớp **dấu vân tay đã tin cậy** không? | Ai thực sự sản xuất file hoặc file có lỗ hổng bảo mật không. |
| **PGP signature verification** | Artifact có chữ ký kiểm chứng được bằng **khóa công khai được chấp nhận** không? | Chủ sở hữu thực tế của khóa chắc chắn đáng tin nếu chưa xác minh danh tính. |
| **SCA/vulnerability scan** | Các thư viện đã chọn có CVE/advisory đã biết không? | Artifact thực tải có đúng nguyên gốc đã phê duyệt không. |
| HTTPS, repository credentials | Kết nối và quyền truy cập tới kho có được bảo vệ không? | Chính repository hoặc mirror có bị thay/đầu độc dữ liệu không. |

Ví dụ một project đã khóa `commons-lang3:3.17.0` trong `gradle.lockfile`. Nếu kẻ tấn công thay JAR ở cùng tọa độ bằng bytes khác, **lockfile có thể không phát hiện** vì version vẫn là `3.17.0`. Một checksum tin cậy trong `verification-metadata.xml` giúp nhận ra sự khác biệt byte.

Ngược lại, một JAR đúng checksum đã phê duyệt vẫn có thể chứa code lỗi thời và CVE. Verification **không phải** trình quét lỗ hổng. Chính sách dependency an toàn thường kết hợp version pinning/locking, checksum hoặc chữ ký, kiểm tra publisher và quét CVE.

## 3. Checksum, chữ ký và mô hình tin cậy

### 3.1. SHA-256: chứng minh bytes không đổi so với mốc được phê duyệt

SHA-256 tạo hash 256 bit, biểu diễn thành 64 ký tự hexadecimal. Nếu nội dung artifact đổi một byte, hash sẽ thay đổi với xác suất áp đảo. Gradle lưu giá trị kỳ vọng trong XML và so sánh với hash được tính từ artifact thực nhận.

```text
Tệp JAR nhận từ repository
           |
       Tính SHA-256
           |
           v
   Actual SHA-256 --------so sánh-------- Expected SHA-256
                                              |
                                     verification-metadata.xml
           |
   giống nhau? -> chấp nhận theo chính sách
   khác nhau?  -> báo lỗi verification ở chế độ strict
```

**Giới hạn quan trọng:** một checksum do chính repository có thể bị tấn công tạo ra **không tự mang tính xác thực**. Nếu lúc bootstrap bạn lấy cả JAR và hash từ nguồn đã bị đầu độc, XML sẽ ghi lại hash của artifact nguy hiểm. Bởi vậy phải xác lập **mốc kỳ vọng đáng tin**, tốt nhất kiểm tra chéo với nguồn độc lập của nhà phát hành hoặc tài liệu phát hành được xác thực.

Gradle hỗ trợ các loại hash như SHA-256/SHA-512, SHA-1 và MD5; nhưng **SHA-256 hoặc SHA-512** mới phù hợp để bảo vệ tính toàn vẹn trong quy trình hiện đại. Không lựa chọn MD5/SHA-1 làm chuẩn mới chỉ vì hash ngắn hơn.

### 3.2. PGP signature: kiểm tra chữ ký từ khóa được tin cậy

Nếu tác giả publish artifact cùng file chữ ký PGP ASCII-armored `.asc`, Gradle có thể lấy chữ ký, tìm khóa công khai tương ứng và kiểm tra chữ ký. Tuy nhiên việc một chữ ký **đúng về mặt toán học** chỉ chứng tỏ artifact được ký bằng một private key; nhóm vẫn phải biết **khóa đó có thực sự thuộc nhà phát hành dự kiến không**.

Các bước:

1. Artifact có chữ ký `.asc` được Gradle hỗ trợ.
2. Gradle tìm public key từ keyring cục bộ hoặc key server theo cấu hình.
3. Chữ ký được kiểm chứng bằng khóa đó.
4. Khóa phải nằm trong **danh sách khóa được tin cậy**, thường giới hạn theo group/module.
5. Nếu còn checksum được cấu hình, Gradle cũng đối chiếu checksum.
6. Nếu artifact không có chữ ký, kiểm tra có thể fallback sang checksum đã định nghĩa.

Không nên cho rằng mọi thư viện đều có chữ ký hoặc mọi file `.asc` đều dùng signer hợp lệ. Người review cần đối chiếu **full fingerprint** khóa với nguồn đáng tin ngoài luồng, ví dụ tài liệu chính thức của publisher.

### 3.3. Vì sao nên kết hợp cả hai?

Một artifact có thể không được ký; checksum là phương án kiểm soát hữu ích. Chữ ký PGP giúp định danh khóa ký, nhưng thuật toán hash nội bộ chữ ký có thể cũ. Theo tài liệu Gradle, nếu muốn kiểm soát cả **integrity và authenticity**, nên dùng cả chữ ký lẫn checksum khi nhà phát hành hỗ trợ. Khi một artifact không được ký, checksum đã thẩm định là fallback tốt hơn việc bỏ qua hoàn toàn.

## 4. verification-metadata.xml nằm đâu và được kích hoạt khi nào?

Đường dẫn trong một build điển hình:

```text
my-project/
└── gradle/
    └── verification-metadata.xml
```

Khi tìm thấy file **`gradle/verification-metadata.xml` trong root build**, Gradle bật dependency verification theo chính sách trong file. Một cấu hình XML hợp lệ nhưng **chưa chứa checksum cho các dependency đang dùng** sẽ thường khiến build có external dependencies thất bại ở chế độ strict, vì Gradle chưa có căn cứ tin cậy cho chúng.

Một ví dụ khung XML **hợp lệ về cấu trúc nhưng chưa đủ để chạy project có external dependencies**:

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

**Không dùng nguyên khung trống trên để thay file đã có.** Đây là ví dụ để đọc cú pháp: nó chưa xác nhận artifact nào. Cách lập baseline đúng sẽ dùng Gradle generate, rồi **review** trước khi commit.

### 4.1. Các khối chính

| Thành phần XML | Ý nghĩa |
| --- | --- |
| `<verification-metadata>` | Root, namespace và schema cho định dạng dependency verification. |
| `<configuration>` | Tùy chọn kiểm tra metadata, chữ ký, trusted keys, trusted artifacts, key servers... |
| `<verify-metadata>true</verify-metadata>` | Xác minh cả metadata POM/Ivy/Gradle Module Metadata khi được tải qua cơ chế dependency management. |
| `<verify-signatures>true</verify-signatures>` | Bật kiểm tra chữ ký PGP nơi có chữ ký phù hợp, kèm chính sách tin cậy khóa và checksum fallback. |
| `<components>` | Danh sách thành phần đã có verification records. |
| `<component group="..." name="..." version="...">` | Định danh một external module theo group, name, version. |
| `<artifact name="...">` | Một file cụ thể thuộc component: JAR, POM, module metadata, sources, v.v. |
| `<sha256 value="..."/>` | Giá trị checksum SHA-256 được phê duyệt cho **đúng file** đó. |
| `<pgp value="..."/>` | Fingerprint public key được tin cậy cho artifact cụ thể. |
| `<trusted-keys>` | Khóa được tin cậy với scope tùy thuộc group/name/version. |
| `<trusted-artifacts>` | Ngoại lệ cho phép artifact được **bỏ qua verification**; cần kiểm soát nghiêm ngặt. |
| `<ignored-keys>` | Khóa bị bỏ qua; nếu không có khóa đáng tin khác, cần checksum fallback. |

Trong tài liệu chính thức, ví dụ component chứa checksum như sau (một **trích đoạn cấu trúc**, không phải file metadata đầy đủ của lab):

```xml
<component group="com.google.guava" name="failureaccess" version="1.0.3">
    <artifact name="failureaccess-1.0.3.jar">
        <sha256
            value="cbfc3906b19b8f55dd7cfd6dfe0aa4532e834250d7f080bd8d211a3e246b59cb"
            origin="Verified"
            reason="Checksum confirmed by reviewer"/>
    </artifact>
</component>
```

Giá trị SHA-256 của `failureaccess-1.0.3.jar` ở đây được lấy từ ví dụ trong tài liệu Gradle; **không** lấy nó làm hash của `commons-lang3` hoặc file khác. Thuộc tính `origin`/`reason` chỉ ghi thông tin phục vụ audit; việc tự viết `origin="Verified"` **không biến một hash chưa được xác minh thành đáng tin** và Gradle không dùng dòng mô tả này như bằng chứng mật mã.

### 4.2. Tại sao phải kiểm tra cả POM/metadata?

POM và Gradle Module Metadata định nghĩa các dependency bắc cầu, variants và attributes; sửa metadata có thể làm build tải thêm module khác mà không đổi JAR trực tiếp. Khi `<verify-metadata>true</verify-metadata>`, Gradle có thể yêu cầu checksums cho cả `.pom`, `.module` và metadata được tải, bên cạnh `.jar`.

Một component cùng version có thể có nhiều entries:

```text
components
└── group:name:version
    ├── name-version.jar      -> SHA-256 được duyệt
    ├── name-version.pom      -> SHA-256 được duyệt
    ├── name-version.module   -> SHA-256 được duyệt nếu có/được dùng
    └── name-version-sources.jar -> nếu đã tải và cần xác minh
```

Đó là lý do file XML được generate có thể dài hơn danh sách dependencies trực tiếp. **Không** xóa các entries POM hoặc transitive chỉ để cho XML “gọn” nếu chúng vẫn được dùng. Đặt `verify-metadata=false` có thể giảm số record nhưng **giảm bảo vệ** vì metadata bị can thiệp có thể thay đổi cả graph.

### 4.3. Phạm vi áp dụng

Một file verification của root build được áp dụng cho root project, các subprojects, `buildSrc` và dependencies do các plugins của build tải qua dependency management engine. Với included builds, Gradle áp dụng chính sách verification của build hiện tại cho phần dependency liên quan; không mặc nhiên sử dụng một file verification riêng của included build theo cách nghĩ “mỗi included build tự kiểm tra”.

Gradle có cơ chế kiểm tra dependencies và plugins được tải qua hệ thống quản lý phụ thuộc của nó, **không phải bộ quét mọi file có trên máy**. Những JAR do chính task đang build tạo ra, dependency dạng changing/SNAPSHOT theo giới hạn Gradle nêu, và các file một custom script tự tải bằng HTTP ngoài cơ chế Gradle không được bao phủ giống external immutable artifacts. Cần các biện pháp riêng cho những bề mặt đó.

## 5. Quy trình tin cậy artifact: từ đề xuất đến bản đã phê duyệt

Một quy trình tốt không bắt đầu bằng việc nhấn “Accept” mọi hash Gradle mới sinh ra. Cần tách **khởi tạo bản ghi kỹ thuật** khỏi **quyết định tin cậy về bảo mật**.

```text
1. Đề xuất thêm/nâng dependency
          |
          v
2. Kiểm tra group:name:version, nguồn publish, license, CVE
          |
          v
3. Resolve graph từ repository được phép
          |
          v
4. Bootstrap checksum / PGP metadata
          |
          v
5. Đối chiếu hash hoặc full key fingerprint với nguồn độc lập
          |
          v
6. Review diff verification-metadata.xml + dependency lock
          |
          v
7. Commit / code review / CI strict
          |
          v
8. Vận hành, giám sát, cập nhật có kiểm soát
```

### 5.1. Bước A: xác định đúng artifact

Ghi lại:

- Group, module name, version và classifier/extension nếu đặc biệt.
- Direct hay transitive dependency? Xuất hiện ở `compileClasspath`, `runtimeClasspath`, `testRuntimeClasspath` hay plugin classpath?
- Repository nào thực sự phục vụ metadata và artifact? Có internal mirror, Maven Local, snapshot repository hay content filter không?
- Nhà phát hành chính thức, trang phát hành, chính sách license, thông báo CVE và kỳ vọng về chữ ký/checksum.
- Nguồn độc lập dùng để xác minh: trang publisher, bản phát hành/tag được bảo vệ, thông tin chữ ký từ maintainer hoặc bản đã phê duyệt trước.

Để tìm module và version thực sự chọn, dùng:

```bash
./gradlew -q dependencies --configuration runtimeClasspath
./gradlew -q dependencyInsight --configuration runtimeClasspath \
  --dependency org.apache.commons:commons-lang3
```

Các lệnh trên xem graph; chúng **không** tự phê duyệt checksum. Chọn đúng project path và configuration; trong multi-project có `:app`, có thể cần `:app:dependencyInsight` thay cho report của root.

### 5.2. Bước B: thiết lập root of trust

Đặt câu hỏi: **tại sao mình tin hash/key này?**

- Nếu giá trị hash chỉ được chép từ XML **mới sinh từ artifact đang tải**, đó mới là dữ liệu quan sát tại thời điểm bootstrap.
- Nếu hash được đối chiếu với nguồn chính thức **độc lập** và đã kiểm tra tính chính xác của publication, độ tin cậy cao hơn.
- Nếu dùng PGP, lấy **full key fingerprint** từ kênh đã xác minh của publisher rồi đối chiếu với key fetched từ key server hoặc keyring.
- Nếu ký bằng key chưa được xác nhận thuộc nhà phát hành, chữ ký đúng chỉ xác minh rằng **một key** đã ký, không xác minh con người/tổ chức mà bạn dự định tin cậy.
- Nếu repository/mirror và trang checksum đều do một bên kiểm soát, không gọi đó là hai nguồn độc lập chỉ vì dùng hai URL.

Quy tắc code review nên đòi evidence rõ với thư viện quan trọng: nguồn được kiểm tra, người duyệt, thời điểm và lý do thay đổi. Thuộc tính XML `origin` và `reason` giúp lưu chú thích; quá trình xác minh thực sự vẫn là trách nhiệm của reviewer.

### 5.3. Bước C: bootstrap, nhưng không tự động coi là được duyệt

Trong build đã biết repositories và versions hợp lệ, Gradle hỗ trợ:

```bash
./gradlew --write-verification-metadata sha256 help
```

Lệnh tạo hoặc cập nhật:

```text
gradle/verification-metadata.xml
```

Gradle cố gắng resolve các resolvable configurations thuộc build và sinh records checksum cho artifacts phát hiện được, bao gồm dependencies bắc cầu và các plugins. Đây là một **lệnh ghi file**, không phải chỉ xem báo cáo; nó phải được chạy ở project/lượt review phù hợp. Tệp sinh ra ban đầu cần được **xem diff và xác minh** trước khi đưa vào VCS hoặc chấp nhận trên CI.

Lựa chọn có chữ ký và checksum:

```bash
./gradlew --write-verification-metadata sha256,pgp help
```

Với signature bootstrap, Gradle có thể tự thêm keys được coi là trusted và sinh ignored-key/checksum fallback. Đó là **quy tắc tự động của bootstrap**, không phải quyết định tin cậy đã được nhân sự phê duyệt. Đọc và review danh sách key, lý do bỏ qua key, nơi lấy hash và những artifact mới.

**Khuyến nghị khi bảo vệ cả checksum và chữ ký:** bootstrap bằng `sha256` trước, review baseline; sau đó bổ sung `pgp` cùng `sha256` để có checksums cho tất cả artifacts trước khi bổ sung chữ ký. Nếu chỉ bootstrap `pgp,sha256` một lần, Gradle có thể ưu tiên chữ ký cho artifact đã ký và chỉ sinh checksum fallback cho artifact chưa ký, khiến một số artifact không có cả hai dạng bằng chứng.

### 5.4. Bước D: dùng dry-run để xem trước file sinh ra

Khi muốn xem file metadata có thể được sinh mà **không ghi đè file chính**, tài liệu Gradle hướng dẫn:

```bash
./gradlew --write-verification-metadata sha256 help --dry-run
```

Gradle tạo file xem trước tên:

```text
gradle/verification-metadata.dryrun.xml
```

`--dry-run` **không** chạy task actions, vì thế có thể bỏ sót dependencies chỉ được resolve trong lúc task thực thi. Nó không thay thế một lần generate và test đầy đủ. Đọc bản xem trước, review chênh lệch, rồi chạy bootstrap thật khi đã sẵn sàng.

### 5.5. Bước E: phê duyệt và commit

Sau khi bootstrap:

1. Xem `git diff -- gradle/verification-metadata.xml` (nếu project dùng Git).
2. Ghi module versions mới, POM, JAR, `.module`, sources/javadocs và transitive entries.
3. Đối chiếu checksum quan trọng bằng kênh độc lập; xác minh fingerprint PGP full 40 hex nếu dùng signature.
4. Phân loại `origin="Generated by Gradle"`, lý do checksum-only, ignored keys và những phần mất chữ ký.
5. Chỉ sau khi review mới ghi chú `origin="Verified"` nếu nhóm thật sự đã xác minh; không chuyển hàng loạt để “làm sạch” diff.
6. Đảm bảo version catalog, BOM/constraints và dependency lockfiles tương thích với artifact đã được duyệt.
7. Commit XML cùng những thay đổi dependency liên quan; thêm reviewer/approval theo chính sách bảo mật.
8. Chạy CI với verification `strict` và lưu report thất bại nếu có.

**Giữ cùng tham số bootstrap** trong các lần cập nhật kế tiếp nếu có thể; đổi thuật toán/tập chế độ giữa các lần khiến diff khó review. Gradle generate theo kiểu incremental: thường bổ sung records mới và giữ records cũ; nó không biết chắc record nào đã hết dùng, vì vậy phải quản lý stale entries có chủ đích.

## 6. Bài lab đầy đủ: Gradle Groovy DSL + Java 17+

Lab này minh họa **tạo metadata checksum, chạy build với strict và kiểm tra sự thay đổi bất thường trong bản sao**, không yêu cầu tạo key hay giả làm publisher. Dùng một project thực hành mới, **không sửa verification XML của sản phẩm thật để thử lỗi**.

### 6.1. Cấu trúc project

```text
artifact-trust-lab/
├── gradlew
├── gradlew.bat
├── gradle/
│   ├── wrapper/...
│   └── verification-metadata.xml   (được Gradle tạo sau)
├── settings.gradle
├── build.gradle
└── src/main/java/example/VerificationDemo.java
```

Giả định project đã được khởi tạo với Gradle Wrapper có thể chạy Java 17+, repository Maven Central được phép truy cập. Khi mới bắt đầu, file `gradle/verification-metadata.xml` **chưa tồn tại**; bạn sẽ tạo bằng lệnh bootstrap.

### 6.2. File settings.gradle

```groovy
rootProject.name = 'artifact-trust-lab'
```

### 6.3. File build.gradle

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}

application {
    mainClass = 'example.VerificationDemo'
}
```

- Plugin `application` là plugin tích hợp, tạo task `run` và hỗ trợ Java.
- `mavenCentral()` là **nguồn tìm artifact**. Nó không thay thế checksum verification.
- `implementation` yêu cầu Commons Lang 3.17.0 cho source Java.
- `application.mainClass` cho biết class chạy ứng dụng.

Không ghi sẵn một hash đoán chừng vào `verification-metadata.xml`; Gradle cần checksum **của bytes artifact thực tế**, sau đó reviewer phải xác lập độ tin cậy của giá trị đó.

### 6.4. File Java chạy được

Tạo **`src/main/java/example/VerificationDemo.java`**:

```java
package example;

import org.apache.commons.lang3.StringUtils;

public final class VerificationDemo {
    private VerificationDemo() {
    }

    public static void main(String[] args) {
        String result = StringUtils.capitalize("gradle verification");
        System.out.println(result);
    }
}
```

`StringUtils.capitalize` viết hoa ký tự đầu của chuỗi, không viết hoa mỗi từ; vì thế stdout của chương trình là:

```text
Gradle verification
```

Chạy một lần khi chưa bật verification để kiểm tra build/repository cơ bản:

```bash
./gradlew -q run --console=plain
```

Nếu project không có Gradle Wrapper hoặc không truy cập Maven Central và chưa có cache, lệnh không thể chạy như dự kiến. Đó là vấn đề thiết lập lab, không có nghĩa cơ chế checksum sai.

### 6.5. Tạo baseline checksum và review

Trong thư mục gốc project:

```bash
./gradlew --write-verification-metadata sha256 help
```

Sau lệnh, kiểm tra `gradle/verification-metadata.xml`. File tạo ra chứa các records cho những artifacts Gradle đã phát hiện/resolve, có thể gồm `commons-lang3-3.17.0.jar`, `.pom` và metadata khác. Đừng đoán **hash thực tế** hay chép giá trị SHA-256 của Commons Lang từ một ví dụ khác.

Bạn cần kiểm tra:

- Có component `group="org.apache.commons"`, `name="commons-lang3"`, `version="3.17.0"` không?
- Artifact `commons-lang3-3.17.0.jar` có `<sha256 value="..."/>` của đúng file không?
- Có checksums cho các metadata artifacts được giải quyết không?
- Có module bắc cầu, buildscript hoặc plugin dependencies nào được phát hiện ngoài dự kiến không?
- Những records nào có `origin="Generated by Gradle"` cần review?
- Có repositories/versions/tọa độ nào không được tổ chức tin cậy không?

Kiểm chứng độc lập với published checksums hoặc trang phát hành đáng tin trước khi xem baseline là “trusted”. Với production, review cả XML theo diff trong pull request. Một file XML được generate thành công chỉ chứng minh **Gradle ghi được metadata**, không phải chứng minh library hoàn toàn an toàn.

### 6.6. Chạy strict sau khi metadata được duyệt

```bash
./gradlew --dependency-verification strict -q run --console=plain
```

Nếu metadata đầy đủ, values hợp lệ và repositories có thể truy cập, **stdout của ứng dụng** vẫn là:

```text
Gradle verification
```

Khi Gradle tìm thấy file metadata, chế độ verification mặc định là `strict`; nêu rõ `--dependency-verification strict` giúp người đọc thấy chính sách thực thi của ví dụ.

Bạn cũng có thể chạy kiểm tra với:

```bash
./gradlew --dependency-verification strict test --console=plain
```

Lab không có test source, nên task `test` của plugin Java có thể kết thúc `NO-SOURCE` thay vì có các test cases. Đừng coi `test` không chạy test như bằng chứng mọi artifact đã được kiểm tra; dùng cả `run` và những task thực sự resolve classpaths.

### 6.7. Mô phỏng checksum mismatch **chỉ trong bản sao lab**

Để hiểu failure mà không cần sửa JAR từ repository:

1. Giữ một bản sao XML đã review (ví dụ thông qua Git).
2. Trong **bản sao lab**, tìm chính xác component Commons Lang 3.17.0, artifact `commons-lang3-3.17.0.jar`.
3. **Chỉ để thử nghiệm**, thay giá trị `sha256` đang được ghi trong entry này bằng 64 ký tự `0`, giữ nguyên XML hợp lệ. Đó là một **expected checksum sai có chủ đích**, không phải giá trị được tin cậy.
4. Chạy lệnh:

```bash
./gradlew --dependency-verification strict run --console=plain
```

Trong lần Gradle kiểm tra artifact đó, build phải **FAIL**, với thông tin tương tự:

```text
Dependency verification failed for configuration ':runtimeClasspath' ...
expected a 'sha256' checksum ... but was ...
```

Đây là **trích đoạn minh họa**: lỗi có thể xuất hiện sớm hơn ở `compileClasspath`, nên **không** cố khớp chính xác tên configuration hoặc format stderr. Điểm cốt lõi: `strict` không chấp nhận file có hash không khớp giá trị expected.

5. **Khôi phục XML gốc đã được tin cậy** từ VCS hoặc bản sao trước thí nghiệm. Chạy lại `./gradlew --dependency-verification strict -q run`, xác nhận ứng dụng in `Gradle verification`.

**Không khắc phục một mismatch thật** bằng cách tự sinh hash mới rồi commit ngay. Mismatch là tín hiệu cần điều tra dữ liệu/repository/nguồn phát hành; bài lab chỉ giả lập để quan sát phản ứng của Gradle.

### 6.8. Lệnh trên Windows PowerShell

Dùng các lệnh tương ứng:

```powershell
.\gradlew.bat -q run --console=plain
.\gradlew.bat --write-verification-metadata sha256 help
.\gradlew.bat --dependency-verification strict -q run --console=plain
```

Các lệnh này không cần cú pháp nối dòng đặc biệt; không có `$n` hay escape PowerShell trong chuỗi source. Nếu cần xem hash bằng `Get-FileHash`, bạn phải chỉ vào một **file thực sự đã tải về** và tự đối chiếu nó với hash đã được duyệt.

## 7. Ví dụ Java 17+ tự tính SHA-256 để hiểu kiểm tra byte

Tạo file **`Sha256Example.java`** độc lập với project Gradle:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;

public class Sha256Example {
    public static void main(String[] args) throws Exception {
        byte[] content = "abc".getBytes(StandardCharsets.UTF_8);
        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(content);
        System.out.println(HexFormat.of().formatHex(digest));
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac Sha256Example.java
java Sha256Example
```

**Stdout chính xác** với chuỗi ASCII `abc`:

```text
ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
```

Đây là SHA-256 test vector chuẩn của chuỗi `abc`, không phải checksum của Commons Lang. Khi kiểm tra một **file JAR thực**, phải hash toàn bộ bytes của file, không hash tên JAR, URL, version hoặc bản mô tả trong POM. Trên Linux/macOS có thể dùng công cụ `sha256sum` với đường dẫn file thực; trên Windows PowerShell dùng `Get-FileHash`. Dù hai công cụ cho cùng digest, kết quả vẫn chỉ đáng tin khi **expected hash** đến từ một nguồn đã được xác minh.

Cách làm của Java ở đây là để hiểu khái niệm; không nên thay thế dependency verification của Gradle bằng một task Java tự hash mọi file khi Gradle đã cung cấp cơ chế chuẩn.

## 8. Kiểm tra PGP: trusted keys, ignored keys và keyring

### 8.1. Trusted keys không đồng nghĩa chỉ tải được public key

Một PGP signature có thể hợp lệ nhưng được ký bằng public key **chưa có trong chính sách trusted**. Gradle sẽ báo kiểu “signature passed, but key is not trusted”. Chỉ cần key server trả về khóa là **chưa đủ để tin key đó**.

Gradle dùng **full fingerprint 40 ký tự hexadecimal** cho `pgp` và `trusted-key`; không nên nhập key ID ngắn dễ bị trùng/giả. Một đoạn minh họa từ tài liệu Gradle có dạng:

```xml
<trusted-keys>
    <trusted-key
        id="06D34ED6FF73DE368A772A781063FE98BCECB758"
        group="com.puppycrawl.tools"
        name="checkstyle"/>
</trusted-keys>
```

Đoạn trên chỉ minh họa **cấu trúc và scope**. Đừng tự thêm fingerprint này cho artifact khác hoặc lấy ví dụ như một quyết định tin cậy của dự án. Reviewer phải kiểm tra fingerprint với chính publisher, đồng thời giới hạn tin cậy về đúng module/group cần thiết.

### 8.2. Ignored keys là ngoại lệ cần giải thích

Một số artifact có chữ ký từ khóa mà Gradle không thể tìm hoặc không tin cậy. File `verification-metadata.xml` có thể chứa `<ignored-keys>` với lý do cụ thể. Khi bỏ qua khóa, Gradle không dùng khóa đó để xác minh; **nếu không còn chữ ký đáng tin nào khác, cần checksum fallback**.

Tránh biến `ignored-keys` thành “danh sách cho qua mọi chữ ký có vấn đề”. Nếu key không tìm thấy, kiểm tra website publisher, key server hợp lệ và khả năng xuất key về keyring nội bộ. Nếu signature **không khớp**, đây là lỗi nghiêm trọng hơn việc key chưa được tin cậy, phải điều tra artifact.

### 8.3. Key servers và local keyrings

Gradle có thể tìm public key từ key servers và lưu keyring phục vụ xác minh. Hai định dạng được hỗ trợ gồm:

- `gradle/verification-keyring.gpg`: binary keyring.
- `gradle/verification-keyring.keys`: ASCII-armored, dễ review diff.

Có thể dùng:

```bash
./gradlew --write-verification-metadata pgp,sha256 --export-keys
```

hoặc chỉ export keys nếu metadata đã được quản lý:

```bash
./gradlew --export-keys
```

Theo tài liệu Gradle, nếu không cấu hình `keyring-format`, lệnh export có thể tạo **cả hai định dạng**; nên commit **một định dạng phù hợp** thay vì tự động thêm cả hai. Nếu chọn armored, cấu hình:

```xml
<configuration>
    <verify-metadata>true</verify-metadata>
    <verify-signatures>true</verify-signatures>
    <keyring-format>armored</keyring-format>
</configuration>
```

Đây chỉ là **fragment bên trong root verification-metadata**, không phải file XML đầy đủ. Keyring lưu **public keys**, không phải private signing keys. Commit public keyring đã review giúp CI hạn chế phụ thuộc key server và hỗ trợ audit; tuy nhiên việc có keyring không tự ghi danh sách trusted fingerprints, vẫn cần `verification-metadata.xml`.

### 8.4. Khi nào không nên tin signature?

- Chữ ký hợp lệ nhưng key fingerprint chưa được xác minh bằng kênh của maintainer.
- Key được bootstrap tự động mà không ai review.
- Key dùng thuật toán/chuỗi tin cậy không đáp ứng chính sách bảo mật.
- Artifact đến từ repository lạ hoặc có dấu hiệu repository shadowing.
- Publisher thông báo key bị thu hồi/compromised.
- Signature của JAR không khớp bytes đã tải.

Không cố “sửa” bằng cách đổi tất cả verification modes thành `off` hoặc tin toàn bộ group ở phạm vi quá rộng. Nếu không giải quyết ngay được, dừng promotion và chuyển cho người chịu trách nhiệm security/supply chain.

## 9. Ba chế độ dependency verification

Gradle cho phép:

| Mode | Cách hoạt động | Khi cân nhắc |
| --- | --- | --- |
| **`strict`** (mặc định khi verification bật) | Báo lỗi và chặn build sớm khi artifact không đạt chính sách xác minh. | **CI/build phát hành**, bước bảo đảm an toàn trước merge/deploy. |
| **`lenient`** | Hiển thị verification failures nhưng vẫn cho phép build tiếp tục. | Chẩn đoán hoặc khảo sát ngắn hạn trên môi trường cách ly; **không dùng để phê duyệt release**. |
| **`off`** | Bỏ qua dependency verification. | Không nên dùng như giải pháp cho CI/release; làm mất lớp bảo vệ. |

Cú pháp CLI:

```bash
./gradlew --dependency-verification strict build
./gradlew --dependency-verification lenient build
./gradlew --dependency-verification off build
```

Ba dòng là **ba lựa chọn so sánh**, **không** phải chuỗi lệnh nên chạy liên tiếp trong pipeline. Trong hướng dẫn lab/CI nên dùng strict. Lenient/off được trình bày để đọc và nhận diện cờ; bật hai mode đó là quyết định giảm an toàn cần kiểm soát.

Có thể cấu hình bằng Gradle property:

```properties
org.gradle.dependency.verification=strict
org.gradle.dependency.verification.console=verbose
```

`console=verbose` hữu ích trên CI vì Gradle sẽ in thêm chi tiết verification failure thay vì yêu cầu xem HTML report ở máy developer. Thuộc tính này không làm thay đổi checksum/trust decisions.

**Đừng nhầm** `--dependency-verification strict` với `strictly '1.2.3'` của rich version constraints hoặc `LockMode.STRICT` của dependency locking. Các từ cùng mang nghĩa “strict” nhưng áp dụng cho **ba cơ chế khác nhau**.

## 10. Đọc lỗi verification và quy trình xử lý an toàn

Một build có thể lỗi **vì metadata thiếu**, **vì bytes sai**, **vì chữ ký chưa tin cậy**, hoặc **vì chữ ký sai thật**. Các trường hợp này cần phản ứng khác nhau.

### 10.1. Checksum chưa có trong XML

Lỗi thường có nội dung tương tự:

```text
Dependency verification failed for configuration ':compileClasspath'
On artifact some-library-1.0.jar: checksum is missing from verification metadata.
```

Nguyên nhân: module/artifact mới, version mới, metadata POM mới, plugin mới hoặc một dependency bắc cầu chưa được đưa vào XML. Đây **chưa phải bằng chứng artifact bị sửa**, nhưng cũng **chưa được phê duyệt**.

Cách làm:

1. Xem đúng module, version và tên artifact mà Gradle báo.
2. Kiểm tra đường dependency, repository nguồn và lý do xuất hiện.
3. Tìm checksum/chữ ký của publisher qua kênh đáng tin.
4. Bootstrap metadata bổ sung ở bản làm việc đã được kiểm soát.
5. Review diff và xác minh trước khi commit.
6. Chạy lại strict và test.

Không tự thêm `<trust group=".*" regex="true"/>` chỉ để vượt lỗi.

### 10.2. Expected checksum khác actual checksum

Ví dụ thông điệp rút gọn:

```text
On artifact some-library-1.0.jar:
expected a 'sha256' checksum of '...'
but was '...'
```

Đây là tình huống **nghiêm trọng** vì file không khớp nội dung được chấp nhận. Đừng tự cho rằng do cache lỗi. Phải điều tra:

- Có tải đúng group/name/version/classifier và repository không?
- Có mirror thay đổi bytes hoặc nhà phát hành re-publish artifact cùng version?
- Artifact cached có bị hỏng/thay đổi, hoặc có proxy trung gian không?
- Hash expected có được duyệt đúng file, có typo trong XML hoặc nhầm POM/JAR không?
- Publisher có thông báo đổi key, rút release hoặc sự cố supply chain không?

Nếu đã xác định cache local bị hỏng bằng nguồn độc lập, có thể bỏ đúng file cache bị lỗi để Gradle tải lại, **không xóa cả cache mù quáng** và không sửa expected hash để phù hợp bytes mới. Khi thật sự có hai bản bytes được publisher hợp lệ công bố (đặc biệt POM khác giữa repositories), Gradle có hỗ trợ `also-trust` cho nhiều checksums. **Chỉ thêm also-trust sau khi xác minh cả hai giá trị**.

### 10.3. Signature hợp lệ nhưng key không trusted

Trạng thái kiểu:

```text
Artifact was signed with key ... and passed verification,
but the key isn't in your trusted keys list.
```

Giải pháp không phải thêm key ID ngắn vào mọi component. Cần kiểm tra full fingerprint, danh tính publisher, kênh phát hành, phạm vi group/module và cuối cùng mới thêm trusted key có giới hạn thích hợp. Nếu chưa xác minh được, giữ build chặn ở strict.

### 10.4. Signature không khớp

Thông báo kiểu `signature didn't match` là dấu hiệu artifact/chữ ký không tương ứng. Điều tra repository, mirror, bytes, public key và thông báo nhà phát hành; đừng đánh dấu key thành ignored và chấp nhận artifact vô điều kiện. Nếu có tình huống publisher thực sự phát hành bản thay thế, phải có bằng chứng độc lập và quy trình phê duyệt rõ ràng.

### 10.5. Artifact bị đánh dấu untrusted do chính sách quá rộng hoặc sai scope

Một `<trusted-key>` áp dụng cho một module không có nghĩa nó đáng tin cho mọi module khác. Kiểm tra scope group/name và tên file. Một `<trusted-artifacts>` rule có thể bỏ qua verification toàn bộ nhóm; kiểm tra rule này trước khi coi một build pass là bằng chứng bảo mật.

Đọc HTML verification report mà Gradle tạo khi thất bại hoặc bật:

```properties
org.gradle.dependency.verification.console=verbose
```

Trong môi trường CI, giữ lại report và log cần thiết nhưng cẩn thận với URL repository nội bộ, thông tin nhận dạng và secrets.

## 11. Trusted artifacts: ngoại lệ không phải chứng nhận an toàn

Gradle cho phép định nghĩa:

```xml
<configuration>
    <trusted-artifacts>
        <trust group="com.mycompany" name="internal-fixture" version="1.0"
               reason="Approved internal exception"/>
    </trusted-artifacts>
</configuration>
```

Đây chỉ là **fragment minh họa**, không phải đề xuất áp dụng ngoại lệ này. Các artifact khớp rule sẽ được **tin ngay và bỏ qua verification**, chứ không được kiểm tra bởi checksum hoặc chữ ký. Một rule `group="com.mycompany"` có thể rất rộng; nếu artifact nội bộ/mirror bị compromise, ngoại lệ có thể làm mất cảnh báo.

Hãy chọn thứ tự ưu tiên:

1. **Tốt nhất:** xuất bản artifact ổn định, có checksum/chữ ký, xác minh bằng XML như external dependencies.
2. **Nếu publisher không ký:** dùng checksum đã phê duyệt thay vì bỏ qua toàn bộ.
3. **Nếu có lý do kỹ thuật ngoại lệ:** giới hạn đúng group/name/version/file, ghi reason, owner, thời hạn đánh giá lại và tác động.
4. **Không dùng:** wildcard trust cho toàn repository/tất cả artifacts chỉ để build xanh.

Tương tự, bỏ xác minh `-sources.jar` hoặc `-javadoc.jar` để IDE import nhanh hơn là một quyết định giảm bảo vệ, vì tài liệu/nguồn cũng có thể bị thay đổi. Gradle hỗ trợ rule tin cậy theo file pattern nhưng không nên bật theo thói quen.

## 12. Dependency verification và dependency locking phối hợp ra sao?

Hai file thường được quản lý cùng PR khi nâng dependency:

```text
gradle.lockfile                  -> phiên bản cuối được resolve
gradle/verification-metadata.xml -> checksum/chữ ký của các file tin cậy
```

Ví dụ:

- `gradle.lockfile` giữ `org.apache.commons:commons-lang3:3.17.0` trong configuration đã khóa.
- `verification-metadata.xml` giữ checksum cho JAR/POM/metadata có liên quan tới version 3.17.0.
- Nếu build yêu cầu 3.18.0 và cập nhật lock state, XML vẫn cần **bằng chứng kiểm tra artifact của version mới**.
- Nếu artifact ở 3.17.0 bị thay đổi bytes nhưng lock vẫn ghi 3.17.0, việc kiểm tra checksum giúp phát hiện.

Các lệnh `--write-locks` và `--write-verification-metadata` **đều là thao tác có thể ghi file**, nhưng ghi **những dữ liệu khác nhau**. Không chạy chúng như bước “xem thông tin” rồi commit bất kể diff. Phân biệt:

```bash
# Chỉ minh họa hai cơ chế, mỗi lệnh ghi trạng thái riêng:
./gradlew dependencies --write-locks
./gradlew --write-verification-metadata sha256 help
```

Lệnh đầu có ý nghĩa khi đã bật dependency locking cho configurations phù hợp. Lệnh thứ hai tạo/cập nhật verification metadata. Với nâng cấp production, thay dependency và xử lý lock/verification trong **một thay đổi được review** để graph và các bằng chứng ăn khớp.

Không dùng dependency locking để “tin artifact” và cũng không dùng checksum để “khóa version” của transitive graph. Nếu ứng dụng cần xác nhận thiếu CVE, dùng SCA/advisory và cập nhật dependency policy song song.

## 13. Bảo trì verification metadata qua các lần nâng cấp

### 13.1. Thêm module mới

Nếu build bổ sung:

```groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
```

vào một project đã bật verification strict nhưng XML chưa biết module đó, bước resolve có thể fail do thiếu checksum. Hãy lấy metadata mới theo quy trình bootstrap + audit. Không chuyển CI thành lenient vĩnh viễn.

### 13.2. Nâng version

Khi thay `3.17.0` thành một version mới đã kiểm tra:

1. Review changelog, license, CVEs, repository nguồn.
2. Xác nhận requested/selected versions qua `dependencyInsight`.
3. Bootstrap records cho artifacts mới.
4. Kiểm tra checksums/signatures **theo đúng version và file**.
5. Review XML diff; không xóa tùy tiện entries module vẫn còn xuất hiện trong các configuration khác.
6. Nếu bật dependency locking, cập nhật lock state có chủ đích.
7. Chạy CI strict và test/integration/smoke phù hợp.

Gradle không tự biết entry cũ có còn cần ở một task ít chạy hay không, nên nó không tự xóa hết stale records. Dọn XML theo graph thực và lịch chạy của CI, không chỉ theo một report `runtimeClasspath`.

### 13.3. Nhiều repositories hoặc mirror có POM khác nhau

Cùng module/version đôi khi có POM bytes khác nhau ở hai repository do whitespace, timestamps hoặc publication policy. Đừng tự tin cả hai là hợp lệ chỉ vì tọa độ giống nhau. So sánh metadata, transitive dependencies và nguồn xuất bản; khi đã xác minh hai bản đều được publisher chấp nhận, Gradle cho phép ghi thêm checksum qua `also-trust`:

```xml
<artifact name="apache-13.pom">
    <sha256 value="2fafa38abefe1b40283016f506ba9e844bfcf18713497284264166a5dbf4b95e">
        <also-trust value="ff513db0361fd41237bef4784968bc15aae478d4ec0a9496f811072ccaf3841d"/>
    </sha256>
</artifact>
```

Đoạn trên lấy dạng dữ liệu từ tài liệu Gradle cho một artifact POM cụ thể; **không** copy vào component bất kỳ khác. Với `also-trust`, Gradle có thể chấp nhận một trong các hashes đã duyệt, nên thêm giá trị mới là quyết định bảo mật, không chỉ là sửa lỗi cú pháp.

### 13.4. Files phụ trợ tải bởi IDE, Gradle plugin và included builds

Một lần `./gradlew help` không nhất thiết kích hoạt mọi đường tải artifact trong các task custom hoặc IDE. Một plugin có thể tải runtime dependency muộn; IDE có thể tải `sources` hoặc `javadocs`; build có included builds. Hãy xây checklist các command representative (compile, test, codegen, packaging, plugin tasks, tooling) để metadata bao phủ bề mặt thật sự được dùng.

Nếu source/Javadoc tải sau nhưng chưa có verification record, strict có thể báo thiếu metadata. Không vội mở trust wildcard; cập nhật records qua quy trình thẩm định phù hợp.

## 14. Những bẫy bảo mật và giới hạn cần hiểu

| Sai lầm | Vì sao nguy hiểm hoặc không chính xác | Cách đúng |
| --- | --- | --- |
| “Generate XML xong là artifact trusted.” | Bootstrap ghi lại artifact hiện tại, kể cả nếu nguồn đã bị compromise. | Review checksum/key fingerprint qua nguồn độc lập trước khi duyệt. |
| “SHA-256 chứng minh tác giả là ai.” | Hash chỉ chứng minh bytes khớp giá trị kỳ vọng. | Đối chiếu publisher, ký PGP/trusted key hoặc kênh độc lập. |
| “Chữ ký PGP pass tức key chắc chắn của tác giả.” | Key có thể thuộc người khác hoặc chưa được tin cậy. | Xác minh full fingerprint với maintainer và giới hạn scope. |
| “Lockfile đủ để ngăn JAR bị thay.” | Lock chủ yếu pin versions, không hash bytes JAR. | Dùng `verification-metadata.xml` song song. |
| “Verification giúp hết CVE.” | Artifact nguyên bản vẫn có thể chứa lỗ hổng. | Kết hợp SCA/CVE scanning và upgrade. |
| Dùng `--dependency-verification off` để CI xanh | Bỏ hẳn lớp kiểm tra integrity/provenance. | Giữ strict, điều tra lỗi và cập nhật metadata đã review. |
| Giữ `lenient` khi release | Artifacts không được phê duyệt vẫn có thể được sử dụng. | Dùng lenient cho khảo sát cô lập, không phải gate phát hành. |
| Khi mismatch, chép actual hash thành expected ngay | Có thể phê duyệt artifact độc hại. | Dừng, so sánh nguồn độc lập và điều tra mirror/cache. |
| Dùng `trusted-artifacts` wildcard | Gradle bỏ qua verification cho phạm vi lớn. | Giảm ngoại lệ, pin scope, theo dõi owner và reason. |
| Bật `verify-metadata=false` để rút ngắn XML | Metadata POM/.module có thể bị thay và kéo transitive nguy hiểm. | Duy trì metadata verification nếu policy bảo mật cần. |
| Tin key ID ngắn hoặc key server mặc định | Key có thể sai người và ID ngắn dễ nhầm. | Đối chiếu full 40-hex fingerprint từ publisher. |
| Tin mọi `origin="Verified"` | origin chỉ là chú thích, không phải bằng chứng crypto. | Lưu tài liệu/approval thực tế trong review. |
| Xóa XML rồi regenerate khi có lỗi | Mất baseline từng được phê duyệt và trust on first use lần nữa. | Điều tra từng artifact, review diff, khôi phục khi sai. |
| Không kiểm tra transitive dependencies | Một JAR trực tiếp có thể kéo nhiều artifact khác. | Bootstrap và audit trên graph thật. |
| Chỉ chạy `help --dry-run` rồi tuyên bố toàn build đã đủ metadata | Không resolve các dependencies chỉ tải ở task execution. | Chạy representative tasks và strict CI. |
| Tin rằng XML xác minh mọi file download bởi shell/curl/custom task | Ngoài cơ chế dependency management của Gradle không thuộc phạm vi tự động. | Quản lý nguồn ngoài bằng kiểm tra checksum/signature riêng. |
| Coi checksum của Maven Central và hash từ cùng CDN là hai nguồn độc lập | Cùng trust boundary có thể bị cùng kẻ tấn công chi phối. | So chéo với publisher hoặc kênh độc lập. |
| Xóa stale entries không kiểm tra buildSrc/variants | Module có thể còn được dùng bởi plugin hoặc task hiếm. | Kiểm tra toàn bộ phạm vi build và CI matrix. |
| Tắt TLS validation để tải key hoặc artifact | Mở đường cho man-in-the-middle. | Dùng HTTPS và CA/trust store phù hợp. |

## 15. Hướng dẫn xử lý sự cố theo quyết định

```text
Build thất bại ở dependency verification?
|
+-- Missing checksum / missing verification metadata?
|      |
|      +-- Artifact mới hoặc version mới?
|      |      -> Xác minh nguồn, bootstrap phần mới, review diff.
|      |
|      +-- POM/.module/sources/Javadoc mới?
|             -> Xem đúng tên file và scope, cập nhật metadata.
|
+-- Actual SHA-256 khác expected?
|      -> Dừng tự động phê duyệt.
|      -> Kiểm tra publisher, repository, cache, mirror, checksum độc lập.
|      -> Chỉ điều chỉnh expected/also-trust khi có bằng chứng hợp lệ.
|
+-- Signature đúng nhưng key chưa trusted?
|      -> Xác minh full fingerprint bằng kênh chính thức.
|      -> Thêm key vào đúng scope nếu được duyệt.
|
+-- Signature không khớp hoặc key bị nghi compromise?
|      -> Từ chối artifact, điều tra publisher/mirror.
|
+-- Module chưa resolve / 401 / 404 / SSL / No matching variant?
       -> Đây có thể là lỗi resolution/repository, chưa phải checksum.
       -> Đọc nguyên nhân gốc và xử lý tọa độ, quyền hoặc attributes.
```

Khi lỗi không nằm ở verification nhưng do repository, không “sửa” bằng cách thêm hash. Khi lỗi ở checksum/signature, không “sửa” bằng cách thay `--refresh-dependencies` và hy vọng mọi thứ qua. `--refresh-dependencies` có thể làm Gradle kiểm tra lại caches/metadata, nhưng không thay expected checksum và cũng không chứng minh artifact mới an toàn.

## 16. Bài tập thực hành

**Bài 1 — Integrity và provenance:** Giải thích vì sao SHA-256 đúng với một JAR nhưng lấy cùng repository bị tấn công không chứng minh publisher đáng tin. Nếu có PGP signature, nhóm cần thêm bước gì trước khi trust public key?

**Bài 2 — File và phạm vi:** Trong root build có `:app`, `:lib`, `buildSrc` và một included build, file verification đặt ở đâu? Vì sao chỉ duyệt một JAR trực tiếp có thể chưa bao phủ cả build?

**Bài 3 — Bootstrap:** Từ project lab mục 6, chạy `./gradlew --write-verification-metadata sha256 help`. Tìm entry JAR và POM của Commons Lang. Đọc `origin` và xác định các bước cần làm trước khi chấp nhận baseline.

**Bài 4 — Strict mode:** Trong bản sao lab, cố ý đổi SHA-256 của một artifact sang 64 chữ số `0`. Chạy strict, quan sát lỗi và **khôi phục XML đã được review**. Vì sao không được commit hash giả?

**Bài 5 — Locking khác verification:** Giả sử lockfile vẫn chọn `3.17.0` nhưng mirror trả JAR khác bytes. Cơ chế nào phát hiện gì? Nếu nâng lên `3.18.0`, cần quản lý cả lock state và verification metadata thế nào?

**Bài 6 — Không có chữ ký:** Một artifact đã xác minh độc lập nhưng không có PGP `.asc`. Có nên bỏ qua hoàn toàn? Hãy trình bày cách dùng checksum SHA-256 fallback được review.

**Bài 7 — Untrusted key:** Một PGP signature hợp lệ nhưng key chưa có trong trusted list. Có nên tin fingerprint vì keyserver trả về đúng ID? Làm thế nào để xác minh danh tính và giới hạn trust theo module?

**Bài 8 — XML lớn:** Trong file metadata có nhiều records của version đã cũ. Vì sao không tự xóa tất cả bằng cách so sánh một `runtimeClasspath` duy nhất? Những source sets, plugin và task execution nào có thể vẫn cần bản cũ?

**Bài 9 — CI:** Thiết kế một gate: bootstrap trên branch review, so checksum/signature, xét CVE, lưu diff, chạy strict trong CI, chạy tests. Khi một nhà phát hành re-publish POM cùng version nhưng nội dung hơi khác, quy trình duyệt `also-trust` cần thông tin gì?

**Bài 10 — Hash bằng Java:** Compile `Sha256Example.java` ở mục 7. Giải thích vì sao output là hash của bytes `abc` và không thể copy hash đó vào entry Commons Lang trong verification XML.

### Đáp án nhanh

1. **File verification nằm ở đâu?** `gradle/verification-metadata.xml` của root build.
2. **Định nghĩa file là đã bật verification chưa?** Có, Gradle nhận file để thực thi chính sách, nhưng file trống không đủ cho external dependencies.
3. **Checksum SHA-256 chứng minh gì?** Bytes khớp expected hash **đã được tin**.
4. **PGP signature giải quyết phần nào?** Chữ ký từ key; cần kiểm tra danh tính/độ tin cậy của key ngoài việc kiểm chứng toán học.
5. **Mode mặc định của verification?** `strict` khi verification được bật.
6. **`lenient` có thích hợp cho release không?** Không; nó có thể cho build tiếp tục dù verification báo lỗi.
7. **`--write-verification-metadata` là read-only?** Không; nó tạo/cập nhật file.
8. **`--dry-run` với lệnh bootstrap tạo file gì?** `gradle/verification-metadata.dryrun.xml`, có thể thiếu resolution lúc task chạy.
9. **`origin="Verified"` là bằng chứng mật mã?** Không; đó là metadata chú thích.
10. **Tại sao chưa đủ nếu chỉ có gradle.lockfile?** Lock versions, không verify bytes artifact.
11. **Gradle có tự quét CVE bằng verification không?** Không.
12. **Trusted-artifacts rule làm gì?** Cho artifact khớp rule bỏ qua verification, cần cân nhắc bảo mật.
13. **Một artifact có nhiều hash do repository khác nhau thì sao?** Điều tra nguồn, chỉ dùng `also-trust` nếu đã xác minh mọi hash được chấp nhận.
14. **Thư viện SNAPSHOT/changing được Gradle verify như immutable dependency không?** Không; theo tài liệu Gradle có các ngoại lệ cho changing dependencies.
15. **Checksum mismatch thật cần làm đầu tiên?** Dừng phê duyệt, giữ evidence, đối chiếu nguồn và tìm nguyên nhân.

## 17. Tài liệu tham khảo chính thức

- **Gradle — Verifying Dependencies / Securing Dependencies**, file XML, SHA-256, PGP, trusted keys, modes, bootstrap, troubleshooting: https://docs.gradle.org/current/userguide/dependency_verification.html
- **Gradle — Securing Dependencies**, integrity, authenticity và vulnerability screening: https://docs.gradle.org/current/userguide/securing_dependencies.html
- **Gradle — Locking Versions**, lock state và khác biệt với kiểm tra bytes artifact: https://docs.gradle.org/current/userguide/dependency_locking.html
- **Gradle — Dependency Resolution Basics**, graph/module/variant/artifact: https://docs.gradle.org/current/userguide/dependency_resolution_basics.html
- **Gradle — Dependency Caching**, metadata và artifact cache: https://docs.gradle.org/current/userguide/dependency_caching.html
- **Gradle — Command-Line Interface**, `--write-verification-metadata`, `--dependency-verification`, `--export-keys`: https://docs.gradle.org/current/userguide/command_line_interface.html
- **Gradle — Viewing and Debugging Dependencies**, `dependencies` và `dependencyInsight`: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
- **Gradle — Securing Repositories**, HTTPS, mirror và chain of trust: https://docs.gradle.org/current/userguide/securing_repositories.html
- **Gradle — Verification Metadata XSD** (định dạng XML/schema): https://schema.gradle.org/dependency-verification/dependency-verification-1.4.xsd

**Tổng kết:** `verification-metadata.xml` mô tả **những artifact và khóa nào đã được nhóm chấp thuận để Gradle kiểm tra**, thông qua hash của từng file và PGP fingerprints. Lệnh bootstrap giúp **thu thập dữ liệu**, không giúp tự động **chứng minh nguồn đáng tin**. Quy trình đúng là xác định publisher, lấy bằng chứng độc lập, review XML và lockfiles, chạy CI strict, xử lý mismatch như một sự cố cần phân tích, rồi mới chấp nhận artifact vào chuỗi cung ứng.