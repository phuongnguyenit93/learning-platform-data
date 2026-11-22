# Lựa chọn runInTransaction cho câu lệnh có yêu cầu đặc biệt

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, mục tiêu là quản lý thay đổi schema và dữ liệu bằng Liquibase qua changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường, đồng thời tích hợp Spring Boot hoặc CI/CD. Bài thuộc chương **Giao dịch và khóa** này giải thích cách chọn **runInTransaction** khi một câu lệnh SQL có yêu cầu giao dịch đặc biệt, nhất là các lệnh **không được chạy trong một transaction block**.

Một thay đổi schema an toàn không chỉ cần SQL hợp lệ. Cần biết câu lệnh có thể tham gia transaction hay không, DBMS thực sự hỗ trợ rollback đến đâu, Liquibase ghi lịch sử khi thành công hoặc thất bại thế nào và phải khôi phục ra sao nếu chỉ một phần thao tác đã hoàn tất. Vì vậy, **runInTransaction: false** không phải mẹo tổng quát để “chạy migration nhanh hơn”; đó là một lựa chọn thay đổi ranh giới an toàn của changeset.

Sau bài này, bạn có thể phân biệt giao dịch ở mức changeset với khóa điều phối Liquibase, quyết định khi nào giữ mặc định **true**, khi nào buộc dùng **false**, viết migration PostgreSQL tạo chỉ mục **CONCURRENTLY**, nhận diện rủi ro partial failure và thiết kế bước kiểm chứng, rollback hoặc forward-fix.

## 1. Giao dịch và changeset trong Liquibase

Một **changeset** là đơn vị triển khai có định danh, gồm **id**, **author** và đường dẫn changelog. Liquibase đối chiếu chúng với **DATABASECHANGELOG** để xác định đã triển khai hay chưa. Theo mặc định, thuộc tính **runInTransaction** của changeset là **true**.

Khi **runInTransaction: true** và DBMS hỗ trợ giao dịch đối với các thay đổi đang chạy, Liquibase cố gắng thực thi các lệnh của changeset trong **một transaction**. Nếu một lệnh phát sinh lỗi trước commit, cơ chế transaction có thể rollback các thao tác trước đó trong changeset. Tuy nhiên:

- **Một changeset không đồng nghĩa toàn bộ changelog.** Nếu changeset A đã commit, changeset B lỗi không có nghĩa A tự động bị rollback.
- **Không phải mọi DDL đều rollback được.** Nhiều DBMS có implicit commit hoặc ngoại lệ theo loại câu lệnh.
- **Không phải mọi tác động đều nằm trong database.** Những lệnh thực hiện công việc bên ngoài database hoặc cấp số sequence có thể có hành vi không đảo ngược theo transaction thông thường.
- **Rollback của DBMS khác rollback của Liquibase.** ROLLBACK transaction do lỗi là một cơ chế; lệnh Liquibase rollback nhằm đảo migration đã ghi nhận là cơ chế khác, thường cần rollback SQL hoặc change type đảo ngược.

Ví dụ: trên PostgreSQL, nhiều câu **ALTER TABLE** thông thường có thể nằm trong transaction. Nhưng **CREATE INDEX CONCURRENTLY** lại không được chạy bên trong transaction block. Đặt mặc định true cho lệnh này thường khiến server từ chối; lúc đó cần changeset **runInTransaction: false**.

## 2. runInTransaction: true và false thực sự khác nhau thế nào?

**runInTransaction** là thuộc tính của **changeset**. Nó cho Liquibase biết có nên bọc các thay đổi của changeset vào transaction do Liquibase quản lý hay không.

| Thuộc tính | Cách thực thi mong muốn | Lợi ích | Rủi ro/giới hạn |
|---|---|---|---|
| **true** (mặc định) | Chạy thay đổi của changeset trong transaction nếu DBMS hỗ trợ | Dễ hạn chế áp dụng dở dang một changeset, thuận tiện xử lý lỗi | Không hợp lệ cho lệnh cấm transaction; DDL implicit commit vẫn có thể phá vỡ tính nguyên tử |
| **false** | Không bọc toàn bộ thay đổi của changeset trong một transaction do Liquibase quản lý | Cho phép chạy một số câu lệnh cần chạy ngoài transaction block | Nếu nhiều thao tác, lỗi giữa chừng có thể để lại một phần thay đổi; lịch sử và schema có thể lệch |

**runInTransaction: false không đồng nghĩa tắt toàn bộ cơ chế transaction của database.** Từng câu lệnh và driver vẫn chịu ngữ nghĩa transaction/autocommit của DBMS. Nó chỉ yêu cầu Liquibase không dùng một giao dịch bao trùm changeset theo cách thông thường.

Một minh họa:

~~~text
Changeset A (runInTransaction: true)
    BEGIN (nếu DBMS hỗ trợ)
      DDL/DML số 1
      DDL/DML số 2
    COMMIT hoặc ROLLBACK

