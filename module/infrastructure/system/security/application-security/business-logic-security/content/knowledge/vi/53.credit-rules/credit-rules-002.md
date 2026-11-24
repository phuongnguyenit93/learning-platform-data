# Credit allocation: phân bổ credit an toàn theo quy tắc nghiệp vụ

## 1. Mục tiêu và phạm vi

Trong chương **Credit Rules**, credit allocation là việc cấp một lượng credit từ nguồn có thẩm quyền cho một đối tượng được phép sử dụng. Credit có thể đại diện cho lượt gọi API, tài nguyên xử lý, lượt sử dụng tính năng hoặc đơn vị ưu đãi nội bộ. Một yêu cầu cấp phát thành công làm thay đổi quyền sử dụng tài nguyên, vì vậy đây là thao tác nhạy cảm về logic nghiệp vụ.

Ví dụ xuyên suốt bài học: một tổ chức có ngân sách 10.000 credit cho một kỳ. Quản trị viên phân bổ credit cho các thành viên; thành viên dùng credit để chạy tác vụ. Mục tiêu là bảo đảm không ai tự cấp thêm credit, vượt hạn mức, nhận credit của tổ chức khác hoặc lợi dụng retry và yêu cầu đồng thời để được cấp nhiều lần.

Bài học sử dụng credit như một đơn vị tài nguyên nội bộ, không mô hình hóa khoản vay, đánh giá tín dụng hay sản phẩm tài chính. Nếu credit quy đổi thành tiền hoặc tài nguyên có giá trị, mọi quy tắc cấp phát vẫn phải do phía máy chủ quyết định.

Sau bài học, bạn cần có khả năng:

- Phân biệt cấp phát với giữ chỗ, sử dụng và thu hồi credit.
- Viết các bất biến nghiệp vụ có thể kiểm tra tại thời điểm commit.
- Gắn quyền cấp phát với tenant, nguồn ngân sách, người nhận và trạng thái phê duyệt.
- Thiết kế transaction chống cấp vượt ngân sách khi có nhiều yêu cầu đồng thời.
- Kết hợp idempotency với định danh nghiệp vụ để ngăn cấp lặp.
- Xây dựng các tình huống kiểm thử theo hành vi lạm dụng.

## 2. Phân biệt các thao tác trong vòng đời credit

### 2.1. Cấp phát không đồng nghĩa với tiêu thụ

Giả sử ngân sách chung còn 10.000 credit. Khi cấp 300 credit cho An, ngân sách chung còn 9.700 và An có 300 credit khả dụng. Khi An dùng 40 credit, ngân sách chung vẫn còn 9.700; trong phần đã cấp cho An có 260 khả dụng và 40 đã tiêu thụ.

Nếu trừ ngân sách chung lần nữa khi sử dụng, hệ thống tính trùng. Nếu cộng trả ngân sách ngay sau khi cấp trong khi người nhận vẫn giữ quyền sử dụng, hệ thống tạo ra credit không có nguồn.

| Thao tác | Ý nghĩa | Biến đổi trong ví dụ |
| --- | --- | --- |
| Allocate | Chuyển quyền sử dụng từ ngân sách chung sang người nhận | Chung −300, khả dụng của An +300 |
| Reserve | Giữ chỗ cho một tác vụ chưa hoàn tất | Khả dụng −50, giữ chỗ +50 |
| Consume | Xác nhận tác vụ đã tiêu thụ phần giữ chỗ | Giữ chỗ −40, đã dùng +40 |
| Release | Hủy phần giữ chỗ chưa dùng | Giữ chỗ −10, khả dụng +10 |
| Reclaim | Thu hồi phần đã cấp nhưng chưa bị ràng buộc | Khả dụng −100, ngân sách chung +100 |
| Refund | Hoàn lại phần đã tiêu thụ theo chính sách | Phải xác định rõ hoàn về người nhận hay nguồn chung |

Refund không tự động có nghĩa là tạo thêm ngân sách. Nếu hoàn từ phần đã dùng về phần khả dụng, đó là chuyển credit giữa hai trạng thái trong cùng nguồn và cùng kỳ.

### 2.2. Xác định đơn vị và ranh giới ngân sách

Mỗi pool, tức nguồn ngân sách, phải có:

- Tenant sở hữu.
- Kỳ ngân sách, chẳng hạn một mã kỳ bất biến.
- Loại credit và đơn vị tính.
- Tổng ngân sách, phần còn có thể phân bổ và trạng thái hoạt động.
- Chính sách người nhận, hạn mức và phê duyệt.

Không cộng credit của hai đơn vị khác nhau chỉ vì cùng là số nguyên. Credit chạy mô hình A và credit lưu trữ có thể có giá trị sử dụng khác nhau. Nếu có chuyển đổi, tỷ lệ và quy tắc làm tròn phải lấy từ cấu hình có thẩm quyền, được lưu cùng giao dịch.

Trong ví dụ này, credit là số nguyên dương. Java dùng `long`, PostgreSQL dùng `BIGINT`. Hệ thống phải từ chối số lẻ, số âm, số 0, giá trị ngoài miền cho phép và phép tính tràn số. Nếu nghiệp vụ cần phần lẻ, hãy định nghĩa đơn vị nhỏ nhất hoặc dùng kiểu thập phân chính xác; không dùng số thực dấu phẩy động cho số dư.

## 3. Viết business invariants trước khi viết API

### 3.1. Bảo toàn ngân sách

Xét một pool trong một tenant, một kỳ và một đơn vị:

- `B`: ngân sách của pool.
- `F`: credit còn tự do để phân bổ.
- `A_i`: credit khả dụng của allocation thứ `i`.
- `R_i`: credit đang giữ chỗ của allocation thứ `i`.
- `C_i`: credit đã tiêu thụ của allocation thứ `i`.

Với tập allocation thuộc pool đó:

~~~text
B = F + Σ(A_i + R_i + C_i)

B >= 0
F >= 0
A_i >= 0
R_i >= 0
C_i >= 0
~~~

Đây là mô hình ngân sách trong một kỳ cố định: credit đã dùng vẫn nằm trong tổng ngân sách đã được cam kết, nên không tự quay lại phần tự do.

Nếu allocation có `G_i` là lượng cấp ban đầu và `T_i` là lượng đã thu hồi về pool:

~~~text
G_i = A_i + R_i + C_i + T_i
T_i >= 0
~~~

Khi cấp thêm `x`:

~~~text
Điều kiện: x > 0 và F >= x
F' = F - x
Tạo allocation: G = x, A = x, R = 0, C = 0, T = 0
~~~

Khi thu hồi `x` credit khả dụng:

~~~text
Điều kiện: x > 0 và A_i >= x
A_i' = A_i - x
T_i' = T_i + x
F' = F + x
~~~

Không thu hồi trực tiếp credit đang giữ chỗ hoặc đã tiêu thụ. Muốn xử lý chúng phải đi qua quy trình hủy reservation hoặc refund có điều kiện riêng.

### 3.2. Hạn mức của người nhận

Giả sử người nhận có hạn mức `Q_u` trong pool này:

~~~text
U_u = Σ(A_i + R_i + C_i), với allocation i thuộc người nhận u
0 <= U_u <= Q_u
~~~

