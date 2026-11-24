# Emergency action definition — Định nghĩa hành động khẩn cấp trong nghiệp vụ

## 1. Hành động khẩn cấp là gì?

Trong chương **Emergency Actions**, một hành động khẩn cấp là một **lệnh nghiệp vụ đã được định nghĩa và cấp quyền theo chính sách riêng**, được sử dụng khi có tình huống cần can thiệp nhanh để hạn chế thiệt hại hoặc duy trì một chức năng thiết yếu. Lệnh này có thể rút ngắn hoặc thay thế một bước trong luồng thông thường, nhưng vẫn phải có chủ thể, phạm vi, điều kiện thực hiện, hiệu ứng và dấu vết rõ ràng.

Ví dụ, khi phát hiện hệ thống đang phát sinh lệnh xuất hàng trùng, người trực sự cố có thể được phép tạm dừng tiếp nhận lệnh xuất mới tại một kho cụ thể mà không chờ đủ hai người phê duyệt trước. Chính sách có thể chuyển bước xác nhận thứ hai sang hậu kiểm, trong khi vẫn bắt buộc xác thực người thao tác, kiểm tra đúng kho, ghi lý do và lưu hiệu ứng duy nhất.

Không thể định nghĩa tính khẩn cấp chỉ bằng một cờ `emergency=true`, tên vai trò `ADMIN` hoặc một ô nhập lý do. Nếu những dữ liệu đó làm vô hiệu hóa mọi kiểm tra, hệ thống đã tạo ra một đường bỏ qua logic nghiệp vụ mà người dùng có thể chủ động khai thác.

Bài học tập trung vào định nghĩa có thể thực thi của hành động khẩn cấp, trong phạm vi bảo vệ business invariants, state machine, quyền theo đối tượng, transaction, idempotency và kiểm thử tấn công logic. Các chính sách và thời hạn trong ví dụ là giả định phục vụ thiết kế phần mềm.

Sau bài học, người học có thể:

- Phân biệt hành động khẩn cấp với thao tác quản trị và cơ chế cấp quyền khẩn cấp.
- Mô tả chính xác điều kiện kích hoạt, phạm vi và ngoại lệ được phép.
- Xác định các bất biến vẫn phải giữ khi có ngoại lệ luồng duyệt.
- Tách thời hạn quyền khẩn cấp khỏi thời gian tồn tại của hiệu ứng nghiệp vụ.
- Thiết kế vòng đời, thực thi nguyên tử, chống trùng và hậu kiểm.
- Xây dựng tình huống kiểm thử nhằm ngăn việc biến ngoại lệ thành quyền thường trực.

## 2. Phân biệt những khái niệm dễ bị trộn lẫn

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| Thao tác quản trị thông thường | Thực hiện công việc theo quyền và quy trình thường lệ | Cập nhật cấu hình trong một thay đổi đã được duyệt |
| Hành động khẩn cấp | Tạo một hiệu ứng nghiệp vụ cụ thể theo chính sách sự cố | Tạm dừng lệnh xuất mới cho kho đang bị phát sinh lệnh trùng |
| Cấp quyền khẩn cấp, thường gọi là break-glass access | Cấp một quyền hạn chế để xử lý sự cố khi điều kiện đặc biệt thỏa mãn | Cho người trực quyền dùng lệnh tạm dừng trong một cửa sổ ngắn |
| Công tắc vận hành | Cơ chế kỹ thuật bật hoặc tắt một hành vi | Một gate ngăn tiếp nhận lệnh xuất mới |
| Quy trình xử lý sự cố | Điều phối phát hiện, can thiệp, phục hồi và đánh giá | Xác nhận sự cố, dừng phát sinh, xử lý lệnh trùng, mở lại có kiểm soát |

Một hành động khẩn cấp có thể dùng quyền trực sẵn có mà không cần cấp thêm quyền break-glass. Ngược lại, được cấp quyền khẩn cấp không có nghĩa được thực hiện mọi hành động quản trị. Công tắc vận hành chỉ là một cách hiện thực hiệu ứng; nó chưa mô tả ai được bật, khi nào được bật hay khi nào được mở lại.

Những phân biệt này giúp tránh một thiết kế quá rộng như “khi incident đang mở thì mọi kiểm tra đều được bỏ qua”. Tình trạng sự cố chỉ là một dữ kiện trong chính sách, không tự trở thành nguồn quyền vô hạn.

