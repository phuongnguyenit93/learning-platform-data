# Làm việc trên nhiều nhánh và xử lý xung đột changelog

Trong một nhóm phát triển, nhiều tính năng thường thay đổi database cùng lúc. Nhánh A thêm cột cho đơn hàng, nhánh B tạo index cho báo cáo, nhánh C cập nhật view. Mỗi nhánh có thể chạy tốt trên database riêng, nhưng khi hợp nhất mã nguồn, các changelog có thể xung đột về tên file, thứ tự include, định danh changeset hoặc phụ thuộc schema. Nếu những nhánh đó đã triển khai lên cùng một database theo thứ tự khác nhau, vấn đề còn khó xử lý hơn: lịch sử Liquibase và schema thực tế có thể không còn khớp với giả định của nhánh mới.

Bài học thuộc chương **Cộng tác** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Phạm vi module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Bài học tập trung vào cách tổ chức changelog khi nhiều người làm việc trên nhiều nhánh Git, cách tránh xung đột định danh và thứ tự, cách giải quyết conflict khi merge/rebase, và cách đồng bộ quy trình phát hành để các database nhận cùng một lịch sử migration có thể dự đoán.

Sau bài học, bạn có thể:

1. Giải thích vì sao changelog là một phần của mã nguồn cần được review và quản lý cùng nhánh tính năng.
2. Thiết kế quy ước changeset ID, author, filename và cấu trúc thư mục để giảm va chạm.
3. Phân biệt xung đột văn bản Git với xung đột ngữ nghĩa của migration.
4. Sắp xếp thứ tự include và dependency khi hợp nhất nhiều nhánh.
5. Xử lý checksum mismatch và changeset đã triển khai theo nguyên tắc bất biến lịch sử.
6. Hiểu giới hạn của DATABASECHANGELOGLOCK khi nhiều pipeline hoặc người dùng cùng cập nhật.
7. Thiết kế CI/CD, database test cách ly và quy trình tích hợp nhánh để phát hiện lỗi trước khi phát hành.

## 1. Vì sao nhiều nhánh Git dễ xung đột changelog?

Giả sử một nhóm có nhánh chính main và ba nhánh tính năng:

~~~text
main
 ├── feature/order-status
 ├── feature/report-index
 └── feature/customer-view
~~~

Mỗi nhánh tạo thay đổi database riêng:

- feature/order-status: thêm cột orders.status.
- feature/report-index: tạo index trên orders.created_at.
- feature/customer-view: tạo hoặc sửa view customer_summary.

Các thay đổi có thể độc lập về mã ứng dụng nhưng cùng chạm vào một changelog gốc, cùng bảng orders, hoặc phụ thuộc lẫn nhau. Khi merge, nhóm có thể gặp các loại vấn đề:

| Loại vấn đề | Ví dụ | Hậu quả |
|---|---|---|
| Conflict văn bản | Hai nhánh cùng sửa db.changelog-master.yaml | Git yêu cầu chọn và hợp nhất nội dung |
| Trùng định danh | Hai changeset dùng cùng ID, author và logical path | Liquibase có thể coi chúng là cùng identity hoặc phát hiện định nghĩa trùng |
| Sai thứ tự | View được tạo trước bảng/cột mà nó tham chiếu | Migration thất bại |
| Phụ thuộc ẩn | Nhánh B giả định cột do nhánh A tạo đã tồn tại | B chạy riêng được ở nhánh A nhưng lỗi khi phát hành |
| Checksum mismatch | Nhánh sửa changeset đã triển khai | Validate/update có thể báo checksum khác |
| Drift môi trường | Nhánh A đã update shared dev DB, nhánh B rollback hoặc sửa schema thủ công | Database không còn khớp changelog tích hợp |
| Conflict rollback | Hai nhánh cùng thay đổi một đối tượng và rollback không độc lập | Hoàn tác một nhánh có thể phá thay đổi của nhánh kia |

Điểm quan trọng là **Git merge thành công không có nghĩa changelog tích hợp đúng về mặt database**. Git giải quyết xung đột nội dung file; Liquibase và database mới quyết định migration có thể thực thi theo thứ tự và trạng thái thực tế hay không.

## 2. Changelog là mã nguồn có lịch sử triển khai

Changelog nên được quản lý trong repository cùng mã ứng dụng hoặc repository database chuyên biệt. Mỗi changeset là một đơn vị thay đổi có định danh, nội dung và lịch sử triển khai.

Ví dụ:

~~~text
db/
  changelog/
    db.changelog-master.yaml
    baseline/
      001-create-customer.yaml
      002-create-orders.yaml
    releases/
      2026/
        11/
          ORD-241-add-order-status.yaml
          RPT-118-add-orders-created-index.yaml
          CRM-092-update-customer-summary.yaml
~~~

Tên file có thể dùng ticket hoặc mã công việc để giảm va chạm. Tuy nhiên, **tên file không thay thế identity của changeset**; vẫn phải quản lý ID, author và logical path.

Những thay đổi sau cần đi cùng code review:

- Changelog mới và thứ tự include.
- Nội dung changeset và SQL tùy chỉnh.
- Precondition và rollback.
- Context, labels, dbms và các thuộc tính chạy lại.
- Thay đổi đường dẫn hoặc cách include file.
- Tác động đến các môi trường đã triển khai.

Không nên xem changelog là file cấu hình phụ có thể sửa nhanh sau khi merge. Nó là một phần của hợp đồng schema giữa ứng dụng và database.

## 3. Hiểu đúng identity của changeset

Liquibase thường nhận diện changeset bằng bộ ba:

~~~text
ID + AUTHOR + FILENAME (hoặc logicalFilePath)
~~~

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "ORD-241-add-order-status"
      author: "orders-team"
      changes:
        - addColumn:
            tableName: orders
            columns:
              - column:
                  name: status
                  type: varchar(24)
~~~

Giả sử hai nhánh có changeset cùng ID nhưng nằm ở hai file khác nhau. Nếu author giống nhau, filename khác nhau thì identity theo bộ ba vẫn khác. Tuy vậy, dùng ID duy nhất toàn repository là quy ước tốt vì dễ tìm kiếm, review và tránh nhầm lẫn khi di chuyển file.

