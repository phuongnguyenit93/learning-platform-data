Một hệ thống mua sắm cho phép nhân viên tạo yêu cầu mua hàng rồi tự chuyển trạng thái sang Approved bằng cách gọi trực tiếp endpoint cập nhật trạng thái, dù giao diện chỉ hiển thị nút Submit; hãy phân tích lỗ hổng bỏ qua bước phê duyệt và ranh giới kiểm tra transition.
Một yêu cầu mua hàng đã được quản lý phê duyệt nhưng người tạo vẫn sửa nhà cung cấp và tổng tiền trước khi bộ phận tài chính thực thi; hãy xác định cách bảo vệ nội dung đã được duyệt và điều kiện cần phê duyệt lại.
Một nhân viên vừa tạo vừa phê duyệt khoản hoàn ứng của chính mình do backend chỉ kiểm tra role Approver mà không kiểm tra quan hệ giữa người tạo và người duyệt; hãy đánh giá lỗi phân tách nhiệm vụ.
Một workflow hỗ trợ nhiều bước Review, Approve và Execute nhưng API chỉ kiểm tra trạng thái hiện tại do client gửi lên, khiến request có thể nhảy từ Draft sang Executed; hãy phân tích invariant của state machine.
Một người dùng thay orderId trong endpoint hủy đơn và hủy được đơn thuộc tài khoản khác vì service chỉ kiểm tra trạng thái đơn; hãy xác định thiếu quyền theo đối tượng trong thao tác hủy.
Một nhân viên thuộc chi nhánh A truy cập hồ sơ khách hàng chi nhánh B bằng cách gửi branchId khác trong request body; hãy phân tích việc tin tenant hoặc organizational scope do client khai báo.
Một API cập nhật hồ sơ cho phép người dùng thêm trường creditLimit và riskStatus dù hai trường này chỉ dành cho quản trị viên; hãy đánh giá mass assignment và quyền ghi theo thuộc tính.
Một đơn hàng đã được duyệt giảm giá 10% nhưng client gửi lại unitPrice thấp hơn khi xác nhận thanh toán và backend dùng giá client gửi; hãy xác định nguồn dữ liệu giá đáng tin cậy và invariant cần bảo vệ.
Một khách hàng áp dụng cùng coupon qua nhiều request đồng thời và vượt giới hạn sử dụng một lần cho mỗi tài khoản; hãy phân tích race condition trong kiểm tra và ghi nhận redemption.
Một chương trình khuyến mãi giới hạn 100 lượt nhưng nhiều giao dịch đồng thời đều đọc số lượt còn lại là 1 rồi cùng được chấp nhận; hãy đánh giá tính nguyên tử của quota enforcement.
Hai khách hàng cùng mua sản phẩm cuối cùng trong kho và cả hai đơn đều được xác nhận do tồn kho chỉ được kiểm tra trước khi tạo đơn; hãy phân tích cách bảo vệ invariant tồn kho.
Một đơn hàng giữ chỗ tồn kho trong 30 phút nhưng job giải phóng reservation chạy trễ, trong khi thanh toán vẫn được chấp nhận sau khi reservation hết hạn; hãy xác định cách đồng bộ thời hạn và trạng thái.
Một khách hàng gửi số lượng âm trong request đổi trả, khiến hệ thống cộng hàng vào kho và tạo khoản hoàn tiền không hợp lệ; hãy đánh giá validation ngữ nghĩa và các invariant số lượng.
Một API chuyển tiền kiểm tra số dư trước transaction rồi thực hiện debit sau đó, cho phép hai request đồng thời cùng rút vượt số dư; hãy phân tích TOCTOU và kiểm soát concurrency.
Một hệ thống tính phí bằng số thực và làm tròn ở các service khác nhau, khiến chia nhỏ một giao dịch thành nhiều giao dịch nhỏ tạo ra tổng phí thấp hơn; hãy đánh giá tính nhất quán của phép tính tiền tệ.
Một khách hàng thay currencyCode trong request sau khi giá đã được báo bằng USD nhưng backend giữ nguyên con số và hiểu thành VND; hãy phân tích invariant giữa số tiền và đơn vị tiền tệ.
Một giao dịch thanh toán thành công nhưng client timeout trước khi nhận response rồi retry, dẫn tới hai payment record và hai lần trừ tiền; hãy đánh giá thiết kế idempotency.
Hai request cùng dùng một idempotency key nhưng khác payload amount, và hệ thống trả lại kết quả của request đầu mà không phát hiện nội dung không khớp; hãy xác định hợp đồng key với payload.
Một API lưu idempotency key sau khi thực hiện side effect, tạo khoảng trống để hai request đồng thời cùng thanh toán; hãy phân tích thứ tự ghi nhận và tính nguyên tử.
Một webhook từ cổng thanh toán được gửi lại nhiều lần sau timeout và mỗi lần đều kích hoạt hoàn tiền; hãy đánh giá deduplication theo event ID và trạng thái nghiệp vụ.
Một consumer nhận sự kiện OrderApproved cũ sau sự kiện OrderCancelled mới hơn và ghi đè trạng thái đơn thành Approved; hãy phân tích thứ tự sự kiện và version check.
Một service cập nhật database thành công nhưng publish event thất bại, khiến hệ thống kho không nhận được lệnh giữ hàng; hãy đánh giá ranh giới transaction và transactional outbox.
Một message consumer xử lý thành công nghiệp vụ nhưng mất ACK, sau đó broker redeliver và tạo thêm một phiếu giao hàng; hãy xác định cách làm consumer idempotent.
Một quy trình đặt hàng qua nhiều service đã trừ tiền nhưng service cấp kho thất bại, trong khi thao tác bù trừ hoàn tiền cũng timeout; hãy phân tích trạng thái trung gian và cách theo dõi saga compensation.
Một yêu cầu hoàn tiền được gửi hai lần với hai request ID khác nhau nhưng cùng payment reference, khiến tổng tiền hoàn vượt số tiền đã thu; hãy xác định invariant tổng refund không vượt captured amount.
Một nhân viên hỗ trợ có quyền hoàn tiền tối đa 500.000 đồng nhưng có thể gửi nhiều yêu cầu liên tiếp ngay dưới hạn mức mà không bị kiểm tra tổng hạn mức theo ngày; hãy phân tích quota theo cửa sổ thời gian.
Một API điều chỉnh giá cho phép nhập giá 0 đồng khi user có quyền sửa catalog nhưng không có quyền phát hành chương trình miễn phí; hãy đánh giá phân tách quyền cấu hình và quyền thực thi nghiệp vụ.
Một người dùng đổi địa chỉ giao hàng sau khi đơn đã được bàn giao cho hãng vận chuyển, khiến kiện hàng đi tới địa chỉ mới mà không có xác minh bổ sung; hãy xác định transition và giới hạn sửa dữ liệu theo trạng thái.
Một khách hàng hủy đơn trong lúc worker đang xác nhận thanh toán, tạo ra trạng thái vừa Cancelled vừa Paid; hãy phân tích race condition giữa hai luồng xử lý.
Một yêu cầu phê duyệt đã được duyệt dựa trên hạn mức của quản lý tại thời điểm gửi nhưng quản lý bị thu hồi quyền trước khi bước Execute chạy; hãy xác định thời điểm kiểm tra lại quyền.
Một tài khoản quản trị bật feature flag bỏ qua bước kiểm tra hạn mức trong production và không có audit record về thay đổi; hãy đánh giá kiểm soát thay đổi rule và quyền quản trị.
Một nhân viên có quyền sửa thông tin nhà cung cấp thay đổi tài khoản ngân hàng sau khi hóa đơn được duyệt nhưng trước khi thanh toán; hãy phân tích ràng buộc giữa dữ liệu đã phê duyệt và dữ liệu dùng để thực thi.
Một batch import có 500 dòng, trong đó 20 dòng thuộc tenant khác, nhưng hệ thống chỉ xác minh tenant ở cấp file và vẫn nhập toàn bộ; hãy đánh giá authorization từng đối tượng trong bulk operation.
Một job nền chạy theo quyền service account rộng và thực hiện thao tác thay mặt người dùng đã mất quyền truy cập tài nguyên từ trước; hãy phân tích confused deputy và kiểm tra quyền lúc thực thi.
Một workflow cho phép người dùng gọi endpoint Approve nhiều lần và mỗi lần lại tăng số lượng điểm thưởng; hãy xác định cách bảo vệ transition đã hoàn tất khỏi side effect lặp.
Một hệ thống tính điểm loyalty cộng điểm theo tổng tiền trước giảm giá nhưng quy tắc công bố yêu cầu tính theo số tiền thực thu; hãy phân tích business invariant và các nguồn dữ liệu tính điểm.
Một người dùng chia một giao dịch lớn thành nhiều giao dịch nhỏ để né ngưỡng yêu cầu phê duyệt cấp cao; hãy xác định cách phát hiện chuỗi giao dịch có liên hệ theo chủ thể và khoảng thời gian.
Một chương trình giới thiệu bạn bè cho phép cùng một thiết bị tạo nhiều tài khoản và tự giới thiệu lẫn nhau để nhận thưởng; hãy phân tích lạm dụng logic qua chuỗi hành động hợp lệ.
Một đơn hàng đã được xác nhận nhưng client có thể gọi lại endpoint ApplyPromotion để thay đổi giá trị sau khi payment intent được tạo; hãy xác định ranh giới bất biến giữa quote, order và payment.
Một API cho phép sửa số lượng sau khi thanh toán nhưng chỉ cập nhật order table mà không điều chỉnh payment hoặc inventory reservation; hãy phân tích tính nhất quán giữa các aggregate.
Một thao tác chuyển quyền sở hữu tài sản số kiểm tra owner trong cache cũ, trong khi database đã ghi nhận owner mới; hãy đánh giá việc dùng dữ liệu stale để quyết định quyền và cập nhật.
Một yêu cầu rút tiền được kiểm tra hạn mức theo ngày bằng timezone của client, khiến người dùng đổi timezone để vượt giới hạn ngày; hãy xác định nguồn thời gian và cách xác định cửa sổ hạn mức nhất quán.
Một nhân viên được phép duyệt hợp đồng dưới 100 triệu đồng nhưng có thể sửa giá trị hợp đồng sau khi phê duyệt để nâng lên 500 triệu đồng; hãy phân tích binding giữa quyết định phê duyệt và phiên bản dữ liệu.
Một quy trình nhiều người duyệt cho phép cùng một người dùng chiếm hai vai trò bằng hai tài khoản khác nhau nhưng cùng danh tính nhân sự; hãy đánh giá cách thực thi dual control dựa trên danh tính thực.
Một API cho phép hủy giao dịch đã quyết toán vì chỉ kiểm tra trạng thái Pending trong cache, trong khi trạng thái database đã chuyển Settled; hãy phân tích nguồn trạng thái có thẩm quyền và tính nhất quán.
Một message có timestamp cũ được xử lý sau khi đối tượng đã chuyển sang trạng thái mới và làm giảm hạn mức đã được tính lại; hãy xác định cách kiểm tra version, sequence và tính hợp lệ của sự kiện.
Một hệ thống retry tự động thao tác tạo vận đơn sau lỗi mạng nhưng nhà vận chuyển đã tạo vận đơn ở lần gọi đầu; hãy phân tích idempotency xuyên qua ranh giới tích hợp bên ngoài.
Một nhân viên quản trị có thể sửa trực tiếp bảng approval record qua API bảo trì mà không tạo audit event; hãy đánh giá kiểm soát đường truy cập quản trị và tính toàn vẹn audit.
Một báo cáo phát hiện nhiều tài khoản dùng coupon theo cùng một chuỗi thao tác, nhưng từng request đều hợp lệ theo rule đơn lẻ; hãy xác định cách phân tích abuse case theo chuỗi sự kiện.
Một lỗi triển khai khiến kiểm tra hạn mức chỉ chạy ở REST endpoint, trong khi cùng nghiệp vụ còn được gọi qua GraphQL, batch job và message consumer; hãy đánh giá tính nhất quán của enforcement ở các entry point.
Một kiểm thử chỉ xác minh từng API riêng lẻ mà không thử chuỗi tạo, sửa, duyệt, hủy và thực thi, khiến lỗi bỏ qua bước phê duyệt không được phát hiện; hãy thiết kế phạm vi kiểm thử theo state machine.
Một đợt kiểm thử tải không tạo được race condition vì các request chạy tuần tự ở test client, trong khi production có nhiều request đồng thời; hãy xác định cách tạo tranh chấp có kiểm soát và xác minh invariant.
Một sự cố khiến số tiền hoàn, tồn kho và trạng thái đơn không khớp sau nhiều lần retry và message đến sai thứ tự; hãy lập cách bảo toàn audit evidence, tái dựng timeline và xác minh phục hồi invariant.
