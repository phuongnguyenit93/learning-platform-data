# Build, test và kiểm tra dependency

Trong vòng đời phát triển API, build, test và kiểm tra dependency là ba hoạt động liên kết với nhau để quyết định một phiên bản có đủ an toàn để phát hành hay không. Build tạo ra artifact từ mã nguồn và các đầu vào đã xác định. Test kiểm tra hành vi của API trong những tình huống bình thường và bất thường. Kiểm tra dependency đánh giá các thư viện mà ứng dụng đưa vào, kể cả những thư viện được kéo theo gián tiếp.

Với API security, ba hoạt động này phải xác minh được các ranh giới bảo mật của từng endpoint, đối tượng dữ liệu và luồng nghiệp vụ. Một ứng dụng biên dịch thành công hoặc trả về HTTP 200 trong happy path vẫn có thể mắc lỗi phân quyền đối tượng, cho phép gọi chức năng trái phép, nhận dữ liệu đầu vào nguy hiểm, bị lợi dụng để truy cập mạng nội bộ hoặc tiêu tốn tài nguyên quá mức. Vì vậy, pipeline cần kiểm tra cả chất lượng kỹ thuật lẫn các điều kiện bảo mật trước khi phát hành.

## 1. Mục tiêu của từng hoạt động

| Hoạt động | Câu hỏi cần trả lời | Kết quả mong đợi |
|---|---|---|
| Build | Mã nguồn và các đầu vào đã khai báo có tạo được artifact hợp lệ, có thể truy vết không? | Artifact được tạo từ phiên bản mã nguồn xác định; cấu hình build và phiên bản công cụ có thể tái lập. |
| Test | API có thực hiện đúng nghiệp vụ và giữ đúng ranh giới bảo mật trong cả trường hợp hợp lệ lẫn không hợp lệ không? | Bộ kiểm thử tự động bao phủ các luồng quan trọng, bao gồm các tình huống bị từ chối. |
| Kiểm tra dependency | Các thư viện trực tiếp và gián tiếp có lỗ hổng, nguồn gốc đáng ngờ hoặc rủi ro bảo trì nào không? | Danh sách dependency được rà soát, lỗ hổng được xử lý hoặc có ngoại lệ được phê duyệt và giới hạn thời gian. |

Không hoạt động nào thay thế được hai hoạt động còn lại. Build không chứng minh API an toàn; test không thể bao quát mọi lỗ hổng trong thư viện bên thứ ba; còn quét dependency không phát hiện được lỗi phân quyền do chính ứng dụng viết.

## 2. Build có thể tái lập và kiểm soát được

Build là quá trình chuyển mã nguồn thành artifact có thể chạy hoặc triển khai, chẳng hạn JAR, WAR hoặc container image. Một build an toàn cần kiểm soát được đầu vào và không vô tình đưa bí mật hoặc cấu hình môi trường vào artifact.

### 2.1. Cố định các đầu vào của build

Các đầu vào thường gồm:

- Phiên bản mã nguồn hoặc commit đang được build.
- Phiên bản JDK và công cụ build.
- Phiên bản plugin build và dependency.
- Các tham số build, profile và cấu hình đóng gói.
- Nguồn tải dependency, chẳng hạn repository nội bộ đã được kiểm soát.

Nên sử dụng Maven Wrapper hoặc Gradle Wrapper được lưu cùng repository để thành viên nhóm và CI sử dụng cùng dòng công cụ. Phiên bản JDK, plugin và thư viện cần được khai báo rõ ràng. Với Gradle, có thể bật dependency locking và dependency verification để kiểm soát phiên bản được phân giải và tính toàn vẹn của artifact. Với Maven, nên khai báo phiên bản trực tiếp hoặc qua `dependencyManagement`, đồng thời dùng quy tắc kiểm tra phiên bản phù hợp; không nên giả định Maven có cơ chế lockfile chuẩn giống Gradle.

Ví dụ các lệnh build thường gặp trong dự án Java:

~~~bash
# Maven: clean, biên dịch, chạy các kiểm tra gắn với lifecycle verify
./mvnw --batch-mode clean verify

