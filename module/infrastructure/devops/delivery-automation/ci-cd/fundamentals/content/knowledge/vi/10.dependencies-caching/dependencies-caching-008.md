# Đảm bảo pipeline vẫn đúng khi cache không có sẵn

Cache trong CI/CD giúp giảm thời gian tải dependency, khôi phục dữ liệu build trung gian và tránh lặp lại những công việc tốn kém. Tuy nhiên, cache có thể bị xóa, hết hạn, không tương thích, hỏng hoặc tạm thời không truy cập được. Vì vậy, **một pipeline đúng phải vẫn build và kiểm thử được khi bắt đầu từ cache rỗng**.

Đây là nguyên tắc quan trọng của **DEVOPS_CI_CD_FUNDAMENTALS**. Pipeline kết nối sự kiện Git với các bước build, kiểm thử, quản lý artifact, môi trường và cổng chất lượng. Cache chỉ hỗ trợ hiệu năng của những bước đó. Nếu kết quả đúng của pipeline phụ thuộc vào việc một cache cụ thể còn tồn tại, pipeline đã có một dependency ẩn và sẽ trở nên khó tái lập.

## 1. Cache là tối ưu hiệu năng, không phải nguồn dữ liệu bắt buộc

Cache là bản sao tạm thời của dữ liệu có thể được tạo hoặc tải lại từ nguồn đáng tin cậy. Trong pipeline, dữ liệu thường được cache gồm:

- Các package hoặc thư viện đã tải từ registry.
- Distribution của công cụ build, chẳng hạn Gradle Wrapper.
- Metadata giúp package manager giải quyết dependency nhanh hơn.
- Kết quả tác vụ build có thể tái sử dụng khi đầu vào không đổi.
- Một số dữ liệu trung gian tốn thời gian tạo lại.

Cache có thể không có vì đây là lần chạy đầu tiên, key thay đổi, cache bị eviction, nhánh không có quyền đọc cache, runner dùng hệ điều hành khác hoặc dịch vụ cache gặp sự cố. Các tình huống đó là bình thường trong vòng đời CI.

Hãy đặt câu hỏi: **Nếu xóa toàn bộ cache và chạy lại pipeline trên cùng commit, kết quả build, test và artifact có còn đúng không?** Nếu câu trả lời là không, cần tìm và loại bỏ sự phụ thuộc ẩn.

Ví dụ:

- Đúng: cache trống thì Gradle tải dependency theo lockfile, sau đó chạy test.
- Sai: cache trống thì job thất bại vì script yêu cầu một file đã từng được tạo trong lần chạy trước.
- Đúng: cache hit giúp test chạy nhanh hơn, cache miss vẫn chạy đủ các bước.
- Sai: bỏ qua test hoặc bỏ qua kiểm tra chất lượng chỉ vì cache hit.

Cache miss không phải lỗi build. Cache service không truy cập được cũng không nên làm hỏng tính đúng đắn của build nếu pipeline có thể lấy lại dữ liệu từ nguồn chính thức. Tuy nhiên, nếu registry hoặc repository nguồn cũng không truy cập được thì pipeline có thể thất bại; cache không tự động trở thành bản sao lưu đầy đủ hay mirror của nguồn đó.

## 2. Phân biệt dependency cache, build cache và artifact

Ba khái niệm này thường bị gộp làm một nhưng có mục đích và yêu cầu lưu trữ khác nhau:

| Loại | Nội dung | Mục tiêu | Có thể mất mà không làm sai kết quả? |
| --- | --- | --- | --- |
| Dependency cache | Package, thư viện, metadata đã tải | Giảm thời gian tải dependency | Có, package manager phải tải lại từ repository |
| Build cache | Đầu ra tác vụ build được lưu theo đầu vào và cấu hình | Tránh thực hiện lại tác vụ có kết quả tương đương | Có, tác vụ phải chạy lại |
| Artifact | JAR, binary, container image, báo cáo test hoặc gói phát hành | Chuyển giao, lưu giữ và phát hành đầu ra đã tạo | Không được xem như dữ liệu tạm; cần lưu theo chính sách |

