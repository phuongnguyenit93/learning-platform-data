# Ghi nhận quy tắc nghiệp vụ mà lược đồ không tự bảo đảm

> **Chương:** Lược đồ và ràng buộc  
> **Module:** DATA_PERSISTENCE_FUNDAMENTALS  
> **Bối cảnh:** Thiết kế persistence cho Java từ dữ liệu, lược đồ, truy vấn và chỉ mục tới giao dịch, cô lập, kiểm soát đồng thời, lỗi kết nối, tiến hóa schema, bảo mật, sao lưu và hiệu năng.

## 1. Vì sao “đúng schema” chưa chắc “đúng nghiệp vụ”?

Giả sử một ứng dụng bán hàng có bảng `orders` gồm `id`, `customer_id`, `status` và `total_minor`. Database có thể buộc ID không trùng, tổng tiền không âm và trạng thái thuộc một tập hữu hạn. Nhưng chỉ như vậy chưa chứng minh:

- Đơn ở trạng thái **đã giao hàng** không thể quay về **nháp**.
- Chỉ người sở hữu hoặc tác nhân được ủy quyền mới được hủy đơn.
- Đơn chỉ được nộp khi có dòng hàng, giá hợp lệ và đủ tồn kho.
- Hai người đặt sản phẩm cuối cùng không thể đều nhận xác nhận thành công.
- Webhook thanh toán bị gửi lặp không tạo hai lần ghi nhận tiền.
- Thời hạn hủy đơn được áp dụng theo đúng chính sách tại thời điểm liên quan.

Các điều kiện này là **quy tắc nghiệp vụ**. Một số có thể thể hiện bằng ràng buộc của kho lưu trữ; một số đòi hỏi thông tin nhiều bản ghi, quyền, thời gian, trạng thái lịch sử hoặc dịch vụ ngoài. Nếu không **ghi nhận thành hợp đồng rõ ràng**, mỗi API, batch job, message consumer hay script có thể tự hiểu khác nhau, tạo ra dữ liệu hợp lệ về mặt kiểu nhưng sai về ý nghĩa.

Mục tiêu bài học:

1. Phân biệt ràng buộc cấu trúc với bất biến và guard nghiệp vụ.
2. Lập **danh mục quy tắc** có định danh, chủ sở hữu, phạm vi và cách kiểm chứng.
3. Chọn nơi thực thi tại domain, application service, repository, database hoặc workflow.
4. Bảo vệ quy tắc tại thời điểm ghi khi nhiều transaction cạnh tranh.
5. Gắn quy tắc với kiểm thử, audit, vận hành và migration để không mất nghĩa qua thời gian.

## 2. Những điều lược đồ thường bảo đảm — và phần còn thiếu

| Cơ chế | Điều có thể bảo đảm | Điều không tự động được bảo đảm |
| --- | --- | --- |
| `NOT NULL` | ID người mua luôn có giá trị | Người thực hiện có quyền trên đơn của ID đó |
| `CHECK` | Số lượng dương, trạng thái thuộc tập cho phép | Chuyển trạng thái từ nguồn sang đích đúng quy trình |
| `UNIQUE` | Mã yêu cầu không trùng trong phạm vi đã định | Tác động gọi dịch vụ bên ngoài không bị lặp |
| `FOREIGN KEY` | Dòng hàng tham chiếu đơn tồn tại | Đơn có đủ dòng hàng để được nộp |
| `DEFAULT` | Giá trị mặc định nếu không truyền | Mặc định đó đúng ngữ nghĩa trong mọi tình huống |
| `INDEX` | Tăng tốc mẫu truy vấn nhất định | Người đọc có quyền hoặc dữ liệu vừa đọc đủ mới |
| Transaction | Những thay đổi trong phạm vi hỗ trợ cùng commit/rollback | Bên trong transaction đã kiểm tra mọi quy tắc nghiệp vụ |

Không nên hiểu rằng hệ quản trị hoàn toàn không thể thực thi những quy tắc phức tạp. Một số công nghệ có **trigger, stored procedure, row-level security, exclusion constraint, conditional update** hoặc transaction đa bản ghi. Nhưng khả năng, ngữ nghĩa và chi phí phụ thuộc sản phẩm/cấu hình. Vì vậy, chủ đề không phải “quy tắc nào SQL tuyệt đối không viết được” mà là **quy tắc nào schema hiện tại chưa bảo vệ, ai sở hữu và phải thực thi như thế nào**.

Đặc biệt trong PostgreSQL, `CHECK` thông thường được thiết kế cho giá trị của hàng được ghi; không nên mong nó tự truy vấn qua những hàng và bảng khác để duy trì một tổng nghiệp vụ trong mọi trường hợp đồng thời.

## 3. Phân loại quy tắc để chọn điểm thực thi

### 3.1. Ràng buộc miền giá trị

Ví dụ `quantity > 0`, `total_minor >= 0`, email không NULL. Chúng tương đối ổn định, có thể bảo vệ tại API/domain **và** bằng constraint database để ngăn mọi đường ghi tạo dữ liệu lỗi.

~~~sql
quantity INTEGER NOT NULL CHECK (quantity > 0),
total_minor BIGINT NOT NULL CHECK (total_minor >= 0)
~~~

### 3.2. Bất biến xuyên hàng hoặc nhiều aggregate

Ví dụ tổng tiền đơn phải khớp tổng các dòng hàng; tổng số ghế đã giữ không vượt sức chứa; chuyển đơn và trừ tồn kho phải cùng thành công. Những quy tắc này thường đòi hỏi **transaction boundary** và cơ chế bảo vệ các hàng cùng tham gia điều kiện.

### 3.3. Guard chuyển trạng thái

Một lệnh hợp lệ phải có trạng thái nguồn đúng và điều kiện đi kèm:

~~~text
DRAFT     + SubmitOrder     + hasLinesAndStock → SUBMITTED
SUBMITTED + ConfirmPayment  + verifiedPayment → PAID
PAID      + ShipOrder       + readyToShip     → SHIPPED
SHIPPED   + CancelDraft                        → REJECT
~~~

`PAID` có thể là giá trị hợp lệ của một cột nhưng `DRAFT → PAID` vẫn là chuyển trạng thái trái phép.

