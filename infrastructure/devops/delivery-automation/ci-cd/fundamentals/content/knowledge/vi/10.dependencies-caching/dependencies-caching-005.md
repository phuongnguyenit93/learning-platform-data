# Thiết kế khóa cache theo đầu vào và môi trường phù hợp

Cache giúp pipeline CI/CD tránh tải lại dependency hoặc tính toán lại những kết quả đã có, nhờ đó rút ngắn thời gian build và giảm tải cho package registry. Tuy nhiên, cache chỉ hữu ích khi pipeline khôi phục đúng dữ liệu cho đúng đầu vào. Nếu khóa cache quá chung, job có thể nhận dữ liệu từ môi trường hoặc cấu hình không tương thích. Nếu khóa quá cụ thể, cache hiếm khi được dùng lại và gần như không tạo ra lợi ích.

Thiết kế cache tốt bắt đầu bằng việc xác định **dữ liệu nào có thể tái sử dụng, những đầu vào nào làm dữ liệu đó thay đổi và môi trường nào có thể dùng chung dữ liệu**. Khóa cache cần phản ánh các yếu tố đó, đồng thời có cơ chế fallback an toàn và giới hạn phạm vi chia sẻ.

## 1. Cache trong pipeline dùng để làm gì?

Cache là vùng lưu trữ tạm thời để tái sử dụng dữ liệu giữa các lần chạy pipeline. Các dữ liệu thường được cache gồm:

- Package đã tải từ Maven, Gradle, npm, pnpm, pip hoặc NuGet.
- Metadata và index của package repository.
- Dependency đã giải nén hoặc wheel phù hợp với môi trường.
- Kết quả build trung gian nếu hệ thống build cache hỗ trợ xác định đầu vào.
- Cache của compiler hoặc công cụ phân tích tĩnh.

Ví dụ, một dự án Java có thể phải tải hàng trăm dependency ở lần build đầu tiên. Nếu lưu local Maven repository, lần chạy sau có thể dùng lại nhiều package đã tải, chỉ cần lấy các dependency còn thiếu hoặc đã thay đổi.

Cần phân biệt ba loại dữ liệu:

| Loại dữ liệu | Mục đích | Cách quản lý |
|---|---|---|
| Dependency cache | Giữ package và metadata để tránh tải lại | Khóa theo manifest/lockfile và môi trường |
| Build cache | Giữ kết quả tính toán trung gian có thể tái sử dụng | Khóa theo toàn bộ đầu vào ảnh hưởng kết quả |
| Artifact phát hành | Sản phẩm đã build để kiểm thử hoặc triển khai | Lưu như artifact có định danh, digest và retention riêng |

Cache không phải nguồn lưu trữ chính thức của sản phẩm phát hành. Nếu cần triển khai hoặc rollback một phiên bản, phải dùng artifact đã được quản lý và xác minh, không dựa vào một thư mục cache có thể bị xóa hoặc thay thế.

Cache cũng không được bảo đảm tồn tại mãi mãi. Nền tảng có thể xóa cache theo chính sách dung lượng, thời gian không sử dụng hoặc giới hạn quota. Pipeline phải luôn có khả năng chạy lại từ đầu khi cache không tồn tại.

## 2. Khóa cache là gì?

Cache key là định danh mà pipeline dùng để tìm một bản cache phù hợp. Khi khôi phục cache, nền tảng so sánh key của lần chạy với các cache đã lưu theo quy tắc của nền tảng.

Một khóa cache tốt phải cân bằng hai yêu cầu:

- **Tính tương thích:** chỉ dùng lại cache khi dữ liệu bên trong có thể được sử dụng an toàn với đầu vào hiện tại.
- **Khả năng tái sử dụng:** không đưa những giá trị thay đổi ở mọi lần chạy vào key nếu chúng không ảnh hưởng đến nội dung cache.

Có thể hình dung key theo cấu trúc:

~~~text
<cache-schema>-<os>-<arch>-<toolchain>-<package-manager>-<dependency-input-hash>
~~~

Ví dụ:

~~~text
deps-v3-linux-x64-jdk21-maven-<pom-hash>
~~~

Trong đó:

- `deps-v3`: phiên bản cấu trúc cache; tăng số này khi thay đổi cách tổ chức hoặc cần vô hiệu hóa cache cũ.
- `linux-x64`: hệ điều hành và kiến trúc.
- `jdk21`: phiên bản runtime hoặc toolchain.
- `maven`: hệ sinh thái package manager.
- `pom-hash`: dấu băm của các file khai báo dependency và cấu hình có ảnh hưởng.

Đây là cấu trúc khái niệm. Cú pháp và cách nền tảng tìm cache có thể khác nhau. Điều quan trọng là từng thành phần phải có lý do: nó thay đổi thì nội dung cache có thể không còn tương thích.

## 3. Chọn đầu vào đưa vào cache key

Không có một danh sách cố định phù hợp với mọi dự án. Hãy bắt đầu từ câu hỏi: **nếu giá trị này thay đổi, cache hiện tại có còn dùng được không?**

Các nhóm đầu vào thường cần xem xét:

| Nhóm đầu vào | Ví dụ | Khi nào cần đưa vào key? |
|---|---|---|
| Hệ điều hành | Linux, Windows, macOS | Khi cache chứa dữ liệu phụ thuộc hệ điều hành |
| Kiến trúc CPU | x64, ARM64 | Khi package hoặc binary phụ thuộc kiến trúc |
| Runtime | JDK 17/21, Node 20/22, Python 3.11/3.12 | Khi dependency hoặc kết quả build phụ thuộc phiên bản |
| Package manager | Maven, Gradle, npm, pnpm, pip | Khi cache có định dạng hoặc vị trí riêng |
| Phiên bản package manager | Maven 3.x, npm 10, pnpm 9 | Khi metadata hoặc cách giải quyết dependency thay đổi |
| Manifest/lockfile | pom.xml, package-lock.json, poetry.lock | Khi tập dependency thay đổi |
| Cấu hình build | profile, compiler flags, feature flags | Khi làm thay đổi package hoặc kết quả build |
| ABI và thư viện hệ thống | glibc, OpenSSL, native toolchain | Khi cache có binary native phụ thuộc môi trường |
| Phạm vi dự án | service-a, service-b trong monorepo | Khi mỗi module có dependency riêng |

### 3.1. Ưu tiên lockfile hoặc manifest có kiểm soát

Lockfile là đầu vào quan trọng vì nó ghi nhận phiên bản dependency đã được phân giải. Ví dụ:

- npm: `package-lock.json` hoặc `npm-shrinkwrap.json`.
- pnpm: `pnpm-lock.yaml`.
- Yarn: `yarn.lock`.
- Python: `poetry.lock`, `uv.lock` hoặc lockfile của công cụ đang dùng.
- Gradle: dependency lockfiles nếu dự án bật dependency locking.
- Maven: thường dùng `pom.xml`, parent POM, BOM và cấu hình Maven có liên quan; Maven không tự tạo một lockfile chuẩn tương đương package-lock.json.

Nếu lockfile thay đổi, key cần thay đổi để pipeline không coi cache cũ là hoàn toàn tương ứng với dependency graph mới. Package manager vẫn phải thực hiện bước xác minh và phân giải dependency theo manifest/lockfile hiện tại.

Với Maven, nếu dependency dùng version động như `LATEST`, version range hoặc SNAPSHOT có thể thay đổi, chỉ hash POM chưa chắc mô tả đầy đủ trạng thái dependency từ repository. Nên pin version, quản lý dependency có kiểm soát và hiểu chính sách cập nhật metadata của Maven.

### 3.2. Chỉ hash file có liên quan

Nếu một repository có nhiều module, không nhất thiết mọi cache phải phụ thuộc vào toàn bộ lockfile trong repository. Có thể tạo cache riêng cho từng service hoặc module để thay đổi ở module A không làm mất cache của module B.

Ví dụ, một monorepo có:

~~~text
repo/
├── services/
│   ├── billing/
│   │   └── package-lock.json
│   └── catalog/
│       └── package-lock.json
└── tools/
    └── package-lock.json
~~~

Cache cho billing nên hash lockfile và cấu hình có ảnh hưởng đến dependency của billing. Nếu hash tất cả lockfile, thay đổi dependency ở catalog cũng làm cache billing bị miss dù hai module độc lập.

