# Đặt tên và vị trí các bảng quản lý của Liquibase

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Hai bảng metadata cốt lõi giúp Liquibase duy trì lịch sử và điều phối các lần cập nhật là **DATABASECHANGELOG** và **DATABASECHANGELOGLOCK**. Khi triển khai vào một database có nhiều schema, nhiều ứng dụng hoặc nhiều pipeline, việc đặt tên và chọn vị trí cho hai bảng này cần được thiết kế thống nhất.

Cấu hình đúng giúp nhóm vận hành tìm được lịch sử migration, cấp quyền rõ ràng, tránh xung đột giữa các ứng dụng và bảo đảm mọi tiến trình Liquibase cùng nhìn vào một bộ metadata. Nội dung dưới đây tập trung vào tên bảng, schema/catalog chứa bảng, cấu hình trong Liquibase CLI và Spring Boot, cũng như cách chuyển đổi cấu hình an toàn.

## 1. Hai bảng metadata mà Liquibase quản lý

Liquibase thường tạo và sử dụng hai bảng trong database đích:

| Bảng mặc định | Vai trò | Dữ liệu tiêu biểu |
|---|---|---|
| DATABASECHANGELOG | Ghi nhận changeset đã được xử lý trên database | ID, AUTHOR, FILENAME, DATEEXECUTED, ORDEREXECUTED, EXECTYPE, MD5SUM và thông tin triển khai |
| DATABASECHANGELOGLOCK | Điều phối quyền cập nhật giữa các tiến trình Liquibase | ID của lock, trạng thái LOCKED, thời điểm khóa và người giữ khóa |

**DATABASECHANGELOG** là sổ lịch sử của changelog. Liquibase dùng các định danh changeset cùng thông tin đã ghi nhận để xác định nội dung còn cần chạy. Bảng này giúp trả lời changeset nào đã được triển khai, thời điểm ghi nhận và kiểu thực thi được lưu.

**DATABASECHANGELOGLOCK** hỗ trợ khóa khi Liquibase thực hiện cập nhật. Một tiến trình lấy lock trước khi chạy migration; tiến trình khác kết nối vào cùng bộ lock sẽ chờ cho đến khi lock được giải phóng hoặc hết thời gian chờ đã cấu hình. Cơ chế này giảm nguy cơ hai tiến trình cùng cập nhật một luồng migration trên cùng database.

Tên mặc định thường là chữ hoa DATABASECHANGELOG và DATABASECHANGELOGLOCK. Liquibase cho phép thay đổi tên hai bảng thông qua các tham số cấu hình. Mỗi database hoặc luồng triển khai cần có cách nhận diện bộ metadata rõ ràng và nhất quán.

## 2. Phân biệt tên bảng với vị trí lưu bảng

Có ba quyết định cấu hình thường bị nhầm lẫn:

1. **Tên bảng metadata:** xác định bảng lịch sử và bảng lock có tên gì.
2. **Schema/catalog metadata:** xác định hai bảng đó nằm ở schema hoặc catalog nào.
3. **Schema/catalog mặc định của đối tượng ứng dụng:** xác định các bảng, index, constraint và đối tượng do changeset tạo ra sẽ được đặt ở đâu khi changelog không chỉ định rõ.

Liquibase cung cấp các tham số riêng cho từng quyết định:

| Mục đích | Tham số Liquibase | Ý nghĩa |
|---|---|---|
| Tên bảng lịch sử | databaseChangeLogTableName | Tên bảng lưu changeset đã xử lý |
| Tên bảng khóa | databaseChangeLogLockTableName | Tên bảng điều phối lock |
| Schema chứa bảng metadata | liquibaseSchemaName | Schema Liquibase dùng cho hai bảng quản lý |
| Catalog chứa bảng metadata | liquibaseCatalogName | Catalog Liquibase dùng cho hai bảng quản lý |
| Schema mặc định của đối tượng ứng dụng | defaultSchemaName | Schema mặc định cho các đối tượng trong changelog |
| Catalog mặc định của đối tượng ứng dụng | defaultCatalogName | Catalog mặc định cho các đối tượng trong changelog |
| Tablespace của bảng metadata | liquibaseTablespaceName | Tablespace dùng khi tạo bảng metadata trên DBMS hỗ trợ |

