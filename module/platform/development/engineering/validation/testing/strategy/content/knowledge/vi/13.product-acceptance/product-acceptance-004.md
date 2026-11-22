# Chấp nhận sản phẩm: Phân biệt chấp nhận của người dùng với hoàn tất kiểm tra kỹ thuật

## 1. Vì sao hai quyết định này cần được phân biệt?

Một bản dựng có thể vượt qua toàn bộ kiểm thử tự động nhưng vẫn không giải quyết đúng công việc của người dùng. Ngược lại, một nhóm người dùng có thể đánh giá một luồng là hữu ích trong buổi thử nghiệm, trong khi sản phẩm vẫn còn lỗi nghiêm trọng về bảo mật, dữ liệu, hiệu năng hoặc khả năng phục hồi. Hai kết quả này trả lời hai câu hỏi khác nhau:

- **Hoàn tất kiểm tra kỹ thuật:** hệ thống đã đáp ứng các yêu cầu kỹ thuật và tiêu chí kiểm thử đã định nghĩa trong phạm vi, môi trường và phiên bản được xác nhận hay chưa?
- **Chấp nhận của người dùng hoặc nghiệp vụ:** sản phẩm có đáp ứng mục tiêu, quy trình làm việc và tiêu chí chấp nhận mà người dùng hoặc chủ sở hữu nghiệp vụ cần hay không?

Trong **VALIDATION_TESTING_STRATEGY**, cần giữ hai loại bằng chứng này riêng biệt nhưng liên kết với nhau. Kiểm tra kỹ thuật cung cấp bằng chứng về hành vi và thuộc tính của hệ thống. Chấp nhận sản phẩm đánh giá giá trị sử dụng và mức phù hợp với nhu cầu trong bối cảnh thực tế. Quyết định phát hành cần xem xét cả hai cùng các rủi ro còn lại.

Nếu đồng nhất hai khái niệm, nhóm có thể gặp các vấn đề:

- Báo cáo “tất cả test pass” bị hiểu nhầm là người dùng đã chấp nhận sản phẩm.
- Buổi demo thành công bị dùng thay cho bằng chứng về bảo mật, dữ liệu hoặc độ tin cậy.
- Người dùng được yêu cầu ký chấp nhận dù các lỗi kỹ thuật nghiêm trọng chưa được xử lý.
- Các tiêu chí nghiệp vụ quan trọng không được xác nhận vì nhóm chỉ theo dõi trạng thái pipeline.
- Trách nhiệm quyết định bị mờ: QA, phát triển, chủ sản phẩm và đại diện người dùng không biết ai có quyền chấp nhận điều gì.

## 2. Hai khái niệm và phạm vi của chúng

### 2.1. Hoàn tất kiểm tra kỹ thuật

Hoàn tất kiểm tra kỹ thuật là kết luận dựa trên các hoạt động verification và kiểm thử đã được lập kế hoạch. Nó xác nhận rằng phiên bản phần mềm cụ thể đáp ứng các tiêu chí kỹ thuật đã định nghĩa trong phạm vi kiểm tra.

Các hoạt động có thể bao gồm:

- Rà soát yêu cầu, thiết kế, mã nguồn và cấu hình.
- Kiểm thử đơn vị, thành phần, hợp đồng, tích hợp, hệ thống và E2E.
- Kiểm thử bảo mật, hiệu năng, khả năng phục hồi, tương thích và khả năng truy cập theo rủi ro.
- Kiểm tra migration, dữ liệu, quyền, cấu hình triển khai và rollback.
- Kiểm tra chất lượng artifact, dependency, pipeline và khả năng quan sát.

Kết quả kỹ thuật cần nêu rõ phiên bản, môi trường, phạm vi, tiêu chí, kết quả, ngoại lệ và rủi ro chưa được xác nhận. “Hoàn tất” chỉ có nghĩa các kiểm tra đã định nghĩa được thực hiện và đánh giá theo quy tắc đã thống nhất; nó không chứng minh không còn lỗi.

### 2.2. Chấp nhận của người dùng hoặc nghiệp vụ

