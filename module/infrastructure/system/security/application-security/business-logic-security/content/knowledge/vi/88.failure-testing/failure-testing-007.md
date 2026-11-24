# Kiểm thử phục hồi và đối soát (Recovery reconciliation test)

Trong chương **Failure Testing** của module bảo vệ logic nghiệp vụ, một tình huống nguy hiểm là hệ thống chỉ hoàn thành một phần công việc: nhà cung cấp đã hoàn tiền nhưng ứng dụng mất phản hồi, transaction đã commit nhưng client nhận timeout, hoặc worker đã gửi lệnh rồi bị dừng trước khi ghi kết quả.

**Recovery reconciliation test** kiểm tra khả năng thu thập lại bằng chứng, xác định công việc thực sự đã xảy ra và đưa dữ liệu về trạng thái phù hợp với sự thật nghiệp vụ. Quá trình phục hồi phải giữ business invariants, quyền theo đối tượng, state machine, transaction và idempotency; không được biến sự thiếu thông tin thành lý do tạo thêm hiệu ứng tài chính.

Bài học dùng luồng hoàn tiền làm ví dụ vì nó thể hiện rõ lỗi một phần và hậu quả của retry sai. Các trạng thái, số tiền, định danh và adapter đều là mô hình tổng hợp cho môi trường kiểm thử, không phải quy định bắt buộc của mọi hệ thống thanh toán.

## 1. Phân biệt phục hồi, đối soát, retry và bù trừ

### 1.1. Mỗi hoạt động trả lời một câu hỏi khác nhau

| Hoạt động | Câu hỏi chính | Ví dụ |
|---|---|---|
| Recovery | Làm thế nào tiếp tục hoặc kết thúc an toàn công việc bị gián đoạn? | Worker chạy lại công việc đã commit sau restart |
| Reconciliation | Các nguồn dữ liệu có khớp nhau về cùng một nghiệp vụ không? | So sánh refund intent, provider transaction và posting nội bộ |
| Retry | Có thử lại một bước theo hợp đồng đã chốt không? | Gửi lại cùng ý định bằng cùng idempotency key còn hiệu lực |
| Compensation | Có thực hiện một nghiệp vụ mới để xử lý hậu quả của nghiệp vụ trước không? | Tạo điều chỉnh được phê duyệt sau một sai lệch đã xác nhận |

Đối soát có thể kết luận chỉ cần ghi nhận kết quả đã xảy ra, không cần gửi thêm lệnh ra ngoài. Bù trừ là một hành động mới có quyền, điều kiện và dấu vết riêng; nó không tự xóa tác động hay lịch sử của giao dịch cũ.

### 1.2. Timeout là thiếu thông tin về kết quả

Xét chuỗi:

```text
Ứng dụng giữ chỗ 40.000 VND
    ↓
Gửi refund intent tới provider
    ↓
Provider hoàn thành công
    ↓
Phản hồi bị mất; ứng dụng còn trạng thái chưa xác định
```

Nếu ứng dụng coi timeout là thất bại cuối cùng, giải phóng giữ chỗ rồi tạo một refund mới, khách có thể được hoàn hai lần. Nếu ứng dụng mãi giữ trạng thái chưa rõ mà không có cơ chế đối soát, tiền hoặc hạn mức có thể bị treo.

Test cần chứng minh cả **an toàn** trong giai đoạn chưa biết và **khả năng kết thúc** khi đã có đủ bằng chứng theo các giả định vận hành được đặc tả. Một thao tác retry nhận `200` chưa đủ chứng minh cả hai điều đó.

## 2. Đặc tả hợp đồng phục hồi trước khi tiêm lỗi

### 2.1. Danh tính nghiệp vụ phải sống qua restart

Một ý định hoàn tiền cần có định danh bền vững, nội dung đã chấp nhận và liên kết với giao dịch gốc:

```text
tenant + order + refundIntent
    ├─ actor và quyết định được phép ban đầu
    ├─ amount + currency + policy/snapshot liên quan
    ├─ idempotency scope/key hoặc business reference
    ├─ các lần thử xử lý
    └─ provider transaction khi đã xác định
```

Một attempt mới không được tự biến thành một ý định tiền mới. Provider reference phải có đủ phạm vi, chẳng hạn provider và merchant account, nếu transaction ID chỉ duy nhất trong phạm vi đó.

Đừng dùng `traceId` làm danh tính duy nhất của nghiệp vụ: retry hoặc callback thường có trace khác. Cũng không nên tìm giao dịch chỉ bằng amount và thời gian gần nhau; nhiều giao dịch hợp lệ có thể giống các thuộc tính ấy.

### 2.2. Trạng thái cần biểu diễn sự chưa xác định

Mô hình tối giản có thể dùng:

| Trạng thái | Ý nghĩa và điều kiện |
|---|---|
| `PENDING` | Ý định được chấp nhận, tiền đang giữ chỗ; kết quả cuối chưa được ghi nhận |
| `SUCCEEDED` | Có bằng chứng thành công phù hợp và ghi nhận nội bộ tương ứng |
| `FAILED_FINAL` | Đã xác nhận thất bại cuối cùng theo hợp đồng; không còn hiệu ứng tiền phải ghi nhận và giữ chỗ đã được xử lý |
| Cờ/công việc `REVIEW` | Có mâu thuẫn hoặc thiếu điều kiện để tự sửa; cần quy trình ngoại lệ |

`REVIEW` có thể là một hàng đợi hoặc cờ riêng, không nhất thiết là một trạng thái thay thế toàn bộ state machine. Nó phải giữ được thông tin đang có và phạm vi rủi ro, thay vì xóa trạng thái tài chính gốc.

