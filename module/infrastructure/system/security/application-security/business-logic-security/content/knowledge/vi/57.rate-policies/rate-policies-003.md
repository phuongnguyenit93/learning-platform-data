# Per tenant rate policy: bảo vệ hạn mức tốc độ theo tenant

## 1. Vì sao cần giới hạn theo tenant?

Trong chương **Rate Policies**, per tenant rate policy là quy tắc kiểm soát tốc độ tiếp nhận công việc của từng tổ chức hoặc không gian khách hàng. Mục tiêu là ngăn một tenant dùng quá phần tài nguyên được phép, làm ảnh hưởng tenant khác hoặc lạm dụng quy trình nghiệp vụ bằng nhiều yêu cầu hợp lệ riêng lẻ.

Một người dùng có thể sở hữu nhiều API key, chạy nhiều client và gửi request đến nhiều instance. Nếu chỉ giới hạn theo key hoặc bộ nhớ của từng instance, tổng lưu lượng của tenant vẫn có thể vượt xa chính sách sản phẩm.

Bài học thuộc module `SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`, tập trung bảo vệ bất biến nghiệp vụ, quyền theo đối tượng, transaction, idempotency và kiểm thử lạm dụng logic. Các mức tốc độ trong bài là ví dụ thiết kế, không phải khuyến nghị cấu hình chung cho mọi hệ thống.

Sau bài học, bạn cần:

- Xác định tenant từ ngữ cảnh được kiểm chứng, thay vì tin tham số do client tự khai.
- Phân biệt giới hạn tốc độ theo tenant với quota và số tác vụ đồng thời.
- Thiết kế hạn mức dùng chung giữa các API key, endpoint và instance theo đúng phạm vi nghiệp vụ.
- Hiểu ranh giới nhất quán của limiter phân tán, retry và thay đổi chính sách.
- Kiểm thử việc đổi danh tính kỹ thuật, chạy song song hoặc đổi đường gọi để lách giới hạn.

## 2. Định nghĩa rõ cái gì đang bị giới hạn

Một chính sách tốc độ cần ít nhất các thành phần:

```text
Chủ thể chịu giới hạn: tenant nào?
Nhóm hành động: loại công việc nào?
Đơn vị chi phí: request, điểm xử lý hoặc đơn vị khác?
Tốc độ duy trì: được cấp thêm bao nhiêu đơn vị mỗi khoảng thời gian?
Burst: được dùng dồn tối đa bao nhiêu đơn vị?
Điểm tính: khi tiếp nhận, khi bắt đầu xử lý hay theo hiệu lực khác?
Phạm vi chia sẻ: instance, vùng hay toàn hệ thống?
```

Ví dụ, tenant A được dùng nhóm `REPORT_QUERY` với tốc độ duy trì 20 điểm mỗi giây và burst tối đa 100 điểm. Một truy vấn đơn giản tốn 1 điểm; một truy vấn nặng có thể tốn nhiều hơn theo mô hình chi phí máy chủ xác định.

Các khái niệm sau giải quyết những vấn đề khác nhau:

| Cơ chế | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| Rate limit | Có nhận thêm công việc ở tốc độ này không? | 20 điểm mỗi giây, burst 100 |
| Quota | Còn tổng ngân sách trong kỳ không? | 100.000 dòng xuất trong tháng |
| Concurrency limit | Hiện có quá nhiều công việc đang chạy không? | Tối đa 3 export đang chạy cho một tenant |
| Queue bound | Có được xếp thêm công việc chờ không? | Tối đa 50 export đang chờ |
| Authorization | Tenant hoặc người gọi có quyền thực hiện không? | Được xuất báo cáo thuộc dự án P1 |

Một tenant có thể không vượt 20 điểm mỗi giây nhưng vẫn tích lũy hàng nghìn tác vụ dài. Ngược lại, chỉ có ba tác vụ đồng thời không ngăn việc tạo và hủy chúng liên tục. Các cơ chế cần phối hợp theo rủi ro và nguồn lực được bảo vệ.

Limiter cho phép không có nghĩa nghiệp vụ được phép. Nó chỉ xác nhận một điều kiện về tiếp nhận lưu lượng; quyền theo đối tượng, trạng thái, giá và các bất biến khác vẫn cần được kiểm tra.

## 3. Tình huống xuyên suốt

Giả sử dịch vụ phân tích báo cáo chạy trên ba instance, phục vụ tenant A và B. Tenant A có hai người dùng, năm API key và một tài khoản tích hợp.

| Thuộc tính | Chính sách minh họa |
| --- | --- |
| Nhóm nghiệp vụ | `REPORT_QUERY` |
| Tốc độ tenant A | 20 điểm/giây |
| Burst tenant A | 100 điểm |
| Chi phí truy vấn đơn giản | 1 điểm |
| Phạm vi chia sẻ | Toàn bộ instance và đường API thuộc nhóm |
| Quy tắc request đã nhận | Tiêu thụ điểm tiếp nhận; không tự hoàn chỉ vì xử lý sau đó lỗi |
| Giới hạn phụ | Có thể thêm theo actor hoặc key nhưng vẫn phải chịu bucket tenant |

Kết quả mong muốn:

- Đổi API key trong tenant A không tạo thêm một bucket tenant có hạn mức đầy đủ.
- Chuyển từ instance 1 sang instance 2 không nhận thêm 100 điểm burst độc lập.
- Gọi endpoint phiên bản mới nhưng cùng nhóm nghiệp vụ không tự có ngân sách mới.
- Client của A tự ghi `X-Tenant-Id: B` không được dùng hoặc tiêu hao bucket B nếu thiếu quyền trong B.
- Một response lỗi hoặc một request nghiệp vụ trùng không làm hệ thống tự hoàn token tiếp nhận để client có thể thử vô hạn.

Điểm tính cuối cùng ở đây là lựa chọn của mô hình. Nếu sản phẩm muốn một nhóm request được miễn hoặc hoàn điểm, phải có quy tắc riêng, kiểm chứng được và không làm mở đường gửi lặp để né giới hạn.

## 4. Tenant chịu giới hạn phải được xác định từ nguồn đáng tin cậy

### 4.1. Header hoặc tham số chỉ là lựa chọn ngữ cảnh

Một request có thể chứa `tenantId` trong URL, header hoặc body. Giá trị đó chỉ thể hiện tenant mà client muốn thao tác. Máy chủ cần kiểm tra danh tính, tư cách thành viên, API key binding hoặc quan hệ ủy nhiệm trước khi dùng nó làm tenant có thẩm quyền.

Ví dụ luồng hợp lệ:

```text
Bảo vệ lưu lượng thô tại điểm vào
→ xác thực credential
→ xác minh tenant được chọn nằm trong phạm vi credential
→ xác định nhóm hành động và chi phí ở máy chủ
→ áp dụng giới hạn tenant và các giới hạn bắt buộc khác
→ kiểm tra quyền đối tượng và thực hiện nghiệp vụ
```

Thứ tự kiểm tra chi tiết có thể thay đổi để giảm chi phí, nhưng không được để một giá trị chưa xác minh quyết định bucket của tenant khác.

### 4.2. Không cho kẻ gọi làm cạn bucket của nạn nhân

Nếu hệ thống trừ bucket B trước khi kiểm tra người gọi có quyền trong B, người dùng tenant A có thể gửi hàng loạt request chỉ định B để làm B bị giới hạn.

Những yêu cầu sai hoặc chưa xác thực vẫn cần cơ chế chống lạm dụng ở điểm vào, chẳng hạn giới hạn theo nguồn truy cập hoặc danh tính đã biết với các giả định tin cậy phù hợp. Nhưng không gán chúng cho bucket nghiệp vụ của một tenant nạn nhân chỉ vì ID nạn nhân xuất hiện trong request.

Nếu hệ thống dùng địa chỉ mạng từ proxy để bảo vệ ingress, phải xác định chuỗi proxy đáng tin. Một header IP do client tự gửi không tự trở thành danh tính mạng có thẩm quyền. Giới hạn theo IP cũng không thay thế giới hạn tenant vì nhiều người có thể dùng chung mạng hoặc một tenant có nhiều nguồn truy cập.

### 4.3. Tích hợp và thao tác thay mặt

Một tích hợp có thể hoạt động cho nhiều tenant. Hệ thống cần biết request đang được thực hiện cho tenant nào và quyền đại diện nào cho phép điều đó.

Có thể có hai lớp giới hạn:

```text
Giới hạn của ứng dụng tích hợp
AND giới hạn tenant đang nhận công việc
```

Không lấy tenant của tài khoản tích hợp làm mặc định cho mọi tác vụ nếu tài nguyên thực sự thuộc khách hàng khác. Cũng không cho tích hợp chọn tùy ý tenant chịu chi phí mà không kiểm tra ủy nhiệm.

Với thao tác nội bộ hoặc nhân viên hỗ trợ, mọi cơ chế bỏ qua limiter phải có quyền và phạm vi rõ ràng. Một header `internal=true` hoặc việc biết URL nội bộ không đủ làm căn cứ miễn giới hạn.

## 5. Bucket key và phạm vi chia sẻ

Một khóa bucket có thể có dạng:

```text
(namespace, canonical_tenant_id, business_action_group)
```

Nếu chính sách thực sự phân biệt vùng hoặc kênh, có thể thêm chiều đó. Tuy nhiên, thêm một chiều vào khóa cũng đồng nghĩa chia nhỏ ngân sách. Cần chứng minh đây là chủ ý sản phẩm.

### 5.1. Các chiều không nên vô tình tạo ngân sách mới

Không thêm các giá trị sau vào bucket tenant chỉ vì chúng thuận tiện trong request:

```text
api_key_id
user_id
instance_id
request_id
idempotency_key
đường dẫn nguyên vẹn có ID tài nguyên
policy_version dùng như một bucket độc lập mới
```

Có thể dùng API key hoặc user ID cho bucket phụ. Nhưng bucket tenant chung vẫn phải tồn tại nếu chính sách giới hạn tổng tenant.

Một đường dẫn như `/reports/R1/query` không nên tự tạo bucket khác `/reports/R2/query` khi cả hai thuộc cùng hạn mức truy vấn báo cáo. Nếu mỗi ID tạo một ngân sách mới, kẻ lạm dụng có thể luân phiên tài nguyên để vượt tổng.

### 5.2. Endpoint cần ánh xạ về nhóm nghiệp vụ ổn định

Các đường gọi như:

```text
GET /v1/reports/{id}/query
POST /v2/report-queries
POST /internal/query-proxy
```

có thể cùng tiêu thụ `REPORT_QUERY` nếu chúng tạo cùng loại công việc được bảo vệ. Ánh xạ nhóm phải do máy chủ sở hữu, không lấy từ một trường `rateGroup` client tự chọn.

