# Kiểm soát quyền sửa changelog và phê duyệt production

Changelog Liquibase là mã nguồn có thể làm thay đổi cấu trúc và dữ liệu của database. Người có quyền sửa changelog có thể thêm SQL tùy ý, thay đổi thứ tự migration, bỏ qua precondition, xóa dữ liệu hoặc làm sai lệch lịch sử triển khai. Người có quyền chạy migration trên production lại có thể thực thi những thay đổi đó bằng quyền DDL/DML của pipeline. Vì vậy, bảo mật migration cần kiểm soát đồng thời **ai được sửa changelog, ai được review, ai được phê duyệt triển khai và danh tính nào được phép thực thi trên database production**.

Bài học thuộc chương **Bảo mật** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Phạm vi module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Bài này tập trung vào quyền truy cập repository, bảo vệ nhánh và file changelog, phân tách nhiệm vụ giữa người viết và người phê duyệt, gắn phê duyệt production với artifact đã kiểm tra, bảo vệ thông tin xác thực database và lưu dấu vết kiểm toán. Liquibase theo dõi changeset và điều phối migration; việc phân quyền con người và phê duyệt triển khai thường phải được thực thi bởi hệ thống quản lý mã nguồn, CI/CD, secret manager và DBMS.

Sau bài học, bạn có thể:

1. Nhận diện rủi ro bảo mật từ quyền sửa changelog và quyền thực thi migration.
2. Thiết kế quyền repository, branch protection và CODEOWNERS cho file nhạy cảm.
3. Áp dụng nguyên tắc least privilege và separation of duties.
4. Xây dựng quy trình review SQL, precondition, rollback và thay đổi phá hủy.
5. Thiết lập phê duyệt production gắn với đúng artifact, môi trường và kết quả kiểm tra.
6. Bảo vệ migration credentials, secrets và quyền DDL trên DBMS.
7. Lưu audit trail, quản lý ngoại lệ khẩn cấp và kiểm soát CI/CD.

## 1. Vì sao quyền sửa changelog là quyền nhạy cảm?

Một changeset có thể tạo, sửa hoặc xóa bảng/cột/index/constraint; cập nhật hoặc xóa dữ liệu; tạo view, function, procedure, trigger; thay đổi quyền và owner; hoặc chạy SQL tùy chỉnh qua sql, sqlFile hay formatted SQL.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "SEC-101-remove-expired-records"
      author: "platform-team"
      changes:
        - sql:
            sql: |
              DELETE FROM app.session
              WHERE expires_at < CURRENT_TIMESTAMP;
~~~

Đoạn SQL có thể hợp lệ và hữu ích, nhưng nếu người sửa bỏ điều kiện WHERE thì tác động trở thành xóa toàn bộ bảng. Một thay đổi nhỏ trong changelog có thể ảnh hưởng lớn tới dữ liệu và hoạt động production.

Vì vậy, quyền ghi vào thư mục changelog phải được xem là quyền đề xuất thay đổi database. Người có quyền merge vào nhánh triển khai có thể gián tiếp cho phép pipeline thực thi SQL trên môi trường có dữ liệu quan trọng.

### 1.1. Những tài sản cần bảo vệ

| Tài sản | Rủi ro |
|---|---|
| Changelog và SQL files | Chèn DDL/DML nguy hiểm, bỏ qua kiểm tra |
| Root/master changelog | Include migration không được review hoặc đổi thứ tự |
| Build/deployment pipeline | Thực thi artifact khác với artifact đã duyệt |
| Production credentials | Truy cập database hoặc chạy lệnh trái phép |
| DATABASECHANGELOG | Làm sai lệch bằng chứng lịch sử nếu bị sửa trực tiếp |
| DATABASECHANGELOGLOCK | Can thiệp điều phối migration |
| Release artifact | Thay nội dung sau review |
| Approval/audit records | Mất khả năng truy vết người và quyết định |

### 1.2. Ba quyền cần phân biệt

1. **Quyền sửa:** tạo hoặc thay đổi changelog trong repository.
2. **Quyền phê duyệt:** xác nhận thay đổi và cho phép phát hành.
3. **Quyền thực thi:** pipeline hoặc danh tính được ủy quyền chạy migration trên database.

Một developer có thể tạo pull request nhưng không được tự phê duyệt thay đổi của mình. Release manager có thể phê duyệt production mà không cần quyền sửa SQL. Pipeline có thể có quyền DDL trên database nhưng người dùng không được gọi pipeline với tham số tùy ý.

## 2. Mô hình kiểm soát từ mã nguồn đến production

~~~mermaid
flowchart TD
    A[Developer tạo changeset] --> B[Pull request]
    B --> C[Static checks và Liquibase validation]
    C --> D[Review của code owner và DB owner]
    D --> E[Merge vào protected branch]
    E --> F[Build artifact bất biến]
    F --> G[Integration test và SQL review]
    G --> H[Production approval]
    H --> I[Pipeline chạy Liquibase]
    I --> J[Verify schema, history và audit]
~~~

Mỗi bước cần có danh tính, quyền và bằng chứng tương ứng. Một pull request được review không có nghĩa pipeline được phép triển khai bất kỳ commit nào sau đó. Approval production cần gắn với artifact cụ thể đã qua kiểm tra.

Nguyên tắc thiết kế:

- Cấp quyền theo vai trò và nhu cầu công việc.
- Mặc định không có quyền ghi production.
- Tách người tạo thay đổi khỏi người phê duyệt khi rủi ro yêu cầu.
- Chỉ phát hành artifact đã được kiểm tra.
- Không để người dùng tự nhập URL hoặc credential production vào pipeline.
- Mọi thao tác production có audit trail.
- Ngoại lệ khẩn cấp có phạm vi, thời hạn và người chịu trách nhiệm.
- Quyền được rà soát định kỳ và thu hồi khi không còn cần thiết.

## 3. Phân quyền repository theo least privilege

Repository chứa changelog cần phân vai rõ ràng.

