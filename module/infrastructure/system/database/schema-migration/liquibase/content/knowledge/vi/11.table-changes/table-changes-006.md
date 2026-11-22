# Thêm, đổi hoặc xóa giá trị mặc định

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, thuộc chương **Thay đổi bảng**, một thao tác migration rất thường gặp là thiết lập **giá trị mặc định (default value)** cho cột. Chẳng hạn, bản ghi hóa đơn mới có trạng thái mặc định **PENDING**, lượt đăng ký mới mặc định **is_active = true**, hoặc bản ghi nhật ký mới mặc định **created_at = CURRENT_TIMESTAMP**. Khi yêu cầu nghiệp vụ thay đổi, nhóm phải biết cách **thêm**, **đổi** hoặc **xóa** giá trị mặc định mà vẫn bảo toàn dữ liệu và lịch sử triển khai.

Liquibase giúp quản lý các thay đổi schema và dữ liệu bằng **changelog**, **changeset**, **precondition**, **checksum** và bảng lịch sử **DATABASECHANGELOG**; đồng thời hỗ trợ kiểm chứng migration, rollback và triển khai qua Spring Boot hoặc CI/CD. Trong chủ đề này, hai change type trọng tâm là **addDefaultValue** và **dropDefaultValue**. Chúng thay đổi định nghĩa schema, còn việc sửa dữ liệu hiện có là một quyết định migration riêng.

Sau bài học, người học cần phân biệt giá trị mặc định với NOT NULL, hiểu hành vi của dữ liệu cũ và lệnh INSERT mới, chọn đúng thuộc tính Liquibase theo kiểu dữ liệu, thiết kế rollback khi đổi default, và kiểm chứng SQL trên hệ quản trị cơ sở dữ liệu thực tế.

## 1. Giá trị mặc định ở tầng database có nghĩa là gì?

Giá trị mặc định là biểu thức hoặc hằng số mà **database** có thể sử dụng để điền giá trị vào cột khi thao tác chèn bản ghi không cung cấp giá trị cho cột đó. Ví dụ bảng **invoice** có cột **status** với mặc định **PENDING**:

~~~sql
INSERT INTO invoice (id, amount) VALUES (101, 150000);
~~~

Nếu cột status có default hợp lệ, database có thể lưu **PENDING** cho dòng mới. Trong khi đó:

~~~sql
INSERT INTO invoice (id, amount, status)
VALUES (102, 250000, 'PAID');
~~~

Dòng này dùng giá trị **PAID** được cung cấp rõ ràng. Với đa số hệ quản trị cơ sở dữ liệu quan hệ, nếu lệnh INSERT **chỉ định NULL một cách tường minh** cho cột nullable, database ghi NULL thay vì lấy default:

~~~sql
INSERT INTO invoice (id, amount, status)
VALUES (103, 100000, NULL);
~~~

Vì vậy, cần phân biệt bốn tình huống:

| Tình huống | Hành vi thông thường |
|---|---|
| INSERT bỏ qua cột có default | Database dùng giá trị mặc định |
| INSERT truyền giá trị cụ thể | Database dùng giá trị được truyền |
| INSERT truyền NULL tường minh vào cột nullable | Có thể lưu NULL, không tự thay bằng default |
| UPDATE không đề cập đến cột | Giá trị cũ của cột được giữ nguyên |

Một số DBMS còn hỗ trợ từ khóa SQL **DEFAULT**, ví dụ dùng trong INSERT để yêu cầu lấy default. Cú pháp chính xác phụ thuộc DBMS và cần thử trên database đích.

**Default không đồng nghĩa với NOT NULL.** Default xác định giá trị được dùng trong một số trường hợp không cung cấp giá trị; ràng buộc NOT NULL kiểm soát việc cột có được chứa NULL hay không. Một cột có thể vừa có default vừa cho phép NULL. Ngược lại, cột NOT NULL vẫn có thể không có default: khi đó ứng dụng thường phải cung cấp giá trị hợp lệ trong INSERT.

**Default cũng không đồng nghĩa với dữ liệu đã được cập nhật.** Thay default của một cột đang tồn tại thường không sửa các dòng đã lưu; nếu cần chuẩn hóa lịch sử, phải thực hiện backfill riêng.

## 2. Ba thao tác chính trong Liquibase

Liquibase có ba cách dùng nổi bật khi thay đổi default của **cột đã tồn tại**:

1. **Thêm default**: dùng **addDefaultValue** để cấu hình giá trị hoặc biểu thức mặc định mới.
2. **Đổi default**: trong nhiều DBMS, cũng dùng **addDefaultValue** với giá trị mới để thay thế default hiện tại; cần kiểm tra hành vi với DBMS đích, đặc biệt khi default được lưu dưới dạng constraint độc lập.
3. **Xóa default**: dùng **dropDefaultValue**, khiến database không còn tự cấp giá trị mặc định cho cột khi không được cung cấp.

Hai change type này tác động vào **metadata/schema của cột**, không phải câu lệnh UPDATE dữ liệu.

Các thuộc tính thường gặp:

