# Just-in-time access

## 1. Mục tiêu và bối cảnh

Trong chương **Khái niệm PAM**, *just-in-time access* là cách quản lý thời điểm đặc quyền có hiệu lực. Thay vì để tài khoản quản trị, tài khoản dịch vụ hoặc workload luôn có quyền cao, hệ thống chỉ mở quyền khi có nhu cầu hợp lệ, trong phạm vi và khoảng thời gian đã xác định.

Đối với PAM, mục tiêu không chỉ là cấp quyền nhanh. Mục tiêu là liên kết được **nhu cầu → điều kiện → cấp quyền → sử dụng → thu hồi → bằng chứng**. Cơ chế này cần phối hợp với least privilege, giới hạn thao tác quản trị, bảo vệ credential, giám sát phiên và quy trình ứng phó sự cố.

Sau bài học, bạn có thể:

- Phân biệt quyền thường trực, quyền đủ điều kiện kích hoạt và quyền đang hiệu lực.
- Mô tả vòng đời một yêu cầu JIT và xác định thời điểm quyền thực sự kết thúc.
- Chọn cách giới hạn thời gian phù hợp với tài khoản con người và danh tính dịch vụ.
- Nhận diện lỗi thu hồi, đường truy cập bỏ qua JIT và bằng chứng cần giữ để kiểm toán.

## 2. Just-in-time access là gì?

**Just-in-time access (JIT access)** là mô hình trong đó khả năng truy cập được cấp hoặc kích hoạt khi đáp ứng nhu cầu và chính sách, có giới hạn thời gian, rồi được kết thúc theo cơ chế đã thiết kế.

Trong phạm vi PAM, khả năng được kích hoạt thường là quyền thực hiện thao tác nhạy cảm trên một tài nguyên cụ thể. Ví dụ: một kỹ sư được kích hoạt quyền khởi động lại dịch vụ A ở môi trường sản xuất trong 20 phút để xử lý một sự cố.

Định nghĩa này có ba thành phần quan trọng:

1. **Có điều kiện:** danh tính, nhiệm vụ, tài nguyên và các yêu cầu liên quan phải được kiểm tra.
2. **Có giới hạn:** hành động, đích truy cập và thời gian được xác định rõ.
3. **Có kết thúc:** quyền và các phương tiện truy cập liên quan được xử lý khi hết hạn, bị hủy hoặc không còn đáp ứng chính sách.

Thời hạn 20 phút trong ví dụ chỉ là một lựa chọn minh họa. Thời hạn thực tế phải phù hợp với nhiệm vụ, mức độ tác động, khả năng thu hồi và cơ chế của hệ thống đích.

### 2.1. Ba trạng thái quyền cần phân biệt

| Trạng thái | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Quyền thường trực — standing access | Quyền tồn tại mà không cần một lần kích hoạt riêng cho nhiệm vụ hiện tại | Tài khoản luôn nằm trong vai trò quản trị sản xuất |
| Quyền đủ điều kiện — eligible access | Danh tính có thể yêu cầu hoặc kích hoạt quyền khi thỏa chính sách | Kỹ sư trực ca được phép xin vai trò vận hành |
| Quyền đang hiệu lực — active access | Quyền đã được kích hoạt và có thể dùng trong ngữ cảnh được phép | Vai trò vận hành còn hiệu lực đến 09:25 trên dịch vụ A |

Tư cách đủ điều kiện cũng là một quyền nhạy cảm cần quản lý. Nếu một tài khoản bị chiếm đoạt có thể kích hoạt vai trò mạnh mà không có ràng buộc phù hợp, việc bỏ quyền thường trực chưa giải quyết hết vấn đề.

Ngoài ra, một danh tính có thể nhận cùng quyền qua nhiều đường. Gỡ một vai trò JIT không làm mất quyền tương đương đang có từ nhóm khác, chính sách khác hoặc một tài khoản khác mà người đó vẫn kiểm soát.

### 2.2. JIT không chỉ áp dụng cho con người

Với con người, nhu cầu có thể là xử lý sự cố hoặc thực hiện một thay đổi được duyệt. Với workload, nhu cầu có thể là một lần triển khai, một tác vụ bảo trì hoặc một công việc xử lý dữ liệu.

