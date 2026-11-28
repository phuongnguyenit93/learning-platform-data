# Viết requirement cho authentication

## 1. Mục tiêu của bài thực hành

Authentication, hay xác thực, là việc hệ thống thiết lập mức tin cậy phù hợp về danh tính của chủ thể đang tương tác. Authorization, hay phân quyền, quyết định chủ thể đó có được thực hiện một hành động trên một đối tượng cụ thể hay không.

Một phiên đăng nhập hợp lệ không tự cho phép đọc dữ liệu tenant khác. Một tài khoản có vai trò quản trị cũng không tự chứng minh bước xác thực bổ sung đã được thực hiện.

Bài thực hành yêu cầu chuyển mục tiêu “đăng nhập an toàn” thành các yêu cầu bảo mật:

- Có nguồn gốc từ rủi ro và phạm vi nghiệp vụ.
- Nêu rõ điều kiện, hành vi và kết quả bắt buộc.
- Bao phủ đăng nhập, xác thực bổ sung, phiên và thu hồi.
- Xác định hành vi khi phụ thuộc lỗi.
- Liên kết với kiến trúc, người chịu trách nhiệm và tiêu chí kiểm thử.

Đầu ra là một tập đặc tả có thể được rà soát, triển khai và kiểm chứng. Bài không yêu cầu xây dựng một giao thức xác thực hoặc tự triển khai thuật toán mật mã.

Các ngưỡng thời gian trong ví dụ là giả định của sản phẩm, không phải giá trị bắt buộc chung cho mọi hệ thống.

## 2. Bối cảnh và phạm vi được giao

### 2.1. Sản phẩm giả định

Một cổng hỗ trợ khách hàng có nhiều workspace:

- Nhân viên dùng trình duyệt để đăng nhập.
- Người có quyền phù hợp xem phiếu, trả lời và xuất dữ liệu.
- Quản trị viên quản lý vai trò thành viên.
- Các thao tác nhạy cảm cần xác thực bổ sung theo chính sách.
- Dịch vụ được triển khai ở nhiều instance.

Cổng không nhận hoặc lưu password của người dùng. Đăng nhập và yếu tố xác thực do dịch vụ danh tính tập trung ID-CORP thực hiện. Cổng chỉ tiếp nhận kết quả qua tích hợp đã được phê duyệt và quản lý phiên ứng dụng.

Phạm vi bài tập là người dùng tương tác qua trình duyệt. Danh tính máy, API key và thông tin xác thực giữa dịch vụ thuộc đặc tả riêng; không được dùng phiên người dùng thay cho chúng.

### 2.2. Các thành phần cần biết

| Thành phần | Trách nhiệm trong bài tập |
| --- | --- |
| Trình duyệt | Khởi tạo luồng đăng nhập, giữ thông tin phiên theo cơ chế đã chọn |
| ID-CORP | Xác minh yếu tố, phát hành kết quả và thông tin phương thức xác thực |
| Thành phần xác minh tích hợp | Kiểm tra nguồn, tính xác thực, mục đích nhận và ràng buộc giao dịch |
| Cổng xác thực ứng dụng | Tạo, kiểm tra và hủy phiên ứng dụng |
| Kho phiên có thẩm quyền | Lưu trạng thái phiên dùng chung cho các instance |
| Danh mục tài khoản ứng dụng | Quyết định tài khoản còn được sử dụng cổng hay đã bị vô hiệu hóa |
| API nghiệp vụ | Yêu cầu phiên hợp lệ và kiểm tra quyền đối với hành động, đối tượng |
| Audit | Ghi sự kiện cần thiết, không chứa bí mật xác thực |

Không được coi thông tin từ trình duyệt là bằng chứng rằng ID-CORP đã xác thực. Ranh giới tin cậy nằm giữa dữ liệu phía gọi cung cấp và kết quả đã được máy chủ kiểm tra.

### 2.3. Hồ sơ tin cậy chức năng của bài tập

Trong bài này, hồ sơ TRUST-01 có các điều kiện:

- Nguồn danh tính được chấp nhận là ID-CORP.
- Bên nhận hợp lệ của kết quả là SUPPORT-WEB.
- Danh tính được liên kết bằng cặp nguồn phát hành và subject ổn định; email hiển thị không phải khóa danh tính có thẩm quyền.
- Kết quả phải được xác minh bằng cơ chế tích hợp đã được phê duyệt, gồm tính xác thực, tính toàn vẹn, thời hạn và mục đích sử dụng.
- Kết quả phải tương ứng với một giao dịch đăng nhập còn hiệu lực do cổng đã khởi tạo.
- Thông tin phương thức và thời điểm xác thực chỉ được dùng sau khi nguồn và tính toàn vẹn được xác minh.
- Một kết quả chỉ xác minh yếu tố cơ bản không được tự nâng thành kết quả MFA.
- Các phương thức MFA được chấp nhận phải thuộc danh mục đã được tổ chức phê duyệt, gồm các yếu tố độc lập theo chính sách của tổ chức.

TRUST-01 là mô tả đầu vào của bài tập, không phải một giao thức mới hoặc một cấu hình mật mã hoàn chỉnh. Trong triển khai thật, các cơ chế, trust anchor, tham số và phiên bản tích hợp phải được xác định, rà soát và kiểm chứng cụ thể.

### 2.4. Các quyết định thời gian đã được cung cấp

