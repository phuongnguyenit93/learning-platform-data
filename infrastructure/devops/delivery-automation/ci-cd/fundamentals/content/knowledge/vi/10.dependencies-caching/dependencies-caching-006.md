# Xử lý cache cũ, cache hỏng và kết quả không nhất quán

Cache giúp pipeline CI/CD tải dependency nhanh hơn, tránh tính toán lại những đầu ra có thể tái sử dụng và giảm thời gian chờ. Nhưng cache cũng có thể trở thành nguồn gây lỗi khó hiểu: một build dùng cache thành công, build khác thất bại; xóa cache thì lỗi biến mất; hoặc cùng một commit tạo ra artifact khác nhau giữa máy cá nhân và runner.

Muốn xử lý đúng, cần xác định cache đang lưu loại dữ liệu nào, dữ liệu đó phụ thuộc vào những đầu vào nào và hệ thống dùng quy tắc nào để khôi phục cache. Cache chỉ là bản sao có thể tái tạo. Build phải có khả năng chạy đúng khi cache trống, và việc cache hit không được làm thay đổi tính đúng đắn của kết quả.

## 1. Phân biệt các loại cache và artifact

Trong quy trình build, nhiều thư mục có thể được gọi chung là cache nhưng chúng có mục đích và mức độ rủi ro khác nhau:

| Loại dữ liệu | Ví dụ | Mục đích | Cách xử lý khi nghi ngờ lỗi |
|---|---|---|---|
| Dependency cache | JAR đã tải, package archive, metadata repository | Tránh tải lại thư viện và plugin | Kiểm tra checksum, metadata và phiên bản; xóa đúng mục bị lỗi |
| Build cache | Kết quả task compile, test hoặc đóng gói | Tái sử dụng đầu ra của tác vụ có đầu vào tương đương | Kiểm tra khai báo input/output và tính xác định của task |
| Workspace cache | Thư mục build trung gian, generated source, output cục bộ | Giảm công việc giữa các lần chạy trên cùng workspace | Dọn workspace hoặc tạo workspace sạch để đối chiếu |
| Tool cache | Bản phân phối Gradle, Maven, JDK hoặc công cụ đã tải | Tránh tải lại công cụ | Kiểm tra phiên bản, nguồn tải và checksum |
| CI cache | Archive được nền tảng CI lưu và khôi phục giữa các job | Chia sẻ dữ liệu có thể tái tạo giữa các runner | Kiểm tra key, phạm vi truy cập, thời điểm lưu và phiên bản cache |
| Artifact | JAR, WAR, image hoặc gói phát hành đã tạo | Lưu đầu ra có định danh để triển khai hoặc phân phối | Xác minh digest, provenance và nguồn build; không coi artifact là cache tạm |

**Artifact và cache không thay thế cho nhau.** Artifact là đầu ra của một lần build, cần được định danh và lưu trữ để triển khai, kiểm thử hoặc phát hành. Cache là dữ liệu hỗ trợ tăng tốc; có thể xóa và tạo lại mà không làm thay đổi kết quả đúng của build.

Ví dụ, một file JAR đã build và được gắn version cùng checksum là artifact. Một thư mục chứa các dependency đã tải về để lần build sau dùng lại là dependency cache. Nếu xóa dependency cache, build phải tải lại thư viện. Nếu xóa artifact đã phát hành, nhóm có thể mất đầu ra cần thiết để triển khai hoặc khôi phục.

### Cache hit không phải bằng chứng về tính đúng đắn

Cache hit chỉ cho biết hệ thống tìm thấy một mục cache theo khóa đã yêu cầu và có thể khôi phục nó. Điều đó không chứng minh:

- Nội dung cache được tạo từ đúng đầu vào.
- Cache chưa bị hỏng hoặc bị thay đổi.
- Mọi đầu vào ảnh hưởng kết quả đã được đưa vào cache key.
- Tác vụ build có khai báo đầy đủ input và output.
- Kết quả đã được kiểm tra trên trạng thái mã nguồn hiện tại.

Do đó, cần kiểm soát cả cách tạo cache, cách chọn key và cách xác minh dữ liệu sau khi khôi phục.

