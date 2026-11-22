# Phân chia quyền sở hữu theo miền nghiệp vụ hoặc thành phần

Trong một hệ thống có nhiều nhóm cùng dùng database, việc để mọi nhóm sửa chung changelog hoặc tự chạy SQL theo cách riêng rất dễ tạo xung đột. Nhóm khách hàng có thể thêm cột, nhóm thanh toán thêm foreign key, nhóm báo cáo tạo view; nếu không xác định ai sở hữu từng phần schema và migration, các thay đổi sẽ chồng lấn, thứ tự triển khai khó đoán và không ai chịu trách nhiệm cuối cùng khi database lệch giữa các môi trường.

**Phân chia quyền sở hữu theo miền nghiệp vụ hoặc thành phần** là cách xác định rõ nhóm nào thiết kế, review, phát hành và vận hành những đối tượng database nào; cách các nhóm phối hợp khi có phụ thuộc hoặc cùng thay đổi một đối tượng; và cách hợp nhất migration vào một lịch sử có thể kiểm toán. Bài học thuộc chương **Cộng tác** của `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`. Module hướng tới quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

## 1. Quyền sở hữu trong database có nghĩa gì?

Quyền sở hữu không chỉ là quyền SQL `OWNER` hoặc quyền tạo bảng. Trong quy trình Liquibase, một miền hoặc thành phần cần có trách nhiệm rõ ràng đối với:

- **Mô hình dữ liệu:** bảng, cột, constraint, index, view, routine, trigger và các object thuộc phạm vi.
- **Changelog:** định nghĩa changeset, ID, author, đường dẫn, precondition, rollback và quan hệ phụ thuộc.
- **Chất lượng migration:** review SQL, kiểm tra dữ liệu, hiệu năng, lock, transaction, khả năng chạy lại và phục hồi.
- **Phát hành:** thứ tự triển khai, tương thích với phiên bản ứng dụng, môi trường và quy trình CI/CD.
- **Vận hành:** xử lý lỗi, schema drift, hotfix, backup/restore và cập nhật lịch sử sau thay đổi khẩn cấp.
- **Hợp đồng với nhóm khác:** quy định cột/API database nào được đọc, ghi, thay đổi hoặc ngừng sử dụng.

Một nhóm sở hữu miền khách hàng có thể chịu trách nhiệm cho schema `customer`, còn nhóm thanh toán sở hữu schema `payment`. Nhưng nếu bảng thanh toán tham chiếu khách hàng, cả hai nhóm cần thống nhất hợp đồng và thứ tự migration. Quyền sở hữu riêng **không xóa bỏ phụ thuộc liên miền**.

### 1.1. Phân biệt ba loại quyền

| Loại quyền | Câu hỏi | Ví dụ |
|---|---|---|
| **Quyền sở hữu nghiệp vụ** | Nhóm nào quyết định ý nghĩa và vòng đời dữ liệu? | Nhóm khách hàng định nghĩa trạng thái khách hàng. |
| **Quyền sở hữu mã migration** | Nhóm nào sửa/review changelog và chịu trách nhiệm changeset? | CODEOWNERS yêu cầu nhóm khách hàng review thư mục changelog customer. |
| **Quyền DBMS** | Tài khoản nào có thể đọc/ghi hoặc thay đổi object thật? | User runtime chỉ có DML; user migration có quyền DDL cần thiết. |

Ba loại này nên hỗ trợ lẫn nhau nhưng không nhất thiết giao cho cùng một người. Ví dụ, nhóm nghiệp vụ sở hữu schema nhưng tài khoản triển khai DDL do nền tảng database quản lý. Việc tách quyền giúp giảm rủi ro và xác định trách nhiệm khi có sự cố.

## 2. Chọn ranh giới: miền nghiệp vụ hay thành phần kỹ thuật?

Không có một cách chia duy nhất. Cần chọn ranh giới phản ánh cách dữ liệu được sở hữu và thay đổi trong thực tế.

### 2.1. Chia theo miền nghiệp vụ (domain)

Một miền nghiệp vụ đại diện cho một nhóm khái niệm và quy tắc dữ liệu liên quan:

| Miền | Object có thể sở hữu | Ví dụ trách nhiệm |
|---|---|---|
| Customer | `customer`, `customer_contact`, `customer_status` | Vòng đời khách hàng, thông tin liên hệ và quy tắc dữ liệu. |
| Order | `sales_order`, `order_line`, `order_event` | Đơn hàng, trạng thái và lịch sử xử lý. |
| Payment | `payment`, `payment_attempt`, `refund` | Giao dịch, hoàn tiền và đối soát. |
| Inventory | `stock_item`, `warehouse`, `reservation` | Tồn kho và giữ hàng. |
| Reporting | View/materialized view hoặc read model phục vụ báo cáo | Hợp đồng đọc dữ liệu, refresh và hiệu năng truy vấn. |

