# Duy trì tri thức khi thay đổi người phụ trách

Trong chương **Cộng tác và trách nhiệm** của module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu cách giữ cho một phần mềm tiếp tục được hiểu, vận hành và thay đổi an toàn khi người đang phụ trách một thành phần rời nhóm, chuyển sang nhiệm vụ khác hoặc bàn giao cho đồng nghiệp.

Mục tiêu của module là hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Những thuộc tính này không chỉ nằm trong các dòng code. Chúng còn phụ thuộc vào việc nhóm có hiểu vì sao một quyết định được đưa ra, biết cách kiểm tra hành vi, tìm được cấu hình, xử lý sự cố và xác định ai có quyền quyết định khi yêu cầu thay đổi.

Một hệ thống có thể build thành công nhưng vẫn rất khó tiếp quản nếu chỉ một người biết cách triển khai, hiểu dữ liệu cũ, nhớ các ngoại lệ của khách hàng hoặc biết vì sao một đoạn logic không được sửa. Khi người đó chuyển công việc, nhóm có thể mất nhiều tuần để khôi phục bối cảnh, lặp lại điều tra cũ hoặc vô tình phá một giả định quan trọng.

> **Duy trì tri thức không có nghĩa ghi lại mọi điều một người biết. Đó là làm cho thông tin cần thiết để hiểu, thay đổi, kiểm thử và vận hành một thành phần có thể được tìm thấy, kiểm chứng và tiếp tục cập nhật bởi người khác.**

Bài này trình bày cách nhận diện tri thức có nguy cơ bị mất, tổ chức bàn giao theo mức rủi ro, dùng code/test/tài liệu làm nguồn tri thức có thể kiểm chứng, xác nhận người nhận đã tiếp quản được công việc và xử lý các tình huống chuyển giao đột ngột.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích vì sao thay đổi người phụ trách có thể làm tăng rủi ro bảo trì dù mã nguồn không đổi.
2. Phân biệt **quyền sở hữu**, **trách nhiệm vận hành**, **kiến thức ngữ cảnh** và **quyền quyết định**.
3. Nhận diện tri thức ngầm có nguy cơ tập trung ở một người hoặc một nhóm nhỏ.
4. Lập bản đồ tri thức cần bàn giao theo thành phần, rủi ro và công việc thực tế.
5. Chọn hình thức chuyển giao phù hợp: tài liệu, walkthrough, pair programming, shadowing và reverse shadowing.
6. Dùng test, ADR, runbook, dashboard và lịch sử thay đổi để giúp người mới xác minh thông tin.
7. Bảo đảm quyền truy cập, thông tin vận hành và trách nhiệm hỗ trợ được chuyển giao an toàn.
8. Thiết kế tiêu chí hoàn tất bàn giao dựa trên khả năng thực hiện nhiệm vụ, không chỉ dựa vào việc đã gửi tài liệu.
9. Duy trì tri thức sau bàn giao bằng review, cập nhật tài liệu và chia sẻ kiến thức trong công việc thường ngày.

## 2. Vì sao thay đổi người phụ trách tạo rủi ro?

Một thành phần phần mềm thường tích lũy nhiều loại hiểu biết:

- **Tri thức về hành vi:** hệ thống cần làm gì trong điều kiện bình thường và ngoại lệ.
- **Tri thức về thiết kế:** vì sao chọn kiến trúc, thuật toán hoặc ranh giới module hiện tại.
- **Tri thức về dữ liệu:** ý nghĩa field, trạng thái, dữ liệu lịch sử và quy tắc chuyển đổi.
- **Tri thức vận hành:** cách deploy, rollback, giám sát, khôi phục và xử lý cảnh báo.
- **Tri thức về phụ thuộc:** service, thư viện, nhóm khác, nhà cung cấp hoặc client bên ngoài.
- **Tri thức về quy trình:** ai phê duyệt, khi nào cần security review, thay đổi nào phải phối hợp.
- **Tri thức về lịch sử:** những phương án đã thử, sự cố từng gặp và giả định đã bị bác bỏ.

Một phần thông tin nằm trong code, test và tài liệu. Một phần chỉ tồn tại trong kinh nghiệm của người đã nhiều lần xử lý hệ thống.

### 2.1. Những rủi ro thường xuất hiện

| Rủi ro | Biểu hiện | Hậu quả có thể xảy ra |
| --- | --- | --- |
| **Tri thức tập trung** | Chỉ một người biết cách thay đổi một module. | Công việc bị chặn khi người đó vắng mặt. |
| **Bối cảnh bị mất** | Không ai biết lý do một giới hạn hoặc workaround tồn tại. | Nhóm lặp lại điều tra hoặc xóa nhầm một bảo vệ quan trọng. |
| **Vận hành không có người nhận** | Không rõ ai xử lý alert, deploy hoặc rollback. | Sự cố kéo dài và trách nhiệm bị bỏ trống. |
| **Tài liệu lỗi thời** | Runbook hoặc sơ đồ không còn khớp hệ thống. | Người mới làm theo hướng dẫn sai. |
| **Quyền truy cập không đầy đủ** | Người nhận không có quyền đọc log, deploy hoặc xem dashboard cần thiết. | Bàn giao trên giấy nhưng không thể thực hiện công việc. |
| **Quyết định không rõ** | Không biết ai có quyền chấp nhận thay đổi API hoặc dữ liệu. | Chậm trễ, quyết định mâu thuẫn hoặc rủi ro không được đánh giá. |

### 2.2. Người rời đi không phải nguyên nhân duy nhất

Tri thức có thể bị mất do đổi nhóm, nghỉ phép dài ngày, luân chuyển trách nhiệm, thuê ngoài kết thúc hợp đồng, tổ chức tái cấu trúc hoặc một module được chuyển sang đội khác.

Vấn đề cốt lõi là **hệ thống và quy trình có phụ thuộc quá nhiều vào hiểu biết cá nhân hay không**. Không nên quy trách nhiệm cho người chuyển đi vì chưa viết đủ tài liệu nếu tổ chức chưa dành thời gian, quyền hạn và cơ chế để duy trì tri thức.

## 3. Phân biệt quyền sở hữu và tri thức

Hai khái niệm thường bị trộn lẫn:

- **Ownership (quyền sở hữu):** nhóm hoặc vai trò chịu trách nhiệm về kết quả, sức khỏe và các quyết định trong phạm vi thành phần.
- **Knowledge (tri thức):** khả năng giải thích hành vi, bối cảnh, giới hạn và cách làm việc với thành phần đó.

