# Phân biệt catalog, schema mặc định và schema lưu bảng theo dõi

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, cấu hình catalog và schema quyết định Liquibase định vị các đối tượng trong cơ sở dữ liệu như thế nào. Ba khái niệm cần tách bạch là **catalog**, **schema mặc định** và **schema lưu bảng theo dõi của Liquibase**. Chúng có quan hệ với nhau nhưng không cùng một vai trò: catalog xác định phạm vi cơ sở dữ liệu theo cách hệ quản trị định nghĩa; schema mặc định là nơi Liquibase tìm hoặc tạo các đối tượng của ứng dụng khi changeset không chỉ rõ schema; còn schema lưu bảng theo dõi là nơi Liquibase ghi lịch sử và khóa điều phối migration.

Cấu hình nhầm các giá trị này có thể khiến migration tạo bảng sai nơi, ứng dụng không tìm thấy bảng, Liquibase tạo một bộ lịch sử mới rồi chạy lại changeset, hoặc nhiều môi trường không thống nhất cách quản lý schema. Bài học này trình bày cách phân biệt, cấu hình và kiểm chứng ba vị trí đó khi dùng Liquibase độc lập hoặc tích hợp Spring Boot và CI/CD.

## 1. Catalog và schema là hai cấp định vị khác nhau

Một hệ quản trị cơ sở dữ liệu thường tổ chức đối tượng theo nhiều cấp. Catalog và schema là hai tên gọi thường gặp trong metadata SQL/JDBC, nhưng ý nghĩa chính xác phụ thuộc vào hệ quản trị.

Có thể hình dung một cấu trúc phổ biến như sau:

~~~text
Database server
└── Catalog (thường tương ứng database)
    └── Schema (namespace trong catalog)
        ├── Table
        ├── View
        ├── Sequence
        └── Stored procedure
~~~

Ví dụ, một hệ thống bán hàng có catalog tên **orders** và các schema **sales**, **inventory**, **audit**. Bảng **customer** có thể nằm trong **orders.sales**, còn bảng ghi sự kiện nằm trong **orders.audit**. Khi viết tên đầy đủ, hệ quản trị có thể dùng cú pháp như **catalog.schema.table**, nhưng dấu phân cách, quy tắc viết hoa và khả năng tham chiếu chéo catalog khác nhau giữa các sản phẩm.

**Catalog** thường là phạm vi chứa các schema hoặc database. Trên SQL Server, catalog thường tương ứng với database. Trên PostgreSQL, một kết nối làm việc trong một database; schema là namespace bên trong database đó. Trên MySQL, thuật ngữ database và schema thường được dùng gần như đồng nghĩa, đồng thời JDBC thường biểu diễn database hiện tại như catalog. Oracle thường dùng schema để chỉ tập đối tượng thuộc một user/owner; database hoặc service được xác định qua cấu hình kết nối, và catalog không đóng vai trò namespace độc lập giống SQL Server.

| Hệ quản trị | Cách hiểu thường gặp | Ví dụ |
|---|---|---|
| PostgreSQL | Catalog thường là database; schema là namespace trong database | database **orders**, schema **sales** |
| SQL Server | Catalog thường là database; schema phân nhóm đối tượng trong database | database **orders**, schema **sales** hoặc **dbo** |
| MySQL | Database và schema thường là hai cách gọi cùng phạm vi; JDBC thường trả database hiện tại ở catalog | database/schema **orders** |
| Oracle | Schema thường gắn với user/owner; database/service nằm ở tầng kết nối | user/schema **SALES** trong service **ORDERSDB** |

Bảng này là cách định hướng khái niệm, không phải quy tắc chuyển đổi tên dùng chung cho mọi driver. Khi cấu hình thực tế, cần căn cứ vào hệ quản trị, phiên bản Liquibase, JDBC driver và cách database ánh xạ metadata catalog/schema. Không nên mặc định rằng một giá trị tên schema trên hệ quản trị này sẽ tương ứng chính xác với trường schema trên hệ quản trị khác.

## 2. Schema mặc định dùng cho đối tượng của ứng dụng

