# Quản lý thông tin bí mật mà không ghi vào source hoặc log trong Gradle

## 1. Mục tiêu và vấn đề cần giải quyết

Một dự án Gradle có thể cần username/password để tải thư viện từ Maven repository riêng, token để publish artifact, khóa ký bản phát hành hoặc credentials để chạy tác vụ triển khai. **Secret** là giá trị nhạy cảm cần được bảo vệ, ví dụ password, access token, API key, private key và passphrase.

Nguyên tắc quan trọng: **mã nguồn mô tả cần lấy secret ở đâu, còn môi trường được cấp quyền mới cung cấp giá trị thật**. Không viết giá trị trong `build.gradle`, `build.gradle.kts`, `settings.gradle(.kts)`, file cấu hình được commit, ví dụ test hoặc tài liệu. Cũng không được in giá trị vào terminal, log CI, báo cáo, artifact hay metadata của build.

Bảo vệ secret cần xét toàn bộ luồng:

~~~text
Developer / CI secret store
      |
      v
Gradle User Home / environment variables
      |
      v
Gradle Provider API / repository credentials API
      |
      v
Repository authentication / publishing / signing
      |
      +--> log, cache, report, artifact: KHONG duoc chua secret
~~~

Một secret để ngoài Git vẫn có thể bị lộ nếu task dùng `println`, HTTP client log request headers, lệnh CI bật shell trace, hoặc plugin ghi giá trị vào output. Vì vậy, cần hiểu **nơi lưu**, **cách cấp**, **cách tiêu thụ** và **đầu ra**.

## 2. Những gì được và không được đưa vào source

| Dữ liệu | Có thể commit? | Lý do |
| --- | --- | --- |
| Plugin ID, Gradle Wrapper version, tọa độ dependency | Có | Thông tin cần để tái lập build |
| Tên repository và URL không chứa credentials | Thường có | Là cấu hình, miễn URL không chứa secret |
| Tên property như `internalRepoUsername` | Có | Chỉ là khóa tham chiếu, không phải giá trị |
| Username nội bộ | Xem chính sách của tổ chức | Có thể tiết lộ tài khoản/định danh |
| Password, token, private key, passphrase | Không | Có thể cấp quyền truy cập khi bị lộ |
| `gradle.properties` của dự án chỉ chứa thông số không bí mật | Có thể | Phục vụ cấu hình chung |
| `GRADLE_USER_HOME/gradle.properties` chứa credentials cá nhân | Không | Cấu hình riêng của người dùng, nằm ngoài Git |
| File `.env` có secret | Không | Dễ bị commit/sao chép và Gradle không tự đọc file `.env` |
| Log có Authorization header hoặc token trong URL | Không | Bản ghi được lưu, chia sẻ hoặc upload |

Không đặt token trong URL repository dạng username/password, query parameter hoặc thông tin request được in ra lỗi. Không truyền secret trực tiếp như giá trị của tham số `-Ppassword=...` hoặc `-Dtoken=...` vì shell history, tiến trình và log CI có thể ghi lại cả dòng lệnh.

## 3. Cấu trúc Gradle User Home và file gradle.properties

Gradle thường sử dụng hai file cùng tên nhưng ở phạm vi khác nhau:

~~~text
my-project/
├── build.gradle.kts
├── settings.gradle.kts
├── gradle.properties                 # Cau hinh du an; chi commit gia tri khong bi mat
├── gradlew
├── gradlew.bat
└── gradle/wrapper/...

<GRADLE_USER_HOME>/
├── gradle.properties                 # Cau hinh user rieng, co the chua credentials
├── caches/
├── daemon/
└── wrapper/dists/
~~~

Gradle User Home mặc định thường là `$HOME/.gradle` trên Linux/macOS và thư mục `.gradle` bên trong user profile Windows. Có thể thay vị trí bằng biến `GRADLE_USER_HOME` hoặc tùy chọn CLI `--gradle-user-home`. **`project/.gradle` là trạng thái/cache của project, không phải `GRADLE_USER_HOME`.**