Các hệ thống thực có thể tách `RESERVED`, `SENT`, `UNKNOWN`, `SETTLED` hoặc nhiều trạng thái khác. Oracle phải dựa vào mô hình thật, bao gồm những bước nào commit nguyên tử và những bước nào cho phép trạng thái trung gian.

### 2.3. Các bất biến cần giữ trong và sau phục hồi

Gọi `R` là tổng tiền được phép hoàn, `F` là khoản đã hoàn thành công và `P` là tiền đang giữ chỗ:

```text
F >= 0
P >= 0
F + P <= R
```

Các quy tắc bổ sung thường cần có:

- Một ý định chỉ tạo số hiệu ứng tiền được hợp đồng cho phép; ví dụ một khoản hoàn cho một refund intent trong mô hình này.
- Amount, currency, tenant, order và nguồn thu phải khớp dữ liệu có thẩm quyền đã được chấp nhận.
- Một giao dịch provider không được ghi nhận thành hai khoản hoàn nội bộ độc lập ngoài thiết kế.
- Chuyển giữ chỗ sang đã hoàn không đếm cùng số tiền hai lần hoặc làm biến mất khoản đã sử dụng.
- Retry, callback và job phục hồi không kéo trạng thái thành công lùi lại theo một sự kiện cũ.
- Mọi sửa dữ liệu phải có nguồn bằng chứng và dấu vết; không xóa posting để làm số tổng trông cân bằng.
- Công cụ phục hồi không được vượt tenant hoặc tự cấp quyền thực hiện nghiệp vụ mới.

Với `R = 100.000`, `F = 30.000`, `P = 40.000`, phần còn lại là 30.000 VND. Khi provider xác nhận khoản 40.000 đã hoàn, kết quả mong đợi là `F = 70.000`, `P = 0`; phần còn lại vẫn 30.000. Không được giải phóng giữ chỗ thành 70.000 khả dụng trước khi ghi nhận khoản đã hoàn.

## 3. Tiêm lỗi vào đúng ranh giới cần chứng minh

### 3.1. Ma trận điểm gián đoạn

| Điểm lỗi | Điều cần quan sát khi phục hồi |
|---|---|
| Trước commit ý định/giữ chỗ | Không có công việc bên ngoài được coi là đã chấp nhận nếu transaction rollback |
| Commit đã xảy ra nhưng phản hồi database/client bị mất | Tra cứu lại bằng business identity, không tạo ý định thay thế chỉ vì timeout |
| Sau commit giữ chỗ và outbox, trước dispatch | Worker sau restart tìm lại được công việc bền vững |
| Sau gửi lệnh, trước khi biết provider có nhận hay chưa | Kết quả chưa rõ được giữ đúng, không giải phóng tiền hoặc tạo key mới tùy tiện |
| Provider thành công, phản hồi bị mất | Đối soát tìm đúng giao dịch cũ, không hoàn thêm |
| Provider thành công, commit ghi nhận local thất bại | Lần phục hồi ghi nhận kết quả có tính idempotent |
| Đã commit thành công local nhưng chưa ACK message | Delivery lại không tạo posting hoặc hiệu ứng tiền trùng |
| Job đối soát bị dừng giữa một batch | Chạy tiếp không bỏ sót record và không áp dụng lại trái phép |
| Snapshot/backup local cũ được phục hồi theo kịch bản test | Đối soát không dùng outbox cũ để gửi lại hiệu ứng đã tồn tại bên ngoài |

Mỗi điểm lỗi cần tín hiệu cho biết test thực sự đã đi qua mốc đó. Một exception được ném trước khi gọi provider không kiểm tra được trường hợp provider thành công nhưng ứng dụng mất phản hồi.

### 3.2. Mô phỏng cả thành công ngoài ứng dụng và sự mất phản hồi

Fake provider nên giữ trạng thái bền vững trong phạm vi kịch bản test, có thể:

- Nhận cùng business reference nhiều lần theo semantics idempotency của hợp đồng.
- Ghi giao dịch thành công rồi trả timeout cho caller.
- Cho truy vấn trả kết quả chưa có hiệu lực quan sát ngay, nếu hợp đồng có độ trễ đó.
- Giao callback trùng hoặc đảo thứ tự.
- Phân biệt từ chối cuối cùng với kết quả chưa rõ.

Một mock chỉ ném timeout rồi không lưu gì không đủ mô phỏng hiệu ứng đã xảy ra. Với kịch bản khôi phục database local, fake provider phải giữ phần lịch sử bên ngoài cần kiểm tra; reset cả hai nguồn về trạng thái trống sẽ làm mất điều kiện sai lệch.

## 4. Thu thập bằng chứng và chọn nguồn có thẩm quyền

### 4.1. Nguồn nào quyết định điều gì?

| Nguồn | Thông tin có thẩm quyền trong phạm vi hợp đồng | Điều không nên tự suy ra |
|---|---|---|
| Refund intent/snapshot đã chấp nhận | Amount được duyệt, currency, order, tenant và ngữ cảnh nghiệp vụ | Chưa chứng minh tiền đã thực sự đi ra |
| Provider và báo cáo/tra cứu phù hợp | Giao dịch bên ngoài, trạng thái, amount/currency của giao dịch ấy | Thành công không chứng minh lệnh ban đầu được cấp quyền đúng |
| Posting/sổ nội bộ | Cách ứng dụng đã ghi nhận hiệu ứng | Không chứng minh provider không có khoản ngoài sổ |
| Outbox/inbox/attempt history | Công việc đã commit, sự kiện tiếp nhận và các lần thử | `SENT` hoặc ACK không tự là bằng chứng hoàn tiền thành công |
| Workload journal/audit test | Điều đã gửi và điểm lỗi được kích hoạt | Timeout phía client không chứng minh rollback |

