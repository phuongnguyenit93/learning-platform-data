# Audit finding remediation trong hệ thống PAM

## 1. Mục tiêu của bài học

Một audit finding là phát hiện có bằng chứng cho thấy thực tế khác với tiêu chí kiểm soát đã được thống nhất. Trong Privileged Access Management (PAM), finding có thể liên quan đến tài khoản quản trị dùng chung, quyền đặc biệt không được rà soát, credential chưa được luân chuyển, truy cập bỏ qua PAM, hoặc bằng chứng phiên không đủ để truy vết.

Remediation là quá trình xử lý phát hiện đó một cách có trách nhiệm: xác định phạm vi ảnh hưởng, kiểm soát rủi ro đang tồn tại, tìm nguyên nhân, sửa kiểm soát và chứng minh rằng kiểm soát hoạt động. Việc hoàn thành một ticket kỹ thuật chỉ là một phần của quá trình này.

Sau bài học, bạn cần có thể:

- Chuyển một finding thành kế hoạch có người chịu trách nhiệm, thời hạn và tiêu chí nghiệm thu cụ thể.
- Phân biệt sửa lỗi hiện tại, khắc phục nguyên nhân gốc, kiểm soát bù và chấp nhận rủi ro.
- Xây dựng bộ bằng chứng liên kết tài khoản, tài sản, yêu cầu truy cập, credential, phiên và thay đổi cấu hình.
- Kiểm thử cả đường truy cập hợp lệ lẫn khả năng từ chối truy cập không hợp lệ.
- Đóng finding dựa trên kết quả xác minh và theo dõi để phát hiện tái diễn.

Các số liệu, thời hạn và tên chính sách trong bài là ví dụ nội bộ giả định. Khi áp dụng, dùng tiêu chí kiểm soát, phạm vi và thẩm quyền đã được tổ chức phê duyệt.

## 2. Đọc đúng một finding trước khi lập kế hoạch

Một finding có ích phải giúp người xử lý trả lời được năm câu hỏi:

| Thành phần | Câu hỏi cần trả lời | Ví dụ trong PAM |
|---|---|---|
| Tiêu chí | Tổ chức yêu cầu điều gì? | Quản trị từ xa của nhóm máy chủ trong phạm vi phải đi qua đường truy cập được PAM kiểm soát |
| Thực trạng | Đã quan sát thấy điều gì khác yêu cầu? | Một số máy chủ vẫn chấp nhận đăng nhập quản trị trực tiếp từ mạng vận hành |
| Bằng chứng | Dữ liệu nào chứng minh thực trạng? | Cấu hình kết nối, kết quả kiểm thử có phê duyệt và log xác thực tương ứng |
| Phạm vi | Tài sản, tài khoản và khoảng thời gian nào bị ảnh hưởng? | Máy chủ sản xuất thuộc một đơn vị vận hành trong kỳ kiểm tra |
| Rủi ro | Sự khác biệt gây hậu quả gì? | Hoạt động quản trị có thể thiếu phê duyệt, thiếu liên kết với người thực hiện hoặc thiếu giám sát phiên |

Không suy ra mức độ rủi ro chỉ từ cách đặt tên finding. Chẳng hạn, “thiếu bản ghi phiên” có thể là lỗi truy xuất bằng chứng, lỗi thu thập, lỗi lưu trữ hoặc thực tế tồn tại một đường truy cập không đi qua PAM. Các trường hợp này đòi hỏi hành động khác nhau.

Cũng cần phân biệt bằng chứng của một lần kiểm tra với kết luận về toàn bộ phạm vi. Nếu auditor kiểm tra 10 tài khoản và thấy 3 tài khoản không có owner, kết luận chắc chắn là mẫu kiểm tra có 3 trường hợp không đáp ứng. Chưa thể khẳng định toàn bộ tổ chức chỉ có đúng 3 tài khoản như vậy.

Khi tiếp nhận finding:

1. Xác nhận nguyên văn tiêu chí và bản finding đang được dùng.
2. Đối chiếu danh sách bằng chứng, thời gian và định danh đối tượng.
3. Ghi rõ điều đã biết, điều còn thiếu và giả định cần kiểm chứng.
4. Thống nhất điểm chưa rõ với người quản lý cuộc kiểm toán.
5. Bắt đầu kiểm soát rủi ro có thật trong khi việc làm rõ vẫn tiếp tục.

Nếu không đồng ý với finding, phản hồi bằng dữ liệu đối chiếu và lập luận gắn với tiêu chí. Không sửa hoặc xóa dấu vết vận hành để làm cho ảnh chụp hệ thống sau đó trông phù hợp với thời điểm đã được kiểm toán.

## 3. Phân biệt bốn cách xử lý thường bị nhầm lẫn

### 3.1. Correction: sửa tình trạng sai đang nhìn thấy

Ví dụ: loại một tài khoản đã nghỉ việc khỏi nhóm quản trị, gán owner cho tài khoản dịch vụ đang thiếu owner, hoặc sửa một connector không đẩy log.

Correction giúp giảm số trường hợp lỗi hiện tại. Tuy nhiên, nếu quy trình tiếp tục tạo ra tài khoản không có owner thì finding sẽ tái diễn.

### 3.2. Corrective action: xử lý nguyên nhân làm phát sinh lỗi

Ví dụ: sửa quy trình tạo tài khoản dịch vụ để bắt buộc có owner còn hiệu lực, thiết lập đối soát định kỳ và cảnh báo khi owner thay đổi hoặc rời tổ chức.

