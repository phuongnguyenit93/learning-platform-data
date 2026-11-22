# Nguyên tắc bảo vệ lịch sử và tránh sửa bảng theo dõi thủ công

## 1. Vì sao lịch sử Liquibase phải được bảo vệ?

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, Liquibase quản lý thay đổi schema và dữ liệu thông qua changelog, changeset, precondition, checksum và lịch sử triển khai. Các quy trình migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD đều dựa vào một nguồn thông tin quan trọng: **Liquibase ghi nhận những changeset nào đã được áp dụng vào database**.

Mỗi lần chạy `update`, Liquibase so sánh changelog hiện tại với bảng lịch sử. Từ đó, nó quyết định changeset nào còn pending, changeset nào đã chạy, changeset nào có checksum không còn khớp và có cần xử lý lại theo cấu hình hay không. Nếu một người tự sửa, xóa hoặc thêm bản ghi trong bảng lịch sử, Liquibase có thể hiểu sai trạng thái database.

Ví dụ:

- Xóa một bản ghi `DATABASECHANGELOG` khiến changeset đã chạy bị xem là chưa chạy; lần `update` sau có thể cố tạo lại bảng hoặc thêm lại cột.
- Thêm thủ công một bản ghi “đã chạy” cho changeset chưa từng áp dụng khiến Liquibase bỏ qua migration bắt buộc, trong khi schema thực tế vẫn thiếu đối tượng.
- Thay giá trị `MD5SUM` có thể che giấu việc nội dung changeset đã bị sửa.
- Đổi `FILENAME` làm thay đổi một phần bộ định danh, khiến cùng `id` và `author` có thể bị nhận diện như changeset khác.
- Sửa tag hoặc thời điểm thực thi có thể làm sai ranh giới rollback và báo cáo lịch sử.

Bài này giải thích cách Liquibase lưu và kiểm tra lịch sử, vì sao không nên thao tác trực tiếp trên các bảng metadata, cách xử lý checksum mismatch hoặc lock bằng cơ chế được hỗ trợ, và cách bảo vệ lịch sử trong pipeline triển khai.

**Nguyên tắc trung tâm:** bảng theo dõi là trạng thái vận hành do Liquibase quản lý. Hãy sửa nguyên nhân ở changelog, cấu hình hoặc quy trình triển khai; chỉ dùng các lệnh đồng bộ/repair được hỗ trợ khi có kế hoạch rõ ràng, không tự viết SQL để “sửa cho xanh”.

## 2. Hai bảng metadata có vai trò khác nhau

Liquibase thường sử dụng hai bảng metadata chính:

| Bảng | Vai trò | Dữ liệu quan trọng |
|---|---|---|
| `DATABASECHANGELOG` | Ghi nhận lịch sử changeset đã được xử lý trên database | ID, AUTHOR, FILENAME, MD5SUM, DATEEXECUTED, ORDEREXECUTED, EXECTYPE, TAG và các metadata khác |
| `DATABASECHANGELOGLOCK` | Điều phối việc chạy Liquibase đồng thời trên cùng database | Trạng thái LOCKED, thời điểm cấp khóa và tiến trình/máy giữ khóa |

Tên bảng và schema metadata có thể được cấu hình khác nhau theo dự án. Khi kiểm tra, phải xác nhận đúng database, catalog/schema và tên bảng Liquibase đang sử dụng. Không mặc định mọi môi trường đều có bảng metadata trong schema `public` hoặc schema mặc định.

### 2.1. DATABASECHANGELOG là lịch sử, không phải bản sao schema

`DATABASECHANGELOG` không lưu toàn bộ định nghĩa bảng, nội dung dữ liệu hay bản backup của database. Nó lưu dấu vết changeset Liquibase đã xử lý cùng một số metadata để nhận diện, kiểm tra và báo cáo.

Vì thế, hai điều sau đều có thể xảy ra:

- Lịch sử ghi changeset đã chạy, nhưng một DBA hoặc script bên ngoài đã sửa schema sau đó.
- Schema tình cờ có một bảng/cột giống kết quả mong muốn, nhưng Liquibase chưa ghi nhận changeset tương ứng.

Bảng lịch sử không chứng minh tuyệt đối schema hiện tại đúng. Cần kết hợp metadata với kiểm tra schema, dữ liệu và log vận hành.

### 2.2. DATABASECHANGELOGLOCK không phải nơi đánh dấu changeset

Bảng lock dùng để ngăn nhiều tiến trình Liquibase cùng cập nhật một database vào cùng thời điểm. Nó không lưu danh sách changeset đã chạy. Xóa bản ghi lịch sử để giải phóng lock là nhầm lẫn nghiêm trọng giữa hai trách nhiệm.

Nếu lock bị giữ sau một lần chạy lỗi, trước hết phải xác định có tiến trình migration nào còn hoạt động hay không. Lệnh `release-locks` có thể được dùng khi đã xác minh lock bị bỏ lại và không có tiến trình hợp lệ đang chạy; không nên sửa cột `LOCKED` bằng SQL thủ công khi chưa điều tra.

## 3. Những trường lịch sử cần hiểu

Một số cột thường gặp trong `DATABASECHANGELOG`:

| Cột | Ý nghĩa |
|---|---|
| `ID` | Giá trị `id` của changeset |
| `AUTHOR` | Giá trị `author` |
| `FILENAME` | Đường dẫn logic của changelog chứa changeset |
| `DATEEXECUTED` | Thời điểm Liquibase ghi nhận lần thực thi |
| `ORDEREXECUTED` | Thứ tự thực thi được ghi nhận |
| `EXECTYPE` | Loại xử lý, ví dụ `EXECUTED`, `MARK_RAN` hoặc `RERAN` |
| `MD5SUM` | Checksum Liquibase lưu cho changeset |
| `TAG` | Mốc tag được ghi trong lịch sử |
| `CONTEXTS` / `LABELS` | Thông tin context/label liên quan khi được ghi nhận |
| `DEPLOYMENT_ID` | Định danh đợt triển khai ở những phiên bản/cấu hình có trường này |

