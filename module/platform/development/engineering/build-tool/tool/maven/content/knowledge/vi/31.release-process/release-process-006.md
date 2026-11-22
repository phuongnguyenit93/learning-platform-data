# Chữ ký artifact và cấu hình plugin ký phù hợp trong quy trình phát hành Maven

## 1. Vì sao JAR đã build thành công vẫn cần chữ ký?

Giả sử nhóm của bạn phát hành Java library `demo.sign:signed-greeter:1.0.0`. Bản JAR compile và test thành công, được upload lên Maven repository. Tuy vậy, consumer ở một máy khác vẫn cần trả lời:

- File vừa tải có đúng những bytes mà người phát hành đã ký hay không?
- Chữ ký thuộc về public key nào? Public key đó có thật sự được tổ chức/người phát hành tin cậy quản lý không?
- POM, main JAR, sources JAR và Javadoc JAR có được ký **đúng từng file** hay chỉ một file bất kỳ?
- Khi artifact bị sửa sau khi ký, quá trình xác minh có phát hiện thay đổi không?
- Quy trình CI lấy private key/passphrase từ đâu mà không làm lộ chúng vào Git, POM, terminal history hoặc logs?
- Maven plugin ký chạy ở giai đoạn nào, trước hay sau các plugin đóng gói và trước hay sau deploy?

Trong hệ sinh thái Maven, một lựa chọn phổ biến là **OpenPGP detached signatures** được tạo bởi Maven GPG Plugin. Các chữ ký thường là file có hậu tố `.asc` đi kèm artifact.

Bài Knowledge thuộc nhóm **Quy trình phát hành**, tập trung vào **chữ ký artifact và cấu hình plugin ký phù hợp**, không đánh đồng việc ký với biên dịch, checksum, mã hóa nội dung, kiểm thử hoặc xuất bản.

**Sau bài này bạn có thể:**

1. Hiểu cặp khóa công khai/bí mật, fingerprint, detached signature, chữ ký `.asc`, integrity và authenticity.
2. Phân biệt OpenPGP artifact signing với SHA-256 checksum, TLS, Java `jarsigner` và software provenance.
3. Cấu hình Maven GPG Plugin `3.2.8`, goal `gpg:sign` tại `verify`, trước `install`/`deploy`.
4. Ký main JAR, project POM, sources JAR và Javadoc JAR, kiểm tra thứ tự các plugin.
5. Thực hành project Java 17, JUnit 5, Source/Javadoc plugins và profile `release-signing`.
6. Tạo key thử nghiệm riêng, ký artifact trong môi trường được kiểm soát và dùng `gpg --verify` kiểm tra bản đã xuất bản.
7. Quản lý private key/passphrase an toàn ở workstation và CI; hiểu `bestPractices`, `gpg-agent` và `MAVEN_GPG_PASSPHRASE`.
8. Phân biệt GnuPG signer `gpg` với Bouncy Castle signer `bc` trong plugin 3.2.x.
9. Hiểu yêu cầu chữ ký khi xuất bản lên Maven Central và khác biệt giữa signing với publishing.
10. Chẩn đoán key unavailable, passphrase lỗi, thiếu `.asc`, byte mismatch, verify good nhưng key chưa trusted và partial release.

Phạm vi: Maven 3.x, JDK 17, GnuPG 2.x và Maven GPG Plugin `3.2.8`. Các plugin versions khác trong ví dụ được ghim để dễ tái hiện; dự án thật cần kiểm tra compatibility/release notes.

## 2. Mô hình chữ ký OpenPGP cho Maven artifacts

Mô hình tối giản:

~~~text
Producer
    artifact bytes (JAR, POM, sources, Javadoc)
                         │
                         ▼
              OpenPGP signing operation
           dùng PRIVATE KEY + thuật toán băm
                         │
                         ▼
                   detached .asc
                         │
                         ▼
             Maven repository chứa:
                   artifact gốc
                   artifact.asc
                         │
                         ▼
Consumer tải artifact + .asc + PUBLIC KEY đáng tin
                         │
                         ▼
              gpg --verify signature file
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
        Good signature          BAD signature
        bytes không đổi         nội dung/chữ ký/key
        theo public key         không khớp
~~~

Một chữ ký **detached** là file riêng. Nội dung JAR/POM **không cần bị sửa** để lưu chữ ký; `.asc` có thể đi cùng file gốc trong Maven repository. Nếu ký `signed-greeter-1.0.0.jar`, đối tượng xác minh là cặp:

~~~text
signed-greeter-1.0.0.jar
signed-greeter-1.0.0.jar.asc
~~~

Maven GPG Plugin tạo chữ ký cho **project POM** và các artifacts đã được project attach tại thời điểm plugin ký. Không phải mọi file trong `target` tự trở thành Maven artifact hoặc tự được ký.

### Private key và public key khác nhau

- **Private key**: chỉ chủ sở hữu/người được cấp quyền ký được dùng; không commit Git, không upload lên repository công khai và không đưa vào tài liệu đào tạo thật.
- **Public key**: dùng xác minh; có thể được chia sẻ công khai, nhập bằng `gpg --import` hoặc lấy từ nguồn đã xác minh.
- **Fingerprint**: định danh dài của key, giúp đối chiếu key nhận được với key được công bố qua một kênh tin cậy.
- **Passphrase**: bảo vệ secret key khi lưu/được dùng. Passphrase **khác** mật khẩu repository để publish.

**Chữ ký tốt chứng minh file khớp private key tương ứng với public key đã dùng; chưa tự chứng minh danh tính xã hội/tổ chức của người phát hành.** Nếu attacker đưa vào một public key giả của chính họ rồi nói đó là khóa của dự án, `gpg --verify` cũng có thể báo Good signature với key giả. Vì thế cần xác minh fingerprint qua một kênh đáng tin cậy.

## 3. Chữ ký khác checksum, TLS và `jarsigner`

| Công cụ/cơ chế | Kiểm tra gì? | Giới hạn |
| --- | --- | --- |
| SHA-256/SHA-512 checksum | File bytes có khớp digest được công bố không? | Nếu attacker thay cả file và checksum, việc so khớp không chứng minh người ký. |
| Detached OpenPGP `.asc` | File bytes khớp chữ ký tạo bởi private key tương ứng. | Cần lấy public key đáng tin và bảo vệ private key. |
| HTTPS/TLS | Bảo vệ kết nối với endpoint được xác thực tại thời điểm truyền. | Không thay thế verification sau khi tải hoặc provenance của người xây artifact. |
| Java `jarsigner` | Ký các entries bên trong JAR theo mô hình Java signing. | Không đồng nghĩa với Maven Central yêu cầu OpenPGP `.asc` cho từng file. |
| CI provenance/attestation | Ghi nguồn, workflow và build identity theo một mô hình chứng thực. | Có thể bổ sung chứ không tự thay chính sách PGP của repository. |
| Unit tests/quality gates | Kiểm chứng hành vi và tiêu chuẩn nội bộ trước phát hành. | Artifact có thể chạy đúng nhưng chưa được ký; hoặc đã ký nhưng còn bug. |

### Ví dụ checksum

~~~bash
sha256sum signed-greeter-1.0.0.jar
~~~

Cho ra digest phụ thuộc binary thực tế, **không có giá trị hex cố định** trong bài. Checksum rất hữu ích để phát hiện lỗi truyền/copy, nhưng nếu nguồn cung cấp digest bị giả mạo thì checksum không đủ.

### Ví dụ detached signature

~~~bash
gpg --verify signed-greeter-1.0.0.jar.asc signed-greeter-1.0.0.jar
~~~

