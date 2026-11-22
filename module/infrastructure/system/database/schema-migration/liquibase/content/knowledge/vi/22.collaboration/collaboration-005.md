# Kiểm soát thứ tự thay đổi có phụ thuộc giữa các nhánh

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chương **Cộng tác**, nhiều người thường phát triển migration song song trên các Git branch khác nhau. Một nhánh có thể tạo bảng **customer**, nhánh khác tạo **sales_order** và khóa ngoại tham chiếu customer; nhánh thứ ba bổ sung dữ liệu hoặc view dựa trên cả hai bảng. Mỗi nhánh có thể chạy độc lập trong môi trường riêng, nhưng khi hợp nhất vào changelog chung, **thứ tự triển khai phải tôn trọng các phụ thuộc**.

Liquibase quản lý thay đổi schema và dữ liệu bằng **changelog**, **changeset**, **precondition**, **checksum** và lịch sử trong **DATABASECHANGELOG**. Công cụ thực thi các changeset theo thứ tự changelog đã khai báo, kết hợp với lịch sử và điều kiện chạy. Liquibase không tự đọc quan hệ giữa Git branches để suy ra rằng nhánh B phải chờ nhánh A. Nhóm cần thiết kế một thứ tự tích hợp có chủ đích, giữ định danh changeset ổn định và kiểm chứng kết quả sau merge.

Bài học này giúp xác định phụ thuộc giữa các thay đổi, tổ chức changelog nhiều nhánh, giải quyết merge/rebase mà không phá lịch sử, điều phối nhiều người cùng triển khai, và xây dựng CI/CD để phát hiện sớm lỗi thứ tự. Đây là phần thực hành quan trọng trong mục tiêu của module: quản lý thay đổi schema và dữ liệu có kiểm chứng, rollback được, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

## 1. Vì sao thay đổi từ nhiều nhánh có thể xung đột?

Giả sử ba nhóm phát triển đồng thời:

- **Nhánh A — customer-domain**: tạo bảng **customer** và cột **id**, **email**.
- **Nhánh B — order-domain**: tạo bảng **sales_order**, cột **customer_id**, rồi thêm foreign key tới **customer.id**.
- **Nhánh C — customer-reporting**: tạo view tổng hợp số đơn theo khách hàng, sử dụng cả **customer** và **sales_order**.

Nếu mỗi nhóm chỉ nhìn vào nhánh của mình, changelog có thể hợp lệ về cú pháp. Nhưng khi hợp nhất, nếu nhánh C hoặc B được include trước khi các đối tượng nền được tạo, migration sẽ lỗi:

~~~text
customer-domain:
    create table customer
          |
          +-------------------------+
                                    |
order-domain:                       |
    create table sales_order        |
          |                         |
    add FK sales_order.customer_id -+
          |
          +------------------------------+
                                         |
customer-reporting:                     |
    create view v_customer_order_count <-+
~~~

Đây là một **đồ thị phụ thuộc**. Các thay đổi tạo object nền phải được triển khai trước thay đổi tham chiếu chúng.

Những lỗi thường gặp khi cộng tác:

- Nhánh B tạo foreign key nhưng chưa có bảng customer trên database thử nghiệm.
- Nhánh C tạo view dựa vào cột mà nhánh A chưa thêm.
- Hai nhánh cùng thêm một cột hoặc constraint với tên khác nhau nhưng ý nghĩa trùng lặp.
- Hai changeset có cùng định danh trong cùng changelog path.
- File changelog được include theo thứ tự không phù hợp sau khi merge.
- Một nhánh đã triển khai lên database dùng chung, nhưng nhánh khác chưa chứa changeset nền.
- Nhóm sửa changeset đã chạy để “khớp” với nhánh mới, làm thay đổi checksum và lịch sử.

Giải pháp bắt đầu từ việc mô tả **phụ thuộc giữa thay đổi**, sau đó tổ chức thứ tự include và lịch phát hành để mọi môi trường chạy cùng một chuỗi hợp lệ.

## 2. Phân biệt phụ thuộc Git branch và phụ thuộc database

Hai loại phụ thuộc này có liên quan nhưng không giống nhau:

| Loại phụ thuộc | Ví dụ | Cách kiểm soát |
|---|---|---|
| **Git branch dependency** | Nhánh order cần code hoặc migration của nhánh customer | Branch protection, merge order, pull request dependency |
| **Changelog dependency** | Changeset thêm FK cần bảng và cột đã tồn tại | Thứ tự include/changeset, precondition, integration test |
| **Schema dependency** | View cần hai bảng và cột nguồn | Đồ thị object, thứ tự tạo/gỡ |
| **Data dependency** | Backfill cần cột mới và dữ liệu tham chiếu đã có | Thứ tự migration, job completion gate, kiểm tra dữ liệu |
| **Application dependency** | Bản app mới ghi cột mà migration phải tạo trước | Triển khai expand trước, rollout app theo compatibility |
| **Release dependency** | Contract NOT NULL chỉ được chạy sau backfill | Pipeline gate, artifact và trạng thái job được xác minh |

