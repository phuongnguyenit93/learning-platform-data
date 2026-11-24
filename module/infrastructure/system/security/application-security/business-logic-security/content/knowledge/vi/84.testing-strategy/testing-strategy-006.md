# Abuse scenario tests — Kiểm thử tình huống lạm dụng nghiệp vụ

## 1. Mục tiêu và phạm vi

Một API có thể nhận dữ liệu đúng định dạng, xác thực token thành công và vẫn thực hiện một hành vi không được phép về mặt nghiệp vụ. Ví dụ người tạo tự duyệt hồ sơ, đặt hàng trước khi được duyệt, gửi đơn giá thấp hơn giá hợp lệ hoặc gửi hai yêu cầu đồng thời để dùng cùng một hạn mức hai lần.

**Abuse scenario test** là kiểm thử một tình huống trong đó người gọi cố đạt được kết quả trái với chính sách bằng cách lợi dụng dữ liệu, quyền, thứ tự thao tác, thời điểm hoặc sự lặp lại của yêu cầu. Mục tiêu là kiểm chứng hệ thống bảo vệ được các điều kiện nghiệp vụ, kể cả khi người gọi không tuân theo giao diện dự kiến.

Bài học thuộc module `SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`, tập trung vào business invariants, state machine, quyền theo đối tượng, transaction và idempotency. Các kịch bản được thực hiện trong môi trường kiểm thử được kiểm soát, với dữ liệu và dịch vụ ngoài được chuẩn bị cho mục đích kiểm thử.

Sau bài học, bạn có thể:

- Chuyển một quy tắc nghiệp vụ thành tình huống lạm dụng có thể thực thi.
- Chuẩn bị đúng chủ thể, đối tượng, trạng thái và lịch sử cho từng kịch bản.
- Kiểm chứng cả phản hồi, dữ liệu đã commit và hiệu lực phụ.
- Thiết kế kiểm thử cho yêu cầu trùng, cạnh tranh đồng thời và kết quả chưa xác định.
- Chọn lớp kiểm thử và mức ưu tiên phù hợp với rủi ro.

## 2. Phân biệt lỗi nhập liệu với lạm dụng nghiệp vụ

Kiểm tra `quantity = -1` là cần thiết, nhưng chưa đủ để chứng minh quy trình mua hàng an toàn. Nhiều tình huống lạm dụng sử dụng toàn bộ giá trị hợp lệ nếu xét riêng từng trường.

| Kiểu kiểm thử | Ví dụ | Câu hỏi chính |
| --- | --- | --- |
| Kiểm tra dữ liệu đầu vào | Số lượng âm, ngày sai định dạng | Dữ liệu có đáp ứng ràng buộc của trường không? |
| Kiểm tra luồng thông thường | Người có quyền duyệt hồ sơ đang chờ | Chức năng có làm đúng việc được phép không? |
| Kiểm tra quyền theo đối tượng | Người có vai trò duyệt dùng ID hồ sơ ngoài phạm vi | Chủ thể này có được thực hiện hành động trên đúng đối tượng này không? |
| Kiểm tra sai trình tự | Gọi đặt hàng khi hồ sơ còn là bản nháp | Có bỏ qua được bước bắt buộc không? |
| Kiểm tra lặp lại và đồng thời | Gửi hai yêu cầu để sử dụng cùng hạn mức | Có tạo thêm hiệu lực trái với bất biến không? |
| Kiểm tra lịch sử | Sửa số tiền sau khi đã được duyệt | Quyết định cũ có bị áp dụng sai cho nội dung mới không? |

Một yêu cầu trả về mã lỗi vẫn có thể làm rò dữ liệu hoặc tạo hiệu lực phụ trước khi lỗi xảy ra. Một yêu cầu trả thành công cũng có thể an toàn nếu hợp đồng cho phép bỏ qua trường client không được quyền quyết định. Vì vậy kết luận cần dựa trên chính sách, kết quả nghiệp vụ và dữ liệu thực tế, không chỉ dựa trên mã HTTP.

## 3. Bắt đầu từ bất biến và mục tiêu của người lạm dụng

### 3.1. Viết bất biến đủ cụ thể

Bất biến là điều kiện phải đúng với trạng thái nghiệp vụ được ghi nhận. Câu “phải bảo mật thanh toán” quá rộng để tạo kiểm thử. Các phát biểu sau có thể kiểm chứng rõ hơn:

1. Người tạo không được phê duyệt hồ sơ do chính mình tạo.
2. Chỉ hồ sơ ở trạng thái cho phép, với revision hiện tại đã được duyệt hợp lệ, mới được đặt hàng.
3. Người dùng thuộc tổ chức A không được đọc hoặc thay đổi hồ sơ thuộc tổ chức B nếu không có quyền liên tổ chức được cấp rõ ràng.
4. Tổng tiền được xác định từ dữ liệu giá, số lượng và ưu đãi được server xác minh theo chính sách.
5. Tổng tiền được giữ hoặc sử dụng từ một hạn mức không vượt giá trị còn được phép dùng.
6. Một thao tác thanh toán logic chỉ tạo tối đa một hiệu lực tài chính tương ứng trong phạm vi hợp đồng xử lý.
7. Thay đổi trường trọng yếu phải làm mất hiệu lực của phê duyệt cũ khi chính sách yêu cầu duyệt lại.

