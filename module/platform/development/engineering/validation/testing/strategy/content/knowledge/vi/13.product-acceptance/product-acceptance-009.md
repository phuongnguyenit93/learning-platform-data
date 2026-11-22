# Ghi nhận chấp nhận có điều kiện và các hành động còn lại

Trong một dự án, kết quả kiểm thử không phải lúc nào cũng hoàn toàn đạt hoặc hoàn toàn không đạt. Có thể sản phẩm đáp ứng phần lớn tiêu chí, nhưng vẫn còn một lỗi ít ảnh hưởng, một phạm vi chưa được xác minh, một giới hạn vận hành hoặc một hành động cần hoàn tất sau phát hành. Khi đó, các bên có thể cân nhắc **chấp nhận có điều kiện** nếu rủi ro còn lại đã được hiểu, có biện pháp kiểm soát và được người có thẩm quyền chấp thuận.

Chấp nhận có điều kiện là một quyết định có phạm vi và thời hạn rõ ràng. Nó ghi nhận rằng sản phẩm hoặc một phần sản phẩm được phép tiếp tục trong những điều kiện cụ thể, trong khi các hành động còn lại vẫn phải được theo dõi và hoàn tất. Đây không phải là cách đổi kết quả kiểm thử không đạt thành đạt, cũng không có nghĩa mọi rủi ro đã được loại bỏ.

## 1. Chấp nhận có điều kiện là gì?

Chấp nhận sản phẩm là quyết định của bên có trách nhiệm rằng sản phẩm, phiên bản hoặc phạm vi chức năng đáp ứng các tiêu chí đã thống nhất để được bàn giao, phát hành hoặc đưa vào sử dụng. Quyết định cần dựa trên yêu cầu, kết quả kiểm thử, rủi ro, giới hạn đã biết và mức sẵn sàng vận hành.

**Chấp nhận có điều kiện (conditional acceptance)** là quyết định chấp nhận kèm theo các điều kiện, giới hạn hoặc hành động cần thực hiện. Ví dụ:

- Cho phép phát hành một tính năng cho nhóm người dùng nội bộ trong khi hoàn tất kiểm thử tương thích trên một trình duyệt ít phổ biến.
- Cho phép triển khai theo từng đợt với giới hạn lưu lượng, trong khi nhóm theo dõi hiệu năng ở mức tải cao hơn.
- Chấp nhận một lỗi giao diện có ảnh hưởng thấp trong một phiên bản, với điều kiện có phương án hỗ trợ người dùng và thời hạn sửa cụ thể.
- Cho phép sử dụng một quy trình vận hành tạm thời trong thời gian ngắn, với người phụ trách và ngày thay thế bằng giải pháp tự động.

Điều kiện phải có thể kiểm tra và thực thi. Câu như “sẽ sửa sớm” hoặc “cần theo dõi thêm” không đủ cụ thể để quản lý. Một điều kiện tốt nêu rõ hành động, người chịu trách nhiệm, hạn hoàn thành, bằng chứng đóng và hậu quả nếu không hoàn thành.

Chấp nhận có điều kiện thường phù hợp khi:

- Phần lớn mục tiêu và tiêu chí chấp nhận đã có bằng chứng đạt.
- Những điểm còn lại đã được nhận diện và mô tả cụ thể.
- Rủi ro còn lại nằm trong ngưỡng mà người có thẩm quyền có thể chấp nhận.
- Có biện pháp giảm thiểu, giới hạn phạm vi hoặc phương án khôi phục phù hợp.
- Các hành động tiếp theo có người sở hữu, thời hạn và tiêu chí hoàn tất.

Nếu còn thiếu bằng chứng về một yêu cầu quan trọng, chưa hiểu rõ tác động của lỗi hoặc chưa có người chịu trách nhiệm chấp nhận rủi ro, quyết định nên ở trạng thái chờ hoặc từ chối cho đến khi có đủ thông tin.

## 2. Phân biệt kết quả kiểm thử và quyết định chấp nhận

Kết quả kiểm thử là bằng chứng về hành vi trong điều kiện đã thực hiện. Quyết định chấp nhận là đánh giá của người có thẩm quyền dựa trên toàn bộ bằng chứng và bối cảnh phát hành. Hai việc có liên quan nhưng không đồng nhất.

