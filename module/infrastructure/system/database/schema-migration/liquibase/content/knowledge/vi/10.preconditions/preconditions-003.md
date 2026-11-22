# Kiểm tra bảng, cột, khóa và đối tượng đã tồn tại

Trong chương **Tiền điều kiện** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, một nhiệm vụ thường gặp là quyết định có nên chạy changeset dựa trên trạng thái hiện tại của cơ sở dữ liệu. Liquibase cung cấp **preConditions** để kiểm tra những điều kiện như bảng đã tồn tại hay chưa, cột đã có chưa, khóa chính/khóa ngoại có đúng tên không, chỉ mục, view hoặc sequence có hiện diện không. Đây là lớp bảo vệ hữu ích khi quản lý thay đổi schema và dữ liệu bằng changelog, changeset, checksum và lịch sử triển khai, cũng như khi thiết kế migration có kiểm chứng, rollback và đưa cùng artifact qua các môi trường bằng Spring Boot hoặc CI/CD.

Một precondition không tự sửa database. Nó đưa ra kết quả **đạt**, **không đạt** hoặc **lỗi trong quá trình đánh giá**; Liquibase xử lý kết quả theo chính sách onFail/onError. Muốn dùng an toàn, người viết phải biết rõ mình đang kiểm tra **đối tượng nào, trong schema nào, bằng thuộc tính nào**, và diễn giải đúng việc đối tượng đã tồn tại có thực sự tương đương với trạng thái mong muốn hay không.

## 1. Tại sao cần kiểm tra sự tồn tại trước khi migration?

Xét changeset sau:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-001-create-customer"
      author: "team-db"
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
~~~

Nếu bảng customer đã tồn tại vì một script trước đó, thao tác createTable có thể thất bại. Có thể xảy ra các tình huống:

- Database mới hoàn toàn: bảng chưa tồn tại, changeset cần được thực thi.
- Database đã chạy chính changeset này: Liquibase nhận diện lịch sử trong **DATABASECHANGELOG** và thường không chạy lại changeset.
- Database có bảng customer do thao tác ngoài Liquibase: bảng tồn tại nhưng changeset chưa được ghi nhận.
- Database có bảng cùng tên nhưng cấu trúc khác dự kiến: chỉ kiểm tra tên bảng sẽ không phát hiện khác biệt.
- Database có nhiều schema/tenant: một bảng customer có thể tồn tại ở schema khác, nhưng schema đích lại chưa có.

Precondition giúp người phát triển mô tả giả định của migration và chọn cách ứng xử có chủ đích. Tuy nhiên, kiểm tra tồn tại không thay thế việc đọc **DATABASECHANGELOG**, không chứng minh schema hoàn toàn đúng và không tự đồng bộ lịch sử triển khai.

## 2. Precondition nằm ở đâu và được đánh giá như thế nào?

Precondition có thể được đặt ở phạm vi **changelog** hoặc **changeset**.

Precondition ở cấp changelog đặt điều kiện chung cho việc xử lý changelog. Ví dụ ngăn triển khai trên loại DBMS không phù hợp:

~~~yaml
databaseChangeLog:
  - preConditions:
      - onFail: HALT
      - dbms:
          type: postgresql
  - changeSet:
      id: "20261119-001-create-customer"
      author: "team-db"
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: BIGINT
~~~

Precondition ở cấp changeset gắn trực tiếp với một thay đổi:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-002-add-customer-phone"
      author: "team-db"
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: customer
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: phone
                  type: VARCHAR(30)
~~~

Ở ví dụ thứ hai, điều kiện được dùng để xác nhận bảng customer tồn tại trước khi thêm cột. Nếu bảng không tồn tại, chính sách HALT yêu cầu Liquibase dừng thay vì để câu SQL phát sinh lỗi khó hiểu hơn.

**Thứ tự tư duy:** xác định changeset có thuộc phạm vi cần chạy không, kiểm tra lịch sử để biết nó đã được ghi nhận chưa, rồi kiểm tra precondition liên quan đến lần chạy. Với changeset thông thường đã được ghi nhận, Liquibase không cần thực thi lại chỉ để kiểm tra precondition. Một precondition không phải cơ chế giám sát schema liên tục sau mỗi lần triển khai.

Lưu ý ở cấp changelog, lựa chọn xử lý kết quả thất bại bị giới hạn hơn so với cấp changeset. Các hành vi như MARK_RAN hoặc CONTINUE dành cho precondition ở cấp changeset; không đặt tùy tiện chúng vào precondition toàn cục.

## 3. Các kiểm tra tồn tại tích hợp sẵn

Liquibase có các precondition kiểu schema/object để kiểm tra metadata của database. Những loại thường gặp:

| Precondition | Câu hỏi cần trả lời | Thuộc tính tiêu biểu |
|---|---|---|
| `tableExists` | Bảng đã tồn tại? | `tableName`, `schemaName` |
| `columnExists` | Cột có thuộc bảng? | `tableName`, `columnName`, `schemaName` |
| `primaryKeyExists` | Khóa chính đã tồn tại? | `tableName`, `primaryKeyName`, `schemaName` |
| `foreignKeyConstraintExists` | Khóa ngoại đã tồn tại? | `foreignKeyName`, `foreignKeyTableName`, `schemaName` |
| `uniqueConstraintExists` | Ràng buộc unique đã tồn tại? | `tableName`, `constraintName`, `schemaName` |
| `indexExists` | Chỉ mục đã tồn tại? | `indexName`, `tableName`, `schemaName` |
| `viewExists` | View đã tồn tại? | `viewName`, `schemaName` |
| `sequenceExists` | Sequence đã tồn tại? | `sequenceName`, `schemaName` |

Khả năng hỗ trợ, tên thuộc tính bắt buộc và cách Liquibase truy vấn metadata có thể khác theo phiên bản Liquibase và DBMS. Đối chiếu phiên bản dự án khi cấu hình; một số precondition có thể sử dụng snapshot của database để xác định kết quả, khiến việc kiểm tra tốn chi phí trên schema lớn.

Với các đối tượng không có precondition dựng sẵn phù hợp, chẳng hạn một thuộc tính cụ thể của trigger, function hoặc phân vùng, có thể dùng **sqlCheck** với truy vấn metadata đặc thù DBMS, hoặc sử dụng cơ chế kiểm tra khác được dự án hỗ trợ. Không giả định mọi loại đối tượng đều có sẵn một precondition `xxxExists` tương ứng.

## 4. Kiểm tra bảng bằng tableExists

### Chỉ cho phép tạo bảng khi bảng chưa tồn tại

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-003-create-invoice"
      author: "team-db"
      preConditions:
        - onFail: MARK_RAN
        - not:
            - tableExists:
                schemaName: app
                tableName: invoice
      changes:
        - createTable:
            schemaName: app
            tableName: invoice
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Ở đây, `not` đảo kết quả: nếu bảng chưa tồn tại, precondition đạt và changeset được chạy; nếu bảng đã tồn tại, precondition không đạt. Với `onFail: MARK_RAN`, Liquibase **ghi nhận changeset đã chạy mà không thực thi** createTable. Trong DATABASECHANGELOG, bạn có thể thấy `EXECTYPE=MARK_RAN`.

Chính sách MARK_RAN chỉ hợp lý khi đã có quy trình xác minh rằng bảng tồn tại tương đương với cấu trúc được changeset mong đợi. Nếu bảng chỉ trùng tên nhưng thiếu cột, thiếu khóa hoặc dùng kiểu dữ liệu sai, đánh dấu đã chạy sẽ che lấp **schema drift**. Trong những trường hợp yêu cầu schema phải đúng tuyệt đối, nên `HALT` và điều tra trước.

### Bắt buộc bảng phải tồn tại trước khi sửa

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-004-add-invoice-status"
      author: "team-db"
      preConditions:
        - onFail: HALT
        - tableExists:
            schemaName: app
            tableName: invoice
      changes:
        - addColumn:
            schemaName: app
            tableName: invoice
            columns:
              - column:
                  name: status
                  type: VARCHAR(20)
~~~

Ở ví dụ này, bảng chưa có là **một lỗi phụ thuộc**, không nên đánh dấu thay đổi là đã hoàn thành. HALT giúp ngăn pipeline tiếp tục với schema chưa sẵn sàng.

## 5. Kiểm tra cột bằng columnExists

Một bảng tồn tại chưa đủ để chứng minh rằng cột cần thêm đã vắng mặt. Kết hợp hai điều kiện:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-005-add-customer-phone"
      author: "team-db"
      preConditions:
        - onFail: HALT
        - and:
            - tableExists:
                schemaName: app
                tableName: customer
            - not:
                - columnExists:
                    schemaName: app
                    tableName: customer
                    columnName: phone
      changes:
        - addColumn:
            schemaName: app
            tableName: customer
            columns:
              - column:
                  name: phone
                  type: VARCHAR(30)
      rollback:
        - dropColumn:
            schemaName: app
            tableName: customer
            columnName: phone
~~~

Điều kiện cho phép chạy khi **bảng customer có tồn tại** và **cột phone chưa tồn tại**. Nếu bảng thiếu hoặc cột đã có, onFail: HALT báo rõ giả định không đạt.

Điều này khác với:

~~~yaml
preConditions:
  - onFail: MARK_RAN
  - and:
      - tableExists:
          tableName: customer
      - not:
          - columnExists:
              tableName: customer
              columnName: phone
~~~

Ở ví dụ thứ hai, nếu **bảng customer chưa tồn tại**, toàn bộ điều kiện thất bại và MARK_RAN vẫn ghi nhận changeset là đã chạy, dù cột cũng không tồn tại. Đây là cách dùng dễ gây sai lệch lịch sử. Khi cần những hành vi khác nhau cho từng trường hợp, hãy thiết kế quy trình kiểm tra hoặc chia changeset/điều kiện rõ ràng thay vì áp một chính sách MARK_RAN cho mọi nguyên nhân thất bại.

