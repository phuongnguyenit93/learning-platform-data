# Quản lý credential, dữ liệu nhạy cảm và quyền ghi remote cache trong Gradle

## 1. Vì sao remote build cache là một ranh giới bảo mật?

Gradle Build Cache giúp tránh chạy lại các task có cùng **đầu vào đã được khai báo** bằng cách tái sử dụng output từ lần build trước. Khi chỉ lưu cache trên máy lập trình viên, rủi ro chủ yếu nằm ở tài khoản và máy đó. Nhưng **remote build cache** được nhiều máy developer, CI runners hoặc pipelines sử dụng; output của một máy có thể trở thành **đầu vào tin cậy của máy khác**.

Ví dụ: CI đã biên dịch một JAR và đẩy task output lên remote cache. Một developer hoặc CI job khác có cache key phù hợp thì Gradle có thể tải JAR đó về và **không chạy lại task compilation**. Nếu kẻ tấn công có thể ghi nội dung giả vào cache, các build tiêu thụ có nguy cơ sử dụng bytes không được tạo ra bởi source tương ứng. Đó là **cache poisoning**, có thể trở thành một đường chèn mã vào artifacts và chuỗi cung ứng phần mềm.

Một rủi ro khác: task output có thể chứa file cấu hình sinh ra với API key, password, private key, access token, tệp chứng thực hoặc thông tin khách hàng. Nếu output đó được cache và chia sẻ, dữ liệu nhạy cảm có thể rời khỏi runner và xuất hiện trên máy của những consumer khác.

**Ba nguyên tắc trung tâm:**

1. **Credential** để kết nối cache phải đến từ nơi lưu secrets an toàn, không nằm trong Git, build script hoặc command line dễ bị ghi log.
2. **Chỉ build thực sự được tin cậy mới có quyền PUSH** lên remote cache; điều kiện `isPush` trong Gradle chỉ là một lớp kiểm soát phía client, **ACL của server mới là rào chắn bắt buộc**.
3. **Không cache task outputs chứa secrets**, kể cả khi connection dùng HTTPS và cache key được tính từ inputs.

### 1.1. Mô hình luồng cache

```text
                     TRUSTED CI (main/release)
                             |
                  HTTPS + write credential
                             |
                      GET + PUT
                             |
                             v
               REMOTE BUILD CACHE SERVER
                namespace: trusted-builds
                             ^
                             |
                  HTTPS + read credential
                             |
                +------------+-----------+
                |                        |
                v                        v
           Developer                 CI verify
         đọc cache được            job read-only
         KHÔNG có quyền PUT       KHÔNG có quyền PUT


       UNTRUSTED PR / FORK / EXTERNAL RUNNER
                             |
               isolated cache / no cache
        (không chung namespace với trusted cache)
```

Sơ đồ là **một policy đề xuất** chứ không phải khả năng mà Gradle tự áp đặt. Server phải cấu hình phân quyền read/write và namespace; Gradle settings cũng phải giới hạn upload. Với môi trường untrusted, kể cả quyền **READ** vào trusted cache cũng có thể không phù hợp nếu cached outputs tiết lộ mã hoặc artifacts nhạy cảm.

## 2. Phân biệt các lớp cache của Gradle trước khi bàn về secrets

Gradle có nhiều loại cache, giải quyết những vấn đề khác nhau:

| Lớp | Lưu gì? | Phạm vi thường gặp | Vấn đề bảo mật cần nhớ |
| --- | --- | --- | --- |
| **Local Build Cache** | Task outputs/artifact transforms đủ điều kiện | Gradle User Home hoặc directory tùy chỉnh | Có thể giữ file output nhạy cảm trên máy |
| **Remote Build Cache** | Task outputs để chia sẻ giữa builds/máy | Cache server qua HTTP(S) | Poisoning, quyền ghi, quyền đọc, nội dung nhạy cảm |
| **Configuration Cache** | State/task graph từ configuration phase | `.gradle/configuration-cache` | Có thể serialize secrets trong task state; được Gradle mã hóa trên đĩa nhưng vẫn cần ACL |
| **Dependency Cache** | JAR, POM và metadata đã tải | Gradle User Home | Nguồn packages, dependency verification và repository trust |
| **Incremental task state / up-to-date** | Snapshots inputs/outputs để biết task đã chạy đúng | Build-local state | Không phải remote shared artifact cache |
| **Daemon/process memory** | State của Gradle JVM và plugins đang chạy | Runtime Gradle | Secrets trong memory/logs; không đồng nghĩa cache file |

**Remote Build Cache không phải Configuration Cache**: Build Cache giữ outputs của các tasks, còn Configuration Cache giữ kết quả cấu hình để tránh phải cấu hình lại build. Việc bảo vệ một lớp không tự động bảo vệ lớp còn lại.

### 2.1. `UP-TO-DATE` khác `FROM-CACHE`

Khi chạy:

```bash
./gradlew generateGreeting --build-cache --console=plain
```

Gradle có thể báo:

- `SUCCESS` hoặc chỉ tên task: task thực thi action.
- `UP-TO-DATE`: outputs và inputs của workspace hiện tại vẫn khớp theo kiểm tra của Gradle.
- `FROM-CACHE`: task không chạy action, outputs được phục hồi từ Build Cache.
- `NO-SOURCE`, `SKIPPED` hoặc task không cacheable: những trạng thái khác cần đọc theo từng task.

Một task có `UP-TO-DATE` **không chứng minh** remote cache hoạt động. Muốn quan sát `FROM-CACHE`, phải có entry hợp lệ và local output không còn, thường làm bằng test có kiểm soát thay vì xóa toàn bộ Gradle User Home.

### 2.2. Gradle Build Cache cần bật

Tùy cấu hình, cache feature có thể chưa được bật. Dùng một trong hai cách:

```bash
./gradlew build --build-cache
```

hoặc trong `gradle.properties` không chứa secrets:

```properties
org.gradle.caching=true
```

`--no-build-cache` vô hiệu hóa Build Cache cho invocation tương ứng. Có cấu hình `buildCache { remote<...> { ... } }` trong settings **không có nghĩa mọi task đều cacheable** hoặc Gradle luôn được bật Build Cache.

## 3. Cơ chế đọc và ghi remote HTTP build cache

Với HTTP remote Build Cache, Gradle sử dụng endpoint phục vụ những cache entries được định danh bằng **cache key**. Ở mô hình mặc định:

- Khi tìm entry, client gửi **GET** tới một đường dẫn kết thúc bằng cache key.
- Khi muốn lưu entry, client gửi **PUT** cùng cache payload.
- Server chấp nhận/không chấp nhận GET/PUT theo auth, ACL, quota, storage policy và namespace.
- Nếu local cache có entry phù hợp, Gradle thường sử dụng local trước khi thử remote.
- Nếu lấy được remote entry hợp lệ, Gradle có thể lưu nó vào local cache để lần sau truy cập nhanh hơn.

### 3.1. Hai trục điều khiển

| Thuộc tính | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `enabled` / `isEnabled` | Cho phép một cache backend được dùng | Bật cache backend không bảo đảm tất cả task cacheable |
| `push` / `isPush` | Client có thể upload outputs tới backend | **Không thay thế server-side ACL** |
| `url` | Endpoint HTTP(S) của remote cache | Không đặt credential trong URL |
| `credentials` | Xác thực client tới server | HTTP Basic Authentication trong `HttpBuildCache` |
| `isAllowUntrustedServer` | Có thể bỏ kiểm tra certificate trust | **Không bật trong production** |
| `isAllowInsecureProtocol` | Cho phép HTTP không mã hóa ở các version hỗ trợ | **Không bật cho cache chứa artifact thật/secrets** |

