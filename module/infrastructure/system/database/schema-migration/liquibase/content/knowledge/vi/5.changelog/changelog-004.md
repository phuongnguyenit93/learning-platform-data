# Sử dụng includeAll và kiểm soát thứ tự phụ thuộc

Trong Liquibase, một changelog gốc có thể chứa trực tiếp các changeset hoặc tham chiếu tới các changelog con. Khi số lượng migration tăng, chia nhỏ theo tệp giúp nhóm review, theo dõi lịch sử và phối hợp nhiều người. Thuộc tính **includeAll** giúp tự động nạp các tệp trong một thư mục, nhưng kéo theo một trách nhiệm quan trọng: **Liquibase không suy luận đồ thị phụ thuộc nghiệp vụ để tự sắp xếp migration**. Nhóm phải thiết kế cấu trúc thư mục, quy ước tên tệp và quy trình kiểm chứng để bảo đảm migration chạy theo thứ tự hợp lệ.

Bài học thuộc chương **Changelog** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Trong toàn bộ module, người học quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Ở đây, trọng tâm là tổ chức changelog với includeAll, hiểu thứ tự thực thi và tránh các lỗi phụ thuộc khó phát hiện khi triển khai lên database đã có dữ liệu.

## 1. includeAll giải quyết bài toán gì?

Giả sử một dự án có hàng trăm thay đổi: tạo bảng khách hàng, tạo bảng đơn hàng, thêm khóa ngoại, thêm index, cập nhật dữ liệu tham chiếu. Nếu viết tất cả changeset trong một tệp, tệp changelog ngày càng dài và dễ xảy ra xung đột khi nhiều người sửa cùng một chỗ.

Một cách tổ chức phổ biến là để mỗi thay đổi hoặc một nhóm thay đổi nhỏ trong một tệp riêng, sau đó sử dụng changelog gốc làm điểm vào:

~~~text
db/changelog/
├── db.changelog-master.yaml
└── changes/
    ├── 0001-create-customers.yaml
    ├── 0002-create-orders.yaml
    ├── 0003-add-order-customer-fk.yaml
    └── 0004-seed-reference-data.yaml
~~~

Thay vì kê khai thủ công từng tệp, changelog gốc có thể sử dụng:

~~~yaml
databaseChangeLog:
  - includeAll:
      path: changes/
      relativeToChangelogFile: true
~~~

Liquibase tìm các changelog có thể nạp trong thư mục được chỉ định, đưa các changeset của chúng vào luồng xử lý và quyết định changeset nào cần thực thi trên database đích dựa vào lịch sử đã ghi nhận. Khi thêm một tệp hợp lệ vào thư mục, lần chạy sau có thể tự nhận diện tệp đó mà không phải chỉnh danh sách include trong changelog gốc.

**Lợi ích:** ít sửa tệp gốc, mỗi PR có thể chứa migration riêng, dễ gom thay đổi theo module và thuận tiện khi nhóm phát triển lớn lên.

**Đổi lại:** một tệp mới cũng tự động trở thành một phần kế hoạch triển khai. Nếu tên hoặc vị trí của nó khiến thứ tự bị sai, Liquibase không thể tự suy ra rằng bảng phải được tạo trước khi có khóa ngoại hoặc dữ liệu phải được chuẩn bị trước khi thêm ràng buộc.

## 2. Phân biệt include và includeAll

Hai cơ chế đều tổ chức changelog thành nhiều tệp, nhưng khác nhau về cách chọn và sắp xếp nguồn.

| Tiêu chí | include | includeAll |
|---|---|---|
| Đối tượng tham chiếu | Một tệp được chỉ định rõ bằng file | Một thư mục được chỉ định bằng path |
| Cách lựa chọn | Chỉ nạp tệp có trong khai báo | Nạp các changelog được phát hiện trong thư mục phù hợp |
| Thứ tự | Theo vị trí từng lệnh include trong changelog gốc | Theo thứ tự includeAll trong changelog gốc, rồi theo thứ tự các tài nguyên do includeAll liệt kê và sắp xếp |
| Khi thêm migration | Phải thêm một lệnh include tương ứng | Có thể chỉ cần thêm tệp vào đúng thư mục |
| Kiểm soát phụ thuộc | Rõ ràng, dễ review thứ tự quan trọng | Phụ thuộc vào quy ước tên, cấu trúc và cấu hình sắp xếp |
| Rủi ro chính | Quên thêm include hoặc sắp xếp sai bằng tay | Vô tình nạp tệp hoặc thay đổi thứ tự khi thêm, đổi tên, di chuyển tệp |

Ví dụ dùng include tường minh:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/0001-create-customers.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/0002-create-orders.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/0003-add-order-customer-fk.yaml
      relativeToChangelogFile: true
~~~

Trường file của include chỉ ra một tài nguyên cụ thể; trường path của includeAll chỉ ra một thư mục. Cả hai đều có thể được dùng trong cùng changelog gốc. Với migration có phụ thuộc nghiêm ngặt, include tường minh thường giúp reviewer nhìn thấy thứ tự ngay trong PR. Với các migration độc lập hoặc có quy tắc tên vững chắc, includeAll giúp giảm việc bảo trì danh sách tệp.

