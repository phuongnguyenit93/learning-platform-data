# Kiểm tra hệ quản trị, người dùng và kết quả SQL

## 1. Vì sao migration cần kiểm tra tiền điều kiện?

Một changeset Liquibase có thể đúng về cú pháp nhưng vẫn không phù hợp với cơ sở dữ liệu đang được kết nối. Ví dụ: một lệnh dùng cú pháp riêng của PostgreSQL bị gửi đến MySQL; tài khoản triển khai thiếu quyền thay đổi bảng; hoặc dữ liệu thực tế chưa đáp ứng điều kiện để thêm ràng buộc. Những tình huống này thường chỉ lộ ra khi thực thi, có thể để lại trạng thái chưa hoàn chỉnh nếu hệ quản trị không hỗ trợ rollback toàn bộ DDL.

**Precondition** trong Liquibase là điều kiện được đánh giá trước khi thực hiện một changeset hoặc một phần quy trình changelog. Ở bài này, chúng ta học ba nhóm kiểm tra quan trọng:

- **dbms**: xác nhận hệ quản trị cơ sở dữ liệu thuộc loại dự kiến.
- **runningAs**: xác nhận tên người dùng database của kết nối đang thực thi Liquibase.
- **sqlCheck**: thực thi truy vấn SQL để kiểm chứng một bất biến hoặc trạng thái dữ liệu và so sánh kết quả với giá trị mong đợi.

Bài thuộc chương **Tiền điều kiện** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Mục tiêu toàn module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài tập trung vào việc kiểm tra **hệ quản trị, người dùng và kết quả SQL** trước khi cho phép migration thay đổi schema hoặc dữ liệu.

Sau bài học, bạn cần có thể giải thích cơ chế đánh giá precondition, viết được YAML cho ba điều kiện nói trên, phân biệt điều kiện không đạt với lỗi khi kiểm tra, biết khi nào nên dừng triển khai và thiết kế bài kiểm chứng trên database thử nghiệm.

## 2. Precondition đứng ở đâu trong vòng đời Liquibase?

Một lượt chạy có thể được hình dung như sau:

~~~text
Liquibase CLI / Spring Boot / CI pipeline
                   |
                   v
            Đọc changelog
                   |
                   v
         Chọn changeset phù hợp
        (context và label filter)
                   |
                   v
        Kiểm tra lịch sử changeset
            DATABASECHANGELOG
                   |
                   v
       Đánh giá precondition áp dụng
              /          \
           Đạt         Không đạt/lỗi
            |                 |
            v                 v
       Thực thi SQL       Áp dụng chính sách
            |            onFail / onError
            v
       Ghi lịch sử
       DATABASECHANGELOG
~~~

Đây là sơ đồ khái quát, không phải cam kết thứ tự nội bộ của mọi phiên bản Liquibase. Các precondition cấp changelog, changeset và cơ chế chạy lại như runOnChange có thời điểm đánh giá phụ thuộc loại lệnh và trạng thái changeset. Điều cần nắm là **precondition cho phép xác minh các giả định trước khi một thay đổi được thực thi**.

Precondition không thay thế quyền database, khóa triển khai, transaction, backup hoặc kiểm thử tích hợp. Một điều kiện đạt không chứng minh toàn bộ migration sẽ thành công: schema có thể thay đổi sau lúc kiểm tra, dữ liệu có thể biến động, hoặc câu lệnh DDL có thể gây khóa bảng trong thời gian dài.

## 3. Cú pháp cơ bản trong YAML

Precondition được khai báo bằng khóa **preConditions**. Tại cấp changeset, ví dụ tối thiểu:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-audit-view
      author: platform-team
      preConditions:
        - onFail: HALT
        - dbms:
            type: postgresql
      changes:
        - sql:
            sql: |
              CREATE OR REPLACE VIEW audit_customer_count AS
              SELECT COUNT(*) AS total FROM customer;
      rollback:
        - sql:
            sql: DROP VIEW IF EXISTS audit_customer_count;
~~~

Ví dụ giả định bảng **customer** đã có sẵn, tài khoản có quyền tạo view, và PostgreSQL chấp nhận định nghĩa đang được dùng. Điều kiện **dbms** bảo đảm changeset này được phép tiếp tục khi kết nối Liquibase sử dụng PostgreSQL. Nếu kết nối dùng DBMS khác, chính sách **onFail: HALT** sẽ dừng lượt cập nhật thay vì cố chạy câu SQL không tương thích.

Có thể đặt precondition ở hai phạm vi:

| Phạm vi | Vị trí | Mục đích thường gặp |
|---|---|---|
| Cấp changelog | Một mục preConditions trực tiếp trong databaseChangeLog | Điều kiện nền tảng cho lượt cập nhật, chẳng hạn yêu cầu hệ quản trị hoặc một trạng thái chung |
| Cấp changeset | preConditions bên trong changeSet | Điều kiện riêng cho thao tác, ví dụ role triển khai hoặc dữ liệu đã sẵn sàng |

Không phải mọi tùy chọn xử lý thất bại đều hợp lệ ở cả hai phạm vi. Đặc biệt, **CONTINUE** và **MARK_RAN** thường chỉ được dùng cho precondition cấp changeset; cấp changelog phù hợp với **HALT** hoặc **WARN** theo khả năng hỗ trợ của phiên bản Liquibase.

## 4. Điều kiện dbms: xác nhận loại hệ quản trị

### 4.1. Cách khai báo

Một changeset có thể dùng SQL đặc thù PostgreSQL:

~~~yaml
preConditions:
  - onFail: HALT
  - dbms:
      type: postgresql
~~~

