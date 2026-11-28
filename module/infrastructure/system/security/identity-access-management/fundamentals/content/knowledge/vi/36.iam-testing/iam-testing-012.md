# Deprovisioning test: kiểm chứng việc thu hồi truy cập đầu cuối

## 1. Đã xử lý yêu cầu chưa có nghĩa đã thu hồi được truy cập

Deprovisioning là quá trình kết thúc hoặc giảm khả năng truy cập khi một tài khoản, quan hệ hoặc quyền không còn cần thiết. Nó có thể bao gồm vô hiệu hóa tài khoản, gỡ quyền, kết thúc phiên, thu hồi credential và xử lý các liên kết với hệ thống đích.

Deprovisioning test kiểm tra rằng quá trình này tạo ra kết quả truy cập đúng theo phạm vi và thời hạn đã xác định.

Ví dụ, An Bình vô hiệu hóa một nhân viên tại nguồn quản lý danh tính. Connector báo thành công và directory hiển thị tài khoản không còn hoạt động. Tuy nhiên, một phiên cổng hợp đồng đã tạo trước đó vẫn có thể xuất dữ liệu.

Trong tình huống đó, kiểm tra cờ tài khoản là chưa đủ. Cần biết phiên còn được chấp nhận tới khi nào, token nào còn hiệu lực và điểm kiểm soát nào đã áp dụng thay đổi.

Mục tiêu của bài là thiết kế bộ kiểm thử cho những câu hỏi này. Các tình huống và dữ liệu minh họa không phải thao tác thu hồi trên tài khoản thật.

## 2. Xác định rõ loại thu hồi đang kiểm tra

Không phải mọi yêu cầu deprovisioning đều có nghĩa xóa toàn bộ tài khoản.

| Tình huống | Phạm vi cần xác định |
| --- | --- |
| Nhân viên kết thúc quan hệ với tổ chức | Những tài khoản, quyền và credential nào phải kết thúc? |
| Nhân viên chuyển nhóm | Quyền cũ nào cần gỡ và quyền nào vẫn hợp lệ? |
| Nhà thầu hết hạn hợp đồng | Mốc hiệu lực và các hệ thống liên quan |
| Người dùng rời một tenant | Chỉ thu hồi tenant đó hay toàn bộ tài khoản? |
| Vai trò tạm thời hết hiệu lực | Quyền đặc quyền và những phiên hoặc khả năng liên quan |
| Ứng dụng ngừng sử dụng một tài khoản | Tài khoản đích, liên kết và dữ liệu cần xử lý |
| Workload kết thúc vòng đời | Danh tính máy, credential và quyền của workload |

Test cần chứng minh đúng phạm vi, bao gồm việc không thu hồi ngoài dự kiến. Một người rời tenant A nhưng vẫn có quan hệ hợp lệ với tenant B không nhất thiết phải mất mọi quyền ở B.

Cũng cần phân biệt kết thúc truy cập với xóa dữ liệu. Hồ sơ hoặc bằng chứng kiểm toán có thể đi theo vòng đời riêng, nhưng việc còn giữ dữ liệu không nên làm chủ thể tiếp tục có quyền ngoài phạm vi đã thu hồi.

Nếu chưa rõ phạm vi hoặc thời hạn, cần làm rõ yêu cầu trước khi đặt kỳ vọng. Không dùng hành vi hiện tại của connector như định nghĩa mặc định cho kết quả đúng.

## 3. Lập bản đồ từ nguồn thay đổi tới điểm thực thi

Một luồng minh họa:

~~~mermaid
flowchart TD
    A[Nguồn có thẩm quyền ghi nhận thay đổi] --> B[Điều phối vòng đời]
    B --> C[Vô hiệu hóa tài khoản hoặc gỡ quyền]
    B --> D[Connector tới ứng dụng đích]
    B --> E[Xử lý credential và phiên theo thiết kế]
    C --> F[Thuộc tính và cache quyền]
    D --> G[Trạng thái tại hệ thống đích]
    E --> H[Điểm chấp nhận token và phiên]
    F --> I[Yêu cầu truy cập thực tế]
    G --> I
    H --> I
    I --> J[Đối chiếu kết quả và thời hạn]