Với batch, cần xác định chi phí phản ánh số phần tử hoặc mức xử lý. Một request chứa 1.000 truy vấn không được mặc định tính bằng một truy vấn nếu chính sách muốn giới hạn công việc thực tế.

### 5.3. Khóa phải có biểu diễn chuẩn

Dùng định danh tenant chuẩn đã được tra hoặc xác minh. Không để chữ hoa, chữ thường, alias hoặc các biểu diễn tương đương tạo nhiều bucket cho cùng tenant.

Khi ghép khóa, dùng định dạng có phân tách hoặc mã hóa không mơ hồ. Không nối các chuỗi tùy ý khiến hai bộ thành phần khác nhau có thể thành cùng một khóa. Giới hạn số chiều và cardinality cũng giúp tránh việc client tạo vô hạn state trong kho limiter.

## 6. Token bucket cho chính sách minh họa

Một token bucket có:

- `B`: dung lượng burst tối đa.
- `r`: tốc độ cấp thêm token mỗi giây.
- `T`: số token hiện còn, trong khoảng từ 0 đến B.
- `c`: chi phí dương của yêu cầu.
- `last_refill`: mốc thời gian đã dùng để cập nhật trạng thái.

Với thời gian trôi qua hợp lệ `dt`, trạng thái được cập nhật:

```text
T_refilled = min(B, T + r × dt)

Nếu c <= T_refilled:
    cho phép
    T_new = T_refilled - c
Ngược lại:
    từ chối
    không trừ thêm chi phí yêu cầu bị từ chối
```

Đọc trạng thái, tính refill, kiểm tra và trừ phải là một thao tác nguyên tử đối với bucket dùng chung.

Mô hình bài giả định `B > 0`, `r > 0` và `c > 0`. Chính sách chặn hoàn toàn, miễn giới hạn hoặc không refill cần trạng thái tường minh riêng; không dùng một số âm hoặc phép chia cho 0 để ngầm biểu diễn chúng.

### 6.1. Ví dụ nhỏ để quan sát tranh chấp

Dùng `B = 10`, `r = 2 token/giây`, bắt đầu với 10 token:

| Thời điểm | Chi phí | Token trước kiểm tra sau refill | Kết quả | Token còn |
| --- | ---: | ---: | --- | ---: |
| t = 0 | 7 | 10 | Cho phép | 3 |
| t = 0 | 5 | 3 | Từ chối | 3 |
| t = 1 giây | 5 | 5 | Cho phép | 0 |
| t = 2 giây | 1 | 2 | Cho phép | 1 |

Hai request tại t = 0 phải nhìn thấy một thứ tự nguyên tử. Không được cùng đọc 10 rồi cùng được chấp nhận với tổng chi phí 12.

Với tham số cố định và nguồn thời gian phù hợp, token bucket cho phép tổng chi phí trong một khoảng dài `dt` không vượt quá phần burst tối đa cộng lượng refill `r × dt`. Nó cho phép dùng dồn; nó không hứa mọi cửa sổ một giây đều có cùng số request được nhận.

### 6.2. Tránh nhầm với fixed window

Một bộ đếm 100 request trong mỗi phút lịch có thể nhận 100 request ngay trước ranh giới phút và 100 request ngay sau đó. Đây là đặc tính của fixed window, không phải tự động là lỗi lập trình.

Nếu sản phẩm cần giới hạn burst giữa các ranh giới, phải chọn thuật toán và tham số phù hợp. Không mô tả một fixed-window counter như thể nó bảo đảm cùng một ngữ nghĩa với token bucket hoặc cửa sổ trượt.

### 6.3. Thời gian và độ chính xác số học

Thời gian dùng để refill phải đến từ cơ chế máy chủ có thẩm quyền, không từ timestamp của client. Với kho trạng thái chia sẻ, cần nguồn thời gian và quy tắc xử lý sai lệch phù hợp với phạm vi bảo đảm.

Không lùi `last_refill` rồi cấp lại cùng khoảng thời gian khi đồng hồ quay ngược. Nếu đồng hồ nhảy tiến, bucket có thể được refill sớm theo thời gian thực dù vẫn bị chặn ở B; vì vậy không tuyên bố bảo đảm tốc độ chính xác vượt quá giả định về đồng hồ và kiến trúc.

Có thể dùng đơn vị thời gian và token theo số nguyên có tỷ lệ để tránh sai số tích lũy. Kiểm tra giới hạn giá trị, phép nhân `r × dt`, phép cộng và làm tròn. Một chi phí âm hoặc tràn số không được biến thành thao tác nạp thêm token.

## 7. Dùng chung hạn mức trong hệ thống nhiều instance

### 7.1. Bộ nhớ riêng của từng instance không tạo tổng hạn mức tenant

Nếu mỗi instance tự tạo bucket `B = 100`, `r = 20`, ba instance có thể nhận tổng burst 300 và tốc độ duy trì 60 điểm/giây cho cùng tenant. Cấu hình đúng trên từng máy không đồng nghĩa chính sách tổng đúng.

Một số lựa chọn kiến trúc:

| Cách làm | Điều cần chứng minh |
| --- | --- |
| Kho trạng thái chia sẻ với thao tác nguyên tử | Mọi instance dùng cùng khóa và cùng trạng thái có mức nhất quán phù hợp |
| Dịch vụ admission chuyên trách | Có đường gọi bắt buộc, kiểm soát danh tính và chính sách lỗi rõ ràng |
| Định tuyến một chủ sở hữu cho mỗi bucket | Không có hai chủ sở hữu cùng nhận quyền khi chuyển giao hoặc lỗi |
| Cấp ngân sách con cho các node hoặc vùng | Tổng phần được cấp không vượt ngân sách gốc và không bị cấp lặp |

