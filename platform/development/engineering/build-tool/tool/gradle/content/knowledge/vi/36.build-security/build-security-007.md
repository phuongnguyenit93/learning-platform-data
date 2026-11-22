# Phân quyền remote cache và ngăn kết quả build không tin cậy trong Gradle

## 1. Vì sao remote Build Cache là một ranh giới bảo mật?

Gradle Build Cache tăng tốc quá trình build bằng cách lưu output của những task có thể cache. Khi một task mới có **cùng tập input được khai báo**, Gradle có thể lấy output đã lưu thay vì chạy task action. Với **remote Build Cache**, kết quả có thể được dùng lại giữa các máy lập trình viên và CI agents.

Điều này tạo ra một ranh giới tin cậy rất quan trọng: **người có quyền ghi vào remote cache có khả năng quyết định những bytes mà các máy khác sẽ nhận dưới dạng task outputs**. Nếu đầu ra là file `.class`, `.jar`, generated source hoặc test report, các bytes đó có thể ảnh hưởng code được chạy, artifact được kiểm thử hay kết quả kiểm chứng. Một người không đáng tin có quyền `PUT` vào namespace chung có thể gây **cache poisoning**: đưa output sai hoặc độc hại vào nơi build hợp lệ có thể lấy lại.

Theo hướng dẫn bảo mật Gradle 9.9, **Gradle Build Cache không ký hay xác minh chữ ký các cache entries**. Vì vậy, kiểm soát **ai được ghi** vào cache là yếu tố cốt lõi, không thể dựa vào việc “Gradle có cache key nên output chắc chắn đến từ nguồn đáng tin”. Cache key giúp **nhận diện input snapshot/implementation** để tái sử dụng, không chứng minh danh tính của producer hoặc rằng producer là CI đáng tin.

Bài này thuộc nhóm **An toàn build**, chủ đề trực tiếp **“Phân quyền remote cache và ngăn kết quả build không tin cậy”** của **Build Tool Gradle**.

**Nguyên tắc tóm lược:** chỉ CI đã xác thực trên nhánh/workflow đáng tin được ghi cache được các nhóm khác tiêu thụ; developer và PR builds tối đa nên có quyền đọc nếu được phép; untrusted forks/branches không được nhận writer secret; cache phục vụ developer/tests và quy trình tạo **published artifact** cần có ranh giới riêng.

### Bạn sẽ học được

1. Phân biệt local cache, remote cache, up-to-date checks, Configuration Cache và dependency cache.
2. Hiểu cơ chế `GET`/`PUT`, cache key, các trạng thái `UP-TO-DATE`/`FROM-CACHE` và giới hạn tin cậy của chúng.
3. Thiết kế mô hình quyền **reader / trusted writer / administrator**, có namespace tách biệt theo trust domain.
4. Hiểu vì sao `push = false` chỉ là **cài đặt client**, không phải server-side authorization.
5. Cấu hình `HttpBuildCache` bằng Groovy DSL trong `settings.gradle`, HTTPS, HTTP Basic Authentication và secrets từ CI.
6. Ngăn CI từ untrusted pull requests/forks làm bẩn shared cache hoặc đánh cắp credentials.
7. Viết ví dụ Java 17 với custom `@CacheableTask` có inputs/outputs rõ, xác minh local cache trước khi kết nối remote.
8. Lập test matrix kiểm reader `GET` nhưng không `PUT`, trusted writer `PUT`, audit và negative tests.
9. Nhận diện cache poisoning, output không lặp lại, thiếu input, rò dữ liệu nhạy cảm, sai namespace và artifact thiếu provenance.
10. Thiết kế publish/release bằng môi trường sạch, có kiểm tra integrity/provenance thay vì dùng cache như nguồn sự thật.
11. Xử lý sự cố nếu nghi ngờ cache đã bị thao túng: ngăn writes/reads, vô hiệu hóa namespace, rotate credentials và rebuild sạch.

**Phạm vi triển khai:** ví dụ dùng Gradle Groovy DSL, Java 17, Gradle Wrapper và JUnit Jupiter. Cấu hình remote **tùy chọn**: phần build Java chạy được bằng local cache mà không cần deploy một server; để kiểm quyền remote thật cần endpoint HTTPS và ACL do người quản trị cache cấu hình. Những giá trị tên người dùng/URL trong ví dụ chỉ là tên biến và domain mẫu, không phải credential hoặc server có sẵn.

---

## 2. Cơ chế Build Cache: output có thể đi từ đâu tới đâu?

### 2.1. Vòng đời một cacheable task

~~~text
Developer hoặc CI chọn task
         |
         v
Gradle lập task graph
         |
         v
Task inputs + implementation -> cache key
         |
         +--> Có output local và inputs không đổi?
         |       |
         |       +--> UP-TO-DATE: không chạy action
         |
         +--> Local Build Cache có entry?
         |       |
         |       +--> FROM-CACHE: khôi phục output
         |
         +--> Remote Build Cache có entry?
         |       |
         |       +--> GET entry -> khôi phục output
         |                         và thường lưu vào local cache
         |
         +--> Không hit?
                 |
                 v
             Chạy task action
                 |
                 v
           Tạo output files
                 |
                 +--> Ghi local cache nếu được bật/push
                 +--> PUT remote cache nếu được bật/push và server chấp nhận
~~~

Gradle thường tìm cache entry ở **local trước, remote sau**; remote hit có thể được nạp vào local cache. Không phải task nào cũng cacheable. Một `Exec` task có side effect, một task publish, hoặc custom task không khai đúng output không thể được coi là artifact build cache hợp lệ chỉ vì có cờ `--build-cache`.

### 2.2. Phân biệt những “cache” dễ nhầm

| Cơ chế | Tái sử dụng thứ gì? | Điểm bảo mật chính |
| --- | --- | --- |
| **Remote Build Cache** | Task outputs, artifact transform outputs giữa machines | **Ai được ghi/đọc output bytes** |
| Local Build Cache | Task outputs trong một Gradle User Home hoặc directory | Bảo vệ máy/CI runner/Gradle User Home |
| Task up-to-date | Existing outputs theo local task history | Input/output tracking đầy đủ |
| Configuration Cache | Configured task graph và configuration state | Chứa state và có thể có secrets nếu thiết kế sai |
| Dependency cache | Third-party JARs/POMs/metadata tải từ repositories | Repository trust, dependency verification |
| CI job artifact store | Artifacts được upload theo pipeline/job | Job permissions, artifact retention/provenance |
| Maven repository | Published artifacts có group/name/version | Publishing ACL, checksums/signatures |

`--build-cache` bật cơ chế **Build Cache**, không tự bật remote endpoint nếu chưa cấu hình. `--configuration-cache` là tính năng khác; không suy remote cache entries được Gradle ký giống một published JAR.

### 2.3. Bật, tắt và mặc định quyền push

Theo Gradle Build Cache docs:

- `./gradlew build --build-cache` bật Build Cache cho invocation.
- `org.gradle.caching=true` trong `gradle.properties` có thể bật cho các invocations.
- `--no-build-cache` tắt Build Cache cho invocation.
- Local Build Cache được cấu hình mặc định trong Gradle User Home; khi Build Cache hoạt động, local cache mặc định có **push enabled**.
- Remote Build Cache phải khai trong `settings.gradle`/cấu hình init script và mặc định có **`push = false`** nếu chưa được cho phép.

Ví dụ:

~~~bash
./gradlew test --build-cache
./gradlew clean test --build-cache --info
./gradlew clean test --no-build-cache --info
~~~

Một task `FROM-CACHE` đã khôi phục output thay vì chạy action; `UP-TO-DATE` là output hiện có trong workspace được chấp nhận. **Cả hai trạng thái đều không tự chứng minh output được tạo bởi người đáng tin**. Niềm tin vào remote cache phải đến từ server authentication, ACL và quy trình producer.

### 2.4. Protocol của Gradle HTTP remote cache

`HttpBuildCache` hoạt động qua HTTP cache endpoint. Với base URL mẫu:

~~~text
https://cache.example.org/cache/
~~~

Client sử dụng những request đại ý:

~~~text
GET /cache/<cache-key>    -> 200 kèm entry hoặc 404 nếu miss
PUT /cache/<cache-key>    -> 2xx nếu server chấp nhận write
~~~

Đây là mô tả giao thức, **không phải lệnh để tự gửi một cache entry hợp lệ**. URL thực tế, certificate, users, namespace, storage và authorization do nhà vận hành server cung cấp.

Những chi tiết cần hiểu:

- Server phải kiểm tra authn/authz **cho từng request**, đặc biệt `PUT`.
- `403 Forbidden` cho reader cố ghi là một kết quả bảo mật **đúng**, không phải một lỗi cần nới quyền.
- `401 Unauthorized` chỉ ra credentials không hợp lệ/thiếu nếu endpoint yêu cầu.
- `404 Not Found` trên `GET` là cache miss bình thường.
- `413 Payload Too Large` có thể xuất hiện khi server không chấp nhận cache entry quá lớn.
- Cần bảo đảm proxy/redirect không làm lộ credentials hoặc đưa request đến host không đáng tin. Với redirects trên `PUT`, Gradle chỉ giữ phương thức PUT khi status phù hợp như 307/308.

Remote cache là **dịch vụ nhận bytes** chứ không phải Maven repository. Không nhầm quyền `PUT` cache key với `publish` một phiên bản thư viện chính thức.

---

## 3. Mối đe dọa: những ai có thể làm sai kết quả build?

### 3.1. Cache poisoning

Một tác nhân có quyền ghi vào remote cache chung có thể làm cho task input key hợp lệ dẫn đến việc nhận **output bytes khác với output của một trusted clean build**. Tình huống rủi ro gồm:

- Compiled `.class` files không tương ứng source đang review.
- Generated sources được thay đổi để khi build tiếp theo compile thì đưa thêm code.
- JAR/ZIP archives có bytes không mong muốn.
- Test outputs/reports làm người xem hiểu sai tác động của một thay đổi.
- Task output chứa script hoặc config được chạy/đọc ở bước sau.

