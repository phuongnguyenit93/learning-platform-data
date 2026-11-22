# Giới hạn quyền đối với pipeline của pull request không tin cậy

Một Pull Request (PR) có thể chứa thay đổi trong mã ứng dụng, build script, test, dependency, Dockerfile và cả cấu hình pipeline. Khi CI chạy PR, hệ thống không chỉ đọc diff để review: nó thực thi mã do người tạo PR cung cấp. Một lệnh build Gradle, Maven plugin, npm lifecycle script hoặc test đều có thể chạy lệnh hệ thống, đọc file trong runner và truy cập mạng.

Nếu PR đến từ fork hoặc người đóng góp chưa được tin cậy, pipeline phải coi toàn bộ mã và dữ liệu do PR cung cấp là đầu vào không tin cậy. Chỉ cần một job có quyền ghi repository, đọc secret production, truy cập mạng nội bộ hoặc dùng chung máy với release job, một thay đổi nhỏ trong PR cũng có thể trở thành đường dẫn chiếm quyền.

Bài học này trình bày cách giới hạn quyền cho pipeline của PR không tin cậy: xác định ranh giới tin cậy, cấp token tối thiểu, không đưa secret vào job kiểm tra, chọn runner cách ly, bảo vệ cache và artifact, kiểm soát workflow có quyền cao, cũng như tách kiểm tra PR khỏi quy trình phát hành.

## 1. Vì sao pipeline của PR là một ranh giới bảo mật?

PR thường được tạo để đề xuất thay đổi trước khi merge. Nhưng từ góc độ CI, một PR có thể thay đổi bất kỳ file nào mà build system sử dụng. Ví dụ:

- Gradle build script có thể khai báo task tùy ý.
- Maven POM có thể thêm plugin thực thi trong lifecycle.
- npm package có thể chạy script khi cài dependency.
- Test có thể đọc file, gọi process hoặc gửi request ra ngoài.
- Dockerfile có thể thực hiện lệnh trong lúc build image.
- Script deploy hoặc helper script có thể bị sửa để chạy lệnh khác.
- Workflow có thể thay đổi trigger, permission, action hoặc cách sử dụng secret.

Vì vậy, "chỉ chạy test" không có nghĩa job an toàn. Test thường thực thi chính mã nguồn và build logic mà PR vừa thay đổi.

### Mô hình tin cậy cơ bản

Có thể chia các luồng công việc thành hai vùng:

- **Untrusted workflow:** kiểm tra PR từ fork hoặc nguồn chưa được tin cậy. Mục tiêu là cung cấp phản hồi build/test với quyền rất hạn chế.
- **Trusted workflow:** publish artifact, tạo release, truy cập secret nhạy cảm hoặc triển khai môi trường. Chỉ chạy từ mã nguồn và sự kiện đã đáp ứng chính sách tin cậy.

Luồng tham khảo:

~~~text
Pull Request from fork / untrusted contributor
                    |
                    v
          Untrusted CI workflow
          - Read-only source access
          - No production secrets
          - Isolated disposable runner
          - Build and test only
                    |
                    v
           Status checks and reports
                    |
              Review / approval
                    |
                    v
             Merge to protected main
                    |
                    v
           Trusted release workflow
           - Rebuild trusted commit
           - Publish immutable artifact
           - Obtain scoped identity
           - Deploy with approval
~~~

Ranh giới quan trọng nằm ở quyền và dữ liệu được phép đi qua. Kết quả test của PR có thể được hiển thị để review, nhưng không nên tự động biến thành đầu vào có quyền cao cho bước publish hoặc deploy.

## 2. Những tài sản cần bảo vệ

Trước khi cấu hình workflow, hãy liệt kê tài sản mà một job có thể truy cập:

| Tài sản | Rủi ro khi PR không tin cậy truy cập được |
|---|---|
| Repository write token | Sửa branch, tag, release hoặc nội dung repository |
| API token và credential | Truy cập dịch vụ bên ngoài hoặc giả mạo danh tính |
| Cloud credential | Đọc dữ liệu, tạo tài nguyên hoặc thay đổi hạ tầng |
| Secret production | Truy cập hệ thống thật và dữ liệu nhạy cảm |
| Registry write permission | Thay thế image hoặc package được phát hành |
| Self-hosted runner | Đọc file còn sót, credential hoặc dữ liệu của job khác |
| Cache dùng chung | Đưa dữ liệu giả vào build đáng tin cậy sau đó |
| Artifact của PR | Đưa binary hoặc script không tin cậy vào luồng release |
| OIDC identity | Nhận credential cloud nếu trust policy quá rộng |
| Network nội bộ | Truy cập database, control plane hoặc service riêng |