### 3.4. Quy tắc quyền truy cập

Chỉ chủ đơn được sửa nháp; nhân viên kho có thể xác nhận xuất hàng nhưng không được tự xác nhận thanh toán. Phải dùng **danh tính đã xác thực** và kiểm tra ở server, không tin trường `isAdmin` do client đưa vào.

### 3.5. Quy tắc theo thời gian, lịch sử và nguồn ngoài

Ví dụ hủy đơn trong 15 phút; chỉ dùng một mã giảm giá một lần; chấp nhận thanh toán sau khi nhà cung cấp xác minh; xử lý sự kiện đến muộn. Những điều này cần mốc thời gian tin cậy, nguồn sự thật, định danh sự kiện và chính sách đối soát.

## 4. Cách ghi nhận một quy tắc có thể triển khai

Câu “không được bán vượt tồn kho” chưa đủ để developer viết code và tester xác nhận. Một **rule card** nên có:

| Trường | Nội dung cần ghi |
| --- | --- |
| **Rule ID** | ID ổn định, ví dụ `INV-001` |
| **Tên/phát biểu** | Một câu chính xác, kiểm chứng được |
| **Owner** | Người/bộ phận xác nhận thay đổi |
| **Phạm vi** | Aggregate, bảng, tenant và luồng áp dụng |
| **Trigger** | Lệnh hoặc sự kiện kích hoạt |
| **Precondition / guard** | Những điều phải đúng trước khi ghi |
| **Postcondition / invariant** | Những điều phải đúng sau commit |
| **Nguồn dữ liệu tin cậy** | Primary database, nhà cung cấp thanh toán, policy đã duyệt |
| **Điểm thực thi** | Domain, service, repository, constraint, workflow |
| **Ranh giới nguyên tử** | Những bảng/hàng/tác động phải được bảo vệ cùng nhau |
| **Lỗi và xung đột** | Từ chối, báo conflict, retry, bù trừ, đối soát |
| **Idempotency** | Cách phân biệt request mới với request lặp |
| **Kiểm thử** | Happy path, trường hợp biên, race, rollback, lỗi mạng |
| **Phiên bản/hiệu lực** | Dữ liệu cũ và mới chịu quy tắc nào |

Không phải mọi quy tắc đều cần một tài liệu dài. Nhưng những điều kiện liên quan **tiền, quyền lợi, tồn kho hoặc cam kết pháp lý** cần đủ thông tin để giải thích và tái hiện một quyết định trong tương lai.

### 4.1. Ví dụ rule card hoàn chỉnh

**ID:** `INV-001 — Không xác nhận đơn nếu làm tồn kho âm`.

**Phát biểu:** Khi đơn chuyển `DRAFT → SUBMITTED`, tổng số lượng cần giữ của từng sản phẩm không được vượt lượng có thể phân bổ. Sau commit, `available_qty >= 0`.

**Nguồn sự thật:** tồn kho chính thức, không phải cache trên trang sản phẩm.

**Guard:** người gửi có quyền; đơn còn nháp; có ít nhất một dòng; mọi lượng đặt dương; tồn đủ ở thời điểm cập nhật.

**Thực thi:** service điều phối, repository dùng cập nhật tồn kho có điều kiện, database giữ `CHECK (available_qty >= 0)`; trạng thái đơn và tồn kho cùng transaction khi nằm trong cùng DB.

**Vi phạm:** rollback; trả lỗi hết hàng hoặc xung đột; không gửi sự kiện “đã đặt” như thể thành công.

**Đồng thời:** mọi đường đặt/giữ/hoàn tồn dùng chung giao thức kiểm soát hàng và idempotency.

**Kiểm thử:** hai request tranh một sản phẩm cuối; đơn gồm hai sản phẩm nhưng sản phẩm thứ hai hết; thử lại sau timeout.

**Ngoại lệ:** nếu có chính sách cho phép backorder, phải tạo quy tắc riêng có owner và giới hạn, không âm thầm bỏ điều kiện tồn kho.

## 5. Danh mục quy tắc mẫu theo vòng đời đơn hàng

Các ID dưới đây chỉ để minh họa cho một hệ thống học tập:

| ID | Quy tắc | Điểm bảo vệ chính | Bằng chứng kiểm thử |
| --- | --- | --- | --- |
| `ORD-001` | Chỉ chủ đơn được nộp/hủy | Authorization + query theo chủ sở hữu | Người khác không sửa được |
| `ORD-002` | Đơn nộp phải có dòng hợp lệ | Domain + khóa/transaction với dòng hàng | Nháp rỗng bị từ chối |
| `ORD-003` | Cấm `DRAFT → PAID` trực tiếp | State machine + conditional update | Chuyển trái cạnh thất bại |
| `INV-001` | Không trừ tồn xuống âm | Constraint + update có điều kiện | Hai đơn tranh hàng cuối |
| `PAY-001` | Chỉ ghi PAID khi đã xác minh nguồn thanh toán | Verification + workflow | Webhook giả bị từ chối |
| `PAY-002` | Một event thanh toán không áp dụng hai lần | Unique event ID + transaction | Webhook trùng chỉ có một tác động |
| `ORD-004` | Tổng tiền chốt theo giá và dòng hàng hợp lệ | Domain + transaction/snapshot | Sửa dòng cạnh tranh với nộp đơn |
| `ORD-005` | Đơn đã bàn giao vận chuyển không được hủy như nháp | State guard + quy trình bù trừ | Hủy SHIPPED bị từ chối |
| `AUD-001` | Thay đổi nhạy cảm có tác nhân, thời điểm và nguyên nhân | Transaction + audit | Lịch sử được ghi khi commit |

**Rule ID là cầu nối giữa yêu cầu, code, SQL, test và vận hành.** Khi đổi tên class hay chuyển từ JDBC sang JPA, ID vẫn có thể giữ nguyên để theo dõi nghĩa nghiệp vụ.

## 6. Đặt quy tắc ở tầng nào trong Java?

~~~mermaid
flowchart TD
    A["API / message / batch command"] --> B["Xác thực và validation đầu vào"]
    B --> C["Application service: quyền, workflow, transaction"]
    C --> D["Domain: state guard và bất biến"]
    D --> E["Repository: conditional write, version, khóa"]
    E --> F[("Database: NOT NULL, UNIQUE, CHECK, FK")]
    F --> G["Commit theo hợp đồng persistence"]
    G --> H["Trả kết quả / phát thông điệp từ outbox"]
