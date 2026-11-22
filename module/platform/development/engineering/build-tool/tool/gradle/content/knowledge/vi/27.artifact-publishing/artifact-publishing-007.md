# Ký artifact bằng Gradle Signing plugin và quản lý khóa bên ngoài source

## 1. Mục tiêu và vấn đề thực tế

Một nhóm Java có thể tạo **JAR**, **sources JAR**, **Javadoc JAR** và **Maven publication** bằng Gradle. Nhưng khi một artifact được tải từ repository, người dùng còn cần biết: **nội dung đó có bị sửa đổi sau khi được bên phát hành ký không, và khóa ký thuộc về ai?** Đó là lý do quy trình xuất bản thường có **chữ ký số**.

Gradle cung cấp **Signing plugin** để ký artifact và metadata bằng **OpenPGP**. Chữ ký thường được phát hành ở dạng tệp **.asc** nằm cạnh JAR/POM/module metadata. Một bên nhận có thể dùng **public key đáng tin cậy** để kiểm chứng nội dung chưa bị thay đổi kể từ khi người nắm private key ký.

Tuy nhiên, việc có chữ ký **không tự làm artifact an toàn**. Nếu private key bị lộ, CI bị xâm nhập, khóa công khai không được xác thực từ kênh đáng tin hoặc mã đã chứa lỗ hổng, chữ ký vẫn có thể hợp lệ về mặt mật mã. Signing là một lớp của **software supply-chain security**, không thay thế kiểm thử, dependency verification, SBOM, provenance, code review và quyền phát hành.

Bài thuộc nhóm **Xuất bản artifact** của **Build Tool Gradle**, trực tiếp giải quyết **“Ký artifact bằng Signing plugin và quản lý khóa bên ngoài source”**.

Sau khi học, bạn có thể:

1. Giải thích chữ ký số OpenPGP, private/public key, fingerprint, passphrase và detached signature.
2. Biết Signing plugin cung cấp task nào và cách liên kết với **maven-publish**.
3. Ký **MavenPublication**, task output hoặc configuration artifacts bằng cú pháp Gradle Groovy DSL.
4. Dùng **useInMemoryPgpKeys(...)** để nhận private key từ biến môi trường/CI secret store, không viết private key trong repository.
5. Biết lựa chọn **useGpgCmd()** khi muốn GnuPG và gpg-agent giữ khóa ngoài Gradle build script.
6. Thiết kế signing bắt buộc với release và không bắt buộc cho snapshot/local development theo chính sách.
7. Chạy ví dụ **Java 17 + Gradle** tạo JAR, sources/Javadoc JAR, POM, Gradle Module Metadata và signatures.
8. Dùng **gpg --verify** kiểm chứng detached signature bằng public key được xác thực.
9. Phân biệt **sign**, **publish**, **publishToMavenLocal**, **assemble** và **build**, và tránh ký trước rồi thay đổi bytes.
10. Cấu hình CI release an toàn, không cấp khóa cho pull request không tin cậy, không in secrets và kiểm tra đầy đủ kết quả.
11. Chẩn đoán các lỗi missing credentials, wrong passphrase, missing signature, fingerprint mismatch, revoked/expired key và publication task wiring.
12. Đặt quy trình rotation, revocation, backup, least privilege, secret retention và audit.

## 2. Mô hình tư duy: build, ký, xuất bản, xác minh

~~~text
Source code + dependency graph
               |
               v
        Gradle Java build
        compile / test / jar
               |
               +-- JAR
               +-- Sources JAR
               +-- Javadoc JAR
               +-- POM
               +-- Gradle Module Metadata
               |
               v
       Signing plugin Sign task
          Private OpenPGP key
     (CI secret / gpg-agent / vault)
               |
               v
        Detached *.asc signatures
               |
               v
        Maven publication/repository
               |
               v
       Consumer downloads artifacts
               |
               v
      Verify with trusted public key
               |
               +-- Valid signature for these bytes?
               +-- Expected full fingerprint?
               +-- Key current/revoked?
               +-- Artifact coordinate/version?
~~~

Phân biệt:

- **Build artifact:** tạo JAR/POM/module metadata.
- **Sign artifact:** dùng private key tạo chữ ký xác thực bytes của từng tệp.
- **Publish artifact:** upload artifact, metadata và signatures tới repository.
- **Verify artifact:** kiểm tra chữ ký dựa trên public key và danh tính/fingerprint mong đợi.
- **Trust artifact:** quyết định sử dụng artifact dựa trên cả chữ ký, nguồn phân phối, review, SBOM, kiểm thử và chính sách.

Một **.asc** không phải bản mã hóa của JAR: JAR vẫn có thể được đọc công khai. Detached signature giúp **kiểm chứng tính toàn vẹn và mối liên hệ với khóa ký**, không nhằm giữ bí mật nội dung.

## 3. OpenPGP, khóa và chữ ký rời

### 3.1. Public key và private key

Một cặp OpenPGP key gồm:

- **Private/secret key**: dùng để tạo chữ ký; phải được bảo vệ, không commit, không in ra log.
- **Public key**: cho consumer kiểm chứng chữ ký; có thể được phân phối rộng, nhưng phải xác thực danh tính/fingerprint.
- **Fingerprint**: định danh khóa mạnh hơn short key ID; dùng để đối chiếu trên kênh đáng tin.
- **Passphrase**: bảo vệ private key khi lưu trữ; không phải public key, và không thay thế phân quyền trên key material.
- **Key ID**: một phần của fingerprint; hữu ích để tìm khóa nhưng short ID có thể bị trùng, không nên coi là bằng chứng tin cậy duy nhất.
- **Signing subkey**: subkey chuyên dùng để ký, có thể rotate/revoke mà không cần cung cấp master private key cho CI.

Private key có thể bị lộ qua source repository, build log, command history, CI environment dump, untrusted PR build, artifact upload hoặc máy runner còn giữ secrets sau job. Do đó việc **không commit key** mới chỉ là yêu cầu tối thiểu.

### 3.2. Detached ASCII-armored signature

Một Maven repository có thể chứa:

~~~text
signed-artifact-lab-1.0.0.jar
signed-artifact-lab-1.0.0.jar.asc
signed-artifact-lab-1.0.0.pom
signed-artifact-lab-1.0.0.pom.asc
signed-artifact-lab-1.0.0-sources.jar
signed-artifact-lab-1.0.0-sources.jar.asc
signed-artifact-lab-1.0.0-javadoc.jar
signed-artifact-lab-1.0.0-javadoc.jar.asc
signed-artifact-lab-1.0.0.module
signed-artifact-lab-1.0.0.module.asc
~~~

Danh sách trên là **các tệp có thể xuất hiện** khi cấu hình publication gồm JAR, sources, Javadoc và Gradle metadata; không phải mọi Maven repository đều lưu/hiển thị mọi tệp giống nhau. Những ký hiệu **.asc** là detached signatures: **mỗi tệp artifact/metadata có một signature tương ứng**.

**Một chữ ký của JAR không tự ký POM hoặc Gradle Module Metadata.** Những file này cũng là một phần của hợp đồng dependency distribution và có thể bị thay đổi độc lập; signing publication giải quyết phạm vi rộng hơn ký riêng một JAR.

### 3.3. Xác minh là hai câu hỏi khác nhau

Lệnh **gpg --verify** có thể trả chữ ký hợp lệ về mặt mật mã. Nhưng vẫn cần hỏi **public key đó có đúng người phát hành mà tổ chức tin cậy không?**

Một khóa lạ có thể ký một JAR giả và tự công bố public key tương ứng. Nếu người kiểm tra chỉ thấy dòng “Good signature” rồi kết luận đúng nhà phát hành, họ đã bỏ qua việc xác thực nguồn khóa. Hãy đối chiếu **full fingerprint** từ kênh tin cậy độc lập, kiểm tra trạng thái khóa và gắn với quy trình release đã được phê duyệt.

### 3.4. Chữ ký khác checksum, encryption và provenance

| Cơ chế | Giải quyết | Không tự giải quyết |
| --- | --- | --- |
| **SHA-256 checksum** | Phát hiện bytes khác khi so với digest đáng tin | Không xác thực người phát hành nếu digest cũng bị thay |
| **OpenPGP signature** | Kiểm chứng bytes và khóa đã ký | Không chứng minh code an toàn hoặc builder chưa bị xâm nhập |
| **Encryption** | Bảo mật nội dung khỏi người không có quyền giải mã | Không tự xác thực chất lượng artifact |
| **SBOM** | Liệt kê software components/dependencies | Không tự xác minh artifact do ai ký |
| **Provenance/attestation** | Bằng chứng quy trình build/nguồn đầu vào theo hệ thống tin cậy | Không thay việc kiểm thử logic |
| **Repository TLS/authentication** | Bảo vệ kênh truyền và quyền upload | Không phải chữ ký detached độc lập của bytes |

