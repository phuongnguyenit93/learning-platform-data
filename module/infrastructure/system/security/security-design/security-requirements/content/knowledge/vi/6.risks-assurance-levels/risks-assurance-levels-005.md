# Risk owner

## 1. Mục tiêu bài học

Trong chương **Rủi ro và mức đảm bảo**, việc xác định một rủi ro bảo mật chưa đủ để làm thay đổi hệ thống. Phải có người chịu trách nhiệm đưa rủi ro đó tới một quyết định: xử lý bằng cách nào, ai thực hiện, cần bằng chứng gì, rủi ro còn lại có được phép chấp nhận không và khi nào phải xem xét lại.

**Risk owner**, hay **chủ sở hữu rủi ro**, là vai trò chịu trách nhiệm quản lý một rủi ro trong phạm vi được giao và bảo đảm các quyết định liên quan được thực hiện đúng thẩm quyền. Vai trò này kết nối hậu quả đối với nghiệp vụ với yêu cầu bảo mật và bằng chứng kỹ thuật.

Sau bài học, người học có thể:

- Chọn risk owner phù hợp với tác động và phạm vi của một rủi ro.
- Phân biệt risk owner với chủ sở hữu hệ thống, người triển khai kiểm soát và người phê duyệt chấp nhận rủi ro.
- Chuyển quyết định xử lý rủi ro thành yêu cầu bảo mật cụ thể, đo được và kiểm chứng được.
- Xác định mức bằng chứng cần có trước khi đánh giá rủi ro còn lại.
- Theo dõi quyết định, ngoại lệ, chuyển giao trách nhiệm và các sự kiện buộc phải đánh giá lại.

Các vai trò, mức rủi ro và thời hạn trong bài là quy ước minh họa cho một tổ chức giả định. Khi áp dụng, phải dùng cơ chế phân quyền và tiêu chí đã được tổ chức chấp thuận.

## 2. Risk owner chịu trách nhiệm về điều gì?

Risk owner phải bảo đảm một rủi ro có:

1. Mô tả đủ rõ về tài sản, kịch bản, hậu quả và phạm vi ảnh hưởng.
2. Đánh giá có căn cứ, thể hiện cả giả định và điểm chưa chắc chắn.
3. Phương án xử lý được quyết định hoặc đưa tới đúng người có thẩm quyền.
4. Người thực hiện, nguồn lực, thời hạn và yêu cầu bảo mật tương ứng.
5. Bằng chứng để xác nhận kết quả, thay vì chỉ ghi nhận đã hoàn thành công việc.
6. Quyết định về rủi ro còn lại trong đúng giới hạn được phép.
7. Cơ chế theo dõi, rà soát và chuyển cấp khi điều kiện thay đổi.

Ví dụ, rủi ro lộ hóa đơn giữa các tổ chức khách hàng có thể cần thay đổi API, chính sách quyền, kho tệp và tác vụ xuất. Risk owner không nhất thiết tự sửa những thành phần đó, nhưng phải theo dõi để toàn bộ phương án xử lý có người thực hiện và được kiểm chứng.

### 2.1. Trách nhiệm phải đi cùng khả năng hành động

Một người chỉ được ghi tên trong bảng rủi ro nhưng không có quyền điều phối, không tiếp cận được thông tin và không có đường xin nguồn lực thì khó thực hiện vai trò.

Risk owner cần có khả năng:

- Hiểu và xác nhận tác động đối với phạm vi mình quản lý.
- Yêu cầu các nhóm liên quan cung cấp thông tin, kế hoạch và bằng chứng.
- Đề xuất hoặc điều phối ưu tiên, nguồn lực và thay đổi trong phạm vi được giao.
- Đưa quyết định vượt quyền tới cấp có thẩm quyền.
- Duy trì trạng thái rủi ro và yêu cầu rà soát khi có dấu hiệu thay đổi.

Không yêu cầu một người phải có quyền tuyệt đối trên mọi hệ thống. Với phụ thuộc liên nhóm, cần cơ chế phối hợp và chuyển cấp đủ rõ để họ có thể thực hiện trách nhiệm.

### 2.2. Sở hữu rủi ro không tự động bao gồm mọi quyền phê duyệt

Cần tách hai câu hỏi:

- **Ai chịu trách nhiệm quản lý rủi ro tới khi có quyết định và theo dõi quyết định?**
- **Ai có thẩm quyền chấp nhận mức hậu quả và rủi ro còn lại trong trường hợp này?**

Hai vai trò có thể trùng nhau nếu tổ chức cho phép. Chúng cũng có thể khác nhau, chẳng hạn risk owner quản lý một sản phẩm nhưng việc chấp nhận rủi ro cao phải do người phụ trách đơn vị kinh doanh quyết định.

Không được suy ra quyền chấp nhận chỉ vì một người được gắn nhãn risk owner. Ngược lại, khi quyết định cần cấp cao hơn, risk owner vẫn tiếp tục điều phối và theo dõi; trách nhiệm không biến mất sau một lần chuyển cấp.

### 2.3. Đây là vai trò quản lý rủi ro xuyên suốt

Một rủi ro đã được chấp nhận vẫn cần người theo dõi điều kiện và thời hạn. Một rủi ro đã được giảm thiểu vẫn có thể quay lại khi thay đổi kiến trúc hoặc cấu hình.

Không dùng nhãn “đã xử lý” để gộp các trạng thái khác nhau:

| Trạng thái | Ý nghĩa cần thể hiện |
| --- | --- |
| Đã chọn phương án | Có quyết định, chưa chắc đã triển khai |
| Đang triển khai | Có công việc và người thực hiện, bằng chứng chưa hoàn tất |
| Đã kiểm chứng | Có kết quả xác minh trong phạm vi và phiên bản cụ thể |
| Rủi ro còn lại đã được chấp nhận | Có quyết định đúng thẩm quyền, điều kiện và thời hạn |
| Đang theo dõi | Cần giám sát giả định, kiểm soát và sự kiện thay đổi |
| Đã đóng | Có căn cứ không còn cần theo dõi theo quy tắc đóng đã được chấp thuận |