Ví dụ, một database PostgreSQL có thể được tổ chức như sau:

~~~text
database: commerce
|
+-- platform_meta
|   +-- orders_liquibase_changelog
|   +-- orders_liquibase_lock
|
+-- orders
|   +-- orders
|   +-- order_items
|   +-- payments
|
+-- billing
    +-- invoices
    +-- payment_attempts
~~~

Trong cấu hình này, liquibaseSchemaName là platform_meta, còn defaultSchemaName là orders. Hai tham số phục vụ hai phạm vi khác nhau. Khi changeset ghi rõ schema hoặc catalog cho một đối tượng, thông tin chỉ định trong changeset cần được xem xét cùng cấu hình mặc định.

### 2.1. Chọn tên bảng dễ quản trị

Tên bảng nên thể hiện rõ ứng dụng hoặc luồng migration sở hữu nó. Một số quy ước có thể dùng:

| Phạm vi | Bảng lịch sử | Bảng lock |
|---|---|---|
| Một ứng dụng tên orders | orders_liquibase_changelog | orders_liquibase_lock |
| Một dịch vụ billing | billing_dbchangelog | billing_dbchangeloglock |
| Một bộ migration dùng chung | platform_dbchangelog | platform_dbchangeloglock |

Nên thống nhất các nguyên tắc sau:

- Dùng một quy ước đặt tên nhất quán trong tất cả môi trường.
- Dùng cặp tên có quan hệ rõ ràng để người vận hành nhận biết bảng lịch sử và bảng lock thuộc cùng luồng.
- Chọn tên ngắn, ổn định và tương thích với giới hạn độ dài identifier của DBMS.
- Tránh từ khóa dành riêng của SQL và ký tự đặc biệt gây khó khi truy vấn metadata.
- Ưu tiên identifier không cần dấu nháy kép; việc viết hoa/thường cần tuân theo quy tắc của DBMS.
- Không đưa tên môi trường như dev, staging hoặc prod vào tên bảng nếu cùng một database được nâng cấp qua các môi trường bằng cùng một cấu hình logic. Tên bảng thường đại diện cho ứng dụng hoặc luồng migration.
- Ghi nhận tên bảng và schema trong tài liệu vận hành, cấu hình triển khai và quy trình cấp quyền.

Tên bảng metadata là một phần của cấu hình định danh lịch sử. Thay đổi tên bảng giữa các lần chạy có thể khiến Liquibase tìm thấy một bảng mới chưa có lịch sử. Vì vậy, cần xem quyết định đặt tên như một phần của thiết kế triển khai dài hạn.

### 2.2. Ghép cặp bảng lịch sử và bảng lock

Bảng lịch sử và bảng lock nên được cấu hình cùng nhau cho mỗi luồng migration. Nếu một ứng dụng đổi tên bảng lịch sử nhưng vẫn dùng lock table của một luồng khác, hai ứng dụng có thể cùng chờ trên một lock hoặc dùng cơ chế điều phối không đúng với ranh giới sở hữu.

Với hai ứng dụng độc lập dùng chung một database:

- Nếu chúng cùng quản lý một changelog và một vòng đời triển khai, có thể dùng chung một bộ bảng metadata. Changeset cần có định danh ổn định và tránh trùng lặp giữa các file.
- Nếu mỗi ứng dụng có changelog, lịch phát hành và quyền sở hữu riêng, nên dùng bộ bảng lịch sử và lock riêng. Cách này giúp tách lịch sử và phạm vi điều phối.
- Nếu nhiều tiến trình cùng dùng một bộ bảng, tất cả phải thống nhất tên bảng, schema, catalog và cấu hình kết nối. Một tiến trình dùng tên mặc định trong khi tiến trình khác dùng tên tùy chỉnh có thể tạo ra hai lịch sử tách rời.

