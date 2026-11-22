# Thiết kế thao tác lũy đẳng trước khi tự động thử lại

Một yêu cầu tạo đơn hàng có thể đã **commit thành công** trong cơ sở dữ liệu nhưng ứng dụng hoặc người gọi vẫn thấy **timeout** vì phản hồi bị mất. Nếu hệ thống tự động gọi lại thao tác mà không có cơ chế nhận diện yêu cầu đã xử lý, nó có thể tạo hai đơn hàng và trừ tồn kho hai lần. Đây là lý do cần **thiết kế tính lũy đẳng (idempotency) trước khi bật tự động thử lại (retry)**.

Bài thuộc chương **Lỗi và thử lại** trong module **DATA_PERSISTENCE_FUNDAMENTALS**. Module hướng đến xây dựng nền tảng lưu trữ bền vững trong ứng dụng Java: thiết kế lược đồ, truy vấn, chỉ mục, giao dịch, mức cô lập, kiểm soát đồng thời, lỗi kết nối, bảo mật và tối ưu hiệu năng. Bài này tập trung vào **hợp đồng nghiệp vụ, ranh giới transaction và xử lý kết quả không chắc chắn**; ví dụ dùng PostgreSQL, JDBC và Spring. Khi dùng hệ quản trị hoặc message broker khác, cần xác minh lại cơ chế khóa, upsert, commit và xử lý trùng lặp.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích vì sao **timeout không chứng minh thao tác thất bại**, nhất là lúc nhận kết quả COMMIT.
- Phân biệt thao tác lũy đẳng tự nhiên với thao tác cần **idempotency key** và lưu kết quả đã xử lý.
- Thiết kế **phạm vi định danh yêu cầu, kiểm tra payload, ràng buộc duy nhất và transaction boundary** để tránh tác động trùng lặp.
- Xử lý hai request cùng khóa đến đồng thời, request được gửi lại sau lỗi mạng, và yêu cầu có cùng khóa nhưng nội dung khác nhau.
- Kết hợp idempotency với **retry có điều kiện, exponential backoff, jitter, deadline** và giới hạn số lần thử.
- Nhận diện ranh giới bảo đảm của một cơ sở dữ liệu và các bước tích hợp cần **outbox/inbox, deduplication hoặc đối soát**.

## 2. Retry tạo ra rủi ro ở đâu?

Giả sử client gửi thao tác đặt mua một sản phẩm. Service trừ tồn kho, tạo đơn hàng và commit:

~~~text
Client                    API Java                      Database
   | POST /orders             |                              |
   |------------------------->| BEGIN                        |
   |                          | UPDATE inventory             |
   |                          | INSERT orders                |
   |                          | COMMIT --------------------->|
   |                          |                    commit thành công
   |          mất phản hồi    X<-----------------------------|
   |<------ timeout ----------|                              |
   |                          |                              |
   | POST /orders lần nữa     |                              |
   |------------------------->| ? Tạo thêm đơn hay trả đơn cũ?|
~~~

Từ phía client, cùng một biểu hiện **timeout** có thể tương ứng với nhiều trạng thái:

1. Yêu cầu chưa đến server, chưa có tác động.
2. Server đã bắt đầu nhưng transaction bị rollback.
3. Server đã commit, phản hồi kết quả bị mất.
4. Server còn đang xử lý, trong khi client đã hết thời gian chờ.

Một bộ retry không thể tự phân biệt chính xác các trạng thái đó chỉ từ ngoại lệ mạng. **Retry an toàn phải dựa vào thiết kế nghiệp vụ phía server**, vì server và database mới có thông tin cần thiết để nhận biết thao tác đã hoàn tất.

## 3. Lũy đẳng là gì?

Một thao tác **lũy đẳng** có tính chất: thực hiện lặp lại cùng thao tác lên cùng trạng thái mục tiêu không tạo ra tác động bổ sung ngoài lần thực hiện có hiệu lực đầu tiên.

Có thể viết ngắn gọn:

~~~text
f(f(state)) = f(state)
~~~

Ví dụ:

| Thao tác | Có tự nhiên lũy đẳng không? | Lý do |
| --- | --- | --- |
| Đặt **status = 'CLOSED'** | Thường có, xét giá trị status cuối | Gọi nhiều lần vẫn đặt cùng một giá trị |
| Gán **profile.name = 'An'** | Thường có, xét giá trị trường name | Lặp lại phép gán không cộng thêm gì |
| **DELETE** một tài nguyên | Thường lũy đẳng về trạng thái cuối | Xóa lần nữa không tạo thêm trạng thái “đã xóa hơn” |
| **balance = balance - 100** | Không | Lặp lại sẽ trừ tiếp 100 |
| **counter = counter + 1** | Không | Mỗi lần gọi cộng một đơn vị |
| **INSERT orders** không kiểm soát trùng | Không | Có thể tạo thêm một đơn mỗi lần |
| Gửi email | Không có bảo đảm tự nhiên | Gửi lại thường tạo thêm email |

**Lũy đẳng về trạng thái không đồng nghĩa mọi phản hồi đều giống hệt nhau.** Ví dụ một DELETE có thể trả 204 ở lần đầu và 404 ở lần sau mà trạng thái tài nguyên cuối vẫn giống nhau. Một hệ API muốn trả cùng kết quả cho cùng yêu cầu cần một hợp đồng **response replay** riêng.

**PUT hoặc DELETE theo HTTP** thường được định nghĩa có tính lũy đẳng về tác động dự định, nhưng cách cài đặt có thể tạo tác dụng phụ như tăng counter, gửi email hoặc sinh lịch sử mỗi lần. Tên HTTP method không tự làm logic nghiệp vụ an toàn để retry.

## 4. Thao tác nguyên tử không đồng nghĩa lũy đẳng

Câu SQL sau là một cách tăng bộ đếm nguyên tử trên một hàng:

~~~sql
UPDATE counters
SET value = value + 1
WHERE id = 10;
~~~

Hai request đồng thời chạy câu lệnh này có thể tăng đúng hai lần, không bị mất cập nhật. Nhưng nếu **chỉ một sự kiện nghiệp vụ** bị gửi lại do timeout, câu UPDATE có thể tăng hai lần dù mỗi lần đều nguyên tử.

Phân biệt:

| Thuộc tính | Câu hỏi nó trả lời |
| --- | --- |
| **Atomicity** | Các bước thuộc một giao dịch có commit/rollback cùng nhau không? |
| **Isolation** | Những transaction đồng thời ảnh hưởng và nhìn thấy nhau thế nào? |
| **Durability** | Một commit được xác nhận được giữ lại theo cam kết gì? |
| **Idempotency** | Cùng một yêu cầu được nhận lại có tạo thêm tác động nghiệp vụ không? |

Trong hệ thống đáng tin cậy, các thuộc tính này **phối hợp**. Dùng transaction để bảo vệ nhiều thay đổi, unique constraint để nhận diện trùng, và idempotency key để đối chiếu giữa các lần gửi lại.

## 5. Xác định chính xác “cùng một yêu cầu”

Idempotency không chỉ là tạo một UUID ngẫu nhiên. Trước khi viết mã, hãy xác định **danh tính logic** của một thao tác.

Một hợp đồng API tạo đơn thường có:

~~~text
POST /orders
Idempotency-Key: 52d48a8c-08f0-4e63-9da2-f706b150a9db
Tenant: tenant-10 (xác định từ danh tính đã xác thực)

Payload:
{
  "productId": 1001,
  "quantity": 2
}
~~~

Khi client retry do lỗi tạm thời, nó phải **gửi lại đúng idempotency key của thao tác cũ**. Nếu người dùng chủ động tạo một đơn hàng khác, dù mua cùng sản phẩm và số lượng, yêu cầu mới phải có **key mới**.

### 5.1. Phạm vi định danh

Thông thường, khóa nên duy nhất trong một phạm vi nghiệp vụ rõ ràng, ví dụ:

~~~text
(tenant_id, request_id)
~~~

Nếu cùng key được dùng cho nhiều loại thao tác, có thể cần đưa **operation_type/endpoint hoặc phiên bản API** vào phạm vi định danh. Ngược lại, chỉ dựa vào request ID toàn cục mà không xét tenant và quyền truy cập có thể gây xung đột hoặc rò rỉ thông tin giữa người dùng.

**Tenant phải lấy từ danh tính đã xác thực/ủy quyền ở server**, không được tin một header tenant do client tự khai báo. Khi đọc lại kết quả cũ, server vẫn phải kiểm tra người gọi có quyền xem và thực hiện thao tác tương ứng.

### 5.2. Cùng key nhưng payload khác

Nếu request ID đã được dùng cho **product_id = 1001, quantity = 2**, một yêu cầu lặp lại cùng key với **quantity = 5** không phải retry hợp lệ. Server phải **báo xung đột hoặc từ chối**, không:

- Tự thực hiện thêm giao dịch mới.
- Trả kết quả đơn hàng cũ như thể payload mới đã được xử lý.
- Ghi đè payload của idempotency record.

Có thể lưu các trường nghiệp vụ đã chuẩn hóa hoặc một **payload fingerprint** được tính từ dạng canonical ổn định. Nếu dùng fingerprint, cần thống nhất cách chuẩn hóa số, đơn vị tiền, Unicode, giá trị mặc định, thứ tự trường và phiên bản hợp đồng. Fingerprint/hash không thay thế xác thực, ủy quyền hoặc ràng buộc nghiệp vụ; tránh lưu dữ liệu nhạy cảm không cần thiết.

## 6. Mô hình dữ liệu cơ bản trong PostgreSQL

Giả sử nghiệp vụ tạo đơn và trừ tồn kho. Ví dụ tối giản có ba bảng:

~~~sql
CREATE TABLE inventory (
    tenant_id  BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    available  BIGINT NOT NULL CHECK (available >= 0),
    PRIMARY KEY (tenant_id, product_id)
);

CREATE TABLE orders (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id  BIGINT NOT NULL,
    request_id UUID NOT NULL,
    product_id BIGINT NOT NULL,
    quantity   BIGINT NOT NULL CHECK (quantity > 0),
    UNIQUE (tenant_id, request_id)
);

CREATE TABLE processed_requests (
    tenant_id  BIGINT NOT NULL,
    request_id UUID NOT NULL,
    product_id BIGINT NOT NULL,
    quantity   BIGINT NOT NULL CHECK (quantity > 0),
    order_id   BIGINT REFERENCES orders(id),
    PRIMARY KEY (tenant_id, request_id)
);
~~~

Ý nghĩa của thiết kế:

- **PRIMARY KEY (tenant_id, request_id)** trong **processed_requests** là điểm tranh chấp được database bảo vệ cho cùng một yêu cầu logic.
- **product_id** và **quantity** là dữ liệu đối chiếu khi request được gửi lại; ứng dụng thật còn có thể cần giá, đơn vị tiền, địa chỉ, người đặt, phiên bản điều khoản và các giá trị quyết định hiệu ứng nghiệp vụ.
- **order_id** ghi nhận kết quả của thao tác đã xử lý. Ví dụ chỉ lưu ID đơn; nếu hợp đồng yêu cầu replay đầy đủ response, cần lưu các trường kết quả bền vững hoặc một cách dựng lại kết quả không thay đổi ý nghĩa.
- **UNIQUE (tenant_id, request_id)** trên bảng **orders** là một lớp phòng vệ bổ sung để ngăn hai đơn cùng request ID kể cả có luồng code khác bỏ qua bảng processed_requests.
- Khóa chính **inventory** giúp phép giảm tồn kho kiểm tra một hàng chính xác.

Điều quan trọng nhất: **không được commit một processed_requests record biểu thị “đã xử lý” trước khi những tác động nghiệp vụ cần thiết được commit**. Trong mô hình đơn giản của bài, cả thao tác nhận key, trừ kho, tạo đơn và lưu order_id nằm trong **một transaction**.

## 7. Quy trình claim key và hoàn tất cùng transaction

Với PostgreSQL, service có thể dùng **INSERT ... ON CONFLICT DO NOTHING RETURNING** để thử nhận quyền xử lý một request ID.

~~~sql
BEGIN;

INSERT INTO processed_requests
    (tenant_id, request_id, product_id, quantity)
VALUES
    (10, '52d48a8c-08f0-4e63-9da2-f706b150a9db', 1001, 2)
ON CONFLICT (tenant_id, request_id) DO NOTHING
RETURNING request_id;
~~~

