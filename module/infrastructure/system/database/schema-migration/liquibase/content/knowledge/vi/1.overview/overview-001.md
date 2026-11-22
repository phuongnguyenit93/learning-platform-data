# Liquibase là gì và bài toán quản lý thay đổi lược đồ

Trong một ứng dụng, lược đồ cơ sở dữ liệu (database schema) gồm các đối tượng như bảng, cột, khóa chính, khóa ngoại, chỉ mục, view và thủ tục lưu trữ. Dữ liệu khởi tạo hoặc dữ liệu tham chiếu cũng có thể cần thay đổi cùng với cấu trúc đó. Khi phần mềm phát triển, các thay đổi này phải được triển khai có thứ tự và nhất quán trên máy phát triển, môi trường kiểm thử, staging và production.

Liquibase là công cụ quản lý thay đổi cơ sở dữ liệu theo phiên bản. Thay vì để mỗi người tự chạy những câu lệnh SQL rời rạc, nhóm mô tả từng thay đổi trong changelog, lưu cùng mã nguồn, rồi để Liquibase xác định thay đổi nào chưa được áp dụng và thực thi chúng theo lịch sử đã ghi nhận.

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, mục tiêu là nắm cách quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp với Spring Boot hoặc CI/CD. Bài này xây dựng nền tảng để hiểu vì sao quy trình đó cần thiết và Liquibase giải quyết phần nào của bài toán.

## 1. Bài toán quản lý thay đổi lược đồ

Một ứng dụng thường thay đổi cơ sở dữ liệu theo nhiều cách:

- Thêm bảng hoặc cột để hỗ trợ chức năng mới.
- Đổi kiểu dữ liệu, thêm ràng buộc, khóa ngoại hoặc chỉ mục.
- Tách một cột thành nhiều cột, chuyển dữ liệu cũ sang cấu trúc mới.
- Cập nhật dữ liệu tham chiếu như danh sách trạng thái, loại tài khoản hoặc cấu hình mặc định.
- Thay đổi view, trigger hoặc stored procedure.

Nếu các thay đổi này chỉ được ghi trong tài liệu triển khai hoặc gửi qua tin nhắn, nhóm sẽ gặp một số vấn đề:

| Vấn đề | Hệ quả |
|---|---|
| Không có lịch sử tập trung | Khó biết môi trường đã chạy câu lệnh nào và chạy vào thời điểm nào. |
| Chạy SQL thủ công | Dễ bỏ sót bước, chạy sai thứ tự hoặc chạy lặp một thao tác không an toàn. |
| Mỗi môi trường có schema khác nhau | Lỗi chỉ xuất hiện ở staging hoặc production dù ứng dụng chạy tốt trên máy lập trình viên. |
| Mã ứng dụng và schema không được phát hành cùng nhau | Phiên bản ứng dụng mới có thể yêu cầu cột chưa tồn tại hoặc không còn tương thích với schema cũ. |
| Sửa trực tiếp lịch sử triển khai | Không thể tái dựng đáng tin cậy một môi trường mới từ mã nguồn hiện tại. |
| Không có kế hoạch hoàn tác | Khi triển khai lỗi, nhóm không biết có thể đảo ngược thay đổi nào và thay đổi nào cần khôi phục dữ liệu. |

Ví dụ, phiên bản ứng dụng mới cần cột **customer.status**. Nếu lập trình viên thêm cột trực tiếp trên máy của mình nhưng quên cập nhật staging, bản phát hành có thể chạy tốt ở môi trường phát triển rồi lỗi khi truy vấn staging. Nếu một người khác tạo cột thủ công ở production, các môi trường lại có lịch sử khác nhau và nhóm không còn một quy trình có thể lặp lại.

Bài toán cốt lõi vì vậy không chỉ là viết câu lệnh ALTER TABLE. Nhóm cần một cơ chế để mô tả thay đổi, lưu chúng trong quản lý phiên bản, áp dụng theo thứ tự, nhận biết trạng thái đã triển khai và kiểm tra các giả định trước khi thực thi.

## 2. Liquibase là gì?

