# Phạm vi, thứ tự khai báo và ưu tiên của thuộc tính trong Liquibase

## 1. Vấn đề cần giải quyết

Liquibase cho phép dùng **thuộc tính (property)** hoặc **tham số changelog (changelog parameter)** để tái sử dụng các giá trị như tên schema, tên bảng, loại dữ liệu và hằng số kỹ thuật. Thay vì viết tên schema cố định vào nhiều changeset, ta khai báo một lần rồi tham chiếu bằng cú pháp <code>${ten.thuoc.tinh}</code>. Cách này giảm lặp, giúp áp dụng cùng một changelog cho những môi trường được thiết kế tương thích.

Tuy nhiên, tham số hóa tạo thêm ba câu hỏi cần trả lời rõ:

1. **Phạm vi:** thuộc tính được sử dụng ở changelog nào, môi trường nào, DBMS nào? Thuộc tính trong changelog cha có nhìn thấy ở changelog con không?
2. **Thứ tự:** nếu một thuộc tính được khai báo ở nhiều vị trí, khai báo trước hay sau lời gọi <code>include</code> có ảnh hưởng gì?
3. **Ưu tiên:** khi cùng một tên được cấp từ CLI, tệp cấu hình, Spring Boot và changelog, Liquibase dùng giá trị nào?

Bài này thuộc chương **Tham số hóa** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Toàn bộ module hướng đến quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Hiểu đúng phạm vi và ưu tiên thuộc tính là điều kiện quan trọng để migration có thể lặp lại và được kiểm chứng ở mọi môi trường.

**Mục tiêu:** sau khi học, người đọc có thể xây dựng sơ đồ nguồn giá trị cho một thuộc tính, dự đoán giá trị được thay thế trong SQL, ngăn khai báo trùng vô ý, và xác minh bộ tham số thực tế trước khi chạy <code>update</code>.

## 2. Phân biệt ba khái niệm dễ nhầm

| Khái niệm | Dùng để làm gì? | Ví dụ | Lưu ý |
|---|---|---|---|
| **Changelog parameter** | Thay một chuỗi ký hiệu trong định nghĩa changelog bằng giá trị đã cung cấp | <code>${app.schema}</code> trong <code>schemaName</code> | Thuộc tính được resolve trong ngữ cảnh changelog, không phải biến SQL runtime |
| **Cấu hình chạy Liquibase** | Điều khiển kết nối, changelog gốc, driver, schema mặc định, contexts, labels và hành vi CLI | <code>url</code>, <code>changeLogFile</code>, <code>defaultSchemaName</code> | Có quy tắc nguồn cấu hình/ghi đè riêng tùy phiên bản và integration |
| **Biến môi trường / Spring property** | Cấp giá trị cho tiến trình, pipeline hoặc cấu hình ứng dụng | <code>APP_SCHEMA</code>, <code>spring.liquibase.parameters.appSchema</code> | Không phải mọi biến môi trường tùy ý đều tự động trở thành changelog parameter |

Sự khác nhau này rất quan trọng. Ví dụ, <code>defaultSchemaName=app</code> là tùy chọn cấu hình Liquibase, còn <code>${app.schema}</code> là một chỗ thay thế trong changelog. Hai giá trị có thể được đặt bằng nhau nhưng Liquibase không buộc chúng đồng bộ. Nếu một changeset chứa <code>schemaName: ${app.schema}</code>, cần biết chính xác tham số <code>app.schema</code> đã được cấp như thế nào.

Ngoài ra, **changelog parameter không phải SQL bind parameter**. Thay thế chuỗi trong tên bảng, tên schema hoặc SQL không có cùng đặc tính bảo vệ và kiểm tra kiểu như placeholder trong JDBC prepared statement. Không nhận tên đối tượng hoặc biểu thức SQL từ dữ liệu đầu vào không đáng tin cậy rồi đưa thẳng vào changelog.

## 3. Cú pháp khai báo và sử dụng thuộc tính

Ví dụ changelog YAML:

~~~yaml
databaseChangeLog:
  - property:
      name: app.schema
      value: inventory

  - property:
      name: app.indexPrefix
      value: idx_inv

  - changeSet:
      id: 001-add-product-index
      author: db-team
      changes:
        - createIndex:
            schemaName: ${app.schema}
            tableName: product
            indexName: ${app.indexPrefix}_product_code
            columns:
              - column:
                  name: code
~~~

Trong trường hợp không có giá trị được cấp từ nguồn khác với độ ưu tiên cao hơn và hai khai báo trên có hiệu lực, Liquibase sẽ thay <code>${app.schema}</code> bằng <code>inventory</code> và <code>${app.indexPrefix}</code> bằng <code>idx_inv</code>. Tên chỉ mục dự kiến là <code>idx_inv_product_code</code>.

