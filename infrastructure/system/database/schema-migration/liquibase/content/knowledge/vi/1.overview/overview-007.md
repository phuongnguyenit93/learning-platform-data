# Cách tiếp cận tài liệu Liquibase theo phiên bản, hệ quản trị và giấy phép

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, mục tiêu là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase thông qua changelog, changeset, precondition, checksum và lịch sử triển khai; đồng thời thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Để áp dụng đúng các kiến thức đó, cần đọc tài liệu theo đúng ba điều kiện của hệ thống đang vận hành: **phiên bản Liquibase**, **hệ quản trị cơ sở dữ liệu (DBMS)** và **gói giấy phép/tính năng được cấp quyền**.

Một trang hướng dẫn có thể mô tả cú pháp đúng cho phiên bản mới nhưng không còn phù hợp với bản đang chạy; một change type có thể được hỗ trợ trên PostgreSQL nhưng sinh SQL khác trên Oracle; một tính năng có thể xuất hiện trong tài liệu sản phẩm nhưng yêu cầu gói thương mại. Vì vậy, trước khi sao chép cấu hình hoặc migration từ tài liệu, hãy xác định rõ cả ba điều kiện này.

## 1. Ba trục cần xác định trước khi đọc tài liệu

| Trục | Cần xác định | Tác động đến migration |
|---|---|---|
| Phiên bản Liquibase | Phiên bản CLI, thư viện `liquibase-core` và các extension đang thực sự được nạp | Quyết định cú pháp, tham số lệnh, hành vi checksum, change type và khả năng tương thích |
| DBMS | Sản phẩm và phiên bản máy chủ, ví dụ PostgreSQL, Oracle, MySQL hoặc SQL Server | Quyết định kiểu dữ liệu, cú pháp SQL, khả năng transactional DDL, cách tạo khóa và giới hạn của từng change type |
| Giấy phép | Bản phân phối, gói thuê bao và quyền sử dụng tính năng trong môi trường chạy | Quyết định những tính năng thương mại, chính sách, báo cáo hoặc cơ chế quản trị nào có thể dùng hợp lệ |

Ba trục này độc lập với nhau. DBMS được Liquibase nhận diện không đồng nghĩa mọi tính năng dành cho DBMS đó đều có trong gói giấy phép hiện tại. Tương tự, có quyền dùng một tính năng không đảm bảo cú pháp của nó tồn tại trong phiên bản Liquibase cũ đang được triển khai.

## 2. Xác định phiên bản Liquibase thực tế

Không nên suy ra phiên bản từ một trang tài liệu đang mở, từ phiên bản Spring Boot, hoặc từ tên module trong dự án. Hãy kiểm tra thành phần thực sự chạy ở từng nơi.

Với CLI, chạy:

```bash
liquibase --version
```

Với dự án Maven, kiểm tra cây dependency để biết phiên bản `liquibase-core` được giải quyết cuối cùng:

```bash
mvn dependency:tree -Dincludes=org.liquibase
```

Với Gradle, có thể xem dependency được chọn trong runtime classpath:

```bash
./gradlew dependencyInsight --dependency liquibase-core --configuration runtimeClasspath
```

Nếu ứng dụng Spring Boot tự chạy Liquibase khi khởi động, phiên bản thư viện trên runtime classpath mới là căn cứ quan trọng. Nếu CI/CD dùng Liquibase CLI trong container hoặc một bước triển khai riêng, phải kiểm tra phiên bản của CLI đó nữa. Hai đường chạy có thể vô tình dùng hai phiên bản khác nhau, dẫn đến kết quả `validate`, checksum hoặc SQL sinh ra không giống nhau.

Ngoài phiên bản lõi, cần ghi nhận các extension đang sử dụng, phiên bản Java, driver JDBC và phiên bản DBMS. Extension có vòng đời phát hành riêng; không nên mặc định rằng extension mới nhất tương thích với mọi phiên bản `liquibase-core`. Đọc hướng dẫn tương thích của extension và khóa phiên bản dependency trong cấu hình build để môi trường phát triển, kiểm thử và triển khai dùng cùng bộ thành phần đã được xác nhận.

## 3. Chọn đúng bộ tài liệu theo phiên bản

Tài liệu Liquibase thường gồm nhiều loại nội dung, mỗi loại trả lời một câu hỏi khác nhau:

- **Concepts** giải thích mô hình như changelog, changeset, checksum, precondition, contexts, labels và bảng lịch sử.
- **Reference** mô tả cú pháp change type, thuộc tính changelog, tham số CLI, cấu hình và hành vi cụ thể.
- **How-to/tutorial** đưa ra quy trình thực hiện một tác vụ; ví dụ nên được kiểm tra lại theo phiên bản và DBMS của dự án.
- **Release notes và upgrade/migration guide** nêu thay đổi giữa các bản, tính năng mới, hành vi bị loại bỏ, thay đổi mặc định và lưu ý khi nâng cấp.
- **Compatibility/support information** cho biết tổ hợp Liquibase, Java, driver và DBMS nào được hỗ trợ.

Ưu tiên tài liệu gắn với đúng phiên bản đang chạy. Nếu trang mặc định hiển thị tài liệu của bản mới nhất, hãy chuyển sang bộ tài liệu hoặc release tương ứng trước khi áp dụng cú pháp. Khi không tìm thấy trang phiên bản cũ, dùng tài liệu mới để hiểu khái niệm nhưng phải xác minh từng tham số, change type và hành vi bằng release notes, reference của bản đang dùng và thử nghiệm trên môi trường tương đương.

Khi nâng cấp Liquibase, đọc release notes theo từng khoảng phiên bản từ bản hiện tại đến bản đích. Chú ý các thay đổi liên quan đến:

1. Cú pháp changelog và cách phân tích YAML, XML, JSON hoặc formatted SQL.
2. Tham số CLI, tên lệnh, giá trị mặc định và cách đọc cấu hình.
3. Change type, cách ánh xạ kiểu dữ liệu và SQL được sinh cho từng DBMS.
4. Checksum và cách Liquibase nhận diện changeset đã được thực thi.
5. Extension, driver JDBC, Java runtime và tích hợp Spring Boot.
6. Quy tắc rollback, precondition và cách xử lý lỗi khi cập nhật schema.

Một changeset đã chạy ở môi trường dùng chung nên được xem là lịch sử triển khai bất biến. Nếu cần thay đổi cấu trúc, hãy tạo changeset mới thay vì chỉnh sửa nội dung changeset cũ. Việc thay đổi nội dung có thể làm checksum không còn khớp với giá trị đã lưu trong `DATABASECHANGELOG`. Chỉ xử lý checksum theo hướng dẫn của đúng phiên bản và sau khi hiểu nguyên nhân; không dùng thao tác xóa hoặc làm mới checksum để che giấu việc sửa lịch sử migration.

## 4. Đọc tài liệu theo DBMS đích

Liquibase cung cấp một mô hình changelog chung, nhưng kết quả cuối cùng vẫn phụ thuộc vào khả năng và cú pháp của DBMS. Với mỗi thay đổi, hãy phân biệt:

- **Change type độc lập DBMS**: mô tả ý định như tạo bảng, thêm cột hoặc tạo khóa. Liquibase sẽ chuyển ý định đó thành SQL phù hợp với DBMS được kết nối, trong phạm vi change type hỗ trợ.
- **SQL đặc thù DBMS**: dùng khi cần cú pháp hoặc tính năng riêng, chẳng hạn một loại index, kiểu dữ liệu, stored procedure hoặc thao tác quản trị riêng của máy chủ.
- **Khác biệt về hành vi**: cùng một lệnh có thể khác về transaction, khóa, cách đặt tên, phân biệt chữ hoa/chữ thường, giá trị identity/sequence hoặc khả năng rollback.

Trước khi chọn change type, tra cứu hỗ trợ cho DBMS và phiên bản máy chủ cụ thể. Đừng chỉ kiểm tra tên DBMS tổng quát: một tính năng có thể yêu cầu phiên bản máy chủ tối thiểu hoặc có giới hạn theo driver. Với thao tác phức tạp, kiểm tra SQL được sinh và đối chiếu với tài liệu của chính DBMS.

### 4.1. Dùng `dbms` để giới hạn changeset

Thuộc tính `dbms` cho phép một changeset chỉ áp dụng cho DBMS được chỉ định. Ví dụ sau minh họa một bảng audit chỉ được tạo trên PostgreSQL:

```yaml
databaseChangeLog:
  - changeSet:
      id: 2026-01-create-audit-event
      author: platform-team
      dbms: postgresql
      preConditions:
        - onFail: HALT
        - not:
            - tableExists:
                tableName: audit_event
      changes:
        - createTable:
            tableName: audit_event
            columns:
              - column:
                  name: id
                  type: BIGINT
                  autoIncrement: true
                  constraints:
                    primaryKey: true
              - column:
                  name: event_type
                  type: VARCHAR(100)
                  constraints:
                    nullable: false
```

