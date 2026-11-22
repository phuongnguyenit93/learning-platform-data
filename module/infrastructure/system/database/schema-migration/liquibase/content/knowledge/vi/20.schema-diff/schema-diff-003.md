# Tạo snapshot phục vụ đối chiếu và lưu dấu trạng thái

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chúng ta quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài thuộc chương **So sánh lược đồ** này tập trung vào cách tạo **snapshot** để ghi lại trạng thái cấu trúc database tại một thời điểm, dùng snapshot làm bằng chứng đối chiếu và lưu dấu trạng thái giữa các lần triển khai.

Snapshot giúp trả lời những câu hỏi như: database trước release có những bảng, cột, khóa và index nào? Sau migration, những đối tượng nào đã xuất hiện hoặc thay đổi? Staging có còn khớp với schema chuẩn đã nghiệm thu không? Một thay đổi thủ công của DBA đã làm database lệch khỏi changelog ở đâu?

Trong Liquibase, snapshot là một biểu diễn có cấu trúc của những đối tượng database mà công cụ có thể đọc được tại thời điểm chụp. Snapshot hữu ích cho so sánh schema, kiểm kê, baseline và điều tra drift. Tuy nhiên, **snapshot không phải backup database, không phải bản sao dữ liệu nghiệp vụ và không tự khôi phục được database**. Cần hiểu rõ giới hạn này trước khi đưa snapshot vào quy trình release.

## 1. Snapshot là gì?

**Snapshot schema** là bản ghi có cấu trúc về trạng thái metadata của database tại một thời điểm. Tùy DBMS, phiên bản Liquibase, quyền truy cập và phạm vi được cấu hình, snapshot có thể mô tả các đối tượng như:

- Catalog và schema.
- Bảng, cột, kiểu dữ liệu, nullability và default.
- Primary key, foreign key, unique constraint và check constraint.
- Index, cột index, uniqueness và một số thuộc tính index.
- View và định nghĩa view.
- Sequence cùng các thuộc tính cấu hình được hỗ trợ.
- Function, procedure, trigger, synonym, type hoặc đối tượng đặc thù khác nếu snapshot generator hỗ trợ.

Một cách hình dung:

~~~text
Database tại thời điểm T
       |
       v
Liquibase đọc metadata qua JDBC/DBMS
       |
       v
Snapshot generator
       |
       v
Snapshot có cấu trúc
       |
       +--> Lưu artifact để truy vết
       |
       +--> Dùng làm bằng chứng kiểm kê
       |
       +--> Hỗ trợ phân tích diff / baseline
       |
       +--> Đối chiếu trước và sau release
~~~

Snapshot mô tả những gì công cụ có thể quan sát và biểu diễn; nó không nhất thiết bao phủ mọi thuộc tính nội bộ của DBMS. Một số object có thể không được hỗ trợ, bị filter, bị ẩn do quyền hoặc được chuẩn hóa theo cách riêng của Liquibase.

**Snapshot là ảnh chụp cấu trúc, không phải ảnh chụp toàn bộ trạng thái runtime.** Nó không thay thế việc kiểm tra dữ liệu, quyền thực tế, lock, replication, transaction đang chạy hay hành vi ứng dụng.

## 2. Phân biệt snapshot, backup, changelog và DATABASECHANGELOG

Các khái niệm này có liên quan nhưng giải quyết những vấn đề khác nhau:

| Khái niệm | Ghi lại điều gì? | Dùng để làm gì? | Có tự phục hồi database không? |
|---|---|---|---|
| **Snapshot schema** | Cấu trúc/object metadata có thể đọc được | Kiểm kê, so sánh, lưu dấu trạng thái | Không |
| **Backup / physical backup** | Dữ liệu và cấu trúc theo cơ chế backup của DBMS | Khôi phục database hoặc một phần | Có thể, theo quy trình restore |
| **PITR / transaction log backup** | Trạng thái có thể phục hồi tới thời điểm/mốc log | Phục hồi sau sự cố | Có, nếu cấu hình và log còn đủ |
| **Liquibase changelog** | Các thay đổi mong muốn được khai báo theo changeset | Version hóa migration | Không trực tiếp; có thể chứa rollback |
| **DATABASECHANGELOG** | Lịch sử changeset Liquibase ghi nhận đã xử lý | Theo dõi migration, checksum và thứ tự | Không |
| **Git tag / release artifact** | Phiên bản mã nguồn và changelog | Truy vết code/release | Không |

Ví dụ, snapshot cho biết bảng invoice có cột status VARCHAR(30), nhưng không chứa tất cả hàng invoice. Nếu một migration xóa nhầm dữ liệu, snapshot không thể khôi phục các hàng đã mất. Cần backup/PITR hoặc nguồn dữ liệu phục hồi phù hợp.