## 3. Một định nghĩa đầy đủ cần những thành phần nào?

Một định nghĩa hữu ích phải đủ rõ để backend quyết định cho phép hoặc từ chối và để người kiểm tra sau này giải thích được quyết định đó.

| Thành phần | Nội dung phải xác định |
| --- | --- |
| Định danh và phiên bản | Hành động nào, áp dụng phiên bản chính sách nào |
| Mục đích | Thiệt hại hoặc rủi ro nào cần chặn, kết quả mong muốn là gì |
| Điều kiện kích hoạt | Tình trạng sự cố, loại đối tượng và tín hiệu nào đủ điều kiện |
| Chủ thể được phép | Ai có quyền kích hoạt hoặc sử dụng; có cần mức xác thực bổ sung không |
| Phạm vi đối tượng | Tenant, kho, dự án, tài nguyên hoặc tập đối tượng cụ thể |
| Tiền điều kiện | Trạng thái và dữ liệu nào phải còn đúng tại điểm thực thi |
| Ngoại lệ cho phép | Chính xác kiểm tra hoặc bước nào được thay thế hay trì hoãn |
| Bất biến được bảo vệ | Những điều kiện không được vi phạm khi tạo hiệu ứng |
| Hiệu ứng | Thay đổi dữ liệu hoặc chuyển trạng thái cụ thể, kể cả giới hạn của nó |
| Thời hạn quyền | Từ lúc nào đến lúc nào người được phép có thể tạo hành động mới |
| Trùng lặp và tranh chấp | Cách xử lý retry, nhiều người cùng thao tác và các lệnh đối nghịch |
| Audit và hậu kiểm | Bằng chứng nào phải lưu, ai đánh giá và xử lý kết quả thế nào |
| Khôi phục | Điều kiện và thẩm quyền thực hiện hành động tiếp theo hoặc mở lại |

Không chỉ viết “có thể bỏ qua phê duyệt khi khẩn cấp”. Cần nói rõ, ví dụ: “người trực đủ điều kiện có thể tạm dừng tiếp nhận lệnh xuất mới tại một kho bị ảnh hưởng; chỉ bước phê duyệt thứ hai trước thực thi được chuyển sang hậu kiểm; không cấp quyền hủy các lệnh đã thực hiện hoặc sửa số liệu tồn kho”.

Lý do và incident ID giúp truy nguyên nhưng không tự chứng minh người gọi có quyền. Backend phải xác minh incident có tồn tại, thuộc phạm vi phù hợp, đang ở trạng thái được chính sách công nhận và có liên hệ hợp lệ với đối tượng cần can thiệp.

## 4. Ví dụ định nghĩa: tạm dừng lệnh xuất mới tại một kho

### 4.1. Bối cảnh và mục tiêu

Giả sử tenant T1 có kho W1. Một sự cố I được xác nhận đang tạo lệnh xuất trùng. Mục tiêu can thiệp là **ngăn các quyết định xuất mới** cho W1 trong hệ thống điều phối, để đội xử lý có thể điều tra và ngăn thiệt hại tăng thêm.

Hành động được định danh là `PAUSE_NEW_FULFILLMENT`. Nó không có nghĩa đã thu hồi các kiện hàng đang trên đường, hủy mọi lệnh cũ hoặc sửa lại số hàng đã xuất. Các kết quả đó cần hành động khác và bằng chứng tương ứng.

### 4.2. Hợp đồng minh họa

```text
Policy: emergency.pause-new-fulfillment
Version: 1
Action: PAUSE_NEW_FULFILLMENT

Trigger:
  Incident được xác minh thuộc loại phát sinh lệnh xuất trùng.
  Incident còn cho phép can thiệp và liên quan đúng kho.

Actor:
  Người trực được cấp quyền containment cho tenant và kho đó.
  Phiên xác thực đạt mức yêu cầu của chính sách.

Scope:
  Một tenant và một warehouseId cụ thể.

Allowed exception:
  Có thể trì hoãn phê duyệt thứ hai sang bước hậu kiểm.

Protected conditions:
  Không bỏ xác thực, kiểm tra phạm vi, tính duy nhất hiệu ứng hoặc audit bắt buộc.
  Không sửa tồn kho hoặc hủy bằng chứng nghiệp vụ để thực hiện lệnh dừng.

Effect:
  Đặt gate tiếp nhận quyết định xuất mới của kho sang PAUSED.

Authority lifetime:
  Quyền can thiệp được cấp tối đa 10 phút trong ví dụ.

Effect lifetime:
  Gate giữ trạng thái PAUSED cho đến khi một lệnh RESUME hợp lệ được thực hiện.

Review:
  Tạo nghĩa vụ hậu kiểm và tham chiếu hiệu ứng ngay trong lần thực thi.
```