Với cơ sở dữ liệu mà schema và bảng thực tế tồn tại như dự kiến, lệnh xem trước SQL giúp xác minh thao tác nhắm tới đối tượng đúng. Không nên chỉ nhìn tệp YAML và suy ra chắc chắn SQL cuối cùng, vì một nguồn tham số bên ngoài có thể đã được đăng ký trước.

Khi đặt tên thuộc tính, nên:

- Dùng tên biểu đạt mục đích, ví dụ <code>inventory.schema</code>, <code>audit.indexPrefix</code>, <code>migration.batchSize</code>.
- Tránh tên quá chung như <code>name</code>, <code>schema</code> hoặc <code>value</code> trong repository có nhiều changelog.
- Giữ cách viết hoa/thường và quy tắc dấu phân cách thống nhất; không mặc định mọi integration chuẩn hóa tên giống nhau.
- Có danh mục thuộc tính nào do pipeline cấp, thuộc tính nào có giá trị mặc định trong changelog.
- Tránh đưa password, token hoặc dữ liệu nhạy cảm vào phần thay thế có thể xuất hiện trong SQL preview và log.

## 4. Phạm vi của thuộc tính: changelog, tệp include và môi trường

### 4.1. Thuộc tính dùng chung giữa các changelog

Trong cấu trúc phổ biến, changelog gốc chứa các khai báo dùng chung trước khi nạp changelog con. Ví dụ minh họa hai tệp **trong nội dung bài học**, không yêu cầu tạo thêm tệp thực tế:

Changelog gốc <code>db.changelog-master.yaml</code>:

~~~yaml
databaseChangeLog:
  - property:
      name: inventory.schema
      value: inventory

  - property:
      name: inventory.auditPrefix
      value: audit_

  - include:
      file: db/changelog/001-create-product.yaml
~~~

Changelog con <code>001-create-product.yaml</code>:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-product
      author: db-team
      changes:
        - createTable:
            schemaName: ${inventory.schema}
            tableName: product
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Ý định thiết kế là khai báo <code>inventory.schema</code> một lần ở changelog gốc để những thay đổi được nạp phía sau có thể sử dụng. Cấu hình truyền tham số bên ngoài vẫn có thể tác động đến giá trị hiệu lực. Cần xác nhận thứ tự nạp changelog và phạm vi tham số theo phiên bản Liquibase sử dụng.

### 4.2. Phạm vi toàn cục và cục bộ

Một số phiên bản Liquibase hỗ trợ thuộc tính <code>global</code> trên khai báo <code>property</code>. Khi được hỗ trợ, cấu hình theo hướng **toàn cục** giúp thuộc tính dùng được ngoài tệp khai báo; giá trị <code>global: false</code> có thể giới hạn thuộc tính vào changelog hiện tại. Phạm vi và hành vi chính xác phụ thuộc phiên bản, vì vậy phải kiểm tra khả năng hỗ trợ trước khi triển khai.

Ví dụ về ý tưởng khai báo cục bộ trong phiên bản hỗ trợ:

~~~yaml
databaseChangeLog:
  - property:
      name: local.indexPrefix
      value: idx_product
      global: false

  - changeSet:
      id: 002-index-product-status
      author: db-team
      changes:
        - createIndex:
            tableName: product
            indexName: ${local.indexPrefix}_status
            columns:
              - column:
                  name: status
~~~

Thuộc tính cục bộ hữu ích khi cùng một tên kỹ thuật có thể xuất hiện trong nhiều changelog con, nhưng không muốn vô tình tác động lẫn nhau. Không nên suy ra rằng <code>global: false</code> tạo ra biến cục bộ cho riêng một changeset: ranh giới của thuộc tính liên quan đến **changelog chứa khai báo**, không đơn giản là khối changeset gần nhất.

Nếu phiên bản đang dùng không hỗ trợ phạm vi cục bộ theo cách mong muốn, hãy dùng tên có tiền tố riêng cho từng module và khai báo thuộc tính tập trung; đừng giả định tính năng sẽ tự hoạt động.

### 4.3. Phạm vi môi trường và DBMS

Trong changelog, khai báo <code>property</code> có thể có điều kiện như <code>context</code> hoặc <code>dbms</code> để chọn giá trị phù hợp với môi trường hay hệ quản trị cơ sở dữ liệu. Ví dụ:

~~~yaml
databaseChangeLog:
  - property:
      name: audit.timestampType
      value: timestamptz
      dbms: postgresql

  - property:
      name: audit.timestampType
      value: datetime2
      dbms: mssql

  - changeSet:
      id: 003-create-audit-event
      author: db-team
      changes:
        - createTable:
            tableName: audit_event
            columns:
              - column:
                  name: created_at
                  type: ${audit.timestampType}