Chấp nhận sản phẩm (product acceptance hoặc user acceptance) là đánh giá có chủ đích về việc sản phẩm có đáp ứng nhu cầu và tiêu chí chấp nhận trong bối cảnh sử dụng hay không. Người tham gia có thể là người dùng đại diện, chuyên gia nghiệp vụ, chủ sản phẩm hoặc người được ủy quyền quyết định.

Hoạt động chấp nhận thường xem xét:

- Người dùng có hoàn thành được công việc chính không?
- Quy trình có phù hợp chính sách và quy tắc nghiệp vụ không?
- Kết quả có chính xác, dễ hiểu và có thể sử dụng trong tình huống thực tế không?
- Các ngoại lệ thường gặp có được xử lý theo cách người dùng chấp nhận không?
- Sản phẩm có đáp ứng yêu cầu trải nghiệm, khả năng truy cập và vận hành liên quan không?
- Các giới hạn và rủi ro còn lại có được người có thẩm quyền hiểu và chấp nhận không?

Chấp nhận không nhất thiết chỉ là một buổi UAT thủ công. Nó có thể kết hợp thử nghiệm với người dùng, kiểm tra quy trình nghiệp vụ, dữ liệu đại diện, phản hồi có cấu trúc và bằng chứng từ các đợt pilot. Tuy nhiên, tiêu chí và người có quyền quyết định phải được xác định trước.

### 2.3. So sánh trực tiếp

| Khía cạnh | Hoàn tất kiểm tra kỹ thuật | Chấp nhận của người dùng/nghiệp vụ |
| --- | --- | --- |
| Câu hỏi chính | Hệ thống có đáp ứng đặc tả và tiêu chí kỹ thuật đã định nghĩa không? | Sản phẩm có đáp ứng nhu cầu và cách làm việc thực tế không? |
| Trọng tâm | Tính đúng đắn, tích hợp, bảo mật, hiệu năng, độ tin cậy và các thuộc tính kỹ thuật | Giá trị sử dụng, quy trình, kết quả nghiệp vụ và mức phù hợp |
| Người thực hiện | QA, kỹ sư kiểm thử, phát triển, bảo mật, vận hành | Người dùng đại diện, chủ sản phẩm, chuyên gia nghiệp vụ hoặc người được ủy quyền |
| Căn cứ | Test plan, test oracle, yêu cầu kỹ thuật, tiêu chuẩn và quality gate | Mục tiêu người dùng, acceptance criteria, quy trình và chính sách nghiệp vụ |
| Bằng chứng | Test report, log, trace, scan, kết quả đo và hồ sơ build | Kịch bản UAT, kết quả nhiệm vụ, phản hồi, quyết định nghiệp vụ và sign-off |
| Kết quả | Đạt, không đạt, chưa đủ bằng chứng hoặc có ngoại lệ | Chấp nhận, chấp nhận có điều kiện, từ chối hoặc cần đánh giá thêm |
| Người chịu trách nhiệm kết luận | Chủ sở hữu chất lượng kỹ thuật theo quy trình | Người có thẩm quyền chấp nhận sản phẩm hoặc nghiệp vụ |

Hai hoạt động có thể diễn ra song song hoặc theo các mốc khác nhau. Chúng cần dùng cùng phiên bản sản phẩm và cùng tiêu chí được truy vết, nhưng không thay thế quyết định của nhau.

## 3. Verification, validation và product acceptance

Ba khái niệm này có quan hệ gần nhau:

- **Verification:** kiểm tra sản phẩm có được xây dựng phù hợp với yêu cầu và đặc tả đã xác định không.
- **Validation:** đánh giá sản phẩm có đáp ứng nhu cầu và mục đích sử dụng trong bối cảnh dự kiến không.
- **Product acceptance:** quyết định có thẩm quyền rằng kết quả sản phẩm được chấp nhận theo tiêu chí và điều kiện đã thống nhất.

Verification thường cung cấp nhiều bằng chứng cho chất lượng kỹ thuật. Validation tập trung vào mức phù hợp với người dùng và nghiệp vụ. Product acceptance là quyết định dựa trên các bằng chứng này cùng mức rủi ro mà tổ chức sẵn sàng chấp nhận.

Ví dụ, một chức năng xuất báo cáo có thể:

1. Vượt qua kiểm thử API, kiểm tra định dạng file và kiểm thử quyền truy cập (verification).
2. Được nhân viên nghiệp vụ dùng để tạo báo cáo cuối ngày và xác nhận các cột, cách tính, quy trình xử lý ngoại lệ đáp ứng công việc (validation).
3. Được chủ sở hữu nghiệp vụ chấp nhận sau khi xem kết quả, các lỗi còn lại và giới hạn đã biết (product acceptance).

Một sản phẩm có thể đạt verification nhưng chưa đạt validation nếu đặc tả ban đầu chưa phản ánh đúng nhu cầu. Một sản phẩm có thể được người dùng đánh giá tích cực nhưng vẫn chưa đủ điều kiện phát hành nếu quality gate kỹ thuật bắt buộc chưa đạt.

## 4. Xác định tiêu chí chấp nhận trước khi thực hiện

### 4.1. Bắt đầu từ mục tiêu và nhiệm vụ của người dùng

Tiêu chí chấp nhận cần mô tả kết quả người dùng cần đạt, điều kiện sử dụng và mức chất lượng cần có. Trước khi thiết kế UAT, hãy làm rõ:

1. Nhóm người dùng nào sẽ sử dụng sản phẩm?
2. Họ cần hoàn thành nhiệm vụ nào và trong bối cảnh nào?
3. Kết quả nào chứng minh nhiệm vụ đã hoàn tất?
4. Quy tắc nghiệp vụ, chính sách và giới hạn nào áp dụng?
5. Những ngoại lệ nào thường xảy ra trong công việc?
6. Điều gì sẽ khiến người dùng không thể chấp nhận sản phẩm?
7. Ai có quyền xác nhận kết quả và ai chịu trách nhiệm cho rủi ro còn lại?

Tránh chỉ dùng mô tả tính năng như “có màn hình tạo báo cáo”. Người dùng cần tạo báo cáo nào, với dữ liệu gì, trong thời gian bao lâu, có thể xử lý sai lệch ra sao và kết quả được sử dụng cho quyết định nào mới là nội dung cần xác nhận.

### 4.2. Viết tiêu chí có thể quan sát

Một tiêu chí chấp nhận tốt cần:

- Mô tả hành vi hoặc kết quả có ý nghĩa với người dùng.
- Xác định vai trò, điều kiện và dữ liệu liên quan.
- Có cách quan sát để kết luận đạt hoặc không đạt.
- Bao gồm trường hợp lỗi hoặc ngoại lệ quan trọng.
- Dùng ngôn ngữ mà người dùng, nghiệp vụ và nhóm kỹ thuật cùng hiểu.
- Tránh từ mơ hồ như “nhanh”, “dễ dùng”, “chính xác” nếu chưa có cách đo hoặc ví dụ cụ thể.

Có thể sử dụng Given–When–Then:

~~~gherkin
Feature: Xem báo cáo doanh thu cuối ngày

  Scenario: Nhân viên kế toán xuất báo cáo trong phạm vi được cấp quyền
    Given nhân viên kế toán đã đăng nhập
      And dữ liệu doanh thu của ngày đã được chốt
    When nhân viên chọn ngày và yêu cầu xuất báo cáo
    Then báo cáo chứa các giao dịch thuộc ngày đã chọn
      And tổng doanh thu khớp với quy tắc tính đã thống nhất
      And nhân viên có thể tải và sử dụng báo cáo
~~~

Tiêu chí này có thể được xác nhận bằng kiểm thử dữ liệu và API, nhưng vẫn cần người dùng nghiệp vụ xem xét xem báo cáo có phù hợp với công việc và cách diễn giải số liệu hay không.

### 4.3. Phân biệt tiêu chí kỹ thuật và tiêu chí chấp nhận

| Tiêu chí kỹ thuật | Tiêu chí người dùng/nghiệp vụ |
| --- | --- |
| API trả đúng schema và mã trạng thái | Người dùng nhận được kết quả có thể hiểu và sử dụng |
| Độ trễ p95 nằm trong ngưỡng đã thống nhất | Nhiệm vụ hoàn tất trong thời gian phù hợp với quy trình làm việc |
| Không có lỗ hổng nghiêm trọng chưa xử lý | Người dùng chỉ truy cập được dữ liệu thuộc phạm vi quyền |
| Migration không làm mất dữ liệu và giữ tính toàn vẹn | Người dùng tìm thấy dữ liệu lịch sử cần thiết sau nâng cấp |
| Pipeline triển khai và rollback đạt kiểm tra | Nhóm vận hành có thể hỗ trợ quy trình và khôi phục khi cần |

