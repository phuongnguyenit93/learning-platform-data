# Assess

## 1. Assess nhằm đưa ra kết luận gì?

Trong quản lý rủi ro và tuân thủ, **Assess** là hoạt động đánh giá có hệ thống để xác định các yêu cầu và kiểm soát bảo mật đã được triển khai đúng, vận hành như dự kiến và tạo ra kết quả bảo vệ cần thiết hay chưa. Kết luận phải dựa trên bằng chứng, có phạm vi, thời điểm và mức độ tin cậy rõ ràng.

Đối với thiết kế yêu cầu bảo mật, Assess nối ba lớp thông tin:

1. **Mục tiêu và rủi ro:** cần bảo vệ tài sản nào trước kịch bản đe dọa nào?
2. **Yêu cầu và cách triển khai:** hệ thống phải đáp ứng điều kiện gì, bằng những kiểm soát nào?
3. **Bằng chứng và quyết định:** quan sát thực tế cho thấy điều gì, còn thiếu gì và ai cần hành động?

Ví dụ, “ngăn người dùng tenant A đọc dữ liệu tenant B” là một mục tiêu bảo mật. Để đánh giá được, cần chuyển nó thành yêu cầu cụ thể về phân quyền tại API, tác vụ nền và điểm tải dữ liệu. Sau đó phải kiểm tra các đường truy cập đó bằng danh tính và dữ liệu thử nghiệm phù hợp.

Một báo cáo quét không phát hiện lỗ hổng chưa đủ chứng minh yêu cầu được đáp ứng. Ngược lại, một lỗi kỹ thuật cần được đặt trong bối cảnh tài sản, khả năng khai thác, tác động và kiểm soát đang hoạt động để đánh giá rủi ro.

Kết quả Assess hỗ trợ quyết định phát hành, cho phép vận hành, khắc phục hoặc chấp nhận rủi ro theo thẩm quyền. Việc hoàn thành đánh giá không tự cấp quyền chấp nhận mọi rủi ro còn lại.

Bài học sử dụng một dịch vụ quản lý hồ sơ đa tenant làm ví dụ. Mã yêu cầu, trạng thái, ngưỡng thời gian và quy tắc ưu tiên trong bài là quy ước minh họa cho hệ thống giả định, cần được điều chỉnh trước khi áp dụng vào một tổ chức cụ thể.

## 2. Phân biệt các đối tượng đánh giá

Cùng một hệ thống có thể có nhiều hoạt động được gọi chung là “đánh giá bảo mật”. Cần xác định rõ câu hỏi của từng hoạt động để tránh kết luận quá phạm vi.

| Đối tượng | Câu hỏi chính | Sản phẩm đầu ra |
| --- | --- | --- |
| Đặc tả yêu cầu | Yêu cầu có rõ, phù hợp rủi ro và có thể kiểm chứng không? | Yêu cầu được làm rõ, tiêu chí chấp nhận |
| Thiết kế kiểm soát | Cách thiết kế có thể đáp ứng yêu cầu và các ranh giới tin cậy không? | Nhận xét kiến trúc, khoảng trống thiết kế |
| Triển khai kiểm soát | Mã, cấu hình và quy trình có thực hiện đúng thiết kế không? | Kết quả kiểm tra và phát hiện |
| Vận hành kiểm soát | Kiểm soát có hoạt động trong thời gian và phạm vi cần thiết không? | Bằng chứng vận hành, sai lệch và độ bao phủ |
| Rủi ro | Khoảng trống hiện tại có thể gây hậu quả gì trong bối cảnh nghiệp vụ? | Rủi ro hiện tại, mức ưu tiên, bất định |
| Tuân thủ | Các nghĩa vụ đã xác định là áp dụng được đáp ứng đến đâu? | Ma trận nghĩa vụ, yêu cầu, bằng chứng và khoảng trống |

Các hoạt động liên hệ với nhau nhưng có sản phẩm khác nhau. Một tài liệu thiết kế mô tả kiểm tra quyền không chứng minh mã đã thực hiện kiểm tra đó. Một kiểm thử thành công tại một thời điểm cũng chưa chứng minh quy trình xét duyệt quyền đã được vận hành đều đặn trong nhiều tháng.

Trong bài này, trọng tâm Assess là **đánh giá yêu cầu và hiệu lực của kiểm soát**, sau đó chuyển kết quả thành thông tin phục vụ quản lý rủi ro và tuân thủ.

### Ba lớp cần kiểm tra

**Thiết kế:** kiểm soát có đủ khả năng xử lý kịch bản đe dọa không? Ví dụ, thiết kế có kiểm tra quyền khi xử lý tác vụ nền hay chỉ ở API tạo tác vụ?

**Triển khai:** kiểm soát có xuất hiện đúng nơi, đúng cấu hình và đúng phạm vi không? Ví dụ, worker có thực sự dùng định danh tenant đã xác minh thay vì tin tham số do bên gọi cung cấp?

**Hiệu lực vận hành:** kiểm soát có thực hiện được chức năng trong điều kiện thực tế đã xác định không? Ví dụ, khi thay đổi quyền hoặc khi dịch vụ phụ thuộc lỗi, đường tải kết quả còn giữ đúng ranh giới tenant không?

Một lớp chưa có bằng chứng phải được ghi nhận riêng. Không dùng kết quả của lớp khác để lấp chỗ trống.

## 3. Xác định đầu vào, phạm vi và trách nhiệm

### 3.1. Đầu vào tối thiểu

Trước khi thực hiện đánh giá, cần có hoặc cần xác nhận các thông tin sau:

- Mục tiêu an toàn thông tin và tài sản nghiệp vụ cần bảo vệ.
- Ranh giới hệ thống, luồng dữ liệu, thành phần và dịch vụ phụ thuộc.
- Mô hình đe dọa, danh sách rủi ro và giả định quan trọng.
- Yêu cầu bảo mật có định danh, phiên bản và tiêu chí chấp nhận.
- Mô tả kiểm soát, cấu hình có hiệu lực và trách nhiệm triển khai.
- Các nghĩa vụ tuân thủ đã được xác định là áp dụng.
- Bằng chứng cũ, ngoại lệ còn hiệu lực, phát hiện chưa đóng và thay đổi kể từ lần đánh giá trước.
- Phiên bản ứng dụng, môi trường, dữ liệu thử nghiệm và quyền truy cập cần thiết.

Thiếu đầu vào không nhất thiết khiến mọi hoạt động phải dừng. Có thể tiếp tục phần độc lập, đồng thời ghi rõ giới hạn. Tuy nhiên, nếu không xác định được tiêu chí chấp nhận cho một yêu cầu, người đánh giá chưa thể đưa ra kết luận đạt yêu cầu đó.

Ví dụ, “phục hồi đủ nhanh” cần được làm rõ thành mục tiêu thời gian, điểm bắt đầu, điều kiện kết thúc và phạm vi dữ liệu trước khi chạy diễn tập.

### 3.2. Phạm vi phải đủ cụ thể

Một phạm vi đánh giá cần nêu:

| Thuộc tính | Ví dụ minh họa |
| --- | --- |
| Hệ thống và luồng nghiệp vụ | Tạo hồ sơ, tìm hồ sơ, tạo export, tải export |
| Thành phần | API, worker, kho tệp, dịch vụ danh tính, hệ thống audit log |
| Môi trường | Môi trường đánh giá có cấu hình bảo mật tương ứng với sản xuất |
| Bản triển khai | Build ứng dụng, phiên bản cấu hình và chính sách quyền xác định |
| Danh tính | Người dùng, quản trị tenant, quản trị hệ thống, danh tính dịch vụ |
| Dữ liệu | Dữ liệu tổng hợp của tenant A và B |
| Khoảng thời gian | Kiểm tra tại một mốc hoặc quan sát vận hành trong một khoảng đã nêu |
| Loại trừ | Thành phần ngoài phạm vi, lý do và ảnh hưởng đến kết luận |

Nếu đánh giá trên môi trường thử nghiệm, phải xác định mức tương đồng với sản xuất. Khác biệt về phân quyền, mạng, secret, logging hoặc cách triển khai có thể làm kết quả không đại diện cho hệ thống vận hành.

Không nên dùng tên môi trường làm bằng chứng tương đồng. Cần đối chiếu các thuộc tính liên quan đến yêu cầu đang đánh giá.

### 3.3. Trách nhiệm và tính độc lập

| Vai trò | Trách nhiệm điển hình |
| --- | --- |
| Chủ sở hữu nghiệp vụ hoặc rủi ro | Xác định tác động và quyết định xử lý rủi ro trong thẩm quyền |
| Chủ sở hữu hệ thống | Cung cấp phạm vi, nguồn lực, triển khai và kế hoạch khắc phục |
| Người sở hữu yêu cầu | Làm rõ mục tiêu, tiêu chí chấp nhận và quan hệ với rủi ro |
| Nhóm phát triển và vận hành | Giải thích triển khai, hỗ trợ thu thập bằng chứng, sửa lỗi |
| Người đánh giá | Lập và thực hiện thủ tục đánh giá, ghi nhận bằng chứng, kết luận trong phạm vi |
| Người phụ trách tuân thủ | Xác nhận nghĩa vụ áp dụng và cách liên kết bằng chứng |
| Người có thẩm quyền quyết định | Xem xét báo cáo, giới hạn đánh giá và rủi ro còn lại trước quyết định |

Mức độc lập cần phù hợp với rủi ro và quy tắc quản trị của tổ chức. Hoạt động tự kiểm tra của nhóm triển khai có giá trị, nhưng các kết luận trọng yếu có thể cần người khác rà soát hoặc đánh giá độc lập.

Tính độc lập không chỉ nằm ở tên phòng ban. Cần xem ai chọn mẫu, ai kiểm soát bằng chứng, ai có thể thay đổi kết quả và có xung đột lợi ích nào ảnh hưởng đến kết luận.

## 4. Lập kế hoạch đánh giá trước khi kiểm thử

Một kế hoạch đánh giá biến mục tiêu chung thành các thủ tục có thể thực hiện và lặp lại.

### 4.1. Nội dung của kế hoạch

1. **Mục tiêu và phạm vi:** yêu cầu, tài sản, hệ thống, môi trường và thời gian.
2. **Đối tượng đánh giá:** thiết kế, mã, cấu hình, quy trình và hành vi vận hành.
3. **Tiêu chí:** điều kiện đạt, nguồn của tiêu chí và quy tắc xử lý ngoại lệ.
4. **Phương pháp:** xem xét tài liệu, phỏng vấn, kiểm thử và quan sát.
5. **Độ sâu và độ bao phủ:** kiểm tra những đường nào, mẫu nào và vì sao.
6. **Điều kiện thực hiện:** quyền truy cập, dữ liệu tổng hợp, giới hạn tải và phụ thuộc.
7. **Bằng chứng:** cần thu gì, định dạng, nơi lưu, phân quyền và thời hạn lưu.
8. **Vai trò:** ai thực hiện, ai hỗ trợ, ai xử lý trở ngại và ai nhận kết quả.
9. **Điều kiện dừng hoặc đổi phương án:** ví dụ khi phép thử gây tác động ngoài phạm vi đã thống nhất.
10. **Quy tắc kết luận và báo cáo:** cách biểu diễn đạt, không đạt, thiếu bằng chứng và chưa đánh giá.

Các giới hạn thực hiện phải cụ thể theo môi trường. Ví dụ, diễn tập phục hồi cần được thực hiện trên phạm vi dữ liệu và hạ tầng đã xác định, có cách xác nhận kết thúc. Không biến một tiêu đề “kiểm thử bảo mật” thành quyền thử mọi hành vi trên mọi tài nguyên.

### 4.2. Thống nhất tiêu chí trước khi biết kết quả

Giả sử một yêu cầu quy định quyền tải export phải được kiểm tra tại thời điểm tải. Sau khi phát hiện một đường tải không kiểm tra quyền, không thể sửa tiêu chí thành “đã kiểm tra quyền lúc tạo export” chỉ để đổi kết quả.

Nếu yêu cầu thật sự cần thay đổi, phải đi qua quy trình quản lý thay đổi: xác định rủi ro, người phê duyệt, phiên bản yêu cầu và ảnh hưởng tới kết luận cũ. Phát hiện trên yêu cầu ban đầu vẫn cần được lưu để giữ khả năng truy vết.

### 4.3. Ví dụ kế hoạch rút gọn

~~~yaml
assessmentId: ASM-EXPORT-01
scope:
  businessFlow: export-and-download
  environment: verification
  applicationBuild: app-build-208
  configurationVersion: cfg-1042
  policyVersion: access-policy-12
requirements:
  - SR-AUTHZ-01
  - SR-LOG-01
methods:
  - examine
  - interview
  - test
testData:
  tenants:
    - tenant-a-synthetic
    - tenant-b-synthetic
evidence:
  include:
    - test-steps
    - sanitized-http-observations
    - authorization-decisions
    - audit-events
  exclude:
    - live-credentials
    - production-personal-data
~~~

Đây là kế hoạch minh họa cho một luồng nghiệp vụ. Danh sách phương pháp chưa thay thế các thủ tục chi tiết, tiêu chí chấp nhận hoặc quy tắc bảo vệ bằng chứng.

## 5. Chuyển yêu cầu thành mục tiêu và thủ tục đánh giá

### 5.1. Chuỗi truy vết

~~~mermaid
flowchart TD
    A["Mục tiêu bảo vệ tài sản"] --> B["Kịch bản đe dọa và rủi ro"]
    B --> C["Yêu cầu bảo mật"]
    C --> D["Kiểm soát trong kiến trúc"]
    D --> E["Mục tiêu đánh giá"]
    E --> F["Thủ tục và ca kiểm thử"]
    F --> G["Bằng chứng thực tế"]
    G --> H["Kết luận và phát hiện"]
    H --> I["Rủi ro hiện tại và kế hoạch xử lý"]
    I --> C
~~~

Một mục tiêu đánh giá nên diễn đạt điều cần xác định, chẳng hạn:

> Xác định rằng mọi đường tải export kiểm tra danh tính, quyền thao tác và phạm vi tenant ở phía máy chủ trước khi trả dữ liệu.

Từ mục tiêu này, người đánh giá cần liệt kê API chính, đường tải trực tiếp qua kho tệp, liên kết đã phát hành trước đó và các đường thay thế thực sự tồn tại trong thiết kế. Không tự thêm đường giả định rồi báo lỗi; cũng không chỉ kiểm tra màn hình người dùng nhìn thấy.

### 5.2. Ma trận yêu cầu, kiểm soát và bằng chứng