| Nội dung | Giá trị giả định |
| --- | --- |
| Giao dịch đăng nhập chưa hoàn tất | Hết hiệu lực sau 5 phút |
| Thời gian nhàn rỗi của phiên | Tối đa 15 phút theo hoạt động được máy chủ tính |
| Tuổi tuyệt đối của phiên | Tối đa 8 giờ từ lúc tạo phiên |
| Độ mới MFA cho thao tác nhạy cảm | Không quá 5 phút tại điểm kiểm tra |
| Thu hồi do vô hiệu hóa tài khoản tại ứng dụng | Tối đa 60 giây từ lúc thay đổi được commit |
| Xử lý thông báo phục hồi hoặc đặt lại yếu tố từ ID-CORP | Thu hồi các phiên liên quan trong tối đa 60 giây từ lúc cổng tiếp nhận thông báo đã được xác minh |

Mốc cuối chỉ đo phần xử lý của cổng sau khi nhận thông báo. Nó chưa bảo đảm thời gian từ lúc thay đổi xảy ra tại ID-CORP đến lúc cổng biết. Nếu mục tiêu cần giới hạn đầu-cuối, phải có yêu cầu riêng về đường chuyển thông báo và hành vi khi đường đó lỗi.

## 3. Rủi ro cần chuyển thành yêu cầu

| Risk ID | Tình huống | Tác động cần tránh |
| --- | --- | --- |
| R-AUTH-01 | Phía gọi tự khai danh tính hoặc gửi kết quả từ nguồn không được tin cậy | Tạo phiên cho sai người |
| R-AUTH-02 | Kết quả hợp lệ bị dùng lại hoặc gắn vào giao dịch đăng nhập khác | Thiết lập phiên ngoài luồng được cho phép |
| R-AUTH-03 | ID phiên trước đăng nhập được giữ nguyên sau xác thực | Một giá trị có trước bị sử dụng như phiên đã đăng nhập |
| R-AUTH-04 | Phiên tồn tại quá lâu hoặc thời hạn chỉ do client thực thi | Tiếp tục sử dụng phiên ngoài giới hạn |
| R-AUTH-05 | Phiên còn dùng được sau logout hoặc vô hiệu hóa tài khoản | Chủ thể không còn được phép vẫn truy cập |
| R-AUTH-06 | Client tự khai đã MFA hoặc dùng chứng nhận quá cũ | Thực hiện thao tác nhạy cảm thiếu mức xác thực yêu cầu |
| R-AUTH-07 | Phục hồi tài khoản tạo đường đi yếu hơn nhưng vẫn được coi là MFA | Vượt chính sách bằng đường phục hồi |
| R-AUTH-08 | ID-CORP hoặc kho phiên lỗi và ứng dụng tự cho phép | Tạo hoặc chấp nhận danh tính không đủ cơ sở |
| R-AUTH-09 | Token, cookie hoặc bí mật xuất hiện trong log và báo cáo | Lộ khả năng truy cập và dữ liệu liên quan |
| R-AUTH-10 | Cùng email được coi là cùng danh tính mà không kiểm tra nguồn | Liên kết nhầm tài khoản hoặc vượt ranh giới danh tính |

Bảng không chứng minh đã bao phủ mọi đe dọa. Khi thay đổi phương thức đăng nhập, thêm danh tính máy hoặc thêm kênh truy cập, cần đánh giá lại phạm vi.

Các biện pháp chống dò yếu tố tại ID-CORP vẫn quan trọng, nhưng không được tự nhận là đã kiểm chứng chỉ vì cổng không nhận password. Cần trách nhiệm, tiêu chí và bằng chứng cho phần phụ thuộc đó theo phạm vi triển khai thực tế.

## 4. Nhiệm vụ và sản phẩm cần hoàn thành

Người học cần xây dựng:

1. Một bảng phạm vi, giả định và câu hỏi còn mở.
2. Tập yêu cầu có ID ổn định, bao phủ các rủi ro trong phạm vi.
3. Tiêu chí nghiệm thu gồm trường hợp được phép, bị cấm và lỗi.
4. Ma trận nối rủi ro, yêu cầu, điểm thực thi và test.
5. Một bản tự rà soát chất lượng và các phụ thuộc chưa đủ cơ sở.

Không dùng các câu sau như đặc tả hoàn chỉnh:

- “Dùng SSO an toàn.”
- “Mọi quản trị viên phải MFA.”
- “Token phải hợp lệ.”
- “Logout phải ngay lập tức.”
- “Có log đầy đủ.”

Mỗi câu cần được chuyển thành hành vi có thể kiểm tra. Nêu công nghệ có thể giải thích một phương án, nhưng chưa thay thế yêu cầu về kết quả bảo vệ.

### 4.1. Mẫu cho một yêu cầu

```yaml
requirementId: AUTH-XX
title: "<Hành vi bảo vệ cụ thể>"
sourceRisks:
  - "<Risk ID>"
scope: "<Chủ thể, đường truy cập và trạng thái liên quan>"
preconditions:
  - "<Điều kiện áp dụng>"
statement: "<Hệ thống phải thực hiện hoặc từ chối điều gì>"
timing:
  startEvent: "<Nếu có ngưỡng>"
  limit: "<Giá trị và đơn vị>"
failureBehavior: "<Hành vi khi thiếu điều kiện hoặc phụ thuộc lỗi>"
verification:
  positive:
    - "<Trường hợp hợp lệ>"
  negative:
    - "<Trường hợp bị cấm>"
  failure:
    - "<Trường hợp lỗi>"
owner: "<Vai trò chịu trách nhiệm>"
dependencies:
  - "<Hồ sơ tích hợp hoặc yêu cầu liên quan>"
```

