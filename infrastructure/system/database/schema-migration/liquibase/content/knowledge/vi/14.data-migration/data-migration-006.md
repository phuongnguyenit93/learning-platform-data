# Thiết kế dữ liệu tham chiếu có khóa ổn định

Trong chương **Chuyển đổi dữ liệu** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, một bài toán quan trọng là quản lý các danh mục dùng chung như trạng thái thanh toán, loại đơn hàng, mã quốc gia, đơn vị tiền tệ và lý do hủy. Các bản ghi này thường có ít hàng nhưng được tham chiếu bởi nhiều bảng, dịch vụ, báo cáo và sự kiện. Nếu định danh thay đổi tùy môi trường hoặc tùy lần seed, cùng một changelog có thể tạo ra dữ liệu không tương thích giữa development, staging và production.

Liquibase quản lý thay đổi schema và dữ liệu qua **changelog**, **changeset**, **precondition**, **checksum** và **DATABASECHANGELOG**. Thiết kế khóa ổn định cho dữ liệu tham chiếu giúp migration được kiểm chứng, có kế hoạch rollback, phối hợp nhiều môi trường và tích hợp nhất quán với Spring Boot hoặc CI/CD. Trọng tâm của bài là **định danh có ý nghĩa bất biến**, không phải chỉ cách chèn một vài dòng vào database.

## 1. Dữ liệu tham chiếu là gì?

Dữ liệu tham chiếu (*reference data*) là tập giá trị tương đối nhỏ, có vai trò định nghĩa các lựa chọn, phân loại hoặc trạng thái mà dữ liệu nghiệp vụ sử dụng:

| Loại | Ví dụ | Cách sử dụng |
|---|---|---|
| Trạng thái | PENDING, SUCCEEDED, FAILED | Được bảng payment và logic nghiệp vụ tham chiếu |
| Loại nghiệp vụ | RETAIL, WHOLESALE | Phân loại khách hàng hoặc đơn hàng |
| Mã chuẩn | VND, USD; VN, SG | Liên kết với chuẩn mã tiền tệ/quốc gia |
| Lý do nghiệp vụ | INVALID_ACCOUNT, CUSTOMER_REQUEST | Phân tích lý do thất bại hoặc hủy |
| Danh mục điều khiển | STANDARD, EXPRESS | Xác định các chế độ xử lý có kiểm soát |

Phân biệt với hai loại dữ liệu khác:

- **Dữ liệu giao dịch** như payment, order, invoice: được tạo liên tục, có vòng đời riêng, không nên coi là migration seed cố định.
- **Dữ liệu cấu hình runtime** như API endpoint, timeout, feature flag: có thể cần thay đổi theo môi trường hoặc trong quá trình vận hành; không nên tự động đưa tất cả vào changelog.

Một danh mục do người vận hành thường xuyên thêm/sửa có thể không phù hợp để Liquibase là nguồn quản lý duy nhất. Liquibase đặc biệt hữu ích cho tập giá trị **do nhóm phát triển quản trị**, cần triển khai có phiên bản và phải khớp với mã ứng dụng.

## 2. Khóa ổn định có nghĩa là gì?

Một khóa ổn định là giá trị nhận diện **cùng một khái niệm** qua thời gian và qua các môi trường. Ví dụ:

~~~text
payment_status
---------------------------------
code        display_name
PENDING     Chờ xử lý
SUCCEEDED   Thành công
FAILED      Thất bại
~~~

Ở đây **code** là định danh; **display_name** là nhãn có thể thay đổi. Tại development, staging và production, SUCCEEDED đều phải đại diện cho đúng khái niệm thanh toán thành công, bất kể thứ tự insert, ngôn ngữ hiển thị hay ID nội bộ.

Khóa ổn định cần có những tính chất:

1. **Duy nhất trong phạm vi được xác định:** không có hai dòng cùng code trong cùng danh mục.
2. **Bất biến về nghĩa:** SUCCEEDED không được đổi từ "thành công" thành "đã hoàn tiền".
3. **Nhất quán liên môi trường:** một code được nhận diện giống nhau ở mọi database triển khai cùng ứng dụng.
4. **Không phụ thuộc cách nạp dữ liệu:** không dựa vào thứ tự INSERT, sequence hoặc auto-increment.
5. **Được kiểm soát thay đổi:** đổi tên nhãn không làm thay khóa; tách/gộp ý nghĩa phải có migration và kế hoạch tương thích.

Không nhầm *khóa ổn định* với *dữ liệu hoàn toàn bất biến*. Nhãn hiển thị, thứ tự sắp xếp hoặc trạng thái ngừng sử dụng có thể thay đổi, còn định danh và ý nghĩa lịch sử của nó phải được bảo vệ.

## 3. Chọn khóa nghiệp vụ hay khóa thay thế?

Ba mô hình thường gặp:

| Mô hình | Ví dụ khóa | Ưu điểm | Nhược điểm/cần lưu ý |
|---|---|---|---|
| Mã nghiệp vụ làm PK | code = SUCCEEDED | Dễ đọc, giống nhau giữa môi trường, seed đơn giản | Khó đổi nếu ý nghĩa mã không thực sự bất biến; FK kiểu chuỗi |
| ID số làm PK, code có UNIQUE | id = 27, code = SUCCEEDED | FK số gọn, phù hợp ORM và bảng lớn | ID tự sinh có thể khác môi trường; tích hợp phải dùng code |
| UUID ổn định làm PK, code có UNIQUE | UUID được cấp cố định hoặc sinh xác định | Định danh độc lập DB, tránh va chạm khi phân tán | Khó đọc; cần chính sách sinh và lưu trữ rõ ràng |

### 3.1. Code làm primary key

Phù hợp với danh mục nhỏ, được kiểm soát bởi mã ứng dụng, có code ổn định và ít biến động. Ví dụ bảng payment_status dùng code VARCHAR(24) làm PK. Bảng payment có status_code trỏ trực tiếp đến code.

Điểm mạnh là không có bảng ánh xạ ID ngẫu nhiên giữa các môi trường. Điểm đánh đổi là cột FK và index liên quan chứa chuỗi; với hệ thống giao dịch rất lớn, cần đánh giá kích thước, hiệu năng và khả năng duy trì tính bất biến của code.

### 3.2. Surrogate ID và alternate key ổn định

Nếu bảng reference data cần số ID nội bộ, có thể dùng:

~~~text
payment_status
id    code         display_name
11    PENDING      Chờ xử lý
12    SUCCEEDED    Thành công
13    FAILED       Thất bại
~~~

Tuy nhiên, một database khác có thể có ID 41, 42, 43 cho cùng ba code. Trong thiết kế này:

- **id** là khóa nội bộ của một database.
- **code** là khóa nghiệp vụ/khóa trao đổi ổn định và phải có UNIQUE.
- API, message, CSV tích hợp và seed các bảng khác nên dùng **code**, hoặc giải quyết id từ code tại database đích.
- Không đưa các giá trị id tự sinh vào enum Java như một sự thật chung của tất cả môi trường.

Một ngoại lệ là nhóm chủ động cấp **ID cố định trên toàn hệ thống** (ví dụ 100, 200, 300). Cách này có thể đúng khi có registry quản lý khoảng giá trị, bảo đảm không trùng và không bị ứng dụng/DB tự cấp ID lấn vào vùng dành riêng. Nhưng nó làm tăng gánh nặng quản trị và thường không cần khi đã có code ổn định.

### 3.3. UUID ổn định

Có thể dùng UUID cố định được cấp một lần và lưu trong seed; hoặc tạo UUID xác định từ một namespace bất biến và mã chuẩn hóa. Không dùng UUID ngẫu nhiên mỗi lần deploy cho cùng một bản ghi: hai môi trường sẽ có định danh khác nhau.

Ngay cả UUID xác định cũng không giải quyết được bài toán **đổi ý nghĩa**. Nếu mã đầu vào hoặc namespace thay đổi thì UUID được sinh sẽ khác; cần có quy trình quản lý version và tương thích như với mọi loại khóa khác.

## 4. Quy tắc thiết kế code

Có thể thống nhất một chuẩn cho danh mục:

~~~text
[A-Z][A-Z0-9_]*
PENDING
SUCCEEDED
FAILED
CUSTOMER_CANCELLED
~~~

Đây là quy ước minh họa, không phải cú pháp bắt buộc của Liquibase. Quy ước nên chỉ rõ:

- Code dùng chữ hoa ASCII, không có khoảng trắng và không phụ thuộc ngôn ngữ hiển thị.
- Không tạo code từ số thứ tự UI hoặc tên dịch có dấu.
- Không dùng mã chỉ có ý nghĩa trong một môi trường như STATUS_1_DEV.
- Mỗi code có mô tả nghiệp vụ và điều kiện chuyển trạng thái rõ ràng.
- Không tái sử dụng code đã ngừng hoạt động cho một khái niệm mới.
- Không đổi code chỉ để sửa chính tả nhãn; thay display_name riêng.
- Nếu hệ thống nhiều tenant, xác định phạm vi uniqueness theo tenant hay toàn hệ thống.

Ví dụ **SUCCEEDED** không nên đổi thành **DONE** sau khi đã xuất hiện trong bảng payment và event. Nếu cần thay đổi thuật ngữ hiển thị sang "Hoàn tất", chỉ cập nhật nhãn. Nếu nghiệp vụ thật sự có thêm trạng thái COMPLETED với nghĩa khác, phải tạo code mới và thiết kế chuyển tiếp.

Một code phù hợp thường xuất phát từ **định nghĩa nghiệp vụ lâu dài**, không phải từ cách hiển thị ngắn hạn. Với dữ liệu tiêu chuẩn quốc tế, ưu tiên mã tiêu chuẩn đã được tổ chức công nhận, đồng thời quản lý cách xử lý khi chuẩn đó cập nhật hoặc ngừng sử dụng mã.

## 5. Thiết kế schema với khóa code bất biến

Ví dụ PostgreSQL và Liquibase YAML: bảng payment_status lưu ba trạng thái đã định nghĩa. Changelog tạo bảng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-001-create-payment-status"
      author: "team-db"
      comment: "Tạo danh mục trạng thái thanh toán, code là khóa ổn định"
      changes:
        - createTable:
            schemaName: app
            tableName: payment_status
            columns:
              - column:
                  name: code
                  type: VARCHAR(24)
                  constraints:
                    primaryKey: true
                    primaryKeyName: pk_payment_status
                    nullable: false
              - column:
                  name: display_name
                  type: VARCHAR(100)
                  constraints:
                    nullable: false
              - column:
                  name: sort_order
                  type: INT
                  constraints:
                    nullable: false
              - column:
                  name: active
                  type: BOOLEAN
                  defaultValueBoolean: true
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            schemaName: app
            tableName: payment_status
~~~

Trong ví dụ này:

- **code** là PK, không dùng auto-increment.
- **display_name** có thể được sửa mà không ảnh hưởng tham chiếu.
- **sort_order** chỉ phục vụ hiển thị, **không** được dùng làm định danh.
- **active** thể hiện có còn cho phép chọn cho dữ liệu **mới** hay không. Nó không có nghĩa phải xóa các bản ghi lịch sử đang dùng code đó.

Rollback dropTable chỉ là minh họa khi mới tạo và chưa phát sinh tham chiếu. Sau khi bảng đã được nhiều đối tượng FK tham chiếu hoặc chứa dữ liệu sản xuất, không được xem DROP TABLE là cách rollback an toàn mặc định.

### Quy tắc khóa ngoại

Giả sử bảng app.payment có cột status_code VARCHAR(24). Khi đã kiểm chứng dữ liệu, có thể thêm FK:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-002-payment-status-fk"
      author: "team-db"
      changes:
        - addForeignKeyConstraint:
            baseTableSchemaName: app
            baseTableName: payment
            baseColumnNames: status_code
            referencedTableSchemaName: app
            referencedTableName: payment_status
            referencedColumnNames: code
            constraintName: fk_payment_payment_status
      rollback:
        - dropForeignKeyConstraint:
            baseTableSchemaName: app
            baseTableName: payment
            constraintName: fk_payment_payment_status
~~~

Ví dụ giả định payment và status_code đã được tạo đúng kiểu ở bước trước. Không chạy changeset FK trước khi bảng/cột đích và dữ liệu đã sẵn sàng. Việc kiểm tra code hợp lệ ở ứng dụng vẫn cần thiết, nhưng FK giúp ngăn các giá trị tham chiếu không tồn tại khi dữ liệu đi vào database từ bất kỳ client nào.

## 6. Seed bằng Liquibase: cấp cùng code ở mọi môi trường

