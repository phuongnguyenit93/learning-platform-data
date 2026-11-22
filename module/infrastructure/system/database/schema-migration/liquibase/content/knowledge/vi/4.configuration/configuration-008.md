# Tách cấu hình phát triển, kiểm thử và production

## 1. Vì sao phải tách cấu hình theo môi trường?

Trong vòng đời phần mềm, cùng một bộ thay đổi lược đồ thường được áp dụng nhiều lần: trên máy lập trình viên, cơ sở dữ liệu dùng cho kiểm thử tích hợp và cuối cùng là cơ sở dữ liệu production. Mục đích của những lần chạy này giống nhau — đưa schema và dữ liệu tham chiếu tới trạng thái mong muốn — nhưng **đích kết nối, tài khoản, quyền, dữ liệu hiện có và mức kiểm soát** không giống nhau.

Liquibase giúp mô tả thay đổi bằng **changelog** và **changeset**, đối chiếu chúng với lịch sử trong bảng **DATABASECHANGELOG**, kiểm tra điều kiện bằng **precondition** và phát hiện changeset lịch sử bị sửa bằng **checksum**. Để dùng các cơ chế đó an toàn, nhóm cần một chiến lược cấu hình nhất quán giữa các môi trường.

Bài này thuộc chương **Cấu hình** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Mục tiêu học tập của module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài tập trung vào câu hỏi: **giữ chung một lịch sử migration nhưng cấu hình Liquibase khác nhau cho phát triển, kiểm thử và production như thế nào?**

Sau bài học, bạn cần biết cách:

1. Phân loại những thông tin nên dùng chung và những thông tin phải tách theo môi trường.
2. Cấu hình Liquibase CLI để kết nối đúng database mà không đưa mật khẩu vào mã nguồn.
3. Dùng contexts, labels và properties đúng mục đích, đồng thời hiểu giới hạn bảo vệ của chúng.
4. Tổ chức cấu hình Spring Boot và CI/CD sao cho một tiến trình chịu trách nhiệm migration.
5. Thiết lập bước kiểm tra trước khi chạy và tiêu chí xác nhận sau khi triển khai.
6. Phát hiện lỗi trỏ nhầm môi trường, sai schema, thiếu quyền hoặc lịch sử migration lệch nhau.

## 2. Phân biệt những môi trường thường gặp

| Tiêu chí | Development (dev) | Testing (test) | Production (prod) |
|---|---|---|---|
| Mục đích | Phát triển và thử thay đổi nhanh | Xác minh schema, dữ liệu và tương thích ứng dụng | Phục vụ người dùng và dữ liệu thật |
| Dữ liệu | Dữ liệu giả hoặc dữ liệu mẫu | Dữ liệu kiểm thử có thể tái tạo; có thể dùng tập dữ liệu đã ẩn danh | Dữ liệu nghiệp vụ thật, cần bảo vệ |
| Migration | Có thể chạy nhiều lần trong quá trình phát triển | Chạy tự động, có kết quả kiểm thử rõ ràng | Chạy theo quy trình phát hành được kiểm soát |
| Tài khoản | Giới hạn trong database/schema dev | Giới hạn trong database/schema test | Tài khoản migration riêng với quyền tối thiểu cần thiết |
| Rollback | Thực hành trên dữ liệu giả | Kiểm thử phương án rollback hoặc khôi phục | Đánh giá mất dữ liệu, backup, kế hoạch sự cố |
| Xác thực và secret | Secret cục bộ không đưa lên Git | Secret do runner/CI cấp | Secret do hệ thống quản lý bí mật cấp, có kiểm soát truy cập |
| Theo dõi | Log phát triển | Log chạy test và chứng cứ kiểm thử | Nhật ký triển khai, phiên bản phát hành, người phê duyệt, cảnh báo |

Một tổ chức có thể bổ sung **staging** hoặc **pre-production**, thường cố gắng mô phỏng production để tập dượt triển khai. Không nên coi môi trường staging là production chỉ vì có dữ liệu tương tự; quyền truy cập và đích kết nối vẫn phải khác biệt.

**Nguyên tắc thiết kế:** sử dụng cùng các changeset đã được review cho chuỗi dev → test → production, nhưng cấp cấu hình vận hành của từng môi trường tại thời điểm chạy. Việc chuyển môi trường không nên yêu cầu chỉnh sửa changeset đã áp dụng ở môi trường trước.

## 3. Xác định rõ cấu hình chung và cấu hình riêng

Một triển khai Liquibase có các nhóm thông tin khác nhau:

| Nhóm thông tin | Dùng chung hay tách riêng? | Ví dụ |
|---|---|---|
| Changelog gốc và các changeset bắt buộc | **Dùng chung** theo phiên bản mã nguồn | db/changelog/db.changelog-master.yaml |
| Phiên bản Liquibase, Java, JDBC driver | **Cố định theo bộ công cụ đã kiểm thử** | Bộ phiên bản trong image CI |
| JDBC URL | **Tách riêng** | shop_dev, shop_test, shop_prod trên các máy chủ khác nhau |
| Username, password, chứng chỉ | **Tách riêng**; cấp qua secret | Tài khoản lb_dev, lb_test, lb_prod |
| Schema mặc định hoặc schema lưu lịch sử | Theo quy ước; có thể **khác theo môi trường** | public hoặc app_schema |
| Context filter | **Chọn rõ khi chạy** | dev, test, prod |
| Label filter | Theo chính sách triển khai | release, dữ liệu mẫu hoặc nhóm changeset tùy chọn |
| Log, cảnh báo, timeout, mức song song | **Tùy môi trường** | Production kiểm soát chặt hơn |
| Cơ chế phê duyệt và backup | **Tùy rủi ro** | Production yêu cầu kiểm tra trước và kế hoạch khôi phục |

Ví dụ, việc thêm cột orders.note là thay đổi schema nghiệp vụ và nên xuất hiện trong cùng changelog trên mọi môi trường cần cột đó. Ngược lại, tạo một khách hàng giả để demo chỉ có ý nghĩa trong dev; nhóm cần xác định rõ có chạy changeset dữ liệu mẫu này ở đâu.

Không nên giải quyết sự khác biệt môi trường bằng cách duy trì ba bản sao changelog phát triển, kiểm thử và production rồi sửa tay từng tệp. Sau một thời gian, chuỗi changeset sẽ lệch nhau và không còn dễ xác định môi trường nào đã chạy phiên bản nào.

## 4. Kiến trúc cấu hình được khuyến nghị

Có thể tổ chức một dự án theo cách sau (đây là **cấu trúc ví dụ**, không yêu cầu tạo các tệp riêng cho bài học):

~~~text
project/
├── db/
│   └── changelog/
│       ├── db.changelog-master.yaml
│       └── changes/
│           ├── 001-create-orders.yaml
│           ├── 002-add-order-note.yaml
│           └── 003-insert-reference-status.yaml
├── config/
│   └── liquibase.properties
└── src/
    └── main/
        └── resources/
            ├── application.yaml
            ├── application-dev.yaml
            ├── application-test.yaml
            └── application-prod.yaml
~~~

Changelog là **tài sản phiên bản hóa**: mọi môi trường chạy cùng revision Git hoặc cùng artifact đã kiểm thử. Tệp properties chung có thể chỉ khai báo những giá trị không nhạy cảm và không thay đổi theo môi trường.

Ví dụ nội dung config/liquibase.properties:

~~~properties
changeLogFile=db/changelog/db.changelog-master.yaml
logLevel=info
~~~

Các thông tin URL, username và password được cung cấp từ môi trường chạy, chẳng hạn từ biến môi trường của tiến trình Liquibase hoặc secret của CI/CD. Nhờ đó, cùng một lệnh logic có thể chạy trên dev, test và prod mà không chỉnh sửa nội dung changelog hay commit mật khẩu.

**Lưu ý về phạm vi:** một số tùy chọn CLI và tên thuộc tính thay đổi giữa các phiên bản Liquibase. Khi chuẩn hóa dự án, hãy cố định phiên bản CLI và kiểm tra cách đặt tên, thứ tự ưu tiên của tệp properties, biến môi trường và command line trên chính phiên bản đó. Không phụ thuộc vào giả định ngầm về cách công cụ hợp nhất nhiều nguồn cấu hình.

## 5. Cấu hình Liquibase CLI cho từng môi trường

### 5.1. Mẫu dùng biến môi trường

Với Liquibase CLI tương thích, các biến môi trường liên quan đến lệnh kết nối thường gồm:

- **LIQUIBASE_COMMAND_URL**: JDBC URL của database đích.
- **LIQUIBASE_COMMAND_USERNAME**: người dùng database.
- **LIQUIBASE_COMMAND_PASSWORD**: mật khẩu database, nhận từ secret manager hoặc hệ thống cấp secret.
- Các tùy chọn khác như driver, classpath hoặc schema theo yêu cầu của dự án.

Ví dụ cấu hình trong một phiên **PowerShell dành riêng cho dev**:

~~~powershell
$env:LIQUIBASE_COMMAND_URL = "jdbc:postgresql://localhost:5432/shop_dev"
$env:LIQUIBASE_COMMAND_USERNAME = "lb_dev"

# Password được cấp an toàn bởi môi trường hoặc secret manager.
# Không in hay gõ mật khẩu thật vào mã nguồn và log.

liquibase --defaults-file=config/liquibase.properties validate
liquibase --defaults-file=config/liquibase.properties status --verbose
~~~

Hai lệnh ở trên chỉ có thể thành công nếu PostgreSQL đang chạy, JDBC driver tương thích được Liquibase nạp và tài khoản có quyền cần thiết. Nếu bản CLI không đóng gói sẵn driver tương ứng, hãy thêm JDBC JAR vào classpath đúng theo bản phân phối đang sử dụng.