Cấu trúc cột có thể khác giữa các phiên bản Liquibase và cách cấu hình metadata. Hãy xem schema thật của bảng và tài liệu phiên bản đang sử dụng; không viết script giả định mọi cột luôn tồn tại.

### 3.1. Bộ định danh changeset

Liquibase nhận diện changeset theo bộ ba:

```text
(id, author, logical changelog file path)
```

Ví dụ:

```text
ID       = 010-create-customer
AUTHOR   = platform-team
FILENAME = db/changelog/changes/010-create-customer.yaml
```

Nếu di chuyển file sang thư mục khác hoặc đổi cách Liquibase nhận diện đường dẫn, thành phần `FILENAME` có thể đổi. Khi đó, dù `id` và `author` giữ nguyên, Liquibase có thể xem changeset là một định danh mới.

Vì vậy, sau khi changeset đã triển khai, không nên tùy tiện đổi tên hoặc di chuyển file. Nếu cần tổ chức lại cấu trúc, phải xem `FILENAME` lịch sử trên từng môi trường và sử dụng `logicalFilePath` ở phạm vi/cú pháp được phiên bản hỗ trợ để duy trì định danh logic phù hợp. Giá trị logic phải khớp chính xác lịch sử đã ghi; không tự đoán hoặc sửa bảng metadata để khớp với đường dẫn mới.

## 4. Checksum dùng để phát hiện thay đổi nội dung

Khi Liquibase xử lý changeset, nó tính checksum và lưu trong `MD5SUM`. Ở những lần chạy sau, Liquibase tính lại theo cơ chế của phiên bản hiện hành và so sánh với giá trị lịch sử. Nếu nội dung changeset đã áp dụng bị thay đổi theo cách ảnh hưởng checksum, Liquibase có thể báo lỗi checksum mismatch.

Checksum giúp phát hiện việc nội dung changeset đã thay đổi kể từ khi được ghi nhận. Nó **không phải chữ ký bảo mật mật mã**, không chứng minh ai đã sửa file và không xác nhận schema thực tế vẫn đúng. Nó cũng không phải hash đơn giản của toàn bộ byte trong file: cách chuẩn hóa/nội dung tham gia checksum phụ thuộc loại change và phiên bản Liquibase; không phải mọi thay đổi khoảng trắng hoặc chú thích đều nhất thiết làm checksum thay đổi.

### 4.1. Phân biệt identity và checksum

| Cơ chế | Câu hỏi | Khi thay đổi |
|---|---|---|
| Identity (`id` + `author` + file path) | Đây có phải changeset đã được ghi nhận không? | Có thể bị xem là changeset mới |
| Checksum (`MD5SUM`) | Nội dung của changeset đã nhận diện có còn khớp không? | Có thể phát sinh lỗi checksum hoặc hành vi chạy lại có chủ đích |

Ví dụ:

- Giữ nguyên identity nhưng sửa SQL tạo bảng đã chạy: checksum có thể không khớp.
- Giữ nguyên nội dung nhưng đổi `id`: identity khác, Liquibase có thể xem là changeset mới.
- Giữ nguyên `id` và `author` nhưng đổi đường dẫn logic: identity cũng có thể khác.

Đổi checksum không sửa được identity; đổi đường dẫn không phải cách sửa lỗi checksum. Phải xác định chính xác lớp vấn đề trước khi chọn biện pháp.

### 4.2. Checksum mismatch nói lên điều gì?

Một lỗi mismatch có thể xuất phát từ:

1. Người phát triển sửa một changeset đã triển khai.
2. Hai nhánh release mang nội dung khác nhau của cùng changeset.
3. Một nhóm thay đổi định nghĩa view/procedure có `runOnChange` nhưng nội dung được xử lý khác kỳ vọng.
4. Phiên bản Liquibase thay đổi cách tính/diễn giải checksum và cần đánh giá nâng cấp.
5. Một thay đổi cấu hình hoặc chỉnh sửa metadata trước đó làm lịch sử không còn phản ánh đúng nguồn.

Không nên lập tức chạy `clear-checksums` hoặc sửa `MD5SUM`. Trước tiên phải tìm changeset nào mismatch, so sánh source đã deploy, Git history/artifact, checksum được báo, DBMS và Liquibase version ở các môi trường.

## 5. Vì sao tuyệt đối tránh sửa DATABASECHANGELOG bằng SQL thủ công?

SQL trực tiếp trên bảng metadata có thể khiến Liquibase và database mất đồng bộ. Những thao tác cần tránh gồm:

| Thao tác thủ công | Hậu quả có thể xảy ra |
|---|---|
| `DELETE FROM DATABASECHANGELOG ...` | Changeset đã chạy bị coi là pending và có thể chạy lại |
| `INSERT INTO DATABASECHANGELOG ...` | Changeset chưa chạy bị đánh dấu như đã chạy, bỏ qua DDL/DML bắt buộc |
| `UPDATE MD5SUM ...` | Che giấu nội dung changeset khác với lịch sử |
| Sửa `ID` / `AUTHOR` / `FILENAME` | Làm sai định danh và quan hệ giữa changelog với lịch sử |
| Sửa `EXECTYPE` / `DATEEXECUTED` / `ORDEREXECUTED` | Làm sai báo cáo thứ tự và trạng thái triển khai |
| Sửa `TAG` | Có thể làm thay đổi ranh giới rollback |
| Xóa hoặc thêm dòng trong `DATABASECHANGELOGLOCK` | Có thể gây tranh chấp lock hoặc chạy đồng thời không an toàn |

