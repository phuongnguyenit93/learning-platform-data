# Xác định lược đồ chuẩn và mốc baseline

Trong chương **Tiếp nhận CSDL** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, đưa một database cũ vào quản lý bằng Liquibase bắt đầu bằng hai quyết định nền tảng: **lược đồ nào được xem là chuẩn** và **lịch sử Liquibase bắt đầu từ mốc nào**. Đây là bước tiếp nhận (legacy database adoption), thường phức tạp hơn việc chạy changelog trên database mới vì database đã có bảng, khóa, index, view, dữ liệu và có thể cả những thay đổi thủ công chưa được ghi lại.

Mục tiêu của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE** là quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Khi tiếp nhận hệ thống cũ, những nguyên tắc đó phải được áp dụng ngay từ đầu: biết chính xác trạng thái hiện tại, xác định trạng thái mong muốn, phân biệt lịch sử đã xảy ra với lịch sử sẽ được Liquibase quản lý, và không để một lệnh baseline che giấu schema drift.

**Baseline không tạo ra lược đồ chuẩn.** Nó ghi nhận rằng một database đã ở một mốc thay đổi nhất định. Lược đồ chuẩn phải được xác định và xác minh trước; sau đó mới chọn cách để Liquibase tiếp tục quản lý database hiện hữu mà không chạy lại những thay đổi đã có.

## 1. Ba khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Câu hỏi cần trả lời |
|---|---|---|
| Lược đồ chuẩn (canonical schema) | Mô hình schema được tổ chức chấp nhận làm chuẩn cho một phiên bản ứng dụng | Bảng, cột, khóa, index, view và các đối tượng cần có là gì? |
| Trạng thái thực tế (observed schema) | Các đối tượng thực sự đang tồn tại trong một database cụ thể | Database này hiện có gì, khác chuẩn ở đâu? |
| Mốc baseline (baseline point) | Mốc lịch sử mà từ đó Liquibase bắt đầu ghi nhận và quản lý các changeset | Những thay đổi nào đã xảy ra trước khi Liquibase tiếp quản? |

Ba khái niệm này không đồng nghĩa:

- Database production có thể đang chạy ổn định nhưng chứa đối tượng thừa, tên cũ hoặc thay đổi thủ công. Nó không tự động trở thành canonical schema.
- Một canonical schema có thể được định nghĩa trong changelog và tài liệu thiết kế, trong khi từng database còn cần được đối chiếu.
- Baseline có thể ghi nhận một tập changeset là đã được xử lý mà không thực thi DDL/DML. Nó không tự sửa database để làm database khớp chuẩn.

Có thể ghi nhớ bằng ba câu hỏi:

- **Canonical schema:** Hệ thống cần có cấu trúc nào?
- **Schema thực tế:** Database đang có cấu trúc nào?
- **Baseline:** Liquibase bắt đầu quản lý lịch sử từ điểm nào?

Nếu nhầm lẫn ba câu hỏi này, việc tiếp nhận có thể đánh dấu một database chưa đúng là đã hoàn tất, hoặc chạy lại DDL trên một hệ thống đang chứa dữ liệu thật.

## 2. Vì sao cần xác định lược đồ chuẩn trước baseline?

Một hệ thống cũ có thể có nhiều nguồn mô tả schema:

- DDL được lưu trong repository từ nhiều năm trước.
- Tài liệu thiết kế đã lỗi thời.
- Database development do nhóm kỹ thuật thường xuyên sửa.
- Database staging được dựng lại từ bản backup cũ.
- Database production đã nhận các bản vá thủ công của DBA.
- Migration từ công cụ cũ như Flyway, công cụ nội bộ hoặc script SQL.
- Entity JPA/Hibernate và mapping trong ứng dụng.
- Stored procedure, view, trigger và job vận hành được quản lý ngoài repository.

Những nguồn này có thể mâu thuẫn. Ví dụ repository nói cột customer.email là VARCHAR(255), production là VARCHAR(320), còn staging là VARCHAR(255). Nếu chỉ lấy DDL production làm chuẩn mà không hiểu lý do khác biệt, nhóm có thể hợp thức hóa một thay đổi ngoài kế hoạch. Nếu lấy file DDL cũ làm chuẩn, baseline có thể mô tả cấu trúc mà production chưa từng có.

Cần chọn canonical schema dựa trên **quyết định kỹ thuật có thể kiểm chứng**, thường gồm:

1. Phiên bản ứng dụng và yêu cầu nghiệp vụ đang được hỗ trợ.
2. Cấu trúc database đã được xác nhận hoạt động trên môi trường mục tiêu.
3. Các migration lịch sử có thể truy xuất và bằng chứng triển khai.
4. Phụ thuộc của ứng dụng, báo cáo, ETL, CDC và dịch vụ khác.
5. Các khác biệt có chủ đích theo DBMS, môi trường hoặc tenant.
6. Các đối tượng cần giữ, cần loại bỏ hoặc cần chuyển đổi trong giai đoạn sau.

Không lấy “database mới nhất” hoặc “database có nhiều bảng nhất” làm tiêu chí duy nhất. Canonical schema là một **phiên bản được phê duyệt**, không phải một bản chụp ngẫu nhiên.

## 3. Xác định phạm vi schema sẽ được quản lý

Trước khi so sánh, phải xác định phạm vi rõ ràng:

- Database/catalog nào?
- Schema ứng dụng nào?
- Những bảng nào thuộc module?
- Có dùng schema dùng chung với ứng dụng khác không?
- Có bảng do extension hoặc công cụ bên ngoài tạo không?
- Những đối tượng nào Liquibase sẽ quản lý?
- Dữ liệu tham chiếu có nằm trong phạm vi không?
- Quyền, owner, sequence, trigger, function, partition và synonym có được quản lý không?

Ví dụ:

~~~text
Database: customer_service
Schema ứng dụng: app
Schema báo cáo: reporting
Schema giám sát: observability

Phạm vi Liquibase tiếp nhận:
- app: bảng, cột, PK/FK/UNIQUE/CHECK, index, view, sequence và dữ liệu tham chiếu được chọn
- reporting: chỉ một số view do ứng dụng sở hữu
- observability: không thuộc phạm vi migration của module
~~~

Đây là cấu trúc minh họa. Không tự ý quản lý toàn bộ database nếu nhiều hệ thống cùng chia sẻ database đó. Chỉ một nhóm có quyền sở hữu rõ ràng mới nên đưa một đối tượng vào changelog của mình.

