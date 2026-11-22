# Invariant enforcement point — Điểm thực thi bất biến bảo mật

Một service có thể kiểm tra số tiền hoàn không vượt khoản đã thu, nhưng hai request đồng thời vẫn có thể cùng vượt qua kiểm tra rồi tạo tổng tiền hoàn lớn hơn giới hạn. Một API có thể kiểm tra quyền đúng, trong khi worker hoặc công cụ quản trị cập nhật cùng dữ liệu qua đường khác.

Vấn đề không chỉ là đã viết điều kiện hay chưa. Cần xác định điều kiện được thực thi ở đâu, dựa trên dữ liệu nào, bao phủ những đường nào và có còn đúng khi thay đổi được commit hoặc tác động được thực hiện hay không.

**Invariant enforcement point** là điểm mà một quy tắc phải được giữ trước khi hệ thống cho phép thay đổi hoặc tiết lộ thông tin tương ứng. Trong chương **Security Invariants**, bài học này trình bày cách chọn và phối hợp các điểm thực thi ở API, application service, domain model, repository, cơ sở dữ liệu và luồng bất đồng bộ.

Trọng tâm là bảo vệ quy tắc nghiệp vụ khỏi bỏ bước phê duyệt, sửa giá, thao tác sai quyền và xử lý trùng. Ví dụ xuyên suốt là giới hạn hoàn tiền có giữ chỗ, vì nó cho thấy rõ sự khác nhau giữa kiểm tra một điều kiện và giữ một invariant dưới cạnh tranh.

## 1. Một điều kiện được kiểm tra chưa chắc đã được thực thi đầy đủ

**Security invariant** là điều kiện bảo mật hoặc nghiệp vụ phải được duy trì trong phạm vi và tại ranh giới đã xác định.

Ví dụ:

- Người dùng chỉ đọc được dữ liệu thuộc phạm vi được phép.
- Chỉ nội dung đã có quyết định phê duyệt phù hợp mới được cấp lệnh thanh toán.
- Tổng tiền hoàn đã xác nhận và đang cam kết không vượt giới hạn được phép hoàn.
- Retry không tạo thêm tác động cho cùng nghĩa vụ.
- Thay đổi quan trọng phải có dấu vết chuẩn tương ứng.

Một hàm trả về `true` chỉ đánh giá điều kiện trên dữ liệu nó nhận được. Để thực thi invariant, hệ thống còn phải bảo đảm:

1. Dữ liệu và danh tính có nguồn thẩm quyền phù hợp.
2. Mọi đường có thể gây tác động đều bị kiểm soát theo hợp đồng.
3. Điều kiện không bị vô hiệu bởi thay đổi cạnh tranh không được phát hiện.
4. Khi không thỏa, tác động bị chặn hoặc được xử lý theo nhánh hợp lệ.
5. Lỗi, retry và phục hồi không tạo đường vượt quy tắc.

### 1.1. Ba ví dụ về điểm kiểm tra đặt chưa đúng

| Cách làm | Vì sao chưa đủ |
| --- | --- |
| Giao diện ẩn nút hoàn tiền khi hết hạn mức | Client có thể gọi API trực tiếp |
| Service đọc số dư rồi gọi nhà cung cấp trước khi giữ chỗ | Request khác có thể dùng cùng phần số dư |
| API chính kiểm tra quyền nhưng worker ghi trực tiếp | Quy tắc không bao phủ đường thực thi khác |

Một điểm thực thi tốt phải nằm trên đường dẫn có khả năng kiểm soát tác động, với dữ liệu và cơ chế phối hợp đủ để giữ quy tắc.

## 2. Phát biểu invariant trước khi chọn tầng

Không nên bắt đầu bằng câu “mọi kiểm tra đặt ở controller” hoặc “mọi invariant phải nằm trong entity”. Các quy tắc khác nhau cần dữ liệu và bảo đảm khác nhau.

Một phát biểu có thể thực thi cần nêu:

| Thành phần | Điều cần xác định |
| --- | --- |
| Đối tượng | Đơn, khoản thanh toán, tổ chức hay tài nguyên dùng chung nào |
| Chủ thể | Người dùng, dịch vụ hoặc quyền thực hiện nào được xét |
| Điều kiện | Quan hệ, trạng thái, số lượng hoặc dữ liệu phải thỏa |
| Phạm vi | Một bản ghi, nhiều bản ghi, một tổ chức hay nhiều hệ thống |
| Thời điểm | Khi quyết định, khi commit, khi tiết lộ hay trước tác động bên ngoài |
| Hành vi lỗi | Từ chối, chờ, giữ trạng thái chưa rõ hoặc thực hiện nhánh khác |
| Bằng chứng | Dữ liệu nào chứng minh điều kiện và kết quả |

Ví dụ yếu:

> Không được hoàn tiền sai.

Ví dụ cụ thể hơn:

> Với một khoản thanh toán trong mô hình hoàn tiền đã chọn, tại mỗi commit của sổ hoàn tiền, tổng số tiền đã xác nhận hoàn và đang giữ chỗ cho các lần hoàn chưa xác định kết quả không được vượt giới hạn hoàn được cấp cho khoản đó.

Phát biểu sau cho biết cần bảo vệ một tổng dùng chung, cần giữ chỗ trước tác động và cần xử lý những lần hoàn chưa rõ kết quả.

## 3. Ví dụ xuyên suốt: giới hạn hoàn tiền có giữ chỗ

Giả sử hệ thống có một khoản đã thu 1.000.000 VND. Theo chính sách ví dụ, số tiền tối đa được hoàn cho nghĩa vụ này là 1.000.000 VND.

Bài học không mô hình hóa chargeback hoặc các điều chỉnh làm thay đổi giới hạn sau đó. Nếu sản phẩm hỗ trợ các trường hợp ấy, cần bổ sung quy tắc chuyển đổi và phối hợp cam kết tương ứng.

Gọi:

- `P`: giới hạn được phép hoàn.
- `F`: tổng đã được xác nhận hoàn thành công.
- `R`: tổng đang giữ chỗ cho các lần hoàn chưa quyết toán.
- `q`: số tiền của yêu cầu hoàn mới.

Invariant:

```text
P >= 0
F >= 0
R >= 0
F + R <= P

Số tiền còn có thể cấp = P - F - R.

Chỉ được cấp thêm q khi:
  q > 0
  và q <= P - F - R.
```

Nếu `F = 300.000` và `R = 500.000` thì chỉ còn 200.000 VND để cấp. Một request không được chỉ so `q` với `P` hoặc với `P - F` rồi bỏ qua các cam kết chưa hoàn tất.

### 3.1. Vì sao kiểm tra ở đầu service vẫn có thể thất bại?

```text
Ban đầu: P = 1.000.000, F = 0, R = 0.

T1 đọc còn 1.000.000; yêu cầu hoàn 600.000.
T2 đọc còn 1.000.000; yêu cầu hoàn 600.000.

T1 kiểm tra đạt và gửi hoàn.
T2 kiểm tra đạt và gửi hoàn.

Tổng tác động có thể là 1.200.000.
```

Mỗi phép so sánh riêng lẻ đều có thể đúng trên dữ liệu đã đọc. Điểm thiếu là cơ chế nhận quyền sử dụng phần còn lại một cách nguyên tử.

### 3.2. Giữ chỗ là một thay đổi nghiệp vụ

Khi cấp yêu cầu mới, `R` tăng trước khi tác động bên ngoài được thực hiện. Khi hoàn thành công:

```text
R := R - q
F := F + q
```

Tổng `F + R` không đổi trong bước quyết toán thành công. Nếu xác định chắc chắn không có tác động và không còn khả năng thực hiện tương ứng, có thể giải phóng phần giữ chỗ theo hợp đồng.

Timeout không tự đủ điều kiện để giải phóng. Nếu nhà cung cấp đã xử lý nhưng phản hồi bị mất, trả `R` sớm có thể cho một yêu cầu khác dùng cùng ngân sách.

## 4. Chọn nơi thực thi theo quyền sở hữu và khả năng kiểm soát

Một cách chọn điểm thực thi là lần lượt xét:

1. Thành phần nào có dữ liệu có thẩm quyền để quyết định?
2. Thành phần nào có quyền chặn hoặc cam kết tác động?
3. Các đường tạo tác động có thực sự đi qua nơi đó không?
4. Cơ chế nào giữ điều kiện trong thời gian từ kiểm tra đến sử dụng?
5. Nếu thành phần khác ghi cùng dữ liệu, quy tắc còn được giữ không?

Với hạn mức hoàn, nơi chỉ biết request mà không biết các lần hoàn đang giữ chỗ không thể tự quyết định đủ. Một service đọc replica có độ trễ cũng không nên xem giá trị đọc được là căn cứ cuối để nhận thêm ngân sách cứng.

Ngược lại, cơ sở dữ liệu có thể giữ quan hệ số học nhưng không tự biết một tài khoản bên ngoài có ý định hợp lệ hay có quyền theo chính sách ứng dụng nếu thông tin đó không được cung cấp và thực thi ở ranh giới phù hợp.

### 4.1. Một bản đồ trách nhiệm

