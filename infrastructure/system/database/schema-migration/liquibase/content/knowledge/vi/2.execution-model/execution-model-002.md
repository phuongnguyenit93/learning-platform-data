# Vai trò và cấu trúc bảng DATABASECHANGELOG

Trong Liquibase, changelog mô tả những thay đổi cần áp dụng cho cơ sở dữ liệu, còn bảng **DATABASECHANGELOG** ghi lại những changeset mà Liquibase đã xử lý trên chính cơ sở dữ liệu đó. Đây là sổ theo dõi triển khai giúp Liquibase biết thay đổi nào đã được thực hiện, kiểm tra tính nhất quán của changeset và cung cấp lịch sử để vận hành các lần cập nhật tiếp theo.

Bài học thuộc chương **Mô hình thực thi** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Module này giúp người học quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; đồng thời thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Sau bài học, bạn có thể giải thích vai trò của DATABASECHANGELOG, nhận diện khóa định danh một changeset, đọc các cột quan trọng, hiểu cách Liquibase sử dụng bảng trong quá trình update và điều tra những tình huống migration chạy lại hoặc bị từ chối do checksum.

## 1. DATABASECHANGELOG là gì?

DATABASECHANGELOG là bảng metadata do Liquibase quản lý trong cơ sở dữ liệu đích. Theo cấu hình mặc định, Liquibase dùng tên bảng **DATABASECHANGELOG**; tên bảng và schema lưu bảng có thể được cấu hình để phù hợp với quy ước của hệ thống.

Mỗi dòng trong bảng đại diện cho một changeset mà Liquibase đã ghi nhận là đã thực thi hoặc đã được đánh dấu là đã chạy. Dòng này cho biết changeset thuộc changelog nào, ai là tác giả, được xử lý vào thời điểm nào, theo thứ tự nào, kết quả thực thi ra sao và checksum nào đang được lưu.

Cần phân biệt ba thành phần:

- **Changelog** là định nghĩa có phiên bản trong mã nguồn, thường viết bằng YAML, XML, JSON hoặc SQL formatted changelog. Nó mô tả thay đổi cần áp dụng.
- **Changeset** là đơn vị thay đổi có định danh, thường gồm **id**, **author** và nội dung thay đổi. Liquibase dùng changeset làm đơn vị theo dõi trong lịch sử.
- **DATABASECHANGELOG** là bảng trong database đích, lưu trạng thái và metadata của các changeset đã được xử lý.

Vì vậy, DATABASECHANGELOG không chứa toàn bộ định nghĩa changelog và cũng không phải bản sao của schema hiện tại. Nó là sổ lịch sử mà Liquibase đối chiếu với changelog đang được cung cấp.

Ví dụ, một nhóm phát triển có changelog như sau:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-01-001
      author: db-team
      comment: Tạo bảng lưu thông tin đơn hàng
      changes:
        - createTable:
            tableName: orders
            columns:
              - column:
                  name: id
                  type: bigint
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: order_code
                  type: varchar(50)
                  constraints:
                    nullable: false
~~~

Khi changeset này được Liquibase thực thi thành công trên một database, Liquibase ghi nhận định danh và thông tin thực thi của nó trong DATABASECHANGELOG. Khi chạy update lần tiếp theo với cùng changelog, Liquibase đọc lịch sử để biết changeset này đã được xử lý.

## 2. Định danh changeset và khóa chính

Một changeset được nhận diện bằng tổ hợp ba giá trị:

1. **ID**: giá trị định danh do người viết changelog đặt.
2. **AUTHOR**: tên hoặc định danh tác giả được khai báo trong changeset.
3. **FILENAME**: đường dẫn changelog mà Liquibase dùng để nhận diện nguồn chứa changeset.

Ba giá trị này kết hợp thành khóa chính của DATABASECHANGELOG. Do đó, chỉ riêng ID không đủ để nhận diện duy nhất một changeset trong toàn bộ hệ thống.

Ví dụ, hai changeset có thể cùng **id: 001** nếu chúng có **author** hoặc **filename** khác nhau. Ngược lại, nếu cả ba giá trị trùng nhau, Liquibase xem chúng là cùng một changeset đã biết.

### Vì sao FILENAME quan trọng?