### 5.1. Ví dụ rủi ro khi xóa một dòng lịch sử

Giả sử changeset `010-create-customer` đã tạo bảng `customer_account` và lịch sử đã ghi nhận. Một người xóa dòng tương ứng khỏi `DATABASECHANGELOG` vì nghĩ rằng cần “chạy lại cho chắc”.

Ở lần `update` tiếp theo, Liquibase có thể coi changeset là pending và cố thực hiện `CREATE TABLE customer_account` lần nữa. Kết quả có thể là lỗi “table already exists”, hoặc tệ hơn nếu changeset có thao tác không an toàn, tạo ra dữ liệu trùng hoặc trạng thái sai.

Việc xóa dòng lịch sử không xóa bảng đã tạo và cũng không hoàn tác dữ liệu. Nó chỉ làm mất bằng chứng Liquibase đã ghi nhận lần trước.

### 5.2. Ví dụ rủi ro khi tự thêm một dòng

Ngược lại, nếu một DBA tự thêm bản ghi `DATABASECHANGELOG` cho changeset `020-add-status-column` mà không thực hiện DDL, Liquibase có thể bỏ qua changeset. Ứng dụng sau đó truy cập cột `status_code` nhưng cột chưa tồn tại.

Đây là lý do không được tự tạo record “đã chạy” bằng SQL. Nếu database đã được tạo thủ công hoặc migration được áp dụng ngoài Liquibase, phải dùng quy trình baseline/synchronization được hỗ trợ và kiểm chứng schema thực tế.

### 5.3. Không sửa MD5SUM để che mismatch

Nếu thay `MD5SUM` bằng checksum mới hoặc một giá trị tùy ý, Liquibase có thể không còn cảnh báo rằng changeset lịch sử khác với file đang có. Nhưng schema thực tế vẫn có thể đang ở trạng thái của nội dung cũ. Việc “làm cho checksum khớp” không làm cho database tự nhận được thay đổi SQL chưa chạy.

Nếu cần chấp nhận một checksum đã biết trong trường hợp hợp lệ, dùng cơ chế `validCheckSum` trong changelog với giá trị cụ thể, lý do và review rõ ràng; không cập nhật cột checksum trực tiếp.

## 6. Cách xử lý changeset đã triển khai bị sửa

Quy tắc phổ biến nhất là **changeset đã triển khai phải được xem như bất biến**. Nếu cần thay đổi schema hoặc dữ liệu, hãy tạo changeset mới.

Ví dụ changeset cũ:

```yaml
databaseChangeLog:
  - changeSet:
      id: 010-create-customer
      author: platform-team
      changes:
        - createTable:
            tableName: customer_account
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
```

Nếu sau đó cần thêm cột `email`, hãy tạo changeset mới:

```yaml
databaseChangeLog:
  - changeSet:
      id: 020-add-customer-email
      author: platform-team
      changes:
        - addColumn:
            tableName: customer_account
            columns:
              - column:
                  name: email
                  type: varchar(320)
```

Đoạn thứ hai là changeset minh họa độc lập; trong changelog thực tế cần include theo đúng thứ tự hoặc đặt cùng một root file hợp lệ. Không quay lại sửa changeset 010 đã chạy để thêm cột.

### 6.1. Khi nào runOnChange phù hợp?

`runOnChange: true` cho phép changeset được thực thi lại khi nội dung ảnh hưởng checksum thay đổi, phù hợp với một số đối tượng có tính khai báo như view hoặc stored procedure, nếu thao tác thay thế được thiết kế an toàn.

Ví dụ:

```yaml
databaseChangeLog:
  - changeSet:
      id: 030-replace-customer-summary-view
      author: platform-team
      runOnChange: true
      changes:
        - createView:
            viewName: v_customer_summary
            replaceIfExists: true
            selectQuery: |
              SELECT id, email
              FROM customer_account
```

Cần hiểu rõ giới hạn:

- `runOnChange` không biến changeset thành nơi chứa mọi migration schema có thể sửa tùy ý.
- Thay đổi view có thể phá vỡ hợp đồng cột với ứng dụng cũ.
- Rollback của một changeset được chạy lại không tự lưu toàn bộ định nghĩa trước đó.
- Thay đổi chỉ khoảng trắng/chú thích có thể không làm checksum đổi tùy cơ chế xử lý.

Không dùng `runAlways` hoặc `runOnChange` để né checksum mismatch của một changeset tạo bảng, xóa dữ liệu hoặc thực hiện thao tác không idempotent.

### 6.2. Khi nào validCheckSum được cân nhắc?

`validCheckSum` cho phép khai báo checksum cụ thể mà changeset có thể chấp nhận trong các tình huống được hiểu rõ. Ví dụ có thể cần thiết khi một thay đổi đã triển khai chỉ được điều chỉnh ở phần nội dung không làm thay đổi kết quả database nhưng Liquibase vẫn cần chấp nhận checksum lịch sử cụ thể, hoặc khi có kế hoạch tương thích được review.

Nguyên tắc:

1. Xác định checksum thực tế trong lỗi/log hoặc bằng lệnh tính checksum được phiên bản hỗ trợ.
2. So sánh nội dung changeset trước/sau và xác nhận thay đổi có thực sự không làm sai trạng thái database.
3. Khai báo checksum cụ thể được phép trong changelog và ghi rõ lý do trong review.
4. Kiểm tra trên database đại diện của mọi nhánh môi trường.
5. Không dùng wildcard như `ANY` để vô hiệu hóa kiểm tra rộng rãi nếu không có lý do được phê duyệt.

