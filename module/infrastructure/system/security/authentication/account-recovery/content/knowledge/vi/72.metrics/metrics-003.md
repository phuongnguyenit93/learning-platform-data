# Recovery failure rate — Tỷ lệ thất bại trong khôi phục tài khoản

## 1. Chỉ số này phải trả lời câu hỏi gì?

Trong hệ thống khôi phục tài khoản, một lượt không thành công có thể do người dùng không nhận được email, nhập sai mã quá nhiều lần, không vượt qua xác minh danh tính, bị chặn vì rủi ro hoặc rời luồng giữa chừng. Những tình huống ấy đều làm người dùng chưa lấy lại được quyền truy cập, nhưng không có cùng nguyên nhân và không dẫn đến cùng hành động xử lý.

**Recovery failure rate** là tỷ lệ các đơn vị khôi phục được xác định là thất bại trong một quần thể và khoảng quan sát đã công bố. Để con số có ý nghĩa, phải chỉ rõ đơn vị đếm, điều kiện thành công, kết quả nào được coi là thất bại, mẫu số và cách xử lý các lượt chưa biết kết quả.

Ví dụ, nhận định “tỷ lệ thất bại là 12%” chưa đủ để đánh giá hệ thống. Nó có thể nói về:

- Request HTTP trả lỗi trong năm phút gần nhất.
- Lượt khôi phục kết thúc không thành công trong ngày.
- Người dùng không hoàn tất khôi phục trong một thời hạn.
- Lần gửi thông báo bị provider từ chối.
- Lần kiểm tra mã bị verifier bác bỏ.

Đây là năm đại lượng khác nhau. Bài học này xây dựng phép đo ở cấp **lượt khôi phục**, đồng thời chỉ ra những chỉ số phụ giúp giải thích thất bại trong các luồng mất mật khẩu, mất MFA, mất passkey hoặc mất thiết bị xác thực.

Mục tiêu vận hành là giúp người dùng hợp lệ lấy lại quyền truy cập theo chính sách an toàn. Không được tối ưu tỷ lệ thành công bằng cách bỏ kiểm tra danh tính, kéo dài hiệu lực token tùy tiện hoặc giữ session nguy hiểm còn hoạt động.

## 2. Viết hợp đồng đo trước khi viết truy vấn

Một metric cần có định nghĩa mà đội sản phẩm, bảo mật, hỗ trợ và vận hành cùng hiểu. Hợp đồng tối thiểu gồm:

| Thành phần | Cần quyết định |
|---|---|
| Đơn vị đếm | Request, challenge, recovery attempt hay recovery journey? |
| Điểm bắt đầu | Server đã ghi nhận một attempt bền vững hay mới mở trang? |
| Quần thể | Toàn bộ attempt đã bắt đầu, một loại recovery hay một tập được xác định trước? |
| Thành công | Đã gửi email, đã xác minh hay đã hoàn tất thay đổi bảo mật cần thiết? |
| Thất bại | Kết quả cuối không thành công gồm những lớp nào? |
| Thời gian | Nhóm theo lúc bắt đầu hay lúc kết thúc? |
| Hạn quan sát | Deadline của luồng và độ trễ nhận dữ liệu là bao lâu? |
| Dữ liệu thiếu | Pending, sự kiện đến muộn và không rõ trạng thái được biểu diễn thế nào? |
| Loại trừ | Synthetic test, replay và request ngoài phạm vi được nhận diện ra sao? |
| Phiên bản | Định nghĩa và bộ phân loại có phiên bản nào? |

Có thể đặt tên đặc tả là `recovery-attempt-outcome-v1`. Đây là tên minh họa, không phải tiêu chuẩn bên ngoài.

