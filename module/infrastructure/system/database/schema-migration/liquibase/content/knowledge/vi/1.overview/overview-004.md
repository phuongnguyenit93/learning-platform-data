# Các khái niệm changelog, changeset, change type và trạng thái thực thi

## 1. Bối cảnh và mục tiêu

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase được dùng để quản lý thay đổi schema và dữ liệu theo lịch sử có thể kiểm tra, tái chạy có kiểm soát và triển khai nhất quán giữa các môi trường. Module hướng tới việc nắm changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp với Spring Boot hoặc CI/CD.

Ở chương **Tổng quan**, bài này làm rõ bốn khái niệm nền tảng: changelog là nơi khai báo lịch sử thay đổi; changeset là đơn vị Liquibase nhận diện và thực thi; change type mô tả thao tác cần thực hiện; trạng thái thực thi cho biết thay đổi đã được áp dụng, chạy lại hay được đánh dấu hoàn tất như thế nào.

## 2. Changelog: bản mô tả có thứ tự của các thay đổi

**Changelog** là một tệp hoặc tập hợp tệp mô tả những thay đổi cần đưa vào cơ sở dữ liệu. Changelog có thể được viết bằng XML, YAML, JSON hoặc SQL đã định dạng theo quy ước Liquibase. Mỗi định dạng đều biểu diễn được danh sách changeset; lựa chọn định dạng nên thống nhất trong một dự án để dễ đọc, review và tự động kiểm tra.

Một dự án thường có changelog gốc, hay master changelog, làm điểm vào cho Liquibase. Tệp này có thể khai báo changeset trực tiếp hoặc nạp các tệp con bằng include/includeAll. Ví dụ cấu trúc:

~~~text
src/main/resources/
└── db/
    └── changelog/
        ├── db.changelog-master.yaml
        ├── release-2026-11/
        │   ├── 001-create-customer.yaml
        │   └── 002-add-customer-status.yaml
        └── release-2026-12/
            └── 001-create-order.yaml
~~~

Master changelog có thể nạp các tệp theo thứ tự đã định:

~~~yaml
databaseChangeLog:
  - include:
      file: release-2026-11/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: release-2026-11/002-add-customer-status.yaml
      relativeToChangelogFile: true
  - include:
      file: release-2026-12/001-create-order.yaml
      relativeToChangelogFile: true
~~~

Thứ tự nạp changelog là một phần của kế hoạch triển khai. Nếu một changeset tạo bảng được tham chiếu bởi changeset tạo khóa ngoại, thay đổi tạo bảng phải được nạp trước. Vì vậy, cần giữ thứ tự include ổn định, đặt tên tệp dễ hiểu và tránh sắp xếp lại lịch sử đã phát hành một cách tùy tiện. includeAll hữu ích khi thư mục có quy ước đặt tên rõ ràng; include tường minh phù hợp khi muốn review chính xác thứ tự từng tệp.

Changelog là bản khai báo mong muốn. Nó không phải bản sao trực tiếp của schema hiện tại trong cơ sở dữ liệu. Liquibase so sánh các changeset được khai báo với lịch sử đã lưu trong cơ sở dữ liệu để xác định phần công việc còn cần thực hiện.

## 3. Changeset: đơn vị nhận diện và thực thi

**Changeset** là đơn vị thay đổi mà Liquibase theo dõi riêng. Trong các định dạng changelog có cấu trúc, changeset thường có ba thành phần nhận diện quan trọng:

- **id**: mã định danh do nhóm phát triển đặt, thường gắn với mục đích hoặc thứ tự thay đổi.
- **author**: người hoặc nhóm chịu trách nhiệm khai báo changeset.
- **đường dẫn changelog**: vị trí logic của tệp chứa changeset; nếu cấu hình logicalFilePath thì giá trị đường dẫn logic đó được dùng để giữ định danh ổn định.

Bộ ba id, author và đường dẫn tệp tạo thành định danh để Liquibase đối chiếu changeset với lịch sử đã triển khai. Hai changeset có cùng id nhưng khác author hoặc khác đường dẫn logic vẫn có thể bị xem là hai changeset khác nhau. Do đó, id nên duy nhất trong phạm vi một tác giả và tệp, có quy ước dễ truy vết; author nên ổn định; đường dẫn tệp cần được quản lý cẩn thận khi di chuyển hoặc đổi tên changelog.