Không cần chọn duy nhất một cơ chế cho toàn dự án. Có thể dùng include để điều phối các giai đoạn bắt buộc và includeAll để nạp các migration độc lập bên trong từng giai đoạn.

## 3. Quy tắc thứ tự của includeAll

### 3.1. Thứ tự sắp xếp là thứ tự tên tài nguyên, không phải thứ tự tạo tệp

Theo cơ chế thông thường, includeAll xử lý các changelog được tìm thấy theo **thứ tự chữ cái (alphabetical/lexicographic) của đường dẫn tài nguyên**. Không nên dựa vào thời gian tạo file, thời gian commit Git, thứ tự trả về từ filesystem hoặc số thứ tự được đọc theo nghĩa số học.

Ví dụ:

~~~text
1-create-customer.yaml
10-add-index.yaml
2-create-order.yaml
~~~

Theo so sánh chuỗi ký tự, 10 có thể được xếp trước 2. Nếu add-index phụ thuộc vào bảng order thì việc chạy từ database trống có thể lỗi.

Dùng số thứ tự có cùng độ rộng:

~~~text
0001-create-customer.yaml
0002-create-order.yaml
0010-add-index.yaml
~~~

Quy tắc nên thống nhất:

- Dùng tiền tố số có độ rộng cố định, đủ lớn cho quy mô dự án (chẳng hạn 0001, 0002, 0003).
- Giữ thống nhất kiểu chữ, cách đặt dấu nối và phần mở rộng tệp; tránh trộn tên hoa/thường khiến việc đọc thứ tự khó dự đoán.
- Sắp xếp theo quan hệ phụ thuộc thật, không chỉ theo ngày tạo hoặc tên tác giả.
- Tránh thay đổi tên hoặc đường dẫn migration đã triển khai chỉ để định dạng đẹp hơn.
- Giữ thư mục chỉ chứa các tệp changelog được chủ động đưa vào triển khai; tệp nháp, backup và tệp thử nghiệm nên nằm ngoài vùng includeAll.

Thứ tự tên tệp chỉ là **quy ước vận hành**, không phải bộ kiểm tra tính đúng đắn của phụ thuộc. Một migration mang tên 0001 vẫn có thể sai nếu bên trong nó tham chiếu đến đối tượng chưa được tạo.

### 3.2. Vị trí trong changelog gốc cũng quyết định thứ tự

Nếu changelog gốc khai báo nhiều phần tử include/includeAll, Liquibase đi qua chúng theo thứ tự xuất hiện trong changelog. Ví dụ:

~~~yaml
databaseChangeLog:
  - includeAll:
      path: schema/
      relativeToChangelogFile: true
  - includeAll:
      path: constraints/
      relativeToChangelogFile: true
  - includeAll:
      path: reference-data/
      relativeToChangelogFile: true
~~~

Cấu hình trên thể hiện ba giai đoạn: cấu trúc bảng, ràng buộc, rồi dữ liệu tham chiếu. Các tệp **trong từng thư mục** được xử lý theo quy tắc sắp xếp của includeAll. Vì vậy, có hai cấp thứ tự: thứ tự khai báo các nhóm ở changelog gốc và thứ tự tệp trong từng nhóm.

Cần bảo đảm mọi changeset trong nhóm trước thực sự cung cấp các điều kiện cần cho nhóm sau. Không phải lúc nào dữ liệu tham chiếu cũng phải chạy sau tất cả constraint: ví dụ, thêm một ràng buộc NOT NULL mới cho bảng đã có dữ liệu có thể yêu cầu backfill trước. Khi đó phải chia giai đoạn phù hợp thay vì áp dụng mô hình thư mục máy móc.

### 3.3. Thư mục con có thể thay đổi tập tài nguyên và thứ tự

includeAll có thể duyệt các thư mục con tùy thuộc cấu hình và phiên bản Liquibase đang dùng. Khi một thư mục có nhiều cấp, không nên suy đoán thứ tự chỉ từ phần tên tệp cuối cùng: đường dẫn tài nguyên và cách so sánh của Liquibase cũng có thể ảnh hưởng thứ tự.

Nếu dự án dùng cây thư mục phức tạp, có ba cách giảm rủi ro:

1. Dùng một thư mục phẳng cho những migration phải chạy theo một chuỗi tuyến tính.
2. Khai báo từng thư mục theo giai đoạn rõ ràng trong changelog gốc.
3. Dùng include tường minh đối với những phần có thứ tự đặc biệt quan trọng.

Một số phiên bản Liquibase cung cấp tùy chọn giới hạn độ sâu duyệt thư mục hoặc bộ lọc đuôi tệp. Hãy kiểm tra cú pháp và mức hỗ trợ trên **phiên bản Liquibase thực tế** trước khi dùng. Dù có bộ lọc, vẫn cần quan sát danh sách changeset được phát hiện trong pipeline.

## 4. Ví dụ đầy đủ: thiết kế thứ tự cho bảng và khóa ngoại