~~~

**API boundary** kiểm tra định dạng, giới hạn payload và quyền đã xác thực. **Domain** phát biểu những hành động hợp lệ như `submit()` thay vì setter tùy ý. **Application service** điều phối nhiều aggregate, transaction và nguồn ngoài. **Repository/database** giữ những điều kiện quan trọng ở điểm ghi và tránh xung đột.

Kiểm tra một quy tắc ở nhiều tầng **không nhất thiết là lặp thừa**: một lần kiểm tra sớm để báo lỗi rõ, một lần bảo vệ tại nguồn sự thật khi dữ liệu có thể thay đổi đồng thời. Nhưng cần thống nhất **một phát biểu nghiệp vụ** và test đảm bảo các tầng không mâu thuẫn.

### 6.1. Domain object không chứng minh đã commit

Java 17+:

~~~java
import java.time.Instant;
import java.util.UUID;

enum OrderStatus {
    DRAFT, SUBMITTED, PAID, SHIPPED, CANCELLED
}

record OrderDraft(
        UUID id,
        UUID customerId,
        OrderStatus status,
        int itemCount,
        long totalMinor,
        long version,
        Instant submittedAt) {

    OrderDraft submit(Instant at) {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Chi don nhap moi duoc nop");
        }
        if (itemCount <= 0 || totalMinor < 0) {
            throw new IllegalArgumentException("Don khong hop le");
        }
        if (at == null) {
            throw new IllegalArgumentException("Thieu thoi diem nop");
        }
        return new OrderDraft(
                id, customerId, OrderStatus.SUBMITTED,
                itemCount, totalMinor, version + 1, at);
    }
}
~~~

Đoạn này kiểm tra **bất biến nội bộ** và tạo trạng thái **đề xuất**. Nó không kiểm tra quyền caller, không biết tồn kho và không ghi database. Trạng thái object đã đổi không có nghĩa transaction đã commit.

## 7. State machine: giá trị hợp lệ khác chuyển trạng thái hợp lệ

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> SUBMITTED: SubmitOrder
    DRAFT --> CANCELLED: CancelDraft
    SUBMITTED --> PAID: ConfirmVerifiedPayment
    SUBMITTED --> CANCELLED: CancelUnpaid
    PAID --> SHIPPED: ShipOrder
    SHIPPED --> [*]
    CANCELLED --> [*]
~~~

Schema có thể cho phép giá trị `PAID`:

~~~sql
CHECK (status IN ('DRAFT', 'SUBMITTED', 'PAID',
                 'SHIPPED', 'CANCELLED'))
~~~

nhưng chưa bảo đảm bước `DRAFT → PAID` có hợp lệ hay không. Một guard đầy đủ cho `SubmitOrder` có thể là:

~~~text
Nguồn trạng thái: DRAFT
Người thao tác: chủ đơn hoặc người được ủy quyền
Dòng hàng: tồn tại, số lượng dương, giá và currency hợp lệ
Tồn kho: đủ ở thời điểm thực sự cập nhật
Đích: SUBMITTED
Tác động: giữ/trừ tồn và ghi trạng thái cùng transaction
~~~

Với các lệnh dựa vào trạng thái đọc trước đó, repository nên kiểm tra **trạng thái nguồn và version ở thời điểm ghi**:

~~~sql
UPDATE orders
SET status = 'SUBMITTED', version = version + 1
WHERE id = :orderId
  AND customer_id = :authenticatedCustomerId
  AND status = 'DRAFT'
  AND version = :expectedVersion;
~~~

Nếu 0 hàng được cập nhật, caller không được coi là thành công; cần phân biệt không có quyền, trạng thái khác và xung đột theo chính sách tránh lộ dữ liệu. Nếu 1 hàng, thay đổi mới được áp dụng ở mức statement; nếu còn trong transaction thì phải đợi commit.

## 8. Time-of-check/time-of-use: kiểm tra đúng rồi vẫn có thể ghi sai

Tồn kho còn một sản phẩm. Hai request cùng đọc `available = 1`, sau đó cùng tính `available - 1 = 0` và đều xác nhận đã đặt. Nguy cơ này phát sinh vì **quyết định dựa trên dữ liệu cũ không được bảo vệ khi ghi**.

### 8.1. Cập nhật tồn kho có điều kiện

~~~sql
UPDATE inventory
SET available_qty = available_qty - :requestedQty
WHERE product_id = :productId
  AND available_qty >= :requestedQty;
~~~

`requestedQty > 0` phải được kiểm tra ở biên/domain. Số hàng cập nhật phải bằng 1; 0 hàng nghĩa là không có sản phẩm hoặc không đủ hàng. Cơ chế này thực thi điều kiện tại nơi ghi, thay vì đọc trước rồi ghi giá trị tuyệt đối thiếu kiểm soát.

### 8.2. Version và khóa bảo vệ những gì?

**Optimistic locking** dùng `version` hoặc điều kiện trên trạng thái nguồn để phát hiện thay đổi. **Pessimistic locking**, ví dụ `SELECT ... FOR UPDATE`, khóa những hàng cần kiểm tra trong transaction. Không kỹ thuật nào tự bảo vệ một aggregate nếu đường ghi khác tự sửa dữ liệu liên quan mà không tuân theo cùng quy ước.

Ví dụ, nếu `orders.version` không tăng khi `order_lines` thay đổi, kiểm tra riêng version ở `orders` chưa ngăn một worker xóa dòng hàng ngay lúc service kiểm tra “đơn có ít nhất một dòng”.

### 8.3. Quy định mọi đường ghi cùng tuân thủ

Rule card phải chỉ rõ:

- Ai được sửa `order_lines` và trong trạng thái nào.
- Khi sửa dòng, có phải khóa `orders` cha hoặc tăng version aggregate không?
- Khi nộp đơn, đọc và ghi phải cùng transaction hay dùng isolation nào?
- Nếu hai transaction tranh chấp, báo conflict hay retry có giới hạn?

