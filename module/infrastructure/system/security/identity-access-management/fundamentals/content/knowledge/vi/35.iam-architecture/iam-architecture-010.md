# Federation boundary: ranh giới tin cậy trong liên kết danh tính

## 1. Liên kết danh tính không xóa bỏ ranh giới bảo mật

Federation cho phép một miền sử dụng những phát biểu về danh tính do một miền khác cung cấp, theo một quan hệ tin cậy đã được xác lập. Federation boundary là ranh giới mà tại đó bên nhận phải quyết định phát biểu nào được chấp nhận, trong ngữ cảnh nào và dẫn tới quyền gì.

Miền ở đây có thể là một tổ chức, tenant, hệ thống danh tính hoặc phạm vi quản trị. Ranh giới không nhất thiết trùng với firewall, vùng mạng hay tên miền DNS.

Ví dụ, An Bình cho nhân viên đối tác đăng nhập cổng hợp đồng bằng nhà cung cấp danh tính của đối tác. An Bình không trực tiếp quản lý mật khẩu của những người đó, nhưng vẫn sở hữu quyết định ai được xem hợp đồng nào trong hệ thống của mình.

Quan hệ federation vì vậy không có nghĩa “người từ đối tác được tin như mọi tài khoản nội bộ”. Nó có nghĩa bên nhận chấp nhận một tập thông tin từ nguồn cụ thể, dưới những điều kiện cụ thể.

Thiết kế tốt cần giữ rõ hai việc: tin một phát biểu về danh tính và cho phép một hành động trên tài nguyên.

## 2. Ai phát biểu, ai chấp nhận và ai cấp quyền?

Một luồng đơn giản:

~~~mermaid
flowchart LR
    subgraph P[Miền đối tác]
        U[Người dùng]
        I[Nhà cung cấp danh tính]
        U --> I
    end
    subgraph A[Miền An Bình]
        V[Điểm xác minh liên kết]
        M[Ánh xạ chủ thể và thuộc tính]
        Z[Chính sách truy cập nội bộ]
        R[Tài nguyên hợp đồng]
        V --> M --> Z --> R
    end
    I -->|Bằng chứng theo quan hệ tin cậy| V
~~~

Nhà cung cấp danh tính có thể phát biểu rằng một chủ thể đã xác thực và có những thuộc tính nào đó. Bên nhận phải xác minh bằng chứng, ánh xạ chủ thể và áp dụng chính sách của mình.

| Trách nhiệm | Câu hỏi cần làm rõ |
| --- | --- |
| Bên phát hành | Ai quản lý tài khoản và chịu trách nhiệm cho phát biểu? |
| Bên nhận | Ứng dụng hoặc miền nào được sử dụng bằng chứng này? |
| Nguồn thuộc tính | Ai có thẩm quyền khẳng định từng thuộc tính? |
| Chủ sở hữu quyền | Ai quyết định quyền với tài nguyên nội bộ? |
| Bên vận hành quan hệ | Ai thay đổi cấu hình và xử lý sự cố liên kết? |

Một tổ chức có thể đáng tin cậy để xác nhận membership của nhân viên nhưng không có thẩm quyền tự cấp vai trò quản trị cho hệ thống của tổ chức khác.

Tương tự, một dịch vụ trung gian xác minh chữ ký không mặc nhiên có đủ ngữ cảnh để cấp quyền nghiệp vụ. Quyết định đó còn phụ thuộc tài nguyên, tenant, quan hệ sở hữu và trạng thái công việc.

## 3. Phân biệt federation, SSO và provisioning

Những khả năng này thường xuất hiện cùng nhau nhưng có phạm vi khác nhau:

| Khái niệm | Vai trò |
| --- | --- |
| Federation | Thiết lập việc chấp nhận phát biểu danh tính giữa các miền |
| SSO | Giảm việc người dùng phải thực hiện đăng nhập lại trong các luồng được hỗ trợ |
| Provisioning | Tạo và cập nhật tài khoản hoặc thuộc tính tại hệ thống đích |
| Authorization | Xác định hành động nào được phép trên tài nguyên |
| Session management | Quản lý phiên và khả năng tiếp tục sử dụng ứng dụng |

