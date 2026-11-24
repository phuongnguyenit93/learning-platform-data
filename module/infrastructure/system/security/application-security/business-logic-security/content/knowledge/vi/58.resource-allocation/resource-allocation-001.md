# Scarce resource claim: bảo vệ việc giành quyền sử dụng tài nguyên khan hiếm

## 1. Bài toán nghiệp vụ

Trong chương **Resource Allocation**, “claim” là thao tác xin và được hệ thống ghi nhận quyền giữ hoặc sử dụng một phần tài nguyên có giới hạn. Tài nguyên có thể là ghế tham dự sự kiện, phòng họp, suất khám, hạn mức chạy tác vụ, máy ảo trong một pool hoặc số lượng hàng dành cho một đợt mở bán.

Ví dụ xuyên suốt: một sự kiện có 100 chỗ. Khách hàng có thể giữ chỗ trong 5 phút để hoàn tất điều kiện đăng ký, sau đó xác nhận. Mỗi khách hàng được chiếm dụng tối đa 4 chỗ, tính cả chỗ đang giữ và chỗ đã xác nhận.

Một endpoint chỉ kiểm tra “còn chỗ” rồi ghi dữ liệu có thể chạy đúng khi một người thao tác tuần tự, nhưng sai khi:

- Hai yêu cầu đọc cùng số chỗ còn lại rồi cùng giành chỗ cuối.
- Một người tạo nhiều lượt giữ bằng các idempotency key khác nhau.
- Khách sửa quantity, resourceId, tenantId hoặc claimId để vượt phạm vi được cấp.
- Yêu cầu xác nhận và tác vụ hết hạn cùng xử lý một claim.
- Người dùng gửi lại yêu cầu sau khi mất phản hồi và hệ thống trừ tài nguyên lần nữa.
- Máy khách tự gửi giá, mức ưu tiên, trạng thái đã phê duyệt hoặc thời hạn giữ dài hơn chính sách.

Đây là vấn đề bảo vệ quy tắc nghiệp vụ: từng API có thể xác thực thành công, dữ liệu vẫn đúng định dạng, nhưng tổ hợp thao tác làm sai quyền phân bổ.

Sau bài học, người học cần có khả năng:

1. Viết business invariants cho việc giữ, xác nhận và trả tài nguyên.
2. Thiết kế state machine với điều kiện chuyển trạng thái rõ ràng.
3. Đặt kiểm tra quyền, hạn mức và cập nhật tài nguyên trong ranh giới nhất quán.
4. Xử lý đồng thời, idempotency và hết hạn mà không cấp vượt sức chứa.
5. Kiểm thử các tình huống lạm dụng thay vì chỉ kiểm tra luồng đăng ký thành công.

## 2. Xác định tài nguyên và ranh giới tin cậy

Trước khi chọn khóa hoặc thuật toán, phải trả lời: **đơn vị nào đang được phân bổ?**

| Loại tài nguyên | Đơn vị cần bảo vệ | Hệ quả thiết kế |
| --- | --- | --- |
| Ghế không đánh số | Số chỗ của một sự kiện | Có thể dùng bộ đếm cho từng sự kiện |
| Ghế có số | Một ghế cụ thể trong một sự kiện | Mỗi ghế chỉ có một chủ sở hữu hiện hành |
| Phòng họp | Phòng cùng khoảng thời gian | Các khoảng đặt không được chồng lấn theo chính sách |
| Máy xử lý tác vụ | Một slot đang sử dụng | Quyền truy cập tài nguyên thực phải gắn với quyền cấp slot |
| Hàng tồn kho | Số lượng sản phẩm tại một kho | Phải xác định khi nào giữ, bán và hoàn kho |

Bộ đếm số lượng không đủ để chứng minh không chồng lịch. Khóa của một sự kiện không bảo vệ tài nguyên nằm trong sự kiện khác. Phạm vi của invariant phải trùng với phạm vi dữ liệu được kiểm soát.

Máy chủ là nơi quyết định:

- Tenant và danh tính người thực hiện từ ngữ cảnh xác thực.
- Khách hàng hoặc chủ thể hạn mức mà người thực hiện được phép đại diện.
- Tài nguyên có được mở để cấp quyền hay không.
- Số lượng hợp lệ, hạn mức và mức ưu tiên.
- Thời hạn giữ, điều kiện phê duyệt và điều kiện xác nhận.
- Giá hoặc quyền lợi đi kèm nếu việc phân bổ có tính phí.

Máy khách được đề nghị số lượng và tài nguyên mong muốn; đề nghị đó chưa phải quyết định phân bổ. UUID khó đoán, nút bị ẩn hoặc màn hình không cho chọn quá 4 chỗ đều không thay thế kiểm tra phía máy chủ.

Nếu nhân viên được đặt thay khách hàng, cần lưu riêng **actor** là người thực hiện và **subject** là người nhận tài nguyên. Quyền thao tác dựa trên actor; hạn mức nghiệp vụ thường dựa trên subject. Dùng actor cho cả hai có thể cho phép đổi tài khoản nhân viên để vượt hạn mức của cùng một khách hàng.

## 3. Viết invariants trước khi viết endpoint

Gọi:

- K là sức chứa của một pool.
- H là tổng quantity của các claim đang ở trạng thái HELD.
- C là tổng quantity của các claim đang ở trạng thái CONFIRMED.
- A là lượng có thể cấp thêm, với A = K − H − C.
- Q(s) là tổng tài nguyên đang bị chiếm dụng bởi subject s trong phạm vi hạn mức.
- L(s) là hạn mức áp dụng cho subject đó.

Các invariant cần được giữ sau mỗi transaction đã commit:

| Invariant | Ý nghĩa |
| --- | --- |
| K ≥ 0, H ≥ 0, C ≥ 0 | Không có sức chứa hoặc bộ đếm âm |
| H + C ≤ K | Không cấp vượt sức chứa |
| quantity là số nguyên dương và có giới hạn | Không tăng tài nguyên bằng số âm hoặc gây tràn số |
| H và C khớp tổng quantity của claim tương ứng | Bộ đếm không tách rời bản ghi quyền sở hữu |
| Q(s) ≤ L(s) | Một chủ thể không vượt hạn mức nghiệp vụ |
| Claim chỉ đi qua chuyển trạng thái được phép | Không xác nhận lại claim hết hạn hoặc đã trả |
| Mọi thao tác đúng tenant và quyền đối tượng | Không xác nhận, hủy hoặc đọc claim của người khác |
| Cùng khóa idempotency và nội dung chỉ có một kết quả tạo ban đầu | Gửi lại không sinh thêm quyền sử dụng |
| Mỗi chuyển trạng thái hoàn trả chỉ có hiệu lực một lần | Retry và worker không tạo sức chứa giả |
| Chỉ xác nhận khi còn hạn tại thời điểm quyết định | Không dùng thông tin cũ đã đọc trước khi chờ khóa |

Trong mô hình này, H đếm claim có trạng thái HELD trong cơ sở dữ liệu, kể cả claim đã qua expires_at nhưng chưa được chuyển sang EXPIRED. Thời gian trôi qua không tự làm bộ đếm thay đổi. Hệ thống có thể tạm thời báo ít chỗ trống hơn lượng có thể thu hồi; đó là vấn đề khả dụng cần xử lý bằng thu hồi hết hạn.

Không được vừa loại claim quá hạn khỏi phép tính khả dụng, vừa giữ cách cập nhật bộ đếm theo trạng thái mà không có quy tắc nhất quán. Hai cách tính khác nhau dễ dẫn tới trả tài nguyên hai lần.

Phạm vi quota cũng phải rõ ràng. “Tối đa 4 chỗ mỗi khách cho một sự kiện” khác “tối đa 4 lượt giữ mỗi phút” và “tối đa 4 chỗ mua trong toàn bộ chiến dịch”. Hạn mức phải xác định thời gian, tài nguyên và trạng thái nào được tính.

## 4. State machine của một claim

| Trạng thái | Có chiếm tài nguyên? | Diễn giải |
| --- | --- | --- |
| HELD | Có, trong H | Đã giữ tạm, chờ điều kiện xác nhận |
| CONFIRMED | Có, trong C | Đã nhận quyền sử dụng chính thức |
| RELEASED | Không | Chủ động trả lượt giữ khi còn hiệu lực |
| EXPIRED | Không | Đã thu hồi lượt giữ quá hạn |
| CANCELLED | Không, nếu chính sách cho hoàn chỗ | Hủy quyền đã xác nhận và trả lại chỗ |

~~~mermaid
stateDiagram-v2
    [*] --> HELD: Được cấp chỗ
    HELD --> CONFIRMED: Đủ điều kiện và còn hạn
    HELD --> RELEASED: Chủ động trả khi còn hạn
    HELD --> EXPIRED: Đến hạn và được thu hồi
    CONFIRMED --> CANCELLED: Được phép hủy và hoàn chỗ
~~~

Sơ đồ không có cạnh EXPIRED → CONFIRMED. Claim hết hạn phải tạo lượt yêu cầu mới nếu muốn xin lại chỗ. Đổi trường status trực tiếp từ request không phải thao tác nghiệp vụ hợp lệ.

Ở ví dụ sự kiện, CANCELLED chỉ được dùng khi việc hủy thực sự làm chỗ có thể bán lại. Với hàng đã giao, suất khám đã sử dụng hoặc tài nguyên đã tiêu thụ không thể hoàn lại, không sao chép máy móc chuyển trạng thái này.

Quy tắc thời gian:

- Xác nhận được phép khi t < expires_at.
- Hết hạn khi t ≥ expires_at.
- t lấy từ nguồn thời gian phía máy chủ được chọn làm chuẩn.
- Thời điểm quyết định được lấy sau khi đã có các khóa cần thiết.

Không dùng hai điều kiện cùng có dấu bằng; nếu cả xác nhận và hết hạn đều hợp lệ tại đúng expires_at, ranh giới nghiệp vụ trở nên mâu thuẫn.

Trạng thái và thời gian là hai điều kiện khác nhau. Claim có thể vẫn mang trạng thái HELD nhưng đã quá hạn, nên chỉ kiểm tra state = HELD là chưa đủ.

## 5. Mô hình lưu trữ tối thiểu

Ví dụ dùng một cơ sở dữ liệu quan hệ làm nơi quyết định cuối cùng cho một pool. Đây là SQL minh họa; kiểu thời gian, cách lấy thời gian thực và cú pháp tham số cần chọn theo hệ quản trị.

~~~sql
CREATE TABLE resource_pool (
    tenant_id      VARCHAR(64)  NOT NULL,
    resource_id    VARCHAR(64)  NOT NULL,
    capacity_qty   BIGINT       NOT NULL,
    held_qty       BIGINT       NOT NULL DEFAULT 0,
    confirmed_qty  BIGINT       NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, resource_id),
    CHECK (capacity_qty >= 0),
    CHECK (held_qty >= 0),
    CHECK (confirmed_qty >= 0),
    CHECK (held_qty + confirmed_qty <= capacity_qty)
);

CREATE TABLE resource_claim (
    tenant_id      VARCHAR(64)  NOT NULL,
    claim_id       VARCHAR(64)  NOT NULL,
    resource_id    VARCHAR(64)  NOT NULL,
    subject_id     VARCHAR(64)  NOT NULL,
    quantity       BIGINT       NOT NULL,
    state          VARCHAR(16)  NOT NULL,
    expires_at     TIMESTAMP    NOT NULL,
    version        BIGINT       NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, claim_id),
    FOREIGN KEY (tenant_id, resource_id)
        REFERENCES resource_pool (tenant_id, resource_id),
    CHECK (quantity > 0),
    CHECK (state IN (
        'HELD', 'CONFIRMED', 'RELEASED', 'EXPIRED', 'CANCELLED'
    ))
);
~~~

