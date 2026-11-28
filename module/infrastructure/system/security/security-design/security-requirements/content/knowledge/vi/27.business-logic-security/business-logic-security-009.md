# Double spending defense — Đặc tả yêu cầu chống chi tiêu trùng

## 1. Double spending là rủi ro nghiệp vụ gì?

**Double spending** là việc cùng một giá trị hoặc quyền sử dụng hữu hạn bị dùng nhiều hơn số lần hoặc số lượng được phép. Rủi ro này xuất hiện trong ví nội bộ, điểm thưởng, số dư trả trước, quyền sử dụng mã ưu đãi hoặc các tài nguyên nghiệp vụ có thể bị tiêu thụ.

Ví dụ, một ví có 100 đơn vị khả dụng. Hai yêu cầu khác nhau, mỗi yêu cầu chi 80 đơn vị, cùng được xử lý dựa trên ảnh chụp số dư 100. Nếu cả hai được chấp nhận, hệ thống đã cho phép chi 160 đơn vị từ nguồn chỉ có 100.

Double spending có thể phát sinh do yêu cầu đồng thời, gửi lại sau mất phản hồi, tác vụ nền chạy lại, thông điệp trùng hoặc quy trình phục hồi không đối soát với kết quả đã xảy ra. Chủ thể có tài khoản hợp lệ vẫn có thể gây ra hoặc lợi dụng các tình huống đó.

Trong đặc tả yêu cầu bảo mật, mục tiêu là chỉ rõ:

> Giá trị nào được bảo vệ, ai có quyền sử dụng, giới hạn tiêu thụ là gì, điểm nào chấp nhận chi tiêu và bằng chứng nào chứng minh không có hiệu ứng vượt quyền hoặc vượt nguồn lực.

Bài học tập trung vào chuyển mô hình đe dọa thành yêu cầu đo được, quyết định kiến trúc và tiêu chí kiểm thử. Các ví dụ dùng đơn vị giá trị nguyên của một hệ thống giả định; chúng không phải hướng dẫn vận hành một sản phẩm tài chính cụ thể.

## 2. Phân biệt các vấn đề thường bị gộp chung

| Vấn đề | Ví dụ | Kiểm soát cần có |
|---|---|---|
| Một lệnh bị gửi lại | Client không nhận được phản hồi nên gửi lại thanh toán đơn A. | Idempotency và biên nhận kết quả nhất quán với hiệu ứng. |
| Hai lệnh khác nhau cạnh tranh cùng nguồn | Đơn A và đơn B cùng chi 80 từ ví có 100. | Kiểm tra nguồn lực và cam kết tiêu thụ theo cơ chế nguyên tử phù hợp. |
| Cùng nghĩa vụ nghiệp vụ dùng khóa mới | Client đổi idempotency key nhưng vẫn thanh toán lại đơn A. | Ràng buộc duy nhất theo định danh nghiệp vụ có thẩm quyền. |
| Thông điệp bị giao lại | Consumer nhận nhiều lần sự kiện ghi nhận cùng khoản chi. | Chống xử lý trùng tại nơi tạo hiệu ứng, gắn với giao dịch nghiệp vụ. |
| Kết quả ngoài hệ thống chưa rõ | Bên thực thi đã xử lý nhưng phản hồi bị mất. | Giữ trạng thái chưa rõ, tra cứu và đối soát trước khi thực hiện lại. |
| Giá trị được ghi nhận sai | Số dư đọc từ cache cũ hoặc khoản nạp bị ghi có hai lần. | Nguồn dữ liệu có thẩm quyền và quy tắc ghi nhận giá trị nhất quán. |

**Idempotency không tự ngăn mọi double spending.** Hai yêu cầu hợp lệ có hai khóa khác nhau vẫn có thể cạnh tranh cùng một số dư. Ngược lại, khóa giao dịch cơ sở dữ liệu không tự giải quyết việc một lệnh được gửi lại sau khi giao dịch đầu đã cam kết.

Yêu cầu cần bao phủ cả tính duy nhất của hiệu ứng nghiệp vụ và giới hạn của nguồn giá trị được tiêu thụ.

## 3. Ví dụ tranh chấp và bất biến cần bảo vệ

### 3.1. Đọc số dư rồi ghi sau có thể sai

| Thời điểm | Luồng A | Luồng B |
|---|---|---|
| 1 | Đọc khả dụng bằng 100. | |
| 2 | | Đọc khả dụng bằng 100. |
| 3 | Kiểm tra 100 đủ chi 80. | |
| 4 | | Kiểm tra 100 đủ chi 80. |
| 5 | Chấp nhận chi cho đơn A. | |
| 6 | | Chấp nhận chi cho đơn B. |

