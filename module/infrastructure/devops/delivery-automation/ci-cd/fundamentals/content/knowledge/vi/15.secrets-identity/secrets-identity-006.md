# Ngăn bí mật xuất hiện trong mã nguồn, nhật ký, cache và artifact

Secret trong CI/CD có thể là mật khẩu, access token, private key, signing key, certificate, credential truy cập registry, thông tin đăng nhập database hoặc webhook token. Những giá trị này thường cần thiết để build, publish package, ký artifact hay triển khai ứng dụng. Nếu secret xuất hiện trong mã nguồn, log, cache hoặc artifact, người có quyền đọc các tài nguyên đó có thể sử dụng nó ngoài mục đích ban đầu.

Rò rỉ secret không chỉ xảy ra khi lập trình viên commit nhầm `.env`. Một workflow có thể in biến môi trường khi bật debug, ghi credential vào file cấu hình rồi upload nhầm, lưu token trong Docker layer, hoặc đưa toàn bộ thư mục làm việc vào cache. Vì vậy, bảo vệ secret cần được thiết kế xuyên suốt vòng đời CI/CD: cấp phát, sử dụng, truyền giữa các bước, ghi log, lưu trữ, thu hồi và điều tra.

Mục tiêu là secret chỉ được cấp cho đúng job và đúng bước cần dùng, tồn tại trong thời gian ngắn nhất có thể, không đi vào đầu ra có thể chia sẻ và có thể thu hồi nhanh khi nghi ngờ bị lộ. Cần kết hợp quản lý secret tập trung, quyền tối thiểu, secret scanning, log hygiene, cache/artifact allowlist và quy trình ứng phó sự cố.

## 1. Nhận diện những nơi secret có thể bị lộ

Trong một pipeline, dữ liệu đi qua nhiều thành phần: repository, runner, shell process, build tool, container builder, cache, artifact store, log service và hệ thống triển khai. Secret có thể bị sao chép từ một nơi sang nơi khác mà người viết workflow không nhận ra.

| Vị trí | Cách rò rỉ thường gặp | Hệ quả |
|---|---|---|
| Mã nguồn và Git history | Commit `.env`, token trong YAML, private key trong script | Secret tồn tại trong lịch sử và bản clone của repository |
| File cấu hình cục bộ | Ghi credential vào `gradle.properties`, `settings.xml`, `.npmrc` | File có thể bị commit, cache hoặc upload |
| Nhật ký CI | `echo`, `printenv`, `set -x`, debug log, exception | Người có quyền đọc log có thể lấy credential |
| Process arguments | Đưa token vào command line hoặc URL | Có thể xuất hiện trong process list, audit log hoặc shell trace |
| Cache | Cache cả thư mục home, config hoặc workspace | Job khác có thể khôi phục dữ liệu chứa secret |
| Artifact | Upload toàn bộ workspace, test report, dump hoặc config | Secret được lưu lâu hơn thời gian chạy job và có thể tải xuống |
| Container image | Dùng `ARG`, `ENV`, `COPY` để đưa secret vào image | Secret có thể nằm trong layer, metadata hoặc image history |
| Output giữa job | Ghi token vào `GITHUB_OUTPUT`, artifact hoặc file trung gian | Job downstream hoặc người tải artifact có thể đọc được |
| Thông báo và báo cáo | Đính kèm log vào issue, chat, email hoặc ticket | Secret lan sang hệ thống có phạm vi truy cập khác |

Một secret có thể đã bị lộ ngay cả khi giá trị hiển thị trong log bị che bằng dấu `***`. Ví dụ, một phần token được nối chuỗi, mã hóa Base64 hoặc chia thành nhiều đoạn có thể không khớp với giá trị mà bộ lọc nhận diện. Việc masking giúp giảm lộ vô tình, nhưng không thay thế thiết kế tránh ghi secret.

## 2. Quản lý secret ở một nguồn có kiểm soát

Không lưu secret lâu dài trong source code hoặc file cấu hình được commit. Dùng secret manager của nền tảng CI/CD, vault hoặc dịch vụ quản lý danh tính và credential của cloud. Repository chỉ giữ tên tham chiếu và cách lấy secret, không giữ giá trị.

Ví dụ file cấu hình có thể mô tả tên biến môi trường mà ứng dụng cần:

```yaml
repository:
  url: https://packages.example.com/releases
  username: ${MAVEN_USERNAME}
  password: ${MAVEN_PASSWORD}
```