Đăng nhập liên kết thành công chưa chứng minh tài khoản nội bộ đã được cấp phát đúng hoặc có quyền hợp lệ.

Provisioning hoàn tất cũng chưa chứng minh người đang đăng nhập kiểm soát đúng danh tính đã được cấp phát.

Nếu dùng tạo tài khoản khi đăng nhập lần đầu, cần xác định rõ ai được tạo tài khoản, tài khoản được gắn vào tenant nào và quyền ban đầu là gì. Không để việc gửi một thuộc tính có tên tổ chức trở thành cách tự gia nhập tổ chức đó.

Các ranh giới tương tự còn xuất hiện với workload nhận danh tính từ một nền tảng để truy cập hệ thống khác. Tuy nhiên, hợp đồng của workload không nên bị coi là giống hệt luồng đăng nhập tương tác của con người.

## 4. Xây dựng hợp đồng tin cậy có phạm vi

Một quan hệ tin cậy cần nhiều hơn một URL hoặc một chứng chỉ.

Những nội dung nên xác lập gồm:

- Định danh chính xác của bên phát hành và bên nhận.
- Giao thức, loại bằng chứng và luồng được chấp nhận.
- Cách ràng buộc khóa hoặc metadata với bên phát hành.
- Nhóm chủ thể hoặc tenant được phép tham gia.
- Thuộc tính được nhận và nguồn có thẩm quyền cho từng thuộc tính.
- Quy tắc ánh xạ sang tài khoản và quyền nội bộ.
- Yêu cầu về xác thực và độ mới theo từng luồng.
- Vòng đời tài khoản, phiên và việc kết thúc quan hệ.
- Chủ sở hữu vận hành, thay đổi và xử lý sự cố.

Ví dụ tài liệu thiết kế:

~~~yaml
relationshipId: partner-a-contract-access
owner: partner_identity_team
issuerReference: approved-partner-a-issuer
recipientReference: contracts-portal
allowedLocalTenant: partner-a
acceptedExternalAttributes:
  - subject_reference
  - display_name
  - partner_membership
mappingPolicyReference: partner-a-contract-mapping
sessionPolicyReference: external-contract-session
lifecyclePolicyReference: partner-access-lifecycle
~~~

Đây là mô tả minh họa, không phải cấu hình có thể trực tiếp bảo đảm an toàn.

Một mục “trusted = true” quá rộng sẽ che khuất các giới hạn. Cần biết bên phát hành được tin cho loại thông tin nào và trong phạm vi nào.

Quan hệ cũng có hướng. Việc An Bình chấp nhận một nhà cung cấp danh tính không tự tạo ra quyền ngược lại cho đối tác truy cập mọi hệ thống của An Bình hoặc sử dụng danh tính An Bình ở nơi khác.

## 5. Kiểm tra bằng chứng tại đúng ranh giới

Tại ranh giới nhận, cần xác minh bằng chứng theo giao thức và hợp đồng đã chọn. Chữ ký hợp lệ là một phần quan trọng, nhưng không đủ để trả lời mọi câu hỏi.

| Câu hỏi | Vấn đề cần ngăn |
| --- | --- |
| Ai thực sự phát hành? | Chấp nhận nguồn chưa được cho phép |
| Khóa có thuộc nguồn đó không? | Dùng một khóa hợp lệ nhưng không thuộc bên được tin |
| Bằng chứng dành cho ai? | Dùng thông tin dành cho hệ thống khác |
| Loại bằng chứng dùng cho luồng nào? | Nhầm token đăng nhập với bằng chứng gọi API hoặc mục tiêu khác |
| Còn hiệu lực và đúng giao dịch không? | Dùng lại hoặc ghép nhầm bằng chứng vào luồng |
| Chủ thể và phạm vi có hợp lệ không? | Ánh xạ sai người hoặc tenant |

