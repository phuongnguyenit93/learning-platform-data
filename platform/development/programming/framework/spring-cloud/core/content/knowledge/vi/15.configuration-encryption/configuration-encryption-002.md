# Vai trò TextEncryptor và thư viện mã hóa cần thiết

Trong hệ thống Spring Cloud, cấu hình thường chứa thông tin cần giữ kín như mật khẩu database, token truy cập, API key hoặc credential của dịch vụ bên ngoài. Những giá trị này có thể được lưu trong repository cấu hình, chuyển qua Config Server và phân phối tới nhiều instance. Chỉ giới hạn quyền đọc repository là chưa đủ: nếu ciphertext bị lộ cùng nơi lưu trữ, người đọc vẫn cần một khóa riêng để giải mã.

Spring Security Crypto cung cấp hợp đồng **`TextEncryptor`** để mã hóa và giải mã chuỗi. Spring Cloud Config sử dụng cơ chế mã hóa này để hỗ trợ endpoint `/encrypt`, `/decrypt` và marker `{cipher}` trong repository cấu hình. Thư viện mã hóa cần có trong classpath, nhưng việc chọn thư viện mới chỉ là một phần của thiết kế; khóa, thuật toán, quyền truy cập và vòng đời xoay khóa mới quyết định hệ thống có an toàn khi vận hành hay không.

Bài học thuộc chương **Mã hóa cấu hình** của module `SPRING_CLOUD_CORE`. Mục tiêu là hiểu vai trò của `TextEncryptor`, phân biệt `spring-security-crypto` với hỗ trợ RSA trong `spring-security-rsa`, biết dependency nào cần cho từng trường hợp và nắm cách Spring Cloud Config dùng encryptor mà không làm lộ khóa trong repository.

## 1. `TextEncryptor` là gì?

`TextEncryptor` là interface trong Spring Security Crypto, thuộc package `org.springframework.security.crypto.encrypt`. Hợp đồng của nó tập trung vào hai thao tác:

- `encrypt(String text)`: biến plaintext thành ciphertext có thể lưu hoặc truyền đi.
- `decrypt(String encryptedText)`: khôi phục plaintext từ ciphertext tương ứng.

Ví dụ cách dùng ở mức API:

```java
import org.springframework.security.crypto.encrypt.TextEncryptor;

public class ConfigValueService {
    private final TextEncryptor encryptor;

    public ConfigValueService(TextEncryptor encryptor) {
        this.encryptor = encryptor;
    }

    public String protect(String plainValue) {
        return encryptor.encrypt(plainValue);
    }

    public String reveal(String cipherValue) {
        return encryptor.decrypt(cipherValue);
    }
}
```

Interface không quy định ứng dụng lấy khóa từ đâu, lưu khóa ở đâu, ai được phép gọi hàm giải mã hoặc ciphertext được lưu trong database/Git như thế nào. Những quyết định đó thuộc về implementation và kiến trúc sử dụng.

### 1.1. TextEncryptor không phải nơi quản lý khóa

`TextEncryptor` nhận plaintext hoặc ciphertext và thực hiện phép biến đổi. Nó không tự cung cấp một kho khóa an toàn, không tự phân quyền người dùng và không tự xoay khóa khi credential thay đổi.

Một ứng dụng có thể tạo `TextEncryptor` từ password/salt, hoặc dùng implementation dựa trên cặp khóa bất đối xứng. Nhưng khóa và tham số cần thiết phải được cung cấp từ nguồn tin cậy, chẳng hạn secret manager, keystore được bảo vệ hoặc biến môi trường được cấp phát an toàn.

### 1.2. Mã hóa khác encoding và hashing

| Khái niệm | Có thể khôi phục giá trị ban đầu? | Mục đích |
| --- | --- | --- |
| Encoding, ví dụ Base64 | Có, không cần secret key | Biểu diễn dữ liệu ở dạng khác |
| Encryption | Có, nếu có khóa phù hợp | Bảo vệ dữ liệu cần giải mã lại |
| Hashing | Không theo thiết kế | So sánh/kiểm tra tính toàn vẹn hoặc lưu verifier |

Config Server cần giải mã password hoặc token để client sử dụng, vì vậy đây là bài toán **mã hóa có thể đảo ngược**, không phải hashing. Với mật khẩu người dùng để xác thực đăng nhập, hãy dùng password hashing qua `PasswordEncoder` với thuật toán phù hợp; không dùng `TextEncryptor` để lưu mật khẩu người dùng theo cách có thể giải mã ngược.

## 2. Thư viện mã hóa trong hệ sinh thái Spring

