# Tự động hóa xây dựng, kiểm thử và kiểm tra chất lượng

Một nhóm phát triển có thể viết xong mã nguồn cho user story “Học viên đăng ký workshop” chỉ trong hai ngày nhưng sau đó chờ nhiều ngày để người khác build, kiểm thử, review và tìm ra lỗi phân quyền. Khi mỗi thay đổi nhỏ đều phải qua nhiều bước thủ công, chi phí nhận phản hồi tăng; nhóm dễ gom nhiều thay đổi thành một đợt lớn và phát hiện vấn đề quá muộn.

**Tự động hóa xây dựng, kiểm thử và kiểm tra chất lượng** tạo ra một chuỗi kiểm chứng có thể lặp lại để nhóm biết sớm mã nguồn có biên dịch được, hành vi đã kiểm tra có còn đúng và thay đổi có vi phạm những tiêu chuẩn cần thiết hay không. Kết hợp với **Continuous Integration (CI)**, đây là nền tảng kỹ thuật giúp Agile giao sản phẩm tăng dần, nhận phản hồi sớm và cải tiến liên tục.

Tuy nhiên, **pipeline xanh không có nghĩa sản phẩm chắc chắn an toàn hoặc có giá trị**: công cụ chỉ kiểm tra những điều đã được cấu hình, còn nhu cầu người dùng, thiết kế, rủi ro chưa biết và điều kiện vận hành vẫn cần con người đánh giá. Bài học thuộc chương **Thực hành kỹ thuật** của module **AGILE_DEVELOPMENT** và liên hệ trực tiếp với user story, backlog, Scrum, Kanban và các thực hành XP như TDD, CI và refactoring.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Phân biệt **build automation, test automation, static analysis, quality gate, CI và CD**.
2. Giải thích lý do phản hồi kỹ thuật sớm giúp giảm làm lại và hỗ trợ giao Increment nhỏ.
3. Thiết kế quy trình build có đầu vào, công cụ, dependency và artifact có thể truy vết.
4. Chọn tầng kiểm thử phù hợp với logic, tích hợp, dữ liệu, bảo mật và hành trình người dùng.
5. Đọc pipeline minh họa Java/Gradle, biết check nào thực sự chạy và check nào cần cấu hình riêng.
6. Xử lý tình huống build đỏ, test flaky, phát hiện lỗ hổng hoặc secret bị lộ.
7. Đề xuất quality gate dựa trên rủi ro, không dùng coverage làm chứng nhận chất lượng tuyệt đối.
8. Xây thử nghiệm cải tiến tốc độ và độ tin cậy của pipeline, kết hợp bằng chứng từ sản phẩm thật.

## 2. Tự động hóa giải quyết vấn đề nào của nhóm Agile?

Phần mềm thường được thay đổi liên tục: sửa lỗi, bổ sung quy tắc, cải thiện giao diện, nâng dependency và tích hợp nhà cung cấp. Nếu kết quả một thay đổi chỉ được kiểm chứng cuối Sprint, mọi việc xây sau đó có thể đang dựa trên giả định sai.

Tự động hóa giúp:

- **Phát hiện lỗi sớm:** Một test phân quyền báo thất bại ngay khi thay đổi có liên quan.
- **Giảm thao tác lặp:** Cùng một quy trình biên dịch và kiểm tra được thực hiện nhất quán.
- **Giữ nhịp tích hợp:** Developers sớm biết thay đổi có xung đột với mã chung hay không.
- **Làm rõ trạng thái hoàn tất:** Một PBI chưa qua kiểm chứng bắt buộc không bị gọi là Done chỉ vì đã merge mã.
- **Giảm thời gian chờ:** Không cần đợi ai nhớ chạy lệnh đóng gói hoặc gửi kết quả bằng tay.
- **Tạo bằng chứng để quyết định:** Product Owner và Developers biết Increment đang có những giới hạn nào.
- **Tăng khả năng thay đổi:** Khi test đáng tin, nhóm có thể refactor và phản ứng với nhu cầu mới an toàn hơn.

### 2.1. Phản hồi muộn làm tăng phạm vi điều tra

Giả sử một thay đổi ở chức năng giữ chỗ gây lỗi đăng ký trùng.

| Lúc phát hiện | Công việc có thể phát sinh |
| --- | --- |
| Trong unit test cục bộ | Sửa quy tắc gần vị trí vừa thay đổi |
| Trong CI của pull request | Xác định commit, phối hợp reviewer, sửa và chạy lại |
| Trong kiểm thử tích hợp cuối Sprint | Điều tra nhiều thay đổi, sửa phụ thuộc và kiểm tra hồi quy |
| Sau phát hành | Khắc phục dữ liệu, hỗ trợ người dùng, điều tra sự cố, cập nhật hệ thống |

Bảng mô tả **xu hướng thường gặp**, không phải quy luật chi phí cố định. Giá trị chính của phản hồi sớm là **giảm lượng công việc đã được xây dựa trên lỗi chưa phát hiện**.

## 3. Phân biệt các hoạt động kiểm chứng

| Hoạt động | Câu hỏi chính | Đầu ra thường gặp | Giới hạn |
| --- | --- | --- | --- |
| **Build automation** | Có thể biên dịch/đóng gói từ đầu vào đã định không? | JAR, image, bundle, build log | Không chứng minh nghiệp vụ đúng |
| **Automated testing** | Những hành vi đã mô tả còn đúng không? | Kết quả pass/fail và test report | Chỉ bao phủ trường hợp đã kiểm tra |
| **Static analysis** | Mã và cấu hình có mẫu lỗi/rủi ro theo quy tắc không? | Phát hiện từ linter hoặc analyzer | Có false positive và giới hạn nhận biết |
| **Formatting** | Mã có tuân quy ước trình bày không? | Kết quả format/lint | Không đánh giá giá trị hoặc thiết kế tổng thể |
| **Security/dependency checks** | Có dấu hiệu lỗ hổng, secret hoặc phụ thuộc rủi ro không? | Danh sách phát hiện và mức nghiêm trọng | Không chứng nhận không còn lỗ hổng |
| **CI** | Thay đổi có được tích hợp thường xuyên và kiểm chứng sớm? | Trạng thái check gắn với commit | Không tự động phát hành production |
| **Quality gate** | Có đủ điều kiện để merge, tạo artifact hoặc phát hành? | Pass/fail theo chính sách | Không thay thế phán đoán chuyên môn |
| **Continuous Delivery/Deployment** | Artifact đủ điều kiện có thể được giao/triển khai thế nào? | Release candidate hoặc deployment | Không miễn trừ phê duyệt, bảo mật, vận hành |

**Không nên nói “có CI” chỉ vì một máy chủ chạy lệnh build mỗi đêm.** CI còn bao gồm thói quen tích hợp thay đổi nhỏ, xem kết quả sớm và phản ứng khi nhánh chung có lỗi.

### 3.1. Luồng phản hồi cơ bản