**Ví dụ nhận thức:** Một `compileJava` task có cache hit, nên Java compiler không chạy trong invocation đó; consumer dùng lại compiled classes từ cache. Nếu cache entry không đáng tin thì “source code đã review” và “class bytes thực sự nhận” có thể không còn tương ứng. Không cần người kiểm code nhìn thấy thay đổi source để output đã bị thay.

Bài này không yêu cầu tạo payload gây hại; mục đích là xây ranh giới ngăn nội dung không tin cậy đi vào shared cache.

### 3.2. Cache key không phải chữ ký số

Cache key thường gắn với task implementation và những declared inputs; chính cơ chế này làm việc tái dùng kết quả nhanh. Nhưng:

- Key **không xác thực ai đã tạo output**.
- Key không tự bảo đảm producer chưa bị xâm nhập.
- Gradle **không ký/xác minh chữ ký cho cache entries** theo hướng dẫn security hiện hành.
- Key không sửa được lỗi một task khai **thiếu input**.
- Key không chứng minh reproducible output nếu task đọc timestamp, network, mutable global state.
- Key không chứng minh binary artifact hợp với source commit đã được duyệt nếu trust boundary bị phá.

Muốn tin kết quả phải đặt câu hỏi: **task implementation và inputs có đúng không, producer có đáng tin không, endpoint có bị thao túng không, và user principal nào được phép viết vào namespace đó?**

### 3.3. Lỗi không ác ý cũng làm “poison” shared cache

Không chỉ attacker. Một developer chạy build trong workspace đang thay file, một script đọc template nhưng quên khai input hoặc dùng Java locale khác có thể sinh output không lặp lại. Nếu máy đó có remote write permission, entry sai có thể lan ra toàn tổ chức.

Theo Gradle use cases, developer machines **không được khuyến nghị push** lên shared remote cache do workspace có thể biến động ngay trong lúc task chạy. CI trusted nên dùng **clean builds** để populate cache cho đến khi đã xác minh hoàn toàn tính đúng đắn của incremental output producers.

### 3.4. Rò dữ liệu qua khả năng đọc cache

Quyền `GET` cũng cần đánh giá. Cache có thể chứa:

- Generated files có business logic nội bộ.
- Compiled classes từ repository private.
- Test fixtures hoặc snapshots vô tình chứa dữ liệu nhạy cảm.
- Filenames/package names và metadata suy ra cấu trúc dự án.
- Artifacts bị ghi nhầm secrets.

Vì vậy “mọi PR chỉ pull-only” **không** có nghĩa mọi fork bên ngoài phải được cấp quyền đọc cache nội bộ. Untrusted forks thường **không nên nhận credentials/remote URL private**. Nếu cần cache riêng cho PR public, dùng namespace và credentials được phép đọc ở phạm vi thông tin public tương ứng.

### 3.5. Credential theft và CI compromise

Gradle build scripts, plugin code và init scripts **không được sandbox**: chúng có thể chạy code với quyền của người gọi Gradle. Một untrusted PR có thể sửa `settings.gradle` hoặc plugin build logic và cố sử dụng/đọc environment nếu CI inject writer secret vào job đó.

Do vậy tách “reader/writer credentials” phải làm ở **CI secret delivery**, không chỉ trong một đoạn `if (branch == 'main')` của source do PR kiểm soát. Nếu pipeline chạy untrusted code trong process có writer credentials, bất kỳ logic nào trong repository đều có thể cố sử dụng credentials đó, dù client config chính thức đặt `push=false`.

---

## 4. Thiết kế trust zones và phân quyền: nguyên tắc nguồn

### 4.1. Các trust domains cần tách

Ít nhất chia:

1. **Trusted protected branch CI** — mã đã review/merge, job được bảo vệ và runners sạch.
2. **Developer local builds** — người dùng có access nội bộ; workspace không phải trusted writer.
3. **Internal pull request CI** — mã chưa merge, có thể chạy trên runners có quyền thấp.
4. **External fork/untrusted PR CI** — mã không đáng tin; không cấp private writer secrets.
5. **Release/publish CI** — tạo artifact phát hành; dùng sạch, có provenance, không coi Build Cache là nguồn tin cậy cuối.
6. **Cache service administration** — thay ACL, rotate credentials, quarantine/retire namespaces.

### 4.2. Ma trận quyền khuyến nghị

| Principal / workflow | Đọc shared **trusted** cache | Ghi shared **trusted** cache | Ghi untrusted riêng | Ghi chú |
| --- | --- | --- | --- | --- |
| Protected `main` CI clean build | Có | **Có, qua writer credential** | Không cần | Publisher chính của cache dùng chung |
| Developer trên máy công ty | Có nếu data classification cho phép | **Không** | Local cache riêng | Không cấp writer token chung |
| Internal PR CI | Có nếu được ủy quyền | **Không** | Có thể dùng namespace riêng | Không chuyển credentials sang job không tin cậy |
| External fork PR CI | Thường **không** nếu cache chứa private data | **Không** | Có thể dùng cache public/ephemeral tách biệt | Không expose private secret |
| Release/publish CI | Tùy policy; **khuyến nghị không dùng cached outputs để phát hành** | Thường không cần | Không | Fresh ephemeral build và verify provenance |
| Cache admin | Theo nhiệm vụ vận hành | Theo ACL quản trị | Có thể | Audit/rotate/retention/quarantine |

**Phân quyền là server-side policy**, không phải một bảng trong tài liệu mà mọi người tự giác tuân. Cần enforce bằng authentication, ACL, network access và CI credential issuance.

### 4.3. Vì sao `push=false` không đủ bảo vệ?

`HttpBuildCache.push = false` cho biết **Gradle client đó** không thực hiện PUT khi task kết thúc. Nhưng:

- Người dùng có thể sửa local build config và đặt `push=true`.
- Untrusted code có thể tự tạo HTTP client khác.
- Một server mà ai cũng có PUT không hề được bảo vệ chỉ nhờ thiện chí của clients.
- Credential có đủ quyền ghi bị lộ sẽ phá hỏng isolation dù source build script có check branch.
- Mỗi plugin hoặc init script đều có thể chạy code bên trong Gradle process.

**Vì thế server phải từ chối PUT của reader identity bằng quyền thực tế.** Tách reader credential và writer credential; server kiểm permission trên mỗi request/namespace.

### 4.4. Tách namespace theo trust boundary

Ví dụ logic về storage paths:

~~~text
/cache/trusted/main/project-a/
/cache/trusted/main/project-b/
/cache/untrusted/pr-sandbox/
/cache/public-oss/
~~~

Đây là **mẫu phân vùng chính sách**, không phải bắt buộc các remote cache products dùng đúng dạng URL này. Yêu cầu bảo mật thực sự là:

- Writer của namespace `untrusted` **không thể ghi** namespace `trusted`.
- Reader public/untrusted không thể `GET` dữ liệu private.
- Nhánh/project khác nhau không được dùng chung writer identity nếu trust model không tương đương.
- Không dùng namespace `trusted` làm nơi nhận cache entries từ fork/branch chưa review.
- Không đưa secret-bearing outputs vào bất kỳ namespace shared nào.

Có thể phân vùng bằng endpoint URL, bucket/prefix, tenant/namespace metadata hoặc ACL của cache product. Đừng chỉ dựa trên naming convention mà không có authorization enforcement.

### 4.5. Least privilege, danh tính riêng và TTL ngắn

Một thiết kế tốt:

- `cache-reader`: `GET/HEAD` theo protocol được service hỗ trợ, **không `PUT`**.
- `cache-writer`: `GET/PUT` trong namespace trusted đã xác định, chỉ cấp cho protected clean CI.
- `cache-admin`: quản trị ACL/retention/quarantine; không đưa vào build job.
- Credentials được rotate, thu hồi và audit; ưu tiên short-lived tokens/service identity nếu backend hỗ trợ.
- Không share một password “god mode” cho developers, PR jobs và protected CI.
- Không dùng một credential để vừa read/write vừa quản trị server.

Với HTTP Basic Authentication mà Gradle hỗ trợ, server vẫn phải map identity thành quyền cụ thể. **HTTP Basic không tự tạo read-only/reader role**; nó chỉ mang credentials và server thực thi policy.

---

## 5. Bảo vệ giao tiếp HTTP: HTTPS, auth và server behavior

### 5.1. HTTPS là yêu cầu, không phải cosmetic

Remote cache có thể vận chuyển compiled code, generated files và credentials. Dùng:

~~~text
https://cache.example.org/cache/
~~~

và **TLS certificate hợp lệ**. Đối với internal CA, cấu hình Java trust store của Gradle runtime để xác thực server. Không coi địa chỉ LAN/VPN là lý do đủ để hạ xuống HTTP.

Không bật:

~~~groovy
allowUntrustedServer = true
~~~

để “chữa nhanh lỗi SSL”. Property này tắt kiểm tra danh tính HTTPS server, mở khả năng máy chủ giả mạo đứng giữa. Không bật `allowInsecureProtocol` cho production cache. Nếu certificate chain sai, sửa certificate/trust store; không bỏ TLS verification.

### 5.2. HttpBuildCache hỗ trợ HTTP Basic credentials

Trong Gradle Groovy DSL, một cấu hình cơ bản có dạng:

~~~groovy
import org.gradle.caching.http.HttpBuildCache

buildCache {
    remote(HttpBuildCache) {
        url = uri('https://cache.example.org/cache/')
        push = false

        credentials {
            username = 'reader-account'
            password = 'not-a-real-secret'
        }
    }
}
~~~

Đây chỉ là **ví dụ hình dạng DSL**, không phải code khuyến nghị để commit: hard-code password vào `settings.gradle` là **sai**. Phần 6 đưa bản có biến môi trường, reader/writer identity và fail-closed; **không dùng password mẫu này để chạy thật**.