| Vai trò | Quyền phù hợp |
|---|---|
| Developer | Đọc repository, tạo branch và pull request |
| Database developer | Đề xuất changeset trong phạm vi domain |
| Domain/database owner | Review tác động schema và dữ liệu |
| Security reviewer | Review quyền, credential, pipeline hoặc SQL nhạy cảm |
| Maintainer | Merge khi điều kiện bảo vệ đã đạt |
| Release manager | Điều phối phát hành và approval production |
| CI service identity | Đọc source, build và publish artifact |
| Deployment identity | Chạy migration theo môi trường được cấp quyền |

Nhóm nhỏ có thể kiêm nhiệm, nhưng cần quy định trường hợp nào bắt buộc người khác review và ai có thể bypass.

### 3.1. Tách quyền đọc và quyền ghi

Hầu hết thành viên có thể cần đọc changelog. Nhưng không phải ai cũng cần quyền push vào nhánh chính hoặc chỉnh sửa pipeline production.

- Cho phép đọc repository theo nhu cầu.
- Hạn chế quyền write/admin ở mức tối thiểu.
- Hạn chế quyền thay đổi branch protection và CODEOWNERS.
- Hạn chế quyền sửa secrets và production environment.
- Không dùng một tài khoản dùng chung cho nhiều developer.
- Thu hồi quyền khi chuyển nhóm hoặc kết thúc nhiệm vụ.

Quyền quản trị repository đặc biệt nhạy cảm vì có thể thay đổi chính sách review và bảo vệ nhánh. Nên giới hạn số người có quyền này và bật audit cho thao tác quản trị.

## 4. Bảo vệ root changelog và toàn bộ file được include

Các đường dẫn nhạy cảm thường gồm:

- Root changelog như db.changelog-master.yaml.
- Thư mục chứa changeset production.
- File SQL được tham chiếu bằng sqlFile.
- Changelog baseline và migration lịch sử.
- File cấu hình build hoặc script chạy Liquibase.
- Pipeline workflow và deployment definitions.
- Cấu hình contexts, labels, schema và datasource.

Có thể dùng CODEOWNERS hoặc cơ chế tương đương để yêu cầu owner review.

Ví dụ:

~~~text
/db/changelog/                 @database-platform
/db/changelog/baseline/        @database-platform @data-architecture
/db/changelog/releases/        @database-platform
/db/changelog/sql/             @database-platform @db-security
/.github/workflows/            @platform-engineering
/deploy/                       @release-engineering
~~~

Cú pháp và cách áp dụng owner phụ thuộc nền tảng quản lý mã nguồn. Cần xác minh rule thực sự bắt buộc review; chỉ thêm file CODEOWNERS mà không bật required review thì chưa tạo được kiểm soát.

### 4.1. Bảo vệ dependency được nạp gián tiếp

Một root changelog có thể include YAML khác, rồi YAML đó tham chiếu SQL bên ngoài:

~~~yaml
databaseChangeLog:
  - include:
      file: releases/2026/11/release.yaml
      relativeToChangelogFile: true
~~~

File release có thể tham chiếu SQL:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "DB-201-create-report"
      author: "reporting-team"
      changes:
        - sqlFile:
            path: ../sql/create_report.sql
            relativeToChangelogFile: true
~~~

Cần bảo vệ cả file release, SQL được tham chiếu và script phụ trợ. CI nên xác định dependency graph để reviewer xem được toàn bộ nội dung thực thi.

### 4.2. Bảo vệ build và pipeline

Một pull request có thể không sửa changelog nhưng thay workflow để bỏ approval, đổi database URL hoặc chạy script khác. Vì vậy, quyền review cần bao phủ workflow CI/CD, script gọi Liquibase, dependency/plugin version, runner image, cấu hình datasource, secret handling và quy tắc chọn environment.

Thay đổi pipeline có thể vô hiệu toàn bộ kiểm soát changelog nếu không được review đúng cấp.

## 5. Branch protection và pull request policy

Nhánh triển khai như main hoặc release branch nên được bảo vệ bằng các chính sách phù hợp:

- Không cho push trực tiếp, chỉ nhận thay đổi qua pull request.
- Bắt buộc một hoặc nhiều approval.
- Yêu cầu review từ code owner đối với changelog và pipeline.
- Bắt buộc CI checks đã định nghĩa.
- Yêu cầu nhánh cập nhật với base branch trước khi merge.
- Hủy approval cũ khi có commit mới làm thay đổi nội dung đã review.
- Hạn chế force push và xóa nhánh được bảo vệ.
- Hạn chế bypass rule, kể cả administrator.
- Lưu audit log của thao tác thay đổi policy.

Tên tùy chọn khác nhau giữa GitHub, GitLab, Bitbucket và hệ thống nội bộ. Hãy kiểm tra hành vi bằng pull request thử nghiệm, không chỉ nhìn cấu hình trên giao diện.

### 5.1. Approval phải áp dụng cho phiên bản cuối

Reviewer có thể phê duyệt pull request, sau đó developer push thêm commit chứa SQL mới. Nếu approval cũ vẫn được giữ nguyên, nội dung chưa được review có thể được merge.

Nên bật cơ chế dismiss stale approvals hoặc yêu cầu review lại khi có commit mới. Với thay đổi database rủi ro cao, approval phải gắn với diff cuối cùng.

### 5.2. Người tạo không tự thỏa điều kiện approval độc lập

Tùy chính sách nền tảng, loại trừ author khỏi số approval hợp lệ hoặc yêu cầu ít nhất một approval độc lập. Một người không nên vừa tạo thay đổi, vừa tự xác nhận, vừa tự bypass bước triển khai production nếu không có ngoại lệ được ghi nhận.

## 6. CODEOWNERS và trách nhiệm review

CODEOWNERS định tuyến review tới người chịu trách nhiệm với file. Nó không tự đánh giá SQL có an toàn hay không.

Ví dụ:

~~~text
/db/changelog/releases/orders/       @orders-db-owners
/db/changelog/releases/billing/      @billing-db-owners
/db/changelog/releases/security/     @database-security
/db/changelog/baseline/              @database-platform
~~~

Tránh quy định owner quá rộng khiến mọi pull request đều chờ một nhóm trung tâm, tạo bottleneck và khiến review thành hình thức. Owner nên hiểu domain và có đủ thẩm quyền từ chối thay đổi không phù hợp.