Một lệnh cập nhật nguyên tử trên một node chưa tự chứng minh toàn bộ hệ thống không vượt giới hạn khi failover, mất dữ liệu hoặc có hai phía cùng xử lý. Phạm vi bảo đảm phải bao gồm cách sao chép, khôi phục và xử lý trạng thái cũ.

### 7.2. Giới hạn theo vùng cần ngữ nghĩa rõ ràng

Nếu mỗi vùng được cấu hình đầy đủ 20 điểm/giây, tổng toàn cầu sẽ lớn hơn 20 khi tenant dùng nhiều vùng. Có thể chấp nhận chính sách theo vùng, nhưng phải gọi và tính nó đúng như vậy.

Nếu sản phẩm cần tổng toàn cầu, có thể dùng một điểm điều phối hoặc phân bổ ngân sách con. Phân bổ trước giúp giảm độ trễ nhưng phải xử lý việc cấp lại khi node cũ chưa chắc đã mất quyền sử dụng.

Một lease hết thời gian theo bộ điều phối không tự bảo đảm node cũ đã dừng. Nếu vẫn cần giới hạn chặt, cơ chế thực thi phải ngăn việc dùng đồng thời ngân sách cũ và mới hoặc chấp nhận một mức vượt có giới hạn được tính rõ.

### 7.3. Xóa state có thể tạo thêm burst

Nếu state bucket bị xóa rồi được tạo mới với đầy token, tenant có thể nhận thêm một burst chưa đến lúc được refill.

Với token bucket cố định có `r > 0`, việc hết hạn state chỉ an toàn về mặt token khi khoảng nhàn rỗi đủ để bucket cũ cũng đã trở lại đầy theo cùng chính sách. Một mốc thận trọng là ít nhất `B / r` kể từ cập nhật liên quan, có làm tròn và xử lý thay đổi cấu hình phù hợp.

Đây không phải lời khuyên dùng một TTL cho mọi chính sách. Nếu tham số đổi, refill bị tắt hoặc state bị eviction ngoài dự kiến, giả định có thể không còn đúng. Kho limiter không được tự mất state rồi vẫn được quảng bá là giới hạn tổng chặt trong mọi tình huống.

## 8. Chi phí yêu cầu và nhiều lớp giới hạn

### 8.1. Chi phí do máy chủ xác định

Một mô hình có thể gán chi phí:

```text
Truy vấn đơn giản: 1 điểm
Truy vấn có nhóm tổng hợp lớn: 5 điểm
Batch: tính theo số phần tử và mức xử lý được chấp nhận
```

Đây chỉ là ví dụ. Chi phí phải dựa trên phân loại hoặc đầu vào đã được chuẩn hóa và giới hạn ở máy chủ. Client không được gửi `cost = 0`, `cost = -1` hoặc tự chọn nhóm rẻ hơn.

Nếu dùng số lượng phần tử làm chi phí, phải kiểm tra batch thực sự có bao nhiêu phần tử, các đường xử lý con và giới hạn kích thước. Việc chỉ đọc một trường `itemCount` client tự khai tạo lỗ hổng nghiệp vụ.

Một yêu cầu có chi phí lớn hơn B sẽ không bao giờ vừa bucket đó dù đợi bao lâu. Cần từ chối dạng công việc, chia nhỏ theo hợp đồng được phép hoặc dùng một luồng riêng; không trả một thời gian chờ hữu hạn rồi yêu cầu client thử vô hạn.

### 8.2. Tenant, actor và giới hạn toàn dịch vụ

Một yêu cầu có thể phải đồng thời đạt:

```text
Giới hạn ingress phù hợp
AND giới hạn toàn dịch vụ hoặc nhóm tài nguyên
AND giới hạn tenant
AND giới hạn actor hoặc API key nếu có
AND giới hạn đồng thời và hàng đợi nếu áp dụng
```

Ví dụ, mỗi key có 10 điểm/giây không thay thế bucket tenant 20 điểm/giây. Tạo mười key không được biến thành 100 điểm/giây nếu sản phẩm chỉ cấp 20 cho tenant.

Một giới hạn toàn dịch vụ cũng không tự bảo vệ tính công bằng giữa các tenant. Tenant A có thể chiếm gần hết công suất chung nếu thiếu giới hạn hoặc cơ chế lập lịch phù hợp cho từng tenant.

### 8.3. Nhiều bucket không mặc nhiên được cập nhật nguyên tử cùng nhau

Nếu lần lượt trừ bucket toàn dịch vụ rồi bucket tenant, bucket đầu có thể đã bị trừ trong khi bucket sau từ chối. Có thể chấp nhận tiêu thụ bảo thủ như vậy nếu được định nghĩa và không tạo hiệu lực vượt hạn mức.

Nếu cần tất cả cùng trừ hoặc cùng không trừ, phải có thao tác nguyên tử trên các trạng thái liên quan hoặc một giao thức nhận quyền được thiết kế tương ứng. Các bucket ở hai kho độc lập không tự tham gia cùng transaction.

Không hoàn token tùy tiện để mô phỏng rollback. Một lần hoàn bị gửi lại, hoặc hoàn sau khi trạng thái đã được refill và thay đổi, có thể cấp thêm ngân sách ngoài chủ ý. Nếu có cơ chế hoàn, phải gắn với một admission cụ thể, số lượng hữu hạn và trạng thái kết thúc đúng một lần.