Khóa **type** là định danh DBMS mà Liquibase nhận diện, chẳng hạn postgresql, mysql, mariadb, mssql, oracle hoặc h2 tùy hệ quản trị và phiên bản được hỗ trợ. Không tự suy đoán tên định danh từ nhãn marketing của sản phẩm; hãy đối chiếu với tài liệu phiên bản Liquibase đang dùng.

Nếu một changeset có SQL chung được phép chạy trên nhiều DBMS, có thể khai báo danh sách loại DBMS theo cú pháp Liquibase hỗ trợ, chẳng hạn:

~~~yaml
preConditions:
  - dbms:
      type: postgresql,mysql
~~~

Tuy nhiên, việc cho phép hai DBMS chỉ có nghĩa điều kiện lựa chọn hợp lệ; **không bảo đảm SQL bên dưới tương thích cả hai**. Các lệnh tạo chỉ mục, thay đổi kiểu dữ liệu, tạo function hoặc procedure có thể khác biệt đáng kể. Khi SQL phụ thuộc DBMS, nên chia rõ changeset hoặc chọn change type có cấu trúc để Liquibase xử lý một phần sự khác biệt cú pháp.

### 4.2. dbms thực sự kiểm tra điều gì?

Điều kiện **dbms** xác định loại hệ quản trị của kết nối thông qua thông tin mà Liquibase/JDBC nhận diện. Nó **không xác nhận**:

- Đây là database development, test hay production.
- Đây là schema hoặc tenant dự định triển khai.
- User đang có đủ quyền DDL/DML.
- Phiên bản máy chủ hỗ trợ mọi tính năng SQL được dùng.
- Mạng, cấu hình TLS hoặc quyền truy cập bảng sau đó đều an toàn.

Ví dụ một hệ thống có cả dev và production đều dùng PostgreSQL. Precondition dbms: postgresql sẽ đạt trên cả hai, dù JDBC URL của pipeline vô tình trỏ nhầm vào production. Vì vậy, dbms là **điều kiện tương thích kỹ thuật**, không phải cơ chế phân quyền hoặc rào chắn môi trường.

### 4.3. Khi nào dùng dbms?

Các tình huống phù hợp gồm kiểm soát lệnh CREATE OR REPLACE FUNCTION chỉ viết cho PostgreSQL, một loại chỉ mục đặc thù DBMS, cú pháp thay đổi cột khác nhau giữa database, hoặc một script SQL không thể diễn đạt đầy đủ bằng change type đa nền tảng.

Với schema cốt lõi và nhiều DBMS, hãy ưu tiên cơ chế migration nhất quán, có thử nghiệm trên từng DBMS được hỗ trợ. Nếu precondition dbms không đạt, chính sách xử lý cần phản ánh mục tiêu: một changeset bắt buộc thì thường **HALT**; một thay đổi riêng cho PostgreSQL trong sản phẩm đa DBMS có thể được tổ chức để không chạy ở DBMS khác theo kế hoạch, thay vì âm thầm bỏ qua một thay đổi thiết yếu.

## 5. Điều kiện runningAs: xác nhận người dùng của kết nối

### 5.1. Ví dụ khai báo

Giả sử quy trình triển khai được phép sử dụng tài khoản **lb_migrator**:

~~~yaml
preConditions:
  - onFail: HALT
  - runningAs:
      username: lb_migrator
~~~

Nếu tên người dùng của kết nối đang chạy Liquibase không đáp ứng điều kiện, precondition không đạt và Liquibase xử lý theo onFail. Đây là một phép kiểm tra hữu ích để tránh dùng nhầm tài khoản ứng dụng thường ngày khi migration đòi hỏi quyền thay đổi schema.

### 5.2. runningAs không thay thế kiểm tra quyền

**runningAs** so sánh danh tính database của kết nối với tên được cấu hình. Điều đó không chứng minh:

- User còn có quyền CREATE/ALTER/DROP trên schema đích.
- Role đã được cấp đúng theo chính sách tối thiểu quyền.
- User chỉ truy cập được database mong muốn.
- Kết nối đang ở đúng host, database hoặc schema.
- Tài khoản đã được xác thực bằng cơ chế bảo mật đạt chuẩn.

Hơn nữa, một số DBMS có quy tắc chuẩn hóa chữ hoa/chữ thường, user/role, proxy user và session authorization riêng. Ví dụ PostgreSQL có phân biệt **current_user** và **session_user** trong tình huống SET ROLE hoặc thay đổi ngữ cảnh quyền. Nếu tổ chức sử dụng cơ chế role phức tạp, cần kiểm chứng hành vi runningAs trên kết nối thực tế thay vì chỉ dựa vào tên mong đợi trên giấy.

### 5.3. Tách người dùng migration và runtime

Nên xem xét hai loại tài khoản:

| Vai trò | Mục đích | Quyền khuyến nghị |
|---|---|---|
| lb_migrator | Chạy Liquibase trong bước phát hành | Quyền DDL/DML cần thiết trên schema được chỉ định; truy cập bảng lịch sử Liquibase |
| app_runtime | Ứng dụng phục vụ yêu cầu của người dùng | Chỉ quyền đọc/ghi dữ liệu nghiệp vụ cần thiết; hạn chế thay đổi schema |

Khi Spring Boot tự chạy Liquibase bằng DataSource chung, người vận hành cần đánh giá liệu quyền của kết nối ứng dụng có quá rộng hay không. Có thể cấu hình kết nối migration riêng hoặc tách migration thành job CI/CD, tùy kiến trúc. Điều kiện runningAs giúp kiểm tra **tên tài khoản được sử dụng**, còn cơ chế phân quyền DBMS mới thực sự thực thi giới hạn quyền.

