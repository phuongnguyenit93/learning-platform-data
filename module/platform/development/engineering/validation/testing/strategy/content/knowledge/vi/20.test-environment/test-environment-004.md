# Cố định phiên bản ứng dụng, công cụ, thành phần phụ thuộc và cấu hình

Trong chiến lược kiểm thử `VALIDATION_TESTING_STRATEGY`, kết quả kiểm thử chỉ có ý nghĩa khi nhóm biết chính xác phần mềm đã được kiểm tra trong điều kiện nào. Cùng một mã nguồn có thể cho kết quả khác nhau nếu chạy bằng phiên bản runtime khác, thư viện khác, trình duyệt khác, database khác hoặc cấu hình khác. Một lỗi có thể xuất hiện trên máy của một thành viên nhưng không tái hiện được trên CI; một bộ test có thể pass ở staging nhưng thất bại ở production vì hai môi trường đã lệch nhau.

Vì vậy, nhóm cần **cố định và ghi nhận phiên bản ứng dụng, công cụ, thành phần phụ thuộc và cấu hình** trong môi trường kiểm thử. Mục tiêu là làm cho môi trường có thể tái lập, giúp so sánh kết quả giữa các lần chạy, phát hiện thay đổi gây lỗi và điều tra sự cố với đủ bằng chứng. Cố định phiên bản không có nghĩa giữ mọi thành phần cũ mãi mãi. Nhóm cần có cách nâng cấp có chủ đích, kiểm tra tương thích và cập nhật baseline khi thay đổi được phê duyệt.

## 1. Vì sao cần cố định môi trường kiểm thử?

Môi trường kiểm thử là tập hợp các yếu tố ảnh hưởng đến việc thực thi phần mềm và kết quả kiểm tra. Nó có thể bao gồm:

- Artifact hoặc phiên bản ứng dụng đang được kiểm tra.
- Ngôn ngữ, compiler, runtime, framework và thư viện.
- Công cụ build, test runner, browser automation và thiết bị.
- Database, message broker, cache, API và dịch vụ phụ thuộc.
- Hệ điều hành, container image, hạ tầng và topology mạng.
- Biến cấu hình, feature flag, locale, timezone và quyền truy cập.
- Dữ liệu kiểm thử, trạng thái ban đầu và cơ chế tạo/dọn dữ liệu.

Nếu những yếu tố này thay đổi mà không được ghi nhận, nhóm khó biết nguyên nhân của một kết quả khác thường. Ví dụ, test API có thể bắt đầu thất bại vì thư viện JSON được nâng cấp tự động; test giao diện có thể thay đổi kết quả do trình duyệt cập nhật; test ngày tháng có thể khác nhau do timezone của máy chạy.

Cố định môi trường giúp:

- **Tái lập lỗi:** người khác có thể dựng lại các phiên bản và cấu hình tương ứng để xác minh lỗi.
- **So sánh đáng tin cậy:** thay đổi kết quả giữa hai lần chạy có thể được liên hệ với thay đổi cụ thể.
- **Phát hiện hồi quy:** giảm nhiễu do môi trường thay đổi ngoài ý muốn.
- **Phân tích nguyên nhân:** xác định lỗi đến từ mã nguồn, thư viện, công cụ, cấu hình hay hạ tầng.
- **Kiểm soát phát hành:** biết artifact đã kiểm thử là artifact nào và điều kiện kiểm tra có đại diện cho môi trường đích không.
- **Hỗ trợ kiểm toán:** cung cấp bằng chứng về phiên bản, nguồn gốc và điều kiện thực hiện kiểm thử.

Môi trường ổn định không tự chứng minh phần mềm đúng. Nó làm cho bằng chứng dễ diễn giải hơn. Nhóm vẫn phải kiểm tra các phiên bản và cấu hình được hỗ trợ, thay đổi có chủ đích và hành vi trong điều kiện thực tế.

## 2. Phân biệt cố định phiên bản, tái lập và tương thích

Ba khái niệm này liên quan nhưng không đồng nghĩa.

- **Cố định phiên bản (version pinning):** chỉ định rõ phiên bản hoặc định danh bất biến của một thành phần được sử dụng, ví dụ JDK 21.0.x, phiên bản Playwright, digest của container image hoặc phiên bản API.
- **Tái lập môi trường (environment reproducibility):** có thể tạo lại môi trường với cùng các thành phần, phiên bản, cấu hình và điều kiện cần thiết để chạy kiểm thử.
- **Tương thích (compatibility):** các phiên bản thành phần có thể hoạt động cùng nhau theo hợp đồng và giới hạn đã xác định.

Một file khai báo phiên bản không đảm bảo môi trường tái lập nếu nó bỏ qua hệ điều hành, kiến trúc CPU, biến cấu hình, dịch vụ ngoài hoặc dữ liệu. Tương tự, hai thành phần đều được pin không có nghĩa chúng tương thích với nhau. Nhóm cần kiểm soát cả danh mục thành phần, cấu hình và ma trận tương thích.

