# Đối chiếu điều kiện chạy cục bộ với môi trường CI

**Chương:** CI/CD  
**Phạm vi module:** `VALIDATION_TESTING_STRATEGY`

Một kiểm thử có thể đạt trên máy của lập trình viên nhưng thất bại trong hệ thống tích hợp liên tục (Continuous Integration, CI). Hiện tượng này thường được mô tả ngắn gọn là “máy tôi chạy được”. Nguyên nhân có thể nằm ở phiên bản runtime, cấu hình, dữ liệu, hệ điều hành, quyền truy cập, mạng, tài nguyên, thứ tự chạy hoặc cách pipeline chuẩn bị môi trường. Nếu nhóm chỉ chạy lại test mà không so sánh điều kiện, lỗi có thể tiếp tục tái diễn và làm giảm niềm tin vào kết quả CI.

Đối chiếu điều kiện cục bộ với CI là hoạt động xác định những yếu tố có thể ảnh hưởng đến kết quả kiểm thử, ghi nhận chúng ở cả hai môi trường và thu hẹp khác biệt có ý nghĩa. Mục tiêu không phải làm hai môi trường giống nhau tuyệt đối. Mục tiêu là bảo đảm các điều kiện liên quan đến hành vi cần kiểm tra được kiểm soát, có thể tái lập và đủ tương đồng để kết quả có ý nghĩa.

Bài học này trình bày cách kiểm kê môi trường, chuẩn hóa lệnh chạy, so sánh runtime và cấu hình, kiểm soát dữ liệu và phụ thuộc, tái hiện lỗi CI ở máy cục bộ, và thiết kế pipeline tạo bằng chứng chẩn đoán. Nội dung cũng phân biệt khác biệt môi trường có chủ đích với sai lệch ngoài ý muốn.

Sau bài học, người học có thể:

- Giải thích vì sao cùng một test có thể cho kết quả khác nhau giữa máy cục bộ và CI.
- Lập danh sách điều kiện cần đối chiếu theo mục tiêu kiểm thử.
- Chuẩn hóa runtime, dependency, lệnh chạy, cấu hình và dữ liệu.
- Nhận diện khác biệt về hệ điều hành, filesystem, locale, múi giờ, quyền, mạng và tài nguyên.
- Tái hiện lỗi CI trong môi trường cục bộ có kiểm soát.
- Phân loại lỗi do mã sản phẩm, test, cấu hình, môi trường hoặc pipeline.
- Thiết kế báo cáo và artifact giúp truy nguyên lần chạy.
- Duy trì mức tương đồng cần thiết mà vẫn giữ được các kiểm tra đa môi trường có chủ đích.

## 1. Vì sao kết quả cục bộ và CI có thể khác nhau?

Máy cục bộ và runner CI có thể cùng chạy một commit nhưng không có cùng điều kiện. Máy cá nhân thường tích lũy trạng thái qua nhiều ngày: dependency đã tải, biến môi trường đã đặt, dữ liệu cũ còn trong cơ sở dữ liệu, tiến trình nền đang chạy hoặc file sinh ra từ lần build trước. Runner CI thường được tạo mới hoặc tái sử dụng theo chính sách của nền tảng, có thư mục làm việc, quyền và giới hạn tài nguyên riêng.

Một số khác biệt phổ biến:

- **Phiên bản công cụ:** JDK, compiler, build tool, browser, driver hoặc thư viện khác nhau.
- **Hệ điều hành và kiến trúc:** Windows, Linux, macOS; x86-64 và ARM; cách xử lý đường dẫn và quyền khác nhau.
- **Cấu hình:** biến môi trường, file cấu hình, profile, feature flag hoặc giá trị mặc định khác nhau.
- **Dữ liệu và trạng thái:** máy cục bộ có dữ liệu cũ hoặc cache; CI dùng database rỗng hoặc dữ liệu seed mới.
- **Phụ thuộc ngoài:** CI có proxy, DNS, firewall, quota hoặc đường mạng khác.
- **Tài nguyên:** runner có ít CPU, RAM, dung lượng đĩa hoặc giới hạn thời gian hơn máy phát triển.
- **Đồng thời:** CI chạy nhiều test hoặc job song song, làm lộ tranh chấp dữ liệu và tài nguyên.
- **Thời gian:** múi giờ, locale, đồng hồ, thời điểm chạy và thứ tự sự kiện khác nhau.
- **Quyền và bảo mật:** người dùng chạy tiến trình, quyền đọc/ghi, chứng thư và secret khác nhau.
- **Lệnh và phạm vi test:** lập trình viên chạy một test cụ thể, trong khi CI chạy profile, tag hoặc toàn bộ suite khác.

Một lần chạy cục bộ đạt chỉ chứng minh test đạt trong điều kiện cục bộ đã sử dụng. Nó không tự chứng minh cùng commit sẽ đạt trên mọi runner hoặc mọi cấu hình được hỗ trợ.

### 1.1. Phân biệt môi trường và đầu vào

Kết quả test chịu ảnh hưởng bởi cả môi trường lẫn đầu vào. Ví dụ, test thanh toán có thể thất bại ở CI vì:

- CI dùng tài khoản thử nghiệm khác.
- Dữ liệu seed không có phương thức thanh toán mà test mong đợi.
- Sandbox bị giới hạn tốc độ.
- Secret không được cấp cho pull request từ nhánh ngoài.
- Test chạy song song và dùng chung một đơn hàng.

Nếu chỉ nhìn thông báo “payment rejected”, nhóm có thể nhầm lỗi nghiệp vụ với lỗi dữ liệu hoặc cấu hình. Cần ghi lại phiên bản, cấu hình không nhạy cảm, dữ liệu định danh và trạng thái phụ thuộc tại thời điểm chạy.

### 1.2. Không phải mọi khác biệt đều cần loại bỏ