`validCheckSum` không thực hiện migration bị thiếu và cũng không chứng minh schema hiện tại khớp với định nghĩa mới. Đây là ngoại lệ có chủ đích trong kiểm tra checksum, không phải công cụ sửa lịch sử tùy tiện.

## 7. Các lệnh Liquibase được hỗ trợ để chẩn đoán và xử lý

Dùng công cụ của Liquibase giúp giữ logic metadata nhất quán hơn so với SQL tự viết. Cú pháp CLI thay đổi theo phiên bản, vì vậy cần kiểm tra trợ giúp/tài liệu đúng bản đang dùng.

| Lệnh | Mục đích | Cảnh báo |
|---|---|---|
| `validate` | Kiểm tra cấu trúc và tính hợp lệ của changelog theo những kiểm tra Liquibase hỗ trợ | Không chứng minh schema thực tế và dữ liệu hoàn toàn đúng |
| `status --verbose` | Xem changeset pending | Kết quả phụ thuộc database, root changelog và filter |
| `history` | Xem lịch sử changeset đã triển khai | Cần xác nhận đúng database/schema metadata |
| `calculate-checksum` | Tính checksum cho changeset theo cú pháp phiên bản | Phải dùng đúng changeset identity và file |
| `clear-checksums` | Xóa checksum đã lưu để Liquibase tính lại ở lần update kế tiếp | Tác động rộng; không dùng để che changeset đã bị sửa nguy hiểm |
| `changelog-sync` | Đánh dấu các changeset phù hợp là đã được đồng bộ mà không chạy thay đổi của chúng | Chỉ dùng để baseline database đã có đúng schema/data |
| `changelog-sync-to-tag` | Đồng bộ lịch sử đến một tag trong trường hợp hỗ trợ | Phải xác minh phạm vi và trạng thái thật |
| `mark-next-changeset-ran` | Đánh dấu changeset kế tiếp là đã chạy mà không thực hiện nội dung theo cơ chế lệnh | Chỉ dùng khi thay đổi tương ứng đã được áp dụng và kiểm chứng bên ngoài |
| `list-locks` | Xem lock đang được ghi nhận | Không tự xóa lock khi chưa biết tiến trình |
| `release-locks` | Giải phóng lock Liquibase bị bỏ lại | Chỉ dùng sau khi xác nhận không có migration hợp lệ đang chạy |

Tên lệnh có thể là dạng kebab-case hoặc camelCase tùy phiên bản. Không sao chép lệnh từ tài liệu của một phiên bản khác mà chưa xác minh. Đặc biệt, `clear-checksums`, `changelog-sync` và `mark-next-changeset-ran` có tác động tới cách Liquibase diễn giải lịch sử; chúng không phải các lệnh “repair” vô hại.

## 8. clear-checksums: dùng đúng lúc, hiểu đúng phạm vi

`clear-checksums` xóa các giá trị checksum đã lưu trong `DATABASECHANGELOG` để Liquibase tính lại ở lần cập nhật tiếp theo. Lệnh này không xóa các changeset, không thực hiện lại toàn bộ DDL/DML và không tự sửa schema.

Ví dụ lệnh:

```bash
liquibase clear-checksums
```

Sau đó, khi chạy `update`, Liquibase có thể tính và lưu checksum mới theo nội dung changelog hiện hành cho những bản ghi đã được ghi nhận. Vì thao tác ảnh hưởng đến checksum của nhiều changeset, phải hiểu lý do và phạm vi trước khi dùng.

### 8.1. Khi nào có thể cân nhắc?

Một trường hợp cần đánh giá là khi nâng cấp Liquibase làm thay đổi cách tính/diễn giải checksum giữa các phiên bản, hoặc khi đã có kế hoạch chuẩn hóa checksum được xác minh trên bản sao database. Trước khi thực hiện:

1. Ghi lại phiên bản Liquibase hiện tại và phiên bản dự kiến.
2. Sao lưu metadata và database theo chính sách.
3. Xác nhận changelog của artifact chính xác với phiên bản đã triển khai.
4. So sánh checksum/lịch sử trên môi trường đại diện.
5. Xác định changeset nào có nội dung khác thực sự, không chỉ khác biểu diễn checksum.
6. Chỉ chạy trong quy trình có kiểm soát, sau đó kiểm tra lại lịch sử và lần update kế tiếp.

### 8.2. Khi nào không được dùng?

Không dùng `clear-checksums` để xử lý nhanh các trường hợp:

- Đã sửa SQL trong changeset tạo bảng/cột đã chạy.
- Muốn bỏ qua lỗi checksum mà chưa hiểu khác biệt nội dung.
- Muốn hợp thức hóa một dòng metadata đã bị sửa thủ công.
- Muốn làm cho nhiều môi trường có lịch sử khác nhau trông giống nhau.
- Muốn tránh tạo changeset mới cho thay đổi schema.

Xóa checksum không làm nội dung mới được áp dụng vào database. Nếu thay đổi có ý nghĩa về schema hoặc dữ liệu, cần changeset mới và một kế hoạch migration thực tế.

## 9. changelog-sync và baseline database hiện hữu

Có dự án áp dụng schema bằng công cụ khác hoặc database đã tồn tại trước khi đưa Liquibase vào. Khi đó, `changelog-sync` có thể được sử dụng để ghi nhận changeset như đã đồng bộ mà không thực thi nội dung thay đổi của chúng.

