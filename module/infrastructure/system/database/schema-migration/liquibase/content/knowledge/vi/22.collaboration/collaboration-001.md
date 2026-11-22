# Quy ước đặt tên changeset và tệp trong nhóm Liquibase

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, chúng ta học cách quản lý thay đổi schema và dữ liệu bằng **changelog, changeset, precondition, checksum và lịch sử triển khai**; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Khi nhiều lập trình viên, DBA và nhóm dịch vụ cùng đóng góp migration, quy ước đặt tên trở thành một phần của tính an toàn: nó giúp nhận diện thay đổi, tránh trùng lặp, đọc lịch sử dễ dàng, review đúng phạm vi và giữ nguyên định danh sau khi đã triển khai.

Bài học thuộc chương **Cộng tác**, tập trung vào cách đặt tên cho **changeset, file changelog, thư mục, file SQL và master changelog** trong một nhóm. Quy ước tốt phải đủ rõ để nhiều người cùng làm việc, nhưng cũng phải tôn trọng cách Liquibase nhận diện changeset và lưu checksum. Các ví dụ dùng YAML và formatted SQL; dự án cần thống nhất một chuẩn phù hợp với phiên bản Liquibase và DBMS đang vận hành.

## 1. Vì sao tên changeset và tên file quan trọng?

Tên không chỉ để đọc. Liquibase dùng một bộ thông tin để nhận diện changeset trong lịch sử, thông thường gồm:

```text
id + author + đường dẫn file changelog
```

Trong đó:

- `id` do nhóm đặt để phân biệt một thay đổi với những thay đổi khác.
- `author` xác định tác giả/nhóm chịu trách nhiệm theo metadata changelog.
- Đường dẫn file changelog (hoặc đường dẫn logic được cấu hình) là một phần của định danh.
- `MD5SUM` được lưu trong `DATABASECHANGELOG` để kiểm tra nội dung changeset theo cơ chế checksum của Liquibase.

Vì vậy, hai changeset có cùng `id` và `author` nhưng nằm ở hai đường dẫn changelog khác nhau có thể được Liquibase xem là hai định danh khác nhau. Điều đó không có nghĩa nhóm nên cố tình tái sử dụng ID: một quy ước **ID duy nhất trong toàn dự án** giúp tránh nhầm lẫn cho người review, người vận hành và công cụ quản lý release.

Tên rõ ràng giúp trả lời nhanh:

1. Thay đổi thuộc miền nghiệp vụ hoặc dịch vụ nào?
2. Nó tạo, thêm, sửa hay xóa đối tượng nào?
3. Đây là thay đổi mới hay một migration cũ đã được triển khai?
4. Ai/nhóm nào chịu trách nhiệm giải thích và hỗ trợ khi có sự cố?
5. File nào cần được mở để review SQL, precondition và rollback?

Tên không thay thế nội dung kỹ thuật. Một changeset tên `add-customer-index` vẫn có thể chứa lệnh xóa bảng; reviewer phải kiểm tra change type, SQL và phạm vi dữ liệu thực tế.

## 2. Phân biệt tên file, ID, author và tên đối tượng database

Những thành phần này có liên quan nhưng không thể dùng thay cho nhau:

| Thành phần | Ví dụ | Mục đích |
|---|---|---|
| Tên file changelog | `20261119-001-add-customer-status.yaml` | Tổ chức file, giúp tìm và review |
| Changeset `id` | `DB-4821-add-customer-status` | Định danh thay đổi trong changelog |
| Changeset `author` | `customer-platform` | Ghi nhận nhóm/tác giả chịu trách nhiệm |
| Tên bảng | `customer` | Đối tượng database được thay đổi |
| Tên cột | `status` | Thuộc tính của bảng |
| Tên constraint | `ck_customer_status` | Nhận diện ràng buộc trong DBMS |
| Tên index | `idx_customer_status` | Nhận diện cấu trúc index |
| Tên tag release | `release-2026.11` | Đánh dấu mốc trong lịch sử triển khai |

Ví dụ một file có thể chứa changeset:

```yaml
databaseChangeLog:
  - changeSet:
      id: "DB-4821-add-customer-status"
      author: "customer-platform"
      comment: "Thêm trạng thái cho hồ sơ khách hàng"
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: status
                  type: VARCHAR(20)
```

Tên file có thể là `DB-4821-add-customer-status.yaml`. Tên file và `id` có thể giống phần mô tả để tiện tra cứu, nhưng Liquibase không yêu cầu chúng phải giống nhau. Nhóm nên chọn một quy ước nhất quán thay vì suy ra ID tự động từ tên file.