Ngược lại, backup có thể phục hồi database nhưng không nhất thiết cho biết thay đổi nào đến từ changeset nào. DATABASECHANGELOG giúp truy vết migration nhưng không chứng minh schema thực tế vẫn đúng nếu ai đó đã sửa database thủ công sau khi Liquibase chạy.

Một quy trình quản trị tốt kết hợp các bằng chứng này thay vì dùng một cơ chế thay thế mọi cơ chế khác.

## 3. Snapshot phục vụ những công việc nào?

### Lưu trạng thái trước và sau release

Chụp snapshot trước khi áp dụng migration tạo mốc trạng thái ban đầu. Sau khi update và postflight, chụp snapshot mới để có thể phân tích thay đổi.

### Phát hiện schema drift

So sánh trạng thái hiện tại với snapshot chuẩn đã được phê duyệt giúp nhận diện object bị thêm, xóa hoặc thay đổi ngoài changelog. Ví dụ, production xuất hiện một index do DBA tạo thủ công nhưng không có trong changelog.

### Thiết lập baseline

Khi tiếp quản database cũ, snapshot giúp kiểm kê trạng thái hiện hữu và đối chiếu với baseline changelog trước khi dùng changelog-sync. Nó cung cấp bằng chứng cấu trúc để nhóm quyết định changeset nào thực sự tương đương với trạng thái đã có.

### Hỗ trợ điều tra sự cố

Nếu migration gây ra lỗi, snapshot trước và sau có thể giúp nhóm hiểu object nào thay đổi. Tuy nhiên, cần ghép với log Liquibase, DATABASECHANGELOG, truy vấn dữ liệu, log ứng dụng và backup.

### Kiểm soát nhiều môi trường

Snapshot của development, staging và production có thể được lưu cùng release ID để đối chiếu. Nếu các môi trường có cấu hình khác nhau có chủ ý, phải ghi rõ phần khác biệt được chấp nhận thay vì kỳ vọng mọi snapshot giống từng byte.

## 4. Chụp snapshot bằng Liquibase

Liquibase có lệnh CLI **snapshot** để tạo biểu diễn snapshot từ database được cấu hình. Tùy phiên bản và cách phân phối, lệnh có thể hỗ trợ ghi kết quả ra file bằng tùy chọn output file.

Ví dụ minh họa:

~~~shell
liquibase --url="jdbc:postgresql://db-host:5432/customer_db" --username="snapshot_reader" snapshot --output-file="artifacts/customer-schema.json"
~~~

Ví dụ không chứa password thật. Trong CI/CD, cấp credentials qua secret store hoặc cơ chế bảo mật của runner. Tên tùy chọn, vị trí tham số và định dạng đầu ra cần xác nhận theo phiên bản Liquibase đang sử dụng bằng lệnh trợ giúp của CLI và tài liệu đi kèm. Không giả định mọi phiên bản có cùng options hoặc cùng định dạng snapshot.

Trước khi chụp:

1. Xác nhận đúng URL, database, schema và role.
2. Xác định phạm vi schema/object cần lưu.
3. Kiểm tra quyền đọc metadata.
4. Cố định phiên bản Liquibase và JDBC driver.
5. Xác nhận không có migration DDL khác đang thay đổi schema đồng thời.
6. Ghi nhận release/commit hoặc lý do tạo snapshot.

Sau khi chụp:

- Kiểm tra lệnh trả kết quả thành công.
- Kiểm tra artifact được tạo, không rỗng và có thể đọc/parse theo định dạng phiên bản.
- Xác nhận snapshot có đúng database/schema và phạm vi mong muốn.
- Kiểm tra một số object đại diện bằng metadata DBMS.
- Lưu artifact vào nơi quản lý phiên bản hoặc artifact storage có chính sách retention.
- Gắn provenance: thời điểm, môi trường, DBMS/version, Liquibase/JDBC version, commit và filter.

Nếu snapshot command của phiên bản đang dùng xuất kết quả trực tiếp ra console thay vì file, hãy dùng cơ chế output được hỗ trợ hoặc thu thập artifact bằng pipeline đã được review. Không tự tạo script xử lý snapshot mà chưa xác minh format.

## 5. Xác định đúng database và thời điểm chụp

Snapshot chỉ hữu ích khi biết rõ nó đến từ đâu và được tạo lúc nào. Trước khi chụp, xác nhận danh tính database bằng truy vấn DBMS.

Ví dụ PostgreSQL:

~~~sql
SELECT
    current_database() AS database_name,
    current_schema() AS current_schema,
    current_user AS connected_role,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port,
    current_setting('server_version') AS server_version;
~~~

