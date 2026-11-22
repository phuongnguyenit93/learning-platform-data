# Phân biệt cache tăng tốc với artifact cần bàn giao

Trong CI/CD, cache và artifact đều có thể chứa tệp được tạo ra trong quá trình build, nhưng chúng phục vụ hai mục đích khác nhau. **Cache giúp một lần chạy sau thực hiện công việc nhanh hơn** bằng cách tái sử dụng dữ liệu có thể tạo lại. **Artifact là đầu ra cần được lưu, chuyển giao, kiểm thử, phát hành hoặc truy vết** sau khi một job hoàn thành.

Nếu coi cache như nơi lưu đầu ra phát hành, pipeline có thể mất bản build khi cache hết hạn hoặc bị xóa. Nếu dùng artifact làm cache cho mọi dependency, hệ thống có thể lưu trữ quá nhiều dữ liệu, truyền tệp không cần thiết và làm chậm job. Vì vậy, kiến trúc CI/CD cần xác định rõ dữ liệu nào có thể tái tạo, dữ liệu nào là kết quả cần bàn giao, ai được đọc hoặc ghi và cần giữ chúng trong bao lâu.

Bài học này giải thích ranh giới giữa cache và artifact, cách áp dụng cho dependency và build output, cách thiết kế cache key, truyền artifact giữa các job, bảo vệ tính toàn vẹn và truy vết đầu ra phát hành. Mục tiêu là làm cho pipeline nhanh hơn mà vẫn bảo đảm bản build được kiểm tra chính là bản được bàn giao và triển khai.

## 1. Hiểu đúng vai trò của cache và artifact

**Cache** là vùng lưu tạm dữ liệu để tránh thực hiện lại một công việc tốn thời gian. Pipeline có thể khôi phục cache ở lần chạy tiếp theo nếu khóa cache phù hợp và dữ liệu vẫn còn. Cache có thể bị hết hạn, xóa, thay thế hoặc không được khôi phục; vì vậy job phải có khả năng tiếp tục bằng cách tạo lại dữ liệu khi cache không tồn tại.

Ví dụ về cache:

- Các gói dependency đã tải về từ Maven, Gradle, npm, pip hoặc một package manager khác.
- Kết quả biên dịch trung gian có thể tái sử dụng khi đầu vào không đổi.
- Các layer hoặc dữ liệu hỗ trợ build container.
- Cache của compiler, test runner hoặc công cụ phân tích tĩnh.
- Dữ liệu đã được tính toán để phục vụ các lần build tiếp theo.

**Artifact** là đầu ra có ý nghĩa của một job hoặc pipeline, được lưu để một bước khác sử dụng, để người dùng tải xuống, để phát hành hoặc để làm bằng chứng. Artifact phải gắn với lần chạy và đầu vào đã tạo ra nó.

Ví dụ về artifact:

- Tệp JAR, WAR, ZIP hoặc gói ứng dụng đã build.
- Container image được lưu trong registry.
- Báo cáo kiểm thử, coverage report và kết quả quét bảo mật.
- Gói triển khai, manifest, file cấu hình đã được tạo theo phiên bản.
- SBOM, chữ ký, provenance hoặc metadata phát hành.
- Tệp nhị phân cần được chuyển từ job build sang job kiểm thử hoặc deploy.

Có thể nhớ bằng hai câu hỏi:

- Nếu dữ liệu biến mất, job có thể tạo lại từ source, dependency và cấu hình đã quản lý không? Nếu có, dữ liệu đó thường phù hợp với cache.
- Nếu dữ liệu biến mất, pipeline có mất đầu ra đã kiểm tra, bằng chứng hoặc gói cần bàn giao không? Nếu có, dữ liệu đó cần được quản lý như artifact.

Đây là cách phân loại theo mục đích. Cùng một loại tệp có thể đóng vai trò khác nhau tùy cách sử dụng. Ví dụ, một tệp JAR trung gian có thể được lưu trong cache build để tái sử dụng, nhưng JAR đã được kiểm tra và dùng để phát hành phải được lưu như artifact có danh tính và thời hạn lưu giữ phù hợp.

## 2. So sánh cache và artifact