Nếu mỗi luồng ghi đè số dư bằng 20 từ ảnh chụp cũ, số dư cuối có thể vẫn không âm nhưng lịch sử lại chứa hai khoản chi 80. Nếu cả hai chỉ trừ mà không bảo vệ điều kiện đủ tiền, số dư có thể xuống âm.

Vì vậy, yêu cầu “số dư cuối không âm” là chưa đủ. Cần đồng thời kiểm tra tổng giá trị được chấp nhận và tính nhất quán với sổ ghi nhận.

### 3.2. Chọn mô hình giá trị rõ ràng

Trong ví dụ ví không cho thấu chi:

~~~text
B = số dư đã ghi nhận
R = tổng giá trị đang giữ cho các cam kết chưa quyết toán
A = số dư khả dụng = B - R

B >= 0
R >= 0
A >= 0
~~~

Các phép biến đổi cho một khoản x:

| Hành động | Thay đổi B | Thay đổi R | Tác động tới A |
|---|---:|---:|---|
| Giữ chỗ x | 0 | +x | Giảm x. |
| Quyết toán khoản đang giữ x | -x | -x | Không đổi so với ngay trước quyết toán. |
| Giải phóng khoản đang giữ x | 0 | -x | Tăng x. |
| Ghi có hợp lệ x | +x | 0 | Tăng x. |

Không được vừa giảm số dư khi giữ chỗ, vừa tiếp tục giảm theo cùng cách khi quyết toán nếu mô hình không định nghĩa như vậy. Tên trường phải phản ánh ngữ nghĩa; “balance” mơ hồ có thể làm nhiều thành phần dùng các công thức khác nhau.

### 3.3. Bộ bất biến tối thiểu

1. Số dư khả dụng không âm trong mọi trạng thái nghiệp vụ đã cam kết của ví thuộc mô hình không thấu chi.
2. Tổng giữ chỗ phải khớp các khoản giữ còn hiệu lực theo mô hình đã chọn.
3. Mỗi hiệu ứng chi có định danh nghiệp vụ và không vượt số lượng được phép cho định danh đó.
4. Mỗi khoản giữ chỉ được quyết toán hoặc giải phóng theo các đường chuyển hợp lệ.
5. Ghi nhận số dư, ledger, khoản giữ và biên nhận chống lặp không được để lại trạng thái từng phần trái quy tắc.
6. Số tiền, đơn vị giá trị, ví nguồn, người thụ hưởng và nghĩa vụ nghiệp vụ phải được xác lập từ dữ liệu có thẩm quyền.
7. Người hoặc dịch vụ tạo khoản chi phải có quyền trên nguồn giá trị và đúng phạm vi tenant.
8. Kết quả chưa rõ không được tự coi là chưa chi để cấp lại khả năng sử dụng cùng giá trị.

Nếu nghiệp vụ cho thấu chi, quy tắc đầu phải được thay bằng giới hạn tín dụng đã phê duyệt cùng điều kiện cụ thể. Không bỏ bất biến chỉ vì một loại tài khoản có chính sách khác.

## 4. Xác định danh tính của lệnh, nghĩa vụ và khoản giữ

Một hệ thống cần phân biệt ít nhất các định danh sau:

| Định danh | Ý nghĩa | Vai trò chống chi trùng |
|---|---|---|
| command_id hoặc idempotency key | Một lệnh từ bên gọi và các lần gửi lại của nó. | Nhận biết cùng một lệnh đã được xử lý. |
| business_reference | Nghĩa vụ nghiệp vụ, chẳng hạn lần thanh toán được phép của một đơn hàng. | Ngăn đổi khóa kỹ thuật để tạo lại cùng nghĩa vụ. |
| reservation_id | Khoản giữ trên nguồn giá trị cụ thể. | Ràng buộc quyết toán, giải phóng và hết hạn. |
| execution_id | Một ý định thực thi logic, đặc biệt khi có hệ thống ngoài. | Liên kết các lần giao việc, retry và kết quả về cùng ý định. |
| ledger_entry hoặc posting_group | Bản ghi hoặc nhóm bút toán của hiệu ứng đã được ghi nhận. | Cho phép đối soát và áp ràng buộc duy nhất phù hợp. |

Phạm vi định danh phải gồm tenant và loại nghiệp vụ khi cần. Không mặc nhiên coi cùng một chuỗi do client gửi là có quyền tham chiếu tới bất kỳ ví hoặc đơn hàng nào.

Trong ví dụ, mỗi đơn hàng chỉ có một lần thanh toán từ ví được phép. Nếu sản phẩm cho thanh toán nhiều phần, business_reference phải biểu diễn từng phần được phép và tổng các phần phải chịu giới hạn của nghĩa vụ gốc. Không dùng quy tắc “một đơn, một khoản chi” cho nghiệp vụ cho phép chia phần mà chưa phân tích.

