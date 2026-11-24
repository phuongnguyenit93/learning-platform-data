# Optimistic version checking

## Mục tiêu bài học

Optimistic version checking là cơ chế chỉ cho phép một thay đổi được áp dụng khi phiên bản dữ liệu hiện tại vẫn khớp với phiên bản mà thao tác đó dựa vào. Nếu dữ liệu đã thay đổi, hệ thống báo xung đột thay vì âm thầm dùng một quyết định được tính từ trạng thái cũ.

Trong bảo mật logic nghiệp vụ, cơ chế này giúp ngăn ghi đè cập nhật, phê duyệt một nội dung khác với nội dung đã xem và áp dụng một thao tác khi trạng thái nghiệp vụ đã chuyển. Hiệu quả bảo vệ phụ thuộc vào việc version bao phủ đúng dữ liệu cần bảo vệ và mọi đường ghi đều tuân thủ cùng quy tắc.

Sau bài học, bạn có thể:

- Nhận diện khoảng trống giữa lúc đọc, kiểm tra và ghi dữ liệu.
- Thiết kế câu lệnh cập nhật nguyên tử với version kỳ vọng.
- Kết hợp version với quyền theo đối tượng, state machine và transaction.
- Xác định khi nào version của một bản ghi chưa đủ bảo vệ bất biến nhiều bản ghi.
- Phân biệt xung đột cần người dùng xem lại với lỗi có thể retry an toàn.
- Kiểm thử đồng thời bằng lịch thực thi có kiểm soát.

## 1. Vấn đề: quyết định đúng với dữ liệu cũ có thể sai khi được ghi

Giả sử một đơn hàng nháp có dòng sản phẩm với số lượng 2, tổng tiền 200.000 và `version=9`.

Hai yêu cầu cùng đọc trạng thái này:

- A muốn đổi số lượng thành 4 và tính tổng tiền mới là 400.000.
- B muốn đổi số lượng thành 5 và tính tổng tiền mới là 500.000.

Nếu cả hai chỉ cập nhật theo ID, yêu cầu ghi sau có thể thay kết quả của yêu cầu ghi trước mà không biết đã có thay đổi khác.

| Thời điểm | Yêu cầu A | Yêu cầu B | Trạng thái lưu trữ |
|---|---|---|---|
| T1 | Đọc số lượng 2, version 9 | | Số lượng 2, version 9 |
| T2 | | Đọc số lượng 2, version 9 | Số lượng 2, version 9 |
| T3 | Ghi số lượng 4 | | Số lượng 4 |
| T4 | | Ghi số lượng 5 | Số lượng 5; thay đổi của A không được nhận biết |

Đây là một dạng mất cập nhật, thường gọi là lost update. Tác động nghiệp vụ có thể lớn hơn một trường dữ liệu: tổng tiền, giới hạn mua, quyết định duyệt hoặc tài liệu đi kèm có thể không còn tương ứng với điều người dùng đã xem.

Với kiểm tra version, cả hai yêu cầu phải gửi điều kiện `expectedVersion=9`. Một yêu cầu cập nhật thành công và tăng version lên 10. Yêu cầu còn lại không còn thỏa điều kiện nên phải nhận xung đột.

Cơ chế này không quyết định A hay B đáng được ưu tiên. Nó bảo đảm hai ý định cùng dựa vào một phiên bản không âm thầm ghi đè nhau.

## 2. Nguyên tắc cốt lõi: so sánh và cập nhật trong cùng thao tác nguyên tử

Một kiểm tra trong mã ứng dụng chưa đủ:

```text
current = đọc đơn hàng
nếu current.version == expectedVersion:
    cập nhật đơn hàng chỉ theo ID
```

Dữ liệu có thể đổi sau câu `if` và trước câu cập nhật. Cần đưa điều kiện version vào chính thao tác ghi:

```sql
UPDATE purchase_order
SET note = :validatedNote,
    version = version + 1
WHERE tenant_id = :authenticatedTenantId
  AND id = :orderId
  AND status = 'DRAFT'
  AND version = :expectedVersion;
```

Các tham số phải được bind bằng cơ chế truy vấn có tham số, không ghép trực tiếp chuỗi người dùng vào SQL.

- Cập nhật đúng 1 dòng: điều kiện ghi đã khớp ở lần thực thi đó.
- Cập nhật 0 dòng: ít nhất một điều kiện không còn đúng hoặc đối tượng không thuộc phạm vi truy vấn.
- Không được bỏ điều kiện version rồi chạy lại cùng thay đổi để “khắc phục” kết quả 0 dòng.

Số dòng cập nhật bằng 1 chưa có nghĩa toàn bộ nghiệp vụ đã commit. Nếu transaction sau đó thất bại, thay đổi và version phải cùng rollback.

Khi dùng kiểu số nguyên hữu hạn cho version, phải có chính sách tránh tràn số. Không để bộ đếm quay về giá trị cũ hoặc bị reset bởi import, script sửa dữ liệu hay quá trình phục hồi.

## 3. Xác định dữ liệu nào phải được version bảo vệ