Đây là **quy trình baseline**, không phải cách chữa mismatch thông thường.

### 9.1. Điều kiện trước khi đồng bộ

Trước khi dùng, phải chứng minh database thực tế đã đạt đúng trạng thái mà changelog tương ứng mô tả:

- Bảng, cột, kiểu dữ liệu, default và constraints tồn tại đúng.
- Index, view, trigger, function và các đối tượng liên quan đúng.
- Dữ liệu tham chiếu và các bước data migration đã được thực hiện đúng.
- Mọi changeset sẽ được đánh dấu là đã chạy đều có hiệu ứng tương ứng đã tồn tại.
- Phạm vi include, context, label, DBMS và tag đúng với kế hoạch baseline.

Nếu chỉ có bảng giống tên nhưng thiếu index hoặc sai constraint, đánh dấu changeset đã chạy sẽ tạo ra lịch sử sai. Liquibase sẽ bỏ qua thao tác chưa thực sự được thực hiện.

### 9.2. Lệnh baseline

Một lệnh CLI minh họa:

```bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  changelog-sync
```

Lệnh này không chạy nội dung changeset như `update`. Nó ghi nhận lịch sử cho các changeset được đồng bộ theo phạm vi/cấu hình. Tùy chọn filter, tag và cách phiên bản hỗ trợ có thể ảnh hưởng tập được ghi nhận.

**Không chạy `changelog-sync` chỉ để dập lỗi checksum hoặc làm mất danh sách pending.** Trước hết phải có báo cáo so sánh schema/data và xác nhận phạm vi baseline; nên thử trên bản sao database và có phê duyệt rõ ràng.

### 9.3. mark-next-changeset-ran

Nếu một changeset cụ thể vừa được áp dụng thủ công bằng một quy trình đã kiểm soát, lệnh `mark-next-changeset-ran` có thể được cân nhắc để ghi nhận changeset kế tiếp mà không chạy lại nội dung. Nhưng phải xác nhận chính xác “next” là changeset nào theo root changelog, filter và lịch sử. Nếu thao tác thủ công không hoàn toàn tương đương nội dung changeset, việc đánh dấu sẽ làm lịch sử không phản ánh thực tế.

Khi có thể, nên để Liquibase thực hiện thay đổi và tự ghi lịch sử ngay trong cùng quy trình thay vì phải đánh dấu sau một lần thực thi bên ngoài.

## 10. Giữ ổn định danh tính khi tổ chức lại changelog

Đường dẫn logic là một phần của bộ định danh. Vì thế, đổi vị trí file có thể tạo ra một changeset mới về mặt lịch sử dù nội dung và `id`/`author` không đổi.

Trước khi di chuyển:

1. Truy vấn `ID`, `AUTHOR`, `FILENAME` của changeset ở từng môi trường.
2. Xác định đường dẫn logic mới và cơ chế include/resource accessor.
3. Giữ nguyên `id` và `author`.
4. Dùng `logicalFilePath` tại phạm vi được phiên bản Liquibase hỗ trợ nếu cần giữ đường dẫn logic cũ.
5. Chạy `status --verbose` và kiểm tra changeset cũ không bất ngờ xuất hiện pending.
6. Xem SQL dự kiến và xác minh trên database có lịch sử đại diện.

Không sửa `FILENAME` trực tiếp trong `DATABASECHANGELOG` để “khớp” với đường dẫn mới. Nếu cần thay đổi logic path, phải thực hiện bằng cấu hình changelog được hỗ trợ và xác minh kết quả nhận diện.

### 10.1. Tránh tái sử dụng id

Không dùng lại cùng bộ ba (`id`, `author`, đường dẫn logic) cho một thay đổi khác. Nếu thay đổi schema mới, hãy tạo changeset mới có định danh riêng. Nếu hai nhánh phát triển độc lập cùng tạo một ID, cần xử lý xung đột trước khi merge; không đổi ID của changeset đã triển khai chỉ để giải quyết xung đột sau này.

### 10.2. Changelog append-only là quy ước hữu ích

Một quy ước đơn giản là xem thư mục changeset đã triển khai như lịch sử append-only:

- Thêm changeset mới cho thay đổi mới.
- Không sửa nội dung changeset đã chạy.
- Không xóa file lịch sử đã chạy.
- Không đổi `id`/`author` hoặc đường dẫn logic tùy tiện.
- Ghi rõ lý do cho ngoại lệ như `validCheckSum` hoặc `runOnChange`.
- Giữ lại artifact/changelog theo từng release để có thể truy xuất.

Đây là quy tắc quản trị giúp nhiều nhóm cùng triển khai mà không làm lệch lịch sử.

## 11. Xử lý DATABASECHANGELOGLOCK đúng cách

Khi một Liquibase process bắt đầu migration, nó sử dụng bảng `DATABASECHANGELOGLOCK` để tránh một process khác chạy đồng thời trên cùng database. Nếu process bị kill hoặc lỗi giữa chừng, lock có thể vẫn còn được ghi nhận.

Trước khi giải phóng:

1. Kiểm tra tiến trình Liquibase/CI job có còn chạy không.
2. Kiểm tra thời điểm `LOCKGRANTED`, thông tin `LOCKEDBY` và log liên quan.
3. Kiểm tra session database có còn thực hiện DDL/DML hoặc giữ transaction không.
4. Xác nhận không có deploy khác đang sử dụng cùng metadata.
5. Chỉ khi đã chứng minh lock bị bỏ lại mới dùng lệnh được hỗ trợ như `release-locks`.
6. Sau khi giải phóng, kiểm tra trạng thái schema, `DATABASECHANGELOG` và chạy `status` để xác định điểm tiếp tục.