| Yêu cầu minh họa | Kiểm soát dự kiến | Mục tiêu đánh giá | Bằng chứng trọng tâm |
| --- | --- | --- | --- |
| SR-AUTHN-01: thao tác quản trị nhạy cảm cần xác minh bổ sung theo chính sách | Cơ chế xác thực và kiểm tra mức xác minh tại API | Thao tác bị từ chối khi danh tính chưa đáp ứng mức xác minh yêu cầu | Cấu hình, ca đạt/từ chối, sự kiện xác thực |
| SR-AUTHZ-01: chỉ người có quyền trong tenant sở hữu được tạo, xử lý và tải export | Phân quyền ở API, worker và điểm tải | Ranh giới tenant được duy trì trên từng đường và thời điểm đã đặc tả | Quan sát request, quyết định quyền, dữ liệu trả về |
| SR-DATA-01: secret không xuất hiện trong đầu ra chẩn đoán thuộc phạm vi | Tham chiếu secret, che dữ liệu, hạn chế endpoint | Các đường xuất dữ liệu được xác định không làm lộ secret thử nghiệm | Cấu hình, kiểm thử lỗi, log đã xử lý |
| SR-LOG-01: thao tác thay đổi quyền quản trị có sự kiện truy vết được | Audit event và đường chuyển log | Sự kiện chứa chủ thể, mục tiêu, kết quả, thời điểm và liên kết yêu cầu | Sự kiện nguồn, sự kiện tại nơi lưu, ca lỗi đường gửi |
| SR-REC-01: phục hồi dữ liệu đáp ứng mục tiêu đã duyệt | Sao lưu, bản sao phục hồi và quy trình restore | Phục hồi được dữ liệu và chức năng trong điều kiện diễn tập xác định | Báo cáo diễn tập, dấu thời gian, kiểm tra dữ liệu và quyền |

Một yêu cầu có thể cần nhiều kiểm soát. Chẳng hạn, ranh giới tenant có thể phụ thuộc cả xác thực danh tính, phân quyền ứng dụng, truy vấn dữ liệu và cơ chế cấp liên kết tải.

Ngược lại, một kiểm soát có thể phục vụ nhiều yêu cầu. Khi kiểm soát chung thất bại, phải rà soát các yêu cầu phụ thuộc thay vì chỉ tạo một phát hiện trong báo cáo của thành phần phát hiện lỗi đầu tiên.

### 5.3. Yêu cầu chưa kiểm chứng được cũng là kết quả quan trọng

Ví dụ “audit log phải đầy đủ” còn thiếu:

- Sự kiện nào bắt buộc?
- Trường nào phải có?
- Khi nào sự kiện phải được ghi nhận?
- Đầy đủ trên những kênh thao tác nào?
- Hành vi khi đường ghi log bị lỗi là gì?

Trước khi kiểm thử, cần làm rõ tiêu chí cùng người sở hữu yêu cầu. Nếu chưa thống nhất được, ghi nhận khoảng trống đặc tả và giới hạn đánh giá. Không tự đặt một ngưỡng rồi báo hệ thống tuân thủ toàn bộ yêu cầu ban đầu.
## 6. Chọn phương pháp: xem xét, phỏng vấn và kiểm thử

### 6.1. Xem xét đối tượng và tài liệu

Xem xét giúp xác định thiết kế, quy tắc và cách triển khai dự kiến. Đối tượng có thể gồm mô hình kiến trúc, đặc tả yêu cầu, mã kiểm soát quyền, cấu hình có hiệu lực, quy trình quản trị và bản ghi vận hành.

Cần xác nhận:

- Tài liệu hoặc artifact thuộc phiên bản nào?
- Đối tượng đó có nằm trong bản triển khai được đánh giá không?
- Nó mô tả trạng thái mong muốn hay trạng thái đang hoạt động?
- Có điểm ghi đè, cơ chế kế thừa hoặc đường bỏ qua nào?
- Bằng chứng có liên hệ trực tiếp với tiêu chí đang xét không?

Ví dụ, một policy trong repository có thể cấm truy cập chéo tenant, nhưng cần đối chiếu bản policy được runtime nạp và những luồng thực sự gọi cơ chế quyết định quyền.

### 6.2. Phỏng vấn người thực hiện và người chịu trách nhiệm

Phỏng vấn giúp hiểu cách vận hành, xác định giả định và tìm bằng chứng cần kiểm tra.

Những câu hỏi có ích:

- Ai có quyền thay đổi kiểm soát?
- Khi hệ thống phụ thuộc lỗi, quy trình xử lý ra sao?
- Ai kiểm tra phát hiện và theo dõi khắc phục?
- Lần gần nhất quy trình được thực hiện là khi nào?
- Có trường hợp ngoại lệ nào được sử dụng?
- Có thể chỉ ra bản ghi của một trường hợp thực tế trong phạm vi đánh giá không?

Lời giải thích cần được đối chiếu với bằng chứng. Phỏng vấn cho biết “nhóm kiểm tra quyền mỗi tháng” chưa đủ để kết luận hoạt động đó đã được thực hiện trong khoảng thời gian cần đánh giá.

Nếu lời giải thích và bản ghi mâu thuẫn, cần ghi nhận mâu thuẫn, làm rõ nguyên nhân và hạn chế kết luận cho đến khi có cơ sở.

### 6.3. Kiểm thử và quan sát hành vi

Kiểm thử kiểm tra kết quả khi thực hiện một hành động hoặc tạo một điều kiện có kiểm soát.

Một bộ thủ tục thường cần:

- **Ca được phép:** hành vi hợp lệ hoạt động đúng, tránh nhầm việc chặn mọi thứ là kiểm soát hiệu quả.
- **Ca không được phép:** yêu cầu sai quyền, sai tenant hoặc không đáp ứng điều kiện bảo mật bị từ chối.
- **Ca biên:** giá trị giới hạn, thay đổi trạng thái quyền, tài nguyên mới tạo hoặc vừa bị xóa.
- **Ca lỗi phụ thuộc:** dịch vụ quyền, nguồn cấu hình hoặc đường ghi log không sẵn sàng.
- **Ca chuyển trạng thái:** triển khai, đổi quyền, xoay secret, phục hồi và hết hạn ngoại lệ.

Kết quả cần quan sát đúng điều kiện bảo mật. Với yêu cầu bảo mật dữ liệu, chỉ thấy giao diện báo lỗi chưa chứng minh API không trả dữ liệu trong response, log hoặc đường tải khác.

Ngược lại, chỉ dựa vào mã HTTP thành công cũng chưa chứng minh đã lộ dữ liệu; phải xác nhận nội dung thực tế và quyền của danh tính thực hiện.

### 6.4. Kiểm soát kế thừa hoặc dùng chung

Một dịch vụ có thể dựa vào nền tảng chung để xác thực, mã hóa, logging hoặc sao lưu. Có bằng chứng của nền tảng chưa đủ để bỏ qua trách nhiệm tích hợp của dịch vụ.

Cần phân tách:

| Phần trách nhiệm | Ví dụ |
| --- | --- |
| Nền tảng thực hiện | Cung cấp cơ chế xác minh danh tính và công bố thuộc tính đã xác minh |
| Dịch vụ cấu hình | Chọn bên phát hành, đối tượng nhận và chính sách được chấp nhận |
| Dịch vụ thực thi | Dùng đúng danh tính để kiểm tra quyền trên tài nguyên |
| Hai bên phối hợp | Xử lý thay đổi, lỗi phụ thuộc và thông tin sự kiện |