## 4. Gradle Signing plugin cung cấp gì?

Core plugin:

~~~groovy
plugins {
    id 'signing'
}
~~~

Signing plugin do Gradle cung cấp, không cần tải một plugin version bên ngoài từ Plugin Portal như nhiều community plugins. Nó cung cấp:

- **signing extension** để cấu hình signatory, chính sách **required** và targets.
- Task loại **Sign** khi bạn gọi **sign(...)** trên publication, configuration hoặc output task.
- Đầu ra OpenPGP signatures cho những tệp được chọn.
- Tích hợp với **maven-publish** hoặc **ivy-publish** để publication tasks đưa signatures lên repository.
- Các cơ chế **in-memory PGP**, legacy keyring và **GnuPG command/gpg-agent**.

Signing plugin **không tự tạo Maven publication**. Nếu bạn chỉ viết **id 'signing'** mà không khai báo sẽ ký cái gì, không thể kết luận mọi JAR trong build được ký.

### 4.1. Tạo chữ ký cho Maven publication

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
    id 'signing'
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }
}

signing {
    sign publishing.publications.mavenJava
}
~~~

**Đây là snippet minh họa cấu trúc**, chưa có signing credentials/repository và không phải toàn bộ lab runnable. Điểm chính: **signing.sign(publication)** tạo task tương ứng, thường là **signMavenJavaPublication**.

Khi publication gồm JAR, POM, Gradle Module Metadata và các archives bổ sung, Gradle signing sẽ tính chữ ký cho publication artifacts/metadata phù hợp. Publishing task có thể phụ thuộc task sign theo wiring của plugin, do đó lệnh publish sẽ có các signatures cần thiết.

### 4.2. Không nhầm các tác vụ

| Task | Trách nhiệm |
| --- | --- |
| **jar** | Đóng gói Java main classes/resources |
| **sourcesJar** | Đóng gói Java sources khi bật |
| **javadocJar** | Đóng gói Javadoc khi bật |
| **generatePomFileForMavenJavaPublication** | Tạo POM metadata cho publication |
| **generateMetadataFileForMavenJavaPublication** | Tạo Gradle Module Metadata cho publication |
| **signMavenJavaPublication** | Sinh chữ ký cho publication đã định nghĩa |
| **publishMavenJavaPublicationTo...Repository** | Upload publication và chữ ký tới repository |
| **publish** | Lifecycle task xuất bản publications tới các repositories được cấu hình |
| **publishToMavenLocal** | Publish vào Maven local repository |
| **assemble** | Tạo local artifacts, không phải một lệnh publish |
| **build** | Đóng gói và kiểm tra theo lifecycle, không mặc định publish |

Khi bạn chạy **./gradlew build**, không tự suy chữ ký hoặc public release đã được xuất bản. Khi bạn chạy **./gradlew publish**, phải xác nhận repository, credentials, publication/signing policy và đường dẫn artifact thật.

## 5. Ký publication khác ký riêng một task output

Signing plugin hỗ trợ nhiều target.

### 5.1. Publication: trường hợp nên dùng cho Maven

~~~groovy
signing {
    sign publishing.publications.mavenJava
}
~~~

Đây là cách bao phủ các artifacts và metadata của publication. Tên **mavenJava** phải trùng tên đã khai báo trong **publishing.publications**.

### 5.2. Configuration artifact

Khi muốn ký artifacts mà một consumable configuration công bố:

~~~groovy
signing {
    sign configurations.runtimeElements
}
~~~

Gradle tạo Sign task tên dạng **signRuntimeElements**. Đoạn này chỉ minh họa và yêu cầu Java plugin đã tạo **runtimeElements**. Ký một configuration **không tự** bảo đảm mọi Maven publication đều mang chữ ký của POM và các metadata khác.

### 5.3. Task output

Nếu có task **distZip** tạo một ZIP độc lập:

~~~groovy
signing {
    sign tasks.named('distZip')
}
~~~

Đoạn này giả định project đã áp dụng plugin cung cấp **distZip** và đang dùng một bản Gradle hỗ trợ sign task outputs; không được dán nguyên vào Java library lab nếu project chưa có distZip.

**Ký task output** thích hợp khi chỉ muốn ký một ZIP/JAR riêng. **Ký Maven publication** thích hợp khi cần phát hành cả JAR và metadata có chữ ký. Đừng cấu hình cả hai lên cùng artifact một cách vô ý rồi sinh nhiều Sign tasks/outputs gây khó quản lý.

## 6. Quản lý khóa: nguyên tắc không đưa private key vào source

**Quy tắc bất biến:** Không commit private key, password, token xuất bản, keyring secret hoặc tệp chứa bản export secret key vào Git, kể cả repository private.

Những nơi nên tránh:

~~~text
project/gradle.properties                 # khi bị commit
project/secring.gpg                       # private keyring trong repo
project/signing-private.asc               # ASCII-armored secret key trong repo
project/build.gradle                      # hardcoded private key/password
project/.github/workflows/release.yml     # secrets viết literal
src/main/resources/private-key.asc        # dễ vô tình đóng gói vào JAR
~~~

**Public key** có thể được phát hành qua kênh xác thực để consumer verify. Tuy nhiên cũng cần ghi full fingerprint và kiểm soát việc thay/rotate public key để tránh thay thế khóa giả.

### 6.1. Chọn nguồn bí mật

| Cơ chế | Thích hợp | Cần chú ý |
| --- | --- | --- |
| **CI secret store → environment variables** | CI release job | Chỉ inject cho trusted releases, hạn chế quyền xem/in logs |
| **Vault / secret manager** | Tổ chức có quản trị secrets | Truy cập theo workload identity, audit và rotation |
| **GnuPG secret keyring + gpg-agent** | Máy developer/release host | Khóa lưu ngoài repo, passphrase qua agent, kiểm soát filesystem |
| **GRADLE_USER_HOME/gradle.properties** | Local development không có secret manager | Quyền file, không đưa vào VCS, cân nhắc key plaintext/passphrase |
| **Managed signing service/HSM** | Yêu cầu bảo mật cao | Có thể cần integration/plugin phù hợp, đừng giả Gradle OpenPGP hỗ trợ mọi KMS trực tiếp |

**Environment variable không phải một két sắt tuyệt đối.** Process con, debug tools, environment dumps, shell tracing hoặc code Gradle/plugin độc hại có thể đọc biến đó. Cần tránh chạy build untrusted code cùng secrets và hạn chế thời gian sống của key material.

### 6.2. Không đặt secret trong command-line arguments

Tránh:

~~~bash
./gradlew publish -PsigningPassword=actual-secret
~~~

Đây là **mẫu cố ý không nên dùng** vì giá trị có thể bị lưu trong shell history, process arguments, logs hoặc telemetry. Dùng CI secret manager hoặc bảo vệ local user Gradle home nếu phù hợp.

Không in:

~~~groovy
println providers.gradleProperty('signingKey').get()
~~~

Đây cũng là **antipattern cố ý**, có thể lộ private key nguyên văn vào build log. Không dùng **--debug** trên release jobs nếu logging hoặc plugin có khả năng hiển thị secrets.

## 7. Ký với private key ASCII-armored trong biến môi trường

Gradle Signing plugin có API:

~~~groovy
signing {
    def key = findProperty('signingKey')
    def password = findProperty('signingPassword')

    useInMemoryPgpKeys(key, password)
    sign publishing.publications.mavenJava
}
~~~

Đây là cú pháp cơ bản theo tài liệu Gradle. Trong lab, ta sẽ dùng **providers.gradleProperty(...)** để đọc project properties và chỉ gọi useInMemoryPgpKeys khi key được cấp.

### 7.1. ORG_GRADLE_PROJECT_ là gì?

Gradle hỗ trợ tự chuyển môi trường:

~~~text
ORG_GRADLE_PROJECT_signingKey       -> project property signingKey
ORG_GRADLE_PROJECT_signingPassword  -> project property signingPassword
ORG_GRADLE_PROJECT_signingKeyId     -> project property signingKeyId
~~~

Dùng **providers.gradleProperty('signingKey')** sẽ đọc project property theo Gradle Provider API, bao gồm nguồn từ environment variables có prefix trên.

CI secret phải chứa **ASCII-armored OpenPGP secret key đầy đủ, nhiều dòng**:

~~~text
-----BEGIN PGP PRIVATE KEY BLOCK-----
...
-----END PGP PRIVATE KEY BLOCK-----
~~~

Khối trên **chỉ minh họa dạng định dạng**, không phải secret key hợp lệ, không được dùng để ký. Trong repository không bao giờ lưu một khối private key thật, kể cả file README, Git history hoặc example configuration.