Mặc định remote cache thường **không push**. Trong kiến trúc bảo mật tốt, developer và PR CI vẫn pull-only ngay cả khi họ có thể đọc cache an toàn, còn trusted CI có write identity khác.

### 3.2. HTTP status và lỗi server

Một số status liên quan:

- `200` / `2xx` cho GET thành công: server trả cache bytes.
- `404` cho GET: chưa có entry, task có thể thực thi và cân nhắc store theo policy.
- `200` / `201` / `204` cho PUT thành công: backend chấp nhận entry.
- `401`: client chưa xác thực hợp lệ.
- `403`: identity không có quyền phù hợp, ví dụ developer không thể PUSH.
- `413`: entry vượt giới hạn upload của server; Gradle có xử lý riêng cho trường hợp quá lớn.
- `5xx` hoặc timeout: server/network lỗi, có thể khiến remote cache bị bỏ qua/disable trong phần còn lại của build.

Không coi HTTP `404` là một build failure nghiêm trọng: cache miss thông thường xảy ra khi chưa từng có output cho key tương ứng. Ngược lại `403 PUT` ở trusted CI là dấu hiệu ACL hoặc credentials có vấn đề cần điều tra; không nên cấp write permission rộng chỉ để tránh lỗi.

## 4. Thiết kế quyền READ và WRITE theo trust level

Một hệ thống cơ bản nên có **hai credential identities**:

1. **Reader**: có quyền tải cache entries bằng GET; không có quyền PUT, DELETE hoặc admin.
2. **Writer**: chỉ được cấp cho CI jobs đã qua review/approval và đáng tin, có quyền PUT trong namespace được kiểm soát.

Tùy server, có thể cần identity thứ ba là **admin/operator** để quản lý users, namespaces, retention, audit logs; không dùng credential này trong mọi Gradle build.

### 4.1. Ma trận phân quyền tham khảo

| Loại build | Đọc trusted cache | Ghi trusted cache | Lý do |
| --- | --- | --- | --- |
| Developer nội bộ trên máy được kiểm soát | Có thể, nếu outputs không nhạy cảm | **Không** | Tránh cache pollution từ workstation |
| CI kiểm tra pull request nội bộ | Chỉ nếu trust policy cho phép | **Không** | Mã PR có thể thay đổi task implementation/inputs |
| CI cho fork/PR không tin cậy | **Không**, hoặc cache tách biệt | **Không** | Tránh cả poisoning và data exposure |
| Trusted main-branch CI sau review | Có | Có với write token riêng | Nguồn tạo outputs tin cậy |
| Trusted release CI đã phê duyệt | Có | Có theo policy | Có thể tạo canonical cache entries |
| Service account giám sát | Chỉ metadata/metrics nếu cần | Không | Principle of least privilege |
| Cache server administrator | Theo nghiệp vụ vận hành | Theo nghiệp vụ vận hành | Không truyền admin token vào builds |

**Một build không trở nên đáng tin chỉ vì tên environment variable là `CI=true`.** PR CI cũng có thể có `CI=true`; attacker có thể sửa script để set biến môi trường hoặc gửi lệnh HTTP PUT nếu server cấp quyền. Do đó:

- Mặt Gradle: `isPush` mặc định `false`, chỉ bật bởi pipeline đáng tin.
- Mặt CI: chỉ inject **write credential** vào job protected/ref đã được xác thực.
- Mặt server: phân quyền **đúng identity**, policy theo namespace và không tin mù quáng vào client.
- Mặt repository: protected branches, required reviews, trusted runner images và hạn chế quyền của third-party workflows.

### 4.2. Tránh namespace chung giữa builds khác mức độ tin cậy

Nếu PR không tin cậy có thể ghi vào cùng namespace với main/release build, cache poisoning có thể làm trusted build tải output độc hại. Ngay cả khi PR chỉ đọc, cache chứa compiled proprietary code hoặc generated configuration có thể bị exfiltrate.

Các phương án:

- Không cấp remote cache cho untrusted builds.
- Dùng một namespace/server khác cho PR không tin cậy, không cho nó push vào trusted namespace.
- Tách cache cho project confidential và project public.
- Chỉ bật shared remote cache khi đã review những task outputs được phép chia sẻ.

Không sử dụng **cache key prefix hoặc biến branch do client tự đặt** làm cơ chế bảo mật duy nhất; server phải xác thực identity và enforce namespace access.

## 5. Cấu hình Kotlin DSL an toàn cho remote HTTP cache

Remote Build Cache được cấu hình ở **`settings.gradle.kts`** của build. Ví dụ dưới đây đọc endpoint và credentials từ environment được cấp bên ngoài source, yêu cầu HTTPS, và chỉ bật `isPush` khi môi trường được đánh dấu là trusted writer.

**File `settings.gradle.kts`, phương án production-oriented:**

```kotlin
import org.gradle.caching.http.HttpBuildCache

rootProject.name = "cache-secure-example"

val cacheUrl = providers.environmentVariable("GRADLE_CACHE_URL")
val cacheUser = providers.environmentVariable("GRADLE_CACHE_USER")
val cachePassword = providers.environmentVariable("GRADLE_CACHE_PASSWORD")

// Chỉ release/main protected CI mới được cấp biến này.
// Không dùng biến này làm thay thế cho ACL ở cache server.
val allowCachePush = providers.environmentVariable("GRADLE_TRUSTED_CACHE_PUSH")
    .map { it == "true" }
    .getOrElse(false)

buildCache {
    local {
        isEnabled = true
        isPush = true
    }

    if (cacheUrl.isPresent) {
        val endpoint = uri(cacheUrl.get())

        require(endpoint.scheme.equals("https", ignoreCase = true)) {
            "Remote cache endpoint must use HTTPS"
        }
        require(endpoint.userInfo == null) {
            "Do not embed credentials in the cache URL"
        }
        require(cacheUser.isPresent && cachePassword.isPresent) {
            "Remote cache credentials must be provided together"
        }

        remote<HttpBuildCache> {
            url = endpoint
            isEnabled = true
            isPush = allowCachePush

            credentials {
                username = cacheUser.get()
                password = cachePassword.get()
            }
        }
    }
}
```

Điểm chính:

- Nếu `GRADLE_CACHE_URL` không có, build **không cấu hình remote**, nhưng local cache vẫn có thể dùng khi Build Cache được bật.
- `require(HTTPS)` tránh vô tình dùng endpoint HTTP truyền credential dạng có thể bị nghe lén.
- `require(no userInfo)` cấm kiểu URL chứa `user:password@host`.
- Cặp credential phải đầy đủ nếu remote được bật; tránh gửi request không có auth rồi vô tình rơi về public cache.
- `isPush` mặc định `false`, vì `GRADLE_TRUSTED_CACHE_PUSH` vắng mặt.
- Reader account phải **không có quyền PUT** trên server, ngay cả nếu ai đó cố bật `GRADLE_TRUSTED_CACHE_PUSH=true`.
- Writer account chỉ inject vào protected CI job, không truyền cho developer hoặc PR fork.