**columnExists chỉ xác nhận sự hiện diện**, không kiểm tra kiểu VARCHAR(30), độ dài, NULL/NOT NULL, default hoặc collation. Nếu migration phụ thuộc vào các thuộc tính đó, cần kiểm chứng bổ sung qua snapshot/diff, SQL metadata hoặc kiểm tra ứng dụng phù hợp.

## 6. Kiểm tra khóa chính và khóa duy nhất

### Khóa chính với primaryKeyExists

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-006-add-order-pk"
      author: "team-db"
      preConditions:
        - onFail: HALT
        - and:
            - tableExists:
                schemaName: app
                tableName: purchase_order
            - not:
                - primaryKeyExists:
                    schemaName: app
                    tableName: purchase_order
      changes:
        - addPrimaryKey:
            schemaName: app
            tableName: purchase_order
            columnNames: id
            constraintName: pk_purchase_order
      rollback:
        - dropPrimaryKey:
            schemaName: app
            tableName: purchase_order
            constraintName: pk_purchase_order
~~~

Điều kiện đặt mục tiêu tránh thêm một khóa chính khi bảng đã có khóa chính khác. Nếu cần kiểm tra **đúng tên khóa** pk_purchase_order, có thể dùng thuộc tính `primaryKeyName` theo cách DBMS/Liquibase hỗ trợ, nhưng vẫn cần xem xét liệu khóa đó áp dụng đúng cột và đúng thứ tự hay không.

Trước khi thêm primary key, phải kiểm tra dữ liệu: cột khóa có NULL hay giá trị trùng không? Precondition kiểm tra sự **tồn tại** của khóa không tự xác nhận tính sạch của dữ liệu để thêm khóa mới.

### Ràng buộc unique với uniqueConstraintExists

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-007-unique-customer-email"
      author: "team-db"
      preConditions:
        - onFail: HALT
        - not:
            - uniqueConstraintExists:
                schemaName: app
                tableName: customer
                constraintName: uq_customer_email
      changes:
        - addUniqueConstraint:
            schemaName: app
            tableName: customer
            columnNames: email
            constraintName: uq_customer_email
      rollback:
        - dropUniqueConstraint:
            schemaName: app
            tableName: customer
            constraintName: uq_customer_email
~~~

Ở đây, điều kiện kiểm tra **ràng buộc tên uq_customer_email** chưa tồn tại. Nó không chứng minh dữ liệu email không trùng; câu lệnh addUniqueConstraint có thể thất bại nếu đã có dữ liệu vi phạm. Một **unique index** và một **unique constraint** có thể được biểu diễn/kiểm tra khác nhau tùy DBMS. Không nhầm `indexExists` với `uniqueConstraintExists` rồi coi hai điều kiện luôn tương đương.

Cũng cần chú ý tên constraint có thể do DBMS tự sinh, bị đổi chữ hoa/thường hoặc nằm trong schema khác. Khi cần độ chính xác, truy vấn metadata của database để biết tên thực tế trước khi viết precondition.

## 7. Kiểm tra khóa ngoại bằng foreignKeyConstraintExists

Ví dụ bảng invoice có cột customer_id và cần bổ sung khóa ngoại tới bảng customer:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-008-add-invoice-customer-fk"
      author: "team-db"
      preConditions:
        - onFail: HALT
        - and:
            - tableExists:
                schemaName: app
                tableName: invoice
            - tableExists:
                schemaName: app
                tableName: customer
            - columnExists:
                schemaName: app
                tableName: invoice
                columnName: customer_id
            - not:
                - foreignKeyConstraintExists:
                    schemaName: app
                    foreignKeyTableName: invoice
                    foreignKeyName: fk_invoice_customer
      changes:
        - addForeignKeyConstraint:
            baseTableSchemaName: app
            baseTableName: invoice
            baseColumnNames: customer_id
            referencedTableSchemaName: app
            referencedTableName: customer
            referencedColumnNames: id
            constraintName: fk_invoice_customer
      rollback:
        - dropForeignKeyConstraint:
            baseTableSchemaName: app
            baseTableName: invoice
            constraintName: fk_invoice_customer
~~~

Điểm cần đọc kỹ:

- `foreignKeyTableName` chỉ **bảng chứa cột khóa ngoại**, ở đây là invoice; nó không phải bảng được tham chiếu.
- `foreignKeyName` là tên ràng buộc muốn kiểm tra, không phải tên cột customer_id.
- Kiểm tra cả bảng/cột tham gia giúp cung cấp thông báo lỗi sớm hơn nhưng chưa đủ: bảng customer phải có khóa được tham chiếu hợp lệ.
- Dữ liệu invoice.customer_id đang tồn tại phải tương thích với dữ liệu customer.id; nếu có giá trị mồ côi, lệnh thêm foreign key có thể thất bại.