Corrective action thường kết hợp thay đổi kỹ thuật với thay đổi quy trình. Một trường bắt buộc trong biểu mẫu chưa đủ nếu người dùng vẫn có thể tạo tài khoản theo một đường khác.

### 3.3. Compensating control: kiểm soát bù trong giới hạn xác định

Một hệ thống cũ có thể chưa hỗ trợ tích hợp PAM theo kế hoạch. Trong thời gian chuyển đổi, tổ chức có thể dùng đường mạng giới hạn, phê duyệt từng lần, tài khoản định danh và giám sát tăng cường.

Kiểm soát bù phải nói rõ nó giảm phần rủi ro nào, còn thiếu phần nào, ai vận hành, bằng chứng nào cần lưu và khi nào hết hiệu lực. Nó không tự động tương đương với kiểm soát gốc.

### 3.4. Risk acceptance: chấp nhận phần rủi ro còn lại

Chấp nhận rủi ro là quyết định của người có thẩm quyền đối với rủi ro và tài sản liên quan. Đội PAM không mặc nhiên có quyền tự chấp nhận rủi ro chỉ vì việc tích hợp khó hoặc quá hạn.

Một quyết định có thể được phê duyệt như ngoại lệ có thời hạn, nhưng trạng thái quản lý phải phân biệt rõ với “đã khắc phục”. Nếu quy trình cho phép đóng finding bằng quyết định chấp nhận rủi ro, hồ sơ phải ghi đúng lý do đóng và tham chiếu ngoại lệ đang được theo dõi.

| Hành động | Giá trị chính | Điều chưa chứng minh |
|---|---|---|
| Xóa quyền sai khỏi các tài khoản đã biết | Sửa các trường hợp hiện tại | Quyền sai không tiếp tục được cấp |
| Sửa quy trình cấp quyền và đối soát | Giảm khả năng tái diễn | Kiểm soát đã vận hành hiệu quả trong thực tế |
| Áp dụng giám sát thủ công tạm thời | Giảm một phần rủi ro trong thời gian chờ | Đã đạt đầy đủ yêu cầu kiểm soát gốc |
| Phê duyệt chấp nhận rủi ro | Ghi nhận quyết định có thẩm quyền | Hệ thống đã được sửa về mặt kỹ thuật |

## 4. Tổ chức vòng đời remediation có thể kiểm soát

Có thể quản lý finding bằng chuỗi trạng thái sau:

```text
Đã tiếp nhận
    -> Đã xác nhận phạm vi và rủi ro
    -> Đã phê duyệt kế hoạch
    -> Đang triển khai
    -> Chờ xác minh
    -> Đã đóng theo kết quả được phê duyệt

Tại mỗi bước:
    thiếu bằng chứng / kiểm thử không đạt / sai phạm vi
        -> trả về bước xử lý phù hợp và giữ lịch sử

Sau khi đóng:
    phát hiện tái diễn
        -> đánh giá mở lại hoặc tạo finding liên quan
```

Giữ nguyên bản finding ban đầu và ghi các lần cập nhật thành lịch sử. Nếu phạm vi mở rộng từ một cụm máy chủ sang nhiều cụm, cần thể hiện sự thay đổi đó thay vì âm thầm sửa mô tả ban đầu.

Một mô hình trách nhiệm tối thiểu gồm:

- **Finding owner:** chịu trách nhiệm đưa finding đến kết quả cuối cùng, điều phối phụ thuộc và báo cáo chậm tiến độ.
- **Control owner:** chịu trách nhiệm thiết kế và vận hành kiểm soát liên quan.
- **Action owner:** thực hiện một hành động cụ thể, ví dụ sửa connector, thay đổi nhóm quyền hoặc cập nhật luồng phê duyệt.
- **Risk owner:** quyết định đối với rủi ro còn lại trong thẩm quyền của mình.
- **Validator:** xác minh kết quả theo quy trình và mức độ độc lập được yêu cầu.
- **Người có thẩm quyền đóng:** phê duyệt kết quả cuối cùng theo quy trình quản lý finding.

Các vai trò có thể do cùng một đơn vị phối hợp thực hiện, nhưng không nên để một người tự triển khai rồi tự xác nhận độc lập công việc của mình. Đơn vị kiểm toán có thể xem xét hoặc retest theo thỏa thuận cuộc kiểm toán; trách nhiệm sửa kiểm soát vẫn thuộc phía quản lý và vận hành.

## 5. Xác định phạm vi và ưu tiên theo rủi ro

### 5.1. Xác định population trước khi đếm lỗi

Population là tập đối tượng thuộc tiêu chí kiểm tra. Với PAM, nó có thể là tất cả máy chủ sản xuất, tất cả tài khoản đặc quyền tương tác, hoặc tất cả credential dịch vụ trong một miền quản lý.

Cần định nghĩa ít nhất:

- Loại tài sản và môi trường: sản xuất, kiểm thử, cloud, thiết bị mạng hoặc hệ điều hành.
- Loại danh tính: người dùng, tài khoản dùng chung, dịch vụ, workload hoặc break-glass.
- Loại quyền: quyền quản trị hệ điều hành, quyền cơ sở dữ liệu, quyền quản lý vault hoặc quyền quản trị nền tảng PAM.
- Đường truy cập: broker, jump host, kết nối trực tiếp, API hoặc công cụ tự động hóa.
- Mốc thời gian: thời điểm chụp danh sách và khoảng thời gian cần kiểm tra.
- Trường hợp được loại trừ: lý do, thẩm quyền và bằng chứng cho từng nhóm loại trừ.