Gradle gửi Basic credentials trước để xác thực cache backend. Khi dùng HTTPS hợp lệ, traffic được bảo vệ trên đường truyền; bản thân Basic Authentication không cung cấp quyền đọc/ghi khác nhau nếu server không phân quyền.

### 5.3. HTTP status và negative tests

| Trường hợp | Status/phản ứng server mong đợi |
| --- | --- |
| Reader gửi `GET` với key hợp lệ | `200` và cache bytes nếu tồn tại |
| Reader gửi `GET` key không tồn tại | `404` |
| Reader cố `PUT` | **`403` hoặc `401`**, không ghi storage |
| Trusted writer gửi `PUT` hợp lệ | `2xx`, entry được lưu trong namespace |
| User không credentials truy cập private cache | `401/403` |
| Writer cố PUT namespace không được phân | **`403`** |
| Cache entry quá lớn | Có thể `413` |
| Server TLS cert không đáng tin | Client phải reject, không tắt verification |

**HTTP cache read có thể trả 404/200 tùy key hiện tại**, nên test quyền đọc và test có entry là hai điều khác nhau. Khi kiểm quyền, dùng một **test key/fixture trong namespace lab** do admin cấp; không chèn bytes thử nghiệm vào production cache.

### 5.4. Network failure không được biến thành lỗi đúng/sai giả

Khi remote cache mất kết nối, Gradle có thể retry hoặc disable remote cache trong invocation; build vẫn có thể tự chạy task nếu policy không yêu cầu cache service như dependency bắt buộc. Không coi “cache miss” là lỗ hổng tự động, cũng không coi “hit” là kiểm integrity.

Đối với security-critical build, policy có thể yêu cầu môi trường mới/cấu hình cache bị tắt hoàn toàn hơn là tin output không rõ nguồn. **Availability** và **integrity** là hai mục tiêu khác nhau.

---

## 6. Mẫu `settings.gradle` Groovy DSL an toàn theo nguyên tắc mặc định

File này áp dụng cho một project Gradle sử dụng một remote HTTP Build Cache **khi có endpoint/credentials được cung cấp**; nếu không có endpoint, build chỉ dùng local Build Cache. Cấu hình này có thể chạy cho Java 17 demo ở phần 8 mà không cần tạo cache server giả.

### 6.1. `settings.gradle` hoàn chỉnh

~~~groovy
import org.gradle.api.GradleException
import org.gradle.caching.http.HttpBuildCache

rootProject.name = 'secure-cache-lab'

// Đây là CI policy signal, KHÔNG phải cơ chế authorization cuối cùng.
// Trusted CI mới được cung cấp writer credentials qua secret store.
def remoteCacheUrl =
    providers.environmentVariable('GRADLE_REMOTE_CACHE_URL').orNull

def writeRequested =
    providers.environmentVariable('CACHE_ALLOW_WRITE')
        .orElse('false')
        .get()
        .equalsIgnoreCase('true')

if (writeRequested && (remoteCacheUrl == null || remoteCacheUrl.isBlank())) {
    throw new GradleException(
        'CACHE_ALLOW_WRITE requires GRADLE_REMOTE_CACHE_URL'
    )
}

if (remoteCacheUrl != null && !remoteCacheUrl.isBlank()) {
    // Production URL phải là HTTPS. Bản demo không hạ security.
    if (!remoteCacheUrl.startsWith('https://')) {
        throw new GradleException(
            'Remote Build Cache URL must use HTTPS'
        )
    }

    // CI cung cấp hai danh tính khác nhau. Untrusted builds
    // không bao giờ được nhận writer credentials.
    def readerUser =
        providers.environmentVariable('CACHE_READ_USER').orNull
    def readerPassword =
        providers.environmentVariable('CACHE_READ_PASSWORD').orNull

    def writerUser =
        providers.environmentVariable('CACHE_WRITE_USER').orNull
    def writerPassword =
        providers.environmentVariable('CACHE_WRITE_PASSWORD').orNull

    def cacheLoginName =
        writeRequested ? writerUser : readerUser
    def cacheLoginSecret =
        writeRequested ? writerPassword : readerPassword

    if (!cacheLoginName || !cacheLoginSecret) {
        throw new GradleException(
            'Missing remote cache credentials for requested role'
        )
    }

    buildCache {
        local {
            enabled = true
        }

        remote(HttpBuildCache) {
            url = uri(remoteCacheUrl)
            enabled = true

            // Client-side switch: server vẫn PHẢI enforce ACL.
            push = writeRequested

            credentials {
                username = cacheLoginName
                password = cacheLoginSecret
            }
        }
    }
}
~~~

**Điều kiện chạy của cấu hình này:**

- Nếu không set `GRADLE_REMOTE_CACHE_URL` và không yêu cầu write, project không cấu hình remote cache. `--build-cache` vẫn dùng local cache.
- Nếu có endpoint HTTPS thì phải có reader credentials ở reader mode hoặc writer credentials ở writer mode; thiếu là **fail-closed**.
- Nếu `CACHE_ALLOW_WRITE=true` nhưng không có endpoint, sẽ fail ngay.
- Nếu ở reader mode, `push=false`; ngay cả khi developer sửa file thành true, **server phải từ chối** nếu credential chỉ có quyền đọc.
- Với writer mode, `push=true` và credentials phải do **protected trusted CI** cung cấp, không lấy từ `CI=true` hay branch name do nguồn untrusted quyết định.
- Tên biến môi trường là **hợp đồng ví dụ**; tổ chức có thể dùng Vault/OIDC/service account và đặt tên khác. Backend vẫn quyết định quyền GET/PUT.
- Không có `allowUntrustedServer=true` hoặc `allowInsecureProtocol=true`.
- Build script **không chứa password literal hay token**.

### 6.2. Tại sao code vẫn cần server-side ACL?

Một người có khả năng chỉnh `settings.gradle` có thể sửa `writeRequested` hoặc gọi HTTP client riêng. **Source code check không phải security boundary**. Điều ngăn kẻ không đáng tin ghi cache là:

1. Không cấp writer credential cho untrusted code.
2. Endpoint xác thực danh tính.
3. Server kiểm quyền `PUT` trên namespace.
4. Cache namespace trusted chỉ chấp nhận writer identity của protected CI.
5. Network/secret store/audit hạn chế sử dụng credential ngoài job được cấp.

Nếu PR có thể sửa build script và vẫn được inject writer credentials vào runner, thiết kế CI đã sai dù đoạn `push=false` có mặt.

### 6.3. Tại sao không dùng `System.getenv('CI')` làm bằng chứng tin cậy?

Gradle docs có ví dụ `push = System.getenv().containsKey('CI')` để minh họa **CI producer pattern**, nhưng đó là ví dụ vận hành đơn giản, **không phải security authorization**. Untrusted PR CI cũng có biến `CI=true`; developer có thể đặt biến đó từ shell.

Một hệ thống an toàn chỉ cung cấp writer identity sau khi CI đã xác nhận event/branch/repository/approval và dùng protected environment. `CACHE_ALLOW_WRITE` là tín hiệu cấu hình **của pipeline đã tin cậy**, còn server credentials/ACL mới là giới hạn thực tế.

### 6.4. Cấu hình secrets và Configuration Cache

Secrets đọc ở settings/build configuration có thể được giữ trong configuration state. Tài liệu Gradle ghi Configuration Cache được mã hóa tại rest nhưng không coi đó là lý do để đưa secrets vào code hoặc chia sẻ cache directories.

Nguyên tắc:

- Secrets đến từ **CI secret store** hoặc private user credential store, không commit vào `settings.gradle`/`gradle.properties` trong repo.
- Bảo vệ `GRADLE_USER_HOME` và `.gradle/configuration-cache` theo principal, không chia sẻ chúng giữa jobs có trust level khác nhau.
- Tránh in credentials qua `println`, `--debug` hoặc error messages; code trên chỉ in thông báo thiếu credential, **không in giá trị**.
- Với custom task dùng credentials, ưu tiên Gradle typed credentials API và lazy providers khi có thể, không lưu secret như output/task input.
- Một remote cache authentication credential được Gradle dùng trong configuration là chuyện khác với secret đưa vào `@Input` của task. Tách chúng.
- Nếu dùng CI fork PR, runner phải **không nhận** private reader/writer credentials nếu fork không được phép xem cache data.

### 6.5. Đừng coi một bản cấu hình mẫu là toàn bộ hệ thống

Đoạn `settings.gradle` không thể tự:

- Tạo user/ACL trên cache server.
- Bảo vệ GitHub/GitLab/Jenkins secrets.
- Xác minh protected branch đã review.
- Tạo TLS certificate.
- Rotate credentials khi lộ.
- Phân vùng namespace của cache backend.
- Chứng minh cache entry do trusted producer tạo.

Những phần đó thuộc **cache service + CI/platform security**, cần có test và audit riêng. Code Gradle chỉ là client policy trong ranh giới đã được tổ chức dựng sẵn.

---

## 7. Thiết kế CI đáng tin: ai được inject secret?

### 7.1. Protected main-branch CI writer

Một trusted writer job cần:

1. Chạy trên **protected branch**/workflow được kiểm soát, không chạy code/runner mutable bởi untrusted PR khi credentials tồn tại.
2. Sử dụng **ephemeral runner** hoặc được reset hoàn toàn; không dùng Gradle User Home chứa dữ liệu từ untrusted job.
3. Verify Gradle Wrapper/distribution, dependencies/plugins, build logic được review.
4. Dùng secret store cung cấp writer identity riêng cho cache namespace phù hợp.
5. Chạy **clean build** để populate cache đến khi chứng minh incremental producer đúng.
6. `CACHE_ALLOW_WRITE=true` được CI đặt cùng writer credentials — chỉ khi step thuộc trusted path.
7. Thực hiện test/check và các quality gates trước hoặc trong cùng trusted pipeline, rồi mới cho outputs được tiêu thụ bởi downstream consumers theo chính sách.
8. Ghi audit: job ID, commit SHA, branch/ref, cache namespace, artifact hashes khi phù hợp.
9. Giới hạn service account theo nguyên tắc least privilege, có rotation/expiry.