Ưu điểm là nhóm hiểu rõ ý nghĩa dữ liệu, quyết định thay đổi gần nhu cầu nghiệp vụ và giảm số người cần phối hợp cho thay đổi nội bộ miền. Thách thức là quy trình liên miền có thể cần dữ liệu hoặc ràng buộc chéo; một bảng dùng chung có thể bị nhiều nhóm muốn thay đổi; các miền có chu kỳ phát hành khác nhau.

### 2.2. Chia theo thành phần kỹ thuật (component)

Một thành phần có thể là schema dùng chung, audit, identity, reporting, nền tảng lưu trữ hoặc phần mở rộng database.

| Thành phần | Phạm vi | Lưu ý |
|---|---|---|
| Audit | Bảng nhật ký, trigger hoặc partition audit | Cần thống nhất retention và quyền đọc. |
| Identity | Bảng tài khoản, role và mapping | Tránh để service nghiệp vụ tự sửa cấu trúc bảo mật. |
| Shared reference data | Danh mục dùng chung | Phải có owner quyết định giá trị và chính sách tương thích. |
| Reporting | View, materialized view, bảng tổng hợp | Phụ thuộc schema nguồn và lịch refresh. |
| Database platform | Extension, role, schema, tablespace, cấu hình | Thường do nhóm nền tảng/DBA sở hữu. |

Chia theo component phù hợp với chức năng hạ tầng dùng chung, nhưng cần tránh tạo một nhóm database trở thành nút thắt cho mọi thay đổi nghiệp vụ nhỏ. Nhóm nền tảng nên sở hữu tiêu chuẩn, quyền, công cụ và object hạ tầng; nhóm miền vẫn chịu trách nhiệm mô hình dữ liệu của mình.

### 2.3. Chọn ranh giới theo mức độ liên kết

Hãy đặt câu hỏi:

1. Ai hiểu rõ quy tắc nghiệp vụ của dữ liệu?
2. Nhóm nào chịu trách nhiệm khi dữ liệu sai?
3. Thay đổi có thể phát hành độc lập không?
4. Object có được nhiều service ghi trực tiếp không?
5. Những phụ thuộc schema nào bắt buộc phải đồng bộ?
6. Có thể kiểm soát quyền ở schema hoặc database account không?

Nếu hai nhóm thường xuyên phải sửa cùng một bảng, ranh giới ownership chưa tốt hoặc hợp đồng tích hợp chưa rõ. Có thể cần một owner duy nhất cho bảng, một API/event thay cho ghi chéo, hoặc chia lại dữ liệu theo bounded context.

## 3. Một owner cho mỗi object có thể thay đổi

Một nguyên tắc hữu ích là **mỗi object database có một nhóm chịu trách nhiệm cuối cùng**. Các nhóm khác có thể là consumer, reviewer hoặc contributor theo quy trình, nhưng không nên có nhiều nhóm cùng tự ý sửa cùng một object.

Ví dụ:

~~~text
customer.customer_record       -> Customer team (owner)
payment.payment_record         -> Payment team (owner)
reporting.customer_summary     -> Reporting team (owner)
platform.audit_event           -> Database platform team (owner)
~~~

Nếu bảng `customer_record` nằm trong schema `customer`, nhóm Customer sở hữu thay đổi cấu trúc và dữ liệu của bảng. Nhóm Reporting có thể yêu cầu thêm trường phục vụ báo cáo, nhưng cần gửi yêu cầu cho owner; nếu cần dữ liệu mới, hai nhóm thống nhất contract và lịch triển khai. Reporting không tự thêm cột vào bảng nguồn trong changelog riêng.

### 3.1. Owner không có nghĩa độc quyền mọi quyết định

Owner chịu trách nhiệm cuối cùng, nhưng một thay đổi có thể cần:

- **Reviewer nghiệp vụ:** xác nhận semantics và dữ liệu.
- **Reviewer database:** đánh giá SQL, index, lock, transaction và rollback.
- **Reviewer consumer:** xác minh ứng dụng phụ thuộc không bị phá vỡ.
- **Platform/DBA:** xác minh quyền, chuẩn vận hành, backup và tác động hạ tầng.

Mức review phụ thuộc độ rủi ro. Thêm nullable column ít tác động có thể cần review gọn; đổi primary key hoặc xóa cột đang được nhiều service dùng cần phối hợp rộng hơn.

## 4. Cấu trúc changelog theo miền hoặc thành phần

Một repository có thể tổ chức changelog theo owner:

~~~text
db/
  changelog/
    root.yaml
    customer/
      changelog.yaml
      changes/
        001-create-customer.yaml
        002-add-customer-email.yaml
    order/
      changelog.yaml
      changes/
        001-create-order.yaml
        002-add-order-status.yaml
    payment/
      changelog.yaml
      changes/
        001-create-payment.yaml
    reporting/
      changelog.yaml
      changes/
        001-create-customer-summary-view.sql
    platform/
      changelog.yaml
      changes/
        001-create-audit-schema.yaml
