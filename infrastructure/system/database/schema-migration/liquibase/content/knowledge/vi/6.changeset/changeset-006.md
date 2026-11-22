# Cập nhật đối tượng có thể thay thế bằng runOnChange

## 1. Bối cảnh và mục tiêu

Trong quản lý schema cơ sở dữ liệu, phần lớn thay đổi nên được ghi thành **changeset mới**: thêm cột, tạo bảng, bổ sung khóa ngoại, chuyển đổi dữ liệu hoặc thay đổi ràng buộc. Tuy nhiên, một số đối tượng có bản chất **định nghĩa có thể thay thế**, chẳng hạn **view**, **stored procedure** hoặc **function**. Nhóm có thể muốn giữ một changeset đại diện cho định nghĩa hiện tại của đối tượng, rồi cho Liquibase thực thi lại khi định nghĩa ấy đổi.

Thuộc tính **runOnChange** của Liquibase phục vụ tình huống này. Nó cho phép một changeset đã được áp dụng chạy lại **khi nội dung có ảnh hưởng đến checksum của changeset thay đổi**. Cách dùng đúng giúp cập nhật đối tượng có thể thay thế mà không phải tạo changeset mới cho từng chỉnh sửa nhỏ của định nghĩa. Cách dùng sai có thể khiến dữ liệu bị chèn trùng, thao tác phá hủy bị lặp hoặc một phiên bản ứng dụng cũ khôi phục định nghĩa không mong muốn.

Bài thuộc chương **Changeset** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Phạm vi module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Riêng bài này giải thích cơ chế runOnChange, điều kiện sử dụng và quy trình kiểm chứng khi thay đổi đối tượng có thể thay thế.

Sau bài học, bạn cần:

- Phân biệt changeset mặc định, runOnChange và runAlways.
- Hiểu mối quan hệ giữa id/author/đường dẫn changelog, checksum và bảng DATABASECHANGELOG.
- Viết changeset runOnChange cho view hoặc function bằng ví dụ Liquibase YAML.
- Kiểm tra khi nào changeset sẽ chạy lại và xem SQL dự kiến trước khi cập nhật.
- Thiết kế rollback, xử lý phụ thuộc và phối hợp giữa dev, test, production.
- Nhận diện những thao tác không phù hợp với runOnChange.

## 2. Vấn đề: định nghĩa đối tượng thay đổi nhiều lần

Giả sử một ứng dụng bán hàng dùng view **order_status_summary** để tổng hợp số đơn hàng và doanh thu theo trạng thái. Ở lần phát hành đầu, view hiển thị tất cả trạng thái. Sau khi nghiệp vụ thay đổi, báo cáo không còn tính các đơn đã hủy.

Có hai hướng quản lý thay đổi:

1. Tạo changeset mới ở mỗi phiên bản để thay định nghĩa view.
2. Dùng một changeset với **runOnChange: true**, chứa định nghĩa view hoàn chỉnh; khi định nghĩa thay đổi, Liquibase thực thi lại changeset đó.

Hướng thứ nhất cho phép lưu chuỗi migration chi tiết qua từng changeset. Hướng thứ hai thuận tiện khi đối tượng hỗ trợ thao tác **CREATE OR REPLACE** hoặc cơ chế thay thế tương đương, và mỗi lần chạy đều đưa đối tượng về một định nghĩa hoàn chỉnh, có thể kiểm chứng.

RunOnChange **không có nghĩa là Liquibase theo dõi trực tiếp nội dung đối tượng trong database**. Liquibase theo dõi checksum của changeset trong changelog. Nếu một người sửa view thủ công trong database nhưng tệp changeset vẫn không đổi, runOnChange thông thường không tự phát hiện sự lệch trạng thái ấy.

## 3. Ôn lại changeset và checksum

Một changeset được Liquibase nhận diện bằng tổ hợp:

- **id**: định danh do người viết đặt.
- **author**: người hoặc nhóm khai báo changeset.
- **Đường dẫn changelog** chứa changeset, hoặc logicalFilePath khi được cấu hình phù hợp.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: refresh-order-summary-view
      author: platform-team
      runOnChange: true
      changes:
        - sql:
            sql: SELECT 1
~~~

Ví dụ trên chỉ minh họa vị trí thuộc tính **runOnChange** trong YAML; câu lệnh SELECT 1 không phải một migration hữu ích để cập nhật view.

Khi chạy update lần đầu, Liquibase xét changeset theo thứ tự changelog và áp dụng changeset chưa được xử lý. Công cụ ghi thông tin vào bảng **DATABASECHANGELOG**, thường có các cột như ID, AUTHOR, FILENAME, DATEEXECUTED, EXECTYPE và MD5SUM.

**Checksum** là dấu kiểm tra được tính từ nội dung có liên quan của changeset. Ở lần chạy sau, Liquibase so sánh checksum hiện tại với giá trị đã lưu để quyết định liệu changeset có nhất quán với lần triển khai trước hay không.