Nếu chữ ký hợp lệ với public key đã nhập, GnuPG thông báo ý nghĩa tương đương `Good signature` và hiện fingerprint/key information. Nếu key chưa được trust, GnuPG có thể đồng thời cảnh báo trust chưa được thiết lập: **đừng xóa cảnh báo bằng cách auto-trust mọi key**, hãy kiểm tra fingerprint trước.

### Java JAR signature không tương đương PGP artifact signature

`jarsigner` ký JAR nội bộ dựa trên JAR signing format. Maven repository thường dùng **OpenPGP detached signature** cho main JAR, POM, source/Javadoc artifacts. Không tạo `.asc` bằng `jarsigner`. Khi repository đích yêu cầu PGP signatures, dùng công cụ phù hợp (ví dụ Maven GPG Plugin) và theo đúng requirements của repository.

## 4. Những file nào phải có chữ ký?

Một library release Java thường publish:

~~~text
signed-greeter-1.0.0.pom
signed-greeter-1.0.0.jar
signed-greeter-1.0.0-sources.jar
signed-greeter-1.0.0-javadoc.jar
~~~

Khi chính sách repository yêu cầu OpenPGP signature cho từng file (ví dụ Maven Central), cần những files đi kèm:

~~~text
signed-greeter-1.0.0.pom.asc
signed-greeter-1.0.0.jar.asc
signed-greeter-1.0.0-sources.jar.asc
signed-greeter-1.0.0-javadoc.jar.asc
~~~

Nếu thêm classifier như `all` hoặc `tests` và upload nó, cũng cần xem chính sách ký đối với artifact tương ứng. GPG Plugin ký những main/attached artifacts đã tồn tại lúc `gpg:sign` chạy.

**Mốc quan trọng: các plugin tạo sources/Javadoc/fat JAR phải hoàn tất trước plugin ký**, nếu muốn chữ ký của các file đó được sinh và attach tự động.

### Vì sao POM cũng cần ký?

POM chứa dependency metadata, parent references, packaging và các thông số ảnh hưởng Maven resolution. Một JAR có chữ ký tốt nhưng POM publish bị thay đổi có thể dẫn consumer tới dependency graph khác. Khi repository yêu cầu, **cả POM lẫn binary artifacts phải có detached signatures riêng**.

### Dạng file trên disk và trong repository

GPG Plugin mặc định dùng `ascDirectory` dưới `${project.build.directory}/gpg` để ghi các chữ ký tạm cho build. Khi được attach và deploy thành công, repository có file `.asc` cạnh artifact gốc theo Maven layout. **Không nhất thiết suy từ một path local duy nhất**: xác nhận bằng plugin logs và danh sách file repository thực tế.

## 5. Goal `gpg:sign` và vị trí trong lifecycle

Maven GPG Plugin `3.2.8` có goal:

~~~text
org.apache.maven.plugins:maven-gpg-plugin:3.2.8:sign
~~~

Goal này ký **project artifact, project POM và attached artifacts** để deploy. Theo tài liệu plugin, goal `sign` có default phase `verify`. Trong một POM rõ ràng, ta vẫn khai báo execution bind tới `verify` để người đọc thấy thứ tự mong đợi.

~~~text
compile
  │
  ▼
test      — unit tests
  │
  ▼
package   — main JAR + sources/Javadoc JAR (attach)
  │
  ▼
verify    — gpg:sign, tạo và attach chữ ký .asc
  │
  ▼
install   — local repository
  │
  ▼
deploy    — deployment repository
~~~

**Không chạy `gpg:sign` quá sớm ở `compile` nếu source/Javadoc/plugins packaging chưa tạo attachments.** Nếu một plugin tạo artifact muộn sau `verify`, chữ ký có thể thiếu. Phải điều chỉnh execution phase/goal order và kiểm tra tập published artifacts thực tế.

### `mvn package` và `mvn verify` khác nhau

- `mvn package`: trong cấu hình bài lab, main/source/Javadoc JARs được tạo; goal ký gắn `verify` **chưa chạy**.
- `mvn verify` với profile ký: chạy qua package rồi ký các artifacts đã có.
- `mvn install` hoặc `mvn deploy` với profile ký: đi qua verify, có thể cài/publish signatures đã attach.

Một câu trả lời sai thường gặp là "đã chạy `mvn package` thì chắc chắn có `.asc`". Điều đó **sai** nếu signing goal nằm ở `verify`.

### Vì sao dùng profile ký phát hành?

Bản build của mọi developer có thể không có private key. Nếu plugin ký luôn hoạt động, `mvn test` hoặc `mvn verify` trên một máy/PR không có key dễ thất bại vì thiếu secret chứ không phải lỗi Java.

Đặt signing execution vào profile `release-signing` (không active mặc định) cho phép:

~~~bash
mvn clean verify                     # build/test mặc định, không ký
mvn -Prelease-signing clean verify   # build/test và ký
mvn -Prelease-signing clean deploy   # build/test/ký rồi publish
~~~

Trong release pipeline, **phải bảo đảm profile này thực sự được kích hoạt**; `BUILD SUCCESS` của build không ký không chứng minh đã đáp ứng yêu cầu publication.

## 6. Maven GPG Plugin: cấu hình ký với thực hành bảo mật

Một mảnh POM minh họa:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-gpg-plugin</artifactId>
    <version>3.2.8</version>
    <executions>
        <execution>
            <id>sign-artifacts</id>
            <phase>verify</phase>
            <goals>
                <goal>sign</goal>
            </goals>
            <configuration>
                <bestPractices>true</bestPractices>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Các điểm quan trọng:

- `<version>3.2.8</version>` ghim plugin, không lấy ngẫu nhiên version khác qua plugin resolution.
- `<id>sign-artifacts</id>` giúp xác định execution trong logs/effective POM.
- `<phase>verify</phase>` đảm bảo plugin ký sau phases đóng gói thông thường.
- `<bestPractices>true</bestPractices>` yêu cầu plugin phát hiện một số cách xử lý secret không an toàn, thay vì chỉ warning.
- Goal `sign` tạo/attach signatures, nhưng **không tự publish** lên repository nếu không chạy phase deploy/publishing mechanism tương ứng.

### Những tùy chọn hữu ích

| Tham số/property | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `bestPractices` / `gpg.bestPractices` | Enforce best-practices về secret handling. | Plugin 3.2.x mặc định `false` vì backward compatibility; nên bật khi đã chuẩn bị môi trường. |
| `signer` / `gpg.signer` | `gpg` (GnuPG executable) hoặc `bc` (Bouncy Castle Java signer). | Hai signer có cách lấy key khác nhau. |
| `keyname` / `gpg.keyname` | Chọn key identity cho GnuPG signer. | Cần key signing có sẵn trong đúng keyring. |
| `homedir` / `gpg.homedir` | GnuPG home/keyring directory. | Không trỏ vào thư mục public/source-tracked chứa private key. |
| `keyEnvName` / `gpg.keyEnvName` | Tên env variable chứa BC signer private key. | Dành cho `bc`, mặc định `MAVEN_GPG_KEY`. |
| `passphraseEnvName` / `gpg.passphraseEnvName` | Tên env chứa passphrase; mặc định `MAVEN_GPG_PASSPHRASE`. | CI injection từ secret store, không hardcode trong POM. |
| `useAgent` / `gpg.useagent` | Cho phép dùng gpg-agent. | Không-interactive session cần agent đã cache hoặc passphrase qua env. |
| `ascDirectory` | Thư mục lưu signature files của build. | Default `${project.build.directory}/gpg`. |
| `skip` / `gpg.skip` | Bỏ ký. | Không được bật trong release job yêu cầu chữ ký. |
| `excludes` | Những file patterns bỏ qua khi ký. | Đừng loại main JAR/POM/sources/Javadoc ngoài ý định. |

