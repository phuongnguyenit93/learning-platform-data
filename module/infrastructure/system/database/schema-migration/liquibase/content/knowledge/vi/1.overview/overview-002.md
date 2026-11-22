# Vai trò của Liquibase trong vòng đời ứng dụng và cơ sở dữ liệu

## 1. Vì sao thay đổi cơ sở dữ liệu cần đi cùng vòng đời ứng dụng?

Một ứng dụng hiếm khi giữ nguyên cấu trúc dữ liệu trong suốt thời gian tồn tại. Khi sản phẩm bổ sung chức năng, nhóm phát triển có thể cần thêm bảng, cột, ràng buộc, chỉ mục, thay đổi kiểu dữ liệu, chuẩn hóa dữ liệu cũ hoặc loại bỏ cấu trúc đã lỗi thời. Những thay đổi này ảnh hưởng trực tiếp đến mã nguồn đang chạy và dữ liệu mà người dùng đã tạo.

Nếu mỗi môi trường được chỉnh sửa cơ sở dữ liệu thủ công, các môi trường dễ lệch nhau: máy của lập trình viên có cột mới nhưng môi trường kiểm thử chưa có; một câu lệnh đã chạy ở staging nhưng bị bỏ sót ở production; hoặc một thao tác sửa dữ liệu được thực hiện mà không có lịch sử để giải thích. Khi đó, việc triển khai ứng dụng trở nên khó lặp lại và khó kiểm chứng.

Liquibase giải quyết bài toán này bằng cách mô tả thay đổi schema và dữ liệu thành các migration có phiên bản, lưu chúng trong changelog được quản lý cùng mã nguồn, rồi áp dụng theo thứ tự vào cơ sở dữ liệu đích. Nhờ vậy, thay đổi cơ sở dữ liệu trở thành một phần có thể xem xét, kiểm thử, triển khai và kiểm toán trong vòng đời phát triển phần mềm.

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, nội dung trọng tâm là cách quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; đồng thời thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Liquibase là công cụ điều phối các thay đổi đó. Nó không thay thế thiết kế dữ liệu, sao lưu, chiến lược phát hành hay quy trình kiểm thử của đội ngũ.

## 2. Liquibase đứng ở đâu trong vòng đời ứng dụng?

Liquibase kết nối quyết định thay đổi dữ liệu với quá trình đưa phiên bản ứng dụng tới các môi trường. Một vòng đời điển hình có thể được nhìn theo các chặng sau:

| Chặng | Công việc liên quan đến cơ sở dữ liệu | Vai trò của Liquibase |
|---|---|---|
| Phân tích và thiết kế | Xác định dữ liệu mới, quan hệ, ràng buộc và cách chuyển dữ liệu hiện có | Cung cấp cách biểu diễn thay đổi thành các bước có thứ tự để nhóm thảo luận và rà soát |
| Phát triển | Viết mã ứng dụng và migration tương ứng | Lưu changelog, changeset và rollback cùng repository |
| Kiểm thử | Kiểm tra migration trên cơ sở dữ liệu sạch và dữ liệu gần với thực tế | Áp dụng migration, xác minh kết quả và phát hiện thay đổi không hợp lệ |
| Đóng gói và phát hành | Xác định phiên bản ứng dụng nào cần cấu trúc dữ liệu nào | Đưa changelog vào artifact hoặc gói triển khai của phiên bản |
| Triển khai | Cập nhật schema và dữ liệu ở môi trường đích | So sánh lịch sử triển khai với changelog, sau đó chạy các changeset còn thiếu |
| Vận hành | Theo dõi trạng thái, xử lý lỗi và thay đổi tiếp theo | Lưu lịch sử đã chạy, checksum và thông tin triển khai để hỗ trợ điều tra |
| Khôi phục hoặc sửa lỗi | Đưa hệ thống về trạng thái an toàn khi migration gặp sự cố | Hỗ trợ rollback cho các thay đổi có thể đảo ngược; cung cấp lịch sử để quyết định bước khắc phục |