Không mặc định “được chấp nhận” đồng nghĩa “không còn rủi ro”.

## 3. Phân biệt các vai trò liên quan

| Vai trò | Trọng tâm trách nhiệm | Ví dụ trong rủi ro xuất hóa đơn |
| --- | --- | --- |
| Risk owner | Điều phối quyết định và quản lý rủi ro theo phạm vi | Người phụ trách nghiệp vụ thanh toán doanh nghiệp |
| Chủ sở hữu hệ thống | Quản lý kiến trúc, vận hành và vòng đời hệ thống | Người phụ trách nền tảng hóa đơn |
| Chủ sở hữu dữ liệu | Quyết định việc sử dụng, phân loại và chia sẻ dữ liệu trong quyền hạn | Vai trò quản lý dữ liệu hóa đơn |
| Control owner — chủ sở hữu kiểm soát | Duy trì hiệu quả của một kiểm soát cụ thể | Nhóm quản lý chính sách quyền hoặc kiểm soát tải tệp |
| Người thực hiện công việc | Xây dựng, cấu hình hoặc sửa một phần giải pháp | Kỹ sư sửa API xuất hóa đơn |
| Người xác minh, đánh giá | Thu thập và đánh giá bằng chứng theo phạm vi | Người kiểm thử hoặc người rà soát độc lập được giao |
| Người có thẩm quyền chấp nhận | Phê duyệt rủi ro còn lại trong giới hạn được giao | Giám đốc đơn vị kinh doanh theo chính sách nội bộ |

Một người có thể kiêm nhiều vai trò khi được phép, nhưng hồ sơ cần chỉ rõ họ đang quyết định với tư cách nào. Nếu chính sách yêu cầu xác minh hoặc phê duyệt độc lập, việc kiêm nhiệm phải được kiểm tra với yêu cầu đó.

### 3.1. Người sửa lỗi không mặc nhiên là risk owner

Kỹ sư có thể hiểu nguyên nhân kỹ thuật nhưng không có quyền quyết định tổ chức chấp nhận hậu quả kinh doanh đến đâu. Giao ticket cho kỹ sư chỉ xác định người thực hiện công việc.

Ví dụ:

- “Nhóm API sửa kiểm tra quyền trước thứ Sáu” là phân công công việc.
- “Người phụ trách nghiệp vụ chịu trách nhiệm điều phối xử lý rủi ro lộ hóa đơn và xin quyết định khi vượt ngưỡng” là phân công quản lý rủi ro.

Cần cả hai để công việc không bị hoàn thành về mặt kỹ thuật nhưng bỏ sót quyết định về phạm vi và rủi ro còn lại.

### 3.2. Nhóm bảo mật không tự động sở hữu mọi rủi ro

Nhóm bảo mật có thể hỗ trợ nhận diện đe dọa, đánh giá kiểm soát, đề xuất yêu cầu và xác minh bằng chứng. Tuy nhiên, hậu quả có thể thuộc một sản phẩm hoặc hoạt động mà nhóm bảo mật không có quyền quyết định.

Với rủi ro thuộc chính nền tảng bảo mật, người phụ trách nền tảng đó có thể là risk owner phù hợp. Cần chọn theo tác động và thẩm quyền thực tế, thay vì theo nhãn “vấn đề bảo mật”.

### 3.3. Nhà cung cấp và bên ngoài

Nhà cung cấp có thể chịu trách nhiệm thực hiện một kiểm soát hoặc cam kết theo hợp đồng. Tổ chức sử dụng dịch vụ vẫn cần vai trò nội bộ theo dõi rủi ro đối với hoạt động của mình.

Chuyển giao một phần chi phí hoặc trách nhiệm không loại bỏ mọi hậu quả còn lại. Risk owner cần biết phần nào đã được chuyển, phần nào vẫn tồn tại và bằng chứng nào cho thấy cam kết được thực hiện.

## 4. Chọn và ghi nhận risk owner

### 4.1. Chọn theo phạm vi tác động và quyền điều phối

Một cách lựa chọn:

1. Xác định mục tiêu nghiệp vụ hoặc tài sản chịu tác động.
2. Xác định người chịu trách nhiệm đối với mục tiêu hoặc tài sản đó.
3. Kiểm tra họ có khả năng điều phối phương án xử lý hay không.
4. Xác định rõ giới hạn quyết định và đường chuyển cấp.
5. Ghi nhận người đảm nhận hiện tại, người thay thế và việc xác nhận nhận trách nhiệm.

Ví dụ:

| Rủi ro | Vai trò có thể phù hợp | Điều kiện cần kiểm tra |
| --- | --- | --- |
| Xuất nhầm hóa đơn cho khách hàng khác | Người phụ trách nghiệp vụ hóa đơn | Có khả năng điều phối sản phẩm, dữ liệu và vận hành |
| Pipeline dùng chung đưa mã sai vào nhiều sản phẩm | Người phụ trách nền tảng phát hành | Có cơ chế phối hợp với các sản phẩm bị ảnh hưởng |
| Mất khả năng phục hồi dữ liệu đối soát | Người phụ trách dịch vụ hoặc nghiệp vụ đối soát | Có thẩm quyền đề xuất mức phục hồi và nguồn lực |
| Nhà cung cấp ngừng hỗ trợ thành phần trọng yếu | Người phụ trách dịch vụ phụ thuộc | Có đường quyết định nâng cấp, thay thế hoặc giảm phạm vi |

Đây là gợi ý lựa chọn, không phải danh sách chức danh bắt buộc.

### 4.2. Với rủi ro liên nhóm, cần đầu mối chịu trách nhiệm rõ

Một hồ sơ rủi ro nên có một đầu mối chịu trách nhiệm được xác định rõ. Các nhóm khác có thể sở hữu kiểm soát hoặc công việc thành phần.

Nếu tổ chức sử dụng một hội đồng làm chủ thể quyết định, cần ghi rõ người điều phối, cách ra quyết định và cách ghi nhận kết quả. Chỉ điền “các nhóm liên quan” không cho biết ai sẽ hành động khi tiến độ bị chậm.