Cả hai đều cần danh tính rõ ràng, phạm vi hẹp, giới hạn thời gian và bằng chứng. Cách xác nhận nhu cầu có thể khác nhau: một yêu cầu của kỹ sư có thể cần phê duyệt theo chính sách; một lần chạy tự động có thể được cho phép dựa trên danh tính workload và điều kiện của quy trình đã được phê duyệt trước.

## 3. JIT giải quyết vấn đề gì?

Quyền thường trực tạo ra một khoảng thời gian mà tài khoản có thể sử dụng đặc quyền kể cả khi không có nhiệm vụ cần đến nó. Khi credential bị lộ, tài khoản bị chiếm đoạt hoặc người dùng thao tác nhầm, quyền đó có thể sẵn sàng để sử dụng.

JIT giảm khoảng thời gian đặc quyền hoạt động không cần thiết và tạo điểm kiểm tra trước khi cấp quyền. Nó cũng giúp gắn một lần sử dụng đặc quyền với lý do, người chịu trách nhiệm và phạm vi được duyệt.

Tuy nhiên, JIT không tự bảo đảm rằng hành động được thực hiện là đúng. Trong cửa sổ được cấp, một tài khoản vẫn có thể gây tác động nếu phạm vi quyền quá rộng hoặc thiếu kiểm soát hành động. Vì vậy, cần kết hợp giới hạn thời gian với giới hạn khả năng thực hiện.

| Câu hỏi kiểm soát | Biện pháp liên quan |
| --- | --- |
| Có thực sự cần quyền này không? | Kiểm kê quyền, xác nhận nhu cầu và chủ sở hữu |
| Chỉ cần làm những gì? | Least privilege và just-enough administration |
| Khi nào được dùng và trong bao lâu? | JIT và điều kiện kích hoạt |
| Truy cập bằng phương tiện nào? | Danh tính, vault, credential hoặc broker phù hợp |
| Đã thực hiện gì? | Giám sát phiên, log API và bằng chứng tại đích |
| Quyền đã chấm dứt chưa? | Thu hồi, kiểm tra trạng thái và xử lý phiên còn tồn tại |

Một tài khoản có toàn quyền trong vài phút vẫn có thể gây ảnh hưởng lớn. JIT giảm thời gian phơi lộ; mức giảm rủi ro còn phụ thuộc vào quyền được cấp và các lớp kiểm soát khác.

## 4. Các cách hiện thực JIT ở mức khái niệm

Không có một cơ chế kỹ thuật duy nhất đại diện cho mọi triển khai JIT. Tùy nền tảng, hệ thống có thể kích hoạt vai trò, cấp credential tạm thời, tạo tài khoản ngắn hạn hoặc kiểm soát một đường truy cập.

| Cách thực hiện | Điều được thay đổi tạm thời | Điều cần kiểm tra khi kết thúc |
| --- | --- | --- |
| Kích hoạt vai trò hoặc nhóm | Tài khoản nhận tập quyền trong khoảng thời gian cho phép | Quyền hiệu lực, độ trễ đồng bộ, token và phiên đã tạo |
| Cấp credential ngắn hạn | Danh tính nhận phương tiện xác thực có thời hạn | Hệ thống đích có kiểm tra thời hạn và còn phiên tồn tại hay không |
| Tạo tài khoản tạm thời | Một tài khoản được tạo cho nhiệm vụ hoặc lần chạy | Vô hiệu hóa hoặc xóa đúng tài khoản, xử lý phiên và tài nguyên liên quan |
| Cho phép truy cập qua broker | Một đường kết nối hoặc phiên được mở theo chính sách | Kết thúc phiên, ngăn kết nối lại và kiểm soát đường truy cập khác |
| Mở kết nối mạng có thời hạn | Một nguồn được tiếp cận đích trong khoảng thời gian giới hạn | Đóng đường mạng và kiểm tra cách xử lý kết nối đã được thiết lập |

Các cơ chế này bảo vệ những lớp khác nhau. Mở đường mạng có thời hạn không tự làm quyền trong cơ sở dữ liệu trở nên tối thiểu. Credential ngắn hạn cũng chưa đủ mô tả toàn bộ JIT nếu nó được cấp liên tục cho một danh tính có quyền quá rộng mà không kiểm tra điều kiện nhiệm vụ.