**Chú ý:** Cache may store outputs trong task executions ngay khi chúng hoàn thành, trước khi toàn job test suite success. Do đó “trusted CI writer” **không tự chứng minh toàn build đã pass**. Nếu policy yêu cầu chỉ results từ commit đã verify hoàn toàn, cần thiết kế **gating hoặc promotion process ở server/pipeline**, không chỉ bật `push=true` trong cùng build đang chạy `test`.

### 7.2. PR CI read-only

Internal PR CI có thể được cấp reader credential nếu cache data được phép lộ trong ranh giới đó:

- `CACHE_ALLOW_WRITE=false` hoặc không set.
- Không inject `CACHE_WRITE_USER/PASSWORD`.
- Reader credential server-side không thể PUT.
- Job chạy với identity và network policy giới hạn.
- Không được upload cache entries sang trusted namespace.
- Không dùng `pull_request_target`/workflow context đặc quyền để checkout và chạy untrusted PR code với secrets.

Nếu cùng runner host được tái sử dụng, phải bảo vệ `~/.gradle/init.d`, distribution/plugin caches và daemons; tách `GRADLE_USER_HOME` cho trust domains.

### 7.3. External fork PR

Nếu cache chứa private bytecode hoặc file metadata, fork PR **không có quyền GET** cache nội bộ. Có thể:

- Chạy không remote cache, dùng local cache ephemeral.
- Dùng public cache riêng nếu artifacts không nhạy cảm và backend ACL bảo đảm isolation.
- Không đưa private cache URL/password vào fork job.
- Không dùng một shared runner/daemon mang writer credentials từ trusted jobs sang fork jobs.

Không đánh đổi bảo mật của trusted cache để giảm vài phút CI của untrusted fork.

### 7.4. Release/publish pipeline

Gradle security best practices khuyến nghị **published artifacts** được tạo từ **fresh, isolated, trusted environment**, không dùng local/incremental/remote cache outputs làm đường tắt tạo release. Có thể chạy các job tests đã tận dụng cache trước đó, nhưng **artifact đem ký/phát hành** phải được tạo theo policy release sạch, có provenance và kiểm artifact đúng source.

Ví dụ ý tưởng cho một release worker **mới**, không tái sử dụng workspace/caches từ PR:

~~~bash
./gradlew clean assemble --no-build-cache
~~~

Đây không phải một lệnh bảo đảm toàn bộ machine hoàn toàn sạch: runner còn phải ephemeral, Gradle Wrapper verified, dependency resolution trusted, no unsafe init scripts và secrets protected. Nếu release job dùng Maven Publish/Signing, thực hiện **sau** clean trusted artifact build và các quality gates.

### 7.5. Bảng quyết định ai có secret

| Dữ kiện CI | Reader secret | Writer secret | Remote namespace |
| --- | --- | --- | --- |
| Protected branch job do CI quản lý | Có | Có nếu job chuyên populate cache | Trusted của repo/nhánh |
| Internal feature branch | Có nếu data được phép | Không | Trusted read-only |
| Internal PR | Có nếu được phép | Không | Read-only hoặc PR sandbox |
| External fork PR | Mặc định không private secret | Không | Off hoặc public/untrusted |
| Deploy/release job | Không nhất thiết | Không dùng để sinh publish artifact | Cache disabled theo release policy |
| Job chạy file workflow PR tự sửa không qua approval | Không private secret | Tuyệt đối không | Sandbox không đặc quyền |

CI implementations khác nhau về cách cấp secrets cho PR và workflow events. Không giả định “GitHub/GitLab luôn an toàn mặc định”; review actual CI permissions, token scope, fork settings và branch protection.

---

## 8. Ví dụ hoàn chỉnh Java 17: cacheable task tạo output ổn định

Bài sẽ dựng một Gradle project **chạy được chỉ với local cache**. Sau đó bạn có thể bật remote HTTPS nếu cache service/ACL đã được tổ chức cung cấp.

Bộ ví dụ này **không tạo/ghi cache entry tùy ý vào một remote server**; nó cho thấy task tốt phải có output dựa trên input rõ ràng. Điều đó là **điều kiện cần** để kết quả một trusted CI push không gây lỗi tính đúng đắn.

### 8.1. Cấu trúc project

~~~text
secure-cache-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── message/
    │   └── name.txt
    ├── main/java/demo/
    │   └── GreetingReader.java
    └── test/java/demo/
        └── GreetingReaderTest.java
~~~

**Gradle Wrapper** phải là bộ file Wrapper hợp lệ do Gradle tạo và verify, không dùng file rỗng. Nếu project chưa có Wrapper, bootstrap từ một Gradle distribution đã được xác thực. Đừng chạy một Wrapper lạ trên repository untrusted rồi kỳ vọng `--build-cache` sẽ bảo vệ hệ thống.

### 8.2. `settings.gradle`

Dùng đúng `settings.gradle` hoàn chỉnh ở mục 6.1. Khi không có `GRADLE_REMOTE_CACHE_URL`, không có remote endpoint và bài thực hành chỉ dùng local cache. Root name là `secure-cache-lab`, nên file này phù hợp với cấu trúc trên.

### 8.3. `build.gradle` hoàn chỉnh

~~~groovy
import java.nio.charset.StandardCharsets
import java.nio.file.Files

import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.0'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

@CacheableTask
abstract class GenerateGreeting extends DefaultTask {
    @InputFile
    @PathSensitive(PathSensitivity.RELATIVE)
    abstract RegularFileProperty getNameFile()

    @Input
    abstract Property<String> getSalutation()

    @OutputFile
    abstract RegularFileProperty getOutputFile()

    @TaskAction
    void generate() {
        def source = nameFile.get().asFile.toPath()
        def destination = outputFile.get().asFile.toPath()

        String name = Files.readString(
            source,
            StandardCharsets.UTF_8
        ).strip()

        if (name.isEmpty()) {
            name = 'bạn'
        }

        String value = salutation.get() + ', ' + name + '!\n'

        Files.createDirectories(destination.parent)
        Files.writeString(
            destination,
            value,
            StandardCharsets.UTF_8
        )
    }
}

tasks.register('generateGreeting', GenerateGreeting) {
    nameFile.set(
        layout.projectDirectory.file('src/message/name.txt')
    )

    salutation.convention('Xin chào')

    outputFile.set(
        layout.buildDirectory.file('generated/greeting.txt')
    )
}
~~~

**Vì sao task này an toàn cho việc thử cache correctness?**

- `@CacheableTask` cho phép Gradle lưu/khôi phục output nếu Build Cache bật.
- `@InputFile` khai file nguồn; `@PathSensitive(RELATIVE)` phù hợp vì relative path/content có ý nghĩa, không phụ thuộc absolute workspace location.
- `@Input Property<String>` là salutation; không đọc biến môi trường hoặc secret ẩn.
- `@OutputFile` là một file output thuộc sở hữu của task.
- `@TaskAction` chỉ đọc declared inputs và ghi declared output; không gọi `project.file` hoặc lấy mutable Project state lúc execution.
- UTF-8 và ký tự `\n` cố định giúp output bytes ổn định across OS đối với nội dung này.
- Không dùng `Random`, time, network hoặc static mutable state.
- Không cache một task có side effect upload/deploy.

### 8.4. `src/message/name.txt`

~~~text
Linh
~~~

### 8.5. `src/main/java/demo/GreetingReader.java`

~~~java
package demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class GreetingReader {
    private GreetingReader() {
    }

    public static String read(Path path) throws IOException {
        return Files.readString(path, StandardCharsets.UTF_8)
            .stripTrailing();
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Expected path to greeting file"
            );
        }

        System.out.println(read(Path.of(args[0])));
    }
}
~~~

Java 17 hỗ trợ `Files.readString`, `Path.of` và `String.stripTrailing`. Reader không phụ thuộc Gradle API và không biết remote cache là gì; nó chỉ đọc artifact file trên filesystem.

### 8.6. `src/test/java/demo/GreetingReaderTest.java`

~~~java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class GreetingReaderTest {
    @TempDir
    Path temporaryDirectory;

    @Test
    void readsUtf8File() throws IOException {
        Path file = temporaryDirectory.resolve("greeting.txt");
        Files.writeString(
            file,
            "Xin chào, Linh!\n",
            StandardCharsets.UTF_8
        );

        assertEquals(
            "Xin chào, Linh!",
            GreetingReader.read(file)
        );
    }

    @Test
    void keepsInternalCharacters() throws IOException {
        Path file = temporaryDirectory.resolve("greeting2.txt");
        Files.writeString(
            file,
            "Xin chào, Mai!\n",
            StandardCharsets.UTF_8
        );

        assertEquals(
            "Xin chào, Mai!",
            GreetingReader.read(file)
        );
    }
}
~~~

Hai JUnit Jupiter tests này kiểm Java reader, **không** chứng minh remote server ACL. Đừng lấy một `test` pass làm bằng chứng production cache đáng tin; phần 10 cần tests riêng cho quyền GET/PUT và namespace.

### 8.7. Chạy local cache, không cần server

Từ root:

~~~bash
./gradlew clean test generateGreeting --build-cache --info
~~~

Expected generated artifact:

~~~text
build/generated/greeting.txt
~~~

Nội dung file (có LF ở cuối):

~~~text
Xin chào, Linh!
~~~

`test` có hai methods pass khi JUnit dependencies đã resolve. Trên Windows PowerShell:

~~~powershell
.\gradlew.bat clean test generateGreeting --build-cache --info
Get-Content build/generated/greeting.txt
~~~

**Không đưa remote URL/credentials**: nếu env `GRADLE_REMOTE_CACHE_URL` vắng mặt, `settings.gradle` chỉ dùng local cache.

### 8.8. Đọc artifact bằng Java 17

Sau khi chạy `classes`/`test` để compile main source:

~~~bash
java -cp build/classes/java/main \
    demo.GreetingReader build/generated/greeting.txt