Có thể tách một rủi ro lớn thành các rủi ro thành phần khi phạm vi, hậu quả và quyền quyết định khác nhau. Tuy nhiên, vẫn cần người theo dõi tác động tổng hợp nếu các thành phần cùng tạo ra một kịch bản lớn.

### 4.3. Hồ sơ phân công tối thiểu

Nên có:

- Định danh rủi ro và phạm vi được giao.
- Vai trò risk owner và người đang đảm nhận.
- Ngày nhận trách nhiệm.
- Giới hạn quyền quyết định.
- Người có thẩm quyền phê duyệt khi vượt giới hạn.
- Các control owner và đầu mối phụ thuộc.
- Kỳ rà soát tiếp theo và sự kiện cần chuyển cấp.

Khi nhân sự đổi vai trò, cần bàn giao rủi ro đang mở, quyết định còn hiệu lực, công việc chậm, ngoại lệ và bằng chứng. Một địa chỉ email đã ngừng sử dụng không phải là cơ chế quản lý trách nhiệm.

## 5. Trách nhiệm trong vòng đời xử lý rủi ro

### 5.1. Làm rõ kịch bản trước khi chọn giải pháp

Một mô tả hữu ích có dạng:

> **Chủ thể hoặc sự kiện đe dọa + điều kiện cho phép xảy ra + tài sản chịu ảnh hưởng + hậu quả.**

Ví dụ:

> Người dùng đã đăng nhập có thể thay phạm vi tổ chức trong tác vụ xuất hóa đơn vì dịch vụ tin vào giá trị do phía khách gửi, dẫn đến tệp xuất chứa dữ liệu của tổ chức khác.

Mô tả “API chưa an toàn” chưa đủ để phân công, đánh giá hoặc viết tiêu chí chấp nhận.

Risk owner cần xác nhận tác động và phạm vi. Nhóm kỹ thuật, dữ liệu và bảo mật hỗ trợ làm rõ điều kiện, đường tấn công và giả định.

### 5.2. Phân biệt rủi ro trước xử lý, mục tiêu và kết quả thực tế

| Khái niệm | Ý nghĩa |
| --- | --- |
| Rủi ro trước phương án xử lý đang xét | Mức đánh giá với điều kiện hiện tại và giả định đã nêu |
| Rủi ro mục tiêu | Mức dự kiến đạt sau khi kiểm soát được triển khai và hoạt động như mong đợi |
| Rủi ro còn lại đã đánh giá | Mức được đánh giá sau xử lý, dựa trên bằng chứng thực tế và giới hạn còn tồn tại |

Không lấy rủi ro mục tiêu làm kết quả đã đạt. Kế hoạch “sẽ bổ sung kiểm tra quyền” chưa chứng minh quyền đã được kiểm tra ở API, tác vụ nền, kho tệp và cache.

Cũng không giảm mức rủi ro bằng cách trừ số lỗi đã sửa hoặc lấy một điểm kỹ thuật làm đại diện cho toàn bộ tác động. Cần xem lại kịch bản, khả năng xảy ra, hậu quả, hiệu quả kiểm soát và mức chưa chắc chắn.

### 5.3. Chọn phương án và theo dõi thực hiện

Các hướng xử lý có thể gồm:

- **Tránh:** bỏ chức năng hoặc thay đổi cách làm để loại bỏ kịch bản trong phạm vi xác định.
- **Giảm thiểu:** triển khai kiểm soát làm giảm khả năng hoặc hậu quả.
- **Chia sẻ hoặc chuyển giao một phần:** dùng thỏa thuận hoặc cơ chế khác, đồng thời đánh giá phần còn lại.
- **Chấp nhận:** quyết định chịu rủi ro còn lại trong đúng giới hạn được phép.

Một phương án có thể kết hợp nhiều hướng. Ví dụ, tạm dừng xuất hàng loạt trong khi bổ sung phân quyền là một quyết định phạm vi cần có điều kiện mở lại rõ ràng.

Risk owner cần bảo đảm phương án có người thực hiện, thời hạn, nguồn lực, yêu cầu bảo mật và tiêu chí kiểm chứng. Khi thiếu nguồn lực hoặc phụ thuộc bị chậm, phải chuyển cấp; việc vẫn để ticket mở không thay thế quyết định quản lý rủi ro.

## 6. Risk owner và mức đảm bảo

**Mức đảm bảo** trong bài là độ tin cậy có căn cứ đối với việc các yêu cầu bảo mật đã được triển khai và hoạt động trong phạm vi xét. Nó phụ thuộc vào chất lượng, độ bao phủ, tính phù hợp và tính độc lập cần thiết của bằng chứng.

Mức đảm bảo không đồng nghĩa mức rủi ro. Có thể có:

- Một rủi ro được đánh giá cao với bằng chứng đánh giá tốt.
- Một rủi ro được ghi là thấp nhưng bằng chứng yếu, khiến kết luận chưa đáng tin.
- Một kiểm soát đã hoạt động ở môi trường thử nhưng chưa có bằng chứng cấu hình production phù hợp.

Risk owner cần biết kết luận dựa trên những gì, còn khoảng trống nào và khoảng trống đó có làm thay đổi quyết định không.

### 6.1. Chọn độ sâu bằng chứng theo hậu quả và sự chưa chắc chắn

Ba nhóm dưới đây là quy ước học tập, không phải cấp chứng nhận:

| Nhóm bằng chứng | Nội dung có thể cần | Khi nào có thể phù hợp |
| --- | --- | --- |
| Cơ bản | Kiểm thử yêu cầu, cấu hình, truy vết kết quả và rà soát của nhóm | Phạm vi hạn chế, tác động được đánh giá thấp và cách triển khai quen thuộc |
| Tăng cường | Rà soát thiết kế, kiểm thử đường bị cấm, điều kiện lỗi, tích hợp và cấu hình triển khai | Dữ liệu nhạy cảm, nhiều ranh giới tin cậy hoặc ảnh hưởng nhiều người dùng |
| Có xác minh độc lập theo phạm vi | Người không trực tiếp triển khai rà soát bằng chứng và thực hiện đánh giá được giao | Hậu quả lớn, kiểm soát phức tạp hoặc chính sách yêu cầu độc lập |