Một changeset có thể thêm các giá trị chuẩn sau khi bảng tồn tại:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-003-seed-payment-status-v1"
      author: "team-db"
      comment: "Cấp ba mã trạng thái thanh toán chuẩn"
      preConditions:
        - onFail: HALT
        - tableExists:
            schemaName: app
            tableName: payment_status
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM app.payment_status
              WHERE code IN ('PENDING', 'SUCCEEDED', 'FAILED')
      changes:
        - insert:
            schemaName: app
            tableName: payment_status
            columns:
              - column:
                  name: code
                  value: PENDING
              - column:
                  name: display_name
                  value: "Chờ xử lý"
              - column:
                  name: sort_order
                  valueNumeric: 10
              - column:
                  name: active
                  valueBoolean: true
        - insert:
            schemaName: app
            tableName: payment_status
            columns:
              - column:
                  name: code
                  value: SUCCEEDED
              - column:
                  name: display_name
                  value: "Thành công"
              - column:
                  name: sort_order
                  valueNumeric: 20
              - column:
                  name: active
                  valueBoolean: true
        - insert:
            schemaName: app
            tableName: payment_status
            columns:
              - column:
                  name: code
                  value: FAILED
              - column:
                  name: display_name
                  value: "Thất bại"
              - column:
                  name: sort_order
                  valueNumeric: 30
              - column:
                  name: active
                  valueBoolean: true
      rollback:
        - delete:
            schemaName: app
            tableName: payment_status
            where: "code IN ('PENDING', 'SUCCEEDED', 'FAILED')"
~~~

**Lưu ý:** bảng phải có schema app, Liquibase được chạy sau changeset tạo bảng và chưa có các code trên. Precondition `sqlCheck` yêu cầu tất cả ba code đều chưa xuất hiện, nếu chỉ một code đã tồn tại thì dừng để điều tra thay vì bỏ qua hay cố chèn phần còn lại. Đây là chính sách **fail-fast** khi nghi ngờ seed thủ công hoặc migration một phần.

Rollback DELETE được trình bày để minh họa cú pháp; **không áp dụng tùy tiện** sau khi payment đang tham chiếu các trạng thái. FK có thể ngăn DELETE, hoặc nếu không có FK thì việc xóa có thể để lại dữ liệu mồ côi. Trên production có dữ liệu phát sinh, kế hoạch sửa tiến hoặc giữ lại các mã đã tham chiếu thường an toàn hơn.

### Vì sao seed có code, không chỉ có id tự tăng?

Nếu chỉ `INSERT (display_name)` và để DB tự sinh id, có thể xảy ra:

~~~text
development:  id=1 -> PENDING;   id=2 -> SUCCEEDED
staging:      id=7 -> PENDING;   id=8 -> SUCCEEDED
production:   id=2 -> PENDING;   id=5 -> SUCCEEDED
~~~

Câu SQL của ứng dụng `WHERE status_id = 2` có thể có nghĩa khác nhau ở từng môi trường. Dùng `WHERE code = 'SUCCEEDED'` tránh nhầm lẫn này khi code đã được định nghĩa thống nhất.

Không dùng `ORDER BY id` hoặc vị trí thứ n trong file CSV để suy ra code. Muốn sắp xếp UI thì dùng `sort_order` và có thứ tự phụ theo code nếu cần.

## 7. Thay nhãn và bổ sung code: viết changeset mới

Sau khi seed v1 đã triển khai, không sửa lại changeset cũ chỉ để đổi nhãn "Thành công" thành "Đã thanh toán". Việc sửa source của changeset đã chạy có thể làm checksum MD5SUM khác hoặc khiến nội dung nguồn không còn đại diện cho lịch sử đã phê duyệt.

Thay vào đó, tạo changeset mới:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261120-001-update-succeeded-label"
      author: "team-db"
      comment: "Đổi nhãn hiển thị, giữ nguyên khóa SUCCEEDED"
      preConditions:
        - onFail: HALT
        - sqlCheck:
            expectedResult: "1"
            sql: |
              SELECT COUNT(*) FROM app.payment_status
              WHERE code = 'SUCCEEDED'
      changes:
        - update:
            schemaName: app
            tableName: payment_status
            columns:
              - column:
                  name: display_name
                  value: "Đã thanh toán"
            where: "code = 'SUCCEEDED'"
      rollback:
        - update:
            schemaName: app
            tableName: payment_status
            columns:
              - column:
                  name: display_name
                  value: "Thành công"
            where: "code = 'SUCCEEDED'"
~~~

Giá trị `SUCCEEDED` ở cột code **không đổi**. Lưu ý rollback cập nhật lại một nhãn cố định có thể ghi đè chỉnh sửa hợp lệ được thực hiện sau migration; chỉ dùng khi quản trị dữ liệu tham chiếu đảm bảo không có thay đổi ngoài kế hoạch và đã xem xét trạng thái hiện tại.

Muốn thêm trạng thái CANCELED, dùng một changeset `insert` mới có code CANCELED, có kiểm tra code chưa tồn tại. Không sửa changeset seed v1 hoặc chèn lại toàn bộ danh sách trạng thái chỉ để thêm một dòng.

Khi một code không còn được phép tạo cho giao dịch mới, thường phù hợp hơn khi chuyển **active=false** hoặc thiết lập trạng thái deprecated. Không xóa code mà các payment lịch sử vẫn đang tham chiếu.

## 8. loadData và loadUpdateData với danh mục lớn

Với danh mục có nhiều hàng như mã quốc gia, đơn vị hành chính hoặc hàng trăm lý do nghiệp vụ, viết từng `insert` có thể khó bảo trì. Liquibase cung cấp change type:

- **loadData:** đọc dữ liệu từ tệp được hỗ trợ (thường là CSV) và chèn vào bảng. Nó không tự bảo đảm thao tác cập nhật/bổ sung theo code.
- **loadUpdateData:** dùng cột hoặc tổ hợp cột khóa được khai báo để cập nhật dòng đã có hoặc chèn dòng chưa có, tùy khả năng và cách thực thi của phiên bản/DBMS.

Ví dụ nội dung tệp CSV **minh họa** (không phải file cần tạo trong bài này):

~~~csv
code,display_name,sort_order,active
PENDING,Chờ xử lý,10,true
SUCCEEDED,Thành công,20,true
FAILED,Thất bại,30,true
CANCELED,Đã hủy,40,true
~~~