Một số khác biệt là mục tiêu kiểm thử. Ví dụ, dự án hỗ trợ Windows và Linux cần chạy trên cả hai hệ điều hành để phát hiện lỗi tương thích. Khi đó, pipeline nên có ma trận môi trường thay vì ép mọi job dùng một hệ điều hành.

Ngược lại, nếu mục tiêu của một unit test là xác minh quy tắc tính phí, việc test vô tình phụ thuộc vào múi giờ của runner là nhiễu cần loại bỏ. Cần phân biệt khác biệt có chủ đích trong ma trận kiểm thử với khác biệt không được kiểm soát.

## 2. Xác định phạm vi đối chiếu

Không cần so sánh mọi chi tiết của hai máy. Hãy bắt đầu từ loại test, hành vi cần xác minh và lỗi đang điều tra.

### 2.1. Đối chiếu theo tầng kiểm thử

| Tầng kiểm thử | Điều kiện thường quan trọng |
|---|---|
| Unit test | JDK/runtime, dependency, locale, múi giờ, seed, trạng thái tĩnh và cấu hình test |
| Component test | Cấu hình component, fake/stub, file, quyền và dữ liệu cục bộ |
| Integration test | Database, broker, container, schema, network, credential và thứ tự khởi động |
| API/contract test | Endpoint, phiên bản API, header, token, dữ liệu và timeout |
| UI/E2E test | Browser, driver, độ phân giải, font, locale, trạng thái phiên, dữ liệu và tốc độ môi trường |
| Performance test | CPU, RAM, số worker, giới hạn runner, mạng, tải nền và dữ liệu đại diện |
| Security test | Quyền, secret, chứng thư, network policy, danh tính và cấu hình bảo mật |

Tầng càng cao thường càng có nhiều phụ thuộc môi trường. Tuy nhiên, unit test cũng có thể khác kết quả nếu sử dụng thời gian hệ thống, file, locale hoặc biến môi trường trực tiếp.

### 2.2. Xác định một lần chạy có thể so sánh

Hai lần chạy chỉ nên được so sánh khi các yếu tố cần thiết tương đương. Ghi nhận tối thiểu:

- Commit hoặc revision được kiểm thử.
- Phiên bản test và mã nguồn build.
- Lệnh, task, profile và bộ lọc test.
- Runtime, build tool và dependency lock/resolution.
- Hệ điều hành, kiến trúc và image/container nếu có.
- Cấu hình, feature flag và profile môi trường.
- Dữ liệu hoặc định danh dataset.
- Số worker, mức song song và timeout.
- Thời điểm chạy và trạng thái dịch vụ phụ thuộc.

Nếu commit khác nhau, dependency được cập nhật hoặc dữ liệu thay đổi, kết quả khác nhau chưa chắc do môi trường. Hãy khóa hoặc ghi nhận những yếu tố đó trước khi kết luận.

## 3. Lập bảng kiểm kê điều kiện môi trường

Một bảng kiểm kê giúp nhóm có điểm xuất phát chung. Không cần thu thập bí mật hoặc toàn bộ thông tin máy; chỉ ghi những thuộc tính liên quan và an toàn để chia sẻ.

### 3.1. Nhóm thông tin cần ghi

| Nhóm | Thuộc tính ví dụ | Cách xác minh |
|---|---|---|
| Mã nguồn | Commit, branch, trạng thái working tree | Git revision và trạng thái build |
| Hệ điều hành | Tên, phiên bản, kiến trúc | Thông tin runner hoặc lệnh hệ thống |
| Runtime | JDK, JVM, Node hoặc runtime khác | Phiên bản executable và thuộc tính runtime |
| Build tool | Gradle/Maven và wrapper version | Wrapper trong repository và output phiên bản |
| Dependency | Phiên bản đã resolve, lockfile, repository | Báo cáo dependency/build log |
| Container | Image và digest/tag, runtime container | Cấu hình image và metadata runner |
| Cấu hình | Profile, biến môi trường, feature flag | Danh sách tên và trạng thái đã che giá trị nhạy cảm |
| Dữ liệu | Dataset, migration, seed, trạng thái khởi tạo | Mã dataset và log setup |
| Phụ thuộc | Database, broker, API, sandbox | Endpoint đã làm sạch, phiên bản và health check |
| Tài nguyên | CPU, RAM, disk, worker, timeout | Metadata runner và cấu hình job |
| Thời gian | UTC timestamp, timezone, locale | Log và thuộc tính tiến trình |
| Quyền | User, nhóm, quyền file, credential scope | Cấu hình runner và kiểm tra truy cập |

### 3.2. Mẫu bảng so sánh

| Thuộc tính | Cục bộ | CI | Khác biệt có ý nghĩa? | Hành động |
|---|---|---|---|---|
| JDK | 21 | 21 | Không | Giữ đồng nhất |
| Hệ điều hành | Windows | Linux | Có | Kiểm tra tính tương thích đường dẫn và filesystem |
| Timezone | Asia/Ho_Chi_Minh | UTC | Có thể có | Cố định trong test hoặc xác minh quy tắc múi giờ |
| Mức song song | 1 worker | 4 workers | Có | Kiểm tra dữ liệu dùng chung và race condition |
| Database | Có dữ liệu cũ | Database mới | Có | Chuẩn hóa migration và seed |

Đây là ví dụ minh họa. Giá trị thực tế phải được lấy từ lần chạy đang điều tra. Cột “Khác biệt có ý nghĩa?” cần được đánh giá theo mục tiêu test, không tự động coi mọi khác biệt là lỗi.

### 3.3. Chỉ thu thập thông tin cần thiết

Không đưa token, mật khẩu, private key, cookie, dữ liệu cá nhân hoặc payload nhạy cảm vào bảng so sánh. Với biến môi trường, có thể ghi tên biến, biến có được đặt hay không, nguồn cấu hình và loại secret; không ghi giá trị. Với endpoint, loại bỏ thông tin xác thực và query chứa dữ liệu nhạy cảm.