Mẫu có thể điều chỉnh theo dự án. Điều cần giữ là mệnh đề bắt buộc, phạm vi, cơ sở và khả năng kết luận.

## 5. Lời giải tham khảo: xác lập danh tính và phiên

### AUTH-01 — Chỉ tạo phiên từ kết quả được xác minh

**Yêu cầu:** Cổng chỉ được tạo phiên xác thực sau khi kết quả từ ID-CORP đã thỏa TRUST-01, giao dịch tương ứng còn hiệu lực và tài khoản ứng dụng được phép hoạt động. Danh tính phiên phải được gắn với cặp nguồn phát hành và subject đã được xác minh.

Không được dùng email, `userId`, `verified = true` hoặc trường tương tự do client tự gửi làm bằng chứng xác thực.

**Tiêu chí nghiệm thu:**

- Kết quả hợp lệ, đúng nguồn, đúng bên nhận và đúng giao dịch tạo phiên cho đúng subject.
- Nguồn không được chấp nhận, kết quả bị thay đổi, quá hạn hoặc sai bên nhận đều không tạo phiên.
- Kết quả hợp lệ về nguồn nhưng không có giao dịch tương ứng bị từ chối.
- Tài khoản ứng dụng đã bị vô hiệu hóa không đăng nhập mới được dù ID-CORP trả xác thực thành công.
- Hai subject khác nhau có cùng email không tự được gộp thành một tài khoản.

**Nguồn:** R-AUTH-01, R-AUTH-10.

### AUTH-02 — Giao dịch đăng nhập có ràng buộc và dùng một lần

**Yêu cầu:** Mỗi giao dịch đăng nhập phải có định danh và dữ liệu ràng buộc được máy chủ quản lý, gắn với luồng trình duyệt đã khởi tạo, chỉ có hiệu lực trong 5 phút và chỉ được hoàn tất thành công một lần.

Việc kiểm tra, tiêu thụ giao dịch và tạo phiên phải bảo đảm hai lần xử lý đồng thời không tạo hai kết quả thành công ngoài chính sách.

Điểm quay về sau đăng nhập chỉ được lấy từ các đích đã được cho phép; không sử dụng một đích tùy ý do phía gọi cung cấp.

**Tiêu chí nghiệm thu:**

- Luồng đúng hoàn tất được trong thời hạn.
- Thiếu hoặc sai ràng buộc giao dịch không tạo phiên.
- Kết quả của giao dịch A không hoàn tất giao dịch B.
- Kết quả đến tại hoặc sau mốc hết hạn không được dùng.
- Gửi lại hoặc xử lý đồng thời cùng kết quả không tạo thêm phiên thành công.
- Đích quay về ngoài phạm vi được phép bị xử lý theo hợp đồng an toàn đã chốt.

**Nguồn:** R-AUTH-02.

### AUTH-03 — Tạo mới định danh phiên sau xác thực

**Yêu cầu:** Khi đăng nhập thành công, cổng phải cấp định danh phiên mới bằng cơ chế sinh bảo mật đã được phê duyệt. Định danh hoặc trạng thái trước xác thực không được tự trở thành phiên đã xác thực.

Thông tin phiên phải được truyền và lưu theo hồ sơ bảo vệ phiên của kiến trúc. Client không được tự sửa subject, mức xác thực hoặc thời hạn bằng cách thay dữ liệu phía mình.

**Tiêu chí nghiệm thu:**

- Định danh trước và sau đăng nhập không bị sử dụng như cùng một phiên đã xác thực.
- Giá trị trước đăng nhập không truy cập được API bảo vệ.
- Sửa thông tin phía client không đổi được danh tính hoặc mức xác thực ở máy chủ.
- Đường truyền và nơi lưu đáp ứng hồ sơ bảo vệ phiên đã chọn.
- Rà soát cơ chế sinh và quản lý phiên có cơ sở; không kết luận khó đoán chỉ vì một mẫu nhỏ không có giá trị trùng.

**Nguồn:** R-AUTH-03, R-AUTH-09.

### AUTH-04 — Thời hạn phiên do máy chủ quyết định

**Yêu cầu:** Phiên chỉ được chấp nhận nếu chưa vượt cả hạn nhàn rỗi 15 phút và tuổi tuyệt đối 8 giờ.

Gọi:

- `t_login`: lúc cổng tạo phiên thành công.
- `t_last`: mốc hoạt động hợp lệ gần nhất được máy chủ tính, khởi tạo bằng `t_login`.
- `t_now`: thời điểm máy chủ quyết định chấp nhận phiên.

Phiên hết hiệu lực khi:

```text
t_now >= min(t_login + 8 giờ, t_last + 15 phút)
```

Danh sách hành động làm mới `t_last` phải được chốt. Trong bài tập, các thao tác nghiệp vụ đã xác thực thuộc danh sách được tính; heartbeat và polling nền được xác định riêng không làm mới thời hạn.

Đây là thời gian không có hoạt động được máy chủ tính, không phải bằng chứng người dùng đang hay không đang gõ bàn phím. Không tin timestamp tự khai từ client.

**Tiêu chí nghiệm thu:**

- Phiên hợp lệ trước ngưỡng hoạt động theo chính sách.
- Đúng ngưỡng hoặc sau ngưỡng phải bị từ chối.
- Hoạt động được tính làm mới hạn nhàn rỗi nhưng không dời `t_login`.
- Heartbeat hoặc polling bị loại khỏi danh sách không giữ phiên sống vô hạn.
- Hoạt động liên tục không kéo phiên qua 8 giờ.
- Thay đồng hồ client không làm phiên được chấp nhận lâu hơn.

