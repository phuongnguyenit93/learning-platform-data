# Manager approval: phê duyệt của quản lý trong quy trình PAM

## Mục tiêu bài học

Trong Privileged Access Management (PAM), phê duyệt của quản lý giúp xác nhận một nhân sự có lý do công việc phù hợp để sử dụng quyền đặc biệt. Quyết định này cần gắn với đúng người, đúng nhu cầu, đúng phạm vi và đúng thời hạn; sau đó được kiểm tra cùng các điều kiện kỹ thuật trước khi quyền có hiệu lực.

Sau bài học, bạn có thể:

- Xác định quản lý chịu trách nhiệm xác nhận điều gì và khi nào cần người phê duyệt khác.
- Thiết kế yêu cầu quyền đủ thông tin để người quản lý ra quyết định.
- Ràng buộc phê duyệt với danh tính, tài sản, vai trò, thời gian và phiên bản yêu cầu.
- Xử lý ủy quyền, vắng mặt, đổi quản lý, yêu cầu khẩn cấp và phê duyệt quá hạn.
- Lưu bằng chứng từ quyết định quản lý đến cấp quyền, sử dụng và thu hồi quyền.

Tên tài sản, mã yêu cầu, thời hạn và cấu trúc dữ liệu trong bài chỉ có mục đích minh họa. Chúng không phải cấu hình của một sản phẩm PAM cụ thể.

## 1. Manager approval giải quyết vấn đề gì?

Giả sử một kỹ sư vận hành yêu cầu quyền khởi động lại dịch vụ thanh toán trong hai giờ để xử lý lỗi đã được ghi nhận. Tài khoản của kỹ sư là hợp lệ, đã có MFA và đang thuộc nhóm vận hành. Tuy nhiên, các thông tin đó chưa trả lời được:

- Kỹ sư có thực sự được giao công việc này không?
- Công việc có phù hợp với trách nhiệm hiện tại của họ không?
- Có cần truy cập sản xuất trong thời gian đề nghị không?
- Ai chịu trách nhiệm về lý do kinh doanh và việc bố trí nhân sự?

**Manager approval** là một quyết định có thể truy vết của người quản lý được chỉ định theo chính sách, nhằm xác nhận các khía cạnh trên.

Nếu không có bước này, người dùng có thể tự chuyển một nhu cầu cá nhân thành yêu cầu quyền đặc biệt. Nếu bước này chỉ là một nút bấm không có thông tin và phạm vi rõ ràng, tổ chức tạo thêm thủ tục nhưng không tạo được quyết định có giá trị.

Phê duyệt của quản lý cũng không chứng minh rằng mọi thao tác kỹ thuật trong yêu cầu đều an toàn. Một quản lý có thể biết nhân sự cần làm nhiệm vụ nhưng không có đủ trách nhiệm hoặc chuyên môn để chấp thuận quyền quản trị trên hệ thống của đơn vị khác.

## 2. Phân biệt các loại trách nhiệm phê duyệt

Một quy trình tốt phân biệt lý do công việc với quyền quyết định trên tài sản.

| Vai trò | Trách nhiệm chính | Giới hạn |
|---|---|---|
| Người yêu cầu | Mô tả công việc, tài sản, quyền và thời gian cần dùng | Không tự quyết định rằng mình đủ điều kiện nhận quyền |
| Quản lý trực tiếp hoặc người quản lý được chính sách chỉ định | Xác nhận phân công, nhu cầu, mức độ phù hợp với vai trò và thời gian | Không mặc nhiên có quyền chấp thuận mọi tài sản |
| Chủ sở hữu tài sản hoặc dịch vụ | Đánh giá phạm vi kỹ thuật, tác động và điều kiện truy cập | Không thay thế việc xác nhận trách nhiệm nhân sự khi chính sách yêu cầu |
| Vai trò bảo mật hoặc tuân thủ được chỉ định | Đánh giá ngoại lệ, xung đột nhiệm vụ hoặc rủi ro đặc biệt | Không cần tham gia mọi yêu cầu nếu chính sách không yêu cầu |
| Hệ thống PAM và cơ chế thực thi | Kiểm tra điều kiện, cấp quyền theo chính sách và thu hồi | Không coi một quyết định đơn lẻ là lý do bỏ qua các điều kiện khác |

Các vai trò có thể do một người kiêm nhiệm trong một số trường hợp, nhưng phải được chính sách cho phép. Hai nút phê duyệt do cùng một người bấm không tự tạo thành hai người kiểm soát độc lập.

Với quyền nhạy cảm cần hai người độc lập, hệ thống phải kiểm tra danh tính người ra quyết định, không chỉ kiểm tra rằng hai tên vai trò đều có kết quả “đã duyệt”.

### Ví dụ

