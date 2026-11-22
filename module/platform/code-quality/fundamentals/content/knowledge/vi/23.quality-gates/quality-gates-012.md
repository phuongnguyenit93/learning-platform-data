# Bảo đảm cổng không thể thay thế toàn bộ trách nhiệm rà soát

Một pull request đã vượt qua build, unit test, kiểm tra coverage và static analysis. Dashboard hiển thị **Quality Gate: PASS**. Tuy nhiên, người review vẫn cần hỏi: thay đổi có thực hiện đúng yêu cầu không, có làm lộ dữ liệu của tenant khác không, khi dịch vụ thanh toán timeout thì trạng thái đơn hàng ra sao, và người vận hành có thể khôi phục hệ thống không?

Một cổng chất lượng (*quality gate*) giúp áp dụng những điều kiện có thể kiểm tra một cách nhất quán trước khi merge hoặc phát hành. Nhưng công cụ chỉ đánh giá **các quy tắc và đầu vào đã được cấu hình**. Nó không tự hiểu đầy đủ ý định nghiệp vụ, mọi bối cảnh kiến trúc, đánh đổi thiết kế hoặc tác động của một thay đổi tới người dùng. Vì vậy, **PASS là bằng chứng cần thiết trong quy trình, không phải sự thay thế cho trách nhiệm rà soát của con người**.

Trong chương **Cổng chất lượng** của module **CODE_QUALITY_FUNDAMENTALS**, bài học này giúp hiểu cách duy trì mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Một quy trình tốt kết hợp kiểm tra tự động với code review có trách nhiệm: máy thực hiện những kiểm tra lặp lại, định lượng được; reviewer đánh giá ngữ nghĩa, bối cảnh và các rủi ro mà công cụ không thể kết luận đầy đủ.

> Cổng chất lượng trả lời “những điều kiện đã định nghĩa có đạt không?”. Review còn phải trả lời “thay đổi này có đúng, phù hợp và an toàn trong hệ thống cụ thể không?”.

## 1. Cổng chất lượng là gì?

**Quality gate** là một tập điều kiện được dùng để quyết định một thay đổi, nhánh mã hoặc artifact có đủ tiêu chuẩn đi tiếp trong quy trình hay không. Cổng thường chạy trong CI/CD và tổng hợp kết quả từ nhiều bước kiểm tra.

Ví dụ, một cổng có thể yêu cầu:

- Dự án biên dịch thành công.
- Bộ unit test bắt buộc không thất bại.
- Không có lỗi nghiêm trọng mới từ static analysis.
- Không có lỗ hổng dependency vượt ngưỡng chính sách.
- Mã mới đáp ứng mức coverage đã thống nhất.
- Artifact được tạo đúng và có thể truy vết về commit.
- Các kiểm tra bảo mật và cấu hình bắt buộc đã hoàn tất.

Khi một điều kiện không đạt, pipeline có thể chặn merge, chặn tạo bản phát hành hoặc yêu cầu người có thẩm quyền xử lý ngoại lệ. Cổng là **cơ chế thực thi chính sách kỹ thuật**, không phải một đánh giá toàn diện về giá trị của thay đổi.

### 1.1. Phân biệt các khái niệm liên quan

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **CI check** | Một bước kiểm tra cụ thể | Chạy lệnh build/test |
| **Quality gate** | Tập điều kiện quyết định có được đi tiếp | Build xanh, test đạt, không có blocker mới |
| **Dashboard** | Hiển thị trạng thái và xu hướng | Số cảnh báo theo module |
| **Code review** | Con người xem xét tính đúng, thiết kế, bối cảnh và rủi ro | Reviewer phát hiện thiếu kiểm tra quyền |
| **Approval rule** | Quy định ai phải xem xét hoặc chấp thuận | Cần một maintainer của module |
| **Release approval** | Quyết định phát hành theo bối cảnh vận hành | Người trực vận hành xác nhận rollout |

Một dashboard xanh không tự động chứng minh nhánh được bảo vệ đúng. Một CI check chạy thành công cũng chưa chắc đã được quality gate bắt buộc. Cần phân biệt **có chạy**, **có báo kết quả** và **kết quả đó có thực sự chặn tiến trình hay không**.

### 1.2. Cổng kiểm tra điều kiện, không hiểu toàn bộ chất lượng

Giả sử dự án đặt ngưỡng coverage 80%. Một PR đạt 82% có thể vượt cổng. Nhưng nếu test chỉ gọi phương thức rồi kiểm tra **assertNotNull**, coverage cao vẫn có thể bỏ sót lỗi tại ngưỡng nghiệp vụ. Ngược lại, một module xử lý thuật toán số học khó có thể có bộ test rất tốt với coverage thấp hơn một ngưỡng chung không phù hợp.

Chỉ số là **đại diện cho một thuộc tính**, không phải thuộc tính chất lượng hoàn chỉnh. Reviewer cần hiểu cổng đang đo điều gì và giới hạn của phép đo đó.

## 2. Máy kiểm tra điều gì tốt, con người cần xem điều gì?

Một cách phân chia trách nhiệm hữu ích:

| Tự động hóa phù hợp | Review của con người cần đánh giá |
| --- | --- |
| Biên dịch, dependency resolution, định dạng theo rule | Thay đổi có giải quyết đúng vấn đề và đúng phạm vi không? |
| Chạy test đã định nghĩa | Oracle của test có phản ánh yêu cầu thật không? |
| Static analysis và một số luồng dữ liệu | Cảnh báo có áp dụng trong bối cảnh cụ thể? Có đường đi nào công cụ không mô hình hóa? |
| Coverage, mutation score nếu có | Các ca test có kiểm tra đúng điều quan trọng hay chỉ chạy qua dòng mã? |
| Quét dependency và cấu hình theo policy | Thành phần có thực sự được triển khai, khai thác theo cách nào, rủi ro được giảm thiểu ra sao? |
| Kiểm tra license, secret, artifact metadata | Quyết định sử dụng thư viện hoặc dữ liệu có phù hợp sản phẩm và tổ chức không? |
| Kiểm tra schema, migration script theo rule | Thứ tự rollout, dữ liệu cũ và rollback/fix-forward có an toàn không? |
| Kiểm tra format, schema API ở mức cấu trúc | Ngữ nghĩa API, khả năng tương thích và trải nghiệm caller có bị thay đổi không? |

Máy có lợi thế ở tính lặp lại: cùng rule có thể áp dụng cho mọi PR và không phụ thuộc việc reviewer có nhớ từng chi tiết hay không. Con người có lợi thế ở việc kết nối yêu cầu, kiến trúc, dữ liệu, người dùng và những hệ quả không thể biểu diễn hết thành rule.

