
# Phối hợp migration với feature flag và phiên bản ứng dụng

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Khi ứng dụng phát hành liên tục, database và application không thể luôn được cập nhật cùng một thời điểm. Trong một đợt rolling deployment, phiên bản cũ và mới có thể cùng chạy; một phần traffic đã đi vào code mới trong khi các instance khác vẫn sử dụng schema cũ.

**Feature flag** giúp bật hoặc tắt một hành vi ở runtime theo nhóm người dùng, tenant, tỷ lệ traffic hoặc điều kiện vận hành. **Database migration** thay đổi cấu trúc và dữ liệu để hỗ trợ hành vi đó. Hai cơ chế cần được phối hợp theo một kế hoạch tương thích: schema phải đủ khả năng phục vụ mọi phiên bản ứng dụng đang chạy, feature flag chỉ được bật khi dữ liệu và contract đã sẵn sàng, và cấu trúc cũ chỉ được loại bỏ khi không còn phiên bản nào phụ thuộc.

Bài thuộc chương **Triển khai an toàn** này trình bày cách phối hợp migration với feature flag và phiên bản ứng dụng. Nội dung đi từ ma trận tương thích, chiến lược expand–migrate–contract, triển khai rolling, dual read/write, backfill, readiness gate, rollout theo tỷ lệ, kill switch, rollback và cleanup flag. Các ví dụ áp dụng cho Spring Boot, Liquibase và pipeline CI/CD.

Phạm vi bài học được xác định bởi **SERVICE_NAME=DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Theo **SERVICE_NAME_DESCRIBE**, module hướng dẫn quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

## 1. Vì sao phải phối hợp schema, ứng dụng và feature flag?

Một thay đổi sản phẩm thường có ba phần:

- **Schema/data migration:** thêm cột, bảng, index, constraint hoặc chuyển đổi dữ liệu.
- **Application version:** code mới đọc/ghi schema hoặc áp dụng logic nghiệp vụ mới.
- **Feature flag:** quyết định thời điểm và phạm vi kích hoạt hành vi mới.

Nếu ba phần này không được điều phối, có thể xảy ra các tình huống:

- Code mới đọc cột chưa được tạo.
- Code cũ không hiểu dữ liệu mới mà code mới đã ghi.
- Feature flag bật cho người dùng khi backfill chưa hoàn tất.
- Một pod cũ ghi dữ liệu theo định dạng cũ trong khi pod mới đã chuyển sang định dạng mới.
- Rollback application nhưng database đã xóa cột mà phiên bản cũ cần.
- Tắt feature flag nhưng dữ liệu đã chuyển đổi hoặc side effect đã phát sinh không tự quay lại.

Vì vậy, không nên coi migration, deploy ứng dụng và bật flag là một thao tác duy nhất. Chúng là những bước có trạng thái và điều kiện hoàn tất riêng.

## 2. Ba cơ chế có trách nhiệm khác nhau

| Cơ chế | Trách nhiệm | Không tự giải quyết |
|---|---|---|
| Liquibase changeset | Đưa schema/data tới trạng thái được định nghĩa và ghi lịch sử | Quyết định người dùng nào được bật tính năng |
| Application version | Triển khai code đọc/ghi và xử lý contract dữ liệu | Bảo đảm mọi instance cũ đã biến mất |
| Feature flag | Bật/tắt nhánh hành vi ở runtime theo policy | Tạo cột, backfill dữ liệu hoặc phục hồi schema |

Một feature flag có thể bật nhanh mà không cần deploy lại ứng dụng nếu nền tảng flag hỗ trợ cập nhật động. Nhưng nó không thể làm cho một cột chưa tồn tại xuất hiện. Tương tự, Liquibase update thành công không có nghĩa code mới đã sẵn sàng hoặc người dùng nên được chuyển sang tính năng mới.

Hãy xác định riêng owner và nguồn sự thật của từng cơ chế: changelog cho database, release/artifact cho application, flag service hoặc cấu hình được quản lý cho feature flag.

## 3. Ma trận tương thích giữa phiên bản ứng dụng và schema

Trước khi phát hành, lập ma trận cho các phiên bản có thể cùng tồn tại:

| Database schema | App cũ | App tương thích mới | App chỉ hỗ trợ schema mới |
|---|---|---|---|
| Schema cũ | Hỗ trợ | Chỉ nếu có fallback | Không hỗ trợ |
| Schema expand | Phải tiếp tục hỗ trợ | Hỗ trợ | Có thể hỗ trợ |
| Schema migrate | Có thể hỗ trợ nếu dữ liệu cũ còn | Hỗ trợ cả hai dạng | Hỗ trợ nếu backfill đạt |
| Schema contract | Thường không hỗ trợ | Có thể không còn hỗ trợ | Hỗ trợ |

Mục tiêu của giai đoạn rolling là schema expand vẫn phục vụ được app cũ lẫn app mới. Chỉ chuyển sang contract khi mọi instance cũ đã dừng, các consumer liên quan đã chuyển đổi và rollback window đã được đánh giá.