Ví dụ changelog tham chiếu đến tệp dữ liệu **đã được quản lý phiên bản**:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261121-001-sync-payment-status-v2"
      author: "team-db"
      changes:
        - loadUpdateData:
            schemaName: app
            tableName: payment_status
            file: payment-status-v2.csv
            relativeToChangelogFile: true
            primaryKey: code
            separator: ","
            encoding: UTF-8
~~~

Trong ví dụ, file được đặt cùng thư mục với changelog chứa changeset. Tên `primaryKey` tại loadUpdateData biểu thị **cột dùng làm khóa đối chiếu dữ liệu**, không phải một yêu cầu tự tạo PRIMARY KEY trong schema.

Các điểm quan trọng:

1. **Tệp CSV phải là dữ liệu được kiểm soát bằng Git/artifact**, không thay đổi bí mật trên runner.
2. **primaryKey phải dựa trên code ổn định**, không dùng label hay thứ tự dòng.
3. **Một changeset đã chạy thường không tự chạy lại** chỉ vì cùng tệp CSV có giá trị mới. Khi cần bản cập nhật tiếp theo, dùng **changeset/tệp dữ liệu phiên bản mới**.
4. Không dùng `runAlways` hoặc `runOnChange` mặc định cho mọi seed: nó có thể ghi đè dữ liệu đang được vận hành quản lý hoặc làm khó rollback.
5. loadUpdateData có thể cập nhật nhiều cột, vì vậy chỉ đưa vào CSV những thuộc tính thật sự do migration sở hữu.
6. Với tệp có dấu phẩy trong nhãn, chuỗi quote, encoding hoặc NULL, phải kiểm thử parser trên file thật và phiên bản Liquibase đang dùng.
7. Không mặc định có rollback tự động để khôi phục toàn bộ giá trị cũ; thao tác cập nhật hàng loạt cần kế hoạch rollback/forward fix riêng.

Nếu một bảng reference data có thể thay đổi bởi người dùng hoặc hệ thống bên ngoài, áp dụng loadUpdateData lặp lại có nguy cơ ghi đè thay đổi hợp lệ. Hãy xác định **nguồn sự thật** và quyền sở hữu từng cột trước khi chọn cách đồng bộ.

## 9. Định danh trên nhiều môi trường: không dựa vào auto-increment

Với surrogate ID là khóa vật lý, một cách an toàn để chèn dữ liệu tham chiếu vào bảng khác là **giải quyết ID bằng code ngay tại database đích**.

Giả sử:

~~~text
payment_status(id, code UNIQUE, display_name)
payment(id, status_id FK -> payment_status.id)
~~~

Tránh seed:

~~~sql
-- Không an toàn nếu id=2 khác nhau giữa các database.
INSERT INTO app.payment (id, status_id)
VALUES (9001, 2);
~~~

Thay vào đó, với PostgreSQL:

~~~sql
INSERT INTO app.payment (id, status_id)
SELECT 9001, ps.id
FROM app.payment_status AS ps
WHERE ps.code = 'SUCCEEDED';
~~~

Cách này dựa vào business key để tìm ID địa phương. Nhưng nếu code SUCCEEDED không tồn tại, `INSERT ... SELECT` có thể không chèn hàng nào mà không phát ra lỗi như mong muốn; vì vậy pipeline phải **kiểm chứng danh mục đã có đúng giá trị bắt buộc** trước khi thực thi và kiểm tra số hàng tác động.

Với FK số, application service cũng nên tìm ID theo code hoặc cache một mapping `code -> id` được nạp từ database hiện tại, **không hard-code id** trong mã nguồn, file JSON hay message giữa các hệ thống.

Nếu hai dịch vụ chia sẻ message `statusId: 2` và hai database không dùng chung registry ID, không có bảo đảm nghĩa là SUCCEEDED. Truyền `statusCode: "SUCCEEDED"` thường ổn định và dễ audit hơn.

## 10. Migrating từ khóa số cũ sang code ổn định

Một hệ thống kế thừa có thể có:

~~~text
legacy_payment_status
id   code          name
4    PENDING       Chờ xử lý
7    SUCCEEDED     Thành công
9    FAILED        Thất bại

payment
id    legacy_status_id
501   7
502   4
~~~

Không được đoán rằng ID 4/7/9 ở production giống development. Việc chuyển đổi cần dựa vào một **bảng ánh xạ được kiểm chứng tại chính database đích**.

### Pha 1 — Expand

Tạo bảng payment_status mới có code ổn định và seed danh mục chuẩn. Bổ sung payment.status_code kiểu VARCHAR(24), cho phép NULL để không làm hỏng các hàng hiện có hoặc writer cũ. Chưa xóa legacy_status_id.

### Pha 2 — Kiểm toán ánh xạ

Kiểm tra sự trùng/mất code trong bảng kế thừa:

~~~sql
SELECT code, COUNT(*)
FROM app.legacy_payment_status
GROUP BY code
HAVING COUNT(*) > 1;

SELECT p.legacy_status_id, COUNT(*) AS row_count
FROM app.payment p
LEFT JOIN app.legacy_payment_status s
  ON s.id = p.legacy_status_id
WHERE s.id IS NULL
GROUP BY p.legacy_status_id;
~~~

Hai truy vấn đầu kiểm tra code trùng và payment tham chiếu một legacy ID không tồn tại. Cần kiểm tra tiếp các code cũ có hợp với danh sách chuẩn không:

~~~sql
SELECT DISTINCT s.code
FROM app.legacy_payment_status s
LEFT JOIN app.payment_status t
  ON t.code = s.code
WHERE t.code IS NULL;
~~~

Nếu code cũ có khác biệt như SUCCESS so với SUCCEEDED, cần lập **quy tắc ánh xạ có phê duyệt**, không tự đổi bằng heuristic hoặc so khớp gần đúng từ nhãn hiển thị.

### Pha 3 — Backfill theo khóa ổn định

Ví dụ PostgreSQL, khi legacy_payment_status.code đã được kiểm chứng:

~~~sql
UPDATE app.payment AS p
SET status_code = s.code
FROM app.legacy_payment_status AS s
WHERE p.legacy_status_id = s.id
  AND p.status_code IS NULL;
~~~

Truy vấn này giải quyết code tại database hiện tại. Nếu hai môi trường dùng ID khác nhau nhưng cùng code, kết quả vẫn nhất quán.

