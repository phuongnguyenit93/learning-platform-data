# Ghim phiên bản thành phần tái sử dụng và công cụ thực thi

Pipeline as code giúp quy trình CI/CD được lưu trong repository, review như mã nguồn và thực thi tự động. Tuy nhiên, một file pipeline được quản lý bằng Git vẫn có thể cho kết quả khác nhau giữa hai lần chạy nếu nó tham chiếu đến thành phần bên ngoài có thể thay đổi: action, reusable workflow, template, shared library, container image, runner image, compiler hoặc dependency.

**Ghim phiên bản (version pinning)** là khai báo rõ phiên bản hoặc định danh bất biến của các thành phần mà pipeline sử dụng. Mục tiêu là để một lần chạy có thể xác định chính xác mã pipeline, thành phần tái sử dụng và bộ công cụ đã tham gia tạo ra kết quả. Khi một tham chiếu được cập nhật, thay đổi đó trở thành thay đổi có thể review và kiểm soát.

Trong module CI/CD, nguyên lý này hỗ trợ tính nhất quán của build, kiểm thử, artifact và phát hành; đồng thời giảm rủi ro chuỗi cung ứng khi một dependency hoặc action bên ngoài bị thay thế. Ghim phiên bản không loại bỏ nhu cầu cập nhật. Nó tạo ra một điểm kiểm soát rõ ràng để nhóm chủ động đánh giá và nâng cấp.

## 1. Những gì cần được ghim phiên bản

Pipeline thường phụ thuộc vào nhiều lớp thành phần. Một danh sách kiểm kê nên bao gồm:

| Thành phần | Ví dụ | Cách định danh nên cân nhắc |
|---|---|---|
| Action hoặc plugin CI | Git checkout action, cache action, scanner action | Commit SHA đầy đủ hoặc phiên bản bất biến đã xác minh |
| Reusable workflow/template | Workflow dùng chung, CI template, pipeline component | Commit SHA hoặc release version bất biến |
| Shared library | Jenkins Shared Library, thư viện script nội bộ | Tag phát hành bất biến hoặc commit SHA |
| Container image | Image chứa tool build, scanner hoặc deploy client | Image digest, có thể kèm tag dễ đọc |
| Runner/executor image | Image máy chạy job hoặc build agent | Digest hoặc phiên bản image đã quản lý |
| Compiler và runtime | JDK, Node.js, Python, .NET SDK | Phiên bản cụ thể, kể cả patch khi cần |
| Build tool | Gradle, Maven, npm, pnpm, Docker BuildKit | Wrapper hoặc phiên bản cụ thể cùng checksum nếu hỗ trợ |
| Dependency ứng dụng | Thư viện trực tiếp và bắc cầu | Lockfile, checksum và quy tắc cập nhật |
| Bộ quy tắc kiểm tra | Linter, formatter, policy bundle, scanner database | Phiên bản hoặc snapshot có ghi nhận |

Không phải thành phần nào cũng có một kiểu định danh giống nhau. Với mã nguồn, commit SHA thường xác định chính xác revision. Với container image, digest xác định nội dung image. Với runtime, cần ghim phiên bản phát hành của runtime và cân nhắc cách runner cung cấp bản vá hệ điều hành. Với dependency, lockfile và checksum giúp xác định gói thực tế được tải.

## 2. Tag, version và định danh bất biến

Các tham chiếu thường gặp có mức độ ổn định khác nhau:

- `latest`, `main`, `stable` hoặc tên nhánh là tham chiếu di động. Nội dung có thể đổi mà pipeline không cần sửa.
- Tag như `v3` hoặc `1.8.0` dễ đọc và tiện nâng cấp, nhưng độ bất biến phụ thuộc chính sách của nơi phát hành. Một số hệ thống cho phép di chuyển tag.
- Commit SHA đầy đủ xác định một revision cụ thể của repository. Khi dùng để pin mã nguồn, nên dùng toàn bộ SHA mà nền tảng yêu cầu thay vì SHA rút gọn.
- Digest như `sha256:...` xác định nội dung của container image hoặc đối tượng hỗ trợ content-addressing.
- Checksum của package hoặc file tải về giúp xác minh nội dung đúng với giá trị đã công bố hoặc lưu trong manifest tin cậy.

Ví dụ, `tool-image:2.4` cho người đọc biết phiên bản dự kiến, nhưng nếu tag bị ghi đè thì cùng tham chiếu có thể trả về image khác. Tham chiếu `tool-image@sha256:...` xác định nội dung cụ thể. Có thể ghi cả tag và digest để vừa dễ đọc vừa bảo đảm định danh.