Với mỗi bất biến, chỉ rõ phạm vi. Chẳng hạn “mỗi đơn hàng chỉ thu tiền một lần” có thể sai với hệ thống hỗ trợ thu tiền nhiều đợt. Bất biến đúng có thể là “mỗi kỳ thu của một đơn chỉ có một khoản thu thành công”, còn tổng tiền các kỳ không vượt số tiền phải trả. Kiểm thử cần bám vào chính sách thật của hệ thống.

### 3.2. Đảo quy tắc thành mục tiêu lạm dụng

| Bất biến | Mục tiêu lạm dụng | Cách biến đổi yêu cầu hoặc lịch sử |
| --- | --- | --- |
| Không được tự duyệt | Tự cấp phê duyệt cho hồ sơ của mình | Gọi API duyệt trực tiếp bằng tài khoản người tạo |
| Duyệt đúng revision | Dùng phê duyệt cho nội dung rẻ để mua nội dung đắt | Duyệt revision cũ rồi sửa số lượng hoặc mặt hàng |
| Giá được server xác minh | Trả ít hơn số tiền hợp lệ | Sửa giá, tổng tiền, mã ưu đãi hoặc tham chiếu báo giá |
| Quyền theo đối tượng | Đọc hoặc sửa hồ sơ ngoài phạm vi | Thay ID hồ sơ, ID tổ chức hoặc ID đối tượng con |
| Hạn mức không vượt trần | Dùng hạn mức hai lần | Gửi các yêu cầu hợp lệ riêng lẻ cùng lúc |
| Một hiệu lực cho thao tác logic | Tạo thu tiền, hoàn tiền hoặc đặt hàng trùng | Phát lại, đổi khóa idempotency, gửi trùng sự kiện |

Từ đó chọn các biến thể mang rủi ro cao. Không cần tạo hàng nghìn payload ngẫu nhiên nếu chưa xác định được hành vi trái chính sách cần phát hiện.

## 4. Cấu trúc một kịch bản có thể tái hiện

Một kịch bản tốt cần đủ thông tin để người khác chạy lại và hiểu vì sao kết quả đúng hoặc sai.

```yaml
scenarioId: creator-cannot-approve-own-purchase
invariant: Người tạo không được tự duyệt hồ sơ của mình
attackerGoal: Làm hồ sơ được duyệt mà không có người duyệt độc lập
actor: Người tạo hồ sơ, chưa có ngoại lệ được cấp
resource: Hồ sơ thuộc cùng tổ chức, do actor tạo
initialState: SUBMITTED, revision 7, chưa có phê duyệt hợp lệ
action: Gọi trực tiếp endpoint duyệt, bỏ qua giao diện
expectedDecision: Từ chối hành động tự duyệt
protectedState:
  - Hồ sơ vẫn ở SUBMITTED
  - Không có phê duyệt hợp lệ cho revision 7
  - Không có sự kiện hồ sơ đã được duyệt
allowedSideEffects:
  - Dấu vết từ chối theo chính sách kiểm toán
```

Đây là mẫu mô tả trong bài học, không phải yêu cầu tạo thêm tệp cấu hình. Khi xây dựng bộ test thật, có thể biểu diễn cùng thông tin bằng mã, dữ liệu test hoặc tài liệu tùy cách tổ chức của dự án.

Các thành phần cần có:

- **Tiền điều kiện:** dữ liệu, trạng thái, revision, quyền và lịch sử trước hành động.
- **Hành động lạm dụng:** yêu cầu trực tiếp hoặc chuỗi yêu cầu cụ thể.
- **Kết quả quyết định:** bị từ chối, trả xung đột, phát lại kết quả cũ hoặc xử lý theo hợp đồng.
- **Trạng thái được bảo vệ:** dữ liệu nào không được thay đổi trái chính sách.
- **Hiệu lực phụ:** sự kiện, sổ giao dịch, giữ chỗ, thông báo hoặc tác động tới dịch vụ ngoài.
- **Thời điểm quan sát:** sau commit, sau xử lý bất đồng bộ hoặc sau đối soát có giới hạn thời gian.

“Không có thay đổi nào” thường là kỳ vọng quá rộng. Bộ đếm chống lạm dụng, bản ghi từ chối hoặc thông tin kiểm toán có thể được cập nhật hợp lệ. Hãy chỉ rõ các thay đổi nghiệp vụ bị cấm và các thay đổi quan sát được phép xảy ra.

## 5. Chuẩn bị chủ thể và dữ liệu đối chứng

Giả sử hệ thống mua hàng có các tài khoản kiểm thử sau:

| Chủ thể | Phạm vi và quyền | Mục đích kiểm thử |
| --- | --- | --- |
| An | Người tạo thuộc tổ chức A | Tạo hồ sơ, thử tự duyệt hoặc sửa trường vượt quyền |
| Bình | Người duyệt được phân công trong tổ chức A | Chứng minh đường duyệt hợp lệ hoạt động |
| Chi | Người cùng tổ chức A nhưng không được phân công | Phát hiện kiểm tra quá rộng ở mức cùng tổ chức |
| Duy | Người thuộc tổ chức B | Kiểm tra cô lập giữa các tổ chức |
| Tài khoản tích hợp | Chỉ có các quyền tích hợp được cấp | Kiểm tra giới hạn hành động của tài khoản dịch vụ |