Nếu trả một hàng, transaction hiện tại đã **claim được key**. Tiếp tục:

~~~sql
UPDATE inventory
SET available = available - 2
WHERE tenant_id = 10
  AND product_id = 1001
  AND available >= 2;
-- Ứng dụng phải xác nhận đúng 1 hàng đã được cập nhật.

INSERT INTO orders (tenant_id, request_id, product_id, quantity)
VALUES (10, '52d48a8c-08f0-4e63-9da2-f706b150a9db', 1001, 2)
RETURNING id;
-- Lấy id của đơn vừa tạo, ví dụ 5001.

UPDATE processed_requests
SET order_id = 5001
WHERE tenant_id = 10
  AND request_id = '52d48a8c-08f0-4e63-9da2-f706b150a9db';

COMMIT;
~~~

Đây là **hai đoạn SQL minh họa luồng điều phối của ứng dụng**, không phải script tự động xử lý nhánh. Nếu câu INSERT đầu **không trả hàng**, ứng dụng phải **đọc bản ghi yêu cầu cũ, đối chiếu payload và trả kết quả đã lưu**, không tiếp tục trừ kho và tạo đơn. Nếu giảm kho cập nhật **0 hàng**, cần rollback và trả lỗi nghiệp vụ tương ứng.

### 7.1. Điều gì xảy ra khi hai request cùng key đến đồng thời?

Giả sử T1 và T2 cùng cố INSERT khóa **(10, request-123)**:

~~~text
T1                                        T2
BEGIN                                    BEGIN
INSERT request-123 --> nhận key          INSERT request-123
                                            |
                                            +--> có thể chờ unique conflict
UPDATE inventory
INSERT orders
UPDATE processed_requests.order_id
COMMIT
                                          INSERT không trả hàng
                                          SELECT processed_requests
                                          kiểm tra payload, lấy order_id
                                          COMMIT
~~~

Trong PostgreSQL, ràng buộc duy nhất có thể khiến T2 phải **chờ transaction đang tạo khóa trùng**. Nếu T1 commit, T2 sẽ không claim thêm được key; tại mức **READ COMMITTED**, một câu SELECT mới của T2 có thể đọc kết quả đã commit. Nếu T1 rollback, T2 có thể nhận quyền INSERT và tự xử lý yêu cầu.

Điều này khác với mẫu sai:

~~~text
SELECT xem request_id tồn tại chưa
Nếu chưa -> INSERT và xử lý
~~~

Hai transaction có thể cùng thấy **chưa có hàng**, vì thế **SELECT rồi INSERT không có unique constraint** là kiểm tra có race condition. Chỉ một ràng buộc được database thực thi mới tạo điểm phối hợp đáng tin cậy.

### 7.2. Nếu key đã tồn tại nhưng order_id chưa có?

Trong ví dụ, **mọi bước thuộc một transaction**. Nếu mã đi đúng đường và commit thành công, người đọc transaction khác sẽ thấy bản ghi đã có **order_id**; nếu lỗi xảy ra trước commit, cả bản ghi claim cũng rollback. Nếu vẫn quan sát được bản ghi committed với **order_id NULL**, đó là dấu hiệu dữ liệu hoặc đường ghi khác vi phạm hợp đồng; không nên tự coi là yêu cầu chưa từng xử lý rồi tạo đơn lần nữa.

Với thao tác dài được xử lý bất đồng bộ, có thể **commit trạng thái IN_PROGRESS** rồi hoàn tất sau. Trường hợp đó cần thiết kế state machine, lease, timeout và quyền tiếp quản riêng; không thể áp nguyên lời giải “một transaction” cho một công việc kéo dài nhiều phút.

## 8. Triển khai với Spring JdbcTemplate và @Transactional

Ví dụ sau triển khai quy trình **claim → thực hiện → lưu kết quả** trong một transaction PostgreSQL **READ COMMITTED**. Nó giả định ba bảng đã có như phần 6; **JdbcTemplate** tham gia transaction manager đúng DataSource. Các lớp kiểm soát quyền, định giá, API response và xử lý lỗi HTTP chưa được thể hiện vì trọng tâm là idempotency của thao tác ghi.

~~~java
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderCommandService {
    private final JdbcTemplate jdbc;

    public OrderCommandService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record Result(long orderId, boolean replayed) {}
    private record Saved(long productId, long quantity, Long orderId) {}

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public Result create(
            long tenantId, UUID requestId, long productId, long quantity
    ) {
        if (requestId == null || tenantId <= 0 ||
                productId <= 0 || quantity <= 0) {
            throw new IllegalArgumentException("Đầu vào không hợp lệ");
        }

        List<UUID> claims = jdbc.query(
            """
            INSERT INTO processed_requests
                (tenant_id, request_id, product_id, quantity)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (tenant_id, request_id) DO NOTHING
            RETURNING request_id
            """,
            (rs, rowNum) -> (UUID) rs.getObject(1),
            tenantId, requestId, productId, quantity
        );

        if (claims.isEmpty()) {
            List<Saved> found = jdbc.query(
                """
                SELECT product_id, quantity, order_id
                FROM processed_requests
                WHERE tenant_id = ? AND request_id = ?
                """,
                (rs, rowNum) -> {
                    long savedProduct = rs.getLong("product_id");
                    long savedQuantity = rs.getLong("quantity");
                    long storedId = rs.getLong("order_id");
                    Long orderId = rs.wasNull() ? null : storedId;
                    return new Saved(savedProduct, savedQuantity, orderId);
                },
                tenantId, requestId
            );

            if (found.size() != 1) {
                throw new IllegalStateException(
                    "Không tìm được trạng thái của request đã claim");
            }
            Saved saved = found.get(0);
            if (saved.productId() != productId ||
                    saved.quantity() != quantity) {
                throw new IllegalArgumentException(
                    "Cùng requestId nhưng payload khác");
            }
            if (saved.orderId() == null) {
                throw new IllegalStateException(
                    "Request đã commit nhưng thiếu kết quả");
            }
            return new Result(saved.orderId(), true);
        }

        int updated = jdbc.update(
            """
            UPDATE inventory
            SET available = available - ?
            WHERE tenant_id = ? AND product_id = ?
              AND available >= ?
            """,
            quantity, tenantId, productId, quantity
        );
        if (updated != 1) {
            throw new IllegalStateException("Không đủ tồn kho");
        }

        List<Long> newIds = jdbc.query(
            """
            INSERT INTO orders
                (tenant_id, request_id, product_id, quantity)
            VALUES (?, ?, ?, ?)
            RETURNING id
            """,
            (rs, rowNum) -> rs.getLong(1),
            tenantId, requestId, productId, quantity
        );
        if (newIds.size() != 1) {
            throw new IllegalStateException("Không tạo được đơn");
        }

        long orderId = newIds.get(0);
        int saved = jdbc.update(
            """
            UPDATE processed_requests
            SET order_id = ?
            WHERE tenant_id = ? AND request_id = ?
            """,
            orderId, tenantId, requestId
        );
        if (saved != 1) {
            throw new IllegalStateException("Không lưu được kết quả");
        }
        return new Result(orderId, false);
    }
}
~~~