Không chọn mức thấp hơn chỉ vì thiếu thời gian. Khi chưa đạt mức bằng chứng cần thiết, phải bổ sung, giảm phạm vi, lùi quyết định hoặc chuyển cấp theo quy tắc được chấp thuận.

Bằng chứng độc lập cũng có giới hạn. Một báo cáo đánh giá chỉ có giá trị trong phạm vi, thời điểm, cấu hình và phương pháp đã nêu.

### 6.2. Những câu hỏi risk owner nên đặt trước khi kết luận

- Bằng chứng gắn với yêu cầu nào và phiên bản nào?
- Đã thử đường truy cập bị cấm, đường lỗi và tác vụ nền chưa?
- Cấu hình được thử có đại diện cho nơi triển khai không?
- Phụ thuộc danh tính, dữ liệu, khóa và logging đã nằm trong phạm vi chưa?
- Có kết quả không đạt hoặc trường hợp chưa thử không?
- Người xác minh có đáp ứng yêu cầu năng lực và độc lập được đặt ra không?
- Kết luận có còn đúng sau thay đổi gần nhất không?
- Các giả định quan trọng có cơ chế theo dõi không?

Một danh sách công cụ đã chạy hoặc số lượng kiểm thử không trả lời đầy đủ các câu hỏi này.

### 6.3. Yêu cầu bắt buộc và quyền chấp nhận

Cần phân biệt:

- Rủi ro còn lại có thể được chấp nhận theo chính sách.
- Yêu cầu bắt buộc mà người đang quyết định không có quyền miễn trừ.
- Ngoại lệ chỉ có hiệu lực khi được đúng chủ thể phê duyệt theo quy trình riêng.

Ví dụ, risk owner không thể tự bỏ một yêu cầu cách ly dữ liệu đã được xác định là điều kiện phát hành bắt buộc chỉ bằng cách ký “chấp nhận rủi ro”.

Nếu không rõ yêu cầu có thể miễn trừ hay không, phải xác minh thẩm quyền và nguồn yêu cầu. Chấp nhận rủi ro không phải cách thay thế việc làm rõ nghĩa vụ.

## 7. Ví dụ xuyên suốt: rủi ro xuất hóa đơn chéo tổ chức

### 7.1. Phạm vi và phân công

Một dịch vụ hóa đơn phục vụ nhiều tổ chức khách hàng. Người dùng có quyền xuất hóa đơn của tổ chức mình. Tác vụ xuất chạy nền và lưu tệp để tải sau.

Rủi ro `R-INV-007` được mô tả:

> Nếu dịch vụ sử dụng phạm vi tổ chức do yêu cầu phía khách cung cấp mà không đối chiếu với danh tính và quyền hiện tại, người dùng có thể tạo hoặc tải tệp hóa đơn của tổ chức khác, dẫn đến tiết lộ dữ liệu kinh doanh.

Phân công giả định:

| Nội dung | Vai trò |
| --- | --- |
| Risk owner | Người phụ trách nghiệp vụ hóa đơn doanh nghiệp |
| Chủ sở hữu kiểm soát API và tác vụ xuất | Nhóm phát triển dịch vụ hóa đơn |
| Chủ sở hữu danh tính và quyền nền tảng | Nhóm quản lý truy cập |
| Chủ sở hữu kiểm soát kho tệp | Nhóm nền tảng lưu trữ |
| Chủ sở hữu logging phục vụ điều tra | Nhóm vận hành quan sát |
| Người xác minh theo yêu cầu độc lập của ví dụ | Người đánh giá không trực tiếp triển khai thay đổi |
| Người phê duyệt rủi ro còn lại | Người phụ trách đơn vị kinh doanh, theo giới hạn đã được giao |

Risk owner xác nhận tác động đến khách hàng và nghiệp vụ, điều phối tiến độ và trình quyết định. Các control owner chịu trách nhiệm duy trì phần kiểm soát được giao.

### 7.2. Quyết định xử lý và điều kiện mở lại

Giả sử đánh giá ban đầu cho thấy đường xuất hiện tại có thể vượt phạm vi tổ chức. Phương án được chọn là:

1. Tạm dừng chức năng xuất bị ảnh hưởng đối với dữ liệu thật.
2. Bổ sung kiểm tra quyền ở các bước tạo tác vụ, chạy tác vụ và tải tệp.
3. Bảo vệ kho tệp và dấu vết truy cập.
4. Kiểm chứng các đường cho phép, bị cấm và điều kiện lỗi.
5. Đánh giá lại rủi ro còn lại và xin quyết định trước khi mở chức năng.

Tạm dừng một chức năng cũng có tác động nghiệp vụ. Risk owner cần ghi nhận phạm vi dừng, người quyết định, cách phục vụ thay thế nếu có và điều kiện mở lại.

Việc đã triển khai bản sửa chưa tự thỏa điều kiện mở lại. Các yêu cầu bắt buộc và bằng chứng tương ứng vẫn phải đạt.

### 7.3. Chuyển thành yêu cầu bảo mật

Các ngưỡng dưới đây là giả định của ví dụ.