Provider là nguồn bằng chứng về hiệu ứng mà nó đã thực hiện; nó không thay thế chính sách về khoản nào được phép hoàn. Nếu provider cho thấy amount khác khoản được duyệt, cần xử lý sai lệch chứ không sửa snapshot được duyệt cho khớp một cách âm thầm.

### 4.2. `NOT_FOUND` cần được diễn giải theo hợp đồng tra cứu

Không tìm thấy giao dịch có thể do truy vấn sai merchant account, sai reference, nguồn đọc bị trễ, cửa sổ lưu lịch sử hoặc hệ thống ngoài chưa cập nhật. Một lần nhận `404` hoặc kết quả rỗng không tự chứng minh chưa có hiệu ứng và có thể an toàn gửi lệnh mới.

Muốn retry tự động phải xác định semantics tra cứu, khả năng lệnh cũ còn được xử lý, phạm vi/thời hạn idempotency và cách liên kết lại cùng ý định. Nếu chưa đủ điều kiện, giữ kết quả chưa rõ, lập lịch tra cứu tiếp hoặc chuyển ngoại lệ theo chính sách.

Nếu idempotency key bên ngoài đã hết thời gian bảo vệ, gửi lại cùng chuỗi key có thể không còn mang ý nghĩa cũ. Test phục hồi sau gián đoạn dài cần có ca này; không coi “key không đổi” là bằng chứng đủ về an toàn.

### 4.3. Chọn mốc chốt và snapshot đủ nhất quán

Đọc trạng thái intent, giữ chỗ và posting từ các thời điểm khác nhau có thể tạo một tổ hợp chưa từng tồn tại. Dùng semantics snapshot phù hợp cho kiểm tra nội bộ; nêu rõ độ trễ replica nếu đọc từ nguồn đó.

Giữa database và provider thường không có một transaction đọc chung. Đối soát cần theo dõi các intent tới mốc đủ tin cậy, hoặc dùng watermark/cửa sổ theo hợp đồng. Ghi thời điểm truy vấn, nguồn bằng chứng và phiên bản dữ liệu để biết một quyết định có còn áp dụng được khi thực thi hay không.

## 5. Xây bảng quyết định phục hồi

| Local và bằng chứng bên ngoài | Hành động thích hợp theo mô hình minh họa |
|---|---|
| `PENDING`, provider thành công cuối cùng, đúng identity/amount/currency | Ghi nhận thành công local và chuyển giữ chỗ trong transaction; không gửi lại lệnh hoàn |
| `PENDING`, provider xác nhận thất bại cuối cùng cho đúng ý định | Kết thúc thất bại và giải phóng giữ chỗ đúng một lần |
| `PENDING`, provider vẫn xử lý hoặc chưa có bằng chứng đủ | Giữ trạng thái chưa kết thúc và phần giữ chỗ theo chính sách, tiếp tục đối soát |
| `SUCCEEDED`, giao dịch provider khớp, posting và giữ chỗ đúng | Không tạo hiệu ứng mới; xác minh và ghi dấu kiểm tra nếu cần |
| `FAILED_FINAL`, provider xác nhận thất bại cuối cùng, không còn hiệu ứng/giữ chỗ | Không tạo nghiệp vụ tiền mới |
| Local terminal mâu thuẫn với kết quả provider đã xác nhận | Đưa vào luồng ngoại lệ; giữ dấu vết và ngăn retry mù |
| Giao dịch provider sai tenant/merchant/reference hoặc amount/currency | Không tự gắn hay ghi nhận cho intent đang xét; điều tra sai lệch |
| Nhiều giao dịch thành công cho một intent chỉ được phép một khoản hoàn | Ghi nhận sự cố trùng hiệu ứng; không che bằng cách chỉ lấy giao dịch mới nhất |
| Provider transaction không liên kết được với ý định hợp lệ | Đối soát danh tính và nguồn gốc; không tự tạo ý định giả để làm đủ cặp |

Bảng này phân biệt **ghi lại sự thật đã xác nhận** với **tạo một tác động mới**. Nếu cần bù trừ hoặc điều chỉnh sổ, đó là quy trình có thẩm quyền và audit riêng, với test về giới hạn, người phê duyệt và idempotency tương ứng.

## 6. Thiết kế oracle: bằng chứng nào làm test đạt hoặc trượt?

Oracle là tập quy tắc dùng để xác định kết quả đúng của test. Với phục hồi, oracle cần xét cả dữ liệu nội bộ và hiệu ứng bên ngoài, cùng điều kiện mà hệ thống phải hội tụ. Chỉ kiểm tra trạng thái cuối `SUCCEEDED` sẽ bỏ qua khả năng hoàn tiền hai lần hoặc ghi sổ thiếu.

### 6.1. Chuẩn bị dữ liệu có thể đối chiếu độc lập

Dùng một bộ dữ liệu xác định trước:

```text
tenant:              tenant-A
merchant account:    merchant-A
order:               order-42
refund intent:       refund-17
amount được duyệt:   40.000 VND
giới hạn hoàn R:     100.000 VND
đã hoàn trước đó F:  30.000 VND
giữ chỗ ban đầu P:   0 VND
business reference:  tenant-A/order-42/refund-17
```

Lưu amount bằng biểu diễn chính xác theo đơn vị tiền đã thống nhất; không dùng số thực dấu phẩy động để so tiền. Fixture phải tạo khoản đã hoàn 30.000 với dữ liệu tương ứng mà oracle cần kiểm tra, không chỉ gán một biến tổng.