## 2. Nhận diện cache cũ, cache hỏng và kết quả không nhất quán

Ba tình trạng này có biểu hiện gần giống nhau nhưng nguyên nhân khác nhau.

### Cache cũ (stale cache)

Cache cũ là cache được tạo từ đầu vào hoặc môi trường không còn phù hợp với lần build hiện tại. Ví dụ:

- Dependency lockfile đã thay đổi nhưng cache key không bao gồm lockfile.
- JDK được nâng từ 17 lên 21 nhưng cache vẫn dùng chung.
- Build script hoặc compiler option thay đổi nhưng build cache không nhận diện đầu vào mới.
- Metadata của repository đã thay đổi nhưng cache cũ vẫn chứa thông tin phân giải trước đó.
- Một dependency dạng SNAPSHOT hoặc version động đã được cập nhật nhưng local repository vẫn giữ bản cũ.

Cache cũ không nhất thiết bị hỏng về mặt file. Nó có thể đọc được và giải nén bình thường nhưng không còn đại diện cho đầu vào cần dùng.

### Cache hỏng (corrupted cache)

Cache hỏng là dữ liệu lưu trữ không còn nguyên vẹn hoặc không thể sử dụng đúng cách:

- Archive bị cắt cụt do job bị dừng khi đang ghi.
- File JAR không đầy đủ hoặc checksum không khớp.
- Metadata hoặc index bị ghi dở.
- Hai tiến trình ghi đồng thời vào cùng thư mục cache.
- Cache archive bị lỗi trong quá trình upload, download hoặc giải nén.
- Một tiến trình khác thay đổi file trong khi build đang đọc.

Dấu hiệu thường gặp là lỗi giải nén, lỗi ZIP, checksum mismatch, class không đọc được, file không tồn tại hoặc lỗi I/O xuất hiện không ổn định.

### Kết quả không nhất quán (inconsistent result)

Kết quả không nhất quán xảy ra khi cùng một thay đổi tạo ra đầu ra hoặc trạng thái kiểm thử khác nhau giữa các lần chạy. Nguyên nhân có thể là cache, nhưng cũng có thể đến từ:

- Dependency hoặc plugin chưa được khóa phiên bản.
- Build phụ thuộc vào thời gian, timezone, locale hoặc thứ tự file.
- Tác vụ đọc dữ liệu từ mạng hoặc dịch vụ bên ngoài đang thay đổi.
- Generated source phụ thuộc vào trạng thái workspace cũ.
- Build script khai báo thiếu input hoặc output.
- Test dùng dữ liệu dùng chung và chạy song song không an toàn.
- Runner có JDK, hệ điều hành, kiến trúc hoặc biến môi trường khác nhau.

Không nên kết luận cache là nguyên nhân duy nhất chỉ vì xóa cache làm build chạy lại thành công. Việc xóa cache có thể buộc công cụ tải lại dependency, tính toán lại output hoặc dùng metadata mới, qua đó tạm che giấu nguyên nhân gốc.

## 3. Thiết kế cache key để tránh khôi phục dữ liệu không tương thích

Cache key là định danh dùng để lưu và khôi phục một nhóm dữ liệu. Key quá rộng có thể khôi phục dữ liệu không phù hợp; key quá hẹp làm cache ít được tái sử dụng và tăng chi phí lưu trữ.

Một cache key nên phản ánh những đầu vào có thể làm thay đổi nội dung cache:

- Hệ điều hành và kiến trúc runner.
- Phiên bản JDK hoặc runtime có ảnh hưởng đến output.
- Phiên bản Gradle/Maven hoặc package manager.
- Wrapper properties và cấu hình công cụ.
- Lockfile, dependency manifest và BOM.
- Build script, plugin và compiler option.
- Loại cache và phạm vi tác vụ.
- Phiên bản định dạng cache hoặc một cache salt do nhóm quản lý.

Ví dụ, cache dependency của Gradle có thể dùng khóa khái niệm:

~~~text
gradle-dependencies
  + operating-system
  + architecture
  + jdk-major
  + wrapper-version
  + dependency-lock-hash
  + cache-schema-version