Khi cấp `x`, điều kiện phải là `U_u + x <= Q_u`. Kiểm tra chỉ số dư khả dụng là sai vì phần đã dùng hoặc đang giữ chỗ vẫn chiếm hạn mức của kỳ.

Ví dụ người nhận có hạn mức 500, đã dùng 400 và còn 100 khả dụng. Nếu chỉ thấy số dư 100 rồi cấp thêm 400, tổng cam kết trở thành 900 dù hạn mức vẫn là 500.

Trong mô hình này, thu hồi phần chưa dùng làm giảm `U_u`. Nếu chính sách còn giới hạn **tổng cấp phát tích lũy** trong kỳ, phải có bộ đếm riêng chỉ tăng khi cấp. Không dùng `U_u` thay cho bộ đếm tích lũy, vì chuỗi cấp rồi thu hồi có thể lặp nhiều lần.

### 3.3. Các bất biến về quyền và nguồn

Mỗi giao dịch cấp phát phải đồng thời thỏa mãn:

1. Actor được xác thực và còn quyền cấp trên pool cụ thể.
2. Pool, người nhận, bản ghi hạn mức và quyết định phê duyệt thuộc cùng tenant.
3. Người nhận còn đủ điều kiện nhận loại credit này.
4. Pool đang mở và nằm trong thời gian hiệu lực.
5. Lượng cấp nằm trong giới hạn của actor, của người nhận và của ngân sách.
6. Nếu phải phê duyệt, quyết định còn hiệu lực, khớp đúng nội dung yêu cầu và chưa được sử dụng.
7. Một lệnh nghiệp vụ chỉ tạo một hiệu ứng cấp phát.
8. Mọi thay đổi số dư có bằng chứng truy vết được ghi bền vững trong cùng transaction.

Các bất biến phải đúng khi transaction commit. Một lần kiểm tra trước đó trong controller không bảo đảm chúng vẫn đúng sau khi chờ khóa hoặc sau khi trạng thái phê duyệt thay đổi.

### 3.4. Nạp thêm và chuyển kỳ là thao tác riêng

Nếu cho phép tăng ngân sách, phải tăng `B` và `F` cùng lượng trong một transaction được ủy quyền và có chứng từ. Không chỉ sửa `F`.

Khi chuyển kỳ, tạo pool hoặc danh tính kỳ mới theo chính sách. Không sửa mã kỳ của pool cũ đang chứa allocation và reservation. Carry-over, nếu có, là giao dịch chuyển nguồn được ghi rõ; không âm thầm cộng số dư từ kỳ trước.

## 4. Mô hình đe dọa và ranh giới tin cậy

### 4.1. Những gì client không được quyết định

Client có thể gửi ý định “cấp 120 credit cho người nhận này”. Client không được tự xác nhận các dữ kiện sau:

~~~json
{
  "tenantId": "tenant-khac",
  "actorRole": "ADMIN",
  "approved": true,
  "poolRemaining": 999999,
  "recipientLimit": 999999,
  "conversionRate": 100,
  "skipApproval": true
}
~~~

Các trường trên phải bị từ chối hoặc không có trong DTO của lệnh cấp phát. Tenant và actor lấy từ ngữ cảnh xác thực đã được kiểm chứng; ngân sách, hạn mức, vai trò và phê duyệt lấy từ dữ liệu có thẩm quyền.

Một yêu cầu tối giản có thể là:

~~~http
POST /credit-pools/{poolId}/allocations
Authorization: Bearer <access-token>
Idempotency-Key: <client-generated-key>
Content-Type: application/json

{
  "beneficiaryId": "user-123",
  "units": 120,
  "commandRef": "approved-request-456",
  "reason": "Ngân sách chạy thử nghiệm"
}
~~~

`commandRef` là định danh của lệnh nghiệp vụ hoặc yêu cầu đã được hệ thống tạo và xác thực. Việc client gửi một chuỗi trông giống mã phê duyệt không chứng minh rằng phê duyệt tồn tại.

Với luồng cấp trực tiếp không cần phê duyệt, server vẫn cần quy tắc xác định danh tính của lần cấp nếu nghiệp vụ đòi hỏi chống lặp độc lập với khóa HTTP. Ví dụ cấp định kỳ có thể dùng danh tính duy nhất gồm pool, người nhận, kỳ và mã chương trình.

### 4.2. Tấn công thường gặp

| Hành vi lạm dụng | Lỗ hổng thường gặp | Ràng buộc cần có |
| --- | --- | --- |
| Đổi người nhận sang tài khoản thuộc tenant khác | Chỉ kiểm tra role chung | Phân quyền theo pool và người nhận; khóa ngoại cùng tenant |
| Tự gửi `approved=true` | Tin trạng thái từ payload | Đọc và tiêu thụ quyết định phê duyệt tại server |
| Cấp số âm để làm tăng nguồn chung | Không kiểm tra miền giá trị | Validate `units > 0` và constraint tại cơ sở dữ liệu |
| Gửi hai lệnh cùng lúc | Đọc số dư rồi ghi mà không đồng bộ | Khóa hoặc cập nhật có điều kiện trong transaction |
| Retry sau timeout | Mỗi lần gọi tạo một allocation | Idempotency bền vững |
| Đổi idempotency key cho cùng lệnh đã duyệt | Chỉ chống lặp theo HTTP key | Unique theo định danh nghiệp vụ và tiêu thụ phê duyệt một lần |
| Chia nhỏ lượng cấp để né phê duyệt | Ngưỡng chỉ xét từng request | Hạn mức tích lũy theo phạm vi và khoảng thời gian của chính sách |
| Hủy rồi cấp lại liên tục để nhận thưởng | Gắn thưởng vào sự kiện cấp thô | Quy tắc thưởng theo quyền lợi thực và định danh chiến dịch |
| Gọi endpoint nội bộ cũ | Chỉ endpoint mới có kiểm tra | Mọi đường ghi dùng chung ranh giới lệnh nghiệp vụ |

Rate limiting hỗ trợ giảm lạm dụng nhưng không thay thế các ràng buộc về quyền, hạn mức và bảo toàn ngân sách. Hai request hợp lệ trong giới hạn tốc độ vẫn có thể gây cấp vượt nếu transaction sai.

## 5. Phân quyền theo đối tượng và phê duyệt

### 5.1. Role là điều kiện đầu vào

Một actor có role quản trị không mặc nhiên được cấp mọi loại credit cho mọi tổ chức.

| Chủ thể | Khả năng điển hình | Điều kiện trên đối tượng |
| --- | --- | --- |
| Thành viên | Xem credit của mình, yêu cầu được cấp | Là chủ sở hữu hoặc có quyền đọc được ủy quyền |
| Người phân bổ | Cấp trong hạn mức được giao | Pool thuộc phạm vi quản lý; người nhận đủ điều kiện |
| Người phê duyệt | Duyệt yêu cầu cần kiểm soát bổ sung | Có thẩm quyền với pool và mức cấp cụ thể |
| Tác vụ tự động | Cấp theo chương trình định kỳ | Đúng service identity, tenant, kỳ và mã chương trình |
| Kiểm toán viên | Đọc lịch sử và đối soát | Có quyền đọc phạm vi cần kiểm tra |