| Thuộc tính | Vai trò | Ghi chú |
|---|---|---|
| **tableName** | Bảng chứa cột cần đổi | Cần đúng tên bảng thực tế |
| **columnName** | Cột được đổi default | Cần tồn tại trước khi chạy |
| **schemaName** | Schema của bảng | Dùng khi dự án cần chỉ rõ schema |
| **columnDataType** | Kiểu dữ liệu cột | Có thể cần cho một số DBMS, nhất là khi sinh lệnh ALTER |
| **defaultValue** | Giá trị mặc định dạng chuỗi | Ví dụ **PENDING**, **STANDARD** |
| **defaultValueNumeric** | Giá trị số | Ví dụ **0**, **100**, **1.5** |
| **defaultValueBoolean** | Giá trị boolean | Ví dụ **true**, **false** |
| **defaultValueDate** | Giá trị ngày/giờ cố định theo cú pháp Liquibase | Không đồng nghĩa với hàm lấy thời gian hiện tại |
| **defaultValueComputed** | Biểu thức database | Ví dụ **CURRENT_TIMESTAMP**, nếu DBMS hỗ trợ |
| **defaultValueConstraintName** | Tên constraint default, chủ yếu liên quan SQL Server | Cần kiểm tra phiên bản Liquibase và cách quản lý constraint |

Không nên đặt nhiều thuộc tính **defaultValue...** cho cùng một thao tác để “dự phòng”. Hãy chọn **một kiểu giá trị** đúng với thiết kế và khả năng hỗ trợ của phiên bản Liquibase/DBMS đang chạy.

## 3. Thêm giá trị mặc định cho cột đã có

Giả sử bảng **invoice** đã có cột **status VARCHAR(24)**, đang cho phép NULL và chưa có default. Từ thời điểm phát hành mới, mọi hóa đơn được tạo mà không truyền status phải có trạng thái **PENDING**.

Changelog YAML:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-001-invoice-status-default"
      author: "platform"
      preConditions:
        - onFail: HALT
        - columnExists:
            tableName: invoice
            columnName: status
      changes:
        - addDefaultValue:
            tableName: invoice
            columnName: status
            columnDataType: VARCHAR(24)
            defaultValue: PENDING
      rollback:
        - dropDefaultValue:
            tableName: invoice
            columnName: status
            columnDataType: VARCHAR(24)
~~~

Ý nghĩa của changeset:

- **columnExists** kiểm tra cột cần thay đổi đã tồn tại; nếu không, **HALT** giúp dừng triển khai để điều tra thứ tự migration.
- **addDefaultValue** thiết lập giá trị cho những INSERT phù hợp trong tương lai.
- **rollback** dùng **dropDefaultValue** vì trạng thái ban đầu của ví dụ là **không có default**. Nếu trước đó đã có default thì rollback như vậy sẽ không khôi phục trạng thái ban đầu; cần lưu và phục hồi đúng default cũ.
- **columnDataType** được khai báo rõ để hỗ trợ các DBMS yêu cầu thông tin kiểu khi sinh ALTER; việc có bắt buộc hay không phụ thuộc DBMS.

Ví dụ SQL tương đương về ý định trên PostgreSQL:

~~~sql
ALTER TABLE invoice
ALTER COLUMN status SET DEFAULT 'PENDING';
~~~

Đây là SQL minh họa dành cho PostgreSQL, không phải câu lệnh chuẩn chung cho mọi DBMS. Liquibase sẽ sinh SQL theo database và phiên bản driver đang kết nối. Vì vậy, cần xem trước kết quả bằng **update-sql** thay vì suy diễn rằng tất cả hệ quản trị dùng cùng cú pháp ALTER.

### Điều gì xảy ra với hóa đơn cũ?

Giả sử trước migration có các dòng:

| id | status trước migration |
|---|---|
| 1 | NULL |
| 2 | CREATED |
| 3 | PAID |

Chỉ chạy **addDefaultValue** sẽ không tự thay trạng thái của ba dòng trên. Sau migration, dữ liệu cũ thường vẫn là **NULL**, **CREATED**, **PAID**; chỉ các thao tác INSERT mới bỏ qua status mới nhận default **PENDING**.

Nếu yêu cầu còn bao gồm “không còn hóa đơn cũ nào có status NULL”, đó là một **migration dữ liệu riêng**; không nên coi addDefaultValue đã thực hiện xong yêu cầu này.

## 4. Đổi giá trị mặc định: quản lý trạng thái trước và sau

Giả sử phiên bản trước đã thiết lập **status = PENDING**, nhưng từ một đợt phát hành mới nhóm muốn hóa đơn mới mặc định **QUEUED**.

Mô hình trạng thái:

~~~text
Trước migration:
    invoice.status DEFAULT 'PENDING'

Changeset đổi default:
    addDefaultValue(defaultValue = 'QUEUED')

Sau migration:
    invoice.status DEFAULT 'QUEUED'

Rollback dự kiến:
    khôi phục DEFAULT 'PENDING'
~~~

