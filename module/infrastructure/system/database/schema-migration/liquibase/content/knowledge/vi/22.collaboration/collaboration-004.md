# Giữ định danh và đường dẫn ổn định khi hợp nhất mã

## 1. Vì sao định danh changeset quan trọng khi nhiều người cùng làm?

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, Liquibase quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Thực tế dự án thường có nhiều nhánh phát triển, nhiều người cùng thêm migration, nhiều môi trường triển khai và các ứng dụng Spring Boot hoặc pipeline CI/CD cùng sử dụng một bộ changelog. Khi hợp nhất mã, việc giữ **định danh changeset và đường dẫn changelog ổn định** giúp Liquibase nhận diện đúng những thay đổi đã chạy trên từng database.

Liquibase không nhận diện changeset chỉ bằng tên file hoặc số thứ tự trong tên. Bộ định danh cơ bản của một changeset gồm:

1. `id` của changeset.
2. `author` của changeset.
3. Đường dẫn logic của changelog chứa changeset (thường được lưu trong `FILENAME` của `DATABASECHANGELOG`).

Có thể mô tả:

```text
changeset identity =
    (id, author, logical changelog file path)
```

Khi một changeset được áp dụng, Liquibase lưu danh tính này cùng checksum và thông tin thực thi vào `DATABASECHANGELOG`. Trong lần chạy sau, nó đối chiếu changelog hiện tại với lịch sử database để biết changeset nào đã chạy, changeset nào còn pending và changeset nào có nội dung không còn khớp.

Vì vậy, một thay đổi tưởng như chỉ là “đổi tên file cho đẹp” hoặc “đổi ID cho thống nhất sau merge” có thể khiến Liquibase coi migration đã chạy là một changeset mới. Hệ quả có thể là chạy lại DDL/DML, báo checksum mismatch, bỏ qua một thay đổi cần thiết hoặc làm lịch sử giữa các môi trường lệch nhau.

Bài học thuộc chương **Cộng tác** này hướng dẫn cách thiết kế identity, tổ chức đường dẫn, xử lý xung đột nhánh và hợp nhất changeset mà không làm mất tính liên tục của lịch sử.

## 2. Bộ ba định danh và vai trò của checksum

Ví dụ một changeset:

```yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-20-add-customer-email
      author: platform-team
      changes:
        - addColumn:
            tableName: customer_account
            columns:
              - column:
                  name: email
                  type: varchar(320)
```

Giả sử changeset này nằm trong file:

```text
db/changelog/changes/2026-11-20-add-customer-email.yaml
```

Liquibase nhận diện nó dựa trên `id`, `author` và đường dẫn logic của file. Tên file vật lý thường trở thành thành phần đường dẫn được ghi vào `FILENAME`, trừ khi dự án cấu hình đường dẫn logic riêng.

### 2.1. ID không phải số thứ tự toàn cục

`id` là chuỗi do nhóm đặt, không phải một sequence database tự tăng. Các nhóm thường dùng:

- Mã ticket hoặc issue, ví dụ `DB-482-add-customer-email`.
- Ngày và mô tả, ví dụ `2026-11-20-add-customer-email`.
- Tên thay đổi ngắn, duy nhất trong phạm vi changelog.
- Tiền tố nhóm/domain kết hợp mã công việc.

ID cần ổn định sau khi đã triển khai. Không tái sử dụng cùng identity cho một thay đổi khác. Cách đặt ID nên giúp reviewer hiểu thay đổi và giảm khả năng hai nhánh tạo cùng một ID.

### 2.2. Author là thành phần identity, không phải người chạy migration

`author` thường là tên nhóm, tài khoản hoặc định danh tác giả được thống nhất trong dự án. Nó không nhất thiết là username của người chạy Liquibase trên production. Nếu thay author của changeset đã triển khai, bộ ba identity sẽ thay đổi.

Không đổi `author` sau khi chạy chỉ để phản ánh người review hoặc người merge. Nếu cần ghi nhận đóng góp, dùng Git history, code review và metadata phát hành.

### 2.3. Đường dẫn logic là thành phần identity

Hai changeset có cùng `id` và `author` nhưng ở hai đường dẫn logic khác nhau có thể được Liquibase xem là hai changeset khác nhau.

Ví dụ:

```text
db/changelog/feature-a/001-add-email.yaml
db/changelog/feature-b/001-add-email.yaml
```

Dù cả hai có `id: 001-add-email` và `author: platform-team`, đường dẫn logic khác nhau làm identity khác nhau. Điều này không có nghĩa nhóm nên cố ý nhân bản cùng một migration ở hai file; nó chỉ giải thích vì sao đổi vị trí file có thể ảnh hưởng lịch sử.

### 2.4. Checksum giải quyết câu hỏi khác identity

Checksum trong `MD5SUM` giúp Liquibase phát hiện nội dung changeset đã nhận diện có thay đổi so với lúc được ghi nhận hay không. Nó không thay thế bộ ba identity.

| Thành phần | Câu hỏi |
|---|---|
| `id` | Changeset mang mã nào? |
| `author` | Changeset được gắn với tác giả/nhóm nào? |
| Đường dẫn logic | Changeset thuộc changelog nào? |
| `MD5SUM` | Nội dung changeset đã nhận diện có khớp checksum được lưu không? |

Nếu sửa nội dung của changeset đã chạy nhưng giữ nguyên identity, Liquibase có thể báo checksum mismatch. Nếu đổi đường dẫn hoặc ID, Liquibase có thể không tìm thấy identity cũ và xem thay đổi như changeset mới. Hai lỗi này cần cách xử lý khác nhau.

## 3. Điều gì xảy ra khi di chuyển file changelog?

Giả sử ban đầu:

```text
db/changelog/
└── changes/
    └── 010-add-customer-email.yaml
```

Sau khi được triển khai, nhóm muốn tổ chức lại thành:

```text
db/changelog/
└── schema/
    └── customer/
        └── 010-add-customer-email.yaml
```

Nội dung changeset và `id`/`author` không đổi, nhưng đường dẫn logic có thể đổi. Trong `DATABASECHANGELOG`, Liquibase đã lưu đường dẫn cũ; khi nạp đường dẫn mới, nó có thể xem changeset là một identity khác và thử chạy lại.

Đối với changeset **chưa từng được triển khai ở bất kỳ môi trường dùng chung nào**, việc di chuyển file thường đơn giản hơn, nhưng vẫn cần kiểm tra các nhánh khác, artifact đã build và môi trường có thể đã chạy bản đó hay chưa.

Đối với changeset **đã triển khai**, phải bảo toàn identity logic hoặc có kế hoạch chuyển đổi lịch sử được review. Không chỉ đổi include path rồi hy vọng Liquibase tự hiểu file mới là file cũ.

## 4. Dùng logicalFilePath để giữ đường dẫn logic

Liquibase có thuộc tính `logicalFilePath` để chỉ định đường dẫn logic được dùng khi nhận diện changeset, tách biệt với vị trí vật lý của file. Thuộc tính này hữu ích khi tổ chức lại thư mục hoặc di chuyển changelog mà vẫn muốn giữ identity lịch sử.

Ví dụ changelog trước đây có đường dẫn logic:

```text
db/changelog/changes/010-add-customer-email.yaml
```

Sau khi chuyển file sang thư mục mới, có thể khai báo đường dẫn logic cũ ở phạm vi changelog theo cú pháp mà phiên bản Liquibase sử dụng hỗ trợ:

Ví dụ về ý nghĩa cần giữ ổn định:

```text
logical file path: db/changelog/changes/010-add-customer-email.yaml
physical file path: db/changelog/schema/customer/010-add-customer-email.yaml
```

Với changelog XML, `logicalFilePath` được khai báo trên phần tử gốc `databaseChangeLog`. Cú pháp cụ thể cho YAML hoặc formatted SQL phụ thuộc định dạng và phiên bản Liquibase; hãy xác nhận tài liệu tương ứng trước khi áp dụng. Đường dẫn logic là giá trị định danh, không phải một mục tùy ý có thể đặt vào bất kỳ vị trí nào trong YAML.

Đoạn trên minh họa ý tưởng cấu hình ở changelog; cần xác nhận vị trí/format chính xác của `logicalFilePath` theo phiên bản Liquibase và định dạng changelog đang dùng. Một số phiên bản hỗ trợ thuộc tính này ở cấp changelog, include hoặc phạm vi khác; không tự sao chép cú pháp khi chưa kiểm tra.

