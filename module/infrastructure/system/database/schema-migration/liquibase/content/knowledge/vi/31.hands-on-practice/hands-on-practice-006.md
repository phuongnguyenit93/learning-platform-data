# Mô phỏng xung đột nhánh và xử lý thứ tự migration

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, mục tiêu là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài thực hành này mô phỏng tình huống nhiều nhánh phát triển cùng thay đổi database, sau đó được hợp nhất và cần triển khai theo một thứ tự nhất quán.

Xung đột migration có thể xuất hiện ngay cả khi Git merge thành công. Hai nhánh có thể thêm cùng một cột, tạo hai index tương đương, hoặc một nhánh thêm foreign key phụ thuộc bảng mà nhánh kia chưa tạo. Một changeset có thể hợp lệ khi chạy riêng trên database của nhánh, nhưng thất bại khi toàn bộ thay đổi được ghép vào root changelog của release.

Cần phân biệt ba lớp vấn đề:

1. **Xung đột mã nguồn:** Git không thể tự hợp nhất nội dung changelog hoặc root include.
2. **Xung đột định danh/lịch sử:** hai changeset dùng cùng định danh Liquibase nhưng có nội dung khác, hoặc đường dẫn changelog thay đổi.
3. **Xung đột ngữ nghĩa database:** các changeset có định danh khác nhau nhưng cùng tác động một đối tượng, hoặc thứ tự thực thi không thỏa dependency.

Mục tiêu là mô phỏng các tình huống này, xác định thứ tự phụ thuộc, hợp nhất changelog an toàn và kiểm chứng cùng một artifact trên database mới lẫn database đã có lịch sử.

## 1. Mô hình nhánh phát triển và migration

Một nhóm có thể phát triển song song các tính năng trên cùng schema. Mỗi nhánh thường chứa code ứng dụng và một hoặc nhiều changeset.

Ví dụ:

~~~text
main
 |
 +-- feature/order-status
 |      +-- thêm cột delivery_status
 |      +-- cập nhật code ghi trạng thái
 |
 +-- feature/order-status-check
 |      +-- thêm CHECK cho delivery_status
 |      +-- giả định cột đã tồn tại
 |
 +-- feature/customer-index
        +-- tạo index trên orders.customer_id
~~~

Khi merge, các thay đổi không chỉ cần hợp nhất về cú pháp. Chúng cần được sắp xếp sao cho:

- Đối tượng được tham chiếu đã tồn tại.
- Cột và kiểu dữ liệu đúng với giả định của changeset phụ thuộc.
- Constraint chỉ được tạo khi dữ liệu đã đạt điều kiện.
- Index không bị tạo trùng hoặc sai định nghĩa.
- Các changeset đã triển khai không bị sửa nội dung.
- Mọi môi trường nhận cùng một chuỗi migration có thể tái lập.

### 1.1. Một nhánh Git không phải một migration lifecycle

Git branch là phạm vi phát triển source. Liquibase history được lưu trong từng database target. Việc tạo, đổi tên hoặc xóa branch không tự thay đổi DATABASECHANGELOG.

Nếu một nhánh đã chạy migration lên database dùng chung, database đó đã có trạng thái thật. Xóa branch hoặc reset commit không đảo DDL/DML. Trước khi merge/rebase, phải biết nhánh đã được deploy ở đâu và changeset nào đã chạy.

### 1.2. Phân biệt môi trường riêng và môi trường dùng chung

| Kiểu môi trường | Cách dùng | Hệ quả khi merge |
|---|---|---|
| Database ephemeral theo branch | Tạo mới và xóa sau test | Có thể reset khi branch thay đổi; không coi history là production history |
| Database tích hợp dùng chung | Nhiều branch cùng triển khai | Dễ xung đột schema và history; cần điều phối release |
| Staging theo release | Chạy artifact đã hợp nhất | Phải dùng chuỗi changeset chính thức |
| Production | Chỉ nhận artifact đã phê duyệt | Không sửa lịch sử đã triển khai; cần forward-fix khi cần |

Ưu tiên database riêng cho mỗi nhánh khi cần thử migration song song. Nếu buộc phải dùng chung database tích hợp, cần quy định branch nào được phép deploy, cách đặt tên schema và cách dọn trạng thái sau test.

## 2. Ba lớp xung đột cần nhận diện

### 2.1. Xung đột Git

Hai nhánh cùng sửa một root changelog hoặc một file YAML có thể tạo conflict marker. Ví dụ:

~~~text
<<<<<<< feature/order-status
- include:
    file: db/changelog/orders/add-delivery-status.yaml
=======
- include:
    file: db/changelog/orders/add-order-state.yaml
>>>>>>> feature/order-state
~~~

Các marker này làm YAML không hợp lệ và không được để lọt vào artifact. Resolve conflict cần giữ đúng các include cần thiết, đúng thứ tự và không bỏ sót changeset.

### 2.2. Xung đột định danh Liquibase