~~~

Stdout chính xác của Java program:

~~~text
Xin chào, Linh!
~~~

Để kiểm Java source độc lập với Gradle JavaCompile:

~~~bash
mkdir -p manual-classes

javac -encoding UTF-8 \
    -d manual-classes \
    src/main/java/demo/GreetingReader.java

java -cp manual-classes \
    demo.GreetingReader build/generated/greeting.txt
~~~

Kết quả vẫn là:

~~~text
Xin chào, Linh!
~~~

`javac` và `java` **không chạy task `generateGreeting` và không thực hiện cache lookups**. File `build/generated/greeting.txt` phải được tạo sẵn qua Gradle. Đây là phép kiểm Java source và output bytes, không phải phép kiểm server authorization.

### 8.9. Khi nào thấy UP-TO-DATE và FROM-CACHE?

Chạy lần đầu:

~~~bash
./gradlew generateGreeting --build-cache --info
~~~

Có thể thấy task được chạy và output cache entry được lưu.

Chạy lại cùng inputs:

~~~bash
./gradlew generateGreeting --build-cache --info
~~~

Thường nhận `UP-TO-DATE` vì local task history/outputs không đổi.

Chạy:

~~~bash
./gradlew clean generateGreeting --build-cache --info
~~~

nếu local cache đã lưu entry và cache key khớp, có thể nhận `FROM-CACHE`. Nếu entry chưa tồn tại, đã bị eviction hoặc key thay đổi, task sẽ chạy lại.

**Không được hứa luôn `FROM-CACHE`:** đó là expected possibility tùy cache state. Việc output đúng mới là tiêu chí quan trọng.

### 8.10. Đổi input và kiểm không sử dụng output cũ

Sửa `src/message/name.txt` thành:

~~~text
Mai
~~~

Chạy:

~~~bash
./gradlew generateGreeting --build-cache --info
~~~

Expected content:

~~~text
Xin chào, Mai!
~~~

Vì input file content thay đổi, cache key/input snapshot thay đổi. Nếu có cached output cho `Mai`, Gradle có thể khôi phục nó; nếu không thì task action chạy. Trong cả hai trường hợp, output **không được còn “Linh”**.

Tương tự, thay `salutation.convention('Xin chào')` thành `'Chào'` (trên branch học tập) khiến output đổi thành:

~~~text
Chào, Mai!
~~~

Đó là một declared `@Input` scalar, nên output đổi có cơ sở.

### 8.11. Liên hệ thực hành với security policy

Một task khai input đầy đủ và deterministic là **điều kiện cần** để shared cache hoạt động đúng, nhưng **chưa đủ** để chống kẻ có quyền ghi:

- Task correctness: Gradle có thể tính key đúng.
- Producer correctness: trusted build tạo bytes dự kiến.
- Storage integrity: backend không bị thao túng.
- Authorization: reader không thể PUT, trusted writer được phép PUT có audit.
- Distribution: untrusted builds không được phép làm bẩn trusted namespace.

Ngay cả task `GenerateGreeting` rất đơn giản ở lab cũng phải nằm trong server-side ACL nếu định dùng remote cache chung.

---

## 9. Kết nối remote cache sau khi server và ACL đã được chuẩn bị

### 9.1. Chế độ developer read-only

Bộ môi trường khái niệm:

~~~text
GRADLE_REMOTE_CACHE_URL=https://cache.example.org/cache/trusted/
CACHE_READ_USER=<reader-identity>
CACHE_READ_PASSWORD=<injected-secret>
CACHE_ALLOW_WRITE=false
~~~

Hai dòng có dấu `<...>` là **giá trị phải được cung cấp từ credential store**, không phải literal password để commit. Không có `CACHE_WRITE_USER`/`CACHE_WRITE_PASSWORD` trên máy developer. Server phải từ chối mọi `PUT` của reader identity.

Sau khi môi trường đã được CI/developer secure setup:

~~~bash
./gradlew clean generateGreeting --build-cache --info
~~~

Nếu remote chứa entry key phù hợp, Gradle có thể `GET` output và báo `FROM-CACHE`. Nếu không có entry, task chạy và **không PUT** remote vì `push=false`. Local Build Cache vẫn có thể nhận entry.

### 9.2. Chế độ trusted CI writer

Trong protected CI job **được quyền populate remote cache**, secret store inject:

~~~text
GRADLE_REMOTE_CACHE_URL=https://cache.example.org/cache/trusted/
CACHE_ALLOW_WRITE=true
CACHE_WRITE_USER=<writer-identity>
CACHE_WRITE_PASSWORD=<injected-secret>
~~~

Writer identity chỉ có quyền ghi namespace trusted đã chỉ định, không có quyền quản trị toàn server. Pipeline nên sử dụng clean workspace và chỉ chạy code từ commit/workflow đáng tin. Lệnh job có thể là:

~~~bash
./gradlew clean test generateGreeting --build-cache --info
~~~

Task `GenerateGreeting` hoặc cacheable Java compilation/test tasks có thể PUT outputs nếu chúng thực thi, `push=true` và backend chấp nhận. **Không suy đã PUT thành công chỉ vì job success**: xem cache service logs và build diagnostic records, phân biệt entry hit/miss, cacheable status và backend response.

### 9.3. Tại sao không có “đường tắt” cho PR writer?

Không dùng:

~~~groovy
push = System.getenv('CI') == 'true'
~~~

làm security policy duy nhất. Đây là **anti-pattern**, vì untrusted PR CI thường cũng có `CI=true`. Nếu PR code được phép lấy writer credentials, nó có thể tự thay đổi behavior để ghi cache hoặc lấy credentials.

Cần dùng **protected branch/workflow job, credential scoping và server ACL**. Client flag chỉ là cách thể hiện lựa chọn trong một job đã được cấp trust.

### 9.4. Phân tách namespace ở server, không chỉ bằng URL string

Bạn có thể cấu hình:

~~~text
https://cache.example.org/cache/trusted/
https://cache.example.org/cache/untrusted/
~~~

nhưng server phải enforce rằng reader/writer của namespace A không truy cập namespace B. Nếu proxy bỏ prefix trước khi backend kiểm ACL hoặc hai URL dẫn tới cùng storage bucket không kiểm quyền, cách tách này chỉ mang tính hình thức.

Thêm tests kiểm **cross-namespace PUT** bị từ chối và **cross-namespace GET** không lộ dữ liệu private.

---

## 10. Kiểm thử phân quyền remote cache thật: test matrix không làm bẩn production

Đừng thử security trên namespace production bằng một entry bất kỳ. Hãy dùng **isolated test namespace** do cache admin cấp, có TTL và quyền như production. Mục tiêu là xác nhận server enforcement.

### 10.1. Bốn nhóm test

**Nhóm A — Reader authn/authz:**

- Reader credential hợp lệ có thể `GET` entry được phép.
- Reader không thể `PUT`, kể cả nếu một client gửi request trực tiếp.
- Reader không thể xóa/sửa một entry đã có.
- Reader không thể đọc namespace được đánh dấu private khác nếu ACL cấm.

**Nhóm B — Writer authn/authz:**

- Protected CI writer có thể `GET` và `PUT` chỉ namespace được cấp.
- Writer không có quyền admin, thay ACL hoặc namespace khác.
- Revoke writer token khiến các requests mới bị từ chối.
- Audit có identity, timestamp, namespace và request outcome.

**Nhóm C — Isolation:**

- PR runner không có writer secret.
- Fork runner không có private reader secret.
- Untrusted job không dùng chung `GRADLE_USER_HOME`, daemon, init scripts với trusted writer.
- Namespace untrusted không thể populate trusted cache.
- Cache URL/credentials không bị expose trong job logs.

**Nhóm D — Correctness:**

- Trusted clean build tạo output bytes đúng.
- Developer read-only build có thể reuse đúng output đó khi inputs khớp.
- Đổi input source làm cache key đổi; không nhận stale output.
- Rebuild sạch không dùng cache cho cùng source/toolchain cho artifact tương đương.
- Release job không dùng remote cache outputs làm artifact phát hành theo chính sách security.

### 10.2. Bảng test cases và oracle

| Test | Identity | Request | Expected server result |
| --- | --- | --- | --- |
| A1 | Reader | GET existing lab key | 200, nội dung lab hợp lệ |
| A2 | Reader | PUT lab key | **403/401**, object không đổi |
| A3 | Reader | GET restricted other namespace | **403/401** |
| B1 | Trusted writer | PUT lab key | 2xx |
| B2 | Trusted writer | GET same lab key | 200 |
| B3 | Trusted writer | PUT outside assigned namespace | **403** |
| C1 | No auth | GET private lab key | **401/403** |
| C2 | Revoked writer | PUT lab key | **401/403** |
| D1 | Developer Gradle reader | `--build-cache` task with matching key | Có thể `FROM-CACHE`, output đúng |
| D2 | Developer Gradle reader | Task input changed | Output đổi đúng |
| D3 | Fresh release runner | `--no-build-cache` | Artifact mới được build từ trusted inputs |

Server API test có thể dùng công cụ HTTP test của platform team, nhưng **không gửi một arbitrary cache entry vào trusted production namespace** chỉ để kiểm PUT. Dùng test namespace/canary object riêng và không thay thế Gradle-computed task cache key bằng dữ liệu tùy ý trong production.

### 10.3. Kiểm được gì chỉ qua Gradle CLI?

~~~bash
./gradlew clean generateGreeting --build-cache --info
~~~

cho biết task chạy/cache hit/miss ở mức Gradle và có thể log lỗi backend. Tuy nhiên nếu `push=false`, client **không hề gửi PUT**, nên lệnh đó **không chứng minh** server từ chối writer access của reader.

Để chứng minh reader không thể ghi, cần **negative authorization test server-side** hoặc security testing harness gửi một controlled PUT trong namespace lab rồi xác nhận **403** và storage không đổi. Đây là khác biệt lớn giữa **client policy test** và **ACL enforcement test**.