CI secret store cần bảo toàn newline nguyên vẹn. Không tự biến chuỗi nhiều dòng thành một dòng nếu build script không decode đúng. **useInMemoryPgpKeys** theo tài liệu nhận chuỗi ASCII-armored, không tự yêu cầu base64; nếu tổ chức chọn lưu base64 thì phải có bước decode an toàn và kiểm soát logging riêng.

### 7.2. Dùng Provider API

~~~groovy
def signingKeyProvider =
        providers.gradleProperty('signingKey')

def signingPasswordProvider =
        providers.gradleProperty('signingPassword')

signing {
    def key = signingKeyProvider.orNull
    def password = signingPasswordProvider.orNull

    if (key != null && !key.isBlank()) {
        useInMemoryPgpKeys(key, password)
    }

    sign publishing.publications.mavenJava
}
~~~

Đây là **snippet có thể đặt trong build.gradle đã áp dụng signing và maven-publish**. **providers.gradleProperty** giúp biểu diễn nguồn của giá trị theo API, nhưng **useInMemoryPgpKeys** vẫn cần chuỗi key thực khi cấu hình signatory. Không coi việc dùng Provider là private key không bao giờ được nạp vào bộ nhớ Gradle.

### 7.3. Dùng signing subkey

Khi key material là một OpenPGP subkey export, Gradle docs hướng dẫn overload ba tham số:

~~~groovy
signing {
    def keyId = providers.gradleProperty('signingKeyId').orNull
    def key = providers.gradleProperty('signingKey').orNull
    def password = providers.gradleProperty('signingPassword').orNull

    if (key != null && !key.isBlank()) {
        useInMemoryPgpKeys(keyId, key, password)
    }

    sign publishing.publications.mavenJava
}
~~~

Đây là **phương án thay thế** phần in-memory block trong lab nếu tổ chức dùng signing subkeys; không cần dùng đồng thời cả hai overload. **signingKeyId** phải trỏ tới subkey phù hợp; tránh chọn nhầm khóa. Khi verify, vẫn đối chiếu **full fingerprint** và trust chain, không chỉ short ID.

### 7.4. Lợi ích và giới hạn của in-memory key

Ưu điểm:

- Không cần đặt tệp secret keyring vào repository/workspace.
- Có thể dùng secret store của CI.
- Không phụ thuộc GnuPG executable trên runner nếu plugin dùng Java-based PGP implementation.
- Dễ xây release pipeline nhất quán cho Java library.

Giới hạn:

- Private key tồn tại trong environment và Gradle process memory trong thời gian ký.
- Nếu build script hoặc third-party plugin độc hại, nó có thể đọc key.
- Secret có thể vô tình xuất hiện trong Gradle diagnostics nếu code in ra.
- Khi CI job kết thúc cần xóa/temp cleanup theo runner policy.
- Không phải phần cứng HSM và không bảo đảm non-exportable key.

## 8. GnuPG và gpg-agent: phương án khác

Nếu developer/release host dùng GnuPG keyring ngoài project, Gradle có thể đổi signatory:

~~~groovy
signing {
    useGpgCmd()
    sign publishing.publications.mavenJava
}
~~~

**Đây là cấu hình thay thế cho in-memory key**, không phải block thứ hai để tự động chạy song song. Theo Gradle docs, **useGpgCmd()** gọi GnuPG executable và có thể dùng **gpg-agent** để lấy passphrase. Cần cài GnuPG đúng cách, có secret key trong keyring và chọn key phù hợp.

Các project properties nâng cao có thể gồm:

~~~properties
signing.gnupg.executable=gpg
signing.gnupg.keyName=FINGERPRINT_OR_KEY_ID
~~~

Đoạn trên là **mẫu tùy chọn** cho cấu hình GnuPG; **FINGERPRINT_OR_KEY_ID** là ký hiệu giải thích, không phải giá trị để copy nguyên. Nên đặt cấu hình thật vào Gradle user home hoặc secret manager ngoài repo và chỉ khi cần.

### 8.1. Xem khóa trên máy phát hành

~~~bash
gpg --list-secret-keys --keyid-format LONG
gpg --fingerprint
~~~