## 9. Mã giả cho admission nguyên tử

Đoạn dưới mô tả một bucket token dùng chung. Nó không phụ thuộc thư viện hoặc công nghệ lưu trữ cụ thể.

Hàm nhận một tenant đã xác minh, nhóm hành động và chi phí do lớp máy chủ có thẩm quyền xác định. Đọc policy, xử lý phiên bản và cập nhật bucket phải nằm trong miền nhất quán phù hợp của dịch vụ limiter.

```java
public AdmissionResult admit(TrustedAdmission request) {
    var key = BucketKey.of(
        request.namespace(),
        request.verifiedTenantId(),
        request.serverActionGroup()
    );

    return bucketStore.atomic(key, tx -> {
        var policy = tx.loadAuthoritativePolicy();
        var state = tx.loadOrInitializeUnderPolicy(policy);
        var now = tx.trustedTime();

        // Nếu policy đổi, chuyển trạng thái theo quy tắc có kiểm soát.
        // Không tạo một bucket đầy mới chỉ vì version đổi.
        state = policyMigration.applyIfNeeded(state, policy, now);
        state.refillBoundedUsingCheckedArithmetic(policy, now);

        long cost = request.validatedCostUnits();
        require(cost > 0, "INVALID_COST");

        if (cost > policy.capacityUnits()) {
            tx.save(state);
            return AdmissionResult.unsupportedCost(policy.version());
        }

        if (state.tokensUnits() < cost) {
            var estimate = retryEstimator.fromCurrentState(
                policy, state, cost
            );
            tx.save(state);
            return AdmissionResult.throttled(
                policy.version(), estimate
            );
        }

        state.consumeExact(cost);
        tx.save(state);

        return AdmissionResult.allowed(
            request.serverAdmissionId(),
            key,
            cost,
            policy.version(),
            state.version()
        );
    });
}
```

Các giả định cần được thực hiện, không chỉ ghi vào tên hàm:

- `atomic` thực sự tuần tự hóa việc quyết định trên bucket dùng chung theo mức bảo đảm đã chọn.
- `TrustedAdmission` không được tạo trực tiếp bằng cách gán request body. Tenant, nhóm và chi phí đã được lớp máy chủ xác minh.
- `loadOrInitializeUnderPolicy` chỉ tạo state mới khi đúng điều kiện. Nó không cho client tạo lại bucket bằng key hoặc version tự chọn.
- Nguồn thời gian và phép refill có quy tắc cho độ chính xác, tràn số và đồng hồ bất thường.
- Thay đổi policy được chuyển đổi tại một mốc có thẩm quyền, không áp tốc độ mới ngược cho cả khoảng thời gian cũ ngoài chủ ý.
- Admission ID do máy chủ tạo cho một lần vào hệ thống, được ràng buộc tenant, nhóm và chi phí. Nó không phải giấy phép dùng lại cho nhiều yêu cầu nghiệp vụ.
- Mã chưa mô tả chống tính lại khi RPC đến limiter bị retry. Nếu cần, bổ sung receipt idempotency cho cùng admission theo phần tiếp theo.

Ở lớp nghiệp vụ, vẫn cần kiểm tra quyền và trạng thái tương ứng:

```text
Admission hợp lệ
→ kiểm tra hoặc dùng kết quả authorization đủ mới
→ tìm hoặc tạo ý định nghiệp vụ theo idempotency
→ transaction bảo vệ bất biến và hiệu lực
```

Một limiter riêng không thể thay thế transaction bảo vệ giá, số dư, trạng thái phê duyệt hoặc việc chỉ thực hiện một lần.

## 10. Retry, idempotency và tác vụ bất đồng bộ

### 10.1. Retry request bên ngoài khác retry RPC đến limiter

Trong mô hình bài, mỗi lần request bên ngoài được đánh giá tiếp nhận đều chịu rate policy, kể cả nó có cùng idempotency key nghiệp vụ. Nhờ vậy, gửi lại một lệnh đã hoàn tất không tạo một đường truy cập không giới hạn.

Idempotency nghiệp vụ bảo vệ việc không tạo thêm hiệu lực, như không xuất thêm file hoặc không gửi thêm đơn hàng. Nó không tự miễn chi phí xử lý HTTP, xác thực hoặc đọc trạng thái.

Ngược lại, middleware có thể gọi limiter, bị mất response rồi tự gửi lại chính lần RPC đó. Nếu lần trước đã trừ token, một lần trừ nữa có thể làm tính dư chi phí cho cùng một lần vào hệ thống.

Có hai cách xử lý phù hợp với những mức bảo đảm khác nhau:

- Chấp nhận tính bảo thủ và không tiếp tục nghiệp vụ khi chưa biết admission đã được cấp hay chưa; không tự hoàn token thiếu căn cứ.
- Dùng `server_admission_id` ổn định cho chính lần vào đó và lưu receipt kết quả theo cơ chế chống trùng của limiter.

Nếu dùng receipt, cùng ID nhưng đổi tenant, nhóm hoặc chi phí phải bị từ chối. Client không được tự phát lại một admission cũ để cấp phép cho nhiều lần vào mới. Receipt cũng cần thời hạn và cách xử lý hết hạn rõ ràng; hết dữ liệu chống trùng không tự chứng minh retry muộn vẫn an toàn.