Chính sách có thể cấm tự cấp hoặc cấm tự phê duyệt. Điều đó phải được kiểm tra bằng quan hệ giữa actor và người nhận hoặc người tạo yêu cầu, không chỉ bằng tên role.

Mọi truy vấn lấy đối tượng bằng ID phải mang theo tenant hoặc một điều kiện phân quyền tương đương:

~~~sql
SELECT *
FROM credit_pool
WHERE tenant_id = :tenant_id
  AND pool_id = :pool_id;
~~~

Không lấy pool theo `pool_id` rồi tin rằng UUID khó đoán sẽ ngăn truy cập sai đối tượng. UUID không thay thế kiểm tra quyền.

### 5.2. Ràng buộc nội dung đã duyệt

Quyết định phê duyệt phải gắn với ít nhất:

- Tenant, pool, kỳ và loại credit.
- Người nhận hoặc tập người nhận đã xác định.
- Lượng credit hoặc giới hạn được duyệt.
- Phiên bản nội dung yêu cầu.
- Người phê duyệt, thời hạn hiệu lực và trạng thái.

Nếu sửa người nhận hoặc số lượng sau khi duyệt, yêu cầu phải quay lại trạng thái chờ duyệt hoặc tạo phiên bản mới. Không áp dụng dấu duyệt cũ cho nội dung đã đổi.

Một mô hình tối giản:

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> PENDING: Gửi yêu cầu
    PENDING --> APPROVED: Người có thẩm quyền duyệt
    PENDING --> REJECTED: Từ chối
    APPROVED --> ALLOCATED: Cấp và tiêu thụ phê duyệt
    APPROVED --> CANCELLED: Hủy trước khi cấp
    APPROVED --> EXPIRED: Quá thời hạn
    ALLOCATED --> [*]
    REJECTED --> [*]
    CANCELLED --> [*]
    EXPIRED --> [*]
~~~

`ALLOCATED` có nghĩa hiệu ứng cấp phát đã commit. Nó không đồng nghĩa người nhận đã tiêu thụ credit.

Trong transaction cấp phát, khóa bản ghi phê duyệt, kiểm tra trạng thái và nội dung rồi chuyển `APPROVED → ALLOCATED` cùng lúc với cập nhật ngân sách. Một request khác không được dùng lại phê duyệt đó.

Nếu chính sách cho phép phê duyệt một trần dùng nhiều lần, phải mô hình hóa `approved_units` và `consumed_units`, đồng thời kiểm tra phần còn được phép ngay trong transaction. Không dùng mô hình phê duyệt một lần rồi diễn giải tùy ý thành phê duyệt nhiều lần.

### 5.3. Quyền thay đổi trong khi giao dịch chạy

Kiểm tra quyền sớm giúp từ chối nhanh, nhưng quyết định cuối cùng phải xét trạng thái nghiệp vụ dưới cơ chế đồng bộ phù hợp.

Nếu yêu cầu “việc thu hồi quyền phải có hiệu lực trước mọi lần cấp tiếp theo”, thao tác thu hồi và cấp phát cần dùng chung một điểm đồng bộ, chẳng hạn khóa bản ghi quyền hoặc kiểm tra phiên bản chính sách theo một giao thức nhất quán. Chỉ gọi dịch vụ kiểm tra quyền trước transaction không tạo ra bảo đảm đó.

Các thay đổi như đóng pool, hạ hạn mức hay thu hồi phê duyệt cũng phải tham gia giao thức khóa được chọn. Không thiết kế riêng endpoint cấp phát rồi để tác vụ quản trị bỏ qua cùng các điều kiện.

## 6. Trạng thái allocation, reservation và hết hạn

### 6.1. Allocation có nhiều phần số dư

Một allocation có thể vừa có phần khả dụng, phần đang giữ chỗ và phần đã dùng. Vì vậy một trường trạng thái đơn giản như `ACTIVE/USED` không đủ thay cho các thành phần số dư.

Bản ghi allocation nên giữ lượng cấp gốc và các thành phần `available`, `reserved`, `spent`, `returned`. Trạng thái phục vụ việc chặn thao tác mới hoặc mô tả vòng đời; số lượng vẫn là dữ liệu quyết định mức chuyển được phép.

Reservation có định danh riêng và chuyển trạng thái một chiều:

~~~mermaid
stateDiagram-v2
    [*] --> HELD: available sang reserved
    HELD --> CONSUMED: reserved sang spent
    HELD --> RELEASED: reserved sang available
    HELD --> EXPIRED: Giải phóng theo chính sách
    CONSUMED --> [*]
    RELEASED --> [*]
    EXPIRED --> [*]
~~~

Ví dụ trên mô hình hóa một reservation được quyết toán một lần. Nếu cho phép tiêu thụ từng phần, phải bổ sung bộ đếm và ràng buộc riêng cho tổng lượng đã quyết toán; không lặp lại chuyển toàn bộ `HELD → CONSUMED`.

Chỉ một trong các thao tác consume, release hoặc expire được thắng khi tranh chấp cùng reservation. Cần khóa hàng hoặc cập nhật có điều kiện theo trạng thái; handler không được cộng trả credit lần nữa sau khi reservation đã kết thúc.

### 6.2. Hết hạn phải có ngữ nghĩa cụ thể

Đối với bài này, chọn chính sách:

1. Không tạo reservation mới sau thời hạn của allocation.
2. Reservation phải được quyết toán hoặc giải phóng theo thời hạn đã được chốt khi giữ chỗ.
3. Khi hết hạn, thu hồi phần khả dụng về đúng pool ban đầu.
4. Chỉ hoàn tất đóng allocation sau khi không còn reservation mở.

Nếu thời hạn dùng để quyết định có cho phép cấp hay giữ chỗ, phải dùng thời gian của server hoặc cơ sở dữ liệu ở thời điểm quyết định dưới khóa. Trong PostgreSQL, `CURRENT_TIMESTAMP` cố định theo thời điểm bắt đầu transaction; transaction chờ khóa lâu có thể cần lấy thời gian hiện tại bằng `clock_timestamp()` cho chính sách kiểm tra hạn tại lúc xử lý.

Một chương trình có thể chọn đốt credit hết hạn thay vì trả về pool. Khi đó cần thêm thành phần burned vào phương trình bảo toàn và ghi chuyển trạng thái tương ứng. Không xóa số dư rồi xem sai lệch là kết quả bình thường.

## 7. Mô hình dữ liệu tối thiểu

Ví dụ sau dùng PostgreSQL và tập trung vào cấp phát. Nó chưa bao gồm bảng thành viên, phân quyền, phê duyệt, reservation, ledger và outbox; các kiểm tra đó vẫn phải tồn tại trong triển khai đầy đủ.

~~~sql
CREATE TABLE credit_pool (
    tenant_id UUID NOT NULL,
    pool_id UUID NOT NULL,
    epoch_code TEXT NOT NULL,
    unit_code TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('OPEN', 'CLOSED')),
    capacity_units BIGINT NOT NULL CHECK (capacity_units >= 0),
    free_units BIGINT NOT NULL CHECK (free_units >= 0),
    PRIMARY KEY (tenant_id, pool_id),
    CHECK (free_units <= capacity_units)
);