## 4. Chuẩn hóa runtime và công cụ build

Khác biệt phiên bản runtime là một nguyên nhân phổ biến khiến test chỉ thất bại ở CI.

### 4.1. Dùng phiên bản runtime được khai báo rõ

Với dự án Java, cần đối chiếu:

- Phiên bản JDK dùng để chạy build.
- Phiên bản compiler và `--release` hoặc toolchain target.
- Phiên bản JVM thực tế của tiến trình test.
- Phiên bản Gradle/Maven và plugin build.
- Phiên bản browser/driver nếu chạy UI test.

JDK dùng để chạy Gradle không nhất thiết giống phiên bản target bytecode. Hãy phân biệt runtime của build với toolchain dùng để biên dịch và chạy test.

### 4.2. Ưu tiên wrapper và cấu hình trong repository

Nếu dự án có Gradle Wrapper hoặc Maven Wrapper, dùng wrapper để cố định phiên bản build tool. Điều này giảm phụ thuộc vào phiên bản cài toàn cục trên máy cá nhân hoặc runner.

Ví dụ:

```bash
./gradlew clean test
```

Trên Windows:

```powershell
.\gradlew.bat clean test
```

Lệnh thực tế cần theo hướng dẫn build của dự án. Không tự thay bằng một phiên bản Gradle/Maven khác chỉ vì máy cá nhân đã cài sẵn.

### 4.3. Khóa và kiểm tra dependency

Dependency có thể thay đổi nếu build tải phiên bản mới theo khoảng version hoặc repository trả về artifact khác. Để tăng tính tái lập:

- Dùng dependency locking hoặc cơ chế quản lý version phù hợp.
- Commit lockfile và cấu hình wrapper cần thiết.
- Hạn chế version động trong build quan trọng.
- Theo dõi repository và mirror mà CI sử dụng.
- Kiểm tra cache không làm che một dependency thiếu hoặc artifact sai.
- Ghi nhận dependency resolution khi cần điều tra.

Không nên xóa cache như phản xạ đầu tiên. Cache có thể chỉ làm lộ hoặc che một vấn đề; cần so sánh lần chạy có cache và lần chạy sạch để xác định nguyên nhân.

### 4.4. Đối chiếu tham số JVM và môi trường tiến trình

Các tham số như heap size, encoding, locale, timezone, system properties và agent có thể khác nhau giữa máy cục bộ và CI. Kiểm tra cấu hình được truyền vào tiến trình test, không chỉ cấu hình của terminal khởi chạy build.

Ví dụ, một test giả định charset mặc định là UTF-8 có thể đạt trên máy cá nhân nhưng thất bại trên runner có cấu hình khác. Nên chỉ định encoding rõ trong ứng dụng, test và công cụ xử lý file khi phù hợp.

## 5. Chuẩn hóa lệnh chạy và phạm vi test

Một nguồn sai lệch phổ biến là cục bộ và CI thực hiện hai công việc khác nhau.

### 5.1. Dùng cùng task và bộ lọc test

Lập trình viên có thể chỉ chạy một test class, trong khi CI chạy toàn bộ suite. Một test đạt riêng lẻ vẫn có thể thất bại khi chạy cùng các test khác vì trạng thái tĩnh, dữ liệu dùng chung, thứ tự hoặc song song.

Khi điều tra, cần chạy theo các mức:

1. Test cụ thể từng thất bại.
2. Nhóm test hoặc module chứa test đó.
3. Toàn bộ suite tương ứng với CI.
4. Cùng cấu hình song song hoặc profile mà CI dùng.

Nếu test chỉ thất bại ở bước 3 hoặc 4, hãy tập trung vào tương tác giữa test, trạng thái chia sẻ và tài nguyên.

### 5.2. Tạo một lệnh chuẩn

Nhóm nên định nghĩa một lệnh build/test chuẩn trong tài liệu dự án hoặc script dùng chung. Pipeline và lập trình viên gọi cùng task, tham số và profile khi mục tiêu là tái hiện cùng một hành vi.

Ví dụ minh họa:

```bash
./gradlew clean test
```

Nếu CI có bước riêng như integration test hoặc contract test, lệnh chuẩn cần thể hiện rõ các task đó. Không nên giả định `test` tự chạy mọi tầng kiểm thử.

### 5.3. Ghi lại lệnh và biến thể

Trong log hoặc báo cáo, ghi:

- Lệnh thực tế đã chạy.
- Task, tag, profile và filter.
- Tham số JVM và biến môi trường không nhạy cảm.
- Có dùng cache hay không.
- Số worker và retry policy.
- Thư mục làm việc và loại runner.

Khi lệnh quá dài, lưu nó dưới dạng script hoặc cấu hình version-controlled để tránh sai khác do copy thủ công.

## 6. So sánh cấu hình và biến môi trường

Cấu hình quyết định ứng dụng kết nối dịch vụ nào, dùng quy tắc nào và bật tính năng nào. Một giá trị mặc định ở cục bộ có thể khác giá trị pipeline cung cấp.

### 6.1. Phân biệt cấu hình với secret

Chia cấu hình thành:

- **Cấu hình không nhạy cảm:** profile, timezone, locale, endpoint nội bộ không chứa thông tin xác thực, feature flag và giới hạn timeout.
- **Secret:** mật khẩu, token, API key, private key, cookie hoặc thông tin xác thực.

Cả hai đều cần được quản lý rõ, nhưng secret phải được cấp qua secret store hoặc cơ chế bảo mật của CI. Không commit secret vào repository và không in giá trị ra log.

### 6.2. Kiểm tra biến bắt buộc

Ứng dụng nên thất bại sớm với thông báo rõ khi thiếu cấu hình bắt buộc. Tránh tự động dùng endpoint production hoặc giá trị mặc định không an toàn khi biến môi trường không tồn tại.

