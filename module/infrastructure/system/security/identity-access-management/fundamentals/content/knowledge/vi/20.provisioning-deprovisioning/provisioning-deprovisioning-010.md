# Provisioning failure

## 1. Provisioning failure là gì?

**Provisioning failure** là tình huống quy trình tạo, cập nhật hoặc thu hồi tài khoản và quyền truy cập không đưa hệ thống đích về trạng thái được yêu cầu, hoặc chưa có đủ bằng chứng để xác nhận trạng thái đó.

Trong IAM, provisioning không chỉ là tạo một dòng tài khoản. Một yêu cầu có thể gồm nhiều thay đổi: liên kết danh tính với tài khoản tại ứng dụng, đặt trạng thái hoạt động, cập nhật thuộc tính, thêm nhóm và cấp vai trò. Khi người dùng chuyển bộ phận hoặc nghỉ việc, cùng cơ chế điều phối còn phải loại bỏ những quyền không còn hợp lệ.

Vì vậy, một lời gọi API thành công chưa đủ để kết luận toàn bộ yêu cầu đã hoàn tất. Ngược lại, một lỗi timeout cũng chưa chứng minh hệ thống đích chưa thay đổi gì.

Có ba dạng cần phân biệt:

| Dạng thất bại | Ví dụ | Điều cần xác định |
|---|---|---|
| Thay đổi không được thực hiện | Connector không xác thực được với ứng dụng | Nguyên nhân chặn thao tác và quyền hạn của connector |
| Thay đổi chỉ hoàn tất một phần | Tạo được tài khoản nhưng chưa thêm được nhóm | Phần nào đã có hiệu lực, phần nào còn thiếu |
| Kết quả chưa xác định | Ứng dụng đã nhận lệnh nhưng phản hồi bị mất | Trạng thái thật tại đích trước khi quyết định gửi lại |

Bài toán cốt lõi là quản lý chênh lệch giữa **trạng thái mong muốn có thẩm quyền** và **trạng thái quan sát được**, đồng thời tránh tạo quyền vượt mức trong quá trình phục hồi.

## 2. Vì sao lỗi provisioning là vấn đề bảo mật?

Một lỗi tạo tài khoản thường lộ ra vì nhân viên mới không đăng nhập được. Lỗi thu hồi quyền có thể ít được chú ý hơn: người dùng vẫn tiếp tục sử dụng quyền cũ, trong khi hệ thống điều phối chỉ ghi nhận một job thất bại.

Tác động phụ thuộc vào hướng thay đổi:

- **Thiếu quyền cần thiết:** người dùng không làm được việc, phải nhờ cấp quyền thủ công hoặc dùng tài khoản chung.
- **Dư quyền:** người chuyển vai trò vẫn giữ nhóm cũ, tài khoản hết hạn vẫn hoạt động hoặc đặc quyền được cấp mà chưa có phê duyệt.
- **Sai người nhận quyền:** quy tắc đối sánh nhầm hai người có cùng tên hoặc tái sử dụng địa chỉ email của người đã nghỉ.
- **Thiếu khả năng kiểm chứng:** job báo thành công nhưng không có bằng chứng ứng dụng đã áp dụng thay đổi.
- **Mất dữ liệu hoặc gián đoạn:** cơ chế phục hồi xóa nhầm tài khoản vốn đã tồn tại trước job.

Nguyên tắc ít quyền nhất phải được giữ cả khi vận hành bình thường lẫn khi gặp lỗi. Không chữa một lỗi cấp tài khoản bằng cách cấp quyền quản trị rộng, bỏ kiểm tra phê duyệt hoặc vô hiệu hóa cơ chế xác thực.

Tuy nhiên, giữ nguyên mọi thứ cũng không luôn an toàn. Nếu yêu cầu thu hồi quyền đang thất bại, việc để tài khoản tiếp tục hoạt động có thể kéo dài rủi ro. Quy trình cần có biện pháp hạn chế truy cập được phê duyệt, chủ sở hữu rõ ràng và bằng chứng thực hiện.

## 3. Xác định điểm hỏng trong chuỗi xử lý

Một chuỗi provisioning điển hình có thể được mô tả như sau:

```text
Nguồn danh tính có thẩm quyền
    → Xác định thay đổi và phiên bản vòng đời
    → Tính trạng thái quyền mong muốn
    → Kiểm tra phê duyệt và chính sách
    → Lập job, đưa vào hàng đợi
    → Connector gửi thay đổi
    → Hệ thống đích áp dụng
    → Đọc lại và đối chiếu
    → Ghi nhận hoàn tất
```

