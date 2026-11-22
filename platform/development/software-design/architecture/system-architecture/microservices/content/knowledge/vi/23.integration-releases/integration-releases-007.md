# Thay đổi cơ sở dữ liệu theo mô hình mở rộng rồi thu hẹp (Expand–Contract) trong Microservices

## Mục tiêu

Sau bài này, người học có thể giải thích vì sao việc sửa schema trực tiếp thường gây sự cố khi triển khai microservice theo kiểu rolling/canary; thiết kế một chuỗi **expand → chuyển tiếp dữ liệu và ứng dụng → contract** không làm gián đoạn các phiên bản đang hoạt động; nhận biết điều kiện tương thích, backfill, dual-write, rollback; và lập kế hoạch phát hành có đo lường để thay đổi bảng dữ liệu an toàn.

## 1. Vấn đề: mã ứng dụng và schema không thay đổi cùng một thời điểm

Trong microservices, mỗi dịch vụ thường sở hữu cơ sở dữ liệu riêng và được triển khai độc lập. Ngay cả với một dịch vụ duy nhất, quá trình rolling deployment cũng khiến **phiên bản cũ và phiên bản mới cùng chạy trong một khoảng thời gian**. Ngoài các instance HTTP, còn có worker xử lý hàng đợi, scheduler, consumer sự kiện, tác vụ batch, công cụ quản trị và tiến trình rollback.

Ví dụ, Order Service phiên bản 1 đọc cột **customer_name**. Nếu migration đổi tên cột thành **buyer_name** rồi triển khai phiên bản 2, những instance v1 chưa được thay thế vẫn gửi truy vấn đến cột đã bị xóa/đổi tên và thất bại. Đảo thứ tự, triển khai v2 trước migration, cũng có thể làm v2 thất bại vì cột mới chưa tồn tại.

~~~text
Thời điểm T0: DB cũ + App v1
Thời điểm T1: DB mở rộng + App v1 và v2 cùng tồn tại
Thời điểm T2: DB mở rộng + App v2 hoàn toàn
Thời điểm T3: DB thu hẹp + App v2 hoặc phiên bản mới tương thích
~~~

Một lần triển khai ứng dụng không phải transaction bao trùm đồng thời tất cả pod, database, message consumer và kết nối bên ngoài. Do đó, mục tiêu thực tế là **mỗi trạng thái trung gian đều vận hành đúng**, có thể quan sát và có đường xử lý khi gặp lỗi.

**Expand–Contract** là chiến lược thực hiện thay đổi không tương thích cuối cùng qua các bước nhỏ tương thích tạm thời:

1. **Expand (mở rộng):** thêm cấu trúc mới mà không phá những gì phiên bản cũ đang dùng.
2. **Migrate/transition (chuyển tiếp):** cập nhật mã đọc/ghi, di chuyển dữ liệu, xác minh và chuyển dần nguồn dữ liệu chuẩn.
3. **Contract (thu hẹp):** xóa cấu trúc cũ sau khi chắc chắn không còn tiến trình hay hợp đồng nào phụ thuộc.

Mục tiêu là thay đổi schema an toàn trong lúc hệ thống phục vụ lưu lượng bình thường. Chiến lược này thường được gọi là *parallel change* hoặc *expand–migrate–contract*. Nó không tự bảo đảm zero downtime: tính an toàn vẫn phụ thuộc thời gian lock của DDL, dung lượng bảng, nghiệp vụ, tính tương thích, và cách triển khai.

## 2. Nguyên tắc thiết kế nền tảng

**Tương thích với phiên bản cũ:** Sau bước expand, code cũ vẫn phải đọc và ghi được những cột/kiểu dữ liệu đã tồn tại. Tránh xóa hoặc đổi tên trường đang được dùng ngay ở bước đầu.

**Mỗi thời điểm phải có dữ liệu chuẩn rõ ràng:** Nếu cùng tồn tại cột cũ và mới, phải xác định cột nào là nguồn sự thật, ứng dụng nào được ghi, và khi nào quyền ưu tiên chuyển sang cột mới. Hai cột cùng được ghi độc lập mà không có quy tắc đồng bộ sẽ gây lệch dữ liệu.

**Thay đổi có thể kiểm chứng:** Định nghĩa trước điều kiện để qua mỗi bước, ví dụ không còn instance cũ, số dòng cần backfill bằng 0, dữ liệu hai cột khớp, tỉ lệ lỗi SQL không tăng.