**Cache không thay thế artifact.** Artifact của một lần build cần được lưu trong kho artifact hoặc registry với định danh có thể truy vết. Không nên dùng cache để chuyển gói phát hành giữa các job hoặc để lưu bằng chứng bắt buộc của một release.

Dependency cache chứa các file có thể tải lại. Build cache có thể chứa đầu ra đã tính toán, nhưng chỉ an toàn khi hệ thống xác định đầy đủ đầu vào, toolchain và các yếu tố ảnh hưởng kết quả. Artifact là đầu ra được pipeline chủ động công bố và quản lý vòng đời.

Ví dụ với Gradle:

- Dependency cache có thể lưu các module đã tải trong Gradle User Home.
- Gradle Build Cache lưu output của task theo cache key được tính từ input và cấu hình task.
- File JAR do task build tạo ra và được phát hành là artifact; nó cần được publish vào kho artifact.

Không nên cache tùy tiện cả thư mục build của dự án rồi giả định các file cũ luôn tương thích với commit mới. Hãy dùng cơ chế build cache chính thức của công cụ, khai báo input/output task đầy đủ và để công cụ quyết định khi nào có thể tái sử dụng kết quả.

## 3. Thiết kế pipeline theo nguyên tắc cold-cache correctness

Cold cache là trạng thái pipeline bắt đầu mà không có dữ liệu cache có thể dùng. Một pipeline đúng cần thực hiện đầy đủ quy trình từ trạng thái này:

1. Checkout đúng commit.
2. Đọc manifest hoặc lockfile của dependency.
3. Khôi phục cache nếu có bản tương thích.
4. Nếu cache thiếu hoặc không dùng được, tải dependency từ repository đã cấu hình.
5. Xác minh dependency và thực hiện build.
6. Chạy kiểm thử và các quality gate.
7. Tạo artifact và lưu kết quả theo quy trình phát hành.
8. Có thể lưu cache mới nếu lần chạy thành công.

Sơ đồ quyết định:

~~~mermaid
flowchart TD
    A["Bắt đầu pipeline tại commit xác định"] --> B["Đọc lockfile và cấu hình toolchain"]
    B --> C["Thử khôi phục cache"]
    C --> D{"Cache có sẵn và tương thích?"}
    D -- "Có" --> E["Dùng dữ liệu cache đã khôi phục"]
    D -- "Không" --> F["Bỏ qua cache và tải dependency"]
    C -. "Cache service lỗi" .-> F
    E --> G["Resolve và xác minh dependency"]
    F --> G
    G --> H["Build và kiểm thử"]
    H --> I{"Các bước bắt buộc đạt?"}
    I -- "Không" --> J["Pipeline thất bại và giữ log"]
    I -- "Có" --> K["Tạo và publish artifact"]
    K --> L["Lưu cache nếu có thể"]
~~~

Điểm quan trọng là cả đường đi có cache và không có cache đều hội tụ về cùng bước resolve dependency, build và kiểm thử. Cache có thể thay đổi thời gian thực thi, nhưng không được thay đổi tiêu chuẩn chất lượng hoặc nội dung đầu ra mong đợi.

### 3.1. Không dùng cache hit làm điều kiện bỏ qua công việc bắt buộc

Một lỗi phổ biến là viết điều kiện kiểu:

~~~yaml
- name: Build
  if: steps.cache.outputs.cache-hit == 'true'
  run: ./gradlew build
~~~

Nếu cache miss, bước build bị bỏ qua và pipeline có thể xanh dù chưa hề build. Điều kiện đó đảo ngược vai trò của cache.

Cách đúng là build luôn chạy:

~~~yaml
- name: Build and test
  run: ./gradlew --no-daemon test
~~~

Package manager hoặc công cụ build tự quyết định dùng dữ liệu đã có hay tải/tạo lại dữ liệu còn thiếu. Nếu muốn hiển thị cache hit/miss, chỉ dùng output để ghi log hoặc đo hiệu năng.

### 3.2. Không chạy chế độ offline khi pipeline cần khả năng cold build

