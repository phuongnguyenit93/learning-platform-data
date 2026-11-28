# Notice requirement — Đặc tả thông báo về xử lý dữ liệu cá nhân

## 1. Từ “có trang chính sách” đến yêu cầu bảo mật có thể kiểm chứng

Một ứng dụng có đường dẫn “Chính sách riêng tư” ở cuối trang. Người dùng tải một tệp lên để nhờ hỗ trợ, nhưng không biết tệp được chuyển sang dịch vụ lưu trữ nào, ai có thể đọc và dữ liệu được giữ bao lâu. Trong khi đó, một SDK phân tích đã khởi chạy trước khi người dùng nhìn thấy bất kỳ giải thích nào.

Việc có một trang chính sách không tự chứng minh người dùng đã được thông báo đúng lúc hoặc thông báo phản ánh đúng hoạt động của hệ thống.

**Notice requirement** là yêu cầu xác định thông tin nào về xử lý dữ liệu phải được truyền đạt, cho ai, tại điểm nào trong hành trình, bằng hình thức nào và với bằng chứng gì. Trong chương Privacy requirement, đây là cách chuyển mục tiêu minh bạch thành hành vi sản phẩm, quyết định kiến trúc và tiêu chí nghiệm thu.

Một yêu cầu yếu:

> Hệ thống phải hiển thị chính sách riêng tư.

Một yêu cầu có thể kiểm chứng:

> Tại bước đính kèm tệp của phiếu hỗ trợ, giao diện phải hiển thị thông báo ngữ cảnh đang có hiệu lực trước khi gửi nội dung tệp. Thông báo nêu dữ liệu được gửi, mục đích sử dụng, nhóm được truy cập, nguyên tắc lưu giữ và đường dẫn tới thông tin đầy đủ. Nếu không tải được phiên bản thông báo phù hợp, thao tác gửi tệp phải bị chặn theo hợp đồng của chức năng.

Yêu cầu sau cho biết điểm áp dụng, dữ liệu, thời điểm, nội dung và hành vi lỗi. Người phát triển biết cần sửa luồng nào; người kiểm thử có thể quan sát request tải lên và phần thông báo tương ứng.

Bài học xây dựng đặc tả sản phẩm và kỹ thuật. Những nội dung phụ thuộc chính sách áp dụng, thị trường, quan hệ với người có dữ liệu hoặc nghĩa vụ cụ thể phải được chủ sở hữu chính sách xác nhận. Không tự suy ra rằng một mẫu thông báo hoặc một thời hạn minh họa trong bài đáp ứng mọi bối cảnh.

## 2. Phân biệt thông báo, đồng ý và quyền thực hiện thao tác

Các khái niệm sau có thể xuất hiện cùng một màn hình nhưng giải quyết các câu hỏi khác nhau:

| Thành phần | Câu hỏi chính | Ví dụ |
|---|---|---|
| Thông báo về xử lý dữ liệu | Hệ thống làm gì với dữ liệu và người dùng cần biết gì? | Giải thích việc gửi tệp cho nhóm hỗ trợ |
| Lựa chọn hoặc đồng ý | Người dùng đã thực hiện lựa chọn nào cho một mục đích theo chính sách áp dụng? | Bật nhận nội dung giới thiệu sản phẩm |
| Xác thực | Caller là ai? | Phiên đăng nhập của nhân viên |
| Phân quyền | Caller được thực hiện thao tác nào trên đối tượng nào? | Nhân viên chỉ đọc tệp của phiếu được giao |
| Hợp đồng nghiệp vụ | Thao tác có đáp ứng điều kiện của chức năng không? | Chỉ nhận loại tệp và kích thước được hỗ trợ |

Thông báo đã hiển thị không đồng nghĩa người dùng đã đồng ý. Người dùng đã bấm một nút cũng không đồng nghĩa mọi mục đích xử lý đều được phép. Đồng ý, khi được chọn làm điều kiện xử lý cho một mục đích, cần yêu cầu và bằng chứng riêng.

Không đặt một checkbox “Tôi đã đọc” rồi dùng cùng giá trị đó để mở quyền quảng cáo, chia sẻ dữ liệu và truy cập hồ sơ. Một sự kiện giao diện không thay thế quyết định chính sách hoặc kiểm tra quyền phía server.

Ngược lại, không mặc định mọi xử lý dữ liệu đều cần cùng một cơ chế đồng ý. Đặc tả phải tách việc thông báo khỏi điều kiện cho phép xử lý đã được xác định cho từng mục đích.

Ví dụ, nút “Gửi tệp” biểu đạt hành động gửi tệp của chức năng hỗ trợ. Việc bấm nút này không tự tạo sự đồng ý cho một SDK quảng cáo không liên quan.

## 3. Xác định mục tiêu, rủi ro và phạm vi của thông báo

### 3.1. Mục tiêu minh bạch phải gắn với hoạt động thực tế

Một số mục tiêu có thể chuyển thành yêu cầu:

- Người dùng biết loại dữ liệu nào sắp rời khỏi thiết bị trong thao tác đang thực hiện.
- Người dùng phân biệt được thông tin cần cho chức năng với mục đích tùy chọn.
- Thông báo đang hiển thị khớp với cấu hình xử lý dữ liệu đang hoạt động.
- Người dùng tìm được thông tin chi tiết và kênh liên hệ mà không phải đoán.
- Nhóm vận hành xác định được phiên bản thông báo đã được cung cấp tại thời điểm có vấn đề.
- Thay đổi luồng xử lý không đi vào hoạt động với thông báo lỗi thời.

Không đặt mục tiêu “mọi người đều đọc hết chính sách”. Hệ thống có thể cung cấp nội dung, kiểm tra khả năng tiếp cận và nghiên cứu mức hiểu; không thể suy ra sự hiểu đầy đủ của từng người từ một lượt mở trang.

### 3.2. Từ rủi ro đến điểm kiểm soát