Một tiêu chí có thể có cả hai mặt. Ví dụ, “người dùng hoàn tất đặt lịch trong thời hạn mục tiêu” cần đánh giá trải nghiệm và quy trình, trong khi phép đo latency, tỷ lệ lỗi và điều kiện tải cung cấp bằng chứng kỹ thuật bổ sung.

## 5. Thiết kế và tổ chức User Acceptance Testing (UAT)

### 5.1. Mục tiêu của UAT

UAT là hoạt động xác nhận sản phẩm có đáp ứng nhu cầu và tiêu chí chấp nhận từ góc nhìn người dùng hoặc nghiệp vụ hay không. UAT không phải buổi demo để xem tính năng có chạy được, cũng không phải cơ hội để người dùng tự tìm mọi lỗi kỹ thuật mà nhóm phát triển chưa kiểm tra.

UAT nên tập trung vào:

- Nhiệm vụ và hành trình thực tế.
- Vai trò và quyền của các nhóm người dùng.
- Quy tắc nghiệp vụ, dữ liệu và kết quả.
- Ngoại lệ ảnh hưởng đến công việc.
- Khả năng hiểu, sử dụng và tiếp tục quy trình.
- Những điểm phụ thuộc vào chính sách hoặc quyết định nghiệp vụ.

Kiểm thử kỹ thuật vẫn cần được thực hiện bởi nhóm phù hợp trước và trong quá trình UAT. Nếu một lỗi kỹ thuật làm cản trở việc đánh giá nghiệp vụ, cần ghi nhận lỗi và xác định có phải dừng kịch bản UAT hay không.

### 5.2. Chọn người tham gia

Người tham gia cần đại diện cho các nhóm sử dụng và quy trình quan trọng. Có thể gồm:

- Người dùng trực tiếp thực hiện nhiệm vụ hàng ngày.
- Người dùng có vai trò hoặc quyền khác nhau.
- Chuyên gia nghiệp vụ hiểu chính sách và trường hợp ngoại lệ.
- Chủ sản phẩm hoặc người được ủy quyền ra quyết định chấp nhận.
- Đại diện hỗ trợ/vận hành nếu sản phẩm ảnh hưởng đến quy trình hỗ trợ.

Không nên chỉ chọn người thiết kế sản phẩm hoặc thành viên nhóm phát triển làm đại diện cho mọi người dùng. Họ có thể hiểu cách hệ thống được xây dựng nhưng không phản ánh đầy đủ cách người dùng thực hiện công việc.

### 5.3. Chuẩn bị môi trường và dữ liệu UAT

Môi trường UAT nên đủ gần với điều kiện dự kiến sử dụng để người tham gia đánh giá đúng hành vi, nhưng vẫn được kiểm soát an toàn. Cần ghi:

- Phiên bản artifact và cấu hình đang thử nghiệm.
- Khác biệt đáng kể giữa UAT và production.
- Tài khoản, vai trò và quyền của người tham gia.
- Dữ liệu đại diện, nguồn dữ liệu và cách làm sạch/khử định danh.
- Hệ thống ngoài được mô phỏng, sandbox hay kết nối thật.
- Cách khởi tạo và reset dữ liệu giữa các phiên.
- Kênh ghi nhận phản hồi và báo lỗi.

Không dùng dữ liệu production nhạy cảm chỉ để làm cho UAT có vẻ thực tế. Hãy dùng dữ liệu tổng hợp hoặc đã được khử định danh, với quyền truy cập tối thiểu.

### 5.4. Thiết kế kịch bản UAT

Mỗi kịch bản nên có:

1. Mục tiêu nghiệp vụ.
2. Vai trò người dùng.
3. Điều kiện trước và dữ liệu cần thiết.
4. Các bước thực hiện theo quy trình thực tế.
5. Kết quả mong đợi và tiêu chí quan sát.
6. Cách ghi nhận kết quả và bằng chứng.
7. Cách xử lý khi kết quả không đạt.