Trên nhiều DBMS, **addDefaultValue** có thể được dùng để thiết lập default mới cho cột đã có default, thay vì tạo một change type tên “modifyDefaultValue”. Ví dụ YAML:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-002-invoice-status-queued"
      author: "platform"
      changes:
        - addDefaultValue:
            tableName: invoice
            columnName: status
            columnDataType: VARCHAR(24)
            defaultValue: QUEUED
      rollback:
        - addDefaultValue:
            tableName: invoice
            columnName: status
            columnDataType: VARCHAR(24)
            defaultValue: PENDING
~~~

Điều quan trọng là **rollback phải khôi phục giá trị cũ**. Nếu rollback bằng **dropDefaultValue**, trạng thái sau khi hoàn tác sẽ là “không có default”, khác với trạng thái trước migration.

Tuy nhiên, hành vi thay thế default không giống nhau trên mọi DBMS. Ví dụ, SQL Server thường quản lý default bằng **default constraint**; nếu một constraint cũ đã tồn tại, lệnh sinh ra có thể cần tìm và xóa constraint trước khi thiết lập constraint mới. Không nên khẳng định rằng YAML ở trên sẽ chạy nguyên vẹn trên mọi hệ quản trị mà không kiểm tra SQL dự kiến. Nếu DBMS yêu cầu nhiều thao tác, có thể cần một quy trình **drop default cũ rồi add default mới** được thiết kế riêng, kèm rollback theo chiều ngược và kiểm soát trạng thái trung gian.

### Đổi default có cập nhật các dòng cũ không?

Không. Giả sử có:

~~~text
invoice 101: status=PENDING (đã được ghi trước đó)
invoice 102: status=PAID
invoice 103: status=NULL
~~~

Sau khi default được đổi sang **QUEUED**, các dòng 101, 102 và 103 vẫn giữ giá trị đang lưu. Default mới chủ yếu tác động đến những INSERT mới không truyền status. Nếu muốn chuyển những bản ghi cũ còn **PENDING** sang **QUEUED**, cần đánh giá logic nghiệp vụ và thực hiện migration dữ liệu riêng; không tự thay toàn bộ chỉ vì default đã đổi.

Chú ý rằng ứng dụng vẫn có thể truyền **PENDING** một cách tường minh. Khi đó database dùng giá trị ứng dụng gửi, không áp default. Việc đổi default ở database phải đi cùng kiểm tra mapper, ORM, JDBC, batch job, trigger và các nguồn ghi dữ liệu khác.

## 5. Xóa giá trị mặc định

Giả sử sau khi đã triển khai một thời gian, mọi client tạo hóa đơn đều phải truyền status tường minh. Nhóm muốn loại bỏ default **QUEUED**.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-003-invoice-status-drop-default"
      author: "platform"
      changes:
        - dropDefaultValue:
            tableName: invoice
            columnName: status
            columnDataType: VARCHAR(24)
      rollback:
        - addDefaultValue:
            tableName: invoice
            columnName: status
            columnDataType: VARCHAR(24)
            defaultValue: QUEUED
~~~

Trong ví dụ này, rollback khôi phục **QUEUED** vì đó là default trước khi xóa.

Sau khi xóa default:

- **INSERT truyền status rõ ràng** vẫn hoạt động nếu giá trị hợp lệ.
- **INSERT bỏ qua status** có thể lưu NULL nếu cột cho phép NULL, hoặc thất bại nếu cột có **NOT NULL**, tùy DBMS và cấu trúc bảng.
- Các bản ghi đã lưu không tự mất hoặc đổi giá trị.
- Việc xóa default không tự thêm ràng buộc NOT NULL và không buộc mọi client phải cung cấp status nếu schema vẫn cho phép NULL.

Trên PostgreSQL, câu lệnh minh họa:

~~~sql
ALTER TABLE invoice
ALTER COLUMN status DROP DEFAULT;
~~~

Ở SQL Server, default thường là constraint gắn với cột; xóa default có thể cần thao tác trên constraint cụ thể. Một migration có hỗ trợ nhiều hệ quản trị phải dựa trên **SQL được Liquibase sinh ra cho đúng database**, không dùng một câu SQL mẫu để giả định hành vi trên tất cả DBMS.

## 6. Chọn đúng kiểu giá trị mặc định

Một mặc định dạng chuỗi, số, boolean, ngày cố định và biểu thức database có ý nghĩa khác nhau. Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-010-account-is-active-default"
      author: "platform"
      changes:
        - addDefaultValue:
            tableName: account
            columnName: is_active
            columnDataType: BOOLEAN
            defaultValueBoolean: true

  - changeSet:
      id: "20261119-011-order-retry-count-default"
      author: "platform"
      changes:
        - addDefaultValue:
            tableName: order_task
            columnName: retry_count
            columnDataType: INTEGER
            defaultValueNumeric: 0

  - changeSet:
      id: "20261119-012-event-created-at-default"
      author: "platform"
      changes:
        - addDefaultValue:
            tableName: event_log
            columnName: created_at
            columnDataType: TIMESTAMP
            defaultValueComputed: CURRENT_TIMESTAMP
~~~