~~~

Trên PostgreSQL, khai báo thuộc tính gắn <code>postgresql</code> dự định cung cấp <code>timestamptz</code>; trên SQL Server, khai báo gắn <code>mssql</code> dự định cung cấp <code>datetime2</code>. Cần thử trên đúng DBMS vì cú pháp và khả năng thay thế trong từng trường của change có thể phụ thuộc phiên bản Liquibase.

Một ví dụ khác phân biệt môi trường:

~~~yaml
databaseChangeLog:
  - property:
      name: inventory.schema
      value: inventory_dev
      context: dev

  - property:
      name: inventory.schema
      value: inventory_prod
      context: prod
~~~

Ví dụ trên chỉ có ý nghĩa khi **context filter thực tế được truyền và kiểm chứng**. Không nên mặc định rằng không truyền filter sẽ loại bỏ mọi khai báo có context; một số cách lựa chọn có thể khiến nhiều khai báo cùng đủ điều kiện. Khi đó, quy tắc ưu tiên khai báo đầu tiên có thể làm kết quả khác mong đợi.

**Contexts và labels không đồng nghĩa với phạm vi của property.** Chúng còn được dùng để chọn changeset, nhưng không được tự giả định mọi thuộc tính hỗ trợ cùng tập điều kiện hay cùng cú pháp như một changeset. Hãy phân biệt việc chọn *giá trị* với việc chọn *thay đổi cần thực thi*.

## 5. Thứ tự khai báo: vì sao vị trí rất quan trọng?

### 5.1. Khai báo trước lần sử dụng

Trong changelog có nhiều <code>include</code>, Liquibase xử lý các khai báo và thay đổi theo cơ chế đọc changelog. Vì vậy, quy ước an toàn là **khai báo tham số dùng chung trước các tệp dùng đến tham số đó**.

Ví dụ nên dùng:

~~~yaml
databaseChangeLog:
  - property:
      name: inventory.schema
      value: inventory

  - include:
      file: db/changelog/010-tables.yaml

  - include:
      file: db/changelog/020-indexes.yaml
~~~

Ví dụ rủi ro:

~~~yaml
databaseChangeLog:
  - include:
      file: db/changelog/010-tables.yaml

  - property:
      name: inventory.schema
      value: inventory
~~~

Nếu tệp được include ở phía trước đã cần <code>${inventory.schema}</code>, không được tin rằng khai báo phía sau sẽ tự quay lại bổ sung hay cập nhật những nơi đã được phân tích. Hành vi cụ thể có thể khác giữa parser/phiên bản; cách làm dễ kiểm chứng nhất vẫn là đưa tham số lên trước nơi sử dụng và chạy <code>validate</code>, <code>update-sql</code> trên changelog đã đóng gói.

### 5.2. Khai báo lần đầu thường quyết định giá trị

Một nguyên tắc đặc trưng của changelog parameters trong Liquibase là **giá trị được đăng ký phù hợp đầu tiên thường được giữ lại**; khai báo lại cùng tên về sau không nên được xem là thao tác gán biến để ghi đè. Đây là lý do cần cẩn thận với trùng tên qua nhiều tệp include.

Ví dụ:

~~~yaml
databaseChangeLog:
  - property:
      name: inventory.schema
      value: inventory_a

  - property:
      name: inventory.schema
      value: inventory_b

  - changeSet:
      id: 004-check-schema
      author: db-team
      changes:
        - createTable:
            schemaName: ${inventory.schema}
            tableName: schema_probe
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Với ngữ cảnh có hiệu lực như nhau, khai báo <code>inventory_a</code> đứng trước. Không nên thiết kế migration dựa vào giả định khai báo thứ hai sẽ đổi tên schema thành <code>inventory_b</code>. Đặc biệt, khi một tham số đã được cấp qua CLI hoặc cơ chế tích hợp trước lúc đọc changelog, các khai báo trong changelog có thể không phải nguồn thắng.

Để thay giá trị giữa các môi trường, nên cấp tham số qua cơ chế môi trường được quản lý, hoặc dùng điều kiện <code>context</code>/<code>dbms</code> có thể kiểm chứng, thay vì cố tình định nghĩa trùng rồi mong thứ tự sau ghi đè thứ tự trước.

### 5.3. Thứ tự trong include và includeAll