Changeset B (runInTransaction: false)
      Lệnh đặc biệt số 1
      [không có transaction chung bao toàn changeset]
      Lệnh đặc biệt số 2
      [nếu lỗi ở đây, lệnh trước có thể đã có hiệu lực]
~~~

Đây là mô hình khái niệm, không phải bản ghi SQL do mọi phiên bản Liquibase phát ra. DBMS, JDBC driver, executor và loại change quyết định cách lệnh được gửi và commit thực tế. Muốn biết chắc, phải chạy thử trên đúng hệ quản trị được triển khai.

## 3. Khi nào cần runInTransaction: false?

Lý do chính đáng nhất là **DBMS quy định câu lệnh không được thực thi trong transaction block**, hoặc công cụ/native executor có yêu cầu tương đương đã được xác minh.

Một số ví dụ cần phân biệt:

| Database / lệnh | Lý do cần chú ý | Hướng xử lý |
|---|---|---|
| **PostgreSQL: CREATE INDEX CONCURRENTLY** | PostgreSQL không cho chạy câu lệnh này trong transaction block | Tách thành changeset riêng và đặt runInTransaction: false |
| **PostgreSQL: DROP INDEX CONCURRENTLY** | Cũng không cho chạy trong transaction block, với các giới hạn riêng | Nếu dùng trong rollback, kiểm thử cơ chế thực thi rollback ngoài transaction |
| **PostgreSQL: REINDEX ... CONCURRENTLY** | Có yêu cầu không nằm trong transaction block | Dùng changeset hoặc job chuyên biệt được kiểm chứng trên version PostgreSQL |
| **PostgreSQL: VACUUM** | Không chạy trong transaction block | Thường nên là tác vụ vận hành/maintenance riêng, không phải schema migration lặp lại |
| **PostgreSQL: CREATE DATABASE** | Không cho chạy trong transaction block, còn liên quan quyền và phạm vi kết nối | Thường provision database bên ngoài changelog kết nối vào database ứng dụng |
| **Các lệnh DDL trên MySQL/Oracle** | Nhiều DDL có implicit commit hoặc ngữ nghĩa transaction đặc thù | Không mặc định đổi tất cả sang false; nghiên cứu DDL cụ thể, DBMS/version và chiến lược phục hồi |

Đừng suy rộng rằng **ALTER TYPE ... ADD VALUE** trên mọi PostgreSQL luôn buộc dùng false: khả năng thực thi trong transaction và thời điểm có thể sử dụng enum value mới có khác biệt giữa các phiên bản PostgreSQL. Cần đánh giá theo phiên bản đích và cách dùng giá trị đó trong cùng transaction.

Ngược lại, không nên đặt **false** cho mọi changeset “DDL nặng”. Một lệnh khóa bảng lâu không có nghĩa nó cần chạy ngoài transaction; việc tách migration, tối ưu câu lệnh, lập lịch và đặt timeout thường là giải pháp đúng hơn.

## 4. Ví dụ chủ đạo: CREATE INDEX CONCURRENTLY trên PostgreSQL

Giả sử hệ thống có bảng **purchase_order** với hàng triệu bản ghi và cột **customer_id** thường được lọc/join. Nhóm cần thêm index để tăng hiệu năng mà muốn giảm ảnh hưởng đến các thao tác ghi đồng thời.

PostgreSQL hỗ trợ:

~~~sql
CREATE INDEX CONCURRENTLY idx_purchase_order_customer_id
ON public.purchase_order (customer_id);
~~~

Khác với **CREATE INDEX** thông thường, biến thể **CONCURRENTLY** được thiết kế để giảm việc chặn các thao tác INSERT/UPDATE/DELETE trong quá trình xây dựng index, nhưng tốn công việc quét bảng, có thể chờ transaction đang chạy và có các giới hạn riêng. Nó **không có nghĩa không dùng khóa, không ảnh hưởng hiệu năng hoặc luôn hoàn tất nhanh**.

Nếu đặt câu lệnh trên trong changeset Liquibase mặc định, PostgreSQL có thể báo lỗi đại ý: **CREATE INDEX CONCURRENTLY cannot run inside a transaction block**. Khắc phục đúng là tách câu lệnh thành một changeset độc lập và đặt **runInTransaction: false**.

### Ví dụ changelog YAML

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 010-create-order-customer-index-concurrently
      author: database-team
      dbms: postgresql
      runInTransaction: false
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            schemaName: public
            tableName: purchase_order
        - columnExists:
            schemaName: public
            tableName: purchase_order
            columnName: customer_id
        - not:
            - indexExists:
                schemaName: public
                tableName: purchase_order
                indexName: idx_purchase_order_customer_id
      changes:
        - sql:
            splitStatements: false
            sql: |
              CREATE INDEX CONCURRENTLY
                idx_purchase_order_customer_id
              ON public.purchase_order (customer_id);
      rollback:
        - sql:
            splitStatements: false
            sql: |
              DROP INDEX CONCURRENTLY
                IF EXISTS public.idx_purchase_order_customer_id;
~~~

Giải thích các quyết định:

