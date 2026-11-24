# Per account rate policy — Chính sách tốc độ theo tài khoản

## 1. Chính sách tốc độ theo tài khoản bảo vệ điều gì?

**Per account rate policy** là chính sách kiểm soát tốc độ chấp nhận thao tác theo một tài khoản nghiệp vụ đã được xác định, thay vì chỉ theo địa chỉ IP, phiên đăng nhập hoặc API key.

Ví dụ, một tài khoản tổ chức được phép yêu cầu xuất báo cáo với tốc độ trung bình 2 đơn vị công việc mỗi giây và được tạo một đợt ngắn tối đa 10 đơn vị. Các thành viên, API key và ứng dụng tích hợp cùng dùng ngân sách của tài khoản đó, trừ khi sản phẩm có các phần phân bổ riêng được định nghĩa rõ.

Trong chương **Rate Policies** của module `SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`, mục tiêu là bảo vệ các bất biến nghiệp vụ trước lạm dụng như chia yêu cầu qua nhiều danh tính kỹ thuật, gọi API thay vì giao diện, dùng batch để che lượng công việc, gửi yêu cầu trùng hoặc vượt kiểm soát bằng xử lý đồng thời.

Rate limit giúp giới hạn tốc độ tạo tác động nhưng không chứng minh từng thao tác hợp lệ. Một request sửa giá hoặc bỏ qua phê duyệt vẫn sai dù chỉ gửi một lần mỗi ngày. Vì vậy chính sách tốc độ phải phối hợp với quyền theo đối tượng, state machine, transaction và idempotency.

Sau bài học, bạn có thể:

- Chọn đúng tài khoản và khóa chính sách từ ngữ cảnh xác thực.
- Phân biệt tốc độ, số lượng công việc đồng thời, quota tích lũy và chi phí nghiệp vụ.
- Thiết kế ngân sách có burst, trọng số và cập nhật nguyên tử.
- Xử lý nhiều API key, nhiều instance, retry và nhiều lớp hạn mức.
- Kiểm thử những cách lách chính sách qua batch, ranh giới thời gian và dữ liệu cấu hình.

## 2. “Account” phải có nghĩa nghiệp vụ rõ ràng

### 2.1. Tài khoản nào cùng chia sẻ ngân sách?

Account có thể là tài khoản cá nhân, tổ chức trả phí hoặc một chủ thể tích hợp. Không mặc định account đồng nghĩa với một user đang đăng nhập.

Ví dụ tổ chức A có ba thành viên và năm API key. Nếu chính sách cam kết 100 đơn vị/phút cho tổ chức, việc mỗi key có 100 đơn vị riêng sẽ tạo ra năm ngân sách thay vì một.

| Đối tượng | Vai trò trong chính sách |
|---|---|
| User | Chủ thể thực hiện, có thể thuộc nhiều tài khoản |
| Account hoặc tenant | Chủ thể chia sẻ ngân sách theo hợp đồng sản phẩm |
| API key | Thông tin xác thực hoặc ủy quyền cho một ứng dụng |
| Session | Phiên hoạt động, không mặc nhiên là nguồn ngân sách mới |
| IP | Tín hiệu mạng, có thể chung cho nhiều tài khoản hoặc thay đổi theo request |
| Tài nguyên đích | Đối tượng cần kiểm tra quyền, không tự quyết định người bị trừ ngân sách |

Thay API key hoặc đăng nhập lại không được làm mới ngân sách account nếu chính sách không cho phép. Ngược lại, hai tenant độc lập không nên bị gộp chỉ vì đi qua cùng một NAT.

### 2.2. Không lấy account trực tiếp từ trường client gửi

Request có thể chứa `accountId`, tenant trong URL hoặc header chọn tổ chức. Đây là lựa chọn cần xác minh với danh tính và quyền hiện hành, không phải bằng chứng người gọi được dùng ngân sách đó.

Một khóa chính sách tham khảo:

```text
(tenant_id, account_id, policy_group)
```

Các thành phần phải được lấy hoặc đối chiếu từ ngữ cảnh đáng tin cậy. Việc mã hóa khóa cần tránh va chạm giữa các thành phần; không nối chuỗi mơ hồ rồi giả định mỗi tổ hợp luôn có khóa khác nhau.

Không dùng `Idempotency-Key`, `User-Agent`, request ID hoặc một header account chưa kiểm tra làm danh tính ngân sách. Người gọi có thể đổi chúng cho mỗi request.

### 2.3. Ai thực hiện và ai chịu ngân sách có thể khác nhau

Một dịch vụ hỗ trợ có thể thay khách hàng chạy tác vụ. Hệ thống cần lưu cả chủ thể thực thi và tài khoản bị tính vào chính sách, đồng thời kiểm tra quyền ủy quyền tương ứng.

Không cho người gọi chọn tùy ý account của nạn nhân để làm cạn ngân sách. Nếu một thao tác thực sự tính theo tài khoản sở hữu tài nguyên, phải xác minh quan hệ và quyền trước khi tạo tác động lên ngân sách đó.