Với changeset thông thường, sửa nội dung sau khi đã chạy có thể gây lỗi **checksum validation**. Đây là cơ chế cảnh báo thay đổi lịch sử. Với changeset có **runOnChange: true**, sự thay đổi nội dung làm checksum khác đi được xem là tín hiệu có chủ đích để **chạy lại changeset**, thay vì mặc nhiên coi đó là lỗi cần dừng.

## 4. runOnChange hoạt động như thế nào?

Thuộc tính đặt ngay trên changeset:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: some-replaceable-object
      author: platform-team
      runOnChange: true
      changes:
        # Định nghĩa đầy đủ của đối tượng có thể thay thế
        - sql:
            sql: SELECT 1
~~~

Ở mức khái quát, vòng đời của changeset được diễn giải như sau:

| Tình huống | Kết quả kỳ vọng |
|---|---|
| Changeset chưa có trong DATABASECHANGELOG | Chạy lần đầu, ghi lịch sử và checksum. |
| Changeset đã chạy; nội dung tính checksum không đổi | Bỏ qua trong lần update tiếp theo. |
| Changeset đã chạy; nội dung làm checksum thay đổi | Chạy lại nhờ runOnChange, ghi nhận kết quả và checksum mới. |
| Changeset đã chạy; chỉ có khác biệt không ảnh hưởng checksum | Không nhất thiết chạy lại. |
| Changeset không được chọn do context/label filter | Không chạy trong lượt đó dù định nghĩa đã thay đổi. |
| Changeset lỗi khi chạy lại | Update báo lỗi; trạng thái database và khả năng rollback phụ thuộc thao tác cùng hệ quản trị. |

Liquibase thường bỏ qua những thay đổi **chỉ liên quan đến khoảng trắng hoặc comment** khi xem xét chạy lại bằng runOnChange. Vì thế, đừng dùng cách sửa comment hay thêm dòng trống để ép đối tượng được triển khai lại. Ngược lại, đừng cho rằng hai tệp SQL có vẻ tương đương về nghiệp vụ thì checksum chắc chắn giống nhau: hãy kiểm tra bằng Liquibase thực tế.

Nếu chạy lại thành công, lịch sử trong DATABASECHANGELOG thường ghi **EXECTYPE = RERAN** và cập nhật checksum. Bảng lịch sử cơ bản không phải kho lưu mọi phiên bản cũ của định nghĩa view/function. Để truy vết từng lần thay đổi, cần kết hợp Git, bản phát hành và log CI/CD.

## 5. So sánh runOnChange, runAlways và changeset mặc định

| Thuộc tính | Thời điểm chạy | Tình huống nên dùng |
|---|---|---|
| Mặc định (không dùng hai thuộc tính) | Một lần khi chưa được ghi nhận; các lần sau bỏ qua nếu hợp lệ | Thêm cột, tạo bảng, sửa ràng buộc, chuyển dữ liệu theo từng phiên bản |
| **runOnChange: true** | Lần đầu và khi checksum thay đổi | View, function, procedure hoặc định nghĩa có thể thay thế |
| **runAlways: true** | Mỗi lần Liquibase xét đến changeset phù hợp | Công việc thực sự cần thực thi ở mọi lượt update, được thiết kế để chạy lặp an toàn |

RunAlways không cần checksum đổi để chạy lại. Nếu changeset runAlways bị sửa nội dung sau khi đã triển khai, hành vi kiểm tra checksum vẫn phải được cân nhắc; một số trường hợp chủ đích kết hợp runAlways và runOnChange. Đó là lựa chọn riêng cần kiểm thử rõ, không nên bật cả hai chỉ để tránh lỗi validation.

Ví dụ, **INSERT** thêm dữ liệu nghiệp vụ thường không phù hợp với runOnChange: nếu chạy lại khi câu lệnh thay đổi, có thể chèn trùng hoặc gây xung đột unique key. Thao tác **DROP TABLE** hay **ALTER TABLE** không có tính thay thế cũng không tự trở nên an toàn chỉ vì gắn runOnChange.

## 6. Tiêu chí chọn đối tượng phù hợp

Một đối tượng phù hợp với runOnChange thường đáp ứng phần lớn những tiêu chí:

1. Có **định nghĩa hoàn chỉnh** trong mã nguồn, không phụ thuộc các bước sửa tay vô hình.
2. Có thể **tạo hoặc thay thế nhiều lần** mà không làm mất dữ liệu nghiệp vụ.
3. Thay đổi định nghĩa có thể review, tạo SQL dự kiến và kiểm thử trên database đại diện.
4. Có thể xác định rõ các đối tượng phụ thuộc như bảng, cột, view hoặc function khác.
5. Có phương án xử lý rollback/khôi phục định nghĩa cũ.
6. Được triển khai có kiểm soát để tránh một release cũ ghi đè định nghĩa từ release mới.