Hai artifact thường gặp có vai trò khác nhau:

| Artifact | Thành phần chính | Khi nào cần |
| --- | --- | --- |
| `org.springframework.security:spring-security-crypto` | `TextEncryptor`, `Encryptors`, key generator và các primitive crypto được Spring Security hỗ trợ | Khi code trực tiếp dùng hợp đồng `TextEncryptor` hoặc các tiện ích mã hóa của Spring Security Crypto |
| `org.springframework.security:spring-security-rsa` | Hỗ trợ mã hóa/giải mã dựa trên RSA và tích hợp key material bất đối xứng | Khi triển khai cấu hình mã hóa RSA/keystore trong Spring Cloud Config hoặc dùng API RSA tương ứng |

Spring Cloud Config Server có thể cung cấp lớp tích hợp phía trên các thư viện này. Một số dependency có thể được kéo vào bắc cầu tùy phiên bản và starter đang dùng. Hãy kiểm tra runtime dependency tree trước khi thêm dependency thủ công; nếu cần RSA mà artifact chưa có trong classpath, bổ sung theo dependency management tương thích của dự án.

### 2.1. Maven: dependency cho TextEncryptor

Khi một module Java độc lập cần dùng trực tiếp `TextEncryptor`/`Encryptors`, dependency cơ bản là:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-crypto</artifactId>
</dependency>
```

Nếu module đó cũng cần RSA implementation được cung cấp riêng:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-rsa</artifactId>
</dependency>
```

Đoạn thứ hai chỉ cần khi sử dụng hỗ trợ RSA tương ứng. Không thêm cả hai một cách máy móc nếu dependency graph đã cung cấp chúng hoặc ứng dụng chỉ dùng một chế độ mã hóa khác.

### 2.2. Gradle: dependency cho TextEncryptor

```groovy
dependencies {
    implementation "org.springframework.security:spring-security-crypto"
    // Chỉ thêm khi cần RSA implementation và chưa được cung cấp bắc cầu.
    implementation "org.springframework.security:spring-security-rsa"
}
```

Đây là ví dụ khai báo dependency. Phiên bản nên được quản lý thống nhất với Spring Boot/Spring Cloud và dependency management của dự án. Tránh ghim một version RSA/crypto tùy ý khác với bộ thư viện đã được kiểm chứng.

### 2.3. Config Server cần dependency nào?

Ứng dụng Config Server thường khai báo `spring-cloud-config-server` và các dependency quản lý bởi Spring Cloud BOM. Nếu cần tính năng mã hóa/giải mã, kiểm tra tài liệu release train và runtime tree để xác nhận thư viện crypto/RSA phù hợp đã có mặt.

Ví dụ dependency chính của Config Server:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-config-server</artifactId>
</dependency>
```

Dependency này cung cấp server chức năng cấu hình tập trung; nó không phải tên gọi khác của `TextEncryptor`. `spring-security-crypto` cung cấp API crypto, còn `spring-security-rsa` bổ sung hỗ trợ RSA khi cần. Cấu hình cụ thể của Config Server quyết định implementation và key material được sử dụng.

## 3. Tạo TextEncryptor bằng Spring Security Crypto

Spring Security Crypto cung cấp factory `Encryptors` để tạo các implementation `TextEncryptor` theo password và salt. Ví dụ:

```java
import org.springframework.security.crypto.encrypt.Encryptors;
import org.springframework.security.crypto.encrypt.TextEncryptor;
import org.springframework.security.crypto.keygen.KeyGenerators;

public class TextEncryptionExample {
    public static void main(String[] args) {
        String password = obtainPasswordFromSecretStore();
        String salt = KeyGenerators.string().generateKey();

        TextEncryptor encryptor = Encryptors.text(password, salt);

        String encrypted = encryptor.encrypt("db-password");
        String decrypted = encryptor.decrypt(encrypted);

        // Chỉ dùng để minh họa API. Không in plaintext/ciphertext nhạy cảm trong production.
    }