~~~mermaid
flowchart LR
    A["User story và thay đổi nhỏ"] --> B["Kiểm tra cục bộ"]
    B --> C["Commit / pull request"]
    C --> D["Build + test + static checks"]
    D --> E{"Đạt điều kiện cần thiết?"}
    E -->|"Chưa"| F["Làm rõ lỗi, sửa và chạy lại"]
    F --> B
    E -->|"Có"| G["Tích hợp vào nhánh chung"]
    G --> H["Kiểm chứng rộng hơn và artifact"]
    H --> I["Increment đủ chất lượng"]
    I --> J["Phản hồi từ người dùng, vận hành"]
    J --> A
~~~

Sơ đồ chỉ là một **mô hình minh họa**. Một nhóm có thể chạy kiểm thử tích hợp ngay trước merge, trên nhánh chung hoặc trong môi trường tiền sản xuất tùy rủi ro. Quan trọng là biết **bước nào bảo vệ quyết định nào**, không phải sao chép một sơ đồ công cụ.

## 4. Build automation: cùng đầu vào, kết quả có thể truy vết

Build tốt không phụ thuộc vào câu “trên máy tôi vẫn chạy được”. Nhóm cần kiểm soát các đầu vào:

1. **Mã nguồn:** Commit/tag cụ thể, không phụ thuộc file chưa được lưu vào quản lý phiên bản.
2. **Toolchain:** Phiên bản JDK, Gradle/Maven, compiler và plugin tương thích.
3. **Dependency:** Thư viện và nơi tải, quy tắc cập nhật hoặc khóa phiên bản.
4. **Cấu hình build:** Các tham số có ảnh hưởng phải được nhận biết; secret không lưu trong repo.
5. **Môi trường:** Hệ điều hành, kiến trúc, timezone, locale nếu có ảnh hưởng tới kết quả.
6. **Artifact:** Tên, phiên bản, hash hoặc định danh giúp truy vết về mã và quy trình tạo ra nó.

**Có thể lặp lại** không nhất thiết là **bit-for-bit giống nhau** trong mọi dự án: timestamp hoặc metadata môi trường có thể làm artifact khác byte. Nếu yêu cầu reproducible build ở mức byte, phải kiểm soát những nguồn biến động đó.

### 4.1. Ví dụ lệnh Gradle cho dự án Java

~~~bash
# Build sạch bằng Gradle Wrapper nếu dự án đã cấu hình.
./gradlew --no-daemon clean build

# Chạy task kiểm thử đơn vị đã đăng ký trong task graph.
./gradlew --no-daemon test

# Chạy các tác vụ kiểm tra nối vào vòng đời check.
./gradlew --no-daemon check
~~~

Trong dự án dùng Gradle Java plugin thông thường, **build** thường phụ thuộc vào **assemble** và **check**; **check** phụ thuộc vào **test**. Các suite kiểm thử hoặc plugin phân tích bổ sung **chỉ chạy khi được cấu hình và nối task phù hợp**. Vì vậy, không nên chạy cả ba lệnh trên liên tục như ba tầng độc lập mà không hiểu task graph.

Đây là **ví dụ trong tài liệu**, không có nghĩa repository cụ thể đã sẵn wrapper, plugin hoặc JDK tương ứng. Trên Windows, có thể dùng tệp **gradlew.bat** theo cấu hình dự án.

### 4.2. Quản lý dependency để build đáng tin

- Ghim hoặc kiểm soát phiên bản plugin và thư viện theo chính sách tổ chức.
- Tránh dependency động không kiểm soát trên đường build quan trọng.
- Dùng repository đáng tin, xác minh tính toàn vẹn khi cần.
- Đánh giá quy tắc dependency locking/verification khi stack hỗ trợ.
- Kiểm tra script tải từ bên ngoài trước khi thực thi.
- Không lưu credential trong mã nguồn, build log hoặc artifact.
- Hiểu rằng cache cải thiện tốc độ nhưng không thay thế việc kiểm tra nguồn.

### 4.3. Khả năng chẩn đoán cũng là chất lượng build

Khi CI đỏ, Developers cần biết:

- Build của commit nào và môi trường nào?
- Lỗi từ compiler, dependency, test, tool hay hạ tầng?
- Báo cáo và log nào chỉ ra nguyên nhân đầu tiên?
- Có thể tái hiện trong môi trường kiểm chứng tương đương không?
- Ai sẽ sửa hoặc đưa nhánh chung trở lại trạng thái tin cậy?

Pipeline chỉ hiện biểu tượng đỏ mà không có ngữ cảnh sẽ **làm tăng thời gian chờ và giảm giá trị phản hồi**.

## 5. Kiểm thử tự động: không phải mọi test có cùng mục đích

| Loại test | Rủi ro cần kiểm tra | Ví dụ workshop | Lưu ý |
| --- | --- | --- | --- |
| **Unit test** | Quy tắc trong một đơn vị mã | Học viên đủ điều kiện tham gia? | Nhanh nhưng có thể mock dependency thật |
| **Component/service test** | Hành vi của một thành phần | Service trả kết quả đăng ký đúng? | Cần fixture phù hợp |
| **Integration test** | Tương tác giữa các thành phần thật | Hai yêu cầu đồng thời có vượt sức chứa? | Cần kho dữ liệu và kiểm soát môi trường |
| **Contract test** | Hai bên cùng hiểu giao diện API | Dịch vụ thông báo nhận payload đúng? | Không thay end-to-end của toàn luồng |
| **End-to-end test** | Một hành trình người dùng qua nhiều tầng | Đăng nhập, đăng ký, xem trạng thái | Chậm hơn, nhạy với giao diện/môi trường |
| **Performance/load test** | Thời gian đáp ứng và năng lực khi có tải | Nhiều lượt đăng ký trong giờ mở lớp | Cần workload đại diện |
| **Security test** | Truy cập sai, cấu hình nguy hiểm, dữ liệu lộ | B không xem được đăng ký của A | Không có test nào bao phủ mọi tấn công |
| **Accessibility test** | Khả năng sử dụng với nhu cầu tiếp cận khác nhau | Nút đăng ký dùng được bằng bàn phím | Cần bổ sung đánh giá thủ công |
| **Smoke test** | Bản triển khai còn thực hiện được các hành vi cơ bản? | API trạng thái workshop còn phản hồi | Không thay hồi quy đầy đủ |

### 5.1. Chiến lược kiểm thử theo rủi ro

Đừng bắt đầu bằng câu “phải có bao nhiêu test?”. Hãy xác định:

1. Hành vi nào có tác động lớn nhất nếu sai?
2. Lỗi có thể xuất hiện trong logic, giao dịch dữ liệu, phân quyền, tích hợp hay trải nghiệm?
3. Tầng kiểm thử nào cho tín hiệu **sớm, đúng và đủ tin cậy**?
4. Những kịch bản nào cần môi trường gần thực tế hoặc chuyên gia thẩm định?
5. Phần nào chưa thể tự động hóa và cần chính sách kiểm chứng bổ sung?

Đối với tính năng đăng ký chỗ cuối, **unit test với mock repository không đủ để chứng minh giao dịch an toàn khi hai yêu cầu đồng thời**. Nhóm cần kiểm thử trên cơ chế lưu trữ/giao dịch phù hợp, đồng thời xem xét thiết kế và các ràng buộc dữ liệu.

## 6. Ví dụ acceptance test cho user story đăng ký workshop

**User story:** Là học viên đủ điều kiện, tôi muốn đăng ký workshop còn chỗ để nhận xác nhận đáng tin cậy.