Khi một FK khác tên nhưng có cùng tác dụng đã tồn tại, precondition kiểm tra **tên cụ thể** vẫn có thể cho phép chạy, dẫn tới ràng buộc trùng chức năng hoặc lỗi DBMS. Trong migration nhạy cảm, cần kiểm tra cả tên và định nghĩa thực tế của FK qua metadata/diff.

## 8. Kiểm tra index bằng indexExists

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-009-index-customer-email"
      author: "team-db"
      preConditions:
        - onFail: HALT
        - and:
            - tableExists:
                schemaName: app
                tableName: customer
            - not:
                - indexExists:
                    schemaName: app
                    tableName: customer
                    indexName: ix_customer_email
      changes:
        - createIndex:
            schemaName: app
            tableName: customer
            indexName: ix_customer_email
            columns:
              - column:
                  name: email
      rollback:
        - dropIndex:
            schemaName: app
            tableName: customer
            indexName: ix_customer_email
~~~

`indexExists` giúp tránh tạo một index có tên đã được dùng. Nhưng sự hiện diện của index không bảo đảm nó được tạo trên đúng cột, đúng thứ tự, có UNIQUE hay có biểu thức/điều kiện WHERE như mong muốn. Một số DBMS tự tạo index cho khóa chính/unique; cách biểu diễn metadata cũng khác nhau.

Nếu thay đổi nhằm tối ưu hiệu năng, ngoài việc kiểm tra index tồn tại cần xem kế hoạch truy vấn, kích thước bảng, nguy cơ khóa ghi và hỗ trợ tạo index online/concurrently của DBMS. Những điều này không được precondition tồn tại giải quyết thay.

## 9. Kiểm tra view và sequence

### View với viewExists

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-010-create-customer-view"
      author: "team-db"
      preConditions:
        - onFail: HALT
        - not:
            - viewExists:
                schemaName: app
                viewName: v_customer_email
      changes:
        - createView:
            schemaName: app
            viewName: v_customer_email
            selectQuery: SELECT id, email FROM app.customer
      rollback:
        - dropView:
            schemaName: app
            viewName: v_customer_email
~~~

`viewExists` chỉ xác nhận tên view đã tồn tại. Nếu cần cập nhật định nghĩa view, các lựa chọn như replaceIfExists hoặc changeset phù hợp với runOnChange có thể hữu ích, nhưng phải kiểm chứng với DBMS. Đừng đánh dấu một changeset là đã hoàn thành chỉ vì có một view trùng tên nhưng khác câu SELECT.

### Sequence với sequenceExists

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-011-create-event-sequence"
      author: "team-db"
      preConditions:
        - onFail: HALT
        - not:
            - sequenceExists:
                schemaName: app
                sequenceName: event_id_seq
      changes:
        - createSequence:
            schemaName: app
            sequenceName: event_id_seq
            startValue: 1
            incrementBy: 1
      rollback:
        - dropSequence:
            schemaName: app
            sequenceName: event_id_seq
~~~

Không phải DBMS nào cũng hỗ trợ sequence độc lập theo cùng cú pháp. Nếu module dùng nhiều hệ quản trị, kết hợp `dbms` hoặc tách changeset chuyên biệt cho DBMS. Tồn tại sequence cũng không chứng minh nó có đúng increment, cache, owner hay giá trị hiện tại.

## 10. Ghép điều kiện bằng and, or, not

Các điều kiện tồn tại có thể lồng bằng toán tử logic:

~~~yaml
preConditions:
  - onFail: HALT
  - and:
      - tableExists:
          schemaName: app
          tableName: customer
      - columnExists:
          schemaName: app
          tableName: customer
          columnName: id
      - not:
          - indexExists:
              schemaName: app
              tableName: customer
              indexName: ix_customer_email
~~~

Ý nghĩa là cả ba điều kiện phải đạt: bảng customer có, cột id có, index ix_customer_email chưa có.

Các toán tử:

| Toán tử | Kết quả đạt khi | Trường hợp dùng |
|---|---|---|
| `and` | Mọi điều kiện con đều đạt | Yêu cầu nhiều phụ thuộc cùng tồn tại |
| `or` | Có ít nhất một điều kiện con đạt | Chấp nhận một trong nhiều trạng thái schema hợp lệ |
| `not` | Điều kiện con không đạt | Yêu cầu đối tượng chưa tồn tại |

Các nhóm điều kiện cũng có thể được lồng nhau. Liquibase hỗ trợ đánh giá điều kiện logic theo cơ chế phù hợp với kết quả của các nhánh; tuy vậy, không xây dựng logic phụ thuộc vào **tác dụng phụ** của một precondition. Việc kiểm tra phải là thao tác đọc, không làm thay đổi dữ liệu.