Số tiền nên dùng biểu diễn chính xác theo đơn vị nhỏ nhất đã quy định hoặc kiểu thập phân có quy tắc rõ ràng. Không mặc định mọi loại tiền có cùng số chữ số thập phân. Giá trị âm, số không, tràn số, sai đơn vị hoặc làm tròn ngoài chính sách phải bị xử lý trước khi chấp nhận chi.

## 5. Điểm quyết định chi phải có tính nguyên tử

### 5.1. Điều kiện và tiêu thụ phải thuộc cùng một quyết định

Hệ thống phải bảo đảm rằng tại điểm chấp nhận cam kết chi:

- Nguồn giá trị tồn tại, thuộc đúng tenant và chủ thể được phép.
- Giá trị yêu cầu hợp lệ và đúng nghĩa vụ nghiệp vụ.
- Còn đủ khả dụng sau khi tính các khoản giữ liên quan.
- Chưa có hiệu ứng cho cùng nghĩa vụ vượt số lần cho phép.
- Thay đổi nguồn lực và ghi nhận hiệu ứng được cam kết nhất quán.

Thiết kế có thể dùng cập nhật có điều kiện, khóa dữ liệu, kiểm soát phiên bản, mức cô lập phù hợp hoặc tuần tự hóa theo nguồn giá trị. Không thể chứng minh an toàn chỉ bằng việc nói “đã dùng transaction”; phải chỉ ra điều kiện nào được bảo vệ trước các giao dịch cạnh tranh.

Nếu nhận xung đột hoặc phải thử lại giao dịch, lần thử lại phải đọc và đánh giá lại dữ liệu có thẩm quyền. Không tái dùng kết luận “đủ tiền” từ lần thử trước.

### 5.2. Mã giả cho chấp nhận một khoản giữ

~~~text
trong một đơn vị giao dịch bảo vệ được bất biến:
  xác lập tenant, chủ thể và quyền từ ngữ cảnh tin cậy
  xác định ví nguồn và nghĩa vụ nghiệp vụ có thẩm quyền

  nếu đã có cùng lệnh:
    kiểm tra nội dung khớp và quyền đọc kết quả hiện tại
    trả biên nhận, không tạo khoản giữ mới
  ngược lại:
    kiểm tra nghĩa vụ chưa có cam kết trùng
    kiểm tra số dư khả dụng tại điểm quyết định
    tăng giá trị đang giữ nếu và chỉ nếu còn đủ khả dụng
    ghi khoản giữ và liên kết nghĩa vụ
    ghi biên nhận lệnh và audit bắt buộc
    ghi ý định xử lý tiếp nếu cần

cam kết tất cả thay đổi hoặc không chấp nhận khoản giữ
~~~

Đây là mô tả ngữ nghĩa, không phải API của một thư viện. Tùy mô hình lưu trữ, quyền và nghĩa vụ có thể cần cơ chế xác minh riêng; giả định nhất quán phải được nêu rõ.

Trong một chuyển giá trị nội bộ, ghi giảm nguồn và ghi tăng đích cũng cần có hợp đồng nguyên tử hoặc cơ chế trung gian nhất quán đã được chứng minh. Không báo hoàn tất khi mới ghi một phía.

### 5.3. Ledger hỗ trợ kiểm chứng nhưng không thay mọi guard

Ledger ghi nhận lịch sử thay đổi giá trị. Với mô hình chuyển nội bộ cùng một đơn vị giá trị, một nhóm ghi nhận có thể gồm nguồn giảm x và đích tăng x, tổng điều chỉnh bằng không.

Hai lần chuyển trùng đều có thể tự cân bằng. Vì vậy, tính cân bằng của ledger không tự chứng minh không double spending. Vẫn phải có giới hạn nguồn lực, định danh hiệu ứng và ràng buộc nghiệp vụ.

Nếu lưu cả số dư tổng hợp và ledger, yêu cầu phải xác định dữ liệu nào có thẩm quyền, cách cập nhật nhất quán và cách phát hiện chênh lệch. Không dùng cache hoặc replica có thể trễ làm căn cứ duy nhất để cấp quyền chi.

## 6. Giữ chỗ, quyết toán và giải phóng

Một khoản giữ giúp tách “giá trị đã được dành cho công việc” khỏi “kết quả đã được quyết toán”. Trong ví dụ, mỗi khoản giữ được quyết toán toàn bộ một lần; chưa hỗ trợ quyết toán nhiều phần.

### 6.1. Mô hình trạng thái minh họa

~~~mermaid
stateDiagram-v2
    [*] --> RESERVED
    RESERVED --> CAPTURED: quyết toán nội bộ
    RESERVED --> RELEASED: hủy trước thực thi
    RESERVED --> EXPIRED: hết hạn trước thực thi
    RESERVED --> IN_FLIGHT: chấp nhận thực thi bên ngoài
    IN_FLIGHT --> CAPTURED: xác nhận thành công
    IN_FLIGHT --> RELEASED: xác nhận không tạo hiệu ứng
    IN_FLIGHT --> RECONCILING: chưa rõ kết quả
    RECONCILING --> CAPTURED: đối soát thành công
    RECONCILING --> RELEASED: đối soát không tạo hiệu ứng