**Không nên giao cho reviewer việc kiểm tra thủ công mọi quy tắc định dạng hoặc chạy đi chạy lại cùng một lệnh test** nếu pipeline có thể tự động hóa đáng tin cậy. Cũng không nên giao cho một con số coverage quyết định thay reviewer rằng thiết kế đã tốt.

## 3. Những lớp thường có trong quality gate

Không phải dự án nào cũng cần tất cả điều kiện dưới đây. Hãy chọn dựa trên loại sản phẩm, mức rủi ro, khả năng của công cụ và chi phí bảo trì.

### 3.1. Build và kiểm tra tính hợp lệ cơ bản

Build giúp xác nhận mã có thể được biên dịch, dependency có thể resolve và các bước đóng gói đã cấu hình hoàn tất.

Với dự án Gradle Java, một bước minh họa:

~~~bash
./gradlew clean check
~~~

Lệnh trên chỉ chạy những task được build định nghĩa và nối vào check; nó không tự đảm bảo mọi module, source set hoặc profile đều được bao phủ nếu cấu hình dự án bỏ sót chúng.

Reviewer vẫn cần kiểm tra:

- Module nào được build và module nào bị bỏ qua?
- Có dùng đúng JDK, compiler flags và phiên bản dependency không?
- Test nào không chạy do profile hoặc điều kiện môi trường?
- Artifact có chứa đúng class, resource và metadata cần phát hành không?
- Có bước build nào bị cache hoặc skip khiến kết quả không phản ánh source mới?

### 3.2. Unit test, integration test và contract test

Các test tự động có thể là điều kiện gate, nhưng loại test phải phù hợp rủi ro:

- **Unit test:** kiểm tra quy tắc nhỏ, thường chạy nhanh và cô lập.
- **Integration test:** kiểm tra tương tác giữa module, DB, queue hoặc dịch vụ ngoài trong môi trường kiểm soát.
- **Contract test:** kiểm tra giao thức mà một bên cung cấp và bên tiêu thụ cùng phụ thuộc.
- **End-to-end test:** kiểm tra luồng qua nhiều thành phần, thường tốn thời gian và nhạy với môi trường hơn.

Không nên lấy số lượng test làm thước đo duy nhất. Một bộ test có nhiều ca sao chép cùng một oracle sai vẫn không bảo vệ được hợp đồng.

### 3.3. Static analysis và quy ước mã

Checkstyle, PMD, SpotBugs hoặc các công cụ tương tự có thể phát hiện những nhóm vấn đề khác nhau. Cổng có thể đặt điều kiện với:

- Lỗi biên dịch hoặc cảnh báo được xem là nghiêm trọng.
- Vi phạm rule bắt buộc về mã nguồn.
- Một số mẫu lỗi null, resource leak, sử dụng API không an toàn.
- Cảnh báo mới trong mã được thay đổi.

Kết quả phụ thuộc **phiên bản công cụ, bộ rule, classpath, source set, cấu hình và phạm vi quét**. Nếu cổng không chạy trên module vừa thay đổi, trạng thái PASS không tạo bằng chứng cho module đó.

### 3.4. Coverage và chất lượng test

Coverage có thể đo dòng, nhánh hoặc các đơn vị khác tùy công cụ. Nó giúp tìm vùng chưa được thực thi trong test, nhưng không trực tiếp cho biết assertion có đúng hay không.

Ví dụ:

~~~java
@Test
void quoteReturnsSomething() {
    var quote = QuoteCalculator.quote(validLines(), false);
    assertNotNull(quote);
}
~~~

Test này có thể thực thi nhiều dòng mã, nhưng chưa xác minh subtotal, phí vận chuyển, tổng tiền hoặc ngưỡng. Một test có oracle cụ thể hơn:

~~~java
@Test
void regularCustomerGetsFreeShippingAtThreshold() {
    var lines = List.of(new QuoteCalculator.Line(500_000L, 1));

    var quote = QuoteCalculator.quote(lines, false);

    assertEquals(0L, quote.shippingFeeVnd());
    assertEquals(500_000L, quote.payableVnd());
}
~~~

Coverage là một **tín hiệu về mức thực thi**, còn test assertions và chất lượng oracle mới cho biết các kết quả nào đã được xác minh.

### 3.5. Security, dependency và cấu hình

Gate có thể chặn:

- Secret được phát hiện trong source hoặc artifact.
- Dependency có lỗ hổng đã biết vượt chính sách.
- Cấu hình triển khai vi phạm rule bảo mật.
- Artifact có nguồn gốc hoặc chữ ký không đáp ứng yêu cầu.
- Những cảnh báo static security analysis ở mức rủi ro được chọn.

Nhưng công cụ không thể tự kết luận toàn bộ khả năng khai thác hoặc mức ảnh hưởng nghiệp vụ. Reviewer vẫn cần hỏi thành phần có thực sự được đóng gói và triển khai không, đường dữ liệu có tới điểm rủi ro không, quyền truy cập ra sao và có biện pháp giảm thiểu nào.

### 3.6. Kiểm tra artifact và khả năng truy vết

Một build xanh nhưng tạo artifact không xác định được source commit, thiếu SBOM hoặc dùng dependency khác với dependency đã quét có thể làm giảm độ tin cậy của phát hành.

Các điều kiện có thể gồm:

- Artifact được gắn commit/version rõ ràng.
- Dependency được khóa hoặc resolve theo chính sách đã chọn.
- SBOM hoặc manifest thành phần được tạo nếu quy trình yêu cầu.
- Artifact đã quét chính là artifact sẽ phát hành.
- Kết quả kiểm tra có thể truy về lần build và cấu hình tương ứng.

Đây là kiểm tra **tính toàn vẹn và khả năng truy vết của chuỗi build**. Nó không thay thế việc review thay đổi nghiệp vụ.

## 4. Những điều quality gate không thể tự kết luận

### 4.1. Không biết yêu cầu nghiệp vụ nếu không có oracle

Một static analyzer có thể thấy phép so sánh hợp lệ, kiểu dữ liệu đúng và không có cảnh báo. Nó không thể tự biết chính sách của cửa hàng là **miễn phí từ 500.000 VND** hay **miễn phí trên 500.000 VND**, trừ khi quy tắc ấy được biểu diễn thành kiểm tra cụ thể.

Reviewer cần đối chiếu:

- Acceptance criteria và bảng quyết định.
- Giá trị biên và các trường hợp bị từ chối.
- Đơn vị, làm tròn, múi giờ hoặc thứ tự ưu tiên nếu có.
- Khác biệt giữa refactor giữ nguyên hành vi và thay đổi nghiệp vụ.

### 4.2. Không hiểu đầy đủ bối cảnh kiến trúc

Một hàm có thể pass mọi test đơn vị nhưng được gọi sai vị trí trong workflow. Ví dụ, service lưu đơn trước khi xác thực quyền truy cập; hàm lưu hoạt động đúng theo hợp đồng cục bộ nhưng trình tự điều phối vi phạm hợp đồng hệ thống.

Reviewer cần xem **ranh giới và luồng gọi**:

- Ai gọi phương thức, ai sở hữu transaction?
- Dữ liệu đã được xác thực và phân quyền trước khi sử dụng chưa?
- Có side effect nào xảy ra trước khi mọi điều kiện bắt buộc được kiểm tra?
- Thay đổi có phá module khác, job theo lịch hoặc client bên ngoài?
- Có phụ thuộc vòng, coupling hoặc trách nhiệm mới đặt sai lớp?

### 4.3. Không đánh giá đầy đủ chất lượng thiết kế

Một gate có thể đo số lượng cảnh báo, độ phức tạp theo công cụ hoặc coverage. Nhưng nó khó kết luận:

- Tên miền và abstraction có phản ánh đúng khái niệm nghiệp vụ không?
- Một lớp có đang ôm quá nhiều trách nhiệm không?
- API có dễ sử dụng và khó gọi sai không?
- Có đang trừu tượng hóa quá sớm hoặc gom hai chính sách độc lập?
- Thiết kế có hỗ trợ thay đổi sắp tới mà không tạo thêm coupling?

Các chỉ số có thể chỉ ra **nơi nên xem xét**, còn quyết định thiết kế cần người hiểu hệ thống và mục tiêu sản phẩm.

### 4.4. Không chứng minh mọi tình huống runtime

CI thường chạy trên dữ liệu và môi trường kiểm soát. Nó không tự bao phủ tất cả:

- Lịch chạy đồng thời hoặc race condition hiếm.
- Sự cố mạng, mất kết nối giữa các bước và timeout không xác định kết quả.
- Cấu hình production thực tế hoặc secret được inject ngoài repository.
- Tải, dung lượng dữ liệu và hành vi của dependency ở quy mô thật.
- Dữ liệu lịch sử, client cũ và các hệ thống bên ngoài.
- Tác động vận hành khi rollout, rollback hoặc khôi phục sau sự cố.

Một gate có thể chạy concurrency test, load test hoặc integration test để giảm rủi ro, nhưng mỗi test vẫn có **phạm vi và giới hạn**. Reviewer phải đọc kết quả đúng mức, không diễn giải test xanh thành bảo đảm tuyệt đối.

## 5. Quality gate và code review cần phối hợp thế nào?

Một quy trình hiệu quả để hai cơ chế bổ trợ nhau:

~~~text
Tác giả mở Pull Request
          |
          v
 CI chạy build / test / analysis
          |
          v
  Quality gate đánh giá policy
          |
          +---- Không đạt ------> Sửa lỗi hoặc xin ngoại lệ
          |
          v
 Reviewer đọc thay đổi và bối cảnh
          |
          +---- Có vấn đề ------> Trao đổi / sửa / xác minh
          |
          v
 Đủ điều kiện kỹ thuật + approval
          |
          v
       Merge / release
~~~

Đây là mô hình khái quát. Trong thực tế CI có thể chạy nhiều lần khi tác giả cập nhật PR, reviewer có thể xem diff trước khi CI xong, và một số kiểm tra phát hành chỉ chạy sau merge. Điều quan trọng là **không được bỏ điều kiện bắt buộc chỉ vì một người đã review**, cũng không được tự động merge chỉ vì gate xanh nếu quy trình yêu cầu approval.

### 5.1. Trách nhiệm của tác giả

Tác giả cần:

- Viết mô tả nêu vấn đề, hành vi trước/sau và phạm vi.
- Bổ sung test có oracle cho logic mới hoặc thay đổi.
- Đọc kết quả gate, xử lý cảnh báo do mình tạo ra.
- Giải thích suppression hoặc ngoại lệ có căn cứ.
- Chỉ ra rủi ro migration, compatibility, rollout và rollback nếu liên quan.
- Trả lời nhận xét reviewer bằng bằng chứng hoặc lý do kỹ thuật.

Không nên coi “CI sẽ bắt lỗi” là lý do để tác giả không tự xem lại diff và test.

### 5.2. Trách nhiệm của reviewer

Reviewer cần:

- Kiểm tra thay đổi có đáp ứng yêu cầu và giữ hợp đồng không.
- Đọc test để đánh giá chất lượng oracle, ca biên và luồng lỗi.
- Xem thiết kế, phân quyền, dữ liệu, concurrency và side effect theo mức rủi ro.
- Kiểm tra phạm vi của các kết quả CI và cảnh báo được chấp nhận.
- Phân biệt lỗi cần chặn với cải tiến không thuộc phạm vi PR.
- Không phê duyệt chỉ dựa trên số lượng người khác đã approve hoặc trạng thái màu xanh.

Reviewer không cần lặp lại mọi bước máy đã làm nếu có thể tin cậy kết quả và hiểu phạm vi. Thời gian review nên tập trung vào **những điều cần phán đoán**.

### 5.3. Trách nhiệm của người duy trì pipeline

Người sở hữu CI và quality policy cần:

- Bảo đảm các check bắt buộc thực sự chạy và kết quả không bị bỏ qua.
- Giữ phiên bản công cụ, rule và cấu hình có thể truy vết.
- Kiểm tra module, source set, generated code và artifact có được bao phủ.
- Quản lý baseline, false positive và ngoại lệ minh bạch.
- Giữ thời gian chạy hợp lý để nhóm không tìm cách né pipeline.
- Theo dõi độ ổn định, flakiness và các lần gate bị bypass.

Một gate lỗi liên tục hoặc chặn nhầm sẽ làm người dùng mất niềm tin. Cải thiện độ tin cậy của pipeline cũng là công việc kỹ thuật cần được ưu tiên.

## 6. Quy tắc merge phải rõ ràng và có thể kiểm chứng

Quality gate chỉ thực sự bảo vệ nhánh khi chính sách merge được cấu hình đúng.

Ví dụ, repository có thể yêu cầu:

- Tất cả CI check bắt buộc phải hoàn thành thành công.
- Có ít nhất một approval từ người đủ quyền.
- PR phải được cập nhật với nhánh đích theo chính sách.
- Không còn conversation hoặc review request chưa được giải quyết theo quy định.
- Chỉ nhóm maintainer được phép bypass trong tình huống đã định nghĩa.

Các quy định cụ thể tùy nền tảng quản lý mã và tổ chức. Không nên giả định chỉ bật một workflow CI là đã bảo vệ nhánh.

### 6.1. Phân biệt trạng thái

| Trạng thái | Ý nghĩa | Hành động tiếp theo |
| --- | --- | --- |
| **PASS** | Những điều kiện đã chạy và được cấu hình đều đạt | Vẫn chờ review/approval nếu quy trình yêu cầu |
| **FAIL** | Có ít nhất một điều kiện không đạt | Điều tra và sửa, hoặc đi qua quy trình ngoại lệ hợp lệ |
| **PENDING** | Check chưa chạy hoặc chưa có kết quả cuối | Chờ kết quả; không coi là PASS |
| **SKIPPED** | Check không chạy do điều kiện hoặc cấu hình | Xác minh việc skip có được phép và phạm vi có bị mất không |
| **CANCELLED** | Lần chạy bị hủy | Chạy lại hoặc xác định lý do hủy |
| **UNKNOWN / ERROR** | Không xác định được kết quả đáng tin cậy | Xử lý như chưa có bằng chứng, không tự coi là đạt |

Một check bị skip có thể là bình thường, ví dụ tài liệu không cần chạy test Java. Nhưng nếu check security bị skip do thiếu credentials hoặc lỗi cấu hình, kết quả đó **không thể được diễn giải là không có phát hiện bảo mật**.

### 6.2. Gate phải chạy trên đúng nội dung được merge

Một kết quả xanh của commit cũ không nhất thiết áp dụng cho diff mới. Khi PR thay đổi sau khi CI hoàn tất, cần có cơ chế:

- Chạy lại các check cần thiết trên commit mới.
- Yêu cầu kết quả gắn với đúng SHA hoặc artifact.
- Tránh merge một trạng thái đã stale theo chính sách nhánh.
- Nếu build phụ thuộc base branch, xác minh lại sau khi base thay đổi theo mức rủi ro.

Điều này bảo đảm reviewer và hệ thống dựa trên **cùng một phiên bản thay đổi**. Nếu review một diff nhưng merge một commit khác, bằng chứng approval có thể không còn phù hợp.

### 6.3. Kiểm tra phạm vi và quyền bypass

Khi gate có cơ chế miễn trừ hoặc bypass, cần biết:

- Ai có quyền bypass?
- Điều kiện nào cho phép dùng?
- Có yêu cầu ghi lý do hoặc ticket sự cố không?
- Có ghi nhận người, thời điểm, commit và check bị bỏ qua không?
- Ai theo dõi việc khắc phục sau bypass?

Nếu mọi developer có thể bỏ qua gate bất cứ lúc nào, gate không còn là rào chắn có hiệu lực. Nếu không ai có thể xử lý một lỗi hạ tầng nghiêm trọng, quy trình có thể chặn cả hoạt động khẩn cấp. Cần **quyền hạn giới hạn, dấu vết kiểm toán và trách nhiệm hậu kiểm**.

## 7. Đặt ngưỡng gate có ý nghĩa

Một quality gate quá lỏng không ngăn được rủi ro; quá nghiêm hoặc không phù hợp có thể tạo false positive, kéo dài feedback và khuyến khích nhóm tìm cách né tránh.

### 7.1. Ưu tiên điều kiện gắn với rủi ro

Ví dụ một bộ điều kiện ban đầu:

| Điều kiện | Lý do | Cách tránh đặt ngưỡng máy móc |
| --- | --- | --- |
| Build bắt buộc thành công | Không phát hành mã không biên dịch/đóng gói được | Chọn đúng module và JDK hỗ trợ |
| Test bắt buộc không thất bại | Bảo vệ hành vi đã có oracle | Kiểm tra test có thật sự chạy và ổn định |
| Không có lỗi bảo mật nghiêm trọng mới | Giảm nguy cơ phát hành rủi ro cao | Đánh giá khả năng áp dụng và xử lý ngoại lệ có căn cứ |
| Không có dependency vi phạm policy | Kiểm soát thành phần sử dụng | Xem artifact runtime, mức ảnh hưởng và phương án cập nhật |
| Không thêm lỗi nghiêm trọng vào mã mới | Ngăn nợ tăng | Baseline cũ phải minh bạch và có kế hoạch xử lý |
| Review approval bắt buộc | Bảo đảm có phán đoán của con người | Chọn reviewer hiểu vùng mã và tránh approve hình thức |

### 7.2. Coverage: ngưỡng tổng và mã mới

Nếu toàn repository có nhiều mã cũ chưa được test, đặt ngưỡng tổng coverage cao ngay có thể làm mọi thay đổi bị chặn vì nợ lịch sử. Một chiến lược có thể là:

- Giữ **baseline hiện trạng** được ghi nhận.
- Đặt kỳ vọng cho **mã mới hoặc mã thay đổi**.
- Không cho thay đổi làm coverage giảm dưới chính sách đã thống nhất.
- Ưu tiên test các nhánh có hậu quả cao.
- Theo dõi nợ coverage cũ và kế hoạch tăng dần.

Nhưng đo coverage trên “mã mới” cũng cần cẩn thận: nếu nhóm tách code sang file mới hoặc thêm nhiều nhánh, phạm vi mẫu số thay đổi. Reviewer nên xem **test oracle và độ rủi ro**, không chỉ con số.

### 7.3. Đếm cảnh báo mới thay vì che toàn bộ cảnh báo cũ

Baseline có thể giúp không để nợ mới tăng trong khi đang xử lý tồn đọng. Tuy nhiên:

- Không được exclude cả module chỉ vì module đó có nhiều cảnh báo.
- Cảnh báo cũ có thể trở nên nghiêm trọng hơn khi cách dùng thay đổi.
- Công cụ nâng phiên bản có thể thay đổi tập rule và kết quả.
- Suppression phải gắn với lý do và phạm vi cụ thể.
- “Không có issue mới” không có nghĩa “không có issue”.

Một gate tốt giúp **nợ mới khó lọt qua hơn**, đồng thời hiển thị rõ khoản nợ cũ vẫn còn.

### 7.4. Không biến metric thành mục tiêu dễ thao túng

Khi một con số trở thành mục tiêu duy nhất, nhóm có thể tối ưu con số thay vì chất lượng:

- Thêm assertion yếu chỉ để tăng coverage.
- Loại tệp khó khỏi phạm vi scan.
- Tắt rule tạo nhiều cảnh báo.
- Chia nhỏ hoặc đổi tên module để thay đổi mẫu số.
- Tạo test chỉ chạy qua code nhưng không xác minh kết quả.

Hãy dùng **nhiều tín hiệu bổ trợ**, kiểm tra tính toàn vẹn của cấu hình và review các thay đổi làm thay đổi phạm vi đo. Metric hữu ích khi hỗ trợ quyết định, không phải khi thay thế tư duy.

## 8. Khi gate thất bại: sửa nguyên nhân thay vì tìm cách làm xanh

Một gate FAIL không phải lúc nào cũng có nghĩa mã nguồn có lỗi. Có thể là test thất bại, dependency repository không truy cập được, scanner lỗi, cấu hình thiếu hoặc policy thực sự bị vi phạm. Cần phân loại trước khi hành động.

### 8.1. Phân biệt lỗi sản phẩm và lỗi hạ tầng kiểm tra

| Dấu hiệu | Khả năng cần điều tra | Bước tiếp theo |
| --- | --- | --- |
| Assertion test thất bại ổn định | Hành vi sai hoặc oracle/test cần xem lại | Tái hiện, xác minh yêu cầu và sửa |
| Test lúc xanh lúc đỏ | Race, dữ liệu dùng chung, thời gian hoặc môi trường không ổn định | Điều tra flakiness; không retry mù quáng |
| Build không resolve dependency | Repository, credentials, version hoặc mạng | Kiểm tra hạ tầng và tính tái lập |
| Scanner không khởi động | Token, phiên bản, cấu hình hoặc dịch vụ scanner | Khôi phục check; kết quả chưa có không phải PASS |
| Có cảnh báo mới | Mã hoặc cấu hình vi phạm rule | Xác minh áp dụng, sửa hoặc xin ngoại lệ đúng quy trình |
| Coverage giảm | Thiếu test, đổi phạm vi đo hoặc cấu hình sai | Xem diff và mẫu số; bổ sung test phù hợp |
| Artifact khác với artifact đã scan | Lỗi chuỗi build hoặc đóng gói | Dừng phát hành và xác minh nguồn gốc |

Không nên coi mọi FAIL là lỗi tác giả, cũng không nên coi mọi lỗi công cụ là lý do để bypass. **Trạng thái không có bằng chứng đáng tin cậy cần được giữ ở trạng thái chưa đạt** cho đến khi được xử lý.

### 8.2. Không retry test flaky cho đến khi xanh

Nếu một test thất bại vì race condition, chạy lại có thể tình cờ xanh. Nhưng lỗi vẫn tồn tại và có thể xảy ra trong production. Retry chỉ hữu ích khi:

- Có bằng chứng lỗi đến từ sự cố hạ tầng tạm thời.
- Chính sách retry được giới hạn số lần.
- Kết quả từng lần chạy vẫn được lưu và quan sát.
- Lỗi flaky được theo dõi để sửa gốc.

Một pipeline luôn tự động chạy lại cho đến khi thành công sẽ làm **mất tín hiệu cảnh báo** và giảm độ tin cậy của gate.

### 8.3. Xử lý cảnh báo scanner

Khi có cảnh báo:

1. Xác nhận công cụ đã quét đúng commit, module và artifact.
2. Đọc rule, vị trí, đường dữ liệu và điều kiện phát hiện.
3. Đối chiếu với hợp đồng và cách chạy thực tế.
4. Sửa mã nếu cảnh báo áp dụng.
5. Nếu là false positive, ghi bằng chứng và suppression hẹp theo chính sách.
6. Thêm test hoặc kiểm soát bù trừ nếu rủi ro quan trọng.
7. Ghi nhận chủ sở hữu và điều kiện xem lại nếu ngoại lệ có thời hạn.

Reviewer không nên chấp nhận một nhận xét “scanner báo sai” mà không có lý do cụ thể. Tác giả cũng không cần sửa máy móc mọi cảnh báo nếu có bằng chứng hợp lệ rằng rule không áp dụng; quan trọng là **quyết định có thể được người khác kiểm tra lại**.

## 9. Ngoại lệ và bypass phải được quản lý

Không có hệ thống thực tế nào đảm bảo mọi gate luôn chính xác trong mọi tình huống. Có thể xuất hiện false positive, lỗi scanner, dependency chưa có bản vá hoặc sự cố production đòi hỏi phát hành khẩn cấp.

Điều đó không có nghĩa nên mở một lối bypass tùy ý. Cần phân biệt:

- **False positive:** cảnh báo không áp dụng theo bằng chứng cụ thể.
- **Risk acceptance:** tổ chức chấp nhận rủi ro còn lại trong một phạm vi và thời hạn.
- **Emergency bypass:** bỏ qua một điều kiện trong tình huống khẩn cấp có kiểm soát.
- **Tool outage:** không có kết quả vì công cụ hoặc hạ tầng kiểm tra không hoạt động.

Các tình huống này khác nhau về nguyên nhân và trách nhiệm.

### 9.1. Một ngoại lệ tốt cần thông tin gì?

| Trường | Nội dung cần ghi |
| --- | --- |
| Check bị miễn | Tên check, rule, commit hoặc artifact liên quan |
| Lý do | False positive, lỗi hạ tầng hay rủi ro được chấp nhận? |
| Bằng chứng | Vì sao rule không áp dụng hoặc vì sao cần phát hành khẩn cấp? |
| Phạm vi | Một cảnh báo, một module hay một lần phát hành? |
| Biện pháp giảm thiểu | Test bổ sung, giới hạn rollout, theo dõi hoặc kiểm soát khác |
| Người phê duyệt | Ai có thẩm quyền chấp nhận rủi ro? |
| Hạn/điều kiện xem lại | Khi nào phải sửa, chạy lại check hoặc loại bỏ suppression? |

Không phải mọi ngoại lệ đều cần cùng mức tài liệu. Một suppression style cục bộ có thể cần chú thích ngắn; bỏ qua scan bảo mật trước phát hành cần mức phê duyệt và kiểm soát cao hơn.

### 9.2. Bypass khẩn cấp không đồng nghĩa bỏ trách nhiệm

Trong sự cố production, nhóm có thể cần phát hành bản sửa trước khi một check không thiết yếu hoạt động trở lại. Một quy trình có kiểm soát nên:

- Chỉ cho người có quyền phù hợp thực hiện.
- Ghi lý do, phạm vi và commit/artifact bị ảnh hưởng.
- Giữ lại các check thiết yếu khác có thể chạy.
- Có test hoặc xác minh thay thế phù hợp với rủi ro.
- Giới hạn rollout và theo dõi sau phát hành.
- Tạo việc hậu kiểm để chạy lại check, sửa nguyên nhân và đóng ngoại lệ.

Nếu một scanner bảo mật không hoạt động, không nên tự động tuyên bố không có lỗ hổng. Nếu vẫn phải phát hành vì sự cố, quyết định đó là **risk acceptance có chủ đích**, cần người có thẩm quyền chịu trách nhiệm.

### 9.3. Ngoại lệ không được trở thành cấu hình mặc định

Các dấu hiệu đáng lo:

- Một rule bị tắt trên toàn repository vì vài false positive.
- Nhiều module bị exclude nhưng không có chủ sở hữu.
- Approval được cấp tự động mà không có người xem xét.
- Check bảo mật thường xuyên bị bypass vì chạy quá lâu.
- Suppression không có thời hạn hoặc điều kiện xem lại.
- Nhóm không còn biết vì sao gate được cấu hình như hiện tại.

Khi điều này xảy ra, cần cải thiện **rule, chất lượng scanner, phạm vi hoặc thời gian pipeline**, thay vì tiếp tục nới lỏng cổng.

## 10. Ví dụ: một PR PASS nhưng vẫn cần review

Giả sử một dự án Java có quality gate với các điều kiện:

~~~text
Build: PASS
Unit tests: PASS
Line coverage: 84% (threshold 80%)
Static analysis: PASS
Dependency scan: PASS
Secret scan: PASS
~~~

PR thay đổi cách xác định khách hàng được phép xem hóa đơn:

~~~java
public Invoice findInvoice(long invoiceId) {
    return invoiceRepository.findById(invoiceId)
            .orElseThrow(InvoiceNotFoundException::new);
}
~~~

Hàm có thể biên dịch, có test cho trường hợp hóa đơn tồn tại và không tồn tại, không có cảnh báo static analysis. Nhưng hợp đồng của endpoint yêu cầu **chỉ chủ sở hữu hóa đơn hoặc người có quyền quản trị mới được xem**.

Nếu controller gọi hàm này mà không kiểm tra quyền, một người dùng có thể thay invoiceId và đọc hóa đơn của người khác. Tất cả gate ở trên vẫn có thể PASS vì:

- Mã hợp lệ về cú pháp và kiểu.
- Test chỉ xác minh tìm thấy/không tìm thấy, chưa xác minh quyền.
- Coverage đạt ngưỡng nhưng thiếu test theo tenant.
- Scanner không được cấu hình hoặc không đủ ngữ cảnh để kết luận lỗi authorization này.

### 10.1. Reviewer phải hỏi gì?

1. Danh tính người gọi lấy từ đâu và có đáng tin không?
2. Hóa đơn thuộc tenant hoặc user nào?
3. Quyền quản trị được kiểm tra ở đâu?
4. Có đường gọi khác bỏ qua kiểm tra quyền không?
5. Khi không có quyền, API trả lỗi gì và có tiết lộ hóa đơn tồn tại không?
6. Test có xác minh user A không thể đọc hóa đơn của user B không?
7. Có kiểm tra quyền ở tầng service để các caller khác cũng được bảo vệ không?

Một hướng thiết kế minh họa:

~~~java
public Invoice findInvoice(
        long invoiceId, AuthenticatedUser actor) {
    Invoice invoice = invoiceRepository.findById(invoiceId)
            .orElseThrow(InvoiceNotFoundException::new);

    authorization.requireCanRead(actor, invoice);
    return invoice;
}
~~~

**AuthenticatedUser** và **authorization** là thành phần giả định của ví dụ. Đoạn này chỉ cho thấy quyền được xét trên tài nguyên đã tải; hệ thống thật cần tránh tiết lộ sự tồn tại tài nguyên theo chính sách, bảo vệ các đường gọi khác và cân nhắc truy vấn có điều kiện quyền ngay tại repository.

### 10.2. Test bổ sung phải kiểm tra quyền, không chỉ coverage

~~~java
@Test
void userCannotReadAnotherUsersInvoice() {
    var invoice = invoiceOwnedBy(userB);
    invoiceRepository.save(invoice);

    assertThrows(AccessDeniedException.class,
            () -> invoiceService.findInvoice(
                    invoice.id(), authenticatedAs(userA)));
}
~~~

Đây là pseudocode JUnit minh họa; các fixture và kiểu người dùng cần được định nghĩa theo dự án. Test cần xác minh **quyền sở hữu cụ thể**, không chỉ kiểm tra phương thức trả về một đối tượng.

Trường hợp này cho thấy **gate và review có hai vai trò bổ sung**: gate xác nhận những policy đã định nghĩa được thực thi; reviewer nhận ra policy quan trọng còn thiếu và yêu cầu bổ sung test/gate phù hợp nếu rủi ro lặp lại.

## 11. Thiết kế gate để hỗ trợ review thay vì tạo cảm giác an toàn giả

Một gate tốt cần **đáng tin, có phạm vi rõ, phản hồi đủ nhanh và có người sở hữu**. Nếu check không ổn định, không rõ lý do hoặc thường xuyên chặn nhầm, nhóm sẽ giảm niềm tin và tìm cách né nó.

### 11.1. Bắt đầu từ rủi ro, sau đó chọn check

Không nên bắt đầu bằng câu hỏi “công cụ có bao nhiêu rule?”. Hãy bắt đầu bằng:

1. Hệ thống có thể gây hậu quả gì nếu thay đổi sai?
2. Lỗi nào có thể phát hiện tự động với độ tin cậy phù hợp?
3. Check cần đầu vào nào và có bao phủ đúng module/artifact không?
4. Kết quả có đủ nhanh để phản hồi trước merge không?
5. Cần người nào đánh giá những điều công cụ không kết luận?

Ví dụ với một dịch vụ xử lý tiền:

| Rủi ro | Kiểm tra tự động phù hợp | Phán đoán review còn cần |
| --- | --- | --- |
| Sai ngưỡng tính phí | Unit test theo bảng giá trị biên | Bảng quyết định có đúng chính sách không? |
| Tràn số | Static rule và test số học | Giới hạn miền dữ liệu có đúng nghiệp vụ? |
| Thanh toán trùng | Test idempotency, integration test | Hợp đồng gateway và trạng thái không xác định có đủ? |
| Lộ dữ liệu tenant | Test quyền, static security analysis nếu phù hợp | Ranh giới trust và mọi đường gọi có được bảo vệ? |
| DB migration gây mất dữ liệu | Kiểm tra migration, integration test | Rollout, backfill và phục hồi có an toàn trên dữ liệu thật? |