### 6.1. Review theo loại rủi ro

| Thay đổi | Reviewer cần thiết |
|---|---|
| Thêm cột nullable | Domain/database owner |
| Thêm NOT NULL hoặc unique constraint | Database owner và owner dữ liệu |
| DROP TABLE/COLUMN hoặc DELETE diện rộng | Database owner, domain owner và release owner |
| Thay đổi quyền/role/grant | Security hoặc database security owner |
| Chạy SQL tùy chỉnh | Người có chuyên môn DBMS và domain |
| Thay root changelog/baseline | Database platform owner |
| Thay workflow hoặc secret handling | Platform/security owner |
| Thay production deployment gate | Release/platform owner |

Đây là ma trận gợi ý; tổ chức cần định nghĩa rule chính xác theo mức độ ảnh hưởng và yêu cầu tuân thủ.

## 7. Separation of duties

**Separation of duties** giảm nguy cơ một người tự tạo, tự phê duyệt và tự thực thi thay đổi nhạy cảm mà không có kiểm tra độc lập.

| Hoạt động | Vai trò | Bằng chứng |
|---|---|---|
| Viết changeset | Developer/database engineer | Pull request |
| Review SQL/schema | Database/domain owner | Review approval |
| Review bảo mật | Security reviewer khi cần | Security approval |
| Merge | Maintainer | Merge record |
| Build artifact | CI identity | Artifact digest |
| Phê duyệt production | Release approver | Environment approval |
| Thực thi migration | Deployment identity | Job log và DB history |
| Xác minh sau triển khai | Operator/monitoring | Verification record |

Nhóm nhỏ có thể kiêm nhiệm, nhưng nên giữ ít nhất một điểm kiểm tra độc lập cho production changes có tác động lớn.

### 7.1. PR approval và production approval khác nhau

- PR approval xác nhận nội dung mã nguồn có thể được merge.
- Production approval xác nhận artifact cụ thể được phép triển khai lên môi trường cụ thể vào thời điểm cụ thể.

Không dùng một approval chung để thay thế cả hai nếu quy trình cần kiểm soát release riêng. Một PR có thể được merge nhưng chưa được phép triển khai production.

## 8. Review SQL như review mã có đặc quyền cao

SQL trong changelog cần được review về cú pháp, dữ liệu và tác động vận hành.

Các câu hỏi:

- Có DDL/DML vượt quá phạm vi ticket không?
- Có DROP, TRUNCATE, DELETE hoặc UPDATE diện rộng không?
- Điều kiện WHERE có đúng và đủ chặt không?
- Có nguy cơ mất dữ liệu hoặc truncate không?
- Có thay đổi quyền/owner không?
- Có function/trigger thay đổi hành vi ngoài dự kiến không?
- Có thao tác phụ thuộc DBMS/version cụ thể không?
- Có transaction hoặc lock kéo dài không?
- Có thể rollback an toàn không?
- Có cần backup, snapshot hoặc forward fix không?

Ví dụ cần review kỹ:

~~~sql
DELETE FROM app.customer;
~~~

Câu lệnh này xóa toàn bộ hàng. Nếu mục tiêu chỉ là xóa dữ liệu test, changeset không được phép đi vào root changelog production. Static policy có thể cảnh báo từ khóa nguy hiểm, nhưng quyết định cuối cùng cần review ngữ nghĩa và môi trường đích.

### 8.1. SQL tùy chỉnh cần review cùng file thực thi

Các thay đổi dùng sql, sqlFile, formatted SQL, stored procedure hoặc custom change có thể thực thi logic rộng. Không chỉ review YAML wrapper rồi bỏ qua file SQL.

CI cần xác định file phụ thuộc, hiển thị chúng trong pull request và bảo đảm reviewer xem được toàn bộ nội dung được triển khai.

### 8.2. Precondition không phải cơ chế cấp quyền

Precondition kiểm tra trạng thái database trước changeset. Nó không xác minh người tạo có được phép thay đổi bảng hay không và không thay thế approval.

~~~yaml
preConditions:
  - onFail: HALT
  - onError: HALT
  - tableExists:
      schemaName: app
      tableName: orders
~~~

Điều kiện này chỉ xác nhận bảng tồn tại theo khả năng kiểm tra của Liquibase. Người viết changelog vẫn có thể đưa changeset nguy hiểm vào repository nếu review không chặn.

## 9. Review rollback và thay đổi phá hủy

Rollback cần được xem như thay đổi độc lập có rủi ro. Một rollback DROP COLUMN có thể làm mất dữ liệu được ghi sau update; rollback tự động có thể không khôi phục được định nghĩa object cũ.

Khi review, xác định:

- Rollback có được hỗ trợ không?
- Có làm mất dữ liệu không?
- Có khôi phục trạng thái trước đó hay chỉ xóa object mới?
- Có phụ thuộc changeset khác không?
- Có tương thích DBMS đích không?
- Có cần forward fix thay vì rollback?
- Có backup/restore hoặc snapshot đã được thử không?

Với thay đổi phá hủy, yêu cầu approval độc lập và bằng chứng test mạnh hơn. Không dựa vào việc Liquibase có thể sinh auto rollback để kết luận an toàn.

### 9.1. Ghi rollback plan trong pull request

~~~text
Migration:
  Thêm cột app.orders.status và backfill từ legacy_state.

Tác động:
  Đọc/ghi thêm cột; không xóa cột cũ.

Rollback:
  Chỉ an toàn trước khi ứng dụng ghi dữ liệu riêng vào status.
  Sau thời điểm switch, ưu tiên forward fix hoặc restore dữ liệu đã lưu.

Kiểm thử:
  Fresh install, upgrade từ release trước, data assertions,
  rollback trên database disposable và kiểm tra thời gian lock.
~~~

Mô tả này giúp reviewer đánh giá rủi ro nghiệp vụ thay vì chỉ nhìn changeset syntax.

## 10. Bảo vệ changeset đã triển khai và checksum