Không dùng danh sách “đã onboard PAM” làm population duy nhất cho finding về “tài sản chưa được onboard”. Cách lấy dữ liệu đó loại chính các đối tượng đang cần tìm khỏi phép kiểm tra.

Có thể đối chiếu inventory tài sản, danh mục tài khoản, cấu hình quyền và dữ liệu truy cập. Nếu các nguồn không khớp, chênh lệch là đầu việc cần xử lý; không tùy ý chọn nguồn tạo ra kết quả đẹp hơn.

### 5.2. Ưu tiên dựa trên khả năng và hậu quả

Các yếu tố thường cần xem xét gồm:

- Mức nhạy cảm của dữ liệu và tài sản mà quyền truy cập có thể tác động.
- Quyền có thường trực hay chỉ được cấp trong một khoảng thời gian ngắn.
- Khả năng truy cập từ các vùng mạng khác nhau.
- Khả năng quy trách nhiệm cho một người hoặc workload cụ thể.
- Khả năng thu hồi credential, token, phiên và quyền đã cấp.
- Độ tin cậy của log, cảnh báo và bằng chứng.
- Quy mô đối tượng bị ảnh hưởng và thời gian tình trạng đã tồn tại.
- Những kiểm soát khác đang thực sự hoạt động.

Việc chưa nhìn thấy sự cố không chứng minh rủi ro thấp. Ngược lại, thiếu log cũng không đủ để kết luận chắc chắn đã có truy cập trái phép.

Nếu xuất hiện dấu hiệu compromise, cần kích hoạt quy trình ứng phó sự cố tương ứng và bảo toàn bằng chứng. Ticket remediation không thay thế quy trình điều tra và xử lý sự cố.

## 6. Giảm rủi ro trước mắt mà không làm mất khả năng vận hành

Một finding nghiêm trọng có thể cần containment trước khi kế hoạch dài hạn hoàn tất. Ví dụ:

- Thu hồi quyền của tài khoản đã xác nhận không còn nhu cầu.
- Hạn chế nguồn kết nối đến tài sản đang cho phép truy cập quản trị trực tiếp.
- Yêu cầu phê duyệt và theo dõi bổ sung đối với một nhóm thao tác nhạy cảm.
- Tạm ngừng luồng cấp quyền tự động đang gán sai nhóm quyền.
- Luân chuyển credential có bằng chứng bị lộ theo quy trình đã được phê duyệt.
- Tăng cường đối soát và rà soát phiên đối với các tài sản chưa thể tích hợp ngay.

Trước mỗi thay đổi, xác định tác động đến dịch vụ, chủ sở hữu phụ thuộc, cửa sổ thực hiện, cách kiểm tra và phương án phục hồi. Khóa đồng loạt tài khoản dịch vụ hoặc đổi credential mà chưa cập nhật consumer có thể gây gián đoạn và dẫn đến việc người vận hành mở lại quyền bằng đường tắt.

Ví dụ, phát hiện một ứng dụng còn dùng mật khẩu tĩnh được nhiều người biết. Luân chuyển mật khẩu là hành động cần thiết trong một số tình huống, nhưng kế hoạch phải bao gồm:

1. Kiểm kê consumer và xác định ai đang sử dụng credential.
2. Bảo đảm ứng dụng lấy được credential thay thế qua cơ chế được phê duyệt.
3. Kiểm tra hành vi cập nhật và phục hồi khi có lỗi.
4. Thực hiện chuyển đổi và xác nhận consumer hoạt động.
5. Xác nhận credential cũ không còn được chấp nhận ở các đích liên quan.
6. Theo dõi lỗi xác thực và các đường sử dụng còn sót.

Một lần rotation thành công chưa chứng minh toàn bộ secret copy, token đã phát hành hoặc phiên đang tồn tại đã mất hiệu lực. Các cơ chế này cần được kiểm tra theo hành vi thực tế của hệ thống.

Ghi containment thành hành động có thời hạn và bằng chứng riêng. Finding tiếp tục được theo dõi cho đến khi đạt điều kiện đóng đã thống nhất.

## 7. Phân tích nguyên nhân gốc trong môi trường PAM

Một kết luận như “nhân viên quên thực hiện” mô tả hành vi gần sự kiện, nhưng thường chưa giải thích được tại sao hệ thống cho phép lỗi tồn tại mà không bị phát hiện.

Phân tích nguyên nhân cần xem nhiều lớp:

| Lớp | Câu hỏi phân tích | Ví dụ nguyên nhân |
|---|---|---|
| Thiết kế | Kiểm soát có bao phủ đường truy cập thực tế không? | Quy trình chỉ xét SSH tương tác, bỏ sót API quản trị |
| Thực thi kỹ thuật | Cấu hình có thực hiện được ý định kiểm soát không? | Network policy còn cho phép nguồn kết nối cũ |
| Quy trình | Các bước có rõ, có điều kiện chặn và có người nhận trách nhiệm không? | Không ai đối soát tài sản mới với danh sách PAM |
| Dữ liệu | Inventory, owner và mức quyền có đáng tin cậy không? | Tài sản đổi đơn vị nhưng owner không được cập nhật |
| Vận hành | Kiểm soát có tiếp tục hoạt động sau triển khai không? | Connector lỗi nhiều ngày mà không có người xử lý |
| Thay đổi | Tại sao cấu hình sai được đưa vào môi trường? | Mẫu triển khai máy chủ không chứa cấu hình bắt buộc |
| Phát hiện | Tại sao lỗi không được cảnh báo sớm hơn? | Báo cáo chỉ đếm tài khoản được quản lý, không tìm tài khoản ngoài phạm vi vault |