Một thiết kế có thể kết hợp nhiều lớp, nhưng phải chỉ rõ lớp nào quyết định thời điểm cấp, lớp nào thực thi giới hạn và lớp nào chứng minh việc kết thúc.

## 5. Vòng đời một yêu cầu JIT

### 5.1. Xác định trước phạm vi và tư cách yêu cầu

Trước khi nhận yêu cầu, cần có danh mục chức năng và tài nguyên được phép. Mỗi phạm vi nên có chủ sở hữu, tiêu chí đủ điều kiện, giới hạn thời gian và cơ chế thu hồi.

Ví dụ, “vận hành dịch vụ A ở sản xuất” cần được cụ thể hóa thành những thao tác được phép. Nếu chỉ dùng nhãn “quản trị”, người yêu cầu và người duyệt có thể hiểu khác nhau về quyền thực tế.

Tư cách đủ điều kiện cần được rà soát khi nhân sự đổi nhiệm vụ, dịch vụ đổi chủ hoặc workload ngừng sử dụng. Không nên để danh sách có thể kích hoạt quyền tăng mãi theo thời gian.

### 5.2. Gửi yêu cầu gắn với một nhiệm vụ

Một yêu cầu hữu ích thường có:

- Danh tính người hoặc workload khởi tạo.
- Chức năng cần thực hiện, tài nguyên và môi trường đích.
- Lý do nghiệp vụ hoặc mã sự cố, thay đổi hay lần chạy.
- Khoảng thời gian cần quyền và thời điểm dự kiến sử dụng.
- Danh tính sẽ thực thi nếu khác với người gửi yêu cầu.

Trường lý do không nên chỉ là một ô văn bản tùy ý không được đối chiếu. Với tác vụ có quy trình quản lý thay đổi, mã tham chiếu cần dẫn đến một công việc phù hợp với tài nguyên và phạm vi xin quyền.

### 5.3. Kiểm tra điều kiện và phê duyệt

Hệ thống đối chiếu yêu cầu với chính sách. Tùy trường hợp, điều kiện có thể bao gồm xác thực bổ sung, trạng thái trực ca, điều kiện thiết bị, quyền sở hữu tài nguyên hoặc phê duyệt của người có thẩm quyền.

Phê duyệt thủ công không phải yêu cầu bắt buộc cho mọi lần kích hoạt JIT. Những tác vụ đã được chuẩn hóa có thể được cho phép tự động nếu danh tính và điều kiện được kiểm tra rõ ràng. Các thao tác có tác động lớn có thể cần người phê duyệt độc lập theo chính sách của tổ chức.

Một quyết định phê duyệt cần gắn với **chính nội dung đã được xem xét**: hành động, tài nguyên, môi trường và giới hạn thời gian. Nếu yêu cầu thay đổi đáng kể sau khi duyệt, hệ thống phải đánh giá lại theo chính sách, tránh dùng phê duyệt cũ cho phạm vi mới.

### 5.4. Kích hoạt và xác nhận quyền tại đích

Phê duyệt chưa có nghĩa quyền đã hoạt động. Bộ thực thi có thể cần gọi hệ thống danh tính, cấu hình vai trò, cấp credential hoặc mở một phiên qua broker.

Chỉ nên thông báo quyền đã sẵn sàng khi có bằng chứng phù hợp rằng việc cấp quyền thành công. Một thông báo “đã gửi lệnh cấp quyền” không tương đương với xác nhận “quyền đã hiệu lực”. Nếu nền tảng có độ trễ truyền chính sách, trạng thái cần phản ánh điều đó.

Tại thời điểm kích hoạt, cần kiểm tra lại các điều kiện có thể đã thay đổi: yêu cầu còn hợp lệ không, đã bị hủy chưa, thời hạn còn đủ không và phạm vi có còn đúng không.

### 5.5. Sử dụng trong giới hạn được phép

Khi quyền đang hiệu lực, hệ thống cần liên kết được hoạt động với lần kích hoạt tương ứng. Người dùng không nên phải biết hoặc tự giữ credential dùng chung nếu cơ chế truy cập có thể thực thi mà không tiết lộ credential đó.

Nếu dùng một danh tính dịch vụ để thực hiện thay người dùng, phải ghi cả người khởi tạo và danh tính thực thi. Nếu chỉ ghi tài khoản dịch vụ ở đích, chuỗi quy trách nhiệm có thể bị đứt.