## 3. Thiết kế quy ước ID cho changeset

Một ID tốt có bốn đặc điểm:

- **Ổn định:** sau khi triển khai không đổi chỉ vì sửa chính tả, đổi người phụ trách hoặc tái cấu trúc thư mục.
- **Duy nhất:** không trùng trong phạm vi mà nhóm quy định; tốt nhất duy nhất toàn module hoặc toàn repository.
- **Có ý nghĩa:** người đọc có thể nhận ra mục đích mà không phải mở toàn bộ nội dung.
- **Dễ tạo song song:** hai nhánh Git hoặc hai nhóm không vô tình sinh cùng ID.

### 3.1. Một mẫu ID phù hợp cho nhóm nhiều người

Mẫu đề xuất:

```text
<ticket-or-date>-<sequence>-<action>-<object>
```

Ví dụ:

| ID | Ý nghĩa |
|---|---|
| `DB-4821-add-customer-status` | Thay đổi gắn với ticket DB-4821 |
| `DB-4822-create-payment-attempt` | Tạo bảng/lịch sử lần thử thanh toán |
| `20261119-001-add-order-source` | Thay đổi đầu tiên của ngày theo thứ tự nhóm |
| `20261119-002-create-order-source-index` | Thay đổi tiếp theo cùng ngày |
| `CRM-731-backfill-customer-tier` | Chuyển đổi dữ liệu theo ticket CRM-731 |

Trong nhóm có nhiều nhánh song song, ID theo ticket thường tránh va chạm tốt hơn một bộ đếm cục bộ như `001`, `002`. Nếu dùng ngày và số thứ tự, phải có một cơ chế cấp số chung trong phạm vi dự án hoặc chấp nhận tiền tố nhóm/ticket để không trùng.

### 3.2. Dùng chuỗi tường minh trong YAML

Nên đặt dấu nháy cho ID, author và các scalar có hình dạng số/ngày:

```yaml
id: "20261119-001-add-order-source"
author: "order-platform"
```

Việc quote giúp người đọc và parser hiểu đây là chuỗi định danh. Tránh dùng ID chỉ là số hoặc ngày không quote, vì YAML parser có thể diễn giải scalar theo kiểu khác với ý định.

### 3.3. Quy tắc động từ và tên đối tượng

Dùng động từ nhất quán, mô tả hành động thực:

| Động từ | Khi dùng | Ví dụ |
|---|---|---|
| `create` | Tạo bảng hoặc đối tượng mới | `create-invoice` |
| `add` | Thêm cột, constraint hoặc thành phần | `add-customer-status` |
| `alter` / `modify` | Thay đổi định nghĩa hiện có | `alter-payment-amount-type` |
| `rename` | Đổi tên đối tượng | `rename-customer-code` |
| `drop` / `remove` | Gỡ đối tượng | `drop-legacy-flag` |
| `create-index` | Tạo index | `create-order-created-at-index` |
| `backfill` | Điền/chuyển đổi dữ liệu đã có | `backfill-customer-tier` |
| `seed` / `load` | Nạp dữ liệu tham chiếu | `seed-country-codes` |
| `add-constraint` | Bổ sung ràng buộc | `add-order-number-unique` |

Không dùng tên mơ hồ như `update-database`, `fix-bug`, `new-change` hoặc `final-version`. Một ID có thể tồn tại nhiều năm; từ “new” hay “latest” nhanh chóng mất ý nghĩa.

## 4. Quy ước author: ghi nhận nhóm chịu trách nhiệm

`author` là một thành phần định danh changeset. Nhóm có thể dùng tên cá nhân, nhưng trong dự án có nhiều thành viên và thay đổi dài hạn, một mã nhóm ổn định thường dễ bảo trì hơn:

- `customer-platform`
- `billing-team`
- `database-platform`
- `inventory-service`

Không dùng email cá nhân có thể bị thu hồi, tên hiển thị thay đổi hoặc username chỉ tồn tại trong một công ty nếu dự án cần bảo toàn lịch sử lâu dài. Nếu tổ chức yêu cầu truy vết người thực hiện, dùng Git author, pull request, audit log hoặc hệ thống release để lưu thông tin đó; không thay `author` trong changelog cũ khi người chịu trách nhiệm thay đổi.

### 4.1. Author không phải tài khoản kết nối database

Ba khái niệm cần tách biệt:

| Khái niệm | Ví dụ | Vai trò |
|---|---|---|
| Changeset author | `customer-platform` | Metadata định danh changeset |
| Git author/committer | Thành viên tạo commit | Truy vết thay đổi trong source control |
| Database user | `liquibase_runner` | Tài khoản thực thi DDL/DML |