Một Git branch có thể được merge nhưng migration của nó chưa được phép triển khai. Ngược lại, changeset có thể đã được triển khai ở một database dùng chung dù code branch chứa nó chưa được merge vào main. Vì thế cần quản lý riêng **trạng thái source control**, **trạng thái changelog** và **trạng thái database**.

Liquibase không có một bộ lập lịch tự động dựa trên quan hệ giữa các Git branch. Nó không tự biết “feature/order phải đợi feature/customer”. Điều đó phải được thể hiện trong changelog chung và quy trình tích hợp.

## 3. Biểu diễn dependency bằng đồ thị có hướng

Có thể mô tả mỗi changeset hoặc nhóm changeset là một node. Nếu B cần A hoàn tất trước, vẽ cạnh:

~~~text
A: create customer
        |
        v
B: create sales_order
        |
        v
C: add FK sales_order -> customer
        |
        v
D: create reporting view
~~~

Trong thực tế, B và một số thay đổi khác có thể chạy song song nếu không phụ thuộc nhau:

~~~text
                +--> B: create sales_order -----+
A: create base -|                               +--> D: create view
                +--> C: create customer_profile-+
~~~

Thứ tự triển khai hợp lệ là một **topological ordering** của đồ thị: mỗi node chỉ chạy sau tất cả node tiền nhiệm của nó. Có thể có nhiều thứ tự hợp lệ nếu các nhánh độc lập; nhưng với những thay đổi có phụ thuộc, không được đảo thứ tự.

### 3.1. Xác định node ở mức nào?

Có thể biểu diễn dependency ở các mức:

- **Object**: bảng, cột, index, constraint, view, sequence.
- **Changeset**: một đơn vị thay đổi Liquibase.
- **Migration file**: nhóm changeset cùng miền nghiệp vụ.
- **Release**: tập thay đổi được phê duyệt cùng đợt.
- **Application version**: phiên bản code cần schema trước hoặc sau một bước.

Đừng gộp mọi thứ thành một node “feature branch”. Một nhánh có thể chứa nhiều changeset, trong đó một số độc lập, một số phụ thuộc. Tách rõ sẽ giúp xác định điểm merge và rollback chính xác hơn.

### 3.2. Phân biệt dependency kỹ thuật và dependency nghiệp vụ

Ví dụ, **sales_order.customer_id** có foreign key tới **customer.id** là dependency kỹ thuật rõ ràng. Nhưng việc backfill **customer.status** trước khi ứng dụng mới lọc theo trạng thái là dependency nghiệp vụ. Database có thể cho phép tạo view trước, nhưng dữ liệu chưa đủ để kết quả đúng.

Cần ghi lại cả hai loại. Precondition kiểm tra được một số điều kiện database; nó không thay thế kế hoạch phối hợp nghiệp vụ hoặc rollout ứng dụng.

## 4. Tổ chức changelog theo nhánh và theo miền nghiệp vụ

Một cấu trúc thư mục có thể giúp nhiều nhóm làm việc độc lập:

~~~text
db/changelog/
├── db.changelog-master.yaml
├── baseline/
│   └── db.changelog-baseline.yaml
├── features/
│   ├── customer/
│   │   └── customer-2026-001.yaml
│   ├── orders/
│   │   └── orders-2026-001.yaml
│   └── reporting/
│       └── reporting-2026-001.yaml
└── releases/
    └── release-2026-11.yaml
~~~

Mỗi nhánh có thể sở hữu một file changelog riêng, tránh nhiều người chỉnh cùng một file. Sau khi merge, **master changelog** quyết định thứ tự tích hợp:

~~~yaml
databaseChangeLog:
  - include:
      file: baseline/db.changelog-baseline.yaml
      relativeToChangelogFile: true

  - include:
      file: features/customer/customer-2026-001.yaml
      relativeToChangelogFile: true

  - include:
      file: features/orders/orders-2026-001.yaml
      relativeToChangelogFile: true

  - include:
      file: features/reporting/reporting-2026-001.yaml
      relativeToChangelogFile: true
~~~

Trong ví dụ, file customer được include trước orders và reporting vì các thay đổi sau phụ thuộc vào nó. Tuy nhiên, **include file không tự tạo dependency**: nó chỉ đưa changelog con vào chuỗi thực thi tại vị trí được khai báo. Nếu reporting cần bảng sales_order và cột customer.region, phải bảo đảm cả hai changeset nền nằm trước reporting.

Các file có thể chứa nhiều changeset; thứ tự bên trong mỗi file cũng phải rõ ràng. Không nên dựa vào tên folder hoặc thứ tự Git merge để suy ra thứ tự thực thi.

### 4.1. Dùng include tường minh khi thứ tự quan trọng

Với các dependency trọng yếu, **include tường minh** thường dễ review hơn vì thứ tự nằm ngay trong master changelog. Reviewer có thể nhìn thấy customer → orders → reporting.

Nếu dùng **includeAll**, Liquibase thường sắp xếp các file theo thứ tự tên/đường dẫn theo quy tắc của runtime. Khi đó có thể đặt prefix như:

~~~text
010-customer.yaml
020-orders.yaml
030-reporting.yaml
~~~

Nhưng cần lưu ý:

- Thứ tự tên file chỉ là cách tạo thứ tự ổn định, không phải mô hình dependency tự động.
- Thêm file mới có tên đứng trước có thể làm thay đổi chuỗi thay đổi trong master.
- Quy tắc sắp xếp và cách include cần được xác nhận với phiên bản Liquibase đang dùng.
- File ngoài phạm vi hoặc file thử nghiệm trong thư mục includeAll có thể vô tình được đưa vào.
- Với migration rủi ro cao, include tường minh giúp phát hiện thay đổi thứ tự trong code review.

Không dùng tên thư mục **customer**, **orders** như bằng chứng rằng Liquibase sẽ chạy đúng thứ tự nghiệp vụ.

## 5. Ví dụ: hai nhánh độc lập tương đối nhưng có dependency

Giả sử nhóm chia công việc như sau:

**Nhánh feature/customer-schema:**

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "CUST-001-create-customer"
      author: "customer-team"
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: VARCHAR(320)
~~~

**Nhánh feature/order-schema:**

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "ORD-001-create-sales-order"
      author: "order-team"
      changes:
        - createTable:
            tableName: sales_order
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: customer_id
                  type: BIGINT
                  constraints:
                    nullable: false
              - column:
                  name: total_amount
                  type: DECIMAL(18,2)
                  constraints:
                    nullable: false

  - changeSet:
      id: "ORD-002-add-customer-foreign-key"
      author: "order-team"
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: customer
        - columnExists:
            tableName: customer
            columnName: id
      changes:
        - addForeignKeyConstraint:
            baseTableName: sales_order
            baseColumnNames: customer_id
            referencedTableName: customer
            referencedColumnNames: id
            constraintName: fk_sales_order_customer
~~~

Nhánh order tạo bảng riêng trước, rồi thêm foreign key trong changeset kế tiếp. Nhờ vậy, cấu trúc bảng order có thể được phát triển và thử nghiệm độc lập ở mức nhất định; bước FK chỉ hợp lệ khi bảng customer đã tồn tại.

Tuy nhiên, precondition **tableExists** và **columnExists** chỉ **kiểm tra điều kiện**. Nếu bảng customer chưa có, **onFail: HALT** dừng migration. Nó không tự tìm branch customer, không merge code, không chạy migration phụ thuộc và không đảm bảo schema của customer đúng toàn bộ hợp đồng.

### 5.1. Sau khi merge

Master changelog include customer trước order. Khi Liquibase chạy update:

1. Changeset CUST-001 tạo customer nếu chưa được ghi nhận và đủ điều kiện.
2. Changeset ORD-001 tạo sales_order.
3. Changeset ORD-002 thêm FK sau khi bảng và cột tham chiếu đã có.
4. Những changeset tiếp theo có thể tạo view dựa trên cả hai bảng.

Nếu include order trước customer, precondition sẽ HALT ở ORD-002. Đó là lỗi thứ tự có thể phát hiện sớm, nhưng pipeline vẫn phải sửa master changelog hoặc dependency; không dùng MARK_RAN để bỏ qua FK.

## 6. ID, author và filename: tránh va chạm giữa nhánh

Liquibase nhận diện một changeset thông qua tổ hợp **id, author và đường dẫn changelog** (có thể được kiểm soát bằng **logicalFilePath**). Khi nhiều nhánh phát triển đồng thời, nhóm cần quy ước để tránh định danh mơ hồ.

Ví dụ quy ước:

~~~text
<DOMAIN>-<SEQUENCE>-<ACTION>

CUST-001-create-customer
ORD-001-create-sales-order
RPT-001-create-customer-order-view
~~~

Hoặc dùng prefix theo ticket/feature:

~~~text
CRM-482-add-customer-region
ORD-731-add-order-customer-fk
RPT-205-create-order-summary
~~~

Điều cần tránh:

- Hai nhóm copy cùng một ID như **001-create-table** vào cùng một file và cùng author.
- Dùng lại ID/author/filepath cho hai thay đổi khác nhau.
- Đổi author hoặc di chuyển file sau khi changeset đã chạy mà không có kế hoạch logicalFilePath.
- Dùng timestamp ngắn có khả năng trùng trong nhóm nhiều người.
- Dựa vào thứ tự ID để suy ra thứ tự thực thi trong khi master include file theo cách khác.

ID duy nhất giúp nhận diện thay đổi, **không tự giải quyết dependency**. Một changeset tên CUST-001 vẫn có thể chạy sau ORD-002 nếu master changelog include sai thứ tự.

### 6.1. Filename là một phần quan trọng của lịch sử

Giả sử changeset CUST-001 đã chạy từ **features/customer/customer-2026-001.yaml**. Nếu sau đó nhóm đổi tên file thành **customer-schema.yaml**, Liquibase có thể xem filename khác là định danh khác nếu logical path không được bảo toàn. Khi đó update có thể cố chạy lại changeset.