| Mã | Yêu cầu | Tiêu chí chấp nhận | Chủ sở hữu kiểm soát |
| --- | --- | --- | --- |
| SR-INV-01 | API phải xác định phạm vi tổ chức từ danh tính và quyền đã xác minh; mọi phạm vi do phía khách gửi phải được kiểm tra | Thay mã tổ chức hoặc mã hóa đơn không cho phép đọc hay xuất dữ liệu ngoài phạm vi | Nhóm dịch vụ hóa đơn |
| SR-INV-02 | Người dùng có quyền xuất hàng loạt phải đáp ứng xác thực đa yếu tố trước khi dùng chức năng đó | Người chưa đáp ứng điều kiện bị chặn; người đã đáp ứng vẫn phải qua kiểm tra quyền và phạm vi | Nhóm quản lý truy cập và nhóm dịch vụ |
| SR-INV-03 | Tác vụ nền phải kiểm tra quyền trước khi tạo nội dung; lượt tải phải kiểm tra lại quyền đối với tệp | Thu hồi quyền sau khi xếp hàng hoặc trước khi tải không dẫn tới cung cấp tệp sau khi việc thu hồi đã có hiệu lực | Nhóm dịch vụ hóa đơn |
| SR-INV-04 | Việc thu hồi quyền xuất phải có hiệu lực trên mọi đường yêu cầu mới trong tối đa 5 phút | Đo từ lúc hệ thống xác nhận thu hồi; thử qua phiên cũ, cache quyền, tác vụ nền và lượt tải | Nhóm quản lý truy cập và nhóm dịch vụ |
| SR-INV-05 | Tệp xuất không được truy cập công khai; lưu trữ và truyền tải phải dùng cơ chế mã hóa được chính sách chấp thuận | Thử tải không xác thực, đổi chủ thể tải và đọc bằng danh tính ngoài phạm vi; không nhận được nội dung | Nhóm nền tảng lưu trữ và nhóm dịch vụ |
| SR-INV-06 | Mọi lần yêu cầu xuất, chạy tác vụ và tải phải tạo sự kiện kiểm toán liên kết; không ghi nội dung hóa đơn hoặc thông tin xác thực | Đối chiếu đầy đủ ba bước, thử cả thành công và từ chối; giá trị giả có dấu nhận diện không xuất hiện trong log | Nhóm dịch vụ và nhóm vận hành quan sát |
| SR-INV-07 | Khi không xác định được quyền hoặc phạm vi tổ chức, hệ thống phải từ chối tạo và cung cấp nội dung | Mô phỏng lỗi phụ thuộc quyền và dữ liệu phạm vi; không tự cho phép để tiếp tục phục vụ | Nhóm dịch vụ và nhóm quản lý truy cập |
| SR-INV-08 | Sau phục hồi cấu hình hoặc dữ liệu, phải xác minh lại cách ly tổ chức và quyền truy cập tệp trước khi mở chức năng xuất | Diễn tập phục hồi có tệp và quyền từ các tổ chức khác nhau; kiểm thử chéo tổ chức vẫn bị từ chối | Nhóm dịch vụ và nhóm nền tảng |

Mỗi yêu cầu cần liên kết với rủi ro và mã kiểm thử. Nhóm triển khai có thể chia công việc chi tiết, nhưng risk owner phải nhìn được yêu cầu nào chưa có chủ sở hữu hoặc còn phụ thuộc chưa giải quyết.

Khoảng 5 phút ở SR-INV-04 là giới hạn được nêu rõ, không phải thu hồi tức thời. Risk owner phải hiểu và đưa phần tiếp cận có thể còn tồn tại trong khoảng này vào đánh giá phù hợp; nếu không được phép có khoảng trễ, yêu cầu phải thay đổi.

### 7.4. Ma trận kiểm chứng tối thiểu của ví dụ

| Chủ thể hoặc tình huống | Kết quả cần thấy |
| --- | --- |
| Người được phép xuất đúng tổ chức | Chỉ có dữ liệu trong phạm vi |
| Người được phép xuất ở A yêu cầu dữ liệu B | Bị từ chối ở cả API và tác vụ nền |
| Người A nhận URL tệp của B | Không tải được nội dung |
| Người dùng đã bị thu hồi quyền | Mọi đường yêu cầu mới bị chặn trong giới hạn đã đặc tả |
| Tác vụ được tạo trước khi quyền thay đổi | Kiểm tra lại, không dựa hoàn toàn vào quyết định lúc xếp hàng |
| Dịch vụ quyền gặp lỗi | Không cung cấp dữ liệu theo một giá trị mặc định cho phép |
| Tệp còn sau phục hồi | Quyền và cách ly vẫn đúng trước khi mở truy cập |
| Log của đường lỗi | Có thông tin điều tra được phép, không có payload hóa đơn |

Một kiểm thử API đơn lẻ không bao phủ mọi đường trong bảng. Nếu một đường chưa được kiểm chứng, hồ sơ phải thể hiện khoảng trống đó.

## 8. Đánh giá kết quả và quyết định rủi ro còn lại

### 8.1. Dựa vào hiệu quả kiểm soát đã được chứng minh

Sau triển khai, risk owner cùng các vai trò hỗ trợ xem xét:

- Các yêu cầu đã đạt trong phạm vi nào.
- Những trường hợp chưa thử hoặc chưa đại diện cho production.
- Kiểm soát có thể thất bại do phụ thuộc nào.
- Có phát hiện nào chưa xử lý.
- Rủi ro còn lại thay đổi thế nào so với đánh giá trước xử lý.
- Mức chưa chắc chắn có cho phép ra quyết định không.

Giả sử mọi yêu cầu của ví dụ đều đạt, cấu hình triển khai đã được đối chiếu và người xác minh hoàn tất phạm vi đã giao. Tổ chức có thể đánh giá rủi ro còn lại ở mức thấp theo tiêu chí nội bộ, với căn cứ và giới hạn được ghi rõ.

Không suy ra mức thấp chỉ vì tất cả kiểm thử đã chạy đều đạt. Cần xem độ bao phủ và phạm vi trước khi dùng kết quả đó làm căn cứ.

### 8.2. Các loại quyết định cần phân biệt

| Quyết định | Điều kiện và hệ quả |
| --- | --- |
| Yêu cầu bổ sung bằng chứng | Chưa đủ căn cứ; chưa được coi là đã đạt mức rủi ro mục tiêu |
| Tiếp tục giảm thiểu | Có khoảng trống cần xử lý, phải có kế hoạch và chủ sở hữu |
| Giảm hoặc dừng phạm vi | Chỉ được hoạt động trong phạm vi đã được cho phép |
| Chấp nhận rủi ro còn lại | Đúng thẩm quyền, không vượt yêu cầu bắt buộc, có điều kiện và thời hạn |
| Chuyển cấp | Vượt giới hạn quyết định, xung đột yêu cầu hoặc hậu quả vượt phạm vi quản lý |

“Chấp nhận nếu sau này sửa xong” thường đang trộn điều kiện phải hoàn thành với quyết định hiện tại. Cần ghi rõ hiện tại đã được phép làm gì, điều kiện nào phải đạt trước và ai xác nhận.