Với endpoint chưa xác thực, như đăng nhập, một username do người gọi nhập chưa phải tài khoản đã được xác thực. Kiểm soát trước xác thực cần chính sách riêng, phối hợp nhiều tín hiệu để tránh biến giới hạn theo tên tài khoản thành công cụ làm người khác không đăng nhập được.

## 3. Phân biệt rate limit với các ràng buộc khác

| Cơ chế | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| Rate limit | Được chấp nhận nhanh đến mức nào? | Trung bình 2 đơn vị/giây, burst 10 |
| Giới hạn đồng thời | Có bao nhiêu công việc đang chạy? | Tối đa 3 job hoạt động |
| Quota theo kỳ | Được dùng tổng cộng bao nhiêu trong kỳ? | 10.000 trang/tháng |
| Ngân sách hoặc credit | Có đủ quyền chi trả cho thao tác không? | Mỗi job cần 20 credit |
| Entitlement | Có quyền sử dụng tính năng không? | Gói được phép xuất báo cáo |
| Quyền theo đối tượng | Có được thao tác tài nguyên cụ thể không? | Được xuất dự án P thuộc tenant T |

Tốc độ 2 job/giây không bảo đảm chỉ có 2 job đang chạy. Nếu mỗi job kéo dài nhiều phút, số job đồng thời vẫn có thể tăng lớn. Cần giới hạn đồng thời nếu tài nguyên yêu cầu điều đó.

Tương tự, giảm tốc độ không ngăn một tài khoản dùng vượt quota tháng nếu tổng tích lũy không được kiểm tra. Một chính sách đầy đủ có thể yêu cầu mọi điều kiện sau cùng đúng:

```text
authenticated
AND authorized_for_object
AND entitled_for_feature
AND within_rate_policy
AND within_concurrency_policy
AND within_period_quota
AND business_state_allows_operation
```

Việc phối hợp các điều kiện phải có semantics rõ ràng khi một điều kiện sau bị từ chối. Không mặc định tất cả các bộ đếm có cùng cách giữ chỗ, hoàn lại hoặc ghi nhận.

## 4. Bất biến của chính sách theo account

### 4.1. Danh tính và phạm vi

- Mọi key hoặc phiên thuộc cùng account phải chia sẻ ngân sách khi chính sách yêu cầu.
- Không dùng quyền hoặc ngân sách của tenant khác do thiếu thành phần trong khóa.
- Các đường vào tương đương về nghiệp vụ phải đi qua cùng nhóm chính sách hoặc cơ chế phối hợp tương ứng.
- Người dùng không tự chọn gói, trọng số, mức burst hay quyền miễn kiểm tra.
- Endpoint quản trị chính sách phải có quyền và phê duyệt riêng khi cần.

### 4.2. Số lượng và thời gian

- Quyết định chấp nhận phải trừ ngân sách đúng trọng số, không chỉ đếm số request HTTP.
- Nhiều request đồng thời không được cùng tiêu một token khả dụng.
- Nhiều instance không được tự nhân hạn mức account ngoài mô hình đã công bố.
- Đồng hồ, TTL và thay đổi cấu hình không được tạo lại token ngoài quy tắc.
- Request bị từ chối không được thực hiện một phần nghiệp vụ nếu API cam kết xử lý nguyên khối.

### 4.3. Retry và hiệu lực nghiệp vụ

Một retry có thể vẫn tiêu ngân sách chống spam theo số lần gọi, nhưng không được tự tạo thêm tác vụ hoặc thu phí cho cùng operation idempotent. Cần phân biệt ngân sách cho lưu lượng request với ngân sách cho việc chấp nhận công việc mới.

Một operation thành công không trở thành hợp lệ chỉ vì đã lấy được token. Token tốc độ không phải phiếu bỏ qua phê duyệt, quyền theo đối tượng hoặc state machine.

## 5. Chọn mô hình tốc độ theo ý nghĩa sản phẩm

### 5.1. Cửa sổ cố định

Ví dụ giới hạn 100 request trong mỗi phút lịch. Mô hình dễ hiểu, nhưng account có thể được chấp nhận 100 request sát cuối phút và thêm 100 ngay đầu phút tiếp theo.

Nếu 100 request đến lúc giây 59,9 và 100 request đến lúc giây 60,1, tổng có thể là 200 trong khoảng 0,2 giây qua ranh giới. Điều này không phá đúng quy tắc cửa sổ cố định, nhưng không phù hợp nếu sản phẩm muốn “tối đa 100 trong mọi khoảng 60 giây”.

### 5.2. Cửa sổ trượt

Cửa sổ trượt xét hoạt động trong khoảng gần nhất. Cách lưu chính xác hoặc xấp xỉ có chi phí và sai số khác nhau; cần chốt mức chính xác trước khi dùng kết quả để hứa một giới hạn cứng.

Không gọi một cơ chế xấp xỉ là giới hạn tuyệt đối nếu thiết kế vẫn có thể vượt ở ranh giới hoặc do cập nhật trễ.

### 5.3. Token bucket

