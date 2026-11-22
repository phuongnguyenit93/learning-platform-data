
# Comments và siêu dữ liệu phục vụ truy vết thay đổi

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase giúp quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Mỗi changeset chứa thao tác kỹ thuật, nhưng một hệ thống migration vận hành lâu dài còn phải trả lời được **ai mô tả thay đổi, thay đổi nhằm giải quyết vấn đề gì, xuất hiện trong phiên bản mã nguồn nào, đã được áp dụng ở database nào và kết quả thực thi ra sao**.

Các câu trả lời đó đến từ **comments và siêu dữ liệu (metadata)** trong changeset, kết hợp với bảng lịch sử DATABASECHANGELOG, hệ thống quản lý mã nguồn và pipeline triển khai. Metadata rõ ràng giúp review thuận lợi hơn, giảm rủi ro sửa nhầm migration cũ, hỗ trợ chẩn đoán sự cố và làm bằng chứng khi đối chiếu trạng thái giữa development, staging và production.

Bài thuộc chương **Changeset** này hướng dẫn khai báo comment, nhận diện và phân loại metadata, thiết lập quy ước truy vết, đọc lịch sử trong database, cũng như liên kết migration với Spring Boot hoặc CI/CD. Mục tiêu không chỉ là biết cú pháp mà còn biết **thông tin nào thực sự được Liquibase lưu lại** và **thông tin nào nhóm cần lưu bằng công cụ bên ngoài**.

## 1. Comments và metadata giải quyết vấn đề gì?

Giả sử một hệ thống quản lý đơn hàng có một changeset bổ sung cột status vào bảng customer. Câu lệnh addColumn chỉ cho biết thao tác tạo cột. Nó chưa giải thích:

- Vì sao cần cột status và hệ thống nào sẽ sử dụng cột đó?
- Tại sao cột được phép null trong giai đoạn đầu?
- Dữ liệu cũ được chuyển đổi như thế nào?
- Thay đổi này thuộc yêu cầu hoặc pull request nào?
- Những môi trường nào đã chạy changeset?
- Có thể rollback mà không mất dữ liệu phát sinh sau khi triển khai không?

Một comment hữu ích ghi lại **bối cảnh và chủ đích**, còn metadata cung cấp **định danh và điều kiện thực thi** để truy vết thay đổi. Hai lớp này bổ sung cho SQL hoặc change type; chúng không thay thế việc kiểm tra schema thực tế và kết quả chạy migration.

Ví dụ, comment “Thêm cột status” chỉ nhắc lại thao tác mà người đọc đã thấy trong YAML. Comment “Mở đường chuyển luồng xét duyệt khách hàng sang status; giữ nullable để bản ứng dụng cũ tiếp tục ghi dữ liệu trong giai đoạn triển khai song song” giải thích quyết định thiết kế. Nếu gắn thêm một mã công việc ổn định, người vận hành có thể tìm lại yêu cầu gốc khi xảy ra vấn đề.

## 2. Ba lớp thông tin phục vụ truy vết

Khi điều tra một migration, nên phân biệt ba lớp thông tin:

| Lớp | Nguồn | Trả lời câu hỏi | Giới hạn |
|---|---|---|---|
| Khai báo changeset | Changelog trong Git: id, author, comment, context, label, precondition, changes, rollback | Dự kiến làm gì, vì sao và trong điều kiện nào | Chưa chứng minh database đã thực thi |
| Lịch sử Liquibase | DATABASECHANGELOG trong từng database | Changeset nào được ghi nhận, thời điểm, checksum và trạng thái thực thi | Không lưu đầy đủ PR, Git SHA, log ứng dụng hoặc toàn bộ schema thực tế |
| Lịch sử phát hành | Git, pull request, issue tracker, artifact, log CI/CD, release record | Ai review, commit nào, build nào, job nào, triển khai ở đâu | Chỉ đáng tin khi được lưu và liên kết nhất quán |

Chẳng hạn, từ Git tìm được thay đổi trong commit A; từ CI/CD biết artifact của commit A được triển khai vào staging; từ DATABASECHANGELOG ở staging biết changeset của commit A đã được ghi nhận. Ba dữ kiện liên kết với nhau mới hình thành chuỗi truy vết hữu ích.

Không nên đồng nhất một row trong DATABASECHANGELOG với một lần triển khai ứng dụng hoàn chỉnh. Trong một lần deployment có thể có nhiều changeset; cũng có thể không có changeset mới vì database đã ở trạng thái mong muốn.

## 3. Nhóm metadata cốt lõi của changeset

Một changeset có nhiều thuộc tính. Một số tạo thành **định danh**, một số mô tả mục đích, một số điều khiển điều kiện chạy và một số quyết định cách Liquibase xử lý lại.

