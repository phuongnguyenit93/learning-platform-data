# Identity proofing privacy: bảo vệ dữ liệu khi xác minh danh tính

## 1. Xác minh danh tính tạo ra một vùng dữ liệu nhạy cảm

Identity proofing là quá trình thiết lập mức tin cậy rằng một chủ thể có mối liên hệ phù hợp với danh tính hoặc những thuộc tính mà họ khai báo. Tùy dịch vụ, quá trình này có thể dựa vào tài liệu, nguồn dữ liệu đáng tin cậy, một bên xác minh hoặc sự kết hợp nhiều phương thức.

Trong IAM, xác minh danh tính có thể hỗ trợ tạo tài khoản, liên kết với hồ sơ có sẵn, khôi phục truy cập hoặc thực hiện một nghiệp vụ cần mức tin cậy cao hơn. Nó không nhất thiết phải xuất hiện ở mọi lần đăng nhập.

Quá trình này có thể thu thập ảnh giấy tờ, ảnh khuôn mặt, video, thông tin liên hệ hoặc thuộc tính cá nhân. Những dữ liệu đó có thể bị sao chép, liên kết hoặc sử dụng ngoài mục đích nếu thiết kế chỉ chú ý tới kết quả “xác minh thành công”.

Identity proofing privacy là việc kiểm soát dữ liệu và tác động tới quyền riêng tư trong toàn bộ quá trình: quyết định có cần xác minh không, cần chứng cứ nào, ai được xem, bên nào nhận dữ liệu và khi nào dữ liệu kết thúc vòng đời.

Ví dụ xuyên suốt: An Bình cung cấp cổng quản lý hợp đồng. Một số thao tác cần xác nhận người dùng có liên hệ với hồ sơ đối tác đã tồn tại. Nhóm IAM cần đạt mục tiêu đó mà không biến mọi tài khoản thành một kho lưu đầy đủ giấy tờ cá nhân.

## 2. Phân biệt proofing, authentication và authorization

Ba hoạt động này có liên quan nhưng không thay thế nhau:

| Hoạt động | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| Identity proofing | Có cơ sở nào để tin chủ thể gắn với danh tính hoặc thuộc tính được khai báo? | Đối chiếu chứng cứ và xác minh người đang làm thủ tục có liên hệ phù hợp |
| Authentication | Chủ thể hiện tại có chứng minh được quyền kiểm soát phương tiện xác thực đã gắn với tài khoản không? | Đăng nhập bằng khóa xác thực hoặc các yếu tố đã đăng ký |
| Authorization | Chủ thể được phép làm gì trong ngữ cảnh hiện tại? | Được xem hoặc phê duyệt một hợp đồng cụ thể |

Một tài khoản đã xác minh danh tính không mặc nhiên được cấp quyền quản trị. Một phiên đăng nhập có MFA cũng không tự chứng minh mọi thuộc tính trong hồ sơ là đúng.

Tương tự, xác minh một thuộc tính không đồng nghĩa đã xác minh mọi khía cạnh của một con người. Có thể chỉ cần xác nhận người đó thuộc một tổ chức, vượt một ngưỡng tuổi hoặc có liên hệ với một hồ sơ cụ thể.

Cần đặt tên kết quả theo phạm vi thực sự được kiểm tra. Một cờ chung như “verified user” dễ bị các dịch vụ hiểu rộng hơn bằng chứng ban đầu.

## 3. Bắt đầu bằng câu hỏi có cần thu thập danh tính thật không

Không phải mọi tài khoản đều cần giấy tờ hoặc tên ngoài đời. Mức xác minh nên phục vụ nhu cầu của luồng và tác động khi nhận diện sai.

Một số câu hỏi thiết kế:

- Nghiệp vụ cần biết chính xác người này là ai hay chỉ cần một thuộc tính?
- Có thể dùng tài khoản của tổ chức hoặc một nguồn tin cậy đã có không?
- Có thể xác minh quan hệ với hồ sơ mà không nhận bản sao toàn bộ giấy tờ không?
- Dữ liệu đã có ở nơi khác có thực sự cần được sao chép về IAM không?
- Phương thức được chọn có phù hợp với những nhóm người dùng thực tế không?
- Nếu không xác minh được, có đường xử lý khác với phạm vi rõ ràng không?

Ví dụ, một diễn đàn nội bộ chỉ cần kiểm tra thành viên còn thuộc tổ chức có thể không cần thu ảnh giấy tờ cá nhân. Một luồng khác cần đối chiếu người đại diện với hồ sơ đối tác có thể cần chứng cứ khác.

Không dùng quy tắc “càng nhiều tài liệu càng an toàn” như một mặc định. Thu thêm dữ liệu làm tăng lượng thông tin cần bảo vệ, nhưng chưa chắc làm tăng độ tin cậy đúng với rủi ro cần xử lý.

Nếu cần nâng mức xác minh ở một thời điểm, có thể tổ chức luồng riêng cho thao tác đó. Không nhất thiết yêu cầu toàn bộ người dùng nộp cùng một tập chứng cứ ngay khi tạo tài khoản.

## 4. Xem quyền riêng tư theo từng bước của quy trình

Một quy trình minh họa:

~~~mermaid
flowchart TD
    A[Xác định mục tiêu và phạm vi] --> B[Chọn phương thức và chứng cứ cần thiết]
    B --> C[Thu thập có kiểm soát]
    C --> D[Kiểm tra chứng cứ và nguồn]
    D --> E[Xác minh liên hệ với chủ thể]
    E --> F[Ra quyết định theo phạm vi]
    F --> G[Gắn kết quả với đúng tài khoản]
    G --> H[Kết thúc vòng đời dữ liệu tạm và lưu phần cần thiết]
~~~

Mỗi bước có rủi ro riêng:

| Bước | Vấn đề riêng tư cần kiểm soát |
| --- | --- |
| Chọn chứng cứ | Thu quá nhiều thông tin so với mục tiêu |
| Thu thập | Tải nhầm, truyền qua kênh không phù hợp hoặc lộ trong log |
| Kiểm tra chứng cứ | Trích xuất thêm trường không cần thiết |
| Xác minh liên hệ với chủ thể | Thu ảnh hoặc sinh trắc học vượt nhu cầu |
| Ra quyết định | Biến đánh giá cục bộ thành hồ sơ suy luận quá rộng |
| Gắn kết quả | Liên kết nhầm tài khoản hoặc tạo định danh dùng chung ngoài dự kiến |
| Lưu giữ và kết thúc | Bản sao tạm, dữ liệu bên nhận hoặc backup tồn tại lâu hơn thiết kế |

Kiểm tra tài liệu có vẻ hợp lệ và xác minh người đang làm thủ tục có liên hệ với tài liệu là những việc khác nhau. Chỉ kiểm tra được một bước thì không nên ghi kết quả như đã hoàn tất toàn bộ quá trình.

Một kết quả không xác định cũng cần được thể hiện riêng với kết quả bị từ chối. Lỗi mạng, ảnh không đọc được và chứng cứ không đạt điều kiện không phải cùng một nguyên nhân.

## 5. Giảm thiểu chứng cứ và thuộc tính được xử lý

Với mỗi trường dữ liệu, nên xác định câu hỏi mà trường đó giúp trả lời.

| Nhu cầu | Hướng giảm dữ liệu cần xem xét |
| --- | --- |
| Kiểm tra một ngưỡng tuổi | Nhận kết quả đáp ứng ngưỡng nếu phù hợp, thay vì chuyển ngày sinh tới mọi ứng dụng |
| Xác minh quan hệ với tổ chức | Dùng thuộc tính hoặc xác nhận từ nguồn tổ chức có thẩm quyền |
| Đối chiếu hồ sơ đã có | Dùng những trường cần cho phép đối chiếu, không sao chép toàn bộ hồ sơ |
| Giải thích một quyết định | Giữ kết quả và tham chiếu cần thiết thay vì mặc định giữ ảnh chứng cứ |
| Ngăn sử dụng lặp không phù hợp | Xác định cơ chế và phạm vi đối chiếu riêng, tránh tạo kho định danh chung không kiểm soát |