Kết quả cần khớp target được phê duyệt. Nếu chạy qua proxy hoặc dịch vụ managed, địa chỉ server có thể không tương ứng trực tiếp hostname trong JDBC URL; đối chiếu thêm metadata hạ tầng.

Một snapshot nên có thời điểm chụp rõ ràng, tốt nhất chuẩn hóa UTC trong hệ thống lưu trữ. Cần phân biệt:

- **Thời điểm bắt đầu chụp**.
- **Thời điểm kết thúc chụp**.
- **Thời điểm release hoặc migration** mà snapshot đại diện.
- **Thời điểm artifact được lưu và xác minh**.

Việc đọc metadata có thể kéo dài và không phải mọi DBMS bảo đảm toàn bộ snapshot phản ánh một transaction snapshot nhất quán nếu schema thay đổi đồng thời. Vì vậy, hãy tránh chạy DDL song song trong lúc chụp; nếu cần độ nhất quán cao, phối hợp cửa sổ triển khai hoặc cơ chế snapshot/metadata lock phù hợp với DBMS.

Không ghi password, token hoặc chuỗi kết nối đầy đủ vào metadata snapshot hay tên artifact.

## 6. Snapshot không tự động chứa dữ liệu nghiệp vụ

Snapshot Liquibase chủ yếu phục vụ metadata schema. Không nên kỳ vọng nó chứa nội dung các hàng như:

- Tên, email hoặc địa chỉ khách hàng.
- Số tiền và trạng thái hóa đơn.
- Các giao dịch đã phát sinh.
- Giá trị từng bản ghi cần phục hồi.
- Toàn bộ trạng thái sequence runtime hoặc cache của database.

Một số metadata về sequence như start value, increment, min/max, cache hoặc cycle có thể được snapshot generator hỗ trợ, nhưng điều đó không có nghĩa snapshot lưu chính xác trạng thái cấp số hiện tại hay số cuối cùng đã được ứng dụng sử dụng. Hành vi tùy DBMS và snapshot generator.

Nếu cần kiểm tra dữ liệu, tạo các **data assertions** riêng, ví dụ số lượng bản ghi, số lượng NULL, số lượng orphan hoặc tổng kiểm tra nghiệp vụ. Không đưa dữ liệu nhạy cảm vào snapshot chỉ để làm bằng chứng; ưu tiên kết quả kiểm tra đã tổng hợp.

Nếu cần phục hồi dữ liệu, dùng backup/PITR hoặc cơ chế lưu dữ liệu phù hợp. Snapshot schema chỉ hỗ trợ phân tích cấu trúc trước/sau.

## 7. Quyền truy cập và độ đầy đủ của snapshot

Liquibase cần đọc metadata qua JDBC và các catalog/system view của DBMS. Tài khoản snapshot nên có quyền đọc cần thiết trên các schema/object thuộc phạm vi so sánh, nhưng không cần quyền DDL nếu chỉ chụp snapshot.

Các nhóm quyền cần kiểm tra:

- Quyền xem schema, bảng, cột và constraint.
- Quyền xem index, sequence và view.
- Quyền đọc metadata function/procedure/trigger nếu cần.
- Quyền xem object thuộc schema ngoài schema mặc định.
- Quyền catalog phù hợp với DBMS.
- Quyền truy cập metadata do extension hoặc tính năng riêng quản lý.

Một snapshot thiếu object có thể do:

1. Tài khoản không có quyền xem metadata.
2. Schema không nằm trong phạm vi được chọn.
3. Object type không được snapshot generator hỗ trợ.
4. Object bị exclude bởi filter.
5. DBMS/version biểu diễn metadata khác.
6. Object thực sự không tồn tại.

Không kết luận object không tồn tại chỉ vì nó không xuất hiện trong snapshot. Hãy xác minh quyền, schema và filter; nếu cần, dùng tài khoản kiểm tra được phê duyệt hoặc truy vấn metadata DBMS riêng.

**Không dùng tài khoản superuser mặc định cho mọi snapshot.** Một tài khoản đọc chuyên biệt giảm rủi ro và giúp chứng minh snapshot được tạo trong phạm vi quyền đã biết.

## 8. Chọn phạm vi schema và object

Một database có thể chứa schema nghiệp vụ, schema quản trị, bảng metadata Liquibase, object hệ thống và extension. Snapshot toàn bộ có thể tạo artifact lớn và nhiễu; snapshot quá hẹp lại bỏ sót khác biệt quan trọng.

Hãy lập danh sách scope:

| Nhóm object | Ví dụ | Quyết định |
|---|---|---|
| Schema nghiệp vụ | app, billing, customer | Thường đưa vào |
| Bảng và cột | invoice, customer, payment | Đưa vào |
| Constraint và index | PK, FK, unique, check, index | Đưa vào |
| View/function/trigger | logic được ứng dụng sở hữu | Đưa vào nếu được quản lý |
| Sequence/identity | nguồn cấp ID | Đưa vào nếu liên quan |
| Liquibase metadata | DATABASECHANGELOG, DATABASECHANGELOGLOCK | Thường loại khỏi snapshot schema nghiệp vụ |
| Object hệ thống | catalog nội bộ DBMS | Không đưa vào phạm vi ứng dụng |
| Extension/đối tượng bên ngoài | extension, object DBA quản lý | Theo ownership và chính sách |

Nếu dùng filter, lưu lại chính xác filter của lần chụp. Hai snapshot chỉ có thể so sánh có ý nghĩa khi phạm vi tương đương. Snapshot A có schema app và billing, còn snapshot B chỉ có app sẽ tạo khác biệt do phạm vi chứ không nhất thiết do drift.

Tùy phiên bản, Liquibase có các tham số chọn schema/catalog hoặc object type cho snapshot/diff. Hãy kiểm tra options hỗ trợ thực tế; không sao chép tham số giữa các phiên bản nếu chưa xác minh.

## 9. Đặt tên và lưu snapshot có thể truy vết

Tên artifact nên cho biết môi trường, release, thời điểm và phạm vi. Ví dụ:

~~~text
customer-prod-before-release-2.4.1.json
customer-prod-after-release-2.4.1.json
customer-staging-release-2.4.1.json
~~~

Không dùng tên chung như latest.json rồi ghi đè liên tục nếu cần truy vết lịch sử. Có thể dùng metadata bên ngoài artifact trong hệ thống lưu trữ:

~~~yaml
artifact:
  name: customer-prod-after-release-2.4.1
  environment: production
  database: customer_db
  schema_scope:
    - app
  captured_at_utc: "2026-11-19T10:30:00Z"
  release_id: "customer-service-2.4.1"
  changelog_commit: "<reviewed-commit>"
  dbms: "PostgreSQL"
  dbms_version: "16"
  liquibase_version: "<pinned-version>"
  jdbc_driver_version: "<pinned-version>"
  filters: "application schemas; exclude Liquibase metadata"
  purpose: "post-deployment schema evidence"
~~~

Đây là mẫu metadata minh họa, không phải cấu trúc JSON snapshot bắt buộc của Liquibase và không yêu cầu tạo file bổ sung trong bài thực hành. Tổ chức có thể lưu các trường này trong catalog artifact, pipeline metadata hoặc release record.

Nên bảo vệ artifact khỏi bị sửa sau khi nghiệm thu. Có thể dùng immutable artifact storage, versioning hoặc checksum SHA-256 được tạo bởi hệ thống lưu trữ/pipeline. Checksum file giúp phát hiện artifact bị thay đổi, nhưng không chứng minh snapshot ban đầu đã đầy đủ hoặc database nguồn đã đúng.

## 10. Snapshot trước và sau migration

Một quy trình release có thể chụp snapshot ở hai thời điểm:

~~~text
Release candidate
     |
     v
Preflight + kiểm tra target
     |
     v
SNAPSHOT BEFORE
     |
     v
Review SQL / Liquibase update
     |
     v
Postflight schema + data + app
     |
     v
SNAPSHOT AFTER
     |
     v
Compare / review / lưu evidence
~~~

Snapshot trước cung cấp trạng thái ban đầu. Snapshot sau cung cấp trạng thái kết quả. Khi so sánh, nhóm có thể kiểm tra migration có tạo đúng bảng/cột/constraint/index như dự kiến hay không và có xuất hiện object ngoài kế hoạch không.

Không nên kỳ vọng hai snapshot chỉ khác đúng những object trong changeset. Một số DBMS có thể thay đổi metadata tự động; migration có thể tạo sequence hoặc index phụ; người vận hành có thể thực hiện thay đổi hợp lệ khác trong cửa sổ triển khai. Mọi khác biệt phải được phân loại.

Một báo cáo sau release nên có:

- Những object được thêm.
- Những object bị xóa.
- Những object thay đổi định nghĩa.
- Những khác biệt không liên quan hoặc đã được phê duyệt.
- Những object không thể so sánh do giới hạn DBMS/permissions.
- Những kiểm tra dữ liệu/ứng dụng bổ sung cần thực hiện.

## 11. Dùng snapshot cùng diff và diff-changelog

Liquibase có thể so sánh database reference với target bằng lệnh **diff**. Trong quá trình này, công cụ lấy snapshot metadata từ hai phía để phân tích khác biệt.

Ví dụ:

~~~shell
liquibase --url="jdbc:postgresql://target-host:5432/customer_stage" --username="diff_reader" --reference-url="jdbc:postgresql://reference-host:5432/customer_reference" --reference-username="reference_reader" diff
~~~