Changeset đã chạy trên môi trường dùng chung nên được xem là bất biến. Sửa nội dung sau triển khai có thể gây checksum mismatch hoặc làm database mới và database cũ có kết quả khác nhau.

Kiểm soát cần có:

- CI phát hiện thay đổi file migration đã phát hành theo policy.
- Reviewer xác minh lịch sử trước khi chấp nhận sửa file cũ.
- Tạo changeset mới cho thay đổi tiếp theo.
- Lưu artifact release cũ để đối chiếu.
- Điều tra checksum mismatch thay vì tự động xóa.
- Không để pipeline tự động chạy clear-checksums để bỏ qua lỗi.

### 10.1. Checksum không phải chữ ký bảo mật

Checksum Liquibase giúp phát hiện nội dung changeset khác với nội dung đã ghi nhận theo cơ chế Liquibase. Nó không chứng minh tác giả đáng tin cậy, không thay thế chữ ký artifact và không ngăn người có quyền sửa cả changelog lẫn metadata database.

Để bảo vệ nguồn gốc:

- Dùng kiểm soát repository và review.
- Giữ commit/tag/release metadata.
- Có thể ký commit hoặc artifact theo chính sách tổ chức.
- Gắn deployment với digest của artifact.
- Bảo vệ DATABASECHANGELOG bằng quyền DBMS.
- Lưu audit log ở hệ thống độc lập phù hợp.

## 11. Bảo vệ root changelog, include và includeAll

Root changelog quyết định file nào được nạp và thứ tự migration. Người sửa root file có thể thêm SQL file chưa được review, bỏ include hoặc thay đổi thứ tự.

Kiểm soát:

1. Bảo vệ root changelog bằng code owner.
2. Review mọi thay đổi include/includeAll.
3. CI kiểm tra đường dẫn và dependency.
4. Giới hạn thư mục includeAll chỉ chứa artifact được quản lý.
5. Không để file thử nghiệm hoặc script tùy tiện trong thư mục được nạp.
6. Kiểm tra graph include đệ quy.
7. Xem update-sql và danh sách changeset được chọn trước phát hành.

### 11.1. Rủi ro includeAll

includeAll thuận tiện nhưng phạm vi nạp có thể mở rộng khi file mới được thêm vào thư mục. Nếu quyền ghi thư mục quá rộng, file bất ngờ có thể trở thành migration được thực thi mà không cần thay đổi root changelog.

Nên giới hạn quyền ghi, quy định naming convention, kiểm tra danh sách file trong CI và review mọi file mới.

## 12. Không cho phép chọn tùy ý changelog production

Pipeline production nên chạy root changelog đã được build và phát hành cùng artifact. Không nên cho người vận hành nhập đường dẫn file hoặc URL changelog tùy ý.

Nếu pipeline cho phép tham số hóa:

- Allowlist root changelog hợp lệ.
- Không nhận đường dẫn tùy ý từ người dùng không tin cậy.
- Không cho phép URL ngoài danh sách nguồn artifact.
- Kiểm tra artifact signature/digest nếu tổ chức sử dụng.
- Ghi lại changelog root, version và commit.
- Xác nhận môi trường đích qua cấu hình được bảo vệ.

Thay đổi tham số có thể khiến pipeline chạy bộ migration khác dù pull request đã được duyệt.

## 13. Phê duyệt production gắn với artifact cụ thể

Approval production phải xác định rõ:

- Artifact/version nào được triển khai.
- Digest hoặc commit nào tương ứng.
- Database/environment đích.
- Changeset pending sẽ chạy.
- SQL preview đã review.
- Người phê duyệt.
- Thời điểm và cửa sổ triển khai.
- Rollback/forward recovery plan.
- Kết quả kiểm tra sau triển khai.

Không phê duyệt nhãn chung như deploy latest nếu nội dung có thể thay đổi sau approval. Khi artifact thay đổi, approval cũ phải hết hiệu lực hoặc được đánh giá lại.

### 13.1. Promote cùng artifact qua các môi trường

Một quy trình tốt build artifact một lần rồi promote artifact đó qua dev, staging và production, thay vì build lại ở từng môi trường từ source có thể đã thay đổi.

~~~text
Commit C
  -> Build artifact A (digest D)
  -> Test A trên integration
  -> Approve A cho staging
  -> Test A trên staging
  -> Approve cùng A cho production
  -> Deploy A với production configuration
~~~

Cấu hình connection/secret thay đổi theo môi trường, nhưng nội dung changelog được phát hành phải giữ nguyên. Điều này giảm rủi ro production chạy artifact khác với artifact đã test.

### 13.2. Approval phải gắn với target

Cùng một artifact có thể được phép chạy trên staging nhưng chưa được phép chạy trên production. Approval cần gắn với environment/resource cụ thể, không chỉ với artifact.

## 14. Approval gate trong CI/CD

Các nền tảng CI/CD thường hỗ trợ protected environment, required reviewer, deployment approval hoặc manual gate. Chi tiết phụ thuộc sản phẩm.

Một gate production nên yêu cầu:

- Deployment job chỉ chạy sau khi quality checks pass.
- Environment được bảo vệ.
- Reviewer thuộc nhóm được phép.
- Người tạo deployment không thể tự phê duyệt nếu policy yêu cầu độc lập.
- Approval gắn với đúng artifact và target.
- Có timeout/expiration và hủy approval khi artifact thay đổi.
- Mọi lần approve/reject/bypass được lưu audit.
- Chỉ deployment identity được quyền truy cập secret production.

### 14.1. Phê duyệt không phải nhập mật khẩu database

Reviewer xác nhận thay đổi qua hệ thống CI/CD. Không gửi password production qua chat, pull request hoặc comment. Pipeline lấy secret từ kho quản lý bí mật sau khi gate cho phép job chạy.

### 14.2. Approval không thay thế kiểm thử

Một người bấm Approve không thể thay validate, integration test, data assertions và SQL review. Approval là quyết định trách nhiệm dựa trên bằng chứng đã có.

## 15. Least privilege cho database migration account

Liquibase cần quyền đủ để thực hiện changeset. Không mặc định cấp superuser/DBA cho mọi môi trường.