~~~gherkin
Feature: Dang ky workshop

  Scenario: Dang ky thanh cong khi con cho
    Given workshop W con mot cho
    And hoc vien A du dieu kien
    When A dang ky workshop W
    Then dang ky cua A duoc xac nhan
    And so cho da xac nhan khong vuot suc chua

  Scenario: Hai yeu cau tranh cho cuoi
    Given W con dung mot cho
    And A va B deu du dieu kien
    When A va B gui yeu cau gan nhu dong thoi
    Then he thong xac nhan khong qua mot dang ky moi
    And moi yeu cau co ket qua ro rang

  Scenario: Bao ve du lieu dang ky
    Given A co dang ky tai workshop W
    When B yeu cau xem dang ky cua A
    Then he thong tu choi truy cap khong hop le
~~~

Những tình huống Gherkin này **chưa phải test tự chạy** nếu thiếu step definition, fixture, kết nối hệ thống và cách kích hoạt trong CI. Cần làm rõ ai chịu trách nhiệm kiểm chứng mỗi kịch bản và dữ liệu thử.

### 6.1. Ghép tình huống với tầng test

| Điều cần xác minh | Kiểm tra nhanh | Kiểm tra hệ thống |
| --- | --- | --- |
| Điều kiện được đăng ký | Unit test của policy | API với danh tính thật trong môi trường thử |
| Không cho đăng ký trùng | Logic kiểm tra tuần tự | Ràng buộc duy nhất ở kho dữ liệu và transaction |
| Không vượt sức chứa | Quy tắc sức chứa | Test các yêu cầu song song trên cơ chế lưu trữ thật |
| Phân quyền xem đăng ký | Unit test policy | Hai tài khoản thật gọi endpoint |
| Thông báo trạng thái | Mapping và mẫu thông điệp | Kiểm thử hành trình/khả năng tiếp cận |

**Kiểm thử concurrency phải thực sự tạo tình huống gần đồng thời**, không chỉ chạy hai bước tuần tự. Ngay cả khi test đa luồng pass nhiều lần, nó vẫn chỉ là bằng chứng trong điều kiện đã thử; nhóm còn cần phân tích cơ chế nhất quán dữ liệu và quan sát sau phát hành.

## 7. TDD và chu kỳ Red – Green – Refactor

**Test-Driven Development (TDD)** thường được mô tả bằng ba bước:

1. **Red:** Viết một test thể hiện hành vi mong đợi và thấy nó thất bại đúng lý do.
2. **Green:** Viết lượng mã vừa đủ để đáp ứng hành vi.
3. **Refactor:** Cải thiện thiết kế trong khi các test vẫn xác nhận hành vi không bị phá.

TDD giúp phản hồi nhanh và tạo điều kiện an toàn hơn để thay đổi mã. Nó cũng thúc đẩy các giá trị XP: **giao tiếp qua ví dụ, đơn giản trong thiết kế, phản hồi sớm, can đảm sửa và tôn trọng người bảo trì**.

### 7.1. Những giới hạn cần nhớ

- Test xanh không chứng minh mọi yêu cầu đã được hiểu đúng.
- Unit test không thay thế integration test cho database hoặc API thật.
- Mock quá mức có thể kiểm tra cách triển khai giả chứ không kiểm tra hành vi quan trọng.
- Không viết test chỉ để nâng coverage mà không có assert có ý nghĩa.
- Sửa test khi yêu cầu thật đổi là hợp lý; sửa test để che bug thì không.

## 8. Làm cho bộ kiểm thử đáng tin

| Thuộc tính | Lý do | Ví dụ thực hành |
| --- | --- | --- |
| **Kỳ vọng rõ** | Khi fail biết quy tắc nào bị phá | Tên test mô tả hành vi và trạng thái mong đợi |
| **Độc lập** | Tránh phụ thuộc thứ tự chạy | Dữ liệu test riêng, cleanup hoặc transaction đúng |
| **Xác định khi có thể** | Giảm kết quả ngẫu nhiên | Kiểm soát thời gian, random seed và môi trường |
| **Nhanh ở tầng phù hợp** | Cho phép chạy thường xuyên | Unit test không khởi động toàn bộ ứng dụng vô cớ |
| **Gần thực tế khi cần** | Bắt lỗi giao tiếp giữa dependency | Integration test với database tương ứng |
| **Chẩn đoán được** | Giảm thời gian tìm lỗi | Báo cáo expected/actual, log đủ ngữ cảnh |
| **Không rò rỉ dữ liệu** | Tránh tiết lộ thông tin nhạy cảm qua log/test | Dùng dữ liệu tổng hợp, che secret |
| **Có người bảo trì** | Tránh để test lỗi thời | Cập nhật fixture và ngưỡng theo thay đổi thực |

### 8.1. Test bất đồng bộ cần chờ theo điều kiện

~~~text
Cach yeu:
  Gui yeu cau xu ly bat dong bo
  Sleep co dinh 5 giay
  Assert ket qua

Cach phu hop hon:
  Gui yeu cau
  Cho theo dieu kien quan sat duoc voi timeout ro rang
  Neu het han, bao trang thai va thong tin chan doan
~~~

Sleep cố định dễ tạo flaky khi runner nhanh/chậm khác nhau. **Polling theo điều kiện với timeout hợp lý** thường đáng tin hơn, nhưng cũng cần giới hạn tần suất để không tạo tải hoặc che hệ thống quá chậm.

## 9. Flaky test: khi tín hiệu không còn đáng tin

Một **flaky test** có thể lúc pass lúc fail khi đầu vào và kỳ vọng không đổi. Nguyên nhân thường gồm:

- Đồng bộ bất đồng bộ sai, race condition trong test hoặc code.
- Dữ liệu dùng chung giữa test, chạy song song không cách ly.
- Network, service ngoài hoặc môi trường CI không ổn định.
- Lệ thuộc giờ thực, timezone, locale, random hoặc thứ tự chạy.
- Resource bị giới hạn làm timeout.
- Fixture khởi tạo/cleanup không nhất quán.

### 9.1. Tại sao không chỉ retry cho xanh?

Chạy lại có thể cung cấp thêm thông tin, nhưng **lấy kết quả pass sau retry để giấu lần fail đầu** sẽ làm nhóm mất lòng tin vào pipeline. Đặc biệt, test bị chập chờn có thể đang phát hiện lỗi đồng thời thật.

Một chính sách thực dụng:

1. Ghi nhận test, tần suất fail, thời điểm và log đủ ngữ cảnh.
2. Phân loại rủi ro: lỗi sản phẩm, test hay hạ tầng?
3. Giao người chịu trách nhiệm và mục tiêu xử lý.
4. Nếu phải cách ly tạm, ghi rõ mất loại bằng chứng nào và cách kiểm chứng thay thế.
5. Định thời điểm đưa test trở lại đường kiểm chứng chính.
6. Xem lại tỷ lệ flaky sau sửa; không chỉ kiểm tra một lần chạy xanh.

**Không xóa test bảo mật hoặc tính đúng đắn dữ liệu chỉ vì nó khiến báo cáo xấu.**

## 10. Static analysis và kiểm tra chất lượng mã

