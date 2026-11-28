# Exception và compensating control trong đặc tả yêu cầu bảo mật

## 1. Vấn đề cần giải quyết

Một nhóm phát triển cần duy trì hệ thống cũ trong 45 ngày trước khi thay thế. Hệ thống chưa hỗ trợ cơ chế xác thực mà kiến trúc chuẩn yêu cầu. Ngừng ngay hệ thống có thể làm gián đoạn nghiệp vụ, nhưng tiếp tục vận hành bằng một lời hứa “sẽ sửa sau” khiến tổ chức không biết đang chấp nhận rủi ro nào.

Exception và compensating control giúp xử lý tình huống này có căn cứ: xác định điều gì chưa đáp ứng, giới hạn phạm vi, thiết kế phương án bảo vệ thay thế, kiểm chứng hiệu lực và giao quyết định cho đúng người có thẩm quyền.

Trong chương Risk management và compliance của module Security Requirements, trọng tâm là chuyển ngoại lệ thành **một hồ sơ có yêu cầu, bằng chứng, trách nhiệm và điều kiện kết thúc**. Một ticket được duyệt hoặc một công cụ được cài thêm chưa đủ chứng minh mục tiêu an toàn thông tin đã đạt.

Sau bài học, người học có thể:

- Phân biệt ngoại lệ, chấp nhận rủi ro, kiểm soát bù đắp và yêu cầu không áp dụng.
- Viết hồ sơ ngoại lệ có phạm vi, thời hạn và tiêu chí kiểm chứng.
- Đánh giá phương án thay thế theo tình huống đe dọa và mức bảo vệ cần duy trì.
- Liên kết quyết định với kiến trúc, kiểm thử, giám sát và kế hoạch khắc phục.
- Theo dõi hết hạn, gia hạn, thu hồi và đóng ngoại lệ bằng bằng chứng.

Các mã định danh, ngưỡng và thời hạn trong bài là ví dụ cho một tổ chức giả định. Quy trình thực tế phải theo chính sách, hợp đồng và nghĩa vụ áp dụng; không coi các ví dụ này là điều kiện đủ để được chứng nhận tuân thủ.

## 2. Phân biệt các khái niệm

### 2.1. Exception: ngoại lệ có kiểm soát

Trong bài này, exception là quyết định cho phép một phạm vi xác định lệch khỏi yêu cầu hoặc cách triển khai chuẩn, trong những điều kiện được ghi rõ. Mô hình quản trị minh họa yêu cầu ngoại lệ có thời hạn và được đánh giá lại khi điều kiện thay đổi.

Ngoại lệ phải trả lời được:

1. Yêu cầu hoặc kiểm soát nào chưa được đáp ứng?
2. Tài sản, người dùng, dữ liệu và đường truy cập nào thuộc phạm vi?
3. Vì sao cách chuẩn chưa thể triển khai?
4. Phương án nào giảm rủi ro trong thời gian ngoại lệ?
5. Rủi ro còn lại là gì và ai được phép chấp nhận?
6. Khi nào ngoại lệ hết hiệu lực và điều gì xảy ra lúc đó?

Một hạn chế kỹ thuật đang tồn tại là dữ kiện đầu vào. Nó chỉ trở thành ngoại lệ đã được phê duyệt sau khi hoàn thành quy trình có thẩm quyền.

### 2.2. Compensating control: kiểm soát bù đắp