Không đặt mật khẩu hoặc thông tin bí mật vào `author`. Author cũng không quyết định quyền được chạy migration; quyền đó đến từ tài khoản database và quy trình phê duyệt.

## 5. Quy ước đặt tên file changelog

Tên file nên:

- Viết thường, dùng chữ Latin không dấu, số và dấu gạch ngang.
- Mô tả hành động cùng đối tượng chính.
- Tránh khoảng trắng, ký tự hệ điều hành đặc thù và tên quá chung.
- Có tiền tố ổn định nếu cần thứ tự khi dùng cơ chế nạp nhiều file.
- Không chứa thông tin môi trường như `prod-only` nếu đó chỉ là cấu hình thực thi; thể hiện điều kiện bằng context/label/DBMS khi phù hợp.
- Không chứa số phiên bản `latest`, `final`, `new` dễ lỗi thời.

Ví dụ:

| Tên file | Đánh giá |
|---|---|
| `20261119-001-create-customer.yaml` | Rõ ngày, thứ tự và mục đích |
| `DB-4821-add-customer-status.yaml` | Tốt khi dùng ticket làm khóa chống trùng |
| `billing-create-invoice-index.yaml` | Có miền nghiệp vụ và hành động |
| `update.yaml` | Quá chung |
| `new-final-v2.yaml` | Không thể hiện thay đổi cụ thể |
| `Customer Status Final.yaml` | Có khoảng trắng, hoa/thường và từ mơ hồ |

Tên file là một phần của định danh changeset thông thường. Vì vậy **không đổi tên hoặc di chuyển file đã triển khai chỉ để làm đẹp cấu trúc** nếu chưa có kế hoạch duy trì đường dẫn logic.

## 6. Tổ chức thư mục theo miền nghiệp vụ

Một cấu trúc có thể áp dụng cho dự án nhiều nhóm:

```text
src/main/resources/db/changelog/
├── db.changelog-master.yaml
├── teams/
│   ├── customer/
│   │   └── changelog.yaml
│   ├── billing/
│   │   └── changelog.yaml
│   └── inventory/
│       └── changelog.yaml
├── changes/
│   ├── customer/
│   │   ├── DB-4821-add-customer-status.yaml
│   │   └── DB-4890-create-customer-search-index.yaml
│   ├── billing/
│   │   └── BILL-731-create-invoice.yaml
│   └── inventory/
│       └── INV-228-add-stock-reserved.yaml
└── sql/
    └── billing/
        └── BILL-812-backfill-invoice-reference.sql
```

Ý nghĩa:

- `db.changelog-master.yaml` là entry point được CLI/Spring Boot cấu hình.
- `teams/` chứa changelog điều phối theo nhóm/miền nghiệp vụ.
- `changes/` chứa các file migration có định danh rõ ràng.
- `sql/` chứa SQL được tham chiếu từ changeset khi cần formatted SQL hoặc `sqlFile`.

Không bắt buộc phải có đủ mọi thư mục. Dự án nhỏ có thể chỉ cần master và một thư mục changes. Dự án lớn nên chọn cấu trúc giúp phân quyền review và tìm chủ sở hữu, tránh tạo quá nhiều tầng thư mục khiến đường dẫn khó đọc.

### 6.1. Master changelog và thứ tự include

Ví dụ master:

```yaml
databaseChangeLog:
  - include:
      file: teams/customer/changelog.yaml
      relativeToChangelogFile: true
  - include:
      file: teams/billing/changelog.yaml
      relativeToChangelogFile: true
  - include:
      file: teams/inventory/changelog.yaml
      relativeToChangelogFile: true
```

Changelog của nhóm customer:

```yaml
databaseChangeLog:
  - include:
      file: ../../changes/customer/DB-4821-add-customer-status.yaml
      relativeToChangelogFile: true
  - include:
      file: ../../changes/customer/DB-4890-create-customer-search-index.yaml
      relativeToChangelogFile: true
```

`relativeToChangelogFile: true` giúp đường dẫn được tính từ file changelog chứa include. Khi chuyển file, phải kiểm tra lại đường dẫn tương đối; một đường dẫn chạy trên Windows có thể vẫn sai khi chạy trên Linux do phân biệt hoa/thường.

Ưu tiên `include` tường minh khi thứ tự migration có phụ thuộc hoặc khi muốn review chính xác danh sách file sẽ chạy. Nếu dùng `includeAll`, thống nhất quy tắc tiền tố/tên file, hiểu cách phiên bản Liquibase đang dùng sắp xếp tài nguyên và xác minh bằng `status`/`update-sql`. Không dựa vào thứ tự tạo file trên máy hoặc thứ tự liệt kê thư mục của hệ điều hành.