### 3.1. Quy ước ID nên có tính duy nhất và dễ truy vết

Một số cách đặt:

~~~text
ORD-241-add-order-status
RPT-118-add-orders-created-index
CRM-092-refresh-customer-summary
20261119-001-add-invoice-reference
~~~

Nên ưu tiên:

- Mã ticket hoặc mã công việc có tính duy nhất.
- Tên ngắn mô tả thay đổi.
- Không tái sử dụng ID đã xuất hiện trong lịch sử.
- Không dùng số tăng dần cục bộ trên từng nhánh nếu nhiều người có thể chọn cùng số.
- Thống nhất quy ước author giữa các nhóm.
- Giữ filename/logicalFilePath ổn định sau khi triển khai.

Không cần dùng tên người thật trong author nếu quy ước tổ chức dùng tên nhóm hoặc service owner; quan trọng là có thể truy vết trách nhiệm.

### 3.2. Trùng ID không phải conflict duy nhất cần tránh

Ngay cả khi bộ ba identity khác nhau, hai changeset vẫn có thể cùng tạo idx_orders_status hoặc cùng thêm cột orders.status. Khi đó Git không nhất thiết báo conflict, nhưng database sẽ báo duplicate object hoặc hai thay đổi có ý nghĩa trùng lặp.

Review phải kiểm tra cả **định danh Liquibase** và **đối tượng database mà changeset tác động**.

## 4. Mỗi nhánh nên có file changeset riêng

Một quy ước giảm conflict là mỗi nhánh tạo file migration riêng, thay vì tất cả cùng sửa một file lớn.

Ví dụ:

~~~text
feature/order-status
  -> ORD-241-add-order-status.yaml

feature/report-index
  -> RPT-118-add-orders-created-index.yaml

feature/customer-view
  -> CRM-092-update-customer-summary.yaml
~~~

Sau khi merge, changelog gốc include các file:

~~~yaml
databaseChangeLog:
  - include:
      file: releases/2026/11/ORD-241-add-order-status.yaml
      relativeToChangelogFile: true
  - include:
      file: releases/2026/11/RPT-118-add-orders-created-index.yaml
      relativeToChangelogFile: true
  - include:
      file: releases/2026/11/CRM-092-update-customer-summary.yaml
      relativeToChangelogFile: true
~~~

Cách này giúp conflict ở file nội dung migration giảm đi. Tuy nhiên, **file master vẫn có thể xung đột** vì nhiều nhánh cùng thêm include. Cần quy định rõ ai hoặc bước nào chịu trách nhiệm tích hợp danh sách include vào nhánh chính.

### 4.1. Có thể dùng includeAll không?

Liquibase có cơ chế **includeAll** để nạp các file trong một thư mục theo quy tắc của nó. Cơ chế này giảm việc nhiều nhánh sửa master cho mỗi file mới, nhưng cần cân nhắc:

- Tên file và thứ tự nạp có xác định, ổn định không?
- Có file thử nghiệm hoặc file chưa hoàn tất bị nạp nhầm không?
- Dependency giữa changeset có thể được biểu diễn bằng thứ tự file không?
- File mới có thể làm thay đổi thứ tự triển khai khi merge không?
- Có thể giới hạn đệ quy và loại file theo cấu hình đang dùng không?

Không dựa vào thứ tự includeAll như một cơ chế quản lý dependency phức tạp. Nếu migration cần thứ tự cụ thể, **include tường minh** dễ review và dễ kiểm soát hơn. Cần xác minh hành vi includeAll theo phiên bản Liquibase và loại changelog.

## 5. Tổ chức master changelog để giảm conflict

Có một số mô hình:

| Mô hình | Cách hoạt động | Phù hợp |
|---|---|---|
| **Master include tường minh** | Mỗi file mới được thêm vào master | Dự án nhỏ, cần thứ tự rõ |
| **IncludeAll theo thư mục** | Liquibase nạp các file trong thư mục theo quy tắc | Nhiều thay đổi độc lập, quy ước tên file ổn định |
| **Master theo release** | Master include từng changelog release; release include changeset con | Nhóm nhiều service/nhóm database |
| **Root changelog phân vùng** | Chia theo domain/schema rồi root include từng vùng | Hệ thống lớn, có ownership rõ |

Ví dụ master theo release:

~~~yaml
databaseChangeLog:
  - include:
      file: releases/2026/11/db.changelog-2026-11.yaml
      relativeToChangelogFile: true
  - include:
      file: releases/2026/12/db.changelog-2026-12.yaml
      relativeToChangelogFile: true
~~~

File release:

~~~yaml
databaseChangeLog:
  - include:
      file: ORD-241-add-order-status.yaml
      relativeToChangelogFile: true
  - include:
      file: RPT-118-add-orders-created-index.yaml
      relativeToChangelogFile: true
~~~

Cấu trúc này gom thay đổi theo đợt phát hành, nhưng vẫn phải giải quyết conflict trong file release nếu nhiều nhánh thêm include cùng lúc.

**Không đổi thứ tự include tùy tiện sau khi changeset đã triển khai.** Thay đổi thứ tự có thể ảnh hưởng dependency hoặc làm lịch sử chạy khác nhau trên database mới so với database cũ.

## 6. Xử lý conflict văn bản trong Git

Khi hai nhánh cùng thêm nội dung vào master changelog, Git có thể tạo conflict marker:

~~~yaml
databaseChangeLog:
  - include:
      file: ORD-241-add-order-status.yaml
      relativeToChangelogFile: true
<<<<<<< HEAD
  - include:
      file: CRM-092-update-customer-summary.yaml
      relativeToChangelogFile: true
=======
  - include:
      file: RPT-118-add-orders-created-index.yaml
      relativeToChangelogFile: true
>>>>>>> feature/report-index
~~~

Đây là marker do Git tạo, không phải YAML hợp lệ. Người giải quyết conflict phải:

1. Giữ cả hai include nếu cả hai thay đổi đều cần tích hợp.
2. Xác định thứ tự dependency giữa chúng.
3. Xóa toàn bộ marker <<<<<<<, =======, >>>>>>>.
4. Kiểm tra thụt đầu dòng và cú pháp YAML.
5. Xác minh đường dẫn tương đối tới từng file.
6. Chạy validate và kiểm tra status/update-sql trên database thử nghiệm.

Không chọn một phía theo thói quen accept ours hoặc accept theirs mà chưa xem nội dung migration. Một phía có thể chứa thay đổi schema bắt buộc cho phía còn lại.

### 6.1. Conflict trong file changeset

Nếu hai nhánh cùng sửa một file migration chưa triển khai, hãy hợp nhất ý định thành một changeset hợp lệ hoặc tách thành changeset riêng. Không để lại hai bản SQL tương tự nhau chỉ để hết conflict.

Nếu file đã được triển khai trên bất kỳ môi trường dùng chung nào, phải xử lý như một thay đổi lịch sử: xác minh checksum và schema thực tế trước khi sửa. Khi changeset đã phát hành, thường nên thêm changeset mới thay vì viết lại nội dung cũ.

## 7. Conflict ngữ nghĩa: Git không phát hiện được

Ví dụ nhánh A:

~~~yaml
- changeSet:
    id: "ORD-241-add-status"
    author: "orders-team"
    changes:
      - addColumn:
          tableName: orders
          columns:
            - column:
                name: status
                type: varchar(24)
~~~

Nhánh B:

~~~yaml
- changeSet:
    id: "RPT-118-add-status-index"
    author: "reporting-team"
    changes:
      - createIndex:
          tableName: orders
          indexName: idx_orders_status
          columns:
            - column:
                name: status
~~~

Git có thể merge hai file mà không conflict. Nhưng nếu changeset tạo index chạy trước changeset thêm cột, migration sẽ thất bại.

Đây là **xung đột phụ thuộc**. Người review cần hiểu quan hệ giữa đối tượng:

~~~mermaid
flowchart TD
    A[Thêm cột orders.status] --> B[Tạo index trên orders.status]
    B --> C[Ứng dụng truy vấn status]
~~~

Thứ tự đúng phải bảo đảm cột tồn tại trước khi index được tạo. Một precondition kiểm tra columnExists có thể giúp phát hiện trạng thái không đạt, nhưng không thay thế việc sắp xếp dependency trong changelog.

## 8. Thiết kế dependency giữa các nhánh

Trước khi phát triển, nhóm nên ghi rõ các migration phụ thuộc:

- Nhánh B cần cột do nhánh A tạo.
- Nhánh C thay đổi view dựa trên cột của A.
- Nhánh D thêm foreign key dựa trên bảng của một nhóm khác.

Có ba cách tổ chức thường gặp:

**Cách 1 — Phối hợp thứ tự merge.** Merge migration nền trước, sau đó merge nhánh phụ thuộc.

**Cách 2 — Tạo nhánh tích hợp.** Merge các nhánh liên quan vào một nhánh integration, kiểm tra thứ tự và test trên database sạch.

**Cách 3 — Tách thay đổi thành các bước tương thích.** Ví dụ thêm cột nullable trước, triển khai ứng dụng tương thích, backfill sau rồi mới thêm constraint.

Không nên để nhánh phụ thuộc âm thầm vào một database developer đã được cập nhật thủ công. Mỗi nhánh phải mô tả rõ những thay đổi mà nó cần.

### 8.1. Precondition không sửa được dependency sai

Ví dụ:

~~~yaml
preConditions:
  - onFail: HALT
  - onError: HALT
  - columnExists:
      tableName: orders
      columnName: status
~~~

Điều kiện này giúp dừng khi cột chưa tồn tại. Nhưng nếu changeset tạo index được include trước changeset thêm cột, migration vẫn thất bại. **Precondition phát hiện điều kiện không đạt; nó không tự sắp xếp lại changelog.**

Tránh dùng MARK_RAN cho tình huống thiếu dependency. Nếu cột chưa tồn tại, đánh dấu changeset index đã chạy sẽ làm lịch sử sai và index vẫn không có.

## 9. Thứ tự changeset sau khi merge

Liquibase xét changeset theo thứ tự changelog được nạp, chịu ảnh hưởng của include, includeAll và cấu hình/filter. Do đó, thứ tự trong Git merge commit không nhất thiết là thứ tự chạy migration.

Ví dụ:

~~~text
db.changelog-master.yaml
  1. baseline
  2. add-order-status
  3. add-order-status-index
  4. update-customer-view
~~~

Khi hợp nhất nhiều nhánh:

- Đưa migration tạo object nền trước migration tham chiếu object đó.
- Giữ thứ tự phụ thuộc đã được review.
- Không sắp xếp lại các file chỉ để tên file trông đẹp.
- Không thay đổi include order đã phát hành nếu không có đánh giá tác động.
- Chạy test trên database mới để xác nhận thứ tự có thể dựng schema.

### 9.1. Thứ tự trong changelog không phải thứ tự commit Git

Một commit Git có thể chứa nhiều file changeset. Liquibase không tự đọc thời gian commit để quyết định thứ tự thực thi. Nó theo changelog đã cấu hình và thứ tự nạp.

Vì vậy, không dựa vào timestamp commit hoặc thứ tự PR merge để suy ra migration sẽ chạy theo thứ tự đó.

## 10. Quy tắc bất biến: không sửa changeset đã triển khai

Một changeset đã chạy trên shared integration, staging hoặc production nên được xem là **bất biến**.

Ví dụ changeset đã triển khai:

~~~yaml
- changeSet:
    id: "ORD-241-add-status"
    author: "orders-team"
    changes:
      - addColumn:
          tableName: orders
          columns:
            - column:
                name: status
                type: varchar(24)
~~~

Sau khi chạy, một nhánh muốn đổi varchar(24) thành varchar(32). Nếu sửa trực tiếp changeset cũ:

- Nội dung có thể không còn khớp checksum lưu trong DATABASECHANGELOG.
- Các database đã triển khai và chưa triển khai có thể phản ứng khác nhau.
- Một môi trường mới có thể tạo cột kiểu 32 trong khi môi trường cũ vẫn giữ kiểu 24.
- Lịch sử không còn mô tả rõ thay đổi nào đã xảy ra.