| Khái niệm | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| Tiêu chí chấp nhận | Điều kiện nào phải đáp ứng để nghiệp vụ được xem là phù hợp? | Người dùng có thể thanh toán và nhận mã giao dịch hợp lệ |
| Kiểm thử chấp nhận | Sản phẩm có đáp ứng tiêu chí trong tình huống đã chọn không? | Thực hiện hành trình thanh toán với dữ liệu và môi trường xác định |
| Kết quả kiểm thử | Điều gì đã xảy ra khi chạy? | 24 trường hợp đạt, 1 trường hợp không đạt, 2 trường hợp bị chặn |
| Rủi ro còn lại | Điều gì vẫn có thể xảy ra và hậu quả là gì? | Một luồng hoàn tiền qua nhà cung cấp chưa được kiểm tra trên sandbox mới |
| Quyết định chấp nhận | Có cho phép bàn giao hoặc phát hành trong phạm vi nào? | Chấp nhận có điều kiện cho 10% lưu lượng, kèm giám sát và hạn đánh giá |

Một bộ kiểm thử có tỷ lệ đạt cao không tự động dẫn đến chấp nhận. Một lỗi đơn lẻ có thể gây hậu quả nghiêm trọng; ngược lại, một sai lệch nhỏ có thể được chấp nhận nếu tác động thấp, có phương án kiểm soát và không vi phạm điều kiện bắt buộc.

Không được sửa báo cáo kiểm thử để làm cho quyết định chấp nhận có vẻ thuận lợi hơn. Hãy giữ nguyên kết quả thực tế và ghi quyết định, điều kiện cùng lý do ở hồ sơ riêng hoặc phần quyết định phát hành.

## 3. Phân loại điều kiện, sai lệch và rủi ro còn lại

Trước khi đưa ra quyết định, nhóm nên phân loại những điểm chưa hoàn tất. Không phải mọi mục mở đều có cùng ý nghĩa.

- **Lỗi đã xác nhận:** hành vi thực tế khác với yêu cầu hoặc kết quả mong đợi. Cần ghi mức độ nghiêm trọng, phạm vi ảnh hưởng và bằng chứng tái hiện.
- **Phạm vi chưa kiểm thử:** chưa có bằng chứng cho một nền tảng, tích hợp, loại dữ liệu hoặc điều kiện cụ thể. Đây là bất định, không phải kết quả đạt.
- **Giới hạn môi trường:** môi trường thử nghiệm không thể mô phỏng đầy đủ production, ví dụ tải, nhà cung cấp hoặc cấu hình mạng.
- **Hành động vận hành còn mở:** tài liệu, cảnh báo, runbook, đào tạo, phân quyền hoặc quy trình hỗ trợ chưa hoàn tất.
- **Sai lệch được chấp thuận:** một yêu cầu hoặc tiêu chí được điều chỉnh có chủ đích và được đúng bên có thẩm quyền phê duyệt.
- **Phụ thuộc bên ngoài:** kết quả còn phụ thuộc nhà cung cấp, phê duyệt, dữ liệu hoặc hệ thống chưa sẵn sàng.

Cần phân biệt **mức độ nghiêm trọng (severity)** của vấn đề với **mức độ ưu tiên (priority)** xử lý. Severity mô tả tác động nếu vấn đề xảy ra; priority mô tả thứ tự xử lý trong bối cảnh nguồn lực và thời hạn. Một lỗi ít nghiêm trọng vẫn có thể được ưu tiên cao vì ảnh hưởng tới một sự kiện sắp diễn ra; một lỗi nghiêm trọng không được hạ thấp chỉ vì khó sửa.

Với mỗi mục còn mở, hãy xác định nó là lỗi đã biết, khoảng trống bằng chứng, điều kiện vận hành hay thay đổi yêu cầu. Việc phân loại giúp quyết định đúng cách xử lý và tránh gọi mọi vấn đề là “rủi ro thấp”.

## 4. Xác định rủi ro còn lại trước khi chấp nhận

Rủi ro còn lại là phần rủi ro vẫn tồn tại sau khi đã áp dụng biện pháp phòng ngừa, phát hiện hoặc giảm thiểu. Nhóm cần đánh giá ít nhất:

1. **Sự kiện có thể xảy ra:** điều gì có thể sai hoặc chưa được xác minh?
2. **Khả năng xảy ra:** có dữ liệu, lịch sử lỗi hoặc điều kiện nào cho thấy khả năng xuất hiện?
3. **Mức độ tác động:** người dùng, dữ liệu, tiền, hoạt động, uy tín hoặc nghĩa vụ nào bị ảnh hưởng?
4. **Khả năng phát hiện:** hệ thống có log, chỉ số, cảnh báo hoặc quy trình nhận biết kịp thời không?
5. **Khả năng khôi phục:** có thể rollback, hoàn tác, đối soát, khôi phục dữ liệu hoặc tắt tính năng không?
6. **Mức độ bất định:** điều gì chưa biết do thiếu dữ liệu hoặc môi trường chưa đại diện?

Có thể dùng ma trận khả năng xảy ra và mức độ tác động để xếp hạng, nhưng điểm số chỉ hỗ trợ thảo luận. Với rủi ro nghiêm trọng, cần ghi rõ giả định và không để điểm trung bình che khuất một hậu quả đặc biệt lớn.

Ví dụ, một lỗi hiển thị nhãn trạng thái sai có thể ít ảnh hưởng nếu dữ liệu và giao dịch vẫn chính xác, nhưng lỗi ghi nhận thanh toán hai lần có thể gây thiệt hại tài chính và cần xử lý trước khi phát hành. Không nên gộp hai vấn đề này thành một con số tổng hợp không giải thích được.

### Các câu hỏi trước khi đề xuất chấp nhận

- Người dùng nào có thể bị ảnh hưởng và trong phạm vi nào?
- Tác động có thể xảy ra ngay lập tức hay chỉ trong điều kiện hiếm?
- Có thể giới hạn người dùng, tính năng, khu vực hoặc lưu lượng để giảm rủi ro không?
- Có cách phát hiện sự cố trước khi hậu quả lan rộng không?
- Có thể tắt tính năng hoặc quay lại phiên bản trước trong thời gian phù hợp không?
- Hành động còn lại có thể hoàn thành trước khi rủi ro trở nên không chấp nhận được không?
- Có nghĩa vụ pháp lý, bảo mật, hợp đồng hoặc chính sách bắt buộc nào không cho phép ngoại lệ không?

Không nên đề xuất chấp nhận có điều kiện nếu rủi ro chưa được mô tả đủ để người ra quyết định hiểu hậu quả. Những yêu cầu bắt buộc theo pháp luật, chính sách bảo mật, hợp đồng hoặc tiêu chí an toàn phải được xử lý theo cơ chế phê duyệt tương ứng; một nhóm dự án không thể tự miễn trừ nghĩa vụ chỉ bằng cách ghi “accepted with conditions”.

## 5. Điều kiện chấp nhận phải cụ thể và có thể kiểm chứng

Mỗi điều kiện nên được viết thành một cam kết có thể theo dõi. Một cấu trúc thực hành:

> **Điều kiện:** [kết quả hoặc hành động cần hoàn tất]. **Phạm vi:** [tính năng, người dùng, môi trường hoặc phiên bản]. **Chủ sở hữu:** [vai trò hoặc người chịu trách nhiệm]. **Hạn:** [ngày/giờ]. **Bằng chứng đóng:** [kiểm thử, tài liệu, log, phê duyệt hoặc xác nhận]. **Nếu không đạt:** [giới hạn, dừng, rollback hoặc chuyển cấp].

Ví dụ:

> Trước ngày 15/07/2027, nhóm thanh toán phải hoàn tất kiểm thử retry và đối soát cho API nhà cung cấp phiên bản mới. Chủ sở hữu là trưởng nhóm thanh toán. Bằng chứng đóng gồm kết quả kiểm thử tích hợp cho timeout, gửi lại cùng khóa idempotency và xác minh không có giao dịch trùng. Nếu chưa đạt, tính năng thanh toán qua nhà cung cấp mới phải tiếp tục bị tắt.

Điều kiện cần tránh các cách diễn đạt không đo được:

| Cách ghi chưa đủ | Cách ghi có thể kiểm chứng |
| --- | --- |
| Sửa lỗi sớm | Sửa lỗi `BUG-214` trước ngày 15/07; chạy lại 6 trường hợp hồi quy đã liên kết và đính kèm kết quả |
| Theo dõi hiệu năng | Theo dõi p95 và tỷ lệ timeout của API trong 7 ngày; cảnh báo khi p95 vượt 800 ms trong 5 phút liên tục |
| Hoàn thiện tài liệu | Cập nhật runbook xử lý giao dịch chưa rõ trạng thái; người trực vận hành xác nhận đã diễn tập trước ngày triển khai đợt hai |
| Kiểm tra thêm trình duyệt | Hoàn tất kiểm thử trên phiên bản trình duyệt được hỗ trợ còn thiếu và lưu kết quả trước khi mở rộng triển khai |

Điều kiện không nên chỉ mô tả công việc như “chạy thêm test”. Cần nói rõ loại bằng chứng nào sẽ xác nhận rủi ro đã giảm hoặc yêu cầu đã được đáp ứng.

## 6. Phân biệt điều kiện phát hành và hành động sau phát hành

Một quyết định có điều kiện có thể chứa các loại cam kết khác nhau. Cần phân biệt rõ để tránh vô tình cho phép phát hành khi một điều kiện bắt buộc chưa được đáp ứng.

**Điều kiện tiên quyết trước phát hành (pre-release condition):** phải hoàn thành trước khi triển khai hoặc mở tính năng. Ví dụ, không còn lỗ hổng nghiêm trọng trong phạm vi bắt buộc, kiểm thử migration đạt, có backup được xác minh hoặc có phê duyệt bảo mật.

**Giới hạn khi phát hành (release restriction):** xác định cách triển khai được phép, chẳng hạn chỉ mở cho nhân viên, giới hạn 5% lưu lượng, giới hạn khu vực hoặc bật qua feature flag.

**Hành động sau phát hành (post-release action):** công việc được phép hoàn tất sau khi phát hành có điều kiện, ví dụ theo dõi chỉ số, hoàn thiện tài liệu hoặc kiểm thử thêm một nền tảng ít phổ biến. Hành động này vẫn phải có chủ sở hữu và hạn.

**Điều kiện dừng hoặc quay lui (stop/rollback condition):** tín hiệu buộc nhóm dừng mở rộng, tắt tính năng hoặc rollback. Ví dụ, tỷ lệ giao dịch thất bại vượt ngưỡng trong 10 phút hoặc xuất hiện bất kỳ giao dịch trùng đã xác nhận.

Không được ghi một điều kiện bắt buộc trước phát hành thành hành động sau phát hành chỉ để kịp thời hạn. Nếu điều kiện tiên quyết chưa đạt, quyết định cần là chưa chấp nhận hoặc giới hạn phát hành theo đúng quy trình và thẩm quyền.

## 7. Ai có quyền chấp nhận?

Chấp nhận sản phẩm và chấp nhận rủi ro cần đúng vai trò. Nhóm kiểm thử cung cấp bằng chứng, phân tích và khuyến nghị; nhóm phát triển giải thích giải pháp kỹ thuật; chủ sản phẩm đánh giá nhu cầu nghiệp vụ; vận hành đánh giá khả năng hỗ trợ. Người có thẩm quyền chịu trách nhiệm về rủi ro mới là người phê duyệt việc chấp nhận rủi ro còn lại.

Vai trò cụ thể tùy tổ chức, nhưng nên làm rõ:

- **Người đề xuất:** tổng hợp bằng chứng và đề nghị chấp nhận hoặc từ chối.
- **Chủ sở hữu rủi ro:** chịu trách nhiệm theo dõi rủi ro và thực hiện biện pháp kiểm soát.
- **Người phê duyệt:** có thẩm quyền chấp nhận rủi ro trong phạm vi đó.
- **Người thực hiện hành động:** hoàn thành công việc còn mở và cung cấp bằng chứng.
- **Người xác minh đóng:** kiểm tra bằng chứng cho thấy điều kiện đã được đáp ứng.

Một người có thể đảm nhận nhiều vai trò trong dự án nhỏ, nhưng trách nhiệm cần được ghi rõ. Với rủi ro cao, nhạy cảm hoặc có yêu cầu độc lập, người đề xuất không nên là người duy nhất phê duyệt và tự xác nhận việc đóng.