| Rủi ro | Yêu cầu cần đặc tả | Bằng chứng phù hợp |
|---|---|---|
| Thu thập xảy ra trước giải thích cần thiết | Gắn thông báo vào đúng điểm bắt đầu luồng | Thứ tự hiển thị và request trên luồng thử |
| Nội dung chung không phản ánh chức năng | Liên kết thông báo với mục đích và loại dữ liệu | Bảng truy vết tới danh mục xử lý |
| Người dùng tưởng gửi tệp đồng nghĩa bật quảng cáo | Tách thông báo và lựa chọn theo mục đích | Kiểm tra trạng thái lựa chọn trước và sau thao tác |
| SDK mới hoạt động nhưng thông báo cũ | Kiểm soát phát hành chung giữa cấu hình và nội dung | Kiểm thử tổ hợp phiên bản và feature flag |
| Cache phục vụ sai nội dung cho tenant hoặc ngôn ngữ | Xác định biến thể và khóa cache đầy đủ | Ca thử nhiều tenant, locale và cấu hình |
| Không mở được thông tin đầy đủ bằng bàn phím | Thiết kế khả năng tiếp cận theo hành trình | Kiểm thử bàn phím và công cụ hỗ trợ |
| Bằng chứng thông báo chứa thêm dữ liệu cá nhân | Giảm dữ liệu và thời hạn lưu của telemetry | Schema sự kiện và kiểm tra log thực tế |
| Bản thông báo bị thay bằng nội dung giả | Quản lý quyền sửa, nguồn nội dung và phát hành | Lịch sử phê duyệt, kiểm tra toàn vẹn bản phát hành |

Thông báo không tự ngăn mọi lạm dụng dữ liệu. Nó phải đi cùng kiểm soát thu thập, phân quyền, chia sẻ, lưu giữ, logging và phục hồi tương ứng.

## 4. Lấy đầu vào từ danh mục xử lý dữ liệu

Không bắt đầu bằng cách sao chép một chính sách dài rồi thêm tên sản phẩm. Trước hết cần biết hệ thống thực sự xử lý gì.

Một bảng đầu vào cho chức năng có thể gồm:

| Thuộc tính | Câu hỏi cần trả lời |
|---|---|
| Người hoặc nhóm liên quan | Người đăng ký, khách hàng hiện hữu, nhân viên hay người có dữ liệu do bên khác cung cấp? |
| Nguồn dữ liệu | Người dùng nhập trực tiếp, thiết bị gửi, hệ thống tích hợp hay bản ghi import? |
| Loại dữ liệu | Nội dung tệp, địa chỉ liên hệ, định danh thiết bị hoặc metadata nào? |
| Mục đích | Mỗi loại dữ liệu phục vụ chức năng cụ thể nào? |
| Thời điểm bắt đầu | Lúc mở trang, chọn tệp, bấm gửi hay khi job chạy? |
| Đích và bên tiếp cận | Dịch vụ nội bộ, đơn vị vận hành, nhà cung cấp hoặc bên nhận nào? |
| Lưu giữ | Chính sách, mốc tính thời gian và các bản sao được quản lý ra sao? |
| Điều kiện xử lý | Điều kiện chính sách và lựa chọn nào phải được thỏa mãn? |
| Điều khiển của người dùng | Có thể bỏ qua, đổi lựa chọn, yêu cầu hỗ trợ hoặc dùng phương án khác không? |
| Ngoại lệ | Xử lý lỗi, backup, phiếu đang tranh chấp hoặc tình huống đặc biệt nào đã được xác định? |
| Chủ sở hữu | Ai xác nhận nội dung và ai chịu trách nhiệm luồng kỹ thuật? |

Từ bảng này, xác định thông tin cần hiện trong thông báo ngắn và thông tin cần có trong phần đầy đủ.

Nếu đội kỹ thuật chưa biết dữ liệu giữ bao lâu, không nên tự viết “chỉ giữ trong thời gian cần thiết” như cách giải quyết thiếu quyết định. Cần một chính sách có thể thực thi và được phê duyệt; thông báo phải mô tả chính sách đó ở mức người dùng hiểu được.

Không tự đưa một nhà cung cấp hoặc một loại xử lý vào thông báo chỉ vì sản phẩm có thể dùng trong tương lai. Mặt khác, không bỏ qua một đường xử lý đang hoạt động chỉ vì nó nằm trong job nền thay vì giao diện chính.

## 5. Xác định ai cần được thông báo và tại điểm nào

### 5.1. Người dùng giao diện không phải lúc nào cũng là người có dữ liệu

Một nhân viên có thể nhập hồ sơ của khách hàng, một doanh nghiệp có thể import danh sách nhân sự hoặc một người dùng có thể gửi tệp chứa thông tin của người khác.

Đặc tả cần xác định:

- Nhóm nào nhận thông báo trực tiếp trong sản phẩm.
- Có nhóm người có dữ liệu không đi qua giao diện hay không.
- Bên nào chịu trách nhiệm cung cấp thông tin cho các nhóm đó theo chính sách áp dụng.
- Kênh cung cấp thông tin, điều kiện kích hoạt và cách ghi nhận cần thiết.
- Giới hạn của bằng chứng khi thông báo được cung cấp qua một bên khác.

Không suy ra rằng hiển thị một modal cho người import đã thông báo cho mọi người xuất hiện trong file. Cũng không tự chọn gửi email hàng loạt như một hành động kỹ thuật mặc định; kênh và trách nhiệm phải được xác định trong thiết kế.

### 5.2. Lập bản đồ điểm bắt đầu xử lý

```text
Mở ứng dụng
    -> tải tài nguyên và tạo request kỹ thuật
    -> có thể khởi tạo SDK theo cấu hình

Mở chức năng hỗ trợ
    -> hiển thị giải thích ngữ cảnh

Chọn tệp
    -> xem trước tại thiết bị hoặc bắt đầu upload, tùy thiết kế

Bấm gửi
    -> gửi nội dung và metadata tới dịch vụ

Job nền
    -> xử lý, chuyển tiếp hoặc dọn dữ liệu
```