### 11.2. Chia tầng phản hồi theo thời gian

Không phải check nào cũng cần chạy trong mỗi lần lưu tệp. Có thể tổ chức:

~~~text
Feedback nhanh trên PR
  - compile
  - unit tests
  - formatting / source rules
  - static analysis cần thiết
          |
          v
Kiểm tra mở rộng trước merge/release
  - integration / contract tests
  - dependency and configuration scans
  - artifact verification
          |
          v
Kiểm tra theo rủi ro triển khai
  - migration verification
  - smoke / canary
  - operational readiness
~~~

Đây là một cách tổ chức tham khảo. Security scan hoặc test tích hợp có thể phải chạy sớm hơn tùy rủi ro. Không được đẩy một check quan trọng ra sau merge chỉ để làm PR xanh nhanh hơn nếu thay đổi không thể được phát hành an toàn khi thiếu bằng chứng đó.

### 11.3. Check phải có người sở hữu

Mỗi gate nên có người hoặc nhóm chịu trách nhiệm:

- Định nghĩa ý nghĩa của rule và mức độ chặn.
- Cập nhật phiên bản công cụ và dữ liệu rule.
- Điều tra lỗi hạ tầng hoặc false positive.
- Xem xét phạm vi bỏ qua và suppression.
- Theo dõi thời gian chạy, tỷ lệ flaky và mức độ hữu ích.
- Thay đổi policy khi yêu cầu hệ thống thay đổi.

Một rule không có người sở hữu dễ trở thành **di sản cấu hình**: nhóm không biết vì sao nó tồn tại, ngại xóa và cũng không biết khi nào cần điều chỉnh.

## 12. Ví dụ cấu hình pipeline ở mức khái niệm

Ví dụ YAML sau mô tả các bước và điều kiện mong muốn, không phải cú pháp hoàn chỉnh cho GitHub Actions, GitLab CI, Jenkins hoặc một nền tảng cụ thể:

~~~yaml
quality:
  required:
    - compile
    - unit-tests
    - static-analysis
    - dependency-scan
    - artifact-verification

  policy:
    fail_on:
      new_critical_findings: true
      required_test_failure: true
      missing_artifact_provenance: true

    review:
      required_approvals: 1
      owner_review_for_sensitive_paths: true

  exceptions:
    require_reason: true
    require_approver: true
    record_commit_and_check: true
    require_follow_up: true
~~~

Mẫu này cho thấy có thể đặt **check tự động** và **yêu cầu approval** trong cùng một chính sách quản trị. Nhưng approval không phải kết quả mà scanner có thể tự đánh giá. Cần dùng cơ chế bảo vệ nhánh và phân quyền của nền tảng thực tế để thực thi.

### 12.1. Cổng phải kiểm tra đúng artifact

Một chuỗi build có thể:

1. Biên dịch source.
2. Chạy test và scanner.
3. Đóng gói JAR/container image.
4. Tải artifact lên registry.
5. Phát hành artifact đó.

Nếu bước 5 lấy một artifact khác với artifact đã qua bước 2 và 3, quality gate không bảo đảm artifact được phát hành đã được kiểm tra. Cần liên kết **commit, build ID, digest và artifact** theo mức phù hợp với quy trình.

### 12.2. Kết quả check phải có khả năng giải thích

Một thông báo “Gate failed” chung chung không giúp tác giả xử lý. Kết quả hữu ích nên chỉ ra:

- Check nào thất bại và phiên bản công cụ.
- Rule hoặc assertion nào không đạt.
- File, dòng, module hoặc artifact liên quan.
- Phạm vi quét và những gì bị loại trừ.
- Cách xem chi tiết và chủ sở hữu hỗ trợ.

Tương tự, một trạng thái PASS nên có thể truy vết **check đã chạy trên commit/artifact nào** và những policy nào đã được áp dụng.

## 13. Checklist cho tác giả và reviewer

### 13.1. Trước khi yêu cầu review

- [ ] PR nêu vấn đề, mục tiêu và phạm vi thay đổi.
- [ ] Tác giả đã tự đọc diff và bỏ các thay đổi không liên quan.
- [ ] Test có oracle theo hợp đồng, gồm biên và lỗi quan trọng.
- [ ] Những thay đổi API, schema hoặc dependency có kế hoạch tương thích.
- [ ] Các check bắt buộc đã chạy trên đúng commit.
- [ ] Kết quả FAIL, SKIPPED hoặc ngoại lệ được giải thích.
- [ ] Không có suppression hoặc bypass mới thiếu lý do.
- [ ] Có ghi rõ rủi ro rollout/rollback khi thay đổi ảnh hưởng vận hành.

### 13.2. Khi reviewer xem PR

- [ ] Gate đã hoàn tất và trạng thái có thể truy vết?
- [ ] Phạm vi module, source set, cấu hình và artifact đã đủ?
- [ ] PASS có phải do check thực sự chạy, hay có check bị skip/exclude?
- [ ] Hợp đồng và ý định nghiệp vụ có được giữ?
- [ ] Các test quan trọng kiểm tra kết quả hay chỉ tăng coverage?
- [ ] Có xem giá trị biên, lỗi, quyền, concurrency và side effect phù hợp?
- [ ] Cảnh báo bị suppression có bằng chứng và phạm vi hẹp?
- [ ] Thiết kế mới có dễ hiểu, dễ thay đổi và đặt đúng trách nhiệm?
- [ ] Có rủi ro mà gate chưa mô hình hóa cần ghi nhận hoặc bổ sung kiểm tra?
- [ ] Approval phản ánh việc đã xem xét thật, không chỉ dựa vào trạng thái CI?

### 13.3. Khi người duy trì thay đổi quality policy

- [ ] Rule mới gắn với một rủi ro hoặc yêu cầu cụ thể.
- [ ] Phạm vi include/exclude đã được kiểm chứng.
- [ ] Có thử nghiệm trên codebase đại diện trước khi bật chặn.
- [ ] False positive và chi phí chạy đã được đánh giá.
- [ ] Có thông báo, tài liệu và người hỗ trợ nhóm phát triển.
- [ ] Không vô tình bỏ qua module hoặc artifact cần bảo vệ.
- [ ] Ngoại lệ cũ được xem lại khi rule hoặc công cụ thay đổi.

## 14. Những hiểu nhầm thường gặp