Ghim vào một commit SHA hoặc digest giúp xác định đầu vào, nhưng không tự chứng minh đầu vào đó an toàn. Trước khi pin, cần xác minh repository nguồn, nhà phát hành, nội dung commit, chữ ký hoặc provenance khi có. Một phiên bản độc hại được pin chính xác vẫn là một phiên bản độc hại.

## 3. Ghim action và reusable workflow trong GitHub Actions

Với GitHub Actions, một action có thể được tham chiếu bằng tag hoặc commit SHA. Đối với pipeline cần kiểm soát chặt, nên pin bằng full-length commit SHA và ghi chú tag phát hành tương ứng để người review hiểu phiên bản đang dùng.

Ví dụ dưới đây dùng giá trị placeholder để minh họa cấu trúc; cần thay bằng SHA đã xác minh từ repository chính thức:

```yaml
name: verify

on:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout source
        uses: actions/checkout@<FULL_40_CHARACTER_COMMIT_SHA> # vX.Y.Z

      - name: Set up Java
        uses: actions/setup-java@<FULL_40_CHARACTER_COMMIT_SHA> # vX.Y.Z
        with:
          distribution: temurin
          java-version: '21.0.x'

      - name: Run tests
        run: ./gradlew test
```

Đoạn mã chỉ minh họa cách pin action. Phiên bản Java `21.0.x` vẫn cho phép nhận các bản patch trong dòng 21; nếu yêu cầu build phải cố định tuyệt đối, cần chọn phiên bản patch cụ thể và kiểm soát cả image/runner cung cấp JDK. Việc pin action không tự pin runtime mà action cài đặt.

Reusable workflow cũng là dependency. Khi gọi workflow từ repository khác, dùng ref bất biến theo chính sách tổ chức, ưu tiên commit SHA đầy đủ khi cần xác định chính xác nội dung:

```yaml
jobs:
  verify:
    uses: owner/ci-workflows/.github/workflows/java-verify.yml@<FULL_COMMIT_SHA>
    with:
      java-version: '21'
```

Khi workflow dùng chung thay đổi, repository tiêu thụ không nên tự động nhận thay đổi đó ngoài ý muốn. Nhóm phát hành một version mới hoặc commit mới, review tác động, rồi cập nhật ref trong repository sử dụng. Nếu workflow có `workflow_call` inputs hoặc secrets, cần kiểm tra hợp đồng đầu vào, quyền token và quyền truy cập secret khi nâng cấp.

## 4. Ghim template, component và shared library ở nền tảng khác

Các nền tảng CI/CD có cú pháp riêng, nhưng nguyên lý giống nhau: tham chiếu đến một revision đã xác định và review thay đổi ref khi nâng cấp.

**GitLab CI/CD** có thể include file từ project khác. Ví dụ mã giả:

```yaml
include:
  - project: platform/ci-templates
    ref: '<FULL_COMMIT_SHA>'
    file: '/templates/java-build.yml'

stages:
  - verify
  - package
```

`ref` có thể là branch, tag hoặc commit tùy cách include. Branch như `main` là tham chiếu di động; tag có thể được bảo vệ theo chính sách nhưng vẫn cần hiểu khả năng thay đổi của hệ thống. Với template quan trọng, pin commit SHA giúp pipeline tiêu thụ một nội dung đã xác định. GitLab CI/CD components cũng nên dùng version được phát hành và quản lý theo quy tắc bất biến của catalog.

**Jenkins Shared Library** có thể được nạp với version cụ thể. Ví dụ minh họa:

```groovy
@Library('company-ci-library@v2.3.1') _

pipeline {
    agent any
    stages {
        stage('Verify') {
            steps {
                runStandardVerification()
            }
        }
    }
}
```

Ở đây `v2.3.1` chỉ an toàn như một mốc cố định nếu chính sách repository ngăn việc di chuyển hoặc ghi đè tag. Với môi trường yêu cầu truy vết nghiêm ngặt, cấu hình SCM có thể tham chiếu commit SHA. Cần kiểm tra cách Jenkins cấu hình default version, override version và cache thư viện để tránh vô tình nạp nhánh mặc định.

Các ví dụ trên là mẫu khái niệm; cú pháp và khả năng pin cụ thể phụ thuộc phiên bản nền tảng, plugin và cấu hình quản trị đang sử dụng.

## 5. Ghim container image và runner/executor

Job CI thường chạy trong container image chứa shell, SDK, scanner hoặc công cụ triển khai. Nếu image được tham chiếu bằng tag di động, một lần chạy sau có thể nhận bộ công cụ khác dù file pipeline không đổi.

Ví dụ:

```yaml
jobs:
  build:
    container:
      image: registry.example.com/ci/java-toolchain:21@sha256:<IMAGE_DIGEST>
    steps:
      - run: ./gradlew clean test
```