- **dbms: postgresql**: đây là SQL riêng PostgreSQL; không chạy nguyên dạng trên DBMS khác.
- **runInTransaction: false**: tránh bọc CREATE INDEX CONCURRENTLY trong transaction chung do Liquibase quản lý.
- **Một câu SQL duy nhất trong changes**: giảm nguy cơ một changeset chạy dở rồi mới thất bại ở câu tiếp theo.
- **splitStatements: false**: truyền đoạn SQL như một statement; đặc biệt tránh tự tách câu lệnh không cần thiết.
- **preConditions**: dừng nếu bảng, cột không có, hoặc index cùng tên đã tồn tại trước lần triển khai. Chúng không chứng minh index có sẵn là hợp lệ hay đúng cột.
- **rollback**: chỉ định câu lệnh đảo hướng được đề xuất; cần kiểm chứng Liquibase rollback thực thi bên ngoài transaction theo DBMS/version đang dùng và bảo đảm index thực sự do changeset này tạo ra.

**Chú ý về rollback:** DROP INDEX CONCURRENTLY có các hạn chế đối với index tham gia constraint, index phân vùng và trạng thái database cụ thể. Trong nhiều tình huống production, lựa chọn forward-fix hoặc thay thế index được giám sát có thể an toàn hơn tự động rollback. Không thử lệnh rollback làm ảnh hưởng hiệu năng trên database production mà chưa review.

## 5. Vì sao một changeset chỉ nên chứa một thao tác non-transactional?

Xét changeset tưởng như thuận tiện:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: risky-multiple-indexes
      author: database-team
      dbms: postgresql
      runInTransaction: false
      changes:
        - sql:
            sql: |
              CREATE INDEX CONCURRENTLY idx_order_customer
              ON public.purchase_order(customer_id);
        - sql:
            sql: |
              CREATE INDEX CONCURRENTLY idx_order_created
              ON public.purchase_order(created_at);
~~~

Nếu index thứ nhất được tạo thành công nhưng index thứ hai thất bại, database có thể đã giữ index thứ nhất trong khi changeset chưa được Liquibase ghi nhận hoàn tất theo lịch sử mong muốn. Lần triển khai lại có thể gặp lỗi **index already exists** ở câu đầu. Trạng thái database trở nên khó giải thích, đặc biệt trong lúc nhiều bản release chạy nối tiếp.

Phương án tốt hơn là **tách thành hai changeset**, mỗi changeset một lệnh có tác động độc lập và có kiểm tra tương ứng:

~~~text
010-create-order-customer-index-concurrently   [false, 1 statement]
011-create-order-created-index-concurrently    [false, 1 statement]
~~~

Tách nhỏ không loại bỏ khả năng một câu lệnh đơn lẻ để lại trạng thái trung gian khi thất bại, nhưng làm rõ đối tượng cần kiểm tra hoặc sửa và giảm số thao tác có thể thành công dở trong một changeset.

**Đừng giải quyết bằng cách đặt onFail: MARK_RAN khi thấy index tồn tại.** Cùng tên chưa chắc đúng định nghĩa; thậm chí PostgreSQL có thể để lại một index **invalid** sau CREATE INDEX CONCURRENTLY thất bại. Nếu tự MARK_RAN, pipeline có thể báo thành công trong khi index không phục vụ truy vấn như kỳ vọng.

## 6. Xác minh index sau lệnh CONCURRENTLY

Với PostgreSQL, chỉ kiểm tra tên index tồn tại là chưa đủ. Một quá trình CREATE INDEX CONCURRENTLY thất bại có thể để lại index có **indisvalid = false**. Tùy giai đoạn lỗi, index không được planner dùng và vẫn có thể tạo chi phí cho các thao tác ghi.

Có thể truy vấn metadata:

~~~sql
SELECT
    ns.nspname AS schema_name,
    idx.relname AS index_name,
    i.indisready,
    i.indisvalid
FROM pg_class AS idx
JOIN pg_namespace AS ns ON ns.oid = idx.relnamespace
JOIN pg_index AS i ON i.indexrelid = idx.oid
WHERE ns.nspname = 'public'
  AND idx.relname = 'idx_purchase_order_customer_id';
~~~

Diễn giải:

- **Không có hàng**: index chưa tồn tại dưới tên/schema đã truy vấn.
- **indisvalid = true**: index được đánh dấu hợp lệ cho các mục đích tương ứng.
- **indisvalid = false**: index đang ở trạng thái không hợp lệ, cần điều tra trước khi coi migration thành công.
- **indisready** cho biết index có ở trạng thái sẵn sàng nhận cập nhật từ thao tác ghi hay không; nó không thay thế kiểm tra indisvalid.

Cần kiểm tra thêm định nghĩa cột, phương thức index, uniqueness, điều kiện partial index nếu có, bằng **pg_indexes.indexdef** hoặc công cụ truy vấn metadata phù hợp. Đừng chỉ tin tên index hay dòng changeset trong DATABASECHANGELOG.

