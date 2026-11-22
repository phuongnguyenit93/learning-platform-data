# Đọc release notes và breaking change của thư viện

Nâng JDK là một phần của quá trình migration Java; phần còn lại thường nằm ở các thư viện mà ứng dụng sử dụng. Một chương trình vẫn biên dịch bằng JDK mới có thể thất bại khi đổi phiên bản framework, JSON serializer, JDBC driver, logging library, HTTP client hoặc build plugin. Ngược lại, một thư viện cũ có thể khởi động được nhưng tồn tại rủi ro bảo mật, không hỗ trợ JPMS, hoặc chỉ tình cờ hoạt động nhờ quyền truy cập nội bộ JDK.

Do đó, **đọc release notes và breaking changes** là kỹ năng quản lý dependency quan trọng. Mục tiêu không phải lướt qua danh sách tính năng mới, mà là chuyển thông tin phát hành của tác giả thư viện thành một **danh sách tác động có thể kiểm chứng** đối với source code, binary, cấu hình, dữ liệu, môi trường chạy và quy trình phát hành của chính ứng dụng.

Bài học trình bày quy trình thực tế từ xác định phiên bản đang chạy, tìm tài liệu gốc, phân loại thay đổi, đọc migration guide qua nhiều version, đến lập ma trận ảnh hưởng và kiểm thử rollout. Các ví dụ minh họa giả định sẽ được ghi rõ để tránh nhầm với lịch sử phát hành thực tế của một thư viện cụ thể.

## 1. Release notes là gì và tại sao phải đọc?

**Release notes** là tài liệu mô tả những điểm đáng chú ý của một bản phát hành: tính năng mới, lỗi đã sửa, thay đổi API, yêu cầu nền tảng, vấn đề đã biết và đôi khi cả hướng dẫn migration. Tùy dự án, các thông tin này được tổ chức thành:

- **Release page:** mô tả từng bản phát hành, có thể gắn với một tag và artifact.
- **CHANGELOG:** nhật ký thay đổi theo version, đôi khi chỉ là danh sách commit hoặc issue.
- **Migration/upgrade guide:** hướng dẫn chuyển phiên bản, tập trung vào thay đổi làm code cũ cần sửa.
- **Compatibility matrix:** bảng kết hợp phiên bản JDK, framework, server, driver hoặc plugin được hỗ trợ.
- **Deprecation policy:** thời điểm API bị cảnh báo, bị thay thế và có thể bị loại bỏ.
- **API reference/Javadoc:** hợp đồng chi tiết của từng phương thức, class và module.
- **Security advisories:** các phiên bản bị ảnh hưởng, bản sửa và biện pháp giảm thiểu rủi ro.
- **Issue tracker/commit/tag diff:** chứng cứ bổ sung khi release notes chưa đủ rõ.

Không phải dự án nào cũng có tất cả các loại tài liệu trên. Chỉ đọc dòng “Bug fixes and improvements” thường không đủ để kết luận bản nâng cấp không có breaking change.

### 1.1. Ba câu hỏi cần trả lời sau khi đọc

1. **Cái gì thay đổi?** API, mặc định, dependency, minimum JDK, data format, bảo mật hay vận hành?
2. **Ứng dụng có dùng phần đó không?** Có import class, gọi API, bật feature, truyền dữ liệu hoặc phụ thuộc gián tiếp nào chịu ảnh hưởng?
3. **Làm thế nào chứng minh không bị hỏng?** Cần sửa mã, cập nhật cấu hình, đổi dependency, chạy test tương thích hoặc triển khai theo thứ tự nào?

Đọc xong tài liệu mà chưa trả lời ba câu này thì chưa chuyển được release notes thành kế hoạch migration có thể thực hiện.

## 2. Bắt đầu từ dependency thật sự được sử dụng

Trước khi tra cứu release notes, cần biết ứng dụng đang chạy chính xác phiên bản thư viện nào. File `pom.xml` hoặc `build.gradle` chỉ thể hiện **yêu cầu khai báo**; dependency resolution có thể chọn một phiên bản khác do BOM, dependency management, version constraints, conflict resolution hoặc transitive dependencies.

Giả sử ứng dụng khai báo trực tiếp thư viện `com.example:report-core:1.4.0`, nhưng một framework hoặc dependency management có thể điều chỉnh phiên bản được resolve. Nếu đọc changelog của phiên bản khai báo mà không xác nhận artifact đầu ra, nhóm có thể phân tích sai khoảng nâng cấp.

### 2.1. Maven: xem dependency tree

```bash
mvn dependency:tree
```

Để tập trung vào một artifact cụ thể:

```bash
mvn dependency:tree \
    -Dincludes=com.fasterxml.jackson.core:jackson-databind
```

Lệnh trong ví dụ sử dụng Maven Dependency Plugin khi plugin và môi trường build đã sẵn sàng. Xem output để biết đường đi nào kéo dependency vào và version nào được chọn.

Với project nhiều module, chạy ở module phù hợp hoặc dùng tùy chọn chọn module của Maven. Ngoài ra, `mvn help:effective-pom` giúp quan sát cấu hình sau khi kế thừa parent POM và dependency management, nhưng **effective POM không tự thay thế dependency tree** trong việc giải thích các artifact thực sự được resolve.

### 2.2. Gradle: xem configuration cụ thể

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Để biết vì sao một thư viện được chọn:

```bash
./gradlew dependencyInsight \
    --dependency jackson-databind \
    --configuration runtimeClasspath
```

Configuration `compileClasspath` và `runtimeClasspath` có thể khác nhau; dự án Android, Kotlin hoặc multi-project còn có các configuration khác. Chọn configuration phản ánh nơi lỗi thực sự xuất hiện.

Trên Windows dùng `gradlew.bat` hoặc cách gọi Gradle phù hợp với dự án. Những lệnh này là ví dụ cho quy trình quản lý dependency; việc đọc release notes không đòi hỏi phải sửa project hoặc chạy build ngay.

### 2.3. Ghi đủ tọa độ artifact

Với Maven, nhận diện dependency bằng:

```text
groupId : artifactId : version [: classifier]
```

Ví dụ:

```text
com.fasterxml.jackson.core:jackson-databind:2.x.y
```

`2.x.y` ở đây là ký hiệu đại diện, không phải một version thực tế. Khi lập hồ sơ migration, phải ghi **version chính xác** và cả repository/source cung cấp artifact.

Nên ghi thêm:

- Checksum của artifact khi cần truy vết.
- Các thư viện liên quan cùng họ và phiên bản của chúng.
- Framework/BOM đang quản lý phiên bản.
- Module nơi dependency được dùng (compile, runtime, test hoặc plugin classpath).
- JDK runtime và compiler được hỗ trợ.
- Những nơi dependency hiện diện: service, batch job, plugin, container image.

**Không nhầm:** cùng tên thư viện nhưng khác groupId, classifier hoặc artifact packaging có thể là các sản phẩm khác nhau; changelog của một fork không tự áp dụng cho artifact chính thức.

## 3. Tìm nguồn release notes đáng tin cậy

Nên bắt đầu từ kênh chính thức của dự án:

1. Trang tài liệu hoặc trang release của nhà phát triển.
2. Repository chính thức với tags/releases và file `CHANGELOG.md`.
3. Migration guide tương ứng chính xác với cặp phiên bản.
4. Javadoc/API reference của phiên bản cũ và mới.
5. Compatibility matrix với JDK và framework.
6. Security advisory chính thức hoặc bản ghi vulnerability được dự án xác nhận.
7. Commit/issue/PR liên quan khi cần làm rõ thông tin.

Những nguồn như Maven Central hoặc repository artifact giúp xác minh tọa độ/version và metadata. Chúng không nhất thiết có đầy đủ giải thích breaking changes. Blog cá nhân, bản tổng hợp từ công cụ tự động hoặc bài trả lời diễn đàn có thể hữu ích để định hướng, nhưng cần đối chiếu tài liệu chính thức trước khi dùng làm cơ sở quyết định production.

### 3.1. Kiểm tra đúng version, branch và tag

Một dự án có thể có:

```text
1.8.x  : maintenance branch
2.0.x  : new major line
2.1.x  : current feature line
```

Changelog của nhánh `main` chưa chắc khớp với bản `1.8.7` đang được ứng dụng sử dụng. Phải xác định tài liệu áp dụng cho **tag/version đã phát hành**, không chỉ source code mới nhất.

Ví dụ, upgrade từ `1.8.7` sang `2.1.3` có thể phải đọc:

- Các mục release giữa `1.8.7` và `1.8.x` cuối cùng, nếu cần.
- Migration guide từ `1.x` lên `2.0`.
- Breaking changes và fixes trong `2.0.x`.
- Các thay đổi tiếp theo từ `2.0` đến `2.1.3`.

Không nên bỏ qua bản major trung gian chỉ vì mục tiêu cuối cùng là phiên bản mới hơn.

### 3.2. Đọc “Known issues” và “Upgrade notes”

Các thông tin này thường ảnh hưởng trực tiếp tới rollout:

- Một lỗi tồn tại trong phiên bản mục tiêu.
- Một cấu hình cũ cần bị loại bỏ.
- Một phiên bản driver/agent không tương thích.
- Một lệnh chuyển đổi dữ liệu phải chạy trước khi khởi động bản mới.
- Một feature bị tắt mặc định vì bảo mật.

Nếu mục tiêu nâng cấp đang có known issue ảnh hưởng đến luồng cốt lõi, có thể cần chọn một bản patch khác trong cùng nhánh hoặc thay thứ tự rollout. Đừng chỉ xem danh sách tính năng mới và bỏ qua ghi chú triển khai.

## 4. Hiểu đúng SemVer nhưng đừng tin tuyệt đối vào số phiên bản

Semantic Versioning thường được mô tả bằng:

```text
MAJOR.MINOR.PATCH
```

Theo SemVer, major thường gắn với thay đổi API không tương thích, minor với tính năng vẫn tương thích và patch với sửa lỗi tương thích. Tuy nhiên:

- Không phải mọi thư viện Java đều theo SemVer.
- Dự án có thể dùng version theo ngày, train release hoặc hệ thống riêng.
- Bản `1.0` có thể có chính sách khác với `0.x`.
- Một security fix trong patch có thể chủ động từ chối hành vi cũ không an toàn.
- Thay đổi transitive dependency trong minor/patch vẫn có thể ảnh hưởng runtime.
- “Binary-compatible” không đồng nghĩa “behavior-compatible” trong mọi trường hợp.

Vì vậy, **số version là tín hiệu để ưu tiên đọc**, không thay thế release notes và kiểm thử.

### 4.1. Các mức ưu tiên đọc

| Kiểu nâng cấp | Mức chú ý ban đầu | Điều cần ưu tiên |
|---|---|---|
| Patch trong cùng nhánh | Thấp hơn, nhưng không bỏ qua. | Security fix, behavioral regression, dependency changes, JDK fixes. |
| Minor/feature | Trung bình. | API additions, default changes, deprecations, transitive dependencies. |
| Major | Cao. | Removed/renamed APIs, constructor changes, configuration migration, Java baseline, data format. |
| Đổi họ framework hoặc serializer | Rất cao. | Toàn bộ contract, ecosystem integration và deployment strategy. |
| Đổi groupId/artifact hoặc fork | Cao. | Provenance, license, security, namespace và compatibility policy. |

Trong thực tế, việc từ một patch cũ lên patch mới sau nhiều năm có thể tạo nhiều thay đổi tích lũy hơn một lần nâng minor rất nhỏ.

## 5. Phân loại breaking change theo các lớp tương thích

Một thư viện có thể “không tương thích” theo nhiều nghĩa:

| Loại | Triệu chứng | Ví dụ |
|---|---|---|
| **Source compatibility** | Code cũ không biên dịch lại được. | Class/method bị xóa, đổi signature hoặc package. |
| **Binary compatibility** | Bytecode cũ tải/chạy với thư viện mới bị lỗi liên kết. | `NoSuchMethodError`, `NoClassDefFoundError`, `AbstractMethodError`. |
| **Behavioral compatibility** | Code vẫn chạy nhưng kết quả khác. | Default timeout, retry policy hoặc validation khác. |
| **Configuration compatibility** | Tên property, default flag hoặc file config thay đổi. | Một option cũ bị thay tên, security option bị tắt. |
| **Data/wire compatibility** | Consumer không đọc đúng dữ liệu mới/cũ. | JSON field, XML namespace, database schema hoặc message format đổi. |
| **Runtime/JDK compatibility** | Thư viện yêu cầu phiên bản Java cao hơn hoặc quyền module mới. | Class file version cao; reflection bị chặn bởi JPMS. |
| **Operational compatibility** | Startup, metrics, thread pool, deployment hoặc tài nguyên thay đổi. | Cơ chế shutdown mới, logging format đổi. |
| **Security compatibility** | Dữ liệu/hành vi cũ không còn được chấp nhận vì kiểm soát an toàn. | Chặn thuật toán yếu hoặc input không an toàn. |
| **Dependency ecosystem** | Phiên bản thư viện đi kèm không tương thích. | Framework kéo driver/parser phiên bản mới. |