## 7. Một file cho một changeset hay nhiều changeset trong một file?

Liquibase cho phép nhiều changeset trong cùng một file changelog. Quyết định tổ chức nên dựa trên cách nhóm review và phát hành:

| Cách tổ chức | Ưu điểm | Hạn chế |
|---|---|---|
| Một file cho mỗi changeset | Dễ review, đổi nhánh ít xung đột, dễ tra cứu theo ID | Tăng số lượng file |
| Một file cho một nhóm migration liên quan | Ít file hơn, dễ đọc một chủ đề liền mạch | Nhiều người sửa chung file dễ conflict |
| Một file rất lớn cho toàn module | Cấu hình include đơn giản | Khó review, khó phân quyền, merge conflict thường xuyên |

Với nhóm nhiều người, **một file cho một changeset hoặc một thay đổi nghiệp vụ nhỏ** thường thuận tiện. Có thể gộp vài change type vào một changeset khi chúng tạo thành một thay đổi logic cần được áp dụng/rollback cùng nhau, ví dụ thêm cột và constraint phù hợp. Tránh gộp các thay đổi không liên quan chỉ để giảm số file.

Ví dụ một changeset có thể thêm cột rồi tạo constraint:

```yaml
databaseChangeLog:
  - changeSet:
      id: "DB-4902-add-order-external-code"
      author: "order-platform"
      changes:
        - addColumn:
            tableName: orders
            columns:
              - column:
                  name: external_code
                  type: VARCHAR(64)
        - addUniqueConstraint:
            tableName: orders
            columnNames: external_code
            constraintName: uq_orders_external_code
      rollback:
        - dropUniqueConstraint:
            tableName: orders
            constraintName: uq_orders_external_code
        - dropColumn:
            tableName: orders
            columnName: external_code
```

Đây là ví dụ đơn giản trên bảng đã có trạng thái phù hợp; nếu bảng có dữ liệu, việc thêm unique có thể thất bại do giá trị trùng hoặc null semantics. Chia thành nhiều changeset có thể cần thiết để backfill và kiểm tra dữ liệu trước khi thêm constraint.

## 8. Quy ước tên cho SQL formatted changelog và SQL file

Một nhóm có thể dùng YAML/XML/JSON changelog hoặc formatted SQL. Không nên trộn các phong cách tùy tiện trong cùng một miền mà không có quy ước rõ ràng.

### 8.1. Formatted SQL

Ví dụ file `DB-4821-add-customer-status.sql`:

```sql
--liquibase formatted sql

--changeset customer-platform:DB-4821-add-customer-status
ALTER TABLE customer
    ADD COLUMN status VARCHAR(20);

--rollback ALTER TABLE customer DROP COLUMN status;
```

Trong formatted SQL, dòng `--changeset` chứa author và ID theo cú pháp `author:id`. Hãy giữ đúng cùng quy ước ID/author như YAML để người review nhận diện thay đổi thống nhất. Cần xác nhận parser formatted SQL và các thuộc tính bổ sung với phiên bản Liquibase đang sử dụng.

### 8.2. Changelog tham chiếu SQL file

Khi SQL dài hoặc đặc thù DBMS, YAML có thể tham chiếu file riêng:

```yaml
databaseChangeLog:
  - changeSet:
      id: "BILL-812-backfill-invoice-reference"
      author: "billing-team"
      changes:
        - sqlFile:
            path: ../../sql/billing/BILL-812-backfill-invoice-reference.sql
            relativeToChangelogFile: true
            splitStatements: false
      rollback:
        - sqlFile:
            path: ../../sql/billing/BILL-812-rollback-invoice-reference.sql
            relativeToChangelogFile: true
            splitStatements: false
```

Ví dụ chỉ minh họa cách tách SQL ra file; `splitStatements` và delimiter cần phù hợp với script, DBMS và cách driver thực thi. Nếu script chứa procedure/function hoặc cú pháp nhiều câu lệnh, phải thử preview và chạy trên database đúng loại.

Tên file SQL nên dùng cùng ticket/ID của changeset để dễ truy ngược. Đừng đặt chung tên như `script.sql`, `data.sql` hoặc `rollback.sql` trong nhiều thư mục mà không có quy ước. File SQL được tham chiếu cũng là tài nguyên của release: phải review, đóng gói và giữ ổn định sau khi changeset đã chạy.

## 9. Đặt tên constraint, index và đối tượng database