Không phải mọi job đều có thể truy cập mọi tài sản. Mục tiêu của thiết kế là bảo đảm job PR chỉ nhận đúng quyền cần thiết để kiểm tra mã và công bố kết quả.

### Xem mọi thành phần do PR điều khiển là mã có thể thực thi

Không chỉ file .java hoặc .js mới có thể thực thi. Hãy coi các nội dung sau là đầu vào có thể thay đổi hành vi job:

- Build script, plugin và dependency.
- Test code, fixture và test data.
- Dockerfile, shell script, PowerShell script.
- Workflow được gọi hoặc reusable workflow.
- Git submodule, package install hook và code generator.
- File cấu hình được parser hoặc tool nạp trong lúc chạy.

Nếu job chạy một lệnh từ repository, cần giả định PR có thể thay đổi cách lệnh đó hoạt động.

## 3. Nguyên tắc thiết kế quyền cho pipeline không tin cậy

### Least privilege

Cấp quyền tối thiểu theo từng job. Job compile/test thường chỉ cần đọc source. Nó không cần quyền ghi repository, tạo release, publish package hoặc triển khai production.

Nên khai báo permission tường minh thay vì dựa vào quyền mặc định rộng của repository hoặc tổ chức.

### Không cấp secret cho PR không tin cậy

Job kiểm tra PR nên chạy mà không có secret nhạy cảm. Nếu integration test cần credential, hãy dùng tài khoản thử nghiệm có quyền rất hẹp, dữ liệu giả lập và môi trường riêng. Không dùng credential production để làm cho test thuận tiện.

### Cách ly môi trường thực thi

Mỗi job nên chạy trong môi trường sạch, không chia sẻ workspace, credential hoặc volume nhạy cảm với job khác. Ưu tiên runner tạm thời, bị thu hồi sau khi hoàn tất.

### Tách kiểm tra khỏi phát hành

PR chỉ tạo bằng chứng kiểm tra. Publish và deploy được thực hiện bởi workflow riêng sau khi thay đổi đã được merge vào nhánh bảo vệ và đáp ứng chính sách release.

### Kiểm tra lại đầu vào ở ranh giới tin cậy

Không coi artifact, cache, report hoặc metadata do PR tạo ra là đáng tin cậy chỉ vì CI của PR đã hoàn tất. Khi cần phát hành, build lại từ commit đã được merge bằng workflow tin cậy và dependency đã được xác minh.

## 4. Token của pipeline và quyền truy cập repository

Nhiều nền tảng CI cấp token tự động cho job. Token này có thể dùng để checkout source, đọc metadata PR, tải artifact hoặc gọi API. Nếu token có quyền ghi, mã trong PR có thể cố sử dụng quyền đó.

### Chỉ cấp quyền đọc cho workflow kiểm tra PR

Ví dụ GitHub Actions:

~~~yaml
name: pr-validation

on:
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    permissions:
      contents: read
    steps:
      - name: Checkout pull request
        uses: actions/checkout@v4
        with:
          persist-credentials: false

      - name: Set up JDK
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
          cache: gradle

      - name: Build and test
        run: ./gradlew --no-daemon check
~~~

Ví dụ này minh họa các điểm chính:

- Trigger là pull_request.
- Token chỉ có contents: read.
- Checkout không lưu credential của Git trong cấu hình repository cục bộ.
- Job không nhận secret production.
- Job chạy build và test trên hosted runner tiêu chuẩn.

Phiên bản action trong ví dụ dùng major tag để dễ đọc. Repository có yêu cầu kiểm soát chuỗi cung ứng nghiêm ngặt nên pin action theo commit SHA đầy đủ và cập nhật có review.

Trên GitHub, fork PR thường nhận token với quyền hạn chế và không được cấp repository secrets theo mặc định. Tuy nhiên, cần kiểm tra cài đặt repository/organization và loại sự kiện thực tế; không nên dựa vào mặc định mà không khai báo permissions rõ ràng. Dependabot và các luồng tự động tương tự cũng có quy tắc hạn chế riêng.

### Không dùng quyền ghi chỉ để đăng comment