| Thuộc tính | Ý nghĩa | Gợi ý sử dụng |
|---|---|---|
| **id** | Mã changeset trong phạm vi author và đường dẫn changelog | Dùng giá trị ổn định, dễ tìm; không tái sử dụng tùy tiện |
| **author** | Tác giả/nhóm được khai báo trong changeset | Chọn định danh ổn định theo quy ước nhóm; tránh đổi sau triển khai |
| **Đường dẫn changelog / FILENAME** | Thành phần đường dẫn được Liquibase dùng để định danh changeset | Không đổi tên hay di chuyển tệp đã phát hành thiếu kiểm soát |
| **comment** | Giải thích chủ đích, bối cảnh hoặc ràng buộc | Ưu tiên ghi “vì sao”, không chỉ nhắc lại change type |
| **context / contextFilter** | Giới hạn hoặc điều kiện chọn changeset theo context | Chỉ dùng khi có quy tắc triển khai rõ ràng |
| **labels** | Nhãn biểu thức để nhóm và lọc changeset | Đặt nhãn có ý nghĩa ổn định, được review |
| **dbms** | Chỉ định DBMS mà changeset áp dụng | Dùng cho SQL hoặc tính năng phụ thuộc hệ quản trị |
| **runOnChange** | Cho phép thực thi lại khi nội dung hợp lệ của changeset thay đổi | Chỉ thích hợp cho trường hợp được thiết kế chạy lại, không làm giải pháp chung cho sửa migration |
| **runAlways** | Yêu cầu changeset được xét chạy lại mỗi lần update phù hợp | Cân nhắc tác động và tính idempotent |
| **runInTransaction** | Điều khiển việc chạy trong transaction khi DBMS và loại thay đổi hỗ trợ | Đánh giá ảnh hưởng khi thay đổi có nhiều câu lệnh |
| **preConditions** | Kiểm tra điều kiện trước khi thực hiện migration | Nêu rõ hành vi khi điều kiện thất bại |
| **rollback** | Mô tả cách hoàn tác nếu có thể | Kiểm tra dữ liệu và khả năng tương thích với phiên bản ứng dụng |

Không phải tất cả thuộc tính đều được lưu nguyên dạng vào DATABASECHANGELOG; bảng lịch sử chứa một tập cột chuẩn và thông tin Liquibase tính toán khi thực thi. Để xem đầy đủ ngữ nghĩa của migration, cần lưu lại changelog tại đúng revision đã phát hành.

**id + author + đường dẫn changelog** là bộ nhận diện changeset thông thường. Comment và label có thể giúp tìm kiếm hoặc lọc, nhưng **không được dùng thay cho bộ định danh**. Nếu hai changeset có comment giống nhau, chúng vẫn là hai changeset khác khi bộ nhận diện khác nhau.

## 4. Ví dụ YAML: comment giải thích bối cảnh thay đổi

Xét một changeset được lưu trong tệp db/changelog/changes/2026/20261119-01-add-customer-status.yaml:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-01-add-customer-status
      author: customer-team
      comment: >-
        CUSTOMER-142: Mở rộng schema cho luồng quản lý trạng thái khách hàng.
        Giữ status nullable trong giai đoạn chuyển đổi để ứng dụng phiên bản cũ
        vẫn tương thích; backfill và ràng buộc NOT NULL sẽ thực hiện ở
        changeset thuộc lần phát hành sau.
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: customer
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: status
                  type: varchar(20)
                  constraints:
                    nullable: true
      rollback:
        - dropColumn:
            tableName: customer
            columnName: status
~~~

Đoạn khai báo thể hiện nhiều lớp thông tin:

1. **id** chứa ngày và hành động để người đọc nhận diện thay đổi; bản thân Liquibase không dùng ngày trong id để sắp xếp changeset.
2. **author** xác định nhóm chịu trách nhiệm khai báo. Nó không chứng minh người nào đã bấm nút triển khai.
3. **comment** ghi mã công việc và lý do giữ cột nullable, giúp người review hiểu tại sao migration chưa tạo constraint chặt hơn.
4. **preConditions** yêu cầu bảng customer tồn tại và dừng nếu điều kiện không đạt.
5. **changes** là thao tác schema thực tế.
6. **rollback** khai báo thao tác xóa cột nếu cần quay lui; việc xóa cột có thể làm mất dữ liệu và phải được đánh giá trước khi áp dụng.

Cú pháp YAML sử dụng chuỗi gộp nhiều dòng với ký hiệu >-. Khi đọc, nội dung được chuẩn hóa thành một giá trị chuỗi, thích hợp cho comment dài. Với nội dung ngắn, có thể viết trực tiếp:

~~~yaml
comment: "CUSTOMER-142: Thêm status để chuẩn bị thay luồng xét duyệt."
~~~

Chỉ đưa thông tin có ích, ổn định và an toàn vào comment. Không ghi password, token, thông tin cá nhân nhạy cảm hoặc dữ liệu production trong phần mô tả, vì changelog và bảng lịch sử có thể được sao chép sang nhiều môi trường hoặc xuất vào báo cáo.

## 5. Comment Liquibase khác comment thông thường trong tệp

Trong YAML, hai cách viết dưới đây không tương đương:

~~~yaml
databaseChangeLog:
  # CUSTOMER-142: Thêm status cho khách hàng.
  - changeSet:
      id: 20261119-01
      author: customer-team
      comment: "CUSTOMER-142: Chuẩn bị chuyển logic xét duyệt sang status."
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: status
                  type: varchar(20)
~~~

Dòng bắt đầu bằng dấu **#** là chú thích của cú pháp YAML. Parser YAML thường bỏ qua nội dung này khi xây dựng cấu trúc dữ liệu. Nó giúp người đọc file nguồn nhưng không phải trường comment thuộc changeset để Liquibase ghi nhận theo cơ chế dành cho comment.

Trái lại, thuộc tính **comment** nằm trong changeSet là metadata của changeset. Liquibase có thể đưa nội dung này vào cột COMMENTS trong DATABASECHANGELOG khi changeset được ghi nhận. Vì vậy, comment của Liquibase phù hợp để viết lý do thay đổi phục vụ truy vết qua database.

Nên dùng comment YAML cho ghi chú nhỏ về cấu trúc file hoặc cách tổ chức include; dùng comment của changeset để giải thích bối cảnh migration cần được theo dõi cùng lịch sử triển khai.