Các loại trên có thể đồng thời xảy ra. Một release major có thể đổi API Java và đồng thời đổi JSON format. Nếu chỉ sửa lỗi compile mà bỏ qua contract dữ liệu, migration vẫn chưa hoàn tất.

## 6. Breaking change về source API

Ví dụ **giả định** thư viện `com.example:billing-client` đổi API giữa bản 1.x và 2.x:

**API cũ:**

```java
public final class BillingClient {
    public Receipt charge(String accountId, long amountMinorUnits) {
        // Old API
        throw new UnsupportedOperationException();
    }
}
```

Ứng dụng gọi:

```java
Receipt receipt = client.charge("A-100", 5000L);
```

**API mới:**

```java
public final class BillingClient {
    public Receipt submitPayment(PaymentRequest request) {
        // New API
        throw new UnsupportedOperationException();
    }
}
```

Code cũ sẽ báo lỗi compile vì `charge(String, long)` không còn tồn tại.

### 6.1. Cách đọc ghi chú API migration

Khi release notes ghi “rename `charge` to `submitPayment`”, vẫn cần kiểm tra:

1. Có thay đổi kiểu input và cách validate không?
2. Có đổi đơn vị tiền (minor units so với decimal string) không?
3. Có đổi kiểu trả về, synchronous/asynchronous contract không?
4. Có đổi checked exception hoặc error code không?
5. Có thay đổi idempotency/transaction semantics không?
6. Có adapter deprecated còn tồn tại trong một phiên bản chuyển tiếp không?

Một cuộc đổi tên API đơn giản trên giấy có thể che giấu thay đổi hành vi lớn hơn.

### 6.2. Kiểm tra import và package relocation

Release notes đôi khi ghi:

```text
Old package: com.example.billing.v1
New package: com.example.billing.api
```

Đây là ví dụ minh họa. Đối với dự án thật, phải xác nhận artifact ID, package, module name và hướng dẫn tự động migration (nếu có). Không tự giả định rằng mọi rename package đều được thư viện hỗ trợ bằng forwarding class.

## 7. Breaking change về binary compatibility

Binary compatibility liên quan tới khả năng class file đã biên dịch liên kết với thư viện mới mà không cần biên dịch lại.

Giả sử ứng dụng được biên dịch với thư viện có:

```java
public String normalize(String input)
```

Sau đó thư viện ở runtime chỉ còn:

```java
public String normalize(CharSequence input)
```

Đối với source code, lời gọi có thể vẫn hợp lệ sau khi biên dịch lại. Nhưng bytecode cũ chứa method descriptor tham chiếu `normalize(Ljava/lang/String;)Ljava/lang/String;`; nếu thư viện mới không còn method đó, JVM có thể ném `NoSuchMethodError` khi thực thi.

### 7.1. Các lỗi runtime thường gặp

| Lỗi | Ý nghĩa sơ bộ | Bước điều tra |
|---|---|---|
| `NoSuchMethodError` | Method descriptor được bytecode gọi không có trong class runtime. | So sánh API/binary, dependency tree và classpath runtime. |
| `NoSuchFieldError` | Field mà bytecode tham chiếu không còn phù hợp. | So sánh field type/name và artifact thực sự được nạp. |
| `NoClassDefFoundError` | Class cần thiết không thể có mặt/khởi tạo tại runtime. | Kiểm tra classpath, module path, transitive dependencies và lỗi gốc. |
| `ClassNotFoundException` | Class loader không tìm thấy class được yêu cầu bằng tên. | Kiểm tra artifact packaging và class loader hierarchy. |
| `AbstractMethodError` | Một instance không có implementation phù hợp với method cần gọi. | Kiểm tra interface/API evolution và các implementation cũ. |
| `IllegalAccessError` | Liên kết gặp quyền truy cập class/member không hợp lệ. | Kiểm tra public/protected/package access, JPMS exports. |
| `UnsupportedClassVersionError` | Class file dùng major version mới hơn JVM hiểu được. | Kiểm tra minimum Java version của thư viện. |

Một ngoại lệ runtime không phải lúc nào cũng do **release mục tiêu tự nó sai**. Ví dụ `NoSuchMethodError` có thể xuất hiện khi hai phiên bản thư viện cùng tồn tại trên classpath hoặc khi dependency resolution chọn một bản không phù hợp với framework.

### 7.2. Công cụ so sánh API

Các công cụ có thể hỗ trợ:

- `japicmp`: so sánh API Java và kiểm tra binary/source incompatibility giữa JAR cũ/mới.
- `Revapi`: kiểm tra API compatibility theo các rule và extension.
- `jdeps`: tìm quan hệ phụ thuộc lớp/package/module và internal API.
- `javap`: xem method descriptor và class file metadata.

Ví dụ tra cấu trúc method sau khi có artifact:

```bash
javap -classpath library.jar -s com.example.billing.BillingClient
```

Kết quả chỉ là một phần của bằng chứng. Công cụ API diff không tự biết hợp đồng nghiệp vụ, format dữ liệu, timeout, lỗi bảo mật hoặc cơ chế reflection. Đừng coi báo cáo “binary compatible” là bảo đảm toàn bộ migration an toàn.

## 8. Behavioral breaking change nguy hiểm vì thường không báo lỗi

Đây là nhóm thay đổi dễ lọt qua compile và unit tests đơn giản nhất.

Ví dụ **giả định** một HTTP client thay chính sách:

| Trường hợp | Phiên bản cũ | Phiên bản mới |
|---|---|---|
| Connection timeout mặc định | Không giới hạn cụ thể | 10 giây |
| Retry tự động | Retry với một số response | Tắt retry mặc định |
| Redirect | Cho phép một kiểu redirect | Yêu cầu opt-in |
| TLS validation | Chấp nhận cấu hình legacy | Từ chối thuật toán yếu |

Các giá trị là minh họa, **không phải release notes của HTTP client có thật**.

Đọc mỗi dòng “Changed default retry policy” cần chuyển thành câu hỏi:

- Request nào được phép retry?
- Request có idempotent không?
- Ai đang thực hiện retry: client, service mesh hay gateway?
- Timeout tổng và timeout từng pha có khác nhau?
- Mất retry có làm tăng lỗi ngắn hạn?
- Giữ retry cũ có nguy cơ tạo giao dịch trùng không?

Một tùy chọn mặc định thay đổi có thể cần sửa test, metrics, SLO và circuit-breaker configuration.

### 8.1. Tránh khôi phục mặc định cũ vô điều kiện

Nếu thay đổi được tạo ra để khắc phục lỗi hoặc bảo mật, bật lại behavior cũ có thể không phù hợp. Trước khi đặt flag, xác định:

1. Vì sao thư viện thay mặc định?
2. Có cảnh báo deprecation hoặc bảo mật không?
3. Hệ thống có dựa vào behavior cũ như một phần hợp đồng nghiệp vụ không?
4. Có giải pháp dài hạn an toàn hơn không?
5. Nếu dùng workaround tạm, có owner và thời điểm gỡ không?

## 9. Configuration và defaults: tìm cả tên cũ lẫn tên mới

Một release note có thể nói “property X is renamed to Y”, “option Z is removed” hoặc “default is now false”.

Ví dụ giả định:

```properties
# Old configuration
example.client.retry.enabled=true
example.client.timeoutMillis=30000
```

Và:

```properties
# New configuration
example.client.retry.mode=idempotent-only
example.client.request-timeout=30s
```

Đây không chỉ là thay key. Giá trị `true` không tương đương hoàn toàn với `idempotent-only`, đơn vị timeout có thể thay đổi, và framework có thể bỏ qua key cũ mà không cảnh báo.

Một bảng migration hữu ích:

| Old configuration | New configuration | Thay đổi ngữ nghĩa | Hành động |
|---|---|---|---|
| `retry.enabled=true` | `retry.mode=idempotent-only` | Chỉ retry thao tác idempotent. | Đánh giá luồng giao dịch. |
| `timeoutMillis=30000` | `request-timeout=30s` | Có thể đổi phạm vi timeout. | Test connect/read/total timeout. |
| Key cũ bị loại | Không có key thay thế | Feature removed. | Xóa config và thay thiết kế. |

Release notes thường chỉ nêu tên thay đổi; nhiệm vụ của nhóm ứng dụng là tìm **mọi nơi cấu hình được gán**: source, deployment manifests, environment variables, secret store, feature flags, test fixtures và template vận hành.

## 10. Minimum JDK và vấn đề tương thích với runtime

Một thư viện có thể nâng minimum supported Java version. Đây là breaking change quan trọng khi ứng dụng còn phải chạy trên nhiều JDK.

Ví dụ **giả định**:

```text
library 1.x -> supports Java 8+
library 2.x -> requires Java 17+
```

Nếu sản phẩm vẫn hỗ trợ runtime Java 11, không thể dùng artifact 2.x đó trong một tiến trình Java 11 chỉ bằng cách cấu hình `--release 11` cho code ứng dụng. Library class file có thể dùng major version 61 (Java 17), mà Java 11 không thể tải.

Một số mốc class file:

| Java | Major version |
|---:|---:|
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |
| 25 | 69 |

Kiểm tra metadata class khi có JAR:

```bash
javap -verbose -classpath library.jar com.example.library.Api
```

Tìm `major version`. Giá trị này cung cấp dấu hiệu về class file, nhưng compatibility còn phụ thuộc API, native libraries, reflection, preview features và các thành phần phụ trợ.

### 10.1. Từ “works on” khác “supported on”

Một thư viện có thể tình cờ chạy trên JDK mới nhưng tác giả **chỉ kiểm thử hoặc hỗ trợ** một tập version cụ thể. Cần đọc compatibility matrix chính thức:

- JDK tối thiểu để chạy.
- JDK được CI/test matrix của dự án hỗ trợ.
- Những JDK có thể dùng để biên dịch thư viện.
- Phiên bản framework, servlet container, driver hoặc Jakarta EE liên quan.
- Operating system/architecture hỗ trợ nếu thư viện có JNI/native code.

“JAR nạp được trên JDK 21” không tự chứng minh nhà cung cấp hỗ trợ mọi tính năng của nó trên JDK 21.

## 11. JPMS, reflection và service loading

Khi nâng từ JDK cũ hoặc một thư viện không modular sang phiên bản mới, lưu ý:

- `module-info.java` có thể xuất hiện hoặc thay đổi.
- Automatic module name có thể khác với tên module đã khai báo.
- Package `exports`/`opens` thay đổi khiến code reflect bị lỗi.
- ServiceLoader provider metadata thay đổi từ `META-INF/services` sang `provides ... with ...`.
- Module không còn được resolve tự động.
- Một thư viện đổi package nhưng không đổi artifact name, hoặc ngược lại.

Ví dụ:

```text
java.lang.reflect.InaccessibleObjectException:
  module com.example.model does not "opens ..."
```

Một lỗi như vậy không tự cho thấy serializer bị hỏng. Có thể bản nâng cấp bắt đầu chạy dưới module path, hoặc library mới cố đọc private member thay vì dùng public constructor/getter.

Để đọc descriptor của modular JAR:

```bash
jar --describe-module --file library.jar
```

Để xem dependency mức module:

```bash
jdeps --print-module-deps --module-path mods application.jar
```

Nếu release notes ghi “module name changed”, phải rà soát cả `requires`, `opens ... to ...`, command-line flags và custom runtime image `jlink`. Thay đổi một module name là vấn đề packaging và runtime graph, không chỉ là sửa Java import.

## 12. Dependency bắc cầu và thay đổi trong BOM

Một framework release có thể cập nhật hàng chục thư viện, dù ứng dụng chỉ đổi một version trong parent POM hoặc platform.

Ví dụ **giả định**:

```text
Framework 3.x
  -> HTTP client A 4.x
  -> JSON serializer B 2.x
  -> Logging API C 1.x

Framework 4.x
  -> HTTP client A 5.x
  -> JSON serializer B 3.x
  -> Logging API C 2.x
```

Breaking change có thể nằm ở:

1. Framework API.
2. Transitive API do ứng dụng vô tình gọi trực tiếp.
3. Cơ chế auto-configuration mới.
4. Version mismatch do dependency override.
5. Classpath hoặc SPI/provider khác.
6. Các thư viện còn chạy nhưng có thay đổi wire format hoặc exception.