Trước khi di chuyển changelog đã phát hành, cần đánh giá **logicalFilePath** theo khả năng của phiên bản Liquibase, thử trên database có lịch sử thật và giữ nguyên định danh logic. Không đổi đường dẫn chỉ để làm sạch tên file.

## 7. Merge và rebase: xử lý thay đổi changelog đã cùng phát triển

Khi hai nhánh sửa cùng master changelog, Git có thể báo conflict. Cách giải quyết không phải chỉ chọn một bên; cần xem **thứ tự dependency**.

Quy trình review merge:

1. Liệt kê changeset mới từ từng nhánh.
2. Vẽ dependency giữa chúng ở mức object, dữ liệu và ứng dụng.
3. Xác định file nào cần include trước.
4. Giữ các changeset độc lập ở vị trí có thể chạy mà không phụ thuộc nhánh khác.
5. Chạy kiểm tra trên database mới và database nâng cấp từ trạng thái tích hợp trước đó.
6. Review thứ tự rollback theo thứ tự triển khai thực tế.
7. Commit master changelog sau khi các kiểm tra đạt.

Nếu dùng rebase để cập nhật feature branch, cần phân biệt **sắp xếp lại commit Git** với **sắp xếp lại changeset Liquibase**. Rebase có thể thay lịch sử commit nhưng không nên sửa ID/author/nội dung của changeset đã triển khai. Nếu feature branch đã được deploy lên một database dùng chung, thay đổi file hoặc ID sau rebase có thể làm lịch sử database không khớp.

### 7.1. Không squash changeset đã triển khai tùy tiện

Squash Git commits có thể hợp lệ nếu chỉ thay lịch sử source control trước khi phát hành. Nhưng gộp nhiều changeset đã chạy thành một changeset mới hoặc xóa file cũ có thể khiến Liquibase không nhận ra lịch sử hiện có.

Quy tắc an toàn:

- Trước khi bất kỳ database nào áp dụng: có thể chuẩn hóa changeset theo review và quy trình team.
- Sau khi đã áp dụng ở một môi trường dùng chung: giữ nguyên định danh/nội dung lịch sử.
- Khi cần thay đổi: thêm changeset mới, có ID mới và giải thích mục đích.
- Nếu lịch sử đã lệch: điều tra DATABASECHANGELOG và schema trước khi dùng các lệnh xử lý checksum hoặc đồng bộ.

## 8. DATABASECHANGELOG và DATABASECHANGELOGLOCK trong cộng tác

Liquibase dùng **DATABASECHANGELOG** để ghi nhận changeset đã chạy, và **DATABASECHANGELOGLOCK** để điều phối việc update trên cùng database.

Hai bảng này phục vụ những mục đích khác nhau:

| Bảng | Vai trò | Không giải quyết |
|---|---|---|
| **DATABASECHANGELOG** | Lưu ID, author, filename, checksum, thời gian và trạng thái thực thi | Không tự sắp xếp dependency giữa Git branches |
| **DATABASECHANGELOGLOCK** | Ngăn các tiến trình Liquibase cùng update một database tại cùng thời điểm theo cơ chế lock | Không khóa Git repository, không phối hợp release giữa các database khác nhau |

Nếu hai developer cùng chạy Liquibase update vào **cùng một database**, cơ chế lock giúp tuần tự hóa các tiến trình theo khả năng của Liquibase/DBMS. Nhưng nếu mỗi người dùng database riêng, không có lock chung giữa hai database. Và dù có lock, lệnh chạy sau vẫn có thể thất bại vì changelog của nó thiếu changeset nền.

**Lock không thay thế dependency management.** Nó giải quyết cạnh tranh đồng thời ở một database; thứ tự changeset vẫn phải được thiết kế trong changelog và release process.

### 8.1. Không tự xóa lock khi chưa điều tra

Nếu Liquibase báo lock đang được giữ, kiểm tra tiến trình migration, log và trạng thái database trước. Một tiến trình có thể đang chạy thật hoặc đã chết để lại lock. Chỉ dùng cơ chế **release-locks** sau khi xác nhận không còn tiến trình hợp lệ đang thực thi. Không sửa tay DATABASECHANGELOGLOCK chỉ để cho pipeline tiếp tục khi chưa biết nguyên nhân.

## 9. Database riêng cho từng branch và database dùng chung

Hai mô hình phát triển có ưu/nhược điểm khác nhau:

| Mô hình | Ưu điểm | Rủi ro/cách quản lý |
|---|---|---|
| **Database riêng theo feature branch** | Nhánh có thể thử migration độc lập; ít ảnh hưởng lẫn nhau | Cần seed/baseline nhất quán; phải kiểm thử lại sau merge trên chuỗi tích hợp |
| **Database dùng chung cho nhóm** | Dễ chia sẻ dữ liệu thử và kiểm tra tích hợp | Branch này có thể để lại changeset mà branch khác không biết; xung đột và lịch sử khó reset |
| **Database ephemeral trong CI** | Tái tạo từ artifact, kiểm tra thứ tự từ đầu | Tốn thời gian khởi tạo; cần dữ liệu fixture và DBMS đúng version |
| **Database tích hợp chỉ deploy từ main** | Có lịch sử thống nhất theo commit đã merge | Developer không được deploy feature chưa tích hợp tùy tiện |

