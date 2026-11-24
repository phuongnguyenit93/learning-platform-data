# False positive — Dương tính giả trong xác thực dựa trên rủi ro

**False positive (FP, dương tính giả)** xảy ra khi hệ thống xác thực dựa trên rủi ro đánh dấu một hoạt động hợp lệ của người dùng thật là đáng ngờ. Ví dụ, một học viên đăng nhập từ điện thoại mới khi đang đi du lịch, nhưng hệ thống coi vị trí hoặc thiết bị khác thường là dấu hiệu chiếm tài khoản và chặn đăng nhập. Người dùng hợp lệ có thể bị yêu cầu MFA lặp lại, bị khóa tạm thời, bị từ chối giao dịch hoặc phải liên hệ bộ phận hỗ trợ.

Trong **risk-based authentication (RBA)**, hệ thống đánh giá tín hiệu của một lần đăng nhập hoặc hành động để chọn mức kiểm soát phù hợp. Mục tiêu là phát hiện hành vi tấn công mà vẫn giữ trải nghiệm cho người dùng hợp lệ. False positive là một loại sai số quan trọng vì nó làm giảm khả năng truy cập, tạo chi phí hỗ trợ, gây mất niềm tin và có thể khiến người dùng tìm cách né kiểm soát bảo mật.

Không phải mọi challenge bổ sung đều là false positive. Nếu policy chủ động yêu cầu step-up cho một hành động nhạy cảm dù người dùng hợp lệ, đó có thể là quyết định kiểm soát đúng. Cần phân biệt **dự đoán rủi ro sai** với **policy cố ý yêu cầu bảo đảm cao hơn**. Việc phân loại đúng giúp đội ngũ cải thiện mô hình, ngưỡng và quy trình mà không vô tình làm yếu bảo mật.

Bài học thuộc module SECURITY_AUTHENTICATION_FUNDAMENTALS, nơi người học tìm hiểu credential, MFA, passkey, token, session, ranh giới tin cậy và phòng chống lạm dụng đăng nhập. Trọng tâm là hiểu sai số dương tính giả, đo lường tác động, điều chỉnh ngưỡng và thiết kế phản ứng theo mức rủi ro có thể giải thích, kiểm tra và khiếu nại.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Định nghĩa false positive trong RBA và phân biệt với false negative, true positive và true negative.
2. Phân biệt dự đoán sai với step-up có chủ đích theo policy.
3. Đọc confusion matrix và tính false positive rate, precision, recall và các chỉ số liên quan.
4. Giải thích ảnh hưởng của base rate khi tỷ lệ tấn công thực tế thấp.
5. Phân tích nguồn FP từ thiết bị mới, vị trí, mạng, hành vi, dữ liệu thiếu và thay đổi hệ thống.
6. Chọn ngưỡng và hành động phù hợp cho từng loại tài nguyên, thay vì áp một ngưỡng toàn cục.
7. Dùng challenge, step-up, rate limit, hold hoặc review để giảm tác động của dự đoán chưa chắc chắn.
8. Thiết kế quy trình thu thập feedback, khiếu nại, gán nhãn và hiệu chỉnh mô hình.
9. Theo dõi FP theo nhóm người dùng, thiết bị, khu vực, thời gian và loại hành động để phát hiện sai lệch.
10. Viết bộ kiểm thử chứng minh việc giảm FP không làm tăng false negative vượt mức rủi ro chấp nhận.

## 2. False positive trong risk-based authentication là gì?

Một hệ thống RBA thu thập tín hiệu như thiết bị, địa chỉ IP, vị trí gần đúng, lịch sử đăng nhập, tốc độ request, dấu hiệu bot, trạng thái phiên và mức nhạy cảm của hành động. Từ các tín hiệu này, hệ thống ước lượng rủi ro hoặc chọn một policy response.

Ví dụ:
- Người dùng thường đăng nhập từ laptop ở nhà, hôm nay dùng điện thoại mới.
- Người dùng hợp lệ đang dùng VPN của công ty khiến IP xuất hiện ở một quốc gia khác.
- Browser được cập nhật làm thay đổi fingerprint.
- Người dùng đi công tác nên thời gian và vùng địa lý khác lịch sử.
- Mạng di động thay đổi IP liên tục.
- Hệ thống phát hiện nhiều lần đăng nhập thất bại do người dùng quên mật khẩu, rồi đánh dấu cả lần đăng nhập đúng là đáng ngờ.