~~~

Không phải hệ thống nào cũng có đủ các nhánh. Bộ test cần theo đúng kiến trúc đang có và chỉ rõ nhánh nào nằm ngoài phạm vi.

Với mỗi nhánh, cần xác định nguồn sự thật, chủ sở hữu thao tác và bằng chứng xác nhận:

| Lớp | Bằng chứng có thể cần |
| --- | --- |
| Nguồn vòng đời | Sự kiện hoặc trạng thái có mốc hiệu lực rõ |
| Điều phối | Yêu cầu đã được tiếp nhận và những đích cần xử lý |
| Connector | Kết quả thực hiện và lỗi theo từng hệ thống |
| Hệ thống đích | Trạng thái tài khoản, membership hoặc quyền |
| Phiên và credential | Trạng thái hiệu lực theo cơ chế tương ứng |
| Ứng dụng | Yêu cầu thực tế không còn được thực hiện trong phạm vi đã thu hồi |

Một sự kiện được gửi không chứng minh đã được áp dụng. Một request tới hệ thống đích thành công cũng chưa chứng minh mọi đường truy cập của chủ thể đã bị chặn.

## 4. Chuẩn bị tài khoản và trạng thái ban đầu có ý nghĩa

Một ca thu hồi không có giá trị nếu tài khoản thử vốn đã không truy cập được trước khi bắt đầu.

Nên chuẩn bị tài khoản tổng hợp với những quyền và đường truy cập đã biết, chẳng hạn:

- Một quyền cấp trực tiếp.
- Một quyền đến từ membership.
- Một phiên ứng dụng đang hoạt động.
- Access token hoặc credential thử nghiệm còn hiệu lực.
- Một hệ thống đích có tài khoản được cấp phát.
- Một tác vụ đang chờ nếu luồng cần bao phủ.

Không cần mọi ca đều có tất cả trạng thái trên. Chọn theo mục tiêu, nhưng phải xác nhận điều kiện ban đầu.

Ví dụ, trước ca thu hồi quyền đọc hợp đồng, cần chứng minh tài khoản đọc được hợp đồng tổng hợp tương ứng. Sau thu hồi, kiểm tra lại cùng loại hành động và tài nguyên.

Cần có chủ thể đối chứng vẫn hợp lệ để nhận biết hệ thống đang chặn đúng người hay toàn bộ ứng dụng đã gặp lỗi.

Dữ liệu thử nên có định danh ổn định và phạm vi tenant rõ. Không dùng một email chung làm khóa đối chiếu duy nhất nếu có thể thay đổi hoặc xuất hiện ở nhiều nguồn.

Không dùng tài khoản quản trị của người vận hành làm đối tượng deprovisioning. Ca thử cần nằm trong môi trường và phạm vi được kiểm soát.

## 5. Đặt tiêu chí đầu cuối và mốc thời gian

Một yêu cầu có thể được mô tả như sau:

~~~text
Sau mốc hiệu lực đã xác định,
trong thời hạn thu hồi của từng đường truy cập:

    chủ thể không tạo được truy cập mới thuộc phạm vi bị thu hồi
    trạng thái truy cập đang có được xử lý theo policy
    các hệ thống đích đạt trạng thái mong đợi
    dữ liệu hoặc quyền không liên quan không bị thay đổi ngoài phạm vi
    kết quả còn có thể được đối chiếu
~~~

Cần phân biệt các mốc:

| Mốc | Ví dụ ý nghĩa |
| --- | --- |
| Thời điểm nguồn xác lập thay đổi | Nguồn xác nhận quan hệ phải kết thúc |
| Mốc hiệu lực nghiệp vụ | Khi quyền phải bắt đầu kết thúc theo yêu cầu |
| Thời điểm tiếp nhận sự kiện | Hệ thống điều phối nhận được thông tin |
| Thời điểm áp dụng tại đích | Đích ghi nhận trạng thái mới |
| Thời điểm quan sát không còn truy cập | Ca thử thấy điểm thực thi từ chối hành động |

Nếu sự kiện tới muộn, chỉ đo từ lúc connector tiếp nhận có thể che phần chậm trước đó. Cần chọn mốc đo phù hợp với yêu cầu thực tế.

Có thể tính độ trễ quan sát của một đường:

~~~text
Độ trễ quan sát
    = thời điểm đầu tiên ghi nhận kết quả truy cập mong đợi
      - mốc bắt đầu đo đã xác định
~~~

Khi dùng polling, thời điểm quan sát không phải thời điểm chính xác trạng thái thực sự chuyển. Báo cáo cần nêu khoảng lấy mẫu và giới hạn này.

Không lấy thời gian trung bình của các đích rồi coi toàn bộ quy trình đạt. Một đích quan trọng vẫn còn quyền truy cập có thể làm yêu cầu đầu cuối không đạt, dù những đích khác xử lý rất nhanh.

## 6. Kiểm thử vô hiệu hóa, gỡ quyền và xóa theo đúng ngữ nghĩa