Đây là cấu trúc minh họa; ứng dụng hoặc công cụ đọc cấu hình phải hỗ trợ cách thay thế biến môi trường tương ứng. Không commit giá trị thật vào file YAML.

### Phân loại và cấp quyền tối thiểu

Mỗi secret cần có mục đích, chủ sở hữu, phạm vi và thời hạn. Không dùng một credential quản trị chung cho tất cả workflow. Ví dụ:

- Job chạy unit test chỉ cần đọc source và dependency công khai thì không cần secret deploy.
- Job tải dependency riêng tư chỉ cần credential đọc package.
- Job publish package cần quyền ghi đúng package/repository.
- Job deploy staging cần danh tính của staging, không cần credential production.
- Job ký release cần quyền ký riêng và chỉ chạy trên revision được chấp thuận.

Secret nên được cấp ở cấp job hoặc step hẹp nhất có thể. Tránh đặt tất cả secret ở cấp workflow hoặc truyền chúng qua nhiều job khi không cần.

### Ưu tiên credential ngắn hạn

Với cloud provider hoặc dịch vụ hỗ trợ workload identity, ưu tiên OIDC hoặc cơ chế tương đương để đổi danh tính workflow lấy credential ngắn hạn. Cách này giảm số lượng access key dài hạn phải lưu và thu hồi.

Trust policy phải giới hạn issuer, audience, repository, branch/tag, environment hoặc workflow identity theo đúng nhu cầu. Chỉ bật quyền yêu cầu OIDC token ở job cần thiết. `id-token: write` cho phép job yêu cầu token; nó không tự giới hạn quyền của danh tính cloud. Quyền thực tế phải được kiểm soát thêm ở trust policy và role phía dịch vụ đích.

Nếu chưa thể bỏ credential dài hạn, hãy đặt TTL phù hợp, giới hạn scope, lưu trong secret manager, xoay vòng định kỳ và có quy trình thu hồi khẩn cấp.

## 3. Ngăn secret đi vào mã nguồn và Git history

### Không commit file cấu hình chứa credential

Các file thường cần chú ý gồm `.env`, `.env.local`, `application-local.yml`, `gradle.properties` cá nhân, Maven `settings.xml`, `.npmrc`, `.pypirc`, file cloud credentials, kubeconfig và private key.

Thêm các file cục bộ vào `.gitignore`:

```gitignore
# Local environment files
.env
.env.*
!.env.example

# Local application configuration
application-local.yml
application-local.yaml

# Private keys and certificates with private material
*.key
*.pem
*.p12
*.pfx

# Local credential directories
.aws/
.kube/
secrets/
```

`.gitignore` chỉ ngăn Git tự động đưa file chưa được theo dõi vào danh sách thay đổi. Nó không xóa file đã commit trước đó và không ngăn người dùng cố ý `git add -f`. Vì vậy, cần kết hợp quy ước repository, review và secret scanning.

Có thể commit file mẫu không chứa giá trị thật:

```dotenv
MAVEN_USERNAME=replace-with-local-username
MAVEN_PASSWORD=replace-with-local-password
```

Đặt tên rõ như `.env.example` và ghi chú cách lấy giá trị từ secret manager. Không dùng giá trị trông giống token thật trong file mẫu vì scanner hoặc người dùng có thể nhầm đó là credential hợp lệ.

### Kiểm tra trước khi commit

Trước khi commit, kiểm tra các file đã stage:

```bash
git status --short
git diff --cached --stat
git diff --cached
```

Review cả file mới, file đổi tên và file nhị phân. Một file cấu hình có thể bị stage từ lần làm việc trước dù thay đổi hiện tại không nhắc tới nó.

Local pre-commit hook có thể chạy secret scanner để cảnh báo sớm, nhưng hook trên máy lập trình viên có thể bị bỏ qua hoặc không được cài. CI và push protection trên nền tảng Git phải là lớp kiểm soát bắt buộc.

### Quét mã nguồn và lịch sử Git

Secret scanner tìm các chuỗi có hình dạng credential, khóa riêng hoặc mẫu token đã biết. Có thể dùng Gitleaks, TruffleHog hoặc scanner do nền tảng cung cấp. Ví dụ với Gitleaks CLI:

```bash
# Quét cây thư mục hiện tại
gitleaks dir --redact .

# Quét repository và lịch sử Git
gitleaks git --redact .
```