Liquibase nhận diện changeset dựa trên tổ hợp định danh, thông thường gồm id, author và đường dẫn file changelog (logical path). Nếu hai nhánh tạo cùng id, author và cùng đường dẫn nhưng nội dung khác nhau, database đã chạy một nhánh có thể gặp checksum mismatch khi nhận artifact của nhánh kia.

Ví dụ cả hai nhánh cùng tạo:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: orders-120-add-delivery-status
      author: team-orders
      changes:
        - addColumn:
            schemaName: app
            tableName: orders
            columns:
              - column:
                  name: delivery_status
                  type: VARCHAR(20)
~~~

Nhánh còn lại cũng dùng id/author/path đó nhưng định nghĩa VARCHAR(30) hoặc thêm default khác. Đây là xung đột lịch sử, không chỉ là xung đột Git.

Không giải quyết bằng cách sửa MD5SUM, chạy clear-checksums hoặc xóa dòng DATABASECHANGELOG để ép Liquibase chấp nhận nội dung mới. Trước tiên phải xác định database nào đã chạy phiên bản nào.

### 2.3. Xung đột ngữ nghĩa schema

Hai changeset có thể có id khác nhau nhưng cùng thêm cột delivery_status. Liquibase coi chúng là hai changeset khác nhau; database vẫn chỉ có thể tạo cột một lần.

Ví dụ:

- Nhánh A thêm delivery_status VARCHAR(20).
- Nhánh B thêm delivery_status VARCHAR(30) DEFAULT 'PENDING'.

Khi chạy tuần tự trên một database trống, changeset thứ hai có thể thất bại vì cột đã tồn tại. Nếu một nhánh tạo index trước khi nhánh kia tạo cột, migration có thể thất bại do dependency chưa được đáp ứng.

Đây là xung đột nghiệp vụ/schema. Git không thể tự phát hiện bằng cách so sánh dòng văn bản.

## 3. Hiểu định danh changeset và checksum

Một changeset thường có các thành phần:

- id: định danh do nhóm phát triển đặt.
- author: tác giả hoặc nhóm sở hữu.
- filepath/logicalFilePath: đường dẫn changelog dùng để nhận diện.
- Nội dung change và thuộc tính ảnh hưởng tới checksum.
- Context, label, DBMS filter và các thuộc tính thực thi liên quan.

Hai changeset có id giống nhau nhưng author hoặc file path khác có thể được Liquibase coi là hai định danh riêng. Tuy nhiên, không nên dựa vào khác biệt path để né xung đột. Cần quy ước id dễ truy vết và duy nhất trong phạm vi module.

### 3.1. Quy ước đặt id

Ví dụ:

~~~yaml
- changeSet:
    id: ORD-1842-001-add-delivery-status
    author: team-orders
    changes:
      - addColumn:
          schemaName: app
          tableName: orders
          columns:
            - column:
                name: delivery_status
                type: VARCHAR(20)
~~~

Có thể dùng ticket/feature key, domain và số thứ tự. Mục tiêu là giảm xác suất hai nhánh tạo cùng id, đồng thời giúp truy vết changeset về yêu cầu và owner.

Quy ước id không thay thế review ngữ nghĩa. Hai id khác nhau vẫn có thể tạo cùng một đối tượng.

### 3.2. File path và logicalFilePath

Di chuyển file changelog có thể làm thay đổi định danh changeset nếu logical path không được giữ ổn định. Khi refactor thư mục, cần kiểm tra cách phiên bản Liquibase đang dùng xử lý logicalFilePath và history hiện có.

Không đổi tên hoặc di chuyển file đã triển khai mà không có kế hoạch tương thích. Nếu cần giữ định danh lịch sử, xác minh cấu hình logicalFilePath bằng test trên bản sao database trước khi merge.

### 3.3. Checksum mismatch sau merge

Khi Liquibase báo checksum mismatch:

1. Xác định changeset id, author và filename.
2. Đọc checksum đã lưu trong DATABASECHANGELOG.
3. So sánh nội dung artifact hiện tại với bản đã phát hành.
4. Xác định nhánh nào đã deploy và môi trường nào bị ảnh hưởng.
5. Kiểm tra có sửa changeset lịch sử, đổi path hoặc thay property substitution không.
6. Chọn khôi phục nội dung cũ hoặc tạo changeset mới.

Checksum mismatch là tín hiệu cần điều tra tính bất biến của lịch sử. Không xóa cảnh báo nếu chưa hiểu nguồn gốc.

## 4. Biểu diễn dependency giữa changeset

Thứ tự migration phải dựa trên quan hệ phụ thuộc, không dựa đơn thuần vào thời điểm commit hoặc tên branch.

Ví dụ:

~~~text
Create customers table
          |
          v
Create orders table
          |
          v
Add orders.delivery_status
          |
          +------------------+
          |                  |
          v                  v
Backfill status       Create supporting index
          |                  |
          v                  |