Tên chủ thể chỉ dùng để dễ theo dõi; khi thực thi, tạo định danh riêng cho mỗi lần chạy để tránh xung đột dữ liệu dùng chung.

Mỗi test từ chối quan trọng nên có một trường hợp đối chứng hợp lệ. Ví dụ:

- Bình duyệt đúng hồ sơ đang được phân công: thành công.
- Chi duyệt cùng hồ sơ: bị từ chối.
- Duy dùng ID của hồ sơ đó: không đọc hay sửa được ngoài quyền.
- An tạo hồ sơ rồi tự duyệt: bị từ chối theo quy tắc tách biệt trách nhiệm.

Đối chứng giúp phát hiện tình huống test vượt qua vì dữ liệu dựng sai, endpoint luôn lỗi hoặc hệ thống từ chối tất cả. Một bộ kiểm thử chỉ chứa đường bị cấm có thể bỏ sót việc chức năng hợp lệ đã hỏng.

Nên tạo trạng thái qua các luồng hợp lệ khi có thể. Với tiền điều kiện khó đạt, chẳng hạn lịch sử cụ thể hoặc revision cũ, fixture có kiểm soát có thể phù hợp. Tuy nhiên, cần tách lỗi dựng dữ liệu khỏi lỗi của chức năng đang kiểm tra và không coi một trạng thái bất khả thi do fixture tạo ra là trạng thái người dùng chắc chắn đạt được.

## 6. Nhóm kịch bản về quyền và phạm vi đối tượng

### 6.1. Thay định danh đối tượng

Không chỉ thử thay ID ở đường dẫn. ID có thể nằm trong body, query, đối tượng lồng nhau, đường dẫn tải tệp hoặc API tra cứu thao tác.

Ví dụ người gọi được sửa hồ sơ `P-A` nhưng không được sửa `P-B`. Các biến thể cần xem xét:

- Đường dẫn dùng `P-A`, body khai báo `purchaseId=P-B`.
- Hồ sơ cha là `P-A` nhưng `lineItemId` thuộc `P-B`.
- Body dùng `tenantId=B` trong khi ngữ cảnh xác thực thuộc tổ chức A.
- API cập nhật bị chặn nhưng endpoint nhân bản, xuất dữ liệu hoặc khôi phục bản nháp vẫn nhận `P-B`.

Kỳ vọng cần bao gồm việc không sửa đối tượng ngoài phạm vi, không gắn đối tượng con sai chủ và không trả dữ liệu vượt quyền. Nếu server bỏ qua trường tổ chức từ client và dùng phạm vi xác thực, kiểm tra rằng trường bị bỏ qua không ảnh hưởng kết quả.

### 6.2. Thay quyền giữa hai bước

Một kịch bản có lịch sử:

1. Bình mở hồ sơ khi đang có quyền duyệt.
2. Quyền được thu hồi hoặc hồ sơ được chuyển sang đơn vị ngoài phạm vi.
3. Bình gửi yêu cầu duyệt từ trang vẫn đang mở.
4. Server đánh giá theo chính sách quyền có hiệu lực tại thời điểm xử lý.

Chính sách thu hồi có thể phụ thuộc cách quản lý phiên, token và bộ nhớ đệm. Test cần nêu rõ độ trễ thu hồi được cho phép và quan sát theo cam kết đó, thay vì mặc định mọi thay đổi quyền đều có hiệu lực tức thời trong mọi kiến trúc.

### 6.3. Đọc kết quả cũ và dữ liệu lỗi

Phát lại một khóa idempotency hoặc tra cứu một mã thao tác cũng là truy cập dữ liệu. Thử dùng định danh thao tác của chủ thể khác, đồng thời kiểm tra quyền hiện tại nếu hệ thống có thể thu hồi quyền xem kết quả.

Nếu chính sách yêu cầu che giấu sự tồn tại của tài nguyên, kiểm tra nội dung công khai của phản hồi, mã lỗi nghiệp vụ và các đường truy vấn liên quan. Không chỉ kiểm tra câu thông báo trên giao diện trong khi body vẫn trả tên tổ chức hoặc trạng thái nội bộ. Kiểm tra thời gian phản hồi cần phương pháp thống kê riêng nếu thuộc mô hình đe dọa; một phép so sánh thời gian đơn lẻ thường không đủ kết luận.

## 7. Nhóm kịch bản về state machine và phê duyệt

### 7.1. Kiểm tra cả chuyển trạng thái được phép và bị cấm

Ví dụ hợp đồng nghiệp vụ đơn giản:

| Trạng thái hiện tại | Hành động | Điều kiện bổ sung | Kỳ vọng |
| --- | --- | --- | --- |
| DRAFT | Gửi duyệt | Người tạo có quyền, dữ liệu hợp lệ | Chuyển sang SUBMITTED |
| DRAFT | Đặt hàng | Chưa có phê duyệt | Bị từ chối |
| SUBMITTED | Duyệt | Người duyệt độc lập, đúng phạm vi | Chuyển sang APPROVED cho revision hiện tại |
| SUBMITTED | Tự duyệt | Người gọi là người tạo | Bị từ chối |
| APPROVED | Đặt hàng | Phê duyệt và điều kiện còn hiệu lực | Tạo đơn theo quy tắc |
| CANCELLED | Đặt hàng | Không có đường mở lại theo chính sách | Bị từ chối |