Đây là đặc tả minh họa, không phải cú pháp cấu hình của một thư viện. Định nghĩa thực tế còn phải nêu cách xác minh đối tượng, trạng thái cho phép và mức xác thực cụ thể của hệ thống.

### 4.3. Quyền hết hạn không đồng nghĩa tự mở lại nghiệp vụ

Quyền 10 phút giới hạn cửa sổ tạo **hành động mới**. Khi cửa sổ đó kết thúc, người trực không thể tiếp tục dùng grant cũ để dừng thêm kho hoặc thực hiện lệnh khác.

Hiệu ứng đã tạo có vòng đời riêng. Nếu gate tự mở lại chỉ vì grant hết hạn trong khi sự cố chưa được xử lý, hệ thống có thể tiếp tục phát sinh lệnh trùng. Vì vậy, ví dụ yêu cầu một lệnh `RESUME_NEW_FULFILLMENT` độc lập, có tiền điều kiện và quyền riêng.

Một hệ thống có thể thiết kế một biện pháp tạm thời tự hết hiệu lực nếu nghiệp vụ yêu cầu. Khi đó phải đặc tả rõ hiệu ứng tự phục hồi, điều kiện an toàn và cách xử lý khi sự cố chưa kết thúc. Không suy ra hành vi đó từ TTL của quyền.

## 5. Ngoại lệ có giới hạn và các bất biến được giữ

### 5.1. Ngoại lệ phải được gọi tên

Trong ví dụ, ngoại lệ là **trì hoãn phê duyệt thứ hai**. Điều này khác với các hành vi sau:

- Tự khai quyền người trực hoặc tenant trong body.
- Chọn một kho không liên quan sự cố.
- Dùng cùng quyền để đổi giá, cấp vai trò hoặc sửa tồn kho.
- Bỏ audit, xóa lịch sử hoặc biến request trùng thành hiệu ứng mới.
- Đổi incident hoặc phạm vi sau khi nhận phê duyệt mà không kiểm tra lại.

Chính sách nên biểu diễn ngoại lệ theo tập giá trị được công bố, chẳng hạn `DEFER_SECOND_APPROVAL`. Không nhận một danh sách tự do như `skipChecks=["authorization", "audit"]` từ client.

### 5.2. Các bất biến của ví dụ

```text
Mỗi hành động có actor thật, incident, tenant và kho có thẩm quyền.
Chỉ được áp dụng hành động có trong định nghĩa và phạm vi grant.
Không tiếp nhận quyết định xuất mới sau khi gate PAUSED có hiệu lực.
Không tạo hai hiệu ứng cùng một ý định nghiệp vụ do retry.
Mọi thay đổi gate có thể truy về một bản ghi quyết định đã commit.
Hết hạn hoặc thu hồi quyền không bị hiểu thành lệnh mở lại gate.
```

Những bất biến về dữ liệu miền khác cũng vẫn áp dụng khi hành động tác động đến miền đó: bảo toàn lượng, không tiêu thụ vượt phần được phép, nội dung đã duyệt khớp nội dung thực hiện và quyền theo đối tượng. Nếu một nghiệp vụ điều chỉnh cần thay đổi số liệu, phải có mô hình điều chỉnh có dấu vết; không dùng nhãn khẩn cấp để ghi tùy ý.

### 5.3. Quyền khẩn cấp là quyền riêng, không phải hợp quyền tùy ý

Người trực có thể không có quyền thao tác thông thường mà hành động khẩn cấp thay thế. Backend phải kiểm tra **quyền khẩn cấp được cấp rõ ràng** cho hành động đó, thay vì yêu cầu ngầm cả hai cơ chế hoặc bỏ toàn bộ kiểm tra.

Ở chiều ngược lại, có vai trò quản trị rộng không tự chứng minh có quyền sử dụng ngoại lệ khẩn cấp. Một quyền dừng kho cũng không tự bao gồm quyền mở lại kho. Phạm vi, giới hạn và căn cứ của từng lệnh cần được xác định riêng.

