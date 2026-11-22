# Tương thích khi nhiều phiên bản ứng dụng chạy đồng thời

Khi triển khai phiên bản mới của một dịch vụ Java theo kiểu rolling deployment, các instance cũ và mới có thể cùng phục vụ request trong nhiều phút, thậm chí lâu hơn. Trong thời gian đó, cả hai phiên bản cùng truy cập **một cơ sở dữ liệu**, nhưng không nhất thiết cùng kỳ vọng về tên cột, giá trị enum, ràng buộc, định dạng sự kiện hoặc cách ghi dữ liệu. Một thay đổi schema hợp lệ ở môi trường thử nghiệm vẫn có thể làm production ngừng hoạt động nếu nó phá vỡ phiên bản đang chạy.

Bài học thuộc chương **Tiến hóa dữ liệu** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Người học thiết kế tầng persistence cho ứng dụng Java từ mô hình dữ liệu, lược đồ, truy vấn, chỉ mục và giao dịch đến cô lập, xử lý lỗi kết nối, bảo mật, sao lưu và hiệu năng. Chủ đề này tập trung vào **hợp đồng tương thích giữa nhiều phiên bản ứng dụng với dữ liệu dùng chung**, sử dụng PostgreSQL, JDBC, JPA/Hibernate và quy trình migration làm ví dụ. Những câu SQL và thứ tự rollout cần được kiểm tra theo phiên bản DBMS và công cụ triển khai thực tế trước khi áp dụng vào production.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích vì sao **rolling deployment, blue-green deployment, canary, rollback và consumer chạy chậm** tạo ra khoảng thời gian nhiều phiên bản cùng tồn tại.
- Phân biệt **tương thích đọc, tương thích ghi, tương thích schema và tương thích ý nghĩa dữ liệu**.
- Thiết kế lộ trình **expand → migrate/backfill → switch → contract** thay vì thay đổi phá vỡ hợp đồng trong một lần triển khai.
- Xây dựng **ma trận tương thích** của ứng dụng cũ/mới với schema và dữ liệu, bao gồm cả tình huống rollback.
- Nhận diện các rủi ro của **đổi tên cột, NOT NULL, enum, giá trị mặc định, dual-write, bulk update, cache, sự kiện và API**.
- Triển khai ví dụ đổi tên trường bằng SQL và Java với các giai đoạn đọc/ghi rõ ràng.
- Tổ chức migration dữ liệu theo lô, kiểm soát cạnh tranh, theo dõi tiến độ và đặt điều kiện đóng giai đoạn an toàn.
- Kiểm thử nhiều phiên bản đồng thời và biết thời điểm **không còn thể rollback chỉ bằng cách triển khai lại binary cũ**.

## 2. Vì sao nhiều phiên bản có thể cùng truy cập một database?

Hình dung hệ thống có bốn instance API dùng chung PostgreSQL:

~~~text
Load balancer
  |
  +-- API A: version 1.8  ----+
  +-- API B: version 1.8  ----+--> PostgreSQL primary
  +-- API C: version 1.9  ----+        |
  +-- API D: version 1.9  ----+        +--> replica/cache/consumers
~~~

Trong quá trình deploy, phiên bản 1.8 vẫn có thể đọc và ghi trong khi 1.9 đã chạy. Không chỉ deployment kiểu rolling mới có khoảng chồng lấn:

- **Canary:** một tỷ lệ nhỏ request được chuyển sang bản mới; phần lớn vẫn ở bản cũ.
- **Blue-green:** hai cụm ứng dụng có thể cùng hoạt động trong thời gian kiểm thử/chuyển traffic.
- **Scale-down hoặc shutdown chậm:** instance cũ đang giữ request, transaction hoặc job chưa hoàn tất.
- **Rollback:** binary cũ được đưa trở lại sau khi schema đã thay đổi.
- **Worker/consumer:** batch, scheduled job, message consumer hoặc công cụ BI có thể triển khai chậm hơn API.
- **Mobile/offline clients:** hợp đồng API hoặc sự kiện có thể còn được dùng lâu hơn một vòng triển khai backend.

Vì vậy, **“đã deploy code mới” không có nghĩa tất cả đường đọc/ghi đã dùng hợp đồng mới**. Cần biết chính xác những bên nào còn phụ thuộc vào dữ liệu cũ.

## 3. Định nghĩa tương thích ở đúng phạm vi

Một hệ thống tiến hóa an toàn phải trả lời hai hướng:

1. **Ứng dụng cũ có tiếp tục hoạt động với schema/dữ liệu mới không?**
2. **Ứng dụng mới có hoạt động khi dữ liệu vẫn được ứng dụng cũ tạo ra không?**

| Loại tương thích | Câu hỏi kiểm tra | Ví dụ lỗi |
| --- | --- | --- |
| **Schema đọc** | SQL cũ còn tìm thấy bảng/cột/kiểu mong đợi không? | DROP COLUMN khi binary cũ vẫn SELECT cột đó |
| **Schema ghi** | INSERT/UPDATE cũ còn thỏa constraint và default mới không? | Thêm cột NOT NULL không có default mà INSERT cũ không gửi giá trị |
| **Định dạng dữ liệu** | Bản mới đọc được dữ liệu do bản cũ tạo, và ngược lại không? | Đổi JSON từ chuỗi sang object nhưng consumer cũ chỉ hiểu chuỗi |
| **Ngữ nghĩa** | Giá trị mới có ý nghĩa mà code cũ xử lý đúng không? | Thêm trạng thái đơn hàng mà enum Java cũ không biết |
| **Giao dịch và đồng thời** | Hai phiên bản cùng ghi có làm sai bất biến không? | Một bản dual-write, bản kia ghi một cột khiến hai cột lệch nhau |
| **Cache/sự kiện** | Cache, projection và consumer cũ còn hiểu dữ liệu mới không? | Event mới bỏ trường mà consumer cũ đang yêu cầu |
| **Rollback** | Có thể quay lại bản cũ mà không mất hoặc hiểu sai dữ liệu mới không? | Bản mới ghi giá trị không thể biểu diễn trong schema cũ |

**Thay đổi không làm SQL báo lỗi chưa chắc đã tương thích nghiệp vụ.** Ví dụ mã cũ nhận giá trị trạng thái mới là **UNKNOWN** rồi âm thầm coi đơn đã hoàn thành: ứng dụng vẫn chạy nhưng kết quả sai. Tương thích phải được kiểm chứng cả ở tầng **hành vi**.

## 4. Ma trận phiên bản là một phần của kế hoạch triển khai

Đừng chỉ kiểm thử “code mới + schema mới”. Khi rolling deployment, ít nhất các cặp sau có thể tồn tại:

| Phiên bản ứng dụng | Schema chưa migrate | Schema đã mở rộng | Schema đã xóa phần cũ |
| --- | --- | --- | --- |
| **N-1 (cũ)** | Thường hoạt động | **Bắt buộc hoạt động** trong khoảng chồng lấn | Có thể hỏng; chưa được contract khi còn N-1 |
| **N (chuyển tiếp)** | Phụ thuộc tính năng đã dùng | Phải hoạt động | Chỉ an toàn nếu không còn truy cập phần cũ |
| **N+1 (đích)** | Thường không được bảo đảm | Có thể hoạt động theo cờ chuyển đổi | Hoạt động nếu dữ liệu đã chuyển đổi đúng |