Quản lý đội ứng dụng xác nhận kỹ sư cần phân tích sự cố. Chủ sở hữu nền tảng dữ liệu đánh giá kỹ sư có nên nhận vai trò đọc log cơ sở dữ liệu hay không. Nếu yêu cầu là thay đổi quyền quản trị dữ liệu khách hàng, có thể cần một bước khác theo chính sách.

Quy trình phải nói rõ cần **tất cả** các bước được yêu cầu, một người trong nhóm được chỉ định, hay một tổ hợp điều kiện cụ thể. Không dùng điều kiện “bất kỳ ai duyệt cũng được” khi mục tiêu là kiểm soát độc lập.

## 3. Xác định đúng quản lý có thẩm quyền

### 3.1. Nguồn quan hệ quản lý phải đáng tin cậy

Quan hệ nhân sự và quản lý có thể đến từ hệ thống nhân sự, danh bạ hoặc nguồn quản trị định danh đã được tổ chức xác định. Điều quan trọng là biết nguồn nào có thẩm quyền, cập nhật thế nào và xử lý sai lệch ra sao.

Không lấy địa chỉ người quản lý do người yêu cầu tự nhập làm căn cứ duy nhất để định tuyến quyết định.

Tại thời điểm định tuyến, cần xác định:

- Nhân sự thuộc đơn vị nào và ai có trách nhiệm quản lý phù hợp.
- Người phê duyệt còn hoạt động và có quyền phê duyệt loại yêu cầu này hay không.
- Quan hệ có áp dụng cho nhân viên, nhà thầu hay nhân sự bên ngoài không.
- Có xung đột nhiệm vụ hoặc tình huống tự phê duyệt không.
- Dữ liệu có đủ mới và có mâu thuẫn cần xử lý không.

Nếu thiếu quan hệ quản lý, nên chuyển sang trạng thái cần xử lý định tuyến với người chịu trách nhiệm rõ ràng. Không biến “không tìm thấy quản lý” thành “không cần phê duyệt”.

### 3.2. Nhà thầu và người dùng bên ngoài

Nhà thầu có thể không có quản lý nội bộ theo sơ đồ nhân sự thông thường. Khi đó, chính sách có thể chỉ định người bảo trợ nội bộ chịu trách nhiệm xác nhận nhu cầu.

Người bảo trợ chỉ có thẩm quyền trong phạm vi được giao. Việc một nhà cung cấp xác nhận kỹ thuật viên của họ cần hỗ trợ không tự thay thế trách nhiệm chấp thuận truy cập của tổ chức sở hữu tài sản.

### 3.3. Chống tự phê duyệt

Cần so sánh định danh thực của người yêu cầu, người hưởng quyền và người phê duyệt. Chỉ so sánh tên hiển thị hoặc địa chỉ email có thể bỏ sót tài khoản thay thế của cùng một người.

Nếu một quản lý yêu cầu quyền cho chính mình, quy trình phải chuyển đến cấp quản lý khác hoặc vai trò độc lập được chỉ định. Không dùng tài khoản thứ hai để vượt điều kiện này.

Một yêu cầu được tạo hộ cũng cần ghi rõ:

- Ai tạo yêu cầu.
- Ai là người được hưởng quyền.
- Ai ra quyết định.

Việc người tạo yêu cầu khác người hưởng quyền không có nghĩa là yêu cầu đã có một người kiểm soát độc lập.

## 4. Một yêu cầu đủ thông tin để quản lý quyết định

“Cần admin để làm việc” không đủ để đánh giá sự cần thiết. Người yêu cầu nên mô tả một công việc cụ thể và quyền tối thiểu có thể thực hiện công việc đó.

| Trường thông tin | Ý nghĩa khi phê duyệt |
|---|---|
| Người hưởng quyền | Xác định đúng nhân sự sẽ được cấp quyền |
| Lý do công việc và ticket | Cho biết nhiệm vụ, kết quả mong đợi và nơi đối chiếu |
| Tài sản hoặc dịch vụ | Tránh hiểu nhầm phạm vi giữa các môi trường |
| Vai trò và hành động | Phân biệt đọc log, khởi động lại dịch vụ và quản trị toàn hệ thống |
| Môi trường | Nhận biết sản xuất, thử nghiệm hoặc vùng nhạy cảm |
| Cửa sổ truy cập và thời lượng | Đánh giá nhu cầu thời gian, không cấp quyền dài hơn cần thiết |
| Hình thức sử dụng | Phiên PAM, vai trò tạm hoặc checkout credential có rủi ro khác nhau |
| Điều kiện và tác động | Nêu khả năng gián đoạn, kế hoạch thay đổi và giám sát cần thiết |
| Quyền đang có hoặc phương án thay thế | Tránh cấp thêm quyền khi quyền hiện tại đã đáp ứng |

Không đưa mật khẩu, token hay dữ liệu nhạy cảm không cần thiết vào phần lý do. Hồ sơ phê duyệt cần đủ thông tin để quyết định, đồng thời được giới hạn người xem phù hợp.

### 4.1. Giao diện ra quyết định