### 8.3. Hồ sơ chấp nhận cần đủ để người khác xem xét lại

Tối thiểu cần có:

- Định danh, kịch bản và phạm vi rủi ro.
- Risk owner và người có thẩm quyền phê duyệt.
- Mức rủi ro còn lại, phương pháp, căn cứ và điểm chưa chắc chắn.
- Các yêu cầu, kiểm soát và bằng chứng liên quan.
- Phát hiện chưa xử lý và lý do có thể chấp nhận, nếu có.
- Điều kiện duy trì, giám sát và ứng phó.
- Thời điểm có hiệu lực, hết hiệu lực và kỳ rà soát.
- Sự kiện làm quyết định phải được đánh giá lại.
- Kết quả được phép: phát hành, vận hành giới hạn hay tiếp tục dừng.

Một quyết định phải có ngày kết thúc hoặc quy tắc rà soát phù hợp. Không dùng chữ ký cũ làm căn cứ cho những thay đổi lớn chưa được đánh giá.

Việc có thời hạn cũng không cho phép bỏ qua sự kiện thay đổi trước ngày hết hạn. Một kiểm soát cốt lõi thất bại có thể buộc dừng hoặc thu hẹp phạm vi ngay theo quy trình đã được chấp thuận.

## 9. Ví dụ hồ sơ quản lý và quyết định

Đoạn YAML dưới đây là hồ sơ minh họa sau khi giả định đã hoàn thành các bước triển khai, xác minh và phê duyệt của ví dụ. Nó không đại diện cho một quyết định thực tế hoặc một định dạng bắt buộc:

```yaml
riskId: R-INV-007
title: cross-tenant-invoice-export
riskStatus: monitored

scenario:
  assetReference: DATA-INVOICE-001
  threat: "Người dùng yêu cầu hoặc tải tệp hóa đơn ngoài tổ chức được cấp."
  enablingCondition: "Phạm vi tổ chức không được kiểm tra nhất quán."
  consequence: "Tiết lộ dữ liệu kinh doanh của tổ chức khác."

ownership:
  riskOwnerRole: enterprise-billing-owner
  currentAssigneeReference: ROLE-ASSIGNMENT-DEMO-01
  acceptanceAuthorityRole: business-line-director
  authorityPolicyReference: RISK-AUTHORITY-DEMO-V1

assessment:
  methodReference: INTERNAL-QUALITATIVE-DEMO-V1
  beforeTreatment: high
  targetAfterTreatment: low
  assessedResidual: low
  rationale: "Các yêu cầu trong phạm vi đã được kiểm chứng và đối chiếu cấu hình."
  limitations:
    - "Kết luận chỉ áp dụng cho phiên bản và đường truy cập được nêu trong bằng chứng."
    - "Thời gian có hiệu lực của thu hồi quyền được đặc tả tối đa 5 phút."

treatment:
  approach: mitigate
  implementationStatus: verified
  requirementReferences:
    - SR-INV-01
    - SR-INV-02
    - SR-INV-03
    - SR-INV-04
    - SR-INV-05
    - SR-INV-06
    - SR-INV-07
    - SR-INV-08

assurance:
  verificationScopeReference: SCOPE-INV-DEMO-01
  verifierRole: independent-security-reviewer
  evidenceReferences:
    - EV-INV-AUTHORIZATION
    - EV-INV-ASYNC-DOWNLOAD
    - EV-INV-CONFIG-LOG-RESTORE

decision:
  type: accept-residual-risk
  approvalReference: DEC-INV-DEMO-01
  approvedByRole: business-line-director
  effectiveAt: "2026-12-01T00:00:00Z"
  expiresAt: "2027-03-01T00:00:00Z"
  nextReviewAt: "2027-01-01T00:00:00Z"
  permittedScope: "Chức năng xuất hóa đơn trong phạm vi phiên bản đã xác minh."
  conditions:
    - "Không có yêu cầu bắt buộc chưa đạt trong phạm vi được mở."
    - "Duy trì kiểm soát quyền, kho tệp và kiểm toán đã được kiểm chứng."
    - "Đánh giá lại trước khi thêm đường xuất hoặc thay đổi cách xác định tổ chức."

monitoring:
  controlOwnerReferences:
    - invoice-service-team
    - access-platform-team
    - storage-platform-team
    - observability-team
  reassessmentTriggers:
    - tenant-scope-model-change
    - new-export-or-download-path
    - material-access-control-failure
    - relevant-security-incident
    - approval-expiry
```

Các mức cao và thấp trong ví dụ là kết quả giả định của phương pháp nội bộ, không phải một phép tính chuẩn dùng chung. Trong hồ sơ thực, phương pháp phải có tiêu chí đủ rõ để người phê duyệt hiểu tại sao kết luận phù hợp.

Các tham chiếu bằng chứng cần dẫn tới nội dung có thể kiểm tra:

| Tham chiếu | Nội dung tối thiểu của ví dụ |
| --- | --- |
| EV-INV-AUTHORIZATION | Phiên bản, môi trường, danh tính giả, phạm vi tổ chức và kết quả kiểm thử cho phép, bị cấm |
| EV-INV-ASYNC-DOWNLOAD | Kiểm thử xếp hàng, thay đổi quyền, tải bằng chủ thể khác và đo thời gian thu hồi |
| EV-INV-CONFIG-LOG-RESTORE | Đối chiếu cấu hình, trường log, bảo vệ kho tệp và diễn tập sau phục hồi |

Chỉ điền một mã bằng chứng nhưng không có nội dung tương ứng không tạo ra mức đảm bảo.

### 9.1. Bảo vệ tính toàn vẹn của hồ sơ quyết định

Hồ sơ rủi ro cũng là dữ liệu cần quản lý. Cần xác định ai được sửa đánh giá, ai được ghi phê duyệt và làm sao truy vết thay đổi.

Một người được phép cập nhật tiến độ không nhất thiết được đổi người phê duyệt hoặc ghi rằng quyết định đã được chấp thuận. Các thay đổi quan trọng cần có danh tính, thời gian, nội dung trước và sau, cùng căn cứ.