Bảng nêu các lựa chọn thiết kế, không khẳng định lúc nào cũng có thể loại bỏ dữ liệu gốc. Một bước kiểm tra có thể cần tiếp cận dữ liệu chi tiết trong thời gian xử lý. Khi đó, cần giới hạn nơi xử lý, người xem và thời gian tồn tại của dữ liệu.

Che hoặc cắt bớt trường trên tài liệu chỉ phù hợp nếu phương thức kiểm tra vẫn thực hiện được đúng mục tiêu. Không hướng dẫn người dùng tự loại bỏ những phần mà quy trình thực sự cần để đánh giá chứng cứ.

Dữ liệu OCR cũng là một bản sao cần quản lý. Xóa ảnh nhưng giữ toàn bộ văn bản trích xuất trong một bảng khác chưa làm lượng thông tin được giữ giảm đi như mong muốn.

Dữ liệu dẫn xuất, như điểm so khớp, dấu hiệu nghi ngờ hoặc quan hệ giữa các hồ sơ, cũng có thể nhạy cảm. Không chỉ lập danh mục cho ảnh đầu vào mà bỏ qua những kết quả được tạo trong quá trình xử lý.

## 6. Thu thập và lưu tạm theo đúng phiên xác minh

Dữ liệu nộp lên cần được gắn với đúng chủ thể và đúng phiên proofing. Một file được tải thành công chưa có nghĩa nó đã thuộc về tài khoản đúng.

Các kiểm soát kỹ thuật cần xem xét gồm:

- Xác thực hoặc xác nhận ngữ cảnh phù hợp trước khi cho nộp chứng cứ.
- Ràng buộc lượt tải lên với phiên xác minh phía server.
- Giới hạn loại tệp, dung lượng và số lần thử theo thiết kế.
- Dùng định danh lưu trữ không chứa số giấy tờ hoặc thông tin cá nhân.
- Kiểm soát quyền đọc đối tượng và thời hạn truy cập.
- Bảo vệ dữ liệu khi truyền và lưu.
- Tách khu vực dữ liệu tạm khỏi nơi lưu kết quả lâu hơn.

Nếu sử dụng đường dẫn tải lên có khả năng cấp quyền truy cập, đường dẫn đó cần được bảo vệ như một thông tin nhạy cảm. Không đưa nó vào log chung, công cụ phân tích trang hoặc thông báo hỗ trợ có phạm vi người xem rộng.

Không lưu ảnh giấy tờ vào đường dẫn công khai chỉ vì tên file khó đoán. Khó đoán tên không thay thế kiểm tra quyền.

Luồng xử lý cũng cần quản lý các bản sao trung gian: file tạm của bộ xử lý ảnh, văn bản OCR, cache trình xem tài liệu, hàng đợi và đầu vào gửi tới nhà cung cấp xác minh.

Với một lần thử bị hủy hoặc hết hạn, cần có cơ chế kết thúc dữ liệu tạm. Không để file chỉ bị “mất liên kết với phiên” rồi tồn tại vô hạn trong kho lưu trữ.

## 7. Sinh trắc học cần được đánh giá theo nhu cầu cụ thể

Một số quy trình có thể dùng ảnh khuôn mặt, so khớp với ảnh trên tài liệu hoặc kiểm tra dấu hiệu người thật. Những phương thức này tạo thêm dữ liệu và rủi ro cần đánh giá.

Cần phân biệt ảnh đầu vào, video, đặc trưng hoặc mẫu sinh trắc được suy ra và kết quả so khớp. Chúng không phải cùng một loại dữ liệu và có thể tồn tại ở các hệ thống khác nhau.