Người quản lý cần thấy bản tóm tắt chính xác của yêu cầu: nhân sự, tài sản, môi trường, quyền, thời hạn và lý do. Những yêu cầu khác nhau không nên hiện dưới cùng một nhãn chung “PAM access”.

Một quyết định nên có các kết quả rõ ràng:

- **Chấp thuận:** đúng phạm vi và điều kiện đang hiển thị.
- **Từ chối:** không đáp ứng nhu cầu hoặc điều kiện; ghi lý do đủ để xử lý tiếp.
- **Yêu cầu bổ sung:** thiếu thông tin hoặc cần thu hẹp phạm vi; chưa phải chấp thuận.

Nếu người quản lý đề nghị đổi từ quyền quản trị sang đọc log, quy trình phải tạo một phạm vi mới được ghi nhận. Không sửa yêu cầu âm thầm sau khi chữ “đã duyệt” đã xuất hiện.

### 4.2. Thông báo không phải bằng chứng quyết định

Email hoặc tin nhắn nhắc việc có thể đưa người quản lý đến hệ thống phê duyệt. Quyết định cần được liên kết với một danh tính đã xác thực và đúng yêu cầu.

Một câu trả lời “OK” qua kênh không xác minh danh tính, phạm vi hoặc phiên bản yêu cầu dễ gây tranh chấp. Nếu tổ chức cho phép quyết định qua kênh tích hợp, kênh đó phải bảo đảm các ràng buộc tương đương và ghi nhận được bằng chứng cần thiết.

Với quyền rủi ro cao, chính sách có thể yêu cầu xác thực lại hoặc xác thực tăng cường tại thời điểm quyết định. Không ghi các yếu tố xác thực bí mật vào nhật ký.

## 5. Ràng buộc phê duyệt vào phạm vi bất biến

Một phê duyệt chỉ có giá trị cho nội dung mà người quản lý đã xem và đồng ý.

Ví dụ, quản lý đã duyệt:

> Nhân sự A đọc log trên máy ứng dụng X từ 20:00 đến 21:00 cho ticket INC-731.

Quyết định đó không nên được tái sử dụng cho:

- Nhân sự B.
- Máy chủ dữ liệu Y.
- Vai trò quản trị thay cho đọc log.
- Cửa sổ 21:00–23:00.
- Một ticket khác hoặc một lần kích hoạt khác nếu chính sách yêu cầu duyệt từng lần.

Một cách triển khai là lưu phiên bản yêu cầu và một bản chụp phạm vi tại thời điểm quyết định. Bản ghi phê duyệt tham chiếu phiên bản đó bằng mã định danh ổn định.

Nếu dùng mã băm để nhận biết thay đổi, dữ liệu cần được chuẩn hóa trước khi băm. Mã băm giúp kiểm tra tính nhất quán của nội dung; nó không tự chứng minh ai phê duyệt hoặc ngăn người có quyền sửa toàn bộ kho dữ liệu. Vẫn cần kiểm soát truy cập và tính toàn vẹn của bằng chứng.

### Ví dụ hồ sơ quyết định

```yaml
approval_record:
  decision_id: APR-9082
  request_id: PAM-2147
  request_version: 3
  beneficiary_id: employee-042
  approver_id: manager-008
  approver_role: line_manager
  authority_source: governed_reporting_line
  decision: APPROVED
  scope:
    asset_ids:
      - payments-app-02
    environment: production
    privilege_profile: service-log-reader
    purpose_ticket: INC-731
    starts_at: "2026-12-03T20:00:00+07:00"
    ends_at: "2026-12-03T21:00:00+07:00"
  decided_at: "2026-12-03T18:10:00+07:00"
  latest_activation_at: "2026-12-03T20:15:00+07:00"
  policy_version: pam-approval-example-v1
```

Đây là mô hình dữ liệu minh họa, không phải cú pháp cấu hình để chạy. Trong ví dụ, 20:15 là thời điểm cuối được phép bắt đầu kích hoạt, còn 21:00 là giới hạn cuối của quyền. Kích hoạt lúc 20:14 không tự động tạo thêm một giờ quyền đến 21:14.

### Thay đổi nào phải xem xét lại?

Những thay đổi ảnh hưởng quyết định như người hưởng quyền, tài sản, quyền, môi trường, mục đích, thời gian hoặc điều kiện quan trọng thường cần một phiên bản và quyết định mới.

Sửa lỗi trình bày không ảnh hưởng phạm vi có thể được xử lý khác theo chính sách, nhưng vẫn cần lưu vết. Không để một trường mô tả tự do trở thành nơi đổi mục đích thực tế mà không tái phê duyệt.

## 6. Phân biệt các mốc thời gian và trạng thái

Một yêu cầu có thể được quản lý chấp thuận nhưng chưa được cấp quyền. Đây là trạng thái hợp lệ, không phải lỗi đồng bộ.