`dbms` xác định phạm vi hệ quản trị mà changeset được phép chạy. Precondition `tableExists` trong ví dụ là một kiểm tra bổ sung: nếu bảng đã tồn tại ngoài lịch sử Liquibase, changeset dừng để người vận hành điều tra thay vì tiếp tục trong trạng thái không rõ ràng. Trong dự án thực tế, cần xác nhận tên DBMS mà Liquibase nhận diện và cú pháp YAML theo đúng phiên bản đang sử dụng.

Nếu nhiều DBMS cần cùng một kết quả nghiệp vụ nhưng SQL khác nhau, có thể tạo các changeset riêng, mỗi changeset có `dbms` tương ứng. Mỗi changeset cần `id` duy nhất trong changelog. Nếu thao tác dùng được chung, ưu tiên change type chuẩn để giảm số nhánh phải bảo trì. Chỉ chuyển sang SQL đặc thù khi khác biệt của DBMS thực sự yêu cầu.

### 4.2. Phân biệt `dbms`, precondition, context và label

Các cơ chế này giải quyết những câu hỏi khác nhau:

| Cơ chế | Câu hỏi được trả lời | Ví dụ sử dụng |
|---|---|---|
| `dbms` | Changeset dành cho hệ quản trị nào? | Chỉ chạy SQL riêng trên PostgreSQL |
| Precondition | Điều kiện của database có cho phép chạy thay đổi này không? | Kiểm tra bảng, cột, DBMS hoặc kết quả truy vấn trước khi thực thi |
| Context | Lần triển khai này có chọn nhóm changeset mang ngữ cảnh nào? | Dữ liệu mẫu chỉ dùng ở môi trường kiểm thử |
| Label | Bộ thay đổi nào được chọn theo nhãn phát hành hoặc mục đích? | Chọn nhóm migration theo phiên bản sản phẩm |

Context và label là bộ lọc triển khai; chúng không thay thế việc xác định DBMS và cũng không cấp quyền sử dụng tính năng theo giấy phép. Precondition là cơ chế kiểm tra điều kiện tại thời điểm chạy, không nên dùng để thay thế việc thiết kế changelog rõ ràng hoặc để bỏ qua một migration thất bại.

### 4.3. Kiểm tra SQL sinh ra và khả năng rollback

Trước khi triển khai, dùng `validate` để kiểm tra cấu trúc changelog và dùng `update-sql` để xem SQL Liquibase dự kiến thực thi. Ví dụ:

```bash
liquibase validate \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  --url="${JDBC_URL}"

liquibase update-sql \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  --url="${JDBC_URL}"
```

`update-sql` giúp review câu lệnh được sinh ra trước khi áp dụng, nhưng không thay thế kiểm thử trên đúng DBMS và phiên bản máy chủ. Hãy kiểm tra kiểu dữ liệu, constraint, index, thứ tự phụ thuộc, khóa và tác động đến dữ liệu hiện hữu. Với SQL tùy chỉnh, xác minh câu lệnh trực tiếp bằng công cụ hoặc môi trường thử nghiệm của DBMS.

Đọc tài liệu rollback cho từng change type và từng DBMS. Không phải mọi thay đổi đều có thể tự động đảo ngược an toàn; thao tác xóa dữ liệu, thay đổi không gian lưu trữ hoặc SQL tùy chỉnh có thể cần rollback tường minh. Một rollback về mặt cú pháp cũng không bảo đảm khôi phục được dữ liệu đã mất. Hãy thử cả chiều triển khai lẫn chiều khôi phục trên dữ liệu mô phỏng gần với thực tế.

## 5. Kiểm tra tính năng theo giấy phép

Tài liệu sản phẩm có thể mô tả cả chức năng trong bản cộng đồng/mã nguồn mở và chức năng thuộc các gói thương mại. Tên gói, phạm vi tính năng và cách cấp phép có thể thay đổi theo thời điểm phát hành; vì vậy, cần đối chiếu trang license/pricing hoặc tài liệu entitlement hiện hành với hợp đồng và cấu hình của tổ chức.

Khi một trang hướng dẫn đề cập đến tính năng cần giấy phép, xác minh các điểm sau:

1. Tính năng thuộc bản phân phối hoặc gói nào; có yêu cầu license key, tài khoản hay dịch vụ bổ sung không?
2. Gói mà nhóm đang sở hữu có quyền dùng tính năng đó trong môi trường phát triển, kiểm thử và production không?
3. Phiên bản Liquibase đang chạy có hỗ trợ tính năng đó không, và extension hoặc thành phần bổ sung nào phải được cài đặt?
4. Cơ chế cấp phép có áp dụng cho CLI, thư viện nhúng, container hoặc pipeline đang triển khai không?
5. Có giới hạn vận hành, điều kiện hỗ trợ hoặc yêu cầu bảo mật nào cần tuân thủ không?

Không suy luận quyền sử dụng chỉ từ việc lệnh có trong tài liệu, package có thể tải xuống hoặc tính năng xuất hiện trong giao diện. Ngược lại, cũng không nên mặc định mọi chức năng nâng cao đều bị khóa: hãy kiểm tra điều kiện cấp phép chính thức của đúng phiên bản và gói sản phẩm.

Giấy phép là điều kiện quyền sử dụng tính năng; DBMS là điều kiện tương thích kỹ thuật. Ví dụ, một change type có thể hỗ trợ PostgreSQL ở cấp kỹ thuật nhưng một tính năng quản trị đi kèm vẫn cần entitlement thương mại. Hai câu hỏi này cần được xác minh riêng. Không ghi license key hoặc bí mật triển khai vào changelog, repository, log CI/CD hay tài liệu chia sẻ; sử dụng secret store và cơ chế cấu hình được tổ chức phê duyệt.

## 6. Quy trình tra cứu và xác nhận trước khi viết migration

Áp dụng quy trình sau cho mỗi thay đổi schema hoặc dữ liệu:

1. **Chụp lại baseline**: ghi nhận phiên bản Liquibase CLI/core, extension, Java, driver, DBMS và phiên bản máy chủ ở từng môi trường.
2. **Chọn tài liệu đúng phiên bản**: mở concepts/reference của release tương ứng; đọc release notes nếu ví dụ hoặc tham số đến từ một bản khác.
3. **Kiểm tra DBMS**: xác nhận change type, kiểu dữ liệu, precondition và cú pháp SQL có hỗ trợ trên DBMS đích.
4. **Kiểm tra entitlement**: đối chiếu tính năng được hướng dẫn với bản phân phối và giấy phép tổ chức đang sử dụng.
5. **Thiết kế changelog**: dùng changeset nhỏ, có `id` ổn định, author rõ ràng, precondition phù hợp và phạm vi `dbms`/context/label có chủ đích.
6. **Review trước khi chạy**: chạy `validate`, xem `update-sql`, kiểm tra `DATABASECHANGELOG` và `DATABASECHANGELOGLOCK` khi cần điều tra lịch sử hoặc trạng thái khóa.
7. **Thử triển khai và khôi phục**: chạy trên database kiểm thử cùng loại và phiên bản với đích; xác minh dữ liệu, checksum, rollback và khả năng chạy lại.
8. **Đồng bộ môi trường**: khóa phiên bản công cụ trong build hoặc container; giữ cấu hình kết nối và secret ngoài changelog; ghi nhận khác biệt có chủ ý giữa dev, test, staging và production.

Một bảng tương thích ngắn trong repository giúp cả nhóm tra cứu nhất quán:

| Thành phần | Giá trị cần lưu | Nơi xác nhận |
|---|---|---|
| Liquibase CLI và core | Phiên bản chính xác | `liquibase --version`, dependency tree hoặc runtime classpath |
| Extension | Tên artifact và phiên bản | Cấu hình build và tài liệu tương thích của extension |
| DBMS | Sản phẩm và phiên bản server | Cấu hình môi trường và thông tin từ máy chủ database |
| Driver | Artifact và phiên bản JDBC | Dependency được giải quyết trong ứng dụng/pipeline |
| Giấy phép | Gói và quyền tính năng | Hồ sơ entitlement và tài liệu license chính thức |
| Tích hợp | Cách Liquibase được gọi | Spring Boot runtime, CLI, container hoặc pipeline |

## 7. Áp dụng trong Spring Boot và CI/CD

Với Spring Boot, xác định phiên bản `liquibase-core` mà ứng dụng thực sự nạp và cấu hình changelog được dùng khi khởi động. Không giả định phiên bản Liquibase chỉ dựa vào phiên bản Spring Boot; dependency management của dự án có thể ghi đè phiên bản mặc định. Khi ứng dụng và pipeline cùng quản lý database, cần thống nhất phiên bản, changelog và thứ tự thực thi để tránh hai cơ chế triển khai cạnh tranh.