CREATE TABLE credit_quota (
    tenant_id UUID NOT NULL,
    pool_id UUID NOT NULL,
    beneficiary_id UUID NOT NULL,
    cap_units BIGINT NOT NULL CHECK (cap_units >= 0),
    allocated_units BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, pool_id, beneficiary_id),
    FOREIGN KEY (tenant_id, pool_id)
        REFERENCES credit_pool (tenant_id, pool_id),
    CHECK (allocated_units >= 0 AND allocated_units <= cap_units)
);

CREATE TABLE credit_allocation (
    tenant_id UUID NOT NULL,
    allocation_id UUID NOT NULL,
    pool_id UUID NOT NULL,
    beneficiary_id UUID NOT NULL,
    command_ref UUID NOT NULL,
    granted_units BIGINT NOT NULL CHECK (granted_units > 0),
    available_units BIGINT NOT NULL CHECK (available_units >= 0),
    reserved_units BIGINT NOT NULL DEFAULT 0 CHECK (reserved_units >= 0),
    spent_units BIGINT NOT NULL DEFAULT 0 CHECK (spent_units >= 0),
    returned_units BIGINT NOT NULL DEFAULT 0 CHECK (returned_units >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, allocation_id),
    UNIQUE (tenant_id, pool_id, command_ref),
    FOREIGN KEY (tenant_id, pool_id, beneficiary_id)
        REFERENCES credit_quota (tenant_id, pool_id, beneficiary_id),
    CHECK (
        granted_units =
        available_units + reserved_units + spent_units + returned_units
    )
);
~~~

Ý nghĩa của các ràng buộc:

- Khóa ngoại ghép mang `tenant_id` giúp ngăn gắn allocation vào quota hoặc pool của tenant khác.
- Bản ghi quota theo pool giúp các request khác nhau cùng tranh chấp một điểm kiểm soát hạn mức.
- `command_ref` duy nhất ngăn cùng một lệnh nghiệp vụ tạo thêm allocation, kể cả khi HTTP key thay đổi.
- Các `CHECK` bảo vệ miền giá trị trên từng hàng và một số quan hệ cục bộ.

`command_ref` ở đây xác định **một lần cấp cho một người nhận trong một pool**. Nếu một phê duyệt có nhiều dòng người nhận, dùng ID dòng hoặc khóa ghép có ý nghĩa tương đương, không dùng cùng một ID cho nhiều lần cấp rồi bỏ unique khi gặp xung đột.

Bản ghi quota phải được tạo qua luồng tin cậy; kèm kiểm tra người nhận thuộc tenant. Trong lược đồ đầy đủ, có thể thêm khóa ngoại ghép tới bảng thành viên. Việc có một quota không chứng minh thành viên vẫn đang hoạt động, nên trạng thái nhận credit vẫn cần kiểm tra tại thời điểm cấp.

Constraint trên từng hàng không tự chứng minh phương trình bảo toàn qua nhiều bảng. Mọi đường ghi phải thực hiện đủ các thay đổi trong một transaction; cần ledger và đối soát để phát hiện sai lệch do lỗi triển khai hoặc thao tác vận hành.

## 8. Transaction cấp phát và kiểm soát đồng thời

### 8.1. Vì sao kiểm tra rồi ghi dễ bị khai thác

Đoạn logic sau không an toàn khi nhiều transaction cùng chạy:

~~~java
long free = poolRepository.readFreeUnits(poolId);

if (free >= requestedUnits) {
    allocationRepository.insert(beneficiaryId, requestedUnits);
    poolRepository.writeFreeUnits(poolId, free - requestedUnits);
}
~~~

Giả sử pool còn 100, hai request đều muốn cấp 80:

~~~text
T1 đọc free = 100
T2 đọc free = 100
T1 tạo allocation 80
T2 tạo allocation 80
T1 ghi free = 20
T2 ghi free = 20

Kết quả: cấp 160 và vẫn báo còn 20, trong khi ngân sách chỉ có 100.
~~~

Constraint `free_units >= 0` không phát hiện lỗi mất cập nhật này, vì số dư cuối vẫn dương. Nếu thay phép ghi bằng trừ tương đối nhưng không chặn kết quả âm, hai lần trừ có thể dẫn đến −60.

Một khóa `synchronized` trong một tiến trình Java cũng không bảo vệ được các instance khác hoặc một tác vụ nền truy cập cùng dữ liệu.

### 8.2. Một chiến lược dễ kiểm chứng: khóa theo pool

Trong mô hình tham chiếu của bài, các đường ghi số dư của cùng pool khóa hàng pool trước. Điều này tạo một điểm tuần tự hóa rõ ràng, đổi lại giới hạn khả năng xử lý song song trên một pool rất nóng.

Thứ tự thực hiện:

1. Xác thực, parse và kiểm tra miền dữ liệu; xác định tenant từ ngữ cảnh tin cậy.
2. Mở transaction.
3. Nhận quyền xử lý idempotency key, hoặc xác định kết quả đã có.
4. Khóa pool; kiểm tra trạng thái, đơn vị, kỳ và thời gian hiệu lực.
5. Kiểm tra quyền hiện hành, trạng thái người nhận và phê duyệt dưới cơ chế đồng bộ đã chọn.
6. Khóa quota của người nhận; kiểm tra phần hạn mức còn có thể cấp.
7. Trừ nguồn chung, tăng tổng đã phân bổ cho người nhận và tạo allocation.
8. Tiêu thụ phê duyệt nếu có; ghi ledger, kết quả idempotency và sự kiện outbox.
9. Commit rồi mới trả thành công cho client.

Một thứ tự khóa có thể thống nhất là pool → dữ liệu quyền liên quan → phê duyệt → quota → allocation/reservation. Khi có nhiều pool hoặc nhiều người nhận, khóa theo thứ tự ID ổn định trong từng nhóm. Các luồng quản trị, thu hồi và quyết toán cũng phải tuân thủ cùng quy ước.

Dưới đây là phần SQL cốt lõi bên trong transaction. Đây là đoạn minh họa cơ chế số dư, chưa phải một endpoint đầy đủ:

~~~sql
-- Chạy cùng transaction với idempotency, quyền và phê duyệt.
SELECT status, epoch_code, unit_code, capacity_units, free_units
FROM credit_pool
WHERE tenant_id = :tenant_id
  AND pool_id = :pool_id
FOR UPDATE;

SELECT cap_units, allocated_units
FROM credit_quota
WHERE tenant_id = :tenant_id
  AND pool_id = :pool_id
  AND beneficiary_id = :beneficiary_id
FOR UPDATE;

-- Điều kiện bắt buộc ở tầng lệnh: :units là số nguyên dương hợp lệ.
UPDATE credit_pool
SET free_units = free_units - :units
WHERE tenant_id = :tenant_id
  AND pool_id = :pool_id
  AND status = 'OPEN'
  AND free_units >= :units
RETURNING free_units;

UPDATE credit_quota
SET allocated_units = allocated_units + :units
WHERE tenant_id = :tenant_id
  AND pool_id = :pool_id
  AND beneficiary_id = :beneficiary_id
  AND allocated_units <= cap_units - :units