**Quan trọng:** biến môi trường tồn tại trong phạm vi tiến trình hoặc phiên terminal. Không nên đặt biến chứa mật khẩu trong profile shell được đồng bộ lên Git, in nội dung secret ra console hoặc để runner không đáng tin cậy truy cập chúng.

### 5.2. Thay đổi đích kết nối, giữ nguyên changelog

Khi chuyển sang test, pipeline thay các biến kết nối cho database test, ví dụ:

~~~text
LIQUIBASE_COMMAND_URL=jdbc:postgresql://test-db.internal:5432/shop_test
LIQUIBASE_COMMAND_USERNAME=lb_test
LIQUIBASE_COMMAND_PASSWORD=<giá trị cấp riêng bởi kho secret test>
~~~

Khi chuyển sang production, pipeline cấp thông tin tương ứng từ secret production:

~~~text
LIQUIBASE_COMMAND_URL=jdbc:postgresql://prod-db.internal:5432/shop_prod
LIQUIBASE_COMMAND_USERNAME=lb_prod
LIQUIBASE_COMMAND_PASSWORD=<giá trị cấp riêng bởi kho secret production>
~~~

Các tên máy chủ và giá trị trong dấu ngoặc nhọn là minh họa, không phải hệ thống tồn tại thật; tuyệt đối không ghi giá trị secret thật vào tệp nguồn. Một người có quyền chạy pipeline test không nên mặc nhiên có quyền truy cập secret production.

Điểm quan trọng nhất là **artifact và changelog giữ nguyên**, còn thông tin đích được cấp theo môi trường chạy. Việc một pipeline hiện tên “deploy test” không đủ để chứng minh kết nối an toàn: phải xác nhận JDBC URL, tài khoản và database hiện tại.

### 5.3. Tệp cấu hình riêng có thể sử dụng khi nào?

Trong trường hợp muốn thấy rõ sự khác biệt không nhạy cảm, có thể có các tệp ví dụ dành riêng cho dev/test/prod, mỗi tệp khai báo URL hoặc schema mặc định nhưng **không chứa password**. Cách này phù hợp nếu policy cho phép commit tên database và host nội bộ; với hệ thống cần che giấu topology, ngay cả URL cũng nên cấp bằng secret hoặc cấu hình runtime.

Một cấu hình chỉ nên có **một nguồn quyết định cuối cùng** cho mỗi thuộc tính; nếu vừa có URL trong file vừa có URL ở biến môi trường, người vận hành cần hiểu chính xác nguồn nào thắng theo phiên bản CLI đang dùng. Lỗi thứ tự ưu tiên là nguyên nhân phổ biến khiến triển khai “đúng tên job nhưng sai database”.

### 5.4. Kiểm tra trước khi chạy update

Có thể thực hiện theo thứ tự:

~~~powershell
# Bước 1: kiểm tra cấu hình/changelog theo phạm vi Liquibase hỗ trợ
liquibase --defaults-file=config/liquibase.properties validate

# Bước 2: xem changeset chưa được áp dụng ở database đích
liquibase --defaults-file=config/liquibase.properties status --verbose

# Bước 3: xem SQL dự kiến trước khi thực thi
liquibase --defaults-file=config/liquibase.properties update-sql
~~~

Lệnh **update-sql** sinh SQL để review nhưng không thay thế việc thử trên dữ liệu đại diện. Trong tài liệu và ví dụ ở những phiên bản khác nhau, tên lệnh có thể được hiển thị theo kiểu updateSQL; nhóm phải thống nhất cú pháp CLI của bản đã cố định.

Trước khi phát hành production, quy trình cần kiểm tra thêm danh tính cơ sở dữ liệu được kết nối, schema mục tiêu và quyền của tài khoản migration. Những bước đó có thể được triển khai qua công cụ quản trị DB hoặc một job kiểm tra độc lập, không cần chạy thay đổi lược đồ.

## 6. Changelog chung và lịch sử riêng của từng database

Giả sử changelog gốc có ba changeset bắt buộc:

~~~yaml
databaseChangeLog:
  - include:
      file: db/changelog/changes/001-create-orders.yaml
  - include:
      file: db/changelog/changes/002-add-order-note.yaml
  - include:
      file: db/changelog/changes/003-insert-reference-status.yaml
~~~

Khi triển khai:

- Ở dev, cả ba changeset có thể đã được áp dụng.
- Ở test, có thể chỉ mới áp dụng hai changeset đầu.
- Ở production, có thể chưa áp dụng bản cập nhật mới.

Mỗi database duy trì bảng **DATABASECHANGELOG** riêng để ghi changeset đã xử lý, cùng thông tin như id, author, đường dẫn changelog, thời điểm chạy và checksum. Liquibase đối chiếu changelog với bảng lịch sử **của đúng database đang kết nối**, nên cùng một artifact có thể cập nhật mỗi môi trường đến trạng thái phù hợp.