Tuy nhiên, nếu dự án dùng workspace chung, lockfile ở root có thể điều khiển dependency của nhiều module. Khi đó, hash lockfile gốc là hợp lý. Cần hiểu cách package manager giải quyết workspace trước khi chia key.

## 4. Đưa môi trường vào cache key

Cùng một dependency declaration có thể tạo ra dữ liệu cache khác nhau trên các môi trường khác nhau.

Ví dụ:

- Package có binary native có thể khác giữa Linux x64 và macOS ARM64.
- Python wheel có thể phụ thuộc phiên bản Python, ABI, hệ điều hành và kiến trúc.
- Node native addon có thể phụ thuộc Node ABI và toolchain biên dịch.
- Java dependency thường độc lập với hệ điều hành hơn, nhưng build cache hoặc native library vẫn có thể phụ thuộc JDK, OS và kiến trúc.
- Gradle hoặc compiler cache có thể phụ thuộc phiên bản công cụ, compiler flags và cấu hình build.

Do đó, hãy đưa vào key những yếu tố môi trường thực sự ảnh hưởng đến dữ liệu được lưu. Với package thuần Java tải từ Maven Central, có thể không cần tách cache theo mọi biến môi trường nếu package manager và nội dung cache tương thích. Nhưng nếu cache chứa native output hoặc build output, cần key chặt hơn.

Một ví dụ key cho Python wheel cache có thể bao gồm:

~~~text
pip-v2-linux-x64-cp312-<lock-hash>
~~~

Trong đó `cp312` biểu thị CPython 3.12. Nếu wheel chứa binary phụ thuộc ABI hoặc thư viện hệ thống, cần xem xét thêm môi trường tương ứng.

Không nên đưa mọi biến môi trường vào key một cách máy móc. Các giá trị như tên job, run ID, thời điểm chạy hoặc commit SHA thường làm key thay đổi liên tục mà không giúp tăng tính tương thích. Chỉ thêm chúng khi chúng thực sự ảnh hưởng đến nội dung cache hoặc khi chủ đích là tạo cache riêng cho từng lần chạy.

## 5. Phiên bản hóa cache và chủ động vô hiệu hóa

Cache cần có một thành phần phiên bản do nhóm kiểm soát, thường gọi là cache schema version hoặc cache epoch.

Ví dụ:

~~~text
deps-v1-linux-x64-jdk21-<hash>
deps-v2-linux-x64-jdk21-<hash>
~~~

Khi chuyển cấu trúc thư mục cache, đổi công cụ, thay cách lưu dữ liệu hoặc phát hiện cache cũ không còn tương thích, tăng từ v1 lên v2 để tạo namespace mới.

Một số lý do cần tăng phiên bản cache:

- Thay đổi định dạng dữ liệu hoặc cấu trúc thư mục.
- Thay package manager hoặc cách quản lý dependency.
- Thay đổi phiên bản toolchain có ảnh hưởng đến cache.
- Phát hiện cache cũ bị hỏng hoặc chứa metadata không còn hợp lệ.
- Cần vô hiệu hóa một nhóm cache sau sự cố.

Không nên tăng phiên bản cache sau mỗi commit. Việc đó khiến pipeline mất khả năng tái sử dụng và phải tải lại toàn bộ dependency. Phiên bản cache chỉ nên thay đổi khi có lý do về tương thích hoặc quản trị.

Cũng không nên dùng timestamp làm thành phần key cho cache dependency thông thường. Nếu key có thời gian chạy, mỗi lần chạy sẽ tạo một cache mới và gần như không có cache hit.

## 6. Exact key, restore key và fallback

Một số nền tảng cho phép khai báo danh sách restore key. Cơ chế này giúp khôi phục một cache gần đúng khi không tìm thấy key chính xác.

Ví dụ key chính:

~~~text
npm-v3-linux-x64-node22-<lock-hash>
~~~

Các restore key có thể giảm dần độ cụ thể:

~~~text
npm-v3-linux-x64-node22-
npm-v3-linux-x64-
~~~

Trình tự khôi phục thường là:

1. Tìm cache khớp chính xác key.
2. Nếu không có, thử các restore key theo thứ tự.
3. Nếu tìm được cache theo prefix, khôi phục cache gần nhất phù hợp theo quy tắc của nền tảng.
4. Chạy package manager để xác minh và tải phần dependency còn thiếu.
5. Khi cần, lưu cache mới dưới key chính xác của lần chạy hiện tại.