Bằng chứng kế thừa phải phù hợp với dịch vụ, phiên bản, môi trường và thời gian đang xét. Những điều kiện sử dụng hoặc trách nhiệm phía dịch vụ chưa được đáp ứng phải được ghi nhận rõ.

## 7. Độ sâu, độ bao phủ và chọn mẫu

### 7.1. Ba khái niệm khác nhau

**Độ sâu** cho biết kiểm tra kỹ đến mức nào: chỉ đọc mô tả, đối chiếu cấu hình, xem logic thực thi hay thực hiện thử nghiệm có lỗi phụ thuộc.

**Độ bao phủ** cho biết đã kiểm tra những đối tượng nào trong tổng thể: API, vai trò, instance, tenant, sự kiện hoặc lần vận hành.

**Chọn mẫu** là cách chọn một phần tổng thể để đánh giá khi không thể kiểm tra hết.

Tăng số request trên cùng một đường API không tự tăng độ bao phủ sang worker hoặc kho tệp. Tăng số tài liệu được đọc cũng không thay thế bằng chứng hành vi.

### 7.2. Lập tổng thể trước khi chọn mẫu

Với yêu cầu phân quyền export, các chiều cần xem có thể gồm:

| Chiều | Các phần tử minh họa |
| --- | --- |
| Điểm thực thi | API tạo tác vụ, worker xử lý, API tải, liên kết tải qua kho tệp |
| Danh tính | Người dùng thường, quản trị tenant, danh tính dịch vụ |
| Quan hệ tài nguyên | Cùng tenant có quyền, cùng tenant thiếu quyền, khác tenant |
| Trạng thái | Đang có quyền, vừa bị thu hồi quyền, tài nguyên đã xóa |
| Điều kiện phụ thuộc | Hoạt động bình thường, dịch vụ quyền lỗi, cache chưa cập nhật |
| Bản triển khai | Các phiên bản đang cùng phục vụ trong giai đoạn chuyển tiếp |

Các phần tử chỉ áp dụng nếu chúng thực sự tồn tại và thuộc phạm vi yêu cầu. Người đánh giá cần ghi rõ tổng thể, cách chọn và những tổ hợp chưa kiểm tra.

Không nhất thiết phải thử mọi tổ hợp của mọi chiều. Có thể dùng thiết kế mẫu theo rủi ro, ưu tiên các đường nhạy cảm và các cách triển khai khác nhau. Tuy nhiên, một tập mẫu được chọn có chủ đích không tự mang ý nghĩa đại diện thống kê.

Nếu muốn suy luận thống kê, cần thiết kế lấy mẫu và giả định phù hợp. Không thể kiểm tra một vài tài khoản thuận tiện rồi báo một tỷ lệ tin cậy cho toàn hệ thống.

### 7.3. Kiểm soát điểm thời gian và kiểm soát theo kỳ

Một thử nghiệm đăng nhập tại thời điểm đánh giá có thể hỗ trợ kết luận về hành vi đăng nhập ở thời điểm đó.

Để đánh giá quy trình rà soát quyền theo kỳ, cần bằng chứng của các lần thực hiện thuộc khoảng thời gian đã chọn, gồm người thực hiện, phạm vi, quyết định và hành động theo sau. Một biên bản được tạo vào ngày đánh giá chưa chứng minh quy trình đã được vận hành đều đặn trước đó.

Phạm vi thời gian cần xuất hiện trong kết luận. Nếu chỉ kiểm tra một đợt triển khai hoặc một mẫu vận hành, không mở rộng lời kết luận thành “kiểm soát luôn hoạt động”.

### 7.4. Thủ tục kiểm thử có thể lặp lại

Ví dụ cho yêu cầu SR-AUTHZ-01:

~~~gherkin
Feature: Export isolation between tenants

  Scenario: An authorized user downloads an export in their tenant
    Given user A belongs to synthetic tenant A
    And user A has export download permission
    And export EA belongs to tenant A
    When user A requests the download of EA
    Then the service returns the expected synthetic content

  Scenario: A user cannot download another tenant's export
    Given user A belongs to synthetic tenant A
    And export EB belongs to synthetic tenant B
    When user A requests the download of EB
    Then the service denies access according to the API contract
    And no content from EB is returned

  Scenario: The authorization dependency is unavailable
    Given user A requests an export that requires an authorization decision
    And no valid decision can be obtained under the defined cache policy
    When the authorization dependency is unavailable
    Then the service does not release the export using an unverified decision
    And the operational signal required by policy is produced
~~~

Thủ tục cần bổ sung cách thiết lập fixture, danh tính, đường API thực tế, điều kiện cache, mã tương quan và nguồn bằng chứng. Không nên dựa vào việc người chạy nhớ các bước chưa được ghi.

Nếu yêu cầu có thời hạn thu hồi quyền, phải thêm ca thay đổi quyền và đo đúng giới hạn đó. Kết quả của ca sai tenant không chứng minh việc thu hồi quyền diễn ra đúng hạn.

## 8. Thu thập và quản lý bằng chứng

### 8.1. Bằng chứng cần đủ thuộc tính

Một bằng chứng hữu ích phải có:

1. **Liên quan:** trực tiếp hỗ trợ mục tiêu đánh giá.
2. **Xác định được nguồn:** biết nó đến từ thành phần và môi trường nào.
3. **Gắn phiên bản:** đối chiếu được ứng dụng, cấu hình và policy đã kiểm tra.
4. **Có thời gian:** xác định thời điểm hoặc khoảng quan sát.
5. **Có tính toàn vẹn:** phát hiện được thay đổi ngoài quy trình được phép.
6. **Có thể kiểm tra lại:** người khác hiểu cách tạo và diễn giải bằng chứng.
7. **Được bảo vệ:** quyền truy cập và dữ liệu nhạy cảm được xử lý phù hợp.

Một ảnh chụp màn hình thiếu đường dẫn, môi trường và thời gian thường có giá trị hạn chế. Một log đầy đủ kỹ thuật nhưng không chỉ ra danh tính hay tài nguyên đang xét cũng có thể không đủ để kết luận yêu cầu phân quyền.

### 8.2. Mẫu bản ghi bằng chứng

~~~yaml
evidenceId: EV-AUTHZ-014
assessmentId: ASM-EXPORT-01
requirementId: SR-AUTHZ-01
procedureId: PROC-DOWNLOAD-CROSS-TENANT
applicationBuild: app-build-208
configurationVersion: cfg-1042
policyVersion: access-policy-12
environment: verification
subject:
  identityAlias: user-a-synthetic
  tenantAlias: tenant-a-synthetic
target:
  objectAlias: export-b-synthetic
  owningTenantAlias: tenant-b-synthetic
expected:
  decision: deny
  targetContentReturned: false
observed:
  decision: allow
  targetContentReturned: true
testResult: FAILED
artifactRefs:
  - evidence://asm-export-01/request-observation
  - evidence://asm-export-01/fixture-comparison
  - evidence://asm-export-01/authorization-trace
~~~

Các giá trị là dữ liệu giả. Bản ghi chỉ ra kết quả kiểm thử, còn mức rủi ro và phạm vi ảnh hưởng phải được đánh giá ở bước tiếp theo.

Nếu một công cụ ghi nhận `decision: allow` bằng cách suy ra từ response, phải mô tả rõ đó là suy luận của công cụ. Không gán kết quả đó cho hệ thống quyết định quyền khi chưa có trace tương ứng.

### 8.3. Bảo vệ dữ liệu và tính toàn vẹn