Do đó, đối với upgrade framework/BOM, phải so sánh **resolved dependency graph trước và sau**, không chỉ so một entry trong file build.

### 12.1. Điều gì xảy ra khi pin transitive dependency?

Một ứng dụng có thể ép `serializer B` về version cũ để tránh thay đổi behavior. Nhưng framework mới có thể đã được biên dịch và kiểm thử với API mới, khiến runtime có `NoSuchMethodError`. Ngược lại, ép version mới khi framework cũ chưa hỗ trợ có thể gây lỗi tương tự.

Chỉ override version khi:

- Biết API requirement của framework và dependency.
- Đã đọc compatibility matrix và các dependency constraints.
- Có integration tests cho đường gọi giữa framework và thư viện đó.
- Có lý do rõ ràng, ví dụ security fix và không có bản framework hỗ trợ tương ứng.

Override dependency là quyết định kỹ thuật cần bằng chứng, không phải thủ thuật để Maven/Gradle hết cảnh báo conflict.

## 13. Security notes không chỉ là mục “bổ sung”

Release notes có thể có những dòng:

- Reject malformed input previously accepted.
- Disable insecure protocols/ciphers.
- Restrict polymorphic deserialization.
- Tighten path traversal validation.
- Change unsafe default.

Đây có thể là những thay đổi **có chủ đích và cần giữ**. Một test cũ phụ thuộc việc chấp nhận dữ liệu không hợp lệ có thể thất bại sau update nhưng điều đó không nhất thiết là regression.

Khi đọc security advisory, cần ghi:

1. ID advisory/CVE hoặc định danh của dự án.
2. Phạm vi phiên bản bị ảnh hưởng.
3. Phiên bản đã sửa và nhánh backport nếu có.
4. Điều kiện khai thác liên quan tới cách ứng dụng dùng thư viện.
5. Mitigation được nhà cung cấp khuyến nghị.
6. Tác động của fix lên cấu hình, giao thức và dữ liệu cũ.

Không chỉ dựa vào điểm CVSS: mức rủi ro trong ứng dụng còn phụ thuộc khả năng tiếp cận bề mặt tấn công, dữ liệu xử lý và các biện pháp bảo vệ đang có. Tuy vậy, cũng không bỏ qua advisory chỉ vì thư viện được dùng gián tiếp.

**Nguyên tắc:** Nếu bản sửa làm một input cũ bị từ chối, trước hết tìm xem input đó có vi phạm chuẩn hoặc chính sách an toàn không. Không tắt kiểm tra bảo mật hoặc hạ cấp thư viện như lựa chọn mặc định.

## 14. License, artifact relocation và tình trạng bảo trì

Release notes và thông tin project còn cho biết các thay đổi ngoài API:

- License mới hoặc điều kiện phân phối khác.
- Repository hoặc groupId thay đổi.
- Dự án ngừng bảo trì, bị archived hoặc chuyển maintainer.
- Chuyển namespace `javax.*` sang `jakarta.*`.
- Cần artifact độc lập thay vì module tích hợp vào JDK.
- Ngừng hỗ trợ một platform/native architecture.

Những thay đổi này có thể quyết định **có được phép nâng** trong tổ chức hay không, ngay cả khi unit tests đều xanh.

Ví dụ, việc chuyển từ JAXB từng đi kèm JDK cũ sang dependency độc lập sau JDK 11 là vấn đề packaging và dependency. Việc chuyển các API Jakarta thế hệ mới sang `jakarta.xml.bind.*` là thay đổi namespace source/binary. Hai việc liên quan nhưng không phải cùng một thay đổi; cần đọc đúng migration guide cho từng chặng.

Không dùng một thông tin bản quyền/giấy phép từ blog không chính thức làm cơ sở pháp lý. Khi cần, tham khảo license file của đúng tag/artifact và quy trình rà soát của tổ chức.

## 15. Cách đọc release notes có hệ thống

Để không bỏ sót, nên đọc theo bốn lượt:

### Lượt 1 — Phạm vi và điều kiện hỗ trợ

Tìm:

- Minimum JDK và các version được hỗ trợ.
- Các framework/driver/toolchain version bắt buộc.
- Artifact name, module name hoặc package relocation.
- License, platform support và known issues.

Nếu một điều kiện nền tảng không đạt, dừng thiết kế migration để chọn lộ trình phù hợp trước khi đi sâu vào API.

### Lượt 2 — Breaking changes và deprecations

Đọc kỹ:

- Removed/renamed classes, methods, fields, constructors.
- Changed signatures/generics/checked exceptions.
- Deprecated APIs chuyển sang removed.
- Configuration keys bị đổi hoặc loại bỏ.
- Behavioral defaults, security policy và data format.

Không nhầm `deprecated` với `removed`. Một API deprecated vẫn có thể hoạt động ở bản hiện tại nhưng có cảnh báo và lộ trình loại bỏ; API removed có thể làm code hoặc binary thất bại ngay.

### Lượt 3 — Dependency changes và interoperability

Kiểm tra:

- Các library version được nâng gián tiếp.
- Các API hoặc module mới cần tích hợp.
- ServiceLoader/SPI changes.
- JDK baseline và bytecode compatibility.
- Serialization schema và wire protocol.
- Plugin, annotation processor, build plugin hoặc agent compatibility.

### Lượt 4 — Bug fixes và known regressions

Đọc các bug fixes có thể làm thay đổi kết quả cũ. Nếu ứng dụng đã dùng workaround cho một bug được sửa, cần xem có phải xóa workaround không, vì giữ workaround đôi khi tạo lỗi khi thư viện mới đã sửa vấn đề gốc.

Đối với known regressions, cân nhắc chọn patch release khác hoặc bổ sung test và rollback plan.

## 16. Biến release notes thành ma trận tác động

Không nên chuyển nguyên văn hàng trăm dòng changelog vào ticket. Tốt hơn là lập một bảng ngắn với mapping tới code và quyết định rõ ràng.

Ví dụ **giả định** khi nâng thư viện `com.example:billing-client`:

| Release note | Phân loại | Ứng dụng có dùng? | Tác động / xử lý | Bằng chứng hoàn tất |
|---|---|---|---|---|
| Removed `charge(String,long)` | Source + binary | Có, module billing adapter. | Chuyển sang `submitPayment(PaymentRequest)`. | Compile + integration test thanh toán. |
| Retry disabled by default | Behavioral/config | Có, outbound requests. | Cấu hình theo idempotency policy. | Retry test và metric. |
| Java 17 minimum | Runtime | Có, một worker còn Java 11. | Nâng worker trước hoặc chọn nhánh library khác. | Runtime matrix trên Java 17+. |
| New JSON field `transactionType` | Wire contract | Có, consumer ngoài. | Bổ sung tolerant reader trước khi producer phát field. | Contract test hai chiều. |
| Fix for unsafe redirect | Security | Có thể. | Giữ security behavior, sửa test cũ. | Security/integration test. |
| New tracing hooks | Feature | Chưa dùng. | Không bắt buộc đổi code. | Ghi nhận không áp dụng. |

Các cột hữu ích:

- Mã thay đổi, phiên bản xuất hiện.
- Link release note, API diff hoặc issue.
- Loại tương thích.
- Vị trí code/cấu hình/dữ liệu bị ảnh hưởng.
- Mức rủi ro và owner.
- Quyết định: sửa, hoãn, chấp nhận có điều kiện hoặc không áp dụng.
- Test/kiểm chứng và trạng thái.

Một thay đổi được đánh dấu “không áp dụng” cũng nên có lý do: chẳng hạn ứng dụng không sử dụng module đó và dependency không xuất hiện trên runtime classpath.

## 17. Cách kiểm tra ứng dụng có dùng breaking API không

Release notes mô tả thư viện, nhưng codebase ứng dụng có thể chỉ sử dụng một phần nhỏ.

Một số phương pháp:

### 17.1. Tìm trực tiếp trong source

Tìm method, package, annotation hoặc property được nêu trong release note. Ví dụ nếu note nói bỏ `LegacyParser`, tìm:

```text
LegacyParser
legacy-parser.enabled
parseLegacy
```

Chú ý reflection, `Class.forName(...)`, configuration string và code generation. Không phải mọi phụ thuộc đều hiện ra qua `import`.

### 17.2. Biên dịch lại bằng phiên bản mục tiêu

Compile có thể phát hiện API bị xóa, generic constraints khác hoặc annotation processor không tương thích. Tuy vậy, compile thành công **không chứng minh** behavior/runtime/data compatibility.

### 17.3. So sánh public API

Dùng `japicmp` hoặc `Revapi` để xem những public/protected declarations thay đổi, đặc biệt khi ứng dụng không thể đọc từng release note của một JAR lớn.

### 17.4. Phân tích runtime linkage

Chạy integration tests và theo dõi lỗi linkage trong các nhánh code chỉ chạy khi ứng dụng hoạt động. Plugin, driver và service providers có thể bị tải muộn, nên test startup không đủ.

### 17.5. So sánh serialized output

Nếu release notes liên quan JSON/XML/protocol, dùng golden fixtures từ version cũ và test round-trip với version mới. Một thay đổi format có thể không hề xuất hiện trong API diff.

## 18. Tạo một kế hoạch nâng cấp theo bước nhỏ

Một lộ trình migration hợp lý:

```text
Inventory current dependencies
            |
            v
Identify target versions + support constraints
            |
            v
Read notes for every release between old and new
            |
            v
Build change-impact matrix
            |
            v
Upgrade dependency in controlled branch
            |
            v
Compile + API + integration + contract tests
            |
            v
Canary/rollout + observe + rollback readiness
```

### Bước 1 — Chốt baseline

Lưu artifact, dependency graph, runtime, compiler, configurations và test results hiện tại. Không nên nâng đồng thời quá nhiều nhóm thư viện nếu điều đó làm mất khả năng tìm nguyên nhân.

### Bước 2 — Chọn đích hợp lệ

Đối chiếu target release với baseline JDK và phiên bản framework. Nếu cần hỗ trợ Java 11 nhưng library mới chỉ hỗ trợ Java 17, hoặc phải nâng baseline, hoặc chọn nhánh library khác; không thể giải quyết chỉ bằng cách ép compiler.

### Bước 3 — Đọc release notes qua từng chặng

Tìm migration guide cho từng major release, sau đó đọc các minor/patch nằm trong khoảng. Ghi cả deprecations sắp bị loại.

### Bước 4 — Ước lượng impact và phân công

Gắn mỗi thay đổi với code owner, data owner hoặc security owner. Nếu có thay đổi giao thức giữa nhiều service, phối hợp thứ tự triển khai.

### Bước 5 — Thực hiện thay đổi nhỏ và chạy test

Thay dependency trên nhánh riêng, cập nhật code/config theo ma trận, chạy compile/linkage tests và integration/contract tests thích hợp.

### Bước 6 — Quan sát trước/sau

Theo dõi tỷ lệ lỗi, latency, retry rate, serialization failures, resource usage, logging và các đường đi hiếm. Không chỉ nhìn trạng thái deployment xanh.

### Bước 7 — Gỡ workaround và ghi bài học

Nếu thư viện mới sửa một bug cũ, bỏ workaround sau khi kiểm tra. Lưu evidence vào upgrade record để những lần sau không phải nghiên cứu lại từ đầu.

## 19. Khi nào nên nâng từng dependency, khi nào nâng đồng bộ?

### 19.1. Nâng từng dependency

Phù hợp khi các thư viện tương đối độc lập, ví dụ một parser hoặc utility không bị framework quản lý chặt. Ưu điểm là dễ khoanh vùng regression và rollback riêng.

Tuy nhiên, phải kiểm tra transitive dependency và các shared APIs để tránh version mismatch.

### 19.2. Nâng theo BOM/framework release train

Phù hợp khi framework công bố một tập version được kiểm thử chung. Ví dụ một framework có parent POM hoặc Gradle platform quản lý nhiều dependency liên quan.

Ưu điểm là giảm rủi ro tổ hợp chưa được hỗ trợ. Đổi lại, nhiều thư viện có thể thay đổi cùng lúc; vì vậy vẫn cần đọc migration guide tổng của framework và những release notes của thành phần quan trọng đối với ứng dụng.

### 19.3. Chia nâng cấp lớn thành các chặng

Nếu nhảy từ version 1.x lên 4.x, có thể cân nhắc:

```text
1.x -> 2.x -> 3.x -> 4.x
```

Không nhất thiết phải phát hành production ở mọi chặng. Nhưng thực hiện từng chặng trong nhánh thử nghiệm giúp cô lập breaking APIs và xác định mốc phát sinh thay đổi, đặc biệt khi migration guide chỉ mô tả các bản kề nhau.

## 20. Chiến lược tương thích dữ liệu và rollout nhiều service