**Phạm vi bảo mật quan trọng:** Values phải được cung cấp qua CI secret manager hoặc environment bảo mật. Provider API giúp tránh hardcode nhưng vì `HttpBuildCache.credentials` được cấu hình trong settings, values có thể được materialize trong configuration; **không tuyên bố rằng dùng Provider tự động bảo đảm secret không bao giờ vào memory/cache/log**. Phải tiếp tục bảo vệ quyền file và configuration cache theo mục 12.

### 5.1. Cấp biến môi trường ở từng loại build

**Máy developer, read-only (mô tả tên biến; không in giá trị):**

```text
GRADLE_CACHE_URL=https://cache.example.org/gradle/trusted/
GRADLE_CACHE_USER=<reader-account-from-secret-store>
GRADLE_CACHE_PASSWORD=<reader-secret-from-secret-store>
GRADLE_TRUSTED_CACHE_PUSH  [không đặt]
```

**Trusted CI protected build:**

```text
GRADLE_CACHE_URL=https://cache.example.org/gradle/trusted/
GRADLE_CACHE_USER=<writer-service-account>
GRADLE_CACHE_PASSWORD=<writer-secret-from-ci-secret-store>
GRADLE_TRUSTED_CACHE_PUSH=true
```

Các dấu ngoặc mô tả **kiểu dữ liệu cần cấp bởi secret store**, không phải credential mẫu dùng được. Domain `example.org` là domain ví dụ, không phải endpoint thật. Không commit hoặc paste password thật vào tài liệu/task output.

**Không ghi cả cặp reader/writer secrets trong cùng file cho tất cả developer** rồi chỉ tin cậy `isPush=false`; nếu đã có write credential, người dùng hoặc attacker có thể gửi HTTP PUT trực tiếp ngoài Gradle.

### 5.2. Lưu ý về `CI` và branch name

Một ví dụ đơn giản trong tài liệu Gradle có thể dùng `System.getenv().containsKey("CI")` để quyết định `isPush`. Đây là **minh họa cấu hình**, không phải cơ chế phân quyền bảo mật đầy đủ: nhiều PR jobs cũng có `CI`. Hãy dùng pipeline protected contexts, có approval, trusted runner, secrets injection và server ACL. Nếu dùng biến branch, cần nguồn branch/ref được CI xác thực và policy không cho untrusted code tự cấp quyền.

## 6. Groovy DSL tương đương

Nếu dự án dùng `settings.gradle`:

```groovy
import org.gradle.caching.http.HttpBuildCache

rootProject.name = 'cache-secure-example'

def cacheUrl = providers.environmentVariable('GRADLE_CACHE_URL')
def cacheUser = providers.environmentVariable('GRADLE_CACHE_USER')
def cachePassword = providers.environmentVariable('GRADLE_CACHE_PASSWORD')

def allowCachePush = providers.environmentVariable('GRADLE_TRUSTED_CACHE_PUSH')
    .map { it == 'true' }
    .getOrElse(false)

buildCache {
    local {
        enabled = true
        push = true
    }

    if (cacheUrl.present) {
        def endpoint = uri(cacheUrl.get())

        assert endpoint.scheme.equalsIgnoreCase('https') :
                'Remote cache endpoint must use HTTPS'
        assert endpoint.userInfo == null :
                'Do not embed credentials in the URL'
        assert cacheUser.present && cachePassword.present :
                'Both credentials must be provided'

        remote(HttpBuildCache) {
            url = endpoint
            enabled = true
            push = allowCachePush

            credentials {
                username = cacheUser.get()
                password = cachePassword.get()
            }
        }
    }
}
```

Đây là **phương án thay thế** cho settings Kotlin DSL, không phải đoạn để chạy song song. Với production, nên dùng kiểm tra `if (...) throw new GradleException(...)` thay vì chỉ dựa trên Groovy `assert` nếu môi trường có thể làm assertions khác đi. Nội dung policy vẫn phải được enforce tại cache server.

### 6.1. Lưu credential trong Gradle User Home

Gradle cho phép cấu hình properties ngoài source, ví dụ ở **`GRADLE_USER_HOME/gradle.properties`** được bảo vệ quyền truy cập:

```properties
cacheUser=the-reader-identity-from-secret-manager
cachePassword=the-reader-secret-from-secret-manager
```

Dấu giá trị trên chỉ mô tả kiểu nội dung, không phải credential sử dụng được. Cần thay bằng secret thật qua **secret manager của người dùng**, bảo vệ file permissions và không đưa file đó vào Git.

Để đọc property thay vì env:

```kotlin
val cacheUser = providers.gradleProperty("cacheUser")
val cachePassword = providers.gradleProperty("cachePassword")
```

Nếu đang dùng settings snippet mục 5, **thay riêng hai dòng khai báo provider**, không tạo trùng hai biến có cùng tên. Cách lưu trong Gradle User Home được Gradle khuyến nghị cho nhiều trường hợp credentials; với CI ephemeral runners, secret environment injection hoặc credential manager thường phù hợp hơn.

### 6.2. Named credentials API cho repository khác cache

Một số Gradle repository declarations hỗ trợ `credentials(PasswordCredentials::class)` và tự tìm properties có prefix theo repository name. Đây là **cơ chế tiện lợi cho dependency/publishing repositories**, nhưng **không nên mặc định** nó áp dụng y hệt cho mọi `HttpBuildCache` declaration.

Với remote HTTP build cache, hãy dùng API `HttpBuildCache.credentials { ... }` theo tài liệu, trừ khi backend/plugin cache cụ thể đưa ra credential abstraction khác.

## 7. HTTPS, certificate trust và bảo vệ đường truyền

`HttpBuildCache` có thể kết nối qua HTTPS. Một triển khai an toàn nên:

- Dùng TLS hợp lệ cho endpoint.
- Giữ trust chain tới certificate authority đáng tin.
- Quản lý certificate rotation và expiry.
- Không ghi password trong URL/query parameters.
- Không đưa cache credentials qua HTTP không mã hóa.
- Hạn chế proxy logging của Authorization headers.
- Bảo vệ endpoint khỏi truy cập ngoài mạng cho phép, nếu phù hợp.
- Bảo đảm server xác minh identity và quyền PUT/GET.

### 7.1. Không bật `isAllowUntrustedServer` để chữa lỗi certificate

Gradle có tùy chọn cho phép bỏ requirement về trusted server certificate. **Không sử dụng tùy chọn này trong production**: kẻ tấn công trên đường truyền có thể giả mạo server và trả cache bytes độc hại hoặc nhận credentials.

Khi gặp lỗi certificate:

1. Kiểm tra hostname trong cache URL và certificate subject/SAN.
2. Kiểm tra certificate chain, intermediate CA, expiry.
3. Cấu hình Java runtime truststore hoặc CA nội bộ đúng cách.
4. Nếu có corporate proxy TLS inspection, kiểm tra policy và certificate đáng tin.
5. Thử GET bằng công cụ phù hợp nhưng không in credential.
6. Chỉ kết nối lại sau khi trust được khôi phục.

Đừng tắt certificate verification như bước đầu tiên.

### 7.2. HTTPS không bảo vệ nội dung khỏi server operator

HTTPS bảo vệ dữ liệu **trên đường truyền**, không làm nội dung cache trở nên bí mật đối với server administrator hoặc người có quyền đọc cache. Nếu output file chứa secret, ngay cả kết nối HTTPS hoàn toàn hợp lệ vẫn có thể làm secret bị phân phối đến nhiều máy.

