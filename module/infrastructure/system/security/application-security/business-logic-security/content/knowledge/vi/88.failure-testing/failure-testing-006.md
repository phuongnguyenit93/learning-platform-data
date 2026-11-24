# Kiểm thử lỗi giữa các phần của giao dịch (Partial transaction failure)

Một thao tác xác nhận đơn hàng có thể cập nhật trạng thái, giữ tồn kho, tạo yêu cầu thanh toán và phát sự kiện. Nếu lỗi xuất hiện giữa các bước, hệ thống có thể giữ hàng nhưng không còn operation để phục hồi, thu tiền hai lần khi retry hoặc trả hàng về kho dù khoản thanh toán vẫn có thể thành công.

Trong chương **Failure Testing** của module Business Logic Security, partial transaction failure là kiểm thử các tình huống lỗi khiến một phần của **quy trình nghiệp vụ** đã có hiệu lực còn phần khác chưa hoàn tất hoặc chưa biết kết quả. Mục tiêu là giữ business invariants, quyền theo đối tượng và khả năng phục hồi tại từng ranh giới.

## 1. Hiểu đúng chữ “partial”

### 1.1. Không mặc định database commit nửa transaction

Trong một transaction cục bộ có tính nguyên tử, các thay đổi được bao trong transaction phải cùng commit hoặc cùng rollback theo bảo đảm của hệ thống lưu trữ. Một exception giữa hai câu ghi không tự có nghĩa câu đầu được commit còn câu sau không.

Các lỗi từng phần thường xuất hiện vì:

- Những lần ghi thực tế nằm trong các transaction khác nhau.
- Một bước chạy ngoài transaction do cấu hình, luồng hoặc connection khác.
- Gửi email, gọi thanh toán hoặc phát thông điệp trực tiếp không nằm trong transaction database.
- Commit đã thành công nhưng phía gọi không nhận được xác nhận.
- Một bước của workflow đã commit, bước sau bị lỗi hoặc chưa chạy.
- Tiến trình chết trước khi ghi lại kết quả của hiệu lực bên ngoài.

Nếu hai hàng trong cùng một transaction thực sự được cam kết nguyên tử mà chỉ một hàng tồn tại sau lỗi, cần điều tra ranh giới transaction, nguồn đọc và giả định hệ thống. Không coi trạng thái đó là điều bình thường rồi dùng retry để che.

### 1.2. Ba loại kết quả cần phân biệt

| Kết quả | Ý nghĩa | Điều không được suy ra |
|---|---|---|
| Đã rollback được xác nhận | Những thay đổi trong transaction đó không commit | Mọi hệ thống ngoài cũng đã được hoàn tác |
| Đã commit được xác nhận | Thay đổi cục bộ đã durable theo bảo đảm sử dụng | Toàn bộ workflow và tác dụng phụ đã hoàn tất |
| Chưa biết commit hay chưa | Mất phản hồi hoặc lỗi tại ranh giới xác nhận | Thao tác chắc chắn thất bại và có thể tạo lại từ đầu |

HTTP 500, timeout hoặc connection bị đóng không tự chứng minh rollback. Đây là điểm dễ bị lạm dụng: client gửi lại với key khác trong khi lần đầu đã có hiệu lực.

### 1.3. Mục tiêu học tập

Sau bài học, bạn có thể:

- Vẽ đúng ranh giới transaction và tác dụng phụ của một thao tác nghiệp vụ.
- Chọn điểm tiêm lỗi trước commit, sau commit và quanh hệ thống ngoài.
- Xác minh rollback bằng dữ liệu đã commit, không chỉ bằng exception.
- Giải quyết kết quả chưa rõ mà không tạo thêm hiệu lực.
- Kiểm tra outbox, idempotency, state machine và compensation.
- Phân biệt tính an toàn với tiến độ phục hồi.

## 2. Mô hình xuyên suốt: xác nhận đơn và thanh toán

Fixture có:

- Đơn ORD-A thuộc người dùng A và tenant T1.
- Đơn đang APPROVED, version 7; nội dung được duyệt đã được ràng buộc với phiên bản.
- Giá server đã chấp nhận là 195.000 đồng, không lấy giá mới từ request retry.
- Kho còn một đơn vị hàng, chưa có reservation cho đơn.
- Mỗi lần xác nhận có operation được định danh và idempotency key trong scope đã định nghĩa.
- Adapter thanh toán kiểm thử hỗ trợ định danh hiệu lực và cơ chế chống trùng theo hợp đồng của fixture.

Luồng được chia thành hai transaction cục bộ và một hiệu lực ngoài database.

### 2.1. Transaction T1: chấp nhận ý định

```text
Xác thực caller và quyền trên ORD-A.
Kiểm tra APPROVED, version 7, báo giá và các điều kiện nghiệp vụ.

T1:
    tạo operation PENDING_PAYMENT với fingerprint của ý định
    giữ một đơn vị kho bằng reservation ACTIVE
    chuyển order sang PAYMENT_PENDING
    tạo outbox PaymentRequested gắn operation
    lưu ánh xạ idempotency key về operation
COMMIT T1

Trả operationId cho caller.
```

Tất cả các lần ghi được liệt kê trong T1 phải cùng commit. Nếu thiết kế thực tế chia chúng thành nhiều transaction, phải mô hình hóa trạng thái trung gian và cách phục hồi riêng.

### 2.2. Hiệu lực thanh toán bên ngoài

Worker đọc sự kiện, xác minh dữ liệu liên quan và gọi bên thanh toán bằng định danh ổn định của operation. Bên ngoài có thể đã thu tiền dù worker không nhận được response.

Không giữ transaction database mở rồi giả định rollback có thể hoàn tác cuộc gọi mạng. Một cuộc gọi nằm trong thân hàm transaction vẫn không tự trở thành một phần của atomic commit cục bộ.