**Tách schema migration và data migration:** Lệnh thêm cột thường nên chạy qua migration có phiên bản; backfill lớn nên là job riêng có thể tạm dừng, chạy tiếp, giới hạn tốc độ và đo tiến độ.

**Thu hẹp là bước cuối cùng:** Xóa cột cũ là thay đổi có thể ngăn rollback về phiên bản trước. Chỉ thực hiện khi thời hạn quay lại phiên bản cũ đã hết và mọi consumer liên quan đã chuyển.

**Tôn trọng quyền sở hữu dữ liệu:** Mỗi microservice nên sở hữu schema của mình. Dịch vụ khác không nên đọc trực tiếp bảng nội bộ như một hợp đồng tích hợp; nếu đang có dependency đó, phải lập danh sách và chuyển sang API/event được quản lý trước khi contract.

## 3. Ví dụ xuyên suốt: đổi cột email trong User Service

Giả sử User Service dùng PostgreSQL, bảng **app_user** và cột **email**. Yêu cầu mới là chuyển dần tên cột sang **email_address** vì mô hình dữ liệu mới, nhưng không dừng dịch vụ. Mọi giá trị đều là chuỗi email giống trước; đây là một phép đổi tên mang cùng ngữ nghĩa, phù hợp để minh họa.

Trạng thái ban đầu:

~~~sql
CREATE TABLE app_user (
    id BIGINT PRIMARY KEY,
    email VARCHAR(320) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL
);
~~~

Phiên bản cũ (v1) đọc/ghi duy nhất **email**. Ta cần đưa ra phiên bản mới sử dụng **email_address**, trong khi vẫn có thể chạy v1 trên cùng DB một khoảng thời gian.

Không dùng ngay:

~~~sql
-- Không an toàn khi v1 còn chạy:
ALTER TABLE app_user RENAME COLUMN email TO email_address;
-- Hoặc: ALTER TABLE app_user DROP COLUMN email;
~~~

Cả hai thao tác làm hợp đồng SQL của v1 bị phá vỡ ngay khi chạy migration.

### Giai đoạn A — Expand schema, giữ v1 hoạt động

Migration đầu tiên chỉ thêm cột mới cho phép NULL:

~~~sql
ALTER TABLE app_user
    ADD COLUMN email_address VARCHAR(320);
~~~

Kết quả:

~~~text
app_user(id, email, email_address, created_at)
             ^          ^
             |          +-- mới, ban đầu có thể NULL
             +------------- v1 vẫn đọc/ghi như trước
~~~

**Không** đặt NOT NULL cho cột mới lúc này, bởi các instance v1 vẫn có thể INSERT chỉ với **email**. Chưa nên drop/rename cột cũ hoặc chuyển ngay unique constraint nếu việc đó làm các phiên bản cũ mất khả năng ghi.

Đánh giá riêng từng thay đổi DDL trên đúng hệ quản trị DB/phiên bản đang dùng. Lệnh ADD COLUMN không default trong nhiều trường hợp PostgreSQL có chi phí thấp, nhưng vẫn cần khóa metadata trong một khoảng thời gian và có thể phải chờ transaction đang giữ lock. Không suy rộng rằng mọi dạng ALTER TABLE đều tức thời.

### Giai đoạn B — Bridge application: đọc cũ, ghi kép

Triển khai phiên bản trung gian v1.5. Khi thay đổi email, phiên bản này ghi **email** và **email_address** trong cùng một transaction ở cùng database, nhưng **vẫn đọc email** trong giai đoạn còn v1.

~~~java
@Service
public class UserEmailService {
    private final JdbcTemplate jdbc;

    public UserEmailService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void changeEmail(long userId, String newEmail) {
        int updated = jdbc.update(
            "UPDATE app_user SET email = ?, email_address = ? WHERE id = ?",
            newEmail, newEmail, userId
        );
        if (updated != 1) {
            throw new IllegalArgumentException("User not found: " + userId);
        }
    }
}
~~~

Khi tạo user mới, v1.5 cũng phải ghi cả hai cột. Truy vấn đọc trong pha này vẫn dùng **email** làm giá trị chuẩn. Cách này cho phép v1 tiếp tục chạy và cập nhật email theo cấu trúc cũ mà không khiến người dùng thấy dữ liệu mới đã ghi ở một cột khác.

**Điểm dễ bị bỏ qua:** Trong rolling deployment, v1 vẫn chỉ ghi cột **email**. Vì vậy cột **email_address** có thể NULL hoặc cũ hơn ở một số dòng. Nếu v1.5 đọc ưu tiên cột mới bằng COALESCE(email_address, email), một giá trị email_address không NULL nhưng đã cũ có thể được trả về. **Không dùng cột mới làm nguồn chuẩn trước khi tất cả writer cũ đã rút và dữ liệu đã được đồng bộ lần cuối.**