Giả sử một changeset đã được triển khai từ **db/changelog/releases/001-create-orders.yaml**. Sau đó nhóm phát triển di chuyển file sang **db/changelog/archive/001-create-orders.yaml**. Nếu đường dẫn mà Liquibase ghi nhận thay đổi, tổ hợp định danh có thể thay đổi. Liquibase có thể coi changeset trong vị trí mới là một changeset khác và tìm cách thực thi lại.

Để ổn định định danh khi tổ chức lại thư mục, có thể khai báo **logicalFilePath** phù hợp ngay từ đầu hoặc giữ nguyên giá trị logic đã được dùng trong các môi trường. Khi thay đổi đường dẫn changelog đã triển khai, cần kiểm tra cách Liquibase đang ghi FILENAME trong DATABASECHANGELOG và lập kế hoạch di chuyển có kiểm chứng.

Không nên tùy tiện đổi **id**, **author** hoặc đường dẫn logic của changeset đã phát hành. Các giá trị đó là một phần của danh tính lịch sử.

## 3. Các cột chính trong DATABASECHANGELOG

Bộ cột cụ thể và kiểu dữ liệu có thể khác nhau theo phiên bản Liquibase và hệ quản trị cơ sở dữ liệu. Vì vậy, hãy xem cấu trúc thực tế trên database đang vận hành khi cần viết truy vấn hoặc công cụ kiểm tra. Các cột thường gặp gồm:

| Cột | Vai trò |
|---|---|
| **ID** | Định danh của changeset theo khai báo trong changelog. |
| **AUTHOR** | Tác giả hoặc định danh người tạo changeset. |
| **FILENAME** | Đường dẫn changelog được dùng trong định danh changeset. |
| **DATEEXECUTED** | Thời điểm Liquibase ghi nhận changeset được xử lý. |
| **ORDEREXECUTED** | Thứ tự thực thi mà Liquibase ghi nhận trong lịch sử triển khai. |
| **EXECTYPE** | Loại kết quả thực thi, thường gặp như EXECUTED, RERAN và MARK_RAN. |
| **MD5SUM** | Checksum Liquibase lưu để phát hiện thay đổi nội dung changeset. |
| **DESCRIPTION** | Mô tả ngắn được Liquibase tạo từ các loại thay đổi trong changeset. |
| **COMMENTS** | Nội dung comment được khai báo cho changeset, nếu có. |
| **TAG** | Nhãn đánh dấu một mốc trong lịch sử, thường được sử dụng cùng thao tác tag và rollback theo tag. |
| **LIQUIBASE** | Phiên bản Liquibase đã ghi nhận lần xử lý changeset. |
| **CONTEXTS** | Thông tin context liên quan đến lần triển khai changeset. |
| **LABELS** | Thông tin label liên quan đến lần triển khai changeset. |
| **DEPLOYMENT_ID** | Giá trị dùng để nhóm các changeset thuộc cùng một lần triển khai. |

### 3.1. Nhóm cột định danh

**ID**, **AUTHOR** và **FILENAME** trả lời câu hỏi: Liquibase đang theo dõi changeset nào?

Khi điều tra một changeset bị chạy lại ngoài dự kiến, hãy đối chiếu cả ba cột. Tìm theo ID đơn lẻ có thể dẫn đến kết luận sai nếu nhiều file sử dụng cùng một giá trị ID.

### 3.2. Nhóm cột thời gian và thứ tự

**DATEEXECUTED** cho biết thời điểm ghi nhận. **ORDEREXECUTED** cho biết thứ tự mà Liquibase ghi nhận trong quá trình triển khai. Kết hợp hai cột này giúp đọc lịch sử và xác định thứ tự các thay đổi trong một lần update.

Không nên coi ORDEREXECUTED là số thứ tự toàn cục giữa mọi môi trường. Mỗi database có lịch sử triển khai riêng; thời điểm và thứ tự có thể khác nhau do lịch phát hành, các context được chọn hoặc quá trình triển khai riêng của từng môi trường.

### 3.3. EXECTYPE: changeset đã được xử lý như thế nào?

Một số giá trị thường gặp:

- **EXECUTED**: changeset được thực thi và ghi nhận.
- **RERAN**: changeset được chạy lại, chẳng hạn do cấu hình **runOnChange** hoặc **runAlways**.
- **MARK_RAN**: Liquibase đánh dấu changeset là đã chạy mà không thực thi các thay đổi của changeset trong lần đó. Trường hợp này thường liên quan đến precondition có **onFail: MARK_RAN**.