Token bucket mô tả thuận tiện cả tốc độ trung bình và đợt ngắn:

```text
B: sức chứa tối đa của bucket
r: tốc độ bổ sung token
T: số token hiện có
c: chi phí của thao tác
```

Với khoảng thời gian hợp lệ `dt`:

```text
T_refilled = min(B, T + r × dt)

nếu T_refilled >= c:
    chấp nhận và lưu T_refilled - c
ngược lại:
    từ chối, không thực hiện công việc mới
```

Ví dụ `B = 10`, `r = 2 token/giây`, mỗi thao tác tốn 1 token. Account có thể dùng ngay 10 token nếu bucket đầy; khi bucket đã cạn, sau 0,5 giây có thể có thêm 1 token theo cách biểu diễn thời gian và độ chính xác đã chọn.

Mô hình này cho phép burst, không tương đương “tối đa 2 request trong mọi giây”. Với trạng thái được bảo toàn và tốc độ không đổi, lượng được chấp nhận trong một khoảng có độ dài `t` bị giới hạn bởi lượng đầu khoảng cùng phần bổ sung, tối đa theo dạng `B + r × t`.

### 5.4. Thời điểm tiêu token

Chính sách phải nói rõ token đại diện cho điều gì:

- Mỗi lần gọi API, kể cả request bị từ chối nghiệp vụ.
- Mỗi cơ hội chấp nhận một công việc mới.
- Một lượng công việc đã được chấp nhận duy nhất.

Không dùng cùng một counter mà mỗi lớp lại hiểu theo một nghĩa khác. Việc một request lỗi có được trả token hay không phải theo hợp đồng; tự động hoàn token cho mọi lỗi có thể tạo đường chạy lặp việc tốn tài nguyên mà không tiêu ngân sách tốc độ.

## 6. Chi phí có trọng số và batch request

### 6.1. Một request không nhất thiết bằng một đơn vị

Nếu một request tạo 100 báo cáo nhưng chỉ tốn một token như request tạo một báo cáo, client có thể dùng batch để nhân tác động. Nên định nghĩa đơn vị chính sách theo chi phí hoặc ý nghĩa nghiệp vụ cần kiểm soát.

Ví dụ:

| Thao tác | Chi phí minh họa |
|---|---:|
| Tra cứu trạng thái một job | 1 đơn vị trong nhóm đọc |
| Tạo một báo cáo chuẩn | 1 đơn vị trong nhóm tạo báo cáo |
| Tạo một báo cáo nặng | 5 đơn vị trong nhóm tạo báo cáo |
| Batch 8 báo cáo chuẩn | 8 đơn vị trong nhóm tạo báo cáo |

Nhóm đọc có thể có ngân sách khác nhóm tạo việc để thao tác thăm dò trạng thái không chiếm hết khả năng tạo công việc. Tuy nhiên, hai endpoint cùng tạo cùng loại báo cáo không nên vô tình nhận hai ngân sách độc lập chỉ vì URL khác nhau.

### 6.2. Chi phí do máy chủ tính

Client có thể gửi số lượng cần xử lý, nhưng giá trị phải được kiểm tra kiểu, phạm vi, quyền và giới hạn batch. Trọng số lấy từ chính sách máy chủ, không tin trường `cost: 0` hoặc `priority: "INTERNAL"` do người gọi tự khai.

Ví dụ Java minh họa chi phí nguyên cho batch:

```java
long costForBatch(long itemCount, long serverUnitCost) {
    if (itemCount < 1 || itemCount > 1_000) {
        throw new IllegalArgumentException("INVALID_BATCH_SIZE");
    }
    if (serverUnitCost < 1 || serverUnitCost > 1_000_000) {
        throw new IllegalStateException("INVALID_RATE_COST_POLICY");
    }
    return Math.multiplyExact(itemCount, serverUnitCost);
}
```

Hàm chỉ minh họa kiểm tra miền giá trị và số học; nó chưa thực hiện quyền, chống trùng hay cập nhật bucket. Các giới hạn là ví dụ sản phẩm, không phải hằng số dùng chung cho mọi hệ thống.

Nếu chi phí chỉ biết sau khi chạy, cần cơ chế ước lượng bảo thủ, giới hạn đầu vào, chia việc hoặc giữ ngân sách theo mô hình rõ ràng. Đếm một token ở đầu rồi cho phép thực hiện lượng việc không giới hạn không bảo vệ được tốc độ tác động.

### 6.3. Request lớn hơn sức chứa

Nếu `c > B`, request không thể được chấp nhận chỉ bằng cách chờ bucket đầy. API cần trả lỗi phù hợp hoặc hỗ trợ chia nhỏ theo quy tắc, thay vì hướng dẫn retry vô hạn.

Chia nhỏ không được bỏ qua giới hạn tổng vì mọi phần vẫn phải dùng cùng ngân sách account và nhóm công việc. Với batch nguyên khối, lấy đủ token trước khi bắt đầu; không chạy nửa batch rồi mới phát hiện thiếu token nếu hợp đồng không cho phép xử lý một phần.