# Gradle: clean, chạy các task kiểm tra và build
./gradlew --no-daemon clean check build
~~~

Đây là ví dụ theo từng công cụ. Dự án cần chọn lệnh phù hợp với cấu hình plugin, task và profile thực tế. CI nên dùng wrapper của repository thay vì dựa vào phiên bản Maven hoặc Gradle cài sẵn trên máy runner.

### 2.2. Tách mã nguồn khỏi cấu hình và bí mật

Không đưa token, mật khẩu, private key, chuỗi kết nối hoặc thông tin xác thực vào:

- Mã nguồn, file cấu hình được commit hoặc tham số mặc định trong code.
- Log build, log test và thông báo lỗi.
- JAR/WAR, container image hoặc artifact phát hành.

Thông tin môi trường nên được cấp qua secret store hoặc cơ chế quản lý cấu hình của nền tảng triển khai. Bản build không nên chứa sẵn thông tin đăng nhập của môi trường development, staging hay production. Nếu phát hiện bí mật đã bị commit, cần thu hồi hoặc xoay vòng bí mật đó; chỉ xóa chuỗi khỏi commit mới nhất không làm cho bí mật cũ mất hiệu lực.

### 2.3. Tạo artifact có thể truy vết

Một artifact cần liên hệ được với commit, lần chạy pipeline, phiên bản công cụ và tập dependency đã dùng để tạo ra nó. Sau khi build và kiểm tra ở CI, hãy lưu artifact cùng metadata hoặc provenance tương ứng. Khi triển khai qua staging rồi production, nên thúc đẩy cùng một artifact đã được kiểm tra thay vì build lại từ mã nguồn ở mỗi môi trường. Cách làm này giảm nguy cơ hai môi trường chạy các artifact khác nhau dù cùng mang một nhãn phiên bản.

Nếu ứng dụng được đóng gói thành container image, cần kiểm tra cả image nền và các package hệ điều hành bên trong image. Việc quét thư viện Java không thay thế việc quét các thành phần của image.

## 3. Kiểm thử API theo lớp và theo ranh giới bảo mật

Một bộ test có ích phải kiểm tra cả điều API được phép làm và điều API bắt buộc phải từ chối. Các test nên được thiết kế từ endpoint, vai trò người gọi, tenant, đối tượng dữ liệu và trạng thái nghiệp vụ.

### 3.1. Các lớp kiểm thử

| Lớp kiểm thử | Phạm vi | Ví dụ cần kiểm tra |
|---|---|---|
| Unit test | Hàm, service, policy hoặc validator riêng lẻ | Quy tắc tính toán, kiểm tra quyền sở hữu, giới hạn dữ liệu đầu vào. |
| Component/integration test | Nhiều thành phần hoạt động cùng nhau, có thể dùng database hoặc dịch vụ giả lập | Bộ lọc xác thực, transaction, truy vấn dữ liệu theo tenant, mapping lỗi. |
| API/contract test | Request và response ở ranh giới HTTP | Schema, kiểu dữ liệu, status code, header, trường bắt buộc và trường không được trả về. |
| End-to-end test | Luồng nghiệp vụ qua nhiều endpoint hoặc dịch vụ | Tạo tài nguyên, cập nhật, đọc lại và kiểm tra quyền ở từng bước. |
| Security test | Các trường hợp tấn công hoặc truy cập trái phép | BOLA/IDOR, BFLA, injection, SSRF, mass assignment, lạm dụng tài nguyên. |
| Performance/resilience test | Hành vi khi tải cao, timeout hoặc dịch vụ phụ thuộc gặp lỗi | Rate limit, giới hạn đồng thời, timeout, retry và khả năng phục hồi. |

Không nhất thiết mọi test đều phải chạy ở mọi commit. Unit test và các kiểm tra nhanh nên chạy thường xuyên; integration, security và performance test có thể được chia theo thời gian chạy hoặc theo mức độ rủi ro. Tuy nhiên, các luồng bảo mật trọng yếu phải có cổng kiểm tra trước khi phát hành.

### 3.2. Xác thực và phân quyền