Với bảng lớn, cần chia backfill theo lô, giám sát thời gian lock, WAL/replication, độ trễ và các bản ghi được viết trong lúc backfill. Câu UPDATE toàn bảng chỉ phù hợp minh họa hoặc database nhỏ. Khi còn phiên bản ứng dụng ghi legacy_status_id, phải có chiến lược đồng bộ/dual-write hoặc điều phối đợt phát hành để hai cột không lệch.

### Pha 4 — Kiểm chứng và siết ràng buộc

~~~sql
SELECT COUNT(*) AS missing_status_code
FROM app.payment
WHERE status_code IS NULL;

SELECT COUNT(*) AS invalid_status_code
FROM app.payment p
LEFT JOIN app.payment_status s
  ON s.code = p.status_code
WHERE p.status_code IS NOT NULL
  AND s.code IS NULL;
~~~

Chỉ khi mọi hàng cần thiết đã có code hợp lệ, các writer mới đã chuyển sang code và không còn phát sinh giá trị sai, mới cân nhắc `NOT NULL` và `FOREIGN KEY`. Thời điểm thêm ràng buộc phải phù hợp DBMS, dữ liệu hiện hữu và thời gian khóa bảng.

### Pha 5 — Contract

Khi đã xác minh mã ứng dụng, báo cáo, job và consumer không dùng legacy_status_id, có thể tạo một changeset riêng để gỡ cột cũ. Đây là mốc phá tương thích và có thể khiến rollback về ứng dụng cũ khó thực hiện. Không xóa bảng mapping/ID cũ ngay khi backfill vừa kết thúc.

**Expand–migrate–contract** giúp hệ thống hỗ trợ phiên bản cũ và mới trong thời gian chuyển đổi. Việc dùng code ổn định không loại bỏ nhu cầu tương thích trong rolling deployment.

## 11. Tiền điều kiện và hành vi khi dữ liệu không đồng nhất

Precondition giúp mô tả giả định trước một changeset. Ví dụ seed chỉ được chạy khi bảng đã tồn tại và code PENDING chưa có:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-004-add-pending-if-absent"
      author: "team-db"
      preConditions:
        - onFail: HALT
        - tableExists:
            schemaName: app
            tableName: payment_status
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*) FROM app.payment_status
              WHERE code = 'PENDING'
      changes:
        - insert:
            schemaName: app
            tableName: payment_status
            columns:
              - column:
                  name: code
                  value: PENDING
              - column:
                  name: display_name
                  value: "Chờ xử lý"
              - column:
                  name: sort_order
                  valueNumeric: 10
              - column:
                  name: active
                  valueBoolean: true
~~~

Đây là một ví dụ độc lập để minh họa precondition, **không được chạy nối tiếp seed v1 ở phần 6** trên cùng database vì code PENDING khi ấy đã tồn tại.

Các lựa chọn xử lý cần phân biệt:

- `HALT`: dừng và yêu cầu điều tra nếu giả định không đúng.
- `CONTINUE`: bỏ qua changeset ở lần chạy hiện tại (với precondition cấp changeset).
- `MARK_RAN`: đánh dấu changeset đã chạy dù không thực thi thay đổi (với precondition cấp changeset).

Với **reference data chuẩn**, dùng MARK_RAN chỉ vì code đã tồn tại có thể che dữ liệu sai: cùng code nhưng nhãn, trạng thái hoặc ý nghĩa khác. Trước khi chấp nhận bản ghi đã tồn tại, phải so sánh những cột do migration quản lý và mục đích nghiệp vụ của code. Khi nghi ngờ drift, fail-fast thường dễ kiểm toán hơn tự bỏ qua.

Precondition chỉ phản ánh trạng thái tại thời điểm được kiểm tra. Nếu hai quy trình khác cùng seed một code, UNIQUE/PK trên code vẫn là bảo vệ ở cấp database; không trông chờ precondition tự giải quyết race condition.

## 12. Chọn cách cập nhật reference data theo vòng đời

Không phải mọi loại thay đổi dữ liệu tham chiếu đều giống nhau:

| Thay đổi | Khuyến nghị | Lý do |
|---|---|---|
| Thêm mã mới | Changeset INSERT mới hoặc CSV phiên bản mới | Giữ lịch sử rõ và không đổi code cũ |
| Sửa nhãn hiển thị | UPDATE theo code, không đổi khóa | Giữ tham chiếu và event hiện hành |
| Đổi sort_order | UPDATE theo code | Sort order không phải định danh |
| Ngừng dùng mã | Đặt active=false/deprecated=true và kiểm soát writer | Giữ lịch sử và các FK cũ |
| Xóa mã có dữ liệu tham chiếu | Tránh DELETE; lập kế hoạch chuyển đổi | Tránh mất dữ liệu hoặc vi phạm FK |
| Đổi nghĩa hoặc tách mã | Tạo code mới, migration dữ liệu có kiểm chứng | Không tái sử dụng định danh cho nghĩa khác |
| Gộp mã | Tạo quy tắc ánh xạ, backfill FK/code, giữ alias nếu cần | Không thể chỉ đổi nhãn rồi coi là gộp |
| Đổi kiểu khóa | Expand–migrate–contract | Tránh chặn phiên bản ứng dụng cũ |
| Khác biệt theo tenant/môi trường | Định nghĩa phạm vi và nguồn dữ liệu rõ ràng | Không làm code toàn hệ thống mang nghĩa khác nhau |

Ví dụ SUCCEEDED từng có nghĩa "giao dịch được ghi nhận", nhưng nay cần phân biệt CAPTURED và SETTLED. Không nên đổi nghĩa SUCCEEDED theo phiên bản mới. Có thể tạo hai code mới, xác định ánh xạ lịch sử và giai đoạn tương thích với client đã dùng SUCCEEDED.

Nếu sản phẩm có tập trạng thái mở rộng theo từng khách hàng, tách danh mục **chuẩn của sản phẩm** khỏi các mục **do tenant quản lý**. Hai loại có quyền sở hữu, quy tắc seed và vòng đời khác nhau.

## 13. Localization: nhãn thay đổi, khóa không đổi

Một lỗi phổ biến là dùng chuỗi hiển thị làm khóa:

~~~text
"Chờ xử lý" -> "Waiting" -> "Pending"
~~~

Nhãn dịch có thể đổi theo ngôn ngữ hoặc cách viết UI. Nếu dùng nhãn làm PK/FK, mỗi lần sửa bản dịch trở thành migration định danh đầy rủi ro.

Thay vào đó:

~~~text
payment_status
code
PENDING
SUCCEEDED
FAILED

payment_status_translation
status_code   locale   display_name
PENDING       vi       Chờ xử lý
PENDING       en       Pending
SUCCEEDED     vi       Thành công
SUCCEEDED     en       Succeeded
~~~

Ở bảng translation, khóa có thể là **(status_code, locale)**, và status_code tham chiếu payment_status.code. UI chọn nhãn theo locale, API/event truyền code. Việc sửa một bản dịch không làm thay đổi danh tính trạng thái.

Không dùng `sort_order`, `display_name` hoặc `locale` đơn lẻ làm khóa nhận diện status. Nếu danh mục vừa có nhãn mặc định vừa có translation, cần xác định một nguồn có thẩm quyền để tránh hai cách dịch bị lệch.

## 14. Nhiều tenant, nhiều phiên bản và khóa tổng hợp

Nếu một danh mục chung cho mọi tenant, có thể dùng code là khóa toàn hệ thống. Nhưng nếu mỗi tenant tự định nghĩa một nhóm lý do hoặc trạng thái tùy chỉnh, code CUSTOM_1 có thể tồn tại ở hai tenant với ý nghĩa khác nhau.

Khi đó, định danh ổn định có thể là **(tenant_id, code)** thay vì chỉ code, hoặc dùng ID nội bộ và UNIQUE(tenant_id, code). Cần bảo đảm:

- Bảng giao dịch tham chiếu cùng tenant với bản ghi danh mục.
- API/event mang đủ thông tin phạm vi (tenant và code) nếu code không toàn cục.
- Migration seed tập giá trị chuẩn không ghi đè các mục do tenant tự quản lý.
- Ràng buộc UNIQUE được đặt đúng phạm vi.
- Rollback không xóa nhầm dữ liệu thuộc tenant khác.

Tương tự, một mã có thể thay đổi định nghĩa theo **thời gian hiệu lực**. Nếu nghiệp vụ cần audit chính xác ý nghĩa tại thời điểm giao dịch, nên dùng bảng version/effective date hoặc lưu snapshot thích hợp, chứ không sửa ý nghĩa của code cũ rồi mất lịch sử.

Trong đa dịch vụ, đừng mặc định database nội bộ của mọi service đều dùng cùng surrogate ID. Hợp đồng liên dịch vụ nên quy định code, phiên bản schema sự kiện và cách xử lý code chưa biết.

## 15. Ứng dụng Java/Spring Boot nên tham chiếu theo code

Trong Java, có thể biểu diễn tập mã chuẩn bằng enum:

~~~java
public enum PaymentStatusCode {
    PENDING,
    SUCCEEDED,
    FAILED,
    CANCELED
}
~~~

Nhưng cần hiểu enum chỉ là **mô hình trong mã ứng dụng**; bản ghi tham chiếu vẫn phải được migration seed đúng. Nếu ứng dụng phát hành code CANCELED trước khi database có giá trị đó và FK/logic validation yêu cầu tham chiếu, request ghi trạng thái mới có thể thất bại.

Một mô hình entity theo code:

~~~java
@Entity
@Table(name = "payment_status", schema = "app")
public class PaymentStatus {
    @Id
    @Column(name = "code", length = 24, nullable = false)
    private String code;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    @Column(name = "active", nullable = false)
    private boolean active;
}
~~~

Nếu bảng payment dùng status_code, có thể lưu mã string ổn định hoặc mapping quan hệ tới PaymentStatus. Cần quyết định rõ ai được phép sửa danh mục trong runtime: nếu do Liquibase sở hữu, tránh cung cấp API quản trị cho phép xóa/đổi code tùy ý.

Với Spring Boot, có thể bật Liquibase:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Spring Boot chạy Liquibase dựa trên cấu hình ứng dụng, nhưng việc nhiều instance khởi động không tự bảo đảm **thời điểm code mới dùng mã mới**. Trong hệ thống cần rolling deployment, thường phải đảm bảo changeset bổ sung code đã được áp dụng trước khi bật logic ghi code mới; với việc loại bỏ code, phải chờ mọi writer/consumer cũ ngừng sử dụng.

Đừng dùng `Enum.ordinal()` để ghi ID tham chiếu: thứ tự enum có thể thay đổi khi thêm/xóa/hợp nhất giá trị. Nếu serialize enum, dùng tên code ổn định hoặc lớp mapping tường minh, có kiểm thử tương thích và xử lý code chưa biết.

## 16. Checksum và lịch sử: tránh sửa seed đã chạy

Liquibase nhận diện changeset bằng **ID + AUTHOR + FILENAME**, lưu các thông tin thực thi vào DATABASECHANGELOG, bao gồm MD5SUM để phát hiện thay đổi nội dung.

Vòng đời chuẩn:

1. Changeset v1 tạo bảng payment_status.
2. Changeset v2 seed PENDING, SUCCEEDED, FAILED.
3. Changeset v3 thêm CANCELED.
4. Changeset v4 thay nhãn SUCCEEDED.
5. Changeset v5 đánh dấu một code không còn cho phép sử dụng mới.

Không quay lại sửa changeset v2 sau khi đã chạy để thêm CANCELED. Sửa source migration lịch sử có thể gây lỗi checksum, làm staging/production nhìn thấy artifact khác và khiến việc audit không còn nhất quán.

**runOnChange**, **runAlways**, **validCheckSum** và **clear-checksums** có các mục đích riêng; không sử dụng như phương án mặc định để seed lại danh mục mỗi lần deploy. Một seed chạy lại có thể ghi đè dữ liệu không thuộc quyền quản lý của Liquibase hoặc làm thay đổi giá trị mà ứng dụng đang dùng.

Nếu một database có bản ghi mã SUCCEEDED nhưng không có lịch sử seed tương ứng, đừng tự sửa DATABASECHANGELOG để đánh dấu hoàn thành. Phải đối chiếu trạng thái dữ liệu, quyền sở hữu và quy trình baseline/chuyển đổi có kiểm chứng.

## 17. Rollback reference data khó hơn rollback DDL đơn giản

Có ba nhóm thao tác và rủi ro khác nhau:

**INSERT code mới:** rollback DELETE có thể thất bại khi FK đã tham chiếu; nếu database không có FK, DELETE có thể để lại giao dịch với code không còn trong danh mục.