Các ứng viên thường gặp:

- View mà hệ quản trị hỗ trợ **CREATE OR REPLACE VIEW** hoặc thay thế tương đương.
- Stored procedure được triển khai từ định nghĩa đầy đủ.
- Function có thể được thay thế với cùng chữ ký tương thích.
- Đôi khi là trigger hoặc đối tượng lập trình database khác, tùy cách tạo/thay thế của hệ quản trị.

Không phải mọi thay đổi của view hay function đều hỗ trợ CREATE OR REPLACE ở mọi hệ quản trị. Ví dụ PostgreSQL giới hạn những thay đổi kiểu cột, tên cột hoặc thứ tự cột hiện có của view khi thay thế; đổi chữ ký function cũng có thể tạo một function khác thay vì thay thế bản cũ. Với thay đổi phá vỡ tương thích, nên xem xét **changeset mới** để xử lý phụ thuộc và chuyển đổi có kiểm soát.

## 7. Ví dụ hoàn chỉnh: thay định nghĩa view trong PostgreSQL

### 7.1. Giả định của ví dụ

Giả sử PostgreSQL có bảng **orders** với các cột:

| Cột | Kiểu minh họa | Ý nghĩa |
|---|---|---|
| id | BIGINT | Khóa chính đơn hàng |
| status | VARCHAR | Trạng thái đơn hàng |
| total_amount | NUMERIC | Giá trị đơn hàng |

Bảng orders phải được tạo bởi migration trước đó và đủ quyền đọc để view hoạt động. Ví dụ tập trung vào việc quản lý **định nghĩa view**, không bao gồm tạo bảng hay dữ liệu mẫu.

Yêu cầu ban đầu: tạo view **order_status_summary** trả về số đơn và tổng tiền theo trạng thái.

### 7.2. Changeset tạo view có runOnChange

~~~yaml
databaseChangeLog:
  - changeSet:
      id: view-order-status-summary
      author: platform-team
      runOnChange: true
      comment: Duy trì định nghĩa view tổng hợp đơn hàng
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: orders
      changes:
        - createView:
            viewName: order_status_summary
            replaceIfExists: true
            selectQuery: |
              SELECT
                  status,
                  COUNT(*) AS order_count,
                  COALESCE(SUM(total_amount), 0) AS total_amount
              FROM orders
              GROUP BY status
      rollback:
        - dropView:
            viewName: order_status_summary
~~~

Các thành phần quan trọng:

- **id** và **author** định danh changeset; chúng cần giữ nguyên khi cập nhật cùng một đối tượng.
- **runOnChange: true** cho phép chạy lại khi checksum thay đổi.
- **createView** biểu diễn thao tác tạo view theo change type của Liquibase.
- **replaceIfExists: true** yêu cầu thay thế view đang tồn tại nếu hệ quản trị hỗ trợ cách tạo/thay thế đó.
- **selectQuery** lưu toàn bộ truy vấn định nghĩa view.
- **preConditions** xác nhận bảng nguồn tồn tại; với onFail: HALT, migration dừng nếu điều kiện không đạt.
- **rollback** minh họa thao tác xóa view khi rollback changeset, nhưng không khôi phục tự động định nghĩa trước đó.

Cần lưu ý tên schema, quyền truy cập, cú pháp createView và khả năng thay thế của hệ quản trị phải được xác minh trên phiên bản Liquibase/database thực tế.

### 7.3. Triển khai lần đầu

Khi changeset chưa có trong DATABASECHANGELOG, lệnh update dự kiến tạo view và ghi nhận nó như changeset đã thực thi. Sau triển khai, có thể kiểm tra trực tiếp:

~~~sql
SELECT
    status,
    order_count,
    total_amount
FROM order_status_summary
ORDER BY status;
~~~

Sau đó, Liquibase có thể bỏ qua changeset ở lần update kế tiếp nếu định nghĩa không thay đổi.

### 7.4. Cập nhật nghiệp vụ trong cùng changeset

Một phiên bản báo cáo mới cần **loại trừ đơn bị hủy**. Giữ nguyên id, author, đường dẫn changelog, runOnChange, các điều kiện và tên view; chỉ thay phần định nghĩa:

~~~yaml
      changes:
        - createView:
            viewName: order_status_summary
            replaceIfExists: true
            selectQuery: |
              SELECT
                  status,
                  COUNT(*) AS order_count,
                  COALESCE(SUM(total_amount), 0) AS total_amount
              FROM orders
              WHERE status <> 'CANCELLED'
              GROUP BY status
~~~

Đây là **trích đoạn thay thế thuộc tính changes của cùng changeset**, không phải một changeset mới. Khi chạy Liquibase trên database đã triển khai định nghĩa cũ, checksum sẽ thay đổi và Liquibase dự kiến thực thi lại createView. Nếu thao tác CREATE OR REPLACE VIEW được hỗ trợ, truy vấn báo cáo sẽ được cập nhật mà không cần xóa thủ công view trước đó.

