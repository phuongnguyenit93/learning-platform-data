# Giữ changelog dễ tái tạo khi có tham số và giá trị mặc định

## 1. Mục tiêu và phạm vi

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase giúp quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Việc thực hành bao gồm migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Bài thuộc chương **Tham số hóa**, tập trung vào câu hỏi: **làm thế nào dùng tham số và giá trị mặc định mà vẫn giữ changelog có thể tái tạo, kiểm tra và triển khai nhất quán?**

Tham số hóa cho phép một changelog phục vụ nhiều môi trường; nhưng nếu môi trường chọn các giá trị khác nhau một cách ngầm định, cùng một tệp có thể tạo ra các đối tượng hoặc dữ liệu khác nhau. Mục tiêu không phải loại bỏ mọi khác biệt môi trường mà là kiểm soát rõ những khác biệt được cho phép, cố định những giá trị thuộc lịch sử migration và ghi nhận bộ cấu hình thực sự được dùng.

Sau bài học, bạn có thể:

- Phân biệt tham số thay thế trong changelog, cấu hình runtime và giá trị mặc định ở cấp database.
- Xác định tham số nào phải cung cấp tường minh, tham số nào được phép có default và tham số nào phải bất biến.
- Viết changeset có property substitution mà vẫn dễ review, dự đoán SQL và kiểm soát rollback.
- Hiểu rủi ro khi đổi property đối với checksum, DATABASECHANGELOG và database đã triển khai.
- Lập quy trình kiểm chứng hai đường đi: tạo database mới và nâng cấp database đã có lịch sử.

## 2. Thế nào là một changelog tái tạo được?

Changelog tái tạo được khi nhóm có thể xác định **phiên bản migration**, **đầu vào triển khai**, **môi trường đích**, **thứ tự changeset** và **kết quả mong đợi**. Cần phân biệt hai tình huống:

1. **Dựng database từ đầu:** chạy toàn bộ changeset áp dụng được từ trạng thái nền đã biết.
2. **Nâng cấp database hiện hữu:** Liquibase đối chiếu changelog với bảng **DATABASECHANGELOG**, xác định changeset chưa chạy và kiểm tra lịch sử.

Một changelog giống hệt về nội dung không đủ bảo đảm kết quả giống hệt nếu tham số, DBMS, dữ liệu đầu vào hoặc bộ lọc changeset khác nhau.

| Đầu vào | Tác động lên khả năng tái tạo |
|---|---|
| Git commit và changelog gốc | Quyết định những changeset nào thuộc lần triển khai |
| Các tệp include, SQL, dữ liệu CSV | Quyết định nội dung phụ thuộc được đọc |
| Giá trị property đã resolve | Có thể thay đổi tên schema, tên đối tượng, SQL hoặc dữ liệu |
| Phiên bản Liquibase/DBMS/driver | Ảnh hưởng cú pháp SQL và hỗ trợ DDL |
| Context, label, dbms filter | Quyết định tập changeset được chạy |
| Database ban đầu và dữ liệu hiện có | Ảnh hưởng precondition, constraint và backfill |
| Lịch sử DATABASECHANGELOG | Quyết định changeset được xem là đã triển khai |
| Timezone, collation, default database | Có thể ảnh hưởng kết quả dữ liệu và so sánh |

Mục tiêu thực tế là **tái tạo có điều kiện**: nếu những đầu vào có ý nghĩa giống nhau thì kết quả logic có thể giải thích và kiểm chứng; nếu khác biệt đã được cho phép thì phải biết rõ chúng khác ở đâu.

## 3. Property substitution trong Liquibase

Liquibase hỗ trợ tham chiếu **changelog parameter** bằng cú pháp placeholder:

~~~text
${propertyName}
~~~

Khi xử lý changelog, Liquibase tìm giá trị property tương ứng từ nguồn cấu hình được hỗ trợ rồi dùng trong phần khai báo có tham chiếu. Property có thể nằm trong changelog hoặc được cung cấp từ công cụ triển khai, ví dụ CLI hay cơ chế cấu hình Spring Boot.

Ví dụ một property **cố định theo nghiệp vụ**:

~~~yaml
databaseChangeLog:
  - property:
      name: initialOrderStatus
      value: NEW

  - changeSet:
      id: 2026-11-19-001
      author: schema-team
      changes:
        - createTable:
            tableName: purchase_order
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: status
                  type: VARCHAR(20)
                  defaultValue: "${initialOrderStatus}"
                  constraints:
                    nullable: false
~~~

Trong ví dụ, property **initialOrderStatus** có giá trị NEW. Khi changeset được thực thi, Liquibase sử dụng giá trị này khi tạo default cho cột status. Đây là giá trị thuộc ý nghĩa của migration, nên phải được giữ ổn định ở những môi trường dự kiến có cấu trúc và quy tắc nghiệp vụ tương đương.

Chú ý: **property không phải bind parameter của prepared statement**. Nếu property được đặt trực tiếp vào SQL tùy chỉnh, giá trị có thể trở thành một phần cú pháp SQL. Cần kiểm tra định dạng, tập giá trị được phép và nguồn cung cấp.

### Ba lớp cấu hình thường bị nhầm

| Lớp | Ví dụ | Vai trò |
|---|---|---|
| Changelog property | ${targetSchema}, ${initialOrderStatus} | Giá trị được thay thế trong nội dung changelog |
| Cấu hình runtime | URL kết nối, changelog root, default schema, context/label | Quyết định Liquibase kết nối đâu và thực thi thế nào |
| Database default | defaultValue, defaultValueBoolean, DEFAULT CURRENT_TIMESTAMP | Hành vi của database khi tạo hoặc cập nhật bản ghi phù hợp |

Một property được thay thế khi xử lý changelog **không có nghĩa** database tiếp tục tham chiếu property đó ở mỗi lần INSERT sau này. Database vận hành theo định nghĩa DDL thực tế đã được áp dụng.

## 4. Chọn tham số và default theo mức độ thay đổi

### 4.1. Giá trị thuộc lịch sử migration

Những giá trị xác định nghĩa nghiệp vụ của thay đổi, như trạng thái mặc định ban đầu, mã dữ liệu chuẩn, tên constraint hoặc quy tắc seed, phải được review cùng changeset.

Ví dụ: initialOrderStatus = NEW.

**Quy tắc:** nếu nghiệp vụ đổi default thành PENDING ở một phiên bản sau, tạo **changeset mới** để điều chỉnh default của schema. Không sửa property hoặc nội dung changeset cũ đã chạy.

### 4.2. Giá trị khác theo môi trường

Đây là các giá trị hạ tầng mà dự án thực sự cho phép khác nhau, như tên schema đích hoặc catalog đích. Ví dụ targetSchema có thể là shop_dev, shop_stage, shop_prod.

**Quy tắc:** truyền tường minh, kiểm tra hợp lệ, ghi nhận giá trị đã chạy và bảo đảm các khác biệt này không làm thay đổi logic nghiệp vụ.

### 4.3. Giá trị vận hành và bí mật

URL, tài khoản kết nối, password, token hoặc secret phục vụ vận hành. Chúng nên được cấp qua secret manager hay cơ chế cấu hình triển khai thích hợp.

**Quy tắc:** không chèn secret vào changelog, tệp SQL, dữ liệu seed hoặc log SQL dự kiến.

### 4.4. Giá trị bắt buộc không có default

Những tham số chọn mục tiêu production hoặc phạm vi cập nhật/xóa dữ liệu nên được xem là bắt buộc. Ví dụ, nếu pipeline quên targetSchema mà changelog tự dùng mặc định shop_dev, lệnh update có thể nhắm sai schema thay vì thất bại sớm.

**Quy tắc:** với tham số nguy hiểm nếu bị bỏ quên, kiểm tra sự hiện diện, định dạng và allowlist **trước khi gọi Liquibase**. Không giả định mọi phiên bản hoặc mọi dạng khai báo sẽ tự xử lý placeholder còn thiếu theo đúng chính sách triển khai của dự án.

## 5. Quy tắc thiết kế giá trị mặc định

**Default tốt** là default có lý do rõ ràng và tạo ra hành vi mong muốn khi người thực thi không truyền giá trị.

