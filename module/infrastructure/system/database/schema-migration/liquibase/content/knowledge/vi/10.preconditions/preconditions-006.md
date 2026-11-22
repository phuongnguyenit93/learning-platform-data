# Phân biệt onFail với onError trong precondition của Liquibase

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, việc quản lý thay đổi schema và dữ liệu bằng changelog, changeset, checksum và lịch sử triển khai chỉ đáng tin cậy khi mỗi bước migration kiểm tra được những giả định trước khi thực thi. Bài thuộc chương **Tiền điều kiện** này tập trung vào hai thuộc tính quan trọng của Liquibase: **onFail** và **onError**. Chúng quyết định Liquibase xử lý như thế nào khi kiểm tra một **precondition** không đạt hoặc khi chính quá trình kiểm tra gặp lỗi.

Người học cần phân biệt được **điều kiện sai** với **không đánh giá được điều kiện**, chọn chính sách dừng hoặc tiếp tục một cách có chủ đích, đọc đúng trạng thái trong DATABASECHANGELOG và áp dụng việc kiểm tra này vào migration an toàn trên các môi trường phát triển, kiểm thử, staging, production, Spring Boot hoặc CI/CD.

## 1. Precondition là gì và được kiểm tra ở đâu?

**Precondition** là điều kiện cần kiểm tra trước khi Liquibase thực thi một changeset hoặc trước khi xử lý phần còn lại của changelog, tùy vị trí khai báo. Nó diễn đạt một giả định về môi trường và trạng thái cơ sở dữ liệu: bảng đã tồn tại, cột chưa có, database có đúng loại, người dùng kết nối phù hợp hoặc dữ liệu hiện tại đáp ứng một tiêu chí.

Ví dụ, một migration thêm cột **status** cho bảng **customer** giả định rằng bảng **customer** đã có và cột **status** chưa tồn tại. Nếu không kiểm tra trước, câu lệnh thêm cột có thể thất bại hoặc cho kết quả ngoài dự kiến trên một môi trường đã bị chỉnh sửa thủ công.

Một số precondition thường gặp:

| Precondition | Điều được kiểm tra | Ví dụ sử dụng |
|---|---|---|
| **tableExists** | Bảng được chỉ định tồn tại hay không | Kiểm tra bảng customer trước khi thêm cột |
| **columnExists** | Cột được chỉ định tồn tại hay không | Tránh thêm trùng cột status |
| **indexExists** | Chỉ mục tồn tại hay không | Kiểm tra trước khi tạo index |
| **foreignKeyConstraintExists** | Khóa ngoại tồn tại hay không | Thay đổi ràng buộc an toàn |
| **dbms** | DBMS thực tế có khớp loại yêu cầu không | Giới hạn SQL dành cho PostgreSQL |
| **sqlCheck** | Kết quả truy vấn SQL có bằng giá trị kỳ vọng không | Xác nhận không còn giá trị NULL trước khi thêm NOT NULL |
| **changeSetExecuted** | Một changeset có được ghi nhận đã chạy chưa | Xác nhận phụ thuộc lịch sử |
| **runningAs** | Tài khoản thực thi có khớp yêu cầu không | Ngăn chạy dưới tài khoản không phù hợp |

Có thể kết hợp các precondition bằng **and**, **or** và **not**. Khi khai báo nhiều điều kiện trong cùng một danh sách, Liquibase xử lý chúng như tổ hợp AND theo quy tắc của cú pháp đang dùng. Vì vậy, với ví dụ thêm cột, điều kiện hợp lệ là: bảng **customer** tồn tại **và** cột **status** **chưa** tồn tại.

Precondition không chứng minh migration sẽ thành công. Giữa thời điểm kiểm tra và thời điểm chạy SQL có thể có thay đổi đồng thời; dữ liệu cũng có thể vi phạm một ràng buộc chưa được kiểm tra. Precondition là lớp bảo vệ bổ sung bên cạnh review SQL, kiểm thử migration và kiểm tra kết quả.

## 2. Khác biệt cốt lõi: onFail và onError