Liquibase có thể tạo bảng, cột, view, sequence và các đối tượng khác thông qua changeset. Nếu changeset không chỉ rõ schema cho một đối tượng, Liquibase cần một giá trị mặc định để xác định nơi thực hiện thay đổi.

Tham số **defaultSchemaName** cung cấp schema mặc định đó. Tham số **defaultCatalogName** cung cấp catalog mặc định khi hệ quản trị và thao tác tương ứng có sử dụng catalog. Hai giá trị này định hướng đối tượng mà changelog quản lý; chúng không phải vị trí lưu lịch sử migration.

Ví dụ, nhóm muốn các bảng nghiệp vụ mặc định nằm trong schema **sales**, trong catalog **orders**. Với Liquibase properties:

~~~properties
url=jdbc:sqlserver://localhost:1433;databaseName=orders
username=liquibase_user
password=<secret được cấp qua môi trường>
defaultCatalogName=orders
defaultSchemaName=sales
~~~

Trong cấu hình này, URL kết nối xác định database mà phiên làm việc hướng tới. **defaultCatalogName** và **defaultSchemaName** cung cấp mặc định để Liquibase định vị các đối tượng trong changelog. Tên catalog phải phù hợp với khả năng của hệ quản trị và quyền của tài khoản kết nối.

Một changeset có thể ghi rõ schema cho đối tượng quan trọng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: create-customer
      author: platform
      changes:
        - createTable:
            catalogName: orders
            schemaName: sales
            tableName: customer
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: VARCHAR(255)
                  constraints:
                    nullable: false
~~~

Khi change khai báo **catalogName** hoặc **schemaName**, Liquibase dùng phạm vi được chỉ định cho change đó thay vì chỉ dựa vào giá trị mặc định. Đây là cách hữu ích khi một changelog quản lý nhiều schema, ví dụ vừa tạo bảng nghiệp vụ trong **sales**, vừa tạo bảng kiểm toán trong **audit**.

Cần lưu ý rằng tên catalog/schema được ghi trong changelog phải tồn tại hoặc được tạo bằng một bước phù hợp trước khi Liquibase sử dụng chúng. **defaultSchemaName** không nên được hiểu là lệnh tự tạo schema. Tài khoản triển khai cũng cần đủ quyền tạo và thay đổi đối tượng tại vị trí đích.

## 3. Schema lưu bảng theo dõi của Liquibase

Liquibase lưu lịch sử migration trong các bảng quản lý riêng. Hai bảng quan trọng nhất là:

- **DATABASECHANGELOG**: lưu changeset đã được ghi nhận, gồm định danh, thời điểm thực thi, loại thực thi và checksum.
- **DATABASECHANGELOGLOCK**: quản lý khóa để ngăn các tiến trình Liquibase cập nhật cùng một database đồng thời theo cách gây xung đột.

Hai bảng này không phải bảng nghiệp vụ. Chúng là metadata để Liquibase biết migration nào đã chạy và có tiến trình nào đang giữ quyền cập nhật hay không.

Tham số **liquibaseSchemaName** chỉ định schema đặt các bảng theo dõi của Liquibase. Tham số **liquibaseCatalogName** chỉ định catalog đặt các bảng này khi hệ quản trị hỗ trợ cấu hình catalog riêng. Có thể tùy chỉnh tên bảng thông qua các tham số như **databaseChangeLogTableName** và **databaseChangeLogLockTableName**, nhưng việc đổi tên bảng cũng phải được quản lý nhất quán giữa các lần triển khai.

Ví dụ, nhóm muốn bảng nghiệp vụ nằm trong **sales**, còn lịch sử migration nằm trong **liquibase_meta**:

~~~properties
defaultCatalogName=orders
defaultSchemaName=sales
liquibaseCatalogName=orders
liquibaseSchemaName=liquibase_meta
~~~

Kết quả mong muốn trên hệ quản trị hỗ trợ cấu trúc catalog/schema này:

~~~text
orders
├── sales
│   └── customer
└── liquibase_meta
    ├── DATABASECHANGELOG
    └── DATABASECHANGELOGLOCK
~~~