**Giá trị logical path phải khớp với đường dẫn đã được lưu trong lịch sử**, không phải đường dẫn vật lý mới mà người viết thích dùng. Trước khi thay đổi, truy vấn `FILENAME` của changeset ở từng database liên quan và xác nhận chính xác giá trị cần giữ.

### 4.1. logicalFilePath không sửa lịch sử đã ghi

Thuộc tính này điều khiển cách Liquibase nhận diện file/changelog hiện tại. Nó không tự sửa các dòng `DATABASECHANGELOG` cũ và không bảo đảm giải quyết mọi tình huống identity đã bị nhân đôi.

Nếu một số môi trường đã chạy đường dẫn cũ, môi trường khác đã chạy đường dẫn mới, cần lập bảng đối chiếu identity theo từng database. Không thêm `logicalFilePath` theo phỏng đoán rồi chạy update trên production.

### 4.2. Khi nào không cần logicalFilePath?

Nếu file chưa được triển khai và chưa có môi trường dùng chung ghi nhận changeset, nhóm có thể di chuyển file và cập nhật include theo quy trình thông thường. Dù vậy, phải kiểm tra artifact cũ, nhánh đang mở và môi trường thử nghiệm để tránh có database đã chạy file trước khi di chuyển.

Nếu thay đổi chỉ là chỉnh thứ tự include mà đường dẫn logic không đổi, không cần dùng `logicalFilePath` chỉ để “phòng ngừa”. Hãy giữ cấu hình đơn giản và ổn định.

## 5. Tình huống xung đột changeset khi hai nhánh phát triển song song

Giả sử hai developer cùng tạo migration từ một nhánh gốc:

```text
main
 |
 +-- feature/customer-email
 |      010-add-customer-email.yaml
 |
 +-- feature/customer-phone
        010-add-customer-phone.yaml
```

Nếu cả hai nhánh dùng cùng `id`, `author` và cùng file path khi được hợp nhất, chúng tạo ra identity trùng. Nếu nội dung khác nhau, một database có thể chạy một nhánh trước; sau đó nhánh kia đưa changeset cùng identity nhưng nội dung khác vào sẽ gây checksum mismatch hoặc xung đột trong quy trình.

Nếu file path khác nhau, Liquibase có thể coi chúng là hai identity riêng dù ID trùng. Điều đó không phải lúc nào cũng gây lỗi kỹ thuật, nhưng vẫn làm lịch sử khó hiểu và tăng nguy cơ trùng thay đổi. Nên thống nhất cách đặt ID và review identity trước khi merge.

### 5.1. Đặt ID có khả năng tránh va chạm

Ví dụ dùng mã công việc:

```yaml
databaseChangeLog:
  - changeSet:
      id: DB-482-add-customer-email
      author: platform-team
      changes:
        - addColumn:
            tableName: customer_account
            columns:
              - column:
                  name: email
                  type: varchar(320)
```

Nhánh khác:

```yaml
databaseChangeLog:
  - changeSet:
      id: DB-497-add-customer-phone
      author: platform-team
      changes:
        - addColumn:
            tableName: customer_account
            columns:
              - column:
                  name: phone
                  type: varchar(32)
```

Cách này làm rõ nguồn thay đổi và giảm khả năng đụng ID. Dù vậy, ID duy nhất không bảo đảm hai migration không xung đột về cấu trúc: cả hai vẫn có thể cùng sửa một cột, đổi cùng một constraint hoặc phụ thuộc vào cùng một trạng thái schema.

### 5.2. Không giải quyết va chạm bằng cách sửa changeset đã chạy

Nếu một changeset đã chạy trên staging hoặc production, không đổi ID/author/path để “nhường” cho nhánh khác. Hãy giữ identity đã triển khai và tạo changeset mới cho phần điều chỉnh. Nếu cả hai nhánh chưa triển khai ở bất kỳ môi trường dùng chung nào, có thể sửa identity trước khi merge theo chính sách nhóm.

## 6. Hợp nhất nhánh: xử lý cả xung đột Git và xung đột migration

Git có thể merge hai file YAML mà không xung đột văn bản, nhưng điều đó không chứng minh thứ tự migration đúng. Ngược lại, Git có thể báo conflict trong root changelog dù hai changeset độc lập về schema.