**Nguồn:** R-AUTH-04.

### AUTH-05 — Logout hủy phiên hiện tại tại nguồn có thẩm quyền

**Yêu cầu:** Trước khi xác nhận logout thành công, cổng phải làm mất hiệu lực phiên hiện tại tại kho phiên có thẩm quyền. Mọi quyết định xác thực mới cho phiên đó sau xác nhận phải bị từ chối trên các instance.

Xóa cookie ở trình duyệt là một phần dọn trạng thái phía client, không thay thế việc hủy phiên ở máy chủ.

Trong bài tập, yêu cầu đã vượt điểm xác thực trước logout có thể hoàn tất theo quyết định trước đó. Nếu cần hủy cả thao tác đang chạy, phải có yêu cầu riêng về điểm kiểm tra lại và hành vi hủy.

**Tiêu chí nghiệm thu:**

- Logout thành công làm phiên cũ không gọi được API bảo vệ.
- Phát lại thông tin phiên cũ ở instance khác vẫn bị từ chối.
- Logout một phiên không tự hủy mọi phiên khác nếu người dùng chỉ chọn logout hiện tại.
- Nếu không thể cập nhật nguồn phiên, không phản hồi thành công như thể việc hủy đã hoàn tất.
- Đăng nhập lại tạo phiên mới, không khôi phục hiệu lực định danh cũ.

**Nguồn:** R-AUTH-05.

## 6. Lời giải tham khảo: MFA, thu hồi và tình huống lỗi

### AUTH-06 — Vô hiệu hóa tài khoản thu hồi mọi phiên thuộc phạm vi

**Yêu cầu:** Khi tài khoản bị vô hiệu hóa tại danh mục tài khoản ứng dụng, mọi phiên của tài khoản đó phải bị từ chối ở các quyết định xác thực mới chậm nhất 60 giây từ mốc thay đổi được commit.

Phạm vi gồm các instance và các đường API bảo vệ đã liệt kê. Đăng nhập mới cũng phải bị từ chối theo AUTH-01.

Ngưỡng này áp dụng cho việc vô hiệu hóa tài khoản từ nguồn ứng dụng. Nó không làm yếu yêu cầu logout phiên hiện tại của AUTH-05.

**Tiêu chí nghiệm thu:**

- Tạo hai phiên của cùng tài khoản và một phiên của tài khoản khác.
- Vô hiệu hóa tài khoản tại nguồn có thẩm quyền, giữ mốc commit t0.
- Thử các phiên trên các instance và đường bảo vệ liên quan.
- Tại hoặc sau t0 + 60 giây, mọi quyết định mới cho tài khoản bị vô hiệu hóa phải bị từ chối.
- Phiên của tài khoản không liên quan vẫn hoạt động theo quyền của nó.
- Message trễ hoặc cập nhật hoạt động phiên không làm phiên đã thu hồi có hiệu lực trở lại.

**Nguồn:** R-AUTH-05.

### AUTH-07 — Thao tác nhạy cảm cần MFA đủ mới và đúng phiên

**Yêu cầu:** Thao tác xuất dữ liệu hàng loạt và thay đổi vai trò thành viên chỉ được đi tiếp khi phiên còn hợp lệ, người dùng có quyền nghiệp vụ tương ứng và bằng chứng MFA đã được xác minh theo TRUST-01 còn đủ mới.

Trong bài tập, đủ mới là không quá 5 phút từ mốc xác minh yếu tố bổ sung do nguồn tin cậy cung cấp, tính tại điểm máy chủ kiểm tra điều kiện của thao tác.

Bằng chứng phải gắn với đúng subject, phiên và giao dịch bổ sung tương ứng. Không nhận cờ `mfaVerified` do client tự khai.

Kết quả xác thực bổ sung chỉ được cập nhật trên phiên vẫn còn hiệu lực. Nó không được khôi phục một phiên đã logout, hết hạn hoặc bị thu hồi trong lúc người dùng đang thực hiện bước bổ sung.

**Tiêu chí nghiệm thu:**

- Phiên hợp lệ với MFA đủ mới và đủ quyền thực hiện được thao tác.
- Phiên chỉ có xác thực cơ bản bị yêu cầu bước bổ sung.
- MFA quá cũ không đáp ứng điều kiện thao tác nhạy cảm.
- Bằng chứng của người khác hoặc phiên khác không được gắn vào phiên hiện tại.
- Gửi `mfaVerified = true` không làm thay đổi mức ở máy chủ.
- Người không có quyền vẫn bị từ chối dù MFA thành công.
- Logout trong lúc chờ MFA rồi gửi kết quả về không làm phiên cũ sống lại.

**Nguồn:** R-AUTH-06, R-AUTH-05.

### AUTH-08 — Phục hồi không tạo đường bỏ qua mức xác thực

**Yêu cầu:** Cổng không được coi việc gửi yêu cầu phục hồi, nhận email hoặc biết một mã tham chiếu hỗ trợ là bằng chứng đã xác thực thành công.

Sau phục hồi tại ID-CORP, đăng nhập và MFA vẫn phải thỏa hồ sơ tin cậy tương ứng. Cổng không được tự nâng mức chỉ vì có thông tin “đã phục hồi”.