Default phù hợp khi:

- Giá trị là hằng số nghiệp vụ của changeset, giống nhau ở các môi trường.
- Giá trị chỉ áp dụng ở môi trường local và được chứa trong cấu hình local có phạm vi rõ.
- Mọi lần chạy với default đều an toàn, đã kiểm chứng và không đổi đích triển khai ngoài ý muốn.
- Người review hiểu default sẽ ảnh hưởng SQL hoặc dữ liệu như thế nào.

Default không phù hợp khi:

- Chọn database hoặc schema production.
- Quyết định tenant, tổ chức, vùng dữ liệu hoặc quyền truy cập.
- Bật xóa dữ liệu, backfill lớn hay lựa chọn tập bản ghi nhạy cảm.
- Thay thế một tham số thực chất cần được người vận hành xác nhận.
- Mang giá trị biến động theo thời gian nhưng lại được gắn vào changeset lịch sử.

Đặc biệt, **không dùng một property có hai nghĩa**: lúc là mặc định local, lúc là lựa chọn production, lúc lại là biến thay đổi logic nghiệp vụ. Điều này khiến quá trình kiểm tra khó xác định một giá trị sai nằm ở cấu hình, trong changelog hay trong lịch sử database.

## 6. Ví dụ: một changelog cho nhiều schema

Giả sử ứng dụng có schema shop_dev, shop_stage và shop_prod. Mỗi môi trường cần cùng cấu trúc bảng và mã trạng thái chuẩn; chỉ có **schema đích** được khác.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-002
      author: schema-team
      comment: Tạo bảng trạng thái đơn hàng trong schema được cấu hình
      changes:
        - createTable:
            schemaName: "${targetSchema}"
            tableName: order_status_catalog
            columns:
              - column:
                  name: code
                  type: VARCHAR(30)
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: description
                  type: VARCHAR(255)
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            schemaName: "${targetSchema}"
            tableName: order_status_catalog

  - changeSet:
      id: 2026-11-19-003
      author: schema-team
      comment: Nạp dữ liệu chuẩn
      changes:
        - insert:
            schemaName: "${targetSchema}"
            tableName: order_status_catalog
            columns:
              - column:
                  name: code
                  value: NEW
              - column:
                  name: description
                  value: Đơn hàng mới
        - insert:
            schemaName: "${targetSchema}"
            tableName: order_status_catalog
            columns:
              - column:
                  name: code
                  value: COMPLETED
              - column:
                  name: description
                  value: Đã hoàn thành
      rollback:
        - delete:
            schemaName: "${targetSchema}"
            tableName: order_status_catalog
            where: "code IN ('NEW', 'COMPLETED')"
~~~

Các quyết định quan trọng:

1. **targetSchema** là required parameter được cung cấp bên ngoài, không có default chung cho staging/production.
2. **NEW** và **COMPLETED** là giá trị seed nghiệp vụ ổn định, không cần biến thành tham số riêng nếu chúng phải giống nhau ở mọi môi trường.
3. DDL và dữ liệu được chia thành hai changeset, giúp review tác động và rollback độc lập.
4. Schema đích phải tồn tại trước, hoặc được tạo bằng một migration có phạm vi được review.
5. Tài khoản Liquibase phải có đủ quyền trên schema thực tế.

Lưu ý: ví dụ là một mô hình thiết kế; từng DBMS có thể tạo SQL và xử lý rollback khác nhau. Trước triển khai cần chạy xem SQL dự kiến trên đúng loại database.

### Rủi ro khi thay đổi targetSchema giữa update và rollback

Nếu update chạy với targetSchema=shop_stage nhưng rollback về sau lại có targetSchema=shop_dev, phần rollback được resolve với **giá trị hiện tại** có nguy cơ nhắm sai schema.

Bởi vậy, bộ tham số ảnh hưởng tên đối tượng cần được **gắn chặt với lịch sử triển khai** và được lưu ở manifest. Không đổi đích schema cho một database đã có lịch sử migration rồi kỳ vọng Liquibase sẽ tự di chuyển toàn bộ đối tượng.