Các changeset chỉ là ví dụ độc lập, giả định bảng/cột đã tồn tại và DBMS hỗ trợ tương ứng. Không chạy chúng trên database thật khi chưa xác nhận schema.

| Nhu cầu | Thuộc tính phù hợp | Giải thích |
|---|---|---|
| Chuỗi cố định **PENDING** | **defaultValue: PENDING** | Database sử dụng literal chuỗi |
| Số nguyên **0** | **defaultValueNumeric: 0** | Database sử dụng literal số |
| Boolean **true** | **defaultValueBoolean: true** | Phụ thuộc cách DBMS ánh xạ boolean |
| Ngày/giờ **cố định** | **defaultValueDate** | Thích hợp cho một mốc ngày/giờ có giá trị cụ thể |
| Thời điểm chèn bản ghi | **defaultValueComputed: CURRENT_TIMESTAMP** | Database đánh giá biểu thức theo thời điểm/thao tác được hỗ trợ |
| Giá trị dựa trên sequence | **defaultValueComputed** với biểu thức đặc thù DBMS | Cú pháp sequence và hỗ trợ mặc định khác nhau theo database |

**defaultValueDate không phải lựa chọn thay thế mặc định cho CURRENT_TIMESTAMP.** Một giá trị ngày cố định và một hàm thời gian được database đánh giá khi INSERT mang ý nghĩa khác nhau. Không dùng dấu nháy không phù hợp khiến biểu thức **CURRENT_TIMESTAMP** trở thành literal chuỗi nếu mục tiêu là lấy thời gian thực tế.

Với sequence, biểu thức mặc định có thể đặc thù DBMS, ví dụ dạng **nextval(...)** trong PostgreSQL. Hãy kiểm tra quy tắc của DBMS, cơ chế identity/auto-increment hiện có và khả năng Liquibase sinh SQL; tránh cấu hình hai cơ chế tự cấp khóa xung đột nhau.

## 7. Khác nhau giữa default trong createTable/addColumn và addDefaultValue

Có ba thời điểm thường gặp để khai báo default:

### 7.1. Khi tạo bảng mới

Có thể đặt default ngay ở phần khai báo cột trong **createTable**:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-020-create-delivery-job"
      author: "platform"
      changes:
        - createTable:
            tableName: delivery_job
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: state
                  type: VARCHAR(20)
                  defaultValue: NEW
                  constraints:
                    nullable: false
~~~

Ở đây default là một phần của định nghĩa cột **state** khi tạo bảng. Không cần thêm một changeset **addDefaultValue** khác chỉ để lặp lại cùng cấu hình.

### 7.2. Khi thêm cột vào bảng có sẵn

**addColumn** cũng có thể khai báo thuộc tính default trong cấu trúc cột. Tuy nhiên, việc thêm cột kèm default vào **bảng đã có dữ liệu** có thể có hành vi và chi phí khác nhau theo DBMS, phiên bản và đặc điểm DDL: metadata-only, ghi lại bảng, khóa, hoặc hiển thị default cho hàng cũ theo cơ chế nội bộ.

Không được mặc định rằng tất cả hàng cũ sẽ được cập nhật vật lý, cũng không được mặc định rằng tất cả hàng cũ vẫn NULL. Hãy kiểm tra trực tiếp trạng thái dữ liệu trước và sau trên DBMS đại diện.

**Phân biệt hai thuộc tính trong addColumn**: **defaultValue** thiết lập giá trị mặc định của cột; còn **value** có thể được dùng để đặt giá trị vào các hàng hiện có theo hành vi của change type. Hai cơ chế này có mục tiêu khác nhau và cần được kiểm chứng.

### 7.3. Khi cột đã tồn tại

Nếu chỉ cần thay cấu hình mặc định của **cột đã có**, **addDefaultValue** là lựa chọn trực tiếp hơn. Nó giữ mục đích changeset rõ ràng và hỗ trợ việc review riêng tác động schema.

| Bối cảnh | Change type điển hình | Điểm cần xác minh |
|---|---|---|
| Tạo bảng lần đầu | **createTable** với default của column | Default được tạo đúng, ràng buộc nhất quán |
| Thêm cột mới vào bảng đã có dữ liệu | **addColumn** với/không với default | Trạng thái của hàng cũ, khóa, chi phí DDL |
| Thêm default cho cột đã tồn tại | **addDefaultValue** | Default áp dụng cho INSERT mới |
| Đổi default cũ sang mới | **addDefaultValue** hoặc chuỗi thao tác phù hợp DBMS | Cách thay thế constraint và rollback |
| Bỏ default | **dropDefaultValue** | Ứng dụng vẫn ghi dữ liệu đúng khi thiếu default |

## 8. Default và backfill dữ liệu: hai mục đích nên tách

Giả sử bảng **customer** đã có hàng triệu dòng với cột **contact_channel** đang NULL. Yêu cầu mới là:

- Khách hàng mới mặc định chọn **EMAIL**.
- Hàng cũ có giá trị NULL phải được chuyển sang **EMAIL**.
- Sau khi ứng dụng ổn định, cột không được phép NULL.

