# Checksum không hợp lệ sau chỉnh sửa hoặc nâng cấp

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, chúng ta học cách quản lý thay đổi schema và dữ liệu bằng **changelog, changeset, precondition, checksum và lịch sử triển khai**; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Checksum giúp Liquibase nhận ra một changeset đã được triển khai có nội dung khác với nội dung hiện tại. Khi checksum không khớp, Liquibase thường dừng validation để tránh tiếp tục với lịch sử migration không rõ ràng.

Bài học thuộc chương **Xử lý sự cố**, tập trung vào tình huống `Validation Failed` hoặc thông báo tương tự cho biết checksum của changeset đã lưu khác checksum Liquibase tính từ changelog hiện tại. Nguyên nhân có thể là ai đó sửa changeset cũ, thay file SQL được tham chiếu, di chuyển changelog, dùng artifact khác giữa các môi trường hoặc nâng cấp phiên bản Liquibase làm thay đổi cách tính checksum. Cần phân biệt các nguyên nhân này trước khi chọn cách xử lý, vì chúng có ý nghĩa và mức độ rủi ro khác nhau.

## 1. Checksum trong Liquibase là gì?

Checksum là giá trị Liquibase tính từ nội dung changeset theo quy tắc của phiên bản Liquibase đang chạy. Liquibase lưu giá trị này trong cột `MD5SUM` của bảng lịch sử `DATABASECHANGELOG` khi changeset được thực thi. Ở lần chạy sau, Liquibase tính lại checksum từ changeset hiện có và so sánh với giá trị lịch sử.

Mục đích là bảo vệ tính bất biến của lịch sử migration:

- Một changeset đã chạy được kỳ vọng giữ nguyên nội dung thực thi.
- Nếu nội dung thay đổi, Liquibase có thể phát hiện và yêu cầu người vận hành điều tra.
- Nhóm có thể phân biệt thay đổi mới (changeset mới) với việc sửa lại một thay đổi đã triển khai.
- Lịch sử giữa dev, test, staging và production có thể được đối chiếu dựa trên ID, author, filename và checksum.

Checksum không phải bản sao của toàn bộ file changelog. Liquibase tính theo nội dung changeset và các quy tắc riêng; một số khác biệt về định dạng hoặc metadata có thể được xử lý khác nhau theo loại changelog và phiên bản. Vì vậy, không tự tính MD5 của cả file rồi so sánh với MD5SUM.

## 2. Liquibase lưu checksum ở đâu?

Thông tin triển khai được lưu trong bảng DATABASECHANGELOG. Những cột thường hữu ích khi điều tra gồm:

| Cột | Ý nghĩa |
|---|---|
| ID | ID của changeset |
| AUTHOR | Author khai báo trong changeset |
| FILENAME | Đường dẫn changelog mà Liquibase dùng để nhận diện |
| MD5SUM | Checksum đã lưu |
| EXECTYPE | Kiểu thực thi được ghi nhận, chẳng hạn EXECUTED, RERAN hoặc MARK_RAN |
| DATEEXECUTED | Thời điểm ghi nhận thực thi |
| ORDEREXECUTED | Thứ tự thực thi trong lịch sử |
| DEPLOYMENT_ID | Nhận diện đợt triển khai nếu phiên bản/cấu hình có ghi trường này |

Tên bảng, schema và cách viết hoa/thường phụ thuộc cấu hình Liquibase và DBMS. Ví dụ truy vấn dưới đây dùng tên bảng mặc định:

```sql
SELECT
    id,
    author,
    filename,
    md5sum,
    exectype,
    dateexecuted,
    orderexecuted
FROM databasechangelog
WHERE id = 'DB-4821-add-customer-status'
  AND author = 'customer-platform';
```

Hãy xác minh database/schema đang kết nối trước khi đọc lịch sử. Một kết quả rỗng có thể có nghĩa là đang xem nhầm database, schema history được cấu hình ở nơi khác, hoặc changeset chưa từng được ghi nhận tại môi trường đó.

## 3. Đọc thông báo checksum mismatch

Thông báo có thể có dạng:

```text
Validation Failed:
  1 changesets check sum
  db/changelog/changes/DB-4821-add-customer-status.yaml::
  customer-platform::DB-4821-add-customer-status
  was: 8:OLD_CHECKSUM
  but is now: 8:NEW_CHECKSUM
```

Chi tiết chính:

- was: checksum đang được lưu trong DATABASECHANGELOG.
- but is now: checksum tính từ changeset hiện tại.
- Tiền tố trước dấu hai chấm là phiên bản định dạng/thuật toán checksum của Liquibase, không phải số phiên bản ứng dụng hay số thứ tự changeset.
- Phần ID, author và đường dẫn giúp xác định changeset cần điều tra.

Nếu hai checksum có cùng tiền tố nhưng phần giá trị khác nhau, nội dung được Liquibase tính checksum có thể đã thay đổi. Nếu tiền tố khác nhau, cần xem xét thay đổi phiên bản/cách tính checksum trước khi kết luận changelog bị sửa. Không thể chỉ nhìn hai chuỗi rồi khẳng định nguyên nhân.

## 4. Những nguyên nhân phổ biến

| Nguyên nhân | Dấu hiệu | Hướng xác minh |
|---|---|---|
| Sửa changeset đã triển khai | SQL/change type trong file khác với artifact cũ | So sánh commit và artifact đã phát hành |
| Sửa file sqlFile | YAML giữ nguyên nhưng SQL bên ngoài thay đổi | So sánh file được tham chiếu giữa các artifact |
| Thay đổi formatted SQL | Nội dung hoặc chỉ thị changeset khác | Review toàn bộ file SQL và parser version |
| Dùng artifact khác giữa môi trường | Cùng release nhưng checksum khác nhau | Đối chiếu commit, digest và nội dung gói triển khai |
| Di chuyển/đổi tên changelog | FILENAME hoặc đường dẫn logic khác | So sánh đường dẫn trong DATABASECHANGELOG với changelog hiện tại |
| Nâng cấp Liquibase | Tiền tố checksum hoặc kết quả tính thay đổi | Kiểm tra phiên bản cũ/mới và release notes |
| Thay dependency/extension | Parser hoặc custom change có hành vi khác | Đối chiếu classpath, extension và phiên bản |
| Chỉnh lịch sử thủ công | MD5SUM hoặc metadata không khớp artifact | Kiểm tra audit log và quyền ghi bảng lịch sử |

Một thay đổi định dạng có thể không ảnh hưởng checksum trong một số trường hợp, nhưng không nên dựa vào điều đó để chỉnh file cũ. Quy tắc checksum có thể khác theo changelog format và phiên bản. Luôn đối chiếu nội dung thực tế với artifact đã triển khai.

## 5. Quy trình điều tra an toàn

Trước khi chạy lệnh sửa trạng thái, giữ nguyên bằng chứng và trả lời lần lượt:

1. Lỗi xảy ra ở database nào, schema nào, trong job nào và với Liquibase version nào?
2. Changeset nào bị báo lỗi? Có bao nhiêu changeset mismatch?
3. Changeset đó đã được chạy ở môi trường nào và bằng artifact nào?
4. Nội dung hiện tại khác gì với commit/artifact đã triển khai?
5. Có thay đổi ở file SQL/CSV, include, property, extension hoặc logicalFilePath không?
6. Lỗi xuất hiện sau khi đổi nội dung hay ngay sau khi nâng cấp Liquibase?
7. Những môi trường khác có cùng checksum và cùng lịch sử không?

Không bắt đầu bằng clear-checksums, không sửa trực tiếp DATABASECHANGELOG, và không thêm một giá trị checksum mới chỉ để pipeline chạy qua. Những thao tác đó có thể làm mất dấu nguyên nhân ban đầu.

### 5.1. Thu thập phiên bản và cấu hình triển khai

Ghi lại:

- Phiên bản Liquibase thực tế của CLI hoặc dependency Spring Boot.
- JDBC driver và các extension/custom change được nạp.
- DBMS, phiên bản server và cấu hình schema history.
- Master changelog, các filter context/label/DBMS và property được truyền.
- Commit, tag, artifact digest và thời điểm phát hành.
- Lệnh hoặc job đã chạy, cùng thông báo lỗi đầy đủ.