**DATABASECHANGELOGLOCK** được dùng để điều phối các lượt cập nhật trên cùng một database. Cơ chế khóa hạn chế xung đột khi nhiều tiến trình Liquibase chạy song song, nhưng không thay thế một quy trình phát hành có người chịu trách nhiệm.

Không nên:

- Sao chép bảng DATABASECHANGELOG từ dev sang production để “đánh dấu cho nhanh”.
- Xóa lịch sử trên production chỉ vì một changeset bị lỗi checksum.
- Sửa nội dung changeset đã triển khai ở dev/test rồi dùng cùng id để chạy production.
- Sửa thủ công schema production mà không phản ánh thay đổi đó qua quy trình kiểm soát migration.

Nếu cần điều chỉnh sau một changeset đã chạy, tạo changeset mới và kiểm chứng trên các môi trường trước khi phát hành. Điều này giữ lịch sử có thể tái dựng và tránh checksum lệch.

## 7. Contexts: chọn những changeset theo ngữ cảnh

**Contexts** cho phép gắn điều kiện chạy cho changeset. Chẳng hạn, dữ liệu demo chỉ nên tồn tại ở dev; dữ liệu phục vụ một bộ test cụ thể chỉ nên chạy trong môi trường thử nghiệm.

Ví dụ dùng cú pháp contextFilter trong Liquibase hiện đại, giả định bảng demo_customer đã được tạo bởi một changeset khác:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: seed-demo-customer-001
      author: training-team
      contextFilter: "@dev"
      changes:
        - insert:
            tableName: demo_customer
            columns:
              - column:
                  name: customer_code
                  value: DEMO-001
              - column:
                  name: display_name
                  value: Khách hàng mẫu
      rollback:
        - delete:
            tableName: demo_customer
            where: "customer_code = 'DEMO-001'"
~~~

Ký hiệu **@dev** yêu cầu context phù hợp được chỉ định tường minh khi chạy; đây là cách giảm nguy cơ dữ liệu mẫu được chạy khi pipeline bỏ quên bộ lọc. Tên thuộc tính và cú pháp chính xác cần được đối chiếu với phiên bản Liquibase đang dùng; một số ví dụ cũ dùng context thay cho contextFilter.

Ví dụ chạy ở dev:

~~~powershell
liquibase --defaults-file=config/liquibase.properties --context-filter=dev status --verbose
liquibase --defaults-file=config/liquibase.properties --context-filter=dev update-sql
~~~

Khi dùng contextFilter, phải phân biệt hai loại changeset:

1. **Migration nghiệp vụ bắt buộc**, như tạo bảng orders: thông thường cần chạy trên mọi môi trường và không nên bị loại do bộ lọc bị cấu hình sai.
2. **Migration tùy chọn hoặc dữ liệu mẫu**, như bản ghi demo: có thể gắn context và yêu cầu chọn đúng ngữ cảnh.

**Một hiểu lầm quan trọng:** không phải mọi changeset có context đều tự động bị loại khi lệnh update không truyền context. Theo hành vi của Liquibase, nếu không chỉ định bộ lọc context, nhiều changeset có khai báo context vẫn có thể được xét chạy; dấu @ có ý nghĩa yêu cầu context tường minh. Vì vậy, không dùng việc đặt tên context là hàng rào bảo vệ duy nhất cho production. Thiết kế quyền database, kiểm tra đích và pipeline có kiểm soát vẫn là điều kiện bắt buộc.

## 8. Labels: lựa chọn thay đổi theo mục đích phát hành

**Labels** là metadata gắn với changeset để hỗ trợ chọn một nhóm thay đổi thông qua **label filter** khi chạy Liquibase. Labels hữu ích khi nhóm muốn quản lý một số changeset tùy chọn, một luồng thử nghiệm hoặc một đợt triển khai có quy ước rõ ràng.

Ví dụ changeset có thể gắn label:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: create-optional-report-view
      author: reporting-team
      labels: reporting
      changes:
        - createView:
            viewName: order_summary_view
            replaceIfExists: true
            selectQuery: SELECT status, COUNT(*) AS total FROM orders GROUP BY status
~~~

Lệnh sử dụng label filter (nếu phù hợp với phiên bản Liquibase):

~~~powershell
liquibase --defaults-file=config/liquibase.properties --label-filter=reporting status --verbose
~~~

**Không dùng label để thay thế quản lý phiên bản.** Labels không biến changeset trở thành một nhánh mã nguồn độc lập và không đảm bảo mọi môi trường sẽ tự động chạy đúng các thay đổi bắt buộc. Nếu không truyền label filter, những changeset có label vẫn có thể được chạy tùy theo quy tắc lọc; cần cấu hình và kiểm thử hành vi thực tế.

Với schema cốt lõi mà ứng dụng phụ thuộc, phương án dễ kiểm soát hơn thường là cho changeset chạy theo thứ tự changelog mà không phụ thuộc nhãn tùy chọn. Labels nên phục vụ một chính sách có lý do nghiệp vụ rõ ràng, được kiểm chứng trong CI.

## 9. Properties và tham số khác nhau theo môi trường