Đặc biệt, không coi các bảng **DATABASECHANGELOG** và **DATABASECHANGELOGLOCK** là bảng nghiệp vụ cần đưa vào baseline ứng dụng. Đây là các bảng quản lý lịch sử/khóa của Liquibase; chúng có vòng đời và cấu hình riêng. Nếu database đã có lịch sử Liquibase, cần điều tra lịch sử đó trước khi tiếp nhận.

## 4. Kiểm kê database hiện hữu

Một inventory tốt phải đủ để người khác lặp lại việc kiểm tra và giải thích vì sao schema được chọn làm chuẩn.

Thông tin kết nối và nền tảng:

- DBMS, phiên bản server, edition và compatibility mode.
- Driver JDBC và phiên bản Liquibase/extension.
- Database, catalog, schema và search path/default schema.
- Collation, character set, timezone nếu có ảnh hưởng.
- Extension, module hoặc tính năng DBMS được bật.
- Tài khoản migration, quyền đọc metadata và quyền DDL.
- Cơ chế replication, partitioning, clustering hoặc multi-tenant.

Đối tượng schema:

| Nhóm | Nội dung cần ghi nhận |
|---|---|
| Bảng | Tên, schema, owner, partition, comment, storage options |
| Cột | Tên, kiểu, độ dài, precision/scale, NULL, default, identity |
| Khóa | PK, FK, UNIQUE, CHECK và thứ tự cột |
| Index | Tên, cột, thứ tự, predicate, biểu thức, unique, trạng thái hợp lệ |
| Sequence | Start, increment, cache, current value, owner/identity liên quan |
| View | Định nghĩa, dependency, materialized/refresh behavior |
| Routine | Function, procedure, trigger và mã nguồn |
| Quyền | Role, grant, default privileges, owner |
| Đối tượng khác | Synonym, type, domain, partition, extension và đối tượng đặc thù DBMS |

Không phải mọi công cụ snapshot/diff đều đọc được mọi đối tượng hoặc mọi thuộc tính của DBMS. Một số đối tượng cần extension, truy vấn metadata riêng hoặc kiểm tra thủ công. Hãy ghi rõ **phần nào được tự động hóa, phần nào chưa được công cụ bao phủ**.

Dữ liệu cũng cần inventory riêng:

- Số hàng theo bảng quan trọng.
- Giá trị NULL, trùng khóa hoặc tham chiếu mồ côi.
- Dữ liệu tham chiếu và mã nghiệp vụ.
- Sequence/identity có đang vượt qua ID hiện có không.
- Các bản ghi đặc biệt, dữ liệu lịch sử hoặc dữ liệu do người dùng quản lý.
- Các quy tắc dữ liệu không biểu diễn được đầy đủ bằng constraint.

Không cần xuất dữ liệu nhạy cảm ra file inventory. Chỉ lưu số liệu tổng hợp, metadata và bằng chứng đã được phép; không sao chép password, token hoặc dữ liệu cá nhân vào changelog.

## 5. Phân biệt canonical schema với schema của một môi trường

Một hệ thống thường có nhiều database:

| Môi trường | Vai trò | Đặc điểm có thể khác |
|---|---|---|
| Development | Phát triển tính năng | Có bảng thử nghiệm hoặc dữ liệu demo |
| Testing | Kiểm thử tự động | Có dữ liệu seed, schema được tạo mới thường xuyên |
| Staging | Diễn tập release | Cấu hình gần production nhưng dữ liệu khác |
| Production | Vận hành thực | Có dữ liệu thật, yêu cầu sẵn sàng cao, thay đổi được kiểm soát |

Schema chuẩn nên mô tả **cấu trúc logic cần được hỗ trợ**. Các khác biệt có chủ đích được quản lý riêng:

- DBMS khác nhau có thể cần changeset SQL riêng hoặc dbms filter.
- Schema name có thể khác theo môi trường và được truyền bằng changelog parameter.
- Extension hoặc tính năng chỉ tồn tại ở một môi trường cần được ghi rõ.
- Dữ liệu demo không được trộn vào baseline production.
- Role/permission có thể được quản lý bởi quy trình bảo mật riêng.

Không tạo một baseline riêng chỉ vì tên môi trường khác nhau nếu cấu trúc logic giống nhau. Ngược lại, không ép các database có khác biệt kỹ thuật thật sự vào một mô hình chung mà không ghi nhận ngoại lệ.

Nếu staging có một index thử nghiệm không có trong production, cần quyết định index đó là:
1. Một phần canonical schema cần đưa vào chuẩn.
2. Một đối tượng thử nghiệm cần loại bỏ.
3. Một khác biệt có chủ đích, cần quản lý riêng.

Chỉ sau khi có quyết định này mới biết baseline nên mô tả đối tượng nào.

## 6. Dùng snapshot, diff và generate-changelog đúng mục đích

Liquibase có các lệnh hỗ trợ khảo sát schema. Cú pháp và option chi tiết có thể thay đổi theo phiên bản, nhưng các khái niệm thường gặp gồm:

| Lệnh | Mục đích | Không nên hiểu nhầm |
|---|---|---|
| snapshot | Chụp mô hình metadata của database | Không phải bản backup dữ liệu |
| diff | So sánh reference database và target database | Không tự quyết định khác biệt nào là đúng |
| diff-changelog | Tạo changelog mô tả khác biệt theo hướng reference/target | Không thể review máy móc rồi chạy ngay |
| generate-changelog | Sinh changelog từ schema hiện có | Không khôi phục được đầy đủ lịch sử migration đã xảy ra |

Ví dụ khảo sát bằng CLI, giả sử URL và thông tin đăng nhập đã được cấu hình an toàn:

~~~bash
liquibase --url="$REFERENCE_URL" --username="$REFERENCE_USER" snapshot
~~~

Cú pháp thực tế của snapshot có thể cần output format hoặc cấu hình tương ứng. Mục đích là thu thập metadata của database tham chiếu.

So sánh một database chuẩn với database đang tiếp nhận:

~~~bash
liquibase   --url="$TARGET_URL"   --username="$TARGET_USER"   --reference-url="$REFERENCE_URL"   --reference-username="$REFERENCE_USER"   diff
~~~