Đừng chỉ xem phiên bản trong file build. CLI trên runner, plugin build và dependency runtime có thể không giống nhau. Cần xác định đúng binary/classpath thực thi lần migration lỗi.

### 5.2. Đối chiếu lịch sử trong DATABASECHANGELOG

Truy vấn đúng hàng theo ID và author, rồi đối chiếu FILENAME, MD5SUM, EXECTYPE và thời gian triển khai. Nếu cùng changeset có nhiều bản ghi do cấu hình hoặc lịch sử bất thường, cần kiểm tra đầy đủ thay vì chỉ lấy một dòng.

So sánh thông tin đó giữa các môi trường:

| Môi trường | Checksum đã lưu | Artifact/commit | Liquibase version |
|---|---|---|---|
| Dev | Ghi nhận | Ghi nhận | Ghi nhận |
| Test | Ghi nhận | Ghi nhận | Ghi nhận |
| Staging | Ghi nhận | Ghi nhận | Ghi nhận |
| Production | Ghi nhận | Ghi nhận | Ghi nhận |

Nếu production và staging có checksum khác nhau trong khi nhóm kỳ vọng cùng release, dừng phát hành tiếp theo cho đến khi giải thích được sự khác biệt.

## 6. Xác định changeset cũ có bị sửa hay không

Lấy đúng artifact đã chạy tại môi trường đang lỗi. Không dùng working tree hiện tại làm chuẩn nếu chưa chứng minh nó chính là artifact đã triển khai.

Kiểm tra:

- id, author, nội dung changes, SQL và thuộc tính của changeset.
- preConditions, rollback, runOnChange, runAlways, context và label.
- File được tham chiếu bởi sqlFile, loadData, loadUpdateData hoặc include.
- Đường dẫn file và logicalFilePath.
- Thay đổi do merge, rebase, cherry-pick hoặc conflict resolution.
- Khác biệt line ending/encoding và cách parser của phiên bản đang chạy xử lý file.

Nếu changeset đã được triển khai ở ít nhất một môi trường, hãy coi nó là bất biến. Một yêu cầu nghiệp vụ mới nên trở thành changeset mới, để mọi môi trường lần lượt áp dụng cùng một lịch sử.

### 6.1. Trường hợp chỉ sửa nội dung SQL

Ví dụ changeset cũ:

```yaml
databaseChangeLog:
  - changeSet:
      id: "DB-4821-add-customer-status"
      author: "customer-platform"
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: status
                  type: VARCHAR(20)
```

Nếu ai đó sửa VARCHAR(20) thành VARCHAR(40) sau khi changeset đã chạy, Liquibase có thể phát hiện checksum mismatch. Cách xử lý đúng thường là khôi phục nội dung cũ và thêm changeset mới dùng modifyDataType sau khi đánh giá DBMS, dữ liệu và tương thích ứng dụng.

Không sửa MD5SUM trong database để khớp nội dung mới. Làm vậy che mất việc database thực tế vẫn có thể đang ở kiểu cũ.

### 6.2. Trường hợp file SQL được tham chiếu bị thay đổi

Ví dụ YAML vẫn giữ nguyên:

```yaml
changes:
  - sqlFile:
      path: sql/DB-4900-backfill-customer.sql
      relativeToChangelogFile: true
```

Nhưng file DB-4900-backfill-customer.sql được chỉnh sau khi đã chạy. Phải so sánh cả SQL file giữa artifact cũ và mới. Một thay đổi ngoài YAML vẫn có thể làm thay đổi checksum hoặc hành vi thực thi theo cơ chế Liquibase của phiên bản/format tương ứng.

Đối với dữ liệu đã backfill, sửa SQL rồi chạy lại có thể ghi đè giá trị mới hoặc xử lý hàng lần thứ hai. Nếu cần sửa kết quả, tạo kế hoạch forward-fix có phạm vi và điều kiện rõ ràng.

## 7. Phân biệt checksum mismatch với thay đổi đường dẫn changelog