Lệnh **gpg --list-secret-keys** cho biết có secret key được GnuPG quản lý; **gpg --fingerprint** giúp xem fingerprint. GnuPG thường giữ secret key trong **GNUPGHOME**, không phải **src/** hoặc **build/** của ứng dụng.

Đừng copy toàn bộ thư mục **~/.gnupg/** vào CI artifacts. Nó có thể chứa private keys, trust database hoặc thông tin nhạy cảm.

### 8.2. Tạo khóa thử nghiệm một cách có kiểm soát

Trên máy thử nghiệm cá nhân, có thể chạy:

~~~bash
gpg --full-generate-key
gpg --list-secret-keys --keyid-format LONG
~~~

GnuPG sẽ hỏi thông tin key type, độ dài, email/UID và passphrase theo cấu hình. Chọn thuật toán và chính sách phù hợp yêu cầu repository/đơn vị phát hành. Đối với release thật, dùng identity được xác minh và quy trình tổ chức phê duyệt; không ký bằng một khóa test vô danh rồi tuyên bố nó là khóa chính thức.

**Không sử dụng private key production làm bài tập chia sẻ trong lớp học, chat hoặc CI không được bảo vệ.**

### 8.3. Lưu public key để verify

Lệnh xuất public key:

~~~bash
gpg --armor --export KEY_FINGERPRINT > release-public.asc
~~~

**KEY_FINGERPRINT** là ký hiệu cần thay bằng full fingerprint thực, không phải khóa bí mật. Public key có thể được chia sẻ để verify, nhưng người dùng vẫn phải xác nhận fingerprint từ kênh đáng tin (chẳng hạn tài liệu phát hành chính thức có kiểm soát).

Lệnh xuất secret key **khác** lệnh export public key. Không dùng **--export-secret-keys** khi mục đích chỉ là chia sẻ public key cho consumer.

## 9. Conditional signing: SNAPSHOT và release

Trong một workflow Java:

- **SNAPSHOT/local build** thường cần compile/test nhanh, không nhất thiết có private key ở mọi máy.
- **Release/publish chính thức** thường yêu cầu artifact và metadata được ký.
- Không nên khiến **./gradlew help** hoặc **./gradlew test** trên máy developer fail chỉ vì chưa có secret release.
- Không được cho phép **release publish unsigned** chỉ vì secrets chưa được cấp.

Gradle Signing plugin có thuộc tính **required** để quyết định khi nào chữ ký là bắt buộc.

### 9.1. Trường hợp đơn giản theo version

~~~groovy
def isRelease =
        !version.toString().endsWith('-SNAPSHOT')

signing {
    required = isRelease
    sign publishing.publications.mavenJava
}
~~~

Nếu version là **1.0.0-SNAPSHOT**, Signing plugin có thể bỏ qua signing khi không có credentials. Nếu version là **1.0.0**, signing được yêu cầu khi task ký phải chạy; thiếu signatory credentials sẽ làm lệnh phát hành lỗi thay vì âm thầm công bố unsigned artifact.

**Cần phân biệt “required” với “bắt buộc mọi task đều phải ký”.** Thuộc tính này ảnh hưởng Sign tasks khi được thực thi. Một lệnh **test** không cần tự chạy signing publication; nhưng lệnh **publish** theo wiring của publication sẽ yêu cầu ký release.

### 9.2. Release flag phải đến từ nguồn đáng tin

Chỉ kiểm tra hậu tố **-SNAPSHOT** là ví dụ phù hợp để học. Pipeline thực tế còn cần:

- Xác nhận tag/release policy.
- Xác nhận branch và approvals.
- Chỉ cấp secrets cho trusted release jobs.
- Từ chối version rỗng, mutable hoặc chưa được phê duyệt.
- Không cho untrusted PR tự đặt **isRelease=false** để bypass publishing policy.

Trong hệ thống doanh nghiệp, nên enforce rule ở cả CI/repository permissions và build logic; đừng chỉ tin một dòng if trong build.gradle để quản lý mọi quyền release.

### 9.3. Không dùng taskGraph API nếu không cần

Gradle docs có ví dụ **required = { isReleaseVersion && gradle.taskGraph.hasTask('publish') }**. Tuy nhiên, với build muốn hỗ trợ configuration cache, nên tránh phụ thuộc vào taskGraph access/Gradle model từ closure khi có giải pháp dựa trên version/properties và CI release gate rõ ràng.

Mẫu trong lab dùng **required = isRelease** và chỉ ký khi Gradle publication Sign task được chọn qua publish task graph. Nó đơn giản, dễ giải thích và không cần truy cập runtime task graph trong cấu hình signing.

## 10. Lab hoàn chỉnh: Java 17 library, Maven publication và ký OpenPGP

Bài thực hành xây một thư viện nhỏ **signed-artifact-lab**, có:

- Java 17 production code.
- Hai JUnit 5 tests.
- **jar**, **sourcesJar**, **javadocJar**.
- Maven publication tên **mavenJava**.
- Repository **localStaging** dưới **build/staging-repo**, không upload Internet.
- Gradle Signing plugin ký publication bằng ASCII-armored key đọc từ environment-backed project properties.
- Version mặc định **1.0.0-SNAPSHOT** để developer build/test không cần private key.
- Tham số **-PreleaseVersion=1.0.0** để giả lập release và yêu cầu signing.
- Lệnh **gpg --verify** để consumer kiểm tra từng detached signature.

**Trong lab, “publish” chỉ đưa artifact vào thư mục local staging để học cách ký/xuất bản an toàn.** Nó không publish lên Maven Central. Để phát hành thật cần đăng ký namespace/groupId, repository credentials, thông tin POM hợp lệ, release governance và policy của kho đích.

### 10.1. Cây thư mục

~~~text
signed-artifact-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/
    ├── main/
    │   └── java/demo/signing/
    │       ├── Receipt.java
    │       └── Main.java
    └── test/
        └── java/demo/signing/
            └── ReceiptTest.java
~~~

Cần JDK 17, Gradle Wrapper phiên bản phù hợp và Internet/mirror để resolve JUnit Jupiter/Platform dependencies. Nếu repo mới chưa có Wrapper, tạo Wrapper một lần bằng Gradle CLI tương thích, rồi commit **gradlew**, **gradlew.bat** và **gradle/wrapper/**. **Không** commit private key hoặc secret properties.

### 10.2. settings.gradle

~~~groovy
dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS

    repositories {
        mavenCentral()
    }
}

rootProject.name = 'signed-artifact-lab'
~~~

Dự án chỉ dùng Gradle core plugins nên không cần một external plugin ID/version. **mavenCentral()** phục vụ JUnit dependencies của lab. Chính sách **FAIL_ON_PROJECT_REPOS** yêu cầu libraries repositories được khai báo tập trung, không tự thêm trong build.gradle.

### 10.3. build.gradle — toàn bộ file

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
    id 'signing'
}

group = 'dev.training'
version = providers.gradleProperty('releaseVersion')
        .getOrElse('1.0.0-SNAPSHOT')

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }

    withSourcesJar()
    withJavadocJar()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java

            pom {
                name = 'Signed Artifact Lab'
                description = 'Java 17 signing demonstration'
            }
        }
    }

    repositories {
        maven {
            name = 'localStaging'
            url = uri(
                layout.buildDirectory.dir('staging-repo')
                        .get().asFile)
        }
    }
}

def isRelease =
        !version.toString().endsWith('-SNAPSHOT')

signing {
    required = isRelease

    def armoredKey =
            providers.gradleProperty('signingKey').orNull

    def passphrase =
            providers.gradleProperty('signingPassword').orNull

    if (armoredKey != null && !armoredKey.isBlank()) {
        useInMemoryPgpKeys(armoredKey, passphrase)
    }

    sign publishing.publications.mavenJava
}
~~~

Đây là **file build.gradle hoàn chỉnh**, không cần plugin buildSrc hay custom build-logic khác.

### 10.4. Giải thích từng nhóm cấu hình

1. **java-library** tạo Java source sets, task compile/test/jar và Java component.
2. **maven-publish** tạo publishing extension, MavenPublication model và publication tasks.
3. **signing** tạo signing extension và Sign tasks khi chúng ta gọi **sign**.
4. **version** nhận từ **releaseVersion** project property, mặc định SNAPSHOT.
5. **java.toolchain.languageVersion = 17** yêu cầu Java 17 toolchain để compile/test.
6. **withSourcesJar()/withJavadocJar()** thêm hai archive tasks và variants bổ sung cho Java component.
7. **JUnit dependencies** chỉ ở test scopes, không được đưa vào publication library main JAR.
8. **publishing.publications.mavenJava** xuất Java component; JAR, POM, metadata, sources và javadoc có thể thành phần của publication.
9. **localStaging** là Maven repository ở **build/staging-repo** của project, không cần credentials.
10. **isRelease** phân biệt **1.0.0-SNAPSHOT** và **1.0.0**.
11. **required = isRelease** khiến release signing là bắt buộc khi Sign task chạy.
12. **providers.gradleProperty('signingKey')** đọc project property, có thể được cấp qua **ORG_GRADLE_PROJECT_signingKey**.
13. **useInMemoryPgpKeys** nạp ASCII-armored secret key vào signatory, không ghi private key ra source tree.
14. **sign publishing.publications.mavenJava** yêu cầu ký artifacts và metadata của publication.

**Một điểm quan trọng:** Provider API mô tả nguồn config nhưng **khi gọi useInMemoryPgpKeys, key string vẫn nằm trong bộ nhớ Gradle**. Chỉ cấp key trong trusted release job, không in nó ra log hoặc expose cho plugin bên ngoài không đáng tin.

### 10.5. src/main/java/demo/signing/Receipt.java

~~~java
package demo.signing;

/**
 * Biểu diễn một biên nhận đơn giản cho bài thực hành.
 */
public record Receipt(String code, long cents) {

    /**
     * Kiểm tra dữ liệu khi tạo biên nhận.
     */
    public Receipt {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException(
                    "code must not be blank");
        }
        if (cents < 0) {
            throw new IllegalArgumentException(
                    "cents must not be negative");
        }
    }

    /**
     * Trả về dòng văn bản xác định cho kiểm thử.
     *
     * @return chuỗi mô tả biên nhận
     */
    public String summary() {
        return "RECEIPT=" + code + ";CENTS=" + cents;
    }
}
~~~

**record** và compact constructor được Java 17 hỗ trợ. Không có dependency bên ngoài trong source production. **summary()** cho một dòng output ổn định, hữu ích cho smoke test.

### 10.6. src/main/java/demo/signing/Main.java

~~~java
package demo.signing;

/**
 * Chương trình demo đọc library class sau khi build.
 */
public final class Main {
    private Main() {
    }

    /**
     * Entry point cho lệnh java -cp.
     *
     * @param args không sử dụng
     */
    public static void main(String[] args) {
        Receipt receipt = new Receipt("A17", 2500);
        System.out.println(receipt.summary());
    }
}
~~~

Stdout chính xác của Java Main:

~~~text
RECEIPT=A17;CENTS=2500
~~~

### 10.7. src/test/java/demo/signing/ReceiptTest.java

~~~java
package demo.signing;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ReceiptTest {
    @Test
    void formatsReceipt() {
        Receipt receipt = new Receipt("A17", 2500);
        assertEquals(
                "RECEIPT=A17;CENTS=2500",
                receipt.summary());
    }

    @Test
    void rejectsNegativeCents() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new Receipt("A17", -1));
    }
}
~~~

Hai JUnit Jupiter test methods được thiết kế để pass. Task **test** của Gradle mới thực thi JUnit và tạo test reports; **javac/java** tự chạy Main ở phần sau chỉ chứng minh Java source chạy được, không kiểm chứng signing hoặc publishing.

## 11. Chạy build không cần private key

Ở chế độ SNAPSHOT mặc định:

~~~bash
./gradlew --version
./gradlew clean test
./gradlew jar sourcesJar javadocJar
./gradlew tasks --all
./gradlew -q help
~~~

Những lệnh này không cần private key release. **signMavenJavaPublication** có thể tồn tại trong task list nhưng không nhất thiết được chọn khi chạy **test/jar/help**.

Có thể tạo local SNAPSHOT publication:

~~~bash
./gradlew publish
~~~

Với **version=1.0.0-SNAPSHOT** và không có signatory credentials, signing không bắt buộc theo config lab. Các artifacts/POM có thể được xuất bản không có chữ ký, phù hợp một staging SNAPSHOT demo nhưng **không được dùng kết quả đó làm release chính thức**.

Bên nhận muốn yêu cầu mọi artifact có chữ ký cần kiểm tra policy riêng; đừng đồng nhất “Gradle publish thành công” với “artifact đã được ký”.

### 11.1. Xem task names

~~~bash
./gradlew tasks --all
./gradlew help --task signMavenJavaPublication
./gradlew help --task publish
~~~

Những tên chính:

~~~text
jar
sourcesJar
javadocJar
signMavenJavaPublication
publishMavenJavaPublicationToLocalStagingRepository
publishAllPublicationsToLocalStagingRepository
publish
publishToMavenLocal
~~~

Một số task names phụ thuộc tên publication/repository. Với lab, **mavenJava** và **localStaging** đã được khai báo chính xác. Nếu sau này đổi name, cập nhật lệnh theo report của Gradle, không copy task path cũ một cách máy móc.

## 12. Thực hiện ký release với secrets bên ngoài repository

Để giả lập release, đặt **releaseVersion=1.0.0**. Gradle cần private key và passphrase hợp lệ để tạo chữ ký.