| Nơi | Vai trò phù hợp | Giới hạn |
| --- | --- | --- |
| Giao diện | Hướng dẫn, ngăn thao tác nhầm, hiển thị trạng thái | Không phải ranh giới bảo mật với client có thể điều khiển |
| API boundary | Xác thực, kiểm tra cấu trúc, giới hạn đầu vào, dựng ngữ cảnh | Không tự giải quyết cạnh tranh và mọi đường ghi |
| Application service | Phân quyền theo đối tượng, phối hợp quyết định và transaction | Cần bảo đảm đường khác không bỏ qua |
| Domain model hoặc domain service | Diễn đạt guard, chuyển trạng thái và quy tắc nghiệp vụ | Không tự khóa dữ liệu hoặc chặn SQL ngoài mô hình |
| Repository hoặc lệnh ghi | Cập nhật có điều kiện, phiên bản và phạm vi dữ liệu | Không thay thế toàn bộ chính sách chủ thể |
| Cơ sở dữ liệu | Ràng buộc bền vững và tính nguyên tử trong phạm vi hỗ trợ | Không tự bao phủ tác động ngoài hoặc mọi chính sách động |
| Worker và nơi nhận tác động | Kiểm tra quyền thực thi, xử lý trùng và kết quả | Không được coi mọi message là một quyết định đã được cấp |

Không cần sao chép mọi quy tắc ở mọi tầng. Cần một phân công rõ, có điểm quyết định chính và các bảo đảm bổ trợ phù hợp.

## 5. Ranh giới API: dựng ngữ cảnh, không nhận thẩm quyền từ payload

Một request hoàn tiền có thể chứa mã khoản thanh toán, số tiền, tiền tệ và khóa thao tác. Các giá trị ấy là đề xuất hoặc định danh do client gửi.

Máy chủ cần:

- Lấy danh tính từ ngữ cảnh xác thực.
- Xác minh tổ chức hiện hành mà tài khoản được phép đại diện.
- Chuẩn hóa số tiền và kiểm tra đơn vị tiền.
- Giới hạn các trường client được phép đặt.
- Không nhận `approvedBy`, `role` hoặc `skipLimit` như bằng chứng quyền.
- Đưa lệnh vào đường thực thi giữ các invariant liên quan.

Kiểm tra số tiền dương ở đây là hữu ích. Nhưng việc request có số tiền đúng kiểu chưa chứng minh còn ngân sách hoặc người gọi được phép hoàn khoản thanh toán đó.

Nếu sản phẩm có ngoại lệ quản trị, ngoại lệ phải có nguồn cấp quyền và phạm vi riêng. Một trường boolean trong payload không tự là một quyết định ngoại lệ.

### 5.1. Danh tính dịch vụ cũng cần phạm vi

Một worker có thể dùng credential riêng, nhưng vẫn phải thực hiện đúng lệnh đã được cấp cho tổ chức và đối tượng tương ứng.

Quyền truy cập cơ sở dữ liệu hoặc broker của worker không tự trở thành quyền nghiệp vụ để hoàn bất kỳ khoản tiền nào. Cần giữ được người hoặc nguồn khởi xướng, dịch vụ thực thi và cơ sở thẩm quyền của công việc.

## 6. Application service và domain: quyết định theo ngữ cảnh

Application service thường phù hợp để phối hợp các điều kiện:

```text
Chủ thể có quyền yêu cầu hoàn khoản này.
Khoản thanh toán thuộc đúng tổ chức và phạm vi.
Nghĩa vụ ở trạng thái cho phép theo chính sách.
Nếu cần phê duyệt hoàn tiền, quyết định còn áp dụng.
Số tiền và tiền tệ có ý nghĩa hợp lệ.
Thao tác chưa được thực hiện hoặc được nhận diện là replay.
Ngân sách được giữ chỗ bằng cơ chế nguyên tử.
```

Domain model có thể diễn đạt những chuyển trạng thái như:

```text
REQUESTED → RESERVED → SUBMITTING → SUCCEEDED
                              ↘ UNKNOWN
                              ↘ FAILED_FINAL
```

Tên trạng thái cần có ngữ nghĩa rõ. `FAILED_FINAL` trong ví dụ phải có căn cứ rằng lần thực hiện tương ứng không còn gây tác động, theo giao thức và bằng chứng tích hợp; một lỗi mạng đơn thuần không đáp ứng điều đó.

### 6.1. Guard trong domain không tự bảo vệ dữ liệu dùng chung

Một phương thức `payment.canRefund(q)` có thể giúp diễn đạt quy tắc. Nếu entity được tải từ dữ liệu cũ và không có cơ chế phối hợp khi ghi, hai instance vẫn có thể cùng cho phép vượt tổng.

Cần nối quy tắc domain với một điểm ghi có bảo đảm cạnh tranh phù hợp: khóa bản ghi liên quan, optimistic locking, cập nhật có điều kiện hoặc cơ chế khác tương ứng.

### 6.2. Kiểm tra quyền cũng có thời điểm hiệu lực

Nếu quyền hoặc phê duyệt có thể đổi đồng thời, phải xác định quyết định dùng quyền hiện tại đến thời điểm nào, hoặc sử dụng một quyền thực thi đã cấp có phạm vi riêng.