Trong ví dụ, danh sách cột kết quả giữ nguyên **status**, **order_count**, **total_amount**, giúp việc thay thế view ở PostgreSQL dễ tương thích hơn. Tuy nhiên, thay đổi lọc dữ liệu có thể ảnh hưởng dashboard hoặc API; vẫn phải review kết quả nghiệp vụ.

### 7.5. Vì sao không tự tạo id mới khi muốn chạy lại?

Nếu đổi id thành view-order-status-summary-v2, Liquibase sẽ xem đây là **changeset khác**. Đối với trường hợp muốn cùng changeset được cập nhật theo runOnChange, cần giữ nguyên danh tính của nó.

Ngược lại, nếu thay đổi có tính bước ngoặt, ví dụ xóa cột kết quả của view, đổi tên đối tượng hoặc phải di chuyển dữ liệu, việc tạo changeset mới với quy trình chuyển đổi riêng có thể là lựa chọn phù hợp hơn. RunOnChange không bắt buộc mọi phiên bản của view phải ở cùng một changeset mãi mãi.

## 8. Ví dụ: function PostgreSQL với SQL tùy chỉnh

Một function thường có phần thân gồm nhiều dấu chấm phẩy. Khi đưa SQL định nghĩa function vào Liquibase YAML, cần bảo đảm Liquibase không tách sai câu lệnh thành những mảnh nhỏ.

Ví dụ function chuẩn hóa khoảng trắng và chuyển tên khách hàng sang chữ hoa:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: fn-normalize-customer-name
      author: platform-team
      runOnChange: true
      comment: Định nghĩa function chuẩn hóa tên khách hàng
      changes:
        - sql:
            splitStatements: false
            sql: |
              CREATE OR REPLACE FUNCTION normalize_customer_name(name_in text)
              RETURNS text
              LANGUAGE sql
              AS $body$
                  SELECT UPPER(BTRIM(name_in));
              $body$;
      rollback:
        - sql:
            sql: |
              DROP FUNCTION IF EXISTS normalize_customer_name(text);
~~~

**splitStatements: false** yêu cầu Liquibase chuyển nguyên khối SQL tới database thay vì tự tách theo dấu kết thúc câu lệnh thông thường. Điều này hữu ích với function có thân SQL chứa dấu chấm phẩy. Với hệ quản trị khác, cú pháp tạo function/procedure và yêu cầu về delimiter có thể khác.

Khi sửa logic bên trong function nhưng vẫn giữ chữ ký tương thích, ví dụ thay đổi quy tắc chuẩn hóa, nhóm cập nhật câu CREATE OR REPLACE FUNCTION trong **cùng changeset**. Chạy update trên database đã có bản cũ sẽ giúp Liquibase phát hiện checksum mới và thực thi lại định nghĩa.

Lệnh rollback trên **xóa function**, không tự phục hồi mã cũ. Nếu cần khôi phục định nghĩa trước đó, phải có quy trình cụ thể sử dụng bản mã nguồn đã kiểm chứng hoặc một migration phục hồi.

## 9. Kiểm chứng bằng Liquibase CLI

Giả sử dự án đã cấu hình đúng JDBC URL, tài khoản, quyền, driver và tệp changelog. Ví dụ lệnh theo cú pháp CLI hiện đại:

~~~bash
liquibase --defaults-file=liquibase.properties validate
liquibase --defaults-file=liquibase.properties status --verbose
liquibase --defaults-file=liquibase.properties update-sql
~~~

Mục đích:

1. **validate**: kiểm tra cấu trúc changelog và những vấn đề Liquibase phát hiện được trước khi thực thi.
2. **status --verbose**: hỗ trợ quan sát những changeset chưa được áp dụng theo môi trường đích. Không nên dựa một mình vào status để kết luận đầy đủ về mọi thay đổi runOnChange.
3. **update-sql**: sinh SQL dự kiến, giúp reviewer kiểm tra có phát sinh CREATE OR REPLACE đúng đối tượng hay không.

Tên lệnh và tùy chọn có thể khác giữa các dòng phiên bản Liquibase; hãy dùng tài liệu của bản CLI được cố định trong dự án. Trên một số tài liệu hoặc phiên bản cũ, tên update-sql được viết theo dạng updateSQL.

Sau khi review và thử trên database kiểm thử, thực hiện:

~~~bash
liquibase --defaults-file=liquibase.properties update
~~~

Tại PostgreSQL, có thể tham khảo thông tin lịch sử bằng truy vấn chỉ đọc sau (tên bảng/cột phản ánh cấu hình mặc định và cơ chế PostgreSQL tự chuyển định danh không đặt dấu nháy sang chữ thường):

~~~sql
SELECT
    id,
    author,
    filename,
    exectype,
    md5sum,
    dateexecuted