RETURNING allocated_units;

INSERT INTO credit_allocation (
    tenant_id, allocation_id, pool_id, beneficiary_id, command_ref,
    granted_units, available_units, reserved_units, spent_units, returned_units
) VALUES (
    :tenant_id, :allocation_id, :pool_id, :beneficiary_id, :command_ref,
    :units, :units, 0, 0, 0
);

-- Tiếp theo: chuyển trạng thái phê duyệt, ghi ledger,
-- hoàn tất idempotency và ghi outbox, rồi mới COMMIT.
~~~

Mỗi `SELECT` bắt buộc phải tìm thấy đúng đối tượng; mỗi `UPDATE` phải trả đúng một hàng. Nếu thiếu pool, thiếu quota, hết ngân sách hoặc vượt hạn mức, toàn bộ transaction phải rollback. Không được bỏ qua số hàng ảnh hưởng và vẫn tạo allocation.

Nếu bước cập nhật quota thất bại sau khi nguồn chung đã bị trừ, rollback sẽ khôi phục cả nguồn chung. Nếu insert allocation vi phạm unique của `command_ref`, rollback cũng phải hủy mọi thay đổi số dư trước đó.

Trong Java, không bắt exception rồi trả kết quả thất bại bình thường bên trong transaction nếu việc đó khiến framework commit phần thay đổi đã thực hiện. Cơ chế báo lỗi phải thật sự đánh dấu rollback hoặc thoát khỏi ranh giới transaction bằng exception phù hợp.

### 8.3. Phác thảo tầng lệnh Java

Đây là mã giả để thể hiện trách nhiệm và thứ tự; các repository là thành phần phải được triển khai theo cùng một giao thức khóa:

~~~java
AllocationResult allocate(Actor actor, AllocateCommand cmd, String key) {
    inputValidator.requirePositiveBoundedUnits(cmd.units());
    inputValidator.requireValidKey(key);

    TenantId tenant = actor.verifiedTenant();
    access.requireCanAttemptAllocation(actor, tenant, cmd.poolId());

    RequestHash hash = requestHasher.canonicalHash(
        "ALLOCATE_V1", tenant, cmd
    );

    return transactionRunner.required(() -> {
        IdempotencyDecision idem = idempotency.claimOrReplay(
            tenant, actor.id(), "ALLOCATE_V1", key, hash
        );

        if (idem.isReplay()) {
            access.requireCanReadStoredResult(actor, idem.result());
            return idem.result();
        }

        CreditPool pool = pools.lock(tenant, cmd.poolId());
        access.lockAndRequireAllocationPermission(actor, pool);
        membership.lockAndRequireEligible(tenant, cmd.beneficiaryId());

        ApprovalDecision approval =
            approvals.lockAndValidateIfRequired(actor, pool, cmd);

        CreditQuota quota = quotas.lock(
            tenant, pool.id(), cmd.beneficiaryId()
        );

        // Lấy thời gian sau khi đã chờ các khóa cần thiết.
        Instant decisionTime = databaseClock.currentInstant();
        policy.requireAllocationAllowed(
            pool, quota, approval, cmd, decisionTime
        );

        pools.decreaseFreeOrFail(pool, cmd.units());       // đúng 1 hàng
        quotas.increaseAllocatedOrFail(quota, cmd.units()); // đúng 1 hàng

        Allocation allocation = allocations.insert(
            pool, cmd.beneficiaryId(), cmd.commandRef(), cmd.units()
        );

        approvals.consumeIfRequired(approval, allocation.id());
        ledger.appendAllocation(allocation, actor);
        outbox.appendCreditAllocated(allocation);

        AllocationResult result = AllocationResult.created(allocation);
        idempotency.complete(idem.requestId(), hash, result);
        return result;
    });
}
~~~

`lockAndRequireAllocationPermission` và các tên tương tự biểu diễn cam kết đồng bộ, không phải chỉ là cách đặt tên. Nếu adapter thực tế chỉ đọc dữ liệu không khóa, bảo đảm của thiết kế chưa được thực hiện.

Ranh giới transaction phải được gọi qua cơ chế có hiệu lực của framework đang sử dụng. Ví dụ trong một số cấu hình Spring dựa trên proxy, gọi nội bộ một phương thức `@Transactional` từ cùng đối tượng không đi qua proxy. Cần kiểm chứng transaction thực sự bao trùm toàn bộ thay đổi.

### 8.4. Chọn cơ chế đồng thời phù hợp

| Cơ chế | Điều kiện để đúng | Điểm cần lưu ý |
| --- | --- | --- |
| Khóa bi quan trên pool và quota | Mọi đường ghi tuân thủ thứ tự khóa | Dễ lập luận, có thể nghẽn trên pool nóng |
| Cập nhật có điều kiện | Mọi cập nhật liên quan nằm cùng transaction, kiểm tra số hàng | Một câu `UPDATE` thành công chưa chứng minh cả nghiệp vụ đã đúng |
| Optimistic locking bằng version | Kiểm tra version trên mọi dữ liệu cần bảo vệ và xử lý retry toàn lệnh | Kiểm tra chỉ version của allocation không bảo vệ pool dùng chung |
| Isolation serializable | Ranh giới transaction đầy đủ, xử lý serialization failure đúng | Không thay thế phân quyền, phê duyệt và idempotency |

Mô hình khóa pool trong bài có thể triển khai với PostgreSQL Read Committed khi tất cả đường ghi tuân thủ giao thức và các điều kiện quan trọng được đọc lại dưới khóa. Nếu đổi isolation hoặc bỏ khóa để tối ưu, phải phân tích lại các tương tác.

Với deadlock hoặc lỗi serialization, retry toàn transaction theo chính sách có giới hạn. Không chỉ chạy lại câu lệnh cuối. Các side effect ra ngoài cơ sở dữ liệu phải được trì hoãn hoặc có giao thức chống lặp; nếu không, retry transaction có thể gửi trùng thông báo hoặc cấp trùng ở hệ thống ngoài.

## 9. Idempotency: một yêu cầu, một hiệu ứng

### 9.1. Timeout không chứng minh giao dịch thất bại

Kịch bản điển hình:

~~~text
Client gửi lệnh cấp 120 credit.
Server commit thành công.
Kết nối đứt trước khi client nhận response.
Client gửi lại lệnh.
~~~

Nếu request thứ hai luôn tạo allocation mới, người nhận có 240 credit. Nếu client không được retry, một lỗi mạng có thể khiến họ không biết thao tác đã thành công hay chưa.

Idempotency cho phép gửi lại cùng một ý định mà không tạo thêm hiệu ứng nghiệp vụ đã commit.

### 9.2. Phạm vi khóa và request fingerprint

Một phạm vi khóa hợp lý cho ví dụ:

~~~text
(tenant_id, actor_id, operation_version, idempotency_key)
~~~

Trong phạm vi đó, server lưu:

- Hash của nội dung yêu cầu đã được chuẩn hóa.
- Định danh request và allocation đã tạo.
- Mã HTTP và nội dung phản hồi nghiệp vụ cần phát lại.
- Thời điểm xử lý và dữ liệu liên kết phục vụ truy vết.