## 7. Cập nhật bucket nguyên tử

### 7.1. Race condition khi đọc rồi trừ riêng

Bucket còn 1 token. Hai request đều đọc thấy 1 rồi cùng được chấp nhận. Ghi lại 0 hai lần không có nghĩa chỉ một request đã được cấp phép.

Tương tự, mutex trong một tiến trình không bảo vệ các instance khác. Nếu mỗi instance có bucket đầy riêng cho cùng account, account có thể nhận tổng ngân sách lớn hơn chính sách theo số instance phục vụ.

### 7.2. Một quyết định nguyên tử cho refill và tiêu token

Mã giả tham khảo:

```text
atomic decision for the rate key:
  load trusted policy and bucket state
  obtain authoritative time for this bucket

  dt = max(0, now - last_refill_at)
  refilled = min(capacity, tokens + refill_rate * dt)
  next_refill_at = max(last_refill_at, now)

  if cost > capacity:
      reject request that cannot fit this policy
  else if refilled >= cost:
      store tokens = refilled - cost
      store last_refill_at = next_refill_at
      return ALLOW
  else:
      store refill progress consistently
      return DENY with appropriate retry guidance
```

Đây là mã giả, không phải triển khai cho một hệ quản trị cụ thể. Cơ chế nguyên tử có thể nằm trong transaction, thao tác có điều kiện hoặc một dịch vụ cấp phép có cùng bảo đảm. Cần kiểm chứng khả năng phối hợp thực tế trên nơi lưu trạng thái được chọn.

Trong ví dụ, request bị từ chối vì thiếu token không tiêu thêm token của bucket công việc, nhưng vẫn có thể bị tính vào một ngân sách số lần gọi riêng. Việc cập nhật tiến trình refill khi từ chối không được tự tạo token ngoài công thức.

### 7.3. Đồng hồ và độ chính xác

Không dùng timestamp do client gửi để refill. Trong một tiến trình có thể dùng thời gian đơn điệu; với trạng thái dùng chung cần nguồn thời gian và cách xử lý sai lệch được xác định phù hợp.

Nếu đồng hồ lùi, không cho `dt` âm và không lùi mốc refill khiến lần sau được cộng lại cùng một khoảng. Nếu đồng hồ nhảy tới trước, phần refill sai vẫn có thể làm đầy bucket sớm; chặn giá trị âm chưa giải quyết toàn bộ vấn đề thời gian.

Token lẻ có thể được biểu diễn bằng đơn vị nhỏ cố định hoặc kiểu số chính xác phù hợp. Tránh sai số tích lũy, tràn phép nhân và mất phần refill lẻ do làm tròn thiếu chủ đích. Khi đã chọn độ chính xác, phải dùng nhất quán trong lưu trữ, quyết định và kiểm thử.

### 7.4. TTL không được reset ngân sách sớm

Xóa trạng thái bucket thường khiến lần truy cập sau khởi tạo lại đầy token. Nếu trạng thái bị xóa trước khi bucket đáng lẽ đã tự đầy, TTL trở thành đường cấp thêm burst.

Với token bucket có `r > 0`, việc thu gom một bucket không hoạt động cần xét thời gian đủ để nó phục hồi đầy và các điều kiện chính sách liên quan. Khi `r = 0`, không thể áp dụng tùy tiện quy tắc hết hạn như bucket có refill.

Không để người dùng đổi key, chuyển endpoint hoặc kích hoạt cơ chế reset để xóa trạng thái đang hạn chế họ. Thay đổi cấu hình cũng cần xử lý trạng thái cũ có chủ đích.

## 8. Phối hợp nhiều lớp chính sách

### 8.1. Account, user và hệ thống có thể cùng có giới hạn

Một thao tác có thể chịu đồng thời:

```text
giới hạn account cho nhóm tạo báo cáo
AND giới hạn user trong account để một thành viên không chiếm hết ngân sách
AND giới hạn tài nguyên dùng chung của hệ thống
```

Các lớp này phục vụ mục tiêu khác nhau. Giới hạn riêng từng user không tự bảo vệ tổng account, vì tài khoản có thể thêm nhiều user. Giới hạn riêng account cũng không bảo đảm công bằng giữa các thành viên bên trong.

Nếu sản phẩm cấp những phần ngân sách riêng cho ứng dụng hoặc nhóm, cần quy tắc phân bổ và giới hạn tổng. Không tự tạo phần mới khi người dùng sinh thêm API key.

### 8.2. Tránh trừ một lớp rồi bỏ quên khi lớp sau từ chối

Giả sử account còn 7 token, ngân sách hệ thống còn 5, request cần 6. Request không thể được chấp nhận theo cả hai điều kiện.

Nếu hợp đồng yêu cầu các bucket công việc chỉ bị trừ khi toàn bộ điều kiện tốc độ cùng cho phép, cần quyết định nhiều bucket nguyên tử hoặc một cơ chế điều phối tương đương. Trừ account trước rồi từ chối ở ngân sách hệ thống sẽ không đáp ứng hợp đồng đó.