Quy tắc được thực thi ở **một API** nhưng bị bỏ qua bởi **batch job hoặc script** chưa phải quy tắc đã được bảo vệ hoàn chỉnh.

## 9. Ví dụ schema tối thiểu để bảo vệ một quy trình

PostgreSQL minh họa:

~~~sql
CREATE TABLE orders (
    id UUID PRIMARY KEY,
    customer_id UUID NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('DRAFT', 'SUBMITTED', 'CANCELLED')
    ),
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0)
);

CREATE TABLE order_lines (
    order_id UUID NOT NULL REFERENCES orders(id),
    product_id UUID NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, product_id)
);

CREATE TABLE inventory (
    product_id UUID PRIMARY KEY,
    available_qty INTEGER NOT NULL CHECK (available_qty >= 0)
);
~~~

**Hợp đồng nghiệp vụ bổ sung**, không suy được chỉ từ DDL:

1. Mọi sửa đổi dòng hàng phải khóa hàng `orders` cha trước và chỉ được làm khi trạng thái còn `DRAFT`.
2. Mọi luồng giữ/trừ/hoàn tồn phải dùng cùng quy tắc cập nhật và chống lặp.
3. Khi nộp đơn, một transaction phải kiểm tra nháp, có dòng hàng, đủ tồn, giảm tồn và chuyển `orders.status`.
4. Nếu một bước thất bại, toàn bộ transaction rollback.
5. Khi mất kết nối sát commit, caller cần cơ chế xác minh kết quả theo định danh ổn định.

### 9.1. Ranh giới giao dịch

~~~mermaid
flowchart TD
    A["Nhận SubmitOrder"] --> B["Xác thực chủ đơn"]
    B --> C["BEGIN transaction"]
    C --> D["Khóa orders và kiểm tra DRAFT"]
    D --> E["Đọc order_lines trong cùng transaction"]
    E --> F{"Có dòng hợp lệ?"}
    F -- Không --> R["ROLLBACK"]
    F -- Có --> G["Giảm tồn có điều kiện cho từng product"]
    G --> H{"Mọi update đúng một hàng?"}
    H -- Không --> R
    H -- Có --> I["Chuyển đơn sang SUBMITTED"]
    I --> J["COMMIT"]
    J --> K["Xác nhận nếu kết quả rõ"]
~~~

Với nhiều sản phẩm, cập nhật theo thứ tự khóa thống nhất (ví dụ theo ID) giúp **giảm** xác suất deadlock; vẫn phải có cách xử lý deadlock và retry an toàn.

### 9.2. Transaction không bao gồm cuộc gọi mạng bên ngoài

Không gửi email hoặc gọi cổng thanh toán trong transaction database rồi giả định cả hai tác động cùng rollback. Nếu cần thông báo sau một thay đổi, **transactional outbox** ghi thông điệp trong cùng transaction và worker gửi sau commit. Phía nhận vẫn phải chịu được gửi trùng.

## 10. JDBC: ghi có điều kiện và không mở transaction rời rạc

Ví dụ Java 17+ dưới đây chỉ minh họa bước **giảm tồn kho** trong transaction **do caller quản lý**:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.UUID;

final class InventoryJdbc {
    static void reserve(
            Connection tx, UUID productId, int requestedQty)
            throws SQLException {
        if (requestedQty <= 0) {
            throw new IllegalArgumentException("So luong phai duong");
        }
        String sql = """
                UPDATE inventory
                SET available_qty = available_qty - ?
                WHERE product_id = ?
                  AND available_qty >= ?
                """;
        try (PreparedStatement statement = tx.prepareStatement(sql)) {
            statement.setInt(1, requestedQty);
            statement.setObject(2, productId);
            statement.setInt(3, requestedQty);
            if (statement.executeUpdate() != 1) {
                throw new IllegalStateException(
                        "Khong ton tai san pham hoac khong du ton");
            }
        }
    }
}
~~~

Hợp đồng `reserve()` không tự commit, vì nó phải tham gia transaction cùng việc chuyển trạng thái đơn. Nếu mỗi repository tự mở `DataSource.getConnection()` rồi autocommit, các thay đổi không còn nguyên tử với nhau.

Một trình tự đơn giản phía application service (mã giả):

~~~text
connection.setAutoCommit(false)
try:
    khóa đơn cha, xác minh chủ đơn/trạng thái
    đọc các dòng hàng theo quy ước khóa
    nếu đơn rỗng: từ chối
    với từng dòng theo thứ tự product ID:
        InventoryJdbc.reserve(connection, productId, qty)
    cập nhật orders WHERE status=DRAFT AND version=expected
    nếu rowCount != 1: từ chối
    connection.commit()
catch lỗi:
    cố gắng rollback; phân loại kết quả commit nếu chưa rõ
    thông báo/đối soát theo hợp đồng
finally:
    đóng connection
~~~

Đây là **mã giả**, không phải Java biên dịch trực tiếp. Tính đúng đắn của quy trình còn phụ thuộc mọi đường sửa dòng hàng tuân theo khóa đơn cha, đồng bộ trong cùng database, mức cô lập và quy tắc transaction đã định.

**Quan trọng:** `commit()` ném ngoại lệ do mất mạng không chứng minh giao dịch chưa từng commit; rollback sau ngoại lệ cũng không xóa được một commit đã hoàn tất trên server. Với lệnh tạo mới hay thanh toán, cần idempotency key và khả năng truy vấn lại.

## 11. Bất biến nhiều bảng: tổng đơn và snapshot giá

Quy tắc “tổng đơn phải khớp các dòng hàng” có thể viết:

~~~text
order.total_minor =
    SUM(line.quantity × line.unit_price_minor)
    theo chính sách thuế/chiết khấu đã chốt
~~~

Đây là bất biến **xuyên nhiều dòng**, lại phụ thuộc vào chính sách giá và thời điểm chốt. Những cách hiện thực:

| Cách | Lợi ích | Rủi ro hoặc điều kiện |
| --- | --- | --- |
| Không lưu tổng, tính từ dòng khi đọc | Tránh lệch dữ liệu dẫn xuất | Có chi phí đọc/tổng hợp |
| Lưu tổng snapshot và cập nhật trong transaction | Đọc nhanh, dễ đối soát | Mọi sửa dòng phải dùng chung giao thức |
| Trigger/procedure ở DB | Giảm nguy cơ đường ghi bỏ sót | Phụ thuộc vendor, cần kiểm thử và tài liệu |
| Tổng hợp bất đồng bộ phục vụ báo cáo | Giảm tải lên OLTP | Kết quả dẫn xuất có độ trễ |