Validate status             |
          |                  |
          v                  |
Add CHECK / NOT NULL         |
          |                  |
          +---------+--------+
                    |
                    v
             Add foreign key
                    |
                    v
             Application switch
~~~

Sơ đồ chỉ là ví dụ. Trong thực tế, index có thể cần trước FK hoặc sau tùy DBMS/workload; constraint có thể được thêm NOT VALID rồi validate ở bước sau. Hãy mô hình hóa dependency thực tế.

### 4.1. Dependency graph

Có thể biểu diễn mỗi changeset như một node. Cạnh A → B có nghĩa B chỉ được chạy sau khi A hoàn tất.

Ví dụ:

| Changeset | Phụ thuộc | Lý do |
|---|---|---|
| create-customers | Không | Tạo bảng cha |
| create-orders | Không | Tạo bảng con ban đầu |
| add-delivery-status | create-orders | Cột cần được thêm vào bảng |
| backfill-delivery-status | add-delivery-status | Cột phải tồn tại |
| add-status-check | backfill-delivery-status | Dữ liệu cần đạt điều kiện |
| add-orders-customer-fk | create-customers, create-orders | Hai bảng và parent key phải tồn tại |

Một thứ tự hợp lệ là thứ tự topo của dependency graph. Nếu graph có chu trình, cần xem lại thiết kế hoặc chia thay đổi thành nhiều giai đoạn.

### 4.2. Commit order không phải execution order

Một nhánh có thể được merge sau nhưng changeset của nó phải chạy trước vì tạo đối tượng nền. Thời gian commit không phải tiêu chí dependency.

Root changelog cần thể hiện thứ tự thực thi một cách rõ ràng. Không dựa vào thứ tự merge pull request để ngầm tạo thứ tự database.

## 5. Tổ chức root changelog để hợp nhất nhánh

Với thay đổi quan trọng, dùng include tường minh giúp reviewer nhìn thấy thứ tự:

~~~yaml
databaseChangeLog:
  - include:
      file: db/changelog/00-foundation/create-customers.yaml
      relativeToChangelogFile: false

  - include:
      file: db/changelog/00-foundation/create-orders.yaml
      relativeToChangelogFile: false

  - include:
      file: db/changelog/10-orders/add-delivery-status.yaml
      relativeToChangelogFile: false

  - include:
      file: db/changelog/20-orders/backfill-delivery-status.yaml
      relativeToChangelogFile: false

  - include:
      file: db/changelog/30-orders/add-status-constraint.yaml
      relativeToChangelogFile: false
~~~

Đường dẫn minh họa cần khớp resource root và cấu trúc artifact thực tế. Nếu dùng relativeToChangelogFile, xác minh cách resolve tương ứng với vị trí file.

### 5.1. Một file changelog theo feature

Có thể tổ chức mỗi feature trong file riêng:

~~~text
db/changelog/
  db.changelog-master.yaml
  00-foundation/
    create-customers.yaml
    create-orders.yaml
  10-orders/
    add-delivery-status.yaml
    backfill-delivery-status.yaml
    add-status-constraint.yaml
  20-customer/
    create-customer-index.yaml
~~~

Cách này giảm xung đột khi nhiều nhánh thêm file khác nhau. Root changelog vẫn cần được hợp nhất và review để xác định thứ tự.

### 5.2. includeAll và thứ tự file

includeAll tiện khi có nhiều file trong một thư mục, nhưng thứ tự resolve có thể phụ thuộc tên/resource accessor và hành vi của phiên bản Liquibase. Nếu thứ tự là dependency quan trọng, nên dùng include tường minh hoặc quy ước tên có thứ tự rõ ràng, sau đó kiểm tra bằng SQL preview.

Không đặt tên file tùy tiện rồi giả định hệ thống file sẽ trả về cùng thứ tự trên mọi máy. Cần kiểm chứng thứ tự thực tế trong artifact chạy CI và production.

### 5.3. Tránh include cùng một changelog nhiều lần

Một file được include lặp hoặc được nạp qua nhiều nhánh của cây changelog có thể gây hành vi khó hiểu, lỗi duplicate hoặc làm reviewer không biết nguồn nào chịu trách nhiệm. Giữ một root canonical và một đường include rõ ràng cho mỗi file.

## 6. Tình huống thực hành: nhánh B phụ thuộc nhánh A

Giả sử nhánh A thêm cột delivery_status. Nhánh B thêm CHECK constraint dựa trên cột đó.

**Nhánh A:**

~~~yaml
databaseChangeLog:
  - changeSet:
      id: ORD-1842-001-add-delivery-status
      author: team-orders
      changes:
        - addColumn:
            schemaName: app
            tableName: orders
            columns:
              - column:
                  name: delivery_status
                  type: VARCHAR(20)
~~~

**Nhánh B:**