### 2.3. Transaction T2: ghi nhận thành công

```text
Có bằng chứng thanh toán hợp lệ, đúng operation, số tiền và currency.

T2:
    ghi nhận kết quả thanh toán với định danh chống trùng
    chuyển operation sang SUCCEEDED
    chuyển order sang PAID
    chuyển reservation ACTIVE sang COMMITTED
    tạo outbox OrderPaid
COMMIT T2
```

Trong mô hình, reservation COMMITTED biểu thị một đơn vị kho đã được phân bổ chắc chắn cho đơn đã thanh toán. Việc xuất kho vật lý nằm ngoài phạm vi bài.

Response của T1 chỉ xác nhận ý định đã được chấp nhận, không chứng minh T2 hay thanh toán đã hoàn tất. Replay phải tìm về cùng operation; hợp đồng có thể trả trạng thái hiện tại hoặc kết quả đã lưu theo API.

## 3. Viết invariant theo từng ranh giới

### 3.1. Tính nguyên tử cục bộ

Nếu T1 rollback được xác nhận:

```text
order vẫn APPROVED với dữ liệu nghiệp vụ ban đầu
không có operation mới của ý định đó
không có reservation mới hoặc phần trừ kho bị bỏ lại
không có outbox PaymentRequested đã commit cho ý định đó
không có ánh xạ idempotency thành công trỏ tới operation không tồn tại
```

Audit về request thất bại có thể tồn tại ngoài projection này. Không yêu cầu toàn database giống từng byte.

Nếu T2 rollback, trạng thái trước T2 vẫn phải giữ nguyên theo mô hình, nhưng thanh toán bên ngoài có thể đã có hiệu lực. Không gán kết quả “chưa thanh toán” chỉ vì bảng cục bộ chưa cập nhật.

### 3.2. Bảo toàn tồn kho

Với fixture không nhập thêm hàng, không xuất kho vật lý và không có luồng ngoài mô hình:

```text
initialStock = availableStock
             + quantity của reservation ACTIVE
             + quantity của reservation COMMITTED

availableStock >= 0
```

Sau T1, hàng chuyển từ available sang ACTIVE. Sau T2, nó chuyển từ ACTIVE sang COMMITTED, không trả lại available.

Nếu thanh toán được xác nhận thất bại và không còn khả năng có hiệu lực theo hợp đồng, một transaction thất bại nghiệp vụ có thể chuyển reservation sang RELEASED và trả hàng. Khi đó lượng RELEASED không còn tính trong ACTIVE hay COMMITTED.

### 3.3. Không nhân đôi hiệu lực

```text
mỗi operation thanh toán có tối đa một hiệu lực thu tiền được phép

đơn trong luồng mẫu không có hai operation đang cạnh tranh
để thu cùng một nghĩa vụ thanh toán

replay không tạo operation, reservation hoặc khoản thu mới
```

Hai idempotency key khác nhau vẫn phải tuân thủ state machine và ràng buộc theo đơn. Chống trùng theo key không tự ngăn hai ý định khác key thu cùng đơn.

### 3.4. Không công bố thành công sai

Trong mô hình:

- Order PAID phải có bằng chứng thanh toán đã xác minh và reservation tương ứng COMMITTED.
- Operation SUCCEEDED không được trỏ tới thanh toán sai số tiền, sai currency hoặc sai tenant.
- Outbox OrderPaid chỉ xuất hiện cùng chuyển trạng thái thành công trong T2.
- Dữ liệu retry không được thay nội dung đã duyệt hoặc giá đã được server chấp nhận.

Khoảng thời gian bên thanh toán đã thu tiền nhưng order còn PAYMENT_PENDING là trạng thái trung gian có thể xảy ra. Nó cần đường phục hồi; không phải lý do để trả thành công giả hoặc thu thêm lần nữa.

### 3.5. An toàn và tiến độ là hai điều khác nhau

**Safety:** không thu trùng, không trả lại hàng sai, không tạo PAID thiếu chứng cứ.

**Recovery/liveness:** operation đã được chấp nhận được xử lý tới trạng thái cuối hoặc chuyển sang trạng thái cần can thiệp trong deadline đã định nghĩa.

Một hệ thống giữ mọi operation ở PENDING_PAYMENT mãi có thể chưa thu trùng, nhưng vẫn không đáp ứng tiến độ nghiệp vụ. Test cần kiểm tra cả hai.

## 4. State machine phải biểu diễn kết quả chưa rõ

Một tập trạng thái operation minh họa:

| Trạng thái | Ý nghĩa |
|---|---|
| PENDING_PAYMENT | Đã chấp nhận ý định, chưa có kết quả cuối |
| PAYMENT_UNKNOWN | Có khả năng thanh toán đã có hiệu lực nhưng chưa xác định |
| SUCCEEDED | Có bằng chứng thành công và trạng thái cục bộ tương ứng đã commit |
| FAILED_NO_EFFECT | Có căn cứ kết thúc thất bại mà không có hiệu lực thu tiền |
| COMPENSATION_PENDING | Đã có hiệu lực cần được bù theo quy tắc |
| COMPENSATED | Hiệu lực bù đã được xác nhận |
| MANUAL_REVIEW | Không thể tự quyết định an toàn trong phạm vi phục hồi tự động |

Các trạng thái cần có bằng chứng và quy tắc chuyển, không chỉ thêm enum.

### 4.1. UNKNOWN không phải FAILED

Sau timeout khi gọi thanh toán, worker có thể:

- Tra cứu theo định danh operation của bên thanh toán.
- Gửi lại cùng ý định với cùng external idempotency key nếu giao thức cho phép.
- Tiếp nhận callback đã được xác minh.
- Chờ/reconcile theo deadline và chuyển sang trạng thái can thiệp.