Nếu ứng dụng tự upload ngay khi người dùng chọn tệp, một thông báo chỉ xuất hiện sau nút “Gửi” là quá muộn so với yêu cầu “trước khi gửi nội dung tệp”.

Cần quan sát hành vi thực tế. Một thao tác được thiết kế là xem trước cục bộ có thể vô tình gọi dịch vụ bên ngoài hoặc tạo upload tạm.

### 5.3. Không đặt một cổng chặn thiếu khả thi

Ngay khi tải ứng dụng web, hạ tầng có thể đã nhận địa chỉ mạng và metadata của request. Vì vậy, không viết yêu cầu tuyệt đối “không có bất kỳ dữ liệu nào được xử lý trước khi hiện thông báo” nếu kiến trúc không thể đáp ứng.

Hãy chỉ rõ luồng cần kiểm soát: chẳng hạn không khởi tạo SDK tùy chọn, không gửi vị trí chính xác hoặc không upload nội dung tệp trước điều kiện đã chốt.

Các xử lý kỹ thuật ngay từ request đầu tiên vẫn cần được đưa vào danh mục và nội dung thông tin phù hợp. Đừng loại chúng khỏi phạm vi chỉ để một tiêu chí giao diện dễ đạt hơn.

## 6. Thiết kế nội dung theo nhiều lớp

Một cách tổ chức thường có ích là kết hợp thông báo ngữ cảnh ngắn với thông tin đầy đủ có thể truy cập dễ dàng.

| Lớp | Nội dung chính | Điểm kiểm chứng |
|---|---|---|
| Ngữ cảnh tức thời | Dữ liệu sắp gửi, mục đích và lựa chọn trực tiếp | Hiện tại đúng bước; không bị che hoặc xuất hiện sau request |
| Chi tiết của chức năng | Bên tiếp cận, lưu giữ, điều khiển và tình huống liên quan | Liên kết đi tới đúng phần; nội dung khớp chức năng |
| Thông tin chung | Chủ thể vận hành, các nhóm xử lý và kênh liên hệ theo phạm vi đã xác định | Tìm được từ các điểm vào phù hợp; phiên bản có thể nhận diện |

Thông báo ngắn không nên là một câu vô nghĩa như “chúng tôi coi trọng quyền riêng tư”. Nó phải giúp người dùng dự đoán điều sắp xảy ra.

Các nhóm thông tin cần được đánh giá để đưa vào nội dung gồm:

- Ai vận hành hoặc chịu trách nhiệm cho hoạt động được mô tả.
- Loại dữ liệu và nguồn nhận dữ liệu.
- Mục đích và điều kiện xử lý theo chính sách áp dụng.
- Những bên hoặc nhóm bên được tiếp cận, bao gồm nhà cung cấp liên quan.
- Nguyên tắc hoặc thời hạn lưu giữ đã được chốt.
- Các lựa chọn, tác động của lựa chọn và cách thay đổi khi có.
- Cách hỏi thông tin, yêu cầu hỗ trợ hoặc thực hiện quyền theo quy trình đã xác định.
- Các đặc điểm như xử lý xuyên môi trường, chuyển giao hoặc ra quyết định tự động nếu thực sự thuộc phạm vi.
- Ngày hiệu lực và cách nhận diện phiên bản khi cần cho vận hành.

Danh sách này là đầu vào thiết kế, không phải một khẳng định rằng cùng tập nội dung và cùng cách trình bày luôn đủ cho mọi sản phẩm.

Nội dung đầy đủ không nên mâu thuẫn với phần ngắn. Nếu phần ngắn nói “chỉ nhóm hỗ trợ đọc tệp” nhưng phần đầy đủ cho phép nhiều nhóm khác đọc, cần sửa thiết kế hoặc cách diễn đạt trước khi phát hành.

## 7. Ví dụ thông báo ngữ cảnh và điều kiện áp dụng

Giả sử một chức năng hỗ trợ đã được chốt các chính sách sau cho môi trường minh họa:

- Nhận nội dung tệp người dùng chủ động chọn và metadata tải lên cần cho vận hành.
- Dùng tệp để xử lý đúng phiếu hỗ trợ tương ứng.
- Nhân viên hỗ trợ được phân công và nhà cung cấp lưu trữ đã cấu hình có vai trò tiếp cận theo thiết kế.
- Bản tệp trên hệ thống hoạt động được xóa theo lịch trong 30 ngày sau khi đóng phiếu, trừ ngoại lệ đã được ghi nhận trong chính sách.
- Bản sao backup có vòng đời riêng, tối đa 90 ngày tính từ lúc tạo bản backup, và không được dùng cho hoạt động hỗ trợ thường ngày.
- Người dùng có thể gửi nội dung mô tả mà không đính kèm tệp.

Các con số trên chỉ thuộc case giả định; không phải thời hạn mặc định hoặc quy tắc áp dụng cho hệ thống khác.

Một bản ngắn có thể là:

> Khi bạn gửi tệp, chúng tôi nhận nội dung tệp và thông tin kỹ thuật của lần tải lên để xử lý phiếu hỗ trợ này. Nhóm hỗ trợ được phân công và nhà cung cấp lưu trữ của dịch vụ tiếp cận dữ liệu theo nhiệm vụ của họ. Bạn có thể gửi mô tả mà không đính kèm tệp. Xem chi tiết về lưu giữ, các bên liên quan và cách liên hệ tại phần “Dữ liệu của phiếu hỗ trợ”.

Ở phần chi tiết, giải thích đúng mốc tính 30 ngày, ngoại lệ và vòng đời backup. Không rút gọn thành “mọi bản sao bị xóa sau 30 ngày” khi kiến trúc và chính sách không bảo đảm điều đó.