Mỗi đoạn có kiểu lỗi riêng.

### Nguồn dữ liệu và sự kiện

Thông tin nhân sự có thể thiếu mã định danh ổn định, thiếu ngày hiệu lực hoặc chứa mã phòng ban không còn hợp lệ. Sự kiện có thể đến trễ, đến trùng hoặc sai thứ tự.

Nếu sự kiện “chuyển sang nhóm kinh doanh” cũ được xử lý sau sự kiện “nghỉ việc”, hệ thống có thể vô tình cấp lại quyền. Vì vậy, chỉ biết một sự kiện chưa từng được xử lý là chưa đủ; còn phải kiểm tra sự kiện đó có còn phù hợp với trạng thái vòng đời hiện tại hay không.

### Chính sách và phê duyệt

Dữ liệu hợp lệ chưa đồng nghĩa người dùng đủ điều kiện nhận quyền. Chính sách có thể yêu cầu quản lý phê duyệt, kiểm tra xung đột nhiệm vụ hoặc giới hạn thời gian đặc quyền.

Thiếu phê duyệt không phải lỗi mạng để thử lại đến khi thành công. Đây là điều kiện nghiệp vụ cần được xử lý đúng quy trình.

### Điều phối và connector

Job có thể bị kẹt trong hàng đợi, mất quyền gọi API, dùng bí mật đã hết hiệu lực hoặc gửi định dạng thuộc tính không được hệ thống đích chấp nhận.

Một connector còn có thể đọc được tài khoản nhưng không được phép quản lý nhóm. Quyền kiểm tra kết nối thành công không chứng minh connector có đủ quyền thực hiện từng loại thay đổi.

### Hệ thống đích và bước xác minh

Ứng dụng có thể thiếu giấy phép, bị giới hạn tốc độ, đang bảo trì hoặc áp dụng thay đổi bất đồng bộ. Nhóm đã cập nhật trong kho danh tính cũng chưa chắc đã được mọi thành phần thực thi quyền nhìn thấy ngay.

Cần tách biệt:

1. Yêu cầu đã được tiếp nhận.
2. Tài khoản và quyền đã được ghi nhận tại đích.
3. Trạng thái truy cập cần kiểm soát đã có hiệu lực trong phạm vi xác minh.

Không phải hệ thống nào cũng quan sát được mức thứ ba trực tiếp. Khi đó phải ghi rõ phạm vi bằng chứng, thay vì gọi mọi phản hồi thành công là “đã thu hồi toàn bộ truy cập”.

## 4. Phân loại lỗi để quyết định hành động

Không nên dùng một chính sách retry chung cho mọi lỗi.

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Tạm thời | Mất kết nối ngắn hạn, dịch vụ tạm không sẵn sàng | Retry có giới hạn, giãn cách và kiểm soát tải |
| Hạn chế công suất | Đích giới hạn tốc độ hoặc hàng đợi quá tải | Giảm đồng thời, tôn trọng thời điểm thử lại mà đích cung cấp |
| Dữ liệu hoặc ánh xạ | Thiếu thuộc tính bắt buộc, mã vai trò không tồn tại | Sửa dữ liệu hoặc cấu hình có thẩm quyền rồi xử lý lại |
| Xác thực hoặc phân quyền connector | Thông tin xác thực hết hiệu lực, connector thiếu quyền quản lý nhóm | Sửa cấu hình, bí mật hoặc phạm vi quyền; tránh retry liên tục khi chưa khắc phục |
| Chính sách hoặc phê duyệt | Yêu cầu đặc quyền chưa được duyệt | Chặn cấp quyền và chuyển đúng chủ sở hữu |
| Xung đột định danh | Tài khoản cùng tên nhưng chưa chứng minh là cùng người | Điều tra đối sánh, không tự gắn danh tính |
| Kết quả chưa xác định | Timeout sau khi gửi lệnh tạo | Đọc lại theo định danh ổn định trước khi gửi lại |
| Yêu cầu hết hiệu lực | Job cấp quyền thuộc phiên bản trước khi nghỉ việc | Đánh dấu bị thay thế, tính lại theo trạng thái hiện tại |

