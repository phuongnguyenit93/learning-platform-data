
# Quan hệ giữa mã nguồn, changelog và từng môi trường triển khai

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, mã nguồn ứng dụng, changelog Liquibase và cấu hình môi trường tạo thành một quy trình phát hành thống nhất. Mã nguồn mô tả ứng dụng cần hoạt động như thế nào; changelog mô tả cơ sở dữ liệu phải thay đổi ra sao để hỗ trợ phiên bản ứng dụng đó; môi trường triển khai cung cấp kết nối, thông tin xác thực và các tham số phù hợp với từng cơ sở dữ liệu.

Hiểu đúng mối quan hệ này giúp nhóm phát triển đưa thay đổi schema và dữ liệu qua nhiều môi trường một cách có thể kiểm tra, lặp lại và truy vết. Một bản phát hành đáng tin cậy phải trả lời được ba câu hỏi: phiên bản mã nguồn nào đang chạy, những changeset nào đã được áp dụng, và mỗi môi trường đang ở trạng thái cơ sở dữ liệu nào.

## 1. Ba thành phần và trách nhiệm của từng thành phần

| Thành phần | Nội dung quản lý | Vai trò trong phát hành |
|---|---|---|
| Mã nguồn ứng dụng | Entity, model, repository, service, truy vấn SQL, cấu hình và mã xử lý nghiệp vụ | Quy định ứng dụng đọc, ghi và diễn giải dữ liệu như thế nào |
| Changelog Liquibase | Changeset tạo bảng, sửa cột, tạo chỉ mục, cập nhật dữ liệu, điều kiện chạy và rollback | Mô tả các bước chuyển schema hoặc dữ liệu từ trạng thái cũ sang trạng thái mới |
| Môi trường triển khai | URL kết nối, tài khoản, schema mặc định, context, label, tham số và bí mật | Xác định Liquibase kết nối tới đâu, chạy với lựa chọn nào và tác động lên cơ sở dữ liệu nào |
| Cơ sở dữ liệu đích | Schema, dữ liệu thực tế và bảng lịch sử Liquibase | Lưu trạng thái đã triển khai của riêng môi trường đó |

Mã nguồn và changelog thường được quản lý cùng một repository và được review trong cùng một thay đổi. Cấu hình kết nối của từng môi trường được cấp riêng khi chạy pipeline hoặc ứng dụng. Lịch sử thực thi được lưu trong chính cơ sở dữ liệu đích, vì vậy môi trường phát triển, kiểm thử, staging và production có lịch sử độc lập.

Có thể hình dung một bản phát hành gồm:

- Một revision mã nguồn đã được review và tạo artifact.
- Master changelog cùng toàn bộ changelog được include tại revision đó.
- Bộ cấu hình triển khai chọn đúng cơ sở dữ liệu và các tham số của môi trường.
- Trạng thái lịch sử Liquibase tại cơ sở dữ liệu đích sau khi migration hoàn tất.

Chỉ có mã nguồn mới không đủ để mô tả đầy đủ bản phát hành nếu ứng dụng phụ thuộc vào một cột, bảng hoặc chỉ mục chưa được tạo. Ngược lại, changelog đã chạy thành công cũng không chứng minh ứng dụng tương thích với schema mới. Hai phần phải được kiểm tra cùng nhau.

## 2. Changelog là một phần của lịch sử mã nguồn

Changelog nên nằm trong repository và được quản lý bằng Git giống như mã Java. Một cấu trúc thường gặp trong ứng dụng Spring Boot là:

~~~text
src/main/resources/
└── db/
    └── changelog/
        ├── db.changelog-master.yaml
        └── changes/
            ├── 2026/
            │   ├── 20261119-01-create-customer.yaml
            │   ├── 20261119-02-add-customer-status.yaml
            │   └── 20261119-03-index-customer-email.yaml
            └── data/
                └── 20261119-04-seed-reference-data.yaml
~~~

Master changelog là điểm vào của Liquibase. Nó khai báo những file con cần nạp và thứ tự nạp chúng. Ví dụ:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/2026/20261119-01-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/2026/20261119-02-add-customer-status.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/2026/20261119-03-index-customer-email.yaml
      relativeToChangelogFile: true
~~~

