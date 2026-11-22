# Thực hiện migration có backfill và kiểm chứng tương thích

Một hệ thống Java đang lưu tên hiển thị của người dùng trong cột **profiles.display_name**. Đội sản phẩm muốn chuyển sang **profiles.preferred_name** để thống nhất cách đặt tên trong API và mô hình dữ liệu. Thay đổi tưởng như đơn giản: thêm cột, copy dữ liệu, đổi code, xóa cột cũ. Tuy nhiên, nếu triển khai rolling deployment, trong một khoảng thời gian **V1 vẫn đọc/ghi display_name trong khi V2 đã đọc/ghi preferred_name**. Nếu copy xong rồi một instance V1 tiếp tục sửa tên, hai cột có thể lệch nhau. Một deploy tưởng là thành công có thể gây mất cập nhật, trả tên cũ hoặc làm bản rollback không chạy được.

Đây là bài **thực hành tổng hợp** của module **DATA_PERSISTENCE_FUNDAMENTALS**, áp dụng kiến thức về schema, SQL, giao dịch, lock, tính nhất quán, Java JDBC, kiểm thử, vận hành và sao lưu để giải quyết một lần tiến hóa dữ liệu thực tế. Mục tiêu không chỉ là viết được lệnh ALTER TABLE, mà là **đưa hệ thống qua nhiều phiên bản tương thích, backfill an toàn trong khi có traffic, chứng minh dữ liệu đúng, và chỉ contract khi đủ điều kiện**.

Ví dụ tập trung vào **PostgreSQL, Spring JDBC và Flyway**, với SQL minh họa có thể chuyển thành migration scripts trong một dự án được cấu hình phù hợp. Không có script nào trong bài được tự động thực thi trên hệ thống production. Các mốc triển khai V1–V4 và dữ liệu là giả định; mỗi hệ thống cần kiểm tra phiên bản PostgreSQL, driver, công cụ migration, quyền hạn, tải và kế hoạch phục hồi trước khi áp dụng.

## 1. Kết quả cần đạt

Sau khi hoàn thành, người học có thể:

- Lập **hợp đồng tương thích** giữa ứng dụng V1, V2, V3, V4 và schema theo từng pha.
- Thiết kế migration **expand → backfill → validate → contract** mà không buộc tất cả instance nâng cấp đồng thời.
- Phân biệt **schema migration** (DDL), **data backfill** (DML theo lô), **application rollout** và **cleanup/contract**.
- Bảo vệ dữ liệu khỏi **writer cũ hoạt động sau backfill**, bằng cơ chế đồng bộ hai chiều trong cửa sổ tương thích hoặc chiến lược tương đương đã chứng minh.
- Viết và vận hành backfill giới hạn batch, giao dịch ngắn, có **FOR UPDATE SKIP LOCKED**, tiến độ, retry và điều kiện hoàn tất.
- Kiểm chứng **giá trị cũ/mới khớp nhau, không còn NULL, old/new read-write đều hoạt động**, kể cả có cập nhật cạnh tranh.
- Triển khai ràng buộc **NOT VALID → VALIDATE CONSTRAINT** và đánh giá thời điểm đặt **NOT NULL**.
- Xây dựng kiểm thử Java/PostgreSQL trên database thật, phát hiện lỗi ở thứ tự rollout và khả năng rollback.
- Chuẩn bị runbook quan sát, phản ứng khi migration dở dang, giảm tải backfill và loại bỏ đường truy cập cột cũ.

## 2. Bài toán và hợp đồng nghiệp vụ

Giả sử hệ thống hồ sơ có API:

~~~text
GET /profiles/{id}       -> tên hiển thị hiện tại
PATCH /profiles/{id}     -> thay đổi tên hiển thị
POST /profiles           -> tạo hồ sơ mới
~~~

Trước thay đổi:

~~~sql
SELECT id, display_name
FROM public.profiles
WHERE tenant_id = ? AND id = ?;
~~~

Đích đến:

~~~sql
SELECT id, preferred_name
FROM public.profiles
WHERE tenant_id = ? AND id = ?;
~~~

Trong ví dụ, **preferred_name mang chính xác cùng ý nghĩa nghiệp vụ với display_name**; chỉ đổi hợp đồng lưu trữ và tên trường phía Java. Đây là lựa chọn có chủ đích để tập trung vào migration, không biến bài thực hành thành bài toán khó về việc suy ra họ/tên hay chuyển đổi dữ liệu không thể đảo ngược.

Bất biến bắt buộc:

1. Với một hồ sơ đang hoạt động, tên phải **không NULL**.
2. Trong giai đoạn hai cột cùng tồn tại, những thay đổi đã commit phải được nhìn thấy **nhất quán qua cả display_name và preferred_name**, sau khi backfill hoàn tất.
3. Mọi câu truy vấn sửa dữ liệu phải bảo vệ **tenant_id** và quyền truy cập tương ứng.
4. Một lần chạy backfill không được tự ý **ghi đè tên mới hơn** vừa được request hợp lệ cập nhật.
5. Rolling deployment không được yêu cầu dừng tất cả phiên bản cũ ngay lập tức.
6. Không xóa dữ liệu nguồn trước khi có đủ bằng chứng rằng ứng dụng và job không còn cần nó.

**Tên hai cột đồng bộ không đồng nghĩa chống mọi lost update giữa hai người dùng.** Nếu hai request cố sửa cùng hồ sơ với dữ liệu cũ, hệ thống vẫn cần version check, khóa hoặc quy tắc last-writer-wins theo nghiệp vụ. Migration chỉ phải bảo đảm không phát sinh thêm sự lệch giữa hai biểu diễn của cùng một giá trị.

## 3. Bốn phiên bản ứng dụng trong một migration

| Phiên bản | Cách đọc | Cách ghi | Điều kiện schema |
| --- | --- | --- | --- |
| **V1 – legacy** | display_name | display_name | Cột cũ tồn tại |
| **V2 – tương thích** | COALESCE(preferred_name, display_name) | preferred_name (trigger đồng bộ cột cũ) | Hai cột + trigger |
| **V3 – đích trung gian** | preferred_name | preferred_name | preferred_name đã được backfill/validate; vẫn giữ cột cũ |
| **V4 – sau contract** | preferred_name | preferred_name | Cột cũ đã được xóa an toàn |

Mỗi phiên bản không nhất thiết là một bản phát hành ứng dụng mới hoàn toàn; chúng đại diện cho **hợp đồng truy cập dữ liệu**. Nếu repository, batch job và API sử dụng các câu SQL khác nhau, tất cả đều phải được đưa vào ma trận.

Trong khoảng V1/V2 hoặc V1/V3 chạy cùng:

~~~text
V1 instance -- đọc/ghi display_name --+
                                      |
                                      v
                              PostgreSQL profiles
                         display_name | preferred_name
                                      ^
                                      |
V2/V3 instance -- đọc/ghi preferred_name

Trigger ở DB đồng bộ hai cột trong cùng row transaction.
~~~

Đây là **một phương án kỹ thuật cho migration này**, không phải khuyến nghị dùng trigger cho mọi thay đổi. Nếu không dùng trigger, đội ngũ phải có cơ chế khác chứng minh **mọi writer cũ đã được nâng cấp trước khi giá trị mới được coi là nguồn chính**, hoặc thiết kế dual-write đáng tin cậy theo từng giai đoạn.

## 4. Chuẩn bị môi trường thực hành

Thành phần:

| Thành phần | Vai trò |
| --- | --- |
| **PostgreSQL test** | Thực thi DDL, trigger, transaction và batch backfill thật |
| **pgJDBC** | Truy cập SQL theo JDBC |
| **Spring JDBC** | Viết repository V1/V2/V3 và kiểm thử API |
| **Flyway** | Quản lý lịch sử schema migration có version |
| **JUnit 5 + Testcontainers** | Chạy các bản ứng dụng giả lập trên PostgreSQL độc lập |
| **HikariCP / DataSource** | Mô phỏng connection pool và transaction boundaries |
| **Metrics/logs** | Theo dõi số hàng còn thiếu, lỗi, throughput, lock và WAL |

Không được hiểu bài thực hành như yêu cầu dùng tất cả công cụ cùng lúc. Với một ứng dụng JDBC thuần, vẫn có thể chứng minh logic bằng PostgreSQL và JUnit. Trong môi trường production, **phương thức chạy migration, quyền DDL và chính sách release** phải phù hợp hạ tầng thực tế.

### 4.1. Schema V1 làm mốc