Nếu hoạt động thực tế hợp lệ nhưng hệ thống dự đoán là tấn công, đó là false positive theo nhãn và định nghĩa đã chọn. Hậu quả có thể là:
- Từ chối đăng nhập hoặc hành động hợp lệ.
- Buộc người dùng thực hiện MFA/step-up không cần thiết.
- Khóa tạm thời tài khoản hoặc thiết bị.
- Tạo nhiều ticket hỗ trợ và tăng thời gian xử lý.
- Làm giảm tỷ lệ hoàn tất giao dịch hoặc onboarding.
- Khiến người dùng quen bấm chấp thuận các challenge, tạo điều kiện cho MFA fatigue.
- Gây bất lợi không đồng đều cho người dùng ở khu vực, thiết bị hoặc điều kiện mạng nhất định.

### 2.1. Phân biệt bốn kết quả

Giả sử hệ thống dự đoán một request có rủi ro cao hoặc cần chặn. Kết quả được so với nhãn thực tế đã được xác minh:

| Dự đoán của hệ thống | Thực tế là tấn công | Thực tế hợp lệ |
| --- | --- | --- |
| **Risk cao / chặn** | True positive (TP): phát hiện đúng | False positive (FP): báo động nhầm |
| **Risk thấp / cho qua** | False negative (FN): bỏ sót tấn công | True negative (TN): nhận diện đúng hoạt động hợp lệ |

Nhãn “thực tế” phải được xác định từ bằng chứng đủ tin cậy, ví dụ kết quả điều tra, xác nhận của người dùng qua kênh độc lập, chargeback đã xác minh hoặc dấu hiệu compromise được xác nhận. Không gán mọi request bị chặn là tấn công thật; làm vậy sẽ khiến dữ liệu huấn luyện củng cố chính những FP đang tồn tại.

### 2.2. FP không đồng nghĩa với mọi lần step-up

Một lần đăng nhập hợp lệ có thể cần step-up vì:
- Người dùng đang truy cập dữ liệu nhạy cảm.
- Chính sách yêu cầu xác thực mới hơn.
- Phiên có assurance thấp hơn mức yêu cầu.
- Hành động cần xác nhận transaction cụ thể.
- Quy định bắt buộc xác minh bổ sung.

Nếu hệ thống biết rõ hành động cần assurance cao và yêu cầu passkey/MFA theo policy, đó là step-up đúng, không nhất thiết là FP. FP xảy ra khi hệ thống hoặc policy đánh giá nhầm một hoạt động là bất thường/không đáng tin dựa trên tín hiệu và nhãn thực tế đã xác định.

## 3. Confusion matrix và các chỉ số cần hiểu

Confusion matrix giúp nhìn rõ hệ thống đã phân loại bao nhiêu trường hợp đúng và sai.

~~~text
                         Thực tế
                    Attack       Legitimate
Dự đoán risk cao      TP             FP
Dự đoán risk thấp     FN             TN
~~~

Các chỉ số phổ biến:

\[
\text{FPR} = \frac{FP}{FP + TN}
\]

FPR (false positive rate) là tỷ lệ hoạt động hợp lệ bị phân loại nhầm thành risk cao trong toàn bộ hoạt động hợp lệ.

\[
\text{Precision} = \frac{TP}{TP + FP}
\]

Precision cho biết trong số các trường hợp hệ thống đánh dấu risk cao, bao nhiêu trường hợp thực sự là tấn công.

\[
\text{Recall / TPR} = \frac{TP}{TP + FN}
\]

Recall (true positive rate) cho biết hệ thống phát hiện được bao nhiêu trong tổng số tấn công thực tế.

\[
\text{FNR} = \frac{FN}{FN + TP} = 1 - \text{Recall}
\]

FNR là tỷ lệ tấn công bị bỏ sót.

Không có một chỉ số đơn lẻ đủ để đánh giá RBA. FPR thấp có thể đi kèm recall thấp; recall cao có thể tạo rất nhiều FP. Precision còn phụ thuộc mạnh vào tỷ lệ tấn công thực tế (base rate). Cần theo dõi thêm tỷ lệ challenge, tỷ lệ người dùng bỏ cuộc, thời gian hỗ trợ, số lần step-up trên mỗi người dùng và thiệt hại từ FN.

### 3.1. Ví dụ về base rate

Giả sử có 100.000 lần đăng nhập:
- 1.000 lần là tấn công thực tế (1%).
- Hệ thống phát hiện đúng 90% tấn công: TP = 900, FN = 100.
- Trong 99.000 lần hợp lệ, hệ thống báo nhầm 2%: FP = 1.980, TN = 97.020.

Khi đó:

\[
\text{Precision} = \frac{900}{900 + 1980} = 31.25\%
\]

Dù FPR chỉ 2% và recall là 90%, chỉ khoảng 31,25% các trường hợp bị đánh dấu risk cao là tấn công thực sự. Phần còn lại là người dùng hợp lệ. Điều này có thể tạo ra lượng challenge/review rất lớn.

| Kết quả | Số lần đăng nhập |
| --- | ---: |
| True positive (TP) | 900 |
| False positive (FP) | 1.980 |
| False negative (FN) | 100 |
| True negative (TN) | 97.020 |

Điểm quan trọng: khi sự kiện tấn công hiếm, ngay cả FPR tương đối thấp vẫn có thể tạo ra nhiều báo động nhầm. Đội ngũ phải đánh giá số lượng FP tuyệt đối và tác động vận hành, không chỉ nhìn phần trăm.

## 4. Nguồn gây false positive

FP có thể đến từ mô hình, dữ liệu, policy hoặc tích hợp. Trước khi thay ngưỡng, cần tìm nguyên nhân.

| Nguồn tín hiệu | Vì sao có thể tạo FP | Ví dụ |
| --- | --- | --- |
| **Thiết bị mới** | Người dùng đổi điện thoại, cài lại browser hoặc xóa cookie | Người dùng hợp lệ bị xem như thiết bị lạ. |
| **IP và mạng** | VPN, NAT, proxy doanh nghiệp, mạng di động hoặc IP tái cấp | Nhiều người có cùng IP hoặc IP thay đổi vị trí địa lý. |
| **Geo-velocity** | Vị trí suy ra từ IP không chính xác hoặc request qua proxy | Người dùng bị cho là di chuyển quá nhanh giữa hai quốc gia. |
| **Browser fingerprint** | Browser update, privacy setting, extension hoặc anti-tracking thay đổi dấu hiệu | Thiết bị quen thuộc bị nhận diện thành thiết bị mới. |
| **Hành vi** | Người dùng thay đổi lịch làm việc, thao tác hoặc accessibility tool | Mô hình coi hoạt động hợp lệ là bất thường. |
| **Tốc độ request** | Đồng bộ, preload hoặc ứng dụng retry | Một batch hợp lệ trông giống automation. |
| **Dữ liệu thiếu/sai** | Telemetry lỗi, clock lệch, IP database cũ hoặc event đến trễ | Điểm rủi ro bị tăng do thiếu thông tin. |
| **Mô hình lỗi thời** | Hành vi người dùng hoặc môi trường thay đổi | Model drift sau khi ra mắt ứng dụng mới. |
| **Policy quá rộng** | Một rule áp dụng cho mọi user/action | Đọc tài liệu cũng bị xử lý như đổi email recovery. |
| **Tích hợp lỗi** | Risk engine nhận sai user/device/session hoặc dùng dữ liệu cũ | Người dùng hợp lệ bị đánh giá dựa trên phiên khác. |

### 4.1. Tín hiệu không ổn định không nên tự quyết định

IP geolocation, device fingerprint và vị trí gần đúng có thể hữu ích như tín hiệu phụ, nhưng không nên được xem là bằng chứng chắc chắn về danh tính hoặc gian lận. Một IP “mới” không chứng minh attacker; một thiết bị “quen” cũng không chứng minh người dùng hiện tại là chủ tài khoản.

Nên kết hợp nhiều tín hiệu độc lập, đánh giá độ tin cậy của từng nguồn và cho phép trạng thái “unknown”. Không biến thiếu telemetry thành risk cao mặc định nếu điều đó gây chặn người dùng hợp lệ; cũng không biến thiếu dữ liệu thành risk thấp mặc định cho hành động nhạy cảm.

## 5. Ngưỡng rủi ro và trade-off giữa FP với FN

Risk engine có thể trả về score hoặc risk band. Policy ánh xạ kết quả sang hành động như allow, monitor, step-up, hold, manual review hoặc deny.

~~~mermaid
flowchart TD
    A["Request đăng nhập / hành động"] --> B["Thu thập tín hiệu có nguồn"]
    B --> C["Đánh giá risk + assurance + action"]
    C --> D{"Risk band"}
    D -->|Thấp| E["Cho phép theo session policy"]
    D -->|Trung bình| F["Step-up phù hợp"]
    D -->|Cao| G["Hold / review / deny theo mức tác động"]
    E --> H["Audit và theo dõi"]
    F --> H
    G --> H
    H --> I["Feedback và hiệu chỉnh policy"]
~~~