Một cách đơn giản hơn có thể là quy định rõ một lớp đếm mọi lần thử đi qua, còn lớp khác kiểm soát công việc mới. Khi đó việc tiêu ngân sách lớp đầu dù lớp sau từ chối có thể là đúng chính sách. Điều quan trọng là semantics được chọn rõ ràng, không để thứ tự middleware quyết định ngẫu nhiên.

Không tự hoàn token bằng phép cộng không có mã thao tác và giới hạn. Retry hoàn hoặc refill xen kẽ có thể tạo token thừa. Nếu dùng cơ chế giữ–chốt–giải phóng, phải thiết kế vòng đời và chống trùng riêng; nó phức tạp hơn một phép giảm counter.

### 8.3. Hàng đợi không thay thế kiểm soát tốc độ thực thi

Rate limit ở API có thể kiểm soát tốc độ nhận job. Khi worker ngừng rồi hoạt động lại, hàng đợi tích lũy có thể được xử lý rất nhanh, tạo burst tại nhà cung cấp hoặc cơ sở dữ liệu phía sau.

Nếu cần giới hạn tốc độ thực thi, dispatcher hoặc worker cũng cần chính sách tương ứng theo account và tài nguyên. Job phải mang định danh account đã xác minh, không để consumer lấy một account khác từ payload không được kiểm tra.

Cần phân biệt hai ngân sách tiếp nhận và thực thi. Không vô tình lấy một token cho cùng ý nghĩa hai lần chỉ vì request và worker đều đi qua hàm có cùng tên.

## 9. Rate policy và idempotency

### 9.1. Hai ngân sách có thể cần hai cách đếm

Một thiết kế thường cần tách:

- **Ngân sách số lần gọi:** giới hạn lưu lượng, kể cả retry hoặc truy vấn lặp.
- **Ngân sách nhận công việc mới:** áp dụng theo operation được chấp nhận, không tự lặp khi trả lại kết quả cũ.

Nếu hoàn toàn miễn mọi retry khỏi kiểm soát lưu lượng, người gọi có thể phát lại cùng key liên tục để gây tải tra cứu. Nếu mỗi retry đều tạo job mới hoặc trừ credit mới, hệ thống lại vi phạm idempotency.

### 9.2. Thứ tự xử lý cần có chủ đích

Luồng tham khảo cho endpoint tạo job:

```text
authenticate and resolve trusted account
apply attempt-rate policy for incoming calls
validate request and verify object permission
resolve scoped idempotency key and fingerprint

if operation already exists:
    return authorized stored result or in-progress reference
else:
    acquire unique ownership for the new operation
    enforce work-admission rate policy
    verify quota, entitlement and business state
    create the job once
    persist result and dispatch intent
```

Đây là luồng logic, chưa tự bảo đảm mọi bước có tính nguyên tử. Việc lấy quyền xử lý key, admission và tạo job phải có giao thức lưu trữ phù hợp với ý nghĩa đã cam kết.

Nếu bộ giới hạn tốc độ nằm ngoài cơ sở dữ liệu nghiệp vụ, lấy token thành công rồi tạo job thất bại có thể làm mất một cơ hội admission. Điều này có thể được chấp nhận nếu token đếm cơ hội xử lý, nhưng không được gọi là “chỉ đếm job thành công” khi không có cơ chế bảo đảm.

Muốn bộ đếm và job commit cùng nhau trong một nguồn dữ liệu có thể dùng transaction thích hợp. Khi ở nhiều nơi lưu khác nhau, cần giao thức điều phối và phục hồi; không giả định một transaction ứng dụng bao trùm được tất cả.

### 9.3. Key không thay thế danh tính nghiệp vụ

Idempotency key phải có phạm vi, chẳng hạn tenant, chủ thể đã xác thực và loại thao tác. Cùng key nhưng khác nội dung phải được xử lý như xung đột theo hợp đồng API.

Người gọi có thể dùng nhiều key cho cùng một sự kiện nghiệp vụ. Khi sản phẩm chỉ cho phép một hiệu lực cho sự kiện đó, cần thêm khóa hoặc ràng buộc theo sự kiện do máy chủ kiểm soát.

Ngược lại, hai job có cùng nội dung chưa chắc là trùng. Không dùng hash payload làm quy tắc cấm toàn cục nếu người dùng được phép yêu cầu hai lần độc lập. Rate limit kiểm soát tốc độ hai lần yêu cầu hợp lệ; idempotency bảo vệ một operation khỏi bị thực hiện lặp do retry.

### 9.4. Lỗi và retry không được biến thành đường miễn phí

Một thao tác có thể tiêu CPU hoặc gọi bên ngoài rồi mới lỗi. Nếu mọi lỗi đều trả lại toàn bộ token, người gọi có thể lặp đầu vào gây lỗi đắt đỏ để tiếp tục dùng tài nguyên.

Cần chọn điều kiện tiêu token dựa trên loại ngân sách, kết hợp kiểm tra đầu vào sớm và giới hạn riêng cho luồng lỗi khi cần. Không tự hoàn credit, reset quota hoặc bỏ qua kiểm tra quyền chỉ vì rate limiter vừa từ chối một retry.