Ma trận thực tế nên chi tiết hơn một bảng ba cột. Cần kiểm tra cả:

- **Bản cũ đọc dữ liệu do bản mới ghi**.
- **Bản mới đọc dữ liệu do bản cũ ghi**.
- **Hai bản cùng ghi một hàng dưới tải cạnh tranh**.
- **Rollback code nhưng không rollback schema**.
- **Dữ liệu trong bản sao, cache, job, sự kiện chưa được xử lý**.

Một quy tắc triển khai hữu ích: **mỗi trạng thái trung gian được phép xuất hiện trong production đều phải được kiểm chứng**. Không chấp nhận kế hoạch chỉ đúng nếu mọi service chuyển phiên bản trong cùng một mili giây.

## 5. Quy trình expand – migrate – contract

Đây là mẫu tiến hóa schema nhằm giữ tương thích trong khi các binary cùng tồn tại:

~~~text
Giai đoạn 0: Schema và app cũ
        |
        v
EXPAND: Thêm cấu trúc mới, giữ nguyên cấu trúc cũ
        |
        v
DEPLOY: App chuyển tiếp đọc/ghi theo hợp đồng cũ và mới
        |
        v
MIGRATE: Chuyển dữ liệu hiện có, kiểm tra sai lệch
        |
        v
SWITCH: Chỉ đọc/ghi dữ liệu mới sau khi mọi writer cũ đã dừng
        |
        v
CONTRACT: Xóa cấu trúc cũ sau khi không còn bất kỳ consumer nào dùng
~~~

Ba ý chính:

**Expand** ưu tiên thay đổi cộng thêm và tương thích, chẳng hạn thêm cột nullable hoặc bảng mới. Đây chưa phải lúc xóa cột cũ.

**Migrate** có thể bao gồm đổi cách ứng dụng ghi dữ liệu, backfill hàng cũ và đối soát. Không mặc định một migration SQL chạy nhanh sẽ giải quyết toàn bộ vấn đề nếu writer cũ vẫn đang cập nhật.

**Contract** chỉ thực hiện khi có bằng chứng mọi binary, job, report, cache/projection và đường rollback được chấp nhận đã ngừng dùng hợp đồng cũ. Thao tác xóa là điểm dễ trở thành **không thể rollback bằng binary cũ**.

Tùy quy mô, một thay đổi logic có thể cần nhiều release ứng dụng và nhiều migration DB. Đó là thiết kế chủ động, không phải lỗi vì chưa “dọn sạch schema” trong cùng sprint.

## 6. Ví dụ xuyên suốt: đổi tên cột mà không gián đoạn

Giả sử bảng **customer_profiles** có trường **display_name**. Đội sản phẩm muốn dùng tên mới **public_name** ở lớp dữ liệu. Hệ thống có cả API và worker đang chạy phiên bản cũ.

Lược đồ ban đầu:

~~~sql
CREATE TABLE customer_profiles (
    tenant_id    BIGINT NOT NULL,
    customer_id  BIGINT NOT NULL,
    display_name TEXT NOT NULL,
    version      BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, customer_id)
);
~~~

Phiên bản cũ **V1**:

~~~sql
-- Đọc:
SELECT display_name
FROM customer_profiles
WHERE tenant_id = ? AND customer_id = ?;

-- Ghi:
UPDATE customer_profiles
SET display_name = ?,
    version = version + 1
WHERE tenant_id = ? AND customer_id = ?
  AND version = ?;
~~~

**Không đổi ngay tên cột bằng RENAME COLUMN rồi deploy V2**. Nếu PostgreSQL đã đổi tên nhưng một instance V1 còn SELECT/UPDATE **display_name**, request cũ sẽ lỗi.

Một kế hoạch tương thích sử dụng các phiên bản ứng dụng:

| Ứng dụng | Đọc trường nào? | Ghi trường nào? | Mục đích |
| --- | --- | --- | --- |
| **V1 (legacy)** | display_name | display_name | Hành vi đang chạy |
| **V2 (chuyển tiếp)** | display_name | **cả hai cột trong cùng UPDATE/INSERT** | Chạy cùng V1, giữ nguồn đọc cũ |
| **V3 (đã chuyển đọc)** | public_name | **cả hai cột** | Chạy cùng V2 sau khi V1 dừng và reconcile |
| **V4 (mới)** | public_name | public_name | Chạy cùng V3 sau khi ràng buộc cột cũ được nới an toàn |

**Lưu ý:** Bảng giả định mỗi bản cập nhật tên được kiểm soát qua **version** hoặc quy tắc xung đột phù hợp. Khi còn V1, **display_name là nguồn đọc chuẩn**; chỉ khi V1 không còn ghi và dữ liệu đã được đồng bộ đầy đủ mới chuyển đường đọc sang **public_name**.

## 7. Expand: thêm cột mà không phá V1

Migration bước đầu:

~~~sql
ALTER TABLE customer_profiles
ADD COLUMN public_name TEXT;
~~~

Tại thời điểm này:

- **display_name** vẫn tồn tại và giữ nguyên kiểu, ràng buộc.
- **public_name** chấp nhận NULL để các INSERT của V1 chưa cung cấp cột mới vẫn hợp lệ.
- V1 tiếp tục đọc/ghi **display_name**.
- V2 có thể bắt đầu biết tới **public_name** sau khi migration đã hoàn thành và ứng dụng tương thích.

**Đừng bắt đầu bằng:**

~~~sql
-- Ví dụ KHÔNG an toàn khi V1 còn chạy:
ALTER TABLE customer_profiles RENAME COLUMN display_name TO public_name;
~~~

Hoặc:

~~~sql
-- Có thể phá INSERT của V1 nếu không có default và writer cũ không gửi cột:
ALTER TABLE customer_profiles ADD COLUMN public_name TEXT NOT NULL;
~~~

Việc thêm cột nullable ở PostgreSQL thường rẻ hơn việc chuyển toàn bộ dữ liệu, nhưng **ALTER TABLE vẫn cần khóa schema** và có thể bị chặn bởi transaction dài. Cần đo thời gian khóa, dùng giới hạn chờ khóa hợp lý và thử trên dữ liệu đủ lớn. “Additive” chỉ có nghĩa **tương thích về hợp đồng**, không có nghĩa **không có rủi ro vận hành**.

### 7.1. Thứ tự deploy tối thiểu

~~~text
1. Kiểm tra mọi bản V1 vẫn chạy được sau ADD COLUMN.
2. Triển khai migration expand thành công.
3. Chỉ sau đó triển khai V2 bắt đầu ghi public_name.
4. Cho V1 và V2 cùng chạy trong khoảng rolling/canary.
~~~

Nếu deploy V2 trước migration, SQL của V2 tham chiếu cột chưa tồn tại sẽ lỗi. Nên kiểm soát thứ tự một cách tự động trong pipeline thay vì dựa vào trí nhớ người triển khai.

## 8. V2: ghi cả hai, nhưng vẫn đọc cột cũ