Không dùng một con số version đơn lẻ để suy ra tương thích. Hai phiên bản có thể cùng đọc schema nhưng khác semantics dữ liệu, transaction hoặc cách ghi. Cần test các cặp app/schema thực sự được phép chạy cùng nhau.

## 4. Expand–migrate–contract là khung phối hợp chính

Chiến lược **expand–migrate–contract** chia thay đổi phá vỡ thành nhiều release tương thích.

<box />

~~~text
EXPAND
  Thêm cấu trúc mới, giữ cấu trúc cũ
       |
       v
MIGRATE
  Deploy code tương thích, chuyển dữ liệu,
  bật flag dần và xác minh
       |
       v
CONTRACT
  Dừng dùng cấu trúc cũ, loại bỏ sau
  khi không còn consumer phụ thuộc
~~~

**Expand:** thêm cột/bảng/index theo cách không làm hỏng phiên bản đang chạy. Cấu trúc mới thường nullable hoặc có default tương thích; chưa xóa trường cũ.

**Migrate:** deploy code có thể xử lý cả trạng thái cũ và mới, backfill dữ liệu, chuyển read path qua feature flag, quan sát và tăng dần phạm vi.

**Contract:** sau khi xác nhận không còn app/consumer cũ, xóa code tương thích tạm thời và loại bỏ cấu trúc cũ trong một changeset riêng.

Không gộp expand và contract vào cùng một changeset/release nếu hệ thống cần rolling deployment hoặc cần khả năng quay lại phiên bản ứng dụng cũ.

## 5. Ví dụ: chuyển từ email sang email_normalized