| Tiêu chí | Cache | Artifact |
|---|---|---|
| Mục đích | Tăng tốc công việc có thể lặp lại | Bàn giao đầu ra và bằng chứng |
| Tính cần thiết | Không có vẫn phải chạy được, dù chậm hơn | Thiếu thì bước phụ thuộc không thể tiếp tục đúng quy trình |
| Vòng đời | Có thể hết hạn, bị xóa hoặc thay thế | Có chính sách lưu giữ theo giá trị và yêu cầu phát hành |
| Khả năng tái tạo | Có thể tạo lại từ đầu vào đã quản lý | Phải giữ đúng đầu ra đã tạo và đã xác minh |
| Danh tính | Thường dựa trên cache key | Gắn với pipeline run, commit, phiên bản và digest |
| Tính bất biến | Có thể thay đổi hoặc được cập nhật theo key | Nên bất biến sau khi tạo và công bố |
| Cách sử dụng | Khôi phục dữ liệu trước khi thực thi | Truyền đầu ra giữa job, lưu trữ hoặc triển khai |
| Khi lỗi | Cache miss thường chỉ làm chậm | Artifact thiếu hoặc sai phải làm pipeline thất bại |
| Bảo mật | Cần kiểm soát nguồn ghi và phạm vi chia sẻ | Cần kiểm soát quyền đọc/ghi, tính toàn vẹn và nguồn gốc |

Cache là một tối ưu hóa. Artifact là một hợp đồng bàn giao. Pipeline cần hoạt động đúng khi cache trống, nhưng phải dừng nếu artifact bắt buộc không tồn tại, không đúng phiên bản hoặc không xác minh được.

Không nên dùng một thư mục có tên cache hoặc artifacts để quyết định bản chất dữ liệu. Hãy xem xét cách pipeline sử dụng dữ liệu, cách định danh, chính sách lưu giữ và hậu quả khi dữ liệu bị mất.

## 3. Phân biệt ba loại dữ liệu thường gặp

Trong pipeline, có ba nhóm dễ bị nhầm lẫn:

1. **Dependency được quản lý:** thư viện hoặc package mà ứng dụng sử dụng, được khai báo trong manifest và lockfile, lấy từ nguồn package đáng tin cậy.
2. **Cache:** bản sao hoặc kết quả trung gian có thể tái sử dụng để giảm thời gian tải và tính toán.
3. **Artifact:** đầu ra của lần build hoặc kiểm thử cụ thể, được chuyển giao cho bước tiếp theo hoặc lưu làm bằng chứng.

Ví dụ với một dự án Java:

- build.gradle hoặc pom.xml khai báo dependency.
- Locking hoặc dependency constraints giúp kiểm soát phiên bản được chọn.
- Cache của Gradle hoặc Maven lưu dữ liệu tải xuống và một số kết quả trung gian.
- Tệp build/libs/application.jar được tạo sau build.
- Pipeline upload JAR đã kiểm tra thành artifact, sau đó job deploy tải đúng artifact đó.

Nguồn package registry vẫn là nơi quản lý package đã phát hành. Cache của package manager chỉ là bản sao cục bộ hoặc từ xa để tải nhanh hơn. Nếu cache bị xóa, package manager phải có thể tải lại dependency từ nguồn được cấu hình.

Một container image cũng có thể có nhiều vai trò. Layer cache giúp build image nhanh hơn; image được push với digest vào container registry và được triển khai là artifact phát hành. Không nên dựa vào layer cache như bằng chứng rằng image phát hành đã được lưu an toàn.

## 4. Cache dependency để giảm thời gian tải

Cài dependency thường là một phần đáng kể thời gian CI. Mỗi lần chạy sạch có thể tải lại hàng trăm package hoặc thư viện. Cache giúp giữ bản tải xuống để job sau sử dụng.

### 4.1. Cache dữ liệu package manager

Ví dụ về thư mục thường được cache:

| Hệ sinh thái | Dữ liệu có thể cache | Đầu vào nên xét |
|---|---|---|
| Java / Gradle | Dependency artifact và metadata trong Gradle user home | Gradle wrapper, dependency declarations, lockfile, repository config, JDK |
| Java / Maven | Local repository của Maven | POM, dependency versions, Maven settings phù hợp, JDK |
| Node.js | Package manager download cache | Lockfile, phiên bản Node và package manager |
| Python | Cache package download và wheel | Lockfile/requirements, phiên bản Python, nền tảng |
| .NET | NuGet package cache | Project files, lockfile, SDK version |
| Container build | Layer cache | Dockerfile, build context, base image và build arguments |

Không phải lúc nào cũng nên cache toàn bộ thư mục làm việc. Ví dụ, với Node.js, cache dữ liệu package manager thường an toàn và dễ tái tạo hơn việc giữ nguyên node_modules giữa các hệ điều hành hoặc phiên bản runtime khác nhau. Với Gradle, có thể cache dependency và build cache theo cơ chế của Gradle, nhưng cần hiểu rõ phạm vi và điều kiện hợp lệ của từng loại dữ liệu.