Tương tự, comment trong câu lệnh SQL hoặc comment của trình soạn thảo code không tự động trở thành comment metadata của changeset. Khi chuyển giữa YAML, XML và formatted SQL, phải dùng cú pháp tương ứng của từng định dạng.

## 6. Comment trong XML và formatted SQL

Liquibase hỗ trợ nhiều định dạng changelog. Metadata phục vụ cùng mục đích nhưng cú pháp khai báo khác nhau.

### 6.1. XML changelog

Trong XML, có thể đặt phần tử **comment** trong **changeSet**:

~~~xml
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.liquibase.org/xml/ns/dbchangelog https://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-latest.xsd">

    <changeSet id="20261119-02-create-index" author="customer-team">
        <comment>
            CUSTOMER-147: Tạo index cho truy vấn tra cứu email của khách hàng.
        </comment>
        <createIndex indexName="idx_customer_email" tableName="customer">
            <column name="email"/>
        </createIndex>
    </changeSet>

</databaseChangeLog>
~~~

Thuộc tính id và author nằm trên changeSet, còn comment là phần tử con. Các phiên bản Liquibase có thể sử dụng XSD/namespace phù hợp riêng; khi làm việc thật, dự án nên ghim phiên bản và validate changelog theo phiên bản đang chạy.

### 6.2. Formatted SQL changelog

Ví dụ minh họa định dạng formatted SQL:

~~~sql
--liquibase formatted sql

--changeset customer-team:20261119-03-create-order-index
--comment: ORDER-233: Tăng tốc truy vấn đơn hàng theo mã khách hàng.
CREATE INDEX idx_purchase_order_customer_id
ON purchase_order(customer_id);

--rollback DROP INDEX idx_purchase_order_customer_id;
~~~

Dòng **--changeset** khai báo author và id; **--comment:** là chỉ thị metadata của Liquibase trong formatted SQL; **--rollback** cung cấp SQL hoàn tác. Đây là các marker đặc biệt được Liquibase hiểu khi tệp được đọc ở chế độ formatted SQL.

Khác với những dòng chú thích SQL thông thường, các chỉ thị formatted SQL có cú pháp và vị trí mang ý nghĩa với Liquibase. Tên lệnh, tham số metadata và khả năng rollback còn phụ thuộc phiên bản Liquibase và DBMS. Ví dụ DROP INDEX có cú pháp khác nhau giữa các hệ quản trị; cần điều chỉnh SQL trước khi sử dụng thực tế.

**Không chuyển đổi định dạng changelog bằng cách copy nguyên comment của một cú pháp sang cú pháp khác.** Sau khi chuyển, cần validate, kiểm tra SQL dự kiến và đối chiếu cách Liquibase nhận diện changeset.

## 7. Phân biệt người tạo changeset, người review và người triển khai

Thuộc tính author thường bị hiểu nhầm là người cuối cùng thực thi migration. Thực tế, author là **metadata được khai báo trong changelog**, không phải danh tính xác thực của tiến trình deploy.

| Vai trò | Nguồn dữ liệu nên dùng | Ý nghĩa |
|---|---|---|
| Người/nhóm khai báo changeset | author trong changelog | Định danh ổn định trong lịch sử Liquibase |
| Người viết hoặc sửa pull request | Git và hệ thống quản lý mã nguồn | Truy vết đóng góp vào source |
| Người review và phê duyệt | Pull request, quy trình review | Bằng chứng kiểm tra và quyết định chấp thuận |
| Tài khoản chạy migration | Nhật ký pipeline, hệ thống IAM/secret store | Chủ thể kỹ thuật thực thi lên database |
| Người phê duyệt production | Release approval hoặc change management | Quyết định triển khai trong môi trường quan trọng |

Có thể dùng author theo tài khoản cá nhân hoặc theo nhóm; lựa chọn tùy quy ước tổ chức. Điều quan trọng là **giá trị author ổn định sau khi changeset được triển khai**, dễ truy ngược về đội chịu trách nhiệm và không bị thay theo người chạy pipeline.

Nếu muốn biết “ai triển khai lúc 15:20?”, không thể chỉ tra AUTHOR trong DATABASECHANGELOG. Cần tra deployment log hoặc hệ thống quản lý phát hành để thấy tài khoản hoặc quy trình đã thực hiện update.

## 8. Định danh changeset: id, author và FILENAME

Giả sử master changelog include tệp changes/2026/20261119-01-add-customer-status.yaml. Liquibase nhận diện changeset dựa trên id, author và đường dẫn tệp changelog hiệu lực. Đường dẫn này thường được lưu trong cột **FILENAME** của DATABASECHANGELOG.

Nếu di chuyển tệp từ:

~~~text
db/changelog/changes/2026/20261119-01-add-customer-status.yaml
~~~

sang:

~~~text
db/changelog/archive/20261119-01-add-customer-status.yaml
~~~

mà không duy trì định danh đường dẫn logic ổn định, Liquibase có thể coi changeset ở đường dẫn mới là một changeset chưa được thực thi. Kết quả có thể là chạy lại câu lệnh thêm cột và thất bại vì cột đã tồn tại.

**logicalFilePath** là cơ chế Liquibase hỗ trợ để giữ định danh logic ổn định trong một số trường hợp tái cấu trúc file. Phạm vi khai báo và cách kế thừa tùy phiên bản và định dạng changelog. Khi có nhu cầu di chuyển tệp đã triển khai, cần:

1. Đọc FILENAME thực tế từ DATABASECHANGELOG ở database đã triển khai.
2. Kiểm tra cơ chế logicalFilePath được phiên bản Liquibase đang dùng hỗ trợ.
3. Mô phỏng thay đổi trên database có lịch sử cũ.
4. Chứng minh sau khi di chuyển, status không báo changeset cũ là pending do đổi đường dẫn.
5. Review riêng thay đổi định danh trước khi đưa vào production.

Không sửa id, author hoặc tên file đã triển khai để “đẹp” hơn. Những giá trị này liên quan trực tiếp tới lịch sử; nếu cần cải thiện cách mô tả thay đổi, có thể bổ sung tài liệu hoặc changeset mới, đồng thời bảo toàn thông tin gốc.

## 9. Tổ chức quy ước comment và mã công việc

Một comment tốt có thể theo cấu trúc dễ nhớ:

**Mã công việc — mục đích nghiệp vụ — lý do kỹ thuật đặc biệt — giới hạn hoặc bước tiếp theo.**

Ví dụ:

~~~text
PAYMENT-812: Bổ sung khóa ngoại từ payment sang purchase_order
để bảo đảm tính toàn vẹn tham chiếu. Phải chuẩn hóa dữ liệu payment
không có đơn hàng tương ứng trước khi bật constraint.
~~~

Một số quy ước hữu ích:

- **Nêu lý do:** giải thích quyết định quan trọng, đặc biệt khi schema tạm thời chấp nhận dữ liệu thiếu.
- **Gắn tham chiếu ổn định:** mã issue, RFC hoặc change request giúp tìm đúng ngữ cảnh; tránh chỉ viết liên kết tới tài nguyên có thể hết hạn.
- **Ngắn và chính xác:** comment không phải nơi sao chép toàn bộ đặc tả nghiệp vụ hay log chạy SQL.
- **Nêu rủi ro có tác động dài hạn:** ví dụ DDL có thể khóa bảng lớn, backfill cần chạy theo lô hoặc rollback không phục hồi dữ liệu.
- **Không chứa bí mật:** không ghi credentials, PII, dữ liệu mẫu nhạy cảm, token hay URL chứa mật khẩu.
- **Không tạo kỳ vọng sai:** nếu rollback chỉ xóa cột, phải nhận thức rằng dữ liệu trong cột sẽ mất; comment không được nói “rollback an toàn tuyệt đối”.
- **Không sửa comment của migration cũ như một thao tác vận hành mặc định:** lưu ý lịch sử đã triển khai có thể giữ comment cũ và quy tắc checksum phụ thuộc nội dung và phiên bản.

Comment nên bổ trợ tên file và code. Có thể dùng id mang ý nghĩa kỹ thuật, ví dụ 20261119-01-create-customer-status, đồng thời comment ghi lý do nghiệp vụ. Không cần nhét quá nhiều thông tin vào id vì id phải được giữ ổn định.

## 10. Metadata về điều kiện môi trường và lựa chọn changeset

Một số metadata mô tả **điều kiện mà changeset có thể được lựa chọn**, chứ không trực tiếp nói vì sao thay đổi được tạo:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-04-test-fixture
      author: qa-platform
      comment: >-
        QA-91: Tạo dữ liệu giả lập dành riêng cho kịch bản tích hợp.
        Không triển khai dữ liệu này tại production.
      context: "@test"
      labels: integration-fixture
      changes:
        - insert:
            tableName: customer
            columns:
              - column:
                  name: id
                  valueNumeric: 900001
              - column:
                  name: email
                  value: fixture@example.invalid
~~~

Trong ví dụ, context bắt buộc bắt đầu bằng **@** được dùng để yêu cầu bộ lọc context chỉ định rõ test ở những phiên bản Liquibase hỗ trợ cú pháp đó. Với một context thông thường, nếu không truyền context filter, Liquibase có thể vẫn xét cho chạy changeset. Vì thế, **gắn context mà không kiểm soát cấu hình gọi update là chưa đủ** để bảo đảm dữ liệu kiểm thử không xuất hiện ở production.

Metadata context, label hoặc dbms nên được review cùng pipeline và được kiểm tra bằng status hoặc updateSQL trên cấu hình tương ứng. Chúng không thay đổi bản chất của id/author/FILENAME; thay vào đó, chúng ảnh hưởng việc changeset có được lựa chọn hoặc áp dụng trong một lần chạy nhất định hay không.

Không dùng context để tạo nhiều schema cốt lõi khác nhau giữa các môi trường nếu mục tiêu là promote cùng một release. Nên giữ migration chính thống nhất, chỉ tách những tác vụ có lý do rõ ràng như fixture kiểm thử hoặc SQL đặc thù DBMS.

## 11. Cách DATABASECHANGELOG ghi nhận metadata

Khi Liquibase thực thi và ghi nhận một changeset, nó cập nhật bảng lịch sử mặc định **DATABASECHANGELOG** trong chính cơ sở dữ liệu đích. Tùy phiên bản Liquibase và DBMS, bảng thường có những cột như sau:

| Cột | Thông tin phục vụ truy vết |
|---|---|
| ID | id khai báo trong changeset |
| AUTHOR | author khai báo trong changeset |
| FILENAME | Đường dẫn changelog hiệu lực được dùng để nhận diện |
| DATEEXECUTED | Thời điểm changeset được ghi nhận thực thi |
| ORDEREXECUTED | Thứ tự thực thi được Liquibase ghi nhận |
| EXECTYPE | Cách changeset được ghi nhận, ví dụ EXECUTED, RERAN, MARK_RAN |
| MD5SUM | Checksum phục vụ đối chiếu nội dung changeset |
| DESCRIPTION | Mô tả ngắn do Liquibase tạo từ nội dung thay đổi |
| COMMENTS | Comment của changeset theo cách Liquibase ghi nhận |
| TAG | Tag Liquibase khi được gán, tùy cách dùng và phiên bản |
| LIQUIBASE | Phiên bản Liquibase được ghi nhận tại lần thực thi |
| CONTEXTS / LABELS | Thông tin context và label theo dữ liệu Liquibase lưu |
| DEPLOYMENT_ID | Mã nhóm thực thi do Liquibase cấp để liên hệ changeset trong một lần cập nhật |

Không phải mọi cột đều có mặt hoặc vận hành giống hệt nhau trong mọi phiên bản/cấu hình. Ngoài ra, cột DESCRIPTION chỉ là bản mô tả kỹ thuật ngắn, không thay thế comment có ngữ cảnh nghiệp vụ.

Một câu truy vấn kiểm tra lịch sử tham khảo:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    DATEEXECUTED,
    ORDEREXECUTED,
    EXECTYPE,
    MD5SUM,
    COMMENTS,
    DEPLOYMENT_ID
FROM DATABASECHANGELOG
ORDER BY DATEEXECUTED, ORDEREXECUTED;
~~~

Cần kết nối đúng database và schema chứa DATABASECHANGELOG. Một số môi trường đặt bảng history trong schema chuyên dụng hoặc thay đổi tên bảng qua cấu hình Liquibase, nên câu truy vấn cần điều chỉnh tương ứng.

**Không coi ORDEREXECUTED là số thứ tự toàn cục duy nhất cho mọi thời điểm**, cũng không dùng DEPLOYMENT_ID như Git commit hash. Các cột giúp truy vết lần chạy Liquibase, còn commit và artifact phải lấy từ Git hoặc CI/CD. Khi cần audit, kết hợp nhiều nguồn và tránh suy luận danh tính người deploy từ AUTHOR.

Lịch sử cũng không tự chứng minh schema hiện tại hoàn toàn đúng: database có thể bị sửa thủ công sau khi changeset chạy. Muốn xác minh drift, cần so sánh schema, dùng snapshot/diff hoặc thực hiện kiểm tra cấu trúc có mục tiêu.

## 12. Comment có thay đổi checksum hay lịch sử đã chạy không?

Checksum giúp Liquibase xác định nội dung changeset có khác với nội dung đã ghi nhận khi thực thi trước đó hay không. Tuy nhiên, **không thể giả định mọi thay đổi văn bản đều làm checksum đổi theo cùng một cách**. Những thành phần được đưa vào checksum, cách chuẩn hóa định dạng, các trường không ảnh hưởng đến checksum và hành vi cụ thể có thể phụ thuộc phiên bản Liquibase.

Vì vậy, có ba nguyên tắc cần giữ:

1. Khi changeset đã chạy ở môi trường chia sẻ, coi nội dung triển khai của nó là **bất biến**.
2. Nếu thay đổi nghiệp vụ hoặc schema cần điều chỉnh, tạo một **changeset mới** để ghi rõ lịch sử sửa chữa.
3. Không dựa vào việc chỉnh comment, xóa checksum hoặc dùng validCheckSum để âm thầm biến đổi nội dung migration đã triển khai.

Ví dụ, nếu comment của changeset cũ bị sai mã issue, việc chỉnh trên Git sau khi changeset đã chạy **không bảo đảm** cột COMMENTS ở DATABASECHANGELOG trên những database đã chạy sẽ tự cập nhật theo comment mới. Điều này tạo ra sự khác nhau giữa changelog hiện tại và lịch sử ghi nhận tại thời điểm chạy.

Nếu cần sửa thông tin mô tả đã phát hành, nhóm nên có chính sách thống nhất: ghi chú bổ sung trong issue/release record, xác nhận tác động checksum với phiên bản hiện tại và tránh giả lập lịch sử. Không tự chỉnh bảng DATABASECHANGELOG chỉ để đồng nhất comment.

## 13. Đọc metadata đúng khi runOnChange hoặc runAlways

Thông thường, changeset đã được ghi nhận chạy sẽ không chạy lại khi Liquibase update cùng database. Hai thuộc tính có thể làm khác hành vi là **runOnChange** và **runAlways**.

- **runOnChange:** một changeset được thiết kế để chạy lại khi phần nội dung được Liquibase theo dõi thay đổi. Thường phù hợp với loại đối tượng có thể cập nhật lại như view hoặc stored procedure theo khả năng DBMS.
- **runAlways:** changeset được thiết kế để chạy mỗi lần update phù hợp, kể cả khi đã có trong lịch sử. Khi có dữ liệu ghi thêm hoặc SQL không idempotent, điều này có thể gây tác động ngoài dự kiến.

Ví dụ minh họa runOnChange với view:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-05-customer-active-view
      author: reporting-team
      runOnChange: true
      comment: >-
        REPORT-76: Quản lý định nghĩa view dùng cho báo cáo khách hàng đang hoạt động.
      changes:
        - createView:
            viewName: v_active_customer
            replaceIfExists: true
            selectQuery: >-
              SELECT id, email
              FROM customer
              WHERE status = 'ACTIVE'
~~~

Chỉ dùng ví dụ theo khả năng createView, replaceIfExists và kiểu SQL của DBMS dự án. Metadata runOnChange giúp xác định chính sách chạy lại, nhưng không thay thế kiểm thử hành vi và dữ liệu của view.