Một file changeset có thể mô tả một thay đổi schema cụ thể:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-01
      author: platform-team
      comment: Tạo bảng lưu khách hàng
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: bigint
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: varchar(320)
                  constraints:
                    nullable: false
                    unique: true
      rollback:
        - dropTable:
            tableName: customer
~~~

Ví dụ trên minh họa một changeset tạo bảng và khai báo rollback tương ứng. Kiểu dữ liệu, cơ chế tự tăng, cú pháp ràng buộc và khả năng rollback thực tế cần được kiểm tra với hệ quản trị cơ sở dữ liệu mà dự án sử dụng.

Liquibase nhận diện một changeset bằng tổ hợp **id, author và đường dẫn changelog**. Khi một changeset được áp dụng, Liquibase ghi nhận nó trong bảng lịch sử mặc định là **DATABASECHANGELOG**. Bảng này chứa thông tin nhận diện, thời điểm chạy, thứ tự thực thi, trạng thái thực thi và checksum của changeset. Vì vậy, tên file và vị trí file cũng có ý nghĩa đối với lịch sử migration.

Master changelog cần thể hiện thứ tự phụ thuộc rõ ràng. Nếu changeset B cần bảng do changeset A tạo ra, A phải được nạp trước B. Không nên dựa vào giả định rằng Liquibase sẽ tự sắp xếp các file theo tên thư mục. Thứ tự include là một phần của hợp đồng triển khai.

Khi cần di chuyển hoặc đổi tên file changelog đã được triển khai, phải xem xét ảnh hưởng đến đường dẫn nhận diện changeset. Có thể dùng thuộc tính logical file path theo cách được Liquibase hỗ trợ để duy trì định danh logic ổn định. Không nên đổi cấu trúc thư mục một cách tùy tiện sau khi lịch sử đã được tạo ở các môi trường.

Liquibase còn dùng bảng **DATABASECHANGELOGLOCK** để quản lý khóa khi cập nhật một cơ sở dữ liệu. Khóa giúp tránh hai tiến trình Liquibase cùng thực thi migration trên một database tại cùng thời điểm. Đây là cơ chế điều phối thao tác migration; nó không thay thế việc điều phối thứ tự phát hành ứng dụng.

## 3. Ghép thay đổi schema với phiên bản ứng dụng

Khi một thay đổi nghiệp vụ làm thay đổi cấu trúc dữ liệu, pull request nên thể hiện cả hai mặt: mã ứng dụng sử dụng cấu trúc mới và changeset tạo ra cấu trúc đó. Reviewer cần đọc được mối liên hệ giữa chúng.

Ví dụ, một phiên bản ứng dụng bắt đầu đọc trạng thái khách hàng từ cột **customer.status**. Nếu code được triển khai trước khi cột tồn tại, truy vấn có thể thất bại. Nếu chỉ thêm cột mà code không sử dụng hoặc không xử lý dữ liệu cũ, migration vẫn có thể hoàn tất nhưng chức năng chưa hoạt động đúng.

Với hệ thống có rolling deployment hoặc nhiều phiên bản ứng dụng cùng tồn tại trong thời gian ngắn, nên thiết kế migration theo hướng **expand-and-contract**:

1. **Expand — mở rộng schema:** thêm bảng hoặc cột mới theo cách tương thích với code hiện tại, thường bắt đầu bằng cột nullable hoặc một giá trị mặc định đã được đánh giá. Chưa xóa cấu trúc cũ.
2. **Deploy compatible code — triển khai code tương thích:** cập nhật ứng dụng để có thể làm việc với cả trạng thái dữ liệu cũ và mới trong giai đoạn chuyển tiếp. Khi cần, ứng dụng có thể ghi đồng thời vào hai vị trí hoặc đọc theo cơ chế fallback.
3. **Migrate data — chuyển dữ liệu:** backfill dữ liệu cũ sang cấu trúc mới. Tác vụ chuyển dữ liệu nên có khả năng chạy lại an toàn, có thể chia lô, ghi log tiến độ và kiểm tra số lượng bản ghi.
4. **Switch and verify — chuyển hẳn sang cấu trúc mới:** chuyển luồng đọc/ghi sang cấu trúc mới, kiểm tra dữ liệu và theo dõi lỗi sau triển khai.
5. **Contract — thu hẹp schema:** chỉ xóa cột, bảng hoặc đường dẫn tương thích cũ sau khi mọi phiên bản ứng dụng còn hoạt động đã ngừng phụ thuộc vào chúng và các môi trường cần thiết đã hoàn tất chuyển đổi.