Điểm quan trọng là migration phải được phát triển và phát hành cùng thay đổi ứng dụng có liên quan. Một phiên bản mã nguồn có thể cần cột mới, nhưng nếu migration chưa chạy thì ứng dụng có thể lỗi khi truy vấn. Ngược lại, nếu xóa cột ngay khi mã cũ vẫn đang chạy trong một đợt triển khai cuốn chiếu, các instance cũ có thể thất bại.

Vì thế, Liquibase giúp quản lý trạng thái cơ sở dữ liệu, còn nhóm phát triển vẫn phải bảo đảm tính tương thích giữa phiên bản ứng dụng đang chạy và schema hiện có.

## 3. Các thành phần cốt lõi và cách chúng phối hợp

### 3.1. Changelog: bản mô tả có thứ tự của thay đổi

Changelog là tệp hoặc tập hợp tệp mô tả các thay đổi cần áp dụng. Liquibase hỗ trợ nhiều định dạng như YAML, XML, JSON và SQL. Một changelog gốc thường đóng vai trò điểm vào, sau đó nạp các changelog con bằng include hoặc includeAll.

Changelog là lịch sử thay đổi được quản lý trong repository. Nó cho người đọc biết nhóm dự định thay đổi điều gì, theo thứ tự nào và trong điều kiện nào. Khi một thay đổi đã được triển khai, nhóm nên xem changeset đó là bất biến; thay đổi mới được thêm bằng changeset mới để lịch sử giữa các môi trường vẫn có thể đối chiếu.

Ví dụ một changelog YAML đơn giản:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: platform-team
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: varchar(320)
                  constraints:
                    nullable: false
~~~

Tệp trên khai báo một thay đổi tạo bảng customer. Trong dự án thật, cần chọn kiểu dữ liệu, tên ràng buộc, chiến lược sinh khóa và quy tắc unique phù hợp với hệ quản trị cơ sở dữ liệu (DBMS) đang sử dụng. Ví dụ chỉ minh họa cấu trúc Liquibase, không phải thiết kế hoàn chỉnh cho mọi hệ thống.

### 3.2. Changeset: đơn vị thay đổi được nhận diện và theo dõi

Changeset là đơn vị Liquibase nhận diện để quyết định một thay đổi đã được chạy hay chưa. Một changeset có ba thành phần nhận diện quan trọng:

- **id**: mã do nhóm đặt để phân biệt changeset.
- **author**: tác giả hoặc định danh nhóm tạo changeset.
- **đường dẫn changelog**: vị trí của tệp chứa changeset, được Liquibase dùng trong định danh lịch sử.

Ba thành phần này kết hợp thành khóa nhận diện của changeset trong lịch sử triển khai. Vì vậy, không nên tùy tiện đổi id, author hoặc di chuyển tệp sau khi changeset đã được áp dụng ở môi trường dùng chung. Cần thống nhất quy ước đặt tên và cấu trúc thư mục ngay từ đầu.

Một changeset nên đại diện cho một mục đích thay đổi rõ ràng, chẳng hạn tạo một bảng, thêm một cột, tạo một chỉ mục hoặc chuyển đổi một nhóm dữ liệu. Chia thay đổi thành các bước nhỏ giúp review, kiểm thử và xử lý lỗi dễ hơn. Tuy nhiên, không nên chia vụn đến mức thứ tự phụ thuộc trở nên khó hiểu.

Liquibase ghi nhận changeset đã thực thi trong bảng lịch sử **DATABASECHANGELOG**. Khi chạy lại lệnh cập nhật, Liquibase đối chiếu changelog với lịch sử này để bỏ qua những changeset đã được áp dụng đúng định danh và chạy những changeset còn thiếu. Nhờ đó, cùng một bộ changelog có thể được đưa qua nhiều môi trường mà không cần người triển khai tự ghi nhớ đã chạy câu lệnh nào.

### 3.3. DATABASECHANGELOG và DATABASECHANGELOGLOCK