## 6. Điều kiện sqlCheck: kiểm tra kết quả truy vấn SQL

### 6.1. Nguyên tắc

**sqlCheck** cho phép chạy một truy vấn SQL và so sánh kết quả với **expectedResult**. Truy vấn cần trả về một giá trị đơn giản mà Liquibase có thể so sánh với giá trị kỳ vọng, thường lấy từ ô đầu tiên của dòng đầu tiên trong tập kết quả.

Ví dụ trước khi thêm ràng buộc UNIQUE, cần xác nhận không có email trùng lặp trong bảng customer:

~~~yaml
preConditions:
  - onFail: HALT
  - sqlCheck:
      expectedResult: "0"
      sql: |
        SELECT COUNT(*)
        FROM (
            SELECT email
            FROM customer
            WHERE email IS NOT NULL
            GROUP BY email
            HAVING COUNT(*) > 1
        ) AS duplicate_emails
~~~

Nếu truy vấn trả về **0**, điều kiện đạt. Nếu có một hay nhiều nhóm email trùng, kết quả khác 0 và migration dừng. Ví dụ sử dụng cú pháp SQL tương đối phổ biến, nhưng vẫn phải kiểm tra trên DBMS được dùng.

**Điều kiện này không tự làm sạch dữ liệu**. Nó chỉ phát hiện tình trạng không đạt yêu cầu. Trước khi thêm UNIQUE, nhóm vẫn phải quyết định nghiệp vụ khi gặp email trùng: hợp nhất, sửa dữ liệu, loại bỏ dòng hay hoãn phát hành.

### 6.2. Lựa chọn kết quả ổn định

Hãy viết sqlCheck theo các quy tắc:

1. **Trả về đúng một giá trị**, tốt nhất là COUNT hoặc CASE biểu diễn trạng thái.
2. **So sánh với biểu diễn rõ ràng**, ví dụ expectedResult: "0" hoặc "OK".
3. **Giới hạn schema và bảng cụ thể**, không dựa vào search path ngầm khi triển khai nhiều schema.
4. **Ưu tiên SELECT không có tác dụng phụ**, tránh câu SQL cập nhật dữ liệu trong precondition.
5. **Dự tính hiệu năng**, vì COUNT trên bảng lớn có thể tốn thời gian, I/O hoặc khóa tùy DBMS.
6. **Không gắn dữ liệu nhạy cảm vào lỗi hoặc log** chỉ để giải thích vì sao điều kiện không đạt.

Với những kiểm tra kiểu dữ liệu có định dạng phức tạp, kết quả NULL, số thực hoặc timestamp, cách chuyển kiểu và so sánh có thể khác giữa driver/DBMS. Một lệnh trả về **0.0** có thể không được đối chiếu giống **"0"** trong mọi bối cảnh. Nên chuẩn hóa thành chuỗi hoặc số nguyên ổn định và kiểm thử chính xác trên runtime thực tế.

### 6.3. Phân biệt không đạt và lỗi kiểm tra

Nếu truy vấn chạy thành công và trả giá trị **khác expectedResult**, đó là trường hợp **precondition không đạt** (*fail*). Nếu truy vấn không chạy được vì bảng không tồn tại, thiếu quyền, lỗi cú pháp hoặc lỗi kết nối, đó có thể là **lỗi đánh giá precondition** (*error*).

Hai tình huống cần cách xử lý khác nhau: một kết quả “còn dữ liệu trùng” là thông tin nghiệp vụ; một lỗi “không thể truy vấn” cho thấy việc kiểm tra chưa đưa ra kết luận đáng tin cậy. **onFail** kiểm soát trường hợp điều kiện không đạt; **onError** kiểm soát lỗi phát sinh khi đánh giá.

## 7. Kết hợp dbms, runningAs và sqlCheck trong một changeset

Ví dụ dưới đây dành cho **PostgreSQL trong database học tập shop_test**. Chúng ta muốn thêm cột **orders.note**, nhưng chỉ sau khi xác nhận:

- Kết nối sử dụng PostgreSQL.
- Liquibase chạy bằng tài khoản lb_migrator.
- Database hiện tại là shop_test.
- Bảng orders đã tồn tại trong schema app.
- Cột note chưa có, để tránh chèn lại một cấu trúc đã tồn tại.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 004-add-order-note
      author: platform-team
      comment: Thêm cột ghi chú cho đơn hàng sau khi kiểm tra môi trường
      preConditions:
        - onFail: HALT
        - onError: HALT
        - dbms:
            type: postgresql
        - runningAs:
            username: lb_migrator
        - sqlCheck:
            expectedResult: "shop_test"
            sql: SELECT current_database()
        - tableExists:
            schemaName: app
            tableName: orders
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM information_schema.columns
              WHERE table_schema = 'app'
                AND table_name = 'orders'
                AND column_name = 'note'
      changes:
        - addColumn:
            schemaName: app
            tableName: orders
            columns:
              - column:
                  name: note
                  type: VARCHAR(500)
      rollback:
        - dropColumn:
            schemaName: app
            tableName: orders
            columnName: note
~~~

### Giải thích các bước

**dbms** loại trừ việc chạy nhầm cú pháp/logic PostgreSQL trên DBMS khác. **runningAs** kiểm tra tên user. **sqlCheck thứ nhất** kiểm tra database hiện tại bằng hàm PostgreSQL current_database(). **tableExists** xác nhận bảng nguồn. **sqlCheck thứ hai** kiểm tra metadata, bảo đảm cột note chưa có.

Trong preConditions YAML, nhiều điều kiện cùng cấp thường được hiểu là kết hợp **AND** ngầm định: tất cả phải đạt để tiếp tục. Nếu bất kỳ điều kiện nào không đạt, chính sách onFail: HALT dừng lượt cập nhật; nếu đánh giá gặp lỗi, onError: HALT cũng dừng.