```text
Gửi yêu cầu
    |
    v
Chờ quản lý -----> Từ chối / Hủy / Hết hạn
    |
    v
Quản lý chấp thuận
    |
    v
Các phê duyệt và điều kiện còn lại
    |
    v
Đủ điều kiện kích hoạt
    |
    v
Kiểm tra lại trước khi cấp
    |
    v
Quyền tạm có hiệu lực
    |
    v
Hết hạn / Hoàn tất / Thu hồi
```

Từng bước cần có trạng thái và sự kiện riêng. Không dùng một giá trị “APPROVED” để đồng thời biểu diễn quyết định quản lý, kết quả kiểm tra chính sách và việc tài khoản đích đã nhận quyền.

### 6.1. Các thời hạn khác nhau

| Mốc | Chức năng |
|---|---|
| Hạn phản hồi | Cho biết khi nào cần nhắc việc, chuyển cấp hoặc đóng yêu cầu chưa được quyết định |
| Hạn giá trị của quyết định | Giới hạn thời gian được phép sử dụng phê duyệt để kích hoạt |
| Cửa sổ truy cập | Giới hạn thời gian công việc được phép diễn ra |
| Thời lượng quyền | Giới hạn tuổi thọ của grant sau khi kích hoạt, trong cửa sổ cho phép |
| Giới hạn phiên | Kiểm soát thời gian phiên hoặc điều kiện duy trì phiên theo chính sách |

Một chính sách minh họa có thể xác định:

```text
grant_end = min(
    thời điểm kích hoạt + thời lượng được cấp,
    kết thúc cửa sổ truy cập,
    giới hạn do chính sách áp dụng
)
```

Công thức này chỉ minh họa giới hạn grant. Thời điểm cuối được phép kích hoạt không nhất thiết là thời điểm phải dừng một grant đã được cấp hợp lệ; phải xác định rõ ý nghĩa của từng mốc trong chính sách.

Không gia hạn quyền chỉ bằng cách kéo dài ticket hoặc gửi lời nhắc cho quản lý. Gia hạn có thể làm thay đổi phạm vi quyết định và cần một yêu cầu hoặc phiên bản được xử lý phù hợp.

### 6.2. Quá hạn và không phản hồi

Không phản hồi không có nghĩa là đồng ý. Khi hết hạn phản hồi, hệ thống có thể nhắc việc, chuyển cho người thay thế có thẩm quyền hoặc hết hạn yêu cầu theo chính sách.

Việc chuyển cấp chỉ đổi người có thể ra quyết định. Nó không làm giảm số bước phê duyệt bắt buộc hoặc cho phép tự động cấp quyền.

Nếu quản lý bấm một liên kết cũ sau khi yêu cầu đã hết hạn, bị hủy hoặc đã thay phiên bản, hệ thống phải từ chối thay đổi không còn hợp lệ và hiển thị trạng thái hiện tại.

## 7. Từ phê duyệt đến cấp quyền: tránh khoảng trống thực thi

### 7.1. Kiểm tra lại tại thời điểm kích hoạt

Trước khi cấp quyền, hệ thống cần xác nhận những điều kiện có ảnh hưởng còn đúng:

- Đúng người hưởng quyền và danh tính còn hoạt động.
- Đúng phiên bản yêu cầu, chưa bị hủy hoặc thay thế.
- Đã đủ các phê duyệt độc lập mà chính sách yêu cầu.
- Các quyết định chưa bị thu hồi và còn giá trị cho lần kích hoạt này.
- Tài sản, vai trò và điều kiện sử dụng vẫn được phép.
- Cửa sổ thời gian, giới hạn sử dụng và điều kiện xác thực được đáp ứng.
- Không xuất hiện điều kiện chặn như xung đột nhiệm vụ chưa được xử lý.

Không nhất thiết yêu cầu quản lý duyệt lại mỗi lần hệ thống đọc trạng thái. Cần tái kiểm tra hoặc tái phê duyệt theo những thay đổi và thời hạn mà chính sách xác định.

Một phê duyệt ban đầu không được vượt qua lệnh khóa khẩn cấp, trạng thái nghỉ việc hoặc một chính sách mới chặn quyền tại thời điểm kích hoạt.

### 7.2. Quyết định đồng thời và sự kiện đến muộn

Hệ thống có thể nhận hai sự kiện gần nhau: quản lý chấp thuận trong khi người yêu cầu hủy, hoặc webhook cũ đến sau một quyết định mới.

Cần có quy tắc chuyển trạng thái xác định, kiểm tra phiên bản và bảo vệ cập nhật đồng thời. Không áp dụng kiểu “sự kiện đến sau ghi đè hết” cho những trạng thái đã kết thúc mà không kiểm tra tính hợp lệ.

Nếu sử dụng tác vụ bất đồng bộ để cấp quyền, tác vụ phải kiểm tra trạng thái hiện hành ngay trước khi cấp. Nếu quyền đã được cấp trong một khoảng đua với yêu cầu hủy, hệ thống cần phát hiện và thực hiện thu hồi, đồng thời ghi nhận khoảng thời gian quyền đã tồn tại.