Trong hệ thống có các writer không thể nâng cấp đồng loạt, có thể dùng trigger đồng bộ tạm thời tại DB, chiến lược CDC có quản lý hoặc cơ chế chống lệch được thiết kế riêng. Trigger cần xem xét thứ tự cập nhật, xung đột ghi, tác động hiệu năng và thời điểm tháo bỏ; không tự thêm trigger chỉ vì muốn tránh kiểm soát phiên bản ứng dụng.

### Giai đoạn C — Backfill dữ liệu theo lô, có thể chạy lại

Sau khi v1.5 đã chạy, chuyển dữ liệu của những bản ghi cũ sang cột mới. Ví dụ PostgreSQL dùng batch 1.000 dòng:

~~~sql
WITH batch AS (
    SELECT id
    FROM app_user
    WHERE email_address IS DISTINCT FROM email
    ORDER BY id
    LIMIT 1000
    FOR UPDATE SKIP LOCKED
)
UPDATE app_user AS u
SET email_address = u.email
FROM batch
WHERE u.id = batch.id;
~~~

Chạy lặp theo lô đến khi không còn dòng khác biệt. Mẫu này minh họa lệnh backfill idempotent theo dữ liệu hiện hành; **không** chạy trong một transaction khổng lồ. Tùy workload cần giới hạn tốc độ và quan sát lock, transaction log/WAL, replication lag, CPU và tốc độ xử lý yêu cầu.

Nếu vẫn còn instance v1 đang cập nhật cột cũ, backfill có thể bị phát sinh chênh lệch mới ngay sau khi vừa xử lý. Vì vậy cần **quét đối soát lần cuối sau khi tất cả writer chỉ ghi cột cũ đã ngừng**, rồi mới chuyển nguồn đọc chuẩn.

Kiểm tra tiến độ:

~~~sql
SELECT COUNT(*) AS remaining
FROM app_user
WHERE email_address IS DISTINCT FROM email;
~~~

Với một bảng có email NOT NULL, điều kiện **IS DISTINCT FROM** hữu ích vì so sánh an toàn với NULL. Chỉ số remaining bằng 0 tại một thời điểm là cần thiết, nhưng chưa đủ để chuyển pha nếu các tiến trình cũ vẫn có thể tiếp tục ghi.

Với dữ liệu lớn, backfill cần có checkpoint, batch size hợp lý, cơ chế resume và khả năng dừng khẩn cấp. Nếu thay đổi có chuyển đổi kiểu, cần xác định quy tắc xử lý giá trị sai, mất mát thông tin, NULL và trường hợp không thể chuyển đổi trước khi chạy thật.

### Giai đoạn D — Chuyển hướng đọc, xác nhận invariant

Khi tất cả writer v1 đã rút khỏi lưu lượng, backfill/đối soát cuối đã hoàn tất và không có tiến trình ngoài luồng nào còn ghi riêng cột cũ, có thể triển khai v2 đọc **email_address**. Trong một thời gian, v2 vẫn **ghi cả hai** để duy trì khả năng quay lại v1.5 và bảo đảm những thành phần chưa được di chuyển vẫn có dữ liệu cũ cập nhật.

~~~text
v1:    READ(email)         WRITE(email)
v1.5:  READ(email)         WRITE(email, email_address)
v2:    READ(email_address) WRITE(email, email_address)
v3:    READ(email_address) WRITE(email_address)
~~~

Việc đi từ v2 sang v3 chỉ an toàn khi không còn v1/v1.5 hoặc bất kỳ consumer nào đòi cột cũ được cập nhật. Bảng này diễn tả ứng dụng đọc/ghi ở mức ý tưởng; trong môi trường thực, hãy kiểm kê cả job nền, stored procedure, CDC, báo cáo, quyền truy cập SQL và phiên bản rollback.

Các invariant cần giữ trong giai đoạn chuyển tiếp:

- Một lần thay đổi email tạo kết quả logic duy nhất; cập nhật hai cột phải thành công hoặc rollback cùng nhau.
- Hai cột đại diện cùng một ngữ nghĩa; ở thời điểm chuyển nguồn đọc, không còn dòng lệch hoặc NULL bất hợp lệ.
- Mọi reader dùng cột mới phải tương thích với kiểu, giới hạn độ dài, collation và quy tắc uniqueness.
- Tất cả đường ghi, bao gồm INSERT, UPDATE, API batch, import và consumer sự kiện, tuân thủ quy tắc ghi hiện hành.
- Kết quả đọc qua API không thay đổi bất ngờ giữa các phiên bản ứng dụng cùng phục vụ người dùng.