### 12.1. Cấp secrets qua CI environment

CI secret manager lưu hai giá trị:

~~~text
PGP_SIGNING_PRIVATE_KEY_ASC
PGP_SIGNING_PASSPHRASE
~~~

Đây là **tên secrets**, không phải giá trị bí mật. Trước khi gọi Gradle, CI ánh xạ chúng sang environment variables được Gradle nhận:

~~~text
ORG_GRADLE_PROJECT_signingKey
ORG_GRADLE_PROJECT_signingPassword
~~~

Đặc biệt, **key phải là ASCII-armored private key đúng định dạng**, nhiều dòng và với passphrase tương ứng. Không đặt secret thực vào README, workflow YAML hoặc tệp **gradle.properties** được commit.

### 12.2. Lệnh Gradle release

Linux/macOS (sau khi môi trường đáng tin đã cấp hai biến):

~~~bash
./gradlew -PreleaseVersion=1.0.0 clean test publish
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat -PreleaseVersion=1.0.0 clean test publish
~~~

Nếu key/password đúng và publication hợp lệ, Gradle dự kiến chạy **signMavenJavaPublication** trong task graph khi publish, tạo các **.asc** và đưa chúng cùng các artifact vào **build/staging-repo**.

Nếu key/password thiếu hoặc sai, **release signing phải fail**. Đây là cơ chế bảo vệ được yêu cầu, không phải một lỗi nên sửa bằng **required = false** cho release.

### 12.3. Artifact paths trong localStaging

Với:

~~~text
group   = dev.training
artifactId = signed-artifact-lab
version = 1.0.0
~~~

Maven repository layout sẽ có dạng:

~~~text
build/staging-repo/
└── dev/training/signed-artifact-lab/1.0.0/
    ├── signed-artifact-lab-1.0.0.jar
    ├── signed-artifact-lab-1.0.0.jar.asc
    ├── signed-artifact-lab-1.0.0-sources.jar
    ├── signed-artifact-lab-1.0.0-sources.jar.asc
    ├── signed-artifact-lab-1.0.0-javadoc.jar
    ├── signed-artifact-lab-1.0.0-javadoc.jar.asc
    ├── signed-artifact-lab-1.0.0.pom
    ├── signed-artifact-lab-1.0.0.pom.asc
    └── ... Gradle metadata/checksum files nếu được publish
~~~

**Đây là layout dự kiến**, không phải liệt kê cố định mọi checksum/metadata files do từng Gradle/repository version tạo. Điều cần xác nhận là **mọi artifact bắt buộc của publication có tệp signature đúng** và không có private key trong staging directory.

### 12.4. Kiểm tra reports sau khi publish

~~~bash
./gradlew -PreleaseVersion=1.0.0 \
    help --task signMavenJavaPublication

./gradlew -PreleaseVersion=1.0.0 \
    tasks --all
~~~

Có thể dùng **--info** trên máy/dev environment khi không đưa secrets vào log, nhưng trong CI production cần hạn chế log verbosity và kiểm tra plugin behavior. Không dùng lệnh nào in signingKey hoặc full environment.

## 13. Xác minh detached signature bằng public key

Một consumer phải lấy **public key từ kênh tin cậy**, kiểm tra fingerprint, sau đó xác minh chữ ký với artifact chính xác.

### 13.1. Nhập public key

~~~bash
gpg --import release-public.asc
gpg --fingerprint
~~~

**release-public.asc** là tệp public key đã được xác thực từ nguồn phát hành; không phải private key, không chứa password. Kiểm tra full fingerprint hiển thị so với fingerprint công bố qua kênh tổ chức đáng tin, không chỉ nhìn tên/email trong UID.

### 13.2. Xác minh JAR

~~~bash
gpg --verify \
  build/staging-repo/dev/training/signed-artifact-lab/1.0.0/signed-artifact-lab-1.0.0.jar.asc \
  build/staging-repo/dev/training/signed-artifact-lab/1.0.0/signed-artifact-lab-1.0.0.jar
~~~

Khi signature khớp và public key đã nhập, GnuPG sẽ báo trạng thái chữ ký theo ngôn ngữ/version cấu hình. **Không đưa ra một dòng stdout cố định**, vì GPG có thể thêm key ID, fingerprint, UID, trust status và ngày ký phụ thuộc môi trường.

Nếu thấy **Good signature** nhưng kèm cảnh báo chưa xác lập trust, điều đó có nghĩa GPG kiểm chứng chữ ký bằng public key hiện có nhưng chưa tự công nhận danh tính người sở hữu khóa. Cần đối chiếu fingerprint và chính sách trust riêng.

### 13.3. Xác minh POM và sources JAR

~~~bash
gpg --verify \
  build/staging-repo/dev/training/signed-artifact-lab/1.0.0/signed-artifact-lab-1.0.0.pom.asc \
  build/staging-repo/dev/training/signed-artifact-lab/1.0.0/signed-artifact-lab-1.0.0.pom

gpg --verify \
  build/staging-repo/dev/training/signed-artifact-lab/1.0.0/signed-artifact-lab-1.0.0-sources.jar.asc \
  build/staging-repo/dev/training/signed-artifact-lab/1.0.0/signed-artifact-lab-1.0.0-sources.jar
~~~

Một JAR signature hợp lệ **không đủ** để kết luận POM/sources đã được ký. Phát hành Maven library đúng cần kiểm soát nhiều tệp/metadata.

### 13.4. Thử thay đổi artifact sau ký

Bài học quan trọng: chữ ký gắn với **bytes đã ký**. Nếu bạn sửa một bản sao của JAR sau khi signing, chữ ký cũ không còn xác minh thành công.

Không chỉnh trực tiếp artifact đã publish của release thật để thử nghiệm. Hãy copy một tệp JAR **vào thư mục tạm** và thay đổi bản sao, rồi dùng signature cũ để verify bản sao. Kỳ vọng GPG báo **BAD signature** hoặc verification failure.

Đừng dựa vào extension, tên file hay version trong filename để xác minh integrity; chữ ký chỉ xác thực đúng bytes.

## 14. Chạy Java 17 của publication độc lập

Phần production của lab không dùng external libraries. Có thể biên dịch và chạy bằng Java 17 mà không cần Gradle/JUnit:

Linux/macOS:

~~~bash
mkdir -p out

javac --release 17 -d out \
  src/main/java/demo/signing/Receipt.java \
  src/main/java/demo/signing/Main.java

java -cp out demo.signing.Main
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null

javac --release 17 -d out src\main\java\demo\signing\Receipt.java src\main\java\demo\signing\Main.java

java -cp out demo.signing.Main
~~~

**Stdout chính xác:**

~~~text
RECEIPT=A17;CENTS=2500
~~~

Sau khi Gradle tạo JAR, có thể dùng:

~~~bash
java -cp build/libs/signed-artifact-lab-1.0.0.jar \
  demo.signing.Main
~~~

khi đang ở version SNAPSHOT. Với **-PreleaseVersion=1.0.0**, JAR tên **signed-artifact-lab-1.0.0.jar**:

~~~bash
java -cp build/libs/signed-artifact-lab-1.0.0.jar \
  demo.signing.Main
~~~

Stdout vẫn như trên. Không dùng **java -jar** nếu JAR chưa có manifest Main-Class; Java Library Plugin không tự khai báo entrypoint cho JAR.

**Phạm vi kiểm chứng:**

- **javac/java** xác nhận source Java 17 compile/run.
- **Gradle test** xác nhận JUnit dependencies/framework và test code.
- **signMavenJavaPublication** xác nhận signing tasks được chọn/thực thi.
- **publish** xác nhận artifacts/signatures được phát hành tới staging repo.
- **gpg --verify** xác nhận detached signature bằng public key.
- **Review fingerprint và release policy** xác nhận key identity và tính đáng tin cậy theo tổ chức.

## 15. gpg-agent local developer workflow

Nếu người ký có GnuPG secret key trên máy riêng, một lựa chọn tốt là không xuất private key ASCII-armored vào env. Thay khối signing **trong build.gradle** bằng:

~~~groovy
signing {
    required = !version.toString().endsWith('-SNAPSHOT')
    useGpgCmd()
    sign publishing.publications.mavenJava
}
~~~

**Đây là phương án thay thế**, không đặt đồng thời hai cấu hình signing khác nhau rồi hy vọng Gradle tự chọn đúng. GnuPG có thể dùng **gpg-agent** để nhập/giữ passphrase theo thời gian cache chính sách của agent.

Trước khi ký:

~~~bash
gpg --list-secret-keys --keyid-format LONG
gpg --fingerprint
~~~

Nếu có nhiều keys, chọn key tương ứng theo **signing.gnupg.keyName** hoặc GnuPG config. Đừng dựa vào “default key” của máy release server nếu artifact policy yêu cầu khóa cụ thể.