### Không dùng những cách chứa passphrase lỗi thời

Không dùng:

~~~xml
<passphrase>my-real-secret</passphrase>
~~~

hoặc:

~~~bash
mvn -Dgpg.passphrase=my-real-secret deploy
~~~

Chúng có thể làm lộ secret trong POM, Git, shell history, process arguments hoặc logs. Plugin `3.2.x` đánh dấu `passphrase` và `passphraseServerId` là **deprecated**; `bestPractices=true` có thể từ chối cách dùng không an toàn.

Trên workstation, ưu tiên **gpg-agent** và pinentry tương tác. Trên CI batch, cấp `MAVEN_GPG_PASSPHRASE` qua secret store/environment injection; không in giá trị và không dùng `set -x`.

## 7. Mô hình khóa thử nghiệm an toàn

Trước khi làm bài lab, cần có GnuPG. Trên Linux/macOS:

~~~bash
gpg --version
gpg --list-secret-keys --keyid-format LONG
~~~

Trên Windows PowerShell cũng có thể dùng:

~~~powershell
gpg --version
gpg --list-secret-keys --keyid-format LONG
~~~

Nếu máy có key phát hành thật, **đừng dùng nó để luyện tập**. Hãy tạo **key test riêng** trong một GnuPG home không thuộc Git checkout.

### 7.1. Tạo home thử nghiệm (Linux/macOS)

Trong **cùng terminal session** dùng cho các bước build:

~~~bash
mkdir -p "$HOME/.gnupg-maven-training"
chmod 700 "$HOME/.gnupg-maven-training"
export GNUPGHOME="$HOME/.gnupg-maven-training"
gpg --full-generate-key
~~~

Khi wizard hỏi thông tin, chọn loại key có khả năng ký (ví dụ RSA signing key được hỗ trợ), đặt UID như:

~~~text
Name: Maven Training
Email: maven-training@example.invalid
~~~

và chọn passphrase phù hợp cho bài lab. **Không tạo key production không passphrase chỉ để tránh cấu hình gpg-agent.** Với môi trường CI, không tạo key mới mỗi lần publish release: key identity cần được quản trị ổn định.

GnuPG versions khác nhau có menu/wizard khác nhau. Không có một transcript stdout giống nhau cho mọi hệ điều hành. Quan trọng là sau khi tạo:

~~~bash
gpg --list-secret-keys --keyid-format LONG
gpg --fingerprint "maven-training@example.invalid"
~~~

phải hiện key có khả năng ký và fingerprint. Đây là key **thử nghiệm**, tuyệt đối không dùng làm chữ ký identity cho dự án thật.

### 7.2. Export chỉ PUBLIC KEY

~~~bash
gpg --armor --output "$HOME/maven-training-public.asc" --export "maven-training@example.invalid"
~~~

File `maven-training-public.asc` có thể chia sẻ để người khác import và verify. **Không chạy `--export-secret-keys` để minh họa public-key sharing**; command đó xuất private key, có thể làm lộ quyền ký.

Trên Windows, có thể xuất file public bằng:

~~~powershell
gpg --armor --output "$HOME\maven-training-public.asc" --export "maven-training@example.invalid"
~~~

Dùng `--output` thay vì tùy tiện chuyển GnuPG ASCII output qua PowerShell 5.1 redirection có thể làm thay đổi encoding file.

### 7.3. Vì sao phải xác minh fingerprint?

Nếu consumer tải public key từ một URL không tin cậy, attacker có thể cung cấp key của họ cùng bản JAR đã bị thay. `Good signature` với key giả **không** bảo đảm chữ ký thuộc về dự án mong muốn. Dự án thật cần công bố fingerprint qua website/SCM/release security channel đáng tin, và consumer đối chiếu đầy đủ fingerprint trước khi tin key.

## 8. Dự án Java 17 runnable: ký POM, JAR, sources, Javadocs

Ta tạo:

~~~text
maven-signing-lab/
├── producer/
│   ├── pom.xml
│   └── src/
│       ├── main/java/demo/sign/Greeter.java
│       └── test/java/demo/sign/GreeterTest.java
└── signed-repo/             # Kho file được tạo/ghi khi deploy
~~~

Project gồm:

- Java 17 library `demo.sign:signed-greeter:1.0.0`.
- Hai JUnit 5 tests.
- Main JAR sinh ở package.
- Source JAR và Javadoc JAR được attach trong package, nhưng **chỉ khi bật release-signing profile** trong ví dụ.
- Maven GPG Plugin ký các files tại verify, cũng trong profile.
- Maven Deploy Plugin publish artifact/POM/signatures vào **file repo thử nghiệm**, không tới Maven Central.

### 8.1. `producer/pom.xml` đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo.sign</groupId>
    <artifactId>signed-greeter</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <distributionManagement>
        <repository>
            <id>lab-signed-releases</id>
            <name>Local Lab Signed Releases</name>
            <url>file://${project.basedir}/../signed-repo</url>
        </repository>
    </distributionManagement>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-deploy-plugin</artifactId>
                <version>3.1.4</version>
            </plugin>
        </plugins>
    </build>

    <profiles>
        <profile>
            <id>release-signing</id>
            <build>
                <plugins>
                    <plugin>
                        <groupId>org.apache.maven.plugins</groupId>
                        <artifactId>maven-source-plugin</artifactId>
                        <version>3.3.1</version>
                        <executions>
                            <execution>
                                <id>attach-sources</id>
                                <phase>package</phase>
                                <goals>
                                    <goal>jar-no-fork</goal>
                                </goals>
                            </execution>
                        </executions>
                    </plugin>

                    <plugin>
                        <groupId>org.apache.maven.plugins</groupId>
                        <artifactId>maven-javadoc-plugin</artifactId>
                        <version>3.11.2</version>
                        <executions>
                            <execution>
                                <id>attach-javadocs</id>
                                <phase>package</phase>
                                <goals>
                                    <goal>jar</goal>
                                </goals>
                            </execution>
                        </executions>
                    </plugin>

                    <plugin>
                        <groupId>org.apache.maven.plugins</groupId>
                        <artifactId>maven-gpg-plugin</artifactId>
                        <version>3.2.8</version>
                        <executions>
                            <execution>
                                <id>sign-artifacts</id>
                                <phase>verify</phase>
                                <goals>
                                    <goal>sign</goal>
                                </goals>
                                <configuration>
                                    <bestPractices>true</bestPractices>
                                    <signer>gpg</signer>
                                    <keyname>maven-training@example.invalid</keyname>
                                </configuration>
                            </execution>
                        </executions>
                    </plugin>
                </plugins>
            </build>
        </profile>
    </profiles>
</project>
~~~

**Vì sao cấu hình này phù hợp?**

1. `packaging=jar` tạo main JAR thông thường.
2. `maven-source-plugin` và `maven-javadoc-plugin` attach artifacts tại phase `package`.
3. `maven-gpg-plugin:3.2.8:sign` chạy phase `verify`, **sau khi các attachments đã được tạo**.
4. `bestPractices=true` buộc cách quản lý secrets an toàn hơn trong phạm vi plugin.
5. `signer=gpg` dùng GnuPG executable và keyring thông qua `GNUPGHOME`.
6. `keyname=maven-training@example.invalid` trỏ test identity, không lấy nhầm key release thật. Khi làm project production, dùng fingerprint/identity đã được tổ chức phê duyệt thay vì giữ email demo.
7. `distributionManagement` trỏ `file:` repo bên ngoài `producer`, không dùng URL của Central/production.
8. Build thông thường không bật profile nên không yêu cầu GPG key và không sinh sources/Javadoc JAR trong demo; release build bật profile để tạo đầy đủ artifacts và ký.
9. Deploy goal được Maven lifecycle bind khi gọi `mvn deploy` đối với JAR packaging.
10. Nếu một source/Javadoc generator fail ở `package`, signing và deploy sẽ không được coi là hoàn tất.