Do đó phải kết hợp **TLS + access controls + giới hạn dữ liệu cacheable**.

## 8. Tác hại của cache poisoning và vì sao phải cấm untrusted PUSH

Remote cache được thiết kế để tái sử dụng bytes đã tạo từ task inputs. Nếu một người có quyền ghi lên cache server có thể đưa payload không đúng vào entry cho key, các build khác có thể dùng bytes đó mà bỏ qua task execution.

Ví dụ rủi ro:

```text
Untrusted PR modifies task/build logic
        |
        v
Pushes crafted bytes into shared cache namespace
        |
        v
Trusted CI looks up matching cache key
        |
        v
Downloads output without executing compiler task
        |
        v
Package/release may include malicious bytes
```

Đây là mô hình **đe dọa**, không phải một hướng dẫn tấn công. Chính sách phòng ngừa:

1. Writer token chỉ ở trusted main/release CI.
2. Server chặn PUT từ reader credentials.
3. Không chia trusted cache namespace cho untrusted jobs.
4. Không cho fork PR nhận quyền đọc kho bí mật hoặc quyền ghi kho trusted.
5. Ngay cả trusted CI cũng cần verify dependencies, Wrapper, plugins và runner image.
6. Quan sát audit logs, metrics, tỷ lệ PUT, unexpected identities và cache key distribution.
7. Có khả năng disable/quarantine namespace nếu nghi ngờ poisoning.

**Điểm quan trọng từ Gradle security guide:** Build Cache hiện không ký/xác minh mật mã riêng cho từng cache entry theo mô hình end-to-end. Việc tin tưởng cached outputs dựa nhiều vào **server-side write access controls**. Không đánh đồng checksum dùng cho truyền tải/tính toàn vẹn kỹ thuật với xác minh tính hợp lệ của người đã tạo bytes.

### 8.1. Vì sao `isPush=false` chưa đủ?

Một developer có `isPush=false` sẽ không nhờ Gradle client upload entry bình thường, nhưng:

- Nếu họ đã có **write credential** trong máy, họ có thể dùng một HTTP client khác.
- Nếu untrusted PR có write secret, mã PR có thể thực thi arbitrary code và dùng token.
- Nếu server chấp nhận unauthenticated PUT, cờ phía Gradle không ngăn người ngoài upload.
- Nếu một cache namespace cho phép nhiều nhóm không tin cậy ghi, outputs từ nhóm này có thể bị nhóm khác sử dụng.

Vì vậy cần cả **client setting và server enforcement**; bảo vệ write credentials là yêu cầu căn bản.

## 9. Task outputs nào không được đưa vào shared cache?

Không cache các output chứa hoặc có thể làm lộ dữ liệu nhạy cảm, trừ khi có một thiết kế bảo vệ dữ liệu được phê duyệt riêng.

Những output cần đặc biệt chú ý:

- `.env` có access token, passwords hoặc service endpoints có secret.
- Files cấu hình generated chứa private credentials.
- JWT, OAuth refresh/access tokens.
- Private signing keys, keystores, passphrases.
- Files kết nối production database, API access tokens.
- Customer data, PII hoặc business data không được phép chia sẻ.
- Reports có nội dung logs/headers chứa Authorization.
- Binary được đóng gói có secret embedded hoặc proprietary content không được phép phát tán.
- Test snapshots được tạo từ dữ liệu bí mật.
- Output khác có thể được suy luận từ dữ liệu nhạy cảm.

### 9.1. Quy tắc xác định một task có thể cache không

Một task chỉ là ứng viên tốt nếu:

1. Outputs chỉ phụ thuộc vào **đầy đủ declared inputs**.
2. Outputs là deterministic/reproducible cho cùng inputs.
3. Outputs có thể tái sử dụng an toàn ở môi trường khác khi cache key khớp.
4. Inputs/outputs không bị lẫn thời gian, machine-specific state hoặc hidden environment dependencies chưa khai báo.
5. Output không chứa secret hoặc dữ liệu không được chia sẻ.
6. Task type được Gradle/plugin đánh dấu cacheable theo đúng API; custom tasks không tự cacheable.
7. Version/implementation của task được Gradle đưa vào cache key phù hợp.
8. Có tests quan sát `FROM-CACHE` và kiểm tra nội dung được phục hồi.

**Có `@CacheableTask` không bảo đảm task an toàn.** Annotation chỉ opt-in; tác giả vẫn chịu trách nhiệm về inputs, outputs và bảo mật nội dung.

### 9.2. Không coi hash của secret là bảo vệ toàn diện

Nếu đưa giá trị secret trực tiếp vào `@Input` hoặc custom task input để cache key thay đổi, Gradle có thể hash/fingerprint thông tin ấy. Điều này **không giải quyết vấn đề** nếu output vẫn chứa secret và bị upload lên remote cache.

Thêm vào đó, debug logging như `org.gradle.caching.debug=true` có thể làm lộ metadata về inputs/hashes/cache keys, cần hạn chế trong môi trường xử lý bí mật. Không in raw secret trong `println`, stacktrace hoặc build scan.

Khi secret ảnh hưởng output bytes, giải pháp mặc định là **không cache task đó** hoặc thiết kế lại để tách phần dùng secret khỏi phần output cacheable; không chỉ hash secret rồi cho phép shared cache.

### 9.3. Tách task công khai với task cần secret

Mô hình tốt:

```text
Compile/generate deterministic public artifact
         |
         v
Cacheable task (outputs safe to share)
         |
         v
Sign/publish/upload/deploy using secret
         |
         v
Non-cacheable sensitive task, protected CI only
```

Đừng để signing key hoặc deployment token chảy vào JAR/resources hoặc file được cache. Nếu task ký artifacts output chứa signature và có yêu cầu release provenance đặc biệt, nên quản lý riêng pipeline/quy định của công ty, không mặc định shared-cache nó như compile output.

## 10. Bài thực hành an toàn: thử local Build Cache trước khi cấu hình remote

Đây là lab **không có server, không cần credential và không gửi file ra mạng**. Nó minh họa cacheable task chuẩn rồi mới chuyển sang remote policy.

Yêu cầu: JDK 17+, Gradle Wrapper tương thích; nếu chưa có Wrapper, cài Gradle tương thích để sinh `gradle wrapper` một lần.

### 10.1. Cấu trúc thư mục

```text
cache-security-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── src/main/java/demo/ReadGreeting.java
├── local-task-cache/      (Gradle tạo khi chạy; không commit)
└── build/                 (Gradle tạo khi chạy)
```

### 10.2. Local-only settings

**File `settings.gradle.kts`:**

```kotlin
rootProject.name = "cache-security-lab"

buildCache {
    local {
        // Tách cache khỏi build/ để clean không xóa cache.
        directory = File(rootDir, "local-task-cache")
        isEnabled = true
        isPush = true
    }
}
```

Không có `remote` nên chỉ có local cache. `directory` được đặt ngoài `build/` để có thể dùng `clean` xóa output nhưng vẫn giữ entry trong cache.

Dùng `--build-cache` để bật cache cho từng lần chạy. Với dự án khác, có thể bật bằng `org.gradle.caching=true` nhưng lab dùng CLI cho dễ quan sát.

### 10.3. Một custom task đúng input/output và cacheable

**File `build.gradle.kts`:**

```kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.TaskAction

plugins {
    base
}

@CacheableTask
abstract class GenerateGreeting : DefaultTask() {
    @get:Input
    abstract val message: Property<String>

    @get:OutputFile
    abstract val outputFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val file = outputFile.get().asFile
        file.parentFile.mkdirs()
        file.writeText(message.get() + "\n", Charsets.UTF_8)
        logger.lifecycle("Generated greeting file")
    }
}

tasks.register<GenerateGreeting>("generateGreeting") {
    message.set("Hello, Gradle cache!")
    outputFile.set(layout.buildDirectory.file("generated/greeting.txt"))
}
```

Giải thích:

- `@CacheableTask` đánh dấu task type là ứng viên cho output caching.
- `@get:Input` khai báo giá trị ảnh hưởng đến nội dung file.
- `@get:OutputFile` khai báo output file.
- `@TaskAction` tạo file với bytes ổn định cho cùng input.
- `message` không chứa secret, output chỉ chứa một câu công khai.
- `plugins { base }` tạo task `clean` để xóa `build/`.
- Code không tạo credential, không truy cập server và không ghi dữ liệu cá nhân.

`file.writeText(..., Charsets.UTF_8)` tạo dòng kết thúc bằng newline; cùng inputs cho output deterministic. Với task phức tạp có file inputs, cần `@PathSensitive(PathSensitivity.RELATIVE)` hoặc cách normalization phù hợp để cache có thể tái sử dụng giữa workspaces.

### 10.4. Java 17 kiểm tra nội dung output

**File `src/main/java/demo/ReadGreeting.java`:**

```java
package demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ReadGreeting {
    private ReadGreeting() {
    }

    public static void main(String[] args) throws IOException {
        Path path = Path.of("build", "generated", "greeting.txt");
        String content = Files.readString(path, StandardCharsets.UTF_8);
        System.out.print(content);
    }
}
```

Đây là một Java 17 program độc lập dùng `javac`/`java` để đọc output của Gradle task. Nó **không phải Java code của custom Gradle task**: Kotlin DSL đã định nghĩa task riêng phía build.

### 10.5. Chạy thử local cache

Linux/macOS từ thư mục `cache-security-lab`:

```bash
./gradlew generateGreeting --build-cache --console=plain
./gradlew clean generateGreeting --build-cache --console=plain
mkdir -p build/demo-classes
javac -d build/demo-classes src/main/java/demo/ReadGreeting.java
java -cp build/demo-classes demo.ReadGreeting
```

Windows PowerShell:

```powershell
.\gradlew.bat generateGreeting --build-cache --console=plain
.\gradlew.bat clean generateGreeting --build-cache --console=plain
New-Item -ItemType Directory -Force build\demo-classes | Out-Null
javac -d build\demo-classes src\main\java\demo\ReadGreeting.java
java -cp build\demo-classes demo.ReadGreeting
```

Ở lần chạy đầu tiên, task action in:

```text
Generated greeting file
```

Khi entry được lưu vào `local-task-cache` và lần thứ hai chạy với cùng task inputs sau `clean`, `generateGreeting` có thể hiện:

```text
> Task :generateGreeting FROM-CACHE
```

Đây là **dòng trạng thái dự kiến trong điều kiện cache hit**; log Gradle có thể khác chi tiết theo Gradle version hoặc cách task implementation được xác định. Nếu chưa thấy `FROM-CACHE`, dùng `--info` để xem lý do task không cache hit, không kết luận tự động rằng Gradle đã lỗi.

**Stdout chính xác của Java program:**

```text
Hello, Gradle cache!
```

Không thêm bí mật vào `message` để thử cache. Đây là lab local-only; khi chuyển sang remote cần bảo vệ backend và lựa chọn task outputs an toàn trước.

### 10.6. Vì sao lần chạy thứ hai cần `clean`?

Nếu chạy `generateGreeting` hai lần liền mà file output vẫn còn và inputs không đổi, Gradle có thể báo `UP-TO-DATE`. `clean` xóa `build/`, làm output không còn trong workspace; nếu cache entry tồn tại, Gradle có thể phục hồi output và báo `FROM-CACHE`.

Lab đặt local cache **ngoài `build/`** để `clean` không xóa cache entry. Không dùng `rm -rf ~/.gradle` hoặc xóa toàn bộ caches để kiểm tra caching; điều đó làm mất những entries cần thử.

## 11. Chuyển từ local lab sang remote: checklist bắt buộc

**Đây là một pha hạ tầng khác**. Không thể chỉ thêm URL remote vào lab rồi coi tất cả đã an toàn.

Trước khi bật remote:

1. Có cache server qua HTTPS và certificate được trust.
2. Có read-only account và write-only/allowed-write identity được quản lý riêng.
3. Server enforce GET/PUT permissions, không tin `isPush` của client.
4. Trusted main/release CI được xác thực theo policy.
5. PR fork/untrusted builds không có quyền truy cập namespace trusted.
6. Không có tasks cacheable sinh ra secrets/private outputs.
7. Repository/CI quản lý output retention, audit logging và incident response.
8. Performance/failure mode đã thử trên staging.
9. Có đường tắt disable remote/cache khi nghi ngờ poisoning.
10. Không upload credential hay secret dưới dạng debug artifact.

Khi backend chưa sẵn sàng, giữ local lab như mục 10 là lựa chọn đúng; đừng tạo một HTTP server public không authentication chỉ để nhìn thấy `FROM-CACHE`.

### 11.1. Dùng local cache để xác thực cacheability trước

Nếu local Build Cache không `FROM-CACHE` được với task đã khai báo đúng, remote cache chưa giải quyết được gốc rễ. Hãy kiểm tra:

- Task thực sự cacheable chưa?
- Input được khai báo đủ chưa?
- Task output đã được Gradle theo dõi chưa?
- Có inputs biến động như timestamp, absolute path, environment không?
- Task implementation/plugin classpath có thay đổi không?
- Có task bị disable caching hoặc kết quả không deterministic không?

Sau khi local cache test pass, mới thử remote **trong namespace staging**, với read/write permissions và data classification rõ.

## 12. Configuration Cache có liên quan secrets nhưng không phải remote Build Cache

Configuration Cache lưu **task graph và state liên quan** sau configuration phase trong thư mục:

```text
.gradle/configuration-cache/
```

Gradle có cơ chế **mã hóa entries trên đĩa**, với key lưu trong Gradle User Home (hoặc cấu hình `GRADLE_ENCRYPTION_KEY` phù hợp). Tuy vậy:

- Task state có thể chứa credentials/tokens nếu plugin hoặc task giữ chúng trong fields.
- Có quyền đọc cả cache entries và encryption key thì không thể xem đó là vùng bí mật an toàn tuyệt đối.
- Hạn chế quyền truy cập vào `.gradle/configuration-cache` và `GRADLE_USER_HOME`.
- Không đưa configuration-cache directory lên CI artifacts hoặc chia sẻ tùy tiện.
- Tránh giữ secrets trực tiếp trong task instance state.
- Ưu tiên Gradle credential APIs và lazy Providers khi phù hợp.

**Build Cache và Configuration Cache độc lập**: cấm upload remote Build Cache không có nghĩa configuration-cache files trên disk không chứa thông tin cần bảo vệ.

### 12.1. Vì sao Provider chưa phải “phép làm secret biến mất”?