Một kết quả “không tìm thấy” ở hệ thống có độ trễ quan sát không tự chứng minh chưa có khoản thu. Chính sách xác nhận không hiệu lực phải dựa trên bảo đảm của giao thức thực tế.

Không trả reservation về available chỉ vì client hết thời gian chờ trong khi khoản thanh toán vẫn có thể xuất hiện. Nếu có timeout nghiệp vụ và chính sách giải phóng, cần phối hợp việc chấm dứt/đảo hiệu lực bên ngoài hoặc mô hình nghĩa vụ chờ xử lý.

### 4.2. Compensation không xóa lịch sử

Nếu đã thu tiền rồi phải hoàn, một refund là hiệu lực mới, có định danh và chống trùng riêng. Nó không làm khoản thu trước đó chưa từng tồn tại.

Test nên phân biệt:

```text
FAILED_NO_EFFECT: không có hiệu lực thu tiền
COMPENSATED: đã có thu tiền và hiệu lực bù được xác nhận
```

Không đặt lại tất cả về trạng thái trước T1 rồi báo “rollback thành công”. Phí, thời gian chờ, nghĩa vụ và dấu vết có thể vẫn cần được xử lý theo nghiệp vụ.

## 5. Chọn điểm tiêm lỗi theo hiệu lực đã xảy ra

Một test case cần nêu rõ **lỗi xảy ra ở đâu, dữ liệu nào đã durable, hiệu lực ngoài nào đã xảy ra và điều gì phải đúng sau phục hồi**. Chỉ ghi “database lỗi” hoặc “payment timeout” chưa đủ để xác định kết quả mong đợi.

Trong bảng dưới, “tiêm lỗi” là hành động của bộ kiểm thử trong môi trường kiểm soát. Đây không phải khả năng mà API nghiệp vụ cho client tùy ý sử dụng.

| Mã | Điểm tiêm lỗi | Điều phải kiểm tra ngay sau lỗi | Điều phải kiểm tra khi phục hồi |
|---|---|---|---|
| F01 | Sau khi tạo operation, trước các lần ghi còn lại của T1 | Khi rollback được xác nhận, không còn operation mồ côi | Retry có thể tạo một operation hợp lệ; không phát sự kiện cho lần đã rollback |
| F02 | Sau khi giữ kho, trước khi tạo outbox hoặc ánh xạ key trong T1 | Order, operation, kho, reservation và idempotency cùng rollback | Một lần retry không giữ thêm hàng do dữ liệu bị bỏ lại |
| F03 | Sau lần ghi cuối của T1, trước COMMIT | Sau rollback, projection nghiệp vụ trở về trước T1 | Không có worker nào gọi thanh toán từ ý định chưa commit |
| F04 | Database đã commit T1, nhưng response tới client bị mất | Một operation và reservation ACTIVE vẫn tồn tại; không suy ra rollback từ timeout | Cùng key tìm lại operation; khác key cũng không thu lại cùng nghĩa vụ |
| F05 | Broker nhận sự kiện nhưng relay chưa đánh dấu đã gửi rồi bị dừng | Sự kiện có thể được phát lại | Consumer nhận trùng nhưng không tạo thêm hiệu lực nghiệp vụ |
| F06 | Worker nhận sự kiện rồi chết trước khi gọi thanh toán | Operation chưa có kết quả cuối; reservation chưa được giải phóng tùy tiện | Lease hoặc cơ chế nhận lại việc cho phép tiếp tục bằng cùng định danh |
| F07 | Bên thanh toán đã thu tiền nhưng response bị cắt | Ledger của stub có một khoản thu; cục bộ có thể còn pending hoặc unknown | Tra cứu/retry an toàn tìm đúng khoản thu; không phát sinh khoản thứ hai |
| F08 | Worker có bằng chứng thành công, nhưng một lần ghi trong T2 lỗi | T2 rollback toàn bộ; khoản thu ngoài database vẫn tồn tại | Bằng chứng được tiếp nhận lại và T2 hoàn tất đúng một lần về mặt nghiệp vụ |
| F09 | T2 đã commit, nhưng worker chết trước ACK message hoặc response API | Order PAID, operation SUCCEEDED, reservation COMMITTED cùng tồn tại | Redelivery, callback và retry không đổi lại trạng thái hay thu thêm |
| F10 | Refund đã có hiệu lực nhưng response hoặc lần ghi xác nhận bị mất | Chưa được kết luận COMPENSATED chỉ từ việc gửi request | Khôi phục cùng refund operation, xác minh một hiệu lực hoàn tiền |
| F11 | Callback cũ tới sau callback thành công hoặc sau khi bù | Trạng thái cuối không bị ghi lùi bởi thông tin cũ | Hợp nhất bằng chứng theo quy tắc, giữ lịch sử và đối chiếu xung đột |
| F12 | External idempotency key có thể hết thời gian lưu trong khi kết quả còn unknown | Không coi key cũ là bảo đảm chống trùng vô thời hạn | Dừng retry có nguy cơ tạo hiệu lực mới, đối soát hoặc chuyển MANUAL_REVIEW |

Với F01–F03 và F08, lặp lại phép thử tại **từng lần ghi** thuộc transaction tương ứng. Một failpoint sau một câu lệnh không đại diện cho mọi đường lỗi: một nhánh có thể dùng connection hoặc transaction riêng.

Đối với F04, điểm cắt phải thật sự nằm sau khi database commit. Ném exception trước `COMMIT` chỉ kiểm tra được một nhánh khác. Có thể để ứng dụng ghi xong, rồi cắt response ở proxy kiểm thử; hoặc dừng tiến trình tại hook sau commit trước khi gửi phản hồi.

### 5.1. Mất ACK có hai nơi khác nhau

- **Relay → broker:** broker đã nhận message, relay chưa biết; relay có thể publish lại.
- **Worker → broker:** worker đã xử lý message, broker chưa nhận ACK; broker có thể giao lại.