Hash phải bao gồm các trường ảnh hưởng hiệu ứng: pool, người nhận, lượng credit, `commandRef` và nội dung nghiệp vụ khác. Cần quy định rõ thứ tự trường, giá trị mặc định và cách biểu diễn số; không lấy hash của JSON thô phụ thuộc khoảng trắng hoặc thứ tự thuộc tính.

Nếu `reason` là phần được ghi vào allocation và audit, hãy đưa dạng chuẩn hóa của nó vào fingerprint. Không để một lần retry thay lý do của hiệu ứng đã commit.

Cùng key, khác fingerprint phải bị từ chối, chẳng hạn `409 IDEMPOTENCY_KEY_REUSED`. Không thực hiện nội dung mới dưới key cũ.

### 9.3. Bản ghi idempotency bền vững

~~~sql
CREATE TABLE credit_idempotency (
    tenant_id UUID NOT NULL,
    actor_id UUID NOT NULL,
    operation_code TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_id UUID NOT NULL,
    request_hash BYTEA NOT NULL,
    response_status INTEGER,
    response_body JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (
        tenant_id, actor_id, operation_code, idempotency_key
    ),
    UNIQUE (tenant_id, request_id),
    CHECK (
        (response_status IS NULL AND response_body IS NULL)
        OR
        (response_status IS NOT NULL AND response_body IS NOT NULL)
    )
);
~~~

Trong thiết kế một transaction của bài, bản ghi được insert trước thay đổi nghiệp vụ và hoàn tất response trước commit:

1. Thử `INSERT ... ON CONFLICT DO NOTHING` theo khóa phạm vi.
2. Nếu insert thành công, transaction này là chủ xử lý.
3. Nếu đã có bản ghi, đọc và khóa bản ghi đó, so fingerprint, rồi phát lại kết quả đã hoàn tất.
4. Nếu có hai transaction cùng key, unique constraint làm transaction sau chờ quyết định của transaction trước.
5. Nếu transaction trước rollback, không còn một hiệu ứng cấp phát đã commit gắn với lần thử đó.
6. Nếu transaction trước commit, transaction sau thấy kết quả đã lưu.

Ở PostgreSQL Read Committed, bước đọc sau insert xung đột nên là một câu lệnh tiếp theo để có snapshot mới. Với isolation khác, cần xử lý khả năng lỗi serialization theo cơ chế đã chọn.

Không commit một hàng chưa có response rồi xử lý cấp phát ở transaction rời mà vẫn dùng thiết kế này. Nếu chọn xử lý bất đồng bộ, cần một state machine request riêng với trạng thái, cơ chế nhận việc và khôi phục; đó là thiết kế khác.

Một hàng idempotency đã commit mà không có kết quả hoàn chỉnh là vi phạm quy ước của luồng đồng bộ. Không tự xem nó là quyền cấp lại; phải chặn và điều tra hoặc khôi phục bằng quy trình đã thiết kế.

Trong ví dụ này, **kết quả thành công** được lưu cùng hiệu ứng. Lỗi kiểm tra nghiệp vụ làm rollback cả bản ghi mới. Vì vậy, một lần thử lại sau khi điều kiện thay đổi có thể được đánh giá lại. Nếu sản phẩm muốn phát lại cả lỗi xác định, phải quy định thêm thời điểm và cách lưu lỗi; không hứa mọi response đều được ghi nhớ khi thiết kế chỉ lưu thành công.

### 9.4. Khóa HTTP và danh tính nghiệp vụ giải quyết hai lớp khác nhau

Idempotency key xử lý retry của một client trong phạm vi đã định. Nó không chứng minh một người được phép tạo lần cấp mới.

Ví dụ cùng một yêu cầu đã duyệt bị gửi qua hai actor khác nhau hoặc hai key khác nhau. Hai hàng idempotency đều có thể hợp lệ, nhưng chỉ được có một allocation cho `commandRef` đó. Cần kết hợp:

- Unique của định danh nghiệp vụ.
- Chuyển trạng thái phê duyệt một lần.
- Điều kiện hạn mức và nguồn ngân sách.
- Kiểm tra nội dung của lệnh đã được duyệt.

Trong mô hình một lệnh cho một allocation, xung đột `commandRef` phải rollback transaction mới. API có thể trả `409 COMMAND_ALREADY_ALLOCATED`, hoặc trả kết quả cũ nếu xác minh đầy đủ rằng đó là cùng lệnh và actor được đọc kết quả. Không bắt unique violation rồi tiếp tục dùng transaction PostgreSQL đang ở trạng thái lỗi.

Khóa có thời hạn lưu cũng phải được thiết kế cẩn thận. Sau khi xóa bản ghi idempotency, một key cũ có thể xuất hiện như mới. Vì vậy không được xóa luôn bằng chứng duy nhất ngăn thực hiện lại quyền lợi nghiệp vụ còn hiệu lực. Danh tính nghiệp vụ và dấu đã tiêu thụ phê duyệt cần tồn tại theo vòng đời phù hợp của chương trình cấp phát.

### 9.5. Phát lại kết quả vẫn cần phân quyền

Không tra key rồi trả response trước mọi kiểm tra quyền. Người dùng có thể đã bị thu hồi quyền hoặc chuyển tổ chức.

Một lần retry cần xác thực actor, tenant và quyền đọc kết quả tại thời điểm hiện tại. Nếu chính sách cho phép đọc lịch sử giao dịch đã tạo sau khi mất quyền cấp mới, quyền lịch sử đó phải được mô hình hóa riêng. Phát lại kết quả không được tạo thêm hiệu ứng hoặc khôi phục một quyền đã mất.

## 10. Ledger, outbox và đối soát

### 10.1. Ghi bằng chứng cùng transaction

Ledger biểu diễn các chuyển credit giữa tài khoản hoặc trạng thái. Một lần cấp 120 có thể được mô hình hóa:

~~~text
Transfer:
  source = pool.free
  destination = allocation.available
  units = 120
  tenant, pool, epoch, unit = cùng một phạm vi
  business_reference = commandRef
  actor = người hoặc service đã thực hiện
~~~

Nguồn giảm và đích tăng cùng lượng. Nếu triển khai theo bút toán cân đối, cần định nghĩa dấu và tổng cân đối nhất quán; không để mỗi handler tự chọn cách ghi.

Ledger phục vụ bằng chứng nên có các đặc điểm:

- Không sửa hoặc xóa lịch sử để “sửa số dư”; dùng bút toán bù có tham chiếu.
- Gắn định danh nghiệp vụ, allocation, actor, tenant và phiên bản chính sách cần truy vết.
- Có khóa duy nhất phù hợp để một chuyển động không bị ghi lặp.
- Được ghi cùng transaction với số dư được vật chất hóa.

Không cần lưu access token, thông tin bí mật hoặc toàn bộ payload chứa dữ liệu không cần thiết trong audit log.

### 10.2. Sự kiện không được đi trước commit

Sai lầm thường gặp là phát `CreditAllocated` trước khi commit. Consumer có thể mở quyền sử dụng trong khi transaction cấp phát sau đó rollback.