~~~

Đây là **cách tổ chức minh họa**, không phải cấu trúc bắt buộc của Liquibase. Tên thư mục phản ánh owner; ID, author và đường dẫn định danh phải được quản lý ổn định.

### 4.1. Root changelog làm điểm hợp nhất

Ví dụ `root.yaml`:

~~~yaml
databaseChangeLog:
  - include:
      file: customer/changelog.yaml
      relativeToChangelogFile: true
  - include:
      file: order/changelog.yaml
      relativeToChangelogFile: true
  - include:
      file: payment/changelog.yaml
      relativeToChangelogFile: true
  - include:
      file: reporting/changelog.yaml
      relativeToChangelogFile: true
  - include:
      file: platform/changelog.yaml
      relativeToChangelogFile: true
~~~

Root changelog cung cấp **điểm vào chung** cho một lần migration. Nó giúp pipeline biết cần nạp những phần nào; nó không tự giải quyết dependency giữa miền, ownership hoặc xung đột ID.

Thứ tự `include` có ý nghĩa đối với thứ tự changeset được nạp và thực thi. Nếu Payment cần bảng Customer tồn tại trước, phải thiết kế thứ tự và hợp đồng phụ thuộc rõ ràng. Không nên để thứ tự alphabet tình cờ quyết định thứ tự triển khai.

### 4.2. Include và includeAll

- `include` chỉ định rõ một changelog. Cách này dễ review, kiểm soát thứ tự và ít bất ngờ.
- `includeAll` nạp một thư mục theo quy tắc của Liquibase. Cách này tiện cho nhiều file nhỏ nhưng cần kiểm soát tên, thứ tự, file được chọn và cách thêm file mới.

Khi nhiều nhóm cùng commit, `includeAll` có thể khiến một file mới tự tham gia root changelog mà reviewer không nhận ra thay đổi thứ tự. Nếu dependency phức tạp hoặc phát hành cần kiểm soát chặt, `include` tường minh thường dễ hiểu hơn.

Không di chuyển changelog đã chạy mà không cân nhắc `logicalFilePath`. Đổi đường dẫn định danh có thể khiến Liquibase nhận diện cùng changeset như một changeset mới, gây pending giả hoặc lỗi thực thi lại.

### 4.3. Không dùng folder như cơ chế cô lập duy nhất

Hai nhóm có thư mục riêng nhưng cùng quyền DDL trên mọi schema vẫn có thể sửa object của nhau. Folder giúp tổ chức mã nguồn và review; ranh giới thật cần thêm:

- Owner được ghi rõ trong tài liệu/repository policy.
- CODEOWNERS hoặc quy tắc review tương đương.
- Tài khoản runtime và migration có quyền phù hợp.
- Schema/database grants giới hạn phạm vi thay đổi.
- CI kiểm tra changelog, naming và phạm vi object khi khả thi.

## 5. ID, author và đường dẫn: tránh xung đột khi cộng tác

Liquibase nhận diện changeset bằng bộ ba **ID, author và đường dẫn định danh changelog**. Khi nhiều nhóm làm song song, việc dùng ID trùng không nhất thiết gây xung đột nếu bộ ba khác, nhưng ID khó đọc hoặc định danh không ổn định khiến audit và review phức tạp.

### 5.1. Quy ước ID và author

Một quy ước dễ hiểu có thể là:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: customer-2026-11-19-001
      author: team-customer
      changes:
        - addColumn:
            tableName: customer_record
            columns:
              - column:
                  name: preferred_language
                  type: VARCHAR(20)
~~~

ID ở ví dụ có ngày và sequence để giảm khả năng trùng khi nhiều người làm việc. Có thể dùng UUID hoặc quy ước khác; quan trọng là ID ổn định và không tái sử dụng cho ý nghĩa thay đổi khác. Author nên là định danh nhóm hoặc người theo policy, không nên đổi tùy tiện sau khi đã triển khai.

### 5.2. Khi merge hai nhánh

Giả sử nhánh Customer và Payment cùng thêm changeset:

~~~text
Branch customer:
  customer/.../001-add-language

Branch payment:
  payment/.../001-add-payment-status
~~~

Nếu mỗi file có path định danh riêng, ID trùng không tự động đồng nghĩa cùng một changeset. Tuy nhiên, phải kiểm tra:

- Cả hai file đã được include vào root.
- Không có bộ ba định danh trùng.
- Thứ tự giữa các changeset có phụ thuộc được xác định.
- Không có hai nhánh sửa cùng một file changelog gốc.
- Changelog đã chạy ở môi trường nào chưa trước khi đổi path/ID.

Không sửa ID đã phát hành chỉ để giải quyết xung đột merge; thêm changeset mới hoặc xử lý định danh theo một kế hoạch có kiểm chứng.