Để V1 và V2 cùng hoạt động, V2 có thể **dual-write cùng hàng**:

~~~sql
UPDATE customer_profiles
SET display_name = :newName,
    public_name = :newName,
    version = version + 1
WHERE tenant_id = :tenantId
  AND customer_id = :customerId
  AND version = :expectedVersion
RETURNING version;
~~~

Ở đây các tham số **:name** là ký hiệu minh họa cho named parameters ở tầng framework; JDBC thuần dùng dấu **?**. Hai cột được cập nhật trong **một câu UPDATE** và thuộc cùng transaction; nếu transaction rollback, cả hai thay đổi rollback.

Khi V2 đọc:

~~~sql
SELECT display_name, version
FROM customer_profiles
WHERE tenant_id = :tenantId AND customer_id = :customerId;
~~~

**Tại sao V2 chưa đọc public_name?** Vì V1 vẫn có thể cập nhật **display_name** mà không cập nhật cột mới. Trong khoảng chồng lấn, giá trị public_name có thể cũ hoặc NULL. Đọc trường mới quá sớm sẽ làm API trả thông tin sai dù tất cả câu SQL đều hợp lệ.

### 8.1. Ví dụ Spring JdbcTemplate ở V2

~~~java
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ProfileNameRepositoryV2 {
    private final JdbcTemplate jdbc;

    public ProfileNameRepositoryV2(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record NameVersion(String name, long version) {}

    public NameVersion read(long tenantId, long customerId) {
        return jdbc.queryForObject(
            """
            SELECT display_name, version
            FROM customer_profiles
            WHERE tenant_id = ? AND customer_id = ?
            """,
            (rs, row) -> new NameVersion(
                rs.getString("display_name"),
                rs.getLong("version")),
            tenantId, customerId);
    }

    public long rename(long tenantId, long customerId,
                       String newName, long expectedVersion) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        List<Long> updated = jdbc.query(
            """
            UPDATE customer_profiles
            SET display_name = ?,
                public_name = ?,
                version = version + 1
            WHERE tenant_id = ? AND customer_id = ?
              AND version = ?
            RETURNING version
            """,
            (rs, row) -> rs.getLong(1),
            newName, newName, tenantId, customerId, expectedVersion);

        if (updated.size() != 1) {
            throw new IllegalStateException(
                "Không tồn tại hoặc đã có cập nhật đồng thời");
        }
        return updated.get(0);
    }
}
~~~

Ví dụ giả định **PostgreSQL** (vì có RETURNING) và đúng DataSource/transaction manager. **jdbc.query(...)** trên UPDATE RETURNING trả một dòng khi thành công; trong service có nhiều bước, cần đặt lời gọi này trong **transaction bao trùm use case**, không coi giá trị RETURNING là đã COMMIT.

Phiên bản V1 cũng phải có cơ chế xử lý cạnh tranh phù hợp. Nếu cả hai phiên bản dùng **version**, một writer dựa trên bản đọc cũ sẽ bị từ chối hoặc buộc đọc lại, thay vì ghi đè vô ý. **Dual-write không tự giải quyết lost update hoặc xung đột nghiệp vụ**.

## 9. Race khi V1 và V2 ghi đồng thời

Giả sử sau khi V2 ghi tên “Bình”, V1 cũ nhận yêu cầu đổi thành “Minh”:

~~~text
V2: UPDATE display_name='Bình', public_name='Bình'
V2: COMMIT

V1: UPDATE display_name='Minh'   (không biết public_name)
V1: COMMIT

Trạng thái:
  display_name = 'Minh'
  public_name  = 'Bình'
~~~

Hai cột **lệch nhau** mà không có câu SQL nào thất bại. Nếu V2 đọc **COALESCE(public_name, display_name)**, kết quả là “Bình” – sai so với trạng thái canonical mà V1 vừa ghi.

Vì vậy, trong khoảng V1 + V2:

1. **Đọc display_name**, chưa ưu tiên cột mới.
2. V2 ghi cả hai cột để giảm khối lượng chuyển đổi về sau.
3. Có thể chạy backfill sơ bộ trong nền, nhưng **không tuyên bố đã chuyển đổi xong** khi V1 còn khả năng ghi.
4. Chỉ chuyển nguồn đọc sau khi mọi V1 và đường ghi legacy ngừng hoạt động, rồi **reconcile** lần cuối.

Nếu nghiệp vụ buộc V2 đọc trường mới ngay khi V1 vẫn chạy, cần một thiết kế khác có điểm phối hợp thật, chẳng hạn trigger bảo đảm mọi UPDATE cũ cũng cập nhật cột mới hoặc một lớp ghi chung. **Trigger có thể giúp, nhưng đòi hỏi kiểm tra thứ tự, recursion, quyền, performance và rollback**; không nên ngầm giả định app dual-write là đủ.

## 10. Backfill theo lô: chuyển dữ liệu đã có

Sau expand, các hàng lịch sử có **public_name = NULL**. Một lệnh cập nhật toàn bảng có thể tạo transaction lớn, lock wait, WAL, replication lag và bloat:

~~~sql
-- Chỉ phù hợp khi dữ liệu nhỏ/đã kiểm chứng tác động:
UPDATE customer_profiles
SET public_name = display_name
WHERE public_name IS NULL;
~~~

Với bảng lớn, nên **chia lô**, quan sát tải và commit giữa các lô. Ví dụ một batch PostgreSQL:

~~~sql
WITH batch AS (
    SELECT tenant_id, customer_id
    FROM customer_profiles
    WHERE public_name IS DISTINCT FROM display_name
    ORDER BY tenant_id, customer_id
    LIMIT 500
    FOR UPDATE SKIP LOCKED
)
UPDATE customer_profiles AS p
SET public_name = p.display_name
FROM batch AS b
WHERE p.tenant_id = b.tenant_id
  AND p.customer_id = b.customer_id;
~~~

Một worker có thể chạy câu này trong các transaction ngắn, commit sau từng batch, giới hạn tốc độ và dừng khi không còn hàng cần cập nhật. **SKIP LOCKED** giúp tránh chờ một số hàng đang bị transaction khác giữ khóa; nó không phải cơ chế tự bảo đảm mọi hàng đã được xử lý. Cần lặp, đo số hàng cập nhật và quét đối soát cuối.

Lưu ý kỹ thuật:

- Câu **ORDER BY + LIMIT** có thể cần chỉ mục/thứ tự quét phù hợp. Khóa chính ở ví dụ là **(tenant_id, customer_id)**.
- **IS DISTINCT FROM** xử lý cả NULL, tốt hơn phép so sánh **<>** khi cột có thể NULL.
- Mỗi UPDATE vẫn tạo WAL và áp lực I/O; cần xem replication lag, lock wait, vacuum và số hàng mỗi đợt.
- Nếu có nhiều backfill workers, cần thiết kế phân công, tiến độ và khả năng chạy lại; không suy rằng chỉ vì có SKIP LOCKED thì không thể bỏ sót.
- Trong khi V1 còn ghi, một hàng đã được backfill **có thể lại bị lệch** sau đó. Backfill giai đoạn này chỉ làm giảm backlog, không phải xác nhận hoàn tất.
- Với dữ liệu thực có chuyển đổi kiểu/phép chuẩn hóa không đảo ngược, cần xác định mapping, giá trị không hợp lệ và khả năng khôi phục thay vì chỉ sao chép cột.