Nếu cần gửi sự kiện ra broker, ghi outbox cùng transaction. Worker phát sự kiện sau commit và có thể phát lại khi retry. Consumer phải xử lý trùng theo event ID hoặc định danh nghiệp vụ trước khi tạo hiệu ứng.

Outbox hỗ trợ chuyển giao sự kiện đáng tin cậy, không tự làm cho toàn bộ hệ thống phân tán có “exactly once”. Nếu cấp credit ở một nhà cung cấp khác, cần giao thức riêng để liên kết lệnh, idempotency ở phía nhận và phục hồi khi kết quả không rõ ràng.

### 10.3. Đối soát theo cùng phạm vi

Các kiểm tra đối soát tối thiểu cho một pool:

~~~text
pool.capacity_units
  = pool.free_units
    + SUM(allocation.available_units
          + allocation.reserved_units
          + allocation.spent_units)

quota.allocated_units
  = SUM(available_units + reserved_units + spent_units)
    theo đúng pool và beneficiary

allocation.granted_units
  = available_units + reserved_units + spent_units + returned_units
~~~

Đọc các bảng trong một snapshot nhất quán để tránh báo sai do giao dịch đang commit giữa những lần đọc. Các truy vấn `SUM` cũng phải dùng kiểu đủ lớn để không tràn khi tổng nhiều hàng.

Đối soát là lớp phát hiện, không thay cho transaction bảo vệ lúc cấp. Nếu phát hiện sai lệch, không tự điều chỉnh giảm credit của người dùng để làm phương trình đẹp lại. Cần dừng hoặc hạn chế đường ghi có lỗi theo quy trình, xác định nguồn sai lệch và ghi điều chỉnh có thẩm quyền.

## 11. Thiết kế hợp đồng API và lỗi

Response thành công nên cho biết allocation cụ thể đã tạo, lượng credit, đơn vị và kỳ. Không chỉ trả một số dư tổng dễ bị hiểu là dữ liệu luôn mới nhất.

~~~json
{
  "allocationId": "allocation-789",
  "poolId": "pool-001",
  "beneficiaryId": "user-123",
  "units": 120,
  "unitCode": "TASK_CREDIT",
  "epochCode": "PERIOD-A",
  "commandRef": "approved-request-456"
}
~~~

Nếu response gốc chứa số dư sau cấp, response được phát lại phản ánh thời điểm giao dịch gốc. Muốn xem số dư hiện tại, client gọi API đọc phù hợp.

Một hợp đồng lỗi minh họa:

| Tình huống | Phản hồi gợi ý | Hiệu ứng nghiệp vụ |
| --- | --- | --- |
| Số lượng sai định dạng hoặc ngoài miền | `400 INVALID_UNITS` | Không có |
| Không được phép truy cập đối tượng | `403` hoặc `404` theo chính sách che giấu tồn tại | Không có |
| Pool đóng hoặc hết hạn | `409 POOL_NOT_ALLOCATABLE` | Không có |
| Không đủ nguồn hoặc vượt hạn mức | `409 INSUFFICIENT_CREDIT` / `QUOTA_EXCEEDED` | Rollback toàn bộ |
| Phê duyệt không còn hợp lệ | `409 APPROVAL_NOT_USABLE` | Rollback toàn bộ |
| Cùng key, khác nội dung | `409 IDEMPOTENCY_KEY_REUSED` | Không thực hiện nội dung mới |
| Lệnh nghiệp vụ đã được dùng | `409 COMMAND_ALREADY_ALLOCATED` hoặc phát lại có kiểm tra quyền | Không cấp thêm |
| Không rõ kết quả do mất kết nối | Client retry cùng key và cùng nội dung | Tra hoặc hoàn tất đúng một hiệu ứng |

Đây là quy ước cho API ví dụ, không phải ánh xạ bắt buộc cho mọi hệ thống. Cần thống nhất ý nghĩa với client và không tiết lộ số dư hoặc sự tồn tại của đối tượng ngoài phạm vi quyền.

Với batch allocation, phải định nghĩa rõ toàn bộ batch là nguyên tử hay từng dòng có kết quả riêng. Nếu xử lý từng dòng độc lập, mỗi dòng cần định danh nghiệp vụ và cơ chế chống lặp; retry cả batch không được cấp lại các dòng đã thành công.

## 12. Kiểm thử các tình huống tấn công logic

Kiểm thử cần quan sát cả response và trạng thái đã commit. Một mã lỗi đúng nhưng nguồn chung đã bị trừ vẫn là thất bại.

### 12.1. Dữ liệu và quyền

| Ca kiểm thử | Cách thực hiện | Kết quả cần chứng minh |
| --- | --- | --- |
| Cấp số âm, 0, số lẻ, ngoài miền | Gửi trực tiếp payload, không qua giao diện | Từ chối; không tạo allocation hoặc ledger |
| Tràn số | Dùng giá trị sát giới hạn kiểu, thử cộng vượt cap | Không wrap-around, không cấp credit ngoài chính sách |
| Sửa pool sang tenant khác | Actor tenant A gọi pool tenant B | Không truy cập hoặc thay đổi dữ liệu tenant B |
| Sửa người nhận sang tenant khác | Giữ pool hợp lệ nhưng đổi beneficiary | Từ chối trước hiệu ứng; không tự tạo quota cho người ngoài |
| Tự nhận role hoặc phê duyệt | Thêm `actorRole`, `approved`, `skipApproval` | Không làm thay đổi quyết định của server |
| Tự cấp khi bị cấm | Người phân bổ đặt beneficiary là chính mình | Bị chặn theo quan hệ actor–beneficiary |
| Sửa yêu cầu sau duyệt | Đổi lượng, pool hoặc người nhận | Phê duyệt cũ không sử dụng được |
| Chia nhỏ để né ngưỡng | Gửi nhiều lệnh dưới ngưỡng trong một kỳ | Áp dụng tổng tích lũy nếu chính sách yêu cầu |
| Phát lại sau mất quyền | Hoàn tất giao dịch rồi thu hồi quyền trước retry | Không cấp thêm; quyền đọc lịch sử theo chính sách |

### 12.2. Đồng thời và yêu cầu trùng

Dùng cơ sở dữ liệu thật có hành vi khóa như môi trường triển khai. Mock repository thường không tái hiện được race condition.

**Ca A — Hai key khác nhau tranh chấp nguồn chung**

~~~text
Ban đầu:
  Pool: capacity = 100, free = 100
  Hai người nhận: quota đủ lớn
  Hai commandRef khác nhau, mỗi lệnh cấp 80

Chạy hai transaction đồng thời.

Kỳ vọng:
  Đúng một lệnh cấp thành công.
  Lệnh kia thất bại do nguồn chỉ còn 20.
  Tổng allocation = 80.
  free = 20.
  Không còn ledger hoặc outbox của lệnh bị rollback.
~~~

**Ca B — Một người nhận tranh chấp hạn mức**

~~~text
Ban đầu:
  Pool: free = 1.000
  Người nhận: cap = 100, allocated = 0
  Hai lệnh khác nhau, mỗi lệnh cấp 80

Kỳ vọng:
  Đúng một allocation 80.
  quota.allocated = 80.
  pool.free = 920.
  Lệnh thất bại không làm nguồn giảm thêm.
~~~