Khi hạ ngưỡng risk cao:
- Nhiều tấn công có thể bị phát hiện hơn (recall tăng).
- Nhiều hoạt động hợp lệ cũng bị đánh dấu (FP tăng).
- Số lần challenge, support ticket và bỏ cuộc có thể tăng.

Khi nâng ngưỡng:
- FP có thể giảm.
- Một số tấn công có thể lọt qua (FN tăng).
- Chi phí gian lận hoặc chiếm tài khoản có thể tăng.

Không chọn ngưỡng chỉ dựa trên việc “giảm số ticket”. Cần cân bằng tổn thất kỳ vọng:

\[
\text{Expected loss} =
C_{FP}\times FP + C_{FN}\times FN + C_{friction}\times \text{friction}
\]

Trong đó chi phí FP có thể gồm mất giao dịch hợp lệ, hỗ trợ, rời bỏ và ảnh hưởng công bằng; chi phí FN có thể gồm account takeover, dữ liệu bị lộ và thiệt hại tài chính. Chi phí ma sát cần đo riêng vì một challenge có thể hợp lệ theo policy nhưng vẫn làm giảm trải nghiệm.

### 5.1. Ngưỡng nên phụ thuộc hành động

Một ngưỡng phù hợp cho xem nội dung không nhất thiết phù hợp cho đổi email recovery hoặc cấp quyền admin. Thiết kế policy theo action/resource:

- **Rủi ro thấp:** cho phép với giám sát khi session và authorization hợp lệ.
- **Rủi ro vừa:** yêu cầu step-up bằng phương thức đã đăng ký.
- **Rủi ro cao:** tạm giữ giao dịch, xác minh bổ sung hoặc review.
- **Rủi ro rất cao/có bằng chứng compromise:** từ chối, revoke session/credential theo incident policy và chuyển xử lý sự cố.

Hành động phải tương xứng. Chỉ vì một IP lạ không nên tự động khóa toàn bộ tài khoản; có thể yêu cầu passkey hoặc kiểm tra bổ sung. Nhưng với bằng chứng credential bị đánh cắp, không nên chỉ yêu cầu một challenge yếu rồi cho qua.

## 6. Thiết kế phản ứng nhiều mức để giảm tác động FP

Một hệ thống chỉ có hai lựa chọn “allow” hoặc “block” dễ tạo ra tác động lớn khi dự đoán chưa chắc chắn. Có thể dùng phản ứng nhiều mức:

| Phản ứng | Khi phù hợp | Điều cần bảo đảm |
| --- | --- | --- |
| **Allow + monitor** | Risk thấp và session/authorization hợp lệ | Audit và phát hiện bất thường tiếp theo. |
| **Step-up** | Có nghi vấn vừa phải hoặc policy yêu cầu freshness/assurance | Dùng authenticator đã đăng ký, không tự downgrade. |
| **Rate limit** | Tốc độ bất thường nhưng chưa đủ bằng chứng takeover | Giới hạn theo account/device/network, tránh khóa hàng loạt người dùng chung NAT. |
| **Hold / delay** | Hành động có thể trì hoãn để xác minh | Hiển thị trạng thái rõ và có thời hạn xử lý. |
| **Manual review** | Tín hiệu mâu thuẫn hoặc tác động lớn | Reviewer có hướng dẫn, audit và quy trình khiếu nại. |
| **Deny / revoke** | Có bằng chứng mạnh hoặc policy bắt buộc | Thông báo an toàn, recovery và incident response. |

Step-up cũng có chi phí và có thể trở thành FP nếu bị áp dụng quá thường xuyên. Cần đo tỷ lệ challenge theo nhóm, số lần người dùng phải xác thực lại và tỷ lệ challenge thất bại do vấn đề usability thay vì gian lận.

### 6.1. Không tạo MFA fatigue

Nếu mỗi tín hiệu nhỏ đều tạo push approval, người dùng có thể quen bấm “Approve” để tiếp tục. Điều này làm giảm hiệu quả bảo vệ và có thể bị attacker khai thác.

- Giới hạn số challenge trong khoảng thời gian.
- Hiển thị rõ hành động, thiết bị và ngữ cảnh.
- Dùng number matching hoặc transaction binding nếu phù hợp.
- Không gửi prompt lặp vô hạn.
- Cho phép từ chối và báo cáo request lạ.
- Không xem việc người dùng bấm approve một prompt mơ hồ là bằng chứng đủ cho giao dịch nhạy cảm.

## 7. Phân tích FP theo nhóm và công bằng