Liquibase thường tạo và quản lý hai bảng hệ thống trong schema được cấu hình:

- **DATABASECHANGELOG** lưu dấu vết các changeset đã được áp dụng, bao gồm thông tin định danh, thời điểm, checksum và kiểu thực thi. Đây là nguồn để Liquibase xác định lịch sử migration.
- **DATABASECHANGELOGLOCK** quản lý khóa triển khai để ngăn nhiều tiến trình Liquibase cùng thực hiện cập nhật changelog đồng thời trên cùng cơ sở dữ liệu.

Khóa triển khai đặc biệt quan trọng khi nhiều instance ứng dụng khởi động gần như cùng lúc hoặc nhiều pipeline vô tình chạy migration song song. Cơ chế khóa giúp tuần tự hóa thao tác Liquibase, nhưng không thay thế việc thiết kế quy trình phát hành chỉ có một nơi chịu trách nhiệm chạy migration. Nếu một tiến trình bị dừng bất thường và khóa còn bị giữ, người vận hành cần kiểm tra tiến trình, log và trạng thái cơ sở dữ liệu trước khi giải phóng khóa; không xóa hoặc sửa bảng khóa theo phản xạ.

Tên bảng và một số cột có thể được cấu hình hoặc khác nhau theo phiên bản. Không nên dùng các bảng này làm nơi lưu nghiệp vụ hay sửa dữ liệu trực tiếp bằng thao tác thủ công.

### 3.4. Checksum: phát hiện changeset đã bị sửa

Khi thực thi changeset, Liquibase tính checksum và lưu giá trị trong DATABASECHANGELOG. Ở lần chạy sau, Liquibase tính lại để kiểm tra nội dung hiện tại có còn khớp với nội dung đã được ghi nhận hay không.

Nếu một changeset đã triển khai bị sửa, checksum có thể thay đổi và Liquibase báo sai khác. Đây là tín hiệu quan trọng: cùng một định danh migration đang đại diện cho nội dung khác nhau giữa các lần triển khai. Cách xử lý thông thường là khôi phục changeset cũ về đúng nội dung đã phát hành và tạo changeset mới cho yêu cầu mới.

Không nên dùng thao tác xóa hoặc làm mới checksum chỉ để vượt qua lỗi. Những lệnh như clearCheckSums có phạm vi ảnh hưởng rộng và chỉ phù hợp trong tình huống bảo trì đã được hiểu rõ, có kiểm soát và có kế hoạch xác minh. Thay đổi checksum không tự chứng minh rằng schema thực tế đang đúng.

### 3.5. Preconditions: xác nhận điều kiện trước khi thay đổi

Precondition là điều kiện Liquibase kiểm tra trước khi chạy changeset hoặc changelog. Điều kiện có thể xác nhận DBMS, phiên bản cơ sở dữ liệu, schema, bảng, cột, dữ liệu hoặc trạng thái mong đợi.

Ví dụ sau chỉ tạo chỉ mục khi chỉ mục đó chưa tồn tại:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-add-customer-email-index
      author: platform-team
      preConditions:
        onFail: HALT
        not:
          - indexExists:
              tableName: customer
              indexName: idx_customer_email
      changes:
        - createIndex:
            tableName: customer
            indexName: idx_customer_email
            columns:
              - column:
                  name: email
~~~

Precondition làm rõ giả định của migration và giúp dừng sớm khi môi trường không ở trạng thái dự kiến. Cần phân biệt hai trường hợp:

- **onFail** xử lý khi điều kiện được đánh giá thành công nhưng kết quả là không đạt.
- **onError** xử lý khi Liquibase không thể đánh giá điều kiện, ví dụ do lỗi truy vấn hoặc quyền truy cập.

Các lựa chọn như HALT, WARN, CONTINUE hoặc MARK_RAN có ý nghĩa vận hành khác nhau và phạm vi áp dụng phụ thuộc cách khai báo cũng như phiên bản Liquibase. HALT thường phù hợp khi tiếp tục có thể gây hỏng dữ liệu hoặc schema. MARK_RAN cần đặc biệt thận trọng vì changeset có thể được ghi nhận là đã xử lý dù các thay đổi bên trong không được chạy; chỉ dùng khi trạng thái hiện tại đã được xác minh là tương đương với kết quả mong muốn.