Một người có thể hiểu rất rõ một hệ thống nhưng không còn là người có quyền phê duyệt thay đổi. Ngược lại, người vừa nhận ownership có thể chưa hiểu hết các quyết định cũ.

| Câu hỏi | Quyền sở hữu trả lời | Tri thức trả lời |
| --- | --- | --- |
| Ai chịu trách nhiệm khi service có sự cố? | Nhóm/vai trò on-call hoặc owner. | Người đó biết tìm log và xử lý thế nào. |
| Ai chấp thuận thay đổi hợp đồng? | Người hoặc nhóm có quyền quyết định. | Người hiểu client và tác động tương thích. |
| Ai cập nhật runbook? | Owner được giao trách nhiệm. | Người biết thao tác và giới hạn hiện tại. |
| Ai có thể review PR? | Quy tắc phân công review. | Người hiểu ngữ nghĩa và rủi ro của thay đổi. |

**Bàn giao ownership mà không chuyển tri thức** khiến người nhận chịu trách nhiệm nhưng thiếu khả năng hành động. **Chuyển tài liệu mà không chuyển quyền quyết định** khiến người nhận hiểu vấn đề nhưng không biết ai có thể chấp thuận giải pháp.

Cần chuyển cả hai phần theo cách rõ ràng.

## 4. Tri thức tường minh và tri thức ngầm

### 4.1. Tri thức tường minh (*explicit knowledge*)

Là thông tin có thể đọc, tìm và kiểm tra trong một nguồn cụ thể:

- README và hướng dẫn bắt đầu.
- Sơ đồ kiến trúc và dependency.
- ADR ghi quyết định cùng lý do.
- JavaDoc, comment giải thích bất biến.
- Unit/integration/contract test.
- Runbook và hướng dẫn triển khai.
- Dashboard, alert và định nghĩa metric.
- API/event schema, migration và ví dụ dữ liệu.
- Lịch sử PR, issue và incident report.

Tri thức tường minh giúp người khác tiếp cận mà không cần hỏi tác giả, nhưng chỉ có ích khi **đúng, dễ tìm và được duy trì**.

### 4.2. Tri thức ngầm (*tacit knowledge*)

Là hiểu biết hình thành qua kinh nghiệm và khó diễn đạt đầy đủ thành tài liệu:

- Biết log nào thường xuất hiện trước một sự cố.
- Nhận ra một cảnh báo thường là dấu hiệu của lỗi upstream.
- Biết dữ liệu staging không đại diện cho một nhóm khách hàng đặc biệt.
- Hiểu vì sao một lần deploy cần chờ job đồng bộ hoàn tất.
- Biết nhóm phụ thuộc thường phản hồi qua kênh hoặc quy trình nào.
- Nhận ra một thay đổi nhỏ có thể tác động đến báo cáo lịch sử.

Không thể chuyển toàn bộ tri thức ngầm bằng cách gửi một file. Cần **quan sát, cùng thực hiện, giải thích quyết định và để người nhận thực hành lại**.

### 4.3. Biến tri thức quan trọng thành thông tin có thể kiểm chứng

Không phải mọi kinh nghiệm đều cần viết thành tài liệu dài. Hãy chọn những hiểu biết có thể ảnh hưởng đến quyết định hoặc gây rủi ro:

| Tri thức ngầm | Cách làm rõ |
| --- | --- |
| “Đừng chạy job này hai lần cùng lúc.” | Ghi điều kiện concurrency, hậu quả và cách kiểm tra trạng thái job. |
| “Khách hàng cũ có mã vùng đặc biệt.” | Mô tả quy tắc dữ liệu, test mẫu đã ẩn danh và nơi xác minh. |
| “Rollback không an toàn sau migration này.” | Ghi rõ điểm không thể đảo ngược, phương án forward-fix và yêu cầu backup. |
| “Alert này thường do queue upstream.” | Liên kết dashboard, trace và các bước phân biệt nguyên nhân. |
| “Không được tính lại hóa đơn bằng giá hiện tại.” | Ghi bất biến nghiệp vụ và test bảo vệ snapshot lịch sử. |

Mục tiêu là giúp người tiếp quản **kiểm chứng và hành động**, không yêu cầu họ tin vào một lời truyền miệng.

## 5. Bắt đầu bằng bản đồ tri thức và rủi ro

Trước khi bàn giao, cần biết phạm vi nào đang được chuyển giao. Một danh sách tên file không đủ vì một module có thể phụ thuộc vào quy trình, dữ liệu và nhóm bên ngoài.

### 5.1. Lập bản đồ theo thành phần và nhiệm vụ

| Phạm vi | Điều người nhận cần biết | Bằng chứng hoặc nguồn |
| --- | --- | --- |
| Hành vi nghiệp vụ | Đầu vào, đầu ra, quy tắc, ngoại lệ và bất biến. | Spec, test, ví dụ đã xác nhận. |
| Kiến trúc | Thành phần gọi nhau, ranh giới và phụ thuộc. | Sơ đồ, ADR, cấu hình. |
| Code | Điểm bắt đầu, nơi sở hữu logic và convention quan trọng. | Package, class, JavaDoc, PR. |
| Test | Cách chạy, test nào bảo vệ rủi ro nào. | Build task, test suite, CI report. |
| Dữ liệu | Schema, ownership, migration và dữ liệu lịch sử. | DDL, migration, data dictionary. |
| Vận hành | Deploy, rollback, health, alert và khôi phục. | Runbook, dashboard, release record. |
| Bảo mật | Trust boundary, role, secret và quyền cần thiết. | Threat model, access policy, security review. |
| Phối hợp | Nhóm phụ thuộc, SLA, quy trình phê duyệt. | Service catalog, issue, contact rota. |

### 5.2. Ưu tiên theo mức rủi ro

Không cần bàn giao tất cả module với độ sâu như nhau. Có thể ưu tiên:

- Thành phần đang có incident hoặc nhiều thay đổi chưa hoàn tất.
- Module liên quan thanh toán, quyền truy cập, dữ liệu nhạy cảm hoặc giao dịch.
- Service không có người thay thế hiểu cách vận hành.
- Thành phần có deploy/migration khó rollback.
- Hợp đồng với client hoặc vendor bên ngoài.
- Công việc có deadline hoặc quyết định đang chờ.

Một module ổn định, ít tác động và có test tốt có thể cần một walkthrough ngắn. Một hệ thống dữ liệu quan trọng cần nhiều phiên thực hành và xác nhận.