Đây là ba mục đích khác nhau: **thiết lập default**, **backfill dữ liệu**, **siết ràng buộc**. Tách chúng giúp kiểm soát khối lượng cập nhật, điều kiện phát hành và rollback.

### Bước A — Thiết lập default cho bản ghi mới

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-030-customer-channel-default"
      author: "platform"
      changes:
        - addDefaultValue:
            tableName: customer
            columnName: contact_channel
            columnDataType: VARCHAR(16)
            defaultValue: EMAIL
      rollback:
        - dropDefaultValue:
            tableName: customer
            columnName: contact_channel
            columnDataType: VARCHAR(16)
~~~

Bước này giúp những INSERT không cung cấp contact_channel có thể nhận **EMAIL**, nhưng **không sửa các dòng cũ đang NULL**.

### Bước B — Backfill dữ liệu cũ

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-031-customer-channel-backfill"
      author: "platform"
      changes:
        - update:
            tableName: customer
            columns:
              - column:
                  name: contact_channel
                  value: EMAIL
            where: contact_channel IS NULL
~~~

WHERE tránh ghi đè các giá trị không NULL. Tuy vậy, với bảng rất lớn, một UPDATE duy nhất có thể gây khóa, tăng transaction log và tạo áp lực lên replication. Cần cân nhắc job theo lô hoặc kế hoạch backfill riêng, có giám sát và kết quả có thể xác minh.

**Không thể tự động rollback backfill một cách an toàn chỉ bằng cách đổi mọi EMAIL trở về NULL.** Một số hàng có thể vốn đã là EMAIL trước migration hoặc được ứng dụng cập nhật sau đó. Nếu cần đảo chính xác, phải có snapshot hoặc phương án lưu nguồn gốc các dòng được cập nhật.

### Bước C — Áp NOT NULL sau khi dữ liệu và ứng dụng sẵn sàng

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-032-customer-channel-not-null"
      author: "platform"
      preConditions:
        - onFail: HALT
        - sqlCheck:
            expectedResult: "0"
            sql: SELECT COUNT(*) FROM customer WHERE contact_channel IS NULL
      changes:
        - addNotNullConstraint:
            tableName: customer
            columnName: contact_channel
            columnDataType: VARCHAR(16)
      rollback:
        - dropNotNullConstraint:
            tableName: customer
            columnName: contact_channel
            columnDataType: VARCHAR(16)
~~~

Bước này chỉ nên chạy khi tất cả nguồn ghi dữ liệu đã tương thích, và kết quả kiểm tra không còn NULL là đáng tin cậy trong thời điểm triển khai.

**Tách thành ba changeset không tự động tạo ba đợt phát hành.** Nếu cả ba đã có sẵn trong changelog và chạy cùng một lệnh **update**, Liquibase có thể thực hiện chúng liên tiếp. Với hệ thống cần deploy ứng dụng giữa các bước, phải dùng kế hoạch release, labels/contexts hoặc phạm vi artifact có chủ đích để dừng đúng điểm.

## 9. Thiết kế rollback theo trạng thái trước migration

Rollback đúng nghĩa là **khôi phục trạng thái trước bước thay đổi**, không đơn giản là thực hiện một thao tác ngược bất kỳ.

| Thay đổi xuôi | Trạng thái trước | Rollback có chủ đích |
|---|---|---|
| Thêm default **PENDING** | Không có default | **dropDefaultValue** |
| Đổi **PENDING** thành **QUEUED** | Default **PENDING** | **addDefaultValue** với PENDING |
| Xóa default **QUEUED** | Default **QUEUED** | **addDefaultValue** với QUEUED |
| Backfill hàng NULL thành EMAIL | Một số hàng NULL, một số đã EMAIL | Cần dữ liệu đối chiếu/snapshot; không suy ra phép đảo an toàn |
| Thêm NOT NULL | Cột cho phép NULL | **dropNotNullConstraint**, có kiểm tra tính tương thích |

Một số change type có khả năng rollback tự động ở một số phiên bản/DBMS, nhưng điều đó không thay thế việc review tác động thực tế. Đặc biệt, **dropDefaultValue** có thể loại bỏ thông tin về giá trị cũ khỏi schema; nếu không khai báo rollback rõ, không nên giả định Liquibase sẽ tự biết default cũ để khôi phục.

Nếu một changeset đổi default đã được triển khai ở môi trường dùng chung, **không sửa lại chính changeset cũ** để thay giá trị. Thay vào đó, tạo changeset mới với ID riêng, mô tả rõ lý do đổi và phương án rollback. Liquibase dùng **checksum** trong **DATABASECHANGELOG** để phát hiện định nghĩa changeset đã chạy bị chỉnh sửa.

### Một caveat quan trọng về rollback theo DBMS

Database có thể lưu default dưới dạng constraint, biểu thức hoặc metadata có cú pháp riêng. Việc rollback **addDefaultValue** có thể cần biết tên default constraint; rollback **dropDefaultValue** có thể cần xây dựng lại biểu thức đúng kiểu. Hãy luôn xem SQL rollback và thử trên đúng DBMS.