Liquibase dùng định danh changeset dựa trên id, author và đường dẫn changelog (hoặc đường dẫn logic). Nếu file được di chuyển hoặc đổi tên, Liquibase có thể xem changeset là một định danh mới chưa có trong lịch sử, thay vì chỉ báo checksum khác.

Đọc FILENAME trong DATABASECHANGELOG và so sánh với đường dẫn hiện tại. Nếu cần tái cấu trúc, logicalFilePath có thể giúp duy trì định danh logic trong các phiên bản/định dạng hỗ trợ, nhưng phải thử trên bản sao database có lịch sử thật.

Không đổi id, author hoặc đường dẫn logic để né lỗi. Không thêm một include mới trỏ tới cùng changeset với đường dẫn khác nếu chưa hiểu ảnh hưởng đến nhận diện và thứ tự thực thi.

## 8. Khi checksum mismatch xuất hiện sau khi nâng cấp Liquibase

Liquibase có thể thay đổi cách tính checksum giữa các phiên bản. Giá trị MD5SUM có tiền tố phiên bản checksum; tiền tố khác nhau có thể phản ánh cách tính mới. Một số phiên bản có thể tự xử lý việc nâng cấp checksum khi validation/update, trong khi một số tình huống hoặc thay đổi cụ thể cần quy trình xử lý có chủ đích.

Hãy thực hiện:

1. Ghi nhận chính xác phiên bản Liquibase cũ và mới.
2. Đọc release notes/migration notes cho thay đổi checksum, parser, changelog format và extension.
3. Dùng đúng artifact đã triển khai để thử trên bản sao database có DATABASECHANGELOG tương ứng.
4. Chạy validation và quan sát checksum được tính, thông báo lỗi và thay đổi metadata.
5. Kiểm tra checksum mismatch có xảy ra với nhiều changeset không, hay chỉ một changeset đã bị sửa.
6. Xác minh các extension/custom change và JDBC driver có tương thích với phiên bản mới.
7. Thống nhất một phiên bản Liquibase cho các bước CI, rehearsal và production.

Không kết luận mọi mismatch sau nâng cấp đều vô hại. Một lần nâng cấp có thể trùng thời điểm với việc sửa changelog; cần phân biệt hai nguyên nhân bằng artifact, commit và lịch sử cụ thể.

### 8.1. Tiền tố checksum không phải số phiên bản Liquibase

Ví dụ 8:... và 9:... thể hiện phiên bản cơ chế checksum, không cho biết chính xác Liquibase CLI đang là 8.x hay 9.x. Không dùng tiền tố này để suy ra phiên bản binary. Hãy lấy phiên bản từ chính CLI/runtime và đối chiếu release notes tương ứng.

### 8.2. Tránh nâng cấp Liquibase đồng thời với thay đổi changelog

Khi có thể, tách hai loại thay đổi:

- Release A: nâng Liquibase/driver/extension nhưng giữ nguyên changelog.
- Release B: thay đổi nội dung migration theo yêu cầu nghiệp vụ.

Cách tách này giúp xác định nguyên nhân khi checksum khác. Nếu phải kết hợp, cần rehearsal với đúng artifact và phiên bản mới trên bản sao lịch sử production, sau đó lưu kết quả đối chiếu.

## 9. Cách xử lý theo từng nguyên nhân

| Kết quả điều tra | Cách xử lý nên cân nhắc |
|---|---|
| Changeset cũ bị sửa ngoài ý muốn | Khôi phục nội dung từ artifact/commit đã triển khai; thêm changeset mới cho thay đổi cần thiết |
| SQL file tham chiếu bị sửa | Khôi phục file cũ; tạo tài nguyên mới và changeset mới cho logic mới |
| Artifact giữa môi trường khác nhau | Dừng rollout; xác định artifact chuẩn, digest và nguồn phát hành; triển khai cùng artifact đã xác minh |
| Chỉ khác đường dẫn file | Đối chiếu FILENAME; thử logicalFilePath theo phiên bản và format trước khi phát hành |
| Nâng cấp checksum có chủ đích | Thử theo hướng dẫn phiên bản trên bản sao; chỉ chuẩn hóa checksum sau khi xác minh nội dung không bị sửa |
| Changeset được thiết kế để thay đổi và chạy lại | Kiểm tra runOnChange, tính idempotent và tác động của lần chạy lại |
| Lịch sử bị sửa thủ công hoặc có dấu hiệu xâm nhập | Dừng triển khai, giữ bằng chứng, điều tra quyền và audit log cùng DBA/security |