**diff** tạo báo cáo khác biệt, không áp dụng DDL lên database. Kết quả phụ thuộc hướng reference/target: reference là trạng thái mong muốn, target là phía được đối chiếu.

Lệnh **diff-changelog** có thể tạo changelog mô tả những thay đổi cần thiết để đưa target gần với reference:

~~~shell
liquibase --url="jdbc:postgresql://target-host:5432/customer_stage" --username="diff_reader" --reference-url="jdbc:postgresql://reference-host:5432/customer_reference" --reference-username="reference_reader" diff-changelog
~~~

Changelog sinh ra chỉ là đề xuất kỹ thuật; cần lưu output riêng, review các thay đổi DROP/ALTER/constraint/index và thử trên database tương thích trước khi update.

Snapshot artifact là bằng chứng lưu trạng thái và có thể hỗ trợ quy trình đối chiếu. Cách dùng trực tiếp snapshot làm đầu vào/reference offline, nếu cần, phụ thuộc khả năng và định dạng được hỗ trợ bởi phiên bản Liquibase cụ thể. Không giả định một file JSON snapshot bất kỳ có thể được truyền vào mọi tùy chọn reference-url. Khi cần so sánh snapshot đã lưu, hãy sử dụng đúng cơ chế snapshot/offline được tài liệu hóa cho phiên bản đang dùng hoặc dựng database reference từ changelog đã được kiểm chứng.

## 12. Snapshot và generate-changelog khác nhau

Hai thao tác thường bị nhầm:

- **snapshot**: ghi lại biểu diễn trạng thái database hiện tại.
- **generate-changelog**: tạo các changeset mô tả cấu trúc database hiện tại để đưa vào quản lý Liquibase.

Ví dụ lệnh:

~~~shell
liquibase snapshot --output-file=artifacts/customer-schema.json
liquibase generate-changelog --changelog-file=db/changelog/baseline.yaml
~~~

Cú pháp output file và các option cần xác nhận theo phiên bản. Snapshot không phải changelog và không có nghĩa các changeset đã được áp dụng.

**generate-changelog** có thể tạo changelog từ database đang tồn tại, nhưng output cần review: tên object, thứ tự phụ thuộc, DBMS-specific SQL, rollback và những object nào nên được quản lý. Không chạy generate-changelog trên production rồi tự động áp dụng output ngược lại chính database đó.

Khi tiếp quản database hiện hữu, snapshot giúp kiểm kê và đối chiếu; generate-changelog giúp tạo đề xuất baseline; changelog-sync có thể ghi nhận changeset tương ứng sau khi đã chứng minh schema thực tế tương đương. Ba bước có mục đích riêng và cần kiểm soát.

## 13. Snapshot không phải bằng chứng duy nhất của DATABASECHANGELOG

Một release nên kết hợp snapshot với lịch sử Liquibase:

~~~sql
SELECT
    id,
    author,
    filename,
    exectype,
    md5sum,
    dateexecuted,
    orderexecuted
FROM public.databasechangelog
ORDER BY orderexecuted;
~~~

Truy vấn giả định metadata nằm trong schema public; điều chỉnh theo cấu hình thực tế.

DATABASECHANGELOG trả lời: changeset nào đã được Liquibase ghi nhận? Snapshot trả lời: những object schema nào được quan sát tại thời điểm chụp? Hai nguồn cần khớp về mặt logic nhưng không thay thế nhau.

Ví dụ, changeset tạo index có trong DATABASECHANGELOG nhưng index bị DBA xóa sau đó. Snapshot mới sẽ không có index, trong khi lịch sử vẫn ghi changeset đã chạy. Đây là dấu hiệu schema drift.

Ngược lại, snapshot cho thấy index tồn tại nhưng DATABASECHANGELOG không có changeset tạo index. Có thể index được tạo thủ công hoặc bằng công cụ khác. Nhóm cần quyết định baseline/reconcile thay vì chạy update mù.

Không sửa trực tiếp DATABASECHANGELOG để làm cho snapshot “khớp”. Hãy tìm nguyên nhân và tạo migration/điều chỉnh lịch sử theo quy trình chính thức đã được review.

## 14. Snapshot theo nhiều môi trường

Development, staging và production có thể khác nhau vì cấu hình, DBMS version, feature hoặc dữ liệu. Snapshot giúp so sánh nhưng không nên áp đặt rằng mọi khác biệt đều là lỗi.

Ví dụ:

| Môi trường | Vai trò | Snapshot nên lưu |
|---|---|---|
| Development | Nơi phát triển schema | Snapshot trước/sau thay đổi lớn hoặc release candidate |
| Integration test | Xác minh changelog từ database sạch | Snapshot trạng thái sau update nếu cần evidence |
| Staging | Mô phỏng production và nghiệm thu | Snapshot trước/sau release candidate |
| Production | Trạng thái thực tế đang phục vụ | Snapshot trước/sau migration quan trọng, theo chính sách vận hành |
| Tenant database | Trạng thái riêng từng tenant | Artifact gắn tenant/database identity và release |