### 4.2. Khóa dependency trước khi cache

Cache chỉ có ý nghĩa khi đầu vào dependency ổn định. Nếu manifest cho phép chọn phiên bản mới nhất hoặc dependency được cập nhật mà không khóa, hai lần chạy có thể dùng các phiên bản khác nhau dù source code không đổi.

Nên:

- Dùng lockfile hoặc cơ chế dependency locking của hệ sinh thái.
- Khai báo phiên bản toolchain rõ ràng.
- Xác định repository nguồn và chính sách dependency.
- Ghi nhận phiên bản runtime, compiler và build tool.
- Review thay đổi dependency như thay đổi mã nguồn.
- Xác minh checksum hoặc chữ ký khi hệ sinh thái hỗ trợ.

Cache giúp tái sử dụng package đã tải, nhưng không thay thế lockfile và chính sách quản lý dependency.

### 4.3. Cache miss phải là trường hợp bình thường

Một job không được phụ thuộc vào việc cache luôn tồn tại. Khi cache miss, pipeline phải tải dependency từ nguồn hợp lệ rồi tiếp tục.

Nếu cache miss khiến build thất bại, có thể pipeline đang dùng cache như nguồn dữ liệu duy nhất. Khi đó cần chuyển dữ liệu cần thiết sang package registry hoặc artifact store phù hợp, đồng thời giữ cache đúng vai trò tăng tốc.

## 5. Thiết kế cache key

Cache key là định danh dùng để tìm dữ liệu cache tương ứng với đầu vào của job. Key quá rộng có thể khôi phục dữ liệu không tương thích; key quá hẹp làm cache miss thường xuyên và giảm hiệu quả.

Một cache key nên phản ánh những đầu vào có thể làm thay đổi nội dung cache, chẳng hạn:

- Hệ điều hành và kiến trúc CPU.
- Phiên bản runtime hoặc JDK.
- Phiên bản compiler và build tool.
- Lockfile hoặc dependency manifest.
- Cấu hình build và các feature flag ảnh hưởng đến kết quả.
- Module hoặc phạm vi dependency.
- Phiên bản định dạng cache nếu cấu trúc dữ liệu thay đổi.

Ví dụ về cách ghép key ở mức khái niệm:

~~~text
cache-key =
  os
  + architecture
  + runtime-version
  + build-tool-version
  + hash(dependency-lockfile)
  + cache-schema-version
~~~

Ví dụ, cache dependency của một dự án Java có thể thay đổi khi gradle-wrapper.properties, lockfile hoặc JDK thay đổi. Nếu key chỉ dựa vào tên nhánh, nhiều trạng thái dependency khác nhau có thể dùng chung cache mà không có cơ chế phân biệt đủ chính xác.

### 5.1. Exact key và fallback key

Một số nền tảng cho phép khôi phục cache theo key chính xác hoặc dùng prefix/fallback key. Có thể dùng fallback để lấy dữ liệu gần nhất rồi cập nhật cache theo key mới, nhưng phải hiểu rủi ro tương thích.

- Exact key phù hợp khi muốn cache khớp đầy đủ với đầu vào.
- Fallback key giúp tăng tỷ lệ cache hit khi lockfile thay đổi nhẹ.
- Dữ liệu khôi phục từ fallback cần được công cụ xác minh và cập nhật theo dependency hiện tại.
- Không dùng fallback quá rộng cho build output hoặc dữ liệu phụ thuộc mạnh vào compiler, platform hay cấu hình.

Fallback key là cách tìm dữ liệu khởi đầu, không phải bằng chứng rằng dữ liệu khôi phục đã hợp lệ.

### 5.2. Phiên bản hóa cache

Khi cấu trúc cache thay đổi, thêm cache schema version vào key để tránh đọc dữ liệu cũ theo định dạng mới. Điều này hữu ích khi nâng cấp toolchain, thay đổi cách đóng gói hoặc chuyển hệ điều hành.

Không nên cố giữ cache cũ bằng mọi giá. Cache có thể xóa và tạo lại. Một cache miss có kiểm soát thường rẻ hơn việc dùng dữ liệu cũ sai định dạng rồi tạo ra lỗi khó điều tra.

## 6. Cache build output và kết quả tính toán

Ngoài dependency đã tải, một số công cụ có thể cache kết quả build hoặc tác vụ đã thực thi. Khi đầu vào không đổi, công cụ có thể bỏ qua công việc và tái sử dụng kết quả.

Ví dụ:

- Gradle build cache.
- Compiler cache.
- Cache của bundler hoặc transpiler.
- Cache của công cụ phân tích tĩnh.
- Remote cache cho monorepo hoặc hệ thống build phân tán.

### 6.1. Điều kiện để tái sử dụng build output

Build output chỉ nên được tái sử dụng khi công cụ có thể xác định đầu vào và môi trường đủ chính xác. Các đầu vào có thể bao gồm source, dependency, compiler, build flags, environment variables, generated code và hệ điều hành.

Một số nguyên tắc:

- Ưu tiên cơ chế cache có hiểu biết về task/input của build tool.
- Khai báo input và output của task đầy đủ.
- Tránh để task phụ thuộc vào thời gian hiện tại, trạng thái máy hoặc file ngoài khai báo.
- Không ghi dữ liệu không xác định vào cache dùng chung.
- Dùng namespace hoặc key riêng cho môi trường khác nhau.
- Có cách chạy clean build để đối chiếu khi nghi ngờ cache sai.

Nếu build task đọc một biến môi trường không được khai báo là input, cache có thể trả về kết quả được tạo dưới cấu hình khác. Khi đó lỗi không nằm ở cache storage mà ở việc build không mô tả đầy đủ các yếu tố ảnh hưởng đến kết quả.

### 6.2. Cache không thay thế kiểm thử

Cache hit chỉ cho biết dữ liệu đã được tìm thấy theo key. Nó không tự chứng minh mã nguồn mới đã được kiểm tra hoặc kết quả vẫn đúng.

Pipeline vẫn cần chạy các bước kiểm thử bắt buộc và ghi lại kết quả cho commit hiện tại. Nếu cache được dùng để bỏ qua một task, build tool phải có cơ chế xác định rằng input tương ứng không thay đổi và task có thể tái sử dụng một cách hợp lệ.

## 7. Artifact là đầu ra cần bàn giao

Artifact cần được quản lý như một đầu ra có danh tính. Khi một job build tạo ra gói ứng dụng, job kiểm thử hoặc deploy phải nhận đúng gói đó thay vì tự build lại từ source trong một môi trường khác.

Một artifact phát hành nên có các thuộc tính:

- Tên và phiên bản dễ nhận biết.
- Commit SHA hoặc source revision đã tạo ra nó.
- Pipeline run ID và thời điểm build.
- Phiên bản runtime, compiler và build tool quan trọng.
- Digest hoặc checksum để xác minh nội dung.
- Metadata về dependency hoặc SBOM nếu quy trình yêu cầu.
- Nguồn lưu trữ, quyền đọc/ghi và chính sách retention.
- Chữ ký hoặc provenance nếu cần xác minh nguồn gốc.

Artifact nên bất biến sau khi công bố. Nếu nội dung thay đổi, hãy tạo artifact mới với danh tính mới. Không ghi đè một file phát hành cũ bằng nội dung khác dưới cùng một phiên bản.

### 7.1. Artifact trung gian và artifact phát hành

Không phải mọi file tạo ra trong job đều cần lưu dài hạn. Có thể phân biệt:

- **Artifact trung gian:** file được truyền giữa các job trong cùng pipeline, ví dụ binary để chạy integration test.
- **Artifact bằng chứng:** test report, coverage report, log đã chọn lọc hoặc kết quả scan.
- **Artifact phát hành:** gói ứng dụng hoặc image sẽ được promote và triển khai.
- **Metadata phát hành:** manifest, SBOM, provenance, chữ ký và thông tin liên kết.

Artifact trung gian có thể có retention ngắn hơn artifact phát hành. Báo cáo kiểm thử có thể cần giữ theo chính sách kiểm toán hoặc điều tra. Artifact phát hành cần tồn tại đủ lâu để triển khai, quay lui và tái tạo môi trường được hỗ trợ.

### 7.2. Artifact store và package registry

Pipeline artifact store thường lưu đầu ra của một lần chạy để job khác hoặc người dùng tải xuống. Package registry hoặc container registry lưu package/image theo phiên bản và có thể phục vụ nhiều pipeline, môi trường hoặc nhóm.

Không nên mặc định hai nơi này có cùng chính sách:

| Nơi lưu | Mục tiêu | Ví dụ |
|---|---|---|
| CI artifact store | Bàn giao giữa job và lưu kết quả pipeline | JAR, test report, build bundle |
| Package registry | Phân phối package có phiên bản | Maven package, npm package, NuGet |
| Container registry | Phân phối container image | Image được xác định bằng tag và digest |
| Remote build cache | Tái sử dụng kết quả build | Task output hoặc compiler cache |