Với máy developer, `GRADLE_USER_HOME/gradle.properties` là nơi hợp lý để cấu hình secret dạng Gradle property. Gradle đọc file này mà không cần đặt một bản sao vào project; vì file nằm ngoài working tree nên tránh được việc commit nhầm khi commit source.

Khi dùng file này:

1. Tạo hoặc quản lý file bằng công cụ được phép, chỉ cấp quyền đọc cho account/process cần thiết.
2. Đặt các property theo **tên** mà build yêu cầu; lấy **giá trị** từ hệ thống cấp secrets thật. Không gửi giá trị vào issue, chat công khai, README hoặc screenshot.
3. Không dùng cloud sync, artifact upload hoặc chia sẻ nguyên thư mục `GRADLE_USER_HOME` như cách phân phối credentials.
4. Tách tài khoản và quyền theo nhu cầu: tài khoản chỉ tải dependency không cần quyền publish.
5. Khi thay đổi hoặc thu hồi token, cập nhật bên cấp quyền và xóa bản sao cũ trong môi trường liên quan.

Với các file `gradle.properties`, user-level trong Gradle User Home được ưu tiên hơn project-level và installation-level. Tuy nhiên, Gradle còn nhận project properties từ CLI, system property và environment; không nên dựa vào sự trùng tên để “đè” secret một cách ngầm định. Quy định một nguồn cấu hình rõ ràng cho từng môi trường là cách dễ kiểm soát hơn.

## 4. Cách dùng Gradle credentials API cho Maven repository

Gradle có API khai báo **kiểu credential** của repository. Với `PasswordCredentials`, Gradle tự tìm username/password từ các project properties theo identity của repository. Cách này giúp script không cần lấy password ra rồi gán hoặc log.

### 4.1. Kotlin DSL

Đoạn sau là ví dụ file `build.gradle.kts`. Nó thêm repository nội bộ chỉ khi có property `internalRepoUrl` chứa URL thực tế, không bí mật:

~~~kotlin
import org.gradle.api.credentials.PasswordCredentials

repositories {
    mavenCentral()

    val internalUrl = providers.gradleProperty("internalRepoUrl")
    if (internalUrl.isPresent) {
        maven {
            name = "internalRepo"
            url = uri(internalUrl.get())
            credentials(PasswordCredentials::class)
        }
    }
}
~~~

Khi repository có identity tên `internalRepo`, Gradle lookup:

- `internalRepoUsername`
- `internalRepoPassword`

Đó là **tên properties**, không phải bí mật được viết trực tiếp trong script. Giá trị của chúng phải được cấp qua `GRADLE_USER_HOME/gradle.properties` hoặc nguồn project property được hỗ trợ, chẳng hạn biến môi trường CI. Khi build thật sự cần credentials nhưng chưa được cấp, Gradle có thể báo lỗi về credentials trước khi chạy task phụ thuộc.

Dòng `internalUrl.get()` chỉ lấy URL cấu hình **không nhạy cảm**. Không sao chép cách gọi `get()` này sang password rồi đưa vào `println`. URL phải là endpoint HTTPS đáng tin cậy của hệ thống sử dụng; không tắt TLS verification để khắc phục lỗi đăng nhập.

### 4.2. Groovy DSL tương đương

Ví dụ file `build.gradle`:

~~~groovy
import org.gradle.api.credentials.PasswordCredentials

def internalUrl = providers.gradleProperty('internalRepoUrl')

repositories {
    mavenCentral()

    if (internalUrl.isPresent()) {
        maven {
            name = 'internalRepo'
            url = uri(internalUrl.get())
            credentials(PasswordCredentials)
        }
    }
}
~~~

Hai ví dụ dùng cùng repository identity và cùng tên credentials; chỉ khác cú pháp DSL. Để tải dependency thật, cần thêm artifact/dependency nội bộ và URL hợp lệ. Đây là **ví dụ cấu hình credentials**, không tự tạo ra Maven repository hoặc user account.

### 4.3. Mỗi kiểu authentication cần đúng credential type