Khi thấy MARK_RAN, không được mặc định rằng câu lệnh tạo hoặc sửa schema trong changeset đã được chạy. Cần xem precondition và trạng thái database tại thời điểm triển khai để hiểu vì sao Liquibase đánh dấu như vậy.

### 3.4. MD5SUM: checksum của changeset

**MD5SUM** lưu checksum mà Liquibase tính từ nội dung changeset theo cơ chế checksum của Liquibase. Dù tên cột có chữ MD5, đây là cơ chế phát hiện thay đổi nội dung phục vụ quản lý migration, không phải chữ ký bảo mật để xác thực tác giả hay bảo vệ dữ liệu trước hành vi giả mạo.

Khi changeset đã chạy bị sửa nội dung, checksum tính từ changelog hiện tại có thể khác giá trị đã lưu. Liquibase dùng sự khác biệt này để phát hiện thay đổi ngoài dự kiến và có thể từ chối update.

Checksum có thể được để trống hoặc đặt lại trong một số thao tác quản trị như **clear-checksums**; Liquibase sẽ tính lại khi xử lý update tiếp theo. Không nên dùng thao tác này như cách bỏ qua tùy tiện lỗi checksum.

### 3.5. Các cột bổ trợ

**DESCRIPTION** và **COMMENTS** giúp con người đọc lịch sử dễ hơn. **LIQUIBASE** hỗ trợ truy vết phiên bản công cụ. **CONTEXTS** và **LABELS** cung cấp ngữ cảnh của lần triển khai, hữu ích khi một changelog có những changeset chỉ áp dụng cho một số môi trường hoặc nhóm database.

**TAG** đánh dấu một mốc lịch sử để hỗ trợ quy trình rollback theo tag. **DEPLOYMENT_ID** giúp gom các changeset được xử lý trong cùng một lần triển khai, thuận tiện khi đối chiếu log CI/CD với lịch sử database.

Các cột bổ trợ không thay thế ba cột định danh. Khi truy vấn một changeset cụ thể, luôn bắt đầu từ **ID**, **AUTHOR** và **FILENAME**.

## 4. Liquibase sử dụng DATABASECHANGELOG trong quá trình update

Ở mức khái quát, quá trình update diễn ra như sau:

1. Liquibase đọc changelog gốc và các changelog được include để tạo danh sách changeset cần xét.
2. Liquibase kết nối database đích và sử dụng bảng DATABASECHANGELOG để tra cứu lịch sử. Nếu bảng theo dõi chưa tồn tại, Liquibase tạo bảng theo cấu hình và khả năng của database.
3. Với từng changeset, Liquibase đối chiếu tổ hợp **ID**, **AUTHOR**, **FILENAME** với lịch sử.
4. Liquibase xét thêm các điều kiện áp dụng như context, label, precondition và các thuộc tính điều khiển thực thi.
5. Changeset chưa được ghi nhận và đủ điều kiện sẽ được thực thi. Sau khi xử lý thành công, Liquibase ghi metadata của changeset vào DATABASECHANGELOG.
6. Ở lần update sau, changeset đã được ghi nhận thường được bỏ qua. Những changeset mới hoặc được cấu hình chạy lại sẽ được xử lý theo quy tắc tương ứng.

Đây là cơ chế giúp lệnh update có thể được chạy lặp lại trong quy trình triển khai mà không áp dụng lại mọi migration từ đầu.

### Ví dụ về lần chạy đầu và lần chạy tiếp theo

Giả sử changelog có ba changeset:

- **001**: tạo bảng **orders**.
- **002**: thêm cột **created_at**.
- **003**: tạo index cho **orders.order_code**.

Ở lần update đầu tiên, nếu cả ba changeset đều hợp lệ và thực thi thành công, DATABASECHANGELOG sẽ có ba dòng tương ứng. Ở lần update tiếp theo, nếu không có thay đổi nào trong changelog và không changeset nào được cấu hình chạy lại, Liquibase nhận diện cả ba dòng và không thực thi lại ba changeset đó.

Khi bổ sung changeset **004**, Liquibase tìm thấy ba changeset cũ trong lịch sử và chỉ cần xét changeset mới cùng các điều kiện áp dụng của nó. Nếu một changeset cũ bị sửa nội dung, checksum giúp Liquibase phát hiện thay đổi đó.