FROM databasechangelog
WHERE id = 'view-order-status-summary'
  AND author = 'platform-team';
~~~

Sau lần chạy đầu, EXECTYPE thường là **EXECUTED**; sau lần chạy lại có nội dung thay đổi, giá trị thường là **RERAN**. Dữ liệu thực tế phụ thuộc phiên bản Liquibase và cấu hình; hãy kiểm chứng trên database thật thay vì giả định kết quả. Bảng DATABASECHANGELOG có thể đặt ở schema riêng theo cấu hình nên cần truy vấn đúng nơi lưu lịch sử.

**Không tự chỉnh sửa MD5SUM hoặc EXECTYPE trong bảng này** để làm thỏa một bài kiểm tra. Nếu checksum khác kỳ vọng, cần xác định changeset đã đổi phần nào và Liquibase có được phép chạy lại theo chính sách hay không.

## 10. Kiểm thử để chứng minh runOnChange thực sự hoạt động

Một bài thực hành nên có ít nhất năm điểm kiểm chứng:

| Bước | Hành động | Kỳ vọng |
|---|---|---|
| 1 | Chạy update với định nghĩa view V1 | View được tạo; changeset có bản ghi lịch sử |
| 2 | Chạy lại update mà không sửa changeset | Không thực thi lại view do checksum không đổi |
| 3 | Sửa phần SELECT thành V2 và chạy update-sql | SQL dự kiến thể hiện thao tác thay thế view |
| 4 | Chạy update để áp dụng V2 | View có hành vi mới; lịch sử phản ánh việc chạy lại |
| 5 | Chạy update thêm lần nữa mà không sửa | Không lặp lại thao tác vì checksum ổn định |

Nên kiểm tra **kết quả truy vấn**, không chỉ log CLI. Với ví dụ view đơn hàng, có thể chèn dữ liệu test hợp lệ gồm trạng thái CANCELLED và trạng thái khác. Ở V1, dữ liệu CANCELLED xuất hiện trong tổng hợp; ở V2, nhóm dòng đó không còn xuất hiện. Chỉ dùng dữ liệu giả trong database dành cho bài học.

Ngoài ra, thử các trường hợp:

- Sửa comment hoặc khoảng trắng rồi quan sát Liquibase có chạy lại không.
- Thay đổi SQL dẫn tới checksum mới và kiểm tra câu lệnh sinh ra.
- Cho precondition thất bại trong database test, xác nhận pipeline dừng và không đánh dấu sai trạng thái.
- Thử trên PostgreSQL version dự định sử dụng, đặc biệt khi CREATE OR REPLACE bị giới hạn bởi cấu trúc view.
- Nếu có context/label filter, xác minh changeset được chọn ở đúng môi trường.

Đừng dùng kết quả của bước chạy trên một database rỗng để suy luận chắc chắn về việc thay thế view đang được những view hoặc function khác phụ thuộc ở production.

## 11. Rollback của runOnChange có điểm gì khác?

RunOnChange khiến **một changeset có thể được thực thi ở nhiều phiên bản nội dung khác nhau**, nhưng Liquibase không tự lưu toàn bộ định nghĩa cũ của đối tượng vào bảng DATABASECHANGELOG để khôi phục theo từng phiên bản trước đó.

Với ví dụ view:

~~~yaml
      rollback:
        - dropView:
            viewName: order_status_summary
~~~

Rollback này xóa view, chứ **không chuyển định nghĩa V2 ngược về V1**. Nếu ứng dụng đang phụ thuộc vào view, thao tác xóa có thể làm hỏng truy vấn ngay cả khi rollback kết thúc thành công.

Các chiến lược thường hợp lý hơn khi lỗi định nghĩa:

1. **Forward fix**: tạo bản định nghĩa V3 sửa lỗi rồi triển khai có kiểm chứng.
2. **Khôi phục bản định nghĩa tốt từ Git**: xác định đúng release, review SQL và chủ động áp dụng theo quy trình thay thế đối tượng.
3. **Migration phục hồi có id mới**: dùng khi cần đảm bảo một bước khôi phục tách biệt, có thể review và theo dõi.

Nếu cần rollback theo tag hoặc số changeset, phải hiểu Liquibase sẽ áp dụng định nghĩa rollback nào và tương tác của nó với các changeset khác. Không nên xem rollback mặc định là cơ chế version control cho mã nguồn stored procedure/view.

Đối với thay đổi dữ liệu không thể đảo ngược, hoặc thao tác xóa bảng/cột, phải có kế hoạch backup và khôi phục riêng. RunOnChange không tạo khả năng phục hồi dữ liệu đã bị mất.

## 12. Những rủi ro kỹ thuật khi thay thế view/function

### 12.1. Giới hạn CREATE OR REPLACE