**Lưu ý:** current_database() là hàm PostgreSQL. Ví dụ này chỉ dành cho PostgreSQL, không dùng nguyên dạng cho MySQL, SQL Server hoặc Oracle. Để triển khai thật, hãy dùng đúng tên DB/schema/user thực tế, loại bỏ việc hardcode shop_test nếu dùng chung artifact cho các môi trường khác, và cấp giá trị môi trường thông qua cấu hình được kiểm soát.

### Giới hạn của ví dụ

Precondition giúp chặn tình huống đã biết, nhưng vẫn có những rủi ro:

- Một user đúng tên vẫn có thể thiếu quyền ALTER TABLE.
- Schema app có thể thay đổi ngoài lịch sử Liquibase.
- Giữa lúc kiểm tra cột chưa tồn tại và khi chạy DDL, tiến trình khác vẫn có thể thay đổi schema; cơ chế khóa Liquibase chỉ điều phối các tiến trình tuân theo cùng lịch sử Liquibase.
- Rollback **dropColumn** sẽ xóa dữ liệu đã được ghi vào note; không thể coi đây là rollback an toàn sau khi ứng dụng bắt đầu sử dụng cột.
- Việc kiểm tra chỉ dựa vào tên database shop_test là không đủ nếu nhiều máy chủ có database cùng tên. Pipeline còn phải xác minh host/port, chứng chỉ, tài khoản và danh tính cluster.

Một quy trình production nên tách việc xác minh đúng đích khỏi các precondition riêng của changeset, đồng thời bổ sung đánh giá khóa bảng, thời gian thực thi và kế hoạch khôi phục.

## 8. Sử dụng AND, OR và NOT khi điều kiện phức tạp

Liquibase hỗ trợ các điều kiện logic dạng **and**, **or** và **not** để tổ chức tập kiểm tra.

### 8.1. AND: tất cả phải đạt

~~~yaml
preConditions:
  - onFail: HALT
  - and:
      - dbms:
          type: postgresql
      - runningAs:
          username: lb_migrator
~~~

Ở đây, PostgreSQL và tên user phù hợp là hai điều kiện đồng thời bắt buộc. Có thể đạt hiệu quả tương tự bằng hai điều kiện cùng cấp nếu không cần cấu trúc lồng.

### 8.2. OR: một trong các nhánh đạt

~~~yaml
preConditions:
  - onFail: HALT
  - or:
      - dbms:
          type: postgresql
      - dbms:
          type: mysql
~~~

Điều kiện đạt nếu DBMS là PostgreSQL hoặc MySQL. Nhưng hãy nhớ SQL bên trong changeset **phải tương thích với cả hai**, hoặc được tách thành các thay đổi thích hợp. OR không tự chuyển cú pháp SQL giữa DBMS.

### 8.3. NOT: phủ định một điều kiện

~~~yaml
preConditions:
  - onFail: HALT
  - not:
      - runningAs:
          username: app_runtime
~~~

Đây là ví dụ về việc từ chối chạy bằng một tài khoản ứng dụng cụ thể. Trong thực tế, **kiểm tra user được phép** bằng runningAs: lb_migrator thường chặt chẽ hơn việc chỉ loại trừ một username, bởi có thể tồn tại nhiều username khác không được phê duyệt.

### 8.4. Đánh giá ngắn mạch và thông báo lỗi

Các nhóm logic có thể được Liquibase đánh giá theo cơ chế ngắn mạch; một điều kiện thất bại có thể khiến những điều kiện kế tiếp không được đánh giá. Vì vậy, đừng dùng precondition để thu thập đầy đủ báo cáo sức khỏe của database. Nếu cần nhiều kết quả kiểm tra độc lập, nên chạy một bước kiểm tra chuyên dụng ngoài migration và xuất báo cáo trước khi cho phép update.

## 9. onFail và onError: điều gì xảy ra khi kiểm tra thất bại?

Cùng một bộ kiểm tra có thể dẫn đến các hành vi khác nhau. Cần hiểu chính sách trước khi đặt vào production.

| Giá trị | Ý nghĩa khái quát | Lưu ý vận hành |
|---|---|---|
| **HALT** | Dừng quá trình cập nhật. | Lựa chọn mặc định an toàn cho điều kiện bắt buộc và bất định. |
| **WARN** | Ghi cảnh báo và tiếp tục xử lý theo phạm vi được hỗ trợ. | Chỉ dùng khi việc tiếp tục được chấp nhận rõ ràng. |
| **CONTINUE** | Bỏ qua changeset hiện tại trong lượt này rồi tiếp tục, không đánh dấu như đã chạy. | Dùng ở cấp changeset khi thay đổi thật sự tùy chọn; có thể được xét lại ở lần chạy sau. |
| **MARK_RAN** | Không thực thi thay đổi nhưng ghi changeset như đã chạy. | Chỉ dùng nếu database đã ở trạng thái tương đương kết quả mong muốn. |

Các giá trị này có phạm vi áp dụng theo vị trí precondition và phiên bản Liquibase; **CONTINUE** và **MARK_RAN** chỉ phù hợp ở cấp changeset. Với kiểm tra dbms, runningAs hay sqlCheck có tính bảo vệ an toàn, **HALT** thường là chính sách dễ giải thích và kiểm chứng nhất.

### 9.1. Ví dụ phân biệt lỗi và điều kiện không đạt