## 11. Reconcile sau khi writer cũ dừng

Điều kiện tiên quyết để chuyển nguồn đọc sang **public_name** là **không còn writer V1** hoặc bất kỳ job/consumer nào chỉ cập nhật display_name.

Khi đã xác nhận điều kiện đó:

~~~sql
-- Kiểm tra còn bao nhiêu hàng không khớp:
SELECT count(*) AS mismatched_rows
FROM customer_profiles
WHERE public_name IS DISTINCT FROM display_name;
~~~

Chạy lại backfill theo lô cho những hàng không khớp, rồi kiểm tra:

~~~sql
SELECT count(*) AS mismatched_rows
FROM customer_profiles
WHERE public_name IS DISTINCT FROM display_name;
-- Mục tiêu: 0, tại một mốc quan sát phù hợp.
~~~

**Đếm 0 ở một thời điểm chưa đủ** nếu còn luồng viết cột cũ. Để chốt giai đoạn, cần kết hợp chứng cứ vận hành như số instance V1 bằng 0, các worker đã được nâng cấp, các transaction V1 đang chạy đã kết thúc và tất cả đường viết có thể truy cập schema cũ đã được kiểm tra.

Nếu V2 vẫn ghi cả hai cột với cùng giá trị, chúng giữ nhất quán cho các bản cập nhật tiếp theo. Trường hợp có bulk SQL hoặc trigger riêng, phải xác minh chúng có cùng hợp đồng ghi hay không.

## 12. V3: chuyển nguồn đọc sau khi dữ liệu đã đồng bộ

Khi **V1 hoàn toàn ngừng ghi** và backfill/reconcile đạt điều kiện, có thể triển khai V3:

~~~sql
-- V3 đọc cột mới:
SELECT public_name, version
FROM customer_profiles
WHERE tenant_id = ? AND customer_id = ?;

-- V3 vẫn ghi cả hai để cùng tồn tại với V2:
UPDATE customer_profiles
SET display_name = ?,
    public_name = ?,
    version = version + 1
WHERE tenant_id = ? AND customer_id = ?
  AND version = ?;
~~~

Trong thời gian V2 và V3 đồng thời:

- **V2 đọc display_name; V3 đọc public_name.**
- **Cả V2 và V3 ghi cùng giá trị vào cả hai cột trong một statement/transaction**.
- Không còn V1 chỉ ghi display_name, nên hai nguồn đọc không tự phân kỳ do đường ghi cũ.
- Vẫn cần version/locking để xử lý hai transaction cùng sửa một hồ sơ.

Có thể dùng **feature flag** để bật đường đọc mới theo nhóm instance, nhưng phải phân biệt flag hành vi và trạng thái schema. Tắt flag để quay lại đường đọc cũ chỉ an toàn khi **cột cũ vẫn được cập nhật đúng và dữ liệu không còn bị phân kỳ**. Một flag không thể tái tạo dữ liệu đã bị xóa khỏi database.

Đừng chuyển sang V3 khi còn vài scheduled jobs V1 ngủ đến nửa đêm rồi mới chạy: **đường ghi thưa nhất thường là nơi phá vỡ giả định tương thích**.

## 13. V4 và contract: xóa phụ thuộc từng bước

Để tiến tới chỉ dùng **public_name**, trước tiên cần đảm bảo mọi code còn chạy không đòi hỏi cột cũ là **NOT NULL khi INSERT**. Lược đồ ban đầu có **display_name TEXT NOT NULL**, nên code V4 chỉ INSERT public_name sẽ lỗi nếu ràng buộc cũ còn giữ.

Một thứ tự an toàn hơn:

1. Xác nhận **không còn V1/V2** và mọi reader còn hoạt động đã chuyển sang public_name.
2. Trong lúc V3 còn ghi cả hai, **nới ràng buộc cột cũ** để V4 có thể không gửi display_name ở INSERT:

~~~sql
ALTER TABLE customer_profiles
ALTER COLUMN display_name DROP NOT NULL;
~~~

3. Triển khai V4 **đọc/ghi public_name**. Trong giai đoạn V3 + V4, V3 vẫn ghi cả hai còn V4 chỉ ghi cột mới; **cả hai đều đọc cột mới**, nên việc display_name không còn đồng bộ không ảnh hưởng những reader đã chuyển đổi.
4. Xác nhận **mọi V3 và các consumer cột cũ đã dừng**, bao gồm khả năng rollback binary theo chính sách.
5. Chỉ sau đó, **contract** bằng cách xóa display_name:

~~~sql
ALTER TABLE customer_profiles
DROP COLUMN display_name;
~~~

Khi chưa loại hết V3, lệnh DROP COLUMN sẽ phá câu UPDATE dual-write của V3 dù mọi V3 đã đọc cột mới. Chỉ kiểm tra đường đọc là **chưa đủ** để contract.

### 13.1. Khi nào đưa public_name thành NOT NULL?

Trong giai đoạn đầu, **public_name** nullable để V1 còn INSERT. Sau khi không còn legacy writer và dữ liệu đã backfill, cần chuyển ràng buộc theo lộ trình riêng.

Ví dụ PostgreSQL:

~~~sql
ALTER TABLE customer_profiles
ADD CONSTRAINT customer_profiles_public_name_present
CHECK (public_name IS NOT NULL) NOT VALID;

-- Kiểm tra dữ liệu hiện có, có thể tốn thời gian:
ALTER TABLE customer_profiles
VALIDATE CONSTRAINT customer_profiles_public_name_present;

-- Sau khi tương thích và đánh giá lock:
ALTER TABLE customer_profiles
ALTER COLUMN public_name SET NOT NULL;
~~~

**NOT VALID** cho CHECK cho phép bổ sung constraint rồi kiểm tra dữ liệu cũ riêng, nhưng các bản ghi **mới/sửa** vẫn bị constraint kiểm tra. Vì vậy chỉ thêm nó sau khi mọi writer đang hoạt động chắc chắn cung cấp public_name phù hợp. Trên những phiên bản PostgreSQL có hỗ trợ tối ưu tương ứng, một validated CHECK có thể giúp bước SET NOT NULL tránh quét bảng lại; **không có nghĩa thao tác SET NOT NULL không cần lock**. Việc giữ hay xóa constraint CHECK bổ sung là quyết định vận hành sau khi đã có NOT NULL.

Các bước **ADD CHECK, VALIDATE, SET NOT NULL và DROP COLUMN** có chế độ khóa và chi phí khác nhau; không tự gom tất cả vào một migration transaction dài nếu điều đó tạo rủi ro downtime.

## 14. Backward-compatible schema nhưng forward-incompatible data

Một migration **thêm cột mới** có thể không phá binary cũ, nhưng **giá trị mới** lại phá logic cũ.

Ví dụ Java:

~~~java
enum OrderStatus {
    NEW, PAID, CANCELED
}

OrderStatus status = OrderStatus.valueOf(statusFromDatabase);
~~~