Nếu index invalid tồn tại sau lỗi, cần xác định có tiến trình tạo index vẫn hoạt động không, kiểm tra log, transaction đang chờ và khối lượng công việc. Một quy trình phục hồi có kiểm soát có thể **DROP INDEX CONCURRENTLY** index bị lỗi rồi tạo lại, hoặc dùng phương án reindex phù hợp theo phiên bản PostgreSQL. Không tự xóa index hợp lệ đang phục vụ truy vấn.

## 7. Giao dịch và khóa DATABASECHANGELOGLOCK là hai cơ chế khác nhau

Liquibase thường dùng hai bảng metadata quan trọng:

- **DATABASECHANGELOG**: ghi nhận changeset đã thực thi, checksum và metadata triển khai.
- **DATABASECHANGELOGLOCK**: điều phối để các tiến trình Liquibase không cùng cập nhật schema đồng thời trong cùng phạm vi metadata.

Khi đặt **runInTransaction: false**, Liquibase **không vì thế mà bỏ khóa điều phối**. Khóa Liquibase và ranh giới transaction của một changeset giải quyết hai vấn đề khác nhau:

| Cơ chế | Mục đích | Điều không bảo đảm |
|---|---|---|
| runInTransaction | Xác định Liquibase có bọc changeset trong transaction không | Không bảo đảm tất cả DBMS rollback được mọi DDL |
| DATABASECHANGELOGLOCK | Phối hợp tiến trình Liquibase cùng thực hiện update | Không khóa mọi writer SQL/app; không tránh hoàn toàn mọi cạnh tranh dữ liệu |
| Khóa do DBMS sử dụng trong DDL | Bảo vệ thay đổi cấu trúc và truy cập đối tượng | Không bị loại bỏ chỉ nhờ runInTransaction: false |
| Transaction của ứng dụng | Quản lý DML nghiệp vụ do ứng dụng thực hiện | Không thay thế quy trình điều phối migration |

Một index CONCURRENTLY có thể chạy lâu dù không chặn ghi theo cách index thường. Trong thời gian đó, lock của Liquibase vẫn có thể khiến tiến trình Liquibase khác phải chờ. Nếu job bị ngắt giữa chừng, cần kiểm tra trạng thái tiến trình, lock và database trước khi can thiệp.

**Không dùng releaseLocks tùy tiện** chỉ vì một thay đổi không có transaction kéo dài. Nếu còn tiến trình thực sự chạy, giải phóng lock sai cách có thể dẫn tới hai tiến trình migration cạnh tranh và tạo thêm lỗi. Chỉ xử lý lock tồn dư sau khi xác nhận tác vụ trước đã kết thúc hoặc thất bại.

## 8. Lỗi khi chạy ngoài transaction: ảnh hưởng tới lịch sử

Với **runInTransaction: true** và DBMS hỗ trợ transactional DDL, lỗi có thể khiến thay đổi trong changeset được rollback theo transaction. Với **false**, thay đổi đã có hiệu lực trước lỗi **có thể còn tồn tại**, dù Liquibase không ghi nhận changeset là đã hoàn thành.

Các tình huống cần chuẩn bị:

1. **Câu lệnh thất bại trước khi tạo đối tượng:** database không có index mới, changeset chưa được ghi nhận; có thể sửa nguyên nhân và thử lại.
2. **Câu lệnh thất bại nhưng để lại đối tượng invalid:** database có index chưa hợp lệ; changeset chưa được ghi nhận đầy đủ. Phải làm sạch/khôi phục trạng thái theo quy trình trước khi chạy lại.
3. **Database đã áp dụng xong nhưng tiến trình Liquibase mất kết nối trước khi ghi lịch sử:** đối tượng có thể tồn tại còn DATABASECHANGELOG chưa phản ánh đúng trạng thái. Cần đối chiếu metadata, log và lịch sử, không dựa một phía.
4. **Nhiều câu lệnh trong một changeset false, câu cuối lỗi:** những câu trước có thể đã commit. Tránh thiết kế này.
5. **Tác vụ đã được ghi nhận nhưng kết quả vận hành không đúng mong muốn:** cần kiểm tra định nghĩa index/đối tượng và dữ liệu, thay vì tin rằng có dòng lịch sử nghĩa là mọi yêu cầu nghiệp vụ đã được đáp ứng.

Một hậu quả quan trọng: **runInTransaction: false có thể khiến trạng thái DATABASECHANGELOG không đồng bộ với trạng thái các đối tượng thực tế** sau một lỗi giữa quá trình. Do đó công tác readback, kiểm tra metadata và log CI/CD là bắt buộc với migration quan trọng.

Không trực tiếp sửa cột MD5SUM hoặc đánh dấu MARK_RAN cho changeset để che lỗi này. **Checksum** bảo vệ định nghĩa changeset đã chạy; nó không chứng minh câu lệnh đã tạo ra index hợp lệ hoặc dữ liệu đạt yêu cầu.

## 9. Cách xử lý partial failure an toàn