### Ví dụ về môi trường không được cố định

Giả sử dự án khai báo dependency `library-x:2.+`. Máy của lập trình viên tải phiên bản 2.4.1 vào đầu tuần, còn CI tải 2.5.0 vài ngày sau. Nếu bản mới thay đổi cách xử lý null hoặc serialization, cùng mã nguồn có thể cho kết quả khác nhau. Việc pin chính xác phiên bản và dùng lockfile giúp tránh tự động nhận một phiên bản mới giữa hai lần chạy.

Tuy nhiên, khi nhóm chủ động nâng library lên 2.5.0, cần chạy test tương thích, đánh giá thay đổi và cập nhật lockfile có review. Cố định phiên bản nhằm kiểm soát thời điểm thay đổi, không ngăn tổ chức cập nhật.

## 3. Xác định những gì cần được quản lý phiên bản

Không chỉ ứng dụng có version. Mỗi thành phần có thể ảnh hưởng đến kết quả test cần được nhận diện và ghi nhận ở mức phù hợp.

### Ứng dụng và artifact

Ghi nhận release version, build number, commit SHA hoặc artifact digest. Với container, nên sử dụng image tag bất biến hoặc image digest để xác định chính xác nội dung image. Tag như `latest` có thể trỏ đến image khác theo thời gian nên không đủ để tái lập.

Nếu pipeline build lại cùng source ở nhiều môi trường, artifact có thể khác do thời điểm build, dependency hoặc tham số build. Nên tạo artifact một lần, xác minh và đưa cùng artifact qua các môi trường; cấu hình môi trường được cung cấp riêng theo quy trình kiểm soát.

### Ngôn ngữ, compiler và runtime

Ghi nhận phiên bản JDK, .NET runtime, Node.js, Python, compiler hoặc runtime tương ứng. Một thay đổi runtime có thể ảnh hưởng đến garbage collection, TLS, encoding, timezone database, API có sẵn hoặc hành vi thư viện.

Với ứng dụng Java, cần phân biệt JDK dùng để build với JRE/runtime dùng để chạy. Một dự án có thể compile bằng JDK 21 nhưng chạy production trên runtime khác; cần xác định cấu hình mục tiêu và kiểm tra tương thích.

### Công cụ build và test

Quản lý phiên bản Maven/Gradle, wrapper, test framework, plugin, browser driver, Playwright/Selenium, linter, static analyzer, code generator và công cụ migration. Phiên bản plugin build cũng có thể ảnh hưởng đến artifact dù dependency ứng dụng không đổi.

Nên dùng wrapper của dự án khi công cụ hỗ trợ, vì wrapper giúp nhóm và CI dùng cùng phiên bản build tool. Tuy nhiên, cần kiểm soát cả phiên bản runtime cần thiết để chạy wrapper.

### Thư viện và dependency bắc cầu

Ghi nhận dependency trực tiếp và dependency bắc cầu (transitive dependencies). Một thư viện trực tiếp có thể kéo theo hàng chục thư viện khác; nếu chỉ pin dependency trực tiếp, đồ thị phụ thuộc vẫn có thể thay đổi.

Dùng lockfile hoặc cơ chế dependency locking phù hợp với hệ sinh thái để ghi lại phiên bản được giải quyết đầy đủ. Review thay đổi lockfile như một phần của thay đổi mã nguồn.

### Dịch vụ và hạ tầng phụ thuộc

Ghi nhận phiên bản database engine, message broker, cache, search engine, service emulator, API contract và container image. Với dịch vụ được quản lý mà không kiểm soát được patch version, cần ghi nhận phiên bản hoặc release channel được nhà cung cấp công bố, cùng giới hạn và thời điểm kiểm tra.

### Hệ điều hành, browser và thiết bị

Ghi nhận hệ điều hành, kiến trúc CPU, browser/version, browser engine, độ phân giải, thiết bị và driver khi chúng ảnh hưởng đến hành vi. Với kiểm thử giao diện, browser auto-update có thể làm thay đổi kết quả hoặc screenshot baseline. Nhóm cần xác định ma trận browser được hỗ trợ và lịch nâng cấp.

### Cấu hình và dữ liệu

Phiên bản không chỉ là số version. Giá trị feature flag, timezone, locale, cấu hình retry, timeout, endpoint, schema, quyền và dữ liệu ban đầu đều có thể thay đổi hành vi. Cần lưu định danh hoặc snapshot cấu hình không nhạy cảm và cách tạo dữ liệu để có thể tái lập.

## 4. Chọn cách cố định phiên bản phù hợp

Không phải mọi thành phần đều được pin theo cùng một cách. Chọn cơ chế dựa trên đặc tính của thành phần và khả năng quản lý của tổ chức.

### Phiên bản chính xác

Khai báo một phiên bản cụ thể, chẳng hạn `2.4.1`, giúp tránh tự động nhận bản mới. Cách này phù hợp với thư viện, plugin, runtime và công cụ có version rõ ràng.