Rollback migration cũng không đảm bảo ứng dụng cũ tương thích với dữ liệu do ứng dụng mới đã ghi. Nếu app mới tạo trạng thái **QUEUED** và sau đó rollback default về **PENDING**, những dòng QUEUED đã lưu vẫn còn. Quy trình rollback phải đánh giá cả schema, dữ liệu lẫn phiên bản ứng dụng.

## 10. Khác biệt đáng chú ý giữa các DBMS

Không có một cú pháp ALTER DEFAULT duy nhất áp dụng cho tất cả hệ quản trị. Liquibase giảm nhu cầu tự viết SQL theo từng DBMS, nhưng không loại bỏ yêu cầu kiểm chứng.

| DBMS | Điều cần quan tâm khi thay default |
|---|---|
| **PostgreSQL** | Thường có **ALTER TABLE ... ALTER COLUMN ... SET DEFAULT / DROP DEFAULT**. Biểu thức có thể dùng CURRENT_TIMESTAMP hoặc hàm DBMS; kiểm tra kiểu và implicit cast |
| **MySQL/MariaDB** | Hành vi ALTER và biểu thức default phụ thuộc phiên bản, engine và kiểu cột; **columnDataType** có thể quan trọng khi Liquibase dựng DDL |
| **Microsoft SQL Server** | Default thường là **default constraint**; cần quan tâm tên constraint khi thay hoặc xóa; cùng cột không thể có các constraint default chồng lên nhau |
| **Oracle** | Hỗ trợ mặc định theo cú pháp riêng; kiểu DATE/TIMESTAMP, sequence và biểu thức cần kiểm tra tương thích |
| **H2 hoặc database thử nghiệm khác** | Dễ dùng cho kiểm thử nhanh, nhưng không thể thay thế kiểm thử trên DBMS production vì DDL và kiểu dữ liệu có thể khác |

Ví dụ SQL Server: khi tạo default constraint cho một cột, việc đặt tên ổn định giúp quản trị và rollback dễ hơn. Liquibase hỗ trợ thuộc tính liên quan như **defaultValueConstraintName** trong những phiên bản có tính năng đó. Đây **không phải** một thuộc tính có thể trông đợi hoạt động như nhau trên mọi DBMS.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-040-invoice-status-default-mssql"
      author: "platform"
      dbms: mssql
      changes:
        - addDefaultValue:
            tableName: invoice
            columnName: status
            columnDataType: VARCHAR(24)
            defaultValue: PENDING
            defaultValueConstraintName: df_invoice_status
~~~

Ví dụ chỉ dành cho SQL Server và chỉ nên dùng khi runtime Liquibase hỗ trợ thuộc tính đó. Nếu dự án hỗ trợ nhiều DBMS, cần quyết định liệu có thể dùng một changeset portable hay phải tách changeset theo **dbms**. Không tự sao chép SQL Server constraint syntax sang PostgreSQL.

Với **defaultValueComputed**, khả năng biểu diễn biểu thức có thể thay đổi theo loại DBMS và phiên bản Liquibase. Kiểm tra tài liệu tương ứng, câu SQL được sinh, rồi thử INSERT. Một biểu thức chạy được trong câu SELECT chưa chắc được DBMS cho phép làm default của cột.

## 11. Cách kiểm chứng default sau khi triển khai

Kiểm tra default cần hai loại bằng chứng: **metadata của cột** đã đổi và **hành vi INSERT** của database đúng kỳ vọng.

### 11.1. Kiểm tra trước khi chạy migration

Sử dụng đúng artifact changelog và phiên bản Liquibase của môi trường:

~~~bash
liquibase --version
liquibase validate
liquibase status --verbose
liquibase update-sql
~~~

- **validate** kiểm tra cấu trúc changelog và quy tắc validation mà Liquibase hỗ trợ.
- **status --verbose** xem changeset nào đang chờ được áp dụng.
- **update-sql** xem SQL Liquibase dự kiến tạo; giúp nhận ra DDL khác nhau theo DBMS, đặc biệt là cách tạo/xóa default constraint.

Các lệnh trên cần cấu hình URL, credentials, changelog, context/label phù hợp với database thử nghiệm. Tên tham số có thể khác tùy phiên bản; không dùng production chỉ để thử nghiệm DDL.

### 11.2. Kiểm tra metadata sau khi update

Có thể dùng truy vấn từ catalog của DBMS, công cụ quản trị schema, hoặc một báo cáo **snapshot** phù hợp của Liquibase để xác định cột đang có default nào. Ví dụ với PostgreSQL:

~~~sql
SELECT
    column_name,
    column_default,
    is_nullable,
    data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'invoice'
  AND column_name = 'status';
~~~

Kết quả cần xác nhận default đúng giá trị hoặc biểu thức mong đợi. Lưu ý biểu thức trong catalog có thể được DBMS chuẩn hóa, thêm kiểu cast hoặc thay đổi hình thức hiển thị; không nên so sánh chuỗi hiển thị bằng phép so sánh văn bản quá cứng nhắc.

### 11.3. Kiểm tra hành vi INSERT

Trên database thử nghiệm:

1. Chèn bản ghi **không truyền cột** có default.
2. Đọc lại để xác nhận DBMS cấp default mong đợi.
3. Chèn bản ghi **truyền giá trị cụ thể**, xác nhận giá trị tường minh được giữ.
4. Nếu cột nullable, thử truyền **NULL tường minh** để quan sát quy tắc thực tế.
5. Sau khi đổi hoặc xóa default, lặp lại các trường hợp tương ứng.
6. Kiểm tra dữ liệu cũ không bị đổi ngoài ý muốn.

Đừng chạy thử INSERT trực tiếp lên bảng production nếu không có kế hoạch dữ liệu và cleanup phù hợp. Với cột thời gian và default tính toán, cần kiểm tra timezone, độ chính xác và thời điểm database đánh giá biểu thức.

### 11.4. Kiểm chứng rollback

Nếu changeset có khai báo rollback, cần xem SQL rollback (theo cú pháp CLI của phiên bản đang dùng) và thử trên database riêng. Quan sát **trạng thái default trước/sau rollback** và xem những dòng dữ liệu đã tạo trong lúc default mới đang hoạt động có còn phù hợp yêu cầu nghiệp vụ không.

Một phép thử chỉ xác nhận changelog parse được không chứng minh rollback sẽ hoạt động hoặc khôi phục đúng giá trị cũ.

## 12. Tích hợp Spring Boot và CI/CD

Với ứng dụng Spring Boot, Liquibase có thể chạy khi khởi động nếu được bật và có changelog trên classpath:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
~~~

Khi ứng dụng mở kết nối và chạy migration, Liquibase sẽ đối chiếu các changeset với **DATABASECHANGELOG**. Vì thế, việc đổi default nên được phát hành như một changeset mới, không sửa nội dung changeset cũ đã chạy để tránh sai khác checksum.

Một trình tự phát hành an toàn cho thay đổi default:

1. **Xác định luồng ghi**: ứng dụng/ORM có bỏ qua cột để database áp default hay luôn truyền giá trị, kể cả NULL?
2. **Kiểm tra tương thích**: nếu đổi default làm thay đổi ý nghĩa nghiệp vụ, các phiên bản ứng dụng cũ và mới có đọc/xử lý giá trị mới được không?
3. **Tạo changeset chuyên biệt**: nêu rõ trạng thái default trước/sau, điều kiện áp dụng, rollback và DBMS.
4. **Chạy validate/update-sql** trên database hoặc bản sao phù hợp; review SQL sinh ra.
5. **Chạy update** trên môi trường thử nghiệm đã có lịch sử tương tự production.
6. **Kiểm tra metadata và INSERT** trước khi đẩy sang môi trường kế tiếp.
7. **Lưu artifact, commit, Liquibase version và kết quả triển khai** để truy nguyên.
8. **Triển khai có kiểm soát**: chỉ định job migration hoặc cách khởi động ứng dụng rõ ràng; tránh để nhiều nơi dùng cấu hình Liquibase khác nhau.

Nếu vừa đổi default vừa chuẩn hóa dữ liệu cũ, nên tách thành các bước với cửa kiểm tra riêng. Không thay đổi default cùng lúc với thao tác phá vỡ tương thích ứng dụng khi chưa có kế hoạch triển khai theo giai đoạn.

**Điểm cần nhớ về ORM:** JPA/Hibernate, các thư viện SQL và bulk importer có thể luôn đưa cột vào câu INSERT. Khi chúng truyền giá trị cụ thể hoặc NULL, default của database có thể không được sử dụng. Đừng chỉ kiểm tra schema mà bỏ qua câu SQL do ứng dụng thực tế phát sinh.

## 13. Các lỗi thường gặp và cách xử lý

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Đã thêm default nhưng dữ liệu cũ vẫn NULL | addDefaultValue không phải backfill | Tạo migration cập nhật dữ liệu riêng, kiểm chứng số dòng |
| INSERT mới vẫn cho NULL | Ứng dụng truyền NULL rõ ràng; cột cho phép NULL | Kiểm tra SQL thực tế và quy tắc NOT NULL |
| Đổi default từ PENDING sang QUEUED nhưng ứng dụng vẫn tạo PENDING | Ứng dụng truyền PENDING tường minh | Sửa cấu hình luồng ghi hoặc cách sử dụng default |
| ALTER thất bại trên SQL Server | Default constraint cũ còn tồn tại hoặc tên constraint khác dự kiến | Kiểm tra catalog, SQL sinh ra và kế hoạch drop/add constraint |
| SQL chạy trên H2 nhưng lỗi trên production | Khác DBMS, driver hoặc biểu thức default | Kiểm thử trên DBMS production tương đương |
| Dùng CURRENT_TIMESTAMP nhưng database lưu chuỗi chữ | Dùng literal thay vì biểu thức computed | Dùng thuộc tính biểu thức phù hợp, kiểm tra SQL sinh ra |
| Rollback đổi default thành không có default | Đã dùng dropDefaultValue trong rollback của bước thay giá trị | Khôi phục default trước migration bằng addDefaultValue |
| Changeset báo checksum mismatch | Sửa nội dung changeset đã chạy | Khôi phục changeset cũ và thêm changeset mới |
| Xóa default khiến ứng dụng lỗi khi INSERT | Cột NOT NULL, client bỏ qua cột | Triển khai ứng dụng cung cấp giá trị trước khi xóa default |
| Thêm default nhưng không có tác dụng trên một môi trường | Chưa áp dụng migration hoặc dùng sai schema/database | Kiểm tra URL, schema, DATABASECHANGELOG và catalog |

