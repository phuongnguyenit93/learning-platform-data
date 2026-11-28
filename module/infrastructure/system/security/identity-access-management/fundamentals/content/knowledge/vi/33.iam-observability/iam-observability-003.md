# MFA challenge rate

## 1. Chỉ số này cho biết điều gì?

**MFA challenge rate** là tỷ lệ các giao dịch xác thực trong một tập quan sát được phát hành yêu cầu xác minh đa yếu tố mới. Trong IAM observability, chỉ số này giúp nhìn thấy mức độ người dùng thực sự gặp một bước MFA, tác động của chính sách truy cập và những thay đổi trong trải nghiệm đăng nhập.

Ví dụ, một ứng dụng có 10.000 giao dịch đăng nhập thuộc diện đánh giá MFA trong một giờ; 5.800 giao dịch nhận challenge mới. Nếu mỗi giao dịch có tối đa một challenge logic trong phạm vi này, tỷ lệ challenge là 58%.

Con số đó chưa trả lời được các câu hỏi sau:

- Bao nhiêu người đã hoàn thành MFA thành công?
- Những giao dịch cần MFA có thực sự nhận challenge đầy đủ không?
- Chính sách có bỏ sót trường hợp đáng lẽ phải yêu cầu MFA không?
- Challenge dùng phương thức xác thực nào và cung cấp mức bảo đảm ra sao?

Vì vậy, MFA challenge rate là chỉ số về hành vi của luồng xác thực. Nó không tự chứng minh hệ thống an toàn hơn hay kém an toàn hơn. Tỷ lệ cao có thể xuất phát từ chính sách chặt hơn, nhưng cũng có thể do mất phiên khiến người dùng bị hỏi lặp lại. Tỷ lệ thấp có thể phản ánh việc tái sử dụng hợp lệ bằng chứng MFA, nhưng cũng có thể do cấu hình sai làm bỏ qua bước xác minh.

## 2. Định nghĩa tập quan sát trước khi tính

Không có mẫu số thích hợp cho mọi hệ thống. Dashboard cần công bố rõ đang đo đăng nhập, step-up khi thực hiện thao tác nhạy cảm hay một loại giao dịch khác.

Trong bài này, ta dùng quy ước cho một **luồng đăng nhập của người dùng**:

> Một giao dịch đủ điều kiện quan sát là giao dịch đã đi tới điểm quyết định chính sách về MFA, có đủ ngữ cảnh để đánh giá và thuộc phạm vi mà tổ chức muốn theo dõi.

Điểm quyết định này không nhất thiết luôn nằm sau một mật khẩu. Luồng liên kết danh tính hoặc đăng nhập không mật khẩu có thể cung cấp ngữ cảnh theo cách khác. Điều cần giữ ổn định là ý nghĩa của sự kiện quyết định, không phải một thứ tự màn hình cố định.

Với quy ước trên:

| Thành phần | Quy ước đo lường |
| --- | --- |
| Đơn vị đếm | Giao dịch xác thực logic, không phải HTTP request |
| Mẫu số | Giao dịch người dùng đã tới điểm đánh giá MFA trong phạm vi đã chọn |
| Tử số | Giao dịch trong tập đó được phát hành challenge MFA mới |
| Khoảng thời gian | Theo cohort giao dịch hoặc cửa sổ vận hành được mô tả rõ |
| Loại trừ | Health check, danh tính workload, refresh token thông thường và giao dịch chưa tới điểm đánh giá |
| Luồng riêng | Step-up cho thao tác nhạy cảm được đo riêng, không cộng tùy tiện vào đăng nhập |

Một request nhập sai mật khẩu trước khi tới điểm đánh giá không thuộc mẫu số này. Nếu đội vận hành còn cần đo tỷ lệ challenge trên **toàn bộ lượt thử đăng nhập**, có thể tạo thêm chỉ số khác với tên và mẫu số riêng. Hai tỷ lệ trả lời hai câu hỏi khác nhau và không nên đặt cạnh nhau như thể cùng định nghĩa.

Danh tính workload thường dùng chứng thư, token hay cơ chế xác thực máy với máy. Đưa lưu lượng đó vào mẫu số MFA của người dùng có thể làm tỷ lệ giảm mạnh dù trải nghiệm MFA của con người không đổi.

## 3. Công thức và các chỉ số đi kèm

Gọi:

- `E`: số giao dịch đủ điều kiện quan sát.
- `R`: số giao dịch có quyết định yêu cầu challenge MFA mới.
- `I`: số giao dịch thực sự được phát hành challenge MFA mới.
- `S`: số giao dịch hoàn thành challenge thành công trong cohort đã xác định.

Khi mỗi giao dịch trong phạm vi chỉ có một challenge logic mới:

```text
MFA challenge rate (%) = I / E × 100

New-MFA requirement rate (%) = R / E × 100

Challenge issuance coverage (%) = I / R × 100

MFA completion rate (%) = S / I × 100
```

Các tỷ lệ không thay thế cho nhau:

| Chỉ số | Câu hỏi được trả lời |
| --- | --- |
| Challenge rate | Bao nhiêu giao dịch đủ điều kiện thực sự nhận challenge mới? |
| Requirement rate | Chính sách yêu cầu challenge mới cho bao nhiêu giao dịch? |
| Issuance coverage | Bao nhiêu giao dịch cần challenge mới đã được phát hành challenge? |
| Completion rate | Bao nhiêu giao dịch đã nhận challenge hoàn thành xác minh? |

Nếu `R` cao nhưng `I` thấp, cần xem đường phát hành challenge: bộ điều phối, nhà cung cấp xác thực, hàng đợi hoặc lỗi trả kết quả. Chỉ theo dõi `I / E` có thể che mất khoảng trống này.

Nếu `I / E` ổn định nhưng `S / I` giảm, vấn đề có thể nằm ở bước hoàn thành: phương thức xác thực gặp lỗi, người dùng không nhận được yêu cầu, nhập sai mã hoặc không tiếp tục thao tác.

Khi mẫu số bằng 0, tỷ lệ không xác định. Dashboard nên hiển thị `N/A` hoặc trạng thái thiếu dữ liệu, thay vì diễn giải thành 0% có ý nghĩa nghiệp vụ.

## 4. Challenge logic khác với số lần thử phương thức

Một challenge logic là một yêu cầu xác minh phục vụ một quyết định truy cập cụ thể. Nó có thể bao gồm nhiều thao tác kỹ thuật:

```text
Một giao dịch đăng nhập
  → yêu cầu MFA logic A
  → gửi thông báo xác thực
  → người dùng yêu cầu gửi lại
  → chuyển sang phương thức dự phòng
  → xác minh thành công
```

Nếu gửi lại thông báo và chuyển phương thức vẫn phục vụ yêu cầu MFA logic A, tử số theo giao dịch chỉ tăng một lần. Số lần gửi thông báo hoặc số lần thử phương thức có thể tăng nhiều lần, nhưng thuộc các metric khác.

Nếu dùng số HTTP request tới nhà cung cấp làm tử số, retry có thể làm challenge rate vượt 100%. Đó không còn là tỷ lệ giao dịch được challenge. Nếu muốn đo tải vận hành, hãy đặt tên rõ như `MFA delivery attempts per transaction` và chấp nhận đây là số lần thử trung bình.

Một giao dịch cũng có thể thực sự cần nhiều challenge độc lập. Khi đó phải chọn một trong hai cách:

1. Giữ đơn vị giao dịch: đếm giao dịch nhận **ít nhất một** challenge mới.
2. Chuyển sang đơn vị quyết định bảo đảm: mỗi điểm quyết định có định danh riêng và tối đa một challenge logic được tính.

Không sử dụng công thức đếm challenge trên giao dịch mà bỏ qua khả năng có nhiều challenge trong cùng giao dịch.

### Chống đếm trùng ở nơi phát sinh sự kiện

Sự kiện `challenge_issued` cần có quy tắc duy nhất và cơ chế chống đếm trùng. Một thiết kế minh họa sử dụng khóa logic:

```text
authentication_transaction_id + assurance_decision_id
```

Trong đó, transaction ID liên kết luồng xác thực, còn decision ID phân biệt các quyết định bảo đảm khác nhau. Retry xử lý cùng một quyết định không được tạo thêm bản ghi được tính vào tử số.

Đặt điểm ghi nhận `issued` tại lúc hệ thống xác nhận challenge logic đã được tạo hoặc được nhà cung cấp chấp nhận theo hợp đồng tích hợp. Gửi một lệnh rồi bị timeout chưa đủ để biết challenge có tồn tại hay không; cần đối soát theo định danh và quy tắc idempotency của tích hợp.

