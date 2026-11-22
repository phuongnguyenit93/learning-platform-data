# Đối chiếu lịch sử Liquibase với phiên bản ứng dụng

## 1. Vì sao phải đối chiếu hai loại phiên bản?

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Quy trình vận hành còn cần migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Một câu hỏi thường gặp là: **ứng dụng đang chạy phiên bản nào, và database đã được migration tới trạng thái nào để phiên bản đó hoạt động an toàn?**

Hai thông tin này liên quan nhưng không đồng nhất:

- **Phiên bản ứng dụng** mô tả artifact/code đang được triển khai, thường là semantic version, build number, commit SHA hoặc image digest.
- **Lịch sử Liquibase** mô tả changeset nào đã được xử lý trên một database cụ thể, theo identity và metadata thực thi.

Ví dụ, ứng dụng **customer-service 3.8.0** có thể cần các changeset **DB-401** đến **DB-417**. Database staging có thể đã chạy thêm **DB-420** từ một nhánh thử nghiệm, trong khi production vẫn dừng ở **DB-414**. Cùng một phiên bản ứng dụng vì thế có thể gặp trạng thái schema khác nhau ở hai môi trường.

Ngược lại, database có thể đã áp dụng đầy đủ migration cho phiên bản ứng dụng mới, nhưng một số replica vẫn đang chạy binary cũ trong quá trình rolling deployment. Nếu migration phá vỡ tương thích ngược, những replica đó có thể lỗi dù Liquibase báo update thành công.

Bài học này trình bày cách liên kết release metadata với **DATABASECHANGELOG**, cách xác định tập changeset cần có cho một phiên bản ứng dụng, cách phát hiện lệch lịch sử và cách kiểm soát compatibility trong triển khai nhiều phiên bản. Nguyên tắc cốt lõi là **đối chiếu bằng bằng chứng từ artifact, deployment và database**, không suy ra phiên bản ứng dụng từ số lượng changeset hoặc một dòng lịch sử cuối cùng.

## 2. Phiên bản ứng dụng và phiên bản schema là hai trục riêng

Không nên giả định ứng dụng 3.8.0 tương đương schema version 3.8.0. Một release ứng dụng có thể:

- Không thay đổi database.
- Thêm một hoặc nhiều changeset.
- Chỉ thay đổi logic đọc/ghi nhưng giữ nguyên schema.
- Cần migration được triển khai trước khi rollout.
- Tương thích với nhiều trạng thái schema trong giai đoạn chuyển tiếp.
- Chia thay đổi schema thành nhiều release để hỗ trợ rolling deployment.

Tương tự, schema có thể tiến lên mà chưa có binary mới được triển khai. Ví dụ pipeline chạy migration job trước, sau đó mới rollout application. Trong khoảng thời gian này, schema đã ở trạng thái mới nhưng các instance cũ vẫn đang hoạt động.

| Khái niệm | Đại diện cho | Nguồn bằng chứng |
|---|---|---|
| Application version | Mã ứng dụng/artifact | Build metadata, image tag/digest, commit SHA, deployment record |
| Changelog version | Tập changelog được đóng gói | Root changelog, commit/artifact, release manifest |
| Database migration history | Changeset thực tế đã được Liquibase ghi nhận | DATABASECHANGELOG |
| Schema state | Cấu trúc và dữ liệu hiện có | Catalog/metadata, truy vấn đối soát, schema diff |
| Deployment event | Lần triển khai cụ thể | CI/CD run, release system, audit log |

Không nguồn nào tự thay thế hoàn toàn các nguồn còn lại. DATABASECHANGELOG có thể chứng minh changeset đã được ghi nhận, nhưng không tự cho biết binary nào đang chạy. Build metadata cho biết binary, nhưng không chứng minh database đã nhận migration.

### 2.1. Một release có thể hỗ trợ nhiều schema state

Trong giai đoạn rollout an toàn, ứng dụng mới thường cần chạy được trên schema trước migration và schema sau migration, hoặc ít nhất phải có thứ tự triển khai rõ ràng.

Ví dụ:

- Ứng dụng 3.7 đọc cột **customer.name**.
- Migration mở rộng thêm **customer.display_name** nhưng vẫn giữ cột cũ.
- Ứng dụng 3.8 có thể đọc cột mới và tiếp tục hỗ trợ dữ liệu cũ trong giai đoạn chuyển tiếp.
- Sau khi mọi instance và consumer đã chuyển, release sau mới bỏ cột **name**.

Do đó, không nên tạo quy tắc đơn giản kiểu “app version bằng schema version”. Hãy xác định **khoảng schema tương thích** cho từng phiên bản ứng dụng.

## 3. DATABASECHANGELOG ghi nhận điều gì?

Liquibase thường dùng bảng **DATABASECHANGELOG** để ghi nhận changeset đã được xử lý trên một database. Những trường thường gặp gồm:

| Cột | Ý nghĩa |
|---|---|
| ID | ID của changeset |
| AUTHOR | Author của changeset |
| FILENAME | Đường dẫn logic của changelog |
| DATEEXECUTED | Thời điểm Liquibase ghi nhận thực thi |
| ORDEREXECUTED | Thứ tự thực thi được ghi nhận |
| EXECTYPE | Kiểu xử lý như EXECUTED, MARK_RAN hoặc RERAN |
| MD5SUM | Checksum được lưu cho changeset |
| TAG | Tag được ghi nhận trong lịch sử |
| CONTEXTS / LABELS | Context/label liên quan, nếu phiên bản và cấu hình lưu các trường này |
| DEPLOYMENT_ID | Định danh deployment ở những phiên bản có hỗ trợ |

Cấu trúc bảng, kiểu dữ liệu và các cột có thể khác theo phiên bản Liquibase, tên/schema metadata tùy chỉnh và DBMS. Trước khi viết truy vấn audit, hãy xác nhận cấu trúc thực tế của bảng trên database đích.

### 3.1. Identity của changeset

Liquibase nhận diện một changeset bằng bộ ba:

```text
(id, author, logical changelog file path)
```

Checksum là thông tin kiểm tra nội dung của changeset đã nhận diện; nó không thay thế identity. Nếu file được di chuyển làm thay đổi logical path, cùng ID và author vẫn có thể bị nhận diện như một changeset khác.

Khi đối chiếu lịch sử giữa các môi trường, luôn xem đủ **ID**, **AUTHOR** và **FILENAME**. Không chỉ so sánh ID hoặc tên file hiển thị trong Git.

### 3.2. DATABASECHANGELOG không lưu application version mặc định

Một nhầm lẫn phổ biến là tìm cột APP_VERSION trong DATABASECHANGELOG. Bảng này chủ yếu quản lý lịch sử changeset; nó không phải sổ đăng ký đầy đủ các binary application đã được rollout.

Nếu cần biết phiên bản ứng dụng nào đã triển khai cùng một migration, hãy liên kết dữ liệu Liquibase với release/deployment metadata được quản lý riêng. Không tự thêm cột hoặc sửa cấu trúc bảng metadata do Liquibase quản lý chỉ để lưu application version.

## 4. Thu thập application version từ artifact

Phiên bản ứng dụng nên được tạo tại build time và gắn với artifact bất biến. Các thông tin thường cần:

- Service/application name.
- Semantic version hoặc release version.
- Git commit SHA.
- Build number hoặc pipeline run ID.
- Artifact checksum hoặc OCI image digest.
- Build timestamp.
- Root changelog path và changelog artifact version.
- Liquibase version và DBMS/driver tương ứng khi có ích cho audit.

Ví dụ metadata trong file build-info:

```properties
build.name=customer-service
build.version=3.8.0
build.artifact=customer-service
build.group=com.example.platform
```

Spring Boot Actuator có thể cung cấp build information nếu artifact được tạo với build-info metadata và endpoint **info** được cấu hình. Một số dự án bổ sung Git commit/branch bằng plugin hoặc tạo manifest riêng. Cần bảo vệ endpoint theo chính sách; không công khai thông tin nội bộ ngoài phạm vi cho phép.

### 4.1. Version tag không đủ để nhận diện artifact

Một image tag như **customer-service:3.8.0** có thể bị ghi đè nếu registry cho phép. Để truy vết chính xác, nên ghi cả image digest hoặc artifact checksum.

Hai build cùng version nhưng khác commit có thể chứa changelog khác nhau. Vì vậy, deployment record cần nhận diện artifact thực tế, không chỉ một chuỗi version do người dùng đặt.

### 4.2. Giữ changelog trong cùng release artifact

Nếu ứng dụng đóng gói changelog trong classpath, artifact ứng dụng và changelog cần được liên kết. Nếu migration job được build riêng, release manifest phải chỉ rõ migration artifact nào thuộc release application nào.

Không chạy migration từ working tree của developer hoặc branch trôi nổi rồi triển khai một image khác. Khi điều tra production, cần có khả năng lấy lại đúng changelog đã được dùng trong lần triển khai đó.

## 5. Tạo release manifest liên kết ứng dụng và changeset

Một release manifest có thể mô tả mối quan hệ giữa artifact ứng dụng và tập migration dự kiến. Đây là metadata do pipeline hoặc hệ thống release quản lý; nó không phải một bảng Liquibase bắt buộc.

Ví dụ YAML minh họa:

```yaml
release:
  service: customer-service
  applicationVersion: 3.8.0
  gitCommit: 8c2d91a
  imageDigest: sha256:example-digest
  changelog:
    root: db/changelog/db.changelog-master.yaml
    artifactVersion: 3.8.0
    expectedChangesets:
      - id: DB-401-add-customer-email
        author: platform-team
        file: db/changelog/changes/DB-401-add-customer-email.yaml
      - id: DB-417-add-customer-status
        author: platform-team
        file: db/changelog/changes/DB-417-add-customer-status.yaml
  database:
    engine: PostgreSQL
    supportedSchemaRange:
      minimum: customer-schema-3.7
      target: customer-schema-3.8
```