Nếu tích hợp SCIM, không nên suy diễn ý nghĩa đầy đủ của mọi trạng thái chỉ từ tên thuộc tính. RFC 7643 mô tả active là trạng thái quản trị, với ngữ nghĩa cụ thể do service provider xác định. Vì vậy, cần đối chiếu tài liệu của đích và hành vi truy cập thực tế. [RFC 7643, User resource](https://www.rfc-editor.org/rfc/rfc7643.html#section-4.1.1)

Với thao tác xóa SCIM, RFC 7644 cho phép bên cung cấp không xóa vĩnh viễn dữ liệu vật lý, nhưng phải xử lý tài nguyên đã xóa theo những quy tắc truy cập của giao thức. Kết quả đó không tự là bằng chứng mọi bản sao dữ liệu đã bị xóa. [RFC 7644, Deleting Resources](https://www.rfc-editor.org/rfc/rfc7644.html#section-3.6)

Các ca thử nên tách:

| Thao tác | Điều cần kiểm tra thêm |
| --- | --- |
| Vô hiệu hóa tài khoản | Đăng nhập và các đường truy cập nào bị chặn |
| Gỡ membership | Những quyền suy ra từ membership có thay đổi đúng không |
| Gỡ quyền trực tiếp | Quyền có còn đến từ một đường cấp khác không |
| Thu hồi vai trò tạm thời | Khả năng đặc quyền còn hoạt động ở đâu |
| Xóa tài khoản đích | Kết quả đọc, tìm kiếm và liên kết theo ngữ nghĩa của đích |
| Giữ hồ sơ nhưng chặn truy cập | Hồ sơ còn lưu không làm tiếp tục cấp quyền |

Nếu quyền được cấp qua nhiều đường, xóa một bản ghi chưa chứng minh quyền có hiệu lực đã mất. Test cần hiểu tập quyền mong đợi sau thay đổi.

Ngược lại, nếu chỉ gỡ một quyền cụ thể, không được coi việc mọi quyền của người dùng biến mất là kết quả tốt hơn.

## 7. Kiểm tra đăng nhập mới và các đường vào thay thế

Sau thay đổi, cần thử những đường đăng nhập hoặc tạo phiên nằm trong phạm vi, không chỉ một màn hình.

Có thể bao gồm:

- Đăng nhập trực tiếp tại ứng dụng.
- Đăng nhập qua SSO.
- Luồng liên kết từ một nhà cung cấp bên ngoài.
- Client web và client khác nếu có hợp đồng khác nhau.
- Cơ chế khôi phục hoặc đặt lại phương tiện.
- Tài khoản cục bộ còn tồn tại bên cạnh tài khoản liên kết.

Một người bị chặn tại IdP nhưng còn tài khoản cục bộ hoạt động ở ứng dụng đích có thể vẫn truy cập được qua một đường khác.

Đồng thời, không coi một lần đăng nhập thất bại do mật khẩu thử sai là bằng chứng deprovisioning có hiệu lực. Cần xác nhận nguyên nhân bằng trạng thái và bằng chứng thích hợp.

Kiểm tra nên đi qua giao diện hoặc API đúng với đường sử dụng thực tế. Một endpoint trạng thái quản trị có thể không phản ánh đầy đủ quyết định tại endpoint tài nguyên.

Nếu chính sách có ngoại lệ truy cập giới hạn sau khi kết thúc quan hệ, test phải kiểm tra đúng ngoại lệ đó: đúng hành động, dữ liệu, thời gian và chủ thể. Không coi ngoại lệ là quyền chung.

## 8. Kiểm tra phiên cũ, access token và refresh token

Đây là nhóm dễ bị bỏ sót nếu chỉ thử đăng nhập mới.

| Loại trạng thái | Câu hỏi kiểm thử |
| --- | --- |
| Phiên web đã có | Yêu cầu tiếp theo có còn được chấp nhận không? |
| Access token đã phát hành | Điểm tài nguyên phản ánh thu hồi vào mốc nào? |
| Refresh token | Có tiếp tục xin được quyền truy cập mới không? |
| Phiên tại ứng dụng đích | Đích có xử lý thay đổi vòng đời không? |
| Kết nối tồn tại lâu | Có mốc đánh giá lại hoặc kết thúc phù hợp không? |
| Cache quyết định | Quyền cũ có tiếp tục được dùng ngoài thời hạn thiết kế không? |

Thu hồi token có thể cần truyền trạng thái tới các nơi xác minh. RFC 7009 có lưu ý về độ trễ truyền thông tin vô hiệu hóa trong triển khai thực tế. Vì vậy, kiểm thử cần quan sát tại các điểm sử dụng liên quan và đối chiếu với yêu cầu thời gian. [RFC 7009, Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html#section-2.1)

Không suy ra rằng logout ở trình duyệt đã thu hồi mọi token. Tương tự, chặn cấp token mới không tự chứng minh token đã phát hành không còn được chấp nhận.

Bộ test nên chuẩn bị token còn hiệu lực đủ để kiểm tra mốc thu hồi. Nếu token tự hết hạn trước khi phép kiểm tra chạy, một kết quả từ chối có thể không chứng minh cơ chế deprovisioning đã hoạt động.

Với từng cơ chế, cần nêu rõ hệ thống hứa hẹn thu hồi như thế nào. Không đặt kỳ vọng vô hiệu hóa tức thì nếu kiến trúc hiện tại chỉ kiểm tra bằng chứng cục bộ mà không có đường cập nhật tương ứng; nếu yêu cầu nghiệp vụ cần nhanh hơn, đó là khoảng trống thiết kế cần được thể hiện.

## 9. Kiểm tra quyền, cache và các đích phân tán

Một nguồn danh tính đã cập nhật không chứng minh mọi điểm thực thi đã cập nhật.

Nên kiểm tra các đường đại diện cho:

- Quyền cấp trực tiếp và quyền suy ra từ nhóm.
- Vai trò có phạm vi tenant hoặc tài nguyên.
- Quyền đặc quyền hoặc truy cập tạm thời.
- Cache thuộc tính và cache quyết định.
- Replica hoặc vùng phục vụ lưu lượng khác.
- Ứng dụng đích có cách lưu trạng thái riêng.

Nếu chỉ thử một instance, có thể bỏ sót instance khác giữ cache cũ. Nếu chỉ đọc kho chính, có thể bỏ sót replica đang phục vụ ứng dụng.

Bộ test cần định vị được điểm quan sát: yêu cầu tới ứng dụng nào, vùng nào và phiên bản nào. Tổng hợp tất cả thành một nhãn “không truy cập được” sẽ làm khó điều tra khi một đích vẫn còn quyền.

Kết quả từ chối cũng phải được hiểu đúng. Timeout hoặc lỗi server không tương đương quyết định từ chối truy cập đã được thực thi. Cần phân biệt “đã chặn đúng” với “không thể xác minh vì phụ thuộc lỗi”.

Các quan sát trước và sau cần cùng phạm vi. Không thử hợp đồng A trước thay đổi rồi thử một hợp đồng B vốn không có quyền sau thay đổi.

## 10. Retry, sự kiện trùng và thứ tự thay đổi

Luồng vòng đời thường có tính bất đồng bộ. Sự kiện có thể bị gửi lại, xử lý chậm hoặc tới khác thứ tự mong đợi.

Các ca quan trọng:

| Tình huống | Kỳ vọng thiết kế cần được kiểm chứng |
| --- | --- |
| Cùng sự kiện kết thúc được xử lý lại | Không tạo tác động ngoài dự kiến |
| Connector đã áp dụng nhưng mất response | Retry không làm sai trạng thái đích |
| Một đích thành công, đích khác lỗi | Không báo toàn bộ hoàn tất |
| Cập nhật cũ tới sau lệnh kết thúc | Không tự khôi phục quyền trái trạng thái mong đợi |
| Job cấp quyền cũ tiếp tục chạy | Không cấp lại quyền đã kết thúc |
| Điều phối khởi động lại | Tiến độ và trạng thái cần thiết không bị mất |
| Đối soát toàn bộ chạy sau thu hồi | Không tái tạo tài khoản hoặc membership ngoài policy |

Ví dụ, một sự kiện cập nhật membership cũ nằm trong hàng đợi có thể tới sau sự kiện nghỉ việc. Test cần kiểm tra cơ chế quyết định thứ tự và trạng thái mong đợi của hệ thống.

Không giả định mọi giao thức tự cung cấp đủ giải pháp cho thứ tự nghiệp vụ. Phiên bản dữ liệu, kiểm tra điều kiện cập nhật hoặc logic đối soát cần được thiết kế trong đúng phạm vi chịu trách nhiệm.

Một ca retry đạt không chỉ là endpoint không báo lỗi. Cần xác nhận trạng thái cuối đúng, tài khoản khác không bị ảnh hưởng và các lần xử lý vẫn có thể đối chiếu.

Không tự động khôi phục quyền đã thu hồi thành công chỉ vì một hệ thống đích khác tạm thời chưa xử lý được. Hành vi khi thất bại từng phần phải được xác định rõ theo yêu cầu bảo vệ truy cập.

## 11. Job, ủy quyền, credential cá nhân và workload liên quan

Deprovisioning có thể ảnh hưởng tới những khả năng không xuất hiện trên trang tài khoản.

Ví dụ:

- Job xuất dữ liệu do người dùng khởi tạo.
- Quyền ủy quyền cho ứng dụng khác.
- Khóa API cá nhân.
- Phiên hoặc credential đặc quyền.
- Thông tin kết nối lưu trong công cụ.
- Tài nguyên hoặc workload mà người đó là chủ sở hữu quản trị.

Cần xác định trước những gì phải kết thúc và những gì phải chuyển trách nhiệm.

Một workload dùng chung cho nghiệp vụ không nhất thiết phải bị tắt khi chủ sở hữu nhân sự nghỉ việc. Có thể cần chuyển người chịu trách nhiệm và xử lý những credential liên quan theo phạm vi đã xác lập.

Ngược lại, một khóa API cá nhân không nên tiếp tục có toàn quyền chỉ vì không sử dụng màn hình đăng nhập.

Với job đang chờ hoặc đang chạy, test cần đối chiếu policy về mốc kiểm tra quyền. Nếu thiết kế yêu cầu đánh giá lại trước thực thi, cần thử việc thu hồi xảy ra giữa lúc tạo job và lúc chạy.

Nếu có thao tác đã bắt đầu, cần kiểm tra ranh giới xử lý phù hợp với nghiệp vụ. Không tự hứa rằng mọi thay đổi quyền có thể hủy tức thì mọi giao dịch đang diễn ra.

## 12. Tài nguyên, dữ liệu và việc quay lại tổ chức

Thu hồi truy cập không nên làm mất dữ liệu nghiệp vụ ngoài phạm vi đã xác định.

Các ca cần xem xét gồm:

| Nội dung | Điều cần kiểm tra |
| --- | --- |
| Tài nguyên do tài khoản tạo | Còn được quản lý bởi chủ thể có trách nhiệm không |
| Quyền sở hữu | Chuyển đúng người hoặc nhóm theo quy trình |
| Bản ghi kiểm toán | Vẫn đối chiếu được hành động với chủ thể phù hợp |
| Hồ sơ giữ lại | Không vô tình cho phép truy cập tiếp |
| Bí danh hoặc định danh được tái sử dụng | Không gắn quyền cũ cho người khác |
| Nhân viên quay lại | Chỉ nhận quyền theo phê duyệt và trạng thái hiện tại |

Nếu một người quay lại, không mặc định khôi phục toàn bộ membership và đặc quyền trước đây. Bộ test cần có ca cho chính sách tái kích hoạt hoặc cấp mới tương ứng.

Một email được tái cấp cho người mới cũng không phải lý do để liên kết người mới với toàn bộ tài nguyên và quyền của người cũ.

Khi cleanup dữ liệu kiểm thử, cần phân biệt việc dọn môi trường với hành vi của chính luồng deprovisioning. Không xóa thủ công mọi tài khoản ở cuối test rồi coi đó là bằng chứng hệ thống đã tự thu hồi đúng.

## 13. Thiết kế test có thể lặp lại và quan sát được

Có thể kết hợp các lớp:

- Unit test cho chuyển trạng thái và điều kiện thứ tự.
- Integration test cho connector và hệ thống đích.
- Kiểm thử hợp đồng cho request, response và lỗi.
- End-to-end test từ thay đổi tại nguồn tới yêu cầu truy cập.
- Kiểm thử lỗi từng phần, retry và xử lý đồng thời.
- Kiểm thử đối soát hoặc khôi phục tiến độ sau gián đoạn.

Mock thành công ở connector chỉ chứng minh nhánh điều phối trong phạm vi test. Nó không chứng minh đích đã vô hiệu hóa phiên hoặc quyền.

Với quá trình hội tụ, nên dùng kiểm tra điều kiện có giới hạn thời gian. Không chỉ chờ một khoảng cố định rồi đoán rằng mọi thứ đã xong.

Mã giả minh họa:

~~~text
xác nhận chủ thể tổng hợp đang có quyền cần kiểm tra
chuẩn bị các phiên và credential thử nghiệm cần bao phủ

ghi nhận mốc bắt đầu theo tiêu chí
phát thay đổi vòng đời qua đường nguồn được kiểm thử

trong giới hạn thời gian của từng mục tiêu:
    quan sát trạng thái và thử hành động đại diện
    ghi lại kết quả theo từng đích
    kết thúc quan sát mục tiêu khi đạt điều kiện đã định

nếu có mục tiêu quá hạn, lỗi hoặc chưa xác minh được:
    không đánh dấu toàn bộ ca đạt

xác nhận các chủ thể và quyền ngoài phạm vi vẫn đúng
~~~

Kết quả quan sát phải đủ chi tiết để biết đích nào chậm hoặc lỗi. Việc polling trả rỗng vì tài khoản kiểm thử không có quyền đọc trạng thái quản trị cũng cần được phân biệt với việc đích đã xóa tài khoản.

## 14. Một ca đầu cuối minh họa

~~~yaml
testId: DEPROVISION-E2E-01
scope: Kết thúc truy cập của tài khoản tổng hợp trong tenant thử nghiệm
preconditions:
  - Tài khoản đang hoạt động và truy cập được tài nguyên tổng hợp
  - Có một phiên web và credential API thử nghiệm còn hiệu lực
  - Các hệ thống đích cần xử lý đã được định danh
trigger:
  - Nguồn có thẩm quyền xác lập thay đổi kết thúc truy cập
expected:
  - Đăng nhập mới bị chặn theo mốc quy định
  - Phiên và credential cũ được xử lý trong thời hạn tương ứng
  - Quyền đích đạt trạng thái mong đợi
  - Không có job cũ tự cấp lại quyền
  - Tài khoản đối chứng tiếp tục có truy cập hợp lệ
evidence:
  - Tham chiếu sự kiện vòng đời
  - Kết quả connector theo từng đích
  - Trạng thái và kết quả truy cập đã giảm thông tin
  - Những mốc thời gian và giới hạn quan sát
~~~

Thời hạn cụ thể phải được điền theo yêu cầu của hệ thống. Mẫu không đặt ra một con số chung cho mọi ứng dụng.

Tại An Bình, test phát hiện đăng nhập mới đã bị chặn nhưng một phiên ở ứng dụng đích vẫn xuất được báo cáo sau mốc yêu cầu. Ca thử không được đánh dấu đạt chỉ vì các đích còn lại đã hoàn tất.

Nhóm xác định đường phiên chưa nhận thay đổi và bổ sung cơ chế xử lý phù hợp. Sau đó, ca hồi quy kiểm tra cả phiên cũ và việc job xuất đã tạo trước đó không tiếp tục ngoài policy.

Đây là sự khác biệt giữa xác minh thao tác quản trị và xác minh kết quả bảo vệ tài nguyên.

## 15. Bằng chứng, dữ liệu kiểm thử và tiêu chí hoàn tất

Báo cáo nên ghi rõ:

| Nội dung | Mục đích |
| --- | --- |
| Phiên bản triển khai và policy | Biết kết quả thuộc trạng thái hệ thống nào |
| Phạm vi chủ thể, tenant và quyền | Tránh kết luận rộng hơn ca thử |
| Các đường truy cập đã chuẩn bị | Biết baseline thực sự có ý nghĩa |
| Mốc hiệu lực và thời hạn | Đối chiếu tiêu chí thời gian |
| Kết quả theo từng đích | Nhận biết thất bại từng phần |
| Kết quả truy cập thực tế | Chứng minh tại điểm thực thi |
| Ngoại lệ và phần chưa xác minh | Không biến thiếu bằng chứng thành đạt |
| Dữ liệu hoặc quyền ngoài phạm vi | Kiểm tra tác động ngoài dự kiến |

Không lưu mật khẩu, token, khóa API hoặc nội dung tài nguyên nhạy cảm vào log CI để chứng minh ca thử. Dùng tham chiếu, trạng thái và dữ liệu tổng hợp vừa đủ.

Các tài khoản thử, credential và dữ liệu tạo ra cần có phạm vi riêng để dọn an toàn. Không dùng quy tắc cleanup rộng có thể tác động tài khoản thật.

Một bộ deprovisioning test đạt cần chứng minh quyền cần kết thúc đã được thực thi ở những đường quan trọng trong phạm vi và thời hạn đã xác định. Đồng thời, nó phải nhận ra các đích còn lỗi, trạng thái có thể tái cấp quyền và tác động tới phần không thuộc yêu cầu thu hồi.