Thông tin lỗi từ đích chỉ là một tín hiệu. Cùng một biểu hiện “không tìm thấy nhóm” có thể do nhóm bị xóa, cấu hình sai, quyền đọc không đủ hoặc thay đổi chưa được đồng bộ. Cần đối chiếu ngữ cảnh thao tác và khả năng quan sát trước khi quyết định sửa.

Việc tự động thử lại sau khi sửa cấu hình phải có điểm kiểm soát: xác minh nguyên nhân đã được khắc phục, kiểm tra yêu cầu còn hợp lệ, rồi mới tiếp tục các job phù hợp.

## 5. Phát hiện và chẩn đoán dựa trên bằng chứng

### Theo dõi cả lỗi hiện ra lẫn lỗi im lặng

Chỉ theo dõi exception trong connector sẽ bỏ sót nhiều trường hợp: job không được tạo, sự kiện không vào hàng đợi, job đứng ở trạng thái chạy quá lâu hoặc job báo thành công sai.

Một cơ chế phát hiện đầy đủ thường kết hợp:

- Kết quả của từng thao tác và từng bước trong job.
- Tuổi của job đang chờ, đặc biệt là job thu hồi quyền.
- Thời gian từ ngày hiệu lực đến khi trạng thái đích được xác minh.
- Chênh lệch phát hiện qua đối soát định kỳ.
- Cảnh báo từ người dùng hoặc chủ ứng dụng.

“Không có lỗi được ghi nhận” chỉ có ý nghĩa khi hệ thống cũng biết những yêu cầu nào đáng lẽ phải tồn tại và phải hoàn thành.

### Bộ câu hỏi chẩn đoán

Khi tiếp nhận một sự cố, cần trả lời tuần tự:

1. Danh tính nào, hệ thống đích nào và thay đổi nào bị ảnh hưởng?
2. Nguồn có thẩm quyền hiện tại yêu cầu trạng thái gì?
3. Yêu cầu thuộc phiên bản vòng đời nào, còn hiệu lực hay đã bị thay thế?
4. Các bước nào đã hoàn tất, bước nào thất bại, bước nào chưa rõ kết quả?
5. Đích hiện đang có tài khoản, nhóm và vai trò nào?
6. Lỗi ảnh hưởng một người, một loại thao tác hay toàn connector?
7. Quyền truy cập đang thiếu hay đang dư, và mức độ nhạy cảm ra sao?
8. Có người hoặc hệ thống khác đang sửa cùng đối tượng không?

Các câu hỏi này giúp tránh hai phản ứng phổ biến nhưng nguy hiểm: chạy lại toàn bộ job mà không biết bước nào đã thành công, hoặc sửa trực tiếp tại đích mà không cập nhật cơ chế đối soát.

### Thông tin cần ghi nhận

Một bản ghi điều phối nên đủ để liên kết các lần xử lý:

```text
operationId: op-5241
subjectId: person-183
targetSystem: expense-app
lifecycleRevision: 28
desiredStateRevision: 42
action: ensure-membership
entitlementId: expense-submit
state: OUTCOME_UNKNOWN
attempt: 2
correlationId: trace-9c31
nextAction: read-target-state
```

Đây là ví dụ mô hình vận hành, không phải schema bắt buộc của một sản phẩm.

Không ghi mật khẩu, access token, refresh token, khóa bí mật hay toàn bộ payload chứa dữ liệu cá nhân vào log. Log và bằng chứng readback cũng cần kiểm soát truy cập, thời gian lưu giữ và mức chi tiết phù hợp. Chỉ lưu các định danh, sai khác và thông tin cần thiết cho điều tra.

## 6. Timeout, idempotency và nguy cơ tạo trùng

Giả sử connector gửi lệnh tạo tài khoản. Ứng dụng đã tạo xong, nhưng phản hồi bị mất. Connector nhận timeout và gửi lại lệnh tạo mà không kiểm tra.

Nếu đích không hỗ trợ cơ chế chống lặp phù hợp, hệ thống có thể tạo hai tài khoản. Tệ hơn, connector có thể gắn nhầm vào một tài khoản cùng tên rồi cấp quyền cho sai đối tượng.

### Timeout phải được xem là kết quả chưa xác định

Sau timeout, cách suy luận an toàn là:

> Chưa biết thao tác đã có hiệu lực hay chưa; cần xác minh trạng thái trước khi quyết định hành động tiếp theo.