Với <code>include</code> tường minh, thứ tự được thể hiện bằng vị trí các mục trong changelog gốc. Với <code>includeAll</code>, việc liệt kê nhiều tệp chịu ảnh hưởng quy tắc sắp xếp, bộ lọc tài nguyên và các khả năng tùy biến của phiên bản Liquibase. Vì thế, nếu giá trị thuộc tính quan trọng phụ thuộc vào thứ tự giữa nhiều tệp, không nên dựa vào tên tệp một cách tình cờ.

Một kiến trúc dễ bảo trì là:

1. Changelog gốc khai báo những property mặc định hoặc nạp một tệp tham số chuyên trách trước.
2. Các changelog con chỉ sử dụng những property được công bố; hạn chế khai báo lại tên dùng chung.
3. Migration mới dùng định danh changeset riêng và không sửa các changeset đã phát hành.
4. Pipeline cố định changelog và phiên bản Liquibase rồi kiểm tra SQL dự kiến trước khi chạy.

## 6. Ưu tiên giữa nguồn bên ngoài và khai báo trong changelog

Đối với một thuộc tính, cần phân biệt **ưu tiên của nguồn cấu hình** và **thứ tự đăng ký thuộc tính trong changelog**. Đây là hai cơ chế có liên quan nhưng không đồng nhất.

### 6.1. Các nguồn cấp tham số thường gặp

| Nguồn cấp giá trị | Cách sử dụng điển hình | Điều cần xác minh |
|---|---|---|
| Tham số dòng lệnh của Liquibase | Truyền giá trị bằng tùy chọn <code>-Dten=giatri</code> trong phiên bản hỗ trợ | Thứ tự tùy chọn và cú pháp của đúng CLI |
| Tệp defaults / properties | Thuộc tính được đọc khi khởi chạy Liquibase | Đúng tệp và cách giá trị được map sang changelog parameters |
| Java system properties | Thuộc tính cấp cho JVM chứa Liquibase | Giá trị nào được adapter/launcher chuyển vào Liquibase |
| Biến môi trường | Giá trị môi trường được CLI hoặc wrapper hỗ trợ | Tên biến, quy tắc ưu tiên và việc biến có được chuyển thành changelog parameter không |
| Spring Boot | <code>spring.liquibase.parameters.*</code> qua cơ chế cấu hình Spring | Giá trị sau khi profile, env và command-line property được bind |
| Thẻ <code>property</code> trong changelog | Mặc định/giá trị có điều kiện DBMS hoặc context | Thứ tự đọc, phạm vi và xung đột tên |

Trong nhiều cách sử dụng, tham số cung cấp **bên ngoài changelog** được đăng ký trước khi đọc changelog và nhờ đó có thể được ưu tiên hơn giá trị mặc định khai báo bằng <code>property</code>. Tuy nhiên, **không có một bảng ưu tiên duy nhất đáng tin cậy cho mọi phiên bản CLI, Spring Boot, Maven/Gradle plugin và wrapper**. Thứ tự giữa CLI, tệp defaults, biến môi trường và Java system properties phải được xác nhận theo công cụ/phiên bản đang chạy.

Không được suy ra rằng tất cả biến môi trường đều được Liquibase dùng để thay thế <code>${...}</code>. Biến của CLI như <code>LIQUIBASE_COMMAND_URL</code> thường cấu hình kết nối; nó không mặc nhiên tạo changelog parameter <code>inventory.schema</code>. Muốn dùng biến tùy ý, cần một bước truyền/mapping tường minh theo cơ chế được integration hỗ trợ.

### 6.2. Ví dụ cấp tham số lúc chạy

Giả sử changelog có mặc định:

~~~yaml
databaseChangeLog:
  - property:
      name: inventory.schema
      value: inventory_local

  - changeSet:
      id: 005-create-category
      author: db-team
      changes:
        - createTable:
            schemaName: ${inventory.schema}
            tableName: category
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Ví dụ CLI tham khảo:

~~~bash
liquibase --defaults-file=./liquibase-staging.properties -Dinventory.schema=inventory_stage update-sql
~~~

Trong phiên bản hỗ trợ cách truyền <code>-D</code> này, giá trị <code>inventory_stage</code> được cấp từ bên ngoài trước khi changelog chạy. Kỳ vọng là SQL nhắm tới schema staging thay vì giá trị mặc định <code>inventory_local</code>. **Phải kiểm chứng bằng SQL thực tế sinh ra và lệnh trợ giúp của bản Liquibase đang dùng**, vì cách cấp changelog parameter có thể khác tùy adapter và phiên bản.

Ví dụ này không có nghĩa nên đặt lại username, password hoặc JDBC URL bằng tên <code>inventory.schema</code>. Mỗi nhóm cấu hình có mục đích riêng; quản lý từng nhóm rõ ràng giúp tránh nhầm migration target.

### 6.3. Bảng quyết định khi trùng tên