### Giai đoạn E — Tăng ràng buộc và contract

Chỉ sau khi các phiên bản còn dùng cột cũ không còn được phép chạy và các phụ thuộc đã chuyển hẳn sang cột mới, mới tiến hành siết constraint và xóa cấu trúc cũ.

Đối với PostgreSQL, có thể chuẩn bị ràng buộc NOT NULL theo lộ trình:

~~~sql
-- Chạy khi không còn writer cũ tạo email_address NULL:
ALTER TABLE app_user
    ADD CONSTRAINT app_user_email_address_required
    CHECK (email_address IS NOT NULL) NOT VALID;

ALTER TABLE app_user
    VALIDATE CONSTRAINT app_user_email_address_required;
~~~

Việc dùng CHECK rồi VALIDATE giúp tách một số phần công việc trên bảng lớn; chi phí và lock cụ thể phụ thuộc phiên bản PostgreSQL. Nếu cần cột mang thuộc tính NOT NULL chính thức, lên lịch **SET NOT NULL** ở bước riêng sau khi đánh giá hành vi của DB phiên bản đang chạy.

Ràng buộc UNIQUE cho email_address cũng cần thiết nếu email vẫn phải duy nhất; PostgreSQL có tùy chọn xây index CONCURRENTLY để giảm lock trong nhiều tình huống, nhưng cách này không được chạy trong transaction block và cần lên kế hoạch riêng theo công cụ migration:

~~~sql
CREATE UNIQUE INDEX CONCURRENTLY
    idx_app_user_email_address_unique
ON app_user (email_address);
~~~

Ví dụ trên yêu cầu kiểm tra dữ liệu không trùng trước và tương thích với loại index/constraint thực tế. Tránh mặc định rằng một tool migration luôn chạy từng file SQL không có transaction; cần cấu hình script phù hợp, ví dụ lựa chọn non-transactional migration của Flyway trong trường hợp này.

Khi đã hoàn tất các điều kiện contract:

~~~sql
ALTER TABLE app_user
    DROP COLUMN email;
~~~

Không được thực thi lệnh DROP này chỉ vì “deploy v2 thành công”. Phải kiểm kê phiên bản còn sống, các connection/task chạy muộn, truy vấn SQL ngoại lệ, công cụ vận hành, cửa sổ rollback và khả năng khôi phục. Sau khi drop, rollback về v1/v1.5 có thể không còn thực hiện trực tiếp; kế hoạch thường cần **forward fix** hoặc phục hồi có quy trình, thay vì giả định một nút rollback code đủ giải quyết.

## 4. Ma trận tương thích trong rolling deployment

| Tình huống | Kết quả mong đợi | Điều kiện |
| --- | --- | --- |
| v1 + schema cũ | Hoạt động | Trạng thái ban đầu |
| v1 + schema mở rộng | Hoạt động | Cột email giữ nguyên và cột mới cho phép NULL |
| v1.5 + schema mở rộng | Hoạt động | Viết kép một transaction, đọc dữ liệu cũ |
| v2 + schema mở rộng | Hoạt động | Writer v1 đã rút, backfill/đối soát xong |
| v3 + schema mở rộng | Hoạt động | Không còn consumer yêu cầu email cũ được cập nhật |
| v3 + schema thu hẹp | Hoạt động | Mã hoàn toàn độc lập với email cũ |
| v1 hoặc v1.5 + schema thu hẹp | Thất bại | Vì vẫn tham chiếu cột đã drop |
| v2 + schema cũ chưa expand | Thất bại | Vì email_address chưa tồn tại |

Từ ma trận này suy ra **thứ tự phát hành** quan trọng như chính nội dung migration. Không thể giả định “schema migration rồi app deployment” luôn đủ nếu app và worker có thể chạy nhiều phiên bản trong thời gian dài. Nên tự động kiểm soát điều kiện cho phép chuyển từng pha.

## 5. Những kiểu thay đổi áp dụng Expand–Contract

### 5.1 Đổi tên cột hoặc bảng

Thêm cột/bảng mới, duy trì đường ghi tương thích, backfill, chuyển reader, rồi xóa cũ. Rename trực tiếp thường phá code cũ nên chỉ phù hợp khi hệ thống thật sự có một thời điểm dừng và đổi nguyên tử toàn bộ reader/writer đã được kiểm soát.