**UPDATE nhãn/sort_order/active:** rollback khôi phục giá trị cũ trong changeset có thể được định nghĩa tường minh, nhưng phải kiểm tra có sự thay đổi hợp lệ nào xảy ra sau đó không.

**Chuyển tham chiếu từ code cũ sang code mới:** rollback phải biết ánh xạ một-một, nhiều-một hay mất thông tin; khi gộp code, phép đảo ngược có thể **không xác định** nếu không lưu dữ liệu gốc.

Ví dụ gộp LEGACY_OK và LEGACY_SUCCESS vào SUCCEEDED, sau đó chỉ lưu SUCCEEDED trong payment. Nếu không lưu mã gốc, không thể biết mỗi hàng trước đây thuộc code nào để rollback đúng. Cần migration ghi mapping/audit hoặc có kế hoạch forward fix thay vì hứa hẹn rollback hoàn toàn.

Các nguyên tắc:

- Không xóa code khi còn dữ liệu tham chiếu.
- Review `rollback-sql` nếu công cụ/phiên bản hỗ trợ và kiểm tra DBMS đích.
- Thử rollback trên dữ liệu đại diện, không chỉ database vừa khởi tạo.
- Xác định thời điểm không còn thể quay lại phiên bản ứng dụng cũ.
- Chuẩn bị backup/restore, audit mapping, checkpoint hoặc phương án sửa tiến cho chuyển đổi không đảo ngược.
- Không coi onFail: MARK_RAN là rollback hoặc cách sửa chênh lệch dữ liệu.

Với code đang được dùng trong production, **giữ code và ngừng sử dụng cho dữ liệu mới** thường an toàn hơn DELETE.

## 18. Quy trình CI/CD và kiểm chứng đa môi trường

Một pipeline cần coi reference data là một phần của contract phát hành:

1. Chọn đúng database, schema, credentials và phiên bản Liquibase.
2. Đọc các changeset mới và danh sách code được thêm/sửa/không còn dùng.
3. Kiểm tra tên code có trùng, sai quy ước hoặc đổi ý nghĩa không.
4. Kiểm tra những code bắt buộc của phiên bản ứng dụng mới.
5. Chạy Liquibase validate, status và update-sql trên môi trường kiểm thử.
6. Kiểm tra generated SQL, điều kiện dữ liệu hiện có và tác động lên FK.
7. Chạy update theo thứ tự đã phê duyệt; dữ liệu chuẩn cần có trước khi code mới sử dụng.
8. Kiểm tra DATABASECHANGELOG, code thực tế và các bản ghi tham chiếu.
9. Chạy integration test qua API, job, message consumer và code mapping.
10. Promote **cùng artifact/changelog đã kiểm thử** lên môi trường tiếp theo.

Lệnh Liquibase CLI khi đã cấu hình kết nối và changelog:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql

# Chỉ triển khai sau khi xác nhận database đích và review SQL:
liquibase update
liquibase history
~~~

SQL kiểm tra danh mục sau chạy:

~~~sql
SELECT code, display_name, sort_order, active
FROM app.payment_status
ORDER BY sort_order, code;

SELECT COUNT(*) AS broken_references
FROM app.payment p
LEFT JOIN app.payment_status s
  ON s.code = p.status_code
WHERE p.status_code IS NOT NULL
  AND s.code IS NULL;
~~~

Nếu danh mục là nguồn sự thật chung của sản phẩm, các môi trường có thể được so sánh **tập code và định nghĩa chuẩn**. Tuy nhiên, các môi trường khác nhau có thể có dữ liệu thử nghiệm hoặc trạng thái rollout khác nhau; cần xác định phạm vi so sánh và không dùng kiểm tra byte-to-byte mù quáng cho toàn bộ database.

Trong CI/CD, không hard-code credentials hoặc URL trong changelog. Nếu dùng Spring Boot startup migration, DATABASECHANGELOGLOCK chỉ điều phối Liquibase, không bảo đảm một phiên bản ứng dụng cũ đã ngừng dùng mã deprecated. Cổng phát hành phải kiểm soát thứ tự cập nhật dữ liệu tham chiếu và chuyển đổi mã ứng dụng.

## 19. Chẩn đoán các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
|---|---|---|
| Cùng code có ID khác nhau giữa môi trường | Dùng auto-increment hoặc dữ liệu đã seed theo thứ tự khác | Dùng code làm khóa trao đổi; tra ID theo code ở database đích |
| FK tới status_id sai nghĩa | Hard-code ID số hoặc ánh xạ sai | Rà soát mapping, backfill theo code và xác minh dữ liệu |
| Seed v2 lỗi trùng khóa | Code đã có do thao tác thủ công hoặc changeset khác | Đối chiếu trạng thái dữ liệu và lịch sử; không MARK_RAN tự động |
| Code PENDING bị đổi thành DONE | Đã dùng nhãn/ý nghĩa mới như một định danh cũ | Giữ code cũ hoặc triển khai code mới với migration tương thích |
| Data load chạy lại làm mất nhãn | Dùng runAlways/loadUpdateData không kiểm soát nguồn sự thật | Tách cột do migration quản lý, version file và tạo changeset mới |
| Production lỗi với code mới | Ứng dụng phát hành trước khi seed code vào DB | Sắp xếp rollout, kiểm tra danh mục và code mapping |
| Không thể DELETE code deprecated | Còn FK từ giao dịch lịch sử | Giữ mã với active=false hoặc lập kế hoạch chuyển tham chiếu |
| Rollback đổi code không khôi phục được | Migration gộp nhiều code thành một, mất dữ liệu gốc | Lưu mapping/audit trước chuyển đổi hoặc dùng forward fix |
| CSV tiếng Việt bị sai ký tự | Encoding, quoting hoặc separator không khớp | Khai báo UTF-8, kiểm tra parser và nội dung trong DB |
| Cùng mã nhưng tên hiển thị khác | Nhãn do runtime tự sửa hoặc quy tắc i18n khác | Xác định quyền sở hữu nhãn, dùng bảng translation |
| Dữ liệu kế thừa có nhiều mã trùng | Không có UNIQUE(code) hoặc dữ liệu bị drift | Audit, chuẩn hóa mapping, thêm constraint sau khi làm sạch |
| Status enum hoạt động ở dev nhưng lỗi staging | Mã chỉ seed ở dev hoặc cấu hình context sai | Kiểm tra code bắt buộc, context/labels và DATABASECHANGELOG |