~~~

CAPTURED, RELEASED và EXPIRED kết thúc vòng đời khoản giữ trong ví dụ. Hoàn lại giá trị sau CAPTURED là nghiệp vụ mới có định danh và quyền riêng, không sửa khoản giữ về RESERVED để dùng lại.

### 6.2. Tranh chấp giữa quyết toán và giải phóng

Nếu một worker quyết toán trong khi worker khác giải phóng cùng khoản giữ, chỉ một đường chuyển được cam kết theo guard hiện tại.

- Nếu quyết toán thắng, giải phóng không được cộng lại khả dụng.
- Nếu giải phóng trước thực thi thắng, quyết toán không được tiêu thụ khoản giữ đã kết thúc.
- Nếu đã IN_FLIGHT hoặc RECONCILING, không được tự giải phóng theo đồng hồ hết hạn của giai đoạn RESERVED.

Hết hạn chỗ giữ không phải bằng chứng một hoạt động bên ngoài chưa xảy ra. Nếu giải phóng khi kết quả vẫn chưa rõ, người dùng có thể dùng lại giá trị trong khi lần thực thi trước đã thành công.

### 6.3. Thời gian và quyền trên khoản giữ

Ví dụ, RESERVED có thời hạn 30 phút theo thời gian máy chủ có thẩm quyền. Quy tắc kiểm tra thời hạn phải được đánh giá cùng trạng thái khi cam kết chuyển; client không được tự kéo dài thời hạn.

Khoản giữ phải gắn với ví, đơn vị giá trị, số lượng và nghĩa vụ nghiệp vụ. Biết reservation_id không đủ để quyết toán hoặc giải phóng. Hệ thống phải kiểm tra quyền hành động và liên kết đối tượng, kể cả với tác vụ nền.

## 7. Gửi lại và kết quả chưa rõ ở ranh giới hệ thống

### 7.1. Idempotency cần đi cùng hiệu ứng

Trong ví dụ, biên nhận chống lặp được giữ tối thiểu 24 giờ từ lúc chấp nhận lệnh. Cùng tenant, phạm vi lệnh, khóa và nội dung phải quy về cùng kết quả đã cam kết; cùng khóa nhưng nội dung khác phải bị từ chối theo hợp đồng.

Biên nhận phải được ghi nhất quán với khoản giữ hoặc khoản chi. Nếu khoản chi đã cam kết nhưng biên nhận chưa được lưu, lần gửi lại có thể bị hiểu thành lệnh mới.

Sau thời hạn lưu, việc thiếu biên nhận không cấp quyền thực hiện lại nghĩa vụ. Guard trạng thái, định danh nghiệp vụ và các ràng buộc lưu cùng lịch sử thực thi vẫn phải bảo vệ giới hạn chi.

Một nghĩa vụ đã giải phóng trước thực thi có thể được thử lại nếu chính sách cho phép. Tuy nhiên, phải chứng minh lần trước không còn khả năng tạo hiệu ứng, không có cam kết chồng lấn và tổng quyết toán của nghĩa vụ không vượt mức được phép.

### 7.2. Ý định nội bộ và tác động bên ngoài

Ghi một ý định thực thi cùng giao dịch cục bộ giúp tránh mất công việc giữa cập nhật dữ liệu và gửi thông điệp. Cơ chế chuyển ý định, chẳng hạn outbox, vẫn có thể giao lại thông điệp.

Thành phần nhận phải dùng cùng execution_id và hợp đồng chống lặp phù hợp. Khi gọi bên ngoài, cần xác định:

- Bên ngoài có hỗ trợ định danh chống lặp không, phạm vi và thời hạn là gì.
- Có thể tra cứu kết quả bằng định danh đã ghi không.
- Những lỗi nào chứng minh chưa tạo hiệu ứng, lỗi nào chỉ cho biết chưa nhận được kết quả.
- Khi nào được retry, với định danh nào và trong giới hạn nào.
- Ai xử lý trường hợp kết quả mâu thuẫn hoặc kéo dài chưa rõ.

Không tạo execution_id mới chỉ vì lần gọi trước timeout. Nếu không có cách ngăn hoặc xác định hiệu ứng trùng ở bên ngoài, thiết kế chưa đủ căn cứ để tuyên bố không chi trùng tại ranh giới đó.

### 7.3. Bằng chứng kết quả phải được xác minh

Một callback thành công phải có nguồn xác minh được, liên kết đúng execution_id và khớp nghĩa vụ, số lượng, đơn vị giá trị và bên nhận theo hợp đồng.