## 10. Phản hồi khi vượt chính sách

### 10.1. Trả kết quả rõ ràng và không chạy nghiệp vụ mới

Một response minh họa khi account tạm thời chưa đủ token:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 2
Cache-Control: no-store
Content-Type: application/json

{
  "code": "ACCOUNT_RATE_LIMITED",
  "policyGroup": "REPORT_CREATE",
  "retryAfterSeconds": 2
}
```

Response không nên chứa API key, định danh account khác hoặc thông tin nội bộ không cần thiết. Quyền xem chi tiết chính sách cũng phải phù hợp phạm vi của người gọi.

Với token bucket có tốc độ bổ sung dương và request có thể vừa bucket, một ước lượng chờ có thể dựa trên:

```text
wait = ceil((cost - available_tokens) / refill_rate)
```

Ước lượng cần cùng đơn vị và độ chính xác với phép quyết định. Nó không giữ chỗ cho client: request khác có thể dùng token trước khi client thử lại. Nếu nhiều chính sách cùng áp dụng, hướng dẫn retry phải xét các điều kiện liên quan, không chỉ một bucket thuận tiện.

### 10.2. Phân biệt thiếu token với tình huống khác

Không báo “chờ 2 giây” cho request có chi phí lớn hơn capacity và không bao giờ đủ điều kiện. Không dùng rate limit để che một lỗi thiếu quyền hoặc một trạng thái nghiệp vụ không hợp lệ.

Nếu nguồn trạng thái rate limit không truy cập được, đó cũng không tự chứng minh account đã vượt tốc độ. Hệ thống cần mã lỗi và hành vi phù hợp chính sách sẵn sàng đã định, đồng thời ngăn việc lỗi hạ tầng làm tăng quyền ngoài cam kết.

### 10.3. Client retry có giới hạn

Client nên tôn trọng hướng dẫn chờ, dùng backoff có giới hạn và độ lệch ngẫu nhiên để tránh mọi client cùng thử lại một thời điểm. Cùng operation cần giữ idempotency key phù hợp khi retry.

Server vẫn phải kiểm tra lại mỗi lần. Header do client tự gửi rằng “đã chờ đủ” không cho phép bỏ qua bucket. Việc client hoạt động đúng chỉ giúp giảm tải, không phải ranh giới bảo mật.

## 11. Nhiều instance, nhiều vùng và thay đổi cấu hình

### 11.1. Một account không được có một ngân sách đầy tại mỗi instance

Nếu bốn instance đều cho account burst 10 độc lập, account có thể nhận tổng burst 40 khi request được phân phối qua cả bốn. Sticky session cũng không phải bảo đảm lâu dài nếu có chuyển instance, lỗi hoặc nhiều đường vào.

Các hướng triển khai có thể là nguồn trạng thái dùng chung với quyết định nguyên tử, dịch vụ cấp phép có thẩm quyền hoặc phân chia ngân sách cứng cho từng vùng. Mỗi cách phải có quy tắc rõ khi kết nối mất hoặc trạng thái được chuyển nơi.

Ví dụ chia tĩnh bucket có `B = 20`, `r = 4 token/giây` thành hai vùng, mỗi vùng `B = 10`, `r = 2`, có thể bảo vệ giới hạn tổng theo các giả định của mô hình và trạng thái phân chia. Đổi lại, một vùng có thể hết token trong khi vùng kia còn, làm giảm khả năng tận dụng ngân sách.

Điều phối lại phần ngân sách cần bảo toàn token và tốc độ đã ủy quyền. Không cấp lại toàn bộ phần của một vùng chỉ vì mất liên lạc trong khi vùng đó vẫn còn khả năng chấp nhận request. Lease hoặc thế hệ chỉ có tác dụng nếu nơi thực thi thực sự ngừng dùng quyền cấp phép đã hết hiệu lực.

### 11.2. Đồng bộ sau có thể không bảo vệ được giới hạn cứng

Nếu mỗi vùng tự chấp nhận rồi cộng counter sau, hệ thống có thể phát hiện vượt nhưng không ngăn được các request đã được nhận.

Một chính sách xấp xỉ có thể phù hợp một số mục tiêu chống tải, nhưng cần biết phạm vi vượt có thể xảy ra. Không mô tả cơ chế xấp xỉ như bảo đảm chính xác cho nghiệp vụ yêu cầu hạn mức cứng.

Nếu nguồn rate limit lỗi mà mỗi instance chuyển sang bucket cục bộ đầy, tổng ngân sách có thể bị nhân lên. Chọn từ chối, trì hoãn hoặc dùng phần dự phòng đã giới hạn theo mục tiêu sản phẩm; không để fallback tự quyết định một hạn mức mới lớn hơn.

### 11.3. Đổi gói hoặc phiên bản không tự reset bucket

Nếu key lưu trạng thái có thêm `policy_version` và mỗi lần triển khai lại tạo key mới đầy token, account sẽ nhận burst mới ngoài ý định mỗi khi cấu hình đổi.

Có thể giữ danh tính nhóm chính sách ổn định và lưu phiên bản áp dụng trong trạng thái, hoặc dùng một quy trình chuyển đổi khác có bảo toàn ngân sách. Việc chủ động cấp burst mới phải là quyết định chính sách có căn cứ, không là tác dụng phụ của đổi tên key.

Khi giảm capacity, cần xác định cách giới hạn lượng token còn lại. Khi đổi refill rate, không dùng tốc độ mới cho toàn bộ khoảng thời gian cũ nếu điều đó không đúng chính sách; cần tính phần thời gian trước và sau mốc áp dụng phù hợp.

Thao tác đổi cấu hình cần quyền riêng, kiểm tra phạm vi và lịch sử. Không cho người dùng tự khai gói cao hơn hoặc gửi cờ bỏ qua giới hạn. Consumer cấu hình cũng cần ngăn sự kiện phiên bản cũ ghi đè cấu hình mới.

## 12. Kiểm toán và quan sát hành vi lạm dụng

Một quyết định rate limit quan trọng nên truy vết được account, tenant, nhóm chính sách, phiên bản áp dụng, chi phí, kết quả và operation liên quan khi có. Không cần ghi token xác thực hoặc payload nhạy cảm để điều tra tốc độ.

Các tín hiệu hữu ích gồm:

- Một account dùng nhiều API key hoặc nhiều phiên để tăng tổng lưu lượng.
- Nhiều endpoint tương đương đang nhận các ngân sách độc lập ngoài ý định.
- Batch tăng mạnh nhưng chi phí admission không đổi.
- Tổng chấp nhận tăng theo số instance hoặc vùng phục vụ.
- Nhiều retry cùng key gây tải dù không tạo operation mới.
- Bucket khởi tạo lại bất thường sau TTL, lỗi hoặc thay đổi cấu hình.
- Độ trễ tra cứu, quyết định không rõ kết quả và tỷ lệ fallback tăng.
- Tốc độ thực thi phía worker vượt mục tiêu dù tốc độ nhận job vẫn thấp.

Đối soát cần phân biệt số request được thấy, số lần lấy token, số operation duy nhất, số job được tạo và số lần thực thi. Các đại lượng này không luôn bằng nhau; sự khác biệt phải giải thích được theo chính sách.

Một request bị từ chối không được để lại job hoặc tác dụng phụ mới trái hợp đồng. Ngược lại, response bị mất sau khi operation đã commit không có nghĩa cần tạo thêm một job. Mã liên kết và lịch sử idempotency giúp phân biệt hai trường hợp.

Khi kiểm tra dữ liệu nhiều nguồn, xét mốc quan sát và độ trễ. Không kết luận vượt chỉ từ hai bản sao đọc lệch thời điểm, cũng không dùng độ trễ làm lý do bỏ qua mọi sai lệch kéo dài.

## 13. Các tình huống kiểm thử tấn công logic

Các ca sau là thiết kế kiểm thử cho bài học, chưa phải kết quả chạy trên một hệ thống cụ thể. Cần quan sát cả quyết định admission, trạng thái bucket, operation và tác dụng nghiệp vụ.

| Tình huống | Cách tạo điều kiện | Kết quả cần bảo đảm |
|---|---|---|
| Đổi account qua request | Gửi ID không thuộc quyền người gọi | Không dùng hoặc làm cạn ngân sách account đích trái quyền |
| Đổi API key | Dùng nhiều key hợp lệ của cùng account | Vẫn chia sẻ ngân sách account theo chính sách |
| Nhiều user trong tổ chức | Gửi đồng thời từ các thành viên | Không nhân tổng giới hạn account |
| Đổi endpoint tương đương | Luân phiên các API cùng tạo báo cáo | Không nhận ngân sách mới chỉ vì đường dẫn khác |
| Batch có nhiều phần tử | Gửi 8 đơn vị khi chỉ còn 5 | Từ chối toàn batch nếu hợp đồng nguyên khối; không tạo phần công việc trước |
| Sửa trọng số | Gửi `cost: 0` hoặc cờ nội bộ | Dùng chi phí máy chủ và quyền hợp lệ |
| Chi phí vượt capacity | Gửi `c > B` | Phản hồi không thể nhận theo chính sách, không retry chờ vô hạn |
| Tranh token cuối | Hai luồng cùng cần token cuối cùng | Chỉ một admission được chấp nhận |
| Nhiều instance | Phân phối request cùng account qua nhiều node | Tổng ngân sách đúng mô hình, không bằng hạn mức nhân số node |
| Ranh giới cửa sổ | Gửi sát trước và sau mốc phút | Kết quả khớp mô hình đã chọn, không nhầm fixed window với rolling window |
| Clock lùi hoặc nhảy | Điều khiển nguồn thời gian kiểm thử | Không refill trùng khoảng; xử lý sai lệch theo thiết kế |
| TTL xóa sớm | Làm mất state trước lúc đáng lẽ bucket đầy | Không tự tạo thêm burst ngoài quy tắc |
| Retry mất response | Commit job rồi ngắt response và gửi lại key | Không tạo job hoặc thu phí lần hai |
| Phát lại liên tục cùng key | Gửi nhiều retry của operation cũ | Ngân sách số lần gọi vẫn kiểm soát tải |
| Nhiều bucket cùng áp dụng | Account đủ nhưng ngân sách khác thiếu | Không tạo công việc; tác động counter đúng semantics đã chọn |
| Lỗi nguồn rate limit | Ngắt kết nối nguồn trạng thái | Không tự chuyển thành nhiều bucket đầy ngoài chính sách |
| Đổi phiên bản cấu hình | Triển khai policy mới khi bucket cạn | Không reset đầy ngoài quyết định được phép |
| Phát lại cấu hình cũ | Giao sự kiện phiên bản cũ sau bản mới | Không hạ cơ chế bảo vệ bằng cấu hình lỗi thời |
| Worker xử lý dồn | Tích lũy queue rồi bật nhiều worker | Chính sách tốc độ thực thi được giữ nếu sản phẩm yêu cầu |

Kiểm thử cạnh tranh cần điểm đồng bộ để các request thực sự chồng lấn tại quyết định. Kiểm thử refill và ranh giới nên dùng đồng hồ điều khiển được, không dựa vào `sleep` và hy vọng lịch chạy tạo đúng điều kiện.

Với nơi lưu dùng chung, kiểm thử tích hợp trên cơ chế nguyên tử thực tế có giá trị hơn mock luôn xử lý tuần tự. Với nhiều vùng, cần kiểm tra cả phân vùng mạng, chuyển ngân sách, khởi động lại và trạng thái đã cấp phép nhưng chưa rõ kết quả.

## 14. Bài tập áp dụng và tiêu chí thiết kế

Một account A có hai API key K1, K2 cùng dùng token bucket:

```text
Nhóm: REPORT_CREATE
Capacity B = 10 token
Refill r = 2 token/giây
Báo cáo chuẩn tốn 1 token
Báo cáo nặng tốn 5 token
Bucket ban đầu đầy
```

Xét các tình huống:

1. Tại cùng một thời điểm, K1 gửi 7 báo cáo chuẩn và K2 gửi 7 báo cáo chuẩn.
2. Sau khi bucket cạn, không có request khác và thời gian tiến thêm đúng 0,5 giây.
3. Bucket hiện có 4 token, client gửi một batch nguyên khối gồm một báo cáo nặng.
4. Một operation tạo báo cáo nặng đã được nhận nhưng response bị mất; client retry đúng key.
5. Đội vận hành thêm một instance hoặc đổi phiên bản policy trong lúc bucket cạn.

Ở tình huống 1, nếu mọi request đơn vị có cùng thời điểm tính refill và không có token bổ sung trong khoảng kiểm thử, tổng số được chấp nhận không vượt 10. Việc phân chia kết quả giữa K1 và K2 phụ thuộc thứ tự phân xử và chính sách công bằng, nhưng không được là 7 cộng 7.

Ở tình huống 2, bucket có thể phục hồi 1 token theo mô hình và độ chính xác đã định. Không được cho thêm 10 chỉ vì một phiên đăng nhập hoặc API key mới xuất hiện.

Ở tình huống 3, chi phí là 5 nên batch chưa được nhận. Với tốc độ 2 token/giây, thiếu 1 token tương ứng khoảng chờ lý thuyết 0,5 giây; hướng dẫn trả về cần làm tròn theo đơn vị giao thức và không hứa giữ chỗ.

Ở tình huống 4, operation không được thực hiện lần hai. Retry có thể vẫn bị tính vào ngân sách số lần gọi; việc trả lại kết quả cũ không phải một job nặng mới để tiếp tục trừ ngân sách công việc theo mô hình đếm operation duy nhất.

Ở tình huống 5, số instance và tên phiên bản không tự tạo ngân sách. Trạng thái cần được chia sẻ hoặc chuyển đổi đúng quy tắc đã chọn.

Một thiết kế có thể được đánh giá bằng chuỗi câu hỏi:

```text
Account nào có thẩm quyền và ai được dùng ngân sách của nó?
    -> Những key, user và đường vào nào cùng chia sẻ chính sách?
    -> Đang đếm request, cơ hội admission hay công việc duy nhất?
    -> Mô hình burst, refill, cửa sổ và trọng số là gì?
    -> Quyết định đồng thời được phân xử nguyên tử ở đâu?
    -> Retry và nhiều lớp giới hạn phối hợp theo semantics nào?
    -> Lỗi, TTL, nhiều vùng và đổi cấu hình có thể cấp thêm ngân sách không?
    -> Bằng chứng nào nối được admission với tác dụng nghiệp vụ?
```

Chính sách tốc độ theo account có hiệu quả khi ngân sách bám đúng chủ thể nghiệp vụ và được thực thi nhất quán trên các đường tạo tác động. Danh tính, chi phí, thời gian, xử lý đồng thời và idempotency phải cùng bảo vệ ý nghĩa đó.