Dùng chung lock table giữa các luồng độc lập có thể làm các lần cập nhật tuần tự hóa và chờ nhau. Dùng lock riêng cho mỗi luồng giảm sự chờ đợi giữa các ứng dụng, đồng thời đòi hỏi nhóm quản trị theo dõi từng bộ metadata tương ứng.

## 3. Chọn schema và catalog cho bảng metadata

### 3.1. Tách schema quản lý khỏi schema nghiệp vụ

Trong database có nhiều schema, một lựa chọn phổ biến là đặt bảng metadata trong schema quản trị riêng. Ví dụ:

~~~text
database: commerce
|
+-- platform_meta
|   +-- orders_liquibase_changelog
|   +-- orders_liquibase_lock
|
+-- orders
|   +-- orders
|   +-- order_items
|   +-- payments
|
+-- billing
    +-- invoices
    +-- payment_attempts
~~~

Lợi ích của cách bố trí này:

- Người vận hành tìm lịch sử triển khai tại một vị trí thống nhất.
- Quyền đọc/ghi metadata có thể được cấp riêng cho tài khoản migration.
- Có thể phân biệt rõ quyền thay đổi schema nghiệp vụ với quyền cập nhật bảng lịch sử.
- Các công cụ kiểm kê và backup có thể đưa schema quản trị vào phạm vi cần bảo vệ.
- Nhiều ứng dụng có thể dùng chung một schema quản trị, trong khi mỗi ứng dụng có cặp bảng riêng.

Schema metadata thường cần được tạo trước bằng quy trình provisioning hoặc bởi DBA. Tài khoản chạy Liquibase phải có quyền tạo và thao tác trên hai bảng trong schema đó. Tùy DBMS và cách cấp quyền, tài khoản có thể cần quyền sử dụng schema, tạo bảng, đọc, thêm, cập nhật và xóa bản ghi.

### 3.2. Catalog và tablespace

Một số DBMS tổ chức database theo catalog, schema và tablespace với ý nghĩa khác nhau. liquibaseCatalogName xác định catalog chứa bảng metadata; liquibaseTablespaceName chỉ định tablespace khi DBMS và driver hỗ trợ. Các tham số này bổ sung cho liquibaseSchemaName.

Không nên xem catalog và schema là hai tên thay thế cho nhau. Cần xác định cấu trúc phân cấp của DBMS đang dùng và kiểm tra database connection thực sự trỏ đến catalog nào. Với môi trường không dùng catalog riêng hoặc DBMS không hỗ trợ tablespace theo cách Liquibase cấu hình, hãy để tham số tương ứng theo mặc định của hệ thống.

### 3.3. Phân biệt default schema với liquibase schema

Ví dụ sau minh họa mục tiêu đặt bảng metadata ở platform_meta và đối tượng ứng dụng ở orders:

~~~properties
liquibaseSchemaName=platform_meta
defaultSchemaName=orders
databaseChangeLogTableName=orders_liquibase_changelog
databaseChangeLogLockTableName=orders_liquibase_lock
~~~

Nếu chỉ cấu hình defaultSchemaName=orders, Liquibase sẽ dùng schema mặc định đó cho đối tượng changelog khi cần phân giải schema, còn bảng metadata vẫn theo vị trí Liquibase được cấu hình hoặc mặc định của connection. Nếu chỉ cấu hình liquibaseSchemaName=platform_meta, bảng metadata được đặt trong schema quản trị, còn đối tượng nghiệp vụ tiếp tục theo schema được khai báo trong changelog hoặc schema mặc định của database.

Cần kiểm tra kỹ cả hai giá trị trong môi trường nhiều schema. Nếu bỏ sót cấu hình, Liquibase có thể tạo bảng metadata trong schema mặc định của tài khoản kết nối hoặc tạo đối tượng nghiệp vụ ở schema không dự kiến.