Có thể kiểm tra sự hiện diện mà không hiển thị giá trị:

```bash
if [ -z "${TEST_API_BASE_URL:-}" ]; then
  echo "TEST_API_BASE_URL is required"
  exit 1
fi
```

Không dùng lệnh tương tự để in token hoặc bí mật. Trong PowerShell, có thể kiểm tra biến và chỉ in trạng thái có/không, không in nội dung secret.

### 6.3. So sánh profile và feature flag

Ví dụ, cục bộ dùng profile `test` nhưng CI vô tình dùng `staging`. Hai profile có thể khác:

- Cơ sở dữ liệu và dữ liệu seed.
- Cơ chế gửi email hoặc thông điệp.
- Bật/tắt tính năng.
- Timeout và retry.
- Cấu hình xác thực.

Hãy ghi profile đang hoạt động và các flag liên quan trong báo cáo. Nếu khác biệt là có chủ đích, test cần xác minh hành vi theo đúng profile đó.

### 6.4. Tránh cấu hình phụ thuộc máy cá nhân

Không nên dựa vào file cấu hình chỉ tồn tại trên máy một lập trình viên, biến môi trường được đặt thủ công hoặc credential trong thư mục cá nhân. Mọi cấu hình cần thiết để tái lập test phải được khai báo trong repository hoặc cấp qua cơ chế môi trường có kiểm soát.

## 7. Đối chiếu dữ liệu và trạng thái dịch vụ

Test có thể đạt cục bộ vì database đã có dữ liệu từ lần chạy trước. CI dùng database mới nên phát hiện thiếu migration hoặc setup không đầy đủ.

### 7.1. Bắt đầu từ trạng thái sạch

Kiểm tra test có chạy được trên database hoặc schema mới không. Pipeline nên có bước:

1. Khởi tạo dịch vụ dữ liệu.
2. Áp dụng migration đúng thứ tự.
3. Nạp seed hoặc fixture cần thiết.
4. Kiểm tra trạng thái sẵn sàng.
5. Chạy test.
6. Dọn dữ liệu hoặc hủy môi trường theo chính sách.

Không phụ thuộc vào dữ liệu được tạo thủ công từ trước. Nếu test cần dữ liệu tồn tại, phải có bước setup có thể lặp lại.

### 7.2. Kiểm tra phiên bản schema và migration

Đối chiếu phiên bản database, schema, extension, collation và migration state. Một test có thể đạt trên database cũ nhưng thất bại khi CI chạy schema mới. Cần kiểm tra cả đường nâng cấp từ phiên bản được hỗ trợ và đường khởi tạo mới nếu đó là yêu cầu sản phẩm.

### 7.3. Cô lập dữ liệu giữa test và worker

Test chạy song song có thể cập nhật cùng một tài khoản, bản ghi hoặc mã dùng một lần. Dùng định danh riêng theo test/run, transaction hoặc namespace phù hợp. Nếu cần chia sẻ fixture, xác định rõ quyền sở hữu và vòng đời.

### 7.4. Xác minh readiness, không chỉ process đã khởi động

Container hoặc service có thể đang chạy nhưng chưa sẵn sàng nhận request. Dùng health check hoặc kiểm tra điều kiện cụ thể như kết nối database, migration hoàn tất và endpoint trả trạng thái sẵn sàng. Một khoảng sleep cố định không bảo đảm dịch vụ đã sẵn sàng.

### 7.5. Dọn dẹp sau test

Test cần cleanup cả khi assertion thất bại. Dữ liệu còn sót có thể làm test sau đạt hoặc thất bại tùy thứ tự. Với môi trường dùng chung, dùng namespace hoặc dữ liệu có định danh riêng để tránh xóa nhầm tài nguyên của job khác.

## 8. Khác biệt hệ điều hành, filesystem và đường dẫn

Các test làm việc với file hoặc tiến trình thường bộc lộ khác biệt giữa Windows và Linux.

### 8.1. Phân biệt chữ hoa/chữ thường

Một số filesystem phân biệt `Config.json` và `config.json`, trong khi một số môi trường mặc định không phân biệt. Import hoặc đường dẫn sai chữ hoa có thể hoạt động cục bộ nhưng thất bại trên Linux runner.

Tên file, package, resource và đường dẫn trong mã nên nhất quán chính xác. Nếu dự án hỗ trợ nhiều hệ điều hành, chạy test trên ma trận phù hợp.

### 8.2. Dấu phân cách đường dẫn

Windows thường dùng dấu `\\`, trong khi Linux/macOS dùng `/`. Dùng API đường dẫn của ngôn ngữ thay vì nối chuỗi thủ công.

Ví dụ Java:

```java
Path report = Paths.get(outputDirectory, "reports", "result.json");
```

Không nên giả định thư mục gốc là một đường dẫn cố định trên máy phát triển. Dùng thư mục làm việc được cấu hình hoặc thư mục tạm do test framework cung cấp.

### 8.3. Quyền file và thực thi

Linux runner có thể yêu cầu bit executable cho script. Quyền đọc/ghi của user CI cũng có thể khác tài khoản cục bộ. Kiểm tra quyền cần thiết và không cấp quyền rộng hơn mức cần dùng.

### 8.4. Line ending và encoding

CRLF và LF, BOM hoặc charset mặc định có thể ảnh hưởng script, file fixture và dữ liệu. Cấu hình `.gitattributes`, encoding rõ ràng và cách đọc file nhất quán. Không dựa vào charset mặc định của máy.

### 8.5. Locale và timezone

Định dạng ngày, số thập phân, sắp xếp chuỗi và thông báo có thể thay đổi theo locale. Thời gian có thể khác do timezone của runner.

Test nên đặt locale/timezone rõ khi chúng không phải đối tượng kiểm tra. Nếu mục tiêu là xác minh đa ngôn ngữ hoặc múi giờ, hãy tạo ma trận test có chủ đích và ghi rõ giá trị.