V2 muốn thêm trạng thái **PARTIALLY_REFUNDED**. Nếu V2 bắt đầu ghi giá trị đó trong khi V1 còn đọc và gọi **valueOf**, V1 có thể ném **IllegalArgumentException**, dù lược đồ **status TEXT** không thay đổi.

Lộ trình tương thích:

1. Triển khai phiên bản reader **đọc được giá trị mới** hoặc xử lý unknown theo chính sách rõ ràng, nhưng **chưa phát sinh giá trị mới**.
2. Đợi mọi reader và consumer quan trọng đạt phiên bản chịu được giá trị đó.
3. Bật tính năng writer tạo **PARTIALLY_REFUNDED**.
4. Kiểm thử rollback: nếu quay lại V1 không biết trạng thái này, dữ liệu đã ghi vẫn có thể làm V1 hỏng. Khi ấy phải giới hạn rollback hoặc có đường chuyển đổi dữ liệu an toàn.

**Unknown không phải lúc nào cũng được tự coi là trạng thái hợp lệ.** Với thanh toán, phân quyền hoặc đơn hàng, chuyển một giá trị lạ thành PAID/ALLOWED/DONE có thể nguy hiểm. Cần định nghĩa cách xử lý thất bại an toàn.

## 15. Các thay đổi schema thường gặp và mức rủi ro

| Thay đổi | Vì sao cần cẩn thận? | Cách tiếp cận |
| --- | --- | --- |
| **Thêm cột nullable** | Thường tương thích, nhưng có schema lock và tác động query mapping | Expand trước, kiểm thử V1 trên schema mở rộng |
| **Thêm cột NOT NULL** | INSERT cũ không gửi giá trị sẽ lỗi | Nullable/default thích hợp trước, backfill, thêm constraint sau |
| **Đổi tên cột** | Binary cũ tham chiếu tên cũ | Thêm cột mới, chuyển đọc/ghi nhiều giai đoạn, drop sau |
| **Xóa cột hoặc bảng** | Reader/writer cũ có thể lỗi ngay | Điều tra mọi consumer và rollback window trước contract |
| **Thu hẹp kiểu/độ dài cột** | Dữ liệu hiện có có thể vượt giới hạn | Đo và làm sạch dữ liệu, dùng chuyển đổi theo giai đoạn |
| **Đổi kiểu dữ liệu** | Cast, precision, ORM converter và index có thể khác | Cột mới, chuyển dữ liệu, xác thực và chuyển code trước |
| **Thêm UNIQUE/FK/CHECK** | Hàng cũ có thể vi phạm, writer cũ có thể ghi dữ liệu không hợp lệ | Đo vi phạm, sửa dữ liệu, triển khai writer tương thích rồi enforce |
| **Đổi default** | INSERT cũ dựa vào default có thể tạo giá trị khác dự kiến | Kiểm tra mọi client và dữ liệu đã phát sinh |
| **Thêm giá trị enum** | Code cũ có thể không parse/không hiểu | Nâng reader trước, bật writer sau |
| **Đổi khóa chính hoặc khóa ngoại** | Join, idempotency, cache key và quan hệ có thể bị ảnh hưởng | Dùng mapping/alias và lộ trình nhiều release |
| **Xây index mới** | Có thể tốn I/O/lock; kế hoạch query thay đổi | Tạo index theo cơ chế ít chặn ghi, đo hiệu năng |

“Thêm” thường ít rủi ro về hợp đồng hơn “xóa”, nhưng không đồng nghĩa có thể chạy SQL trực tiếp không kiểm tra trên bảng nhiều tỷ hàng.

## 16. PostgreSQL: index và migration trên bảng lớn

Giả sử V2 cần tìm hồ sơ theo tenant và public_name. Cần thêm index mà không muốn khóa ghi lâu:

~~~sql
CREATE INDEX CONCURRENTLY idx_profiles_tenant_public_name
ON customer_profiles(tenant_id, public_name);
~~~

Trong PostgreSQL, **CREATE INDEX CONCURRENTLY** nhằm giảm chặn ghi so với cách tạo index thông thường, nhưng:

- **Không được chạy trong một transaction block**. Công cụ migration có thể mặc định bọc script trong transaction, nên phải cấu hình chính xác theo công cụ đang sử dụng.
- Có thể mất nhiều thời gian và dùng CPU/I/O; không tự là tác vụ “miễn phí”.
- Nếu build thất bại, một **invalid index** có thể còn tồn tại; cần kiểm tra và xử lý qua quy trình được hỗ trợ.
- Index có thể cần thời gian để trở nên sẵn dùng cho planner; không deploy tính năng với kỳ vọng hiệu năng chưa được xác minh.

Ví dụ kiểm tra index hợp lệ:

~~~sql
SELECT indexrelid::regclass AS index_name,
       indisvalid,
       indisready
FROM pg_index
WHERE indexrelid = 'idx_profiles_tenant_public_name'::regclass;
~~~

SQL trên minh họa PostgreSQL và yêu cầu index đã tồn tại. Đừng biến việc tạo index thành bước bắt buộc trong một transaction chứa những thay đổi dữ liệu nghiệp vụ.

Với bảng lớn, đặt **lock_timeout** ngắn cho những DDL có nguy cơ bị chờ khóa quá lâu, theo dõi blocking transactions và kiểm tra khả năng retry migration an toàn. Không tự động retry lệnh DDL không rõ trạng thái mà không kiểm tra schema hiện tại.

## 17. Flyway/Liquibase và thứ tự triển khai

Các công cụ migration như **Flyway** hoặc **Liquibase** giúp quản lý thứ tự, version và lịch sử thay đổi schema. Tuy nhiên, công cụ chỉ thực thi migration: **nó không tự bảo đảm hợp đồng tương thích giữa nhiều phiên bản ứng dụng**.

Một pipeline khái niệm:

~~~text
Migrate schema (EXPAND)
       |
       v
Kiểm thử V1 trên schema mở rộng
       |
       v
Deploy V2 chuyển tiếp (canary -> rolling)
       |
       v
Backfill + metrics + đối soát
       |
       v
Xác nhận không còn V1 writers
       |
       v
Deploy V3 chuyển đường đọc
       |
       v
Deploy V4 và gỡ các phụ thuộc legacy
       |
       v
Migrate schema (CONTRACT) sau khi đã hết rollback window
~~~

Thực hành nên tách:

- **Schema migrations:** thay đổi cấu trúc DB, version có quản lý.
- **Data migrations/backfills:** job riêng có thể tạm dừng, chạy lại, đo tiến độ và xử lý dữ liệu lỗi.
- **Feature flags:** điều khiển thời điểm bắt đầu đọc/ghi giá trị mới.
- **Compatibility gates:** kiểm thử và điều kiện vận hành xác nhận một phase đã an toàn.

Không mặc định mọi migration có thể rollback bằng SQL ngược. Ví dụ **DROP COLUMN** làm mất thông tin; cách đảo ngược bằng ADD COLUMN tạo cột rỗng, không phục hồi dữ liệu cũ.

## 18. Rollback ứng dụng không đồng nghĩa rollback dữ liệu