| Loại | Dữ liệu cần cung cấp | Trường hợp |
| --- | --- | --- |
| `PasswordCredentials` | `Username` + `Password` | Username/password hoặc token được server chấp nhận như password |
| `HttpHeaderCredentials` | `AuthHeaderName` + `AuthHeaderValue` | Server dùng HTTP authentication header tùy chỉnh |
| `AwsCredentials` | `AccessKey` + `SecretKey`; session token khi áp dụng | Repository dùng cơ chế AWS phù hợp |

Các suffix dựa trên identity của repository. Ví dụ tên `internalRepo` cộng `Username` thành `internalRepoUsername`. Nếu server yêu cầu header token, không tự gắn token vào URL; dùng đúng cơ chế `HttpHeaderCredentials` và authentication hỗ trợ bởi repository theo tài liệu.

### 4.4. Download và publish có phạm vi khác nhau

`repositories { }` cho dependency resolution, trong khi `publishing { repositories { } }` thuộc cấu hình plugin `maven-publish` dùng để đẩy artifact lên server. Có thể khai báo credentials theo identity cho publish repository tương tự, nhưng nên dùng **tài khoản và token riêng**, cấp quyền tối thiểu. Một script có maven repository không tự tạo tác vụ publish đầy đủ: cần plugin, publications và repository thực tế.

## 5. ORG_GRADLE_PROJECT_: cấp secrets từ môi trường

Gradle cho phép ánh xạ environment variable thành project property theo mẫu:

~~~text
ORG_GRADLE_PROJECT_<propertyName>
~~~

Để cấp credentials cho ví dụ `internalRepo`, tên biến là:

~~~text
ORG_GRADLE_PROJECT_internalRepoUsername
ORG_GRADLE_PROJECT_internalRepoPassword
~~~

Gradle ánh xạ chúng thành properties `internalRepoUsername` và `internalRepoPassword`, để cơ chế credentials lookup có thể dùng. Đây là cách phù hợp cho CI vì secret có thể được inject vào process Gradle ở thời điểm chạy, không cần tạo file chứa plaintext trong repository.

Để dùng project property có tên khác, API Kotlin DSL là `providers.gradleProperty("propertyName")`; để đọc biến môi trường không theo prefix trên, dùng `providers.environmentVariable("ENV_NAME")`.

**Không nhầm Gradle project properties với OS environment variables:** `providers.gradleProperty("internalRepoPassword")` có thể lấy property được cung cấp qua `ORG_GRADLE_PROJECT_internalRepoPassword`, trong khi `providers.environmentVariable("DEPLOY_TOKEN")` trực tiếp lấy biến `DEPLOY_TOKEN` từ môi trường.

Để tránh sai lệch, giữ tên property đúng chữ hoa/thường; không tự đổi `internalRepoPassword` thành `INTERNALREPOPASSWORD`.

### 5.1. Giới hạn của biến môi trường

Environment variable không được tự động mã hóa. Process Gradle và các tiến trình con có thể đọc nó; debugger hoặc script/plugin được chạy cùng quyền có thể truy xuất. Vì vậy:

- Chỉ cấp secret cho job hoặc step thật sự cần.
- Không dump toàn bộ environment ra stdout hoặc upload vào artifact.
- Không cho code hoặc plugin không đáng tin chạy trong process có quyền truy cập secret.
- Cân nhắc token ngắn hạn, vault/secret manager và workload identity/OIDC khi dịch vụ hỗ trợ.
- Thu hồi/rotate token khi có dấu hiệu rò rỉ; xóa biến trong shell không xóa những bản sao đã lọt vào logs.

## 6. Ví dụ cấu hình CI mà không ghi giá trị vào YAML

Trong một job GitHub Actions đã được cấu hình checkout, Java, Gradle Wrapper và plugin publish, có thể cấp credentials **chỉ trong step publish** bằng snippet:

~~~yaml
- name: Publish artifacts
  env:
    ORG_GRADLE_PROJECT_internalRepoUsername: ${{ secrets.INTERNAL_REPO_USERNAME }}
    ORG_GRADLE_PROJECT_internalRepoPassword: ${{ secrets.INTERNAL_REPO_PASSWORD }}
  run: ./gradlew publish --console=plain
~~~