Ngoài URL và secret, Liquibase có thể cần các tham số như:

- **defaultSchemaName**: schema mặc định mà các thay đổi có thể nhắm tới khi không chỉ định schema riêng.
- **liquibaseSchemaName**: schema được dùng cho các bảng theo dõi của Liquibase trong cấu hình hỗ trợ.
- **driver** và **classpath**: giúp CLI tìm JDBC driver khi bộ cài không cung cấp sẵn.
- Context/label filter, timeout và mức log tùy chính sách phát hành.

Ví dụ giả định một dự án có schema ứng dụng tên app_schema. Nếu dev mặc định dùng public còn production dùng app_schema, một changeset không khai báo schema có thể tạo bảng ở hai nơi khác nhau. Vì vậy, nhóm nên thống nhất schema mục tiêu và kiểm tra quyền tạo bảng ở schema đó.

**Thay đổi schema lưu bảng DATABASECHANGELOG một cách tùy tiện đặc biệt nguy hiểm.** Nếu Liquibase chuyển sang tra cứu một bảng lịch sử khác với bảng đã dùng trước đó, công cụ có thể hiểu nhầm các changeset cũ là chưa chạy. Trước khi đổi các tùy chọn điều khiển nơi lưu lịch sử, cần có kế hoạch chuyển đổi trạng thái được review.

Trong changelog, cũng có thể sử dụng properties để tránh nhân bản SQL khi một giá trị kỹ thuật thực sự cần thay đổi theo DBMS hoặc môi trường. Tuy nhiên, properties không nên làm cùng changeset mang hai ý nghĩa nghiệp vụ khác nhau. Chẳng hạn, một changeset thêm cột bắt buộc không nên bị thay đổi thành thao tác khác chỉ vì đang chạy ở dev hay production.

## 10. Tách môi trường trong Spring Boot

Nếu ứng dụng dùng Spring Boot cùng liquibase-core, có thể lưu đường dẫn changelog chung trong application.yaml và đặt khác biệt vận hành trong các profile:

~~~yaml
# application.yaml
spring:
  liquibase:
    change-log: classpath:db/changelog/db.changelog-master.yaml
~~~

Khi muốn Spring Boot chạy migration tự động ở dev:

~~~yaml
# application-dev.yaml
spring:
  liquibase:
    enabled: true
~~~

Nếu production giao migration cho một job CI/CD riêng, có thể tắt cơ chế tự chạy Liquibase trong tiến trình ứng dụng production:

~~~yaml
# application-prod.yaml
spring:
  liquibase:
    enabled: false
~~~

Các đoạn YAML trên nằm trong **những file profile khác nhau** ở ví dụ, không được ghép ba đối tượng spring vào cùng một file như các khóa trùng nhau. Profile phải được kích hoạt đúng khi chạy ứng dụng; việc đặt tên application-prod.yaml tự nó không bảo đảm được nạp.

Thông tin datasource có thể được cấp bằng biến môi trường hay secret manager theo cơ chế cấu hình Spring Boot, chẳng hạn SPRING_DATASOURCE_URL, SPRING_DATASOURCE_USERNAME và SPRING_DATASOURCE_PASSWORD. Không nên commit mật khẩu trong profile.

**Chọn một chủ sở hữu migration cho mỗi lần phát hành:**

- Nếu **ứng dụng khởi động rồi tự chạy Liquibase**, phải cân nhắc thời gian startup, nhiều replica cùng khởi động và khả năng tương thích giữa các phiên bản ứng dụng.
- Nếu **pipeline chạy Liquibase trước**, ứng dụng production nên được cấu hình rõ ràng để không tự chạy cùng một luồng migration ngoài kế hoạch.

Liquibase có cơ chế khóa, nhưng chỉ dựa vào khóa không đủ để giải quyết trật tự phát hành, hành vi startup hoặc thay đổi schema không tương thích với phiên bản ứng dụng còn đang chạy.

## 11. Tổ chức CI/CD để phát hành cùng một artifact

Một pipeline mẫu có thể triển khai các bước sau:

1. **Build / kiểm tra đầu vào:** chọn phiên bản Java, Liquibase, JDBC driver đã được phê duyệt; checkout đúng commit và xác minh changelog.
2. **Validate:** kiểm tra cấu trúc changelog và những vấn đề Liquibase có thể phát hiện trước khi chạy.
3. **Dev migration:** chạy trên cơ sở dữ liệu dev được chỉ định, theo dõi lịch sử và kết quả.
4. **Test migration:** dùng đúng artifact đó để migrate database test, chạy integration test và thử chiến lược rollback/khôi phục.
5. **Review SQL:** sinh SQL dự kiến, nhận diện thay đổi có thể gây khóa bảng, mất dữ liệu hoặc yêu cầu downtime.
6. **Production gate:** phê duyệt theo chính sách, xác minh đúng đích, quyền, backup và kế hoạch ứng phó sự cố.
7. **Production migration:** chạy một lần bởi job được kiểm soát, ghi log, kết quả, commit/release và changeset đã áp dụng.
8. **Xác minh sau phát hành:** kiểm tra schema, DATABASECHANGELOG, truy vấn ứng dụng, chỉ số lỗi và hành vi tương thích.