Đây là bảng minh họa, không phải quy tắc chung cho mọi hệ thống. Mỗi dự án cần bảng chuyển trạng thái và điều kiện tương ứng với nghiệp vụ của mình.

### 7.2. Kiểm tra phê duyệt gắn với nội dung

Chuỗi lạm dụng điển hình:

```text
Tạo hồ sơ revision 7 với số lượng nhỏ
  -> Gửi duyệt và được duyệt revision 7
  -> Sửa số lượng hoặc người nhận để tạo revision 8
  -> Gửi yêu cầu đặt hàng với phê duyệt revision 7
```

Kỳ vọng: nếu trường thay đổi là trọng yếu theo chính sách, revision 8 chưa đủ điều kiện đặt hàng. Kiểm tra cả trạng thái, revision được duyệt và đơn hàng thực tế; không chỉ kiểm tra trường `approved=true`.

Các biến thể gồm phát lại yêu cầu duyệt cũ, gửi `status=APPROVED` từ client, chèn ID phê duyệt của hồ sơ khác hoặc dùng endpoint chỉnh sửa phụ để tránh tăng revision. Quy tắc phải được bảo vệ ở tất cả đường có thể thay đổi nội dung liên quan.

### 7.3. Ví dụ kiểm thử bằng giả mã

```text
given:
  hồ sơ của An thuộc tổ chức A
  revision 7 đã được Bình duyệt hợp lệ
  số lượng là trường bắt buộc duyệt lại khi thay đổi

when:
  An sửa số lượng qua chức năng được phép, tạo revision 8
  An gọi trực tiếp đặt hàng và gửi tham chiếu phê duyệt revision 7

then:
  thao tác đặt hàng không được chấp nhận cho revision 8
  không có đơn hàng mới cho lần đặt này
  không có giữ chỗ hoặc yêu cầu thu tiền do lần đặt bị cấm tạo ra
  revision 8 cần phê duyệt mới theo chính sách
  bản ghi kiểm toán phản ánh sự kiện nếu chính sách yêu cầu
```

Trường hợp đối chứng: sau khi revision 8 được người có quyền duyệt hợp lệ, đặt hàng thành công theo điều kiện còn lại. Nhờ vậy test chứng minh hệ thống chặn đúng việc dùng phê duyệt cũ, thay vì vô tình chặn mọi lần đặt hàng.

## 8. Nhóm kịch bản về giá, ưu đãi và hạn mức

### 8.1. Chuẩn bị kỳ vọng độc lập

Giả sử dữ liệu kiểm thử xác định đơn giá là `100000 VND`, số lượng là `2`, ưu đãi hợp lệ là `10000 VND` và ví dụ này không có thuế hay phí khác. Tổng phải trả là:

```text
2 × 100000 - 10000 = 190000 VND
```

Thử gửi `unitPrice=1`, `discount=199999` hoặc `total=1`. Tùy hợp đồng, server có thể từ chối trường không được phép hoặc bỏ qua giá trị đó rồi tự xác định số tiền. Trong cả hai cách, dữ liệu đã ghi và yêu cầu thanh toán phải tuân thủ số tiền hợp lệ; không được tạo đơn với tổng tiền do người gọi tùy ý quyết định.

Kỳ vọng nên được tính từ fixture và quy tắc đã xác định. Nếu test gọi lại đúng hàm tính giá của production để tạo giá trị mong đợi, cùng một lỗi trong hàm có thể khiến cả kết quả và kỳ vọng đều sai theo cùng cách.

### 8.2. Kiểm tra tổ hợp có ý nghĩa

- Ưu đãi thuộc người dùng hoặc tổ chức khác.
- Mã hết hạn hoặc không áp dụng cho mặt hàng đang mua.
- Ghép nhiều ưu đãi vốn không được phép cộng dồn.
- Chia một đơn thành nhiều đơn để vượt chính sách giới hạn theo người hoặc theo kỳ.
- Dùng báo giá cũ sau khi sửa số lượng, tiền tệ hoặc đối tượng nhận hàng.
- Dùng tổng tiền bằng không hoặc giá trị sát ngưỡng phê duyệt.
- Thử ranh giới làm tròn và đơn vị tiền khi hệ thống hỗ trợ nhiều loại tiền.

Không mặc định mọi cách chia đơn đều là lạm dụng. Nếu chính sách chỉ giới hạn theo đơn mà không giới hạn theo người hay kỳ, test không nên tự áp đặt một quy tắc chưa được yêu cầu. Khi phát hiện khoảng trống chính sách, ghi nhận để làm rõ trước khi biến nó thành kết quả mong đợi.

### 8.3. Kiểm tra tổng hợp sau nhiều thao tác

Một lần hoàn `60000 VND` có thể hợp lệ, nhưng hoàn hai lần cho giao dịch chỉ thu `100000 VND` có thể vi phạm chính sách. Kiểm tra số dư hoặc sổ giao dịch sau toàn bộ chuỗi, không chỉ giới hạn của từng request.

Với tiền, xác định rõ đơn vị lưu, quy tắc làm tròn và thời điểm áp dụng. Dùng giá trị kỳ vọng chính xác phù hợp mô hình tiền của hệ thống, tránh phép so sánh gần đúng che mất sai lệch có ý nghĩa tài chính.

## 9. Nhóm kịch bản về yêu cầu trùng và idempotency