Giao diện cũng có thể nhắc người dùng chỉ gửi thông tin cần cho vấn đề đang hỗ trợ và che phần không cần thiết. Lời nhắc này không chuyển toàn bộ trách nhiệm xử lý an toàn sang người gửi.

Nút “Gửi tệp” cần có tên phù hợp với hành động. Không đổi thành “Đồng ý tất cả” nếu chức năng không phải một quyết định đồng ý được đặc tả riêng.

## 8. Biểu diễn liên kết giữa thông báo và hoạt động xử lý

Thông báo cần gắn với cấu hình thực thi, không chỉ là một tài liệu rời. Một bản ghi cấu hình minh họa trong bài:

```yaml
processingId: support-attachment-upload
processingRevision: 4
noticeId: support-attachment-context
noticeSemanticVersion: "3"
noticePresentationRevision: "2"
locale: vi
dataCategories:
  - user-selected-file-content
  - upload-technical-metadata
purposeIds:
  - resolve-support-ticket
retentionPolicyRef: support-attachment-retention-v2
recipientPolicyRef: support-attachment-recipients-v1
entryPoint: support.ticket.attachment
displayBoundary: before-file-content-upload
choicePolicyRef: support-attachment-processing-policy
fullNoticeSection: support-ticket-data
```

Đây là mô hình liên kết để thảo luận, không phải schema bắt buộc của một framework.

Những trường quan trọng:

- **processingId và processingRevision:** hoạt động xử lý nào đang chạy và cấu hình nào áp dụng.
- **noticeSemanticVersion:** phiên bản nội dung có ý nghĩa về xử lý dữ liệu.
- **noticePresentationRevision:** thay đổi cách trình bày không nhất thiết đổi ý nghĩa.
- **locale:** bản ngôn ngữ thực sự được cung cấp.
- **purposeIds:** các mục đích được mô tả; không tự tạo quyền cho mục đích đó.
- **policyRef:** liên kết tới chính sách đã chốt, tránh tự ghi một giá trị khác ở từng nơi.
- **displayBoundary:** thời điểm có thể kiểm chứng bằng sự kiện hoặc request cụ thể.

Nếu cấu hình thay đổi bên nhận hoặc thời hạn lưu giữ, phải đánh giá thông báo còn đúng không. Đừng chỉ kiểm tra noticeId tồn tại rồi coi mọi revision của hoạt động xử lý đều tương thích.

Với sản phẩm nhiều tenant hoặc nhiều biến thể, cần mô tả yếu tố nào được phép làm nội dung khác nhau. Việc tenant tự nhập văn bản cũng phải có quyền sửa, xác nhận và giới hạn cấu hình phù hợp.

## 9. Luồng thực thi: tách điều kiện hiển thị khỏi điều kiện xử lý

Một luồng minh họa:

```text
Xác định hoạt động xử lý và cấu hình đang có hiệu lực
        |
        v
Chọn thông báo đúng ngữ cảnh, phiên bản và ngôn ngữ
        |
        v
Kiểm tra nội dung có sẵn và hiển thị tại ranh giới đã chốt
        |
        v
Cung cấp lựa chọn riêng nếu hoạt động có yêu cầu lựa chọn
        |
        v
Đánh giá điều kiện xử lý, quyền đối tượng và trạng thái lựa chọn
        |
        v
Thực hiện thao tác nếu toàn bộ điều kiện tương ứng cho phép
```

Mã giả có thể thể hiện việc tách các quyết định:

```text
plan = processingRegistry.resolve(feature, tenant, deployment)
notice = noticeCatalog.resolve(plan, effectiveLocale)

if plan.requiresContextNotice and not notice.isCompatibleAndAvailable:
    blockFeatureAccordingToContract()
    recordMinimalDeliveryFailure()
    return

renderNoticeAtRequiredBoundary(notice)

decision = processingPolicy.evaluate(
    plan,
    callerPermissions,
    objectScope,
    independentUserChoices
)

if decision.permitted:
    executeFeature(plan)
else:
    returnPolicyDefinedOutcome()
```

Hàm render không nên tự ghi “đã đồng ý”. Việc bấm mở phần chi tiết cũng không được thay đổi lựa chọn mục đích không liên quan.

Một UI guard có thể ngăn client chính thức upload trước khi thông báo sẵn sàng. Nó không chứng minh client không thể bị sửa. Server vẫn phải kiểm tra quyền truy cập, điều kiện xử lý và các trạng thái cần thiết độc lập với sự kiện “đã hiển thị” do client gửi.

Nếu chức năng cần ghi nhận một bước thông báo theo hợp đồng, phải đặc tả cách liên kết với phiên hoạt động và giới hạn tin cậy của bằng chứng. Không biến một cờ noticeShown từ request thành giấy phép truy cập dữ liệu.

Đối với SDK tùy chọn, cần kiểm tra cả thời điểm tải, khởi tạo, đặt định danh và gửi sự kiện theo cấu hình. Chỉ trì hoãn event nghiệp vụ trong khi SDK đã gửi metadata không đạt yêu cầu nếu mục tiêu là chặn toàn bộ luồng SDK đó.

## 10. Hình thức hiển thị, khả năng tiếp cận và ngôn ngữ

### 10.1. Vị trí và độ rõ

Yêu cầu giao diện nên mô tả vị trí theo hành trình thay vì chỉ theo tọa độ:

> Trong bước xác nhận tệp, thông báo ngữ cảnh nằm cùng khu vực với thao tác gửi và xuất hiện trước lần request mang nội dung tệp.

Nội dung không nên bị che bởi banner, nằm trong tooltip khó phát hiện hoặc chỉ xuất hiện khi người dùng thao tác sai. Trên màn hình nhỏ, cần giữ khả năng đọc và thao tác với phần chi tiết.

Không cần ép mọi thông báo thành modal. Một thông báo inline đúng chỗ có thể phù hợp hơn. Hình thức phải được chọn theo độ quan trọng, chiều dài và bước quyết định thực tế.

### 10.2. Khả năng tiếp cận