Liquibase phân biệt hai kết quả bất thường của việc đánh giá precondition.

**onFail** áp dụng khi Liquibase **đánh giá được điều kiện**, nhưng kết quả điều kiện là **không đúng** so với yêu cầu. Đây là một kết quả kiểm tra hợp lệ về mặt kỹ thuật, chỉ không đáp ứng giả định của migration.

**onError** áp dụng khi Liquibase **gặp lỗi trong quá trình đánh giá điều kiện**, nên không thể xác định kết quả theo cách thông thường. Ví dụ: câu SQL của **sqlCheck** không hợp lệ, truy vấn kiểm tra gặp lỗi quyền truy cập, hoặc cơ chế kiểm tra metadata database phát sinh ngoại lệ.

Một ví dụ dễ nhớ:

- Precondition hỏi: **“Bảng customer có tồn tại không?”** và database trả lời rõ rằng không tồn tại → **fail**, xử lý bằng **onFail**.
- Precondition hỏi cùng câu, nhưng quá trình truy vấn metadata bị lỗi hoặc không có quyền → **error**, xử lý bằng **onError**.

Khác biệt này **không** phụ thuộc vào mức độ nghiêm trọng do người viết đánh giá. Một kết quả **fail** có thể rất nguy hiểm về nghiệp vụ, và một kết quả **error** có thể chỉ do SQL viết sai. Liquibase phân loại theo **cơ chế thực thi kiểm tra**, sau đó mới áp dụng hành động bạn cấu hình.

| Khía cạnh | onFail | onError |
|---|---|---|
| Khi nào kích hoạt? | Precondition được đánh giá và cho kết quả false | Việc đánh giá precondition ném lỗi/ngoại lệ |
| Ví dụ | tableExists trả false; sqlCheck trả số khác expectedResult | sqlCheck có cú pháp SQL sai; truy vấn metadata lỗi |
| Có biết trạng thái điều kiện? | Biết rằng điều kiện yêu cầu không được đáp ứng | Không thể kết luận điều kiện bằng cách đánh giá vừa thực hiện |
| Ý nghĩa vận hành | Database không ở trạng thái được migration kỳ vọng | Việc kiểm tra không đáng tin cậy hoặc không thể hoàn thành |
| Hành động khả dụng | HALT, WARN; thêm CONTINUE và MARK_RAN khi ở cấp changeset | Tập hành động tương tự, tùy vị trí khai báo |
| Chính sách an toàn mặc định thường chọn | HALT khi giả định bắt buộc | HALT, nhất là khi không xác minh được trạng thái database |

**Lưu ý quan trọng:** **onError không phải bộ xử lý mọi lỗi SQL của changeset**. Nó xử lý lỗi phát sinh khi **đánh giá precondition**. Nếu precondition đã đạt nhưng câu lệnh **ALTER TABLE** hoặc **UPDATE** trong phần **changes** thất bại, lỗi đó thuộc giai đoạn thực thi thay đổi và chịu cơ chế xử lý lỗi/transaction của Liquibase và database; không thể đặt **onError: WARN** để bảo đảm bỏ qua một lỗi DDL.

## 3. Bốn chính sách xử lý: HALT, WARN, CONTINUE, MARK_RAN

Cả onFail và onError có thể nhận giá trị chính sách, nhưng phạm vi cho phép phụ thuộc cấp khai báo.

### HALT: dừng cập nhật

**HALT** khiến Liquibase dừng quy trình update khi điều kiện không đạt hoặc có lỗi theo nhánh tương ứng. Đây là lựa chọn phù hợp nhất với những precondition bảo vệ cấu trúc dữ liệu và tính toàn vẹn.

Ví dụ: nếu cần thêm khóa ngoại nhưng bảng được tham chiếu không tồn tại, nên dừng và tìm nguyên nhân. Nếu truy vấn kiểm tra số bản ghi NULL bị lỗi, cũng nên dừng vì chưa thể chứng minh dữ liệu thỏa điều kiện.