Một gói có thể được upload lên artifact store để kiểm thử, sau đó publish vào package registry khi đã đạt điều kiện phát hành. Cần giữ liên kết giữa artifact ban đầu và package đã công bố, chẳng hạn bằng digest và metadata.

## 8. Truyền artifact giữa các job

Trong pipeline nhiều job, mỗi job có thể chạy trên runner khác nhau. Filesystem cục bộ thường không được chia sẻ hoặc không nên được giả định là còn tồn tại. Vì vậy, artifact cần được upload ở job tạo ra và download ở job phụ thuộc.

Luồng cơ bản:

~~~mermaid
flowchart TD
    A["Checkout source"] --> B["Build"]
    B --> C["Tạo package"]
    C --> D["Upload artifact"]
    D --> E["Job kiểm thử tải artifact"]
    E --> F["Integration / acceptance tests"]
    F --> G{"Đạt điều kiện?"}
    G -- "Không" --> H["Giữ báo cáo, dừng phát hành"]
    G -- "Có" --> I["Job deploy tải đúng artifact"]
    I --> J["Triển khai môi trường"]
    J --> K["Xác minh phiên bản và digest"]
~~~

Các bước cần xác định:

1. Job build tạo artifact từ commit cụ thể.
2. Pipeline kiểm tra file tồn tại, kích thước và cấu trúc hợp lệ.
3. Job upload artifact lên nơi lưu trữ được quản lý.
4. Job kiểm thử tải artifact theo đúng pipeline run hoặc định danh đã ghi nhận.
5. Job deploy chỉ tải artifact đã vượt qua các cổng cần thiết.
6. Sau triển khai, hệ thống đối chiếu phiên bản hoặc digest đang chạy.

Không nên truyền file bằng cách dựa vào thư mục workspace của runner trước đó. Nếu các job chạy trên máy khác, file cục bộ có thể không tồn tại. Hãy dùng cơ chế artifact handoff của nền tảng hoặc một kho lưu trữ được kiểm soát.

### 8.1. Tránh build lại ở từng job

Giả sử job test build lại ứng dụng và job deploy cũng build lại. Dù cùng commit, kết quả có thể khác do dependency, toolchain, biến môi trường, thời điểm hoặc cấu hình runner.

Với quy trình phát hành, nên:

- Build một artifact từ đầu vào đã xác định.
- Kiểm thử chính artifact đó.
- Promote chính artifact đó qua các môi trường.
- Xác minh digest ở từng điểm bàn giao.

Cách này giúp giảm khác biệt giữa bản đã kiểm thử và bản được triển khai. Một số dự án có thể cần build riêng theo nền tảng hoặc kiến trúc, nhưng mỗi biến thể vẫn phải có danh tính, metadata và bằng chứng riêng.

## 9. Bảo đảm tính toàn vẹn và nguồn gốc artifact

Artifact có thể bị hỏng trong quá trình truyền, bị ghi đè hoặc bị thay thế bởi một nguồn không đáng tin. Vì vậy, cần xác minh nội dung và nguồn gốc.

### 9.1. Digest và checksum

Sau khi tạo artifact, pipeline có thể tính SHA-256 hoặc digest do registry cung cấp. Khi tải artifact ở job sau, tính lại hoặc xác minh digest để bảo đảm nội dung khớp.

Digest xác định nội dung byte cụ thể. Nếu chỉ so sánh tên file hoặc version tag, pipeline có thể không phát hiện nội dung đã thay đổi dưới cùng tên.

### 9.2. Provenance và chữ ký

Với hệ thống cần mức tin cậy cao, có thể bổ sung:

- Provenance mô tả source, builder và quy trình tạo artifact.
- Chữ ký số để xác minh artifact được tạo hoặc phát hành bởi danh tính được tin cậy.
- SBOM mô tả thành phần phần mềm có trong artifact.
- Attestation hoặc bằng chứng kiểm tra gắn với digest.

Các cơ chế này cần được tích hợp với danh tính builder và chính sách xác minh. Một chữ ký hợp lệ từ một danh tính không được phép không chứng minh artifact đáng tin cậy.

### 9.3. Không đưa secret vào artifact

Artifact có thể được chia sẻ qua nhiều job hoặc người dùng. Không đóng gói token, private key, file .env bí mật hoặc dữ liệu nhạy cảm vào artifact. Cấu hình môi trường và secret nên được cấp khi triển khai hoặc khi ứng dụng khởi động theo cơ chế được kiểm soát.

Nếu phát hiện artifact chứa secret, cần xử lý như sự cố lộ thông tin: thu hồi hoặc luân chuyển credential, xác định nơi artifact đã được tải và tạo bản phát hành sạch.