Không phải thay đổi nào cũng cần đủ năm bước. Một thay đổi bổ sung nhỏ có thể chỉ cần một changeset. Tuy nhiên, việc xóa hoặc đổi tên cột đang được sử dụng thường cần giai đoạn chuyển tiếp, đặc biệt khi triển khai không dừng toàn bộ dịch vụ.

Quy tắc quan trọng là schema phải tương thích với phiên bản ứng dụng trong suốt khoảng thời gian triển khai. Không nên giả định tất cả instance ứng dụng được thay thế đồng thời. Với thay đổi phá vỡ tương thích, cần tách thời điểm mở rộng và thời điểm loại bỏ cấu trúc cũ thành các lần phát hành có thể kiểm soát.

## 4. Dùng chung changelog, cấu hình riêng cho từng môi trường

Thông thường, dev, test, staging và production nên sử dụng cùng một master changelog từ cùng revision hoặc artifact đã được kiểm tra. Mỗi môi trường có URL, tài khoản, schema mặc định và bí mật riêng. Nhờ đó, cùng một lịch sử thay đổi được áp dụng theo cách nhất quán trên các cơ sở dữ liệu khác nhau.

| Môi trường | Mục đích | Điều cần giữ nhất quán |
|---|---|---|
| Development | Phát triển và kiểm tra nhanh | Chạy được changelog mới nhất, dễ tái tạo database |
| Test/QA | Kiểm tra tích hợp, dữ liệu và hành vi | Dùng cùng migration với bản dự kiến phát hành |
| Staging | Diễn tập quy trình gần production | Dùng cùng artifact, thứ tự và cấu hình tương đương production |
| Production | Phục vụ người dùng thật | Có kiểm soát quyền, thời điểm, quan sát và kế hoạch khôi phục |

Một ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USER}
    password: ${DB_PASSWORD}
  liquibase:
    change-log: classpath:db/changelog/db.changelog-master.yaml
    enabled: true
    contexts: ${LIQUIBASE_CONTEXTS:}
    labels: ${LIQUIBASE_LABELS:}
~~~

Các biến môi trường được cấp theo môi trường chạy. Không commit mật khẩu hoặc thông tin kết nối production vào repository. Nếu Liquibase cần một tài khoản riêng với quyền DDL trong khi ứng dụng chỉ cần quyền đọc/ghi dữ liệu, có thể cấu hình kết nối Liquibase riêng bằng các thuộc tính Spring Boot tương ứng, thay vì dùng chung tài khoản datasource của ứng dụng.

Đường dẫn changelog nên ổn định giữa các môi trường. Thay đổi URL kết nối, credentials hoặc schema mặc định không nên buộc phải sửa nội dung migration. Nếu một changeset cần giá trị phụ thuộc môi trường, hãy truyền qua tham số được quản lý có chủ đích và xác thực giá trị trước khi triển khai.

### Context và label

Liquibase hỗ trợ context và label để lựa chọn changeset cần chạy. Chúng hữu ích khi một thay đổi thực sự chỉ dành cho một nhóm môi trường hoặc một mục đích cụ thể, chẳng hạn dữ liệu mẫu chỉ dùng trong môi trường kiểm thử.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: seed-test-customer
      author: platform-team
      context: '@test'
      changes:
        - insert:
            tableName: customer
            columns:
              - column:
                  name: email
                  value: test@example.invalid
~~~

Context hoặc label được chọn khi chạy Liquibase, tùy cách tích hợp và phiên bản công cụ. Với dữ liệu chỉ dành cho kiểm thử, nên cấu hình bộ lọc context/label rõ ràng trong pipeline production; nếu không truyền context filter, Liquibase có thể vẫn chạy changeset có gắn context. Có thể dùng context bắt buộc như '@test' (trong phiên bản hỗ trợ) để yêu cầu filter chỉ định rõ test, rồi kiểm tra SQL dự kiến trước khi phát hành.

Không nên tạo nhiều nhánh changelog riêng cho từng môi trường chỉ vì dữ liệu kết nối khác nhau. Việc đó khiến schema ở các môi trường dần khác biệt và làm khó quá trình kiểm tra. Chỉ dùng context/label khi có lý do nghiệp vụ rõ ràng; các thay đổi schema cốt lõi nên được áp dụng nhất quán.