Xác thực trả lời câu hỏi người gọi là ai. Phân quyền trả lời người gọi đó được phép thực hiện hành động nào trên đối tượng nào. Kiểm thử chỉ xác nhận token hợp lệ là chưa đủ.

Với mỗi endpoint, hãy xác định ít nhất:

- Không có token, token sai chữ ký, hết hạn hoặc sai audience có bị từ chối không.
- Người dùng đã đăng nhập nhưng không có quyền chức năng có bị từ chối không.
- Người dùng có quyền gọi chức năng nhưng không sở hữu đối tượng được yêu cầu có bị từ chối không.
- Người dùng thuộc tenant A có thể đọc hoặc sửa dữ liệu của tenant B không.
- Vai trò quản trị có được kiểm tra ở đúng endpoint và đúng thao tác nhạy cảm không.

Ví dụ, với `GET /accounts/{accountId}`, test cần tạo hai tài khoản thuộc hai chủ sở hữu khác nhau. Người dùng A đọc tài khoản của A phải thành công; người dùng A đọc tài khoản của B phải bị từ chối theo chính sách của hệ thống. Không được coi việc endpoint yêu cầu đăng nhập là bằng chứng đã ngăn được BOLA/IDOR.

Ví dụ minh họa dạng test service bằng Java/JUnit:

~~~java
@Test
void userCannotReadAnotherUsersAccount() {
    var caller = authenticatedUser("user-a", "tenant-a");

    assertThrows(
        AccessDeniedException.class,
        () -> accountService.getAccount("account-owned-by-b", caller)
    );
}
~~~

Các hàm tạo người dùng và service trong ví dụ là fixture minh họa; khi áp dụng cần thay bằng cơ chế xác thực và dữ liệu test của dự án. Ở tầng API, nên có thêm test tích hợp để xác minh danh tính từ request thực sự được truyền đến lớp phân quyền.

### 3.3. Validation và bảo vệ dữ liệu

Test validation nên bao gồm:

- Thiếu trường bắt buộc, sai kiểu, giá trị ngoài khoảng cho phép và định dạng không hợp lệ.
- Chuỗi quá dài, mảng quá lớn, JSON lồng sâu hoặc payload vượt giới hạn.
- Trường không được phép cập nhật, trường chỉ dành cho quản trị và thuộc tính nhạy cảm bị gửi thêm trong request.
- Ký tự đặc biệt, dữ liệu có thể gây injection và các trường hợp encoding bất thường.

Kiểm tra mass assignment bằng cách gửi thêm các trường như `role`, `ownerId`, `tenantId` hoặc `isAdmin` vào request cập nhật. API phải chỉ bind các trường được phép theo DTO hoặc allowlist; không được để dữ liệu đầu vào tự thay đổi quyền, chủ sở hữu hay trạng thái nội bộ.

Test response cũng phải kiểm tra dữ liệu không được phép lộ ra ngoài, chẳng hạn password hash, access token, secret nội bộ, thông tin định danh không cần thiết hoặc thuộc tính của tenant khác. Kiểm tra cả log và thông báo lỗi để chắc chắn chúng không chứa token, mật khẩu hay dữ liệu cá nhân vượt quá nhu cầu vận hành.

### 3.4. SSRF và các luồng gọi ra ngoài

Nếu API nhận URL hoặc tên host từ người dùng rồi gọi dịch vụ bên ngoài, cần kiểm thử đường đi mạng này như một ranh giới bảo mật riêng. Các trường hợp nên có gồm:

- URL dùng scheme không được hỗ trợ hoặc định dạng bất thường.
- Địa chỉ loopback, mạng private, link-local và địa chỉ metadata của nền tảng cloud.
- Tên miền trỏ đến IP bị cấm sau khi phân giải DNS.
- Redirect chuyển từ host được phép sang host bị cấm.
- DNS thay đổi giữa thời điểm kiểm tra và thời điểm kết nối.
- Response quá lớn, kết nối chậm hoặc máy chủ đích không phản hồi.