~~~

Không nhất thiết mọi cache phải chứa tất cả trường trên. Hãy chọn đúng tập đầu vào theo dữ liệu đang lưu. Cache dependency thuần túy có thể ít phụ thuộc vào commit SHA hơn cache build output. Cache kết quả biên dịch cần tính đến compiler, build script và các đầu vào của task.

### Không dùng commit SHA làm key mặc định cho dependency cache

Nếu key chứa commit SHA, mỗi commit thường tạo cache mới dù dependency không thay đổi. Điều này làm giảm đáng kể tỷ lệ cache hit. Với dependency cache, hash lockfile và cấu hình dependency thường phù hợp hơn.

Ngược lại, với kết quả build phụ thuộc vào nội dung mã nguồn, task cache cần nhận diện các input của task. Không nên dùng một key tĩnh cho toàn bộ build output vì mã nguồn thay đổi có thể vẫn khôi phục đầu ra cũ.

### Phân biệt exact key và restore key

Một số nền tảng CI hỗ trợ key chính xác và danh sách khóa dự phòng (restore keys). Exact key biểu thị bộ đầu vào được mong đợi. Restore key cho phép tìm một cache gần khớp hơn khi không có exact match.

Restore key hữu ích với dependency cache có thể bổ sung dữ liệu mà không làm thay đổi dependency đã khóa. Nhưng fallback quá rộng có thể kéo theo metadata hoặc package không tương thích. Không nên dùng restore key rộng cho cache chứa build output hoặc generated files nếu chưa chứng minh tính an toàn.

Nếu dùng fallback, hãy:

1. Giữ các trường bất biến quan trọng như hệ điều hành, kiến trúc và loại công cụ.
2. Không fallback giữa các major version không tương thích.
3. Xác minh dependency bằng lockfile và checksum sau khi restore.
4. Chỉ lưu cache mới sau khi job hoàn tất thành công.
5. Ghi lại cache key thực tế và nguồn restore để có thể chẩn đoán.

## 4. Ví dụ cache dependency trong GitHub Actions

Ví dụ sau minh họa cache Gradle dựa trên hệ điều hành, wrapper properties và các file dependency lock:

~~~yaml
steps:
  - name: Checkout
    uses: actions/checkout@v4

  - name: Set up JDK
    uses: actions/setup-java@v4
    with:
      distribution: temurin
      java-version: '17'

  - name: Restore Gradle dependency cache
    uses: actions/cache/restore@v4
    with:
      path: |
        ~/.gradle/caches/modules-2
        ~/.gradle/wrapper/dists
      key: gradle-deps-linux-jdk17-<lockfile-hash>
      restore-keys: |
        gradle-deps-linux-jdk17-

  - name: Build
    run: ./gradlew --no-daemon clean check

  - name: Save Gradle dependency cache
    if: success()
    uses: actions/cache/save@v4
    with:
      path: |
        ~/.gradle/caches/modules-2
        ~/.gradle/wrapper/dists
      key: gradle-deps-linux-jdk17-<lockfile-hash>
~~~

Trong ví dụ, giá trị <lockfile-hash> là placeholder để biểu thị hash của lockfile và cấu hình dependency. Khi triển khai thực tế, hãy dùng expression hoặc bước tính hash phù hợp với các file đang có trong repository. Nếu dùng restore key rộng, chỉ dùng cho dependency cache có thể xác minh lại; không áp dụng cùng cách đó cho build output.

Ví dụ trên là cấu hình minh họa, cần điều chỉnh đường dẫn và phiên bản action theo repository. Không phải mọi thư mục trong GRADLE_USER_HOME đều nên được chia sẻ giữa runner. Tránh cache daemon state, file lock đang hoạt động, log tạm hoặc dữ liệu phụ thuộc hệ điều hành mà không có lý do rõ ràng.

### Cache Maven trong CI

Với Maven, thư mục local repository thường là ~/.m2/repository. Có thể cache thư mục này để tránh tải lại dependency và plugin:

~~~yaml
steps:
  - name: Checkout
    uses: actions/checkout@v4

  - name: Set up JDK
    uses: actions/setup-java@v4
    with:
      distribution: temurin
      java-version: '17'
      cache: maven

  - name: Verify
    run: ./mvnw -B clean verify
~~~

Tính năng cache Maven tích hợp trong action setup JDK là một lựa chọn tiện lợi. Cần xem key mà action sử dụng, file dependency được theo dõi và chính sách cache của repository. Nếu dự án dùng nhiều pom.xml, profile, BOM hoặc file cấu hình dependency riêng, cần bảo đảm các file đó được đưa vào quá trình xác định cache key.

Không nên cache file ~/.m2/settings.xml chứa credential hoặc cấu hình repository riêng tư. Cache chỉ nên chứa dữ liệu dependency có thể tái tạo. Credential phải được cấp qua secret hoặc cơ chế xác thực riêng của CI.

## 5. Cache dependency của Gradle và Maven có điểm khác nhau

### Gradle

Gradle lưu nhiều loại dữ liệu dưới GRADLE_USER_HOME, trong đó có:

- Wrapper distributions.
- Module artifacts và metadata.
- Dependency resolution cache.
- Build cache nếu được cấu hình lưu tại đó.
- Daemon state, log và dữ liệu hỗ trợ khác.

Không nên coi toàn bộ GRADLE_USER_HOME là một archive cache có thể chuyển tùy ý giữa mọi runner. Một số dữ liệu phụ thuộc phiên bản, hệ điều hành, tiến trình đang chạy hoặc cấu hình cụ thể. Ưu tiên cache đúng các vùng cần thiết, ví dụ module artifacts hoặc wrapper distributions; tách build cache nếu có chính sách riêng.

Gradle dependency cache và Gradle build cache cũng khác nhau. Dependency cache giữ các thư viện và metadata đã phân giải. Build cache lưu output của task có thể tái sử dụng dựa trên đầu vào task. Xóa dependency cache có thể làm build tải lại thư viện; tắt build cache buộc một số task chạy lại. Hai thao tác giúp khoanh vùng các nguyên nhân khác nhau.

### Maven

Maven local repository lưu dependency, plugin, metadata và các artifact đã tải hoặc cài cục bộ. Cache toàn bộ ~/.m2/repository có thể hữu ích, nhưng cần chú ý:

- Artifact SNAPSHOT có thể thay đổi theo thời gian.
- Metadata của repository có thể cũ.
- Plugin hoặc parent POM có thể được cập nhật theo chính sách repository.
- Nhiều dự án có thể dùng chung local repository với cấu hình khác nhau.
- Một lần build có thể để lại artifact được cài cục bộ mà không tồn tại trên repository từ xa.

Với dependency release bất biến và version được khai báo rõ, cache Maven thường dễ quản lý hơn. Với SNAPSHOT hoặc version động, nên giới hạn thời gian cache, tách namespace hoặc buộc cập nhật có chủ đích. Khi cần kiểm tra lại metadata, có thể dùng tùy chọn cập nhật phù hợp hoặc xóa đúng artifact bị nghi ngờ, thay vì xóa toàn bộ local repository ngay lập tức.

## 6. Phân biệt cache dependency và build cache

Đây là bước quan trọng khi kết quả build không nhất quán.

**Dependency cache** trả lời câu hỏi: công cụ đã tải và phân giải thư viện nào? Nếu dependency cache sai, build có thể dùng sai phiên bản hoặc file thư viện hỏng.

**Build cache** trả lời câu hỏi: với một tập input của task, output nào có thể tái sử dụng? Nếu build cache sai, build có thể lấy lại output được tạo từ input khác hoặc từ task khai báo thiếu dependency.

Với Gradle, task có thể tham gia build cache khi input/output được khai báo đúng và task phù hợp với việc cache. Một task tự đọc file không khai báo, đọc thời gian hệ thống hoặc truy vấn API bên ngoài nhưng vẫn được đánh dấu cacheable có thể trả lại output cũ không còn đúng.

Khi viết custom task:

- Khai báo mọi file, property và option ảnh hưởng output là input.
- Khai báo output rõ ràng.
- Tránh phụ thuộc vào trạng thái ngầm của workspace.
- Không đánh dấu task không xác định là cacheable.
- Chuẩn hóa đầu ra nếu thứ tự, timestamp hoặc đường dẫn có thể thay đổi.

Nếu task không thể mô tả đầy đủ input, cân nhắc tắt cache cho task đó cho đến khi có thể bảo đảm tính đúng đắn. Không nên bật cache cho mọi task chỉ để tăng tỷ lệ cache hit.

## 7. Cache cũ: xác định đúng thời điểm cần vô hiệu hóa

Cache nên được vô hiệu hóa khi một đầu vào quan trọng thay đổi đến mức dữ liệu cũ không còn tương thích. Những sự kiện thường cần thay đổi cache key hoặc cache version:

| Thay đổi | Cache cần xem xét | Lý do |
|---|---|---|
| Nâng Gradle hoặc Maven | Wrapper/tool cache, dependency cache và build cache liên quan | Định dạng cache hoặc cách phân giải có thể thay đổi |
| Nâng JDK | Build cache và cache chứa output phụ thuộc JDK | Bytecode và hành vi compiler có thể thay đổi |
| Thay lockfile hoặc BOM | Dependency cache hoặc key theo dependency | Bộ dependency mong đợi đã thay đổi |
| Thay plugin/build script | Build cache và key cấu hình | Cách tạo output có thể thay đổi |
| Thay compiler option | Build cache | Output biên dịch có thể khác |
| Thay hệ điều hành/kiến trúc | Tool cache và build cache phụ thuộc nền tảng | Binary hoặc native output có thể không tương thích |
| Thay định dạng cache | Cache schema/version | Dữ liệu cũ không còn đọc đúng |
| Thay nguồn repository | Dependency metadata và cache liên quan | Cùng tọa độ có thể được phân giải từ nguồn khác |

Không cần xóa cache chỉ vì có commit mới nếu đầu vào liên quan không thay đổi. Thay đổi cache key có chọn lọc giúp vừa giữ được hiệu quả tái sử dụng, vừa tránh dùng dữ liệu không tương thích.

### Dùng cache salt có chủ đích

Một cache salt là chuỗi phiên bản do nhóm quản lý, ví dụ cache-v3. Khi phát hiện cache cũ do thay đổi cấu trúc hoặc chính sách mà key chưa phản ánh, tăng salt để tạo namespace mới.

Không nên tăng salt sau mỗi lần build hoặc sau mọi commit. Làm vậy biến cache thành dữ liệu dùng một lần và khiến nhóm mất khả năng nhận biết đầu vào nào thực sự cần thay đổi.

## 8. Cache hỏng: quy trình khoanh vùng và phục hồi

Khi nghi ngờ cache hỏng, xử lý theo phạm vi nhỏ trước:

**Bước 1: Ghi lại bằng chứng.** Lưu run ID, commit SHA, cache key, restore key, log tải/giải nén và lỗi cụ thể. Ghi nhận runner, hệ điều hành, JDK và build tool.

**Bước 2: Tái hiện trên cùng đầu vào.** Chạy lại cùng commit và cấu hình. Nếu lỗi chỉ xuất hiện trên một runner hoặc một lần restore, kiểm tra khác biệt về workspace và cache nguồn.

**Bước 3: Chạy đối chứng không dùng cache nghi ngờ.** Tắt restore cache hoặc dùng cache key mới cho đúng phạm vi. Nếu build sạch vẫn lỗi, nguyên nhân có thể nằm ở mã nguồn, dependency hoặc môi trường.

**Bước 4: Xóa đúng mục bị lỗi.** Nếu xác định một artifact hoặc metadata cụ thể bị hỏng, xóa đúng mục đó trong local cache hoặc tạo namespace cache mới. Tránh xóa toàn bộ cache dùng chung khi chưa cần thiết.

**Bước 5: Tải lại và xác minh.** Lấy dependency từ repository tin cậy, kiểm tra checksum nếu có, chạy build và test. Lưu cache mới chỉ sau khi job hoàn tất thành công.

**Bước 6: So sánh kết quả.** So sánh log, dependency tree, artifact digest và cache key giữa lần chạy sạch và lần chạy có cache.