~~~yaml
databaseChangeLog:
  - changeSet:
      id: ORD-1850-001-add-delivery-status-check
      author: team-orders
      changes:
        - sql:
            sql: |
              ALTER TABLE app.orders
              ADD CONSTRAINT ck_orders_delivery_status
              CHECK (delivery_status IN ('PENDING', 'SHIPPED', 'CANCELLED'));
~~~

Nếu root changelog include B trước A, database mới sẽ báo cột delivery_status không tồn tại. Nếu include A trước B, dependency cấu trúc được đáp ứng.

Tuy nhiên, constraint vẫn có thể thất bại nếu dữ liệu hiện tại chứa giá trị khác. Vì vậy, thứ tự cần bao gồm cả backfill/chuẩn hóa dữ liệu trước bước enforce.

### 6.1. Root changelog sau merge

~~~yaml
databaseChangeLog:
  - include:
      file: db/changelog/orders/ORD-1842-add-delivery-status.yaml
  - include:
      file: db/changelog/orders/ORD-1842-backfill-delivery-status.yaml
  - include:
      file: db/changelog/orders/ORD-1850-add-delivery-status-check.yaml
~~~

Tên file chỉ minh họa. Không sửa changeset đã chạy để đổi id hoặc nội dung. Nếu cần thêm bước backfill, tạo changeset/job mới và đặt vào đúng vị trí dependency của release.

## 7. Tình huống hai nhánh cùng tạo một cột

Giả sử:

- Nhánh A thêm delivery_status VARCHAR(20).
- Nhánh B thêm delivery_status VARCHAR(30) và default PENDING.

Hai changeset có id khác nhau nhưng cùng tạo một cột. Khi hợp nhất, database trống có thể chạy A rồi thất bại ở B vì cột đã tồn tại.

### 7.1. Khi chưa nhánh nào được deploy

Có thể hợp nhất thiết kế thành một changeset canonical trước khi phát hành. Chọn kiểu dữ liệu, default, nullability và semantics đúng với yêu cầu. Loại bỏ thay đổi trùng chưa triển khai và cập nhật root changelog.

Sau khi changeset đã được deploy ở bất kỳ môi trường có history cần bảo tồn, không tự ý sửa/xóa nó. Chuyển sang quy trình hội tụ trạng thái.

### 7.2. Khi một nhánh đã được deploy

Ví dụ nhánh A đã chạy ở staging, nhánh B chưa chạy. Kiểm tra schema/history staging, sau đó thiết kế changeset mới để đưa schema tới trạng thái cuối. Nếu cần tăng độ dài cột hoặc thêm default, dùng ALTER tương ứng thay vì chạy lại addColumn.

Giữ nguyên changeset A đã phát hành. Đảm bảo artifact release chứa lịch sử A và changeset mới theo thứ tự.

### 7.3. Khi hai nhánh đã deploy lên hai môi trường khác nhau

Đây là tình huống phức tạp hơn vì hai database có thể có history và schema khác nhau. Cần:

1. Thu thập DATABASECHANGELOG của từng môi trường.
2. So sánh định nghĩa cột, default, constraint và dữ liệu.
3. Xác định changeset nào đã chạy ở từng nơi.
4. Xác định trạng thái đích canonical.
5. Thiết kế changeset hội tụ có precondition kiểm tra trạng thái.
6. Kiểm thử trên bản sao của cả hai trạng thái.
7. Triển khai theo thứ tự và xác minh history từng môi trường.

Không dùng MARK_RAN hàng loạt để che khác biệt. Chỉ dùng khi hậu điều kiện đã tồn tại đúng và được kiểm chứng; nếu định nghĩa khác, cần ALTER/repair thực sự.

## 8. Tình huống hai nhánh tạo cùng changeset identity

Nếu hai nhánh cùng dùng id, author và logical file path nhưng khác nội dung, Liquibase có thể nhận diện đó là cùng một changeset đã bị sửa.

Ví dụ:

~~~yaml
# Branch A
- changeSet:
    id: ORD-1900-add-index
    author: team-orders
    changes:
      - createIndex:
          schemaName: app
          tableName: orders
          indexName: idx_orders_created
          columns:
            - column:
                name: created_at
~~~

~~~yaml
# Branch B
- changeSet:
    id: ORD-1900-add-index
    author: team-orders
    changes:
      - createIndex:
          schemaName: app
          tableName: orders
          indexName: idx_orders_customer
          columns:
            - column:
                name: customer_id
~~~

Nếu hai nội dung ở cùng logical path, đây không phải hai changeset độc lập an toàn. Một môi trường có thể đã lưu checksum của A; artifact mới mang B sẽ mismatch.

Cách xử lý:

- Xác định changeset đã được deploy ở đâu.
- Nếu chưa deploy ở đâu, thống nhất nội dung và định danh trước release.
- Nếu đã deploy, giữ nguyên nội dung đã phát hành và tạo changeset mới cho index còn thiếu.
- Không sửa checksum database để biến B thành A.
- Test upgrade path trên database có history cũ.