### 10.2. Tiêu thụ token không nguyên tử với transaction nghiệp vụ

Limiter có thể cho phép rồi transaction nghiệp vụ rollback. Trong mô hình tính theo tiếp nhận, token vẫn đã được dùng. Đây là một tiêu thụ bảo thủ phù hợp với điểm tính đã công bố, không phải tự động là lỗi cần hoàn.

Nếu sản phẩm muốn chỉ tính khi hoàn tất, đó là một mô hình khác cần quy trình giữ, quyết toán hoặc đo sử dụng riêng. Không dùng việc hoàn token tự do sau mọi lỗi làm giải pháp, vì kẻ lạm dụng có thể liên tục tạo lỗi có chi phí mà không chịu giới hạn.

### 10.3. Xếp hàng không có nghĩa đã giới hạn công việc đang chạy

Một endpoint có thể chỉ nhận 20 điểm/giây nhưng vẫn xếp hàng nhanh hơn khả năng xử lý dài hạn. Cần giới hạn hàng đợi và số công việc đồng thời theo tenant nếu đó là tài nguyên phải bảo vệ.

Quy định rõ rate policy áp dụng khi nhận job, khi worker bắt đầu hay ở cả hai checkpoint với hai ngân sách khác nhau. Không vô tình tính cùng một điểm nghiệp vụ hai lần chỉ vì request và worker cùng đi qua một middleware.

Nếu hàng đợi phát lại cùng thông điệp, worker phải giữ cùng operation và kiểm soát quyền nhận xử lý. Việc phát lại không tự tạo một công việc độc lập chỉ vì nó đến từ nguồn nội bộ.

Nếu job có thể làm nhiều lời gọi ra một nhà cung cấp, có thể cần limiter riêng tại đường ra, gắn với tenant hoặc tài khoản thực sự chịu công việc. Limiter ở API vào không chứng minh tốc độ lời gọi ra đã đúng.

## 11. Thay đổi policy không được trở thành cách reset hạn mức

### 11.1. Nguồn policy phải có thẩm quyền

Policy có thể được suy ra từ gói dịch vụ, hợp đồng hoặc override quản trị. Máy chủ cần quy tắc ưu tiên rõ ràng giữa cấu hình gốc, giới hạn an toàn và ngoại lệ được phép.

Không để client chọn `plan = enterprise`, gửi `rate = 100000` hoặc tự khai một phiên bản cấu hình để được dùng mức cao hơn. Một flag phía giao diện cũng không là căn cứ tăng hạn mức.

Nếu có override tăng giới hạn, cần quyền, phạm vi, lý do và thời điểm hết hiệu lực thích hợp. Không cộng hoặc chọn giá trị lớn nhất của mọi nguồn cấu hình nếu chính sách không chủ động cho phép làm vậy.

### 11.2. Giữ bucket ổn định khi version thay đổi

Một cách làm nguy hiểm là:

```text
bucket_key = tenant_id + action_group + policy_version
```

Mỗi version mới sẽ có thể tạo một bucket đầy mới. Việc liên tục đổi cấu hình hoặc chuyển gói có thể cấp thêm nhiều burst.

Có thể giữ version trong state hoặc metadata để chuyển đổi chính sách, còn khóa nghiệp vụ ổn định. Ví dụ, tại mốc đổi được xác nhận:

1. Refill theo policy cũ đến mốc đổi theo quy tắc đã chọn.
2. Chuyển sang dung lượng mới với `tokens_new <= capacity_new`.
3. Không tự nạp đầy phần tăng dung lượng trừ khi chính sách cấp thêm burst cho phép rõ ràng.
4. Áp dụng tốc độ refill mới từ mốc đổi.
5. Lưu phiên bản và dấu vết chuyển đổi.

Một lựa chọn đơn giản cho số token là `min(tokens_current, capacity_new)` sau khi xử lý refill cũ. Đây là một chính sách chuyển trạng thái minh họa; hệ thống phải chọn và kiểm thử ngữ nghĩa của mình, nhất là khi giảm tốc độ, tăng dung lượng hoặc có nhiều vùng.

### 11.3. Cấu hình xấu không được tạo miễn giới hạn

Kiểm tra miền giá trị của capacity, refill rate, chi phí tối đa, TTL và các trạng thái đặc biệt. Nếu cấu hình thiếu hoặc không đọc được, không mặc định thành không giới hạn nếu sản phẩm chưa chủ động chọn điều đó.

Việc một instance còn cache policy cũ có thể khiến mức giới hạn khác nhau trong giai đoạn cập nhật. Nếu cần chuyển đổi chặt, dịch vụ admission phải kiểm chứng version hiện tại hoặc có giao thức áp dụng tương ứng. TTL cấu hình chỉ giới hạn độ cũ; nó không tự tạo thay đổi đồng thời trên mọi node.

## 12. Kết quả từ chối, thời gian thử lại và lỗi hạ tầng

### 12.1. Trả kết quả đúng ngữ nghĩa

Khi biết chắc request bị hạn chế do rate policy, API có thể trả trạng thái 429 cùng mã lỗi sản phẩm và gợi ý thử lại. Ví dụ minh họa:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 2
Content-Type: application/json