Các ca kiểm tra có thể gồm:

- Điều hướng đến liên kết và lựa chọn bằng bàn phím.
- Thứ tự focus có nghĩa và không bị kẹt trong thành phần hiển thị.
- Công cụ đọc màn hình nhận biết được tiêu đề, nội dung và nhãn hành động.
- Tăng cỡ chữ không làm mất nội dung hoặc che nút.
- Không dùng riêng màu sắc để truyền đạt lựa chọn hoặc trạng thái lỗi.
- Liên kết tới nội dung đầy đủ có tên mô tả rõ, không chỉ là một ký hiệu.
- Sau khi đóng phần chi tiết, người dùng trở lại đúng bước đang làm.

Một ảnh chụp màn hình đẹp không đủ chứng minh các thuộc tính này.

### 10.3. Bản ngôn ngữ và fallback

Cần quyết định ngôn ngữ hiệu lực được lấy từ đâu, ưu tiên thiết lập nào và điều gì xảy ra khi thiếu bản dịch. Việc chỉ dịch tiêu đề nhưng giữ nội dung quan trọng ở ngôn ngữ khác phải được ghi nhận đúng, không coi là đã có bản dịch đầy đủ.

Ví dụ hợp đồng cho một chức năng có rủi ro cao: nếu thiếu bản thông báo tiếng Việt đã được xác nhận cho revision hiện tại, chức năng đó tạm thời không gửi dữ liệu; giao diện giải thích lỗi và cung cấp hướng xử lý. Đây là lựa chọn thiết kế của chức năng, không phải kết luận rằng mọi sản phẩm luôn phải chặn theo cùng cách.

Mã ngôn ngữ, phiên bản nội dung và liên kết chi tiết phải đi cùng nhau. Cache chỉ theo noticeId có thể phục vụ bản tiếng Anh cho người dùng đang cần tiếng Việt hoặc bản của tenant khác.

## 11. Thay đổi thông báo và quản lý phiên bản

### 11.1. Phân loại thay đổi theo ý nghĩa

| Loại thay đổi | Ví dụ | Việc cần đánh giá |
|---|---|---|
| Trình bày | Sửa lỗi chính tả, bố cục hoặc nhãn liên kết | Có đổi ý nghĩa, khả năng tiếp cận hoặc bằng chứng không? |
| Nội dung xử lý | Thêm mục đích, bên nhận hoặc loại dữ liệu | Có cần thông báo lại, thay đổi lựa chọn hoặc dừng luồng cũ không? |
| Vận hành | Đổi kênh liên hệ, đường dẫn hoặc tên thành phần | Link, lịch sử và hành trình đang dùng có còn đúng không? |
| Chính sách lưu giữ | Đổi mốc hoặc nguyên tắc lưu | Hệ thống thực thi và dữ liệu đã có chịu tác động thế nào? |
| Bản dịch | Sửa một cách diễn đạt làm sai nghĩa | Bản ngôn ngữ nào cần cập nhật và có tương thích không? |

Không suy ra rằng đổi noticeSemanticVersion tự động làm mất hiệu lực mọi lựa chọn trước đó. Tác động tới lựa chọn hoặc điều kiện xử lý là một quyết định chính sách riêng.

Cũng không suy ra rằng lựa chọn cũ luôn đủ cho mục đích mới. Cần kiểm tra phạm vi ban đầu, chính sách hiện hành và yêu cầu chuyển tiếp đã được phê duyệt.

### 11.2. Đồng bộ phát hành nội dung với tính năng

Một quy trình có thể yêu cầu:

1. Chủ sở hữu xử lý cập nhật danh mục và mô tả thay đổi.
2. Chủ sở hữu chính sách xác nhận nội dung cùng tác động đến lựa chọn.
3. Nhóm sản phẩm và nội dung kiểm tra cách diễn đạt, ngôn ngữ và hành trình.
4. Nhóm kỹ thuật liên kết revision tính năng với phiên bản thông báo tương thích.
5. Kiểm thử cả cấu hình đang hoạt động và cấu hình sắp phát hành.
6. Kích hoạt thông báo trước hoặc cùng điểm cho phép tính năng theo kế hoạch.
7. Giám sát lỗi phân phối, cache và hành vi dữ liệu sau phát hành.

Nếu rollback code, phải kiểm tra thông báo còn đúng với cấu hình được khôi phục. Không phục vụ một bản thông báo cũ nói ít hơn trong khi một SDK hoặc luồng chia sẻ mới vẫn đang chạy.

### 11.3. Lưu lịch sử có mục đích

Lịch sử giúp xác định nội dung từng có hiệu lực và xử lý thắc mắc. Cần lưu bản nội dung thực tế hoặc tham chiếu bất biến tới bản phát hành; một URL luôn trỏ tới “bản mới nhất” không đủ để tái hiện thông báo cũ.

Có thể lưu hash của artifact để đối chiếu, nhưng hash không thay thế chính nội dung cần tái hiện. Phải có khả năng lấy lại artifact tương ứng và kiểm tra đúng biến thể ngôn ngữ, tenant, cấu hình.

Quyền sửa nội dung, phê duyệt và kích hoạt nên được kiểm soát theo rủi ro. Không cho phép một tài khoản nội dung thay đổi âm thầm cả thông báo lẫn cấu hình xử lý để tự che giấu việc mở rộng thu thập.

## 12. Bằng chứng cung cấp thông báo và giới hạn kết luận

### 12.1. Phân biệt các mức bằng chứng