## 9. Phát hiện xung đột bằng kiểm tra schema

Git diff cho biết file nào thay đổi nhưng không biết hai changeset có tạo cùng một đối tượng. Cần kết hợp review changelog với kiểm tra schema.

Các câu hỏi trong pull request:

- Hai changeset có cùng table/column/index/constraint name không?
- Có đổi kiểu hoặc default của cùng cột không?
- Có thay đổi cùng một view/function/trigger không?
- Changeset mới có tham chiếu đối tượng được tạo ở nhánh khác không?
- Có dữ liệu cũ vi phạm constraint không?
- Có hai changeset cùng seed một business key không?
- Root changelog có include đúng thứ tự không?
- Context/label/DBMS filter có loại bỏ dependency không?

Có thể dùng snapshot/diff giữa database baseline và database sau migration để phát hiện schema drift. Diff không tự hiểu ý nghĩa nghiệp vụ, nên reviewer vẫn phải xác nhận thay đổi dự kiến.

## 10. Precondition khi hợp nhất nhánh

Precondition có thể kiểm tra đối tượng tồn tại hoặc dữ liệu đạt điều kiện trước khi chạy. Ví dụ kiểm tra cột trước khi tạo constraint:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: ORD-1850-002-verify-status-column
      author: team-orders
      preConditions:
        - onFail: HALT
        - columnExists:
            schemaName: app
            tableName: orders
            columnName: delivery_status
      changes:
        - sql:
            sql: |
              ALTER TABLE app.orders
              ADD CONSTRAINT ck_orders_delivery_status
              CHECK (delivery_status IN ('PENDING', 'SHIPPED', 'CANCELLED'));
~~~

Precondition xác nhận cột tồn tại, nhưng chưa chứng minh kiểu dữ liệu, default hoặc dữ liệu đều đúng. Với yêu cầu quan trọng, cần kiểm tra thêm metadata và invariant.

### 10.1. MARK_RAN không phải công cụ merge conflict

MARK_RAN có thể ghi nhận changeset như đã chạy dù change không được thực thi. Nếu dùng để bỏ qua changeset trùng, phải chứng minh đối tượng hiện tại tương đương chính xác với hậu điều kiện mong muốn.

Không dùng MARK_RAN chỉ vì cột đã tồn tại. Cột có thể sai kiểu, sai độ dài, sai default hoặc khác semantics. Precondition yếu cộng MARK_RAN dễ tạo history xanh nhưng schema sai.

### 10.2. onFail và onError

- onFail: điều kiện precondition được đánh giá nhưng không thỏa.
- onError: có lỗi trong lúc đánh giá precondition.

Với dependency bắt buộc, HALT thường phù hợp để dừng khi giả định sai. WARN hoặc MARK_RAN cần lý do rõ ràng và kiểm thử trên các trạng thái database đã biết.

## 11. Context, label và DBMS filter trong dependency graph

Một changeset tạo cột có thể chỉ chạy với context dev, trong khi changeset tạo constraint chạy ở prod. Khi đó dependency không tồn tại ở môi trường đích.

Sau merge, kiểm tra:

- Context truyền vào Liquibase CLI hoặc Spring Boot.
- Label expression.
- DBMS filter.
- Property substitution.
- Profile môi trường.
- Root changelog thực tế.
- Changeset nào bị lọc khỏi execution plan.

Dependency graph phải được đánh giá theo từng cấu hình môi trường. Hai changeset cùng nằm trong root không có nghĩa chúng luôn được chạy cùng nhau.

Không xóa filter để làm migration chạy qua nếu filter bảo vệ dữ liệu hoặc môi trường khác. Sửa phạm vi chọn changeset có chủ đích.

## 12. Xử lý thay đổi đã deploy ở branch hoặc môi trường dùng chung

Trước khi merge branch có migration đã chạy, lập bảng trạng thái:

| Môi trường | Changeset A | Changeset B | Schema thực tế |
|---|---|---|---|
| Dev branch A | EXECUTED | Chưa chạy | Cột kiểu VARCHAR(20) |
| Dev branch B | Chưa chạy | EXECUTED | Cột kiểu VARCHAR(30), default PENDING |
| Staging | Chưa chạy | Chưa chạy | Baseline |
| Production | Chưa chạy | Chưa chạy | Baseline |

Đây là ví dụ về trạng thái phân kỳ. Không thể giả định một root changelog duy nhất sẽ chạy giống nhau trên mọi database nếu lịch sử đã khác.

Quy trình hội tụ:

1. Chốt schema đích được phê duyệt.
2. Xác định những thay đổi đã chạy và dữ liệu đã phát sinh.
3. Tạo migration bổ sung cho từng trạng thái cần hội tụ.
4. Dùng precondition có kiểm chứng để phân biệt trạng thái.
5. Kiểm thử trên bản sao từng trạng thái.
6. Chọn rollout theo môi trường và lưu bằng chứng.
7. Sau hội tụ, các release sau dùng chung artifact và root changelog.