Ví dụ chỉ minh họa cấu trúc dữ liệu; tên schema milestone và danh sách changeset phải được tạo từ release thực tế. Không suy ra danh sách expected changesets chỉ bằng cách lọc tên file hoặc so sánh số ID.

Manifest có thể được sinh ở build time hoặc release preparation. Cần version-control, kiểm tra tính toàn vẹn nếu chính sách yêu cầu và lưu cùng deployment record.

### 5.1. Manifest nên có hai loại thông tin

1. **Artifact identity:** application version, commit, image digest, changelog root, Liquibase version.
2. **Database expectation:** changeset bắt buộc, schema milestone, khoảng schema tương thích và yêu cầu data migration.

Một manifest hữu ích phải giúp trả lời: “Artifact nào đã được triển khai?” và “Artifact này yêu cầu database ở trạng thái nào?”. Nó không nên chỉ ghi một số version chung chung.

## 6. Xác định tập changeset mà một phiên bản ứng dụng yêu cầu

Có nhiều cách quản lý mapping.

### 6.1. Mapping theo release manifest

Pipeline lưu danh sách changeset dự kiến của release, với mỗi changeset được định danh bằng ID, author và logical path. Đây là cách rõ ràng khi release cần audit hoặc có nhiều nhánh.

Ưu điểm là có thể so sánh expected set với actual history. Nhược điểm là manifest phải được cập nhật đồng bộ với changelog; nếu tạo thủ công, nó có thể bị stale.

### 6.2. Mapping theo schema milestone/tag

Một tag có thể đánh dấu một mốc lịch sử Liquibase, chẳng hạn **customer-schema-3.8**. Tag giúp vận hành gọi tên trạng thái schema theo release hoặc milestone.

Tuy nhiên, tag không tự chứng minh application version nào đang chạy. Một database có thể được tag trước khi application rollout hoàn tất; một ứng dụng có thể tương thích với nhiều tag/schema state.

Dùng tag như mốc schema, rồi liên kết tag với application release trong manifest hoặc deployment record.

### 6.3. Mapping theo commit/artifact changelog

Nếu changelog được đóng gói cùng artifact, commit và digest cho phép xác định chính xác nguồn migration. Có thể so sánh root changelog của artifact với history database bằng công cụ Liquibase và truy vấn metadata.

Cách này giảm phụ thuộc vào một trường version tự khai báo, nhưng vẫn cần quy tắc xác định changeset nào là bắt buộc cho release.

## 7. Truy vấn lịch sử Liquibase để đối chiếu

Truy vấn chỉ đọc sau có thể giúp kiểm tra những changeset gần đây:

```sql
SELECT ID,
       AUTHOR,
       FILENAME,
       DATEEXECUTED,
       ORDEREXECUTED,
       EXECTYPE,
       MD5SUM,
       TAG
FROM DATABASECHANGELOG
ORDER BY ORDEREXECUTED DESC, DATEEXECUTED DESC;
```

Câu truy vấn là ví dụ với tên bảng/cột mặc định. Hãy xác nhận schema, tên bảng, các cột tồn tại và cú pháp DBMS thực tế trước khi chạy. Không sửa bảng metadata bằng SQL để làm kết quả khớp với release manifest.

### 7.1. So sánh expected changesets với actual history

Với mỗi changeset trong manifest, kiểm tra:

- Có bản ghi trong DATABASECHANGELOG không?
- ID, author và logical file path có khớp không?
- Checksum có tương ứng với artifact đã phát hành không?
- EXECTYPE có đúng với chính sách release không?
- Thời điểm thực thi có trước thời điểm ứng dụng mới nhận traffic không?
- Có changeset ngoài tập dự kiến được chạy thêm không?

Nếu một changeset được ghi là MARK_RAN, cần xem lý do và precondition; không tự coi nó tương đương với việc SQL đã chạy như EXECUTED. Với RERAN, cần hiểu runOnChange/runAlways và history theo phiên bản Liquibase.

### 7.2. Thời gian và thứ tự không thay thế identity

ORDEREXECUTED và DATEEXECUTED hữu ích để sắp xếp lịch sử. Nhưng không nên kết luận “mọi changeset trước order 120 thuộc app 3.8”. Các môi trường có thể chạy lịch sử khác nhau, có tag, baseline, changeset đặc biệt hoặc triển khai xen kẽ.

Luôn liên kết order/time với identity và artifact cụ thể.

## 8. Dùng lệnh Liquibase để kiểm tra trạng thái hiện tại

Một số lệnh hữu ích trong quy trình vận hành:

```bash
liquibase validate
liquibase status --verbose
liquibase history
liquibase update-sql
```