Ví dụ lệnh kiểm tra/giải phóng:

```bash
liquibase list-locks
liquibase release-locks
```

Không chạy `release-locks` khi một migration hợp lệ vẫn đang hoạt động; điều đó có thể cho phép process khác bắt đầu cập nhật đồng thời và gây tranh chấp. Không dùng SQL `UPDATE DATABASECHANGELOGLOCK SET LOCKED = FALSE` như một giải pháp mặc định, vì có thể bỏ qua những điều kiện và hành vi xử lý của Liquibase.

Lock bị giữ không đồng nghĩa changeset đã thất bại hoàn toàn hoặc chưa thay đổi gì. Sau khi process dừng, phải xem log và kiểm tra schema/lịch sử để biết changeset nào đã hoàn tất.

## 12. Cách chẩn đoán checksum mismatch theo bằng chứng

Khi Liquibase báo checksum mismatch, hãy thực hiện theo trình tự:

### Bước 1. Ghi lại thông tin lỗi

Lưu changeset ID, author, file path, checksum lịch sử và checksum Liquibase đang tính. Không chỉnh file hoặc metadata ngay khi chưa ghi nhận trạng thái.

### Bước 2. Kiểm tra nguồn changelog

Xác nhận đúng branch, commit, artifact, file được đóng gói và các file include. Kiểm tra xem một changeset đã bị sửa, đổi định dạng hoặc đổi đường dẫn không.

### Bước 3. So sánh các môi trường

Kiểm tra cùng changeset trên development, staging và production. Nếu checksum khác nhau, tìm commit/artifact đã được triển khai ở từng môi trường. Không giả định database đã chạy cùng một phiên bản changelog chỉ vì dùng chung repository.

### Bước 4. Xác định loại khác biệt

Phân loại khác biệt thành:

- Thay đổi thực sự về DDL/DML.
- Chỉnh sửa không ảnh hưởng ý nghĩa nhưng có thể tác động checksum tùy loại change.
- Thay đổi do phiên bản Liquibase hoặc cách canonicalize.
- Đổi đường dẫn/identity, không phải lỗi checksum thuần túy.
- Metadata bị sửa thủ công hoặc history đã bị hỏng.

### Bước 5. Chọn biện pháp đúng

| Kết quả điều tra | Hướng xử lý |
|---|---|
| Changeset đã chạy bị sửa logic | Khôi phục file lịch sử và tạo changeset mới |
| View/procedure có chủ đích thay theo nội dung | Đánh giá `runOnChange` và rollback trước khi sửa |
| Thay đổi đã biết và được chứng minh không làm thay đổi kết quả database | Cân nhắc `validCheckSum` cụ thể sau review |
| Thay đổi checksum do nâng cấp Liquibase | Thử quy trình nâng cấp và `clear-checksums` có kiểm soát trên bản sao |
| Đường dẫn logic đổi | Giữ identity bằng cơ chế `logicalFilePath` phù hợp |
| Bảng lịch sử bị sửa hoặc mất dòng | Dừng update, đối chiếu backup/log/schema và lập kế hoạch repair được phê duyệt |

Không có một lệnh duy nhất giải quyết mọi trường hợp. Chọn biện pháp dựa trên bằng chứng, không dựa trên mục tiêu làm cho pipeline tiếp tục chạy.

## 13. Truy vấn metadata chỉ đọc để audit

Các truy vấn dưới đây chỉ nhằm kiểm tra, không sửa bảng theo dõi. Cần thay schema/tên bảng nếu dự án cấu hình khác mặc định.

### 13.1. Xem lịch sử gần nhất

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

Không phải phiên bản nào cũng có tất cả các cột trong ví dụ; hãy xem cấu trúc thật trước khi sử dụng truy vấn.

### 13.2. Tìm định danh trùng trong metadata

```sql
SELECT ID,
       AUTHOR,
       FILENAME,
       COUNT(*) AS record_count
FROM DATABASECHANGELOG
GROUP BY ID, AUTHOR, FILENAME
HAVING COUNT(*) > 1;
```

Kết quả bất thường cần điều tra theo version/schema metadata, cách chạy và nguồn dữ liệu. Không tự xóa dòng trùng trước khi xác minh lịch sử và ảnh hưởng.

### 13.3. Xem trạng thái lock

```sql
SELECT ID, LOCKED, LOCKGRANTED, LOCKEDBY
FROM DATABASECHANGELOGLOCK;
```

Đây là truy vấn quan sát. Không dùng kết quả `LOCKED = TRUE` làm căn cứ duy nhất để xóa lock: phải xác định process còn hoạt động hay không.

### 13.4. Đối chiếu metadata với schema thực

Có thể dùng `information_schema` hoặc catalog của DBMS để kiểm tra bảng/cột/constraint, nhưng không nên chỉ so sánh tên object. Cần xác minh kiểu, nullability, default, index, FK, view và nội dung dữ liệu liên quan. Metadata Liquibase và trạng thái schema là hai nguồn bằng chứng bổ sung nhau.

## 14. Bảo vệ metadata giữa nhiều môi trường và nhiều nhánh

Mỗi database có lịch sử riêng. Development có thể đã chạy changeset mới hơn production; staging có thể có một changeset được `MARK_RAN`; production có thể được baseline bằng quy trình riêng. Do đó, không thể sao chép hoặc sửa bảng lịch sử của môi trường này để thay thế môi trường khác.

Các nguyên tắc:

1. **Một artifact changelog đã review:** build và deploy cùng phiên bản changelog đã được xác nhận.
2. **Không chia sẻ database metadata giữa các database độc lập:** mỗi database phải quản lý bảng lịch sử/lock riêng theo cấu hình đúng.
3. **Không chỉnh history trực tiếp để đồng bộ:** dùng baseline hoặc synchronization được hỗ trợ khi có bằng chứng schema thực.
4. **Theo dõi drift:** kiểm tra schema thật so với thay đổi kỳ vọng, không chỉ dựa vào số changeset.
5. **Giữ lịch sử artifact:** có thể truy xuất changelog, checksum, Liquibase version và commit của từng đợt.
6. **Quản lý quyền:** tài khoản ứng dụng không cần quyền sửa bảng metadata; tài khoản migration nên có quyền tối thiểu cần thiết và audit.
7. **Review nhánh:** giải quyết xung đột changeset trước khi merge; không sửa changeset đã phát hành để làm các nhánh “đồng bộ”.

### 14.1. Baseline nhiều môi trường

Khi đưa Liquibase vào một hệ thống đã tồn tại, mỗi môi trường phải được đánh giá độc lập. Nếu production và staging có schema khác nhau, một lệnh `changelog-sync` giống nhau có thể ghi nhận sai lịch sử ở một trong hai. Cần báo cáo khác biệt, chuẩn hóa schema hoặc xây baseline phù hợp từng trạng thái trước khi tiếp tục triển khai chung.

## 15. CI/CD: ngăn sửa metadata thủ công bằng quy trình

Một pipeline có thể áp dụng các cổng kiểm soát:

```text
Commit changelog
      |
      v
Review changeset đã triển khai có bị sửa?
      |
      v
validate + kiểm tra checksum/lịch sử
      |
      v
Preview update-sql / rollback-sql
      |
      v
Kiểm tra schema và dữ liệu trên môi trường đại diện
      |
      v
Phê duyệt release
      |
      v
Liquibase update / rollback
      |
      v
Audit DATABASECHANGELOG và schema sau triển khai
```

Cụ thể:

- **Code review:** changeset đã chạy phải bất biến; mọi thay đổi DDL/DML mới dùng changeset mới trừ ngoại lệ được duyệt.
- **Artifact integrity:** lưu commit, phiên bản Liquibase, driver, DBMS và root changelog dùng khi deploy.
- **Preview:** sinh SQL trước update/rollback và review thao tác phá hủy, phạm vi dữ liệu, dependency.
- **History audit:** ghi lại ID/AUTHOR/FILENAME, EXECTYPE, thời điểm và kết quả.
- **Lock control:** chỉ một cơ chế sở hữu migration; không để nhiều pipeline hoặc startup ứng dụng cùng cạnh tranh.
- **Least privilege:** tài khoản runtime không có quyền cập nhật/xóa metadata Liquibase; quyền migration được kiểm soát.
- **Recovery:** backup/point-in-time recovery và quy trình repair phải được thử trước khi cần.
- **Incident procedure:** nếu metadata sai, dừng triển khai và yêu cầu đối chiếu, không chạy script sửa bảng lịch sử tùy tiện.

### 15.1. Spring Boot và việc tự động chạy Liquibase

Spring Boot có thể chạy Liquibase khi ứng dụng khởi động:

```yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
```

Cấu hình này cần được phối hợp với pipeline. Nếu CI/CD đã sở hữu migration, có thể cấu hình ứng dụng không tự chạy Liquibase trong môi trường đó theo kiến trúc dự án. Nếu cả startup và pipeline cùng có thể chạy, cần đảm bảo lock và quyền sở hữu nhất quán. `DATABASECHANGELOGLOCK` không thay thế quy trình phê duyệt hoặc ngăn một instance tự chạy các changeset còn pending sau khi nhóm đã rollback.

## 16. Quy trình ứng phó khi phát hiện ai đó sửa metadata

Nếu phát hiện bảng lịch sử có dấu hiệu bị sửa ngoài Liquibase:

1. **Dừng các lần update/rollback tự động** có thể làm tình trạng phức tạp thêm; thông báo đúng người chịu trách nhiệm vận hành theo quy trình nội bộ.
2. **Lưu bằng chứng:** backup metadata, log Liquibase, audit log database, commit/artifact và thời điểm deploy.
3. **Xác định thay đổi thủ công:** dòng nào được thêm/xóa/sửa; trường nào bị thay đổi; người hoặc job nào thực hiện nếu audit có.
4. **Đối chiếu schema và dữ liệu thực:** xác minh DDL/DML nào đã thực sự chạy, changeset nào đã được áp dụng và những thay đổi ngoài Liquibase.
5. **So sánh các môi trường:** tìm trạng thái lịch sử đúng hoặc nguồn backup đáng tin cậy, không sao chép mù từ môi trường khác.
6. **Lập kế hoạch repair:** có thể cần phục hồi metadata từ backup, baseline/sync có kiểm chứng hoặc migration bù; lựa chọn phải được Liquibase owner/DBA review.
7. **Thử trên bản sao:** kiểm tra lần update/rollback kế tiếp không lặp thay đổi, không bỏ qua migration và không mất dữ liệu.
8. **Khôi phục quyền và kiểm soát:** loại bỏ quyền chỉnh metadata không cần thiết, bổ sung audit và ngăn tái diễn.
9. **Hậu kiểm:** xác nhận history, schema, dữ liệu và ứng dụng đã nhất quán.

Không thực hiện ngay một lệnh `changelog-sync` hoặc `clear-checksums` để che dấu hiệu bất thường. Hai lệnh này không thể tự tái tạo lịch sử thật nếu không biết SQL nào đã được áp dụng.

## 17. Bài thực hành: kiểm tra checksum và bảo toàn lịch sử