### 5.6. Kết thúc, thu hồi và đóng yêu cầu

Quyền có thể kết thúc do hết hạn, người dùng hoàn thành sớm, người có thẩm quyền hủy hoặc sự kiện an ninh yêu cầu thu hồi ngay.

Thu hồi cần xử lý những lớp liên quan: vai trò, credential được cấp, token, phiên, kết nối hoặc đường truy cập. Không phải nền tảng nào cũng có khả năng chấm dứt tất cả ngay lập tức. Thiết kế phải mô tả được giới hạn và cơ chế giảm khoảng thời gian còn truy cập được.

Chỉ đóng yêu cầu khi đã xác nhận kết quả thu hồi theo cơ chế được cam kết. Nếu thu hồi lỗi, cần trạng thái riêng, cảnh báo và người chịu trách nhiệm xử lý; không thể coi lỗi đó là đã kết thúc thành công.

## 6. Mô hình trạng thái và thời gian

### 6.1. Tách trạng thái nghiệp vụ khỏi trạng thái kỹ thuật

Mô hình dưới đây là ví dụ để suy nghĩ về thiết kế, không phải bộ trạng thái bắt buộc của mọi sản phẩm:

```text
REQUESTED -> APPROVED -> ACTIVATING -> ACTIVE
    |           |            |          |
    v           v            v          v
 REJECTED   CANCELLED    GRANT_FAILED  REVOKING -> CLOSED
                                        |
                                        v
                                  REVOKE_FAILED
```

Các trạng thái cuối như `REJECTED` hoặc `CANCELLED` chỉ an toàn khi không còn cấp quyền đang dang dở hoặc quyền đã được tạo. Nếu hủy xảy ra đồng thời với quá trình cấp quyền, hệ thống cần kiểm tra và dọn phần đã cấp.

Khi đến thời hạn, quyền **hết hiệu lực theo chính sách**. Hệ thống có thể chuyển sang thu hồi và chờ xác nhận kỹ thuật. Một dòng trạng thái “expired” trên cổng không đủ chứng minh rằng hệ thống đích đã từ chối mọi truy cập.

### 6.2. Chọn cách tính thời hạn rõ ràng

Cần quy định thời gian bắt đầu tính từ đâu: lúc gửi yêu cầu, lúc được duyệt hay lúc quyền thực sự được kích hoạt. Những cách tính này tạo ra trải nghiệm và thời gian quyền hiệu lực khác nhau.

Một phương án minh họa là:

```text
thời_điểm_kết_thúc = giá_trị_sớm_nhất_của(
    thời_điểm_kích_hoạt + thời_lượng_được_duyệt,
    hạn_kết_thúc_tuyệt_đối_được_duyệt,
    giới_hạn_kết_thúc_theo_chính_sách
)
```

Ngoài thời điểm kết thúc, có thể cần một hạn chót để bắt đầu kích hoạt. Một yêu cầu được duyệt từ lâu không nên mặc nhiên dùng được vào bất kỳ thời điểm tương lai nào.

Ví dụ:

| Thời điểm | Sự kiện | Ý nghĩa |
| --- | --- | --- |
| 09:00 | Gửi yêu cầu cho 20 phút | Chưa có quyền |
| 09:02 | Duyệt; không được dùng sau 09:30 | Được phép kích hoạt trong giới hạn đã duyệt |
| 09:05 | Xác nhận quyền hiệu lực | Bắt đầu khoảng sử dụng 20 phút |
| 09:25 | Đến thời điểm kết thúc | Không được tiếp tục sử dụng; cơ chế hết hạn và thu hồi phải được thực thi |
| Sau khi kiểm tra thu hồi | Đóng yêu cầu | Có bằng chứng về kết quả kết thúc quyền |

Gia hạn cũng là một quyết định truy cập. Nó cần được kiểm tra theo chính sách, lưu lý do và đặt giới hạn mới; không nên tự động nối dài vô hạn chỉ vì một phiên còn đang mở.

### 6.3. Dùng thời gian đáng tin cậy

Quyết định hết hạn nên dựa trên thời gian được hệ thống thực thi tin cậy, không dựa vào đồng hồ mà người yêu cầu có thể tùy ý sửa. Khi có nhiều thành phần, cần tính đến chênh lệch đồng hồ và độ trễ truyền trạng thái.