Biện pháp phòng vệ cần được kiểm tra ở chính thành phần thực hiện outbound request: allowlist scheme/host khi nghiệp vụ cho phép, kiểm tra IP sau DNS resolution, áp dụng chính sách cho từng redirect, giới hạn thời gian và kích thước response, đồng thời chặn truy cập đến vùng mạng nhạy cảm ở tầng network. Chỉ kiểm tra chuỗi URL bằng một biểu thức đơn giản thường không đủ để ngăn SSRF.

### 3.5. Lạm dụng tài nguyên và hành vi khi lỗi

Test cần xác minh giới hạn tài nguyên có hiệu lực ở phía server:

- Pagination có giới hạn page size tối đa; client không thể yêu cầu một trang khổng lồ.
- Payload và upload có giới hạn kích thước.
- Endpoint tốn tài nguyên có rate limit, timeout và giới hạn concurrency phù hợp.
- Các truy vấn lọc, tìm kiếm hoặc biểu thức đầu vào không tạo ra công việc không giới hạn.
- Retry không khuếch đại tải khi dịch vụ phụ thuộc đang lỗi.
- Khi chạm giới hạn, API trả lỗi nhất quán (ví dụ HTTP 429 cho rate limit) và không làm lộ chi tiết nội bộ.

Test cần bao gồm cả trường hợp nhiều request đồng thời và trường hợp một dependency phản hồi chậm. Nếu chỉ kiểm tra một request đơn lẻ, nhóm có thể bỏ sót lỗi cạn connection pool, thread hoặc bộ nhớ.

### 3.6. Header, CORS và lỗi HTTP

Tùy loại API và cách triển khai, cần kiểm tra CORS chỉ cho phép origin được phê duyệt, không phản chiếu tùy tiện giá trị Origin do client gửi. Kiểm tra các security header phù hợp với giao thức và bề mặt sử dụng; không sao chép một bộ header cho mọi loại API mà không xét cách client truy cập.

Response lỗi nên ổn định và không tiết lộ stack trace, câu SQL, đường dẫn nội bộ, tên máy chủ hay thông tin xác thực. Test nên xác nhận status code và cấu trúc lỗi theo contract đã công bố. Với lỗi quyền truy cập, hệ thống có thể chọn 403 hoặc 404 theo chính sách tránh tiết lộ sự tồn tại của tài nguyên; điều quan trọng là hành vi nhất quán và không làm rò rỉ dữ liệu.

## 4. Kiểm tra dependency trực tiếp và gián tiếp

Dependency là một phần của bề mặt tấn công. Ứng dụng có thể dùng một thư viện trực tiếp, trong khi thư viện đó lại kéo theo nhiều dependency khác. Vì vậy, chỉ xem các thư viện được khai báo trực tiếp là chưa đủ.

### 4.1. Những rủi ro cần xem xét

| Nhóm rủi ro | Nội dung cần xem xét |
|---|---|
| Lỗ hổng đã công bố | Phiên bản có CVE hoặc advisory ảnh hưởng hay không; mức độ nghiêm trọng và điều kiện khai thác là gì. |
| Khả năng bị khai thác trong ứng dụng | Thành phần dễ tổn thương có nằm trên đường chạy thực tế, có được gọi với dữ liệu không tin cậy hoặc có thể tiếp cận từ endpoint không. |
| Nguồn gốc và tính toàn vẹn | Package đến từ repository đáng tin cậy không; có dấu hiệu package giả mạo, typosquatting hoặc artifact bị thay thế không. |
| Tình trạng bảo trì | Dự án còn được duy trì, có bản vá và quy trình phát hành đáng tin cậy không. |
| Giấy phép | License có phù hợp với chính sách phân phối và sử dụng của tổ chức không. |
| Mức độ cần thiết | Dependency có thực sự cần thiết, có thể bỏ hoặc thay bằng thành phần ít rủi ro hơn không. |

### 4.2. Phân biệt dependency trực tiếp và bắc cầu