Khi điều kiện quá sâu hoặc cần rất nhiều nhánh đặc thù môi trường, nên xem lại thiết kế migration. Một precondition khó đọc có thể che giấu trường hợp schema drift, dẫn đến việc bỏ qua nhầm changeset.

## 11. Phân biệt onFail, onError và lựa chọn hành vi

Precondition có hai loại kết quả bất thường quan trọng:

- **Fail:** kiểm tra thực hiện được nhưng kết quả không thỏa điều kiện. Ví dụ tableExists xác nhận bảng customer chưa có.
- **Error:** bản thân việc kiểm tra phát sinh lỗi. Ví dụ mất quyền đọc metadata, lỗi kết nối hoặc câu sqlCheck không hợp lệ.

Vì vậy, `onFail` và `onError` không đồng nghĩa. Ví dụ:

~~~yaml
preConditions:
  - onFail: HALT
  - onError: HALT
  - onFailMessage: "Schema chưa đáp ứng điều kiện để thêm khóa"
  - onErrorMessage: "Không đánh giá được metadata của database"
  - tableExists:
      schemaName: app
      tableName: invoice
~~~

Hành vi thường dùng ở **cấp changeset**:

| Chính sách | Khi precondition không đạt | Khi nào cân nhắc |
|---|---|---|
| `HALT` | Dừng triển khai với lỗi | Khi thiếu đối tượng là sai trạng thái hoặc có nguy cơ dữ liệu |
| `WARN` | Ghi cảnh báo và tiếp tục xử lý theo quy tắc tương ứng | Khi chỉ cần quan sát; không phù hợp để ngăn DDL nguy hiểm |
| `CONTINUE` | Bỏ qua changeset ở lần chạy này, không ghi nhận như đã chạy | Khi thay đổi có thể được đánh giá lại trong lần sau |
| `MARK_RAN` | Bỏ qua thao tác nhưng ghi nhận changeset như đã chạy | Chỉ khi đã xác minh database thật sự tương đương với kết quả cần có |

`CONTINUE` và `MARK_RAN` chỉ hợp lệ cho precondition cấp changeset; ở cấp changelog, thường dùng `HALT` hoặc `WARN`. Hành vi có thể thay đổi theo onFail hoặc onError được khai báo, nên cần kiểm tra cấu hình thực tế.

**Cảnh báo nghiệp vụ:** MARK_RAN không chạy SQL; nếu một changeset có nhiều change và chỉ một phần schema đã tồn tại, MARK_RAN có thể bỏ qua những change còn thiếu. Không dùng MARK_RAN đại trà như cách làm cho migration “chạy xanh” sau khi phát hiện đối tượng đã tồn tại.

## 12. Khi cần kiểm tra sâu hơn bằng sqlCheck

Các precondition kiểu `...Exists` thường trả lời câu hỏi sự tồn tại. Khi cần kiểm tra định nghĩa hoặc dữ liệu cụ thể, `sqlCheck` có thể trả về **một giá trị đơn (scalar)** rồi so sánh với expectedResult.

Ví dụ PostgreSQL: trước khi thêm ràng buộc unique vào email, xác nhận không có nhóm email trùng trong bảng đã tồn tại:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-012-check-email-unique"
      author: "team-db"
      preConditions:
        - onFail: HALT
        - and:
            - tableExists:
                schemaName: app
                tableName: customer
            - columnExists:
                schemaName: app
                tableName: customer
                columnName: email
            - sqlCheck:
                expectedResult: "0"
                sql: |
                  SELECT COUNT(*)
                  FROM (
                    SELECT email
                    FROM app.customer
                    WHERE email IS NOT NULL
                    GROUP BY email
                    HAVING COUNT(*) > 1
                  ) duplicated;
      changes:
        - addUniqueConstraint:
            schemaName: app
            tableName: customer
            columnNames: email
            constraintName: uq_customer_email
      rollback:
        - dropUniqueConstraint:
            schemaName: app
            tableName: customer
            constraintName: uq_customer_email
~~~

Nếu có bất kỳ email không NULL nào bị trùng, truy vấn trả về số lớn hơn 0, precondition fail và Liquibase dừng. Ví dụ bỏ qua NULL để phù hợp với một số cách hiểu UNIQUE phổ biến; quy tắc UNIQUE và NULL vẫn cần xác minh theo DBMS mục tiêu. Nó cũng chưa xác minh đã tồn tại ràng buộc tên uq_customer_email hay chưa; nên bổ sung kiểm tra phù hợp nếu database có thể đã trải qua thay đổi ngoài Liquibase.

Một ví dụ kiểm tra kiểu cột bằng metadata PostgreSQL:

~~~sql
SELECT COUNT(*)
FROM information_schema.columns
WHERE table_schema = 'app'
  AND table_name = 'customer'
  AND column_name = 'email'
  AND data_type = 'character varying'
  AND character_maximum_length = 320;
~~~