Thiết kế quyền:

- Tài khoản migration riêng với tài khoản runtime ứng dụng.
- Quyền chỉ trên database/schema/object cần quản lý.
- Chỉ cấp CREATE/ALTER/DROP khi migration thực sự cần.
- Quyền ghi DATABASECHANGELOG và DATABASECHANGELOGLOCK.
- Quyền sequence, routine hoặc grant theo changeset.
- Không cấp quyền quản trị server nếu không cần.
- Tách quyền read-only cho kiểm tra/diff khỏi quyền DDL cho update.
- Rà soát và thu hồi quyền tạm sau migration nếu chính sách yêu cầu.

### 15.1. Không dùng application user để chạy migration

Ứng dụng runtime thường chỉ cần SELECT/INSERT/UPDATE/DELETE theo chức năng. Nếu ứng dụng giữ credential có quyền CREATE/DROP, lỗ hổng ở tầng ứng dụng có thể dẫn tới thay đổi schema.

Dùng migration user riêng trong deployment job. Không nhúng credential DDL vào image ứng dụng hoặc file cấu hình được commit.

### 15.2. Kiểm tra quyền hiệu lực

Một user có vẻ không có DROP trực tiếp vẫn có thể nhận quyền qua role membership hoặc schema owner. Kiểm tra quyền hiệu lực, role inheritance, default privileges và owner của object theo DBMS.

Least privilege dựa trên quyền thực tế của connection, không chỉ danh sách GRANT trực tiếp.

## 16. Quản lý secrets và kết nối production

Database URL, username, password, certificate, private key và token không được commit vào changelog hoặc repository.

Nên:

- Lấy secret từ secret manager hoặc protected CI variables.
- Phân quyền đọc secret theo environment và job identity.
- Dùng secret riêng cho từng môi trường.
- Xoay vòng credential theo chính sách.
- Tránh in connection properties nhạy cảm trong log.
- Tránh truyền password dưới dạng command-line argument dễ lộ qua process list/history.
- Không đưa secret vào artifact hoặc test report.
- Dùng TLS và xác minh chứng thư khi kết nối qua mạng.

Ví dụ cấu hình minh họa:

~~~properties
url=DB_MIGRATION_URL
username=DB_MIGRATION_USER
password=DB_MIGRATION_PASSWORD
changelogFile=db/changelog/db.changelog-master.yaml
~~~

Các giá trị trên là tên placeholder, không phải credential. Cách inject phải theo secret manager và runtime pipeline. Không tạo file properties chứa mật khẩu thật rồi commit vào repository.

### 16.1. Tách secret theo môi trường

Credential staging không nên có quyền truy cập production. Credential production không được cấp cho pull request từ fork hoặc job chạy mã chưa tin cậy.

Test PR chỉ nên dùng database ephemeral với credential dùng một lần. Production secret chỉ được cung cấp sau khi job vào protected environment và đạt approval.

## 17. Kiểm soát context, labels và tham số runtime

Context/labels có thể thay đổi tập changeset Liquibase chọn. Filter sai có thể bỏ qua migration bắt buộc hoặc kích hoạt changeset chỉ dành cho môi trường khác.

Cần kiểm soát:

- Ai được sửa context/label trong changelog.
- Ai được thay đổi filter của production job.
- Filter nào được phép theo môi trường.
- Giá trị mặc định và hành vi khi tham số thiếu.
- Changeset không có label/context có được chọn hay không.
- Kết quả status và update-sql với cấu hình production.
- Log filter đã dùng trong mỗi deployment.

Không cho người vận hành tùy ý nhập context để bỏ qua changeset hoặc kích hoạt migration thử nghiệm. Dùng allowlist và cấu hình được review.

## 18. Hạn chế lệnh Liquibase nguy hiểm trong production

Một số lệnh cần kiểm soát đặc biệt:

| Lệnh/nhóm thao tác | Rủi ro |
|---|---|
| update | Thực thi changeset pending |
| rollback / rollback-count | Có thể xóa hoặc đảo dữ liệu/schema |
| changelog-sync | Ghi nhận changeset như đã xử lý mà không chạy changes |
| mark-next-changeset-ran | Thay đổi history theo cơ chế đánh dấu |
| clear-checksums | Thay đổi metadata checksum |
| drop-all | Xóa object trong phạm vi database/schema |
| tag | Gắn mốc lịch sử, ảnh hưởng quy trình rollback |
| diff-changelog | Sinh artifact thay đổi cần review kỹ |

Không nhất thiết cấm mọi lệnh khỏi production; một số thao tác có thể cần trong quy trình được kiểm soát. Nhưng không cho developer hoặc job PR tùy ý gọi lệnh phá hủy hay thay đổi history trên production.

### 18.1. Không tự động sửa DATABASECHANGELOG

Sửa/xóa hàng trong DATABASECHANGELOG có thể làm Liquibase hiểu sai trạng thái đã triển khai. Không dùng SQL thủ công để làm pipeline xanh hoặc bỏ qua checksum mismatch.

Nếu cần phục hồi metadata, phải có incident record, người phê duyệt, kế hoạch đối chiếu schema thật và kiểm tra trên bản sao trước.

## 19. Bảo vệ DATABASECHANGELOG và DATABASECHANGELOGLOCK

Hai bảng metadata có vai trò quan trọng:

- DATABASECHANGELOG lưu identity, checksum, thời điểm và trạng thái changeset.
- DATABASECHANGELOGLOCK điều phối tiến trình Liquibase trên cùng metadata database.

Cần bảo vệ bằng quyền DBMS:

- Application runtime không cần quyền sửa history nếu không có yêu cầu rõ ràng.
- Developer không dùng tài khoản production để cập nhật metadata thủ công.
- Chỉ migration identity được ghi metadata trong quy trình bình thường.
- Audit việc thay đổi bảng metadata.
- Backup và retention phù hợp.
- Không giải phóng lock thủ công khi chưa xác minh tiến trình.

### 19.1. Lock không phải approval gate

DATABASECHANGELOGLOCK chỉ điều phối tiến trình Liquibase. Nó không xác minh người chạy có production approval hay không, không kiểm tra nội dung changeset đã được review và không ngăn DBA chạy DDL ngoài Liquibase.