- **validate** kiểm tra tính hợp lệ của changelog theo những kiểm tra Liquibase hỗ trợ.
- **status --verbose** cho biết changeset pending theo database và cấu hình đang kết nối.
- **history** hiển thị lịch sử đã triển khai theo khả năng của phiên bản.
- **update-sql** sinh SQL dự kiến cho changeset pending mà không thực hiện update.

Các lệnh phải chạy với đúng root changelog, URL, credentials, schema, context, label, parameters, driver và phiên bản Liquibase của release. Nếu khác cấu hình, tập changeset được chọn có thể khác.

Không dùng riêng status để kết luận database tương thích với application version. Pending changeset có thể là migration dự kiến cho release tiếp theo, migration tùy context hoặc thay đổi chưa được phép triển khai vào môi trường đó.

### 8.1. Preview không thay thế kiểm tra schema và dữ liệu

update-sql cho biết SQL dự kiến, nhưng không chứng minh dữ liệu hiện tại đáp ứng precondition hoặc migration chạy thành công trên production. Cần thêm kiểm tra schema/data và thử nghiệm trên database đại diện.

Nếu release yêu cầu một changeset cụ thể nhưng status --verbose không liệt kê nó, hãy điều tra xem changeset đã chạy, bị lọc bởi context/label/dbms, bị nhận diện dưới identity khác hay không được include trong root changelog.

## 9. Dùng tag làm schema milestone

Liquibase hỗ trợ gắn tag vào lịch sử database. Ví dụ CLI:

```bash
liquibase tag --tag=customer-schema-3.8
```

Một cách khác là dùng change type **tagDatabase** trong changelog theo cú pháp phiên bản. Tag có thể hữu ích để đánh dấu mốc schema sau một nhóm changeset đã được áp dụng.

Ví dụ changelog:

```yaml
databaseChangeLog:
  - changeSet:
      id: DB-417-add-customer-status
      author: platform-team
      changes:
        - addColumn:
            tableName: customer_account
            columns:
              - column:
                  name: status_code
                  type: varchar(20)
  - changeSet:
      id: DB-418-mark-schema-3-8
      author: platform-team
      changes:
        - tagDatabase:
            tag: customer-schema-3.8
```

Tag là mốc lịch sử schema, không phải application version đang chạy. Nếu deployment bị dừng sau migration nhưng trước rollout application, database có thể đã mang tag 3.8 trong khi mọi instance vẫn là app 3.7.

Để đối chiếu chính xác, release record nên lưu cả tag/schema milestone và application deployment state.

## 10. Xây dựng ma trận tương thích ứng dụng–schema

Một ma trận compatibility mô tả phiên bản ứng dụng nào có thể hoạt động với schema state nào.

Ví dụ:

| Ứng dụng | Schema 3.7 | Schema 3.8-expand | Schema 3.8-contract |
|---|---:|---:|---:|
| App 3.7 | Có | Có | Không |
| App 3.8 | Có điều kiện | Có | Có |
| App 3.9 | Không hỗ trợ | Có | Có |

Đây là ví dụ minh họa. Mỗi ô cần dựa trên kiểm thử và hợp đồng ứng dụng thật, không điền theo suy đoán.

### 10.1. Vì sao cần compatibility range?

Trong rolling deployment, app cũ và mới có thể chạy đồng thời. Nếu migration xóa cột cũ ngay khi app mới vừa khởi động, các instance cũ có thể lỗi. Compatibility range giúp xác định schema nào an toàn trong giai đoạn chuyển tiếp.

Một cách biểu diễn trong manifest:

```yaml
application:
  version: 3.8.0
databaseCompatibility:
  minimumSchema: customer-schema-3.7
  maximumSchema: customer-schema-3.8-expand
requiredSchemaMilestone:
  - customer-schema-3.8-expand
```

Tên milestone chỉ là ví dụ. Nếu schema mới đã contract và bỏ cấu trúc cũ, compatibility range của app cũ phải loại trừ trạng thái đó.

### 10.2. Không chỉ dựa vào version string

Version string có thể tăng nhưng migration không đổi; hoặc schema có thể được cập nhật độc lập. Ma trận phải mô tả yêu cầu thực tế như cột bắt buộc, constraint, semantics và data state. Có thể bổ sung kiểm tra capability/schema marker thay vì chỉ so sánh chuỗi version.

## 11. Expand–migrate–contract và rolling deployment

Để nhiều phiên bản ứng dụng cùng hoạt động an toàn, hãy tách thay đổi phá vỡ tương thích thành nhiều giai đoạn:

```text
EXPAND
  Thêm cột/bảng mới, giữ cấu trúc cũ
       |
       v
MIGRATE
  Backfill và đối soát dữ liệu
  Triển khai app tương thích hai cấu trúc
       |
       v
CUTOVER
  Chuyển read/write sang cấu trúc mới
       |
       v
VERIFY
  Xác nhận không còn consumer cũ
       |
       v
CONTRACT
  Bỏ cột/bảng cũ trong release riêng
```