Tên lệnh và tùy chọn có thể thay đổi theo phiên bản scanner; hãy pin phiên bản công cụ trong CI và kiểm tra tài liệu của phiên bản đang dùng. Quét cây hiện tại và quét lịch sử là hai phạm vi khác nhau. Secret đã bị xóa khỏi file hiện tại vẫn có thể còn trong commit cũ.

Nên bật secret scanning và push protection nếu nền tảng repository hỗ trợ. Push protection có thể chặn credential đã nhận diện trước khi commit được đẩy lên remote. Scanner vẫn có thể bỏ sót secret tùy chỉnh hoặc giá trị không theo mẫu đã biết, vì vậy không được coi kết quả sạch là bằng chứng tuyệt đối.

### Không xem việc xóa commit là thu hồi secret

Nếu secret đã được push, xóa dòng đó trong commit mới không làm credential cũ mất hiệu lực. Lịch sử vẫn có thể còn trên remote, fork, clone, pull request, cache hoặc bản sao của người khác.

Thứ tự xử lý khi phát hiện secret đã commit:

1. Thu hồi hoặc rotate credential ngay; ưu tiên chặn khả năng sử dụng trước.
2. Xác định loại secret, phạm vi quyền, thời gian tồn tại và hệ thống có thể đã truy cập.
3. Kiểm tra log truy cập và hoạt động bất thường trong thời gian credential còn hiệu lực.
4. Xóa secret khỏi source hiện tại và, khi cần, làm sạch Git history theo quy trình quản trị repository.
5. Phối hợp cập nhật các clone, fork, branch và pipeline có thể giữ lịch sử cũ.
6. Quét lại repository, artifact, log và cache để xác định bản sao còn sót.
7. Ghi nhận nguyên nhân và bổ sung kiểm soát ngăn tái diễn.

Viết lại history có thể cần force push và làm gián đoạn các clone đang tồn tại. Chỉ thực hiện theo quy trình repository của nhóm, phối hợp với người dùng và nhóm liên quan. History rewrite không thay thế việc rotate credential.

## 4. Tránh đưa secret vào command line và shell history

Không đặt token trực tiếp trong câu lệnh, URL hoặc tham số được ghi lại. Ví dụ sau có nguy cơ làm lộ credential qua shell history, process list hoặc log:

```bash
curl -H "Authorization: Bearer REAL_TOKEN_VALUE" https://api.example.com/deploy
```

Không dùng URL dạng `https://user:password@host/...` vì URL có thể xuất hiện trong log proxy, exception hoặc telemetry.

Ưu tiên để chương trình đọc credential từ biến môi trường hoặc secret file được cấp trong thời gian ngắn. Với công cụ hỗ trợ stdin, file descriptor hoặc secret mount, dùng các cơ chế đó để tránh đưa giá trị vào command argument. Dù dùng biến môi trường, không in toàn bộ môi trường và không chạy shell tracing khi secret đang hiện diện.

Ví dụ trong GitHub Actions, truyền secret vào đúng step:

```yaml
- name: Publish package
  env:
    MAVEN_USERNAME: ${{ secrets.MAVEN_USERNAME }}
    MAVEN_PASSWORD: ${{ secrets.MAVEN_PASSWORD }}
  run: ./gradlew --no-daemon publish
```

Gradle có thể đọc biến môi trường để xác thực repository:

```kotlin
publishing {
    repositories {
        maven {
            name = "internalReleases"
            url = uri("https://packages.example.com/releases")
            credentials {
                username = providers.environmentVariable("MAVEN_USERNAME").orNull
                password = providers.environmentVariable("MAVEN_PASSWORD").orNull
            }
        }
    }
}
```

Ví dụ này giả định repository hỗ trợ xác thực username/password và Gradle Maven Publish plugin đã được cấu hình. Không ghi các giá trị ra `gradle.properties` hoặc log. Nếu plugin hoặc build script có thể in credential, hãy sửa cách log và kiểm thử với giá trị giả trước khi dùng.

Biến môi trường vẫn có thể được đọc bởi process con cùng user hoặc bị ghi ra khi debug. Hãy cấp ở step hẹp nhất, dùng runner riêng cho job nhạy cảm và kết thúc job ngay sau khi hoàn thành thao tác.

## 5. Ngăn secret xuất hiện trong nhật ký CI

Log thường được lưu lâu, lập chỉ mục và chia sẻ cho nhiều người hơn quyền truy cập secret gốc. Vì vậy, một lần `echo` nhầm có thể tạo ra bản sao credential khó thu hồi hoàn toàn.