Liquibase là công cụ quản lý migration cơ sở dữ liệu. Người phát triển khai báo các thay đổi trong một hoặc nhiều tệp changelog. Mỗi thay đổi được đóng gói thành changeset có định danh, tác giả và nội dung cụ thể. Khi chạy Liquibase với một cơ sở dữ liệu, công cụ đọc changelog, đối chiếu lịch sử triển khai trong chính cơ sở dữ liệu đó, sau đó chỉ thực thi những changeset còn thiếu theo thứ tự được khai báo.

Liquibase hỗ trợ nhiều dạng changelog như XML, YAML, JSON và SQL có chú thích theo định dạng Liquibase. Với các change type có cấu trúc, Liquibase có thể tạo SQL phù hợp với hệ quản trị cơ sở dữ liệu được hỗ trợ. Khi cần tận dụng tính năng riêng của một hệ quản trị, nhóm có thể dùng SQL tùy chỉnh hoặc các cơ chế phù hợp khác.

Liquibase thường giúp nhóm:

- Đưa thay đổi schema và một số thay đổi dữ liệu vào cùng quy trình phát hành mã nguồn.
- Theo dõi changeset đã chạy trên từng cơ sở dữ liệu.
- Phát hiện một changeset đã áp dụng bị chỉnh sửa thông qua checksum.
- Kiểm tra điều kiện trước khi chạy thay đổi bằng precondition.
- Khai báo cách rollback khi có thể đảo ngược thao tác.
- Chọn phạm vi triển khai theo môi trường bằng contexts, labels và cấu hình kết nối.
- Tích hợp migration vào ứng dụng Spring Boot hoặc pipeline CI/CD.

Liquibase không tự thiết kế mô hình dữ liệu, không thay thế việc review SQL, kiểm thử hiệu năng, sao lưu hay kế hoạch phát hành ứng dụng. Một changeset hợp lệ về cú pháp vẫn có thể gây khóa bảng lâu, làm đầy dung lượng hoặc khiến phiên bản ứng dụng đang chạy không tương thích. Nhóm vẫn phải đánh giá tác động trên hệ quản trị và dữ liệu thực tế.

## 3. Các khái niệm nền tảng

### 3.1. Changelog

Changelog là tệp mô tả các thay đổi cơ sở dữ liệu. Một changelog chính thường đóng vai trò điểm vào và bao gồm các changelog nhỏ hơn theo chức năng hoặc phiên bản phát hành. Cách chia tệp rõ ràng giúp review và tra cứu lịch sử dễ hơn.

Ví dụ cấu trúc thư mục:

~~~text
src/main/resources/
└── db/
    └── changelog/
        ├── db.changelog-master.yaml
        └── changes/
            ├── 001-create-customer.yaml
            ├── 002-add-customer-status.yaml
            └── 003-create-customer-index.yaml
~~~

Changelog chính có thể khai báo các tệp theo thứ tự:

~~~yaml
databaseChangeLog:
  - include:
      file: db/changelog/changes/001-create-customer.yaml
  - include:
      file: db/changelog/changes/002-add-customer-status.yaml
  - include:
      file: db/changelog/changes/003-create-customer-index.yaml
~~~

Đường dẫn trong include phải trỏ đúng tới tệp changelog trong cấu hình tìm kiếm của Liquibase. Nhóm nên giữ cách đặt tên ổn định, dễ đọc và thể hiện thứ tự hoặc mục đích thay đổi.

### 3.2. Changeset

Changeset là đơn vị thay đổi mà Liquibase theo dõi và triển khai. Một changeset thường có ba thành phần nhận diện:

- **id**: định danh do nhóm đặt.
- **author**: người hoặc nhóm chịu trách nhiệm.
- Đường dẫn changelog chứa changeset.

Vì vậy, chỉ trùng id chưa chắc đã tạo ra cùng một changeset nếu tác giả hoặc đường dẫn khác. Trong cùng một changelog, nên đặt id có ý nghĩa và không tái sử dụng tùy tiện.

Một changeset có thể chứa một hoặc nhiều change. Ví dụ sau tạo bảng khách hàng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: platform-team
      comment: Tạo bảng lưu thông tin khách hàng
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
                  type: VARCHAR(320)
                  constraints:
                    nullable: false
                    unique: true
      rollback:
        - dropTable:
            tableName: customer
~~~