### 5.2 Đổi kiểu dữ liệu

Ví dụ từ integer sang UUID hoặc từ string sang cấu trúc có schema. Tạo cột mới kiểu mong muốn, thiết kế phép chuyển đổi, chuyển dữ liệu và kiểm chứng không mất ngữ nghĩa. Cần giải quyết các ID tham chiếu, index, foreign key, event và URL đang dùng kiểu cũ. Một số kiểu chuyển đổi không đảo ngược chính xác; kế hoạch rollback phải xét nguy cơ mất dữ liệu.

### 5.3 Tách một bảng lớn thành nhiều bảng

Tạo bảng đích, chuyển dữ liệu theo khóa chính, bảo đảm ghi mới đi theo cơ chế đồng bộ/ghi tương thích, chuyển dần truy vấn, rồi mới thu hồi cấu trúc cũ. Các giao dịch nhiều bảng phải tính đến consistency, khóa và isolation. Nếu tách dữ liệu sang **database thuộc service khác**, đó còn là thay đổi ranh giới nghiệp vụ; dual-write xuyên hai database không tự có atomicity và có thể cần outbox, event, idempotency và quy trình reconciliation.

### 5.4 Thêm ràng buộc hoặc xóa cột không còn dùng

Một cột mới chưa có dữ liệu không thể lập tức đặt NOT NULL nếu ứng dụng cũ vẫn insert mà không điền cột. Với NOT NULL, UNIQUE, foreign key hoặc CHECK, nên thêm theo giai đoạn và xác thực dữ liệu. Một cột tưởng như “không dùng” vẫn có thể xuất hiện trong job báo cáo, ứng dụng đọc trễ, migration, script hoặc consumer ngoài hệ thống.

## 6. Vấn đề dual-write và tính nhất quán dữ liệu

Ghi hai cột trong **cùng một row/cùng database transaction** thường có thể bảo đảm atomicity cho ví dụ đổi tên. Nhưng hai lần gọi tới **hai microservices hoặc hai database khác nhau** không có cùng tính chất đó.

Ví dụ User Service ghi MySQL, rồi đồng bộ sang Search Service thông qua message. Nếu commit DB thành công nhưng publish event thất bại, dữ liệu hai phía lệch nhau. Trong trường hợp ấy, cân nhắc transactional outbox, consumer idempotent, retry có backoff, dead-letter processing, lag metrics và reconciliation. Không nên xem “gọi API hai lần” là dual-write an toàn.

Ngoài ra, ngay trong một database, ghi kép vẫn có rủi ro nếu có code path bị bỏ sót. Có thể lập bảng bao phủ tất cả đường ghi:

| Đường ghi | V1 | V1.5/V2 |
| --- | --- | --- |
| API tạo user | Ghi email | Ghi email và email_address |
| API cập nhật email | Ghi email | Ghi cả hai |
| Import dữ liệu batch | Ghi email | Ghi cả hai |
| Background job | Ghi email nếu có | Ghi cả hai nếu có |
| Admin script | Kiểm kê riêng | Cập nhật theo quy tắc chuyển tiếp |

Chuyển nguồn đọc khi **mọi writer** đều được kiểm soát. Một cron job chạy mỗi đêm, quên nâng cấp, đủ khiến một migration được coi là thành công lúc ban ngày phát sinh lệch dữ liệu vào hôm sau.

## 7. Migration schema cần an toàn về vận hành

Migration đúng về logic vẫn có thể gây downtime nếu tạo lock kéo dài hoặc quá tải database. Trước khi chạy trên bảng lớn:

1. **Đo quy mô:** số dòng, kích thước bảng/index, tốc độ write, replication lag, thời gian backup và các truy vấn dài.
2. **Xem SQL cụ thể:** ADD COLUMN, UPDATE backfill, CREATE INDEX, ALTER TYPE, SET NOT NULL và DROP COLUMN có đặc điểm lock khác nhau.
3. **Tách job nặng:** backfill theo batch ngoài request path, kiểm soát TPS và dừng khi latency/lag vượt ngưỡng.
4. **Chạy rehearsal:** dùng bản sao dữ liệu có quy mô và cấu trúc giống thực tế, quan sát lock, WAL, index build và hành vi rollback.
5. **Giới hạn thời gian lock:** với PostgreSQL có thể cấu hình lock_timeout/statement_timeout phù hợp cho từng migration, không để migration giữ hàng chờ khiến request sản xuất đình trệ.
6. **Theo dõi sau từng pha:** SQL errors, HTTP 5xx, queue lag, throughput, CPU, pool saturation, replication lag và số dòng khác biệt.