Nên ưu tiên dữ liệu tổng hợp và danh tính thử nghiệm riêng. Trước khi lưu request, response hoặc log, cần loại bỏ giá trị xác thực, secret và dữ liệu không cần thiết cho kết luận.

Khi che dữ liệu, vẫn phải giữ được mối liên hệ cần thiết: cùng người dùng, cùng tài nguyên và cùng lần gọi. Có thể dùng alias ổn định trong phạm vi hồ sơ đánh giá.

Digest có thể hỗ trợ phát hiện artifact bị sửa, nhưng không tự chứng minh nguồn tạo, tính đúng đắn hoặc việc phê duyệt artifact. Cần kết hợp quyền truy cập, nguồn thu thập và lịch sử thao tác.

Không công bố digest của secret như một cách chứng minh secret được bảo vệ. Giá trị dễ dự đoán có thể bị thử đoán bằng cách tính digest và so sánh. Nên dùng định danh phiên bản không nhạy cảm theo phạm vi được phép.

### 8.4. Bằng chứng hết tính đại diện

Bằng chứng có thể mất tính đại diện khi thay đổi:

- Logic xác thực hoặc phân quyền.
- Nguồn cấu hình, thứ tự ghi đè hoặc baseline.
- Thành phần xử lý dữ liệu và đường truyền dữ liệu.
- Mô hình tenant, vai trò hoặc quyền quản trị.
- Nhà cung cấp hoặc điều kiện tích hợp kiểm soát dùng chung.
- Schema, secret, cơ chế sao lưu hoặc cách phục hồi.
- Phạm vi nghĩa vụ và giả định rủi ro.

Không có một thời hạn hiệu lực chung cho mọi bằng chứng. Cần dựa vào loại kiểm soát, nhịp thay đổi và yêu cầu áp dụng. Khi tái sử dụng bằng chứng cũ, phải ghi rõ vì sao nó còn phù hợp với đối tượng hiện tại.

## 9. Kết luận đánh giá và ghi nhận phát hiện

### 9.1. Phân biệt kết quả kiểm thử với kết luận yêu cầu

Một ca kiểm thử có thể đạt nhưng yêu cầu chưa đủ bằng chứng vì còn các đường chưa được kiểm tra. Ngược lại, một ca bị chặn do môi trường lỗi chưa tự chứng minh kiểm soát bị lỗi.

Quy ước minh họa cho kết luận yêu cầu:

| Trạng thái | Ý nghĩa |
| --- | --- |
| MET | Bằng chứng đủ để xác định yêu cầu được đáp ứng trong phạm vi và thời gian đã nêu |
| NOT_MET | Có bằng chứng xác định một hoặc nhiều điều kiện bắt buộc không được đáp ứng |
| PARTIALLY_MET | Một số tiêu chí được đáp ứng, một số không; phải chỉ rõ từng phần |
| INCONCLUSIVE | Đã đánh giá nhưng bằng chứng thiếu hoặc mâu thuẫn, chưa đủ kết luận |
| NOT_ASSESSED | Chưa thực hiện đánh giá theo kế hoạch |
| NOT_APPLICABLE | Có căn cứ được xác nhận rằng yêu cầu không áp dụng cho đối tượng này |

Với yêu cầu gồm nhiều tiêu chí bắt buộc, một phần không đạt vẫn khiến yêu cầu chưa đáp ứng đầy đủ. Trạng thái PARTIALLY_MET giúp trình bày chi tiết, không phải điều kiện tự động cho phép phát hành.

Không dùng NOT_APPLICABLE cho một kiểm soát khó kiểm tra, chưa triển khai hoặc chưa có ngân sách. Căn cứ không áp dụng phải gắn với phạm vi, đặc tính hệ thống và nguồn yêu cầu.

Quy tắc tổng hợp trạng thái phải được xác định trước. Nếu cần kết quả nhị phân cho một cổng phát hành, phải nêu cách xử lý các trạng thái chưa đáp ứng đầy đủ hoặc chưa kết luận được.

### 9.2. Một phát hiện cần những thành phần nào?

Một phát hiện nên gồm:

- Mã định danh và tiêu đề mô tả điều kiện quan sát được.
- Yêu cầu, tiêu chí và kiểm soát bị ảnh hưởng.
- Đối tượng, môi trường, phiên bản và thời điểm.
- Điều kiện xảy ra, bước tái hiện và bằng chứng.
- Kết quả mong đợi so với kết quả thực tế.
- Phạm vi đã xác nhận và phần ảnh hưởng còn cần kiểm tra.
- Kịch bản rủi ro, tác động và giả định.
- Nguyên nhân đã xác minh hoặc giả thuyết cần điều tra.
- Chủ sở hữu, cách xử lý, thời hạn và tiêu chí kiểm tra lại.

Tránh viết một phát hiện chỉ có câu “phân quyền yếu”. Câu đó không cho biết đường nào, dữ liệu nào, danh tính nào hoặc điều kiện nào đã thất bại.

### 9.3. Ví dụ phát hiện F-01

**Tiêu đề:** API tải export trả dữ liệu tổng hợp của tenant B cho người dùng tenant A.

**Tiêu chí:** SR-AUTHZ-01 yêu cầu kiểm tra quyền và tenant sở hữu tại điểm tải.

**Phạm vi đã xác nhận:** môi trường verification, build app-build-208, cấu hình cfg-1042, đường tải export được kiểm tra bằng hai tenant tổng hợp.

**Quan sát:** người dùng A nhận được nội dung fixture của export B qua đường tải được đánh giá, dù danh tính A không có quyền trên tenant B.

**Bằng chứng:** EV-AUTHZ-014 và các artifact liên quan.

**Kết luận:** NOT_MET đối với tiêu chí kiểm soát tải chéo tenant. Các đường tạo và xử lý tác vụ có kết quả riêng.

**Kịch bản rủi ro:** một người dùng được xác thực có thể truy cập export ngoài tenant nếu tìm được hoặc nhận được định danh hay đường tải tương ứng.

**Phần chưa xác nhận:** khả năng suy đoán định danh, phạm vi các loại export khác và mức tương đồng của cấu hình sản xuất.

**Nguyên nhân:** chưa kết luận cho đến khi đối chiếu logic thực thi và các đường tích hợp. Việc chưa thấy một sự kiện từ chối không đủ chứng minh chính xác nguyên nhân mã nguồn.

**Tiêu chí đóng:** đường tải và các đường tương tự trong phạm vi đều kiểm tra tenant và quyền đúng yêu cầu; ca hợp lệ vẫn hoạt động; kết quả kiểm tra lại gắn với bản sửa xác định.

Viết rõ phạm vi đã xác nhận giúp giữ độ chính xác. Không cần khẳng định “mọi dữ liệu sản xuất đã bị lộ” để giải thích rằng một khoảng trống phân quyền cần được xử lý ưu tiên.
## 10. Chuyển phát hiện thành đánh giá rủi ro

### 10.1. Viết kịch bản trước khi chọn mức

Một phát hiện kỹ thuật cần được diễn giải bằng kịch bản:

> Chủ thể nào có thể thực hiện hành động gì, qua điểm yếu nào, ảnh hưởng tài sản nào, dưới điều kiện nào và gây hậu quả gì?

Với F-01:

- **Chủ thể:** người dùng đã có tài khoản hợp lệ trong một tenant.
- **Điều kiện:** có được định danh hoặc đường tải export thuộc tenant khác.
- **Khoảng trống:** điểm tải không thực thi đầy đủ điều kiện quyền và tenant.
- **Tài sản:** dữ liệu nằm trong export.
- **Hậu quả:** truy cập trái phép dữ liệu ngoài phạm vi được cấp quyền.
- **Kiểm soát liên quan:** xác thực, phân quyền, cơ chế cấp đường tải, giới hạn truy cập và giám sát.

Có thể xác nhận một đường bypass trong môi trường thử nghiệm mà vẫn chưa biết tần suất khai thác ngoài thực tế. Hai thông tin này cần được trình bày riêng.

### 10.2. Khả năng xảy ra, tác động và bất định

Khả năng xảy ra cần xét điều kiện truy cập, mức phổ biến của danh tính cần thiết, độ khó đạt điều kiện khai thác, mức lộ diện và kiểm soát đang hoạt động.

Tác động cần xét loại dữ liệu, quy mô tài nguyên ảnh hưởng, chức năng nghiệp vụ, khả năng khôi phục và các nghĩa vụ liên quan đã được xác định.

Ví dụ một ma trận định tính nội bộ:

| Khả năng xảy ra \ Tác động | Thấp | Vừa | Cao |
| --- | --- | --- | --- |
| Thấp | Thấp | Thấp | Vừa |
| Vừa | Thấp | Vừa | Cao |
| Cao | Vừa | Cao | Rất cao |

Ma trận chỉ hữu ích khi các mức có định nghĩa và ví dụ phù hợp với tổ chức. Những nhãn này không phải xác suất hoặc giá trị tổn thất tiền tệ.

Không nên tự gán “khả năng 80%” chỉ vì một ca kiểm thử thành công. Thử nghiệm có điều kiện cho biết hành vi tồn tại trong điều kiện đó; ước lượng xác suất ngoài thực tế cần dữ liệu và mô hình khác.

Báo cáo nên kèm **mức độ tin cậy của nhận định**:

| Nhận định | Cơ sở | Mức tin cậy minh họa |
| --- | --- | --- |
| Đường tải đã kiểm tra trả dữ liệu chéo tenant | Tái hiện được, có fixture và quan sát đầy đủ | Cao |
| Các đường tải khác có cùng lỗi | Chưa rà soát đủ | Chưa đủ cơ sở |
| Sản xuất có cùng hành vi | Cần đối chiếu build, cấu hình và tích hợp | Phụ thuộc bằng chứng tương đồng |
| Sự cố đã xảy ra với người dùng thật | Chưa có bằng chứng điều tra | Chưa kết luận |

Bất định phải được ghi nhận và xử lý bằng thu thập thông tin, giới hạn phạm vi hoặc quyết định có điều kiện. Thiếu thông tin không phải lý do tự động hạ mức rủi ro.

### 10.3. Phân biệt rủi ro vốn có, hiện tại và mục tiêu

**Rủi ro vốn có** là rủi ro được xét trong bối cảnh chưa tính các kiểm soát giảm thiểu đã quy định trong phương pháp.

**Rủi ro hiện tại hoặc còn lại** xét các kiểm soát đang thực sự được triển khai và có bằng chứng hiệu lực tại thời điểm đánh giá.

**Rủi ro mục tiêu** là mức dự kiến sau khi thực hiện phương án xử lý. Nó chưa phải kết quả đã đạt.

Ví dụ, nhóm phát triển dự kiến thêm kiểm tra tenant tại điểm tải. Trước khi triển khai và kiểm tra lại, không thể ghi nhận rủi ro hiện tại đã giảm chỉ vì công việc được đưa vào kế hoạch.

Một kiểm soát phát hiện như cảnh báo truy cập bất thường có thể giúp phát hiện hoặc giảm thời gian sự cố. Nó không tự tương đương với kiểm soát ngăn trả dữ liệu sai tenant. Nếu dùng làm kiểm soát bù, phải đánh giá tác dụng thực tế đối với kịch bản rủi ro.

### 10.4. Mức độ lỗi khác với mức rủi ro nghiệp vụ

Mức độ nghiêm trọng kỹ thuật mô tả đặc tính của điểm yếu. Mức rủi ro nghiệp vụ còn phụ thuộc tài sản, điều kiện tiếp cận, quy mô, kiểm soát và hệ quả đối với tổ chức.

Không nên cộng các mức rủi ro định tính hoặc lấy trung bình để kết luận một hệ thống “an toàn”. Một khoảng trống trọng yếu có thể quyết định việc phát hành dù nhiều yêu cầu khác đã đạt.

Các thang đo dùng cho ưu tiên phải được công bố cùng quy tắc quyết định. Khi có nhiều bên tham gia, cần giải thích vì sao một phát hiện được ưu tiên thay vì chỉ đưa ra một con số.

## 11. Liên kết với compliance mà vẫn giữ đúng ý nghĩa bằng chứng

### 11.1. Lập ma trận nghĩa vụ

Đầu vào compliance cần xác định nguồn nghĩa vụ, đối tượng áp dụng, nội dung cần đáp ứng và người chịu trách nhiệm xác nhận. Nguồn có thể là chính sách nội bộ, hợp đồng hoặc yêu cầu bên ngoài đã được tổ chức xác định là áp dụng.

Không cần mỗi nghĩa vụ có một kiểm soát riêng. Có thể dùng quan hệ nhiều-nhiều:

| Nghĩa vụ minh họa | Yêu cầu triển khai | Bằng chứng | Kết luận cần ghi |
| --- | --- | --- | --- |
| POL-ACCESS-01: giới hạn dữ liệu theo phạm vi được cấp quyền | SR-AUTHZ-01 | Kiểm thử các điểm thực thi quyền | Điều kiện nào đạt, điều kiện nào chưa đạt |
| POL-TRACE-02: truy vết thay đổi quyền quản trị | SR-LOG-01 | Sự kiện, cấu hình và kiểm tra đường gửi | Kênh nào đã bao phủ và khoảng thời gian nào |
| POL-RECOVERY-03: chứng minh khả năng phục hồi theo mục tiêu đã duyệt | SR-REC-01 | Diễn tập restore và kiểm tra kết quả | Mục tiêu nào được đo, điều kiện nào còn thiếu |

Các mã POL là chính sách nội bộ giả định cho ví dụ, không đại diện cho một điều khoản pháp lý hoặc tiêu chuẩn bên ngoài.

Nếu tính áp dụng của một nghĩa vụ chưa được xác nhận, phải ghi nhận việc cần làm rõ với chủ thể có trách nhiệm. Không suy ra nghĩa vụ chỉ từ tên công nghệ hoặc tên ngành nghề.

### 11.2. Đánh giá sự phù hợp và đánh giá rủi ro có thể cho kết quả khác nhau

Một tổ chức có thể đã thực hiện đúng quy trình rà soát quyền nhưng vẫn còn rủi ro trong một luồng export mới chưa được mô hình hóa.

Ngược lại, một kiểm soát kỹ thuật có thể giảm rủi ro hiệu quả nhưng chưa tạo được hồ sơ hoặc cách phê duyệt mà một nghĩa vụ áp dụng yêu cầu.

Vì vậy, báo cáo cần trình bày cả:

- Khoảng trống so với yêu cầu hoặc nghĩa vụ áp dụng.
- Kịch bản và mức rủi ro còn lại.
- Bằng chứng và giới hạn của từng nhận định.
- Hành động khắc phục hoặc quyết định cần thực hiện.

