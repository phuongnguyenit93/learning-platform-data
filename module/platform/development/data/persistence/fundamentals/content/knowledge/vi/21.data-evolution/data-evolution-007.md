# Chiến lược mở rộng rồi thu hẹp (expand–contract)

## Mục tiêu học tập

Sau khi hoàn thành bài học, người học có thể:

1. Giải thích vì sao thay đổi schema trực tiếp có thể làm ứng dụng Java đang chạy lỗi dù migration SQL đã thực thi thành công.
2. Trình bày các pha **expand → migrate/backfill → chuyển đổi read/write → contract** và điều kiện an toàn để đi sang từng pha.
3. Thiết kế tương thích giữa **phiên bản ứng dụng cũ và mới** trong lúc rolling deployment, canary, blue–green deployment hoặc rollback.
4. Xử lý trường hợp cập nhật xảy ra đồng thời với backfill, không làm mất dữ liệu hoặc chọn nhầm bản ghi cũ.
5. Viết ví dụ PostgreSQL và JDBC cho việc đổi cột có kiểm soát, dual-write nguyên tử và backfill theo lô.
6. Phân tích lock DDL, transaction, index, replication lag, timeout, bảo mật, quan sát và kế hoạch khôi phục.
7. Xây dựng bảng kiểm tra triển khai và tiêu chí chứng minh không còn consumer phụ thuộc vào cấu trúc cũ trước khi xóa nó.

Bài thuộc chương **Tiến hóa dữ liệu** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Module nghiên cứu nguyên lý lưu trữ dữ liệu bền vững trong ứng dụng Java: mô hình dữ liệu, lược đồ, truy vấn, chỉ mục, giao dịch, cô lập, đồng thời, lỗi kết nối, sao lưu, bảo mật và hiệu năng. Khi tiến hóa schema, yêu cầu không chỉ là “DDL chạy được”, mà là **mọi phiên bản ứng dụng đang hoạt động đều có thể đọc/ghi đúng dữ liệu trong suốt quá trình chuyển đổi**.

## 1. Vì sao một lệnh đổi cột có thể làm sập hệ thống?

Giả sử một dịch vụ đặt hàng đang có bảng PostgreSQL:

~~~sql
CREATE TABLE orders (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      BIGINT NOT NULL,
    delivery_note  TEXT,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Phiên bản ứng dụng **V1** sử dụng cột `delivery_note` để đọc và ghi ghi chú giao hàng.

Một migration trực tiếp:

~~~sql
ALTER TABLE orders
RENAME COLUMN delivery_note TO shipping_note;
~~~

có thể hoàn thành rất nhanh, nhưng ngay sau đó **V1 vẫn đang chạy** và tiếp tục gửi:

~~~sql
SELECT id, delivery_note
FROM orders
WHERE tenant_id = ? AND id = ?;
~~~

Câu SQL này sẽ thất bại vì cột cũ không còn tồn tại. Việc PostgreSQL đổi tên metadata thành công **không có nghĩa toàn bộ các service instance, job nền, API, consumer, báo cáo hoặc công cụ vận hành đã đồng thời chuyển sang tên mới**.

Trong deployment thực tế thường tồn tại một khoảng thời gian mà:

- Load balancer vẫn chuyển request tới cả V1 và V2.
- Worker hoặc batch job có chu kỳ khởi động khác API.
- Connection pool của một tiến trình còn đang thực thi request trước khi rollout.
- Rollback về bản build cũ vẫn là phương án phục hồi khả dụng.
- Một query báo cáo, event consumer hoặc job định kỳ còn dùng cột cũ.

Do đó, đổi schema **phá tương thích** trong một bước dễ tạo lỗi production dù SQL hợp lệ.

**Expand–contract** chia thay đổi thành nhiều bước tương thích để cấu trúc cũ và mới có thể cùng tồn tại trong một giai đoạn chuyển tiếp.

## 2. Expand–contract thực sự là một giao thức chuyển trạng thái

Quy trình điển hình:

~~~text
Schema cũ + ứng dụng cũ
          |
          v
EXPAND: thêm cấu trúc mới, giữ cấu trúc cũ
          |
          v
Ứng dụng chuyển tiếp hỗ trợ cả hai cấu trúc
          |
          v
BACKFILL: chuyển dữ liệu cũ sang cấu trúc mới theo lô
          |
          v
READ CUTOVER: xác minh dữ liệu mới, chuyển nguồn đọc
          |
          v
WRITE CUTOVER: ứng dụng không còn phụ thuộc ghi cột cũ
          |
          v
CONTRACT: xóa cột/constraint/API cũ sau cửa sổ rollback
          |
          v
Schema mới + ứng dụng mới
~~~

Đây là **quy trình logic**, không phải yêu cầu số lượng deployment cố định. Trong một thay đổi đơn giản có thể gom vài bước; trong thay đổi lớn có thể tách thành nhiều release và chạy backfill hàng ngày.

| Pha | Cấu trúc dữ liệu | Trách nhiệm ứng dụng | Điều kiện để tiến tiếp |
| --- | --- | --- | --- |
| **Expand** | Thêm cột/bảng/index/ràng buộc mới theo cách tương thích | Phiên bản cũ vẫn chạy bình thường | Schema mới tồn tại, không làm hỏng V1 |
| **Transition** | Cả cũ và mới cùng tồn tại | Phiên bản chuyển tiếp đọc/ghi theo giao thức rõ ràng | Có thể triển khai song song các version |
| **Backfill** | Chuyển dữ liệu lịch sử sang cấu trúc mới | Ghi mới và backfill không giẫm lên nhau | Dữ liệu mới đầy đủ, được đối soát |
| **Read cutover** | Cả cột vẫn hiện diện | Đọc dữ liệu mới, duy trì khả năng quay lại khi còn rollback | Không còn writer cũ gây stale cho cấu trúc mới |
| **Write cutover** | Cấu trúc cũ còn để tương thích/quan sát | Ngừng ghi cũ sau khi xác định rollback boundary | Không còn consumer yêu cầu cột cũ |
| **Contract** | Xóa cấu trúc cũ | Chỉ chạy code tương thích schema cuối | Hết cửa sổ rollback, dependency và dữ liệu đã kiểm chứng |

Ba nguyên tắc nền tảng:

1. **Mỗi bước migration phải tương thích với các phiên bản sẽ cùng chạy tại thời điểm đó.**
2. **Không chuyển nguồn sự thật một cách ngầm định.** Phải nói rõ thời điểm cột cũ hay cột mới là nơi được tin cậy khi hai giá trị khác nhau.
3. **Xóa là bước cuối.** Một cấu trúc có vẻ “không còn dùng” vẫn có thể phục vụ rollback, batch job, CDC consumer hoặc một code path ít chạy.

## 3. Ví dụ xuyên suốt: đổi `delivery_note` thành `shipping_note`

Ta sẽ triển khai tên mới mà không làm gián đoạn V1. Để tập trung vào cơ chế, cả hai cột là `TEXT` có thể NULL và có **cùng ý nghĩa nghiệp vụ**.

Các trạng thái ứng dụng:

- **V1:** chỉ biết `delivery_note`; đọc và ghi cột cũ.
- **V2:** phiên bản chuyển tiếp, biết cả hai cột, **đọc cột cũ** trong lúc V1 còn hoạt động, **ghi cả hai trong cùng transaction**.
- **V2 sau cutover:** chuyển đọc sang `shipping_note`, vẫn ghi cả hai để có thể rollback về V1 trong cửa sổ đã định.
- **V3:** chỉ đọc/ghi `shipping_note` sau khi không còn cần rollback về V1; cột cũ vẫn hiện diện tạm thời cho đến khi toàn bộ V2 đã ngừng.
- **Schema cuối:** xóa `delivery_note` khi không còn V1/V2, query, job hoặc integration sử dụng nó.

### 3.1. Ma trận version/schema

| Trạng thái | V1: cũ-only | V2: dual-write | V3: mới-only |
| --- | --- | --- | --- |
| **S0:** chỉ `delivery_note` | Hoạt động | Không tương thích: V2 cần cột mới | Không tương thích |
| **S1:** có cả hai cột, cột mới cho phép NULL | Hoạt động | Hoạt động | Chỉ phù hợp khi quy tắc ghi/read đã cutover |
| **S2:** dữ liệu mới đã được backfill và kiểm chứng | Vẫn có thể ghi cột cũ, gây lệch | Hoạt động | Phù hợp sau khi loại writer cũ |
| **S3:** chỉ `shipping_note` | Không tương thích | Không tương thích: V2 còn ghi cột cũ | Hoạt động |

**Quan trọng:** một version chạy được với schema hai cột **không đồng nghĩa dữ liệu luôn nhất quán**. V1 chỉ ghi cột cũ; nếu V2 đã đọc cột mới mà V1 còn sửa một đơn hàng, V2 có thể thấy bản cũ. Vì thế, kế hoạch rollout phải kiểm soát **cả khả năng chạy SQL lẫn semantics của dữ liệu**.

## 4. Pha EXPAND: thêm mà chưa phá

Trong PostgreSQL, migration đầu tiên:

~~~sql
-- Migration M1: schema được mở rộng.
ALTER TABLE orders
ADD COLUMN shipping_note TEXT;
~~~

Các lưu ý:

- Cột mới **cho phép NULL**, nên hàng lịch sử chưa có `shipping_note` vẫn hợp lệ.
- V1 không truy cập cột mới nên các câu SQL chỉ định rõ danh sách cột vẫn chạy.
- Trong nhiều phiên bản PostgreSQL, thêm cột nullable không có default có thể là thao tác metadata ngắn; nhưng `ALTER TABLE` vẫn có thể yêu cầu **ACCESS EXCLUSIVE lock** và phải chờ transaction khác nhả khóa.
- Không mặc nhiên kết luận “thêm cột không khóa bảng”. Ở production, cần kế hoạch lock timeout và quan sát các transaction dài.
- Code `INSERT INTO orders VALUES (...)` không chỉ định danh sách cột dễ bị hỏng khi schema đổi. Nên dùng `INSERT INTO orders (tenant_id, delivery_note) VALUES (?, ?)`.

Ví dụ chạy DDL với thời gian chờ khóa có giới hạn trong môi trường được quản lý:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';
ALTER TABLE orders ADD COLUMN shipping_note TEXT;
COMMIT;
~~~

Nếu không lấy được khóa đúng hạn, PostgreSQL báo lỗi; transaction phải rollback. Có thể lên lịch thử lại migration theo quy trình vận hành, **không retry vô hạn** gây tranh chấp. Hệ thống migration cần ghi nhận migration nào đã thành công và quản lý thứ tự triển khai.

Nếu sử dụng Flyway hoặc Liquibase, hãy để một cơ chế quản lý version migration có kiểm soát. Những công cụ đó không tự quyết định được logic backfill, thời điểm cutover hoặc khả năng rollback ứng dụng.

### 4.1. Vì sao không thêm ngay ràng buộc NOT NULL?

Nếu yêu cầu cột mới bắt buộc có dữ liệu, trực tiếp thêm `shipping_note TEXT NOT NULL` vào bảng đang có hàng lịch sử thường thất bại khi chưa có giá trị, hoặc đòi thao tác ảnh hưởng lớn đến toàn bảng.

Thứ tự phổ biến là:

1. Thêm cột mới ở trạng thái tương thích (có thể NULL).
2. Đảm bảo mọi writer mới cung cấp giá trị khi nghiệp vụ cần.
3. Backfill hàng lịch sử và kiểm tra `NULL`.
4. Chỉ sau đó mới áp đặt ràng buộc chặt hơn theo cách phù hợp với DBMS.

Trong ví dụ `shipping_note`, **NULL là giá trị hợp lệ** vì khách hàng có thể không có ghi chú; ta không thêm NOT NULL một cách máy móc. Thiết kế migration phải giữ đúng **ngữ nghĩa nghiệp vụ**, không chỉ đáp ứng “mỗi cột đều có giá trị”.

## 5. Pha TRANSITION: V1 và V2 cùng tồn tại

Phiên bản V2 có thể dùng **dual-write trong một UPDATE**:

~~~sql
UPDATE orders
SET delivery_note = ?,
    shipping_note = ?,
    updated_at = CURRENT_TIMESTAMP
WHERE tenant_id = ?
  AND id = ?;
~~~

Cả hai tham số ghi chú là **cùng một giá trị logic**. Vì là một statement trong một transaction DB, thao tác không tạo tình trạng “cột cũ commit nhưng cột mới rollback” trong chính transaction đó.

Không nên thực hiện:

~~~text
UPDATE delivery_note ở transaction A -> COMMIT
UPDATE shipping_note ở transaction B -> COMMIT
~~~

Nếu ứng dụng lỗi, mạng đứt hoặc một câu SQL thất bại ở giữa, hai cột có thể khác nhau. Nếu bắt buộc dùng nhiều statement, chúng phải tham gia **cùng một transaction**, với rollback khi có lỗi và idempotency khi kết quả commit không chắc chắn.

### 5.1. Đừng chuyển sang đọc cột mới quá sớm

Giả sử trước rollout, hai cột đều có giá trị `"Gọi trước khi giao"`. Trong lúc V1 và V2 cùng chạy:

~~~text
T1: V2 đọc cả hai cột (đang bằng nhau)
T2: V1 UPDATE delivery_note = "Giao sau 18h"
T3: V1 COMMIT
T4: shipping_note vẫn là "Gọi trước khi giao"
T5: V2 nếu đọc shipping_note sẽ thấy dữ liệu cũ
~~~

**Quy tắc rõ ràng cho ví dụ này:**

- Khi **V1 vẫn có thể ghi**, `delivery_note` là **nguồn có thẩm quyền** cho đường đọc của V2.
- V2 được phép dual-write để tạo dữ liệu mới, nhưng **chưa tin** `shipping_note` làm nguồn đọc.
- Sau khi chắc chắn không còn writer V1, chạy lượt đồng bộ cuối rồi mới chuyển đọc sang `shipping_note`.

Một giải pháp khác là trigger phía DB đồng bộ cột cũ sang cột mới khi V1 ghi. Nhưng trigger phức tạp hơn, phải quy định hướng ưu tiên khi cả hai cột bị cập nhật, xử lý giá trị NULL, tránh đệ quy và kiểm thử tất cả đường ghi. Không thêm trigger chỉ vì muốn cắt bỏ thời gian overlap mà chưa đánh giá rủi ro.

### 5.2. Tại sao `COALESCE(shipping_note, delivery_note)` chưa đủ?

Trong khi V1 còn ghi, `shipping_note` có thể **khác NULL nhưng đã cũ**. Khi đó:

~~~sql
SELECT COALESCE(shipping_note, delivery_note)
FROM orders
WHERE tenant_id = ? AND id = ?;
~~~

sẽ chọn giá trị mới-cột nhưng lỗi thời, không chọn cột cũ vừa được V1 cập nhật. `COALESCE` chỉ giải quyết **thiếu dữ liệu NULL**, không giải quyết **nguồn nào là phiên bản đúng nhất**.

Trong giai đoạn V1 có thể ghi, đọc trực tiếp cột cũ theo giao thức rõ ràng đáng tin hơn. Nếu buộc phải đọc new-first, cần cơ chế đồng bộ/phiên bản được chứng minh đúng dưới concurrent writes, chứ không chỉ một fallback đơn giản.

## 6. Java/JDBC: dual-write nguyên tử nhưng ranh giới vẫn rõ

Ví dụ Java 17 cho phiên bản V2:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Types;
import javax.sql.DataSource;

public final class OrderNoteRepositoryV2 {
    private final DataSource dataSource;

    public OrderNoteRepositoryV2(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean changeNote(
            long tenantId, long orderId, String note)
            throws SQLException {

        String sql = """
            UPDATE orders
            SET delivery_note = ?,
                shipping_note = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE tenant_id = ?
              AND id = ?
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            bindNullableText(statement, 1, note);
            bindNullableText(statement, 2, note);
            statement.setLong(3, tenantId);
            statement.setLong(4, orderId);

            // Ví dụ dùng một statement trong autocommit.
            // Với nghiệp vụ nhiều bảng, dùng transaction do service sở hữu.
            connection.setAutoCommit(true);
            return statement.executeUpdate() == 1;
        }
    }

    private static void bindNullableText(
            PreparedStatement statement, int index, String text)
            throws SQLException {
        if (text == null) {
            statement.setNull(index, Types.VARCHAR);
        } else {
            statement.setString(index, text);
        }
    }
}
~~~

Đây là lớp minh họa, không phải ứng dụng đầy đủ. Những giới hạn cần nhận thức:

- `DataSource` phải được cấu hình và quản lý vòng đời từ bên ngoài.
- `changeNote` chỉ xác nhận một hàng đã được cập nhật nếu statement và commit theo chế độ autocommit hoàn thành thành công; nếu `SQLException` do mất mạng xảy ra lúc driver chờ phản hồi, **kết quả ghi có thể chưa xác định**.
- Nếu service đang sở hữu transaction gồm nhiều SQL, repository không nên ép `autoCommit=true` như ví dụ; phải tham gia cùng transaction hiện tại. Có thể tách phiên bản JDBC cho connection đã được cấp.
- `WHERE tenant_id = ?` giới hạn phạm vi dữ liệu theo tenant nhưng **không thay thế xác thực và phân quyền**.
- Với optimistic locking, câu UPDATE có thể cần `AND version = ?` và tăng `version`; dual-write hai cột không tự ngăn lost update giữa các writer.
- Khi một kết nối lấy từ pool được đóng bằng `try-with-resources`, handle thường được trả về pool; không giữ connection dùng chung ở singleton.

Một ví dụ đường đọc V2 **trước read cutover**:

~~~java
String sql = """
    SELECT delivery_note
    FROM orders
    WHERE tenant_id = ?
      AND id = ?
    """;
~~~

Sau read cutover (khi không còn writer V1 và dữ liệu đã đồng bộ):

~~~java
String sql = """
    SELECT shipping_note
    FROM orders
    WHERE tenant_id = ?
      AND id = ?
    """;
~~~

Đường đọc được thay đổi bằng release hoặc feature flag có kiểm soát. Nếu dùng flag, cần quan sát trạng thái flag ở tất cả instance và đường batch/worker; **flag tắt ở controller chưa chứng minh mọi consumer đã đổi**.

### 6.1. Entity JPA/Hibernate cần chú ý điều gì?

Một entity V2 có thể map cả hai field:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    private Long id;

    @Column(name = "delivery_note")
    private String deliveryNote;

    @Column(name = "shipping_note")
    private String shippingNote;

    protected OrderEntity() {}

    public void changeNote(String note) {
        this.deliveryNote = note;
        this.shippingNote = note;
    }
}
~~~

Ví dụ chỉ thể hiện mapping hai cột, chưa phải entity hoàn chỉnh với tenant, constructor nghiệp vụ, transaction và optimistic version. Cần kiểm tra **SQL thực** của ORM: dirty checking, merge, bulk update, native query, batch job hoặc đường sửa field bằng reflection có thể không đi qua `changeNote()`.

Một `@PreUpdate` callback không thay thế việc kiểm tra mọi writer ngoài ORM. Trong giai đoạn nhiều version, một V1 có mapping một cột vẫn ghi cột cũ. Nếu ứng dụng dùng Spring Data JPA, `save()` cũng không cam kết tự dual-write trừ khi mapping và hành vi được thiết kế đúng.

## 7. Pha BACKFILL: xử lý dữ liệu cũ theo lô

Sau khi thêm cột, các hàng lịch sử có `shipping_note = NULL`. Nếu V2 đang đọc cột cũ, hệ thống vẫn hoạt động. Có thể chạy backfill **ngoài luồng request người dùng**, theo batch nhỏ.

### 7.1. Backfill cơ bản

Với một bảng nhỏ:

~~~sql
UPDATE orders
SET shipping_note = delivery_note
WHERE shipping_note IS DISTINCT FROM delivery_note;
~~~

PostgreSQL `IS DISTINCT FROM` so sánh cả giá trị NULL theo ngữ nghĩa xác định: hai NULL được xem là không khác nhau; NULL và chuỗi rỗng là khác nhau. Điều này phù hợp khi cần bảo toàn ghi chú tùy chọn, không thay NULL thành chuỗi rỗng một cách vô ý.

**Không chạy một UPDATE toàn bảng trên production lớn mà không đánh giá:** một transaction duy nhất có thể giữ khóa hàng lâu, tạo lượng WAL lớn, bloat, áp lực I/O, replication lag và tăng thời gian rollback nếu thất bại.

### 7.2. Chia lô trong PostgreSQL

Có thể chọn tối đa 500 hàng khác nhau, khóa hàng để phối hợp với writer, rồi cập nhật trong cùng statement:

~~~sql
WITH batch AS (
    SELECT id
    FROM orders
    WHERE shipping_note IS DISTINCT FROM delivery_note
    ORDER BY id
    LIMIT 500
    FOR UPDATE SKIP LOCKED
)
UPDATE orders AS o
SET shipping_note = o.delivery_note
FROM batch AS b
WHERE o.id = b.id;
~~~

Thực thi statement trong những transaction ngắn, lặp lại theo kế hoạch với tốc độ giới hạn, giám sát số hàng thay đổi và tải DB. Lệnh chạy minh họa giả định `id` là khóa chính duy nhất và `orders` chỉ có một nguồn dữ liệu nghiệp vụ.

**Điểm cần hiểu về đồng thời:**

- `FOR UPDATE SKIP LOCKED` tránh chờ những hàng đang bị khóa bởi transaction khác; batch có thể tạm bỏ qua hàng bận.
- Một UPDATE thường khóa hàng trong DB; khi V2 cùng cập nhật cả hai cột, thao tác hàng được serialize theo khóa DB thay vì hai writer sửa nửa chừng không phối hợp.
- Nếu V1 còn viết `delivery_note`, nó vẫn có thể sửa hàng **sau lượt backfill**. Khi đó `shipping_note` lại bị lệch.
- Vì vậy backfill có thể được thực thi nhiều lần, nhưng **chỉ được tuyên bố hoàn tất sau khi V1 đã ngừng ghi và lượt đối soát cuối đã chạy**.
- `SKIP LOCKED` không bảo đảm một lượt quét đã xét mọi hàng; cần lặp đến khi hội tụ và kiểm tra độc lập.
- Query lọc `IS DISTINCT FROM` trên bảng rất lớn có thể phải scan tốn kém mỗi batch; tùy workload, dùng khoảng ID/watermark, job queue hoặc phương án tracking để tránh quét lại toàn bộ bảng nhiều lần.

**Lưu ý cú pháp:** `SKIP LOCKED` là tính năng PostgreSQL; các DBMS khác có syntax và locking semantics riêng. Hãy kiểm thử trên engine/phiên bản sử dụng thật.

### 7.3. Backfill phải có khả năng chạy lại

Một job có thể bị dừng do deploy, lỗi kết nối hoặc timeout. Phương án an toàn cần:

- **Idempotent**: chạy lại không nhân đôi dữ liệu hoặc làm mất trạng thái mới.
- **Có progress**: đếm batch/hàng, lưu checkpoint nếu cần, không dùng offset dễ thay đổi làm bằng chứng duy nhất.
- **Giới hạn tài nguyên**: batch nhỏ, commit mỗi batch, có sleep/throttle và dừng khi DB quá tải.
- **Quan sát được**: số hàng còn lệch, số lỗi, WAL/replication lag, lock wait và thời gian dự kiến theo tiến độ thực.
- **Không ghi đè cập nhật mới**: xác định rõ cột có authority trong từng giai đoạn.

Nếu chuyển dữ liệu bằng phép biến đổi không đảo ngược, ví dụ tách một chuỗi tên thành nhiều trường có ngữ nghĩa khác nhau, phải xác định quy tắc làm sạch và xử lý ngoại lệ. Đừng suy rằng mọi `NULL`, chuỗi trống hoặc ký tự Unicode có thể được diễn dịch đúng bằng một câu SQL đơn giản.

## 8. Đồng thời giữa backfill và cập nhật người dùng

Giả sử V2 ghi cả hai cột nhưng một batch backfill vẫn đang chạy:

~~~text
T1: Backfill chọn order 501, giá trị cũ "Gọi trước"
T2: V2 muốn đổi thành "Giao cuối tuần"
T3: Backfill và V2 cạnh tranh khóa hàng trong DB
T4: DB tuần tự hóa hai UPDATE trên hàng theo thứ tự khóa
~~~

Nếu backfill viết `shipping_note = delivery_note` **bằng biểu thức đọc giá trị hàng tại thời điểm UPDATE trong DB**, còn V2 luôn viết hai cột bằng cùng một giá trị trong cùng UPDATE, trạng thái cuối có thể giữ được hai cột bằng nhau sau khi các giao dịch hoàn tất.

Ngược lại, **cách backfill sau đây nguy hiểm**:

~~~text
SELECT delivery_note ở T1 -> lấy "Gọi trước"
... chờ nhiều giây trong Java ...
UPDATE orders SET shipping_note = "Gọi trước" ở T5
~~~

Nếu người dùng đã đổi cả hai cột ở T3, backfill dùng giá trị lưu trong heap Java từ T1 có thể **ghi đè cột mới bằng bản cũ**. Không nên đưa dữ liệu cũ qua một hàng đợi chậm rồi cập nhật không có version guard.

Giải pháp cho backfill có phép biến đổi phức tạp thường cần:

1. Đọc kèm `version` hoặc `updated_at` có semantics phù hợp.
2. Khi ghi, dùng **conditional UPDATE** theo version/giá trị nguồn đã đọc và kiểm tra số hàng thay đổi.
3. Nếu có xung đột, tải lại nguồn và tính lại; không đè dữ liệu mới.
4. Dùng row lock với transaction ngắn khi phù hợp, tránh giữ khóa trong lúc gọi API ngoài.
5. Có quy trình kiểm chứng sau khi mọi writer cũ rời hệ thống.

Đối với `version` dùng để chống xung đột, mọi writer liên quan phải cập nhật và kiểm tra nó theo cùng quy tắc; một client SQL ngoài ORM bỏ qua version có thể làm chiến lược thiếu an toàn.

### 8.1. Source of truth theo từng giai đoạn

| Giai đoạn | Cột được dùng để quyết định giá trị đúng | Hệ quả |
| --- | --- | --- |
| V1 còn ghi | `delivery_note` | Không dùng `shipping_note` làm read source mặc dù đã backfill |
| Mọi V1 writer đã ngừng; V2 dual-write | Đồng bộ lần cuối từ `delivery_note` sang `shipping_note` | Sau kiểm chứng, có thể read cutover |
| V2 đã đọc mới, vẫn dual-write | `shipping_note` phục vụ read; `delivery_note` được giữ đồng bộ để rollback | Có thể quay về V1 nếu không có writer mới-only |
| V3 bắt đầu new-only | `shipping_note` | V1 không còn là rollback target an toàn |
| Đã contract | `shipping_note` | Cột cũ đã được xóa, rollback cần forward fix/migration mới |

**Đây là cam kết của kiến trúc rollout, không chỉ một convention trong code.** Cần quan sát và chặn đường ghi cũ trước khi thay authority.

## 9. READ CUTOVER: khi nào có thể tin cột mới?

Trước khi V2 chuyển từ đọc cũ sang đọc mới, xác nhận:

1. Không còn process V1 nhận traffic ghi: API, worker, job theo lịch, queue consumer, admin script, migration tool và batch integration đã được kiểm tra.
2. V2 đang dual-write đúng ở mọi đường cập nhật có thể sửa ghi chú.
3. Backfill cuối đã chạy sau khi writer cũ được drain.
4. Đã đối soát `shipping_note` và `delivery_note`, bao gồm NULL/chuỗi rỗng và các trường hợp biên.
5. Đã thử canary đọc cột mới và so sánh kết quả trong môi trường phù hợp.
6. Có kế hoạch rollback khi phát hiện sự khác biệt, vì hai cột vẫn đang tồn tại.

Câu SQL kiểm tra mức lệch:

~~~sql
SELECT COUNT(*) AS mismatched_rows
FROM orders
WHERE shipping_note IS DISTINCT FROM delivery_note;
~~~

Trên bảng lớn, `COUNT(*)` này có thể phải quét nhiều dữ liệu và cần chạy theo lịch phù hợp. Có thể kiểm tra theo dải ID, tenant, mẫu đại diện và so khớp tổng hợp; tuy nhiên **chỉ lấy mẫu không chứng minh tuyệt đối không còn hàng lệch**. Tiêu chí hoàn tất phải phù hợp mức rủi ro của dữ liệu.

Ví dụ so sánh một số hàng lệch để điều tra:

~~~sql
SELECT id, tenant_id, delivery_note, shipping_note
FROM orders
WHERE shipping_note IS DISTINCT FROM delivery_note
ORDER BY id
LIMIT 50;
~~~

Không đưa thông tin nhạy cảm của ghi chú vào log giám sát rộng rãi; cần hạn chế quyền xem dữ liệu và che hoặc hash nếu phù hợp.

### 9.1. Triển khai cutover bằng feature flag

Nếu sử dụng flag:

~~~text
read_from_shipping_note = false  (đọc cũ)
                              |
              Backfill/đối soát đạt
                              |
                              v
read_from_shipping_note = true   (đọc mới)
~~~

Flag nên có owner, phạm vi rõ (global/tenant/instance), audit thay đổi, metric và rollback procedure. Một số instance chưa nhận flag hoặc một job không dùng flag vẫn có thể đọc khác nhau; cần bảo đảm deployment/flag propagation đúng theo yêu cầu.

Vì V2 tiếp tục dual-write cả hai cột trong cửa sổ rollback, có thể tạm chuyển lại đọc cũ nếu phát hiện lỗi **trước khi V3 new-only xuất hiện**.

## 10. WRITE CUTOVER: bỏ ghi cũ mà không phá rollback

Đây là bước thường bị đánh giá thấp. Khi V3 chỉ ghi `shipping_note`, `delivery_note` sẽ không còn được cập nhật cho các request đó. Một bản V1 được rollback lại sẽ đọc dữ liệu cũ hoặc NULL.

Do đó, trước khi triển khai V3 new-only:

- Xác nhận quyết định **không còn rollback trực tiếp về V1** sau mốc này, trừ khi có cơ chế đồng bộ ngược đã được thiết kế và kiểm thử.
- Nếu cần rollback chức năng, chuẩn bị rollback về **V2 vẫn đọc cột mới** (và dual-write) khi schema cũ vẫn tồn tại.
- Đảm bảo không còn producer chỉ viết `delivery_note`.
- Cập nhật runbook, feature flag và trạng thái migration; đừng để đội vận hành dùng một bản build cũ không tương thích dữ liệu mới.

Trong ví dụ, vì cột cũ được phép NULL, V3 có thể thực hiện:

~~~sql
UPDATE orders
SET shipping_note = ?,
    updated_at = CURRENT_TIMESTAMP
WHERE tenant_id = ?
  AND id = ?;
~~~

Nếu cột cũ vốn có `NOT NULL` hoặc constraint khác, **new-only INSERT có thể vẫn thất bại trước khi xóa cột**. Khi đó cần một pha expand bổ sung để nới ràng buộc cũ theo cách an toàn, đồng thời kiểm tra các version còn tồn tại. Không bỏ qua constraint chỉ vì bản code mới đã thay đổi.

V3 có thể được triển khai khi các V2 vẫn còn chạy: V2 đọc mới và dual-write, V3 đọc mới và new-only, nên cả hai có thể chạy với **schema hai cột**. Nhưng nếu rollback V3 về V2, V2 đọc mới nên vẫn đúng; **rollback về V1 không còn an toàn về dữ liệu**.

## 11. CONTRACT: khi nào mới được xóa cột cũ?

Chỉ khi tất cả điều kiện sau được đáp ứng:

- Mọi instance V1 và V2 đã ngừng; kể cả worker theo lịch, delayed queue, batch, admin và các bản canary.
- Không có SQL trực tiếp/ORM mapping/view/report/BI tool/CDC consumer còn dùng `delivery_note`.
- V3 đã chạy ổn định và mọi thao tác dùng `shipping_note` duy nhất.
- Có thời gian theo dõi đủ lâu cho đường ít được gọi và rollback window đã hết.
- Backup, PITR và kế hoạch xử lý sự cố được kiểm tra theo yêu cầu nghiệp vụ.
- Đội ngũ đã chấp nhận rằng **drop là bước khó đảo ngược ngay lập tức**.

Migration cuối:

~~~sql
-- Migration M2: chỉ thực thi sau khi đã xác minh toàn bộ dependency.
ALTER TABLE orders
DROP COLUMN delivery_note;
~~~

PostgreSQL thường thực hiện việc drop metadata cột theo cơ chế riêng, nhưng câu `ALTER TABLE` vẫn cần khóa phù hợp và có thể chờ transaction dài. Không suy rằng vì DDL ngắn nên không ảnh hưởng production. Với bảng lớn, cần đánh giá bloat/khả năng thu hồi dung lượng vật lý và kế hoạch bảo trì riêng.

**Một khi đã DROP, không thể rollback bằng cách đơn giản đổi tên cột mới thành cột cũ** nếu các bản ghi phát sinh sau write cutover có ngữ nghĩa/schema khác hoặc dữ liệu đã được biến đổi mất thông tin. Khi cần phục hồi, có thể phải viết migration tiến về phía trước, phục hồi từ backup phù hợp hoặc dùng cơ chế đồng bộ ngược được chuẩn bị sẵn.

### 11.1. Contract cũng có thể là xóa API và event cũ

Expand–contract không chỉ áp dụng cho bảng:

- **API:** cho phép field request mới đồng thời vẫn chấp nhận field cũ, chuyển client, rồi ngừng hỗ trợ field cũ.
- **Event schema:** producer phát format tương thích; consumer nâng cấp; sau đó mới loại field/version cũ.
- **Cache key:** trong giai đoạn chuyển đổi có thể đọc/ghi theo hai key với protocol rõ ràng; phải kiểm soát stale/invalidations.
- **Index:** thêm index mới, chuyển truy vấn và quan sát plan, rồi loại index cũ nếu không còn cần.
- **Service contract:** có consumer triển khai độc lập nên thời điểm contract phải theo nhịp cập nhật của consumer, không chỉ theo deployment API.

Nếu cả DB và event consumer cùng được thay đổi, cần lập ma trận tương thích **đa chiều**, vì rollback ứng dụng không tự rollback event đã phát hoặc consumer đã xử lý.

## 12. DDL online: lock, chỉ mục và giới hạn kỹ thuật

Cụm từ “zero-downtime migration” nên được hiểu là **mục tiêu triển khai không gây gián đoạn vượt SLO**, không phải “DDL không bao giờ giữ khóa”.

### 12.1. Những thao tác có rủi ro khác nhau

| Thao tác | Rủi ro chính | Cách đánh giá |
| --- | --- | --- |
| Thêm cột nullable không default | Khóa DDL ngắn nhưng có thể chờ khóa lâu | Lock timeout, transaction dài, thời điểm rollout |
| Thêm cột có default phức tạp | Có thể rewrite/backfill tốn tài nguyên tùy DBMS/phiên bản | Xác minh cơ chế của engine, benchmark |
| Đổi kiểu cột | Có thể rewrite dữ liệu và khóa lâu | Expand sang cột mới và backfill nếu cần |
| Tạo chỉ mục trên bảng lớn | CPU/I/O, WAL, lock và thời gian build | Chọn phương án online hỗ trợ; đo tải thực |
| Thêm UNIQUE | Dữ liệu trùng, lock/index build | Dọn dữ liệu, tạo unique index theo quy trình phù hợp |
| Thêm NOT NULL | Dữ liệu cũ còn NULL, scan/lock | Backfill và validate trước |
| Drop cột/bảng | Code cũ hỏng, mất dữ liệu/khả năng rollback | Contract sau xác minh dependency |
| Rename cột trực tiếp | Query cũ không còn chạy | Dùng hai cột trong giai đoạn overlap |

### 12.2. Ví dụ `CREATE INDEX CONCURRENTLY`

Nếu đường đọc mới thường tìm theo `tenant_id` và `updated_at`, chỉ mục có thể là ứng viên:

~~~sql
CREATE INDEX CONCURRENTLY idx_orders_tenant_updated
ON orders (tenant_id, updated_at DESC, id DESC);
~~~

Trong PostgreSQL, `CREATE INDEX CONCURRENTLY` giảm mức chặn ghi so với tạo chỉ mục thông thường, nhưng:

- Không chạy được bên trong một transaction block thông thường.
- Có thể chạy lâu, chờ transaction và sử dụng đáng kể CPU/I/O/WAL.
- Nếu build thất bại, có thể để lại index ở trạng thái invalid cần kiểm tra và xử lý.
- Không nên tạo index chỉ vì thêm cột; chỉ mục phải phục vụ **truy vấn cụ thể và kế hoạch thực thi thực tế**.

Nếu dùng migration framework mặc định bọc mỗi migration trong transaction, phải cấu hình đúng cho migration chứa `CONCURRENTLY`, theo phiên bản framework. Không đặt lệnh này vào `BEGIN ... COMMIT` như ví dụ ADD COLUMN.

### 12.3. Bổ sung ràng buộc theo từng bước

Với ràng buộc có thể được tạo ở trạng thái chưa validate, PostgreSQL hỗ trợ một số đường đi như `ADD CONSTRAINT ... NOT VALID` rồi `VALIDATE CONSTRAINT` cho loại constraint phù hợp. Điều này giúp phân tách bước đưa quy tắc mới vào hệ thống với bước quét xác nhận dữ liệu lịch sử.

Không phải mọi constraint đều hỗ trợ `NOT VALID` như nhau: ví dụ UNIQUE constraint không đơn giản dùng cú pháp đó. Với UNIQUE trên bảng lớn, có thể xem xét **tạo unique index concurrently** trước, kiểm tra dữ liệu trùng, rồi gắn constraint khi thỏa điều kiện hỗ trợ. Cần kiểm tra chính xác trên PostgreSQL phiên bản đang dùng.

Đừng thêm constraint vào giữa rolling deployment nếu V1 vẫn có thể tạo những hàng không phù hợp với constraint đó. Contract bao gồm cả **thắt chặt quy tắc ghi** sau khi mọi writer đã tương thích.

## 13. Triển khai có điều phối với nhiều bản Java

Một kế hoạch khả thi cho hệ thống nhiều instance:

| Release/mốc | Database | Ứng dụng | Kiểm chứng |
| --- | --- | --- | --- |
| R0 | Chỉ `delivery_note` | V1 | Baseline metrics và backup |
| R1 | Thêm `shipping_note` nullable | V1 vẫn hoạt động | Không có SQL error từ V1; lock/DDL an toàn |
| R2 | Hai cột | Rolling V2: đọc cũ, dual-write | V1/V2 đồng thời thành công; SQL/metrics dual-write đúng |
| R3 | Hai cột, backfill theo lô | V2 + có thể còn V1 | Backfill idempotent; không quá tải; chưa read cutover |
| R4 | Hai cột, dữ liệu đã đồng bộ | Chỉ V2; không còn V1 writer | Lượt backfill cuối, mismatches = 0 |
| R5 | Hai cột | V2 đọc mới, dual-write | Canary/read parity, rollback về đọc cũ còn được |
| R6 | Hai cột | Rolling V3 đọc mới, ghi mới-only | Không rollback về V1; V2/V3 cùng chạy an toàn |
| R7 | Hai cột | Chỉ V3 | Không còn query/mapping/consumer cũ; hết rollback window |
| R8 | Chỉ `shipping_note` | V3 | DDL drop thành công, theo dõi error và traffic |

Nếu một bước không đạt điều kiện, **dừng tại pha đó**, điều tra nguyên nhân rồi tiếp tục. Không sử dụng một pipeline bắt buộc phải chạy hết R1–R8 trong một lần bất chấp trạng thái ứng dụng và dữ liệu.

### 13.1. Điểm không thể rollback dễ dàng

Rollback thường có ba mức:

- **Trước read cutover:** có thể chuyển lại V1/V2 đọc cũ nếu code và schema vẫn còn tương thích.
- **Sau read cutover nhưng trước V3 new-only:** V2 dual-write giữ hai cột đồng bộ, nên rollback đọc về cũ vẫn là phương án có thể xem xét.
- **Sau khi V3 new-only đã ghi dữ liệu:** V1 không còn là rollback target an toàn; các hàng mới/sửa có thể chưa đồng bộ về `delivery_note`.
- **Sau DROP:** chỉ code không phụ thuộc cột cũ mới hoạt động; phục hồi thường đòi migration/restore bổ sung.

Một “rollback deployment” không đồng nghĩa “rollback dữ liệu” hoặc “rollback schema”. Đó là ba hoạt động khác nhau và cần runbook độc lập.

## 14. Observability: đo đúng trước khi tuyên bố hoàn tất

Đề xuất một bộ chỉ số theo pha:

| Nhóm | Chỉ số | Ý nghĩa |
| --- | --- | --- |
| Compatibility | SQL error: undefined_column, missing table, mapping error | Còn code sử dụng schema không phù hợp? |
| Deployment | Số instance V1/V2/V3, job/consumer còn chạy | Có thực sự hết writer cũ chưa? |
| Backfill | Số hàng xử lý/lô, hàng còn lệch, tốc độ, lỗi | Dữ liệu đã hội tụ chưa? |
| Database | Lock wait, transaction age, WAL bytes, replication lag | Migration có làm hệ thống mất ổn định không? |
| API | p95/p99 latency, lỗi ghi/đọc, tính đúng đắn response | Thay đổi schema ảnh hưởng người dùng ra sao? |
| Data quality | Null/empty distinction, mismatched notes, sample parity | Phép chuyển đổi có giữ nguyên ý nghĩa không? |
| Rollback | Số writer new-only, khả năng V2/old đọc đúng | Còn rollback target nào hợp lệ? |
| Security | Cross-tenant access, log chứa dữ liệu nhạy cảm | Migration có làm lộ dữ liệu hoặc bỏ sót điều kiện tenant? |

Trong PostgreSQL, có thể quan sát lock và transaction đang chạy bằng `pg_stat_activity`, `pg_locks` theo quyền được cấp. Nhưng không dựa chỉ vào database session để biết mọi **code path chưa chạy** có phụ thuộc cột cũ hay không. Cần inventory từ source, logs, metrics, query statistics, job scheduler và consumer.

Không log giá trị `delivery_note` và `shipping_note` hàng loạt vì chúng có thể chứa địa chỉ hoặc thông tin cá nhân. Có thể dùng so sánh trong DB, thống kê tổng hợp và truy cập chẩn đoán có kiểm soát.

## 15. Lỗi kết nối và restart trong lúc migration

Expand–contract không loại bỏ lỗi phân tán hoặc sự cố nền tảng:

- **Migration DDL timeout:** có thể chưa thay đổi schema; phải kiểm tra migration state trước khi chạy lại.
- **Backfill job chết giữa chừng:** transaction đang thực thi có thể rollback; các batch đã commit vẫn tồn tại. Job phải resume/idempotent.
- **Mất phản hồi COMMIT:** một batch có thể đã commit nhưng worker không biết. Chạy lại logic an toàn phải dựa vào điều kiện dữ liệu, không chỉ số batch đã ghi nhớ trên client.
- **Replica lag:** đường đọc ở replica có thể chưa thấy cột/dữ liệu theo kỳ vọng; cần kiểm soát promotion/replication và đúng nguồn đối soát.
- **Connection pool chứa session lâu:** prepared statement, kế hoạch truy vấn hay cached metadata có thể cần refresh theo driver/provider; thường rollout/reconnect có kiểm soát tốt hơn giả định mọi session cập nhật tức thì.
- **Failover khi backfill:** cần dừng/khởi động lại job đúng authority, giữ lại tiến độ đã commit và kiểm tra duplicate processing.

Cần xác định rõ RPO/RTO và kiểm thử backup/restore cho dữ liệu nghiệp vụ quan trọng trước khi drop hoặc transform mất thông tin. Backup không phải lý do để bỏ kiểm chứng; restore từ backup có thể làm mất những giao dịch mới hơn mốc sao lưu.

## 16. Kiểm thử expand–contract theo các pha

### 16.1. Test tương thích schema và code

| Schema | Phiên bản | Tình huống | Kỳ vọng |
| --- | --- | --- | --- |
| S0 chỉ cũ | V1 | Đọc/ghi đơn bình thường | PASS |
| S1 hai cột | V1 | Đọc/ghi cột cũ | PASS |
| S1 hai cột | V2 | Đọc cũ/ghi đôi | PASS |
| S1 hai cột | V1 + V2 | Hai request đồng thời sửa một hàng | Không mất cập nhật theo cơ chế concurrency đã chọn |
| S1 hai cột | V1 cập nhật sau backfill | So sánh hai cột | Có thể lệch; V2 vẫn đọc cũ |
| S2 đồng bộ xong | Chỉ V2 | Read cutover | Đọc mới chính xác, dual-write còn hoạt động |
| S2 hai cột | V2 + V3 | Rolling new-only | Đọc mới đúng, không còn dựa trên old |
| S3 chỉ mới | V3 | Đọc/ghi | PASS |
| S3 chỉ mới | V1 hoặc V2 | Gọi query cũ | **Expected fail**; không cho chạy version này ở production |

### 16.2. Test race giữa backfill và writer

Dùng hai connection PostgreSQL độc lập hoặc một fake DAO có latch:

1. Chuẩn bị một hàng có `delivery_note = "A"` và `shipping_note = NULL`.
2. Cho backfill bắt đầu và bị chặn tại điểm đã lựa chọn trong test.
3. V2 cập nhật cả hai cột thành `"B"`, commit.
4. Cho backfill chạy tiếp.
5. Đọc cả hai cột trên connection mới; kiểm tra kết quả không bị đưa về `"A"`.
6. Lặp test khi V1 chỉ sửa cột cũ trong overlap để chứng minh tại sao phải đồng bộ cuối **sau khi drain V1**.

Phân biệt test backfill SQL lấy giá trị nguồn trong UPDATE với test backfill kiểu Java đọc giá trị cũ rồi cập nhật về sau. Hai kiểu có nguy cơ race khác nhau.

### 16.3. Test rollback và sự cố

- Deploy V2 rồi rollback V1: khi cả hai vẫn dual-write và old canonical, dữ liệu được đọc đúng không?
- Read cutover xong rồi chuyển lại đọc cũ: hai cột còn đồng bộ trong rollback window không?
- V3 đã ghi new-only: có cơ chế ngăn rollback V1 hoặc cảnh báo rõ ràng không?
- DDL chờ một transaction dài: `lock_timeout` có giúp dừng thay vì chặn toàn hệ thống không?
- Backfill chạy nửa đường rồi crash: lặp lại có đưa dữ liệu đến trạng thái đúng không?
- Bảng có hàng `NULL` và chuỗi rỗng: có bị chuyển đổi mất thông tin không?
- Batch job/CDC consumer dùng field cũ: có được nhận diện trước contract không?
- Khi network timeout lúc commit, hệ thống có đối soát trạng thái thay vì ghi đôi hay không?

Cần test trên database và driver thực, đặc biệt nếu dùng JPA/Hibernate: provider có thể sinh SQL/DDL khác kỳ vọng và metadata cache có thể cần kiểm tra.

## 17. Những sai lầm thường gặp

**“Migration RENAME COLUMN chạy nhanh là zero downtime.”** Dù DDL ngắn, ứng dụng cũ vẫn gửi SQL tới tên cột đã biến mất.

**“Thêm cột xong có thể chuyển toàn bộ V2 sang đọc mới.”** Khi V1 còn ghi cột cũ, dữ liệu mới có thể stale dù không NULL.

**“`COALESCE(new, old)` giải quyết mọi trường hợp chuyển đổi.”** Nó không phân biệt một giá trị new đã cũ với giá trị old vừa được V1 commit.

**“Dual-write bằng hai transaction là đủ.”** Nếu một transaction commit và transaction kia fail, dữ liệu phân kỳ.

**“Backfill chạy xong một lượt nghĩa là dữ liệu cuối đã đầy đủ.”** Old writer có thể tiếp tục ghi sau lượt backfill và tạo mismatch mới.

**“Backfill bằng Java cứ SELECT rồi UPDATE sau cũng an toàn.”** Giá trị đọc từ trước có thể ghi đè cập nhật mới nếu không có điều kiện version/locking.

**“Mọi cột mới phải NOT NULL ngay.”** Dữ liệu lịch sử và phiên bản cũ có thể chưa cung cấp giá trị; cần tiến hóa constraint theo pha.

**“Có thể rollback code sau bất cứ bước nào.”** Khi V3 đã new-only, rollback về V1 có thể đọc dữ liệu lỗi thời; sau DROP, V1/V2 không còn tương thích.

**“DROP COLUMN không làm mất thời gian vì chỉ đổi metadata.”** DDL vẫn cần khóa và có thể chờ; khả năng rollback, consumer và dữ liệu mới là rủi ro lớn hơn thời gian CPU của DDL.

**“Có backup thì drop bất kỳ lúc nào cũng sửa được.”** Restore tốn thời gian và có thể bỏ mất giao dịch sau mốc sao lưu; cần RPO/RTO và quy trình kiểm chứng.

**“Nếu API mới hoạt động thì không còn ai dùng cột cũ.”** Job đêm, báo cáo, CDC và consumer chạy theo lịch có thể vẫn sử dụng cột cũ.

**“Tool migration tự bảo đảm data correctness.”** Flyway/Liquibase giúp quản lý version thực thi; lựa chọn authority, dual-write, data transformation và rollout vẫn phải do thiết kế nghiệp vụ quyết định.

## 18. Bài tập vận dụng

**Bài 1 — thiết kế rollout.** Cho V1 đọc/ghi `orders.delivery_note`, cần đổi thành `shipping_note` mà hệ thống có 10 instance và batch job chạy mỗi giờ. Hãy viết thứ tự expand, V2, backfill, read cutover, V3, contract; nêu bằng chứng cần có trước mỗi bước.

**Bài 2 — tìm lỗi trong phương án.** Nhóm triển khai thêm `shipping_note`, backfill một lượt, sau đó cho V2 đọc `COALESCE(shipping_note, delivery_note)` ngay khi V1 còn hoạt động. Hãy dựng lịch V1 UPDATE sau backfill và chỉ ra tại sao có stale read.

**Bài 3 — sửa JDBC.** Một service gọi hai lệnh `UPDATE delivery_note` và `UPDATE shipping_note` trên hai connection autocommit riêng. Hãy viết lại thành một UPDATE hai cột trong một transaction, bind cả NULL và kiểm tra số hàng bị ảnh hưởng.

**Bài 4 — batch an toàn.** Với bảng vài triệu hàng, thiết kế backfill có kích thước batch, commit, retry, checkpoint, giới hạn WAL/replication lag và điều kiện dừng. Nêu điểm khác nhau giữa idempotent SQL backfill và backfill Java đọc một giá trị rồi ghi lại sau.

**Bài 5 — ma trận rollback.** Giả sử V1 chỉ đọc old, V2 dual-write, V3 new-only. Với từng trạng thái R1, R5, R6 và R8 trong bảng triển khai, xác định bản rollback nào an toàn về schema **và dữ liệu**. Trình bày mốc phải cấm rollback V1.

**Bài 6 — kiểm chứng contract.** Liệt kê các consumer có thể dùng `delivery_note` ngoài HTTP API; nêu chỉ số hoặc bằng chứng cần thu thập để xác nhận không còn phụ thuộc. Tại sao chỉ search source code chưa chắc đủ?

**Bài 7 — tiến hóa ràng buộc.** Một cột mới bắt buộc phải có ở mọi hàng sau triển khai cuối. Hãy đề xuất cách thêm nullable, backfill, kiểm tra, cập nhật writer và thắt chặt NOT NULL. Nếu bảng có nhiều triệu hàng, cần xem lock/validation thế nào?

**Bài 8 — index và schema migration.** Bảng lớn cần index mới khi chuyển query. So sánh tạo index thông thường với `CREATE INDEX CONCURRENTLY` ở PostgreSQL. Vì sao không được đặt lệnh concurrently trong transaction block và cần xử lý invalid index khi thất bại?

## Ghi nhớ

**Expand–contract không đơn thuần là một mẹo chia DDL thành hai lệnh.** Đây là một giao thức chuyển đổi giữa **dữ liệu, phiên bản ứng dụng và các consumer**: mở rộng schema theo cách tương thích, cho code cũ/mới cùng tồn tại, giữ nguồn sự thật rõ ràng, backfill và đối soát, chuyển đọc rồi ghi, cuối cùng mới xóa cấu trúc cũ.

Với ứng dụng Java, hãy đặc biệt kiểm tra hành vi JDBC/ORM trong rolling deployment, tính nguyên tử của dual-write, race giữa backfill và writer cũ, tính đúng đắn khi rollback, giới hạn khóa DDL và chi phí WAL/replication. **Chỉ contract khi đã có bằng chứng không còn dependency cũ và đã chấp nhận điểm không thể rollback trực tiếp**. Một migration được coi là thành công khi dữ liệu vẫn đúng và dịch vụ vẫn đáp ứng hợp đồng trong toàn bộ quá trình tiến hóa, không chỉ khi câu SQL chạy xong.