Bằng chứng đính kèm phải được bảo vệ theo nội dung của nó. Báo cáo có dữ liệu khách hàng, chi tiết cấu hình hoặc thông tin khai thác không được công khai chỉ vì nằm trong hồ sơ quản lý rủi ro.

## 10. Theo dõi và chuyển cấp sau quyết định

### 10.1. Xác định sự kiện cần đánh giá lại

Risk owner cần theo dõi ít nhất những thay đổi có thể làm mất hiệu lực căn cứ cũ:

- Thêm loại dữ liệu, khách hàng hoặc phạm vi nghiệp vụ.
- Thay ranh giới tổ chức, mô hình quyền hoặc danh tính dịch vụ.
- Thêm API, đường tải, tác vụ nền hoặc nơi lưu mới.
- Đổi nhà cung cấp hay phụ thuộc quan trọng.
- Phát hiện kiểm soát không hoạt động như đã chứng minh.
- Xuất hiện sự cố hoặc thông tin đe dọa liên quan.
- Ngoại lệ hoặc quyết định chấp nhận hết hiệu lực.
- Thay đổi chủ sở hữu, quyền quyết định hoặc nguồn lực xử lý.

Đánh giá lại có thể chỉ tập trung vào phần bị ảnh hưởng nếu có căn cứ xác định phạm vi. Nếu thay đổi đụng tới giả định cốt lõi, cần mở rộng phạm vi xem xét tương ứng.

### 10.2. Khi nào phải chuyển cấp?

Các tình huống điển hình:

| Tình huống | Việc risk owner cần làm |
| --- | --- |
| Rủi ro vượt giới hạn được phép chấp nhận | Trình đúng người có thẩm quyền, kèm phương án và bằng chứng |
| Công việc xử lý chậm làm điều kiện vận hành không còn đúng | Yêu cầu quyết định về tiến độ, phạm vi hoặc dừng chức năng theo chính sách |
| Hai nhóm không thống nhất người thực hiện | Nêu rõ khoảng trống trách nhiệm và chuyển tới cấp điều phối |
| Chưa rõ có được miễn một yêu cầu bắt buộc không | Xác minh nguồn yêu cầu và thẩm quyền trước khi tiếp tục |
| Bằng chứng không đủ hoặc có kết quả trái ngược | Bổ sung đánh giá; không xác nhận đã đạt chỉ để kịp tiến độ |
| Quyết định hết hạn mà chưa rà soát | Thực hiện hành vi đã quy định khi hết hạn; không tự gia hạn |
| Thay đổi nhân sự khiến không còn đầu mối | Yêu cầu chỉ định và bàn giao được xác nhận |

Một thông báo đã gửi hoặc một cuộc họp đã diễn ra không tự tạo thành phê duyệt. Cần có kết quả, chủ thể quyết định, phạm vi và thời điểm đủ rõ để thực hiện.

### 10.3. Những yêu cầu quản trị có thể kiểm chứng

Ví dụ một tổ chức có thể đặc tả:

| Mã | Yêu cầu minh họa | Cách kiểm chứng |
| --- | --- | --- |
| GOV-RO-01 | Trước quyết định phát hành liên quan, mỗi rủi ro trong phạm vi phải có risk owner đã xác nhận nhận trách nhiệm và đường phê duyệt | Đối chiếu danh sách rủi ro với hồ sơ phân công và thẩm quyền |
| GOV-RO-02 | Rủi ro chỉ được ghi “đã kiểm chứng” khi có bằng chứng liên kết với yêu cầu, phiên bản và phạm vi | Thử cập nhật trạng thái khi thiếu từng thành phần; hệ thống hoặc quy trình phải chặn |
| GOV-RO-03 | Quyết định chấp nhận phải có người phê duyệt đủ quyền, phạm vi, điều kiện và thời hạn | Kiểm tra hồ sơ; thử vai trò không đủ quyền hoặc quyết định thiếu thời hạn theo chính sách |
| GOV-RO-04 | Thay đổi ảnh hưởng ranh giới tổ chức hoặc đường xuất dữ liệu phải dẫn tới đánh giá lại trước khi mở phạm vi mới | Dùng một thay đổi mẫu, đối chiếu kết quả đánh giá và quyết định mở chức năng |

Các yêu cầu này cần được hiện thực hóa bằng quy trình hoặc công cụ phù hợp. Một trường bắt buộc chỉ kiểm tra có dữ liệu; việc người được ghi thực sự có thẩm quyền vẫn cần cơ chế xác nhận.

### 10.4. Chỉ số hỗ trợ quản lý trách nhiệm

Có thể theo dõi:

- Số rủi ro chưa có owner được xác nhận.
- Số phương án xử lý quá hạn theo mức ưu tiên.
- Số quyết định chấp nhận sắp hết hoặc đã hết hiệu lực.
- Số yêu cầu xử lý rủi ro chưa có chủ sở hữu kiểm soát.
- Số kết luận rủi ro còn lại thiếu bằng chứng cần thiết.
- Thời gian từ khi phát hiện thay đổi quan trọng tới lúc có đánh giá lại.

Ví dụ:

> Tỷ lệ rủi ro có owner hợp lệ = số rủi ro trong phạm vi có người đã nhận trách nhiệm và đường quyết định phù hợp / tổng số rủi ro đang cần quản lý trong cùng phạm vi.

Mẫu số cần phản ánh rủi ro thực tế đang quản lý, bao gồm rủi ro vừa được nhận diện. Không chỉ lấy những mục đã hoàn tất phân công.

Số rủi ro được đóng không nên được xem riêng là bằng chứng quản lý tốt. Cần xem căn cứ đóng, tình trạng kiểm soát và các sự kiện buộc phải mở lại.