| Tình huống | Cách hiểu an toàn |
|---|---|
| Hai <code>property</code> cùng tên, cùng phạm vi/điều kiện trong một changelog | Khai báo sớm hơn có thể thắng; coi là lỗi thiết kế cần loại bỏ |
| Changelog gốc và con cùng khai báo tên dùng chung | Cẩn thận với thứ tự nạp; không kỳ vọng child override parent |
| Property được khai báo sau nơi sử dụng | Không dựa vào việc parser quay lại thay thế; chuyển khai báo lên trước |
| Giá trị từ CLI và changelog cùng tên | Xác minh nguồn thắng theo phiên bản/adapter; kiểm tra SQL preview |
| Các thuộc tính cùng tên nhưng <code>dbms</code> khác nhau | Chỉ một giá trị nên phù hợp DBMS đích; kiểm tra trường hợp thiếu hoặc chồng lấn |
| Các thuộc tính cùng tên nhưng <code>context</code> khác nhau | Phải chắc chắn filter thực tế khiến tập khai báo đủ điều kiện không mơ hồ |
| Thuộc tính toàn cục và cục bộ cùng tên | Kiểm tra hỗ trợ phiên bản và ranh giới phạm vi; ưu tiên đặt tên riêng |

Các quy tắc này nên được thể hiện thành convention của repository để reviewer không phải suy đoán từ vị trí tệp.

## 7. Thuộc tính trong Spring Boot và pipeline CI/CD

### 7.1. Truyền tham số qua Spring Boot

Spring Boot hỗ trợ map thuộc tính vào changelog parameters qua <code>spring.liquibase.parameters</code> trong cấu hình phù hợp. Ví dụ:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    parameters:
      inventory.schema: ${APP_SCHEMA:inventory}
      inventory.auditPrefix: audit_
~~~

Trong ví dụ này, <code>${APP_SCHEMA:inventory}</code> là placeholder được Spring xử lý từ môi trường ứng dụng; giá trị sau khi Spring resolve mới được chuyển thành changelog parameter <code>inventory.schema</code>. Còn <code>${inventory.schema}</code> trong changelog được Liquibase thay thế khi đọc migration. Hai tầng placeholder có cú pháp tương tự nhưng chủ thể và thời điểm xử lý khác nhau.

Điều cần kiểm tra ở runtime:

- Profile Spring nào đang hoạt động và những nguồn cấu hình nào ghi đè property?
- Liquibase dùng datasource ứng dụng hay datasource riêng?
- Giá trị thực tế của <code>spring.liquibase.parameters.inventory.schema</code> là gì?
- Đường dẫn changelog có đúng artifact chứa bản đã review không?
- Có job CI/CD khác cũng đang chạy migration vào database đó không?

Nếu ứng dụng có nhiều instance và pipeline đã chịu trách nhiệm thực thi migration, có thể cấu hình <code>spring.liquibase.enabled=false</code> ở runtime cho các instance ứng dụng theo chiến lược phát hành. Việc bật auto-run chỉ để kiểm tra tham số có thể vô tình triển khai migration thật.

### 7.2. Phân tách môi trường qua CI/CD

Một pipeline có thể cấp các giá trị như schema nghiệp vụ, DBMS, context filter, tài khoản kết nối bằng cấu hình/secret riêng từng môi trường. Tuy nhiên, cần phân định rạch ròi:

- **Changelog parameter** xác định chuỗi được thay trong migration, ví dụ <code>inventory.schema</code>.
- **Connection configuration** xác định database mà job kết nối tới.
- **Context/label filter** xác định những changeset nào đủ điều kiện chạy.
- **Default schema** có thể tác động tới change không chỉ rõ schema.

Không được mặc định rằng đặt changelog parameter <code>inventory.schema=inventory_prod</code> sẽ đổi luôn <code>defaultSchemaName</code>, hay ngược lại. Nếu hai nguồn cùng biểu diễn schema mong muốn, pipeline cần kiểm tra tính nhất quán của chúng.

Ví dụ manifest cho một lần preflight:

~~~yaml
release: inventory-service-2026.11
environment: staging
liquibase:
  version: "<pinned-version>"
  changelog: db/changelog/db.changelog-master.yaml
  database: inventory
  defaultSchema: inventory_stage
  contexts: staging
  parameters:
    inventory.schema: inventory_stage
    inventory.auditPrefix: audit_
checks:
  propertySourcesReviewed: pending
  changelogValidated: pending
  pendingChangesetsReviewed: pending
  updateSqlReviewed: pending
~~~

Đây là ví dụ **bản ghi để đối chiếu**, không phải định dạng trực tiếp bắt buộc của Liquibase. Kết quả check chỉ được đánh dấu đạt sau khi có bằng chứng. Không ghi secret và không lưu toàn bộ biến môi trường vào log.