Kịch bản nên dùng ngôn ngữ của công việc, không bắt người dùng thực hiện các thao tác kỹ thuật không thuộc nhiệm vụ của họ. Có thể cung cấp hướng dẫn ngắn, nhưng không nên dẫn dắt đến mức người tham gia chỉ làm theo từng cú nhấp mà không đánh giá được kết quả.

## 6. Bằng chứng và người có quyền chấp nhận

### 6.1. Các loại bằng chứng cần kết hợp

Một quyết định chấp nhận có thể dựa trên nhiều nguồn:

| Nguồn bằng chứng | Điều nó hỗ trợ đánh giá |
| --- | --- |
| Báo cáo kiểm thử kỹ thuật | Các tiêu chí kỹ thuật đã chạy, kết quả, phạm vi và lỗi còn lại |
| Kết quả UAT | Người dùng thực hiện nhiệm vụ và đánh giá kết quả theo tiêu chí |
| Dữ liệu đầu ra | Tính chính xác và đầy đủ của kết quả nghiệp vụ |
| Phản hồi người dùng | Khó khăn, mức phù hợp và các nhu cầu chưa được đáp ứng |
| Hồ sơ lỗi và ngoại lệ | Tác động, mức độ nghiêm trọng, trạng thái xử lý và biện pháp giảm thiểu |
| Bằng chứng vận hành | Khả năng giám sát, hỗ trợ, phục hồi và xử lý quy trình |
| Đánh giá tuân thủ hoặc bảo mật | Việc đáp ứng các yêu cầu bắt buộc có liên quan |

Bằng chứng phải gắn với phiên bản và môi trường cụ thể. Một kết quả UAT trên bản dựng cũ không tự động áp dụng cho bản dựng đã thay đổi. Nếu có thay đổi sau UAT, cần phân tích tác động và quyết định phần nào phải xác nhận lại.

### 6.2. Vai trò và quyền quyết định

| Vai trò | Trách nhiệm |
| --- | --- |
| Người dùng tham gia UAT | Thực hiện nhiệm vụ, ghi nhận kết quả và phản hồi theo trải nghiệm thực tế |
| Chuyên gia nghiệp vụ | Xác nhận quy tắc, dữ liệu và ngoại lệ có đáp ứng chính sách |
| QA / Test Lead | Cung cấp bằng chứng kỹ thuật, quản lý kịch bản, lỗi và phạm vi kiểm thử |
| Nhóm phát triển | Phân tích và khắc phục lỗi sản phẩm, cung cấp thông tin kỹ thuật |
| Vận hành / SRE | Xác nhận khả năng triển khai, giám sát, hỗ trợ và phục hồi trong phạm vi trách nhiệm |
| Chủ sản phẩm / người được ủy quyền | Ra quyết định chấp nhận nghiệp vụ theo thẩm quyền và rủi ro đã được trình bày |
| Người quyết định phát hành | Kết hợp trạng thái kỹ thuật, chấp nhận sản phẩm và các điều kiện phát hành |

Người tham gia UAT có thể xác nhận một nhiệm vụ cụ thể nhưng không nhất thiết có quyền chấp nhận toàn bộ sản phẩm. Quyền ký chấp nhận cần được tổ chức xác định trước, tránh việc một phản hồi tích cực không chính thức bị hiểu thành phê duyệt phát hành.

### 6.3. Phân biệt sign-off và quyết định phát hành

Sign-off của nghiệp vụ xác nhận sản phẩm đáp ứng các tiêu chí chấp nhận thuộc phạm vi người ký. Quyết định phát hành còn có thể cần xem xét quality gate kỹ thuật, bảo mật, vận hành, tuân thủ, lịch triển khai và rủi ro tổng thể.

Do đó:

- Sign-off nghiệp vụ không miễn trừ các kiểm soát kỹ thuật bắt buộc.
- Test report kỹ thuật đạt không thay thế sign-off nghiệp vụ khi quy trình yêu cầu.
- Người quyết định phát hành cần nhìn thấy cả hai kết quả và các ngoại lệ.
- Nếu một bên chưa chấp nhận, phải ghi rõ lý do, tác động và quyết định tiếp theo.