Việc một bên liên quan im lặng, tham dự cuộc họp hoặc không phản đối không đồng nghĩa đã chấp nhận. Cần có ghi nhận rõ về người phê duyệt, phạm vi, thời điểm và điều kiện.

## 8. Hồ sơ ghi nhận quyết định chấp nhận có điều kiện

Hồ sơ nên đủ ngắn để dùng được nhưng đủ thông tin để người khác hiểu quyết định sau này. Các trường gợi ý:

| Trường | Nội dung cần ghi |
| --- | --- |
| Mã quyết định | Định danh duy nhất để tham chiếu |
| Sản phẩm và phiên bản | Tên sản phẩm, build, commit hoặc phiên bản phát hành |
| Phạm vi được chấp nhận | Tính năng, người dùng, môi trường, khu vực hoặc đợt triển khai |
| Tiêu chí và bằng chứng | Tiêu chí đã đánh giá, kết quả kiểm thử và nguồn bằng chứng |
| Vấn đề còn mở | Mã lỗi, khoảng trống kiểm thử, giới hạn hoặc phụ thuộc chưa hoàn tất |
| Rủi ro còn lại | Khả năng, tác động, bất định và nhóm bị ảnh hưởng |
| Biện pháp kiểm soát | Giới hạn, giám sát, rollback, hỗ trợ hoặc biện pháp kỹ thuật |
| Điều kiện và hành động | Việc cần làm, chủ sở hữu, hạn, bằng chứng đóng |
| Điều kiện dừng | Ngưỡng hoặc sự kiện buộc dừng, tắt hoặc rollback |
| Thời hạn hiệu lực | Ngày hết hạn hoặc thời điểm bắt buộc đánh giá lại |
| Người phê duyệt | Vai trò, tên hoặc định danh theo quy trình tổ chức và thời điểm |
| Trạng thái theo dõi | Mở, đang thực hiện, chờ xác minh, hoàn tất, quá hạn hoặc bị thu hồi |

Hồ sơ cần liên kết đến báo cáo kiểm thử, lỗi, yêu cầu, đánh giá rủi ro và kế hoạch triển khai. Không nên chép lại toàn bộ nhật ký vào biên bản chấp nhận; hãy tham chiếu nguồn bằng chứng có thể truy cập và đúng phiên bản.

### Mẫu biên bản ngắn

```text
DECISION-ID: ACC-2027-014
PRODUCT / VERSION: Checkout Service / release-3.8.0
DECISION: ACCEPTED WITH CONDITIONS
SCOPE: Enable for internal users, maximum 5% of eligible traffic
EVIDENCE: Regression suite 184/186 passed; 2 cases blocked by provider sandbox
OPEN ITEMS:
  - BUG-214: payment status display may lag after provider timeout
RESIDUAL RISK:
  - Some users may see a pending state longer than expected
CONTROLS:
  - Reconciliation job every 5 minutes
  - Alert when pending age exceeds 10 minutes
  - Feature flag and rollback procedure verified
ACTIONS:
  - Owner: Payments team lead
    Due: 2027-07-15
    Closure evidence: Integration tests for timeout and retry
STOP CONDITION:
  - Any confirmed duplicate charge or reconciliation backlog > 30 minutes
REVIEW / EXPIRY: 2027-07-16
APPROVER: Product release authority
APPROVED AT: 2027-07-10 14:00 UTC
```

Mẫu chỉ minh họa cấu trúc. Các giá trị thực tế phải lấy từ bằng chứng và quy trình của dự án. Không điền số lượng đạt, thời hạn hoặc người phê duyệt theo suy đoán.

## 9. Theo dõi các hành động còn lại

Chấp nhận có điều kiện chỉ hữu ích khi hành động còn lại được quản lý đến khi đóng. Một danh sách hành động nên có ít nhất:

- Mã hành động và liên kết đến quyết định chấp nhận.
- Mô tả kết quả cần đạt, không chỉ tên công việc.
- Chủ sở hữu chịu trách nhiệm cuối cùng.
- Người hoặc nhóm thực hiện nếu khác chủ sở hữu.
- Hạn hoàn thành và mốc trung gian nếu cần.
- Mức ưu tiên và rủi ro nếu trễ hạn.
- Bằng chứng cần cung cấp để đóng.
- Người xác minh và trạng thái hiện tại.