Một changeset có thể chứa một hoặc nhiều change type. Chúng được thực hiện theo thứ tự khai báo trong changeset. Ví dụ dưới đây tạo bảng customer và bổ sung cột status trong một changeset tiếp theo:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-01-001
      author: platform-team
      comment: Tạo bảng khách hàng
      preConditions:
        - onFail: HALT
        - not:
            - tableExists:
                tableName: customer
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: BIGINT
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: VARCHAR(255)
                  constraints:
                    nullable: false
                    unique: true
      rollback:
        - dropTable:
            tableName: customer

  - changeSet:
      id: 2026-11-01-002
      author: platform-team
      comment: Bổ sung trạng thái khách hàng
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: status
                  type: VARCHAR(20)
                  defaultValue: ACTIVE
                  constraints:
                    nullable: false
        - createIndex:
            tableName: customer
            indexName: idx_customer_status
            columns:
              - column:
                  name: status
      rollback:
        - dropIndex:
            tableName: customer
            indexName: idx_customer_status
        - dropColumn:
            tableName: customer
            columnName: status
~~~

Trong ví dụ, changeset đầu tiên kiểm tra bảng customer chưa tồn tại rồi mới tạo bảng. Nếu điều kiện không đạt, onFail: HALT yêu cầu Liquibase dừng để người vận hành xử lý trạng thái cơ sở dữ liệu. Changeset thứ hai thêm cột và tạo index; rollback khai báo thứ tự đảo ngược phù hợp: xóa index trước rồi mới xóa cột mà index phụ thuộc.

Khi changeset đã triển khai ở một môi trường dùng chung, hãy xem nội dung của nó như một phần lịch sử bất biến. Nếu cần sửa cấu trúc hoặc dữ liệu, tạo changeset mới để bổ sung hoặc điều chỉnh. Sửa changeset đã chạy có thể làm checksum thay đổi, gây lỗi xác thực hoặc khiến các môi trường có lịch sử khác nhau. Nếu phải di chuyển tệp, cần xem xét logicalFilePath để Liquibase tiếp tục nhận diện changeset theo đường dẫn logic cũ.

## 4. Change type: mô tả thao tác trên cơ sở dữ liệu

**Change type** là loại thao tác mà một changeset yêu cầu Liquibase thực hiện. Trong YAML, các change type nằm trong danh sách changes. Liquibase dùng mô tả này để tạo câu lệnh phù hợp với hệ quản trị cơ sở dữ liệu đang kết nối.

Một số change type thường gặp:

| Nhóm thao tác | Change type tiêu biểu | Mục đích |
|---|---|---|
| Bảng và cột | createTable, dropTable, addColumn, renameColumn, modifyDataType | Tạo, xóa hoặc điều chỉnh cấu trúc bảng |
| Ràng buộc | addPrimaryKey, addForeignKeyConstraint, addUniqueConstraint, addNotNullConstraint | Bảo vệ tính toàn vẹn dữ liệu |
| Chỉ mục | createIndex, dropIndex | Tạo hoặc xóa chỉ mục |
| Dữ liệu | insert, update, delete, loadData | Thêm, cập nhật, xóa hoặc nạp dữ liệu |
| Câu lệnh tùy chỉnh | sql, sqlFile | Chạy SQL khi change type có sẵn không diễn tả đủ yêu cầu |
| Đối tượng khác | createView, createSequence, createProcedure | Quản lý view, sequence và thủ tục lưu trữ |

Ưu tiên change type có cấu trúc khi nó biểu diễn đầy đủ yêu cầu. Cách này giúp Liquibase tạo SQL theo từng hệ quản trị và làm changelog dễ đọc hơn. Với SQL tùy chỉnh, cú pháp có thể phụ thuộc nhà cung cấp cơ sở dữ liệu; cần ghi rõ phạm vi DBMS, delimiter hoặc cách tách câu lệnh nếu cần, đồng thời kiểm tra SQL sinh ra trên đúng loại cơ sở dữ liệu mục tiêu.

Không phải change type nào cũng được mọi hệ quản trị hỗ trợ giống nhau. Một thay đổi có thể cần cách triển khai riêng cho PostgreSQL, MySQL, Oracle hoặc SQL Server. Có thể dùng thuộc tính dbms hoặc các changelog phù hợp theo môi trường để giới hạn nơi chạy. Khi dùng SQL riêng cho một hệ quản trị, cần ghi rõ lý do và kiểm tra khả năng rollback.