Precondition không phải cơ chế tự sửa mọi sai lệch. Nếu điều kiện thất bại, người phát triển cần hiểu vì sao môi trường khác dự kiến, xác định cách đưa nó về trạng thái hợp lệ rồi mới triển khai tiếp.

## 4. Liquibase hỗ trợ các môi trường như thế nào?

Một hệ thống thường có môi trường local, integration, test, staging và production. Các môi trường này có thể dùng dữ liệu, thông tin kết nối, quyền truy cập và quy mô khác nhau, nhưng cần tiến triển theo cùng một lịch sử migration đã được review.

### 4.1. Dùng chung changelog, tách cấu hình môi trường

Thông thường, changelog mô tả thay đổi cần thiết cho ứng dụng, còn cấu hình kết nối được cung cấp riêng theo môi trường. URL, tài khoản, mật khẩu, schema mặc định và thông tin nhạy cảm không nên được ghi cứng trong changelog hoặc commit vào repository.

Liquibase có contexts và labels để chọn changeset phù hợp với mục đích triển khai. Chúng có thể hữu ích cho dữ liệu mẫu, tác vụ chỉ chạy trong môi trường thử nghiệm hoặc nhóm migration được điều khiển theo nhãn phát hành. Tuy nhiên, nếu dùng contexts để tạo ra các lịch sử schema khác nhau ngoài ý muốn, các môi trường có thể dần lệch nhau. Cần quy định rõ changeset nào là bắt buộc ở mọi môi trường và changeset nào thực sự có điều kiện.

Một nguyên tắc hữu ích là cùng một phiên bản ứng dụng phải có thể giải thích rõ những changeset nào cần được áp dụng tại từng môi trường. Mọi khác biệt phải có chủ đích, được review và có cách kiểm chứng.

### 4.2. Thứ tự triển khai và tính tương thích

Trong triển khai thông thường, migration cần hoàn tất trước khi phiên bản ứng dụng phụ thuộc vào schema mới được đưa vào phục vụ lưu lượng. Với triển khai cuốn chiếu hoặc nhiều instance, thứ tự này phải tính đến cả mã cũ và mã mới cùng tồn tại trong một khoảng thời gian.

Ví dụ, khi cần thêm cột phone_number:

1. Thêm cột theo cách tương thích với ứng dụng cũ, thường là cho phép NULL hoặc có giá trị mặc định phù hợp.
2. Phát hành ứng dụng có thể đọc và ghi cột mới, đồng thời vẫn xử lý được bản ghi chưa có giá trị.
3. Chuyển đổi hoặc backfill dữ liệu cũ theo kế hoạch có thể theo dõi.
4. Sau khi xác nhận mọi instance và dữ liệu đã đáp ứng yêu cầu, mới cân nhắc thêm NOT NULL hoặc ràng buộc chặt hơn.

Đây là cách tiếp cận mở rộng rồi thu hẹp (expand-contract). Nó giảm rủi ro khi schema và ứng dụng được cập nhật ở các thời điểm khác nhau. Liquibase thực hiện từng bước schema/data migration; logic tương thích vẫn phải được thiết kế trong mã ứng dụng và kế hoạch phát hành.

### 4.3. Cẩn trọng với migration dữ liệu lớn

Thay đổi dữ liệu có thể kéo dài hơn thay đổi cấu trúc đơn giản. Một câu lệnh cập nhật toàn bộ bảng lớn có thể giữ khóa lâu, tạo tải I/O, làm tăng thời gian triển khai hoặc ảnh hưởng truy vấn của ứng dụng.

Với dữ liệu lớn, nên cân nhắc:

- Chuyển dữ liệu theo lô có giới hạn và có thể tiếp tục sau khi gián đoạn.
- Đo thời gian, dung lượng log giao dịch và ảnh hưởng khóa trên DBMS thực tế.
- Tách backfill dài thành tác vụ vận hành có theo dõi thay vì buộc ứng dụng chờ khởi động.
- Xác định cách kiểm tra số bản ghi đã xử lý, số bản ghi còn lại và điều kiện hoàn tất.
- Có kế hoạch dừng, tiếp tục hoặc sửa dữ liệu nếu tác vụ thất bại giữa chừng.

Liquibase giúp lưu định nghĩa và lịch sử migration, nhưng không tự bảo đảm mọi câu lệnh đều an toàn với bảng lớn. Đặc tính DDL, khóa, transaction và tạo chỉ mục khác nhau giữa PostgreSQL, MySQL, Oracle, SQL Server và các DBMS khác; phải thử trên đúng loại và phiên bản cơ sở dữ liệu đích.

## 5. Rollback và xử lý khi migration gặp lỗi

Rollback là khả năng đưa thay đổi đã thực hiện trở lại trạng thái trước đó. Liquibase hỗ trợ rollback dựa trên thông tin rollback được khai báo hoặc được sinh tự động cho một số loại thay đổi. Không phải mọi thao tác đều có thể đảo ngược đầy đủ.

Ví dụ một changeset có rollback tường minh:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 003-create-audit-event
      author: platform-team
      changes:
        - createTable:
            tableName: audit_event
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: event_type
                  type: varchar(100)
      rollback:
        - dropTable:
            tableName: audit_event
~~~

Rollback ở ví dụ này xóa bảng audit_event. Nếu bảng đã nhận dữ liệu thật, thao tác rollback sẽ làm mất dữ liệu đó. Vì vậy, rollback hợp lệ về mặt cú pháp chưa chắc là phương án an toàn về mặt nghiệp vụ.

Trước khi triển khai, nhóm cần đánh giá:

- Thay đổi có đảo ngược được không? Nếu xóa cột hoặc chuyển đổi dữ liệu làm mất thông tin, rollback có thể không khôi phục được giá trị ban đầu.
- Có cần sao lưu hoặc snapshot trước migration không? Sao lưu phải có quy trình phục hồi đã được thử, không chỉ tồn tại trên giấy.
- Có thể sửa tiến về phía trước bằng một changeset mới không? Trong nhiều tình huống production, migration sửa lỗi theo hướng tiến (forward fix) an toàn hơn việc quay ngược schema đang được ứng dụng sử dụng.
- Ứng dụng phiên bản cũ có tương thích với schema sau rollback không? Cần đánh giá cả mã nguồn, dữ liệu và các instance đang chạy.
- Ai quyết định dừng triển khai, rollback hay tiếp tục khắc phục? Quyết định phải dựa trên tín hiệu vận hành và mức độ ảnh hưởng.

Khi migration thất bại, cần đọc log để xác định changeset và câu lệnh gây lỗi, kiểm tra DATABASECHANGELOG, DATABASECHANGELOGLOCK và trạng thái schema thực tế. Không giả định rằng toàn bộ changeset luôn được rollback nguyên tử: khả năng transaction phụ thuộc DBMS, loại câu lệnh và cấu hình thực thi. Một số lệnh DDL có thể tự commit hoặc không hỗ trợ transaction như mong đợi.

Nếu cần chạy lại sau lỗi, trước hết phải xác minh thay đổi đã thực hiện đến đâu. Việc sửa trực tiếp bảng lịch sử để ép Liquibase chạy lại có thể làm lịch sử không còn phản ánh trạng thái thật. Hãy chọn phương án khôi phục hoặc forward fix có kiểm soát, sau đó ghi nhận thay đổi bằng migration mới khi phù hợp.

## 6. Tích hợp Liquibase với Spring Boot

Trong ứng dụng Spring Boot, Liquibase thường được tích hợp qua dependency Liquibase tương ứng với phiên bản Spring Boot đang dùng. Khi dependency có mặt và cấu hình được bật, Spring Boot có thể tự động khởi chạy migration trong quá trình khởi tạo application context.