`providers.environmentVariable(...)` và `providers.gradleProperty(...)` hỗ trợ truyền cấu hình/lazy evaluation. Nhưng nếu plugin giải quyết Provider thành một String trong configuration phase hoặc lưu nó vào task state, thông tin nhạy cảm vẫn có thể nằm trong state/caches hoặc memory.

Điều nên làm:

- Không lưu secret raw trong task fields khi có thể.
- Dùng Gradle credentials handling/Providers phù hợp.
- Chỉ resolve secret tại thời điểm cần thiết, không in ra log.
- Bảo vệ Gradle User Home và CI runners.
- Thận trọng với plugin bên thứ ba tự giữ token trong configuration state.

### 12.2. Không dùng Configuration Cache để chia sẻ secrets giữa máy

Encryption key thường gắn với machine/Gradle User Home. `GRADLE_ENCRYPTION_KEY` là cơ chế cho những môi trường chia sẻ hoặc tự quản lý key đặc biệt, **không phải lời khuyên bật đồng loạt** hoặc đưa key vào source.

Không commit key, không đặt key trong untrusted CI logs và không lấy encryption key của developer để chia sẻ công khai. Encryption không thay thế access controls và secret rotation.

## 13. Diagnostic không làm lộ dữ liệu nhạy cảm

Dùng lệnh:

```bash
./gradlew generateGreeting --build-cache --info
```

để xem lý do task được chạy, UP-TO-DATE hoặc FROM-CACHE. Khi debug remote:

- Dùng logs ở mức vừa đủ, không log Authorization headers.
- Giữ HTTP URL không chứa password.
- Không in `System.getenv("GRADLE_CACHE_PASSWORD")`.
- Không paste nguyên `gradle.properties` vào ticket công khai.
- Không gửi cache payload làm attachment nếu chưa xác định nó không chứa secrets.
- Không chia sẻ stacktraces có token/URL query chứa secret mà chưa redact.
- Không bật caching debug trên production build chứa sensitive inputs chỉ để tìm một cache key.

### 13.1. `org.gradle.caching.debug=true` là công cụ cần kiểm soát

Gradle có tùy chọn debug caching để xem input hashes/cache keys:

```properties
org.gradle.caching.debug=true
```

Nó có thể hữu ích khi so hai environments để tìm cache misses, nhưng không nên bật mặc định trong CI public logs. Nó có thể in thông tin mô tả input property names/hashes và cấu trúc build. Khi có secret inputs, tốt nhất **thiết kế lại task để không cache secret-based outputs** thay vì dựa vào việc hash giúp che kín hoàn toàn.

### 13.2. Kiểm tra trạng thái mà không nhìn giá trị secret

Nếu cần kiểm tra cache credential được cấp cho Gradle:

- Kiểm tra server auth/ACL bằng một test access có kiểm soát.
- Xác nhận task hoặc build resolve được khi quyền đọc hợp lệ.
- Với trusted writer, kiểm tra PUT thực trong staging namespace có logging đã redact.
- Không in token trực tiếp.
- Ghi rõ identity **theo role**, không ghi secret.

Nên có dashboard phía server: GET hit/miss, PUT attempt/success/403, auth principal, namespace, payload sizes và retention metrics, với logs chỉ chứa thông tin được phép lưu.

## 14. Mô hình CI: trusted writer, read-only consumers

Một pipeline đề xuất:

```text
Pull Request check
  |
  +-- không nhận remote write token
  +-- đọc cache chỉ khi dữ liệu được phép chia sẻ
  +-- isPush=false
  +-- build/test, không publish remote cache entries
  |
  v
Required tests + code review
  |
  v
Protected main branch CI
  |
  +-- runner được tin cậy
  +-- read/write credential riêng
  +-- GRADLE_TRUSTED_CACHE_PUSH=true
  +-- server ACL cho phép PUT namespace trusted
  +-- build/test và đẩy cacheable safe outputs
  |
  v
Other developers / read-only CI
  |
  +-- GET từ namespace trusted
  +-- không có quyền PUT
```

Nếu nhiều protected pipelines có quyền ghi, cần policy quản lý tất cả writers như một trust group. Một runner bị chiếm quyền có thể poison cache; remote cache phải được xem như một thành phần supply chain cần audit.

### 14.1. “Main branch” không phải check security duy nhất

Một code snippet kiểm tra `GIT_BRANCH=main` trong build script không đáng tin nếu attacker có thể kiểm soát biến đó hoặc sửa build script để bỏ điều kiện. Để cho phép write:

- CI hệ thống phải xác thực ref/approval context.
- Secrets chỉ được inject vào protected jobs.
- Server xác thực write service account.
- Runner image/workflows nên được review/pin.
- Nếu build được kích hoạt từ fork, không dùng credential có write access.

Đừng xem `isPush=true` là giấy chứng nhận source đã được review.

### 14.2. Nếu untrusted CI chỉ đọc trusted cache thì sao?

Cần phân loại nội dung:

- Với public/open-source project và cache entries không nhạy cảm, read-only có thể được cân nhắc.
- Với proprietary code hoặc dữ liệu có thể bị trích xuất từ cache entries, **không cấp GET vào trusted cache** cho fork PR, runner bên ngoài hoặc workloads không đáng tin.
- Có thể dùng cache hoàn toàn riêng cho untrusted runs, hoặc tắt cache ở trust boundary.

Mục tiêu không chỉ ngăn injection mà còn ngăn **data exfiltration**.

## 15. Remote cache server policy và vận hành

Một remote cache backend nên có:

1. **HTTPS** với certificate/hostname hợp lệ.
2. **Authentication** cho GET/PUT theo nhu cầu.
3. **Authorization** phân tách read/write và namespaces.
4. **No anonymous PUT**.
5. **Audit logs** không chứa raw secrets.
6. **Storage encryption at rest** nếu dữ liệu/pháp chế yêu cầu, do backend quản lý.
7. **Retention/eviction** để tránh lưu artifacts vô hạn.
8. **Quota và payload limits** để tránh abuse và chi phí quá lớn.
9. **Backup/incident response** phù hợp với cache có thể tái tạo.
10. **Metrics/alerting** cho PUT từ identity lạ, spikes, error rates.
11. **Network segmentation** cho projects confidential.
12. **Credential rotation** và khả năng revoke writers ngay.

Gradle cung cấp HTTP cache client, nhưng không mặc định tạo mọi ACL hoặc chính sách của backend. Một server không auth mà cho ghi có thể làm vô hiệu phần lớn các guardrails phía Gradle client.

### 15.1. Cách đối xử khi nghi ngờ cache bị poison

Khi nghi ngờ:

- Ngừng writer access ngay tại server.
- Tạm tắt shared cache ở những build quan trọng (ví dụ `--no-build-cache`).
- Cô lập namespace nghi vấn; không cho production builds đọc trong quá trình điều tra.
- Thu thập logs/metrics access theo quy trình incident response, redact secrets.
- Xác minh source commits, CI runner images, dependencies, build inputs.
- Rebuild artifacts quan trọng từ môi trường đáng tin với cache disabled.
- Xem xét rotate writer credentials và purge cache entries bị ảnh hưởng.
- Chỉ bật lại khi đã xác nhận nguyên nhân, policy và tests.

Không chỉ đổi một Gradle property từ `isPush=true` về `false` rồi coi rủi ro đã được loại bỏ, vì entries bị poison có thể vẫn tồn tại và server ACL có thể còn bị lộ.