Một số công cụ có chế độ offline. Chế độ này hữu ích khi môi trường đã được chuẩn bị đủ dependency, nhưng sẽ làm cold build thất bại nếu thiếu một package.

Ví dụ với Gradle, lệnh thông thường:

~~~bash
./gradlew --no-daemon test
~~~

cho phép Gradle tải dependency còn thiếu từ repository được cấu hình. Lệnh dùng chế độ offline:

~~~bash
./gradlew --offline test
~~~

chỉ phù hợp khi pipeline chủ động bảo đảm mọi dependency cần thiết đã có sẵn. Không bật offline chỉ để tránh tải lại dependency trong pipeline thông thường. Nếu cần build ngoại tuyến vì yêu cầu môi trường, hãy chuẩn bị và xác minh bộ dependency đầu vào như một phần riêng của quy trình.

## 4. Khóa dependency để cache không làm thay đổi phiên bản

Cache không nên quyết định phiên bản thư viện. Phiên bản phải đến từ manifest, lockfile hoặc quy tắc resolution có thể kiểm soát và review.

Ví dụ:

| Hệ sinh thái | Cách cố định dependency |
| --- | --- |
| Gradle | Dependency locking, version catalog và dependency verification |
| Maven | Khai báo version rõ ràng, quản lý phiên bản qua BOM/parent và kiểm soát repository |
| npm | package-lock.json và npm ci |
| pnpm | pnpm-lock.yaml và pnpm install --frozen-lockfile |
| Yarn | yarn.lock và chế độ immutable phù hợp với phiên bản Yarn |
| Python | Lockfile hoặc file requirements có pin version và hash theo chính sách |

Lockfile xác định đồ thị dependency mà lần build dự kiến sử dụng. Cơ chế checksum hoặc dependency verification giúp phát hiện nội dung package không khớp với giá trị đã tin cậy. Cache chỉ cung cấp bản sao của package; công cụ vẫn phải kiểm tra tính nhất quán theo chính sách.

Với Gradle, có thể bật dependency locking cho các configuration cần thiết và tạo verification metadata. Khi lockfile hoặc verification metadata thay đổi, thay đổi đó cần được review như thay đổi mã nguồn. Với npm, dùng npm ci trong CI để cài theo package-lock.json; lệnh này thất bại nếu package.json và lockfile không đồng bộ, đồng thời tạo môi trường cài đặt xác định hơn npm install.

Không dùng một tag dependency di động hoặc dải version quá rộng rồi dựa vào cache để giữ phiên bản cũ. Khi cache bị xóa, công cụ có thể tải phiên bản mới và tạo ra kết quả khác. Phiên bản phải được khóa độc lập với cache.

## 5. Thiết kế cache key có thể dự đoán

Cache key là định danh cho một nhóm dữ liệu có thể dùng chung. Key tốt cần thay đổi khi nội dung cache không còn tương thích và được giữ ổn định khi dữ liệu vẫn có thể tái sử dụng.

Các thành phần thường cần đưa vào key:

- Hệ điều hành và kiến trúc runner.
- Phiên bản runtime, chẳng hạn JDK hoặc Node.js.
- Package manager hoặc phiên bản công cụ build.
- Lockfile và manifest liên quan đến dependency.
- Các file cấu hình có ảnh hưởng đến resolution.
- Một tiền tố phiên bản do nhóm quản lý để chủ động vô hiệu hóa cache cũ.

Ví dụ key cho Gradle:

~~~text
gradle-v2-linux-jdk21-<hash-cua-lockfiles-va-toolchain>
~~~

Key không nên chỉ dựa trên tên nhánh hoặc commit SHA. Nếu đưa commit SHA vào key, gần như mỗi commit tạo cache mới và mất phần lớn khả năng tái sử dụng. Ngược lại, key quá rộng có thể dùng cache từ runtime hoặc hệ điều hành không tương thích.

### 5.1. Exact key và restore prefix

Một số hệ thống hỗ trợ danh sách restore key. Pipeline có thể thử:

1. Exact key chứa hash lockfile hiện tại.
2. Prefix tương thích với cùng hệ điều hành và runtime.
3. Nếu không tìm được cache phù hợp, bắt đầu từ cache rỗng.