### 10.4. Đo hiệu năng nhưng không bỏ integrity

Một shared cache tốt cần đo:

- Remote hit rate của compile/test/cacheable custom tasks.
- Thời gian download so với tự chạy task action.
- Bytes transferred và storage eviction.
- Cache misses do OS/JDK/encoding/paths.
- Số cached entries từ trusted CI và tần suất clean builds.
- Tỷ lệ auth failures/denied PUT, không coi `403` là lỗi performance.
- Sự khác biệt hash của outputs giữa clean rebuild và cache restoration.
- Incidents/quarantine và thời gian thu hồi credentials.

Không thưởng KPI “hit rate càng cao càng tốt” nếu phải cấp write permission cho mọi developer. **Integrity và provenance** là điều kiện trước, speedup đứng sau.

---

## 11. Task đúng mới tạo cache entry có thể sử dụng an toàn

### 11.1. Missing declared inputs: poisoned outputs không cần attacker

Một custom task:

~~~groovy
tasks.register('badReport') {
    outputs.file(layout.buildDirectory.file('report.txt'))

    doLast {
        // Input ảnh hưởng output nhưng Gradle không được khai.
        def region = System.getenv('DEPLOY_REGION') ?: 'local'
        def out = layout.buildDirectory.file('report.txt').get().asFile
        out.parentFile.mkdirs()
        out.text = region
    }
}
~~~

Đây là **anti-pattern**:

- `DEPLOY_REGION` không khai input.
- Closure có thể capture project layout vào execution và gây Configuration Cache issue.
- Output có thể khác khi env đổi nhưng Gradle không biết.
- Nếu task bị ép cacheable bằng plugin khác, kết quả có thể sai và được chia sẻ.

Với output phụ thuộc environment, dùng `providers.environmentVariable('DEPLOY_REGION')` được wire vào `@Input Property<String>`; task action chỉ đọc property. Hoặc nếu task có side effect deploy thì **không nên cacheable** ngay cả khi region là input.

### 11.2. Reproducibility phải được chứng minh

Cùng inputs/toolchain nên tạo **cùng output bytes**. Những nguồn không ổn định:

- Java compiler vendor/minor version hoặc annotation processor tạo timestamp.
- OS line endings và encoding mặc định.
- Absolute workspace paths được chèn vào output.
- Locale/timezone/system clock.
- File traversal order không xác định.
- Network response không pinned.
- Dynamic/SNAPSHOT dependencies.
- Shared mutable state hoặc concurrency races.
- Outputs overlap giữa hai tasks.
- Secret hoặc host-specific file được chèn vào generated artifact.

Có thể đo SHA-256 trong hai clean, independent workspaces rồi so kết quả. **Hash bằng nhau** cho một artifact giúp kiểm byte equality, nhưng không tự chứng minh producer đáng tin: phải nối với source/toolchain/workflow provenance.

### 11.3. Dependency locking và dependency verification

Gradle có **dependency locking** và **dependency verification** nhằm giảm version drift và xác minh third-party artifacts. Chúng hữu ích để trusted CI producer dùng đúng plugins/libraries.

Nhưng:

- Dependency verification áp lên dependencies theo metadata/checksums/signatures.
- Build Cache outputs là kết quả tasks riêng.
- Dependency verification **không làm cache entry được ký bởi trusted CI**.
- Secure dependencies không thay thế ACL của remote cache.
- Một plugin độc hại đã chạy trong Gradle process vẫn có thể tác động build logic hoặc lộ secrets nếu bạn cấp nó quyền.

Cần kết hợp trusted source/toolchain, dependency integrity, CI isolation và cache ACL.

### 11.4. Chỉ nên cache những tasks thuần và có output

Không đánh dấu `@CacheableTask` lên:

- Deploy/upload/publish/signing operations có side effects.
- Database migration/remote mutation.
- Gửi email hoặc tạo ticket.
- Task thực thi lệnh external không được mô hình hóa inputs/outputs.
- Task lấy live network data không được snapshot thành input.
- Task tạo output chứa random token/time cần khác mỗi invocation.
- Task chỉ in logs mà không có artifact để restore.

Nếu task action phải chạy mỗi lần vì side effect quan trọng, Build Cache hit bỏ qua action là **hành vi sai**. Chỉ dùng caching với task đã được chứng minh deterministic và có declared outputs.

### 11.5. Secrets tuyệt đối không nên nằm trong cached outputs

Không ghi API token, private key, credentials, secret-containing environment, internal personal data hoặc signed artifacts có sensitive material vào cacheable output. Remote cache là **shared storage**; quyền đọc của developer hoặc CI job khác có thể đủ để lấy nội dung đó.

Với release signing, task dùng private key phải chạy trong môi trường trusted, không đưa key vào generated classes/logs/cache artifacts. Phân loại generated outputs theo sensitivity trước khi bật remote cache.

---

## 12. Bảo vệ Gradle Wrapper, build logic và local state

Chỉ giới hạn remote cache `PUT` chưa đủ nếu **trusted CI producer đã bị chiếm**.

### 12.1. Gradle Wrapper và distribution

Gradle Wrapper chạy **trước** các build script security checks:

- Verify `gradle/wrapper/gradle-wrapper.jar` qua checksum/signature từ nguồn Gradle đáng tin.
- Pin Gradle distribution version và `distributionSha256Sum` trong Wrapper properties khi phù hợp.
- Chỉ tải qua HTTPS hoặc trusted mirror.
- Review mọi PR thay `gradlew`, `gradlew.bat`, `gradle-wrapper.jar`, `gradle-wrapper.properties`.
- Không chạy Wrapper từ repository untrusted trên máy chứa writer credentials.

Chúng là điều kiện tiên quyết của một trusted cache writer: nếu tool bị thay trước khi build chạy, server vẫn có thể nhận output không đáng tin dù identity là protected CI.

### 12.2. Build logic có thể chạy code tùy ý

Những bề mặt thực thi sớm:

- `settings.gradle`/`build.gradle` hoặc Kotlin DSL counterparts.
- `buildSrc` và included builds `build-logic`.
- `init.gradle`/`~/.gradle/init.d`, CLI `--init-script`.
- Precompiled/binary Gradle plugins được tải từ repositories.
- Remote `apply from:` scripts.
- CI workflow files và custom action scripts.

Không chạy untrusted build logic với writer secrets. Một protected branch không đủ nếu server/CI cho phép workflow chưa review tự thêm một job vào trusted environment.

### 12.3. GRADLE_USER_HOME và Daemon

Gradle User Home có plugin/dependency caches, potentially credentials, init scripts. Với CI:

- Tạo **private Gradle User Home riêng cho từng trust domain/job** khi cần.
- Không share daemon từ untrusted fork với protected writer job.
- Không mount `~/.gradle/init.d` do job không tin cậy tạo vào trusted job.
- Không share configuration-cache directories qua untrusted runners.
- Dọn ephemeral workspace trước trusted writer/release.
- Kiểm permissions trên `~/.gradle` và các files chứa credentials.

Trên POSIX, một mẫu hardening có thể là:

~~~bash
chmod 700 "$HOME/.gradle"
chmod 600 "$HOME/.gradle/gradle.properties"
~~~

Chỉ chạy những lệnh này với directory thực sự thuộc user đang quản trị; nếu file `gradle.properties` không tồn tại thì cần bỏ lệnh tương ứng. Trên Windows sử dụng NTFS ACL thay chmod.

### 12.4. Configuration Cache là một vấn đề secrets riêng

`.gradle/configuration-cache` lưu configured task graph và có thể chứa values/metadata nhạy cảm nếu credentials bị resolve/capture trong configuration. Gradle mã hóa cache state bằng key máy trong Gradle User Home, nhưng nếu attacker có quyền đọc cả cache và key thì encryption không còn là ranh giới.

Bởi vậy:

- Không commit `.gradle/configuration-cache`.
- Không dùng chung với untrusted workspace.
- Không log task inputs có secrets.
- Dùng credential providers khi Gradle API hỗ trợ.
- Tránh truyền long-lived writer token vào properties của cacheable task.

**Remote Build Cache ≠ Configuration Cache.** Bảo mật của cả hai liên quan supply chain nhưng giải pháp cụ thể khác nhau.

---

## 13. Release artifact: vì sao không nên lấy từ remote cache?

Một bản release có vai trò khác một developer/test build:

- Người dùng tải artifact và tin rằng nó đến từ **source commit đã duyệt**.
- Team có thể ký artifacts và tạo provenance/SBOM.
- Việc build/cache reuse có thể che dấu nguồn binary thực tế nếu cache hoặc local state bị kompromised.
- Artifact cần reproducibility và môi trường sạch.

Gradle security best practices khuyến nghị published artifacts luôn được build ở **trusted pristine environment**, không dùng local/remote caches hay incremental artifacts để làm đường tắt khi publish. Nhờ đó có thêm một lớp assurance ngoài cache ACL.

### 13.1. Phân biệt pipeline quality nhanh và pipeline release đáng tin

| Pipeline | Vai trò | Build Cache policy |
| --- | --- | --- |
| Developer local tests | Phản hồi nhanh | Local + remote reader nếu được phép |
| Internal PR CI tests | Kiểm thay đổi chưa merge | Read-only hoặc isolated cache |
| Trusted main CI checks | Kiểm post-merge và populate cache | Trusted writer, clean producer |
| Release artifact generation | Sinh binary để ký và publish | **Fresh ephemeral**, `--no-build-cache` cho artifact generation |
| Release validation | Hash/provenance/signature verification | Không tin cache hit thay attestation |

Nếu tổ chức đã có mô hình signed artifact/provenance, dùng nó cho **published artifacts**; không nhầm “cache URL có HTTPS” với việc artifact đã được ký.

### 13.2. Byte equality và provenance

Một kiểm tra hữu ích trên hai clean trusted builds:

~~~bash
./gradlew clean assemble --no-build-cache
~~~