Ví dụ V3 đã bắt đầu đọc **public_name** nhưng V2 vẫn ghi cả hai cột. Nếu mọi writer còn duy trì display_name đầy đủ, có thể rollback V3 về V2 trong một khoảng thời gian cho phép.

Nhưng khi V4 chỉ ghi public_name, **display_name có thể không còn theo kịp**. Lúc đó rollback V4 về V2 (vốn đọc display_name) sẽ làm người dùng thấy dữ liệu cũ. Sau khi **DROP COLUMN display_name**, binary V2/V3 còn tham chiếu cột cũ sẽ lỗi ngay.

Vì vậy kế hoạch nên ghi rõ:

| Giai đoạn | Có thể rollback binary không? | Điều kiện |
| --- | --- | --- |
| Sau ADD COLUMN nullable | Thường có | V1 vẫn hiểu schema, không có dữ liệu mới phá nghĩa |
| V1 + V2 | Có thể quay về V1 | V2 chưa tạo dữ liệu V1 không đọc được; cột cũ còn đầy đủ |
| V2 + V3 | Có thể quay về V2 trong cửa sổ xác định | Cả hai còn ghi cột cũ và mới đúng hợp đồng |
| V3 + V4 | **Không mặc định** quay về V2 | V4 có thể đã ngừng cập nhật cột cũ |
| Sau DROP COLUMN cũ | Binary tham chiếu cột cũ không thể chạy an toàn | Cần roll-forward hoặc quy trình phục hồi dữ liệu được chuẩn bị |

**Roll-forward** thường là lựa chọn ít rủi ro hơn sau khi migration phá hủy thông tin đã diễn ra: sửa lỗi bằng phiên bản mới tương thích với schema hiện tại. Nếu phải khôi phục từ backup/PITR, cần đánh giá ảnh hưởng tới dữ liệu mới phát sinh sau mốc backup; không tự restore production để lấy lại một cột mà không có kế hoạch đối soát.

## 19. Thay đổi dữ liệu trong hệ phân tán và consumer chậm

Một ứng dụng có thể ghi database và phát sự kiện **ProfileUpdated** vào message broker. Consumer cũ có thể xử lý event sau nhiều giờ:

~~~text
Producer V2 --> outbox --> broker --> Consumer V1
                              |
                              +------> Consumer V2
~~~

Nếu producer bỏ field cũ ngay khi deploy bản mới, consumer V1 có thể không deserialize được. Cần lập ma trận tương thích cho **event schema** tương tự database schema.

Nguyên tắc thường hữu ích:

1. **Thêm field optional** và giữ field cũ trong cửa sổ chuyển tiếp; xác định rõ default và semantics.
2. Nâng cấp **consumer/reader trước producer/writer** khi sắp giới thiệu giá trị hoặc field mới.
3. Chỉ bỏ field cũ khi tất cả consumer, replay jobs và nguồn dữ liệu lịch sử đã tương thích.
4. Dùng schema/versioning cho JSON, Avro, Protobuf hoặc định dạng tương ứng, nhưng **schema registry không tự giải quyết mọi thay đổi ngữ nghĩa**.
5. Nếu một event có thể được replay từ lịch sử, cần consumer đủ sức hiểu **định dạng cũ lâu hơn thời gian deploy thông thường**.
6. Gắn **event_id** ổn định và idempotency ở consumer để tránh tác động lặp khi migration/replay.

Đừng gọi một thay đổi backward-compatible chỉ vì parser có thể bỏ qua field không biết: nếu field mới làm thay đổi quy tắc tính tiền, trạng thái đơn hoặc quyền truy cập, consumer cũ vẫn có thể ra quyết định sai.

## 20. ORM và phiên bản ứng dụng: những điểm dễ bị bỏ qua

Khi dùng JPA/Hibernate, tương thích còn phụ thuộc mapping và chiến lược sinh SQL:

- **Entity mapping:** @Column(name = "display_name") còn tồn tại trong binary cũ, nên DROP COLUMN sẽ phá SELECT/INSERT/UPDATE của nó.
- **@Enumerated(EnumType.STRING):** giá trị enum mới có thể làm binary cũ không nạp được entity.
- **ddl-auto=create/update:** không nên dùng tự động sửa schema ngoài kiểm soát trong production nhiều instance; có thể gây race với công cụ migration và làm trạng thái trung gian khó dự đoán.
- **Schema validation:** app mới có thể fail startup nếu schema chưa được expand. Cần xem pipeline và startup behavior.
- **Dirty checking:** binary V1 chỉ quản lý một trường, binary V2 quản lý cả hai; không tự suy rằng V1 sẽ đồng bộ trường mới.
- **Bulk JPQL/native SQL:** có thể bỏ qua lifecycle hooks, optimistic version increment hoặc logic dual-write trong entity/service.
- **Caching:** cache cấp hai, query cache hoặc Redis có thể mang bản ghi có schema cũ. Cần version cache key, invalidation hoặc cơ chế deserialize chịu được thay đổi.
- **Serialization:** object JSON lưu lâu hoặc trong cache có thể chứa trường/enum không còn được parser mới hiểu.

### 20.1. Gợi ý kiểm soát annotation và transaction

Ở V2, nếu dùng JPA thay vì JDBC, cả hai field phải được cập nhật nhất quán trong cùng transaction:

~~~java
@Transactional
public void rename(long tenantId, long customerId, String name) {
    CustomerProfile profile =
        repository.findByTenantIdAndCustomerId(tenantId, customerId)
            .orElseThrow();
    profile.setDisplayName(name);
    profile.setPublicName(name);
}
~~~

Đoạn mã là **pseudocode Spring Data JPA**: giả định entity, repository và setter đã được định nghĩa; cần xác thực tenant/ủy quyền, kiểm soát version và rollback rule. Khi entity managed, dirty checking sẽ tạo SQL phù hợp ở flush, nhưng **tính đúng chỉ có nếu mọi đường ghi của V2 đều cập nhật cả hai field**. Batch job hoặc native UPDATE đi đường khác vẫn có thể tạo lệch dữ liệu.

## 21. Kiểm thử tính tương thích có giá trị hơn kiểm thử một phiên bản

Một kế hoạch kiểm thử nên có ít nhất các nhóm:

### 21.1. Kiểm thử schema cũ/mới

- V1 **SELECT/INSERT/UPDATE/DELETE** bình thường sau expand.
- V2 không truy cập cột mới trước khi migration thành công.
- Ràng buộc NOT NULL, CHECK, FK, UNIQUE mới không làm những đường ghi hợp lệ của V1 thất bại.
- Sau contract, chỉ binary không còn phụ thuộc cột cũ được phép khởi chạy.

### 21.2. Kiểm thử đồng thời

- V1 và V2 cùng sửa cùng hàng; V2 vẫn thấy giá trị canonical từ display_name.
- V2/V3 cùng ghi sau switch; hai cột giữ cùng giá trị.
- V3/V4 cùng ghi; tất cả readers đều dùng public_name và không cần cột cũ mới nhất.
- Backfill chạy cùng request thật; không làm mất cập nhật hoặc giữ khóa quá lâu.
- Lỗi serialization/deadlock phải retry toàn bộ transaction khi phù hợp, không lặp tác dụng nghiệp vụ.

### 21.3. Kiểm thử rollback/failure