Các ràng buộc chặn một phần dữ liệu sai nhưng chưa chứng minh tổng quantity trong resource_claim bằng bộ đếm trong resource_pool. Transaction của ứng dụng phải duy trì quan hệ đó; đối soát giúp phát hiện sai lệch.

Trong hệ thống hoàn chỉnh còn cần:

- Dữ liệu quota theo đúng tenant, subject và phạm vi nghiệp vụ.
- Bản ghi idempotency có khóa duy nhất và dấu vân tay yêu cầu.
- Chính sách mở bán, điều kiện xác nhận, quyền đại diện và các mốc kiểm toán.
- Chỉ mục hỗ trợ tìm claim HELD quá hạn và truy vấn theo subject.
- Quy ước về múi giờ, độ chính xác và ánh xạ kiểu thời gian.

Khóa idempotency không thay thế claim_id. Một giá trị nhận diện lần gọi có thể dùng để tìm lại kết quả tạo claim; claim_id nhận diện đối tượng trong các thao tác tiếp theo.

Nếu tài nguyên là từng ghế cụ thể, nên có bản ghi hiện hành cho từng ghế, với khóa duy nhất theo tenant, sự kiện và mã ghế. Đổi ghế từ trống sang có chủ sở hữu phải là cập nhật nguyên tử có điều kiện. Lịch sử có thể chứa nhiều lượt giữ đã kết thúc, nhưng mỗi ghế chỉ có một chủ sở hữu hiện hành.

## 6. Vì sao “kiểm tra rồi ghi” bị khai thác

Đoạn mã tư duy sau không an toàn nếu các bước không có cơ chế đồng bộ chung:

~~~text
available = readAvailable(resourceId)
if available >= requestedQuantity:
    insertClaim(requestedQuantity)
    decreaseAvailable(requestedQuantity)
~~~

Khi chỉ còn một chỗ:

| Thời điểm | Yêu cầu A | Yêu cầu B |
| --- | --- | --- |
| 1 | Đọc available = 1 | |
| 2 | | Đọc available = 1 |
| 3 | Tạo claim một chỗ | |
| 4 | | Tạo claim một chỗ |
| 5 | Ghi bộ đếm theo giá trị đã đọc | |
| 6 | | Ghi bộ đếm theo giá trị đã đọc |

Có thể xuất hiện hai claim cho một chỗ, dù bộ đếm cuối cùng vẫn hiển thị hết chỗ. Chỉ kiểm tra bộ đếm không âm sẽ bỏ sót sai lệch giữa quyền sở hữu và số lượng.

Bọc câu lệnh trong transaction nhưng không chọn cơ chế kiểm soát đồng thời phù hợp cũng chưa đủ. Cần một điểm quyết định mà các yêu cầu cạnh tranh không thể cùng vượt qua dựa trên dữ liệu cũ.

| Cơ chế | Điều kiện để bảo vệ đúng |
| --- | --- |
| SELECT ... FOR UPDATE | Mọi luồng thay đổi pool phải theo cùng giao thức khóa |
| UPDATE có điều kiện còn đủ lượng | Kiểm tra số hàng cập nhật và ghi claim trong cùng transaction |
| Optimistic locking bằng version | Mọi lần ghi liên quan kiểm tra version; xử lý lại khi xung đột |
| Isolation phát hiện xung đột tuần tự hóa | Hiểu hành vi hệ quản trị và retry toàn bộ transaction bị hủy |
| Ràng buộc duy nhất cho slot cụ thể | Biểu diễn đúng một chủ sở hữu hiện hành cho slot |

Không dùng synchronized trong một tiến trình Java làm bảo đảm duy nhất nếu có nhiều instance, worker hoặc đường ghi khác.

## 7. Tạo claim trong một transaction

### 7.1. Thứ tự thao tác

1. Xác thực actor, xác định tenant và subject được phép đại diện.
2. Kiểm tra quantity nguyên dương, không vượt giới hạn của một yêu cầu.
3. Chuẩn hóa nội dung nghiệp vụ và tính dấu vân tay cho idempotency.
4. Bắt đầu transaction, chiếm khóa idempotency hoặc trả kết quả đã có.
5. Khóa pool cần sử dụng.
6. Khóa dữ liệu quota của subject.
7. Kiểm tra lại quyền đối tượng và điều kiện cần nhất quán với quyết định cấp.
8. Lấy thời gian chuẩn sau khi có các khóa, tính expires_at theo chính sách máy chủ.
9. Kiểm tra và tăng quota, tăng H có điều kiện, tạo claim HELD.
10. Ghi kết quả idempotency rồi commit.
11. Trả phản hồi sau khi commit thành công.

Trong mô hình một cơ sở dữ liệu này, quota, pool, claim và kết quả idempotency của lần tạo thành công phải cùng commit hoặc cùng rollback.

Nếu quyền hoặc điều kiện phê duyệt nằm trong dữ liệu có thể thay đổi đồng thời, cần bảo vệ chính dữ liệu đó, chẳng hạn khóa hàng liên quan hoặc kiểm tra phiên bản tại lần ghi. Chỉ đọc quyền trong transaction không tự bảo đảm quyền không thay đổi ngay trước commit.

### 7.2. Phần cập nhật sức chứa

SQL dưới đây chỉ minh họa phần pool và claim sau khi xử lý idempotency, quyền và quota. Tenant, subject, claim_id và expires_at đều do máy chủ xác định hoặc xác minh.

~~~sql
BEGIN;

SELECT capacity_qty, held_qty, confirmed_qty
FROM resource_pool
WHERE tenant_id = :tenant_id
  AND resource_id = :resource_id
FOR UPDATE;

UPDATE resource_pool
SET held_qty = held_qty + :quantity
WHERE tenant_id = :tenant_id
  AND resource_id = :resource_id
  AND capacity_qty - held_qty - confirmed_qty >= :quantity;