### Ví dụ chuỗi nguyên nhân

Finding: tài khoản dịch vụ trên một nhóm máy chủ có quyền cao nhưng không có owner xác thực được.

```text
Không xác định được người chịu trách nhiệm tài khoản
    -> trường owner chứa tên đội cũ
    -> quy trình chuyển giao hệ thống không cập nhật danh mục
    -> không có bước đối soát sau chuyển giao
    -> kiểm soát chỉ yêu cầu owner tại thời điểm tạo tài khoản
```

Kế hoạch chỉ điền lại tên owner cho các tài khoản hiện có là correction. Để xử lý nguyên nhân, có thể cần thêm sự kiện chuyển giao vào quy trình, xác nhận trách nhiệm mới và cơ chế phát hiện owner không còn hợp lệ.

Không dùng chuỗi suy luận thay cho bằng chứng. Mỗi giả thuyết cần được kiểm tra bằng hồ sơ thay đổi, cấu hình, luồng tạo tài khoản, lịch sử vận hành hoặc dữ liệu phù hợp. Một finding cũng có thể có nhiều nguyên nhân cùng tồn tại.

## 8. Chuyển finding thành kế hoạch hành động có thể nghiệm thu

Một hành động tốt nêu rõ kết quả cần đạt, đối tượng cần tác động, người chịu trách nhiệm, ngày dự kiến và bằng chứng chứng minh kết quả.

So sánh:

> Cải thiện việc quản lý quyền admin.

với:

> Đối soát toàn bộ tài khoản quản trị tương tác trong phạm vi máy chủ sản xuất đã được xác định; xử lý từng tài khoản không có owner hoặc nhu cầu được phê duyệt; thực hiện kiểm thử đường cấp quyền và thu hồi; lưu danh sách đối soát cùng bằng chứng xác minh.

Cách viết thứ hai vẫn cần được cụ thể hóa thành các action riêng để quản lý phụ thuộc và ngày hoàn tất.

Một mẫu hồ sơ giả định:

```yaml
findingId: PAM-F-027
title: Duong quan tri truc tiep chua duoc kiem soat day du
scope:
  populationRef: POP-PAM-027-v2
  environment: production
  capturedAt: "2026-04-03T09:00:00Z"
findingOwner: role-platform-operations-lead
controlOwner: role-pam-control-owner
status: IN_PROGRESS
actions:
  - id: A1
    outcome: Chot population va xu ly chenh lech inventory
    owner: role-asset-management
    dueDate: "2026-04-08"
    evidenceRefs:
      - EV-027-POPULATION
  - id: A2
    outcome: Gioi han duong quan tri theo thiet ke da phe duyet
    owner: role-platform-network
    dependsOn:
      - A1
    dueDate: "2026-04-15"
    evidenceRefs:
      - EV-027-CHANGE
  - id: A3
    outcome: Xac minh truy cap hop le va thu tu choi duong bypass
    owner: role-control-validation
    dependsOn:
      - A2
    dueDate: "2026-04-18"
    evidenceRefs:
      - EV-027-RETEST
closure:
  criteriaRef: CR-PAM-027-v1
  validationStatus: NOT_STARTED
  approvalRef: null
```

Đây là cấu trúc minh họa cho việc quản lý finding, không phải schema bắt buộc của một sản phẩm. Không đưa password, private key, token hoặc đường dẫn chứa credential vào hồ sơ.

Kế hoạch cũng cần chứa chi phí hoặc nguồn lực có ảnh hưởng thực tế, phụ thuộc vào đơn vị khác, điều kiện rollback và những rủi ro phát sinh trong lúc chuyển đổi. Nếu phụ thuộc đang chậm, finding owner phải quản lý phụ thuộc đó; việc gắn nhãn “đợi vendor” không làm cho rủi ro biến mất.

## 9. Định nghĩa tiêu chí đóng trước khi triển khai

Tiêu chí đóng nên được thống nhất sớm để tránh tình trạng đội triển khai cho rằng đã xong nhưng người xác minh không có cơ sở chấp nhận.

Một bộ tiêu chí thường bao gồm bốn tầng:

### 9.1. Phạm vi được giải quyết

Tất cả đối tượng thuộc population đã được đối soát. Với mỗi đối tượng, hồ sơ chỉ rõ đã đáp ứng, đã loại bỏ, đã chuyển khỏi phạm vi với lý do hợp lệ, hoặc đang có ngoại lệ được phê duyệt.

Không gộp các trường hợp ngoại lệ vào số “đã khắc phục” khi báo cáo. Nếu chúng được phép tồn tại, phải trình bày riêng trạng thái và phần rủi ro còn lại.

### 9.2. Thiết kế kiểm soát đáp ứng tiêu chí

Mô tả kiểm soát và cấu hình phải giải thích cách kiểm soát ngăn chặn, phát hiện hoặc xử lý rủi ro. Ví dụ, “bật PAM” chưa cho biết đường trực tiếp có bị chặn hay không.

### 9.3. Kiểm soát được thực thi và vận hành

Cần có bằng chứng đã triển khai và kiểm thử. Với kiểm soát định kỳ, cần kiểm tra nó thực sự chạy trong khoảng thời gian phù hợp với yêu cầu và rủi ro.

Một ảnh cấu hình không chứng minh kiểm soát đã hoạt động liên tục. Ngược lại, một log thành công cũng không chứng minh cấu hình đã bao phủ đủ population.

### 9.4. Kết quả được xác minh và phê duyệt