| Trạng thái | Ý nghĩa | Bước tiếp theo |
| --- | --- | --- |
| Open | Chưa bắt đầu hoặc chưa có tiến triển được xác nhận | Phân công và lập kế hoạch |
| In progress | Đang thực hiện | Theo dõi tiến độ và trở ngại |
| Ready for verification | Đã hoàn thành theo người thực hiện, chờ kiểm tra bằng chứng | Người xác minh rà soát kết quả |
| Closed | Bằng chứng đạt tiêu chí đóng đã được xác nhận | Cập nhật hồ sơ rủi ro và quyết định |
| Blocked | Có phụ thuộc hoặc trở ngại ngăn việc hoàn thành | Chuyển cấp hoặc cập nhật quyết định |
| Overdue | Đã quá hạn mà chưa đóng | Đánh giá lại rủi ro và quyền tiếp tục phát hành |
| Cancelled | Hành động không còn cần thiết do thay đổi có phê duyệt | Ghi lý do và cập nhật quyết định liên quan |

Không nên tự động đánh dấu hành động là đóng chỉ vì mã đã được merge hoặc ticket đã chuyển sang Done. Cần xác minh đúng bằng chứng đã cam kết, chẳng hạn kết quả kiểm thử trên build cần phát hành, tài liệu được phê duyệt hoặc diễn tập vận hành.

## 10. Thời hạn, rà soát lại và thu hồi chấp nhận

Chấp nhận có điều kiện không nên có hiệu lực vô thời hạn. Hồ sơ cần ghi ngày hết hạn hoặc thời điểm đánh giá lại. Thời hạn nên dựa trên mức rủi ro và tốc độ thay đổi của sản phẩm.

Cần đánh giá lại khi:

- Hành động đến hạn nhưng chưa hoàn thành.
- Xuất hiện lỗi mới, sự cố production hoặc bằng chứng làm tăng rủi ro.
- Phạm vi, phiên bản, cấu hình hoặc lượng người dùng thay đổi.
- Biện pháp kiểm soát không hoạt động như giả định.
- Có thay đổi từ nhà cung cấp, quy định hoặc yêu cầu nghiệp vụ.
- Điều kiện dừng bị kích hoạt.
- Quyết định hết thời hạn.

Việc đánh giá lại có thể dẫn đến một trong các kết quả:

1. **Đóng điều kiện:** bằng chứng xác nhận hành động đã hoàn tất và rủi ro đã giảm như dự kiến.
2. **Gia hạn có phê duyệt:** có lý do, đánh giá rủi ro cập nhật, biện pháp kiểm soát vẫn hiệu lực và thời hạn mới rõ ràng.
3. **Thu hẹp phạm vi:** giới hạn người dùng, tính năng hoặc lưu lượng để giảm rủi ro.
4. **Tạm dừng hoặc rollback:** rủi ro vượt ngưỡng, điều kiện dừng xảy ra hoặc biện pháp kiểm soát thất bại.
5. **Từ chối chấp nhận:** bằng chứng mới cho thấy không thể tiếp tục trong điều kiện an toàn hoặc phù hợp.

Gia hạn không nên là thao tác mặc định mỗi khi hành động quá hạn. Người phê duyệt cần xem lại lý do trễ, tác động hiện tại và khả năng thực thi điều kiện. Nếu rủi ro đã thay đổi, cần tạo đánh giá mới thay vì chỉ kéo dài ngày cũ.

## 11. Ví dụ thực tế: phát hành có điều kiện cho luồng thanh toán

Giả sử một phiên bản mới của Checkout Service đã hoàn thành kiểm thử chức năng và hồi quy. Các trường hợp thanh toán thành công, bị từ chối và hoàn tiền cơ bản đều đạt. Tuy nhiên, môi trường sandbox của nhà cung cấp chưa ổn định nên hai trường hợp timeout sau khi nhà cung cấp đã nhận yêu cầu chưa thể xác minh đầy đủ.

Nhóm phân tích thấy rủi ro là hệ thống có thể hiển thị trạng thái chờ lâu hoặc cần đối soát trước khi thử lại. Nếu xử lý sai, khách hàng có thể gửi lại yêu cầu và phát sinh giao dịch trùng. Đây là rủi ro liên quan đến tiền, nên không thể xem hai trường hợp bị chặn như kiểm thử đạt.