### Những lệnh dễ làm lộ dữ liệu

Tránh các lệnh hoặc chế độ debug sau trong job có secret:

```bash
set -x
env
printenv
set
curl -v ...
./gradlew --debug publish
```

`set -x` in lệnh sau khi shell đã mở rộng biến. `env`, `printenv` và `set` có thể liệt kê giá trị môi trường. Chế độ verbose/debug của HTTP client, build tool hoặc SDK có thể ghi header, URL, request body và thông tin xác thực.

Chỉ bật debug khi thật sự cần, giới hạn người xem và thời gian lưu log, dùng credential thử nghiệm có thể thu hồi, đồng thời kiểm tra log trước khi chia sẻ. Không dùng production secret để tái hiện lỗi trong một phiên debug không kiểm soát.

### Không đưa secret vào thông báo lỗi

Exception có thể chứa URL đầy đủ, request header, connection string hoặc nội dung cấu hình. Khi xử lý lỗi, log mã trạng thái, tên dịch vụ, correlation ID và thông tin đã làm sạch. Không log object cấu hình nguyên vẹn nếu object có trường password hoặc token.

Ví dụ thông báo an toàn:

```text
Package publish failed: HTTP 401 from internal package registry.
Repository: internalReleases
Request ID: <correlation-id>
Credential value: [redacted]
```

Không ghi response body hoặc request header thô nếu chưa xác định chúng không chứa secret hay dữ liệu nhạy cảm.

### Masking chỉ là lớp phòng vệ bổ sung

Nền tảng CI thường tự che secret đã khai báo khi phát hiện đúng chuỗi trong log. Với giá trị được tạo trong runtime, một số nền tảng cho phép đăng ký giá trị cần mask trước khi có thể xuất hiện trong output. Ví dụ GitHub Actions hỗ trợ workflow command `add-mask`.

```bash
printf '::add-mask::%s\n' "$GENERATED_TOKEN"
```

Lệnh phải chạy trước mọi output có thể chứa giá trị. Tuy nhiên, masking có thể không nhận diện biến thể đã encode, cắt ngắn, nối chuỗi hoặc biến đổi. Không in secret để “thử xem có bị mask không”. Cách đúng là không tạo log chứa secret ngay từ đầu.

Không truyền secret qua job output hoặc `GITHUB_OUTPUT` chỉ để tiện chia sẻ. Nếu job sau cần credential, hãy để job đó lấy credential trực tiếp từ secret manager hoặc yêu cầu token ngắn hạn riêng.

## 6. Ngăn secret lọt vào cache

Cache nhằm tăng tốc build, không phải kho lưu trữ cấu hình hoặc secret. Khi cache một thư mục quá rộng, các file xác thực có thể bị lưu cùng dependency và được khôi phục ở lần chạy sau.

Các đường dẫn cần xem xét kỹ:

- `$HOME`, `~/.gradle`, `~/.m2`, `~/.npm`, `~/.config`.
- `.aws/`, `.kube/`, `.docker/` và thư mục credential của cloud SDK.
- `.env`, `.npmrc`, `.pypirc`, Maven `settings.xml`, kubeconfig.
- `gradle.properties` hoặc file cấu hình repository có password.
- Workspace chứa file tạm được tạo trong lúc deploy hoặc ký artifact.
- Build output, test report hoặc generated config có thể nhúng biến môi trường.

Không cache toàn bộ home directory hoặc workspace chỉ để tiết kiệm thời gian. Chọn đúng thư mục dependency cần tái sử dụng và loại trừ cấu hình chứa credential.

### Ví dụ cache Gradle có phạm vi hẹp

Với GitHub Actions, có thể dùng cache Gradle qua action setup chuyên dụng hoặc cấu hình cache path rõ ràng. Ví dụ dưới đây minh họa cache dependency Gradle:

```yaml
- name: Set up Gradle
  uses: gradle/actions/setup-gradle@v4

- name: Build and test
  run: ./gradlew --no-daemon clean check
```

Action này quản lý cache Gradle theo cơ chế riêng. Cần đọc cấu hình và quyền truy cập của action đang pin trước khi dùng. Không thêm một bước cache `$HOME` hoặc toàn bộ `.gradle` tùy tiện nếu chưa biết những file nào có thể chứa credential hoặc dữ liệu nhạy cảm.

Nếu tự cấu hình cache, chỉ lưu các thư mục dependency/artifact cache đã xác định, không lưu `gradle.properties` cá nhân, `init.gradle` chứa credential hoặc file `credentials`.