Không phải mọi vấn đề đều cần chạy ứng dụng mới phát hiện được. Phân tích tĩnh và các rule kiểm tra có thể tìm:

- Cú pháp, kiểu dữ liệu hoặc tình huống null có nguy cơ lỗi.
- Biến không dùng, nhánh khó hiểu, code smell.
- Vi phạm coding convention hoặc kiến trúc lớp/module.
- Mẫu sử dụng API không an toàn.
- Cấu hình hoặc hạ tầng dạng mã có sai lệch theo chính sách.
- Chỗ xuất hiện token, khóa truy cập hoặc thông tin không nên commit.

### 10.1. Ví dụ nhóm công cụ trong dự án Java

| Kiểm tra | Công cụ minh họa | Giá trị và giới hạn |
| --- | --- | --- |
| **Formatting** | Formatter phù hợp Java/Gradle | Giảm tranh luận trình bày, không đảm bảo thiết kế |
| **Style/lint** | Checkstyle | Thực thi quy ước, phụ thuộc rule set |
| **Static bugs** | PMD, SpotBugs | Phát hiện một số mẫu lỗi, có thể có false positive |
| **Architecture** | Test phụ thuộc module/lớp | Giữ ranh giới có chủ đích, cần chính sách rõ |
| **SAST** | Scanner bảo mật phù hợp stack | Tìm một số mẫu lỗ hổng, không bao phủ mọi tấn công |
| **Secret scanning** | Scanner hỗ trợ Git/CI | Phát hiện credential lộ, không thay quản lý secret |

Các tên trên là **ví dụ công cụ**, không phải yêu cầu cài tất cả. Plugin hoặc task mới không tự chạy trong Gradle cho tới khi được cấu hình và nối vào vòng kiểm chứng.

### 10.2. Xử lý cảnh báo theo rủi ro

Một cảnh báo có thể là **true positive**, **false positive** hoặc tình huống **cần điều tra thêm**. Không nên dọn mọi warning bằng cách tắt rule. Nếu một ngoại lệ được chấp nhận, nên có:

1. Lý do và bằng chứng.
2. Phạm vi áp dụng nhỏ nhất.
3. Người có thẩm quyền chấp nhận.
4. Thời điểm xem lại.
5. Biện pháp giảm rủi ro nếu cần.

## 11. Security checks và supply chain trong pipeline

Một bản build có thể chứa mã nghiệp vụ đúng nhưng vẫn có rủi ro do dependency, cấu hình hoặc pipeline được cấp quyền quá rộng.

### 11.1. Những lớp kiểm soát có thể bổ sung

- **Software Composition Analysis (SCA):** Kiểm tra dependency và lỗ hổng đã biết.
- **SAST:** Phân tích mẫu code nguy hiểm.
- **Secret scanning:** Phát hiện credential bị đưa vào repository.
- **Container scanning:** Nếu dùng image, kiểm tra base image và package.
- **Cấu hình/IaC scanning:** Phát hiện chính sách mạng hoặc quyền không phù hợp.
- **Dependency licensing:** Kiểm tra ràng buộc giấy phép khi cần.
- **Kiểm thử bảo mật theo hành vi:** Phân quyền, injection, dữ liệu, các lỗi logic quan trọng.
- **Đánh giá chuyên môn:** Xử lý những rủi ro mà scanner không thể hiểu hết.

### 11.2. CVE không phải một con số để xử lý máy móc

Khi scanner phát hiện CVE, nhóm cần hỏi:

1. Phiên bản đang dùng có thực sự bị ảnh hưởng?
2. Ứng dụng có sử dụng đường code có thể bị khai thác?
3. Có bản vá hoặc biện pháp giảm thiểu an toàn?
4. Artifact nào đang được phát hành và ai bị ảnh hưởng?
5. Ai có thẩm quyền quyết định rủi ro tồn dư?
6. Khi nào kiểm tra lại nếu chưa thể sửa ngay?

Không nên bỏ qua cảnh báo chỉ vì “chưa từng bị tấn công”, nhưng cũng không nên chặn vô hạn mọi thay đổi mà không đánh giá phạm vi áp dụng.

### 11.3. Bảo vệ chính CI

- Cấp **quyền tối thiểu** cho token CI.
- Không truyền secret production vào job chạy mã PR không tin cậy từ bên ngoài.
- Tách job kiểm chứng PR khỏi job deploy có quyền nhạy cảm.
- Kiểm soát phiên bản action/plugin; hệ thống quan trọng có thể pin theo commit SHA đã xác minh.
- Không in secret, dữ liệu thật hoặc token trong test report.
- Bảo vệ nhánh và môi trường phát hành phù hợp rủi ro.
- Truy vết artifact và nguồn gốc dependency.

**Một pipeline có quét bảo mật nhưng làm lộ credential triển khai vẫn là một pipeline thiếu an toàn.**

## 12. Quality gate: điều kiện để được đi tiếp

**Quality gate** là bộ điều kiện cần đạt trước một hành động như merge, tạo artifact hoặc phát hành.

| Điều kiện ở PR | Bằng chứng | Phản ứng nếu không đạt |
| --- | --- | --- |
| Build thành công | Compiler và task build | Sửa mã hoặc điều tra hạ tầng |
| Bộ test bắt buộc đạt | Báo cáo pass/fail | Không merge khi chưa xử lý theo chính sách |
| Formatting/static checks phù hợp đạt | Báo cáo tool | Sửa hoặc xét ngoại lệ có lý do |
| Không lộ credential | Secret scanner | Xử lý secret, thu hồi nếu đã bị lộ |
| Phát hiện bảo mật mức không chấp nhận được đã được xử lý | Kết quả phân tích/risk acceptance | Sửa hoặc xin quyết định đúng thẩm quyền |
| Review có người đủ thẩm quyền/kỹ năng | Xác nhận review | Bổ sung xem xét kỹ thuật hoặc nghiệp vụ |
| Hạng mục dữ liệu có kiểm chứng phù hợp | Test/plan migration | Bổ sung bằng chứng, rollback khi cần |

Không phải mọi kiểm tra nặng đều cần chạy trong từng PR. Một dự án có thể có gate **PR**, gate **artifact** và gate **release** với phạm vi khác nhau. Chính sách phải nói rõ **mốc nào cần bằng chứng nào**.

### 12.1. Không biến coverage thành chứng chỉ chất lượng

Một module có 95% line coverage vẫn có thể thiếu assert quan trọng, bỏ sót concurrency hoặc kiểm thử sai yêu cầu. Coverage cho biết mã đã được thực thi trong test; nó **không đo đầy đủ tính đúng đắn**.

Coverage có thể giúp:

- Tìm phần mã mới chưa được kiểm chứng.
- Chỉ ra nhánh xử lý lỗi bị bỏ sót.
- Kết hợp mutation testing hoặc review chất lượng test khi phù hợp.
- Quan sát thay đổi theo thời gian với cùng phương pháp đo.

Nhưng không nên dùng số phần trăm làm KPI cá nhân hoặc thay cho đánh giá rủi ro.

### 12.2. Gate cần có quy tắc ngoại lệ

Một gate đáng tin trả lời:

- Nó bảo vệ rủi ro gì?
- Khi đỏ, ai có thể điều tra?
- Nếu lỗi từ hạ tầng, xử lý thế nào?
- Ai chấp nhận ngoại lệ, bằng chứng gì, trong bao lâu?
- Cách phục hồi kiểm chứng đã bị tạm bỏ là gì?
- Khi nào xem lại rule vì cảnh báo quá nhiều hoặc bỏ sót lỗi?

**Ngoại lệ có kiểm soát khác với việc tắt check cho tiện.**

## 13. Tối ưu thứ tự check để phản hồi sớm

Nếu formatter mất vài giây nhưng được chạy sau một bộ test 40 phút, nhóm sẽ biết lỗi trình bày quá muộn. Một cách bố trí hợp lý:

| Thời điểm | Kiểm tra thường phù hợp | Mục đích |
| --- | --- | --- |
| **Máy cục bộ** | Formatter, lint nhanh, unit tests liên quan | Sửa khi thay đổi còn mới |
| **Pull request** | Compile, test nhanh, static checks, security checks thích hợp | Chặn lỗi thường gặp trước merge |
| **Nhánh chung/artifact** | Test tích hợp rộng hơn, xác minh artifact | Đảm bảo khả năng giao |
| **Theo lịch hoặc trước phát hành** | End-to-end nặng, performance, đánh giá bảo mật sâu | Xem rủi ro cần môi trường/chi phí lớn |
| **Sau triển khai** | Smoke test, health checks, giám sát | Phát hiện khác biệt môi trường và ảnh hưởng thật |

### 13.1. Chạy song song phải đi kèm cách ly

Các check độc lập có thể chạy song song để giảm thời gian, nhưng cần:

- Không dùng chung dữ liệu khiến test ảnh hưởng nhau.
- Kiểm soát giới hạn runner và dependency ngoài.
- Biết artifact nào được tạo và check nào đã kiểm chứng nó.
- Tổng hợp **mọi check bắt buộc**, không chỉ job hoàn thành đầu tiên.
- Không dùng cache hỏng hoặc không đáng tin để che sai lệch.

## 14. Ví dụ GitHub Actions với Java/Gradle

Ví dụ minh họa workflow chạy khi có pull request và push vào nhánh chính:

~~~yaml
name: java-ci

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - name: Checkout source
        uses: actions/checkout@v4

      - name: Set up JDK
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - name: Set up Gradle
        uses: gradle/actions/setup-gradle@v4

      - name: Build and verify configured checks
        run: ./gradlew --no-daemon clean build
~~~

**Giả định:** Repository có Gradle Wrapper, dùng JDK phù hợp và đã đăng ký những task build/test cần thiết. Trong dự án Java thông thường, task build bao gồm các bước assemble/check và test theo task graph; **integration test, linter hay security scanner tùy chỉnh không tự chạy nếu chưa gắn vào quy trình**.

Đối với dự án thật:

1. Kiểm tra phiên bản action còn được hỗ trợ và chính sách pin theo SHA khi cần.
2. Thay JDK minh họa bằng phiên bản thực tế được dùng.
3. Xác nhận wrapper và quyền chạy file.
4. Bổ sung báo cáo test/lint mà không làm lộ secret.
5. Xác nhận các suite quan trọng có nằm trong đường kiểm chứng hay chưa.
6. Tách triển khai production sang workflow có quyền và phê duyệt tương ứng.

**Không nên sao chép ví dụ rồi kết luận dự án đã có kiểm thử bảo mật, kiểm thử đồng thời hoặc kiểm thử hiệu năng.** Chỉ những task được cấu hình thực sự mới tạo bằng chứng.

### 14.1. Build đỏ trên nhánh chung

Nhánh chung bị đỏ kéo dài gây khó cho cả nhóm. Chính sách thường phù hợp là:

- Xác định thay đổi hoặc hạ tầng gây lỗi.
- Ưu tiên sửa hoặc hoàn tác phạm vi thay đổi bị lỗi.
- Không tích lũy thêm nhiều thay đổi chưa kiểm chứng.
- Chạy lại các check cần thiết.
- Phân tích vì sao vấn đề vượt qua gate ban đầu.

Mục tiêu là khôi phục **khả năng tích hợp đáng tin**, không phải tìm người chịu phạt vì một lần test đỏ.

## 15. CI khác Continuous Delivery và Continuous Deployment

| Khái niệm | Trọng tâm | Ví dụ |
| --- | --- | --- |
| **Continuous Integration** | Thay đổi nhỏ được tích hợp và kiểm chứng thường xuyên | PR hoặc commit kích hoạt build/test |
| **Continuous Delivery** | Giữ artifact ở trạng thái có thể phát hành theo chính sách | Artifact đã kiểm chứng, có quy trình phê duyệt phát hành |
| **Continuous Deployment** | Thay đổi đạt điều kiện được tự động triển khai tới production | Deploy và kiểm tra sau triển khai không cần nút bấm phát hành thủ công |

**CI không tự động đồng nghĩa deploy**; Continuous Delivery không có nghĩa bỏ điều kiện bảo mật/vận hành.

### 15.1. Artifact cần truy vết về đúng commit

Giả sử pipeline đã kiểm chứng artifact cho commit A. Nếu sau đó có commit B, **kết quả kiểm chứng của A không tự áp dụng cho B**. Khi phát hành, nhóm cần biết:

- Mã nguồn và phiên bản dependency nào đã tạo artifact?
- Check nào được chạy trên mã hoặc artifact tương ứng?
- Có thay đổi cấu hình nào khi triển khai?
- Có cách xác minh tính toàn vẹn artifact và quay lại phiên bản trước không?

Nguyên tắc thực dụng là **không vô tình deploy một bản khác với bản đã được kiểm chứng**, đồng thời chấp nhận những bước đóng gói theo môi trường cần thiết nếu có kiểm soát rõ.

## 16. Tự động hóa hỗ trợ Definition of Done

Trong Scrum, **Definition of Done (DoD)** mô tả trạng thái chất lượng mà Increment phải đáp ứng. Tự động hóa tạo ra bằng chứng cho nhiều điều kiện; Developers và Scrum Team vẫn phải xem xét những phần cần phán đoán hoặc kiểm chứng bổ sung.

| Điều kiện hoàn tất | Bằng chứng tự động | Bổ sung có thể cần |
| --- | --- | --- |
| Biên dịch/đóng gói | Build thành công | Xác minh artifact được phát hành |
| Logic nghiệp vụ đúng | Unit/component tests | Làm rõ yêu cầu với Product Owner |
| Giao tiếp dữ liệu đúng | Integration/contract tests | Review thiết kế, kiểm thử di trú |
| Phân quyền và bảo mật | Security test/SAST phù hợp | Đánh giá chuyên môn, threat modeling |
| Chất lượng mã | Format/lint/static analysis | Code review kiến trúc |
| Vận hành phù hợp | Smoke test, health checks | Diễn tập khôi phục, kiểm tra quy trình |
| Trải nghiệm có ích | Một số test giao diện | Thử với người dùng và accessibility review |

**Pipeline xanh không tự làm một PBI thành Done** nếu có điều kiện DoD chưa được kiểm chứng. Ngược lại, test bị đỏ vì hạ tầng không rõ cần được xử lý bằng chính sách minh bạch; không được giả định mọi lỗi đều vô hại.