Khi chấp nhận `refund-17`, giữ chỗ tăng lên 40.000; sau khi xác nhận thành công, giữ chỗ trở về 0 và tổng đã hoàn tăng thành 70.000. Khoản khả dụng để hoàn thêm là 30.000 ở cả hai thời điểm đó. Các con số này được xác định từ kịch bản đã duyệt, không lấy trạng thái cuối của ứng dụng làm kỳ vọng cho chính ứng dụng.

### 6.2. Kiểm tra theo từng lớp

| Lớp kiểm tra | Bằng chứng cần đọc | Điều kiện đạt của kịch bản thành công này |
|---|---|---|
| Quyết định nghiệp vụ | Intent và snapshot đã được duyệt | Vẫn đúng tenant, order, amount, currency và danh tính ý định |
| Hiệu ứng bên ngoài | Lịch sử giao dịch thực tế của fake provider hoặc sandbox phù hợp | Chỉ một khoản hoàn thành công 40.000 cho đúng ý định |
| Ghi nhận nội bộ | Nhóm posting/ledger entry theo thiết kế | Chỉ một lần ghi nhận hiệu ứng hoàn của `refund-17`, amount đúng |
| Hạn mức | Giữ chỗ và tổng đã hoàn | `F = 70.000`, `P = 0`, còn được hoàn 30.000 |
| State machine | Intent, phiên bản và lịch sử chuyển trạng thái | Kết thúc `SUCCEEDED`, sự kiện cũ không kéo lùi trạng thái |
| Công việc bền vững | Outbox, inbox, retry/reconciliation work item | Công việc đã được xác nhận xử lý hoặc còn lịch xử lý hợp lệ; không thất lạc |
| Truy vết | Quyết định đối soát và nguồn bằng chứng | Giải thích được ai/cơ chế nào đã sửa, dựa vào giao dịch nào |

Một lần ghi nhận hiệu ứng có thể gồm nhiều dòng debit/credit. Vì vậy, hãy đếm **nhóm posting nghiệp vụ** theo mô hình sổ thay vì khẳng định mọi hệ thống chỉ có đúng một dòng ledger.

Số request gửi tới provider cũng khác số hiệu ứng tiền. Nhiều request cùng danh tính có thể là hợp lệ trong hợp đồng idempotency. Oracle cần đếm giao dịch thực sự thành công và kiểm tra danh tính/nội dung của từng request; riêng bước đối soát chỉ ghi nhận một kết quả đã biết thì không được phát sinh thêm lệnh hoàn.

### 6.3. Phân biệt an toàn trong lúc chạy và hội tụ sau lỗi

**An toàn** phải được giữ ở các mốc quan sát được: chưa rõ kết quả thì không giải phóng giữ chỗ sai; không vượt hạn mức; không ghi nhận trùng; không sửa đối tượng khác tenant. Với một bước được thiết kế nguyên tử, kiểm tra trạng thái đã commit trước/sau transaction thay vì coi các phép gán tạm bên trong transaction là dữ liệu đã công bố.

**Hội tụ** cần điều kiện rõ ràng, ví dụ: provider đã cho tra cứu kết quả cuối, database hoạt động, worker được cấp lượt chạy, retry chưa hết ngân sách và không có tranh chấp mới làm thay đổi kịch bản. Trong môi trường kiểm thử xác định, có thể yêu cầu kết thúc trong tối đa năm lượt xử lý sau khi các điều kiện ấy đúng. Con số năm là ngân sách của test minh họa, không phải cam kết chung cho production.

Nếu provider tiếp tục không thể xác định kết quả, kết thúc test có thể là `PENDING` kèm giữ chỗ, lịch xử lý tiếp và dấu cảnh báo đúng chính sách. Chỉ chuyển sang `REVIEW` không làm biến mất nghĩa vụ tài chính còn chưa biết. Test cần xác minh record ngoại lệ tồn tại và có thông tin xử lý, không chỉ thấy job đã thoát mà coi là đạt.

## 7. Kịch bản chủ đạo: provider thành công rồi worker mất phản hồi

### 7.1. Tiến trình có điểm dừng kiểm soát

```text
1. Chấp nhận refund-17 và commit giữ chỗ + công việc gửi lệnh.
2. Worker gửi lệnh với business identity và idempotency key đã lưu.
3. Fake provider ghi thành công một giao dịch 40.000 VND.
4. Chặn/mất phản hồi trước khi ứng dụng ghi nhận thành công.
5. Dừng worker; giữ nguyên database và lịch sử fake provider.
6. Khởi động worker mới chỉ với dữ liệu bền vững.
7. Cho tra cứu provider nhìn thấy kết quả đã thành công.
8. Chạy đối soát: kiểm tra bằng chứng rồi commit ghi nhận local.
9. Giao lại message/callback và chạy đối soát thêm nhiều lần.
10. Kiểm tra toàn bộ oracle, gồm cả hiệu ứng tiền bên ngoài.
```

Ở bước 4, phải chứng minh provider đã ghi giao dịch trước khi tạo timeout hoặc dừng tiến trình. Có thể dùng barrier/latch do test harness điều khiển: provider báo đã commit, test xác nhận mốc ấy, sau đó mới làm mất phản hồi. Chờ một khoảng thời gian tùy ý rồi kill worker dễ tạo một test lúc đi qua điểm lỗi, lúc chưa đi qua.

Khởi động lại phải làm mất cache, lock trong bộ nhớ và các biến tiến trình của worker cũ. Một test chỉ tạo lại service object nhưng vô tình dùng chung bộ nhớ chứa kết quả thành công chưa chứng minh được phục hồi từ dữ liệu bền vững.