Nếu giá sản phẩm hôm nay đã thay đổi, **không tự tính lại** tổng của đơn lịch sử bằng giá mới. Rule cần ghi rõ nguồn giá và phiên bản chính sách thuế/chiết khấu, điểm làm tròn và dữ liệu cần lưu để đối soát.

Không nên thêm một `CHECK` giả định có thể tự quét mọi hàng con. Hãy chọn cơ chế được DB hỗ trợ thật và kiểm chứng trong các tình huống cạnh tranh.

## 12. Quy tắc theo thời gian và sự kiện đến muộn

Yêu cầu “tự hủy đơn sau 15 phút nếu chưa thanh toán” cần được đặc tả sâu hơn:

- Tính từ lúc tạo nháp, lúc nộp đơn hay lúc bắt đầu thanh toán?
- Thời điểm nào là nguồn tin cậy: đồng hồ client, server, database hay timestamp từ nhà cung cấp?
- Nếu payment đã thành công ở nhà cung cấp trước hạn nhưng webhook đến sau hạn, xử lý thế nào?
- Nếu job chạy trễ hoặc chạy lại nhiều lần, có hoàn tồn kho hai lần không?
- Chính sách mới áp dụng cho đơn cũ hay chỉ đơn tạo từ một thời điểm nhất định?

Một ví dụ ghi nhận:

~~~text
Rule ID: ORD-EXP-001
Trigger: Job kiểm tra đơn chờ thanh toán
Precondition: status = SUBMITTED, chưa có thanh toán hợp lệ
Mốc thời gian: submitted_at do hệ thống ghi nhận
Thời hạn: 15 phút theo policy_version gắn với đơn
Postcondition: đơn được hủy hợp lệ, hoàn giữ tồn tối đa một lần
Concurrency: cập nhật theo status/version trong transaction
Late event: chuyển sang đối soát/hoàn tiền
Retry: idempotent theo order ID và loại hành động
~~~

### 12.1. Job không được ghi trạng thái bằng một câu UPDATE thiếu guard

Ví dụ sơ lược:

~~~sql
UPDATE orders
SET status = 'CANCELLED',
    version = version + 1
WHERE id = :orderId
  AND status = 'SUBMITTED'
  AND version = :expectedVersion;
~~~

Lệnh này chỉ bảo vệ **trạng thái và version**, chưa xác minh trạng thái thanh toán ở dịch vụ ngoài hoặc các điều kiện đã được chủ sở hữu nghiệp vụ phê duyệt. Việc hủy còn có thể cần hoàn tồn kho và ghi lịch sử trong cùng transaction; nếu không thể cập nhật nguyên tử qua các dịch vụ, phải dùng workflow đối soát.

### 12.2. Đồng hồ và múi giờ là một phần của quy tắc

Nên lưu thời điểm có nghĩa nghiệp vụ theo một quy ước rõ, thường là instant/UTC khi thích hợp. Phân biệt “15 phút kể từ khi nộp” với “hết ngày địa phương của cửa hàng”. Với quy tắc phụ thuộc deadline, không tin timestamp do client tự cung cấp như bằng chứng duy nhất.

## 13. Quy tắc liên quan tới dịch vụ bên ngoài

Khi cổng thanh toán gửi sự kiện `payment_succeeded`, database ứng dụng có thể kiểm tra mã sự kiện duy nhất nhưng **không tự xác nhận** nguồn gửi có thực sự đáng tin và số tiền có đúng đơn không.

Hồ sơ `PAY-001` nên yêu cầu:

1. Xác thực webhook/chữ ký theo hợp đồng nhà cung cấp hoặc tra cứu kết quả từ kênh tin cậy.
2. Đối chiếu `paymentId`, `orderId`, amount, currency và trạng thái dự kiến.
3. Từ chối hoặc cách ly sự kiện không hợp lệ.
4. Áp dụng sự kiện đúng một lần theo mã định danh ổn định.
5. Chỉ chuyển `SUBMITTED → PAID` nếu state guard còn thỏa.
6. Nếu đơn đã hủy hoặc event đến muộn, kích hoạt quy trình đối soát/bù trừ được phê duyệt.

### 13.1. Idempotency không tự xuất hiện vì có transaction

Một bảng phụ trợ có thể chứa:

~~~sql
CREATE TABLE processed_payment_events (
    provider_event_id TEXT PRIMARY KEY,
    order_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL
);
~~~

Để có **tác động tối đa một lần**, việc ghi nhận `provider_event_id` và thay đổi trạng thái đơn phải nằm trong **cùng transaction**, hoặc được bảo vệ bằng một giao thức khác có cam kết tương đương. Chỉ insert một event ID rồi gọi hệ thống khác bên ngoài transaction có thể để lại tác động một phần.

Khóa sự kiện cũng phải đến từ nguồn đã xác thực. Một client không đáng tin gửi mã `event_id` ngẫu nhiên không phải bằng chứng thanh toán.

### 13.2. Transactional outbox và workflow bù trừ

Một transaction có thể ghi:

~~~text
BEGIN
  kiểm tra trạng thái đơn và payment event đã xác thực
  ghi sự kiện đã xử lý và cập nhật đơn
  ghi outbox message cho hệ thống sau
COMMIT
~~~

Worker phát message từ outbox sau commit. Consumer cần xử lý lặp an toàn vì một message có thể được gửi nhiều lần. Transaction database thông thường **không** làm cho cuộc gọi tới cổng thanh toán hay dịch vụ vận chuyển trở thành nguyên tử với commit nội bộ.

Với nhiều dịch vụ, có thể dùng saga/workflow có các bước bù trừ. Bù trừ là **thao tác nghiệp vụ mới**, không phải một phép rollback SQL thần kỳ xuyên các hệ thống.

## 14. Phân quyền phải được ghi như một quy tắc có thể kiểm thử

Không hiển thị nút “Hủy đơn” trên giao diện **không đồng nghĩa** người dùng không thể gọi trực tiếp API.