Không nên xử lý lỗi bằng cách xóa checksum hoặc chỉnh tay dòng lịch sử mà chưa tìm nguyên nhân. Cần biết rõ sai ở **định nghĩa changelog**, **cấu hình triển khai**, **SQL được DBMS hỗ trợ** hay **câu INSERT của ứng dụng**.

## 14. Bài thực hành từng bước

Thực hiện trên database thử nghiệm độc lập; chọn DBMS và phiên bản Liquibase giống môi trường cần triển khai nếu có thể.

**Bài toán:** Bảng **invoice** có cột **status VARCHAR(24)** nullable, chưa có default. Giả sử dữ liệu cũ đã có một số trạng thái khác nhau.

**Giai đoạn 1 — Thêm default**

- Tạo changeset **addDefaultValue** với **PENDING**.
- Xem SQL bằng **update-sql**, triển khai lên database thử nghiệm.
- Chèn một hóa đơn mà không truyền status, xác nhận kết quả.
- Đọc lại các hóa đơn trước migration, xác nhận không bị tự thay đổi.

**Giai đoạn 2 — Đổi default**

- Tạo changeset mới với **QUEUED**, khai báo rollback đưa về **PENDING**.
- Chạy migration và thử tạo hóa đơn mới.
- Đọc lại hóa đơn PENDING trước đó, xác nhận chúng vẫn là PENDING.
- Kiểm chứng vì sao application-level default có thể ghi đè hành vi này.

**Giai đoạn 3 — Xóa default**

- Tạo changeset **dropDefaultValue**, rollback sẽ khôi phục **QUEUED**.
- Chạy migration; kiểm tra metadata cột không còn default.
- Thử INSERT không truyền status vào bảng nullable; quan sát kết quả.
- Thử lại khi cấu trúc của bài tập có NOT NULL, chỉ trên database thử nghiệm để quan sát lỗi/điều kiện hợp lệ.

**Giai đoạn 4 — Rollback**

- Dùng khả năng rollback phù hợp của phiên bản Liquibase trên database thử nghiệm để đảo bước xóa default.
- Xác nhận metadata trở về **QUEUED**, không phải **PENDING** hoặc **không default**.
- Thảo luận vì sao các dòng đã được chèn trong thời gian default QUEUED tồn tại vẫn không tự đổi thành giá trị khác.

Kết quả được coi là đúng khi người học có thể giải thích độc lập **giá trị default của schema**, **giá trị thực lưu trong các hàng** và **hành vi của ứng dụng khi INSERT**, thay vì coi ba thứ là một.

## 15. Checklist review migration thay đổi default

Trước khi merge hoặc chạy migration, hãy xác nhận:

- Đã xác định đúng bảng, schema, cột, kiểu dữ liệu và trạng thái default hiện tại.
- Thao tác là **thêm**, **đổi** hay **xóa** default; mô tả rõ mục đích changeset.
- Đã dùng đúng một thuộc tính **defaultValue...** phù hợp kiểu giá trị hay biểu thức.
- Đã xác nhận default là literal hay biểu thức được database đánh giá.
- Đã phân biệt tác động đến INSERT mới với dữ liệu cũ và giá trị NULL.
- Nếu cần backfill hoặc NOT NULL, đã tách kế hoạch và kiểm chứng riêng.
- Đã kiểm tra hành vi của ORM/application, đặc biệt việc truyền giá trị hoặc NULL tường minh.
- Đã xem SQL sinh ra trên DBMS và phiên bản Liquibase dự kiến triển khai.
- Với SQL Server, đã xử lý default constraint và tên constraint theo tình trạng thực tế.
- Đã chuẩn bị rollback khôi phục **đúng default trước migration**, không chỉ xóa default tùy tiện.
- Đã thử migration lẫn rollback trên database đại diện; kiểm tra metadata và INSERT.
- Đã giữ nguyên những changeset đã được ghi nhận, dùng changeset mới cho yêu cầu tiếp theo.

**Kết luận:** Trong Liquibase, **addDefaultValue** thiết lập hoặc thay đổi giá trị mặc định của cột, còn **dropDefaultValue** loại bỏ mặc định đó. Cốt lõi của migration an toàn là hiểu rằng **default là quy tắc schema cho thao tác ghi trong tương lai**, không tự thay thế mọi NULL hoặc dữ liệu hiện có. Khi có thay đổi nghiệp vụ, hãy mô tả rõ trạng thái trước/sau, chọn kiểu giá trị chính xác, kiểm tra SQL theo DBMS, chuẩn bị rollback đúng nghĩa và phối hợp ứng dụng với quy trình triển khai nhiều môi trường.