Một pipeline cụ thể có thể chia bước theo các job khác nhau, nhưng cần bảo đảm **promotion cùng artifact**. Nếu test chạy commit A còn production checkout nhánh đang di chuyển và vô tình chạy commit B, kết quả kiểm thử trước đó không còn chứng minh chính xác phiên bản được triển khai.

### 11.1. Quy tắc bảo vệ production

Pipeline production nên có những điều kiện tối thiểu:

- Tài khoản và secret production chỉ khả dụng trong job được ủy quyền.
- Job phải xác minh host, database và schema đích trước khi chạy thay đổi.
- Migration được review và thử trên test/staging đại diện.
- Có kế hoạch backup hoặc phục hồi khi changeset có rủi ro phá hủy dữ liệu.
- Có cơ chế ngăn chạy trùng một quy trình phát hành ở tầng orchestration.
- Có log xác định ai/phiên bản nào đã chạy, thời điểm nào và kết quả ra sao.

Không nên cho một lệnh được copy từ tài liệu hoặc terminal dev mặc nhiên có khả năng cập nhật production. Ngoài tách cấu hình, cần **tách quyền** và kiểm soát đường thực thi.

### 11.2. Những thông tin cần ghi nhận trong log phát hành

| Thông tin | Mục đích |
|---|---|
| Phiên bản ứng dụng và commit Git | Truy vết artifact triển khai |
| Phiên bản Liquibase, JDBC và hệ quản trị | Tái hiện môi trường đã chạy |
| Tên môi trường và định danh database mục tiêu | Phát hiện nhầm đích |
| Thời điểm bắt đầu/kết thúc, trạng thái | Giám sát và xử lý sự cố |
| Changeset dự kiến và changeset thực tế | Đối chiếu changelog với DATABASECHANGELOG |
| Kết quả kiểm thử, phê duyệt, backup | Có bằng chứng trước khi phát hành |

Log không được chứa password, token hoặc chuỗi kết nối có thông tin xác thực. Nếu phải ghi URL để truy vết, cần loại bỏ bí mật và tuân thủ chính sách nội bộ về thông tin hạ tầng.

## 12. Mô hình ba lớp kiểm tra để tránh chạy nhầm production

Tách file cấu hình mới giải quyết một phần vấn đề. Có thể dùng ba lớp bảo vệ:

### Lớp 1: Xác thực đích trước khi kết nối

Kiểm tra tên môi trường, JDBC URL đã giải quyết biến, host/port và database dự kiến. Trong CI, biến environment phải đến từ cấu hình job đúng và không được cho job thường tùy ý chọn secret production.

### Lớp 2: Xác nhận đích trong database

Dùng truy vấn đọc phù hợp với hệ quản trị để xác định database/schema, tài khoản hiện tại và thông tin môi trường trước khi chạy migration. Ví dụ trên PostgreSQL, câu lệnh kiểm tra chỉ đọc có thể là:

~~~sql
SELECT
    current_database() AS database_name,
    current_schema()   AS schema_name,
    current_user       AS login_name;
~~~

Pipeline so sánh kết quả thực tế với allowlist của môi trường. Kết nối thành công chưa có nghĩa nó trỏ đúng database; nếu không khớp, job phải dừng trước lệnh update.

### Lớp 3: Kiểm tra phạm vi thay đổi

Xem changeset pending bằng status, xem SQL dự kiến bằng update-sql và kiểm tra precondition phù hợp. Cũng cần xác định migration có động đến bảng lớn, dữ liệu nhạy cảm hoặc đối tượng dùng chung giữa dịch vụ hay không.

Một precondition như kiểm tra loại DBMS có thể phát hiện việc chạy SQL PostgreSQL trên hệ khác, nhưng **không xác nhận được đây là production hay dev** nếu cả hai cùng dùng PostgreSQL. Vì vậy, precondition không thay thế xác minh đích và kiểm soát quyền.

## 13. Quản lý dữ liệu mẫu, dữ liệu tham chiếu và dữ liệu thật

Không phải mọi dữ liệu đều nên được xử lý theo cùng một cách:

- **Dữ liệu tham chiếu bắt buộc:** mã trạng thái đơn hàng, cấu hình nghiệp vụ dùng ở mọi môi trường có thể nằm trong changelog chung, với quy trình đảm bảo idempotency và rollback phù hợp.
- **Dữ liệu demo hoặc dữ liệu phục vụ test:** có thể gắn contextFilter yêu cầu ngữ cảnh tường minh hoặc được tạo bởi riêng công cụ kiểm thử. Tránh để dữ liệu này lọt vào production.
- **Dữ liệu nghiệp vụ thật:** không được tùy tiện ghi đè theo dữ liệu giả từ dev. Với data migration cần quy tắc chuyển đổi rõ, kế hoạch backfill, kiểm tra số lượng bản ghi và xử lý dữ liệu bất thường.