Giả sử một hệ thống đơn hàng cần bảng customers, bảng orders và khóa ngoại từ orders.customer_id sang customers.id. Đồ thị phụ thuộc là:

~~~mermaid
flowchart TD
    A["Tạo bảng customers"]
    B["Tạo bảng orders"]
    C["Thêm FK orders.customer_id → customers.id"]
    D["Thêm dữ liệu đơn hàng mẫu"]
    A --> C
    B --> C
    C --> D
~~~

Bảng customers và orders có thể được tạo độc lập. Changeset tạo khóa ngoại phụ thuộc **cả hai** bảng. Thao tác insert đơn hàng sau đó cần dữ liệu khách hàng hợp lệ nếu khóa ngoại đã được áp dụng.

### 4.1. Changelog gốc

~~~yaml
databaseChangeLog:
  - includeAll:
      path: changes/
      relativeToChangelogFile: true
~~~

### 4.2. Tệp 0001-create-customers.yaml

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 0001-create-customers
      author: team
      changes:
        - createTable:
            tableName: customers
            columns:
              - column:
                  name: id
                  type: bigint
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: varchar(255)
                  constraints:
                    nullable: false
                    unique: true
~~~

Changeset này tạo đối tượng customers. Trên PostgreSQL của phòng thực hành, hãy kiểm tra kiểu auto-increment được Liquibase tạo ra với phiên bản database và driver thực tế.

### 4.3. Tệp 0002-create-orders.yaml

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 0002-create-orders
      author: team
      changes:
        - createTable:
            tableName: orders
            columns:
              - column:
                  name: id
                  type: bigint
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: customer_id
                  type: bigint
                  constraints:
                    nullable: false
~~~

Ở bước này, cột customer_id đã có, nhưng khóa ngoại chưa được thêm. Tách riêng ràng buộc giúp học viên nhìn thấy quan hệ giữa thứ tự tạo bảng và thứ tự tạo constraint.

### 4.4. Tệp 0003-add-order-customer-fk.yaml

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 0003-add-order-customer-fk
      author: team
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: customers
        - tableExists:
            tableName: orders
        - columnExists:
            tableName: orders
            columnName: customer_id
      changes:
        - addForeignKeyConstraint:
            baseTableName: orders
            baseColumnNames: customer_id
            referencedTableName: customers
            referencedColumnNames: id
            constraintName: fk_orders_customers
~~~

Precondition kiểm tra trạng thái database trước khi thêm khóa ngoại. Nếu một bảng hoặc cột chưa tồn tại, Liquibase dừng bằng HALT thay vì ghi nhận một bước triển khai không hoàn chỉnh.

Đây chỉ là một lớp bảo vệ. Precondition **không thay thế** thứ tự tệp đúng, vì quy trình vẫn có thể thất bại hoặc tạo khác biệt giữa môi trường mới và cũ nếu migration được đặt sai chỗ.

### 4.5. Khi phát sinh phụ thuộc về dữ liệu

Giả sử tệp 0004-insert-orders.yaml chèn đơn hàng của customer có ID 1. Migration này chỉ chạy thành công nếu customer ID 1 đã tồn tại; thứ tự tạo bảng và khóa ngoại đúng vẫn chưa đủ.

Nhóm có thể thêm một changeset seed khách hàng trước khi insert orders, sử dụng mã định danh ổn định hoặc truy vấn xác định khóa thay vì giả định ID tự tăng luôn bằng 1. Nếu dùng data migration có tác dụng trên production, cần bảo đảm câu lệnh idempotent theo ý định, có điều kiện dữ liệu rõ và được kiểm thử cả trên database có dữ liệu hiện hữu.

Bài học quan trọng: **phụ thuộc giữa các migration bao gồm schema, constraint, dữ liệu và khả năng tương thích của phiên bản ứng dụng**, không chỉ thứ tự tạo bảng.

## 5. Thiết kế quy tắc phụ thuộc trước khi đặt tên tệp

Một cách làm hiệu quả là xác định các cạnh phụ thuộc trước, rồi mới chọn tên hoặc thư mục. Với mỗi migration, hãy hỏi:

- Nó cần bảng, cột, kiểu dữ liệu, schema, view hoặc extension nào đã tồn tại?
- Nó cần bản ghi tham chiếu nào đã tồn tại?
- Nó có làm thay đổi một constraint mà dữ liệu hiện tại chưa thỏa mãn không?
- Nó có cần ứng dụng phiên bản trước cùng hoạt động trong giai đoạn chuyển tiếp không?
- Khi rollback, đối tượng nào phải được gỡ hoặc phục hồi trước?

Ví dụ về thứ tự hợp lệ đối với thay đổi cột:

~~~text
0001-add-new-column.yaml
0002-backfill-new-column.yaml
0003-validate-backfill.yaml
0004-add-not-null-constraint.yaml
0005-switch-read-path.yaml  (bước ứng dụng, thường không nằm trong changelog)
0006-drop-old-column.yaml   (sau khi xác nhận không còn client sử dụng)
~~~