Khi changeset này được áp dụng thành công, Liquibase ghi nhận nó trong lịch sử của cơ sở dữ liệu. Lần chạy update tiếp theo trên cùng cơ sở dữ liệu sẽ không chạy lại changeset đó theo cơ chế mặc định.

Nên chia changeset theo một thay đổi có ý nghĩa và có thể review độc lập. Một changeset quá lớn khiến lỗi khó khoanh vùng; quá nhiều changeset vụn vặt lại làm lịch sử khó đọc. Với thay đổi quan trọng, hãy ghi comment để người review hiểu mục đích và ảnh hưởng.

### 3.3. Change type và SQL tùy chỉnh

Change type là cách khai báo thao tác như tạo bảng, thêm cột, tạo chỉ mục, thêm khóa ngoại hoặc cập nhật dữ liệu. Cách khai báo có cấu trúc giúp Liquibase xử lý một phần khác biệt cú pháp giữa các hệ quản trị được hỗ trợ.

Khi cần câu lệnh đặc thù, nhóm có thể dùng change type sql hoặc changelog định dạng SQL. SQL tùy chỉnh đem lại quyền kiểm soát cao, nhưng người viết phải tự xem xét tính tương thích với hệ quản trị, cú pháp rollback và hành vi giao dịch. Không nên giả định cùng một câu SQL sẽ chạy giống nhau trên mọi database.

### 3.4. Lịch sử triển khai: DATABASECHANGELOG

Liquibase tạo bảng DATABASECHANGELOG để lưu trạng thái các changeset đã được xử lý. Bảng này thường chứa thông tin nhận diện như ID, AUTHOR và FILENAME, cùng thời điểm chạy, thứ tự thực thi, kiểu kết quả, checksum và một số metadata khác.

Nhờ lịch sử này, Liquibase biết changeset nào đã chạy trên một cơ sở dữ liệu cụ thể. Hai môi trường có thể đang ở hai trạng thái khác nhau; mỗi lần triển khai, Liquibase đối chiếu changelog với lịch sử của đúng môi trường được kết nối.

DATABASECHANGELOG là nguồn lịch sử triển khai của Liquibase. Không nên tùy tiện xóa hoặc sửa các dòng trong bảng này để ép một migration chạy lại, vì thao tác đó có thể khiến Liquibase hiểu sai trạng thái thực tế của schema.

### 3.5. Khóa triển khai: DATABASECHANGELOGLOCK

DATABASECHANGELOGLOCK dùng để điều phối việc chạy migration trên cùng cơ sở dữ liệu, giúp tránh hai tiến trình Liquibase đồng thời cập nhật changelog gây xung đột. Khi một tiến trình đang giữ khóa, tiến trình khác thường phải chờ hoặc kết thúc theo cấu hình.

Nếu khóa còn tồn tại sau khi một tiến trình bị dừng bất thường, cần xác minh không còn migration nào đang chạy trước khi giải phóng khóa. Xóa hoặc cập nhật khóa khi tiến trình cũ vẫn hoạt động có thể khiến hai lần triển khai chồng lấn.

## 4. Liquibase áp dụng migration như thế nào?

Ở mức khái quát, một lần chạy liquibase update diễn ra theo trình tự:

1. Đọc changelog gốc và các changelog được include.
2. Kết nối tới cơ sở dữ liệu đích bằng thông tin kết nối và quyền được cấp.
3. Lấy khóa triển khai để điều phối các lần cập nhật đồng thời.
4. Đọc DATABASECHANGELOG và xác định changeset nào chưa được áp dụng.
5. Đánh giá contexts, labels và các precondition có liên quan.
6. Sinh hoặc thực thi SQL cho các changeset đủ điều kiện theo thứ tự.
7. Ghi lịch sử, checksum và kết quả thực thi vào DATABASECHANGELOG.
8. Giải phóng khóa sau khi hoàn tất.

Trình tự này giúp migration có thể lặp lại trên nhiều môi trường: cùng một bộ changelog được đối chiếu với lịch sử riêng của từng cơ sở dữ liệu. Tuy nhiên, kết quả cuối cùng vẫn phụ thuộc vào phiên bản hệ quản trị, quyền của tài khoản triển khai, dữ liệu hiện có và các điều kiện của môi trường.