-- Chi tiep tuc khi UPDATE anh huong dung mot hang.
-- Neu khong du cho, khong INSERT claim.

INSERT INTO resource_claim (
    tenant_id, claim_id, resource_id, subject_id,
    quantity, state, expires_at, version
)
VALUES (
    :tenant_id, :claim_id, :resource_id, :subject_id,
    :quantity, 'HELD', :expires_at, 0
);

-- Quota va ket qua idempotency thuoc cung transaction.
COMMIT;
~~~

SELECT có khóa giúp thực hiện quyết định trên pool theo thứ tự. Điều kiện trong UPDATE bảo vệ trực tiếp việc tăng lượng đã giữ. Nếu INSERT thất bại, transaction phải rollback cả phần tăng bộ đếm.

Trong SQL rút gọn, không đủ chỗ có thể kết thúc bằng rollback. Nếu muốn lưu và phát lại kết quả từ chối nghiệp vụ, cần nhánh transaction rõ ràng: chưa thay đổi quota hay pool thì có thể ghi kết quả từ chối và commit. Nếu đã thay đổi một phần, phải hoàn tác bằng cơ chế transaction phù hợp trước khi lưu kết quả. Không commit một kết quả từ chối trong khi vẫn để lại tài nguyên đã trừ.

### 7.3. Minh họa cấu trúc service Java

Đây là mã giả theo phong cách Java; tx, idem, pools, quotas và claims đại diện cho lớp truy cập dữ liệu, không phải thư viện có sẵn.

~~~java
ClaimResult claim(AuthContext auth, ClaimCommand cmd) {
    Subject subject = authorization.resolveSubject(auth, cmd.subjectId());
    long quantity = policy.validateQuantity(cmd.quantity());
    String fingerprint = canonicalFingerprint(
        auth.tenantId(), subject.id(), cmd.resourceId(), quantity
    );

    return tx.required(connection -> {
        IdempotencyDecision decision = idem.acquire(
            connection, auth, "CREATE_CLAIM",
            cmd.idempotencyKey(), fingerprint
        );

        if (decision.hasResult()) {
            return decision.originalResult();
        }

        Pool pool = pools.lock(
            connection, auth.tenantId(), cmd.resourceId()
        );
        Quota quota = quotas.lock(
            connection, auth.tenantId(), subject.id(), pool.quotaScope()
        );

        authorization.checkClaimPermission(connection, auth, subject, pool);
        policy.checkEligibility(connection, subject, pool);
        quota.requireRoom(quantity);

        Instant decisionTime = clock.readDatabaseWallClock(connection);
        Instant expiresAt = policy.expiryFrom(decisionTime, pool);

        if (pools.reserveIfAvailable(connection, pool, quantity) != 1) {
            throw new InsufficientCapacity();
        }

        quotas.increase(connection, quota, quantity);
        Claim created = claims.insertHeld(
            connection, auth.tenantId(), subject.id(),
            pool.id(), quantity, expiresAt
        );

        ClaimResult result = ClaimResult.created(created);
        idem.complete(connection, decision, result);
        return result;
    });
}
~~~

Các điều kiện đi kèm:

- Tất cả lời gọi bên trong dùng cùng connection và transaction.
- tx.required chỉ trả kết quả thành công ra ngoài sau commit.
- Lỗi không đủ chỗ trong ví dụ Java làm rollback và không lưu kết quả từ chối.
- readDatabaseWallClock phải đọc thời gian tại lúc gọi, sau khi chờ khóa. Không mặc định biểu thức trả thời điểm bắt đầu transaction có cùng ý nghĩa.
- quantity phải giới hạn trước các phép cộng. BIGINT hoặc long không thay thế kiểm tra miền giá trị.
- TTL được máy chủ xác định theo loại giữ chỗ mà subject được phép sử dụng.
- Không gọi dịch vụ mạng chậm trong lúc giữ khóa pool.

Khi dùng framework quản lý transaction, cần kiểm tra ranh giới transaction thực tế, đường gọi phương thức và quy tắc rollback. Annotation đơn lẻ không chứng minh mọi thay đổi đã dùng cùng transaction.

## 8. Xác nhận, trả chỗ và hết hạn

### 8.1. Giao thức khóa chung

Các luồng tạo, xác nhận, trả, hết hạn và hủy phải có thứ tự khóa thống nhất. Ví dụ:

1. Bản ghi idempotency của thao tác, nếu có.
2. Các pool theo khóa đã sắp xếp.
3. Các hàng quota theo khóa đã sắp xếp.
4. Các claim theo khóa đã sắp xếp.

Khi cần tra claim_id để biết pool và subject, có thể đọc dữ liệu định tuyến trước nếu các trường đó bất biến sau khi tạo. Sau khi có đủ khóa, phải đọc lại trạng thái hiện hành và xác minh quyền trước khi quyết định.

Không khóa claim trước trong worker hết hạn nhưng khóa pool trước trong API xác nhận. Không bổ sung khóa pool mới sau khi đã khóa quota nếu giao thức quy định toàn bộ pool phải được khóa trước. Thứ tự nhất quán giảm nguy cơ deadlock; ứng dụng vẫn phải xử lý deadlock hoặc xung đột với retry có giới hạn.

### 8.2. Xác nhận

Trong transaction:

1. Khóa đúng pool, quota cần thiết và claim.
2. Kiểm tra tenant, subject, quyền thao tác và các điều kiện phê duyệt.
3. Đọc thời gian chuẩn t sau khi có khóa.
4. Nếu claim là HELD và t < expires_at, chuyển sang CONFIRMED.
5. Giảm H và tăng C cùng lượng quantity.
6. Ghi bằng chứng điều kiện xác nhận theo yêu cầu nghiệp vụ và commit.