Khi merge, cần xem hai lớp:

1. **Conflict mã nguồn:** hai nhánh cùng sửa root changelog, cùng file hoặc cùng block include.
2. **Conflict vận hành database:** hai changeset có identity trùng, dependency sai thứ tự hoặc giả định schema khác nhau.

Ví dụ root changelog ban đầu:

```yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true
```

Nhánh A thêm:

```yaml
  - include:
      file: changes/010-add-customer-email.yaml
      relativeToChangelogFile: true
```

Nhánh B thêm:

```yaml
  - include:
      file: changes/020-add-customer-phone.yaml
      relativeToChangelogFile: true
```

Sau merge, root changelog cần chứa cả hai include với thứ tự phù hợp:

```yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/010-add-customer-email.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/020-add-customer-phone.yaml
      relativeToChangelogFile: true
```

Thứ tự 010 trước 020 chỉ là ví dụ; nếu hai changeset độc lập, thứ tự có thể không quan trọng về schema, nhưng nếu 020 phụ thuộc cột email hoặc thay đổi do 010 tạo ra thì phải đặt đúng thứ tự. Không dựa vào số trong ID để Liquibase tự sắp xếp.

### 6.1. include và includeAll

`include` khai báo file cụ thể, giúp reviewer thấy thứ tự và quan hệ phụ thuộc. `includeAll` nạp các file trong thư mục theo quy tắc sắp xếp của Liquibase/resource accessor. Khi dùng includeAll:

- Đặt tên file có thứ tự ổn định.
- Không đưa file nháp, file backup hoặc changelog không dành cho môi trường vào cùng thư mục.
- Kiểm tra chính xác những file được nạp.
- Không dựa vào thứ tự tạo file trên filesystem.
- Review tác động khi thêm file mới vì nó có thể thay đổi thứ tự xử lý.

Với các migration phụ thuộc nhau hoặc nhiều nhóm cùng đóng góp, `include` tường minh thường dễ kiểm soát hơn. Nếu dùng `includeAll`, cần có quy ước tên và kiểm tra tự động để tránh một file mới chen vào giữa chuỗi đã triển khai.

## 7. Giữ changelog đã triển khai theo quy tắc append-only

Một quy ước cộng tác hữu ích là xem changeset đã triển khai như lịch sử bất biến:

- Thêm changeset mới cho thay đổi mới.
- Không sửa nội dung changeset đã chạy để bổ sung DDL/DML.
- Không tái sử dụng identity cho mục đích khác.
- Không di chuyển file đã chạy nếu chưa bảo toàn logical path.
- Không xóa changelog cũ chỉ vì đã hoàn tất release.
- Không đổi include/path một cách tùy tiện giữa các nhánh.
- Ghi lý do và phạm vi cho ngoại lệ như `validCheckSum` hoặc `runOnChange`.

Ví dụ cần thêm cột `phone` sau khi `010-add-customer-email` đã triển khai, hãy tạo `020-add-customer-phone`. Không quay lại thêm cột phone vào changeset 010.

### 7.1. Vì sao append-only giúp nhiều môi trường nhất quán?

Giả sử staging đã chạy 010 và production cũng đã chạy 010. Nếu nội dung 010 thay đổi, hai môi trường có thể vẫn có cùng identity nhưng schema thực tế khác nhau. Nếu sau đó pipeline chạy update, Liquibase có thể phát hiện checksum mismatch ở một hoặc cả hai môi trường.

Khi changeset lịch sử được giữ nguyên, thay đổi mới được biểu diễn bằng identity mới. Mỗi database có thể tiến dần qua cùng chuỗi migration, trong khi lịch sử giải thích rõ bước nào được áp dụng ở đâu.

Append-only không có nghĩa changelog không bao giờ được tổ chức lại. Nó có nghĩa **không thay đổi danh tính và ý nghĩa của migration đã được ghi nhận**. Tái cấu trúc file cần giữ logical path và được kiểm chứng trên lịch sử thật.

## 8. Chọn chiến lược file và root changelog ổn định

Một cấu trúc dễ cộng tác:

```text
src/main/resources/db/changelog/
├── db.changelog-master.yaml
├── changes/
│   ├── 001-create-customer.yaml
│   ├── DB-482-add-customer-email.yaml
│   └── DB-497-add-customer-phone.yaml
└── sql/
    └── views/
```

