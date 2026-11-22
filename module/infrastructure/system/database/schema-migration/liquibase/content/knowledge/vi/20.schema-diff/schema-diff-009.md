# Phát hiện schema drift do thay đổi ngoài quy trình

Một database production có thể vẫn chạy bình thường dù cấu trúc của nó đã khác với changelog trong repository. DBA có thể thêm index để xử lý sự cố hiệu năng, một hotfix có thể đổi kiểu cột trực tiếp, hoặc một script vận hành có thể tạo trigger mà không đi qua pipeline Liquibase. Những thay đổi này đôi khi cần thiết trong tình huống khẩn cấp, nhưng nếu không được ghi nhận và quản lý lại, các môi trường sẽ dần có cấu trúc khác nhau. Đây là **schema drift**: schema thực tế lệch khỏi trạng thái được quản lý hoặc được chấp nhận làm chuẩn.

Bài học thuộc chương **So sánh lược đồ** của module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`. Module hướng tới quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này tập trung vào cách nhận diện drift do thay đổi ngoài quy trình, dùng Liquibase để so sánh schema, xác minh nguyên nhân và đưa thay đổi hợp lệ trở lại lịch sử migration.

## 1. Schema drift là gì?

Schema drift xảy ra khi cấu trúc database thật khác với cấu trúc mà nhóm kỳ vọng từ changelog đã phát hành, baseline đã duyệt hoặc một database tham chiếu đáng tin cậy.

Một vài ví dụ:

- Changelog tạo cột `customer.email VARCHAR(80)`, nhưng DBA đã đổi trực tiếp thành `VARCHAR(255)`.
- Một index được thêm thủ công trên production nhưng không có changeset tương ứng.
- Một foreign key bị xóa để xử lý sự cố dữ liệu rồi không được tạo lại.
- Một trigger hoặc stored procedure được chỉnh body trực tiếp, khiến behavior khác với staging.
- Một cột bị xóa ngoài Liquibase, trong khi `DATABASECHANGELOG` vẫn ghi changeset tạo cột đã `EXECUTED`.
- Một database được restore từ bản backup cũ, làm mất các migration mới nhất nhưng history ở hệ thống giám sát không được cập nhật.

Schema drift không nhất thiết là thay đổi sai. Một số thay đổi thủ công có thể là hotfix hợp lệ. Vấn đề nằm ở chỗ **thay đổi chưa được kiểm chứng, chưa được ghi vào nguồn quản lý và chưa được đồng bộ giữa các môi trường**.

### 1.1. Ba trạng thái cần phân biệt

| Khái niệm | Mô tả | Ví dụ |
|---|---|---|
| **Desired schema** | Cấu trúc được nhóm chấp nhận làm mục tiêu, được mô tả qua changelog/baseline hoặc reference đã kiểm soát. | Database mới dựng từ changelog phát hành. |
| **Actual schema** | Cấu trúc đang tồn tại thật trên database cần kiểm tra. | Production tại thời điểm kiểm kê. |
| **Recorded migration history** | Những changeset Liquibase đã ghi nhận trong `DATABASECHANGELOG`. | `001`, `002` đã `EXECUTED`. |

Ba trạng thái này có thể không đồng nhất. Ví dụ history ghi `002` đã chạy, nhưng DBA xóa cột do `002` tạo. Liquibase vẫn có thể xem `002` đã hoàn tất; lệnh `status` không tự phát hiện cột bị xóa. Cần so sánh schema thật với một nguồn tham chiếu.

### 1.2. Drift khác với pending changeset

- **Pending changeset:** một changeset thuộc phạm vi changelog hiện tại chưa được ghi nhận trong lịch sử database.
- **Schema drift:** cấu trúc thực tế lệch khỏi cấu trúc tham chiếu, kể cả khi tất cả changeset đều đã được ghi nhận.

Do đó, `status` báo không có pending **không chứng minh schema không drift**. Ngược lại, có pending không nhất thiết là drift: có thể đó là thay đổi mới đang chờ release đúng kế hoạch.

## 2. Những nguồn tạo ra drift

| Nguồn thay đổi ngoài quy trình | Biểu hiện | Rủi ro |
|---|---|---|
| Hotfix trực tiếp từ DBA | Thêm index, đổi cột, xóa constraint. | Changelog và production khác nhau. |
| SQL chạy thủ công | Script được chạy từ console nhưng không commit vào repository. | Không truy vết được người thực hiện, thời điểm và lý do. |
| ORM tự cập nhật schema | Hibernate hoặc framework khác tự thêm/sửa cột. | Cấu trúc thay đổi ngoài changeset đã review. |
| Tool quản trị hoặc extension | Tạo trigger, sequence, view, extension. | Một số object không có trong baseline. |
| Restore/clone database | Khôi phục schema từ snapshot cũ hoặc từ môi trường khác. | Mất migration hoặc mang theo object không mong muốn. |
| Khác biệt cấu hình DBMS | Collation, default schema, extension, version hoặc kiểu native khác. | Diff báo khác dù không phải hotfix. |
| Migration lỗi giữa chừng | DDL tự commit hoặc changeset không transaction để lại object. | History chưa ghi thành công nhưng schema đã đổi một phần. |
| Thay đổi từ ứng dụng khác dùng chung database | Một service khác sở hữu một phần schema. | Dễ nhận nhầm object hợp lệ là drift của service hiện tại. |

Không phải mọi khác biệt đều là vi phạm. Trước khi sửa, cần xác định **quyền sở hữu object**: service Liquibase hiện tại, DBA, một ứng dụng khác hay nền tảng database. Một database dùng chung có thể có nhiều vùng schema với chủ sở hữu khác nhau.

## 3. Vì sao checksum và status không phát hiện mọi schema drift?

Liquibase sử dụng `DATABASECHANGELOG` để theo dõi changeset đã xử lý và checksum để phát hiện một số thay đổi trong định nghĩa changeset. Các cơ chế này không liên tục đọc toàn bộ schema thật để so sánh với changelog.

Ví dụ:

1. Changeset `001` tạo bảng `customer_record` và được ghi `EXECUTED`.
2. Một DBA chạy `ALTER TABLE customer_record DROP COLUMN email` trực tiếp.
3. Không có changeset nào mới được thêm vào `DATABASECHANGELOG`.
4. Changelog trong Git vẫn giữ nguyên, checksum `001` vẫn khớp với nội dung đã chạy.
5. `status` có thể không liệt kê `001` là pending vì history vẫn ghi nó đã thực thi.

Trong tình huống này:

- **Checksum** cho biết định nghĩa changeset có bị thay đổi theo cách Liquibase phát hiện hay không.
- **History** cho biết Liquibase đã ghi nhận việc xử lý changeset.
- **Schema comparison** mới cho biết object thật đang khác reference như thế nào.

Không dùng `clearCheckSums` để chữa schema drift. Lệnh này xử lý checksum đã lưu, không khôi phục cột bị xóa, index bị thiếu hoặc trigger bị sửa.

## 4. Chọn nguồn tham chiếu đáng tin cậy

Để phát hiện drift, cần so sánh actual schema với một **reference schema**. Chất lượng kết quả phụ thuộc trực tiếp vào việc chọn đúng reference.

### 4.1. Các nguồn reference thường dùng

| Nguồn | Khi phù hợp | Rủi ro |
|---|---|---|
| Database mới được dựng từ changelog đã phát hành | Muốn biết schema mà chính changelog hiện tại tạo ra. | Có thể thiếu khác biệt hợp lệ theo DBMS/version hoặc dữ liệu cấu hình. |
| Database staging đã được kiểm thử và phê duyệt | Muốn so sánh production với một môi trường chuẩn. | Staging có thể tự drift hoặc chưa chứa hotfix được chấp nhận. |
| Snapshot/reference database được quản lý riêng | Muốn kiểm soát mốc schema và tái sử dụng trong pipeline. | Snapshot có thể lỗi thời so với release mới. |
| Changelog/baseline được review và dựng thành database tạm | Muốn reference có thể tái tạo từ version control. | Cần cùng DBMS, version, extension và cấu hình quan trọng. |

**Không mặc định development là reference tốt.** Developer có thể đã chạy SQL thử, ORM có thể tự cập nhật schema hoặc dữ liệu/object đặc thù của môi trường làm cho development khác production.

### 4.2. Reference phải cùng ngữ cảnh kỹ thuật

Trước khi diff, xác minh:

- Cùng loại DBMS và phiên bản tương thích.
- Cùng schema/catalog mục tiêu, hoặc có mapping schema rõ ràng.
- Cùng extension, collation, encoding và những feature ảnh hưởng metadata.
- Cùng phiên bản Liquibase, JDBC driver và extension liên quan.
- Tài khoản có quyền đọc metadata cần thiết trên cả reference lẫn target.
- Phạm vi object được so sánh phù hợp với quyền sở hữu của ứng dụng.

Nếu reference là PostgreSQL nhưng target là Oracle, không nên xem mọi khác biệt kiểu vật lý là drift. Khi cần hỗ trợ nhiều DBMS, phải so sánh theo **hợp đồng schema và ý nghĩa nghiệp vụ**, không chỉ chuỗi tên kiểu.

## 5. Dùng Liquibase diff để phát hiện khác biệt

Liquibase có các lệnh so sánh database/reference như `diff` và tạo changelog từ khác biệt như `diff-changelog`. Ý nghĩa hướng so sánh rất quan trọng:

- **Reference database:** trạng thái được xem là chuẩn.
- **Target database:** database đang được kiểm tra hoặc database có thể được cập nhật.
- `diff`: báo cáo những khác biệt giữa reference và target.
- `diff-changelog`: tạo changelog biểu diễn các khác biệt theo hướng có thể dùng để đưa target về gần reference, tùy loại object và khả năng hỗ trợ.

Ví dụ CLI khái quát:

~~~bash
liquibase \
  --reference-url=jdbc:postgresql://localhost:5432/customer_reference \
  --reference-username=reference_reader \
  --url=jdbc:postgresql://localhost:5432/customer_production \
  --username=drift_reader \
  diff
~~~

Ví dụ minh họa dùng reference đã được phê duyệt và target là production. Tài khoản chỉ đọc là lựa chọn phù hợp cho bước phát hiện drift nếu quyền metadata đủ. Credential phải được lấy từ secret/config an toàn, không ghi mật khẩu vào lệnh hoặc log.

Tên tham số, cách đặt cấu hình reference và cú pháp CLI có thể khác giữa các phiên bản. Một số bản có cách gọi hoặc tên command cũ khác. Hãy xem `liquibase diff --help` của bản đang khóa trong dự án trước khi đưa vào pipeline.

### 5.1. Đọc kết quả diff

Một báo cáo diff có thể nhóm khác biệt theo loại object:

| Kết quả khái quát | Ví dụ | Câu hỏi điều tra |
|---|---|---|
| Object chỉ có ở reference | Reference có index `idx_customer_email`, target không có. | Index bị xóa thủ công hay target chưa nhận migration? |
| Object chỉ có ở target | Target có bảng `legacy_import_tmp`, reference không có. | Đây là object tạm, object của service khác hay hotfix hợp lệ? |
| Object tồn tại ở cả hai nhưng khác thuộc tính | Cột `email` có độ dài khác. | Khác biệt có ảnh hưởng dữ liệu hoặc ứng dụng không? |
| Định nghĩa object khác | View/function/trigger có body khác. | Logic nào là phiên bản được phê duyệt? |
| Không thể so sánh hoặc không đọc được | User thiếu quyền hoặc DBMS không hỗ trợ snapshot object. | Phạm vi diff có bị thiếu dữ liệu không? |

Tên nhóm và cách trình bày chính xác phụ thuộc loại object, DBMS và phiên bản Liquibase. Không kết luận “không có drift” nếu log cho biết một phần object không được snapshot hoặc không thể so sánh.

### 5.2. Hướng diff không phải hướng tự động sửa

Nếu reference là schema chuẩn và target là production, một object chỉ có ở target có thể được thể hiện như object cần loại bỏ để target khớp reference. Nhưng object đó có thể chứa dữ liệu thật hoặc thuộc service khác. **Báo cáo diff không có quyền quyết định object nào được xóa.**

Trước khi dùng `diff-changelog`, phải xác nhận reference và target được đặt đúng chiều. Nếu đảo ngược hai URL, changeset sinh ra có thể mô tả hướng thay đổi ngược lại.

## 6. Ví dụ: phát hiện cột bị đổi thủ công

Giả sử changelog đã phát hành tạo bảng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: db-team
      changes:
        - createTable:
            tableName: customer_record
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: VARCHAR(80)
                  constraints:
                    nullable: false
~~~

Sau đó, một DBA mở rộng độ dài cột trên production bằng SQL trực tiếp:

~~~sql
ALTER TABLE customer_record
ALTER COLUMN email TYPE VARCHAR(255);
~~~

Đoạn SQL trên là cú pháp PostgreSQL. Các DBMS khác có cú pháp đổi kiểu riêng. Changelog và `DATABASECHANGELOG` vẫn ghi nhận trạng thái cũ, còn actual schema có `VARCHAR(255)`.

### 6.1. So sánh trên database tham chiếu

Tạo hoặc chọn một reference PostgreSQL được dựng từ changelog đã phát hành (cột `email` là `VARCHAR(80)`), sau đó diff với production. Nếu cả hai database có cùng schema và quyền metadata phù hợp, báo cáo có thể chỉ ra khác biệt về độ dài cột.

Diff cho biết **có khác biệt**, nhưng chưa trả lời:

- DBA thay đổi vì ticket hotfix nào?
- Dữ liệu production có email dài hơn 80 không?
- 255 có phải yêu cầu mới đã được phê duyệt không?
- Staging và các tenant khác đang ở kiểu nào?
- Ứng dụng hiện tại có giả định độ dài 80 ở validation hoặc API không?

Đây là bước cần điều tra nghiệp vụ và vận hành.

### 6.2. Đưa hotfix hợp lệ vào lịch sử

Nếu thay đổi lên 255 là yêu cầu hợp lệ, hãy giữ changeset `001` bất biến và tạo changeset mới, ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-expand-customer-email
      author: db-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: customer_record
        - columnExists:
            tableName: customer_record
            columnName: email
      changes:
        - modifyDataType:
            tableName: customer_record
            columnName: email
            newDataType: VARCHAR(255)
~~~

Đây là changeset ví dụ cho trạng thái cũ có cột email và yêu cầu chuẩn hóa thành độ dài 255. Nếu production đã có 255 do hotfix, changeset mới khi chạy ở production có thể không cần thay đổi vật lý; tuy nhiên Liquibase vẫn cần ghi nhận lịch sử theo một quy trình rõ ràng. Không nên mặc định `modifyDataType` lặp lại sẽ luôn vô hại trên mọi DBMS.

Trên staging hoặc database mới còn `VARCHAR(80)`, changeset `002` sẽ thực hiện nâng kiểu. Sau khi triển khai đồng nhất, changelog trở thành nguồn sự thật mới. Cần kiểm tra cả ứng dụng, dữ liệu, SQL preview và rollback (thu hẹp về 80 có thể mất dữ liệu).

### 6.3. Khi hotfix không được chấp nhận

Nếu thay đổi 255 là ngoài ý muốn và không có dữ liệu dài hơn 80, nhóm có thể lập kế hoạch khôi phục schema theo migration mới hoặc quy trình remediation được duyệt. Trước khi thu hẹp, phải kiểm tra giá trị dài nhất, hành vi làm tròn/cắt dữ liệu và ứng dụng đang ghi. Không chạy lệnh thu hẹp chỉ để làm diff hết khác biệt.

## 7. Tạo diff-changelog và review trước khi dùng

Ví dụ CLI khái quát:

~~~bash
liquibase \
  --reference-url=jdbc:postgresql://localhost:5432/customer_reference \
  --url=jdbc:postgresql://localhost:5432/customer_test \
  diff-changelog \
  --changelog-file=build/drift-candidate.yaml
~~~

`diff-changelog` có thể sinh ra changelog chứa thay đổi để làm target tiến gần reference. Output này là **ứng viên cần review**, không phải bản vá tự động được phép triển khai.

Review từng changeset sinh ra:

- Hướng thay đổi có đúng không? Reference và target có bị đảo không?
- Có tạo/drop table, column, index hoặc constraint không mong muốn?
- Có làm mất dữ liệu khi drop/thu hẹp cột không?
- Có thay đổi object ngoài phạm vi service không?
- Có bỏ sót trigger, routine, quyền hoặc extension không?
- SQL có portable và phù hợp DBMS đích không?
- Thứ tự dependency có đúng không?
- Rollback có khả thi và có bảo toàn dữ liệu không?

Không đưa output diff-changelog trực tiếp vào production chỉ vì lệnh tạo thành công. Cần review như một pull request migration bình thường, thử trên database có cấu trúc và dữ liệu đại diện, chạy `validate` và xem SQL preview.

## 8. Lọc phạm vi so sánh để giảm nhiễu

Một database có thể chứa object hệ thống, object của extension, schema dùng chung hoặc object do service khác sở hữu. Nếu so sánh mọi thứ mà không xác định phạm vi, diff có thể trả về nhiều khác biệt không liên quan.

Các yếu tố cần kiểm soát:

| Bộ lọc/phạm vi | Mục đích | Cần cẩn thận |
|---|---|---|
| Schema/catalog | Giới hạn schema thuộc ứng dụng. | Default schema của user có thể khác giữa môi trường. |
| Include/exclude object | Chọn bảng, view, sequence, index hoặc loại object phù hợp. | Loại trừ quá rộng có thể bỏ sót drift quan trọng. |
| Object owner | Chỉ so sánh object do service sở hữu. | Một object dùng chung có thể có nhiều owner nghiệp vụ. |
| DBMS feature | Xác định extension, type hoặc tính năng native. | Khác biệt theo phiên bản không phải lúc nào cũng là thay đổi thủ công. |
| Liquibase metadata | Tránh coi bảng history/lock là schema nghiệp vụ. | Không loại metadata nếu mục tiêu kiểm tra là chính các bảng quản trị đó. |

Liquibase có các tùy chọn về schema, catalog, loại object và include/exclude tùy phiên bản. Cú pháp chính xác cần kiểm tra qua help của command đang dùng; không áp dụng một danh sách filter chung cho mọi bản hoặc extension.

### 8.1. Tránh nhiễu do tên schema

Ví dụ reference dùng schema `app` nhưng target dùng `customer_prod`. Diff có thể báo nhiều object thiếu/thừa nếu không cấu hình schema tương ứng hoặc mapping phù hợp. Trước khi điều tra từng bảng, hãy xác minh:

- Reference schema và target schema.
- Default schema và current schema của user.
- Object có cùng tên nhưng nằm ở schema khác không.
- Chỉ mục hoặc constraint có tên được tự sinh khác nhau không.

Nếu khác biệt chỉ do tên/schema được cấu hình có chủ đích, tài liệu hóa mapping thay vì tạo changeset drop/create để ép hai database giống tên.

## 9. Những giới hạn của schema diff

Diff là công cụ metadata, không phải công cụ hiểu toàn bộ hành vi ứng dụng.

### 9.1. Không đồng nghĩa data diff

Hai database có cùng bảng, cột và index nhưng dữ liệu khác nhau:

- Một môi trường có 100 triệu hàng, môi trường khác có 10 hàng.
- Một bảng có duplicate hoặc orphan records.
- Dữ liệu tham chiếu bị thiếu.
- Một lần backfill chỉ hoàn thành một phần.

Schema diff không tự chứng minh nội dung dữ liệu giống nhau. Muốn kiểm tra data drift, cần truy vấn kiểm tra bất biến, count, checksum theo lô, đối chiếu nguồn dữ liệu hoặc công cụ data comparison riêng. Không tải toàn bộ dữ liệu production vào máy phát triển chỉ để diff schema.

### 9.2. Không phải mọi object đều được snapshot đầy đủ

Khả năng so sánh phụ thuộc DBMS, quyền user, Liquibase Core, extension và loại object. Các khác biệt dễ bị bỏ qua hoặc biểu diễn không đầy đủ gồm:

- Body procedure/function hoặc trigger có cú pháp native phức tạp.
- Quyền, role, ownership và default privileges.
- Extension, partition, synonym, policy hoặc loại object riêng DBMS.
- Expression index, partial index, operator class hoặc storage parameters.
- Materialized view và trạng thái refresh.
- Collation, charset, tablespace hoặc cấu hình instance.

Hãy xem cảnh báo snapshot và log command. Nếu object quan trọng không được đọc hoặc so sánh, **không được kết luận database không drift**.

### 9.3. Khác biệt do phiên bản và normalization

Hai DBMS cùng loại nhưng khác phiên bản có thể biểu diễn metadata/default expression khác nhau. Liquibase có thể chuẩn hóa một số thuộc tính, nhưng không đảm bảo loại bỏ mọi khác biệt. Tên constraint/index tự sinh, thứ tự metadata hoặc cách render type cũng có thể tạo kết quả cần diễn giải.

Đối chiếu trên cùng DBMS/version là cách giảm nhiễu. Nếu không thể, hãy định nghĩa rõ những khác biệt được chấp nhận và kiểm tra ý nghĩa thay vì chỉ so chuỗi output.

## 10. Phát hiện drift theo lịch trong CI/CD

Drift có thể xuất hiện nhiều tháng sau release. Một lần diff thủ công không đủ nếu không có quy trình định kỳ và owner xử lý.

Luồng kiểm tra khuyến nghị:

~~~mermaid
flowchart TD
    A[Chọn changelog và reference đã phê duyệt] --> B[Xác minh DBMS, version, schema và quyền]
    B --> C[Snapshot/diff reference với target]
    C --> D{Có khác biệt?}
    D -->|Không| E[Lưu kết quả và thời điểm kiểm tra]
    D -->|Có| F[Phân loại object và owner]
    F --> G{Hotfix hợp lệ?}
    G -->|Có| H[Viết changeset mới để ghi nhận]
    G -->|Không| I[Điều tra và lập remediation]
    H --> J[Review, validate, SQL preview và test]
    I --> J
    J --> K[Triển khai có kiểm soát]
    K --> L[Diff lại và xác minh schema/data]
    L --> E
~~~

### 10.1. Những thời điểm nên chạy

- Sau khi có hotfix trực tiếp từ DBA.
- Trước một đợt release có DDL quan trọng.
- Sau khi restore/clone/refresh database.
- Theo lịch định kỳ với production hoặc database có yêu cầu kiểm toán.
- Sau khi chuyển giao database từ nhóm khác hoặc đưa legacy vào Liquibase.

Tần suất phải dựa trên tốc độ thay đổi, rủi ro và chi phí snapshot. Với database rất lớn, schema snapshot thường nhẹ hơn data diff, nhưng vẫn cần đánh giá tải metadata và quyền truy cập.

### 10.2. Pipeline cần dùng reference có thể tái tạo

Reference đáng tin cậy nên được dựng từ commit changelog đã phát hành bằng cùng phiên bản Liquibase và cấu hình DBMS tương ứng, hoặc lấy từ một môi trường chuẩn đã được kiểm soát. Không lấy tùy tiện một database development đang thay đổi làm chuẩn.

Lưu bằng chứng:

- Commit/version changelog và Liquibase Core/driver.
- DBMS/version và schema được so sánh.
- Thời điểm snapshot, database reference/target theo định danh không nhạy cảm.
- Danh sách object khác biệt và các filter đã dùng.
- Quyết định phân loại, người phê duyệt và changeset khắc phục.

Không lưu mật khẩu, token hoặc dữ liệu nhạy cảm trong artifact diff.

## 11. Đưa thay đổi thủ công hợp lệ trở lại quy trình

Không phải mọi hotfix đều phải bị đảo ngược. Nếu DBA đã thêm index để khắc phục sự cố và nhóm quyết định giữ lại, cần đưa thay đổi ấy về version control:

1. Thu thập lý do, người thực hiện, thời điểm và câu SQL gốc.
2. Kiểm tra object hiện tại trên mọi môi trường liên quan.
3. Xác định thay đổi có thể mô tả bằng change type Liquibase hay cần SQL native.
4. Tạo changeset mới với ID/author/path ổn định.
5. Kiểm thử từ cả database chưa có hotfix và database đã có hotfix.
6. Chọn chiến lược đồng bộ history phù hợp nếu target đã chứa object do DBA tạo.
7. Cập nhật tài liệu vận hành và quy định mọi thay đổi tương lai đi qua quy trình đã thống nhất.

### 11.1. Không tạo changeset làm trùng object

Giả sử production đã có index `idx_customer_email` do DBA tạo, còn staging chưa có. Nếu thêm changeset `createIndex` và chạy ngay trên production, Liquibase có thể gặp lỗi index đã tồn tại. Một precondition `indexExists` với `MARK_RAN` có thể được cân nhắc trong một thiết kế baseline/tiếp nhận có kiểm chứng, nhưng phải so sánh định nghĩa index thật (cột, thứ tự, unique, predicate, expression, schema). Chỉ trùng tên chưa đủ.

Một chiến lược khác là tách changeset tạo index cho môi trường chưa có và ghi nhận trạng thái tương đương ở production theo một quy trình baseline đã duyệt. Cần kiểm thử trên bản sao production và staging trước khi phát hành. Không sửa trực tiếp history để làm cho lệnh chạy qua.

### 11.2. Nếu hotfix không hợp lệ

Nếu thay đổi ngoài quy trình không được chấp nhận:

- Đánh giá object có thể xóa/khôi phục an toàn không.
- Xác định dữ liệu hoặc ứng dụng đã phụ thuộc vào object.
- Viết changeset remediation mới theo trạng thái thực tế.
- Nếu cần restore, kiểm tra backup và kế hoạch khôi phục.
- Không dùng diff-changelog để tự động drop object mà chưa xác định owner.

## 12. Quy trình điều tra một drift bất ngờ

Khi diff phát hiện object khác nhau, đi theo thứ tự:

### Bước 1 — Xác nhận phép so sánh

Kiểm tra reference/target có đúng chiều, đúng DBMS, đúng database/schema và đúng phiên bản công cụ. Kiểm tra filter, object types, default schema và quyền snapshot.

### Bước 2 — Xác định object và phạm vi sở hữu

Ghi nhận tên object, loại object, schema, thuộc tính khác nhau và service/owner chịu trách nhiệm. Nếu object thuộc hệ thống khác, phối hợp với owner trước khi thay đổi.

### Bước 3 — Đối chiếu lịch sử

Tìm changeset có liên quan trong `DATABASECHANGELOG`, xem ID/author/FILENAME/EXECTYPE/MD5SUM và commit phát hành. Lịch sử Liquibase không phản ánh những SQL thủ công không được ghi nhận.

### Bước 4 — Tìm nguồn gốc

Đối chiếu audit log DBMS, ticket hotfix, script DBA, pipeline log, thay đổi ORM và thời điểm restore. Không suy đoán người thực hiện chỉ từ kết quả diff.

### Bước 5 — Đánh giá ảnh hưởng

Kiểm tra dữ liệu, index usage, query plan, lock, dependencies, quyền và phiên bản ứng dụng. Một index thừa có thể không gây lỗi chức năng nhưng tốn dung lượng; một foreign key bị thiếu có thể cho phép dữ liệu orphan.

### Bước 6 — Chọn phương án

| Phân loại | Hướng giải quyết |
|---|---|
| Hotfix hợp lệ, cần giữ | Tạo changeset mới mô tả trạng thái được chấp nhận và đồng bộ các môi trường. |
| Thay đổi ngoài ý muốn, có thể đảo ngược | Tạo remediation changeset hoặc quy trình restore đã thử. |
| Khác biệt do cấu hình/DBMS có chủ đích | Ghi nhận mapping/ngoại lệ, chỉnh phạm vi so sánh. |
| Object thuộc service khác | Xác nhận owner, loại khỏi phạm vi nếu phù hợp và theo dõi bằng quy trình của owner. |
| Diff không đủ bằng chứng | Bổ sung snapshot, quyền metadata hoặc kiểm tra thủ công trước khi kết luận. |

### Bước 7 — Kiểm chứng sau xử lý

Chạy diff lại trên cùng phạm vi, đối chiếu history và schema thật. Nếu thay đổi liên quan dữ liệu, chạy truy vấn bất biến/data validation riêng. Lưu kết quả và quyết định để lần kiểm tra sau có thể hiểu vì sao một khác biệt được chấp nhận.

## 13. Kết hợp với Spring Boot và quản trị thay đổi schema

Trong ứng dụng Spring Boot, Liquibase có thể chạy khi khởi động:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/master.yaml
~~~

Nếu Hibernate/JPA cũng được cấu hình tự cập nhật schema, ví dụ `ddl-auto=update`, có thể phát sinh drift ngoài changelog. Nên xác định một nguồn sở hữu DDL chính, dùng schema validation và quản lý thay đổi qua Liquibase.

Các nguyên tắc phối hợp:

- Tài khoản ứng dụng runtime chỉ có quyền cần thiết; tài khoản migration có quyền DDL riêng.
- Hotfix DBA phải có ticket, script, kiểm chứng và bước đưa lại vào changelog.
- Pipeline diff cần reference từ artifact đã phát hành hoặc database chuẩn được quản lý.
- `DATABASECHANGELOGLOCK` giúp điều phối Liquibase, nhưng không ngăn DBA hoặc ứng dụng khác chạy SQL trực tiếp.
- Sau deploy, kiểm tra history, schema và behavior ứng dụng; không chỉ nhìn `status`.

## 14. Bài thực hành có kiểm chứng

**Bối cảnh:** một service khách hàng quản lý bảng `customer_record` bằng Liquibase. Changelog tạo cột `email VARCHAR(80)` và index theo email. Một người quản trị thay đổi độ dài cột trực tiếp trên production thành `VARCHAR(255)`.

### Giai đoạn A — Dựng reference và target

1. Tạo PostgreSQL test database từ changelog đã phát hành; đây là reference.
2. Tạo bản sao target từ trạng thái có cùng migration history.
3. Trên target, thực hiện hotfix SQL đổi `email` thành `VARCHAR(255)`.
4. Xác minh history không thay đổi chỉ vì câu SQL thủ công.

### Giai đoạn B — Phát hiện drift

1. Chạy `liquibase diff` với reference và target đúng chiều.
2. Xem báo cáo có khác biệt kiểu cột hay không.
3. Đối chiếu metadata cột bằng truy vấn phù hợp DBMS.
4. Chạy `status` và quan sát vì sao changeset cũ vẫn có thể được xem là đã triển khai.
5. Ghi lại giới hạn của diff và những thuộc tính cần xác minh thêm.

### Giai đoạn C — Đưa hotfix vào changelog

1. Giữ nguyên changeset tạo bảng ban đầu.
2. Thêm changeset mới `modifyDataType` để chuẩn hóa độ dài 255.
3. Chạy `validate`, `status --verbose` và `update-sql` trên reference/target.
4. Kiểm thử từ database mới và database đã có hotfix.
5. Xác minh không làm mất dữ liệu, ứng dụng ghi/đọc email dài hơn 80 ký tự được và history có changeset mới.

### Giai đoạn D — Xác minh hội tụ

1. Dựng database thử mới từ toàn bộ changelog.
2. Áp dụng forward changesets trên target đã có hotfix theo quy trình kiểm chứng.
3. Chạy diff lại giữa reference chuẩn mới và target.
4. Đối chiếu schema và dữ liệu riêng.
5. Ghi nhận những khác biệt được chấp nhận có chủ đích.

### Tiêu chí đạt

- Giải thích được vì sao `status` và checksum không tự phát hiện mọi schema drift.
- Dùng đúng reference/target khi chạy diff.
- Phân biệt drift hợp lệ, drift ngoài ý muốn và khác biệt do cấu hình.
- Biết review `diff-changelog` trước khi áp dụng.
- Đưa hotfix hợp lệ vào một changeset mới mà không sửa lịch sử cũ.
- Có kết quả diff sau xử lý và kiểm tra dữ liệu/ứng dụng.

## 15. Checklist phát hiện và xử lý schema drift

- [ ] Reference schema được xác định rõ, có owner và version/commit.
- [ ] Reference và target cùng DBMS/version hoặc khác biệt đã được giải thích.
- [ ] Đúng JDBC URL, database, schema, catalog và quyền metadata.
- [ ] Đã xác minh hướng reference/target trước khi chạy diff-changelog.
- [ ] Phạm vi object và include/exclude filter được ghi nhận.
- [ ] Đã đọc cảnh báo snapshot và các loại object không thể so sánh.
- [ ] Đã phân biệt schema drift với pending changeset và data drift.
- [ ] Đã đối chiếu `DATABASECHANGELOG`, checksum và lịch sử deploy.
- [ ] Đã xác định owner và nguồn gốc của từng khác biệt.
- [ ] Không drop object hoặc chạy diff-changelog output trực tiếp lên production.
- [ ] Hotfix hợp lệ được đưa vào changeset mới; lịch sử cũ được giữ nguyên.
- [ ] Thay đổi bị từ chối có remediation/restore plan đã kiểm chứng.
- [ ] Đã thử trên database đại diện và nhiều môi trường cần hỗ trợ.
- [ ] Sau xử lý, diff lại và kiểm tra schema/data/behavior.
- [ ] Có quy trình định kỳ, lưu kết quả và người chịu trách nhiệm xử lý drift.

## 16. Câu hỏi tự kiểm tra

1. Schema drift là gì? Vì sao một hotfix hợp lệ vẫn có thể tạo drift?
2. Desired schema, actual schema và migration history khác nhau như thế nào?
3. Vì sao `status` báo không pending không chứng minh schema không drift?
4. Checksum của changeset có phát hiện việc DBA xóa cột trực tiếp không?
5. Reference database nên được chọn theo những tiêu chí nào?
6. Trong Liquibase diff, reference và target có vai trò gì?
7. Vì sao đảo reference và target có thể sinh changeset theo hướng nguy hiểm?
8. `diff-changelog` có thể thay thế review migration không? Vì sao?
9. Schema diff khác data diff ở đâu?
10. Những loại object nào có thể không được snapshot hoặc so sánh đầy đủ?
11. Làm sao phân biệt drift với khác biệt cấu hình DBMS có chủ đích?
12. Khi DBA thêm index hợp lệ trên production, cần làm gì để các môi trường hội tụ?
13. Vì sao không nên tự động xóa object chỉ có ở target?
14. Làm thế nào tổ chức kiểm tra drift định kỳ trong CI/CD mà không lấy development làm reference tùy tiện?

## Kết luận

Phát hiện schema drift đòi hỏi so sánh **schema thật với một reference có thể tin cậy**, không chỉ đọc changeset history hoặc checksum. Liquibase `diff` và `diff-changelog` giúp xác định, mô tả khác biệt, nhưng kết quả phải được phân loại theo owner, nguyên nhân, dữ liệu và DBMS trước khi sửa. Hotfix được chấp nhận cần được đưa trở lại changelog bằng changeset mới; thay đổi không hợp lệ cần remediation hoặc restore có kiểm chứng. Khi kết hợp diff định kỳ, review SQL, đối chiếu `DATABASECHANGELOG` và kiểm tra dữ liệu/ứng dụng, `DATABASE_SCHEMA_MIGRATION_LIQUIBASE` giúp giữ các môi trường nhất quán và duy trì lịch sử triển khai có thể truy vết.