Nhóm cân nhắc các phương án:

- Hoãn phát hành toàn bộ cho đến khi sandbox ổn định và hoàn tất kiểm thử.
- Phát hành giới hạn cho nhân viên nội bộ với dữ liệu giao dịch thử, không xử lý thanh toán thật.
- Nếu đã có cơ chế kiểm soát được xác minh độc lập, triển khai giới hạn lưu lượng với giám sát đối soát và khả năng tắt nhanh.

Giả sử cơ chế idempotency, đối soát và rollback đã được xác minh ở phạm vi phù hợp, người có thẩm quyền có thể phê duyệt triển khai giới hạn. Quyết định phải ghi rõ:

1. Chỉ bật cho nhóm người dùng và mức lưu lượng được phê duyệt.
2. Không thử lại giao dịch khi trạng thái lần đầu chưa được xác minh; truy vấn hoặc đối soát trước.
3. Theo dõi số giao dịch chờ, tuổi giao dịch, timeout và giao dịch trùng.
4. Tắt feature flag ngay nếu xuất hiện giao dịch trùng đã xác nhận hoặc backlog đối soát vượt ngưỡng.
5. Nhóm thanh toán hoàn tất kiểm thử timeout và retry trước ngày đã định.
6. Người xác minh kiểm tra kết quả, sau đó người phê duyệt xem xét mở rộng phạm vi.

Trong ví dụ này, quyết định không có nghĩa toàn bộ luồng thanh toán đã được xác minh. Nó cho phép một phạm vi hạn chế trong điều kiện được kiểm soát và có thời hạn. Nếu cơ chế ngăn giao dịch trùng chưa có bằng chứng hoặc không thể tắt tính năng nhanh, phương án phù hợp có thể là hoãn phát hành.

## 12. Truyền đạt quyết định cho các bên liên quan

Quyết định cần được truyền đạt bằng ngôn ngữ rõ ràng để người triển khai, vận hành, hỗ trợ và nghiệp vụ hiểu đúng phạm vi.

Một thông báo chấp nhận có điều kiện nên trả lời:

- Phiên bản hoặc phạm vi nào được phép tiếp tục?
- Những tiêu chí nào đã đạt và bằng chứng ở đâu?
- Những vấn đề hoặc khoảng trống nào còn mở?
- Rủi ro và tác động tiềm tàng là gì?
- Biện pháp kiểm soát nào phải được duy trì?
- Hành động nào cần hoàn tất, ai chịu trách nhiệm và khi nào?
- Điều kiện nào buộc dừng, tắt tính năng hoặc rollback?
- Ai đã phê duyệt và khi nào phải xem xét lại?

Tránh các câu chung như “đã được QA approve” nếu chúng che khuất điều kiện. Nên nêu rõ “được phép triển khai giới hạn cho nhóm nội bộ đến ngày X; hai trường hợp timeout chưa có bằng chứng; nhóm thanh toán phải hoàn tất kiểm thử và người phê duyệt đánh giá lại trước khi mở rộng”.

Thông tin phải có sẵn ở nơi các nhóm tra cứu trạng thái phát hành, lỗi và hành động. Nếu có thay đổi phạm vi hoặc điều kiện, cập nhật hồ sơ và thông báo cho những bên bị ảnh hưởng.

## 13. Những sai lầm thường gặp

- **Chấp nhận bằng lời nói:** không có người phê duyệt, phạm vi hoặc thời hạn khiến quyết định không thể truy nguyên.
- **Dùng chấp nhận có điều kiện để bỏ qua tiêu chí bắt buộc:** điều kiện không thể miễn trừ nghĩa vụ pháp lý, bảo mật hoặc an toàn nếu quy trình không cho phép.
- **Gọi kiểm thử bị chặn là đạt:** thiếu bằng chứng phải được ghi là chưa xác minh.
- **Điều kiện không có chủ sở hữu:** công việc còn mở dễ bị bỏ quên.
- **Không có bằng chứng đóng:** ticket hoàn thành nhưng không chứng minh rủi ro đã giảm.
- **Không đặt ngày hết hạn:** ngoại lệ tạm thời trở thành trạng thái kéo dài không được xem xét.
- **Không nêu điều kiện dừng:** nhóm không biết khi nào phải tắt tính năng hoặc rollback.
- **Gia hạn tự động:** bỏ qua việc đánh giá lại tác động và lý do chậm.
- **Mở rộng phạm vi mà không phê duyệt lại:** quyết định cho một nhóm nhỏ bị áp dụng nhầm cho toàn bộ người dùng.
- **Không cập nhật rủi ro sau khi đóng hành động:** hồ sơ tiếp tục thể hiện mức rủi ro cũ hoặc bỏ sót rủi ro mới.