HALT không tự rollback toàn bộ những changeset đã thực thi thành công trước đó trong cùng một lần update. Khả năng transaction và rollback thực tế phụ thuộc vào DBMS, kiểu thay đổi và ranh giới transaction. Vì thế cần xác minh lịch sử triển khai trước khi chạy lại.

### WARN: cảnh báo rồi tiếp tục

**WARN** cho phép quy trình tiếp tục sau khi ghi cảnh báo về precondition. Khi nằm ở cấp changeset, phần thay đổi có thể vẫn được thực thi dù điều kiện không đạt hoặc phép kiểm tra có lỗi.

Chỉ dùng WARN khi kiểm tra mang tính **cảnh báo/thông tin** và việc tiếp tục thực thi đã được đánh giá an toàn. Ví dụ, một bước báo cáo không ảnh hưởng schema có thể chấp nhận cảnh báo về metadata phụ. Ngược lại, nếu điều kiện nhằm ngăn **DROP TABLE** hoặc bảo vệ dữ liệu trước **UPDATE**, dùng WARN sẽ vô hiệu hóa mục đích bảo vệ.

WARN không sửa được điều kiện sai và không xác nhận database ở trạng thái an toàn.

### CONTINUE: bỏ qua changeset trong lần update hiện tại

**CONTINUE** có thể dùng cho precondition ở **cấp changeset**. Nếu kích hoạt, Liquibase bỏ qua changeset đó trong lần update hiện tại, không đánh dấu là đã chạy. Khi update được gọi lại, changeset vẫn có thể được xem xét nếu còn phù hợp với bộ lọc thực thi.

Ví dụ, một bước bổ sung dữ liệu cho bảng tùy chọn có thể được bỏ qua khi bảng chưa được tạo trong môi trường thử nghiệm, rồi được thực hiện ở lần chạy sau khi bảng xuất hiện. Tuy nhiên, với migration bắt buộc để ứng dụng hoạt động, bỏ qua có thể làm schema thiếu thay đổi mà pipeline vẫn đi tiếp. Cần xác định rõ phụ thuộc giữa các changeset và điểm kiểm tra đầu ra.

### MARK_RAN: ghi nhận đã chạy mà không thực thi thay đổi

**MARK_RAN** cũng chỉ dùng cho precondition ở **cấp changeset**. Liquibase bỏ qua phần changes của changeset hiện tại nhưng ghi nhận changeset trong **DATABASECHANGELOG**, thường với kiểu thực thi **MARK_RAN**.

Hành vi này có thể hữu ích trong một trường hợp baseline đã được xác minh độc lập: đối tượng mong muốn đã tồn tại với **đúng cấu trúc**, nên không cần tạo lại. Nhưng **tableExists** hoặc **columnExists** đơn lẻ không chứng minh đối tượng hiện tại đúng kiểu, constraint, index hoặc dữ liệu kỳ vọng.

Đặc biệt nguy hiểm nếu cấu hình **onError: MARK_RAN**: khi kiểm tra không chạy được do lỗi quyền hoặc SQL, hệ thống vẫn có thể ghi lịch sử như đã xử lý mặc dù trạng thái database chưa được chứng minh. Trong quy trình migration có kiểm chứng, nên ưu tiên **onError: HALT**.

### Phạm vi giá trị

| Vị trí precondition | HALT | WARN | CONTINUE | MARK_RAN |
|---|---|---|---|---|
| **Cấp changelog** | Có | Có | Không | Không |
| **Cấp changeset** | Có | Có | Có | Có |

Cấp **changelog** không gắn với một changeset riêng để “đánh dấu chạy” hoặc “bỏ qua rồi xét lại” theo cách cấp changeset làm được. Vì vậy, tại cấp changelog chỉ sử dụng **HALT** hoặc **WARN**. Đặt CONTINUE hay MARK_RAN tại cấp này là sai phạm vi và cần sửa cấu hình.

## 4. Ví dụ YAML: phân biệt bằng một migration thêm cột