Một thực hành tốt là dùng database riêng hoặc ephemeral cho nhánh phát triển; database dùng chung chỉ nhận **artifact tích hợp đã được kiểm soát**. Điều này giảm trường hợp database chứa changeset của branch A nhưng source branch B chưa có A.

Nếu buộc phải dùng một database chung cho nhiều nhánh, cần quy định rõ ai được phép chạy migration, branch nào là nguồn chuẩn, cách reset dữ liệu thử, và cách kiểm tra lịch sử trước mỗi lần update. Không để mọi developer tự chạy changelog tùy ý vào môi trường chung.

## 10. Context và label không tạo dependency

Liquibase có **context** và **label** để chọn tập changeset theo môi trường hoặc mục đích release. Nhưng chúng không thay thế thứ tự dependency.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "CUST-010-create-customer"
      author: "customer-team"
      contextFilter: "dev,test,prod"
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false

  - changeSet:
      id: "ORD-020-add-customer-fk"
      author: "order-team"
      labels: "release-2026-11"
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: customer
      changes:
        - addForeignKeyConstraint:
            baseTableName: sales_order
            baseColumnNames: customer_id
            referencedTableName: customer
            referencedColumnNames: id
            constraintName: fk_sales_order_customer
~~~

Nếu pipeline chọn label của ORD-020 nhưng không đưa changeset CUST-010 vào phạm vi phù hợp, FK có thể thất bại. Một changeset không có label/context cũng có thể đủ điều kiện theo quy tắc mặc định của Liquibase; không giả định filter hoạt động như một phép lọc nghiêm ngặt chỉ lấy những dòng có nhãn khớp.

Cần kiểm tra các filter thực tế ở runtime và bảo đảm **mọi dependency bắt buộc đều được phép chạy hoặc đã tồn tại**. Precondition HALT giúp phát hiện điều kiện thiếu; nó không tự bổ sung changeset bị filter loại.

## 11. Dependency của data migration và rollout ứng dụng

Phụ thuộc giữa nhánh không chỉ là CREATE TABLE/FK. Một feature có thể gồm nhiều bước:

~~~text
Nhánh A:
    add column customer.region (nullable)
            |
            v
Nhánh B:
    deploy application writes region
            |
            v
Nhánh C:
    backfill old customer rows
            |
            v
Nhánh D:
    verify no NULL
            |
            v
Nhánh E:
    add NOT NULL constraint
~~~

Trong chuỗi trên, B là thay đổi ứng dụng, C có thể là job backfill, D là điều kiện kiểm chứng, E là contract schema. Nếu tất cả changeset schema được merge vào một master changelog rồi chạy update một lần, Liquibase có thể tiếp tục đến E mà không tự chờ application rollout hay job backfill bên ngoài.

Cần thiết kế **release gate** thực sự:

1. Deploy schema expand.
2. Deploy writer tương thích.
3. Chạy backfill và lưu checkpoint.
4. Xác minh dữ liệu đạt invariant.
5. Chỉ sau đó mới cho phép changeset contract chạy.

Có thể dùng các release artifact/changelog scope riêng hoặc điều phối bằng pipeline/context/label có chủ đích. Điều quan trọng là filter phải được truyền tường minh và đã thử; thiếu filter có thể mở rộng phạm vi chạy hơn dự kiến.

## 12. Rollback khi nhiều nhánh đã tích hợp

Giả sử thứ tự triển khai:

~~~text
CUST-001: create customer
ORD-001: create sales_order
ORD-002: add FK sales_order -> customer
RPT-001: create reporting view
~~~

Rollback toàn bộ thường phải xét theo thứ tự ngược:

~~~text
RPT-001: drop view
ORD-002: drop FK
ORD-001: drop sales_order
CUST-001: drop customer
~~~

Nhưng nếu sales_order đã có dữ liệu thật, rollback dropTable có thể phá hủy dữ liệu. Thứ tự đúng chỉ giải quyết phụ thuộc kỹ thuật; không chứng minh rollback được phép về mặt nghiệp vụ.

Khi một nhánh gặp lỗi sau khi đã triển khai, hãy xác định:

- Changeset nào đã được ghi vào DATABASECHANGELOG?
- Changeset nào phụ thuộc vào object của nhánh đó?
- Có nhánh khác đã sử dụng object mới chưa?
- Có dữ liệu hoặc ứng dụng mới đã ghi dựa trên schema mới chưa?
- Có thể rollback riêng thay đổi lỗi hay cần roll-forward?
- Rollback có làm mất dữ liệu hoặc phá hợp đồng của nhánh khác không?