Một changeset chạy tốt trên database dev rỗng có thể thất bại ở production vì tồn tại bản ghi không hợp lệ, khóa ngoại hoặc bảng quá lớn. Vì vậy, khi chuyển đổi cột nullable thành NOT NULL, hãy tính trước dữ liệu đang có, backfill và kiểm tra dữ liệu trước khi thêm ràng buộc.

Bất cứ thao tác chuyển dữ liệu nào có khả năng mất mát nên được xem xét trên môi trường kiểm thử với dữ liệu đại diện và đã ẩn danh. Đừng copy dữ liệu production chưa được bảo vệ sang máy phát triển chỉ để kiểm thử migration.

## 14. Rollback và khả năng tương thích qua các môi trường

Liquibase hỗ trợ khai báo rollback nhưng không thể bảo đảm mọi migration đều có thể đảo ngược. Nếu changeset xóa cột đã chứa dữ liệu, rollback bằng cách tạo lại cột sẽ không khôi phục các giá trị cũ. Do đó, production cần chính sách backup và phục hồi riêng.

Để giảm rủi ro khi thay đổi schema đồng thời phát hành ứng dụng, có thể dùng chu trình **expand–migrate–contract**:

1. **Expand:** thêm bảng/cột mới tương thích với phiên bản ứng dụng cũ.
2. **Migrate:** chuyển dữ liệu và cập nhật ứng dụng trong khi vẫn hỗ trợ cấu trúc cũ.
3. **Verify:** kiểm chứng dữ liệu, quan sát log và chuẩn bị ứng phó sự cố.
4. **Contract:** loại bỏ cấu trúc cũ ở lần phát hành sau khi không còn phiên bản ứng dụng nào sử dụng.

Trong dev, test và staging, hãy kiểm tra cả trường hợp ứng dụng cũ chạy với schema mới trong khoảng chuyển tiếp. Điều này đặc biệt quan trọng khi production triển khai theo rolling update hoặc có nhiều phiên bản ứng dụng cùng tồn tại.

Quy trình rollback nên được thử trước production, làm rõ thời điểm có thể quay lại, phạm vi dữ liệu có thể mất và điều kiện buộc phải dùng migration sửa lỗi tiến về phía trước thay vì rollback.

## 15. Tình huống thực hành: một changeset, ba môi trường

Giả sử ứng dụng bán hàng cần thêm cột ghi chú cho đơn hàng. Changeset có thể được khai báo như sau:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-add-order-note
      author: platform-team
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: orders
      changes:
        - addColumn:
            tableName: orders
            columns:
              - column:
                  name: note
                  type: VARCHAR(500)
      rollback:
        - dropColumn:
            tableName: orders
            columnName: note
~~~

Giả định: bảng orders đã tồn tại do một changeset trước đó tạo. Changeset này không cần context dev/test/prod vì cấu trúc mới được ứng dụng sử dụng ở tất cả môi trường. Rollback xóa cột, nên chỉ phù hợp khi chưa có dữ liệu cần giữ trong cột note.

Chuỗi thực hành:

1. **Ở dev:** cấu hình URL tới shop_dev, chạy validate, status và update-sql, sau đó mới thực thi update; kiểm tra cột xuất hiện và lịch sử ghi nhận changeset.
2. **Ở test:** dùng chính commit changelog đó, cấu hình URL tới shop_test, chạy migration trên dữ liệu test có sẵn; kiểm thử thêm và đọc ghi cột note, kiểm tra tính tương thích với ứng dụng.
3. **Trước production:** xác minh đường kết nối shop_prod, kiểm tra SQL dự kiến, mức khóa bảng, backup và kế hoạch phục hồi; thực hiện phê duyệt nếu quy trình yêu cầu.
4. **Ở production:** job được ủy quyền dùng secret production để chạy migration một lần; kiểm tra DATABASECHANGELOG, schema thực tế và log ứng dụng.
5. **Sau phát hành:** giữ nguyên changeset đã triển khai; nếu cần thay đổi kiểu dữ liệu hoặc độ dài cột, tạo changeset mới có id khác.

Bảng quan sát kỳ vọng:

| Thời điểm | Dev | Test | Production |
|---|---|---|---|
| Ban đầu | Chưa có cột note | Chưa có cột note | Chưa có cột note |
| Sau bước 1 | Có cột note | Chưa có | Chưa có |
| Sau bước 2 | Có | Có cột note | Chưa có |
| Sau bước 4 | Có | Có | Có cột note |

Bảng này mô tả **trạng thái mong đợi**, không phải kết quả đã đo trên database thật. Mỗi môi trường có bảng DATABASECHANGELOG riêng; khác biệt tiến độ triển khai trong thời gian phát hành là bình thường nếu được kiểm soát.