Một cấu hình tối giản trong application.yml có thể như sau:

~~~yaml
spring:
  liquibase:
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    enabled: true
~~~

Datasource của Spring Boot cung cấp kết nối cho Liquibase trong cấu hình phổ biến. Tùy hệ thống, nhóm có thể cấu hình datasource hoặc Liquibase riêng, schema lưu bảng lịch sử, default schema, contexts, labels và các tham số liên quan. Cần kiểm tra tài liệu của phiên bản Spring Boot và Liquibase cụ thể để dùng đúng tên thuộc tính.

Một luồng làm việc phù hợp cho môi trường phát triển:

1. Lập trình viên tạo changeset trong thư mục changelog và cập nhật changelog gốc để nạp tệp đó.
2. Khởi động ứng dụng hoặc chạy Liquibase trên cơ sở dữ liệu thử nghiệm.
3. Kiểm tra schema, dữ liệu và log migration.
4. Chạy kiểm thử ứng dụng trên schema vừa được cập nhật.
5. Đưa changelog vào cùng thay đổi mã nguồn để review và phát hành.

Trong production, cần quyết định rõ ai chạy migration. Nếu mỗi instance Spring Boot tự chạy migration lúc khởi động, cơ chế khóa Liquibase hỗ trợ tránh thực thi đồng thời, nhưng startup của nhiều instance vẫn có thể chờ nhau và quyền của tài khoản ứng dụng có thể phải quá rộng. Với hệ thống có yêu cầu vận hành chặt chẽ, thường nên chạy migration bằng một bước hoặc job riêng trong pipeline trước khi triển khai các instance ứng dụng. Sau khi job thành công, ứng dụng mới được cập nhật.

Nếu pipeline hoặc job riêng chịu trách nhiệm chạy migration, cấu hình ứng dụng có thể tắt Liquibase auto-run bằng thuộc tính phù hợp, ví dụ **spring.liquibase.enabled: false**, để tránh chạy lặp từ từng instance. Cần bảo đảm job migration và ứng dụng dùng đúng changelog, đúng phiên bản artifact và đúng cơ sở dữ liệu mục tiêu.

Tài khoản chạy migration thường cần quyền DDL và một số quyền dữ liệu cao hơn tài khoản runtime. Nên cân nhắc tách tài khoản migration khỏi tài khoản ứng dụng chỉ cần quyền truy vấn và cập nhật nghiệp vụ. Bí mật kết nối phải lấy từ cơ chế quản lý secret của môi trường, không đưa vào repository.

## 7. Liquibase trong pipeline CI/CD

CI/CD biến migration thành một bước có thể lặp lại trong quy trình phát hành. Một pipeline tham khảo gồm:

| Bước | Kiểm tra hoặc hành động | Kết quả mong đợi |
|---|---|---|
| Review mã nguồn | Rà soát changelog, thứ tự changeset, precondition, rollback và tính tương thích | Migration có mục đích rõ ràng và được phê duyệt |
| Kiểm tra cú pháp | Chạy Liquibase validate trên changelog | Phát hiện cấu trúc hoặc tham chiếu changelog không hợp lệ |
| Xem trước SQL | Sinh SQL dự kiến bằng updateSQL hoặc lệnh tương ứng của phiên bản đang dùng | Reviewer thấy câu lệnh có thể tác động tới DBMS |
| Kiểm thử migration | Chạy update trên cơ sở dữ liệu dùng riêng cho kiểm thử, tốt nhất cùng DBMS với production | Migration chạy thành công và đạt trạng thái mong muốn |
| Kiểm thử ứng dụng | Chạy test tích hợp và kiểm tra tương thích với schema sau migration | Chức năng ứng dụng hoạt động với schema mới |
| Triển khai migration | Chạy update bằng thông tin kết nối của môi trường đích | DATABASECHANGELOG ghi nhận đúng changeset |
| Triển khai ứng dụng | Cập nhật ứng dụng sau khi migration đạt điều kiện | Phiên bản ứng dụng chạy trên schema tương thích |
| Xác minh sau triển khai | Kiểm tra log, health check, truy vấn quan trọng và số liệu vận hành | Phát hiện sớm lỗi schema hoặc dữ liệu |