Tuy nhiên, số phiên bản có thể không xác định đầy đủ nội dung. Một nhà cung cấp có thể thay đổi artifact phía sau cùng một tag trong một số hệ thống. Với thành phần đóng gói, định danh digest thường mạnh hơn tag.

### Lockfile và dependency locking

Manifest mô tả dependency mong muốn; lockfile ghi lại phiên bản cụ thể đã được giải quyết, thường bao gồm cả dependency bắc cầu và checksum. Ví dụ, hệ sinh thái Node.js dùng `package-lock.json`, Yarn dùng lockfile riêng, Python có thể dùng lock/constraints theo công cụ, còn Gradle/Maven có các cơ chế quản lý dependency tương ứng.

Quy tắc thực hành:

- Commit lockfile vào repository nếu dự án và công cụ khuyến nghị.
- Dùng chế độ cài đặt tôn trọng lockfile trong CI.
- Không xóa và tạo lại lockfile tùy tiện để “sửa” lỗi dependency.
- Review thay đổi phiên bản, checksum và dependency bắc cầu.
- Cập nhật lockfile cùng với thay đổi dependency có chủ đích.

### Container image và digest

Container giúp đóng gói runtime, thư viện hệ thống và ứng dụng. Để tái lập, cần pin base image và image được triển khai bằng digest khi phù hợp, ví dụ `image@sha256:...`. Chỉ pin tag như `stable` hoặc `latest` có thể vẫn cho kết quả khác nếu tag được cập nhật.

Container không đóng gói mọi thứ. Kernel, CPU, mount, network, secret, volume, timezone hoặc dịch vụ ngoài vẫn có thể khác giữa môi trường. Vì vậy, cần ghi nhận cả cấu hình runtime và hạ tầng.

### Toolchain wrapper và version manager

Dùng Maven Wrapper, Gradle Wrapper hoặc công cụ quản lý runtime như SDKMAN, asdf, mise hay file version của dự án để thống nhất công cụ. File cấu hình cần được review và CI phải kiểm tra đúng phiên bản.

Tránh phụ thuộc vào phiên bản cài sẵn trên máy của một người. Tài liệu setup nên nêu rõ phiên bản, lệnh khởi tạo và cách xác nhận công cụ.

### Ma trận tương thích

Với hệ thống hỗ trợ nhiều phiên bản runtime, browser hoặc database, lập ma trận để chỉ ra các tổ hợp cần kiểm tra. Ví dụ, sản phẩm có thể hỗ trợ JDK 17 và 21, PostgreSQL 15 và 16, hoặc nhiều browser được khách hàng sử dụng.

Không nhất thiết kiểm tra mọi tổ hợp Cartesian product nếu chi phí quá lớn. Có thể chọn tổ hợp đại diện, phiên bản cũ nhất được hỗ trợ, phiên bản mới nhất được hỗ trợ và những kết hợp có rủi ro cao. Cần ghi rõ phạm vi chưa kiểm tra.

## 5. Quản lý phiên bản ứng dụng và artifact

Một nguyên tắc quan trọng là phân biệt source code, build và artifact.

- **Source revision:** commit hoặc revision của mã nguồn.
- **Build:** lần tạo artifact, có thể phụ thuộc toolchain, dependency và tham số build.
- **Artifact:** gói thực thi được triển khai, ví dụ JAR, package, image hoặc bundle frontend.
- **Release:** phiên bản được phát hành cùng cấu hình và thông tin triển khai.

Để tái lập, cần liên kết các định danh này. Chỉ ghi version `1.8.0` có thể chưa đủ nếu có nhiều build cùng version hoặc artifact được build lại.

### Build một lần, triển khai nhiều môi trường

Một cách làm đáng tin cậy là:

1. Build artifact từ commit và toolchain đã xác định.
2. Chạy kiểm tra chất lượng và lưu checksum/digest.
3. Đưa cùng artifact qua môi trường tích hợp, staging và production theo quy trình.
4. Cung cấp cấu hình môi trường riêng, có kiểm soát và không nhúng secret vào artifact.
5. Ghi lại release record gồm artifact, commit, cấu hình, thời điểm và kết quả kiểm tra.

Cách này giảm rủi ro “đã test một bản, triển khai một bản khác”. Nếu có lý do phải build khác theo môi trường, cần ghi rõ và có bằng chứng kiểm tra tương đương.

### Versioning và tương thích ngược

Semantic Versioning (SemVer) dùng dạng `MAJOR.MINOR.PATCH` với quy ước về thay đổi tương thích trong API công khai. Tuy nhiên, không phải mọi dependency hoặc nhà cung cấp đều tuân thủ SemVer đúng như mong đợi. Không nên chỉ dựa vào số version để kết luận an toàn; cần đọc release notes, kiểm tra contract và chạy test.

Với API hoặc message schema, cần xem xét phiên bản consumer/provider có thể cùng tồn tại trong giai đoạn triển khai. Với database, cần kiểm tra ứng dụng cũ và mới có thể cùng hoạt động trong thời gian migration hay không.