Approval phải được thực thi ở CI/CD và quyền database phải được giới hạn độc lập.

## 20. Audit trail và khả năng truy vết

Một deployment production cần trả lời:

- Ai tạo thay đổi?
- Ai review SQL và schema?
- Ai phê duyệt production?
- Artifact nào đã được triển khai?
- Changelog root và changeset nào được chạy?
- Database nào bị tác động?
- Khi nào job bắt đầu/kết thúc?
- Kết quả và lỗi là gì?
- Có thao tác thủ công hoặc ngoại lệ nào không?

Nguồn bằng chứng:

| Nguồn | Thông tin |
|---|---|
| Git/SCM audit | Commit, pull request, author, reviewer, merge |
| CI/CD audit | Build, artifact digest, environment approval, job log |
| Secret manager audit | Danh tính truy cập secret và thời điểm |
| Liquibase log | Changeset được xét/thực thi và kết quả |
| DATABASECHANGELOG | Lịch sử changeset trong database |
| DBMS audit | DDL/DML hoặc thay đổi quyền theo khả năng DBMS |
| Incident/change record | Ngoại lệ, phê duyệt khẩn cấp và phục hồi |

Không phụ thuộc một nguồn duy nhất. DATABASECHANGELOG không phải nhật ký kiểm toán bất biến cho mọi thao tác; rollback có thể làm thay đổi các dòng history. Lưu log triển khai ở hệ thống độc lập với quyền chỉnh sửa hạn chế.

### 20.1. Đồng bộ thời gian và định danh

Để đối chiếu các hệ thống:

- Đồng bộ thời gian theo chuẩn tổ chức.
- Ghi pipeline run ID và artifact digest.
- Ghi database/environment identifier.
- Gắn deployment record với commit/tag.
- Tránh tài khoản chia sẻ không truy được cá nhân.
- Bảo vệ log khỏi sửa/xóa ngoài quyền.

## 21. Bảo vệ pipeline khỏi thay đổi trái phép

Pipeline chạy migration là một phần của trust boundary. Cần kiểm soát:

- Ai được sửa workflow và deployment script.
- Ai được tạo hoặc sửa environment secrets.
- Ai được thay runner/image/tool version.
- Ai được chọn branch, tag hoặc artifact.
- Ai được retry hoặc rerun production job.
- Ai được bypass approval.
- Job có thể truy cập mạng và database nào.
- Artifact được lấy từ registry nào.

### 21.1. Không chạy mã pull request không tin cậy với production secret

Pull request từ fork hoặc branch chưa được review có thể chứa script độc hại trong build. Không cung cấp production secret cho job chạy mã đó.

Test PR chỉ dùng credential và database test có phạm vi hạn chế. Deployment job production chạy sau merge, lấy artifact đã phát hành và vào protected environment theo policy.

### 21.2. Pin dependency và công cụ

Phiên bản Liquibase, JDBC driver, plugin và image chạy pipeline có thể ảnh hưởng SQL được sinh hoặc thực thi. Nên:

- Khóa phiên bản trong build.
- Quản lý nâng cấp dependency qua pull request.
- Kiểm tra nguồn và tính toàn vẹn artifact.
- Không tải script từ URL tùy ý trong job production.
- Ghi tool version trong deployment record.

## 22. Kiểm tra trước production bằng bằng chứng cụ thể

Trước approval, pipeline nên cung cấp:

1. Artifact digest và commit.
2. Liquibase version, DBMS/version, driver.
3. Target database/environment đã xác minh.
4. validate result.
5. status và danh sách changeset pending.
6. update-sql preview.
7. Review DDL/DML phá hủy hoặc SQL tùy chỉnh.
8. Integration test trên DBMS mục tiêu.
9. Data assertions và rollback/forward recovery plan.
10. Thời gian dự kiến, lock/risk và cửa sổ triển khai.

Reviewer cần nhìn đúng nội dung sẽ chạy. Nếu cấu hình runtime thay đổi sau preview, cần tạo lại bằng chứng tương ứng.

### 22.1. Preview không bảo đảm tuyệt đối

update-sql giúp xem SQL dự kiến, nhưng thực thi còn phụ thuộc trạng thái database, quyền, dữ liệu, DBMS và concurrency tại thời điểm chạy. Approval cần dựa trên test và hiểu biết rủi ro, không chỉ file SQL preview.

## 23. Quy trình triển khai production tham khảo

~~~text
1. Merge pull request vào protected release branch.
2. Build artifact từ commit đã merge.
3. Tính và lưu artifact digest.
4. Chạy integration/upgrade tests trên DBMS đại diện.
5. Sinh status và update-sql với cấu hình mục tiêu.
6. Review kết quả và rollback/forward plan.
7. Tạo deployment request cho đúng production environment.
8. Required approver xác nhận artifact, target và cửa sổ.
9. Protected deployment job lấy secret qua identity được cấp quyền.
10. Chạy Liquibase với root changelog đã khóa.
11. Xác minh schema, DATABASECHANGELOG và ứng dụng.
12. Lưu audit evidence và kết quả deployment.
~~~

Không cho phép thay artifact hoặc root changelog sau approval mà không chạy lại gate. Nếu deployment bị retry, kiểm tra trạng thái database trước khi thực thi lại.

## 24. Xác minh sau production deployment

Sau khi job hoàn tất, kiểm tra:

- Changeset dự kiến đã được ghi nhận.
- Không có changeset ngoài phạm vi.
- Schema thực tế đạt contract.
- Data migration assertions đạt.
- Ứng dụng đọc/ghi được.
- Không có lỗi lock hoặc migration dang dở.
- Không có dấu hiệu partial DDL.
- Deployment log được lưu.

Ví dụ truy vấn history:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    DATEEXECUTED,
    EXECTYPE,
    MD5SUM,
    DEPLOYMENT_ID
FROM DATABASECHANGELOG
ORDER BY DATEEXECUTED, ORDEREXECUTED;
~~~