Không chọn biện pháp dựa trên việc làm cho lệnh update hết báo lỗi. Điều cần khôi phục là sự nhất quán giữa **nội dung migration, lịch sử database và trạng thái schema/dữ liệu thực tế**.

## 10. Khôi phục changeset đã bị sửa ngoài ý muốn

Quy trình khuyến nghị:

1. Tạm dừng job Liquibase ở các môi trường bị ảnh hưởng.
2. Lưu thông báo lỗi, hàng DATABASECHANGELOG, artifact hiện tại và artifact đã triển khai.
3. Xác định commit cuối cùng chứa changeset đúng.
4. Khôi phục nguyên nội dung changeset và mọi file tài nguyên đã tham chiếu.
5. Kiểm tra id, author, FILENAME/logicalFilePath có trùng lịch sử hay không.
6. Chạy validate, status và SQL preview trên bản sao database.
7. Nếu cần thay đổi schema/dữ liệu, tạo changeset mới với ID mới và kế hoạch triển khai riêng.
8. Sau khi xác minh, phát hành lại artifact thống nhất cho các môi trường.

Nếu changeset cũ đã bị chạy bằng nội dung khác ở một môi trường, không thể chỉ khôi phục file rồi giả định mọi database giống nhau. Phải kiểm tra schema và dữ liệu thật ở từng môi trường; có thể cần migration bù để đưa chúng về cùng trạng thái.

## 11. clear-checksums dùng khi nào?

Lệnh clear-checksums xóa các giá trị checksum đã lưu trong DATABASECHANGELOG của database mục tiêu. Ở lần update tiếp theo, Liquibase tính lại checksum cho các changeset đã có lịch sử và ghi giá trị mới theo phiên bản/cấu hình hiện tại. Lệnh này tác động rộng tới lịch sử checksum của database, không chỉ một changeset được chỉ định.

Có thể cân nhắc khi:

- Nhóm đã xác minh nội dung changeset lịch sử là đúng.
- Nguyên nhân thực sự là thay đổi cơ chế checksum do nâng cấp Liquibase và quy trình phiên bản yêu cầu chuẩn hóa lại.
- Đã thử trên bản sao database có lịch sử tương đương.
- Có phê duyệt, cửa sổ triển khai và bản ghi trước/sau.

Không dùng chỉ vì:

- Có một changeset bị sửa ngoài ý muốn.
- Không biết artifact nào đã chạy.
- Muốn bỏ qua lỗi validation trong production.
- Muốn hợp thức hóa thay đổi SQL đã chạy nhưng chưa được review.

### 11.1. Ví dụ lệnh và phạm vi ảnh hưởng

Tùy phiên bản CLI, lệnh có thể được gọi như sau:

```bash
liquibase --defaults-file=liquibase.properties clear-checksums
```

Đây là lệnh **thay đổi metadata** của database mục tiêu. Kiểm tra url, defaultSchemaName, liquibaseSchemaName, credential và master changelog trước khi chạy. Không chạy thử trên production chỉ để xem phản ứng.

clear-checksums không phải lệnh sửa nội dung changeset, không sửa schema và không khôi phục dữ liệu. Nó cũng không chứng minh checksum mới là đúng. Vì phạm vi tác động rộng, không nên chạy nếu chỉ một changeset có vấn đề chưa được giải thích.

## 12. validCheckSum có phải cách sửa lỗi không?

Liquibase hỗ trợ khai báo checksum được chấp nhận cho changeset qua validCheckSum. Cơ chế này có thể hữu ích trong một số trường hợp có chủ đích, nhưng không phải biện pháp mặc định cho checksum mismatch.

Ví dụ minh họa cú pháp YAML (giá trị phải là checksum đã được xác minh của changeset cụ thể):