## 4. Cấu hình trong Liquibase CLI và file properties

### 4.1. Cấu hình trong liquibase.properties

Có thể lưu các tham số dùng chung trong file cấu hình của Liquibase:

~~~properties
url=jdbc:postgresql://localhost:5432/commerce
username=commerce_migrator
changeLogFile=db/changelog/db.changelog-master.yaml

liquibaseSchemaName=platform_meta
defaultSchemaName=orders
databaseChangeLogTableName=orders_liquibase_changelog
databaseChangeLogLockTableName=orders_liquibase_lock
~~~

Trong ví dụ, mật khẩu được cấp riêng qua secret manager hoặc cơ chế biến môi trường mà runner/Liquibase hỗ trợ, chẳng hạn biến môi trường cấu hình lệnh LIQUIBASE_COMMAND_PASSWORD. Không ghi mật khẩu production dạng rõ trong repository. File properties có thể được tách theo môi trường hoặc được tạo từ cấu hình bảo mật của pipeline.

### 4.2. Ghi đè tham số từ CLI

Khi cần thử cấu hình hoặc kiểm tra một database cụ thể, có thể truyền tham số qua dòng lệnh:

~~~bash
liquibase \
  --liquibase-schema-name=platform_meta \
  --default-schema-name=orders \
  --database-changelog-table-name=orders_liquibase_changelog \
  --database-changelog-lock-table-name=orders_liquibase_lock \
  status --verbose
~~~

Sau khi xác nhận cấu hình, dùng cùng bộ tham số với các lệnh kiểm tra và triển khai như validate, history, update-sql và update. Các tham số cần nhất quán giữa lần kiểm tra trước triển khai và lần thực thi thực tế.

Tên tham số CLI được viết theo dạng kebab-case; tên thuộc tính trong file properties thường dùng camelCase. Hãy đối chiếu với phiên bản Liquibase đang dùng khi triển khai cấu hình mới, đặc biệt khi nâng cấp phiên bản CLI hoặc plugin.

## 5. Cấu hình trong Spring Boot

Spring Boot cung cấp nhóm thuộc tính spring.liquibase để cấu hình Liquibase khi ứng dụng khởi động. Ví dụ:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/commerce
    username: commerce_app
    password: ${DB_PASSWORD}
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
    liquibase-schema: platform_meta
    default-schema: orders
    database-change-log-table: orders_liquibase_changelog
    database-change-log-lock-table: orders_liquibase_lock
    user: commerce_migrator
    password: ${LIQUIBASE_PASSWORD}
~~~

Trong cấu hình này:

- spring.datasource xác định kết nối mặc định của ứng dụng.
- spring.liquibase.change-log trỏ đến changelog gốc.
- spring.liquibase.liquibase-schema chọn schema chứa bảng metadata.
- spring.liquibase.default-schema chọn schema mặc định cho đối tượng changelog.
- spring.liquibase.database-change-log-table và spring.liquibase.database-change-log-lock-table xác định tên hai bảng quản lý.
- spring.liquibase.user và spring.liquibase.password có thể dùng thông tin xác thực dành riêng cho migration.

Tên thuộc tính Spring Boot cần khớp với phiên bản Spring Boot đang sử dụng. Kiểm tra metadata cấu hình và tài liệu của phiên bản dự án khi nâng cấp framework. Nếu dùng cấu hình Java hoặc nhiều profile, bảo đảm các giá trị cuối cùng được nạp giống nhau trong mọi instance.

Tách tài khoản migration khỏi tài khoản runtime giúp giới hạn quyền. Tài khoản migration có thể cần quyền DDL trên schema nghiệp vụ và quyền DML trên schema metadata. Tài khoản runtime thường chỉ cần quyền truy cập dữ liệu theo chức năng ứng dụng. Không nên cấp quyền tạo bảng metadata cho mọi kết nối runtime nếu pipeline hoặc một migration job chuyên trách đã đảm nhận công việc đó.