Cách đúng thường là tạo changeset mới:

~~~yaml
- changeSet:
    id: "ORD-318-expand-status-length"
    author: "orders-team"
    changes:
      - modifyDataType:
          tableName: orders
          columnName: status
          newDataType: varchar(32)
~~~

SQL thực tế và rollback phải được kiểm tra theo DBMS. Nếu changeset cũ chưa được triển khai ở bất kỳ môi trường dùng chung nào, nhóm có thể chỉnh sửa trong nhánh phát triển trước khi phát hành, nhưng phải xác nhận không có database nào đã ghi nhận identity đó.

### 10.1. Không dùng clear-checksums để hợp thức hóa sửa lịch sử

clear-checksums có mục đích quản lý checksum trong các tình huống được kiểm soát; nó không biến việc sửa changeset đã triển khai thành an toàn và không đồng bộ schema giữa môi trường.

Khi checksum mismatch:

1. Xác định changeset identity và môi trường đã triển khai.
2. Lấy artifact changelog đã phát hành trước đó.
3. So sánh nội dung và checksum.
4. Kiểm tra schema thật.
5. Tạo changeset mới cho thay đổi tiếp theo nếu phù hợp.
6. Chỉ sử dụng thao tác quản lý checksum đặc biệt khi đã có quyết định và kế hoạch được review.

## 11. Xung đột filename và logicalFilePath

Một nhánh có thể di chuyển file migration:

~~~text
releases/2026/11/ORD-241-add-order-status.yaml
~~~

sang:

~~~text
domains/orders/ORD-241-add-order-status.yaml
~~~

Liquibase có thể coi đường dẫn thay đổi là một phần của identity. Trên database đã lưu FILENAME cũ, đường dẫn mới có thể khiến changeset bị nhận diện như một identity khác.

Nếu cần tái cấu trúc thư mục:

- Giữ đường dẫn logic tương thích bằng logicalFilePath khi phiên bản/định dạng hỗ trợ.
- Kiểm tra cú pháp và phạm vi áp dụng logicalFilePath của phiên bản đang dùng.
- Đối chiếu giá trị FILENAME trong DATABASECHANGELOG.
- Test trên bản sao database đã triển khai và database mới.
- Không chỉ đổi path trong Git rồi giả định Liquibase tự hiểu đó là cùng changeset.

Đây là lý do nên ổn định cấu trúc changelog trước khi phát hành rộng.

## 12. Nhiều nhánh tạo changeset cùng tác động một đối tượng

Ví dụ hai nhánh độc lập đều muốn thêm index cho bảng orders:

- Nhánh A tạo idx_orders_created_at.
- Nhánh B cũng tạo index cùng cột nhưng đặt tên idx_orders_created.

Git không phát hiện conflict vì hai file khác nhau. Nhưng sau merge, có thể tồn tại hai index gần như trùng lặp, tăng chi phí ghi và lưu trữ.

Trước khi merge:

1. Tìm kiếm changelog toàn repository theo table/column/index name.
2. Kiểm tra các changeset đã có và đang phát triển.
3. Trao đổi với owner của bảng.
4. Quyết định một index chung hoặc hai index có mục đích khác nhau.
5. Kiểm tra query plan và workload nếu cần.
6. Loại bỏ migration thừa trước khi triển khai.

Tương tự, hai nhánh cùng thêm cột có ý nghĩa khác nhau nhưng cùng tên là conflict schema cần giải quyết ở thiết kế dữ liệu, không chỉ đổi tên changeset ID.

## 13. Xung đột do thay đổi dữ liệu

Migration dữ liệu có thể xung đột dù schema không xung đột.

Ví dụ nhánh A chuẩn hóa giá trị:

~~~sql
UPDATE customer
SET status = upper(status);
~~~

Nhánh B giả định status đã được chuẩn hóa và dùng giá trị đó để backfill cột khác.

Nếu B chạy trước A, dữ liệu có thể bị bỏ sót. Nếu A chạy sau B, điều kiện hoặc mapping có thể không còn đúng.

Cần:

- Mô tả dependency dữ liệu giữa changeset.
- Thiết kế update có phạm vi xác định và có thể kiểm tra.
- Kiểm tra số hàng trước/sau.
- Đảm bảo thao tác chạy lại không gây nhân đôi tác động.
- Xác định rollback có thể khôi phục giá trị cũ không.
- Test với dữ liệu đại diện, bao gồm NULL, giá trị cũ và ngoại lệ.

Không dựa vào thứ tự nhánh Git để bảo đảm thứ tự dữ liệu; phải thể hiện dependency trong release changelog và quy trình triển khai.

## 14. Context và labels không phải cơ chế thay thế quản lý nhánh

Có thể gắn context hoặc label cho changeset:

~~~yaml
- changeSet:
    id: "RPT-118-add-reporting-index"
    author: "reporting-team"
    labels: reporting
    context: reporting
    changes:
      - createIndex:
          tableName: orders
          indexName: idx_orders_created_at
          columns:
            - column:
                name: created_at
~~~

Những thuộc tính này có thể lọc changeset khi chạy Liquibase theo cấu hình. Nhưng không nên dùng context/label như cách tự động chọn “changeset thuộc nhánh Git nào”.

Lý do:

- Nhánh có thể merge vào main nhưng context cũ vẫn còn.
- Môi trường có thể chạy filter khác nhau.
- Changeset bị bỏ qua trong một lần update có thể làm thiếu dependency.
- Context/label không thay thế thứ tự include hoặc identity.

Dùng chúng cho mục đích triển khai thực sự như nhóm tính năng, DBMS hoặc môi trường, với chính sách rõ ràng. Không dùng chúng để che changeset chưa được tích hợp.

## 15. Shared development database: tiện nhưng rủi ro

Nhiều developer có thể cùng dùng một database dev để kiểm thử. Điều này tạo feedback nhanh nhưng dễ phát sinh drift:

- Nhánh A chạy update và thêm cột.
- Nhánh B chưa có changeset A nhưng ứng dụng B vẫn chạy nhờ cột tồn tại trong DB dev.
- B được merge và triển khai lên database sạch thì lỗi vì thiếu cột.
- Một developer rollback nhánh A làm hỏng môi trường mà nhánh B đang dùng.