Release notes của serializer, ORM, message library hoặc HTTP framework có thể ảnh hưởng dữ liệu được trao đổi giữa nhiều phiên bản service.

Giả sử service A bản mới phát message thêm field:

```json
{
  "eventId": "evt-42",
  "status": "READY",
  "sourceSystem": "gateway"
}
```

Consumer bản cũ có thể bị lỗi nếu reader từ chối unknown fields. Khi đó không nên nâng producer trước khi consumer hỗ trợ schema mới.

Một chiến lược thường dùng là **expand → migrate → contract**:

1. **Expand:** consumer nhận cả format cũ và mới.
2. **Migrate:** producer chuyển dần, đồng thời theo dõi thông điệp cũ đang tồn tại.
3. **Contract:** sau khi không còn consumer/data cũ, bỏ logic tương thích tạm.

Đối với dữ liệu đã lưu (database, cache, queue, object storage), phải xác định khả năng rollback. Phiên bản code cũ chưa chắc đọc được dữ liệu mà serializer phiên bản mới đã ghi. Rollback dependency không tự rollback dữ liệu.

## 21. Cần test những gì sau khi đọc breaking changes?

Không nhất thiết chạy mọi test ở mọi bước, nhưng phải có chiến lược bao phủ theo rủi ro.

| Kiểu thay đổi | Test cần ưu tiên |
|---|---|
| API/source | Compile, unit tests tại call sites, API/binary compatibility test nếu phát hành thư viện. |
| Binary/transitive | Integration tests trên artifact runtime, classpath/module path, plugin load. |
| Configuration/default | Test với cấu hình mới, missing config, config legacy, startup failure. |
| Serialization/protocol | Golden fixtures, backward/forward compatibility, schema validation. |
| Security | Negative tests với input bất hợp lệ, kiểm soát quyền truy cập, TLS/certificate. |
| Performance | Baseline throughput, P95/P99 latency, CPU/memory, resource leaks. |
| JDK baseline | Test trên minimum supported JDK và JDK mục tiêu. |
| Operational lifecycle | Startup/shutdown, graceful drain, retry, scheduled jobs và rollback. |

### 21.1. Một bài test đơn giản về hợp đồng

Ví dụ, một thư viện đã được nâng có thể vẫn parse được dữ liệu theo hợp đồng:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class PaymentContractTest {
    @Test
    void minorUnitsArePreserved() {
        PaymentRequest request =
                new PaymentRequest("A-100", 5000L);

        assertEquals(5000L, request.amountMinorUnits());
    }
}
```

`PaymentRequest` ở đây là DTO giả định của ứng dụng. Test thực tế cần gọi adapter/serializer hoặc API được nâng để kiểm tra đúng đường tác động; không chỉ tạo object rồi tự xác nhận getter như ví dụ minh họa cấu trúc.

### 21.2. Matrix JDK × dependency version

Khi sản phẩm hỗ trợ nhiều JDK:

| Dependency | JDK 11 | JDK 17 | JDK 21 |
|---|---|---|---|
| Library 1.x | Theo support matrix của dự án | Theo support matrix | Theo support matrix |
| Library 2.x | Có thể không được hỗ trợ | Theo support matrix | Theo support matrix |

Không tự điền “có” chỉ vì một bản chạy thử được. Phải kiểm tra vendor support policy, class file version và test trên runtime thấp nhất mà sản phẩm cam kết.

### 21.3. Test negative cases

Đặc biệt chú ý các ca bị từ chối sau security fix, ví dụ JSON chứa type ID không được phép, XML chứa external entity hoặc TLS dùng thuật toán đã bị vô hiệu hóa. Đây có thể là **kết quả đúng** của thư viện mới; test phải nêu rõ hành vi từ chối kỳ vọng thay vì coi mọi exception là regression.

## 22. Phân biệt lỗi do bản nâng cấp với lỗi ứng dụng có sẵn

Một sự cố xuất hiện sau khi thay dependency chưa chắc do code mới của thư viện sai. Nó có thể làm lộ một giả định tiềm ẩn:

- Ứng dụng dùng class nội bộ thay vì API được hỗ trợ.
- Ứng dụng phụ thuộc thứ tự iteration không được cam kết.
- Cấu hình bảo mật cũ bỏ qua validation cần thiết.
- Consumer giả định một JSON field luôn tồn tại, dù schema ghi optional.
- Nhiều thư viện dùng cùng shared dependency nhưng version khác nhau.

Quy trình phân loại:

1. Tái hiện lỗi trên artifact và môi trường cố định.
2. Đối chiếu release notes và hợp đồng API.
3. So sánh dependency graph trước/sau.
4. Viết reproducer tối thiểu nếu có thể.
5. Kiểm tra library issue tracker và known regressions.
6. Kết luận với mức độ chắc chắn rõ ràng: intentional change, ứng dụng dựa hành vi không được hỗ trợ, integration mismatch hay bug thư viện.

Không gán “breaking change cố ý” cho mọi lỗi chỉ vì có nâng version. Nếu thư viện mới vi phạm API contract còn hiệu lực, đó có thể là regression thật sự cần báo maintainer.

## 23. Chọn bản target: latest chưa chắc là phù hợp nhất

Nâng đến phiên bản mới nhất có thể giải quyết nhiều vấn đề, nhưng quyết định phải xét:

- Minimum JDK và baseline runtime của sản phẩm.
- Phiên bản framework/BOM đang hỗ trợ.
- Security fixes và support lifecycle.
- Major migrations cần làm.
- Known issues/known regressions của target.
- Tính ổn định của API và nhu cầu nghiệp vụ.
- License và điều kiện phân phối.
- Khả năng rollback và thời gian kiểm thử.

Nếu bản mới nhất yêu cầu Java 21 nhưng hệ thống có production node Java 17, có thể cần nâng JDK trước hoặc chọn nhánh thư viện còn được hỗ trợ trên Java 17. Không chọn bản cũ đã hết bảo trì một cách tùy tiện; cần đánh giá rủi ro và kế hoạch nâng tiếp.

## 24. Mẫu upgrade record có thể lưu cùng dự án

Một bản ghi ngắn, dễ kiểm tra hơn những ghi chú rời:

```yaml
changeId: DEP-MIG-023
component: "billing-client"
coordinates: "com.example:billing-client"
fromVersion: "1.8.7"
toVersion: "2.1.3"
sourceOfTruth:
  - "Release notes v2.0"
  - "Migration guide 1.x -> 2.x"
  - "Release notes v2.1.3"