Ví dụ, khi xác minh ID token trong OpenID Connect, issuer phải khớp với issuer dự kiến và audience phải bao gồm client tương ứng theo các quy tắc của giao thức. Đây không phải quy tắc thay thế toàn bộ những kiểm tra khác. [OpenID Connect Core, ID Token Validation](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation)

Với JWT, cần ngăn việc dùng một token ở bên nhận hoặc mục đích không phù hợp. RFC 8725 mô tả rủi ro thay thế token và nhầm lẫn giữa các loại JWT, đồng thời yêu cầu kiểm tra audience trong các tình huống áp dụng. [RFC 8725, sections 2.7–2.8 và 3.8–3.12](https://www.rfc-editor.org/rfc/rfc8725.html#section-3.9)

Các kiểm tra thời gian, ràng buộc giao dịch và chống phát lại phải theo đúng luồng. Không viết một bộ kiểm tra tối giản rồi sử dụng cho mọi giao thức.

Nên dùng thành phần tích hợp phù hợp với giao thức và cấu hình rõ phạm vi tin cậy. Việc tích hợp thư viện không loại bỏ trách nhiệm cấu hình issuer, bên nhận và các điều kiện của hệ thống.

## 6. Metadata và khóa cũng nằm trong ranh giới tin cậy

Bằng chứng có thể tham chiếu tới khóa hoặc đi kèm định danh nguồn. Không nên để dữ liệu do bên gửi tự khai mở rộng tập nguồn được tin.

Ví dụ, một token tự khai issuer mới không phải lý do để hệ thống tự tải khóa từ bất kỳ địa chỉ nào rồi chấp nhận issuer đó.

Cần phân biệt:

- Tìm thông tin của một nguồn đã nằm trong quan hệ tin cậy.
- Xác minh metadata hoặc khóa thuộc nguồn dự kiến.
- Quyết định thêm một quan hệ tin cậy mới.

Ba việc đó không phải một bước tự động duy nhất.

Vòng đời khóa cũng cần được thiết kế: nhận khóa mới, giai đoạn chuyển tiếp, bỏ khóa cũ và xử lý khi nghi ngờ khóa bị lộ. Cần có trách nhiệm rõ giữa bên phát hành, thành phần trung gian và các ứng dụng nhận.

Khi gặp một khóa chưa biết, hệ thống có thể cần cập nhật metadata theo cơ chế đã định. Nhưng không nên bỏ xác minh hoặc chấp nhận dữ liệu cấu hình không có nguồn tin cậy để làm đăng nhập tiếp tục hoạt động.

Đồng thời, không giữ metadata cũ vô hạn chỉ vì nguồn tạm thời không truy cập được. Phạm vi chấp nhận dữ liệu đã lưu cần gắn với chính sách và tình huống lỗi được thiết kế.

## 7. Định danh chủ thể phải giữ được phạm vi nguồn

Hai nhà cung cấp khác nhau có thể phát hành cùng một giá trị chủ thể. Nếu ứng dụng chỉ lưu một chuỗi subject mà bỏ nguồn, các danh tính có thể bị nhập nhầm.

Trong OpenID Connect, cặp issuer và subject là cơ sở định danh ổn định theo phạm vi được đặc tả. Email, tên hiển thị hoặc tên đăng nhập không có cùng bảo đảm về tính duy nhất và ổn định. [OpenID Connect Core, Claim Stability and Uniqueness](https://openid.net/specs/openid-connect-core-1_0.html#ClaimStability)

Ví dụ ánh xạ nội bộ:

~~~text
Nguồn đối tác A + subject 582
    -> tài khoản ngoài A trong tenant đối tác A

Nguồn đối tác B + subject 582
    -> tài khoản ngoài B trong tenant đối tác B
~~~

Hai giá trị subject giống nhau không đủ để gộp hai tài khoản.

Việc liên kết một tài khoản bên ngoài với tài khoản nội bộ đã có cũng cần quy trình riêng. Không tự động liên kết chỉ vì email trùng, vì thuộc tính có thể thay đổi, được tái cấp hoặc có ngữ nghĩa khác giữa các nguồn.

Nếu thay nhà cung cấp danh tính hoặc chuyển tenant, cần có kế hoạch duy trì quan hệ chủ thể. Việc đổi issuer không đơn giản là đổi nhãn hiển thị.

Tương tự, không giả định một chủ thể luôn có cùng định danh ở mọi ứng dụng. Khi có cơ chế định danh theo phạm vi bên nhận, việc ánh xạ phải tôn trọng thiết kế đó và không tự tạo khả năng liên kết rộng hơn nhu cầu.

## 8. Ánh xạ thuộc tính không được biến thành cấp quyền tùy ý

Một trong những điểm nguy hiểm nhất là chuyển thẳng group hoặc role bên ngoài thành quyền nội bộ mà không xét nguồn và phạm vi.

Ví dụ, đối tác có group tên “admin”. Tên này có thể chỉ nói về quản trị một nhóm làm việc ở phía đối tác. Nó không có nghĩa thành viên được quản trị cổng hợp đồng An Bình.

Một bảng ánh xạ có phạm vi có thể như sau:

| Dữ liệu đầu vào đã được chấp nhận | Điều kiện bổ sung | Kết quả nội bộ |
| --- | --- | --- |
| Membership của đối tác A | Đúng quan hệ và đúng tenant | Được xem chức năng dành cho thành viên đối tác A |
| Nhóm xử lý hợp đồng của đối tác A | Có ánh xạ đã xác định và quyền trên hồ sơ tương ứng | Quyền nghiệp vụ giới hạn |
| Role không được ánh xạ | Không có quy tắc chấp nhận | Không tạo thêm quyền |
| Thuộc tính quản trị bên ngoài | Chưa có quyền nội bộ tương ứng | Không tự nâng lên quản trị nội bộ |

Bảng này chỉ minh họa nguyên tắc. Kết quả thực tế cần theo mô hình quyền của ứng dụng.

Một thuộc tính được ký không tự chứng minh bên phát hành có thẩm quyền quyết định mọi ý nghĩa của nó. Chữ ký giúp xác định nguồn và bảo vệ thông tin theo cơ chế sử dụng; bên nhận vẫn cần đánh giá quyền hạn của nguồn đối với thuộc tính.

Đối với thuộc tính quan trọng như tenant, trạng thái quan hệ hoặc tư cách thành viên, cần biết ai được sửa và thay đổi có hiệu lực khi nào. Đặc biệt, một trường người dùng có thể tự chỉnh không nên được dùng như thuộc tính quản trị chỉ vì nó xuất hiện trong token.

## 9. Không coi quan hệ tin cậy là bắc cầu tự động

Giả sử An Bình tin một identity broker, broker đó nhận danh tính từ nhiều nguồn khác nhau. An Bình không nên suy diễn rằng mọi nguồn phía sau broker đều được chấp nhận theo cùng điều kiện.

~~~text
Nguồn A -> Broker -> An Bình
Nguồn B -> Broker -> An Bình

An Bình tin Broker cho một phạm vi
    không tự chứng minh
Nguồn A và nguồn B có cùng quyền hoặc cùng mức tin cậy
~~~

Broker có thể xác minh bằng chứng đầu vào rồi phát hành bằng chứng mới. Bên nhận cần biết broker chịu trách nhiệm cho điều gì và những thông tin nguồn nào cần được giữ lại để áp dụng policy.

Nếu quyết định phụ thuộc vào nguồn ban đầu, ngữ cảnh đó phải được truyền và bảo vệ theo hợp đồng tin cậy. Không chấp nhận một trường nguồn do client cuối tự đặt.

Broker cũng không tự sửa được mọi vấn đề về quy trình đăng ký, khôi phục hoặc quản trị tài khoản của nguồn bên ngoài. Một tài khoản ở nguồn bị chiếm có thể vẫn tạo được bằng chứng hợp lệ về mặt giao thức.

Vì vậy, cần giới hạn những gì một nguồn hoặc một quan hệ có thể tác động. Đối với chức năng nhạy cảm, có thể cần điều kiện bổ sung được xác định riêng, thay vì coi mọi đường đăng nhập qua broker là tương đương.

## 10. Phương thức xác thực và mức tin cậy phải có ngữ nghĩa thống nhất

Bên nhận có thể cần biết người dùng đã xác thực theo cách nào hoặc mức tin cậy mà bên phát hành khẳng định.

Tuy nhiên, một trường ghi “MFA” hoặc một nhãn mức tin cậy chỉ có ý nghĩa khi các bên thống nhất nó được tạo ra theo điều kiện nào.

Những câu hỏi cần làm rõ gồm:

- Người dùng đăng ký phương tiện xác thực bằng quy trình nào.
- Khôi phục tài khoản có thể thay phương tiện theo điều kiện nào.
- Nhãn phương thức hoặc mức tin cậy phản ánh bước nào.
- Bằng chứng xác thực mới đến mức nào đối với thao tác đang xét.
- Có cần bước bổ sung trước hành động nhạy cảm không.

Không chỉ kiểm tra một chuỗi có xuất hiện rồi suy ra mọi yêu cầu đã đạt.

Cũng không yêu cầu thêm một bước xác thực rồi coi mọi vấn đề cấp quyền được giải quyết. Xác thực mạnh hơn không thay thế kiểm tra tenant, quan hệ với tài nguyên hoặc điều kiện tách biệt trách nhiệm.

Quyết định nào có thể dùng kết quả xác thực liên kết và quyết định nào cần điều kiện riêng phải được đặt tại phía có trách nhiệm bảo vệ tài nguyên.

## 11. Vòng đời tài khoản và phiên cần vượt qua ranh giới tổ chức

Khi một người rời tổ chức đối tác, việc họ không nhận được bằng chứng đăng nhập mới chưa chắc kết thúc ngay mọi khả năng truy cập tại An Bình.

Những trạng thái có thể còn tồn tại gồm:

| Trạng thái | Vấn đề cần xử lý |
| --- | --- |
| Tài khoản cục bộ | Còn hoạt động và giữ quyền gì? |
| Phiên ứng dụng | Có tiếp tục được chấp nhận không? |
| Token đã phát hành | Điều kiện hiệu lực và kiểm tra trạng thái là gì? |
| Cache membership | Thay đổi nguồn được phản ánh khi nào? |
| Job đang chờ | Có tiếp tục dưới quyền đã lưu không? |
| Quan hệ liên kết tài khoản | Còn được dùng để khôi phục hoặc truy cập không? |

Quan hệ federation cần phối hợp với luồng cấp phát, đối soát hoặc tín hiệu vòng đời thích hợp. Không coi một kết nối đăng nhập là giải pháp đầy đủ cho việc kết thúc quyền.

An Bình cũng cần khả năng đình chỉ một tài khoản hoặc một quan hệ tại địa phương khi có sự cố, theo phạm vi quản trị của mình. Việc bên nguồn vẫn xác thực được người dùng không có nghĩa phía nhận phải tiếp tục cấp quyền.

Kết thúc hợp tác với một đối tác có thể cần xử lý cả cấu hình tin cậy, tài khoản, phiên, quyền, credential tích hợp và dữ liệu còn lưu. Xóa một khóa hoặc tắt một nút đăng nhập không tự chứng minh toàn bộ các trạng thái này đã được xử lý.

## 12. Phân biệt quyền của con người với quyền của dịch vụ

Trong liên kết workload, một nền tảng hoặc miền có thể cung cấp bằng chứng để workload nhận quyền ở hệ thống khác. Ranh giới vẫn cần giới hạn nguồn, đối tượng nhận, loại workload và phạm vi quyền.

Không nên coi mọi workload từ một nền tảng là cùng một chủ thể. Cần phân biệt những thuộc tính có ý nghĩa như môi trường, ứng dụng hoặc bối cảnh thực thi theo cơ chế được sử dụng.

Nếu một dịch vụ gọi tài nguyên thay mặt người dùng, bên nhận cần hiểu cả quyền của workload lẫn ngữ cảnh ủy quyền. Chỉ biết dịch vụ kết nối là ai chưa đủ để suy ra người dùng nào được phép đọc dữ liệu.

Tương tự, không dùng cùng một bằng chứng ở mọi tài nguyên chỉ vì các dịch vụ nằm trong cùng doanh nghiệp. Phạm vi bên nhận và quyền được giao phải phù hợp với đường gọi.

Quan hệ federation của con người và quan hệ cấp quyền cho workload có thể chia sẻ hạ tầng, nhưng không nên dùng chung một policy quá rộng làm mất những khác biệt đó.

## 13. Ranh giới dữ liệu và quyền riêng tư

Federation còn là đường chuyển thuộc tính giữa các bên. Mỗi bên nhận nên chỉ có thông tin cần cho mục đích đã xác định.

Một ứng dụng hợp đồng có thể cần định danh, tên hiển thị và quan hệ với tổ chức. Nó không nhất thiết cần số giấy tờ, toàn bộ nhóm nội bộ hoặc thông tin khôi phục của người dùng.

Cần kiểm soát cả chiều gửi và chiều nhận:

- Bên phát hành chọn dữ liệu được cung cấp cho từng ứng dụng.
- Bên nhận giới hạn những gì lưu và chuyển tiếp.
- Broker không tự trở thành kho gom mọi thuộc tính.
- Log tránh lưu nguyên token hoặc toàn bộ hồ sơ.
- Quyền liên kết dữ liệu giữa nhiều nguồn được xác định riêng.
- Khi kết thúc quan hệ, dữ liệu còn lại đi theo vòng đời tương ứng.

Định danh đã được đổi hoặc mã hóa theo một cách nào đó vẫn có thể liên kết được với cá nhân thông qua dữ liệu khác. Không coi chỉ thay định danh là đủ để bỏ mọi giới hạn sử dụng.

Một sự đồng ý trong một luồng cũng không tự mở phạm vi dữ liệu cho mọi bên nhận tương lai. Thay đổi bên nhận hoặc mục đích cần được xử lý như thay đổi của quan hệ, không chỉ là sửa mapper.

## 14. Sự cố và khả năng cô lập quan hệ tin cậy

Một quan hệ có thể gặp lỗi cấu hình, gián đoạn nguồn, lộ khóa hoặc tài khoản quản trị bị xâm phạm.

Kiến trúc cần biết cách giới hạn tác động:

| Tình huống | Khả năng cần có |
| --- | --- |
| Một nguồn đối tác gặp sự cố | Xác định và xử lý đúng quan hệ bị ảnh hưởng |
| Khóa bị nghi ngờ lộ | Thay đổi tin cậy và đánh giá những trạng thái đã được tạo |
| Thuộc tính ánh xạ sai | Thu hẹp hoặc tắt ánh xạ, đối soát quyền liên quan |
| Tài khoản ngoài bị chiếm | Đình chỉ tại đích và xem lại phiên, token hoặc job liên quan |
| Broker nhận thêm nguồn | Có điểm kiểm soát trước khi nguồn mới được chấp nhận |
| Nguồn tạm thời không hoạt động | Hành vi suy giảm theo thiết kế, không tự bỏ xác minh |

Đổi khóa không tự kết thúc mọi phiên cục bộ đã được tạo trước đó. Xử lý sự cố cần nhìn cả bằng chứng mới và trạng thái sau đăng nhập.

Nếu có phương án truy cập khẩn cấp, phương án đó cần phạm vi, quyền, thời gian và kiểm toán riêng. Không biến sự cố federation thành lý do dùng chung một tài khoản quản trị không kiểm soát.

Quan sát nên tách lỗi xác minh bằng chứng, lỗi ánh xạ chủ thể, từ chối quyền và lỗi nghiệp vụ. Những nhóm lỗi này dẫn tới các hướng điều tra khác nhau.

## 15. Ví dụ thiết kế tại An Bình

Đối tác A được phép đưa nhân viên vào cổng hợp đồng của tenant A. An Bình xác lập một quan hệ có issuer, bên nhận và quy tắc ánh xạ rõ ràng.

Một người đăng nhập thành công có thể được ánh xạ vào tài khoản đối tác, nhưng chỉ đọc được những hợp đồng mà policy của An Bình cho phép.

Các trường hợp được xử lý khác nhau:

| Tình huống | Cách diễn giải |
| --- | --- |
| Nguồn đúng, bằng chứng đúng, quyền đúng | Cho thực hiện hành động trong phạm vi |
| Nguồn đúng nhưng bằng chứng dành cho ứng dụng khác | Không chấp nhận cho luồng hiện tại |
| Nguồn đúng, group tên “admin” nhưng chưa được ánh xạ | Không tạo quyền quản trị An Bình |
| Email trùng một tài khoản nội bộ | Không tự động liên kết tài khoản |
| Người dùng thuộc đối tác A yêu cầu hợp đồng tenant B | Kiểm tra và từ chối nếu không có quyền phù hợp |
| Broker thêm nguồn B | Không tự coi nguồn B thuộc quan hệ của đối tác A |
| Đối tác báo người dùng đã nghỉ | Áp dụng quy trình vòng đời và kiểm tra trạng thái còn tồn tại |
| Nghi ngờ quan hệ bị xâm phạm | Cô lập quan hệ theo quy trình và đánh giá tác động |

Thiết kế này giữ được lợi ích của liên kết: An Bình không cần quản lý mật khẩu của từng nhân viên đối tác. Đồng thời, nó giữ quyền quản trị tài nguyên và phạm vi truy cập ở nơi có trách nhiệm tương ứng.

## 16. Những tình huống cần kiểm tra

| Tình huống kiểm tra | Điều cần bảo đảm |
| --- | --- |
| Bằng chứng có chữ ký hợp lệ từ nguồn chưa được chấp nhận | Không tự tạo quan hệ tin cậy |
| Khóa không thuộc nguồn dự kiến | Không xác nhận nguồn chỉ từ việc kiểm tra mật mã thành công |
| Sai audience hoặc sai loại bằng chứng | Không dùng cho ứng dụng hoặc luồng khác |
| Bằng chứng hết hạn hoặc không khớp giao dịch | Xử lý theo kiểm tra của giao thức tương ứng |
| Hai nguồn có cùng subject | Không nhập nhầm danh tính |
| Email trùng tài khoản đã có | Không tự liên kết ngoài quy trình |
| Thuộc tính role không được ánh xạ | Không tự tạo quyền |
| Người dùng sửa thuộc tính phía nguồn | Không vượt phạm vi thẩm quyền đã xác lập |
| Broker có nhiều nguồn | Giữ đúng giới hạn theo nguồn và quan hệ |
| Quyền bị thu hồi nhưng phiên còn | Hành vi phản ánh thiết kế vòng đời đã công bố |
| Workload nhận bằng chứng từ bên ngoài | Chỉ nhận đúng phạm vi quyền được giao |
| Một quan hệ bị cô lập | Không làm mở rộng tin cậy qua đường khác |
| Thay khóa hoặc metadata | Không bỏ qua xác minh và có thể quan sát tiến trình |
| Kiểm tra claim và log | Không chia sẻ dữ liệu danh tính ngoài nhu cầu |

Federation boundary có hiệu lực khi mỗi phát biểu được chấp nhận với đúng nguồn, phạm vi và ngữ nghĩa, sau đó được chuyển thành quyết định truy cập có giới hạn tại bên nhận. Liên kết giúp các miền phối hợp danh tính; ranh giới giữ cho sự phối hợp đó không trở thành quyền truy cập không kiểm soát.