Liquibase có thể quản lý giao dịch cho changeset khi hệ quản trị và loại thao tác hỗ trợ. Không phải mọi thao tác DDL đều có cùng hành vi giao dịch trên mọi database. Với thay đổi nhiều bước hoặc thao tác không thể rollback bằng transaction, cần thiết kế changeset sao cho có thể phát hiện trạng thái dở dang và phục hồi an toàn.

## 5. Precondition: kiểm tra giả định trước khi thay đổi

Precondition là điều kiện Liquibase đánh giá trước khi thực thi changeset hoặc một nhóm thay đổi. Nó giúp xác nhận môi trường đang ở trạng thái mà migration mong đợi, chẳng hạn bảng đã tồn tại, cột chưa tồn tại, đang dùng đúng hệ quản trị hoặc đang kết nối bằng tài khoản phù hợp.

Ví dụ, changeset dưới đây chỉ thêm cột status khi bảng khách hàng đã có cột email:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-add-customer-status
      author: platform-team
      preConditions:
        - onFail: HALT
        - columnExists:
            tableName: customer
            columnName: email
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: status
                  type: VARCHAR(20)
                  defaultValue: ACTIVE
      rollback:
        - dropColumn:
            tableName: customer
            columnName: status
~~~

Một số cách xử lý khi precondition không đạt:

| Giá trị onFail | Hành vi khái quát |
|---|---|
| HALT | Dừng quá trình cập nhật. Đây thường là lựa chọn an toàn khi giả định bắt buộc bị sai. |
| WARN | Ghi cảnh báo rồi tiếp tục xử lý changeset. Chỉ dùng khi nhóm hiểu rõ rủi ro. |
| CONTINUE | Bỏ qua changeset trong lần chạy này và tiếp tục; changeset chưa được đánh dấu là đã chạy. |
| MARK_RAN | Bỏ qua nội dung changeset nhưng ghi nhận nó như đã chạy. Chỉ dùng khi trạng thái hiện tại thực sự tương đương kết quả mong muốn. |

Precondition cũng có thể gặp lỗi khi đánh giá, ví dụ thiếu quyền đọc metadata hoặc kết nối không ổn định. Cần phân biệt trường hợp điều kiện không đúng với trường hợp không thể kiểm tra điều kiện. Có thể cấu hình cách xử lý lỗi bằng onError; với migration quan trọng, dừng triển khai thường an toàn hơn việc tiếp tục trong trạng thái chưa xác định.

Precondition không thay thế kiểm thử. Nó kiểm tra các giả định được khai báo, chứ không chứng minh dữ liệu đã đúng nghiệp vụ, truy vấn mới đủ nhanh hoặc ứng dụng tương thích với schema.

## 6. Checksum: bảo vệ tính nhất quán của changeset

Khi changeset được áp dụng, Liquibase tính checksum và lưu giá trị đó trong DATABASECHANGELOG, thường ở cột MD5SUM. Ở các lần chạy sau, Liquibase tính lại và đối chiếu để phát hiện nội dung của changeset đã thay đổi so với phiên bản được triển khai trước đó.

Checksum giúp phát hiện một lỗi quy trình phổ biến: sửa trực tiếp changeset cũ sau khi nó đã chạy ở một môi trường. Nếu nội dung thay đổi, Liquibase có thể báo lỗi validation do checksum không còn khớp. Đây là tín hiệu để nhóm xem xét lịch sử thay đổi.

Quy tắc thực hành quan trọng là xem changeset đã triển khai như lịch sử bất biến. Nếu cần điều chỉnh schema hoặc sửa dữ liệu, hãy tạo changeset mới mô tả phần điều chỉnh. Cách này giữ cho một môi trường mới có thể tái dựng cùng chuỗi thay đổi mà các môi trường cũ đã trải qua.

Liquibase có các tùy chọn đặc biệt như runOnChange để chạy lại changeset khi nội dung thay đổi, thường hữu ích với đối tượng có thể thay thế như view hoặc stored procedure. runAlways cho phép chạy changeset ở mỗi lần cập nhật. Đây là các hành vi có chủ đích và cần review kỹ; không nên bật chúng để che giấu việc sửa lịch sử migration.