Một runbook ngắn cho migration PostgreSQL **CREATE INDEX CONCURRENTLY** bị lỗi:

1. **Dừng phát hành phụ thuộc:** không triển khai ứng dụng mới nếu ứng dụng đòi index hay ràng buộc chưa được kiểm chứng; lưu log và dấu thời gian thất bại.
2. **Xác minh tiến trình còn chạy hay không:** kiểm tra Liquibase, session database và tác vụ xây dựng index; không vội chạy lại hoặc giải phóng lock.
3. **Đối chiếu trạng thái index:** truy vấn pg_index, pg_indexes và schema đích; kiểm tra index có tồn tại, có hợp lệ, có đúng cột không.
4. **Đối chiếu DATABASECHANGELOG:** changeset đã ghi nhận chưa, mã id/author/file có đúng không, có dấu hiệu metadata bị cập nhật dở không.
5. **Phân loại sự cố:** timeout, phiên bị hủy, lỗi quyền, thiếu dung lượng, transaction dài, index cùng tên, dữ liệu không thỏa UNIQUE nếu đang tạo unique index.
6. **Chọn đường phục hồi:** nếu index invalid, đánh giá xóa/reindex có kiểm soát; nếu index đã hợp lệ nhưng lịch sử chưa phản ánh, xử lý reconcile theo quy trình đã review. Không tự tạo hoặc sửa bản ghi Liquibase.
7. **Thử lại trên staging/bản sao:** kiểm tra lệnh, quyền, timeout và kế hoạch rollback/forward-fix.
8. **Tiếp tục pipeline chỉ khi đủ bằng chứng:** lưu kết quả SQL kiểm tra và bản ghi lịch sử tương ứng.

Ví dụ câu lệnh PostgreSQL để **xóa một index invalid đã xác minh** (không áp dụng máy móc, cần đúng tên/schema và đủ điều kiện của DROP INDEX CONCURRENTLY):

~~~sql
DROP INDEX CONCURRENTLY IF EXISTS
    public.idx_purchase_order_customer_id;
~~~

Đây là lệnh vận hành có tác động. Không dùng trên production khi index đang được tạo, khi chưa xác minh dependency hoặc khi tên trùng với một index hợp lệ khác.

## 10. Phân biệt các lựa chọn không thay thế được runInTransaction

Một số tùy chọn Liquibase dễ bị dùng nhầm:

| Cơ chế | Tác dụng | Có giải quyết lệnh cấm transaction không? |
|---|---|---|
| **runInTransaction: false** | Không bọc cả changeset bằng transaction Liquibase | Có thể, nếu DBMS cho lệnh chạy ngoài transaction |
| **runAlways: true** | Chạy changeset trong mỗi lần update phù hợp | Không; còn nguy hiểm với DDL không thể chạy lặp lại |
| **runOnChange: true** | Cho phép chạy lại khi checksum thay đổi | Không; không thay thế chọn ranh giới transaction |
| **splitStatements: false** | Điều khiển việc Liquibase tách chuỗi SQL thành câu lệnh | Không; chuỗi SQL vẫn có thể nằm trong transaction nếu runInTransaction true |
| **failOnError: false** | Cho phép một số lỗi changeset không dừng quy trình theo cấu hình | Không; có thể che giấu trạng thái sai lệch |
| **preConditions** | Kiểm tra điều kiện trước thay đổi | Không; chỉ bảo vệ giả định, không đổi yêu cầu transaction của server |
| **runWith** | Chọn executor phù hợp trong những trường hợp được hỗ trợ | Không mặc định; cần xem executor và ràng buộc runInTransaction |

**runInTransaction được đặt ở changeset**, không phải ở từng thuộc tính của lệnh SQL. Nếu trong một changeset có cả lệnh transaction-safe và lệnh không transaction-safe, hãy tách chúng thành changeset khác nhau.

Nếu dùng Liquibase native executor cho SQL*Plus, psql hoặc sqlcmd ở những môi trường hỗ trợ, cần xem tài liệu phiên bản về các hạn chế kết hợp **runWith** và **runInTransaction**. Đừng sao chép cấu hình JDBC cho native executor mà không thử nghiệm.

## 11. DBMS có implicit commit: false không đồng nghĩa an toàn hơn

Trên PostgreSQL, nhiều DDL có thể rollback; chọn runInTransaction thường có ý nghĩa rõ ràng. Nhưng trên MySQL, Oracle và một số DBMS khác, nhiều câu DDL có hành vi **implicit commit** hoặc không hỗ trợ rollback DDL như DML.

Ví dụ, một changeset chứa:

~~~sql
ALTER TABLE example_table ADD COLUMN note VARCHAR(100);
UPDATE example_table SET note = 'ready' WHERE note IS NULL;
~~~

Không thể mặc định rằng hai lệnh này sẽ rollback chung khi UPDATE lỗi trên mọi DBMS, kể cả khi runInTransaction giữ mặc định true. Cách chính xác phụ thuộc DBMS, engine, phiên bản, kiểu DDL và driver.

Do đó, trước khi phát hành:

- Xác định DBMS có hỗ trợ DDL transactional cho lệnh cụ thể hay không.
- Cân nhắc tách thay đổi schema khỏi backfill dữ liệu.
- Dùng precondition để phát hiện schema/dữ liệu lệch kỳ vọng.
- Xem xét timeout, locks và tác động truy vấn dài.
- Chuẩn bị forward-fix khi rollback nguyên tử không khả dụng.

Đừng đổi sang false chỉ vì DBMS có implicit commit; điều đó không làm DDL “an toàn” hơn. Quyết định false cần xuất phát từ **yêu cầu của câu lệnh/DBMS** hoặc một quy trình vận hành được kiểm chứng, không phải một tối ưu mặc định.

## 12. Lựa chọn runInTransaction cho migration dữ liệu

Nhiều migration không tạo đối tượng mà thực hiện **UPDATE** hoặc **INSERT** dữ liệu. Khi đó transaction bảo vệ tính toàn vẹn rất quan trọng.

Với một bước sửa dữ liệu ngắn, có thể để mặc định true:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 020-normalize-customer-status
      author: database-team
      runInTransaction: true
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: customer
      changes:
        - sql:
            sql: |
              UPDATE customer
              SET status = 'ACTIVE'
              WHERE status IS NULL;
~~~

Trên DBMS hỗ trợ, transaction giúp tránh trạng thái áp dụng dở trong phạm vi changeset. Nhưng nếu bảng quá lớn, UPDATE dài có thể giữ khóa, tạo log và ảnh hưởng hiệu năng. Đáp án không đơn giản là chuyển **false**.

Các chiến lược thích hợp hơn có thể là:

- Tách backfill thành các batch có thể tiếp tục, với điều kiện lọc idempotent.
- Dùng job dữ liệu riêng theo thiết kế được review nếu quá trình chạy nhiều giờ.
- Thực hiện expand–migrate–verify–contract để schema và ứng dụng cùng tương thích trong giai đoạn chuyển đổi.
- Đặt timeout/giới hạn tải và theo dõi số bản ghi xử lý.
- Chỉ chuyển sang false khi có lý do cụ thể về transaction boundary và đã thiết kế hành vi retry/khôi phục.

**runInTransaction: false không tự động chia một UPDATE lớn thành các batch nhỏ.** Một câu UPDATE có thể vẫn là một transaction do DBMS quản lý, vẫn giữ khóa và chiếm tài nguyên lớn. Cách chia batch cần được thiết kế ở SQL, job hoặc ứng dụng.

## 13. Precondition và kiểm soát điều kiện trước lệnh đặc biệt

Khi chọn false, nên tăng mức độ kiểm soát **trước** và **sau** thay đổi.

Trước CREATE INDEX CONCURRENTLY, cần kiểm tra:

- Bảng và cột đã tồn tại trong schema đúng.
- Tên index chưa được dùng cho một định nghĩa khác.
- Loại index/biểu thức được PostgreSQL hỗ trợ ở phiên bản đích.
- Không có index invalid từ lần triển khai trước.
- Database còn dung lượng và không có phiên long-running transaction gây chờ kéo dài ngoài dự kiến.
- Account migration đủ quyền và timeout đủ cho tác vụ.

Một precondition **indexExists** là kiểm tra tồn tại theo metadata, không xác minh toàn bộ cấu trúc, tính hợp lệ hoặc trạng thái xây dựng index. Nếu đã có index, nên **HALT** để người vận hành đánh giá; đừng mặc định **MARK_RAN**.

**onFail: HALT** được dùng khi điều kiện đánh giá được nhưng không thỏa mãn; **onError: HALT** khi chính việc đánh giá điều kiện gặp lỗi. Các điều kiện precondition không thay thế việc kiểm tra index **indisvalid** sau lệnh.

Không được coi **validate** là bằng chứng rằng PostgreSQL sẽ cho phép SQL chạy ngoài transaction. Validate kiểm tra cấu trúc changelog và một số điều kiện tĩnh; lỗi transaction của server chỉ xuất hiện khi SQL thực sự được thực thi trong đúng bối cảnh.

## 14. Tích hợp Spring Boot và CI/CD

Liquibase có thể chạy ngay khi Spring Boot khởi động hoặc chạy trong một job migration riêng của pipeline. Cấu hình chạy theo ứng dụng, ví dụ:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Khi một changeset **runInTransaction: false** mất nhiều thời gian, việc cho nhiều replica ứng dụng cùng khởi động và chờ migration có thể làm rollout chậm hoặc gặp timeout. Liquibase sử dụng DATABASECHANGELOGLOCK để điều phối, nhưng không loại bỏ thời gian xây dựng index, cạnh tranh tài nguyên hay timeout bên ngoài.

Với hệ thống production, job migration chuyên biệt thường giúp quan sát tiến trình và điều phối tốt hơn:

~~~text
Pull request
    |
    v
Validate changelog + review SQL
    |
    v
Test migration trên bản sao hoặc staging
    |
    v