`Issued` cũng không đồng nghĩa người dùng đã nhìn thấy yêu cầu trên thiết bị. Khả năng gửi tới thiết bị và tương tác của người dùng cần được theo dõi riêng nếu hệ thống có dữ liệu đó.

## 5. Phiên, SSO và bằng chứng MFA đã có

Không phải giao dịch không có challenge mới đều là giao dịch chưa được bảo vệ bằng MFA.

Ví dụ, một người dùng đã xác minh MFA ở nhà cung cấp danh tính. Khi truy cập ứng dụng tiếp theo qua SSO, ứng dụng có thể chấp nhận bằng chứng xác thực trước đó nếu nguồn phát hành, mức bảo đảm, độ mới và các điều kiện chính sách đều hợp lệ. Giao dịch này không tạo challenge mới nhưng vẫn có thể đáp ứng yêu cầu bảo đảm của ứng dụng.

Tương tự, một phiên hiện hữu có thể tiếp tục được chấp nhận trong giới hạn chính sách. Không nên buộc metric challenge rate tính những lần sử dụng phiên đó như challenge mới.

Để giải thích tỷ lệ, điểm quyết định có thể ghi nhận các kết quả tách biệt:

| Kết quả chính sách minh họa | Ý nghĩa |
| --- | --- |
| `require_new` | Cần challenge mới |
| `reuse_assurance` | Chấp nhận bằng chứng MFA còn hợp lệ theo chính sách |
| `exempt` | Chính sách cho phép miễn trong ngữ cảnh cụ thể |
| `deny` | Từ chối truy cập ở điểm quyết định |

Đây là bộ giá trị minh họa, không phải schema bắt buộc của mọi sản phẩm IAM. Khi dùng nó để đối soát, các kết quả phải loại trừ nhau và bao phủ đúng tập giao dịch đã định nghĩa.

Nếu một tổ chức bật SSO và tăng khả năng tái sử dụng hợp lệ bằng chứng MFA, challenge rate có thể giảm cùng với số lần người dùng bị gián đoạn. Để đánh giá thay đổi, cần xem cả tỷ lệ tái sử dụng bằng chứng, độ mới của xác thực theo chính sách và kết quả truy cập.

## 6. Ví dụ tính toán với một cohort hoàn chỉnh

Giả sử theo dõi 10.000 giao dịch đăng nhập đủ điều kiện. Mọi giao dịch trong cohort đã có kết quả chính sách; các challenge đã tới trạng thái kết thúc theo thời hạn quan sát.

| Kết quả ở điểm quyết định | Số giao dịch |
| --- | ---: |
| Yêu cầu challenge mới | 6.000 |
| Tái sử dụng bằng chứng MFA hợp lệ | 3.500 |
| Được miễn theo chính sách | 400 |
| Bị từ chối ở điểm quyết định | 100 |
| Tổng | 10.000 |

Trong 6.000 giao dịch yêu cầu challenge mới, có 5.800 giao dịch thực sự được phát hành challenge. 200 giao dịch còn lại cần được phân tích theo nguyên nhân cụ thể; không thể tự kết luận tất cả đều là lỗi nhà cung cấp.

Kết quả của 5.800 challenge đã phát hành:

| Trạng thái kết thúc | Số giao dịch |
| --- | ---: |
| Thành công | 5.220 |
| Xác minh thất bại | 290 |
| Hết hạn | 174 |
| Người dùng hủy hoặc bỏ dở, theo quy tắc phân loại đã chọn | 116 |
| Tổng | 5.800 |

Các tỷ lệ tương ứng:

```text
Challenge rate       = 5.800 / 10.000 × 100 = 58%
Requirement rate     = 6.000 / 10.000 × 100 = 60%
Issuance coverage    = 5.800 / 6.000 × 100 ≈ 96,67%
Completion rate      = 5.220 / 5.800 × 100 = 90%
```

Kết luận vận hành gồm hai phần riêng: 58% giao dịch gặp challenge mới; trong nhóm cần challenge mới vẫn còn khoảng trống phát hành 3,33%. Tỷ lệ hoàn thành 90% chỉ áp dụng cho nhóm đã nhận challenge, không phải toàn bộ giao dịch cần MFA.

Trong thực tế, người dùng đóng trình duyệt thường không tạo sự kiện kết thúc rõ ràng. Hệ thống cần quy tắc xác định `abandoned`, `expired` và `pending`, tránh gán một challenge đồng thời vào nhiều trạng thái. Những challenge còn đang chờ không nên bị kết luận là thất bại trước khi hết cửa sổ quan sát.