Checksum là cơ chế kiểm tra tính nhất quán của nội dung changeset trong quy trình Liquibase, không phải chữ ký bảo mật cho toàn bộ cơ sở dữ liệu. Việc xóa hoặc tính lại checksum hàng loạt không phải cách sửa mặc định cho lỗi do chỉnh sửa changeset cũ. Trước khi dùng thao tác quản trị checksum, cần xác định nguyên nhân và đánh giá ảnh hưởng trên các môi trường.

## 7. Rollback: chuẩn bị đường lui có kiểm soát

Rollback là thao tác đảo ngược một hoặc nhiều changeset đã triển khai. Với một số change type có cấu trúc, Liquibase có thể suy ra thao tác ngược. Với SQL tùy chỉnh hoặc thao tác không có phép đảo ngược rõ ràng, nhóm cần khai báo rollback tường minh.

Ví dụ trong changeset tạo bảng ở trên, rollback là xóa bảng vừa tạo. Với changeset thêm cột, rollback có thể xóa cột đó nếu việc xóa không làm mất dữ liệu cần giữ lại.

Không phải migration nào cũng có thể rollback an toàn:

- Xóa cột hoặc bảng có thể làm mất dữ liệu không thể tái tạo.
- Gộp nhiều bản ghi thành một bản ghi có thể không có phép biến đổi ngược.
- Gửi dữ liệu ra hệ thống bên ngoài không thể được hoàn tác chỉ bằng SQL.
- Một thay đổi đã được ứng dụng mới sử dụng có thể khiến việc quay về phiên bản ứng dụng cũ không còn tương thích.

Vì vậy, rollback cần được thiết kế cùng migration và kiểm thử trên dữ liệu đại diện. Trước khi chạy ở production, nhóm nên biết rollback sẽ tác động đến đối tượng nào, có làm mất dữ liệu không, cần dừng ứng dụng hay không và có cần khôi phục từ backup hay không. Rollback không thay thế backup hoặc kế hoạch khôi phục thảm họa.

Trong một số tình huống, triển khai một changeset sửa lỗi mới sẽ an toàn hơn chạy rollback. Ví dụ, nếu migration đã ghi dữ liệu nghiệp vụ mới và ứng dụng đã bắt đầu sử dụng dữ liệu đó, một migration tiến về phía trước có thể giữ lại dữ liệu và đưa schema về trạng thái tương thích tốt hơn.

## 8. Phối hợp nhiều môi trường

Thông thường, nhóm nên duy trì một bộ changelog trong quản lý phiên bản và áp dụng nó lên từng cơ sở dữ liệu bằng cấu hình kết nối riêng. Changelog mô tả chuỗi thay đổi; thông tin máy chủ, database, tài khoản và mật khẩu được cung cấp theo môi trường.

Một số cơ chế hỗ trợ kiểm soát phạm vi:

- **Contexts**: chọn nhóm changeset theo ngữ cảnh triển khai, ví dụ dữ liệu mẫu chỉ dùng trong môi trường phát triển.
- **Labels**: gắn nhãn changeset để pipeline chọn tập thay đổi phù hợp với mục tiêu phát hành.
- **Properties**: đưa giá trị có thể thay đổi theo môi trường vào cấu hình thay vì ghi cứng thông tin kết nối hoặc giá trị triển khai vào changelog.

Cần thống nhất cách dùng contexts và labels trong nhóm. Nếu bộ lọc của pipeline vô tình loại một changeset bắt buộc, môi trường có thể thiếu schema dù lệnh triển khai kết thúc mà không có lỗi rõ ràng. Những migration thiết yếu cho ứng dụng không nên phụ thuộc vào bộ lọc tùy chọn thiếu kiểm soát.

Không nên để nhiều tiến trình độc lập cùng sở hữu việc migration một database trong cùng thời điểm. Nếu ứng dụng Spring Boot tự chạy Liquibase lúc khởi động và pipeline cũng chạy Liquibase, hãy xác định rõ ai là bên chịu trách nhiệm triển khai schema và điều phối thứ tự. Bảng khóa giúp hạn chế chạy đồng thời, nhưng không thay thế thiết kế phát hành thống nhất.

## 9. Tích hợp với Spring Boot và CI/CD

### 9.1. Spring Boot

Trong ứng dụng Spring Boot, có thể thêm thư viện liquibase-core vào classpath và cấu hình DataSource. Khi Liquibase được kích hoạt, Spring Boot có thể chạy migration trong quá trình khởi động ứng dụng.