Truy vấn đó chỉ dùng được khi metadata, tên schema và kiểu dữ liệu khớp với PostgreSQL đang triển khai. Với MySQL, SQL Server hoặc Oracle cần truy vấn hệ thống tương ứng. Không đưa SQL metadata riêng của một DBMS vào migration đa DBMS mà không dùng `dbms` hoặc nhánh cấu hình phù hợp.

Một precondition `sqlCheck` được thiết kế để **đọc** trạng thái database. Tránh dùng INSERT, UPDATE, DELETE hoặc DDL trong precondition: chúng có thể tạo tác dụng phụ chỉ vì Liquibase đang kiểm tra khả năng triển khai.

## 13. Xác định đúng catalog, schema và cách viết tên đối tượng

Một lỗi phổ biến là bỏ `schemaName` và mặc định Liquibase sẽ kiểm tra đúng schema. Khi có nhiều schema cùng tồn tại, kết quả có thể khác dự kiến.

Các điểm cần ghi nhớ:

- **catalogName** và **schemaName** là hai khái niệm khác nhau; cách tổ chức catalog/schema phụ thuộc DBMS.
- Nếu không khai báo schemaName, Liquibase thường dùng default schema từ kết nối/cấu hình; phải xác minh đó là schema ứng dụng mong muốn.
- PostgreSQL có `search_path`; SQL trực tiếp dùng tên không đủ schema có thể giải quyết khác với cách precondition truy vấn metadata.
- Tên được tạo bằng dấu nháy kép có thể phân biệt chữ hoa/thường; tên không trích dẫn thường được DBMS chuẩn hóa theo quy tắc riêng.
- Một số DBMS giới hạn độ dài tên và tự cắt hoặc tự tạo tên constraint/index.
- Kiểm tra tên object mà không đối chiếu bảng/schema có thể dẫn đến kết luận đúng ở chỗ này nhưng sai ở chỗ khác.

Khi cần triển khai cùng changelog qua nhiều môi trường, có thể dùng changelog parameter:

~~~yaml
preConditions:
  - onFail: HALT
  - tableExists:
      schemaName: "${appSchema}"
      tableName: customer
~~~

Giá trị appSchema phải được cấp từ nguồn cấu hình có kiểm soát và đúng với schemaName sử dụng trong `changes` cũng như `rollback`. Thay tham số sau khi đã triển khai không tự chuyển đối tượng sang schema mới. Trước khi rollback, xác nhận lại giá trị đã dùng khi update.

## 14. Đọc precondition cùng với lịch sử DATABASECHANGELOG

Precondition và bảng DATABASECHANGELOG giải quyết những câu hỏi khác nhau:

- **DATABASECHANGELOG:** Liquibase đã ghi nhận changeset (id, author, filename) trong database đích chưa?
- **Precondition:** database đang có những đối tượng hoặc dữ liệu cần thiết cho thay đổi hay không?
- **Kiểm tra schema thực tế:** định nghĩa, quyền, dữ liệu và phụ thuộc có đúng kỳ vọng không?

Ví dụ có bảng invoice nhưng không có dòng lịch sử tương ứng trong DATABASECHANGELOG:

1. Có thể bảng được tạo ngoài Liquibase.
2. Có thể quá trình baseline/sync lịch sử chưa hoàn thành.
3. Có thể tên file, id hoặc author của changeset đã thay đổi.
4. Có thể đang kết nối nhầm schema hoặc database.

Nếu một changeset tạo bảng được đặt `onFail: MARK_RAN` khi bảng đã tồn tại, bảng DATABASECHANGELOG có thể ghi EXECTYPE=MARK_RAN. Điều này cho biết Liquibase đã **đánh dấu**, không chứng minh nó thực sự đã tạo bảng.

Ngược lại, nếu changeset đã được ghi nhận EXECUTED từ trước, việc thay đổi schema ngoài Liquibase sau đó không được precondition tự phát hiện trong lần update thông thường. Muốn kiểm toán schema drift cần snapshot/diff, truy vấn metadata hoặc công cụ kiểm tra chuyên biệt thay vì tin rằng precondition là giám sát liên tục.

## 15. Kiểm tra và rollback trong quy trình nhiều môi trường

Trước khi đưa changeset có precondition lên staging hoặc production, nên kiểm chứng theo trình tự:

1. Xác nhận JDBC URL, DBMS, database, schema, tài khoản migration và version Liquibase.
2. Đọc changelog và xem changeset có thuộc context/label/dbms của môi trường hiện tại không.
3. Kiểm tra DATABASECHANGELOG để biết định danh id–author–filename đã được ghi nhận hay chưa.
4. Dùng SQL metadata hoặc snapshot để hiểu trạng thái bảng/cột/khóa hiện có, nhất là khi dự định MARK_RAN.
5. Chạy `liquibase validate` để kiểm tra cấu trúc changelog và một số lỗi cấu hình.
6. Chạy `liquibase status --verbose` và `liquibase update-sql` để review kế hoạch thực thi. Lưu ý kết quả và cách đánh giá precondition trong chế độ sinh SQL có thể phụ thuộc cấu hình/version; đừng coi generated SQL là bằng chứng cuối cùng của trạng thái thực thi.
7. Triển khai bằng `liquibase update` trong job được điều phối có kiểm soát.
8. Đối chiếu DATABASECHANGELOG, EXECTYPE và schema/dữ liệu thực tế sau triển khai.