H + C không đổi, nên xác nhận không phải lần cấp thêm. Nếu quota tính cả HELD và CONFIRMED thì tổng quota của subject cũng không đổi.

Nếu claim đã CONFIRMED, phản hồi lặp lại phải biểu diễn trạng thái đã xác nhận, không tăng C lần nữa. Nếu claim là EXPIRED, RELEASED hoặc CANCELLED, không khôi phục quyền cũ.

Nếu đã quá hạn nhưng còn HELD, transaction có thể chuyển sang EXPIRED và hoàn tài nguyên, rồi trả kết quả “không thể xác nhận”. Nhánh này phải commit việc thu hồi trước khi trả lỗi nghiệp vụ. Ném exception làm rollback toàn bộ transaction sẽ hủy cả việc hoàn tài nguyên vừa thực hiện.

Một request đến trước hạn nhưng chờ khóa đến sau hạn không mặc nhiên được xác nhận. Điều kiện còn hạn phải được đánh giá khi đã có quyền quyết định độc quyền trên claim.

### 8.3. Chủ động trả và thu hồi hết hạn

Chủ động trả khi còn hạn tạo chuyển trạng thái HELD → RELEASED. Nếu đã quá hạn, có thể chuẩn hóa thành HELD → EXPIRED. Cả hai đều giảm H và lượng quota đang bị chiếm dụng tương ứng.

Worker có thể tìm ứng viên bằng truy vấn nhẹ:

~~~sql
SELECT tenant_id, claim_id, resource_id, subject_id
FROM resource_claim
WHERE state = 'HELD'
  AND expires_at <= :candidate_scan_time;
~~~

Đây chỉ là danh sách ứng viên. Khi xử lý từng claim, worker phải mở transaction, lấy khóa theo cùng giao thức và kiểm tra lại state cùng expires_at bằng thời gian quyết định hiện tại. Claim có thể đã được xác nhận, trả hoặc gia hạn trước khi worker có khóa.

~~~sql
UPDATE resource_claim
SET state = 'EXPIRED',
    version = version + 1
WHERE tenant_id = :tenant_id
  AND claim_id = :claim_id
  AND state = 'HELD'
  AND expires_at <= :decision_time;
~~~

Chỉ khi câu lệnh ảnh hưởng đúng một hàng mới được giảm H và quota theo quantity đã đọc dưới khóa. Các thay đổi cùng transaction; nếu kiểm tra bộ đếm thất bại thì rollback và ghi nhận lỗi nhất quán để điều tra.

Không giảm bộ đếm theo dữ liệu quét cũ. Hai worker có thể cùng thấy một ứng viên, nhưng chỉ một lần chuyển HELD → EXPIRED được phép hoàn tài nguyên.

### 8.4. Xác nhận đua với hết hạn

Hai kết quả hợp lệ:

- Xác nhận có khóa, kiểm tra thấy còn hạn và commit CONFIRMED; worker đọc lại rồi bỏ qua claim.
- Worker chuyển claim quá hạn sang EXPIRED và commit; xác nhận sau đó bị từ chối.

Nếu xác nhận lấy được khóa sau expires_at, nó không được thành công chỉ vì worker chưa chạy. Lịch chạy worker quyết định độ nhanh thu hồi, không quyết định hiệu lực của quyền xác nhận.

## 9. Idempotency và chống tích trữ

### 9.1. Xử lý yêu cầu gửi lại

Khóa idempotency cần được ràng buộc ít nhất với tenant, danh tính gọi đã xác thực, loại thao tác và key mà client gửi.

Dấu vân tay nội dung gồm subject, tài nguyên, quantity và các lựa chọn ảnh hưởng kết quả. Nếu client chọn báo giá có định danh, định danh đó cũng phải thuộc nội dung được ràng buộc và được máy chủ kiểm tra hiệu lực.

| Tình huống | Hành vi |
| --- | --- |
| Key mới | Thực hiện tối đa một lần tạo có hiệu lực |
| Cùng key, cùng nội dung, đã có kết quả | Trả kết quả tạo ban đầu đã lưu |
| Cùng key, nội dung khác | Từ chối xung đột |
| Cùng key, lần đầu đang xử lý | Chờ có giới hạn hoặc trả trạng thái đang xử lý |
| Transaction tạo bị rollback | Không để lại claim hoặc tài nguyên đã trừ một phần |

Cần ràng buộc duy nhất ở nơi lưu idempotency để hai instance không cùng “không thấy key” rồi tạo hai claim. Trong mô hình một transaction, bản ghi và kết quả hoàn thành được commit cùng claim; không commit trạng thái đang xử lý vô thời hạn nếu không có cơ chế phục hồi.

Ví dụ mất phản hồi:

1. Transaction tạo claim thành công.
2. Server mất kết nối trước khi client nhận claim_id.
3. Client gửi lại cùng key.
4. Server trả claim_id đã tạo, không trừ thêm chỗ.

Phản hồi phát lại mô tả kết quả lần tạo ban đầu. Claim có thể đã hết hạn hoặc bị hủy sau đó. API cần cung cấp cách đọc trạng thái hiện tại; phát lại phản hồi cũ không đồng nghĩa quyền vẫn còn hiệu lực.

Thời gian giữ bản ghi idempotency phải phù hợp khoảng retry được hỗ trợ. Xóa key sau 30 giây trong khi cho phép retry 5 phút có thể khiến retry muộn bị hiểu là yêu cầu mới. Hợp đồng API phải xác định giới hạn này.

### 9.2. Nhiều key vẫn có thể chiếm hết chỗ

Idempotency không ngăn một khách hàng gửi 1.000 request với 1.000 key. Cần chính sách bổ sung:

- Quota theo subject, tính HELD và CONFIRMED theo định nghĩa.
- Giới hạn số lượng và số lượt giữ đang hoạt động.
- Thời gian giữ tối đa và chính sách gia hạn.
- Điều kiện đủ tư cách nhận tài nguyên.
- Giới hạn tốc độ tạo, hủy và tạo lại.
- Kiểm soát hành vi nhiều danh tính theo mức bảo đảm của sản phẩm.