**Shared database không phải đại diện đáng tin cậy cho trạng thái của từng nhánh.**

Ưu tiên:

- Database riêng cho mỗi nhánh hoặc mỗi CI job.
- Container/database ephemeral có cùng DBMS với mục tiêu.
- Dữ liệu seed có phiên bản và tái tạo được.
- Database tích hợp chung chỉ dùng cho kiểm thử phối hợp đã lên lịch.
- Ghi rõ changeset đã được áp dụng trên môi trường nào.

### 15.1. Nếu buộc phải dùng database chung

Thiết lập quy tắc:

1. Chỉ một pipeline hoặc người được phân công thực hiện migration tại một thời điểm.
2. Không tự ý rollback changeset của nhánh khác.
3. Ghi nhận artifact và danh sách changeset đã chạy.
4. Reset/rebuild môi trường bằng quy trình đã thống nhất nếu drift quá lớn.
5. Không lấy database chung làm bằng chứng duy nhất rằng nhánh riêng có thể dựng schema.

## 16. DATABASECHANGELOGLOCK giải quyết vấn đề nào?

Liquibase sử dụng **DATABASECHANGELOGLOCK** để điều phối việc thực thi migration trên một database. Cơ chế này giúp ngăn hai tiến trình Liquibase cùng chạy update đồng thời trên cùng metadata database theo cách không được kiểm soát.

Nhưng lock này **không giải quyết mọi xung đột cộng tác**:

- Không hợp nhất file changelog trong Git.
- Không phát hiện hai nhánh tạo cùng một index trước khi chạy.
- Không bảo đảm include order đúng.
- Không chặn DBA chạy DDL trực tiếp.
- Không chặn ứng dụng ghi dữ liệu trong khi migration.
- Không làm cho DDL implicit commit trở nên transactional.
- Không thay thế review và CI.

### 16.1. Khi pipeline phải chờ lock

Nếu một job đang chạy Liquibase, job khác có thể phải chờ hoặc báo không lấy được lock tùy cấu hình và thời gian chờ.

Quy trình xử lý:

1. Xác định job/pipeline nào đang giữ lock.
2. Kiểm tra tiến trình còn hoạt động không.
3. Xem log của job đang chạy.
4. Không xóa lock chỉ vì job mới đang chờ.
5. Chỉ xử lý lock bị kẹt sau khi xác minh không còn migration hoạt động.
6. Sau khi xử lý, kiểm tra schema và DATABASECHANGELOG.

Giải phóng lock không tự hoàn nguyên một changeset đã thay đổi schema trước khi tiến trình bị dừng.

## 17. Rebase và merge: tác động tới changelog

Một nhánh feature lâu ngày có thể tạo changeset dựa trên trạng thái main cũ. Trong lúc đó, main đã nhận những migration khác.

Khi rebase:

- Changelog mới từ main được đưa vào lịch sử nhánh.
- File changeset của feature vẫn phải được giữ.
- Master include có thể cần cập nhật theo cấu trúc mới.
- Dependency phải được đánh giá lại.
- Không thay đổi ID/author/path chỉ để giải quyết conflict.
- Chạy lại validate và integration test trên database mới.

Ví dụ các lệnh Git minh họa:

~~~bash
git fetch origin
git rebase origin/main
~~~

Hoặc merge:

~~~bash
git fetch origin
git merge origin/main
~~~

Lệnh Git chỉ giải quyết lịch sử mã nguồn. Sau đó vẫn phải kiểm tra changelog, include order, SQL và schema. Không xem rebase/merge hoàn tất là migration đã được tích hợp đúng.

### 17.1. Khi rebase làm thay đổi commit

Việc rebase tạo commit mới không tự làm thay đổi changeset identity. Liquibase không dùng Git commit hash làm định danh changeset mặc định. Tuy nhiên, nếu nội dung changelog hoặc path bị sửa trong quá trình rebase, checksum/identity có thể thay đổi.

## 18. Quy trình tích hợp nhánh feature đề xuất

Một luồng làm việc có thể áp dụng:

~~~mermaid
flowchart TD
    A[Developer tạo feature branch] --> B[Thêm changeset file riêng]
    B --> C[Kiểm tra ID, dependency và rollback]
    C --> D[CI chạy validate và test DB riêng]
    D --> E[Review PR]
    E --> F[Merge vào integration/main]
    F --> G[Kiểm tra master include và thứ tự]
    G --> H[Test changelog trên database sạch]
    H --> I[Test nâng cấp từ baseline đại diện]
    I --> J[Review update-sql và phát hành]
~~~

Chi tiết:

1. Tạo changeset file riêng, ID duy nhất.
2. Ghi rõ bảng/cột/object bị tác động và dependency.
3. Thêm precondition phù hợp, không dùng MARK_RAN để bỏ qua lỗi.
4. Viết rollback hoặc nêu rõ phương án forward fix nếu không thể đảo ngược.
5. CI chạy validate và test trên database cách ly.
6. Review SQL, include path, identity và thứ tự.
7. Merge vào nhánh tích hợp.
8. Chạy test từ database trống và database có baseline.
9. Sinh update-sql/rollback-sql để review.
10. Phát hành theo thứ tự đã được phê duyệt.

## 19. Hai loại database test cần có

Một bộ kiểm thử nhánh nên có hai baseline khác nhau:

| Loại database | Mục đích | Điều phát hiện |
|---|---|---|
| **Database trống** | Chạy toàn bộ changelog từ đầu | Thiếu include, sai thứ tự, thiếu dependency hoặc baseline không dựng được |
| **Database đã có baseline** | Mô phỏng môi trường hiện hữu rồi áp dụng migration mới | Lỗi nâng cấp, precondition, checksum và khác biệt schema cũ |

Nếu dự án có nhiều DBMS chính thức, chạy test trên từng DBMS/driver được hỗ trợ. Một test chỉ dùng H2 có thể không phát hiện lỗi dialect, DDL implicit commit hoặc locking của PostgreSQL/MySQL/Oracle/SQL Server.