Một FPR trung bình thấp có thể che giấu nhóm người dùng bị ảnh hưởng nặng. Ví dụ, người dùng sử dụng mạng di động, VPN, thiết bị giá rẻ, công cụ hỗ trợ tiếp cận hoặc browser có chế độ privacy cao có thể bị đánh dấu nhiều hơn.

Cần theo dõi, trong phạm vi pháp luật và quyền riêng tư cho phép:
- Loại thiết bị và phiên bản OS/browser.
- Loại mạng (mobile, corporate VPN, residential) ở mức tổng hợp phù hợp.
- Khu vực hoặc quốc gia nếu thực sự cần và có căn cứ.
- Nhóm hành động và mức nhạy cảm.
- Tỷ lệ challenge, block, appeal và overturn.
- Tỷ lệ hoàn tất xác thực thay thế.
- Chênh lệch false positive rate giữa các nhóm được phép đánh giá.

Không suy ra thuộc tính nhạy cảm của người dùng để phân nhóm nếu không có căn cứ hợp pháp và mục đích rõ. Không dùng vị trí, ngôn ngữ hoặc loại thiết bị như proxy cho thuộc tính nhạy cảm mà không đánh giá tác động. Phân tích công bằng cần bảo vệ dữ liệu, giảm định danh và kiểm soát quyền truy cập.

### 7.1. Kiểm tra sai lệch trong ngưỡng

Nếu một nhóm có FPR cao hơn đáng kể:
1. Kiểm tra chất lượng và mức bao phủ dữ liệu.
2. Xác định tín hiệu nào đóng góp nhiều vào quyết định.
3. Kiểm tra proxy hoặc rule không phù hợp.
4. So sánh hiệu quả theo action và mức tổn thất.
5. Kiểm tra khả năng dùng authenticator/fallback của nhóm đó.
6. Thử điều chỉnh policy trong môi trường đánh giá có kiểm soát.
7. Đo lại cả FP và FN trước khi triển khai.

Không giải quyết chênh lệch bằng cách đơn giản tắt mọi kiểm soát cho nhóm bị ảnh hưởng. Cần tìm nguyên nhân và chọn biện pháp có cùng mức bảo vệ nhưng ít tạo ma sát hơn.

## 8. Gán nhãn đúng: làm sao biết đó là false positive?

Đánh giá FP phụ thuộc vào ground truth. Một request bị challenge rồi thành công không tự động là FP: người dùng hợp lệ có thể đã vượt challenge, nhưng cũng có thể là attacker đã chiếm cả yếu tố thứ hai. Một request bị chặn và không có khiếu nại cũng không tự động là tấn công.

Nguồn gán nhãn có thể gồm:
- Người dùng xác nhận hoạt động qua kênh độc lập đã xác minh.
- Kết quả điều tra account takeover.
- Báo cáo gian lận đã được xác minh.
- Bằng chứng credential/thiết bị bị chiếm hoặc bị thu hồi.
- Kết quả hỗ trợ và khiếu nại đã được review.
- Dữ liệu chargeback hoặc tổn thất đã xác nhận, nếu phù hợp.

Nên dùng nhãn nhiều trạng thái thay vì ép nhị phân:
- Confirmed attack.
- Confirmed legitimate.
- Inconclusive/unknown.
- Policy-required challenge.
- User abandoned/no evidence.

Không dùng “không thấy gian lận” làm nhãn legitimate nếu chưa có bằng chứng đủ. Tránh dùng kết quả của chính risk engine làm ground truth cho model mới vì sẽ tạo feedback loop.

### 8.1. Khiếu nại và overturn

Khi người dùng bị chặn nhầm:
- Cung cấp kênh hỗ trợ an toàn và dễ tìm.
- Xác minh người yêu cầu bằng phương thức phù hợp, không hỏi họ gửi mật khẩu/OTP.
- Ghi lại decision ID, policy/model version, thời điểm và lý do tổng quát.
- Cho reviewer xem tín hiệu cần thiết với quyền tối thiểu.
- Ghi kết quả overturn và lý do.
- Cập nhật nhãn sau khi có bằng chứng, không tự động thay đổi model ngay từ một khiếu nại đơn lẻ.
- Phản hồi cho người dùng về cách khôi phục quyền truy cập mà không tiết lộ chi tiết giúp attacker né detection.

Không nên công khai toàn bộ risk score hoặc rule nội bộ trong thông báo từ chối. Cần giải thích đủ để người dùng xử lý, đồng thời bảo vệ tín hiệu chống gian lận.

## 9. Hiệu chỉnh và kiểm định mô hình