**Những bảo đảm và giả định quan trọng:**

1. **@Transactional** đặt ranh giới chứa cả INSERT claim, UPDATE tồn kho, INSERT order và UPDATE kết quả. Method phải được gọi qua cơ chế Spring transaction proxy/manager đang hoạt động. Mặc định Spring rollback với runtime exception; ví dụ sử dụng các exception không kiểm tra để bảo vệ giao dịch.
2. Unique constraint trên **(tenant_id, request_id)** được DB kiểm soát. Khi hai yêu cầu chạy đồng thời, **ON CONFLICT** và khóa giúp tránh cả hai cùng claim. Với mức READ COMMITTED, sau khi câu claim kết thúc, SELECT kế tiếp có snapshot mới và có thể thấy bản ghi đã commit của request khác.
3. Nhánh **claims.isEmpty()** chỉ **đối chiếu và trả kết quả cũ**, không trừ tồn kho lần nữa. Nếu payload khác phải từ chối.
4. Nhánh claim thành công thực hiện giảm tồn kho **có điều kiện** và kiểm tra số hàng, tránh overselling trên một hàng. UPDATE này nguyên tử nhưng chỉ được commit cùng toàn bộ transaction.
5. **order_id** là kết quả nghiệp vụ được lưu bền vững cùng đơn hàng. Cờ **replayed** chỉ phục vụ minh họa/quan sát và có thể không cần lộ trong API response.
6. Nếu hết hàng, ví dụ ném exception và **rollback cả claim**. Một lần retry sau khi hàng được bổ sung có thể thành công. Nếu hợp đồng yêu cầu lặp lại **cùng kết quả lỗi nghiệp vụ ban đầu**, phải thiết kế lưu trạng thái từ chối như một kết quả kết thúc, thay vì rollback claim theo mẫu này.

Lưu ý thêm: một exception lúc **commit** do mất kết nối vẫn có thể khiến phía gọi không rõ transaction đã commit hay chưa. Việc dùng request ID cho phép lần gọi tiếp theo **kiểm tra kết quả thay vì tạo thêm đơn**. Không xem việc có **@Transactional** là bảo đảm tự động đúng một lần cho toàn HTTP request.

## 9. Khi nào lưu cả phản hồi, trạng thái và thời hạn của key?

Mô hình đơn giản lưu **order_id** đã đủ cho việc tránh tạo lại đơn. Một API thực tế thường còn quan tâm tới:

| Trường | Vai trò |
| --- | --- |
| **scope / tenant_id / operation_type** | Phân biệt phạm vi request ID |
| **request_id** | Khóa ổn định giữa các lần thử lại |
| **request_fingerprint** | Phát hiện cùng key nhưng nội dung nghiệp vụ khác |
| **status** | Ví dụ PROCESSING, SUCCEEDED, REJECTED, FAILED_RETRYABLE theo hợp đồng |
| **result_id / response_code / response_body** | Cho phép trả kết quả nhất quán khi request lặp |
| **created_at / completed_at** | Quan sát tuổi yêu cầu và xác định chính sách lưu |
| **expires_at** | Thời hạn giữ key nếu nghiệp vụ cho phép xóa |
| **lease_owner / fencing_token** | Chỉ cần trong thiết kế công việc bất đồng bộ được tiếp quản |

Không nhất thiết phải có tất cả trường. Lựa chọn phụ thuộc vào điều kiện nghiệp vụ:

- **Tác động tài chính/điểm thưởng:** thường cần lưu bằng chứng xử lý lâu dài, có thể nằm ở sổ cái với unique business reference; xóa key quá sớm có thể làm giao dịch cũ bị thực hiện lại.
- **Tạo nội dung/đơn hàng:** có thể lưu key trong thời hạn nêu rõ trong hợp đồng API và giữ định danh nghiệp vụ gốc sau đó.
- **Yêu cầu thuần đọc:** nhiều thao tác đã lũy đẳng tự nhiên; có thể không cần bảng idempotency.
- **Công việc dài:** cần trạng thái trung gian có thể đọc qua endpoint trạng thái; API có thể trả **202 Accepted** thay vì giữ kết nối HTTP suốt quá trình.

**TTL không phải chỉ là tối ưu dung lượng.** Nếu server xóa key sau 10 phút trong khi client/message broker có thể retry sau một ngày, cùng request ID có thể được coi là mới và tạo tác động lần hai. Chính sách TTL phải phù hợp cửa sổ retry, thời gian phát lại, yêu cầu pháp lý và khả năng đối soát.

## 10. Hai request đang chạy: trả lỗi, chờ hay báo đang xử lý?

Có hai mô hình thường gặp.

### 10.1. Xử lý đồng bộ trong một transaction

Claim chưa commit nên request khác cùng key có thể **chờ unique constraint**. Nếu transaction đầu ngắn và hoàn tất, request sau đọc kết quả đã commit và trả lại cho client. Hệ thống cần giới hạn chờ bằng **lock timeout, statement timeout, transaction deadline và HTTP deadline** phù hợp.

Nếu request sau hết thời gian chờ, nó có thể trả tín hiệu **đang xử lý/thử lại sau** cho client, nhưng không được tự mở một thao tác mới với key khác.

### 10.2. Xử lý bất đồng bộ có trạng thái bền vững

Khi tác vụ cần nhiều giây hoặc phút, transaction ngắn đầu tiên có thể ghi một yêu cầu **IN_PROGRESS** rồi commit. Worker xử lý nền qua các bước được quản lý. Mô hình này cần:

- Quy tắc chuyển trạng thái rõ ràng: **IN_PROGRESS → SUCCEEDED / REJECTED / RETRYABLE_ERROR**.
- Cơ chế **lease** và **fencing token** nếu worker có thể bị coi là mất rồi được worker khác tiếp quản, để worker cũ không hoàn tất chồng lên worker mới.
- Thao tác nghiệp vụ cuối cùng phải kiểm tra trạng thái/owner và có ràng buộc chống tác động trùng.
- Client nhận cùng key thì xem trạng thái hoặc nhận **202** cùng ID; không tự chạy thêm tác vụ song song.
- Kế hoạch xử lý yêu cầu bị kẹt, deadline, cảnh báo và khả năng tiếp tục sau crash.

Không được dùng một cột **IN_PROGRESS** rồi mặc định mọi request ở trạng thái đó sẽ tự hoàn tất. Nếu tiến trình chết, hệ thống cần cơ chế khôi phục hoặc tiếp quản được thiết kế trước.

## 11. Retry có điều kiện: phân loại lỗi trước

Ngay cả khi đã có idempotency, **không phải lỗi nào cũng nên retry**. Một số lỗi mang tính kết thúc, retry chỉ tăng tải và trì hoãn phản hồi rõ ràng.

| Lỗi hoặc tình huống | Có nên tự động retry? | Lý do và điều kiện |
| --- | --- | --- |
| Không lấy được connection từ pool | Có thể, có giới hạn | Chưa thực thi thao tác mới; cần xem pool quá tải và deadline |
| Kết nối DB không thiết lập được | Có thể, có giới hạn | Kiểm tra lỗi tạm thời, tránh dồn retry lên DB đang sự cố |
| PostgreSQL **40001** (serialization failure) | Thường có thể | **Retry toàn bộ transaction** và các bước đọc/ra quyết định trên snapshot mới |
| PostgreSQL **40P01** (deadlock) | Thường có thể | DB đã hủy một transaction; retry với backoff khi nghiệp vụ cho phép |
| **lock_timeout** | Có thể | Tìm nguyên nhân khóa, retry có jitter nếu không vượt deadline |
| **statement_timeout** | Phụ thuộc | Truy vấn có thể quá đắt hoặc đang chờ; phải xác định transaction đã rollback/có an toàn không |
| **23505** (unique violation) | Không retry mù quáng | Có thể là key trùng hoặc một ràng buộc nghiệp vụ khác; đọc lại và phân loại |
| Đầu vào không hợp lệ/không đủ tồn kho | Thường không | Retry cùng trạng thái có khả năng thất bại tiếp; phụ thuộc hợp đồng kết quả lỗi |
| Mất kết nối lúc **COMMIT** | Chỉ sau đối soát | Kết quả chưa chắc chắn; cùng key giúp đọc trạng thái trước khi quyết định |
| HTTP **429 / 503 / 502 / 504** từ dịch vụ ngoài | Có thể | Tôn trọng **Retry-After**, deadline và tính lũy đẳng của thao tác ngoài |

Trong PostgreSQL, **SQLSTATE 57014** thường liên quan query canceled, có thể do statement timeout hoặc hủy chủ động; **55P03** liên quan lock not available. Chỉ dựa vào mã nhóm là chưa đủ để quyết định retry: cần đọc ngữ cảnh, trạng thái transaction, thông điệp lỗi và hợp đồng nghiệp vụ.

Nếu một transaction bị lỗi ở PostgreSQL, nó thường chuyển sang trạng thái cần **ROLLBACK** trước khi tiếp tục. Không bắt SQLException rồi thử lại riêng câu UPDATE cuối trên **cùng transaction đã abort**.

## 12. Retry đúng đơn vị công việc và đúng key

Giả sử nghiệp vụ phải đọc trạng thái hiện hành, trừ tồn kho và tạo đơn trong transaction. Khi lỗi serialization xảy ra, **không** được retry riêng câu INSERT cuối cùng dựa trên dữ liệu đã đọc từ snapshot cũ.

~~~text
Sai:
  BEGIN
    SELECT trạng thái
    UPDATE inventory
    INSERT orders --> serialization error
    thử lại INSERT ngay trên transaction cũ

Đúng:
  ROLLBACK / để transaction manager rollback
  BEGIN transaction mới, vẫn dùng cùng request_id
    claim hoặc đối chiếu request_id
    đọc lại các điều kiện nghiệp vụ
    thực hiện mọi thay đổi bắt buộc
  COMMIT
~~~

Trong ứng dụng Spring, một lớp điều phối **bên ngoài** transaction có thể thực hiện retry toàn bộ lời gọi service **@Transactional**. Retry phải tạo **lần gọi giao dịch mới**; nếu đặt vòng retry trong cùng method transaction, mọi lần thử có thể dùng chung transaction bị lỗi và không bao giờ khôi phục đúng.

Với một request HTTP, người gọi giữ **cùng request ID** qua mọi attempt. Tạo UUID mới trong mỗi attempt khiến cơ chế deduplication mất tác dụng.

## 13. Exponential backoff, jitter và ngân sách retry

Retry liên tiếp ngay lập tức có thể làm sự cố trầm trọng hơn. Ví dụ 2.000 request cùng bị từ chối kết nối; nếu tất cả thử lại sau đúng 100 ms, database lại nhận một đợt tải đồng bộ.

Một chiến lược thông dụng:

~~~text
base_delay = 100 ms
max_delay  = 2 000 ms
attempt    = 1, 2, 3, ...

backoff_cap = min(max_delay, base_delay * 2^(attempt - 1))
sleep_delay = random(0, backoff_cap)  // full jitter
~~~

Đây là công thức minh họa, không phải lời khuyên dùng một bộ tham số cho mọi hệ thống. Khi triển khai cần:

- **Giới hạn số attempt và thời gian tổng**, gồm thời gian pool wait, SQL, backoff và deadline HTTP.
- Nếu bên ngoài đã retry request, tránh để mỗi tầng bên trong cùng retry nhiều lần rồi nhân tải lên theo cấp số nhân.
- Với HTTP **429** hoặc dịch vụ có quy định **Retry-After**, cân nhắc hướng dẫn của phía nhận trong giới hạn deadline nghiệp vụ.
- Dùng **jitter** để phân tán thời điểm retry, cùng **backpressure/circuit breaker** khi hệ phụ thuộc đang quá tải.
- Không giữ transaction hoặc connection DB mở trong lúc chờ backoff. Mỗi attempt mới cần transaction mới.
- Không để retry tự động che mất lỗi nghiệp vụ, làm API giữ request quá lâu hoặc làm xấu khả năng quan sát lỗi.