Hai schema có thể nằm trong cùng một catalog. Việc tách riêng giúp phân quyền rõ ràng và tránh trộn metadata triển khai với đối tượng nghiệp vụ. Tuy nhiên, đây là lựa chọn kiến trúc, không phải yêu cầu bắt buộc. Với một ứng dụng nhỏ, nhóm có thể đặt bảng theo dõi và bảng nghiệp vụ trong cùng schema nếu điều đó phù hợp với chính sách vận hành.

Schema chứa bảng theo dõi cần được chuẩn bị trước khi chạy Liquibase nếu hệ quản trị hoặc cấu hình không tự tạo schema đó. Tài khoản Liquibase phải có quyền truy cập và tạo/cập nhật bảng trong schema này. Tài khoản ứng dụng runtime có thể chỉ cần quyền đọc/ghi trên schema nghiệp vụ, không nhất thiết được phép sửa bảng lịch sử migration.

## 4. Phân biệt ba cấu hình bằng câu hỏi vận hành

Ba tham số thường bị nhầm lẫn vì đều chứa từ catalog hoặc schema. Hãy gắn mỗi tham số với câu hỏi mà nó trả lời:

| Cấu hình | Câu hỏi | Đối tượng chịu tác động |
|---|---|---|
| **defaultCatalogName** | Nếu change không chỉ catalog, Liquibase dùng catalog nào làm mặc định? | Đối tượng database được quản lý bởi changeset |
| **defaultSchemaName** | Nếu change không chỉ schema, Liquibase dùng schema nào làm mặc định? | Bảng, view, sequence và đối tượng ứng dụng |
| **liquibaseCatalogName** | Catalog nào chứa các bảng quản lý của Liquibase? | DATABASECHANGELOG và DATABASECHANGELOGLOCK |
| **liquibaseSchemaName** | Schema nào chứa các bảng quản lý của Liquibase? | DATABASECHANGELOG và DATABASECHANGELOGLOCK |

Nếu **defaultSchemaName=sales** và **liquibaseSchemaName=liquibase_meta**, một changeset tạo bảng **customer** không chỉ schema sẽ hướng đến **sales.customer**, trong khi lịch sử migration được lưu ở **liquibase_meta.DATABASECHANGELOG**. Hai cấu hình có thể trùng nhau nếu nhóm muốn dùng chung một schema.

Đặt **liquibaseSchemaName** không có nghĩa là thay đổi schema mặc định của ứng dụng. Ngược lại, đặt **defaultSchemaName** không tự chuyển bảng DATABASECHANGELOG sang schema đó. Khi cần tách riêng vị trí, phải cấu hình cả hai tham số.

## 5. Cấu hình trong Liquibase CLI và file properties

Với Liquibase CLI, có thể đặt các giá trị trong **liquibase.properties**:

~~~properties
url=jdbc:sqlserver://db.example.internal:1433;databaseName=orders
username=liquibase_user
password=<secret được cấp qua môi trường>
defaultCatalogName=orders
defaultSchemaName=sales
liquibaseCatalogName=orders
liquibaseSchemaName=liquibase_meta
changeLogFile=db/changelog/db.changelog-master.yaml
~~~

Hoặc truyền các tham số tương ứng khi chạy lệnh CLI:

~~~bash
liquibase \
  --default-catalog-name=orders \
  --default-schema-name=sales \
  --liquibase-catalog-name=orders \
  --liquibase-schema-name=liquibase_meta \
  update
~~~

Tên tham số và cách nạp cấu hình cần khớp với phiên bản Liquibase mà dự án sử dụng. Không nên đặt mật khẩu trực tiếp trong file được commit vào Git. Hãy dùng biến môi trường, secret store của CI/CD hoặc cơ chế cấp thông tin xác thực được tổ chức phê duyệt.

Nếu ứng dụng dùng database mà catalog không phải một cấp độc lập hoặc không hỗ trợ chuyển catalog trong cùng kết nối, chỉ cấu hình catalog khi cần và khi driver/hệ quản trị hỗ trợ. Đặc biệt, **defaultCatalogName** không thay thế URL kết nối, tên database trong URL hay thông tin xác thực. Cấu hình một catalog khác không tự mở kết nối mới tới một database khác.