## 17. Scrum, Kanban và XP tận dụng tự động hóa thế nào?

| Cách tiếp cận | Tự động hóa mang lại giá trị gì? | Thực hành |
| --- | --- | --- |
| **Scrum** | Tạo Increment đạt DoD trong từng Sprint và có bằng chứng tại Sprint Review | Build/test liên tục, không dồn QA cuối Sprint |
| **Kanban** | Giảm thời gian chờ kiểm chứng, minh bạch nơi công việc bị chặn | Theo dõi work item age và queue time của review/test |
| **XP** | Hiện thực hóa Feedback, Simplicity, Courage qua TDD/CI/refactoring | Test nhỏ, tích hợp thường xuyên, sửa thiết kế có bảo vệ |
| **Product Backlog** | Cung cấp thông tin rủi ro và độ khả thi cho ưu tiên | Spike API và kiểm thử sớm trước khi cam kết phạm vi lớn |

### Daily Scrum và pipeline đỏ

Thay vì chỉ hỏi từng người “hôm qua viết bao nhiêu code”, Developers có thể nhìn Sprint Goal và hỏi:

> “Có Increment nào đang bị chặn vì kiểm thử hoặc build? Hạng mục nào gần đạt DoD nhất? Chúng ta cần phối hợp thế nào hôm nay để hoàn tất thay vì bắt đầu thêm?”

Đây là một cách dùng dữ liệu Kanban và CI để **kiểm tra, thích ứng trong Scrum**, không phải công thức bắt buộc cho Daily Scrum.

## 18. Đo cả độ nhanh lẫn độ tin cậy của pipeline

| Chỉ số | Ý nghĩa | Điều cần tránh |
| --- | --- | --- |
| **Thời gian pipeline** | Từ lúc job bắt đầu đến kết quả | Giảm bằng cách bỏ test quan trọng |
| **Thời gian chờ runner** | Công việc chờ tài nguyên CI bao lâu | Nhầm chờ với thời gian test thực |
| **Tỷ lệ lỗi theo nguyên nhân** | Lỗi code, test, dependency, hạ tầng | Chỉ báo phần trăm fail mà không phân loại |
| **Tỷ lệ flaky** | Kết quả test thiếu ổn định | Ẩn fail khi retry thành công |
| **Thời gian khôi phục build** | Từ lúc nhánh chung đỏ tới khi ổn | Đổ lỗi cá nhân thay cải thiện cơ chế |
| **Work item age/cycle time** | Hạng mục bị chờ bao lâu trong luồng | Coi số thẻ hoàn tất là giá trị |
| **Lỗi sau phát hành** | Lỗi lọt qua các check đã có | Bỏ qua loại lỗi nghiêm trọng chỉ vì số ít |
| **Kết quả người dùng** | Increment có giải quyết nhu cầu thật? | Coi CI xanh là bằng chứng đã tạo giá trị |

### 18.1. Ví dụ tối ưu sai mục tiêu

Pipeline từ 24 phút giảm còn 8 phút vì bỏ toàn bộ integration test. Nhóm báo thành công, nhưng lỗi giao dịch đăng ký trùng xuất hiện khi có nhiều học viên cùng đăng ký. Đây là **tối ưu một chỉ số và làm xấu mục tiêu sản phẩm**.

Cách cải thiện tốt hơn có thể là:

1. Chạy check nhanh trước.
2. Tách suite độc lập và chạy song song khi có cách ly.
3. Giảm test trùng lặp đã được chứng minh.
4. Cải thiện dependency cache/runner nhưng vẫn kiểm soát nguồn.
5. Giữ các test rủi ro cao tại điểm quyết định phù hợp.
6. Xem thời gian phản hồi cùng lỗi lọt, WIP và chất lượng Increment.

## 19. Tình huống xuyên suốt: phát triển luồng đăng ký workshop

Một Scrum Team có Sprint Goal: **“Học viên đủ điều kiện đăng ký được workshop còn chỗ và nhận trạng thái đáng tin.”**

Nhóm sử dụng Java/Gradle, quản lý PR và có bảng Kanban để quan sát công việc.

### 19.1. Hiện trạng

- Các Developers dùng phiên bản JDK khác nhau; build cục bộ và CI đôi khi khác.
- Test unit nhiều nhưng đa số mock repository, không kiểm chứng giao dịch đồng thời.
- PR lớn chờ review hai đến ba ngày.
- Một test chập chờn nên thường được rerun tới khi xanh.
- Kiểm thử end-to-end bị dồn cuối Sprint.
- Story được chuyển sang Done dù vẫn còn lỗi phân quyền chưa kiểm tra.

### 19.2. Bước chẩn đoán

| Dấu hiệu | Giả thuyết | Bằng chứng cần thu |
| --- | --- | --- |
| Build khác nhau | Toolchain hoặc dependency không đồng nhất | Phiên bản JDK, Gradle, plugin, môi trường |
| Lỗi đồng thời lọt qua | Thiếu test đúng tầng | Kiểm thử giao dịch và ràng buộc trên DB thật |
| PR chờ lâu | Quá nhiều WIP hoặc review thiếu năng lực | Queue time, work item age, kích thước PR |
| Flaky bị bỏ qua | Hạ tầng/test hoặc sản phẩm thiếu ổn định | Lịch sử pass/fail, log, điều kiện tái hiện |
| Done không phản ánh chất lượng | DoD chưa rõ hoặc gate chưa gắn đúng | Quy tắc hoàn tất và bằng chứng cho từng PBI |

### 19.3. Thử nghiệm cải tiến trong hai Sprint

**Sprint thứ nhất:**

1. Thống nhất JDK và wrapper; tạo cách build có thể tái lập.
2. Chạy build và unit test trên PR.
3. Viết integration test cho chỗ cuối và phân quyền với dữ liệu thử cách ly.
4. Thống nhất gate bắt buộc trước merge.
5. Không đưa PBI chưa đáp ứng DoD sang trạng thái Done.
6. Đo queue time, WIP và lỗi có thể phát hiện sớm.

**Sprint thứ hai:**

1. Sửa flaky test theo nguyên nhân.
2. Bổ sung static/dependency/security checks hữu ích.
3. Thử tối ưu cache hoặc runner theo chính sách tin cậy.
4. Chia PR nhỏ hơn và review sớm.
5. Quan sát lỗi sau phát hành, phản hồi người dùng và thời gian từ code tới Increment.

### 19.4. Đánh giá minh họa

| Chỉ báo | Trước | Sau | Cách hiểu |
| --- | ---: | ---: | --- |
| Kết quả CI cơ bản | 25 phút | 12 phút | Nhanh hơn nếu check vẫn đủ phù hợp |
| Hạng mục chờ review/test | 6 | 3 | Có thể giảm điểm chờ; cần xem qua nhiều chu kỳ |
| Test flaky lặp lại | 4 | 1 | Tín hiệu đáng tin hơn, vẫn còn việc phải sửa |
| Lỗi đăng ký trùng lọt tới cuối Sprint | 3 | 0 trong mẫu quan sát | Đáng khích lệ, chưa chứng minh loại bỏ mọi lỗi |
| Item đạt DoD | 3 | 5 | Có thể tốt hơn; cần xét độ lớn và chất lượng item |