**Bước 7: Tìm nguyên nhân gốc.** Kiểm tra key thiếu đầu vào, ghi cache đồng thời, task khai báo input/output thiếu, repository trả dữ liệu thay đổi hoặc quy trình upload/download bị gián đoạn.

### Ví dụ khoanh vùng với Gradle

Có thể tách dependency cache và build cache để xác định lớp gây lỗi:

~~~bash
# Chạy build và không dùng build cache
./gradlew --no-build-cache clean check

# Buộc làm mới dependency metadata theo yêu cầu
./gradlew --refresh-dependencies clean check

# Xem các Java toolchain được Gradle phát hiện
./gradlew -q javaToolchains
~~~

Hai tùy chọn đầu không có cùng tác dụng. --no-build-cache tắt việc lấy/lưu output từ build cache cho lần chạy đó. --refresh-dependencies yêu cầu Gradle kiểm tra lại trạng thái dependency theo cơ chế phân giải của nó; không đồng nghĩa xóa toàn bộ mọi cache trên máy.

Chỉ dùng --refresh-dependencies khi cần kiểm tra dependency resolution. Nó có thể làm tăng tải mạng và thời gian build. Nếu nghi ngờ một file JAR cụ thể bị hỏng, có thể xác định tọa độ dependency rồi xóa đúng mục tương ứng trong Gradle cache để tải lại.

### Ví dụ khoanh vùng với Maven

~~~bash
# Chạy Maven với chế độ cập nhật metadata/dependency từ repository
./mvnw -B -U clean verify
~~~

Tùy loại repository và phiên bản dependency, -U yêu cầu Maven kiểm tra cập nhật cho snapshot và release đã thiếu. Nó không phải lệnh xóa toàn bộ local repository. Nếu một artifact cụ thể bị hỏng, xác định tọa độ groupId/artifactId/version rồi xóa đúng thư mục artifact trong ~/.m2/repository để Maven tải lại.

Không xóa thư mục local repository trong lúc một Maven process khác đang sử dụng. Nếu nhiều job cùng dùng một repository chia sẻ, hãy dừng hoặc cô lập các job liên quan trước khi dọn dữ liệu.

## 9. Kết quả không nhất quán: so sánh build sạch và build có cache

Một quy trình đối chứng giúp phân biệt lỗi do cache với lỗi không xác định khác:

| Lần chạy | Workspace | Cache | Mục đích |
|---|---|---|---|
| A | Mới hoàn toàn | Không restore cache | Lấy mốc build sạch |
| B | Mới hoàn toàn | Restore cache hiện tại | Kiểm tra ảnh hưởng của cache |
| C | Mới hoàn toàn | Cache key mới | Kiểm tra namespace cache cũ |
| D | Cùng cấu hình với A | Chạy lại build sạch | Kiểm tra tính ổn định của chính build |

So sánh các kết quả:

- Dependency tree và phiên bản thực tế được phân giải.
- JDK, build tool, plugin và cấu hình môi trường.
- Danh sách file trong artifact.
- Nội dung file và checksum.
- Test result, generated source và log của task.
- Cache hit/miss và nguồn cache được khôi phục.

Nếu A và B khác nhau nhưng A và D giống nhau, cache là một nghi vấn mạnh. Nếu A và D cũng khác nhau, build có thể đang phụ thuộc vào thời gian, mạng, dữ liệu hoặc tác vụ không xác định. Nếu A, B và C đều thất bại giống nhau, cần điều tra mã nguồn, dependency hoặc môi trường trước khi tiếp tục xóa cache.

### So sánh artifact

Khi yêu cầu là tạo artifact byte-for-byte giống nhau, có thể tính SHA-256:

~~~bash
# Linux
sha256sum build/libs/application.jar

# PowerShell
Get-FileHash .\build\libs\application.jar -Algorithm SHA256
~~~

Digest khác nhau cho biết nội dung file khác nhau, nhưng chưa chỉ ra nguyên nhân. Hãy giải nén và so sánh từng file để tìm khác biệt như timestamp, thứ tự entry, manifest, generated metadata hoặc nội dung được sinh từ thời gian build.