Nếu changeset được chạy lại, lịch sử DATABASECHANGELOG có thể thể hiện EXECTYPE như RERAN và cập nhật một số trường theo cơ chế Liquibase. Không nên đọc comment hoặc DATEEXECUTED rồi suy ra toàn bộ các lần chạy lịch sử: DATABASECHANGELOG không phải hệ thống audit sự kiện bất biến đầy đủ. Muốn có lịch sử từng lần deploy, cần lưu log pipeline hoặc báo cáo migration riêng.

## 14. Preconditions, rollback và comment phục vụ xử lý sự cố

Comment hữu ích nhất khi kết nối được với những quyết định có thể gây tranh luận khi xử lý sự cố: precondition, rollback và lộ trình chuyển dữ liệu.

Ví dụ, nhóm cần chuẩn hóa email từ dữ liệu cũ trước khi áp dụng unique constraint. Một comment có thể giải thích:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-06-normalize-email
      author: customer-team
      comment: >-
        CUSTOMER-151: Chuẩn hóa dữ liệu email cũ trước khi áp dụng constraint mới.
        Việc chuẩn hóa phải được kiểm chứng về bản ghi trùng và dữ liệu sai;
        thay đổi dữ liệu có thể không rollback hoàn toàn nếu không lưu snapshot.
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: customer
      changes:
        - sql:
            sql: >-
              UPDATE customer
              SET email = LOWER(email)
              WHERE email IS NOT NULL
~~~

Đây là minh họa cho comment và precondition, **chưa phải migration sản xuất hoàn chỉnh**: câu lệnh LOWER có thể gây xung đột với ràng buộc unique hoặc làm mất thông tin chữ hoa/chữ thường cần giữ. Muốn dùng thật, cần thống kê dữ liệu trùng, xác định collation, backfill có kiểm chứng và thiết kế phương án phục hồi.

Comment nên giải thích lý do thay đổi, rủi ro và các tiền đề quan trọng. Precondition là **điều kiện có thể thực thi** để Liquibase kiểm tra; rollback là **thao tác có thể thực thi** để khôi phục trong phạm vi được hỗ trợ. Comment không tự áp đặt điều kiện và cũng không bảo đảm rollback sẽ thành công.

Khi đọc changelog trong tình huống khẩn cấp, có thể thực hiện theo thứ tự:

1. Xác định id, author, FILENAME, EXECTYPE và checksum của changeset gặp vấn đề.
2. Tìm đúng tệp changelog từ revision đã phát hành và đọc comment, precondition, changes, rollback.
3. Đối chiếu PR hoặc issue chứa quyết định thiết kế.
4. Kiểm tra schema và dữ liệu thực tế trên database chịu tác động.
5. Chọn rollback, forward fix hoặc phục hồi từ backup dựa trên ảnh hưởng dữ liệu.
6. Ghi nhận kết quả và thông tin deployment trong hệ thống phát hành.

Không thay đổi metadata đã triển khai để che giấu sự cố. Mục tiêu của truy vết là giữ được một chuỗi bằng chứng có thể kiểm tra lại.

## 15. Liên kết comments với Git và CI/CD

Một quy trình truy vết đầy đủ cần ghép metadata Liquibase với thông tin từ build và deploy:

~~~text
Yêu cầu / Issue
      |
      v
Pull request: code + changeset + comment
      |
      v
Review và merge commit
      |
      v
CI tạo artifact từ commit đã xác định
      |
      v
Migration job chạy Liquibase theo môi trường
      |
      v
DATABASECHANGELOG ghi changeset đã chạy
      |
      v
Release record liên kết commit, job, môi trường và kết quả
~~~

Một bảng theo dõi triển khai có thể gồm các trường sau:

| Trường trong release record | Nguồn |
|---|---|
| Release version, artifact digest, Git SHA | Pipeline build hoặc kho artifact |
| Target environment, database identifier | Cấu hình job triển khai được kiểm chứng |
| Thời điểm bắt đầu/kết thúc và job URL | CI/CD |
| Người phê duyệt, tài khoản thực thi | Quy trình release/IAM |
| Changelog revision | Commit hoặc artifact đã đóng gói |
| Changeset id, author, filename, checksum | Báo cáo Liquibase và DATABASECHANGELOG |
| Kết quả kiểm tra schema/dữ liệu | Test integration và kiểm tra sau migration |
| Mã công việc nghiệp vụ | Comment, PR và issue tracker |

Không phải mọi trường trong bảng này đều được lưu tự động trong DATABASECHANGELOG. Ví dụ, Liquibase không mặc định lưu Git SHA hoặc URL của pipeline vào từng row lịch sử. Nếu nhóm cần bằng chứng audit, pipeline phải ghi lại chúng một cách có chủ đích mà không lộ secret.

Khi deploy sang nhiều môi trường, dùng cùng artifact/changelog revision đã được test. Mỗi database có DATABASECHANGELOG riêng và có thể ở trạng thái khác nhau vào một thời điểm; comment giúp xác định ý định của changeset, còn bảng lịch sử cho biết những changeset nào đã được ghi nhận ở môi trường cụ thể.

## 16. Metadata và Spring Boot

Trong ứng dụng Spring Boot, Liquibase có thể chạy khi ứng dụng khởi động nếu dependency và cấu hình phù hợp. Ví dụ:

~~~yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USER}
    password: ${DB_PASSWORD}
  liquibase:
    change-log: classpath:db/changelog/db.changelog-master.yaml
    enabled: true
~~~