Không giả định rằng một giao dịch trong cơ sở dữ liệu workflow có thể nguyên tử hóa toàn bộ thao tác trên IdP, vault và máy đích. Thiết kế cần xử lý thất bại từng phần và có cách đối soát.

### 7.3. Chống cấp quyền lặp

Một lần bấm, thông báo lại hoặc webhook trùng không được tạo nhiều grant ngoài ý định. Có thể dùng định danh quyết định, định danh lần kích hoạt và kiểm tra tính lặp an toàn.

Chính sách phải nói rõ phê duyệt cho một lần sử dụng hay cho nhiều lần trong một cửa sổ. Với quyết định một lần, việc kết thúc grant không tự khôi phục quyền dùng lại quyết định đó.

Nếu cho phép nhiều phiên, phải giới hạn số lần, đồng thời và phạm vi; mỗi lần sử dụng đều cần đối chiếu với quyết định còn hiệu lực.

### 7.4. Thu hồi sau khi đã cấp

Quản lý có thể rút lại xác nhận do thay đổi phân công hoặc phát hiện yêu cầu không còn phù hợp. Hệ thống cần truyền quyết định này tới các lớp thực thi liên quan theo chính sách.

Khóa khả năng yêu cầu quyền mới chưa đủ nếu grant hoặc phiên đang hoạt động vẫn còn hiệu lực. Cần xác định việc gỡ nhóm hoặc vai trò tạm, kết thúc phiên PAM, xử lý phiên trên tài sản đích và credential đã cấp.

Đổi mật khẩu sau checkout không mặc nhiên kết thúc một phiên đã xác thực. Bằng chứng thu hồi phải phản ánh kết quả thực tế trên các lớp đó.

## 8. Ủy quyền, thay đổi nhân sự và ngoại lệ

### 8.1. Quản lý vắng mặt

Ủy quyền nên được cấu hình trước hoặc được một vai trò có trách nhiệm thiết lập, với phạm vi rõ ràng:

- Người giao và người nhận quyền phê duyệt.
- Khoảng thời gian có hiệu lực.
- Nhân sự hoặc đơn vị được áp dụng.
- Loại tài sản, loại quyền và mức rủi ro được xử lý.
- Điều kiện cấm như tự phê duyệt hoặc ủy quyền tiếp khi không được phép.

Không dùng việc chuyển tiếp email làm cơ chế ủy quyền duy nhất. Người được ủy quyền cần đăng nhập bằng danh tính của mình; không dùng tài khoản hoặc yếu tố MFA của quản lý.

Bằng chứng phải ghi ai thực sự quyết định và dựa trên ủy quyền nào. Không ghi thành “quản lý đã duyệt” nếu người khác thực hiện thay.

### 8.2. Nhân sự chuyển nhóm hoặc đổi quản lý

Cần xác định điều gì xảy ra với yêu cầu đang chờ, quyết định chưa dùng và quyền đang hoạt động.

Một hướng xử lý có thể là định tuyến lại yêu cầu đang chờ; đánh giá lại quyết định chưa kích hoạt nếu cơ sở phân công thay đổi; rà soát grant đang tồn tại theo mức rủi ro và chính sách.

Không mặc định mọi thay đổi tên quản lý đều làm vô hiệu mọi quyết định quá khứ. Tuy nhiên, một nhu cầu truy cập dựa trên công việc cũ không nên tự đi theo nhân sự sang vai trò mới.

Khi người hưởng quyền nghỉ việc hoặc bị khóa, việc từ chối cấp mới và xử lý quyền đang có phải theo vòng đời định danh, không chờ người quản lý trả lời từng yêu cầu.

### 8.3. Quản lý không hiểu phạm vi kỹ thuật

Có thể cung cấp các gói quyền dễ hiểu, ví dụ “đọc log dịch vụ A trong một giờ”, với ánh xạ kỹ thuật được chủ sở hữu duy trì.

Nếu yêu cầu chứa quyền không rõ tác động, người quản lý nên yêu cầu làm rõ hoặc chuyển đánh giá cho chủ sở hữu phù hợp. Không buộc quản lý xác nhận một nhận định kỹ thuật mà họ không có trách nhiệm kiểm chứng.

### 8.4. Sự cố khẩn cấp

Nếu cần quyền trước khi hoàn thành quy trình thông thường, sử dụng đường khẩn cấp đã được tổ chức định nghĩa. Đường này phải xác định điều kiện kích hoạt, người chấp thuận hoặc chịu trách nhiệm, phạm vi, thời hạn, giám sát và rà soát sau sự cố.