Quota phải được kiểm tra và cập nhật nguyên tử. Nếu hai request cùng thấy subject đang giữ 3 trong giới hạn 4 rồi mỗi request giữ thêm 1, invariant vẫn bị phá dù pool còn nhiều chỗ.

Rate limit điều tiết tốc độ. Quota giới hạn lượng đang bị chiếm dụng hoặc tổng quyền đã cấp theo phạm vi. Giới hạn request mỗi phút không thay thế giới hạn số ghế.

IP và thiết bị là tín hiệu hỗ trợ: nhiều người hợp lệ có thể chung mạng, còn người lạm dụng có thể đổi địa chỉ. Không dùng IP làm định nghĩa duy nhất của subject.

## 10. TTL, gia hạn và công bằng

### 10.1. Thời hạn phản ánh chi phí chiếm dụng

TTL quá dài cho phép giữ tài nguyên mà không hoàn tất; TTL quá ngắn làm người dùng hợp lệ mất quyền khi thực hiện điều kiện cần thiết.

Cần xác định:

- Thời gian giữ mặc định.
- Thời gian giữ tối đa tính từ lúc tạo ban đầu.
- Số lần gia hạn và điều kiện được gia hạn.
- Có cho gia hạn sau khi hết hạn hay không; ví dụ này không cho phép.
- Hành vi khi đang thanh toán hoặc chờ phê duyệt bên ngoài.

Nếu mỗi lần gọi đều được đặt expires_at = now + TTL, client có thể gia hạn vô hạn. Cần giới hạn theo created_at hoặc một mốc tuyệt đối do máy chủ quản lý.

Gia hạn phải kiểm tra quyền, trạng thái và thời gian trong transaction. Worker đã chọn ứng viên phải đọc lại expires_at sau khi có khóa.

### 10.2. Thu hồi theo kịp tải thực tế

Có thể kết hợp worker nền theo lô nhỏ, thu hồi khi truy cập claim quá hạn và thu hồi có giới hạn khi pool thiếu chỗ.

Nếu thu hồi claim của nhiều subject, phải giữ thứ tự khóa đã quy định. Không mở transaction quá lớn hoặc khóa tùy tiện thêm quota của chủ thể khác trong lúc đã đi qua bước khóa claim.

Worker chậm làm tài nguyên bị giữ lâu hơn về mặt bộ đếm. Cần thu hồi đáng tin cậy và theo dõi độ trễ; không bỏ qua kiểm tra sức chứa để bù cho worker.

### 10.3. Hàng đợi và mức ưu tiên

Cấp chỗ theo ai đến trước cần định nghĩa “đến trước” ở đâu: nhận HTTP, vào hàng đợi hay lúc quyết định transaction. Thứ tự lấy khóa của cơ sở dữ liệu không tự bảo đảm công bằng theo thời điểm bấm nút.

Nếu dùng hàng đợi:

- Ticket và mức ưu tiên do máy chủ cấp, xác minh.
- Client không được tự tăng priority hoặc dùng lại ticket đã tiêu thụ.
- Quy tắc bỏ hàng, hết hạn và thử lại phải rõ ràng.
- Người được gọi từ hàng đợi vẫn phải qua kiểm tra sức chứa cuối cùng.

Bảo toàn sức chứa và công bằng là hai mục tiêu cần thiết kế riêng. Cơ chế chống cấp thừa có thể đúng nhưng vẫn để một nhóm bot liên tục thắng chỗ.

## 11. Quyền theo đối tượng và điều kiện phê duyệt

Mọi endpoint đọc, xác nhận, trả, gia hạn hoặc hủy đều phải kiểm tra:

~~~text
actor thuộc tenant nào?
actor có được thao tác thay subject này không?
claim có thuộc đúng tenant và subject được phép không?
thao tác có hợp lệ với state hiện tại không?
bằng chứng phê duyệt hoặc thanh toán có đúng claim này không?
~~~

Không tải claim bằng claim_id rồi mặc định người biết mã được thao tác. Truy vấn cần giới hạn tenant; chính sách xác minh subject hoặc quyền quản trị được giao.

Bằng chứng phê duyệt phải gắn với nội dung được duyệt. Nếu quản lý duyệt 1 chỗ cho khách A, client không được đổi quantity thành 4 hoặc chuyển quyền đó sang khách B rồi xác nhận.

Nếu có giá, máy chủ tra giá hoặc báo giá hợp lệ, tính tổng tiền và kiểm tra quan hệ giữa thanh toán với claim. Giá thấp hơn hoặc cờ paid = true từ client không phải điều kiện đủ.

Khi nội dung đã duyệt thay đổi, cần giữ nội dung claim bất biến hoặc tăng phiên bản và yêu cầu duyệt lại phiên bản mới.

Nhật ký cần thể hiện ai cấp, xác nhận, hủy, theo quyền nào và phiên bản chính sách nào. Điều này giúp phát hiện đường API cho phép bỏ qua một bước bắt buộc.

## 12. Thanh toán và dịch vụ bên ngoài

Cơ sở dữ liệu phân bổ không thể tự commit nguyên tử cùng cổng thanh toán qua HTTP thông thường.

Không giữ khóa pool trong lúc gọi mạng rồi giả định mọi sự cố đều rollback được. Thanh toán có thể thành công dù ứng dụng hết thời gian chờ và transaction local bị hủy.

Một mô hình có thể là:

1. Tạo claim HELD cùng dữ liệu cần thiết và sự kiện outbox trong transaction local.
2. Sau commit, xử lý thanh toán hoặc phê duyệt với idempotency phù hợp.
3. Xác thực nguồn kết quả và ánh xạ đúng payment, claim, số lượng, tiền và phiên bản.
4. Chuyển trạng thái theo chính sách nghiệp vụ.