Một risk score chỉ hữu ích nếu được kiểm định trên dữ liệu đại diện và theo đúng mục tiêu sử dụng. Trước khi thay đổi threshold:
- Tách dữ liệu train, validation và test theo thời gian hoặc account/session để tránh leakage.
- Đánh giá trên traffic gần đây và các tình huống hiếm.
- Kiểm tra calibration: score có tương ứng với tần suất rủi ro quan sát được không.
- Đo precision/recall/FPR theo threshold và action.
- Đánh giá theo nhóm và loại thiết bị.
- Kiểm tra drift sau khi thay đổi app, browser, nhà cung cấp hoặc threat landscape.
- Thực hiện shadow evaluation hoặc canary trước khi áp dụng rộng.
- Có rollback và người phê duyệt threshold/policy.

### 9.1. ROC và Precision-Recall

ROC curve biểu diễn TPR so với FPR ở nhiều threshold. Precision-Recall curve biểu diễn precision so với recall. Khi base rate thấp, PR curve thường giúp nhìn rõ hơn tác động của báo động giả tới các cảnh báo được tạo ra. Không chỉ dựa vào AUC; hãy chọn điểm vận hành phù hợp với chi phí FP/FN của từng action.

~~~text
for threshold in candidate_thresholds:
    predictions = score >= threshold
    calculate TP, FP, TN, FN
    calculate FPR, precision, recall
    calculate challenge_rate and user_friction
    calculate expected_security_loss
    compare results by action and cohort
select threshold under approved risk constraints
validate on holdout and recent traffic
~~~

Không tối ưu threshold trên cùng tập dữ liệu dùng để báo cáo kết quả cuối cùng. Ghi rõ thời gian dữ liệu, định nghĩa attack/legitimate, cách xử lý unknown và phiên bản model.

### 9.2. Rule-based và model-based RBA

FP có thể đến từ rule cứng hoặc mô hình học máy:
- Rule kiểu “IP quốc gia mới = block” thường dễ hiểu nhưng có thể gây FP lớn.
- Model kết hợp nhiều tín hiệu có thể linh hoạt hơn, nhưng khó giải thích và có thể học proxy không mong muốn.
- Hybrid policy có thể dùng model để xếp hạng rủi ro, sau đó áp rule bắt buộc và action theo tài nguyên.

Không giả định model phức tạp luôn tốt hơn. Một rule đơn giản, minh bạch và có fallback tốt có thể phù hợp hơn cho hành động nhạy cảm. Dù dùng phương pháp nào, cần version hóa, audit, kiểm định và giám sát.

## 10. Pseudocode cho quyết định risk-based

Ví dụ minh họa cách tách risk score khỏi action policy:

~~~text
evaluateRequest(request, session, account):
    context = collectTrustedSignals(request, session, account)
    risk = riskEngine.score(context)
    actionPolicy = policyFor(request.action, request.resource)

    if account.isDisabled or session.isRevoked:
        return DENY

    if actionPolicy.requiresFreshAuthentication:
        if not authenticationIsFresh(session, actionPolicy):
            return STEP_UP

    if context.hasConfirmedCompromise:
        recordSecurityEvent(context, risk)
        return DENY_AND_START_INCIDENT

    if risk >= actionPolicy.highRiskThreshold:
        if actionPolicy.supportsReview:
            return HOLD_FOR_REVIEW
        return STEP_UP_OR_DENY(actionPolicy)

    if risk >= actionPolicy.mediumRiskThreshold:
        return STEP_UP_WITH_ALLOWED_AUTHENTICATOR

    return ALLOW_AND_MONITOR
~~~

Trong triển khai thật, không để risk score thay thế authorization. Sau khi request vượt qua RBA, API vẫn phải kiểm tra quyền, tenant, scope, trạng thái tài khoản và điều kiện nghiệp vụ. Nếu tín hiệu thiếu hoặc lỗi, áp dụng policy riêng cho “unknown”; không mặc định tất cả lỗi telemetry là risk thấp hoặc risk cao.

### 10.1. Ghi decision để điều tra

Một decision record có thể gồm:
- Decision ID và correlation ID.
- Account/session reference đã được bảo vệ.
- Action/resource và thời điểm.
- Risk score/band cùng model version.
- Policy version, threshold và action đã chọn.
- Tín hiệu/rule reason code ở mức cần thiết.
- Kết quả step-up, review, appeal hoặc incident sau đó.