Ví dụ đổi **customer.name** thành **customer.display_name**:

1. Release schema A thêm display_name nullable, giữ name.
2. App 3.8 đọc/ghi theo quy tắc tương thích, có thể dual-write có kiểm soát.
3. Backfill dữ liệu cũ và kiểm tra số lượng/giá trị.
4. Chuyển toàn bộ consumer sang cột mới.
5. Xác nhận app cũ, job, báo cáo và tích hợp không còn đọc cột name.
6. Release sau mới bỏ name.

### 11.1. Thứ tự release cần được ghi rõ

Một deployment record nên lưu migration job bắt đầu/kết thúc, tag hoặc changeset cuối của schema milestone, application rollout bắt đầu/kết thúc, phiên bản app trước/sau, thời điểm mỗi replica chuyển version và kết quả smoke test/readiness.

Nhờ đó, khi sự cố xảy ra, đội vận hành biết database đã tiến đến đâu và app nào còn đang chạy.

### 11.2. Dual-write cần có tính idempotent và đối soát

Nếu app ghi cả cột cũ và mới, cần đảm bảo hai lần ghi thuộc cùng transaction hoặc có cơ chế đồng bộ có thể retry an toàn. Nếu ghi thành hai thao tác độc lập, một thao tác có thể thành công còn thao tác kia thất bại.

Hãy có metric/log để phát hiện chênh lệch, quy tắc xử lý bản ghi lỗi và checkpoint cho backfill. Không contract cấu trúc cũ chỉ vì migration job đã hoàn thành; phải xác nhận mọi consumer đã chuyển.

## 12. Đối chiếu lịch sử trong rolling deployment

Giả sử có ba replica:

| Replica | Application version | Trạng thái |
|---|---|---|
| Pod A | 3.7.4 | Đang phục vụ |
| Pod B | 3.8.0 | Đã ready |
| Pod C | 3.8.0 | Đang khởi động |

Database đã chạy changeset DB-417 để thêm cột mới. Đây có thể là trạng thái hợp lệ nếu app 3.7.4 vẫn tương thích với schema expand. Nếu changeset DB-418 xóa cột cũ ngay lúc đó, Pod A có thể lỗi.

Trạng thái release cần quan sát ở hai cấp:

1. **Database state:** tập changeset, schema milestone, dữ liệu.
2. **Fleet state:** tập phiên bản app đang chạy và trạng thái rollout.

Không chỉ nhìn một pod hoặc một dashboard version. Cần xác nhận tất cả instance/worker/consumer quan trọng đã chuyển trước khi chạy contract migration.

### 12.1. Nhiều service dùng chung database

Nếu nhiều service chia sẻ database, application version của một service không thể đại diện cho toàn bộ consumer. Ma trận compatibility phải liệt kê tất cả service, batch job, ETL và integration có sử dụng object sẽ thay đổi.

Một migration có thể tương thích với customer-service 3.8 nhưng phá vỡ reporting-job 2.4. Cần owner của từng consumer xác nhận trước khi xóa hoặc đổi semantics của schema.

## 13. Phát hiện lệch lịch sử giữa ứng dụng và database

### 13.1. App mới nhưng changeset bắt buộc chưa chạy

Ví dụ app 3.8 query cột status_code nhưng DATABASECHANGELOG chưa có changeset tạo cột. Nguyên nhân có thể là migration job bị bỏ qua, Liquibase bị tắt, root changelog sai hoặc changeset bị filter.

Hành động:

1. Dừng rollout/traffic nếu app không tương thích schema hiện tại.
2. Xác minh database đích và root changelog.
3. Chạy status --verbose với đúng cấu hình.
4. Đối chiếu expected changeset trong manifest với actual history.
5. Kiểm tra schema thực tế và SQL preview.
6. Chạy migration qua quy trình được phê duyệt rồi hậu kiểm.

### 13.2. App cũ nhưng schema đã contract

Nếu schema đã bỏ cột hoặc bảng mà app cũ vẫn chạy, cần khôi phục tương thích bằng migration bù hoặc rollback được thiết kế trước. Không tự thêm lại cột rỗng rồi cho app tiếp tục nếu semantics/dữ liệu đã thay đổi.

### 13.3. App version đúng nhưng changelog artifact khác

Hai artifact cùng ghi version 3.8.0 nhưng khác commit hoặc digest có thể chứa changeset khác. Hãy so sánh image digest, build metadata, commit và changelog artifact; không chỉ so sánh version string.

### 13.4. History có changeset ngoài manifest

Có thể database đã nhận hotfix, migration vận hành hoặc changeset từ nhánh khác. Xác định nguồn, người phê duyệt, compatibility và ảnh hưởng trước khi tiếp tục. Không xóa dòng history để làm actual set giống expected set.

### 13.5. History khớp nhưng schema thực tế bị drift