Không có một mẹo DDL chung cho PostgreSQL, MySQL và các managed database. Các tối ưu như online DDL, concurrent index build, instant ADD COLUMN và transactional DDL phụ thuộc engine, phiên bản, dạng bảng và cả công cụ migration.

## 8. Tổ chức migration với Flyway hoặc Liquibase

Trong hệ Java/Spring Boot, Flyway và Liquibase thường dùng để quản lý lịch sử schema. Mỗi schema change có version, được chạy theo thứ tự và có bằng chứng đã áp dụng. Không sửa nội dung migration đã chạy ở môi trường khác để “thay thế” lịch sử: tạo migration tiếp theo khi cần sửa.

Ví dụ cấu trúc minh họa dùng Flyway:

~~~text
db/migration/
  V101__expand_add_email_address.sql
  V102__add_email_address_constraint.sql
  V103__contract_drop_legacy_email.sql

jobs/
  BackfillEmailAddressJob.java
~~~

Gợi ý luồng triển khai:

~~~text
M1: Apply V101 (expand)
    -> Verify app v1 vẫn hoạt động
R1: Deploy v1.5 (dual write, old read)
    -> Drain toàn bộ old-only writers v1
D1: Run backfill + reconciliation
    -> Verify no divergence
R2: Deploy v2 (new read, dual write)
    -> Soak/observe và giữ rollback window
R3: Deploy v3 (new read, new write)
    -> Verify không còn phụ thuộc cột cũ
M2: Apply constraint/index thích hợp và V103 contract
~~~

Đây là một **trình tự minh họa**, không nhất thiết mọi migration có số version đúng như trên. Việc chạy V102 phải đặt ở thời điểm phù hợp; nếu ép NOT NULL quá sớm thì writer cũ vẫn INSERT thiếu cột mới sẽ lỗi. Mỗi đợt deploy có thể kéo dài nhiều giờ/ngày tùy yêu cầu quan sát.

Không chạy đồng thời nhiều service instance như thể mỗi instance đều tự sở hữu độc lập một migration schema nặng. Cần quy định một điểm chạy migration duy nhất và chặn ứng dụng mới chưa tương thích cho tới khi expand hoàn tất.

Trong Spring Boot, thiết lập như Hibernate ddl-auto=update không thay thế kế hoạch migration có kiểm soát. Ở môi trường production, thường nên quản lý DDL rõ ràng bằng migration versioned và cấu hình Hibernate theo chính sách xác thực schema phù hợp của dự án.

## 9. Triển khai dần bằng feature flag và canary

Khi cần giảm rủi ro, có thể chia quyền đọc/ghi qua cờ tính năng:

- Cờ ghi kép bật khi schema mới đã có.
- Chuyển đọc sang cột mới chỉ khi đã dừng old writer, backfill xong và kiểm tra đủ điều kiện.
- Theo dõi lỗi/độ lệch trên canary trước khi mở rộng traffic.
- Tách flag dữ liệu khỏi flag giao diện; không để từng pod tự quyết ngẫu nhiên về nguồn dữ liệu chuẩn.

Trong chuyển đổi dữ liệu, **feature flag không tự giải quyết tương thích**. Nếu có instance cũ vẫn ghi cột cũ, canary đọc cột mới có thể thấy dữ liệu cũ. Phải kiểm soát writer và đồng bộ dữ liệu trước khi chuyển flag đọc.

Đối với rolling/canary trong Kubernetes, đừng chỉ kiểm tra Deployment mới đã Ready. Hãy chắc chắn các Job, CronJob, consumer, pod đang termination và phiên bản rollback cũng được tính trong kiểm kê. Các kết nối pool hoặc task đang chạy lâu có thể sống sau thời điểm router ngừng gửi request mới.

## 10. Rollback và chiến lược hồi phục

Có thể rollback application trong giai đoạn expand nếu schema mở rộng vẫn tương thích với bản cũ và dữ liệu cũ vẫn được duy trì chính xác. Ngược lại, sau contract drop cột cũ, rollback về code cũ rất có thể thất bại.