Những câu hỏi cần làm rõ:

| Câu hỏi | Ý nghĩa đối với thiết kế |
| --- | --- |
| Vì sao cần phương thức này? | Tránh thu sinh trắc chỉ vì tích hợp có sẵn |
| Phương thức kiểm tra được điều gì? | Không diễn giải điểm so khớp thành bảo đảm tuyệt đối |
| Dữ liệu gốc và mẫu được lưu ở đâu? | Xác định phạm vi cần bảo vệ và kết thúc vòng đời |
| Có chuyển tới bên khác không? | Kiểm soát bản sao và cách sử dụng tiếp theo |
| Người không thực hiện được có đường thay thế nào? | Giảm việc ép người dùng lặp lại một phương thức không phù hợp |
| Có dùng dữ liệu để phát triển mô hình không? | Nhận diện một hoạt động khác cần được xác lập riêng |

Ảnh hoặc đặc trưng khuôn mặt không thể được đổi đơn giản như đổi mật khẩu. Vì vậy, hậu quả của việc lộ dữ liệu cần được cân nhắc ngay từ lựa chọn kiến trúc.

Kiểm tra người thật và so khớp không phải bảo đảm không thể bị đánh lừa. Hệ thống cũng có thể từ chối nhầm hoặc không xử lý được do thiết bị, ánh sáng hoặc những điều kiện khác. Luồng xử lý cần phân biệt các trường hợp và có cách hỗ trợ phù hợp.

Một kết quả proofing không nên trở thành cơ sở để tự động gắn thêm các suy luận không cần thiết về người dùng. Dữ liệu được nộp để xác minh danh tính không mặc nhiên là dữ liệu huấn luyện hoặc phân tích cho mục tiêu khác.

## 8. Giới hạn nhà cung cấp và người đánh giá thủ công

Dùng một nhà cung cấp bên ngoài không làm biến mất trách nhiệm thiết kế đường đi của dữ liệu. Cần biết dữ liệu nào được gửi, bên nào thực sự xử lý và phần nào được giữ sau khi hoàn tất.

Các nội dung cần làm rõ với từng tích hợp:

- Tập dữ liệu đầu vào và kết quả đầu ra.
- Mục đích sử dụng của từng loại dữ liệu.
- Bản sao tạm, bản sao lưu và dữ liệu dẫn xuất.
- Quyền truy cập của người vận hành hoặc người đánh giá.
- Điều kiện lưu giữ, kết thúc và cách xác nhận.
- Việc sử dụng dữ liệu cho hoạt động khác.
- Cách xử lý lỗi, tranh chấp kết quả và sự cố dữ liệu.

Không gửi toàn bộ hồ sơ IAM chỉ để gọi một dịch vụ kiểm tra tài liệu. Bên nhận nên có đúng dữ liệu cần cho chức năng mà nó được giao.

Đánh giá thủ công có thể cần thiết trong một số luồng, nhưng tạo ra quyền xem dữ liệu nhạy cảm. Có thể giới hạn người đánh giá theo vai trò, vụ việc, thời gian và loại trường được xem.

Các thao tác mở chi tiết, bỏ che thông tin, tải xuống hoặc xuất hàng loạt cần có quyền riêng phù hợp. Người hỗ trợ tài khoản không mặc nhiên cần quyền tải mọi ảnh chứng cứ.

Nên tránh chuyển giấy tờ qua chat cá nhân hoặc đính kèm vào ticket chung để giải quyết nhanh một trường hợp. Cần có đường hỗ trợ trong phạm vi được kiểm soát, với khả năng đối chiếu ai đã xem dữ liệu và vì sao.

## 9. Lưu kết quả đúng phạm vi thay vì phân phối chứng cứ

Nhiều ứng dụng chỉ cần kết quả một phép xác minh, không cần ảnh giấy tờ hoặc dữ liệu sinh trắc đã dùng để tạo kết quả.