Nếu production có object đặc thù được DBA quản lý, ghi rõ ownership và lý do khác biệt. Nếu tenant có schema riêng, snapshot phải gắn tenant/schema chính xác; không lưu một file tên chung khiến không biết nó đến từ tenant nào.

Cần dùng cùng phạm vi object và filter khi so sánh. Nếu staging và production khác DBMS hoặc version, một số khác biệt có thể là đặc tính nền tảng chứ không phải schema drift.

## 15. Snapshot và kiểm tra schema drift

**Schema drift** là sự khác biệt giữa trạng thái database thực tế và trạng thái được mong muốn/ghi nhận trong changelog hoặc snapshot chuẩn. Nguyên nhân có thể là:

- DBA thay đổi thủ công mà không tạo changeset.
- Migration chạy một phần.
- Hotfix đã triển khai nhưng chưa backport.
- Một môi trường bỏ lỡ changeset hoặc dùng filter khác.
- Ứng dụng/ORM tự tạo DDL ngoài Liquibase.
- Object bị xóa hoặc sửa bởi công cụ khác.
- Snapshot được tạo với quyền hoặc phạm vi không đầy đủ.

Một quy trình phát hiện drift:

1. Chọn snapshot chuẩn hoặc database reference đã được nghiệm thu.
2. Xác nhận target identity, DBMS/version và schema scope.
3. Chụp snapshot hiện tại hoặc chạy diff trên hai database.
4. Phân loại object missing, unexpected và changed.
5. Đối chiếu DATABASECHANGELOG/checksum và release commit.
6. Xác định thay đổi hợp lệ, hotfix, object ngoài ownership hoặc lỗi.
7. Tạo changeset forward-fix hoặc cập nhật quy trình baseline nếu cần.
8. Kiểm thử và lưu snapshot mới sau khi sửa.

Không nên tự động sinh và áp dụng diff-changelog cho mọi drift. Một bảng thừa có thể chứa dữ liệu cần giữ; một constraint khác có thể là quyết định nghiệp vụ; một index không có trong reference có thể được thêm để giải quyết tải production. Con người cần review ý nghĩa của khác biệt.

## 16. Snapshot và các object DBMS-specific

Snapshot generator không nhất thiết biểu diễn mọi đối tượng của mọi DBMS giống nhau. Cần kiểm tra những object quan trọng của hệ thống:

- **PostgreSQL:** sequence, extension, partition, policy/RLS, function, trigger, materialized view và index method.
- **Oracle:** package, synonym, sequence, materialized view, trigger và các kiểu dữ liệu riêng.
- **SQL Server:** schema-bound object, stored procedure, trigger, sequence, identity và index options.
- **MySQL:** engine/table options, trigger, routine, event và collation.
- **SQLite:** giới hạn về object type và cách biểu diễn constraint/index.

Danh sách này là ví dụ những khác biệt có thể cần xem xét; mức hỗ trợ snapshot cụ thể phụ thuộc Liquibase version, DBMS, JDBC driver và extension. Nếu một object không xuất hiện, xác minh quyền và khả năng hỗ trợ trước khi kết luận nó không tồn tại.

Đối với object quan trọng nhưng không được snapshot đầy đủ, bổ sung truy vấn metadata DBMS hoặc kiểm tra chuyên biệt. Ghi rõ phần nào nằm ngoài phạm vi snapshot để báo cáo không tạo cảm giác đã kiểm kê toàn bộ database.

## 17. Snapshot và sequence: tránh nhầm cấu hình với runtime state

Sequence thường cấp ID cho bảng. Snapshot có thể biểu diễn một số thuộc tính định nghĩa như increment, min/max, cycle hoặc cache tùy DBMS/generator, nhưng không nên mặc định nó lưu trạng thái runtime đủ để phục hồi sequence.

Với PostgreSQL, có thể kiểm tra cấu hình qua metadata:

~~~sql
SELECT
    schemaname,
    sequencename,
    start_value,
    min_value,
    max_value,
    increment_by,
    cycle,
    cache_size
FROM pg_sequences
WHERE schemaname = 'public'
  AND sequencename = 'invoice_id_seq';
~~~

Nếu cần kiểm tra trạng thái cấp số và dữ liệu hiện tại, phải dùng quy trình riêng có hiểu biết về cache, concurrent writers và ngữ nghĩa nextval/setval. Không gọi nextval chỉ để “kiểm tra” vì nó tiêu thụ một giá trị; không dùng snapshot để đặt lại sequence trong production.

## 18. Bảo mật và retention của snapshot