Restore prefix chỉ là cách lấy dữ liệu gần nhất để tiết kiệm thời gian. Nó không chứng minh mọi dependency hiện tại đã có đủ hoặc đúng phiên bản. Package manager vẫn phải resolve theo lockfile và tải những gì thiếu.

Không nên fallback từ Linux sang Windows, từ JDK 21 sang JDK 8 hoặc giữa các kiến trúc khác nhau nếu dữ liệu cache chứa thành phần phụ thuộc môi trường. Chỉ mở rộng phạm vi restore khi đã biết dữ liệu đó tương thích.

### 5.2. Vô hiệu hóa cache có chủ đích

Khi thay đổi cấu trúc cache hoặc phát hiện cache cũ gây lỗi, tăng tiền tố phiên bản, ví dụ từ gradle-v2 sang gradle-v3. Cách này tạo namespace mới mà không cần xóa thủ công mọi cache cũ.

Nếu chỉ thay đổi dependency, hash lockfile nên làm key thay đổi tự động. Nếu thay đổi toolchain, image hoặc cấu hình có ảnh hưởng đến cache, key cũng phải phản ánh thay đổi đó.

## 6. Ví dụ GitHub Actions: cache Gradle nhưng luôn build được khi cache thiếu

Ví dụ dưới đây minh họa cách tách bước restore, build/test và save. Cache action được phép thất bại mà không làm pipeline thất bại; bước build/test vẫn phải chạy và tự resolve dependency.

~~~yaml
name: Java CI

on:
  pull_request:
  push:
    branches:
      - main

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - name: Restore Gradle dependency cache
        id: gradle-cache
        uses: actions/cache/restore@v4
        continue-on-error: true
        with:
          path: |
            ~/.gradle/caches/modules-2
            ~/.gradle/wrapper/dists
          key: gradle-v2-${{ runner.os }}-jdk21-${{ hashFiles('**/*.gradle*', '**/gradle-wrapper.properties', '**/gradle.lockfile', 'gradle/libs.versions.toml', 'gradle/verification-metadata.xml') }}
          restore-keys: |
            gradle-v2-${{ runner.os }}-jdk21-

      - name: Build and test
        run: ./gradlew --no-daemon test

      - name: Save Gradle dependency cache
        if: ${{ success() && steps.gradle-cache.outcome == 'success' && steps.gradle-cache.outputs.cache-hit != 'true' }}
        uses: actions/cache/save@v4
        continue-on-error: true
        with:
          path: |
            ~/.gradle/caches/modules-2
            ~/.gradle/wrapper/dists
          key: ${{ steps.gradle-cache.outputs.cache-primary-key }}
~~~

Trong ví dụ:

- Restore được thử trước khi build. Cache miss là một kết quả bình thường.
- continue-on-error chỉ áp dụng cho thao tác cache. Nếu build hoặc test thất bại, job vẫn thất bại.
- Bước build/test không phụ thuộc output cache-hit nên luôn chạy.
- Gradle tải dependency thiếu từ repository và vẫn dùng lock/verification nếu dự án đã cấu hình.
- Save chỉ chạy sau khi build/test thành công và thao tác restore đã thực thi thành công.
- Cache save cũng không được làm hỏng kết quả build nếu dịch vụ cache gặp sự cố.

Ví dụ dùng các action cache riêng của GitHub Actions. Hãy kiểm tra phiên bản action theo chính sách cập nhật của repository. Cache key và đường dẫn cần điều chỉnh theo toolchain, cấu hình dependency và loại dữ liệu thực sự muốn lưu. Không thêm thư mục chứa secret hoặc file cấu hình có thông tin xác thực vào cache.

## 7. Ví dụ với npm và các package manager khác

Với npm, lockfile là cơ sở để cài dependency xác định. Dù cache npm trống, npm ci vẫn tải các package cần thiết:

~~~yaml
- uses: actions/setup-node@v4
  with:
    node-version-file: .nvmrc
    cache: npm

- name: Install dependencies
  run: npm ci

- name: Run tests
  run: npm test
~~~