Người xác minh đối chiếu tiêu chí, dữ liệu và kết quả retest; ghi rõ giới hạn của phép kiểm tra. Người có thẩm quyền phê duyệt đóng hoặc yêu cầu xử lý tiếp theo quy trình.

Không có một số ngày quan sát hay một cỡ mẫu chung đúng cho mọi finding. Thời gian và cách kiểm tra phải được xác định theo tần suất kiểm soát, mức rủi ro, loại thay đổi và yêu cầu cuộc kiểm toán.

## 10. Xây dựng bằng chứng có thể truy vết

Bộ bằng chứng tốt cho phép người khác dựng lại được: đã kiểm tra đối tượng nào, vào thời điểm nào, theo tiêu chí nào và vì sao kết luận hợp lý.

### 10.1. Liên kết các mắt xích

Một chuỗi thường gặp trong PAM:

```text
Định danh người hoặc workload
    -> yêu cầu truy cập và phê duyệt
    -> quyền được cấp / credential được sử dụng
    -> tài sản đích và phiên truy cập
    -> thao tác hoặc sự kiện có thể quan sát
    -> hết hạn / thu hồi / kết thúc phiên
```

Không phải sản phẩm nào cũng có cùng trường dữ liệu. Cần xác định các khóa liên kết thực tế, ví dụ request ID, account ID, asset ID, session ID và change ID.

Nếu không thể liên kết một phiên đặc quyền với người yêu cầu do tài khoản dùng chung, đó là giới hạn phải được ghi nhận. Không suy diễn danh tính người thao tác chỉ từ một tên tài khoản kỹ thuật.

### 10.2. Các loại bằng chứng cần cân nhắc

| Loại bằng chứng | Vai trò | Giới hạn cần lưu ý |
|---|---|---|
| Danh sách population và kết quả đối soát | Chứng minh phạm vi đã kiểm tra | Có thể thiếu tài sản nếu nguồn đầu vào không đầy đủ |
| Bản ghi cấu hình và thay đổi | Chứng minh thiết kế đã được triển khai | Không tự chứng minh kiểm soát vận hành hiệu quả |
| Yêu cầu và phê duyệt truy cập | Chứng minh thẩm quyền và mục đích | Không chứng minh quyền được thu hồi đúng lúc |
| Log cấp, sử dụng và thu hồi quyền | Chứng minh các sự kiện liên quan | Cần kiểm tra tính đầy đủ và đồng bộ thời gian |
| Kết quả kiểm thử có bước và điều kiện rõ | Chứng minh hành vi đã quan sát | Chỉ có giá trị trong phạm vi và điều kiện kiểm thử |
| Hồ sơ rà soát định kỳ | Chứng minh kiểm soát được thực hiện theo lịch | Cần có xử lý đối với chênh lệch đã phát hiện |
| Phê duyệt ngoại lệ | Chứng minh quyết định có thẩm quyền | Không chứng minh rủi ro đã được loại bỏ |

### 10.3. Ghi metadata để người khác hiểu bằng chứng

Với từng evidence item, nên lưu:

- Mã bằng chứng và finding/action liên quan.
- Nguồn, cách truy xuất và bộ lọc đã sử dụng.
- Thời gian thu thập, khoảng thời gian dữ liệu và múi giờ.
- Định danh đối tượng hoặc cách giả danh nhất quán.
- Người thu thập và vị trí lưu được kiểm soát.
- Phạm vi dữ liệu bị che hoặc bị loại bỏ.
- Kết quả mà evidence item hỗ trợ và giới hạn của nó.

Nếu dùng checksum để kiểm tra file không bị thay đổi, cần hiểu rằng checksum chỉ hỗ trợ kiểm tra tính toàn vẹn của bản file đã thu. Nó không chứng minh nội dung nguồn là chính xác hay dữ liệu đã đầy đủ.

### 10.4. Bảo vệ bằng chứng như dữ liệu nhạy cảm

Log và bản ghi phiên có thể chứa tên người dùng, dữ liệu nghiệp vụ hoặc thông tin hệ thống. Bằng chứng kiểm toán không nên trở thành một kho secret mới.

Chỉ cho người có nhu cầu truy cập; che dữ liệu nhạy cảm trên bản dùng cho rà soát; giữ bản gốc ở nơi được kiểm soát khi cần. Áp dụng thời hạn lưu trữ và quy trình xử lý dữ liệu của tổ chức, bao gồm yêu cầu bảo toàn phục vụ điều tra nếu có.

Không đính kèm trực tiếp private key hoặc mật khẩu để “chứng minh tài khoản hoạt động”. Không chỉnh sửa bản gốc của log mà không lưu dấu vết và giải thích. Khi cần trích xuất đã che dữ liệu, giữ liên kết với nguồn và ghi rõ cách biến đổi.

## 11. Retest: kiểm thử kết quả khắc phục

Retest phải xuất phát từ tiêu chí và nguyên nhân finding, không chỉ lặp lại thao tác mà đội triển khai đã thực hiện.

### 11.1. Kiểm tra thiết kế và triển khai

Người xác minh xem:

- Phạm vi cấu hình có khớp population đã thống nhất.
- Các đường cấp quyền và đường truy cập có được bao phủ.
- Quy trình có xác định owner và điều kiện phê duyệt.
- Các tài khoản khẩn cấp và dịch vụ có cách xử lý riêng phù hợp.
- Hệ thống có quan sát được trạng thái lỗi của chính kiểm soát.
- Thay đổi có được triển khai theo hồ sơ được phê duyệt.

### 11.2. Kiểm tra hành vi thành công và hành vi bị từ chối

Ví dụ finding về truy cập quản trị trực tiếp:

| Tình huống | Kết quả cần quan sát |
|---|---|
| Người có thẩm quyền yêu cầu truy cập qua luồng PAM hợp lệ | Quyền hoặc phiên được cấp đúng tài sản, phạm vi và thời hạn |
| Yêu cầu thiếu điều kiện phê duyệt cần thiết | Không được cấp quyền theo đường được kiểm tra |
| Kết nối quản trị qua đường trực tiếp nằm trong phạm vi cấm | Bị từ chối; có bằng chứng ở lớp kiểm soát phù hợp |
| Quyền JIT đã hết hạn | Không mở được phiên mới bằng quyền đã hết hạn |
| Quyền được thu hồi trong một phiên đang tồn tại | Hành vi được kiểm tra riêng và khớp thiết kế thu hồi phiên |
| Connector hoặc đường ghi nhận log gặp lỗi | Có cảnh báo và xử lý theo thiết kế đã thống nhất |

Đặc biệt, hết hạn quyền tạo phiên mới không tự động đồng nghĩa với việc phiên đang chạy đã bị kết thúc. Nếu finding yêu cầu thu hồi truy cập đang tồn tại, phải xác minh hành vi đó riêng.

Đối với cơ chế JEA hoặc quyền theo lệnh, cần kiểm tra phạm vi thao tác được cho phép và điều kiện từ chối các thao tác ngoài phạm vi. Không chỉ xác nhận rằng người dùng “đăng nhập được”.

Các phép thử phải có thẩm quyền và nằm trong kế hoạch thay đổi hoặc kiểm thử. Ưu tiên môi trường kiểm thử tương đương để xác nhận hành vi; nếu cần kiểm tra sản xuất, dùng cách được phê duyệt, ít tác động, có giám sát và phương án dừng. Không tự tạo đường bypass hoặc thử lệnh phá hủy để làm bằng chứng.

### 11.3. Kiểm tra tính hiệu quả trong vận hành

Sau triển khai, kiểm tra dữ liệu vận hành thực tế phù hợp với kiểm soát:

- Yêu cầu truy cập được xử lý theo tiêu chí đã định.
- Quyền cấp có thời hạn và phạm vi đúng.
- Tài sản mới được đưa vào quy trình.
- Cảnh báo có người tiếp nhận và được xử lý.
- Các chênh lệch trong rà soát được theo dõi đến kết quả.
- Những ngoại lệ hết hạn không tiếp tục được sử dụng âm thầm.

Nếu finding về rà soát quyền theo chu kỳ, việc sửa biểu mẫu hôm nay chưa chứng minh một kỳ rà soát đã được thực hiện. Có thể ghi nhận phần triển khai đã xong trong khi phần xác minh vận hành còn chờ.

### 11.4. Lấy mẫu mà không làm sai kết luận

Khi không thể kiểm tra mọi giao dịch, ghi rõ cách chọn mẫu, population nguồn, khoảng thời gian, loại trường hợp và lý do chọn. Các tình huống rủi ro cao hoặc khác biệt về kỹ thuật nên được cân nhắc riêng.

Không để đội thực hiện chỉ đưa ra vài phiên thành công dễ tìm rồi gọi đó là toàn bộ retest. Cũng không dùng một kết quả đạt trên hệ điều hành này để kết luận cho một nền tảng khác mà chưa có cơ sở tương đương.

Nếu mẫu phát hiện lỗi, đánh giá mở rộng kiểm tra và phạm vi ảnh hưởng. Không xóa trường hợp lỗi khỏi mẫu rồi tính lại tỷ lệ đạt.

## 12. Tình huống xuyên suốt: đường quản trị bỏ qua PAM

### 12.1. Thực trạng ban đầu

Một đơn vị vận hành có 84 máy chủ thuộc phạm vi quản trị từ xa. Trong ví dụ này, cuộc đối soát xác nhận 17 máy chủ vẫn có ít nhất một đường quản trị trực tiếp không đáp ứng tiêu chí nội bộ.

17 máy chủ là số tài sản bị ảnh hưởng, không phải số tài khoản. Một máy chủ có thể có nhiều tài khoản và nhiều đường truy cập. Hồ sơ cần giữ cả hai mức chi tiết để tránh báo cáo thiếu.

Kiểm tra bổ sung cho thấy có máy chủ dùng mẫu network policy cũ, có máy chủ mới chưa vào luồng onboard và một số đường khẩn cấp chưa được phân loại đúng. Vì nguyên nhân khác nhau, một thay đổi duy nhất sẽ không giải quyết toàn bộ finding.

### 12.2. Containment và phân tích

Đội vận hành xác nhận các phụ thuộc quan trọng trước khi hạn chế nguồn kết nối. Những đường đang có rủi ro được áp dụng giám sát tăng cường và phê duyệt bổ sung trong thời gian xử lý.

Finding owner chốt population có phiên bản và đối chiếu 84 máy chủ với inventory, cấu hình mạng và danh mục PAM. Các tài sản không khớp giữa nguồn dữ liệu được đưa vào danh sách xử lý, không bị bỏ khỏi mẫu số.

Phân tích nguyên nhân chỉ ra:

- Mẫu triển khai cũ còn được dùng.
- Quy trình tạo máy chủ chưa có điểm kiểm tra PAM trước bàn giao.
- Chưa có kiểm tra định kỳ đường truy cập quản trị ngoài PAM.
- Quy trình break-glass chưa mô tả rõ đường truy cập và bằng chứng cần lưu.

### 12.3. Kế hoạch xử lý

Đội phụ trách chia kế hoạch thành các hành động:

1. Sửa mẫu cấu hình và triển khai có kiểm soát tới các máy chủ bị ảnh hưởng.
2. Hoàn thiện luồng onboard cho tài sản mới.
3. Kiểm tra lại tài khoản, owner và phạm vi quyền trên các máy chủ liên quan.
4. Thiết kế và xác minh đường break-glass riêng, có phê duyệt và giám sát phù hợp.
5. Thiết lập đối soát phát hiện tài sản hoặc đường truy cập mới chưa được quản lý.
6. Retest độc lập theo tiêu chí đã thống nhất.

Mỗi hành động có action owner và ngày hoàn tất. Việc cập nhật quy trình được gắn với kiểm tra thực thi, không chỉ với một văn bản đã ký.

### 12.4. Xác minh và quyết định đóng

Người xác minh đối chiếu kết quả trên toàn population, kiểm tra các nhóm cấu hình khác nhau và thực hiện các phép thử đã được phê duyệt. Bằng chứng chỉ rõ đường quản trị hợp lệ hoạt động, đường trực tiếp bị cấm bị chặn và đường khẩn cấp được xử lý theo thiết kế.

Nếu còn 2 máy chủ đang chờ nâng cấp, báo cáo phải thể hiện rõ chúng đang có ngoại lệ hay vẫn chưa đáp ứng. Không trình bày “82/84 đã xử lý” như “finding đã được khắc phục hoàn toàn”.

Khi tất cả điều kiện đã thống nhất được đáp ứng, hồ sơ đóng tham chiếu:

- Population cuối cùng và cách đối soát.
- Các thay đổi đã triển khai.
- Kết quả retest và giới hạn phép kiểm tra.
- Bằng chứng kiểm soát vận hành.
- Các ngoại lệ hợp lệ còn tồn tại, nếu quy trình cho phép.
- Người xác minh và người phê duyệt kết quả.

Sau đó, kiểm tra drift vẫn tiếp tục để phát hiện mẫu cấu hình cũ hoặc đường truy cập không phù hợp xuất hiện trở lại.

## 13. Quản lý quá hạn, ngoại lệ và phần rủi ro còn lại

Finding quá hạn cần được xử lý như một quyết định quản lý rủi ro, không chỉ là vấn đề cập nhật ngày trong công cụ.

Khi thấy nguy cơ trễ:

1. Nêu hành động nào bị trễ và nguyên nhân có bằng chứng.
2. Đánh giá lại rủi ro trong khoảng thời gian kéo dài.
3. Xác định kiểm soát bù đang thực hiện được đến đâu.
4. Đề xuất lịch mới, các mốc trung gian và người chịu trách nhiệm.
5. Xin phê duyệt của người có thẩm quyền theo quy trình.
6. Giữ ngày ban đầu và lịch sử thay đổi để báo cáo trung thực.

Một ngoại lệ có ích cần ghi rõ đối tượng, lý do, rủi ro còn lại, kiểm soát bù, người vận hành, ngày hết hạn và điều kiện thu hồi. Đến ngày hết hạn phải có hành động: khắc phục, ngừng sử dụng, hoặc đánh giá lại và phê duyệt mới theo thẩm quyền.

Không tự động gia hạn ngoại lệ chỉ vì hệ thống vẫn hoạt động. Cũng không áp dụng một ngoại lệ của tài sản A cho tài sản B chỉ vì hai tài sản cùng nhà cung cấp.

Nếu tiến độ phụ thuộc vendor, hồ sơ vẫn cần phần việc mà tổ chức kiểm soát được: quản lý đường truy cập, theo dõi sử dụng, kiểm tra quyền, xác minh thông tin cập nhật và chuẩn bị phương án thay thế.

## 14. Chỉ số theo dõi tiến độ và chất lượng remediation

Số finding đóng trong tháng giúp thấy khối lượng công việc nhưng không đủ phản ánh hiệu quả. Một nhóm có thể đóng nhiều finding đơn giản trong khi finding có rủi ro lớn vẫn tồn tại.

Có thể theo dõi các chỉ số sau:

| Chỉ số | Ý nghĩa | Cách đọc cẩn thận |
|---|---|---|
| Finding đang mở theo mức rủi ro | Thể hiện mức tồn đọng | Mức rủi ro cần được đánh giá nhất quán |
| Tuổi finding và số ngày quá hạn | Thể hiện thời gian rủi ro tồn tại | Giữ được hạn gốc và lịch gia hạn |
| Tỷ lệ retest đạt lần đầu | Phản ánh chất lượng triển khai và bằng chứng | Cần tiêu chí retest ổn định |
| Tỷ lệ finding bị mở lại | Gợi ý hiệu quả đóng và chống tái diễn | Phải phân biệt tái diễn với finding mới khác phạm vi |
| Phạm vi đã xử lý trên population | Cho biết độ bao phủ thực tế | Chốt phiên bản và mẫu số khi tính |
| Ngoại lệ sắp hết hạn và đã hết hạn | Phản ánh việc quản lý rủi ro còn lại | Không trộn vào số đã remediation |
| Tài sản mới chưa đáp ứng sau bàn giao | Đo khả năng ngăn lỗi mới | Cần đối chiếu từ nguồn inventory độc lập |

Ví dụ tỷ lệ bao phủ:

```text
Tỷ lệ đối tượng đáp ứng
    = số đối tượng đã được xác minh đáp ứng
      / tổng đối tượng thuộc population đã xác nhận
```

Nếu population tăng do phát hiện thêm tài sản, tỷ lệ có thể giảm dù đội vẫn đang xử lý. Cần giải thích thay đổi mẫu số thay vì chỉ báo một phần trăm đơn lẻ.

