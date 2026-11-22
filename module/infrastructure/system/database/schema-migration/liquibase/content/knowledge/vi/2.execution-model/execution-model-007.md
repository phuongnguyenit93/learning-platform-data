# Phân biệt trạng thái triển khai với cấu trúc cơ sở dữ liệu thực tế

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase quản lý thay đổi schema và dữ liệu thông qua changelog, changeset, precondition, checksum và lịch sử triển khai. Khi vận hành, cần phân biệt hai câu hỏi: **Liquibase ghi nhận những changeset nào đã được triển khai?** và **cơ sở dữ liệu hiện tại thực sự có những đối tượng, cấu trúc và dữ liệu nào?** Hai câu trả lời thường trùng nhau sau một lần triển khai thành công, nhưng chúng được tạo ra và kiểm chứng theo những cơ chế khác nhau.

Sự phân biệt này giúp tránh kết luận sai từ lệnh status, xử lý đúng khi có thay đổi thủ công, phục hồi sau migration lỗi giữa chừng và giữ cho các môi trường phát triển, kiểm thử, staging và production nhất quán.

## 1. Bốn lớp thông tin cần quan sát

Có thể xem trạng thái migration qua bốn lớp độc lập:

| Lớp | Nguồn thông tin | Câu hỏi trả lời | Điều không thể tự chứng minh |
|---|---|---|---|
| Trạng thái mong muốn | Changelog trong source control | Nhóm dự định thay đổi điều gì? | Thay đổi đã chạy trên database hay chưa |
| Lịch sử thực thi | Bảng **DATABASECHANGELOG** | Liquibase ghi nhận changeset nào đã chạy hoặc được đánh dấu là đã chạy? | Schema hiện tại còn giống kết quả của changeset hay không |
| Cấu trúc thực tế | Catalog/metadata của database | Bảng, cột, khóa, index, view, sequence… hiện đang tồn tại ra sao? | Những thay đổi đó được tạo bởi Liquibase, DBA hay ứng dụng |
| Trạng thái vận hành | Log, quyền, kết nối, cấu hình ứng dụng và dữ liệu | Ứng dụng có thể sử dụng database theo cách dự kiến hay không? | Chỉ dựa vào lịch sử migration có thể xác nhận ứng dụng hoạt động đúng |

### 1.1. Changelog mô tả trạng thái mong muốn

Changelog là tập hợp các changeset được quản lý cùng mã nguồn. Mỗi changeset mô tả một thay đổi có định danh, tác giả và nội dung cụ thể, chẳng hạn thêm cột, tạo index, thay đổi constraint hoặc chuyển đổi dữ liệu.

Ví dụ một changeset trong SQL formatted changelog:

~~~sql
--liquibase formatted sql
--changeset team-database:2026-11-19-01-add-orders-status
ALTER TABLE orders ADD COLUMN status VARCHAR(20) DEFAULT 'PENDING';
--rollback ALTER TABLE orders DROP COLUMN status;
~~~

Đoạn changelog thể hiện ý định thêm cột **status**. Nó không chứng minh cột đã được tạo trên mọi database. Một môi trường có thể chưa chạy changeset, bị loại khỏi lần triển khai do context hoặc label, hoặc gặp lỗi khi thực thi.

### 1.2. DATABASECHANGELOG là sổ ghi nhận thực thi

Liquibase sử dụng bảng **DATABASECHANGELOG** để lưu lịch sử changeset trên từng database. Bảng này thường có các thông tin như:

- **ID**, **AUTHOR**, **FILENAME**: định danh changeset mà Liquibase dùng để nhận diện.
- **DATEEXECUTED**, **ORDEREXECUTED**: thời điểm và thứ tự ghi nhận.
- **EXECTYPE**: kiểu thực thi được ghi nhận, ví dụ **EXECUTED**, **RERAN** hoặc **MARK_RAN**.
- **MD5SUM**: checksum của changeset tại thời điểm được ghi nhận.
- **DEPLOYMENT_ID**: mã đợt triển khai trong các phiên bản Liquibase hỗ trợ trường này.

Liquibase đối chiếu định danh changeset trong changelog với các bản ghi trong bảng này để xác định changeset nào còn pending. Vì vậy, **DATABASECHANGELOG** là lịch sử do Liquibase quản lý, không phải bản chụp đầy đủ của schema.