`secrets.INTERNAL_REPO_USERNAME` và `secrets.INTERNAL_REPO_PASSWORD` là **tham chiếu tới tên secrets** được quản lý trong hệ thống CI; YAML không chứa giá trị thật. Snippet này không phải workflow độc lập: cần plugin publish, publication, URL repository và permissions phù hợp.

Để triển khai có trách nhiệm:

1. Chỉ cấp secrets vào bước publish, không truyền sẵn cho mọi job build/test.
2. Kiểm tra người có quyền sửa workflow, script Gradle, plugin hoặc bước shell trong job.
3. Hạn chế workflows dùng untrusted pull requests/fork chạy với publish credentials.
4. Sử dụng CI environments bảo vệ, approval cho release khi quy trình yêu cầu.
5. Không dùng `echo`, `env`, `printenv`, shell trace `set -x` hoặc command logging có thể in secrets.
6. Đừng phụ thuộc hoàn toàn vào việc CI tự mask giá trị: log của một token đã encode hoặc bị biến đổi có thể không được che.
7. Không upload secrets file, Gradle User Home, Configuration Cache có thông tin nhạy cảm hoặc debug logs thô.

Có thể chuyển nguyên tắc này sang các hệ thống CI khác: secret store được phân quyền cấp biến môi trường đúng phạm vi, Gradle tiêu thụ qua credentials API, logs chỉ chứa kết quả cần thiết.

## 7. Provider API: sử dụng và kiểm tra mà không in secret

API `Provider` giúp tham chiếu giá trị từ cấu hình môi trường theo cách lazy, nhưng **Provider không phải cơ chế mã hóa**. Khi gọi `get()` để lấy giá trị secret, mã sử dụng vẫn nhận chuỗi thật và chịu trách nhiệm bảo vệ.

Trong Kotlin DSL, có thể phối hợp hai nguồn:

~~~kotlin
val tokenFromGradle = providers.gradleProperty("deployToken")
val tokenFromEnv = providers.environmentVariable("DEPLOY_TOKEN")
val tokenProvider = tokenFromGradle.orElse(tokenFromEnv)
~~~

`orElse` ưu tiên nguồn đầu tiên khi có giá trị. Đây là thứ tự ưu tiên **do code định nghĩa**, không phải quy tắc ưu tiên mặc định chung cho mọi project properties.

### 7.1. Thử nghiệm runnable chỉ kiểm tra presence

File `build.gradle.kts` tối giản:

~~~kotlin
val hasToken = providers.environmentVariable("DEPLOY_TOKEN").isPresent

tasks.register("checkSecretPresence") {
    group = "verification"
    description = "Check whether a token is configured"

    doLast {
        if (hasToken) {
            println("DEPLOY_TOKEN is configured")
        } else {
            println("DEPLOY_TOKEN is missing")
        }
    }
}
~~~

Chạy từ thư mục chứa Gradle Wrapper:

~~~bash
./gradlew -q checkSecretPresence
~~~

Hoặc trên Windows PowerShell:

~~~powershell
.\gradlew.bat -q checkSecretPresence
~~~

Nếu `DEPLOY_TOKEN` chưa tồn tại, stdout của task là:

~~~text
DEPLOY_TOKEN is missing
~~~

Nếu biến tồn tại, dòng thay thành `DEPLOY_TOKEN is configured`. Mã **không đọc hoặc in giá trị của token**; nó chỉ chuyển thông tin tồn tại thành Boolean. Nhưng kiểm tra presence **không chứng minh token đúng**, chưa hết hạn hoặc được cấp đủ quyền. Muốn kiểm tra đăng nhập thật phải dùng task/plugin thực hiện yêu cầu có kiểm soát, không log credentials hoặc request headers.

Khi thiết kế custom task có secrets, tránh giải quyết bằng cách đưa `tokenProvider.get()` vào `println`, command-line argument, report hoặc output. Ưu tiên API chuyên dụng của plugin, managed property/provider và sử dụng giá trị tại thời điểm cần; đặc biệt chú ý quy tắc của Configuration Cache và tác dụng phụ của task publish.