Đọc lại nên dựa trên định danh liên kết ổn định giữa danh tính nguồn và tài khoản đích. Email và tên hiển thị có thể thay đổi, tái sử dụng hoặc không duy nhất, nên không được mặc nhiên dùng làm bằng chứng rằng hai tài khoản thuộc cùng một người.

Nếu không quan sát được đích, giữ trạng thái chưa xác định và chuyển sang nhánh xử lý phù hợp. Không biến sự thiếu bằng chứng thành kết luận “chưa tạo”.

### Thiết kế thao tác có thể thực hiện lại an toàn

Idempotency nghĩa là xử lý lặp cùng một ý định không làm phát sinh hiệu ứng ngoài ý định đó. Ví dụ, thao tác “bảo đảm tài khoản là thành viên nhóm A” có thể kiểm tra trạng thái và giữ nguyên nếu quan hệ đã tồn tại.

Các biện pháp thường dùng gồm:

- Lưu operation ID bền vững trước khi gửi lệnh.
- Dùng cùng khóa chống lặp cho các lần thử lại của cùng thao tác nếu đích hỗ trợ.
- Tách định danh thao tác khỏi số lần thử.
- Đọc lại trạng thái đích và xác minh liên kết danh tính.
- Dùng cơ chế kiểm tra phiên bản hoặc tiền điều kiện nếu đích hỗ trợ.
- Ghi nhận từng bước đã hoàn tất để không lặp lại tác dụng phụ không cần thiết.

Không phải API nào cũng hỗ trợ idempotency key, và việc gửi cùng một chuỗi khóa không tự tạo ra bảo đảm nếu đích không xử lý nó. Cơ chế chống lặp còn có thể có thời hạn lưu giữ; quy trình phục hồi cần biết giới hạn thực tế của đích.

Một thay đổi mới về ý định, chẳng hạn đổi sang vai trò khác, cần được phân biệt với retry của ý định cũ.

## 7. Retry có kiểm soát và quản lý trạng thái job

### Không retry vô hạn

Retry hữu ích với lỗi tạm thời nhưng có thể khiến sự cố nặng hơn nếu mọi worker đồng loạt gửi lại yêu cầu. Một chính sách phù hợp cần xác định:

- Loại lỗi nào được retry tự động.
- Số lần thử hoặc tổng thời gian cho phép.
- Khoảng giãn cách tăng dần và giới hạn tối đa.
- Độ ngẫu nhiên của thời điểm thử lại để tránh dồn tải.
- Giới hạn số thao tác đồng thời theo hệ thống đích.
- Điều kiện dừng, cảnh báo và chuyển chủ sở hữu.

Một công thức minh họa cho khoảng chờ tăng dần là:

```text
giới_hạn_lần_này = min(khoảng_chờ_tối_đa, khoảng_chờ_gốc × 2^số_lần_lỗi)
khoảng_chờ = giá_trị_ngẫu_nhiên_trong_khoảng(0, giới_hạn_lần_này)
```

Các tham số phải được chọn theo năng lực đích, yêu cầu vận hành và mức độ rủi ro; công thức không thay thế đánh giá đó. Nếu đích cung cấp hướng dẫn thử lại, cần đưa hướng dẫn ấy vào quyết định lập lịch.

Khi lỗi xác thực ảnh hưởng toàn connector hoặc đích đang gián đoạn diện rộng, có thể tạm dừng gửi thêm thao tác theo cơ chế ngắt mạch. Các yêu cầu vẫn phải được theo dõi và cảnh báo; tạm dừng gửi không đồng nghĩa xóa lỗi khỏi hệ thống.

### Trạng thái cần thể hiện thực tế

Một mô hình trạng thái minh họa:

```text
PENDING → RUNNING → VERIFYING → COMPLETED
              │          │
              │          └→ RETRY_WAIT hoặc MANUAL_REQUIRED
              ├→ OUTCOME_UNKNOWN → VERIFYING
              ├→ RETRY_WAIT → RUNNING
              └→ BLOCKED

Bất kỳ job chưa hoàn tất nào:
    nếu ý định không còn hiệu lực → SUPERSEDED
```

Ý nghĩa của các trạng thái phải rõ:

- `COMPLETED`: hậu điều kiện đã được xác minh trong phạm vi đã định.
- `OUTCOME_UNKNOWN`: chưa có đủ bằng chứng về hiệu ứng của thao tác.
- `RETRY_WAIT`: đã có quyết định thử lại và lịch thực hiện tiếp theo.
- `BLOCKED`: cần sửa điều kiện dữ liệu, chính sách hoặc cấu hình.
- `MANUAL_REQUIRED`: không thể tự động kết luận hoặc phục hồi an toàn.
- `SUPERSEDED`: job cũ bị thay thế bởi ý định mới, không được tiếp tục cấp quyền theo job này.

Không gom mọi trường hợp vào một trạng thái `FAILED` rồi để người vận hành đoán bước kế tiếp. Mỗi job chưa hoàn tất cần có lý do, hành động tiếp theo và chủ sở hữu khi đã vượt khả năng tự động xử lý.

### Tránh thao tác từ worker cũ

Nếu worker mất kết nối, job có thể được giao lại trong khi worker cũ vẫn tiếp tục chạy. Khóa ở hệ thống điều phối giúp giảm xung đột nhưng không tự ngăn một yêu cầu đã gửi tới đích.

Cần phối hợp lease hoặc ownership của job với kiểm tra phiên bản, idempotency và tiền điều kiện tại đích khi có thể. Trước mỗi thay đổi cấp quyền, kiểm tra lại ý định còn hiệu lực. Nếu đích không hỗ trợ bảo vệ cập nhật đồng thời, phải thừa nhận khoảng rủi ro và dùng điều phối tuần tự cùng đối soát để kiểm soát.

## 8. Lỗi một phần: tiếp tục hay bù trừ?

Provisioning nhiều bước thường đi qua các hệ thống độc lập, nên không thể mặc định tất cả đều nằm trong một giao dịch nguyên tử.

Ví dụ:

```text
Bước 1: Tạo tài khoản                    → thành công
Bước 2: Gán giấy phép                    → thành công
Bước 3: Thêm nhóm expense-submit         → thất bại
Bước 4: Đọc lại quyền và kết thúc         → chưa thực hiện
```

Có hai hướng phục hồi chính.

**Tiếp tục tiến về trạng thái mong muốn:** giữ những thay đổi đã thành công và xử lý lại phần còn thiếu. Hướng này phù hợp khi ý định vẫn hợp lệ, trạng thái trung gian chấp nhận được và từng bước có thể được kiểm chứng.

**Bù trừ có kiểm soát:** thực hiện hành động mới để giảm hoặc đảo tác động đã tạo ra. Chẳng hạn, vô hiệu hóa tài khoản mới tạo nếu quy trình yêu cầu tài khoản chỉ được hoạt động khi đã hoàn tất phê duyệt và cấu hình quyền.

Bù trừ không có nghĩa là “rollback chắc chắn”. Bản thân thao tác bù trừ cũng có thể thất bại, cần được theo dõi và xác minh.

### Không đảo thay đổi vượt ownership

Trước khi bù trừ phải biết:

- Tài khoản hoặc quyền có tồn tại trước job hay không.
- Job này thực sự đã tạo hoặc thay đổi phần nào.
- Có thay đổi hợp lệ khác diễn ra sau đó không.
- Việc xóa có ảnh hưởng dữ liệu nghiệp vụ hoặc chính sách lưu giữ không.
- Biện pháp giảm quyền nào được cho phép trong tình huống đó.

Không xóa cả tài khoản chỉ vì bước thêm nhóm thất bại nếu tài khoản đó đã tồn tại từ trước. Không xóa thành viên nhóm chỉ dựa trên giả định job vừa thêm nó, vì quyền có thể được cấp bởi một luồng hợp lệ khác.

Với thao tác thu hồi quyền, hoàn tác về trạng thái có nhiều quyền hơn thường làm tăng rủi ro. Nếu thu hồi nhóm A thành công nhưng nhóm B thất bại, không nên tự thêm lại nhóm A để đạt một trạng thái “đồng nhất”. Cần tiếp tục xử lý phần quyền còn sót và áp dụng biện pháp hạn chế bổ sung theo thẩm quyền.

## 9. Deprovisioning failure cần ưu tiên riêng

Dù thường cùng dùng connector và hàng đợi, cấp quyền thất bại và thu hồi thất bại có hậu quả khác nhau.