Nếu một dòng ghi nhận changeset thêm cột **orders.status**, dòng đó cho biết Liquibase đã ghi nhận lần thực thi tương ứng. Nó không liên tục truy vấn catalog để bảo đảm cột vẫn còn tồn tại sau nhiều tháng vận hành.

Bảng **DATABASECHANGELOGLOCK** có vai trò khác: quản lý khóa để ngăn nhiều tiến trình Liquibase cùng thực hiện cập nhật trên một database tại cùng thời điểm. Bản ghi khóa không phải bằng chứng rằng schema đã đúng hoặc migration đã hoàn tất.

### 1.3. Schema thực tế nằm trong database

Cấu trúc thực tế được lưu trong catalog và metadata của hệ quản trị cơ sở dữ liệu. Khi cần xác minh, phải quan sát database đích: bảng và cột, kiểu dữ liệu, nullability, default, khóa chính, khóa ngoại, constraint, index, view, sequence, trigger và các đối tượng liên quan.

Cấu trúc thực tế có thể thay đổi sau lần migration gần nhất do DBA sửa trực tiếp, script ngoài Liquibase, thao tác thủ công, restore backup, triển khai ứng dụng khác hoặc một migration thất bại sau khi đã thực hiện một phần DDL.

Dữ liệu cũng có thể thay đổi sau migration. Một changeset chuyển đổi dữ liệu có thể đã chạy thành công, nhưng các bản ghi tiếp tục được ứng dụng cập nhật. Vì thế, lịch sử migration không phải ảnh chụp dữ liệu hiện tại.

## 2. Liquibase xác định changeset đã triển khai như thế nào?

Với mỗi changeset, Liquibase dựa vào bộ định danh gồm **id**, **author** và đường dẫn changelog (**filename**, có thể được kiểm soát bằng **logicalFilePath**). Khi chạy **update**, Liquibase đọc changelog, tra lịch sử trong **DATABASECHANGELOG**, áp dụng các bộ lọc thích hợp rồi thực thi những changeset đủ điều kiện và chưa được ghi nhận.

Một số yếu tố ảnh hưởng đến quyết định thực thi:

- **Định danh và đường dẫn:** đổi vị trí file có thể làm thay đổi cách Liquibase nhận diện changeset nếu không duy trì đường dẫn logic ổn định. Cần quản lý việc di chuyển changelog có chủ đích.
- **Checksum:** Liquibase tính checksum để phát hiện nội dung changeset đã thay đổi so với lần ghi nhận trước. Checksum hỗ trợ kiểm soát tính nhất quán của lịch sử; nó không phải checksum của toàn bộ schema database.
- **runOnChange:** cho phép chạy lại changeset khi nội dung thay đổi theo quy tắc của Liquibase. Cách này thường phù hợp với một số đối tượng có thể thay thế như view hoặc stored procedure, sau khi đã đánh giá tác động.
- **runAlways:** yêu cầu changeset được chạy trong mỗi lần cập nhật phù hợp. Lịch sử có thể thể hiện lần chạy lại, nhưng điều đó vẫn không chứng minh mọi đối tượng trong database đang đúng.
- **Context và label:** giới hạn changeset nào được chọn trong một lần triển khai. Hai môi trường dùng cùng changelog nhưng tham số context/label khác nhau có thể có tập changeset đã chạy khác nhau.
- **DBMS và precondition:** điều kiện theo hệ quản trị, trạng thái database hoặc metadata có thể làm changeset dừng, cảnh báo, bỏ qua hay được đánh dấu đã chạy tùy cấu hình.

Điểm quan trọng: Liquibase dùng lịch sử để quyết định changeset nào cần chạy. Cơ chế đó không tương đương với việc đối chiếu toàn bộ schema thực tế ở mỗi lần **update**.

## 3. Các tình huống lịch sử và schema không khớp nhau