Root changelog:

```yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/DB-482-add-customer-email.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/DB-497-add-customer-phone.yaml
      relativeToChangelogFile: true
```

Ưu điểm:

- Root file có vị trí ổn định.
- Các changeset độc lập được chia thành file riêng.
- Thứ tự nạp được review tường minh.
- Mã công việc giúp giảm va chạm ID.
- File SQL phụ trợ có thư mục riêng, không bị include nhầm.

Tên file chỉ là một phần của cách tổ chức; đường dẫn logic và nội dung include mới quyết định Liquibase nhận diện changelog như thế nào. Nếu đổi cấu trúc, phải xác nhận identity cũ không bị đổi ngoài ý muốn.

### 8.1. Không tạo một file root khác chỉ để né conflict

Nếu hai nhánh cùng sửa root changelog, việc tạo thêm root thứ hai có thể làm dự án có hai lịch sử triển khai khác nhau. Một số môi trường có thể chạy root A, môi trường khác chạy root B; sau này hợp nhất rất khó đối chiếu.

Nên giải quyết conflict ở root chung và giữ một entry point được cấu hình nhất quán. Nếu kiến trúc thật sự cần nhiều root changelog (ví dụ nhiều module hoặc database riêng), phải xác định rõ database nào dùng root nào và lịch sử nào thuộc phạm vi đó.

## 9. Xử lý cherry-pick và hotfix

Cherry-pick một commit chứa changeset từ nhánh khác không chỉ là lấy một đoạn code; nó đưa một migration identity vào changelog được triển khai.

Trước khi cherry-pick:

1. Xác định changeset đã chạy ở môi trường nào chưa.
2. Xác nhận identity gồm ID, author và logical path.
3. Kiểm tra root changelog đã include file chưa.
4. Kiểm tra dependency của changeset có mặt trong nhánh đích không.
5. Xem changeset có giả định một cột/bảng hoặc dữ liệu do commit khác tạo ra không.
6. Kiểm tra cùng identity có nội dung khác trong nhánh đích không.
7. Review SQL và rollback trên DBMS đích.

### 9.1. Hotfix đã chạy production

Nếu hotfix migration đã chạy production, hãy giữ nguyên identity và file logic tương ứng khi merge ngược về main/release branch. Không tạo một changeset mới có cùng tác dụng chỉ vì commit gốc chưa được merge; nếu làm vậy, database có thể áp dụng thay đổi hai lần.

Cần kiểm tra lịch sử production để xác định changeset đã được ghi nhận dưới đường dẫn nào. Nếu cherry-pick khiến đường dẫn khác, hãy xử lý logical path trước khi triển khai lên môi trường khác.

### 9.2. Hai nhánh cùng giải quyết một lỗi

Nếu hai nhánh tạo hai migration khác nhau cho cùng một mục tiêu, đừng merge cả hai một cách máy móc. So sánh DDL/DML, xác định nhánh nào đã triển khai, giữ identity của thay đổi đã chạy và tạo migration bù cho phần còn thiếu. Không sửa lịch sử production để làm cho hai nhánh có cùng file.

## 10. Thứ tự changeset và dependency phải được review riêng

ID hoặc tên file có thể gợi ý thứ tự, nhưng dependency thực tế cần được thể hiện bằng thứ tự changelog và thiết kế migration.

Ví dụ:

```text
001-create-account-status
        |
        v
002-seed-status-values
        |
        v
003-add-account-status-column
        |
        v
004-backfill-account-status
        |
        v
005-add-not-null
        |
        v
006-add-foreign-key
```

Nếu một nhánh chỉ mang changeset 005 mà thiếu 002–004, việc include file có thể làm Liquibase gặp precondition fail hoặc DDL lỗi. Vì vậy, cherry-pick phải đi kèm các dependency cần thiết hoặc một migration được thiết kế lại cho trạng thái đích.

### 10.1. Tránh merge một changeset phụ thuộc thay đổi chưa có

Ví dụ `DB-600-add-status-index` giả định cột `status_code` tồn tại. Nếu merge vào main trước migration tạo cột, root changelog có thể nạp index trước và thất bại. Hãy đặt dependency trong cùng chuỗi release và kiểm tra thứ tự include.