Ví dụ cấu hình trong application.yaml:

~~~yaml
spring:
  liquibase:
    change-log: classpath:db/changelog/db.changelog-master.yaml
    enabled: true
~~~

Tệp changelog chính cần nằm đúng vị trí trên classpath. Thông tin kết nối thường được cấu hình qua datasource của Spring Boot hoặc cấu hình Liquibase riêng khi cần. Tài khoản chạy migration cần đủ quyền DDL/DML cần thiết; tài khoản runtime của ứng dụng có thể được cấp quyền hẹp hơn.

Nếu nhóm chọn để Liquibase quản lý schema, nên tránh để cơ chế tự cập nhật schema của ORM và Liquibase cùng thay đổi cấu trúc theo hai nguồn độc lập. Có thể cấu hình Hibernate ở chế độ kiểm tra schema như validate, tùy phiên bản và cách tổ chức ứng dụng, để phát hiện chênh lệch khi khởi động.

Trong hệ thống có nhiều replica, chạy migration lúc mọi instance cùng khởi động có thể tạo độ trễ hoặc tranh chấp triển khai. Hãy cân nhắc chạy migration trong một bước phát hành riêng trước khi khởi động phiên bản ứng dụng mới, hoặc bảo đảm quy trình khởi động được điều phối phù hợp.

### 9.2. CI/CD

Một pipeline thường tổ chức migration thành bước có thể kiểm tra và truy vết:

1. Kiểm tra changelog và cấu hình bằng lệnh liquibase validate.
2. Sinh SQL dự kiến bằng liquibase updateSQL để review tác động trước khi thực thi.
3. Chạy migration trên database dùng cho kiểm thử tích hợp.
4. Kiểm tra schema, dữ liệu, khả năng tương thích và thời gian thực thi.
5. Đưa cùng phiên bản changelog đã kiểm tra lên staging rồi production theo quy trình phê duyệt của nhóm.
6. Lưu log triển khai, phiên bản mã nguồn, kết quả và người hoặc pipeline thực hiện.

validate giúp phát hiện một số lỗi cấu trúc changelog và tính nhất quán, còn updateSQL cho phép xem SQL Liquibase dự kiến tạo ra. Hai bước này không chứng minh migration chắc chắn chạy thành công trên dữ liệu production; vẫn cần kiểm thử trên hệ quản trị và dữ liệu đủ đại diện.

Thông tin xác thực nên được cấp qua secret của môi trường CI/CD hoặc hệ thống quản lý bí mật. Tránh ghi mật khẩu vào repository, changelog hoặc log pipeline. Tài khoản triển khai nên có đúng quyền cần thiết và được quản lý riêng với tài khoản ứng dụng thông thường.

## 10. Migration an toàn khi ứng dụng đang hoạt động

Một migration có thể đúng về mặt schema nhưng vẫn làm gián đoạn ứng dụng đang chạy. Ví dụ, nếu phiên bản mới yêu cầu cột bắt buộc ngay lập tức, trong khi phiên bản cũ vẫn đang ghi dữ liệu, việc thêm cột với ràng buộc quá sớm có thể khiến một trong hai phiên bản lỗi.

Với hệ thống cần triển khai liên tục, có thể dùng chiến lược **expand–migrate–contract**:

1. **Expand**: thêm cấu trúc mới theo cách tương thích ngược, ví dụ thêm cột nullable hoặc bảng mới mà phiên bản cũ vẫn hoạt động được.
2. **Migrate**: phát hành ứng dụng có khả năng đọc/ghi cấu trúc mới; chuyển dữ liệu cũ theo từng đợt và theo dõi kết quả.
3. **Switch**: chuyển luồng đọc chính sang cấu trúc mới sau khi dữ liệu đã được kiểm chứng.
4. **Contract**: ở một lần phát hành sau, loại bỏ cột hoặc cấu trúc cũ khi không còn phiên bản ứng dụng nào phụ thuộc.

Với bảng lớn, cần đánh giá thời gian tạo chỉ mục, mức khóa, dung lượng log, tốc độ backfill và khả năng tiếp tục sau lỗi. Có hệ quản trị hỗ trợ cách tạo index ít khóa hơn hoặc thao tác trực tuyến; cú pháp và giới hạn khác nhau theo database. Hãy dùng tài liệu của hệ quản trị đích để chọn chiến lược cụ thể.