| Lịch sử trong DATABASECHANGELOG | Cấu trúc thực tế | Nguyên nhân có thể | Hệ quả |
|---|---|---|---|
| Changeset chưa được ghi nhận | Thay đổi chưa tồn tại | Chưa triển khai hoặc bị lọc bởi context/label | status có thể liệt kê changeset pending |
| Changeset đã được ghi nhận | Đối tượng vẫn tồn tại đúng | Migration chạy bình thường | Lịch sử và schema đang nhất quán đối với thay đổi đó |
| Changeset đã được ghi nhận | Đối tượng đã bị sửa hoặc xóa | DBA sửa thủ công, script khác hoặc thao tác vận hành | status có thể không báo pending dù schema đã drift |
| Changeset chưa được ghi nhận | Một phần thay đổi đã xuất hiện | DDL thực hiện dở dang trước khi lỗi, hoặc thay đổi thủ công | Lần update tiếp theo có thể lỗi vì đối tượng đã tồn tại |
| Changeset có MARK_RAN | Nội dung thay đổi không được chạy bởi changeset đó | Precondition chọn MARK_RAN hoặc thao tác đồng bộ lịch sử | Lịch sử có thể được đánh dấu hoàn tất dù cần kiểm chứng riêng điều kiện schema |
| Lịch sử được sao chép nhưng schema không được sao chép tương ứng | Schema không khớp với lịch sử | Chỉ phục hồi hoặc sao chép bảng lịch sử | Liquibase có thể bỏ qua thay đổi mà database thực tế vẫn thiếu |

### Ví dụ A: lịch sử nói đã chạy nhưng cột đã bị xóa

Changeset thêm cột **orders.status** từng chạy thành công và có dòng tương ứng trong **DATABASECHANGELOG**. Sau đó, một người vận hành chạy lệnh SQL thủ công để xóa cột.

Khi chạy **liquibase status**, Liquibase có thể không liệt kê changeset thêm cột là pending vì changeset đã có trong lịch sử. **liquibase validate** cũng có thể thành công vì changelog và checksum vẫn hợp lệ. Tuy nhiên, truy vấn catalog hoặc so sánh schema sẽ phát hiện cột **status** đang thiếu.

Cách xử lý là xác minh database đích và nguyên nhân xóa cột, đánh giá ảnh hưởng đến ứng dụng và dữ liệu, sau đó tạo một migration sửa chữa có kiểm soát nếu cần. Không xóa tùy tiện dòng lịch sử để buộc Liquibase chạy lại changeset cũ: việc đó có thể làm thay đổi định danh triển khai, gây lỗi khi đối tượng khác vẫn còn hoặc tạo ra tác động lặp không an toàn.

### Ví dụ B: DDL đã chạy một phần nhưng lịch sử chưa ghi nhận

Một changeset gồm nhiều câu lệnh DDL. Câu lệnh đầu tạo bảng thành công, câu lệnh sau lỗi do thiếu quyền. Tùy hệ quản trị và ranh giới transaction, thay đổi đầu tiên có thể vẫn còn dù changeset chưa được ghi nhận hoàn tất trong **DATABASECHANGELOG**.

Ở lần chạy tiếp theo, Liquibase thấy changeset chưa có trong lịch sử và thử chạy lại. Lệnh tạo bảng có thể lỗi vì bảng đã tồn tại. Khi đó, chỉ nhìn **status** sẽ không đủ để quyết định có thể chạy lại an toàn hay không.

Cần kiểm tra log của lần chạy lỗi, trạng thái từng đối tượng trong database, transaction và khả năng rollback của hệ quản trị. Sau khi xác định chính xác phần đã được áp dụng, hãy chọn phương án khôi phục hoặc migration sửa chữa có thể kiểm chứng. Không đánh dấu changeset là đã chạy chỉ để làm cho danh sách pending biến mất.

## 4. Chọn đúng công cụ cho câu hỏi cần trả lời

Mỗi lệnh Liquibase cung cấp một loại bằng chứng khác nhau:

| Công cụ/lệnh | Bằng chứng chính | Không nên dùng để kết luận |
|---|---|---|
| **status --verbose** | Changeset còn pending theo changelog, bộ lọc và lịch sử | Schema thực tế hoàn toàn khớp changelog |
| **history** | Các changeset được ghi nhận trong lịch sử triển khai | Mọi đối tượng vẫn còn nguyên vẹn |
| **validate** | Tính hợp lệ của changelog và các kiểm tra như checksum | Database không có schema drift |
| **update-sql** | SQL Liquibase dự kiến thực thi cho các changeset được chọn | SQL chắc chắn chạy thành công hoặc đã chạy |
| **update** | Thực thi các changeset đủ điều kiện và ghi nhận lịch sử | Không còn bất kỳ thay đổi thủ công nào trong database |
| **diff** | Khác biệt giữa database tham chiếu và database đích trong phạm vi đối tượng được hỗ trợ/chọn | Hai database giống nhau về mọi dữ liệu, quyền và hành vi ứng dụng |
| **diff-changelog** | Changelog đề xuất từ khác biệt được phát hiện | Có thể triển khai ngay mà không cần review |
| **snapshot** | Ảnh chụp metadata schema tại thời điểm lấy snapshot | Lịch sử triển khai hoặc trạng thái dữ liệu đầy đủ |

### 4.1. Kiểm tra lịch sử và changeset pending

Có thể bắt đầu bằng:

~~~bash
liquibase status --verbose
liquibase history
liquibase validate
~~~

Đọc kết quả theo đúng ý nghĩa:

- **status** trả lời Liquibase còn thấy changeset nào chưa được ghi nhận là đã chạy trong phạm vi bộ lọc hiện tại.
- **history** cho biết các lần triển khai được lưu trong bảng lịch sử.
- **validate** kiểm tra changelog và các ràng buộc kiểm tra của Liquibase, bao gồm checksum trong những trường hợp áp dụng.

Ba lệnh này hữu ích để kiểm tra quy trình migration, nhưng không thay thế việc so sánh schema trên database đích.

### 4.2. Xem SQL trước khi thực thi

~~~bash
liquibase update-sql
~~~

Kết quả giúp review câu lệnh mà Liquibase dự kiến gửi đến database. Đây là bước kiểm tra quan trọng trong CI/CD, nhất là với thao tác xóa cột, đổi kiểu dữ liệu, tạo index lớn hoặc chuyển đổi dữ liệu.

SQL được sinh ra có thể khác theo DBMS, cấu hình schema, context, label và trạng thái lịch sử của database. Việc đọc SQL không xác nhận quyền thực thi, khóa, thời gian chạy hoặc kết quả thực tế.

### 4.3. So sánh cấu trúc thực tế

Khi cần trả lời database đích có giống một nguồn tham chiếu hay không, dùng **diff** với đúng reference và target đã cấu hình. Nguồn tham chiếu có thể là một database chuẩn hoặc snapshot phù hợp.

~~~bash
liquibase diff
~~~

Cần kiểm tra kỹ hướng so sánh, connection, catalog/schema, loại đối tượng và phạm vi được chọn. Nếu cần tạo đề xuất migration từ khác biệt:

~~~bash
liquibase diff-changelog
~~~

Changelog sinh tự động chỉ là đầu vào cho review. Người phụ trách phải kiểm tra thứ tự phụ thuộc, dữ liệu hiện có, khả năng tương thích, tính an toàn khi triển khai và rollback. Công cụ diff không hiểu đầy đủ ý nghĩa nghiệp vụ của mọi thay đổi.

Schema diff thường tập trung vào metadata của các đối tượng được hỗ trợ. Không mặc định rằng nó đã so sánh toàn bộ dữ liệu, quyền truy cập, cấu hình runtime, extension hoặc hành vi của ứng dụng. Với yêu cầu kiểm tra dữ liệu, cần thiết kế truy vấn đối soát, kiểm tra số lượng, khóa nghiệp vụ, checksum dữ liệu hoặc công cụ chuyên dụng tương ứng.

## 5. Những thao tác có thể làm lịch sử trông đúng nhưng che khuất sai lệch

### changelogSync

**changelogSync** ghi nhận các changeset phù hợp như đã chạy mà không thực thi nội dung thay đổi của chúng. Nó có thể hữu ích khi tiếp nhận một database cũ đã có schema tương ứng với changelog mới, sau khi đã kiểm kê và xác minh đầy đủ.

Nếu dùng trên database chưa có đúng cấu trúc, lịch sử sẽ tiến lên nhưng schema không được tạo ra. Những lần **update** tiếp theo có thể bỏ qua các changeset đã được đồng bộ. Vì vậy, chỉ dùng thao tác này trong quy trình baseline/adoption có bằng chứng đối chiếu và phê duyệt.

### Precondition với MARK_RAN