## 10. Bảo mật cache và tránh cache poisoning

Cache có thể được ghi bởi một lần chạy rồi được lần chạy khác khôi phục. Nếu nguồn ghi không đáng tin có thể thay đổi cache dùng chung, job tin cậy có thể nhận dữ liệu bị đầu độc.

Các rủi ro thường gặp:

- Pull request từ fork ghi vào cache mà nhánh chính sử dụng.
- Cache key quá rộng khiến các nhánh hoặc môi trường khác nhau chia sẻ dữ liệu.
- Cache chứa script hoặc binary đã bị thay thế.
- Cache cũ khôi phục dependency không còn phù hợp.
- Cache lưu nhầm secret, token hoặc file cấu hình nhạy cảm.
- Cache được tải từ nguồn ngoài mà không xác minh.

### 10.1. Phân tách cache theo trust boundary

Nên xác định ai được phép ghi cache và ai được phép đọc:

- Cache từ PR không tin cậy không được dùng làm nguồn ghi cho pipeline release.
- Cache nhánh chính có thể có phạm vi riêng.
- Cache build có quyền ghi nên được giới hạn theo repository, branch hoặc trust level.
- Cache có dữ liệu nhạy cảm cần được cô lập hoặc không đưa vào cache dùng chung.
- Không dùng chung cache giữa môi trường có quyền khác nhau nếu chưa đánh giá rủi ro.

Chính sách cụ thể phụ thuộc nền tảng CI/CD. Một số nền tảng tự giới hạn cache theo nhánh hoặc ref; số khác cho phép chia sẻ rộng hơn. Hãy xác minh hành vi thực tế, không giả định cache tự động được cô lập.

### 10.2. Cache không phải nơi lưu bí mật

Không cache toàn bộ thư mục HOME hoặc workspace nếu trong đó có credential. Hãy chọn chính xác thư mục dữ liệu có thể tái tạo. Nếu cache cần xác thực để truy cập, credential phải được cấp riêng qua secret manager, không đóng gói trong nội dung cache.

### 10.3. Khi nghi ngờ cache bị đầu độc

Có thể:

1. Ngừng sử dụng cache key hoặc namespace bị ảnh hưởng.
2. Xóa cache trong phạm vi cần thiết.
3. Chạy clean build từ dependency registry đáng tin cậy.
4. Kiểm tra checksum, chữ ký và nguồn dependency.
5. Xác định job hoặc danh tính đã ghi cache.
6. Kiểm tra artifact được tạo trong khoảng thời gian nghi ngờ.
7. Tạo lại artifact và lưu bằng chứng điều tra.

Không nên chỉ xóa cache rồi tiếp tục phát hành nếu chưa xác định artifact nào đã được tạo từ cache đáng ngờ.

## 11. Chính sách retention và dọn dẹp

Cache và artifact cần chính sách lưu giữ khác nhau.

**Cache** có thể có TTL ngắn hoặc bị loại bỏ theo dung lượng. Khi cache cũ ít được dùng hoặc không còn phù hợp, có thể xóa để tiết kiệm storage. Việc xóa cache không được làm mất khả năng build đúng.

**Artifact** cần retention theo giá trị của đầu ra:

- Artifact tạm của pull request có thể giữ trong thời gian ngắn.
- Test report có thể giữ theo nhu cầu review và điều tra.
- Artifact release cần giữ theo thời gian hỗ trợ phiên bản và chính sách rollback.
- SBOM, provenance và bằng chứng phê duyệt có thể cần lưu lâu hơn package tạm.
- Artifact phục vụ khôi phục phải được bảo vệ khỏi quy trình dọn dẹp thông thường.

Cần có quy tắc tránh xóa nhầm artifact đang được triển khai hoặc còn được hỗ trợ. Dọn dẹp nên dựa trên metadata, trạng thái phát hành và chính sách retention, không chỉ dựa vào tuổi file.

## 12. Ví dụ pipeline có cache và artifact riêng biệt

Ví dụ dưới đây mô tả ý tưởng tổ chức job, cache và artifact. Đây không phải cú pháp của một nền tảng CI/CD cụ thể:

~~~yaml
pipeline:
  build:
    steps:
      - checkout_source
      - restore_dependency_cache:
          key: os-runtime-toolchain-lockfile-hash
      - resolve_dependencies_from_trusted_registry
      - run_build
      - run_unit_tests
      - create_application_package
      - calculate_artifact_digest
      - upload_pipeline_artifact:
          name: application-package
          include:
            - application.jar
            - build-metadata.json

  integration_test:
    needs: [build]
    steps:
      - download_pipeline_artifact:
          name: application-package
      - verify_artifact_digest
      - run_integration_tests_on_downloaded_package
      - upload_test_report

  deploy:
    needs: [integration_test]
    condition: release_gates_pass
    steps:
      - download_pipeline_artifact:
          name: application-package
      - verify_artifact_digest
      - deploy_same_package
      - verify_running_version
~~~

Ở đây, dependency cache được khôi phục để giảm thời gian resolve và tải thư viện. Artifact ứng dụng được upload riêng để job integration test và deploy tải đúng đầu ra của job build. Nếu cache miss, build vẫn có thể tải dependency từ registry. Nếu artifact ứng dụng thiếu hoặc digest không khớp, job phụ thuộc phải dừng.

### 12.1. Ví dụ với dự án Java

Với Gradle hoặc Maven, có thể cân nhắc:

- Cache dữ liệu dependency của Gradle/Maven để giảm thời gian tải package.
- Dùng dependency locking hoặc phiên bản khai báo rõ để kết quả resolve ổn định.
- Dùng build cache của Gradle khi task được khai báo input/output đúng.
- Upload JAR/WAR đã build như pipeline artifact.
- Upload test report và coverage report làm artifact bằng chứng.
- Publish package đã được phê duyệt vào Maven repository nếu đó là đầu ra phân phối.
- Triển khai đúng JAR hoặc image đã được kiểm thử, không build lại trong job deploy.

Đường dẫn cache và cách cấu hình cụ thể phụ thuộc phiên bản tool, hệ điều hành và nền tảng CI. Cần kiểm tra tài liệu công cụ đang sử dụng trước khi chọn thư mục hoặc bật remote cache.

## 13. Điều tra các vấn đề thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Cache hit nhưng build lỗi | Key không phản ánh đủ input, cache cũ hoặc build task khai báo input thiếu | Chạy clean build, so sánh key và đầu vào task |
| Cache miss liên tục | Key thay đổi quá thường xuyên, cache scope không phù hợp hoặc TTL ngắn | Kiểm tra thành phần key, tần suất và chính sách retention |
| Build nhanh nhưng deploy không tìm thấy file | Dùng workspace cục bộ thay cho artifact handoff | Kiểm tra bước upload/download và tên artifact |
| Job test và deploy chạy hai bản khác nhau | Mỗi job tự build lại | Chuyển sang truyền cùng artifact và xác minh digest |
| Artifact bị ghi đè | Dùng tên/version mutable hoặc registry không khóa | Dùng version duy nhất, digest và chính sách immutable |
| Artifact quá lớn | Đóng gói file trung gian, cache hoặc dữ liệu không cần thiết | Thu hẹp danh sách file, tách report và package |
| Cache chứa secret | Cache toàn bộ workspace hoặc HOME | Xóa cache bị ảnh hưởng, thu hồi secret và giới hạn đường dẫn cache |
| Pipeline PR làm nhiễm cache release | Chia sẻ quyền ghi cache giữa trust level khác nhau | Tách namespace và quyền ghi/đọc cache |
| Artifact không thể xác minh | Thiếu digest, metadata hoặc nguồn gốc | Bổ sung manifest, checksum và provenance phù hợp |
| Artifact bị xóa trước khi cần rollback | Retention không tính đến vòng đời phát hành | Điều chỉnh chính sách lưu giữ theo phiên bản hỗ trợ |

Khi điều tra, cần xác định lỗi thuộc cache hay artifact. Nếu cache miss, thử clean build để xem pipeline có thể tạo lại dữ liệu không. Nếu artifact thiếu, sai digest hoặc không có nguồn gốc, cần dừng bước phụ thuộc và khôi phục đúng đầu ra từ pipeline run đáng tin cậy.

## 14. Tình huống mẫu: build một lần, kiểm thử và triển khai cùng artifact

Giả sử nhóm phát triển một dịch vụ Java và muốn giảm thời gian build nhưng vẫn bảo đảm bản production chính là bản đã được kiểm thử.