Không viết điều kiện chỉ chạy npm ci khi cache hit. Package manager sẽ dùng dữ liệu trong cache nếu phù hợp và tải phần thiếu khi cần. npm ci yêu cầu lockfile nhất quán và không cập nhật lockfile trong quá trình cài.

Với pnpm hoặc Yarn, chọn lệnh cài đặt bất biến tương ứng với phiên bản công cụ và lockfile của repository. Không dùng một lệnh cài đặt tự do trong CI nếu mục tiêu là tái lập đồ thị dependency.

Nếu muốn cache bị lỗi không chặn pipeline, cần kiểm tra semantics của action cache mà nền tảng cung cấp. Với bước restore/save riêng, có thể đặt chính sách cho lỗi cache; không áp dụng chính sách bỏ qua lỗi cho chính lệnh cài dependency hoặc test.

## 8. GitLab CI và các nền tảng khác

GitLab CI hỗ trợ khai báo cache ở cấp job hoặc cấu hình dùng chung. Ví dụ:

~~~yaml
gradle-test:
  image: gradle:8-jdk21
  stage: test
  variables:
    GRADLE_USER_HOME: "$CI_PROJECT_DIR/.gradle"
  cache:
    key:
      files:
        - gradle.lockfile
        - gradle/wrapper/gradle-wrapper.properties
    paths:
      - .gradle/caches/modules-2/
      - .gradle/wrapper/dists/
    policy: pull-push
  script:
    - ./gradlew --no-daemon test
~~~

GRADLE_USER_HOME được đặt trong workspace để các đường dẫn cache tương đối trỏ đúng đến thư mục Gradle sử dụng. Cache được restore trước script theo cấu hình runner. Nếu không có cache phù hợp, Gradle vẫn resolve dependency qua repository. Với nhiều job dùng chung cache, có thể chọn một job cập nhật cache và các job khác chỉ đọc bằng policy pull để giảm ghi đè hoặc cạnh tranh. Hành vi cache thực tế còn phụ thuộc cấu hình GitLab Runner và cache backend.

Các nền tảng khác cũng có cơ chế tương đương:

| Nền tảng | Cơ chế thường dùng | Nguyên tắc giữ tính đúng |
| --- | --- | --- |
| GitHub Actions | actions/cache hoặc cache tích hợp trong setup action | Không gate build/test theo cache hit; cho phép cache step lỗi |
| GitLab CI/CD | cache key, paths, policy | Script vẫn resolve dependency khi cache miss |
| Azure Pipelines | Cache task với key và restore key | Task cache không thay thế lệnh restore/cài dependency |
| Jenkins | Cache plugin, thư mục dùng chung hoặc cache của tool | Không giả định workspace hay agent luôn còn dữ liệu |

Đọc tài liệu đúng phiên bản nền tảng để biết cache miss, cache backend outage, quyền đọc/ghi và phạm vi chia sẻ được xử lý thế nào. Không sao chép nguyên cú pháp của một nền tảng sang nền tảng khác.

## 9. Cache có thể cũ, hỏng hoặc không đáng tin

Cache tồn tại không đồng nghĩa nội dung của nó còn phù hợp. Một cache có thể chứa dữ liệu cũ, file bị cắt, metadata không tương thích hoặc nội dung bị thay đổi ngoài dự kiến.

### 9.1. Cache stale

Cache stale có thể xảy ra khi key không phản ánh đủ đầu vào. Ví dụ, thay đổi JDK nhưng key không chứa phiên bản JDK; thay đổi lockfile nhưng cache key chỉ dựa trên tên nhánh.

Biện pháp:

- Đưa các đầu vào quan trọng vào key.
- Dùng lockfile để xác định dependency.
- Đưa toolchain và hệ điều hành vào key khi dữ liệu phụ thuộc chúng.
- Có tiền tố phiên bản để chủ động làm mới cache.
- Không dùng cache để giữ cấu hình build hoặc secret cần thay đổi theo môi trường.

### 9.2. Cache corrupt

Cache có thể bị hỏng do lần ghi trước bị ngắt, filesystem lỗi hoặc nội dung không hoàn chỉnh. Khi công cụ phát hiện file không hợp lệ, pipeline nên có khả năng loại bỏ dữ liệu đó và tải/tạo lại.