Trong mô hình lệnh này, cần xác nhận rõ database nào là **reference** và database nào là **target** theo cách Liquibase định nghĩa. Với diff-changelog, hướng sinh thay đổi có ý nghĩa rất quan trọng: changelog được tạo ra nhằm mô tả các thay đổi để đưa target về gần reference. Đọc kỹ output và kiểm tra hướng trước khi dùng.

Có thể sinh changelog từ một database hiện có:

~~~bash
liquibase   --url="$SOURCE_URL"   --username="$SOURCE_USER"   generate-changelog   --changelog-file=db/changelog/baseline/legacy-schema.yaml
~~~

Đây là điểm bắt đầu để kiểm kê, không phải canonical schema tự động. Changelog được sinh có thể chứa tên object do DBMS tạo, cấu trúc đặc thù, thứ tự hoặc metadata khó bảo trì. Cần review, chuẩn hóa có kiểm soát và đối chiếu với phạm vi module.

**Không chạy diff-changelog sinh ra trực tiếp lên production chỉ vì command kết thúc thành công.** Công cụ phát hiện khác biệt vật lý; người chịu trách nhiệm phải quyết định khác biệt nào là chủ ý, khác biệt nào là drift, và thay đổi nào có thể phá dữ liệu.

## 7. Xây dựng canonical schema từ bằng chứng

Một quy trình lựa chọn chuẩn có thể thực hiện như sau:

1. Chọn phiên bản ứng dụng đang được hỗ trợ và xác định các DBMS mục tiêu.
2. Thu thập snapshot/metadata từ các môi trường liên quan.
3. So sánh với DDL, changelog lịch sử và mapping của ứng dụng.
4. Phân loại từng khác biệt: chuẩn, drift ngoài kế hoạch, khác biệt môi trường có chủ ý, đối tượng thử nghiệm hoặc chưa rõ nguồn gốc.
5. Kiểm tra ảnh hưởng tới ứng dụng, báo cáo, job, CDC và tích hợp ngoài.
6. Chốt mô hình schema mong muốn cùng người sở hữu database.
7. Tạo changelog mô tả mô hình đó theo các changeset có thứ tự.
8. Kiểm thử tạo mới database từ changelog trên đúng DBMS/version.
9. So sánh database vừa tạo với canonical model đã phê duyệt.
10. Chỉ sau khi đạt tiêu chí mới sử dụng changelog làm cơ sở baseline cho database legacy.

Kết quả cần có một **phiên bản canonical rõ ràng**, ví dụ legacy-schema-v1, gắn với commit hoặc artifact cụ thể. Không chỉ lưu một file DDL rời rạc mà không biết nó được phê duyệt khi nào và dành cho phiên bản ứng dụng nào.

Nếu có nhiều DBMS, canonical schema có thể là mô hình logic chung cùng các nhánh triển khai vật lý riêng. Không giả định cùng một loại column/index/sequence có semantics hoàn toàn giống nhau trên PostgreSQL, MySQL, SQL Server hoặc Oracle.

## 8. Chọn một database làm reference có trách nhiệm

Trong thực tế, production thường là nguồn bằng chứng quan trọng nhưng không phải lúc nào cũng là nguồn chuẩn duy nhất.

Trước khi chọn một database làm reference, hãy hỏi:

- Có migration thủ công nào chưa được ghi nhận không?
- Có đối tượng thừa do hotfix hoặc công cụ bên ngoài tạo không?
- Có cấu trúc cũ còn tồn tại nhưng ứng dụng không sử dụng không?
- Database đó có đúng phiên bản ứng dụng đang được hỗ trợ không?
- Có khác biệt do tenant hoặc extension không?
- Có thể tái tạo cấu trúc đó trên database mới không?
- Có dữ liệu và ràng buộc nào cần giữ nhưng chưa được mô tả trong changelog không?

Một production database có thể hoạt động tốt nhưng có một index thủ công giúp truy vấn quan trọng không bị chậm. Nếu bỏ index ấy khỏi canonical schema, lần dựng mới hoặc môi trường khác có thể có hiệu năng kém. Ngược lại, production có thể chứa một index trùng lặp được tạo trong một đợt điều tra sự cố; không nhất thiết phải mang nó sang tất cả môi trường.

Do đó, reference database là **nguồn quan sát**, còn canonical schema là **kết quả quyết định sau review**. Hai thứ có thể trùng nhau nhưng không nên coi là đồng nghĩa.

## 9. Phân loại schema drift trước khi baseline

Schema drift là khác biệt giữa cấu trúc thực tế và mô hình/changelog được coi là chuẩn.

| Loại drift | Ví dụ | Cách xử lý |
|---|---|---|
| Thiếu đối tượng chuẩn | Production thiếu index trong changelog | Kiểm tra nguyên nhân, bổ sung bằng changeset mới hoặc sửa trạng thái trước baseline |
| Đối tượng thừa | Bảng debug hoặc index thử nghiệm | Xác nhận owner và dependency; giữ có chủ đích hoặc lập kế hoạch loại bỏ |
| Khác thuộc tính | VARCHAR(255) thay vì VARCHAR(320) | Đánh giá dữ liệu, ứng dụng và tính tương thích trước alter |
| Khác tên | FK cùng ý nghĩa nhưng tên khác | Chuẩn hóa hoặc chấp nhận ngoại lệ theo quy ước |
| Khác dữ liệu tham chiếu | Một môi trường thiếu code chuẩn | Seed/reconcile dữ liệu riêng, không chỉ baseline schema |
| Khác DBMS | Kiểu dữ liệu hoặc index đặc thù | Tách changeset theo dbms/nhánh hỗ trợ |
| Không rõ nguồn gốc | Trigger không có trong repository | Điều tra owner, tác động và lịch sử trước khi quyết định |

Không nên “sửa tất cả cho giống nhau” trong một lần baseline. Với database đang vận hành, một thay đổi nhỏ như drop index, đổi kiểu cột hoặc thêm NOT NULL cũng có thể gây lock, mất dữ liệu hoặc lỗi ứng dụng.

Mỗi drift cần được ghi nhận bằng:
- Đối tượng bị ảnh hưởng.
- Trạng thái thực tế ở từng môi trường.
- Trạng thái canonical.
- Nguồn gốc hoặc người chịu trách nhiệm.
- Tác động dữ liệu và ứng dụng.
- Quyết định giữ, sửa, bỏ hoặc theo dõi.
- Bằng chứng đã kiểm chứng.

Những khác biệt chưa giải thích được phải là **blocker cho baseline**, không được biến thành ngoại lệ âm thầm.