Nếu môi trường branch chỉ là database ephemeral, có thể tạo lại từ root canonical sau merge. Nếu đó là staging/production hoặc database có dữ liệu cần giữ, không reset tùy tiện.

## 13. Liquibase lock và chạy migration đồng thời

DATABASECHANGELOGLOCK điều phối các Liquibase runner dùng cùng bộ metadata trong một database. Nó giúp tránh hai runner cùng update một target tại cùng thời điểm.

Tuy nhiên, lock không giải quyết:

- Git merge conflict.
- Hai changeset tạo cùng cột với id khác nhau.
- Dependency sai thứ tự.
- Hai database có history khác nhau.
- Một ứng dụng ghi dữ liệu không tương thích trong lúc migration.
- Hai Liquibase runner dùng metadata table khác nhau nhưng cùng sửa một schema.

Vì vậy, cần kiểm soát concurrency ở CI/CD và release orchestration. Một lock database không thay thế migration plan.

### 13.1. Tránh nhiều branch cùng deploy một database

Nếu hai branch cùng chạy Liquibase lên một database tích hợp, runner thứ hai có thể chờ lock rồi chạy trên schema mà branch đầu vừa thay đổi. Changeset của nó có thể không còn đúng giả định ban đầu.

Tốt nhất dùng database riêng cho branch hoặc chỉ cho một release candidate được chỉ định deploy vào môi trường tích hợp.

## 14. Xử lý merge conflict trong Git theo quy trình

Khi root changelog hoặc file YAML có conflict:

1. Dừng merge tại trạng thái conflict.
2. Đọc cả hai phiên bản và hiểu mục tiêu changeset.
3. So sánh dependency và object bị tác động.
4. Resolve YAML/XML/JSON để cú pháp hợp lệ.
5. Đặt include theo dependency graph.
6. Kiểm tra không mất changeset của nhánh nào.
7. Chạy validate và SQL preview.
8. Chạy update trên database baseline mới.
9. Chạy upgrade path từ release cũ.
10. Review diff cuối cùng trước khi commit merge.

Không chỉ xóa conflict marker rồi chọn một phía. Điều đó có thể làm mất migration đã được nhánh kia phát triển.

### 14.1. Không đổi thứ tự đã triển khai một cách tùy tiện

Liquibase chỉ thực thi changeset pending theo changelog/config hiện tại; changeset đã ghi history không tự chạy lại chỉ vì include order thay đổi. Tuy nhiên, đổi thứ tự các changeset pending có thể làm thay đổi execution sequence của database mới hoặc môi trường chưa chạy chúng.

Vì vậy, sau khi một chuỗi migration đã được phát hành, hãy xem thứ tự là một phần của release contract. Thêm changeset mới ở cuối hoặc dùng cấu trúc include được thiết kế rõ; tránh sắp xếp lại lịch sử đã phát hành nếu không có kế hoạch migration cụ thể.

## 15. Kiểm thử sau merge

Một lần merge chỉ hoàn tất khi đã kiểm tra được cả database mới và database nâng cấp.

### 15.1. Validate và SQL preview

Chạy bằng đúng Liquibase version, root changelog, context, label, DBMS và properties dự kiến:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
~~~

Review SQL preview để xác nhận:

- Changeset được chọn đúng.
- Thứ tự đúng với dependency.
- Không tạo đối tượng trùng.
- Không chạy changeset của môi trường khác.
- SQL tương thích DBMS.
- Không có câu lệnh phá hủy ngoài dự kiến.

### 15.2. Fresh install

Tạo database mới, chạy toàn bộ root changelog đã merge. Xác minh schema cuối, constraint, index, dữ liệu seed và DATABASECHANGELOG.

Fresh install thường phát hiện dependency bị thiếu hoặc include order sai.

### 15.3. Upgrade path

Khởi tạo database từ release baseline gần nhất được hỗ trợ, nạp dữ liệu đại diện và chạy artifact sau merge. Xác minh changeset cũ không bị thay đổi checksum và changeset mới chạy đúng thứ tự.

Upgrade path phát hiện xung đột lịch sử, dữ liệu cũ và trạng thái đã triển khai mà fresh install không thể phát hiện.

### 15.4. Kiểm thử các trạng thái branch đã từng deploy

Nếu branch A hoặc B từng chạy trên database có history cần giữ, tạo bản sao từ từng trạng thái và chạy artifact hợp nhất. Không chỉ test một database trống.

## 16. Kiểm tra rollback sau merge

Sau khi hợp nhất, rollback order phải được review theo thứ tự ngược dependency. Nếu changeset B tạo constraint dựa trên cột do A tạo, rollback thường cần gỡ constraint trước rồi mới có thể drop cột.

Nhưng rollback không tự động an toàn nếu ứng dụng đã ghi dữ liệu vào cột mới hoặc có consumer mới. Kiểm thử:

- Rollback SQL preview.
- Thứ tự drop dependency.
- Dữ liệu có bị mất không.
- Ứng dụng cũ có chạy sau rollback không.
- Các môi trường có cùng lịch sử không.
- Forward-fix có an toàn hơn không.

Không rollback một target chỉ để làm cho DATABASECHANGELOG giống target khác nếu dữ liệu và schema đang phục vụ nghiệp vụ.

## 17. Quy trình CI/CD cho nhánh và release

Một pipeline có thể tổ chức:

~~~text
Feature branch
    |
    v
Review changeset identity + object impact
    |
    v
Build changelog artifact
    |
    v
Validate + dependency/order checks
    |
    v
Fresh database migration test
    |
    v
Upgrade baseline test
    |
    v
Application compatibility test
    |
    v
Merge to release branch
    |
    v
Resolve root changelog order
    |
    v
Run merged artifact against branch-state fixtures
    |
    v
SQL preview + approval
    |
    v
Promote same artifact through environments
    |
    v
Post-check history/schema/data
~~~

### 17.1. Artifact bất biến

Sau khi merge và test, tạo artifact có version/digest. Staging và production dùng cùng artifact; không build lại hoặc thay changelog theo môi trường sau khi đã phê duyệt.

Context/label/credentials có thể khác theo environment nhưng phải được quản lý rõ. Lưu root changelog, Liquibase version, JDBC driver, digest và execution result.

### 17.2. Pull request checklist

Mỗi pull request có migration nên nêu:

- Changeset id/author/file path.
- Đối tượng database bị tác động.
- Dependency với changeset khác.
- Dữ liệu hiện tại có thể vi phạm không.
- Context/label/DBMS filter.
- Rollback hoặc lý do không thể rollback.
- Ảnh hưởng tới app cũ/mới.
- Kết quả validate, SQL preview, fresh install và upgrade test.
- Trạng thái deploy của branch nếu đã chạy migration.

## 18. Bài thực hành: mô phỏng hai nhánh cùng thay đổi orders

**Mục tiêu:** tạo hai nhánh feature độc lập, mô phỏng dependency và xung đột schema, hợp nhất root changelog rồi xác minh thứ tự. Dùng database lab riêng có thể tạo lại.

### Bước 1. Tạo baseline

Tạo database lab và chạy changelog nền có bảng customers và orders:

~~~sql
CREATE SCHEMA app;

CREATE TABLE app.customers (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);

CREATE TABLE app.orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT,
    status VARCHAR(20) NOT NULL
);
~~~

Ghi lại DATABASECHANGELOG baseline và artifact version.

### Bước 2. Tạo nhánh A

Nhánh A thêm cột delivery_status nullable:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: LAB-210-add-delivery-status
      author: lab-team
      changes:
        - addColumn:
            schemaName: app
            tableName: orders
            columns:
              - column:
                  name: delivery_status
                  type: VARCHAR(20)
~~~

Chạy trên database riêng A. Kiểm tra cột tồn tại và app cũ vẫn chạy.

### Bước 3. Tạo nhánh B

Nhánh B thêm CHECK constraint giả định cột đã tồn tại:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: LAB-211-add-delivery-status-check
      author: lab-team
      changes:
        - sql:
            sql: |
              ALTER TABLE app.orders
              ADD CONSTRAINT ck_orders_delivery_status
              CHECK (delivery_status IN ('PENDING', 'SHIPPED', 'CANCELLED'));
~~~

Chạy trên database riêng B khi chưa có nhánh A. Quan sát lỗi dependency. Ghi changeset id và root cause; không sửa history bằng tay.

### Bước 4. Hợp nhất root changelog

Tạo root canonical include nhánh A trước nhánh B. Nếu có backfill, đặt nó giữa addColumn và add constraint. Chạy validate và update-sql để review execution order.

### Bước 5. Chạy fresh install sau merge

Tạo database mới và chạy root hợp nhất. Xác minh bảng, cột, dữ liệu và CHECK constraint. Thử insert một giá trị hợp lệ và một giá trị không hợp lệ.

### Bước 6. Tạo xung đột cùng đối tượng

Trong một nhánh lab khác, tạo changeset thêm delivery_status với kiểu VARCHAR(30) hoặc default khác. Merge file đó vào root để quan sát lỗi duplicate object trên database mới.

Không dùng MARK_RAN để che lỗi. Xác định định nghĩa canonical, loại bỏ thay đổi trùng nếu chưa phát hành; nếu đã phát hành ở môi trường có history cần giữ, thiết kế changeset hội tụ mới.

### Bước 7. Kiểm tra identity conflict

Tạo hai bản changelog dùng cùng id, author và logical path nhưng nội dung khác. Chạy một bản trên database lab, sau đó thử artifact chứa bản còn lại. Quan sát checksum mismatch và ghi lại cách khôi phục nội dung đã phát hành hoặc tạo changeset mới.