DBA hoặc script ngoài Liquibase có thể sửa object sau migration. History vẫn ghi changeset đã chạy nhưng schema hiện tại khác. Cần dùng schema diff hoặc kiểm tra metadata/data để phát hiện drift; không coi history là snapshot schema.

## 14. Phân biệt drift, pending migration và version mismatch

| Hiện tượng | Ý nghĩa | Bằng chứng cần xem |
|---|---|---|
| Pending changeset | Changelog hiện tại có thay đổi chưa được áp dụng | status --verbose, root changelog và filters |
| Checksum mismatch | Nội dung changeset đã nhận diện không khớp lịch sử | Log, checksum, artifact và commit |
| Identity mismatch | ID/author/logical path khác lịch sử | FILENAME và changelog path |
| Schema drift | Cấu trúc thực tế khác trạng thái mong muốn/lịch sử | diff, catalog và schema audit |
| App/schema incompatibility | App đang chạy yêu cầu schema khác trạng thái hiện tại | Compatibility matrix, runtime errors và release manifest |
| Release artifact mismatch | Artifact deploy khác artifact đã test/duyệt | Image digest, commit, pipeline run |
| Partial migration | Một phần changeset/DDL đã áp dụng trước khi lỗi | Logs, history và schema/data thực tế |

Các khái niệm này có thể cùng xảy ra. Ví dụ app mới có thể đang chạy trên schema drift và đồng thời có một changeset pending. Phải phân loại trước khi chọn biện pháp sửa.

## 15. Release ledger: nơi ghi nhận lần deploy ứng dụng

Nếu cần truy vết app version đã chạy cùng migration nào, hãy lưu deployment metadata trong hệ thống release/audit riêng hoặc một bảng ứng dụng được thiết kế có chủ đích. Không biến DATABASECHANGELOG thành bảng quản lý application release.

Một bản ghi release có thể gồm:

| Trường | Ví dụ |
|---|---|
| Service | customer-service |
| Application version | 3.8.0 |
| Commit | 8c2d91a |
| Image digest | sha256:... |
| Environment | staging |
| Deployment ID | deploy-2026-11-20-042 |
| Migration artifact | customer-service-db-3.8.0 |
| Liquibase version | phiên bản đã pin |
| Schema milestone | customer-schema-3.8-expand |
| Migration started/finished | timestamp có timezone |
| Expected changesets | manifest hoặc tham chiếu artifact |
| Actual result | success/failed/partial |
| Approval | release/change reference |

### 15.1. Nếu lưu release ledger trong database

Có thể thiết kế bảng riêng do ứng dụng hoặc release platform sở hữu, ví dụ application_release_audit. Bảng này cần schema, retention, quyền ghi và semantics được quản lý rõ. Không thêm cột tùy tiện vào bảng Liquibase metadata.

Nếu record release được ghi bằng changeset, hãy phân biệt record đó là một phần của database migration hay là sự kiện application rollout. Hai sự kiện có thời điểm và trạng thái khác nhau. Có thể cần một deployment system ghi nhận sau khi app rollout hoàn tất.

### 15.2. Tránh ghi application version quá sớm

Nếu ghi “app 3.8.0 deployed” ngay trước khi rollout bắt đầu, record có thể sai khi rollout thất bại. Tốt hơn là ghi event có trạng thái STARTED, SUCCEEDED, FAILED hoặc PARTIAL trong release ledger/audit system, cùng thời gian và deployment ID. Chỉ cập nhật trạng thái cuối sau khi rollout và hậu kiểm thực sự hoàn tất.

## 16. Vận hành khi migration được chạy bởi Spring Boot

Spring Boot có thể chạy Liquibase khi application context khởi tạo, thông qua bean tích hợp SpringLiquibase.

Ví dụ:

```yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
```

Trong mô hình này, application startup và migration có quan hệ trực tiếp. Nếu Liquibase lỗi, context thường không khởi tạo thành công. Nhưng điều đó không có nghĩa database không thay đổi: các changeset trước có thể đã commit.

Khi vận hành, cần ghi nhận artifact/version nào khởi chạy Liquibase, database URL/schema, root changelog và context/label, changeset bắt đầu/kết thúc và lỗi, application version của từng instance cùng thời điểm instance ready.

### 16.1. Migration job riêng giúp tách hai vòng đời

Với hệ thống nhiều replica hoặc cần phê duyệt, có thể chạy migration job riêng trước rollout:

```text
Build application + migration artifact
              |
              v
Validate / preview / test
              |
              v
Run Liquibase migration job
              |
              v
Verify DATABASECHANGELOG + schema
              |
              v
Record schema milestone
              |
              v
Roll out application version
              |
              v
Verify fleet version + readiness
              |
              v
Record deployment success
```

Khi chọn mô hình này, ứng dụng runtime có thể tắt auto-run Liquibase theo profile. Nhưng pipeline phải bảo đảm migration job thành công trước khi rollout và không có đường triển khai khác bỏ qua bước đó.