Giả sử bảng customer đã tồn tại và cần thêm cột status. Changelog YAML minh họa:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: add-customer-status
      author: database-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - onFailMessage: "Bang customer phai co va cot status chua ton tai"
        - onErrorMessage: "Khong the kiem tra metadata bang/cot"
        - tableExists:
            tableName: customer
        - not:
            - columnExists:
                tableName: customer
                columnName: status
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: status
                  type: varchar(30)
      rollback:
        - dropColumn:
            tableName: customer
            columnName: status
~~~

Các nhánh hành vi:

1. **Có bảng customer, chưa có cột status, đọc metadata thành công:** precondition đạt; Liquibase chạy addColumn rồi ghi nhận lịch sử.
2. **Không có bảng customer:** **tableExists** trả false; đây là **onFail**, nên HALT và không thực thi addColumn.
3. **Đã có cột status:** biểu thức **not(columnExists)** không đạt; đây cũng là **onFail**. Cấu hình HALT buộc nhóm xác minh vì sao cột đã có.
4. **Lỗi truy vấn metadata hoặc quyền kiểm tra:** nếu Liquibase không thể đánh giá precondition và phát sinh lỗi, đây là **onError**; HALT và báo lỗi kiểm tra.
5. **Precondition đạt nhưng addColumn thất bại:** lỗi xảy ra trong **changes** và không được phân loại thành onError của precondition.

Hai trường **onFailMessage** và **onErrorMessage** cho phép đưa thông điệp có ngữ cảnh vào log. Nên mô tả kỳ vọng và phạm vi, nhưng không chèn thông tin bí mật, password hoặc chuỗi kết nối nhạy cảm.

Đối với production, rollback **dropColumn** có thể làm mất dữ liệu được ghi sau khi triển khai. Cần cân nhắc kế hoạch rollback hoặc forward-fix trước khi sử dụng.

## 5. Ví dụ SQLCheck: phân biệt số liệu không đạt và truy vấn bị lỗi

Một trường hợp thực tế là cần chuyển cột **customer.status** sang **NOT NULL** sau khi backfill dữ liệu cũ. Không thể chỉ kiểm tra cột tồn tại; phải kiểm tra dữ liệu đang đáp ứng ràng buộc.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: require-customer-status
      author: database-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - onFailMessage: "Con customer.status NULL, can backfill truoc"
        - onErrorMessage: "Khong the truy van du lieu customer"
        - tableExists:
            tableName: customer
        - columnExists:
            tableName: customer
            columnName: status
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM customer
              WHERE status IS NULL
      changes:
        - addNotNullConstraint:
            tableName: customer
            columnName: status
            columnDataType: varchar(30)
~~~

Hãy tách các tình huống:

- Truy vấn chạy thành công và trả về **0**: điều kiện đạt; Liquibase có thể thực hiện bước thêm ràng buộc.
- Truy vấn chạy thành công và trả về **37**: giá trị khác expectedResult **0**; precondition **fail**, kích hoạt **onFail: HALT**. Đây không phải lỗi SQL.
- Câu SQL viết sai tên bảng/cột, dùng cú pháp không hỗ trợ hoặc gặp lỗi quyền: truy vấn **không thực thi thành công**; thường phát sinh precondition **error**, kích hoạt **onError: HALT**.
- Nếu bảng hoặc cột không tồn tại, **tableExists** hoặc **columnExists** có thể trả false trước khi đến sqlCheck; đó là **onFail**. Nếu lỗi xảy ra khi kiểm tra metadata, đó là **onError**.

**sqlCheck** cần một kết quả vô hướng rõ ràng có thể so sánh với **expectedResult**. Giá trị NULL, kết quả không đúng định dạng hoặc truy vấn không trả về kết quả hợp lệ có thể cho hành vi khác nhau tùy driver và phiên bản. Nên dùng truy vấn đơn giản, xác định, chỉ đọc, chẳng hạn COUNT(*), và xác minh trường hợp mong muốn trên đúng DBMS.

Nếu precondition đạt mà một phiên giao dịch khác thêm bản ghi NULL trước khi constraint được tạo, DDL vẫn có thể thất bại. Do đó không xem precondition là bảo đảm chống race condition; cần thiết kế triển khai, khóa và xử lý dữ liệu phù hợp.