## 6. Quyền truy cập và vòng đời tạo bảng

Liquibase có thể khởi tạo bảng quản lý khi chạy lần đầu nếu bảng chưa tồn tại và tài khoản có quyền phù hợp. Với schema metadata riêng, cần chuẩn bị schema và quyền trước khi chạy. Quyền thường được chia theo giai đoạn:

| Hoạt động | Quyền thường cần |
|---|---|
| Tạo schema metadata | Quyền quản trị hoặc quyền tạo schema theo DBMS |
| Tạo hai bảng metadata lần đầu | Quyền tạo bảng trong schema metadata |
| Đọc lịch sử | SELECT trên bảng DATABASECHANGELOG |
| Ghi lịch sử | INSERT và các quyền cập nhật cần thiết |
| Điều phối lock | SELECT, INSERT, UPDATE và DELETE theo thao tác của Liquibase |
| Chạy changeset nghiệp vụ | Quyền DDL/DML tương ứng trên schema đích |

Quyền cụ thể phụ thuộc DBMS, cách Liquibase tạo bảng, cơ chế cấp quyền và changeset. Nên kiểm thử bằng đúng tài khoản mà pipeline hoặc ứng dụng sẽ dùng. Một lần chạy thành công bằng tài khoản DBA không chứng minh tài khoản migration production có đủ quyền.

Nếu schema metadata được quản lý bởi DBA, quy trình provisioning có thể tạo sẵn schema và cấp quyền cho migration role. Nếu tổ chức yêu cầu tạo sẵn cả bảng metadata, phải bảo đảm cấu trúc tương thích với phiên bản Liquibase và để Liquibase kiểm tra/khởi tạo lịch sử theo quy trình được hỗ trợ. Không tự thiết kế lại cột của hai bảng theo nhu cầu báo cáo.

## 7. Ví dụ triển khai với hai ứng dụng trong cùng database

Giả sử database commerce chứa hai ứng dụng độc lập: orders và billing. Mỗi ứng dụng có changelog, lịch phát hành và nhóm sở hữu riêng.

Cấu hình đề xuất:

| Thuộc tính | Orders | Billing |
|---|---|---|
| Metadata schema | platform_meta | platform_meta |
| History table | orders_liquibase_changelog | billing_liquibase_changelog |
| Lock table | orders_liquibase_lock | billing_liquibase_lock |
| Default schema | orders | billing |
| Migration role | orders_migrator | billing_migrator |

Với cấu hình này, lịch sử của hai ứng dụng tách biệt và lock của mỗi luồng cũng độc lập. Mỗi migration role chỉ nên được cấp quyền cần thiết trên schema metadata tương ứng và schema nghiệp vụ của ứng dụng.

Ví dụ properties cho Orders:

~~~properties
liquibaseSchemaName=platform_meta
defaultSchemaName=orders
databaseChangeLogTableName=orders_liquibase_changelog
databaseChangeLogLockTableName=orders_liquibase_lock
~~~

Ví dụ properties cho Billing:

~~~properties
liquibaseSchemaName=platform_meta
defaultSchemaName=billing
databaseChangeLogTableName=billing_liquibase_changelog
databaseChangeLogLockTableName=billing_liquibase_lock
~~~

Hai bộ cấu hình có thể chạy độc lập. Nếu một thay đổi cần tác động đồng thời đến cả hai schema, nhóm cần xác định chủ sở hữu migration và thứ tự triển khai. Việc chia bộ metadata không tự tạo transaction phân tán giữa các ứng dụng.

Nếu hai ứng dụng thực chất là một hệ thống dùng chung một changelog và một quy trình phát hành, một bộ metadata dùng chung có thể đơn giản hơn. Quyết định cần dựa trên ranh giới sở hữu, lịch phát hành, quyền truy cập và khả năng phối hợp vận hành.