Vì vậy, đếm số lần publish hoặc số lần handler chạy không đủ để kết luận lỗi nghiệp vụ. Cần đếm operation, sự kiện logic, reservation và hiệu lực thanh toán thực tế theo định danh ổn định.

## 6. Chuẩn bị bộ kiểm thử có khả năng quan sát đúng

### 6.1. Thành phần tối thiểu

Một bộ kiểm thử tích hợp hữu ích cho mô hình này có:

1. Database với transaction, constraint và cơ chế concurrency phù hợp với triển khai cần kiểm chứng.
2. Ứng dụng đi qua đúng lớp quản lý transaction thực tế, thay vì gọi một mock repository.
3. Failpoint có tên tại ranh giới ghi dữ liệu, commit, gọi provider và ACK.
4. Stub thanh toán có ledger riêng, lưu ánh xạ external key → hiệu lực và cho phép tra cứu kết quả.
5. Outbox relay/consumer có thể tạm dừng, chạy từng bước và giao message trùng hoặc trễ.
6. Đồng hồ kiểm thử, barrier hoặc latch để điều khiển timeout, lease và thứ tự thực thi.
7. Bộ quan sát đọc dữ liệu đã commit và đối chiếu với ledger của provider stub.

Ledger của stub phải sống qua lần restart ứng dụng được kiểm thử. Nếu reset cả ứng dụng lẫn ledger, phép thử mất dấu khoản thu đã xảy ra và có thể báo thành công giả.

Stub cần mô phỏng ít nhất ba hành vi độc lập:

```text
reject_before_effect:
    từ chối theo hợp đồng, không tạo khoản thu

effect_then_response:
    ghi một khoản thu, trả bằng chứng thành công

effect_then_drop_response:
    ghi một khoản thu, sau đó làm caller nhận timeout
```

Hành vi thứ ba khác với việc ném timeout trước khi ghi khoản thu. Chỉ mô phỏng timeout trước hiệu lực sẽ bỏ qua điểm nguy hiểm nhất của partial transaction failure.

### 6.2. Chọn đúng loại lỗi

| Cách gây lỗi | Xác minh được điều gì | Giới hạn cần nhớ |
|---|---|---|
| Ném exception tại failpoint | Đường xử lý lỗi và rollback theo cấu hình transaction | Tiến trình vẫn có thể chạy `catch`/`finally` |
| Dừng tiến trình rồi khởi động lại | Khả năng phục hồi từ dữ liệu durable | Không được dựa vào cleanup trong bộ nhớ |
| Cắt response sau khi downstream tạo hiệu lực | Xử lý kết quả unknown | Phải có chứng cứ downstream đã thực sự tạo hiệu lực |
| Giao lại hoặc đảo thứ tự message | Idempotency, state machine, xử lý thông tin cũ | Không thay thế kiểm thử rollback database |
| Tạm dừng worker tới khi hết lease | Tranh chấp giữa worker cũ và worker tiếp quản | Hết lease không chứng minh lời gọi mạng cũ đã bị hủy |

Không dùng một exception trong Java để tuyên bố đã kiểm chứng crash recovery. Hai tình huống có thể đi qua các đường cleanup khác nhau.

### 6.3. Đọc dữ liệu độc lập với transaction đang kiểm thử

Seed fixture rồi commit trước khi gọi luồng cần kiểm thử. Sau lỗi, chờ transaction của ứng dụng kết thúc và dùng connection/transaction quan sát mới để đọc trạng thái.

Không bọc toàn bộ test trong một transaction ngoài rồi để framework rollback cuối test. Cách đó có thể che việc ứng dụng chưa thực sự commit, khiến outbox chưa xuất hiện hoặc làm các lần ghi khác connection bị hiểu sai.

Các trường của snapshot phải thuộc cùng một ảnh dữ liệu nhất quán hoặc được đọc sau khi đã điều phối dừng các bên ghi. Đọc lần lượt nhiều bảng trong khi worker vẫn chạy có thể ghép những thời điểm khác nhau thành một trạng thái “nửa commit” giả.