Khi cổng nhận thông báo phục hồi hoặc đặt lại yếu tố đã được xác minh từ ID-CORP, các phiên liên quan theo mốc cắt trong sự kiện phải bị thu hồi trong tối đa 60 giây.

Hợp đồng sự kiện phải xác định nguồn, bên nhận, tính toàn vẹn, subject, ID sự kiện và mốc thay đổi có thẩm quyền. Xử lý lặp không được đổi mốc cắt và vô tình hủy các phiên mới hợp lệ ngoài phạm vi của sự kiện.

**Tiêu chí nghiệm thu:**

- Trạng thái mới yêu cầu phục hồi không tạo phiên.
- Kết quả chỉ có xác thực cơ bản không mở thao tác yêu cầu MFA.
- Sự kiện giả hoặc sai subject không thu hồi nhầm phiên.
- Sự kiện hợp lệ thu hồi đúng các phiên thuộc phạm vi trong hạn.
- Gửi lại cùng sự kiện không làm sai phạm vi hoặc khôi phục phiên cũ.
- Nhận sự kiện sai thứ tự vẫn giữ được quy tắc thu hồi theo hợp đồng.

Mốc đo ở đây bắt đầu từ khi cổng nhận sự kiện đã được xác minh. Cần yêu cầu bổ sung nếu muốn giới hạn cả độ trễ từ ID-CORP đến cổng hoặc xử lý trường hợp sự kiện bị mất.

**Nguồn:** R-AUTH-07, R-AUTH-05.

### AUTH-09 — Thiếu cơ sở xác thực không dẫn đến tự cho phép

**Yêu cầu:** Nếu không thể xác minh một kết quả đăng nhập hoặc kết quả MFA, cổng không được tạo phiên hoặc nâng mức dựa vào dữ liệu chưa kiểm tra.

Nếu kho phiên không cung cấp được trạng thái đủ tin cậy để quyết định, API bảo vệ phải từ chối theo hợp đồng lỗi; không tự tin các trường phía client để thay thế.

Khi ID-CORP không sẵn sàng, phiên ứng dụng đã có chỉ được tiếp tục nếu máy chủ vẫn kiểm tra được hiệu lực, trạng thái tài khoản và quyền cần thiết theo các yêu cầu hiện hành. Không tự kéo dài hạn hoặc bỏ yêu cầu MFA để bù sự cố.

**Tiêu chí nghiệm thu:**

- ID-CORP lỗi không tạo được phiên mới hoặc kết quả bổ sung giả.
- Phiên cũ còn hợp lệ và kiểm tra cục bộ đầy đủ có hành vi đúng chính sách.
- Phiên hết hạn không được kéo dài vì ID-CORP lỗi.
- Kho phiên lỗi không làm API chấp nhận một định danh chưa xác minh.
- Luồng dự phòng không dùng email tự khai hoặc tài khoản đặc biệt không được đặc tả.
- Phản hồi lỗi không làm lộ chi tiết bí mật của tích hợp.

**Nguồn:** R-AUTH-08.

### AUTH-10 — Audit xác thực có ích nhưng không chứa bí mật

**Yêu cầu:** Các quyết định đăng nhập thành công/thất bại, MFA, logout, thu hồi và xử lý thông báo phục hồi phải phát sinh sự kiện audit theo danh mục đã chốt.

Sự kiện cần có hành động, kết quả, thời điểm, thành phần, correlation ID và tham chiếu danh tính hoặc phiên ở mức cần thiết. Không ghi password, mã yếu tố, token, cookie phiên hoặc nội dung kết quả có thể dùng để truy cập.

Danh tính trong sự kiện phải phản ánh độ tin cậy: thông tin do người chưa xác thực tự khai không được ghi như một actor đã được xác nhận.

**Tiêu chí nghiệm thu:**

- Kịch bản hợp lệ, bị cấm và lỗi tạo các sự kiện tương ứng.
- Liên kết được sự kiện với đúng lần thử mà không cần lưu bí mật.
- Marker tổng hợp đặt trong trường bị cấm không xuất hiện ở các nguồn thuộc phạm vi.
- Người không có quyền không đọc hoặc sửa được audit.
- Phân biệt một quyết định xác thực thất bại với lỗi kỹ thuật của phụ thuộc.

Độ bền, thời hạn chuyển tiếp, lưu giữ và hành vi khi đường audit lỗi cần được chốt trong yêu cầu vận hành liên quan. Không dùng câu “có log” để thay thế các quyết định đó trước khi đưa đặc tả vào triển khai thực tế.

**Nguồn:** R-AUTH-09.

## 7. Không gộp hiệu lực phiên với độ mới MFA

Một phiên có thể vẫn hợp lệ cho tác vụ thông thường nhưng cần xác thực bổ sung trước tác vụ nhạy cảm.

| Phiên ứng dụng | MFA | Quyền nghiệp vụ | Kết quả |
| --- | --- | --- | --- |
| Hợp lệ | Đủ mới | Có quyền | Được tiếp tục thao tác nhạy cảm |
| Hợp lệ | Thiếu hoặc quá cũ | Có quyền | Cần bước bổ sung, chưa thực hiện thao tác |
| Hợp lệ | Đủ mới | Không có quyền | Bị từ chối theo phân quyền |
| Hết hạn hoặc bị thu hồi | Đủ mới theo một kết quả trước | Bất kỳ | Không dùng phiên đó để thực hiện |
| Hợp lệ | Không cần cho tác vụ thường | Có quyền tác vụ thường | Hoạt động theo yêu cầu tương ứng |