Không xóa file changelog của một nhánh rồi kỳ vọng Liquibase tự xóa các object đã tạo. Lịch sử database vẫn còn và schema cũng vẫn còn; cần migration rollback/sửa chữa được thiết kế rõ.

### 12.1. Ưu tiên sửa tiến khi thay đổi đã được dùng

Nếu feature A đã được triển khai và feature B đã tạo dữ liệu phụ thuộc, việc rollback A có thể gây thiệt hại lớn. Trong nhiều trường hợp, thêm changeset mới để sửa lỗi hoặc ngừng sử dụng feature là an toàn hơn xóa các object nền.

Không chỉnh sửa changeset A đã chạy để “đảo” nó. Hãy tạo changeset mới, có dependency và rollback phù hợp, đồng thời phối hợp với chủ sở hữu feature B.

## 13. Quy tắc thay đổi changelog sau khi merge

Một số nguyên tắc giữ lịch sử ổn định:

- **Không sửa nội dung changeset đã triển khai** chỉ để thay đổi thứ tự hoặc sửa SQL. Thêm changeset mới cho thay đổi tiếp theo.
- **Không đổi ID/author/filename** sau khi database đã ghi nhận changeset, trừ khi có kế hoạch quản lý định danh/logicalFilePath được kiểm thử.
- **Không dùng clear-checksums** để che checksum mismatch do sửa nội dung.
- **Không thêm changeset vào trước baseline hoặc marker release đã phát hành** nếu điều đó làm thay đổi ý nghĩa lịch sử.
- **Không dùng MARK_RAN** để bỏ qua dependency còn thiếu, trừ khi trạng thái đích đã tồn tại và được xác minh độc lập.
- **Không đổi thứ tự include tùy tiện** khi database đã chạy các changeset theo thứ tự cũ.
- **Không xóa changelog file đã được include** mà không xử lý lịch sử và đường dẫn logic.

Nếu cần tái cấu trúc changelog, thực hiện trước khi release hoặc lập kế hoạch chuyển đổi có kiểm thử trên database có lịch sử. Git merge sạch không có nghĩa Liquibase history sẽ sạch.

## 14. Quy trình cộng tác từ feature branch tới release

Một quy trình mẫu:

### Giai đoạn A — Phân tích dependency trước khi code

1. Chia yêu cầu thành thay đổi schema, dữ liệu và ứng dụng.
2. Vẽ dependency graph giữa các thay đổi.
3. Chọn changeset/file mà mỗi nhóm sở hữu.
4. Thống nhất ID, author, filename và naming convention.
5. Xác định DBMS/môi trường cần kiểm thử.

### Giai đoạn B — Phát triển độc lập

1. Mỗi nhánh tạo changelog riêng.
2. Dùng database branch riêng hoặc ephemeral để thử migration.
3. Viết precondition cho dependency quan trọng.
4. Kiểm tra update-sql, update và rollback trên DBMS mục tiêu.
5. Không deploy feature branch tùy tiện lên database tích hợp dùng chung.

### Giai đoạn C — Review và merge

1. Review nội dung changeset, schema/data impact và rollback.
2. Xác nhận ID/author/path không trùng.
3. Cập nhật master changelog theo topological order.
4. Giải quyết conflict bằng dependency graph, không chỉ theo thứ tự tên branch.
5. Chạy test tích hợp từ database sạch và database nâng cấp từ baseline.

### Giai đoạn D — Phát hành

1. Đóng gói commit/artifact cụ thể.
2. Chạy Liquibase validate và SQL preview.
3. Xác nhận context/label/dbms và precondition.
4. Chạy migration trên môi trường theo thứ tự release.
5. Theo dõi DATABASECHANGELOGLOCK và log migration.
6. Kiểm tra schema, dữ liệu và ứng dụng sau deploy.
7. Lưu bằng chứng release và các changeset đã áp dụng.

### Giai đoạn E — Xử lý lỗi

1. Dừng pipeline trước các changeset phụ thuộc nếu bước nền thất bại.
2. Kiểm tra lịch sử và trạng thái schema thực tế.
3. Quyết định rollback riêng, rollback release hay roll-forward.
4. Phối hợp chủ sở hữu các nhánh đang dùng object liên quan.
5. Tạo changeset sửa chữa mới khi cần, giữ nguyên lịch sử cũ.

## 15. CI/CD: kiểm thử thứ tự và dependency tự động

CI nên kiểm tra cả changelog lẫn trạng thái database.

| Kiểm tra | Mục tiêu | Lỗi có thể phát hiện |
|---|---|---|
| **Changelog validation** | Parse master và các file include | YAML/XML lỗi, include thiếu |
| **Changeset identity check** | Kiểm tra ID/author/path theo quy ước | Định danh trùng hoặc không ổn định |
| **Fresh database update** | Chạy toàn chuỗi từ database trống | Sai thứ tự tạo object, dependency thiếu |
| **Upgrade database test** | Chạy từ baseline/version cũ | Changeset giả định trạng thái không có thật |
| **SQL preview** | Review SQL sinh cho DBMS mục tiêu | Dialect không đúng, DDL ngoài ý muốn |
| **Dependency test** | Xác nhận FK/view/index và object nguồn tồn tại | Nhánh phụ thuộc được include quá sớm |
| **Rollback test** | Thử đảo phạm vi đã triển khai | Thứ tự rollback sai, dữ liệu không thể đảo |
| **Application integration test** | Chạy ứng dụng với schema sau migration | Code và schema không tương thích |