### Rollback gắn với change type

Rollback mô tả cách hoàn tác một changeset khi cần quay lui triển khai. Một số change type có thể được Liquibase tạo rollback tự động; với SQL tùy chỉnh hoặc thao tác không thể suy ra chiều ngược, cần khai báo rollback tường minh. Rollback phải phản ánh tác động thực tế và được kiểm tra trên dữ liệu mẫu trước khi dùng ở môi trường quan trọng.

Không phải mọi thay đổi đều có thể đảo ngược mà không mất dữ liệu. Ví dụ dropTable hoặc dropColumn có thể làm mất dữ liệu; rollback tạo lại bảng hoặc cột không khôi phục được dữ liệu đã bị xóa nếu không có bản sao. Với thay đổi dữ liệu, cần thiết kế cách phục hồi dữ liệu cũ hoặc chọn chiến lược tiến về phía trước (forward fix) khi rollback không an toàn.

## 5. Các điều khiển ảnh hưởng đến việc thực thi changeset

Ngoài change type, changeset có thể có các thuộc tính điều khiển thời điểm và điều kiện chạy:

- **preConditions** kiểm tra trạng thái cơ sở dữ liệu trước khi thực thi, chẳng hạn bảng, cột hoặc dữ liệu đã tồn tại hay chưa. Có thể đặt precondition ở cấp changelog hoặc changeset.
- **onFail** quyết định hành vi khi điều kiện không đạt. HALT dừng triển khai; WARN ghi cảnh báo rồi tiếp tục; CONTINUE bỏ qua changeset trong lần chạy đó; MARK_RAN ghi nhận changeset như đã chạy dù các thay đổi trong nó không được thực thi. **onError** điều khiển tình huống đánh giá precondition gặp lỗi.
- **context** và **labels** lọc changeset theo mục đích hoặc nhóm triển khai, ví dụ dữ liệu mẫu chỉ dành cho môi trường kiểm thử. Đây là bộ lọc triển khai, không thay đổi định danh changeset.
- **dbms** giới hạn hệ quản trị cơ sở dữ liệu được phép chạy changeset.
- **runOnChange** cho phép chạy lại changeset khi nội dung làm checksum thay đổi; thường hữu ích với định nghĩa view hoặc procedure cần cập nhật theo phiên bản.
- **runAlways** yêu cầu changeset chạy trong mỗi lần Liquibase xử lý update, phù hợp với một số thao tác cần lặp lại có chủ đích. Chỉ dùng khi thao tác an toàn khi chạy nhiều lần.
- **runInTransaction** mặc định là true trong các trường hợp thông thường, để Liquibase thực thi changeset trong giao dịch nếu cơ sở dữ liệu hỗ trợ. Chỉ đặt false khi câu lệnh hoặc hệ quản trị yêu cầu chạy ngoài transaction; cần cân nhắc khả năng changeset bị thực hiện một phần nếu lỗi giữa chừng.

Precondition cần mô tả đúng trạng thái mong đợi. Ví dụ, điều kiện tableExists chỉ cho biết bảng tồn tại, không chứng minh bảng có đúng cột, kiểu dữ liệu, index hoặc constraint. Nếu một bảng đã được tạo thủ công nhưng cấu trúc sai, dùng MARK_RAN có thể che giấu sai lệch. Hãy kiểm tra đủ các thuộc tính cần thiết hoặc dừng để xử lý drift trước khi tiếp tục.

## 6. Checksum và lịch sử triển khai

Liquibase tính checksum cho changeset và lưu giá trị đó trong bảng lịch sử. Checksum giúp phát hiện changeset đã triển khai bị sửa nội dung. Khi Liquibase gặp changeset có cùng định danh nhưng checksum khác với lịch sử đã lưu, quá trình validate/update có thể báo lỗi để ngăn lịch sử triển khai âm thầm thay đổi.

Các nguyên tắc quan trọng:

1. Không chỉnh sửa changeset đã chạy trên môi trường dùng chung; tạo changeset mới để sửa hoặc bổ sung.
2. Không xóa hoặc đổi id, author hay đường dẫn logic của changeset đã phát hành nếu chưa đánh giá tác động tới định danh.
3. Chỉ dùng validCheckSum khi có lý do rõ ràng và đã review giá trị checksum được chấp nhận.
4. clear-checksums là thao tác quản trị để yêu cầu Liquibase tính lại checksum ở lần chạy tiếp theo; không dùng nó như cách mặc định để bỏ qua lỗi do sửa lịch sử.