Ví dụ ngân sách giả định:

~~~text
Deadline request = 5 giây
Attempt 1: lấy connection + transaction     1,4 giây
Backoff có jitter                            0,1 giây
Attempt 2: transaction mới                   1,2 giây
Backoff có jitter                            0,3 giây
Thời gian còn cho attempt 3                  tối đa 2,0 giây
~~~

Tổng thời gian cho retry phải nằm trong deadline của request, hoặc công việc phải chuyển sang **quy trình bất đồng bộ có trạng thái**. Không giữ HTTP request vô hạn chỉ vì muốn “chắc chắn thành công”.

## 14. Khi kết quả COMMIT không rõ ràng

Tình huống khó nhất: API đã gửi **COMMIT**, sau đó kết nối mất trước phản hồi.

~~~text
Trường hợp A:
  SQL đã chạy nhưng DB rollback --> không có kết quả committed

Trường hợp B:
  COMMIT đã bền vững --> response bị mất --> client nhìn thấy lỗi
~~~

Một ngoại lệ trên connection **không phân biệt chắc chắn A và B**. Ngay cả khi ứng dụng thử gọi rollback sau lỗi, rollback không thể thu hồi giao dịch đã commit trên server.

Quy trình phục hồi an toàn:

1. Không ngay lập tức tạo request ID khác để chạy lại thao tác.
2. Dùng connection còn hoạt động hoặc **connection mới** sau khi DB sẵn sàng để truy vấn trạng thái của **request_id**.
3. Nếu đã có kết quả committed và payload khớp, trả lại kết quả đó.
4. Nếu chứng minh được chưa xử lý, thực hiện lại bằng **cùng request_id** qua transaction có unique constraint; phải tiếp tục chống race với tiến trình cũ đang chạy.
5. Nếu DB chưa thể kiểm tra hoặc kết quả chưa thể kết luận, giữ trạng thái **UNKNOWN/PENDING**, trả hướng dẫn tra cứu hoặc xử lý bất đồng bộ; không khẳng định đã rollback.

Không phải mọi hệ thống có thể chứng minh “chưa xử lý” chỉ bằng việc không thấy một hàng ở thời điểm hiện tại. Yêu cầu có thể còn đang thực thi hoặc bản ghi chưa commit. **Unique constraint và claim atomically** vẫn là tuyến phòng vệ khi hệ thống quyết định thử lại.

## 15. Tác dụng phụ ngoài database: gửi email và message

Giả sử luồng nghiệp vụ:

~~~text
BEGIN DB transaction
  INSERT order
  Gửi email xác nhận --> email đã gửi
  UPDATE inventory   --> lỗi
ROLLBACK
~~~

Database có thể rollback đơn hàng, nhưng email không được thu hồi. Idempotency ở bảng orders cũng không tự khắc phục email đã gửi trước đó.

Một cách thiết kế thường dùng là **transactional outbox**:

~~~text
Transaction DB:
  INSERT order
  INSERT processed_requests
  INSERT outbox_event(event_id, order_id, event_type, payload)
  COMMIT
          |
          v
Outbox publisher --> Message broker --> Consumer
      có thể gửi lặp                kiểm tra event_id
~~~

Outbox bảo đảm **dữ liệu nghiệp vụ và ý định gửi sự kiện** được lưu cùng một transaction DB. Publisher có thể crash sau khi gửi nhưng trước khi đánh dấu đã gửi, nên event có thể được phát lại. **Consumer phải deduplicate/idempotent**.

Ở phía consumer, có thể dùng bảng **processed_events(consumer_name, event_id)** với unique constraint và ghi dấu đã xử lý trong cùng transaction với thay đổi DB đích. Nếu consumer còn gọi một API ngoài, transaction DB cục bộ không tự bao trùm API đó: cần idempotency key được phía API chấp nhận hoặc mô hình saga/đối soát phù hợp.

## 16. Có đạt “exactly once” không?

Đừng diễn giải idempotency key thành “mạng sẽ gửi một lần” hoặc “code sẽ chạy đúng một lần”.

Một hệ thống có thể:

- **Nhận cùng request nhiều lần**.
- **Chạy logic kiểm tra nhiều lần** do retry hoặc tranh chấp.
- **Gửi sự kiện nhiều lần** vì publisher không biết broker đã nhận chưa.
- Nhưng vẫn bảo đảm **một tác động nghiệp vụ được commit cho mỗi request ID hợp lệ** trong phạm vi DB và hợp đồng đã xác định.

Đó là cách diễn đạt thực tế hơn về **effectively-once business effect** trong phạm vi được quản lý. Bảo đảm chỉ đúng khi mọi đường ghi đều dùng cùng quy tắc unique key, không có đường vòng không kiểm soát, key được giữ đủ lâu và các tác dụng phụ ngoài DB được phối hợp phù hợp.

Nếu một consumer ghi vào database đích nhưng việc ghi dấu đã xử lý nằm ở một database độc lập khác, hai thao tác không cùng một transaction. Tính lũy đẳng phải được thiết kế ở **ranh giới thực sự có thể commit nguyên tử**, hoặc có kế hoạch bù trừ/đối soát.

## 17. Các trường hợp lỗi và hành vi mong đợi