**Windows:** `file://${project.basedir}/../signed-repo` phù hợp nhất với đường dẫn Unix. Nếu lab nằm ở `C:\maven-signing-lab` trên Windows, thay `<url>` thành `file:///C:/maven-signing-lab/signed-repo`, dùng dấu slash của URL. Không điền private key hoặc passphrase vào POM này.

### 8.2. `src/main/java/demo/sign/Greeter.java`

~~~java
package demo.sign;

import java.util.Objects;

/**
 * A tiny Java library used to demonstrate signed Maven artifacts.
 */
public final class Greeter {
    private Greeter() {
    }

    /**
     * Creates a stable greeting.
     *
     * @param name name to greet
     * @return greeting for the supplied name
     * @throws NullPointerException when name is null
     */
    public static String hello(String name) {
        Objects.requireNonNull(name, "name");
        return "Hello " + name + " from signed Maven library";
    }

    public static void main(String[] args) {
        System.out.println(hello("Maven"));
    }
}
~~~

Chương trình chỉ cần Java standard library ở runtime, phù hợp để kiểm tra trực tiếp class output sau build. Public API có Javadoc comments để Javadoc Plugin tạo tài liệu.

### 8.3. `src/test/java/demo/sign/GreeterTest.java`

~~~java
package demo.sign;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreeterTest {
    @Test
    void createsGreeting() {
        assertEquals(
                "Hello Maven from signed Maven library",
                Greeter.hello("Maven"));
    }

    @Test
    void rejectsNull() {
        assertThrows(
                NullPointerException.class,
                () -> Greeter.hello(null));
    }
}
~~~

Hai JUnit 5 tests được Surefire khám phá qua naming convention `*Test`. Maven phase `test` chạy trước `verify`; ký không được dùng để che giấu compile/test failures.

## 9. Kiểm tra Java trước khi cần GPG

Trong `maven-signing-lab/producer`:

~~~bash
mvn --version
java -version
mvn -B -ntp clean verify
~~~

Lệnh này **không** kích hoạt `release-signing`. Kết quả kỳ vọng:

- Compile với release 17.
- `GreeterTest` có 2 tests PASS.
- Sinh `target/signed-greeter-1.0.0.jar`.
- Không mặc định có chữ ký từ execution trong profile chưa active.
- Maven kết thúc `BUILD SUCCESS` nếu môi trường đúng.

Thử chạy code:

~~~bash
java -cp target/classes demo.sign.Greeter
~~~

**Stdout chương trình chính xác:**

~~~text
Hello Maven from signed Maven library
~~~

Không dùng `java -jar target/signed-greeter-1.0.0.jar` trong demo: chưa cấu hình JAR Manifest `Main-Class`. Bài dùng `java -cp` để tránh sai lệch giữa ký artifact và cách khởi động CLI.

## 10. Build với profile ký và xem artifacts

Sau khi tạo key test từ mục 7, bảo đảm `GNUPGHOME` vẫn chỉ đúng home đó trong **cùng shell session**, và gpg-agent có thể yêu cầu/cache passphrase khi ký.

Từ `producer`:

~~~bash
mvn -Prelease-signing clean verify
~~~

Vì profile active:

- Source plugin attach `signed-greeter-1.0.0-sources.jar`.
- Javadoc plugin attach `signed-greeter-1.0.0-javadoc.jar`.
- GPG plugin ký main JAR, POM và các attached source/Javadoc JARs.
- Các detached signature files nằm trong build output, theo cấu hình `ascDirectory` của plugin.
- `verify` **không đồng nghĩa đã deploy**; `signed-repo` chưa chắc có nội dung mới.

### Kiểm tra file bằng lệnh portable

Trên Linux/macOS:

~~~bash
jar tf target/signed-greeter-1.0.0.jar
jar tf target/signed-greeter-1.0.0-sources.jar
jar tf target/signed-greeter-1.0.0-javadoc.jar
~~~

Các điểm cần thấy:

- Main JAR chứa `demo/sign/Greeter.class`.
- Sources JAR chứa `demo/sign/Greeter.java`.
- Javadoc JAR chứa trang/API docs cho `demo.sign.Greeter`.
- GPG execution logs cho thấy ký POM và artifacts.

Không dùng việc có ba JAR làm bằng chứng bốn chữ ký đúng. Chữ ký `POM` là một file riêng, và ký các attachments cần kiểm tra thêm.

### Cảnh báo với `-B`

`mvn -B ...` là batch mode, có thể ngăn gpg-agent mở pinentry dialog tương tác. Nếu key test có passphrase và agent chưa cache, lần chạy với `-B` có thể FAIL dù key hợp lệ.

Ở workstation, bước ký tương tác nên dùng `mvn -Prelease-signing clean verify` khi cần nhập passphrase qua gpg-agent. Trong CI, dùng batch mode cùng **passphrase được inject an toàn** (hoặc agent đã được chuẩn bị). Không bỏ passphrase của private key release chỉ để lệnh batch đỡ lỗi.

## 11. Deploy thử nghiệm rồi xác minh bốn chữ ký

Khi ký tại verify đã PASS và bạn muốn kiểm tra publish vào kho `file:` của lab:

~~~bash
mvn -Prelease-signing clean deploy
~~~

Maven chạy các phases gồm `package`, `verify`, `install` và `deploy`. Trong `maven-signing-lab/signed-repo`, cấu trúc kỳ vọng:

~~~text
signed-repo/
└── demo/
    └── sign/
        └── signed-greeter/
            ├── maven-metadata.xml
            └── 1.0.0/
                ├── signed-greeter-1.0.0.pom
                ├── signed-greeter-1.0.0.pom.asc
                ├── signed-greeter-1.0.0.jar
                ├── signed-greeter-1.0.0.jar.asc
                ├── signed-greeter-1.0.0-sources.jar
                ├── signed-greeter-1.0.0-sources.jar.asc
                ├── signed-greeter-1.0.0-javadoc.jar
                └── signed-greeter-1.0.0-javadoc.jar.asc
~~~

Có thể có checksum/metadata files khác. Đây là **cây kỳ vọng**, không phải toàn bộ listing cố định của Maven output. File `.asc` và file gốc cần khớp tên.

### Xác minh từ đúng repository files

Trên Linux/macOS, đứng ở thư mục `producer`:

~~~bash
gpg --verify ../signed-repo/demo/sign/signed-greeter/1.0.0/signed-greeter-1.0.0.jar.asc ../signed-repo/demo/sign/signed-greeter/1.0.0/signed-greeter-1.0.0.jar
~~~

POM:

~~~bash
gpg --verify ../signed-repo/demo/sign/signed-greeter/1.0.0/signed-greeter-1.0.0.pom.asc ../signed-repo/demo/sign/signed-greeter/1.0.0/signed-greeter-1.0.0.pom
~~~

Sources:

~~~bash
gpg --verify ../signed-repo/demo/sign/signed-greeter/1.0.0/signed-greeter-1.0.0-sources.jar.asc ../signed-repo/demo/sign/signed-greeter/1.0.0/signed-greeter-1.0.0-sources.jar
~~~

Javadoc:

~~~bash
gpg --verify ../signed-repo/demo/sign/signed-greeter/1.0.0/signed-greeter-1.0.0-javadoc.jar.asc ../signed-repo/demo/sign/signed-greeter/1.0.0/signed-greeter-1.0.0-javadoc.jar
~~~