## 8. Thay đổi tên hoặc vị trí bảng metadata đã tồn tại

Đổi tên bảng metadata là thao tác ảnh hưởng trực tiếp đến việc Liquibase nhận diện lịch sử. Ví dụ, database đã có DATABASECHANGELOG với nhiều changeset được ghi nhận. Một bản phát hành mới cấu hình orders_liquibase_changelog. Liquibase có thể tìm bảng mới, không thấy lịch sử cũ và xem các changeset như chưa được triển khai. Lần update tiếp theo có nguy cơ chạy lại các migration cũ.

Vì vậy, không thay đổi tên hoặc schema metadata chỉ bằng cách sửa một dòng cấu hình trong production. Hãy lập kế hoạch chuyển đổi có kiểm chứng:

1. Xác định chính xác tên bảng và schema hiện đang được mọi tiến trình sử dụng.
2. Dừng hoặc điều phối các tiến trình migration để không có lần cập nhật nào đang giữ lock.
3. Sao lưu database hoặc ít nhất hai bảng metadata cùng cấu trúc và thông tin cần thiết để phục hồi.
4. Xác định phương án chuyển đổi được DBMS hỗ trợ: đổi tên bảng, chuyển schema hoặc sao chép có kiểm soát. Giữ nguyên toàn bộ bản ghi lịch sử và cấu trúc cần thiết.
5. Xử lý cả bảng lock. Kiểm tra không còn lock đang hoạt động trước khi di chuyển; giữ trạng thái lock nhất quán và xác nhận cơ chế khóa mới.
6. Cập nhật đồng bộ cấu hình trong CLI, Spring Boot, pipeline, job vận hành và mọi instance có thể chạy Liquibase.
7. Chạy history, status --verbose và validate với cấu hình mới. Đối chiếu số lượng và nội dung lịch sử với bản sao lưu hoặc nguồn cũ.
8. Chạy update-sql để review changeset Liquibase dự kiến. Nếu kết quả bất ngờ liệt kê toàn bộ lịch sử cũ là pending, dừng và điều tra cấu hình metadata.
9. Sau khi kiểm chứng trên môi trường thử nghiệm, triển khai theo cửa sổ thay đổi đã phê duyệt và lưu lại bằng chứng.

Không tạo bảng metadata mới rỗng rồi dùng changelogSync để che đi việc mất lịch sử. changelogSync chỉ phù hợp với quy trình baseline có xác minh schema và nội dung tương ứng. Nó không thay thế việc di chuyển dữ liệu lịch sử từ bảng cũ.

Nếu cần giữ tương thích trong giai đoạn chuyển đổi, xác định rõ phiên bản cấu hình nào được phép chạy và tránh để hai tiến trình cùng cập nhật một database bằng hai bộ tên khác nhau.

## 9. Kiểm tra vị trí và tên bảng sau cấu hình

Sau khi cấu hình, hãy xác minh bằng cả Liquibase và catalog của DBMS. Với PostgreSQL, có thể kiểm tra sự tồn tại và vị trí bảng bằng truy vấn:

~~~sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_name IN (
    'orders_liquibase_changelog',
    'orders_liquibase_lock'
)
ORDER BY table_schema, table_name;
~~~

Đọc một phần lịch sử để xác nhận Liquibase đang ghi vào đúng bảng:

~~~sql
SELECT id, author, filename, dateexecuted, orderexecuted, exectype
FROM platform_meta.orders_liquibase_changelog
ORDER BY orderexecuted;
~~~

Kiểm tra trạng thái lock bằng truy vấn chỉ đọc:

~~~sql
SELECT *
FROM platform_meta.orders_liquibase_lock;
~~~

Tên cột của bảng lock và kiểu dữ liệu có thể phụ thuộc phiên bản Liquibase và DBMS. Dùng SELECT * trong ví dụ kiểm tra giúp quan sát cấu trúc thực tế; các thao tác quản trị lock nên đi qua cơ chế Liquibase được hỗ trợ.