Version nên đại diện cho phạm vi mà quyết định nghiệp vụ dựa vào. Phạm vi đó thường là một aggregate: tập dữ liệu có những bất biến cần được duy trì cùng nhau.

Ví dụ một đơn hàng có:

```text
PurchaseOrder
    tenantId
    status
    totalAmount
    version
    OrderLine[]
        productId
        quantity
        unitPriceSnapshot
```

Nếu quyết định phê duyệt dựa vào các dòng hàng và tổng tiền, mọi thay đổi ảnh hưởng những dữ liệu đó phải làm thay đổi version của đơn hàng hoặc một snapshot được liên kết rõ ràng với version đó.

| Thay đổi | Có cần tác động tới version dùng để bảo vệ nội dung đơn hàng? |
|---|---|
| Đổi số lượng, sản phẩm hoặc giá được phép áp dụng | Có |
| Thêm hoặc xóa dòng | Có |
| Chuyển `DRAFT` sang `SUBMITTED` | Có |
| Đổi tài liệu làm bằng chứng phê duyệt | Có, hoặc đổi định danh snapshot được kiểm tra cùng version |
| Cập nhật thông tin kỹ thuật không ảnh hưởng quyết định | Tùy mô hình; có thể tách version nếu không làm mất bất biến |
| Thay đổi dữ liệu ngoài aggregate, như hạn mức chung của dự án | Cần cơ chế bảo vệ riêng cho dữ liệu ngoài đó |

Không nên có một đường API cập nhật dòng và tăng version, trong khi tác vụ import hoặc admin script sửa trực tiếp dòng mà không thay đổi version gốc. Khi đó, người duyệt có thể thấy version không đổi dù nội dung thực tế đã khác.

Đối với một màn hình tổng hợp nhiều nguồn, version của riêng đơn hàng không tự bao phủ bảng giá, quyền truy cập, hạn mức dự án hoặc tồn kho. Cần xác định dữ liệu nào được chốt thành snapshot và dữ liệu nào phải kiểm tra lại khi ghi.

## 4. Hợp đồng yêu cầu: version biểu diễn điều kiện, không biểu diễn quyền

Một lệnh sửa số lượng có thể có dạng:

```json
{
  "orderId": "1be70a4e-1fcb-42a0-a06e-863c75b716f8",
  "lineId": "f8098811-d13e-46d9-890f-aa93639dd046",
  "newQuantity": 4,
  "expectedVersion": 9
}
```

Máy chủ vẫn phải tự xác định tenant từ ngữ cảnh xác thực, kiểm tra quyền sửa đơn hàng và xác minh dòng thuộc đúng đơn hàng.

`expectedVersion` có ba tính chất cần giữ:

1. Nó mô tả phiên bản mà phía gọi đã dựa vào.
2. Máy chủ so sánh nó với dữ liệu thực, không dùng nó để tự gán version hiện tại.
3. Nó không phải bí mật, chữ ký, quyền truy cập hoặc bằng chứng rằng người dùng thật sự đã đọc nội dung.

Một người dùng gửi đúng version của đơn hàng ngoài quyền vẫn phải bị từ chối. Một người gửi version rất lớn không được làm bộ đếm nhảy tới giá trị đó. Thiếu version cũng không được hiểu là bỏ qua kiểm tra đối với thao tác yêu cầu điều kiện này.

Nếu HTTP API dùng `ETag` và `If-Match`, cần thiết kế validator phù hợp với tài nguyên hoặc biểu diễn được bảo vệ và ánh xạ đúng về điều kiện ghi. Không dùng một ETag không bao phủ phần dữ liệu đã thay đổi rồi cho rằng nó tương đương version nghiệp vụ. Có thể dùng version trong body nếu đó là hợp đồng được chọn; các đường gọi khác nhau phải có ngữ nghĩa nhất quán.

## 5. Duy trì version mà người dùng đã dựa vào

Một lỗi dễ gặp là đọc lại dữ liệu mới nhất rồi thay luôn version kỳ vọng của phía gọi:

```text
client gửi expectedVersion = 9
server đọc thấy version = 10
server dùng version = 10 để cập nhật ý định được tính từ version 9
```

Cách này làm câu lệnh cập nhật có vẻ an toàn nhưng bỏ qua xung đột mà người dùng cần biết.

Luồng hợp lệ thường là:

1. Nhận version kỳ vọng từ lệnh và kiểm tra kiểu, miền giá trị.
2. Đọc dữ liệu trong phạm vi được phép.
3. Nếu snapshot đọc được khác version kỳ vọng, dừng hoặc đi vào một quy trình gộp đã được thiết kế rõ ràng.
4. Kiểm tra quyền, trạng thái và tính toán giá trị mới từ dữ liệu tin cậy.
5. Ghi với điều kiện version kỳ vọng ban đầu.
6. Nếu câu ghi không cập nhật đúng một bản ghi, rollback và báo xung đột hoặc lỗi phạm vi thích hợp.

Kiểm tra ở bước 3 giúp báo lỗi sớm. Điều kiện ghi ở bước 5 vẫn bắt buộc vì dữ liệu có thể đổi giữa hai bước đó.