Phải có nhánh khi thanh toán đến sau lúc claim hết hạn:

- Nếu chính sách cho phép, thử cấp lại bằng quyết định mới với kiểm tra sức chứa đầy đủ.
- Hoặc hoàn tiền, xử lý bù theo chính sách.

Không hồi sinh EXPIRED và tăng C trực tiếp khi tài nguyên đã được cấp cho người khác.

Nếu cần bảo đảm quyền trong thời gian thanh toán, phải mô hình hóa trạng thái và thời hạn chiếm dụng. Trạng thái trung gian vẫn thuộc phép tính sức chứa; đổi tên thành PAYMENT_PENDING không làm lượng chiếm dụng biến mất khỏi invariant.

Với nhiều dịch vụ, chọn rõ nơi có thẩm quyền cấp tài nguyên. Distributed lock riêng lẻ không thay thế việc lưu quyết định và xử lý retry bền vững.

## 13. Fencing khi quyền được sử dụng ngoài cơ sở dữ liệu

Với ghế sự kiện, claim có thể là quyền cần bảo vệ. Với slot tác vụ hoặc máy ảo, worker còn truy cập tài nguyên thực sau khi được cấp.

Tình huống:

1. Worker A giữ slot và bắt đầu xử lý.
2. A bị treo hoặc mất kết nối, lease hết hạn.
3. Hệ thống cấp cùng slot cho B.
4. A hoạt động trở lại và tiếp tục ghi dữ liệu.

Thu hồi claim chưa chắc dừng được A. Có thể dùng fencing token khi cần ngăn chủ cũ tiếp tục gây tác động:

- Mỗi lần cấp lại cùng tài nguyên hoặc slot có một thế hệ tăng đơn điệu.
- Worker gửi token khi thao tác với tài nguyên đích.
- Nơi nhận kiểm tra nguyên tử và từ chối thế hệ cũ.

Version tăng riêng trên từng claim mới không đương nhiên là fencing token của slot. Nếu claim A và B cùng bắt đầu ở version 0 thì không biết ai được cấp sau. Token phải tăng theo đúng tài nguyên cần loại bỏ chủ cũ.

Fencing có tác dụng khi nơi nhận thực sự kiểm tra token và giữ được thông tin thế hệ. Nó không thay thế xác thực, kiểm tra thời hạn hoặc cơ chế hủy công việc. Nếu tài nguyên đích không hỗ trợ fencing, phải có cách khác để cô lập hoặc dừng quyền cũ trước khi cấp lại.

## 14. Kiểm thử tình huống tấn công logic

Phải quan sát cả kết quả API lẫn dữ liệu đã commit. HTTP 200 hoặc 409 riêng lẻ không chứng minh tài nguyên được bảo toàn.

| Tình huống | Cách thực hiện | Điều phải khẳng định |
| --- | --- | --- |
| Tranh chỗ cuối | Hai connection cùng xin 1 chỗ khi K = 1 | Chỉ một claim có hiệu lực; H + C = 1 |
| Nhiều request đồng thời | Tổng quantity yêu cầu lớn hơn K | Lượng cấp không vượt K |
| Retry sau mất phản hồi | Commit rồi ngắt phản hồi, gửi lại cùng key | Cùng claim_id, không tăng H lần nữa |
| Trùng key khác nội dung | Đổi quantity hoặc subject, giữ key | Từ chối xung đột, dữ liệu không đổi |
| Nhiều key vượt quota | Cùng subject gửi đồng thời key khác nhau | Tổng lượng trong phạm vi không vượt L |
| Quantity không hợp lệ | 0, số âm, quá lớn, số thập phân | Bị từ chối trước khi thay đổi dữ liệu |
| Sai quyền đối tượng | Đổi sang claim_id của người khác | Không đọc dữ liệu nhạy cảm hoặc thay đổi quyền |
| Sai tenant | Dùng resource_id của tenant khác | Không tác động tài nguyên ngoài phạm vi |
| Xác nhận đua hết hạn | Hai transaction xử lý cùng claim | Một chuyển trạng thái thắng; bộ đếm khớp |
| Đúng biên thời gian | Quyết định tại t = expires_at | Xác nhận bị từ chối |
| Chờ khóa qua thời hạn | Chặn xác nhận đến quá hạn | Không dùng thời gian đọc trước khi chờ |
| Worker chạy lặp | Hai worker thu hồi cùng claim | Chỉ giảm H và quota một lần |
| Ứng viên hết hạn đã cũ | Gia hạn sau quét, trước khi worker có khóa | Worker không thu hồi claim còn hạn |
| Xác nhận hoặc trả lặp | Gọi lại sau lần thành công | Không đổi bộ đếm lần hai |
| Lỗi giữa transaction | Lỗi sau tăng H, trước INSERT hoặc commit | Không lưu thay đổi riêng lẻ |
| Thanh toán đến muộn | Gửi kết quả sau EXPIRED | Không hồi sinh quyền; xử lý bù đúng chính sách |
| Giảm capacity | Đặt K nhỏ hơn H + C | Từ chối hoặc qua quy trình thu hồi rõ ràng |
| Chủ lease cũ quay lại | A dùng token cũ sau khi slot cấp cho B | Nơi nhận từ chối A nếu có fencing |

Tổ chức kiểm thử đồng thời:

1. Dùng nhiều transaction và connection thật trên hệ quản trị mục tiêu.
2. Dùng barrier hoặc cơ chế điều phối để chạm đúng điểm cạnh tranh.
3. Chủ động giữ rồi nhả khóa theo kịch bản.
4. Thu thập mọi kết quả, kể cả deadlock, timeout và retry.
5. Truy vấn lại dữ liệu đã commit để kiểm tra invariant.

Không chỉ dùng mock repository hoặc sleep ngẫu nhiên rồi kết luận không có race condition. Sleep có thể không tạo lịch thực thi gây lỗi. Nguồn clock phục vụ kiểm thử phải phản ánh đúng quyết định sau khi lấy khóa.