```yaml
databaseChangeLog:
  - changeSet:
      id: "DB-4821-add-customer-status"
      author: "customer-platform"
      validCheckSum: "8:VERIFIED_PREVIOUS_CHECKSUM"
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: status
                  type: VARCHAR(20)
```

Khi chấp nhận checksum cũ, Liquibase có thể coi checksum đó là hợp lệ theo khai báo. Điều này **không làm changeset đã chạy được thực thi lại** để áp dụng logic mới. Nếu thay đổi thực sự cần đổi schema hoặc dữ liệu, hãy tạo changeset mới.

Không dùng giá trị wildcard/ANY để chấp nhận mọi checksum trong môi trường production. Không thêm một checksum được đoán hoặc lấy từ môi trường không xác định. Nếu có lý do hợp lệ để chấp nhận nhiều checksum, phải ghi rõ artifact, phiên bản, môi trường, lý do và người phê duyệt.

## 13. runOnChange và runAlways khác gì?

Hai thuộc tính này là hành vi thực thi của changeset, không phải công cụ chữa mọi lỗi checksum:

| Thuộc tính | Hành vi | Trường hợp phù hợp |
|---|---|---|
| runOnChange: true | Chạy lại changeset khi nội dung làm checksum thay đổi theo quy tắc Liquibase | Định nghĩa view/procedure/function cần đồng bộ theo nội dung |
| runAlways: true | Chạy changeset mỗi lần Liquibase thực hiện update phù hợp | Tác vụ cần lặp lại có chủ đích và an toàn |
| Mặc định | Changeset đã chạy không tự chạy lại chỉ vì có lần update mới | Migration một lần như tạo bảng/thêm cột |

Ví dụ runOnChange:

```yaml
databaseChangeLog:
  - changeSet:
      id: "DB-5201-replace-customer-summary-view"
      author: "reporting-team"
      runOnChange: true
      changes:
        - createView:
            viewName: customer_summary
            replaceIfExists: true
            selectQuery: |
              SELECT id, status
              FROM customer
```

Ví dụ chỉ mang tính minh họa; cần xác minh change type và hỗ trợ replaceIfExists theo DBMS/phiên bản. Không dùng runOnChange cho migration dữ liệu không idempotent hoặc DDL có tác dụng phụ khó lặp lại. Một thay đổi nhỏ trong view có thể phù hợp, nhưng một changeset UPDATE cộng dồn số dư thường không phù hợp.

runAlways càng cần thận trọng vì nó được chạy lại ở mỗi lần update phù hợp. Nếu chỉ muốn sửa một changeset đã triển khai, đừng bật runAlways để che mismatch.

## 14. Quy trình kiểm chứng bằng lệnh Liquibase

Sau khi xác định nguyên nhân và có artifact cần thử, có thể dùng các lệnh sau. Cú pháp option có thể khác theo phiên bản CLI:

```bash
# Kiểm tra cấu trúc và một số quy tắc changelog
liquibase --defaults-file=liquibase.properties validate

# Xem changeset còn pending
liquibase --defaults-file=liquibase.properties status

# Sinh SQL dự kiến mà không thực thi migration
liquibase --defaults-file=liquibase.properties update-sql

# Xem lịch sử triển khai
liquibase --defaults-file=liquibase.properties history
```

Các lệnh này hỗ trợ kiểm tra, nhưng không thay thế việc đối chiếu artifact đã triển khai và trạng thái schema/dữ liệu. update-sql có thể vẫn gặp validation error trước khi sinh SQL; đó là tín hiệu cần điều tra tiếp, không phải lý do để tắt validation.

Một số phiên bản có lệnh tính checksum cho một changeset, thường được gọi là calculate-checksum. Cách truyền định danh changeset và khả năng của lệnh phụ thuộc phiên bản CLI. Dùng liquibase help calculate-checksum hoặc tài liệu đúng phiên bản đang cài để xác nhận cú pháp; không tự tạo checksum bằng MD5 ngoài Liquibase.

## 15. Những việc không nên làm để vượt qua checksum mismatch