## 16. Lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `FROM-CACHE` không xuất hiện | Cache chưa bật, task không cacheable hoặc key thay đổi | Dùng `--build-cache --info`, kiểm tra inputs/outputs |
| Task luôn `UP-TO-DATE` | Outputs hiện tại đã tồn tại | Thử `clean` với local cache nằm ngoài `build/` |
| Local cache hit nhưng remote miss | Cache key khác, remote chưa có entry hoặc auth/network | Kiểm tra key và server GET logs |
| `401 Unauthorized` | Sai/thiếu credentials | Kiểm tra secret injection và role, không in token |
| `403 Forbidden` khi PUT từ developer | Server chặn writer không được phép | Đây là policy đúng; sửa client `isPush=false` |
| `403 Forbidden` khi PUT từ trusted CI | Writer role thiếu hoặc token hết hiệu lực | Kiểm tra ACL, identity và protected job |
| `404 Not Found` khi GET | Chưa có entry hoặc namespace sai | Cache miss bình thường; xem task execution |
| TLS certificate error | CA/hostname/truststore sai | Sửa truststore/certificate, không bật untrusted server |
| HTTP URL bị từ chối | Gradle yêu cầu secure transport hoặc policy code | Chuyển sang HTTPS |
| Cache có bản JAR không mong muốn | Untrusted writer/namespace trộn hoặc input tracking sai | Cô lập, rebuild cache-disabled và điều tra |
| Task bị `NO-SOURCE` | Không có input source phù hợp | Kiểm tra source paths/task inputs |
| Task không cacheable | Chưa opt-in, output tracking sai, plugin disable cache | Xem task type/annotations và `--info` |
| Cache bị invalid do timestamp | Task output/input thay đổi không deterministic | Bỏ timestamp, chuẩn hóa generator hoặc không cache |
| Cache hit trên một máy nhưng không trên máy khác | Absolute paths, toolchain/plugin versions hoặc OS khác | Xem path sensitivity và environment-dependent inputs |
| Server trả `413` | Payload quá lớn | Chỉnh task outputs hoặc server quotas theo policy |
| Remote backend timeout | Network/backend lỗi | Điều tra server; build nên có fallback phù hợp |
| Secrets xuất hiện trong remote cache | Sensitive outputs bị đánh dấu cacheable | Cô lập/purge, rotate secrets, sửa task policy |
| Secrets xuất hiện trong configuration cache | Task state giữ token | Xem plugin/task state, quyền thư mục và key |
| PR CI có thể PUSH | Writer token bị cấp sai hoặc server ACL quá rộng | Thu hồi token, chỉnh protected jobs và ACL |
| Cache URL chứa user:password | Cấu hình rò rỉ qua logs/process | Chuyển sang credentials API/secret store |
| `isPush=false` nhưng server còn chấp nhận PUT | Server ACL không enforce | Sửa server policy; cờ client chưa đủ |
| Maven dependency cache bị nhầm với Build Cache | Hai cơ chế cache khác nhau | Xem đúng task/cache loại nào |
| Configuration Cache mã hóa mà vẫn rò token | ACL key/cache directory yếu | Bảo vệ User Home và serializable task fields |
| Cache enabled nhưng output file không có | Task/action lỗi hoặc output chưa được khai báo | Xem task action/`@OutputFile`/build log |
| Cache đẩy file config production | Task output chứa sensitive fields | Không cache task đó và xử lý incident |
| Performance không cải thiện | Ít tasks cacheable, chi phí GET/PUT lớn | Đo cache hit rate, task costs và server latency |

### 16.1. Chẩn đoán theo thứ tự

1. Xác định đang nói về **Build Cache, Configuration Cache hay Dependency Cache**.
2. Xác nhận `--build-cache` hoặc `org.gradle.caching=true`.
3. Kiểm tra task đã opt-in và khai báo inputs/outputs đúng.
4. Xem `UP-TO-DATE`, `FROM-CACHE` và `--info`.
5. Chạy lab local-only để phân biệt task cacheability với lỗi server.
6. Kiểm tra remote endpoint HTTPS, certificate, URL path/namespace.
7. Kiểm tra reader/writer identity và GET/PUT ACL trên server.
8. Kiểm tra CI trust level, secret injection và policy `isPush`.
9. Xem server logs đã redact, không in credentials.
10. Nếu nghi ngờ poisoning/leak, disable/quarantine cache và xử lý theo quy trình security.

## 17. Những sai lầm cần tránh

**Sai lầm 1 — “Gradle đã dùng HTTPS nên mọi output có thể được cache.”** HTTPS không thay đổi loại dữ liệu lưu trong payload. Secret output vẫn nguy hiểm.

**Sai lầm 2 — “Có `isPush=false` là server an toàn.”** Không; server phải xác thực và chặn PUT đối với reader identities.

**Sai lầm 3 — “Mọi CI job đều đáng tin.”** Không; PR fork và untrusted code cũng có thể chạy trong CI.

**Sai lầm 4 — “Cache key có hash nên không thể poison cache.”** Không; quyền ghi backend và payload integrity mới là rủi ro trọng tâm.

**Sai lầm 5 — “Task chứa token thì khai báo token làm `@Input` là đủ.”** Không; output chứa token vẫn có thể bị cache và chia sẻ.

**Sai lầm 6 — “Configuration Cache và Build Cache là một.”** Không; chúng lưu các loại state khác nhau.

**Sai lầm 7 — “Xóa caches của developer là bước đầu tiên để debug.”** Không; sẽ làm mất dữ liệu cần kiểm tra và không sửa ACL/credentials.

**Sai lầm 8 — “Dùng `isAllowUntrustedServer=true` là sửa TLS lỗi.”** Nó làm giảm security; nên sửa CA/truststore.

**Sai lầm 9 — “Có quyền đọc cache không có rủi ro.”** Nếu outputs chứa private code hoặc dữ liệu, read access có thể gây rò rỉ.

**Sai lầm 10 — “Chỉ cần server read/write role trong tên tài khoản.”** ACL phải được enforce thật theo HTTP methods/namespaces.

**Sai lầm 11 — “Gradle cache entry được ký và verify end-to-end.”** Không nên giả định như vậy; Gradle hiện dựa vào trust của remote cache writer.

**Sai lầm 12 — “Toolchain/Gradle version nào cũng cho cùng cache key.”** Task implementation, plugin classpath và những inputs khác có thể làm key khác.

## 18. Checklist review pull request thay đổi remote cache

Trước khi merge cấu hình remote Build Cache, hãy trả lời:

1. Endpoint có dùng HTTPS và certificate trust hợp lệ không?
2. URL có chứa credentials trong user info/query không?
3. Credentials đến từ secret store hoặc file user-level được bảo vệ không?
4. App/repo source có chứa token hoặc password hardcode không?
5. Remote cache `isPush` mặc định là `false` không?
6. Writer token chỉ cấp cho protected CI jobs không?
7. Server có từ chối PUT từ developer/PR identities không?
8. Trusted/untrusted builds có cùng namespace không?
9. Untrusted builds có thể GET confidential output không?
10. Có cacheable task nào sinh file có secret không?
11. Task inputs có đầy đủ và output deterministic không?
12. Có task custom thiếu `@CacheableTask` hoặc cố cache task không phù hợp không?
13. Có test local `FROM-CACHE` đã qua không?
14. Có test staging remote GET và trusted PUT riêng không?
15. Server access logs có redact auth headers/token không?
16. Có retention, quota, incident handling và revoke plan không?
17. Configuration Cache có thể serialize sensitive task state không?
18. Gradle User Home/cache directory có quyền truy cập hợp lý không?
19. Có tài liệu phân biệt developer reader account với CI writer account không?
20. Có cách tắt cache nhanh trong sự cố không?
21. Có thử clean trusted rebuild khi remote cache bị disable không?
22. Security team có phê duyệt chia sẻ loại artifacts này không?