Trong thực tế, bước chuyển đổi ứng dụng có thể nằm trong một deployment riêng, không phải file Liquibase. Hệ thống phân tán nên dùng chiến lược **expand–migrate–contract**: mở rộng schema tương thích ngược, di chuyển dữ liệu và ứng dụng, sau đó mới thu hẹp schema. includeAll chỉ điều khiển thứ tự các tệp được nạp; nó không điều phối toàn bộ vòng đời phát hành ứng dụng.

### Khi nào cần include tường minh?

Dùng include tường minh nếu:

- Một thay đổi có phụ thuộc quan trọng phải được reviewer nhìn thấy ngay trong changelog gốc.
- Cần xen kẽ migration từ nhiều thư mục theo thứ tự không thể biểu đạt rõ ràng bằng tên.
- Việc thêm tệp mới tự động vào một thư mục có thể gây rủi ro lớn.
- Nhóm muốn khóa danh sách migration của một bản phát hành trước khi kiểm thử và đưa lên production.

Một cấu trúc kết hợp có thể là:

~~~yaml
databaseChangeLog:
  - include:
      file: bootstrap/0001-create-core-schema.yaml
      relativeToChangelogFile: true
  - includeAll:
      path: features/
      relativeToChangelogFile: true
  - include:
      file: constraints/0900-add-critical-constraints.yaml
      relativeToChangelogFile: true
~~~

Cần xác nhận các file trong features không phụ thuộc vào constraint được khai báo sau và không vô tình chứa migration tương đương một file đã include tường minh. Không nạp chồng một thư mục tổng với các thư mục con đã include riêng nếu điều đó tạo ra thay đổi trùng lặp.

## 6. Các thuộc tính includeAll thường cần biết

| Thuộc tính | Mục đích | Điểm cần kiểm soát |
|---|---|---|
| path | Chỉ định thư mục chứa các changelog con | Đường dẫn phải khớp với vị trí tài nguyên khi chạy thực tế |
| relativeToChangelogFile | Xác định cách hiểu path tương đối so với tệp changelog chứa includeAll | Hữu ích khi đóng gói tài nguyên cùng ứng dụng |
| errorIfMissingOrEmpty | Quy định hành vi khi thư mục được chỉ định không tồn tại hoặc không chứa tệp hợp lệ | Với thư mục migration bắt buộc, nên báo lỗi thay vì im lặng |
| endsWithFilter | Lọc tài nguyên theo phần đuôi tên tệp (khi phiên bản Liquibase hỗ trợ) | Tránh vô tình nạp file không phải changelog; xác nhận đúng cú pháp và phiên bản |
| minDepth / maxDepth | Giới hạn độ sâu duyệt thư mục (khi hỗ trợ) | Giúp kiểm soát cây thư mục; cần xem lại khi thay cấu trúc |
| resourceComparator | Cho phép dùng bộ so sánh tài nguyên tùy chỉnh trong môi trường hỗ trợ | Tăng độ phức tạp, phụ thuộc mã Java và classpath; không nên dùng nếu quy ước tên đủ rõ |

Ví dụ minh họa có lọc file YAML:

~~~yaml
databaseChangeLog:
  - includeAll:
      path: changes/
      relativeToChangelogFile: true
      errorIfMissingOrEmpty: true
      endsWithFilter: .yaml
~~~

Tùy chọn hỗ trợ và cú pháp có thể khác nhau giữa các phiên bản Liquibase. Hãy kiểm tra tài liệu đúng phiên bản đang chạy và chạy validate trên CLI/ứng dụng thực tế trước khi áp dụng một thuộc tính nâng cao.

**Đừng dùng comparator tùy chỉnh để che giấu quy tắc phụ thuộc khó hiểu.** Nếu reviewer không thể nhìn thấy thứ tự và lý do chỉ bằng cấu trúc changelog, việc vận hành và debug sẽ khó hơn. Chỉ cân nhắc resourceComparator khi có yêu cầu đặc thù đã được kiểm thử và nhóm kiểm soát được mã comparator cùng phiên bản runtime.

## 7. Giữ ổn định định danh changeset khi tổ chức lại thư mục

Một changeset được nhận diện qua tổ hợp **ID, author và đường dẫn tệp changelog** (hoặc logical file path đã được cấu hình tương ứng). Bảng DATABASECHANGELOG lưu các thông tin này để Liquibase biết thay đổi nào đã chạy.

Ví dụ ban đầu:

~~~text
db/changelog/changes/0001-create-customers.yaml
~~~

Sau đó nhóm đổi vị trí thành:

~~~text
db/changelog/2026/0001-create-customers.yaml
~~~

Dù ID và author giữ nguyên, đường dẫn đã thay đổi có thể khiến Liquibase xem đây là changeset khác và cố thực hiện lại. Hậu quả có thể là báo bảng đã tồn tại, constraint trùng tên hoặc dữ liệu bị chèn lại. Nếu tệp cũ vẫn còn trong vùng includeAll, changeset còn có thể bị phát hiện ở cả hai vị trí.

Để giảm rủi ro:

1. Đặt tên và cấu trúc thư mục ổn định ngay từ đầu.
2. Xem các migration đã chạy trên môi trường dùng chung là lịch sử bất biến.
3. Khi muốn chỉnh một migration đã phát hành, ưu tiên tạo changeset mới thay vì sửa hoặc đổi tên tệp cũ.
4. Nếu bắt buộc di chuyển, nghiên cứu cách dùng **logicalFilePath** theo phiên bản Liquibase cụ thể, xác nhận quy tắc kế thừa/đường dẫn và thử trên database đã có lịch sử trước khi triển khai.
5. So sánh danh sách changeset Liquibase dự kiến chạy trước và sau khi di chuyển; không mặc định đổi path là thao tác vô hại.

**Checksum** giúp phát hiện nội dung changeset đã triển khai bị thay đổi, nhưng không thay thế việc kiểm soát định danh và đường dẫn. Một lỗi tổ chức includeAll có thể dẫn đến thay đổi được nhận diện lại ngay cả khi nội dung không đổi.

## 8. Thêm migration mới vào hệ thống đã triển khai

Đây là tình huống quan trọng nhất khi vận hành lâu dài.

Giả sử production đã chạy các tệp 0001, 0002, 0003. Nhóm tạo tệp mới 0000-create-extension.yaml vì nghĩ cần chạy nó trước tất cả. Khi chạy lại changelog:

- Trên **database mới**, Liquibase xử lý 0000 trước 0001 theo thứ tự tên; kết quả có thể khác luồng thiết kế ban đầu.
- Trên **database production**, các changeset 0001–0003 đã được ghi trong DATABASECHANGELOG, còn 0000 là changeset chưa chạy. Liquibase có thể áp dụng 0000 sau khi hệ thống đã có schema và dữ liệu của ba changeset kia.

Như vậy, một changelog có thể tạo hai lịch sử thực thi khác nhau tùy trạng thái database. Điều này không nhất thiết luôn sai, nhưng cần được chủ động thiết kế và kiểm thử.

Với các dự án dùng tiền tố tăng dần, **migration mới thông thường nên được thêm ở cuối chuỗi phát hành đã tồn tại**. Nếu cần chuẩn bị dữ liệu hoặc cấu trúc mà một migration cũ đáng lẽ cần, hãy viết thay đổi bổ sung thích hợp cho database hiện tại; đừng giả định đặt tên nhỏ hơn sẽ khiến Liquibase viết lại lịch sử.

Tương tự, đổi tên tệp để thay đổi thứ tự sau khi đã triển khai không làm Liquibase chạy lại các changeset đã ghi nhận theo đúng thứ tự mới. Nó còn có thể thay đổi danh tính changeset do đường dẫn thay đổi. Quy trình review vì thế cần xem xét cả **fresh install** lẫn **upgrade từ phiên bản trước**.

## 9. Precondition, context và label có thay thế cơ chế phụ thuộc không?

### 9.1. Precondition là kiểm tra điều kiện, không phải bộ sắp xếp

Precondition có thể kiểm tra rằng bảng tồn tại, cột tồn tại, database đang ở trạng thái nhất định hoặc có bản ghi dữ liệu phù hợp. Nó hữu ích để dừng sớm với lỗi dễ hiểu. Ví dụ HALT khi thiếu bảng là tín hiệu tốt hơn so với để câu lệnh DDL lỗi mơ hồ.

Tuy nhiên, precondition không tự đưa migration tạo bảng chạy lên phía trước. Nếu thiếu một migration tiền đề, phải sửa cấu trúc changelog hoặc cách chọn changeset; không dùng precondition như cơ chế điều phối thứ tự thay thế.

Đặc biệt thận trọng với hành vi MARK_RAN: nó có thể ghi nhận changeset như đã chạy dù thay đổi thực tế không được thực thi. Nếu sử dụng sai, database sẽ có lịch sử biểu kiến hoàn chỉnh nhưng thiếu cấu trúc hoặc dữ liệu cần thiết.

### 9.2. Context và label có thể làm phụ thuộc bị thiếu

Context và label cho phép chọn changeset theo môi trường hoặc mục đích. Nhưng chúng cũng có thể khiến chỉ một nửa chuỗi phụ thuộc được chọn.

Ví dụ: changeset tạo bảng order_status bị giới hạn vào context dev, trong khi changeset thêm khóa ngoại vào order_status lại không bị giới hạn. Trên production, bảng không được tạo nhưng khóa ngoại vẫn được yêu cầu, dẫn đến lỗi.

Nguyên tắc:

- Các migration tạo schema cốt lõi nên có phạm vi nhất quán trên những môi trường dùng chung schema.
- Nếu một changeset phụ thuộc changeset được lọc bằng context/label, điều kiện lọc phải tương thích.
- Dữ liệu mẫu chỉ dành cho development phải được tách khỏi dữ liệu tham chiếu bắt buộc cho production.
- Kiểm thử chính xác tổ hợp context/label được pipeline sử dụng, thay vì chỉ chạy mặc định ở local.