### 7.2. Mã giả phong cách Java cho test harness

Đoạn sau mô tả giao thức test, không phải mã chạy độc lập. Các hàm `harness`, `provider`, `assertThat` và fixture cần được hiện thực bằng hạ tầng kiểm thử của dự án. Đồng hồ test được điều khiển để không phải chờ backoff thực.

```java
void recoversProviderSuccessWithoutAnotherRefund() {
    var fixture = fixtures.approvedRefund(
        "tenant-A", "merchant-A", "order-42", "refund-17",
        100_000L, 30_000L, 40_000L, "VND"
    );

    // Chính sách này chỉ áp dụng cho lệnh hoàn của refund-17.
    // Provider lưu giao dịch trước, rồi adapter làm mất phản hồi.
    provider.forReference(fixture.businessReference())
            .commitSuccessThenLoseReply();

    harness.acceptApprovedIntent(fixture);
    assertThat(harness.reservedAmount(fixture.order())).isEqualTo(40_000L);

    harness.dispatchUntilProviderCommittedThenStopWorker();

    // Kiểm tra điều kiện tạo lỗi, trước khi bắt đầu phục hồi.
    assertThat(provider.successfulRefundCount(fixture.businessReference()))
            .isEqualTo(1);
    assertThat(harness.intentState(fixture.intent())).isEqualTo(PENDING);
    assertThat(harness.refundPostingGroupCount(fixture.intent()))
            .isEqualTo(0);
    assertThat(harness.reservedAmount(fixture.order())).isEqualTo(40_000L);

    harness.startFreshWorkerWithSameDurableStores();
    provider.makeCommittedResultVisibleToLookup(fixture.businessReference());
    long commandsBeforeReconciliation = provider.refundCommandCount();

    // Mỗi lượt tiến đồng hồ tới lúc công việc đến hạn rồi chạy worker.
    harness.runDueReconciliationUntilTerminal(fixture.intent(), 5);

    assertThat(harness.intentState(fixture.intent())).isEqualTo(SUCCEEDED);
    assertThat(harness.refundPostingGroupCount(fixture.intent()))
            .isEqualTo(1);
    assertThat(harness.refundPostingAmount(fixture.intent())).isEqualTo(40_000L);
    assertThat(harness.totalRefunded(fixture.order())).isEqualTo(70_000L);
    assertThat(harness.reservedAmount(fixture.order())).isEqualTo(0L);
    assertThat(harness.remainingRefundable(fixture.order())).isEqualTo(30_000L);
    assertThat(provider.refundCommandCount())
            .isEqualTo(commandsBeforeReconciliation);

    harness.redeliverOriginalMessage(fixture.intent());
    harness.deliverVerifiedSuccessCallbackTwice(fixture.intent());
    harness.runReconciliationAgain(fixture.intent());

    assertThat(provider.successfulRefundCount(fixture.businessReference()))
            .isEqualTo(1);
    assertThat(harness.refundPostingGroupCount(fixture.intent()))
            .isEqualTo(1);
    harness.assertAcceptedIdentityAndAmountsUnchanged(fixture);
    harness.assertNoOutstandingReservation(fixture.intent());
    harness.assertRecoveryDecisionHasEvidence(fixture.intent());
}
```

Các assertion trước restart giúp tránh test đạt giả do chưa gửi được lệnh hoặc do local đã hoàn tất trước khi lỗi được kích hoạt. Assertion sau khi giao lại sự kiện chứng minh tính ổn định của kết quả khi xử lý lặp.

Sau lượt reconciliation đầu tiên, nên đọc đồng thời bộ dữ liệu nội bộ bằng snapshot phù hợp để kiểm tra trạng thái và số tổng. Nếu pipeline ghi sổ có bước bất đồng bộ được đặc tả riêng, thay các assertion tức thời bằng điều kiện chờ có hạn cho từng mốc; vẫn kiểm tra bất biến an toàn trong giai đoạn chuyển tiếp ấy.

### 7.3. Biến thể cần tách thành test riêng

- Provider xác nhận thất bại cuối cùng: không có giao dịch hoàn thành công, không có posting hoàn thành công, giữ chỗ được giải phóng đúng một lần.
- Provider đang xử lý: giữ trạng thái chưa kết thúc và không gửi một ý định thay thế; sau khi có kết quả cuối, hệ thống tiếp tục đúng nhánh.
- Provider thành công nhưng transaction ghi nhận local rollback: chạy lại dùng cùng bằng chứng, không ghi nhận một nửa và không tạo khoản hoàn mới.
- Commit local thành công nhưng worker mất xác nhận commit: đọc lại trạng thái bền vững trước khi quyết định hành động; không dựa duy nhất vào exception.
- Lookup chưa thấy kết quả rồi mới thấy thành công: không giải phóng tiền hoặc tạo key mới trong khoảng trống quan sát.
- Lệnh cũ còn đang xử lý khi lookup trả rỗng: test phải mô phỏng lệnh ấy có thể thành công sau đó, tránh giả định rỗng đồng nghĩa an toàn gửi mới.

## 8. Chạy đồng thời: callback, retry và đối soát cùng sửa một ý định

### 8.1. Tạo cuộc đua tại bước áp dụng quyết định

Cho worker đối soát A, worker đối soát B và callback handler cùng nhìn thấy `PENDING` và cùng có bằng chứng thành công. Dừng tất cả trước bước ghi, rồi cho chúng tiếp tục theo các thứ tự khác nhau.

Kết quả cần đạt:

- Chỉ một lần chuyển giữ chỗ sang khoản đã hoàn cho intent.
- Một nhóm posting nghiệp vụ hợp lệ; các đường chạy còn lại nhận ra kết quả đã áp dụng.
- Không âm giữ chỗ, không tăng tổng tiền hai hoặc ba lần.
- Không có đường xử lý bỏ qua kiểm tra tenant, merchant account, identity, amount và currency chỉ vì một đường khác đã kiểm tra trước đó.
- Sự kiện cũ về trạng thái đang xử lý không ghi đè thành công đã xác nhận.

Khóa hàng hoặc cập nhật có điều kiện theo version có thể bảo vệ thay đổi nội bộ. Ràng buộc duy nhất theo định danh nghiệp vụ và phạm vi provider transaction giúp ngăn ghi nhận trùng ở cấp database. Mỗi cơ chế phải được kiểm tra trên phạm vi dữ liệu mà nó thật sự bảo vệ; một unique key trên posting không tự ngăn hai lệnh ngoài ứng dụng tạo hai giao dịch tiền.

### 8.2. Quyết định đọc trước đó có thể đã hết hiệu lực

Ví dụ A đọc intent ở version 7 rồi đi tra cứu provider. Trong lúc đó, callback B đã ghi nhận thành công và chuyển intent lên version 8. Khi A quay lại, nó phải kiểm tra lại điều kiện áp dụng trong transaction hoặc dùng version để phát hiện dữ liệu đã đổi.

Mã giả cho bước ghi nhận có thể có dạng:

```text
bằng_chứng = tra_cứu_provider(identity_đã_lưu)
xác_minh_nguồn_và_các_thuộc_tính(bằng_chứng)

BEGIN TRANSACTION
    đọc_và_khóa_intent_cùng_dữ_liệu_hạn_mức_cần_thiết()
    kiểm_tra_lại_tenant_identity_amount_currency_và_điều_kiện_áp_dụng()

    nếu kết_quả_này_đã_được_áp_dụng_hợp_lệ:
        không_tạo_posting_hoặc_hiệu_ứng_mới()
    ngược_lại_nếu trạng_thái_hiện_tại_cho_phép_ghi_nhận:
        ghi_nhóm_posting_với_ràng_buộc_danh_tính()
        chuyển_giữ_chỗ_sang_đã_hoàn()
        cập_nhật_trạng_thái_và_dấu_vết_quyết_định()
    ngược_lại:
        ghi_nhận_ngoại_lệ_theo_chính_sách()
COMMIT
```

Đây là mô hình khi các thay đổi nội bộ trên nằm trong cùng database transaction. Nếu sổ tiền là một dịch vụ riêng, cần đặc tả riêng giao thức chuyển tiếp, công việc bền vững và oracle cho từng phía; không thể gọi transaction local là nguyên tử trên cả hai dịch vụ.

Không giữ database transaction mở trong suốt cuộc gọi mạng chỉ để làm sơ đồ trông tuần tự. Đặt lời gọi ngoài transaction tạo ra khoảng thời gian có thể tranh chấp; test phải chứng minh cách kiểm tra lại và hợp đồng idempotency xử lý khoảng đó.

### 8.3. Worker cũ tiếp tục chạy sau khi mất quyền giữ công việc

Cho A lấy lease rồi bị treo; lease hết hạn, B tiếp quản; sau đó A chạy tiếp. Test kiểm tra worker cũ không ghi đè kết quả mới hoặc đánh dấu hoàn tất một công việc mà nó không còn quyền cập nhật.

Token phiên bản/fencing chỉ bảo vệ được tài nguyên thực sự kiểm tra token ấy. Provider không hiểu token nội bộ sẽ không tự từ chối lệnh của worker cũ. Bởi vậy, chống trùng hiệu ứng bên ngoài vẫn cần danh tính nghiệp vụ và hợp đồng provider phù hợp; lease một mình không chứng minh an toàn tài chính.

## 9. Đối soát theo batch và phục hồi từ backup

### 9.1. Không để checkpoint che mất record chưa xử lý

Tạo batch gồm nhiều intent: có intent đã khớp, intent cần ghi nhận, intent cần tra cứu lại và một record lỗi dữ liệu. Dừng job tại các điểm trước/sau commit sửa từng intent, trước/sau cập nhật checkpoint và trước ACK công việc.

Sau restart, kiểm tra **mọi identity trong tập dữ liệu kỳ vọng**, thay vì chỉ so số lượng bản ghi đã xử lý. Hai lần đếm cùng một intent có thể bù cho một intent bị bỏ sót nếu oracle chỉ nhìn tổng.

Checkpoint không được làm record chưa xử lý biến mất khỏi phạm vi chạy tiếp. Nếu tiến checkpoint qua một record đang chờ, phải còn work item bền vững để quay lại record đó. Khi xử lý lặp do crash trước checkpoint, thao tác áp dụng phải idempotent. Dữ liệu sửa và checkpoint ở các hệ lưu trữ khác nhau cần cơ chế bảo đảm không mất công việc đã đặc tả; không giả định chúng cùng commit.

Cũng cần kiểm tra các tình huống:

- Một record lỗi không ngăn tất cả record còn lại tiến triển; record lỗi được lưu vào luồng ngoại lệ có đủ identity và nguyên nhân.
- Cursor có thứ tự ổn định và cách xử lý record mới hoặc record cập nhật được mô tả rõ. Quét theo timestamp thay đổi mà không có tie-breaker/cơ chế quét bù có thể bỏ sót hoặc lặp ngoài ý muốn.
- Hết rate limit hoặc mất mạng không biến thành đánh dấu đã đối soát thành công.
- Chạy chồng hai batch không áp dụng cùng sai lệch hai lần.
- Hết số lần retry không làm công việc biến mất; có trạng thái xử lý tiếp hoặc ngoại lệ bền vững theo chính sách.