Nếu cơ chế đích không đáp ứng được yêu cầu thu hồi đúng thời điểm, phải điều chỉnh thiết kế hoặc mô tả rõ độ trễ cho phép. Không nên hứa thu hồi tức thì khi nền tảng chỉ hỗ trợ hết hạn sau một khoảng trễ.

## 7. Vì sao thu hồi là phần khó?

### 7.1. Vai trò bị gỡ nhưng phiên vẫn hoạt động

Một hệ thống có thể đánh giá quyền ở thời điểm đăng nhập hoặc cấp token; hệ thống khác có thể đánh giá lại ở mỗi yêu cầu. Vì vậy, gỡ vai trò có thể ảnh hưởng đến lần truy cập mới nhưng chưa ảnh hưởng ngay đến phiên hiện có.

Các câu hỏi cần trả lời gồm:

- Token hoặc credential hiện có hết hạn lúc nào?
- Hệ thống đích có kiểm tra lại quyền trong phiên không?
- Có cơ chế thu hồi hoặc chấm dứt phiên không?
- Phiên có thể tự lấy token mới hay mở kết nối khác không?
- Việc kết thúc tại broker có chặn được mọi đường truy cập được phép không?

Không thể suy ra câu trả lời chỉ từ việc cổng PAM hiển thị một thời hạn. Cần dựa vào cơ chế xác thực, phân quyền và phiên của hệ thống đích.

### 7.2. Đổi credential không đồng nghĩa xóa quyền

Luân chuyển mật khẩu hoặc bí mật giúp xử lý phương tiện xác thực cũ. Nó không tự xóa quyền đã gán cho tài khoản và cũng không bảo đảm phiên hiện có bị chấm dứt.

Ngược lại, gỡ quyền không tự làm credential đã lộ trở nên vô hại cho mọi tài nguyên khác. Khi một credential được dùng chung ở nhiều nơi, việc ứng phó phức tạp hơn và có thể ảnh hưởng đến dịch vụ ngoài nhiệm vụ JIT ban đầu.

Vì vậy, cần phân biệt quản lý quyền, quản lý credential và quản lý phiên; phối hợp chúng theo cùng vòng đời yêu cầu.

### 7.3. Nhiều yêu cầu cùng tồn tại

Nếu nhiều lần kích hoạt cùng dùng một tài khoản và một vai trò, việc kết thúc một yêu cầu có thể vô tình gỡ quyền cần cho yêu cầu khác. Ngược lại, giữ vai trò cho yêu cầu còn hiệu lực có thể khiến người đã hết hạn vẫn dùng được quyền nếu họ chia sẻ cùng danh tính hoặc phiên.

Thiết kế cần theo dõi rõ quyền được tạo bởi lần kích hoạt nào và ai còn được dùng nó. Các lựa chọn có thể gồm danh tính tách biệt, phiên được ràng buộc riêng hoặc cơ chế đích hỗ trợ giới hạn theo lần cấp. Một bộ đếm số yêu cầu chưa đủ giải quyết quy trách nhiệm nếu mọi người vẫn biết cùng credential.

### 7.4. Lỗi mạng và thao tác dở dang

Lệnh cấp quyền có thể đã thành công ở đích nhưng phản hồi bị mất. Nếu hệ thống thử lại mà không đối chiếu trạng thái, nó có thể tạo bản cấp quyền trùng hoặc không biết cần thu hồi gì.

Một thiết kế đáng tin cậy cần mã tương quan cho từng lần cấp, thao tác có thể thử lại an toàn và bước đối chiếu trạng thái thực tế. Khi cấp quyền thành công một phần, phải ghi rõ phần đã tạo và xử lý thu hồi tương ứng.

Nếu hệ thống thu hồi đang lỗi, cần tiếp tục theo dõi và thử lại theo chính sách, đồng thời có cơ chế cảnh báo và xử lý. Tự gia hạn quyền để che lỗi sẽ làm mất ý nghĩa của thời hạn ban đầu.

## 8. Ví dụ: JIT cho xử lý sự cố dịch vụ

### 8.1. Nhu cầu

Kỹ sư trực ca cần khởi động lại dịch vụ A ở sản xuất. Công việc không cần đọc bí mật của dịch vụ B, đổi nhóm quản trị hay sửa chính sách vault.