Liquibase lưu lịch sử trong bảng **DATABASECHANGELOG** do Liquibase quản lý. Bảng này thường chứa id, author, filename, ngày thực thi, thứ tự thực thi, loại thực thi, checksum, mô tả và phiên bản Liquibase. Tên cột cụ thể có thể khác theo phiên bản, nhưng ý nghĩa chính là liên kết từng changeset với lần triển khai đã ghi nhận.

Bảng **DATABASECHANGELOGLOCK** hỗ trợ khóa triển khai để tránh nhiều tiến trình Liquibase cùng cập nhật một cơ sở dữ liệu tại một thời điểm. Nếu một lần chạy bị ngắt bất thường, cần kiểm tra tiến trình còn hoạt động và trạng thái khóa trước khi giải phóng khóa; không xóa khóa chỉ để làm lệnh update chạy tiếp khi chưa xác định nguyên nhân.

## 7. Đọc trạng thái thực thi

Trạng thái của changeset được hiểu bằng cách đối chiếu changelog với DATABASECHANGELOG:

| Trạng thái quan sát | Ý nghĩa | Cách xử lý |
|---|---|---|
| Pending / chưa triển khai | Có trong changelog nhưng chưa có bản ghi tương ứng trong DATABASECHANGELOG, hoặc chưa được chạy do bộ lọc hiện tại | Kiểm tra thứ tự, context, label, dbms và SQL dự kiến trước khi update |
| EXECUTED | Changeset đã thực thi thành công và được ghi vào lịch sử | Giữ nguyên changeset; dùng changeset mới cho thay đổi tiếp theo |
| RERAN | Changeset được chạy lại, thường do runOnChange hoặc runAlways | Xác minh việc chạy lặp là có chủ đích và an toàn |
| MARK_RAN | Liquibase ghi nhận changeset như đã chạy nhưng không thực hiện các change bên trong theo nhánh xử lý tương ứng | Kiểm tra schema thực tế; không mặc định xem đây là bằng chứng SQL đã được áp dụng |
| Bị bỏ qua trong lần chạy | Changeset không chạy do context/label/dbms hoặc chính sách precondition như CONTINUE | Kiểm tra bộ lọc và điều kiện; changeset có thể còn cần chạy ở lần triển khai khác |
| Thất bại | Câu lệnh hoặc bước kiểm tra gặp lỗi; update có thể dừng tại changeset đó | Đọc lỗi, kiểm tra transaction và schema thực tế, sau đó xử lý có kiểm soát trước khi chạy lại |

Pending là trạng thái được suy ra khi so sánh changelog với lịch sử, không phải một giá trị EXECTYPE được ghi cho changeset chưa chạy. Trong DATABASECHANGELOG, EXECTYPE thường cho biết cách changeset được ghi nhận, chẳng hạn EXECUTED, RERAN hoặc MARK_RAN. Một changeset bị bỏ qua do bộ lọc không đồng nghĩa với changeset đã được thực thi. Khi update thất bại, cần kiểm tra cả log lẫn trạng thái thực tế của cơ sở dữ liệu; không giả định mọi câu lệnh trong changeset đều đã được hoàn tác nếu thao tác không hỗ trợ transaction.

Có thể dùng các lệnh sau để kiểm tra theo từng bước:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
liquibase update
liquibase history
~~~

validate kiểm tra changelog và các vấn đề cấu trúc có thể phát hiện trước khi triển khai. status cho biết changeset nào còn chờ. update-sql hiển thị SQL dự kiến để review. update thực thi các thay đổi còn thiếu. history hỗ trợ xem lịch sử triển khai. Tùy phiên bản Liquibase và cách đóng gói, cách truyền URL, credentials, context hoặc label có thể khác; không đưa thông tin bí mật vào dòng lệnh hoặc changelog được commit.

## 8. Quy trình áp dụng trong Spring Boot và CI/CD

Trong ứng dụng Spring Boot, Liquibase thường được cấu hình để chạy khi ứng dụng khởi động. Ví dụ cấu hình changelog:

~~~yaml
spring:
  liquibase:
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    enabled: true
~~~