| Giai đoạn gặp lỗi | Cách xử lý thường khả thi |
| --- | --- |
| Expand DDL thất bại | Dừng tiến trình; kiểm tra trạng thái DDL thực tế và metadata, không chạy lại mù |
| V1.5 dual-write gây lỗi | Rollback về v1 nếu cột cũ còn đầy đủ; giữ cột mới để điều tra |
| Backfill bị dừng | Resume từ trạng thái hiện hành, batch idempotent; không drop dữ liệu cũ |
| Đọc cột mới gây lỗi | Chuyển lại đọc cũ nếu dual-write vẫn duy trì và invariant cho phép |
| V3 hoặc contract đã xóa cột cũ | Ưu tiên forward fix hoặc phương án phục hồi dữ liệu đã diễn tập, vì code cũ không còn tương thích |

**Rollback schema** không đồng nghĩa rollback dữ liệu: nếu thay đổi kiểu gây mất thông tin hoặc ghi dữ liệu mới không còn thể hiện được theo schema cũ, chỉ undo DDL cũng không phục hồi trạng thái nghiệp vụ trước đó. Cần xác định điểm không thể quay lại, backup/restore procedure và người có quyền đưa ra quyết định từ trước.

Một release plan nên ghi rõ: bước nào có thể đảo ngược, trạng thái cần lưu trước khi đi tiếp, metric dùng để dừng, cách xử lý khi có request đang bay, người xác nhận contract và mức mất dữ liệu có thể chấp nhận (nếu có).

## 11. Kiểm thử thay đổi schema qua nhiều phiên bản

Kiểm thử migration không dừng ở chạy script SQL thành công. Cần quan sát ứng dụng thực tế ở các trạng thái chuyển tiếp:

| Loại kiểm thử | Trọng tâm |
| --- | --- |
| Migration test | SQL áp dụng được trên schema/phiên bản dữ liệu thực tế; idempotency của job backfill |
| Compatibility test | App v1 chạy với DB đã expand; v1.5 và v2 cùng tồn tại đúng quy tắc |
| Integration test | Repository, transaction, index, constraint, serialization và worker nền |
| Data reconciliation | Giá trị cột cũ và mới khớp theo quy tắc; số dòng sai bằng 0 tại gate |
| Performance/load test | DDL/backfill/index build không vượt giới hạn latency, lock và lag |
| Rollback rehearsal | Quay về mã cũ còn hoạt động khi đang ở pha mở rộng/chuyển tiếp |
| Release smoke test | Hành trình người dùng quan trọng chạy được qua mỗi đợt deploy |

Ví dụ test ở tầng tích hợp cho v1.5: tạo user và thay đổi email thì cả hai cột cùng được ghi; khi transaction thất bại, cả hai không bị ghi nửa chừng. Ví dụ test tương thích: cho v1 cập nhật email trên schema mở rộng, sau đó chạy reconciliation và xác nhận v2 đọc đúng email mới nhất.

Tránh chỉ test bằng database trống. Với bảng có hàng triệu dòng, migration có thể ổn trong unit/integration environment nhưng tạo lock, WAL hoặc replication lag ngoài dự kiến khi gặp dữ liệu thật.

## 12. Gates và quan sát trong CI/CD

Một pipeline có thể đặt điều kiện chuyển pha:

**Trước expand:** migration được review, chạy thử đúng engine/version; đã có phương án dừng khi lock quá lâu.

**Sau expand:** schema mới hiện diện; app hiện tại vẫn không lỗi; số request thất bại và độ trễ không xấu đi rõ rệt.

**Sau bridge:** xác nhận toàn bộ instance/worker đã nâng cấp; không còn writer cũ; đường ghi kép được dùng bởi các code path liên quan.

**Sau backfill:** remaining = 0 sau vòng đối soát cuối, không phát sinh khác biệt mới, job đã lưu checkpoint và hoàn tất.

**Trước chuyển read:** rule về nguồn dữ liệu chuẩn rõ ràng; dữ liệu mới đầy đủ; canary và đường rollback còn hoạt động.

**Trước contract:** không còn mã, truy vấn, job, consumer, dashboard hoặc integration nào cần trường cũ; cửa sổ rollback đã đóng; đã kiểm tra lại hệ thống sau khi đổi.

Các chỉ số nên có: tổng dòng đã backfill, tốc độ backfill/phút, remaining, số bản ghi lỗi chuyển đổi, latency DB p95/p99, lock wait, WAL/replication lag, số lỗi SQL theo phiên bản ứng dụng, tỉ lệ lỗi API, queue lag và số instance cũ còn sống. Chọn ngưỡng cụ thể từ SLO và đo thực tế của từng hệ thống.

## 13. Sai lầm phổ biến và cách sửa