Nếu yêu cầu thu hồi phải có hiệu lực trước khi nhận cam kết mới, dữ liệu quyết định quyền và thao tác cấp cam kết phải được phối hợp theo hợp đồng đó. Chỉ đọc quyền trước transaction rồi bỏ qua mọi thay đổi sau không tự đáp ứng yêu cầu.

## 7. Repository và cơ sở dữ liệu: thực thi giới hạn khi ghi

Với ví dụ hoàn tiền, có thể dùng một bản ghi số dư theo khoản thanh toán và tổ chức. Tiền được lưu theo đơn vị nguyên nhỏ nhất mà ứng dụng đã quy định cho tiền tệ đó.

Ví dụ cấu trúc rút gọn:

```sql
CREATE TABLE payment_refund_balance (
    tenant_id       VARCHAR(64) NOT NULL,
    payment_id      VARCHAR(64) NOT NULL,
    currency        VARCHAR(3)  NOT NULL,
    captured_minor  BIGINT      NOT NULL,
    refunded_minor  BIGINT      NOT NULL,
    reserved_minor  BIGINT      NOT NULL,

    PRIMARY KEY (tenant_id, payment_id),

    CHECK (captured_minor >= 0),
    CHECK (refunded_minor >= 0),
    CHECK (reserved_minor >= 0),
    CHECK (refunded_minor <= captured_minor),
    CHECK (reserved_minor <= captured_minor - refunded_minor)
);
```

Trong mô hình đơn giản này, `captured_minor` là giới hạn hoàn được cấp từ khoản thu đã xác nhận. Quy tắc chuyển đổi tiền tệ, khởi tạo số dư và điều chỉnh giới hạn phải được quản lý ở đường có thẩm quyền.

Các cột bắt buộc có `NOT NULL` để không để giá trị thiếu làm sai cách diễn giải điều kiện. Kiểu số và giới hạn đầu vào phải đủ để các phép toán không tràn.

### 7.1. Cập nhật có điều kiện là điểm cấp ngân sách

```sql
UPDATE payment_refund_balance
SET reserved_minor = reserved_minor + :amountMinor
WHERE tenant_id = :trustedTenantId
  AND payment_id = :paymentId
  AND currency = :validatedCurrency
  AND :amountMinor > 0
  AND :amountMinor <= captured_minor - refunded_minor - reserved_minor;
```

Ứng dụng chỉ được xem là đã giữ chỗ khi số dòng bị ảnh hưởng đúng theo hợp đồng. Không có dòng được cập nhật có thể do thiếu số dư, sai phạm vi hoặc tiền tệ; không được tiếp tục gửi hoàn như thể đã được cấp.

Cập nhật này nhằm làm cho quyết định cấp số tiền và việc tăng giữ chỗ được thực hiện cùng một thao tác có điều kiện. Cần kiểm tra ngữ nghĩa cạnh tranh của hệ quản trị và cấu hình sử dụng thực tế.

Ràng buộc `CHECK` là bảo đảm bổ trợ ở trạng thái được lưu, không thay thế kiểm tra kết quả lệnh ghi. Việc báo lỗi ràng buộc cũng cần được xử lý đúng để transaction không để lại thay đổi dở dang.

### 7.2. SQL này không chứng minh toàn bộ quyền nghiệp vụ

Câu lệnh biết tổ chức, khoản thanh toán, tiền tệ và số dư. Nó chưa tự biết người gọi có quyền hoàn tiền, quyết định phê duyệt có hợp lệ hay có đang áp dụng một ngoại lệ không.

Những điều kiện đó phải được thực thi ở điểm có thông tin tương ứng. Nếu trạng thái đủ điều kiện hoàn có thể thay đổi đồng thời, cần đưa nó vào cơ chế khóa, điều kiện ghi hoặc giao thức phiên bản phù hợp.

Một invariant thường cần sự phối hợp của nhiều điểm, nhưng phải biết mỗi điểm giữ phần nào.

### 7.3. Ràng buộc tham chiếu và tính duy nhất

Ngoài quan hệ số học, có thể cần:

- Khóa duy nhất cho thao tác logic trong phạm vi được định nghĩa.
- Quan hệ giữa reservation và đúng khoản thanh toán của đúng tổ chức.
- Cách ngăn một kết quả nhà cung cấp bị áp dụng hai lần.
- Ràng buộc trạng thái hoặc phiên bản trên các thay đổi liên quan.

Nếu mã đối tượng chỉ duy nhất trong tổ chức, các khóa và quan hệ tham chiếu phải giữ cả phạm vi đó. Một foreign key chỉ trỏ vào mã không đúng phạm vi có thể không thể hiện được quan hệ nghiệp vụ cần bảo vệ.

## 8. Một transaction cho cam kết cục bộ hoàn chỉnh

Giữ chỗ thành công nhưng không tạo reservation khiến khó quyết toán. Tạo reservation nhưng không có thông điệp bền vững có thể làm công việc mất đường thực thi.

Một transaction tiếp nhận có thể gồm:

```text
BEGIN
  Kiểm tra chủ thể, đối tượng và điều kiện nghiệp vụ.
  Nhận diện thao tác lặp trong đúng phạm vi.
  Giữ số tiền bằng cập nhật có điều kiện.
  Tạo reservation gắn với khoản thanh toán và thao tác.
  Lưu kết quả idempotency theo hợp đồng.
  Ghi outbox cho công việc cần thực hiện.
  Ghi audit bắt buộc cho cam kết.
COMMIT
```

### 8.1. Minh họa service Java

Đoạn sau thể hiện sự phối hợp, không phải một tích hợp hoàn tiền hoàn chỉnh. Các repository phải tham gia cùng transaction; ngữ cảnh actor đã được xác thực và phạm vi truy cập phải được xác minh ở máy chủ.

```java
@Transactional
public RefundAccepted reserveRefund(
        VerifiedActor actor,
        RefundCommand command) {

    RefundScope scope = policy.resolveRefundScope(
            actor, command.paymentId());

    PaymentView payment = payments.findInScope(
                    scope, command.paymentId())
            .orElseThrow(PaymentNotVisibleException::new);

    policy.requireRefundAllowed(actor, payment, command);

    var replay = idempotency.findAuthorizedReplay(
            actor, payment, command);
    if (replay.isPresent()) {
        return replay.get();
    }

    Money amount = moneyPolicy.validateFor(payment, command);

    int changed = balances.reserveIfAvailable(
            payment.tenantId(),
            payment.id(),
            amount.currency(),
            amount.minorUnits());

    if (changed != 1) {
        throw new RefundReservationRejectedException();
    }

    RefundReservation reservation = reservations.create(
            actor, payment, amount, command.operationKey());

    RefundAccepted result = RefundAccepted.from(reservation);
    idempotency.recordResult(actor, command, result);
    outbox.append(RefundRequested.from(reservation));
    audit.append(RefundReserved.from(actor, reservation));

    return result;
}
```

Những hợp đồng cần được triển khai rõ:

- Quyền và dữ liệu đủ điều kiện không bị dùng ngoài ranh giới hiệu lực đã chọn.
- Replay được ràng buộc với đúng chủ thể hoặc phạm vi truy cập, hành động và nội dung.
- Hai request cùng tranh một khóa phải được xử lý bằng cơ chế nguyên tử, chẳng hạn ràng buộc duy nhất và xử lý xung đột phù hợp.
- Nếu trùng khóa bị phát hiện sau khi đã tăng giữ chỗ, transaction thua phải rollback phần tăng đó.
- Mọi lỗi cần rollback phải có hành vi tương ứng theo cấu hình transaction.
- Số tiền giữ chỗ chính là số tiền reservation và thông điệp được phép thực thi.
- Cơ chế giữ chỗ không bị bỏ qua ở một nhánh đặc biệt trong cùng service.

Một request kiểm tra trước rằng khóa chưa tồn tại rồi mới ghi không tự chống được cạnh tranh. Tương tự, một annotation transaction không tự chứng minh mọi repository đang dùng cùng nguồn dữ liệu và ranh giới commit.

### 8.2. Outbox bảo vệ việc chuyển tiếp, không tạo tính nguyên tử với bên ngoài

Outbox lưu thông điệp cần gửi cùng transaction với cam kết. Publisher đọc dữ liệu đã commit rồi chuyển tiếp, có thể retry nếu đích tạm ngừng.

Thông điệp có thể được gửi lại. Worker và nơi ghi nhận kết quả vẫn phải xử lý trùng theo định danh ổn định và trạng thái phù hợp.

Transaction cục bộ không rollback được khoản hoàn mà nhà cung cấp đã thực hiện. Phần đó cần mô hình riêng.

## 9. Nơi thực hiện tác động và nơi ghi nhận kết quả

Một reservation hợp lệ phải được chuyển thành đúng tác động đã được cấp:

```text
Reservation của tổ chức A, khoản P, số tiền q, tiền tệ C
→ worker thực thi đúng nghĩa vụ đó
→ nhà cung cấp xác nhận hoặc kết quả còn chưa rõ
→ hệ thống quyết toán đúng reservation.
```

Worker không được tùy ý lấy số tiền mới từ message do nguồn khác ảnh hưởng, đổi khoản thanh toán hoặc coi mọi công việc là thẩm quyền hoàn tiền.

### 9.1. Điểm thực thi khi gửi nhà cung cấp

Cần xác minh:

- Reservation có tồn tại và thuộc trạng thái được phép nhận việc.
- Lần thực thi liên kết đúng nghĩa vụ và tham số.
- Quyền thực thi của workload hoặc lệnh còn phù hợp theo chính sách.
- Việc nhận việc và retry không tạo một tác động độc lập ngoài hợp đồng.
- Định danh chống trùng được dùng nhất quán với nhà cung cấp nếu có cơ chế tương ứng.