**Ca C — Cùng key, cùng nội dung**

Gửi nhiều request song song với cùng actor, tenant, operation, key và fingerprint. Sau khi xử lý hoặc retry các lỗi tạm thời theo hợp đồng:

- Chỉ có một allocation đã commit.
- Chỉ có một hiệu ứng ledger cho lần cấp.
- Mọi kết quả thành công trỏ cùng allocation.
- Nguồn và quota chỉ thay đổi một lần.

**Ca D — Cùng key, khác nội dung**

Cho hai request tranh chấp cùng key nhưng khác người nhận hoặc lượng credit. Chỉ một fingerprint được gắn với hiệu ứng thành công; request có nội dung khác bị xung đột. Không có lần cấp thứ hai.

**Ca E — Khác key, cùng commandRef**

Gửi cùng lệnh đã duyệt với hai key, có thể qua hai actor đều có quyền. Kết quả phải chỉ có một allocation; phê duyệt chỉ được tiêu thụ một lần.

**Ca F — Phê duyệt hoặc pool thay đổi khi đang chờ**

Cho lệnh cấp chờ khóa, rồi đóng pool hoặc làm hết hạn quyết định theo giao thức phù hợp. Khi lệnh lấy được các khóa cần thiết, nó phải đánh giá trạng thái và thời gian hiện tại theo chính sách, không dùng kết quả kiểm tra cũ trước lúc chờ.

Dùng barrier hoặc latch để điều khiển các transaction đi đến điểm tranh chấp. Chỉ chạy tuần tự hoặc dùng `sleep` ngẫu nhiên không đủ chứng minh cơ chế đồng thời đúng.

### 12.3. Lỗi giữa các bước và khôi phục

Chèn lỗi tại các điểm có ý nghĩa:

1. Sau khi trừ pool nhưng trước cập nhật quota.
2. Sau khi tăng quota nhưng trước insert allocation.
3. Sau khi tạo allocation nhưng trước tiêu thụ phê duyệt.
4. Sau khi ghi ledger nhưng trước hoàn tất idempotency.
5. Sau khi commit nhưng trước khi client nhận response.
6. Sau khi outbox gửi sự kiện nhưng trước khi đánh dấu đã gửi.

Với các điểm 1–4, toàn bộ transaction phải rollback: không có thay đổi số dư, allocation, phê duyệt hoặc sự kiện bền vững rời rạc.

Với điểm 5, retry cùng key phải trả lại allocation đã commit. Với điểm 6, consumer nhận trùng sự kiện nhưng không tạo trùng hiệu ứng.

Ngoài ra, cho release và consume cùng tranh chấp một reservation; chỉ một nhánh được thắng. Thử reclaim đồng thời với reserve để chứng minh một credit không vừa bị trả về pool vừa được giữ chỗ cho người dùng.

### 12.4. Kiểm tra bất biến theo chuỗi hành động

Thay vì chỉ kiểm tra một endpoint riêng lẻ, có thể sinh chuỗi hành động:

~~~text
allocate → reserve → release → reserve → consume → reclaim
~~~

Sau mỗi bước đã commit, kiểm tra:

- Mọi thành phần số dư không âm.
- Phương trình bảo toàn đúng theo pool, kỳ và đơn vị.
- Quota khớp tổng cam kết của người nhận và không vượt cap.
- Không có hai allocation cho cùng danh tính nghiệp vụ.
- Không có phê duyệt một lần được tiêu thụ nhiều lần.
- Lệnh thất bại không để lại thay đổi dở dang.

Đây là kiểm thử theo mô hình hoặc thuộc tính. Nó đặc biệt hữu ích khi một chuỗi thao tác hợp lệ riêng lẻ tạo ra kết quả sai sau khi kết hợp, chẳng hạn release lặp rồi reclaim phần credit đã được trả trước đó.

## 13. Lỗi thiết kế cần nhận ra khi review

| Thiết kế có vấn đề | Vì sao gây rủi ro | Hướng sửa |
| --- | --- | --- |
| UI khóa nút cấp thêm nhưng API vẫn nhận | Client không phải ranh giới tin cậy | Bảo vệ lệnh tại server và cơ sở dữ liệu |
| Đọc số dư, kiểm tra rồi lưu giá trị mới | Có thể mất cập nhật khi đồng thời | Khóa hoặc conditional update trong transaction |
| Chỉ khóa hàng allocation vừa tạo | Không bảo vệ pool và quota dùng chung | Đồng bộ trên tài nguyên bị tranh chấp |
| Tách trừ pool và tạo allocation thành hai transaction | Lỗi ở giữa phá bảo toàn | Một transaction cho hiệu ứng cục bộ đầy đủ |
| Cache Redis là bằng chứng chống lặp duy nhất | Cache mất hoặc key hết hạn có thể cấp lại | Bằng chứng bền vững cùng transaction với hiệu ứng |
| Tin JWT role để duyệt mọi pool | Role không mô tả đủ quan hệ đối tượng hiện tại | Kiểm tra phạm vi pool, tenant và chính sách |
| Unique chỉ theo idempotency key | Hai key mới vẫn dùng lại cùng quyền lợi | Bổ sung định danh nghiệp vụ và trạng thái phê duyệt |
| Ghi audit hoặc phát sự kiện trước commit | Có bằng chứng hoặc tác vụ của giao dịch thất bại | Ledger cùng transaction, outbox cho hệ thống ngoài |
| “Sửa” số dư bằng cách xóa lịch sử | Mất khả năng truy vết và phục hồi | Bút toán điều chỉnh có thẩm quyền |
| Tối ưu bỏ khóa pool nhưng không đổi mô hình kiểm chứng | Tăng song song đồng thời bỏ mất điểm bảo vệ | Thiết kế lại cơ chế nguyên tử và kiểm thử race |

## 14. Tiêu chí hoàn thành một luồng cấp phát

Trước khi xem luồng credit allocation là đủ điều kiện triển khai, cần trả lời rõ:

- Credit thuộc tenant, đơn vị, kỳ và nguồn nào?
- Công thức bảo toàn và công thức hạn mức là gì?
- Actor được cấp trên đối tượng nào, cho ai và đến mức nào?
- Nội dung phê duyệt có khớp chính xác lệnh đang thực hiện không?
- Một lần cấp nghiệp vụ được định danh thế nào khi client đổi key?
- Hai request tranh chấp nguồn hoặc quota bị tuần tự hóa ở đâu?
- Nếu bất kỳ bước ghi nào thất bại, toàn bộ hiệu ứng có rollback không?
- Mất response sau commit thì client tìm lại kết quả bằng cách nào?
- Reserve, consume, release, reclaim và expiry có giữ cùng bất biến không?
- Ledger, sự kiện và số dư có thể đối soát trong một snapshot nhất quán không?

Điểm cốt lõi của cấp phát an toàn là mỗi lần cấp phải có **nguồn hợp lệ, người nhận hợp lệ, thẩm quyền hợp lệ và hiệu ứng nguyên tử có thể truy vết**. Idempotency giải quyết retry; định danh nghiệp vụ ngăn dùng lại cùng quyền lợi; transaction giữ các bất biến đúng khi nhiều thao tác cùng chạy.