## 6. Cấu hình onFail và onError khác nhau có ý nghĩa gì?

Hai thuộc tính được đặt độc lập. Một thay đổi có thể chủ động bỏ qua khi database không có thành phần tùy chọn, nhưng phải dừng khi không kiểm tra được database. Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: update-optional-customer-label
      author: database-team
      preConditions:
        - onFail: CONTINUE
        - onError: HALT
        - tableExists:
            tableName: customer_label
      changes:
        - sql:
            sql: |
              UPDATE customer_label
              SET label = 'ACTIVE'
              WHERE label IS NULL;
~~~

Khi bảng tùy chọn **customer_label** không tồn tại, điều kiện **tableExists** trả false; Liquibase bỏ qua changeset trong lần chạy hiện tại. Nếu sau đó bảng được tạo, lần update tiếp theo có thể thực hiện bước này. Nếu việc kiểm tra bảng bị lỗi, **onError: HALT** dừng, tránh tiếp tục trong trạng thái không chắc chắn.

Cấu hình này chỉ hợp lý khi dữ liệu **customer_label** thật sự là tùy chọn và việc bỏ qua không gây lỗi cho ứng dụng hoặc các changeset phụ thuộc. Nó cũng đòi hỏi câu UPDATE an toàn khi chạy vào thời điểm muộn hơn. Với bước migration bắt buộc, nên chọn **onFail: HALT**.

Ngược lại, cấu hình **onFail: HALT** nhưng **onError: WARN** thường đáng ngờ khi precondition bảo vệ dữ liệu. Hệ thống sẽ dừng nếu điều kiện được đánh giá là sai, nhưng lại có thể tiếp tục khi **không đánh giá được** điều kiện. Hãy giải thích rõ quyết định đó trong review nếu thật sự cần dùng.

## 7. MARK_RAN và nguy cơ sai lệch lịch sử

Xem một changeset tạo chỉ mục:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: add-customer-email-index
      author: database-team
      preConditions:
        - onFail: MARK_RAN
        - onError: HALT
        - not:
            - indexExists:
                tableName: customer
                indexName: idx_customer_email
      changes:
        - createIndex:
            tableName: customer
            indexName: idx_customer_email
            columns:
              - column:
                  name: email
~~~

Nếu index chưa có, changeset chạy. Nếu index có rồi, biểu thức **not(indexExists)** trả false; **onFail: MARK_RAN** khiến Liquibase ghi nhận changeset như đã xử lý mà không tạo index.

Nghe có vẻ tiện để “chạy lại không lỗi”, nhưng có rủi ro: index cùng tên có thể được tạo trên cột khác, có thuộc tính unique khác hoặc chưa đạt yêu cầu hiệu năng. Chỉ dùng chiến lược MARK_RAN khi đã xác minh index hiện có **tương đương với kết quả mong muốn**, hoặc trong quy trình baseline đã được kiểm tra đầy đủ.

Nếu muốn tránh che giấu một thay đổi bất thường, chọn **onFail: HALT**, rồi phân tích và quyết định bước sửa. **MARK_RAN** thường chỉ nên được dùng cho trạng thái đã hiểu, không phải đường tắt để bỏ qua mọi migration bị vướng đối tượng có sẵn.

Khi một changeset được MARK_RAN, lịch sử có thể cho thấy changeset đã được xử lý, nhưng không có nghĩa lệnh **changes** đã chạy. Điều này rất quan trọng khi đọc DATABASECHANGELOG hoặc phân tích sự khác biệt giữa staging và production.

## 8. Precondition cấp changelog so với cấp changeset

Precondition ở đầu changelog có thể dùng để bảo vệ toàn bộ tập thay đổi. Ví dụ, một changelog chỉ dùng PostgreSQL:

~~~yaml
databaseChangeLog:
  - preConditions:
      - onFail: HALT
      - onError: HALT
      - dbms:
          type: postgresql
  - changeSet:
      id: create-postgresql-only-object
      author: database-team
      changes:
        - sql:
            sql: |
              CREATE TABLE IF NOT EXISTS app_marker (
                marker_id BIGINT PRIMARY KEY
              );