| Tình huống | Hành vi mong đợi |
| --- | --- |
| Request đầu hợp lệ, đủ hàng | Một transaction tạo đơn, trừ hàng, lưu request ID và kết quả |
| Retry cùng key và cùng payload sau commit | Không trừ kho/tạo đơn lần nữa; trả lại đơn đã lưu |
| Hai request cùng key đến đồng thời | Chỉ một transaction claim thành công; transaction khác chờ hoặc đọc lại kết quả |
| Cùng key nhưng payload khác | Báo xung đột; không tạo tác động mới |
| Claim được key rồi UPDATE tồn kho thất bại, toàn transaction rollback | Không tồn tại processed record committed giả thành công |
| INSERT order thất bại sau khi giảm tồn kho nhưng chưa commit | Toàn transaction rollback, tồn kho không bị giảm vĩnh viễn |
| Client mất phản hồi sau COMMIT | Dùng lại cùng key để đối chiếu; không tạo đơn thứ hai |
| Chạy SERIALIZABLE gặp 40001 | Retry toàn bộ transaction mới nếu còn thời gian, giữ key |
| Key đã hết TTL rồi client gửi lại | Có nguy cơ tạo lại tác động; chính sách giữ key phải phù hợp cửa sổ retry |
| Publisher gửi outbox event hai lần | Consumer deduplicate theo event ID và xử lý tác động đích an toàn |
| Retry request bị hủy bởi người dùng | Phải có hợp đồng cancel rõ ràng; hủy HTTP không chắc hủy giao dịch DB đã commit |

**Trạng thái lỗi có thể cache hay không** là một quyết định nghiệp vụ. Ví dụ nếu yêu cầu bị từ chối vì không đủ hàng, hệ thống có thể trả cùng kết quả từ chối trong mọi lần retry cùng key, hoặc cho phép cùng request được xử lý lại sau khi restock. Quy tắc này phải được công bố rõ; không để hành vi ngẫu nhiên tùy thời điểm timeout.

## 18. Cách kiểm thử idempotency và retry

Một test đơn giản “gửi lại hai lần rồi chỉ có một đơn” là cần thiết nhưng chưa đủ. Cần kiểm thử các ranh giới mà lỗi thật hay xảy ra:

1. **Lặp tuần tự:** gửi hai request cùng key/payload. Kiểm tra cùng kết quả nghiệp vụ, số đơn bằng 1 và tồn kho chỉ trừ một lần.
2. **Lặp đồng thời:** cho nhiều thread gửi cùng key lên các connection khác nhau. Kiểm tra unique constraint, không deadlock kéo dài và không tạo tác động trùng.
3. **Payload khác:** gửi cùng key nhưng đổi số lượng/sản phẩm. Kiểm tra bị từ chối mà không thay đổi dữ liệu.
4. **Lỗi giữa transaction:** gây lỗi sau khi trừ kho nhưng trước khi tạo đơn; kiểm tra rollback cả kho và claim.
5. **Mất phản hồi sau commit:** mô phỏng server đã commit nhưng client bị timeout. Retry cùng key phải trả kết quả cũ.
6. **Lỗi serialization/deadlock:** bảo đảm mỗi attempt dùng transaction mới và retry toàn unit of work, không giữ snapshot hoặc connection đã lỗi.
7. **Worker chết sau khi gửi message:** publisher khởi động lại có thể gửi lặp; consumer không ghi tác động hai lần.
8. **TTL và dữ liệu cũ:** nếu key bị dọn theo thời hạn, kiểm tra chính sách không cho phép replay gây tác động không mong muốn.

Trong kiểm thử, đối chiếu **bất biến dữ liệu**, không chỉ xem HTTP status:

~~~text
Số order với (tenant_id, request_id) = 1
Số lần trừ tồn kho cho một request = 1
Kết quả replay trỏ về cùng order_id
Không có record "đã xử lý" trỏ tới một order không tồn tại
~~~

Nếu thực hiện kiểm thử cạnh tranh, cần các connection/transaction độc lập và điểm đồng bộ phù hợp để tái hiện thực sự hai luồng chạy chồng nhau. Gọi cùng method tuần tự trong một thread không kiểm tra được race khi hai request cố claim đồng thời.

## 19. Quan sát và vận hành

Khi triển khai retry an toàn, hãy bổ sung các tín hiệu sau:

- **idempotency_new_total:** số request mới claim thành công.
- **idempotency_replay_total:** số lần trả kết quả đã xử lý.
- **idempotency_payload_conflict_total:** cùng key nhưng payload khác.
- **idempotency_inflight_wait_duration:** thời gian chờ claim khi cùng key đang được xử lý.
- **retry_attempts / retry_exhausted:** số attempt và trường hợp hết ngân sách.
- **commit_unknown_total:** số lần client không xác định được trạng thái commit.
- **transaction_rollback / deadlock / serialization_failure:** phân loại lỗi DB.
- **outbox_backlog / duplicate_event_total:** trạng thái phát/nhận sự kiện khi có tích hợp.

Log nên có **correlation ID, tenant ID đã xác thực, request ID, operation type, trạng thái attempt và SQLSTATE**. Không ghi dữ liệu nhạy cảm không cần thiết như số thẻ, token hoặc payload nguyên văn. Khi cần lưu fingerprint, lựa chọn cách mã hóa/bảo vệ phù hợp với dữ liệu và chính sách truy cập.

Tăng mạnh tỷ lệ replay có thể là client retry bất thường, kết nối chập chờn hoặc ứng dụng tạo lại request quá nhiều. Tăng tỷ lệ conflict có thể báo hiệu client tái sử dụng key sai, lỗi canonicalization payload hoặc hành vi bất thường. Dùng số liệu để chẩn đoán trước khi đổi chính sách retry.

## 20. Những sai lầm thiết kế thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Mỗi attempt tạo một UUID mới | Server không nhận ra request trùng | Tạo key một lần cho ý định nghiệp vụ, giữ nguyên qua retry |
| Chỉ **SELECT** kiểm tra key rồi **INSERT** | Hai transaction cùng thấy chưa tồn tại | Dùng unique constraint và claim bằng thao tác nguyên tử |
| Đánh dấu SUCCESS trước khi nghiệp vụ commit | Record báo thành công nhưng đơn hàng chưa có | Ghi kết quả và tác động nghiệp vụ trong cùng transaction |
| Coi **23505** luôn là retry thành công | Có thể vi phạm unique constraint khác hoặc payload khác | Phân biệt ràng buộc, đối chiếu payload và kết quả |
| Cho cùng key với payload mới chạy lại | Có thể tạo tác động ngoài ý định | Lưu/đối chiếu fingerprint hoặc trường nghiệp vụ |
| Tự động retry sau commit timeout với key mới | Dễ thanh toán/tạo đơn hai lần | Giữ key, đối soát trạng thái, xử lý kết quả chưa rõ |
| Retry riêng statement cuối trên transaction đã lỗi | Snapshot/transaction có thể đã abort | Rollback và retry toàn bộ unit of work trong transaction mới |
| Giữ transaction mở trong khi backoff | Giữ khóa và chiếm pool, làm tăng tải | Kết thúc transaction trước khi chờ retry |
| Dọn key quá sớm | Retry muộn bị coi là request mới | TTL phù hợp hợp đồng và thời gian phát lại |
| Chỉ deduplicate phía producer, quên consumer | Event lặp có thể tạo tác động lặp | Dùng inbox/event ID và unique constraint ở nơi tiêu thụ |
| Trộn gửi email/API ngoài vào transaction DB | Rollback DB không hoàn tác tác dụng ngoài | Outbox/idempotent external API hoặc mô hình phối hợp |
| Coi mọi lỗi timeout đều retryable | Gây bão retry và che lỗi nghiệp vụ | Phân loại lỗi, backoff, jitter, deadline, circuit breaker |