## 6. Cố định cấu hình môi trường

Phiên bản ứng dụng giống nhau vẫn có thể hoạt động khác nhau nếu cấu hình khác. Cấu hình cần được quản lý có kiểm soát, phân biệt giá trị theo môi trường và có khả năng truy vết.

### Tách cấu hình khỏi artifact

Không nên build một artifact riêng chỉ để nhúng URL, cờ tính năng hoặc thông số cho từng môi trường. Nên giữ artifact bất biến và cung cấp cấu hình khi chạy hoặc triển khai.

Những giá trị thường cần cấu hình gồm:

- Endpoint của database, API và message broker.
- Timeout, retry, pool size và giới hạn tài nguyên.
- Feature flag và rollout percentage.
- Locale, timezone, định dạng tiền tệ và encoding.
- Chế độ log, mức log và sampling.
- Quyền, role, certificate và thông tin xác thực.
- Tùy chọn cache, hàng đợi và xử lý bất đồng bộ.

### Quản lý cấu hình như mã nguồn

Với cấu hình không nhạy cảm, có thể lưu trong repository hoặc hệ thống quản lý cấu hình có version history. Mỗi thay đổi cần review, kiểm tra schema/validation và gắn với release hoặc môi trường áp dụng.

Cần tránh cấu hình thủ công không được ghi lại trên máy chủ. Nếu phải có thao tác khẩn cấp, ghi nhận người thực hiện, thời điểm, giá trị thay đổi và kế hoạch đưa trạng thái về cấu hình được quản lý.

### Quản lý secret riêng biệt

Mật khẩu, token, private key và connection string có thông tin xác thực không được lưu trong file cấu hình thông thường, log hoặc repository. Dùng secret manager hoặc cơ chế bảo vệ được tổ chức phê duyệt. Môi trường kiểm thử nên dùng credential riêng, quyền tối thiểu và có vòng đời rõ.

Không đưa secret thật vào snapshot cấu hình hoặc báo cáo test. Có thể lưu tên tham chiếu secret, version/rotation identifier hoặc trạng thái đã cấu hình mà không lưu giá trị bí mật.

### Cố định các giá trị dễ gây sai lệch

Đặc biệt chú ý:

- **Timezone:** đặt rõ UTC hoặc timezone nghiệp vụ; không dựa vào mặc định máy chạy.
- **Locale:** định dạng số, ngày, dấu thập phân và sắp xếp chuỗi có thể thay đổi.
- **Encoding:** xác định UTF-8 hoặc định dạng cần dùng cho dữ liệu.
- **Feature flags:** ghi nhận giá trị và đối tượng áp dụng tại thời điểm test.
- **Timeout/retry:** thay đổi nhỏ có thể làm khác kết quả bất đồng bộ.
- **Random seed:** cố định seed khi test cần tái lập dữ liệu ngẫu nhiên; không dùng seed cố định cho mục tiêu cần kiểm tra tính khó đoán trong môi trường bảo mật.
- **Clock:** dùng thời gian có thể điều khiển cho test logic phụ thuộc thời điểm.

## 7. Quản lý dữ liệu và trạng thái môi trường

Một môi trường có cùng phiên bản nhưng dữ liệu ban đầu khác nhau vẫn có thể cho kết quả khác. Vì vậy, cần quản lý fixture, seed data, schema và quy trình reset.

### Dữ liệu seed và fixture

Ghi lại cách tạo dữ liệu, phiên bản fixture, quan hệ giữa bản ghi và trạng thái ban đầu. Dữ liệu cần đại diện cho luồng nghiệp vụ và các trường hợp biên. Tránh phụ thuộc vào một tập dữ liệu được tạo thủ công từ lâu mà không ai biết nguồn gốc.

### Migration và schema

Ghi nhận phiên bản schema database và migration đã áp dụng. Một test cần biết đang chạy trên schema nào, có migration pending hay không và dữ liệu có tương thích với ứng dụng đang kiểm tra không.

### Reset và cô lập dữ liệu

Chọn cơ chế reset phù hợp như tạo database riêng cho test, transaction rollback, namespace riêng, tenant riêng hoặc fixture có ID duy nhất. Không để test chạy song song ghi vào cùng bản ghi dùng chung nếu không có cơ chế cô lập.

### Dữ liệu nhạy cảm

Ưu tiên dữ liệu tổng hợp hoặc đã được ẩn danh theo quy định. Nếu dữ liệu từ production được sử dụng cho kiểm thử, phải có căn cứ, kiểm soát truy cập, giảm thiểu trường dữ liệu và quy trình xử lý được phê duyệt. Không sao chép bí mật hoặc thông tin cá nhân vào môi trường kém bảo vệ chỉ để tái hiện lỗi.

## 8. Kiểm soát phiên bản của công cụ và dịch vụ phụ thuộc

### Công cụ kiểm thử