## 7. Các kết quả chấp nhận có thể có

Không nên chỉ có hai trạng thái “pass” và “fail” cho toàn bộ hoạt động. Có thể sử dụng các kết quả:

| Kết quả | Ý nghĩa | Điều kiện và hành động |
| --- | --- | --- |
| Chấp nhận (Accepted) | Các tiêu chí chấp nhận trong phạm vi đã đạt | Lưu bằng chứng, người phê duyệt và phiên bản được chấp nhận |
| Chấp nhận có điều kiện (Conditionally accepted) | Có giới hạn hoặc lỗi còn lại nhưng người có thẩm quyền chấp nhận với điều kiện rõ | Ghi rủi ro, biện pháp giảm thiểu, chủ sở hữu và thời hạn xử lý |
| Từ chối (Rejected) | Một hoặc nhiều tiêu chí quan trọng không đạt hoặc rủi ro không được chấp nhận | Ghi lý do, yêu cầu khắc phục và phạm vi cần kiểm tra lại |
| Chưa đủ bằng chứng (Pending / Inconclusive) | Chưa thể kết luận do thiếu dữ liệu, người tham gia, môi trường hoặc kết quả | Bổ sung bằng chứng và lên lịch đánh giá lại |

Chấp nhận có điều kiện không nên được dùng để hợp thức hóa lỗi nghiêm trọng hoặc yêu cầu bắt buộc chưa đáp ứng. Các ràng buộc pháp lý, bảo mật, an toàn hoặc chính sách tổ chức có thể không cho phép miễn trừ.

### 7.1. Quản lý lỗi trong UAT

Khi người dùng báo một vấn đề, cần phân loại:

- Lỗi sản phẩm: hành vi không đáp ứng tiêu chí hoặc gây sai lệch.
- Yêu cầu chưa rõ: kỳ vọng chưa được thống nhất hoặc tiêu chí thiếu.
- Yêu cầu thay đổi: nhu cầu mới nằm ngoài phạm vi đã thống nhất.
- Vấn đề dữ liệu hoặc môi trường: điều kiện thử nghiệm không đúng.
- Vấn đề sử dụng: người dùng không hiểu hoặc khó hoàn thành quy trình.

Không tự động xem mọi phản hồi là defect, cũng không bác bỏ phản hồi chỉ vì test tự động đã pass. Cần xem xét bằng chứng, mục tiêu và bối cảnh sử dụng để quyết định có phải lỗi, khoảng trống yêu cầu hay thay đổi phạm vi.

### 7.2. Đánh giá lỗi còn lại theo tác động

Một danh sách lỗi cần thể hiện:

- Mô tả và bước tái hiện.
- Nhóm người dùng hoặc hành trình bị ảnh hưởng.
- Mức độ nghiêm trọng và tần suất dự kiến.
- Tiêu chí chấp nhận liên quan.
- Biện pháp tạm thời hoặc phương án giảm thiểu.
- Chủ sở hữu khắc phục và thời hạn.
- Người có thẩm quyền chấp nhận rủi ro nếu tiếp tục.

Không dùng số lượng lỗi đóng để thay cho đánh giá tác động. Một lỗi đơn lẻ trong luồng thanh toán hoặc phân quyền có thể nghiêm trọng hơn nhiều lỗi giao diện nhỏ.

## 8. Ví dụ: chấp nhận nghiệp vụ và hoàn tất kỹ thuật cho quy trình đặt lịch

Giả sử sản phẩm cho phép người dùng chọn khung giờ, thanh toán và nhận xác nhận đặt lịch.

### 8.1. Bằng chứng kỹ thuật

Nhóm kỹ thuật xác nhận:

- API kiểm tra quyền và dữ liệu đầu vào đúng.
- Quy tắc ngăn hai người đặt cùng một khung giờ hoạt động.
- Callback thanh toán lặp không tạo giao dịch trùng.
- Timeout và trạng thái chưa xác định được xử lý theo hợp đồng.
- Lịch và giao dịch được liên kết đúng trong trạng thái cuối.
- Các kịch bản lỗi, hiệu năng và bảo mật trọng yếu đạt ngưỡng.
- Log, trace và cảnh báo đủ để vận hành điều tra.