## 6. Phụ thuộc giữa các miền và thứ tự migration

Phân chia ownership không có nghĩa mỗi miền có thể triển khai độc lập trong mọi trường hợp. Một miền có thể phụ thuộc vào object do miền khác sở hữu:

~~~text
Customer domain
  customer_record(id)
       |
       | referenced by
       v
Payment domain
  payment_record(customer_id)
       |
       v
Reporting domain
  customer_payment_summary view
~~~

Trong ví dụ:

- Customer owner tạo và quản lý bảng `customer_record`.
- Payment owner tạo `payment_record` và foreign key đến Customer nếu kiến trúc chọn database-level FK.
- Reporting owner tạo view phụ thuộc hai bảng.

### 6.1. Quy tắc phối hợp dependency

1. Consumer không tự tạo hoặc thay đổi object thuộc owner khác.
2. Owner cung cấp hợp đồng: schema, kiểu, nullability, ý nghĩa, uniqueness và quy tắc tương thích.
3. Changeset tạo object nguồn phải được triển khai trước object phụ thuộc.
4. Thay đổi phá vỡ contract cần lộ trình chuyển tiếp và xác nhận consumer.
5. Xóa object nguồn chỉ sau khi tất cả phụ thuộc đã được chuyển hoặc loại bỏ.

### 6.2. Foreign key liên miền có phải luôn cần?

Không. Foreign key giúp DBMS bảo vệ tính toàn vẹn tham chiếu, nhưng có thể tạo coupling triển khai giữa hai miền, nhất là khi chúng thuộc các service/database độc lập. Nếu dữ liệu được phân tán hoặc service sở hữu database riêng, một foreign key xuyên database có thể không khả thi hoặc không phù hợp.

Quyết định dùng FK cần cân nhắc:

- Hai bảng có thực sự nằm trong cùng database và cùng boundary vận hành không?
- Có thể đảm bảo thứ tự migration và tương thích release không?
- Xóa/archival dữ liệu ở miền nguồn có ảnh hưởng miền tiêu thụ không?
- Hợp đồng có thể được bảo vệ qua API/event và kiểm tra bất đồng bộ không?

Không thêm FK chỉ để “schema đẹp”, cũng không bỏ FK chỉ để giảm phối hợp nếu nghiệp vụ cần đảm bảo toàn vẹn đồng bộ.

### 6.3. Dependency ở changelog

Liquibase thực thi changeset theo thứ tự được nạp trong changelog sau khi áp dụng filters và điều kiện. Không nên giả định Liquibase tự suy luận toàn bộ dependency chỉ từ SQL hoặc tên bảng. Hãy sắp xếp include, chia changelog và thiết kế precondition phù hợp.

Precondition `tableExists` hoặc `columnExists` có thể làm migration dừng nếu dependency chưa có. Đây là cơ chế bảo vệ giả định, không phải cách thay thế kế hoạch thứ tự. Dùng `onFail="MARK_RAN"` để bỏ qua dependency thiếu có thể làm lịch sử ghi đã xử lý trong khi object thật chưa được tạo.

## 7. Phân chia quyền ở cấp DBMS

Một quy trình cộng tác tốt không chỉ dựa vào review code. Tài khoản database cần phản ánh quyền hạn thực tế.

| Tài khoản/role | Quyền điển hình | Không nên có mặc định |
|---|---|---|
| Application runtime | SELECT/INSERT/UPDATE/DELETE cần cho ứng dụng. | Quyền ALTER/DROP schema rộng. |
| Liquibase migration | DDL và quyền cần để cập nhật schema thuộc phạm vi. | Quyền quản trị toàn server nếu không cần. |
| Read-only/reporting | SELECT trên view/bảng được phép. | Quyền DML hoặc DDL. |
| DBA/platform | Quản trị hạ tầng, user, backup, cấu hình và sự cố. | Dùng tài khoản cá nhân chạy ứng dụng thường ngày. |

Có thể tạo schema riêng cho từng miền và cấp quyền:

~~~sql
-- Ví dụ PostgreSQL, cần điều chỉnh owner/role theo chính sách thực tế.
CREATE SCHEMA customer AUTHORIZATION customer_owner;
GRANT USAGE ON SCHEMA customer TO customer_app;
GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA customer TO customer_app;
~~~

Ví dụ này chỉ minh họa quyền; quyền trên object được tạo trong tương lai, default privileges, sequence và routine cần được cấu hình riêng nếu ứng dụng cần. Không cấp quyền DDL cho role runtime chỉ để tránh lỗi permission trong migration.

### 7.1. Một database, nhiều schema hay nhiều database?

| Mô hình | Lợi ích | Đánh đổi |
|---|---|---|
| Một schema dùng chung | Dễ tạo FK và join; một nơi quản lý. | Coupling cao, khó giới hạn quyền theo owner. |
| Một database, nhiều schema theo miền | Ranh giới tên và grants rõ hơn; có thể dùng transaction/FK nội database tùy DBMS. | Cần quản lý cross-schema grants, migration và dependency. |
| Database riêng cho từng service/miền | Cô lập vận hành và quyền tốt hơn. | Không có transaction/FK xuyên database thông thường; tích hợp qua API/event. |