Một lời nhắn “cứ làm đi, mai tôi duyệt” không tự tạo thành một cơ chế khẩn cấp có kiểm soát. Quy trình khẩn cấp được thiết kế trước có thể có các điều kiện khác với quy trình chuẩn, nhưng phải ghi nhận trạng thái thực tế của lần sử dụng.

Phê duyệt sau sự cố có giá trị xem xét và quy trách nhiệm. Nó không chứng minh rằng tại thời điểm quyền được cấp đã tồn tại một phê duyệt trước đó.

## 9. Bằng chứng và khả năng truy vết

Một bản ghi “manager approved” thiếu người quyết định, phạm vi và thời điểm sẽ khó phục vụ kiểm toán hoặc điều tra.

Bộ bằng chứng tối thiểu nên nối được các đối tượng sau:

```text
Yêu cầu + phiên bản
    -> Người hưởng quyền
    -> Quản lý/người được ủy quyền và căn cứ thẩm quyền
    -> Quyết định + thời điểm + phạm vi
    -> Kết quả các bước phê duyệt và kiểm tra còn lại
    -> Lần kích hoạt + grant/phiên
    -> Hết hạn/thu hồi + kết quả xác minh
```

Những dữ liệu hữu ích gồm:

| Dữ liệu | Câu hỏi được trả lời |
|---|---|
| Mã yêu cầu, phiên bản và nội dung đã duyệt | Người quản lý đã nhìn thấy phạm vi nào? |
| Định danh người hưởng quyền và người quyết định | Ai được cấp, ai chịu trách nhiệm chấp thuận? |
| Vai trò phê duyệt, nguồn quan hệ quản lý hoặc mã ủy quyền | Người quyết định có thẩm quyền theo căn cứ nào? |
| Thời điểm, kết quả và lý do | Quyết định xảy ra khi nào và vì sao? |
| Phiên bản chính sách, điều kiện và hạn sử dụng | Những quy tắc nào được áp dụng? |
| Mã grant hoặc phiên và tài sản đích | Phê duyệt được sử dụng cho lần truy cập nào? |
| Sự kiện hủy, hết hạn, thu hồi và kết quả thực thi | Quyền kết thúc như thế nào? |

Cần thống nhất cách biểu diễn thời gian và múi giờ để đối chiếu giữa workflow, IdP, PAM và hệ thống đích. Nếu log đến trễ, cần phân biệt thời điểm sự kiện xảy ra và thời điểm hệ thống thu nhận.

Bằng chứng cần có phân quyền đọc, bảo vệ khỏi sửa hoặc xóa trái phép và thời hạn lưu theo yêu cầu của tổ chức. Người ra quyết định không nên có khả năng tự xóa dấu vết phê duyệt của mình.

Không cần sao chép toàn bộ hồ sơ nhân sự vào mỗi yêu cầu. Nên lưu những thuộc tính hoặc tham chiếu cần thiết để giải thích thẩm quyền, với cơ chế bảo vệ và khả năng tái dựng phù hợp.

### Chỉ số giúp đánh giá quy trình

Có thể theo dõi thời gian chờ theo nhóm rủi ro, tỷ lệ yêu cầu bị trả lại vì thiếu thông tin, số quyết định quá hạn, số trường hợp ủy quyền và số lần kích hoạt bị chặn do quyết định không còn hợp lệ.

Một tỷ lệ chấp thuận gần tuyệt đối hoặc thời gian quyết định rất ngắn có thể là tín hiệu cần kiểm tra, nhưng không tự chứng minh phê duyệt hình thức. Cần xem mẫu yêu cầu, chất lượng phân quyền và hoàn cảnh vận hành.

Không tối ưu chỉ theo tốc độ duyệt. Cần quan sát cả độ rộng quyền được cấp, ngoại lệ và khả năng thu hồi đúng hạn.

## 10. Tình huống thực hành: yêu cầu đọc log sản xuất

### 10.1. Bối cảnh

Lan thuộc đội vận hành ứng dụng. Quản lý trực tiếp là Minh. Lan được giao phân tích lỗi trên dịch vụ thanh toán theo ticket `INC-731`.

Lan yêu cầu vai trò `service-log-reader` trên `payments-app-02` từ 20:00 đến 21:00. Quyền này được thiết kế để đọc log phù hợp, không cho sửa cấu hình hoặc đọc dữ liệu ứng dụng ngoài phạm vi.

Chính sách của tình huống yêu cầu quản lý xác nhận phân công, chủ sở hữu dịch vụ xác nhận phạm vi tài sản và người dùng kích hoạt quyền bằng danh tính cá nhân qua PAM.

### 10.2. Dòng xử lý hợp lệ