## 14. Checklist trước khi ghi nhận chấp nhận có điều kiện

- [ ] Phạm vi sản phẩm, phiên bản, người dùng và môi trường được nêu rõ.
- [ ] Kết quả kiểm thử được giữ nguyên và có thể truy nguyên.
- [ ] Mọi lỗi, khoảng trống bằng chứng và giới hạn còn mở đã được liệt kê.
- [ ] Rủi ro còn lại được đánh giá về khả năng xảy ra, tác động và bất định.
- [ ] Các yêu cầu bắt buộc và điều kiện không được miễn trừ đã được xem xét.
- [ ] Biện pháp giảm thiểu, giám sát, rollback hoặc giới hạn triển khai có thể thực hiện.
- [ ] Mỗi hành động có kết quả cần đạt, chủ sở hữu, hạn và bằng chứng đóng.
- [ ] Điều kiện dừng và người có trách nhiệm phản ứng đã được xác định.
- [ ] Người phê duyệt có thẩm quyền đã chấp thuận rõ ràng.
- [ ] Thời hạn hiệu lực và thời điểm đánh giá lại được ghi nhận.
- [ ] Quyết định đã được truyền đạt đến phát triển, kiểm thử, vận hành, hỗ trợ và nghiệp vụ liên quan.

## 15. Những điểm cần ghi nhớ

- Chấp nhận có điều kiện là quyết định có phạm vi, điều kiện, chủ sở hữu và thời hạn rõ ràng.
- Kết quả kiểm thử, đánh giá rủi ro và quyết định chấp nhận là các thông tin khác nhau; không sửa kết quả kiểm thử để hợp thức hóa quyết định.
- Rủi ro còn lại cần được hiểu về khả năng xảy ra, tác động, khả năng phát hiện, khả năng khôi phục và mức độ bất định.
- Mỗi hành động còn mở cần có người chịu trách nhiệm, hạn hoàn thành, bằng chứng đóng và cách xử lý khi quá hạn.
- Điều kiện tiên quyết trước phát hành phải hoàn tất trước khi triển khai; không đổi chúng thành việc sau phát hành nếu không có phê duyệt phù hợp.
- Quyết định cần nêu giới hạn triển khai, điều kiện dừng, thời hạn và người có thẩm quyền.
- Khi có bằng chứng mới hoặc điều kiện thay đổi, phải đánh giá lại; có thể đóng, gia hạn có phê duyệt, thu hẹp, tạm dừng hoặc thu hồi chấp nhận.

## Câu hỏi tự kiểm tra

1. Chấp nhận có điều kiện khác gì với kết quả kiểm thử đạt và quyết định phát hành thông thường?
2. Vì sao một trường hợp kiểm thử bị chặn không thể được ghi nhận như trường hợp đạt?
3. Hãy viết một điều kiện chấp nhận có đủ phạm vi, chủ sở hữu, hạn hoàn thành, bằng chứng đóng và cách xử lý nếu không đạt.
4. Ai nên chịu trách nhiệm cung cấp bằng chứng, sở hữu rủi ro và phê duyệt chấp nhận rủi ro còn lại?
5. Một lỗi ảnh hưởng thấp có thể được chấp nhận có điều kiện trong những hoàn cảnh nào? Cần có biện pháp kiểm soát gì?
6. Vì sao quyết định chấp nhận có điều kiện cần thời hạn hiệu lực và điều kiện dừng?
7. Nếu một hành động còn mở quá hạn và xuất hiện sự cố production liên quan, nhóm cần xem xét lại những thông tin và quyết định nào?
8. Hãy lập một biên bản chấp nhận có điều kiện cho một tính năng bạn biết, bao gồm bằng chứng, rủi ro còn lại, hành động và người phê duyệt.