### 9.2. Khôi phục database local không khôi phục được thời gian bên ngoài

Kịch bản phục hồi backup cần ba mốc rõ ràng:

```text
t0: Tạo backup local; refund-17 chưa tồn tại trong backup.
t1: Hệ thống thật chấp nhận refund-17; provider hoàn thành 40.000.
t2: Khôi phục local về t0; provider vẫn giữ giao dịch của t1.
```

Nếu chỉ quét các intent `PENDING` trong database đã phục hồi, job sẽ không tìm được `refund-17`. Test phải kiểm tra khả năng phát hiện giao dịch ngoài sổ từ phía provider, báo cáo giao dịch hoặc một nhật ký bền vững độc lập theo thiết kế.

Đối soát vì vậy cần xét hai chiều: **local → provider** để xác nhận các ý định đã biết, và **provider → local** để tìm hiệu ứng không còn cặp tương ứng. Cửa sổ quét bù phải bao phủ khoảng dữ liệu có thể mất và độ trễ công bố mà hợp đồng yêu cầu. Không tái sử dụng một watermark mới hơn dữ liệu đã khôi phục mà không có cơ chế quét lại phù hợp.

Một biến thể khác là backup có intent và outbox chưa gửi, nhưng provider đã xử lý nó sau thời điểm backup. Khi khôi phục, outbox có thể được phát lại. Test cần chứng minh replay không tạo thêm khoản hoàn, kể cả khi thời gian gián đoạn dài hơn thời hạn bảo vệ idempotency bên ngoài. Nếu thiết kế không đủ bằng chứng để tự động bảo đảm, kết quả đúng là chặn gửi lại và chuyển đối soát/ngoại lệ theo chính sách.

Chạy phục hồi backup trong môi trường cô lập, gắn với fake provider hoặc tài khoản sandbox được phép. Dùng dữ liệu tổng hợp; không kết nối một bản backup cũ vào endpoint tiền thật trong kịch bản kiểm thử.

## 10. Kiểm thử lạm dụng đường phục hồi

Đường phục hồi thường chạy bằng service account có quyền rộng. Nó cần khôi phục **ý định đã được chấp nhận hợp lệ**, đồng thời kiểm tra các hạn chế hiện hành mà nghiệp vụ quy định phải áp dụng lúc thực thi. Không dùng thay đổi quyền của actor để phủ nhận một khoản tiền đã thực sự đi ra; cũng không dùng quyết định cũ để hợp thức hóa một lệnh tiền mới.

| Tình huống tấn công logic | Điều phải chứng minh |
|---|---|
| Người dùng tenant B yêu cầu đối soát `refund-17` của tenant A | Kiểm tra quyền theo đối tượng chặn truy cập/thay đổi trái phép, không rò thông tin từ kết quả tra cứu |
| Cùng reference xuất hiện ở hai merchant account | Chỉ dữ liệu đúng phạm vi được gắn vào intent; ID giống nhau không đủ làm bằng chứng |
| Request phục hồi gửi amount/currency khác snapshot đã duyệt | Dữ liệu đầu vào không sửa khoản đã duyệt hoặc tự phát sinh lệnh mới |
| Callback giả, sai chữ ký hoặc sai nguồn theo hợp đồng adapter | Không dùng callback ấy làm căn cứ ghi nhận tiền; áp dụng cơ chế xác thực phù hợp với kênh |
| Callback có chữ ký hợp lệ nhưng sai intent/amount/currency | Vẫn bị chặn hoặc chuyển ngoại lệ; tính xác thực của nguồn không thay thế kiểm tra nội dung |
| Người vận hành bấm phục hồi nhiều lần hoặc gọi hai request đồng thời | Một quyết định được áp dụng theo semantics idempotent; không nhân số hiệu ứng |
| API phục hồi cho nhập tùy ý `SUCCEEDED` hoặc giải phóng giữ chỗ | Không cho bỏ qua bằng chứng, state machine hoặc quyền dành riêng cho xử lý ngoại lệ |
| Retry đổi key để vượt xung đột nội dung | Không biến cùng ý định thành khoản hoàn mới; xung đột được báo và điều tra |
| Báo cáo đối soát chứa nhiều giao dịch thành công cho một ý định | Hiển thị đầy đủ sự cố; không dùng phép gộp/xóa trùng làm mất bằng chứng tiền đã đi ra hai lần |
| Actor ban đầu bị thu hồi quyền sau lúc chấp nhận intent | Hành vi tuân theo hợp đồng đã chốt cho ghi nhận kết quả cũ và cho bước thực thi mới; có test riêng cho hai việc |

Nếu có chức năng sửa thủ công, test phải phân biệt quyền **xem sai lệch**, **áp dụng sửa chữa** và **phê duyệt điều chỉnh** theo mô hình quyền thực tế. Dry run phải tạo được đề xuất có thể kiểm tra mà không phát lệnh tiền hay sửa dữ liệu nghiệp vụ. Audit của lần áp dụng cần giữ identity, lý do, bằng chứng và người/cơ chế thực hiện; không ghi credential hay dữ liệu nhạy cảm không cần thiết.

## 11. Tổ chức bộ test và bằng chứng khi thất bại

### 11.1. Tách phạm vi để biết test chứng minh điều gì