## 17. Rollback ứng dụng không đồng nghĩa rollback database

Khi release mới gặp lỗi, nhóm có thể rollback application binary về phiên bản cũ. Database có thể vẫn ở schema mới vì migration đã được áp dụng trước đó.

Nếu schema migration theo hướng expand và giữ tương thích ngược, app cũ có thể chạy trên schema mới. Đây là lý do chiến lược expand–migrate–contract hữu ích: rollback app thường không cần rollback database ngay.

Nếu schema đã contract hoặc thay đổi semantics phá vỡ tương thích, rollback app có thể thất bại. Cần đánh giá:

- App cũ cần bảng/cột nào?
- Schema hiện tại còn giữ những object đó không?
- Dữ liệu có bị chuyển đổi/xóa không?
- Rollback DDL có thể làm mất dữ liệu mới không?
- Có thể triển khai forward fix nhanh hơn không?
- Có backup/PITR hoặc mapping để khôi phục dữ liệu không?

Không chạy rollback chỉ vì app deployment bị rollback. Hãy xác định schema state và compatibility trước.

### 17.1. Rollback có thể làm lịch sử khác với manifest release

Một database có thể đã chạy migration của app 3.8, sau đó application binary quay lại 3.7. Điều đó không có nghĩa lịch sử Liquibase cần bị xóa. Deployment record cần thể hiện app 3.7 đang chạy trên schema milestone 3.8-expand, nếu cặp này được hỗ trợ.

Lịch sử database phản ánh thay đổi schema đã áp dụng; release ledger phản ánh application rollout. Giữ hai dòng thời gian riêng nhưng liên kết bằng deployment ID/artifact.

## 18. Quy trình đối chiếu trước và sau release

### Trước release

1. Xác nhận application artifact version, commit và image digest.
2. Xác nhận migration artifact/root changelog cùng release.
3. Xác định expected changesets và schema milestone.
4. Đọc actual history từ database đích.
5. Chạy validate, status --verbose và SQL preview với đúng filters.
6. Kiểm tra schema/data drift và precondition.
7. Xác nhận compatibility với tất cả app version đang chạy.
8. Review rollback/forward-fix và backup.

### Trong release

1. Ghi deployment ID và bắt đầu migration event.
2. Chạy migration theo một cơ chế sở hữu rõ ràng.
3. Theo dõi log, lock và thời gian changeset.
4. Nếu thất bại, dừng rollout và xác minh partial apply.
5. Sau khi migration thành công, đối chiếu actual history và schema.
6. Chỉ sau đó rollout application nếu quy trình yêu cầu migration trước.

### Sau release

1. Kiểm tra phiên bản của toàn bộ replica/worker/consumer.
2. Kiểm tra readiness và smoke test.
3. Đối chiếu expected/actual changeset set.
4. Ghi schema milestone và application deployment result.
5. Kiểm tra không còn consumer cũ trước contract migration.
6. Lưu manifest, log và audit record để truy vết.

## 19. Những lỗi vận hành thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| App 3.8 lỗi thiếu cột dù release đã deploy | Migration chưa chạy, chạy nhầm DB hoặc bị filter | Xác minh URL, root changelog, status và schema |
| DATABASECHANGELOG mới hơn app đang chạy | Migration job chạy trước rollout hoặc app rollback | Kiểm tra compatibility matrix và deployment event |
| App version giống nhau nhưng DB khác nhau | Lịch sử/nhánh/artifact khác hoặc drift | So sánh digest, manifest, identity và schema |
| Changelog history khớp nhưng app vẫn lỗi | Schema drift, dữ liệu sai hoặc app mapping khác | Kiểm tra catalog/data và artifact |
| Tag schema đúng nhưng app chưa rollout | Tag được ghi ở bước migration trước rollout | Xem deployment state riêng |
| Pending changeset ngoài release | Root changelog mới hơn, context/filter khác hoặc nhánh khác | So sánh artifact và manifest, không update tùy tiện |
| Checksum mismatch | Changeset đã chạy bị sửa hoặc version khác | Đối chiếu artifact/commit, giữ history |
| Một số replica lỗi sau contract migration | Replica cũ vẫn dùng schema cũ | Điều phối rollout và kiểm tra consumer trước contract |
| App rollback nhưng DB không rollback | Hai quy trình có vòng đời riêng | Xác nhận app/schema compatibility trước hành động |
| Nhiều service dùng chung schema | Chỉ kiểm tra version của một service | Lập ma trận cho mọi consumer |
| Deployment record báo success nhưng migration lỗi | Record được ghi quá sớm hoặc không có trạng thái trung gian | Ghi event STARTED/FAILED/PARTIAL/SUCCEEDED đúng thời điểm |
| History có MARK_RAN nhưng app mong object tồn tại | Changeset được đánh dấu mà hiệu ứng thực tế chưa được xác minh | Kiểm tra schema và điều kiện baseline, không chỉ đọc EXECTYPE |