Nếu thao tác được thiết kế là một ý định có thể tính lại trên trạng thái mới, việc retry phải đọc, kiểm tra và tính lại toàn bộ phần liên quan. Nó không phải một ngoại lệ cho phép ghi đè bằng kết quả tính từ snapshot cũ.

## 6. Ví dụ SQL: thay số lượng và tổng tiền trong một transaction

Giả sử máy chủ đã xác minh số lượng hợp lệ, tra đúng dòng hàng và tính tổng mới theo chính sách giá của đơn hàng. Các giá trị tiền không được lấy tùy ý từ request.

```sql
BEGIN;

UPDATE purchase_order
SET total_amount = :serverCalculatedTotal,
    version = version + 1
WHERE tenant_id = :authenticatedTenantId
  AND id = :orderId
  AND status = 'DRAFT'
  AND version = :expectedVersion;

-- Mã ứng dụng phải kiểm tra đúng 1 dòng được cập nhật.
-- Nếu không đạt: ROLLBACK, không chạy tiếp các thay đổi phụ thuộc.

UPDATE order_line
SET quantity = :validatedQuantity
WHERE tenant_id = :authenticatedTenantId
  AND order_id = :orderId
  AND id = :lineId;

-- Mã ứng dụng tiếp tục kiểm tra đúng 1 dòng được cập nhật.

INSERT INTO order_audit (
    tenant_id, order_id, actor_id, event_type, from_version, to_version
) VALUES (
    :authenticatedTenantId, :orderId, :authenticatedActorId,
    'QUANTITY_CHANGED', :expectedVersion, :expectedVersion + 1
);

COMMIT;
```

Khối SQL minh họa thứ tự thao tác; các dòng comment không tự tạo cơ chế rollback. Service phải kiểm tra update count, bắt lỗi và điều khiển transaction tương ứng.

Các điều kiện để ví dụ bảo vệ được dữ liệu:

- Mọi đường sửa nội dung liên quan đều tham gia cơ chế version của đơn hàng.
- Dòng hàng được xác minh thuộc đúng đơn hàng, và việc cập nhật dòng, tổng tiền, version, audit nằm trong cùng transaction.
- Chính sách quyền được thực thi trong phạm vi thích hợp; điều kiện tenant không thay thế đầy đủ kiểm tra quyền sửa.
- `serverCalculatedTotal` được tính từ dữ liệu mà version bảo vệ hoặc từ các phụ thuộc được kiểm soát riêng.
- Nếu có một lỗi sau cập nhật đơn hàng, transaction rollback cả version lẫn dữ liệu nghiệp vụ.

Cập nhật root trước giúp xác lập quyền thực hiện lần ghi theo version trước khi áp dụng thay đổi phụ thuộc. Điều đó không thay thế việc kiểm tra các bất biến trên trạng thái kết quả, chẳng hạn giới hạn tổng tiền hoặc tổng số lượng.

## 7. Ví dụ Java với JDBC: bắt buộc kiểm tra số dòng cập nhật

Đoạn Java 17 sau minh họa lớp ghi dữ liệu, không phải một endpoint hoàn chỉnh. `ValidatedChange` là kế hoạch do service tạo sau khi kiểm tra quyền và nghiệp vụ; không bind trực tiếp `newTotal` hoặc `tenantId` từ request của người dùng vào record này.

Đối với ví dụ, tổng tiền đã được tính từ snapshot nội dung đơn hàng tương ứng `expectedVersion`. Những phụ thuộc khác, nếu có, cần được service bảo vệ riêng.

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.UUID;

public final class OptimisticQuantityWriter {
    public record ValidatedChange(
            UUID tenantId,
            UUID orderId,
            UUID lineId,
            long expectedVersion,
            int newQuantity,
            BigDecimal newTotal) {}

    public static final class OptimisticConflict extends RuntimeException {
        public OptimisticConflict() {
            super("ORDER_UPDATE_CONDITION_FAILED");
        }
    }

    private static final String UPDATE_ORDER = """
            UPDATE purchase_order
            SET total_amount = ?, version = ?
            WHERE tenant_id = ? AND id = ?
              AND status = 'DRAFT' AND version = ?
            """;

    private static final String UPDATE_LINE = """
            UPDATE order_line
            SET quantity = ?
            WHERE tenant_id = ? AND order_id = ? AND id = ?
            """;