**Tất cả con số là tình huống giả định để học phân tích**, không phải cam kết CI sẽ tạo mức cải thiện tương ứng ở mọi nhóm.

## 20. Các tình huống khó và ranh giới quyết định

### 20.1. Check đỏ vì hạ tầng, trong khi PR là bản sửa lỗi khẩn

Không nên tự động merge khi chưa có bằng chứng, nhưng cũng không nên chờ vô hạn. Nhóm cần xác định nguyên nhân, mức rủi ro, kiểm chứng thay thế và thẩm quyền ngoại lệ. **Mọi phần kiểm chứng bị bỏ qua phải được nêu rõ**, cùng kế hoạch bổ sung sau đó.

### 20.2. Secret đã được commit rồi xóa ở commit tiếp theo

Xóa khỏi file hiện tại **không đảm bảo secret đã an toàn**: nó có thể còn trong lịch sử và đã bị sao chép. Theo quy trình bảo mật, nhóm cần **thu hồi/luân chuyển credential, đánh giá phạm vi ảnh hưởng** và xử lý lịch sử hoặc artifact nếu cần.

### 20.3. Scanner báo dependency có CVE nhưng chưa có bản vá

Phải phân tích đường khai thác, mức ảnh hưởng, biện pháp giảm thiểu, người chịu trách nhiệm và thời điểm xem lại. Không tắt scanner vô thời hạn; cũng không dùng số CVE thô làm quyết định máy móc thiếu bối cảnh.

### 20.4. Bộ test nặng khiến PR luôn chờ hàng giờ

Có thể phân tầng check, cải thiện cách ly/parallelism, chạy theo lịch hoặc trước release những bài test phù hợp; **không bỏ test cần thiết để kiểm chứng rủi ro lớn**. Nếu phần bắt buộc không thể đáp ứng, nhóm phải nói rõ giới hạn thay vì giả vờ Done.

### 20.5. Tool mới tạo quá nhiều cảnh báo di sản

Ưu tiên lỗ hổng rủi ro cao hoặc mã mới, lập backlog xử lý phần cũ và thống nhất ngoại lệ. Đừng bật chặn mọi thứ rồi vô hiệu hóa cả công cụ vì không ai xử lý nổi.

## 21. Lộ trình áp dụng từng bước

### Bước 1 — Định nghĩa hành vi và rủi ro cốt lõi

Chọn một lát cắt thực sự có giá trị. Ví dụ “không đăng ký vượt sức chứa”, với điều kiện chấp nhận và chất lượng rõ.

### Bước 2 — Chuẩn hóa build

Dùng wrapper, phiên bản công cụ và dependency có chính sách. Có một lệnh build sạch dễ chạy trên máy mới.

### Bước 3 — Tự động hóa check nhanh

Biên dịch, unit test và lint/format phù hợp; kết quả có log rõ, người chịu trách nhiệm khi đỏ.

### Bước 4 — Gắn kiểm chứng với pull request

Mỗi thay đổi được kiểm tra trên đúng commit, có chính sách merge và quyền workflow phù hợp.

### Bước 5 — Bổ sung test theo rủi ro

Với dữ liệu, phân quyền và API, xây integration/security test ở tầng cần thiết, cùng fixture độc lập.

### Bước 6 — Thêm quality/security checks

Chọn tool tạo thông tin có ích, xác định cách phân loại kết quả và quy tắc ngoại lệ.

### Bước 7 — Đo độ trễ phản hồi

Xem pipeline time, runner queue, flaky, review wait, lỗi lọt và sự ổn định của Increment.

### Bước 8 — Cải tiến theo thực nghiệm

Thử thay đổi nhỏ, xem kết quả trước/sau với cùng cách đo, điều chỉnh DoD và rule khi rủi ro thay đổi.

~~~mermaid
flowchart TD
    A["Chọn rủi ro và hành vi quan trọng"] --> B["Thiết kế test/check"]
    B --> C["Tự động chạy trong luồng tích hợp"]
    C --> D["Phân tích tín hiệu và sai lệch"]
    D --> E["Sửa mã, test, môi trường hoặc chính sách"]
    E --> F["Kiểm chứng Increment và phản hồi người dùng"]
    F --> G["Xem lại chất lượng và thời gian phản hồi"]
    G --> A
~~~

## 22. Checklist thiết kế pipeline

Đây là **mẫu học tập** chứ không phải artifact bắt buộc của Scrum, Kanban hay XP.

~~~text
MUC TIEU CUA PIPELINE:
HANH VI / RUI RO SAN PHAM CAN BAO VE:
LOAI COMMIT / PR / BRANCH DUOC KIEM TRA:

BUILD:
[ ] Toolchain va dependency duoc quan ly
[ ] Build co the tai lap, artifact truy vet commit
[ ] Secrets tach khoi ma nguon va log

TEST:
[ ] Unit tests cho logic quan trong
[ ] Integration/contract tests cho dependency thuc
[ ] Test du lieu, phan quyen va loi quan trong
[ ] Ke hoach end-to-end/performance theo rui ro
[ ] Test failure co bao cao de dieu tra
[ ] Flaky test co owner va thoi han xu ly

QUALITY/SECURITY:
[ ] Formatter/lint va static checks phu hop
[ ] Dependency/security checks theo rui ro
[ ] Coverage khong duoc coi la chung nhan chat luong
[ ] Canh bao va ngoai le co ly do/nguoi chiu trach nhiem
[ ] CI co quyen toi thieu, khong lo secret

GATE/RELEASE:
[ ] Check bat buoc gan dung commit
[ ] Co quy tac khi build do va can phe duyet ngoai le
[ ] Artifact phat hanh tuong ung ban da kiem chung
[ ] Co kiem soat deploy, theo doi va khoi phuc khi can
[ ] Done khong chi dua tren bieu tuong xanh

CAI TIEN:
- Diem cho lon nhat:
- Rui ro chua co test:
- Loi sau phat hanh:
- Gia thuyet cai tien tiep theo:
- Thoi diem xem lai:
~~~

Không cần bắt mọi thành viên ký mọi dòng cho từng PR nhỏ. Hãy **tự động hóa phần lặp lại và chọn kiểm soát tương xứng rủi ro**.

## 23. Bài tập tình huống: cải thiện CI trước ngày ra mắt

Nhóm có ba tuần để giao tính năng workshop. Dữ liệu minh họa:

| Hiện tượng | Tình trạng |
| --- | --- |
| Thời gian CI | 28 phút; 14 phút chờ runner và tải dependency |
| Unit tests | 140 test, phần lớn mock repository |
| Integration tests | Chưa chạy tự động; cần mở database thủ công |
| Security | Phát hiện một secret hard-code trong file cấu hình thử nghiệm |
| Code quality | Formatter và analyzer chạy không nhất quán |
| Test flaky | 3 test thường pass sau retry |
| Review | PR lớn, chờ 2–3 ngày |
| Sản phẩm | Lỗi tranh chỗ cuối mới được phát hiện trong kiểm thử muộn |

**Ràng buộc:** Không được bỏ kiểm soát phân quyền hoặc tính đúng đắn chỗ. Ngân sách runner có giới hạn.

### Câu hỏi