Preflight metadata, quyền, locks, dung lượng
    |
    v
CI/CD migration job (Liquibase update)
    |
    v
Postflight: index hợp lệ + DATABASECHANGELOG đúng
    |
    v
Deploy phiên bản ứng dụng phụ thuộc thay đổi
~~~

**Lưu ý:** không giả định rằng **liquibase update-sql** sẽ cho bạn thấy toàn bộ hành vi giao dịch giống khi chạy update thật. Nó rất hữu ích để review SQL dự kiến, nhưng vẫn cần môi trường test dùng DBMS và phiên bản tương đương production.

Thiết lập timeout ở cả job CI/CD, JDBC, database và hạ tầng một cách nhất quán với đặc tính thao tác. Nếu lệnh index có thể mất nhiều thời gian, pipeline phải cung cấp log và dấu hiệu tiến độ; tắt timeout vô điều kiện hoặc cho phép retry tự động không kiểm tra trạng thái có thể làm tình hình tệ hơn.

Với rollout theo nhiều phiên bản ứng dụng, hãy xét **tương thích**: index phục vụ hiệu năng thường có thể tạo trước code sử dụng, còn thay đổi dữ liệu/schema bắt buộc cần được sắp thứ tự cùng ứng dụng cũ và mới.

## 15. Quy trình thực hành có kiểm chứng

Giả sử đã có PostgreSQL và Liquibase CLI kết nối đúng database test, với bảng purchase_order và customer_id:

**Bước 1 — Xem schema và lịch sử.** Kiểm tra bảng, cột, index cùng tên và DATABASECHANGELOG. Ghi nhận quy mô bảng, quyền và phiên bản PostgreSQL.

**Bước 2 — Thêm changeset CREATE INDEX CONCURRENTLY.** Dùng ví dụ mục 4 với **runInTransaction: false**, một SQL statement và rollback được review. Không đặt tên index trùng đối tượng khác.

**Bước 3 — Validate và review SQL.**

~~~shell
liquibase validate
liquibase update-sql
~~~

Lệnh giả định đã có liquibase.properties hoặc tham số tương đương cung cấp changelog, JDBC URL, driver và credentials.

**Bước 4 — Update trên test.**

~~~shell
liquibase update
liquibase status --verbose
~~~

Kiểm tra log để xác nhận changeset được thực thi mà không báo lỗi transaction block.

**Bước 5 — Postflight.** Truy vấn **pg_index.indisvalid**, **pg_indexes.indexdef** và DATABASECHANGELOG. Đo thời gian và tài nguyên, kiểm tra kế hoạch truy vấn khi có ý nghĩa. Đừng kết luận index hữu ích chỉ vì tạo thành công.

**Bước 6 — Thử lỗi có kiểm soát.** Trên một bản sao database, mô phỏng index cùng tên hoặc làm gián đoạn tác vụ theo phương án an toàn được phép; quan sát cách lịch sử và metadata có thể khác nhau. Không gây sự cố cố ý trên production.

**Bước 7 — Thử rollback hoặc forward-fix.** Kiểm chứng DROP INDEX CONCURRENTLY chỉ khi đủ điều kiện, đồng thời xác nhận Liquibase thực hiện rollback ngoài transaction nếu dùng SQL đó. Sau rollback, kiểm tra cả đối tượng database và DATABASECHANGELOG.

**Bước 8 — Đưa vào CI/CD.** Chạy cùng changelog đã review qua staging và production, kèm kiểm tra trạng thái index, giám sát locks và báo cáo kết quả trước khi triển khai ứng dụng.

Ví dụ kiểm tra lịch sử trên PostgreSQL:

~~~sql
SELECT id, author, filename, exectype, md5sum, dateexecuted
FROM databasechangelog
WHERE id = '010-create-order-customer-index-concurrently';
~~~

Nếu có dòng đã thực thi, tiếp tục xác minh index thực tế. Nếu không có dòng nhưng index tồn tại, **không chạy lại ngay** mà phải xác định đây là index hợp lệ từ một lần chạy dở hay đối tượng do bên khác tạo.

## 16. Các lỗi vận hành thường gặp