Dependency trực tiếp được khai báo bởi ứng dụng. Dependency bắc cầu (transitive dependency) được kéo vào thông qua dependency khác. Một lỗ hổng có thể nằm sâu trong cây dependency nhưng vẫn ảnh hưởng đến ứng dụng nếu mã dễ tổn thương được nạp hoặc gọi trong điều kiện phù hợp.

Với Maven, có thể xem cây dependency bằng:

~~~bash
./mvnw dependency:tree
~~~

Với Gradle:

~~~bash
./gradlew dependencies
~~~

Các lệnh này giúp hiểu dependency được phân giải, nhưng không thay thế công cụ SCA. Công cụ Software Composition Analysis (SCA) đối chiếu thành phần với dữ liệu lỗ hổng và advisory, đồng thời có thể cung cấp thông tin license hoặc policy tùy cấu hình. Ví dụ công cụ trong hệ sinh thái có OWASP Dependency-Check, osv-scanner và các dịch vụ SCA thương mại.

### 4.3. Đánh giá cảnh báo đúng ngữ cảnh

Không nên chỉ nhìn một con số CVSS rồi tự động kết luận mọi cảnh báo có mức độ như nhau. Khi xử lý một phát hiện, cần xem:

1. Dependency và phiên bản bị ảnh hưởng có thực sự nằm trong artifact đang phát hành không.
2. Lỗ hổng có thể bị kích hoạt trong cách ứng dụng sử dụng thư viện đó không.
3. Endpoint hoặc luồng dữ liệu không tin cậy nào có thể dẫn tới đoạn mã dễ tổn thương.
4. Có phiên bản đã vá tương thích hay không; việc nâng cấp có thay đổi API hoặc hành vi không.
5. Nếu chưa thể nâng cấp, có biện pháp giảm thiểu thực tế nào và rủi ro còn lại là gì.

Khả năng khai thác trong ứng dụng giúp ưu tiên công việc, nhưng không nên dùng nhận định “chưa thấy đường gọi” làm lý do bỏ qua cảnh báo nghiêm trọng mà không có bằng chứng và người chịu trách nhiệm. Một dependency có thể được kích hoạt qua đường gọi gián tiếp hoặc thay đổi theo cấu hình runtime.

### 4.4. Quản lý phiên bản và nguồn dependency

Để giảm rủi ro dependency bị thay đổi ngoài dự kiến:

- Khai báo phiên bản rõ ràng; tránh version range hoặc phiên bản động trong build phát hành nếu không có cơ chế kiểm soát.
- Dùng repository được tổ chức phê duyệt hoặc proxy nội bộ để quản lý nguồn tải package.
- Bật dependency locking và verification phù hợp với công cụ build.
- Kiểm tra checksum hoặc chữ ký khi hệ sinh thái và nguồn cung cấp hỗ trợ.
- Hạn chế quyền ghi vào repository package; bảo vệ quy trình publish artifact nội bộ.
- Xóa dependency không còn dùng và tránh thêm thư viện chỉ để giải quyết một tác vụ rất nhỏ.

Không nên tự động nâng cấp hàng loạt dependency trong production mà không chạy test tương thích và review thay đổi. Bot cập nhật dependency có thể tạo pull request, nhưng mỗi thay đổi vẫn cần đi qua build, test, SCA và quy trình review của dự án.

### 4.5. SBOM và xử lý ngoại lệ

Software Bill of Materials (SBOM) là danh mục thành phần phần mềm trong một artifact, có thể bao gồm tên package, phiên bản, quan hệ dependency và thông tin nhận diện. SBOM giúp nhóm biết phiên bản đang chạy có chứa thư viện nào khi một lỗ hổng mới được công bố. Có thể dùng định dạng phổ biến như CycloneDX hoặc SPDX và lưu SBOM gắn với đúng artifact phát hành.

Nếu chưa thể khắc phục một lỗ hổng, ngoại lệ cần ghi rõ dependency và phiên bản, lý do chưa nâng cấp, đánh giá khả năng ảnh hưởng, biện pháp giảm thiểu, người phê duyệt và ngày hết hạn. Ngoại lệ phải được rà soát lại khi có phiên bản vá, thay đổi cách sử dụng dependency hoặc thay đổi mức độ khai thác. Tránh dùng quy tắc bỏ qua toàn bộ một thư viện hoặc một họ cảnh báo mà không giới hạn phạm vi.