Với public key đúng, mỗi lệnh báo thông điệp tương đương:

~~~text
gpg: Good signature from "Maven Training <maven-training@example.invalid>"
~~~

**Đây là trích đoạn minh họa**, không phải toàn bộ stderr chính xác vì GnuPG in timestamp, key fingerprint và warnings/trust khác nhau tùy phiên bản/keyring. Cần kiểm tra exit code **0** và **fingerprint** cũng như số cặp artifact/signature đúng. Một warning key chưa được trusted không nên bị che giấu.

### Vì sao xác minh repository thay vì chỉ `target`?

Mục tiêu của ký trong release là bảo vệ artifacts **mà consumer thực sự lấy được**. Nếu build tạo `.asc` ở `target` nhưng Deploy Plugin không attach/publish chúng, ký đã chạy mà repository chưa đạt yêu cầu. Xem repository là bước quan trọng bên cạnh plugin logs.

## 12. Kiểm chứng trên máy/khóa khác

Một người nhận cần public key. Họ có thể import public key do dự án cung cấp qua kênh được kiểm tra:

~~~bash
gpg --import maven-training-public.asc
gpg --fingerprint "maven-training@example.invalid"
~~~

Sau đó đối chiếu fingerprint với fingerprint do chủ artifact công bố qua một kênh tin cậy, rồi:

~~~bash
gpg --verify signed-greeter-1.0.0.jar.asc signed-greeter-1.0.0.jar
~~~

Nếu không có public key phù hợp, GnuPG có thể báo `No public key`; đó là **thiếu key để verify**, không có nghĩa artifact chắc chắn bị sửa. Nếu signature verify sai, kiểm tra bytes, key và filenames thay vì chỉ import thêm một key lạ.

### Test phát hiện thay đổi sau khi ký

Trong **bản sao thử nghiệm**, copy JAR đã ký, thêm vài bytes để mô phỏng tampering, rồi xác minh bằng signature của bản gốc:

~~~bash
cp signed-greeter-1.0.0.jar signed-greeter-tampered.jar
printf 'modified' >> signed-greeter-tampered.jar
gpg --verify signed-greeter-1.0.0.jar.asc signed-greeter-tampered.jar
~~~

Lần verify cuối được **mong đợi FAIL** (thường báo BAD signature) vì bytes không còn khớp. Không làm thí nghiệm này trực tiếp trên JAR đang publish hoặc trên repository chung. Đừng sửa một artifact đã ký rồi dùng lại cùng signature.

**Chữ ký OpenPGP được tạo trên bytes**, không phải "các class vẫn compile được". Chỉ một thay đổi metadata ZIP timestamp hoặc sắp xếp entries trong JAR cũng làm signature cũ không còn đúng.

## 13. Lựa chọn GnuPG signer và BC signer

Maven GPG Plugin từ `3.2.0` hỗ trợ hai signer modes.

### Mode 1 — `gpg` signer (mặc định)

~~~xml
<configuration>
    <signer>gpg</signer>
</configuration>
~~~

- Gọi executable `gpg` được cài trên hệ điều hành.
- Dùng GnuPG home/keyring thông thường hoặc `GNUPGHOME`/`gpg.homedir`.
- Có thể dùng gpg-agent cho passphrase.
- Đòi CI runner có GnuPG executable, key material và cơ chế passphrase tương ứng.
- Lab ở mục 8 dùng mode này.

### Mode 2 — `bc` signer (Bouncy Castle thuần Java)

~~~xml
<configuration>
    <signer>bc</signer>
</configuration>
~~~

BC signer không dùng GnuPG keyring `~/.gnupg` để tìm private key giống signer `gpg`. Nó cần key dạng **Transferable Secret Keys (TSK)** qua `keyFilePath` hoặc environment variable, mặc định `MAVEN_GPG_KEY`. Nếu key có passphrase, cần cách cung cấp passphrase an toàn.

Một ví dụ **lệnh mô tả chọn signer**, không áp dụng trực tiếp lên POM lab trước khi chuẩn bị key TSK:

~~~bash
mvn -Prelease-signing -Dgpg.signer=bc clean verify
~~~

Nếu project không có `MAVEN_GPG_KEY` hoặc `gpg.keyFilePath` hợp lệ, lệnh có thể FAIL. Đừng kết luận BC signer tự tạo key hoặc dùng keyring của GnuPG signer.

### Khi chọn mode nào?

| Bối cảnh | `gpg` | `bc` |
| --- | --- | --- |
| Máy developer đã cài GnuPG và gpg-agent | Tự nhiên, ít bước | Cần thiết lập key material riêng. |
| CI image không có gpg executable | Cần cài GnuPG | Có thể phù hợp nếu policy cho phép key qua env/file. |
| Key chỉ tồn tại trong GnuPG keyring | Phù hợp | Không tự đọc keyring như gpg signer. |
| Tối thiểu hóa secret exposure | Có thể dùng agent | Có thể dùng environment secret injection. |
| Quy trình doanh nghiệp | Chọn theo key governance và runtime | Chọn theo key governance và runtime. |

Không có khuyến nghị "BC luôn an toàn hơn" hoặc "gpg luôn an toàn hơn". Bảo mật phụ thuộc cách cấp, bảo vệ, xoay vòng và thu hồi key, không chỉ implementation.

## 14. Passphrase và private key ở CI: mẫu thao tác an toàn

Một CI publish job có thể dùng:

~~~text
Secret store
  ├── private signing key (protected secret)
  ├── signing passphrase (protected secret)
  └── repository upload token (protected secret)
                  │
                  ▼
        Authorized release job only
                  │
                  ▼
     Temp GnuPG home / signer configured
                  │
                  ▼
     Maven verify → gpg:sign → deploy
                  │
                  ▼
    Cleanup ephemeral secret state + audit
~~~

**Private key, passphrase và repository credentials là ba bí mật/loại quyền khác nhau.** Không cấp signing key cho mọi build từ pull request không đáng tin. Một PR chưa review không được quyền kích hoạt release signing vì có thể sửa POM/plugins/scripts để lấy secrets.

### GnuPG signer trên Linux CI, ví dụ dạng khung

CI cần inject `GPG_PRIVATE_KEY_ASCII` và `MAVEN_GPG_PASSPHRASE` bằng secret store. Sau khi secrets đã được cấp, một job có thể chuẩn bị keyring tạm:

~~~bash
export GNUPGHOME="$(mktemp -d)"
chmod 700 "$GNUPGHOME"
printf '%s' "$GPG_PRIVATE_KEY_ASCII" | gpg --batch --import
gpg --list-secret-keys --keyid-format LONG
mvn -B -ntp -Prelease-signing clean deploy
~~~

Đây là **khung CI**, không phải shell script độc lập để chạy trên máy không có secrets. Không in biến private key/passphrase, không bật shell tracing, không lưu private key trong build artifacts; set cleanup/trap phù hợp ngay cả khi job fail. Trên shared runners, bảo vệ secret scope và filesystem permissions. Signing key trong CI phải khớp `<keyname>`/fingerprint được chọn, không dùng test identity từ bài học cho release thật.

### Vì sao không dùng `-Dgpg.passphrase=...`?

Plugin `3.2.x` khuyến nghị passphrase từ agent hoặc environment variable, trong đó tên mặc định là `MAVEN_GPG_PASSPHRASE`. Đưa passphrase vào CLI property dễ lộ trong process list và command history. Đưa vào `pom.xml` dễ lộ trong SCM/artifact metadata. `bestPractices=true` hỗ trợ fail sớm nếu dùng một số cách cũ không an toàn.

### Batch và gpg-agent