Các cách sau có thể làm lịch sử khó tin cậy hoặc che giấu trạng thái database:

- Sửa trực tiếp MD5SUM trong DATABASECHANGELOG.
- Xóa hàng DATABASECHANGELOG để Liquibase chạy lại changeset.
- Chạy clear-checksums khi chưa xác định nguyên nhân và phạm vi.
- Thêm validCheckSum wildcard/ANY cho mọi changeset.
- Tắt validation hoặc bỏ qua lỗi bằng cấu hình toàn cục.
- Dùng changelog-sync/mark-next-changeset-ran để đánh dấu một thay đổi chưa thực thi là đã chạy.
- Sửa ID/author/path của changeset đã triển khai.
- Chỉnh SQL trong artifact production ngay trên runner mà không có commit/review.
- Rollback mù quáng chỉ để xóa lỗi checksum.

Nếu nghi ngờ bảng lịch sử bị chỉnh sửa trái phép, lưu bằng chứng, kiểm tra quyền database và audit log, sau đó phối hợp DBA/security. Không tự viết lại lịch sử để làm cho trạng thái hiển thị có vẻ hợp lệ.

## 16. Ma trận quyết định nhanh

| Tình huống đã xác minh | Hành động tiếp theo |
|---|---|
| Nội dung changeset cũ bị sửa nhưng schema đã triển khai đúng theo bản cũ | Khôi phục nội dung/artifact cũ; thêm changeset mới nếu cần thay đổi |
| File sqlFile cũ bị chỉnh | Khôi phục tài nguyên cũ; tạo SQL file và changeset mới |
| Chỉ khác artifact giữa môi trường | Dừng rollout, chọn artifact chuẩn và triển khai thống nhất sau khi đối chiếu |
| Chỉ khác đường dẫn | Đối chiếu FILENAME; thử duy trì logicalFilePath trên bản sao |
| Checksum thay đổi do nâng cấp phiên bản đã được xác nhận | Rehearsal theo hướng dẫn release; cân nhắc chuẩn hóa checksum có kiểm soát |
| Changeset view/procedure được thiết kế runOnChange | Xác minh thay đổi, tính an toàn khi chạy lại và behavior của DBMS |
| Changeset có checksum khác nhưng thay đổi chỉ được chấp nhận có chủ đích | Cân nhắc validCheckSum cụ thể sau review; xác nhận không cần chạy lại logic |
| Không xác định được nguồn gốc hoặc có dấu hiệu can thiệp | Dừng triển khai và điều tra; không thay đổi metadata để bỏ cảnh báo |

## 17. Phòng ngừa checksum mismatch trong nhóm

### 17.1. Giữ changeset đã triển khai bất biến

- Không sửa SQL, change type hoặc dữ liệu seed trong changeset đã chạy.
- Không thay file SQL/CSV được tham chiếu sau khi triển khai.
- Không đổi id, author, filename hoặc logicalFilePath tùy tiện.
- Yêu cầu mới được thêm thành changeset mới.
- Nếu cần thay view/procedure có chủ đích, cân nhắc runOnChange và quy tắc review riêng.

### 17.2. Dùng cùng artifact giữa các môi trường

Build một artifact từ commit đã review và dùng chính artifact đó để promote qua test, staging và production. Không build lại từ nhánh có thể thay đổi cho mỗi môi trường nếu mục tiêu là cùng một release. Ghi digest, commit và Liquibase version trong biên bản triển khai.

### 17.3. Pin phiên bản Liquibase và dependency

Quản lý nhất quán:

- Liquibase CLI hoặc dependency runtime.
- JDBC driver.
- Liquibase extension/custom change.
- Java runtime và cấu hình parser/resource accessor.
- Master changelog và các file resource.

Nâng cấp phiên bản cần có rehearsal trên bản sao lịch sử production, đọc release notes và kiểm tra checksum/validation trước khi áp dụng rộng.

### 17.4. Review các thay đổi lịch sử trong pull request