Precondition giúp kiểm tra điều kiện trước khi chạy changeset. Cấu hình **onFail: MARK_RAN** có thể yêu cầu Liquibase đánh dấu changeset là đã chạy khi điều kiện thất bại. Điều đó hữu ích trong một số quy trình tiếp nhận trạng thái có sẵn, nhưng cần bảo đảm điều kiện thất bại thực sự có nghĩa là thay đổi đã được áp dụng theo cách tương đương.

Nếu precondition chỉ kiểm tra một phần cấu trúc, hoặc điều kiện không đủ chặt, trạng thái **MARK_RAN** có thể che giấu việc database thiếu các chi tiết khác. Hãy ghi rõ lý do, kiểm tra toàn bộ hậu điều kiện và lưu bằng chứng trước khi dùng.

### clear-checksums

**clear-checksums** xóa checksum đã lưu để Liquibase tính lại trong lần cập nhật sau. Lệnh này có thể cần trong một số tình huống quản trị checksum có kiểm soát, nhưng không sửa schema, không khôi phục changeset và không giải quyết drift. Không dùng nó như cách xử lý mặc định khi checksum khác dự kiến; trước hết phải tìm nguyên nhân thay đổi changelog.

### Rollback

Rollback dùng logic rollback của changeset hoặc cơ chế rollback theo tag/date/count được cấu hình. Nó giúp đảo ngược những thay đổi mà Liquibase có thể xử lý theo định nghĩa tương ứng. Rollback không tự phát hiện và sửa mọi thay đổi thủ công, cũng không bảo đảm phục hồi dữ liệu đã mất nếu thao tác không có khả năng đảo ngược.

Trước khi rollback, phải xác minh đúng database, tag hoặc phạm vi changeset, nội dung rollback SQL, tác động đến dữ liệu và khả năng khôi phục. Với thay đổi phá hủy dữ liệu, cần có backup hoặc phương án phục hồi đã kiểm chứng.

## 6. Quy trình kiểm chứng một lần triển khai

Một quy trình triển khai có thể tổ chức theo các bước sau:

1. **Chốt đầu vào:** xác định phiên bản changelog, database đích, schema/catalog, DBMS, context, label và tài khoản kết nối. Bảo đảm pipeline dùng đúng cấu hình của môi trường.
2. **Kiểm tra lịch sử:** chạy **history** và **status --verbose**; tìm changeset pending, changeset được chạy lại hoặc được đánh dấu **MARK_RAN**, và các khác biệt giữa môi trường.
3. **Kiểm tra changelog:** chạy **validate**; review thay đổi trong source control, định danh changeset, checksum, precondition và rollback.
4. **Đối chiếu schema trước triển khai:** so sánh database đích với baseline/reference phù hợp. Điều tra drift hiện có trước khi chạy migration mới.
5. **Review SQL dự kiến:** chạy **update-sql**, kiểm tra câu lệnh DDL/DML, thứ tự phụ thuộc, thời gian khóa, dung lượng, quyền và tác động đến ứng dụng.
6. **Triển khai có kiểm soát:** chạy **update** từ một tiến trình được chỉ định. Theo dõi log, trạng thái lock và kết quả từng changeset.
7. **Kiểm tra sau triển khai:** đọc **history**, chạy các truy vấn xác minh cấu trúc và dữ liệu quan trọng, rồi đối chiếu schema với trạng thái mong muốn.
8. **Kiểm tra ứng dụng:** chạy smoke test và kiểm tra các thao tác đọc/ghi đi qua những bảng, cột, index hoặc constraint vừa thay đổi.
9. **Lưu bằng chứng:** lưu phiên bản changelog, log, kết quả kiểm tra, snapshot/diff cần thiết và quyết định xử lý sai lệch.

Không nên coi việc **update** kết thúc với mã thành công là bằng chứng duy nhất. Một lần triển khai đáng tin cậy cần có cả lịch sử thực thi, kiểm tra cấu trúc sau triển khai và kiểm tra hành vi ứng dụng ở phạm vi phù hợp.

## 7. Giữ các môi trường nhất quán

Mỗi database có bảng **DATABASECHANGELOG** riêng, phản ánh lịch sử của chính database đó. Cùng một nhánh source code không có nghĩa mọi môi trường đã thực thi cùng tập changeset: context, label, DBMS, cấu hình kết nối và thời điểm triển khai có thể khác nhau.