Browser automation, test runner, mocking library, coverage tool và static analyzer đều có thể ảnh hưởng kết quả. Cần pin phiên bản và ghi nhận plugin, driver hoặc browser binary liên quan.

Ví dụ, khi dùng Playwright, phiên bản package và browser binaries cần tương thích. Chỉ pin package nhưng cho phép browser tự cập nhật có thể tạo sai lệch. Khi nâng cấp, chạy bộ test giao diện đại diện và cập nhật baseline có review.

### Database và message broker

Phiên bản database có thể ảnh hưởng SQL, query planner, collation, transaction và extension. Phiên bản broker có thể ảnh hưởng delivery, ordering, retry hoặc cấu hình bảo mật. Nên chạy test tích hợp với phiên bản tương ứng môi trường mục tiêu và các phiên bản được hỗ trợ.

### API và dịch vụ bên ngoài

Với API ngoài, ghi nhận API version, endpoint, schema, contract và chế độ sandbox/production. Nhà cung cấp có thể thay đổi hành vi phía server mà không thay client package; cần contract test, kiểm tra thông báo thay đổi và theo dõi phụ thuộc.

Nếu dịch vụ ngoài không thể pin, ghi rõ điều gì nằm ngoài quyền kiểm soát và cách phát hiện thay đổi. Có thể dùng simulator hoặc recorded response cho test lặp lại, đồng thời duy trì một số kiểm tra tích hợp định kỳ với sandbox hoặc endpoint được phê duyệt.

### Hệ điều hành và môi trường thực thi

Ghi nhận container base image, OS package, CPU architecture và kernel khi có ảnh hưởng. Một image giống nhau chạy trên kiến trúc CPU khác hoặc kernel khác vẫn có thể có hành vi khác, đặc biệt với native library, filesystem, networking hoặc concurrency.

## 9. Phát hiện và quản lý environment drift

**Environment drift** là hiện tượng các môi trường hoặc cấu hình lệch nhau theo thời gian ngoài kế hoạch. Ví dụ, staging được cập nhật thư viện TLS nhưng production vẫn dùng bản cũ; một biến môi trường được sửa thủ công trên server; hoặc database staging đã áp dụng migration mới nhưng môi trường kiểm thử khác chưa áp dụng.

Drift có thể đến từ:

- Cập nhật tự động của OS, browser, runtime hoặc package.
- Thao tác thủ công ngoài pipeline.
- Cấu hình được sao chép giữa môi trường nhưng không cập nhật đồng bộ.
- Secret rotation hoặc chứng thư hết hạn.
- Dependency được giải quyết động hoặc lockfile không được dùng.
- Dịch vụ ngoài thay đổi phiên bản hoặc chính sách.
- Hạ tầng được thay đổi mà không cập nhật Infrastructure as Code.

### Cách phát hiện drift

- So sánh manifest/version inventory giữa các môi trường.
- Kiểm tra checksum hoặc digest của artifact và container image.
- So sánh cấu hình đã khai báo với cấu hình đang chạy.
- Dùng IaC plan hoặc công cụ phát hiện thay đổi ngoài quản lý.
- Kiểm tra phiên bản runtime, browser, database và service endpoint trong pipeline.
- Lưu release record và lịch sử cấu hình để biết thay đổi xảy ra khi nào.
- Chạy smoke/compatibility test sau khi có cập nhật nền tảng.

### Cách xử lý drift

1. Xác định thành phần hoặc giá trị đang lệch và phạm vi ảnh hưởng.
2. Phân biệt thay đổi được phê duyệt với thay đổi ngoài quy trình.
3. Đánh giá rủi ro và quyết định đưa môi trường về baseline hay cập nhật baseline.
4. Thực hiện thay đổi qua quy trình được kiểm soát.
5. Chạy lại kiểm tra phù hợp và ghi bằng chứng.
6. Cập nhật manifest, lockfile, tài liệu và kế hoạch nâng cấp.

Không phải mọi khác biệt giữa môi trường đều là drift cần xóa bỏ. Dev, test, staging và production có thể cần endpoint, quy mô hoặc quyền khác nhau. Điều cần kiểm soát là khác biệt có chủ đích, được ghi nhận và không làm mất giá trị của phép kiểm thử.

## 10. Cố định môi trường nhưng vẫn cập nhật an toàn

Pin phiên bản quá lâu có thể giữ lại lỗ hổng bảo mật, lỗi đã biết hoặc thành phần hết hỗ trợ. Do đó, nhóm cần cân bằng tính tái lập với việc cập nhật bảo mật và tương thích.

### Thiết lập chính sách nâng cấp

Chính sách có thể xác định:

- Ai sở hữu dependency, runtime, browser và base image.
- Tần suất kiểm tra bản cập nhật và cảnh báo bảo mật.
- Thời hạn xử lý lỗ hổng theo mức độ nghiêm trọng.
- Cách đánh giá release notes và breaking changes.
- Bộ test phải chạy khi nâng cấp từng nhóm thành phần.
- Cách phê duyệt, rollout và rollback thay đổi.
- Khi nào cần nâng cấp khẩn cấp ngoài chu kỳ.