Không lưu dữ liệu nhạy cảm thô hoặc fingerprint đầy đủ nếu không cần. Không ghi password, OTP, cookie, access token, refresh token hoặc private key. Giới hạn ai được xem reason code chi tiết vì thông tin đó có thể giúp attacker điều chỉnh hành vi.

## 11. Bài thực hành: giảm false positive cho StudyHub

**Bối cảnh:** StudyHub có học viên và giảng viên đăng nhập từ web/mobile. Risk engine hiện đánh dấu risk cao khi IP thay đổi quốc gia, thiết bị mới hoặc có nhiều request trong thời gian ngắn. Người dùng đi công tác và người dùng mạng di động thường bị challenge; một số tài khoản bị khóa tạm thời dù không có dấu hiệu compromise. Tài khoản giảng viên có quyền sửa điểm và tài khoản quản trị có quyền cấp role.

### 11.1. Phân tích dữ liệu

Hãy thu thập một tập đánh giá đã gán nhãn độc lập:
- Lần đăng nhập được xác nhận hợp lệ.
- Sự cố takeover đã được xác nhận.
- Trường hợp chưa rõ hoặc không đủ bằng chứng.
- Quyết định challenge/block và kết quả sau đó.
- Action, thiết bị, mạng và policy/model version.

Tính confusion matrix, FPR, precision, recall và challenge rate. Phân tích theo action, platform và nhóm thiết bị. Không coi mọi trường hợp người dùng vượt MFA là tấn công hoặc mọi trường hợp không khiếu nại là legitimate.

### 11.2. Thiết kế thay đổi policy

Đề xuất:
1. Không block chỉ dựa trên một tín hiệu IP hoặc geo-velocity không ổn định.
2. Kết hợp thiết bị, session, hành vi và mức nhạy cảm của action.
3. Với risk trung bình, yêu cầu passkey/MFA step-up thay vì khóa ngay.
4. Với đổi email recovery hoặc cấp role, yêu cầu freshness và assurance phù hợp dù risk score thấp.
5. Với bằng chứng compromise mạnh, revoke/deny và kích hoạt incident response.
6. Tạo quy trình review/appeal cho trường hợp tín hiệu mâu thuẫn.
7. Đo FPR, FN, challenge completion, support load và fraud loss trong shadow/canary.
8. Theo dõi tác động theo mạng di động, VPN, browser privacy và thiết bị hỗ trợ tiếp cận.

### 11.3. Bộ ca kiểm thử chấp nhận

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Người dùng hợp lệ đăng nhập từ thiết bị mới | Có thể step-up theo policy; không tự động khóa chỉ vì thiết bị mới. |
| Người dùng hợp lệ dùng VPN doanh nghiệp | IP lạ là tín hiệu phụ; kết hợp thêm bằng chứng trước khi deny. |
| IP geolocation sai hoặc database cũ | Trạng thái tín hiệu được đánh dấu không chắc chắn; không tự coi là bằng chứng compromise. |
| Người dùng mạng di động đổi IP liên tục | Không tạo hàng loạt FP hoặc khóa account chỉ vì IP churn. |
| Browser update làm fingerprint thay đổi | Đánh giá lại theo nhiều tín hiệu; có đường step-up. |
| Request nền hợp lệ tạo burst | Phân biệt pattern của ứng dụng với automation tấn công. |
| Credential bị xác nhận compromise | Từ chối/revoke theo incident policy dù các tín hiệu khác trông quen thuộc. |
| Action đổi email recovery | Áp freshness/assurance policy độc lập với risk score thấp. |
| Risk score sát threshold | Action ổn định theo policy; không dao động bất thường giữa allow/block. |
| Telemetry thiếu hoặc provider outage | Áp trạng thái unknown và fallback đã định nghĩa; không tự động fail open cho action nhạy cảm. |
| Người dùng khiếu nại quyết định block | Có decision ID, quy trình xác minh và audit overturn. |
| Một nhóm có FPR cao bất thường | Cảnh báo, phân tích nguyên nhân và kiểm định trước khi thay threshold. |
| Threshold mới giảm FP | Đánh giá đồng thời FN, fraud loss và friction trên holdout/canary. |
| Attacker cố tình mô phỏng thiết bị quen | Không chỉ dựa fingerprint; vẫn kiểm tra credential, session và hành vi. |
| Một decision bị retry | Idempotency/audit không tạo nhiều lần khóa hoặc challenge ngoài policy. |
| Reviewer thay đổi nhãn | Ghi actor, lý do, bằng chứng và model/policy version. |
| Người dùng không có authenticator chính | Chỉ dùng fallback đã được phê duyệt; không hạ assurance âm thầm. |