### Bước 8. Test upgrade path và rollback

Khởi tạo một database từ baseline, chạy artifact hợp nhất. Thực hiện rollback trên bản sao, kiểm tra thứ tự gỡ constraint/cột và dữ liệu. Test app cũ trên schema sau rollback.

### Bước 9. Ghi bằng chứng

Lưu trong kết quả CI/test:

- Root changelog đã merge.
- Dependency order.
- Artifact digest.
- Liquibase/DBMS version.
- DATABASECHANGELOG trước/sau.
- SQL preview.
- Kết quả fresh install và upgrade path.
- Lỗi có chủ đích ở nhánh B.
- Kết quả resolve duplicate object và checksum conflict.
- Rollback result và compatibility test.

## 19. Các lỗi thường gặp khi hợp nhất migration

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| YAML parse error sau merge | Conflict marker hoặc indent sai | Resolve file, validate lại |
| Column already exists | Hai nhánh tạo cùng cột | So định nghĩa và trạng thái deploy, thiết kế hội tụ |
| Checksum mismatch | Cùng changeset identity nhưng nội dung khác | Khôi phục bản đã phát hành hoặc changeset mới |
| Relation/column does not exist | Include order hoặc dependency sai | Sắp xếp theo dependency graph |
| FK validation fail | Dữ liệu cũ có orphan | Sửa dữ liệu và validate có kiểm soát |
| Changeset bị bỏ qua | Context/label/DBMS filter không khớp | Kiểm tra execution scope |
| Changeset chạy hai lần | File được include lặp hoặc path/identity thay đổi | Kiểm tra cây include và logical path |
| Index already exists | Hai nhánh tạo index tương đương | So định nghĩa, kiểm tra history và catalog |
| Một môi trường thành công, nơi khác thất bại | History/schema đã phân kỳ | Lập trạng thái từng target và migration hội tụ |
| Liquibase chờ lock | Runner khác đang update cùng metadata | Điều phối runner; xác minh lock owner |
| Rollback thất bại | Dependency hoặc dữ liệu mới còn tồn tại | Review thứ tự rollback và chọn forward-fix nếu cần |

## 20. Checklist nghiệm thu merge migration

- [ ] Đã phân biệt Git conflict, changeset identity conflict và schema semantic conflict.
- [ ] Đã xác định mọi nhánh từng deploy migration ở đâu.
- [ ] Changeset id/author/path ổn định và không trùng ngoài chủ đích.
- [ ] Không sửa nội dung changeset đã triển khai.
- [ ] Root changelog có thứ tự include theo dependency graph.
- [ ] includeAll không làm thứ tự phụ thuộc trở nên mơ hồ.
- [ ] Không include lặp cùng file ngoài chủ đích.
- [ ] Context/label/DBMS filter được kiểm tra theo từng môi trường.
- [ ] Precondition không che giấu đối tượng sai bằng MARK_RAN.
- [ ] Đã kiểm tra schema và dữ liệu trước khi enforce constraint.
- [ ] Fresh install trên database mới đạt.
- [ ] Upgrade path từ baseline hỗ trợ đạt.
- [ ] Đã test trên bản sao của từng trạng thái branch đã deploy.
- [ ] SQL preview đã được review.
- [ ] Checksum và DATABASECHANGELOG không có sai lệch chưa giải thích.
- [ ] Rollback/forward-fix được đánh giá theo dữ liệu và compatibility.
- [ ] Application cũ/mới hoạt động trên schema chuyển tiếp.
- [ ] CI/CD dùng cùng artifact đã kiểm thử và lưu digest.
- [ ] Không có Liquibase runner chạy song song ngoài kế hoạch.
- [ ] Hậu kiểm schema, data, constraint, index và history đạt.

## 21. Kết luận

Mô phỏng xung đột nhánh giúp phát hiện rằng migration có thể xung đột ở ba lớp: nội dung Git, định danh/checksum của changeset và ngữ nghĩa schema. Hai changeset khác id vẫn có thể tạo cùng cột; hai nhánh cùng id/author/path nhưng nội dung khác có thể làm sai lệch lịch sử; một changeset hợp lệ riêng lẻ vẫn có thể thất bại nếu root changelog chạy sai thứ tự dependency.

Hãy mô hình hóa dependency thành đồ thị, tổ chức root changelog rõ ràng, giữ bất biến changeset đã triển khai và kiểm tra trạng thái từng môi trường trước khi hợp nhất. Fresh install, upgrade path, branch-state fixture, SQL preview, rollback test và application compatibility test cần chạy trên artifact đã merge. Khi các nhánh đã tạo ra history khác nhau, cần migration hội tụ được kiểm thử trên từng trạng thái thay vì xóa history hoặc dùng MARK_RAN để che khác biệt. Cách làm này giúp release Liquibase có thứ tự xác định, có thể tái lập và dễ kiểm toán.