Tên đối tượng DB nên nhất quán với quy ước của dự án, giới hạn identifier của DBMS và mục đích nghiệp vụ.

| Loại | Mẫu gợi ý | Ví dụ |
|---|---|---|
| Primary key | `pk_<table>` | `pk_customer` |
| Foreign key | `fk_<child>_<parent>` | `fk_order_customer` |
| Unique constraint | `uq_<table>_<columns>` | `uq_customer_tenant_email` |
| Check constraint | `ck_<table>_<rule>` | `ck_invoice_amount_nonnegative` |
| Index thường | `idx_<table>_<columns>` | `idx_order_created_at` |
| Unique index | `ux_<table>_<columns>` | `ux_member_normalized_email` |
| Sequence | `seq_<table>_<column>` | `seq_invoice_id` |
| View | `vw_<purpose>` hoặc quy ước thống nhất khác | `vw_monthly_revenue` |

Các tiền tố trên là quy ước nhóm, không phải yêu cầu của Liquibase. Nếu DBMS có giới hạn độ dài tên, chọn cách rút gọn có thể đoán được và tránh cắt mất phần phân biệt. Với unique index theo biểu thức/partial index, tên nên nêu được mục đích, ví dụ `ux_member_active_email`, và điều kiện cần được ghi trong changelog.

Không dùng cùng một tên constraint cho các bảng khác nhau nếu DBMS hoặc công cụ quản trị yêu cầu phạm vi tên rộng hơn dự kiến. Kiểm tra metadata thực tế trước khi chọn tên, nhất là khi baseline database đã có những tên do DBA tạo thủ công.

## 10. Tên changeset phải phản ánh thay đổi, không phản ánh trạng thái nhánh

Một số tên có vẻ tiện lúc phát triển nhưng trở nên vô nghĩa sau vài tháng:

| Không nên | Nên dùng |
|---|---|
| `new-change` | `DB-4821-add-customer-status` |
| `fix-final` | `BILL-812-correct-invoice-reference` |
| `v2-update` | `DB-4902-add-order-external-code` |
| `prod-hotfix` | `OPS-231-add-payment-timeout-index` |
| `test-script` | `QA-129-seed-order-fixtures` |
| `latest-schema` | `DB-5100-create-audit-entry` |

Tên `prod-hotfix` còn gợi ý rằng changeset chỉ chạy ở production. Nếu migration chỉ dành cho một môi trường hoặc một mục đích, thể hiện điều kiện bằng context/label/DBMS phù hợp và hiểu rõ semantics filter. Không dựa vào tên file để Liquibase tự giới hạn môi trường.

Không đưa thông tin bí mật, dữ liệu khách hàng hoặc nội dung nhạy cảm vào ID, filename, comment hay author vì những trường này có thể xuất hiện trong Git, log và bảng lịch sử.

## 11. Quy tắc bất biến: không sửa hoặc đổi tên changeset đã triển khai

Khi changeset đã được áp dụng ở một môi trường, coi nội dung và định danh của nó là **bất biến**. Các thao tác sau có thể gây sai lệch lịch sử:

- Đổi `id` hoặc `author`.
- Di chuyển/đổi tên file làm thay đổi đường dẫn định danh.
- Sửa change type, SQL, precondition hoặc rollback của changeset cũ.
- Thay nội dung file `sqlFile` đã được tham chiếu.
- Sắp xếp lại include làm thay đổi thứ tự thực thi ở môi trường chưa đồng bộ.

Liquibase lưu thông tin changeset trong `DATABASECHANGELOG`, bao gồm `ID`, `AUTHOR`, `FILENAME` và checksum. Nếu thay đổi nội dung, có thể phát sinh lỗi checksum. Nếu thay đổi đường dẫn định danh, công cụ có thể nhận diện thành một changeset khác và cố thực thi lại.

### 11.1. Thay đổi yêu cầu nghiệp vụ thì tạo changeset mới

Ví dụ changeset cũ tạo cột:

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

Sau đó nghiệp vụ yêu cầu đổi độ dài lên 40 ký tự. Không sửa `VARCHAR(20)` trong changeset đã triển khai. Hãy thêm changeset mới:

```yaml
databaseChangeLog:
  - changeSet:
      id: "DB-4977-expand-customer-status-length"
      author: "customer-platform"
      changes:
        - modifyDataType:
            tableName: customer
            columnName: status
            newDataType: VARCHAR(40)
```

ID mới mô tả rõ bước tiến schema và giữ nguyên lịch sử thay đổi ban đầu. Khi dùng `modifyDataType`, cần xem SQL preview và kiểm tra hỗ trợ của DBMS/phiên bản; thay đổi kiểu có thể ảnh hưởng dữ liệu hiện có.