Một bản ghi kết quả minh họa:

~~~json
{
  "proofing_reference": "proof-example-42",
  "subject_reference": "subject-example-18",
  "workflow": "partner_account_linking",
  "outcome": "verified",
  "verified_attributes": [
    "association_with_existing_partner_record"
  ],
  "policy_version": "partner-linking-v3",
  "completed_at": "2026-01-15T08:30:00Z",
  "evidence_reference": "restricted-evidence-example-7",
  "retention_policy_reference": "partner-proofing-lifecycle"
}
~~~

Các giá trị là dữ liệu giả. Tham chiếu chứng cứ không được tự nó cấp quyền đọc chứng cứ.

Bản ghi trên nói về một mối liên hệ trong một luồng cụ thể. Nó không tuyên bố người dùng đã được xác minh mọi thuộc tính, đủ điều kiện cho mọi nghiệp vụ hoặc có quyền truy cập mọi hồ sơ đối tác.

Ứng dụng dùng kết quả cần biết:

| Nội dung | Lý do |
| --- | --- |
| Ai đưa ra kết quả | Xác định nguồn có được tin cậy cho mục tiêu này không |
| Kết quả gắn với tài khoản nào | Tránh sử dụng cho chủ thể khác |
| Thuộc tính hoặc quan hệ nào đã được kiểm tra | Tránh diễn giải quá phạm vi |
| Kết quả được tạo khi nào | Đánh giá độ mới theo chính sách |
| Quy trình và phiên bản nào được dùng | Hiểu cơ sở đánh giá |
| Bên nào được nhận và sử dụng | Hạn chế chuyển tiếp hoặc tái sử dụng |
| Trạng thái hiện tại của kết quả | Xử lý khi kết quả bị thay thế hoặc không còn được chấp nhận |

Nếu chuyển kết quả qua thông điệp hoặc assertion, cần kiểm tra tính toàn vẹn, nguồn phát hành, bên nhận, ràng buộc với chủ thể và thời gian theo cơ chế được chọn.

Tái sử dụng một kết quả phù hợp có thể giảm việc nộp lại chứng cứ, nhưng không nên trở thành định danh chung giúp mọi bên theo dõi cùng một cá nhân. Cần xem xét các tham chiếu riêng theo phạm vi và giới hạn khả năng liên kết.

## 10. Gắn kết quả với tài khoản mà không tạo đường chiếm đoạt

Proofing có thể đúng ở bước đánh giá chứng cứ nhưng sai khi liên kết tài khoản.

Ví dụ, tài liệu của một người được xác minh, nhưng kết quả lại gắn vào phiên do người khác kiểm soát. Hoặc một thao tác liên kết hai tài khoản sử dụng email trùng mà không có bằng chứng phù hợp về quyền kiểm soát và mối liên hệ.

Cần kiểm soát các điểm chuyển từ proofing sang tài khoản:

- Kết quả gắn với phiên và chủ thể nào ngay từ đầu.
- Khi nào được phép xác nhận liên kết.
- Ai có quyền thay đổi đích liên kết.
- Cách xử lý retry, hết hạn và kết quả đến muộn.
- Bằng chứng nào cần có khi kết hợp hoặc tách tài khoản.
- Thông báo nào giúp chủ tài khoản nhận ra thay đổi không mong muốn.

Không chỉ dựa vào một trường định danh có thể được thay đổi hoặc tái cấp để gắn chứng cứ với tài khoản lâu dài.

Thông báo cũng cần tiết chế dữ liệu. Thông báo một lượt xác minh hoặc liên kết tài khoản không cần đính kèm bản sao giấy tờ, số giấy tờ đầy đủ hoặc ảnh khuôn mặt.