Không dùng context/label như biện pháp phân quyền. Việc ai có quyền thay đổi schema được kiểm soát bởi quyền database, pipeline và chính sách triển khai.

## 10. Tương tác với rollback và thứ tự hủy phụ thuộc

Một chuỗi migration hợp lệ khi triển khai tiến không có nghĩa là rollback luôn an toàn. Nếu bảng orders có khóa ngoại trỏ tới customers, không thể xóa customers trước khi gỡ khóa ngoại hoặc xử lý các đối tượng phụ thuộc.

Thông thường, khi rollback theo số lượng changeset hoặc về một mốc phù hợp, Liquibase xử lý các thay đổi đã ghi nhận theo thứ tự đảo ngược. Nhưng khả năng rollback từng changeset còn phụ thuộc change type, database và cách rollback được khai báo. SQL tùy biến hoặc migration dữ liệu một chiều có thể không có rollback tự động.

Với cấu trúc ví dụ:

~~~text
Triển khai:
0001 tạo customers
0002 tạo orders
0003 thêm FK orders → customers

Rollback về trước 0001:
0003 gỡ FK
0002 gỡ orders
0001 gỡ customers
~~~

Nếu một changeset seed dữ liệu bị xóa hoặc làm biến đổi dữ liệu, rollback cấu trúc không tự khôi phục thông tin đã mất. Với production, cần phương án backup/restore hoặc forward-fix đã được thử nghiệm.

Khi quyết định đưa tệp vào includeAll, người viết migration nên trả lời cả hai câu hỏi: những điều kiện nào phải tồn tại **trước khi chạy**, và những đối tượng hoặc dữ liệu nào phải được xử lý **khi rollback**.

## 11. Kiểm chứng thứ tự trước khi chạy migration thật

Không nên kết luận thứ tự đúng chỉ bằng cách nhìn tên tệp. Phải kiểm chứng những thay đổi Liquibase thực sự nhận diện khi chạy với classpath, search path, context, label và phiên bản đã chọn.

### 11.1. Kiểm tra cấu trúc và danh sách dự kiến

Với CLI Liquibase được cấu hình sẵn kết nối database, changelog và quyền phù hợp, có thể dùng các lệnh tương ứng:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
~~~

Ý nghĩa của từng bước:

- **validate:** kiểm tra tính hợp lệ ở mức Liquibase có thể xác minh, giúp phát hiện lỗi khai báo, tham chiếu và các vấn đề liên quan đến changeset.
- **status --verbose:** liệt kê các changeset chưa áp dụng trên database đích; có thể dùng để đối chiếu danh sách và vị trí.
- **update-sql:** tạo trước SQL cho phần thay đổi chờ chạy để reviewer kiểm tra đối tượng, thứ tự và cú pháp dự kiến.

Tên lệnh, tùy chọn và phạm vi kiểm tra cần đối chiếu với phiên bản Liquibase mà nhóm đang dùng. Cả ba bước đều **không thay thế** kiểm thử thực thi trên database đại diện: precondition có thể phụ thuộc trạng thái dữ liệu, DDL có thể khóa bảng và một SQL hợp lệ về cú pháp vẫn có thể lỗi do quyền hoặc constraint.

Khi thực sự chạy update trên database thực hành, kiểm tra lịch sử:

~~~sql
SELECT id, author, filename, orderexecuted, dateexecuted, exectype
FROM databasechangelog
ORDER BY orderexecuted;
~~~

DATABASECHANGELOG ghi lịch sử đã áp dụng cho database. Nó không có chức năng chứng minh mọi môi trường có cùng dữ liệu; phải kiểm tra đối tượng, constraint và kết quả dữ liệu bằng các truy vấn độc lập.

### 11.2. Kiểm thử trên hai trạng thái database

Một quy trình kiểm chứng đáng tin cậy phải có ít nhất hai kịch bản:

| Kịch bản | Mục đích | Phải xác nhận |
|---|---|---|
| Database mới hoàn toàn | Kiểm tra toàn bộ changelog tạo được hệ thống từ đầu | Tất cả bảng, index, constraint và dữ liệu bắt buộc được tạo đúng theo thứ tự |
| Database đã chạy phiên bản trước | Kiểm tra nâng cấp an toàn khi lịch sử changeset đã tồn tại | Chỉ những changeset mới cần thiết được áp dụng, không chạy lại lịch sử do đổi path, không phá dữ liệu hiện hữu |

Khi dự án hỗ trợ nhiều database engine hoặc phiên bản engine, cần chạy thử trên từng cấu hình được hỗ trợ. Nếu pipeline dùng context/label khác local, hãy kiểm tra thêm các tổ hợp thực tế, đặc biệt những đường đi có thể bỏ qua migration tiền đề.

### 11.3. Xác minh phạm vi includeAll trong artifact được đóng gói

Với Spring Boot, changelog thường nằm trong classpath, chẳng hạn thư mục resources:

~~~text
src/main/resources/
└── db/changelog/
    ├── db.changelog-master.yaml
    └── changes/
        ├── 0001-create-customers.yaml
        ├── 0002-create-orders.yaml
        └── 0003-add-order-customer-fk.yaml