**“Quality Gate PASS nghĩa là PR an toàn.”** PASS chỉ xác nhận các điều kiện đã cấu hình và thực sự chạy đều đạt. Nó không chứng minh mọi yêu cầu, rủi ro và bối cảnh đã được xem xét.

**“Có code review thì không cần quality gate.”** Con người dễ bỏ sót các kiểm tra lặp lại như build, test, dependency và rule bắt buộc. Gate giúp áp dụng chúng nhất quán.

**“Coverage đạt ngưỡng chứng minh test tốt.”** Coverage không đo trực tiếp oracle hoặc khả năng phát hiện lỗi. Test phải kiểm tra kết quả và các điều kiện quan trọng.

**“Static analysis không báo lỗi nghĩa là không có lỗ hổng.”** Công cụ chỉ phát hiện những gì rule và phạm vi của nó mô hình hóa. Thiếu check hoặc thiếu module không phải bằng chứng an toàn.

**“Gate xanh thì có thể tự động merge mọi PR.”** Một số thay đổi vẫn cần approval của người hiểu module, dữ liệu, bảo mật hoặc vận hành.

**“Cảnh báo nào cũng phải sửa ngay.”** Cần đánh giá khả năng áp dụng và mức rủi ro. False positive có thể được xử lý bằng bằng chứng và suppression hẹp theo quy trình.

**“Có thể bypass vì đang gấp.”** Bypass khẩn cấp cần quyền hạn, lý do, phạm vi, biện pháp giảm thiểu và hậu kiểm. Nếu không, ngoại lệ sẽ thành lối đi mặc định.

**“Thêm càng nhiều gate càng tốt.”** Gate không ổn định, chậm hoặc không liên quan làm giảm hiệu quả và niềm tin. Chọn check theo rủi ro và duy trì chất lượng của chính pipeline.

**“Người review chỉ cần xem các check đỏ.”** Check xanh vẫn không đánh giá được toàn bộ ngữ nghĩa, kiến trúc, quyền truy cập và hành vi lỗi. Reviewer cần xem thay đổi theo hợp đồng và bối cảnh.

**“Gate là trách nhiệm của đội DevOps.”** Người sở hữu pipeline quản lý cơ chế, nhưng nhóm phát triển và reviewer cùng chịu trách nhiệm về chất lượng thay đổi và việc sử dụng gate đúng cách.

## 15. Tình huống thực hành

Một PR thêm endpoint tải hóa đơn PDF cho khách hàng. CI báo:

~~~text
Compile: PASS
Unit tests: PASS
Line coverage: 86%
Static analysis: PASS
Dependency scan: PASS
Secret scan: PASS
Quality Gate: PASS
~~~

Diff chính:

~~~java
public byte[] downloadInvoice(long invoiceId) {
    Invoice invoice = invoiceRepository.findById(invoiceId)
            .orElseThrow(InvoiceNotFoundException::new);
    return pdfRenderer.render(invoice);
}
~~~

Nhóm có test cho hóa đơn tồn tại và không tồn tại. Tuy nhiên, chưa có test về người dùng thuộc tenant khác. API được gọi sau khi xác thực đăng nhập, nhưng đoạn service không thể hiện việc kiểm tra quyền.

### Câu hỏi

1. Gate đang cung cấp bằng chứng gì và điều gì chưa được xác minh?
2. Vì sao coverage 86% không chứng minh endpoint an toàn?
3. Reviewer cần lần theo hợp đồng nào giữa authentication, authorization, repository và controller?
4. Những test nào cần thêm để xác minh khách hàng không đọc hóa đơn của tenant khác?
5. Nếu một reviewer phát hiện vấn đề nhưng static analysis không cảnh báo, có nên bỏ qua vì gate đã PASS không?
6. Có nên thêm một rule hoặc test bắt buộc vào gate cho các endpoint truy cập dữ liệu nhạy cảm không? Điều kiện nào giúp rule đó có giá trị?
7. Nếu scan bảo mật bị SKIPPED do lỗi dịch vụ scanner, có thể coi PR đạt điều kiện bảo mật không?

### Gợi ý đối chiếu

- Gate chỉ cung cấp bằng chứng cho compile, test, coverage, static analysis, dependency scan và secret scan đã cấu hình. Nó chưa chứng minh quyền đọc hóa đơn theo tenant.
- Coverage phản ánh mức mã được thực thi, không chứng minh test đã dùng user/tenant khác nhau hoặc kiểm tra việc từ chối truy cập.
- Reviewer cần xác định ai là chủ sở hữu hóa đơn, quyền được kiểm tra ở tầng nào, mọi đường gọi service có được bảo vệ và phản hồi lỗi có làm lộ tài nguyên không.
- Cần test chủ sở hữu hợp lệ được tải, người dùng khác tenant bị từ chối, quyền quản trị theo đúng chính sách và nhánh tài nguyên không tồn tại.
- Không có cảnh báo scanner không làm mất trách nhiệm review. Nếu reviewer có bằng chứng về thiếu authorization, cần yêu cầu sửa hoặc làm rõ trước khi chấp thuận.
- Có thể bổ sung test quyền ở tầng service/integration vào CI vì đây là rủi ro lặp lại; rule static chỉ hữu ích nếu công cụ có thể mô hình hóa đúng cấu trúc quyền.
- Check bảo mật SKIPPED nghĩa là chưa có bằng chứng từ check đó. Nếu policy yêu cầu bắt buộc, cần khôi phục check hoặc đi qua quy trình risk acceptance có thẩm quyền, không tự coi là PASS.

## 16. Ghi nhớ

- **Quality gate** thực thi một tập điều kiện có thể kiểm tra và giúp áp dụng chính sách nhất quán; nó không đánh giá toàn bộ tính đúng, thiết kế hoặc rủi ro của thay đổi.
- **Code review** vẫn phải kiểm tra ý định, hợp đồng, ngữ nghĩa, giá trị biên, luồng lỗi, quyền truy cập, side effect và tác động kiến trúc.
- **PASS, FAIL, PENDING, SKIPPED và ERROR** có ý nghĩa khác nhau. Không có kết quả đáng tin cậy không thể được coi là đạt.
- Coverage, static analysis và số lượng cảnh báo là **tín hiệu có giới hạn**; cần xem oracle, phạm vi và chất lượng test.
- Gate phải gắn với đúng commit/artifact, có người sở hữu, phản hồi ổn định và ngoại lệ có dấu vết.
- Quy trình đáng tin cậy kết hợp **máy kiểm tra những điều có thể tự động hóa** với **con người chịu trách nhiệm cho phán đoán cần bối cảnh**.