Cần hiểu rõ semantics của nền tảng đang dùng. Một số hệ thống coi restore key là prefix, một số có quy tắc scope và thứ tự tìm kiếm riêng. Không nên giả định mọi CI đều hoạt động giống nhau.

Fallback chỉ nên nới lỏng những yếu tố mà package manager có thể xử lý an toàn. Ví dụ, có thể fallback giữa các lock hash khác nhau trong cùng OS, kiến trúc và runtime nếu cache chỉ là kho package tải về và package manager luôn xác minh package cần dùng. Không nên fallback từ Linux sang Windows hoặc từ Python 3.12 sang 3.8 nếu cache chứa binary phụ thuộc môi trường.

**Không bỏ các thành phần môi trường quan trọng khỏi restore key chỉ để tăng cache hit.** Cache hit cao nhưng dữ liệu không tương thích có thể gây lỗi khó tái hiện.

## 7. Ví dụ: cache dependency với GitHub Actions

### 7.1. Maven

Với dự án Maven, GitHub Actions có thể dùng cache tích hợp trong action setup-java:

~~~yaml
name: Java CI

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Java and Maven cache
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven
          cache-dependency-path: |
            **/pom.xml
            .mvn/wrapper/maven-wrapper.properties

      - name: Verify
        run: ./mvnw --batch-mode verify
~~~

Ở đây, cache được gắn với hệ sinh thái Maven và các file dependency được chỉ định. Với monorepo hoặc cấu hình Maven phức tạp, cần điều chỉnh cache-dependency-path để bao gồm parent POM, BOM hoặc file cấu hình có ảnh hưởng đến dependency resolution.

Maven local repository thường nằm trong `~/.m2/repository`. Không nên cache toàn bộ thư mục home vì có thể vô tình đưa cấu hình người dùng hoặc dữ liệu nhạy cảm vào cache.

### 7.2. npm

Với Node.js, action setup-node có thể cache dữ liệu package manager:

~~~yaml
name: Node CI

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: npm
          cache-dependency-path: web/package-lock.json

      - name: Install dependencies
        working-directory: web
        run: npm ci

      - name: Run tests
        working-directory: web
        run: npm test
~~~

Với npm, cache tích hợp thường lưu package data của npm. Nó không đồng nghĩa với việc cache toàn bộ `node_modules`. Lệnh `npm ci` cài dependency theo lockfile và tái tạo thư mục cài đặt phù hợp với dự án. Không nên bỏ qua npm ci chỉ vì cache đã được khôi phục.

### 7.3. Dùng actions/cache trực tiếp

Khi cần kiểm soát key rõ hơn, có thể dùng action cache trực tiếp. Ví dụ sau minh họa cache Maven repository:

~~~yaml
- name: Restore Maven dependencies
  uses: actions/cache@v4
  with:
    path: ~/.m2/repository
    key: deps-v3-${{ runner.os }}-${{ runner.arch }}-jdk21-maven-${{ hashFiles('**/pom.xml', '.mvn/wrapper/maven-wrapper.properties') }}
    restore-keys: |
      deps-v3-${{ runner.os }}-${{ runner.arch }}-jdk21-maven-
~~~

Key có cache schema, OS, kiến trúc, JDK, package manager và hash các POM cùng Maven Wrapper. Restore key chỉ bỏ phần hash dependency, vẫn giữ các yếu tố môi trường chính.

Đây là ví dụ cho dependency cache. Với build cache hoặc cache chứa binary native, có thể cần thêm compiler version, ABI, build profile hoặc các cờ ảnh hưởng kết quả. Hãy kiểm tra action cache của nền tảng về giới hạn kích thước, phạm vi truy cập, eviction và cách lưu cache sau job.

## 8. Cache trong monorepo và ma trận môi trường

Monorepo có thể chứa nhiều ứng dụng và nhiều loại dependency. Một cache duy nhất cho toàn bộ repository thường khó đạt cân bằng giữa phạm vi tái sử dụng và độ chính xác.

Có thể chia cache theo:

- Service hoặc module.
- Package manager.
- Lockfile tương ứng.
- Runtime version.
- OS và architecture.
- Nhóm dependency dùng chung.

Ví dụ, cache cho `services/billing` và `services/catalog` có thể dùng hai key riêng, cùng một cache schema nhưng hash lockfile khác nhau. Nếu cả hai phụ thuộc workspace root, key cần hash lockfile root và các manifest liên quan.

Với matrix build, mỗi tổ hợp OS, runtime hoặc architecture có thể cần cache riêng. Ví dụ:

| Matrix | Cache nên phân biệt khi |
|---|---|
| Ubuntu x64 / Windows x64 | Package hoặc dữ liệu cache phụ thuộc OS |
| Linux x64 / Linux ARM64 | Có native binary hoặc compiler output |
| JDK 17 / JDK 21 | Build cache hoặc công cụ phụ thuộc JDK |
| Node 20 / Node 22 | Native addon hoặc cache phụ thuộc Node ABI |
| Python 3.11 / 3.12 | Wheel hoặc cache phụ thuộc Python ABI |

Không nhất thiết phải tách cache cho mọi matrix nếu nội dung cache là package thuần và tương thích giữa các môi trường. Quyết định phải dựa trên loại dữ liệu được cache, không chỉ dựa trên tên matrix.

## 9. Cache và an toàn chuỗi cung ứng

Cache có thể chứa dữ liệu được tạo ra từ một lần chạy trước. Nếu một job không đáng tin có thể ghi cache mà job phát hành có quyền cao sẽ khôi phục và thực thi, cache trở thành đường truyền dữ liệu độc hại.

Một số rủi ro:

- Cache bị đầu độc (cache poisoning) bởi mã hoặc script trong pull request.
- Cache chứa file thực thi đã bị thay đổi.
- Cache lưu nhầm token, credential hoặc file cấu hình nhạy cảm.
- Cache từ một môi trường được khôi phục trong môi trường không tương thích.
- Cache cũ giữ dependency đã bị thu hồi hoặc metadata không còn phù hợp.

Các nguyên tắc bảo vệ:

1. Xem cache là dữ liệu có thể bị thay đổi, không phải bằng chứng về nguồn gốc.
2. Không cache secret, token, private key hoặc file credential.
3. Tách namespace hoặc phạm vi cache giữa job không tin cậy và job phát hành có quyền cao.
4. Không khôi phục cache do pull request bên ngoài kiểm soát vào job có quyền deploy hoặc publish.
5. Không thực thi binary hoặc script lấy từ cache nếu chưa có cơ chế xác minh phù hợp.
6. Dùng package manager và checksum/signature verification để xác minh dependency.
7. Pin dependency và công cụ; dùng lockfile và dependency verification khi hệ sinh thái hỗ trợ.
8. Giữ khả năng build sạch khi cần điều tra hoặc phát hành nhạy cảm.

Cache key không phải cơ chế phân quyền. Một key khó đoán hoặc có tên riêng không thay thế chính sách access control của nền tảng. Cần hiểu ai có thể ghi cache, ai có thể khôi phục cache và cache có được chia sẻ giữa các branch, workflow hoặc repository hay không.

Với release quan trọng, có thể chạy một lần build sạch không dùng cache hoặc dùng cache đã được tạo trong phạm vi tin cậy, rồi so sánh kết quả theo chính sách. Cách này tốn thời gian hơn nhưng hữu ích để điều tra cache poisoning hoặc lỗi do dữ liệu cũ.

## 10. Cache invalidation và xử lý cache hỏng

Cache invalidation là việc làm cho cache cũ không còn được sử dụng hoặc xóa cache không còn phù hợp. Đây là một trong những phần khó nhất của caching vì cache có thể tồn tại lâu hơn thay đổi đã tạo ra nó.

Các cách xử lý:

- **Thay key theo dependency hash:** lockfile thay đổi sẽ tạo key mới.
- **Tăng cache schema version:** thay đổi cấu trúc cache hoặc cần vô hiệu hóa hàng loạt.
- **Xóa cache cụ thể:** dùng công cụ quản trị của nền tảng khi phát hiện cache hỏng.
- **Giới hạn retention:** đặt thời gian lưu và dung lượng phù hợp.
- **Chạy clean build:** bỏ qua cache để xác minh lỗi có đến từ cache hay không.