Một artifact có thể khác digest do timestamp archive dù bytecode và logic không đổi. Ngược lại, hai artifact có tên giống nhau không bảo đảm nội dung giống nhau. Nên lưu digest cùng build ID, commit SHA và thông tin môi trường.

## 10. Kiểm soát cache khi có nhiều job chạy song song

Nhiều job có thể cùng khôi phục hoặc ghi cache. Nếu chúng chia sẻ trực tiếp một thư mục đang được sử dụng, có thể xảy ra:

- File bị ghi dở khi job khác đang đọc.
- Metadata hoặc lock file bị xung đột.
- Job thất bại nhưng vẫn để lại trạng thái trung gian.
- Hai job lưu nội dung khác nhau dưới cùng một key.
- Runner bị dừng trước khi upload cache hoàn tất.

Ưu tiên cơ chế cache của nền tảng CI có quy trình upload/download riêng và cache key rõ ràng. Với local cache dùng chung, cần cơ chế khóa, ghi tạm rồi thay thế nguyên tử khi có thể, và tránh để nhiều process sửa cùng một vùng dữ liệu không an toàn.

Nếu job chạy song song chỉ cần đọc dependency cache đã hoàn chỉnh, có thể cho phép chúng dùng chung cache theo cách build tool hỗ trợ. Nhưng không nên tự chia sẻ daemon state hoặc thư mục output của task giữa nhiều process nếu công cụ không bảo đảm an toàn.

### Chỉ lưu cache sau khi công việc thành công

Một job thất bại giữa chừng có thể đã tải một phần dependency hoặc tạo output dở dang. Nếu hệ thống upload cache bất kể trạng thái, lần sau có thể khôi phục dữ liệu chưa hoàn chỉnh.

Thông thường, chỉ lưu cache sau khi các bước xác minh thành công. Với dependency cache, cần biết công cụ có thể phục hồi dữ liệu tải dở hay không; với build cache, chỉ publish output khi task hoàn tất hợp lệ và metadata đầu vào đã được ghi nhận đầy đủ.

## 11. Bảo mật và phạm vi tin cậy của cache

Cache có thể chứa mã nguồn đã sinh, dependency, metadata, file cấu hình và đôi khi cả dữ liệu nhạy cảm nếu đường dẫn cache được chọn quá rộng. Cần xem cache là một kênh trao đổi dữ liệu giữa các lần chạy:

- Không cache file chứa secret, access token, credential hoặc settings có mật khẩu.
- Không cache toàn bộ home directory của người dùng nếu chưa kiểm tra nội dung.
- Tách cache theo repository, dự án, hệ điều hành và mức độ tin cậy khi cần.
- Không cho workflow từ pull request không đáng tin cậy ghi đè cache được workflow phát hành tin cậy sử dụng.
- Xác minh checksum hoặc chữ ký của dependency/artifact theo chính sách.
- Hạn chế quyền truy cập cache và log thông tin đủ để truy vết nguồn tạo.
- Không thực thi script hoặc binary lấy từ cache không rõ nguồn trong môi trường có secret hoặc quyền cao.

Một cache bị đầu độc (cache poisoning) có thể khiến job tin cậy khôi phục file do một workflow ít tin cậy tạo ra. Hậu quả có thể là chạy mã độc, dùng dependency đã bị thay thế hoặc tạo artifact sai. Cần thiết kế quyền ghi/đọc theo trust boundary, không chỉ theo tên branch.

Với các pipeline có quyền publish hoặc deploy, cân nhắc chỉ cho phép chúng đọc cache được tạo bởi nhánh hoặc workflow tin cậy. Nếu nền tảng không cung cấp ranh giới truy cập đủ chặt, hãy dùng cache namespace riêng hoặc bỏ cache ở bước nhạy cảm.

## 12. Theo dõi hiệu quả và chất lượng cache

Tỷ lệ cache hit cao không phải mục tiêu duy nhất. Cache có ích khi giảm thời gian và chi phí mà không làm tăng lỗi hoặc tạo kết quả sai.