~~~

Nếu môi trường là DBMS khác, **dbms** được đánh giá là không thỏa mãn → **onFail: HALT**. Nếu xảy ra lỗi trong quá trình kiểm tra, xử lý theo **onError: HALT**. Tại cấp changelog, không dùng CONTINUE hoặc MARK_RAN.

Khi chỉ một changeset dùng SQL riêng cho PostgreSQL, việc đặt điều kiện ở cấp changeset có thể phù hợp hơn vì các changeset khác vẫn có thể chạy cho DBMS khác. Ngoài precondition, Liquibase còn có thuộc tính **dbms** cho changeset để giới hạn loại DBMS; cần chọn cơ chế phù hợp với chủ đích.

Tương tự, **contexts** và **labels** có thể quyết định changeset có được xem xét trong lần chạy hiện tại hay không. Việc một changeset bị bộ lọc loại ra không đồng nghĩa precondition của nó đã fail hoặc error. Khi chẩn đoán changeset không chạy, phải kiểm tra bộ lọc, lịch sử DATABASECHANGELOG, rồi mới đến precondition.

## 9. Bảng quyết định cho một lần update

Bảng sau giả định changeset **chưa được ghi nhận đã chạy**, được chọn bởi bộ lọc và Liquibase đã bắt đầu đánh giá precondition:

| Kết quả đánh giá | Chính sách | Hành vi chính | Lịch sử changeset |
|---|---|---|---|
| Điều kiện **true** | Bất kỳ | Tiếp tục thực thi changes | Ghi EXECUTED nếu changes chạy thành công |
| Điều kiện **false** | onFail: HALT | Dừng update và báo fail | Không ghi changeset này là đã chạy |
| Điều kiện **false** | onFail: WARN | Cảnh báo, vẫn có thể thực thi changes | Ghi nếu thực thi thành công |
| Điều kiện **false** | onFail: CONTINUE | Bỏ qua changeset lần này | Không ghi nhận, có thể xét lại |
| Điều kiện **false** | onFail: MARK_RAN | Bỏ qua changes, đánh dấu xử lý | Ghi MARK_RAN |
| Lỗi khi kiểm tra | onError: HALT | Dừng update và báo lỗi kiểm tra | Không ghi changeset này là đã chạy |
| Lỗi khi kiểm tra | onError: WARN | Cảnh báo và tiếp tục | Ghi nếu thực thi thành công |
| Lỗi khi kiểm tra | onError: CONTINUE | Bỏ qua changeset lần này | Không ghi nhận, có thể xét lại |
| Lỗi khi kiểm tra | onError: MARK_RAN | Bỏ qua changes, đánh dấu xử lý | Ghi MARK_RAN; **rủi ro cao** |

**Điều kiện true** nghĩa là kết quả đánh giá precondition đạt yêu cầu, bất kể cấu hình onFail/onError. Hai nhánh xử lý chỉ có tác dụng khi false hoặc error xảy ra.

**Changeset đã được thực thi trước đó** thường được Liquibase bỏ qua mà không đánh giá lại precondition, trừ những trường hợp có cơ chế chạy lại như runAlways hoặc runOnChange. Vì thế, precondition không phải công cụ giám sát schema liên tục. Khi cần kiểm tra tính nhất quán của database sau triển khai, hãy bổ sung truy vấn xác minh, test hoặc công cụ so sánh schema.

## 10. Phân biệt lỗi precondition với lỗi migration

Trong thực tế, người vận hành thường chỉ thấy “Liquibase update failed”. Cần tìm **giai đoạn lỗi** trước khi quyết định xử lý.

**Lỗi giai đoạn nạp changelog:** YAML sai cấu trúc, file include không tồn tại hoặc change type không được nhận diện. Đây có thể là lỗi parse/validate, trước cả khi đánh giá precondition; onError không nhất thiết được gọi.