Điều chỉnh schema và tên bảng metadata theo cấu hình. Không chỉ kiểm tra history; cần xác minh catalog và hành vi ứng dụng.

## 25. Quy trình khẩn cấp và break-glass access

Có thể xảy ra sự cố production cần sửa database ngoài lịch triển khai thông thường. Cần một quy trình **break-glass** có kiểm soát để phản ứng kịp thời.

Quy trình nên quy định:

- Điều kiện kích hoạt và mức độ sự cố.
- Người được phép yêu cầu và người phê duyệt.
- Tài khoản tạm thời, quyền tối thiểu và thời hạn.
- Phạm vi database/schema/object được tác động.
- Snapshot/backup hoặc phương án khôi phục phù hợp.
- Ghi log câu lệnh và phiên làm việc.
- Thông báo cho owner/on-call.
- Thu hồi credential sau thao tác.
- Tạo changeset/audit record để phản ánh trạng thái sau sự cố.
- Review hậu kiểm và cập nhật quy trình.

### 25.1. Không để thay đổi khẩn cấp thành drift lâu dài

Nếu DBA phải sửa trực tiếp production, cần ghi nhận DDL/DML và đưa trạng thái đó vào changelog theo quy trình được review. Trước khi thêm changeset, xác minh schema/history để tránh chạy lại thao tác đã thực hiện.

Không chạy changelog-sync chỉ để che thay đổi thủ công nếu chưa đối chiếu trạng thái và phạm vi. Việc tiếp nhận thay đổi cần quyết định rõ: baseline correction, forward migration hoặc reconciliation.

## 26. Xử lý khi phát hiện changelog độc hại hoặc sai quyền

Nếu phát hiện changeset trái phép hoặc có dấu hiệu bị chèn:

1. Dừng pipeline liên quan và khóa khả năng triển khai theo incident procedure.
2. Giữ lại commit, PR, artifact, job log và audit evidence.
3. Xác định artifact đã được build hoặc triển khai ở môi trường nào.
4. Kiểm tra database history và schema/data thật.
5. Xác định credential hoặc service identity có thể đã bị lộ.
6. Thu hồi/rotate credential nếu cần.
7. Phân loại tác động DDL/DML và dữ liệu.
8. Lập kế hoạch containment, restore hoặc forward fix.
9. Khôi phục branch protection/approval policy.
10. Review quyền repository, CI/CD và database.
11. Ghi nhận incident và kiểm tra các môi trường khác.

Không xóa commit hoặc log để “làm sạch” lịch sử. Giữ bằng chứng phục vụ điều tra và nghĩa vụ kiểm toán.

## 27. Các anti-pattern bảo mật cần tránh

| Anti-pattern | Rủi ro | Kiểm soát thay thế |
|---|---|---|
| Mọi developer đều có admin repository | Có thể bypass review | Giới hạn admin và quyền write |
| Push trực tiếp vào main | Bỏ qua PR checks | Protected branch |
| Người viết tự approve | Thiếu kiểm tra độc lập | Required reviewer khác author |
| Chỉ bảo vệ root changelog | SQL include có thể bị sửa | Bảo vệ toàn bộ dependency graph |
| Chạy latest từ branch thay đổi | Artifact có thể đổi sau review | Build và promote artifact bất biến |
| Pipeline cho nhập URL tùy ý | Có thể nhắm nhầm database | Allowlist target và protected config |
| Dùng runtime DB user cho Liquibase | Ứng dụng có quyền DDL | Migration identity riêng |
| Dùng DBA credential trong CI PR | Mã không tin cậy truy cập production | Secret chỉ cấp cho protected deployment |
| Lưu password trong properties | Lộ credential qua Git/log | Secret manager |
| Tự động clear-checksums | Che sửa lịch sử | Điều tra checksum và changeset mới |
| Sửa DATABASECHANGELOG bằng tay | History mất tin cậy | Reconciliation có phê duyệt |
| Approval chung cho mọi môi trường | Không kiểm soát target | Environment-specific approval |
| Bypass gate không audit | Không truy trách nhiệm | Break-glass có thời hạn và log |
| Chỉ xem update-sql rồi deploy | Không kiểm tra dữ liệu/runtime | Integration test và assertions |

## 28. Ma trận kiểm soát theo giai đoạn

| Giai đoạn | Kiểm soát | Owner |
|---|---|---|
| Authoring | Quyền branch riêng, changeset file riêng, không chứa secret | Developer |
| Pull request | Review code owner, static checks, validate | Maintainer/database owner |
| SQL review | Đánh giá DDL/DML, data loss, rollback và dependency | DB/domain owner |
| Merge | Protected branch, approval độc lập, required checks | Repository maintainer |
| Build | Artifact digest, tool version, source provenance | CI identity |
| Pre-production | Integration/upgrade test, SQL preview, target validation | Release engineering |
| Production approval | Reviewer được ủy quyền, artifact/target cụ thể | Release approver |
| Deployment | Protected secret, least-privilege migration identity | Deployment platform |
| Verification | Schema/history/data assertions, audit record | Database operator |
| Exception | Break-glass, expiry, hậu kiểm và thu hồi | Incident commander/database owner |

## 29. Ví dụ CODEOWNERS và policy review

~~~text
/db/changelog/                  @database-platform
/db/changelog/releases/orders/  @orders-db-owners
/db/changelog/releases/billing/ @billing-db-owners
/db/changelog/sql/              @database-platform @db-security
/.github/workflows/             @platform-engineering
/deploy/production/             @release-engineering @security-team
~~~

Policy đi kèm:

- Mọi thay đổi dưới db/changelog cần approval của owner tương ứng.
- Thay đổi DROP/DELETE diện rộng cần thêm domain owner.
- Thay đổi quyền hoặc pipeline cần security/platform review.
- Changeset đã phát hành không được sửa nếu chưa có ngoại lệ được ghi nhận.
- Commit mới sau approval phải được review lại theo branch policy.
- Merge chỉ diễn ra khi required CI checks pass.

CODEOWNERS chỉ định người review; cần bật branch protection để approval thực sự là điều kiện merge.

## 30. Ví dụ production approval