**Mục tiêu:** thực hành trên database lab riêng để hiểu mối quan hệ giữa changelog, checksum và metadata.

### Bước 1. Tạo một changeset và áp dụng

Tạo changeset `001-create-customer` tạo bảng `customer_account`, chạy `update` và kiểm tra bản ghi lịch sử trong `DATABASECHANGELOG`. Ghi lại `ID`, `AUTHOR`, `FILENAME`, `MD5SUM` và `EXECTYPE`.

### Bước 2. Sửa changeset đã chạy trong nhánh lab

Thử thêm cột trực tiếp vào changeset cũ. Chạy `validate` và `update` để quan sát hành vi checksum/identity của phiên bản Liquibase đang dùng. Không áp dụng cách làm này vào nhánh phát hành thật.

### Bước 3. Khôi phục changeset cũ và tạo changeset mới

Trả changeset 001 về nội dung đã triển khai. Tạo `002-add-customer-email` riêng, chạy update và xác minh hai bản ghi lịch sử. So sánh cách này với sửa changeset cũ.

### Bước 4. Thử validCheckSum trong tình huống được kiểm soát

Tạo một tình huống lab có checksum khác nhưng nội dung đã được chứng minh không thay đổi kết quả schema. Tìm checksum cụ thể trong lỗi/diagnostic, thử khai báo `validCheckSum` chính xác và quan sát. Không dùng `ANY` làm giải pháp chung.

### Bước 5. Thử clear-checksums

Sao lưu database lab, chạy `clear-checksums`, kiểm tra giá trị metadata và chạy update trong môi trường thử nghiệm. Ghi nhận rằng lệnh này không tự thực thi lại toàn bộ changeset đã chạy, mà làm Liquibase tính lại checksum theo cơ chế tiếp theo. Không thực hành trên production.

### Bước 6. Thử baseline với schema đã có

Tạo database lab có schema giống kết quả changelog bằng một cách khác. So sánh cấu trúc, dữ liệu, constraints, index và view. Chỉ sau khi chứng minh tương đương mới thử `changelog-sync` và xác minh history. Nếu cố ý bỏ sót một index hoặc constraint, quan sát vì sao việc sync sẽ tạo ra lịch sử không đúng.

### Bước 7. Thử xử lý lock

Trong lab, tạo tình huống lock bị bỏ lại mà không có tiến trình Liquibase còn chạy. Xem `list-locks`, kiểm tra session và dùng `release-locks` theo quy trình. Không sửa SQL trực tiếp trên `DATABASECHANGELOGLOCK`.

**Tiêu chí hoàn thành:** giải thích được vì sao identity khác checksum, không sửa metadata bằng SQL, phân biệt clear-checksums với changelog-sync và biết cách dừng/điều tra khi lịch sử không còn đáng tin.

## 18. Checklist bảo vệ lịch sử Liquibase

- [ ] `DATABASECHANGELOG` và `DATABASECHANGELOGLOCK` được hiểu đúng vai trò, không dùng thay thế cho nhau.
- [ ] Không có script thủ công INSERT/UPDATE/DELETE trên bảng metadata trong quy trình deploy thông thường.
- [ ] Changeset đã chạy được giữ bất biến; thay đổi mới tạo changeset mới.
- [ ] Bộ định danh `id`/`author`/đường dẫn logic ổn định; việc di chuyển file có kế hoạch `logicalFilePath` phù hợp.
- [ ] Checksum được xem là kiểm tra nội dung changeset, không phải chữ ký bảo mật hay bản backup schema.
- [ ] Khi checksum mismatch, đã xác định nguyên nhân trước khi chọn validCheckSum hoặc clear-checksums.
- [ ] `validCheckSum` chỉ chấp nhận giá trị cụ thể có lý do và review; không vô hiệu hóa rộng rãi bằng `ANY`.
- [ ] `clear-checksums` chỉ chạy khi hiểu tác động trên toàn bộ checksum và đã thử trên database đại diện.
- [ ] `changelog-sync`/`mark-next-changeset-ran` chỉ dùng cho baseline hoặc ghi nhận thay đổi đã áp dụng thực tế, có đối chiếu schema/data.
- [ ] Lock được giải phóng bằng cơ chế Liquibase sau khi xác minh không còn tiến trình đang chạy.
- [ ] Mỗi môi trường được audit riêng; không sao chép lịch sử từ staging sang production.
- [ ] Pipeline có validate, status, SQL preview, review, quyền tối thiểu và hậu kiểm.
- [ ] Có backup/audit log và quy trình ứng phó khi metadata bị sửa ngoài ý muốn.
- [ ] Ứng dụng Spring Boot và pipeline thống nhất nơi sở hữu migration.
- [ ] Sau mọi thao tác repair/baseline, schema, dữ liệu và lịch sử đều được kiểm chứng trên database thử nghiệm trước khi triển khai thật.

**Kết luận:** lịch sử Liquibase là một phần của trạng thái triển khai database và cần được bảo vệ như mã migration. `DATABASECHANGELOG` ghi nhận danh tính, checksum và trạng thái changeset; `DATABASECHANGELOGLOCK` điều phối việc chạy đồng thời. Sửa thủ công các bảng này có thể khiến Liquibase chạy lại thay đổi đã áp dụng hoặc bỏ qua thay đổi còn thiếu. Hãy giữ changeset đã triển khai bất biến, tạo changeset mới cho thay đổi mới, chẩn đoán checksum bằng bằng chứng và chỉ dùng các lệnh đồng bộ/repair được hỗ trợ khi có baseline, kiểm thử và phê duyệt rõ ràng.