Liquibase không đọc ý nghĩa nghiệp vụ trong tên ID để tự sắp xếp phụ thuộc. Precondition giúp phát hiện một số điều kiện thiếu, nhưng không thay thế thiết kế thứ tự.

## 11. Kiểm tra identity và history trước/sau merge

Bảng `DATABASECHANGELOG` là nguồn bằng chứng về changeset đã được xử lý trên từng database. Một truy vấn chỉ đọc thường dùng:

```sql
SELECT ID,
       AUTHOR,
       FILENAME,
       DATEEXECUTED,
       ORDEREXECUTED,
       EXECTYPE,
       MD5SUM
FROM DATABASECHANGELOG
ORDER BY ORDEREXECUTED, DATEEXECUTED;
```

Cấu trúc cột có thể khác theo phiên bản/cấu hình; phải xác nhận schema và tên bảng metadata thật trước khi chạy. Không dùng SQL để sửa lịch sử.

### 11.1. So sánh identity giữa hai môi trường

Lập bảng đối chiếu theo:

- ID.
- AUTHOR.
- FILENAME hoặc logical path.
- Checksum.
- Trạng thái thực thi và thời điểm.
- Phiên bản artifact/changelog đã triển khai.

Nếu staging có một identity mà production chưa có, điều đó có thể là trạng thái pending bình thường. Nhưng nếu cùng một thay đổi có hai đường dẫn khác nhau, phải điều tra xem có phải file đã bị di chuyển sau triển khai hoặc cùng một migration bị include hai lần.

### 11.2. Không so sánh chỉ theo ID

Cùng `ID` nhưng khác `AUTHOR` hoặc `FILENAME` vẫn có thể là identity khác. Vì vậy, báo cáo kiểm tra xung đột phải xét bộ ba, không chỉ grep ID trùng.

Ngược lại, nếu cùng bộ ba nhưng checksum khác, cần xác định nhánh nào đã triển khai nội dung nào. Không giải quyết bằng cách cập nhật `MD5SUM` trực tiếp.

## 12. Quy trình merge đề xuất cho nhóm

Một quy trình cộng tác có thể thực hiện như sau:

1. Developer tạo changeset mới với ID theo quy ước nhóm và author thống nhất.
2. Đặt file trong thư mục ổn định, thêm include đúng vị trí trong root changelog.
3. Chạy kiểm tra changelog, xem SQL dự kiến và thử trên DBMS tương ứng.
4. Pull/rebase nhánh mới nhất; giải quyết conflict root changelog bằng cách giữ cả thay đổi hợp lệ và đúng thứ tự dependency.
5. Kiểm tra identity của mọi changeset mới và các changeset đã triển khai.
6. Xác nhận không sửa file/identity lịch sử; nếu di chuyển file, có kế hoạch logicalFilePath.
7. Chạy `validate`, `status --verbose`, `update-sql` trên database thử nghiệm có history đại diện.
8. Review precondition, rollback, context/label và DBMS-specific SQL.
9. Merge code và build một artifact changelog cố định.
10. Triển khai cùng artifact qua các môi trường; hậu kiểm `DATABASECHANGELOG` và schema.

### 12.1. Merge xong nhưng chưa deploy: vẫn có thể điều chỉnh identity

Nếu changeset chưa được áp dụng ở bất kỳ database dùng chung nào, nhóm có thể sửa ID hoặc đường dẫn để giải quyết conflict trước khi phát hành. Nhưng cần xác nhận không có database cá nhân/staging nào đã chạy bản cũ và không có artifact đã được deploy.

Khi đã có môi trường dùng chung ghi nhận identity, hãy xem nó là lịch sử và tạo migration mới nếu cần thay đổi.

### 12.2. Không sửa changelog theo trạng thái một môi trường duy nhất

Một thay đổi có thể đã chạy trên staging nhưng chưa chạy production. Khi đó, nội dung changelog vẫn phải được giữ ổn định vì staging đã ghi nhận nó. Không sửa changeset chỉ để phù hợp với production; cần một changeset mới nếu yêu cầu thay đổi.