Quy tắc `ORD-001` phải chỉ rõ:

- Người gọi được xác thực thế nào?
- Chỉ chủ đơn, chủ tenant hoặc nhân viên được ủy quyền mới có quyền?
- Quyền có thay đổi theo trạng thái đơn không?
- Trường nào được sửa và trường nào chỉ được đọc?
- Các đường export, job nền, support tool và script có được kiểm soát không?

Một lớp bảo vệ ở repository:

~~~sql
UPDATE orders
SET status = 'CANCELLED',
    version = version + 1
WHERE id = :orderId
  AND customer_id = :authenticatedCustomerId
  AND status = 'DRAFT'
  AND version = :expectedVersion;
~~~

`:authenticatedCustomerId` phải đến từ ngữ cảnh định danh đáng tin cậy, không phải trường người dùng có thể tự sửa. Database cũng có thể sử dụng phân quyền tối thiểu và row-level security nếu hệ quản trị hỗ trợ và phạm vi đã được kiểm chứng.

### 14.1. Không dùng API cập nhật tùy ý mọi field

API `PATCH /orders/{id}` nhận nguyên JSON với `status`, `ownerId`, `totalMinor` và `paidAt` có thể dẫn tới **mass assignment**. Thay vào đó nên cung cấp lệnh chuyên biệt như `UpdateDraftOrder`, `CancelOrder` hoặc `ConfirmPayment`, mỗi lệnh có tập trường và guard rõ ràng.

Khi không có quyền, cần cân nhắc phản hồi để không làm lộ đơn hàng của người khác. Việc `UPDATE` trả 0 hàng có nhiều nguyên nhân; không tự suy rằng đơn không tồn tại.

## 15. Audit: chứng minh vì sao một thay đổi được cho phép

Cột `status = PAID` chỉ cho biết **hiện trạng**. Để biết **ai, khi nào, theo quy tắc nào** đã ghi nhận thanh toán, hệ thống có thể cần lịch sử:

~~~sql
CREATE TABLE order_transition_history (
    event_id UUID PRIMARY KEY,
    order_id UUID NOT NULL,
    rule_id TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    request_id TEXT,
    reason TEXT,
    occurred_at TIMESTAMPTZ NOT NULL
);
~~~

Với transition quan trọng, ghi lịch sử **trong cùng transaction** với cập nhật trạng thái để tránh trường hợp trạng thái đổi mà audit không có. Tùy nghiệp vụ có thể cần lưu định danh chứng từ, chính sách tính giá, tỷ giá hoặc quyết định phê duyệt.

### 15.1. Phân biệt audit trail, event và event sourcing

- **Audit trail:** hỗ trợ kiểm toán, tìm nguyên nhân và truy vết tác nhân.
- **Domain event:** mô tả một việc nghiệp vụ đã xảy ra để hệ khác tiêu thụ.
- **Event sourcing:** dùng các sự kiện như nguồn sự thật và dựng lại trạng thái từ chuỗi sự kiện.

Thêm một bảng lịch sử **không tự động biến hệ thống thành event-sourced system**. Nếu dùng event sourcing, còn phải quản lý thứ tự, phiên bản sự kiện, replay, idempotency và tiến hóa schema sự kiện.

### 15.2. Audit phải bảo vệ dữ liệu nhạy cảm

Không ghi nguyên văn mật khẩu, token, thông tin thẻ hoặc toàn bộ request chỉ để điều tra. Ghi metadata tối thiểu có ích như `rule_id`, `request_id` và người thực hiện, cùng chính sách phân quyền, mã hóa và retention.

## 16. Liên kết một quy tắc từ yêu cầu tới code, SQL và test

Một quy tắc chỉ nằm trong wiki rất dễ bị quên khi code đổi. Nên duy trì khả năng truy ngược:

~~~text
Yêu cầu nghiệp vụ
    ↓
Rule ID / owner / version
    ↓
Domain method và application service
    ↓
Repository / SQL / transaction / constraint
    ↓
Unit test + integration test + concurrency test
    ↓
Metric + audit + runbook xử lý sự cố
~~~

| Rule ID | Nơi kiểm tra logic | Nơi bảo vệ dữ liệu | Test |
| --- | --- | --- | --- |
| `ORD-002` | `Order.submit()` | Khóa đơn và kiểm tra dòng trong transaction | Nháp rỗng không nộp được |
| `INV-001` | `SubmitOrderService` | Conditional update tồn kho | Hai đơn tranh một sản phẩm |
| `PAY-002` | `PaymentEventHandler` | Unique event ID cùng transaction | Webhook lặp chỉ có một tác động |
| `ORD-003` | State machine | `UPDATE ... WHERE status=? AND version=?` | Chuyển trái cạnh bị từ chối |
| `ORD-001` | Authorization policy | Query theo chủ sở hữu + quyền DB | Khách khác không sửa được |

Tên hàm ở bảng chỉ minh họa. Điều quan trọng là giữ **Rule ID ổn định** qua các lần refactor và có test bảo vệ ý nghĩa của nó.

## 17. Kiểm thử quy tắc: đường thành công là chưa đủ

Unit test của `OrderDraft.submit()` chứng minh guard nội tại hoạt động, nhưng **không chứng minh** database chặn được hai request tranh tồn kho hay một giao dịch rollback hoàn toàn.

### 17.1. Ma trận kiểm thử

| Tình huống | Điều cần chứng minh |
| --- | --- |
| Số lượng 0/âm hoặc lớn bất thường | Validation và constraint từ chối đúng |
| Đơn nháp không có dòng | Không thể nộp |
| Người dùng khác gửi lệnh | Không có thay đổi hoặc lộ dữ liệu trái quyền |
| Hai request cùng version | Không ghi đè âm thầm |
| Hai đơn tranh sản phẩm cuối | Chỉ một request có thể giữ/trừ thành công |
| Đơn có hai sản phẩm, sản phẩm sau hết hàng | Rollback toàn bộ, không giữ một phần |
| Hai webhook cùng event ID | Thanh toán được ghi tối đa một lần |
| Timeout gần commit | Không tự tạo đơn/thanh toán mới khi chưa biết kết quả |
| Thanh toán thành công sau khi hủy | Chạy chính sách đối soát |
| Job tự hủy chạy lại | Không hoàn tồn hai lần |
| Reader mới đọc dữ liệu cũ | Áp dụng đúng phiên bản quy tắc |