| Sự kiện | Có thể hỗ trợ chứng minh | Không tự chứng minh |
|---|---|---|
| Nội dung đã được phát hành | Có một artifact được kích hoạt | Người dùng cụ thể đã nhìn thấy |
| API trả thông báo thành công | Nội dung đã được gửi tới client | Client đã render hoặc người dùng đã đọc |
| Client báo render thành công | Client chính thức báo đã đưa nội dung vào giao diện | Nội dung nằm trong tầm nhìn, được hiểu hoặc không có client giả |
| Người dùng mở chi tiết | Có tương tác mở nội dung | Đã đọc hết hoặc đồng ý mọi mục đích |
| Người dùng xác nhận một bước | Có hành động theo hợp đồng của bước đó | Có quyền truy cập dữ liệu hoặc một sự đồng ý không được đặc tả |
| Thử nghiệm mức hiểu | Một mẫu người dùng hiểu ở mức đã đo | Mọi cá nhân trong tương lai đều hiểu |

Tỷ lệ mở trang cao không tự là tiêu chí hoàn tất minh bạch. Ngược lại, không có sự kiện telemetry cũng không luôn chứng minh thông báo không xuất hiện: có thể hệ thống đo bị chặn hoặc mạng bị lỗi.

### 12.2. Giảm dữ liệu trong bản ghi bằng chứng

Một schema sự kiện minh họa:

```text
eventId
eventType
processingId
processingRevision
noticeId
noticeSemanticVersion
noticePresentationRevision
effectiveLocale
entryPoint
clientBuild
deliveryOutcome
occurredAt
subjectReferenceIfRequired
```

Chỉ thêm định danh cá nhân nếu có nhu cầu đã được xác định. Nhiều kiểm tra khả năng phân phối có thể dùng số liệu tổng hợp hoặc tham chiếu phiên ngắn hạn thay cho hồ sơ người dùng đầy đủ.

Nếu cần liên kết sự kiện với một người hoặc phiên, tham chiếu đó vẫn có thể là dữ liệu cá nhân. Đổi ID thành hash không tự biến bản ghi thành dữ liệu vô danh.

Không ghi nội dung tệp, giá trị form, token đăng nhập hoặc toàn bộ request chỉ để chứng minh thông báo đã hiển thị. Bản ghi bằng chứng cần quyền truy cập, thời hạn lưu và quy trình xóa của chính nó.

Thời điểm do client gửi có giới hạn tin cậy. Đối với yêu cầu cần đối chiếu thời gian, phải phân biệt thời gian client báo và thời gian server nhận; không dựa vào đồng hồ client để khẳng định một trình tự tuyệt đối.

## 13. Luồng lỗi, API, tích hợp và phục hồi

### 13.1. Hành vi lỗi phải có hợp đồng riêng

| Tình huống | Hành vi cần đặc tả |
|---|---|
| Không tải được thông báo ngữ cảnh | Chặn hoặc dùng bản local tương thích theo chính sách của chức năng; không tự bỏ qua |
| Link chi tiết lỗi | Có điểm quan sát và hành vi UI; không coi thông báo đầy đủ đã được cung cấp thành công |
| Cache giữ revision cũ | Phát hiện không tương thích trước khi bật luồng xử lý tương ứng |
| Chưa có bản dịch hiện hành | Áp dụng fallback hoặc chặn đã được quyết định, ghi nhận locale thực tế |
| Telemetry thất bại | Phân biệt lỗi cung cấp thông báo với lỗi ghi nhận bằng chứng |
| SDK không tuân thủ cấu hình trì hoãn | Không phát hành hoặc vô hiệu hóa luồng theo quyết định vận hành |
| Khôi phục bản cấu hình cũ | Kiểm tra lại sự tương thích giữa xử lý, thông báo và lựa chọn |
| Có yêu cầu xóa dữ liệu | Áp dụng chính sách cho cả bản ghi bằng chứng liên quan; không mặc định giữ vô hạn |

Không dùng một quy tắc chặn cho mọi lỗi mà không đánh giá hậu quả. Nếu bằng chứng cá nhân là điều kiện bắt buộc của một luồng, cần quy định xử lý khi không ghi được; nếu telemetry chỉ đo chất lượng phân phối, không nên tự biến lỗi đo thành mất khả năng dùng toàn bộ dịch vụ.

### 13.2. API và các kênh không có màn hình

Với API trực tiếp, chức năng import hoặc xử lý dữ liệu nhận từ đối tác, cần xác định kênh cung cấp thông tin phù hợp và trách nhiệm của các bên. Không thêm một cờ noticeAccepted vào mọi endpoint như giải pháp chung.

Tài liệu tích hợp có thể mô tả dữ liệu và luồng xử lý, nhưng tài liệu cho lập trình viên không tự chứng minh mọi người có dữ liệu đã nhận thông báo. Yêu cầu phải nêu rõ nhóm người nhận và kênh được chọn.

Mobile hoặc desktop có thể dùng bản thông báo đóng gói cục bộ để hoạt động khi mạng không ổn định. Cần quy tắc về tuổi phiên bản, tính tương thích và thời điểm không được tiếp tục sử dụng bản cũ.

### 13.3. Trang thông báo cũng là một luồng dữ liệu

Trang chính sách có thể tải font, hình ảnh, SDK, chat widget hoặc dịch vụ ngoài. Các thành phần này có thể tạo xử lý dữ liệu trước khi người dùng đọc thông tin.

Phải đưa chúng vào phạm vi kiểm tra. Một trang được thiết kế để giải thích quyền riêng tư không nên âm thầm thêm một đường thu thập chưa có trong danh mục.

Quyền truy cập nội dung cũng cần phù hợp. Chẳng hạn, thông tin chung có thể cần được đọc trước đăng nhập; một liên kết chỉ mở sau đăng nhập có thể không phục vụ được người đang cân nhắc sử dụng dịch vụ. Nội dung nội bộ có giới hạn riêng phải được tách rõ.

## 14. Bộ yêu cầu mẫu có thể đưa vào đặc tả

Các mã sau là ví dụ trong phạm vi chức năng tải tệp hỗ trợ. Dự án cần thay điểm vào, phạm vi, ngưỡng và chủ sở hữu bằng quyết định thực tế.