### 5.3. Không dùng số lượng file làm thước đo độ phức tạp bàn giao

Một service có 30 file có thể có hợp đồng rất đơn giản. Một job định kỳ chỉ có một class nhưng liên quan tới dữ liệu tài chính, lịch chạy, quyền truy cập và quy trình khôi phục. **Độ sâu bàn giao phải theo rủi ro và công việc**, không theo số file.

## 6. Một quy trình bàn giao có thể kiểm chứng

Một quy trình thực tế có thể gồm bảy giai đoạn:

~~~text
Xác định phạm vi và rủi ro
          |
          v
Chọn người nhận và quyền quyết định
          |
          v
Thu thập nguồn tri thức hiện có
          |
          v
Walkthrough + cùng thực hiện nhiệm vụ
          |
          v
Người nhận thực hành lại (reverse shadow)
          |
          v
Xác nhận ownership và công việc còn mở
          |
          v
Theo dõi sau chuyển giao và cập nhật tri thức
~~~

### 6.1. Xác định thời gian và phạm vi

Trước hết làm rõ:

- Ngày người cũ ngừng phụ trách.
- Thời gian overlap có thể dành cho chuyển giao.
- Các service/module nằm trong phạm vi.
- Việc nào đang triển khai, việc nào chờ quyết định.
- Ai nhận trách nhiệm kỹ thuật và vận hành.
- Những phần cần người khác hỗ trợ chuyên môn.

Nếu thời gian bàn giao ngắn, chọn nhiệm vụ quan trọng nhất và ghi lại những phần chưa chuyển được để có kế hoạch giảm rủi ro.

### 6.2. Thu thập nguồn tri thức trước buổi trao đổi

Người bàn giao nên chuẩn bị link tới README, ADR, runbook, test, dashboard, PR/issue và incident report có liên quan. Tránh bắt đầu buổi họp bằng việc chia sẻ màn hình rồi tìm file ngẫu nhiên.

Người nhận nên đọc trước các nguồn này và ghi lại câu hỏi. Cách làm đó giúp thời gian trao đổi tập trung vào **bối cảnh chưa thể hiểu chỉ bằng tài liệu**.

### 6.3. Walkthrough theo nhiệm vụ thật

Thay vì đi qua từng package, hãy chọn các nhiệm vụ:

- Làm sao thêm một quy tắc nghiệp vụ?
- Làm sao chạy test và biết test nào cần chạy?
- Làm sao kiểm tra một request thất bại?
- Làm sao deploy một phiên bản mới?
- Nếu migration lỗi thì phải làm gì?
- Thay đổi API ảnh hưởng client nào?
- Khi nào cần hỏi nhóm phụ thuộc hoặc xin phê duyệt?

Người bàn giao giải thích **vì sao** thực hiện từng bước, điều kiện dừng và dấu hiệu thành công.

### 6.4. Người nhận thực hành lại

Sau walkthrough, người nhận tự thực hiện một nhiệm vụ đại diện trong khi người cũ quan sát. Ví dụ: sửa một test, tra một trace, tạo một thay đổi nhỏ hoặc diễn tập quy trình rollback trên môi trường an toàn.

Đây là cách phát hiện sớm khoảng trống giữa “đã nghe giải thích” và “có thể tự làm”.

### 6.5. Xác nhận ownership và điểm hỗ trợ

Ghi rõ ngày chuyển giao, nhóm/vai trò owner mới, reviewer hoặc người hỗ trợ, kênh escalation và quyết định còn chờ. Một người nhận mới không nhất thiết phải biết mọi thứ ngay, nhưng phải biết **ai có thể giúp và khi nào cần gọi hỗ trợ**.

## 7. Các hình thức chia sẻ tri thức và khi nào nên dùng

| Hình thức | Mục đích | Phù hợp khi | Giới hạn |
| --- | --- | --- | --- |
| **Tài liệu hướng dẫn** | Giữ thông tin có thể tìm và đọc lại. | Quy trình lặp lại, hợp đồng, cấu hình. | Dễ lỗi thời nếu không có owner. |
| **Walkthrough** | Giải thích bối cảnh và quyết định. | Hệ thống có nhiều giả định ngầm. | Người nhận có thể chỉ nghe thụ động. |
| **Pair programming** | Cùng thực hiện thay đổi thật. | Logic phức tạp, test khó hoặc code ít người hiểu. | Tốn thời gian đồng thời của hai người. |
| **Shadowing** | Người mới quan sát người cũ làm việc. | Incident, deploy, review hoặc vận hành. | Người mới chưa chứng minh khả năng tự làm. |
| **Reverse shadowing** | Người mới thực hiện, người cũ quan sát và góp ý. | Kiểm tra khả năng tiếp quản. | Cần môi trường an toàn và phạm vi phù hợp. |
| **Bài tập diễn tập** | Kiểm tra phản ứng trước tình huống. | Rollback, phục hồi, sự cố, migration. | Phải cập nhật theo hệ thống thực. |
| **ADR/decision log** | Giữ lý do và đánh đổi của quyết định. | Kiến trúc hoặc hợp đồng có ảnh hưởng dài hạn. | Không thay thế hướng dẫn thao tác. |

Một buổi bàn giao tốt thường kết hợp nhiều hình thức. Tài liệu giúp giữ thông tin; walkthrough giải thích bối cảnh; reverse shadowing xác minh người nhận đã hiểu đủ để hành động.

## 8. Những nguồn tri thức cần giữ trong repository

### 8.1. README và hướng dẫn bắt đầu

README của module nên giúp người mới trả lời nhanh:

- Thành phần này giải quyết vấn đề gì?
- Điểm bắt đầu của code nằm ở đâu?
- Cần công cụ và cấu hình nào?
- Chạy build và test bằng cách nào?
- Link tới tài liệu kiến trúc, API và runbook ở đâu?
- Nhóm nào sở hữu thành phần?

README không nên chứa toàn bộ runbook hoặc mọi quyết định. Nó nên đóng vai trò **cửa vào** tới nguồn đúng.

### 8.2. ADR giữ lý do của quyết định

Một ADR (*Architecture Decision Record*) có thể ghi:

- Bối cảnh và vấn đề.
- Các phương án đã cân nhắc.
- Quyết định được chọn.
- Lý do và đánh đổi.
- Hệ quả, giới hạn và điều kiện xem lại.