Nếu credential của nhà cung cấp có thể được một đường khác sử dụng để hoàn tiền không qua reservation, bảo đảm ở sổ nội bộ không tự bao phủ đường đó. Phạm vi quyền và những đường phát sinh tác động phải được mô hình hóa đầy đủ.

### 9.2. Điểm thực thi khi quyết toán

Khi xác nhận thành công, cần chuyển reservation sang trạng thái thành công và cập nhật `R`, `F` nhất quán, không áp dụng lại khi callback lặp.

Khi nhận thất bại cuối cùng, chỉ giải phóng phần giữ chỗ mà hợp đồng xác định có thể trả. Khi chưa rõ kết quả, tiếp tục biểu diễn trạng thái chưa rõ và đối soát thay vì mặc định đã thất bại.

Các cập nhật trạng thái reservation và số dư phải được phối hợp nguyên tử hoặc bằng giao thức có bảo đảm tương ứng. Nếu hai callback cùng giảm `R`, bộ đếm có thể âm hoặc ngân sách bị cấp lại sai.

### 9.3. Không giải phóng chỉ vì lease hoặc timeout hết hạn

Worker cũ có thể vẫn đang thực thi sau khi mất kết nối. Một lease hết hạn là tín hiệu về quyền sở hữu xử lý, không tự là bằng chứng tác động đã dừng.

Cần cơ chế nhận việc, chặn chủ sở hữu cũ hoặc xác minh kết quả phù hợp với nơi gây tác động. Không nên dùng một tác vụ dọn dẹp đơn giản để xóa cam kết mà chưa biết tiền đã được hoàn hay chưa.

## 10. Bao phủ mọi đường thay đổi liên quan

Điểm thực thi bị vô hiệu nếu có đường khác tạo cùng tác động mà không đi qua hoặc không giữ điều kiện tương đương.

Các đường cần kiểm kê:

| Đường | Nguy cơ cần xét |
| --- | --- |
| API công khai | Bỏ qua giao diện, sửa payload và gọi trực tiếp |
| Giao diện nhân viên | Có quyền cao hơn nhưng vẫn phải giữ giới hạn tài chính |
| Batch hoặc import | Kiểm tra một phần rồi cập nhật nhiều đối tượng |
| Consumer nội bộ | Tin message mà không kiểm tra nguồn và phạm vi |
| Công cụ retry | Tạo thao tác mới thay vì tiếp tục cùng nghĩa vụ |
| Script vận hành | Ghi trực tiếp và làm lệch sổ giữ chỗ |
| Migration hoặc tác vụ sửa dữ liệu | Cập nhật trạng thái mà không duy trì quan hệ số học |
| Tích hợp đối tác | Dùng credential rộng để tạo tác động ngoài luồng chuẩn |

Một shared library giúp tái sử dụng quy tắc nhưng không ép mọi writer phải gọi nó. Domain model chỉ có private setter cũng không chặn một script SQL có quyền ghi trực tiếp.

Có thể thu hẹp quyền ghi, đưa thao tác nhạy cảm qua một dịch vụ sở hữu dữ liệu hoặc một giao diện lưu trữ được kiểm soát, kết hợp ràng buộc dữ liệu phù hợp. Cần chọn theo kiến trúc và quyền thực tế.

Bảo đảm luôn phụ thuộc vào các chủ thể có khả năng thay đổi dữ liệu hoặc cơ chế thực thi. Nếu một tài khoản có thể sửa cả số dư, reservation và ràng buộc, phải đánh giá quyền đó như một ranh giới quản trị riêng.

## 11. Áp dụng nguyên tắc cho các invariant khác

| Invariant | Điểm quyết định chính cần xem xét | Bảo đảm bổ trợ |
| --- | --- | --- |
| Chỉ đọc đúng đối tượng | Phạm vi truy vấn và quyết định quyền phía máy chủ | Projection, cache và kiểm tra tải file theo phạm vi |
| Không lộ trường nội bộ | Nơi dựng dữ liệu đầu ra cho đúng chủ thể | DTO hoặc danh sách trường rõ, kiểm soát export |
| Không thanh toán khi chưa duyệt | Nơi cấp intent hoặc cam kết có thẩm quyền | Guard trạng thái, snapshot nội dung và outbox |
| Giá không do client tự quyết | Nơi chốt điều khoản có thẩm quyền | Nguồn giá, phiên bản và kiểm tra mọi đường sửa |
| Không xử lý trùng nghĩa vụ | Nơi nhận quyền thực hiện và trạng thái nghiệp vụ | Unique constraint, idempotency và consumer chống trùng |
| Không vượt quota | Nơi cấp phần ngân sách hoặc slot | Giữ chỗ, bộ đếm nguyên tử và vòng đời giải phóng |
| Thay đổi có dấu vết | Transaction hoặc giao thức gắn thay đổi với audit | Kho audit được bảo vệ và chuyển tiếp bền vững |