| ID | Yêu cầu | Bằng chứng nghiệm thu |
|---|---|---|
| NTC-01 | Mỗi hoạt động xử lý thuộc phạm vi có mapping tới thông báo, nhóm người nhận, điểm vào và chủ sở hữu | Bảng truy vết và danh mục hoạt động đang bật |
| NTC-02 | Thông báo ngữ cảnh xuất hiện trước request gửi nội dung tệp trong mọi đường upload của client chính thức | Kiểm tra thứ tự UI và request tại chọn tệp, kéo thả, retry và gửi form |
| NTC-03 | Thông báo nêu đúng loại dữ liệu, mục đích và lựa chọn trực tiếp; phần đầy đủ phản ánh bên nhận và lưu giữ đã chốt | Đối chiếu nội dung với cấu hình thực thi và policy tương ứng |
| NTC-04 | Việc hiển thị, mở hoặc xác nhận thông báo không tự thay đổi lựa chọn của mục đích khác | So sánh trạng thái lựa chọn và hoạt động SDK trước, sau thao tác |
| NTC-05 | Client chọn đúng biến thể theo locale, tenant và revision xử lý; cache không trộn biến thể | Ca kiểm thử tổ hợp cấu hình cùng kiểm tra khóa cache |
| NTC-06 | Không bật luồng xử lý khi thiếu phiên bản thông báo tương thích nếu chính sách chức năng yêu cầu thông báo tại điểm đó | Fault injection và kiểm tra không có request dữ liệu tương ứng |
| NTC-07 | Liên kết chi tiết hoạt động và truy cập được bằng bàn phím cùng công cụ hỗ trợ trong hành trình được hỗ trợ | Kiểm thử thao tác thực tế trên thiết bị và build đã chốt |
| NTC-08 | Thay đổi mục đích, dữ liệu, bên nhận hoặc lưu giữ phải được đánh giá tác động trước kích hoạt | Lịch sử phê duyệt và cấu hình phiên bản tương thích |
| NTC-09 | Bản thông báo từng có hiệu lực có thể được tái hiện theo ngôn ngữ và biến thể tương ứng | Lấy lại artifact từ bản ghi phiên bản, kiểm tra nội dung |
| NTC-10 | Bản ghi bằng chứng không chứa nội dung tệp, dữ liệu form nhạy cảm hoặc token xác thực | Kiểm tra schema và các nhánh log thành công, lỗi, retry |
| NTC-11 | Báo cáo phân biệt phát hành, phân phối, render, tương tác và lựa chọn của người dùng | Đối chiếu định nghĩa sự kiện với dashboard và ca thử |
| NTC-12 | Rollback và restore không để cấu hình xử lý mới chạy cùng thông báo không còn đúng | Diễn tập thay phiên bản và kiểm tra luồng sau khôi phục |
| NTC-13 | Các entry point không có UI có trách nhiệm và kênh thông báo được xác định theo chính sách | Đối chiếu API, import, đối tác và quy trình cung cấp thông tin |
| NTC-14 | Quyền sửa và kích hoạt thông báo được kiểm soát; thay đổi có lịch sử | Kiểm tra quyền, lịch sử và khả năng tái hiện bản phát hành |

Ví dụ cụ thể hóa NTC-02:

> Với bản web hỗ trợ desktop và mobile, chọn tệp hoặc kéo thả chỉ tạo preview cục bộ trước bước xác nhận. Request chứa nội dung tệp chỉ được client chính thức phát đi sau khi thông báo ngữ cảnh tương thích đã được render và người dùng thực hiện thao tác gửi. Ca thử phải quan sát cả request upload tạm và request retry, không chỉ endpoint gửi phiếu cuối cùng.

Ví dụ cụ thể hóa độ trễ: trong môi trường thử có thiết bị, mạng và build được ghi rõ, p95 thời gian từ mở bước đính kèm đến khi nội dung thông báo đọc được không vượt 500 ms. Đây là ngưỡng minh họa của sản phẩm; cần ngưỡng riêng cho lỗi mạng, cache và phương án local nếu có. Một request trả 200 không tự chứng minh nội dung đã đọc được trên màn hình.

## 15. Ma trận kiểm thử và tiêu chí kết luận

| Nhóm ca | Kích thích | Oracle và điểm quan sát |
|---|---|---|
| Luồng thông thường | Mở bước đính kèm rồi gửi tệp giả lập | Thông báo đúng xuất hiện trước request mang nội dung tệp |
| Upload sớm | Chọn tệp, kéo thả hoặc dán nội dung | Không có upload tạm trước ranh giới đã chốt |
| Thông báo không tải được | Làm lỗi nguồn nội dung trong môi trường thử | UI và luồng dữ liệu thực hiện đúng hợp đồng lỗi |
| Bản dịch thiếu | Chọn locale thiếu revision tương thích | Fallback hoặc chặn đúng chính sách; bằng chứng ghi locale thực tế |
| Cache lỗi thời | Phục vụ bản cũ khi feature flag đã đổi | Không bật cấu hình cần nội dung mới nếu không tương thích |
| Nhiều tenant | Hai tenant có chính sách khác nhau | Nội dung và cache không lẫn biến thể |
| Lựa chọn độc lập | Mở thông báo, đóng chi tiết và bấm gửi tệp | Không tự bật mục đích quảng cáo hoặc SDK ngoài phạm vi |
| Quyền truy cập | Gọi API bằng caller thiếu quyền | Server từ chối theo policy dù request có cờ noticeShown |
| Khả năng tiếp cận | Dùng bàn phím, trình đọc màn hình và chữ lớn | Có thể đọc, mở chi tiết và trở lại đúng bước |
| Trang chi tiết | Mở nội dung trước đăng nhập khi phạm vi yêu cầu | Đúng trang, không bị cổng đăng nhập ngoài thiết kế |
| Logging | Chạy thành công, lỗi và retry với marker trong tệp | Marker nội dung không có trong kênh telemetry bị cấm |
| Bằng chứng | API thành công nhưng renderer hoặc telemetry lỗi | Không gộp delivery thành render hoặc consent |
| Rollback | Khôi phục build hoặc cấu hình cũ | Thông báo, xử lý và lựa chọn vẫn có tổ hợp được phép |
| Tích hợp | Import hoặc gửi dữ liệu qua đối tác | Trách nhiệm, kênh và bằng chứng đúng phạm vi đã chốt |