~~~yaml
preConditions:
  - onFail: HALT
  - onError: HALT
  - onFailMessage: "Dữ liệu chưa đáp ứng điều kiện migration"
  - onErrorMessage: "Không thể đánh giá precondition an toàn"
  - sqlCheck:
      expectedResult: "0"
      sql: SELECT COUNT(*) FROM app.customer WHERE email IS NULL
~~~

Nếu truy vấn trả về 3, onFail áp dụng. Nếu tài khoản thiếu quyền đọc app.customer, onError áp dụng. Các trường hợp đều phải dừng theo cấu hình trên.

Thông báo tùy chỉnh nên mô tả giả định đã không được xác nhận; tránh đưa mật khẩu, token, dữ liệu khách hàng hoặc cả câu truy vấn nhạy cảm vào message. Tên thuộc tính và hỗ trợ thông báo tùy chỉnh cần được kiểm tra trên phiên bản Liquibase đã chốt.

### 9.2. Khi nào MARK_RAN có thể nguy hiểm?

Giả sử changeset cần thêm cột note, nhưng sqlCheck cho biết bảng orders không tồn tại. Nếu dùng MARK_RAN, Liquibase có thể ghi nhận changeset là đã chạy dù **cột note chưa hề được tạo**. Các lần chạy sau có thể bỏ qua changeset này, khiến schema và lịch sử triển khai lệch nhau.

Chỉ dùng MARK_RAN khi nhóm đã xác nhận trạng thái database **thực sự đáp ứng kết quả dự kiến**. Ví dụ migration được áp dụng trước đó bằng quy trình khác và có bằng chứng kiểm chứng đầy đủ. Đây không phải công cụ để giúp pipeline luôn hiển thị màu xanh.

## 10. Kiểm tra tại cấp changelog

Có thể yêu cầu toàn bộ changelog chỉ được xử lý trên một loại DBMS:

~~~yaml
databaseChangeLog:
  - preConditions:
      - onFail: HALT
      - onError: HALT
      - dbms:
          type: postgresql

  - changeSet:
      id: 001-create-settings
      author: platform-team
      changes:
        - createTable:
            tableName: app_setting
            columns:
              - column:
                  name: setting_key
                  type: VARCHAR(100)
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Precondition cấp changelog phù hợp với giả định áp dụng rộng cho cả bộ migration. Tuy nhiên, nếu module cố ý hỗ trợ nhiều DBMS hoặc phần changelog chứa một số thay đổi dành riêng cho PostgreSQL, điều kiện quá rộng sẽ chặn cả thay đổi không liên quan. Khi đó nên cân nhắc tổ chức changeset và precondition riêng đúng phạm vi.

Một precondition kiểm tra user ở cấp toàn changelog cũng có thể làm việc phát triển cục bộ khó dùng nếu mọi lập trình viên có username khác nhau. Quyết định nên dựa trên thiết kế vận hành cụ thể, thay vì sao chép điều kiện production lên mọi môi trường mà không phân tích.

## 11. Kiểm tra dữ liệu trước migration có rủi ro

**sqlCheck** đặc biệt hữu ích khi một thay đổi schema phụ thuộc vào dữ liệu đang tồn tại:

| Migration dự kiến | Câu hỏi cần kiểm tra trước | Mẫu sqlCheck |
|---|---|---|
| Thêm UNIQUE(email) | Có email bị trùng không? | Đếm số nhóm có COUNT lớn hơn 1 |
| Chuyển cột sang NOT NULL | Có giá trị NULL không? | SELECT COUNT(*) ... WHERE column IS NULL |
| Tạo khóa ngoại | Có dòng con không có cha không? | SELECT COUNT(*) ... LEFT JOIN ... WHERE parent.id IS NULL |
| Đổi kiểu VARCHAR sang số | Có dữ liệu không chuyển được không? | Kiểm tra theo quy tắc chuyển kiểu và DBMS cụ thể |
| Xóa trạng thái cũ | Còn dữ liệu đang tham chiếu trạng thái đó không? | Đếm bản ghi còn dùng trạng thái cần xóa |
| Backfill dữ liệu | Dữ liệu nguồn đã đầy đủ và không mâu thuẫn chưa? | Kiểm tra tổng số hoặc bất biến nghiệp vụ |

Ví dụ trước khi thêm NOT NULL cho customer.phone_number:

~~~yaml
preConditions:
  - onFail: HALT
  - sqlCheck:
      expectedResult: "0"
      sql: |
        SELECT COUNT(*)
        FROM app.customer
        WHERE phone_number IS NULL
~~~

Kết quả 0 chỉ xác nhận **tại thời điểm đọc**, không đảm bảo một tiến trình khác không ghi NULL ngay sau đó. Với hệ thống có ghi dữ liệu đồng thời, cần phối hợp hành vi ứng dụng, transaction hoặc khóa/ràng buộc thích hợp; thông thường triển khai theo các giai đoạn expand–migrate–contract để tránh áp ràng buộc quá sớm.

**Lưu ý về SQL có tác dụng phụ:** precondition được thiết kế để kiểm tra. Không dùng UPDATE, DELETE, INSERT hoặc hàm có tác dụng phụ trong sqlCheck để sửa dữ liệu trước khi changeset chạy. Một thao tác kiểm tra nên có kết quả có thể lặp lại và không thay đổi trạng thái nghiệp vụ.

## 12. Kết quả sqlCheck cần đáng tin cậy

Có một số mẫu giúp kết quả so sánh ổn định.

### 12.1. Trả về số lượng vi phạm

~~~sql
SELECT COUNT(*)
FROM app.orders
WHERE total_amount < 0;
~~~

Với expectedResult: "0", điều kiện đạt khi không có dòng có tổng tiền âm. Đây chỉ là một kiểm tra dữ liệu mẫu; nghiệp vụ có thể cho phép số âm trong trường hợp hoàn tiền, nên bất biến phải được xác định từ yêu cầu thực tế.