## 7. Cung cấp property từ đâu?

Nên xác định một nguồn sở hữu cho từng loại tham số:

| Nguồn | Nội dung khuyến nghị | Lưu ý |
|---|---|---|
| Changelog | Hằng số nghiệp vụ cần giữ nguyên trong lịch sử | Version hóa cùng mã migration |
| Cấu hình local | Tên schema và database local | Chỉ áp dụng trong môi trường phát triển |
| Cấu hình CI/CD | Tên schema đích, context/label, giá trị không bí mật | Kiểm tra trước deploy và ghi vào manifest |
| Secret manager | Credential, token và thông tin bảo mật | Không ghi ra changelog hoặc SQL |
| Manifest phát hành | Artifact, DBMS, tham số đã dùng (không bí mật) | Dùng để kiểm tra và tái hiện điều kiện triển khai |

Ví dụ truyền changelog parameter qua CLI trong các phiên bản hỗ trợ tùy chọn -D:

~~~bash
liquibase -DtargetSchema=shop_stage --changelog-file=db/changelog/db.changelog-master.yaml update-sql
~~~

Câu lệnh minh họa cách cấp giá trị; tên cờ, cách nạp file properties và thứ tự ưu tiên giữa các nguồn cấu hình cần được xác nhận theo phiên bản Liquibase thực tế. Cần kiểm tra SQL sinh ra để chắc chắn **targetSchema** đã được resolve thành shop_stage.

**Không định nghĩa trùng một property trong nhiều nguồn rồi dựa vào giả định chưa kiểm chứng về thứ tự ghi đè.** Thói quen an toàn là lập hợp đồng tham số, quy định nguồn sở hữu, kiểm tra giá trị thực tế trước khi update và ngăn config local thấm vào production.

## 8. Property khác DEFAULT của cơ sở dữ liệu

Ví dụ:

~~~yaml
databaseChangeLog:
  - property:
      name: initialStatus
      value: NEW
  - changeSet:
      id: 2026-11-19-004
      author: schema-team
      changes:
        - addColumn:
            tableName: purchase_order
            columns:
              - column:
                  name: status
                  type: VARCHAR(20)
                  defaultValue: "${initialStatus}"
~~~

Khi chạy, Liquibase resolve initialStatus và tạo thay đổi tương ứng. Database sau đó giữ giá trị mặc định theo DDL đã được áp dụng. Nếu initialStatus bị đổi thành PENDING trong changelog cũ, database đã triển khai **không tự đổi default** chỉ vì nội dung tệp thay đổi. Trên database mới, lịch sử đã bị sửa có thể tạo kết quả khác.

Muốn đổi default theo nghiệp vụ, cần một **changeset mới** điều chỉnh default của cột. Nếu cần cập nhật dữ liệu đã có, tạo kế hoạch backfill riêng.

Liquibase cũng hỗ trợ cách biểu diễn mặc định theo kiểu dữ liệu, tùy change type và DBMS:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-005
      author: schema-team
      changes:
        - addColumn:
            tableName: account_profile
            columns:
              - column:
                  name: enabled
                  type: BOOLEAN
                  defaultValueBoolean: true
              - column:
                  name: retry_count
                  type: INT
                  defaultValueNumeric: 0
~~~

Mặc định là biểu thức database, ví dụ CURRENT_TIMESTAMP, có thể cần cơ chế như defaultValueComputed theo DBMS. **Giá trị mặc định cho dòng mới không đồng nghĩa tự động backfill mọi dòng đã có một cách giống nhau trên mọi hệ quản trị.** Phải kiểm tra SQL sinh ra và tác động lên dữ liệu hiện tại.

## 9. Những nguồn gây kết quả không xác định

### 9.1. Giá trị thời gian

CURRENT_TIMESTAMP hoặc NOW() cho kết quả khác nhau giữa các lần tạo database. Điều này có thể đúng đối với timestamp mang nghĩa “thời điểm tạo tại môi trường này”, nhưng không phù hợp với bản ghi seed cần có thời điểm lịch sử cố định.

Cần xác định ý nghĩa dữ liệu trước khi chọn biểu thức default, tránh dùng thời gian triển khai thay cho mốc nghiệp vụ.