### 11.2. Khi thật sự phải di chuyển file

Đôi khi tái cấu trúc thư mục là cần thiết. Liquibase có cơ chế `logicalFilePath` để giữ định danh logic khi đường dẫn vật lý thay đổi, tùy phiên bản và định dạng changelog. Trước khi dùng:

1. Truy vấn `FILENAME` trong `DATABASECHANGELOG` của các môi trường.
2. Xác định chính xác đường dẫn logic đang được lưu.
3. Kiểm tra cú pháp/vị trí `logicalFilePath` được hỗ trợ trong phiên bản đang dùng.
4. Thử trên bản sao database đã có lịch sử, không chỉ trên database mới.
5. Chạy `validate`, `status` và kiểm tra rằng changeset cũ không xuất hiện lại như pending.
6. Review tất cả include tương đối và tài nguyên SQL/CSV đi kèm.

Không coi `logicalFilePath` là lý do để đổi tên file thường xuyên. Cách an toàn nhất vẫn là giữ đường dẫn changelog đã triển khai ổn định.

## 12. Cộng tác qua Git branch và pull request

Nhiều nhóm thường phát triển song song. Xung đột có thể xảy ra ở ID, tên file, master changelog hoặc thứ tự migration.

### 12.1. Tránh trùng ID khi phát triển song song

Giả sử hai nhánh cùng tạo changeset:

```text
feature/customer-status
  DB-4821-add-customer-status.yaml

feature/billing-status
  DB-4821-add-billing-status.yaml
```

Nếu hai nhóm dùng chung ticket hoặc quy ước ID không đủ phân biệt, có thể xảy ra trùng. Đặt ID theo ticket thực sự của mỗi thay đổi, hoặc dùng prefix miền nghiệp vụ/nhóm:

```text
CUSTOMER-4821-add-customer-status
BILLING-731-add-invoice-status
```

Nếu hệ thống quản lý ticket không cấp ID duy nhất toàn repository, cần có prefix để tránh collision. Không giải quyết bằng cách đổi ID của changeset đã triển khai; hãy xử lý khi hai nhánh còn ở giai đoạn review.

### 12.2. Giảm xung đột master changelog

Nếu mọi nhóm cùng thêm dòng vào một master file, merge conflict sẽ thường xuyên xảy ra. Có thể dùng một changelog điều phối theo team/domain như mục 6:

- Mỗi nhóm sở hữu file changelog con của mình.
- Người/nhóm duy trì master chịu trách nhiệm tích hợp các file con.
- Pull request mới thêm include theo thứ tự đã review.
- Không để hai nhóm cùng sửa một file migration đang được review.

Một cách khác là mỗi changeset file được include trực tiếp trong master. Dù chọn cách nào, phải có owner rõ ràng và quy trình xử lý conflict.

### 12.3. Thứ tự merge không luôn bằng thứ tự nghiệp vụ

Hai pull request có thể merge theo thời điểm khác với thứ tự mà thay đổi phụ thuộc. Ví dụ:

1. PR A tạo bảng `customer_segment`.
2. PR B tạo foreign key từ `customer` sang `customer_segment`.
3. Nếu PR B được đưa vào luồng thực thi trước PR A, migration có thể thất bại.

Người review phải nhận diện dependency và bảo đảm thứ tự include/changelog phù hợp. Nếu thay đổi có thể triển khai độc lập, thiết kế để không phụ thuộc thứ tự merge; nếu bắt buộc có thứ tự, thể hiện nó rõ trong master và kế hoạch phát hành.

## 13. Quy ước cho include, includeAll và thứ tự file

### 13.1. Dùng include khi cần kiểm soát rõ

```yaml
databaseChangeLog:
  - include:
      file: changes/2026/DB-4821-add-customer-status.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/2026/DB-4977-expand-customer-status-length.yaml
      relativeToChangelogFile: true
```

Danh sách include thể hiện thứ tự rõ trong code review. Cách này phù hợp khi thay đổi có phụ thuộc hoặc cần kiểm soát chính xác release.

### 13.2. Dùng includeAll có quy ước chặt

```yaml
databaseChangeLog:
  - includeAll:
      path: changes/customer
      relativeToChangelogFile: true
```

Nếu dùng `includeAll`, file cần tên có thể sắp xếp và nhận diện rõ, ví dụ:

```text
20261119-001-create-customer.yaml
20261119-002-add-customer-status.yaml
20261120-001-create-customer-index.yaml
```