    private static String obtainPasswordFromSecretStore() {
        throw new UnsupportedOperationException("Provide a managed secret source");
    }
}
```

Đây là ví dụ API, không phải cấu hình hoàn chỉnh để triển khai. `password` phải được lấy từ nguồn bí mật; không hard-code hoặc commit vào repository. `salt` cần được quản lý nhất quán với dữ liệu đã mã hóa. Nếu tạo salt mới mỗi lần chạy mà không lưu lại salt tương ứng, dữ liệu cũ có thể không giải mã được.

### 3.1. Password và salt có vai trò khác nhau

- **Password/secret** là bí mật dùng để dẫn xuất khóa mã hóa.
- **Salt** là dữ liệu bổ sung cho quá trình dẫn xuất khóa; nó không phải password và thường không cần giữ bí mật như khóa.
- **Ciphertext** là kết quả mã hóa; có thể lưu trong repository cấu hình nhưng vẫn cần bảo vệ quyền truy cập và tính toàn vẹn.

Không tự chọn salt cố định yếu hoặc tái sử dụng ví dụ trong tài liệu. Hãy tuân theo yêu cầu của API và thư viện đang dùng, sử dụng salt ngẫu nhiên đúng định dạng và lưu lại cùng metadata cần thiết để giải mã. Việc thay salt hoặc password mà không có kế hoạch migration có thể khiến ciphertext cũ không còn giải mã được.

### 3.2. Chọn implementation theo yêu cầu

`Encryptors` cung cấp các factory method với đặc tính bảo mật và định dạng khác nhau. Không nên suy luận rằng mọi `TextEncryptor` đều tương thích với nhau chỉ vì cùng implement một interface.

Khi chọn implementation, cần xác định:

1. Cách dẫn xuất khóa từ secret/password.
2. Thuật toán và mode mã hóa được sử dụng.
3. Cách tạo và lưu IV/nonce/salt.
4. Cách kiểm tra tính toàn vẹn của ciphertext.
5. Định dạng đầu ra và khả năng tương thích khi nâng cấp thư viện.
6. Cách quản lý version/key id để giải mã dữ liệu đã mã hóa trước đó.

Không tự thiết kế thuật toán, ghép primitive hoặc cắt bớt phần xác thực ciphertext để “tăng tương thích”. Dùng implementation được thư viện hỗ trợ và kiểm tra tài liệu bảo mật của phiên bản cụ thể.

## 4. TextEncryptor trong Spring Cloud Config

Spring Cloud Config hỗ trợ mã hóa giá trị cấu hình để repository có thể lưu ciphertext thay cho plaintext. Config Server cung cấp endpoint mã hóa/giải mã và xử lý các giá trị có marker `{cipher}` khi đọc cấu hình.

```mermaid
flowchart TD
    A[Secret plaintext] --> B[POST /encrypt trên Config Server]
    B --> C[TextEncryptor / key configuration]
    C --> D[Ciphertext]
    D --> E[Repository cấu hình với {cipher}]
    E --> F[Config Server đọc property source]
    F --> G[Giải mã bằng encryptor và key phù hợp]
    G --> H[Client nhận cấu hình theo cơ chế server]
```

Sơ đồ mô tả mô hình giải mã phía server thường dùng. Cần cấu hình server có quyền truy cập key để giải mã; nếu kiến trúc chọn giải mã phía client thì phải thiết kế key distribution và client behavior riêng. Không suy ra vị trí giải mã chỉ từ việc ciphertext nằm trong repository.

### 4.1. Endpoint `/encrypt` và `/decrypt`

Config Server cung cấp endpoint HTTP POST để mã hóa hoặc giải mã nội dung. Ví dụ local:

```bash
curl -X POST \
  -H "Content-Type: text/plain" \
  --data-binary "sample-secret" \
  http://localhost:8888/encrypt
```

Endpoint trả về ciphertext. Giá trị đó có thể được đặt trong repository cấu hình với tiền tố `{cipher}`:

```yaml
spring:
  datasource:
    username: app_user
    password: "{cipher}AQB...ciphertext..."
```

Để kiểm tra giải mã trong môi trường test được bảo vệ:

```bash
curl -X POST \
  -H "Content-Type: text/plain" \
  --data-binary "AQB...ciphertext..." \
  http://localhost:8888/decrypt
```

Các giá trị trong ví dụ là placeholder. Không đưa secret thật vào shell history, terminal log hoặc tài liệu. Không gọi endpoint trên server production chỉ để thử nghiệm nếu chưa có quyền và quy trình được phê duyệt.

### 4.2. Marker `{cipher}` có ý nghĩa gì?

`{cipher}` là marker để Config Server nhận diện property value đã được mã hóa. Ví dụ:

```yaml
catalog:
  api-token: "{cipher}AQB..."