Không nên chọn mô hình chỉ để thuận tiện chia thư mục changelog. Boundary cần phù hợp domain, tải, tính nhất quán, backup/restore, bảo mật và khả năng vận hành.

## 8. Quy trình review changeset theo owner

Mỗi pull request thay đổi schema nên có thông tin tối thiểu:

- Miền/component sở hữu và người review.
- Object thay đổi, trạng thái trước/sau.
- Lý do nghiệp vụ và consumer bị ảnh hưởng.
- Changelog/changeset mới, precondition và rollback.
- SQL preview trên DBMS đích.
- Khả năng transaction, lock, downtime và dung lượng dữ liệu.
- Kế hoạch backfill/validation nếu thay đổi dữ liệu.
- Lộ trình tương thích ứng dụng cũ/mới.
- Cách xử lý khi deploy lỗi hoặc cần restore.

### 8.1. Ma trận review theo rủi ro

| Thay đổi | Owner cần review | Nhóm phối hợp thường cần |
|---|---|---|
| Thêm nullable column nội bộ miền | Owner miền | Consumer nếu có đọc object. |
| Thêm FK sang miền khác | Owner hai miền | DBA/platform, nhóm deploy. |
| Xóa cột hoặc đổi kiểu phá tương thích | Owner miền | Tất cả consumer, QA, platform. |
| Thêm index trên bảng lớn | Owner miền | DBA/platform và nhóm vận hành. |
| Thay trigger/routine dùng chung | Owner component | Mọi miền phụ thuộc và security reviewer. |
| Thay role/grant/schema | Platform/DBA | Owner miền và security. |

Mức review có thể thay đổi theo quy mô, nhưng **owner cuối cùng phải được xác định trước khi merge**.

### 8.2. CODEOWNERS và kiểm soát đường dẫn

Ví dụ quy tắc CODEOWNERS:

~~~text
/db/changelog/customer/   @team-customer
/db/changelog/order/      @team-order
/db/changelog/payment/    @team-payment
/db/changelog/reporting/  @team-reporting
/db/changelog/platform/   @team-database-platform
/db/changelog/root.yaml   @team-database-platform @team-release
~~~

Đây là ví dụ cú pháp CODEOWNERS; cần điều chỉnh tên nhóm theo hệ thống Git thực tế. CODEOWNERS hỗ trợ yêu cầu review nhưng không thay thế kiểm soát quyền trên database, test migration hoặc phê duyệt phát hành.

Root changelog có thể cần owner nền tảng và release vì nó điều phối thứ tự toàn hệ thống. Nhóm miền vẫn review nội dung changelog thuộc mình.

## 9. Xung đột khi nhiều nhóm thay đổi cùng một object

Tình huống khó nhất là hai nhóm cùng cần sửa một bảng hoặc cùng thêm changeset phụ thuộc vào cùng một cột.

Ví dụ:

- Customer muốn đổi `customer_record.email` thành nullable để hỗ trợ hồ sơ chưa xác minh.
- Marketing muốn thêm unique index trên `email` vì dùng email làm định danh chiến dịch.

Hai yêu cầu có thể xung đột: unique index cho phép một số NULL tùy DBMS, nhưng nhiều bản ghi không email hoặc email trùng có thể ảnh hưởng quy tắc nghiệp vụ. Không nên để hai PR merge độc lập rồi mới phát hiện.

### 9.1. Quy trình giải quyết

1. Chỉ định owner của bảng làm người điều phối.
2. Ghi rõ mỗi yêu cầu, bất biến dữ liệu và consumer.
3. Thống nhất contract cuối cùng: nullable hay không, unique trên toàn bảng hay chỉ giá trị không null, collation/case sensitivity.
4. Thiết kế một chuỗi changeset có thứ tự, có thể chia bước expand và contract.
5. Gộp hoặc phối hợp PR để tránh hai changeset cạnh tranh cùng object.
6. Chạy thử trên snapshot dữ liệu đại diện, kiểm tra duplicate/NULL trước khi thêm constraint.
7. Phát hành theo kế hoạch có tương thích với phiên bản ứng dụng đang chạy.

### 9.2. Không giải quyết xung đột bằng cách sửa changeset đã phát hành

Nếu một changeset của Customer đã chạy, Marketing không nên sửa nó để thêm unique index. Hãy thêm changeset mới thuộc owner của object hoặc owner đã được ủy quyền, có review của các nhóm liên quan. Điều này giữ lịch sử Liquibase rõ ràng và giúp rollback/điều tra có căn cứ.

## 10. Chia sẻ dữ liệu mà không chia sẻ quyền sửa schema