Với tính bí mật, điểm thực thi không chỉ nằm lúc đọc cơ sở dữ liệu. Nếu một response đúng quyền được cache rồi trả cho người khác, dữ liệu vẫn bị lộ. Tương tự, export và file tải là những nơi tiết lộ mới cần chính sách phù hợp.

Với phê duyệt, kiểm tra `approvedRevision == currentRevision` chỉ có ý nghĩa khi mọi thay đổi nội dung quan trọng đều tăng revision theo đúng giao thức và bản quyết định có nguồn đáng tin. Không thể coi phép so sánh là đủ nếu dữ liệu nền có thể bị sửa ngoài mô hình.

## 12. Những lựa chọn làm điểm thực thi mất hiệu lực

### 12.1. Kiểm tra ở xa tác động nhưng không giữ bằng chứng hoặc phiên bản

Quyết định dựa trên một bản đọc cũ có thể không còn đúng khi ghi. Cần gắn nó với dữ liệu hoặc thẩm quyền có hiệu lực, phát hiện thay đổi hoặc phối hợp quyền truy cập.

### 12.2. Chỉ dựa vào cache cho giới hạn cứng

Cache có thể hỗ trợ hiển thị hoặc giảm tải. Nếu các instance cấp ngân sách từ dữ liệu trễ mà không có cơ chế phối hợp, tổng cam kết có thể vượt mức.

Một thiết kế cho phép vượt có giới hạn có thể phù hợp với quota mềm. Không nên mô tả nó như invariant cứng nếu hợp đồng không cung cấp bảo đảm đó.

### 12.3. Sao chép cùng một phép kiểm tra ở nhiều nơi

Ba tầng cùng so một trường client kiểm soát không tạo thành ba nguồn thẩm quyền. Nhiều phiên bản logic còn dễ lệch khi chính sách thay đổi.

Nên có cách định nghĩa và kiểm thử nhất quán cho quy tắc, đồng thời dùng các bảo đảm có vai trò rõ như giới hạn đầu vào, guard miền và ràng buộc lưu trữ.

### 12.4. Dùng transaction như câu trả lời cho mọi cạnh tranh

Transaction cung cấp bảo đảm theo phạm vi và cấu hình của nó. Một transaction có đọc rồi ghi vẫn có thể không giữ một tổng dùng chung nếu thiếu phối hợp cần thiết.

Cần xác định tài nguyên tranh chấp, mức cô lập, điều kiện cập nhật hoặc phạm vi khóa; không chỉ xác nhận phương thức có annotation.

### 12.5. Cho ngoại lệ bỏ qua toàn bộ quy tắc

Một quản trị viên có thể được phép tăng hạn mức theo quy trình, nhưng không nên vô tình được ghi trạng thái tùy ý khiến sổ không còn nhất quán.

Ngoại lệ cần được mô hình hóa như hành động có quyền, phạm vi, lý do và dấu vết. Nếu thay đổi giới hạn đang có cam kết, phải xử lý phần đã cấp theo chính sách thay vì xóa mức sử dụng.

## 13. Kiểm thử ngay tại nơi quy tắc có thể bị phá

Bộ kiểm thử nên chứng minh bảo đảm của từng điểm và của cả chuỗi.

| Tình huống | Thuộc tính cần xác minh |
| --- | --- |
| Yêu cầu hợp lệ | Có một reservation đúng số tiền và phạm vi |
| Sai tổ chức hoặc đối tượng | Không tiết lộ hoặc thay đổi dữ liệu ngoài quyền |
| Số tiền âm, thiếu hoặc sai đơn vị | Không làm tăng ngân sách hoặc sai phép tính |
| Hai yêu cầu 600.000 trên giới hạn còn 1.000.000 | Tổng giữ chỗ và đã hoàn không vượt giới hạn |
| Nhiều instance | Không phụ thuộc khóa trong bộ nhớ một tiến trình |
| Lỗi sau tăng giữ chỗ | Transaction rollback phần tăng nếu reservation không được commit |
| Hai request cùng khóa | Không có hai cam kết cho cùng thao tác theo hợp đồng |
| Đổi khóa | Không vượt giới hạn hoặc tạo tác động trái nghĩa vụ |
| Outbox chưa chuyển được | Cam kết bền vững và có thể tiếp tục xử lý sau phục hồi |
| Worker nhận message lặp | Không thực hiện thêm tác động độc lập |
| Callback lặp | Không tăng `F` hoặc giảm `R` hai lần |
| Timeout sau khi nhà cung cấp có thể đã xử lý | Không giải phóng phần giữ chỗ chỉ vì thiếu phản hồi |
| Quyền hoặc điều kiện đổi đồng thời | Hành vi đúng ranh giới quyết định đã mô tả |
| Batch, quản trị và script được phép | Các đường vẫn giữ invariant hoặc bị ràng buộc quyền phù hợp |
| Ghi dữ liệu vi phạm trực tiếp bằng tài khoản thử nghiệm được giới hạn | Ràng buộc lưu trữ chặn những trạng thái mà nó có trách nhiệm bảo vệ |