Khi gặp lỗi, phân biệt lỗi **kết nối/changelog**, lỗi **định danh changeset**, lỗi **khóa tham chiếu**, lỗi **ngữ nghĩa mã** và lỗi **quy trình rollout**. Một hàng đã xuất hiện trong DATABASECHANGELOG không tự chứng minh dữ liệu tham chiếu trên database không bị sửa ngoài Liquibase sau đó.

## 20. Bài thực hành: giữ nghĩa của status qua hai database

**Bài toán:** hai database thử nghiệm A và B cùng dùng ứng dụng thanh toán. Trong hệ thống cũ, ID số của trạng thái khác nhau giữa A và B. Cần tạo danh mục chuẩn payment_status và chuyển app.payment sang status_code bất biến.

### Chuẩn bị

- Hai database thử nghiệm có dữ liệu gần giống nhưng có thể khác surrogate ID.
- Một changelog dùng chung với các code PENDING, SUCCEEDED, FAILED.
- Quyền đọc metadata, chạy migration và kiểm tra dữ liệu.
- Kế hoạch rollback/backfill phù hợp; chỉ thử thao tác phá dữ liệu trong database có thể khôi phục.

### Thực hiện

1. Đọc cấu trúc legacy_payment_status và payment trên từng database; ghi lại ID/code tương ứng.
2. Chạy SQL audit tìm code trùng và giao dịch mồ côi.
3. Tạo bảng payment_status với PK code, seed ba giá trị bằng changeset.
4. Chạy validate và update-sql; xác nhận code được chèn **giống nhau** ở A và B.
5. Thêm payment.status_code nullable.
6. Backfill code từ bảng legacy bằng join theo ID **chỉ trong database đích**; không mang ID của A sang B.
7. Kiểm tra số payment thiếu status_code hoặc tham chiếu code không có trong danh mục.
8. Đổi mã ứng dụng để dùng status_code; thử đọc/ghi và xử lý sự kiện với code.
9. Sau khi không còn writer dùng ID cũ, cân nhắc FK, NOT NULL và contract trong changeset riêng.
10. Thêm CANCELED ở một changeset mới; xác nhận hai database thấy cùng code nhưng không cần cùng ID số.
11. Thử đổi nhãn SUCCEEDED bằng changeset UPDATE theo code; xác nhận dữ liệu payment không bị thay đổi.
12. Xem xét rollback của việc thêm CANCELED sau khi có payment dùng code này. Giải thích vì sao DELETE không còn là thao tác an toàn.

### Câu hỏi tự kiểm tra

- Nếu status SUCCEEDED có id=7 ở A và id=42 ở B, có thể truyền id=7 qua API chung không? **Không**, trừ khi có registry ID chung và hợp đồng ràng buộc rõ. Thông thường truyền code.
- Nếu đổi display_name từ "Thành công" sang "Đã thanh toán", có cần đổi code SUCCEEDED không? **Không.**
- Có nên seed `status_id=1` vì PENDING luôn nằm đầu CSV? **Không**; thứ tự hàng không phải danh tính.
- Nếu một code không còn dùng, có nên xóa ngay? **Không** khi giao dịch lịch sử còn tham chiếu nó.
- Nếu muốn phát hành code CANCELED, dữ liệu hay ứng dụng nên sẵn sàng trước? **Seed giá trị và các schema cần thiết trước**, sau đó bật đường ghi mã mới theo kế hoạch tương thích.
- Nếu gộp hai mã khác nhau vào SUCCEEDED, có tự rollback chính xác không? **Không** nếu không giữ ánh xạ dữ liệu nguồn.

## 21. Checklist review dữ liệu tham chiếu có khóa ổn định

- [ ] Đã xác định dữ liệu thực sự là reference data do phiên bản ứng dụng quản lý.
- [ ] Mỗi mã có định nghĩa nghiệp vụ, phạm vi duy nhất và người sở hữu.
- [ ] Không dùng nhãn, thứ tự hiển thị hoặc ID tự tăng ngẫu nhiên làm khóa trao đổi liên môi trường.
- [ ] Đã cân nhắc code làm PK so với surrogate ID + UNIQUE(code).
- [ ] Code bất biến về nghĩa, không tái sử dụng code đã ngừng hoạt động.
- [ ] Bảng reference có PK/UNIQUE và bảng tham chiếu có FK tương ứng.
- [ ] Đã kiểm tra code trùng, dữ liệu mồ côi và mapping từ hệ thống cũ.
- [ ] Seed được quản lý bằng changeset có id, author, filename ổn định.
- [ ] Không sửa changeset seed đã chạy; mọi thay đổi dùng changeset mới hoặc file dữ liệu phiên bản mới.
- [ ] loadUpdateData dùng khóa đối chiếu là code thực sự ổn định và có nguồn dữ liệu rõ ràng.
- [ ] Nhãn đa ngôn ngữ được tách khỏi code; sort_order không phải khóa.
- [ ] Với mã deprecated, giữ khả năng đọc dữ liệu lịch sử.
- [ ] Đã thiết kế mở rộng/backfill/siết ràng buộc/contract cho migration từ ID cũ sang code.
- [ ] Đã đánh giá khả năng backfill theo lô, dual-write và phát hành nhiều phiên bản ứng dụng.
- [ ] Không hard-code surrogate ID vào enum Java, message hoặc code tích hợp.
- [ ] Có kế hoạch rollback/forward fix khi thêm, cập nhật, ngừng hoặc gộp mã.
- [ ] Đã kiểm tra checksum, DATABASECHANGELOG và code thực tế sau migration.
- [ ] Có cổng kiểm tra reference data trong Spring Boot hoặc CI/CD trước khi bật logic dùng code mới.
- [ ] Cùng artifact/changelog được promote qua các môi trường; secret và thông tin kết nối được quản lý riêng.

**Kết luận:** dữ liệu tham chiếu có khóa ổn định giúp một khái niệm nghiệp vụ giữ nguyên danh tính qua các database, phiên bản mã và lần triển khai. Liquibase cung cấp lịch sử cho việc tạo, seed và thay đổi danh mục; **thiết kế khóa đúng** mới ngăn hệ thống phụ thuộc vào ID sinh ngẫu nhiên hoặc nhãn thay đổi. Khi kết hợp UNIQUE/FK, migration theo changeset bất biến, backfill có kiểm chứng và kế hoạch rollback phù hợp, đội ngũ có thể bảo trì reference data an toàn trên nhiều môi trường cùng Spring Boot và CI/CD.