## 10. Thiết kế changelog baseline có thể dựng database mới

Một baseline tốt cần phục vụ hai trường hợp khác nhau:

- Database legacy đã có cấu trúc: Liquibase cần ghi nhận các changeset baseline như đã được xử lý, không chạy lại DDL.
- Database mới: Liquibase cần thực thi những changeset đó để tạo cấu trúc chuẩn từ đầu.

Ví dụ changelog gốc:

~~~yaml
databaseChangeLog:
  - include:
      file: baseline/001-create-reference-tables.yaml
      relativeToChangelogFile: true
  - include:
      file: baseline/002-create-core-tables.yaml
      relativeToChangelogFile: true
  - include:
      file: baseline/003-create-constraints-indexes.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/20261120-add-customer-status.yaml
      relativeToChangelogFile: true
~~~

Các tệp baseline chứa các changeset mô tả cấu trúc chuẩn tại một mốc đã thống nhất. Tệp changes mới chứa những thay đổi sau mốc đó.

Ví dụ changeset tạo bảng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "baseline-v1-001-create-customer"
      author: "db-adoption"
      comment: "Baseline schema v1: bảng customer"
      changes:
        - createTable:
            schemaName: app
            tableName: customer
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    primaryKeyName: pk_customer
                    nullable: false
              - column:
                  name: email
                  type: VARCHAR(320)
                  constraints:
                    nullable: false
~~~

Các ID baseline phải có quy ước riêng, dễ nhận biết và ổn định. Không tái sử dụng ID đã có trong lịch sử Liquibase cũ. FILENAME của mỗi changeset cũng phải ổn định; nếu sau này đổi thư mục, hãy đánh giá logicalFilePath và lịch sử trước khi triển khai.

**Baseline không nên được viết chỉ từ một bản dump thiếu kiểm chứng.** Changelog cần tái tạo được schema chuẩn trên một database trống hoặc schema cô lập, rồi được so sánh lại với canonical model.

## 11. Baseline một database legacy mà không chạy lại DDL

Đây là điểm quan trọng nhất khi tiếp nhận database đã tồn tại.

Nếu database đã có đúng cấu trúc được mô tả bởi các changeset baseline, chạy update trực tiếp có thể khiến Liquibase cố thực thi CREATE TABLE hoặc các DDL khác. Điều này thường dẫn tới lỗi object already exists.

Liquibase cung cấp lệnh **changelog-sync** để đánh dấu các changeset chưa được ghi nhận trong changelog hiện tại là đã được xử lý trong lịch sử database, mà không chạy các change DDL/DML tương ứng.

Ví dụ:

~~~bash
liquibase   --changelog-file=db/changelog/baseline-only.yaml   changelog-sync
~~~

Trong ví dụ, baseline-only.yaml chỉ include những changeset thuộc mốc baseline đã được đối chiếu. Cấu hình kết nối phải trỏ đến đúng database legacy đang tiếp nhận.

Sau khi sync, Liquibase ghi nhận các changeset tương ứng trong DATABASECHANGELOG theo cơ chế của lệnh; các bản ghi thường có EXECTYPE thể hiện được đánh dấu thay vì DDL thực thi. Kiểm tra lịch sử thực tế theo phiên bản Liquibase đang dùng.

**changelog-sync không kiểm tra đầy đủ rằng schema thực tế giống changelog.** Nó có thể đánh dấu một changeset là đã xử lý ngay cả khi bảng/cột/constraint còn thiếu. Nếu dùng nó trước khi đối chiếu, bạn có thể biến một database sai thành database mà Liquibase tin rằng đã qua baseline.

Vì thế, chỉ thực hiện sync sau khi:
1. Chốt canonical schema.
2. So sánh schema legacy với canonical.
3. Giải quyết hoặc phê duyệt mọi drift.
4. Kiểm tra dữ liệu và các constraint cần có.
5. Xác nhận baseline-only changelog chỉ chứa các changeset lịch sử đến đúng mốc.
6. Có backup và phê duyệt thao tác ghi lịch sử.
7. Review SQL mà lệnh sync dự kiến tạo nếu phiên bản hỗ trợ changelog-sync-sql.

## 12. Tại sao cần changelog baseline riêng?

Một rủi ro lớn là chạy changelog-sync với changelog gốc đang chứa cả lịch sử và các changeset mới sau baseline.

Ví dụ:

~~~text
db.changelog-master.yaml
  ├── baseline-v1.yaml
  ├── change-20261120-add-customer-status.yaml
  └── change-20261122-add-payment-index.yaml
~~~

Nếu chạy changelog-sync trên toàn bộ master, Liquibase có thể đánh dấu **tất cả changeset chưa được ghi nhận trong phạm vi đang chọn** là đã xử lý, kể cả các thay đổi sau baseline chưa từng được thực thi trên database legacy.

Khi đó, các migration mới có thể bị bỏ qua ở những lần update sau.

Cách tổ chức an toàn là dùng một entry point baseline chỉ chứa các changeset thuộc mốc lịch sử cần ghi nhận:

~~~yaml
databaseChangeLog:
  - include:
      file: baseline/001-create-reference-tables.yaml
      relativeToChangelogFile: true
  - include:
      file: baseline/002-create-core-tables.yaml
      relativeToChangelogFile: true
  - include:
      file: baseline/003-create-constraints-indexes.yaml
      relativeToChangelogFile: true
~~~

Sau khi baseline sync thành công, master changelog dùng cho các lần triển khai tương lai có thể include cùng các tệp baseline đó và nối tiếp các changeset mới:

~~~yaml
databaseChangeLog:
  - include:
      file: baseline/001-create-reference-tables.yaml
      relativeToChangelogFile: true
  - include:
      file: baseline/002-create-core-tables.yaml
      relativeToChangelogFile: true
  - include:
      file: baseline/003-create-constraints-indexes.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/20261120-add-customer-status.yaml
      relativeToChangelogFile: true
~~~

Điều kiện quan trọng: đường dẫn logic/filename của những changeset baseline phải tiếp tục được nhận diện đúng như khi sync. Không tạo một bản sao khác của cùng changeset với ID/author/file khác chỉ để có master mới.

Một cách khác là dùng lệnh sync giới hạn tới tag hoặc phạm vi mà phiên bản Liquibase hỗ trợ. Nếu dùng, phải kiểm chứng chính xác ranh giới changeset được đánh dấu. Với quy trình dễ kiểm toán, baseline-only changelog thường dễ giải thích hơn.