Sau khi xác nhận vị trí vật lý, chạy các lệnh kiểm tra bằng đúng cấu hình dùng khi triển khai:

~~~bash
liquibase validate
liquibase history
liquibase status --verbose
liquibase update-sql
~~~

Kết quả cần thể hiện rằng Liquibase tìm được lịch sử dự kiến, không tạo thêm một bộ bảng metadata ngoài ý muốn và không coi changeset cũ là pending. update-sql giúp xem trước tác động; chỉ thực hiện update sau khi đã review và xác nhận database đích.

### 9.1. Kiểm tra theo DBMS

Cách truy vấn catalog khác nhau theo hệ quản trị:

| DBMS | Nguồn metadata thường dùng | Điều cần xác nhận |
|---|---|---|
| PostgreSQL | information_schema.tables, pg_catalog | Schema, tên bảng, owner và quyền |
| MySQL | information_schema.tables | Database/catalog và tên bảng |
| Oracle | USER_TABLES, ALL_TABLES, DBA_TABLES | Owner/schema, tên bảng và quyền nhìn thấy |
| SQL Server | sys.tables, sys.schemas | Schema, tên bảng và principal sở hữu/quyền |

Tên mặc định và cách database chuyển đổi chữ hoa/thường phụ thuộc DBMS. Khi cấu hình identifier có dấu nháy hoặc tên chứa ký tự đặc biệt, hãy kiểm tra cách Liquibase tạo câu lệnh và cách catalog lưu tên.

## 10. Lỗi cấu hình thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Liquibase tạo DATABASECHANGELOG trong schema không dự kiến | Thiếu liquibaseSchemaName hoặc kết nối dùng default schema khác | Kiểm tra URL, user, current schema và cấu hình metadata |
| Liquibase báo không tìm thấy bảng lịch sử rồi tạo bảng mới | Tên bảng hoặc schema giữa các lần chạy không nhất quán | So sánh tham số CLI, properties, Spring profile và pipeline |
| Các changeset cũ xuất hiện pending hàng loạt | Liquibase đang đọc một bảng lịch sử mới/rỗng | Dừng update; tìm bảng lịch sử gốc và xác minh cấu hình |
| Lỗi quyền khi khởi tạo bảng | Migration role thiếu quyền tạo bảng hoặc thao tác trên schema metadata | Kiểm tra quyền schema, owner và grants |
| Lỗi quyền khi chạy lần tiếp theo | Tài khoản có quyền tạo bảng nhưng thiếu quyền đọc/ghi lịch sử hoặc lock | Kiểm tra SELECT/INSERT/UPDATE/DELETE và quyền thực tế |
| Hai ứng dụng chờ lock lâu | Dùng chung lock table hoặc tiến trình khác đang chạy migration | Xác định tiến trình giữ lock, thời gian chờ và ranh giới luồng |
| Bảng metadata bị tạo trùng ở nhiều schema | Các tiến trình kết nối bằng user/schema khác nhau hoặc cấu hình thiếu nhất quán | Kiểm tra catalog, schema và cấu hình hiệu lực của từng tiến trình |
| Tên bảng không được DBMS chấp nhận | Tên dài, từ khóa SQL, quy tắc chữ hoa/thường hoặc identifier quoting | Chọn tên đơn giản, kiểm tra giới hạn DBMS và truy vấn catalog |

Khi gặp lỗi lock, xác định tiến trình đang giữ lock và log triển khai trước. Không tự đặt LOCKED=false, xóa dòng lock hoặc xóa bảng lock trong lúc một migration có thể còn chạy. Nếu lock thực sự bị bỏ lại sau khi tiến trình kết thúc bất thường, dùng lệnh release-locks theo hướng dẫn Liquibase sau khi đã xác nhận không có tiến trình cập nhật đang hoạt động.

## 11. Nguyên tắc vận hành cho nhiều môi trường và CI/CD