### Phân tách cache theo ranh giới tin cậy

Cache có thể bị đầu độc nếu job không tin cậy ghi dữ liệu mà job đặc quyền sau đó khôi phục và thực thi. Ví dụ, pull request từ fork có thể chạy script build do contributor kiểm soát. Không để cache do job không tin cậy ghi vào namespace được job release tin cậy sử dụng.

Các nguyên tắc:

- Dùng cache key có phạm vi theo hệ điều hành, runtime, lockfile và nhóm tin cậy.
- Không dùng restore key quá rộng để khôi phục dữ liệu không rõ nguồn.
- Không cho job chạy mã không tin cậy ghi vào cache mà job deploy hoặc ký artifact dùng lại.
- Không lưu secret, token, file cấu hình xác thực hoặc artifact phát hành trong cache.
- Xem cache là dữ liệu có thể bị xóa hoặc thay đổi; xác minh dependency sau khi khôi phục.
- Với job release, cân nhắc cache riêng hoặc chạy sạch nếu độ tin cậy của cache không thể chứng minh.

Phạm vi cache và quyền đọc/ghi khác nhau theo nền tảng CI. Cần kiểm tra cơ chế branch scope, pull request scope và quyền restore/save thực tế, không giả định mọi nền tảng có cùng quy tắc.

## 7. Ngăn secret lọt vào artifact và báo cáo

Artifact thường được chia sẻ giữa job, lưu trên server hoặc tải về để điều tra. Chỉ upload đúng file cần thiết thay vì toàn bộ workspace.

### Dùng allowlist thay vì upload toàn bộ thư mục

Ví dụ cấu hình có rủi ro:

```yaml
- uses: actions/upload-artifact@v4
  with:
    name: everything
    path: .
```

Nó có thể đưa `.env`, file cấu hình, log, cache, credential tạm và các file không liên quan vào artifact. Nên chỉ định chính xác đầu ra cần lưu:

```yaml
- uses: actions/upload-artifact@v4
  with:
    name: application-release
    path: |
      build/libs/application.jar
      build/reports/tests/test/index.html
    if-no-files-found: error
    retention-days: 7
```

Ví dụ chỉ phù hợp nếu test report không chứa dữ liệu nhạy cảm. Nếu report có request/response, dữ liệu test thật hoặc token, hãy làm sạch hoặc không upload report đó. Đường dẫn allowlist cần được review mỗi khi build thay đổi cấu trúc output.

### Kiểm tra nội dung trước khi upload

Trước khi lưu artifact, xác minh danh sách file và loại file. Có thể tạo manifest, quét secret trên thư mục staging và chỉ upload khi scan đạt.

Ví dụ shell kiểm tra thư mục staging:

```bash
find release-staging -type f -print
gitleaks dir --redact release-staging
```

Scanner có thể không phát hiện credential tùy chỉnh hoặc dữ liệu nhạy cảm không theo mẫu token. Kết hợp allowlist đường dẫn, kiểm tra nội dung và review những file mới được đưa vào artifact.

### Giới hạn quyền và thời gian lưu

Artifact chứa log hoặc test report nên có retention phù hợp với mục đích. Hạn chế quyền download theo vai trò, repository và môi trường. Không dùng artifact store như nơi chia sẻ credential giữa nhóm. Nếu artifact có chứa secret, coi đó là sự cố rò rỉ: thu hồi credential, gỡ hoặc cách ly artifact theo chính sách và rà soát bản tải xuống nếu có thể.

## 8. Bảo vệ secret trong Docker build và container image

Một lỗi phổ biến là truyền credential qua Docker `ARG` hoặc `ENV`:

```dockerfile
ARG REPOSITORY_TOKEN
ENV REPOSITORY_TOKEN=$REPOSITORY_TOKEN
RUN ./gradlew publish
```

`ENV` tồn tại trong cấu hình image; `ARG` có thể xuất hiện trong metadata hoặc lịch sử build tùy cách build và phiên bản công cụ. Không dùng chúng làm kênh truyền secret.

### Dùng BuildKit secret mount

BuildKit cho phép mount secret tạm thời vào một bước build. Secret mount không được tự động lưu vào layer cuối nếu script không sao chép hoặc ghi giá trị đó ra output.

Ví dụ Dockerfile:

```dockerfile
# syntax=docker/dockerfile:1.7
FROM eclipse-temurin:21-jdk AS build
WORKDIR /workspace
COPY . .

RUN --mount=type=secret,id=maven_settings,target=/root/.m2/settings.xml,required=true \\
    ./mvnw --batch-mode --settings /root/.m2/settings.xml package

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /workspace/target/application.jar /app/application.jar
ENTRYPOINT ["java", "-jar", "/app/application.jar"]
```

Build với secret file:

```bash
docker buildx build \\
  --secret id=maven_settings,src="$HOME/.m2/settings.xml" \\
  --tag registry.example.com/team/application:1.0.0 .
```

`settings.xml` phải được tạo từ secret manager hoặc file credential tạm có quyền truy cập hạn chế. Không copy file đó vào build context. Thêm nó vào `.dockerignore` nếu có khả năng nằm trong context.

Ví dụ `.dockerignore`:

```dockerignore
.env
.env.*
!.env.example
**/settings.xml
**/.npmrc
**/gradle.properties
**/*.pem
**/*.key
.aws/
.kube/
.docker/
secrets/
```

Điều chỉnh `.dockerignore` theo cấu trúc dự án. Không loại trừ file cấu hình build hợp lệ nếu nó không chứa secret; mục tiêu là ngăn credential và file cục bộ đi vào build context.

Ngay cả khi dùng secret mount, lệnh build vẫn có thể làm lộ secret nếu in file, bật shell trace, ghi cấu hình đã giải mã vào thư mục được copy sang stage sau hoặc đưa secret vào output. Hãy kiểm tra script và các layer được tạo.

### Không copy credential vào image cuối

Multi-stage build giúp chỉ copy đầu ra cần thiết từ build stage sang runtime stage. Tuy nhiên, nó không tự bảo đảm secret biến mất nếu secret đã được ghi vào file output hoặc layer được copy. Chỉ copy artifact ứng dụng, không copy home directory, Maven/Gradle config hoặc thư mục workspace đầy đủ.

Kiểm tra image bằng công cụ inspect và scanner phù hợp. Nếu phát hiện credential trong image, tạo image mới sau khi rotate credential; xóa tag cũ không làm image đã được tải về biến mất khỏi máy khác.

## 9. Thiết kế workflow chỉ cấp secret cho job tin cậy

Không phải mọi trigger đều có cùng mức tin cậy. Pull request từ fork có thể chạy mã do contributor kiểm soát. Workflow cần tách phần kiểm tra mã không tin cậy khỏi phần publish/deploy có quyền truy cập secret.

### Tách job kiểm thử và job phát hành

Ví dụ sau chạy test cho pull request và push, nhưng chỉ publish khi push vào nhánh chính:

```yaml
name: Verify and publish

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
      - run: ./gradlew --no-daemon clean check

  publish:
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    needs: test
    runs-on: ubuntu-latest
    environment: package-publishing
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
      - name: Publish package
        env:
          MAVEN_USERNAME: ${{ secrets.MAVEN_USERNAME }}
          MAVEN_PASSWORD: ${{ secrets.MAVEN_PASSWORD }}
        run: ./gradlew --no-daemon publish
```

Job `test` không nhận secret publish. Job `publish` chỉ chạy sau push vào `main`, và chỉ step publish được cấp credential. Environment `package-publishing` cần được cấu hình protection rule, branch policy và quyền người phê duyệt phù hợp. Đây là ví dụ nền tảng; cần pin action theo full commit SHA trong repository yêu cầu kiểm soát chuỗi cung ứng nghiêm ngặt.

Không dùng `pull_request_target` để checkout rồi thực thi script từ head của pull request trong job có secret hoặc quyền ghi. Sự kiện này chạy trong ngữ cảnh của nhánh đích và có thể có quyền cao hơn. Nếu cần dùng để gắn nhãn hoặc quản lý metadata, không chạy mã không tin cậy từ pull request trong ngữ cảnh đặc quyền.

### Dùng OIDC thay cho cloud access key dài hạn

Với deploy cloud, job có thể yêu cầu OIDC token và đổi lấy credential ngắn hạn. Ví dụ cấu hình quyền ở cấp job:

```yaml
deploy-staging:
  runs-on: ubuntu-latest
  permissions:
    contents: read
    id-token: write
  steps:
    - uses: actions/checkout@v4
    - name: Authenticate to cloud
      run: ./scripts/ci/authenticate-with-oidc.sh
    - name: Deploy
      run: ./scripts/ci/deploy-staging.sh
```