| Mốc | Sự kiện | Kết quả |
|---|---|---|
| 17:30 | Lan gửi yêu cầu phiên bản 1 | Hệ thống xác định Minh từ nguồn quan hệ quản lý |
| 17:40 | Minh xác nhận công việc và cửa sổ truy cập | Hoàn tất bước quản lý, chưa cấp quyền |
| 18:00 | Chủ sở hữu dịch vụ duyệt vai trò đọc log | Yêu cầu đủ các quyết định cần thiết |
| 20:05 | Lan yêu cầu kích hoạt | Hệ thống kiểm tra lại danh tính, phạm vi và thời hạn |
| 20:05 | Cấp grant tạm và mở phiên phù hợp | Gắn grant, phiên và yêu cầu với nhau |
| 20:40 | Lan kết thúc công việc | Thu hồi sớm theo quy trình |
| Sau đó | Đối soát quyền và log | Xác nhận kết quả rồi đóng hồ sơ |

Các trạng thái không nên được suy ra chỉ từ thời gian. Ví dụ, đến 20:00 không có nghĩa là được cấp quyền nếu chủ sở hữu dịch vụ chưa duyệt hoặc tài khoản Lan đã bị khóa.

### 10.3. Biến thể: người yêu cầu đổi sang quyền ghi

Sau khi Minh duyệt, Lan sửa yêu cầu từ đọc log sang khởi động lại dịch vụ.

Đây là thay đổi có ảnh hưởng đến phạm vi và tác động. Quyết định cũ không nên được áp dụng ngầm cho phiên bản mới. Hệ thống tạo phiên bản mới và yêu cầu các quyết định liên quan theo chính sách.

Người quản lý cần xác nhận phần công việc mới vẫn nằm trong phân công; chủ sở hữu dịch vụ cần đánh giá thêm tác động và điều kiện thực hiện.

### 10.4. Biến thể: chuyển nhóm trước khi kích hoạt

Lan chuyển sang đội khác trước 20:00. Hệ thống nhận được cập nhật quan hệ nhân sự.

Cần đánh giá liệu nhu cầu cũ còn hợp lệ hay không theo chính sách đã xác lập. Nếu yêu cầu phải được quản lý hiện tại xác nhận lại, grant bị giữ lại cho đến khi đủ điều kiện. Không chỉ kiểm tra rằng trong lịch sử đã từng có một người quản lý bấm chấp thuận.

Nếu dữ liệu quan hệ đang mâu thuẫn, hệ thống cần trạng thái chờ xử lý rõ ràng và người chịu trách nhiệm. Không định tuyến ngẫu nhiên tới một người có quyền rộng.

### 10.5. Biến thể: thiếu quyền tại tài sản đích sau khi đã duyệt

PAM ghi nhận quyết định hợp lệ nhưng thao tác cấp vai trò tại máy đích thất bại.

Hệ thống phải phản ánh rằng phê duyệt đã có nhưng cấp quyền thất bại. Không đánh dấu truy cập thành công, không cho rằng phiên đã sẵn sàng và không gửi mật khẩu khác để xử lý ngoài quy trình.

Cơ chế thử lại phải kiểm tra quyết định và thời hạn còn giá trị, đồng thời tránh tạo nhiều grant nếu lần trước thực tế đã thành công nhưng phản hồi bị mất.

## 11. Kiểm chứng quy trình trước khi vận hành

Các phép thử phải thực hiện trên tài khoản và tài sản được phép. Mục tiêu là kiểm chứng quyết định được thực thi theo phạm vi, không chỉ xác nhận rằng giao diện có nút phê duyệt.

| Phép thử | Kết quả mong đợi |
|---|---|
| Người yêu cầu nhập một email quản lý khác | Định tuyến không dựa riêng vào giá trị tự khai |
| Quản lý dùng tài khoản phụ để duyệt quyền cho chính mình | Xung đột danh tính được xử lý theo chính sách |
| Người được ủy quyền duyệt sau khi ủy quyền hết hạn | Quyết định không được chấp nhận bằng ủy quyền cũ |
| Bấm chấp thuận từ thông báo của phiên bản cũ | Không phê duyệt nhầm phiên bản hiện tại |
| Thay tài sản, quyền hoặc thời gian sau phê duyệt | Quyết định cũ không mở rộng sang phạm vi mới |
| Quản lý duyệt nhưng thiếu bước chủ sở hữu bắt buộc | Chưa cấp quyền |
| Quyết định hợp lệ nhưng người hưởng quyền bị khóa | Không cấp mới; xử lý quyền hiện hữu theo chính sách |
| Quản lý không phản hồi đến hết hạn | Nhắc việc, chuyển cấp hoặc hết hạn; không tự cấp |
| Hai quyết định hoặc webhook giống nhau đến nhiều lần | Không tạo grant lặp ngoài chính sách |
| Yêu cầu bị hủy khi tác vụ cấp quyền đang chờ | Không cấp từ trạng thái cũ hoặc phát hiện và thu hồi nếu đã xảy ra đua |
| Grant đã kết thúc rồi người dùng dùng lại phê duyệt một lần | Không tái cấp nếu không có quyền sử dụng lại |
| Workflow mất phản hồi sau thao tác cấp tại đích | Đối soát trạng thái thực tế trước khi thử lại |
| Quản lý rút lại quyết định khi phiên đang hoạt động | Trạng thái thu hồi và tác động thực tế được ghi nhận |
| Người không có vai trò kiểm toán truy cập hồ sơ | Không xem được thông tin ngoài thẩm quyền |