Các lệnh thường gặp trong quy trình gồm validate để kiểm tra changelog, updateSQL để xem trước SQL và update để áp dụng migration. Cú pháp chính xác có thể khác giữa các phiên bản CLI hoặc cách tích hợp; pipeline nên cố định phiên bản Liquibase và kiểm thử lệnh trong môi trường build.

Không nên chạy migration production từ mọi nhánh build hoặc mọi lần khởi động ứng dụng. Cần gắn migration với artifact đã được phê duyệt, kiểm soát thông tin xác thực và bảo đảm chỉ một pipeline/job được quyền triển khai vào môi trường đó tại một thời điểm. Log triển khai nên ghi lại phiên bản ứng dụng, phiên bản changelog, môi trường, người hoặc pipeline kích hoạt và kết quả.

## 8. Quy trình thực hành một thay đổi an toàn

Giả sử một phiên bản ứng dụng cần thêm bảng customer_preference để lưu lựa chọn của khách hàng. Có thể triển khai theo trình tự sau:

**Bước 1 — Xác định tác động.** Làm rõ khóa chính, khóa ngoại, tính duy nhất, khả năng NULL, dung lượng dự kiến, quyền truy cập và cách ứng dụng đọc/ghi dữ liệu. Xác định các phiên bản ứng dụng nào sẽ cùng tồn tại trong đợt phát hành.

**Bước 2 — Tạo changeset.** Thêm changeset mới vào changelog theo quy ước id và author của dự án. Nếu thay đổi phụ thuộc trạng thái hiện có, thêm precondition phù hợp. Khai báo rollback khi có thể mô tả chính xác cách đảo ngược và đánh giá tác động mất dữ liệu.

**Bước 3 — Review migration.** Kiểm tra tên đối tượng, kiểu dữ liệu, ràng buộc, khả năng tương thích DBMS, thứ tự thực thi và ảnh hưởng khóa. Sinh SQL để xem câu lệnh thực tế nếu hệ thống cần kiểm soát chi tiết theo DBMS.

**Bước 4 — Chạy thử.** Áp dụng changelog trên cơ sở dữ liệu thử nghiệm cùng loại với môi trường đích. Kiểm tra bảng được tạo, ràng buộc có hiệu lực, dữ liệu mẫu được xử lý đúng và ứng dụng có thể sử dụng schema mới.

**Bước 5 — Kiểm tra lịch sử.** Xác minh changeset xuất hiện trong DATABASECHANGELOG với định danh và checksum mong đợi. Chạy lại quy trình update để xác nhận Liquibase không thực thi lại changeset đã hoàn tất.

**Bước 6 — Triển khai theo thứ tự.** Chạy migration bằng job phát hành được kiểm soát, chờ kết quả thành công rồi mới triển khai phiên bản ứng dụng phụ thuộc vào bảng mới. Với triển khai cuốn chiếu, duy trì khả năng tương thích giữa mã cũ và schema mới trong suốt quá trình.

**Bước 7 — Xác minh và lưu bằng chứng.** Kiểm tra health check, log ứng dụng, truy vấn nghiệp vụ, lịch sử migration và số liệu vận hành. Lưu kết quả pipeline để có thể truy vết khi cần điều tra.