## 5. Theo dõi lịch sử riêng của từng database

Mỗi cơ sở dữ liệu đích duy trì bảng DATABASECHANGELOG của chính nó. Khi Liquibase chạy, công cụ so sánh changelog hiện tại với lịch sử đã ghi nhận để xác định changeset nào còn chờ thực thi.

Ví dụ, cùng một release có ba changeset:

| Changeset | Development | Staging | Production |
|---|---|---|---|
| Tạo bảng customer | Đã chạy | Đã chạy | Đã chạy |
| Thêm cột status | Đã chạy | Đã chạy | Chưa chạy |
| Tạo index email | Đã chạy | Chưa chạy | Chưa chạy |

Đây có thể là trạng thái hợp lệ trong quá trình phát hành tuần tự. Tuy nhiên, nhóm phải biết rõ môi trường nào đang ở bước nào và không được kết luận rằng production đã có schema mới chỉ vì staging đã chạy thành công.

Không chỉnh sửa trực tiếp bảng DATABASECHANGELOG để đánh dấu migration đã chạy hoặc chưa chạy. Việc thay đổi lịch sử bằng tay có thể làm Liquibase và schema thực tế mất đồng bộ. Nếu cần xử lý lịch sử bất thường, phải xác định nguyên nhân, đối chiếu schema thật và dùng quy trình Liquibase phù hợp với phiên bản đang vận hành.

Bảng DATABASECHANGELOG cũng không phải bản sao đầy đủ của schema. Nó cho biết những changeset nào đã được ghi nhận là thực thi; nó không chứng minh rằng không có người hoặc công cụ nào sửa database ngoài Liquibase. Vì vậy, cần có quy trình hạn chế thay đổi thủ công và kiểm tra drift khi thích hợp.

## 6. Quy trình CI/CD đưa changelog qua các môi trường

Một pipeline tốt dùng cùng revision mã nguồn và changelog đã được review để triển khai lần lượt. Không nên sửa changelog giữa các môi trường hoặc tạo một bản migration khác chỉ để production chạy được.

Một luồng tham khảo:

~~~text
Pull request
    |
    v
Review code + changelog
    |
    v
Validate changelog
    |
    v
Test migration trên database mới
và database có dữ liệu phiên bản trước
    |
    v
Tạo artifact/revision bất biến
    |
    v
Deploy Development -> Test -> Staging
    |
    v
Kiểm tra kết quả và phê duyệt phát hành
    |
    v
Deploy Production
    |
    v
Kiểm tra DATABASECHANGELOG,
schema, log và hành vi ứng dụng
~~~

Các bước kiểm tra Liquibase thường dùng gồm:

- **validate:** kiểm tra cấu trúc và khả năng đọc changelog theo cấu hình công cụ.
- **status:** xem changeset nào đang chờ áp dụng trên database đích.
- **update-sql:** sinh SQL dự kiến để review trước khi thực thi.
- **update:** áp dụng các changeset còn thiếu.
- **rollback hoặc rollback-sql:** kiểm tra hoặc thực hiện phương án rollback đã chuẩn bị, khi loại thay đổi và hệ quản trị cơ sở dữ liệu hỗ trợ.

Cần phân biệt các bước này. Validate không chứng minh migration chắc chắn chạy thành công trên database thật. Update-sql giúp review câu lệnh được sinh ra nhưng không thay thế việc thử chạy trên môi trường tương đương. Một migration chỉ nên được coi là đã kiểm chứng sau khi được thực thi trên database thử nghiệm phù hợp và kết quả được xác nhận.

Nên kiểm tra ít nhất hai tình huống:

- **Database mới:** toàn bộ changelog có thể tạo schema cần thiết từ đầu.
- **Database đã có dữ liệu:** migration nâng cấp từ phiên bản trước hoàn tất và giữ đúng dữ liệu cần bảo toàn.

Với migration có lượng dữ liệu lớn, cần đo thời gian, dung lượng log, lock và ảnh hưởng tới truy vấn đang chạy. Có thể tách việc backfill thành job riêng để kiểm soát tiến độ, thay vì đặt một thao tác dài trong changeset triển khai ứng dụng.

Khi promote sang môi trường tiếp theo, pipeline nên dùng đúng artifact hoặc commit đã được kiểm tra. Nếu staging chạy một revision nhưng production lại lấy một revision khác, kết quả staging không còn là bằng chứng cho bản production.