### 19.1. Test database riêng cho mỗi nhánh

Mỗi CI job nên có database/schema riêng, tên có thể gắn với pipeline run ID. Điều này tránh:

- Changeset nhánh khác làm thay đổi trạng thái test.
- Rollback phá dữ liệu của job đang chạy.
- Một nhánh vô tình dựa vào migration chưa có trong repository.
- DATABASECHANGELOG của job trước ảnh hưởng job sau.

Dọn database test theo chính sách của CI sau khi đã lưu log và kết quả cần thiết.

## 20. Kiểm tra changelog sau merge

Sau khi merge, chạy các bước phù hợp với phiên bản Liquibase dự án:

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml validate

liquibase --changelog-file=db/changelog/db.changelog-master.yaml status --verbose

liquibase --changelog-file=db/changelog/db.changelog-master.yaml update-sql
~~~

Review:

- Changelog gốc có include đủ file không?
- Có file nào bị include hai lần?
- Có changeset ID/author/path bị trùng ngoài ý muốn không?
- Changeset phụ thuộc có đứng sau object nền không?
- SQL có nhắm đúng schema không?
- Context/label filter có làm thiếu migration không?
- Có thay đổi nào đang bị MARK_RAN hoặc runAlways/runOnChange ngoài chủ đích?
- Có DROP/ALTER phá hủy nào do conflict merge tạo ra không?

**status** không thay thế validate, và update-sql không chứng minh SQL thực thi thành công. Cần chạy integration test trên DBMS mục tiêu.

## 21. Xung đột checksum khi hai nhánh sửa cùng changeset

Giả sử một changeset đã triển khai ở staging. Nhánh A đổi kiểu dữ liệu, nhánh B đổi comment. Khi merge, một trong hai nhánh có thể đã sửa trực tiếp file changeset cũ.

Hậu quả có thể là checksum mismatch trên staging/production, trong khi database mới lại tạo schema theo nội dung đã sửa. Hai môi trường cùng dùng một changelog repository nhưng có kết quả khác nhau.

Cách giải quyết:

1. Xác định changeset đã triển khai ở đâu.
2. Khôi phục nội dung đã phát hành làm mốc lịch sử nếu cần.
3. Tạo changeset mới cho thay đổi kiểu dữ liệu/comment.
4. Xem update-sql trên database có history thật.
5. Xác minh dữ liệu và schema.
6. Không clear-checksums hoặc sửa DATABASECHANGELOG chỉ để làm pipeline xanh.

Nếu changeset chỉ tồn tại trên nhánh cá nhân và chưa được triển khai ở bất kỳ database dùng chung nào, nhóm có thể chỉnh sửa trước khi merge, nhưng cần thống nhất một bản cuối cùng.

## 22. Khi hai nhánh có migration đã chạy trên cùng shared environment

Đây là trường hợp phức tạp hơn conflict Git.

Giả sử:

- Nhánh A đã chạy changeset A trên dev chung.
- Nhánh B cũng đã chạy changeset B trên dev chung.
- A phụ thuộc B nhưng master changelog tích hợp lại sắp A trước B.

Database dev có thể chạy được vì B đã được áp dụng trước, nhưng database sạch sẽ thất bại vì A chạy trước B.

**Lịch sử thực thi trên shared database không tự phản ánh thứ tự changelog tích hợp.**

Cách xử lý:

1. Ghi lại history thực tế của database chung.
2. Xác định dependency giữa A và B.
3. Kiểm tra cả schema và DATABASECHANGELOG.
4. Tạo database mới và chạy changelog tích hợp từ đầu.
5. Nếu thứ tự tích hợp sai, sửa changelog trước khi phát hành.
6. Không sửa ID/path của A hoặc B đã triển khai chỉ để thay đổi thứ tự.
7. Nếu cần migration sửa chữa, tạo changeset mới có dependency rõ.

## 23. Rollback khi thay đổi đến từ nhiều nhánh

Một rollback có thể tác động tới thay đổi của nhánh khác nếu hai changeset cùng thay đổi một đối tượng.

Ví dụ:

- A thêm cột orders.status.
- B tạo index trên orders.status.
- C sửa view dùng orders.status.

Nếu rollback A trước, B/C có thể còn phụ thuộc cột status và rollback sẽ lỗi hoặc làm schema không hợp lệ.

Thứ tự rollback cần đảo dependency:

~~~text
Rollback C: khôi phục/xóa view phụ thuộc
Rollback B: xóa index
Rollback A: xóa cột
~~~

Đây là thứ tự logic. SQL cụ thể phụ thuộc DBMS và định nghĩa object.

**Không rollback một changeset độc lập chỉ vì nhánh Git của nó bị đóng.** Khi changeset đã phát hành và có changeset khác phụ thuộc, cần kế hoạch rollback toàn chuỗi hoặc forward fix.

## 24. Forward fix thường phù hợp hơn viết lại lịch sử

Sau khi changeset đã triển khai, đôi khi phát hiện thiết kế ban đầu chưa hoàn hảo. Có thể muốn sửa trực tiếp file cũ, nhưng điều đó làm mất tính nhất quán giữa database đã chạy và database mới.

Một forward fix thêm changeset mới để đưa schema từ trạng thái hiện tại sang trạng thái mong muốn.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "ORD-352-correct-order-status-default"
      author: "orders-team"
      changes:
        - addDefaultValue:
            tableName: orders
            columnName: status
            defaultValue: NEW
~~~

Ví dụ chỉ minh họa ý tưởng; cần xác minh kiểu dữ liệu, giá trị default và tác động với DBMS thực tế.

Forward fix có lợi:

- Lịch sử thể hiện rõ sai sót và cách sửa.
- Database đã triển khai và database mới có cùng chuỗi thay đổi.
- Không cần ép checksum của changeset cũ khớp lại.
- Dễ review và điều tra hơn.

Tuy nhiên, forward fix cũng phải có precondition, rollback/forward plan và kiểm thử dữ liệu phù hợp.

## 25. Xử lý migration phụ thuộc theo mô hình expand–migrate–contract