## 8. Thứ tự xử lý và tác động đến thay đổi schema

Một lỗi hay gặp là xem property như biến chương trình có thể gán lại tùy ý ở bất cứ đâu. Trong Liquibase, changelog chủ yếu mô tả lịch sử thay đổi, không phải script ngôn ngữ lập trình thông thường. Kết quả còn phụ thuộc vào lúc parser đọc thuộc tính, áp dụng điều kiện và tạo thay thế cho từng change.

Hãy xét một quy trình phát hành:

1. Liquibase khởi tạo với cấu hình kết nối, changelog path, tham số từ các nguồn bên ngoài.
2. Liquibase đọc changelog gốc và những tệp được include theo cấu trúc của changelog.
3. Các khai báo property đủ điều kiện được đăng ký theo phạm vi/thứ tự.
4. Placeholder <code>${...}</code> được resolve khi phần changelog liên quan được phân tích.
5. Liquibase đối chiếu changeset với bảng lịch sử, điều kiện chạy và checksum; sau đó chuẩn bị thao tác SQL.
6. Lệnh xem trước hoặc update tạo SQL theo trạng thái database và cấu hình tại thời điểm chạy.

Đây là mô hình khái niệm để hiểu nguồn giá trị, không phải cam kết về từng bước nội bộ của mọi phiên bản parser. Trong thực tế, chỉ nên tin vào kết quả kiểm chứng của bản Liquibase được dự án sử dụng.

### 8.1. Tác động tới checksum và lịch sử

Một changeset được Liquibase nhận diện qua id, author và đường dẫn changelog (hoặc cơ chế đường dẫn logic khi được sử dụng). Lịch sử triển khai và checksum giúp phát hiện một số thay đổi nội dung ngoài dự kiến.

Thay đổi khai báo property hoặc giá trị cấp ngoài có thể làm SQL dự kiến khác đi giữa các môi trường, kể cả khi changeset giữ nguyên tên. Không nên dựa hoàn toàn vào checksum để chứng minh tham số, tên schema hoặc dữ liệu ở mọi lần triển khai đều giống nhau: cơ chế checksum và thời điểm tính toán phụ thuộc loại change và phiên bản công cụ.

Nguyên tắc vận hành là:

- **Không sửa changeset đã triển khai** chỉ để thay giá trị property mong muốn.
- Quản lý bộ tham số theo từng môi trường, đi kèm artifact/release.
- Với thay đổi schema hoặc dữ liệu mới, tạo changeset mới và đánh giá tương thích ứng dụng.
- Khi checksum sai khác, kiểm tra nguồn gốc thay đổi trước khi cân nhắc bất kỳ thao tác xử lý checksum nào.
- Đối với rollback, kiểm tra cả tham số hiệu lực của SQL rollback; rollback có thể không an toàn nếu schema hoặc dữ liệu bị đổi so với lần update.

### 8.2. Tham số không bảo đảm migration lặp lại an toàn

Thay <code>${inventory.schema}</code> bằng một schema khác không có nghĩa migration tự thích nghi được với mọi môi trường. DBMS có thể khác kiểu dữ liệu, quyền tạo bảng, cú pháp index và transaction. Preconditions phải diễn đạt giả định đúng, migration cần thử trên DBMS mục tiêu và thay đổi dữ liệu lớn cần kế hoạch riêng.

Nếu một thuộc tính không được resolve, Liquibase hoặc DBMS có thể báo lỗi hoặc tạo ra SQL không đúng kỳ vọng tùy ngữ cảnh. Pipeline nên chặn sớm bằng validation, kiểm tra bộ tham số bắt buộc và review SQL thực tế, không dựa vào việc lỗi sẽ tự hiển thị theo một cách cố định.

## 9. Thực hành dự đoán giá trị: ba trường hợp

### Trường hợp A — Trùng property trong một changelog

~~~yaml
databaseChangeLog:
  - property:
      name: app.schema
      value: first_schema
  - property:
      name: app.schema
      value: second_schema
~~~

**Phân tích:** hai khai báo cùng tên có điều kiện giống nhau là điểm xung đột. Theo nguyên tắc giá trị phù hợp đầu tiên thường được giữ lại, kỳ vọng là <code>first_schema</code> nếu không có nguồn bên ngoài nào cấp trước. Không thiết kế hệ thống phụ thuộc vào việc khai báo sau sẽ ghi đè; nên xóa khai báo trùng và kiểm tra bằng SQL preview.

### Trường hợp B — Có giá trị bên ngoài

Changelog:

~~~yaml
databaseChangeLog:
  - property:
      name: app.schema
      value: local_schema
~~~

Pipeline cấp changelog parameter <code>app.schema=stage_schema</code> qua một integration được hỗ trợ.

**Phân tích:** giá trị bên ngoài có thể được đăng ký trước khi đọc changelog, nên <code>stage_schema</code> có thể là giá trị hiệu lực. Muốn kết luận phải kiểm tra ưu tiên cụ thể của integration và SQL preview; không thể chỉ nhìn khai báo <code>local_schema</code>.

### Trường hợp C — Hai khai báo có context khác nhau

~~~yaml
databaseChangeLog:
  - property:
      name: app.schema
      value: stage_schema
      context: staging

  - property:
      name: app.schema
      value: prod_schema
      context: prod
~~~

**Phân tích:** ý định là chọn schema theo môi trường. Nếu filter <code>staging</code> thực sự được cấp và chỉ khai báo staging đủ điều kiện thì <code>stage_schema</code> là kết quả dự kiến. Nếu filter bị bỏ trống hoặc sai, có thể xảy ra lựa chọn không mong muốn; không suy đoán, phải kiểm chứng tập property đủ điều kiện và SQL dự kiến.

Ba trường hợp minh họa rằng **phạm vi và điều kiện quyết định khai báo nào hợp lệ, thứ tự quyết định khai báo nào có trước, và nguồn cấp bên ngoài có thể tác động trước cả hai**.

## 10. Quy trình kiểm chứng thuộc tính trước khi chạy Liquibase

Khi chuẩn bị phát hành, nhóm nên áp dụng các bước sau:

1. **Cố định artifact và phiên bản Liquibase.** Ghi rõ commit, changelog path, JDBC driver và DBMS.
2. **Liệt kê thuộc tính quan trọng.** Đặc biệt là tên schema, bảng, chỉ mục, kiểu dữ liệu và các tham số liên quan tới thay đổi dữ liệu.
3. **Dựng sơ đồ nguồn giá trị.** Với mỗi tên, chỉ rõ được khai báo ở changelog nào, có nguồn CLI/Spring/CI nào truyền trước, có <code>context</code>/<code>dbms</code> hoặc giới hạn <code>global</code> không.
4. **Kiểm tra thứ tự include và khai báo.** Đảm bảo property được xác định trước khi tệp con dùng tới; loại bỏ trùng tên không chủ đích.
5. **Xác minh cấu hình hiệu lực.** Kiểm tra database, schema, context filter, label filter và nguồn cấp tham số cho đúng môi trường.
6. **Chạy validate và status bằng đúng bộ cấu hình.** Kiểm tra changelog hợp lệ và changesets chưa chạy có đúng phạm vi.
7. **Sinh và review SQL.** Đọc tên đối tượng sau thay thế, điều kiện, DDL phá hủy, dữ liệu mẫu, schema lịch sử và quyền.
8. **Giữ nguyên tham số khi update.** Nếu release, filter hoặc property thay đổi sau preview, làm lại các bước kiểm tra chịu ảnh hưởng.
9. **Xác minh sau triển khai.** Đối chiếu DATABASECHANGELOG, trạng thái schema và kết quả ứng dụng; ghi lại manifest để truy vết.

Ví dụ lệnh CLI tham khảo:

~~~bash
liquibase --defaults-file=./config/liquibase-staging.properties validate
liquibase --defaults-file=./config/liquibase-staging.properties status --verbose
liquibase --defaults-file=./config/liquibase-staging.properties update-sql
~~~

Những lệnh này cần được thử với cú pháp đúng phiên bản. Không được dùng tham số/secret khác nhau giữa bước status, preview và bước update dự kiến. Việc validate thành công không chứng minh một SQL sẽ chạy an toàn trên dữ liệu production.

### 10.1. Bảng ghi nhận nguồn và giá trị

| Property | Nguồn dự kiến | Phạm vi/điều kiện | Giá trị hiệu lực đã xác minh | Bằng chứng |
|---|---|---|---|---|
| <code>inventory.schema</code> | Spring Boot hoặc CLI parameter | Theo môi trường | <code>inventory_stage</code> | SQL preview nhắm tới schema staging |
| <code>inventory.auditPrefix</code> | Changelog gốc | Dùng chung các changelog con | <code>audit_</code> | Tên đối tượng trong SQL preview |
| <code>audit.timestampType</code> | Property với <code>dbms</code> | PostgreSQL | <code>timestamptz</code> | SQL tạo cột và DBMS đích |

Đây là giá trị minh họa; người triển khai chỉ được điền PASS khi xác minh đúng môi trường thực tế. Không đưa mật khẩu, token hoặc chuỗi chứa thông tin xác thực vào bảng này.