| Triệu chứng | Khả năng nguyên nhân | Hướng xử lý |
|---|---|---|
| “cannot run inside a transaction block” | Lệnh yêu cầu chạy ngoài transaction, changeset đang true | Tách lệnh, đặt runInTransaction false sau khi kiểm chứng DBMS |
| Index tồn tại sau khi job thất bại | CREATE INDEX CONCURRENTLY đã bắt đầu và để lại đối tượng | Kiểm tra indisvalid/indisready và DATABASECHANGELOG |
| Lần retry báo “relation already exists” | Lần trước tạo index hoặc để lại index invalid | Đối chiếu metadata, không MARK_RAN tự động |
| Index build chờ lâu | Long-running transaction, workload lớn, tài nguyên thấp | Kiểm tra session/locks, tiến trình xây index, timeout |
| Database báo đã có index nhưng query vẫn chậm | Index invalid, định nghĩa chưa phù hợp, planner không chọn | Kiểm tra định nghĩa/trạng thái, số liệu thống kê và kế hoạch truy vấn |
| Migration true mà DDL vẫn không rollback | DBMS có implicit commit hoặc DDL không transactional | Xác minh hành vi theo DBMS và chuẩn bị forward-fix |
| Migration false chạy được nhưng trạng thái nửa vời | Nhiều SQL một changeset hoặc lỗi sau tác động từng phần | Tách changeset, tăng postflight, có runbook phục hồi |
| Lock Liquibase còn giữ | Job còn chạy hoặc bị ngắt trước khi giải phóng lock | Xác minh tiến trình trước khi can thiệp DATABASECHANGELOGLOCK |
| Hibernate hoặc ứng dụng start timeout | Liquibase chạy dài khi khởi động | Chạy migration bằng job chuyên trách hoặc điều chỉnh rollout |
| Checksum không khớp sau khi sửa SQL | Chỉnh changeset đã triển khai | Khôi phục nội dung cũ, tạo changeset mới nếu cần đổi |

**Không sửa trực tiếp DATABASECHANGELOG**, không sử dụng clear-checksums hoặc releaseLocks như bước chữa chung cho tất cả các lỗi. Những thao tác này có thể che giấu khác biệt thực tế hoặc cho phép chạy chồng migration.

## 17. Bài tập tình huống

Nhóm có ba yêu cầu:

**Tình huống A:** thêm cột **customer.status** trên PostgreSQL bằng ALTER TABLE bình thường. Migration cần hoàn tác nếu câu lệnh trong changeset bị lỗi. **Lựa chọn:** giữ mặc định **runInTransaction: true** nếu DBMS/loại DDL hỗ trợ, đặt precondition phù hợp và kiểm thử rollback.

**Tình huống B:** tạo index trên bảng **purchase_order** đang có nhiều giao dịch ghi, dùng **CREATE INDEX CONCURRENTLY**. **Lựa chọn:** changeset riêng, **runInTransaction: false**, một câu SQL, kiểm tra metadata index trước và sau, kịch bản invalid index nếu lỗi.

**Tình huống C:** backfill 20 triệu bản ghi; transaction dài gây lock và transaction log lớn. **Lựa chọn:** không coi false là giải pháp đủ. Xây dựng batch idempotent, kiểm soát tốc độ, theo dõi tiến độ, phối hợp phiên bản ứng dụng và quyết định thực thi trong Liquibase hay job riêng sau khi đánh giá.

Câu hỏi tự kiểm tra: nếu changeset B báo lỗi nhưng có index cùng tên xuất hiện, có thể dùng **onFail: MARK_RAN** để bỏ qua không? **Không.** Phải kiểm tra định nghĩa, tính hợp lệ, nguồn gốc và lịch sử trước khi quyết định cách ghi nhận hoặc khôi phục. Một index invalid không tương đương một migration đã thành công.

## 18. Checklist quyết định runInTransaction

- [ ] Đã xác nhận chính xác DBMS, server version, Liquibase version và JDBC/executor.
- [ ] Đã biết lệnh có được chạy trong transaction block không.
- [ ] Giữ runInTransaction: true khi không có lý do thực tế để tắt.
- [ ] Nếu phải dùng false, mỗi changeset chỉ chứa thao tác độc lập nhỏ nhất có thể.
- [ ] Đã review trường hợp failure sau khi database áp dụng một phần thao tác.
- [ ] Đã xác định precondition bắt buộc và dùng onFail/onError phù hợp.
- [ ] Đã có câu truy vấn postflight xác minh đối tượng thực tế, không chỉ xem DATABASECHANGELOG.
- [ ] Đã xem SQL dự kiến và chạy thử trên DBMS tương thích với production.
- [ ] Đã kiểm tra lock, timeout, kết nối và tác động tới writer.
- [ ] Có kế hoạch rollback hoặc forward-fix được kiểm chứng, đặc biệt với lệnh không transaction.
- [ ] Đã xem xét phụ thuộc với ứng dụng Spring Boot/JPA và job CI/CD.
- [ ] Không sửa changeset đã triển khai, không làm sai lệch checksum và lịch sử.

Trong **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, **runInTransaction** là công cụ xác định ranh giới giao dịch cho từng changeset, không phải cờ bật/tắt an toàn của toàn hệ thống. Hãy ưu tiên transaction khi được hỗ trợ; chỉ dùng **false** cho lệnh có yêu cầu đặc biệt như **CREATE INDEX CONCURRENTLY**, và bù đắp phần mất đi của khả năng rollback nguyên tử bằng changeset nhỏ, precondition, kiểm tra metadata, runbook phục hồi và kiểm soát triển khai. Nhờ kết hợp các cơ chế này với DATABASECHANGELOGLOCK, checksum, lịch sử và CI/CD, nhóm có thể thực hiện migration đúng yêu cầu DBMS mà vẫn kiểm soát được rủi ro khi xảy ra lỗi.