## 6. Cấu hình trong Spring Boot

Spring Boot cung cấp các thuộc tính Liquibase phổ biến để đặt changelog, schema mặc định và schema chứa bảng theo dõi. Ví dụ:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: app_user
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
    default-schema: sales
    liquibase-schema: liquibase_meta
~~~

Trong ví dụ này:

- **spring.liquibase.default-schema** đặt schema mặc định cho các thay đổi của changelog.
- **spring.liquibase.liquibase-schema** đặt schema lưu bảng DATABASECHANGELOG và DATABASECHANGELOGLOCK.
- **spring.datasource.url** xác định database mà ứng dụng kết nối tới; ví dụ PostgreSQL đang kết nối database **orders**.

Tên thuộc tính Spring Boot có thể khác cách viết tên tham số trong Liquibase CLI. Không tự suy ra rằng mọi tham số **defaultCatalogName** hoặc **liquibaseCatalogName** đều có một thuộc tính **spring.liquibase.*** tương ứng trong mọi phiên bản Spring Boot. Nếu cần cấu hình catalog, hãy kiểm tra metadata cấu hình của đúng phiên bản Spring Boot/Liquibase đang dùng và truyền tham số qua cơ chế Liquibase được phiên bản đó hỗ trợ.

Trong môi trường nhiều giai đoạn, có thể đưa tên schema vào profile hoặc cấu hình bên ngoài:

~~~yaml
spring:
  liquibase:
    default-schema: sales
    liquibase-schema: liquibase_meta
~~~

Giá trị mặc định ở trên phù hợp với ví dụ minh họa. Development, staging và production có thể dùng tên schema khác nhau theo quy ước của tổ chức, nhưng phải bảo đảm mọi cấu hình trỏ đúng database và đúng đối tượng lịch sử đã tồn tại.

## 7. Ảnh hưởng của schema mặc định trong SQL và quyền của tài khoản

Cần phân biệt cách Liquibase định vị đối tượng trong các change có cấu trúc với cách database phân giải tên trong câu SQL thuần.

Với các change có thuộc tính schema/catalog, Liquibase có thông tin để tạo đối tượng tại vị trí đã chỉ định hoặc tại vị trí mặc định. Nhưng trong một changeset dùng **sql** hoặc **sqlFile**, câu lệnh SQL có thể chứa tên bảng không ghi schema:

~~~sql
UPDATE customer
SET status = 'ACTIVE'
WHERE status IS NULL;
~~~

Tên **customer** không được định vị giống nhau trên mọi database. Database có thể dùng schema mặc định của user, search path hoặc cấu hình session để tìm bảng. Vì vậy, việc đặt **defaultSchemaName** trong Liquibase không nên được coi là bảo đảm rằng mọi tên không đầy đủ trong SQL tùy ý sẽ được viết lại thành tên có schema.

Với SQL quan trọng hoặc changelog dùng nhiều schema, nên ghi rõ tên schema theo cú pháp của hệ quản trị:

~~~sql
UPDATE sales.customer
SET status = 'ACTIVE'
WHERE status IS NULL;
~~~

Đây là ví dụ cú pháp phổ biến, cần điều chỉnh theo hệ quản trị và quy tắc định danh của database đích.

Quyền truy cập cũng cần được xét riêng cho hai vị trí:

- Trên schema nghiệp vụ, Liquibase cần quyền tạo hoặc thay đổi các đối tượng do changeset quản lý.
- Trên schema metadata, Liquibase cần quyền đọc, tạo và cập nhật các bảng theo dõi cũng như khóa.
- Ứng dụng runtime chỉ nên nhận quyền cần thiết để thực hiện chức năng nghiệp vụ; không nên cấp quyền quản trị schema hoặc sửa lịch sử migration nếu không cần.

Nếu nhóm dùng tài khoản triển khai khác tài khoản chạy ứng dụng, hãy xác nhận cả hai tài khoản có quyền đúng trên các schema tương ứng. Tránh xử lý lỗi thiếu quyền bằng cách cấp quyền quản trị rộng trên toàn database.