### 9.2. ID sinh ngẫu nhiên

UUID ngẫu nhiên và sequence có thể tạo mã khác nhau giữa môi trường. Nếu các bảng khác hoặc hệ thống ngoài tham chiếu đến ID seed, cân nhắc mã nghiệp vụ ổn định.

### 9.3. Dữ liệu đầu vào và precondition

Backfill được tính từ dữ liệu hiện có sẽ khác nhau khi số lượng khách hàng hay trạng thái giao dịch ở mỗi môi trường khác nhau. Điều cần tái tạo là **quy tắc biến đổi trên cùng đầu vào**, không phải yêu cầu staging phải có từng bản ghi giống production.

### 9.4. Tệp phụ thuộc ngoài changelog

Khi dùng sqlFile hoặc loadData, cần version hóa tệp SQL/CSV, cố định encoding, định dạng ngày tháng và đường dẫn tương đối. Cùng một changelog nhưng SQL phụ thuộc bị chỉnh ngoài Git sẽ tạo kết quả khác.

### 9.5. Context, label và DBMS

Nếu một changeset chỉ được chọn chạy trong context test, dữ liệu của test và production có thể khác nhau theo thiết kế. Cần ghi rõ bộ lọc ở manifest. Hãy dùng chức năng context/label chính thức thay vì thay thế cả đoạn SQL qua một property tự đặt nếu chỉ cần lọc changeset.

## 10. Checksum và lịch sử: vì sao không sửa property tùy tiện?

Liquibase nhận diện changeset bằng **id + author + đường dẫn changelog** (hoặc logicalFilePath). Sau khi chạy, nó ghi lịch sử trong **DATABASECHANGELOG** và sử dụng checksum để phát hiện một số dạng thay đổi nội dung đã triển khai.

Tham số hóa tạo ra hai rủi ro liên quan nhưng khác nhau:

- **Sai lệch nội dung:** giá trị property làm thay đổi SQL hoặc dữ liệu được tạo.
- **Sai lệch lịch sử:** changeset đã được ghi là đã chạy nhưng database không còn tương ứng với ý nghĩa migration tại thời điểm chạy.

Tùy change type, cách tính checksum và phiên bản Liquibase, thay đổi property có thể ảnh hưởng tới giá trị được kiểm tra hoặc tạo ra drift mà nhóm không phát hiện ngay qua checksum. Vì vậy, **không nên coi checksum là cơ chế xác nhận đầy đủ tính tương đương giữa hai môi trường**.

Quy tắc thực hành:

1. Giữ nguyên changeset và giá trị nghiệp vụ có tác động tới lịch sử sau khi đã triển khai.
2. Nếu cần điều chỉnh cấu trúc hoặc default, tạo changeset mới.
3. Không dùng runOnChange như cách mặc định để chạy lại DDL hoặc seed dữ liệu; chỉ sử dụng khi changeset được thiết kế an toàn cho việc chạy lại.
4. Không dùng clear-checksums để bỏ qua lỗi do sửa lịch sử.
5. Nếu thay đổi nguồn tham số hoặc cách resolve, kiểm tra trên bản sao database **có DATABASECHANGELOG cũ** trước khi triển khai.

**Tình huống:** một changeset tạo bảng trong schema shop_a, sau đó cùng database được chạy update lại với targetSchema=shop_b. Nếu định danh changeset vẫn như cũ và lịch sử cho biết changeset đã chạy, Liquibase không tự hiểu rằng cần tạo lại bảng trong schema mới. Đổi property **không phải** một migration chuyển schema.

## 11. Thiết kế rollback khi có tham số

Rollback là thao tác hoàn tác changeset đã triển khai; nó cần đúng đối tượng, đúng thứ tự và đúng trạng thái database.

Một rollback tham chiếu targetSchema sẽ được xử lý theo cấu hình hiện hành. Nếu giá trị này khác khi triển khai ban đầu, thao tác có thể chạm sai đối tượng. Tương tự, dùng property chọn tên index, bảng hay catalog cũng có rủi ro.

Để rollback đáng tin cậy:

- Ghi lại bộ tham số không bí mật trong manifest ứng với đúng database và release.
- Trước rollback, xác nhận schema/database đích và những changeset thực sự đã được ghi trong lịch sử.
- Tạo SQL rollback dự kiến khi công cụ và phiên bản hỗ trợ; review SQL trước khi chạy.
- Kiểm tra hiệu ứng mất dữ liệu, khả năng phục hồi dữ liệu cũ và phụ thuộc giữa thay đổi.
- Thử với bản sao database có dữ liệu, DBMS và lịch sử gần với môi trường cần rollback.
- Khi rollback phá hủy dữ liệu hoặc không an toàn, cân nhắc changeset mới theo hướng sửa tiến về phía trước (forward fix).

**Có rollback khai báo trong changelog không có nghĩa rollback luôn khôi phục được dữ liệu đã mất.** Ví dụ dropColumn có thể xóa dữ liệu cột; tạo lại cột không tự khôi phục dữ liệu đó.

## 12. Bảo mật và kiểm soát giá trị đầu vào

Property substitution không phải ràng buộc tham số an toàn như prepared statement. Ví dụ chống chỉ định:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: unsafe-demo
      author: demo
      changes:
        - sql:
            sql: "DELETE FROM customer WHERE tenant_id = ${tenantId}"
~~~

Nếu tenantId đến từ nguồn không tin cậy, chuỗi thay thế có thể làm thay đổi cú pháp hoặc phạm vi xóa. Đây là ví dụ về điều **không nên áp dụng** cho production.

Nên áp dụng:

- Kiểm tra tham số chọn schema, catalog, tên đối tượng bằng allowlist hoặc quy tắc identifier rõ ràng.
- Không nhận tham số migration nhạy cảm từ đầu vào người dùng hoặc nhánh CI không được tin cậy.
- Với dữ liệu chuẩn, ưu tiên change type có cấu trúc và literal được review.
- Không nội suy password, token hoặc secret vào SQL và tránh in toàn bộ tham số trong log.
- Với SQL phụ thuộc DBMS, giới hạn bằng dbms và kiểm tra ở đúng engine mục tiêu.

Cần phân biệt việc thay thế tại vị trí **identifier**, **data literal** và **đoạn SQL tự do**. Ba vị trí có quy tắc escape khác nhau; một phép thay chuỗi chung không bảo đảm an toàn cho cả ba.

## 13. Spring Boot: truyền property từ cấu hình ứng dụng

Spring Boot có khả năng tích hợp Liquibase khi khởi động ứng dụng. Ví dụ cấu hình dành cho **local**:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    parameters:
      targetSchema: shop_local
~~~

Thuộc tính **spring.liquibase.parameters** có thể cung cấp changelog parameters khi phiên bản Spring Boot/Liquibase sử dụng hỗ trợ cơ chế này. Trên staging và production, targetSchema phải được cấp theo cấu hình môi trường được review, không dùng default local chung.

Phân biệt:

- **change-log** chọn changelog gốc.
- **parameters** cung cấp biến được changelog tham chiếu.
- **default-schema** là cấu hình schema mặc định của Liquibase; không đương nhiên tương đương property tên targetSchema.
- **datasource** hoặc cấu hình kết nối riêng của Liquibase xác định database thực sự được kết nối.

Một sai lệch phổ biến: default schema của connection là A nhưng placeholder targetSchema lại resolve thành B. Nếu một số changeset chỉ định schemaName và các changeset khác bỏ trống schemaName, các thay đổi có thể rơi vào hai schema khác nhau.

Cần thống nhất chiến lược dùng schemaName tường minh hoặc mặc định, và kiểm chứng SQL thực tế.

## 14. Pipeline CI/CD để bảo đảm khả năng tái tạo

### Bước 1: xác nhận artifact

Chốt Git commit chứa changelog, tệp include, sqlFile/loadData và những thành phần cần thiết khác. Ghi nhận phiên bản Liquibase, driver, DBMS và các tùy chọn triển khai quan trọng.

### Bước 2: lập manifest triển khai