Ví dụ: vì sao service lưu snapshot phí vận chuyển tại thời điểm tạo đơn thay vì tính lại theo chính sách hiện tại. Nếu chỉ nhìn code, người mới có thể nghĩ đây là dữ liệu dư thừa và xóa nó.

### 8.3. Test là tài liệu có thể thực thi

Một test có tên rõ và assertion có ý nghĩa thể hiện ví dụ về hành vi:

~~~java
@Test
void invoiceKeepsShippingFeeCalculatedAtOrderCreation() {
    // Ví dụ: hóa đơn lịch sử dùng khoản phí đã chốt,
    // không tính lại bằng chính sách hiện hành.
    Order order = orderWithStoredShippingFee(30_000L);
    ShippingPolicy currentPolicy = freeShippingForEveryTier();

    Invoice invoice = invoiceService.create(order, currentPolicy);

    assertEquals(30_000L, invoice.shippingFeeCents());
}
~~~

Đoạn mã là ví dụ minh họa một hợp đồng lịch sử. Tên helper và lớp service đại diện cho mô hình giả định; trong dự án thật, test cần phản ánh chính xác API và dữ liệu hiện có.

Test có thể phát hiện khi hành vi thay đổi, nhưng không tự giải thích mọi lý do kiến trúc. **Kết hợp test với ADR và tài liệu nghiệp vụ** giúp người nhận hiểu cả điều gì phải giữ và vì sao.

### 8.4. JavaDoc và comment

JavaDoc nên mô tả hợp đồng người gọi cần biết: ý nghĩa tham số, đơn vị, giá trị trả về, ngoại lệ và giới hạn. Comment trong code nên giải thích bất biến, lý do hoặc workaround khó suy ra.

Tránh comment lặp lại cú pháp. Ví dụ “tăng i lên 1” không thêm nhiều tri thức; nhưng “phải xử lý event theo thứ tự sequence vì downstream dùng sequence để loại bản trùng” có thể rất quan trọng.

### 8.5. Lịch sử PR và issue

PR có thể giữ bối cảnh của thay đổi cụ thể, review discussion và các phương án đã bị từ chối. Issue có thể giữ công việc còn mở, người phụ thuộc và tiêu chí chấp nhận.

Tuy nhiên, lịch sử PR không nên là nơi duy nhất chứa hợp đồng hiện tại. Người mới cần một đường dẫn từ README/ADR/test tới quyết định quan trọng, thay vì phải tìm kiếm hàng trăm cuộc thảo luận.

## 9. Runbook và tri thức vận hành

Một module có thể dễ sửa trong IDE nhưng khó vận hành nếu không ai biết cách triển khai hoặc phục hồi.

Runbook nên nêu rõ:

1. **Phạm vi:** service, môi trường và phiên bản áp dụng.
2. **Điều kiện trước:** quyền cần thiết, dependency, trạng thái hệ thống.
3. **Thao tác:** các bước theo thứ tự, lệnh hoặc đường dẫn công cụ.
4. **Kết quả mong đợi:** log, health check hoặc trạng thái xác nhận.
5. **Dấu hiệu thất bại:** timeout, alert, lỗi cấu hình và cách phân loại.
6. **Khôi phục:** rollback, forward-fix, retry hoặc cách dừng an toàn.
7. **Escalation:** nhóm/vai trò liên hệ khi vượt phạm vi.
8. **Cập nhật:** owner và lần xác minh gần nhất.

### 9.1. Phân biệt thao tác thường ngày và khôi phục khẩn cấp

Hướng dẫn deploy bình thường không đủ thay thế runbook sự cố. Người tiếp quản cần biết:

- Có thể rollback ứng dụng nhưng không rollback schema hay không?
- Một job có idempotent không?
- Có cần tạm dừng consumer trước khi sửa dữ liệu?
- Dữ liệu nào cần backup?
- Khi nào không được retry vì có thể tạo giao dịch trùng?
- Alert nào cần gọi on-call khác?

Những câu trả lời này phải được xác minh bằng diễn tập hoặc lịch sử sự cố, không chỉ ghi theo trí nhớ.

### 9.2. Không ghi secret trực tiếp trong tài liệu

Runbook có thể nói cách truy cập secret manager hoặc cách xin quyền, nhưng không được chứa mật khẩu, token, private key hoặc dữ liệu khách hàng. Việc bàn giao phải chuyển **quyền truy cập qua cơ chế được phê duyệt**, không gửi bí mật qua chat hay tài liệu.

## 10. Bàn giao code: từ bản đồ package tới luồng nghiệp vụ

Người mới thường không cần nghe giải thích mọi class. Họ cần biết cách đi từ một yêu cầu tới nơi quyết định hành vi.

Một walkthrough code có thể theo đường:

~~~text
Yêu cầu / API / Event
          |
          v
Controller hoặc Consumer
          |
          v
Application Service
          |
          v
Domain Policy / Model
          |
          v
Repository / External Gateway
          |
          v
Kết quả, event hoặc trạng thái được lưu
          |
          v
Test bảo vệ hợp đồng
~~~

Đây là sơ đồ khái niệm; một dự án có thể tổ chức khác. Hãy giải thích các ranh giới thật của hệ thống, chứ không ép mọi codebase vào cùng một kiến trúc.

### 10.1. Những câu hỏi cần trả lời khi bàn giao một luồng

- Đầu vào đến từ đâu và đã được xác thực ở đâu?
- Thành phần nào sở hữu quy tắc nghiệp vụ?
- Dữ liệu nào là nguồn sự thật?
- Tác dụng phụ xảy ra ở đâu?
- Transaction hoặc idempotency được bảo vệ thế nào?
- Lỗi được chuyển đổi và trả cho client ra sao?
- Test nào bảo vệ đường thành công và đường thất bại?
- Có một consumer hoặc job khác dùng cùng dữ liệu không?

Người nhận nên tự lần theo một request hoặc event thật trên môi trường dev, sau đó giải thích lại luồng bằng lời của mình.

## 11. Ví dụ Java: bàn giao một chính sách vận chuyển

Giả sử một nhóm sở hữu module tính phí vận chuyển. Người phụ trách cũ hiểu rõ ba điều mà code đơn thuần chưa làm nổi bật:

1. Phí dự tính dùng chính sách hiện tại.
2. Hóa đơn đã chốt phải giữ phí tại thời điểm tạo đơn.
3. Thay đổi ngưỡng phải được kiểm tra ở đúng dưới và đúng ngưỡng.