    public static long applyInTransaction(
            Connection connection, ValidatedChange change) throws SQLException {
        if (connection.getAutoCommit()) {
            throw new IllegalStateException("An explicit transaction is required");
        }
        if (change.expectedVersion() < 0 || change.newQuantity() <= 0) {
            throw new IllegalArgumentException("Invalid validated change");
        }

        long nextVersion = Math.addExact(change.expectedVersion(), 1L);

        try (PreparedStatement statement =
                     connection.prepareStatement(UPDATE_ORDER)) {
            statement.setBigDecimal(1, change.newTotal());
            statement.setLong(2, nextVersion);
            statement.setObject(3, change.tenantId());
            statement.setObject(4, change.orderId());
            statement.setLong(5, change.expectedVersion());

            if (statement.executeUpdate() != 1) {
                throw new OptimisticConflict();
            }
        }

        try (PreparedStatement statement =
                     connection.prepareStatement(UPDATE_LINE)) {
            statement.setInt(1, change.newQuantity());
            statement.setObject(2, change.tenantId());
            statement.setObject(3, change.orderId());
            statement.setObject(4, change.lineId());

            if (statement.executeUpdate() != 1) {
                throw new IllegalStateException("Expected line is not writable");
            }
        }

        return nextVersion;
    }
}
```

Việc bind UUID bằng `setObject` phụ thuộc khả năng driver và kiểu cột đã chọn. Nếu cơ sở dữ liệu lưu UUID theo kiểu khác, dùng ánh xạ tương ứng; không chuyển thành ghép chuỗi SQL.

Caller phải điều khiển transaction và không trả thành công trước commit:

```text
mở connection và bắt đầu transaction
try:
    tải dữ liệu, xác minh quyền và tạo kế hoạch hợp lệ
    nextVersion = applyInTransaction(connection, plan)
    ghi audit, kết quả idempotency và outbox nếu cần
    commit
    trả kết quả thành công với nextVersion
catch bất kỳ lỗi làm thao tác không hợp lệ:
    rollback
    phân loại lỗi để phản hồi hoặc retry
```

Nếu cập nhật dòng hàng thất bại sau khi root đã tăng version, không được bắt lỗi rồi vẫn commit root. Tương tự, một framework có cơ chế transaction cần được cấu hình để loại lỗi xung đột thực sự làm rollback theo hợp đồng của nó.

Ví dụ cố ý giữ việc đọc và quyết định nghiệp vụ ở service. Repository thực hiện cập nhật có điều kiện; nó không tự chữa xung đột bằng cách đọc version mới rồi ghi lại.

## 8. Kết hợp với state machine và quyết định phê duyệt

### 8.1. Version và trạng thái có trách nhiệm khác nhau

Điều kiện `status='DRAFT'` trả lời: trạng thái hiện tại có cho phép sửa không?

Điều kiện `version=:expectedVersion` trả lời: dữ liệu còn đúng phiên bản mà ý định này dựa vào không?

Một đơn hàng có thể đi qua:

```text
DRAFT, version 9
    -> SUBMITTED, version 10
    -> DRAFT, version 11
```

Trạng thái cuối vẫn là `DRAFT`, nhưng yêu cầu sửa từ version 9 đã cũ. Chỉ kiểm tra trạng thái sẽ không phát hiện chu trình này. Đây là một tình huống tương tự vấn đề ABA: giá trị quan sát quay lại như trước, trong khi lịch sử ở giữa đã thay đổi.

Version phải tiếp tục tăng khi chuyển trạng thái; không reset về 0 khi trả hồ sơ về nháp.

### 8.2. Phê duyệt phải gắn với nội dung đã xem

Một thao tác duyệt có thể yêu cầu:

```sql
UPDATE purchase_order
SET status = 'APPROVED',
    approved_by = :authenticatedApproverId,
    version = version + 1
WHERE tenant_id = :authenticatedTenantId
  AND id = :orderId
  AND status = 'SUBMITTED'
  AND version = :reviewedVersion;