Precondition dùng cho chiều **triển khai** không mặc nhiên là điều kiện bảo vệ đầy đủ cho chiều **rollback**. Ví dụ dropColumn trong rollback có thể xóa dữ liệu phát sinh sau khi addColumn. Trước rollback, xem SQL rollback, đối tượng đích, phụ thuộc khóa ngoại và backup/khả năng khôi phục. Nếu đối tượng đang tồn tại nhưng khác cấu trúc, rollback tự động có thể không khôi phục được trạng thái ban đầu một cách an toàn.

Với CI/CD hoặc Spring Boot, cùng changelog có thể chạy ở nhiều database khác nhau nhưng precondition trả kết quả khác nhau. Đó là hành vi bình thường nếu các môi trường có schema khác nhau; khác biệt phải được giải thích rõ trước khi cho qua pipeline. Không thay đổi id/author chỉ để ép một changeset chạy lại, cũng không tự chỉnh DATABASECHANGELOG để biến trạng thái không khớp thành “đã xong”.

## 16. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| tableExists trả không đạt dù thấy bảng | Kiểm tra nhầm schema/catalog hoặc khác chữ hoa/thường | Xác nhận schemaName, default schema, quoted identifier và connection |
| columnExists đạt nhưng addColumn vẫn lỗi | Cột có ở schema khác, điều kiện không yêu cầu cột vắng mặt, hoặc thay đổi khác xảy ra giữa lúc kiểm tra và thực thi | Kiểm tra lại tổ hợp tableExists + not columnExists, SQL và lịch sử |
| MARK_RAN nhưng thiếu cột/khóa | Chỉ kiểm tra tên bảng rồi đánh dấu toàn bộ changeset | Đối chiếu trạng thái đầy đủ; thiết kế changeset bổ sung có kiểm chứng |
| Khóa ngoại đã có nhưng precondition không nhận ra | Sai foreignKeyName hoặc foreignKeyTableName; DBMS tự sinh tên | Truy vấn metadata ràng buộc và xác nhận bảng chứa FK |
| indexExists đạt nhưng index không đáp ứng truy vấn | Tên trùng nhưng cột/thứ tự/predicate khác kỳ vọng | Kiểm tra định nghĩa index, EXPLAIN và chiến lược tối ưu |
| primaryKeyExists không đạt | Sai schemaName, tableName hoặc tên khóa; bảng dùng khóa khác | So sánh metadata của khóa chính và tên ràng buộc thực tế |
| Thêm UNIQUE thất bại dù uniqueConstraintExists không đạt | Dữ liệu đã trùng hoặc constraint/index tương đương tồn tại với tên khác | Kiểm tra dữ liệu, tên constraint và loại đối tượng |
| sqlCheck báo lỗi trong một môi trường | Query metadata phụ thuộc DBMS hoặc thiếu quyền | Sửa SQL cho đúng DBMS, kiểm tra quyền hoặc dùng precondition tích hợp |
| validate thành công nhưng update thất bại | Validate không chứng minh dữ liệu/DDL thực tế hợp lệ | Kiểm tra trên database đại diện, review SQL, metadata và transaction |
| Precondition không phát hiện schema drift sau triển khai | Changeset đã chạy không được kiểm tra như một bộ quy tắc giám sát liên tục | Dùng diff/snapshot, audit schema và changeset sửa tiến mới |

Nếu nghi ngờ lỗi nằm ở metadata, nên chạy truy vấn chỉ đọc trên **chính database** mà Liquibase kết nối. Không suy luận trạng thái production từ kết quả development hoặc staging.

## 17. Bài thực hành: thêm cột và tạo index có kiểm chứng

**Bối cảnh:** database thử nghiệm đã có bảng app.customer(id, email). Cần bổ sung cột phone và một index phục vụ truy vấn. Hãy dùng hai changeset độc lập:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-020-add-customer-phone"
      author: "team-db"
      preConditions:
        - onFail: HALT
        - and:
            - tableExists:
                schemaName: app
                tableName: customer
            - not:
                - columnExists:
                    schemaName: app
                    tableName: customer
                    columnName: phone
      changes:
        - addColumn:
            schemaName: app
            tableName: customer
            columns:
              - column:
                  name: phone
                  type: VARCHAR(30)
      rollback:
        - dropColumn:
            schemaName: app
            tableName: customer
            columnName: phone

  - changeSet:
      id: "20261119-021-index-customer-phone"
      author: "team-db"
      preConditions:
        - onFail: HALT
        - and:
            - columnExists:
                schemaName: app
                tableName: customer
                columnName: phone
            - not:
                - indexExists:
                    schemaName: app
                    tableName: customer
                    indexName: ix_customer_phone
      changes:
        - createIndex:
            schemaName: app
            tableName: customer
            indexName: ix_customer_phone
            columns:
              - column:
                  name: phone
      rollback:
        - dropIndex:
            schemaName: app
            tableName: customer
            indexName: ix_customer_phone