```

Khi Config Server đọc property source, nó có thể xử lý marker và giải mã giá trị theo cấu hình encryptor. Marker không phải thuật toán mã hóa, không phải khóa và cũng không làm ciphertext an toàn hơn nếu key bị lộ.

Nếu giá trị không có marker, Config Server thường xem nó như giá trị cấu hình thông thường. Vì vậy, cần quản lý nhất quán việc mã hóa secret và kiểm tra repository để tránh commit plaintext ngoài dự kiến.

### 4.3. Giải mã thất bại

Giải mã có thể thất bại nếu:

- Server không có key hoặc keystore phù hợp.
- Ciphertext được tạo bởi một key/version khác.
- Ciphertext bị cắt, đổi encoding hoặc bị sửa.
- Implementation/algorithm/parameters không tương thích.
- Keystore sai password, alias hoặc không đọc được.

Không nên tiếp tục chạy production với một placeholder không giải mã được nếu property đó là credential bắt buộc. Hãy làm startup fail rõ ràng hoặc đánh dấu instance không sẵn sàng theo chính sách, đồng thời tránh log plaintext hay key trong thông báo lỗi.

## 5. Cấu hình khóa đối xứng cho Config Server

Với mã hóa đối xứng, cùng một secret key được dùng để mã hóa và giải mã. Spring Cloud Config có thể nhận khóa qua thuộc tính `encrypt.key`.

Ví dụ:

```yaml
encrypt:
  key: ${CONFIG_ENCRYPT_KEY}
```

Biến `CONFIG_ENCRYPT_KEY` phải được cấp từ secret manager hoặc cơ chế quản lý bí mật của nền tảng. Không đặt giá trị thật trực tiếp trong `application.yml`, Config Server Git repository hoặc image container.

### 5.1. Ưu điểm và giới hạn

Ưu điểm:

- Cấu hình tương đối đơn giản.
- Một secret có thể dùng với implementation đối xứng tương ứng.
- Phù hợp khi một nhóm server được quản lý như một trust boundary rõ ràng.

Giới hạn:

- Server cần giữ secret có khả năng giải mã.
- Nếu nhiều hệ thống cùng cần giải mã, việc phân phối secret cần được kiểm soát chặt.
- Khi secret bị lộ, các ciphertext có thể bị giải mã nếu attacker có đủ dữ liệu và thuật toán.
- Xoay khóa cần kế hoạch để giải mã dữ liệu đã mã hóa bằng khóa cũ.

### 5.2. Không đặt khóa cạnh ciphertext

Một anti-pattern là lưu cả `encrypt.key` và ciphertext trong cùng repository. Khi đó, người đọc repository có thể có đủ thông tin để giải mã, làm mất mục tiêu tách khóa khỏi dữ liệu.

Nên tách:

| Thành phần | Vị trí phù hợp |
| --- | --- |
| Ciphertext `{cipher}...` | Repository cấu hình có kiểm soát quyền đọc |
| Khóa đối xứng | Secret manager, secret mount hoặc biến môi trường được cấp an toàn |
| Quyền sử dụng khóa | Identity/service account riêng của Config Server |
| Audit | Hệ thống ghi nhận truy cập secret và thao tác mã hóa/giải mã |

## 6. Mã hóa bất đối xứng và keystore RSA

Mã hóa bất đối xứng dùng một cặp public/private key. Public key có thể được phân phối để mã hóa; private key phải được bảo vệ để giải mã. Trong mô hình Spring Cloud Config, cấu hình keystore có thể cung cấp key material RSA cho server.

Ví dụ thuộc tính keystore theo dạng YAML:

```yaml
encrypt:
  key-store:
    location: ${CONFIG_ENCRYPT_KEYSTORE_LOCATION}
    password: ${CONFIG_ENCRYPT_KEYSTORE_PASSWORD}
    alias: config-server-key
    secret: ${CONFIG_ENCRYPT_KEY_PASSWORD}