### 17.2. Ví dụ unit test với JUnit 5

Giả sử dùng record `OrderDraft` ở mục 6:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class OrderDraftTest {
    @Test
    void cannotSubmitEmptyDraft() {
        OrderDraft draft = new OrderDraft(
                UUID.randomUUID(),
                UUID.randomUUID(),
                OrderStatus.DRAFT,
                0, 0, 1, null);

        assertThrows(
                IllegalArgumentException.class,
                () -> draft.submit(
                        Instant.parse("2026-01-01T00:00:00Z")));
    }
}
~~~

Test này chỉ kiểm tra domain guard, **không thay thế integration test** trên database thật.

### 17.3. Concurrency test đúng cách

Thiết lập một sản phẩm còn đúng một đơn vị. Bắt đầu hai giao dịch độc lập gần đồng thời, mỗi giao dịch muốn giữ một đơn vị cho đơn khác nhau. Sau khi cả hai hoàn tất, xác minh:

1. Chỉ một đơn được xác nhận theo chính sách.
2. Tồn kho không âm.
3. Không có đơn xác nhận nhưng thiếu thao tác giữ/trừ tương ứng.
4. Transaction thất bại không để lại ghi một phần.

Test nên chạy lại nhiều lần, có thể dùng cơ chế đồng bộ điểm bắt đầu và kiểm tra dữ liệu **sau khi commit**, không dựa vào kết quả log của một lần chạy tuần tự.

## 18. Tiến hóa quy tắc khi dữ liệu lịch sử còn tồn tại

Ví dụ thời hạn hủy tăng từ 15 lên 30 phút. Chỉ đổi hằng số trong Java chưa trả lời:

- Đơn tạo trước ngày đổi chính sách có được dùng hạn 30 phút?
- Các job hủy đã lên lịch theo hạn 15 phút sẽ làm gì?
- Khi kiểm toán đơn đã bị hủy, làm sao biết quy tắc lúc ấy là 15 phút?
- Hai phiên bản ứng dụng chạy song song có ra cùng quyết định?

Một cách làm có kiểm soát:

1. Cập nhật rule card, xác nhận owner và thời điểm hiệu lực.
2. Xác định quy tắc cho dữ liệu trước/sau thay đổi.
3. Lưu `expires_at` hoặc `policy_version` nếu cần giữ chính sách tại thời điểm tạo.
4. Thay đổi domain, job, các đường đọc/ghi, audit và test cùng nhau.
5. Lập migration/backfill chỉ khi có nguồn dữ liệu đáng tin.
6. Triển khai tương thích trong thời gian rolling deployment.
7. Giám sát các tình huống trái quy tắc sau khi phát hành.

### 18.1. Thêm constraint mới cần làm sạch dữ liệu trước

Nếu muốn quy định mã giảm giá là duy nhất theo khách, nhưng dữ liệu hiện tại đã có hai hàng trùng, thêm `UNIQUE(customer_id, coupon_code)` có thể thất bại. Cần tìm collision, quyết định cách xử lý nghiệp vụ, chạy migration thử và kiểm chứng trên tập dữ liệu đại diện.

Trong hệ thống lớn, còn phải tính tác động của khóa bảng, xây dựng index và tương thích các writer cũ. **Thay schema là thay hợp đồng**, không chỉ thay cú pháp SQL.

## 19. Kiểm toán dữ liệu và phục hồi sau sự cố

Backup có thể giữ nguyên byte nhưng thiếu ngữ nghĩa nếu không lưu được những thông tin cần diễn giải: bảng giá ở thời điểm giao dịch, tỷ giá, chính sách thuế, trạng thái và phiên bản quy tắc.

Khi diễn tập restore, ngoài xác minh số hàng và schema, có thể thực hiện các phép kiểm invariant:

~~~text
Không có inventory.available_qty âm
Không có đơn SUBMITTED thiếu dòng hàng theo chính sách áp dụng
Không có provider_event_id trùng trong tập đã xử lý
Không có quan hệ tham chiếu mồ côi
Số tiền đã đối soát khớp snapshot và rounding policy
~~~

Một số kiểm tra cần xét **phiên bản chính sách của dữ liệu cũ**, không phải cứ chạy quy tắc hiện hành rồi tự sửa tất cả bản ghi bị báo bất thường.

Replication không thay thế backup: một lỗi logic hoặc xóa nhầm có thể lan sang các bản sao. Thử restore cũng cần xác minh RPO/RTO và khả năng ứng dụng Java đọc đúng dữ liệu đã khôi phục.

## 20. Giám sát và xử lý khi phát hiện vi phạm

| Chỉ số hoặc sự kiện | Giá trị |
| --- | --- |
| Số lần từ chối theo `rule_id` | Phát hiện tăng lỗi input hoặc đổi hành vi |
| Optimistic-lock conflict | Đánh giá cạnh tranh và khả năng cần cải thiện workflow |
| Deadlock/serialization retry | Điều tra transaction giữ khóa hoặc thứ tự khóa |
| Event trùng bị bỏ qua | Theo dõi replay và idempotency |
| Commit không rõ kết quả | Theo dõi lỗi kết nối và nhu cầu đối soát |
| Record sai bất biến khi audit | Phát hiện đường ghi bỏ qua hợp đồng |
| Thời gian workflow bù trừ | Giám sát nghĩa vụ chưa hoàn tất |

Khi thấy dữ liệu sai, nên **chặn vi phạm mới**, khoanh vùng và kiểm tra nguồn sự thật, sửa theo một kế hoạch có audit rồi bổ sung regression test. Không nên tự động ghi đè dữ liệu tài chính hoặc lịch sử mà chưa xác minh ngữ nghĩa.

Log cần chứa thông tin hỗ trợ truy vết như `rule_id`, `request_id`, mã lỗi và thông tin trạng thái cho phép ghi; tránh đưa thông tin cá nhân hoặc bí mật thô vào log.