### 15.1. Test database sạch và database nâng cấp đều cần thiết

Database sạch chỉ kiểm tra đường tạo mới. Database nâng cấp kiểm tra lịch sử changeset, baseline, dữ liệu cũ và những dependency đã có. Hai đường có thể cho kết quả khác nhau.

Ví dụ, branch B có thể chạy được trên database sạch vì fixture đã tạo customer, nhưng thất bại trên database nâng cấp do production đang dùng schema cũ thiếu cột customer.id theo tên dự kiến. Cần test cả hai trạng thái.

### 15.2. CI tích hợp sau merge

Một pipeline có thể:

~~~text
PR branch A:
    validate changelog A
    update database riêng
    integration test

PR branch B:
    validate changelog B
    test với dependency fixture hoặc branch A đã tích hợp

After merge:
    build canonical master changelog
    provision clean DB
    run update
    verify schema and dependencies
    run rollback test
    run application integration tests
~~~

Đây là sơ đồ quy trình, không phải cú pháp của một nền tảng CI cụ thể. Với nhánh B phụ thuộc A, cần test tích hợp trên một artifact chứa A đã được merge hoặc trên fixture thể hiện đúng hợp đồng; không để test đơn nhánh tạo cảm giác branch B độc lập khi thực tế không phải vậy.

## 16. Spring Boot và nhiều instance ứng dụng

Spring Boot có thể tự chạy Liquibase khi ứng dụng khởi động nếu cấu hình bật. Trong môi trường có nhiều instance:

- Nhiều instance có thể cùng khởi động và cùng yêu cầu migration.
- DATABASECHANGELOGLOCK hỗ trợ điều phối việc update trên cùng database.
- Một instance có thể đang dùng schema cũ trong khi migration được áp dụng.
- Các branch khác nhau có thể đóng gói changelog khác nhau nếu deployment không dùng cùng artifact.
- Một instance cũ có thể không tương thích với schema do instance mới vừa tạo.

Vì vậy, cần thống nhất **một nguồn artifact/changelog chuẩn** cho mỗi release. Với hệ thống quan trọng, một migration job chuyên trách trong CI/CD thường dễ kiểm soát hơn việc mọi application instance tự chạy một changelog có thể khác phiên bản.

Chiến lược expand-contract giúp giảm rủi ro rolling deployment:

1. Tạo cấu trúc mới theo cách tương thích ngược.
2. Triển khai code có thể đọc/ghi cả trạng thái chuyển tiếp.
3. Chuyển dữ liệu và xác minh.
4. Bỏ cấu trúc cũ sau khi mọi instance đã chuyển.
5. Giữ rollback phù hợp với dữ liệu phát sinh.

Không để hai release khác nhau cùng thay đổi master changelog theo cách chưa được tích hợp rồi cho chúng chạy vào một database chung.

## 17. Những lỗi cộng tác thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| FK không tạo được sau merge | File tạo bảng được include sau file tạo FK | Sắp xếp master theo dependency graph |
| View không tạo được | Cột hoặc bảng nguồn chưa tồn tại | Đưa changeset nền lên trước, thêm precondition HALT |
| Changeset chạy trên branch riêng nhưng lỗi sau merge | Branch riêng dùng fixture khác hoặc thiếu dependency thật | Test trên master tích hợp từ database sạch và database nâng cấp |
| Duplicate changeset identifier | Hai nhóm dùng ID/author/path trùng | Quy ước ID theo domain/ticket và kiểm tra CI |
| Chạy update bị chờ lock | Một Liquibase process khác đang giữ DATABASECHANGELOGLOCK | Kiểm tra process/log trước khi release lock |
| Database dùng chung có changeset lạ | Developer deploy feature branch chưa merge | Chỉ cho artifact canonical deploy vào DB tích hợp |
| Changeset cũ checksum mismatch | Sửa nội dung sau khi đã triển khai | Giữ nguyên lịch sử, thêm changeset mới |
| Chạy nhầm thứ tự do includeAll | Tên file không thể hiện dependency hoặc thứ tự khác kỳ vọng | Include tường minh hoặc quy ước prefix và test |
| MARK_RAN làm thiếu constraint | Dùng precondition để bỏ qua dependency | Dừng HALT, xác minh schema và sửa thứ tự |
| Rollback feature A làm hỏng feature B | B đã tạo dữ liệu/object phụ thuộc A | Xem dependency graph, rollback theo thứ tự và phối hợp chủ sở hữu |
| Branch mới đưa contract chạy quá sớm | Pipeline không chờ backfill/app rollout | Tạo release gate có trạng thái VERIFIED |
| App instance lỗi sau migration | Schema không tương thích với phiên bản app còn chạy | Dùng expand-contract và điều phối rollout |