```

Ý nghĩa tổng quát:

- `location`: vị trí keystore.
- `password`: password mở keystore.
- `alias`: tên entry/key cần sử dụng.
- `secret`: password bảo vệ private key entry nếu keystore yêu cầu.

Tên property canonical dùng kebab-case trong YAML; các thuộc tính tương ứng được ánh xạ theo relaxed binding. Hãy kiểm tra tên property chính xác trong tài liệu Spring Cloud Config của release train đang chạy.

### 6.1. Vai trò của `spring-security-rsa`

`spring-security-rsa` bổ sung hỗ trợ RSA cho hệ sinh thái Spring Security. Khi Config Server dùng RSA/keystore, dependency này cần có trong runtime classpath theo yêu cầu của phiên bản. Nó không thay thế `spring-security-crypto` trong mọi use case và không phải nơi lưu private key.

Private key vẫn phải được bảo vệ bằng keystore password, secret quản lý riêng, file permission và quyền truy cập runtime phù hợp. Không đưa keystore private key vào repository cấu hình hoặc image dùng chung nếu image đó có thể được phân phối rộng.

### 6.2. Khi nào chọn đối xứng, khi nào chọn bất đối xứng?

| Tiêu chí | Đối xứng | Bất đối xứng |
| --- | --- | --- |
| Khóa mã hóa/giải mã | Cùng một secret | Public key và private key khác nhau |
| Phân phối | Phải bảo vệ secret ở mọi nơi cần mã hóa/giải mã | Có thể phân phối public key rộng hơn; private key giữ kín |
| Quản lý | Đơn giản hơn trong môi trường nhỏ, trust boundary rõ | Phù hợp khi cần tách vai trò mã hóa và giải mã |
| Vận hành | Xoay secret phải xử lý ciphertext cũ | Quản lý certificate/keystore, alias và private key |
| Yêu cầu dependency | Crypto implementation phù hợp | Cần RSA support và key store material phù hợp |

Không có lựa chọn tốt nhất cho mọi hệ thống. Quyết định phụ thuộc mô hình phân phối cấu hình, số bên có quyền mã hóa, cách bảo vệ private key và chính sách key rotation.

## 7. TextEncryptor và khả năng tùy biến trong Config Server

Một ứng dụng độc lập có thể inject `TextEncryptor` như dependency thông thường. Tuy nhiên, trong Config Server, việc chọn encryptor có thể cần phụ thuộc môi trường, tenant hoặc key version. Spring Cloud Config cung cấp các abstraction để định vị encryptor phù hợp theo môi trường cấu hình, chẳng hạn `TextEncryptorLocator` trong các dòng hỗ trợ.

Một locator tùy biến có thể giải quyết các yêu cầu như:

- Chọn key/keystore theo tenant hoặc ứng dụng.
- Giải mã ciphertext được tạo bằng nhiều key version trong giai đoạn xoay khóa.
- Lấy key từ secret manager thay vì cấu hình trực tiếp trong file.
- Áp dụng chính sách tách biệt giữa môi trường staging và production.

Không nên tự viết thuật toán mã hóa trong locator. Locator chỉ nên chọn hoặc cung cấp implementation đã được kiểm chứng, còn key material phải đến từ hệ thống quản lý bí mật có phân quyền.

### 7.1. Không tự tạo một bean TextEncryptor rồi giả định Config Server sẽ dùng nó

Việc khai báo một `@Bean TextEncryptor` trong ứng dụng không đảm bảo mọi luồng mã hóa/giải mã của Config Server sẽ sử dụng bean đó. Config Server có cơ chế cấu hình và locator riêng. Nếu cần thay đổi cách chọn encryptor, hãy dùng extension point mà phiên bản Spring Cloud Config hỗ trợ và kiểm thử endpoint `/encrypt`, `/decrypt` cũng như xử lý `{cipher}` end-to-end.

## 8. Dependency và tương thích phiên bản

Mã hóa cấu hình nằm ở giao điểm của Spring Cloud Config, Spring Security Crypto và đôi khi Spring Security RSA. Vì vậy, không nên quản lý các version một cách độc lập.

### 8.1. Dùng Spring Cloud BOM

Với ứng dụng Spring Cloud, import BOM tương thích để quản lý các module Cloud:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Version của `spring-cloud.version` phải tương thích với Spring Boot version theo bảng tương thích chính thức. BOM Cloud không có nghĩa mọi artifact Spring Security đều có cùng version với Cloud release train; hãy kiểm tra dependency management và resolved tree.

### 8.2. Kiểm tra dependency tree

Maven:

```bash
mvn dependency:tree '-Dincludes=org.springframework.security:*'
```

Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-crypto --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-rsa --configuration runtimeClasspath
```

Kiểm tra:

1. `spring-security-crypto` có mặt nếu code dùng `TextEncryptor`/`Encryptors`.
2. `spring-security-rsa` có mặt nếu use case RSA yêu cầu.
3. Không có nhiều version xung đột của Spring Security Crypto/RSA.
4. Spring Cloud Config Server và Spring Boot thuộc tổ hợp được hỗ trợ.
5. Runtime artifact thực sự chứa dependency cần thiết, không chỉ test classpath.

Nếu một starter đã kéo dependency bắc cầu, không cần thêm bản duplicate. Nếu phải thêm trực tiếp để dùng API trong code, giữ version do dependency management điều phối.

## 9. Quy trình mã hóa một secret cho Config Server

Một quy trình minh họa cho repository cấu hình:

1. Xác định Config Server instance và môi trường được phép thực hiện mã hóa.
2. Đảm bảo server đang sử dụng đúng key/keystore.
3. Gửi plaintext tới endpoint `/encrypt` qua kết nối bảo vệ.
4. Nhận ciphertext và xác minh có thể giải mã bằng cùng cấu hình key.
5. Lưu ciphertext trong property value với marker `{cipher}`.
6. Commit ciphertext qua quy trình review repository.
7. Xác minh Config Server giải mã đúng khi phục vụ cấu hình cho client.
8. Kiểm tra log để bảo đảm không có plaintext hoặc key bị ghi ra.

Ví dụ repository:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/catalog
    username: catalog_app
    password: "{cipher}AQB...ciphertext..."
```

URL và username có thể không phải bí mật trong mọi tổ chức, nhưng password cần được bảo vệ. Không mặc định toàn bộ cấu hình đều cần mã hóa; mã hóa có chọn lọc giúp giảm độ phức tạp và tránh nhầm lẫn khi debug.

### 9.1. Kiểm tra ở môi trường không production

Trước khi áp dụng cho production, hãy dùng một Config Server test với key test riêng, mã hóa một giá trị giả, lưu vào repository test và xác minh client nhận được giá trị plaintext đúng. Không dùng lại production key cho local hoặc CI nếu không có yêu cầu rõ ràng và cơ chế bảo vệ tương ứng.

## 10. Quản lý khóa, phân quyền và xoay khóa

Mã hóa chỉ có ý nghĩa khi khóa được bảo vệ độc lập với ciphertext.

### 10.1. Nguyên tắc bảo vệ khóa

- Lưu key/keystore password trong secret manager hoặc cơ chế cấp phát bí mật tương đương.
- Chỉ identity của Config Server hoặc thành phần mã hóa được phép truy cập khóa cần thiết.
- Hạn chế quyền đọc file keystore và quyền truy cập volume mount.
- Không ghi key, plaintext hoặc request body chứa secret vào log, tracing hay audit payload.
- Dùng TLS cho traffic giữa operator, Config Server và các thành phần liên quan.
- Theo dõi truy cập secret và thay đổi cấu hình key.
- Có backup/restore key an toàn và kiểm tra khả năng khôi phục trước khi thay đổi production.

### 10.2. Vì sao xoay khóa cần kế hoạch?

Ciphertext cũ được tạo bằng key/parameters cũ. Nếu Config Server chỉ còn key mới mà không có cách giải mã dữ liệu cũ, các property đã mã hóa có thể không dùng được sau deployment.

Một quy trình rotation có thể gồm:

1. Tạo key mới trong hệ thống quản lý khóa.
2. Cấu hình server hỗ trợ giải mã ciphertext theo key cũ trong giai đoạn chuyển tiếp, nếu implementation/locator được thiết kế để chọn nhiều key.
3. Mã hóa lại secret bằng key mới.
4. Cập nhật repository và xác minh client nhận đúng giá trị.
5. Theo dõi lỗi giải mã và xác nhận không còn ciphertext phụ thuộc key cũ.
6. Thu hồi key cũ sau khi hoàn tất migration và thời gian rollback.

Khả năng giữ nhiều key hoặc định tuyến theo key version phụ thuộc implementation và cấu hình; không giả định một thuộc tính `encrypt.key` đơn giản tự hỗ trợ rotation không gián đoạn. Với yêu cầu nhiều key, thiết kế locator/versioning và kiểm thử migration trước.

### 10.3. Không dùng một key cho mọi môi trường

Staging, production và local nên có key riêng. Nếu staging key bị lộ, tác động không nên lan sang production. Tương tự, quyền truy cập Config Server staging không nên tự động cho phép giải mã secret production.

## 11. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Không tìm thấy `TextEncryptor` khi compile | Thiếu `spring-security-crypto` trong compile classpath | Kiểm tra dependency declaration và dependency tree |
| RSA/keystore không hoạt động | Thiếu RSA support, sai alias hoặc keystore config | Kiểm tra runtime classpath, keystore path, password, alias và private key entry |
| `/encrypt` hoặc `/decrypt` trả 404 | Config Server encryption support không được cấu hình/khởi tạo hoặc endpoint path khác | Kiểm tra server dependency, version và log startup |
| Endpoint trả lỗi khi mã hóa | Không có key/keystore phù hợp hoặc key config sai | Kiểm tra `encrypt.key`/keystore và quyền đọc secret |
| Config Server không giải mã `{cipher}` | Ciphertext được tạo bởi key khác, dữ liệu hỏng hoặc server thiếu key | Đối chiếu key version, ciphertext và server instance |
| Client nhận placeholder/giá trị không dùng được | Decryption failure hoặc cấu hình server/client không đúng | Kiểm tra log server và response property source, không log plaintext |
| Mã hóa được nhưng không giải mã được sau restart | Password/salt/keystore không ổn định hoặc key bị thay | Kiểm tra nguồn cấp phát và tính bền vững key material |
| Môi trường này giải mã được, môi trường khác không | Các môi trường dùng key/algorithm/parameters khác nhau | Kiểm tra key separation và ciphertext provenance |
| Ciphertext cũ hỏng sau rotation | Key cũ đã bị thu hồi quá sớm | Khôi phục key cũ theo quy trình và hoàn tất migration |
| Secret xuất hiện trong log | Logging request/response hoặc debug quá chi tiết | Mask body, giảm log, rotate secret nếu đã lộ |

Trình tự điều tra:

1. Xác định lỗi xảy ra lúc compile, lúc Config Server startup, khi gọi endpoint hay khi client nhận cấu hình.
2. Kiểm tra đúng runtime classpath có crypto/RSA dependency cần thiết.
3. Xác nhận server đang dùng đúng symmetric key hoặc keystore/alias.
4. Kiểm tra ciphertext được tạo bởi môi trường/key version nào.
5. Kiểm tra endpoint và security policy, bao gồm TLS/authentication.
6. Xác nhận `{cipher}` được giữ nguyên trong repository và không bị YAML/template xử lý sai.
7. Kiểm tra log lỗi giải mã và property source trả về mà không tiết lộ plaintext.
8. Nếu có rotation, xác nhận key cũ còn được hỗ trợ trong giai đoạn migration.

## 12. Kiểm thử mã hóa và giải mã

Kiểm thử nên xác nhận tính đối xứng của phép biến đổi với cùng key/configuration, đồng thời xác nhận hệ thống từ chối dữ liệu hỏng hoặc key không phù hợp theo cách an toàn.

| Mục tiêu | Cách kiểm thử | Điều cần xác nhận |
| --- | --- | --- |
| TextEncryptor round trip | Encrypt plaintext rồi decrypt ciphertext với cùng encryptor | Nhận lại đúng plaintext |
| Key mismatch | Decrypt ciphertext bằng key khác | Không trả plaintext sai hoặc bỏ qua lỗi |
| Salt persistence | Restart process và dùng lại salt/key đã lưu | Ciphertext cũ vẫn giải mã được |
| Config Server endpoint | Gọi `/encrypt` rồi `/decrypt` trong môi trường test | Hai endpoint dùng cấu hình encryptor tương thích |
| `{cipher}` integration | Đặt ciphertext trong repository test và yêu cầu cấu hình | Config Server xử lý marker đúng |
| RSA keystore | Dùng keystore test, alias và password test | Mã hóa/giải mã theo cặp key được cấu hình |
| Missing key | Khởi động server không có key bắt buộc | Startup/endpoint báo lỗi rõ theo thiết kế |
| Rotation | Mã hóa bằng key cũ, chuyển sang key mới theo kế hoạch | Ciphertext cũ được giải mã trong giai đoạn chuyển tiếp |
| Secret hygiene | Kiểm tra log/test output | Không xuất hiện plaintext, key hoặc keystore password |

Ví dụ unit test với cùng một encryptor:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.encrypt.Encryptors;
import org.springframework.security.crypto.encrypt.TextEncryptor;

class TextEncryptorTest {
    @Test
    void encryptsAndDecryptsWithSameConfiguration() {
        String password = "test-only-secret-from-fixture";
        String salt = "a1b2c3d4e5f60708";
        TextEncryptor encryptor = Encryptors.text(password, salt);

        String plain = "not-a-real-credential";
        String cipher = encryptor.encrypt(plain);

        assertThat(cipher).isNotEqualTo(plain);
        assertThat(encryptor.decrypt(cipher)).isEqualTo(plain);
    }
}
```