- Deploy V2 một phần rồi dừng: V1 vẫn hoạt động.
- Migration bị timeout: schema ở trạng thái nào? Có thể chạy lại an toàn không?
- Backfill bị dừng giữa chừng: tiếp tục chạy được, không làm sai dữ liệu?
- V3 rollback sang V2: dữ liệu cột cũ còn đầy đủ hay không?
- Sau V4 bắt đầu ghi chỉ cột mới: hệ thống từ chối rollback về V2 nếu dữ liệu không còn tương thích.
- Cache/consumer lâu đời xử lý được thông điệp thuộc thời kỳ chuyển tiếp.

Các kiểm thử cần chạy **trên database thật cùng loại/phiên bản được hỗ trợ** để đo khóa, isolation và behavior thực tế. Một mock repository chỉ xác nhận method được gọi đúng, không chứng minh SQL hay DDL tương thích.

## 22. Quan sát và điều kiện dừng từng giai đoạn

Một rollout nhiều phiên bản cần chỉ số và **gates** rõ ràng:

| Gate | Dữ liệu quan sát | Điều kiện đề xuất |
| --- | --- | --- |
| Expand hoàn tất | Migration history, schema metadata, errors | Cột mới tồn tại, V1 vẫn hoạt động |
| V2 phủ đủ | Deployment inventory, logs, request metrics | Mọi writer mới hỗ trợ dual-write, không còn path ngoài kiểm soát |
| Dừng V1 | Số instance, jobs, DB sessions, event consumers | Không còn request/transaction/job legacy có thể ghi chỉ cột cũ |
| Reconcile | Số hàng khác nhau/NULL, backlog và tốc độ xử lý | Không còn mismatch tại mốc kiểm tra phù hợp, writer còn lại duy trì quy tắc |
| Switch đọc | Error rate, dữ liệu trả về, version/freshness | V2/V3 hoạt động đồng thời, không lệch kết quả ngoài mong đợi |
| V4 hoạt động | DDL/ràng buộc và giám sát INSERT | Những writer mới không cần display_name, mọi reader đã dùng public_name |
| Contract | Truy vấn SQL, ORM mapping, báo cáo, rollback plan | Không còn binary hoặc consumer tham chiếu cột cũ |

Metric có thể triển khai:

- **schema_compatibility_errors_total:** lỗi thiếu cột, thiếu bảng, loại dữ liệu không mong đợi.
- **legacy_field_write_total:** còn bao nhiêu lượt ghi qua code cũ.
- **backfill_rows_remaining / backfill_rows_per_second:** tiến độ, không chỉ số batch hoàn thành.
- **dual_column_mismatch_total:** số hàng hai cột khác nhau hoặc thiếu.
- **migration_lock_wait / migration_duration:** ảnh hưởng DDL và job lên transaction bình thường.
- **replica_lag / WAL generation / pool wait:** tác động của data migration tới hệ thống.
- **unknown_enum_values / event_decode_errors:** consumer đọc dữ liệu/định dạng mới thất bại.
- **rollback_compatibility_gate:** có còn được phép đưa binary nào quay lại không.

Không nên log dữ liệu cá nhân nguyên văn để đối soát; dùng số lượng, IDs đã giới hạn quyền, hashing/tokenization theo yêu cầu bảo mật và log truy cập được kiểm soát.

## 23. Những sai lầm thiết kế thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| RENAME COLUMN ngay trước rolling deploy | V1 đang chạy báo column does not exist | Expand bằng cột mới, chuyển nhiều giai đoạn |
| Thêm NOT NULL khi writer cũ chưa gửi cột | INSERT từ V1 thất bại | Nullable/default an toàn, backfill rồi validate constraint |
| V2 đọc cột mới ngay khi V1 chỉ ghi cột cũ | Trả dữ liệu cũ/NULL sau ghi của V1 | V2 đọc canonical cũ cho đến khi V1 dừng và reconcile |
| Dual-write hai SQL nằm trong hai transaction | Một cột commit, cột kia lỗi | Ghi cả hai trong cùng statement/transaction |
| Backfill một lần rồi coi hoàn tất khi V1 còn ghi | Cột lại lệch sau backfill | Reconcile cuối sau khi legacy writer dừng |
| DROP cột cũ khi V3 còn dual-write | V3 UPDATE/INSERT thất bại | Chỉ contract khi mọi writer đã bỏ cột cũ |
| Chỉ kiểm tra reader, bỏ qua INSERT constraint | V4 không gửi display_name bị NOT NULL từ chối | Nới ràng buộc legacy trước khi chuyển writer mới |
| Bật enum value mới trước khi nâng reader | Code cũ không parse hoặc hiểu sai trạng thái | Reader tương thích trước, writer phát giá trị mới sau |
| Cho ORM tự update schema trong mọi instance | DDL race, trạng thái trung gian khó kiểm soát | Migration có quản lý, điều phối riêng |
| CREATE INDEX CONCURRENTLY trong transaction mặc định | Migration thất bại ở PostgreSQL | Cấu hình migration ngoài transaction cho bước này |
| Tin rằng rollback binary là rollback dữ liệu | Code cũ không đọc được dữ liệu mới hoặc cột đã xóa | Định nghĩa rollback window và ưu tiên roll-forward |
| Chỉ nâng API, quên worker/consumer/BI | Job chạy muộn phá dữ liệu hoặc lỗi đọc | Kiểm kê mọi reader/writer phụ thuộc schema |
| Không kiểm thử concurrent writers | Lost update hoặc lệch dual column | Version, khóa/ràng buộc, test nhiều bản đồng thời |
| Xem thay đổi schema đồng nghĩa thay đổi event schema | Consumer cũ thất bại khi replay | Kế hoạch compatibility cho schema sự kiện riêng |

## 24. Bài tập vận dụng

### Bài 1. Có thể RENAME ngay không?

V1 vẫn chạy trên hai instance và SELECT **display_name**. Nhóm muốn deploy V2 đổi tên cột thành **public_name** trong cùng một migration. Điều gì có thể xảy ra?

**Gợi ý:** Các SELECT/UPDATE của V1 tham chiếu tên cũ sẽ lỗi. Dùng ADD COLUMN, V2 dual-write, backfill, dừng V1, chuyển đọc rồi mới contract.

### Bài 2. Vì sao COALESCE sai?

V2 đã ghi **display_name='Bình', public_name='Bình'**. Sau đó V1 cập nhật **display_name='Minh'**. Nếu V2 đọc **COALESCE(public_name, display_name)**, nó trả gì? Có phù hợp với trạng thái vừa ghi không?

**Gợi ý:** Trả “Bình” vì public_name không NULL, nhưng giá trị canonical mới từ V1 là “Minh”. Trong thời kỳ V1 còn ghi, V2 nên đọc display_name hoặc có cơ chế đồng bộ mạnh khác.

### Bài 3. Backfill xong chưa?

Job backfill đã cập nhật mọi hàng hiện có và đếm mismatch bằng 0 lúc 10:00. Một scheduled job V1 bắt đầu lúc 23:00 vẫn cập nhật display_name. Có thể chuyển mọi reader sang public_name lúc 10:01 không?