Script xác thực cần dùng SDK của cloud provider để lấy OIDC token từ môi trường runner và đổi thành credential ngắn hạn. Trust policy phía cloud phải kiểm tra issuer, audience, repository, ref và environment. Không ghi token OIDC hoặc credential trả về vào log, artifact hay cache.

## 10. Kiểm tra secret trước và sau khi build

Secret scanning nên được đặt ở nhiều điểm, vì một lớp có thể bỏ sót dữ liệu mà lớp khác nhìn thấy.

| Thời điểm | Kiểm tra | Mục tiêu |
|---|---|---|
| Trên máy phát triển | Pre-commit scan và review staged diff | Ngăn secret trước khi commit |
| Khi push | Secret scanning/push protection | Chặn credential đã nhận diện trước khi vào remote |
| Trong pull request | Quét diff và file mới | Phát hiện secret trong thay đổi đang review |
| Trên Git history | Quét toàn bộ lịch sử theo lịch | Phát hiện secret cũ còn tồn tại |
| Trước cache save | Kiểm tra path và nội dung được cache | Tránh lưu credential hoặc output nhạy cảm |
| Trước artifact upload | Allowlist và secret scan staging directory | Tránh upload secret, log hoặc config |
| Trước publish image | Quét layer, metadata và image filesystem | Phát hiện credential đã bị bake vào image |
| Sau sự cố | Quét lại repository, cache, artifact và log | Xác định phạm vi bản sao còn sót |

Scanner nên được cấu hình để redact report. Báo cáo phát hiện secret cần hạn chế quyền truy cập; không đính kèm nguyên văn giá trị phát hiện vào issue hoặc chat. Với false positive, dùng allowlist hẹp theo file hoặc rule, có lý do và thời hạn xem xét. Không tạo allowlist rộng để bỏ qua cả thư mục cấu hình.

Secret scanner không thay thế DLP hoặc kiểm tra dữ liệu cá nhân. Một file có thể chứa thông tin khách hàng, dữ liệu production hoặc certificate không theo mẫu token mà scanner không nhận diện. Vì vậy, kiểm soát đường dẫn và quyền upload vẫn cần thiết.

## 11. Xoay vòng và ứng phó khi secret bị lộ

Khi nghi ngờ secret xuất hiện trong source, log, cache hoặc artifact, hãy coi credential đó là đã bị lộ cho tới khi xác minh được phạm vi. Không chờ hoàn tất điều tra mới thu hồi một token có quyền cao.

### Quy trình phản ứng

1. **Chặn khả năng sử dụng:** revoke token, disable key hoặc rotate password/certificate. Nếu hệ thống hỗ trợ, giảm scope hoặc khóa credential ngay.
2. **Xác định phạm vi:** tìm commit, workflow run, log, artifact, cache key, image digest và hệ thống đã nhận credential.
3. **Kiểm tra hoạt động:** xem audit log, API access, registry pull/push, deployment và truy cập bất thường trong thời gian secret còn hiệu lực.
4. **Thay credential:** cấp credential mới với scope nhỏ hơn, cập nhật secret manager và xác minh workflow hoạt động.
5. **Loại bỏ bản sao:** làm sạch source/history theo quy trình, gỡ artifact hoặc image bị ảnh hưởng, xóa cache liên quan và giới hạn quyền log.
6. **Thông báo đúng nhóm:** báo cho chủ sở hữu hệ thống, security và người vận hành theo quy trình nội bộ; tránh gửi secret trong thông báo.
7. **Ngăn tái diễn:** thêm scanner, sửa allowlist, thu hẹp quyền, giảm retention hoặc thay đổi cách truyền secret.

Xóa artifact hoặc log khỏi giao diện không chứng minh mọi bản sao đã biến mất. Có thể tồn tại bản tải xuống, bản mirror, cache, backup hoặc bản export. Việc thu hồi credential là biện pháp quan trọng nhất để làm cho các bản sao cũ không còn sử dụng được.

### Xác định mức độ ảnh hưởng

Khi đánh giá sự cố, ghi lại loại secret, quyền của nó, hệ thống đích, thời gian bị lộ, ai có quyền đọc vị trí rò rỉ và có dấu hiệu sử dụng trái phép hay không. Không đưa giá trị secret vào báo cáo sự cố; dùng fingerprint hoặc định danh credential đã được hệ thống quản lý cấp.