Tuy nhiên, cách sắp xếp tài nguyên, filter và behavior của `includeAll` cần được xác minh theo phiên bản Liquibase/ResourceAccessor. Không dựa vào thời điểm file được tạo, thứ tự Explorer hiển thị hoặc thứ tự file system. Nếu dependency quan trọng, `include` tường minh thường dễ review hơn.

### 13.3. Không dùng thư mục để biểu thị môi trường

Thư mục `prod/`, `dev/` hoặc `test/` có thể làm người đọc hiểu nhầm rằng Liquibase tự chọn file theo môi trường. Chỉ đường dẫn include và điều kiện changeset mới quyết định nội dung được nạp/chạy. Nếu có thay đổi thực sự khác DBMS, context hoặc label, hãy cấu hình có chủ đích và test từng luồng.

## 14. Quy ước comment và mô tả changeset

Comment nên giải thích **lý do nghiệp vụ hoặc rủi ro**, không lặp lại nguyên văn tên ID.

Không hữu ích:

```yaml
comment: "Add customer status"
```

Hữu ích hơn:

```yaml
comment: "Lưu trạng thái xử lý hồ sơ để hỗ trợ luồng phê duyệt mới"
```

Với migration dữ liệu hoặc thay đổi có rủi ro, comment có thể ghi:

- Nguồn dữ liệu/phiên bản file tham chiếu.
- Phạm vi bảng hoặc tenant bị tác động.
- Điều kiện cần có trước khi chạy.
- Vì sao cần tách thành nhiều changeset.
- Giới hạn rollback hoặc lý do chọn forward-fix.

Không ghi mật khẩu, token, dữ liệu cá nhân hoặc nội dung bí mật trong comment. Comment có thể xuất hiện trong repository, lịch sử và báo cáo triển khai.

## 15. Tổ chức naming convention thành quy ước nhóm

Một quy ước chỉ có giá trị khi mọi người cùng hiểu và áp dụng. Nên ghi nó trong tài liệu đóng góp hoặc pull request template của repository, gồm:

| Hạng mục | Quy tắc cần thống nhất |
|---|---|
| ID | Prefix ticket/domain + động từ + đối tượng; chuỗi quote trong YAML |
| Author | Tên team/service ổn định, không dùng credential |
| File name | Lowercase kebab-case, không dấu, mô tả mục đích |
| Folder | Theo domain/team hoặc loại tài nguyên |
| Constraint/index | Prefix thống nhất và tên phản ánh bảng/cột/quy tắc |
| SQL file | Gắn cùng ticket/ID changeset, đường dẫn ổn định |
| Master | Một owner, include order được review |
| Immutability | Không sửa/rename changeset đã triển khai; tạo changeset mới |
| Path migration | Kiểm tra `FILENAME` và `logicalFilePath` trước khi di chuyển |
| Review | Kiểm tra uniqueness, dependency, SQL, precondition, rollback và filter |

### 15.1. Checklist pull request migration

- [ ] ID changeset mới, rõ mục đích và không trùng theo quy ước dự án.
- [ ] `author` đúng team/service chịu trách nhiệm.
- [ ] Tên file lowercase, không dấu, không có từ mơ hồ như `new`, `final`, `latest`.
- [ ] File đặt trong đúng domain/folder và không đổi đường dẫn file cũ đã triển khai.
- [ ] `include`/`includeAll` đúng path, thứ tự và case-sensitive trên môi trường Linux.
- [ ] Constraint, index, view, sequence và tên đối tượng tuân thủ convention.
- [ ] Comment mô tả lý do thay đổi, không chứa bí mật.
- [ ] Changeset có granularity hợp lý, không gộp thay đổi không liên quan.
- [ ] Precondition, context/label/DBMS và rollback được review.
- [ ] File SQL/CSV tham chiếu được đóng gói và giữ đường dẫn ổn định.
- [ ] `validate`, `status`, `update-sql` chạy với phiên bản/config mục tiêu.
- [ ] Thay đổi đã triển khai được giữ bất biến; yêu cầu mới dùng changeset mới.
- [ ] Dependency với changeset của nhóm khác đã được xác nhận.