Nếu chỉ bàn giao class tính phí mà không truyền những quy tắc này, người mới có thể vô tình dùng logic dự tính để tính lại hóa đơn lịch sử.

### 11.1. Hợp đồng được mô tả bằng code và test

~~~java
enum CustomerTier {
    STANDARD, PREMIUM
}

record InvoiceShippingFee(long amountCents) {
    InvoiceShippingFee {
        if (amountCents < 0) {
            throw new IllegalArgumentException("Negative fee");
        }
    }
}

final class ShippingPolicy {
    long estimate(long subtotalCents, CustomerTier tier) {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }
        if (tier == null) {
            throw new NullPointerException("tier");
        }

        long threshold = tier == CustomerTier.PREMIUM
                ? 300_000L : 500_000L;
        return subtotalCents >= threshold ? 0L : 30_000L;
    }
}
~~~

Đoạn code minh họa phép tính dự kiến. Nó không bao gồm database, cấu hình theo thời gian hoặc chính sách thực tế của một sản phẩm.

Test thể hiện sự khác nhau giữa phí dự tính và khoản phí đã chốt:

~~~java
@Test
void historicalInvoiceUsesStoredFeeAfterPolicyChanges() {
    InvoiceShippingFee storedFee = new InvoiceShippingFee(30_000L);

    ShippingPolicy currentPolicy = new ShippingPolicy();
    long currentEstimate =
            currentPolicy.estimate(600_000L, CustomerTier.STANDARD);

    assertEquals(30_000L, storedFee.amountCents());
    assertEquals(0L, currentEstimate);
}
~~~

Test minh họa hai giá trị có vòng đời khác nhau. Trong ứng dụng thật, cần xác minh invoice lấy phí đã lưu từ persistence và không vô tình gọi lại policy hiện hành.

### 11.2. Nội dung người phụ trách cũ cần bàn giao

| Chủ đề | Thông tin cần truyền | Người nhận xác minh bằng cách nào |
| --- | --- | --- |
| Chính sách hiện tại | Ngưỡng STANDARD/PREMIUM và đơn vị tiền. | Đọc policy và test giá trị biên. |
| Phí dự tính | Tính theo chính sách hiện hành. | Chạy test hoặc luồng preview trên dev. |
| Hóa đơn lịch sử | Giữ phí đã chốt tại thời điểm tạo đơn. | Kiểm tra persistence mapping và test invoice. |
| Cấu hình | Nguồn cấu hình, cách rollout và version. | Tìm cấu hình môi trường và quy trình deploy. |
| Thay đổi ngưỡng | Test dưới, đúng ngưỡng và trên ngưỡng. | Tạo PR nhỏ và review test. |
| Sự cố | Dấu hiệu khi phí preview và invoice không khớp. | Xem dashboard/log đã ẩn dữ liệu nhạy cảm. |

### 11.3. Reverse shadowing

Người nhận được yêu cầu thêm một hạng khách hàng mới trên nhánh thử nghiệm. Họ phải:

1. Tìm nơi khai báo hạng.
2. Tìm nơi sở hữu ngưỡng phí.
3. Xác định dữ liệu cấu hình cần cập nhật.
4. Thêm test cho đúng dưới và đúng ngưỡng.
5. Xác định ảnh hưởng tới preview và invoice.
6. Nêu các gate cần chạy trước merge.
7. Giải thích cách rollback nếu cấu hình mới gây lỗi.

Người phụ trách cũ quan sát và chỉ can thiệp khi có nguy cơ hoặc hiểu sai hợp đồng. Nếu người nhận không thể làm được, nhóm biết chính xác **phần tri thức nào còn thiếu**.

## 12. Bàn giao công việc đang mở và quyết định đang chờ

Người tiếp quản cần hiểu không chỉ hệ thống hiện tại mà cả những cam kết chưa hoàn tất.

Một danh sách bàn giao nên phân loại:

| Trạng thái | Nội dung cần ghi |
| --- | --- |
| **Đang thực hiện** | PR, nhánh, mục tiêu, phần đã xong, phần còn lại, test chưa chạy. |
| **Đang review** | Người review, câu hỏi chưa giải quyết, quyết định đang chờ. |
| **Đang bị chặn** | Phụ thuộc bên ngoài, quyền cần cấp, deadline và cách escalation. |
| **Đã thống nhất nhưng chưa triển khai** | ADR, kế hoạch rollout, điều kiện phát hành. |
| **Nợ kỹ thuật đã ghi nhận** | Tác động, bằng chứng, owner, ưu tiên và trigger xem lại. |
| **Sự cố theo dõi** | Trạng thái khắc phục, dữ liệu cần xác minh, hành động hậu sự cố. |
| **Cam kết với bên khác** | API compatibility, lịch migration, hỗ trợ client hoặc vendor. |

### 12.1. Không bàn giao chỉ bằng danh sách link

Một danh sách 40 issue mà không nêu issue nào quan trọng, issue nào đã lỗi thời và issue nào đang chặn release sẽ tạo thêm công việc cho người nhận.

Nên có một bản tóm tắt ngắn:

- Ba việc cần xử lý trước.
- Các deadline hoặc mốc phụ thuộc.
- Những quyết định cần xin phê duyệt.
- Các giả định chưa xác minh.
- Những vấn đề có thể chờ.
- Người/nhóm có thể hỗ trợ từng việc.

## 13. Quyền truy cập và trách nhiệm vận hành phải được chuyển riêng

Một người mới có thể hiểu hệ thống nhưng chưa có quyền truy cập môi trường, log hoặc dashboard. Điều này làm bàn giao không hoàn tất.

Hãy kiểm tra các nhóm quyền cần thiết:

- Repository và CI/CD.
- Issue tracker và tài liệu kiến trúc.
- Dashboard, logs, traces và alert.
- Môi trường dev/staging phù hợp.
- Quyền triển khai hoặc yêu cầu người có thẩm quyền triển khai.
- Secret manager theo nguyên tắc quyền tối thiểu.
- Database read-only hoặc quyền vận hành được phê duyệt.
- Kênh on-call và escalation.

### 13.1. Nguyên tắc quyền tối thiểu

Không cấp toàn bộ quyền production chỉ để người nhận “đỡ bị chặn”. Quyền cần phù hợp vai trò, được cấp qua quy trình, có audit và được thu hồi khi không còn cần.

Nếu một thao tác yêu cầu quyền đặc biệt, runbook nên nêu **cách xin quyền và ai phê duyệt**, không chứa token hoặc hướng dẫn chia sẻ credential.