### Nâng cấp có kiểm soát

Một quy trình điển hình:

1. Xác định lý do nâng cấp: bảo mật, lỗi, tính năng, hỗ trợ hoặc chuẩn hóa.
2. Xem release notes, dependency tree và cảnh báo tương thích.
3. Tạo nhánh hoặc thay đổi riêng, cập nhật version/lockfile có review.
4. Chạy unit, integration, contract, security và regression test phù hợp.
5. Kiểm tra build/artifact, cấu hình và môi trường đại diện.
6. Triển khai thử hoặc canary nếu thay đổi ảnh hưởng runtime/service.
7. Theo dõi metric và lỗi; dừng hoặc khôi phục nếu vượt tiêu chí.
8. Cập nhật baseline và tài liệu phiên bản sau khi phê duyệt.

### Không cập nhật mọi thứ cùng lúc

Khi nhiều thành phần thay đổi đồng thời, nếu test thất bại sẽ khó xác định nguyên nhân. Với thay đổi lớn, nên nâng cấp theo nhóm hoặc tách commit để dễ quy kết. Tuy nhiên, với lỗ hổng bảo mật nghiêm trọng, tổ chức có thể cần cập nhật nhiều thành phần nhanh hơn; khi đó cần tăng cường kiểm tra và ghi nhận quyết định rủi ro.

## 11. Tự động hóa việc tái lập môi trường

Môi trường nên được mô tả bằng file và script có thể review, thay vì dựa vào ghi nhớ hoặc thao tác thủ công.

### Environment manifest

Một manifest có thể ghi nhận các thành phần và phiên bản. Ví dụ minh họa:

```yaml
application:
  version: 3.8.2
  commit: 7d91c4a
  artifactDigest: sha256:abc123-example

toolchain:
  jdk: 21.0.4
  gradle: 8.10.2

services:
  postgres:
    image: postgres:16.4
  redis:
    image: redis:7.4.1

testTools:
  junit: 5.11.0
  playwright: 1.48.0

configuration:
  timezone: UTC
  locale: vi-VN
  featureSet: checkout-v3-test
```

Các giá trị trong ví dụ chỉ minh họa định dạng, không phải khuyến nghị phiên bản cho mọi dự án. Trong triển khai thực tế, container image nên được pin bằng digest nếu cần định danh bất biến; secret chỉ tham chiếu qua secret manager, không ghi giá trị thật vào manifest.

### Tạo môi trường bằng script hoặc container

Có thể dùng Docker Compose, devcontainer, Kubernetes manifests, Terraform, Ansible hoặc công cụ tương đương để tạo hạ tầng và dịch vụ phụ thuộc. Script cần có thể chạy lặp, xử lý lỗi rõ ràng và không để lại tài nguyên ngoài ý muốn.

### Kiểm tra manifest trong CI

CI có thể xác nhận:

- Toolchain đúng phiên bản được khai báo.
- Lockfile được sử dụng và không bị bỏ qua.
- Artifact có digest và nguồn build.
- Container image dùng tag/digest được phê duyệt.
- Schema/configuration hợp lệ.
- Dịch vụ phụ thuộc sẵn sàng và đúng phiên bản.
- Kết quả test gắn với manifest hoặc release record.

### Ghi nhận môi trường thực tế

Manifest mô tả trạng thái mong muốn; cần có cách xác minh trạng thái đang chạy. Pipeline có thể tạo báo cáo version inventory, image digest, runtime, schema và config reference. Nếu trạng thái thực tế khác manifest, phát cảnh báo hoặc chặn bước phát hành theo chính sách.

## 12. Bằng chứng cần lưu cho mỗi lần kiểm thử

Một báo cáo test có thể pass nhưng khó tái lập nếu không biết nó chạy trên môi trường nào. Với các lần chạy quan trọng, lưu:

- Commit SHA, build ID, artifact version và digest.
- Phiên bản runtime, compiler, build tool và test runner.
- Dependency lockfile hoặc dependency inventory.
- Container image digest, OS/architecture và phiên bản dịch vụ phụ thuộc.
- Browser/driver/device và cấu hình hiển thị khi kiểm thử giao diện.
- Phiên bản schema database, migration và trạng thái dữ liệu ban đầu.
- Config manifest, feature flags, locale, timezone và các giá trị không nhạy cảm.
- Tham chiếu secret/config version mà không lưu bí mật.
- Thời điểm chạy, môi trường, người hoặc pipeline thực hiện.
- Kết quả test, log, trace, lỗi và liên kết đến bằng chứng.

Không nhất thiết chép mọi thông tin vào từng test case. Có thể lưu một environment manifest gắn với test run ID, rồi liên kết từ báo cáo. Quan trọng là người điều tra có thể truy ngược từ kết quả đến đúng môi trường.