### Vai trò của precondition

Precondition kiểm tra điều kiện trước khi Liquibase thực thi changeset hoặc changelog. Ví dụ, một changeset chỉ được áp dụng khi bảng đích chưa tồn tại.

Cách xử lý khi điều kiện không đạt phụ thuộc vào cấu hình **onFail** hoặc **onError**. Với **MARK_RAN**, Liquibase ghi nhận changeset là đã chạy với EXECTYPE tương ứng, dù phần thay đổi trong changeset không được thực thi trong lần đó. Với các lựa chọn như **HALT** hoặc **CONTINUE**, luồng xử lý sẽ khác.

Do đó, khi đối chiếu DATABASECHANGELOG với schema thực tế, cần đọc cả precondition. Một dòng MARK_RAN thể hiện quyết định của Liquibase theo chính sách đã khai báo, không chứng minh rằng mọi câu lệnh trong changeset đã được thực hiện.

## 5. Quan hệ giữa DATABASECHANGELOG và checksum

Checksum giúp phát hiện changeset đã triển khai bị chỉnh sửa. Quy tắc vận hành quan trọng là: changeset đã được phát hành và triển khai nên được xem là bất biến. Khi cần thay đổi schema hoặc dữ liệu, hãy tạo changeset mới mô tả phần thay đổi tiếp theo.

Ví dụ, changeset **001** đã tạo bảng **orders** trên production. Nếu sửa trực tiếp changeset **001** để thêm cột **status**, checksum có thể thay đổi và Liquibase phát hiện nội dung hiện tại khác nội dung đã ghi nhận. Cách an toàn là tạo changeset **004** để thêm cột **status**.

Một số thuộc tính và thao tác có ảnh hưởng đến cách kiểm tra checksum:

- **runOnChange**: cho phép chạy lại changeset khi checksum thay đổi. Thường phù hợp với những đối tượng có thể thay thế toàn bộ định nghĩa, chẳng hạn một số view hoặc procedure.
- **runAlways**: yêu cầu changeset được thực thi mỗi lần update đủ điều kiện. Chỉ dùng khi hành vi lặp lại đã được thiết kế an toàn.
- **validCheckSum**: khai báo checksum được chấp nhận trong trường hợp có lý do kiểm soát rõ ràng. Cần ghi lại lý do và quy trình phê duyệt.
- **clear-checksums**: xóa checksum đã lưu để Liquibase tính lại trong lần update tiếp theo. Lệnh này không phải cách sửa migration sai và không tự động chạy lại toàn bộ changeset cũ.

Không nên dùng runOnChange, runAlways, validCheckSum hoặc clear-checksums chỉ để làm cho pipeline vượt qua lỗi. Trước khi chọn cách xử lý, hãy xác định changeset đã chạy ở những môi trường nào, nội dung nào đã thay đổi và liệu database thực tế có còn phù hợp với changelog hay không.

## 6. DATABASECHANGELOG và lịch sử triển khai nhiều môi trường

Mỗi môi trường có database đích và lịch sử DATABASECHANGELOG riêng. Development, test, staging và production có thể có các thời điểm triển khai, thứ tự thực thi và tập changeset đã áp dụng khác nhau.

Khi so sánh các môi trường, nên đối chiếu:

- Bộ định danh changeset gồm **ID**, **AUTHOR** và **FILENAME**.
- Các changeset còn thiếu hoặc xuất hiện khác nhau giữa các môi trường.
- **EXECTYPE** và checksum đối với những changeset cần điều tra.
- Context, label và precondition đã sử dụng trong lần triển khai.
- **DATEEXECUTED**, **ORDEREXECUTED** và **DEPLOYMENT_ID** để liên hệ với log phát hành.

Không yêu cầu timestamp hoặc ORDEREXECUTED phải giống nhau giữa các môi trường. Điều quan trọng là trạng thái migration có đúng với chiến lược phát hành và schema mong muốn hay không.

Nên dùng cùng một phiên bản changelog đã được kiểm soát trong Git hoặc artifact phát hành để triển khai qua các môi trường. Nếu mỗi môi trường nhận một bản changelog khác nhau, việc đối chiếu checksum và lịch sử sẽ khó tin cậy.