## 8. Ngăn secret lọt vào log và artifact

Các đường rò rỉ không chỉ là source control:

| Nơi có thể lộ | Nguyên nhân | Cách giảm rủi ro |
| --- | --- | --- |
| `println` / `logger.lifecycle` / `logger.debug` | Build script hoặc plugin log chuỗi raw | Không log secret; log thông báo trạng thái trung tính |
| `--info` / `--debug` / `--stacktrace` | Plugin hoặc HTTP client in tham số, header, exception | Chỉ dùng nơi tin cậy; kiểm tra log trước khi chia sẻ |
| Shell history / command line | Truyền `-Ppassword=...`, `-Dtoken=...` hoặc gọi tool với token trong args | Cấp qua secret store/biến môi trường thích hợp; không đưa raw token vào args |
| GitHub Actions log | Shell trace, env dump, command echo | Giới hạn step, tránh in, kiểm tra masking nhưng không phụ thuộc hoàn toàn |
| Build scan / telemetry | Custom tags/values, environment capture, plugin reporting | Xem phạm vi dữ liệu thu thập và quyền truy cập; không publish secrets |
| Unit test / integration test reports | Test in env, URL hoặc request | Không đưa token vào stdout hoặc stacktrace của test |
| HTTP URL / exception | Password trong URL, query token hoặc lỗi chứa header | Dùng credentials API và TLS, cấm ghi raw request |
| `build/`, JAR, ZIP, Docker image | Task copy file credentials vào output | Không đóng gói secret; dùng runtime injection/secret mount khi phù hợp |
| Remote Build Cache | Task output có plaintext secret được cache | Không tạo output chứa secret; giới hạn cache theo trust boundary |
| Configuration Cache | Task configuration/state giữ secret có thể bị serialize | Dùng API phù hợp, hạn chế serialize và bảo vệ cache/khóa |

Không coi việc `--quiet` là đủ để giấu một secret: nó giảm log của Gradle, còn `println` trong task vẫn có thể in. Cũng không nên tin mọi plugin sẽ tự che bất kỳ chuỗi nào trông giống token.

Khi cần gửi log cho người hỗ trợ, hãy **kiểm tra và redact** trước khi chia sẻ. Ngoài token cần tìm Authorization header, cookie, username, private key, URL có credentials và dữ liệu cá nhân. Tránh đăng log nguyên gốc lên ticket công khai; log bản sao cũng có thể tồn tại lâu sau khi issue đã đóng.

## 9. Git và .gitignore: tránh commit nhầm, xử lý khi đã lộ

Một `.gitignore` của project có thể bỏ qua file local thường gặp:

~~~gitignore
.gradle/
**/build/
.env
.env.local
secrets.local.properties
~~~

Đây là những tên file cục bộ minh họa; Gradle **không tự đọc** `.env` hoặc `secrets.local.properties` nếu không có build logic/plugin riêng. File `GRADLE_USER_HOME/gradle.properties` mặc định nằm ngoài project nên không phụ thuộc `.gitignore` trong project.

**Quan trọng:** thêm file vào `.gitignore` sau khi đã được Git track **không xóa file khỏi index hoặc Git history**. Nếu credentials từng được commit, hành động đúng là:

1. Xem secret đã bị lộ đối với mọi người/hệ thống có quyền truy cập bản commit hoặc bản sao.
2. **Thu hồi hoặc rotate** token/mật khẩu từ dịch vụ cấp quyền càng sớm càng tốt.
3. Loại giá trị khỏi phiên bản source hiện tại và xử lý file đã track.
4. Kiểm tra Git history, pull requests, forks, CI logs, artifacts, mirror, backup và cache theo phạm vi có thể.
5. Phối hợp xử lý history nếu cần; rewrite Git history tác động người dùng khác và **không thay thế việc thu hồi secret**.
6. Bổ sung secret scanning trong local/CI mà không đưa token thật lên công cụ quét không được phê duyệt.

Không chụp màn hình phần cấu hình có password, không paste token vào issue chỉ để nhờ người khác tái hiện lỗi.

## 10. Configuration Cache và Build Cache có liên quan đến secret thế nào?