Một workflow có thể cần đăng kết quả hoặc nhãn lên PR. Đừng vì nhu cầu đó mà cấp pull-requests: write cho toàn bộ job build/test.

Có thể tách thành hai job:

- Job kiểm tra mã: chỉ đọc source, không có secret và không có quyền ghi.
- Job cập nhật PR: chỉ xử lý metadata cần thiết, có quyền ghi giới hạn và không checkout hoặc thực thi mã từ PR.

Nếu job cập nhật PR cần đọc dữ liệu do PR cung cấp, hãy truyền dữ liệu như dữ liệu thuần, xác thực và giới hạn kích thước; không ghép chuỗi đó thành lệnh shell hoặc mã thực thi.

## 5. Phân biệt pull_request và pull_request_target

GitHub Actions có hai sự kiện thường được nhắc đến khi thiết kế workflow PR.

### pull_request

Sự kiện pull_request phù hợp cho build/test PR. Với fork, workflow thường chạy theo chính sách hạn chế token và secrets. Mặc định checkout trong ngữ cảnh PR thường kiểm tra merge ref để xác minh thay đổi kết hợp với nhánh đích; nếu chọn checkout head SHA, cần hiểu rằng đó là kiểm tra riêng phần commit của nhánh nguồn.

Đây thường là lựa chọn phù hợp cho CI không cần quyền ghi hoặc secret.

### pull_request_target

pull_request_target chạy workflow trong ngữ cảnh repository đích. Nó có thể có quyền và secret của repository đích theo cấu hình. Điều này hữu ích cho các thao tác metadata có kiểm soát như gắn nhãn hoặc phản hồi PR, nhưng nguy hiểm nếu workflow tải và thực thi mã từ nhánh PR.

**Không checkout và chạy mã PR trong một job pull_request_target có quyền cao.** Nếu build script, test hoặc action của PR được thực thi trong job này, mã không tin cậy có thể tìm cách sử dụng token hoặc secret sẵn có.

Ví dụ về hành vi cần tránh:

~~~yaml
on:
  pull_request_target:

jobs:
  unsafe:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha }}
      - run: ./gradlew check
~~~

Workflow trên checkout mã từ PR rồi thực thi build script trong ngữ cảnh pull_request_target. Đây là một mẫu rủi ro cao.

Nếu cần pull_request_target cho metadata:

- Chỉ dùng workflow được review từ nhánh mặc định.
- Không checkout PR head.
- Không chạy script, action hoặc build tool từ nội dung PR.
- Không đưa dữ liệu event vào shell command theo cách nội suy không an toàn.
- Cấp đúng quyền API cần cho thao tác metadata.
- Giữ logic đơn giản, dễ audit.

Nếu cần build/test, dùng workflow pull_request có quyền đọc và môi trường cách ly.

## 6. Tránh command injection từ dữ liệu PR

Tiêu đề PR, tên branch, commit message, tên người dùng và nội dung mô tả đều do người gửi kiểm soát. Nếu nội suy trực tiếp các giá trị này vào script shell, dữ liệu có thể bị diễn giải như cú pháp lệnh.

Ví dụ không an toàn:

~~~yaml
- name: Print PR title
  run: echo "${{ github.event.pull_request.title }}"
~~~

Biểu thức được thay thế trước khi shell chạy. Nếu tiêu đề chứa ký tự điều khiển shell, câu lệnh được tạo ra có thể khác với ý định của người viết workflow.

Cách an toàn hơn là truyền giá trị qua environment variable và dùng nó như dữ liệu:

~~~yaml
- name: Print PR title
  env:
    PR_TITLE: ${{ github.event.pull_request.title }}
  run: printf '%s\n' "$PR_TITLE"
~~~

Một số nguyên tắc:

- Không nội suy trực tiếp dữ liệu event vào run script.
- Truyền dữ liệu qua environment hoặc file input có kiểm soát.
- Quote biến khi sử dụng trong shell.
- Validate kiểu, độ dài và tập ký tự trước khi dùng làm tham số.
- Không dùng eval hoặc ghép dữ liệu thành command.
- Không ghi dữ liệu PR chưa lọc vào GITHUB_ENV hoặc GITHUB_OUTPUT theo cách có thể tạo thêm dòng điều khiển.
- Với PowerShell, truyền qua environment và xử lý như chuỗi dữ liệu; tránh nối trực tiếp vào mã lệnh.
- Không đưa tiêu đề, branch name hoặc commit message vào tên file/path mà không chuẩn hóa.