## 11. Quy trình thực hành đề xuất

Khi tạo một migration mới, có thể đi theo trình tự sau:

1. Xác định yêu cầu: thay đổi schema hay dữ liệu, môi trường nào bị ảnh hưởng và phiên bản ứng dụng nào cần nó.
2. Viết changeset mới với id, author, comment và thay đổi nhỏ, rõ mục đích.
3. Thêm precondition khi migration phụ thuộc vào trạng thái hiện có cần được xác nhận.
4. Khai báo rollback nếu có phép đảo ngược an toàn; ghi rõ giới hạn nếu thao tác không thể hoàn tác.
5. Chạy validation và xem SQL dự kiến sinh ra.
6. Áp dụng trên database thử nghiệm có cấu trúc và dữ liệu gần với thực tế.
7. Kiểm tra DATABASECHANGELOG, schema, dữ liệu, thời gian chạy và log lỗi.
8. Kiểm thử ứng dụng với cả schema trước và sau nếu quy trình phát hành cần tương thích nhiều phiên bản.
9. Đưa changeset vào repository, review cùng mã ứng dụng và triển khai theo thứ tự môi trường.
10. Sau khi đã áp dụng, giữ nguyên changeset lịch sử; mọi điều chỉnh tiếp theo được ghi bằng changeset mới.

Một migration tốt cần có mục đích rõ ràng, kết quả dự kiến có thể kiểm chứng và cách xử lý khi thất bại. Với thao tác có nguy cơ mất dữ liệu, cần bổ sung backup, kế hoạch khôi phục hoặc bước chuyển đổi dữ liệu có thể tiếp tục an toàn.

## 12. Những lỗi thường gặp và cách phòng tránh

| Lỗi | Cách phòng tránh |
|---|---|
| Sửa changeset đã chạy | Tạo changeset mới để sửa trạng thái; chỉ dùng runOnChange cho trường hợp được thiết kế rõ ràng. |
| Đặt id trùng hoặc đổi đường dẫn tùy tiện | Dùng quy ước định danh và tổ chức changelog ổn định. |
| Bỏ qua precondition thất bại | Xác định vì sao trạng thái không đúng; không dùng MARK_RAN chỉ để pipeline chạy tiếp. |
| Giả định rollback luôn khôi phục được dữ liệu | Viết và kiểm thử rollback; chuẩn bị backup hoặc migration sửa lỗi tiến về phía trước. |
| Chạy migration đồng thời từ nhiều nơi | Chỉ định một đầu mối triển khai cho mỗi database và điều phối pipeline/ứng dụng. |
| Chỉ kiểm thử trên database trống | Kiểm thử với dữ liệu có sẵn, dữ liệu biên và kích thước gần thực tế. |
| Dùng tài khoản runtime có quyền DDL quá rộng | Tách quyền migration và quyền truy cập thường ngày của ứng dụng khi kiến trúc cho phép. |
| Coi validate là bằng chứng migration chạy được | Xem SQL sinh ra và thực thi thử trên đúng hệ quản trị, phiên bản và dữ liệu đại diện. |

## 13. Kết luận

Liquibase giải quyết bài toán quản lý thay đổi cơ sở dữ liệu bằng cách biến migration thành lịch sử có phiên bản, có định danh và có thể triển khai lặp lại. Changelog mô tả chuỗi thay đổi; changeset là đơn vị thực thi; precondition kiểm tra giả định; checksum giúp phát hiện nội dung lịch sử bị sửa; DATABASECHANGELOG lưu trạng thái đã áp dụng; DATABASECHANGELOGLOCK điều phối các lần cập nhật; rollback cung cấp đường lui khi thao tác có thể đảo ngược.

Giá trị của Liquibase đến từ việc kết hợp công cụ với kỷ luật phát hành: giữ changeset đã chạy ổn định, kiểm tra SQL dự kiến, thử trên dữ liệu đại diện, phối hợp migration với vòng đời ứng dụng và ghi nhận kết quả trên từng môi trường. Khi các nguyên tắc đó được thực hiện nhất quán, nhóm có thể kiểm soát thay đổi schema và dữ liệu tốt hơn trong Spring Boot cũng như pipeline CI/CD.