Nếu private signing key bị lộ, cần xem xét thu hồi key/certificate, đánh giá artifact đã ký trong khoảng thời gian ảnh hưởng và phát hành lại bằng khóa mới. Nếu credential registry bị lộ, kiểm tra cả quyền đọc lẫn quyền ghi package và image.

## 12. Những cách làm tạo cảm giác an toàn giả

| Cách làm | Vì sao chưa đủ | Cách cải thiện |
|---|---|---|
| Chỉ thêm `.env` vào `.gitignore` | File đã tracked hoặc đã commit vẫn tồn tại | Secret scanning, staged diff review và push protection |
| Xóa secret trong commit mới | Credential cũ vẫn hoạt động và history có thể còn bản sao | Revoke/rotate trước, sau đó xử lý history |
| Dựa hoàn toàn vào log masking | Biến thể secret có thể không được nhận diện | Không in secret, tắt trace và debug nhạy cảm |
| Truyền token trên command line | Có thể lộ qua process list, shell history hoặc log | Secret manager, env/file descriptor hoặc secret mount |
| Cache toàn bộ `$HOME` | Có thể lưu config và credential cá nhân | Cache allowlist thư mục dependency |
| Upload toàn bộ workspace | Có thể chứa `.env`, log và file tạm | Artifact allowlist và scan trước upload |
| Dùng Docker `ARG`/`ENV` cho token | Secret có thể tồn tại trong metadata hoặc layer | BuildKit secret mount hoặc workload identity |
| Dùng chung một secret production cho mọi job | Mở rộng phạm vi ảnh hưởng khi job không tin cậy bị chiếm | Credential riêng, quyền tối thiểu và TTL ngắn |
| Chỉ chạy scanner một lần | Secret có thể xuất hiện ở lịch sử, log hoặc output mới | Quét nhiều điểm trong vòng đời |
| Cho phép cache PR được dùng bởi job release | Có nguy cơ dùng dữ liệu do mã không tin cậy tạo ra | Phân tách trust scope và xác minh input |
| Lưu secret trong artifact để job sau dùng | Artifact thường có quyền tải rộng và retention dài | Job sau tự lấy credential từ secret manager |

## 13. Checklist bảo vệ secret trong CI/CD

Trước khi merge hoặc vận hành pipeline, hãy kiểm tra:

- [ ] Không có secret thật trong mã nguồn, file mẫu, script, YAML hoặc Git history mới.
- [ ] `.gitignore` và `.dockerignore` loại trừ đúng file credential cục bộ.
- [ ] Secret được lưu trong secret manager hoặc hệ thống credential có kiểm soát.
- [ ] Mỗi job/step chỉ nhận secret cần thiết; job test không nhận credential publish/deploy.
- [ ] Ưu tiên OIDC hoặc credential ngắn hạn cho cloud và registry khi có hỗ trợ.
- [ ] Token không xuất hiện trong command line, URL, shell history hoặc process arguments.
- [ ] Không dùng `set -x`, `env`, `printenv`, verbose/debug logging trong bước có secret.
- [ ] Exception, request header và response body được làm sạch trước khi ghi log.
- [ ] Secret động được mask trước output nếu nền tảng hỗ trợ, nhưng không dựa vào masking để bảo vệ.
- [ ] Không ghi secret vào job output, cache, artifact hoặc file trung gian dùng chung.
- [ ] Cache chỉ chứa đường dẫn dependency cần thiết; cache của job không tin cậy không được dùng làm đầu vào cho job đặc quyền.
- [ ] Artifact dùng allowlist, có retention và quyền download phù hợp.
- [ ] Docker build dùng secret mount; không dùng `ARG`/`ENV` hoặc copy credential vào image.
- [ ] Secret scanning chạy trên diff, repository và phạm vi cần thiết của Git history.
- [ ] False positive được xử lý bằng allowlist hẹp, có lý do và thời hạn.
- [ ] Có quy trình revoke/rotate, điều tra log và xử lý các bản sao khi secret bị lộ.
- [ ] Quyền ký artifact và deploy production được giới hạn ở workflow và identity được chấp thuận.

Bảo vệ secret không phải một thao tác che chuỗi trong log. Đó là việc kiểm soát nơi credential được tạo, ai được đọc, process nào được sử dụng và những đầu ra nào có thể giữ lại dữ liệu. Khi source, log, cache, artifact và image đều được quản lý theo nguyên tắc tối thiểu, pipeline có thể thực hiện build và phát hành mà không biến các tài nguyên dùng chung thành nơi lưu credential ngoài ý muốn.