Khi nhiều nhánh thay đổi cùng một hợp đồng dữ liệu, có thể chia theo giai đoạn tương thích:

**Expand:** thêm cột hoặc cấu trúc mới mà ứng dụng cũ vẫn hoạt động.

**Migrate:** cập nhật dữ liệu và triển khai ứng dụng tương thích cả cấu trúc cũ/mới.

**Switch:** chuyển đọc/ghi sang cấu trúc mới.

**Contract:** bỏ cột hoặc constraint cũ sau khi không còn phụ thuộc.

Ví dụ:

~~~text
Branch A:
  add orders.status_new (nullable)

Branch B:
  deploy application dual-write / compatible read

Integration:
  backfill status_new
  verify consistency

Release:
  switch reads to status_new
  enforce constraint

Later release:
  drop legacy_status
~~~

Đây là mô hình phối hợp release, không phải mọi bước nên nằm trong một changeset. Cần xác định rõ owner và thứ tự tích hợp giữa nhánh database với nhánh ứng dụng.

## 26. Ownership và code review cho changelog

Một nhóm có thể dùng CODEOWNERS hoặc quy tắc review để chỉ định người chịu trách nhiệm với:

- Root/master changelog.
- Schema của từng domain.
- Migration phá hủy dữ liệu.
- Stored procedure/function.
- Quyền và security grants.
- Baseline và logicalFilePath.
- Các thay đổi ảnh hưởng nhiều service.

Người review cần hiểu không chỉ YAML syntax mà cả SQL được sinh và database behavior.

### 26.1. Checklist review pull request

- ID có duy nhất và có ý nghĩa không?
- Author có theo quy ước không?
- Filename/logicalFilePath có ổn định không?
- Changelog gốc đã include file đúng chưa?
- Dependency có được khai báo/sắp thứ tự không?
- Precondition có phản ánh đúng trạng thái mong đợi không?
- Có dùng MARK_RAN để che lỗi không?
- Rollback có khôi phục được dữ liệu/đối tượng không?
- Changeset cũ đã triển khai có bị sửa không?
- Có SQL phụ thuộc DBMS hoặc executor không?
- Test trên database sạch và database baseline đã đạt chưa?
- Có migration nào khác cùng tác động object không?

## 27. Tự động phát hiện xung đột trước khi merge

CI có thể kiểm tra một số lỗi có tính cơ học:

- Hai changeset trùng ID/author/path.
- ID trùng theo quy ước nội bộ.
- File changelog không được include.
- Include path không tồn tại.
- Conflict marker còn sót.
- Changelog không validate.
- Changeset mới sửa file đã triển khai theo policy repository.
- SQL hoặc migration test thất bại trên database sạch.
- Changeset phụ thuộc object không tồn tại tại thời điểm chạy.

Một số kiểm tra như dependency giữa view và column cần hiểu SQL hoặc catalog, khó giải quyết chỉ bằng regex. CI nên kết hợp kiểm tra tĩnh với **integration test thực thi Liquibase** trên database thực tế.

### 27.1. Không viết một script tự chế để suy ra toàn bộ identity nếu không cần

Nếu cần kiểm tra uniqueness, có thể dùng công cụ parser hoặc cơ chế kiểm tra của Liquibase theo phiên bản. Regex đơn giản trên YAML có thể bỏ sót anchor, include lồng nhau, formatted SQL hoặc logicalFilePath.

Mục tiêu là phát hiện sớm, không tạo thêm một parser không đầy đủ rồi tin kết quả như nguồn chân lý.

## 28. Mẫu quy trình cho nhóm phát triển

Một quy trình thực tế có thể chuẩn hóa:

| Giai đoạn | Người chịu trách nhiệm | Bằng chứng |
|---|---|---|
| Thiết kế thay đổi | Feature owner + DBA/domain owner | Dependency, schema contract |
| Tạo changeset | Developer | File riêng, ID/author, rollback |
| Kiểm tra cục bộ | Developer | Validate, update-sql, DB test |
| Review PR | Code owner | Identity, SQL, dependency, data risk |
| Tích hợp | Maintainer/release owner | Master include và thứ tự |
| CI tích hợp | Pipeline | Database sạch + baseline test |
| Phát hành | Release owner | Artifact, history, deployment ID |
| Sau triển khai | On-call/database owner | Schema verification, drift, logs |

Không nhất thiết một cá nhân làm tất cả; điều quan trọng là mỗi bước có owner và kết quả có thể kiểm tra.

## 29. Tình huống thực hành: hai nhánh cùng sửa bảng orders

**Bối cảnh:** hai developer làm việc độc lập.

Nhánh A tạo cột:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "ORD-410-add-status"
      author: "orders-team"
      changes:
        - addColumn:
            tableName: orders
            columns:
              - column:
                  name: status
                  type: varchar(24)
~~~

Nhánh B tạo index:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "RPT-208-index-status"
      author: "reporting-team"
      changes:
        - createIndex:
            tableName: orders
            indexName: idx_orders_status
            columns:
              - column:
                  name: status
~~~

### 29.1. Yêu cầu

1. Tạo hai file changeset riêng.
2. Ghi dependency rằng index cần cột status.
3. Tích hợp cả hai file vào master theo đúng thứ tự.
4. Chạy validate và status.
5. Chạy update-sql.
6. Test trên database sạch.
7. Test trên database đã có baseline.
8. Kiểm tra index thật trong catalog.
9. Review rollback theo thứ tự index rồi cột.
10. Lưu kết quả CI.

### 29.2. Câu hỏi

- Nếu master include B trước A, chuyện gì xảy ra?
- Nếu developer B đã test trên shared DB có cột status từ nhánh A nhưng database sạch không có cột, vì sao test local có thể gây hiểu lầm?
- Nếu A đã triển khai staging rồi thay đổi kiểu cột trong file cũ, cần xử lý thế nào?
- Nếu B đã triển khai production, có thể rollback A riêng không?
- DATABASECHANGELOGLOCK có ngăn hai developer tạo changeset trùng ý nghĩa trong Git không?

### 29.3. Đáp án định hướng