rồi tính SHA-256 của file artifact. Làm lại trên **independent clean environment** với cùng source, Gradle/JDK/plugins/dependencies đã pin. Nếu hashes giống nhau, artifact có tính reproducibility ở phép kiểm này.

Tuy nhiên chỉ hash giống nhau **không đủ** để chứng minh producer không bị compromise. Provenance cần ghi commit, builder identity, workflow, dependency/toolchain versions và approvals theo chính sách release.

### 13.3. Không cache publish/sign tasks như pure transforms

Task publish có side effect gửi artifact tới remote registry; task sign dùng private key và tạo data cần integrity. Không gắn `@CacheableTask` bừa bãi để skip chúng bằng output cache. Nếu signing output có thể mô hình hóa như deterministic local transform trong một hệ thống đặc thù, vẫn phải xem security policy về key/signed file; không mặc định cho vào shared remote cache.

---

## 14. Khi nghi remote cache bị tấn công: phản ứng sự cố

Đừng cố “chạy clean” rồi kết luận cache đã sạch. `clean` xóa workspace outputs nhưng Gradle vẫn có thể lấy cùng cache entry độc hại ở lần sau.

### 14.1. Bảy bước ứng phó

1. **Ngăn ghi:** disable/deny `PUT` ở trusted namespace, revoke writer credentials nghi bị lộ, vô hiệu hóa compromised identities.
2. **Ngăn tiêu thụ:** tạm disable remote cache trong các builds bị ảnh hưởng; dùng `--no-build-cache` và tránh dùng local cache chưa xác minh.
3. **Cô lập data:** quarantine/retire namespace hoặc xóa các entries liên quan theo backend admin APIs; không giả định Gradle CLI có một lệnh chung để “purge mọi remote cache”.
4. **Giữ bằng chứng:** lưu audit logs, cache key/namespace, CI job IDs, commit SHAs, timestamps, hashes và incident timeline theo retention/security policy.
5. **Đánh giá phạm vi:** tìm các consumers đã lấy những entries đó, artifacts/test outputs bị ảnh hưởng, và liệu compiled classes/generated files đã đi vào downstream builds hay release pipeline.
6. **Rebuild sạch:** từ trusted source/toolchain và ephemeral CI, disable output caches, chạy security/tests, so artifact hashes/provenance với baseline.
7. **Khôi phục có kiểm:** rotate reader/writer creds, sửa ACL/namespace, verify negative tests, populate namespace trusted mới chỉ từ protected clean CI.

### 14.2. Vì sao xóa local `build/` chưa đủ?

~~~bash
./gradlew clean build --build-cache
~~~

vẫn có thể `FROM-CACHE` khi remote chứa entry. Nếu nghi cache bị ô nhiễm, một test rebuild sạch nên:

~~~bash
./gradlew clean build --no-build-cache
~~~

trên **fresh trusted runner** và private Gradle User Home. Đây mới là kiểm đúng hơn; chỉ xóa `build/` trong workspace cũ không bảo đảm init scripts, plugin dependencies hoặc remote cache đã đáng tin.

### 14.3. Không overwrite để “sửa” toàn bộ cache theo cùng key

Đặt lại cache entry bằng PUT từ CI có thể không được backend cho phép overwrite hoặc có race giữa multiple producers. Không dựa vào hành vi ghi đè không được document. Quản trị viên nên dùng **quarantine/retire namespace** và backend-specific invalidation policy; sau đó cho trusted producers populate dữ liệu lại.

### 14.4. Ghi incident report đủ thông tin

Một báo cáo tốt trả lời:

- Cache backend nào, namespace nào, thời điểm nào?
- Reader/writer identities nào có quyền khi sự cố xảy ra?
- Ai/CI job nào thực hiện PUT?
- Cache keys/outputs/consumers nào bị ảnh hưởng?
- Published artifacts có bị sử dụng cached bytes hay không?
- Đã revoke/rotate credentials và kiểm denied PUT chưa?
- Đã rebuild artifact ở trusted pristine environment chưa?
- Cần thay đổi pipeline, ACL, plugin checks hay reproducibility tests gì?

Không public secrets hoặc nội dung cache private trong incident report ngoài phạm vi được phép.

---

## 15. Troubleshooting thực tế

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Developer `push=false` nhưng server vẫn chấp nhận PUT trực tiếp | Server ACL quá rộng | Cấp reader identity chỉ GET; test 403 |
| PR job có `CACHE_WRITE_PASSWORD` | CI secret scoping sai | Thu hồi/rotate, chặn secrets cho untrusted code |
| Reader nhận `401` | Thiếu/sai credentials | Kiểm secret delivery, không hard-code |
| Reader nhận `403` khi GET | Không có quyền đọc namespace | Kiểm server policy; đừng nới quyền tự động |
| Reader PUT nhận `403` | ACL hoạt động đúng | Không sửa thành writer |
| Trusted CI PUT `403` | Writer chưa được cấp đúng namespace | Kiểm CI identity/server audit, không bật anonymous write |
| TLS handshake fail | CA/certificate sai | Sửa cert/trust store; không bật allowUntrustedServer |
| HTTP URL bị Gradle chặn | Insecure transport | Dùng HTTPS, không bật allowInsecureProtocol |
| Cache miss thường xuyên | Inputs, Gradle version, JDK, OS khác | Phân tích cache keys/input normalization |
| `FROM-CACHE` nhưng output khác expected | Cache poisoning hoặc task input tracking sai | Disable remote, rebuild sạch, điều tra producer/key |
| `UP-TO-DATE` dù source thay | Inputs khai thiếu hoặc task implementation lỗi | Sửa declared inputs/outputs |
| Dev push được dù `push=false` | Client có thể bị sửa/HTTP trực tiếp | Server ACL là security boundary |
| Cache entry chứa secrets | Task output leakage | Quarantine cache, rotate secrets, sửa task |
| Fork PR đọc được private cache | Namespace/read ACL sai | Thu hồi reader access, tách public/private |
| Build không dùng remote dù URL đặt | Settings config sai/cache disabled | Kiểm `settings.gradle`, `--build-cache --info` |
| `clean build` vẫn lấy output độc hại | Remote cache vẫn có entry | `--no-build-cache` trên fresh runner |
| Published artifact lệch source hash | Build provenance/caching sai | Rebuild trusted pristine, audit chain |
| Gradle logs vô tình in password | Build script/CI logging sai | Remove logging, rotate secret, masking |
| PR chỉnh workflow để lấy privileged job | Workflow event/permissions sai | Protected environments, no untrusted code with secrets |
| Multiple repos share one namespace writer | Trust domain chưa tách | Phân namespace/identity và ACL |
| TestKit pass nhưng server ACL hở | Local fixture không kiểm external server | Negative HTTP auth tests ở server |
| Local cache dùng chung runner PR/main | Gradle User Home/daemon isolation sai | Private ephemeral per trust domain |
| Dependency verification enabled nhưng cache vẫn rủi ro | Hai trust boundaries khác nhau | Cache ACL riêng, provenance riêng |
| Release job dùng cache outputs | Publish policy thiếu pristine build | Build clean --no-build-cache trên trusted runner |
| Backend unavailable, task vẫn chạy | Cache là optimization, không source of truth | Xử lý availability riêng, không nới ACL |

### 15.1. Đọc logs đúng ý nghĩa

~~~bash
./gradlew clean test generateGreeting --build-cache --info
~~~

`--info` giúp quan sát cache decisions, nhưng không bảo đảm có thông tin server ACL đầy đủ, nhất là khi `push=false` làm client không thử PUT. Để chứng minh 403/401 và audit, lấy **cache service logs** cùng negative auth tests.

### 15.2. Không chữa sai cách

- Không để reader dùng writer password “cho khỏi 403”.
- Không bật anonymous PUT để sửa cache miss.
- Không thêm `allowUntrustedServer=true` khi cert sai.
- Không giữ token trong Git repository hoặc Gradle build scan.
- Không dùng `CI=true` làm security role.
- Không đưa fork PR vào same trusted namespace với writer access.
- Không chỉ xóa `build/` khi nghi cache poisoning.
- Không mặc định `FROM-CACHE` tương đương đã qua security review.
- Không dùng dependency verification như thay thế remote cache signature.
- Không cache publish/deploy vì mong CI nhanh hơn.

---

## 16. Bài tập thực hành có đáp án

### Bài 1 — Gradle remote cache có ký entries không?

**Đáp án:** Theo security docs Gradle 9.9, Build Cache không ký/xác minh chữ ký cache entries. Phải tin tưởng writer identity, server ACL, CI producer và dữ liệu output.

### Bài 2 — Reader có `push=false` nên server không cần chặn PUT?

**Đáp án:** Sai. `push=false` là client setting. Người có thể sửa client hoặc gửi HTTP request trực tiếp; server phải enforce reader không có quyền PUT.

### Bài 3 — Developer có quyền ghi remote chung sẽ gây rủi ro gì?

**Đáp án:** Developer workspace có thể thay đổi trong lúc task chạy; thiếu input tracking hoặc untrusted build logic có thể tạo entry sai và chia sẻ tới CI/đồng nghiệp. Vì vậy developers chỉ nên pull, trusted clean CI populate.

### Bài 4 — PR trên fork có được reader secret của cache nội bộ không?

**Đáp án:** Mặc định không, nhất là khi cache chứa private compiled sources/metadata. Nếu cần public cache cho fork, dùng namespace riêng với data classification phù hợp.

### Bài 5 — Protected branch CI dùng `push=true` là đủ để an toàn?

**Đáp án:** Chưa đủ. Credential phải được protected, runner sạch, build logic/dependencies/Wrapper đáng tin, server ACL đúng, audit và task output deterministic.

### Bài 6 — HTTP Basic có tự tạo read-only permission?

**Đáp án:** Không. Nó đưa credential để backend xác thực; server quyết định reader có GET nhưng không PUT.

### Bài 7 — Vì sao HTTPS chưa chứng minh output đáng tin?