Ví dụ trên dùng fixture test cố định để hai phía có cùng tham số; không sao chép password/salt đó sang production. Kiểm thử integration phải dùng key test riêng và xác nhận Config Server endpoint cũng như marker `{cipher}` hoạt động qua toàn bộ luồng.

## 13. Thực hành: thêm mã hóa cho cấu hình catalog-service

Giả sử Config Server phục vụ cấu hình cho `catalog-service` và repository cần lưu password database dưới dạng ciphertext.

**Bước 1 — Chọn mô hình khóa:** quyết định dùng symmetric key qua `encrypt.key` hoặc RSA keystore theo yêu cầu phân phối và vận hành. Tạo key riêng cho môi trường test.

**Bước 2 — Kiểm tra dependency:** xác nhận Config Server có dependency cần thiết; nếu code trực tiếp dùng `TextEncryptor`, kiểm tra `spring-security-crypto`; nếu dùng RSA, xác nhận `spring-security-rsa` có mặt theo release train.

**Bước 3 — Cấp key an toàn:** cấu hình Config Server đọc key từ secret manager hoặc secret mount. Không lưu key trong Git.

**Bước 4 — Mã hóa giá trị giả:** gửi một password test tới `/encrypt`, nhận ciphertext và thử `/decrypt` trong môi trường được bảo vệ.