Không đặt mục tiêu “không còn finding mở” theo cách khiến nhóm che giấu chênh lệch hoặc hạ mức rủi ro. Mục tiêu là xử lý rủi ro và duy trì kiểm soát có thể chứng minh.

## 15. Các lỗi thường làm finding tái diễn

### Đóng ticket sau khi đổi cấu hình

Đổi cấu hình mới chứng minh một hành động đã được thực hiện. Cần kiểm tra phạm vi, hành vi và bằng chứng vận hành theo tiêu chí đóng.

### Chỉ sửa các tài khoản trong mẫu audit

Cách này xử lý các trường hợp đã thấy nhưng có thể bỏ sót phần population còn lại. Cần đánh giá phạm vi toàn bộ tiêu chí, rồi áp dụng cách kiểm tra phù hợp.

### Xem đào tạo là hành động duy nhất

Đào tạo có thể cần thiết, nhưng nếu đường cấp quyền vẫn không có điều kiện chặn hoặc đối soát thì lỗi có thể tiếp tục. Hành động phải gắn với nguyên nhân đã xác minh.

### Chấp nhận rủi ro bằng bình luận trong ticket

Một câu “đồng ý tạm thời” không thay thế quyết định có thẩm quyền nếu thiếu đối tượng, thời hạn, rủi ro còn lại và trách nhiệm vận hành.

### Thu thập ảnh chụp không có định danh và thời gian

Người xem không thể biết ảnh thuộc tài sản nào, cấu hình nào và khoảng thời gian nào. Bổ sung metadata và dữ liệu đối chiếu thay vì tăng số lượng ảnh.

### Giữ nguyên đường bypass sau khi PAM hoạt động

PAM có thể quản lý một đường truy cập trong khi đường khác vẫn cho phép quyền tương đương. Kiểm tra phải bao phủ các đường có liên quan đến finding.

### Không kiểm tra consumer sau rotation

Credential có thể đã đổi trong vault nhưng ứng dụng vẫn dùng bản cũ, dùng fallback hoặc dừng hoạt động. Cần xác minh cả việc sử dụng credential mới và xử lý credential cũ theo thiết kế.

### Không theo dõi sau khi đóng

Một mẫu triển khai cũ, thay đổi nhân sự hoặc connector ngừng hoạt động có thể làm lỗi quay lại. Cần gắn kiểm soát với vận hành liên tục và quản lý thay đổi.

## 16. Bài tập thực hành

### Bối cảnh

Một cuộc kiểm tra phát hiện tài khoản dịch vụ có quyền quản trị trên 6 hệ thống. Trong đó, 2 tài khoản không có owner xác thực được, 3 tài khoản chưa có bằng chứng rà soát quyền trong kỳ và 1 tài khoản vẫn được sử dụng bằng secret lưu ngoài vault.

Các nhóm lỗi có thể chồng lấn; chưa có dữ liệu xác nhận 6 hệ thống là toàn bộ population. Chưa phát hiện dấu hiệu compromise.

### Yêu cầu

1. Nêu những dữ liệu cần thu thập để xác định population và mức ảnh hưởng.
2. Đề xuất các hành động containment có cân nhắc tác động đến consumer.
3. Xây dựng ít nhất ba giả thuyết nguyên nhân gốc và cách xác minh từng giả thuyết.
4. Viết kế hoạch có action owner, kết quả cần đạt, thời hạn và phụ thuộc.
5. Định nghĩa bằng chứng và tiêu chí retest cho từng nhóm lỗi.
6. Nêu cách xử lý nếu một hệ thống chưa thể tích hợp vault đúng hạn.
7. Xác định chỉ số sau đóng giúp phát hiện lỗi tái diễn.

### Gợi ý tự kiểm tra

Một phương án phù hợp cần nhận ra rằng số lỗi chưa phải số tài khoản duy nhất nếu các nhóm chồng lấn. Nó cũng cần phân biệt owner có tên trên danh sách với owner thực sự xác nhận trách nhiệm.

Với secret ngoài vault, kế hoạch cần hiểu consumer, cơ chế phân phối và khả năng thu hồi trước khi thay đổi. Với rà soát quyền, kế hoạch cần có kết quả đánh giá và xử lý chênh lệch, không chỉ bổ sung một ngày rà soát.

Nếu phải dùng ngoại lệ, hãy mô tả phần rủi ro còn lại và kiểm soát bù có thể kiểm chứng. Không đánh dấu remediation hoàn tất chỉ vì ngoại lệ đã được tạo.

## 17. Điểm cần ghi nhớ

Audit finding remediation trong PAM kết nối quản lý rủi ro với các thay đổi cụ thể trên danh tính, quyền truy cập, credential, tài sản và phiên. Một hồ sơ có thể đóng khi kết quả đã đáp ứng tiêu chí được thống nhất và được xác minh theo đúng thẩm quyền.

Để làm được điều đó, cần duy trì chuỗi liên kết từ finding đến population, nguyên nhân, hành động, thay đổi, kiểm thử và bằng chứng. Correction giải quyết các trường hợp hiện tại; corrective action giúp lỗi không tiếp tục phát sinh; kiểm soát bù và chấp nhận rủi ro cần được ghi nhận đúng bản chất và thời hạn.

Chất lượng remediation thể hiện ở khả năng chứng minh kiểm soát hoạt động và phát hiện tái diễn sau khi đóng, chứ không chỉ ở số ticket được chuyển sang trạng thái hoàn tất.