Một cấu hình metadata nên được quản lý như một phần của cấu hình migration có version. Dev, test, staging và production cần cùng quy ước tên bảng và schema trong cùng một database logic; URL, credentials và schema nghiệp vụ có thể thay đổi theo môi trường.

Trong pipeline:

1. Nạp cấu hình kết nối và tên bảng metadata từ một nguồn cấu hình có kiểm soát.
2. Xác nhận database đích, catalog, schema metadata và schema nghiệp vụ.
3. Chạy validate, history và status --verbose bằng cùng bộ tham số sẽ dùng cho migration.
4. Review update-sql, xác nhận các changeset pending phù hợp với bản phát hành.
5. Chạy migration bằng một job hoặc một tiến trình được chỉ định.
6. Xác nhận bảng lịch sử được cập nhật tại đúng schema và lock đã được giải phóng.
7. Lưu log, phiên bản changelog và thông tin môi trường phục vụ kiểm toán.

Với Spring Boot nhiều replica, nếu mỗi instance đều bật Liquibase, tất cả phải nhận cùng tên bảng và vị trí metadata. Liquibase lock giúp điều phối, nhưng việc tập trung migration vào một bước triển khai chuyên trách thường giúp quyền và lịch sử dễ kiểm soát hơn. Nếu pipeline đã chạy migration trước khi ứng dụng khởi động, cân nhắc tắt Liquibase tự động trong các instance runtime theo cấu hình của dự án.

Không dùng tên bảng khác nhau theo từng lần chạy ngẫu nhiên hoặc theo tên máy. Không để profile production và pipeline production có cấu hình metadata khác nhau. Nếu một thay đổi tên/schema là cần thiết, quản lý nó như một migration vận hành riêng có backup, thời điểm chuyển đổi và bước xác minh.

## 12. Checklist trước khi đưa cấu hình vào production

- [ ] Tên bảng lịch sử và bảng lock đã được thống nhất và ghi lại.
- [ ] Hai bảng được đặt trong schema/catalog dự kiến.
- [ ] liquibaseSchemaName và defaultSchemaName đã được phân biệt đúng mục đích.
- [ ] Các tiến trình CLI, Spring Boot và CI/CD dùng cùng bộ tham số metadata.
- [ ] Schema metadata đã tồn tại hoặc có quy trình tạo được kiểm soát.
- [ ] Migration role có đủ quyền trên schema metadata và schema nghiệp vụ.
- [ ] Runtime role chỉ có quyền cần thiết cho ứng dụng.
- [ ] Tên bảng tương thích giới hạn identifier và quy tắc chữ hoa/thường của DBMS.
- [ ] history, status --verbose và validate cho kết quả đúng trên database đích.
- [ ] update-sql không cho thấy việc chạy lại các changeset đã triển khai.
- [ ] Bảng lock không còn trạng thái giữ khóa sau khi migration kết thúc bình thường.
- [ ] Backup và quy trình phục hồi đã được chuẩn bị trước khi đổi tên hoặc di chuyển bảng metadata.
- [ ] Log và bằng chứng kiểm tra được lưu cùng phiên bản changelog.

## 13. Kết luận

Tên và vị trí của **DATABASECHANGELOG** và **DATABASECHANGELOGLOCK** xác định nơi Liquibase lưu lịch sử và phối hợp các lần cập nhật. Hãy chọn tên ổn định theo ứng dụng hoặc luồng migration, đặt bảng ở schema quản trị phù hợp, và cấu hình rõ liquibaseSchemaName, liquibaseCatalogName, databaseChangeLogTableName cùng databaseChangeLogLockTableName.

Đồng thời, giữ riêng khái niệm schema metadata với defaultSchemaName của đối tượng nghiệp vụ. Mọi thay đổi tên hoặc vị trí bảng đã có lịch sử cần được chuyển đổi có kiểm chứng, cập nhật đồng bộ trong CLI, Spring Boot và CI/CD, rồi xác nhận lại bằng lịch sử Liquibase và catalog của database.