Trên PostgreSQL, CREATE OR REPLACE VIEW không cho phép thay đổi tùy tiện tên, kiểu và thứ tự của các cột hiện hữu. Có thể phải thực hiện migration riêng khi đổi hợp đồng dữ liệu của view, đặc biệt khi các ứng dụng hoặc đối tượng khác đang truy vấn theo tên cột cũ.

Với function, CREATE OR REPLACE FUNCTION phụ thuộc vào **tên và kiểu tham số đầu vào** để nhận diện chữ ký; thay đổi chữ ký có thể tạo overload mới. Thay đổi kiểu kết quả cũng có thể không được cho phép nếu không xử lý function cũ. Vì vậy, một lệnh CREATE OR REPLACE hợp lệ về mặt cú pháp vẫn chưa chứng minh thay đổi tương thích.

### 12.2. Phụ thuộc giữa các đối tượng

Một view báo cáo có thể được view khác, dashboard, ORM mapping hoặc API sử dụng. Sửa biểu thức lọc hoặc kiểu kết quả có thể thay đổi nghiệp vụ ở nhiều nơi. Quy trình review nên xác định các phụ thuộc và kiểm thử truy vấn tiêu thụ view/function.

### 12.3. Quyền truy cập và chủ sở hữu

Tài khoản migration cần quyền thay thế đối tượng theo quy định hệ quản trị. Quyền tạo mới, thay thế và thay đổi owner không giống nhau. Nếu PostgreSQL từ chối vì đối tượng thuộc người dùng khác, không nên mở quyền quản trị toàn hệ thống chỉ để chạy được migration; hãy chuẩn hóa owner và quyền triển khai theo chính sách.

### 12.4. Tính nguyên tử và lỗi giữa chừng

Không phải mọi DBMS đều hỗ trợ giao dịch DDL giống nhau. Nếu changeset chứa nhiều thao tác, một phần có thể đã thay đổi trước khi lệnh tiếp theo thất bại. Vì vậy, nên giữ changeset runOnChange tập trung vào một định nghĩa có thể thay thế, kiểm tra hỗ trợ giao dịch của DBMS và thiết kế phương án xử lý trạng thái dở dang.

### 12.5. Rủi ro bị triển khai ngược

Giả sử production đang dùng view V3. Một pipeline cũ chứa định nghĩa V2 nhưng cùng changeset runOnChange có thể chạy sau đó. Vì nội dung của V2 khác checksum V3, Liquibase có thể **chạy lại V2** và thay thế view mới bằng định nghĩa cũ.

Đây là rủi ro đặc trưng của việc dùng cùng một changeset có thể thay đổi qua nhiều release. Phải bảo vệ production bằng cách chỉ cho phép artifact được phê duyệt chạy migration, khóa phiên bản release, kiểm soát thứ tự deployment và ngăn job cũ cập nhật nhầm schema sau khi release mới đã triển khai.

## 13. runOnChange và các môi trường dev, test, production

Mỗi môi trường lưu lịch sử changeset riêng trong DATABASECHANGELOG. Ví dụ:

| Môi trường | Định nghĩa view hiện tại | Checksum của changeset |
|---|---|---|
| Dev | V3 | Checksum tương ứng V3 |
| Test | V2 | Checksum tương ứng V2 |
| Production | V1 | Checksum tương ứng V1 |

Đây chỉ là trạng thái minh họa, không phải checksum thực tế. Khi đưa **cùng artifact chứa V3** lên test và production, Liquibase so sánh nội dung hiện tại với lịch sử riêng của từng database và có thể chạy lại changeset ở những nơi chưa có checksum V3.

Điều quan trọng là dùng **cùng revision changelog đã kiểm thử** khi chuyển qua các môi trường, đồng thời quản lý riêng thông tin kết nối, quyền, mật khẩu và điều kiện phát hành. Không sửa trực tiếp nội dung view trong production để “cho giống” dev vì như vậy có thể tạo drift ngoài lịch sử Liquibase.

Các cơ chế **context** và **label** vẫn tác động đến việc có xét changeset ở một lượt update hay không. Nếu changeset runOnChange bị loại bởi bộ lọc, nó không tự chạy chỉ vì checksum đã thay đổi. Với một view thiết yếu cho ứng dụng, hãy cân nhắc không gắn bộ lọc tùy chọn làm bỏ sót thay đổi bắt buộc.

Nếu Spring Boot có Liquibase tự chạy khi khởi động và CI/CD cũng có job migration, cần quy định **một chủ sở hữu** cho mỗi lượt triển khai. Bảng DATABASECHANGELOGLOCK giúp điều phối việc chạy đồng thời, nhưng không giải quyết xung đột release V2/V3 hoặc việc dùng sai cấu hình môi trường.

## 14. Vấn đề khi đổi tên, di chuyển changelog

Danh tính changeset gắn với id, author và đường dẫn changelog hoặc logicalFilePath được cấu hình. Nếu di chuyển tệp chứa changeset sang đường dẫn mới mà không bảo toàn danh tính, Liquibase có thể xem nó như changeset chưa từng chạy.