Ví dụ, nếu Gradle báo artifact trong cache bị hỏng, hãy xác định artifact và repository nguồn, xóa đúng cache entry hoặc đổi cache namespace rồi chạy lại resolution. Không xóa bừa mọi thư mục trên runner dùng chung vì có thể ảnh hưởng job khác.

### 9.3. Cache backend unavailable

Nếu dịch vụ cache không truy cập được, pipeline có thể bỏ qua restore/save và tiếp tục. Cách xử lý phụ thuộc action và nền tảng; với bước cache độc lập, có thể đánh dấu lỗi cache là không chặn job.

Chỉ bỏ qua lỗi của thao tác cache. Các lỗi sau vẫn phải làm pipeline thất bại:

- Dependency không thể tải từ repository.
- Checksum hoặc chữ ký package không hợp lệ.
- Lockfile không nhất quán.
- Build hoặc test thất bại.
- Artifact không được tạo hoặc không đạt quality gate.

Nếu tổ chức cần build khi cả cache và repository công cộng đều không truy cập được, cần thiết kế một dependency proxy/mirror hoặc repository nội bộ có độ sẵn sàng và chính sách lưu giữ phù hợp. Đó là nguồn cung cấp dependency được quản lý, không nên nhầm với cache tạm của CI.

## 10. Bảo mật cache và ngăn cache poisoning

Cache có thể chứa package, metadata hoặc output do một pipeline tạo ra. Nếu pipeline không đáng tin cậy có thể ghi vào cache mà job đặc quyền sử dụng, kẻ tấn công có thể tìm cách đưa nội dung độc hại vào luồng build.

Các nguyên tắc bảo vệ:

- Không cache secret, token, private key, file credential hoặc nội dung chứa dữ liệu nhạy cảm.
- Tách cache theo hệ điều hành, runtime và mức độ tin cậy khi cần.
- Không để pipeline từ fork hoặc mã không được review ghi vào cache mà job phát hành tin cậy sử dụng.
- Hạn chế quyền ghi cache; job chỉ cần đọc nên dùng chế độ read-only nếu nền tảng hỗ trợ.
- Xác minh package bằng lockfile, checksum, signature hoặc dependency verification.
- Không chạy script lấy từ cache như thể chúng là mã đã được review.
- Giới hạn thời gian lưu và quyền truy cập cache theo chính sách tổ chức.

Cache không phải ranh giới bảo mật. Nếu một job có thể ghi vào thư mục được job đặc quyền đọc lại, hãy coi nội dung đó là đầu vào không đáng tin cậy cho đến khi được xác minh.

Đặc biệt, không dùng cache từ một pull request không tin cậy để cung cấp binary, script hoặc dependency cho job có secret production. Cần tách phạm vi cache và quyền token giữa kiểm thử mã bên ngoài với quy trình triển khai có đặc quyền.

## 11. Tránh cache quá rộng và cache sai dữ liệu

Cache quá rộng có thể làm tăng thời gian upload/download, gây lỗi tương thích và che giấu vấn đề build. Hãy chỉ lưu dữ liệu thực sự tốn thời gian tải lại hoặc tái tạo.

Nên cache:

- Package manager download cache.
- Gradle/Maven dependency cache phù hợp.
- Công cụ hoặc SDK có phiên bản xác định nếu nền tảng không cung cấp sẵn.
- Build cache chính thức khi task có input/output xác định.

Cần cân nhắc kỹ trước khi cache:

- Thư mục build chứa output phụ thuộc commit hoặc timestamp.
- File log, báo cáo tạm hoặc dữ liệu test có thể tạo lại.
- Workspace đầy đủ của một job.
- Thư mục chứa secret hoặc cấu hình theo môi trường.
- Cache của trình biên dịch có phụ thuộc hệ điều hành/toolchain mà key chưa mô tả.

Cache càng lớn thì thời gian transfer và khả năng gặp lỗi càng cao. Hãy đo tổng thời gian restore, build, save và kích thước cache. Một cache hit không có lợi nếu tải xuống mất nhiều thời gian hơn việc tải lại dependency cần thiết.