## 13. Các lỗi cộng tác thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Liquibase chạy lại changeset sau khi chuyển file | Logical path đổi, identity khác | Khôi phục path logic cũ bằng cơ chế được hỗ trợ, kiểm tra lịch sử |
| Checksum mismatch sau merge | Hai nhánh sửa cùng changeset đã chạy | Khôi phục nội dung lịch sử, tạo changeset mới cho điều chỉnh |
| Một changeset xuất hiện hai lần | Cùng migration được include từ nhiều root/path | Xác định một entry point và identity, loại include trùng trước khi triển khai |
| Cùng ID nhưng hai thay đổi khác nhau | Quy ước ID thiếu tính phân biệt hoặc nhánh tạo trùng | Đối chiếu cả ID/author/path, giải quyết trước deploy |
| Changeset phụ thuộc bảng chưa có | Thứ tự include hoặc cherry-pick thiếu dependency | Đưa các bước tiền đề vào chuỗi đúng, kiểm tra precondition |
| Git merge sạch nhưng update thất bại | Conflict vận hành không được phát hiện qua text merge | Review dependency, SQL và lịch sử database |
| Staging và production có FILENAME khác nhau | Đã di chuyển file hoặc cấu hình logical path không thống nhất | So sánh history từng môi trường và giữ identity |
| Hotfix chạy production nhưng merge ngược bị nhận diện mới | Cherry-pick làm thay đổi path hoặc nội dung | Giữ identity đã triển khai, kiểm tra logicalFilePath |
| Hai pipeline cùng cập nhật một database | Không có một chủ thể sở hữu migration | Điều phối pipeline và kiểm tra DATABASECHANGELOGLOCK |
| Rollback nhầm changeset của nhánh khác | History có thay đổi xen kẽ, phụ thuộc count/tag không được review | Xác định danh tính và mốc rollback thực tế trước preview |

Không giải quyết các vấn đề này bằng cách xóa record `DATABASECHANGELOG`, sửa checksum trực tiếp hoặc đánh dấu changeset đã chạy mà không đối chiếu schema. Những thao tác đó che giấu xung đột thay vì giải quyết nó.

## 14. Spring Boot và CI/CD: giữ một nguồn changelog nhất quán

Spring Boot thường cấu hình Liquibase qua classpath:

```yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
```

Trong nhóm có nhiều nhánh:

- Tất cả artifact cần dùng cùng root changelog đã được review.
- Các file include phải được đóng gói trong artifact.
- Không để một môi trường chạy root A và môi trường khác chạy root B nếu không có chủ đích kiến trúc.
- Nếu pipeline sở hữu migration, cân nhắc cấu hình ứng dụng không tự chạy Liquibase trong môi trường đó theo thiết kế.
- Nếu ứng dụng tự chạy migration lúc startup, phải quản lý thứ tự release và tránh hai nguồn điều phối đồng thời.

`DATABASECHANGELOGLOCK` giúp Liquibase điều phối process chạy đồng thời trên cùng database, nhưng không giải quyết xung đột ID, đường dẫn hay checksum. Lock cũng không bảo đảm một artifact khác không chạy migration ngoài ý muốn sau khi process trước kết thúc.

### 14.1. Cổng kiểm tra tự động nên có gì?

Một pipeline có thể kiểm tra:

1. Root changelog tồn tại và parse hợp lệ.
2. Mọi include/path tham chiếu tới file có trong artifact.
3. Bộ ba ID/author/logical path không bị trùng ngoài dự kiến.
4. Changeset đã triển khai không bị chỉnh sửa so với artifact lịch sử.
5. Di chuyển file có khai báo logical path được review.
6. Thứ tự dependency và DBMS/context/label phù hợp.
7. `validate` và `update-sql` đạt trên DBMS đại diện.
8. Rollback được khai báo/đánh giá cho thay đổi có rủi ro.
9. Preview và update dùng cùng artifact, cấu hình và filter.
10. Sau deploy, đối chiếu `DATABASECHANGELOG` và schema thực tế.

Các kiểm tra tự động không thay thế review domain, nhưng có thể ngăn nhiều lỗi identity và đường dẫn trước khi migration đến môi trường dùng chung.

## 15. Bài thực hành: hợp nhất hai nhánh Liquibase

**Bối cảnh:** nhánh A thêm cột email; nhánh B thêm cột phone vào `customer_account`. Cả hai nhánh cùng bắt đầu từ root changelog cũ và đều có một file changeset mới.