Snapshot có thể chứa tên database, schema, bảng, cột, tên role, định nghĩa view/function hoặc thông tin cấu trúc nhạy cảm. Dù không chứa row data, artifact vẫn có thể tiết lộ kiến trúc nội bộ.

Chính sách lưu trữ nên quy định:

- Ai được phép tạo snapshot production.
- Ai được đọc hoặc tải artifact.
- Artifact lưu trong hệ thống nào, region nào và thời hạn bao lâu.
- Có cần mã hóa khi truyền và khi lưu không.
- Có cần immutable/versioned retention để phục vụ audit không.
- Cách xóa artifact hết hạn theo chính sách bảo mật.
- Cách loại credentials và thông tin kết nối khỏi metadata/log.

Không commit snapshot production vào repository công khai hoặc chia sẻ rộng nếu chưa đánh giá nội dung. Dùng artifact storage với quyền truy cập phù hợp và gắn release ID để dễ truy vết.

Nếu tạo checksum SHA-256 cho file snapshot, lưu checksum trong metadata của artifact hoặc hệ thống provenance. Checksum chứng minh file hiện tại giống file đã được băm, không chứng minh nguồn snapshot là database đúng hoặc quá trình chụp đầy đủ.

## 19. Snapshot trước và sau migration trong CI/CD

Một pipeline có thể tạo snapshot trước và sau migration quan trọng:

~~~text
Build changelog artifact
        |
        v
Resolve database target + schema scope
        |
        v
Preflight identity / permissions / history
        |
        v
Snapshot BEFORE
        |
        v
Review update-sql + approval
        |
        v
Liquibase update
        |
        v
Postflight DATABASECHANGELOG + schema + data
        |
        v
Snapshot AFTER
        |
        v
Compare expected changes / review drift
        |
        v
Store evidence with release ID
~~~

Snapshot trước và sau nên được tạo bởi cùng phiên bản Liquibase/JDBC, với cùng scope/filter, nếu mục tiêu là so sánh có ý nghĩa. Nếu thay đổi DBMS/JDBC giữa hai lần, cần ghi rõ vì output có thể khác do cách biểu diễn metadata.

Các gate nên dừng release khi:

- Không xác định được đúng database/schema.
- Snapshot không đầy đủ hoặc không đọc được.
- Changelog/SQL chưa được review.
- Postflight không đạt.
- Diff có thay đổi phá hủy ngoài kế hoạch.
- Không thể đối chiếu artifact với release commit.

Không cần chụp snapshot sau mọi changeset nhỏ nếu chi phí không hợp lý. Có thể chọn theo release, theo mức độ rủi ro hoặc trước/sau những migration phá hủy. Quan trọng là chính sách rõ ràng và nhất quán.

## 20. Runbook xử lý khi snapshot khác trạng thái mong đợi

Khi snapshot mới không giống snapshot chuẩn:

1. **Xác nhận nguồn:** database, schema, DBMS/version, thời điểm và role có đúng không?
2. **Xác nhận scope:** schema/filter/object type có giống lần snapshot chuẩn không?
3. **Kiểm tra độ đầy đủ:** có thiếu quyền metadata hoặc object type không được hỗ trợ không?
4. **Đối chiếu lịch sử:** changeset nào đã chạy, checksum có bất thường không, có hotfix chưa backport không?
5. **Phân loại drift:** object thiếu, object thừa, định nghĩa khác, khác biệt có chủ ý hay lỗi snapshot.
6. **Xác định owner:** object thuộc ứng dụng, DBA, extension hay dịch vụ khác?
7. **Chọn hành động:** tạo forward-fix, cập nhật baseline được review, giữ khác biệt có lý do hoặc khôi phục theo backup nếu có sự cố.
8. **Chụp snapshot sau xử lý:** xác minh trạng thái mới và lưu cùng release evidence.

Không chạy update chỉ để làm diff biến mất. Một changelog tự sinh có thể drop object hoặc thu hẹp kiểu dữ liệu; mọi thay đổi phải được đánh giá về dữ liệu, dependency, hiệu năng và tương thích ứng dụng.