**Configuration Cache** lưu trạng thái cấu hình và task graph đã được xử lý để tái sử dụng. Nếu một secret bị lấy ra sớm rồi lưu trong trạng thái task được serialize, giá trị ấy có thể đi vào cache entry. Gradle hiện hỗ trợ mã hóa Configuration Cache trên đĩa, nhưng đó không phải lý do để chia sẻ cache entry và khóa mã hóa một cách công khai.

Theo hướng dẫn Gradle, đối với **repository credentials**, nên dùng Gradle credentials API và nguồn user-level `GRADLE_USER_HOME/gradle.properties`. Nội dung file user-level properties không tự động được serialize vào Configuration Cache chỉ vì được dùng làm nguồn; nhưng một task/plugin tự lưu plaintext vào state vẫn có thể tạo rủi ro. Cần xem quyền truy cập `project/.gradle/configuration-cache`, khóa mã hóa ở Gradle User Home và chính sách cache trong CI.

**Build Cache** là hệ thống khác: nó lưu output của những task được phép cache. Nếu output của task chứa file credentials hoặc token, Build Cache có thể giữ hoặc phát tán file đó. Không tạo artifact/cache output mang secrets; với task triển khai/publish có tác dụng bên ngoài, không giả định cache giúp thay thế việc thực thi nghiệp vụ.

**Gradle User Home** còn chứa caches, daemon logs và wrapper distributions; không nên upload nguyên thư mục như build artifact hay chia sẻ giữa các runner không tin cậy. Các tool cache chính thức cần được cấu hình quyền truy cập và nội dung phù hợp.

## 11. Các tình huống gỡ lỗi điển hình

| Triệu chứng | Nguyên nhân có thể | Hành động đúng |
| --- | --- | --- |
| Báo thiếu `internalRepoUsername` | Name/identity repo hoặc property chưa khớp | Kiểm tra tên repo, property và nguồn cấp; không hardcode |
| Local tải được dependency, CI thất bại | Developer có user gradle.properties, CI chưa có secret | Cấp secret vào đúng step CI, không copy file user lên Git |
| CI báo 401/403 | Token hết hạn, sai quyền hoặc authentication type | Kiểm tra repository URL/TLS, quyền và rotation |
| Dùng `providers.gradleProperty` nhưng nhận missing | Property không được cấp hoặc tên không đúng | Kiểm tra tên và source, có thể kiểm tra presence mà không log value |
| Task in token trong `--debug` | Script/plugin tự log credentials | Ngừng chia sẻ log, rotate token, sửa logging |
| Gradle build scan chứa nội dung nội bộ | Plugin/custom value gửi quá nhiều metadata | Loại dữ liệu nhạy cảm, kiểm tra phạm vi và quyền truy cập scan |
| Secret đã commit, đã thêm gitignore | Lịch sử Git vẫn có secret | Rotate và xử lý history/bản sao theo quy trình |
| CI lưu cache chứa file secret | Task viết secrets vào output hoặc lưu User Home bừa bãi | Sửa output, giới hạn cache, thu hồi credentials đã lộ |
| Configuration Cache gây lo ngại | Secret có thể được serialize qua state | Dùng credentials API và tránh capture plaintext; bảo vệ cache/key |
| Token chỉ có thể dùng khi chạy trên một máy | Token bị ràng buộc scope/IP/role hoặc đã hết hạn | Cấp credentials đúng môi trường, không chuyển token cá nhân bừa bãi |

Nên ghi vào tài liệu vận hành **tên property cần cấu hình**, môi trường nhận nó, quyền tối thiểu và nguồn cấp, nhưng không ghi giá trị thật. Người thực hiện build có thể tự kiểm tra bước cung cấp secret bằng công cụ quản trị của tổ chức.

## 12. Checklist trước khi mở PR hoặc chạy release