## 9. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách phòng tránh |
|---|---|---|
| Sửa changeset đã chạy ở môi trường dùng chung | Checksum sai khác; lịch sử giữa môi trường không còn nhất quán | Giữ changeset đã phát hành bất biến và tạo changeset mới |
| Dùng id trùng hoặc đổi đường dẫn changelog tùy tiện | Liquibase có thể nhận diện sai hoặc không đối chiếu được lịch sử như dự kiến | Dùng quy ước định danh ổn định, review thay đổi cấu trúc tệp |
| Dùng MARK_RAN để bỏ qua lỗi | Lịch sử có thể ghi nhận changeset đã xử lý trong khi schema chưa đạt trạng thái yêu cầu | Chỉ dùng sau khi xác minh trạng thái thực tế tương đương với kết quả migration |
| Dùng cùng tài khoản quyền cao cho ứng dụng runtime | Tăng phạm vi thiệt hại nếu thông tin xác thực bị lộ hoặc ứng dụng bị khai thác | Tách quyền migration và quyền runtime khi phù hợp |
| Chạy DDL hoặc backfill lớn trực tiếp lúc nhiều instance khởi động | Startup kéo dài, cạnh tranh khóa và tải lớn lên cơ sở dữ liệu | Dùng migration job có kiểm soát, đo tải và chia nhỏ tác vụ dữ liệu |
| Giả định rollback luôn phục hồi được dữ liệu | Có thể mất dữ liệu hoặc tạo schema không tương thích với ứng dụng | Đánh giá khả năng đảo ngược, backup/restore và phương án forward fix |
| Chỉ kiểm thử trên H2 trong khi production dùng DBMS khác | Khác biệt SQL, kiểu dữ liệu, DDL và transaction có thể bị bỏ sót | Kiểm thử migration trên cùng loại DBMS với môi trường đích |
| Không xem trước SQL và không kiểm tra sau triển khai | Có thể phát hành câu lệnh tốn kém hoặc không đúng dự kiến | Review SQL, log, lịch sử và các chỉ số sau triển khai |

## 10. Danh sách kiểm tra trước khi phát hành

Trước khi cho phép pipeline cập nhật cơ sở dữ liệu, hãy xác nhận:

- Changelog gốc nạp đúng các tệp migration mới.
- Mỗi changeset có id, author và mục đích rõ ràng; không sửa nội dung changeset đã triển khai.
- Preconditions phản ánh đúng giả định về trạng thái môi trường; hành vi onFail và onError đã được cân nhắc.
- SQL sinh ra phù hợp với DBMS và phiên bản đích.
- Migration đã chạy trên dữ liệu thử nghiệm đủ đại diện; thay đổi dữ liệu lớn có kế hoạch theo dõi riêng.
- Rollback hoặc phương án forward fix đã được đánh giá; backup và khả năng phục hồi được xác nhận khi cần.
- Schema mới tương thích với phiên bản ứng dụng trong suốt quá trình triển khai.
- Chỉ một job/pipeline chịu trách nhiệm cập nhật môi trường đích; quyền và secret được giới hạn phù hợp.
- DATABASECHANGELOG và log triển khai thể hiện đúng changeset, checksum và kết quả.
- Có bước xác minh sau triển khai và người chịu trách nhiệm xử lý khi migration thất bại.

## 11. Kết luận

Liquibase đưa thay đổi schema và dữ liệu vào quy trình phát triển phần mềm dưới dạng migration có định danh, thứ tự và lịch sử. Changelog giúp nhóm quản lý ý định thay đổi; changeset là đơn vị thực thi; precondition xác nhận trạng thái đầu vào; checksum phát hiện nội dung bị sửa; DATABASECHANGELOG lưu lịch sử; còn cơ chế khóa giúp điều phối các lần cập nhật đồng thời.

Giá trị của Liquibase thể hiện rõ nhất khi nó được tích hợp xuyên suốt từ review mã nguồn, kiểm thử, đóng gói đến triển khai và vận hành. Để sử dụng an toàn, nhóm cần giữ changeset đã phát hành ổn định, kiểm thử trên DBMS thực tế, quản lý khác biệt môi trường có chủ đích, thiết kế migration tương thích với nhiều phiên bản ứng dụng và chuẩn bị phương án phục hồi. Khi những thực hành này được duy trì, cơ sở dữ liệu trở thành một phần có thể dự đoán và truy vết trong vòng đời ứng dụng.