~~~

Cấu hình thường gặp:

~~~properties
spring.liquibase.change-log=classpath:/db/changelog/db.changelog-master.yaml
~~~

Cần bảo đảm tệp changelog con thực sự được đóng gói trong JAR hoặc image container. Một cấu hình chạy được từ thư mục source nhưng thiếu tài nguyên sau build có thể gây lỗi không tìm thấy tệp hoặc khiến tập migration khác dự kiến.

Không nên dựa vào thứ tự duyệt file của hệ điều hành. Hãy kiểm tra trực tiếp qua Liquibase ở môi trường chạy của artifact. Với ứng dụng nhiều replica, nhóm nên quyết định rõ migration chạy trong job trước deployment hay lúc ứng dụng khởi động, và bảo đảm không có tiến trình triển khai chồng chéo.

## 12. Lỗi thường gặp khi dùng includeAll

| Triệu chứng | Khả năng gây ra | Cách xử lý |
|---|---|---|
| Tệp 0010 chạy trước 0002 | Tên có độ rộng số không nhất quán | Dùng tiền tố cố định cho tệp mới; với tệp đã triển khai, đánh giá rủi ro đổi path trước khi đổi tên |
| Lỗi table/column does not exist | Changeset phụ thuộc chạy trước changeset tạo đối tượng | Xác định đồ thị phụ thuộc; sửa thứ tự bằng cấu trúc và tệp bổ sung phù hợp |
| Nhiều tệp ngoài ý muốn được nạp | Thư mục chứa changelog nháp hoặc cấu hình duyệt thư mục quá rộng | Thu hẹp thư mục, áp dụng bộ lọc được phiên bản hỗ trợ, loại tệp nháp ra khỏi vùng includeAll |
| Chạy từ IDE được nhưng trong JAR bị lỗi | Changelog con không nằm trong artifact hoặc đường dẫn classpath khác | Kiểm tra đóng gói resources và cấu hình relativeToChangelogFile/search path |
| Database cũ báo bảng đã tồn tại sau khi di chuyển tệp | ID/author giữ nguyên nhưng đường dẫn định danh changeset thay đổi | Kiểm tra DATABASECHANGELOG; nghiên cứu logicalFilePath và quy trình di chuyển an toàn |
| Database mới chạy tốt nhưng nâng cấp production lỗi | Chỉ kiểm thử fresh install, bỏ qua lịch sử hiện hữu | Thử cả migration từ baseline/version trước lên phiên bản mới |
| Chỉ dev chạy được, production thiếu bảng | Context/label lọc mất changeset tiền đề | Đối chiếu bộ lọc theo môi trường và phạm vi phụ thuộc |
| Changelog bị lặp hoặc vòng lặp tham chiếu | Include/includeAll chồng lấn hoặc changelog gián tiếp nạp lại chính nó | Tách phạm vi thư mục, bỏ khai báo trùng và kiểm tra đường dẫn tham chiếu |
| Rollback thất bại do FK | Đảo ngược changeset không xử lý quan hệ phụ thuộc phù hợp | Thử rollback trên database đại diện, viết rollback tường minh khi cần |
| Migration mới chạy ngoài thứ tự mong đợi trên database cũ | Thêm file có tiền tố đứng trước các file đã chạy | Kiểm tra lịch sử trước khi đặt tên; phát hành migration mới tiếp nối trạng thái hiện tại |

Khi điều tra lỗi, bắt đầu từ tệp changelog gốc, đường dẫn includeAll và danh sách changeset Liquibase đọc được. Sau đó kiểm tra DATABASECHANGELOG của database đích để biết trạng thái thực thi; cuối cùng đối chiếu bảng, constraint và dữ liệu thật. Không tự sửa bảng DATABASECHANGELOG hoặc làm mới checksum để che giấu lỗi thứ tự.

## 13. Quy ước cho nhóm và tích hợp CI/CD

Đối với repository do nhiều người cùng phát triển, nên đưa các quy tắc sau vào code review:

1. **Một điểm vào chính:** Changelog gốc được version control và được ứng dụng/pipeline tham chiếu nhất quán.
2. **Tiền tố tăng dần và cố định:** Người tạo migration mới dùng một tên tệp rõ ràng, không lấn vào khoảng lịch sử đã triển khai nếu không có lý do được kiểm chứng.
3. **Tệp nhỏ, ý nghĩa rõ:** Một tệp chứa một hoặc vài changeset liên quan chặt chẽ, dễ review và dễ điều tra.
4. **Định danh ổn định:** Không tùy tiện sửa ID, author, tên hoặc vị trí tệp đã triển khai; dùng changeset mới để sửa trạng thái database.
5. **Phụ thuộc ghi rõ:** PR mô tả những bảng, cột, dữ liệu hoặc phiên bản ứng dụng mà migration cần.
6. **Bộ lọc nhất quán:** Các changeset phụ thuộc nhau phải hoạt động trong những context/label phù hợp.
7. **Kiểm tra hai chiều:** Thử từ database trống và thử nâng cấp từ database có lịch sử của bản phát hành trước.
8. **Xem trước SQL:** Review SQL dự kiến và những precondition ảnh hưởng đến việc chạy hoặc bỏ qua migration.
9. **Rollback/forward-fix:** Mỗi thay đổi có rủi ro phải có kế hoạch phục hồi; bảo toàn dữ liệu quan trọng.
10. **Chốt artifact phát hành:** Kiểm soát nội dung changelog được đóng gói, phiên bản Liquibase và database đích trước khi lên production.