Một phép thử không đạt cần dẫn đến sửa cơ chế hoặc xử lý ngoại lệ có trách nhiệm rõ ràng. Không chỉ sửa nhãn trạng thái để hồ sơ trông như đã tuân thủ.

## 12. Những sai lầm làm phê duyệt mất giá trị

**Duyệt chỉ dựa vào tên người yêu cầu.** Người quen thuộc vẫn có thể yêu cầu quyền quá rộng hoặc ngoài nhiệm vụ. Cần xem mục đích, tài sản, vai trò và thời gian.

**Cho rằng quản lý duyệt là đủ cho mọi tài sản.** Quản lý xác nhận nhu cầu nhân sự; quyền quyết định tài sản phải theo chính sách của tài sản đó.

**Cho phép thay nội dung sau khi được duyệt.** Quyết định cần gắn phiên bản và phạm vi; thay đổi ảnh hưởng quyết định phải được xử lý lại.

**Dùng quá hạn phản hồi làm lý do tự chấp thuận.** Thời hạn giúp điều phối công việc, không thay thế quyết định có thẩm quyền.

**Ủy quyền không có ngày hết hạn.** Một người thay thế tạm thời có thể trở thành người phê duyệt thường trực ngoài dự kiến. Cần giới hạn và rà soát vòng đời ủy quyền.

**Coi phê duyệt là quyền quản trị thường trực.** Phê duyệt phải đi cùng cơ chế least privilege và JIT/JEA; quyền cần hết hạn hoặc được thu hồi theo công việc.

**Đóng ticket rồi mặc định quyền đã mất.** Cần sự kiện thực thi và xác minh trên grant, phiên và tài sản đích liên quan.

## 13. Tự kiểm tra

1. Quản lý xác nhận nhu cầu công việc khác gì với chủ sở hữu tài sản chấp thuận quyền kỹ thuật?
2. Vì sao người hưởng quyền không được tự chọn một email bất kỳ làm người quản lý phê duyệt?
3. Sau khi được duyệt đọc log, người yêu cầu đổi sang quyền quản trị. Quyết định cũ có còn đủ không?
4. Một quyết định còn hạn nhưng tài khoản người hưởng quyền đã bị khóa. Có được kích hoạt không?
5. Quản lý không phản hồi trước hạn thì quy trình nên làm gì?
6. Cần ghi gì khi một người được ủy quyền ra quyết định thay quản lý?
7. Vì sao “quản lý đã duyệt” và “quyền đã cấp” phải là hai trạng thái khác nhau?
8. Nếu thao tác cấp quyền gặp lỗi mạng sau khi gửi đến máy đích, vì sao không nên thử lại vô điều kiện?

### Gợi ý trả lời

1. Quản lý xác nhận phân công và sự cần thiết đối với nhân sự; chủ sở hữu đánh giá phạm vi, tác động và điều kiện truy cập tài sản.
2. Thẩm quyền cần xuất phát từ nguồn được quản trị; giá trị tự khai có thể dẫn yêu cầu đến người không chịu trách nhiệm hoặc người thông đồng.
3. Không đủ cho phạm vi đã thay đổi; cần phiên bản mới và các quyết định phù hợp theo chính sách.
4. Không. Phê duyệt không vượt qua trạng thái định danh và các điều kiện chặn hiện hành.
5. Nhắc việc, chuyển cấp hợp lệ hoặc hết hạn yêu cầu; không coi im lặng là đồng ý.
6. Ghi danh tính người thực sự quyết định, người giao quyền, phạm vi, thời hạn và căn cứ ủy quyền.
7. Có thể còn bước phê duyệt, điều kiện kích hoạt hoặc lỗi thực thi; hai trạng thái trả lời hai câu hỏi khác nhau.
8. Lần trước có thể đã thành công nhưng phản hồi bị mất. Cần đối soát, kiểm tra tính lặp an toàn và xác nhận quyết định vẫn còn hiệu lực.

## Kết luận

Manager approval có giá trị khi phản ánh một quyết định có trách nhiệm về nhu cầu sử dụng quyền đặc biệt. Quyết định cần gắn với đúng người hưởng quyền, đúng phiên bản yêu cầu, phạm vi cụ thể và thời hạn rõ ràng.

Trong PAM, quyết định đó phải được kết nối với phê duyệt tài sản khi cần, kiểm tra chính sách tại thời điểm kích hoạt, cấp quyền tối thiểu có thời hạn và thu hồi có bằng chứng. Khi các liên kết này được thực thi, tổ chức có thể giải thích không chỉ ai đã đồng ý, mà còn quyền nào thực sự được cấp và kết thúc như thế nào.