CI có thể cảnh báo khi pull request sửa file changelog cũ hoặc tài nguyên đã phát hành. Kết hợp CODEOWNERS, rule bảo vệ thư mục migration và quy trình phê duyệt. CI không tự biết chính xác changeset đã chạy ở mọi database; cần dữ liệu release/metadata phù hợp để phân biệt changeset mới với changeset lịch sử.

## 18. Tình huống thực hành: mismatch sau nâng cấp Liquibase

Giả sử staging báo:

```text
was: 8:ABC...
but is now: 9:XYZ...
```

Trong khi production chưa báo lỗi. Hãy xử lý trên bản sao staging:

1. Ghi phiên bản Liquibase đang chạy ở staging và production.
2. Xác nhận cả hai dùng cùng commit, artifact và file resource.
3. Truy vấn DATABASECHANGELOG để lấy ID, AUTHOR, FILENAME, MD5SUM, DATEEXECUTED.
4. Đối chiếu changeset và file SQL tham chiếu với artifact đã triển khai.
5. Kiểm tra release notes về checksum version, parser và extension.
6. Chạy validate, status bằng đúng Liquibase version mới trên bản sao.
7. Xác minh mismatch có xuất hiện ở các changeset khác không.
8. Nếu nội dung không bị sửa và nguyên nhân checksum version đã rõ, làm theo hướng dẫn nâng cấp tương ứng; chỉ cân nhắc clear-checksums sau rehearsal và approval.
9. Chạy update-sql và đối chiếu rằng không có migration nghiệp vụ mới ngoài dự kiến.
10. Lưu kết quả trước/sau, rồi mới lập kế hoạch promote phiên bản.

Nếu phát hiện file changeset khác với artifact production, dừng quy trình nâng cấp checksum và xử lý như một thay đổi nội dung ngoài dự kiến. Không dùng việc nâng cấp Liquibase để hợp thức hóa một chỉnh sửa chưa được giải thích.

## 19. Checklist xử lý sự cố checksum

- [ ] Ghi lại lỗi đầy đủ, changeset ID, author, filename và hai checksum.
- [ ] Xác minh database/schema và Liquibase version thực tế của job.
- [ ] Đọc hàng tương ứng trong DATABASECHANGELOG, không sửa trực tiếp.
- [ ] Đối chiếu artifact hiện tại với artifact/commit đã triển khai.
- [ ] Kiểm tra SQL/CSV được tham chiếu, include, property và logical file path.
- [ ] Xác định changeset đã chạy ở những môi trường nào.
- [ ] Phân biệt sửa nội dung, đổi đường dẫn, đổi dependency và nâng cấp checksum algorithm.
- [ ] Nếu nội dung cũ bị sửa ngoài ý muốn, khôi phục bản đã triển khai.
- [ ] Nếu cần thay đổi logic, tạo changeset mới hoặc dùng runOnChange đúng mục đích.
- [ ] Chỉ dùng validCheckSum cụ thể hoặc clear-checksums khi có nguyên nhân, thử nghiệm và approval rõ ràng.
- [ ] Không xóa hàng lịch sử, sửa MD5SUM bằng SQL hoặc tắt validation để bỏ qua lỗi.
- [ ] Chạy validate/status/update-sql trên bản sao có lịch sử tương đương.
- [ ] Xác nhận schema, dữ liệu và metadata nhất quán trước khi tiếp tục rollout.
- [ ] Lưu quyết định, bằng chứng, người phê duyệt và artifact digest.

**Kết luận:** checksum mismatch là tín hiệu cho biết nội dung changeset hiện tại và lịch sử Liquibase không còn khớp theo quy tắc checksum đang dùng. Hãy xác minh artifact, DATABASECHANGELOG, file SQL được tham chiếu, đường dẫn và phiên bản Liquibase trước khi hành động. Khôi phục changeset cũ nếu bị sửa ngoài ý muốn; dùng changeset mới cho thay đổi nghiệp vụ; chỉ chuẩn hóa checksum hoặc chấp nhận checksum cũ khi nguyên nhân đã rõ và được kiểm chứng. Cách xử lý có bằng chứng giúp quy trình DATABASE_SCHEMA_MIGRATION_LIQUIBASE giữ lịch sử triển khai đáng tin cậy qua nhiều môi trường và pipeline.