**Bước 5 — Lưu ciphertext:**

```yaml
spring:
  datasource:
    username: catalog_app
    password: "{cipher}AQB...test-ciphertext..."
```

**Bước 6 — Kiểm thử client:** khởi động `catalog-service` với đúng application/profile/label, xác nhận cấu hình được giải mã và kết nối database test thành công.

**Bước 7 — Kiểm tra secret hygiene:** rà soát log Config Server, CI output, exception và Actuator để chắc chắn plaintext/key không bị lộ.

**Bước 8 — Chuẩn bị rotation:** ghi nhận key version và quy trình giải mã ciphertext cũ trước khi đưa secret production vào hệ thống.

### Câu hỏi tự kiểm tra

1. `TextEncryptor` cung cấp hai thao tác cốt lõi nào?
2. Vì sao `TextEncryptor` không phải một key management system?
3. `spring-security-crypto` và `spring-security-rsa` có vai trò khác nhau như thế nào?
4. Vì sao không dùng `TextEncryptor` để lưu password đăng nhập của người dùng?
5. Marker `{cipher}` có ý nghĩa gì trong repository cấu hình?
6. Thuộc tính `encrypt.key` dùng cho mô hình khóa nào?
7. Trong RSA keystore configuration, `location`, `password`, `alias` và `secret` có vai trò gì?
8. Vì sao salt/key parameters phải được quản lý ổn định để giải mã ciphertext cũ?
9. Vì sao không lưu khóa cùng repository chứa ciphertext?
10. Xoay khóa cần giữ khả năng giải mã dữ liệu cũ trong giai đoạn nào?

**Gợi ý đáp án:** (1) `encrypt` và `decrypt`; (2) Nó không lưu, phân phối, phân quyền hay xoay khóa; (3) Crypto cung cấp TextEncryptor và API crypto, RSA bổ sung hỗ trợ mã hóa bất đối xứng; (4) Password đăng nhập cần hashing một chiều; (5) Đánh dấu giá trị đã mã hóa để Config Server xử lý; (6) Khóa đối xứng; (7) Định vị keystore, mở keystore, chọn entry và mở private key entry; (8) Nếu tham số khác, ciphertext cũ có thể không giải mã được; (9) Người đọc có thể có cả ciphertext và key; (10) Trong suốt quá trình migration/rollback cho đến khi không còn ciphertext dùng key cũ.

## 14. Những nguyên tắc cần nhớ

- `TextEncryptor` là hợp đồng mã hóa/giải mã chuỗi; nó không tự quản lý khóa, phân quyền hay rotation.
- `spring-security-crypto` cung cấp `TextEncryptor` và các tiện ích crypto; `spring-security-rsa` bổ sung hỗ trợ RSA khi use case yêu cầu.
- Spring Cloud Config dùng encryptor cho endpoint `/encrypt`, `/decrypt` và xử lý property có marker `{cipher}`.
- `encrypt.key` biểu diễn cấu hình khóa đối xứng; RSA keystore cần location, password, alias và private-key secret phù hợp.
- Dependency và version phải được kiểm tra trên runtime classpath và quản lý theo tổ hợp Spring Boot/Spring Cloud được hỗ trợ.
- Ciphertext có thể lưu trong repository; key phải được tách và bảo vệ bằng secret manager/keystore cùng quyền truy cập tối thiểu.
- Không dùng mã hóa thuận nghịch thay cho password hashing; không log plaintext, key hoặc credential.
- Rotation cần giữ khả năng giải mã ciphertext cũ trong giai đoạn chuyển tiếp và có kiểm thử rollback.

Hiểu vai trò `TextEncryptor` và các thư viện mã hóa giúp thiết kế đúng ranh giới giữa API crypto, Config Server và hệ thống quản lý khóa. Khi dependency, key material và quy trình vận hành được xác định rõ, Spring Cloud có thể phân phối cấu hình chứa secret mà vẫn kiểm soát được khả năng giải mã và rủi ro khi thay đổi khóa.