Với một changeset runOnChange chứa CREATE OR REPLACE, việc bị nhận diện thành changeset mới có thể gây khó theo dõi; với những thao tác không an toàn khi chạy lặp, hậu quả còn nghiêm trọng hơn. Do đó, nhóm cần quy ước ổn định cho tên tệp và cấu trúc changelog.

Khi cần tổ chức lại các tệp, hãy tìm hiểu thuộc tính **logicalFilePath**, kiểm thử cách Liquibase nhận diện changeset trên một bản sao database đã có lịch sử và kiểm tra SQL dự kiến. Không tự thay đổi FILENAME trong DATABASECHANGELOG bằng tay để “sửa” vấn đề đường dẫn.

## 15. Những tình huống không nên dùng runOnChange

| Tình huống | Vì sao nguy hiểm? | Cách tổ chức phù hợp hơn |
|---|---|---|
| INSERT dữ liệu nghiệp vụ sau mỗi lần sửa câu lệnh | Dễ chèn trùng hoặc làm sai trạng thái dữ liệu | Dùng changeset mới, khóa duy nhất và logic cập nhật dữ liệu có kiểm soát |
| Thêm cột/khóa ngoại | Chạy lặp có thể lỗi “đã tồn tại” hoặc thay đổi schema ngoài dự kiến | Một changeset mới cho mỗi bước cấu trúc |
| DROP TABLE hoặc DROP COLUMN | Lặp lại thao tác phá hủy; không phục hồi dữ liệu đã mất | Migration riêng có kế hoạch backup và rollback/khôi phục |
| Chuyển đổi dữ liệu không thể đảo ngược | Có thể biến đổi dữ liệu lần thứ hai hoặc không còn đầu vào gốc | Changeset chuyển đổi phiên bản hóa, kiểm tra idempotency và dữ liệu |
| Thay đổi chữ ký function làm phá vỡ tương thích | CREATE OR REPLACE không nhất thiết cập nhật đúng đối tượng cũ | Migration chuyển đổi function và phụ thuộc theo thứ tự |
| Sửa object thủ công trên production rồi mong Liquibase tự nhận biết | Checksum vẫn tính từ changelog; có thể không đổi | Phát hiện drift bằng kiểm tra độc lập, sau đó triển khai thay đổi có quản lý |
| Sửa comment để ép cập nhật view | Comment/khoảng trắng có thể không ảnh hưởng cơ chế runOnChange | Dùng thay đổi định nghĩa có ý nghĩa hoặc quy trình triển khai lại được kiểm soát |
| Cho nhiều release cũ/mới chạy song song | Định nghĩa có thể bị ghi đè qua lại | Kiểm soát artifact được phép triển khai và thứ tự release |

Đặc biệt, **clear-checksums** là thao tác quản trị checksum, không phải cách mặc định để ép runOnChange chạy lại. Việc xóa rồi tính lại checksum có thể che lấp lịch sử thay đổi nội dung mà không thực thi SQL như mong đợi. Chỉ dùng các thao tác quản trị này khi hiểu chính xác trạng thái cơ sở dữ liệu và được quy trình vận hành cho phép.

## 16. Quy trình làm việc được đề xuất

Khi cập nhật một đối tượng bằng runOnChange, hãy thực hiện:

1. **Xác định đối tượng có thể thay thế**: view/function/procedure có định nghĩa đầy đủ; kiểm tra DBMS có cơ chế thay thế phù hợp.
2. **Kiểm tra phụ thuộc**: bảng, cột, chữ ký, kiểu dữ liệu, quyền, owner, ứng dụng và báo cáo sử dụng đối tượng.
3. **Chỉnh sửa trong cùng changeset**: giữ nguyên id/author/đường dẫn; chỉ thay nội dung định nghĩa cần thiết, giữ runOnChange: true.
4. **Kiểm tra YAML/SQL**: chạy validate và review nội dung thay đổi trong Git.
5. **Xem trước SQL**: chạy update-sql với đúng phiên bản Liquibase và database đích đại diện.
6. **Chạy trên dev/test**: xác nhận lần đầu, lần chạy lại khi checksum thay đổi và lần bỏ qua khi checksum không đổi.
7. **Kiểm chứng hành vi nghiệp vụ**: truy vấn view/function bằng dữ liệu thử có cả trường hợp biên.
8. **Đánh giá cách khôi phục**: xác nhận rollback có thể làm gì, chuẩn bị định nghĩa phiên bản trước và phương án forward fix nếu cần.
9. **Promote cùng artifact**: triển khai lên staging/production theo thứ tự; ngăn pipeline chứa định nghĩa cũ chạy sau pipeline mới.
10. **Kiểm tra sau triển khai**: đối chiếu định nghĩa đối tượng, bảng DATABASECHANGELOG, log migration và kết quả ứng dụng.