## 8. Khác biệt theo hệ quản trị và các bẫy thường gặp

### PostgreSQL

PostgreSQL tổ chức schema bên trong database. Một kết nối làm việc với một database tại một thời điểm; schema như **public**, **sales** hoặc **liquibase_meta** là namespace trong database đó. Có thể dùng **defaultSchemaName** để định hướng đối tượng ứng dụng và **liquibaseSchemaName** để tách bảng theo dõi. Cần bảo đảm schema metadata tồn tại và user Liquibase có quyền phù hợp. Ngoài ra, **search_path** của session có thể ảnh hưởng cách database tìm đối tượng trong SQL không ghi schema đầy đủ.

### SQL Server

SQL Server phân biệt database (catalog) và schema. Một database có thể có các schema **dbo**, **sales**, **audit**. Tài khoản kết nối thường có database mặc định và user có schema mặc định; cấu hình Liquibase cần thống nhất với database trong JDBC URL. Đặt **defaultSchemaName=sales** không tự tạo schema **sales** hoặc cấp quyền cho user.

### MySQL

MySQL thường xem database và schema là tương đương. Driver JDBC có thể biểu diễn database hiện tại như catalog thay vì schema. Vì thế, khi cấu hình **defaultCatalogName** hoặc **defaultSchemaName**, cần kiểm tra hành vi của phiên bản Liquibase và driver đang dùng. Không sao chép cấu hình SQL Server hoặc PostgreSQL sang MySQL mà chưa xác minh cách ánh xạ.

### Oracle

Trong Oracle, schema thường gắn với user sở hữu đối tượng. Tên schema có thể trùng với tên user, và user triển khai cần quyền phù hợp để tạo đối tượng trong schema của mình hoặc schema khác. Database/service được xác định bởi cấu hình kết nối; không nên xem **liquibaseSchemaName** như tên service hoặc database. Cần kiểm tra quy tắc owner và quyền khi tách schema ứng dụng với schema metadata.

Một số lỗi vận hành thường gặp:

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Bảng nghiệp vụ xuất hiện trong public hoặc dbo thay vì schema mong muốn | Chưa đặt defaultSchemaName, cấu hình không được nạp hoặc SQL dùng tên không đầy đủ | Kiểm tra cấu hình thực tế, change có schemaName và schema mặc định của session |
| DATABASECHANGELOG được tạo trong schema khác | Chưa đặt liquibaseSchemaName hoặc tham số không được áp dụng | Truy vấn metadata để xác định vị trí bảng theo dõi |
| Liquibase báo không tìm thấy bảng lịch sử rồi tạo bảng mới ở nơi khác | Cấu hình vị trí tracking khác với nơi lịch sử hiện tại đang lưu | Xác minh catalog/schema và cấu hình của môi trường trước khi update |
| Migration thất bại vì không có quyền | User Liquibase thiếu quyền trên schema nghiệp vụ hoặc metadata | Kiểm tra quyền riêng cho từng schema |
| Development chạy được nhưng production tạo bảng sai nơi | Giá trị mặc định, user mặc định hoặc search_path khác nhau | So sánh URL, cấu hình Liquibase và quyền của tài khoản ở từng môi trường |

## 9. Thay đổi vị trí bảng theo dõi cần bảo toàn lịch sử

Một rủi ro lớn là đổi **liquibaseSchemaName** sau khi dự án đã triển khai. Giả sử lịch sử hiện nằm ở **public.DATABASECHANGELOG**, nhưng cấu hình mới chuyển sang **liquibase_meta**. Nếu Liquibase không tìm thấy bảng lịch sử tại vị trí mới, nó có thể coi database chưa có lịch sử migration và chuẩn bị tạo bộ bảng theo dõi mới. Khi chạy update, các changeset cũ có thể bị xem như chưa triển khai, dẫn tới lỗi đối tượng đã tồn tại hoặc dữ liệu bị xử lý lặp.

Vì vậy, chuyển vị trí bảng theo dõi phải được xem là một thay đổi vận hành có kế hoạch:

1. Xác định chính xác catalog/schema hiện đang chứa DATABASECHANGELOG và DATABASECHANGELOGLOCK.
2. Sao lưu database hoặc ít nhất bảo đảm có bản sao khôi phục được của các bảng metadata.
3. Kiểm tra phiên bản Liquibase, cấu hình hiện tại, quyền user và vị trí đích.
4. Lập phương án di chuyển hai bảng metadata sang vị trí mới theo khả năng của hệ quản trị; bảo toàn đầy đủ nội dung và cấu trúc cần thiết.
5. Cập nhật cấu hình để Liquibase trỏ đúng vị trí mới.
6. Chạy validation và kiểm tra lịch sử bằng cùng artifact, sau đó xác minh Liquibase nhận diện các changeset cũ là đã triển khai.
7. Chỉ tiếp tục migration mới khi lịch sử và trạng thái schema đã được xác nhận nhất quán.

Không xóa bảng lịch sử cũ chỉ vì muốn Liquibase tạo lại bảng ở schema mới. Không dùng **changelogSync** hoặc thao tác sửa trực tiếp metadata để che đi việc Liquibase đang trỏ sai vị trí. Nếu có nhiều môi trường, hãy diễn tập quy trình chuyển đổi trên bản sao database trước khi thực hiện ở môi trường dùng chung.

## 10. Nhiều schema, nhiều tenant và nhiều môi trường

Một database có thể chứa nhiều schema phục vụ các nhóm nghiệp vụ khác nhau. Nếu một Liquibase execution quản lý nhiều schema, changeset cần xác định rõ đối tượng thuộc schema nào. Có thể đặt mặc định cho schema chính và chỉ rõ schema cho các change đặc biệt. Điều quan trọng là mỗi thay đổi phải có phạm vi rõ ràng, tránh dựa vào schema mặc định ngầm khác nhau giữa các môi trường.

Với mô hình multi-tenant, mỗi tenant có schema riêng, cần xác định lịch sử migration được theo dõi như thế nào. Nếu các tenant có vòng đời cập nhật độc lập, mỗi tenant thường cần một phạm vi lịch sử tương ứng, chẳng hạn bộ bảng DATABASECHANGELOG riêng trong schema của tenant hoặc một chiến lược metadata được thiết kế để nhận diện tenant rõ ràng. Nếu nhiều tenant dùng chung một bảng lịch sử mà changeset chỉ được ghi nhận một lần, Liquibase có thể không chạy cùng changeset cho các schema còn lại như mong muốn. Không nên dùng chung một lịch sử mà không xác định rõ mô hình thực thi.

Trong CI/CD, cùng một artifact changelog nên được triển khai tuần tự qua các môi trường. Mỗi môi trường có thể cấu hình catalog/schema theo quy ước riêng, nhưng phải bảo đảm:

- Đường kết nối trỏ tới đúng database.
- Schema mặc định của đối tượng nghiệp vụ được xác định rõ.
- Schema/catalog metadata trỏ đúng các bảng lịch sử đã tồn tại.
- Tài khoản migration có đủ quyền trên cả hai vị trí.
- Các bước kiểm tra xác nhận bảng được tạo đúng schema và lịch sử được ghi đúng nơi.
- Không có nhiều tiến trình Liquibase cạnh tranh cập nhật cùng một database.

Cấu hình tách biệt theo môi trường nên được quản lý qua profile, biến môi trường hoặc secret/config store của nền tảng triển khai. Tránh sửa changelog theo môi trường chỉ để đổi vị trí schema; dùng cấu hình và tham số triển khai để giữ cùng một nội dung migration có thể truy nguyên.

## 11. Quy trình kiểm chứng cấu hình

Trước khi chạy update trên database dùng chung, hãy kiểm tra cấu hình theo thứ tự sau:

1. **Xác minh kết nối:** đọc JDBC URL, database/service, user và driver. Đảm bảo catalog mà cấu hình chỉ định có thể truy cập từ kết nối đó.
2. **Xác minh schema nghiệp vụ:** kiểm tra schema mặc định tồn tại, đúng tên và user Liquibase có quyền cần thiết.
3. **Xác minh schema metadata:** kiểm tra vị trí DATABASECHANGELOG và DATABASECHANGELOGLOCK hiện tại; nếu chưa có, xác nhận schema đích và quyền tạo bảng.
4. **Xác minh cấu hình hiệu lực:** kiểm tra file properties, tham số CLI, biến môi trường và thuộc tính Spring Boot để biết giá trị nào thực sự được nạp.
5. **Xem SQL dự kiến:** dùng **update-sql** trên đúng cấu hình và database đích để xem câu lệnh Liquibase sẽ thực hiện.
6. **Kiểm tra trạng thái:** chạy **status --verbose** và **validate**; xác nhận Liquibase nhận ra lịch sử hiện tại và chỉ liệt kê changeset dự kiến.
7. **Thử nghiệm:** chạy trên database mới và một bản sao database đã có lịch sử để kiểm tra cả cài đặt ban đầu lẫn nâng cấp.

Ví dụ một nhóm lệnh kiểm tra CLI:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
~~~

Các lệnh trên cần dùng cùng bộ cấu hình kết nối và catalog/schema với lần triển khai thật. **update-sql** giúp xem trước SQL nhưng không thay thế việc kiểm tra quyền, khả năng tương thích của hệ quản trị hay thử nghiệm trên bản sao database.

Với hệ quản trị hỗ trợ information schema, có thể truy vấn metadata để xác định vị trí các bảng theo dõi. Ví dụ tổng quát sau cần điều chỉnh theo database:

~~~sql
SELECT
    TABLE_CATALOG,
    TABLE_SCHEMA,
    TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_NAME IN (
    'DATABASECHANGELOG',
    'DATABASECHANGELOGLOCK'
);
~~~

Một số hệ quản trị không cung cấp đầy đủ các cột giống nhau trong INFORMATION_SCHEMA hoặc dùng view metadata riêng. Hãy sử dụng catalog view phù hợp, chẳng hạn view hệ thống của SQL Server, PostgreSQL hoặc Oracle. Mục tiêu là xác nhận bảng lịch sử và bảng khóa thực sự nằm ở catalog/schema nào, không chỉ dựa vào cấu hình đã khai báo.

## 12. Checklist trước khi phát hành

Trước khi đưa cấu hình Liquibase vào một môi trường mới hoặc thay đổi vị trí metadata, hãy xác nhận:

- Đã phân biệt catalog với schema theo đúng hệ quản trị và JDBC driver.
- Đã xác định database/service qua URL kết nối và hiểu rõ phạm vi mà catalog đang đại diện.
- Đã đặt defaultCatalogName/defaultSchemaName cho các đối tượng ứng dụng khi cần.
- Đã đặt liquibaseCatalogName/liquibaseSchemaName cho bảng DATABASECHANGELOG và DATABASECHANGELOGLOCK khi cần tách vị trí.
- Đã kiểm tra thuộc tính Spring Boot có thực sự được hỗ trợ ở phiên bản dự án đang dùng.
- Schema đích đã tồn tại và user Liquibase có quyền phù hợp.
- SQL thuần trong changeset đã được rà soát để tránh phụ thuộc ngoài ý muốn vào search_path hoặc schema mặc định của user.
- Đã xác minh Liquibase nhận diện đúng lịch sử hiện tại, đặc biệt khi chuyển schema lưu bảng theo dõi.
- Đã thử cả database mới và database nâng cấp, đồng thời xem trước SQL dự kiến.

Catalog, schema mặc định và schema lưu bảng theo dõi giải quyết ba nhu cầu định vị khác nhau trong quá trình thực thi migration. Khi cấu hình rõ ràng, Liquibase có thể tạo đối tượng ứng dụng đúng nơi, ghi lịch sử vào vị trí được quản lý riêng và duy trì hành vi nhất quán giữa các môi trường. Đây là nền tảng để kiểm soát thay đổi schema và dữ liệu, phối hợp migration với Spring Boot hoặc CI/CD và bảo toàn lịch sử triển khai lâu dài.