## 9. Mạng và dịch vụ phụ thuộc

Runner CI thường chạy trong mạng có proxy, firewall, DNS, certificate store và chính sách egress riêng. Kết nối cục bộ thành công không bảo đảm CI truy cập được cùng endpoint.

### 9.1. Kiểm tra DNS, proxy và TLS

Khi request thất bại, xác định lỗi xảy ra ở bước phân giải tên, thiết lập kết nối, bắt tay TLS, xác thực hay xử lý response. Không ghi secret hoặc toàn bộ header nhạy cảm khi bật debug.

### 9.2. Đối chiếu endpoint và môi trường

Kiểm tra cục bộ và CI có gọi cùng loại endpoint không: local service, test environment, sandbox hay production. Dùng endpoint thử nghiệm theo chính sách và xác minh cấu hình trước khi chạy thao tác có tác dụng phụ.

### 9.3. Timeout, retry và quota

Runner chậm hơn có thể làm lộ timeout quá ngắn. Sandbox có thể giới hạn tốc độ hoặc số request. Hãy phân biệt timeout do ứng dụng, do runner, do mạng hay do nhà cung cấp.

Retry cần có giới hạn và chỉ áp dụng cho lỗi tạm thời phù hợp. Không retry mù quáng thao tác có tác dụng phụ như thanh toán hoặc gửi thông báo. Giữ kết quả lần đầu để chẩn đoán.

### 9.4. Không phụ thuộc dịch vụ công cộng không ổn định trong unit test

Unit test không nên cần internet để chạy. Dùng stub/fake cho logic; giữ contract/integration test với sandbox hoặc dịch vụ thật ở nhóm riêng, có retry và chính sách môi trường phù hợp.

## 10. Tài nguyên, song song và tính ổn định

CI có thể cấp ít tài nguyên hơn máy phát triển và thường chạy nhiều job cùng lúc.

### 10.1. CPU và bộ nhớ

Thiếu CPU hoặc RAM có thể làm test chậm, timeout, garbage collection tăng hoặc tiến trình bị hệ điều hành kết thúc. Ghi nhận tài nguyên runner và giới hạn heap. Tránh đặt timeout dựa trên máy cá nhân mạnh hơn runner.

### 10.2. Dung lượng đĩa và file tạm

Build cache, artifact và dữ liệu test có thể làm đầy đĩa trong job dài. Dùng thư mục tạm phù hợp, dọn file theo vòng đời và ghi nhận dung lượng khi có lỗi ghi file.

### 10.3. Mức song song

CI có thể chạy nhiều test class, worker hoặc job đồng thời. Điều này làm lộ:

- Trạng thái tĩnh hoặc singleton bị chia sẻ.
- Dữ liệu test dùng chung.
- Cổng mạng hoặc tên file bị trùng.
- Quota dịch vụ ngoài bị vượt.
- Tranh chấp khóa và transaction.

Khi điều tra, thử chạy tuần tự để xác định ảnh hưởng song song, sau đó tăng dần số worker. Chạy tuần tự đạt không chứng minh test an toàn khi chạy song song; cần kiểm tra riêng điều kiện concurrency nếu CI sử dụng nó.

### 10.4. Thời gian chờ và flaky test

Không giải quyết mọi lỗi CI bằng cách tăng timeout. Nếu test chờ một trạng thái bất đồng bộ, hãy chờ điều kiện có thể quan sát với thời hạn tối đa rõ ràng. Ghi lại bước cuối cùng, timestamp và trạng thái phụ thuộc khi timeout.

### 10.5. Cache và workspace tái sử dụng

Cache giúp tăng tốc nhưng có thể che dependency thiếu hoặc giữ artifact cũ. Workspace tái sử dụng có thể chứa file từ lần chạy trước. Cần xác định rõ:

- Cache nào được chia sẻ và theo khóa nào.
- Artifact nào được tái sử dụng.
- Bước nào cần clean.
- Dữ liệu nào phải tạo mới.
- Cách so sánh lần chạy cache và clean khi điều tra.

Không xóa toàn bộ cache ở mọi lần chạy nếu không cần thiết; điều đó làm pipeline chậm và có thể che vấn đề thiết kế cache. Hãy dùng cache key có liên quan đến lockfile, runtime hoặc cấu hình build.

## 11. Dùng container để tăng tính nhất quán

Container có thể đóng gói runtime, thư viện hệ thống và công cụ để giảm khác biệt giữa cục bộ và CI.

### 11.1. Lợi ích

- Dùng cùng image và dependency hệ thống.
- Chuẩn hóa đường dẫn và môi trường tiến trình trong container.
- Giảm phụ thuộc vào phần mềm cài sẵn trên máy host.
- Tái hiện runner dễ hơn nếu image và cấu hình được quản lý.

### 11.2. Container không làm môi trường giống hệt

Vẫn có khác biệt ở:

- Kernel và hệ điều hành host.
- Kiến trúc CPU và hỗ trợ instruction set.
- Network, DNS, proxy và certificate.
- CPU/RAM/disk limit.
- Volume mount và quyền file.
- Secret, biến môi trường và cấu hình runtime.
- Dịch vụ ngoài container.

Vì vậy, container giảm một số nguồn khác biệt nhưng không loại bỏ nhu cầu đối chiếu.

### 11.3. Cố định image và phiên bản

Dùng image có version rõ ràng; với môi trường cần tái lập cao, cân nhắc pin theo digest. Tránh dùng tag thay đổi liên tục như `latest` cho pipeline quan trọng nếu không có cơ chế kiểm soát cập nhật.

### 11.4. Dùng cùng cấu hình container cục bộ và CI

Nếu dự án cung cấp Dockerfile hoặc dev container, dùng cùng image và cách mount/cấu hình phù hợp khi tái hiện lỗi. Không đưa secret vào image hoặc layer build. Cấp secret lúc chạy qua cơ chế an toàn.