## 13. Baseline, changelog-sync và update khác nhau thế nào?

| Hành động | Chạy DDL/DML từ changeset? | Ghi lịch sử Liquibase? | Mục đích |
|---|---:|---:|---|
| update | Có, với changeset đủ điều kiện chưa chạy | Có | Thực thi thay đổi |
| changelog-sync | Không chạy change của các changeset được sync | Có | Ghi nhận các changeset đã có sẵn trên database |
| changelog-sync-sql | Chỉ sinh SQL dự kiến cho thao tác sync | Không tự áp dụng SQL | Review trước sync |
| generate-changelog | Không triển khai schema | Không tự đánh dấu lịch sử | Sinh mô tả từ database hiện có |
| diff | Không | Không | So sánh reference và target |
| diff-changelog | Tạo nội dung changelog | Không tự triển khai | Mô tả khác biệt cần xử lý |

Tên lệnh và tham số cụ thể phụ thuộc phiên bản Liquibase. Cần kiểm tra help/tài liệu của bản CLI/extension đang sử dụng trước khi đưa vào pipeline.

Một baseline cũng không nhất thiết là một lệnh duy nhất. Nó là **quy trình có phê duyệt** gồm kiểm kê, chọn chuẩn, tạo changelog, kiểm tra, sync lịch sử, tag mốc và xác nhận sau cùng.

## 14. Kiểm chứng trước khi sync: so sánh cả schema và dữ liệu

Trước baseline, cần có ma trận kiểm tra từng đối tượng quan trọng:

| Hạng mục | Kiểm tra | Tiêu chí chấp nhận |
|---|---|---|
| Bảng | Có đủ bảng chuẩn, không có bảng lạ chưa giải thích | Tên và phạm vi phù hợp |
| Cột | Kiểu, độ dài, precision, NULL/default | Khớp canonical hoặc có ngoại lệ phê duyệt |
| PK/FK/UNIQUE/CHECK | Định nghĩa và cột tham gia | Đúng quan hệ, đúng semantics |
| Index | Cột, thứ tự, predicate, trạng thái | Đủ workload và không tạo index ngoài kế hoạch |
| View/routine/trigger | Định nghĩa và dependency | Đúng logic ứng dụng và DBMS |
| Sequence/identity | Giá trị, increment, liên kết cột | Không tạo xung đột ID sau tiếp quản |
| Quyền | Owner, role, grants | Tài khoản runtime và migration có quyền phù hợp |
| Dữ liệu tham chiếu | Code bắt buộc, khóa duy nhất | Cùng nghĩa giữa các môi trường |
| Dữ liệu nghiệp vụ | NULL, trùng, mồ côi, ràng buộc | Không vi phạm điều kiện chuẩn |
| Lịch sử | Script cũ, Liquibase/Flyway history | Không mất dấu thay đổi đã xảy ra |

Schema diff không thể thay thế kiểm tra dữ liệu. Ví dụ bảng payment có đúng cột status_code và FK nhưng chứa mã status chưa có trong danh mục thì dữ liệu vẫn không hợp lệ. Ngược lại, dữ liệu hiện có có thể đúng dù chưa có FK vật lý; khi đó cần bổ sung constraint sau khi đánh giá tác động.

Đối với dữ liệu lớn, các truy vấn audit nên dùng kế hoạch và giới hạn tài nguyên phù hợp. Không chạy một phép COUNT/GROUP BY toàn bảng production trong giờ cao điểm nếu chưa đánh giá chi phí.

## 15. Baseline dữ liệu tham chiếu riêng với baseline schema

Schema baseline mô tả cấu trúc. Dữ liệu tham chiếu như mã quốc gia, trạng thái thanh toán hoặc loại đơn hàng có thể cần baseline riêng.

Ví dụ database legacy có bảng payment_status với code ổn định:

~~~text
PENDING
SUCCEEDED
FAILED
~~~

Nhưng một môi trường thiếu CANCELED hoặc có nhãn SUCCEEDED khác. Việc sync changeset tạo bảng payment_status không làm dữ liệu tự đồng bộ.

Cần phân biệt:

- **Schema changeset:** tạo bảng, cột, khóa, index.
- **Reference-data changeset:** thêm/sửa mã chuẩn theo code ổn định.
- **Transactional data:** đơn hàng, payment, khách hàng; thường không đưa vào baseline seed cố định.
- **Operational configuration:** giá trị runtime có thể cần nguồn quản lý khác.

Nếu dữ liệu tham chiếu được Liquibase quản lý, hãy kiểm tra từng code và ý nghĩa, không chỉ số lượng dòng. Dùng code ổn định thay vì ID tự tăng giữa môi trường. Không xóa code đã được giao dịch lịch sử tham chiếu.

## 16. Lịch sử cũ từ script thủ công hoặc công cụ khác

Database legacy có thể chưa từng dùng Liquibase. Nhưng cũng có thể đã được quản lý bởi:

- Flyway với schema history table.
- Công cụ migration nội bộ.
- Bộ script SQL đánh số theo release.
- DBA chạy thay đổi thủ công theo ticket.
- Hệ thống triển khai tự động khác.

Không xóa bảng lịch sử cũ hoặc chuyển toàn bộ lịch sử sang Liquibase bằng cách đoán ID/filename.

Quy trình tiếp nhận nên:

1. Lưu bản sao các script và history hiện có.
2. Xác định release/phiên bản schema từng được triển khai.
3. So sánh script với schema thực tế để tìm migration thiếu hoặc hotfix.
4. Xác định có cần giữ lịch sử công cụ cũ để audit không.
5. Chọn một mốc chuyển giao rõ ràng.
6. Tạo changelog baseline mô tả trạng thái chuẩn ở mốc đó.
7. Dùng changelog-sync trên phạm vi baseline đã xác minh.
8. Ghi lại nguồn gốc lịch sử trước baseline trong tài liệu vận hành hoặc artifact quản trị phù hợp.

Nếu tiếp tục dùng cả công cụ cũ và Liquibase để thay đổi cùng schema, cần có ranh giới ownership rõ ràng. Hai công cụ không tự đồng bộ lịch sử của nhau. Một schema chỉ nên có một quy trình migration chủ đạo tại một thời điểm, trừ khi có thiết kế phối hợp cụ thể.

## 17. Gắn tag và xác định mốc tiếp quản

Sau khi baseline được ghi nhận, nên có một dấu mốc dễ tra cứu, ví dụ:

~~~text
legacy-schema-v1
~~~

Tag giúp nhóm nói rõ database đã được tiếp quản ở phiên bản nào. Liquibase hỗ trợ lệnh **tag** và change type **tagDatabase** trong những quy trình phù hợp; cách sử dụng cụ thể phụ thuộc phiên bản và thứ tự triển khai.

Một chu trình minh họa:

~~~bash
liquibase   --changelog-file=db/changelog/baseline-only.yaml   changelog-sync

liquibase   --changelog-file=db/changelog/baseline-only.yaml   tag legacy-schema-v1
~~~

Trước khi chạy, phải xác nhận cú pháp tag theo phiên bản và tag sẽ gắn vào changeset/lịch sử nào. Nếu cần tạo tag bằng một changeset tagDatabase, phải hiểu nó là một thay đổi lịch sử riêng và không để nó làm thay đổi phạm vi baseline ngoài dự kiến.

Tag không phải checksum, không phải bản backup và không chứng minh schema thực tế không drift. Nó là **mốc lịch sử** để nhóm xác định điểm tiếp quản hoặc phạm vi rollback theo quy trình.

## 18. Kiểm thử baseline trên database trống

Một changelog baseline tốt phải tái tạo được canonical schema trên một database trống hoặc schema cô lập.

Quy trình:

1. Tạo database thử nghiệm đúng DBMS/version với production mục tiêu.
2. Dùng master changelog đầy đủ và chạy update từ trạng thái trống.
3. Kiểm tra bảng, cột, PK/FK/UNIQUE/CHECK, index, sequence, view và routine trong phạm vi.
4. Kiểm tra dữ liệu tham chiếu bắt buộc.
5. Chạy snapshot/diff so với canonical model hoặc database reference đã được phê duyệt.
6. Kiểm tra ứng dụng tương thích với schema vừa tạo.
7. Thử rollback các changeset mới theo thứ tự phụ thuộc trên database thử nghiệm có thể khôi phục.
8. Ghi nhận các đối tượng chưa được công cụ snapshot hỗ trợ và kiểm tra riêng.

Nếu baseline changelog chỉ hoạt động trên database legacy nhưng không thể dựng database mới, nó chưa phải một mô tả tái lập đầy đủ. Có thể còn thiếu sequence, default, extension, permission, trigger hoặc dữ liệu tham chiếu.

## 19. Kiểm thử baseline trên database legacy

Sau khi database trống dựng đúng chuẩn, thử tiếp trên bản sao có cấu trúc giống legacy:

1. Lấy bản backup/snapshot đã được phép sử dụng.
2. Đọc metadata và so sánh với canonical schema.
3. Xử lý các drift đã được phê duyệt.
4. Chạy changelog-sync-sql hoặc công cụ preview tương ứng nếu phiên bản hỗ trợ.
5. Review chính xác những changeset nào sẽ được đánh dấu.
6. Chạy changelog-sync trên database thử nghiệm.
7. Đọc DATABASECHANGELOG, xác nhận ID/AUTHOR/FILENAME và EXECTYPE.
8. Chạy status --verbose để xác nhận chỉ những changeset sau baseline còn pending.
9. Chạy update-sql cho các changeset tiếp theo và kiểm tra không có DDL baseline bị lặp.
10. Thực thi changeset tiếp theo trên bản sao, kiểm tra schema/dữ liệu.

Điều cần chứng minh là:
- Baseline sync **không chạy lại DDL/DML lịch sử**.
- Lịch sử ghi nhận đúng phạm vi baseline.
- Changeset mới vẫn pending và có thể chạy.
- Cấu trúc sau tiếp quản vẫn khớp canonical schema.
- Có bằng chứng cho từng ngoại lệ.

Không thử nghiệm bằng cách chạy changelog-sync trực tiếp lên production lần đầu. Hãy diễn tập trên bản sao có lịch sử và dữ liệu đại diện, sau đó dùng đúng artifact và kế hoạch đã được phê duyệt.

## 20. Nhiều database legacy không giống nhau

Một tổ chức có thể có nhiều khách hàng hoặc vùng triển khai, mỗi database được nâng cấp ở thời điểm khác nhau:

~~~text
legacy_A: schema v1 + index thủ công
legacy_B: schema v1 nhưng thiếu một FK
legacy_C: schema v2 đã có cột mới
~~~

Không chạy một lệnh baseline chung mà không phân loại.

Có thể lập ma trận:

| Database | So với canonical | Quyết định trước baseline |
|---|---|---|
| legacy_A | Thừa index chưa rõ nguồn gốc | Điều tra workload, giữ hoặc loại theo phê duyệt |
| legacy_B | Thiếu FK | Audit dữ liệu, thêm FK trước hoặc đưa vào migration chuẩn có kiểm soát |
| legacy_C | Đã có cột của release mới | Xác định lịch sử nguồn và tránh chạy lại thay đổi đó |
| legacy_D | Khác DBMS | Dùng nhánh changeset/SQL phù hợp và kiểm thử riêng |

Nếu database đã có một phần thay đổi sau mốc baseline, cần xác định chính xác những changeset nào đã được thực thi. Không đánh dấu toàn bộ changelog tới phiên bản mới nhất chỉ vì một số đối tượng đã tồn tại.

Các lựa chọn:
- Reconcile database về baseline đã chọn trước khi sync.
- Xác minh từng thay đổi đã tồn tại và dùng quy trình baseline theo mốc phù hợp.
- Tách nhánh theo DBMS/đối tượng đặc thù nhưng giữ logic canonical chung.
- Dừng tiếp nhận nếu không thể giải thích trạng thái hiện tại.

Không dùng nhiều changeset trùng định danh để “đoán” môi trường nào đã có đối tượng. Định danh phải nhất quán, còn khác biệt phải được biểu đạt bằng lịch sử, filter và migration có kiểm chứng.

## 21. Spring Boot và CI/CD sau khi tiếp nhận

Sau baseline, ứng dụng Spring Boot có thể cấu hình Liquibase như sau:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Mục tiêu là để Liquibase quản lý thay đổi, còn Hibernate validate mapping của ứng dụng ở mức phù hợp. Không để **ddl-auto: update** tự sửa schema production song song với Liquibase, vì hai nguồn quản lý có thể tạo drift và lịch sử không đồng nhất.