```

Máy chủ còn phải kiểm tra quyền duyệt, quy tắc phân tách người tạo và người duyệt nếu có, cùng các điều kiện nghiệp vụ khác. Nếu số dòng cập nhật không bằng 1, không tạo một bản ghi phê duyệt thành công độc lập bên ngoài transaction.

`reviewedVersion` chỉ hữu ích khi nó bao phủ nội dung mà người duyệt đã xem. Nếu thay file đính kèm không làm đổi version hoặc snapshot liên quan, câu lệnh trên vẫn có thể duyệt nội dung khác với nội dung đã xem.

Quyết định duyệt nên lưu version hoặc snapshot nguồn đã được chấp thuận, không chỉ trạng thái cuối. Version mới sau chuyển trạng thái và version nội dung được xét duyệt cần được diễn giải rõ trong audit.

## 9. Quyền truy cập cũng có thể thay đổi đồng thời

Kiểm tra version dữ liệu không tự bảo vệ quyền. Ví dụ:

```text
T1: dịch vụ đọc quyền của người được ủy quyền, thấy còn hiệu lực
T2: quản trị viên thu hồi ủy quyền
T3: dịch vụ cập nhật đơn hàng với version vẫn khớp
```

Nếu quyền ủy quyền không nằm trong phạm vi version đơn hàng, điều kiện version không phát hiện thay đổi ở T2.

Hệ thống phải xác định rõ thời điểm mà quyết định quyền có hiệu lực và cơ chế nhất quán tương ứng. Tùy chính sách, có thể kiểm tra quyền trong điều kiện ghi, kiểm tra một authorization revision, hoặc phối hợp khóa hay transaction với dữ liệu quyền.

Một phép đọc quyền trước đó trong cùng transaction không mặc nhiên giải quyết mọi lịch thu hồi quyền. Cần xem cơ chế isolation và cách đường thu hồi quyền tham gia cùng quy tắc.

Không đưa ra bảo đảm “thu hồi có hiệu lực ngay trước commit” nếu cách triển khai chỉ dùng một snapshot quyền đã đọc từ đầu. Với tác vụ nền và lệnh bị trì hoãn, cần quyết định kiểm tra lại quyền tại thời điểm thực thi theo chính sách nghiệp vụ.

## 10. Giới hạn: version từng bản ghi không tự bảo vệ bất biến nhiều bản ghi

### 10.1. Ví dụ write skew với ngân sách chung

Một dự án còn ngân sách 100 đơn vị. Hai yêu cầu tạo cam kết chi:

- A tạo khoản 80 trên chứng từ A.
- B tạo khoản 80 trên chứng từ B.

Cả hai đọc tổng cam kết hiện tại bằng 0. Mỗi yêu cầu sửa một chứng từ khác nhau, với version khác nhau, nên các điều kiện version riêng lẻ đều có thể thành công. Tổng cam kết sau đó thành 160, vi phạm giới hạn 100.

Đây là một dạng write skew: các transaction ghi vào các bản ghi khác nhau nhưng cùng phá một bất biến được tính từ tập dữ liệu chung.

Không thể giải quyết chỉ bằng việc thêm `version` vào mỗi chứng từ nếu các yêu cầu không tranh chấp trên một điều kiện bao phủ ngân sách chung.

### 10.2. Chọn ranh giới kiểm soát phù hợp

| Cách tiếp cận | Cơ chế bảo vệ |
|---|---|
| Aggregate ngân sách có revision | Mọi thay đổi cam kết phải cập nhật có điều kiện cùng root ngân sách trong transaction |
| Cập nhật số dư có điều kiện | Chỉ tăng mức sử dụng nếu tổng sau thay đổi không vượt hạn mức |
| Khóa tài nguyên chung | Mọi đường ghi đọc và cập nhật bất biến dưới cùng quy ước khóa |
| Isolation mạnh hơn | Thiết kế transaction với khả năng phát hiện lịch không hợp lệ và xử lý rollback/retry |
| Ràng buộc lưu trữ phù hợp | Dùng constraint cho những bất biến có thể biểu diễn trực tiếp trong mô hình |

Ví dụ một cập nhật điều kiện cho ngân sách:

```sql
UPDATE project_budget
SET committed_amount = committed_amount + :amount,
    version = version + 1
WHERE tenant_id = :authenticatedTenantId
  AND project_id = :projectId
  AND version = :expectedBudgetVersion
  AND :amount > 0
  AND committed_amount + :amount <= limit_amount;