Ví dụ một bản ghi nội bộ để truy vết, **không phải định dạng cấu hình Liquibase bắt buộc**:

~~~yaml
deploymentId: release-2026-11-19-01
gitCommit: "<commit-da-kiem-chung>"
environment: staging
dbms: postgresql
liquibaseVersion: "<phien-ban-da-chot>"
changelog: db/changelog/db.changelog-master.yaml
contextFilter: "<bo-loc-da-chon>"
labelFilter: "<bo-loc-da-chon>"
parameters:
  targetSchema: shop_stage
~~~

Chỉ lưu những tham số được phép ghi nhận; secret không có mặt trong manifest.

### Bước 3: kiểm tra tham số bắt buộc

Pipeline phải dừng nếu targetSchema thiếu, rỗng, sai môi trường hoặc không thuộc allowlist. Đồng thời đối chiếu giá trị bất biến nghiệp vụ trong changelog; bảo đảm context và label đã được chấp thuận.

### Bước 4: xem SQL dự kiến

Khi kết nối và changelog đã được cấu hình, dùng quy trình kiểm tra điển hình:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
~~~

Kiểm tra xem tên schema đã resolve, SQL không còn placeholder ngoài ý muốn, không có secret bị chèn vào, dữ liệu seed giống thiết kế, precondition hợp lý và các changeset cũ không tự nhiên xuất hiện như pending.

Validate phát hiện những vấn đề được Liquibase hỗ trợ kiểm tra; **nó không thay thế review SQL hoặc kiểm tra nội dung database sau chạy**.

### Bước 5: kiểm chứng hai đường đi

1. **Database mới:** chạy changelog từ trạng thái nền xác định với bộ tham số dự kiến.
2. **Database có lịch sử:** nâng cấp bản sao môi trường đã từng chạy release trước để kiểm tra checksum, schema drift và tác động lên dữ liệu.

Sau đó thử chạy update lần hai với cùng cấu hình. Với changeset thông thường đã chạy, không nên có thay đổi mới; với runAlways/runOnChange, phải kiểm tra riêng hành vi lặp lại đã thiết kế.

### Bước 6: triển khai và xác minh

Sau khi review SQL và thông số đích, chạy update. Đối chiếu **DATABASECHANGELOG**, schema, dữ liệu và log. Lưu manifest để có bằng chứng tham số đã dùng khi cần điều tra hoặc rollback.

**Exit code 0 chưa đủ khẳng định có thể tái tạo** nếu config thực tế không được ghi nhận hoặc schema đã rơi vào sai vị trí.

## 15. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| Bảng được tạo vào schema sai | Pipeline dùng default local hoặc tham số bị ghi đè | Kiểm tra required parameter, allowlist và SQL trước deploy |
| Placeholder còn nguyên trong SQL | Tên property sai hoặc giá trị không được nạp | Kiểm tra nguồn cấu hình và cú pháp theo phiên bản |
| Changelog cũ lỗi checksum | Đã sửa changeset lịch sử hoặc nội dung ảnh hưởng checksum | Đối chiếu Git/lịch sử, dùng changeset mới cho thay đổi schema |
| Property đổi nhưng database không đổi | Changeset đã được ghi là đã chạy | Không kỳ vọng chạy lại tự động; tạo migration mới |
| Database mới có seed khác database cũ | Seed dựa timestamp, random ID hoặc property khác | Làm rõ mức tái tạo mong muốn và cố định dữ liệu chuẩn |
| Rollback chạm sai đối tượng | Property tên schema lúc rollback khác lúc update | Lấy đúng giá trị từ manifest và đối chiếu database |
| Local chạy tốt, production lỗi | DBMS, quyền hoặc trạng thái ban đầu khác | Kiểm tra SQL, quyền và precondition trên DBMS đích |
| Secret lộ trong log | Dùng property substitution chứa bí mật | Chuyển qua secret store, giới hạn log |
| Trùng tên property nhiều nguồn | Quy tắc ưu tiên không được quản lý | Chỉ định nguồn sở hữu và kiểm chứng giá trị resolve |
| Đổi default trong changelog không sửa DB cũ | Default là DDL đã áp dụng | Viết changeset mới điều chỉnh default |