Hết độ mới MFA không tự đồng nghĩa toàn bộ phiên phải bị hủy. Hệ thống cần kiểm tra đúng điều kiện của hành động.

Ngược lại, một kết quả MFA gần đây không làm một phiên đã bị thu hồi trở lại hợp lệ.

Yêu cầu về mức MFA cũng chưa tự chứng minh khả năng chống mọi hình thức lừa lấy thông tin xác thực. Nếu rủi ro đòi hỏi đặc tính bổ sung của phương thức, phải nêu đặc tính đó và phương pháp kiểm chứng riêng, không chỉ ghi “MFA”.

## 8. Ma trận truy vết và tiêu chí kiểm thử

### 8.1. Liên kết rủi ro, yêu cầu và kiến trúc

| Rủi ro | Yêu cầu | Điểm thực thi | Bằng chứng dự kiến |
| --- | --- | --- | --- |
| Giả danh hoặc liên kết nhầm | AUTH-01 | Bộ xác minh, liên kết subject | Kết quả kiểm tra nguồn, bên nhận, subject và tài khoản |
| Phát lại hoặc tráo giao dịch | AUTH-02 | Kho giao dịch đăng nhập | Test dùng lại, hết hạn, sai luồng và đồng thời |
| Sử dụng lại trạng thái trước đăng nhập | AUTH-03 | Cấp và quản lý phiên | Test định danh trước/sau cùng rà soát cơ chế sinh |
| Phiên quá hạn | AUTH-04 | Kiểm tra phiên tại máy chủ | Test biên và hoạt động nền với thời gian kiểm soát |
| Phiên không bị thu hồi | AUTH-05, AUTH-06 | Kho phiên, danh mục tài khoản, các instance | Test phát lại sau logout, vô hiệu hóa nhiều phiên |
| MFA giả hoặc quá cũ | AUTH-07 | Nguồn mức xác thực và điểm thao tác nhạy cảm | Test cờ client, sai subject, hết độ mới, thiếu quyền |
| Bỏ qua qua đường phục hồi | AUTH-08 | Tích hợp phục hồi và xử lý sự kiện | Test trạng thái phục hồi, sự kiện giả/lặp/sai thứ tự |
| Tự cho phép khi phụ thuộc lỗi | AUTH-09 | Cổng xác thực và API bảo vệ | Diễn tập lỗi có điều khiển |
| Lộ bí mật trong quan sát | AUTH-10 | Nguồn audit và log liên quan | Schema sự kiện, marker và kiểm tra quyền truy cập |

Đây là kế hoạch bằng chứng, chưa phải kết quả đã kiểm chứng.

### 8.2. Bộ test tối thiểu cho lời giải

| Test ID | Tình huống | Kết quả trọng tâm |
| --- | --- | --- |
| AT-01 | Kết quả hợp lệ, tài khoản hoạt động | Tạo phiên đúng subject và đúng mức |
| AT-02 | Sai nguồn hoặc sai bên nhận | Không tạo phiên |
| AT-03 | Kết quả bị thay đổi hoặc quá hạn | Không tạo phiên, không tin dữ liệu chưa xác minh |
| AT-04 | Cùng email nhưng khác subject | Không tự gộp danh tính |
| AT-05 | Sai hoặc hết hạn giao dịch | Không hoàn tất đăng nhập |
| AT-06 | Hai lần hoàn tất đồng thời | Không tạo nhiều thành công ngoài chính sách |
| AT-07 | Phát lại định danh trước đăng nhập | Không được coi là phiên xác thực |
| AT-08 | Đúng ngưỡng idle hoặc absolute | Phiên bị từ chối theo mốc máy chủ |
| AT-09 | Polling nền liên tục | Không làm mới idle nếu nằm ngoài danh sách |
| AT-10 | Logout rồi phát lại ở instance khác | Phiên cũ bị từ chối ở quyết định mới |
| AT-11 | Vô hiệu hóa tài khoản có nhiều phiên | Mọi phiên thuộc phạm vi bị từ chối trong hạn |
| AT-12 | Client tự gửi cờ MFA | Không nâng mức |
| AT-13 | MFA cũ hoặc thuộc phiên khác | Không mở thao tác nhạy cảm |
| AT-14 | MFA thành công nhưng không có quyền | Không thực hiện nghiệp vụ |
| AT-15 | Logout khi MFA đang chờ | Kết quả trở về không làm sống lại phiên |
| AT-16 | Phục hồi và sự kiện lặp/sai thứ tự | Không bỏ qua mức xác thực, thu hồi đúng phạm vi |
| AT-17 | ID-CORP hoặc kho phiên lỗi | Đúng hành vi từ chối hoặc tiếp tục có điều kiện |
| AT-18 | Token tổng hợp trong luồng thành công và lỗi | Không xuất hiện ở nguồn log bị cấm |

Bổ sung test cho từng điểm vào thực tế. Không dùng test một endpoint để kết luận mọi API bảo vệ đã thực thi kiểm tra phiên.

### 8.3. Kiểm thử ở biên thời gian

Với ngưỡng T, thử:

- Trước T, khi mọi điều kiện khác hợp lệ.
- Đúng T.
- Sau T.
- Hoạt động hoặc cập nhật cạnh tranh quanh T.
- Sai lệch đồng hồ và mốc không chắc chắn theo thiết kế.

Đối với thời hạn phiên ở AUTH-04, đúng hạn là hết hiệu lực. Đối với độ mới MFA “không quá 5 phút”, đúng 5 phút vẫn thỏa điều kiện độ mới nếu các điều kiện khác hợp lệ. Cần thể hiện rõ sự khác nhau này trong assertion.