Để phối hợp nhiều môi trường:

- Dùng một nguồn changelog được quản lý bằng version control; phát hành cùng phiên bản changelog qua các môi trường theo thứ tự đã định.
- Duy trì cấu hình riêng cho URL, credentials, default schema, catalog, context và label; kiểm tra pipeline thực sự trỏ đến database dự kiến.
- So sánh cả lịch sử lẫn schema giữa các môi trường. Hai nơi cùng có một changeset trong **DATABASECHANGELOG** vẫn có thể khác nhau do thay đổi thủ công sau triển khai.
- Không sao chép riêng bảng **DATABASECHANGELOG** sang một database có schema khác. Khi clone/restore toàn bộ database, cần hiểu rằng cả schema, dữ liệu và lịch sử đều thuộc cùng một thời điểm snapshot.
- Chỉ dùng context/label để phân biệt phần triển khai có chủ đích; tránh tạo các nhánh changelog không thể đối chiếu hoặc khiến production bỏ qua migration cần thiết.
- Quản lý thay đổi thủ công bằng quy trình có ghi nhận. Sau thao tác khẩn cấp, phải cập nhật hồ sơ, kiểm tra drift và quyết định migration tiếp theo để đưa các môi trường về cùng trạng thái mong muốn.

Nếu một môi trường được dựng từ database có sẵn, hãy kiểm kê schema trước, xác định baseline, rồi mới cân nhắc **changelogSync**. Không lấy lịch sử của môi trường khác làm bằng chứng rằng database mới đã có cùng cấu trúc.

## 8. Tích hợp với Spring Boot và CI/CD

Spring Boot có thể tự chạy Liquibase khi ứng dụng khởi động nếu tích hợp Liquibase được bật. Cấu hình changelog và schema cần nhất quán với môi trường:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
    default-schema: app
~~~

Trong môi trường có nhiều replica, nếu mọi instance cùng khởi động và cùng yêu cầu migration, Liquibase lock hỗ trợ điều phối việc cập nhật trên một database. Tuy nhiên, nên xác định rõ một migration job hoặc một bước triển khai chịu trách nhiệm cập nhật schema để dễ kiểm soát quyền, log, thời gian và phê duyệt. Khi pipeline đã chạy migration riêng, có thể tắt Liquibase tự chạy trong các instance ứng dụng bằng cấu hình phù hợp, tránh hai cơ chế triển khai cùng chịu trách nhiệm.

Một pipeline điển hình gồm:

~~~text
Build changelog artifact
        |
        v
Validate changelog và checksum
        |
        v
Đọc history + status của database đích
        |
        v
Sinh update-sql và review
        |
        v
Phê duyệt triển khai
        |
        v
Chạy Liquibase update
        |
        v
Kiểm tra history + schema diff + smoke test
        |
        v
Lưu log và bằng chứng triển khai
~~~

Tài khoản migration nên có quyền cần thiết để thay đổi schema; tài khoản runtime của ứng dụng chỉ nên có quyền phục vụ hoạt động của ứng dụng. Không đưa credentials vào changelog hoặc log build. Với production, cần giới hạn quyền chạy migration, bảo vệ thông tin kết nối và ghi nhận ai/phần mềm nào đã thực hiện triển khai.

## 9. Cách xử lý khi phát hiện drift

Khi schema thực tế không khớp lịch sử hoặc changelog, hãy xử lý theo trình tự:

1. Xác nhận đúng database, catalog, schema và tài khoản đang kiểm tra. Sai connection hoặc default schema có thể tạo ra kết quả diff gây hiểu nhầm.
2. Thu thập **history**, **status**, log triển khai gần nhất và snapshot/diff hiện tại.
3. Xác định đối tượng nào khác biệt, khác biệt xuất hiện từ thời điểm nào và ai hoặc tiến trình nào đã tạo ra nó.
4. Phân loại nguyên nhân: migration chưa chạy, migration chạy một phần, thay đổi thủ công, restore/clone, sai bộ lọc context/label hoặc lịch sử bị đồng bộ không đúng.
5. Đánh giá ảnh hưởng đến dữ liệu và ứng dụng. Với DDL đã chạy một phần, xác định rõ phần nào có thể giữ, phần nào cần phục hồi và điều kiện an toàn khi chạy lại.
6. Chọn một thay đổi sửa chữa có thể review, có precondition/hậu điều kiện phù hợp và rollback khả thi. Nếu cần baseline hoặc đồng bộ lịch sử, phải chứng minh schema hiện tại đã tương ứng với changelog.
7. Triển khai trên môi trường thử nghiệm, kiểm tra lại history và schema, sau đó mới áp dụng theo quy trình production.
8. Ghi lại nguyên nhân và biện pháp phòng ngừa để các môi trường khác không lặp lại sai lệch.