Một nhóm tiêu thụ dữ liệu không nhất thiết cần quyền sửa bảng nguồn. Có một số mô hình:

| Cách chia sẻ | Khi phù hợp | Trách nhiệm |
|---|---|---|
| View do owner nguồn hoặc reporting owner quản lý | Cần contract đọc ổn định trên cùng database. | Owner view quản lý definition; owner nguồn thông báo thay đổi. |
| Read model/projection | Cần dữ liệu tối ưu cho truy vấn riêng. | Nhóm xây projection quản lý schema và quá trình đồng bộ. |
| API/service contract | Service khác sở hữu database riêng. | Producer quản lý dữ liệu, consumer dùng API. |
| Event/CDC | Cần tích hợp bất đồng bộ hoặc xây read model. | Producer quản lý event schema/version; consumer quản lý storage riêng. |
| Replication/read replica | Nhu cầu đọc lớn hoặc báo cáo. | Platform quản lý replication; owner dữ liệu quản lý contract. |

Không để một service khác truy cập và sửa trực tiếp bảng của miền chỉ vì cùng database. Nếu cần quyền ghi chéo, phải có hợp đồng và owner phê duyệt, đồng thời xem xét việc phá vỡ ranh giới domain.

### 10.1. View cũng có owner

Một view báo cáo có thể phụ thuộc bảng của Customer và Payment. Reporting team sở hữu view và changeset tạo view, nhưng không sở hữu bảng nguồn. Khi cột nguồn đổi tên hoặc bị xóa, owner nguồn cần thông báo và phối hợp trước khi triển khai.

Có thể triển khai expand–migrate–contract:

1. Thêm cột mới song song với cột cũ.
2. View và consumer chuyển sang cột mới.
3. Xác nhận không còn truy vấn cột cũ.
4. Xóa cột cũ bằng changeset mới sau khi owner/consumer xác nhận.

## 11. Release và thứ tự triển khai nhiều miền

Root changelog tạo một luồng triển khai chung, nhưng release cần quản lý dependency giữa các nhóm. Một thay đổi liên miền có thể cần:

~~~text
Release R:
  1. Customer: thêm cột mới nullable
  2. Payment: thêm cột tham chiếu/logic tương thích
  3. Deploy ứng dụng Customer và Payment có thể đọc cả hai dạng
  4. Backfill dữ liệu
  5. Reporting: cập nhật view
  6. Kiểm chứng tất cả consumer
  7. Customer: contract, bỏ cột cũ ở release sau
~~~

Đây là lịch trình minh họa; thứ tự thực tế phụ thuộc dependency và chiến lược triển khai. Không nên gộp tất cả vào một changeset lớn chỉ vì chúng cùng một release. Chia changeset theo bước giúp xác định chính xác phần nào đã chạy nếu có lỗi.

### 11.1. Một owner hay một pipeline trung tâm?

| Mô hình | Đặc điểm | Phù hợp khi |
|---|---|---|
| **Pipeline migration trung tâm** | Một pipeline chạy root changelog và điều phối toàn database. | Có database dùng chung, cần thứ tự toàn cục và kiểm soát chặt. |
| **Pipeline theo miền** | Mỗi miền có changelog/pipeline riêng, dùng schema/database riêng hoặc cơ chế điều phối đã định nghĩa. | Các miền tương đối độc lập, có thể phát hành riêng. |

Nếu nhiều pipeline độc lập cùng chạy trên **một database và cùng bảng history Liquibase**, cần hiểu cơ chế lock và thứ tự changeset. Lock giúp serialize việc cập nhật history nhưng không giải quyết dependency nghiệp vụ hoặc xung đột DDL. Không cho các pipeline cùng sở hữu một object chạy tùy ý.

Với database dùng chung, pipeline trung tâm thường dễ kiểm soát hơn; nhóm miền vẫn sở hữu nội dung changeset, còn nhóm release/platform chịu trách nhiệm hợp nhất và thực thi.

## 12. Tài khoản và changelog khi có nhiều database

Trong kiến trúc database riêng theo service, mỗi service có thể có:

- Changelog root riêng.
- Bảng `DATABASECHANGELOG` và `DATABASECHANGELOGLOCK` riêng.
- Tài khoản migration riêng.
- Quy trình release và backup riêng.
- Contract API/event với các service khác.

Không dùng một tài khoản migration có quyền DDL trên mọi database nếu không cần. Nếu một nghiệp vụ yêu cầu migration nhiều database, orchestration cần xác định thứ tự, retry và trạng thái từng database; không giả định một transaction Liquibase có thể commit nguyên tử trên nhiều database độc lập.

## 13. Xử lý hotfix và thay đổi ngoài quy trình trong mô hình ownership

Một hotfix DBA có thể là cần thiết để khôi phục dịch vụ. Sau khi ổn định, owner của object phải:

1. Thu thập SQL, thời điểm, ticket, người thực hiện và database đã áp dụng.
2. Kiểm tra object thực tế trên mọi môi trường.
3. Xác định hotfix được giữ hay cần remediation.
4. Tạo changeset mới phản ánh thay đổi đã được chấp nhận, hoặc migration đưa schema về chuẩn.
5. Kiểm thử từ database chưa có hotfix và database đã có hotfix.
6. Đối chiếu `DATABASECHANGELOG`, schema diff và dữ liệu sau xử lý.

Không sửa changeset lịch sử đã chạy để “đưa hotfix vào quá khứ”. Không tự xóa hàng `DATABASECHANGELOG` hoặc chạy `changelogSync` để làm sạch history khi chưa kiểm tra schema.

## 14. Cộng tác trong CI/CD

Một quy trình CI/CD hỗ trợ ownership có thể gồm:

~~~mermaid
flowchart TD
    A[Nhóm miền mở PR changelog] --> B[CODEOWNERS yêu cầu owner review]
    B --> C[Kiểm tra ID/path/include và dependency]
    C --> D[Liquibase validate + status + SQL preview]
    D --> E[Test trên DB đại diện]
    E --> F[Review consumer và platform nếu cần]
    F --> G[Merge vào root release]
    G --> H[Pipeline migration được điều phối]
    H --> I[Kiểm tra DATABASECHANGELOG và schema]
    I --> J[Smoke test service và consumer]
~~~

Các kiểm tra có thể tự động:

- File changelog mới phải nằm trong thư mục owner được phép.
- ID/author/path không trùng theo quy ước.
- Changelog con phải được include.
- Changeset mới không sửa nội dung đã phát hành ngoài policy.
- Root changelog có thứ tự dependency được review.
- `validate`, `status` và SQL preview chạy bằng phiên bản Liquibase đã khóa.
- Test migration trên database cùng loại DBMS và có dữ liệu đại diện.
- Báo cáo changeset ảnh hưởng object của nhiều miền cần reviewer tương ứng.

Tự động hóa không thể thay thế review nghiệp vụ, đánh giá lock trên bảng lớn hoặc phê duyệt hotfix. CI cần đưa ra bằng chứng để người review quyết định.

## 15. Các lỗi cộng tác thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Hai nhóm cùng thêm cột vào một bảng | Không có owner duy nhất hoặc contract chung. | Chỉ định owner, hợp nhất yêu cầu và changeset. |
| Changeset trùng định danh | Quy ước ID/author/path không rõ. | Xác minh history và định danh; tạo ID mới trước khi phát hành. |
| Merge xong nhưng migration chạy sai thứ tự | Include order hoặc dependency không được review. | Sắp xếp root changelog và thêm precondition phù hợp. |
| Một nhóm xóa cột nhóm khác đang dùng | Consumer không được thông báo hoặc không có contract. | Expand–migrate–contract, xác nhận usage trước contract. |
| Pipeline miền chạy đồng thời trên database chung | Không có release orchestration; hiểu nhầm lock là dependency manager. | Dùng pipeline điều phối chung hoặc tách database/ownership rõ ràng. |
| Runtime app có thể ALTER TABLE | Cấp quyền quá rộng hoặc ORM tự cập nhật schema. | Tách runtime role và migration role; tắt auto DDL production. |
| Hotfix không có trong changelog | Thiếu quy trình hậu hotfix. | Owner ghi nhận bằng changeset mới và diff lại. |
| Root changelog tự nạp file ngoài dự kiến | Dùng includeAll thiếu kiểm soát. | Review filter/order, cân nhắc include tường minh. |
| Changelog di chuyển khiến changeset thành pending | Đường dẫn định danh thay đổi. | Bảo toàn logicalFilePath và kiểm tra FILENAME. |
| Nhiều nhóm sửa view dùng chung | Không có owner component hoặc dependency contract. | Chỉ định owner view, phối hợp owner bảng nguồn. |

## 16. Bài thực hành có kiểm chứng

**Bối cảnh:** một hệ thống có ba miền Customer, Payment và Reporting dùng chung một PostgreSQL database. Customer sở hữu bảng khách hàng, Payment sở hữu bảng thanh toán, Reporting sở hữu view tổng hợp.

### Giai đoạn A — Phân chia ownership

1. Liệt kê bảng, view, routine và schema thuộc từng miền.
2. Gán một owner cuối cùng cho từng object.
3. Xác định object dùng chung, consumer và quyền truy cập.
4. Viết quy ước ID/author/path và reviewer cho từng thư mục changelog.

### Giai đoạn B — Tổ chức changelog

1. Tạo cấu trúc thư mục changelog theo miền trong project lab.
2. Viết changelog con cho Customer, Payment, Reporting.
3. Tạo root changelog dùng `include` tường minh.
4. Đặt thứ tự tạo bảng nguồn trước bảng phụ thuộc và view.
5. Chạy `validate` và kiểm tra SQL preview trên PostgreSQL thử nghiệm.