Không dùng một trường “thành công” do client tự gửi làm căn cứ ghi nợ, ghi có hoặc quyết toán. Tương tự, một sự kiện nạp giá trị trùng không được tạo thêm khả dụng chỉ vì có hai lần giao thông điệp.

Thông điệp trùng hoặc đến muộn phải được xử lý mà không tạo thêm hiệu ứng. Một sự kiện cũ không được làm CAPTURED quay lại RESERVED hoặc giải phóng khoản đã quyết toán.

## 8. Nhiều writer, khóa và phân vùng mạng

Một khóa trong bộ nhớ tiến trình chỉ điều phối các luồng của tiến trình đó. Nó không tự bảo vệ khi có nhiều replica, worker hoặc vùng triển khai cùng ghi vào nguồn giá trị.

Ngay cả khóa phân tán cũng cần phân tích tình huống hết hạn: chủ cũ có thể tiếp tục chạy trong khi chủ mới đã được cấp khóa. Việc chỉ ghi log “đã lấy khóa” chưa chứng minh tại nơi cam kết không còn hai chủ ghi cạnh tranh.

Yêu cầu nên ràng buộc kết quả:

- Mọi đường chi phải đi qua cơ chế quyết định có thẩm quyền cho nguồn giá trị.
- Writer cũ hoặc writer không còn quyền sở hữu không được cam kết hiệu ứng trái bất biến.
- Kiểm soát cạnh tranh và tính duy nhất phải còn hiệu lực khi thay worker, failover hoặc retry.
- Mất khả năng xác minh nguồn lực không được làm từng phía độc lập cho phép dùng toàn bộ cùng một số dư.

Thiết kế có thể dùng điều kiện phiên bản hoặc mã thứ tự sở hữu được kiểm tra tại nơi ghi, bên cạnh các cơ chế điều phối khác. Cần kiểm thử khả năng từ chối writer cũ sau khi quyền sở hữu thay đổi.

Nếu nghiệp vụ cho chi ngoại tuyến hoặc nhiều nơi hoạt động độc lập, phải có mô hình phân bổ quyền chi hữu hạn, quy tắc tổng hạn mức và đối soát riêng. Không áp dụng lời cam kết của ví trực tuyến có một quyết định có thẩm quyền cho mô hình đó mà không bổ sung yêu cầu.

Khi không thể quyết định an toàn, hệ thống phải trả trạng thái tạm thời hoặc chưa rõ theo hợp đồng. Từ chối an toàn bảo vệ giá trị nhưng vẫn có tác động tới availability; cần đo và quản lý cả hai yêu cầu, không ghi nhận một lần từ chối là thanh toán thành công.

## 9. Bộ yêu cầu chống double spending mẫu

### SR-DS-001 — Không chấp nhận chi vượt nguồn khả dụng

Với ví không cho thấu chi, mỗi quyết định giữ hoặc chi mới phải bảo đảm số dư khả dụng sau cam kết không âm, sử dụng nguồn dữ liệu có thẩm quyền và tính đủ các khoản giữ còn hiệu lực.

Kiểm tra đủ giá trị và ghi nhận tiêu thụ phải được bảo vệ trước các lệnh cạnh tranh. Không dùng kết quả đọc cache hoặc ảnh chụp cũ làm căn cứ duy nhất.

Bằng chứng nghiệm thu: ví có B bằng 100, R bằng 0; hai lệnh khác nhau cho hai nghĩa vụ khác nhau cùng xin giữ 80. Tối đa một khoản giữ 80 được chấp nhận, không xuất hiện tổng giữ 160 hoặc hai khoản chi 80 từ nguồn đó.

### SR-DS-002 — Phạm vi quyền và nội dung có thẩm quyền

Mỗi lệnh phải kiểm tra quyền trên ví nguồn, tenant, hành động và nghĩa vụ nghiệp vụ. Người dùng không được đổi ví, đơn vị giá trị, số lượng hoặc bên nhận để mở rộng quyền bằng đầu vào tự khai.

Giá trị phải được biểu diễn chính xác, có giới hạn và quy tắc chuẩn hóa. Từ chối giá trị âm, sai đơn vị, vượt miền cho phép hoặc không khớp nghĩa vụ.

Bằng chứng gồm chủ thể khác tenant, chủ thể không sở hữu nguồn, thay đổi số tiền, sai đơn vị và các biên giá trị. Không phát sinh khoản giữ hoặc thay đổi số dư cho lệnh bị từ chối.

### SR-DS-003 — Chống lặp lệnh và ràng buộc nghĩa vụ

Trong tối thiểu 24 giờ, cùng lệnh và cùng nội dung phải liên kết với một biên nhận và hiệu ứng logic. Cùng khóa với nội dung khác phải bị từ chối; đọc kết quả đã lưu vẫn phải tuân theo quyền hiện tại.