## 13. Ví dụ xuyên suốt: chuẩn hóa môi trường kiểm thử cho ứng dụng Java

Giả sử một dịch vụ thương mại điện tử được phát triển bằng Java, build bằng Gradle, lưu dữ liệu trong PostgreSQL, dùng Redis để cache và chạy test API/UI qua CI.

### Vấn đề ban đầu

- Máy lập trình viên dùng JDK 21, nhưng CI lấy JDK mặc định của runner.
- Gradle Wrapper không được dùng nhất quán; mỗi máy cài một phiên bản Gradle.
- Dependency có khai báo version range và không có dependency locking.
- PostgreSQL chạy bằng tag image có thể thay đổi.
- Browser trên máy cá nhân tự cập nhật, trong khi browser trên CI khác phiên bản.
- Timezone của máy chạy test khác nhau.
- Một số feature flag được chỉnh trực tiếp trong staging nhưng không ghi lại.

Kết quả là test ngày tháng và UI có lúc pass, lúc fail; lỗi không tái hiện được giữa máy cá nhân và CI.

### Biện pháp chuẩn hóa

1. Chỉ định JDK và Gradle Wrapper version, xác minh trong CI.
2. Khóa dependency và commit lockfile phù hợp với dự án.
3. Pin PostgreSQL/Redis image theo phiên bản và digest được quản lý.
4. Pin browser automation package và browser binary tương thích.
5. Thiết lập timezone/locale rõ ràng cho test; dùng Clock injection cho logic phụ thuộc thời gian.
6. Đưa feature flag và cấu hình không nhạy cảm vào manifest có version; secret lấy từ secret manager.
7. Tạo môi trường dịch vụ phụ thuộc bằng script/container có thể chạy lặp.
8. Gắn manifest, artifact digest và kết quả test vào mỗi CI run.

### Xác minh sau chuẩn hóa

Nhóm chạy cùng commit và manifest trên máy phát triển được hỗ trợ và CI. Kết quả test cần ổn định; khi cố tình đổi một dependency hoặc browser version, pipeline phải thể hiện rõ thay đổi trong manifest và chạy bộ test tương thích. Nhóm cũng kiểm tra việc dựng môi trường mới từ đầu để xác nhận không còn bước thủ công bị bỏ sót.

### Duy trì baseline

Khi có bản cập nhật JDK hoặc PostgreSQL, nhóm tạo thay đổi riêng, đọc release notes, chạy test tương thích và cập nhật manifest sau khi phê duyệt. Baseline mới được lưu cùng release record để lần sau có thể xác định môi trường đã dùng.

## 14. Những sai lầm thường gặp

**Chỉ pin dependency trực tiếp.** Dependency bắc cầu vẫn có thể thay đổi. Dùng lockfile hoặc dependency locking để ghi lại toàn bộ đồ thị phiên bản được giải quyết.

**Dùng tag động như `latest`.** Tag có thể trỏ đến nội dung khác theo thời gian. Với artifact/container cần tái lập, dùng version cụ thể và digest khi phù hợp.

**Cho rằng cùng mã nguồn nghĩa là cùng ứng dụng.** Compiler, runtime, plugin, dependency và tham số build có thể làm artifact khác nhau. Gắn commit với build và artifact digest.

**Build riêng artifact cho mỗi môi trường.** Điều này có thể khiến production chạy thứ chưa được test. Ưu tiên build một lần, promote cùng artifact và quản lý cấu hình riêng.

**Chỉ ghi version mà không ghi cấu hình.** Timezone, feature flag, timeout, locale và dữ liệu ban đầu cũng ảnh hưởng kết quả. Ghi manifest cấu hình không nhạy cảm và tham chiếu secret an toàn.

**Cố định phiên bản nhưng không cập nhật.** Pin quá lâu làm tăng rủi ro bảo mật và hết hỗ trợ. Có chính sách nâng cấp định kỳ, đánh giá lỗ hổng và kiểm tra tương thích.

**Cho rằng container giải quyết mọi khác biệt.** Kernel, CPU, network, mount, secret và dịch vụ ngoài vẫn có thể khác. Ghi nhận những yếu tố ngoài container có ảnh hưởng.

**Bỏ qua browser và driver.** UI test có thể thay đổi do browser binary hoặc driver khác. Pin và nâng cấp chúng có kiểm soát theo ma trận hỗ trợ.

**Sao chép cấu hình production vào test không kiểm soát.** Có thể làm lộ secret hoặc dữ liệu cá nhân. Dùng cấu hình riêng, credential riêng và dữ liệu tổng hợp/đã xử lý.

**Không phát hiện thay đổi thủ công.** Môi trường có thể lệch manifest mà không ai biết. Dùng version inventory, IaC drift detection và kiểm tra sau triển khai.

**Coi môi trường giống hệt nhau là mục tiêu tuyệt đối.** Các môi trường có thể cần quy mô, endpoint và quyền khác nhau. Hãy quản lý khác biệt có chủ đích và xác minh những đặc tính cần tương đương.