~~~text
Release:
  service: DATABASE_SCHEMA_MIGRATION_LIQUIBASE
  version: 2.6.0
  commit: COMMIT_SHA
  artifact-digest: SHA256_DIGEST

Target:
  environment: production
  database: orders
  schema: app

Migration:
  pending changesets: 2
  destructive changes: none
  custom SQL: reviewed
  update-sql: attached
  upgrade test: passed
  rollback/forward plan: attached

Approvals:
  database owner: approved
  release approver: approved

Execution:
  identity: production-liquibase-deployer
  job: PIPELINE_RUN_ID
~~~

Các giá trị là placeholder. Approval record cần tham chiếu artifact digest, environment và bằng chứng tương ứng. Không phê duyệt yêu cầu chỉ có tên release mà không biết nội dung artifact nào sẽ chạy.

## 31. Checklist bảo mật trước khi cho phép migration production

- [ ] Changelog và SQL nằm trong repository được bảo vệ.
- [ ] Root changelog, include files và sqlFile dependencies đều có owner review.
- [ ] Branch protection ngăn push trực tiếp và hạn chế bypass.
- [ ] Người tạo thay đổi không tự thỏa điều kiện approval độc lập.
- [ ] Reviewer phù hợp với domain và mức rủi ro.
- [ ] CI kiểm tra cấu trúc, identity, checksum, include và conflict marker.
- [ ] Liquibase validate và integration tests đã pass.
- [ ] SQL preview, precondition, rollback và data impact đã được review.
- [ ] Changeset đã triển khai được giữ bất biến theo policy.
- [ ] Artifact được build từ commit đã merge và có digest/provenance.
- [ ] Approval production gắn với đúng artifact và target.
- [ ] Approval bị vô hiệu khi artifact hoặc nội dung thay đổi.
- [ ] Production environment được bảo vệ bằng required reviewer.
- [ ] Production secret chỉ cấp cho deployment job được ủy quyền.
- [ ] Migration identity tách khỏi application runtime user.
- [ ] Quyền DBMS chỉ đủ cho changeset cần chạy.
- [ ] Connection/TLS và secret handling đáp ứng chính sách.
- [ ] Context/labels và root changelog không thể bị thay đổi tùy tiện lúc deploy.
- [ ] Các lệnh nguy hiểm như drop-all, clear-checksums, changelog-sync và rollback được kiểm soát riêng.
- [ ] DATABASECHANGELOG và DATABASECHANGELOGLOCK được bảo vệ bằng quyền DBMS.
- [ ] Audit trail ghi người viết, reviewer, approver, artifact, target và kết quả.
- [ ] Có break-glass procedure, expiry và hậu kiểm.
- [ ] Có xác minh schema/data/history sau triển khai.
- [ ] Không dùng production secret trong job chạy mã PR không tin cậy.
- [ ] Quyền repository, CI/CD, secret manager và DBMS được rà soát định kỳ.

## 32. Câu hỏi tự kiểm tra

**1. Vì sao quyền sửa changelog được xem là quyền nhạy cảm?**

Vì changeset có thể thực thi DDL/DML và SQL tùy chỉnh trên database, gây mất dữ liệu hoặc thay đổi quyền nếu được triển khai.

**2. CODEOWNERS có tự ngăn merge khi owner chưa review không?**

Không. Cần bật branch protection hoặc quy tắc review bắt buộc tương ứng.

**3. PR approval và production approval khác nhau thế nào?**

PR approval cho phép merge nội dung đã review; production approval cho phép triển khai artifact cụ thể tới môi trường cụ thể.

**4. Vì sao cần separation of duties?**

Để một người không thể tự tạo, tự phê duyệt và tự triển khai thay đổi rủi ro cao mà không có kiểm tra độc lập.

**5. Checksum Liquibase có phải chữ ký bảo mật không?**

Không. Checksum hỗ trợ phát hiện nội dung changeset khác với nội dung đã ghi nhận; nó không xác thực tác giả hoặc bảo vệ artifact khỏi người có quyền sửa.

**6. Vì sao phải bảo vệ cả SQL file được include?**

Vì root changelog có thể tham chiếu file SQL bên ngoài; nội dung thực thi nằm trong dependency đó.

**7. Vì sao migration user cần tách khỏi application user?**

Để ứng dụng runtime không giữ quyền DDL rộng, giảm tác động nếu ứng dụng bị xâm phạm.

**8. Có nên cho pipeline PR truy cập production secret không?**

Không. Job chạy mã chưa tin cậy chỉ nên dùng credential test giới hạn.

**9. DATABASECHANGELOGLOCK có kiểm tra approval không?**

Không. Nó điều phối tiến trình Liquibase, không xác minh người chạy hoặc quyết định phê duyệt.

**10. Khi nào cần break-glass?**

Khi sự cố đáp ứng điều kiện khẩn cấp đã định nghĩa và thao tác không thể chờ quy trình bình thường; cần quyền tạm thời, audit và hậu kiểm.

**11. Vì sao approval cần gắn với artifact digest?**

Để bảo đảm đúng nội dung đã kiểm tra được triển khai; artifact thay đổi phải được kiểm tra/phê duyệt lại.

**12. Sau production update cần xác minh những gì?**

Schema thực tế, dữ liệu, DATABASECHANGELOG, ứng dụng, log và mọi dấu hiệu partial state.

**Kết luận:** Bảo vệ Liquibase trong production cần một chuỗi kiểm soát liên tục từ repository tới database. Hãy giới hạn quyền sửa changelog, bảo vệ root/include/SQL bằng code owner và branch policy, yêu cầu review độc lập, giữ changeset đã triển khai bất biến, build artifact có thể truy vết và gắn approval với đúng artifact cùng môi trường. Pipeline sử dụng secret được bảo vệ và migration identity có quyền tối thiểu; DBMS metadata và audit log được bảo vệ riêng. Khi quyền sửa, quyền duyệt và quyền thực thi được phân định, mọi ngoại lệ có dấu vết và kết quả sau triển khai được xác minh, nhóm có thể quản lý thay đổi schema có trách nhiệm mà vẫn đáp ứng yêu cầu vận hành production.