| Phạm vi | Mục tiêu chính | Giới hạn cần nhớ |
|---|---|---|
| Test bảng quyết định | Bao phủ tổ hợp state, bằng chứng, quyền và hành động được phép | Không chứng minh commit, khóa hay crash thực |
| Test tích hợp database và fake provider | Kiểm tra rollback, uniqueness, giữ chỗ, replay và các điểm gián đoạn xác định | Fake chỉ chính xác trong phần hợp đồng được mô hình hóa |
| Test dừng/restart tiến trình | Kiểm tra dữ liệu bền vững và mất trạng thái trong bộ nhớ | Cần chứng minh đã dừng ở đúng mốc lỗi |
| Test adapter với sandbox được phép | Kiểm tra ánh xạ identity, idempotency, lookup và callback theo hợp đồng thật | Không mặc định sandbox tái hiện toàn bộ hành vi hoặc độ trễ production |
| Diễn tập khôi phục backup cô lập | Kiểm tra dữ liệu mất, phát lại outbox, quét bù và giao dịch ngoài sổ | Phải giữ lịch sử bên ngoài độc lập với bản local được phục hồi |

Một bộ test ngắn nên có ít nhất các nhánh: thành công bị mất phản hồi; thất bại cuối cùng; chưa xác định; ghi nhận local rollback; xử lý đồng thời; dữ liệu sai phạm vi; replay sau restart; batch crash; khôi phục mất intent; và gián đoạn vượt thời hạn idempotency đã mô hình hóa.

### 11.2. Lưu đủ dữ liệu để tái hiện

Khi test thất bại, báo cáo nên chứa:

- Identity có phạm vi tenant/merchant và mã kịch bản; dùng định danh tổng hợp hoặc đã che dữ liệu nhạy cảm.
- Điểm tiêm lỗi dự kiến và xác nhận mốc thực sự đã đạt.
- Trạng thái trước lỗi, sau restart và sau từng lượt đối soát liên quan.
- Giao dịch provider, nhóm posting, giữ chỗ, outbox/inbox và checkpoint tương ứng.
- Chuỗi sự kiện/attempt cùng thứ tự do harness điều khiển; seed nếu có phát sinh lịch chạy ngẫu nhiên.
- Oracle bị vi phạm: ví dụ “hai giao dịch thành công cho một intent” thay vì chỉ “expected true”.

Theo dõi tuổi của intent chưa xác định, lượng giữ chỗ còn treo, số sai lệch, số giao dịch ngoài sổ và số ngoại lệ quá hạn giúp kiểm tra khả năng quan sát. Các chỉ số tổng hợp hỗ trợ phát hiện vấn đề; chúng không thay thế kiểm tra theo identity vì nhiều sai lệch có thể bù nhau trên số tổng.

### 11.3. Những nguyên nhân khiến test đạt giả

- Reset provider cùng lúc reset database, làm mất hiệu ứng cần đối soát.
- Chỉ assert HTTP status hoặc trạng thái intent, bỏ qua giao dịch ngoài và sổ nội bộ.
- Timeout được tạo trước khi provider nhận lệnh nhưng test lại tuyên bố kiểm tra thành công bị mất phản hồi.
- Cho retry sinh key mới trong fixture, khác hợp đồng khôi phục cùng ý định.
- Mock trả lại chính dữ liệu local nên hai nguồn luôn khớp dù dữ liệu đã sai.
- Dùng thời gian chờ tùy ý mà không xác nhận điểm lỗi, khiến cuộc đua không thực sự xảy ra.
- Kiểm tra tổng tiền cả batch mà không đối chiếu từng identity.
- Chờ đến khi có kết quả mà không đặt hạn test hoặc không chạy công việc đến hạn, khiến lỗi hội tụ biến thành treo bộ test.
- Coi việc đẩy vào hàng đợi ngoại lệ là đã phục hồi tài chính xong, dù giữ chỗ và bằng chứng còn chưa được xử lý.

## 12. Bài thực hành: chứng minh phục hồi mà không tạo thêm tiền

Với fixture `order-42`, thực hiện tuần tự:

1. Chấp nhận intent 40.000 VND khi đã hoàn 30.000 trên giới hạn 100.000.
2. Làm provider hoàn thành rồi mất phản hồi; xác minh local vẫn giữ chỗ 40.000 và chưa có posting thành công cho intent mới.
3. Restart worker; cho lookup trả chưa thấy một lần trước khi thấy giao dịch thành công. Ghi lại trạng thái giữa hai lần lookup.
4. Cho callback và hai worker đối soát cùng xử lý kết quả; kiểm tra oracle theo identity và theo hạn mức.
5. Phát lại công việc nhiều lần; xác nhận vẫn chỉ có một hiệu ứng tiền của intent và một nhóm ghi nhận nghiệp vụ.
6. Lặp lại với bằng chứng đúng reference nhưng sai merchant account hoặc amount; xác nhận không tự gắn vào intent và có ngoại lệ đủ thông tin.
7. Khôi phục bản local có trước lúc tạo intent, giữ nguyên provider; chứng minh quét từ phía provider tìm được khoản ngoài sổ và đưa vào đúng quy trình.

Sản phẩm của bài thực hành gồm timeline điểm lỗi, bảng trạng thái kỳ vọng/thực tế, bằng chứng bên ngoài và nội bộ, cùng assertion cụ thể cho từng bất biến. Với bước cần xử lý ngoại lệ, nêu rõ dữ liệu được giữ lại và hành động nào vẫn bị chặn cho tới khi có thẩm quyền/bằng chứng phù hợp.

Một recovery reconciliation test có giá trị phải trả lời được ba câu: **hiệu ứng nào đã thật sự xảy ra, hệ thống dựa vào đâu để ghi nhận hoặc tiếp tục, và điều gì ngăn cùng sự cố tạo thêm hiệu ứng hoặc bỏ sót nghĩa vụ**. Đó là tiêu chí để đánh giá phục hồi logic nghiệp vụ sau gián đoạn.