Unit test phù hợp với guard, phép tính và state machine. Integration test cần cho ràng buộc cơ sở dữ liệu, transaction, cạnh tranh và repository. Test ở ranh giới API hoặc consumer cần xác minh danh tính, ánh xạ trường và các đường đi thực tế.

Test concurrency cần phối hợp các luồng để có tranh chấp, không chỉ gọi hai lần tuần tự. Mock repository thường không tái hiện bảo đảm khóa hoặc cập nhật có điều kiện của cơ sở dữ liệu.

Không chỉ kiểm tra mã lỗi. Cần xem trạng thái đã commit, số dư, reservation, outbox và tác động tại thành phần giả lập hoặc môi trường thử nghiệm nhà cung cấp.

## 14. Duy trì điểm thực thi khi hệ thống thay đổi

Một invariant đã được giữ hôm nay có thể mất hiệu lực khi thêm writer, tách service hoặc thay chính sách.

Những thay đổi cần xem xét:

- Một API mới cập nhật cùng dữ liệu.
- Chuyển logic sang worker hoặc batch.
- Tách một cơ sở dữ liệu thành nhiều nơi lưu.
- Dùng cache hoặc replica cho quyết định trước đây lấy từ nguồn chuẩn.
- Thêm hoàn một phần, nhiều tiền tệ hoặc nhiều nhà cung cấp.
- Thay cách thu hồi quyền hoặc hiệu lực phê duyệt.
- Chạy song song nhiều phiên bản ứng dụng trong lúc triển khai.

Nếu phiên bản mới thực thi quy tắc nhưng phiên bản cũ vẫn có quyền ghi theo cách cũ, có thể xuất hiện khoảng trống. Kế hoạch chuyển đổi cần giữ tương thích và bảo đảm cần thiết ở các writer cùng tồn tại.

Tác vụ đối soát có thể phát hiện số dư lệch với sổ reservation. Việc sửa cũng phải phối hợp với thay đổi đang chạy, có nguồn thẩm quyền và dấu vết; không nên tính lại rồi ghi đè giữa lúc có giao dịch mới.

Quan sát các lần từ chối, lỗi ràng buộc, giữ chỗ tồn lâu và chênh lệch sổ giúp phát hiện vấn đề. Những tín hiệu này hỗ trợ vận hành; chúng không thay thế điểm thực thi chủ động.

## 15. Ghi rõ hợp đồng cho mỗi điểm thực thi

Một hồ sơ ngắn có thể gồm:

| Trường | Ví dụ với giới hạn hoàn |
| --- | --- |
| Invariant | `F + R <= P` theo khoản thanh toán và tổ chức |
| Nguồn có thẩm quyền | Số dư và reservation được quản lý ở nơi lưu đã chọn |
| Điểm cấp cam kết | Cập nhật giữ chỗ có điều kiện trong transaction tiếp nhận |
| Điều kiện ngoài số học | Quyền đối tượng, trạng thái, tiền tệ và phê duyệt nếu cần |
| Điểm bảo vệ bổ trợ | Ràng buộc dữ liệu, định danh thao tác, consumer và quyết toán |
| Đường phải đi qua | API, nhân viên, batch, worker và công cụ được cấp quyền |
| Khi không đủ điều kiện | Không cấp cam kết; thay đổi dở dang rollback theo hợp đồng |
| Khi kết quả ngoài chưa rõ | Giữ trạng thái và giữ chỗ cần thiết để đối soát |
| Bằng chứng | Test cạnh tranh, rollback, retry và kiểm tra tác động |
| Giả định còn tin cậy | Nguồn xác nhận, quyền ghi dữ liệu và nơi thực hiện tác động |

Với một quy tắc mới, có thể làm theo trình tự:

1. Phát biểu điều kiện, phạm vi và thời điểm phải đúng.
2. Xác định dữ liệu cùng chủ thể có thẩm quyền.
3. Kiểm kê mọi đường có thể tạo thay đổi hoặc tiết lộ liên quan.
4. Chọn nơi có thể chặn hoặc cấp tác động.
5. Phối hợp kiểm tra và ghi bằng cơ chế phù hợp.
6. Bổ sung ràng buộc và kiểm soát ở các ranh giới cần thiết.
7. Mô hình hóa retry, lỗi, thu hồi và kết quả chưa rõ.
8. Kiểm thử tại đúng nơi bảo đảm có thể bị phá.

Một invariant được thực thi khi các đường liên quan không thể tạo trạng thái hoặc tác động trái hợp đồng trong phạm vi giả định đã chọn. Chọn đúng điểm thực thi giúp nối quy tắc nghiệp vụ với quyền, dữ liệu và cơ chế nguyên tử thực sự bảo vệ nó.