Khi một người nghỉ việc, việc vô hiệu hóa tài khoản tại nhà cung cấp danh tính có thể chặn một số lần đăng nhập mới qua SSO. Điều đó không tự chứng minh mọi truy cập vào ứng dụng đích đã dừng. Ứng dụng có thể còn phiên đang hoạt động, đăng nhập cục bộ, khóa API hoặc cơ chế xác thực riêng.

Một yêu cầu thu hồi cần xác định các đường truy cập liên quan, tùy kiến trúc thực tế:

| Thành phần | Bằng chứng cần tìm |
|---|---|
| Tài khoản tại đích | Trạng thái hoạt động hoặc vô hiệu hóa đúng danh tính |
| Nhóm và vai trò | Những quyền không còn hợp lệ đã được loại bỏ |
| Phiên ứng dụng | Cơ chế kết thúc hoặc hết hiệu lực phiên đã được thực hiện trong phạm vi hỗ trợ |
| Token và khóa thuộc phạm vi quản lý | Quyết định thu hồi hoặc hết hiệu lực đã được áp dụng và xác minh |
| Phương thức đăng nhập khác | Đường truy cập không qua SSO đã được kiểm tra theo chính sách |

Không phải mọi loại token hoặc phiên đều thu hồi tức thì. Với phần không thể thu hồi trực tiếp, cần ghi nhận thời hạn còn hiệu lực, biện pháp hạn chế khả dụng và phần rủi ro còn lại.

Trình tự xử lý sự cố có thể gồm: đánh giá đặc quyền và thời điểm hiệu lực; thực hiện biện pháp hạn chế được phép; ưu tiên sửa connector hoặc thao tác tại đích; kiểm tra lại; lưu bằng chứng và đóng sự cố khi đạt điều kiện.

Hành động thủ công phải được ghi vào hệ thống theo dõi và được đối soát sau đó. Nếu chỉ vô hiệu hóa tại đích mà quy trình đồng bộ vẫn coi trạng thái mong muốn là “active”, lượt đồng bộ kế tiếp có thể bật tài khoản trở lại.

## 10. Đối soát để phát hiện chênh lệch còn sót

Retry xử lý một yêu cầu đã biết. **Reconciliation**, hay đối soát, tìm chênh lệch giữa trạng thái mong muốn và trạng thái quan sát được, kể cả khi không có job lỗi nào được ghi nhận.

Những chênh lệch thường gặp gồm:

- Tài khoản cần có nhưng chưa được tạo.
- Tài khoản đã tạo trùng hoặc chưa liên kết được với danh tính nguồn.
- Người dùng còn vai trò từ bộ phận cũ.
- Tài khoản đáng lẽ bị vô hiệu hóa nhưng vẫn hoạt động.
- Quyền được cấp trực tiếp ngoài quy trình.
- Job báo thành công nhưng thay đổi chưa tồn tại tại đích.

Đối soát an toàn cần một nguồn xác định trạng thái mong muốn có thẩm quyền. Không được dùng bản snapshot cũ để tự động ghi đè những thay đổi hợp lệ mới hơn.

Một lượt đối soát nên:

1. Xác định thời điểm, phiên bản và phạm vi dữ liệu nguồn.
2. Thu thập trạng thái đích với độ đầy đủ và độ trễ đã biết.
3. Đối sánh theo liên kết danh tính đáng tin cậy.
4. Phân loại chênh lệch và đánh giá quyền sở hữu thay đổi.
5. Tự sửa các trường hợp nằm trong chính sách đã phê duyệt.
6. Chuyển các trường hợp mơ hồ sang điều tra thủ công.
7. Đọc lại để xác minh kết quả sửa.

Nếu quyền đọc tại đích bị giới hạn, danh sách trả về thiếu một nhóm không đủ chứng minh người dùng không thuộc nhóm ấy. Một nguồn quan sát thiếu dữ liệu không nên kích hoạt hàng loạt lệnh tạo mới hoặc xóa quyền.

Ngoại lệ hợp lệ, chẳng hạn đặc quyền khẩn cấp có thời hạn, cần được biểu diễn trong mô hình quyết định hoặc quy trình ngoại lệ. Không bỏ qua chênh lệch vô thời hạn chỉ vì có chú thích “đã xử lý thủ công”.

## 11. Ví dụ xuyên suốt: chuyển bộ phận rồi nghỉ việc

Lan đang có tài khoản ở ứng dụng quản lý chi phí. Khi Lan chuyển từ nhóm hỗ trợ sang nhóm bán hàng, yêu cầu mới là bỏ `support-expense` và thêm `sales-expense`.