Trong batch mode, GnuPG signer có thể ngăn pinentry hỏi trực tiếp. Nếu gpg-agent chưa có passphrase cached, build có thể lỗi `Inappropriate ioctl for device` hoặc `No pinentry`, tùy hệ thống. Cách xử lý đúng là chuẩn bị agent hoặc inject passphrase an toàn theo supported plugin mechanism; không đơn giản tắt authentication/protection.

Với `signer=bc`, cần bảo đảm private key ở TSK format và environment variables mà plugin đọc. Chỉ truyền name `MAVEN_GPG_KEY` không làm key material tự xuất hiện.

## 15. Thứ tự plugin: sources/Javadoc/shade trước ký

Một project có thể attach:

- Maven Source Plugin: `-sources.jar`.
- Maven Javadoc Plugin: `-javadoc.jar`.
- Maven Shade Plugin: `-all.jar` (nếu configured attached).
- Maven Assembly Plugin: `-bin.zip` hoặc `-jar-with-dependencies.jar`.
- Maven GPG Plugin: detached signatures cho những artifact đã có.

Một workflow phù hợp:

~~~text
src/main/java
      │
      ▼
compile + test
      │
      ▼
package
  ├── main jar
  ├── source plugin attaches sources jar
  ├── javadoc plugin attaches javadoc jar
  ├── shade/assembly plugin attaches distro variants (nếu dùng)
      │
      ▼
verify
  └── gpg:sign → ký POM, main, attached artifacts
      │
      ▼
install / deploy
~~~

### Cẩn thận với plugin chạy ở phase muộn

Nếu một plugin attach `-all.jar` ở `install` (sau `verify`), GPG Plugin đã chạy xong nên không tự ký artifact đó. Sửa bằng cách đưa artifact generation/attach về phase trước signing hoặc thiết kế execution order phù hợp và xác minh file list.

Không thêm một goal `gpg:sign` thủ công ngay trước `mvn package` rồi nghĩ nó sẽ ký các source/Javadoc chưa sinh.

### GPG plugin không ký arbitrary files trong `target`

Một report `target/report.txt` hoặc `target/custom.jar` chưa attach không tự được GPG Plugin ký. Nếu repository yêu cầu ký những file custom, phải xác định **cách attach/classifier/extension hợp lệ**, hoặc dùng quy trình signing tường minh phù hợp với loại artifact.

### Source/Javadoc không phải GPG responsibility

GPG Plugin không tạo Javadoc hoặc sources. Nó chỉ ký những artifact đã có. Nếu Maven Central yêu cầu sources/Javadocs, phải cấu hình các plugin tạo chúng, rồi ký đúng từng file.

## 16. Chữ ký trong Maven Central và repository nội bộ

### Maven Central

Theo Sonatype Central documentation, publication artifacts cần OpenPGP signatures `.asc`, và thường yêu cầu project POM, main artifact, sources và Javadoc JAR theo checklist metadata hiện hành. Người phát hành cần quản lý public key/fingerprint để consumers có thể kiểm tra. <https://central.sonatype.org/publish/requirements/gpg/>

**Quan trọng:** có chữ ký hợp lệ **không đủ** để publish lên Central. Còn có metadata requirements, source/Javadoc artifacts, namespace verification, checksums, license, publication API/repository rules và yêu cầu khác.

Khi sử dụng **Central Publisher Portal**, cơ chế upload hiện đại có thể dựa vào `central-publishing-maven-plugin` hoặc bundle workflows theo tài liệu Sonatype. **Không chỉ thêm `distributionManagement` trỏ một OSSRH URL cũ rồi mặc định mọi tài khoản Central mới sẽ upload được**. Hãy kiểm tra phương thức publication được Central hỗ trợ tại thời điểm phát hành: <https://central.sonatype.org/publish/publish-portal-maven/>.

### Repository doanh nghiệp

Một repository manager nội bộ có thể:

- Bắt buộc chữ ký cho mọi release.
- Chỉ yêu cầu checksums hoặc không kiểm tra PGP khi upload.
- Chấp nhận key fingerprints do đội security duyệt.
- Dùng signing key per team hoặc per release pipeline.
- Cấm overwrite release version.
- Quét SBOM/vulnerabilities và bắt staging approval trước promotion.

Dù kho nội bộ không bắt buộc PGP, một team vẫn có thể chọn ký để cung cấp verification độc lập. Nhưng **repository upload PASS không tự chứng minh signatures/trust policy đã đạt**; phải kiểm tra trên file xuất bản.

### Không nhầm chữ ký với repository credential

- **GPG private key** ký artifact bytes.
- **Repository token** cho phép upload.
- **Public key** cho phép verify.
- Một tài khoản có quyền upload không tự chứng minh đó là owner của signing key.
- Một artifact có signature tốt không tự chứng minh nó được publish tới đúng repository.

Hai điều kiện ký và publish phải được kiểm tra riêng.

## 17. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `gpg:sign` không xuất hiện trong log. | Profile `release-signing` chưa active hoặc execution không bind. | Dùng `-Prelease-signing`, xem effective POM và lifecycle log. |
| Build `package` thành công nhưng không có `.asc`. | Signing ở `verify`, chưa chạy tới phase đó. | Chạy `verify` hoặc `deploy` với signing profile. |
| `gpg: not found`. | CI image thiếu GnuPG executable/PATH. | Cài supported GnuPG hoặc cân nhắc `bc` signer với key format phù hợp. |
| `No secret key`. | Chưa import private key, sai `GNUPGHOME` hoặc `keyname`. | Kiểm tra `gpg --list-secret-keys` trong đúng environment. |
| `No pinentry`/`Inappropriate ioctl`. | Batch mode thiếu passphrase/agent cache. | Dùng secret env injection hoặc chuẩn bị gpg-agent, không tắt signing. |
| Plugin báo dùng passphrase không an toàn. | `bestPractices=true` gặp `gpg.passphrase`/legacy config. | Chuyển sang gpg-agent hoặc `MAVEN_GPG_PASSPHRASE`. |
| Maven build success nhưng deploy thiếu `.asc`. | GPG chưa attach signature, deploy skip hoặc artifacts tạo sau ký. | So plugin log, package/verify order và repo files. |
| Có `jar.asc` nhưng không có `pom.asc`. | Sign goal/chế độ deploy sai hoặc thiếu POM handling. | Kiểm tra effective POM, GPG logs và repository layout. |
| Có main signature, thiếu sources/Javadoc signatures. | Plugins chưa attach JARs trước `verify` hoặc không active. | Bind source/javadoc goals ở `package`, xác minh attached files. |
| `gpg --verify` báo `No public key`. | Consumer chưa import đúng public key. | Lấy key từ kênh tin cậy, kiểm fingerprint. |
| `gpg --verify` báo `BAD signature`. | File bytes đã thay hoặc signature không khớp file/key. | Lấy lại đúng cặp file, checksum, provenance; không bypass. |
| `Good signature` nhưng warning untrusted key. | Public key chưa có xác nhận trust. | Xác minh fingerprint qua kênh độc lập; không auto trust key lạ. |
| Chữ ký hợp lệ nhưng security scan fail. | Signing không kiểm tra vulnerabilities/license. | Giữ security/quality gates độc lập. |
| CI dùng đúng key nhưng không ký được ở Windows. | GPG executable/PATH/pinentry/file permissions khác. | Kiểm tra GPG 2.x config, user profile và secret handling. |
| Plugin GPG `bc` không dùng được `~/.gnupg`. | BC signer không đọc GnuPG keyring như mode gpg. | Cấp key TSK qua `keyFilePath`/`MAVEN_GPG_KEY`. |
| Ký nhầm private key của người khác. | Nhiều secret keys, thiếu `keyname`/fingerprint selection. | Dùng identity/fingerprint rõ và kiểm signature signer. |
| Artifacts ký đúng nhưng Central từ chối. | Thiếu metadata/source/javadoc, namespace hoặc bundle policy. | Đối chiếu requirements và Central Portal publisher. |
| `mvn deploy` fail 401/403. | Token publish sai/quyền thiếu, không liên quan GPG. | Kiểm tra settings server ID, repository URL và privileges. |
| HTTP 409/release đã tồn tại. | Repository không cho ghi đè release coordinate. | Bump version mới, không cố overwrite artifacts đã ký. |
| `gpg.skip=true` khiến release không có signature. | Skip property/profile bị bật. | Bảo vệ CI profile, xác minh .asc thực tế. |
| `deployAtEnd` vẫn có partial publication. | Không phải atomic transaction cho mọi repository uploads. | Dùng staging/promotion nếu yêu cầu nhất quán. |
| Public key bị hết hạn/thu hồi. | Key lifecycle chưa quản lý/rotate. | Xem expiration/revocation, thiết lập key rotation và phát hành thông báo. |
| Chữ ký vỡ dù Java class không đổi. | ZIP bytes/metadata thay sau khi ký. | Ký artifacts cuối cùng; không repackage sau signing. |