Trong pipeline CI/CD, tách quyền tài khoản migration khỏi quyền runtime của ứng dụng khi có thể, lưu secret ở hệ thống quản lý bí mật và kiểm tra JDBC URL/schema đích trước khi chạy update. Không dùng cùng cấu hình kết nối cho dev/test/production.

## 17. Bài tập suy luận

**Tình huống A:** Bạn sửa định nghĩa view bằng cách thêm điều kiện WHERE, giữ nguyên id/author và runOnChange: true. Changelog đã chạy V1 trên test.

- Điều gì xảy ra khi chạy update-sql trên test?
- Sau khi triển khai V2, lần chạy update kế tiếp với cùng artifact có cần thay thế view nữa không?
- Tại sao việc chỉnh sửa comment không phải cách đáng tin cậy để ép chạy lại?

**Hướng giải:** Liquibase dự kiến nhận diện checksum thay đổi và sinh SQL thay thế view; sau khi đã ghi checksum V2, lần update khác với cùng nội dung thường bỏ qua. Comment/khoảng trắng không phải tín hiệu thay đổi định nghĩa có ý nghĩa và có thể không kích hoạt chạy lại.

**Tình huống B:** Production đang có V3 nhưng người vận hành vô tình chạy pipeline từ một nhánh cũ chứa V2, cùng id/author và runOnChange.

- Vì sao runOnChange có thể khiến V2 được triển khai lại?
- Cần bảo vệ quy trình thế nào?

**Hướng giải:** Checksum V2 khác checksum V3 đã lưu, nên Liquibase có thể xem đây là thay đổi cần thực thi lại. Cần dùng artifact được phê duyệt, kiểm soát thứ tự release, xác minh phiên bản và chặn job cũ chạy sau job mới.

**Tình huống C:** Một changeset runOnChange có rollback là DROP VIEW. Sau khi chạy V2, ứng dụng báo lỗi và nhóm muốn quay về V1.

- Rollback đó có khôi phục V1 không?
- Có thể giải quyết thế nào?

**Hướng giải:** DROP VIEW sẽ xóa view; nó không tự lưu và phục hồi truy vấn V1. Cần chuẩn bị SQL định nghĩa V1 từ bản mã nguồn đã kiểm thử hoặc tạo bản V3 sửa lỗi, rồi triển khai theo quy trình có kiểm soát.

## 18. Checklist tự đánh giá

- [ ] Tôi giải thích được runOnChange chạy lần đầu và chạy lại khi checksum của changeset thay đổi.
- [ ] Tôi phân biệt được runOnChange với runAlways và changeset mặc định.
- [ ] Tôi hiểu id/author/đường dẫn phải được giữ ổn định để Liquibase nhận diện cùng changeset.
- [ ] Tôi biết vì sao whitespace/comment không phải cách đáng tin cậy để ép changeset chạy lại.
- [ ] Tôi viết được changeset YAML tạo hoặc thay thế view, có runOnChange, precondition và rollback minh họa.
- [ ] Tôi kiểm tra được output của validate, update-sql và kết quả truy vấn object trong database test.
- [ ] Tôi nhận diện được giới hạn CREATE OR REPLACE của DBMS và tác động đến đối tượng phụ thuộc.
- [ ] Tôi hiểu rollback xóa view/function không đồng nghĩa khôi phục phiên bản trước.
- [ ] Tôi biết cách tránh release cũ ghi đè lại định nghĩa từ release mới.
- [ ] Tôi không dùng runOnChange cho DML hoặc DDL có tác dụng phá hủy không an toàn khi lặp.
- [ ] Tôi biết checksum không tự kiểm tra mọi khác biệt do người khác sửa tay trong database.
- [ ] Tôi tách thông tin kết nối, secret và quyền của dev/test/prod khi thực hành.

## 19. Kết luận

**runOnChange** là công cụ hữu ích khi quản lý **định nghĩa có thể thay thế** trong Liquibase. Nó cho phép cùng một changeset được áp dụng lần đầu, bỏ qua khi checksum không đổi và chạy lại khi nội dung có ảnh hưởng đến checksum thay đổi. Cách này đặc biệt phù hợp với view, function hoặc procedure được khai báo bằng định nghĩa đầy đủ và triển khai theo cơ chế thay thế an toàn của hệ quản trị.

Để sử dụng runOnChange đúng, cần kết hợp **changeset có danh tính ổn định**, **kiểm tra checksum và DATABASECHANGELOG**, **review SQL dự kiến**, **kiểm thử trên dữ liệu đại diện**, **kế hoạch khôi phục định nghĩa** và **quản lý thứ tự release**. RunOnChange giúp đơn giản hóa cập nhật một số đối tượng, nhưng không thay thế kỷ luật migration có phiên bản, không tự phát hiện drift và không biến mọi thao tác chạy lại thành an toàn.