Kiểm thử idempotency cần phân biệt **số request**, **số lần gọi dịch vụ** và **số hiệu lực nghiệp vụ**. Ba số này không nhất thiết bằng nhau.

| Tình huống | Kỳ vọng cần kiểm chứng |
| --- | --- |
| Cùng khóa, cùng nội dung, gửi lần lượt | Kết quả theo hợp đồng phát lại; không thêm hiệu lực nghiệp vụ |
| Cùng khóa, cùng nội dung, gửi đồng thời | Cơ chế đăng ký thao tác chịu được cạnh tranh; không xử lý trùng |
| Cùng khóa nhưng đổi số tiền hoặc người nhận | Không thay nội dung thao tác đã được ghi nhận; xử lý xung đột theo hợp đồng |
| Khác khóa nhưng cùng đối tượng và cùng hiệu lực bị giới hạn | Bất biến trên đối tượng vẫn chặn hiệu lực trùng |
| Mất phản hồi sau khi đã commit | Tra cứu hoặc phát lại nhận diện được thao tác cũ |
| Dùng khóa hoặc định danh thao tác của chủ thể khác | Không vượt phạm vi truy cập hoặc đọc kết quả trái phép |
| Phát lại sau cửa sổ lưu khóa | Xử lý theo hợp đồng và ràng buộc nghiệp vụ; không suy luận rằng hiệu lực cũ đã biến mất |

Ví dụ hai yêu cầu đặt hàng dùng hai khóa khác nhau vẫn có thể phải tạo tối đa một đơn cho một hồ sơ, nếu đó là chính sách. Chỉ kiểm thử “cùng khóa tạo một đơn” sẽ bỏ sót việc người gọi đổi khóa để vượt giới hạn trên hồ sơ.

Nếu hệ thống ghi nhớ cả kết quả từ chối cuối cùng, cần kiểm tra hành vi phát lại đúng hợp đồng. Một khóa cũ không nhất thiết có nghĩa “đánh giá lại yêu cầu theo quyền và giá mới”. Thao tác mới sau khi sửa dữ liệu phải được phân biệt rõ với việc hỏi lại kết quả của thao tác trước.

Với thanh toán ngoài hệ thống, bộ giả lập nên ghi nhận định danh thao tác và hiệu lực được chấp nhận. Có thể cho phép nhiều lần gọi kỹ thuật nhưng vẫn chỉ có một khoản thu logic. Chỉ khẳng định “gọi dịch vụ đúng một lần” nếu đó thật sự là yêu cầu của thiết kế; một kiến trúc có retry hợp lệ có thể gọi nhiều lần với cùng định danh an toàn.

Với webhook hoặc thông điệp trùng, phát lại cùng sự kiện và các biến thể có ý nghĩa theo hợp đồng nguồn. Kiểm chứng đơn hàng, sổ giao dịch và thông báo nghiệp vụ không bị cộng lặp sai. Không coi việc đã lưu `eventId` là đủ nếu việc lưu đó và cập nhật nghiệp vụ có thể lệch nhau khi tiến trình lỗi.

## 10. Nhóm kịch bản đồng thời và transaction

### 10.1. Một ví dụ vượt hạn mức

Hạn mức còn lại là `1000000 VND`. Hai yêu cầu độc lập đều muốn giữ `700000 VND`. Từng yêu cầu hợp lệ nếu chạy một mình, nhưng không thể chấp nhận cả hai theo bất biến này.

```text
given:
  một hạn mức có 1000000 VND khả dụng
  hai yêu cầu khác nhau, mỗi yêu cầu cần 700000 VND
  cả hai chủ thể đều có quyền, không có lý do từ chối khác

when:
  cho hai yêu cầu bắt đầu xử lý gần đồng thời
  chờ cả hai nhận kết quả cuối cùng theo hợp đồng

then:
  chỉ một yêu cầu giữ tiền thành công
  tổng tiền giữ là 700000 VND
  phần khả dụng là 300000 VND
  yêu cầu còn lại bị xử lý xung đột hoặc từ chối phù hợp
  không có số dư âm hoặc hai hiệu lực giữ tiền đã commit
```

Để tăng khả năng tái hiện cạnh tranh, dùng cơ chế đồng bộ điểm bắt đầu trong bộ kiểm thử hoặc điểm điều khiển dành riêng cho môi trường test. Không dựa vào một khoảng ngủ tùy ý rồi hy vọng hai request đụng nhau.

Điểm đồng bộ cần được đặt cẩn thận. Nếu một request đã giữ khóa mà còn chờ request kia đi qua cùng khóa để báo sẵn sàng, chính bộ test có thể tạo deadlock. Mục tiêu là kiểm tra lịch thực thi có ý nghĩa, không thay đổi cơ chế đồng bộ của hệ thống theo cách khiến lỗi không thể xảy ra.

### 10.2. Các cặp hành động nên thử

- Duyệt và hủy cùng hồ sơ.
- Sửa nội dung và đặt hàng dựa trên phê duyệt cũ.
- Hai yêu cầu dùng cùng mã ưu đãi chỉ còn một lượt.
- Hai lần hoàn tiền cùng phần tiền còn được hoàn.
- Thu hồi quyền và thực hiện hành động nhạy cảm, theo mô hình hiệu lực quyền đã định nghĩa.

Kỳ vọng là các kết quả đã commit phải tương thích với bất biến và quy tắc phân xử của hệ thống. Không ép một request cụ thể luôn thắng nếu chính sách không yêu cầu thứ tự đó.