### 11.4. Câu hỏi tự đánh giá

1. False positive và false negative khác nhau thế nào?
2. Vì sao một lần step-up không nhất thiết là false positive?
3. FPR và precision đo hai điều khác nhau nào?
4. Vì sao base rate thấp có thể làm precision thấp dù FPR nhỏ?
5. VPN, mạng di động và browser update có thể gây FP ra sao?
6. Vì sao không nên block chỉ dựa trên một tín hiệu IP?
7. Khi nào nên step-up, hold, review hoặc deny?
8. Ground truth cần được gán nhãn thế nào để tránh feedback loop?
9. Vì sao phải đo FP theo nhóm và theo loại hành động?
10. Làm thế nào giảm FP mà không làm FN tăng vượt mức rủi ro chấp nhận?

**Tiêu chí hoàn thành:** Người học có thể đọc confusion matrix, tính và diễn giải FPR/precision/recall, tìm nguyên nhân FP, thiết kế action policy nhiều mức, mô tả quy trình appeal/labeling và chứng minh bằng test rằng thay đổi threshold không làm suy giảm bảo vệ quá giới hạn.

## 12. Vận hành, giám sát và cải tiến liên tục

Các chỉ số nên theo dõi:
- FPR và số FP tuyệt đối theo action, platform, region và thời gian.
- Precision/recall và tỷ lệ incident được xác nhận.
- Challenge rate, challenge success/failure và số challenge trên mỗi người dùng.
- Tỷ lệ deny, hold, manual review và appeal.
- Tỷ lệ appeal được overturn.
- Thời gian xử lý support và chi phí vận hành.
- Tỷ lệ bỏ cuộc hoặc giao dịch hợp lệ bị gián đoạn.
- Tổn thất gian lận liên quan FN.
- Chênh lệch chỉ số giữa nhóm thiết bị/mạng được phép đánh giá.
- Tỷ lệ tín hiệu thiếu, lỗi provider và model drift.

Thiết lập ngưỡng cảnh báo cho FP tăng đột biến, một nhóm bị challenge nhiều hơn bình thường, tỷ lệ appeal overturn tăng hoặc model score thay đổi sau release. Theo dõi cả chỉ số kỹ thuật và kết quả nghiệp vụ; giảm FPR mà làm tổn thất gian lận tăng mạnh không phải cải thiện.

Mọi thay đổi model, threshold, rule hoặc risk provider cần:
1. Có owner và lý do thay đổi.
2. Được đánh giá trên dữ liệu holdout có nhãn đáng tin.
3. Có phân tích FP/FN, tác động nhóm và chi phí friction.
4. Chạy shadow/canary khi phù hợp.
5. Có rollback, audit và versioning.
6. Được review sau triển khai bằng traffic thực tế.

Không dùng dữ liệu sinh ra từ quyết định cũ làm ground truth mà không kiểm tra. Nếu hệ thống cũ đã chặn người dùng hợp lệ, dữ liệu quan sát sẽ thiếu hành vi sau đăng nhập của họ; đây là selection bias cần tính đến khi huấn luyện hoặc đánh giá model mới.

## 13. Tài liệu nên đọc tiếp

- **NIST SP 800-63B — Authentication and Authenticator Management**: quản lý phiên, reauthentication và kiểm soát xác thực theo rủi ro; kiểm tra phiên bản hiện hành.
- **NIST AI Risk Management Framework (AI RMF)**: quản trị rủi ro, đo lường, giám sát và quản lý hệ thống có mô hình.
- **NIST SP 800-30**: đánh giá rủi ro hệ thống thông tin và lựa chọn biện pháp kiểm soát.
- **OWASP Automated Threats to Web Applications**: phân loại và giảm thiểu automation abuse.
- **OWASP Authentication Cheat Sheet**: kiểm soát đăng nhập, lockout, reauthentication và thông báo.
- **OWASP ASVS**: tiêu chí kiểm thử cho authentication, session và access control.
- **Tài liệu đánh giá mô hình thống kê/ML của tổ chức**: calibration, ROC/PR, drift, data quality và fairness theo mục đích được phép.

Khi triển khai thật, hãy xác định rõ định nghĩa attack/legitimate, chi phí FP/FN, base rate, action được bảo vệ và khả năng hỗ trợ người dùng. **Giảm false positive không phải là nới lỏng bảo mật tùy tiện; đó là làm cho tín hiệu, ngưỡng và phản ứng chính xác hơn để người dùng hợp lệ ít bị cản trở trong khi các hành vi tấn công vẫn được phát hiện và xử lý tương xứng.**