Bộ thử phải dùng dữ liệu tổng hợp và quan sát request ở môi trường được kiểm soát. Nếu cần marker để theo đường đi, không dùng thông tin cá nhân thật làm marker.

Không kết luận PASS chỉ vì tìm thấy link chính sách trong DOM. Cần xem nội dung nào, phiên bản nào, thời điểm nào, entry point nào và hành vi dữ liệu thực tế.

Nếu không quan sát được request nền hoặc chưa có thiết bị để kiểm thử một hành trình được hỗ trợ, ghi nhận chưa đủ bằng chứng hoặc chưa thực thi. Không đưa các ca đó vào nhóm đã đạt.

Nghiên cứu mức hiểu có thể bổ sung: cho người tham gia một nhiệm vụ rồi hỏi dữ liệu nào sẽ được gửi, để làm gì và họ có lựa chọn nào. Cần xác định mẫu, câu hỏi và tiêu chí đánh giá trước; kết quả này bổ trợ kiểm thử kỹ thuật, không thay thế nó.

## 16. Case study: thêm phân tích hành vi vào chức năng hỗ trợ

Một nền tảng đang có thông báo cho việc gửi tệp hỗ trợ. Nhóm sản phẩm muốn đo hành vi để cải thiện màn hình và đề xuất một SDK mới. SDK có thể khởi tạo ngay khi mở trang, gửi định danh thiết bị cùng sự kiện tương tác tới nhà cung cấp.

### 16.1. Vấn đề cần phân tích

Thông báo gửi tệp mô tả mục đích xử lý phiếu và nội dung tệp. Nó không tự bao phủ mục đích phân tích, định danh thiết bị, bên nhận mới hoặc thời điểm khởi chạy SDK.

Không thể giải quyết bằng cách thêm câu “có thể dùng dữ liệu để nâng cao trải nghiệm” rồi giữ nguyên mọi quyết định kỹ thuật. Cần xác định dữ liệu thực gửi, mục đích cụ thể, điều kiện xử lý và lựa chọn áp dụng.

### 16.2. Quyết định và truy vết

| Quyết định | Tác động tới yêu cầu | Ca kiểm chứng |
|---|---|---|
| Tách hoạt động phân tích khỏi gửi tệp | Mapping processingId và thông báo riêng theo ngữ cảnh | Gửi tệp không tự bật trạng thái phân tích |
| Chốt điều kiện cho phép SDK hoạt động | Không chỉ kiểm tra việc mở thông báo | Caller hoặc phiên chưa đủ điều kiện không khởi tạo/gửi theo phạm vi chặn |
| Bổ sung dữ liệu và bên nhận vào nội dung | Đồng bộ policy và phiên bản thông báo | Đối chiếu request SDK với danh mục được phê duyệt |
| Giữ chức năng hỗ trợ hoạt động khi phân tích không được phép | Xác định phương án nghiệp vụ tương ứng | Gửi phiếu thành công trong cấu hình phân tích tắt |
| Phát hành có kiểm soát | Ghép revision SDK, feature flag và thông báo | Tổ hợp bản cũ, cache cũ và rollout từng phần được xử lý đúng |
| Giảm telemetry bằng chứng | Không dùng chính dữ liệu nhạy cảm làm sự kiện đo | Kiểm tra log bằng marker giả lập |

Nếu sau kiểm thử phát hiện SDK gửi request ngay khi module được import, việc tắt event ở cấp ứng dụng chưa đủ cho yêu cầu trì hoãn toàn bộ luồng SDK. Cần sửa điểm tải hoặc khởi tạo, cấu hình SDK hay chọn phương án khác.

Case này cho thấy notice requirement phải liên kết với kiến trúc. Nội dung đúng nhưng thời điểm thu thập sai vẫn không đạt tiêu chí của chức năng.

## 17. Bài tập đặc tả

Một ứng dụng tiếp nhận hồ sơ cho phép người dùng nhập số điện thoại, đính kèm giấy tờ và gửi dữ liệu cho nhóm xử lý. Có thêm job import do đối tác vận hành. Trang thông báo đang dùng cùng một cache key cho mọi ngôn ngữ và nhóm sản phẩm muốn thêm SDK ghi hành vi.

Hãy thực hiện:

1. Lập danh mục hoạt động xử lý và nhóm người có dữ liệu, kể cả người không đi qua giao diện.
2. Xác định thời điểm bắt đầu gửi dữ liệu ở từng luồng, bao gồm upload tạm và SDK.
3. Viết một thông báo ngữ cảnh ngắn và chỉ ra thông tin nào đi vào phần đầy đủ.
4. Tách yêu cầu thông báo khỏi lựa chọn, phân quyền và kiểm tra nghiệp vụ.
5. Thiết kế mapping giữa processingRevision, noticeSemanticVersion, locale và policy.
6. Chốt hành vi khi thiếu bản dịch, link lỗi hoặc cache phục vụ phiên bản cũ.
7. Định nghĩa bằng chứng tối thiểu; nêu rõ điều gì bằng chứng không chứng minh được.
8. Viết ít nhất sáu ca kiểm thử có oracle, gồm một ca upload sớm và một ca không tự bật lựa chọn khác.
9. Mô tả phát hành, rollback và lấy lại bản nội dung từng có hiệu lực.
10. Viết một bảng truy vết từ rủi ro đến yêu cầu, thành phần thực hiện và bằng chứng nghiệm thu.

Kết quả cần giúp người dùng nhận được thông tin đúng lúc, đồng thời cho phép nhóm phát triển, kiểm thử và vận hành xác định rõ thông báo nào phải đi cùng hoạt động xử lý nào.