Một yêu cầu minh họa:

| Thuộc tính | Giá trị |
| --- | --- |
| Người khởi tạo | Kỹ sư trực ca, dùng tài khoản cá nhân |
| Chức năng | Khởi động lại dịch vụ A |
| Đích | Dịch vụ A, môi trường sản xuất |
| Lý do | Mã sự cố đang xử lý |
| Thời lượng | 20 phút, theo chính sách của tình huống |
| Đường thực thi | Cổng vận hành gọi tác vụ giới hạn sẵn |
| Điều kiện kết thúc | Hoàn thành sớm, hết hạn hoặc bị hủy |

### 8.2. Thực thi quyền có giới hạn

Cổng vận hành kiểm tra danh tính, điều kiện trực ca và nội dung phê duyệt. Danh tính tác vụ chỉ có khả năng thực hiện thao tác đã xác định trên dịch vụ A. Tham số phải bị ràng buộc để yêu cầu không trở thành một cách chạy lệnh tùy ý.

Mã giả dưới đây mô tả logic, không phải cấu hình của một sản phẩm:

```text
khi_kích_hoạt(yêu_cầu):
    kiểm_tra danh_tính, phạm_vi, phê_duyệt_và_thời_hạn
    từ_chối nếu yêu_cầu_đã_hủy hoặc không_còn_hợp_lệ
    cấp quyền cho đúng hành_động và tài_nguyên
    xác_nhận kết_quả_cấp_quyền
    ghi mã_lần_cấp và thời_điểm_kết_thúc

khi_thực_hiện(lần_cấp, thao_tác):
    kiểm_tra lần_cấp còn_hợp_lệ
    kiểm_tra thao_tác khớp phạm_vi_được_duyệt
    thực_thi bằng danh_tính_được_chỉ_định
    ghi người_khởi_tạo, đích và kết_quả

khi_kết_thúc(lần_cấp):
    ngừng_chấp_nhận thao_tác_mới theo lần_cấp
    thu_hồi quyền_và_phương_tiện_truy_cập liên_quan
    đối_chiếu trạng_thái_tại_đích
    đóng nếu xác_nhận_thành_công
    nếu_lỗi: ghi trạng_thái_lỗi, cảnh_báo và tiếp_tục_xử_lý
```

Logic ở cổng chỉ kiểm soát những thao tác đi qua cổng. Nếu kỹ sư vẫn có đường đăng nhập trực tiếp bằng một tài khoản thường trực với cùng quyền, cần xử lý đường đó trong thiết kế PAM.

### 8.3. Kết thúc và điều tra

Sau khi hoàn thành, kỹ sư có thể kết thúc quyền sớm. Hệ thống lưu kết quả thao tác, thời điểm kết thúc và bằng chứng thu hồi. Nếu thao tác vẫn xảy ra sau thời hạn, dữ liệu cần giúp phân biệt nguyên nhân: phiên cũ chưa đóng, token còn được chấp nhận, sai cấu hình thời gian hoặc một đường truy cập khác.

Nhờ vậy, điều tra không chỉ dừng ở câu hỏi “ai đã đăng nhập?”, mà có thể xác định lần cấp quyền nào cho phép hành động nào và vì sao nó còn hiệu lực.

## 9. JIT cho tài khoản dịch vụ và workload

Với một pipeline triển khai, việc có người phê duyệt mỗi lần lấy credential có thể không phù hợp với cách vận hành. Thay vào đó, hệ thống có thể xác minh danh tính workload và điều kiện của lần chạy đã được cho phép.

Ví dụ, một lần chạy được phép triển khai ứng dụng A vào một môi trường xác định. Danh tính của lần chạy nhận credential tạm thời chỉ đủ cho hành động đó. Thời hạn phải phù hợp với công việc và việc gia hạn phải chịu cùng chính sách giới hạn.

Những điểm cần xác định gồm:

- Chủ sở hữu chịu trách nhiệm về danh tính và nhu cầu quyền của workload.
- Bằng chứng cho thấy lần chạy đến từ nguồn và quy trình được cho phép.
- Mối ràng buộc giữa credential, lần chạy, tài nguyên và môi trường.
- Cách ngăn một tác vụ dùng quyền của tác vụ hoặc môi trường khác.
- Điều gì xảy ra với credential, token và phiên khi tác vụ bị hủy hoặc kết thúc.
- Ai được thay đổi cấu hình pipeline hoặc chính sách cấp quyền cho workload.