### 13.2. Chuyển giao trách nhiệm on-call

Cần xác định:

- Ngày/giờ bắt đầu và kết thúc lịch trực.
- Alert nào thuộc phạm vi service.
- Mức độ sự cố và thời gian phản hồi theo chính sách nhóm.
- Kênh liên hệ và escalation.
- Runbook nào đã được diễn tập.
- Ai là backup khi owner chính không sẵn sàng.

Không nên đưa người mới vào lịch trực chỉ vì đã tham gia một buổi giới thiệu. Họ cần có quyền, hiểu quy trình và biết khi nào phải gọi hỗ trợ.

## 14. Bàn giao khi không có thời gian overlap

Đôi khi người phụ trách nghỉ đột xuất hoặc chuyển việc ngay. Không thể yêu cầu một phiên bàn giao hoàn hảo trong mọi tình huống.

Khi overlap không có, hãy giảm rủi ro theo thứ tự:

1. Xác định service/module đang có tác động lớn nhất.
2. Tìm owner nhóm, reviewer gần đây và người on-call hiện tại.
3. Đọc README, ADR, runbook, test, incident report và lịch sử deploy.
4. Xác minh quyền truy cập và kênh hỗ trợ.
5. Tạm hoãn thay đổi không cần thiết nếu chưa hiểu tác động.
6. Diễn tập các thao tác quan trọng trên môi trường an toàn.
7. Ghi các khoảng trống tri thức và giao người xử lý.
8. Bổ sung người thứ hai hiểu module để giảm phụ thuộc đơn lẻ.

### 14.1. Tìm tri thức từ dấu vết còn lại

Nếu người cũ không thể trả lời, có thể khôi phục bối cảnh từ:

- ADR và PR đã merge.
- Test và commit history.
- Incident/postmortem.
- Log/trace đã được phân quyền.
- Schema và migration.
- Dashboard và alert definition.
- Tài liệu client hoặc vendor.
- Trao đổi review có liên kết tới thay đổi.

Cần phân biệt **điều tài liệu xác nhận** với **giả thuyết người mới suy ra**. Nếu không rõ, hãy ghi rõ câu hỏi và tìm người có thẩm quyền xác nhận trước khi thay đổi rủi ro cao.

## 15. Duy trì tri thức sau khi bàn giao

Bàn giao không phải một cuộc họp kết thúc là xong. Sau khi nhận ownership, người mới sẽ phát hiện các giả định thiếu, link hỏng hoặc quy trình không còn đúng.

Một nhịp duy trì có thể gồm:

- Trong tuần đầu: thực hiện một thay đổi nhỏ, chạy test và walkthrough vận hành.
- Sau một chu kỳ phát hành: xem lại runbook, alert và các điểm chưa rõ.
- Sau incident đầu tiên: cập nhật tri thức từ điều vừa học.
- Khi có thay đổi API/schema: cập nhật contract, migration note và hướng dẫn client.
- Khi có quyết định kiến trúc mới: tạo hoặc cập nhật ADR.
- Theo định kỳ phù hợp: kiểm tra owner, quyền truy cập và các tài liệu trọng yếu.

Không cần lên lịch họp định kỳ cho mọi module nếu không có giá trị. Có thể dùng **sự kiện thay đổi** làm trigger cập nhật tài liệu.

### 15.1. Cập nhật tri thức trong cùng PR

Khi thay đổi một hợp đồng, PR nên xem xét:

- Test có phản ánh hành vi mới?
- JavaDoc/comment có còn đúng?
- README hoặc ví dụ API có thay đổi?
- Runbook có thao tác mới?
- ADR có cần ghi quyết định?
- Dashboard/alert có ngưỡng mới?
- Người trực có cần biết thay đổi vận hành?

Không phải mỗi PR cần sửa mọi loại tài liệu. Nhưng người review nên biết **nguồn tri thức nào chịu ảnh hưởng** và ghi lý do nếu không cần cập nhật.

## 16. Đo khả năng duy trì tri thức mà không xếp hạng cá nhân

Có thể dùng một số tín hiệu ở cấp nhóm hoặc thành phần:

| Tín hiệu | Câu hỏi hỗ trợ | Giới hạn |
| --- | --- | --- |
| Số người có thể thực hiện nhiệm vụ quan trọng | Tri thức có tập trung ở một người không? | Số người biết tên module không đồng nghĩa có thể vận hành. |
| Tỷ lệ runbook trọng yếu được xác minh | Hướng dẫn có còn phù hợp? | Có tài liệu không chứng minh người đọc làm được. |
| Thời gian để người mới thực hiện thay đổi nhỏ | Khả năng tiếp quản có cải thiện không? | Phụ thuộc độ khó và kinh nghiệm cá nhân. |
| Số câu hỏi/chặn do thiếu bối cảnh | Khoảng trống tri thức nằm ở đâu? | Hỏi nhiều có thể là dấu hiệu người mới cẩn thận. |
| Số thao tác vận hành được diễn tập | Quy trình khẩn cấp có thể thực hiện không? | Diễn tập không bao phủ mọi tình huống thật. |
| Tỷ lệ issue bàn giao có owner/trạng thái rõ | Công việc còn mở có được quản lý? | Trạng thái có thể lỗi thời nếu không cập nhật. |

Không dùng các chỉ số này để xếp hạng người cũ hoặc người mới. Mục tiêu là **tìm điểm phụ thuộc của hệ thống vào một cá nhân và cải thiện khả năng phục hồi của nhóm**.

### 16.1. Tránh tối ưu một con số

Tăng số người có quyền truy cập không tự làm tăng tri thức. Viết thêm 50 trang tài liệu không chứng minh người mới có thể xử lý sự cố. Giảm thời gian onboarding có thể do phạm vi bàn giao bị cắt bớt.

Hãy kết hợp số liệu với bài tập thực tế, review của người nhận và kết quả công việc sau chuyển giao.

## 17. Những lỗi thường gặp khi bàn giao

### 17.1. Chỉ có một buổi trình bày

Người mới nghe hết kiến trúc nhưng chưa tự chạy test, sửa code hoặc xem log. Khi gặp nhiệm vụ thật, họ không biết bắt đầu ở đâu.

**Cải thiện:** thêm reverse shadowing và nhiệm vụ thực hành có phạm vi an toàn.

### 17.2. Tài liệu quá dài nhưng không có đường vào