### 12.2. Dùng CASE trả về chuỗi trạng thái

Ví dụ chỉ dành cho PostgreSQL:

~~~sql
SELECT CASE
         WHEN current_database() = 'shop_test'
          AND current_schema() = 'app'
         THEN 'OK'
         ELSE 'BLOCK'
       END;
~~~

Trong YAML, đặt **expectedResult: "OK"**. Đây là một cách rõ ràng để kết hợp kiểm tra database và schema của kết nối. Tuy nhiên, current_schema() phụ thuộc search_path hiện tại và không bảo đảm mọi câu DDL sẽ sử dụng schema đó nếu chúng có schemaName riêng. Cần kiểm tra SQL cuối cùng và cấu hình Liquibase.

### 12.3. Tránh truy vấn không trả dòng

Nếu SELECT không trả hàng nào, đừng giả định Liquibase sẽ hiểu tương đương 0 hoặc chuỗi rỗng. Hãy viết truy vấn dạng COUNT, EXISTS được chuyển thành CASE, hoặc truy vấn tổng hợp được bảo đảm trả về một giá trị. Ngoài ra, hãy tránh trả NULL khi ý nghĩa “không đạt” cần được biểu diễn tường minh.

### 12.4. Xử lý hiệu năng

Một truy vấn sqlCheck trên bảng rất lớn có thể chạy lâu. Chẳng hạn kiểm tra trùng email bằng GROUP BY trên hàng chục triệu dòng có thể tiêu thụ nhiều bộ nhớ và I/O. Trong CI/CD, nên đo hiệu năng trên dữ liệu đại diện, dùng chỉ mục hoặc câu truy vấn được tối ưu khi phù hợp, và thiết lập timeout/cảnh báo ở tầng vận hành.

Không nên bỏ điều kiện bắt buộc chỉ vì nó chậm; hãy xem có thể kiểm tra dữ liệu trước bằng job riêng, đo kết quả có thể kiểm chứng và đặt một điều kiện cuối ngắn gọn ngay trước DDL hay không.

## 13. Kiểm tra danh tính database và giới hạn bảo vệ

Một sai lầm phổ biến là coi ba điều kiện dbms, runningAs và sqlCheck như một hệ thống xác thực toàn diện. Chúng kiểm tra những gì được khai báo, không bảo đảm mọi yếu tố vận hành.

### 13.1. Ví dụ rủi ro trỏ nhầm

Cả development và production đều sử dụng PostgreSQL và đều có role lb_migrator. Một pipeline chạy với JDBC URL production nhưng dùng changelog chung. Khi đó:

- **dbms: postgresql** đạt.
- **runningAs: lb_migrator** đạt.
- Một sqlCheck chỉ kiểm tra bảng orders tồn tại cũng đạt.
- Migration vẫn có thể tác động đến production, dù người vận hành định chạy test.

Để giảm rủi ro, cần kiểm tra **host/cluster, tên database, schema, tài khoản và quyền** theo allowlist của môi trường. Trong production, secret chỉ nên có sẵn cho job được phê duyệt, đồng thời có bước xác minh đích độc lập trước update.

### 13.2. Precondition khác preflight của pipeline

**Precondition trong changelog** là kiểm tra gần thay đổi cụ thể và có thể được lưu cùng changeset. **Preflight trong pipeline** xác nhận các yếu tố lớn hơn như release/commit, môi trường, phê duyệt, backup, secret, trạng thái database, thời gian triển khai và đối tượng bị tác động.

Hai lớp kiểm tra bổ trợ nhau. Không nên dồn mọi chính sách triển khai vào một sqlCheck rồi cho rằng nó thay thế được quy trình phê duyệt hoặc phân quyền.

## 14. Phối hợp với contexts, labels và môi trường

Liquibase có thể chọn tập changeset bằng **context filter** và **label filter**. Một changeset không được chọn bởi các bộ lọc có thể không được xét thực thi trong lượt update đó, bất kể precondition của nó sẽ đạt hay không.

Ví dụ, một changeset nạp dữ liệu demo chỉ dành cho dev có thể mang **contextFilter: "@dev"** và precondition kiểm tra dữ liệu đích. Dấu @ yêu cầu ngữ cảnh được chỉ định rõ trong những phiên bản Liquibase hỗ trợ cú pháp này, nhưng **không phải hàng rào bảo mật**: nếu pipeline production vô tình truyền dev, changeset vẫn có thể được xét.

Không dùng điều kiện dbms hay runningAs thay thế bộ lọc môi trường. Ngược lại, cũng không dùng context/label thay cho kiểm tra DBMS hoặc quyền khi SQL đòi hỏi tính năng đặc biệt.

Khi một thay đổi schema là bắt buộc cho ứng dụng ở mọi môi trường, đừng cấu hình để nó chỉ chạy trong một context tùy chọn. Điều kiện tiền đề cần thể hiện **trạng thái bắt buộc**, còn context/label thể hiện **phạm vi lựa chọn** theo chính sách được review.

## 15. Tích hợp trong Spring Boot và CI/CD

Khi Spring Boot có liquibase-core trên classpath và kích hoạt Liquibase lúc khởi động, các precondition trong changelog cũng được đánh giá theo cấu hình Liquibase đang chạy. Nếu precondition HALT thất bại, quá trình migration có thể khiến ứng dụng không hoàn tất khởi động. Điều này thường thích hợp hơn việc ứng dụng chạy với schema không tương thích, nhưng cần chiến lược khởi động và rollback phù hợp trong môi trường có nhiều replica.

Một pipeline CI/CD có thể dùng trình tự:

1. Xác nhận **phiên bản Java, Liquibase, JDBC driver và artifact changelog**.
2. Kiểm tra đúng **database, schema, JDBC URL, role và quyền** bằng bước chỉ đọc.
3. Chạy **liquibase validate** để kiểm tra changelog theo khả năng của công cụ.
4. Chạy **liquibase status --verbose** để xem changeset dự kiến.
5. Chạy **liquibase update-sql** để review SQL dự kiến trước khi thực thi.
6. Thử migration và precondition trên database test với dữ liệu đại diện.
7. Review backup, kế hoạch rollback hoặc forward fix trước production.
8. Chạy **liquibase update** bằng job được ủy quyền; theo dõi log, kết quả và bảng DATABASECHANGELOG.
9. Kiểm tra schema, dữ liệu và hành vi ứng dụng sau triển khai.

Lệnh minh họa:

~~~bash
liquibase --defaults-file=liquibase.properties validate
liquibase --defaults-file=liquibase.properties status --verbose
liquibase --defaults-file=liquibase.properties update-sql
~~~

Trong tài liệu hoặc phiên bản cũ, lệnh xem trước SQL có thể được viết theo dạng updateSQL. Hãy dùng đúng cú pháp CLI của phiên bản đang chạy. **Việc sinh SQL ở chế độ xem trước có thể có cách xử lý precondition khác với chạy update**, tùy tùy chọn và phiên bản; cần kiểm chứng trên đúng công cụ. Không được suy ra rằng output update-sql luôn là bằng chứng mọi precondition đã được đánh giá với cùng tác dụng như update thực tế.

Việc sử dụng Spring Boot hay CI/CD làm chủ sở hữu migration cần được quyết định rõ. Nếu cả pipeline và từng replica ứng dụng cùng chạy Liquibase, bảng DATABASECHANGELOGLOCK giúp điều phối các tiến trình nhưng không thay thế kế hoạch triển khai hay ngăn version cũ làm thay đổi schema theo ý định khác.

## 16. Kiểm thử precondition theo cả nhánh đạt và nhánh không đạt

Một bài thực hành có kiểm chứng không chỉ chạy một lần trên database “đúng”. Nên tạo các tình huống giả lập ở môi trường học tập:

| Tình huống | Điều kiện kỳ vọng | Kết quả cần quan sát |
|---|---|---|
| PostgreSQL, đúng user, đúng DB, không có cột note | Tất cả đạt | Changeset thực thi; cột note xuất hiện |
| PostgreSQL, sai username | runningAs không đạt | HALT; cột chưa được tạo |
| PostgreSQL, sai database | sqlCheck current_database không đạt | HALT; không cập nhật nhầm schema |
| MySQL thay vì PostgreSQL | dbms không đạt | HALT trước SQL đặc thù PostgreSQL |
| PostgreSQL, cột note đã tồn tại | sqlCheck số cột trả 1 | HALT; không chạy addColumn lặp |
| Bảng orders không tồn tại | tableExists không đạt | HALT; điều tra thứ tự changelog |
| Thiếu quyền đọc metadata | sqlCheck lỗi hoặc trả kết quả không mong đợi | onError/onFail theo tình huống; điều tra quyền |
| Truy vấn sqlCheck lỗi cú pháp | Lỗi đánh giá | onError: HALT; không đánh dấu thành công |

Một quy trình thử cụ thể:

1. Tạo database test riêng và bảng orders theo cấu trúc đầu vào.
2. Cấp đúng username đã dùng trong runningAs.
3. Chạy validate và update-sql; kiểm tra SQL không nhắm tới bảng ngoài phạm vi.
4. Chạy update ở tình huống đạt; xác minh cột, DATABASECHANGELOG và ứng dụng.
5. Khôi phục database test hoặc tạo bản sao sạch để thử từng nhánh không đạt.
6. Ghi lại lỗi của Liquibase, phân biệt fail và error, kiểm tra changeset không bị ghi nhận sai.
7. Thử rollback/khôi phục trên dữ liệu giả nếu thay đổi có thể ảnh hưởng dữ liệu.
8. Chỉ dùng kết quả thử nghiệm để kết luận trên cùng DBMS/phiên bản và cấu hình tương ứng.

Cần nhớ **tiền điều kiện được đánh giá ở mỗi lần Liquibase xét changeset theo cơ chế hoạt động**, còn một changeset bình thường đã được ghi nhận thành công sẽ không tự chạy lại trong các lượt update sau. Không nên mong thay đổi sqlCheck trong một changeset đã triển khai sẽ tự kiểm tra lại mọi môi trường nếu chưa có cơ chế được thiết kế tương ứng.

## 17. Phân tích ba tình huống thực tế

### Tình huống A: thêm UNIQUE khi dữ liệu đã trùng

Nhóm muốn thêm unique constraint cho customer.email. sqlCheck trả kết quả 3 nhóm email trùng. Nếu dùng onFail: HALT, migration dừng.

**Hướng xử lý:** không bỏ điều kiện để chạy tiếp. Phải xác định chính sách xử lý khách hàng trùng, làm sạch dữ liệu bằng một migration có kiểm chứng, kiểm tra lại và mới bổ sung ràng buộc. Nếu production có dữ liệu lớn, cân nhắc tác động của việc tạo unique index và thời gian khóa bảng.

### Tình huống B: đúng DBMS và username nhưng sai môi trường

Pipeline test dùng JDBC URL production. DBMS là PostgreSQL và username cũng là lb_migrator, nên hai precondition đầu đều đạt.

**Hướng xử lý:** bổ sung xác minh database và schema theo whitelist ở tầng pipeline, dùng secret/role khác nhau giữa môi trường, khóa quyền chạy production theo job được phê duyệt. Không dùng tên job hoặc một username chung làm bằng chứng duy nhất.