Khi cache bị hỏng, không nên lặp lại cùng một lần restore vô hạn. Pipeline có thể phát hiện lỗi giải nén hoặc lỗi package manager, xóa hoặc bỏ qua cache theo chính sách rồi tải dependency sạch. Cần ghi log đủ để phân biệt cache miss bình thường với cache corruption.

Đối với package manager, nên để công cụ quản lý dependency kiểm tra tính hợp lệ của package. Xóa cache toàn bộ chỉ nên là biện pháp có chủ đích, vì nó làm tăng thời gian build và tải lên registry.

## 11. Đo hiệu quả cache

Cache không tự động làm pipeline nhanh hơn. Một cache rất lớn có thể mất nhiều thời gian tải xuống và giải nén hơn việc tải lại một số dependency nhỏ.

Nên theo dõi:

| Chỉ số | Ý nghĩa |
|---|---|
| Exact hit rate | Tỷ lệ lần chạy khôi phục đúng key |
| Restore hit rate | Tỷ lệ lần chạy tìm được cache qua key fallback |
| Cache miss rate | Tỷ lệ không tìm được cache |
| Restore duration | Thời gian tải và giải nén cache |
| Save duration | Thời gian đóng gói và lưu cache |
| Cache size | Dung lượng cache và tốc độ tăng |
| Build duration | Thời gian pipeline thực tế |
| Dependency download volume | Lượng dữ liệu phải tải từ registry |
| Failure after restore | Lỗi xảy ra sau khi khôi phục cache |

Một số tình huống cần điều tra:

- Hit rate cao nhưng build không nhanh hơn: cache quá lớn hoặc bước nghẽn nằm ở nơi khác.
- Hit rate thấp: key chứa đầu vào thay đổi liên tục hoặc restore key không phù hợp.
- Lỗi chỉ xuất hiện khi cache hit: cache cũ, không tương thích hoặc bị hỏng.
- Cache tăng dung lượng nhanh: đang lưu cả output không cần thiết hoặc nhiều phiên bản không được dọn.
- Restore chậm hơn download: nên giảm phạm vi cache hoặc dùng cache tích hợp của package manager.

Hãy so sánh thời gian end-to-end của job trước và sau khi bật cache. Mục tiêu là giảm tổng thời gian và tải hệ thống, không phải tối đa hóa con số cache hit bằng mọi giá.

## 12. Checklist thiết kế cache key

Trước khi bật cache hoặc thay đổi cache key, hãy kiểm tra:

- [ ] Đã xác định rõ loại dữ liệu được cache và mục đích tái sử dụng.
- [ ] Cache key chứa manifest hoặc lockfile có ảnh hưởng đến dependency.
- [ ] Key bao gồm OS, kiến trúc và runtime khi dữ liệu cache phụ thuộc môi trường.
- [ ] Đã xem xét phiên bản package manager, compiler và cấu hình build có liên quan.
- [ ] Cache của từng module trong monorepo được phân tách theo dependency thực tế.
- [ ] Cache schema version có thể tăng khi thay đổi định dạng hoặc cần vô hiệu hóa.
- [ ] Không dùng run ID, timestamp hoặc commit SHA nếu chúng không ảnh hưởng nội dung cache.
- [ ] Restore key chỉ fallback qua những môi trường tương thích.
- [ ] Package manager vẫn xác minh dependency theo lockfile hiện tại.
- [ ] Cache không chứa secret, credential hoặc dữ liệu nhạy cảm.
- [ ] Cache từ job không tin cậy không được dùng trong job phát hành có quyền cao.
- [ ] Có thể chạy clean build khi cache lỗi hoặc cần điều tra.
- [ ] Cache có giới hạn dung lượng, retention và quy trình xóa.
- [ ] Có metric để đo cache hit, thời gian restore/save và lợi ích thực tế.

Khóa cache cần mô tả đúng những đầu vào quyết định khả năng tái sử dụng. Khi key bao gồm dependency và môi trường có liên quan, fallback được giới hạn hợp lý, còn cache được tách theo phạm vi tin cậy, pipeline có thể tăng tốc mà vẫn giữ được tính nhất quán và khả năng truy vết.