Credential ngắn hạn làm giảm thời gian hữu dụng của một giá trị bị lộ, nhưng nếu bất kỳ workload nào cũng có thể yêu cầu lại credential quyền cao thì vấn đề phân quyền vẫn còn. Cơ chế cấp mới và gia hạn phải kiểm tra danh tính cùng phạm vi một cách có ý nghĩa.

## 10. Bằng chứng cho kiểm toán và ứng phó sự cố

Một chuỗi bằng chứng JIT cần nối được yêu cầu với quyền thực tế và hành động tại đích.

| Nhóm bằng chứng | Thông tin cần giữ |
| --- | --- |
| Nhu cầu | Mã yêu cầu, lý do, tham chiếu sự cố hoặc thay đổi |
| Danh tính | Người hoặc workload khởi tạo; danh tính thực thi |
| Quyết định | Chính sách áp dụng, điều kiện đã kiểm tra, người duyệt nếu có |
| Phạm vi | Chức năng, tài nguyên, môi trường, thời lượng và hạn kết thúc |
| Cấp quyền | Mã lần cấp, thời điểm yêu cầu và xác nhận, kết quả tại đích |
| Sử dụng | Hành động, đích thực tế, kết quả, dữ liệu phiên hoặc API phù hợp |
| Kết thúc | Lý do kết thúc, thu hồi đã thực hiện, thời điểm xác nhận và lỗi còn tồn tại |

Dấu thời gian và mã liên kết cần nhất quán để đối chiếu giữa cổng PAM, hệ thống danh tính, vault và hệ thống đích. Lưu bằng chứng phê duyệt mà thiếu bằng chứng sử dụng hoặc thu hồi sẽ làm chuỗi này không đầy đủ.

Không ghi credential, token hay nội dung bí mật vào log. Có thể ghi định danh bí mật hoặc credential được cấp, danh tính nhận và kết quả xử lý mà không sao chép giá trị xác thực.

Log cũng cần được bảo vệ theo quyền truy cập và chính sách lưu giữ phù hợp. Nếu người dùng đặc quyền có thể sửa hoặc xóa toàn bộ bằng chứng về chính hoạt động của họ, khả năng kiểm toán sẽ suy giảm.

## 11. Lỗi thiết kế thường gặp và cách nhận biết

| Lỗi | Dấu hiệu | Hướng xử lý |
| --- | --- | --- |
| JIT chỉ là một bộ đếm trên giao diện | Đến hạn nhưng hệ thống đích vẫn cho truy cập ngoài điều kiện cam kết | Xác định cơ chế thực thi thời hạn, phiên và xác nhận thu hồi |
| Cấp quyền quá rộng | Nhiệm vụ nhỏ nhưng nhận toàn quyền quản trị | Giới hạn chức năng, tài nguyên và tham số |
| Phê duyệt không ràng buộc nội dung | Đổi đích hoặc vai trò sau khi duyệt mà không đánh giá lại | Gắn quyết định với phạm vi cụ thể và quản lý thay đổi yêu cầu |
| Tư cách đủ điều kiện tồn tại không được rà soát | Người đã đổi nhiệm vụ vẫn kích hoạt được quyền | Rà soát chủ sở hữu và vòng đời quyền yêu cầu |
| Gia hạn vô hạn | Quyền “tạm thời” thực tế hoạt động liên tục | Đặt giới hạn, kiểm tra lại nhu cầu và theo dõi chuỗi gia hạn |
| Có đường truy cập bỏ qua JIT | Tài khoản hoặc credential khác vẫn mang cùng quyền thường trực | Kiểm kê các nguồn quyền và đường truy cập tương đương |
| Hủy tác vụ nhưng quên quyền | Pipeline đã dừng, credential hoặc vai trò vẫn dùng được | Gắn kết thúc tác vụ với thu hồi và cơ chế xử lý lỗi |
| Thu hồi lỗi nhưng vẫn đóng yêu cầu | Báo cáo hoàn thành chỉ dựa vào trạng thái cổng | Giữ trạng thái lỗi, đối chiếu đích và theo dõi đến khi xử lý xong |
| Dùng chung danh tính mà không ràng buộc phiên | Không biết ai còn dùng quyền sau khi một yêu cầu kết thúc | Tách danh tính hoặc phiên và giữ liên kết theo lần cấp |