~~~

**Các bước thực hiện:**

1. Chuẩn bị database thử nghiệm có schema app và bảng customer, chưa có cột phone/index ix_customer_phone.
2. Chạy validate, status --verbose và update-sql; xem changeset nào sẽ chạy và SQL nhắm tới schema nào.
3. Chạy update, xác nhận cột phone và index ix_customer_phone thực sự tồn tại.
4. Truy vấn DATABASECHANGELOG; xác nhận hai changeset được ghi nhận và kiểm tra EXECTYPE.
5. Chạy lại update; trong trường hợp thông thường, hai changeset đã ghi nhận sẽ được bỏ qua.
6. Trên **database thử nghiệm độc lập**, tạo sẵn cột phone trước nhưng chưa có lịch sử Liquibase; chạy status và kiểm tra phản ứng của precondition HALT ở changeset thứ nhất khi update.
7. Đối chiếu với giả định MARK_RAN: nếu chỉ đánh dấu changeset thứ nhất đã chạy, liệu index và định nghĩa cột có được bảo đảm đúng không? **Không.** Phải kiểm chứng cả kiểu dữ liệu và phụ thuộc.
8. Thử xem SQL rollback và thực hiện rollback chỉ trong môi trường thử nghiệm được phép mất dữ liệu, sau khi kiểm tra ảnh hưởng của dropColumn.

**Câu hỏi tự kiểm tra:**

- Cần chạy addColumn chỉ khi cột chưa có: dùng gì? **not + columnExists**, thường đi cùng tableExists.
- Muốn tránh thêm FK trùng tên: dùng gì? **foreignKeyConstraintExists**, kiểm tra đúng bảng chứa FK và tên ràng buộc.
- Unique constraint không tồn tại có chứng minh dữ liệu không trùng? **Không**; cần kiểm tra dữ liệu.
- MARK_RAN có chạy câu SQL createTable không? **Không**, nó chỉ ghi nhận changeset theo chính sách khi điều kiện thất bại.
- Nếu changeset đã chạy nhưng bảng sau đó bị xóa thủ công, precondition có tự khôi phục bảng ở update tiếp theo không? **Không** trong cơ chế changeset thông thường; cần xác định drift và tạo quy trình khắc phục riêng.

## 18. Checklist review precondition tồn tại

- [ ] Đã chọn đúng loại precondition cho bảng, cột, khóa, index, view hoặc sequence.
- [ ] Đã xác định DBMS và phiên bản Liquibase hỗ trợ precondition/thuộc tính đang dùng.
- [ ] Đã chỉ rõ schemaName/catalogName khi môi trường có nhiều schema.
- [ ] Đã kiểm tra đúng bảng chứa FK, đúng tên constraint/index và định nghĩa thực tế.
- [ ] Đã ghép `and`, `or`, `not` theo điều kiện nghiệp vụ, không tạo nhánh bất ngờ.
- [ ] Đã phân biệt **đối tượng có tồn tại** với **đối tượng đúng cấu trúc**.
- [ ] Đã phân biệt onFail với onError, chọn HALT/CONTINUE/MARK_RAN có chủ đích.
- [ ] Không dùng MARK_RAN để che trạng thái schema drift chưa được xác minh.
- [ ] Precondition chỉ đọc trạng thái database; sqlCheck không có tác dụng phụ.
- [ ] Đã xác nhận constraint có thể thêm được trên dữ liệu hiện tại.
- [ ] Đã kiểm tra DATABASECHANGELOG và EXECTYPE bên cạnh trạng thái đối tượng.
- [ ] Đã review SQL và thử migration trên database đại diện trước production.
- [ ] Đã đánh giá rollback, khả năng mất dữ liệu và phụ thuộc khi xóa đối tượng.
- [ ] Đã xác nhận giá trị changelog parameters/schema giống nhau giữa các bước kiểm tra và triển khai.
- [ ] Có log triển khai và bằng chứng kiểm chứng schema thực tế sau update.

Precondition kiểm tra bảng, cột, khóa và các đối tượng đã tồn tại là công cụ **diễn đạt giả định** của migration một cách tường minh. Sức mạnh của nó nằm ở việc dừng hoặc xử lý changeset có chủ đích khi trạng thái database không phù hợp. Để triển khai Liquibase an toàn qua nhiều môi trường, luôn kết hợp precondition với định danh changeset, lịch sử DATABASECHANGELOG, kiểm tra metadata/định nghĩa thực tế, thử nghiệm rollback và quy trình CI/CD có kiểm chứng.