Với CI/CD, pipeline sau baseline cần:
- Dùng cùng master changelog và artifact đã kiểm thử.
- Xác nhận database đã được tiếp nhận và có history baseline.
- Chạy validate/status/update-sql.
- Xem những changeset nào còn pending.
- Không chạy lại changelog-sync trong mỗi deployment thông thường.
- Chạy update cho changeset mới theo quy trình phê duyệt.
- Kiểm tra DATABASECHANGELOG và schema thực tế sau triển khai.

Một ví dụ lệnh thông thường sau khi baseline đã xong:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
# Sau review và phê duyệt:
liquibase update
liquibase history
~~~

Changelog-sync là thao tác tiếp nhận/baseline, **không phải lệnh thay thế update cho mọi lần phát hành**. Đưa changelog-sync vào pipeline chạy mỗi release có thể đánh dấu nhầm các changeset mới là đã thực thi mà không thay đổi database.

Nếu Liquibase chạy trong Spring Boot startup, hãy bảo đảm database đã baseline trước khi bật bản ứng dụng có changelog mới. Nếu có nhiều instance, DATABASECHANGELOGLOCK điều phối các tiến trình Liquibase nhưng không thay thế thứ tự rollout giữa phiên bản ứng dụng cũ và mới.

## 22. Rollback và khôi phục trong giai đoạn tiếp nhận

Baseline thường không tạo thay đổi schema; changelog-sync chủ yếu ghi lịch sử. Vì vậy, không nên nghĩ rollback baseline giống rollback một changeset DDL.

Có hai phần cần phân biệt:

**Rollback cấu trúc:** nếu đã sửa schema để đưa legacy về canonical, phải có rollback/backup/forward fix cho những thay đổi đó. Thêm FK, đổi kiểu cột hoặc drop index có thể ảnh hưởng dữ liệu và hiệu năng.

**Rollback lịch sử:** nếu baseline sync ghi nhầm changeset là đã chạy, việc xóa hàng DATABASECHANGELOG hoặc sửa history có thể khiến Liquibase chạy lại DDL nguy hiểm. Không tự xóa các bản ghi này để “làm lại baseline”.

Trước baseline:
- Backup database và history hiện có.
- Lưu bản changelog/commit đã dùng.
- Xác nhận đúng database/schema và danh sách changeset sẽ sync.
- Review SQL sync nếu công cụ hỗ trợ.
- Có phê duyệt và phương án khôi phục.

Nếu phát hiện sync sai:
1. Dừng các deployment tiếp theo.
2. Đọc chính xác những dòng history vừa được ghi.
3. So sánh schema thực tế với canonical.
4. Xác định changeset nào đã được thực thi thật và changeset nào chỉ bị đánh dấu.
5. Lập kế hoạch reconcile lịch sử có kiểm soát cùng backup và người sở hữu DB.
6. Chỉ sau đó mới tiếp tục update.

Không sử dụng lệnh clear-checksums để đảo ngược baseline sync; clear-checksums xử lý checksum theo quy tắc riêng, không xóa hoặc sửa cấu trúc schema và không phải lệnh khôi phục lịch sử baseline.

## 23. Chẩn đoán lỗi thường gặp khi xác định baseline

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Chạy update và gặp table already exists | Chưa baseline hoặc changeset được nhận diện như mới | Dừng; so sánh schema, ID/AUTHOR/FILENAME và history |
| Changelog-sync xong nhưng thiếu bảng/cột | Sync đánh dấu changeset dù schema chưa khớp | Đối chiếu canonical, tạo migration sửa tiến; không tin history đơn độc |
| Changeset cũ xuất hiện pending sau đổi thư mục | FILENAME thay đổi | Kiểm tra logicalFilePath và đường dẫn đã lưu |
| Staging và production có số changeset khác nhau | Lịch sử triển khai khác hoặc filter khác | Đối chiếu định danh, EXECTYPE, context/label và artifact |
| Diff báo nhiều khác biệt không liên quan | So sánh nhầm schema, system objects hoặc extension | Giới hạn scope, schema và object types |
| Generate-changelog có tên constraint lạ | DBMS tự sinh tên hoặc schema đã có lịch sử thủ công | Review và chuẩn hóa có kiểm soát |
| Không thấy trigger/function trong diff | Snapshot/extension chưa hỗ trợ hoặc thiếu quyền metadata | Kiểm tra bằng catalog và truy vấn chuyên biệt |
| Baseline schema đạt nhưng app lỗi | Thiếu reference data, permission hoặc object ngoài scope | Kiểm tra contract ứng dụng và data baseline |
| Changelog-sync đánh dấu cả migration mới | Dùng full master thay vì phạm vi baseline | Dừng; xác định history đã ghi, reconcile trước update |
| Database có Liquibase history từ trước | Đang tiếp quản một database đã được công cụ quản lý | Bảo toàn history, xác định ownership và baseline tiếp nối |
| Update sau baseline bỏ qua thay đổi cần chạy | Changeset mới đã bị sync nhầm | Xem EXECTYPE và trạng thái thật; lập kế hoạch khôi phục history |
| Không thể tái tạo schema từ baseline | Changelog thiếu đối tượng hoặc phụ thuộc môi trường | Hoàn thiện changelog và thử lại trên database trống |

Khi chẩn đoán, luôn phân biệt:
- Lỗi **canonical model**: chuẩn chưa được xác định hoặc có mâu thuẫn.
- Lỗi **schema drift**: database thực tế khác chuẩn.
- Lỗi **identity/history**: ID/AUTHOR/FILENAME không khớp.
- Lỗi **baseline scope**: changelog-sync đánh dấu sai phạm vi.
- Lỗi **snapshot coverage**: công cụ không nhìn thấy đủ đối tượng.
- Lỗi **application contract**: schema/data đúng một phần nhưng ứng dụng còn phụ thuộc cấu trúc khác.

## 24. Bài thực hành: tiếp nhận một database legacy

**Bối cảnh:** ứng dụng Spring Boot đang sử dụng PostgreSQL. Database legacy đã có bảng customer, payment, payment_status và các FK, nhưng chưa có DATABASECHANGELOG. Nhóm muốn đưa schema vào quản lý Liquibase mà không chạy lại DDL đã tồn tại.

### Phần A — Kiểm kê và chọn chuẩn