Tag `21` giúp người đọc nhận biết mục đích; digest xác định nội dung image. Digest cần được lấy từ registry đáng tin cậy và cập nhật có chủ đích. Nếu image cần bản vá bảo mật, phát hành digest mới, đánh giá thay đổi và cập nhật pipeline qua review.

Runner cũng là một phần của môi trường thực thi. Hosted runner có thể được nhà cung cấp cập nhật image, kernel, công cụ cài sẵn và package mà không cần thay đổi workflow. Nhãn như `ubuntu-latest` có thể chuyển sang một bản Ubuntu mới theo lịch của nhà cung cấp. Khi cần độ ổn định cao hơn, cân nhắc runner tự quản lý với image đã pin, container job theo digest hoặc runner group được kiểm soát. Dù dùng hosted runner, nên ghi lại image/runner version thực tế để hỗ trợ điều tra.

Không phải mọi thuộc tính của máy chạy đều có thể pin chỉ bằng `runs-on`. Nếu nền tảng cung cấp runner image version hoặc immutable image reference, dùng cơ chế đó; nếu không, cần coi image hosted là một đầu vào có thể thay đổi và kiểm thử định kỳ với cập nhật của nhà cung cấp.

## 6. Ghim compiler, runtime, build tool và dependency

Pin action nhưng để compiler hoặc dependency trôi nổi vẫn có thể làm build thay đổi. Một quy trình ổn định cần quản lý cả toolchain:

- Dùng Gradle Wrapper hoặc Maven Wrapper để repository xác định phiên bản build tool. Với Gradle Wrapper, kiểm tra distribution URL và cấu hình checksum phân phối nếu quy trình hỗ trợ.
- Khai báo Java toolchain và phiên bản JDK cụ thể phù hợp với chính sách tương thích; ghi nhận vendor và patch version khi cần.
- Dùng lockfile cho dependency và plugin khi hệ sinh thái hỗ trợ; tránh version range hoặc dependency động trong pipeline phát hành.
- Pin base image, compiler image và công cụ đóng gói; xác minh checksum hoặc chữ ký của file tải về.
- Ghi nhận biến môi trường build có ảnh hưởng đến đầu ra, locale, timezone và tham số kiến trúc khi chúng quan trọng.

Ví dụ cấu hình Gradle minh họa Java toolchain:

```kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Đoạn cấu hình khóa major version của toolchain theo yêu cầu build; nó không nhất thiết khóa patch release hoặc vendor. Muốn kiểm soát chặt hơn, runner/container image cần cung cấp JDK cụ thể và pipeline nên ghi nhận phiên bản thực tế bằng `java -version`.

Dependency lockfile cũng cần được review. Lockfile xác định phiên bản giải quyết cho một lần cài đặt, nhưng không thay thế kiểm tra checksum, nguồn tải và chính sách bảo mật. Với package manager hỗ trợ integrity hash, giữ và xác minh các hash đó. Không nên tắt xác minh TLS hoặc checksum để khắc phục lỗi tải dependency.

## 7. Kết hợp pinning với bảo mật chuỗi cung ứng

Ghim phiên bản giúp xác định thành phần, còn kiểm soát chuỗi cung ứng giúp đánh giá thành phần đó có đáng tin hay không. Một số thực hành cần kết hợp:

1. Chỉ lấy action, template, library và image từ nguồn được tổ chức phê duyệt.
2. Xác minh commit, tag ký số, image signature hoặc provenance khi nhà phát hành cung cấp.
3. Giới hạn quyền của token CI và chỉ cấp secret cho job thực sự cần.
4. Dùng quyền đọc cho dependency và registry ở job tiêu thụ; tách quyền publish khỏi quyền build thông thường khi phù hợp.
5. Quét dependency và image theo chính sách; gắn kết quả scan với digest hoặc revision đã kiểm tra.
6. Ghi nhận nguồn, phiên bản và định danh nội dung trong log hoặc build provenance.
7. Theo dõi cảnh báo bảo mật và khả năng bị xâm phạm của dependency đã pin.

Một SHA cố định ngăn ref tự trôi sang commit khác, nhưng không ngăn commit được pin chứa mã độc hoặc lỗ hổng. Nếu một action bị phát hiện xâm phạm, nhóm phải chủ động thay ref sang bản an toàn, kiểm tra lịch sử sử dụng và đánh giá artifact được tạo trong khoảng thời gian bị ảnh hưởng.

## 8. Cập nhật phiên bản có kiểm soát

Pin mọi thứ rồi không cập nhật sẽ khiến pipeline ổn định trong ngắn hạn nhưng tích tụ lỗ hổng và nợ kỹ thuật. Vì vậy, pinning phải đi cùng quy trình nâng cấp:

1. **Kiểm kê:** tạo danh sách action, workflow, template, shared library, image, runner và toolchain đang được dùng.
2. **Theo dõi:** nhận thông báo release, advisory bảo mật và vòng đời hỗ trợ của từng thành phần.
3. **Đề xuất cập nhật:** bot hoặc người phụ trách mở pull request thay đổi ref, digest hoặc phiên bản.
4. **Review thay đổi:** đọc release notes, diff, breaking changes, yêu cầu quyền mới và thay đổi hành vi.
5. **Chạy pipeline xác minh:** test trên revision cập nhật, kiểm tra bảo mật và so sánh artifact hoặc kết quả khi cần.
6. **Promote dần:** cập nhật ở repository thử nghiệm hoặc nhóm dự án nhỏ trước khi áp dụng rộng.
7. **Lưu khả năng quay lui:** giữ ref trước đó và ghi lại cách trở về bản ổn định nếu phát hiện vấn đề.

Với lỗ hổng nghiêm trọng, thời gian nâng cấp cần theo SLA bảo mật thay vì chờ chu kỳ định kỳ. Tuy nhiên, ngay cả bản vá khẩn cấp cũng cần xác minh nguồn, kiểm tra tương thích và ghi nhận ai phê duyệt.

## 9. Tính tái lập và giới hạn của version pinning

Pin phiên bản làm giảm biến động của đầu vào nhưng không bảo đảm hai lần chạy tạo ra byte đầu ra giống hệt nhau. Kết quả còn có thể phụ thuộc thời gian, thứ tự file, random seed, trạng thái mạng, dữ liệu bên ngoài, hệ điều hành, kernel, locale, cache hoặc dịch vụ từ xa.

Phân biệt ba mục tiêu:

- **Version pinning:** cố định phiên bản hoặc định danh của thành phần phụ thuộc.
- **Reproducible build:** cùng đầu vào được kiểm soát có thể tạo ra đầu ra giống nhau theo định nghĩa của dự án.
- **Traceability:** có thể xác định chính xác đầu vào, công cụ, lần chạy và artifact đã tạo ra kết quả.

Ba mục tiêu bổ trợ nhau. Một pipeline có pinning và traceability tốt vẫn có thể không reproducible nếu build phụ thuộc thời gian hoặc dịch vụ ngoài. Khi cần reproducible build, cần bổ sung quy tắc về đầu vào không xác định, môi trường cô lập, timestamp, thứ tự đóng gói và xác minh checksum của đầu ra.

Hosted runner, dịch vụ SaaS, registry và advisory database có thể thay đổi theo cách không thể pin hoàn toàn từ file pipeline. Hãy xác định rõ phần nào được cố định, phần nào được nhà cung cấp quản lý và cách ghi nhận phiên bản thực tế. Không tuyên bố pipeline hoàn toàn bất biến nếu các đầu vào quan trọng vẫn do dịch vụ bên ngoài cập nhật tự động.

## 10. Checklist review pipeline

Trước khi merge thay đổi pipeline hoặc phát hành template dùng chung, hãy kiểm tra:

- [ ] Không dùng nhánh hoặc tag di động cho thành phần quan trọng nếu cần định danh bất biến.
- [ ] Action và reusable workflow được pin bằng ref đã xác minh; ghi chú version để người review đọc được.
- [ ] Template, component và shared library có version phát hành rõ ràng và chính sách chống ghi đè.
- [ ] Container image được tham chiếu bằng digest khi cần kiểm soát nội dung.
- [ ] Runner image và runtime/toolchain được kiểm soát hoặc ghi nhận phiên bản thực tế.
- [ ] Build tool wrapper, lockfile và checksum được review cùng mã nguồn.
- [ ] Nguồn dependency, chữ ký/provenance và quyền truy cập được xác minh theo chính sách.
- [ ] Quy trình cập nhật có release notes, test, approval và kế hoạch rollback.
- [ ] Không có secret hoặc token quyền rộng bị đưa vào workflow dùng chung.
- [ ] Có cách kiểm kê và phát hiện thành phần hết hỗ trợ hoặc có advisory bảo mật.

Ghim phiên bản biến dependency của pipeline thành những đầu vào có thể nhìn thấy và review. Khi kết hợp định danh bất biến, kiểm soát nguồn, quản lý toolchain và lịch cập nhật có trách nhiệm, nhóm có thể hiểu vì sao pipeline tạo ra một kết quả, tái hiện sự cố dễ hơn và nâng cấp thành phần mà vẫn giữ được khả năng truy vết.