Trong CI/CD, cố định phiên bản CLI hoặc container image thay vì dùng một tag thay đổi theo thời gian. Pipeline nên có bước kiểm tra changelog, tạo SQL dự kiến để review và triển khai vào môi trường kiểm thử cùng loại DBMS với production. Chỉ đưa thay đổi lên môi trường tiếp theo sau khi đã xác nhận kết quả, lịch sử changeset và phương án rollback. Nếu dùng tính năng có điều kiện license, kiểm tra entitlement của đúng runner hoặc môi trường chạy và truyền bí mật qua secret manager.

Với mỗi môi trường, URL kết nối, thông tin xác thực, schema mặc định và quyền database có thể khác nhau. Hãy đặt các giá trị này trong cấu hình môi trường hoặc secret store; giữ nội dung changelog có thể review trong version control. Bảng `DATABASECHANGELOG` giúp đối chiếu changeset đã chạy, còn `DATABASECHANGELOGLOCK` hỗ trợ nhận biết trạng thái khóa khi một tiến trình đang cập nhật. Khi điều tra sai khác, so sánh lịch sử thực thi, phiên bản Liquibase và DBMS trước khi quyết định chạy lại hoặc sửa migration.

## 8. Những sai lầm thường gặp

- **Dùng trang “latest” cho một runtime cũ**: tham số hoặc change type có thể chưa tồn tại hoặc đã đổi hành vi. Cần chuyển về tài liệu của đúng release và đọc release notes.
- **Chỉ kiểm tra DBMS mà bỏ qua phiên bản server**: một cú pháp hoặc khả năng có thể chỉ có ở một số phiên bản. Cần kiểm tra compatibility/support matrix và thử trên server tương đương.
- **Cho rằng SQL sinh ra giống nhau ở mọi DBMS**: cùng một change type có thể tạo kiểu dữ liệu hoặc câu lệnh khác. Cần review `update-sql` và kiểm thử trên DBMS đích.
- **Nhầm context/label với quyền license**: bộ lọc changeset không cấp entitlement. Cần kiểm tra giấy phép độc lập.
- **Sửa changeset đã triển khai để “sửa nhanh”**: checksum có thể lệch giữa các môi trường và lịch sử không còn tái lập được. Hãy bổ sung changeset mới, xử lý checksum theo hướng dẫn chính thức khi có lý do hợp lệ.
- **Tin rằng mọi change type đều rollback tự động**: khả năng đảo ngược tùy loại thay đổi và DBMS. Cần đọc reference rollback và diễn tập khôi phục.
- **Để CLI và ứng dụng dùng phiên bản khác nhau**: kết quả kiểm tra và triển khai có thể khác. Hãy khóa phiên bản và kiểm tra dependency thực tế trong cả hai đường chạy.

## 9. Checklist tra cứu nhanh

Trước khi đưa một thay đổi Liquibase vào review, có thể tự kiểm tra:

- [ ] Đã xác định phiên bản CLI, `liquibase-core` và extension đang chạy.
- [ ] Đã mở tài liệu/reference đúng phiên bản và đọc release notes liên quan.
- [ ] Đã xác định DBMS cùng phiên bản server của môi trường đích.
- [ ] Đã xác minh change type, cú pháp SQL, precondition và rollback trên DBMS đó.
- [ ] Đã kiểm tra tính năng có yêu cầu gói hoặc entitlement thương mại hay không.
- [ ] Changeset đã triển khai được giữ bất biến; thay đổi mới được bổ sung bằng changeset mới.
- [ ] `validate`, SQL preview và kiểm thử trên môi trường tương đương đã đạt.
- [ ] Phiên bản và cấu hình triển khai giữa Spring Boot, CLI và CI/CD đã được thống nhất.
- [ ] Thông tin xác thực và license key được quản lý bằng secret store, không nằm trong changelog hoặc repository.

Khi chưa chắc chắn một ví dụ có áp dụng được hay không, hãy ghi lại phiên bản Liquibase, DBMS/server, gói giấy phép và đường chạy đang dùng, sau đó kiểm tra từng điều kiện trong tài liệu chính thức. Cách tiếp cận này giúp nhóm đưa ra migration có thể review và tái lập, giảm sai lệch giữa các môi trường, đồng thời giữ được lịch sử schema và dữ liệu rõ ràng trong suốt vòng đời triển khai.