runtime:
  minimumJdkRequired: 17
  applicationMinimumJdk: 17
changes:
  - id: BC-01
    category: source
    summary: "Renamed charge API"
    affectedCode: "billing adapter"
    action: "Replace with submitPayment"
    proof: "Compile + integration tests"
  - id: BC-02
    category: behavior
    summary: "Changed retry defaults"
    affectedCode: "outbound payment requests"
    action: "Define idempotency-aware retry policy"
    proof: "Retry contract tests"
securityNotes:
  - "Review redirect validation change"
rollout:
  strategy: "Canary with rollback"
  metrics: "Request failures, retries, latency"
owner: "Billing team"
status: "In verification"
```

Toàn bộ tọa độ, phiên bản và thay đổi trong mẫu này **chỉ là dữ liệu giả định** để minh họa cách ghi hồ sơ; không nên coi đó là release note thực tế của một artifact có thật.

Mỗi thay đổi có link tài liệu hoặc issue cụ thể trong hồ sơ thực. Nên ghi cả đường dẫn tới code/test để người duyệt pull request kiểm chứng được quyết định thay vì chỉ thấy lời xác nhận “upgrade complete”.

## 25. Những sai lầm thường gặp

**Chỉ xem tiêu đề của release mới nhất.** Có thể bỏ qua breaking changes của nhiều bản trung gian.

**Cho rằng patch/minor luôn tương thích tuyệt đối.** Một security fix hoặc thay đổi dependency vẫn có thể ảnh hưởng behavior.

**Đọc version khai báo thay vì version đã resolve.** BOM và transitive dependency có thể chọn artifact khác.

**Chỉ quan tâm lỗi compile.** Binary linkage, serialization và runtime defaults có thể đổi mà compiler không báo.

**Bỏ qua minimum JDK.** Library mới có thể phát class file không chạy được trên runtime thấp nhất.

**Ép một transitive version không theo compatibility matrix.** Framework có thể gọi method chỉ tồn tại ở phiên bản mới hơn.

**Bỏ known issues và security notes.** Upgrade có thể thất bại vì known regression hoặc vì hành vi cũ không an toàn bị chặn.

**Đồng nhất deprecated với removed.** Deprecated là cảnh báo/lộ trình; removed là breaking change có thể xảy ra ngay.

**Đánh dấu không ảnh hưởng mà không kiểm tra sử dụng thực tế.** Reflection, SPI, configuration và runtime plugin có thể gọi API dù không có import rõ trong source.

**Phụ thuộc thứ tự release notes để ưu tiên sửa.** Thứ tự changelog không phải thứ tự rủi ro trong ứng dụng.

**Rollback code mà không xét dữ liệu.** Payload/schema mới đã được lưu có thể không đọc được bởi phiên bản cũ.

**Chỉ kiểm thử startup.** Những đường lỗi như scheduled job, retry, plugin loading hoặc dữ liệu legacy có thể chỉ xuất hiện sau đó.

## 26. Checklist trước khi duyệt nâng cấp dependency

- [ ] Đã xác nhận artifact coordinates và version thực tế được resolve.
- [ ] Đã chốt version nguồn, version đích và JDK baseline.
- [ ] Đã đọc migration guide cho mọi bước major trong khoảng nâng.
- [ ] Đã đọc release notes/CHANGELOG của các bản trung gian quan trọng.
- [ ] Đã kiểm tra compatibility matrix, deprecation/removal và known issues.
- [ ] Đã so sánh dependency graph và BOM trước/sau.
- [ ] Đã phân loại source, binary, behavioral, config, data, runtime và security changes.
- [ ] Đã xác định những API/configuration thực sự được ứng dụng dùng.
- [ ] Đã xem xét minimum JDK và JPMS/reflection/SPI.
- [ ] Đã kiểm tra serializer, schema, database và message compatibility nếu liên quan.
- [ ] Đã xét security advisory và thay đổi kiểm soát đầu vào.
- [ ] Đã xem license, artifact relocation và tình trạng bảo trì.
- [ ] Đã có ma trận impact với owner, action và bằng chứng xác nhận.
- [ ] Đã có compile, integration, contract và runtime matrix tests theo rủi ro.
- [ ] Đã biết thứ tự rollout và khả năng rollback code/dữ liệu.
- [ ] Đã ghi lại workaround tạm và điều kiện xóa bỏ.
- [ ] Đã lưu link release notes, tag/commit và hồ sơ quyết định cho lần nâng tiếp theo.

## Tài liệu tham khảo

- [Semantic Versioning](https://semver.org/): quy tắc MAJOR.MINOR.PATCH và giới hạn của việc suy luận từ version.
- [Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): xem dependency graph thực tế của Maven.
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): transitive dependencies, mediation và dependency management.
- [Gradle — Viewing and debugging dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): `dependencies` và `dependencyInsight`.
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): cơ chế khóa phiên bản đã resolve.
- [japicmp](https://github.com/siom79/japicmp): công cụ so sánh public API/binary giữa JAR.
- [Revapi](https://revapi.org/): kiểm tra thay đổi API và các rule tương thích.
- [OpenJDK jdeps](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html): phân tích dependency class/package/module.
- [JLS — Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html): quy tắc binary compatibility của Java.
- [JEP 320 — Remove the Java EE and CORBA Modules](https://openjdk.org/jeps/320): ví dụ thay đổi packaging làm ứng dụng phải bổ sung dependency.
- [GitHub — About releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases): khái niệm releases/tags khi tìm tài liệu dự án.
- [OSV Database](https://osv.dev/): nguồn tham khảo vulnerability theo package và version; đối chiếu với advisory chính thức.

## Kết luận

Đọc release notes đúng cách là một hoạt động **phân tích tương thích**, không chỉ là xem danh sách tính năng. Trước tiên phải xác định chính xác artifact/version mà build và runtime thực sự dùng, sau đó đọc tài liệu chính thức của từng chặng nâng cấp, phân loại thay đổi theo source, binary, behavior, config, data, JDK và security. Từng breaking change cần được nối với vị trí sử dụng trong ứng dụng, phương án xử lý và bài kiểm thử chứng minh kết quả. Ma trận tác động, dependency graph trước/sau, golden fixtures và kế hoạch rollout/rollback giúp biến thông tin phát hành thành một quyết định migration rõ ràng, có thể kiểm chứng và bảo trì lâu dài.