Environment variable giúp tránh việc shell parse giá trị ngay lúc tạo script, nhưng không tự động làm dữ liệu trở nên đáng tin cậy. Nếu giá trị được truyền tiếp vào một shell command, SQL, template hoặc API nhạy cảm, vẫn phải validate và encode theo đúng ngữ cảnh.

## 7. Không cấp secret production cho build/test PR

Build tool và test có thể thực thi mã tùy ý. Nếu job có secret, mã PR có thể đọc biến môi trường, file credential, process argument, workspace hoặc metadata service rồi gửi dữ liệu ra ngoài.

### Dùng dữ liệu và credential thử nghiệm

Nếu integration test cần xác thực:

- Tạo tài khoản test riêng.
- Chỉ cấp quyền vào dữ liệu giả lập hoặc namespace test.
- Đặt hạn mức và thời gian sống ngắn.
- Không dùng chung password hoặc token với staging/production.
- Thu hồi credential sau khi không còn cần.
- Hạn chế network egress của runner tới đúng service test.

Nếu có thể, dùng mock, service container hoặc môi trường ephemeral để test không cần secret bên ngoài.

### Không tin vào việc secret đã được mask

Masking chỉ giúp che một số giá trị trong log theo cơ chế nền tảng. Nó không ngăn mã độc đọc secret hoặc gửi secret qua mạng. Mã có thể encode, chia nhỏ hoặc biến đổi giá trị trước khi xuất ra. Vì vậy, biện pháp chính là không cấp secret cho job không tin cậy.

### Cẩn thận với reusable workflow

Reusable workflow có thể nhận secret từ caller hoặc được cấu hình kế thừa secret. Không dùng secrets: inherit cho một caller không tin cậy nếu workflow con có quyền rộng. Xác định rõ secret nào được truyền, job nào dùng và điều kiện nào cho phép gọi workflow.

## 8. Chọn runner và mức cách ly

Runner là nơi mã PR được thực thi. Nếu runner lưu credential hoặc có thể truy cập hệ thống nội bộ, quyền của máy có thể quan trọng hơn quyền token trong repository.

### Ưu tiên runner dùng một lần

Với PR từ fork hoặc nguồn chưa được tin cậy, ưu tiên hosted runner tiêu chuẩn hoặc runner ephemeral được tạo riêng cho job. Sau khi job kết thúc, môi trường và storage tạm được thu hồi.

Runner cần có:

- Workspace riêng cho từng job.
- Không có credential production lưu sẵn.
- Không mount thư mục home hoặc socket đặc quyền không cần thiết.
- Network egress được giới hạn theo yêu cầu.
- Không chia sẻ volume chứa dữ liệu giữa job không cùng trust zone.
- Cơ chế dọn file, process và container sau khi chạy.

### Tránh self-hosted runner lâu dài cho PR không tin cậy

Một self-hosted runner chạy lâu dài có thể chứa:

- Token đăng ký runner hoặc credential cloud.
- Cache và workspace của job trước.
- SSH key hoặc file cấu hình nội bộ.
- Kết nối mạng tới database, registry và control plane.
- Quyền truy cập Docker daemon hoặc Kubernetes cluster.

Nếu PR không tin cậy chạy trên máy đó, mã có thể tìm cách đọc dữ liệu hoặc ảnh hưởng job sau. Shell executor đặc biệt nhạy cảm vì lệnh chạy trực tiếp trên host. Container executor cũng không tự bảo đảm cách ly nếu container được privileged, mount Docker socket hoặc có quyền host rộng.

Chỉ sử dụng self-hosted runner cho PR không tin cậy khi đã có thiết kế cách ly phù hợp, runner dùng một lần, không chứa secret lâu dài, không có quyền mạng nhạy cảm và đã kiểm thử ranh giới bảo mật.

### Nhãn runner không phải ranh giới bảo mật duy nhất

Labels/tags chỉ giúp chọn runner. Chúng không thay thế quyền truy cập repository, protected runner, network policy và isolation. Cần cấu hình nền tảng để repository hoặc pipeline không tin cậy không thể yêu cầu một runner đặc quyền chỉ bằng cách thêm nhãn vào YAML.

## 9. Bảo vệ cache khỏi poisoning