Dùng cơ chế kiểm soát thời gian hoặc đồng hồ thử phù hợp; không cần để test thực sự ngủ 8 giờ.

Khi ghép mốc từ nhiều hệ thống, phải biết sai số và cách đối chiếu. Nếu sai số có thể làm đổi kết luận ở sát biên, kết quả chưa đủ cơ sở để ghi đạt.

## 9. Ví dụ đặc tả một test

### 9.1. Thu hồi sau vô hiệu hóa tài khoản

```gherkin
Feature: Thu hồi phiên khi tài khoản ứng dụng bị vô hiệu hóa

  Scenario: Các phiên cũ không tiếp tục dùng sau thời hạn thu hồi
    Given USER-A có hai phiên ứng dụng hợp lệ
    And USER-B có một phiên hợp lệ không liên quan
    And các phiên đã gọi được API thuộc quyền của mình
    When tài khoản USER-A bị vô hiệu hóa tại nguồn ứng dụng
    And mốc commit được ghi là t0
    Then tại hoặc sau t0 cộng 60 giây
    And mọi quyết định xác thực mới của USER-A trên các instance bị từ chối
    And USER-B vẫn hoạt động theo quyền và thời hạn của mình
    And đăng nhập mới của USER-A không tạo phiên
```

Kịch bản này cần được chuyển thành test thực thi có điều khiển nguồn tài khoản, thời gian và các instance. Viết Gherkin chưa chứng minh hệ thống đã đáp ứng.

### 9.2. Mã giả kiểm tra phiên không sống lại sau MFA

```text
fixture = createValidBasicSessionWithAuthorizedUser()
assert fixture.canPerformOrdinaryAction()

challenge = beginAdditionalAuthentication(fixture.session)
holdBeforeApplyingMfaResult(challenge)

logout = logoutCurrentSession(fixture.session)
assert logout.isConfirmedByAuthoritativeSessionStore()

result = createValidTrustedMfaResultFor(challenge)
resumeAndApplyMfaResult(result)

assert oldSessionRemainsRevoked(fixture.session)
assert sensitiveActionWithOldSessionIsDenied()
assert noBusinessSideEffectFromDeniedAction()
assert auditDistinguishesMfaResultAndRevokedSession()
```

Đây là mã giả, không phải API của một thư viện.

Điểm đồng bộ phải giữ đúng giai đoạn trước khi áp dụng kết quả. Một khoảng sleep ngẫu nhiên không bảo đảm test đã tạo điều kiện cạnh tranh mong muốn.

Nếu môi trường dùng bộ giả lập ID-CORP, phân biệt test logic nghiệp vụ với test tích hợp xác minh thực. Một stub luôn trả “đã xác minh” không chứng minh ứng dụng kiểm tra nguồn, toàn vẹn và ràng buộc đúng.

## 10. Rà soát lời giải bằng câu hỏi cụ thể

### 10.1. Độ rõ

Người triển khai và người kiểm thử có trả lời giống nhau không:

- “Phiên hợp lệ” gồm trạng thái, thời hạn và tài khoản nào?
- Điểm nào quyết định danh tính đã xác thực?
- Hoạt động nào làm mới thời gian nhàn rỗi?
- Logout hiện tại khác thu hồi mọi phiên như thế nào?
- MFA đủ mới đo từ lúc nào?
- Khi nguồn quyền hoặc phiên lỗi, điều gì được phép tiếp tục?

Nếu một từ phải được giải thích miệng mỗi lần, nên đưa định nghĩa vào đặc tả hoặc tham chiếu một phiên bản ổn định.

### 10.2. Tính nhất quán

Kiểm tra các cặp dễ mâu thuẫn:

| Cặp điều kiện | Điều cần tránh |
| --- | --- |
| Logout phải hủy trước xác nhận và kiểm tra phiên dùng cache lâu | Vẫn chấp nhận phiên cũ sau khi đã báo logout thành công |
| Idle 15 phút và polling luôn làm mới | Phiên không bao giờ idle theo ý định sản phẩm |
| Absolute 8 giờ và refresh đặt lại mốc login | Phiên kéo dài vô hạn |
| MFA mới và phiên đã thu hồi | Kết quả MFA khôi phục phiên cũ |
| Vô hiệu hóa tài khoản và ID-CORP còn phiên SSO | Đăng nhập mới bỏ qua trạng thái tài khoản ứng dụng |
| Phục hồi yếu tố và mức MFA cũ | Cổng tự giữ đặc quyền không còn đủ cơ sở |
| Phụ thuộc lỗi và luồng dự phòng | Tự tin dữ liệu client vì không kiểm tra được |

Không để mỗi instance chọn một cách diễn giải khác.

### 10.3. Tính khả thi và phụ thuộc

Trước khi dùng lời giải trong hệ thống thật, cần chốt:

- Giao thức và hồ sơ tích hợp cụ thể của TRUST-01.
- Danh mục phương thức xác thực và bằng chứng mức được chấp nhận.
- Bảo vệ thông tin phiên ở trình duyệt, đường truyền và máy chủ.
- Nguồn quyền, kho phiên, chiến lược đồng bộ và độ trễ.
- Ngữ nghĩa sự kiện phục hồi, mốc cắt và xử lý sai thứ tự.
- Phạm vi thất bại, sai số thời gian và khả năng quan sát.
- Chính sách audit, độ bền, quyền, lưu giữ và lỗi chuyển tiếp.
- Trách nhiệm bảo vệ yếu tố, chống dò và phục hồi tại ID-CORP.
- Những đường API hoặc client khác chưa nằm trong bài tập.