## 12. Quy trình tái hiện lỗi CI ở máy cục bộ

Khi test thất bại ở CI nhưng đạt cục bộ, cần tái hiện theo thứ tự để tránh thay đổi nhiều yếu tố cùng lúc.

### 12.1. Bảo toàn bằng chứng CI

Thu thập:

- Commit SHA và trạng thái checkout.
- Lệnh/task/profile và danh sách test thực thi.
- Runtime, build tool, OS và image.
- Cấu hình không nhạy cảm và tên biến bắt buộc.
- Mã định danh dữ liệu, migration và seed.
- Số worker, timeout, retry và thời gian chạy.
- Log test, log ứng dụng, trace, screenshot và artifact.
- Trạng thái phụ thuộc, quota và tài nguyên runner.

Không bắt đầu bằng việc chạy lại mà chưa lưu log của lần thất bại đầu tiên. Lần chạy sau có thể không tái hiện được trạng thái ban đầu.

### 12.2. Checkout đúng revision

Đảm bảo máy cục bộ đang kiểm tra đúng commit CI đã chạy. Tránh vô tình dùng thay đổi chưa commit hoặc dependency được resolve khác. Nếu working tree có thay đổi, ghi nhận chúng và tái hiện trên checkout sạch khi phù hợp.

### 12.3. Chạy đúng lệnh và bộ lọc

Chạy cùng task, profile, tag, system property và mức song song. Nếu CI chạy toàn suite, sau khi chạy test đơn lẻ hãy chạy nhóm và suite để tìm tương tác.

### 12.4. Mô phỏng điều kiện CI từng bước

Ưu tiên so sánh từng nhóm:

1. Dùng cùng JDK và build wrapper.
2. Dùng cùng dependency và lockfile.
3. Dùng cùng profile, biến môi trường và feature flag không nhạy cảm.
4. Dùng database/container và seed tương đương.
5. Cố định locale, timezone và encoding nếu có liên quan.
6. Chạy với cùng số worker và timeout.
7. Dùng container/image giống CI nếu có.
8. Kiểm tra mạng, sandbox và quota bằng endpoint thử nghiệm.

Thay đổi từng yếu tố giúp xác định khác biệt nào có liên quan. Nếu thay đồng thời JDK, database và số worker, kết quả có thể đạt nhưng không biết yếu tố nào đã khắc phục lỗi.

### 12.5. Tái hiện trên runner hoặc image tương đương

Nếu có thể, chạy cùng container hoặc runner image trong môi trường cục bộ. Nếu không thể tái hiện vì runner có quyền hoặc mạng đặc thù, tạo một job chẩn đoán trong CI với log bổ sung và phạm vi nhỏ. Không mở quyền hoặc in secret chỉ để chẩn đoán.

### 12.6. Xác nhận nguyên nhân và thêm kiểm soát

Sau khi tìm ra nguyên nhân:

- Sửa mã, test, cấu hình hoặc pipeline ở đúng nơi.
- Thêm test hồi quy cho điều kiện từng gây lỗi nếu phù hợp.
- Giữ lại log hoặc bằng chứng cần thiết.
- Chạy lại trên điều kiện đã gây lỗi và trên suite liên quan.
- Kiểm tra không làm yếu cổng chất lượng hoặc che lỗi bằng retry.

## 13. Phân loại lỗi theo nguồn gốc

Không phải mọi lỗi chỉ xuất hiện ở CI đều là lỗi CI. Cần phân loại dựa trên bằng chứng.

| Nhóm | Dấu hiệu thường gặp | Hướng điều tra |
|---|---|---|
| Lỗi sản phẩm | Kết quả nghiệp vụ sai, có thể tái hiện khi điều kiện kích hoạt xuất hiện | Kiểm tra logic, dữ liệu, trace và yêu cầu |
| Lỗi test | Assertion, setup, cleanup hoặc locator sai | Review mã test và oracle |
| Lỗi cấu hình | Profile, endpoint, feature flag hoặc biến bắt buộc khác | So sánh cấu hình và kiểm tra giá trị mặc định |
| Lỗi dữ liệu | Thiếu seed, dữ liệu trùng, migration hoặc trạng thái cũ | Tạo môi trường sạch và xác minh setup |
| Lỗi hạ tầng | Runner, mạng, DNS, disk, CPU hoặc dịch vụ không sẵn sàng | Kiểm tra trạng thái nền tảng và health check |
| Lỗi tương thích | Khác OS, runtime, charset, timezone hoặc filesystem | Tái hiện trên ma trận và chuẩn hóa API sử dụng |
| Flaky/race condition | Kết quả thay đổi theo thời điểm, thứ tự hoặc song song | Lưu attempt, seed, worker và timeline |
| Lỗi pipeline | Sai lệnh, bước bị bỏ qua, artifact thiếu hoặc thứ tự job sai | Kiểm tra cấu hình workflow và dependency giữa job |

Một lỗi có thể thuộc nhiều nhóm. Ví dụ, test thiếu cleanup là lỗi test và có thể tạo ra lỗi dữ liệu ở job kế tiếp. Ghi nhận nguyên nhân gốc và các yếu tố góp phần, tránh chỉ gắn nhãn chung “CI flaky”.

## 14. Thiết kế pipeline hỗ trợ đối chiếu

Pipeline nên tạo điều kiện tái lập và cung cấp đủ bằng chứng khi thất bại.

### 14.1. Khai báo môi trường tường minh

Khai báo phiên bản runtime, image, build tool, profile, biến bắt buộc, timezone và locale nếu chúng ảnh hưởng kết quả. Tránh phụ thuộc giá trị mặc định của runner.

### 14.2. Kiểm tra trước khi chạy test

Thực hiện preflight phù hợp:

- Xác nhận runtime và build tool đúng phiên bản.
- Kiểm tra biến cấu hình bắt buộc có tồn tại.
- Xác minh endpoint thử nghiệm và health check.
- Xác minh database đã migration và seed.
- Kiểm tra quyền thư mục và dung lượng cần thiết.
- Ghi nhận số worker và giới hạn tài nguyên.

Preflight nên thất bại với thông báo có thể hành động nếu điều kiện bắt buộc thiếu. Không in giá trị secret.

### 14.3. Giữ lệnh chạy nhất quán

Pipeline nên gọi wrapper hoặc script version-controlled của dự án. Các tham số khác nhau theo môi trường cần được khai báo có chủ đích và ghi nhận.

### 14.4. Lưu báo cáo và artifact

Tùy tầng kiểm thử, lưu:

- Báo cáo test có trạng thái từng test.
- Log build và log ứng dụng đã làm sạch.
- Trace, screenshot hoặc video khi cần.
- Mã commit, phiên bản image và runtime.
- Mã dataset/seed và migration version.
- Thời gian chạy, số lần retry và nguyên nhân retry.
- Kết quả preflight và trạng thái phụ thuộc.

Đặt thời hạn lưu và quyền truy cập phù hợp. Artifact có thể chứa dữ liệu nhạy cảm; cần lọc hoặc bảo vệ trước khi tải lên.

### 14.5. Không che thất bại bằng retry vô hạn

Retry có thể phù hợp với lỗi hạ tầng tạm thời được xác định. Pipeline phải giữ kết quả lần đầu, giới hạn số lần và phân loại trạng thái cuối. Không chuyển một test thất bại thành đạt sạch chỉ vì một lần chạy lại tình cờ thành công.

## 15. Ví dụ cấu hình pipeline có preflight và artifact

Đoạn YAML dưới đây là ví dụ khái niệm, không gắn với một nhà cung cấp CI cụ thể. Tên trường và cú pháp cần điều chỉnh theo nền tảng thực tế.

```yaml
test-job:
  image: project-test-image:21
  variables:
    TZ: UTC
    LANG: C.UTF-8
  steps:
    - name: Record build context
      run: ./ci/record-context.sh
    - name: Validate required configuration
      run: ./ci/preflight.sh
    - name: Run regression tests
      run: ./gradlew --no-daemon clean test
    - name: Publish test reports
      if: always()
      artifacts:
        paths:
          - build/reports/tests/
          - build/test-results/
```

Ví dụ nhấn mạnh ba điểm: môi trường được khai báo, preflight chạy trước test và báo cáo được lưu kể cả khi test thất bại. Trong cấu hình thật, cần bảo đảm image được pin theo chính sách, secret được cấp an toàn và artifact không chứa dữ liệu nhạy cảm.

### 15.1. Ví dụ preflight Java

Có thể ghi nhận phiên bản runtime mà không tiết lộ bí mật:

```bash
java -version
./gradlew --version
git rev-parse HEAD
```

Với thông tin môi trường, chỉ ghi các biến không nhạy cảm đã được phê duyệt. Không dùng `env`, `printenv` hoặc lệnh dump toàn bộ cấu hình trong job có secret.

### 15.2. Lưu trạng thái phụ thuộc

Preflight có thể kiểm tra health endpoint, truy vấn phiên bản database hoặc xác minh migration state. Nên lưu kết quả ngắn gọn như “database ready”, phiên bản schema và endpoint alias, thay vì log toàn bộ response chứa dữ liệu nhạy cảm.

## 16. Ví dụ điều tra: test chỉ thất bại trên Linux runner

Giả sử test đọc fixture `TestData/Customer.json` đạt trên máy Windows nhưng thất bại ở CI Linux với lỗi không tìm thấy file.

### 16.1. Thu thập bằng chứng

- Cùng commit và cùng test class.
- Máy cục bộ dùng Windows; runner dùng Linux.
- Fixture trong repository có tên `testdata/customer.json`.
- Test tham chiếu `TestData/Customer.json`.

### 16.2. Xác định khác biệt có ý nghĩa

Filesystem trên môi trường cục bộ có thể không phân biệt chữ hoa/chữ thường, còn filesystem Linux thông thường phân biệt. Vì vậy, đường dẫn sai vẫn hoạt động trên máy Windows nhưng không tìm thấy file ở CI.

### 16.3. Sửa và xác minh

Sửa đường dẫn trong test hoặc đổi tên resource để thống nhất chính xác. Chạy lại trên Windows và Linux. Nếu dự án hỗ trợ cả hai hệ điều hành, giữ test trong ma trận CI để ngăn lỗi quay lại.

Ví dụ khác: test chỉ thất bại khi chạy song song có thể do hai worker ghi cùng một file tạm. Cách xử lý là tạo thư mục riêng theo test/run, không phải chỉ giảm số worker mãi mãi.

## 17. Duy trì mức tương đồng phù hợp

Môi trường cục bộ và CI không cần giống nhau ở mọi thuộc tính. Cần quyết định yếu tố nào phải thống nhất, yếu tố nào cần kiểm tra đa dạng và yếu tố nào được phép khác.

### 17.1. Thống nhất các yếu tố ảnh hưởng đến kết quả

Thường nên chuẩn hóa:

- Phiên bản runtime và build tool.
- Dependency và cách resolve.
- Lệnh, task, profile và tham số test.
- Encoding và cấu hình locale/timezone khi không phải mục tiêu kiểm tra.
- Migration và cách tạo dữ liệu.
- Cấu hình dịch vụ phụ thuộc cần thiết.
- Quy tắc timeout, retry và cách thu thập kết quả.

### 17.2. Kiểm tra đa dạng có chủ đích

Một số yếu tố cần được kiểm tra trên nhiều cấu hình:

- Hệ điều hành và kiến trúc CPU được hỗ trợ.
- Phiên bản runtime được hỗ trợ.
- Locale và timezone thuộc phạm vi sản phẩm.
- Browser, thiết bị hoặc độ phân giải.
- Mức song song và tải.
- Phiên bản database hoặc broker trong ma trận tương thích.

Đưa các biến thể này vào ma trận CI rõ ràng. Không nên vô tình thay đổi môi trường giữa các lần chạy mà không ghi nhận.

### 17.3. Tạo môi trường phát triển có thể tái lập

Các lựa chọn gồm dev container, Docker Compose, script bootstrap, wrapper build và tài liệu setup. Mục tiêu là giúp lập trình viên tạo môi trường đủ gần với CI mà không cần sao chép toàn bộ hạ tầng sản xuất.

Mọi công cụ bootstrap cần kiểm tra phiên bản, xử lý lỗi rõ và không tự tải hoặc thực thi script không đáng tin cậy. Secret phải được cấp riêng qua cơ chế an toàn.

### 17.4. Rà soát khi pipeline thay đổi

Khi thay runner image, JDK, build plugin, mức song song hoặc cache strategy, cần xem đó là thay đổi môi trường có thể ảnh hưởng kết quả test. Chạy tập kiểm tra đại diện, so sánh báo cáo và cập nhật tài liệu.

## 18. Những sai lầm thường gặp

### 18.1. Cho rằng CI luôn sai khi cục bộ đạt

CI có thể đang phát hiện lỗi thực do môi trường sạch, quyền chặt hơn hoặc chạy song song. Hãy tái hiện và phân loại trước khi bỏ qua kết quả.

### 18.2. Chỉ chạy test thất bại riêng lẻ

Test riêng lẻ có thể đạt vì không còn tương tác với test khác. Cần chạy nhóm và suite với mức song song tương đương CI.

### 18.3. Dùng cache hoặc dữ liệu cục bộ mà không nhận biết

Cache và trạng thái cũ có thể che thiếu bước setup. Kiểm tra trên checkout sạch và môi trường dữ liệu mới.

### 18.4. In toàn bộ biến môi trường để chẩn đoán

Log có thể làm lộ token, mật khẩu hoặc dữ liệu cá nhân. Chỉ ghi tên biến, trạng thái tồn tại và giá trị không nhạy cảm đã được phê duyệt.

### 18.5. Tăng timeout để che nguyên nhân

Timeout dài hơn có thể làm pipeline chậm mà không sửa race condition, deadlock hoặc service không sẵn sàng. Chờ điều kiện quan sát được và xác định giới hạn hợp lý.

### 18.6. Cố làm môi trường giống hệt mà bỏ qua ma trận tương thích

Nếu sản phẩm cần chạy trên nhiều hệ điều hành hoặc runtime, chỉ dùng một image duy nhất có thể bỏ sót lỗi tương thích. Chuẩn hóa phần cần ổn định và kiểm tra biến thể theo ma trận.

### 18.7. Retry cho đến khi đạt

Retry không giới hạn che mất lần thất bại đầu tiên và có thể bỏ sót lỗi hiếm. Giữ lịch sử từng attempt và giới hạn retry theo loại lỗi.

### 18.8. Không ghi nhận phần chưa kiểm tra

Nếu CI bỏ qua integration test do sandbox không sẵn sàng, báo cáo phải ghi rõ trạng thái blocked và rủi ro còn lại. Không báo cáo toàn bộ suite đạt khi một phần chưa chạy.

## 19. Danh sách rà soát khi đối chiếu cục bộ và CI

Khi một test có kết quả khác nhau, hãy kiểm tra:

- [ ] Cùng commit và trạng thái mã nguồn sạch.
- [ ] Cùng lệnh, task, profile và phạm vi test.
- [ ] Cùng phiên bản runtime, build tool và dependency.
- [ ] Hệ điều hành, kiến trúc và filesystem được ghi nhận.
- [ ] Cấu hình và feature flag liên quan được so sánh mà không lộ secret.
- [ ] Locale, timezone, encoding và clock được kiểm soát khi cần.
- [ ] Database, schema, migration, seed và trạng thái dữ liệu tương đương.
- [ ] Endpoint, credential scope, network, DNS, TLS và quota được xác minh.
- [ ] Quyền file, thư mục làm việc và tài nguyên runner được xem xét.
- [ ] Số worker, mức song song, timeout và retry được đối chiếu.
- [ ] Cache và workspace cũ không che bước setup thiếu.
- [ ] Log, trace, báo cáo và artifact của lần thất bại đầu tiên được lưu.
- [ ] Lỗi được phân loại theo sản phẩm, test, cấu hình, dữ liệu, hạ tầng hoặc pipeline.
- [ ] Nguyên nhân đã xác minh được sửa và có test hồi quy phù hợp.
- [ ] Các khác biệt có chủ đích được ghi trong ma trận môi trường.

## 20. Kết luận

Đối chiếu điều kiện chạy cục bộ với CI giúp nhóm hiểu vì sao cùng một thay đổi có thể tạo kết quả khác nhau và làm cho kiểm thử có thể tái lập. Cần so sánh revision, lệnh chạy, runtime, dependency, cấu hình, dữ liệu, hệ điều hành, thời gian, quyền, mạng, tài nguyên và mức song song theo mục tiêu test.

Khi CI thất bại, hãy bảo toàn bằng chứng lần đầu, tái hiện đúng revision và thay đổi từng yếu tố có kiểm soát. Chuẩn hóa những điều kiện cần ổn định; dùng ma trận để kiểm tra những khác biệt là yêu cầu tương thích; và giữ cấu hình, dữ liệu cùng secret trong cơ chế quản lý phù hợp. Một pipeline tốt không chỉ chạy test mà còn ghi lại đủ ngữ cảnh để người phát triển hiểu kết quả, xác định nguyên nhân và sửa lỗi mà không che giấu tín hiệu chất lượng.