## 7. Checksum và nguyên tắc không sửa changeset đã triển khai

Liquibase tạo checksum cho changeset và lưu trong DATABASECHANGELOG. Khi đọc changelog hiện tại, Liquibase có thể phát hiện nội dung của một changeset đã khác với nội dung từng được ghi nhận. Tùy loại chỉnh sửa và phiên bản Liquibase, một số thay đổi định dạng có thể được xử lý đặc biệt; nhóm không nên dựa vào điều đó để sửa migration đã triển khai.

Nguyên tắc an toàn là:

- Changeset chưa triển khai ở bất kỳ môi trường dùng chung nào có thể còn được chỉnh sửa trong quá trình review.
- Khi changeset đã được triển khai, coi nội dung của nó là bất biến.
- Nếu cần sửa kết quả, tạo changeset mới để bổ sung, điều chỉnh hoặc khôi phục trạng thái.
- Nếu đổi vị trí file, kiểm tra định danh đường dẫn và chiến lược logical file path.
- Chỉ dùng validCheckSum hoặc thao tác clear-checksums trong trường hợp đã hiểu nguyên nhân, đánh giá ảnh hưởng và ghi nhận quyết định vận hành.

Không nên xóa hoặc sửa một changeset cũ để làm cho pipeline hết báo lỗi checksum. Cách làm đó có thể khiến các database đã triển khai và database mới khởi tạo có lịch sử khác nhau. Một changeset mới thể hiện rõ lịch sử sửa chữa và cho phép mọi môi trường tiến về cùng trạng thái đích.

## 8. Preconditions giúp migration kiểm tra trạng thái trước khi chạy

Precondition cho phép đặt điều kiện để changeset chỉ chạy khi database ở trạng thái phù hợp. Ví dụ, một migration cần bảng customer tồn tại trước khi thêm cột:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-02
      author: platform-team
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
                  defaultValue: ACTIVE
                  constraints:
                    nullable: true
~~~

Ví dụ minh họa ý tưởng kiểm tra điều kiện trước khi thay đổi; cần xác nhận cú pháp precondition theo định dạng changelog và phiên bản Liquibase của dự án. Nếu điều kiện không đạt, lựa chọn xử lý phải phản ánh đúng mức độ an toàn.

Một số lựa chọn onFail thường gặp:

| Lựa chọn | Ý nghĩa khái quát | Khi cân nhắc |
|---|---|---|
| HALT | Dừng cập nhật khi điều kiện không đạt | Trạng thái không đúng có thể làm migration sai hoặc gây mất dữ liệu |
| WARN | Cảnh báo và tiếp tục theo cấu hình | Điều kiện chỉ mang tính thông tin và việc tiếp tục đã được đánh giá |
| CONTINUE | Bỏ qua changeset trong lần chạy đó | Có lý do rõ ràng để chờ lần chạy sau |
| MARK_RAN | Đánh dấu changeset như đã chạy mà không thực thi thay đổi | Chỉ khi đã xác minh thay đổi tương đương đã tồn tại và việc ghi nhận này là có chủ đích |

Không dùng MARK_RAN để che giấu việc schema bị lệch. Nếu bảng hoặc cột đã tồn tại do thao tác thủ công, cần kiểm tra kiểu dữ liệu, constraint, index và dữ liệu thực tế trước khi quyết định ghi nhận changeset.

## 9. Rollback là một phần của thiết kế migration

Rollback mô tả cách đưa database về trạng thái trước một hoặc nhiều changeset. Một số change type có thể được Liquibase hỗ trợ rollback tự động; với thay đổi phức tạp hoặc SQL tùy chỉnh, cần khai báo rollback tường minh và kiểm tra SQL được sinh ra.

Ví dụ changeset tạo bảng ở trên khai báo rollback bằng dropTable. Đây là trường hợp tương đối rõ vì có thể xóa đối tượng vừa tạo. Với changeset xóa dữ liệu, ghi đè dữ liệu hoặc chuyển đổi dữ liệu, rollback có thể không khôi phục được giá trị ban đầu nếu không lưu lại thông tin cần thiết.

Trước khi phát hành, hãy trả lời:

- Rollback có thực sự khôi phục được schema và dữ liệu cần thiết không?
- Có dữ liệu mới phát sinh sau khi migration chạy không?
- Phiên bản ứng dụng cũ có tương thích với schema sau rollback không?
- Có cần backup, snapshot hoặc bản lưu dữ liệu trước khi thực thi không?
- Có thể khắc phục bằng một changeset tiến tới (forward fix) an toàn hơn không?

Rollback schema không đồng nghĩa rollback toàn bộ hệ thống. Ví dụ, nếu một cột mới đã nhận dữ liệu do phiên bản ứng dụng mới ghi vào, xóa cột đó có thể làm mất dữ liệu. Trong trường hợp này, một migration sửa tiếp theo có thể an toàn hơn việc quay ngược schema.

Nên thử rollback trên database thử nghiệm có dữ liệu đại diện, đồng thời kiểm tra đường quay tiến lại nếu kế hoạch khôi phục yêu cầu. Với thao tác phá hủy dữ liệu, phải có phương án bảo toàn dữ liệu riêng; không coi rollback tự động là bảo đảm khôi phục.

## 10. Triển khai đồng thời và kiểm soát quyền truy cập

DATABASECHANGELOGLOCK giúp tuần tự hóa các lần Liquibase cập nhật cùng một database. Nếu pipeline và nhiều instance Spring Boot cùng cố gắng chạy migration, một tiến trình sẽ giữ khóa và tiến trình còn lại phải chờ hoặc xử lý theo cấu hình timeout. Điều này giảm nguy cơ chạy trùng changeset, nhưng vẫn có thể làm khởi động ứng dụng chậm hoặc khiến các lần phát hành cạnh tranh nhau.

Với hệ thống nhiều replica, nên cân nhắc chạy migration bằng một bước/job riêng trong pipeline hoặc một tiến trình được điều phối rõ ràng. Nếu để Spring Boot tự chạy Liquibase khi khởi động, cần hiểu thứ tự khởi động, thời gian chờ khóa và quyền DDL của từng instance. Không xóa khóa thủ công khi chưa xác định tiến trình đang giữ khóa có còn hoạt động hay không.

Tài khoản Liquibase cần đủ quyền để thực hiện các thay đổi dự kiến, nhưng nên được quản lý riêng với quyền truy cập runtime của ứng dụng khi mô hình bảo mật yêu cầu. Pipeline cần lấy credentials từ secret store hoặc cơ chế bảo mật tương đương, giới hạn quyền theo môi trường và tránh in bí mật ra log.

Migration có thể giữ lock trên bảng hoặc ảnh hưởng tới truy vấn ứng dụng tùy hệ quản trị cơ sở dữ liệu. Với bảng lớn, tạo index hoặc cập nhật nhiều dòng, cần xem xét chiến lược online/concurrent index phù hợp với database, thời gian chạy, lock và tải thực tế. Không thể giả định mọi câu lệnh DDL đều ngắn hoặc có thể rollback giống nhau trên mọi hệ quản trị.

## 11. Các sai lệch thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Ứng dụng lỗi vì thiếu cột sau deploy | Code mới được chạy trước migration hoặc migration chưa được chọn | Kiểm tra thứ tự phát hành, status và DATABASECHANGELOG của đúng database |
| Checksum mismatch | Nội dung changeset đã triển khai bị sửa hoặc định danh file thay đổi | So sánh revision, kiểm tra đường dẫn và tạo changeset sửa tiếp nếu cần |
| Dev chạy được nhưng production không chạy | Dữ liệu, quyền, schema, context hoặc phiên bản database khác nhau | Kiểm tra cấu hình kết nối, precondition, quyền và dữ liệu production tương ứng |
| Changeset được ghi nhận nhưng thay đổi không tồn tại | Có thể đã dùng MARK_RAN hoặc lịch sử bị can thiệp | Đối chiếu schema thật với lịch sử và điều tra thao tác đã thực hiện |
| Liquibase chờ khóa | Có tiến trình khác đang cập nhật hoặc khóa còn sót sau sự cố | Xác định tiến trình và trạng thái database trước khi xử lý lock |
| Rollback làm mất dữ liệu | Thay đổi dữ liệu không có thông tin phục hồi | Dừng thao tác phá hủy, đánh giá backup và cân nhắc forward fix |
| Môi trường có schema khác nhau | Thay đổi thủ công, bỏ qua changeset hoặc dùng changelog khác nhau | So sánh schema, lịch sử và artifact đã triển khai; chuẩn hóa lại bằng migration có kiểm soát |