{
  "code": "TENANT_RATE_LIMITED",
  "requestId": "req_77",
  "retryAfterSeconds": 2
}
```

Với một bucket có `r > 0` và chi phí không vượt B, thời gian thiếu token tại snapshot hiện tại có thể ước lượng bằng:

```text
wait ≈ (cost - tokens_available) / refill_rate
```

Làm tròn theo hợp đồng response và đơn vị thời gian phù hợp. Đây là ước lượng khi chưa có lưu lượng cạnh tranh tiếp theo, không phải hứa chắc request sẽ được nhận đúng thời điểm đó.

Nếu bị chặn bởi nhiều giới hạn, kết quả phải phản ánh các điều kiện thực sự liên quan. Nếu chi phí không bao giờ vừa capacity, không trả một ước lượng hữu hạn dựa trên refill như thể đợi là đủ.

### 12.2. Không giả làm hết hạn mức khi limiter không trả lời

Khi kho limiter mất kết nối, hệ thống chưa chắc biết bucket đã hết. Có thể trả lỗi dịch vụ tạm thời phù hợp, chẳng hạn 503 trong hợp đồng minh họa, và ghi riêng lý do hạ tầng.

Chính sách lỗi cần cân bằng tài nguyên và tính sẵn sàng theo loại hành động:

| Lựa chọn | Điều cần bảo vệ |
| --- | --- |
| Chặn khi không xác minh được admission | Không nhận công việc vượt khả năng hoặc cam kết giới hạn |
| Dùng ngân sách dự phòng đã được cấp trước | Tổng ngân sách dự phòng không bị cấp lặp và có giới hạn rõ ràng |
| Chấp nhận một mức lưu lượng suy giảm có giới hạn | Không gọi đó là giới hạn tổng chặt nếu các node có thể nhận thêm độc lập |

Một fallback cho mỗi instance tự có đầy đủ hạn mức tenant có thể làm tổng tăng theo số instance. Nếu chọn đánh đổi đó, cần tính và quan sát mức vượt, không để nó xuất hiện như hành vi ngầm khi có lỗi.

### 12.3. Tránh tạo thêm làn sóng retry

Client nên có cơ chế chờ và phân tán thời điểm gửi lại theo hợp đồng. Ở phía máy chủ, không để worker hoặc gateway tự lặp nhanh khi nhận kết quả bị hạn chế.

Endpoint kiểm tra trạng thái và thông báo lỗi cũng dùng tài nguyên. Một lệnh nghiệp vụ đã bị chặn không được tự tạo hàng nghìn lần polling không kiểm soát hoặc một hàng đợi retry vô hạn.

## 13. Quan sát, audit và quyền quản lý policy

Cần quan sát số lần cho phép, từ chối, lỗi hạ tầng, chi phí đã nhận, độ trễ limiter và độ cũ policy theo các chiều có kiểm soát. Không dùng toàn bộ đường dẫn hoặc mọi ID client tự khai làm nhãn metric không giới hạn.

Một bản ghi quyết định hữu ích có thể gồm:

```text
request_id hoặc server_admission_id
tenant đã xác minh
action_group và cost
policy_version
kết quả allow, throttled, unsupported_cost hoặc unavailable
bucket_version hoặc định danh checkpoint phù hợp
instance hoặc vùng xử lý
thời điểm và reason_code
```

Không ghi raw access token hoặc API key bí mật vào audit. Nếu cần truy vết key, dùng định danh nội bộ phù hợp.

Policy và ngoại lệ cần audit riêng: ai thay đổi, giá trị trước, sau, mốc hiệu lực và phạm vi. Quyền xem thống kê không tự cho quyền tăng hạn mức hoặc tạo đường bypass.

Dữ liệu rate theo tenant cũng có thể tiết lộ hoạt động sử dụng. API quản trị, trang thống kê và nội dung response phải tôn trọng quyền xem tương ứng. Không trả chính xác lưu lượng tenant khác chỉ vì người gọi đoán được ID.

Các tín hiệu lạm dụng gồm luân phiên nhiều key sau khi bị hạn chế, chuyển endpoint cùng nghiệp vụ, đổi tenant tự khai, batch có chi phí bất thường hoặc tăng lưu lượng đúng lúc policy đổi. Cảnh báo giúp điều tra; bucket và kiểm tra quyền vẫn phải chặn trực tiếp tại điểm tiếp nhận.

## 14. Kiểm thử tình huống lách hạn mức

| Tình huống | Cách thử | Kết quả cần chứng minh |
| --- | --- | --- |
| Nhiều API key | Cùng tenant luân phiên nhiều key | Tổng vẫn chịu bucket tenant chung |
| Nhiều người dùng | Nhiều actor cùng gửi cho tenant A | Bucket actor không thay thế giới hạn tổng A |
| Nhiều instance | Cùng lúc gọi qua các instance | Không nhân capacity hoặc refill theo số instance ngoài chính sách |
| Giả tenant | Client A gửi tenant B chưa được phép | Không dùng hoặc làm cạn bucket B |
| Alias tenant | Dùng các biểu diễn tương đương của một tenant | Cùng một định danh chuẩn và cùng bucket |
| Đổi endpoint | Gọi v1, v2 và proxy cùng nghiệp vụ | Cùng nhóm rate nếu chính sách quy định như vậy |
| Đổi tài nguyên | Luân phiên nhiều report ID | Không tự có một ngân sách mới cho mỗi đường dẫn |
| Batch lớn | Một request chứa nhiều công việc con | Chi phí tính theo quy tắc máy chủ, không chỉ theo số HTTP request |
| Giả chi phí | Gửi cost 0, âm hoặc rất lớn | Không nạp token hoặc làm tràn số; chỉ dùng cost hợp lệ |
| Chi phí vượt burst | Cost lớn hơn capacity | Từ chối đúng loại, không gợi ý chờ hữu hạn sai nghĩa |
| Race trên bucket | Hai request cùng đọc gần hết token | Tổng được nhận không vượt trạng thái nguyên tử cho phép |
| Đổi policy | Tăng version liên tục hoặc chuyển gói | Không tạo bucket đầy mới ngoài chính sách chuyển đổi |
| State hết TTL | Request đến sau khi state bị xóa | Không cấp burst sớm hơn ngữ nghĩa refill cho phép |
| Eviction hoặc failover | Làm mất hoặc phục hồi state cũ | Hành vi khớp mức bảo đảm và fallback đã chọn |
| RPC limiter timeout | Lệnh trừ có thể đã commit nhưng response mất | Không tiếp tục không kiểm soát hoặc hoàn token thiếu căn cứ |
| Retry cùng idempotency key | Gửi lặp lệnh đã hoàn tất | Không thêm hiệu lực nghiệp vụ; lưu lượng lặp vẫn chịu rate theo hợp đồng |
| Lỗi nghiệp vụ sau admission | Tạo request bị lỗi sau khi nhận | Không tự hoàn token tiếp nhận để tạo vòng lặp miễn phí |
| Nhảy hoặc lùi đồng hồ | Mô phỏng nguồn thời gian bất thường | Không cấp lại cùng khoảng refill hoặc dùng timestamp client |
| Hàng đợi tăng nhanh | Nhiều job dài được tiếp nhận | Có giới hạn chờ và đồng thời nếu tài nguyên cần bảo vệ |
| Tích hợp đa tenant | Tài khoản tích hợp thao tác cho A và B | Tính đúng phạm vi đại diện và bucket chịu công việc |

### 14.1. Kiểm thử thuật toán với đồng hồ kiểm soát được

Dùng một nguồn thời gian kiểm thử để xác định trạng thái ban đầu, thời gian refill và thứ tự admission. Không cần chờ thật một phút chỉ để kiểm tra phép tính refill.

Với B = 10, r = 2 và hai request chi phí 7 và 5 tại cùng thời điểm, chỉ có tổng chi phí phù hợp được nhận. Sau một giây, trạng thái mới phải phản ánh đúng chi phí đã nhận, không dựa vào một bản sao đã đọc trước đó.

Kiểm tra biên 0 token, đúng bằng cost, capacity đầy, thời gian rất dài, cost quá lớn và số học gần giới hạn kiểu dữ liệu. Kiểm thử thuật toán trong một process chưa chứng minh được bảo đảm nhiều instance; cần kiểm thử riêng đường trạng thái chia sẻ.

### 14.2. Kiểm thử đồng thời và nhiều instance

Dùng kết nối hoặc process độc lập, tạo điểm đồng bộ để các request thực sự cạnh tranh cùng bucket. Tổng hợp chi phí được phép từ tất cả instance và so sánh với mô hình thời gian, capacity và refill đã định nghĩa.

Đồng thời thay API key hoặc endpoint nhưng giữ cùng tenant và nhóm nghiệp vụ. Nếu tổng được nhận tăng theo số key hoặc instance, khóa hoặc phạm vi chia sẻ đang khác chính sách.

Không dùng một kỳ vọng như “không quá 20 request trong mọi giây” để kiểm thử bucket cho burst 100. Kỳ vọng phải khớp thuật toán và chi phí, nếu không test có thể báo sai một hành vi được thiết kế hợp lệ.

### 14.3. Kiểm thử phục hồi và thay đổi cấu hình

Ngắt kết nối sau khi limiter đã cập nhật nhưng trước khi trả response; đổi policy khi còn ít token; chuyển chủ sở hữu bucket; và cho một node dùng policy cũ trong thời gian kiểm soát được.

Kiểm tra rằng fallback, receipt admission và chuyển trạng thái không tạo thêm ngân sách ngoài phạm vi đã công bố. Ghi rõ giới hạn của thử nghiệm nếu kiến trúc chấp nhận một mức vượt trong giai đoạn lỗi; không kết luận giới hạn tuyệt đối từ một lần chạy bình thường.

## 15. Tự đánh giá thiết kế

1. Tenant dùng để tính rate được xác minh từ đâu, và request sai có thể làm cạn bucket nạn nhân không?
2. Bucket nào giữ giới hạn tổng khi một tenant có nhiều key, actor, endpoint và instance?
3. Chi phí phản ánh công việc nào, và client có thể đổi nó bằng tham số tự khai không?
4. Thuật toán cho phép burst và refill ra sao, có khớp hợp đồng sản phẩm không?
5. Trạng thái chia sẻ có mức nhất quán nào khi failover hoặc có nhiều vùng?
6. Retry RPC đến limiter, retry HTTP và idempotency nghiệp vụ đang được phân biệt như thế nào?
7. Đổi policy, xóa state hoặc hết TTL có vô tình cấp một bucket đầy mới không?
8. Khi limiter lỗi, hệ thống chặn, dùng ngân sách dự phòng hay chấp nhận mức vượt có giới hạn nào?

Per tenant rate policy an toàn gắn lưu lượng với đúng tenant và cùng một ngân sách nghiệp vụ trên mọi đường xử lý liên quan. Khóa chuẩn, cập nhật nguyên tử, mô hình chi phí rõ ràng và chính sách phục hồi có giới hạn giúp ngăn việc đổi danh tính kỹ thuật hoặc tận dụng lỗi hệ thống để vượt phần tài nguyên được phép.