### 10.3. Tiêm lỗi tại ranh giới quan trọng

Tạo lỗi có kiểm soát ở các điểm như sau:

1. Sau khi kiểm tra điều kiện nhưng trước khi ghi trạng thái.
2. Sau khi ghi một phần thay đổi trong transaction nhưng trước commit.
3. Sau commit nhưng trước khi phản hồi tới client.
4. Sau khi ghi outbox nhưng trước khi bên gửi sự kiện hoàn tất.
5. Sau khi dịch vụ ngoài tạo hiệu lực nhưng trước khi hệ thống nhận phản hồi.

Với thay đổi cùng transaction, lỗi trước commit không được để lại trạng thái nghiệp vụ dở dang. Với hiệu lực bên ngoài, rollback database không tự hoàn tác được giao dịch ngoài hệ thống; test cần kiểm tra trạng thái chưa xác định, đối soát hoặc quy trình bù trừ theo thiết kế.

Một test có tiêm lỗi nhưng chỉ kiểm tra exception đã xuất hiện chưa chứng minh tính nhất quán. Cần đọc lại dữ liệu đã commit và kiểm tra các hiệu lực liên quan bằng một ngữ cảnh quan sát phù hợp.

## 11. Thiết kế oracle: điều gì chứng minh hệ thống đã chặn đúng?

Oracle là cơ sở để kết luận kết quả kiểm thử đúng hay sai. Với lạm dụng nghiệp vụ, nên có nhiều lớp bằng chứng bổ trợ.

| Lớp quan sát | Ví dụ kiểm chứng | Lỗi có thể phát hiện |
| --- | --- | --- |
| Phản hồi API | Quyết định từ chối hoặc xung đột đúng hợp đồng, không lộ dữ liệu | Sai ánh xạ lỗi, rò thông tin |
| Trạng thái đối tượng | Revision, trạng thái và chủ sở hữu đúng | Chuyển trạng thái trái phép dù trả lỗi |
| Sổ nghiệp vụ hoặc ràng buộc dữ liệu | Tổng giữ tiền, số đơn, số phê duyệt hợp lệ | Cộng lặp, vượt hạn mức, ghi không nguyên tử |
| Sự kiện và tích hợp | Không có hiệu lực không được phép, không cộng lặp khi xử lý lại | Thao tác phụ đã xảy ra trước khi từ chối |
| Kiểm toán | Có dấu vết cần thiết, không ghi bí mật | Thiếu khả năng điều tra hoặc lộ dữ liệu trong log |

### 11.1. Đọc trạng thái thực sự đã commit

Một test chạy trong transaction bao ngoài có thể nhìn thấy thay đổi chưa commit hoặc che mất hành vi cạnh tranh. Với kiểm thử tích hợp, cần hiểu ranh giới transaction của ứng dụng và của framework test. Khi phù hợp, đọc lại bằng kết nối hoặc ngữ cảnh mới để xác minh dữ liệu đã commit.

Không dùng đối tượng còn trong bộ nhớ làm bằng chứng duy nhất cho dữ liệu lưu. Đối tượng có thể chưa được ghi hoặc đã bị rollback trong khi giá trị trong bộ nhớ vẫn đổi.

### 11.2. Quan sát hệ thống bất đồng bộ

Không kết luận “không có hiệu lực” ngay khi API trả về nếu worker vẫn có thể xử lý sau đó. Cần một điểm quan sát xác định, chẳng hạn thao tác đã kết thúc và các thông điệp liên quan đã được xử lý trong môi trường kiểm thử.

Chờ theo điều kiện với thời hạn tối đa; khi hết hạn mà thao tác còn treo, test phải thất bại với bằng chứng trạng thái hiện tại. Không chuyển kết quả chưa xác định thành thành công chỉ vì chưa nhìn thấy bản ghi xấu trong một khoảng ngắn.

Với hệ thống cho phép giao thông điệp lặp, có thể tồn tại nhiều lần giao kỹ thuật. Oracle nên kiểm tra hiệu lực nghiệp vụ và các định danh logic cần duy nhất, thay vì mặc định mọi thông điệp vật lý chỉ được xuất hiện một lần.

### 11.3. Tránh kỳ vọng tự xác nhận

Không xây oracle bằng cùng nhánh quyết định đang được kiểm tra. Ví dụ test quyền không nên gọi lại chính hàm `canApprove` để quyết định rằng người gọi đáng lẽ được duyệt hay không. Hãy lấy kỳ vọng từ bảng chính sách độc lập và fixture rõ ràng.

Các quan hệ bảo toàn có thể làm oracle mạnh hơn: tổng đã thu trừ tổng đã hoàn bằng số dư tương ứng; tổng giữ không vượt hạn mức; mỗi phê duyệt hợp lệ gắn với đúng hồ sơ và revision. Cần điều chỉnh phương trình theo chính sách thực tế về phí, tiền tệ và các loại giao dịch.

## 12. Kiểm thử dựa trên mô hình, thuộc tính và phép biến đổi

### 12.1. Sinh chuỗi hành động từ mô hình nhỏ

Với state machine, một mô hình tham chiếu nhỏ có thể giữ trạng thái, revision và quyền tối thiểu. Bộ sinh tạo chuỗi gồm cả hành động hợp lệ và hành động vi phạm điều kiện, chẳng hạn:

```text
tạo -> gửi duyệt -> tự duyệt -> duyệt hợp lệ -> sửa -> đặt hàng
```

Sau mỗi bước, so kết quả hệ thống với quyết định của mô hình và kiểm tra bất biến. Không chỉ so kết quả cuối cùng, vì một chuyển trạng thái sai ở giữa có thể bị thao tác sau đó che khuất.

Mô hình phải đơn giản và được xem xét độc lập. Sao chép toàn bộ mã production sang mô hình có thể sao chép luôn lỗi. Khi phát hiện chuỗi lỗi, lưu seed và rút gọn chuỗi để có ca hồi quy dễ hiểu.

### 12.2. Các thuộc tính có ích

- Phát lại cùng một thao tác theo hợp đồng không làm tăng số hiệu lực nghiệp vụ tương ứng.
- Một hành động bị cấm không tạo phê duyệt hoặc chuyển trạng thái được bảo vệ.
- Đổi sang chủ thể không có quyền không mở thêm dữ liệu hay hành động trên cùng đối tượng.
- Chỉ thay tổng tiền do client tự khai không được làm thay đổi số tiền server xác định hợp lệ.
- Khi nội dung trọng yếu thay đổi, phê duyệt cũ không trở thành phê duyệt cho nội dung mới.

Thuộc tính cần bao gồm tiền điều kiện rõ ràng. Ví dụ thu hồi quyền đọc có thể khiến phát lại không còn trả được nội dung kết quả cũ; điều đó không mâu thuẫn với yêu cầu không tạo thêm hiệu lực.

### 12.3. Kiểm thử bằng phép biến đổi

Từ một yêu cầu hợp lệ, tạo một biến thể có chủ đích:

- Giữ nội dung, đổi chủ thể sang người không được phân công.
- Giữ chủ thể, đổi đối tượng sang tổ chức khác.
- Giữ đối tượng, đổi revision sang phiên bản cũ.
- Giữ ý định, phát lại hoặc thay thời điểm gửi.

Ưu điểm là dễ chỉ ra yếu tố khiến quyết định phải thay đổi. Tuy nhiên, sau khi đổi đối tượng cần đảm bảo fixture còn đáp ứng các tiền điều kiện khác; nếu đối tượng mới không tồn tại thì test chưa chứng minh đã kiểm tra quyền trên một đối tượng tồn tại ngoài phạm vi.

## 13. Chọn lớp kiểm thử và tổ chức chạy

| Lớp kiểm thử | Phù hợp để kiểm chứng | Giới hạn |
| --- | --- | --- |
| Unit hoặc domain test | Quy tắc quyền, bảng chuyển trạng thái, tính tiền và revision | Không chứng minh được khóa, transaction hoặc ràng buộc database thật |
| Integration test với database phù hợp | Cập nhật nguyên tử, ràng buộc duy nhất, đồng thời, outbox | Cần kiểm soát dữ liệu, cấu hình và lịch thực thi |
| API test | Bỏ qua UI, thay ID, trường vượt quyền, hợp đồng lỗi | Cần thêm oracle dữ liệu để phát hiện hiệu lực ẩn |
| Kiểm thử tích hợp dịch vụ ngoài | Timeout, retry, thông báo trùng, đối soát | Bộ giả lập cần mô phỏng đúng ngữ nghĩa cần kiểm tra |
| End-to-end test | Một số chuỗi rủi ro cao qua các thành phần thật | Chi phí cao, khó chẩn đoán nếu dùng cho mọi biến thể |

Chọn lớp thấp nhất có thể chứng minh rủi ro đang xét, rồi bổ sung một số đường tích hợp quan trọng. Không dùng nhiều end-to-end test giống nhau để thay cho việc kiểm chứng ràng buộc đồng thời ở database.

Mock hữu ích để tạo phản hồi ngoài hệ thống và tiêm lỗi, nhưng mock repository không thể chứng minh hệ quản trị dữ liệu thực thi khóa hoặc mức cô lập như mong đợi. Với test đồng thời, cần môi trường đủ tương đồng về các đặc tính đó.

Một cách phân nhóm thực tế:

- Nhóm chạy nhanh khi thay đổi mã: quyền, chuyển trạng thái, giá, các ca API trọng yếu.
- Nhóm tích hợp bắt buộc cho thay đổi nhạy cảm: transaction, idempotency, cạnh tranh và hiệu lực phụ liên quan.
- Nhóm mở rộng theo lịch phù hợp với dự án: nhiều seed, lịch cạnh tranh và tình huống lỗi dài hơn.

Lịch chạy không được biến thành lý do bỏ qua ca rủi ro cao khi đang sửa chính cơ chế bảo vệ đó. Khi một kiểm thử phát hiện lỗi thực, giữ lại phiên bản tái hiện nhỏ trong nhóm hồi quy phù hợp.

## 14. Ma trận bao phủ và ưu tiên theo rủi ro

Ma trận giúp nhìn thấy khoảng trống giữa quy tắc và bằng chứng kiểm thử. Ví dụ sau dùng cho hệ thống mua hàng minh họa:

| Quy tắc | Chủ thể hoặc biến thể | Test chính | Bằng chứng bắt buộc |
| --- | --- | --- | --- |
| Không tự duyệt | Người tạo, kể cả khi có một số quyền duyệt khác | Gọi API duyệt hồ sơ của mình | Không có phê duyệt hợp lệ hoặc sự kiện duyệt |
| Đúng phạm vi đối tượng | Cùng tổ chức nhưng ngoài phân công; khác tổ chức | Thay ID cha, ID con và ID tổ chức | Không đọc hoặc sửa vượt phạm vi |
| Phê duyệt đúng nội dung | Revision cũ và trường trọng yếu đổi | Duyệt, sửa rồi đặt hàng | Không tạo đơn dựa trên phê duyệt cũ |
| Giá đáng tin cậy | Giá hoặc tổng tiền do client sửa | Gửi payload giá giả | Số tiền lưu và thanh toán đúng chính sách |
| Hạn mức không vượt trần | Hai yêu cầu hợp lệ riêng lẻ | Chạy đồng thời | Tổng đã commit trong giới hạn |
| Không tạo hiệu lực trùng | Cùng khóa, khác khóa, thông điệp trùng | Phát lại và cạnh tranh | Số hiệu lực đúng hợp đồng |
| Nhất quán khi lỗi | Trước commit, sau commit, sau hiệu lực ngoài | Tiêm lỗi tại ranh giới | Không có trạng thái dở dang trái chính sách; kết quả treo được giải quyết |

Ưu tiên dựa trên hậu quả, khả năng tiếp cận, khả năng khai thác và độ khó phát hiện sau sự cố. Các thao tác chuyển tiền, hoàn tiền, cấp quyền, duyệt giao dịch lớn hoặc truy cập dữ liệu liên tổ chức thường cần bằng chứng mạnh hơn một chức năng chỉnh sửa mô tả thông thường.

Độ bao phủ dòng lệnh cao không chứng minh đã bao phủ tình huống lạm dụng. Một nhánh `if` có thể đã chạy nhưng chưa bao giờ được thử với chủ thể sai, đối tượng sai, revision cũ hoặc hai yêu cầu đồng thời.

## 15. Đọc lỗi test và chuyển thành hồi quy

Khi test thất bại, thu thập bằng chứng đủ tái hiện: mã kịch bản, seed nếu có, chủ thể và quyền kiểm thử, trạng thái ban đầu, chuỗi hành động, định danh thao tác, kết quả API và trạng thái đã commit. Với test đồng thời, ghi thêm những mốc thực thi hữu ích mà không làm thay đổi lịch chạy quá mức.

Không ghi token, mật khẩu hoặc toàn bộ payload nhạy cảm vào báo cáo. Dữ liệu test vẫn có thể chứa bí mật kết nối hoặc thông tin truy cập môi trường.

Phân biệt các nguyên nhân:

1. **Lỗi bảo vệ nghiệp vụ:** hệ thống cho phép hiệu lực trái chính sách.
2. **Oracle sai:** test áp một quy tắc chưa có hoặc quan sát quá sớm.
3. **Fixture sai:** người gọi, trạng thái hay dữ liệu không đúng tiền điều kiện.
4. **Môi trường thiếu ổn định:** phụ thuộc ngoài, cấu hình database hoặc thời gian khiến không thể kết luận.

Không sửa test thành chấp nhận hành vi hiện tại chỉ để làm bộ test xanh. Nếu chính sách thay đổi hợp lệ, cập nhật phát biểu bất biến, kỳ vọng và các ca liên quan cùng nhau. Nếu là lỗi hệ thống, giữ ca hồi quy tái hiện trước khi sửa và chạy lại bằng chứng ở lớp có thể quan sát rủi ro.

Test không ổn định cần được xử lý bằng cách làm rõ đồng bộ, thời hạn và dữ liệu. Chạy lặp đến khi xanh hoặc bỏ qua toàn bộ nhóm đồng thời có thể che đúng loại lỗi mà nhóm đó cần phát hiện.

## 16. Danh sách kiểm tra khi hoàn thành một kịch bản

- Đã viết rõ bất biến và mục tiêu lạm dụng.
- Đã xác định chủ thể, phạm vi đối tượng, trạng thái, revision và lịch sử cần thiết.
- Đã có trường hợp đối chứng hợp lệ cho quyết định quan trọng.
- Đã thử đường API trực tiếp nếu giao diện có thể bị bỏ qua.
- Đã kiểm chứng phản hồi công khai và nguy cơ lộ thông tin.
- Đã đọc trạng thái đã commit và hiệu lực phụ liên quan.
- Đã phân biệt hiệu lực nghiệp vụ với số lần gửi request hoặc giao thông điệp.
- Đã kiểm tra phát lại, thay khóa và cạnh tranh khi chúng ảnh hưởng bất biến.
- Đã xác định điểm kết thúc quan sát cho xử lý bất đồng bộ và kết quả chưa rõ.
- Đã bảo đảm oracle độc lập đủ để phát hiện lỗi trong logic đang kiểm tra.
- Đã giữ dữ liệu, seed và bằng chứng cần thiết để tái hiện mà không làm lộ bí mật.

Một abuse scenario test có giá trị khi nó chứng minh người gọi không thể đạt mục tiêu trái chính sách bằng một đường đi cụ thể, đồng thời vẫn cho phép hành vi hợp lệ. Sức mạnh của bộ kiểm thử đến từ bất biến rõ ràng, dữ liệu đối chứng và quan sát hiệu lực thực tế trên toàn bộ chuỗi xử lý.