## 18. Bài thực hành: hợp nhất ba nhánh có phụ thuộc

**Bối cảnh:** Ba nhóm cùng làm một release:

- Nhánh A tạo bảng **customer**.
- Nhánh B tạo bảng **sales_order** và FK tới **customer.id**.
- Nhánh C tạo view **v_customer_order_count** từ hai bảng.

### Bước 1 — Vẽ đồ thị

Xác định:
- A phải trước B-FK.
- B-create-table phải trước B-FK.
- A và B phải trước C-view.

Một thứ tự hợp lệ:

~~~text
A: create customer
B1: create sales_order
B2: add FK
C: create view
~~~

Nếu B1 không phụ thuộc A, B1 có thể được triển khai trước A trong một số thiết kế; nhưng B2 vẫn phải chờ A và B1. Thứ tự trên chọn cách đơn giản để review.

### Bước 2 — Tạo file riêng

- Mỗi nhánh có file changelog riêng.
- Dùng ID theo domain/ticket.
- Gắn rollback phù hợp.
- Dùng precondition HALT cho object nền quan trọng.
- Không chỉnh sửa file của nhánh khác trong lúc phát triển độc lập.

### Bước 3 — Hợp nhất master

Include A trước B, sau đó C. Review thứ tự trong master và đường dẫn file. Xác nhận include không kéo theo changelog thử nghiệm hoặc file không liên quan.

### Bước 4 — Test tích hợp

- Tạo database sạch.
- Chạy validate, update-sql và update.
- Kiểm tra customer, sales_order, FK và view.
- Kiểm tra DATABASECHANGELOG để xác nhận thứ tự.
- Chạy test truy vấn view.

### Bước 5 — Thử thứ tự sai trên database tạm

Đổi thứ tự include để B-FK chạy trước A. Xác nhận precondition HALT hoặc DBMS từ chối FK. Sau đó sửa master và chạy lại trên database được reset/khôi phục phù hợp.

Không xóa lịch sử hoặc sửa DATABASECHANGELOG bằng tay để “làm cho lần chạy lại được”. Dùng database thử nghiệm mới hoặc khôi phục trạng thái test sạch.

### Bước 6 — Thử rollback

Xem rollback SQL và xác nhận:
1. Drop view.
2. Drop FK.
3. Drop sales_order.
4. Drop customer.

Nếu dữ liệu thử đã được chèn, ghi nhận rõ dropTable sẽ xóa dữ liệu. Không dùng bài tập này để rollback database nghiệp vụ thật.

## 19. Checklist review thứ tự changeset giữa các nhánh

Trước khi merge hoặc release, xác nhận:

- Đã liệt kê tất cả changeset mới của các nhánh và người/nhóm sở hữu?
- Đã vẽ dependency giữa bảng, cột, constraint, index, view, dữ liệu và ứng dụng?
- Đã phân biệt dependency kỹ thuật với dependency nghiệp vụ/rollout?
- Master changelog include các file theo một topological order hợp lệ?
- includeAll có thứ tự ổn định và không kéo nhầm file thử nghiệm?
- Changeset ID/author/filename không va chạm và được giữ ổn định?
- File path/logicalFilePath có thay đổi sau khi đã triển khai không?
- Precondition kiểm tra dependency quan trọng và dùng HALT khi điều kiện bắt buộc thiếu?
- Context/label filter không loại mất changeset nền cần thiết?
- Database test theo branch và database tích hợp có chính sách deploy rõ?
- CI chạy từ database sạch và database nâng cấp từ baseline?
- SQL preview đã được review trên DBMS mục tiêu?
- Rollback đảo theo thứ tự ngược và không xóa object/dữ liệu của nhánh khác ngoài ý định?
- DATABASECHANGELOG và DATABASECHANGELOGLOCK được kiểm tra đúng mục đích?
- Spring Boot instances dùng cùng artifact và schema tương thích trong rolling deployment?
- Changeset đã chạy được giữ nguyên; sửa lỗi bằng changeset mới?
- Release gate chờ ứng dụng/backfill hoàn tất trước contract?
- Có bằng chứng kiểm tra schema, dữ liệu và ứng dụng sau deploy?

**Kết luận:** Khi nhiều nhánh cùng phát triển Liquibase changelog, **thứ tự Git merge không tự bảo đảm thứ tự migration đúng**. Nhóm cần mô tả dependency giữa changeset, sắp xếp master changelog theo thứ tự hợp lệ, giữ ID/author/path ổn định, dùng precondition để dừng khi thiếu object nền và kiểm thử trên database sạch lẫn database đã nâng cấp. DATABASECHANGELOG ghi lại lịch sử, DATABASECHANGELOGLOCK điều phối các tiến trình cùng database; cả hai đều không thay thế việc quản lý dependency giữa nhánh. Kết hợp quy ước cộng tác với CI/CD, release gate và rollback theo thứ tự ngược sẽ giúp các nhóm phát triển song song mà vẫn giữ schema và dữ liệu nhất quán.