Quy trình khôi phục sau khi mất phương tiện xác thực cần được đánh giá như một luồng riêng. Không tự động chấp nhận ảnh giấy tờ gửi cho bộ phận hỗ trợ như bằng chứng đủ để thay credential hoặc chiếm quyền kiểm soát tài khoản.

## 11. Vòng đời chứng cứ, dữ liệu dẫn xuất và audit

Không phải mọi loại dữ liệu trong proofing đều cần giữ cùng thời gian.

| Dữ liệu | Câu hỏi về vòng đời |
| --- | --- |
| Ảnh hoặc video đầu vào | Còn cần sau khi ra quyết định không? |
| Văn bản OCR | Có trường nào còn cần, và bản đầy đủ được xử lý ra sao? |
| Mẫu hoặc đặc trưng sinh trắc | Có cần lưu hay chỉ xử lý tạm? |
| Điểm và lý do quyết định | Giữ mức chi tiết nào để giải thích và đối chiếu? |
| Kết quả proofing | Còn được dùng cho luồng nào và tới điều kiện nào? |
| Audit truy cập chứng cứ | Giữ gì để kiểm soát việc xem và xử lý dữ liệu? |
| Bản sao tại bên cung cấp | Ai thực hiện kết thúc và có bằng chứng gì? |

Cần phân biệt việc làm một chứng cứ hết hiệu lực, cấm sử dụng kết quả và xóa dữ liệu lưu trữ. Đổi một cờ trạng thái chưa chứng minh dữ liệu đã bị xóa khỏi các bản sao.

Ngược lại, xóa chứng cứ không nhất thiết đồng nghĩa phải làm biến mất mọi dấu vết tối thiểu về việc một quyết định đã xảy ra. Phần còn giữ cần có mục đích, phạm vi, quyền và lịch kết thúc rõ ràng.

Không dùng lý do chống gian lận để mặc định lưu mọi tài liệu vô hạn. Nếu cần dữ liệu cho hoạt động đó, xác định cụ thể phần cần giữ, người được dùng và điều kiện xem xét lại.

Cần quản lý cả phiên bị hủy, bị từ chối và chưa hoàn tất. Những phiên này vẫn có thể chứa tài liệu thật của người dùng.

Đối với backup và phục hồi, phải tính tới khả năng dữ liệu đã kết thúc vòng đời xuất hiện trở lại. Quy trình phục hồi cần áp dụng những giới hạn hiện hành trước khi đưa dữ liệu trở lại luồng sử dụng.

## 12. Cung cấp thông tin và đường hỗ trợ có ý nghĩa

Người dùng nên hiểu họ được yêu cầu làm gì trước khi nộp dữ liệu, thay vì chỉ thấy một nút chấp nhận chung.

Những nội dung cần diễn đạt rõ gồm:

- Mục đích của lần xác minh.
- Loại chứng cứ hoặc thuộc tính cần cung cấp.
- Bên nào tham gia xử lý.
- Dữ liệu nào được giữ và vòng đời được quản lý như thế nào.
- Điều gì xảy ra khi quá trình không hoàn tất.
- Đường hỗ trợ hoặc phương thức khác khi phù hợp.

Giải thích rõ không tự thay thế các kiểm soát kỹ thuật. Một màn hình mô tả dữ liệu chỉ dùng cho xác minh phải phù hợp với cấu hình thực tế của hệ thống và bên cung cấp.

Không yêu cầu người dùng tiếp tục tải thêm tài liệu mà không nêu được thông tin còn thiếu. Việc thử lại nhiều lần có thể làm lượng dữ liệu tăng lên trong khi không giải quyết được nguyên nhân thất bại.

Cần có cách xử lý kết quả không xác định hoặc bị đánh giá sai, với quyền xem dữ liệu giới hạn cho người hỗ trợ. Sửa một sai sót không nên đòi hỏi người dùng gửi chứng cứ qua một kênh ít kiểm soát hơn.

## 13. Tình huống tại An Bình