- B có thể thất bại vì cột chưa tồn tại.
- Shared database có drift từ nhánh khác nên không đại diện trạng thái nhánh độc lập.
- Changeset đã triển khai nên được giữ nguyên; tạo changeset mới để sửa kiểu.
- Cần xét dependency B → A; rollback A trước có thể làm B lỗi.
- Liquibase lock chỉ điều phối tiến trình Liquibase trên database, không phát hiện conflict Git hoặc thiết kế trùng lặp.

## 30. Tình huống thực hành: conflict master changelog

Hai nhánh cùng thêm include vào master. Git báo conflict.

**Yêu cầu giải quyết:**

1. Đọc hai file changeset mới và xác định đối tượng tác động.
2. Xác định dependency.
3. Hợp nhất cả hai include nếu đều cần.
4. Đặt thứ tự đúng.
5. Xóa marker conflict và kiểm tra YAML.
6. Chạy validate.
7. Xem status và update-sql.
8. Chạy migration trên database sạch.
9. Chạy migration trên database có baseline.
10. Kiểm tra DATABASECHANGELOG và catalog.

Không chọn một phía chỉ để Git báo merge thành công. Kết quả cần đúng cả cấu trúc mã nguồn lẫn schema.

## 31. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Git merge thành công nhưng update thất bại | Conflict ngữ nghĩa/dependency | Test trên database sạch và kiểm tra thứ tự |
| Duplicate changeset | ID/author/path bị trùng hoặc include lặp | Kiểm tra identity và changelog graph |
| Duplicate column/index | Hai nhánh tạo cùng object | Hợp nhất ý định, bỏ migration thừa trước triển khai |
| Checksum mismatch | Sửa changeset đã triển khai | Giữ nội dung cũ, tạo changeset mới |
| Changeset chạy hai lần | Path/identity thay đổi hoặc history không đúng schema | Kiểm tra FILENAME/logicalFilePath và metadata |
| File changeset không được chạy | Thiếu include hoặc filter không khớp | Kiểm tra master và context/labels/dbms |
| Index chạy trước column | Include order sai | Sắp xếp dependency trong changelog |
| View tham chiếu cột chưa có | Migration view merge sai thứ tự | Đặt changeset nền trước view |
| Rollback một nhánh làm hỏng nhánh khác | Hai migration phụ thuộc cùng object | Rollback theo thứ tự ngược dependency hoặc forward fix |
| Dev test pass nhưng CI fail | Shared database đã có schema từ nhánh khác | Database riêng cho mỗi branch/job |
| CI chờ DATABASECHANGELOGLOCK | Pipeline khác đang update | Kiểm tra tiến trình; không giải phóng lock mù |
| includeAll nạp file ngoài ý muốn | Thư mục chứa file thử nghiệm hoặc thứ tự không rõ | Tách thư mục và xác minh quy tắc includeAll |
| Diff giữa môi trường nhiễu | Filter/schema scope khác nhau | Cố định scope và DBMS/version |
| Context/label làm thiếu changeset | Filter runtime không nhất quán | Ghi rõ filter và test mỗi môi trường |
| Sửa file cũ để đổi thứ tự | Changelog đã triển khai bị biến đổi | Thêm changeset mới, giữ lịch sử |
| Merge bỏ mất một include | Chọn nhầm một phía conflict | So sánh danh sách file và test master |
| Rebase làm đổi path | Tái cấu trúc thư mục không giữ logical path | Kiểm tra identity và lịch sử |
| Migration data bị chạy lặp | SQL không idempotent/runAlways | Thiết kế điều kiện, marker và rollback dữ liệu |

## 32. Checklist trước khi merge changelog từ nhiều nhánh

- [ ] Mỗi nhánh dùng file changeset riêng theo quy ước.
- [ ] ID có tính duy nhất và dễ truy vết.
- [ ] Author nhất quán.
- [ ] Filename/logicalFilePath được giữ ổn định.
- [ ] Không có changeset identity trùng hoặc include lặp.
- [ ] Không có hai migration cùng tạo/sửa một object ngoài ý muốn.
- [ ] Dependency giữa cột, index, constraint, view và dữ liệu đã rõ.
- [ ] Thứ tự include phù hợp dependency.
- [ ] Không còn Git conflict markers.
- [ ] YAML/XML/JSON/formatted SQL hợp lệ.
- [ ] Changelog cũ đã triển khai không bị sửa tùy tiện.
- [ ] Checksum mismatch đã được điều tra.
- [ ] Precondition không dùng MARK_RAN để che dependency thiếu.
- [ ] Rollback theo thứ tự ngược phụ thuộc và có kiểm tra dữ liệu.
- [ ] Context/labels/dbms được dùng có chủ đích.
- [ ] IncludeAll không nạp file ngoài phạm vi.
- [ ] CI chạy trên database cách ly, không phụ thuộc shared dev DB.
- [ ] Đã test trên database trống và database có baseline.
- [ ] Đã review update-sql và rollback-sql.
- [ ] Đã kiểm tra DBMS/version và JDBC/native executor.
- [ ] DATABASECHANGELOGLOCK không bị can thiệp khi còn tiến trình chạy.
- [ ] Master changelog sau merge có thể dựng lại schema theo thứ tự xác định.
- [ ] Artifact, log CI và deployment metadata được lưu.
- [ ] Có owner phê duyệt thay đổi phá hủy và kế hoạch phục hồi.

**Kết luận:** Cộng tác trên nhiều nhánh với Liquibase đòi hỏi quản lý đồng thời **identity changeset, cấu trúc include, thứ tự dependency, checksum và trạng thái database ở từng môi trường**. Tạo file migration riêng cho mỗi nhánh giúp giảm conflict văn bản, nhưng không loại bỏ xung đột ngữ nghĩa khi nhiều nhánh cùng tác động một đối tượng. Hãy giữ changeset đã triển khai bất biến, dùng changeset mới cho thay đổi tiếp theo, test trên database cách ly và kiểm tra changelog tích hợp từ đầu đến cuối. Khi Git merge, Liquibase validate, update-sql và integration test cùng xác nhận, nhóm mới có cơ sở tin rằng lịch sử migration sau hợp nhất sẽ nhất quán và có thể triển khai lặp lại.