Cache giúp tăng tốc dependency và build, nhưng cache có thể chứa dữ liệu do job tạo ra. Nếu job không tin cậy ghi cache mà job phát hành tin cậy đọc lại, dữ liệu giả có thể ảnh hưởng build sau đó.

Các tình huống rủi ro:

- PR ghi file giả vào cache dùng chung.
- Job release khôi phục cache có nội dung do PR tạo.
- Cache chứa executable, script hoặc dependency đã bị thay đổi.
- Cache chứa credential hoặc file cấu hình nhạy cảm.
- Cache key quá rộng khiến nhiều nhánh hoặc trust zone dùng chung dữ liệu.

Biện pháp:

- Tách cache theo trust zone và phạm vi repository/branch.
- Dùng key có hash lock file, toolchain và các đầu vào liên quan.
- Không để job PR ghi vào cache mà release job tin cậy sử dụng.
- Không cache secret, credential hoặc thư mục home.
- Xem cache là dữ liệu có thể bị thay đổi; xác minh dependency bằng lock file và checksum.
- Với release quan trọng, cân nhắc build sạch hoặc chỉ khôi phục cache đã được kiểm soát.

Cơ chế cache scope khác nhau giữa các nền tảng. Cần hiểu rõ job nào có thể đọc và ghi cache nào, đặc biệt với fork PR và merge request pipeline.

## 10. Xem artifact và report từ PR là dữ liệu không tin cậy

Một job PR có thể upload bất kỳ file nào được phép. Artifact đó có thể chứa binary, script, HTML report hoặc file nén được tạo có chủ đích.

Không nên:

- Tải artifact PR rồi chạy script hoặc executable trong job có quyền cao.
- Dùng JAR hoặc container image từ PR làm artifact release.
- Cho workflow deploy tin cậy tự động dùng artifact chỉ dựa vào tên file.
- Giải nén archive không kiểm soát đường dẫn hoặc dung lượng.
- Tin nội dung report HTML có thể chứa script khi hiển thị ở nơi có quyền.

Nếu cần giữ test report để review, hãy lưu ở phạm vi PR và hiển thị theo cách an toàn. Nếu cần artifact phát hành, workflow tin cậy nên build lại từ commit đã merge và tạo artifact mới có digest, provenance rõ ràng.

### Tách namespace artifact

Dùng tên hoặc namespace thể hiện nguồn và mức tin cậy, nhưng không chỉ dựa vào tên để quyết định quyền. Metadata cần bao gồm repository, commit SHA, workflow run, nguồn trigger và digest. Job release phải xác minh những giá trị đó trước khi sử dụng.

## 11. Kiểm soát OIDC và quyền cloud

OIDC cho phép job nhận danh tính ngắn hạn từ nền tảng CI để truy cập cloud hoặc secret manager mà không cần lưu access key dài hạn. Tuy nhiên, nếu trust policy quá rộng, một PR không tin cậy có thể yêu cầu token và nhận credential không mong muốn.

### Chỉ cấp id-token khi job thật sự cần

Trong GitHub Actions, quyền id-token: write cho phép job yêu cầu OIDC token. Không đặt quyền này ở mức workflow cho tất cả job nếu chỉ một job deploy cần.

Ví dụ cấu trúc quyền theo job:

~~~yaml
on:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-24.04
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
      - run: ./gradlew --no-daemon check

  deploy:
    needs: verify
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-24.04
    permissions:
      contents: read
      id-token: write
    environment: production
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - name: Obtain deployment identity
        run: ./scripts/deploy-with-oidc.sh
~~~

Workflow minh họa chỉ chạy khi push lên main. Bước xác thực cloud cụ thể phụ thuộc nhà cung cấp và cần dùng action/CLI đã được review. Job verify không có quyền lấy OIDC token; chỉ job deploy có quyền này và còn chịu bảo vệ của production environment.

### Trust policy phải giới hạn nguồn phát hành

Cloud role nên kiểm tra các claim phù hợp, chẳng hạn:

- Repository hoặc project chính xác.
- Owner hoặc organization.
- Branch hoặc ref được bảo vệ.
- Workflow identity hoặc reusable workflow được phép.
- Environment production nếu dùng environment claim.
- Audience đúng với dịch vụ nhận token.
- Event hoặc loại pipeline được phép, nếu claim và nền tảng hỗ trợ.