Không dùng một tỷ lệ chung như “95% yêu cầu đạt” để thay thế phân tích các khoảng trống trọng yếu. Nếu báo cáo tỷ lệ, cần công bố mẫu số, cách xử lý không áp dụng, chưa đánh giá và trọng số nếu có.

Một đánh giá nội bộ cũng không tự mang ý nghĩa chứng nhận từ một bên có thẩm quyền khác. Phạm vi và giá trị của báo cáo phải được diễn đạt đúng với hoạt động đã thực hiện.

## 12. Kế hoạch khắc phục, kiểm tra lại và chấp nhận rủi ro

### 12.1. Chuyển phát hiện thành công việc có thể đóng

| Trường | Ví dụ cho F-01 |
| --- | --- |
| Chủ sở hữu | Nhóm chịu trách nhiệm API export |
| Hành động | Kiểm tra tenant và quyền tại điểm tải, rà soát đường tải tương tự |
| Phụ thuộc | Danh tính và metadata chủ sở hữu export được cung cấp đáng tin |
| Tiêu chí hoàn thành | Ca hợp lệ đạt; ca chéo tenant và thiếu quyền bị từ chối; không trả nội dung ngoài quyền |
| Kiểm tra lại | Thực hiện trên build và cấu hình chứa bản sửa |
| Bằng chứng | Quan sát request, fixture, quyết định quyền và sự kiện liên quan |
| Thời hạn | Được quyết định theo mức rủi ro và quy tắc quản trị |
| Rủi ro trong thời gian chờ | Ghi rõ điều kiện hạn chế luồng hoặc kiểm soát bù đang áp dụng |

“Đã merge bản sửa” chưa đủ để đóng phát hiện đối với hệ thống đang chạy. Cần xác nhận bản sửa đã đến đúng đối tượng trong phạm vi quyết định và được kiểm tra lại.

Nếu báo cáo chỉ đánh giá artifact trước triển khai, có thể đóng phần phát hiện thuộc artifact theo quy tắc đã nêu. Tuy nhiên, kết luận đó vẫn khác với việc xác nhận sản xuất đã được khắc phục.

### 12.2. Kiểm tra lại có trọng tâm

Một lần kiểm tra lại cần bao phủ:

1. Điều kiện từng gây lỗi.
2. Các đường có cùng cơ chế hoặc nguyên nhân đã xác định.
3. Ca hợp lệ để phát hiện việc sửa lỗi bằng cách chặn mọi truy cập.
4. Các điều kiện lỗi phụ thuộc có thể làm xuất hiện lại khoảng trống.
5. Bằng chứng gắn với phiên bản và môi trường chứa bản sửa.

Không nhất thiết chạy lại toàn bộ mọi đánh giá nếu thay đổi có phạm vi hẹp và phân tích tác động đủ rõ. Ngược lại, nếu sửa cơ chế phân quyền dùng chung, chỉ kiểm tra lại một endpoint là chưa đủ để đánh giá tác động rộng hơn.

Kết quả mới phải liên kết với kết quả cũ và giữ lịch sử. Không xóa phát hiện ban đầu chỉ vì lần thử sau đã thành công.

### 12.3. Chấp nhận rủi ro cần một quyết định riêng

Khi chưa thể khắc phục ngay, chủ thể có thẩm quyền có thể xem xét phương án xử lý theo quy tắc của tổ chức. Hồ sơ cần nêu:

- Rủi ro và yêu cầu chưa đáp ứng.
- Phạm vi hệ thống, dữ liệu, môi trường và phiên bản liên quan.
- Kiểm soát bù đang có và bằng chứng hiệu lực.
- Lý do, người quyết định và căn cứ thẩm quyền.
- Thời hạn, điều kiện hết hiệu lực và mốc đánh giá lại.
- Người chịu trách nhiệm theo dõi và kế hoạch xử lý tiếp.

Chấp nhận rủi ro không biến NOT_MET thành MET. Trạng thái kỹ thuật của yêu cầu và trạng thái quyết định rủi ro cần được lưu riêng.

Ví dụ, một phát hiện có thể vẫn chưa khắc phục, trong khi một quyết định cho phép vận hành có điều kiện còn hiệu lực. Khi điều kiện thay đổi hoặc quyết định hết hạn, phải xem xét lại; không để ngoại lệ tự trở thành trạng thái vĩnh viễn.

### 12.4. Khi nào phát hiện được coi là đóng?

Có thể phân biệt các trạng thái xử lý:

- **Open:** đã xác nhận, chưa có hoặc chưa hoàn thành phương án.
- **Remediating:** đang thực hiện phương án.
- **Ready for retest:** đã có bản sửa và đủ điều kiện kiểm tra lại.
- **Closed — verified:** bằng chứng mới chứng minh tiêu chí đóng được đáp ứng.
- **Risk accepted:** có quyết định rủi ro hợp lệ; không đồng nghĩa đã sửa.
- **Reopened:** điều kiện lỗi xuất hiện lại hoặc bằng chứng đóng không còn phù hợp.

Tên trạng thái có thể khác giữa các công cụ. Điều quan trọng là không dùng một trạng thái “Done” chung để làm mất khác biệt giữa đã sửa, đã xác minh và đang chấp nhận rủi ro.

## 13. Ví dụ đánh giá phục hồi có thể đo được

Giả sử SR-REC-01 quy định:

> Trong điều kiện diễn tập đã xác định, dịch vụ phải khôi phục chức năng hồ sơ trong 60 phút từ thời điểm mất khả dụng, và điểm dữ liệu khôi phục không được cũ hơn 15 phút so với mốc sự cố đã quy định.

Cần làm rõ các mốc:

- `t0`: thời điểm mất khả dụng trong kịch bản.
- `tReady`: thời điểm dịch vụ đáp ứng các kiểm tra chức năng và bảo mật đã quy định.
- `tCut`: mốc đối chiếu mất dữ liệu trong kịch bản; ở ví dụ này bằng `t0`.
- `tRecovered`: thời điểm nghiệp vụ của dữ liệu mới nhất đã được xác nhận khôi phục, theo cách đo đã thống nhất.

Các phép đo minh họa:

~~~text
recoveryDuration = tReady - t0
observedRecoveryPointGap = tCut - tRecovered

Yêu cầu minh họa:
recoveryDuration <= 60 phút
observedRecoveryPointGap <= 15 phút
~~~

Để đo điểm khôi phục, có thể tạo các bản ghi đánh dấu tổng hợp có thời gian và xác nhận ghi thành công trước sự cố. Sau restore, kiểm tra bản ghi nào thực sự có mặt và tính nhất quán của chúng.

Không lấy thời điểm “job backup thành công” làm thời điểm dữ liệu được khôi phục mà không kiểm tra nội dung. Cũng không dùng thời điểm bắt đầu restore làm điểm bắt đầu đo nếu yêu cầu quy định tính từ lúc dịch vụ mất khả dụng.

Bộ bằng chứng cần có:

1. Điều kiện diễn tập, dung lượng dữ liệu và các phụ thuộc.
2. Dấu thời gian có thể so sánh được.
3. Trạng thái backup và artifact được dùng để restore.
4. Kết quả kiểm tra dữ liệu sau khôi phục.
5. Kiểm tra chức năng, phân quyền và khả năng truy cập secret sau phục hồi.
6. Hạn chế của phép thử so với phạm vi vận hành thực tế.