**Lỗi precondition fail:** điều kiện đánh giá thành công nhưng trả false. Log thường cho biết precondition không đáp ứng; hành vi phụ thuộc onFail. Cần điều tra trạng thái database, dữ liệu hay DBMS và so sánh với giả định.

**Lỗi precondition error:** không thể hoàn thành việc đánh giá; hành vi phụ thuộc onError. Cần điều tra quyền truy cập metadata, cấu trúc SQLCheck, kết nối, dữ liệu đầu vào và DBMS.

**Lỗi thực thi changes:** precondition đã đạt hoặc được cho phép tiếp tục, nhưng DDL/DML bị database từ chối: khóa trùng, dữ liệu vi phạm constraint, deadlock, timeout hoặc thiếu quyền DDL. Các lỗi này không tự chuyển sang onError; xử lý theo cơ chế lỗi khi thực thi changeset.

**Lỗi checksum:** một changeset đã chạy bị sửa nội dung gây lệch checksum. Đó là cơ chế bảo vệ lịch sử, không phải kết quả fail/error của một precondition. Không chữa bằng cách đặt onFail hay onError.

Để tránh làm hỏng lịch sử triển khai, không sửa trực tiếp **DATABASECHANGELOG**, không xóa checksum hoặc dùng **MARK_RAN** chỉ để làm pipeline “xanh”. Nếu có khác biệt giữa schema thực tế và changelog, cần xác minh độc lập trước khi áp dụng thay đổi khôi phục hoặc migration mới.

## 11. Kiểm chứng với Liquibase CLI, Spring Boot và CI/CD

Trên database thử nghiệm, có thể tạo changelog gồm một changeset với **sqlCheck COUNT(*)** như ví dụ ở phần 5. Thực hiện thí nghiệm theo thứ tự:

1. **Kết quả đạt:** chuẩn bị dữ liệu không có status NULL; gọi update và xác nhận precondition đạt, changes được thực thi.
2. **Kết quả fail:** trên bản sao database chưa được áp dụng changeset, tạo một bản ghi có status NULL. Chạy update và xác nhận dừng ở nhánh onFail.
3. **Kết quả error:** trên database thử nghiệm riêng, cố ý dùng tên cột không tồn tại trong sqlCheck để tạo lỗi truy vấn; chạy update và quan sát nhánh onError.
4. **Thay chính sách:** thử onFail: CONTINUE để thấy changeset không được ghi nhận; thử onFail: MARK_RAN chỉ trên bản sao kiểm soát để thấy khác biệt lịch sử.
5. **Khôi phục cấu hình an toàn:** trước khi sử dụng trên môi trường dùng chung, đặt lại HALT cho mọi điều kiện bắt buộc, kiểm tra dữ liệu và kiểm tra câu SQL sẽ thực thi.

Các lệnh Liquibase CLI thường dùng, sau khi cấu hình URL, driver, credentials và changelog:

~~~shell
liquibase validate
liquibase update-sql
liquibase update
liquibase status --verbose
~~~

**validate** hữu ích để bắt lỗi cú pháp/cấu hình changelog nhưng không bảo đảm mọi câu truy vấn kiểm tra chạy được trên database thật. **update-sql** giúp xem SQL dự kiến mà không thay đổi schema; hành vi đánh giá precondition trong chế độ xuất SQL có thể chịu quy tắc riêng theo phiên bản và cấu hình, vì thế cần chạy thử update trên database tương thích để kiểm chứng nhánh fail/error. **status --verbose** hỗ trợ xem changeset còn pending; nó không thay thế kiểm tra dữ liệu nghiệp vụ.

Có thể truy vấn lịch sử trong PostgreSQL như sau:

~~~sql
SELECT id, author, filename, exectype, dateexecuted
FROM databasechangelog
ORDER BY orderexecuted;
~~~

Một changeset **MARK_RAN** có thể xuất hiện trong lịch sử mà chưa từng thực thi câu DDL/DML. Một changeset bị **CONTINUE** sẽ còn pending. Khi update bị HALT, các changeset trước đó có thể đã ghi nhận thành công, nên không được mặc định rằng toàn bộ lần triển khai bị đảo ngược.