Khi điều tra, luôn xác nhận đúng database trước khi chạy lệnh có tác động. Tên môi trường trong log hoặc pipeline không đủ để bảo đảm kết nối đang trỏ đúng đích; hãy kiểm tra host, database, schema và tài khoản theo quy trình bảo mật của nhóm.

## 12. Ví dụ luồng phát hành một thay đổi

Giả sử phiên bản mới bổ sung trạng thái cho khách hàng. Mã Java sẽ đọc trường status để quyết định khách hàng có được phép thực hiện một nghiệp vụ hay không.

Một quy trình có thể thực hiện như sau:

1. Developer tạo changeset thêm cột status ở trạng thái tương thích, chẳng hạn nullable trong giai đoạn đầu.
2. Developer cập nhật entity, repository và logic nghiệp vụ để xử lý cả bản ghi cũ chưa có status.
3. Pull request chứa code và changelog được review cùng nhau; reviewer kiểm tra thứ tự include, precondition, SQL dự kiến và rollback.
4. CI chạy validate, kiểm tra status, sinh update-sql và thực thi migration trên database thử nghiệm. CI kiểm tra cả database rỗng lẫn database đã có dữ liệu.
5. Pipeline tạo artifact từ revision đã kiểm tra và triển khai cùng changelog đó lên development, test rồi staging.
6. Sau khi kiểm tra hành vi ứng dụng, pipeline triển khai migration lên production theo bước đã được điều phối. Liquibase ghi nhận changeset trong DATABASECHANGELOG của production.
7. Ứng dụng được triển khai theo thứ tự tương thích với schema. Nhóm kiểm tra log, lỗi truy vấn, dữ liệu status và kết quả nghiệp vụ.
8. Nếu cần chuyển dữ liệu cũ, chạy backfill có thể theo dõi và kiểm tra. Chỉ khi dữ liệu và ứng dụng đã chuyển hoàn toàn mới cân nhắc loại bỏ đường dẫn cũ ở một changeset thuộc lần phát hành sau.

Trong toàn bộ luồng, changelog là lịch sử chuyển đổi được version hóa; Git cho biết nội dung nào thuộc một revision; pipeline quyết định khi nào revision được áp dụng; DATABASECHANGELOG cho biết từng database đã ghi nhận những bước nào. Bốn yếu tố này kết hợp giúp truy vết một thay đổi từ pull request tới môi trường đang chạy.

## 13. Checklist trước khi triển khai

- [ ] Code và changelog liên quan nằm trong cùng thay đổi được review.
- [ ] Master changelog include đúng file và đúng thứ tự phụ thuộc.
- [ ] Changeset có id, author ổn định và mô tả mục đích rõ ràng.
- [ ] Changeset đã triển khai trước đó không bị sửa nội dung.
- [ ] Preconditions kiểm tra đúng trạng thái cần thiết và cách xử lý khi thất bại đã được cân nhắc.
- [ ] SQL dự kiến đã được review trên đúng loại database.
- [ ] Migration đã được thử trên database mới và database nâng cấp từ phiên bản trước.
- [ ] Dữ liệu lớn có kế hoạch backfill, đo thời gian và kiểm tra kết quả.
- [ ] Cấu hình môi trường trỏ đúng database, schema, context và label.
- [ ] Credentials được cấp an toàn và tài khoản có quyền phù hợp.
- [ ] Pipeline promote cùng revision/artifact qua các môi trường.
- [ ] Có phương án rollback hoặc forward fix, cùng backup phù hợp với mức độ rủi ro.
- [ ] Sau triển khai đã kiểm tra DATABASECHANGELOG, schema thực tế, log và hành vi ứng dụng.

Quản lý migration bằng Liquibase hiệu quả khi nhóm coi changelog là tài sản của mã nguồn và coi mỗi database là một đích triển khai có lịch sử riêng. Mã ứng dụng, changeset, cấu hình môi trường và bằng chứng thực thi cần luôn liên kết được với cùng một bản phát hành. Nhờ đó, nhóm có thể biết chính xác thay đổi nào sẽ chạy, thay đổi nào đã chạy ở từng môi trường và cần làm gì khi quá trình triển khai không đạt kết quả mong muốn.