1. Xác nhận DBMS/version, database, schema, quyền và các extension.
2. Chụp snapshot/metadata schema hiện tại.
3. Kiểm tra DDL trong repository và migration lịch sử.
4. So sánh staging với production; liệt kê bảng/cột/constraint/index khác nhau.
5. Phân loại khác biệt và quyết định canonical schema được phê duyệt.
6. Kiểm tra dữ liệu tham chiếu và các FK hiện có.
7. Ghi nhận những object không được snapshot bao phủ.

### Phần B — Tạo baseline changelog

1. Sinh changelog sơ bộ từ schema chuẩn bằng công cụ phù hợp hoặc viết thủ công theo quy ước.
2. Review mọi createTable, column, PK/FK/UNIQUE, index, sequence, view và routine.
3. Tách baseline-only changelog chứa đúng các changeset đến mốc legacy-schema-v1.
4. Tạo master changelog tương lai include các tệp baseline với đường dẫn ổn định và các changeset sau mốc.
5. Thử master changelog trên database trống và so sánh với canonical.
6. Thử baseline-only changelog trên bản sao legacy.

### Phần C — Sync lịch sử có kiểm soát

1. Backup bản sao legacy và xác nhận kết nối target.
2. Chạy validate và kiểm tra status.
3. Sinh SQL sync nếu phiên bản hỗ trợ, review phạm vi.
4. Chạy changelog-sync trên baseline-only changelog.
5. Kiểm tra DATABASECHANGELOG: các changeset baseline được ghi nhận đúng.
6. Gắn tag mốc baseline theo quy trình đã chọn.
7. Dùng master changelog chạy status; xác nhận chỉ các changeset sau baseline còn pending.
8. Review update-sql và chạy thử changeset tiếp theo trên bản sao.

### Phần D — Đối chiếu và bàn giao

- So sánh schema sau tiếp nhận với canonical.
- Kiểm tra dữ liệu reference và FK.
- Khởi động ứng dụng với Hibernate validate.
- Chạy integration test và smoke test.
- Lưu artifact/changelog revision, tag, history và báo cáo drift.
- Chỉ sau khi có bằng chứng mới bật quy trình Liquibase trong CI/CD/production.

### Câu hỏi tự kiểm tra

- Canonical schema có nhất thiết là schema production hiện tại? **Không.** Production là bằng chứng quan trọng, nhưng phải đánh giá drift và yêu cầu được phê duyệt.
- Changelog-sync có chạy CREATE TABLE không? **Không**, nó đánh dấu changeset như đã được xử lý trong lịch sử mà không thực thi change.
- Changelog-sync có kiểm tra database đã đúng canonical không? **Không đầy đủ.** Phải so sánh trước.
- Tại sao baseline-only changelog quan trọng? **Để tránh đánh dấu nhầm các changeset sau mốc baseline là đã chạy.**
- Generate-changelog có khôi phục lịch sử migration thủ công không? **Không.** Nó mô tả schema quan sát được, không biết đầy đủ ai đã thay đổi gì và khi nào.
- Có nên xóa DATABASECHANGELOG nếu baseline sai? **Không.** Cần điều tra và reconcile lịch sử có kiểm soát.
- Nếu schema giống nhau nhưng reference data khác nhau thì baseline schema đã đủ chưa? **Chưa.** Cần baseline/reconcile dữ liệu riêng.

## 25. Checklist trước khi tiếp nhận database legacy

**Xác định canonical schema**
- [ ] Đã xác định database, schema, catalog và phạm vi object thuộc module.
- [ ] Đã xác định DBMS/version và các extension/feature có ảnh hưởng.
- [ ] Đã thu thập DDL, snapshot, migration lịch sử và mapping ứng dụng.
- [ ] Đã phân loại khác biệt giữa development, staging và production.
- [ ] Đã quyết định canonical schema và có người chịu trách nhiệm phê duyệt.
- [ ] Đã ghi lại drift, ngoại lệ và object không được công cụ snapshot hỗ trợ.
- [ ] Đã kiểm tra dữ liệu tham chiếu, FK, unique, sequence và các quy tắc dữ liệu.

**Thiết kế baseline**
- [ ] Baseline changelog tái tạo được schema trên database trống.
- [ ] ID/AUTHOR/FILENAME ổn định, không xung đột lịch sử cũ.
- [ ] Đường dẫn include và logicalFilePath đã được kiểm soát.
- [ ] Có baseline-only changelog chỉ chứa changeset đến đúng mốc.
- [ ] Changelog master tương lai include cùng baseline file và các migration mới.
- [ ] Dữ liệu tham chiếu được xử lý riêng với schema baseline.
- [ ] Không đưa DATABASECHANGELOG/DATABASECHANGELOGLOCK vào object nghiệp vụ.

**Thực hiện baseline**
- [ ] Có backup và xác nhận target database.
- [ ] Đã so sánh target với canonical và xử lý drift.
- [ ] Đã review phạm vi changelog-sync/changelog-sync-sql.
- [ ] Không chạy changelog-sync trên master chứa changeset mới ngoài mốc.
- [ ] Đã kiểm tra DATABASECHANGELOG và EXECTYPE sau sync.
- [ ] Đã gắn tag/mốc tiếp quản nếu quy trình yêu cầu.
- [ ] Status trên master chỉ hiển thị các changeset sau baseline còn pending.

**Sau baseline**
- [ ] Đã so sánh schema thực tế với canonical lần cuối.
- [ ] Đã kiểm tra data, permissions và ứng dụng.
- [ ] Đã thử update changeset tiếp theo trên database bản sao.
- [ ] Đã thử rollback/forward fix phù hợp.
- [ ] CI/CD dùng update cho phát hành thường xuyên, không lặp changelog-sync.
- [ ] Có tài liệu provenance, artifact revision, người phê duyệt và bằng chứng triển khai.

**Kết luận:** tiếp nhận database legacy an toàn bắt đầu từ việc xác định một **canonical schema có thể tái tạo và được phê duyệt**, sau đó mới chọn **baseline point** để Liquibase ghi nhận lịch sử. Snapshot, diff và generate-changelog giúp quan sát và tạo bản nháp; chúng không thay thế review. Changelog-sync giúp đánh dấu các thay đổi đã tồn tại mà không chạy lại DDL, nhưng không xác minh database có đúng cấu trúc hay không. Kết hợp kiểm kê, phân loại drift, baseline-only changelog, kiểm chứng DATABASECHANGELOG, thử trên database trống và bản sao legacy sẽ tạo nền tảng đáng tin cậy để các changeset mới tiếp tục được quản lý bằng Liquibase, Spring Boot và CI/CD.