Tính nguyên tử và cách nhóm các câu lệnh bằng transaction được minh họa trong [tài liệu Transactions của PostgreSQL](https://www.postgresql.org/docs/current/tutorial-transactions.html). Khi áp dụng vào hệ thống cụ thể, cần kiểm chứng đúng ranh giới transaction mà ứng dụng thực sự mở.

## 7. Ba ví dụ kiểm thử từ rollback tới phục hồi

Các đoạn Java dưới đây là **mã giả theo phong cách JUnit**, diễn đạt hợp đồng kiểm thử; `env`, `observer`, `faults` và các helper là thành phần minh họa, chưa phải API thư viện hay chương trình chạy độc lập. Giả định fixture có order ORD-A như mục 2, provider stub lưu ledger bền qua restart và các test được cách ly dữ liệu.

### 7.1. Lỗi trong T1 phải rollback toàn bộ projection

```java
@Test
void loiSauGiuKhoKhongDeLaiDuLieuMoCoi() {
    var fixture = env.seedAndCommitApprovedOrder("ORD-A", "A", "T1");
    env.pauseAsyncWorkers();
    var before = observer.businessSnapshotFromPrimary(fixture);

    faults.throwOnceAt("AFTER_RESERVATION_WRITE_BEFORE_T1_COMMIT");

    assertThrows(InjectedFailure.class, () ->
        env.application().confirm(fixture.command(), "confirm-k1")
    );
    env.awaitConfirmedRollbackOfApplicationTransaction();

    var after = observer.businessSnapshotFromPrimary(fixture);
    assertEquals(before, after);
    assertEquals(0, observer.operationsForOrder("ORD-A").size());
    assertEquals(0, observer.paymentRequestedEventsFor("ORD-A").size());
    assertEquals(0, env.providerLedger().captureEffectsFor("ORD-A"));
}
```

`businessSnapshotFromPrimary` chỉ lấy dữ liệu trong projection nghiệp vụ đã định nghĩa, không gồm sequence, timestamp log hoặc audit của request lỗi. `awaitConfirmedRollbackOfApplicationTransaction` là hook quan sát transaction của harness, không phải suy luận từ HTTP 500.

Sau kiểm tra rollback, nên gỡ failpoint và gửi lại cùng key. Lần chạy này phải có thể chấp nhận một ý định hợp lệ, giữ đúng một đơn vị hàng và tạo đúng một outbox logic. Nếu key bị mắc ở “đang xử lý” mà không có operation hoặc lease để phục hồi, phép thử vẫn phát hiện lỗi dù kho đã rollback đúng.

### 7.2. Thu tiền rồi timeout: restart không được thu thêm

```java
@Test
void matPhanHoiSauThuTienVanPhucHoiCungOperation() {
    var fixture = env.seedAndCommitApprovedOrder("ORD-A", "A", "T1");
    env.pauseAsyncWorkers();
    var accepted = env.api().confirm(fixture.command(), "confirm-k2");
    var operationId = accepted.operationId();

    env.provider().captureThenDropResponseOnce(operationId);
    env.runPaymentWorkerOneAttempt(operationId);

    assertEquals(1, env.providerLedger().captureEffectsFor(operationId));
    assertFalse(observer.operation(operationId).isSucceeded());
    assertEquals("PAYMENT_PENDING", observer.order("ORD-A").state());
    assertEquals("ACTIVE", observer.reservationFor(operationId).state());

    env.restartApplicationKeepingDatabaseBrokerAndProviderLedger();
    var replay = env.api().confirm(fixture.command(), "confirm-k2");
    assertEquals(operationId, replay.operationId());

    env.recovery().runUntilTerminal(operationId, env.testDeadline());

    assertEquals("SUCCEEDED", observer.operation(operationId).state());
    assertEquals("PAID", observer.order("ORD-A").state());
    assertEquals("COMMITTED", observer.reservationFor(operationId).state());
    assertEquals(1, observer.operationsForOrder("ORD-A").size());
    assertEquals(1, env.providerLedger().captureEffectsFor(operationId));
    assertEquals(1, observer.logicalOrderPaidEventsFor(operationId).size());
}
```

Đường phục hồi có thể tra cứu kết quả hoặc gửi lại cùng external key trong thời gian được provider bảo đảm. Vì vậy không ép số lần gọi provider phải bằng một: **một hiệu lực** và **một lần gọi mạng** là hai phép đếm khác nhau.

Trong test này, provider stub cung cấp kết quả có thể xác minh, nên yêu cầu cuối là SUCCEEDED. Với fixture cố ý làm bằng chứng không thể khôi phục, kết quả mong đợi phải là MANUAL_REVIEW đúng hạn, kèm bất biến không thu thêm; không sửa assertion tùy theo kết quả tình cờ nhận được.

### 7.3. T2 đã commit rồi mất ACK: message trùng không tạo hiệu lực mới

```text
Given:
    T1 đã commit, provider đã thu tiền đúng một lần
    worker nhận bằng chứng thanh toán hợp lệ

When:
    chạy T2 tới khi database xác nhận commit
    dừng worker trước khi ACK message
    restart và giao lại chính message đó
    đồng thời giao callback thành công trùng cho cùng payment

Then:
    order vẫn PAID, operation vẫn SUCCEEDED
    reservation vẫn COMMITTED, availableStock vẫn bằng 0
    chỉ một khoản thu và một payment record logic được ghi nhận
    chỉ một OrderPaid logic gắn lần chuyển trạng thái đó
    không tạo refund hoặc chuyển lại PAYMENT_PENDING
```

“Một OrderPaid logic” là một event ID gắn với một lần chuyển trạng thái. Outbox relay có thể gửi nhiều bản sao của event ID ấy; yêu cầu phía consumer là không tạo thêm hiệu lực như giao hàng hai lần.

## 8. Kiểm thử các cơ chế thường được dùng để xử lý lỗi

### 8.1. Transactional outbox

Ghi business state và outbox trong cùng transaction giúp tránh khoảng hở “database đã cập nhật nhưng ý định phát sự kiện bị mất”. Relay vẫn có thể phát lại, nên consumer cần xử lý trùng. Đây là hai đặc điểm được trình bày trong [AWS Prescriptive Guidance về transactional outbox](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html).

Các assertion áp dụng cho mô hình bài này:

- T1 rollback → không có PaymentRequested đã commit và không có khoản thu ngoài.
- T1 commit nhưng relay chết → outbox còn đủ dữ liệu hoặc dấu vết để gửi lại.
- Relay publish thành công rồi chết → cùng event ID được giao lại an toàn.
- T2 rollback → không có OrderPaid được công bố cho chuyển trạng thái chưa commit.
- T2 commit → OrderPaid được xử lý về sau trong deadline phục hồi của fixture.

Nếu consumer dùng inbox/dedup record cho thay đổi database cục bộ, kiểm thử việc ghi dedup record cùng transaction với thay đổi ấy. Ghi “đã xử lý” trước khi effect commit có thể làm mất việc; ghi sau trong transaction khác có thể cho phép lặp effect.

Inbox của database không tự bao được hiệu lực thanh toán bên ngoài. Với bước này vẫn cần operation durable, external idempotency và/hoặc giao thức tra cứu kết quả tương ứng. Không suy ra exactly-once cho toàn workflow chỉ vì có outbox hoặc broker chống trùng.

### 8.2. Idempotency của API và của provider

Hai lớp idempotency có nhiệm vụ khác nhau:

| Lớp | Định danh điển hình | Điều cần kiểm thử |
|---|---|---|
| API nhận ý định | Scope được định nghĩa, client key, fingerprint | Replay cùng ý định tìm lại operation; khác nội dung bị từ chối |
| Worker gọi provider | Provider account, action và external key bền vững của operation | Restart/redelivery không đổi key của cùng hiệu lực |
| Callback/consumer | Provider event ID và/hoặc effect ID cùng scope | Message trùng không ghi nhận hoặc thực hiện lại hiệu lực |
| Refund | Refund operation và key riêng của hiệu lực bù | Retry refund không hoàn quá số tiền được phép |

Scope có thể bao gồm tenant, chủ thể và loại thao tác theo hợp đồng API; phải đủ để không trả kết quả của người khác. Fingerprint cần ràng buộc ý định chuẩn hóa như order, version được duyệt, số tiền, currency và loại thao tác. Không lấy một key do client gửi để thay cho mọi kiểm tra nghiệp vụ.

Các biến thể phải có assertion rõ ràng:

1. Cùng key, cùng fingerprint, đang pending → cùng operation hoặc phản hồi “đang xử lý” theo hợp đồng, không tạo thêm hiệu lực.
2. Cùng key, đổi order/số tiền/currency → từ chối xung đột, không sửa operation gốc.
3. Khác key, cùng order còn PAYMENT_PENDING hoặc đã PAID → state machine/ràng buộc nghiệp vụ chặn operation cạnh tranh.
4. Cùng chuỗi key ở tenant khác → không truy cập dữ liệu tenant ban đầu; hành vi riêng biệt theo scope đã công bố.
5. Key local hết hạn hoặc cache bị xóa → dữ liệu nghiệp vụ durable vẫn ngăn xác nhận lại đơn đã xử lý.
6. Worker hết lease rồi chạy lại → external key và fingerprint của cùng operation không bị tạo mới.

Không coi mọi provider có cùng semantics. Ví dụ, [Stripe Idempotent requests](https://docs.stripe.com/api/idempotent_requests) mô tả với API v1 việc lưu response sau khi endpoint bắt đầu thực thi, có thể replay cả lỗi 500, so khớp tham số và cho phép loại bỏ key sau khi đã đủ thời gian lưu tối thiểu. Bảo đảm retry phải được thiết kế theo đúng API đang tích hợp.

Với kết quả còn unknown, hết cửa sổ chống trùng không phải thời điểm tự động phát sinh key mới. [Stripe Advanced error handling](https://docs.stripe.com/error-low-level) cũng phân biệt mất phản hồi với kết quả thất bại và yêu cầu đối soát khi không thể retry trong cửa sổ bảo đảm. Áp dụng vào mô hình ở đây, test F12 phải xác minh việc ngừng tạo yêu cầu có nguy cơ thu thêm.

### 8.3. Concurrency và kiểm soát phiên bản

Transaction đúng về atomicity vẫn có thể cho phép hai thao tác hợp lệ riêng lẻ cùng vi phạm một invariant khi chạy song song. Thiết kế cần cơ chế phù hợp như conditional update, khóa, ràng buộc duy nhất hoặc isolation với retry đúng cách; test phải đi qua cơ chế thực tế đó.

Một lịch kiểm thử có thể điều phối như sau:

```text
Request R1 dùng key K1 đọc đơn ORD-A ở APPROVED, version 7.
Request R2 dùng key K2 cũng tới ranh giới tranh chấp của ORD-A.
Cho các request tiếp tục theo thứ tự do barrier của harness kiểm soát.

Nếu thiết kế dùng khóa trước khi đọc:
    xác minh request sau thực sự phải chờ hoặc bị từ chối phù hợp;
    không bắt cả hai giữ cùng khóa rồi mới nhả barrier.

Nếu thiết kế dùng optimistic concurrency:
    kiểm tra số hàng bị cập nhật và xử lý xung đột phiên bản.

Quan sát sau commit:
    chỉ một operation có quyền thực hiện nghĩa vụ thanh toán này;
    chỉ một reservation ACTIVE và không âm kho;
    request còn lại không phát thêm PaymentRequested có hiệu lực mới.
```

Tiếp theo, làm R1 mất response sau T1 rồi để R2 retry. Cách kết hợp này kiểm tra liệu nhánh phục hồi có bỏ qua khóa hoặc version check mà nhánh thông thường vẫn thực hiện hay không.

Khi database báo deadlock hoặc serialization conflict và bảo đảm transaction đã bị hủy, có thể retry toàn bộ transaction theo chính sách. Nếu kết quả COMMIT chưa rõ, phải giải quyết operation cũ trước; không dùng chung một nhánh “retry mọi exception”.

### 8.4. Lease và worker cũ

Cho worker W1 bắt đầu gọi provider rồi tạm dừng đến khi lease hết hạn. W2 nhận lại việc và tiếp tục. Sau đó cho W1 chạy tiếp với response muộn.

Test phải chứng minh:

- W1 và W2 sử dụng cùng định danh của hiệu lực đang phục hồi.
- Việc tiếp quản có fencing/version check hoặc cơ chế tương đương để worker cũ không ghi đè trạng thái mới.
- Một response cũ báo pending/failed không ghi lùi SUCCEEDED hoặc COMPENSATED.
- Hết lease không làm hệ thống suy ra khoản thu của W1 chắc chắn chưa xảy ra.

Fencing trong database không tự chặn request đã gửi tới provider. Hai lớp bảo vệ phải được kiểm thử ở đúng nơi chúng có hiệu lực.

## 9. Ghép lỗi hạ tầng với hành vi lạm dụng nghiệp vụ

Một lỗi ngẫu nhiên trở thành vấn đề bảo mật khi người dùng có thể chủ động tạo hoặc khai thác cửa sổ không nhất quán. Không cần chứng minh người dùng điều khiển được database crash; họ có thể đóng kết nối, gửi trùng, thay key hoặc thao tác đồng thời khi hệ thống đang chậm.

### 9.1. Đổi giá hoặc bỏ qua phê duyệt khi retry

Sau F04 hoặc F07, gửi lại yêu cầu với cùng key nhưng giảm giá, đổi currency, đổi order ID hoặc đổi version. Yêu cầu mới phải bị từ chối theo quy tắc xung đột; dữ liệu ban đầu không được sửa và số hiệu lực không tăng.

Gửi tiếp một key khác với các thay đổi tương tự. State machine và ràng buộc nội dung được duyệt vẫn phải áp dụng; key mới không cấp quyền bỏ qua bước phê duyệt. Nếu nghiệp vụ cho phép sửa đơn sau duyệt, phải tạo phiên bản/quy trình duyệt mới và giải quyết nghĩa vụ pending cũ theo chính sách trước khi thu theo ý định mới.

Đặc biệt, kiểm tra case đơn đổi version trong khoảng giữa lần đọc điều kiện và lần ghi. Việc “đã kiểm tra APPROVED ở đầu request” không đủ nếu lần ghi không ràng buộc phiên bản hoặc không khóa đúng dữ liệu liên quan.

### 9.2. Đọc hoặc phục hồi operation sai quyền

Lấy operation ID hoặc chuỗi idempotency key của fixture A, rồi gọi API bằng người dùng B và tenant khác:

- Lấy trạng thái operation.
- Replay lệnh xác nhận đơn.
- Hủy hoặc yêu cầu refund.
- Gọi endpoint retry/recover dành cho vận hành nếu có.

Mỗi lần gọi phải kiểm tra quyền trên đối tượng và phạm vi chức năng theo chính sách. Không trả cached response có dữ liệu của A trước khi kiểm tra quyền; idempotency key và operation ID không phải bằng chứng sở hữu.

Nếu quyền bị thu hồi sau khi ý định đã được chấp nhận, tách hai câu hỏi: B/caller hiện tại có được xem hoặc ra lệnh mới không, và worker có tiếp tục nghĩa vụ đã được chấp nhận không? Câu trả lời theo chính sách nghiệp vụ đã công bố. Không mặc định cứ mất phiên đăng nhập là được bỏ qua việc đối soát khoản thu.

### 9.3. Callback giả, trùng và sai thứ tự

Thử callback có chữ ký/nguồn không hợp lệ, đúng event ID nhưng sai tenant, sai operation, sai amount/currency hoặc effect ID đã gắn với operation khác. Không được chuyển PAID hoặc phát OrderPaid từ các dữ liệu không hợp lệ đó.

Sau callback thành công, giao lại callback pending hoặc failed cũ. Trạng thái không được ghi lùi chỉ vì message tới sau. Quy tắc hợp nhất phải dựa vào semantics của provider và bằng chứng của đúng hiệu lực, không đơn thuần “response cuối cùng thắng”.

Đối với callback hợp lệ báo thành công muộn sau khi hệ thống đã giải phóng hàng theo một chính sách khác, phải có đường xử lý nghĩa vụ cụ thể: giữ lại/phân bổ lại hợp lệ, bù hoặc chuyển can thiệp. Không đánh dấu PAID thiếu hàng rồi coi test đã qua. Trong mô hình cơ sở của bài, khoản thu còn unknown thì chưa được giải phóng reservation chỉ vì timeout.

### 9.4. Lạm dụng compensation để nhận lợi ích hai lần

Tạo lỗi sau khoản thu rồi gửi yêu cầu hủy/refund lặp lại, song song với callback và recovery worker. Kiểm tra cả ledger thu tiền, ledger hoàn tiền và trạng thái đơn:

```text
với luồng một khoản thu và không có điều chỉnh khác:
    tổng tiền hoàn đã xác nhận <= tiền đã thu có thể hoàn

refund chưa rõ kết quả:
    không tạo refund mới chỉ vì lần gọi trước timeout

COMPENSATED:
    có bằng chứng refund đúng nghĩa vụ và dữ liệu cục bộ đã commit
```

Nếu có phí, refund từng phần hoặc nhiều loại điều chỉnh, cần định nghĩa lại công thức theo chính sách đó. Không dùng một phép đếm refund duy nhất để đại diện cho mọi nghiệp vụ.

## 10. Tiêu chí đánh giá kết quả và bằng chứng

### 10.1. Đánh giá tại thời điểm lỗi và sau phục hồi

Mỗi case nên có hai nhóm assertion:

| Thời điểm | Assertion về safety | Assertion về tiến độ |
|---|---|---|
| Ngay sau lỗi, khi đã xác định ranh giới commit | Không có dữ liệu cục bộ bị bỏ dở trong transaction; không có hiệu lực vượt quyền hoặc trùng | Có operation/outbox/lease hoặc dấu vết cần thiết cho đường phục hồi đã thiết kế |
| Trong quá trình retry/reconcile | Invariant tiếp tục đúng ở các checkpoint được điều phối | Không bị vòng lặp retry vô hạn hay bỏ quên operation |
| Hết deadline kiểm thử | Không thu trùng, không hoàn trùng, không báo thành công sai | Tới trạng thái cuối mong đợi hoặc MANUAL_REVIEW theo đúng fixture và chính sách |

Assertion safety được kiểm tra xuyên suốt lịch chạy có điều phối, không chỉ sau khi hệ thống “tự ổn định”. Một khoản thu trùng rồi được refund ngay sau đó vẫn vi phạm invariant không thu trùng của mô hình.

Deadline là giá trị của hợp đồng/fixture, không phải `sleep` cố định rồi đoán đã xử lý xong. Ưu tiên chờ điều kiện với timeout hữu hạn, đồng hồ điều khiển được và trace giải thích bước đang chờ. Nếu deadline hết mà chưa đạt trạng thái kỳ vọng, test phải thất bại với bằng chứng đủ để tái hiện.

### 10.2. Bộ dữ liệu quan sát

Ghi nhận theo case ID, tenant, order ID, operation ID, event ID và định danh hiệu lực của provider. Lưu ít nhất:

- Failpoint, thứ tự thực thi và lần crash/restart.
- Trạng thái/version order, operation và reservation trước lỗi, sau lỗi, sau phục hồi.
- Snapshot outbox/inbox liên quan và thông tin số lần giao lại.
- Số lượng, amount, currency và định danh các khoản thu/refund trong ledger của stub.
- Fingerprint ý định, quyết định chấp nhận/reject/replay, và bằng chứng kết quả ngoài.
- Quyết định chuyển trạng thái, thời gian đối soát, lease/fencing version và nguyên nhân chuyển can thiệp nếu có.

Không cần log dữ liệu thẻ, token xác thực hoặc secret để chứng minh invariant. Trong báo cáo, có thể dùng định danh kiểm thử hoặc giá trị đã che phù hợp.

Đừng chỉ đếm hàng payment trong database của ứng dụng. Một khoản thu đã xảy ra nhưng chưa được ghi cục bộ chính là tình huống cần tìm; ledger ngoài là nguồn quan sát độc lập trong fixture này.

### 10.3. Mẫu một case có thể tái hiện

```text
Case: F07-capture-response-lost
Fixture: ORD-A, tenant T1, APPROVED v7, stock=1, amount=195000 VND
Ý định: xác nhận đúng phiên bản đã duyệt, client key=confirm-k2
Tiêm lỗi: provider ghi capture rồi làm mất response đúng một lần
Checkpoint sau lỗi:
    provider có 1 capture; order PAYMENT_PENDING; reservation ACTIVE
Phục hồi:
    restart ứng dụng, giữ DB/broker/provider ledger
    replay cùng ý định; cho worker tra cứu kết quả hợp lệ
Kỳ vọng cuối:
    cùng operation; SUCCEEDED; PAID; reservation COMMITTED
    1 capture; 0 refund; 1 OrderPaid logic; stock available=0
Giới hạn:
    deadline theo fixture; không giả định retry được sau TTL provider
    không yêu cầu mỗi message hoặc cuộc gọi mạng chỉ xuất hiện một lần
```

## 11. Các sai lầm làm test báo qua nhưng vẫn lọt lỗi

| Sai lầm | Vì sao chưa chứng minh được an toàn | Cách sửa phép thử |
|---|---|---|
| Chỉ assert HTTP 500 hoặc exception | Không biết transaction đã commit hay provider đã thu tiền | Đọc trạng thái durable và ledger ngoài |
| Mock timeout trước khi tạo hiệu lực | Bỏ qua nhánh thu tiền thành công nhưng mất response | Thêm chế độ effect-then-drop-response |
| Chỉ kiểm tra một lần ghi trong transaction | Nhánh khác có thể dùng transaction riêng hoặc commit sớm | Đặt failpoint sau từng lần ghi quan trọng |
| Chỉ gửi lại cùng key | Không kiểm tra người dùng đổi key để vượt ràng buộc theo đơn | Thêm different-key/same-obligation và concurrency |
| Gán FAILED sau mọi timeout | Unknown bị xử lý như chắc chắn không thu tiền | Kiểm tra bằng chứng trước chuyển trạng thái hoặc giải phóng hàng |
| Restart làm mất ledger của stub | Khoản thu đầu biến mất khỏi khả năng quan sát | Giữ ledger qua restart ứng dụng |
| Đọc nhiều bảng khi worker vẫn chạy mà không có snapshot nhất quán | Ghép nhiều thời điểm thành một vi phạm giả | Điều phối checkpoint hoặc dùng ảnh đọc nhất quán |
| Chỉ quan sát trạng thái cuối | Hiệu lực vượt invariant có thể đã xảy ra rồi được bù | Kiểm tra lịch sử hiệu lực và các checkpoint |
| Cho phép test chấp nhận mọi trạng thái pending/manual/final | Che lỗi phục hồi bằng assertion quá rộng | Định nghĩa kết quả và deadline trước khi chạy |
| Coi mock test qua là bằng chứng transaction thực tế an toàn | Mock không kiểm chứng commit, isolation hay hiệu lực ngoài tiến trình | Bổ sung kiểm thử tích hợp và bằng chứng chạy tại các ranh giới đã nêu |

## 12. Bài tập áp dụng

1. Với luồng xác nhận đơn của bạn, liệt kê từng lần ghi và từng tác dụng phụ; đánh dấu transaction thực sự bao lấy chúng.
2. Viết invariant cho kho, số tiền, quyền theo đối tượng và nội dung được duyệt; nêu rõ chúng áp dụng ngay lập tức hay sau một mốc phục hồi.
3. Chọn ba case đại diện: rollback trước T1 commit, mất response sau T1 commit, thu tiền rồi mất response. Mỗi case phải có dữ liệu quan sát và kết quả cuối riêng.
4. Thêm hai request đồng thời dùng key khác nhau cho cùng đơn. Chứng minh chỉ một nghĩa vụ thanh toán được thực hiện.
5. Cho refund timeout sau khi đã hoàn tiền. Mô tả vì sao retry cần cùng refund operation và bằng chứng nào cho phép chuyển COMPENSATED.
6. Cho kết quả unknown kéo dài quá cửa sổ chống trùng của provider. Chỉ ra điểm dừng tự động, nghĩa vụ còn giữ và dữ liệu cần bàn giao để can thiệp.

Một lời giải đạt yêu cầu phải giải thích được **hiệu lực nào đã xảy ra, điều gì còn chưa biết, vì sao retry không tạo thêm lợi ích và cơ chế nào đưa workflow tới kết quả có thể kiểm chứng**.