## 16. Các lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể có | Cách kiểm tra, xử lý |
|---|---|---|
| Pipeline test cập nhật nhầm dev | JDBC URL lấy từ biến cũ hoặc file override | Kiểm tra giá trị đích đã resolve, so sánh với allowlist trước update |
| Production báo không có changeset mới dù schema thiếu cột | Trỏ nhầm database, filter loại changeset hoặc lịch sử không khớp | Kiểm tra database/schema, status, contexts/labels và DATABASECHANGELOG |
| Dev chạy được nhưng test thiếu driver | Classpath hoặc phiên bản JDBC không được đóng gói trong runner | Cố định image và JDBC JAR, kiểm tra classpath ở đúng tiến trình |
| Precondition thất bại trên production | Dữ liệu hoặc schema có khác biệt chưa được tính đến | Dừng và điều tra trạng thái thật; không dùng MARK_RAN chỉ để bỏ qua lỗi |
| Checksum không khớp | Một changeset lịch sử đã bị chỉnh sửa | Đối chiếu commit và lịch sử; tạo changeset mới khi cần thay đổi tiếp |
| Bảng DATABASECHANGELOG trống bất thường | Đang kết nối sang DB/schema khác hoặc thay đổi schema lưu lịch sử | Kiểm tra URL, defaultSchemaName, liquibaseSchemaName trước khi chạy |
| Dữ liệu demo xuất hiện ở production | Chưa đặt context bắt buộc hoặc lệnh không lọc như dự kiến | Tách seed khỏi schema bắt buộc, dùng context @ và kiểm tra trên test |
| Spring Boot và pipeline cùng chạy migration | Hai điểm chạy đều được bật | Chỉ định một chủ sở hữu; tắt Liquibase của ứng dụng nếu pipeline sở hữu |
| Trùng quyền hoặc lỗi permission | Tài khoản runtime và tài khoản migration bị dùng lẫn | Tách tài khoản, cấp quyền vừa đủ theo schema và môi trường |
| Test chạy được, production bị khóa bảng lâu | Dữ liệu production lớn hơn, DDL có hành vi khác | Thử trên dữ liệu đại diện, đánh giá locking, thời gian chạy và phương án triển khai |

Khi gặp lỗi, không nên sửa trực tiếp DATABASECHANGELOG hoặc xóa checksum để “đồng bộ” trạng thái. Cần tìm xem khác biệt đến từ kết nối, cấu hình filter, quyền, dữ liệu hay changelog đã bị thay đổi.

## 17. Checklist trước khi chuyển môi trường

Trước mỗi lần dùng Liquibase trên môi trường mới, kiểm tra:

- [ ] Phiên bản mã nguồn/changelog và bộ công cụ đã được chốt.
- [ ] JDBC URL, database, schema và tài khoản thực tế khớp môi trường mong muốn.
- [ ] Secret được cấp bởi kho bí mật tương ứng; không xuất hiện trong Git hoặc log.
- [ ] Java, Liquibase và JDBC driver có phiên bản tương thích trong runner thực tế.
- [ ] Context và label filter được chọn có chủ đích, nhất là với dữ liệu mẫu.
- [ ] Changelog đã qua validate; status và SQL dự kiến đã được review.
- [ ] Không có pipeline hoặc instance khác đang điều khiển cùng lượt migration.
- [ ] Production có phê duyệt, backup và phương án khôi phục phù hợp mức rủi ro.
- [ ] Migration đã được thử trên dữ liệu và phiên bản database đủ đại diện.
- [ ] Sau update có bước kiểm tra DATABASECHANGELOG, đối tượng schema và ứng dụng.

**Tiêu chí hoàn thành bài:** bạn có thể giải thích rõ vì sao **một changelog phiên bản hóa** cần đi cùng **nhiều cấu hình kết nối biệt lập**, mô tả cách phân tách secret và quyền, chọn contexts/labels an toàn, đồng thời thực hiện được một quy trình kiểm tra trước và sau khi migrate mà không nhầm đích.

## 18. Kết luận

Tách cấu hình phát triển, kiểm thử và production là một phần không thể thiếu của quản lý schema bằng Liquibase. Cùng một changelog và bộ changeset được phát hành theo trình tự, nhưng mỗi môi trường sử dụng JDBC URL, tài khoản, quyền, secret, bộ lọc và quy trình kiểm soát riêng. Liquibase theo dõi lịch sử đã triển khai trên từng database thông qua DATABASECHANGELOG, trong khi checksum, precondition và rollback giúp phát hiện hoặc xử lý một số dạng rủi ro — với điều kiện được thiết kế, kiểm thử và vận hành đúng.

Một quy trình đáng tin cậy cần đồng thời **giữ changeset lịch sử ổn định**, **xác minh đúng đích kết nối**, **bảo vệ secret**, **kiểm tra SQL trên dữ liệu đại diện** và **chỉ định một chủ sở hữu migration** trong Spring Boot hoặc CI/CD. Khi những nguyên tắc này nhất quán, việc chuyển migration từ dev qua test đến production trở nên có thể dự đoán, kiểm chứng và truy vết hơn.