Một dashboard có thể theo dõi:

| Chỉ số | Ý nghĩa |
|---|---|
| Cache hit rate | Tỷ lệ yêu cầu khôi phục cache thành công |
| Restore duration | Thời gian tải và giải nén cache |
| Save duration | Thời gian đóng gói và upload cache |
| Cache size | Dung lượng cache và tốc độ tăng |
| Dependency download time | Thời gian tải dependency khi cache miss |
| Build duration with/without cache | Mức cải thiện thực tế của cache |
| Cache-related failure rate | Tỷ lệ lỗi có liên quan đến restore, checksum hoặc dữ liệu cache |
| Clean-build consistency | Mức độ giống nhau giữa các lần build sạch |
| Cache invalidation frequency | Tần suất phải đổi key hoặc xóa cache |

Nếu cache lớn đến mức thời gian restore gần bằng thời gian tải dependency, lợi ích có thể không đáng kể. Hãy giới hạn đường dẫn, loại bỏ dữ liệu không cần thiết và đánh giá cache theo tổng thời gian restore + build + save.

Nên xem thêm tỷ lệ build thất bại sau cache hit. Một cache hit nhanh nhưng làm tăng lỗi không nhất quán là cache đang gây hại cho luồng giao hàng.

## 13. Checklist xử lý sự cố cache

Khi build có dấu hiệu dùng cache sai, có thể đi theo checklist:

- [ ] Xác định loại cache liên quan: dependency, build output, workspace, tool hay CI cache.
- [ ] Ghi lại commit SHA, run ID, runner, JDK, build tool và cache key.
- [ ] Xác định cache được restore từ exact key hay restore key.
- [ ] Kiểm tra lockfile, build script, plugin, toolchain và các đầu vào đã được phản ánh trong key chưa.
- [ ] Chạy đối chứng không dùng đúng loại cache đang nghi ngờ.
- [ ] Kiểm tra checksum, archive, metadata và dependency tree.
- [ ] Nếu cần, tạo cache key mới hoặc xóa đúng mục bị hỏng.
- [ ] Chạy build sạch nhiều lần để kiểm tra tính ổn định.
- [ ] So sánh artifact digest và nội dung nếu cần tái lập byte-for-byte.
- [ ] Kiểm tra quyền ghi/đọc cache, job song song và nguy cơ cache poisoning.
- [ ] Chỉ lưu cache mới sau khi dữ liệu đã được xác minh.
- [ ] Ghi lại nguyên nhân và thay đổi cache key hoặc quy trình để lỗi không lặp lại.

## 14. Quy tắc thực hành

- Thiết kế cache theo loại dữ liệu và đầu vào thực sự ảnh hưởng đến dữ liệu đó.
- Dùng lockfile và phiên bản công cụ rõ ràng; không dùng cache để che giấu dependency không ổn định.
- Giữ exact key đủ chặt; chỉ dùng restore key khi đã hiểu rủi ro tương thích.
- Tách dependency cache khỏi build cache và artifact phát hành.
- Khi điều tra, tắt đúng loại cache để đối chứng trước khi xóa hàng loạt.
- Chỉ xóa mục cache đã khoanh vùng hoặc tạo namespace mới khi cần vô hiệu hóa.
- Tránh chia sẻ dữ liệu ghi đang hoạt động giữa các job song song nếu công cụ không bảo đảm an toàn.
- Không lưu secret hoặc cho workflow ít tin cậy ghi cache mà pipeline phát hành tin cậy sẽ sử dụng.
- Theo dõi cả hiệu năng cache và lỗi sau cache hit; build sạch vẫn phải chạy đúng.

Cache tốt giúp CI/CD nhanh hơn mà không làm thay đổi ý nghĩa của build. Khi key phản ánh đúng đầu vào, cache được tách theo mục đích, dữ liệu được xác minh và quy trình phục hồi có thể khoanh vùng, nhóm có thể tận dụng cache mà vẫn giữ kết quả build đáng tin cậy. Nếu build chỉ đúng khi có hoặc không có một cache cụ thể, đó là tín hiệu cần điều tra tính xác định của dependency, task và môi trường.