- [ ] Không có password/token/key trong build script, file được commit, test fixture, tài liệu hoặc URL.
- [ ] Tên credentials được đặt rõ ràng; dùng `PasswordCredentials` hoặc API phù hợp thay cho hardcode.
- [ ] Secret local lưu ngoài project ở `GRADLE_USER_HOME`/secret manager với quyền file đúng.
- [ ] CI cấp secret đúng job/step, không cho mã không tin cậy truy cập.
- [ ] Token có quyền tối thiểu, thời hạn sống và cơ chế thu hồi hợp lý.
- [ ] Không truyền secret như đối số CLI, không `echo`/dump environment hay header.
- [ ] Logs, stacktrace, test reports, build scans và artifacts được xem xét trước khi chia sẻ.
- [ ] Task output, cache, Docker image không chứa file secret.
- [ ] Nếu đã lộ, token được rotate; Git history, CI logs, cache và bản sao được xử lý.
- [ ] Tài liệu hướng dẫn onboarding ghi tên property và cách cấp quyền, không ghi plaintext.

## 13. Bài tập tự kiểm tra

**Bài 1.** Repository khai báo `name = "internalRepo"` và `credentials(PasswordCredentials::class)`. Gradle đọc những property nào?  
**Đáp án:** `internalRepoUsername` và `internalRepoPassword`.

**Bài 2.** Muốn cấp `internalRepoPassword` qua environment của CI, dùng tên biến nào?  
**Đáp án:** `ORG_GRADLE_PROJECT_internalRepoPassword`.

**Bài 3.** File `GRADLE_USER_HOME/gradle.properties` có nằm trong project/.gradle không?  
**Đáp án:** không. Đó là hai vùng khác nhau; Gradle User Home mặc định ở home user.

**Bài 4.** `providers.environmentVariable("DEPLOY_TOKEN").isPresent` có xác nhận token hợp lệ không?  
**Đáp án:** không. Nó chỉ kiểm tra có giá trị môi trường ở thời điểm đó.

**Bài 5.** Dùng `Provider<String>` có tự bảo vệ token khỏi mọi log hay cache không?  
**Đáp án:** không. Provider có tính lazy, nhưng mã sau đó vẫn có thể lấy plaintext và làm lộ.

**Bài 6.** `--quiet` có ngăn `println(token)` in ra không?  
**Đáp án:** không nên dựa vào `--quiet`; code tự in ra vẫn có thể lộ giá trị.

**Bài 7.** Token đã nằm trong commit cũ, xóa dòng trong commit mới đã đủ chưa?  
**Đáp án:** chưa. Cần thu hồi/rotate, xử lý history và các bản sao.

**Bài 8.** Vì sao credentials cho download dependency nên khác credentials cho publish?  
**Đáp án:** nguyên tắc quyền tối thiểu; build chỉ download không cần quyền ghi.

**Bài 9.** Configuration Cache mã hóa có thể được public không?  
**Đáp án:** không. Cache có thể chứa state nhạy cảm, phải bảo vệ cả cache và khóa.

**Bài 10.** Khi có thể dùng secret manager để cấp môi trường cho job CI, tại sao không viết mật khẩu vào `-P...`?  
**Đáp án:** args/command history/log có thể làm lộ giá trị; CI secret injection hạn chế những kênh đó khi cấu hình đúng.

## 14. Tài liệu tham khảo chính thức

- [Gradle — Build Environment Configuration](https://docs.gradle.org/current/userguide/build_environment.html): `gradle.properties`, project properties, environment và Provider API.
- [Gradle — Supported Repository Protocols / Handling credentials](https://docs.gradle.org/current/userguide/supported_repository_protocols.html): credentials lookup theo repository identity.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): cache entry, bảo vệ credentials và cấu hình tin cậy.
- [Gradle — Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html): hạn chế đối với task state, provider và secrets.
- [Gradle — Securing the Build Tool](https://docs.gradle.org/current/userguide/securing_build_tool.html): hướng dẫn bảo vệ công cụ build.
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): publish repository, publication và authentication.
- [GitHub Actions — Using secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets): cấu hình secrets cho CI.

**Kết luận:** source chỉ nên chứa tên property và logic Gradle; **giá trị** đến từ User Home hoặc môi trường/secret store có quyền kiểm soát; logging, cache, artifact và quy trình phát hành phải giữ secret không bị phát tán.