Ứng dụng cần dependency Liquibase và JDBC driver phù hợp. Cấu hình kết nối phải trỏ đúng cơ sở dữ liệu; credentials nên lấy từ secret hoặc biến môi trường. Nếu CI/CD chịu trách nhiệm triển khai migration, nhóm cần thống nhất rõ tiến trình nào chạy Liquibase để tránh nhiều instance ứng dụng cùng khởi chạy migration ngoài dự kiến.

Một luồng triển khai có kiểm soát thường gồm:

1. Người phát triển tạo changeset mới, mô tả thay đổi bằng change type phù hợp và bổ sung rollback hoặc ghi rõ giới hạn rollback.
2. Pull request review thứ tự changelog, định danh changeset, precondition, tính tương thích DBMS và tác động lên dữ liệu.
3. Pipeline chạy validate, kiểm tra trạng thái và tạo SQL dự kiến; reviewer kiểm tra SQL trên đúng phiên bản hệ quản trị.
4. Pipeline áp dụng migration vào môi trường đích bằng context/label và cấu hình kết nối tương ứng.
5. Sau triển khai, kiểm tra DATABASECHANGELOG, log ứng dụng, schema và các truy vấn nghiệp vụ liên quan.
6. Khi có sự cố, đánh giá changeset đã chạy tới đâu, khả năng rollback và dữ liệu bị ảnh hưởng; chọn rollback đã kiểm chứng hoặc tạo changeset tiến về phía trước.

Giữa các môi trường, cùng một changelog nên tạo ra cùng một lịch sử logic. Khác biệt cấu hình như URL, tài khoản, context, label và thông tin secret được truyền từ cấu hình triển khai. Không sửa trực tiếp changeset theo từng môi trường vì điều đó làm checksum và lịch sử phân kỳ. Nếu một môi trường có schema được tạo ngoài Liquibase, cần đối chiếu thực tế và xử lý sai lệch trước khi đồng bộ lịch sử.

## 9. Lỗi thường gặp và cách phòng tránh

- **Trùng hoặc đổi định danh changeset:** Liquibase có thể coi thay đổi là một changeset mới hoặc không khớp lịch sử. Dùng quy ước id/author và giữ đường dẫn logic ổn định.
- **Sửa changeset đã triển khai:** checksum không khớp. Tạo changeset mới; chỉ dùng cơ chế checksum ngoại lệ khi có quyết định được review.
- **Sai thứ tự phụ thuộc:** thay đổi khóa ngoại hoặc index chạy trước khi bảng/cột tồn tại. Sắp xếp include và changeset theo quan hệ phụ thuộc.
- **Precondition quá rộng:** điều kiện chỉ kiểm tra sự tồn tại nhưng bỏ qua cấu trúc. Kiểm tra đủ trạng thái cần thiết; chọn HALT khi không thể tự động kết luận an toàn.
- **Dùng MARK_RAN tùy tiện:** lịch sử ghi nhận đã chạy trong khi SQL chưa áp dụng. Chỉ dùng sau khi đã xác minh schema thực tế tương đương với kết quả mong đợi.
- **Rollback làm mất dữ liệu:** rollback DDL không khôi phục dữ liệu đã xóa. Thiết kế bản sao lưu, cách phục hồi hoặc forward fix trước khi triển khai.
- **Chạy đồng thời nhiều tiến trình:** có thể gặp khóa Liquibase hoặc xung đột triển khai. Bảo đảm một đầu mối migration tại một thời điểm và xử lý lock theo quy trình.
- **Khác biệt hệ quản trị:** SQL tùy chỉnh chạy được ở máy phát triển nhưng lỗi ở môi trường đích. Kiểm tra bằng đúng DBMS và phiên bản tương ứng.

## 10. Ghi nhớ

Changelog tổ chức lịch sử thay đổi; changeset là đơn vị có định danh ổn định; change type diễn tả thao tác; precondition và các bộ lọc quyết định thay đổi có đủ điều kiện chạy hay không; checksum phát hiện nội dung lịch sử bị sửa; DATABASECHANGELOG lưu dấu triển khai. Khi hiểu rõ mối quan hệ này, người phát triển có thể dự đoán Liquibase sẽ chọn changeset nào, vì sao một changeset được chạy hoặc bỏ qua, và cần kiểm tra gì trước khi triển khai hoặc rollback.

Một migration tốt cần có mục đích rõ ràng, thứ tự phụ thuộc hợp lý, điều kiện chạy phù hợp, SQL có thể review, chiến lược rollback được kiểm chứng và lịch sử changeset nhất quán giữa các môi trường.