## 21. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| “Có CHECK là đủ” | Bỏ sót chuyển trạng thái, quyền, dữ liệu nhiều hàng | Tách rule card và bảo vệ theo phạm vi |
| Quy tắc chỉ nằm trong bình luận | Các service tự hiểu khác nhau | ID, owner, source, version, test |
| Kiểm tra trong RAM rồi ghi không khóa | Race, oversell, lost update | Conditional update, transaction, version/lock |
| Kiểm tra chỉ ở controller | Script và job có thể bypass | Bảo vệ ở domain/repository/DB phù hợp |
| Đưa toàn bộ logic vào trigger không tài liệu | Phụ thuộc vendor, khó gỡ lỗi | Ghi rõ contract và test DB logic |
| Dùng cache làm nguồn quyết định tồn cuối | Dữ liệu cũ làm sai | Kiểm tra tại nguồn sự thật khi ghi |
| Webhook tới là chuyển PAID ngay | Event giả/lặp/đến muộn | Xác thực nguồn, state guard, idempotency |
| Retry sau timeout bằng ID mới | Tác động trùng | Khóa idempotency, tra cứu kết quả |
| Đổi chính sách nhưng không version | Không giải thích được quyết định cũ | Policy version/effective time và migration |
| Chỉ test happy path | Không thấy race hoặc rollback một phần | Integration/concurrency/failure tests |

## 22. Bài tập vận dụng

### Bài tập 1: Phân loại quy tắc

Hãy phân loại năm yêu cầu: giá sản phẩm không âm; cấm `DELIVERED → DRAFT`; mã thanh toán chỉ xử lý một lần; chỉ chủ tài khoản đọc lịch sử; tổng đơn bằng tổng dòng sau thuế. Với mỗi yêu cầu, chỉ rõ phần nào có thể bảo vệ bằng `CHECK`, `UNIQUE`, FK và phần nào cần service/domain/transaction.

**Gợi ý:** Giá không âm phù hợp `CHECK`; chuyển trạng thái cần guard và cập nhật có điều kiện; thanh toán trùng cần unique ID cùng transaction; truy cập cần authorization; tổng đơn cần quy tắc tính và bảo vệ đồng thời nhiều hàng.

### Bài tập 2: Viết rule card

Soạn `ORD-002` — “chỉ nộp đơn có ít nhất một dòng hàng”. Ghi rõ owner, trigger, nguồn sự thật, precondition, postcondition, transaction boundary, xung đột và test. Vì sao chỉ đọc `COUNT(*) > 0` rồi cập nhật đơn là chưa đủ nếu một job khác có thể xóa dòng cùng lúc?

### Bài tập 3: Cạnh tranh tồn kho

Tồn kho còn 1. Hai request đặt một món cùng lúc. Đề xuất câu SQL cập nhật có điều kiện, cách kiểm tra row count và điều kiện commit. Nếu đơn có hai sản phẩm nhưng sản phẩm thứ hai hết hàng, làm sao tránh giữ sản phẩm đầu tiên?

**Gợi ý:** Mọi thao tác trừ tồn và cập nhật đơn nằm trong một transaction; lỗi ở bất kỳ bước nào phải rollback.

### Bài tập 4: Thanh toán đến muộn

Một job vừa hủy đơn quá hạn, nhưng webhook đến muộn xác nhận tiền đã được thu. Hãy mô tả Rule ID về thời hạn, xác minh nguồn, idempotency, đối soát và hoàn tiền; không tự ép `CANCELLED → PAID`.

### Bài tập 5: Đổi hạn hủy đơn

Quy tắc tăng từ 15 phút lên 30 phút. Bạn sẽ áp dụng cho đơn cũ hay đơn mới? Cần lưu `expires_at`, `policy_version` và thay đổi job/test/migration ra sao để vẫn giải thích được quyết định trong lịch sử?

## 23. Checklist bàn giao quy tắc nghiệp vụ ngoài schema

- [ ] Có Rule ID, phát biểu chính xác, owner, phạm vi và phiên bản/hiệu lực.
- [ ] Phân loại rõ bất biến một hàng, nhiều hàng, trạng thái, quyền, thời gian và nguồn ngoài.
- [ ] Biết nguồn sự thật; không dùng client input hoặc cache cũ để ra quyết định cuối cùng.
- [ ] Ghi guard, invariant sau commit, hành vi từ chối và phương án xử lý lỗi.
- [ ] Chỉ rõ điều nào được constraint DB bảo vệ, điều nào cần domain/service/workflow.
- [ ] Có transaction boundary, isolation/lock/version/conditional update phù hợp.
- [ ] Mọi đường ghi liên quan cùng tuân thủ một giao thức bảo vệ bất biến.
- [ ] Có idempotency, retry và xử lý kết quả commit không rõ.
- [ ] Có phương án sự kiện đến muộn, timeout và bù trừ khi liên quan dịch vụ ngoài.
- [ ] Audit/metric gắn rule nhưng không làm lộ dữ liệu nhạy cảm.
- [ ] Test domain, tích hợp, cạnh tranh, rollback, lỗi mạng và phục hồi.
- [ ] Migration và policy version giữ đúng ngữ nghĩa cho dữ liệu lịch sử.

## 24. Tổng kết

**Schema là lớp bảo vệ quan trọng, nhưng không phải bản đặc tả đầy đủ mọi quyết định nghiệp vụ.** Kiểu dữ liệu, khóa và constraint bảo vệ điều kiện mà hệ quản trị có thể kiểm tra trực tiếp; còn trạng thái, quyền, lịch sử, thời gian, bất biến nhiều bản ghi và nguồn ngoài phải được **ghi nhận thành quy tắc có chủ sở hữu, điều kiện và bằng chứng kiểm thử**.

Trong ứng dụng Java, domain mô tả các hành vi được phép; service điều phối quyền và workflow; repository/database bảo vệ điều kiện tại điểm ghi. Transaction, optimistic/pessimistic locking, idempotency, audit và restore giữ quy tắc đúng qua cạnh tranh và sự cố. Một quy tắc quan trọng nên có chuỗi liên kết **Rule ID → thực thi → test → giám sát → phiên bản thay đổi**. Nhờ vậy, hệ thống không chỉ lưu dữ liệu bền vững mà còn **duy trì đúng ý nghĩa nghiệp vụ** trong suốt vòng đời dữ liệu.