Tài liệu [Google SRE: Implementing SLOs](https://sre.google/workbook/implementing-slos/) khuyến nghị biểu diễn nhiều SLI dưới dạng số sự kiện tốt chia tổng sự kiện, đồng thời phân biệt điều muốn đo với cách triển khai đo. Áp dụng vào recovery, cần thống nhất trước “lượt khôi phục đạt yêu cầu” rồi mới chọn nguồn dữ liệu và công thức.

### 2.1. Đừng thu hẹp mẫu số sau khi đã biết kết quả

Nếu chỉ đếm các lượt đã qua xác minh, những người bị kẹt ở bước nhận mã biến mất khỏi chỉ số. Nếu loại mọi lượt bị chặn bảo mật khỏi một báo cáo trước đây bao gồm chúng, tỷ lệ thất bại có thể giảm mà trải nghiệm không đổi.

Một phân khúc “có tín hiệu người dùng hợp lệ” chỉ hữu ích khi quy tắc xác định được công bố, có căn cứ và giữ nhất quán. Không thể biết chắc mọi người gọi endpoint công khai là chủ tài khoản. Cũng không thể mặc định mọi lượt bị từ chối là tấn công.

Nên giữ báo cáo toàn bộ quần thể, rồi thêm các góc nhìn có nhãn rõ:

- Toàn bộ attempt được server ghi nhận.
- Luồng và nhóm rủi ro tại thời điểm bắt đầu.
- Quần thể có bằng chứng độc lập phù hợp với mục tiêu phân tích.
- Lượt đã được xác nhận liên quan sự cố, với thời gian đủ để cập nhật kết luận.

Nếu một kết luận điều tra đến muộn làm thay đổi phân loại, lưu phiên bản báo cáo thay vì âm thầm đổi số lịch sử.

### 2.2. Có những lỗi xảy ra trước điểm bắt đầu

Một sự cố DNS, gateway hoặc lưu database có thể khiến người dùng không tạo được attempt. Metric chỉ dựa trên attempt đã ghi nhận sẽ không thấy đầy đủ các lỗi ấy.

Vì vậy cần một SLI riêng cho khả năng bắt đầu recovery, sử dụng nguồn quan sát phù hợp ở phía client, edge và server. Không cộng request lỗi trước điểm bắt đầu vào tử số của attempt failure rate nếu chúng không thuộc mẫu số tương ứng.

## 3. Chọn đúng đơn vị đếm

### 3.1. Request không đồng nghĩa attempt

Một attempt có thể bao gồm:

1. Khởi tạo yêu cầu.
2. Gửi challenge.
3. Gửi lại mã.
4. Hai lần kiểm tra mã không đạt.
5. Một lần kiểm tra đạt.
6. Hoàn tất thay đổi credential.
7. Thực thi các điều kiện bảo mật sau recovery theo policy.

Nếu lượt này cuối cùng đạt điều kiện thành công, kết quả attempt là thành công. Hai lần kiểm tra mã không đạt vẫn thuộc metric verifier nhưng không biến attempt thành hai lần khôi phục thất bại.

Ngược lại, HTTP 200 hoặc 202 ở endpoint yêu cầu khôi phục thường chỉ phản ánh việc xử lý request theo giao thức. Nó không chứng minh email đã tới, người gọi là chủ tài khoản hay recovery đã hoàn tất.

[OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html) yêu cầu thông điệp nhất quán và thời gian phản hồi đồng đều cho tài khoản tồn tại và không tồn tại để hạn chế dò tài khoản. Vì vậy, không suy kết quả recovery nội bộ chỉ từ response công khai.

### 3.2. Attempt và journey có thể cùng cần thiết

**Attempt** là một lượt có định danh ổn định và vòng đời được server quản lý. Một mã gửi lại hoặc HTTP retry với cùng ngữ nghĩa không nhất thiết tạo attempt mới.

**Journey** là hành trình lớn hơn theo quy tắc sản phẩm: người dùng thử khôi phục bằng email, chuyển qua recovery code rồi cần hỗ trợ thủ công. Nó có thể bao gồm nhiều attempt.

Nếu attempt đầu thất bại và attempt sau thành công:

- Attempt failure rate vẫn ghi nhận thất bại đầu tiên.
- Journey có thể được tính thành công nếu đáp ứng quy tắc hoàn tất của journey.
- Thời gian khôi phục của journey vẫn phản ánh chi phí của các lần thử trước.

Đừng gộp journey theo email thô hoặc địa chỉ IP. IP dùng chung và trình duyệt khác nhau có thể gây gộp nhầm; kẻ tấn công cũng có thể gửi yêu cầu cho cùng tài khoản. Việc liên kết cần căn cứ và quyền truy cập phù hợp, không tạo thêm khả năng dò tài khoản qua giao diện công khai.

### 3.3. Retry và idempotency phải có quy tắc ổn định

Request được gửi lại do mất kết nối không nên tạo thêm terminal outcome cho cùng một attempt. Server cần kiểm soát idempotency theo phạm vi tenant, operation và danh tính/ngữ cảnh được phép; không tin một attempt ID tùy ý do client cung cấp.

Nếu sản phẩm chủ động cho bắt đầu attempt mới sau khi lượt cũ đã kết thúc, hai attempt được đếm riêng. Quy tắc này phải nhất quán theo thời gian. Không thay việc tạo ID chỉ để làm mẫu số tăng.

## 4. Thành công phải gắn với mục tiêu bảo mật của từng luồng

Điểm thành công nên do state machine phía server xác nhận, không lấy từ thông điệp trên trình duyệt.

| Luồng | Ví dụ điều kiện kết thúc thành công | Chưa đủ để kết luận thành công |
|---|---|---|
| Quên mật khẩu | Đã chấp nhận bằng chứng, cập nhật credential và hoàn tất các điều kiện sau recovery theo policy | Token đã được phát |
| Mất MFA | Đã đạt mức xác minh cần thiết, thực hiện thay đổi MFA được phép và kiểm soát quyền của session liên quan | Nhân viên mở ticket |
| Mất passkey | Đã hoàn tất luồng khôi phục và thao tác authenticator theo yêu cầu; không trao thêm quyền chỉ vì có yêu cầu | Người dùng mở trang đăng ký |
| Mất thiết bị | Đã hoàn tất phương án thay thế được chấp nhận và các bước bảo vệ tương ứng | Provider nhận yêu cầu gửi SMS |
| Nghi bị chiếm tài khoản | Đã thực hiện những điều kiện khôi phục quyền kiểm soát mà policy quy định | Chỉ đổi được mật khẩu |

Không phải mọi luồng cần cùng một tập điều kiện. Hãy định nghĩa rõ thao tác nào là bắt buộc để đóng attempt, thao tác nào được theo dõi riêng và giới hạn bảo đảm của hệ thống.

Nếu revocation session là điều kiện bắt buộc, sự kiện “đã gửi yêu cầu revocation” không tự chứng minh điều kiện ấy đã hoàn tất. Cần bằng chứng theo cơ chế thực tế, chẳng hạn version bảo mật đã được enforce ở nơi kiểm tra quyền, trong phạm vi mà đặc tả yêu cầu.

Đối với recovery khi nghi ngờ bị xâm phạm, OWASP lưu ý mật khẩu mới có thể chưa đủ nếu kẻ tấn công còn session hoặc đã đổi yếu tố khôi phục. Điểm thành công phải phản ánh các biện pháp bảo vệ được lựa chọn cho tình huống đó. Tham khảo phần [Account Recovery After Suspected Compromise](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#account-recovery-after-suspected-compromise).

**Kết quả workflow cũng không tự chứng minh người khôi phục là chủ tài khoản hợp lệ.** Attempt có thể được hệ thống ghi thành công rồi sau đó bị xác nhận là chiếm đoạt tài khoản. Chỉ số chất lượng bảo mật sau recovery cần được theo dõi bổ sung.

## 5. Phân loại kết quả cuối và nguyên nhân

Có thể dùng tập outcome phục vụ phân tích như sau. Đây là schema minh họa; không yêu cầu đổi tên trạng thái nghiệp vụ hiện có.

| Outcome đo lường | Ý nghĩa |
|---|---|
| `SUCCEEDED` | Đạt điều kiện thành công đã công bố |
| `FAILED_TECHNICAL` | Kết thúc do lỗi kỹ thuật khiến không hoàn tất được |
| `FAILED_VERIFICATION` | Kết thúc do không đáp ứng yêu cầu xác minh |
| `DENIED_POLICY` | Kết thúc vì policy hoặc kiểm soát rủi ro từ chối |
| `EXPIRED` | Attempt hết thời hạn theo định nghĩa của luồng |
| `CANCELLED` | Attempt được hủy bằng một hành động đã ghi nhận |
| `FAILED_OTHER` | Biết đã kết thúc không thành công nhưng chưa phân loại được vào các nhóm trên |

Từ đây, bài học quy ước **terminal non-success**, tức kết quả cuối không thành công, bao gồm tất cả các outcome trong bảng trừ `SUCCEEDED`. Khi dashboard viết ngắn là “failure rate”, nó phải hiển thị hoặc liên kết được quy ước này.

Tỷ lệ lỗi kỹ thuật là một chỉ số thành phần, không bằng tỷ lệ toàn bộ kết quả cuối không thành công.

### 5.1. Pending và unknown không phải outcome thất bại mặc định

- **Pending:** trạng thái đã biết, lượt vẫn chưa có kết quả cuối tại mốc quan sát.
- **Unknown:** dữ liệu hiện có không đủ để xác định trạng thái/kết quả.
- **Failed other:** đã biết lượt kết thúc không thành công nhưng chưa rõ lớp nguyên nhân.

Unknown không được tự đổi thành failed other. Trường hợp thiếu một event kết thúc không chứng minh nghiệp vụ đã thất bại.

Attempt hết deadline nhưng scheduler chưa chạy có thể xuất hiện là pending quá hạn. Hệ thống cần reconciliation để phát hiện và xử lý theo state machine. Dashboard đo chất lượng dữ liệu nên làm rõ khoảng lệch ấy.

### 5.2. Lỗi từng bước có thể khôi phục được

Một provider timeout, một callback trùng hoặc một lần nhập sai OTP chưa đủ để kết luận attempt thất bại. Attempt có thể thử lại, chuyển provider hoặc dùng phương án khác.

Chỉ ghi outcome cuối khi lượt thật sự kết thúc theo quy tắc. Các lỗi tạm thời vẫn được ghi ở cấp operation để giải thích latency và chi phí retry.

### 5.3. Chọn nguyên nhân chính theo quy tắc, giữ các yếu tố đóng góp

Một attempt có thể bị gửi email chậm, gặp mã hết hạn rồi bị hủy. Nếu mỗi nguyên nhân đều được cộng vào tử số độc lập, một attempt sẽ trở thành nhiều thất bại.

Nên có:

- Một outcome cuối cho mỗi attempt.
- Một nhóm nguyên nhân chính theo bộ phân loại có phiên bản.
- Danh sách yếu tố đóng góp trong dữ liệu phân tích có kiểm soát.

Ví dụ, email tới chậm là yếu tố đóng góp, còn kết quả cuối là expired. Nếu điều tra xác nhận lỗi provider là nguyên nhân chính, báo cáo nguyên nhân có thể bổ sung kết luận đó. Không đếm thêm một attempt thất bại chỉ vì biết thêm nguyên nhân.

## 6. Ba phép đo thường bị nhầm với nhau

Gọi:

- `C`: tập attempt trong một cohort bắt đầu đã chọn.
- `S`: số attempt thành công.
- `F`: số attempt kết thúc không thành công theo quy ước ở trên.
- `P`: số attempt còn pending tại snapshot.
- `U`: số attempt chưa rõ trạng thái.
- `N = |C| = S + F + P + U`.

Các tập phải loại trừ nhau; mỗi attempt chỉ thuộc một nhóm tại cùng snapshot.

### 6.1. Tỷ lệ thất bại trong các lượt đã kết thúc

~~~text
Resolved failure rate = F / (S + F)
~~~

Đây là đại lượng mô tả kết quả cuối trong phần cohort đã có kết quả. Mẫu số không chứa pending và unknown, vì vậy cần công bố thêm:

~~~text
Resolution coverage = (S + F) / N
Pending ratio       = P / N
Unknown ratio       = U / N
~~~

Một tỷ lệ thất bại thấp với coverage rất thấp có thể chỉ là phần thất bại chưa được ghi nhận.

Nếu `S + F = 0`, kết quả là không có dữ liệu để tính, thường hiển thị N/A. Không gán 0% và không dùng một mẫu số giả bằng 1.

### 6.2. Tỷ lệ lỗi kỹ thuật trong các lượt đã kết thúc

~~~text
Technical failure share among resolved
    = F_technical / (S + F)
~~~

Còn:

~~~text
Technical contribution among failures
    = F_technical / F
~~~

Đại lượng đầu cho biết lỗi kỹ thuật chiếm bao nhiêu trong toàn bộ lượt đã kết thúc. Đại lượng sau cho biết cơ cấu nguyên nhân trong những lượt không thành công. Chúng không có cùng mẫu số.

Cũng có thể đo lỗi kỹ thuật trên toàn bộ cohort `F_technical / N`; phải đặt tên riêng và không so trực tiếp với chỉ số trên nếu coverage thay đổi.

### 6.3. Tỷ lệ chưa xác nhận thành công trước deadline

Khi sản phẩm quan tâm “người dùng có hoàn tất trong thời hạn D không?”, nên dùng một chỉ số theo deadline:

~~~text
Confirmed success by deadline = S_D / N_D
No confirmed success by deadline = 1 - S_D / N_D
~~~

Trong đó:

- `N_D` chỉ chứa attempt đã tới deadline quan sát.
- `S_D` là các attempt có bằng chứng thành công không muộn hơn deadline của chính lượt đó.
- Dữ liệu được đọc ở một snapshot có độ trễ nhận sự kiện được kiểm soát.

Phần chưa xác nhận thành công có thể bao gồm thất bại đã biết và dữ liệu chưa đủ. Chỉ số này không tự cho phép kết luận toàn bộ phần ấy là lỗi kỹ thuật hoặc người dùng từ bỏ.

Một tổ chức có thể quy định thiếu bằng chứng thành công sẽ tính vào phần không đạt SLI. Đó là hợp đồng đo dịch vụ được công bố, không phải suy luận về nguyên nhân thất bại thực tế.

Nếu attempt thành công sau D, nó có thể là thành công cuối cùng nhưng vẫn không đạt mục tiêu hoàn tất trước D. Giữ cả hai góc nhìn để biết mức độ chậm trễ.

## 7. Cohort, cửa sổ thời gian và dữ liệu đến muộn

### 7.1. Cohort theo lúc bắt đầu

Cohort theo lúc bắt đầu trả lời:

> Những lượt bắt đầu trong khoảng [a, b) đã có kết quả ra sao?

Ưu điểm là có cùng quần thể khi đánh giá một thay đổi giao diện, policy hoặc provider. Nhược điểm là cần chờ đủ lâu để nhiều lượt kết thúc.

Một lượt bắt đầu trước nửa đêm và kết thúc sau nửa đêm vẫn thuộc cohort theo thời điểm bắt đầu. Dùng khoảng nửa mở `[a, b)` và ghi timezone để không đếm hai lần ở ranh giới.

### 7.2. Cửa sổ theo lúc kết thúc

Cửa sổ theo lúc kết thúc trả lời:

> Trong các lượt kết thúc gần đây, tỷ lệ không thành công là bao nhiêu?

Góc nhìn này hữu ích cho giám sát gần thời gian thực. Tuy nhiên, lượt thành công nhanh và lượt hết hạn chậm có thể đến từ các cohort khác nhau. Tỷ lệ có thể tăng khi một loạt attempt cũ cùng hết hạn dù dịch vụ vừa phục hồi.

Không chia “số attempt thất bại kết thúc trong 5 phút” cho “số attempt bắt đầu trong 5 phút”. Hai tập không tương ứng; kết quả thậm chí có thể vượt 100%.

### 7.3. Hạn token, hạn attempt và hạn đo không nhất thiết giống nhau

Một OTP có thể hết hạn trong vài phút, còn journey cần hỗ trợ thủ công kéo dài lâu hơn. Mã mới có thể được phát trong cùng attempt hoặc thuộc attempt mới tùy thiết kế.

Định nghĩa ba mốc riêng:

1. Hạn sử dụng của một challenge/token.
2. Hạn nghiệp vụ của attempt.
3. Deadline hoàn tất mà sản phẩm muốn đo.

Không kéo dài hạn credential để làm đẹp metric. Nếu các loại recovery có deadline khác nhau, so sánh chúng theo từng loại hoặc nêu rõ cách chuẩn hóa.

### 7.4. Watermark và phiên bản snapshot

Sự kiện có thể xảy ra đúng hạn nhưng tới kho phân tích muộn. Cần phân biệt:

- `occurred_at`: thời điểm chuyển trạng thái ở nguồn có thẩm quyền.
- `ingested_at`: thời điểm pipeline nhận sự kiện.
- `snapshot_at`: thời điểm chốt dữ liệu cho báo cáo.

Watermark là mốc mà pipeline đánh giá dữ liệu sự kiện đã được xử lý đến đó, với mức bảo đảm cụ thể. Nó không phải lời hứa tuyệt đối rằng không thể có dữ liệu đến muộn.

Cohort chín cho phép đo deadline khi mọi attempt trong phần đang báo cáo đã tới deadline, và snapshot có độ bao phủ dữ liệu phù hợp. Nếu nguồn còn gián đoạn, báo chất lượng dữ liệu suy giảm.

Báo cáo có thể có trạng thái provisional rồi finalized theo quy tắc. Nếu bổ sung sự kiện đến muộn, lưu thời điểm cập nhật và phiên bản. Không tự kéo một sự kiện hoàn tất muộn về trước deadline dựa trên thời gian client khai báo.

## 8. Ví dụ tính đủ tử số, mẫu số và phần thiếu

Giả sử một cohort có 1.000 attempt, mọi lượt đã tới deadline đo. Tại snapshot, trạng thái được phân loại như sau:

| Nhóm | Số lượt |
|---|---:|
| Thành công đúng hạn | 700 |
| Thất bại kỹ thuật | 40 |
| Không đạt xác minh | 60 |
| Bị policy từ chối | 100 |
| Hết hạn | 50 |
| Hủy đã được ghi nhận | 20 |
| Không thành công, chưa phân loại nguyên nhân | 10 |
| Pending quá deadline | 15 |
| Không rõ trạng thái | 5 |
| **Tổng** | **1.000** |

Trong ví dụ này, các kết quả cuối đã biết đều xảy ra trong deadline; không có kết quả thành công muộn.

~~~text
S = 700
F = 40 + 60 + 100 + 50 + 20 + 10 = 280
P = 15
U = 5

Resolved failure rate = 280 / 980 ≈ 28,57%
Resolution coverage   = 980 / 1.000 = 98%
Technical share among resolved = 40 / 980 ≈ 4,08%
Technical contribution among failures = 40 / 280 ≈ 14,29%
No confirmed success by deadline = 300 / 1.000 = 30%
~~~

Không nên báo “30% lỗi hệ thống”. Trong 300 lượt chưa xác nhận thành công có từ chối bảo mật, không đạt xác minh, hết hạn, hủy và 20 lượt chưa đủ kết luận.

Với 20 lượt chưa rõ kết quả cuối, tỷ lệ không thành công thực tế của toàn cohort nằm trong khoảng từ 28% đến 30%, nếu các outcome đã biết là chính xác. Đây là khoảng do dữ liệu thiếu theo cách gán cực trị, không phải khoảng tin cậy thống kê.

Nếu sau đó 20 lượt ấy đều có bằng chứng thành công đúng hạn, tỷ lệ cuối là 28%. Nếu đều là thất bại đúng hạn, tỷ lệ cuối là 30%. Con số 28,57% ban đầu chỉ mô tả 980 lượt đã có kết quả.

Một báo cáo rõ ràng nên hiển thị số lượt, tỷ lệ, coverage, snapshot và định nghĩa thay vì chỉ một phần trăm màu xanh hoặc đỏ.

## 9. Thiết kế sự kiện để tính lại được kết quả

### 9.1. Chọn nguồn có thẩm quyền

Browser event như “đã bấm nút hoàn tất” hữu ích cho phân tích giao diện, nhưng không nên là nguồn duy nhất cho kết quả bảo mật. Trình duyệt có thể đóng, mất mạng hoặc gửi dữ liệu giả.

Nguồn kết quả nên xuất phát từ chuyển trạng thái đã commit ở hệ thống quản lý attempt. Một event minh họa:

~~~json
{
  "event_id": "evt-demo-93",
  "schema_version": 1,
  "event_type": "RECOVERY_ATTEMPT_FINALIZED",
  "attempt_ref": "attempt-demo-17",
  "tenant_ref": "tenant-demo",
  "state_version": 8,
  "flow": "mfa_recovery",
  "started_at": "2026-11-20T01:00:00Z",
  "finalized_at": "2026-11-20T01:08:00Z",
  "outcome": "FAILED_TECHNICAL",
  "primary_reason": "credential_commit_unavailable",
  "policy_revision": "recovery-policy-demo-4",
  "metric_definition": "recovery-attempt-outcome-v1"
}
~~~

Các giá trị trên hoàn toàn là dữ liệu minh họa. Trong hệ thống thực, reference phải được quản lý như dữ liệu có thể liên kết tới tài khoản, kể cả khi không chứa tên hay email.

Không đưa vào event đo lường:

- Mật khẩu, OTP, recovery code hoặc reset token còn nguyên.
- URL khôi phục có secret trong query hoặc fragment.
- Cookie, Authorization header hay session bearer token.
- Tài liệu xác minh danh tính và nội dung trao đổi hỗ trợ không cần thiết.
- Request/response body chưa được loại dữ liệu nhạy cảm.

Reason nên lấy từ enum có kiểm soát, không dùng trực tiếp thông báo exception tự do. Một chuỗi lỗi của provider có thể chứa dữ liệu người dùng hoặc thay đổi liên tục.

### 9.2. Commit nghiệp vụ và phát event phải phối hợp

Nếu database đã đổi credential nhưng tiến trình chết trước lúc tăng counter, metric có thể bỏ sót kết quả. Nếu tăng counter trước commit rồi transaction rollback, metric có thể đếm một thành công chưa xảy ra.

Một mẫu thiết kế là transactional outbox:

~~~text
BEGIN

  Kiểm tra attempt, version và quyền thực hiện chuyển trạng thái.
  Cập nhật attempt theo state machine.
  Ghi event kết thúc vào outbox trong cùng transaction.

COMMIT

  Publisher đọc outbox và gửi event.
  Consumer nhận event, kiểm tra schema và loại bản trùng.
  Projection lưu một kết quả chuẩn cho từng attempt.
~~~

State transition cần kiểm soát đồng thời, chẳng hạn cập nhật có điều kiện theo version. Nếu hai request cùng hoàn tất một token dùng một lần, chỉ chuyển trạng thái hợp lệ được ghi nhận là kết quả chuẩn.

Outbox hỗ trợ tránh khoảng hở giữa commit và phát event, nhưng delivery vẫn có thể lặp. Không gọi toàn bộ pipeline là “exactly once” chỉ vì đã có outbox.

### 9.3. Phân biệt chống trùng event với chống trùng attempt

Có hai loại lỗi thường gặp:

1. Cùng một event được giao lại nhiều lần.
2. Hai event khác nhau cùng mô tả một kết quả cuối của cùng attempt.

Loại thứ nhất có thể phát hiện bằng event ID trong phạm vi producer tương ứng. Loại thứ hai cần kiểm soát bằng state version và quy tắc kết thúc của attempt.

Một projection chuẩn thường cần khóa định danh gồm tenant và attempt, cùng các ràng buộc phù hợp cho event ID/version. Nó không chỉ là câu lệnh đếm số event kết thúc.

Nếu phát hiện outcome cuối xung đột, đưa vào đối soát và báo chất lượng dữ liệu. Không tùy tiện chọn event có thời gian client mới nhất.

Nếu nghiệp vụ cần sửa kết quả đã ghi, dùng cơ chế correction có audit và phiên bản. Đừng trừ một counter Prometheus đã phát để giả lập sửa lịch sử; hãy tính lại báo cáo chuẩn từ dữ liệu bền vững.

### 9.4. Counter vận hành không thay thế sổ kết quả

Một consumer có dedup bền vững vẫn có thể chết giữa việc lưu dấu đã xử lý và tăng counter trong RAM. Tùy thứ tự, counter có thể bị thiếu hoặc lặp.

Vì vậy nên phân vai:

- Projection hoặc kho dữ liệu có đối soát phục vụ báo cáo chuẩn và tính lại cohort.
- Counter phục vụ quan sát biến động nhanh với các giới hạn được công bố.
- Reconciliation so sánh số attempt bắt đầu, số outcome và trạng thái nguồn để phát hiện thiếu/lặp.

Không lấy cam kết chính xác của kho dữ liệu áp cho mọi time series được scrape từ ứng dụng.

## 10. Truy vấn SQL theo cohort đã định nghĩa

Giả sử có bảng snapshot phân tích `recovery_attempt_snapshot`, một dòng cho mỗi bộ khóa:

~~~text
(snapshot_id, metric_definition, tenant_ref, attempt_ref)
~~~

Các trường phục vụ ví dụ:

| Trường | Ý nghĩa |
|---|---|
| `started_at` | Điểm bắt đầu theo server |
| `measurement_deadline_at` | Deadline đo đã được xác định theo hợp đồng |
| `outcome_bucket` | Một outcome cuối, PENDING hoặc UNKNOWN tại snapshot |
| `success_by_deadline` | Có bằng chứng thành công đúng hạn; có thể chưa xác định |
| `flow` | Loại recovery theo taxonomy |
| `snapshot_id` | Snapshot dữ liệu bất biến dùng cho báo cáo |
| `metric_definition` | Phiên bản định nghĩa metric |

Quan trọng: snapshot phải được dựng từ danh sách attempt bắt đầu đầy đủ, rồi nối dữ liệu kết quả. Nếu dựng bảng chỉ từ event kết thúc, pending và những lượt mất event sẽ không có dòng để đếm.

Deadline đo phải được xác định theo quy tắc có phiên bản, không lấy thời điểm hết hạn vừa bị sửa sau sự cố để viết lại mục tiêu lịch sử.

Truy vấn sau dùng cú pháp PostgreSQL và giả định bảng đã có ràng buộc các giá trị outcome hợp lệ:

~~~sql
WITH cohort AS (
    SELECT outcome_bucket, success_by_deadline
    FROM recovery_attempt_snapshot
    WHERE snapshot_id = :snapshot_id
      AND metric_definition = :metric_definition
      AND started_at >= :cohort_start
      AND started_at < :cohort_end
      AND measurement_deadline_at <= :observation_horizon
),
counts AS (
    SELECT
        COUNT(*) AS n_started,
        COUNT(*) FILTER (
            WHERE outcome_bucket = 'SUCCEEDED'
        ) AS n_success,
        COUNT(*) FILTER (
            WHERE outcome_bucket IN (
                'FAILED_TECHNICAL',
                'FAILED_VERIFICATION',
                'DENIED_POLICY',
                'EXPIRED',
                'CANCELLED',
                'FAILED_OTHER'
            )
        ) AS n_non_success,
        COUNT(*) FILTER (
            WHERE outcome_bucket = 'FAILED_TECHNICAL'
        ) AS n_technical,
        COUNT(*) FILTER (
            WHERE outcome_bucket = 'PENDING'
        ) AS n_pending,
        COUNT(*) FILTER (
            WHERE outcome_bucket = 'UNKNOWN'
        ) AS n_unknown,
        COUNT(*) FILTER (
            WHERE success_by_deadline IS TRUE
        ) AS n_success_by_deadline
    FROM cohort
)
SELECT
    n_started,
    n_success,
    n_non_success,
    n_pending,
    n_unknown,
    ROUND(
        100.0 * n_non_success
        / NULLIF(n_success + n_non_success, 0),
        2
    ) AS resolved_failure_pct,
    ROUND(
        100.0 * (n_success + n_non_success)
        / NULLIF(n_started, 0),
        2
    ) AS resolution_coverage_pct,
    ROUND(
        100.0 * n_technical
        / NULLIF(n_success + n_non_success, 0),
        2
    ) AS technical_share_of_resolved_pct,
    ROUND(
        100.0 * (n_started - n_success_by_deadline)
        / NULLIF(n_started, 0),
        2
    ) AS no_confirmed_success_by_deadline_pct
FROM counts;
~~~

Các điểm cần hiểu khi sử dụng:

1. `observation_horizon` là mốc hạn đo đang xét; snapshot phải được thu sau đó với quy tắc độ trễ dữ liệu đã công bố.
2. Các attempt chưa tới deadline bị lọc ra. Nếu muốn báo cáo toàn bộ cohort, cần chờ đủ lâu hoặc trình bày riêng phần chưa chín.
3. `NULLIF` giữ mẫu số 0 thành NULL. Giao diện nên hiển thị N/A.
4. Outcome ở snapshot là kết quả cuối được biết tại snapshot. Một lượt có thể thành công muộn và vẫn có `success_by_deadline = false`.
5. Tử số “chưa xác nhận thành công đúng hạn” bao gồm phần chưa đủ bằng chứng, như đã định nghĩa ở mục 6.
6. Nếu lọc tenant hoặc flow, áp cùng bộ lọc vào toàn bộ cohort trước khi tính các tử số và mẫu số.

Đây là ví dụ truy vấn, không phải mô tả một bảng đã tồn tại trong ứng dụng. Không chạy SQL lên production chỉ vì ví dụ dùng tên trường quen thuộc.

### 10.1. Đối soát số lượng trước khi đọc tỷ lệ

Với taxonomy đã nêu, kiểm tra:

~~~text
n_started
  = n_success + n_non_success + n_pending + n_unknown
~~~

Nếu không khớp, có thể có outcome mới chưa được ánh xạ, join nhân bản dòng hoặc dữ liệu snapshot không đầy đủ.

Nếu một attempt có nhiều provider operation, cần tổng hợp operation trước khi join vào fact attempt. Một phép join trực tiếp một-nhiều có thể làm một lượt thất bại bị đếm nhiều lần dù đã chống trùng event ở tầng trước.

## 11. Counter và PromQL cho quan sát gần thời gian thực

### 11.1. Một metric terminal có tập label hữu hạn

Có thể định nghĩa counter minh họa:

~~~text
recovery_attempt_completed_total{
  flow="password_reset",
  result="success",
  failure_class="none"
}
~~~

Quy ước:

- Chỉ tăng khi ghi nhận một kết quả cuối.
- `result` chỉ có success hoặc non_success.
- `failure_class` lấy từ tập none, technical, verification, policy, expired, cancelled, other.
- Success luôn đi với failure_class=none.
- Mỗi attempt chỉ đóng góp một lần cho metric này trong mô hình đo, với các giới hạn delivery/counter đã giải thích.

Tên có hậu tố `_total` thể hiện counter. Tài liệu [Prometheus: Instrumentation](https://prometheus.io/docs/practices/instrumentation/) khuyến nghị có cả số lỗi và số lần thử tương ứng để tính tỷ lệ, đồng thời nhất quán về thời điểm đếm.

Không dùng label như account ID, email, số điện thoại, attempt ID, token ID, session ID hoặc IP. Hash ID vẫn tạo số lượng giá trị rất lớn và còn có thể liên kết dữ liệu. [Prometheus: Metric and label naming](https://prometheus.io/docs/practices/naming/) cảnh báo mỗi tổ hợp label tạo time series mới và không nên dùng các chiều không giới hạn như ID người dùng hay email.

Flow và failure class cũng cần enum giới hạn. Không đưa toàn bộ exception message hoặc policy revision tăng liên tục vào label của counter tích lũy.

### 11.2. Tỷ lệ kết quả cuối không thành công trong 15 phút

~~~promql
sum by (flow) (
  increase(
    recovery_attempt_completed_total{result="non_success"}[15m]
  )
)
/
sum by (flow) (
  increase(recovery_attempt_completed_total[15m])
)
~~~

Kết quả ở dạng 0–1; định dạng phần trăm ở dashboard hoặc nhân 100 khi cần.

Đây là **cửa sổ theo lúc kết thúc**, không phải cohort theo lúc bắt đầu. Nó cũng chưa cho biết pending hoặc lượt không tới được điểm tạo attempt.

Tính `increase` trên từng time series trước rồi mới cộng giúp xử lý counter reset theo từng instance. Không lấy hiệu thô của tổng counter để suy số lượt sau restart.

`increase` dùng dữ liệu scrape và ngoại suy trong khoảng quan sát nên có thể cho số lẻ. Các kết quả này phù hợp giám sát; không thay thế số đếm đã đối soát trong báo cáo cohort.

### 11.3. Tách phần lỗi kỹ thuật

~~~promql
sum by (flow) (
  increase(
    recovery_attempt_completed_total{
      result="non_success",
      failure_class="technical"
    }[15m]
  )
)
/
sum by (flow) (
  increase(recovery_attempt_completed_total[15m])
)
~~~

Đây là phần lỗi kỹ thuật trong các lượt kết thúc. Nếu traffic tấn công làm số từ chối policy tăng mạnh, mẫu số cũng tăng và có thể che bớt phần lỗi kỹ thuật.

Bởi vậy, đọc thêm số lỗi tuyệt đối, volume, các tỷ lệ theo luồng và SLI cho operation kỹ thuật cụ thể. Không mặc định metric này chính là độ tin cậy cho người dùng hợp lệ.

### 11.4. Không có traffic khác với không có telemetry

Khi mẫu số bằng 0, tỷ lệ không xác định. Khi scrape mất hoặc collector lỗi, không có time series không có nghĩa hệ thống đang không phát sinh lỗi.

Cần theo dõi heartbeat, scrape health và độ mới của pipeline. Có thể khởi tạo các series có tập giá trị hữu hạn ở 0 để dashboard hiển thị nhất quán, nhưng vẫn phải kiểm tra nguồn dữ liệu có hoạt động.

Tránh dùng `or vector(0)` hoặc ép mẫu số thành 1 một cách đại trà. Những cách ấy có thể biến mất dữ liệu thành một đường “0% thất bại” rất dễ gây hiểu nhầm.

## 12. Đọc funnel để tìm điểm gây thất bại

Một funnel minh họa:

~~~mermaid
flowchart LR
    A[Attempt bắt đầu] --> B[Challenge khả dụng]
    B --> C[Bằng chứng được chấp nhận]
    C --> D[Thay đổi credential được commit]
    D --> E[Đạt điều kiện bảo mật sau recovery]
    E --> F[Attempt thành công]
    A --> G[Kết quả cuối không thành công]
    B --> G
    C --> G
    D --> G
    E --> G
~~~

Không phải mọi flow đều đi qua đúng các bước này. Ví dụ recovery code có thể không cần gửi challenge qua provider. Funnel phải có các nhánh rõ ràng hoặc được tách theo flow; không coi bước không áp dụng là một thất bại.

Cần phân biệt:

| Chỉ số | Câu hỏi |
|---|---|
| Request error rate | Endpoint hoặc dependency có xử lý request đúng giao thức không? |
| Delivery failure rate | Các operation gửi thông báo có đạt điều kiện giao đã định nghĩa không? |
| Verification rejection rate | Các lần nộp bằng chứng bị bác bỏ bao nhiêu? |
| Attempt failure rate | Các lượt khôi phục có kết quả cuối ra sao? |
| Journey non-completion | Hành trình người dùng chưa hoàn tất trong thời hạn nào? |

Ví dụ một người nhập sai mã ba lần rồi thành công tạo ba verifier rejection, nhưng một attempt thành công. Một email bị provider từ chối rồi gửi lại thành công có thể tạo một operation thất bại mà không có attempt thất bại.

Provider accepted, provider delivered, người dùng mở thông báo và bằng chứng đã xác minh là các mốc khác nhau. Không thay thế mốc này bằng mốc kia để đẩy funnel lên cao.

Một tỷ lệ chuyển bước nên đếm số attempt duy nhất trong cùng cohort đã tới hai bước liên tiếp, với thời gian quan sát phù hợp. Đếm số event thô có retry sẽ làm funnel sai.

## 13. Diễn giải biến động: bắt đầu từ giả thuyết có thể kiểm tra

### 13.1. Provider gặp sự cố

Dấu hiệu có thể thấy:

- Operation gửi thông báo lỗi tăng.
- Số attempt pending và tuổi pending tăng.
- Challenge resend tăng.
- Sau một khoảng thời gian, expired hoặc failed technical mới tăng.

Attempt failure rate có thể phản ứng chậm hơn sự cố ban đầu. Chỉ chờ tỷ lệ kết thúc vượt ngưỡng sẽ phát hiện muộn. Đọc thêm lỗi dependency và backlog.

Hành động phù hợp là xác định provider, region và loại thông báo bị ảnh hưởng; cân nhắc phương án dự phòng đã được policy cho phép. Không tự chuyển sang một kênh yếu hơn chỉ để giữ chỉ số.

### 13.2. Chống lạm dụng chặn nhiều request

Nếu policy denial tăng nhưng technical error ổn định, nguyên nhân có thể là chiến dịch tấn công. Nó cũng có thể là rule mới gây chặn nhầm.

Cần đối chiếu threat signal, thay đổi policy, mẫu hỗ trợ và dữ liệu điều tra được phép. Không thể suy “tỷ lệ từ chối tăng nghĩa là hệ thống an toàn hơn” chỉ từ metric.

Một denominator tăng do bot cũng có thể làm tỷ lệ lỗi kỹ thuật giảm. Giữ cả volume theo lớp kết quả để không bị tỷ lệ đánh lừa.

### 13.3. Người dùng hợp lệ gặp khó ở bước xác minh

Một thay đổi UX, lỗi bàn phím, bản địa hóa, khả năng tiếp cận hoặc provider đến chậm đều có thể làm số lần không đạt xác minh tăng.

Để đánh giá chặn nhầm, cần bằng chứng độc lập về những trường hợp hợp lệ đã được kiểm tra. Mẫu hỗ trợ chỉ chứa người đã liên hệ nên có thể bị thiên lệch.

Không gán mọi `FAILED_VERIFICATION` cho “lỗi người dùng”. Outcome mô tả kết quả kiểm tra; nguyên nhân cần phân tích thêm.

### 13.4. Failure rate giảm bất thường sau deploy

Đừng mặc định đây là cải thiện. Có thể:

- Event kết thúc không được phát.
- Bộ ánh xạ bỏ qua outcome mới.
- Lỗi được đổi thành pending và chưa hết hạn.
- Quần thể chuyển sang một flow dễ hơn.
- Tính năng đo ở client bị tắt.
- Kiểm soát bảo mật bị bỏ qua.

Đối chiếu volume starts, terminal coverage, pending quá hạn, schema errors và chất lượng bảo mật sau recovery. Một đồ thị đẹp không thay thế kiểm tra các điều kiện thành công.

## 14. Phân khúc và so sánh công bằng

Các chiều phân tích thường hữu ích gồm loại recovery, kênh gửi, nhóm provider, region, phiên bản ứng dụng theo đợt phát hành, nhóm rủi ro ban đầu và loại client ở mức tổng hợp.

Không nhất thiết đưa mọi chiều vào Prometheus. Các phân tích chi tiết hoặc có nhiều tenant nên làm ở kho phân tích có kiểm soát truy cập, giới hạn số nhóm và xử lý các nhóm quá nhỏ theo nhu cầu riêng tư.

### 14.1. Đừng lấy trung bình đơn giản của các tỷ lệ

Giả sử:

| Nhóm | Không thành công | Đã kết thúc | Tỷ lệ |
|---|---:|---:|---:|
| A | 10 | 100 | 10% |
| B | 180 | 900 | 20% |

Tỷ lệ chung đúng là:

~~~text
(10 + 180) / (100 + 900) = 19%
~~~

Trung bình hai tỷ lệ bằng 15% không biểu diễn xác suất thất bại của một attempt trong toàn bộ tập trên.

Trung bình theo tenant có thể là một chỉ số khác nếu tổ chức muốn mỗi tenant có trọng số như nhau. Khi đó phải đặt tên và mục đích khác, không gọi nó là tỷ lệ attempt chung.

### 14.2. Cơ cấu traffic có thể đảo kết luận

Giả sử hai nhóm low risk và high risk có tỷ lệ như sau:

| Giai đoạn | Low risk | High risk | Toàn bộ |
|---|---|---|---|
| Trước | 9/900 = 1% | 20/100 = 20% | 29/1.000 = 2,9% |
| Sau | 0/100 = 0% | 90/900 = 10% | 90/1.000 = 9% |

Cả hai nhóm đều cải thiện nhưng tỷ lệ chung tăng vì traffic chuyển mạnh sang nhóm high risk. Cần xem cơ cấu cohort và tỷ lệ trong nhóm trước khi kết luận deploy làm hệ thống tệ đi.

Nếu dùng tỷ lệ chuẩn hóa theo trọng số cố định, công bố trọng số và vẫn giữ tỷ lệ thực tế. Không chọn lại trọng số sau khi đã thấy kết quả.

### 14.3. Số mẫu nhỏ và quan hệ nhân quả

Một thất bại trên hai lượt là 50%, nhưng chưa có độ ổn định giống 500 thất bại trên 1.000 lượt. Luôn hiển thị số đếm và thời gian quan sát; khi cần ước lượng độ bất định, dùng phương pháp thống kê phù hợp với đơn vị và sự phụ thuộc của dữ liệu.

Nhiều attempt của cùng người dùng hoặc cùng chiến dịch bot không nhất thiết là những quan sát độc lập. Không áp một cách máy móc khoảng tin cậy nhị thức rồi coi nó là bằng chứng chắc chắn.

So sánh trước/sau deploy còn chịu ảnh hưởng provider, lịch sử cohort, traffic mix và policy. Một tương quan thời gian giúp đặt giả thuyết, chưa tự chứng minh nguyên nhân.

## 15. Đặt mục tiêu và cảnh báo theo mục đích

Không có một ngưỡng failure rate chuẩn cho mọi hệ thống recovery. Luồng password reset tự động và quy trình mất toàn bộ authenticator có thể khác đáng kể về rủi ro, thời gian và mức xác minh.

Nên tách ít nhất ba hướng sử dụng:

1. **Độ tin cậy kỹ thuật:** commit, dependency, queue và thực thi điều kiện bảo mật có hoạt động theo thiết kế không?
2. **Khả năng hoàn tất:** các cohort người dùng có đạt mục tiêu recovery trong thời hạn không?
3. **Hiệu quả bảo mật:** hệ thống có chặn lạm dụng, hạn chế chặn nhầm và giảm việc trao quyền sai không?

Một attempt bị từ chối đúng policy có thể không đạt mục tiêu trải nghiệm nhưng vẫn là kết quả xử lý đúng của một operation bảo mật. Không ép cùng một tỷ lệ vừa đại diện reliability vừa đại diện khả năng khôi phục của chủ tài khoản.

### 15.1. Cảnh báo cần đủ volume và chất lượng dữ liệu

Một rule minh họa có thể yêu cầu tỷ lệ lỗi kỹ thuật tăng trong nhiều cửa sổ và có đủ số lượt. Ngưỡng, thời gian giữ và số mẫu phải dựa trên baseline, mức tác động và traffic thực tế.

Ngoài cảnh báo tỷ lệ, cần cảnh báo:

- Số lỗi tuyệt đối tăng đáng kể.
- Pending quá deadline hoặc tuổi pending tăng.
- Coverage và độ mới dữ liệu giảm.
- Một flow quan trọng không còn ghi nhận starts/terminal events.
- Schema mới không được phân loại.
- Có dấu hiệu khôi phục thành công sai người.

Không được tắt cảnh báo mất telemetry chỉ vì chưa đủ mẫu số để tính tỷ lệ nghiệp vụ.

### 15.2. Error budget chỉ có ý nghĩa khi cùng định nghĩa

Nếu SLO dùng một quần thể operation kỹ thuật đã định nghĩa, với mục tiêu good ratio là `G`, thì:

~~~text
Allowed bad ratio = 1 - G
Burn rate = observed bad ratio / (1 - G)
~~~

Ví dụ giả định `G = 99,5%` và bad ratio hiện tại bằng 1% thì burn rate là 2. Đây chỉ là minh họa công thức; không phải khuyến nghị đặt SLO recovery ở 99,5%.

Không đưa toàn bộ policy denial vào error budget lỗi kỹ thuật nếu hợp đồng SLI xác định chúng là kết quả xử lý hợp lệ. Cũng không được loại lỗi ảnh hưởng người dùng ra sau khi sự cố xảy ra để bảo vệ budget.

Một cửa sổ burn rate ngắn cần được đọc cùng cửa sổ dài và volume. Nó không trực tiếp bằng số giờ còn lại trước khi hết budget nếu tốc độ traffic và cơ cấu lỗi thay đổi.

## 16. Bảo vệ dữ liệu và giữ được khả năng giải thích

Metric recovery có thể trở thành một kênh rò rỉ về sự tồn tại của tài khoản, trạng thái MFA hoặc cơ chế khôi phục của từng người.

Thực hiện các nguyên tắc thiết kế sau:

- Bảo vệ endpoint metrics, dashboard và kho sự kiện bằng quyền truy cập phù hợp.
- Tách dữ liệu tổng hợp cho vận hành với dữ liệu điều tra có thể liên kết tới tài khoản.
- Chỉ giữ các trường cần cho mục tiêu đo và đối soát.
- Không công khai tỷ lệ hoặc count theo một tài khoản do người gọi tùy ý chỉ định.
- Với phân tích nhóm nhỏ, cân nhắc giới hạn truy vấn và cách trình bày tránh suy ngược cá nhân.
- Quy định thời gian lưu, người sở hữu dữ liệu và lịch sử thay đổi định nghĩa metric.

Đừng thêm account ID vào metric label để tiện debug rồi cho rằng một dashboard nội bộ luôn an toàn. Metric thường được sao chép, lưu lâu và được nhiều hệ thống truy cập.

Mặt khác, chỉ xóa mọi định danh ngay từ đầu cũng có thể làm mất khả năng dedup và đối soát. Có thể giữ reference ổn định trong lớp dữ liệu hạn chế, rồi xuất rollup tổng hợp không chứa các định danh ấy.

Các identifier ngẫu nhiên hoặc giả danh hóa vẫn cần kiểm soát liên kết. Chúng không tự biến toàn bộ dữ liệu thành vô danh.

## 17. Các tình huống minh họa để hiểu đúng phép đo

### Tình huống A: một request có ba lần retry

Ba lần retry HTTP được server ánh xạ về cùng attempt nhờ idempotency. Lượt kết thúc thành công.

Kết quả: một attempt thành công; số request có thể lớn hơn một. Không tăng attempt denominator cho từng retry.

### Tình huống B: gửi lại OTP làm mã cũ vô hiệu

Người dùng nhập mã cũ và bị bác bỏ, sau đó nhập mã mới đúng hạn rồi hoàn tất.

Kết quả: một lần verifier reject và một attempt thành công. Việc mã cũ không dùng được là hành vi đúng nếu policy đã thiết kế như vậy.

### Tình huống C: credential đã commit nhưng bước bảo mật bắt buộc chưa đạt

Nếu điều kiện đóng attempt yêu cầu cơ chế session protection đã có hiệu lực, việc chỉ cập nhật credential chưa đủ để phát event success.

Kết quả: attempt chưa được tính thành công cho tới khi đạt điều kiện hoặc kết thúc theo nhánh thất bại đã định nghĩa. Cần theo dõi trạng thái dở dang và xử lý an toàn.

### Tình huống D: hai callback giống nhau

Provider gửi lại cùng callback. Consumer nhận hai lần nhưng chỉ một transition hợp lệ được commit.

Kết quả: một outcome chuẩn. Có thể tăng counter duplicate callback riêng để biết tình trạng delivery.

### Tình huống E: hoàn tất ngoài deadline đo

Attempt đạt điều kiện thành công ở phút 45, trong khi mục tiêu hoàn tất là 30 phút.

Kết quả: successful eventual outcome, nhưng không thành công đúng hạn. Hai báo cáo không mâu thuẫn vì đo hai câu hỏi khác nhau.

### Tình huống F: không có event kết thúc

Kho dữ liệu biết attempt đã bắt đầu nhưng không có dữ liệu tin cậy để xác định kết quả.

Kết quả: unknown hoặc pending tùy trạng thái nguồn đã biết, kèm đối soát. Không tự tạo một thất bại kỹ thuật.

### Tình huống G: bị policy chặn đúng nhưng người dùng cần trợ giúp

Attempt bị từ chối vì thiếu bằng chứng cần thiết. Người dùng sau đó dùng phương án hỗ trợ hợp lệ trong một attempt khác.

Kết quả: attempt đầu không thành công, attempt sau có kết quả riêng. Journey có thể thành công nếu đáp ứng định nghĩa liên kết và hoàn tất. Không sửa attempt đầu thành success để làm đẹp số.

### Tình huống H: recovery thành công rồi phát hiện chiếm đoạt tài khoản

Workflow ban đầu đạt mọi bước mà hệ thống kiểm tra, nhưng điều tra sau đó xác nhận người thực hiện là kẻ tấn công.

Kết quả: giữ được lịch sử workflow và bổ sung kết luận bảo mật theo phiên bản. Theo dõi confirmed unauthorized recovery với cửa sổ phát hiện và cohort riêng. Không suy mọi success trong dashboard là “khôi phục an toàn cho đúng chủ tài khoản”.

## 18. Những điều cần nhớ khi áp dụng

Một bản ghi định nghĩa metric dùng được có thể trình bày gọn như sau:

~~~text
Metric: Recovery terminal non-success rate
Definition: recovery-attempt-outcome-v1
Unit: one server-managed recovery attempt
Population: declared flow and cohort; explicit exclusions
Numerator: known terminal non-success outcomes
Denominator: known terminal outcomes
Time basis: attempt start cohort at a named snapshot
Companion measures: resolution coverage, pending, unknown, counts
Deadline measure: reported separately
Security context: breakdown by policy outcome and assurance requirements
Source: committed state transitions with reconciled projection
~~~

Trước khi diễn giải một biến động, hãy trả lời được: đang đếm request hay attempt, những lượt nào vào mẫu số, có bao nhiêu pending/unknown, các cohort đã đủ thời gian quan sát chưa, và định nghĩa outcome có thay đổi không.

Một failure rate hữu ích dẫn tới hành động cụ thể: sửa dependency, giảm chậm trễ, cải thiện bước xác minh, điều chỉnh rule gây chặn nhầm hoặc khắc phục khoảng trống dữ liệu. Mọi cải thiện vẫn phải giữ các yêu cầu về token dùng một lần, xác minh danh tính, chống lạm dụng và kiểm soát session của luồng recovery.