Nếu chỉ có thông báo backup thành công mà chưa diễn tập restore, không được kết luận SR-REC-01 đã đạt. Có thể xác nhận một phần quy trình sao lưu và ghi phần kiểm chứng phục hồi là chưa đánh giá hoặc chưa đủ bằng chứng tùy hoạt động đã thực hiện.

Một diễn tập đáp ứng mục tiêu trong một điều kiện chưa chứng minh mọi thảm họa đều khôi phục đúng hạn. Báo cáo phải nêu điều kiện, phạm vi dữ liệu và các phụ thuộc đã được thử.

## 14. Tổng hợp báo cáo và duy trì đánh giá

### 14.1. Nội dung báo cáo

Một báo cáo Assess cần đủ để người đọc không tham gia kiểm thử vẫn hiểu được:

- Đã đánh giá hệ thống nào, phiên bản nào, ở đâu và trong khoảng nào.
- Yêu cầu, baseline, nghĩa vụ và giả định được sử dụng.
- Phương pháp, độ sâu, độ bao phủ và cách chọn mẫu.
- Bằng chứng, kết luận, phát hiện và mức độ tin cậy.
- Rủi ro hiện tại, giới hạn và các điểm chưa xác định.
- Kế hoạch xử lý, người chịu trách nhiệm và quyết định đang cần.
- Điều kiện phải đánh giá lại.

Báo cáo kỹ thuật có thể chi tiết, nhưng phần phục vụ quyết định cần nêu rõ khoảng trống nào ảnh hưởng đến việc phát hành hoặc vận hành và vì sao.

### 14.2. Ví dụ tổng hợp kết quả

| Yêu cầu | Kết luận minh họa | Căn cứ hoặc giới hạn | Việc cần làm |
| --- | --- | --- | --- |
| SR-AUTHN-01 | MET trong các thao tác quản trị thuộc phạm vi | Ca có và thiếu mức xác minh đã được thực hiện trên bản xác định | Duy trì kiểm tra khi thay đổi chính sách |
| SR-AUTHZ-01 | NOT_MET | Có bằng chứng tải chéo tenant tại điểm tải | Khắc phục F-01 và kiểm tra lại |
| SR-DATA-01 | INCONCLUSIVE | Một đường chẩn đoán chưa truy cập được nên chưa đủ bằng chứng | Bổ sung quyền và hoàn tất đánh giá |
| SR-LOG-01 | PARTIALLY_MET | Một kênh thay đổi quyền không tạo đủ trường bắt buộc | Sửa kênh đó, kiểm tra cả luồng lỗi |
| SR-REC-01 | NOT_ASSESSED | Chưa thực hiện thủ tục diễn tập restore | Lập và thực hiện diễn tập |

Bảng minh họa không có nghĩa cả hệ thống đạt vì một số dòng có MET. Người quyết định phải xem yêu cầu nào bắt buộc, rủi ro nào còn lại và có giới hạn nào khiến chưa thể quyết định.

### 14.3. Các tác nhân đánh giá lại

Cần xem xét đánh giá lại khi:

- Có thay đổi đáng kể về dữ liệu, luồng nghiệp vụ hoặc ranh giới tin cậy.
- Thay đổi danh tính, phân quyền, cấu hình hoặc cơ chế kiểm soát dùng chung.
- Có sự cố, phát hiện mới hoặc bằng chứng trái với kết luận trước.
- Kiểm soát bù ngừng hoạt động hoặc quyết định chấp nhận rủi ro hết hiệu lực.
- Nghĩa vụ áp dụng, mức chấp nhận rủi ro hoặc mục tiêu phục hồi thay đổi.
- Đến kỳ đánh giá được tổ chức xác định.

Đánh giá lại có thể theo phần bị ảnh hưởng nếu phân tích tác động đủ rõ. Khi không xác định được ảnh hưởng, phạm vi cần được mở rộng để tránh dùng kết quả cũ cho một hệ thống đã khác.

## 15. Các lỗi thường gặp và bài tập áp dụng

### 15.1. Các lỗi làm kết luận thiếu tin cậy

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ chạy công cụ quét | Bỏ sót logic nghiệp vụ, vận hành và yêu cầu không nằm trong khả năng công cụ | Thiết kế thủ tục từ yêu cầu và kịch bản rủi ro |
| Chỉ kiểm tra ca hợp lệ | Không biết kiểm soát có chặn hành vi sai quyền không | Thêm ca không được phép và lỗi phụ thuộc |
| Đánh giá tệp cấu hình thay cho trạng thái thực tế | Kết luận sai khi có ghi đè hoặc drift | Đối chiếu cấu hình có hiệu lực và phiên bản |
| Tin phỏng vấn mà không đối chiếu | Nhầm mô tả quy trình với việc thực hiện quy trình | Kiểm tra bản ghi và mẫu vận hành |
| Không ghi tổng thể chọn mẫu | Không hiểu kết luận bao phủ đến đâu | Liệt kê tổng thể, mẫu và phần chưa kiểm tra |
| Thiếu bằng chứng nhưng ghi đạt | Che mất bất định và làm sai quyết định | Dùng trạng thái chưa kết luận hoặc chưa đánh giá |
| Chấm rủi ro từ số phát hiện | Bỏ qua tài sản, kịch bản và kiểm soát | Đánh giá từng kịch bản trong bối cảnh |
| Đóng lỗi khi có kế hoạch sửa | Ghi nhận rủi ro mục tiêu như đã đạt | Kiểm tra lại trên đối tượng đã khắc phục |
| Chấp nhận rủi ro rồi đổi kết quả thành đạt | Mất sự thật về yêu cầu chưa đáp ứng | Tách trạng thái kỹ thuật và quyết định rủi ro |
| Tái sử dụng bằng chứng không xét thay đổi | Kết luận trên phiên bản không còn phù hợp | Xác nhận tính đại diện trước khi dùng lại |

### 15.2. Bài tập

Một dịch vụ đa tenant có API, worker export, kho tệp và hệ thống audit log. Nhóm phát triển cung cấp kết quả quét không có phát hiện nghiêm trọng, ảnh chụp cấu hình phân quyền và thông báo backup thành công.

Hãy lập một gói Assess rút gọn:

1. Viết ba yêu cầu đo được cho phân quyền export, logging quản trị và phục hồi.
2. Xác định mục tiêu đánh giá và điểm thực thi cần kiểm tra cho mỗi yêu cầu.
3. Chọn phương pháp, mẫu và điều kiện thử; giải thích các phần chưa bao phủ.
4. Viết ít nhất một ca hợp lệ, một ca sai quyền và một ca lỗi phụ thuộc.
5. Thiết kế bản ghi bằng chứng không chứa secret nhưng đủ tái kiểm tra.
6. Giả sử tải chéo tenant thành công trong môi trường thử nghiệm: viết phát hiện, phạm vi xác nhận và các điều chưa biết.
7. Đánh giá rủi ro hiện tại dựa trên kiểm soát có bằng chứng; tách khỏi rủi ro dự kiến sau sửa.
8. Nêu tiêu chí đóng phát hiện, điều kiện chấp nhận rủi ro và tác nhân cần đánh giá lại.

Một kết quả tốt cho phép người đọc truy ngược từ kết luận về rủi ro đến phát hiện, bằng chứng, thủ tục, yêu cầu và mục tiêu bảo vệ tài sản. Khi còn thiếu một mắt xích, báo cáo cần thể hiện khoảng trống đó để quyết định tiếp theo dựa trên đúng mức độ hiểu biết hiện có.