~~~sql
CREATE TABLE public.profiles (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    display_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX profiles_tenant_id_id
ON public.profiles(tenant_id, id);

INSERT INTO public.profiles(tenant_id, display_name)
VALUES
    (10, 'An'),
    (10, 'Bình'),
    (20, 'Chi');
~~~

Bảng này là fixture dạy học; thực tế cần schema riêng, quyền user, migration baseline và constraints/index theo workload. Dữ liệu về tên là dữ liệu giả. **Không chạy CREATE TABLE hay INSERT trực tiếp lên production** khi chưa có kế hoạch và quyền thao tác.

### 4.2. Truy vấn xác nhận trạng thái ban đầu

~~~sql
SELECT id, tenant_id, display_name
FROM public.profiles
ORDER BY id;
~~~

Kỳ vọng có ba hồ sơ thuộc hai tenant. **preferred_name chưa tồn tại**; bất kỳ phiên bản ứng dụng nào tham chiếu đến nó trước bước expand đều sẽ lỗi.

## 5. Preflight trước khi triển khai schema

Trước khi chạy bất kỳ migration nào, cần trả lời:

- Hiện có bao nhiêu instance Java V1, bao nhiêu worker/cron/script quản trị vẫn dùng **display_name**?
- Có câu **SELECT *** được ánh xạ theo vị trí cột, hoặc code dựa vào danh sách cột cố định không?
- Có **view, trigger, function, stored procedure, CDC pipeline, report, ETL hoặc read replica** phụ thuộc tên cột không?
- Có **backup có thể restore** và phương án khôi phục sau DDL/data mistake chưa?
- Các table lớn bao nhiêu, có partition không, tốc độ ghi và transaction dài hiện tại thế nào?
- Sự thay đổi có ảnh hưởng **RPO, RTO, replication lag, WAL, locking** không?
- User chạy Flyway có quyền **ALTER TABLE, CREATE FUNCTION, CREATE TRIGGER** nhưng không quá quyền không cần thiết?
- Các phiên bản PostgreSQL được dùng ở production, staging và CI có tương thích với cú pháp migration không?

Chạy quan sát có kiểm soát:

~~~sql
SELECT count(*) AS total_profiles
FROM public.profiles;

SELECT relname, n_live_tup, n_dead_tup
FROM pg_stat_user_tables
WHERE relname = 'profiles';
~~~

**n_live_tup/n_dead_tup là thống kê ước lượng**, không thay cho COUNT chính xác. Một COUNT trên bảng cực lớn có thể tạo I/O đáng kể; hãy lập ngân sách cho lần kiểm chứng hoặc dùng phương pháp lấy mẫu có giới hạn trước khi quét toàn bảng.

## 6. Thứ tự triển khai tổng thể

~~~text
P0: DB schema V1 + ứng dụng V1
        |
        v
P1: EXPAND: thêm preferred_name nullable + trigger đồng bộ
        |   V1 vẫn chạy được
        v
P2: Deploy V2 dần: đọc fallback, ghi preferred_name
        |   V1 và V2 có thể chạy đồng thời
        v
P3: BACKFILL: cập nhật mọi hàng cũ còn preferred_name NULL
        |   giới hạn từng batch, commit, đo lỗi/tiến độ
        v
P4: VALIDATE: 0 NULL, 0 mismatch, ràng buộc được kiểm chứng
        |
        v
P5: Deploy V3: chỉ đọc/ghi preferred_name
        |   cột cũ và trigger vẫn được giữ để rollback
        v
P6: CONTRACT: chắc chắn không còn V1/V2/job tham chiếu cột cũ
        |   xóa trigger/function và display_name
        v
P7: V4 + vận hành/backup theo schema mới
~~~

**Không gộp tất cả bước vào một migration SQL/transaction khổng lồ.** P1 là schema change ngắn; P3 có thể chạy hàng giờ hoặc nhiều ngày theo workload; P4 đo dữ liệu; P6 là thay đổi phá tương thích cần gate riêng.

## 7. Pha EXPAND: thêm cột không phá V1

Một file Flyway ví dụ tên **V2__expand_profile_preferred_name.sql**:

~~~sql
ALTER TABLE public.profiles
ADD COLUMN preferred_name TEXT;
~~~

Đây là thay đổi **additive**: V1 vẫn có thể dùng display_name như trước. Với PostgreSQL, thêm cột nullable không có DEFAULT thường là thao tác metadata tương đối nhanh, nhưng **ALTER TABLE vẫn cần khóa DDL** và có thể phải chờ transaction dài. Không suy rằng nó luôn không khóa hoặc luôn hoàn thành tức thì.

Các nguyên tắc:

1. Đặt **lock_timeout** cho quá trình DDL theo chính sách deploy để migration thất bại có kiểm soát khi bị chặn.
2. Chạy một migration coordinator; tránh nhiều instance đồng thời cố thực hiện DDL ngoài sự điều phối Flyway.
3. Nếu lỗi do lock timeout, kiểm tra blocker rồi chạy lại theo quy trình; không tự kill một backend chỉ vì migration chờ.
4. Không đặt **NOT NULL** ngay lúc thêm cột vì hàng cũ chưa có dữ liệu mới.
5. Không xóa display_name và không yêu cầu V1 đổi SQL trong cùng release.

Truy vấn sau expand:

~~~sql
SELECT id, display_name, preferred_name
FROM public.profiles
ORDER BY id;
~~~

Với hàng cũ, **preferred_name hiện NULL**. Đây là trạng thái dự kiến cho đến khi backfill; ứng dụng V2 phải có fallback trong thời gian đó.

## 8. Chặn writer cũ làm lệch dữ liệu trong giai đoạn chuyển tiếp

Giả sử chỉ thêm cột rồi chạy:

~~~sql
UPDATE public.profiles
SET preferred_name = display_name
WHERE preferred_name IS NULL;
~~~

Ngay sau đó, V1 vẫn đang chạy:

~~~sql
UPDATE public.profiles
SET display_name = 'Tên mới từ V1'
WHERE id = 1;
~~~

Nếu không có đồng bộ, cột preferred_name vẫn chứa **giá trị cũ**. V2 đọc preferred_name sẽ trả thông tin lỗi thời ngay cả khi backfill từng báo **100%**.

Vì vậy, với rolling deployment có V1 thực sự còn quyền ghi, **chỉ chạy backfill rồi đổi sang đọc cột mới là không đủ**. Một giải pháp trong bài này là **BEFORE INSERT OR UPDATE trigger** đồng bộ hai hướng ở DB, trong cùng transaction đã thay đổi hồ sơ.

## 9. Trigger đồng bộ hai chiều trong pha chuyển tiếp

Một migration SQL tiếp theo, ví dụ **V3__sync_profile_names.sql**:

~~~sql
CREATE OR REPLACE FUNCTION public.sync_profile_name_columns()
RETURNS trigger
LANGUAGE plpgsql
AS $fn$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.display_name IS NULL AND NEW.preferred_name IS NULL THEN
            RAISE EXCEPTION
                USING ERRCODE = '23514',
                      MESSAGE = 'profile name is required';
        ELSIF NEW.display_name IS NULL THEN
            NEW.display_name := NEW.preferred_name;
        ELSIF NEW.preferred_name IS NULL THEN
            NEW.preferred_name := NEW.display_name;
        ELSIF NEW.display_name IS DISTINCT FROM NEW.preferred_name THEN
            RAISE EXCEPTION
                USING ERRCODE = '23514',
                      MESSAGE = 'profile name columns disagree';
        END IF;
    ELSE
        IF NEW.display_name IS DISTINCT FROM OLD.display_name
           AND NEW.preferred_name IS DISTINCT FROM OLD.preferred_name THEN
            IF NEW.display_name IS DISTINCT FROM NEW.preferred_name THEN
                RAISE EXCEPTION
                    USING ERRCODE = '23514',
                          MESSAGE = 'conflicting profile name writes';
            END IF;
        ELSIF NEW.display_name IS DISTINCT FROM OLD.display_name THEN
            NEW.preferred_name := NEW.display_name;
        ELSIF NEW.preferred_name IS DISTINCT FROM OLD.preferred_name THEN
            NEW.display_name := NEW.preferred_name;
        ELSIF NEW.preferred_name IS NULL THEN
            -- Chạm hàng legacy chưa backfill: đồng bộ ngay khi UPDATE.
            NEW.preferred_name := NEW.display_name;
        END IF;
    END IF;

    RETURN NEW;
END;
$fn$;

CREATE TRIGGER profiles_sync_name_columns
BEFORE INSERT OR UPDATE ON public.profiles
FOR EACH ROW
EXECUTE FUNCTION public.sync_profile_name_columns();
~~~

**Trigger này là mẫu dạy học cho một phép đổi tên cột bảo toàn ý nghĩa**, không phải template cho mọi kiểu thay đổi dữ liệu. Nó được thiết kế để xử lý cả INSERT và UPDATE với giá trị thuộc V1/V2, và từ chối trường hợp một statement cố ghi hai cột khác nhau.

### 9.1. Phân tích từng trường hợp

| Thao tác | Kết quả kỳ vọng |
| --- | --- |
| V1 INSERT chỉ display_name | Trigger điền preferred_name trước khi kiểm tra NOT NULL của display_name |
| V2 INSERT chỉ preferred_name | Trigger điền display_name để V1 vẫn đọc được |
| V1 UPDATE chỉ display_name | Trigger sao chép giá trị mới sang preferred_name |
| V2 UPDATE chỉ preferred_name | Trigger sao chép giá trị mới sang display_name |
| UPDATE cả hai cột bằng cùng giá trị | Chấp nhận |
| UPDATE cả hai cột bằng hai giá trị khác nhau | Từ chối bằng lỗi có chủ đích |
| Hàng cũ preferred_name NULL được UPDATE một cột không liên quan | Trigger bổ sung preferred_name từ display_name |
| Backfill ghi preferred_name từ display_name | Hai giá trị tương ứng; trigger giữ đồng bộ |

**IS DISTINCT FROM** cần thiết vì so sánh **NULL** bằng dấu bằng thông thường có kết quả unknown. Việc dùng phép so sánh NULL-safe giúp trường hợp hàng cũ chưa backfill được xử lý rõ ràng.

### 9.2. Giới hạn và chi phí

- Trigger tăng chi phí ghi và độ phức tạp; phải đo thời gian, replication/WAL và hành vi khi import hàng loạt.
- Trigger **không ngăn last-writer-wins** giữa hai giao dịch cùng sửa tên; cần **version check/optimistic locking** nếu không được phép ghi đè.
- Các writers dùng COPY, bulk SQL, stored procedure hoặc đặc quyền đặc biệt cần được kiểm thử riêng; **không được tắt trigger** trong quá trình import/backfill mà không có thiết kế thay thế.
- Cần thống nhất cách chuẩn hóa chuỗi, NULL, whitespace và encoding; ví dụ giả định hai cột có cùng nghĩa và kiểu.
- Khi migration kết thúc, trigger phải được loại bỏ **sau khi không còn writer cần cột cũ**, không loại sớm chỉ để tiết kiệm CPU.

## 10. Các câu SQL smoke test ngay sau EXPAND

Trong database **dành riêng cho kiểm thử**, chạy:

~~~sql
-- Tạo bằng giao diện của V1.
INSERT INTO public.profiles(tenant_id, display_name)
VALUES (10, 'Old API insert')
RETURNING id, display_name, preferred_name;

-- Tạo bằng giao diện của V2.
INSERT INTO public.profiles(tenant_id, preferred_name)
VALUES (10, 'New API insert')
RETURNING id, display_name, preferred_name;

-- Sửa như V1, trigger phải cập nhật cả hai cột.
UPDATE public.profiles
SET display_name = 'Updated from legacy'
WHERE tenant_id = 10 AND display_name = 'Old API insert'
RETURNING id, display_name, preferred_name;

-- Sửa như V2, trigger phải cập nhật cả hai cột.
UPDATE public.profiles
SET preferred_name = 'Updated from new'
WHERE tenant_id = 10 AND preferred_name = 'New API insert'
RETURNING id, display_name, preferred_name;
~~~

Với từng câu có **RETURNING**, xác nhận hai cột bằng nhau. Đây là smoke test **trên fixture**, không phải dữ liệu production. Trong production, dùng kiểm thử application và telemetry an toàn; không tạo hồ sơ giả vào bảng người dùng thật mà thiếu quy trình dọn dẹp.

Kiểm tra trường hợp mâu thuẫn:

~~~sql
-- Phải thất bại trên dữ liệu test vì hai giá trị khác nhau.
INSERT INTO public.profiles(tenant_id, display_name, preferred_name)
VALUES (10, 'A', 'B');
~~~

Sau exception PostgreSQL trong transaction, phải **ROLLBACK** hoặc rollback tới savepoint thích hợp trước khi chạy câu SQL khác trên cùng connection.

## 11. Mã Java V1: hợp đồng cột cũ

Một repository JDBC tối giản:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;

public final class ProfileRepositoryV1 {
    private final JdbcTemplate jdbc;

    public ProfileRepositoryV1(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public String getName(long tenantId, long id) {
        return jdbc.queryForObject(
            """
            SELECT display_name
            FROM public.profiles
            WHERE tenant_id = ? AND id = ?
            """,
            String.class, tenantId, id);
    }

    public int rename(long tenantId, long id, String name) {
        return jdbc.update(
            """
            UPDATE public.profiles
            SET display_name = ?
            WHERE tenant_id = ? AND id = ?
            """,
            name, tenantId, id);
    }
}
~~~

Code V1 không biết preferred_name tồn tại, nhưng vẫn chạy được sau EXPAND vì cột cũ được giữ và trigger đồng bộ. **tenantId phải xuất phát từ ngữ cảnh xác thực/ủy quyền**, không tin tùy ý header của client. Ví dụ chưa trình bày toàn bộ validation, optimistic version hoặc mapping lỗi not-found.

## 12. Mã Java V2: đọc fallback, ghi cột mới

~~~java
import org.springframework.jdbc.core.JdbcTemplate;

public final class ProfileRepositoryV2 {
    private final JdbcTemplate jdbc;

    public ProfileRepositoryV2(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public String getName(long tenantId, long id) {
        return jdbc.queryForObject(
            """
            SELECT COALESCE(preferred_name, display_name)
            FROM public.profiles
            WHERE tenant_id = ? AND id = ?
            """,
            String.class, tenantId, id);
    }

    public int rename(long tenantId, long id, String newName) {
        return jdbc.update(
            """
            UPDATE public.profiles
            SET preferred_name = ?
            WHERE tenant_id = ? AND id = ?
            """,
            newName, tenantId, id);
    }
}
~~~

**COALESCE** đảm bảo V2 đọc được hàng legacy chưa backfill. Khi V2 ghi preferred_name, trigger cập nhật display_name trong cùng transaction; V1 sẽ nhìn thấy giá trị sau commit.

Nếu V2 cần tạo mới:

~~~sql
INSERT INTO public.profiles(tenant_id, preferred_name)
VALUES (?, ?);
~~~

Trigger BEFORE INSERT phải còn hoạt động để điền **display_name**, vì schema V1 vẫn có ràng buộc **display_name NOT NULL**.

Lưu ý:

- V2 **chỉ được deploy sau khi P1 thêm cột và P1/P2 bật trigger**. Nếu code dùng preferred_name trước DDL, ứng dụng gặp lỗi undefined column.
- Fallback chỉ giải quyết hàng chưa backfill; nó không thay thế đồng bộ khi **writer V1 tiếp tục ghi**.
- Nếu V2 dùng JPA entity mapping, cần kiểm tra **dynamic update, dirty checking và INSERT columns** để code ORM không vô tình ghi cả hai cột khác nhau.
- API nên giữ cấu trúc response tương thích với client, không đồng thời đổi contract HTTP và DB khi không bắt buộc.

## 13. Ma trận tương thích từng cặp phiên bản

| Schema / app | V1 | V2 | V3 |
| --- | --- | --- | --- |
| S0: chỉ display_name | **Đạt** | **Không đạt**: thiếu preferred_name | **Không đạt** |
| S1: hai cột + trigger, backfill dở | **Đạt** | **Đạt** nhờ COALESCE + trigger | **Chưa đạt**: có NULL |
| S2: hai cột + trigger, backfill và validation xong | **Đạt** | **Đạt** | **Đạt** |
| S3: chỉ preferred_name | **Không đạt** | **Không đạt** do V2 còn nhắc display_name trong COALESCE | **Đạt** |

Ma trận trên là **hợp đồng cần chứng minh bằng test**, không chỉ là sơ đồ lý thuyết. Đặc biệt: V2 **vẫn phụ thuộc cột cũ khi đọc**, nên **không được contract khi còn instance V2**, dù mọi hàng đã được backfill và V2 chỉ ghi cột mới.

Để không bị mắc kẹt lúc rollback, mỗi thay đổi phá tương thích phải có một **cửa sổ quan sát** trước khi xóa cột cũ.

## 14. BACKFILL: chia hàng triệu bản ghi thành các lô nhỏ

Sau khi trigger đã hoạt động và V2 có thể rollout, nhiều hàng V1 đã tồn tại sẽ có preferred_name NULL. Backfill theo batch:

~~~sql
WITH batch AS (
    SELECT id
    FROM public.profiles
    WHERE preferred_name IS NULL
    ORDER BY id
    LIMIT 500
    FOR UPDATE SKIP LOCKED
)
UPDATE public.profiles AS p
SET preferred_name = p.display_name
FROM batch
WHERE p.id = batch.id
  AND p.preferred_name IS NULL
RETURNING p.id;
~~~

Chạy câu SQL trên **trong một transaction ngắn**, rồi COMMIT. Lặp lại cho đến khi đã xử lý hết những hàng thiếu.

**Tại sao phải SKIP LOCKED?**

- Nếu một request đang cập nhật hồ sơ, backfill không cần chờ khóa của nó lâu; có thể bỏ qua hàng ấy và xử lý trong lượt tiếp theo.
- Nhiều worker backfill có thể tránh tranh cùng một hàng, nếu orchestration được thiết kế đúng.
- Câu UPDATE trên hàng được khóa dùng giá trị **display_name của hàng tại thời điểm UPDATE**; cùng row lock và trigger giúp tránh ghi đè thiếu kiểm soát lên update đang thực thi.

**SKIP LOCKED không tạo snapshot toàn cục và không bảo đảm hàng được quét theo thứ tự tuyệt đối**. Nó phù hợp công việc backfill có thể xử lý lại/idempotent, không phù hợp dùng làm một API phân trang yêu cầu thứ tự/bản chụp ổn định.

### 14.1. Những lỗi cần tránh

~~~sql
-- Không nên thực hiện trên bảng rất lớn trong một transaction:
UPDATE public.profiles
SET preferred_name = display_name
WHERE preferred_name IS NULL;
~~~

Một UPDATE khổng lồ có thể giữ nhiều row locks, sinh WAL lớn, làm tăng replication lag, tốn disk và kéo dài rollback khi có lỗi. Cần đo kích thước và tốc độ trên môi trường tương đương trước khi chọn batch size.

~~~sql
-- KHÔNG an toàn khi writer cũ vẫn đang hoạt động nếu không có đồng bộ:
UPDATE public.profiles
SET preferred_name = display_name;
~~~

Không nên viết đè mọi hàng đã có preferred_name. Giới hạn **WHERE preferred_name IS NULL** để không vô tình đặt lại dữ liệu mới hoặc hợp thức hóa một trạng thái đang mâu thuẫn.

## 15. Java JDBC: thực thi một batch trong transaction

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class ProfileBackfill {
    private final DataSource source;

    public ProfileBackfill(DataSource source) {
        this.source = source;
    }

    public int runOneBatch(int batchSize) throws SQLException {
        if (batchSize < 1 || batchSize > 1000) {
            throw new IllegalArgumentException("batchSize ngoài giới hạn");
        }

        String sql = """
            WITH batch AS (
                SELECT id FROM public.profiles
                WHERE preferred_name IS NULL
                ORDER BY id
                LIMIT ?
                FOR UPDATE SKIP LOCKED
            )
            UPDATE public.profiles AS p
            SET preferred_name = p.display_name
            FROM batch
            WHERE p.id = batch.id
              AND p.preferred_name IS NULL
            """;

        try (Connection connection = source.getConnection()) {
            connection.setAutoCommit(false);
            try {
                int updated;
                try (PreparedStatement st =
                             connection.prepareStatement(sql)) {
                    st.setInt(1, batchSize);
                    st.setQueryTimeout(20);
                    updated = st.executeUpdate();
                }
                connection.commit();
                return updated;
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }
}
~~~

Đây là lớp thực thi **một batch**, không phải toàn bộ scheduler. Trong hệ thống thật phải có giới hạn worker, deadline, quan sát, cancellation, ghi nhận progress và cơ chế dừng khi database bị tải cao. **setQueryTimeout** là timeout của JDBC statement theo driver, không phải giới hạn tổng thời gian job.

Nếu một COMMIT mất phản hồi do lỗi mạng, client có thể không biết batch đã commit chưa. Vì thao tác **chỉ ghi preferred_name khi NULL** và trigger đồng bộ, có thể chạy lại batch an toàn theo điều kiện dữ liệu của bài thực hành; tuy vậy, hệ thống vẫn phải xác minh trạng thái DB và không coi mọi thao tác ETL đều idempotent như thế.

## 16. Orchestration và điều kiện backfill hoàn tất

Một worker có thể gọi **runOneBatch(500)** liên tục, giảm tốc khi PostgreSQL/replica chịu tải và ghi metrics. Nhưng **updated = 0 không đủ chứng minh đã hoàn tất**: nếu các hàng còn thiếu đang bị transaction khác khóa, SKIP LOCKED có thể bỏ qua tất cả.

Quy trình tốt:

1. Chạy từng batch, commit, đo **rows_updated, elapsed_ms, retries, SQLSTATE**.
2. Khi nhiều lượt trả 0, dừng sinh công việc dồn dập và kiểm tra backlog thực:

~~~sql
SELECT count(*) AS pending
FROM public.profiles
WHERE preferred_name IS NULL;
~~~

3. Nếu còn hàng, chờ/backoff rồi thử lại hoặc điều tra lock/transaction lâu; không đánh dấu hoàn thành.
4. Khi pending = 0, kiểm tra **mismatch** giữa hai cột và chạy kiểm chứng cùng các ứng dụng V1/V2 đang hoạt động.
5. Có một **cửa sổ quan sát** sau khi backfill báo 0, để phát hiện writer/trigger/path bất thường trước khi thêm ràng buộc chặt.

Lưu ý **COUNT toàn bảng** có thể tốn I/O trên bảng lớn. Chọn tần suất hợp lý, đặc biệt tránh COUNT sau mỗi batch 500 hàng. Có thể dùng metrics tiến độ để theo dõi liên tục, còn COUNT chính xác làm gate kiểm chứng theo lịch.

## 17. Kiểm chứng dữ liệu trước khi công bố backfill hoàn tất

Một job báo **processed = tổng số hàng từ một snapshot** chưa đủ để bảo đảm mọi hàng còn đúng sau khi có writer đồng thời. Hãy xây dựng các truy vấn kiểm chứng rõ ràng:

~~~sql
SELECT
    count(*) AS total,
    count(*) FILTER (
        WHERE preferred_name IS NULL
    ) AS missing_new_name,
    count(*) FILTER (
        WHERE preferred_name IS DISTINCT FROM display_name
    ) AS mismatched_names
FROM public.profiles;
~~~

Sau backfill và khi trigger hoạt động đúng, kỳ vọng:

~~~text
missing_new_name = 0
mismatched_names = 0
~~~

**IS DISTINCT FROM** phát hiện cả trường hợp một bên NULL, không bỏ sót vì ba giá trị logic TRUE/FALSE/UNKNOWN của SQL. Từ đó, một hàng bị lệch sẽ là tín hiệu lỗi cần điều tra thay vì âm thầm chọn cột nào đó để che bất thường.

Để tìm những hàng cụ thể trên database test hoặc truy vấn điều tra có kiểm soát:

~~~sql
SELECT id, tenant_id, display_name, preferred_name
FROM public.profiles
WHERE preferred_name IS DISTINCT FROM display_name
ORDER BY id
LIMIT 100;
~~~

Trong production, giá trị tên là dữ liệu cá nhân. Chỉ hiển thị chi tiết cho vai trò được phép, không đưa toàn bộ dữ liệu vào metrics/traces/logs; metrics chỉ cần số lượng và xu hướng, còn mẫu điều tra cần quyền truy cập và retention phù hợp.

### 17.1. Kiểm tra không chỉ tổng số, mà còn hành vi

Test dữ liệu tĩnh không bắt được một writer cũ bất ngờ bật lại sau vài phút. Cần kiểm tra:

- **V1 INSERT** với chỉ display_name: trigger điền preferred_name.
- **V2 INSERT** với chỉ preferred_name: trigger điền display_name.
- **V1 UPDATE sau khi một hàng đã backfill**: preferred_name thay đổi theo.
- **V2 UPDATE**: display_name thay đổi theo.
- **V1 và V2 cùng UPDATE một hàng**: sau khi các transaction commit, hai cột vẫn giống nhau.
- **UPDATE hai cột mâu thuẫn**: bị từ chối theo thiết kế.
- **DELETE** và đọc theo tenant: không phát sinh thay đổi quyền hoặc rò dữ liệu.
- **Ứng dụng V1/V2 sau deploy**: không có lỗi undefined column, NULL không mong muốn hoặc query plan thoái hóa nghiêm trọng.

**Quan hệ đồng bộ hai cột** khác với **thứ tự cập nhật nghiệp vụ**. Nếu V1 và V2 cùng thay đổi một trường, kết quả cuối có thể là giá trị của transaction commit sau theo cơ chế DB. Muốn không bỏ qua chỉnh sửa của người dùng khác phải có thêm optimistic version check hoặc conflict workflow.

## 18. Thêm ràng buộc dữ liệu theo cách có thể kiểm soát

Chỉ sau khi backfill hoàn tất và xác minh không còn NULL/mismatch, hãy chuyển từ trạng thái mềm sang ràng buộc cứng. Với PostgreSQL:

~~~sql
ALTER TABLE public.profiles
ADD CONSTRAINT profiles_preferred_name_present
CHECK (preferred_name IS NOT NULL) NOT VALID;

ALTER TABLE public.profiles
VALIDATE CONSTRAINT profiles_preferred_name_present;
~~~

**NOT VALID** cho phép thêm CHECK mà chưa quét kiểm chứng toàn bộ hàng cũ ngay thời điểm tạo constraint, nhưng **constraint vẫn được thực thi đối với những INSERT/UPDATE mới**. Nếu còn một hàng cũ preferred_name NULL và code UPDATE cột không liên quan, trigger trong ví dụ sẽ điền preferred_name trước khi constraint kiểm tra; tuy vậy tốt nhất vẫn hoàn tất backfill trước để giảm rủi ro.

**VALIDATE CONSTRAINT** thực hiện kiểm tra dữ liệu hiện có. Nó vẫn cần scan bảng và dùng locks phù hợp, nhưng thường có mức ảnh hưởng đến thao tác ghi thấp hơn nhiều thay đổi DDL yêu cầu khóa mạnh. Phải kiểm tra phiên bản PostgreSQL, thời lượng và tải thực; **không gọi nó là thao tác luôn không khóa**.

Khi đã validate và đủ điều kiện, có thể đặt NOT NULL cho cột:

~~~sql
ALTER TABLE public.profiles
ALTER COLUMN preferred_name SET NOT NULL;
~~~

Trên một số phiên bản PostgreSQL, sự tồn tại của CHECK đã được validate chứng minh preferred_name không NULL có thể giúp tránh full-table scan ở bước SET NOT NULL; nhưng bước này vẫn cần **DDL lock** và có hành vi phụ thuộc phiên bản. Không khẳng định luôn tức thời trên bảng lớn.

### 18.1. Ràng buộc nhất quán hai biểu diễn

Trong cửa sổ migration, muốn DB chặn mọi thay đổi mới làm hai cột không khớp, có thể bổ sung sau khi backfill:

~~~sql
ALTER TABLE public.profiles
ADD CONSTRAINT profiles_name_columns_equal
CHECK (preferred_name IS NOT DISTINCT FROM display_name) NOT VALID;

ALTER TABLE public.profiles
VALIDATE CONSTRAINT profiles_name_columns_equal;
~~~

Ràng buộc này làm rõ contract rằng hai cột cùng mang một ý nghĩa. **Trigger xử lý đồng bộ**, còn **CHECK** phát hiện trạng thái sai nếu một code path vô tình ghi khác nhau hoặc trigger bị thay thế sai.

Cần lưu ý trước khi áp constraint: một migration/script đặc biệt hoặc bulk import từng bỏ qua trigger sẽ làm UPDATE/INSERT bị từ chối. **Fail-fast là điều mong muốn cho correctness**, nhưng phải có runbook và thử nghiệm để tránh bất ngờ khi triển khai.

## 19. V3: chuyển hoàn toàn sang cột mới sau validation

Khi dữ liệu đã đủ, ứng dụng V3 chỉ tham chiếu preferred_name:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;

public final class ProfileRepositoryV3 {
    private final JdbcTemplate jdbc;

    public ProfileRepositoryV3(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public String getName(long tenantId, long id) {
        return jdbc.queryForObject(
            """
            SELECT preferred_name
            FROM public.profiles
            WHERE tenant_id = ? AND id = ?
            """,
            String.class, tenantId, id);
    }

    public int rename(long tenantId, long id, String newName) {
        return jdbc.update(
            """
            UPDATE public.profiles
            SET preferred_name = ?
            WHERE tenant_id = ? AND id = ?
            """,
            newName, tenantId, id);
    }
}
~~~

V3 **không còn tham chiếu display_name** ở bất kỳ câu SQL nào. Trong lúc rolling deployment V1/V2/V3, cột cũ và trigger vẫn tồn tại, nên:

- V1 tiếp tục đọc/ghi display_name.
- V2 tiếp tục đọc COALESCE và ghi preferred_name.
- V3 chỉ đọc/ghi preferred_name.
- Trigger giữ hai biểu diễn thống nhất cho đến khi hết giai đoạn chuyển tiếp.

**Không contract ngay khi phiên bản V3 đầu tiên khởi động.** Phải xác minh tất cả instance, background jobs, task queues, batch tools, consumer và kế hoạch rollback đã không còn phụ thuộc cột cũ. Một instance V2 sống sót sau rollout vẫn sẽ lỗi nếu cột display_name bị xóa.

## 20. CONTRACT: xóa cột cũ khi và chỉ khi đã hết phụ thuộc

Sau thời gian quan sát và khi mọi code path chỉ dùng preferred_name, một migration contract minh họa:

~~~sql
BEGIN;

DROP TRIGGER profiles_sync_name_columns
ON public.profiles;

DROP FUNCTION public.sync_profile_name_columns();

ALTER TABLE public.profiles
DROP COLUMN display_name;

COMMIT;
~~~

Nếu đã bổ sung CHECK so sánh hai cột ở mục 18, trước khi DROP COLUMN phải xử lý dependency:

~~~sql
ALTER TABLE public.profiles
DROP CONSTRAINT IF EXISTS profiles_name_columns_equal;
~~~

**Thứ tự đúng của migration contract** phải đặt DROP CONSTRAINT so sánh **trước** khi xóa cột display_name (và cùng transaction nếu cần). Không copy riêng khối đầu mà bỏ qua dependency thực tế. Một script đầy đủ cho trạng thái đã có constraint sẽ là:

~~~sql
BEGIN;

ALTER TABLE public.profiles
DROP CONSTRAINT IF EXISTS profiles_name_columns_equal;

DROP TRIGGER profiles_sync_name_columns ON public.profiles;
DROP FUNCTION public.sync_profile_name_columns();
ALTER TABLE public.profiles DROP COLUMN display_name;

COMMIT;
~~~

Trong production phải kiểm tra **views, functions, triggers khác, index, grants, policies và consumer** còn nhắc display_name không. Nếu còn dependency, PostgreSQL có thể từ chối DROP COLUMN hoặc ứng dụng sẽ lỗi sau deploy. **Không dùng CASCADE để xóa bừa các dependency**; cần xác định từng đối tượng và chủ sở hữu.

Các DDL contract có thể cần khóa mạnh. Cần lập lịch, đặt lock timeout, theo dõi blockers và kế hoạch quay lại nếu lock không lấy được; đừng biến deploy schema thành gián đoạn kéo dài vì chờ transaction cũ.

### 20.1. Vì sao contract thường không có rollback tức thời?

Khi đã DROP display_name, phiên bản V1 và V2 **không thể hoạt động bằng SQL cũ**. Rollback ứng dụng về V1 hoặc V2 lúc này sẽ lỗi. Ngoài ra, tái tạo một cột display_name rỗng không có nghĩa đã tái tạo ngay dữ liệu, constraints, index và hành vi như trước.

Vì vậy, contract cần một quyết định release riêng: **chấm dứt cửa sổ rollback về những binary cũ**, có bản dự phòng dữ liệu phù hợp và cam kết không còn caller phụ thuộc schema cũ.

## 21. Flyway: tách migration có version khỏi backfill vận hành

Một cấu trúc file mô tả ý tưởng:

~~~text
db/migration/
  V1__create_profiles.sql
  V2__expand_profile_preferred_name.sql
  V3__sync_profile_names.sql
  V4__add_preferred_name_constraints.sql
  V5__contract_display_name.sql
~~~

**Đây là những tên file ví dụ, không phải file được tạo trong nhiệm vụ này.** Một dự án thật có thể dùng version có timestamp hoặc prefix khác theo chuẩn chung. Cần chú ý thứ tự: **V4 chỉ được chạy sau khi backfill đã hoàn tất**, và **V5 chỉ sau rollout V3 hoàn toàn**. Nếu ứng dụng luôn auto-run mọi pending Flyway migration khi khởi động, việc đóng gói V4/V5 sớm trong cùng artifact có thể làm chúng chạy **trước khi gate dữ liệu/deploy được phê duyệt**.

Một cách triển khai:

1. Release schema expand (V2, V3) được áp bởi migration coordinator.
2. Deploy V2 application.
3. Chạy **backfill job riêng có checkpoints/metrics**, không đặt hàng triệu UPDATE vào một Flyway script mặc định chạy một transaction lớn.
4. Khi kiểm chứng dữ liệu PASS, mới cho phép migration constraint V4 vào luồng chạy.
5. Deploy V3 application hoàn toàn, xác nhận hết dependency cũ và hết cửa sổ rollback V1/V2.
6. Chỉ sau đó mới cho phép V5 contract.

Flyway ghi lịch sử DDL migrations; nó **không chứng minh backfill đúng hoặc deployment không còn phiên bản cũ**. Cần lưu tiến độ và bằng chứng ngoài lịch sử schema, ví dụ qua job metrics, change record hoặc bảng điều phối an toàn được hệ thống quản lý.

**Không sửa nội dung migration versioned đã chạy** trên một môi trường để “cho nhanh”. Nếu cần thay đổi, thường tạo migration version mới theo quy trình và xử lý checksum/history hợp lệ; không tự ý chỉnh lịch sử production.

## 22. Xử lý backfill khi ứng dụng tiếp tục ghi

Xét chuỗi sự kiện sau:

~~~text
T0: Hàng id=42, display_name='An', preferred_name=NULL.
T1: Worker backfill khóa id=42.
T2: V1 muốn đổi display_name='An mới', phải chờ row lock.
T3: Backfill đặt preferred_name='An', COMMIT.
T4: V1 UPDATE display_name='An mới'.
    Trigger trong transaction V1 đặt preferred_name='An mới'.
T5: V1 COMMIT.

Cuối cùng: cả hai cột = 'An mới'.
~~~

Nếu thứ tự đảo lại:

~~~text
T1: V1 UPDATE display_name='An mới' và trigger điền preferred_name.
T2: V1 COMMIT.
T3: Worker backfill tìm WHERE preferred_name IS NULL.
    Hàng này không còn thuộc tập cần backfill.
~~~

**Hai lịch đều giữ cùng kết quả mong muốn** nhờ trigger và điều kiện WHERE. Nếu không có trigger, lịch thứ nhất có thể khiến preferred_name trở nên stale sau UPDATE của V1.

### 22.1. Không backfill bằng cách đọc cũ ở Java rồi UPDATE vô điều kiện

Một anti-pattern:

~~~text
SELECT id, display_name FROM profiles   (đọc 10.000 hàng)
... xử lý trên Java trong 2 phút ...
UPDATE profiles SET preferred_name = ? WHERE id = ?
~~~

Giữa lúc SELECT và UPDATE, tên có thể đã thay đổi. Nếu code không kiểm tra version/state, nó có thể đặt preferred_name theo **giá trị đã cũ**. Với bài thực hành này, nên để database **đọc display_name tại thời điểm UPDATE và giữ row lock trong một transaction ngắn**. Nếu bắt buộc chuyển đổi ở Java, dùng version compare-and-set hoặc thiết kế chụp dữ liệu/đối soát riêng.

### 22.2. Không tắt trigger để backfill cho nhanh

Tắt trigger có thể gây mất đồng bộ khi V1/V2 ghi đồng thời, và cần quyền cao. Trước khi đánh đổi bất kỳ safeguard nào để tối ưu throughput, phải có phương án tương đương được chứng minh và kiểm thử dưới contention. Với migration không cho phép dừng writer, **tính đúng là điều kiện ưu tiên**.

## 23. JUnit 5 và Testcontainers: kiểm thử compatibility trên DB thật

Khung test Java với PostgreSQL Testcontainers:

~~~java
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
class ProfileMigrationCompatibilityIT {
    @Container
    static PostgreSQLContainer<?> database =
            new PostgreSQLContainer<>("postgres:16")
                    .withDatabaseName("profile_migration")
                    .withUsername("test_user")
                    .withPassword("test_password");

    private Connection connect() throws Exception {
        return DriverManager.getConnection(
                database.getJdbcUrl(),
                database.getUsername(),
                database.getPassword());
    }

    @Test
    void oldWriterAndNewReaderSeeSameValue() throws Exception {
        // Fixture/bootstrap chạy V1, V2 và V3 SQL migrations
        // trước khi vào test này; ví dụ bằng Flyway trong @BeforeAll.
        try (Connection oldConnection = connect();
             Connection newConnection = connect()) {

            long id;
            try (PreparedStatement insert = oldConnection.prepareStatement(
                    """
                    INSERT INTO public.profiles(tenant_id, display_name)
                    VALUES (10, 'An') RETURNING id
                    """);
                 ResultSet rs = insert.executeQuery()) {
                assertTrue(rs.next());
                id = rs.getLong(1);
            }

            try (PreparedStatement rename = oldConnection.prepareStatement(
                    """
                    UPDATE public.profiles SET display_name = ?
                    WHERE tenant_id = ? AND id = ?
                    """)) {
                rename.setString(1, "An từ V1");
                rename.setLong(2, 10L);
                rename.setLong(3, id);
                assertEquals(1, rename.executeUpdate());
            }

            try (PreparedStatement read = newConnection.prepareStatement(
                    """
                    SELECT display_name, preferred_name
                    FROM public.profiles
                    WHERE tenant_id = ? AND id = ?
                    """)) {
                read.setLong(1, 10L);
                read.setLong(2, id);
                try (ResultSet rs = read.executeQuery()) {
                    assertTrue(rs.next());
                    assertEquals("An từ V1", rs.getString(1));
                    assertEquals("An từ V1", rs.getString(2));
                }
            }
        }
    }
}
~~~

**Khung test chưa độc lập chạy ngay**: phải thêm dependency Testcontainers/JUnit/pgJDBC, bootstrap Flyway migrations **trước test** và cô lập fixture giữa các test. Đừng chạy migration contract V5 trong test này, vì nó cố ý cần cả cột cũ và mới.

Testcontainers giúp test **PostgreSQL thật** thay vì mock DB hoặc H2, nhưng không tự tái tạo production load, IAM, replication, disk performance và deployment topology. Cần kết hợp CI integration test với staging rehearsal.

## 24. Kiểm thử hai writer đồng thời

Một test cần chứng minh bất biến **hai cột luôn bằng nhau sau commit**, kể cả khi V1/V2 cùng UPDATE một hàng:

~~~text
Fixture: id=42, display_name=preferred_name='Start'

Worker A:
  Connection A độc lập
  UPDATE profiles SET display_name='Legacy write' WHERE id=42

Worker B:
  Connection B độc lập
  UPDATE profiles SET preferred_name='New write' WHERE id=42

Coordinator:
  CountDownLatch hoặc CyclicBarrier cho hai worker bắt đầu gần nhau.
  Chờ cả hai commit bằng Future.get(timeout).
  Đọc bằng Connection C mới.

Assertion:
  display_name = preferred_name.
  Giá trị cuối thuộc tập {'Legacy write','New write'}.
~~~

**Không assert cứng worker A hoặc B phải thắng** nếu không chủ động điều phối thứ tự commit. PostgreSQL dùng row locks để tuần tự hóa hai UPDATE cùng hàng; trigger đảm bảo cột tương ứng cũng được cập nhật. Khi cả hai thay cùng một trường theo ý định nghiệp vụ khác nhau, lần ghi đến sau vẫn có thể ghi đè lần trước: hãy thêm **version** hoặc điều kiện precondition nếu nghiệp vụ không cho phép.

Các test đồng thời còn cần:

- Tạo **hai physical/logical connections độc lập**, pool có ít nhất hai connection khả dụng.
- Dùng **CountDownLatch với timeout** để điều phối, không dựa vào Thread.sleep.
- Đặt statement/transaction timeout cho ca deadlock/failure.
- Dùng ID fixture riêng và **commit dữ liệu trước khi worker đọc**.
- Đóng thread, connection và transaction trong finally khi assertion thất bại.
- Kiểm tra cuối cùng bằng connection **mới**, tránh identity map hoặc snapshot cũ.

## 25. Ma trận CI bắt buộc trước release

| Bài test | Schema | Ứng dụng/luồng | Kỳ vọng |
| --- | --- | --- | --- |
| T1 | S0 legacy | V1 | Tạo, đọc, sửa hoạt động |
| T2 | S1 expanded | V1 | Không lỗi, trigger đồng bộ ghi mới |
| T3 | S1 expanded, có hàng cũ NULL | V2 | Đọc COALESCE đúng, UPDATE không lệch |
| T4 | S1 expanded, đang backfill | V1 + V2 | Không mất đồng bộ khi ghi đồng thời |
| T5 | S2 validated | V1 + V2 + V3 | Cả ba đọc/ghi theo hợp đồng |
| T6 | S2 validated | V3 | Không truy vấn display_name ở bất kỳ code path nào |
| T7 | S3 contracted | V3/V4 | Hoạt động đúng chỉ với preferred_name |
| T8 | S3 contracted | V1/V2 | **Kỳ vọng không tương thích**; xác nhận điều kiện rollback đã hết |
| T9 | S1/S2 | Backfill crash giữa chừng | Chạy lại an toàn, cuối cùng NULL=0/mismatch=0 |
| T10 | S1/S2 | Hai writers cạnh tranh | Hai cột nhất quán; nếu dùng version thì conflict đúng |
| T11 | S1/S2 | Payload NULL hoặc hai cột mâu thuẫn | Constraint/trigger từ chối theo hợp đồng |
| T12 | S1/S2 | Import/batch/consumer cũ | Không bỏ qua trigger hay ghi sai cột |

**Ma trận không có nghĩa mọi nhánh phải chạy trong cùng một JVM.** Với các release cũ, có thể chạy container/binary tương ứng với schema stage được dựng bằng Flyway; dùng test fixture thực và assertions từ API hoặc DB.

Đừng lẫn:

- **Compatibility test**: phiên bản này có hoạt động trên schema kia không?
- **Data correctness test**: trạng thái dữ liệu có đúng và đồng bộ không?
- **Performance test**: thời gian query/lock/WAL/throughput có đáp ứng giới hạn không?
- **Operational test**: migration có resume sau crash và dừng an toàn khi DB quá tải không?

Để chấp nhận deploy, cần ít nhất bằng chứng cho **bốn nhóm**, không chỉ compilation và schema migration đã chạy.

## 26. Fault injection và khả năng tiếp tục backfill

Một backfill đã commit theo batch phải chịu được crash. Bài test:

1. Tạo 2.000 hàng legacy trước khi expand (preferred_name ban đầu NULL).
2. Chạy schema expand và trigger.
3. Chạy **một batch 500** rồi COMMIT.
4. Giả lập worker chết hoặc process restart.
5. Khởi động worker khác, tiếp tục chạy câu UPDATE với **WHERE preferred_name IS NULL**.
6. Khi không còn batch hữu ích, kiểm chứng **pending = 0**, **mismatch = 0**.
7. Chạy lại toàn bộ job lần nữa; không được làm mất giá trị đã đúng.

Những lỗi bổ sung cần thử:

| Điểm lỗi | Kỳ vọng |
| --- | --- |
| Worker crash trước COMMIT | Transaction rollback, hàng chưa xử lý sẽ được chạy lại |
| Worker crash sau COMMIT trước ghi metrics | Job có thể lặp lại an toàn, metrics có thể cập nhật sau |
| Connection mất khi COMMIT phản hồi | Không suy đoán; kiểm chứng DB, chạy lại theo điều kiện idempotent |
| Một hàng bị khóa dài | SKIP LOCKED bỏ qua, job quay lại sau, không báo hoàn tất sớm |
| Trigger ném lỗi | Batch rollback và ghi SQLSTATE, không bỏ qua sai lệch |
| Replica lag quá ngưỡng | Throttle/pause backfill, không tự tăng tốc |
| Câu query bị statement timeout | Rollback batch, backoff, retry hữu hạn |
| Instance V1 cập nhật sau backfill | Trigger cập nhật preferred_name, không tạo mismatch |
| Deployment V3 trước validate | Gate chặn; nếu đã xảy ra, xác định hàng NULL và rollback code |
| Contract trong khi còn V2 | Phải bị gate ngăn từ trước, không coi là lỗi có thể bỏ qua |

Một yếu tố quan trọng: **một batch đã commit không rollback chỉ vì batch tiếp theo lỗi**. Vì vậy phải chủ động chọn migration operation **idempotent** và có trạng thái tiến độ, thay vì trông chờ một transaction bao trùm cả triệu hàng.

## 27. Kiểm soát tài nguyên khi backfill bảng lớn

Mỗi batch có tác động tới PostgreSQL:

- UPDATE sinh phiên bản hàng mới dưới MVCC và có thể tăng **dead tuples**.
- WAL tăng, replica có thể bị lag; backup/archive cần đủ dung lượng.
- Index trên những cột thay đổi có thể phát sinh chi phí cập nhật tùy kế hoạch HOT update và trạng thái page.
- Transaction giữ row locks cho đến COMMIT; batch quá lớn gây contention.
- Autovacuum cần cơ hội dọn phiên bản cũ; long-running transactions khác có thể cản việc dọn.
- CPU, I/O và connection pool cho backfill có thể cạnh tranh với API request.

Một bộ thông số ban đầu **để thử nghiệm**, không phải chuẩn cố định:

~~~text
batch size:         100–500 rows, điều chỉnh theo payload/I/O
workers:            1 trước, tăng dần nếu throughput/lag ổn định
statement timeout: theo p99 batch đo được và operational deadline
sleep/backoff:      điều chỉnh theo lock, WAL và replica lag
pause thresholds:   pool pending, replica lag, WAL disk, error rate
~~~

Đo **rows/sec, batch p95/p99 latency, transaction duration, lock waits, WAL bytes, replica lag, dead tuples và API latency**. Nếu batch chạy nhanh trong test 1.000 hàng, không suy rằng production 100 triệu hàng sẽ có cùng footprint.

**Chọn batch size theo cả số hàng và kích thước dữ liệu**. Với trường TEXT rất lớn hoặc chuyển đổi JSON/BLOB, 500 hàng có thể nặng hơn nhiều so với bảng hồ sơ trong ví dụ.

## 28. Rủi ro PostgreSQL DDL và ranh giới lock

Những câu lệnh schema cần lập kế hoạch riêng:

| Thao tác | Loại rủi ro | Kiểm soát |
| --- | --- | --- |
| ADD COLUMN nullable | Có thể chờ khóa metadata/DDL | Lock timeout, chạy ngắn, preflight |
| CREATE TRIGGER/FUNCTION | Thay đổi đường ghi, có thể chờ khóa | Smoke tests V1/V2 ngay sau migration |
| ADD CHECK ... NOT VALID | Bắt đầu chặn writes không phù hợp | Chạy sau backfill/gate theo kế hoạch |
| VALIDATE CONSTRAINT | Scan dữ liệu, tiêu thụ I/O | Theo dõi load/lag, thử staging |
| SET NOT NULL | DDL lock và có thể scan tùy version | Kiểm tra CHECK đã validate và kế hoạch vận hành |
| DROP COLUMN | Phá tương thích với ứng dụng cũ | Chỉ sau inventory và hết rollback window |
| CREATE INDEX | Có thể ảnh hưởng writer; CONCURRENTLY có quy tắc transaction riêng | Lập migration độc lập khi cần |

Nếu chuyển đổi thực tế cần index mới trên preferred_name, cân nhắc:

~~~sql
CREATE INDEX CONCURRENTLY profiles_preferred_name_idx
ON public.profiles(preferred_name);
~~~

**CREATE INDEX CONCURRENTLY không được chạy bên trong transaction block PostgreSQL thông thường**. Một số migration frameworks yêu cầu đánh dấu migration không transactional; Flyway cần cấu hình tương thích. Lệnh vẫn tiêu thụ tài nguyên và có thể để lại invalid index nếu thất bại; phải theo dõi và xử lý đúng trước khi retry.

Trong bài đổi tên cột demo này, không có truy vấn WHERE theo preferred_name nên **không mặc định cần index chỉ trên tên**. Thêm index không đúng nhu cầu làm tăng chi phí ghi/backfill.

## 29. Rollback theo từng pha, không giả định chạy ngược DDL

| Thời điểm gặp sự cố | Có thể làm gì? | Giới hạn |
| --- | --- | --- |
| Sau EXPAND, V1 vẫn chạy | Giữ cột mới chưa dùng; sửa trigger hoặc tạm dừng rollout V2 | Không được xóa dữ liệu cũ theo phản xạ |
| V2 lỗi khi một phần instance đã rollout | Rollback V2 về V1, vẫn giữ hai cột + trigger | V1 cần cột cũ và hành vi trigger đúng |
| Backfill chạy dở | Tạm dừng job, giữ schema, sửa nguyên nhân, chạy lại idempotent | Các batch đã commit vẫn tồn tại |
| Validation thất bại | Dừng gate; tìm NULL/mismatch và nguyên nhân | Không đặt NOT NULL hoặc rollout V3 khi chưa sửa |
| V3 lỗi trước contract | Rollback V3 về V2 hoặc V1 theo ma trận | Cột cũ + trigger phải còn |
| Sau contract đã DROP display_name | **Không rollback trực tiếp về V1/V2** | Có thể cần forward-fix hoặc recovery plan riêng |

Đừng dùng một câu **UPDATE preferred_name = display_name** toàn bảng để “rollback dữ liệu” nếu trong thời gian đó có writer mới. Nó có thể ghi đè những thay đổi hợp lệ. Trong migration demo, trước contract hai cột đồng bộ bằng trigger; cách rollback ứng dụng tốt nhất thường là **chuyển code về V1 trong khi vẫn giữ schema expanded**, không reverse data backfill.

Một migration sửa schema sai nên ưu tiên **roll-forward có kiểm soát** nếu thay đổi còn bảo toàn dữ liệu và phụ thuộc; restore backup/PITR chỉ khi có đánh giá đầy đủ dữ liệu hợp lệ được ghi sau mốc phục hồi. Khôi phục toàn database về mốc cũ có thể làm mất các transaction nghiệp vụ không liên quan.

## 30. Kiểm tra tương thích không chỉ là SQL trả 200

Một API GET trả 200 nhưng lấy từ cache có thể che lỗi database. Một migration tốt cần kiểm chứng:

- **Read-after-write**: V1 ghi, V2/V3 đọc cùng dữ liệu đã commit trên primary theo hợp đồng.
- **Write-after-read**: V2 sửa, V1 đọc đúng dữ liệu trước khi hết cửa sổ cũ.
- **Cross-tenant isolation**: tenant 10 không sửa/đọc hồ sơ tenant 20.
- **NULL/empty/Unicode**: giá trị phù hợp constraint, không tự cắt mất dấu tiếng Việt.
- **Concurrency**: V1/V2 cùng UPDATE một hàng; không tạo mismatch.
- **Schema rollback compatibility**: ứng dụng cũ hoạt động trên expanded schema trước contract.
- **ORM/JPA**: nếu các entity mapping dùng @Column hoặc @Version, flush/clear và query cache không giữ cột cũ sau contract.
- **Prepared statement caches**: session/pool tái sử dụng câu SQL cũ cần được quan sát và tái khởi tạo theo rollout.
- **CDC/ETL/reporting**: downstream schema mappings được cập nhật theo kế hoạch, không chỉ API Java.
- **Replica**: đọc từ replica có thể trễ WAL nên không dùng nó làm bằng chứng duy nhất ngay sau write.

**Kiểm thử tương thích là quan hệ giữa binary, schema và dữ liệu**, không chỉ giữa Java class và kiểu cột.

## 31. Quan sát tiến độ và đặt release gates

Dashboard tối thiểu:

| Giai đoạn | Tín hiệu | Điều kiện quyết định |
| --- | --- | --- |
| Expand | Migration version applied, DDL lock wait, errors | V1 vẫn hoạt động, trigger smoke PASS |
| V2 rollout | Lỗi SQL, API p99, instance versions, mismatches | V1/V2 cùng chạy đúng và không regression |
| Backfill | Rows updated, batches/sec, pending, failures | Tiến độ tăng, không tạo tải quá mức |
| Validate | NULL count, mismatch count, constraint validation | Đều 0 và validation PASS |
| V3 rollout | V3 readiness, V1/V2 còn lại, dependency inventory | Tất cả code path hỗ trợ chỉ preferred_name |
| Contract | No legacy queries, approved rollback boundary | Không còn binary/job/report phụ thuộc cột cũ |
| Post-contract | DB errors, business metrics, backup restore proof | Không có truy vấn cột cũ; nghiệp vụ ổn định |

Cảnh báo nên phát khi:

- **preferred_name IS DISTINCT FROM display_name** tăng lại sau khi được xác nhận 0.
- Backfill không tiến triển trong khi pending > 0.
- Lock waits, WAL disk usage hoặc replica lag vượt ngưỡng của workload.
- SQLSTATE liên quan missing column, constraint violation hoặc timeout tăng sau deploy.
- Có instance V1/V2 vẫn chạy khi gần thời điểm contract.

Thay vì bật **SELECT COUNT(*)** mỗi giây trên bảng lớn, dùng metrics tiến độ job, sự kiện lỗi và các đợt reconciliation scan theo chu kỳ. Nếu dữ liệu nhạy cảm, không xuất tên/tenant ID từng người vào log/telemetry.

## 32. Runbook triển khai được kiểm chứng

~~~text
CHANGE: rename profiles.display_name -> preferred_name
OWNER: migration team + SRE + application team
SCOPE: PostgreSQL primary, Java API, consumers, reports
PRECONDITION:
  Backup/restore plan được thử
  Schema/DB version xác nhận
  Chỉ một migration coordinator
  V1 health/API baseline có số liệu

PHASE 1 - EXPAND
  Deploy ADD preferred_name + sync trigger
  Kiểm tra V1 INSERT/UPDATE/SELECT và mismatch
  Nếu lỗi: dừng V2 rollout, sửa bằng migration mới

PHASE 2 - V2
  Canary V2 -> rolling V2
  Kiểm tra V1/V2 co-existence, pool, SQL errors
  Giữ cột cũ cho rollback

PHASE 3 - BACKFILL
  Khởi chạy job batch 100–500 với giới hạn worker
  Theo dõi pending/rows per sec/WAL/lag/locks
  Pause khi vượt ngưỡng
  Chạy đến khi pending = 0; chạy reconciliation

PHASE 4 - VALIDATE
  missing_new_name = 0
  mismatched_names = 0
  ADD CHECK NOT VALID, VALIDATE; SET NOT NULL khi được duyệt
  Ghi lại kết quả kiểm thử DB/app

PHASE 5 - V3
  Deploy V3 chỉ tham chiếu preferred_name
  Theo dõi ở cửa sổ rollback
  Inventory: API, batch, analytics, CDC, old workers

PHASE 6 - CONTRACT (quyết định riêng)
  Xác nhận không còn app V1/V2/SQL cũ
  Chấp nhận không rollback binary V1/V2 trực tiếp nữa
  Drop constraint so sánh, trigger/function, display_name
  Xác minh V3/V4 và backup/restore theo schema đích

CLOSE:
  Lưu migration versions, số liệu, lỗi, owner, timestamps
  Ghi lessons learned và điều kiện hoàn tất
~~~

Mỗi pha nên có **người chịu trách nhiệm, phê duyệt, deadline, rollback/stop criteria và người có quyền thao tác**. Chạy từng pha theo gate; không đặt P1–P6 vào cùng một script không có cơ hội quan sát và dừng.

## 33. Các lỗi thiết kế cần tránh

| Sai lầm | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Đổi tên cột bằng RENAME rồi deploy cùng lúc | V1 không còn cột cũ khi còn instance chạy | Expand hai cột và contract có gate |
| Chỉ chạy một UPDATE copy dữ liệu | Writer V1 sau backfill làm preferred_name stale | Trigger/đồng bộ trong cửa sổ tương thích |
| Đưa NOT NULL vào EXPAND | Hàng cũ thiếu dữ liệu, migration/ghi có thể lỗi | Thêm nullable trước, backfill, validate rồi NOT NULL |
| V2 đọc preferred_name không fallback | Hàng cũ chưa backfill trả NULL | COALESCE hoặc gate trước deploy |
| Backfill trong một transaction hàng triệu UPDATE | Locks/WAL/rollback quá lớn | Batch hữu hạn, commit và rate limit |
| Dùng SKIP LOCKED rồi 0 rows là kết thúc | Có thể còn hàng đang bị khóa | Kiểm pending độc lập và retry |
| Copy giá trị cũ qua Java trong thời gian dài | Ghi đè thay đổi mới | UPDATE tại DB theo row lock/condition |
| Tắt trigger để import nhanh | Hai cột lệch khi V1/V2 ghi | Giữ ràng buộc hoặc thiết kế đồng bộ thay thế |
| Chỉ test một application version | Bỏ sót incompatibility lúc rolling | Test ma trận V1/V2/V3 × schema |
| Đếm hàng bằng SELECT COUNT mỗi batch | Tạo I/O thừa trên bảng lớn | Metrics và reconciliation scan định kỳ |
| Contract khi còn V2 | COALESCE vẫn tham chiếu display_name | Kiểm toàn bộ code paths trước DROP |
| Thay checksum Flyway migration đã chạy | Mất kiểm soát lịch sử schema | Migration version mới theo quy trình |
| Tin test H2 chứng minh semantics Postgres | Khác MVCC/locking/DDL | Testcontainers PostgreSQL thực |
| Không xét CDC/ETL/reporting | Downstream lỗi sau contract | Inventory dependency đầy đủ |
| Rollback về V1 sau DROP COLUMN | V1 lỗi query thiếu display_name | Kết thúc rollback window trước contract |
| Chỉ kiểm tra API 200 | Cache hoặc path ít dùng che lỗi | Read/write, constraints, jobs, database validations |

## 34. Bài tập thực hành và câu hỏi kiểm tra

### Bài 1. Thứ tự an toàn

Bạn được giao thêm **preferred_name** vào bảng có hai triệu hồ sơ đang có traffic V1. Có nên deploy V2 trước khi ADD COLUMN không?

**Gợi ý:** Không. EXPAND schema + trigger trước, smoke test V1, sau đó mới deploy V2 đọc fallback.

### Bài 2. Vì sao backfill không đủ?

Sau khi UPDATE toàn bộ preferred_name, V1 vẫn ghi display_name. Nêu ví dụ một hàng bị stale.

**Gợi ý:** V1 đổi tên từ A thành B nhưng preferred_name vẫn A nếu không có đồng bộ; V2 đọc tên cũ.

### Bài 3. NULL ở cột mới

Tại sao không đặt preferred_name NOT NULL ngay khi ADD COLUMN?

**Gợi ý:** Hàng legacy chưa có dữ liệu mới. Thêm nullable, backfill, kiểm chứng rồi áp constraint.

### Bài 4. Hai chiều INSERT

V2 chỉ gửi INSERT preferred_name, trong khi display_name vẫn NOT NULL. Làm sao tương thích V1?

**Gợi ý:** BEFORE INSERT trigger điền display_name trước khi kiểm tra ràng buộc; cần test transaction thật.

### Bài 5. UPDATE cạnh tranh

V1 và V2 cùng đổi tên một hồ sơ. Trigger giúp điều gì và không giúp điều gì?

**Gợi ý:** Hai cột được đồng bộ trong transaction; nó không thay thế version check để ngăn lost update theo nghiệp vụ.

### Bài 6. SKIP LOCKED

Worker backfill trả 0 rows, nhưng query kiểm chứng vẫn thấy 12 hàng preferred_name NULL. Có phải tất cả đã hoàn tất?

**Gợi ý:** Chưa. Hàng có thể đang bị khóa hoặc job khác xử lý; backoff và chạy lại, không đặt gate PASS.

### Bài 7. Idempotency của backfill

Job commit 500 hàng rồi crash. Có nên reset preferred_name của mọi hàng về NULL để chạy lại?

**Gợi ý:** Không. Chỉ xử lý hàng NULL còn lại, giữ các batch đã commit; kiểm mismatch sau cùng.

### Bài 8. Constraint NOT VALID

CHECK preferred_name IS NOT NULL NOT VALID có cho phép một INSERT mới chứa preferred_name NULL không?

**Gợi ý:** Không mặc định; NOT VALID bỏ kiểm tra toàn bộ hàng cũ lúc ADD, nhưng vẫn áp constraint lên những row INSERT/UPDATE mới.

### Bài 9. V2 sau contract

V2 ghi preferred_name nhưng đọc COALESCE(preferred_name, display_name). Nó có chạy sau khi DROP display_name không?

**Gợi ý:** Không. V2 vẫn có tham chiếu SQL tới cột đã xóa.

### Bài 10. Rủi ro snapshot ứng dụng

Backfill SELECT 1.000 hàng vào Java, xử lý 2 phút rồi ghi preferred_name theo dữ liệu cũ. Có thể hỏng ở đâu?

**Gợi ý:** Người dùng có thể đổi display_name ở giữa; backfill dựa trên stale snapshot. Ưu tiên UPDATE tại DB dưới row lock và điều kiện cụ thể.

### Bài 11. Rollback

V3 gặp lỗi trước contract và cột cũ còn được trigger đồng bộ. Có thể rollback về V2 không? Còn sau contract?

**Gợi ý:** Trước contract có thể theo ma trận; sau DROP display_name không thể rollback V2 trực tiếp.

### Bài 12. Flyway và backfill

Có nên đưa một UPDATE 100 triệu hàng và DROP COLUMN vào cùng một migration Flyway tự chạy khi startup?

**Gợi ý:** Không. Tách DDL, backfill vận hành theo batch và contract có gate riêng.

### Bài 13. CI matrix

Một test V3 trên schema S3 pass. Có đủ chứng minh rolling deployment V1/V2/V3 trên S2 an toàn không?

**Gợi ý:** Chưa. Cần test từng cặp version-schema, cả read/write và concurrency.

### Bài 14. Tải PostgreSQL

Backfill tăng throughput nhưng replica lag tăng mạnh, API p99 chậm. Nên làm gì?

**Gợi ý:** Pause/throttle worker, giảm batch/concurrency, điều tra WAL/I/O/locks. Không tăng tốc vì chỉ nhìn phần trăm đã hoàn tất.

### Bài 15. Security

Một job backfill chạy bằng tài khoản superuser và log toàn bộ display_name để debug. Những vấn đề gì?

**Gợi ý:** Quyền quá rộng và rò dữ liệu cá nhân. Dùng role đủ quyền, log count/ID có kiểm soát, retention rõ ràng.

## 35. Checklist nghiệm thu migration

1. **Mục tiêu:** xác định rõ hai cột có cùng ý nghĩa, hay cần transform có thể mất dữ liệu?
2. **Bất biến:** NULL, mismatch, tenant scope, đồng thời và thứ tự update được định nghĩa?
3. **Inventory:** mọi API, batch, consumer, report, view, trigger, CDC đều đã được rà soát?
4. **Backup:** có bản sao kiểm chứng restore và phương án sự cố DDL/data corruption?
5. **EXPAND:** chỉ thêm thành phần backward-compatible; V1 smoke PASS?
6. **Sync:** có cơ chế ngăn V1 ghi cột cũ làm stale cột mới sau backfill?
7. **V2:** đọc fallback và ghi mới, không tham chiếu cột chưa được thêm?
8. **Backfill:** batch hữu hạn, transaction ngắn, rate limit, metrics, pause/resume?
9. **Race:** test old/new writers trong khi backfill chạy và sau khi hoàn tất?
10. **Progress:** không coi 0 updated dưới SKIP LOCKED là hoàn tất khi chưa kiểm pending?
11. **Data check:** missing_new_name = 0, mismatched_names = 0, có điều tra mẫu?
12. **Constraints:** CHECK NOT VALID/VALIDATE, NOT NULL và locks được lập kế hoạch?
13. **V3:** chỉ dùng preferred_name, không còn COALESCE với cột cũ ở mọi path?
14. **Contract:** không còn V1/V2/job/SQL cũ; hết cửa sổ rollback binary cũ?
15. **Flyway:** lịch sử migrations hợp lệ, không tự chạy contract sớm?
16. **Performance:** DB locks, WAL, replication lag, bloat, autovacuum, pool được theo dõi?
17. **Testing:** PostgreSQL thật, matrix version × schema, fault injection, concurrency và correctness?
18. **Security:** role tối thiểu, tenant isolation, redaction, audit và retention?
19. **Release gates:** owner, thresholds, approvals, incident stop/rollback decision rõ ràng?
20. **Post-deploy:** bằng chứng V4 hoạt động, không có query cột cũ và backup/schema mới dùng được?

## 36. Tổng kết

**Thực hiện migration có backfill và kiểm chứng tương thích** là một quy trình triển khai nhiều pha, không phải một câu ALTER TABLE hay UPDATE đơn lẻ. Với ví dụ chuyển **display_name → preferred_name**, cần **EXPAND** để V1 vẫn hoạt động, **đồng bộ writes cũ/mới** trong cửa sổ rolling deployment, **BACKFILL** theo batch có transaction ngắn và điều kiện có thể chạy lại, **VALIDATE** dữ liệu/constraints, rồi mới deploy code chỉ dùng cột mới và thực hiện **CONTRACT**.

Điểm khó nhất thường không nằm ở SQL copy ban đầu, mà ở những khoảng chuyển tiếp: V1 ghi sau backfill, worker crash giữa batch, replica chậm, V2 đọc fallback, trigger/constraint không thống nhất, hoặc contract trong khi vẫn còn code cũ. Vì vậy, hãy chứng minh bằng **ma trận tương thích, kiểm thử PostgreSQL thật, truy vấn đối soát, fault injection và release gates**, đồng thời giữ rollback window đến khi đã sẵn sàng chấp nhận thay đổi phá tương thích. Một migration được coi là thành công khi **dữ liệu đúng, ứng dụng cũ/mới hoạt động theo cam kết, hệ thống phục hồi được sau lỗi và tài nguyên vận hành nằm trong giới hạn**, chứ không chỉ khi công cụ migration báo success.