| Thời điểm | Sự kiện hoặc kết quả | Quyết định cần thực hiện |
|---|---|---|
| T1 | Nhận thay đổi bộ phận, phiên bản vòng đời 51 | Tính trạng thái quyền và tạo các thao tác được phép |
| T2 | Bỏ `support-expense` thành công | Ghi nhận bước hoàn tất, không thực hiện lại việc không cần thiết |
| T3 | Thêm `sales-expense` bị timeout | Đánh dấu kết quả chưa xác định và đọc lại |
| T4 | Trước khi xác minh xong, nhận thông tin nghỉ việc phiên bản 52 | Chặn tiếp tục ý định cấp quyền của phiên bản 51, lập yêu cầu thu hồi |
| T5 | Đọc lại thấy `sales-expense` đã được thêm ở T3 | Thu hồi theo phiên bản 52; không gọi job cũ là “chưa làm gì” |
| T6 | Vô hiệu hóa tài khoản và kiểm tra các đường truy cập liên quan | Xác minh hậu điều kiện, ghi rõ phần nào đã kiểm tra |

Ví dụ cho thấy ba yêu cầu độc lập:

**Chống lặp:** không thêm quyền nhiều lần chỉ vì mất phản hồi.

**Đúng thứ tự vòng đời:** job cũ không được tiếp tục cấp quyền sau khi ý định mới đã thay thế nó.

**Xác minh và sửa trạng thái thật:** đánh dấu job cũ là `SUPERSEDED` không tự xóa hiệu ứng đã xảy ra ở đích. Yêu cầu thu hồi vẫn phải xử lý quyền đã tồn tại.

Một bộ điều phối đơn giản về mặt ý tưởng có thể đi theo logic sau:

```text
xử_lý(job):
    kiểm_tra_ownership(job)
    ý_định = đọc_trạng_thái_mong_muốn_hiện_tại(job.subject)

    nếu job không còn phù hợp với ý_định:
        đánh_dấu_SUPERSEDED(job)
        bảo_đảm_có_yêu_cầu_đối_soát_theo_ý_định_hiện_tại
        kết_thúc

    quan_sát = đọc_trạng_thái_đích(job.subject)

    nếu quan_sát chưa đủ để kết_luận:
        ghi_OUTCOME_UNKNOWN_và_hành_động_tiếp_theo(job)
        kết_thúc

    nếu hậu_điều_kiện đã đúng:
        ghi_COMPLETED_kèm_bằng_chứng(job)
        kết_thúc

    xác_định_thay_đổi_còn_thiếu
    kiểm_tra_lại_phiên_bản_và_thẩm_quyền_trước_khi_ghi
    thực_hiện_thao_tác_có_cơ_chế_chống_lặp_phù_hợp
    đọc_lại_và_phân_loại_kết_quả
    cập_nhật_trạng_thái_hoặc_chuyển_chủ_sở_hữu
```

Đây là mã giả mô tả luồng quyết định, chưa phải một thuật toán bảo đảm nguyên tử trên nhiều hệ thống. Trong triển khai thực tế, sự thay đổi ý định và yêu cầu đang bay tới đích có thể giao nhau; kiểm tra phiên bản, điều phối đồng thời và đối soát sau thao tác vẫn cần thiết.

## 12. Vận hành, trách nhiệm và tiêu chí đóng sự cố

### Phân định trách nhiệm

Một sự cố có thể cần phối hợp giữa đội IAM, người sở hữu nguồn nhân sự và chủ ứng dụng.

| Vấn đề | Chủ sở hữu thường cần tham gia |
|---|---|
| Thuộc tính nhân sự sai hoặc thiếu | Đội quản lý nguồn danh tính có thẩm quyền |
| Ánh xạ thuộc tính, hàng đợi, logic connector | Đội IAM hoặc đội tích hợp |
| API đích, giấy phép, khả năng thu hồi phiên | Chủ ứng dụng và đội vận hành đích |
| Phê duyệt, xung đột quyền, ngoại lệ đặc quyền | Chủ quyền hoặc người phê duyệt theo chính sách |
| Dấu hiệu truy cập trái phép trong thời gian lỗi | Đội xử lý sự cố bảo mật |

Tên đội có thể khác nhau giữa các tổ chức, nhưng mỗi job bị chặn cần có người chịu trách nhiệm xử lý và đường chuyển cấp rõ ràng.