**Gợi ý:** Chưa an toàn. Legacy job có thể làm lệch hai cột sau mốc kiểm tra. Phải vô hiệu hóa/nâng cấp mọi đường ghi cũ, đợi chúng dừng, reconcile lại rồi chuyển đọc.

### Bài 4. NOT NULL và INSERT

V4 chỉ INSERT public_name nhưng bảng vẫn khai báo **display_name TEXT NOT NULL**, không có default. V4 có thể INSERT thành công không?

**Gợi ý:** Không trong trường hợp thông thường; cột cũ bị bỏ trống và vi phạm NOT NULL. Cần nới ràng buộc cũ khi không còn V1/V2 phụ thuộc, trước khi deploy writer chỉ ghi cột mới.

### Bài 5. Rollback sau V4

V4 đã ghi tên mới vào public_name nhưng không cập nhật display_name. Nhóm muốn rollback V4 về V2 vì có lỗi giao diện. Vì sao đây là quyết định nguy hiểm?

**Gợi ý:** V2 đọc display_name, có thể thấy tên cũ. Cần đánh giá rollback window và tính nhất quán; nếu vượt điểm chuyển, ưu tiên roll-forward hoặc quy trình phục hồi/đối soát đã chuẩn bị.

### Bài 6. Enum mới

Code V1 có **OrderStatus.valueOf()** chỉ biết NEW, PAID, CANCELED. Code V2 bắt đầu ghi trạng thái PARTIALLY_REFUNDED. Schema vẫn là TEXT, vậy có vấn đề không?

**Gợi ý:** Có. V1 có thể ném exception hoặc xử lý sai. Nâng cấp mọi reader trước khi writer bắt đầu phát sinh giá trị mới; dữ liệu đã ghi còn ảnh hưởng khả năng rollback.

### Bài 7. Migration index

Một script migration chạy trong transaction mặc định và dùng **CREATE INDEX CONCURRENTLY** trên PostgreSQL. Vì sao cần điều chỉnh công cụ?

**Gợi ý:** PostgreSQL không cho CREATE INDEX CONCURRENTLY chạy trong transaction block. Cần tách và cấu hình migration thích hợp, quan sát index invalid nếu build lỗi.

### Bài 8. Consumer xử lý chậm

Producer V2 bỏ trường **customerName** trong event, nhưng một consumer V1 chỉ chạy mỗi ngày vẫn đọc trường đó. Cần thay đổi thứ tự rollout thế nào?

**Gợi ý:** Duy trì field cũ trong giai đoạn chuyển tiếp, nâng consumer để hiểu event mới trước, kiểm tra replay/history và chỉ bỏ field khi không còn consumer phụ thuộc.

### Bài 9. Backfill gặp crash

Một job đã cập nhật 2 triệu hàng và dừng đột ngột khi còn 300.000 hàng. Thiết kế nào giúp tiếp tục mà không làm hỏng dữ liệu?

**Gợi ý:** Mỗi batch transaction ngắn, câu cập nhật idempotent theo trạng thái hiện tại, metrics về số hàng còn lệch, đối soát và retry có kiểm soát. Không chạy một transaction khổng lồ hoặc dựa duy nhất vào số batch đã gọi.

### Bài 10. Lập ma trận tương thích

Cho bốn phiên bản V1/V2/V3/V4 như bài học. Hãy nêu cặp cùng chạy nào an toàn theo kế hoạch và khi nào không thể DROP display_name.

**Gợi ý:** V1+V2 an toàn khi cả hai đọc cũ và V2 dual-write; V2+V3 an toàn sau khi V1 dừng và reconcile; V3+V4 an toàn khi cả hai đọc mới và ràng buộc cũ đã nới. Không DROP display_name khi còn V1/V2/V3 hoặc consumer nào tham chiếu nó.

## 25. Checklist trước khi triển khai thay đổi schema

1. **Kiểm kê:** những API, worker, scheduled job, reporting job, consumer và client nào đọc/ghi dữ liệu cần đổi?
2. **Ma trận:** mọi cặp ứng dụng đang có thể cùng chạy có tương thích với schema/dữ liệu trung gian không?
3. **Expand trước:** thay đổi thêm cột/bảng/default có phá INSERT/SELECT cũ không; migration có nguy cơ chờ khóa không?
4. **Nguồn chuẩn:** trong giai đoạn hai trường cùng tồn tại, trường nào là nguồn đọc đúng?
5. **Writer cũ:** có cơ chế xác nhận mọi writer legacy đã dừng trước khi chuyển nguồn đọc không?
6. **Dual-write:** có thực hiện trong một transaction và bảo vệ optimistic conflict không? Mọi đường ghi, gồm batch và native SQL, có tuân thủ không?
7. **Backfill:** có chạy theo lô, xử lý lại an toàn, kiểm soát WAL/lock/replica lag và đối soát mismatch không?
8. **Ràng buộc:** khi nào thêm NOT NULL/UNIQUE/FK/CHECK, có dữ liệu cũ vi phạm không và writer nào có thể bị từ chối?
9. **Switch:** khi bật cột/giá trị mới, có rollback window rõ ràng và dữ liệu cũ vẫn phù hợp không?
10. **Contract:** có bằng chứng không còn code hoặc consumer đọc/ghi cột cũ, kể cả khi rollback không?
11. **Sự kiện/cache:** format event, schema registry, cache keys, serializer và replay lịch sử có tương thích không?
12. **Security:** tenant boundary, dữ liệu nhạy cảm và quyền migration có được giữ đúng qua các bảng/cột mới không?
13. **Giám sát:** có metrics lỗi tương thích, mismatch, backfill backlog, lock wait và thay đổi latency không?
14. **Phục hồi:** biết khi nào roll-forward, khi nào cần đối soát và khi nào phục hồi backup/PITR không?
15. **Kiểm thử:** đã chạy ít nhất V1+V2, V2+V3, V3+V4 dưới tải đồng thời trên DB thật loại tương ứng chưa?

## 26. Tổng kết

**Tương thích khi nhiều phiên bản ứng dụng chạy đồng thời** không phải chỉ là giữ các câu SQL tiếp tục chạy. Nó là việc đảm bảo các binary cũ và mới có thể **cùng đọc, cùng ghi, hiểu đúng dữ liệu và bảo vệ bất biến nghiệp vụ** trong mọi trạng thái trung gian được phép xuất hiện. Rolling deployment chỉ an toàn khi database schema, ứng dụng, consumer, cache và dữ liệu lịch sử có một hợp đồng chuyển đổi rõ ràng.

Kỹ thuật thực dụng là **expand trước, giữ đường đọc cũ khi writer cũ còn hoạt động, dual-write có kiểm soát, backfill/reconcile sau khi ngừng writer legacy, chuyển đọc rồi mới contract**. Bước cuối chỉ được xóa cấu trúc cũ khi không còn bất kỳ đường truy cập hoặc rollback plan nào cần nó. Trong Java, phối hợp quy trình đó với **transaction, optimistic locking, SQL có điều kiện, migration versioning, feature flag, metrics và kiểm thử nhiều phiên bản** để tiến hóa hệ thống dữ liệu mà không biến mỗi lần release thành rủi ro gián đoạn dịch vụ.