1. Pipeline nhận commit đã được hợp nhất vào nhánh chính.
2. Job build khôi phục dependency cache theo hệ điều hành, JDK, Gradle wrapper và lockfile.
3. Nếu cache miss, Gradle tải dependency từ repository được cấu hình. Việc này có thể lâu hơn nhưng không làm thay đổi danh tính đầu vào đã khóa.
4. Job chạy unit test, build JAR và tạo metadata chứa commit SHA, pipeline run ID cùng phiên bản toolchain.
5. Pipeline tính digest và upload JAR như artifact của lần chạy.
6. Job integration test chạy trên runner khác, tải đúng artifact, xác minh digest rồi khởi động dịch vụ để kiểm thử.
7. Báo cáo kiểm thử được upload riêng làm artifact bằng chứng.
8. Khi release gate đạt, job deploy tải chính JAR đã kiểm thử, xác minh digest lần nữa và triển khai lên staging hoặc production theo chính sách.
9. Pipeline kiểm tra phiên bản đang chạy và ghi lại artifact digest trong bản ghi phát hành.
10. Cache có thể hết hạn sau đó mà không ảnh hưởng đến bản phát hành đã lưu trong artifact store hoặc package registry.

Trong tình huống này, cache giúp giảm công việc tải dependency. Artifact bảo đảm đầu ra build được chuyển giao chính xác giữa các job và môi trường. Hai cơ chế bổ sung cho nhau nhưng có vòng đời và yêu cầu tin cậy khác nhau.

## 15. Lộ trình thực hành

Có thể thực hành trên một repository mẫu theo các bước:

1. **Kiểm kê dữ liệu pipeline:** liệt kê dependency, thư mục cache, build output, báo cáo test và gói phát hành hiện có.
2. **Phân loại:** đánh dấu từng loại dữ liệu là dependency nguồn, cache, artifact trung gian, artifact bằng chứng hoặc artifact phát hành.
3. **Khóa dependency:** thêm lockfile hoặc cơ chế dependency locking, cố định phiên bản runtime và build tool.
4. **Tạo cache dependency:** chọn đúng thư mục package manager, xây dựng key từ hệ điều hành, toolchain và lockfile.
5. **Thử cache miss:** xóa hoặc đổi key cache trong môi trường thử nghiệm, xác nhận build vẫn tải dependency và chạy thành công.
6. **Tạo artifact:** đóng gói ứng dụng, thêm metadata commit/run ID và tính digest.
7. **Truyền qua job:** upload artifact ở job build, download ở job test và deploy; không dựa vào workspace của runner trước.
8. **Xác minh tính toàn vẹn:** thử dùng sai digest trong môi trường thử nghiệm và xác nhận pipeline dừng.
9. **Kiểm tra ranh giới bảo mật:** xác nhận PR không tin cậy không thể ghi cache được release tin cậy sử dụng hoặc đưa secret vào cache.
10. **Thiết lập retention:** đặt thời hạn riêng cho cache, artifact tạm, báo cáo và artifact phát hành.
11. **Đo hiệu quả:** so sánh thời gian tải dependency, tỷ lệ cache hit, dung lượng lưu trữ, thời gian truyền artifact và tỷ lệ build có thể tái lập.

### Tiêu chí hoàn thành

Người học có thể xem bài thực hành hoàn thành khi chứng minh được:

- Giải thích được vì sao cache là tối ưu tốc độ còn artifact là đầu ra bàn giao.
- Phân loại đúng dependency, cache, build output và artifact phát hành.
- Thiết kế cache key phản ánh các đầu vào ảnh hưởng đến tính tương thích.
- Chứng minh pipeline vẫn chạy đúng khi cache miss.
- Upload và download artifact giữa các job độc lập.
- Xác minh artifact bằng digest và metadata.
- Triển khai cùng artifact đã được kiểm thử qua các môi trường.
- Phân tách quyền cache theo trust boundary và không lưu secret trong cache.
- Thiết lập retention khác nhau cho cache, báo cáo và artifact phát hành.
- Điều tra được cache miss, cache poisoning, artifact thiếu hoặc sai digest.

## Kết luận

Cache và artifact cùng hỗ trợ pipeline nhưng có trách nhiệm khác nhau. Cache tái sử dụng dữ liệu có thể tạo lại để tiết kiệm thời gian; artifact lưu đầu ra và bằng chứng cần bàn giao, kiểm thử, phát hành hoặc truy vết. Cache có thể mất mà pipeline vẫn phải chạy đúng. Artifact bắt buộc phải có danh tính, được lưu theo chính sách và được xác minh trước khi sử dụng.

Một kiến trúc CI/CD hiệu quả quản lý dependency bằng phiên bản rõ ràng, thiết kế cache key theo đầu vào thực tế, phân tách cache theo ranh giới tin cậy và truyền artifact qua các job bằng cơ chế lưu trữ có kiểm soát. Khi build một lần, kiểm thử và triển khai cùng artifact, nhóm có thể tăng tốc pipeline mà vẫn biết chính xác đầu ra nào đã được xác minh và đang chạy trên môi trường đích.