Không dùng wildcard quá rộng như mọi repository trong tổ chức hoặc mọi branch nếu quyền được cấp có thể thay đổi hạ tầng production. Hãy thử xác minh token claim từ từng loại sự kiện trước khi bật quyền.

### Approval là một lớp kiểm soát bổ sung

Environment protection, required reviewers và deployment approval giúp kiểm soát thời điểm job được tiếp cận production. Chúng không thay thế việc giới hạn token, runner và source code. Một job được phê duyệt nhưng thực thi mã PR không tin cậy vẫn có thể lạm dụng quyền mà job nhận được.

## 12. Tách workflow PR khỏi workflow phát hành

Một kiến trúc an toàn thường dùng hai loại workflow có quyền khác nhau.

### Workflow PR

- Trigger theo pull_request hoặc merge_request_event.
- Chạy lint, build, unit test và kiểm tra tĩnh.
- Chỉ có quyền đọc source.
- Không có secret production.
- Không có quyền publish hoặc deploy.
- Dùng runner cách ly.
- Artifact và cache được coi là không tin cậy.

### Workflow sau merge

- Trigger từ push vào nhánh được bảo vệ hoặc tag release đã được bảo vệ.
- Checkout commit thực tế đã được merge.
- Build artifact trong môi trường tin cậy.
- Chạy test và security gate bắt buộc.
- Tạo digest, provenance và lưu artifact bất biến.
- Chỉ cấp quyền publish hoặc deploy cho job cần dùng.
- Có approval và xác minh sau triển khai.

Luồng này bảo đảm artifact phát hành được tạo từ commit đã được merge, không phụ thuộc vào một file binary do PR tự upload.

### Cẩn thận với workflow_run

Một workflow tin cậy được kích hoạt sau khi workflow PR hoàn tất có thể chạy với quyền cao hơn workflow ban đầu. Nếu nó tải artifact của PR rồi thực thi, giải nén hoặc sử dụng artifact như mã tin cậy, ranh giới bảo mật đã bị phá vỡ.

Nếu dùng workflow_run:

- Xác minh repository, workflow, event, branch và run ID.
- Không thực thi artifact hoặc script từ workflow không tin cậy.
- Không truyền secret vào bước xử lý nội dung do PR kiểm soát.
- Giới hạn quyền token của workflow sau.
- Tốt nhất chỉ dùng report như dữ liệu cần hiển thị; build lại từ commit đã merge trước khi publish.

## 13. GitLab merge request pipeline và runner

GitLab có shared/instance runners và runner do nhóm tự quản lý. Merge request pipeline có thể chạy mã do nhánh nguồn cung cấp, vì vậy cần kiểm soát variables, runner và quyền job.

Một số điểm cần rà soát:

- Dùng CI/CD variables với phạm vi và quyền phù hợp.
- Không cấp protected variables cho merge request không đáp ứng điều kiện bảo vệ.
- Protected runner chỉ nhận job từ ref được chính sách bảo vệ cho phép; cần kiểm tra điều kiện cụ thể của phiên bản GitLab và cấu hình project/group.
- Không cho merge request từ fork chạy trên runner có quyền truy cập mạng nội bộ hoặc credential production.
- Kiểm tra cài đặt cho phép fork MR pipeline chạy trong parent project, vì ngữ cảnh đó có thể thay đổi tài nguyên và quyền mà pipeline nhìn thấy.
- Không bật quyền ghi hoặc secret chỉ để cho job MR cập nhật repository.
- Dùng environment protected và approval cho deploy.
- Không dùng shell executor trên máy có quyền rộng cho mã MR không tin cậy.

Ví dụ job kiểm tra chỉ dùng runner tag dành cho CI thông thường:

~~~yaml
stages:
  - verify

verify:
  stage: verify
  tags:
    - linux-ci-untrusted
  variables:
    GIT_STRATEGY: clone
  script:
    - ./gradlew --no-daemon check
~~~

Tag linux-ci-untrusted chỉ là ví dụ. Cần đăng ký runner phù hợp, bảo đảm không có secret hoặc quyền nội bộ và cấu hình project không cho job khác tùy tiện sử dụng. Việc dùng clone có thể tạo workspace sạch hơn nhưng không thay thế cách ly host.

GitLab có các thiết lập riêng cho protected variables/runners trong merge request pipeline và thay đổi theo phiên bản. Hãy kiểm tra hành vi thực tế của phiên bản đang vận hành, nhất là khi source branch và target branch thuộc project khác nhau.