### Bước 1. Tạo hai nhánh

- Nhánh A tạo `DB-482-add-customer-email`.
- Nhánh B tạo `DB-497-add-customer-phone`.
- Mỗi nhánh thêm include vào root changelog.

### Bước 2. Cố ý tạo một conflict identity trong lab

Trong một bản lab riêng, đặt cùng `id`, `author` và logical path cho hai changeset có nội dung khác nhau. Thử merge và quan sát kết quả kiểm tra/triển khai trên database thử nghiệm. Không đưa identity xung đột này vào môi trường dùng chung.

### Bước 3. Giải quyết identity

Đổi ID của các changeset **chưa triển khai ở bất kỳ database dùng chung nào** theo mã công việc riêng. Nếu một changeset đã chạy, giữ identity và nội dung đã triển khai; tạo changeset mới cho phần điều chỉnh.

### Bước 4. Hợp nhất root changelog

Đưa cả hai include vào root, sắp xếp theo dependency. Kiểm tra không có file bị include trùng qua include và includeAll.

### Bước 5. Thử di chuyển file

Di chuyển một changeset đã chạy trong database lab. Quan sát thay đổi `FILENAME` và cách Liquibase nhận diện. Khôi phục identity bằng `logicalFilePath` đúng cú pháp phiên bản đang dùng; xác minh status không coi nó là migration mới.

### Bước 6. Đối chiếu lịch sử

Chạy `history`, `status --verbose` và truy vấn chỉ đọc `DATABASECHANGELOG`. Xác nhận bộ ba identity, checksum và thứ tự giữa hai môi trường lab.

### Bước 7. Kiểm tra pipeline

Build artifact, xác nhận root changelog và file include có trong classpath; chạy `validate` và `update-sql` trên database thử nghiệm.

**Tiêu chí hoàn thành:** hai thay đổi độc lập được giữ nguyên; không identity nào bị nhân đôi ngoài dự kiến; file đã triển khai giữ đường dẫn logic; thứ tự dependency rõ ràng; history và schema sau thử nghiệm nhất quán.

## 16. Checklist trước khi merge changelog

- [ ] Changeset mới có ID theo quy ước và không xung đột với identity đã có.
- [ ] Author được dùng nhất quán; không đổi author của changeset đã triển khai.
- [ ] File nằm trong thư mục ổn định và root changelog include đúng một lần.
- [ ] Đường dẫn logic của changeset đã chạy được giữ nguyên.
- [ ] Nếu di chuyển file, `logicalFilePath` được thiết kế dựa trên `FILENAME` lịch sử thật và cú pháp phiên bản.
- [ ] Changeset đã triển khai không bị sửa nội dung, ID, author hoặc path tùy tiện.
- [ ] Conflict Git và conflict dependency database đều được review.
- [ ] Cherry-pick/hotfix giữ nguyên identity đã chạy và mang theo dependency cần thiết.
- [ ] Thứ tự include được xác định rõ; không dựa vào số ID để Liquibase tự sắp xếp.
- [ ] includeAll không nạp nhầm file và có quy tắc thứ tự ổn định.
- [ ] Root changelog nhất quán giữa ứng dụng, CI/CD và các môi trường.
- [ ] `validate`, `status`, `update-sql` và kiểm thử trên DBMS đại diện đạt.
- [ ] Checksum mismatch được điều tra bằng nội dung/commit/artifact, không sửa MD5SUM trực tiếp.
- [ ] Hậu kiểm `DATABASECHANGELOG` sau deploy xác nhận đúng identity và checksum.
- [ ] Có quy trình giải quyết nếu hai nhánh cùng sửa một migration đã triển khai.

**Kết luận:** cộng tác Liquibase an toàn đòi hỏi cả nhóm giữ ổn định bộ ba `id`, `author` và đường dẫn logic của changeset. Checksum phát hiện nội dung đã thay đổi; nó không thay thế identity. Khi hợp nhất nhánh, hãy giải quyết xung đột trước deploy, giữ changelog đã triển khai theo quy tắc append-only, dùng `logicalFilePath` có kiểm chứng khi di chuyển file và review thứ tự dependency. Làm được những điều này giúp các database ở development, staging và production cùng tiến qua một lịch sử migration có thể giải thích và truy vết.