Thông tin nằm rải rác trong nhiều trang, không có README hoặc index chỉ ra nguồn nào là hiện hành.

**Cải thiện:** tạo trang bắt đầu ngắn, link tới nguồn có thẩm quyền và ghi owner.

### 17.3. Chuyển giao thông tin nhưng không chuyển trách nhiệm

Người cũ giải thích hệ thống, nhưng không ai xác nhận owner mới, lịch trực hoặc quyền phê duyệt.

**Cải thiện:** ghi ngày hiệu lực, vai trò, backup và escalation.

### 17.4. Chuyển quyền quá rộng để tránh chậm trễ

Người nhận được cấp quyền admin hoặc credential dùng chung mà không cần thiết.

**Cải thiện:** cấp theo vai trò, audit, thời hạn và quy trình secret manager.

### 17.5. Giữ mọi quyết định trong chat riêng

Một người nhớ lý do nhưng không có ADR hoặc link trong issue. Khi họ rời nhóm, không ai tìm được bối cảnh.

**Cải thiện:** ghi lại quyết định có tác động dài hạn vào nguồn tri thức của dự án.

### 17.6. Không phân biệt dữ liệu hiện tại với dữ liệu lịch sử

Người mới dùng chính sách hiện hành để tính lại hóa đơn cũ hoặc diễn giải lại trạng thái cũ.

**Cải thiện:** ghi rõ snapshot, version và thời điểm hiệu lực trong hợp đồng dữ liệu.

### 17.7. Coi việc gửi tài liệu là tiêu chí hoàn thành

Người nhận chưa mở được dashboard, chưa chạy được test hoặc chưa biết rollback nhưng ticket bàn giao đã đóng.

**Cải thiện:** xác nhận bằng nhiệm vụ người nhận tự thực hiện và bằng chứng kết quả.

## 18. Mẫu kế hoạch bàn giao có thể dùng trong nhóm

~~~markdown
# Kế hoạch bàn giao: <thành phần / phạm vi>

## 1. Thông tin chuyển giao
- Owner hiện tại:
- Owner tiếp nhận:
- Nhóm chịu trách nhiệm:
- Ngày hiệu lực:
- Thời gian overlap:
- Backup / escalation:

## 2. Phạm vi
- Service / module:
- API / event / database:
- Môi trường:
- Phụ thuộc bên ngoài:
- Phần ngoài phạm vi:

## 3. Tri thức cần tiếp quản
- Hành vi và bất biến:
- Kiến trúc và ADR:
- Code entry point:
- Test và lệnh chạy:
- Cấu hình và dữ liệu:
- Runbook / dashboard / alert:
- Bảo mật và quyền truy cập:
- Quy trình review / release:

## 4. Công việc đang mở
- PR / issue:
- Incident / follow-up:
- Quyết định đang chờ:
- Deadline / dependency:
- Rủi ro đã biết:
- Nợ kỹ thuật:

## 5. Hoạt động chuyển giao
- [ ] Người nhận đã đọc nguồn tri thức chính.
- [ ] Walkthrough luồng nghiệp vụ đã hoàn tất.
- [ ] Người nhận tự chạy build và test.
- [ ] Người nhận thực hiện một thay đổi mẫu.
- [ ] Người nhận tra cứu dashboard/log.
- [ ] Runbook quan trọng đã được diễn tập.
- [ ] Quyền truy cập đã được xác minh.
- [ ] Owner, backup và escalation đã rõ.

## 6. Khoảng trống còn lại
- Nội dung chưa xác minh:
- Rủi ro tạm thời:
- Người xử lý:
- Thời hạn / trigger xem lại:

## 7. Xác nhận
- Người bàn giao:
- Người tiếp nhận:
- Đại diện nhóm:
- Ngày xác nhận:
- Điều kiện còn mở:
~~~

Mẫu này là điểm bắt đầu. Với một thư viện nhỏ, có thể chỉ cần README, test và người review backup. Với service thanh toán hoặc dữ liệu quan trọng, cần thêm runbook, migration, quyền truy cập và diễn tập khôi phục.

## 19. Kịch bản thực hành: tiếp quản một service trong năm ngày

Giả sử một kỹ sư mới nhận ownership của service báo giá. Đây là kế hoạch minh họa có thể điều chỉnh theo quy mô và mức rủi ro.

| Ngày | Hoạt động | Bằng chứng cần có |
| --- | --- | --- |
| **Ngày 1** | Đọc README, kiến trúc, ADR, API contract và danh sách issue. | Vẽ lại luồng chính, liệt kê câu hỏi chưa rõ. |
| **Ngày 2** | Pair walkthrough một thay đổi nhỏ và chạy test. | Tự chạy được build/unit test, hiểu test quan trọng. |
| **Ngày 3** | Reverse shadow: người mới sửa một chính sách trong branch thử nghiệm. | PR nhỏ có test, giải thích được phạm vi ảnh hưởng. |
| **Ngày 4** | Diễn tập tra log, dashboard và một runbook không phá hủy. | Tìm đúng tín hiệu và nêu bước escalation. |
| **Ngày 5** | Review công việc mở, quyền truy cập, lịch release và trách nhiệm. | Kế hoạch 30 ngày, owner/backup và khoảng trống được ghi rõ. |

Không nên coi năm ngày là chuẩn bắt buộc. Một module ít rủi ro có thể tiếp quản nhanh hơn; một hệ thống có migration phức tạp, nhiều client hoặc yêu cầu bảo mật có thể cần nhiều tuần.

## 20. Khi nào có thể xem bàn giao là hoàn tất?

Không có một checklist chung đảm bảo mọi người đã biết mọi thứ. Tuy nhiên, có thể xác nhận bàn giao khi:

1. **Ownership rõ:** nhóm và vai trò chịu trách nhiệm đã được xác nhận.
2. **Nguồn tri thức tìm được:** người nhận biết nơi xem hợp đồng, test, quyết định và runbook.
3. **Nhiệm vụ cơ bản tự thực hiện được:** build, test, thay đổi nhỏ và review theo quy trình.
4. **Vận hành có hỗ trợ:** người nhận biết cách theo dõi, escalation và khôi phục trong phạm vi đã diễn tập.
5. **Quyền truy cập phù hợp:** không thiếu quyền cần thiết và không có quyền thừa.
6. **Công việc còn mở có chủ sở hữu:** issue, incident, PR và quyết định chờ không bị bỏ quên.
7. **Khoảng trống được ghi nhận:** điều chưa biết có người xử lý và thời hạn hoặc trigger xem lại.
8. **Tri thức có người duy trì:** sau ngày chuyển giao, tài liệu và test tiếp tục được cập nhật.