Không chỉnh sửa trực tiếp **DATABASECHANGELOG** như một cách sửa nhanh nếu chưa hiểu tác động của định danh, checksum, thứ tự và trạng thái thực tế. Mọi thao tác quản trị lịch sử đều cần có kế hoạch, backup và bằng chứng xác minh.

## 10. Checklist đánh giá trạng thái triển khai

Trước khi kết luận một database đã ở đúng phiên bản, hãy trả lời được các câu hỏi sau:

- Changelog và phiên bản source được triển khai có xác định rõ không?
- Đúng database, catalog, schema, DBMS, context và label đã được chọn chưa?
- **DATABASECHANGELOG** có ghi nhận đúng changeset, định danh và trạng thái thực thi không?
- Có changeset nào **MARK_RAN**, **RERAN**, bị bỏ qua hoặc có checksum cần điều tra không?
- Có changeset pending nào bị bỏ sót ngoài dự kiến không?
- Schema thực tế có đủ bảng, cột, kiểu dữ liệu, constraint, index và đối tượng cần thiết không?
- Các chuyển đổi dữ liệu quan trọng có hậu điều kiện kiểm chứng được không?
- Có khác biệt nào do thao tác thủ công, script ngoài Liquibase hoặc migration lỗi trước đó không?
- SQL dự kiến, rollback và tác động vận hành đã được review chưa?
- Ứng dụng chạy bằng tài khoản thực tế có thể thực hiện các luồng đọc/ghi cần thiết không?
- Bằng chứng triển khai và quyết định xử lý drift đã được lưu lại chưa?

Một kết luận trạng thái tốt cần nêu rõ phạm vi kiểm tra và thời điểm kiểm tra. Ví dụ: “Liquibase không còn changeset pending tại thời điểm triển khai; schema của schema **app** đã được đối chiếu với snapshot chuẩn và không có khác biệt trong phạm vi bảng, cột, constraint và index được kiểm tra; smoke test các luồng đặt hàng đã thành công.” Cách diễn đạt này cho biết bằng chứng nào đã có, thay vì dùng một trạng thái duy nhất để đại diện cho toàn bộ database.

## 11. Nguyên tắc cần ghi nhớ

- Changelog là mô tả thay đổi mong muốn; **DATABASECHANGELOG** là lịch sử Liquibase ghi nhận; catalog là cấu trúc database đang tồn tại.
- **status**, **history** và **validate** chủ yếu kiểm tra changelog cùng lịch sử. Chúng không thay thế **diff**, snapshot hoặc truy vấn metadata khi cần phát hiện schema drift.
- Checksum kiểm soát thay đổi nội dung changeset, không chứng minh schema hoặc dữ liệu hiện tại còn nguyên vẹn.
- **MARK_RAN** và **changelogSync** có thể cập nhật lịch sử mà không thực thi nội dung migration; chỉ dùng khi đã xác minh trạng thái database tương ứng.
- Một changeset thất bại có thể để lại thay đổi một phần tùy DBMS và transaction. Luôn kiểm tra database trước khi thử chạy lại.
- Rollback cần dựa trên khả năng đảo ngược thực tế và phương án bảo vệ dữ liệu.
- Mỗi môi trường có lịch sử riêng; hãy triển khai cùng nguồn changelog và kiểm tra cả lịch sử lẫn schema tại từng môi trường.

Khi tách bạch được lịch sử triển khai và cấu trúc thực tế, đội ngũ có thể dùng Liquibase đúng vai trò: quản lý thay đổi có kiểm soát, đồng thời dùng các phép kiểm tra độc lập để xác nhận database đang ở trạng thái mà ứng dụng và vận hành yêu cầu.