### 15.1. Không nhầm keyring file legacy và GPG 2.x

Gradle Signing plugin vẫn có cách cấu hình legacy:

~~~properties
signing.keyId=KEYID
signing.secretKeyRingFile=/absolute/path/to/secring.gpg
signing.password=passphrase
~~~

Đây là **mẫu giải thích thuộc tính**, không chứa giá trị thật. GnuPG 2.1+ thay đổi cách lưu private keys và keyring format; đường dẫn **~/.gnupg/** của GPG hiện đại không nhất thiết tương đương một file **secring.gpg** mà Gradle legacy API có thể dùng.

Nếu chọn cách legacy, phải export đúng keyring format được plugin hỗ trợ, đặt ngoài repo và bảo vệ permission. **Không trỏ tùy tiện tới private-keys-v1.d hoặc ~/.gnupg** rồi coi đó là secring.gpg. Với CI hiện đại, **useInMemoryPgpKeys** thường dễ kiểm soát hơn.

### 15.2. GPG agent và CI

gpg-agent có thể phù hợp với workstation hoặc dedicated release host. Trên CI ephemeral runner, cần bảo đảm:

- GnuPG executable và agent thực sự có mặt.
- Secret key được nhập bằng cách không ghi lộ vào logs.
- Pinentry/loopback handling phù hợp noninteractive environment.
- Key selection đúng fingerprint.
- Keyring/temp files được xóa an toàn sau job.
- Runner không chia sẻ secret state với untrusted jobs.

Nếu không thể đảm bảo điều này, CI secret store + in-memory PGP có thể đơn giản hơn, nhưng vẫn phải giới hạn quyền thực thi build code.

## 16. GitHub Actions: ký khi tạo release từ protected tag

Ví dụ workflow ở **.github/workflows/release.yml**. Nó dùng local staging repo trong lab, không phát hành lên Maven Central. Secret injection chỉ có tại release job được bảo vệ.

~~~yaml
name: Signed Java release

on:
  push:
    tags:
      - 'v*'

permissions:
  contents: read

jobs:
  release:
    runs-on: ubuntu-latest
    environment: release

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Java 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Configure Gradle
        uses: gradle/actions/setup-gradle@v6

      - name: Test, sign, and stage Maven publication
        env:
          ORG_GRADLE_PROJECT_signingKey: ${{ secrets.PGP_SIGNING_PRIVATE_KEY_ASC }}
          ORG_GRADLE_PROJECT_signingPassword: ${{ secrets.PGP_SIGNING_PASSPHRASE }}
        shell: bash
        run: |
          VERSION="$(printf '%s' "$GITHUB_REF_NAME" | sed 's/^v//')"
          ./gradlew "-PreleaseVersion=$VERSION" clean test publish

      - name: Upload public release outputs
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: signed-staging-public-files
          path: |
            build/staging-repo/**
            build/reports/tests/**
            build/test-results/test/TEST-*.xml
          if-no-files-found: warn
          retention-days: 14
~~~

### 16.1. Giải thích an toàn

- Workflow chỉ trigger khi push tag **v*** theo YAML; cần bảo vệ tag creation và GitHub **environment: release** bằng approvals/permissions phù hợp trong repository settings.
- **permissions: contents: read** tránh cấp write token khi không cần.
- Hai secrets được đưa vào **environment** riêng cho step ký. Không in trực tiếp key/password vào console.
- **VERSION** được lấy từ tên tag (bỏ prefix v) rồi truyền qua **-PreleaseVersion**; trong hệ thống thật nên validate version và đảm bảo tag đã được phê duyệt.
- **./gradlew clean test publish** vẫn có thể fail; không có **|| true** hoặc **continue-on-error**.
- Bước upload dùng **if: always()** để giữ những artifact/report đã tạo trong trường hợp thất bại.
- Artifact upload chỉ lấy output công khai **build/staging-repo** và test reports; không upload Gradle user home, workspace secret files hoặc environment dump.
- **Release thực tế chỉ nên publish/promote artifact khi tất cả tests, signing và verification pass**. Upload artifact khi fail để debug không đồng nghĩa được phép promote release thất bại.

### 16.2. Tại sao không chạy signing secrets ở pull_request?

Pull requests từ nguồn không đáng tin có thể sửa build.gradle, init scripts, plugins hoặc task actions để đọc environment variables và gửi secrets ra ngoài. Vì vậy:

- Không inject private signing key trong PR build, đặc biệt fork/untrusted branches.
- Không expose key trong workflow chạy trực tiếp code chưa được review.
- Cân nhắc artifact promotion workflow: build/test từ commit được phê duyệt, rồi ký trên trusted release runner.
- Dùng environment protection rules và least-privilege identity.
- Hạn chế bên nào được sửa release workflow/build logic và tạo tags.
- Pin Gradle Wrapper/actions/plugins/dependencies theo security policy.

Signing key bảo vệ release artifact chỉ khi **quy trình dùng key cũng đáng tin**.

### 16.3. Dùng branch/repository khác nhau cho trusted release

Trong tổ chức lớn, build từ PR và release signing có thể tách thành hai workflows/environments. Nhưng **không ký artifact không xác định nguồn** chỉ vì nó được copy từ job khác. Kết nối theo commit SHA, checksums, artifact provenance và approvals; dùng artifact promotion có integrity verification.

### 16.4. Version và mutable artifacts

Ví dụ lab dùng staging file repository. Maven Central/public release thường yêu cầu version độc nhất/immutable: không overwrite **1.0.0** bằng bytes khác rồi giữ signature cũ. Nếu phải sửa lỗi release, phát hành version mới và chữ ký mới; không tự xóa/rewrite artifact đã được consumer cache.

## 17. Khi xuất bản tới Maven repository thực

Cấu hình localStaging chỉ phục vụ thực hành. Một repository ngoài thường yêu cầu:

- Đăng ký namespace/groupId và quyền publish.
- Repository endpoint và cơ chế credentials/token.
- Metadata POM đầy đủ: name, description, URL, license, developer/SCM theo policy của repository.
- JAR, sources/Javadoc artifacts nếu yêu cầu.
- Chữ ký OpenPGP cho artifacts/metadata theo chính sách hiện hành.
- Repository staging/promote/release workflow.
- Quyền hạn, audit logs và secret rotation.
- Dependency coordinates/release version không bị thay đổi sau ký.
- Kiểm tra SHA256/attestation và consumer verification.

Ví dụ **maven-publish** repository auth (không dùng thật nếu chưa cấu hình URL/secret manager):

~~~groovy
publishing {
    repositories {
        maven {
            name = 'releaseRepository'
            url = uri(
                providers.gradleProperty('releaseRepoUrl').get())

            credentials {
                username = providers.gradleProperty(
                    'releaseRepoUser').orNull

                password = providers.gradleProperty(
                    'releaseRepoPassword').orNull
            }
        }
    }
}
~~~

**Đoạn này là minh họa bổ sung**, không thể copy độc lập nếu chưa có **maven-publish**, publication và values. Không hardcode username/password; không sử dụng URL placeholder cho production. Cần bảo vệ repository credentials **riêng** với signing private key: quyền upload và quyền ký là hai đặc quyền khác nhau.

### 17.1. Ký không tự publish

Lệnh:

~~~bash
./gradlew signMavenJavaPublication
~~~

chỉ chuẩn bị signature outputs; nó không đưa artifacts tới repository nếu không có publish task. Tương tự:

~~~bash
./gradlew publish
~~~

khi chưa đăng ký signing targets có thể publish unsigned artifacts. Phải cấu hình **sign publication** đúng và kiểm tra repository contents sau release.

### 17.2. Publish không tự verify trust

Publisher dùng private key để ký. Consumer mới là bên kiểm tra chữ ký bằng public key. Việc repository chấp nhận file **.asc** không chứng minh key đúng identity, key chưa bị thu hồi hoặc consumer có chính sách verify mạnh. Cần kiểm thử end-to-end với public key đã được tin cậy.

### 17.3. Gradle dependency verification khác publication signing

Gradle có **dependency verification** để kiểm tra dependencies đã tải dựa trên checksums/signatures/metadata có kiểm soát. Nó bảo vệ **đầu vào của build**. Signing plugin bảo vệ **đầu ra được publish**.

Cả hai rất hữu ích nhưng khác mục tiêu:

~~~text
Verify third-party dependencies
             |
             v
       Build Java artifact
             |
             v
       Sign our publication
             |
             v
       Consumer verifies it
~~~

Không nhầm một file **verification-metadata.xml** của Gradle dependency verification với artifact chữ ký OpenPGP của Maven publication.

## 18. Rotation và revocation của khóa

### 18.1. Vì sao phải có key lifecycle?

Private key có thể hết hạn, bị lộ, thuộc về người rời team hoặc cần đổi thuật toán. Không nên để một cá nhân giữ khóa duy nhất không có backup/transfer policy.

Quy trình khuyến nghị:

1. Inventory full fingerprint, key owner/role, expiry và mục đích.
2. Dùng signing subkey/dedicated release key thay vì master key hằng ngày khi phù hợp.
3. Lưu key material trong secret manager/GPG protected store có access logs.
4. Quy định ai được phép tạo/rotate/revoke và ai được approve release.
5. Tạo recovery/revocation plan trước khi sự cố xảy ra.
6. Đối chiếu public key fingerprint ở kênh công bố chính thức.
7. Cập nhật CI secret reference và verify pipeline với key mới.
8. Ghi lại thời điểm cutover và các versions được ký bởi fingerprint nào.
9. Khi phát hiện lộ khóa, revoke, thông báo consumer và đánh giá lại artifacts đã ký.
10. Không xóa key cũ/public historical metadata nếu việc verify releases trước đó còn cần, trừ khi retention/policy yêu cầu.

### 18.2. Khóa hết hạn thì artifact cũ thế nào?

Không thể chỉ dựa vào thông báo “expired” rồi kết luận mọi signature của historical releases đều vô giá trị. OpenPGP verification/trust policy có thể xét thời điểm ký, thời gian hiệu lực, revocation và bằng chứng timestamp phù hợp. **Không tự đổi artifact cũ** để “gia hạn chữ ký” mà không có chính sách phát hành.

Trong release process, cần có kế hoạch rotate trước khi signing key hết hạn, kiểm thử consumer verification và công bố full fingerprint của khóa mới.

### 18.3. Khóa bị lộ

Nếu private key bị lộ:

- Dừng signing releases bằng khóa đó.
- Revoke theo quy trình OpenPGP/tổ chức.
- Điều tra CI, secret store, logs và phạm vi lộ.
- Xem xét releases được ký trong khoảng nghi ngờ.
- Rotate sang key mới qua trusted approval.
- Công bố thông tin xác thực key mới qua kênh độc lập đáng tin.
- Không chỉ xóa key khỏi Git ở commit mới: **Git history có thể vẫn chứa secret**, cần xử lý/thu hồi key ngay cả khi history được rewrite.

## 19. Lỗi thường gặp trong Gradle Signing

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| **Task signMavenJavaPublication not found** | Chưa sign publication, sai publication name, plugin chưa áp dụng | Kiểm tra signing DSL, mavenJava và tasks --all |
| **Cannot perform signing task because it has no configured signatory** | Release required nhưng chưa có key đúng | Cấp ORG_GRADLE_PROJECT_signingKey/signingPassword qua trusted secret store |
| **Wrong PGP secret key / invalid armored block** | CI secret bị mất newline, copy thiếu header/footer hoặc dùng public key | Kiểm tra định dạng secret ở secret manager, không in key ra log |
| **Incorrect passphrase** | Mật khẩu không khớp key, secret store chứa phiên bản cũ | Rotate/fix secret reference, không bỏ bảo vệ key |
| **No signature .asc after publish** | Signing không required ở SNAPSHOT, sign target sai hoặc task skipped | Xem version/policy/task graph/signing credentials |
| **JAR.asc có nhưng POM.asc không** | Chỉ ký task jar thay vì MavenPublication | Ký publishing.publications.mavenJava |
| **GPG good signature nhưng cảnh báo untrusted** | Public key có nhưng identity chưa xác minh | So fingerprint theo trusted channel |
| **BAD signature** | Artifact bị thay bytes hoặc signature ghép nhầm tệp | Verify đúng pair cùng version/checksum, điều tra tampering |
| **No public key** | GPG chưa import đúng release public key | Lấy khóa từ nguồn tin cậy, kiểm tra fingerprint rồi import |
| **Different key fingerprint** | Rotate key chưa công bố hoặc giả mạo | Dừng chấp nhận release, xác minh owner/signing policy |
| **Key expired/revoked** | Key lifecycle chưa được quản lý | Kiểm tra lịch sử/revocation policy, rotate theo quy trình |
| **gpg executable not found** | useGpgCmd nhưng CI/host chưa cài GnuPG | Cài đúng executable hoặc dùng in-memory PGP |
| **gpg-agent/pinentry error** | Agent không tương tác được trên CI, key locked | Cấu hình noninteractive GPG/agent đúng hoặc dùng in-memory |
| **sign works locally but CI fails** | Local keyring hiện có, CI thiếu key/permission/newline | Đưa secrets qua protected env và kiểm tra runtime |
| **test passes but publish fails signing** | Signing chỉ chạy khi publication được publish | Đây là boundary đúng; kiểm tra credentials/release gate |
| **SNAPSHOT unsigned** | required=false, không có signatory | Đúng nếu policy cho phép; không promote thành release |
| **release unsigned dù publish pass** | required bị đặt false/logic release sai | Enforce signing policy và kiểm tra published .asc |
| **Private key lộ trong CI log** | Debug print/environment dump/set -x | Thu hồi key, làm sạch logs, sửa pipeline và rotate |
| **Private key xuất hiện trong Git history** | Đã commit file key/gradle.properties | Revoke/rotate ngay; xử lý history theo policy |
| **Signatures khác nhau giữa runs** | OpenPGP signing chứa thời gian/metadata/algorithm randomness | Không đòi .asc byte-for-byte giống mọi lần; verify từng signature |
| **Artifact bị thay sau khi sign** | Publisher/transformer đổi bytes | Ký artifact cuối cùng, không chỉnh sau ký |
| **Maven repository thiếu files** | Publish config/task/repository staging sai | Kiểm tra generated publication files và repo layout |
| **POM có credentials** | Nhầm repository auth với POM metadata | Không đưa secrets vào POM/build artifacts |
| **Module metadata signature không tồn tại** | Không publish Gradle Module Metadata hoặc khác Gradle behavior | Kiểm tra publication contents và signing targets |
| **Only CI secrets available for PRs** | Quyền pipeline sai, không an toàn | Tách PR test và protected release signing |
| **Cannot find Java 17 toolchain** | JDK/Gradle version/provisioning không phù hợp | Cài JDK17, dùng Gradle Wrapper tương thích |
| **Signature verification pass nhưng malware vẫn có** | Khóa ký thuộc người phát hành nhưng build compromised | Thêm SLSA/provenance, reviews, tests và supply-chain controls |

### 19.1. Debug theo thứ tự

~~~text
Ký/publish release không đúng?
             |
             v
1. Đúng project/module và publication name?
             |
             v
2. maven-publish + signing plugins có áp dụng?
             |
             v
3. signMavenJavaPublication có trong task graph?
             |
             v
4. isRelease/required quyết định chính sách nào?
             |
             v
5. CI có cấp đúng signingKey/signingPassword?
             |
             v
6. Khóa có là secret OpenPGP ASCII-armored hợp lệ?
             |
             v
7. Sign task có tạo *.asc cho các artifact/metadata?
             |
             v
8. Publish đưa đúng file vào repository staging?
             |
             v
9. GPG verify bằng đúng trusted public key/fingerprint?
             |
             v
10. Release approvals, SBOM, artifact digest và logs đủ?
~~~

Lệnh kiểm tra không in secrets:

~~~bash
./gradlew --version
./gradlew tasks --all
./gradlew help --task signMavenJavaPublication
./gradlew -PreleaseVersion=1.0.0 \
    publish --dry-run

gpg --list-keys --keyid-format LONG
gpg --fingerprint
~~~

**--dry-run không thực hiện signing action hoặc publish**, chỉ giúp xem task graph. Không dùng nó làm bằng chứng chữ ký tồn tại.

## 20. CI security checklist cụ thể

Trước khi cho một job nhận secret signing key:

- [ ] Job chỉ chạy ở protected tags/branches và sau approval.
- [ ] Untrusted PR/fork code không được nhận signing private key.
- [ ] Người sửa build scripts/CI workflows được kiểm soát.
- [ ] CI secret được quản lý ở secret store, không chứa trong YAML/source.
- [ ] Không có **set -x**, environment dumps, println key hoặc debug logs lộ secrets.
- [ ] Secret chỉ được inject vào step ký và được hủy sau job theo runner policy.
- [ ] Key có passphrase và owner/rotation/revocation policy.
- [ ] Full public fingerprint được công bố từ kênh độc lập đáng tin.
- [ ] Release signing.required=true theo version/pipeline policy.
- [ ] Build/tests thành công trước bước promote artifacts.
- [ ] MavenPublication gồm đúng JAR, sources/Javadoc và metadata.
- [ ] Không xuất bản SNAPSHOT unsigned dưới version release chính thức.
- [ ] Detached .asc cho từng artifact quan trọng được tạo và upload.
- [ ] Consumer verify chữ ký và fingerprint, không chỉ hash.
- [ ] Repository publish token tách khỏi signing secret và có quyền tối thiểu.
- [ ] Wrapper, plugins, dependencies được kiểm soát/verify/pin phù hợp.
- [ ] Không ký artifacts từ unverified external job mà không kiểm tra digest/provenance.
- [ ] Có audit record: commit SHA, artifact coordinate/version, checksums, signing fingerprint, CI run ID.
- [ ] Nếu khóa bị lộ, có quy trình revoke/rotate/incident response.

## 21. Bài tập thực hành

### Bài 1 — Task graph signing

Chạy **./gradlew tasks --all** và **./gradlew help --task signMavenJavaPublication**. Giải thích vì sao task ký xuất hiện sau khi **sign publishing.publications.mavenJava**, nhưng lệnh **test** không cần ký.

### Bài 2 — Snapshot không có secret

Với version mặc định **1.0.0-SNAPSHOT**, chạy **./gradlew clean test publish**. Quan sát staging repository và giải thích vì sao policy cho phép snapshot không ký mà không nên áp dụng cho release.

### Bài 3 — Release không có secret

Trong môi trường không có signingKey/signingPassword, chạy:

~~~bash
./gradlew -PreleaseVersion=1.0.0 publish
~~~

Quan sát error của Sign task và giải thích vì sao build fail là đúng. Không “chữa” bằng required=false. Không cần private key thật để hoàn thành bài tập này.

### Bài 4 — Ký release trên môi trường riêng

Trong một môi trường thử nghiệm được phép, tạo signing key tạm và lưu **bên ngoài repository**. Cấp private key/password qua secret manager, chạy release publish tới localStaging, kiểm tra JAR/POM/sources **.asc**.

Không copy/private key vào chat, README hoặc test artifact. Dùng **dedicated test key**, không dùng key production của công ty.

### Bài 5 — Xác minh public fingerprint

Import public key của lab vào GPG, kiểm tra full fingerprint và chạy **gpg --verify**. Giải thích vì sao GPG có thể báo chữ ký đúng nhưng vẫn cảnh báo chưa xác lập trust.

### Bài 6 — Đổi bytes sau signing

Copy JAR sang một thư mục tạm và thay đổi nội dung bản sao, không sửa repository release. Thử verify signature cũ trên bản sao. Giải thích vì sao chữ ký phải gắn với đúng bytes được publish.

### Bài 7 — Chỉ ký JAR

Đổi tạm signing target sang task **jar** thay vì MavenPublication, sau đó so sánh artifacts đã được ký. Vì sao một Maven release đúng có thể cần ký cả POM/metadata? Khôi phục publication signing.

### Bài 8 — Thêm sources/Javadoc

Tạm bỏ **withSourcesJar()/withJavadocJar()**, kiểm tra publication artifacts và Sign task outputs, sau đó bật lại. Vì sao không nên giả mọi publication đều có đúng năm file?

### Bài 9 — Chuyển sang GnuPG

Trong một branch thử nghiệm ở máy có GPG-agent, thay in-memory block bằng **useGpgCmd()**, chọn key có kiểm soát và publish local staging. So sánh security tradeoffs với việc đưa ASCII-armored key qua CI env.

### Bài 10 — Mất newline của secret

Trong môi trường test cô lập, cố tình cung cấp một secret string không còn đúng định dạng armor (không dùng private key production) và đọc lỗi. Giải thích vì sao secret manager cần bảo toàn multiline; không in key để debug.

### Bài 11 — Rotation incident

Giả lập tình huống signing subkey bị lộ. Viết checklist: revoke, rotate, update public fingerprint, thông báo consumers, kiểm tra releases và CI audit. Không chỉ xóa secret khỏi git ở commit mới.

### Bài 12 — Separation of duties

Thiết kế CI cho team: developer có quyền push code, release approver có quyền approve, protected runner có quyền đọc private key, deploy job có quyền publish token. Vì sao một người/step không nhất thiết phải nắm mọi quyền?

## 22. Câu hỏi tự kiểm tra

1. Gradle Signing plugin tạo loại chữ ký nào?
2. Tệp **.asc** có phải bản mã hóa của JAR không?
3. Public key và private key có trách nhiệm khác nhau ra sao?
4. Vì sao chỉ thấy “Good signature” chưa đủ để tin artifact?
5. Full fingerprint đáng tin cậy hơn short key ID ở đâu?
6. **signing** plugin có tự tạo **mavenJava** publication không?
7. Task **signMavenJavaPublication** xuất hiện từ cấu hình nào?
8. Vì sao ký riêng JAR không bảo đảm POM đã được ký?
9. **publish** khác **sign** và **build** như thế nào?
10. **ORG_GRADLE_PROJECT_signingKey** được Gradle chuyển thành property nào?
11. **useInMemoryPgpKeys(...)** có tự mã hóa/ẩn secret khỏi mọi build plugin không?
12. Vì sao không commit **~/.gradle/gradle.properties** có secret vào repo?
13. Có thể dùng **useGpgCmd()** khi máy không có GnuPG không?
14. **required=false** ở snapshot có nghĩa release được phép unsigned không?
15. Vì sao release không có signing key nên thất bại khi publish?
16. Khi nào CI phải cấp private key?
17. Vì sao không cấp key cho build từ PR không tin cậy?
18. **gpg --verify** cần những tệp nào?
19. Vì sao ký trước rồi sửa JAR khiến verification fail?
20. Signing key hết hạn hoặc bị revoke cần xử lý ra sao?
21. Public key có thể chia sẻ rộng rãi không, cần kiểm soát gì?
22. Chữ ký OpenPGP có thay thế SBOM/provenance/kiểm thử không?
23. Maven Central/public repository có thể yêu cầu ký những thành phần nào?
24. Vì sao **publishToMavenLocal** không phải xác nhận release đã lên server?
25. Java 17 compiler thành công có chứng minh artifact ký đúng không?
26. Khi dùng signing subkey, API ba tham số của Gradle dùng để làm gì?
27. Tại sao repository credentials và signing credentials cần tách biệt?
28. Một snapshot unsigned có được xem là release artifact chính thức không?
29. Vì sao môi trường CI cần tránh debug environment dump?
30. Có cần luôn ký toàn bộ nội dung thư mục **build/** không?

**Đáp án gợi ý:** (1) OpenPGP; (2) không; (3) private ký, public verify; (4) phải xác minh identity/fingerprint; (5) hạn chế nhầm/giả mạo ID ngắn; (6) không; (7) sign publication; (8) file metadata độc lập; (9) build tạo, sign tạo chữ ký, publish upload; (10) signingKey; (11) không; (12) lộ secret; (13) không; (14) không; (15) signing.required theo release; (16) chỉ trusted release job; (17) build code có thể đọc/lộ secret; (18) detached .asc và artifact đúng bytes, public key đáng tin; (19) chữ ký ràng buộc bytes; (20) rotate/revoke/inform; (21) có, xác minh full fingerprint; (22) không; (23) JAR, POM, sources/Javadoc, metadata theo policy; (24) chỉ local; (25) không; (26) chỉ định subkey ID, secret key, password; (27) least privilege; (28) không; (29) ngăn lộ private key; (30) không, ký targets phục vụ publication/verification contract.

## 23. Tài liệu Gradle và OpenPGP chính thức

- [Gradle — The Signing Plugin](https://docs.gradle.org/current/userguide/signing_plugin.html)
- [Gradle — Signing Artifacts](https://docs.gradle.org/current/userguide/publishing_signing.html)
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html)
- [Gradle — Build Environment: Project Properties](https://docs.gradle.org/current/userguide/build_environment.html)
- [Gradle — Publishing Overview](https://docs.gradle.org/current/userguide/publishing_overview.html)
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html)
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)
- [Gradle — Configuring Publication Repositories](https://docs.gradle.org/current/userguide/publishing_maven.html)
- [GnuPG — Manual](https://gnupg.org/documentation/manuals/gnupg/)
- [OpenPGP — IETF Standards](https://www.rfc-editor.org/rfc/rfc9580)
- [GitHub Actions — Using Secrets](https://docs.github.com/en/actions/security-guides/using-secrets-in-github-actions)

**Kết luận:** Gradle Signing plugin giúp ký Maven publication hoặc những artifact outputs được chọn bằng OpenPGP, tạo detached **.asc** để consumer xác minh bằng public key. Nhưng **ký đúng file**, **giữ private key ngoài source**, **chỉ cấp khóa cho trusted release CI**, **bắt buộc ký ở release**, **verify fingerprint từ kênh tin cậy** và **quản lý rotation/revocation** mới tạo nên quy trình phát hành có trách nhiệm. Một chữ ký hợp lệ là bằng chứng về bytes và khóa, không phải giấy chứng nhận tự động rằng phần mềm không có lỗ hổng.