Đổi khóa không được tạo cam kết chồng lấn hoặc quyết toán vượt mức cho cùng nghĩa vụ. Trong ví dụ mỗi đơn có một lần thanh toán từ ví được phép, không được có hai kết quả thanh toán thành công của cùng lần thanh toán đó.

Bằng chứng phải gồm gửi lại sau mất phản hồi, gửi đồng thời cùng khóa, cùng khóa khác nội dung và cùng nghĩa vụ với nhiều khóa khác nhau. Khi hết hạn biên nhận, guard nghiệp vụ vẫn phải ngăn hiệu ứng thứ hai trái phép.

### SR-DS-004 — Nhất quán số dư, khoản giữ và ledger

Mọi cam kết giữ, quyết toán, giải phóng hoặc ghi có phải cập nhật các dữ liệu có liên quan một cách nhất quán. Lỗi giữa các bước không được để lại số dư đã đổi nhưng không có hiệu ứng tương ứng, hoặc ledger đã ghi mà nguồn khả dụng không được bảo vệ.

Với chuyển nội bộ cùng đơn vị giá trị, ghi giảm nguồn và ghi tăng đích phải tuân theo hợp đồng nhất quán đã chọn. Hệ thống không được báo hoàn tất khi mới ghi nhận một phía.

Bằng chứng gồm chèn lỗi tại các điểm trước cam kết, sau cam kết và trước trả phản hồi. Đối soát phải chứng minh các phương trình số dư, khoản giữ và hiệu ứng vẫn đúng, không chỉ kiểm tra mã phản hồi.

### SR-DS-005 — Vòng đời khoản giữ chống quyết toán và giải phóng trùng

Khoản giữ phải có trạng thái, số lượng, đơn vị giá trị, ví nguồn, nghĩa vụ và định danh rõ ràng. Trong mô hình một lần quyết toán toàn bộ, cùng khoản giữ không được vừa CAPTURED vừa được giải phóng để tăng khả dụng.

RESERVED hết hạn sau 30 phút nếu chưa chuyển sang giai đoạn thực thi bên ngoài. Quyết toán, hủy và hết hạn phải kiểm tra trạng thái hiện tại theo cơ chế bảo vệ cạnh tranh.

IN_FLIGHT hoặc RECONCILING không được tự giải phóng chỉ vì thời hạn RESERVED đã qua. Chuyển từ các trạng thái này sang RELEASED cần bằng chứng không tạo hiệu ứng theo hợp đồng.

### SR-DS-006 — Không thực thi lại khi kết quả chưa rõ

Timeout, mất kết nối hoặc chưa nhận callback phải được phân loại theo bằng chứng. Nếu không thể kết luận, giữ liên kết execution_id và khoản giữ ở trạng thái phù hợp để đối soát, không cấp lại giá trị như thể chưa có cam kết.

Trong ví dụ, đối tượng ở RECONCILING quá năm phút phải phát cảnh báo trong 60 giây tiếp theo. Ngưỡng theo dõi này không tự trở thành điều kiện giải phóng.

Khi gửi lại tới bên ngoài, phải tuân theo khả năng chống lặp và tra cứu của ranh giới đó. Bằng chứng phải mô phỏng trường hợp bên ngoài đã xử lý thành công nhưng phản hồi bị mất, sau đó kết quả đến muộn.

### SR-DS-007 — Audit, đối soát và phục hồi an toàn

Mỗi quyết định được chấp nhận phải có bằng chứng về tenant, chủ thể, nguồn giá trị, nghĩa vụ, lệnh, khoản giữ hoặc lần thực thi, số lượng, đơn vị và trạng thái trước sau.

Các sai lệch giữa số dư, khoản giữ, ledger và kết quả bên ngoài phải được phát hiện qua đối soát theo lịch đã xác định. Trong hồ sơ ví dụ, thực hiện kiểm tra đối soát tự động ít nhất mỗi ngày và sau mỗi lần phục hồi dữ liệu trước khi mở lại đường chi.

Sửa sai phải tạo nghiệp vụ điều chỉnh có quyền và truy vết; không xóa khoản chi hoặc sửa trực tiếp số dư để che chênh lệch. Không cho phép ghi mới sau phục hồi khi chưa đánh giá các hiệu ứng bên ngoài có thể đã xảy ra nhưng chưa có trong dữ liệu khôi phục.

## 10. Ma trận kiểm thử và bằng chứng chấp nhận