**Rename/drop ngay trong một migration:** thay bằng ADD mới, cập nhật app theo nhiều phiên bản, rồi DROP cuối cùng.

**Thêm NOT NULL quá sớm:** để cột mới nullable trong giai đoạn instance cũ chưa ghi; chỉ siết constraint sau khi mọi writer đã chuyển và dữ liệu được xác thực.

**Dual-write nhưng đọc cột mới ngay:** có thể đọc bản cũ của dữ liệu khi writer phiên bản cũ vẫn chạy. Giữ cột cũ làm nguồn chuẩn cho đến khi rút old writer và reconciliation.

**Backfill một UPDATE toàn bảng:** transaction kéo dài, khó dừng, tạo lock/WAL lớn. Chia batch, đo tiến độ và tốc độ, có khả năng resume.

**Chỉ kiểm tra deployment HTTP:** quên scheduler, consumer, ETL và truy vấn ngoài service. Kiểm kê tất cả reader/writer trước contract.

**Coi rollback là hoàn tác script:** dữ liệu có thể đã biến đổi, và schema mới/cũ có thể không tương thích. Thiết kế rollback theo mỗi giai đoạn và biết điểm không thể đảo ngược.

**Không để ý index/constraint:** dữ liệu chuyển xong nhưng mất uniqueness hoặc các đường truy vấn mới trở nên chậm. Chuyển constraint/index có chủ đích và đo hiệu năng.

**Không kiểm tra DDL trên bảng lớn:** cùng một lệnh ALTER có lock khác nhau giữa phiên bản DB. Diễn tập và dùng ngưỡng dừng phù hợp.

## 14. Checklist trước khi thu hẹp

- [ ] Cấu trúc mới đã có và ứng dụng cũ chạy được trong suốt giai đoạn expand.
- [ ] Toàn bộ đường đọc/ghi cũ đã được xác định, bao gồm API, worker, scheduler, batch, admin và integration.
- [ ] Đã dừng các writer cũ và hoàn tất đối soát dữ liệu lần cuối.
- [ ] Tất cả dữ liệu mới đáp ứng quy tắc chuyển đổi, không còn NULL/sai lệch không mong muốn.
- [ ] Đã kiểm tra uniqueness, index, khóa ngoại và các ràng buộc cần thiết.
- [ ] App mới và các consumer không còn tham chiếu cột/bảng cũ.
- [ ] Đã kiểm thử các trạng thái trung gian, tác động vận hành và đường rollback tương ứng.
- [ ] Đã có metric, log, cảnh báo và quyền dừng migration khi có sự cố.
- [ ] Cửa sổ rollback về phiên bản cũ đã được đóng theo quyết định phát hành.
- [ ] Kế hoạch backup/restore hoặc forward fix sau bước contract đã được diễn tập.

## 15. Bài tập áp dụng

Hãy giả sử Product Service đang lưu **price_cents INT** và cần chuyển sang **price_amount DECIMAL(19,2)** trong khi nhiều instance cũ vẫn phục vụ lưu lượng. Thiết kế kế hoạch triển khai có các nội dung: cách quy đổi chính xác (cents sang đơn vị tiền tệ), xử lý rounding, kiểu dữ liệu và currency; cột mới nullable hay không; cách ghi kép; thời điểm di chuyển nguồn đọc; cách backfill và kiểm chứng không mất chính xác; điều kiện bỏ cột price_cents.

Hãy tự kiểm tra phương án khi một phiên bản cũ vẫn cập nhật giá trong lúc backfill chạy. Điều gì xảy ra nếu nguồn đọc mới được mở trước khi phiên bản cũ ngừng ghi? Nếu đã contract thì còn rollback về ứng dụng cũ được không? Từ đó rút ra vì sao **giai đoạn chuyển tiếp** quan trọng bằng cả expand và contract.

## Kết luận

Thay đổi schema trong microservices là bài toán **tương thích giữa các phiên bản đang tồn tại đồng thời**. Expand–Contract chia một thay đổi phá vỡ hợp đồng thành những bước có thể triển khai, quan sát và xác nhận: mở rộng cấu trúc để code cũ tiếp tục hoạt động; chuyển tiếp cách ghi, đồng bộ dữ liệu và cách đọc; rồi thu hẹp khi mọi phụ thuộc đã rời khỏi cấu trúc cũ. Tính an toàn phụ thuộc vào việc quản lý writer/reader, tính nhất quán dữ liệu, đặc tính DDL của database, khả năng rollback và các điều kiện phát hành rõ ràng.