Cấu hình trên chỉ định master changelog và kết nối database. Các metadata id, author, comment và điều kiện chạy nằm trong changeset được include từ master. Nếu có nhiều instance Spring Boot cùng khởi động, DATABASECHANGELOGLOCK giúp điều phối cập nhật trên cùng database, nhưng nhóm vẫn cần kiểm soát thứ tự triển khai và nguồn chạy migration.

Một mô hình khác là chạy Liquibase trong job Maven/Gradle/CLI riêng rồi tắt migration tự động ở runtime. Dù dùng cách nào, các bằng chứng cần đối chiếu gồm changelog revision, kết quả update và bảng lịch sử của đúng database.

Khi Spring Boot khởi động thất bại do migration, hãy kiểm tra log có changeset id, author, filename và lỗi DBMS. Comment trong changelog có thể dẫn về ticket hoặc quyết định thiết kế để hiểu bối cảnh. Không dựa vào comment để kết luận schema đã ở trạng thái đúng; xác nhận trên database thật và qua lịch sử thực thi.

## 17. Chọn metadata nào nên đưa vào comment, metadata nào ở nơi khác?

Một dấu hiệu của thiết kế tốt là không cố nhét mọi thông tin vào comment.

| Thông tin | Nơi lưu khuyến nghị | Lý do |
|---|---|---|
| Mục tiêu thay đổi, bối cảnh nghiệp vụ | comment trong changeset | Theo cùng định nghĩa migration |
| Định danh thay đổi | id, author, filename | Liquibase dùng nhận diện và lịch sử |
| Giới hạn DBMS hoặc môi trường | dbms, context/label | Có thể tham gia lựa chọn changeset |
| Điều kiện tiền đề | preConditions | Được Liquibase kiểm tra khi chạy |
| SQL hoặc thay đổi schema | changes | Được thực thi |
| Phương án hoàn tác | rollback | Được công cụ sử dụng khi rollback |
| Phân tích nghiệp vụ dài hoặc thiết kế chi tiết | RFC/issue/PR | Có phiên bản, review, thảo luận |
| Ai phê duyệt và khi nào | Pull request/release workflow | Cần bằng chứng ngoài changelog |
| Git SHA và artifact chính xác | Build/release record | Gắn với lần build cụ thể |
| Log chạy migration và kết quả kiểm thử | CI/CD và hệ thống quan sát | Có thể có nhiều lần chạy, nhiều môi trường |
| Schema thực tế sau triển khai | Database và công cụ kiểm tra cấu trúc | Lịch sử Liquibase không tự mô tả mọi thay đổi ngoài công cụ |

Tài liệu và metadata nên bổ sung nhau. Comment càng dài chưa chắc càng tốt: nếu lặp lại toàn bộ RFC, nó dễ lỗi thời. Một comment gọn, ghi đúng “vì sao” và tham chiếu mã công việc ổn định thường hữu ích hơn.

## 18. Sai lầm thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Có comment trong YAML nhưng COMMENTS trống | Chỉ viết ghi chú với dấu #, không dùng trường comment của changeset | Kiểm tra cú pháp comment metadata, validate và thử trên database test |
| Comment đúng nhưng không thấy thay đổi schema | Changeset đã chạy, bị lọc, chưa được include hoặc precondition ảnh hưởng | Xem status, master changelog, context/label và schema thực tế |
| Người vận hành cho rằng AUTHOR là người deploy | Nhầm tác giả changeset với tài khoản CI/CD | Tra log pipeline và approval để tìm chủ thể triển khai |
| Changeset cũ bị xem là mới | Đổi id, author hoặc đường dẫn changelog | Đối chiếu DATABASECHANGELOG, xử lý định danh logic có kiểm chứng |
| Database ghi comment cũ dù Git đã sửa | Changeset đã chạy trước khi comment thay đổi | Không sửa bảng lịch sử tùy tiện; ghi bổ sung trong release record/issue |
| Checksum mismatch sau khi sửa file | Nội dung changeset đã triển khai thay đổi | So sánh revision, tạo changeset mới cho thay đổi thực tế |
| Context được ghi nhưng fixture vẫn chạy production | Không truyền filter đúng hoặc hiểu sai semantics context | Dùng cơ chế lọc rõ ràng, kiểm tra status/updateSQL trên cấu hình production |
| Không xác định được commit đã triển khai | Chỉ dựa vào DATABASECHANGELOG, không lưu release metadata | Gắn commit/artifact/job vào release record |
| Comment mô tả rollback an toàn nhưng dữ liệu bị mất | Comment không phản ánh tác động thực tế của rollback | Kiểm tra rollback trên dữ liệu đại diện và cập nhật kế hoạch khôi phục |
| DATABASECHANGELOG báo đã chạy nhưng schema lệch | Có sửa database ngoài Liquibase hoặc migration thực tế khác mong đợi | Dùng snapshot/diff/kiểm tra DDL, điều tra drift và sửa bằng migration có kiểm soát |

Khi xử lý những lỗi này, ưu tiên xác định đúng database đích, phiên bản Liquibase và revision changelog. Không sửa trực tiếp DATABASECHANGELOG để “làm đẹp” báo cáo nếu chưa đánh giá hậu quả tới định danh và lịch sử.

## 19. Bài thực hành: thiết lập truy vết cho một migration

Giả sử hệ thống cần thêm bảng lưu lịch sử thay đổi trạng thái đơn hàng. Công việc được theo dõi bằng mã **ORDER-319**.

**Bước 1 — Xác định metadata:** chọn id ổn định, author là nhóm sở hữu changeset, comment nêu mục đích audit trạng thái và lưu ý về dung lượng dữ liệu. Tệp có thể đặt trong thư mục migration của cùng revision.