### Giai đoạn C — Thử xung đột liên miền

1. Giả lập Customer muốn đổi nullability của email, Reporting cần dùng email làm dimension.
2. Ghi rõ contract hiện tại và consumer.
3. Thiết kế thay đổi tương thích, ví dụ thêm cột/logic song song trước khi contract.
4. Yêu cầu owner Customer và Reporting review.
5. Chạy migration trên database có dữ liệu giả lập chứa NULL/duplicate để kiểm tra constraint.

### Giai đoạn D — Kiểm chứng pipeline và quyền

1. Dùng runtime role chỉ có quyền DML cần thiết.
2. Dùng migration role riêng để áp dụng changelog.
3. Xác minh runtime không thể ALTER/DROP object ngoài ý muốn.
4. Kiểm tra root changelog nạp đúng tất cả changeset và đúng thứ tự.
5. Chạy lại pipeline và đối chiếu `DATABASECHANGELOG`, schema, view và ứng dụng.

**Tiêu chí đạt:** mỗi object có owner; consumer không tự sửa object nguồn; dependency được thể hiện rõ; root changelog hợp nhất có thứ tự; quyền runtime/migration được tách; thay đổi liên miền có review và kiểm thử.

## 17. Checklist thiết kế ownership

- [ ] Mỗi schema/table/view/routine quan trọng có owner chịu trách nhiệm cuối cùng.
- [ ] Ranh giới domain/component phản ánh ý nghĩa dữ liệu và khả năng phát hành độc lập.
- [ ] Có danh sách consumer và hợp đồng đọc/ghi cho object chia sẻ.
- [ ] Changelog được tổ chức theo owner và có root include được review.
- [ ] ID, author, filename/logicalFilePath có quy ước ổn định.
- [ ] Include order và dependency giữa miền được xác định.
- [ ] CODEOWNERS hoặc cơ chế review tương đương bảo vệ thư mục migration.
- [ ] Runtime role và migration role được tách quyền.
- [ ] Object dùng chung có quy trình phối hợp và owner rõ ràng.
- [ ] Breaking changes dùng lộ trình tương thích, không xóa cột đột ngột.
- [ ] Hotfix ngoài quy trình được ghi nhận bằng changeset mới sau điều tra.
- [ ] Pipeline có validate, status, SQL preview, test và xác minh sau deploy.
- [ ] Nhiều pipeline không tự ý cạnh tranh trên cùng database/object.
- [ ] Có backup/restore và quy trình sự cố cho thay đổi rủi ro cao.

## 18. Câu hỏi tự kiểm tra

1. Quyền sở hữu nghiệp vụ, quyền sở hữu changelog và quyền DBMS khác nhau như thế nào?
2. Khi nào nên chia changelog theo domain, khi nào theo component?
3. Vì sao mỗi object cần một owner cuối cùng dù nhiều nhóm cùng sử dụng?
4. Root changelog có vai trò gì khi nhiều nhóm phát triển changelog con?
5. `include` và `includeAll` khác nhau ở mức kiểm soát thứ tự như thế nào?
6. Vì sao thay đổi đường dẫn changelog đã chạy cần xem xét `logicalFilePath`?
7. Làm thế nào xử lý dependency khi Payment cần bảng Customer?
8. Khi nào foreign key liên miền tạo coupling không phù hợp?
9. Vì sao CODEOWNERS không thay thế quyền DBMS và test migration?
10. Tại sao runtime role không nên có quyền DDL rộng?
11. Khi hai nhóm muốn thay đổi cùng một cột, ai điều phối và cần thống nhất những gì?
12. Làm thế nào chia sẻ dữ liệu mà không cho consumer sửa trực tiếp bảng nguồn?
13. Vì sao nhiều pipeline chạy trên cùng database vẫn có thể gây lỗi dù Liquibase có lock?
14. Sau hotfix DBA, owner cần làm gì để đưa thay đổi trở lại lịch sử migration?

## Kết luận

Phân chia quyền sở hữu theo miền nghiệp vụ hoặc thành phần giúp nhóm biết **ai quyết định cấu trúc, ai quản lý changeset và ai chịu trách nhiệm vận hành**. Changelog theo owner, root include rõ ràng, định danh ổn định, quyền DBMS phù hợp và quy trình review liên miền tạo ra ranh giới cộng tác có thể kiểm soát. Liquibase cung cấp lịch sử và cơ chế triển khai; nhóm vẫn phải quản lý dependency, hợp đồng consumer, quyền và thứ tự release. Khi mỗi object có owner rõ ràng và mọi thay đổi được đưa qua một quy trình có kiểm chứng, `DATABASE_SCHEMA_MIGRATION_LIQUIBASE` có thể hỗ trợ nhiều nhóm phát triển mà vẫn giữ schema nhất quán, dễ truy vết và an toàn khi thay đổi.