Khi tích hợp **Spring Boot**, Liquibase có thể chạy lúc ứng dụng khởi động; nếu precondition bắt buộc HALT, quá trình khởi tạo có thể thất bại. Đây thường là kết quả mong muốn để tránh ứng dụng chạy trên schema không tương thích. Khi tích hợp **CI/CD**, bước migration cần báo lỗi rõ ràng, dừng phát hành nếu schema chưa đạt yêu cầu và lưu log cho việc chẩn đoán. Trong hệ thống nhiều instance, ưu tiên xác định rõ job migration hay ứng dụng chịu trách nhiệm thực thi; cơ chế DATABASECHANGELOGLOCK điều phối các tiến trình Liquibase nhưng không thay thế việc review cấu hình.

## 12. Chọn chính sách theo tình huống

| Tình huống | onFail đề xuất | onError đề xuất | Vì sao |
|---|---|---|---|
| Kiểm tra bảng/cột bắt buộc trước thay đổi schema | HALT | HALT | Không có hoặc không kiểm tra được đối tượng thì phải điều tra |
| Kiểm tra không có NULL trước khi thêm NOT NULL | HALT | HALT | Bảo vệ toàn vẹn dữ liệu; không được bỏ qua lỗi truy vấn |
| Bước dữ liệu tùy chọn, an toàn nếu dời sang lần sau | CONTINUE (cấp changeset) | HALT | Chỉ bỏ qua khi biết rõ điều kiện false |
| Đối tượng đã tồn tại với cấu trúc **được xác minh tương đương** | MARK_RAN (cấp changeset, có kiểm soát) | HALT | Có thể baseline nhưng không che giấu lỗi kiểm tra |
| Kiểm tra chỉ để cảnh báo, thay đổi không phụ thuộc kết quả | WARN | HALT hoặc WARN nếu có lý do rõ ràng | Cần chứng minh việc tiếp tục là an toàn |
| Điều kiện bảo vệ chung cho toàn changelog | HALT | HALT | Không dùng CONTINUE/MARK_RAN ở cấp changelog |

Có thể dùng onFail và onError khác nhau, nhưng mọi lựa chọn khác HALT cần trả lời: *nếu database không như giả định hoặc không xác minh được, ứng dụng và dữ liệu có còn đúng không?* Với thay đổi schema hoặc dữ liệu mang tính quyết định, nếu không chứng minh được điều đó thì dừng là lựa chọn phù hợp.

## 13. Những nguyên tắc cần ghi nhớ

- **onFail** xử lý trường hợp precondition **được đánh giá là sai**; **onError** xử lý khi **không đánh giá được vì gặp lỗi**.
- **HALT** phù hợp cho giả định bắt buộc. **WARN** tiếp tục sau cảnh báo, nên chỉ dùng khi đã xác minh an toàn.
- **CONTINUE** bỏ qua changeset trong lần hiện tại mà không đánh dấu đã chạy; **MARK_RAN** bỏ qua thay đổi nhưng ghi lịch sử. Hai chính sách này chỉ dùng ở cấp changeset.
- Lỗi trong **changes** không được xử lý bằng onError của precondition; lỗi parse/validate và lỗi checksum cũng là các cơ chế riêng.
- Không dựa vào điều kiện tồn tại của bảng/cột để khẳng định toàn bộ schema tương đương; khi dùng MARK_RAN cần chứng minh rõ trạng thái.
- Precondition chỉ bảo vệ thời điểm chạy và không phải cơ chế kiểm toán schema liên tục. Phải kết hợp review changelog, checksum, DATABASECHANGELOG, rollback/forward-fix, kiểm thử dữ liệu và log triển khai.

Trong **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, phân biệt đúng **onFail** và **onError** giúp nhóm quyết định chính xác khi nào phải dừng, khi nào có thể bỏ qua có kiểm soát và khi nào việc đánh dấu lịch sử là hợp lệ. Đây là nền tảng để triển khai migration có kiểm chứng, phối hợp nhiều môi trường và vận hành Liquibase đáng tin cậy cùng Spring Boot hoặc CI/CD.