## 16. Bài tập thực hành

Bạn có ba môi trường: local, staging, production. Ứng dụng dùng cùng changelog để quản lý bảng purchase_order. Yêu cầu:

- Schema lần lượt là orders_local, orders_stage và orders_prod.
- Cột status ban đầu có default NEW ở cả ba môi trường.
- Release tiếp theo muốn default PENDING nhưng **không backfill dữ liệu cũ**.
- Production phải từ chối chạy nếu không có tên schema đích.
- Có thể xem lại tham số đã dùng sau nhiều tháng.

**Câu hỏi:**

1. Tham số nào phải truyền theo môi trường và không nên có default chung?
2. Giá trị nào nên được cố định trong changeset lịch sử?
3. Có nên sửa property initialStatus=NEW thành PENDING trong changeset cũ không?
4. Những thông tin nào cần ghi vào manifest?
5. Cần kiểm chứng gì ở database mới và database đã chạy phiên bản trước?
6. Rủi ro nào xuất hiện nếu rollback dùng targetSchema khác lúc update?

**Hướng giải:**

- targetSchema là required parameter từ deployment, có allowlist rõ.
- NEW là default nghiệp vụ của changeset đầu tiên, bất biến giữa môi trường.
- Release đổi sang PENDING cần changeset **mới** điều chỉnh default; không chỉnh sửa changeset cũ hoặc vô tình update mọi bản ghi hiện tại.
- Manifest ghi Git commit, Liquibase/DBMS version, context/label và targetSchema đã dùng; không chứa secret.
- Kiểm tra đường dựng database mới, đường nâng cấp database đã có DATABASECHANGELOG, SQL dự kiến và trạng thái schema sau triển khai.
- Rollback phải dùng đúng schema mà changeset ban đầu đã nhắm đến.

Một bài làm đạt yêu cầu phải giải thích được **vì sao chỉ thay đổi giá trị property không tương đương với phát hành một migration mới**.

## 17. Checklist trước khi phát hành

- [ ] Các property đã được phân loại thành hằng số nghiệp vụ, cấu hình môi trường hoặc secret.
- [ ] Các giá trị mặc định có mục đích, phạm vi và owner rõ ràng.
- [ ] Tham số quyết định đích production là required và được validate trước update.
- [ ] Không sửa ý nghĩa changeset đã chạy bằng cách thay property hoặc đổi default ngầm.
- [ ] Mỗi property có nguồn sở hữu xác định, tránh dựa vào thứ tự ghi đè mơ hồ.
- [ ] Changelog và mọi tệp SQL/CSV liên quan được version hóa đúng artifact.
- [ ] Đã kiểm tra SQL sinh ra với bộ tham số, DBMS, context/label thực tế.
- [ ] Đã thử trên database mới và database có lịch sử triển khai.
- [ ] Đã kiểm tra DATABASECHANGELOG và trạng thái schema sau chạy.
- [ ] Các thao tác rollback được đối chiếu với manifest của lần update.
- [ ] Secret không xuất hiện trong changelog, manifest công khai hoặc SQL log.

## 18. Ghi nhớ

**Tham số hóa tốt** giúp cùng một changelog hoạt động trong nhiều môi trường với những khác biệt được kiểm soát. **Giá trị mặc định tốt** giúp hành vi dự đoán được mà không che giấu tham số bắt buộc.

Ba nguyên tắc cốt lõi:

1. **Giữ lịch sử ổn định:** giá trị quyết định ý nghĩa migration đã chạy phải bất biến; thay đổi nghiệp vụ tạo changeset mới.
2. **Quản lý đầu vào:** tham số môi trường được cấp, kiểm tra và ghi nhận; secret không được nội suy vào SQL.
3. **Kiểm chứng bằng kết quả:** tái tạo được đánh giá qua SQL dự kiến, trạng thái database và DATABASECHANGELOG trên cả đường tạo mới lẫn nâng cấp.

Đó là cơ sở để triển khai thay đổi schema và dữ liệu qua Liquibase một cách dự đoán được, có thể kiểm toán và có kế hoạch rollback rõ ràng.