An Bình ban đầu nhận ảnh giấy tờ qua ticket hỗ trợ để liên kết người dùng với hồ sơ đối tác. Ảnh được lưu trong ticket, văn bản OCR ở một bảng riêng và toàn bộ kết quả được đưa vào log.

Thiết kế này tạo ra nhiều bản sao mà người vận hành khó xác định hết. Mỗi lần xử lý lỗi, thêm nhân viên lại có thể xem tài liệu.

Nhóm IAM chuyển sang luồng có phạm vi rõ:

| Thành phần | Cách xử lý |
| --- | --- |
| Bước bắt đầu | Xác định rõ phiên và hồ sơ đối tác cần liên kết |
| Thu thập | Nhận chứng cứ qua luồng được kiểm soát |
| Xử lý | Chỉ gửi trường cần thiết tới thành phần xác minh |
| Hỗ trợ | Cho người được giao vụ việc xem phần cần thiết |
| Kết quả cho ứng dụng | Trả quan hệ đã xác minh và tham chiếu phù hợp |
| Log | Ghi mốc xử lý, kết quả và tham chiếu, không ghi ảnh hoặc OCR đầy đủ |
| Kết thúc | Dọn dữ liệu tạm và áp dụng vòng đời cho phần được giữ |

Một ứng dụng khác sau đó muốn dùng ảnh đã nộp để cá nhân hóa giao diện. Nhóm không coi việc ảnh đang tồn tại là đủ để chuyển nó. Đề xuất sử dụng mới được xem xét trước khi có thay đổi luồng dữ liệu.

Khi nhà cung cấp trả lỗi không xác định, hệ thống ghi đúng trạng thái và hướng người dùng tới bước hỗ trợ thích hợp. Nó không mặc định coi người dùng gian lận hoặc yêu cầu lặp lại vô hạn cùng một phương thức.

Ứng dụng hợp đồng chỉ nhận kết quả cần cho việc liên kết hồ sơ. Quyền xem hoặc phê duyệt hợp đồng vẫn được đánh giá riêng theo chính sách truy cập.

## 14. Những điểm cần kiểm tra trong thiết kế

| Tình huống | Điều cần bảo đảm |
| --- | --- |
| Một luồng không cần danh tính thật | Không tự thu giấy tờ chỉ vì chức năng có sẵn |
| Người dùng nộp chứng cứ | File gắn với đúng phiên và không công khai |
| Tài liệu có nhiều trường | Chỉ xử lý và chuyển tiếp phần cần thiết |
| OCR hoặc xử lý ảnh tạo file trung gian | Bản sao trung gian có quyền và vòng đời |
| Có so khớp khuôn mặt | Phân biệt dữ liệu gốc, đặc trưng và kết quả |
| Nhân viên hỗ trợ mở hồ sơ | Quyền và audit phù hợp với vụ việc |
| Nhà cung cấp hoàn tất xử lý | Biết dữ liệu còn ở đâu và được dùng thế nào |
| Kết quả được gửi sang ứng dụng | Phạm vi, nguồn, chủ thể và độ mới được kiểm tra |
| Phiên bị hủy hoặc hết hạn | Dữ liệu tạm không bị bỏ lại vô thời hạn |
| Có đề xuất tái sử dụng dữ liệu | Xem xét trước khi sao chép hoặc phân phối |
| Khôi phục dữ liệu từ backup | Giới hạn và vòng đời hiện hành tiếp tục được áp dụng |
| Kiểm tra log và telemetry | Không xuất hiện credential, ảnh hoặc hồ sơ dư thừa |

Bảo vệ quyền riêng tư trong identity proofing bắt đầu từ việc chỉ xác minh điều thực sự cần và kết thúc bằng kiểm soát những dữ liệu còn lại sau quyết định. Một kết quả đáng tin cậy, đúng phạm vi và gắn với đúng tài khoản thường hữu ích cho IAM hơn việc phân phối rộng rãi toàn bộ chứng cứ đã dùng để tạo ra nó.