| Kịch bản | Cách tạo điều kiện | Kết quả phải chứng minh |
|---|---|---|
| Hai nghĩa vụ khác nhau cùng tranh số dư | Ví có 100; hai lệnh đồng thời xin giữ 80 với khóa khác nhau. | Tối đa một khoản giữ được chấp nhận; nguồn lực và ledger nhất quán. |
| Nhiều lệnh cạnh tranh | 20 lệnh cho các nghĩa vụ khác nhau cùng xin giữ 80 từ ví có 100. | Tổng cam kết không vượt 100; kết quả từ chối hoặc xung đột rõ ràng. |
| Gửi lại cùng lệnh | Làm mất phản hồi sau cam kết, gửi lại cùng khóa và nội dung. | Không tạo khoản giữ, khoản chi hoặc ý định thứ hai. |
| Đổi khóa cho cùng nghĩa vụ | Gửi các khóa khác nhau cho cùng lần thanh toán được phép. | Không tạo cam kết chồng lấn hoặc quyết toán hai lần. |
| Nội dung không khớp | Dùng cùng khóa nhưng thay số lượng hoặc ví nguồn. | Từ chối xung đột; không tái dùng kết quả sai nội dung. |
| Tranh chấp vòng đời | Quyết toán, giải phóng và hết hạn cùng cạnh tranh trên một khoản giữ. | Chỉ đường hợp lệ được cam kết; không vừa trừ chi vừa cộng lại khả dụng. |
| Chèn lỗi từng phần | Dừng xử lý giữa các bước ghi hoặc ngay sau cam kết. | Không có số dư, ledger, khoản giữ hoặc biên nhận mâu thuẫn. |
| Thực thi ngoài chưa rõ | Bên ngoài thành công, phản hồi bị mất và callback về muộn. | Không giải phóng sớm, không tạo execution_id mới để chi lại. |
| Sự kiện trùng | Giao lại xác nhận chi hoặc nạp giá trị. | Không ghi nợ hoặc ghi có thêm cho cùng hiệu ứng. |
| Writer cũ tiếp tục chạy | Thay quyền sở hữu xử lý khi chủ cũ còn hoạt động. | Chủ cũ không cam kết trái guard tại nguồn có thẩm quyền. |
| Khôi phục dữ liệu cũ | Khôi phục bản dữ liệu chưa chứa một hiệu ứng ngoài đã xảy ra. | Đối soát trước mở chi; không cấp lại quyền sử dụng giá trị đã tiêu thụ. |

Ví dụ ca kiểm thử trọng tâm:

~~~gherkin
Feature: Hai lệnh khác nhau không cùng tiêu thụ vượt khả dụng

  Scenario: Hai khoản giữ cạnh tranh trên ví không thấu chi
    Given ví của tenant A có số dư đã ghi nhận 100 và tổng giữ 0
    And nghĩa vụ X và Y đều hợp lệ nhưng khác nhau
    And mỗi nghĩa vụ yêu cầu giữ 80 với khóa lệnh riêng
    When hai lệnh được xử lý đồng thời tại điểm kiểm tra khả dụng
    Then tối đa một khoản giữ 80 được cam kết
    And số dư khả dụng không âm
    And tổng khoản giữ khớp dữ liệu tổng hợp
    And không có hai hiệu ứng chi 80 từ nguồn ban đầu đó
    And kết quả từng lệnh và audit có thể được đối soát
~~~

Phép thử phải điều khiển hoặc quan sát được điểm cạnh tranh giữa kiểm tra nguồn lực và cam kết. Chạy tuần tự rồi thấy kết quả đúng không chứng minh thiết kế an toàn khi đồng thời.

Cần kiểm tra trên cấu hình nhiều writer hoặc replica nếu đó là mô hình triển khai. Một bài thử chỉ có khóa trong một tiến trình không đủ bằng chứng cho hệ thống có nhiều nơi ghi.

Bằng chứng nên gồm cấu hình, lịch thực thi, các định danh liên quan, dữ liệu trước sau, kết quả giao dịch và thông điệp. Các lần timeout hoặc mất phản hồi phải được đối soát trước khi kết luận số lượng hiệu ứng thực tế.

## 11. Logging, đối soát và điều tra

Số lượng HTTP thành công không phản ánh chính xác số khoản chi. Cần phân biệt lệnh đã nhận, lệnh đã cam kết, ý định đã phát, hiệu ứng đã xác nhận và kết quả chưa rõ.

Các tín hiệu hữu ích gồm:

- Số xung đột hoặc từ chối do không đủ khả dụng.
- Số lần gửi lại khớp biên nhận và số lần xung đột nội dung.
- Cùng nghĩa vụ xuất hiện nhiều lệnh hoặc nhiều định danh thực thi bất thường.
- Khoản giữ quá hạn, IN_FLIGHT kéo dài và RECONCILING chưa được giải quyết.
- Chênh lệch giữa số dư tổng hợp, ledger và khoản giữ.
- Bút toán hoặc xác nhận ngoài không liên kết được với ý định đã lưu.
- Lần thử quyết toán khoản đã giải phóng hoặc giải phóng khoản đã quyết toán.

Một trường hợp xung đột không tự chứng minh có chủ thể tấn công; client lỗi hoặc retry cũng có thể tạo ra nó. Cần giữ đủ ngữ cảnh để điều tra mà không ghi token, mật khẩu hoặc dữ liệu cá nhân không cần thiết.