## 5. Đưa các kiểm tra vào CI/CD

Pipeline nên tự động hóa các kiểm tra lặp lại để mọi thay đổi đều được đánh giá theo cùng một tiêu chí. Một luồng tham khảo:

~~~mermaid
flowchart TD
    A[Commit / Pull request] --> B[Kiểm tra wrapper và toolchain]
    B --> C[Resolve dependency có kiểm soát]
    C --> D[Build và unit test]
    D --> E[SAST và secret scan]
    E --> F[SCA và kiểm tra license]
    F --> G[Integration và API security test]
    G --> H[Tạo artifact và SBOM]
    H --> I[Kiểm tra image nếu có]
    I --> J[Đưa lên staging]
    J --> K[Smoke test và kiểm tra sau triển khai]
    K --> L[Promote artifact đã kiểm tra]
~~~

Thứ tự thực tế có thể thay đổi theo công cụ và thời gian chạy. Ví dụ SCA có thể chạy ngay sau khi phân giải dependency để phản hồi sớm, sau đó chạy lại trên artifact cuối cùng để xác nhận đúng tập thành phần được đóng gói.

### 5.1. Thiết kế cổng chất lượng

Nhóm cần định nghĩa điều kiện pass/fail rõ ràng. Một chính sách tham khảo:

- Build thất bại, unit test trọng yếu thất bại hoặc kiểm tra bảo mật bắt buộc thất bại: không cho phát hành.
- Phát hiện secret trong thay đổi: chặn merge và yêu cầu xử lý, bao gồm thu hồi bí mật nếu đã bị lộ.
- Dependency có lỗ hổng nghiêm trọng: chặn phát hành theo ngưỡng chính sách; chỉ cho phép ngoại lệ có người phê duyệt, lý do và thời hạn.
- Test phân quyền đối tượng, phân quyền chức năng hoặc tenant isolation thất bại: chặn phát hành.
- Cảnh báo mức thấp: ghi nhận, phân công và theo dõi theo SLA thay vì bỏ qua không có chủ sở hữu.

Ngưỡng severity cần được tổ chức thống nhất và có thể điều chỉnh theo mức phơi bày, dữ liệu xử lý và khả năng khai thác. Không nên đặt ngưỡng chỉ để làm cho pipeline luôn xanh.

### 5.2. Giữ kết quả kiểm tra có thể truy vết

Mỗi lần phát hành nên lưu tối thiểu:

- Commit hoặc phiên bản mã nguồn.
- Kết quả build và test, bao gồm test bảo mật trọng yếu.
- Báo cáo SCA và các ngoại lệ còn hiệu lực.
- SBOM của artifact được phát hành.
- Mã định danh hoặc digest của artifact/container image.
- Thông tin pipeline và thời điểm triển khai.

Khi cần điều tra sự cố hoặc đánh giá ảnh hưởng của CVE mới, nhóm có thể xác định artifact nào chứa dependency bị ảnh hưởng và đang được triển khai ở môi trường nào.

## 6. Ví dụ áp dụng cho một thay đổi API

Giả sử nhóm bổ sung endpoint `GET /orders/{orderId}` để người dùng xem đơn hàng. Một thay đổi hoàn chỉnh cần đi qua các bước sau:

1. **Xác định yêu cầu bảo mật:** người gọi phải được xác thực; chỉ chủ sở hữu đơn hàng hoặc vai trò được ủy quyền mới được xem; dữ liệu trả về không chứa thông tin thanh toán nhạy cảm.
2. **Build:** dùng wrapper và phiên bản JDK đã khai báo; không đưa token hoặc thông tin môi trường vào artifact; ghi nhận commit tạo ra bản build.
3. **Unit test:** kiểm tra policy cho phép chủ sở hữu, từ chối người dùng khác và từ chối tenant khác.
4. **Integration/API test:** gửi request không token, token hết hạn, orderId không tồn tại, orderId của người khác và orderId hợp lệ; kiểm tra status code, response schema và dữ liệu bị ẩn.
5. **Kiểm tra lạm dụng:** xác minh endpoint không cho phép truy vấn hàng loạt bằng cách thay orderId liên tục mà không có giới hạn phù hợp; kiểm tra pagination nếu endpoint hỗ trợ danh sách.
6. **SCA:** quét dependency của artifact, xử lý cảnh báo mới hoặc ghi nhận ngoại lệ có thời hạn.
7. **Phát hành:** lưu báo cáo test, báo cáo dependency và SBOM gắn với artifact; triển khai staging và chạy smoke test trước khi promote cùng artifact đó.