### Chỉ số cần theo dõi

Tỷ lệ job thành công chung có thể che khuất một số ít yêu cầu thu hồi đặc quyền đang thất bại. Nên phân tách theo hành động, ứng dụng và mức độ rủi ro:

- Thời gian từ ngày hiệu lực đến lúc cấp hoặc thu hồi được xác minh.
- Tuổi của yêu cầu thu hồi lâu nhất chưa hoàn tất.
- Số job đang ở trạng thái chưa xác định hoặc cần xử lý thủ công.
- Tỷ lệ lỗi theo connector và nhóm nguyên nhân.
- Số chênh lệch phát hiện qua đối soát.
- Số trường hợp quyền bị cấp lại bởi sự kiện hoặc job cũ.
- Khối lượng retry và mức sử dụng giới hạn công suất tại đích.

Ngưỡng cảnh báo phải gắn với đặc quyền, yêu cầu nghiệp vụ và khả năng phục hồi của tổ chức. Không coi một mốc thời gian chung cho mọi ứng dụng là bảo đảm phù hợp.

### Đóng sự cố dựa trên hậu điều kiện

Chỉ đóng sự cố sau khi đã xác nhận:

1. Ý định hiện tại còn hiệu lực và được nguồn có thẩm quyền xác nhận.
2. Liên kết danh tính nguồn với tài khoản đích là đúng.
3. Các thay đổi trong phạm vi đã được áp dụng và đọc lại.
4. Những đường truy cập cần kiểm soát đã được xử lý, hoặc phần chưa xử lý có chủ sở hữu và quyết định chấp nhận rõ ràng theo chính sách.
5. Job cũ, retry đang chờ và thay đổi thủ công đã được xử lý để tránh tái cấp quyền.
6. Bằng chứng cùng nguyên nhân và hành động khắc phục đã được ghi nhận.

Nếu còn rủi ro chưa được chấp nhận hoặc hậu điều kiện chưa đạt, không đánh dấu yêu cầu thu hồi là hoàn tất chỉ vì đã gửi email cho chủ ứng dụng.

## 13. Các sai lầm cần tránh

**Thấy timeout thì tạo lại ngay:** có thể tạo trùng hoặc cấp lặp. Cần xử lý kết quả chưa xác định và kiểm tra liên kết danh tính.

**Dùng email làm khóa đối sánh duy nhất:** có thể gắn nhầm tài khoản khi đổi tên hoặc tái sử dụng địa chỉ. Cần định danh ổn định và cơ chế liên kết đáng tin cậy.

**Retry mọi lỗi với cùng tần suất:** làm quá tải đích, không sửa được lỗi dữ liệu hoặc phê duyệt. Cần phân loại và giới hạn retry.

**Coi “đã gửi lệnh” là hoàn tất:** bỏ qua thay đổi bất đồng bộ và lỗi một phần. Cần xác minh hậu điều kiện ở mức hệ thống quan sát được.

**Xóa tài khoản để làm lại cho nhanh:** có thể mất dữ liệu và vượt ownership. Cần biết tài khoản có từ trước và tác động của hành động bù trừ.

**Khôi phục quyền đã thu hồi vì một bước khác thất bại:** làm tăng quyền trong lúc xử lý deprovisioning failure. Cần tiếp tục giảm quyền theo trạng thái mong muốn hiện tại.

**Chỉ khóa SSO rồi kết luận mất mọi truy cập:** bỏ sót phiên, token hoặc đăng nhập riêng. Cần xét các đường truy cập thực tế.

**Để thao tác thủ công nằm ngoài đối soát:** lượt đồng bộ sau có thể khôi phục trạng thái sai. Cần phản ánh quyết định vào nguồn hoặc ngoại lệ có kiểm soát.

**Phát lại hàng đợi lỗi mà không kiểm tra phiên bản:** có thể cấp quyền theo một quyết định đã hết hiệu lực. Cần tính lại theo vòng đời hiện tại trước khi ghi.

Xử lý provisioning failure hiệu quả đòi hỏi biết điều gì đã xảy ra, điều gì vẫn chưa chắc chắn và trạng thái nào hiện được phép tồn tại. Mỗi lần phục hồi phải thu hẹp chênh lệch đó bằng thao tác có kiểm soát, xác minh được và phù hợp với nguyên tắc ít quyền nhất.