## 7. Cửa sổ thời gian và độ trễ sự kiện

Có hai cách nhìn hữu ích, với mức chính xác khác nhau.

### Theo dõi vận hành bằng cửa sổ trượt

Dashboard có thể lấy tốc độ phát hành challenge trong 15 phút chia cho tốc độ giao dịch tới điểm đánh giá trong cùng 15 phút. Cách này cho phản hồi nhanh nhưng hai luồng sự kiện không nhất thiết thuộc cùng cohort.

Ví dụ, giao dịch tới điểm đánh giá lúc 09:59:59, còn sự kiện phát hành tới lúc 10:00:02. Hai sự kiện nằm ở hai cửa sổ khác nhau. Sự chênh lệch dễ thấy khi lưu lượng ít, có hàng đợi hoặc độ trễ thu thập tăng.

Tỷ lệ cửa sổ ngắn đôi khi có thể vượt phạm vi kỳ vọng dù quy tắc đếm logic đúng. Không nên cắt về 100% rồi bỏ qua: cần kiểm tra độ trễ, mất dữ liệu, đếm trùng và sự nhất quán của phạm vi lọc.

### Báo cáo chính xác bằng cohort

Để tính tỷ lệ của cohort, chọn giao dịch theo thời điểm đi vào điểm đánh giá, rồi liên kết sự kiện phát hành của chính những giao dịch đó. Với completion rate, tiếp tục đợi đến khi các giao dịch kết thúc hoặc hết thời hạn quan sát đã công bố.

Báo cáo nên có thời điểm chốt dữ liệu, số giao dịch còn chờ và cách xử lý sự kiện đến muộn. Nhờ vậy, thay đổi do dữ liệu chưa đầy đủ không bị hiểu thành thay đổi chính sách.

## 8. Thiết kế metric và truy vấn minh họa

Một bộ counter có thể được tổ chức như sau:

```text
iam_auth_decisions_total{
  flow="signin",
  mfa_decision="require_new|reuse_assurance|exempt|deny"
}

iam_mfa_challenges_issued_total{flow="signin"}

iam_mfa_challenge_outcomes_total{
  flow="signin",
  outcome="success|failed|expired|abandoned"
}
```

Ký hiệu có dấu `|` phía trên chỉ mô tả tập giá trị có thể có. Mỗi mẫu thực tế chỉ mang một giá trị cụ thể, ví dụ `mfa_decision="require_new"`.

Các metric trong ví dụ chỉ bao gồm giao dịch của người dùng thuộc tập đủ điều kiện đã thống nhất. Counter quyết định tăng một lần khi có kết quả quyết định; counter phát hành tăng một lần cho giao dịch được challenge theo quy tắc chống trùng. Counter kết quả chỉ tăng khi challenge có trạng thái kết thúc theo định nghĩa hệ thống.

PromQL sau minh họa tỷ lệ challenge theo cửa sổ trượt:

```promql
100 *
sum(rate(iam_mfa_challenges_issued_total{flow="signin"}[15m]))
/
sum(rate(iam_auth_decisions_total{flow="signin"}[15m]))
```

Tỷ lệ chính sách yêu cầu challenge mới:

```promql
100 *
sum(rate(iam_auth_decisions_total{
  flow="signin", mfa_decision="require_new"
}[15m]))
/
sum(rate(iam_auth_decisions_total{flow="signin"}[15m]))
```

Các truy vấn này minh họa phép đo vận hành, không thay thế phép liên kết cohort. Khi không có lưu lượng, tầng hiển thị cần xử lý kết quả không xác định thành `N/A`. Cảnh báo cũng cần điều kiện số lượng giao dịch tối thiểu để tránh phản ứng với một vài sự kiện.

Khi tổng hợp nhiều instance hoặc ứng dụng, cộng tử số và mẫu số trước khi chia. Không lấy trung bình đơn giản các phần trăm: ứng dụng có 10 giao dịch không nên có trọng số ngang với ứng dụng có 100.000 giao dịch.

### Chọn chiều phân tích có giới hạn

Các chiều thường hữu ích gồm môi trường, ứng dụng đã đăng ký, loại luồng, nhóm chính sách và nhóm rủi ro. Tập giá trị cần được kiểm soát để số chuỗi thời gian không tăng vô hạn.