## 11. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Giao mọi rủi ro cho nhóm bảo mật | Quyết định nghiệp vụ không có người đủ quyền | Chọn owner theo tác động và quyền điều phối |
| Gán owner là người đang sửa ticket | Có người thực hiện nhưng thiếu người quyết định về hậu quả | Tách công việc kỹ thuật với quản lý rủi ro |
| Ghi “các nhóm liên quan” | Khi chậm tiến độ không ai điều phối | Có đầu mối chịu trách nhiệm và phụ thuộc rõ |
| Chọn người không có quyền và không có đường chuyển cấp | Trách nhiệm tồn tại trên giấy | Ghi giới hạn quyền, nguồn lực và cấp quyết định |
| Dùng rủi ro mục tiêu làm rủi ro còn lại | Chấp nhận dựa trên kế hoạch chưa kiểm chứng | Đánh giá lại bằng bằng chứng thực tế |
| Cho rằng ký chấp nhận có thể miễn mọi yêu cầu | Vượt thẩm quyền hoặc bỏ qua điều kiện bắt buộc | Xác minh nguồn yêu cầu và quyền miễn trừ |
| Đánh giá mọi kiểm soát bằng một lần quét | Bỏ sót logic quyền, tác vụ nền và cấu hình | Chọn bằng chứng theo kịch bản và mức đảm bảo |
| Coi quyết định chấp nhận có hiệu lực mãi | Thay đổi lớn vẫn dựa trên căn cứ cũ | Có thời hạn, điều kiện và sự kiện đánh giá lại |
| Chuyển cho nhà cung cấp rồi bỏ theo dõi | Không ai quản lý hậu quả còn lại đối với tổ chức | Giữ owner nội bộ và kiểm tra cam kết |
| Đóng rủi ro khi ticket hoàn tất | Công việc xong nhưng điều kiện an toàn chưa được chứng minh | Tách trạng thái triển khai, xác minh và quyết định |
| Thay owner bằng cách sửa tên | Mất lịch sử, công việc hoặc ngoại lệ đang có | Bàn giao được xác nhận và giữ dấu vết |
| Báo “chưa xảy ra sự cố” làm bằng chứng đủ | Không biết kiểm soát có thực sự ngăn được kịch bản | Dùng kiểm thử, rà soát và dữ liệu vận hành phù hợp |

## 12. Bài tập vận dụng

Một dịch vụ báo cáo cho nhiều khách hàng vừa bổ sung chức năng tải dữ liệu hàng loạt. Người trưởng nhóm kiểm thử được điền làm risk owner vì là người phát hiện lỗi.

Người này có thể yêu cầu chạy lại kiểm thử nhưng không điều phối được nhóm phát triển, không quyết định phạm vi phát hành và không có quyền đề xuất nguồn lực. Ticket sửa API đã đóng. Chưa có kiểm thử đường tải tệp và tác vụ nền. Bảng rủi ro ghi mức còn lại là thấp vì “đã sửa lỗi”.

Nhóm dự định mở chức năng vào ngày hôm sau và đề nghị trưởng nhóm kiểm thử ký chấp nhận.

Hãy thực hiện:

1. Xác định những khoảng trống về owner, thẩm quyền và bằng chứng.
2. Đề xuất vai trò có thể làm risk owner và cách xác nhận phù hợp.
3. Phân công chủ sở hữu kiểm soát cho API, tác vụ nền và kho tệp.
4. Viết hai yêu cầu bảo mật với tiêu chí chấp nhận.
5. Nêu quyết định hiện tại có thể đưa ra và thông tin cần bổ sung trước khi mở chức năng.
6. Đề xuất hai sự kiện làm quyết định sau này phải được đánh giá lại.

### Gợi ý tự đối chiếu

- Người phát hiện lỗi không mặc nhiên phù hợp làm risk owner. Cần kiểm tra quyền quản lý tác động, khả năng điều phối và đường chuyển cấp.
- Người phụ trách sản phẩm hoặc nghiệp vụ báo cáo có thể phù hợp nếu được giao đúng phạm vi và thẩm quyền. Không chỉ đổi chức danh trong bảng; người nhận cần xác nhận trách nhiệm.
- Nhóm API, nhóm tác vụ và nhóm lưu trữ có thể sở hữu các kiểm soát thành phần. Risk owner theo dõi toàn bộ phương án xử lý.
- Một yêu cầu có thể buộc kiểm tra quyền trên tệp tại lượt tải; thử chuyển liên kết cho tài khoản khách hàng khác phải không nhận được nội dung.
- Một yêu cầu khác có thể buộc tác vụ nền xác minh phạm vi dữ liệu trước khi tạo tệp; thử thay mã khách hàng hoặc thay đổi quyền sau khi xếp hàng phải cho kết quả theo chính sách.
- Mức thấp hiện được ghi chưa có đủ căn cứ vì còn đường chưa kiểm chứng. Cần bổ sung bằng chứng, đánh giá lại hoặc chọn phạm vi vận hành hạn chế đã được phê duyệt.
- Trưởng nhóm kiểm thử chỉ ký chấp nhận nếu được giao đúng thẩm quyền và các điều kiện cần thiết đã thỏa. Chữ ký để kịp ngày phát hành không giải quyết khoảng trống.
- Thay mô hình khách hàng, thêm đường tải, thay quyền hoặc phát hiện lỗi cách ly là các sự kiện cần đánh giá lại.

## 13. Sản phẩm đầu ra của bài học

Với một rủi ro bảo mật cụ thể, người học cần tạo được:

1. Mô tả kịch bản có tài sản, điều kiện, hậu quả và phạm vi.
2. Phân công risk owner được xác nhận, cùng giới hạn quyết định và đường chuyển cấp.
3. Phương án xử lý có chủ sở hữu kiểm soát, người thực hiện và thời hạn.
4. Các yêu cầu bảo mật gắn với kiểm thử và mức bằng chứng cần thiết.
5. Đánh giá rủi ro còn lại tách khỏi mục tiêu dự kiến.
6. Hồ sơ quyết định đúng thẩm quyền, có điều kiện và thời hạn.
7. Cơ chế theo dõi, bàn giao và đánh giá lại sau thay đổi.

Kết quả phải giúp trả lời được: **ai đang chịu trách nhiệm quản lý rủi ro, ai làm các kiểm soát, ai được quyết định chấp nhận, quyết định dựa trên bằng chứng nào và điều gì sẽ buộc phải xem xét lại**.