Giả sử bảng customer hiện có cột \`email\`. Sản phẩm muốn chuẩn hóa địa chỉ email để tìm kiếm nhất quán và dùng cột mới \`email_normalized\`.

Một lần đổi tên trực tiếp:

~~~sql
ALTER TABLE customer RENAME COLUMN email TO email_normalized;
~~~

có thể làm code cũ lỗi ngay trong rolling deployment. Thay vào đó, chia thành nhiều giai đoạn:

1. Thêm \`email_normalized\` nullable.
2. Deploy application version có thể ghi cả \`email\` và \`email_normalized\`.
3. Chờ tất cả instance chỉ ghi \`email\` cũ được drain.
4. Backfill giá trị mới cho các hàng còn thiếu hoặc chưa đồng bộ.
5. Xác minh dữ liệu và bật flag đọc từ cột mới cho một nhóm nhỏ.
6. Tăng dần rollout sau khi metric đạt.
7. Sau thời gian ổn định, ngừng ghi/đọc \`email\` cũ.
8. Xóa cột cũ trong release contract riêng.

Trong toàn bộ giai đoạn, schema phải hỗ trợ các phiên bản đang chạy và feature flag không được bật trước khi dữ liệu đáp ứng invariant.

## 6. Giai đoạn expand bằng Liquibase

Ví dụ changeset YAML thêm cột mới:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-add-customer-email-normalized
      author: customer-team
      comment: Mở rộng schema để hỗ trợ email chuẩn hóa.
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: email_normalized
                  type: varchar(320)
                  constraints:
                    nullable: true
~~~

Cột mới nullable giúp phiên bản cũ vẫn insert customer mà chưa biết tới cột đó. Trước khi áp dụng, xác minh DBMS, kích thước bảng, lock, default và khả năng thêm cột online.

Không đặt NOT NULL ngay trong bước expand nếu ứng dụng cũ chưa ghi cột này. Không xóa cột email cũ trong cùng release. Có thể tạo index ở changeset riêng sau khi đánh giá kích thước dữ liệu và khả năng online/concurrent của DBMS.

Rollback tự động của addColumn có thể dẫn đến dropColumn trên DBMS được hỗ trợ, nhưng điều đó sẽ xóa dữ liệu mới đã được ghi. Trong production, rollback application thường nên giữ schema expand; không tự động chạy rollback DDL chỉ vì rollout code thất bại.

## 7. Phiên bản tương thích: đọc cũ, ghi cả hai

Sau khi schema expand, deploy một phiên bản trung gian, gọi là **compatibility version**. Phiên bản này:

- Vẫn đọc cột cũ để tương thích dữ liệu hiện tại.
- Ghi cột cũ như trước.
- Đồng thời ghi cột mới theo cùng một transaction khi có thể.
- Chưa yêu cầu feature flag đọc cột mới.
- Có metric để phát hiện hai giá trị không nhất quán.

Ví dụ Java minh họa:

~~~java
@Transactional
public void updateEmail(long customerId, String email) {
    String normalized = normalizeEmail(email);

    customerRepository.updateEmail(customerId, email);
    customerRepository.updateNormalizedEmail(customerId, normalized);
}
~~~

Đây là pseudo-code; cách cập nhật repository và transaction phụ thuộc ORM/JDBC và thiết kế domain. Nếu hai cột nằm trong cùng database, cập nhật trong một transaction có thể giữ tính nhất quán tốt hơn. Nếu ghi qua hai database/service khác nhau, cần cơ chế phân tán phù hợp như outbox/event và reconciliation; không giả định một transaction cục bộ bao phủ nhiều database.

Trong rolling deployment, app cũ có thể vẫn ghi cột cũ mà không cập nhật cột mới. Vì vậy, chưa được bật read flag cho toàn bộ traffic cho đến khi các writer cũ đã được drain và dữ liệu được backfill/đối chiếu.

## 8. Feature flag điều khiển read path

Khi compatibility version đã chạy ổn định, feature flag có thể điều khiển nhánh đọc:

~~~java
public CustomerEmail getEmail(Customer customer, FlagContext context) {
    if (featureFlags.isEnabled("customer-email-normalized-read", context)) {
        return CustomerEmail.fromNormalized(customer.getEmailNormalized());
    }
    return CustomerEmail.fromLegacy(customer.getEmail());
}
~~~

Flag có thể được đánh giá theo user, tenant, region hoặc cohort. Cần quy định giá trị mặc định an toàn khi flag service không truy cập được; ví dụ tiếp tục dùng read path cũ nếu cột cũ vẫn tồn tại và dữ liệu cũ còn đáng tin.

Không dùng flag để bỏ qua authorization, validation hoặc các kiểm soát bảo mật. Feature flag chỉ quyết định tính năng/nhánh xử lý nào được sử dụng, không thay thế quyền truy cập nghiệp vụ.

Tên flag nên mô tả hành vi, có owner, ngày tạo, mục đích, điều kiện xóa và trạng thái mặc định. Tránh flag mơ hồ như \`new-feature\` hoặc dùng lại cùng tên cho một hành vi khác sau khi flag cũ đã bị xóa.

## 9. Feature flag không phải migration flag

Một **feature flag** điều khiển hành vi ứng dụng. Một **migration flag** hoặc trạng thái migration điều khiển tiến trình chuyển đổi dữ liệu. Hai loại có thể liên quan nhưng không nên nhập làm một.

Ví dụ:

- Feature flag \`customer-email-normalized-read\`: chọn đọc cột cũ hay mới.
- Migration progress: số lượng customer đã được backfill.
- Readiness condition: không còn hàng thiếu giá trị hoặc mismatch vượt ngưỡng.
- Release state: compatibility version đã được triển khai trên mọi instance.

Nếu chỉ bật feature flag mà không kiểm tra tiến độ backfill, app có thể đọc NULL hoặc dữ liệu sai. Nếu chỉ đánh dấu migration hoàn tất mà không kiểm tra code version, app cũ có thể tiếp tục ghi theo định dạng cũ.

Nguồn trạng thái migration nên có thể kiểm chứng từ job, bảng progress, metric hoặc query; feature flag service không nên là nơi duy nhất ghi nhận tiến độ dữ liệu.

## 10. Backfill trước khi chuyển read path

Sau khi writer tương thích đã được triển khai và writer cũ được drain, backfill các hàng còn thiếu:

~~~sql
UPDATE customer
SET email_normalized = LOWER(TRIM(email))
WHERE email_normalized IS NULL;
~~~

Câu lệnh minh họa giả định quy tắc chuẩn hóa là trim và lowercase; quy tắc email thật cần được xác định theo nghiệp vụ, Unicode, domain, local-part và chính sách định danh. Không mặc định lowercase toàn bộ email luôn đúng với mọi hệ thống.

Với bảng lớn, chạy batch theo khóa ổn định, có checkpoint và metric thay vì một UPDATE toàn bảng trong changeset duy nhất. Ví dụ khái niệm:

~~~text
Đọc batch customer_id từ watermark
        |
        v
Tính giá trị normalized theo quy tắc đã chốt
        |
        v
Ghi giá trị nếu bản ghi chưa được xử lý
        |
        v
Đối chiếu row count / mismatch
        |
        v
Lưu checkpoint và tiếp tục batch kế tiếp
~~~

Job backfill cần idempotent hoặc có khả năng resume sau khi lỗi. Nếu ứng dụng tiếp tục ghi trong lúc backfill, cần bảo đảm không ghi đè giá trị mới bằng dữ liệu cũ; có thể dùng update có điều kiện, version/timestamp hoặc transaction phù hợp.

## 11. Readiness gate trước khi bật flag

Không bật read flag chỉ vì migration job exit code 0. Một gate có thể kiểm tra:

- Cột mới tồn tại đúng kiểu và schema.
- Compatibility version đã triển khai đủ số instance.
- Không còn writer cũ chưa hỗ trợ cột mới.
- Backfill đạt số lượng và tỷ lệ hoàn tất yêu cầu.
- Không có mismatch vượt ngưỡng giữa cột cũ và mới.
- Query đọc cột mới hoạt động với index/plan mong muốn.
- Database latency, lock wait và error rate ổn định.
- Feature flag có default và kill switch đã được thử.
- Có owner trực vận hành trong thời gian rollout.

Ví dụ truy vấn chỉ đọc:

~~~sql
SELECT
    COUNT(*) AS total_rows,
    SUM(CASE WHEN email_normalized IS NULL THEN 1 ELSE 0 END) AS missing_rows
FROM customer;
~~~

Cú pháp aggregate có thể khác theo DBMS. Với dữ liệu lớn, query cần đánh giá chi phí và có thể dựa trên bảng progress hoặc metric đã được kiểm chứng. Không log email hoặc dữ liệu cá nhân để chứng minh readiness.

## 12. Rollout theo cohort hoặc tỷ lệ traffic

Khi gate đạt, bật feature flag theo từng bước:

| Giai đoạn | Phạm vi gợi ý | Mục tiêu |
|---|---|---|
| Internal | Nhân viên/test tenant | Kiểm tra hành vi trên dữ liệu thực có kiểm soát |
| Canary | Một nhóm nhỏ hoặc tỷ lệ thấp | Phát hiện lỗi sớm |
| Limited | Một số tenant/region | Kiểm tra tải và khác biệt dữ liệu |
| Broad | Tăng dần phần lớn traffic | Đánh giá ổn định ở quy mô lớn |
| Full | Toàn bộ phạm vi dự kiến | Hoàn tất rollout tính năng |

Các tỷ lệ cụ thể phụ thuộc sản phẩm và mức độ rủi ro; không có một con số mặc định phù hợp cho mọi hệ thống. Tăng tỷ lệ theo metric, không theo lịch cố định nếu hệ thống đang có lỗi.

Cần đảm bảo cohort ổn định nếu người dùng thực hiện nhiều request liên quan; tránh cùng một user lúc đọc schema cũ, lúc đọc schema mới ngoài ý muốn. Flag evaluation có thể dựa trên user/tenant key để giữ phân bổ nhất quán.

## 13. Quan sát trong thời gian rollout

Theo dõi ít nhất hai nhóm chỉ số:

**Chỉ số ứng dụng:**

- Error rate, timeout và exception của nhánh mới.
- Latency p50/p95/p99.
- Tỷ lệ fallback về read path cũ.
- Tỷ lệ dữ liệu thiếu hoặc không hợp lệ.
- Kết quả nghiệp vụ như tìm kiếm, đăng nhập hoặc tạo đơn.
- Phân bố lỗi theo cohort/tenant/app version.

**Chỉ số database:**

- Query latency và execution plan.
- CPU, I/O, connection count.
- Lock wait, deadlock và replication lag.
- Tỷ lệ NULL/mismatch.
- Index usage và kích thước index.
- Backfill progress và thời gian batch.

Dashboard cần phân biệt app version và flag state để biết lỗi chỉ xảy ra trên cohort mới hay trên toàn hệ thống. Không chỉ quan sát tổng error rate vì một cohort nhỏ có thể gặp lỗi nghiêm trọng bị che bởi traffic còn lại.

## 14. Kill switch: tắt hành vi mới nhanh chóng

Một feature flag vận hành có thể làm kill switch nếu hành vi mới gây lỗi. Khi tắt:

- Ứng dụng quay về nhánh đọc/ghi cũ nếu code còn hỗ trợ.
- Pipeline dừng tăng rollout hoặc dừng bước contract.
- Nhóm giữ nguyên schema expand để điều tra.
- Kiểm tra dữ liệu đã ghi trong giai đoạn flag bật.
- Quyết định forward fix hoặc thử lại sau.

**Tắt flag không tự rollback database.** Nếu code mới đã ghi dữ liệu vào cột mới, dữ liệu đó vẫn còn. Nếu hệ thống đã gửi event, thanh toán hoặc side effect ra bên ngoài, tắt flag không thể thu hồi những hành động đã xảy ra.

Một kill switch tốt phải được thử trước release, có người sở hữu và không phụ thuộc chính nhánh code đang gặp sự cố. Nếu flag service không sẵn sàng, ứng dụng cần có fallback mặc định được thiết kế an toàn.

## 15. Dual read và dual write: chỉ dùng khi có lý do rõ

Dual write là ghi cả cấu trúc cũ và mới. Dual read là đọc cả hai hoặc fallback giữa chúng. Những cơ chế này giúp chuyển đổi dần nhưng cũng tạo thêm độ phức tạp.

Rủi ro:

- Một write thành công, write còn lại thất bại nếu không cùng transaction.
- Hai cột lệch nhau do app version cũ.
- Retry tạo duplicate side effect.
- Read fallback che giấu dữ liệu mới chưa hoàn tất.
- Nhiều nguồn ghi khác nhau không tuân thủ cùng quy tắc chuẩn hóa.

Nếu hai cột trong cùng database, có thể cập nhật trong một transaction và thêm invariant/metric kiểm tra. Nếu dữ liệu đi qua service/database khác nhau, cân nhắc outbox, event version, idempotency key và reconciliation job.

Không duy trì dual write lâu hơn cần thiết. Khi đã chuyển read/write path và xác nhận dữ liệu, lập lịch bỏ logic tương thích trong một release sau.

## 16. Phiên bản cũ và mới cùng chạy trong rolling deployment

Giả sử deployment có 6 replica:

- 2 pod chạy app v1, chỉ biết cột email.
- 4 pod chạy app v2, biết cả email và email_normalized.

Trong thời gian này, v1 vẫn có thể ghi email mà không cập nhật email_normalized. Vì vậy:

1. Schema expand phải được chạy trước khi v2 rollout.
2. v2 phải giữ khả năng hoạt động với dữ liệu cũ.
3. Không bật read flag toàn hệ thống khi v1 còn chạy.
4. Sau khi v1 được drain, kiểm tra không còn worker/consumer cũ.
5. Chạy backfill hoặc reconciliation cuối.
6. Xác minh invariant rồi mới bật flag theo cohort.

Không chỉ kiểm tra Deployment desired replicas. Cần xác nhận phiên bản thực sự đang phục vụ traffic, background worker, scheduled job, consumer queue và các ứng dụng tích hợp cũng đã chuyển đổi.

## 17. Background job và consumer cũng là phiên bản ứng dụng

Một hệ thống có thể đã rollout API server v2 nhưng worker xử lý queue vẫn là v1. Worker cũ có thể tiếp tục ghi dữ liệu theo schema cũ trong khi feature flag đã bật cho API.

Danh sách consumer cần kiểm kê:

- API/web application.
- Background worker và scheduler.
- Consumer Kafka/RabbitMQ.
- ETL/CDC connector.
- Báo cáo, BI và export job.
- Script vận hành hoặc integration bên ngoài.
- Mobile/desktop client nếu contract API thay đổi.

Trước contract schema, phải xác định mọi writer/reader của đối tượng bị thay đổi. Một cột không còn được API sử dụng vẫn có thể được báo cáo hoặc batch job đọc hàng đêm.

## 18. Feature flag state và schema migration nên được triển khai độc lập

Tránh tạo một changeset Liquibase vừa ALTER TABLE vừa bật feature flag trong một lần chạy. Hai thao tác có vòng đời và cách phục hồi khác nhau:

- DDL có thể cần lock, transaction và thời gian thực thi.
- Flag cần thay đổi runtime nhanh, targeting và audit.
- Rollback DDL có thể phá dữ liệu.
- Flag có thể cần tắt ngay mà không chờ database deployment.

Liquibase ghi nhận changeset đã xử lý trong **DATABASECHANGELOG**; **DATABASECHANGELOGLOCK** điều phối các tiến trình Liquibase dùng chung bảng khóa. Hai bảng này không quản lý trạng thái feature flag và không điều phối các database khác. Nếu changeset dùng `runInTransaction: false`, hoặc DBMS có DDL tự commit, một lần chạy thất bại có thể để lại thay đổi một phần. Trước khi retry, phải đối chiếu lịch sử Liquibase với schema và dữ liệu thực tế của đúng database; không chỉ dựa vào exit code của job.

Một quy trình phù hợp:

1. Liquibase expand schema.
2. Application compatibility version được deploy với flag off.
3. Backfill và readiness checks.
4. Flag được bật theo rollout policy.
5. Sau khi ổn định, deploy app bỏ code cũ.
6. Liquibase contract schema trong một release riêng.

Nếu flag configuration được lưu trong database, vẫn nên có owner và API/quy trình cập nhật riêng. Không để migration schema tự động bật flag mà không có readiness gate và approval.

## 19. Cấu hình Spring Boot và feature flag

Spring Boot có thể bật Liquibase khi startup:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
~~~

Nếu CI/CD là migration owner, runtime có thể tắt auto-run:

~~~yaml
spring:
  liquibase:
    enabled: false
~~~

Feature flag thường được đọc từ một provider/configuration service:

~~~java
if (featureFlagService.isEnabled("customer-email-normalized-read", context)) {
    return repository.findByNormalizedEmail(email);
}
return repository.findByLegacyEmail(email);
~~~

Tên class/method chỉ là ví dụ. Cần xử lý lỗi provider, cache, timeout và default state. Không gọi feature flag service theo cách làm request quan trọng bị treo vô hạn. Có thể cache trạng thái flag với thời hạn và fallback đã được xác định.

Không dùng property \`spring.liquibase.enabled\` như feature flag cho nghiệp vụ. Property này điều khiển migration startup, còn flag nghiệp vụ điều khiển hành vi ứng dụng.

## 20. Test ma trận app/schema/flag

Kiểm thử một nhánh code với một schema là chưa đủ. Tối thiểu cần xác minh các tổ hợp được phép:

| Schema | App version | Flag | Kết quả cần xác nhận |
|---|---|---|---|
| Cũ | Cũ | Off | Luồng hiện tại vẫn hoạt động |
| Expand | Cũ | Off | App cũ không lỗi vì cột mới |
| Expand | Compatibility mới | Off | Ghi tương thích; đọc cũ |
| Expand + backfill | Compatibility mới | Canary on | Đọc mới đúng cho cohort |
| Expand + backfill | Compatibility mới | Off | Kill switch quay về nhánh cũ |
| Expand | App mới sau rollout | On | Không có missing/mismatch vượt ngưỡng |
| Contract | App mới đã loại code cũ | On | Chỉ chạy sau khi không còn consumer cũ |

Nếu có nhiều app version cùng tồn tại, test rolling overlap. Nếu flag có targeting theo tenant/region, test cả trường hợp flag khác nhau trong cùng một thời điểm.

Đừng chỉ test flag bật; cần test flag tắt, provider không truy cập được, cấu hình thiếu, dữ liệu không đầy đủ và rollback application.

## 21. Precondition và readiness cho migration

Liquibase precondition có thể xác nhận trạng thái cục bộ trước changeset:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-create-customer-email-index
      author: customer-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - columnExists:
            tableName: customer
            columnName: email_normalized
      changes:
        - createIndex:
            tableName: customer
            indexName: idx_customer_email_normalized
            columns:
              - column:
                  name: email_normalized
~~~

Precondition này kiểm tra cột ở database Liquibase đang kết nối. Nó không chứng minh app v2 đã được rollout, worker cũ đã dừng hoặc feature flag đã được cấu hình.

Các điều kiện liên quan ứng dụng/flag cần được orchestration hoặc release gate kiểm tra. Không đưa trạng thái runtime phức tạp vào precondition SQL chỉ để biến Liquibase thành feature flag coordinator.

## 22. Contract: chỉ xóa cấu trúc cũ khi đủ điều kiện

Khi feature flag đã bật ổn định, code mới chỉ dùng cột mới và mọi consumer cũ đã được loại bỏ, có thể lập kế hoạch contract.

Trước khi drop cột email cũ:

- Đã xác minh không còn app version đọc/ghi cột đó.
- Background worker, report, ETL và integration đã chuyển đổi.
- Flag cũ đã được dọn hoặc trạng thái của nó đã rõ.
- Dữ liệu cũ đã được lưu/archived nếu có yêu cầu.
- Không còn dual write hoặc fallback đọc cột cũ.
- Có backup/PITR và kế hoạch forward fix.
- Đã kiểm tra dependency như view, trigger, index, procedure.
- Có thời gian theo dõi sau rollout đủ dài theo rủi ro.

Changeset contract nên riêng biệt:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 010-drop-legacy-customer-email
      author: customer-team
      comment: Chỉ chạy sau khi mọi consumer đã chuyển sang email_normalized.
      changes:
        - dropColumn:
            tableName: customer
            columnName: email
~~~

Đây là thao tác phá hủy dữ liệu cột cũ. Không đưa vào cùng release với lần bật flag đầu tiên. Nếu còn khả năng cần quay lại app cũ, giữ cột thêm một thời gian và trì hoãn contract.

## 23. Rollback application, flag và database là ba quyết định riêng

Khi canary có lỗi, thứ tự xử lý thường là:

1. Tắt flag hoặc giảm rollout để ngừng nhánh hành vi mới.
2. Dừng rollout application tiếp theo.
3. Nếu cần, rollback application về compatibility version.
4. Giữ schema expand để tránh phá dữ liệu mới.
5. Kiểm tra dữ liệu đã ghi và side effect.
6. Chọn forward fix, reconciliation hoặc phục hồi từ backup.
7. Chỉ rollback database nếu SQL đảo ngược an toàn và đã được kiểm chứng.

| Hành động | Điều nó làm | Điều nó không làm |
|---|---|---|
| Tắt feature flag | Dừng nhánh hành vi mới | Không xóa dữ liệu đã ghi |
| Rollback app | Đưa code về phiên bản cũ | Không tự khôi phục schema |
| Liquibase rollback | Thực hiện changeset đảo ngược trong phạm vi chọn | Không thay thế backup, không chắc phục hồi DML |
| Forward fix | Tạo thay đổi mới để sửa trạng thái hiện tại | Không đưa lịch sử về mốc cũ |
| Restore/PITR | Khôi phục dữ liệu từ điểm phục hồi | Có thể làm mất giao dịch sau điểm đó |

Không coi “flag off” là rollback hoàn chỉnh. Nếu nhánh mới đã phát sinh event, gửi email, tính phí hoặc tạo record bên ngoài database, cần quy trình compensating action riêng.

## 24. Tránh bật flag trước khi migration và backfill sẵn sàng

Một lỗi phổ biến là deploy app có flag off, chạy migration add column, rồi bật flag ngay khi Liquibase update thành công. Nếu cột mới cần backfill, ứng dụng có thể đọc NULL hoặc dữ liệu chưa chuẩn hóa.

Readiness gate nên kiểm tra ít nhất:

- Schema mới tồn tại đúng định nghĩa.
- Writer tương thích đã rollout và writer cũ đã drain.
- Backfill hoàn tất hoặc tỷ lệ còn thiếu nằm trong ngưỡng được chấp thuận.
- Dữ liệu mới và cũ khớp theo quy tắc đã định.
- Query/index có hiệu năng phù hợp.
- Flag provider hoạt động và kill switch được thử.
- Metric/alert đã được thiết lập.
- Owner sẵn sàng theo dõi rollout.

Nếu dữ liệu tiếp tục thay đổi, readiness có thể cần kiểm tra watermark hoặc reconciliation liên tục thay vì một lần COUNT. Gate phải đo đúng invariant nghiệp vụ.

## 25. Quản lý vòng đời feature flag

Feature flag tạo nợ kỹ thuật nếu không có kế hoạch dọn dẹp. Mỗi flag nên có metadata:

| Trường | Nội dung |
|---|---|
| Key | Tên duy nhất, mô tả hành vi |
| Owner | Nhóm/cá nhân chịu trách nhiệm |
| Purpose | Lý do tồn tại |
| Created/review date | Thời điểm tạo và ngày xem xét |
| Default | Hành vi khi provider lỗi hoặc không có cấu hình |
| Rollout policy | Cohort, tenant, tỷ lệ hoặc điều kiện |
| Kill switch | Cách tắt nhanh |
| Removal condition | Điều kiện xóa flag và nhánh code cũ |
| Related release | Migration/app version liên quan |

Sau khi tính năng ổn định:

1. Đặt flag về trạng thái cuối đã phê duyệt.
2. Xác nhận không còn cần rollback qua nhánh cũ.
3. Xóa nhánh code không còn dùng.
4. Xóa flag khỏi provider/configuration.
5. Xóa compatibility code và dual write.
6. Sau đó mới contract schema nếu an toàn.

Không để một flag cũ tiếp tục điều khiển hành vi không còn được kiểm thử. Cũng không tái sử dụng key đã xóa cho tính năng khác nếu hệ thống có cache/audit hoặc client cũ còn giữ giá trị.

## 26. Security và consistency khi dùng feature flag

Feature flag không phải cơ chế authorization. Không đặt quyền truy cập dữ liệu nhạy cảm chỉ dựa trên một flag có thể bị thay đổi bởi người vận hành hoặc config service.

Các nguyên tắc:

- Authorization vẫn được kiểm tra độc lập trong server-side code.
- Flag targeting không chứa PII nếu không cần.
- Chỉ người có quyền mới được thay đổi flag production.
- Ghi audit ai bật/tắt, thời gian, phạm vi và lý do.
- Cache và fallback không được tạo trạng thái mở quyền ngoài ý muốn.
- Không để client tự gửi giá trị flag rồi server tin tưởng vô điều kiện.
- Đảm bảo flag mới không làm thay đổi semantics transaction hoặc bỏ qua invariant dữ liệu.
- Với nhiều service, version hóa contract và rollout flag nhất quán theo dependency.

Nếu flag service bị lỗi, hệ thống phải có default behavior rõ ràng. Với tính năng ảnh hưởng dữ liệu hoặc thanh toán, mặc định thường phải chọn nhánh đã ổn định và không tạo side effect mới.

## 27. Quan sát và audit trong một đợt rollout

Một release record nên kết nối ba dòng thời gian:

1. **Database:** changeset nào chạy, target nào, revision và kết quả hậu kiểm.
2. **Application:** version nào rollout, instance nào còn chạy version cũ, thời gian drain.
3. **Feature flag:** thời điểm đổi state, cohort/tỷ lệ, operator và metric trước/sau.

Dashboard có thể hiển thị:

| Thời điểm | Schema | App | Flag | Quyết định |
|---|---|---|---|---|
| T0 | Expand hoàn tất | v1 | Off | Tiếp tục |
| T1 | Expand | v1 + v2 compatibility | Off | Chờ drain v1 |
| T2 | Backfill đạt | v2 | Off | Canary |
| T3 | Backfill đạt | v2 | 5% on | Theo dõi |
| T4 | Backfill đạt | v2 | 50% on | Mở rộng nếu metric đạt |
| T5 | Ổn định | v2 | 100% on | Chờ contract window |
| T6 | Contract | v3 | On | Xóa cấu trúc cũ |

Bảng này minh họa thứ tự, không phải lịch thời gian bắt buộc. Giữ log không chứa secret/PII và liên kết được với release ID, commit SHA, target ID và change request.

## 28. Lỗi thường gặp khi phối hợp migration và feature flag

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| App mới lỗi missing column | Rollout app trước migration expand | Chạy migration prerequisite và kiểm tra target |
| App cũ lỗi sau expand | Thay đổi không backward-compatible hoặc default/constraint phá vỡ | Thiết kế expand tương thích và test app cũ |
| Flag bật nhưng dữ liệu mới NULL | Backfill chưa xong hoặc writer cũ còn hoạt động | Tắt flag, drain writer cũ, backfill/reconcile |
| Hai cột lệch giá trị | Dual write không cùng transaction hoặc có writer cũ | Xác định source of truth, sửa write path và reconcile |
| Canary lỗi nhưng rollback app không đủ | Database đã contract hoặc dữ liệu mới không tương thích | Giữ schema expand, forward fix/restore theo runbook |
| Flag off nhưng side effect vẫn tiếp tục | Event/job đã phát sinh hoặc worker không kiểm tra flag | Dừng producer/consumer và xử lý compensating action |
| Flag service lỗi làm request timeout | Không có cache/default/fallback | Thiết kế timeout và default state an toàn |
| Pod cũ vẫn ghi schema cũ | Background worker hoặc instance chưa drain | Kiểm kê mọi writer, không chỉ API replica |
| Contract drop column làm báo cáo lỗi | ETL/report/BI còn đọc cột cũ | Kiểm kê consumer và readiness trước contract |
| Rollback Liquibase xóa dữ liệu mới | Dùng dropColumn sau khi app đã ghi | Không rollback DDL tự động; backup/forward fix |
| Feature flag bị quên lâu dài | Không có owner/removal condition | Đặt lifecycle, deadline và cleanup task |
| Môi trường staging chạy được, production lỗi | Data volume/lock/flag targeting khác nhau | Rehearsal với dữ liệu đại diện và cấu hình tương đương |

## 29. Bài thực hành: chuyển một cột với feature flag

Thực hiện trên database disposable, không dùng production.

### Bước 1 — Tạo schema cũ

Tạo bảng customer có cột email và dữ liệu giả đại diện. Ghi lại số hàng, giá trị NULL và các consumer đang đọc cột này.

### Bước 2 — Expand bằng Liquibase

Dùng changeset addColumn tạo email_normalized nullable. Chạy validate, status, updateSQL, review và update. Xác nhận app cũ vẫn hoạt động với schema expand.

### Bước 3 — Deploy compatibility version

Deploy code có thể ghi email và email_normalized, nhưng vẫn đọc email. Trong môi trường rolling giả lập, giữ một writer cũ để chứng minh cột mới có thể còn thiếu dữ liệu.

### Bước 4 — Drain writer cũ và backfill

Xác nhận mọi API/worker cũ đã dừng. Chạy backfill theo batch nếu dữ liệu đủ lớn. Kiểm tra NULL, mismatch và quy tắc chuẩn hóa. Thử dừng job giữa chừng rồi resume để kiểm chứng idempotency.

### Bước 5 — Canary flag

Bật customer-email-normalized-read cho một cohort thử nghiệm. Theo dõi latency, error rate, fallback và mismatch. Nếu có lỗi, tắt flag và xác nhận app quay về nhánh cũ trong khi schema expand vẫn giữ nguyên.

### Bước 6 — Tăng rollout và cleanup

Mở rộng flag khi gate đạt. Sau thời gian ổn định, deploy version bỏ dual write/legacy read. Kiểm tra mọi consumer đã chuyển đổi trước khi tạo changeset contract xóa email cũ.

### Bước 7 — Thử rollback theo từng lớp

Thử riêng:
- Tắt flag.
- Rollback application về compatibility version.
- Đánh giá SQL rollback của changeset expand.
- Khôi phục từ backup hoặc forward fix trong tình huống dữ liệu mới đã phát sinh.

Ghi rõ hành động nào chỉ đổi hành vi, hành động nào thay đổi schema và hành động nào có thể làm mất dữ liệu.

## 30. Checklist trước khi phối hợp migration với feature flag

- [ ] Đã xác định schema cũ/mới và các application version có thể chạy đồng thời.
- [ ] Migration expand backward-compatible với app đang chạy.
- [ ] Changeset Liquibase có id/author ổn định, precondition và rollback được đánh giá.
- [ ] Cột/bảng mới chưa bị đặt constraint phá vỡ writer cũ.
- [ ] Compatibility version có read/write behavior được test.
- [ ] Đã kiểm kê API, worker, scheduler, queue consumer, ETL và báo cáo.
- [ ] Đã xác định source of truth trong giai đoạn dual write.
- [ ] Backfill có batch/checkpoint/resume khi cần.
- [ ] Có invariant và readiness gate trước khi bật flag.
- [ ] Feature flag có owner, default state, targeting, kill switch và removal condition.
- [ ] Flag không thay thế authorization hoặc validation.
- [ ] Rollout theo cohort/tỷ lệ có metric và alert.
- [ ] Đã thử flag off, provider failure và app rollback.
- [ ] Có kế hoạch xử lý side effect đã phát sinh.
- [ ] Schema expand được giữ trong rollback window nếu app cũ cần.
- [ ] Contract chỉ chạy sau khi mọi consumer cũ đã chuyển đổi.
- [ ] SQL preview và DDL lock/transaction được đánh giá.
- [ ] Release record liên kết migration revision, app version và flag changes.
- [ ] Đã rehearsal trên database có dữ liệu đại diện.
- [ ] Có owner trực theo dõi, approval và runbook recovery.
- [ ] Feature flag tạm thời có lịch dọn dẹp và code cleanup.

**Ghi nhớ:** Liquibase chuẩn bị schema và dữ liệu; application version cung cấp code tương thích; feature flag điều khiển thời điểm kích hoạt hành vi. Hãy expand trước, triển khai compatibility version, drain writer cũ, backfill và kiểm tra invariant, sau đó mới bật flag theo cohort. Chỉ contract cấu trúc cũ khi không còn consumer phụ thuộc và rollback window đã được đánh giá. Tắt flag không phục hồi database, rollback app không tự đảo schema, còn rollback DDL có thể làm mất dữ liệu mới. Phối hợp ba lớp bằng readiness gate, metric, release record và kế hoạch forward fix giúp triển khai an toàn qua Spring Boot hoặc CI/CD.