Không đưa user ID, email, transaction ID, challenge ID, địa chỉ IP hay token vào nhãn metric. Những định danh phục vụ đối soát có thể nằm trong log hoặc trace được kiểm soát truy cập; không ghi mã OTP, bí mật xác thực hay nội dung token. Chỉ giữ dữ liệu cần cho điều tra và áp dụng thời hạn lưu phù hợp.

Nếu muốn phân tích theo phương thức, cần phân biệt phương thức được đề nghị, được chọn và được thử. Một challenge có nhiều phương thức dự phòng không thể được cộng qua mọi phương thức rồi coi tổng đó là số giao dịch được challenge.

## 9. Đọc biến động và điều tra nguyên nhân

| Hiện tượng | Giả thuyết cần kiểm tra | Dữ liệu đối chiếu |
| --- | --- | --- |
| Challenge rate tăng sau triển khai | Chính sách yêu cầu xác minh thường xuyên hơn | Requirement rate, phiên bản chính sách, thời điểm rollout |
| Challenge rate tăng, requirement rate cũng tăng và tỷ lệ tái sử dụng giảm | Phiên hoặc bằng chứng xác thực không còn được chấp nhận như trước | Lý do không tái sử dụng, thay đổi thời hạn phiên, ngữ cảnh SSO |
| Requirement rate ổn định nhưng challenge rate giảm | Đường phát hành không đáp ứng đủ yêu cầu | Issuance coverage, lỗi điều phối, độ trễ và lỗi tích hợp |
| Challenge rate ổn định nhưng completion rate giảm | Khó khăn ở bước hoàn thành xác minh | Kết quả theo phương thức, thời gian hoàn thành, lỗi giao nhận |
| Challenge rate tăng trong một nhóm rủi ro | Chính sách phản ứng với ngữ cảnh rủi ro hoặc tín hiệu bị lệch | Kết quả đánh giá rủi ro, loại sự kiện, phiên bản bộ đánh giá |
| Tổng tỷ lệ giảm nhưng từng ứng dụng không đổi | Cơ cấu lưu lượng chuyển sang ứng dụng ít challenge hơn | Số giao dịch và tỷ lệ theo ứng dụng |

Một trình tự điều tra phù hợp bắt đầu bằng việc xác nhận metric còn cùng định nghĩa và cùng phạm vi. Tiếp theo, kiểm tra mức đầy đủ của dữ liệu và tách biến động do cơ cấu lưu lượng. Sau đó mới đối chiếu quyết định chính sách, phát hành và kết quả hoàn thành.

Nếu xuất hiện nhiều yêu cầu xác nhận liên tiếp với ít lần hoàn thành, cần xem cả số lần gửi lại, quyết định rủi ro và phản hồi từ người dùng để phân biệt lỗi tích hợp với hành vi lạm dụng. Challenge rate tổng hợp không đủ để tự kết luận nguyên nhân.

## 10. Đặt cảnh báo theo bối cảnh

Không nên đặt mục tiêu chung kiểu “MFA challenge rate phải càng cao càng tốt”. Chính sách truy cập quyết định lúc nào cần xác minh mới; quan sát phải giúp xác nhận chính sách đó được thực thi và người dùng có thể hoàn thành.

Một cảnh báo có ý nghĩa thường kết hợp:

- Mức lệch so với đường cơ sở của cùng ứng dụng, loại luồng và chu kỳ thời gian.
- Số giao dịch đủ lớn và biến động kéo dài đủ lâu.
- Issuance coverage hoặc completion rate để xác định tác động.
- Thông tin triển khai chính sách, SSO và phiên để giải thích thay đổi có chủ đích.
- Trạng thái thu thập dữ liệu để phân biệt sự cố IAM với thiếu telemetry.

Chẳng hạn, một ứng dụng có requirement rate ổn định quanh mức quen thuộc, nhưng issuance coverage giảm liên tục cùng với lỗi tạo challenge tăng. Tổ hợp này hữu ích hơn một cảnh báo chỉ nói challenge rate giảm, vì nó chỉ ra yêu cầu chính sách chưa được chuyển thành bước xác minh thực tế.

Với dashboard IAM, nên đặt challenge rate cạnh số giao dịch đủ điều kiện, requirement rate, issuance coverage, completion rate và độ trễ hoàn thành. Bộ chỉ số đó giúp nối ba câu hỏi: **chính sách yêu cầu gì, hệ thống đã phát hành gì và người dùng hoàn thành ra sao**.