## 21. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Snapshot thiếu bảng | Sai schema scope hoặc thiếu quyền metadata | Kiểm tra target identity, schema và quyền |
| Snapshot có nhiều object lạ | Đưa schema hệ thống/metadata vào scope | Xác định ownership và filter rõ ràng |
| Snapshot trước/sau khác hàng loạt | Liquibase/JDBC/DBMS version hoặc filter thay đổi | Chuẩn hóa phiên bản và phạm vi |
| Artifact không đọc được | Output bị cắt, lệnh thất bại hoặc format khác | Kiểm tra exit code, log, format theo version |
| Diff báo object thừa | Reference/target đảo chiều hoặc object ngoài ownership | Xác minh hướng và quyền sở hữu |
| Snapshot khớp nhưng app lỗi | Snapshot không kiểm tra dữ liệu/runtime/permissions đầy đủ | Bổ sung smoke test, data assertions và privilege checks |
| DATABASECHANGELOG nói đã chạy nhưng object thiếu | Drift sau migration hoặc partial failure | Kiểm tra schema thật và log, tạo forward-fix |
| Snapshot không khôi phục được dữ liệu | Nhầm snapshot với backup | Dùng backup/PITR hoặc nguồn phục hồi dữ liệu |
| Sequence tiếp tục cấp ID không mong muốn | Snapshot không đại diện đầy đủ runtime sequence state | Kiểm tra sequence bằng metadata và quy trình DBMS riêng |

## 22. Quy trình thực hành tổng hợp

Giả sử ứng dụng billing chuẩn bị phát hành release 2.4.1 trên PostgreSQL:

**Bước 1 — Chuẩn bị:** xác định commit changelog, Liquibase/JDBC version, database/schema đích và tài khoản snapshot đọc metadata.

**Bước 2 — Chụp snapshot trước:** chạy lệnh snapshot theo cú pháp được xác minh cho phiên bản CLI; lưu artifact với tên gắn release và môi trường.

**Bước 3 — Kiểm tra artifact:** xác nhận file không rỗng, đọc được, chứa các object trọng yếu như invoice, customer, FK và index; ghi provenance và filter.

**Bước 4 — Review migration:** chạy validate, status và update-sql; xem các changeset có tác động phá hủy hoặc cần lock dài.

**Bước 5 — Update trên database test:** chạy migration trên bản sao hoặc database tương thích, postflight dữ liệu và ứng dụng.

**Bước 6 — Phê duyệt production:** xác nhận backup/PITR, maintenance window, quyền và owner migration.

**Bước 7 — Chạy update:** theo dõi log, DATABASECHANGELOGLOCK, thời gian và lỗi.

**Bước 8 — Chụp snapshot sau:** chỉ sau khi update và postflight hoàn tất, chụp snapshot mới với cùng scope/filter.

**Bước 9 — Đối chiếu:** phân loại object được thêm/xóa/thay đổi; xác minh đúng những thay đổi đã review, không có drift bất ngờ.

**Bước 10 — Lưu bằng chứng:** gắn snapshot trước/sau, release ID, commit, DBMS/version, Liquibase/JDBC version, log, SQL review và kết quả postflight vào release record.

Nếu bước update thất bại, không chụp snapshot sau rồi kết luận release đã hoàn tất. Trước tiên cần xác minh trạng thái thật, xử lý partial failure và quyết định retry, rollback hoặc forward-fix.

## 23. Checklist tạo và lưu snapshot

- [ ] Xác nhận đúng database, schema, DBMS/version và tài khoản kết nối.
- [ ] Xác định mục đích: baseline, pre-release, post-release, drift audit hay điều tra.
- [ ] Cố định phiên bản Liquibase/JDBC và cú pháp snapshot command.
- [ ] Xác định schema/object scope và filter.
- [ ] Đảm bảo quyền metadata đủ nhưng không cấp DDL không cần thiết.
- [ ] Tránh DDL đồng thời làm snapshot thiếu nhất quán.
- [ ] Kiểm tra artifact được tạo, không rỗng và đọc được.
- [ ] Gắn provenance: thời điểm UTC, môi trường, release/commit, DBMS/version và filter.
- [ ] Lưu artifact ở nơi có quyền truy cập và retention phù hợp.
- [ ] Nếu cần integrity check, lưu checksum artifact và nguồn provenance.
- [ ] Phân biệt snapshot với backup, changelog và DATABASECHANGELOG.
- [ ] Không dùng snapshot làm bằng chứng thay thế data assertions hoặc application tests.
- [ ] So sánh snapshot trước/sau với cùng scope và công cụ tương thích.
- [ ] Review mọi khác biệt, nhất là DROP/ALTER/constraint/index.
- [ ] Chụp và lưu snapshot sau chỉ khi trạng thái sau migration đã được xác minh.

Với **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, snapshot là một bằng chứng cấu trúc có giá trị khi được gắn với đúng database, thời điểm, phiên bản công cụ và phạm vi object. Hãy dùng snapshot để kiểm kê, đối chiếu và phát hiện drift; kết hợp với changelog, DATABASECHANGELOG, kiểm tra dữ liệu, smoke test và backup/PITR để có cái nhìn đầy đủ. Khi snapshot trước/sau được tạo nhất quán và lưu cùng release evidence, nhóm có thể giải thích database đã thay đổi như thế nào, thay đổi nào được mong đợi và những khác biệt nào cần điều tra trước khi triển khai tiếp.