1. Phần nào cho thấy **pipeline chậm**, phần nào cho thấy **pipeline thiếu bằng chứng quan trọng**?
2. Vì sao 140 unit tests và build xanh chưa chứng minh giao dịch đồng thời an toàn?
3. Đề xuất ba ưu tiên đầu cho Sprint tiếp theo và giải thích thứ tự.
4. Vì sao xóa secret khỏi file hiện tại chưa xử lý xong sự cố?
5. Cần tạo môi trường database test thế nào để các test có thể lặp lại và không ảnh hưởng nhau?
6. Có thể giảm thời gian chờ dependency/runner mà không bỏ kiểm soát nguồn bằng cách nào?
7. Khi một test phân quyền flaky, có được xóa nó để kịp phát hành không?
8. Gate nào nên dùng cho PR và gate nào cần thêm trước phát hành?
9. PR chờ review liên quan thế nào tới WIP, work item age và cycle time?
10. Nếu thời gian CI giảm nhưng số lỗi sản phẩm tăng, nhóm nên kiểm tra điều gì?
11. Sprint Goal và Definition of Done giúp ưu tiên tự động hóa ra sao?
12. Đề xuất ba chỉ báo để đánh giá cải tiến sau hai Sprint.

### Gợi ý hướng giải

**Thứ nhất, bảo vệ rủi ro người dùng:** Thu hồi hoặc luân chuyển secret theo quy trình, phân tích phạm vi ảnh hưởng, bổ sung integration test cho giao dịch giữ chỗ và phân quyền. **Thứ hai, tạo vòng CI đáng tin:** Chuẩn hóa toolchain, môi trường database thử và check bắt buộc; xử lý flaky theo nguyên nhân. **Thứ ba, giảm thời gian phản hồi:** Cache có kiểm soát, runner hợp lý, PR nhỏ, review sớm và test song song khi cách ly được.

Gate của PR cần build, test quan trọng, check chất lượng và review phù hợp; trước phát hành có thể thêm kiểm thử rộng hơn, kiểm soát vận hành và xác nhận rủi ro còn mở. **Không dùng một lần retry xanh để xóa nghĩa vụ kiểm chứng lỗi dữ liệu hoặc bảo mật**.

## 24. Các sai lầm thường gặp

| Sai lầm | Rủi ro | Cách xử lý |
| --- | --- | --- |
| “Build xanh là nghiệp vụ đúng” | Thiếu test hành vi hoặc dữ liệu | Kiểm tra tập check và DoD |
| “Coverage cao là đủ an toàn” | Không đo chất lượng assert và rủi ro chưa kiểm | Kết hợp test theo rủi ro |
| “Mọi test phải chạy trên mọi commit” | Phản hồi quá chậm, chi phí lớn | Phân tầng kiểm chứng đúng điểm |
| “Test chậm thì bỏ” | Lỗi lọt qua gate | Tối ưu hoặc chạy ở mốc phù hợp |
| “Flaky retry tới xanh” | Che lỗi thật | Phân loại và sửa nguyên nhân |
| “Có workflow YAML là có CI tốt” | Tích hợp vẫn dồn lô lớn | Thay đổi nhỏ và phản ứng với fail |
| “CI thay thế review” | Thiếu phân tích thiết kế/giá trị | Kết hợp máy và người |
| “Static warning chắc chắn là bug” | Xử lý false positive sai | Triaging có bằng chứng |
| “SAST tìm được mọi lỗ hổng” | Bỏ sót runtime và nghiệp vụ | Nhiều lớp kiểm soát |
| “Check của commit A bảo đảm commit B” | Phát hành mã chưa được kiểm | Truy vết check/artifact |
| “PR test cần secret production” | Lộ thông tin nhạy cảm | Quyền tối thiểu, cách ly |
| “Tăng tốc bằng bỏ security scan” | Gia tăng rủi ro supply chain | Tối ưu nhưng giữ bảo vệ |
| “Kiểm thử chỉ thuộc QA” | Dồn kiểm chứng cuối Sprint | Developers cùng tạo Increment đạt DoD |
| “Build đỏ có thể để sang Sprint sau” | Nhánh chung không tin cậy | Ưu tiên khôi phục và học |
| “Mọi warning cũ phải chặn từ hôm nay” | Gate không khả thi | Lộ trình new code và rủi ro cao |
| “CI/CD miễn trừ phê duyệt production” | Bỏ nghĩa vụ vận hành/pháp lý | Quyền quyết định rõ |
| “Càng nhiều tool càng Agile” | Hệ thống rườm rà, không có owner | Chọn tool theo giá trị |
| “Pipeline nhanh hơn luôn tốt” | Có thể bỏ kiểm chứng thiết yếu | Đo cùng chất lượng và outcome |

## 25. Ghi nhớ và tự kiểm tra

**Tự động hóa xây dựng, kiểm thử và kiểm tra chất lượng biến phản hồi kỹ thuật thành một phần thường xuyên của phát triển Agile.** Build lặp lại được giúp nhóm tích hợp; kiểm thử nhiều tầng giúp phát hiện sai lệch hành vi; static/security checks tìm thêm rủi ro; quality gate bảo vệ các quyết định merge và phát hành. **Không một biểu tượng xanh nào thay thế được hiểu biết nghiệp vụ, review chuyên môn, chất lượng Increment và phản hồi người dùng.**

Tự kiểm tra:

1. Build automation khác test automation và CI như thế nào?
2. Vì sao phải kiểm soát công cụ, dependency và đầu vào để build đáng tin?
3. Trong Gradle, task build, check và test liên hệ nhau thế nào?
4. Unit test, integration test và end-to-end test giải quyết những rủi ro khác nhau ra sao?
5. Vì sao mock repository chưa chứng minh không đăng ký vượt sức chứa khi đồng thời?
6. TDD Red – Green – Refactor giúp nhóm thay đổi mã an toàn hơn thế nào?
7. Flaky test nguy hiểm ở điểm nào? Vì sao retry không phải cách sửa?
8. Vì sao line coverage không được dùng như chứng chỉ chất lượng?
9. Quality gate của PR khác điều kiện phát hành ở đâu?
10. Secret trong commit đã xóa ở commit tiếp theo còn nguy hiểm gì?
11. Làm sao xử lý CVE ở dependency khi chưa có bản vá?
12. Vì sao CI cần quyền tối thiểu và tách khỏi workflow deploy?
13. Artifact được kiểm chứng cần truy vết về commit thế nào?
14. Pipeline xanh và Definition of Done khác nhau ra sao?
15. Những chỉ số nào cho biết tự động hóa vừa nhanh hơn vừa đáng tin hơn?
16. Scrum, Kanban và XP có thể sử dụng phản hồi tự động ra sao?

Trước khi thêm một tool hoặc bước kiểm chứng, hãy hỏi: **“Rủi ro nào cần được nhận biết sớm, tín hiệu có đủ tin để quyết định không, ai sẽ hành động khi nó thất bại và liệu cách làm này giúp nhóm giao Increment có giá trị nhanh hơn mà không đánh đổi chất lượng?”** Trả lời được những câu hỏi ấy giúp tự động hóa trở thành thực hành kỹ thuật phục vụ **phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục** trong Agile.