### Tình huống C: sqlCheck báo lỗi, người vận hành muốn MARK_RAN

Một changeset thêm cột note gặp lỗi sqlCheck vì role thiếu quyền đọc information_schema hoặc bảng chưa có. Người vận hành đề xuất MARK_RAN để pipeline chạy tiếp.

**Hướng xử lý:** đó là cách che giấu trạng thái chưa biết. Dừng triển khai, tìm nguyên nhân thiếu quyền hoặc thứ tự migration; kiểm tra lại trạng thái thực trước khi thay đổi. MARK_RAN chỉ có thể được xem xét khi có bằng chứng rằng kết quả của changeset đã thực sự tồn tại, chứ không nhằm bỏ qua lỗi đánh giá.

## 18. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| dbms không đạt dù SQL nhìn có vẻ tương thích | Đang kết nối DBMS khác hoặc định danh type sai | Kiểm tra JDBC URL, driver, metadata DBMS, tên type Liquibase hỗ trợ |
| runningAs không đạt | Sai account, thay đổi role/session hoặc quy tắc username | Kiểm tra current_user/session_user và danh tính kết nối trên đúng DBMS |
| sqlCheck trả kết quả khác 0 | Dữ liệu vi phạm điều kiện | Truy vấn read-only để phân tích dữ liệu, không dùng MARK_RAN để bỏ qua |
| sqlCheck lỗi vì không có bảng | Sai thứ tự changelog, schema hoặc quyền truy cập | Kiểm tra tableExists, schemaName và changeset tạo bảng |
| sqlCheck dùng đúng SQL nhưng chạy quá lâu | Truy vấn quét bảng lớn, thiếu index | Xem query plan trên test đại diện, tối ưu kiểm tra và timeout |
| expectedResult không khớp do định dạng | Kết quả NULL, số thực, khoảng trắng hoặc cách chuyển kiểu | Chuẩn hóa kết quả thành COUNT hoặc CASE đơn giản |
| Precondition đạt nhưng DDL bị từ chối | User thiếu quyền thay đổi schema | Kiểm tra quyền DDL thực tế; runningAs chỉ kiểm tên user |
| Kiểm tra đạt trên test nhưng sai trên production | Dữ liệu, phiên bản DBMS, schema hoặc cấu hình khác nhau | Thử trên dữ liệu đại diện, xác minh đích và SQL dự kiến |
| Cột đã có nhưng changeset vẫn định thêm | Bản ghi lịch sử lệch schema thực tế hoặc kiểm tra sai schema | Điều tra drift và DATABASECHANGELOG, không tự xóa lịch sử |
| update-sql và update cho hành vi khác | Chế độ xem trước xử lý precondition hoặc đầu vào khác | Kiểm tra tài liệu phiên bản và thử lệnh trên database test |

Không chỉnh sửa trực tiếp DATABASECHANGELOG, xóa checksum hay thay status chỉ để biến một precondition lỗi thành kết quả thành công. Phải phân biệt lỗi cấu hình, thiếu dữ liệu, thiếu quyền và thay đổi schema ngoài lịch sử.

## 19. Checklist trước khi triển khai

- [ ] Tôi biết changeset này hỗ trợ DBMS và phiên bản database nào.
- [ ] dbms kiểm tra đúng loại hệ quản trị theo tài liệu Liquibase đang sử dụng.
- [ ] runningAs kiểm tra tài khoản dự kiến; quyền database được xác minh riêng.
- [ ] sqlCheck là truy vấn chỉ đọc, trả về một giá trị có thể so sánh ổn định.
- [ ] expectedResult được kiểm tra trên DBMS và driver thực tế.
- [ ] Tôi phân biệt onFail với onError và chọn HALT cho điều kiện bắt buộc.
- [ ] Tôi không dùng MARK_RAN để che giấu dữ liệu hoặc schema chưa đúng.
- [ ] Tôi biết phạm vi của precondition là cấp changelog hay cấp changeset.
- [ ] Tôi hiểu context/label filter có thể khiến changeset không được chọn.
- [ ] Tôi đã xác minh host, database, schema, JDBC URL và quyền trước update.
- [ ] Tôi đã kiểm tra SQL sinh ra và thử trên dữ liệu đại diện.
- [ ] Tôi có kế hoạch rollback, forward fix hoặc khôi phục nếu migration gây lỗi.
- [ ] Tôi đã kiểm tra trạng thái DATABASECHANGELOG và đối tượng schema sau triển khai.
- [ ] Tôi không để thông tin nhạy cảm trong SQL kiểm tra, thông báo hoặc log.

## 20. Kết luận

Ba precondition **dbms**, **runningAs** và **sqlCheck** trả lời ba câu hỏi khác nhau: *đang dùng loại database nào*, *đang kết nối bằng user nào* và *trạng thái dữ liệu/schema có đáp ứng giả định hay không*. Chúng giúp chuyển các giả định triển khai thành điều kiện có thể kiểm tra cùng changelog.

Để sử dụng hiệu quả, hãy viết điều kiện rõ ràng, chọn chính sách **onFail/onError** phù hợp, ưu tiên dừng khi trạng thái chưa chắc chắn, xác minh kết nối đúng môi trường và thử cả nhánh đạt lẫn nhánh thất bại. Trong module DATABASE_SCHEMA_MIGRATION_LIQUIBASE, những thói quen này bổ sung cho việc quản lý changeset, checksum, lịch sử DATABASECHANGELOG, rollback và tích hợp Spring Boot/CI/CD, giúp migration có thể kiểm chứng và truy vết trên nhiều môi trường.