## 14. Checklist rà soát workflow trước khi cho PR chạy

### Trigger và quyền

- [ ] PR từ fork chạy bằng trigger phù hợp như pull_request hoặc merge_request_event.
- [ ] Workflow khai báo permissions tối thiểu và không dùng write-all.
- [ ] Job build/test không có quyền ghi repository, publish hoặc deploy.
- [ ] Không cấp secret production cho PR không tin cậy.
- [ ] Không cấp id-token: write nếu job không cần cloud identity.
- [ ] Không dùng secrets: inherit cho workflow được gọi từ nguồn không tin cậy.

### Workflow logic

- [ ] Không dùng pull_request_target để checkout và chạy mã PR.
- [ ] Không nội suy trực tiếp tiêu đề, branch name hoặc nội dung PR vào shell script.
- [ ] Không dùng eval hoặc biến dữ liệu thành mã lệnh.
- [ ] Action, reusable workflow và dependency quan trọng được review/pin theo chính sách.
- [ ] Job có quyền ghi được tách khỏi job thực thi mã PR.

### Runner và tài nguyên

- [ ] PR chạy trên hosted runner hoặc runner tạm thời đã cách ly.
- [ ] Runner không chứa credential lâu dài hoặc workspace cũ.
- [ ] Không mount Docker socket, host path hoặc network nội bộ không cần thiết.
- [ ] Cache được tách theo trust boundary và không chứa secret.
- [ ] Artifact PR không được dùng làm đầu vào phát hành tin cậy.

### Phát hành

- [ ] Release workflow chạy sau merge trên branch/tag được bảo vệ.
- [ ] Artifact được build lại từ commit đã merge.
- [ ] Publish/deploy dùng identity ngắn hạn và quyền giới hạn.
- [ ] Trust policy OIDC giới hạn repository, ref, workflow và environment.
- [ ] Production có approval và audit.
- [ ] Deployment record lưu commit, artifact digest và kết quả xác minh.

## 15. Những anti-pattern cần tránh

| Anti-pattern | Rủi ro | Cách xử lý |
|---|---|---|
| Cấp toàn bộ secret repository cho job PR | Mã PR có thể đọc và gửi secret ra ngoài | Không cấp secret cho job không tin cậy |
| Dùng token write cho toàn workflow | Build script có thể sửa repository hoặc release | Chỉ cấp read permission; tách job ghi |
| Dùng pull_request_target để chạy build PR | Mã PR chạy trong ngữ cảnh có quyền cao | Dùng pull_request cho build/test |
| Chạy PR trên self-hosted runner lâu dài | Có thể chiếm host hoặc đọc dữ liệu job khác | Dùng runner ephemeral, cách ly và không secret |
| Dùng chung cache giữa PR và release | Cache poisoning làm sai build tin cậy | Tách cache scope và xác minh dependency |
| Deploy artifact PR sau khi workflow xanh | Artifact do nguồn không tin cậy tạo ra được phát hành | Build lại sau merge |
| Dùng OIDC trust wildcard | PR có thể nhận cloud credential ngoài dự kiến | Ràng buộc claim theo repo/ref/workflow/environment |
| Nội suy title hoặc branch vào run script | Có nguy cơ command injection | Truyền qua env, quote và validate |
| Dùng workflow_run rồi chạy artifact PR | Quyền cao của workflow sau bị lạm dụng | Không thực thi artifact untrusted |
| Tin vào masking của log | Secret vẫn có thể bị đọc hoặc exfiltrate | Không cấp secret ngay từ đầu |
| Cho mọi job dùng production environment | Tăng bề mặt truy cập và khó audit | Giới hạn environment theo job và approval |

## Kết luận

Pipeline của PR không tin cậy cần được thiết kế như một môi trường thực thi mã bên ngoài ranh giới tin cậy. Hãy cấp token chỉ đọc, không đưa secret production vào job, tránh workflow có quyền cao thực thi mã PR, dùng runner cách ly, tách cache và artifact, đồng thời giới hạn OIDC theo repository, ref và environment. Sau khi PR được review và merge vào nhánh bảo vệ, workflow phát hành mới build lại từ commit tin cậy, tạo artifact có provenance và thực hiện publish/deploy với quyền riêng. Cách phân tách này giúp CI vẫn cung cấp phản hồi nhanh cho người đóng góp mà không mở rộng quyền của họ tới hệ thống phát hành.