```

Việc tạo chứng từ và tăng cam kết phải cùng transaction. Giá trị tiền phải dùng kiểu và đơn vị phù hợp, cùng kiểm tra tràn miền số theo cách triển khai.

Nếu bất biến là “chỉ có một yêu cầu đang mở” hoặc “không được tạo thêm khi đã có bản ghi thỏa điều kiện”, nó còn liên quan tới sự xuất hiện của bản ghi mới. Version của những hàng đã đọc không tự phát hiện mọi trường hợp thêm hàng. Cần ràng buộc duy nhất, root chung hoặc cơ chế kiểm soát tương ứng với bất biến đó.

## 11. Optimistic checking không đồng nghĩa không có khóa

Tên “optimistic” mô tả cách giả định xung đột không thường xuyên rồi xác nhận điều kiện khi ghi. Nó không có nghĩa cơ sở dữ liệu không dùng khóa nội bộ.

Một câu `UPDATE` có điều kiện vẫn có thể chờ transaction khác đang giữ tài nguyên cần thiết. Kết quả có thể là cập nhật thành công, không có dòng phù hợp, timeout hoặc một lỗi cạnh tranh khác tùy hệ quản trị và mức isolation.

Vì vậy, service cần xử lý cả xung đột nghiệp vụ và lỗi transaction. Không giả định mọi cạnh tranh đều chỉ biểu hiện bằng update count bằng 0.

| Đặc tính | Optimistic version checking | Khóa bi quan |
|---|---|---|
| Cách phối hợp | Đọc rồi xác nhận version khi ghi | Giành quyền truy cập tài nguyên trước phần xử lý cần bảo vệ |
| Chi phí khi ít xung đột | Thường thuận tiện cho các thao tác ngắn | Có thể giữ khóa lâu hơn nếu phạm vi xử lý rộng |
| Khi xung đột thường xuyên | Có nhiều rollback hoặc yêu cầu xem lại | Có thể tạo chờ đợi và tranh chấp khóa |
| Bảo vệ ý định dựa trên màn hình cũ | Version kỳ vọng thể hiện điều kiện rõ ràng | Khóa ở transaction ngắn không tự bao phủ khoảng thời gian người dùng đang đọc màn hình |
| Bất biến nhiều bản ghi | Cần đúng ranh giới version | Cần đúng tài nguyên và quy ước khóa |

Có thể kết hợp version kỳ vọng từ phía gọi với khóa trong transaction để bảo vệ một bất biến phức tạp. Hai cơ chế giải quyết những phần khác nhau của bài toán.

Không giữ transaction hoặc khóa cơ sở dữ liệu trong suốt thời gian người dùng đọc màn hình, chờ phê duyệt hay thực hiện một cuộc gọi mạng dài.

## 12. Xung đột và retry: giữ đúng ý định nghiệp vụ

### 12.1. Những trường hợp nên yêu cầu xem lại

Không tự động thay version rồi áp dụng lại các thao tác mà quyết định phụ thuộc mạnh vào snapshot:

- Phê duyệt tổng tiền hoặc tài liệu đã xem.
- Ghi đè một biểu mẫu gồm nhiều trường.
- Thay thế nội dung hoặc bằng chứng nghiệp vụ.
- Đặt một giá trị tuyệt đối dựa trên lựa chọn cũ.

Khi đó, trả xung đột và cho phía gọi tải lại dữ liệu, xem khác biệt rồi gửi ý định mới nếu vẫn muốn thực hiện.

### 12.2. Những trường hợp có thể tính lại

Một ý định như “thêm một đơn vị” có thể được thiết kế để tính lại trên trạng thái mới. Tuy nhiên, retry phải kiểm tra lại quyền, trạng thái, giá, giới hạn và mọi phụ thuộc liên quan.

Ngay cả phép cộng cũng không tự an toàn: thêm một đơn vị có thể vượt tồn kho, giới hạn đơn hàng hoặc làm thay đổi tổng tiền mà người dùng cần xác nhận.

Retry nên có số lần hoặc thời gian tối đa, có khoảng lùi phù hợp và không giữ lại kết quả tính từ snapshot đã thất bại. Nếu xung đột liên tục, cần trả trạng thái rõ ràng hoặc thiết kế lại ranh giới tranh chấp.

### 12.3. Retry transaction khác với retry quyết định của con người

Deadlock hoặc lỗi serialization có thể dẫn tới yêu cầu chạy lại toàn bộ transaction theo hợp đồng của cơ sở dữ liệu. Điều đó không có nghĩa được tự chấp thuận một version mới thay người dùng.

Khi chạy lại, điều kiện `reviewedVersion` ban đầu vẫn phải được giữ. Nếu nội dung đã đổi, lần chạy lại phải kết thúc bằng xung đột nghiệp vụ thay vì cập nhật quyết định duyệt sang nội dung mới.

Các hiệu ứng bên ngoài như gửi email, thanh toán hoặc phát message không được thực hiện lặp tùy ý trong một vòng retry. Có thể dùng outbox và consumer chống trùng để tách hiệu ứng khỏi lần thực thi transaction.

## 13. Version checking và idempotency bổ sung cho nhau

Hai cơ chế trả lời hai câu hỏi khác nhau:

| Cơ chế | Câu hỏi |
|---|---|
| Version checking | Dữ liệu còn là trạng thái mà ý định này dựa vào không? |
| Idempotency | Yêu cầu này đã tạo hiệu ứng nghiệp vụ trước đó chưa? |

Giả sử yêu cầu dùng version 9 đã commit và tăng version lên 10, nhưng phản hồi bị mất. Nếu retry chỉ kiểm tra version 9, phía gọi nhận xung đột dù thao tác ban đầu đã thành công.

Khi có khóa idempotency, service có thể nhận ra cùng thao tác và trả lại kết quả đã commit sau khi xác minh phạm vi, quyền đọc kết quả và fingerprint.

Một thiết kế cần bảo đảm:

- Khóa idempotency có phạm vi phù hợp, chẳng hạn tenant, loại thao tác và đối tượng.
- Fingerprint bao gồm nội dung có ý nghĩa, trong đó có version kỳ vọng nếu version là một phần của ý định.
- Cùng khóa nhưng đổi số lượng hoặc version kỳ vọng phải được xử lý như xung đột fingerprint, không âm thầm diễn giải lại.
- Kết quả idempotency được ghi nhất quán với thay đổi dữ liệu.
- Hai yêu cầu cùng khóa đến đồng thời chỉ có một lần tạo hiệu ứng, thông qua ràng buộc duy nhất hoặc cơ chế tương đương.
- Retry một thao tác đã thành công không áp dụng lại nó hoặc đưa dữ liệu quay về kết quả cũ sau khi có thay đổi tiếp theo.

Sau khi người dùng xem lại và quyết định sửa trên version mới, đó có thể là một ý định mới và cần khóa mới theo hợp đồng API. Không thay version trong fingerprint nhưng giữ nguyên khóa cũ để né một lỗi xung đột.

## 14. ORM, bulk update và những đường ghi dễ bỏ sót

Nhiều ORM hỗ trợ trường version và kiểm tra optimistic locking. Khi dùng, cần hiểu chính xác thời điểm câu ghi được thực thi và thời điểm lỗi xung đột xuất hiện: có thể ở lúc flush hoặc commit, không nhất thiết ở lệnh gán thuộc tính.

Các điểm cần kiểm soát:

- Không trả thành công trước khi flush/commit cần thiết đã hoàn tất.
- Không nuốt lỗi optimistic locking rồi tiếp tục commit một phần nghiệp vụ.
- Không mặc định một bulk update hoặc native SQL tự áp dụng cùng cơ chế version với cập nhật entity thông thường.
- Không cho mapper ghi đè trường version của entity chỉ vì request có trường cùng tên.
- Khi ghi từ một DTO cũ, phải giữ điều kiện version mà DTO đại diện, thay vì đọc entity mới nhất rồi áp toàn bộ DTO lên đó.
- Sau cập nhật ngoài cơ chế theo dõi của ORM, xử lý trạng thái cache hoặc persistence context theo cách phù hợp để tránh tiếp tục dùng snapshot cũ.

Tác vụ import, job nền, API nội bộ, công cụ hỗ trợ và script vận hành đều có thể làm mất bảo đảm nếu sửa dữ liệu liên quan mà không tăng version đúng phạm vi.

Nếu hệ thống phục hồi một bản dữ liệu cũ, không tái sử dụng cặp định danh và version theo cách làm yêu cầu cũ trở nên hợp lệ. Có thể cần revision tiếp tục tăng hoặc một định danh thế hệ mới tùy thiết kế. Không dùng timestamp có độ phân giải hạn chế như thể nó chắc chắn phân biệt mọi lần cập nhật.

## 15. Phản hồi lỗi và audit

Một lỗi xung đột có thể có cấu trúc:

```json
{
  "code": "STALE_ORDER_VERSION",
  "message": "Đơn hàng đã thay đổi. Hãy tải lại trước khi tiếp tục.",
  "expectedVersion": 9,
  "action": "RELOAD"
}
```

Chỉ trả dữ liệu hiện tại, current version hoặc nội dung khác biệt nếu chủ thể được phép đọc chúng. Cập nhật 0 dòng không tự chứng minh đối tượng tồn tại ở version khác: nó còn có thể sai tenant, đã bị xóa hoặc không còn ở trạng thái cho phép.

Mã HTTP cần theo hợp đồng API. Nếu dùng cơ chế điều kiện HTTP như `If-Match`, phản hồi cần phù hợp với ngữ nghĩa điều kiện đó; nếu dùng lệnh nghiệp vụ với version trong body, dịch vụ có thể định nghĩa phản hồi xung đột cùng mã lỗi ổn định.

Audit thành công nên ghi:

- Tenant, đối tượng và chủ thể từ ngữ cảnh tin cậy.
- Loại thao tác, version nguồn và version kết quả.
- Thay đổi nghiệp vụ hoặc snapshot liên quan.
- Request ID, thông tin idempotency cần thiết và thời điểm commit theo thiết kế.

Bản ghi audit thành công cần nhất quán với transaction tạo hiệu ứng. Nếu transaction rollback, không để lại một bản ghi độc lập tuyên bố rằng thay đổi đã thành công.

Các lần xung đột có thể được theo dõi ở luồng quan sát hoặc audit riêng với trạng thái thất bại rõ ràng. Không ghi đầy đủ payload nhạy cảm chỉ để chẩn đoán tranh chấp, và không coi mọi xung đột đều là tấn công: nhiều trường hợp là hoạt động hợp lệ của người dùng hoặc tác vụ nền.

## 16. Kiểm thử tình huống đồng thời có chủ đích

### 16.1. Lịch kiểm thử tối thiểu

Một kiểm thử tích hợp chống lost update nên tạo hai transaction thực sự độc lập:

```text
Chuẩn bị đơn hàng DRAFT, version 9.