Theo thuật ngữ NIST, compensating security control là biện pháp quản lý, vận hành hoặc kỹ thuật được dùng thay cho kiểm soát được khuyến nghị trong baseline, nhằm cung cấp mức bảo vệ tương đương hoặc có thể so sánh. Khi áp dụng khái niệm này cần giữ đúng ngữ cảnh của baseline và yêu cầu đang xét. [Nguồn: NIST Glossary — Compensating Security Control](https://csrc.nist.gov/glossary/term/compensating_security_control).

Từ khóa quan trọng là **bù cho khả năng bảo vệ bị thiếu**. Cần chỉ ra phương án tác động lên đường tấn công nào, giảm hậu quả gì và kiểm chứng bằng cách nào. “Bật thêm logging” có thể tăng khả năng điều tra, nhưng chưa mặc nhiên thay thế được một cơ chế ngăn truy cập trái phép.

Kiểm soát bù đắp có thể là một tổ hợp biện pháp. Nó không nhất thiết chỉ có hiệu lực ngắn hạn: một phương án thay thế lâu dài có thể được lựa chọn qua quy trình điều chỉnh baseline phù hợp. Tuy nhiên, khi nó gắn với ngoại lệ tạm thời, điều kiện hiệu lực phải được quản lý cùng hồ sơ ngoại lệ.

### 2.3. Các khái niệm liên quan

| Khái niệm | Câu hỏi nó trả lời | Điều không được suy ra tự động |
| --- | --- | --- |
| Exception | Có được phép lệch chuẩn trong phạm vi và điều kiện này không? | Mục tiêu bảo vệ đã đạt |
| Risk acceptance | Ai chấp nhận phần rủi ro còn lại, trên căn cứ nào? | Yêu cầu gốc đã được thực hiện |
| Compensating control | Cơ chế nào thay thế khả năng bảo vệ bị thiếu? | Chỉ cần có tên công cụ là đủ |
| Alternative implementation | Cách triển khai khác có đáp ứng chính yêu cầu không? | Luôn cần ngoại lệ nếu yêu cầu chỉ đặc tả kết quả |
| Not applicable | Có căn cứ nào cho thấy yêu cầu không áp dụng? | Triển khai khó nghĩa là không áp dụng |
| Remediation plan | Làm gì để xử lý khoảng trống và khi nào xong? | Kế hoạch tương lai là bằng chứng bảo vệ hiện tại |

Ví dụ, nếu yêu cầu chỉ nói “mọi truy cập quản trị phải được xác thực MFA”, một cổng truy cập đáp ứng đủ điều kiện có thể là cách triển khai hợp lệ. Nếu yêu cầu bắt buộc “ứng dụng tự tích hợp trực tiếp với IdP”, đưa MFA ra cổng không đáp ứng nguyên văn cách triển khai đó. Cần ghi nhận sai lệch hoặc điều chỉnh yêu cầu bằng quy trình có thẩm quyền.

## 3. Bắt đầu từ yêu cầu và mô hình đe dọa

Trước khi đề xuất biện pháp bù đắp, hãy tách ba tầng:

- **Mục tiêu:** ngăn người chỉ có mật khẩu bị lộ thực hiện thao tác quản trị.
- **Yêu cầu bảo mật:** mọi truy cập quản trị tương tác thuộc phạm vi phải đáp ứng chính sách MFA đã phê duyệt và truy vết được tới danh tính cá nhân.
- **Cách triển khai chuẩn:** ứng dụng tích hợp trực tiếp với nhà cung cấp danh tính của tổ chức.

Sự tách biệt giúp biết một đề xuất chỉ thay đổi cách thực hiện hay làm giảm cả mức bảo vệ. Nếu yêu cầu đã quy định phương thức xác thực, nơi thực thi hoặc khả năng chống một kiểu tấn công cụ thể, đánh giá phải giữ đủ các điều kiện đó.

Mô hình đe dọa cần nêu rõ tác nhân, năng lực, tài sản, đường truy cập và hậu quả. Với ví dụ trên, ít nhất phải xét mật khẩu bị lộ, truy cập vòng qua cổng, chiếm phiên, tài khoản backend có quyền quá mức và người quản trị làm mất khả năng quy trách nhiệm.

Một đề xuất “đặt sau VPN” chỉ xử lý được một phần điều kiện tiếp cận. Nó chưa tự chứng minh người dùng có đúng quyền, phiên đã được thu hồi hay tài khoản cá nhân được bảo toàn trên ứng dụng đích.

## 4. Khi nào có thể xem xét ngoại lệ?

Một hồ sơ đáng xem xét có lý do cụ thể: ràng buộc kỹ thuật đã được xác nhận, giới hạn của sản phẩm đang sử dụng, xung đột với tính sẵn sàng của nghiệp vụ hoặc thời gian chuyển đổi cần thiết. Lý do cần có bằng chứng và các phương án đã cân nhắc.

Deadline hoặc chi phí có thể giải thích vì sao nhóm đề nghị ngoại lệ, nhưng không chứng minh phương án thay thế cung cấp đủ bảo vệ. Cần so sánh cả lựa chọn trì hoãn phát hành, thu hẹp chức năng, giảm phạm vi dữ liệu hoặc ngừng đường truy cập có rủi ro.

NIST SP 800-53B yêu cầu lập luận vì sao kiểm soát baseline không thể triển khai, cách kiểm soát bù đắp đáp ứng yêu cầu và đánh giá rủi ro liên quan. Hướng dẫn cũng nêu có thể cần nhiều kiểm soát để tạo mức bảo vệ tương đương hoặc có thể so sánh. Đây là cơ sở tham khảo cho việc thiết kế hồ sơ, không phải giấy miễn trừ tuân thủ chung. [Nguồn: NIST SP 800-53B, phần Selecting Compensating Controls](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-53B.pdf).

Trước khi cho phép vận hành theo ngoại lệ, cần xác nhận:

1. Yêu cầu có được phép điều chỉnh theo cơ chế đang áp dụng không?
2. Người phê duyệt có thẩm quyền trên đúng phạm vi rủi ro không?
3. Biện pháp bù đắp đã được triển khai và kiểm chứng hay mới là kế hoạch?
4. Phần rủi ro chưa xử lý đã được trình bày đầy đủ chưa?
5. Có người vận hành, giám sát và thực hiện kế hoạch kết thúc không?

Quyết định nội bộ không tự miễn trừ nghĩa vụ bắt buộc từ luật, hợp đồng hoặc khuôn khổ đánh giá bên ngoài. Khi một nghĩa vụ quy định điều kiện chấp nhận biện pháp thay thế, phải làm theo cơ chế đó và có người phụ trách phù hợp xác nhận căn cứ.

## 5. Đánh giá kiểm soát bù đắp bằng lập luận có thể kiểm chứng

### 5.1. So sánh theo khả năng bảo vệ

Một đánh giá hữu ích so sánh kiểm soát gốc và phương án đề xuất trên cùng tình huống đe dọa:

| Chiều đánh giá | Câu hỏi |
| --- | --- |
| Mục tiêu | Phương án bảo vệ cùng tài sản và cùng thuộc tính an toàn không? |
| Phạm vi | Có bao phủ mọi endpoint, tài khoản và luồng nền đang thuộc ngoại lệ? |
| Thời điểm | Phương án ngăn hành động trước khi xảy ra hay chỉ phát hiện sau đó? |
| Độ mạnh | Có đáp ứng các thuộc tính xác thực, quyền hạn và chống sửa đổi cần thiết? |
| Khả năng đi vòng | Có đường mạng, API, phiên cũ hoặc tài khoản khác bỏ qua biện pháp? |
| Phụ thuộc | Nếu IdP, mạng, log hoặc nhân sự trực không hoạt động thì điều gì xảy ra? |
| Độc lập | Một lỗi cấu hình hoặc cùng một quyền quản trị có thể vô hiệu hóa mọi lớp không? |
| Vận hành | Ai duy trì, kiểm tra thay đổi và phản ứng trong thời gian cam kết? |
| Bằng chứng | Có phép kiểm tra tái lập và tiêu chí chấp nhận cụ thể không? |
| Rủi ro mới | Phương án có tạo điểm lỗi tập trung, lộ dữ liệu hoặc đặc quyền mới không? |

Không cần biến mọi tiêu chí thành điểm số. Với điều kiện bắt buộc như “không được truy cập backend trực tiếp”, chỉ một đường đi vòng chưa xử lý có thể đủ để bác bỏ kết luận bảo vệ tương đương.

### 5.2. Phòng ngừa, phát hiện và phục hồi có vai trò khác nhau

Giả sử một thao tác có thể xuất toàn bộ dữ liệu trong 20 giây, còn quy trình xem log chỉ chạy mỗi ngày. Khả năng phát hiện sau một ngày khó bù cho việc thiếu kiểm soát ngăn xuất dữ liệu.

Biện pháp phát hiện có thể góp phần vào phương án nếu thời gian phát hiện và phản ứng phù hợp với diễn biến tấn công, đồng thời có cơ chế giới hạn thiệt hại. Phải lập luận cho toàn bộ chuỗi phát hiện, xác nhận, phản ứng và khôi phục; số lượng cảnh báo không thể hiện trực tiếp mức bảo vệ.

Tương tự, sao lưu có thể hỗ trợ khôi phục tính sẵn sàng hoặc toàn vẹn. Nó không lấy lại được tính bí mật sau khi dữ liệu đã bị sao chép ra ngoài.

### 5.3. Mẫu lập luận cho một biện pháp

~~~text
Khoảng trống:
  Ứng dụng cũ chưa tích hợp trực tiếp với IdP theo chuẩn kiến trúc.

Tình huống đe dọa:
  Người có mật khẩu ứng dụng truy cập chức năng quản trị qua đường bỏ qua MFA.

Biện pháp đề xuất:
  Buộc truy cập qua cổng thực thi MFA; chặn đường trực tiếp;
  giữ danh tính cá nhân; giới hạn và thu hồi phiên theo chính sách.

Bằng chứng cần có:
  Kiểm thử đi vòng từ các vùng mạng liên quan;
  kiểm thử xác thực, quyền, thu hồi và truy vết đầu cuối.

Giới hạn kết luận:
  Chỉ áp dụng cho ứng dụng, endpoint, tài khoản và cấu hình đã xác định.
  Chưa được coi là đủ cho các đường khác hoặc thuộc tính chưa kiểm chứng.

Rủi ro còn lại:
  Phụ thuộc vào cổng truy cập, chính sách mạng và khả năng bảo toàn danh tính.
~~~

Một chữ ký phê duyệt không thay cho các phép kiểm tra này. Nếu bằng chứng không đủ để chứng minh mức bảo vệ tương đương, hồ sơ phải ghi đúng là biện pháp giảm thiểu một phần cùng phần rủi ro chưa được bù.

## 6. Đặc tả hồ sơ ngoại lệ

Hồ sơ nên đủ rõ để một người không tham gia cuộc trao đổi ban đầu vẫn hiểu và đánh giá lại được.

| Trường | Nội dung cần ghi |
| --- | --- |
| Mã và phiên bản | Định danh ngoại lệ, lần sửa, lịch sử quyết định |
| Yêu cầu gốc | Mã, phiên bản, nội dung và tiêu chí chưa đáp ứng |
| Nguồn yêu cầu | Chính sách nội bộ, mục tiêu nghiệp vụ, hợp đồng hoặc nghĩa vụ liên quan |
| Phạm vi | Tài sản, môi trường, endpoint, người dùng, dữ liệu; phần ngoài phạm vi |
| Lý do | Ràng buộc có bằng chứng và phương án đã cân nhắc |
| Phân tích đe dọa | Đường tấn công, tác nhân, hậu quả và giả định |
| Biện pháp bù đắp | Cấu hình, quy trình, thành phần và người sở hữu từng biện pháp |
| Lập luận bảo vệ | Khả năng được thay thế, điều kiện hiệu lực và khoảng trống còn lại |
| Kiểm chứng | Ca kiểm thử, kết quả, thời gian, phiên bản cấu hình, người đánh giá |
| Rủi ro còn lại | Mức phơi nhiễm, hậu quả, độ không chắc chắn và căn cứ chấp nhận |
| Điều kiện hiệu lực | Bằng chứng bắt buộc trước kích hoạt, giới hạn vận hành và trigger thu hồi |
| Thời hạn | Ngày bắt đầu, ngày hết hạn, lịch rà soát và điều kiện gia hạn |
| Kế hoạch kết thúc | Người thực hiện, mốc chuyển đổi, tiêu chí đóng và phương án khi chậm |
| Phê duyệt | Chủ rủi ro, người có thẩm quyền và xác nhận liên quan |
| Truy vết | Liên kết yêu cầu, kiến trúc, ticket, bằng chứng và quyết định |

Không chỉ ghi “áp dụng cho hệ thống legacy”. Cần có danh sách hoặc tham chiếu tới danh sách được quản lý phiên bản. Thêm một máy chủ, tổ chức sử dụng hoặc chức năng xuất dữ liệu có thể làm thay đổi rủi ro và cần xem xét lại trước khi mở rộng.

### Tách ba trạng thái

Nên quản lý riêng:

- **Trạng thái yêu cầu gốc:** đạt, chưa đạt hoặc chưa đủ bằng chứng.
- **Trạng thái ngoại lệ:** đang đề nghị, đã phê duyệt, đang hiệu lực, hết hạn hoặc bị thu hồi.
- **Trạng thái kiểm soát bù đắp:** chưa triển khai, đã kiểm chứng, suy giảm hoặc chưa đủ bằng chứng.

Nhờ vậy, “ngoại lệ đang hiệu lực” không bị hiểu thành “yêu cầu gốc đã thực hiện đầy đủ”. Một phương án được duyệt có điều kiện cũng chưa được kích hoạt nếu kiểm thử bắt buộc trước vận hành chưa đạt.

## 7. Tình huống: ứng dụng cũ chưa tích hợp xác thực tập trung

### 7.1. Bối cảnh và khoảng trống

Một tổ chức dùng ứng dụng quản trị kho cũ. Ứng dụng có tài khoản cá nhân và ghi nhận người thực hiện, nhưng chưa tích hợp được với nhà cung cấp danh tính tập trung. Nhóm dự kiến thay thế ứng dụng sau 45 ngày.

Các yêu cầu liên quan:

| Mã | Nội dung giả định |
| --- | --- |
| SEC-AUTH-01 | Phiên quản trị tương tác phải qua MFA theo chính sách của tổ chức |
| SEC-AUTHZ-02 | Người dùng chỉ thực hiện hành động trong quyền đã được cấp |
| SEC-AUDIT-03 | Thao tác quản trị phải truy vết được tới danh tính cá nhân |
| SEC-ARCH-04 | Ứng dụng quản trị tích hợp trực tiếp với IdP được phê duyệt |

Khoảng trống đã biết là SEC-ARCH-04 chưa được thực hiện. Hiện trạng cũng chưa có bằng chứng đủ để kết luận SEC-AUTH-01 được đáp ứng. Hồ sơ không được gộp hai vấn đề thành câu chung “ứng dụng có ngoại lệ bảo mật”.

Giả định cơ chế quản trị nội bộ cho phép xem xét ngoại lệ đối với SEC-ARCH-04; việc thay cách tích hợp không được phép làm mất mục tiêu MFA, phân quyền và truy vết cá nhân.

### 7.2. Phương án đề xuất

- Đặt đường truy cập quản trị sau một cổng có khả năng thực thi chính sách MFA đã phê duyệt.
- Chặn truy cập trực tiếp tới ứng dụng từ mọi vùng không được phép; rà soát cả đường quản trị, API và các cổng phụ thuộc có liên quan.
- Duy trì tài khoản cá nhân trên ứng dụng, ánh xạ có kiểm soát với người dùng qua cổng và giữ giới hạn quyền.
- Ràng buộc vòng đời phiên và thu hồi truy cập theo yêu cầu; không để cơ chế đăng nhập cũ tạo đường sử dụng ngoài phạm vi được bảo vệ.
- Thu thập bằng chứng đầu cuối, giám sát thay đổi cấu hình và quy định phản ứng khi kiểm soát suy giảm.
- Giữ kế hoạch thay thế ứng dụng, chủ sở hữu và tiêu chí kết thúc ngoại lệ.

~~~mermaid
flowchart LR
    U["Người quản trị"] --> G["Cổng truy cập có MFA"]
    I["IdP và chính sách"] --> G
    G --> N["Đường kết nối được kiểm soát"]
    N --> L["Ứng dụng cũ với tài khoản cá nhân"]
    X["Đường truy cập trực tiếp"] --> B["Bị chặn theo phạm vi đã xác định"]
    G --> E["Bằng chứng phiên và danh tính"]
    L --> E
~~~

Sơ đồ thể hiện ý định thiết kế. Bằng chứng cấu hình và kiểm thử mới xác nhận đường thực tế có đúng như vậy hay không.

Nếu cổng chỉ xác thực người A nhưng cho phép dùng một tài khoản quản trị chung ở ứng dụng, mục tiêu quy trách nhiệm cá nhân và giới hạn quyền có thể bị suy giảm. Chưa được coi đây là bù đắp đầy đủ chỉ vì bước MFA đã xuất hiện.

### 7.3. Tiêu chí kiểm chứng trước khi kích hoạt

Các tiêu chí dưới đây là hợp đồng kiểm chứng minh họa, cần chi tiết hóa theo kiến trúc thật.

| Kiểm thử | Điều kiện đạt |
| --- | --- |
| Truy cập hợp lệ | Người có đúng quyền và phiên đáp ứng MFA thực hiện được hành động được cấp |
| Thiếu điều kiện MFA | Không tạo được phiên quản trị sử dụng được trên ứng dụng |
| Truy cập trực tiếp | Các đường từ những vùng mạng liên quan không đi vòng cổng được |
| Endpoint hoặc cổng phụ | Không tồn tại đường quản trị thuộc phạm vi mà chính sách chưa bao phủ |
| Quyền thấp | Tài khoản ít quyền không sử dụng được chức năng quản trị cao hơn |
| Ánh xạ danh tính | Hành động trên ứng dụng gắn đúng người qua cổng; không tráo hoặc dùng chung danh tính ngoài chính sách |
| Thu hồi | Sau sự kiện thu hồi, truy cập qua cổng và phiên ứng dụng thuộc phạm vi bị vô hiệu hóa trong thời hạn yêu cầu |
| Sự cố phụ thuộc | Lỗi IdP hoặc cổng không mở ra chế độ truy cập bỏ qua chính sách |
| Bằng chứng | Sự kiện tổng hợp có thể đối chiếu giữa phiên cổng và thao tác ứng dụng |
| Khôi phục dịch vụ | Có cách phục hồi đường quản trị mà vẫn giữ điều kiện xác thực, quyền và ghi nhận bắt buộc |

Trong ví dụ, giả sử thời hạn thu hồi đã được tổ chức xác định là tối đa 5 phút. Phép thử phải nêu rõ mốc bắt đầu, loại phiên, thời gian quan sát và trạng thái ứng dụng sau thu hồi. Việc tài khoản đã bị khóa ở IdP chưa đủ nếu phiên ứng dụng cũ còn dùng được.

Nếu có đường truy cập khẩn cấp, cần đặc tả và đánh giá riêng: ai được sử dụng, lúc nào, điều kiện xác thực, giới hạn quyền, cách giám sát và kết thúc. Không để một dòng “break-glass” vô hiệu hóa lập luận không có đường đi vòng.

### 7.4. Cách ra kết luận

Sau kiểm chứng, hồ sơ có thể ghi:

- SEC-ARCH-04 vẫn chưa được thực hiện theo cách chuẩn; ngoại lệ EX-017 cho phép phạm vi đã xác định sử dụng phương án khác đến hạn phê duyệt.
- SEC-AUTH-01, SEC-AUTHZ-02 và SEC-AUDIT-03 được đánh giá riêng theo bằng chứng trên đúng phiên bản triển khai.
- Kết quả chỉ có hiệu lực khi cấu hình cổng, đường mạng, ánh xạ danh tính và cơ chế thu hồi giữ đúng các giả định đã kiểm tra.
- Rủi ro còn lại gồm phụ thuộc tập trung vào cổng và khả năng cấu hình thay đổi làm mở đường truy cập mới; hồ sơ phải nêu cách theo dõi và người chịu trách nhiệm.
- Nếu không thể bảo toàn danh tính hoặc thu hồi phiên theo yêu cầu, cần sửa phương án, giảm chức năng hoặc trình bày đúng phần chưa đáp ứng để quyết định theo thẩm quyền.

Có thể dùng thang định tính để so sánh rủi ro trước và sau, nhưng phải ghi căn cứ về khả năng xảy ra và hậu quả. Không gán một mức “thấp” chỉ vì đã thêm nhiều lớp kiểm soát; cũng không cộng hoặc nhân các điểm thứ bậc rồi coi đó là xác suất chính xác.

## 8. Áp dụng cho năm nhóm yêu cầu bảo mật

| Nhóm | Khoảng trống minh họa | Hướng bù đắp cần đánh giá | Giới hạn cần làm rõ |
| --- | --- | --- | --- |
| Xác thực | Ứng dụng chưa tích hợp IdP trực tiếp | Cổng thực thi MFA, kiểm soát mọi đường truy cập và vòng đời phiên | Còn đường đi vòng hoặc phiên không thu hồi được thì mục tiêu chưa được bảo đảm |
| Phân quyền | Chưa hỗ trợ tách hai vai trò trong một thao tác | Tách bước nghiệp vụ, quyền tối thiểu, phê duyệt độc lập trước khi có hiệu lực | Xem log sau thao tác không tự tương đương việc ngăn một người tự thực hiện toàn bộ |
| Dữ liệu | Thành phần cũ chưa có cơ chế mã hóa theo chuẩn yêu cầu | Xem xét lớp bảo vệ khác cùng kiểm soát truy cập, khóa và vị trí dữ liệu | Mã hóa ổ đĩa không bảo vệ khỏi mọi truy cập của tiến trình hoặc người có đặc quyền |
| Logging | Không ghi được đầy đủ hành động quản trị | Đối chiếu log ứng dụng với bằng chứng tại lớp truy cập hoặc lớp dữ liệu phù hợp | Log cổng không chứng minh hành động nội bộ nào đã xảy ra nếu thiếu khả năng tương quan |
| Phục hồi | Chưa có failover tự động trong thời gian chuyển đổi | Bản sao, môi trường chờ, quy trình phục hồi và diễn tập | Chỉ là phương án phù hợp nếu chứng minh được RTO, RPO và tính toàn vẹn đã yêu cầu |

Các dòng trên là điểm xuất phát để phân tích, không phải danh sách phương án được chấp thuận sẵn. Với mỗi trường hợp, phải quay lại thuộc tính cần bảo vệ: bí mật, toàn vẹn, sẵn sàng, xác thực hoặc trách nhiệm giải trình.

Ví dụ, thay kiểm soát phân quyền bằng “hai người cùng biết mật khẩu quản trị” có thể còn làm giảm khả năng quy trách nhiệm. Một biện pháp mang tên quy trình bốn mắt chỉ có ý nghĩa khi người thực hiện không thể tự bỏ qua bước phê duyệt độc lập và bằng chứng thể hiện điều đó.

## 9. Quy trình xét duyệt và phân công trách nhiệm

Một quy trình minh họa gồm các bước sau:

1. **Đề nghị:** nhóm sở hữu nêu yêu cầu chưa đạt, lý do, phạm vi và kế hoạch xử lý.
2. **Kiểm tra tính áp dụng:** xác nhận nguồn yêu cầu và cơ chế cho phép ngoại lệ hoặc triển khai thay thế.
3. **Đánh giá kỹ thuật:** xem mô hình đe dọa, kiến trúc, phương án bù đắp và ca kiểm thử.
4. **Triển khai, kiểm chứng:** thu thập bằng chứng cho các điều kiện bắt buộc trước vận hành.
5. **Quyết định:** người có thẩm quyền chấp nhận, từ chối hoặc yêu cầu bổ sung; ghi rõ điều kiện và thời hạn.
6. **Kích hoạt:** xác nhận mọi điều kiện tiên quyết đã đạt và thông báo trách nhiệm vận hành trong phạm vi cần thiết.
7. **Theo dõi và kết thúc:** giám sát hiệu lực, rà soát thay đổi, xử lý hết hạn và đóng bằng bằng chứng.

Tổ chức có thể phê duyệt có điều kiện trước bước triển khai. Trạng thái đó phải thể hiện rõ hệ thống chưa được phép vận hành theo ngoại lệ cho tới khi các điều kiện tiên quyết đạt.

| Vai trò | Trách nhiệm chính |
| --- | --- |
| Người đề nghị / nhóm phát triển | Cung cấp khoảng trống, ràng buộc và kế hoạch khắc phục |
| Chủ kiểm soát | Triển khai, vận hành và duy trì hiệu lực biện pháp |
| Người đánh giá bảo mật | Kiểm tra lập luận, bằng chứng và giới hạn kết luận |
| Chủ rủi ro | Hiểu hậu quả đối với nghiệp vụ, chịu trách nhiệm phần rủi ro được quản lý |
| Người phê duyệt có thẩm quyền | Ra quyết định trong hạn mức và phạm vi được giao |
| Người phụ trách nghĩa vụ áp dụng | Xem xét điều kiện hợp đồng, pháp lý hoặc khuôn khổ đánh giá khi có liên quan |
| Nhóm vận hành / trực | Theo dõi điều kiện hiệu lực, phản ứng và escalation |

Tên vai trò và cách tách nhiệm vụ tùy tổ chức. Điều cần giữ là người đề nghị không tự suy ra mình có quyền chấp nhận mọi hậu quả; đánh giá kỹ thuật cũng không thay thế thẩm quyền quyết định nghiệp vụ hoặc nghĩa vụ bắt buộc.

Mọi bằng chứng và quyết định cần gắn cùng phiên bản hồ sơ. Nếu cấu hình đã thay đổi sau kiểm thử, phải xác định kết quả cũ còn áp dụng hay cần kiểm chứng lại.

## 10. Giám sát trong thời gian ngoại lệ

Đối với EX-017, kế hoạch giám sát cần theo dõi chính những điều làm phương án còn hợp lệ:

- Đường truy cập trực tiếp có tiếp tục bị chặn không?
- Chính sách MFA có được áp dụng cho đầy đủ tài khoản và phiên thuộc phạm vi không?
- Có tài khoản dùng chung, quyền mở rộng hoặc endpoint mới không?
- Khả năng thu hồi và đối chiếu danh tính có còn hoạt động không?
- Bằng chứng có còn mới và đủ phạm vi không?
- Mốc thay thế ứng dụng có còn khả thi không?

Ví dụ quy tắc vận hành:

~~~text
Ngoại lệ: EX-017
Phạm vi: danh sách ứng dụng, endpoint và tài khoản tại phụ lục có phiên bản
Thời hạn: tối đa 45 ngày kể từ khi kích hoạt theo quyết định phê duyệt
Rà soát: mỗi tuần và ngay khi xuất hiện thay đổi ảnh hưởng điều kiện hiệu lực

Trigger cần phản ứng:
  - Phát hiện đường truy cập bỏ qua cổng
  - Chính sách MFA hoặc ánh xạ danh tính không còn đúng
  - Phép thử thu hồi không đạt
  - Bằng chứng giám sát hết hạn hoặc nguồn quan trọng mất dữ liệu
  - Tài sản hoặc chức năng mở rộng ra ngoài phạm vi phê duyệt

Quyết định phải có trước:
  Ai nhận thông báo, ai được hạn chế chức năng, biện pháp duy trì nghiệp vụ,
  điều kiện thu hồi ngoại lệ và người được phép cho hoạt động trở lại.
~~~

Phát hiện kiểm soát không đạt và mất khả năng quan sát là hai tình huống khác nhau. Khi nguồn giám sát ngừng báo cáo, trạng thái bằng chứng là chưa đủ kết luận; không được tự coi biện pháp vẫn đạt.

Quy tắc phản ứng khi mất bằng chứng phải được quyết định theo tác động. Có thể hạn chế một chức năng nhạy cảm, dùng biện pháp thay thế đã chuẩn bị hoặc chuyển cấp xử lý trong thời hạn được chấp thuận. Không chờ sự cố xảy ra mới quyết định điều kiện tiếp tục vận hành.

### Khi công cụ có cơ chế bỏ qua cảnh báo

Nếu dùng suppression hoặc waiver trong scanner hay pipeline, cấu hình phải tham chiếu mã ngoại lệ, đúng loại phát hiện, đúng tài sản, đúng thời hạn và người phê duyệt. Hồ sơ vẫn cần giữ kết quả quan sát gốc.

Tắt toàn bộ quy tắc cho một repository hoặc một môi trường chỉ để bỏ qua một ngoại lệ hẹp có thể che mất các vi phạm mới. Cơ chế hết hạn của suppression cũng cần được kiểm tra; hết hạn hồ sơ trên tài liệu chưa bảo đảm công cụ đã khôi phục kiểm tra.

## 11. Hết hạn, gia hạn và thu hồi

### Hết hạn

Ngày hết hạn là điểm phải thực hiện một quyết định đã chuẩn bị, không chỉ là ngày gửi email nhắc việc. Trước hạn cần xác nhận khắc phục có hoàn tất không và điều kiện vận hành tiếp theo là gì.

Phương án xử lý có thể là chuyển sang hệ thống mới, tắt riêng chức năng có rủi ro hoặc thực hiện biện pháp khác đã được phê duyệt. Nếu hạn chế hoạt động có tác động lớn tới tính sẵn sàng, phải chuẩn bị và kiểm thử cách chuyển đổi phù hợp trước hạn.

### Gia hạn

Gia hạn là quyết định mới dựa trên dữ kiện hiện tại. Hồ sơ cần cập nhật:

- Vì sao kế hoạch cũ chưa hoàn tất và điều gì đã thay đổi?
- Phạm vi có còn giống quyết định trước không?
- Biện pháp bù đắp có được kiểm chứng gần đây không?
- Đe dọa, điểm yếu, hậu quả hoặc nghĩa vụ áp dụng có thay đổi không?
- Thời hạn mới có căn cứ, người chịu trách nhiệm và mốc kiểm tra khả thi không?

Không tự gia hạn vì người phê duyệt chưa phản hồi hoặc vì ngoại lệ trước đó từng được chấp thuận. Nếu hệ thống đã vận hành ngoài thời hạn, cần ghi nhận khoảng thời gian đó đúng thực tế; một quyết định ký sau không tạo bằng chứng rằng giai đoạn trước đã được kiểm soát.

### Thu hồi trước hạn

Ngoại lệ cần được xem xét thu hồi khi điều kiện bảo vệ không còn đúng, rủi ro vượt phạm vi chấp nhận, phát hiện thông tin bị thiếu hoặc sai, hoặc có thay đổi làm hồ sơ cũ không còn áp dụng.

Nếu có dấu hiệu sự cố đang diễn ra, chuyển sang quy trình ứng phó sự cố tương ứng và phối hợp quyết định ngoại lệ. Không đợi lịch rà soát định kỳ.

## 12. Đóng ngoại lệ bằng bằng chứng

Ngoại lệ có thể kết thúc theo nhiều cách: thực hiện kiểm soát gốc, thay thế hoặc ngừng hệ thống, loại bỏ chức năng liên quan, hoặc đưa phương án thay thế vào baseline qua quy trình điều chỉnh chính thức.

Tiêu chí đóng cần phù hợp với lý do kết thúc. Với EX-017, nếu ứng dụng mới đã tích hợp IdP trực tiếp, cần chứng minh:

1. Lưu lượng và tài khoản trong phạm vi đã chuyển sang ứng dụng mới.
2. Yêu cầu xác thực, phân quyền và truy vết đạt tiêu chí trên triển khai mới.
3. Đường quản trị của ứng dụng cũ đã bị loại bỏ hoặc xử lý theo quyết định kết thúc.
4. Tài khoản, quyền, bí mật và dữ liệu còn lại được xử lý theo yêu cầu.
5. Inventory, kiến trúc, ca kiểm thử, suppression và hồ sơ rủi ro đã cập nhật.

Một pull request đã merge hoặc một máy chủ đã cài phiên bản mới chưa tự chứng minh đủ những điều này.

Nếu chuyển sang phương án thay thế lâu dài, phải có yêu cầu và baseline được phê duyệt tương ứng. Không đóng hồ sơ bằng cách xóa yêu cầu gốc khỏi tài liệu mà không lưu lý do và quyết định thay đổi.

## 13. Truy vết và đánh giá chất lượng quản trị ngoại lệ

Chuỗi truy vết nên giữ được quan hệ:

~~~text
Yêu cầu và phiên bản
  -> khoảng trống
  -> tình huống đe dọa / rủi ro
  -> ngoại lệ và phạm vi
  -> biện pháp bù đắp
  -> ca kiểm thử / bằng chứng
  -> quyết định có thẩm quyền
  -> giám sát, gia hạn hoặc thu hồi
  -> bằng chứng đóng và cập nhật yêu cầu
~~~

Các chỉ số có ích gồm số ngoại lệ đang hiệu lực theo mức rủi ro, ngoại lệ quá hạn, ngoại lệ thiếu bằng chứng mới, số lần gia hạn, tài sản quan trọng bị ảnh hưởng và tình trạng kế hoạch khắc phục.

Không đánh giá chất lượng chỉ bằng tổng số ngoại lệ giảm. Con số có thể giảm do xử lý tốt, do gộp phạm vi quá rộng hoặc do nhóm không đăng ký khoảng trống. Cần đối soát với phát hiện kiểm thử và thay đổi kiến trúc.

Tương tự, nhiều ngoại lệ cùng dựa vào một cổng truy cập có thể tạo rủi ro tập trung. Mỗi hồ sơ riêng lẻ được duyệt chưa đủ để kết luận tổ chức chịu được việc cổng đó mất hiệu lực trên toàn bộ phạm vi.

## 14. Bài thực hành đặc tả

Với một hệ thống chưa thể triển khai kiểm soát chuẩn, hãy soạn một hồ sơ ngoại lệ gồm:

1. Một yêu cầu gốc có phiên bản, khoảng trống và lý do có bằng chứng.
2. Phạm vi có thể đối soát tới tài sản và đường truy cập cụ thể.
3. Một tình huống đe dọa cùng hậu quả cần bảo vệ.
4. Phương án bù đắp, giới hạn và phụ thuộc của từng biện pháp.
5. Kiểm thử hành vi hợp lệ, hành vi bị cấm, đường đi vòng và chế độ khi lỗi.
6. Rủi ro còn lại, người có thẩm quyền và điều kiện trước kích hoạt.
7. Thời hạn, trigger đánh giá lại, cách xử lý khi mất hiệu lực và kế hoạch kết thúc.

Sau đó xét ba thay đổi: thêm một endpoint, nguồn giám sát ngừng hoạt động và kế hoạch khắc phục chậm hai tuần. Hồ sơ tốt phải chỉ ra thay đổi nào nằm ngoài quyết định cũ, bằng chứng nào cần cập nhật và ai quyết định bước tiếp theo.

Exception có giá trị khi khoảng trống được nhìn thấy và có người chịu trách nhiệm. Compensating control có giá trị khi khả năng bảo vệ thay thế được đặc tả và kiểm chứng. Kết hợp hai cơ chế đúng cách giúp duy trì mục tiêu bảo mật trong điều kiện triển khai thực tế, đồng thời giữ rõ phần rủi ro còn lại và thời điểm phải xử lý dứt điểm.