Không sao chép thủ công các dòng DATABASECHANGELOG từ môi trường này sang môi trường khác để làm cho lịch sử trông giống nhau. Việc đó có thể khiến Liquibase tin rằng changeset đã chạy trong khi database đích chưa có thay đổi tương ứng, hoặc che giấu sai lệch schema.

## 7. Kiểm tra DATABASECHANGELOG bằng SQL

Có thể đọc bảng bằng truy vấn chỉ đọc để kiểm tra lịch sử. Tùy database, schema và cách đặt tên bảng, cần bổ sung schema hoặc quy tắc quote identifier phù hợp.

Liệt kê lịch sử:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    DATEEXECUTED,
    ORDEREXECUTED,
    EXECTYPE,
    MD5SUM,
    DESCRIPTION,
    DEPLOYMENT_ID
FROM DATABASECHANGELOG
ORDER BY DATEEXECUTED, ORDEREXECUTED;
~~~

Tìm một changeset theo định danh:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    DATEEXECUTED,
    EXECTYPE,
    MD5SUM
FROM DATABASECHANGELOG
WHERE ID = '2026-11-01-001'
  AND AUTHOR = 'db-team'
  AND FILENAME = 'db/changelog/releases/001-create-orders.yaml';
~~~

Đếm số changeset được ghi nhận:

~~~sql
SELECT COUNT(*) AS changeset_count
FROM DATABASECHANGELOG;
~~~

Ví dụ minh họa một dòng dữ liệu:

| Cột | Giá trị minh họa |
|---|---|
| **ID** | **2026-11-01-001** |
| **AUTHOR** | **db-team** |
| **FILENAME** | **db/changelog/releases/001-create-orders.yaml** |
| **DATEEXECUTED** | **2026-11-01 09:15:00** |
| **ORDEREXECUTED** | **1** |
| **EXECTYPE** | **EXECUTED** |
| **MD5SUM** | Checksum do Liquibase tạo |
| **DESCRIPTION** | **createTable tableName=orders** |
| **DEPLOYMENT_ID** | Mã của lần triển khai tương ứng |

Các giá trị trên chỉ minh họa cách đọc bảng. Kiểu dữ liệu, định dạng timestamp, giá trị checksum và các cột có thể khác trên database thực tế.

Khi điều tra, hãy kết hợp truy vấn này với changelog trong đúng phiên bản artifact đã triển khai và log Liquibase. DATABASECHANGELOG cho biết Liquibase đã ghi nhận điều gì; nó không tự chứng minh schema hiện tại không bị chỉnh sửa thủ công sau đó.

## 8. DATABASECHANGELOG khác DATABASECHANGELOGLOCK như thế nào?

Liquibase thường quản lý thêm bảng **DATABASECHANGELOGLOCK**. Hai bảng có mục đích khác nhau:

| Bảng | Mục đích |
|---|---|
| **DATABASECHANGELOG** | Lưu lịch sử và metadata của changeset đã được xử lý. |
| **DATABASECHANGELOGLOCK** | Điều phối khóa để tránh nhiều tiến trình Liquibase cùng thực hiện migration trên một database tại cùng thời điểm. |

DATABASECHANGELOG trả lời câu hỏi “changeset nào đã được ghi nhận?”. DATABASECHANGELOGLOCK trả lời câu hỏi “hiện có tiến trình Liquibase nào đang giữ quyền thực hiện migration?”.

Nếu triển khai báo đang có lock, hãy kiểm tra tiến trình migration và log của pipeline trước. Chỉ giải phóng lock bằng lệnh Liquibase phù hợp sau khi xác nhận không còn tiến trình hợp lệ đang chạy. Không xóa hoặc sửa dữ liệu của hai bảng bằng thao tác thủ công thiếu kiểm soát.

## 9. Kết hợp với Spring Boot và CI/CD

Trong ứng dụng Spring Boot, Liquibase có thể chạy khi ứng dụng khởi động nếu dependency và cấu hình được bật. DATABASECHANGELOG vẫn nằm trong database mà Liquibase kết nối; Spring Boot cung cấp cấu hình cho changelog, schema và tên bảng theo phiên bản đang sử dụng.

Ví dụ cấu hình YAML minh họa:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    database-change-log-table: DATABASECHANGELOG
    database-change-log-lock-table: DATABASECHANGELOGLOCK