**Bước 2 — Viết changeset:**

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-07-create-order-status-history
      author: order-team
      comment: >-
        ORDER-319: Lưu lịch sử chuyển trạng thái đơn hàng để phục vụ
        điều tra nghiệp vụ và đối soát. Cần đánh giá tăng trưởng dữ liệu
        và chính sách lưu trữ trước khi phát hành production.
      changes:
        - createTable:
            tableName: order_status_history
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: order_id
                  type: bigint
                  constraints:
                    nullable: false
              - column:
                  name: status
                  type: varchar(30)
                  constraints:
                    nullable: false
              - column:
                  name: changed_at
                  type: timestamp
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            tableName: order_status_history
~~~

Đây là ví dụ schema cơ bản; khóa ngoại, index, generation strategy cho id, múi giờ, retention policy và yêu cầu hiệu năng cần được bổ sung theo DBMS và nghiệp vụ thực tế. Rollback bằng dropTable sẽ mất dữ liệu lịch sử nếu bảng đã nhận bản ghi; phải cân nhắc riêng trước khi triển khai.

**Bước 3 — Liên kết với nguồn gốc:** trong PR, ghi mã ORDER-319 và mô tả cách ứng dụng ghi dữ liệu vào bảng. Reviewer kiểm tra tên bảng/cột, quyền, index, khả năng backfill nếu cần, rollback và comment. Tên ticket giúp tìm được quyết định thiết kế mà không làm changeset quá dài.

**Bước 4 — Kiểm thử:** chạy validate, status, sinh SQL dự kiến rồi chạy update trên database test. Xác minh bảng order_status_history và bản ghi tương ứng trong DATABASECHANGELOG.

**Bước 5 — Đối chiếu lịch sử:** dùng câu truy vấn có điều kiện nhận diện changeset:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    DATEEXECUTED,
    EXECTYPE,
    MD5SUM,
    COMMENTS,
    DEPLOYMENT_ID
FROM DATABASECHANGELOG
WHERE ID = '20261119-07-create-order-status-history'
  AND AUTHOR = 'order-team';
~~~

Không bỏ qua FILENAME khi đối chiếu vì id + author chưa phải toàn bộ định danh. Có thể có nhiều database hoặc changelog có cùng id/author với đường dẫn khác nhau. Trong tình huống cần xác thực chính xác, đối chiếu cả FILENAME với đường dẫn hiệu lực mà Liquibase đã dùng.

**Bước 6 — Bàn giao phát hành:** ghi lại Git SHA, artifact, môi trường, pipeline job và kết quả kiểm tra. Dùng cùng revision đã kiểm tra để triển khai staging rồi production. Xác nhận lịch sử riêng trong mỗi database sau update.

**Bước 7 — Thử tình huống điều tra:** giả sử hai tháng sau có lỗi cập nhật trạng thái. Từ bảng order_status_history, xác định thời điểm phát sinh dữ liệu; từ DATABASECHANGELOG, xác định changeset tạo bảng và comment ORDER-319; từ PR và release record, xác định thiết kế, phiên bản ứng dụng và đợt triển khai liên quan.

Thông qua quy trình này, comment phục vụ **giải thích mục đích**, metadata phục vụ **nhận diện**, DATABASECHANGELOG phục vụ **đối chiếu trạng thái triển khai**, và hệ thống phát hành phục vụ **truy vết quyết định cùng lần triển khai**.

## 20. Checklist trước khi merge và triển khai

- [ ] Changeset có id, author và đường dẫn changelog ổn định.
- [ ] Comment giải thích vì sao cần thay đổi, không chỉ lặp lại tên change type.
- [ ] Comment có mã công việc hoặc tham chiếu thiết kế phù hợp.
- [ ] Comment không chứa credentials, dữ liệu cá nhân hoặc thông tin nhạy cảm.
- [ ] Các precondition, rollback và hạn chế DBMS/môi trường được khai báo bằng thuộc tính có thể kiểm tra.
- [ ] Context/label đã được kiểm tra cùng filter và cấu hình CI/CD thực tế.
- [ ] Không chỉnh sửa tùy tiện changeset đã được triển khai.
- [ ] Không di chuyển file cũ khi chưa có kế hoạch bảo toàn FILENAME/logicalFilePath.
- [ ] Changelog đã được validate; SQL dự kiến đã được review.
- [ ] Migration được thử trên database mới và database có dữ liệu đại diện.
- [ ] Bảng DATABASECHANGELOG và schema thực tế được đối chiếu sau update.
- [ ] Git SHA, artifact, job triển khai và môi trường được lưu trong release record.
- [ ] Reviewer hiểu cách rollback hoặc forward fix nếu migration có vấn đề.
- [ ] Các bản ghi lịch sử và comment có thể được truy vết lại đúng PR/issue.
- [ ] Không coi AUTHOR, COMMENTS hoặc DEPLOYMENT_ID là bằng chứng đầy đủ về người phê duyệt hoặc toàn bộ quá trình deploy.

**Ghi nhớ:** comment trong changeset giữ lại **lý do và bối cảnh**; id, author và đường dẫn changelog xác lập **định danh**; các thuộc tính điều kiện mô tả **khi nào Liquibase được phép xét chạy**; DATABASECHANGELOG ghi nhận **trạng thái thực thi của từng database**. Kết hợp các dữ liệu đó với Git và CI/CD mới tạo ra chuỗi truy vết đáng tin cậy cho thay đổi schema và dữ liệu trong suốt vòng đời ứng dụng.