## 12. Đo hiệu quả và chẩn đoán

Để biết cache có thực sự giúp pipeline, theo dõi:

- Cache hit rate theo job và theo nhánh.
- Thời gian restore và save.
- Thời gian tải dependency khi cold cache.
- Kích thước cache và tốc độ truyền.
- Tỷ lệ lỗi restore/save và lỗi do cache corrupt.
- Thời gian build/test khi có cache và khi không có cache.

Không tối ưu chỉ số hit rate bằng cách làm key quá rộng. Mục tiêu là tái sử dụng dữ liệu tương thích và giữ cold build đúng. Nếu cache hit rate thấp nhưng cold build nhanh, có thể cache không cần thiết. Nếu cache lớn làm pipeline chậm hơn, hãy thu hẹp paths hoặc thay đổi cách lưu.

Khi pipeline chỉ lỗi lúc cache hit:

1. Thử chạy lại với namespace cache mới hoặc cold cache.
2. So sánh phiên bản toolchain, lockfile và package thực tế.
3. Kiểm tra key có thiếu đầu vào nào không.
4. Kiểm tra dữ liệu cache có bị ghi từ job không đáng tin cậy không.
5. Sửa key hoặc loại dữ liệu cache; sau đó xác minh cả cold build và warm build.

Khi pipeline chỉ lỗi lúc cache miss:

1. Xác minh lệnh cài dependency có thực sự chạy không.
2. Kiểm tra repository URL, DNS, proxy và credential.
3. Xác minh lockfile có đầy đủ và đồng bộ.
4. Kiểm tra có vô tình bật chế độ offline hay không.
5. Xác minh runner có đủ công cụ và quyền ghi vào thư mục cần thiết.

## 13. Checklist bảo đảm pipeline không phụ thuộc cache

**Thiết kế dependency**

- [ ] Dependency được khai báo và khóa phiên bản bằng manifest/lockfile.
- [ ] Có checksum, signature hoặc cơ chế verification phù hợp.
- [ ] Toolchain và package manager được xác định rõ.
- [ ] Repository nguồn có thể truy cập từ runner khi cache trống.

**Thiết kế cache**

- [ ] Cache chỉ chứa dữ liệu có thể tải lại hoặc tái tạo.
- [ ] Key phản ánh hệ điều hành, runtime và lockfile liên quan.
- [ ] Restore prefix chỉ dùng cho dữ liệu tương thích.
- [ ] Cache miss và lỗi cache backend không làm bỏ qua build/test.
- [ ] Cache không chứa secret hoặc dữ liệu nhạy cảm.
- [ ] Job không đáng tin cậy không thể đầu độc cache của job phát hành.

**Xác minh pipeline**

- [ ] Build và test chạy kể cả khi cache hit hoặc miss.
- [ ] Có thể chạy thành công từ cache rỗng.
- [ ] Không dùng offline mode ngoài quy trình đã chuẩn bị dependency.
- [ ] Cache corrupt có cách loại bỏ và tải/tạo lại.
- [ ] Artifact được publish bằng cơ chế artifact/registry riêng.
- [ ] Lỗi build, test, dependency verification và quality gate vẫn làm pipeline thất bại.

## Kết luận

Cache giúp CI/CD nhanh hơn, nhưng không được quyết định pipeline có đúng hay không. Hãy khóa dependency bằng manifest và lockfile, tạo cache key phản ánh các yếu tố tương thích, dùng cache miss như một đường đi bình thường và để package manager tải lại dữ liệu còn thiếu. Khi cache cũ, hỏng hoặc backend không truy cập được, chỉ bỏ qua phần tối ưu cache; build, test và các quality gate vẫn phải thực thi đầy đủ.

Một pipeline đáng tin cậy phải chạy đúng từ trạng thái cold cache, tạo artifact có thể truy vết và phát hiện lỗi dependency thực sự. Khi đó, cache có thể bị xóa hoặc thay thế bất cứ lúc nào mà quy trình CI/CD vẫn giữ được tính đúng đắn và khả năng tái lập.