## 16. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Liquibase xem changeset cũ là pending sau khi đổi tên file | Đường dẫn file là một phần định danh | Khôi phục path hoặc đánh giá `logicalFilePath` có kiểm chứng |
| Checksum validation thất bại | Nội dung changeset cũ hoặc SQL file được tham chiếu bị thay đổi | So sánh với bản đã triển khai; tạo changeset mới cho yêu cầu mới |
| Hai nhóm vô tình tạo changeset trùng | ID chỉ là `001`, `002` cục bộ | Dùng ticket/domain prefix và kiểm tra ở pull request |
| Migration chạy sai thứ tự | Master/`includeAll` không thể hiện dependency rõ | Dùng include tường minh hoặc quy ước prefix đã kiểm chứng |
| Local chạy được nhưng Linux CI không tìm thấy file | Sai hoa/thường hoặc path separator/relative path | Chuẩn hóa tên file, kiểm tra resource trên Linux |
| Nhiều người conflict trong master | Một file điều phối là điểm sửa chung | Tách changelog theo domain và giao owner tích hợp master |
| Author thay đổi khi nhân sự nghỉ việc | Dùng email/tên cá nhân làm author | Dùng team/service ổn định; không sửa author cũ đã triển khai |
| Tên changeset ghi `prod-hotfix` nhưng vẫn chạy nơi khác | Tên file không phải bộ lọc môi trường | Dùng context/label/DBMS đúng semantics và xác minh preview |
| SQL file bị thiếu trong JAR | Resource không được đóng gói hoặc path tương đối sai | Kiểm tra artifact và đường dẫn từ changelog |
| Đổi cấu trúc thư mục khiến include hỏng | Path tương đối được tính từ changelog khác | Cập nhật include có review; giữ logical identity của changeset đã chạy |
| Rollback không tìm thấy thay đổi mong muốn | Nhầm tên file/ID với định danh hoặc lịch sử thực thi | Đối chiếu `ID`, `AUTHOR`, `FILENAME`, `DATEEXECUTED` trong `DATABASECHANGELOG` |

## 17. Bài thực hành: chuẩn hóa một nhóm migration

Giả sử nhóm có ba thành viên cùng phát triển các thay đổi cho customer và billing. Hãy thực hiện:

1. Đề xuất convention ID dùng ticket/domain prefix, author dùng tên team ổn định.
2. Tạo cấu trúc `db/changelog/` có master và hai changelog con `customer`, `billing`.
3. Viết hai changeset độc lập: thêm `customer.status` và tạo bảng `invoice`.
4. Đặt tên file theo ID, dùng lowercase kebab-case và đường dẫn tương đối.
5. Đưa hai file vào master bằng include tường minh; review thứ tự nếu có dependency.
6. Viết một changeset formatted SQL hoặc `sqlFile`, đặt tên file trùng ticket để dễ truy vết.
7. Chạy `validate`, `status`, `update-sql` trên database thử nghiệm và kiểm tra các changeset được nhận diện.
8. Giả lập đổi tên file sau khi đã chạy trên database thử nghiệm; quan sát ảnh hưởng đến `FILENAME` và pending changeset. Khôi phục path, không chỉnh lịch sử metadata.
9. Tạo hai nhánh có ID trùng trong bản nháp; đề xuất cách giải quyết trước merge.
10. Thêm một changeset mới để thay đổi schema; giữ nguyên các changeset đã chạy.

### Ví dụ convention hoàn chỉnh để nhóm tham khảo

```text
Changeset ID:
  <TICKET>-<verb>-<object>

Author:
  <stable-team-or-service>

Filename:
  <TICKET>-<verb>-<object>.yaml

Folder:
  db/changelog/changes/<domain>/

Constraint:
  pk_<table>
  fk_<child>_<parent>
  uq_<table>_<columns>
  ck_<table>_<rule>

Index:
  idx_<table>_<columns>
  ux_<table>_<columns>

SQL resource:
  db/changelog/sql/<domain>/<TICKET>-<verb>-<object>.sql

Rule:
  Deployed changesets are immutable.
  New requirements get new changesets.
```

Đây là một convention mẫu, không phải chuẩn bắt buộc của Liquibase. Điều quan trọng là nhóm chọn một cách, ghi lại, áp dụng nhất quán và kiểm tra nó trong code review.

**Kết luận:** đặt tên changeset và tệp tốt giúp nhóm cộng tác mà vẫn giữ được lịch sử migration ổn định. Hãy dùng ID duy nhất có ý nghĩa, author là team/service bền vững, tên file mô tả hành động và đối tượng, thư mục theo miền nghiệp vụ, include order được kiểm soát và tên constraint/index nhất quán. Khi changeset đã triển khai, giữ nguyên định danh và nội dung; mọi yêu cầu mới được thể hiện bằng changeset mới. Kết hợp quy ước đó với `validate`, `status`, `update-sql`, review dependency và quản lý `DATABASECHANGELOG` sẽ giúp quy trình `DATABASE_SCHEMA_MIGRATION_LIQUIBASE` dễ cộng tác, truy vết và vận hành qua nhiều môi trường.