Bàn giao hoàn tất không có nghĩa người nhận đã thay thế hoàn toàn kinh nghiệm của người cũ. Nó có nghĩa **người nhận có thể chịu trách nhiệm trong phạm vi đã xác định, biết giới hạn của mình và biết cách tìm hỗ trợ**.

## 21. Bài tập tự đánh giá

### Tình huống A: chỉ một người biết deploy

Một service có README và unit test đầy đủ, nhưng chỉ một kỹ sư biết cấu hình secret, chạy migration và rollback production.

**Câu hỏi:** tài liệu hiện tại đã đủ để bàn giao chưa?

**Gợi ý:** chưa. Cần runbook deploy/migration/rollback, quyền được cấp qua quy trình, diễn tập trên môi trường an toàn và owner/backup on-call. Unit test không chứng minh quy trình vận hành.

### Tình huống B: người cũ giải thích rất nhiều nhưng không có ADR

Người phụ trách cũ nhớ vì sao service giữ snapshot giá tại thời điểm đặt hàng, nhưng code không có comment và tài liệu không nói lý do.

**Câu hỏi:** nên chuyển tri thức này thành gì?

**Gợi ý:** ghi bất biến trong tài liệu nghiệp vụ hoặc ADR, liên kết tới test chứng minh hóa đơn lịch sử giữ giá đã chốt. Không cần ghi lại toàn bộ cuộc trò chuyện, chỉ giữ quyết định và hệ quả quan trọng.

### Tình huống C: người mới có quyền admin

Để tránh phải chờ cấp quyền, người tiếp quản được chia sẻ tài khoản admin production dùng chung.

**Câu hỏi:** đây có phải cách bàn giao hợp lý?

**Gợi ý:** không. Cần tài khoản định danh, quyền tối thiểu, secret manager, audit và phê duyệt theo vai trò. Bàn giao quyền truy cập phải có thể kiểm soát và thu hồi.

### Tình huống D: module có hai người biết nhưng cả hai cùng rời nhóm

Bảng ownership ghi hai tên, nhưng không ai khác biết quy trình khôi phục dữ liệu.

**Câu hỏi:** chỉ số “hai người sở hữu” có đủ chứng minh rủi ro thấp không?

**Gợi ý:** không. Cần kiểm tra khả năng thực hiện nhiệm vụ và backup thực tế. Ownership trên bảng không đồng nghĩa tri thức đã phân tán.

### Tình huống E: người mới không trả lời được mọi câu hỏi

Sau một tuần, người nhận có thể sửa logic và chạy test nhưng chưa tự xử lý được incident hiếm.

**Câu hỏi:** có phải bàn giao thất bại?

**Gợi ý:** không nhất thiết. Xác định phạm vi trực và mức rủi ro, bảo đảm có người hỗ trợ, runbook và đường escalation. Ghi phần chưa thực hành để lên kế hoạch diễn tập tiếp theo.

### Tình huống F: tài liệu và code mâu thuẫn

ADR cũ nói dùng ngưỡng phí trước chiết khấu, còn code và test hiện tại áp dụng sau chiết khấu.

**Câu hỏi:** người mới nên làm gì trước khi sửa?

**Gợi ý:** không tự chọn một nguồn theo cảm giác. Kiểm tra yêu cầu hiện hành, lịch sử thay đổi và owner nghiệp vụ; ghi nhận mâu thuẫn, xác nhận hợp đồng rồi cập nhật tài liệu/test/code đồng bộ.

## 22. Checklist duy trì tri thức khi thay đổi người phụ trách

- [ ] Phạm vi service/module và mức rủi ro đã được xác định.
- [ ] Owner mới, nhóm chịu trách nhiệm, backup và quyền quyết định đã rõ.
- [ ] Người nhận biết nguồn sự thật của hành vi, cấu hình và dữ liệu.
- [ ] README có đường dẫn tới ADR, test, API contract và runbook.
- [ ] Các quyết định dài hạn có lý do, đánh đổi và điều kiện xem lại.
- [ ] Test quan trọng được giải thích và có thể chạy lại.
- [ ] Người nhận đã thực hiện ít nhất một nhiệm vụ đại diện.
- [ ] Runbook deploy, rollback và incident đã được xem xét/diễn tập theo rủi ro.
- [ ] Dashboard, alert, log và quyền truy cập đã được xác minh.
- [ ] Không có secret hoặc dữ liệu nhạy cảm bị sao chép vào tài liệu bàn giao.
- [ ] PR, issue, incident, deadline và quyết định chờ có owner mới.
- [ ] Các phụ thuộc bên ngoài và quy trình escalation đã rõ.
- [ ] Giả định chưa xác minh được ghi riêng với điều đã được chứng minh.
- [ ] Người nhận biết giới hạn quyền hạn và khi nào cần hỗ trợ.
- [ ] Tài liệu có owner và được cập nhật khi code/hợp đồng thay đổi.
- [ ] Việc bàn giao được xác nhận bằng khả năng thực hiện, không chỉ bằng danh sách tài liệu đã gửi.

## 23. Kết luận

**Duy trì tri thức khi thay đổi người phụ trách** là điều kiện để hệ thống tiếp tục được bảo trì an toàn qua thay đổi nhân sự và tổ chức. Code, test, ADR, README, runbook và lịch sử thay đổi đều có thể giữ tri thức, nhưng mỗi nguồn chỉ có ích khi người nhận biết tìm ở đâu, hiểu giới hạn và kiểm chứng được nội dung.

Một cuộc bàn giao tốt kết hợp **tài liệu dễ tìm, giải thích bối cảnh, thực hành cùng nhau, reverse shadowing, quyền truy cập phù hợp và xác nhận ownership**. Nó cũng ghi rõ những điều chưa biết, việc còn mở và người hỗ trợ khi có sự cố.

Trong **CODE_QUALITY_FUNDAMENTALS**, chất lượng mã không chỉ được quyết định bởi người viết hiện tại. Một hệ thống **đáng tin cậy, dễ hiểu và dễ thay đổi** phải cho phép người tiếp theo tìm ra quyết định quan trọng, kiểm tra hành vi, thực hiện thay đổi và vận hành có trách nhiệm mà không phụ thuộc hoàn toàn vào trí nhớ của một cá nhân.