## 20. Bài thực hành: đối chiếu release với database history

**Bối cảnh:** customer-service chuẩn bị phát hành 3.8.0. Release manifest yêu cầu hai changeset DB-401 và DB-417, cùng schema milestone **customer-schema-3.8-expand**. Có ba môi trường dev, staging và production.

### Bước 1. Xác định artifact

Ghi application version, commit, image digest, changelog root, Liquibase version và migration artifact. Xác nhận changelog trong artifact là đúng commit đã review.

### Bước 2. Lấy actual history

Trên từng database lab/môi trường được phép, truy vấn DATABASECHANGELOG và lưu ID, AUTHOR, FILENAME, MD5SUM, EXECTYPE, thời gian và tag. Không sửa record.

### Bước 3. So sánh expected và actual

Lập bảng:

| Changeset | Manifest | Dev | Staging | Production |
|---|---|---|---|---|
| DB-401 | Required | EXECUTED | EXECUTED | EXECUTED |
| DB-417 | Required | EXECUTED | EXECUTED | Pending |

Kết quả này cho thấy production chưa đạt tập changeset yêu cầu. Trước khi rollout app 3.8.0, phải xác định nguyên nhân và chạy migration theo quy trình được duyệt.

### Bước 4. Kiểm tra schema milestone

Xác nhận tag/schema state trên từng database. Không dùng tag thay cho kiểm tra actual changesets hoặc schema. Nếu tag đã có nhưng DB-417 thiếu, điều tra vì sao mốc lịch sử không khớp manifest.

### Bước 5. Kiểm tra compatibility

Giả sử app 3.7.4 đang chạy ở production. Xác nhận changeset DB-417 chỉ thêm cột nullable và app 3.7.4 tương thích. Nếu migration xóa cột cũ, dừng rollout và thiết kế giai đoạn expand–migrate–contract.

### Bước 6. Chạy migration và hậu kiểm

Chạy migration job với artifact đã duyệt, kiểm tra history, schema và dữ liệu. Sau đó rollout app 3.8.0, xác nhận mọi replica đã chuyển version và ghi deployment success.

### Bước 7. Mô phỏng lỗi rollout

Cho migration thành công nhưng cố ý làm một replica app 3.8.0 không ready. Ghi nhận trạng thái database và application fleet. Thực hiện rollback binary về 3.7.4 nếu compatibility cho phép, giữ history Liquibase đúng thực tế và ghi deployment event thất bại/rollback.

**Tiêu chí hoàn thành:** giải thích được vì sao application version không bằng schema version; đối chiếu expected/actual changesets bằng identity; xác định schema compatibility khi rolling deployment; giữ lịch sử và release record chính xác khi rollout thất bại.

## 21. Checklist đối chiếu application version và Liquibase history

- [ ] Application artifact có version, commit và digest có thể truy vết.
- [ ] Changelog/migration artifact được liên kết với đúng application release.
- [ ] Root changelog và Liquibase version được ghi nhận.
- [ ] Expected changesets được xác định bằng ID, author và logical path.
- [ ] Actual history được đọc từ đúng database/schema metadata.
- [ ] Checksum và EXECTYPE được kiểm tra, không chỉ đếm số changeset.
- [ ] validate, status --verbose, history và SQL preview chạy với đúng cấu hình.
- [ ] Tag được dùng như schema milestone, không bị coi là application version.
- [ ] Schema thực tế và dữ liệu được đối chiếu để phát hiện drift.
- [ ] Có compatibility matrix cho mọi phiên bản app đang chạy.
- [ ] Rolling deployment không contract object khi còn consumer cũ.
- [ ] Nhiều service/worker dùng chung database được đưa vào ma trận.
- [ ] Migration job và application rollout có deployment ID liên kết.
- [ ] Release ledger ghi trạng thái STARTED/FAILED/PARTIAL/SUCCEEDED đúng thời điểm.
- [ ] Rollback application được đánh giá độc lập với rollback database.
- [ ] Sau release đã kiểm tra toàn bộ replica, readiness, history và schema.
- [ ] Không sửa/xóa/đánh dấu thủ công record DATABASECHANGELOG để ép version khớp.
- [ ] Manifest, artifact, log và audit record được lưu theo chính sách.

**Kết luận:** đối chiếu lịch sử Liquibase với phiên bản ứng dụng là việc liên kết hai dòng thời gian độc lập: artifact đang chạy và changeset đã áp dụng trên database. DATABASECHANGELOG cho biết identity, checksum và trạng thái migration; build metadata và deployment ledger cho biết binary, commit và lần rollout. Hãy liên kết chúng bằng release manifest, schema milestone và deployment ID, sau đó kiểm tra compatibility giữa mọi phiên bản ứng dụng đang chạy với schema thực tế. Cách làm này giúp phát hiện sớm migration bị thiếu, schema drift, artifact không nhất quán và rủi ro khi rolling deployment hoặc rollback.