Nếu test chỉ xác nhận người dùng đã đăng nhập có thể nhận được đơn hàng, lỗi phân quyền đối tượng vẫn có thể lọt qua. Nếu chỉ quét dependency mà không test quyền truy cập, pipeline vẫn không phát hiện được lỗi nghiệp vụ này.

## 7. Các lỗi thường gặp khi tổ chức build và test

- **Chỉ kiểm tra happy path:** test tạo và đọc tài nguyên bằng tài khoản hợp lệ nhưng không thử tài khoản khác, tenant khác hoặc vai trò thiếu quyền.
- **Chỉ kiểm tra role:** xác nhận người dùng có role phù hợp nhưng không xác minh quyền trên từng object được truyền qua path hoặc query parameter.
- **Tin vào kết quả compile:** build thành công không chứng minh validation, phân quyền, SSRF hay rate limit hoạt động đúng.
- **Chỉ quét dependency trực tiếp:** bỏ sót thư viện bắc cầu được kéo vào từ framework hoặc SDK.
- **Nâng cấp dependency không có regression test:** bản vá có thể khắc phục CVE nhưng đồng thời thay đổi hành vi hoặc gây lỗi tương thích.
- **Tắt cảnh báo để pipeline xanh:** làm mất tín hiệu về rủi ro và khiến nhóm không biết lỗ hổng còn tồn tại.
- **Build lại ở từng môi trường:** tạo ra khác biệt artifact giữa staging và production, làm giảm độ tin cậy của kết quả kiểm tra.
- **Chỉ test ở tầng service:** bỏ sót lỗi do cấu hình security filter, mapping endpoint, serialization hoặc middleware HTTP.
- **Không lưu bằng chứng:** sau phát hành không thể xác định chính xác mã nguồn, dependency và kết quả kiểm tra của artifact đang chạy.

## 8. Checklist trước khi phát hành

- [ ] Build dùng wrapper, JDK và plugin có phiên bản được kiểm soát.
- [ ] Artifact không chứa secret hoặc cấu hình riêng của môi trường.
- [ ] Có thể truy vết artifact về commit và lần chạy pipeline.
- [ ] Unit test và integration test trọng yếu đã pass.
- [ ] Endpoint nhạy cảm có test xác thực, phân quyền chức năng và phân quyền đối tượng.
- [ ] Có test tenant isolation, validation và mass assignment khi phù hợp.
- [ ] Các luồng outbound URL đã được kiểm tra SSRF nếu nghiệp vụ có gọi URL do người dùng cung cấp.
- [ ] Rate limit, kích thước request, timeout và concurrency được kiểm tra ở endpoint có rủi ro lạm dụng.
- [ ] Dependency trực tiếp và bắc cầu đã được quét; cảnh báo có người xử lý.
- [ ] Ngoại lệ dependency có lý do, người phê duyệt và ngày hết hạn.
- [ ] SBOM được tạo cho đúng artifact; container image được kiểm tra nếu có.
- [ ] Artifact đã kiểm tra được triển khai lên staging và được promote theo cùng định danh.

Build, test và kiểm tra dependency cần trở thành một phần thường xuyên của vòng đời API. Khi các kiểm tra được gắn với endpoint, đối tượng dữ liệu và luồng nghiệp vụ cụ thể, nhóm có bằng chứng rõ ràng hơn rằng phiên bản phát hành vừa hoạt động đúng vừa giữ được các ranh giới bảo mật đã thiết kế.