~~~

Tên bảng mặc định thường đã đủ dùng. Chỉ cấu hình lại khi có yêu cầu về schema, phân quyền, quy ước đặt tên hoặc cần tránh xung đột với hệ thống khác. Hãy xác nhận thuộc tính cấu hình có trong phiên bản Spring Boot đang dùng.

Trong CI/CD, có thể tổ chức bước migration theo hướng:

1. Kiểm tra changelog và checksum bằng các bước xác thực phù hợp.
2. Sinh SQL dự kiến, ví dụ bằng **update-sql**, để review thay đổi trước khi áp dụng.
3. Triển khai bằng **update** vào đúng database và đúng artifact đã được phê duyệt.
4. Thu thập log triển khai, kết quả lịch sử và thông tin deployment để truy vết.
5. Kiểm tra schema hoặc hành vi ứng dụng sau migration.

DATABASECHANGELOG hỗ trợ bước kiểm tra sau triển khai: nhóm vận hành có thể xác định changeset nào đã được ghi nhận, thời điểm thực thi và lần triển khai liên quan. Quyền truy cập database của pipeline nên tuân theo nguyên tắc tối thiểu cần thiết; tài khoản chạy migration cần quyền phù hợp để Liquibase quản lý cả bảng lịch sử và schema đích.

## 10. DATABASECHANGELOG hỗ trợ rollback như thế nào?

DATABASECHANGELOG là đầu vào quan trọng để Liquibase biết những changeset nào đã được ghi nhận và có thể xét khi rollback. Tuy nhiên, bảng này không lưu đầy đủ câu lệnh rollback hay toàn bộ định nghĩa ngược của migration. Liquibase cần changelog và cấu hình rollback tương ứng để xác định hành động cần thực hiện.

Khi rollback thành công, Liquibase cập nhật lịch sử để phản ánh changeset đã được rollback; các dòng tương ứng với changeset bị rollback được loại khỏi lịch sử theo cơ chế của lệnh rollback. Nếu dùng tag, cột TAG giúp đánh dấu mốc để chọn phạm vi rollback.

Vì rollback có thể làm mất dữ liệu hoặc ảnh hưởng đến ứng dụng, cần:

- Xác nhận changeset có rollback tự động hoặc rollback tùy chỉnh phù hợp.
- Xem trước SQL rollback khi quy trình và phiên bản Liquibase hỗ trợ.
- Sao lưu và kiểm tra khả năng khôi phục dữ liệu trước thao tác có rủi ro.
- Thực hành rollback trên môi trường thử nghiệm có dữ liệu và cấu trúc gần với production.
- Đối chiếu lại schema, dữ liệu và DATABASECHANGELOG sau rollback.

Không xóa dòng trong DATABASECHANGELOG bằng SQL để giả lập rollback. Nếu chỉ xóa dòng mà không đảo ngược thay đổi schema hoặc dữ liệu, lần update tiếp theo có thể chạy lại changeset trên một database đã ở trạng thái khác dự kiến.

## 11. Các tình huống thường gặp và hướng điều tra

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
|---|---|---|
| Changeset cũ bị chạy lại sau khi di chuyển file | FILENAME thay đổi làm thay đổi định danh | So sánh đủ ID, AUTHOR, FILENAME; kiểm tra logicalFilePath và cách include changelog. |
| Update dừng vì checksum khác | Nội dung changeset đã triển khai bị chỉnh sửa hoặc checksum cần được xử lý có chủ đích | So sánh changelog với artifact đã phát hành; ưu tiên tạo changeset mới. Chỉ chấp nhận checksum hoặc tính lại checksum khi có quy trình được kiểm soát. |
| Changeset không được thực thi | Changeset đã có trong lịch sử, context/label không khớp hoặc precondition quyết định bỏ qua | Kiểm tra định danh, cấu hình context/label, precondition và EXECTYPE. |
| Có dòng MARK_RAN nhưng thay đổi không xuất hiện | Precondition có thể đã đánh dấu changeset là đã chạy mà không thực thi nội dung | Đọc onFail/onError, kiểm tra điều kiện tại thời điểm triển khai và trạng thái schema. |
| Không có dòng lịch sử nhưng database có một phần thay đổi | Lần chạy trước có thể thất bại sau khi một số thao tác đã tác động lên database; khả năng rollback transaction phụ thuộc database và cấu hình | Đối chiếu log, schema và dữ liệu thực tế. Không kết luận chỉ từ việc thiếu dòng trong DATABASECHANGELOG. |
| Pipeline báo lock đang được giữ | Một tiến trình Liquibase khác đang chạy hoặc lock còn sót sau sự cố | Kiểm tra DATABASECHANGELOGLOCK, log và tiến trình đang chạy; chỉ giải phóng lock sau khi xác nhận an toàn. |
| Các môi trường có lịch sử khác nhau | Lịch phát hành, context, label hoặc artifact triển khai khác nhau | So sánh bộ định danh changeset và checksum; đối chiếu artifact cùng log triển khai của từng môi trường. |