### Thứ tự debug có hiệu quả

1. Xác nhận signing profile active và GPG execution **đã chạy**.
2. Xác nhận GnuPG/key material/agent/passphrase cho đúng signer.
3. Đọc error cụ thể; không in secrets khi debug.
4. Kiểm tra main/POM/attached files được tạo **trước verify**.
5. Kiểm tra chữ ký ở build directory và ở deployment repository.
6. Import public key đáng tin, so fingerprint rồi `gpg --verify` từng cặp.
7. Chạy consumer từ environment khác nếu muốn chứng minh artifact availability.
8. Ghi rõ trạng thái build, signing, deployment, verification là **bốn kết luận độc lập**.

## 18. Những quyết định thiết kế phát hành quan trọng

### Ký ở workstation hay CI?

- **Workstation:** phù hợp khi release thủ công, gpg-agent/pinentry và hardware-backed key; tăng tương tác người ký.
- **CI:** phù hợp release tự động nhưng cần bảo vệ secrets, chống PR untrusted, audit/provenance và phân quyền chặt chẽ.
- **Hardware token/HSM:** có thể giữ private key không xuất ra filesystem, tùy signer/PKCS11/GPG integration; cần kiểm tra plugin/agent/hardware compatibility. Không tự khẳng định Maven GPG Plugin có HSM support trực tiếp cho mọi thiết bị.

### Ký SNAPSHOT hay release?

Không có một chính sách đúng cho mọi repository. Nhiều nhóm chỉ ký releases đã duyệt; nhóm khác ký cả snapshots để theo dõi provenance nội bộ. Maven GPG Plugin không tự suy ra policy đó; cần đặt execution/profile và CI conditions rõ.

Tránh cho pipeline untrusted PR có quyền truy cập release private key. `-Prelease-signing` là lựa chọn cấu hình, **không phải hệ thống phân quyền**: kiểm soát secrets vẫn phải do CI/infra.

### Reproducible builds và chữ ký

Để build tái lập, project có thể cố định plugin versions, inputs và `project.build.outputTimestamp`. Tuy nhiên OpenPGP signature có thể bao gồm metadata như thời gian ký, nên **không được suy luận hai `.asc` sẽ byte-for-byte giống nhau chỉ vì hai JAR giống hệt**. Xác minh signature hợp lệ trên artifact bytes và provenance, thay vì đòi identical signature files trong mọi lần ký.

### Ký nhiều modules

Một reactor có parent `packaging=pom` và các child modules cần ký không nhất thiết chỉ có JARs. Parent POM artifact cũng có thể cần signature. Nếu parent cấu hình GPG Plugin trong `build/plugins` và execution được inherited, kiểm tra effective POM và Reactor Build Order để xác nhận mỗi module có goal ký đúng phase.

Nếu một child module dùng plugin mới để attach archive sau `verify`, chữ ký có thể thiếu. Nếu module tắt signing bằng profile/skip, release có thể không đủ chữ ký cho toàn bộ artifact set. Multi-module QA phải kiểm **từng tọa độ GAV** và cả POM-only modules.

### Signed artifacts không đồng nghĩa signed Git tags

GPG có thể dùng để ký Git commits/tags nhưng đó là một cơ chế áp dụng trên Git objects. Maven GPG Plugin ký JAR/POM artifacts, không tự tạo và ký Git tag. Muốn release được truy vết tốt, có thể kết hợp:

- Signed Git release tag, nếu chính sách yêu cầu.
- CI provenance/attestation.
- Signed Maven artifacts (OpenPGP `.asc`).
- Repository immutability và publishing approvals.

Cần định nghĩa bằng chứng nào thuộc bước nào, tránh một chữ “signed” chung chung.

## 19. Checklist trước khi publish một bản đã ký

**Nội dung artifact:**

- [ ] Main artifact/POM đúng GAV, version, metadata và packaging.
- [ ] Unit/integration/security/license checks có kết quả thích hợp.
- [ ] Source/Javadoc JARs và custom attached artifacts đã tạo trước signing.
- [ ] Có đủ `.asc` cho từng artifact mà repository yêu cầu.
- [ ] Không có repackaging/mutation **sau** khi ký.

**Khóa và quyền:**

- [ ] Private key nằm trong secret store/GPG agent/hardware được bảo vệ, không ở Git.
- [ ] Signing key thuộc đúng owner/project; fingerprint đã được đối chiếu.
- [ ] Passphrase không nằm trong POM, CLI arguments hoặc logs.
- [ ] CI chỉ cấp secret cho approved release jobs; PR không tin cậy không có quyền ký.
- [ ] Repository token khác signing key và chỉ có quyền ghi cần thiết.
- [ ] Có policy expiration/revocation/rotation và quy trình ứng phó key compromise.

**Maven/plugin:**

- [ ] `maven-gpg-plugin` được ghim version, execution `sign` ở đúng phase.
- [ ] Release profile active, không bật `gpg.skip`.
- [ ] Source/Javadoc/plugins packaging chạy trước `verify`.
- [ ] `bestPractices=true` được bật và môi trường xử lý secrets tương thích.
- [ ] `signer=gpg` hoặc `bc` được chọn đúng với nguồn private key.
- [ ] Ký POM, main, sources, javadoc và attached variants theo policy.
- [ ] Không nhầm `mvn package` với `mvn verify`/`mvn deploy`.

**Xác minh:**

- [ ] `gpg --verify` trên **files trong published repository** có exit code 0.
- [ ] Public key fingerprint khớp kênh công bố tin cậy, không chỉ Good signature.
- [ ] Ít nhất một tampering negative test đã được kiểm chứng trong môi trường lab.
- [ ] Consumer độc lập tải đúng GAV và không phải artifact cache cũ.
- [ ] Repository publishing requirements/immutability/staging đã được kiểm.
- [ ] Release run ID, commit, key fingerprint và artifact checksum được ghi lại.

## 20. Bài tập thực hành và đáp án

### Bài A — phân loại an toàn

Hãy quyết định đúng/sai:

1. `mvn package` luôn tạo `.asc`.
2. Nếu JAR có `sha256`, bạn không cần quan tâm ai đã tạo checksum.
3. `gpg --verify` báo Good signature nghĩa là người ký chắc chắn thuộc công ty bạn.
4. Source JAR được tạo **sau** `verify` có thể không được gpg:sign bao gồm trong lượt đó.
5. `-Dgpg.passphrase=...` trong shell là cách khuyến nghị để lưu release secret.
6. `bestPractices=true` giúp phát hiện những secret-handling practices không an toàn.
7. POM cũng là artifact đáng quan tâm khi ký và publish.
8. `gpg.skip=true` có thể tạo release không có chữ ký nếu không kiểm soát.
9. `jarsigner` thay thế tự động mọi yêu cầu OpenPGP `.asc` của Central.
10. Maven GPG Plugin ký được artifact nhưng không tự publish nếu chưa chạy deployment flow.

**Đáp án:** (1) Sai — cần goal ký đúng phase. (2) Sai — checksum không chứng minh danh tính nhà phát hành nếu nguồn checksum chưa tin cậy. (3) Sai — còn phải kiểm fingerprint/key trust. (4) Đúng. (5) Sai — có thể lộ secrets. (6) Đúng theo cơ chế plugin. (7) Đúng. (8) Đúng. (9) Sai. (10) Đúng.

### Bài B — dựng Java 17 và ký

1. Cài Maven 3.x, JDK 17 và GnuPG 2.x.
2. Tạo **key test**, không dùng production key, và ghi fingerprint.
3. Tạo `producer/pom.xml`, `Greeter.java` và `GreeterTest.java` đúng mục 8.
4. Chạy `mvn -B -ntp clean verify`; xác nhận 2 tests PASS, không yêu cầu ký.
5. Chạy `java -cp target/classes demo.sign.Greeter`; stdout phải là `Hello Maven from signed Maven library`.
6. Chạy `mvn -Prelease-signing clean verify` khi gpg-agent sẵn sàng.
7. Xem main/source/Javadoc JARs và GPG logs; giải thích tại sao `verify` chưa deploy.
8. Chạy `mvn -Prelease-signing clean deploy` vào `file:` repo test.
9. Đếm cặp POM/JAR/sources/Javadoc và `.asc` trong `signed-repo`; dùng `gpg --verify` từng cặp.
10. Import public key vào môi trường verify khác, kiểm fingerprint và test một file bị sửa có BAD signature.

### Bài C — phân tích lỗi CI

CI release gặp:

~~~text
gpg: signing failed: No secret key
~~~

Hãy liệt kê những khả năng và bước kiểm:

- `GNUPGHOME` sai hoặc không được cấp tới job.
- Private key chưa import/không đúng format.
- POM chọn `keyname` không trùng signing-capable key.
- CI dùng `signer=bc` nhưng chỉ chuẩn bị keyring GnuPG.
- Secret không được cấp cho job vì policy của protected branch/tag.
- Có thể do filesystem permissions/user identity khác workstation.

**Không khắc phục bằng** hardcode private key vào POM, log secret hoặc tắt ký để đạt BUILD SUCCESS.

### Bài D — kiểm tra file đã xuất bản

Cho repository có:

~~~text
example-2.0.0.pom
example-2.0.0.pom.asc
example-2.0.0.jar
example-2.0.0.jar.asc
example-2.0.0-sources.jar
example-2.0.0-javadoc.jar
example-2.0.0-javadoc.jar.asc
~~~

Nếu repository yêu cầu .asc cho từng artifact, **thiếu** file nào? **Đáp án:** `example-2.0.0-sources.jar.asc`. Không giải quyết bằng cách copy chữ ký của main JAR sang tên sources: nội dung khác sẽ verify FAIL. Phải ký đúng source JAR bytes với signing key hợp lệ và publish chữ ký tương ứng theo quy trình được phép.

### Bài E — đưa vào dự án đa module

Một project có parent POM, `api`, `service` và plugin tạo distribution ZIP. Hãy xác định:

1. Parent POM có cần `.pom.asc` nếu publish theo yêu cầu Central không?
2. Source/Javadoc goals chạy trước hay sau GPG sign?
3. ZIP attached chỉ có ở `target` nhưng chưa attach thì GPG/Deploy Plugin có tự xử lý không?
4. Nếu GPG keys chỉ có ở CI release job, build PR nên xử lý thế nào?
5. Làm sao xác nhận signer identity phù hợp, ngoài dòng Good signature?
6. Nếu repo manager upload thành công 3/4 artifacts rồi fail, có được tuyên bố đã publish trọn vẹn không?
7. Có thể dùng `deployAtEnd` thay transaction/staging không?
8. Vì sao cần so artifact checksum và published POM ngoài kiểm tra chữ ký?

**Định hướng:** profile ký chỉ cho authorized jobs; ký POM/attached artifacts; staging/approval để tránh partial publication; xác minh bytes, signature, fingerprint và metadata.

## 21. Kết luận

**Chữ ký artifact tạo một bằng chứng mật mã cho những bytes đã phát hành theo public key tương ứng.** Trong Maven, cách thường dùng là Maven GPG Plugin ký **POM + main artifact + mọi attached artifacts đã sẵn sàng**, tạo detached `.asc` trước khi install/deploy.

Mô hình cần nhớ:

~~~text
Source + Java tests
       │
       ▼
Maven package
  ├── main.jar
  ├── sources.jar (attached)
  └── javadoc.jar (attached)
       │
       ▼
Maven verify + gpg:sign
  ├── pom.asc
  ├── main.jar.asc
  ├── sources.jar.asc
  └── javadoc.jar.asc
       │
       ▼
Maven deploy / Central publishing workflow
       │
       ▼
Consumer kiểm fingerprint + gpg --verify
~~~

Không nhầm bốn kết luận:

- **Build PASS**: project có thể biên dịch/kiểm thử theo cấu hình.
- **Signing PASS**: những bytes đã ký có signatures hợp lệ với key tương ứng.
- **Deploy PASS**: repository nhận artifacts/signatures theo chính sách.
- **Trusted release PASS**: signer identity, repository source, integrity, metadata và release governance đều đã được xác minh.

Bảo vệ private key và passphrase, tránh hardcode CLI/POM, xác minh fingerprints qua kênh tin cậy và ký **sau khi artifacts cuối cùng được tạo**. Một `Good signature` không cứu được build lỗi, metadata sai hoặc người ký không đáng tin.

## Tài liệu chính thức

- Apache Maven GPG Plugin — giới thiệu, signer và best-practices: https://maven.apache.org/plugins/maven-gpg-plugin/
- Maven GPG Plugin `gpg:sign` (3.2.8) — tham số, signer, bestPractices: https://maven.apache.org/plugins/maven-gpg-plugin/sign-mojo.html
- Maven GPG Plugin — Usage: https://maven.apache.org/plugins/maven-gpg-plugin/usage.html
- Maven GPG Plugin — Deploy signed artifacts: https://maven.apache.org/plugins/maven-gpg-plugin/examples/deploy-signed-artifacts.html
- Maven Source Plugin — Attach Sources: https://maven.apache.org/plugins/maven-source-plugin/usage.html
- Maven Javadoc Plugin — Attach Javadocs: https://maven.apache.org/plugins/maven-javadoc-plugin/usage.html
- Maven Deploy Plugin — `deploy:deploy`: https://maven.apache.org/plugins/maven-deploy-plugin/deploy-mojo.html
- Apache Maven — Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Sonatype Central — PGP Signing Requirement: https://central.sonatype.org/publish/requirements/gpg/
- Sonatype Central — Publication Requirements: https://central.sonatype.org/publish/requirements/
- Sonatype Central — Publisher Portal Maven Plugin: https://central.sonatype.org/publish/publish-portal-maven/
- Sonatype Central — Published Component Immutability: https://central.sonatype.org/publish/requirements/immutability/
- GnuPG — User Manual, keys and verification: https://www.gnupg.org/documentation/manuals/gnupg/