Các phép đối soát:

~~~text
held_qty
    = SUM(quantity của claim có state HELD)

confirmed_qty
    = SUM(quantity của claim có state CONFIRMED)

held_qty + confirmed_qty <= capacity_qty

quota_used(subject, scope)
    = SUM(quantity của các claim được chính sách quota tính vào)
~~~

Đối soát cần ảnh chụp nhất quán hoặc đồng bộ phù hợp. Đọc bộ đếm trước một commit và danh sách claim sau commit có thể tạo kết quả sai lệch giả.

Trong mô hình này, SUM cho HELD không lọc expires_at. Khi transaction chuyển sang EXPIRED, tập claim và bộ đếm mới thay đổi cùng nhau.

## 15. Quan sát và xử lý sai lệch

Nên theo dõi:

- Tỷ lệ cấp thành công, thiếu sức chứa, vượt quota và từ chối quyền.
- Thời gian chờ khóa, deadlock, retry và độ dài hàng đợi.
- Số claim HELD quá hạn chưa thu hồi, lượng bị giữ và độ trễ thu hồi.
- Hành vi tạo rồi hủy, gia hạn và hết hạn theo nhóm.
- Idempotency replay và xung đột nội dung cùng key.
- Sai lệch giữa bộ đếm, tổng claim và quota.
- Xác nhận muộn hoặc thao tác bị từ chối vì fencing token cũ.

Audit log có thể chứa claim_id, resource_id, tenant, actor, subject, trạng thái trước/sau, quantity, thời điểm quyết định và lý do từ chối, với quyền truy cập log phù hợp. Không ghi token xác thực hoặc dữ liệu thanh toán nhạy cảm.

Không dùng từng claim_id hay subject_id làm nhãn metric có số lượng giá trị không giới hạn. Metric tổng hợp phục vụ vận hành; log được kiểm soát phục vụ điều tra đối tượng cụ thể.

Nếu bộ đếm lệch dữ liệu claim, không đặt lại lượng trống bằng tay trong lúc hệ thống vẫn cấp chỗ. Cần kiểm soát đường ghi liên quan, xác định nguồn dữ liệu chuẩn, sửa có điều phối và lưu vết. Sửa bộ đếm mà bỏ qua claim có quyền thực có thể tạo thêm lượt cấp vượt sức chứa.

## 16. Những thiết kế dễ gây sai quy tắc

| Thiết kế | Vấn đề | Hướng thay thế |
| --- | --- | --- |
| Frontend khóa nút sau một lần bấm | Vẫn gửi request trực tiếp được | Idempotency và kiểm tra máy chủ |
| Đọc số dư rồi ghi số đã tính | Hai request dùng dữ liệu cũ | Khóa hoặc cập nhật có điều kiện |
| Chỉ giới hạn request | Nhiều request nhỏ vẫn giữ hết chỗ | Quota theo lượng và subject |
| Cấp ở Redis, ghi claim ở DB riêng | Sự cố có thể làm hai nơi lệch nhau | Nơi quyết định chuẩn và giao thức nhất quán |
| Hết TTL thì cộng chỗ, không kiểm tra state | Worker lặp trả nhiều lần | Chuyển trạng thái có điều kiện cùng transaction |
| Chỉ kiểm tra HELD khi xác nhận | Claim quá hạn vẫn được nhận | Kiểm tra state và thời gian |
| Gia hạn vô hạn khi client ping | Một người giữ chỗ mãi | Thời hạn tuyệt đối và điều kiện gia hạn |
| Tin claim_id khó đoán | Biết mã là có thể chiếm quyền | Quyền theo tenant, subject và thao tác |
| Retry bằng key mới | Tạo thêm claim sau phản hồi mất | Dùng lại key trong khoảng được hỗ trợ |
| Chỉ bảo vệ endpoint tạo | Hủy hoặc chỉnh capacity làm lệch số lượng | Mọi đường thay đổi giữ cùng invariant |

Nếu cần đồng thời nhiều tài nguyên, chẳng hạn phòng và thiết bị, phải quyết định có cho cấp một phần không. Với thao tác tất cả hoặc không có gì trong một cơ sở dữ liệu, khóa các pool theo thứ tự ổn định, kiểm tra toàn bộ rồi commit cùng transaction. Với nhiều hệ thống, cần giao thức đặt trước và xử lý bù tương ứng.

## 17. Checklist áp dụng

- Đơn vị tài nguyên và phạm vi tenant nào được bảo vệ?
- HELD, CONFIRMED và trạng thái trung gian nào chiếm sức chứa?
- Ai là actor, ai là subject và quota tính trên ai?
- Pool, claim, quota và idempotency có cùng ranh giới commit không?
- Tạo, xác nhận, trả, hết hạn, gia hạn và chỉnh capacity có theo cùng giao thức đồng thời không?
- Thời gian hiệu lực được quyết định sau khi có khóa bằng nguồn clock nào?
- Cùng key khác nội dung xử lý ra sao; idempotency được lưu bao lâu?
- Có ngăn tích trữ bằng nhiều key và gia hạn vô hạn không?
- Phê duyệt, thanh toán có gắn đúng claim và nội dung được duyệt không?
- Worker chạy lại hoặc chủ lease cũ quay lại có thể gây tác động lần nữa không?
- Kiểm thử đồng thời đã kiểm tra bộ đếm khớp quyền sở hữu sau commit chưa?
- Khi thu hồi chậm hoặc dữ liệu lệch, quy trình sửa bảo vệ invariant nào?

Một claim an toàn là quyết định cấp quyền có chủ thể, phạm vi, số lượng, trạng thái và thời hạn rõ ràng. Các quan hệ đó phải được giữ xuyên suốt vòng đời tài nguyên, kể cả khi request bị gửi lại, transaction cạnh tranh và người dùng chủ động tìm cách lạm dụng.