Khi dịch vụ phê duyệt hoặc cấp quyền không hoạt động, cách xử lý yêu cầu mới phải được quy định rõ. Tránh tự chuyển một lỗi vận hành thành quyền thường trực. Nếu cần truy cập khẩn cấp, hãy có cơ chế riêng với điều kiện sử dụng, trách nhiệm và bằng chứng; sau sự kiện phải xử lý việc kết thúc quyền và credential liên quan.

## 12. Đánh giá một triển khai JIT

Những câu hỏi sau giúp kiểm tra thiết kế ở mức khái niệm:

1. Quyền nào còn thường trực và vì sao phải giữ lại?
2. Ai đủ điều kiện yêu cầu; ai có thể thay đổi tư cách đó?
3. Một lần kích hoạt có ràng buộc rõ hành động, tài nguyên, môi trường và thời hạn không?
4. Phê duyệt và điều kiện được kiểm tra vào những thời điểm nào?
5. Hệ thống xác nhận quyền hiệu lực và kết thúc bằng cách nào?
6. Token, phiên, kết nối và đường truy cập khác được xử lý ra sao?
7. Nếu cấp hoặc thu hồi lỗi một phần, ai theo dõi và xử lý?
8. Bằng chứng có nối được nhu cầu, quyết định, thực thi và kết thúc không?

Một số số liệu có thể hỗ trợ vận hành là thời gian chờ kích hoạt, tỷ lệ cấp quyền thành công, thời gian quyền hiệu lực, số lần gia hạn, số quyền thu hồi lỗi và độ trễ xác nhận thu hồi. Cần đọc các số liệu cùng nhau: kích hoạt nhanh nhưng nhiều quyền rộng hoặc thu hồi không đáng tin cậy chưa thể hiện một cơ chế JIT tốt.

Giảm thời gian quyền hoạt động cũng không tự chuyển thành một tỷ lệ giảm rủi ro cố định. Rủi ro còn phụ thuộc vào danh tính, phạm vi, tài nguyên và khả năng thực thi kiểm soát.

## 13. Bài tập vận dụng

Một nhóm tuyên bố đã dùng JIT vì vai trò quản trị tự bị gỡ sau 30 phút. Tuy nhiên, phiên được tạo trong khoảng đó có thể tiếp tục hoạt động; một tài khoản dịch vụ dùng chung vẫn có quyền tương đương; việc gia hạn được tự động chấp nhận khi người dùng chưa đóng cửa sổ làm việc.

Hãy phân tích:

- Đâu là quyền thường trực, đâu là quyền đủ điều kiện và đâu là quyền đang hiệu lực?
- Hệ thống đã giới hạn thời gian ở lớp nào, còn bỏ sót lớp nào?
- Vì sao việc gỡ vai trò chưa đủ chứng minh truy cập đã kết thúc?
- Cần thay đổi điều kiện gia hạn như thế nào?
- Những bằng chứng nào cần bổ sung để xác nhận thu hồi?

**Định hướng trả lời:** phải kiểm tra cơ chế quyền của phiên hiện có và cách chặn truy cập sau thời hạn; xử lý đường truy cập tương đương qua tài khoản dịch vụ; thay việc gia hạn dựa trên cửa sổ đang mở bằng đánh giá nhu cầu và giới hạn rõ ràng. Kết quả thu hồi cần dựa trên cơ chế thực thi và trạng thái tại đích, có liên kết với từng lần cấp quyền.

## 14. Ghi nhớ

JIT access đưa đặc quyền vào một vòng đời có điều kiện và thời hạn. Nó có giá trị khi quyền được cấp đúng lúc, đúng phạm vi, được sử dụng có thể truy vết và được kết thúc bằng một cơ chế có bằng chứng.

Để áp dụng trong PAM, hãy quản lý đồng thời quyền yêu cầu, quyền thực thi, credential, phiên và đường truy cập. Giới hạn thời gian cần đi cùng least privilege, JEA, giám sát và xử lý thu hồi; một thời hạn hiển thị riêng lẻ chưa đủ đại diện cho toàn bộ cơ chế.