**Đáp án:** HTTPS bảo vệ kết nối đến server đã được xác thực, nhưng nếu server bị compromise hoặc writer độc hại thì output vẫn không đáng tin. Cần ACL/producer trust và artifact integrity controls.

### Bài 8 — Gradle cache key có đồng nghĩa content signature?

**Đáp án:** Không. Key ánh xạ inputs/implementation để tái sử dụng; không chứng minh nguồn gốc và chữ ký của output.

### Bài 9 — Có nên bật `allowUntrustedServer=true` cho server self-signed?

**Đáp án:** Không trong production. Cài internal CA/trust store phù hợp để Gradle JVM xác minh server. Tắt verification mở rủi ro MITM.

### Bài 10 — `GRADLE_REMOTE_CACHE_URL` không được đặt thì demo có chạy không?

**Đáp án:** Có. `settings.gradle` chỉ tạo remote config khi endpoint có mặt. Với `--build-cache`, local cache vẫn hoạt động.

### Bài 11 — Reader kết nối remote nhưng không thấy `FROM-CACHE` có phải 403?

**Đáp án:** Không. Có thể cache miss, output không cacheable, cache disabled hoặc key khác. Phải xem logs/backend responses, không đoán từ thiếu status.

### Bài 12 — Một `clean build --build-cache` có thật sự clean output producer không?

**Đáp án:** Không chắc. `clean` xóa local outputs, nhưng Gradle có thể restore outputs từ Build Cache. Khi điều tra integrity hoặc phát hành artifact, dùng fresh runner và `--no-build-cache`.

### Bài 13 — Release job có nên lấy JAR từ remote cache?

**Đáp án:** Security best practice của Gradle khuyến nghị published artifacts được build trong trusted pristine environment không dựa trên cached outputs. Tách pipeline kiểm thử nhanh và build release đáng tin.

### Bài 14 — Task đọc `System.getenv('TOKEN')` rồi ghi ra report cacheable có ổn không?

**Đáp án:** Không. Secret rò vào output shared cache; thêm `@Input` còn chưa giải quyết rủi ro. Sửa thiết kế để không đưa secret vào artifact; publish/deploy operations thường non-cacheable.

### Bài 15 — Tại sao phải kiểm negative PUT ở server?

**Đáp án:** Reader Gradle client với `push=false` không gửi PUT, nên build success chỉ kiểm client behavior. Server có thật sự từ chối PUT phải được chứng minh bằng authorization test trong namespace lab.

### Bài 16 — Cache namespace chỉ khác URL prefix có đủ không?

**Đáp án:** Chưa. Backend phải enforce ACL giữa prefixes/tenants. Nếu toàn bộ prefixes map chung storage không phân quyền, isolation chỉ là tên gọi.

### Bài 17 — Khi đã nghi cache poisoned cần làm gì đầu tiên?

**Đáp án:** Ngăn writes/reads trong trust domain bị ảnh hưởng, revoke writer credential và quarantine namespace; sau đó điều tra và rebuild trusted clean. Không chỉ chạy `clean` rồi bật cache lại.

### Bài 18 — Java reader in “Xin chào, Linh!” có chứng minh cache server an toàn?

**Đáp án:** Không. Nó chứng minh Java code/output file hoạt động với input demo. ACL server phải được kiểm độc lập qua identities, GET/PUT denial và audit.

### Bài 19 — Có thể dùng Build Cache khi làm developer unit tests?

**Đáp án:** Có, nếu task inputs/outputs đúng, reader trust phù hợp và remote cache được quản trị an toàn. Không nên vô hiệu hóa mọi cache chỉ vì release pipeline cần sạch.

### Bài 20 — Điều gì cần ghi khi audit trusted writer?

**Đáp án:** Service account, branch/workflow protected status, commit SHA, Gradle/Java/plugin versions, cache namespace, key/PUT events, job identity, retention và artifact provenance nếu dùng.

### Bài 21 — Nếu third-party Gradle plugin dùng timestamp trong generated files?

**Đáp án:** Output không deterministic; shared cache có thể chứa data khác nhau với cùng declared inputs. Sửa/pin plugin, khai inputs hoặc tắt caching cho task cho đến khi đảm bảo correctness.

### Bài 22 — Tại sao fork PR không được chạy cùng daemon với trusted writer?

**Đáp án:** Daemon và Gradle User Home có thể giữ state/init scripts/caches/credentials xuyên invocations. Cần cô lập trust domains và dùng ephemeral agents.

### Bài 23 — Có thể dùng private signing key như writer credential?

**Đáp án:** Không. Tách secrets theo mục đích. Signing keys dành cho release signing trong trusted job; cache writer identity chỉ có quyền PUT vào cache namespace, không có quyền ký/phát hành.

### Bài 24 — Một cache hit có bảo đảm test đang chạy lại không?

**Đáp án:** Không. `FROM-CACHE` nghĩa task action có thể bị bỏ qua và outputs được restore. Với security-critical checks cần đánh giá liệu reuse phù hợp hay cần test execution thực tế trên trusted clean release verification.

---

## 17. Checklist triển khai remote cache an toàn

1. Đã phân biệt remote Build Cache với Configuration Cache, dependency cache và publish repository?
2. Đã kiểm Gradle Wrapper/distribution từ nguồn đáng tin?
3. Tất cả remote cache URLs dùng HTTPS và TLS cert được verify?
4. Không bật `allowUntrustedServer`/`allowInsecureProtocol` cho production?
5. Backend có authentication bắt buộc?
6. Reader credentials **không thể PUT** ở server?
7. Writer credentials chỉ có quyền trên namespace đã cấp?
8. Writer secrets chỉ cấp cho protected trusted CI jobs?
9. Developer builds đặt `push=false` và không có writer credentials?
10. Internal PR jobs không nhận writer secret?
11. External fork PR không nhận private cache credentials nếu không được phép đọc?
12. Cache namespaces tách theo trust level/repository/data sensitivity?
13. Server enforce namespace isolation và negative tests 403/401?
14. CI dùng ephemeral runners/Gradle User Home riêng giữa trust domains?
15. Không chia sẻ daemon/init scripts từ untrusted jobs sang trusted writer?
16. Có audit GET/PUT/write identities, job IDs và commit metadata?
17. Có TTL/rotation/revocation và procedure quarantine entries?
18. Tasks được cache đã có declared inputs/outputs và deterministic results?
19. Không đưa secrets hoặc private keys vào cacheable task outputs?
20. Build logic/dependencies/Wrapper/plugins của trusted writer được review/verify?
21. Trusted cache được populate từ clean CI, không từ developer local workspace?
22. Có kiểm remote cache hit nhưng output vẫn đúng source/inputs?
23. Không cho publish/release dùng cache artifacts thay trusted pristine build?
24. Có negative tests reader PUT, untrusted namespace PUT, no-auth private GET?
25. Có so artifact hashes từ clean build và cached build ở workflows phù hợp?
26. Đã tách cache availability issue khỏi artifact integrity issue?
27. Khi nghi poisoning, có thể disable remote/cache, revoke credentials và rebuild sạch?
28. Server credentials không được hard-code, commit hoặc in logs?
29. Có support matrix Gradle/JDK/OS/plugins khi share remote cache?
30. Quyền cấp phát có được review định kỳ và cập nhật khi nhân sự/CI workflow thay đổi?

## 18. Tài liệu tham khảo chính thức

- [Gradle 9.9 — Securing the Build Tool](https://docs.gradle.org/9.9.0/userguide/securing_build_tool.html): ranh giới Wrapper/build logic, remote cache poisoning, reader/writer ACL, HTTPS, namespace separation, Gradle User Home và daemon.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): cơ chế cache keys, local/remote cache, `HttpBuildCache`, `GET`/`PUT`, `push` và authentication.
- [Gradle — Use Cases for the Build Cache](https://docs.gradle.org/current/userguide/build_cache_use_cases.html): trusted CI producers, developer pull-only và clean builds.
- [Gradle — Best Practices for Security](https://docs.gradle.org/current/userguide/best_practices_security.html): trusted clean/ephemeral builds khi xuất bản artifacts, supply-chain security.
- [Gradle — Securing Gradle Builds](https://docs.gradle.org/current/userguide/security.html): lớp repositories, dependencies, build tool và nguy cơ từ poisoned caches.
- [Gradle — HttpBuildCache DSL](https://docs.gradle.org/current/dsl/org.gradle.caching.http.HttpBuildCache.html): `url`, `push`, `enabled`, credentials, TLS verification.
- [Gradle — Common Caching Problems](https://docs.gradle.org/current/userguide/common_caching_problems.html): missing inputs, non-repeatable outputs, OS/JDK differences, overlapping outputs.
- [Gradle — Build Cache Concepts](https://docs.gradle.org/current/userguide/build_cache_concepts.html): cache key, relocatability, repeatability và task output semantics.
- [Gradle — Task Output Caching](https://docs.gradle.org/current/userguide/build_cache.html#sec:task_output_caching): task cacheability và output reuse.
- [Gradle — Implementing Custom Tasks](https://docs.gradle.org/current/userguide/implementing_custom_tasks.html): `@CacheableTask`, `@InputFile`, `@Input`, `@OutputFile`.
- [Gradle — Incremental Builds](https://docs.gradle.org/current/userguide/incremental_build.html): up-to-date checks và input/output tracking.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): checksum/signature verification cho dependencies, khác với cache entries.
- [Gradle — Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html): secrets, serialization và configuration inputs.
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): pin và xác minh distribution.
- [Gradle — Build Services](https://docs.gradle.org/current/userguide/build_services.html): tài nguyên dùng chung an toàn cho tasks khi cần.

**Kết luận:** Remote Build Cache có thể tiết kiệm nhiều thời gian nhưng **không phải nguồn artifact tự xác minh**. Giới hạn quyền server-side cho trusted writers, không cấp secrets cho untrusted code, dùng HTTPS/namespace isolation, xây task deterministic và giữ một pipeline phát hành sạch là các điều kiện tối thiểu để tăng tốc mà không làm giảm sự tin cậy của kết quả build.