## 19. Bài tập thực hành

**Bài tập A — phân biệt cache.** Mô tả Build Cache, Configuration Cache và Dependency Cache. Vì sao configuration cache encryption không chứng minh remote Build Cache an toàn?

**Bài tập B — chạy local cache.** Tạo `cache-security-lab` ở mục 10 và chạy hai lệnh Gradle theo thứ tự. Quan sát lần đầu task thực thi, lần sau có thể `FROM-CACHE`.

**Bài tập C — kiểm tra output bằng Java.** Biên dịch và chạy `demo.ReadGreeting` bằng Java 17, xác nhận stdout `Hello, Gradle cache!` sau khi task output được tạo/phục hồi.

**Bài tập D — input thay đổi.** Đổi `message` từ `Hello, Gradle cache!` thành `Hello, local cache!` rồi chạy. Vì sao cache key phải khác và output không được dùng sai?

**Bài tập E — phân biệt `UP-TO-DATE`.** Chạy `generateGreeting` liên tiếp mà không clean, so sánh status với lần chạy có clean. Giải thích điều kiện để thấy `FROM-CACHE`.

**Bài tập F — ranh giới secrets.** Một task tạo `build/generated/production.env` chứa token. Hãy phân tích vì sao nó không nên là cacheable task; thiết kế lại để tạo output không nhạy cảm hoặc tách task dùng secret khỏi phần cacheable.

**Bài tập G — credential sources.** Phân biệt `GRADLE_CACHE_USER`/`GRADLE_CACHE_PASSWORD` qua CI secrets với values hardcode trong settings. Nêu rủi ro của CLI arguments.

**Bài tập H — đọc/ghi.** Thiết kế hai server accounts, reader chỉ GET và trusted writer có PUT. Tại sao `isPush=false` không đủ nếu server vẫn chấp nhận PUT bằng reader token?

**Bài tập I — PR fork.** Một PR từ fork không được tin cậy cần chạy tests. Nên cấp quyền remote cache nào nếu cache chứa private outputs? Giải thích.

**Bài tập J — TLS.** Giả sử endpoint có certificate không được trust. Sửa truststore/certificate thế nào theo nguyên tắc bảo mật, thay vì bật `isAllowUntrustedServer`?

**Bài tập K — debugging.** Dùng `--build-cache --info` để tìm cache miss trong lab không có secrets. Nêu vì sao không bật `org.gradle.caching.debug=true` bừa bãi trong job xử lý credentials.

**Bài tập L — cache poisoning.** Mô tả ở mức phòng thủ chuỗi rủi ro nếu untrusted writer có thể ghi fake task output. Đề xuất ba lớp giảm thiểu độc lập.

**Bài tập M — CI policy.** Thiết kế pipeline tách fork PR, internal PR, protected main và release. Xác định quyền GET/PUT, secret injection và namespace cho từng loại.

**Bài tập N — incident response.** Khi phát hiện cache có file chứa token, lập kế hoạch cô lập, xóa cache entry, rotate token, review logs và sửa task.

**Bài tập O — trade-off hiệu năng.** Nếu server xa làm upload mất nhiều thời gian hơn task compilation, nên xem cache hit rate, payload size và server latency trước khi bật push rộng.

**Bài tập P — configuration cache.** Phân tích tác động của plugin giữ token trong task state. Vì sao phải bảo vệ cả `.gradle/configuration-cache` và encryption key?

### Câu hỏi tự kiểm tra

1. Remote Build Cache lưu thứ gì?
2. Cache key được xây từ những yếu tố nào?
3. `FROM-CACHE` khác `UP-TO-DATE` ở điểm nào?
4. Vì sao Build Cache cần được bật để task thực sự dùng cache?
5. HTTP remote cache dùng GET để làm gì?
6. HTTP remote cache dùng PUT để làm gì?
7. `isPush` kiểm soát hành vi phía nào?
8. Vì sao server ACL phải chặn PUT với reader account?
9. Có nên chia trusted cache namespace cho fork PR không?
10. Vì sao GET trusted cache có thể gây rủi ro lộ thông tin?
11. Chỉ HTTPS có ngăn dữ liệu nhạy cảm bị cache không?
12. Vì sao `isAllowUntrustedServer` là lựa chọn nguy hiểm?
13. Có nên đặt credential trong URL hoặc build script không?
14. Gradle Provider giúp gì, và không bảo đảm gì về secrets?
15. Task output chứa private key có cacheable không?
16. Hash của secret trong task input có làm output chứa secret an toàn không?
17. `@CacheableTask` có bảo đảm output không có secret không?
18. Vì sao cacheable task phải deterministic và khai báo đầy đủ inputs?
19. Configuration Cache lưu dữ liệu nào khác Build Cache?
20. Vì sao cần bảo vệ `GRADLE_USER_HOME`?
21. `GRADLE_ENCRYPTION_KEY` có nên commit vào repo không?
22. Một 401/403 từ cache server nên chẩn đoán thế nào?
23. Tại sao `CI=true` không chứng minh job được tin cậy?
24. Vì sao write credentials không nên được cấp cho mọi PR?
25. Nếu nghi poisoning, bước containment quan trọng đầu tiên là gì?
26. Vì sao cache hit không thay thế tests/security review cho release?
27. Có thể dùng `--no-build-cache` để rebuild một artifact tin cậy khi điều tra không?
28. Vì sao cần test local cache trước khi bật remote?
29. Những logs nào có thể làm lộ secrets khi debug cache?
30. Một policy read-only client và server write ACL khác nhau thế nào?

## 20. Tài liệu chính thức

- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html)
- [Gradle — Securing the Build Tool](https://docs.gradle.org/current/userguide/securing_build_tool.html)
- [Gradle — Configuration Cache: Security Considerations](https://docs.gradle.org/current/userguide/configuration_cache.html)
- [Gradle — Configuration Cache Requirements: Credentials and Secrets](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html)
- [Gradle — Build Cache: Common Caching Problems](https://docs.gradle.org/current/userguide/common_caching_problems.html)
- [Gradle — Best Practices for Tasks](https://docs.gradle.org/current/userguide/best_practices_tasks.html)
- [Gradle — Build Cache Debugging](https://docs.gradle.org/current/userguide/build_cache_debugging.html)
- [Gradle — Build Environment Configuration](https://docs.gradle.org/current/userguide/build_environment.html)

**Ghi nhớ:** Remote Build Cache là một **shared task-output store** cần được bảo vệ như thành phần của software supply chain. Dùng HTTPS và credentials ngoài source, nhưng quan trọng hơn là **server-side write ACL, phân tách trusted CI writer khỏi read-only consumers, cô lập untrusted builds** và **không cache outputs chứa secrets**. `isPush=false`, Provider APIs hoặc Configuration Cache encryption đều chỉ giải quyết một phần vấn đề; cần chính sách end-to-end từ task design đến CI, cache server, logs và incident response.