## 21. Bài tập vận dụng

### Bài 1. Hai lần bấm đặt hàng

Người dùng bấm “Đặt hàng”, nhận timeout, rồi bấm lại. Cả hai request đều có cùng key nhưng lần thứ hai đổi **quantity từ 2 thành 3**. Server nên làm gì?

**Gợi ý:** Từ chối yêu cầu thứ hai vì cùng key nhưng payload nghiệp vụ khác. Nếu người dùng muốn tạo đơn khác hoặc sửa đơn, dùng quy trình và định danh thao tác phù hợp, không tái sử dụng key cũ như một yêu cầu mới.

### Bài 2. Atomic UPDATE và retry

Một API tăng điểm bằng:

~~~sql
UPDATE rewards
SET points = points + 10
WHERE user_id = 501;
~~~

Câu UPDATE có tính nguyên tử trên hàng, vậy có thể tự động retry bất cứ khi nào client mất kết nối không?

**Gợi ý:** Không. Nếu lần đầu đã commit, lần sau cộng thêm 10. Cần định danh sự kiện điểm duy nhất, unique constraint và transaction bảo vệ cả việc ghi sổ điểm lẫn cập nhật số dư.

### Bài 3. Hai transaction cùng claim

T1 đã INSERT một idempotency key nhưng chưa commit. T2 dùng cùng key và chạy **INSERT ... ON CONFLICT DO NOTHING** ở PostgreSQL. T2 chắc chắn trả kết quả ngay không?

**Gợi ý:** Không. T2 có thể phải chờ transaction T1 quyết định commit/rollback vì unique constraint. Sau commit của T1, T2 không claim được key và cần đọc kết quả; nếu T1 rollback, T2 có thể tự claim.

### Bài 4. Hết hàng giữa transaction

Service claim key thành công rồi trừ tồn kho được 0 hàng. Theo ví dụ code ở phần 8, request record sẽ ở trạng thái nào sau exception?

**Gợi ý:** Method ném runtime exception, transaction rollback, nên claim chưa commit cũng mất. Nếu muốn cache kết quả “không đủ hàng” cho key này, cần một thiết kế trạng thái từ chối có chủ đích và commit nhất quán.

### Bài 5. Serialization failure

Một transaction SERIALIZABLE đọc hạn mức, quyết định được phép thanh toán và cập nhật hai hàng. Câu cuối bị **SQLSTATE 40001**. Chỉ chạy lại câu cuối có đúng không?

**Gợi ý:** Không. Retry toàn transaction trong giao dịch mới, đọc lại hạn mức và điều kiện nghiệp vụ. Giữ request ID cũ để chống tác động trùng.

### Bài 6. Outbox và duplicate event

Publisher gửi **OrderCreated(eventId=E10)** tới broker, broker đã nhận nhưng publisher crash trước khi đánh dấu hoàn tất. Sau khởi động publisher gửi E10 lần nữa. Làm sao consumer tránh tạo hai hóa đơn?

**Gợi ý:** Consumer dùng event ID trong phạm vi consumer, unique constraint và transaction gộp việc ghi dấu đã xử lý với tạo hóa đơn; khi nhận lại E10, đọc/đối chiếu kết quả cũ.

### Bài 7. TTL ngắn

Service giữ idempotency key trong 15 phút, nhưng hàng đợi có thể phát lại message sau 24 giờ. Thiết kế này có rủi ro gì?

**Gợi ý:** Khi key hết hạn, message cũ có thể được xử lý như mới. Phải phối hợp thời hạn giữ key với cửa sổ phát lại, hoặc giữ một khóa nghiệp vụ bền vững hơn để ngăn trùng.

### Bài 8. Kết quả commit không chắc chắn

Client gửi COMMIT và nhận SQLException do mất mạng. Server có thể đã commit nhưng client chưa biết. Nêu thứ tự xử lý trước khi gửi lại thao tác.

**Gợi ý:** Giữ request ID, kết nối lại và tra trạng thái, đối chiếu payload/kết quả; nếu có kết quả thì trả lại; nếu chưa thể kết luận thì duy trì trạng thái chờ/đối soát, không dùng key mới. Mọi attempt sau vẫn phải được bảo vệ bằng unique constraint và transaction.

## 22. Ghi nhớ khi thiết kế tầng persistence

**Thiết kế lũy đẳng phải đi trước retry.** Trước khi cho hệ thống tự thử lại, hãy xác định “một thao tác nghiệp vụ” được nhận diện bằng gì, lưu key ở phạm vi nào, xử lý thế nào khi key trùng hoặc payload khác, và kết quả nào cần được trả lại. Dùng **ràng buộc duy nhất tại database** làm điểm phối hợp và **một transaction** để ghi nhận key, tác động nghiệp vụ cùng kết quả đã hoàn tất.

Sau đó mới chọn **những lỗi thực sự đáng retry**, thực hiện lại **toàn bộ transaction** khi cần, giới hạn số attempt và deadline, dùng **backoff có jitter** và theo dõi lỗi. Khi có kết nối đứt lúc COMMIT hoặc tác dụng phụ ngoài DB, cần thêm **đối soát, outbox/inbox và cơ chế idempotency của hệ thống nhận**. Nhờ đó, ứng dụng Java có thể chấp nhận thông điệp hoặc request được gửi lặp mà vẫn giữ đúng bất biến dữ liệu và tránh tạo tác động nghiệp vụ ngoài ý định.