## 15. Checklist cố định và tái lập môi trường kiểm thử

### Thành phần và phiên bản

- [ ] Ứng dụng có commit, build ID, version và artifact digest.
- [ ] Runtime, compiler, build tool và plugin được chỉ định rõ.
- [ ] Dependency trực tiếp và bắc cầu được khóa bằng cơ chế phù hợp.
- [ ] Container image, database, broker, cache và dịch vụ phụ thuộc có version/digest được ghi nhận.
- [ ] Browser, driver, thiết bị và OS được quản lý theo ma trận hỗ trợ.

### Cấu hình và dữ liệu

- [ ] Cấu hình không nhạy cảm có version hoặc manifest.
- [ ] Secret được quản lý riêng và không xuất hiện trong repository/log.
- [ ] Timezone, locale, encoding, feature flag, timeout và retry được xác định.
- [ ] Dữ liệu seed/fixture, schema và migration có thể tái tạo.
- [ ] Trạng thái được cô lập và có quy trình reset/dọn dẹp.

### Tự động hóa và drift

- [ ] Có script/container/IaC để tạo môi trường lặp lại.
- [ ] CI xác minh đúng toolchain, lockfile, artifact và dịch vụ phụ thuộc.
- [ ] Có version inventory hoặc báo cáo trạng thái thực tế.
- [ ] Thay đổi thủ công và drift được phát hiện, review và xử lý.
- [ ] Có lịch và chủ sở hữu cho việc nâng cấp dependency, runtime và image.

### Bằng chứng và tương thích

- [ ] Test run liên kết được với manifest, commit, artifact và cấu hình.
- [ ] Có ma trận tương thích cho các phiên bản cần hỗ trợ.
- [ ] Các bản nâng cấp được kiểm tra bằng test phù hợp trước khi cập nhật baseline.
- [ ] Giới hạn do dịch vụ ngoài hoặc môi trường không thể pin được ghi rõ.
- [ ] Kết quả và rủi ro tồn dư được lưu cùng release record.

## 16. Tự kiểm tra mức độ hiểu

**Tình huống 1:** CI và máy lập trình viên dùng cùng commit nhưng khác phiên bản JDK. Test serialization chỉ thất bại trên CI. Cần so sánh toolchain và runtime thực tế, chuẩn hóa phiên bản, sau đó chạy lại để xác định ảnh hưởng của runtime.

**Tình huống 2:** Container test dùng `postgres:latest`. Một lần chạy mới có hành vi query khác. Cần pin phiên bản image và digest được phê duyệt, ghi nhận database version và có quy trình nâng cấp riêng.

**Tình huống 3:** `package.json` chỉ định một khoảng phiên bản nhưng lockfile không được dùng trong CI. Dependency bắc cầu thay đổi theo thời điểm. Cần commit lockfile và cấu hình CI cài đặt theo lockfile; review thay đổi khi nâng cấp.

**Tình huống 4:** Staging và production dùng cùng artifact nhưng khác feature flag. Đây có thể là khác biệt có chủ đích, nhưng cần ghi lại giá trị, nhóm người dùng áp dụng và kiểm tra nhánh hành vi tương ứng. Cùng artifact không đồng nghĩa cùng cấu hình.

**Tình huống 5:** Nhóm pin mọi thư viện trong hai năm để giữ test ổn định, nhưng một dependency có lỗ hổng nghiêm trọng. Cần áp dụng chính sách nâng cấp bảo mật, đánh giá release notes và chạy test tương thích; không nên dùng tính ổn định làm lý do trì hoãn vô thời hạn.

**Tình huống 6:** Test lỗi chỉ tái hiện được trên môi trường có locale `vi-VN`. Báo cáo trước đó không lưu locale. Cần bổ sung locale vào manifest và xem đây là một phần của điều kiện tái lập.

Khi đánh giá một lần chạy test, hãy tự hỏi: **đã kiểm tra artifact nào, bằng toolchain và dependency phiên bản nào, trên dịch vụ và dữ liệu nào, với cấu hình gì?** Nếu không thể trả lời hoặc tái tạo các điều kiện này, kết quả kiểm thử chưa có đủ ngữ cảnh để điều tra và so sánh đáng tin cậy.

## Kết luận

Cố định phiên bản ứng dụng, công cụ, thành phần phụ thuộc và cấu hình giúp môi trường kiểm thử có thể tái lập, giảm nhiễu do thay đổi ngoài ý muốn và hỗ trợ điều tra lỗi. Nhóm cần quản lý artifact và toolchain, khóa dependency trực tiếp lẫn bắc cầu, ghi nhận dịch vụ/hạ tầng, kiểm soát cấu hình và dữ liệu, phát hiện environment drift, đồng thời duy trì chính sách nâng cấp an toàn. Khi mỗi test run được liên kết với manifest và bằng chứng môi trường thực tế, kết quả trở nên dễ diễn giải, so sánh và sử dụng trong quyết định chất lượng.