Một pipeline CI/CD có thể xác minh syntax, build artifact, khởi tạo database thử nghiệm, chạy changelog và chạy kiểm tra schema/dữ liệu. Pipeline nâng cấp cần bổ sung một database đã được migrate theo bản trước, sau đó áp dụng bản mới. Nếu dự án phát hành song song nhiều nhánh, hãy có quy tắc giải quyết xung đột tiền tố và dependency; không giả định tên tệp do từng nhánh tạo ra sẽ luôn tạo thứ tự hợp lệ khi merge.

## 14. Bài thực hành tự kiểm tra

Trên PostgreSQL lab của module, hãy thực hiện lần lượt:

1. Tạo changelog gốc có includeAll trỏ tới một thư mục changes trong cùng cây tài nguyên.
2. Tạo hai tệp với prefix 0001 và 0002 để tạo customers và orders, sau đó tạo 0003 để thêm khóa ngoại.
3. Kiểm tra danh sách changeset và SQL dự kiến trước khi chạy update.
4. Chạy migration trên database trống; xem bảng và khóa ngoại, sau đó truy vấn DATABASECHANGELOG theo orderexecuted.
5. Tạo một database thực hành khác đang ở trạng thái đã chạy 0001–0002 rồi chạy lên 0003; so sánh với database dựng mới từ đầu.
6. Trên bản sao riêng, thử đặt tên tệp 1, 2, 10 để quan sát sự khác biệt giữa thứ tự chuỗi và thứ tự số học; không thử nghiệm này trên database dùng chung.
7. Thử thêm một tệp có tiền tố đứng trước lịch sử đã chạy. Dùng status và update-sql để dự đoán điều gì xảy ra trên database đã có dữ liệu, rồi so sánh với database mới.
8. Đưa một migration seed chỉ dành cho dev vào cùng thư mục và dùng context/label; kiểm chứng không để migration production phụ thuộc vào dữ liệu bị lọc.
9. Thử rollback trong môi trường có thể xóa bỏ, kiểm tra các đối tượng phụ thuộc và dữ liệu còn lại.

Điều kiện hoàn thành: người học giải thích được vì sao tên tệp không tự bảo đảm thứ tự hợp lệ, phân biệt được cơ chế include và includeAll, đọc được lịch sử thay đổi trên từng database, đồng thời dự đoán được hậu quả khi thêm hoặc di chuyển migration sau khi đã triển khai.

## 15. Checklist trước khi merge một PR có includeAll

| Câu hỏi kiểm tra | Bằng chứng cần có |
|---|---|
| Changelog gốc có đang nạp đúng thư mục? | Đường dẫn, classpath và vị trí tệp được xác minh |
| Các tệp mới có nằm đúng vùng includeAll? | Danh sách tệp được phát hiện khớp với PR |
| Tên tệp có tuân thủ quy ước thứ tự? | Prefix cố định; không tạo xung đột thứ tự |
| Có dependency nào chưa được đáp ứng? | Đồ thị bảng, khóa ngoại, dữ liệu và phiên bản ứng dụng được review |
| Context/label có bỏ qua migration tiền đề? | Chạy kiểm chứng đúng bộ lọc của từng môi trường |
| Có đổi tên/path của tệp đã chạy? | Nếu có, kế hoạch giữ định danh và kiểm thử nâng cấp |
| Có thay đổi checksum ngoài dự kiến? | So sánh changelog và DATABASECHANGELOG, giải quyết bằng migration phù hợp |
| Database mới có dựng được từ đầu? | Kết quả kiểm thử fresh install |
| Database cũ có nâng cấp được? | Kết quả kiểm thử upgrade với dữ liệu hiện hữu |
| Có thể phục hồi khi gặp lỗi? | Rollback hoặc forward-fix và backup đã được kiểm tra |

**Nguyên tắc cốt lõi:** includeAll giúp *phát hiện và nạp* changelog theo quy tắc sắp xếp tài nguyên; còn việc bảo đảm phụ thuộc đúng thuộc về thiết kế migration và quy trình kiểm chứng của nhóm. Hãy dùng includeAll khi cần phát triển mở rộng, đặt tên tệp nhất quán, giữ ổn định lịch sử đã triển khai và kiểm thử cả cơ sở dữ liệu mới lẫn cơ sở dữ liệu đang vận hành. Khi thứ tự phụ thuộc quá phức tạp hoặc cần khóa chính xác danh sách triển khai, hãy chuyển phần quan trọng sang include tường minh để reviewer và pipeline có thể kiểm soát rõ ràng.