Một lưu ý quan trọng: việc không tìm thấy dòng trong DATABASECHANGELOG không luôn chứng minh rằng database chưa từng bị tác động. Một số hệ quản trị có thao tác DDL không rollback được như transaction thông thường, và changeset có thể được cấu hình **runInTransaction: false**. Nếu lần chạy thất bại giữa chừng, cần kiểm tra trạng thái database thực tế trước khi quyết định chạy lại hoặc tạo migration sửa chữa.

## 12. Quy tắc vận hành tốt

- Xem changeset đã phát hành là bất biến; bổ sung thay đổi bằng changeset mới.
- Đặt ID rõ ràng, AUTHOR ổn định và đường dẫn changelog có chủ đích.
- Thiết lập logicalFilePath phù hợp nếu cần khả năng di chuyển file mà vẫn giữ định danh lịch sử.
- Dùng precondition để kiểm tra giả định quan trọng trước khi sửa schema hoặc dữ liệu.
- Chỉ bật runOnChange hoặc runAlways khi hiểu rõ tác động của việc chạy lại.
- Đưa changelog và cấu hình Liquibase vào quản lý phiên bản; triển khai cùng một artifact qua các môi trường.
- Dùng SQL chỉ đọc hoặc lệnh Liquibase để kiểm tra lịch sử; tránh cập nhật, chèn hoặc xóa dòng trực tiếp trong DATABASECHANGELOG.
- Khi có sai lệch, so sánh lịch sử với changelog đã phát hành, log triển khai và schema thực tế.
- Ghi lại lý do cho mọi thao tác quản trị checksum, tag, rollback hoặc giải phóng lock.

## 13. Tự kiểm tra kiến thức

**Tình huống 1:** Một changeset có ID giống nhau ở hai file changelog khác nhau. Liquibase có xem chúng là cùng một changeset không?

**Gợi ý:** Kiểm tra cả AUTHOR và FILENAME. Định danh changeset dựa trên tổ hợp ba giá trị ID, AUTHOR và FILENAME.

**Tình huống 2:** Một changeset có EXECTYPE = MARK_RAN. Có thể kết luận câu lệnh tạo bảng trong changeset đã chạy không?

**Gợi ý:** Không. Hãy kiểm tra precondition và chính sách onFail hoặc onError; MARK_RAN có thể ghi nhận changeset mà không thực thi nội dung thay đổi.

**Tình huống 3:** Pipeline báo checksum mismatch ở production sau khi một changeset cũ được sửa. Cách xử lý nên bắt đầu từ đâu?

**Gợi ý:** Xác định artifact đã triển khai và nội dung changeset đã thay đổi. Thông thường nên khôi phục changeset cũ về nội dung đã phát hành và tạo changeset mới cho thay đổi tiếp theo. Không xóa checksum chỉ để bỏ qua cảnh báo.

**Tình huống 4:** DATABASECHANGELOG của staging và production có cùng các changeset nhưng DATEEXECUTED khác nhau. Đây có phải lỗi không?

**Gợi ý:** Không nhất thiết. Mỗi môi trường có lịch triển khai riêng. Hãy so sánh định danh, checksum, kết quả thực thi và trạng thái schema theo chiến lược phát hành.

Khi có thể đọc đúng DATABASECHANGELOG và liên hệ từng dòng với changeset trong changelog, bạn đã có nền tảng để giải thích cách Liquibase theo dõi migration, điều tra sự cố checksum, đối chiếu nhiều môi trường và kiểm soát rollback trong quy trình phát hành.