Đối soát phải kiểm tra các bất biến theo từng nguồn giá trị và đơn vị. Không cộng nhiều loại tiền để kiểm tra cân bằng nếu chưa có mô hình quy đổi và bút toán tương ứng.

Khi phát hiện chênh lệch, cần quy định phạm vi tạm dừng, người có quyền quyết định và cách điều chỉnh. Hoàn tiền hoặc ghi bù là hiệu ứng mới có thể bị lặp; chúng cũng cần định danh, quyền và kiểm soát cạnh tranh.

## 12. Những cách viết dễ gây hiểu sai

| Cách viết chưa đủ | Vấn đề | Cách làm rõ |
|---|---|---|
| “Không cho số dư âm.” | Số dư có thể bị ghi đè trong khi lịch sử đã có hai khoản chi. | Kiểm tra cả tổng cam kết, ledger và nguồn khả dụng. |
| “Có idempotency key nên không thể chi trùng.” | Hai khóa khác nhau vẫn tranh cùng số dư hoặc cùng nghĩa vụ. | Bổ sung guard nguồn lực và ràng buộc nghiệp vụ. |
| “Đã dùng transaction.” | Chưa xác định điều kiện đọc và ghi có được bảo vệ trước cạnh tranh không. | Mô tả điểm quyết định và chứng minh bằng phép thử đồng thời. |
| “Ledger cân bằng là đủ.” | Hai giao dịch trùng đều có thể cân bằng riêng. | Kiểm tra tính duy nhất và giới hạn nguồn của mỗi hiệu ứng. |
| “Khóa ở service nên mọi nơi đều an toàn.” | Replica hoặc worker khác có thể không chịu cùng khóa. | Đặc tả quyền cam kết tại nguồn có thẩm quyền. |
| “Timeout thì trả lại tiền giữ.” | Bên ngoài có thể đã thực hiện thành công. | Giữ trạng thái chưa rõ và đối soát trước giải phóng. |
| “Hết hạn khóa thì worker cũ chắc chắn đã dừng.” | Chủ cũ có thể tiếp tục hoạt động. | Ngăn cam kết từ chủ cũ tại nơi tạo hiệu ứng. |
| “Gửi callback thành công là được ghi nhận.” | Có thể sai nguồn, trùng hoặc không khớp giao dịch. | Xác minh bằng chứng và liên kết ý định thực thi. |
| “Khôi phục backup là có thể mở ví ngay.” | Dữ liệu cũ có thể chưa phản ánh khoản chi đã xảy ra ngoài hệ thống. | Đối soát và đánh giá quyền chi trước khi mở ghi mới. |
| “Hoàn tiền là sửa số dư về giá trị trước.” | Mất lịch sử và có thể hoàn nhiều lần. | Tạo nghiệp vụ điều chỉnh có định danh và guard riêng. |

## 13. Truy vết và duy trì yêu cầu trong vòng đời phát triển

Khi phân tích nghiệp vụ, xác định nguồn giá trị, đơn vị, quyền sử dụng, giới hạn và số lần tiêu thụ được phép. Với điểm thưởng hoặc mã ưu đãi, cần nói rõ phạm vi “một lần”: theo người dùng, chiến dịch, đơn hàng hay toàn bộ mã.

Khi mô hình hóa đe dọa, đưa vào lệnh đồng thời, thay khóa, replay sự kiện, giải phóng sớm, writer cũ và phục hồi từ dữ liệu chưa cập nhật. Mỗi rủi ro cần liên kết với bất biến và bằng chứng tương ứng.

Khi thiết kế, gắn SR-DS-001 tới cơ chế quyết định nguồn lực, SR-DS-003 tới biên nhận và nghĩa vụ, SR-DS-004 tới đơn vị cam kết, SR-DS-005 tới vòng đời khoản giữ và SR-DS-006 tới ranh giới hệ thống ngoài.

Khi phát triển và nghiệm thu, kiểm tra cả đường hợp lệ lẫn tranh chấp và lỗi từng phần. Khi vận hành, theo dõi chênh lệch và kết quả chưa rõ; thay đổi số writer, thời hạn chống lặp, cách giữ chỗ hoặc nhà cung cấp thực thi phải được đánh giá lại.

Bài tập áp dụng: một nền tảng có 100 điểm thưởng khả dụng, hai đơn hàng cùng muốn dùng 80 điểm và một lệnh hoàn điểm có thể được gửi lại. Hãy viết bất biến, định danh nghiệp vụ, điều kiện chấp nhận, vòng đời giữ điểm và cách xử lý timeout. Với từng yêu cầu, nêu rủi ro được giảm, điểm thực thi trong kiến trúc và dữ liệu cần đọc lại để chứng minh không tiêu thụ hoặc hoàn điểm trùng.