Kết quả này cho biết phiên bản đã đáp ứng các kiểm tra kỹ thuật trong phạm vi đã chạy.

### 8.2. Bằng chứng chấp nhận người dùng/nghiệp vụ

Người dùng đại diện và chuyên gia nghiệp vụ thực hiện các nhiệm vụ:

- Tìm dịch vụ và chọn khung giờ phù hợp.
- Hiểu được thời điểm khung giờ được giữ.
- Hoàn tất thanh toán hoặc nhận hướng dẫn khi thanh toán chưa có kết quả cuối.
- Tra cứu lịch đã đặt và hiểu trạng thái.
- Hủy hoặc đổi lịch theo chính sách.
- Xử lý trường hợp khung giờ vừa được người khác đặt.

Họ đánh giá kết quả có phù hợp quy trình, thông tin có đủ rõ để ra quyết định và các ngoại lệ có thể xử lý được hay không.

### 8.3. Bảng quyết định

| Kết quả kỹ thuật | Kết quả UAT | Cách diễn giải |
| --- | --- | --- |
| Đạt | Đạt | Có bằng chứng kỹ thuật và nghiệp vụ; tiếp tục xem xét các điều kiện phát hành còn lại |
| Đạt | Không đạt | Hệ thống có thể đúng theo đặc tả nhưng đặc tả hoặc trải nghiệm chưa đáp ứng nhu cầu; cần làm rõ và điều chỉnh |
| Không đạt | Đạt | Người dùng có thể thích trải nghiệm nhưng còn khoảng trống kỹ thuật; xử lý các gate bắt buộc trước quyết định phát hành |
| Không đạt | Không đạt | Chưa có cơ sở chấp nhận; khắc phục và xác nhận lại |
| Chưa đủ bằng chứng | Bất kỳ | Chưa kết luận được phạm vi liên quan; bổ sung kiểm tra hoặc phiên UAT cần thiết |

### 8.4. Ví dụ chấp nhận có điều kiện

Giả sử UAT xác nhận luồng đặt lịch đáp ứng quy trình, nhưng một báo cáo phụ trợ có lỗi căn lề không ảnh hưởng đến số liệu hoặc khả năng sử dụng. Chủ nghiệp vụ có thể chấp nhận có điều kiện nếu:

- Lỗi không vi phạm tiêu chí bắt buộc hoặc quy định.
- Phạm vi người dùng và tác động đã được xác định.
- Có cách làm việc tạm thời nếu cần.
- Có người chịu trách nhiệm và thời hạn sửa.
- Người có thẩm quyền đã ghi nhận quyết định.

Nếu lỗi làm sai số tiền, cho phép truy cập lịch của người khác hoặc làm mất lịch đã thanh toán, không thể xem đây là lỗi trình bày nhỏ để chấp nhận theo cùng cách. Mức độ tác động và chính sách bắt buộc quyết định khả năng chấp nhận.

## 9. Quản lý thay đổi sau khi đã chấp nhận

Chấp nhận gắn với một phiên bản, cấu hình, phạm vi và tập tiêu chí cụ thể. Nếu có thay đổi sau sign-off, nhóm cần đánh giá lại:

1. Mã nguồn, cấu hình hoặc dependency có thay đổi không?
2. Thay đổi có ảnh hưởng hành trình hoặc tiêu chí đã được chấp nhận không?
3. Bằng chứng kỹ thuật nào cần chạy lại?
4. Người dùng có cần xác nhận lại một phần UAT không?
5. Các điều kiện chấp nhận có điều kiện còn hiệu lực không?
6. Có rủi ro mới hoặc thay đổi mức độ rủi ro không?

Không phải mọi sửa lỗi nhỏ đều yêu cầu chạy lại toàn bộ UAT. Phân tích tác động có thể xác định phần cần xác nhận lại, nhưng thay đổi ảnh hưởng đến hành vi người dùng, quy tắc nghiệp vụ hoặc dữ liệu cần được xem xét bởi chủ sở hữu tương ứng.

### 9.1. Duy trì dấu vết quyết định

Hồ sơ chấp nhận nên ghi:

- Tên sản phẩm, phiên bản và artifact.
- Môi trường, cấu hình và dữ liệu UAT.
- Tiêu chí đã đánh giá và kết quả từng tiêu chí.
- Người tham gia, vai trò và người có thẩm quyền ký.
- Lỗi, ngoại lệ và rủi ro còn lại.
- Điều kiện chấp nhận, biện pháp giảm thiểu và thời hạn.
- Ngày quyết định và điều kiện phải đánh giá lại.

Hồ sơ này giúp nhóm hiểu tại sao một phiên bản được chấp nhận và phạm vi quyết định có hiệu lực.

## 10. Mẫu kế hoạch và biên bản chấp nhận sản phẩm

### 10.1. Mẫu kế hoạch UAT

~~~text
Sản phẩm / tính năng:
Phiên bản / artifact:
Mục tiêu chấp nhận:
Nhóm người dùng đại diện:
Người có thẩm quyền quyết định:

Phạm vi quy trình:
Ngoài phạm vi:
Tiêu chí chấp nhận:
Các tình huống chính và ngoại lệ:

Môi trường và cấu hình:
Dữ liệu và tài khoản:
Phụ thuộc / sandbox:
Điều kiện bắt đầu:

Kịch bản UAT:
Nguồn bằng chứng:
Cách ghi nhận lỗi và phản hồi:
Điều kiện kết thúc:
Lịch và người hỗ trợ:
~~~

### 10.2. Mẫu biên bản quyết định

~~~text
Sản phẩm / tính năng:
Phiên bản được đánh giá:
Ngày đánh giá:
Phạm vi đã thực hiện:

Kết quả kiểm tra kỹ thuật:
- Phạm vi và tiêu chí:
- Kết quả:
- Lỗi / ngoại lệ còn lại:

Kết quả UAT / nghiệp vụ:
- Nhóm người dùng tham gia:
- Nhiệm vụ đã thực hiện:
- Tiêu chí đạt / không đạt:
- Phản hồi chính:

Rủi ro còn lại:
Biện pháp giảm thiểu:
Chủ sở hữu và thời hạn:

Quyết định:
  [ ] Accepted
  [ ] Conditionally accepted
  [ ] Rejected
  [ ] Pending / Inconclusive

Người có thẩm quyền:
Điều kiện hoặc lý do:
Điều kiện đánh giá lại:
~~~

Mẫu cần được điều chỉnh theo quy trình tổ chức. Không ghi nhận chữ ký hoặc quyết định thay cho người có thẩm quyền.

## 11. Checklist phân biệt chấp nhận sản phẩm và hoàn tất kỹ thuật

- [ ] Tiêu chí kỹ thuật và tiêu chí người dùng/nghiệp vụ được xác định riêng.
- [ ] Mỗi tiêu chí có cách quan sát và bằng chứng phù hợp.
- [ ] Phạm vi, phiên bản và môi trường được ghi nhận cho cả kiểm thử kỹ thuật và UAT.
- [ ] Người tham gia UAT đại diện cho nhóm người dùng và quy trình quan trọng.
- [ ] Người có quyền quyết định chấp nhận được xác định trước.
- [ ] UAT đánh giá nhiệm vụ và kết quả nghiệp vụ, không chỉ xem demo.
- [ ] Các lỗi và phản hồi được phân loại theo nguyên nhân và tác động.
- [ ] Lỗi nghiêm trọng và kiểm soát bắt buộc được xử lý theo quality gate.
- [ ] Chấp nhận có điều kiện có lý do, biện pháp giảm thiểu, chủ sở hữu và thời hạn.
- [ ] Sign-off nghiệp vụ và quyết định phát hành được ghi nhận riêng.
- [ ] Thay đổi sau sign-off được đánh giá tác động và xác định phạm vi kiểm tra lại.
- [ ] Hồ sơ quyết định có thể truy vết tới phiên bản và bằng chứng cụ thể.

Hoàn tất kiểm tra kỹ thuật cho biết hệ thống đã đáp ứng các kiểm tra được định nghĩa; chấp nhận của người dùng cho biết sản phẩm phù hợp với nhu cầu và quy trình được đại diện đánh giá. Khi hai kết quả được ghi nhận riêng, liên kết bằng chứng và đặt đúng người chịu trách nhiệm, tổ chức có thể đưa ra quyết định phát hành minh bạch và có căn cứ hơn.