## 11. Lỗi thường gặp và cách khắc phục

| Biểu hiện | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Property dường như không nhận giá trị mới | Một khai báo hoặc nguồn bên ngoài đã đăng ký cùng tên trước | Xác định nguồn thắng, loại bỏ trùng và preview SQL |
| Property có hiệu lực ở changelog này nhưng thiếu ở changelog khác | Phạm vi local/global, thứ tự include hoặc khác biệt phiên bản | Kiểm tra ranh giới scope và đưa khai báo trước nơi dùng |
| Migration dùng nhầm schema ở production | Context filter vắng mặt, property trùng hoặc tham số CI cấp sai | Kiểm tra filter, bảng nguồn giá trị và SQL preview |
| Lệnh chạy với giá trị khác máy dev | Java system property, biến môi trường, Spring profile hoặc defaults-file | So sánh cấu hình đã resolve trên runner |
| Thay đổi property nhưng bảng cũ không thay đổi | Changeset tương ứng đã được ghi nhận là chạy | Tạo migration mới; không sửa lịch sử để ép rerun |
| Checksum báo sai khác | Nội dung changelog đã triển khai bị thay đổi hoặc có khác biệt định nghĩa | So sánh artifact gốc, đánh giá trước khi xử lý |
| Placeholder còn nguyên trong SQL hoặc sinh tên đối tượng sai | Property thiếu, sai tên hoặc chưa đủ điều kiện theo context/dbms | Kiểm tra danh mục tham số và các điều kiện |
| SQL khác giữa các môi trường ngoài dự kiến | Property theo DBMS/context hoặc nguồn runtime không nhất quán | Đối chiếu từng bộ tham số và DBMS, chạy kiểm thử phù hợp |
| Dữ liệu nhạy cảm lộ trong log/preview | Dùng substitution cho secret hoặc dump cấu hình | Di chuyển secret sang cơ chế quản lý phù hợp, che log |

Một anti-pattern đáng tránh là sửa trực tiếp bảng <code>DATABASECHANGELOG</code> hoặc xóa checksum nhằm ép Liquibase chọn lại property. Việc đó làm lịch sử triển khai khó đối chiếu và không giải quyết gốc rễ của cấu hình sai.

## 12. Checklist review trước khi chấp nhận migration tham số hóa

- [ ] Mỗi property có tên rõ ràng, người quản lý và nguồn cấp giá trị được xác định.
- [ ] Thuộc tính dùng chung được khai báo hoặc truyền trước khi changelog con sử dụng.
- [ ] Không có khai báo trùng tên vô ý; nếu dùng điều kiện <code>context</code>/<code>dbms</code>, các nhánh được kiểm chứng.
- [ ] Những tính năng phạm vi như <code>global: false</code> được kiểm tra trên phiên bản Liquibase thực tế.
- [ ] CLI, defaults, biến môi trường, Java, Spring Boot và CI/CD không có giá trị ghi đè chưa giải thích.
- [ ] Changelog parameter và cấu hình kết nối/default schema được đối chiếu độc lập.
- [ ] SQL preview cho thấy đúng schema, bảng, cột, chỉ mục, kiểu dữ liệu và dữ liệu được thay thế.
- [ ] Cùng một artifact, bộ lọc và tham số sẽ được dùng cho update.
- [ ] Changeset đã triển khai được giữ bất biến; thay đổi mới có changeset mới và phương án rollback/forward fix phù hợp.
- [ ] Không đưa dữ liệu không tin cậy, password hoặc token vào thay thế chuỗi trong changelog.
- [ ] Kết quả validate, status và review SQL được ghi nhận trong pipeline.

## 13. Ghi nhớ

Khi gặp cú pháp <code>${ten.thuoc.tinh}</code> trong Liquibase, hãy truy ngược **nguồn cấp → phạm vi áp dụng → điều kiện context/dbms → thứ tự đăng ký → giá trị hiệu lực**. Thuộc tính trong changelog không nên được dùng như biến có thể gán lại tùy ý; khai báo phù hợp đầu tiên và nguồn đã cấp trước có thể quyết định giá trị. Tính năng local/global cũng phải được xác nhận theo phiên bản.

Tham số hóa giúp dùng lại changelog giữa các môi trường, nhưng độ an toàn đến từ việc kiểm chứng giá trị thực tế và SQL sau thay thế. Kết hợp quy tắc đặt tên rõ ràng, changelog có thứ tự, cấu hình CI/CD được quản lý và review SQL trước update giúp lịch sử migration nhất quán, dễ rollback hoặc sửa lỗi, và giảm nguy cơ áp dụng thay đổi schema vào sai đối tượng.