Không thay các quyết định đó bằng từ “chuẩn” hoặc “an toàn”. Nếu chưa có cơ sở, giữ thành vấn đề mở có chủ sở hữu thay vì tuyên bố đã hoàn tất đặc tả triển khai.

## 11. Tiêu chí đánh giá bài thực hành

Có thể chấm mỗi chiều từ 0 đến 2:

- 0: thiếu hoặc có mâu thuẫn lớn.
- 1: đã đề cập nhưng còn mơ hồ hoặc thiếu phạm vi.
- 2: rõ, nhất quán và có cách kiểm chứng.

| Chiều đánh giá | Dấu hiệu đạt 2 điểm |
| --- | --- |
| Phạm vi và nguồn rủi ro | Nêu rõ người dùng, thành phần, giới hạn và rủi ro liên kết |
| Xác lập danh tính | Nguồn tin cậy, subject, giao dịch và chống phát lại được đặc tả |
| Phiên và thu hồi | Idle, absolute, logout, vô hiệu hóa và nhiều instance nhất quán |
| MFA và phục hồi | Không tự nâng mức, có độ mới, ràng buộc và chống sống lại phiên |
| Lỗi và dữ liệu | Không tự cho phép, không lộ bí mật, có trách nhiệm cho phụ thuộc |
| Khả năng kiểm chứng | Có positive, negative, failure, biên thời gian và bằng chứng dự kiến |

Tổng tối đa là 12 điểm. Nếu dùng mốc đạt 10 điểm cho bài tập, vẫn cần các điều kiện bắt buộc:

- Không tin danh tính hoặc mức MFA tự khai từ client.
- Không dùng xác thực thay cho phân quyền.
- Không chấp nhận phiên đã hết hạn hoặc thu hồi.
- Không tự cho phép khi thiếu cơ sở kiểm tra.
- Không tuyên bố đã kiểm chứng các phụ thuộc chưa được kiểm chứng.

Điểm đánh giá phản ánh chất lượng bài đặc tả trong phạm vi bài tập, không phải tỷ lệ an toàn của một hệ thống thực.

## 12. Hồ sơ bàn giao của người học

Một bộ bàn giao gọn có thể gồm các phần trong cùng tài liệu:

1. Bối cảnh, sơ đồ thành phần và ranh giới tin cậy.
2. Bảng thuật ngữ, giả định và giá trị thời gian.
3. Tập yêu cầu AUTH có phiên bản và chủ sở hữu.
4. Bảng rủi ro → yêu cầu → điểm thực thi → test.
5. Các tiêu chí nghiệm thu và dữ liệu tổng hợp cần tạo.
6. Phụ thuộc, vấn đề mở và quyết định cần chốt.
7. Kết quả tự rà soát và kế hoạch lấy bằng chứng khi triển khai.

Không ghi “PASS” chỉ vì đã viết test case. Kết quả thực thi cần được quản lý riêng và gắn với build, cấu hình, môi trường, phiên bản bộ thử và phạm vi quan sát.

Nếu test bị bỏ qua, công cụ lỗi hoặc chưa biết phiên có được kiểm tra ở mọi đường không, phải thể hiện đúng khoảng trống đó.

## 13. Các lỗi cần tránh khi viết requirement cho authentication

| Lỗi | Vì sao chưa đủ | Cách sửa |
| --- | --- | --- |
| “Dùng SSO là an toàn” | Chưa có nguồn, mục đích nhận và ràng buộc giao dịch | Đặc tả TRUST-01 và điểm tạo phiên |
| “Token hợp lệ” | Không rõ hợp lệ theo điều kiện nào | Nêu nguồn, toàn vẹn, thời hạn và phạm vi sử dụng |
| Dùng email làm định danh duy nhất | Có thể liên kết sai nguồn hoặc subject | Chốt khóa danh tính có thẩm quyền |
| Coi có cookie là đã xác thực | Cookie có thể cũ, sửa hoặc không còn hiệu lực | Kiểm tra trạng thái tại máy chủ |
| Chỉ xóa cookie khi logout | Phiên máy chủ có thể còn dùng được | Thu hồi tại nguồn trước xác nhận |
| Chỉ quy định idle | Hoạt động liên tục có thể kéo phiên không giới hạn | Có tuổi tuyệt đối và mốc không bị reset |
| “Admin luôn MFA” nhưng tin cờ client | Chưa có bằng chứng phương thức và độ mới | Dùng kết quả đã xác minh, gắn đúng phiên |
| MFA xong là cho thao tác | Có thể thiếu quyền hoặc phiên đã bị thu hồi | Kiểm tra các điều kiện độc lập |
| Phục hồi được coi là đặc quyền hỗ trợ | Tạo đường đi yếu hơn chính sách | Giữ mức xác thực và hợp đồng thu hồi |
| Đo từ lúc nhận thông báo nhưng hứa đầu-cuối | Bỏ qua độ trễ hoặc mất sự kiện bên ngoài | Tách từng mốc và trách nhiệm |
| Ghi token để dễ debug | Tạo nguồn lộ khả năng truy cập | Dùng tham chiếu, correlation ID và dữ liệu tổng hợp |
| Có bảng yêu cầu là kết luận đã đáp ứng | Chưa có bằng chứng triển khai | Tách trạng thái đặc tả và kết quả kiểm chứng |