A đọc snapshot version 9.
B đọc snapshot version 9.
Điểm đồng bộ: chỉ cho ghi khi cả hai đã đọc xong.

Cho A và B thực hiện câu UPDATE có expectedVersion = 9.
Transaction thắng commit.
Transaction còn lại rollback khi xung đột hoặc lỗi cạnh tranh tương ứng.

Đọc lại bằng transaction mới và kiểm tra trạng thái cuối.
```

Không đặt một barrier yêu cầu cả hai câu `UPDATE` hoàn tất rồi mới cho transaction thắng commit. Transaction còn lại có thể đang chờ khóa của transaction thắng, khiến chính kiểm thử bị kẹt.

Không dùng hai lời gọi nối tiếp trên cùng connection làm bằng chứng rằng đã kiểm thử cạnh tranh. Cũng không dựa vào một khoảng `sleep` ngẫu nhiên làm cơ chế duy nhất để tạo lịch cần kiểm tra.

### 16.2. Ma trận kiểm thử lạm dụng và sai lệch logic

| Tình huống | Kết quả cần quan sát |
|---|---|
| Hai lệnh sửa cùng đơn hàng, cùng version | Một lần thay đổi hợp lệ; lần còn lại không ghi đè |
| Hai lệnh sửa hai dòng khác nhau nhưng chung root version | Tuân thủ phạm vi aggregate; không có tổng tiền sai do hai snapshot cũ |
| Version khớp nhưng người gọi không có quyền | Không thay đổi dữ liệu hoặc tiết lộ snapshot ngoài quyền |
| Thiếu version hoặc version ngoài miền hợp đồng | Từ chối trước khi tạo hiệu ứng |
| Gửi version rất lớn | Không gán version máy chủ theo giá trị client |
| Sửa ở `DRAFT`, đồng thời có người nộp hồ sơ | Kết quả tuân thủ một thứ tự hợp lệ của state machine |
| Trạng thái đi `DRAFT -> SUBMITTED -> DRAFT` | Lệnh từ version cũ vẫn bị từ chối |
| File bằng chứng thay đổi trước lúc duyệt | Quyết định cũ không chấp thuận nội dung mới |
| Cập nhật root thành công nhưng cập nhật dòng thất bại | Rollback cả root, version, audit và hiệu ứng liên quan |
| Hai chứng từ khác nhau cùng dùng ngân sách chung | Tổng cam kết không vượt bất biến, không chỉ kiểm tra version từng chứng từ |
| Quyền bị thu hồi trong khi lệnh đang xử lý | Hành vi đúng với chính sách nhất quán quyền đã công bố |
| Mất phản hồi sau commit rồi retry cùng khóa | Trả kết quả cũ nhất quán, không tạo hiệu ứng lần nữa |
| Retry cùng khóa nhưng đổi expected version | Xung đột fingerprint theo hợp đồng idempotency |
| Bulk update hoặc import thay nội dung | Version bảo vệ snapshot được cập nhật đúng |
| Deadlock hoặc serialization failure | Rollback và retry theo chính sách; không lặp hiệu ứng ngoài transaction |
| Version gần giới hạn kiểu số | Không tràn số hoặc quay lại một version cũ |

Ngoài response, kiểm tra số dòng hàng, tổng tiền, trạng thái, version, bản ghi idempotency và audit/outbox theo thiết kế. Một lỗi được trả về đúng nhưng dữ liệu đã bị thay một phần vẫn là thất bại của cơ chế bảo vệ.

## 17. Các lỗi thiết kế thường gặp

| Cách triển khai | Vì sao không đủ | Cách sửa |
|---|---|---|
| Đọc version, so sánh bằng `if`, rồi cập nhật chỉ theo ID | Có khoảng trống giữa kiểm tra và ghi | Đưa version vào điều kiện ghi nguyên tử |
| Tự lấy version mới nhất khi client gửi version cũ | Biến xung đột thành ghi đè âm thầm | Giữ điều kiện gốc hoặc gộp theo chính sách tường minh |
| Tăng version nhưng không kiểm tra version kỳ vọng | Có bộ đếm lịch sử nhưng không chặn lệnh cũ | So sánh và tăng trong cùng thao tác |
| Chỉ version hóa root nhưng sửa con trực tiếp | Snapshot thay đổi mà version không đổi | Mọi thay đổi ảnh hưởng bất biến phải tham gia quy ước chung |
| Cho rằng đúng version là đủ quyền | Người ngoài phạm vi vẫn có thể đoán hoặc đọc version | Kiểm tra quyền theo đối tượng và tenant |
| Chỉ dùng version từng hàng cho hạn mức chung | Không phát hiện write skew giữa các hàng khác nhau | Bảo vệ tài nguyên hoặc bất biến chung |
| Retry bằng cách đổi expected version rồi giữ kết quả tính cũ | Ý định và dữ liệu không còn cùng snapshot | Đọc, kiểm tra và tính lại hoặc yêu cầu xác nhận mới |
| Tách audit và cập nhật nghiệp vụ thiếu phối hợp | Có thể ghi thành công giả hoặc mất dấu vết | Transaction chung hoặc thiết kế điều phối nhất quán |
| Đồng nhất version với idempotency | Không phân biệt lệnh cũ với retry của lệnh đã thành công | Dùng cả hai theo trách nhiệm riêng |

## 18. Áp dụng vào một thao tác nghiệp vụ mới

Trước khi thêm optimistic version checking, hãy xác định rõ:

1. Ý định nào đang được bảo vệ, và nó dựa vào snapshot dữ liệu nào?
2. Version thuộc bản ghi hay aggregate nào, và mọi đường ghi nào phải làm nó thay đổi?
3. Câu ghi nguyên tử kiểm tra những điều kiện nào về tenant, đối tượng, trạng thái và version?
4. Những phụ thuộc ngoài version, như quyền, hạn mức hoặc tài nguyên chung, được bảo vệ ra sao?
5. Khi cập nhật 0 dòng hoặc transaction thất bại, hệ thống rollback và phân loại kết quả như thế nào?
6. Xung đột nào cần xem lại, xung đột nào có thể tính lại, và idempotency xử lý mất phản hồi ra sao?
7. Kiểm thử nào chứng minh hai yêu cầu đồng thời không thể phá bất biến?

Optimistic version checking phát huy tác dụng khi version đại diện đúng dữ liệu quyết định, điều kiện được xác nhận ngay trong thao tác ghi và các thay đổi phụ thuộc cùng nằm trong một ranh giới nhất quán. Nó giúp hệ thống từ chối ý định đã cũ một cách có thể giải thích, thay vì để thứ tự chạy ngẫu nhiên quyết định kết quả nghiệp vụ.
