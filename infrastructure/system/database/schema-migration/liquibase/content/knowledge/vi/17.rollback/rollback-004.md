# Gắn mốc bằng tag và change type tagDatabase trong Liquibase

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chúng ta học cách quản lý thay đổi schema và dữ liệu bằng Liquibase với **changelog**, **changeset**, **precondition**, **checksum** và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài thuộc chương **Hoàn tác** này tập trung vào cách đặt một **mốc trạng thái database (tag)**, đặc biệt là sự khác nhau giữa **lệnh `liquibase tag`** và **change type `tagDatabase`** trong changelog.

Tag hữu ích khi cần phát biểu rõ: *“Nếu bản phát hành mới gặp lỗi, database cần trở về trạng thái tại mốc đã kiểm chứng này.”* Tuy nhiên, tag chỉ đánh dấu một ranh giới **trong lịch sử thực thi Liquibase**; nó **không phải bản sao dữ liệu, không tự sinh rollback cho mọi changeset và không bảo đảm hệ thống quay lại trạng thái nghiệp vụ trước đó**.

Mục tiêu của bài là biết chọn cách gắn mốc, đọc metadata của tag trong `DATABASECHANGELOG`, xem trước phạm vi rollback, kiểm chứng khả năng hoàn tác và xây dựng quy trình release/CI/CD có thể truy vết.

## 1. Tag đánh dấu điều gì?

Liquibase quản lý lịch sử các changeset đã thực thi trong bảng **DATABASECHANGELOG** của database đích. Một changeset thông thường được nhận diện theo **id**, **author** và **đường dẫn changelog**; bảng lịch sử còn có thông tin về thời điểm thực thi, thứ tự, checksum và kiểu thực thi.

**Tag** là nhãn được gắn tại một **điểm trong lịch sử đó**, ví dụ:

- `release_2026_11_19`: mốc schema cho một bản phát hành;
- `before_customer_status_not_null`: trạng thái trước bước siết ràng buộc;
- `baseline_v2`: mốc đã xác nhận trong một quy trình tiếp quản database;
- `staging_candidate_17`: mốc thử nghiệm trong database staging.

Hình dung lịch sử:

~~~text
Trạng thái S0
    |
    v
changeset 001: tạo bảng customer             -> S1
    |
    v
changeset 002: thêm cột status               -> S2
    |
    +---- TAG: release_1_0 -------------------+
    |                                        |
    v                                        |
changeset 003: backfill status               -> S3
    |                                        |
    v                                        |
changeset 004: thêm NOT NULL                 -> S4
                                             |
rollback tới release_1_0  <-----------------+
  mục tiêu: đảo các thay đổi sau ranh giới S2
~~~

Trong ví dụ, **rollback đến tag** nhằm loại bỏ tác động của các changeset sau mốc, còn các changeset đã thuộc trạng thái S2 không nằm trong phạm vi hoàn tác. Cách Liquibase xử lý **dòng metadata của chính tagDatabase** khi rollback có thể phụ thuộc vào cơ chế gắn tag, phiên bản và các thuộc tính liên quan; cần kiểm chứng trên phiên bản sử dụng, không suy luận chỉ từ sơ đồ.

**Tag thuộc database đích**, không phải nhãn Git tự động đồng bộ qua các môi trường. Cùng một tên tag trên development, staging và production có thể đại diện cho những thời điểm khác nhau hoặc chưa tồn tại ở một môi trường. Vì vậy, luôn xác định rõ database, changelog và lịch sử trước khi dùng một tag để rollback.

## 2. Hai cách gắn mốc: lệnh tag và change type tagDatabase

Liquibase có hai cơ chế phổ biến:

1. **Lệnh `tag` của CLI:** gắn tag vào trạng thái hiện tại của database đã được Liquibase quản lý.
2. **Change type `tagDatabase`:** đặt một bước gắn mốc **trong changelog**, để Liquibase thực thi như một changeset khi cập nhật tới vị trí đó.

| Tiêu chí | `liquibase tag` | `tagDatabase` trong changelog |
|---|---|---|
| Điểm kích hoạt | Người vận hành hoặc pipeline gọi lệnh tag | Liquibase chạy changeset chứa `tagDatabase` trong `update` |
| Lưu trong mã nguồn changelog | Không nhất thiết | Có, là một changeset được version hóa |
| Vị trí mốc | Cuối phần lịch sử đã thực thi tại lúc gọi lệnh | Vị trí định trước trong thứ tự changeset |
| Lưu trên DATABASECHANGELOG | Thông thường điền TAG cho bản ghi cuối liên quan | Có bản ghi changeset gắn mốc riêng trong lịch sử |
| Phù hợp | Đánh dấu sau khi postflight/smoke test đạt | Đánh dấu ranh giới logic cố định của migration |
| Điều cần cảnh giác | Có changeset còn pending hoặc ai đó update xen vào | Changelog/contexts/labels khiến tag không được áp dụng ở môi trường đích |

Hai cơ chế **không tự thay thế nhau**. Nếu yêu cầu là *“đặt mốc sau khi các bài kiểm tra triển khai thực tế hoàn tất”*, lệnh `tag` trong pipeline thường diễn đạt đúng ý định hơn. Nếu yêu cầu là *“mỗi database khi đã chạy đến changeset này phải có một ranh giới rollback giống nhau”*, `tagDatabase` trong changelog thường phù hợp hơn.

Không nên coi tag vừa là release đã nghiệm thu, vừa là mốc schema nếu thời điểm tạo tag diễn ra **trước** khi chạy kiểm tra hậu điều kiện. Tên tag và quy trình phải nói rõ tag đại diện cho điều gì.

## 3. Dùng lệnh liquibase tag

Khi database đã được cập nhật đến trạng thái mong muốn, có thể chạy lệnh gắn tag từ Liquibase CLI:

~~~shell
liquibase tag --tag=release_1_0
~~~

Các ví dụ CLI trong bài giả định `liquibase.properties` hoặc tham số tương đương đã cung cấp **changelog-file, JDBC URL, driver và credentials**; cách viết options có thể thay đổi theo phiên bản Liquibase. Hãy xác minh cú pháp bằng CLI phiên bản được cố định trong dự án trước khi đưa vào CI/CD.

Lệnh tag ghi mốc vào metadata `DATABASECHANGELOG`; nó **không chạy các changeset đang pending** thay cho `update` và không tạo ảnh chụp bảng dữ liệu. Nếu đặt tag khi database chưa chạy hết changelog dự kiến, mốc có thể đại diện cho trạng thái khác mục tiêu release.

Một luồng vận hành có kiểm soát:

~~~shell
liquibase validate
liquibase status --verbose
liquibase update
liquibase status --verbose
liquibase tag --tag=release_1_0
~~~

**Không** nên copy nguyên luồng này vào production mà bỏ qua review SQL và hậu kiểm dữ liệu. Thứ tự đúng là: nhận diện đúng database → validate, review changeset/SQL → update → xác minh hậu điều kiện → **gắn tag sau khi đạt gate**.

Cần kiểm tra phiên cập nhật có kết thúc hoàn toàn và không có job khác cập nhật chen vào giữa bước kiểm tra và bước tag. Nếu có thay đổi xen vào, tag có thể đánh dấu một trạng thái khác đã được phê duyệt.

### Lệnh tag có thay đổi lịch sử thế nào?

Với cơ chế CLI thông dụng, tag được điền vào trường **TAG** của một dòng đã thực thi gần nhất trong `DATABASECHANGELOG`, thay vì thêm một changeset mới. Điều đó có hai hệ quả:

- Không thể coi mỗi lần gọi `tag` là một **bản ghi audit append-only** độc lập. Nếu đặt nhiều tag ở cùng một điểm, cần xác minh cách phiên bản Liquibase lưu/ghi đè giá trị TAG.
- Vị trí của tag phụ thuộc lịch sử đã thực thi tại lúc gọi lệnh. Pipeline phải bảo đảm toàn bộ changeset dự kiến đã chạy trước khi đặt mốc.

Với database hoàn toàn chưa có lịch sử Liquibase, không được mặc định rằng lệnh `tag` có sẵn một changeset cuối để gắn nhãn. Hãy khởi tạo và xác minh quy trình baseline riêng theo version/edition được sử dụng.

## 4. Dùng change type tagDatabase trong YAML changelog

`tagDatabase` là một change type đặt trong `changes` của changeset. Nó không có nhiệm vụ sửa bảng nghiệp vụ; nó đánh dấu trạng thái đạt đến vị trí đó trong chuỗi migration.

Ví dụ một changelog YAML hoàn chỉnh ở mức minh họa, giả sử database PostgreSQL mới và bảng `customer` chưa tồn tại:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: database-team
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
                  type: varchar(255)
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            tableName: customer

  - changeSet:
      id: 002-add-customer-status
      author: database-team
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: status
                  type: varchar(30)
      rollback:
        - dropColumn:
            tableName: customer
            columnName: status

  - changeSet:
      id: 003-tag-release-1-0
      author: database-team
      changes:
        - tagDatabase:
            tag: release_1_0

  - changeSet:
      id: 004-create-customer-status-index
      author: database-team
      changes:
        - createIndex:
            tableName: customer
            indexName: idx_customer_status
            columns:
              - column:
                  name: status
      rollback:
        - dropIndex:
            tableName: customer
            indexName: idx_customer_status
~~~

**Cách đọc:**

- Changeset 001 và 002 xây dựng trạng thái schema ban đầu.
- Changeset 003 đặt tag **release_1_0** tại ranh giới **sau** 002 và **trước** 004.
- Changeset 004 nằm **sau tag**; khi muốn đưa database từ trạng thái đã chạy 004 về ranh giới mốc, đây là thay đổi nằm trong tập cần xét rollback.
- Nếu chưa chạy `update` đến 003, chỉ có dòng YAML **không đồng nghĩa tag đã tồn tại trong database**.
- Nếu dùng `rollback` đến mốc trong khi bảng có dữ liệu thực tế, cần đánh giá tác động khi xóa index, constraint, cột hoặc bảng; định nghĩa rollback thành công chưa chắc hoàn nguyên dữ liệu theo nghiệp vụ.

Đặt `tagDatabase` như một changeset riêng giúp ranh giới dễ review và đối chiếu trong lịch sử. Đặt ID và author ổn định, không di chuyển file chứa changeset sau khi đã triển khai nếu không kiểm soát logical file path.

## 5. Tag trong DATABASECHANGELOG

Trên PostgreSQL, nếu bảng metadata của Liquibase nằm trong schema `public`, có thể kiểm tra:

~~~sql
SELECT
    id, author, filename, tag,
    exectype, dateexecuted, orderexecuted, md5sum
FROM public.databasechangelog
ORDER BY orderexecuted;
~~~

Một cách kiểm tra tag cụ thể:

~~~sql
SELECT
    id, author, filename, tag, exectype, orderexecuted
FROM public.databasechangelog
WHERE tag = 'release_1_0'
ORDER BY orderexecuted;
~~~

Ở đây:

- **TAG** chứa nhãn mốc do Liquibase ghi nhận.
- **ID/AUTHOR/FILENAME** xác định changeset gắn với dòng lịch sử, đặc biệt quan trọng với `tagDatabase`.
- **EXECTYPE** cho biết cách changeset được ghi nhận, ví dụ `EXECUTED`, `RERAN`, `MARK_RAN` tùy trường hợp.
- **ORDEREXECUTED** giúp hiểu thứ tự trong lịch sử ở thời điểm hiện tại; không nên dùng như audit bất biến cho mọi lần rollback và chạy lại.
- **MD5SUM** là checksum phục vụ xác thực thay đổi changeset, không phải checksum của toàn bộ database.

Đường dẫn và tên bảng metadata có thể được cấu hình khác, chẳng hạn schema riêng cho Liquibase. Không tự động chạy truy vấn `public.databasechangelog` ở production nếu tổ chức đã thay metadata schema.

Khi dùng `tagDatabase`, bạn thường thấy một dòng cho changeset chuyên gắn mốc. Với lệnh `tag`, cột TAG thường được điền trên một dòng changeset đã chạy. Dù cách nào, **dòng TAG không xác minh rằng dữ liệu nghiệp vụ đang ở trạng thái đúng**. Cần kiểm tra bảng/cột/constraint và dữ liệu sau triển khai.

## 6. Chọn mốc rollback như thế nào?

Mốc hợp lý nằm tại **trạng thái đã được kiểm chứng**, không chỉ tại nơi thuận tiện để thêm một dòng YAML.

Ví dụ hệ thống đặt hàng cần đưa lên schema v2:

~~~text
v1: customer(id, email)
      |
      | addColumn status (nullable)
      v
v1.1: customer có cột status, ứng dụng cũ vẫn tương thích
      |
      +-- TAG: before_status_enforcement
      |
      | backfill status
      | addNotNullConstraint
      v
v2: status bắt buộc
~~~

Đặt tag **before_status_enforcement** trước backfill và constraint giúp xác định phạm vi muốn đảo khi thay đổi v2 không tương thích. Tuy nhiên, rollback về mốc có thể cần:

- Đảo constraint NOT NULL.
- Xử lý tác động của backfill (dữ liệu nào đã được viết bởi ứng dụng sau đó?).
- Xem xét việc ứng dụng v2 còn chạy không.
- Quyết định nên rollback database, chỉ rollback ứng dụng hay dùng forward-fix.

Không nên đặt tag trước thao tác phá hủy mà mặc định rollback có thể “hồi sinh” cột đã DROP hoặc dữ liệu đã DELETE. Khôi phục dữ liệu có thể cần backup/PITR hay một cơ chế ghi nhận trạng thái trước đó.

### Tag có phải “điểm lưu an toàn” tuyệt đối?

**Không.** Tag giống như **địa chỉ trong lịch sử migration**, không phải checkpoint transaction và không phải snapshot. Cơ chế rollback chỉ có thể thực thi những thao tác đảo ngược được định nghĩa hoặc Liquibase hỗ trợ. Một số thay đổi SQL tự do, data migration hoặc DDL riêng DBMS có thể không có rollback tự động.

Vì vậy, trước khi quyết định dùng tag, cần làm rõ:

1. Những changeset **sau tag** là gì?
2. Chúng có rollback hợp lệ, đã thử trên DBMS đích chưa?
3. DBMS có rollback được DDL trong transaction không, hay có implicit commit?
4. Có cần phục hồi dữ liệu, quyền, trigger, sequence hoặc đối tượng ngoài phạm vi không?
5. Ứng dụng đang chạy có tương thích với schema cũ sau rollback không?

## 7. Xem trước rollback tới tag

Liquibase có lệnh xem SQL rollback dự kiến. Với cú pháp CLI thường dùng:

~~~shell
liquibase rollback-sql --tag=release_1_0
~~~

Lệnh này giúp kiểm tra phạm vi rollback **mà không áp dụng rollback**. Tên option và vị trí tham số có thể thay đổi theo phiên bản CLI; cần xác nhận bằng `liquibase --help` hoặc hướng dẫn đi kèm phiên bản đang dùng.

Khi review output, hãy kiểm tra:

| Câu hỏi | Vì sao cần kiểm tra |
|---|---|
| Đúng database, schema và tag? | Tránh đảo sai môi trường/nhầm mốc |
| Tag có thực sự tồn tại trong lịch sử đích? | Tên tag trong Git chưa đủ |
| Những changeset nào nằm sau mốc? | Có thể nhiều hơn phạm vi release vừa triển khai |
| Có `DROP TABLE`, `DROP COLUMN`, `DELETE` không? | Có thể gây mất dữ liệu và dependency |
| Các SQL rollback có đúng thứ tự đảo ngược không? | Quan hệ khóa ngoại, view, index, trigger phụ thuộc thứ tự |
| Có changeset `sql`/data migration thiếu rollback? | Liquibase có thể không tạo kế hoạch rollback đầy đủ |
| Có hành vi DDL không transaction không? | Có thể thất bại giữa chừng và để lại trạng thái dở |
| Rollback có cần giám sát quyền và lock? | Các lệnh đảo DDL có thể khóa bảng hoặc cần quyền đặc biệt |

Nếu `rollback-sql` báo lỗi vì changeset thiếu rollback, **đó là blocker cần giải quyết**, không phải lý do để bỏ qua bước preview. Nếu output được tạo thành công cũng chưa chứng minh các câu SQL sẽ chạy thành công hoặc phục hồi toàn bộ dữ liệu.

Một quy trình production nên yêu cầu review đầu ra rollback và đánh giá tác động trước khi cho phép thực thi, đặc biệt với schema đang có writer.

## 8. Thực thi rollback tới tag

Khi đã kiểm tra mốc, SQL đảo ngược, dữ liệu và tương thích ứng dụng, có thể thực thi:

~~~shell
liquibase rollback --tag=release_1_0
~~~

**Rollback theo tag đi lùi từ trạng thái hiện tại về ranh giới đã gắn tag.** Không có nghĩa Liquibase đưa database “trở lại ngày phát hành” ở cấp byte hay cấp dữ liệu nghiệp vụ; nó xử lý các changeset trong phạm vi lịch sử theo logic rollback.

Những điều cần ghi nhớ:

- Các thay đổi sau mốc phải có **rollback tương ứng hoặc được Liquibase hỗ trợ rollback tự động**, nếu không quá trình có thể dừng.
- Rollback có thể bị DBMS từ chối vì constraint, data dependency, quyền hoặc khác biệt phiên bản.
- Một số thao tác rollback đã chạy có thể không tự đảo ngược nếu lỗi phát sinh sau đó, nhất là trên DBMS có DDL implicit commit hoặc changeset chạy ngoài transaction.
- Khi rollback thành công, **DATABASECHANGELOG** thay đổi để phản ánh những changeset đã bị rollback; khi cập nhật trở lại, một số changeset có thể được thực thi lần nữa.
- **Dòng tagDatabase/tag có được giữ lại sau rollback hay không** cần được xác minh theo cơ chế tag, phiên bản Liquibase và các tùy chọn tương ứng. Với những phiên bản/edition có hỗ trợ thuộc tính như `keepTagOnRollback`, chính sách này có thể điều chỉnh việc giữ mốc. Không xây script retry chỉ dựa trên giả định tag luôn còn tồn tại.

### Phân biệt rollback theo tag với rollback theo số changeset/ngày

- **Rollback theo tag:** chọn ranh giới logic, chẳng hạn `release_1_0`.
- **Rollback theo count:** hoàn tác một số changeset đã chạy; dễ sai nếu số thay đổi khác giữa môi trường.
- **Rollback theo ngày:** nhắm đến thời điểm trong lịch sử, nhưng cần xét timezone, độ chính xác mốc và các changeset thực tế.

Tag thường dễ giải thích hơn trong vận hành release vì nó có **ý nghĩa nghiệp vụ hoặc phiên bản phát hành**. Tuy nhiên, tính chính xác vẫn phụ thuộc tag thực sự được ghi trong database và lịch sử không bị sửa ngoài quy trình.

## 9. Hành vi khi rollback chạm tagDatabase

`tagDatabase` là **changeset có định danh và vị trí trong changelog**, trong khi tag qua CLI thường gắn lên bản ghi lịch sử đã có. Sự khác nhau này ảnh hưởng cách Liquibase xác định ranh giới và xử lý chính bản ghi tag lúc rollback.

**Nguyên tắc vận hành:** một tag trong changelog được dùng làm mốc để đưa schema về trạng thái của những changeset đã thực thi **trước hoặc đến ranh giới tag**. Thông thường, rollback tới mốc không chủ ý đảo các migration trước mốc. Tuy nhiên, cần kiểm tra **mốc metadata có còn được lưu hay bị loại khi rollback** trên phiên bản Liquibase sử dụng. Tùy phiên bản/edition, có thể có tùy chọn giữ tag khi rollback (ví dụ `keepTagOnRollback` khi được hỗ trợ).

Ví dụ:

~~~text
001 create customer       [EXECUTED]
002 add status            [EXECUTED]
003 tagDatabase v1_0      [EXECUTED + TAG=v1_0]
004 create index          [EXECUTED]

rollback tới v1_0:
  - index do 004 tạo cần được đảo theo rollback của 004
  - customer và status của 001/002 là trạng thái mục tiêu
  - dòng metadata 003 cần được kiểm tra lại theo phiên bản/tùy chọn
~~~

Vì vậy, hãy thử **trọn chu trình update → tagDatabase → update bổ sung → rollback tới tag → truy vấn DATABASECHANGELOG và schema → update lại** trên database test trước khi chuẩn hóa pipeline. Không viết automation chỉ kiểm tra bằng cách truy vấn một dòng TAG sau rollback mà bỏ qua schema thực tế.

Một điểm nữa: một changeset chứa `tagDatabase` có thể được áp dụng khi `update` chạy đến nó, **trước** những changeset phía sau trong cùng đợt update. Nếu đợt update về sau thất bại, tag trước đó không chứng minh toàn bộ release thành công. Tag chỉ đánh dấu vị trí trong lịch sử, không xác nhận gate postflight.

## 10. Ví dụ triển khai có precondition và rollback

Giả sử mục tiêu là đánh dấu trạng thái sau khi tạo bảng `customer`, trước khi thêm UNIQUE cho `email`. Lý do chọn ranh giới này là muốn có khả năng đảo ràng buộc mà vẫn giữ dữ liệu và bảng ban đầu.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 101-customer-before-email-unique-tag
      author: database-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: customer
        - columnExists:
            tableName: customer
            columnName: email
      changes:
        - tagDatabase:
            tag: before_customer_email_unique

  - changeSet:
      id: 102-customer-email-unique
      author: database-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*) FROM (
                SELECT email
                FROM customer
                WHERE email IS NOT NULL
                GROUP BY email
                HAVING COUNT(*) > 1
              ) duplicate_emails
      changes:
        - addUniqueConstraint:
            tableName: customer
            columnNames: email
            constraintName: uq_customer_email
      rollback:
        - dropUniqueConstraint:
            tableName: customer
            constraintName: uq_customer_email
~~~

**Giả định:** bảng `customer` đã tồn tại từ các changeset trước, cùng schema mục tiêu, và DBMS hỗ trợ SQL kiểm tra trùng email như minh họa. Hãy điều chỉnh schema, collation, chuẩn hóa email và quy tắc NULL theo DBMS thật. Precondition chỉ giúp phát hiện dữ liệu không đạt trước thời điểm chạy; writer đồng thời vẫn có thể tạo trùng trước khi constraint được áp dụng.

Khi rollback đến `before_customer_email_unique`, Liquibase phải có khả năng đảo ràng buộc UNIQUE vừa thêm. Nhưng nếu ứng dụng phiên bản mới đã phụ thuộc ràng buộc này để ngăn email trùng, rollback có thể tạo lỗ hổng toàn vẹn dữ liệu dù lệnh SQL chạy thành công. Do đó phải xem xét phiên bản ứng dụng và các kiểm tra nghiệp vụ trước khi thực thi.

**Không dùng `onFail: MARK_RAN` cho tag hoặc cho bước thêm UNIQUE chỉ để né điều kiện sai.** Nếu đã có constraint cùng tên, cần đối chiếu định nghĩa trước; MARK_RAN có thể làm lịch sử báo đã triển khai trong khi database không đạt trạng thái kỳ vọng.

## 11. Kiểm tra tag và lịch sử trước/sau rollback

Một số lệnh CLI hữu ích (tùy phiên bản/edition và các tùy chọn hỗ trợ):

~~~shell
liquibase validate
liquibase status --verbose
liquibase tag-exists --tag=before_customer_email_unique
liquibase rollback-sql --tag=before_customer_email_unique
~~~

**Tag tồn tại** là điều kiện cần để rollback đến tag; nhưng không đủ. Trước thao tác, kiểm tra:

1. Định danh database/schema và phiên bản DBMS.
2. Tên tag chính xác và không có nhầm lẫn giữa môi trường.
3. Changeset nào ở sau mốc và kế hoạch rollback cho từng changeset.
4. Dữ liệu mới có thể bị mất hoặc không còn phù hợp sau rollback.
5. Bản sao hoặc phương án phục hồi đã được kiểm thử.
6. Tiến trình ứng dụng hoặc migration khác có đang ghi dữ liệu/giữ khóa không.

Sau rollback:

~~~sql
SELECT id, author, filename, tag, exectype, dateexecuted
FROM public.databasechangelog
ORDER BY orderexecuted;
~~~

Kết hợp với metadata thực tế, ví dụ PostgreSQL để kiểm tra constraint:

~~~sql
SELECT
    conname,
    contype,
    convalidated
FROM pg_constraint
WHERE conrelid = 'public.customer'::regclass
  AND conname = 'uq_customer_email';
~~~

**Kỳ vọng khi rollback tới mốc trước UNIQUE:** ràng buộc `uq_customer_email` không còn; các bảng/cột được tạo **trước mốc** vẫn tồn tại. Nếu kế hoạch sản phẩm cần duy trì uniqueness, đó không phải trạng thái ứng dụng được phép tiếp tục hoạt động mà không có giải pháp thay thế.

Đừng chỉ nhìn `DATABASECHANGELOG` để kết luận hậu điều kiện đạt. Một thay đổi DDL có thể còn tác động ngoài dự kiến; một data migration đã rollback có thể không phục hồi giá trị ban đầu; một rollback lỗi giữa chừng có thể để lại metadata và schema chưa đồng bộ.

## 12. Tag, rollback, restore và forward-fix khác nhau

| Khái niệm | Mục đích | Không bảo đảm |
|---|---|---|
| **Tag** | Đặt ranh giới trong lịch sử migration | Không lưu toàn bộ dữ liệu hoặc snapshot schema |
| **Rollback theo tag** | Chạy logic đảo ngược changeset sau mốc | Không tự phục hồi dữ liệu đã mất, tài nguyên ngoài DB |
| **Rollback transaction** | Hủy thay đổi chưa commit trong transaction nếu DBMS hỗ trợ | Không đảo các changeset đã commit trước đó |
| **Restore/PITR** | Khôi phục database từ backup hoặc thời điểm đã lưu | Có thể mất những giao dịch hợp lệ sau thời điểm phục hồi |
| **Forward-fix** | Tạo changeset mới sửa trạng thái hiện tại | Không tự đưa hệ thống về phiên bản cũ |
| **Git tag** | Đánh dấu commit hoặc artifact mã nguồn | Không tạo Liquibase tag trong DATABASECHANGELOG |

Một release có thể cần **rollback ứng dụng** trước, **giữ nguyên schema** nếu vẫn tương thích, sau đó dùng forward-fix để sửa lỗi dữ liệu. Không phải mọi sự cố ứng dụng đều cần rollback database. Ngược lại, một migration phá hủy dữ liệu có thể không thể khắc phục bằng rollback SQL, dù đã gắn tag trước đó.

Đối với bước có nguy cơ xóa dữ liệu, chuyển kiểu không thể đảo hoặc cập nhật dữ liệu một chiều, cần có phương án backup/restore được thử, RPO/RTO và quyết định duy trì hoặc dừng writer trong quá trình khôi phục.

## 13. Tổ chức release bằng tag trong CI/CD

Có thể chọn hai chiến lược chính.

### Chiến lược A — Tag được khai báo trong changelog

~~~text
Review changelog
  -> 001/002 cập nhật schema
  -> 003 tagDatabase: schema_release_1_0
  -> 004/005 thay đổi kế tiếp
  -> Kiểm tra DATABASECHANGELOG và schema
~~~

Ưu điểm: vị trí ranh giới tag gắn với mã nguồn và thứ tự changeset, thuận tiện khi muốn các môi trường có một mốc schema giống nhau **sau khi đã chạy tới changeset gắn tag**.

Hạn chế: tag được áp dụng trong lúc update, không chờ pipeline hoàn tất mọi hậu kiểm. Nếu muốn gắn nhãn *“đã được nghiệm thu production”*, cần thêm một cơ chế ghi nhận phát hành sau các gate kiểm tra.

### Chiến lược B — Tag qua CLI sau postflight

~~~text
Build artifact từ commit đã review
  -> preflight database & history
  -> validate + review update-sql
  -> Liquibase update
  -> postflight schema/data/app smoke test
  -> nếu PASS: liquibase tag --tag=release_1_0
  -> ghi log/commit/build/tag metadata
~~~

Ưu điểm: chỉ tạo tag khi những kiểm tra bắt buộc đã đạt. Hạn chế: tag phụ thuộc luồng vận hành, không phải một changeset được khai báo trong changelog; cần tránh race giữa postflight và lúc gắn tag.

Ở cả hai chiến lược, phải xác định **một tiến trình sở hữu migration**. Nếu Spring Boot được cấu hình tự chạy Liquibase khi nhiều replica khởi động, hoặc job CI và ứng dụng cùng tự update, việc gắn tag bằng CLI cần được điều phối để không đánh dấu sai ranh giới. `DATABASECHANGELOGLOCK` giúp tránh các tiến trình Liquibase cập nhật schema đồng thời, nhưng không thay cho gate phê duyệt release.

Một mẫu Spring Boot khi ứng dụng chịu trách nhiệm chạy Liquibase:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Nếu pipeline chạy Liquibase riêng trước deploy ứng dụng, profile runtime có thể tắt `spring.liquibase.enabled` để tránh thực thi ngoài kế hoạch. Chỉ dùng một mô hình theo kiến trúc đã chọn; không thay đổi ownership giữa các môi trường mà thiếu tài liệu vận hành.

## 14. Đặt tên tag và kiểm soát tính duy nhất

Tên tag nên dễ đọc, ổn định, tránh mơ hồ, và thống nhất với cách đặt version cho release. Một quy ước minh họa:

~~~text
schema_release_2026_11_19_01
before_customer_email_unique
baseline_customer_v2
~~~

Một số khuyến nghị:

- **Tránh tên quá chung** như `latest`, `prod` hoặc `stable` nếu chúng có thể trỏ đến các mốc khác nhau theo thời gian.
- **Không tái sử dụng cùng tên cho nhiều mốc trong một database**. Dù một hệ quản trị hoặc phiên bản cho phép ghi tag lặp, việc tìm mốc rollback sẽ khó giải thích và nguy hiểm.
- **Không dùng tag database để thay thế Git tag.** Có thể dùng hai nhãn tương ứng, nhưng cần ghi mapping giữa release artifact, changelog commit và database tag.
- **Không dùng ngày làm bằng chứng duy nhất**: nhiều pipeline có thể chạy trong cùng một ngày. Thêm mã release/build nếu cần.
- **Giữ nguyên tên tag đã triển khai**. Sửa `tag:` trong một changeset `tagDatabase` cũ có thể gây xung đột lịch sử/checksum và không tự cập nhật mọi database đồng nhất.
- **Báo cáo rõ phạm vi môi trường**: tag `release_1_0` trên staging không chứng minh production cũng đã cập nhật tới ranh giới này.

Nếu muốn sử dụng tag làm điểm phục hồi phát hành, nhóm cần ghi thêm trạng thái hậu kiểm, thời điểm, build, DBMS/version, người phê duyệt và kịch bản rollback đã được thử.

## 15. Các rủi ro thường gặp

### Rủi ro 1 — Có tag nhưng không có rollback khả dụng

Một changeset SQL tự do thực hiện backfill không lưu giá trị cũ. Khi rollback, không thể suy ra những giá trị ban đầu. Tag không giải quyết được việc thiếu thông tin đảo ngược.

**Giải pháp:** thiết kế rollback ngay lúc viết changeset, ghi dữ liệu trước thay đổi nếu được phép, thử rollback-sql và cân nhắc restore/forward-fix.

### Rủi ro 2 — Gắn tag khi còn changeset pending

Pipeline thấy update trước đó trả mã 0 nhưng vẫn có changeset không được chọn do context/label, hoặc chưa chạy tới migration mong muốn. Lệnh tag đặt mốc ở trạng thái khác dự kiến.

**Giải pháp:** kiểm tra đúng contexts/labels, đối chiếu các changeset bắt buộc, hậu điều kiện schema và lịch sử; tag sau gate thay vì sau một câu log “SUCCESS”.

### Rủi ro 3 — TagDatabase bị đánh dấu MARK_RAN

Nếu `tagDatabase` hoặc changeset liên quan bị xử lý đặc biệt qua precondition, lịch sử có thể không phản ánh đầy đủ ý nghĩa ranh giới như người đọc changelog mong đợi.

**Giải pháp:** giữ changeset tag đơn giản, điều kiện rõ ràng; đọc `DATABASECHANGELOG` và xác minh mốc thực sự đã được ghi trên database test/đích trước khi dựa vào nó.

### Rủi ro 4 — Rollback làm mất tương thích phiên bản ứng dụng

Ứng dụng mới đã yêu cầu cột vừa được thêm sau tag; rollback xóa cột khiến ứng dụng mới lỗi dù migration đảo ngược thành công.

**Giải pháp:** chọn kế hoạch ứng dụng và database cùng nhau; dùng expand/contract, dừng writer khi cần, smoke test và cân nhắc rollback ứng dụng hoặc forward-fix thay vì chỉ rollback schema.

### Rủi ro 5 — Database đã thay đổi ngoài Liquibase

Một DBA sửa index/constraint hoặc dữ liệu bằng SQL trực tiếp. Lịch sử tag còn nguyên nhưng trạng thái thực tế đã drift.

**Giải pháp:** kết hợp so sánh metadata, SQL kiểm tra và nhật ký thay đổi ngoài Liquibase; không tin rằng TAG hoặc MD5SUM của changeset đồng nghĩa mọi đối tượng DB vẫn đúng.

### Rủi ro 6 — Tag bị mất hoặc thay đổi sau rollback

Tùy cơ chế và phiên bản Liquibase, dòng metadata chứa tag có thể được xử lý khác nhau khi rollback. Script tự động dựa vào cùng tag để retry mà không kiểm tra lại có thể thất bại.

**Giải pháp:** kiểm tra lại tag sau rollback, dùng cơ chế giữ tag nếu phiên bản hỗ trợ và đã review; lưu log release độc lập với DATABASECHANGELOG để truy vết.

### Rủi ro 7 — Hai pipeline cùng tác động một database

Một pipeline gọi update trong khi pipeline khác định gắn tag hoặc rollback. Dù có locking của Liquibase, trình tự các bước ngoài lệnh update có thể không nguyên tử như kỳ vọng.

**Giải pháp:** điều phối release bằng một job duy nhất hoặc cơ chế deployment lock ở tầng pipeline; không dùng tag theo cách chạy xen kẽ với update chưa xác định trạng thái.

## 16. Quy trình kiểm chứng trọn vòng trên database thử nghiệm

Hãy dùng một database test cô lập, không phải production, và một changelog minh họa ở mục 4.

**Bước 1 — Preflight.** Xác nhận database, schema, role, Liquibase/JDBC version. Bảo đảm chưa có bảng customer hoặc chuẩn bị database thử nghiệm phù hợp với điều kiện của ví dụ.

**Bước 2 — Validate và xem SQL update.**

~~~shell
liquibase validate
liquibase update-sql
~~~

Review rằng 001, 002, 003 (tagDatabase) và 004 đúng thứ tự, không còn changeset ngoài phạm vi.

**Bước 3 — Chạy update và kiểm tra tag.**

~~~shell
liquibase update
liquibase tag-exists --tag=release_1_0
~~~

Sau đó truy vấn `DATABASECHANGELOG`, kiểm tra dòng `003-tag-release-1-0`, trường TAG và ràng buộc/index thực tế của database.

**Bước 4 — Xem SQL rollback tới mốc.**

~~~shell
liquibase rollback-sql --tag=release_1_0
~~~

Kỳ vọng phạm vi chủ yếu liên quan những changeset chạy sau mốc, chẳng hạn index do 004 tạo. Nếu SQL dự kiến xóa bảng customer của 001 thì cần dừng và điều tra chọn mốc/sai changelog trước khi thực thi.

**Bước 5 — Rollback trong test.**

~~~shell
liquibase rollback --tag=release_1_0
~~~

Kiểm tra index của 004 đã được loại bỏ theo rollback, bảng customer và cột status vẫn tồn tại, dữ liệu không bị mất ngoài dự kiến. Đọc lại `DATABASECHANGELOG`, xác nhận dòng tag được giữ/xử lý theo hành vi thực tế của phiên bản.

**Bước 6 — Update lần nữa.** Chạy lại `liquibase status --verbose`, review changeset đang pending rồi `liquibase update` để kiểm tra đường triển khai lại hoạt động. Với tagDatabase, kiểm tra xem Liquibase có áp dụng lại changeset gắn tag theo lịch sử còn lại không.

**Bước 7 — Thử cách gắn tag CLI.** Trên bản sao test đã đạt postflight, gọi `liquibase tag --tag=after_postflight_test`, truy vấn TAG và so sánh cách ghi metadata với `tagDatabase`. Không dùng cùng tên cho hai phương pháp trên một database.

**Bước 8 — Đánh giá phục hồi.** Thử một changeset SQL không có rollback tự động (trong phạm vi test) để thấy vì sao tag không đủ. Ghi lại giới hạn, phương án forward-fix và quy trình backup/restore trước khi vận hành production.

Kết quả bài tập không chỉ là một lệnh rollback chạy xong, mà là **bằng chứng trạng thái schema, dữ liệu, lịch sử và ứng dụng** tương ứng mốc mong muốn.

## 17. Checklist trước khi dùng tag ở production

- [ ] Xác minh database, schema, role và changelog artifact chính xác.
- [ ] Xác định tag sẽ được tạo **trong changelog** hay **sau postflight**; tài liệu hóa ý nghĩa.
- [ ] Tên tag duy nhất, gắn với release/commit và không mơ hồ giữa môi trường.
- [ ] Đã xác minh changeset cần thiết chạy xong trước khi gắn mốc.
- [ ] Đã kiểm tra tag tồn tại trong `DATABASECHANGELOG` sau khi tạo.
- [ ] Biết rõ những changeset **sau tag** và phạm vi rollback.
- [ ] Đã review `rollback-sql` và thử rollback trên DBMS/version tương đương.
- [ ] Đã xem dữ liệu có thể mất hoặc thay đổi không thể đảo; có kế hoạch restore/forward-fix.
- [ ] Đã kiểm tra các phiên bản ứng dụng có tương thích với schema trước tag.
- [ ] Đã điều phối job CI/CD, Spring Boot và các tiến trình Liquibase khác.
- [ ] Có log/approval/backup phù hợp; không coi TAG là snapshot.
- [ ] Đã kiểm tra lại tag, lịch sử và schema sau một lần rollback thử nghiệm.
- [ ] Không sửa changeset đã triển khai hoặc bảng `DATABASECHANGELOG` để “chữa” sai mốc.

## 18. Tổng kết và nguyên tắc lựa chọn

**`liquibase tag`** phù hợp khi đội vận hành muốn gắn mốc vào trạng thái database **đã triển khai và kiểm chứng**, thường sau postflight của CI/CD. **`tagDatabase`** phù hợp khi muốn **khai báo ranh giới rollback trong chính changelog**, được quản lý bằng id/author và chạy theo thứ tự changeset.

Dù chọn cách nào, hãy phân biệt **mốc lịch sử** với **khả năng phục hồi**: tag chỉ trả lời *“đi lùi tới vị trí nào?”*, còn rollback SQL, trạng thái dữ liệu, transaction của DBMS, backup và tương thích ứng dụng mới trả lời *“có thực sự quay lại an toàn được không?”*. Với **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, phối hợp tag, changelog bất biến, checksum, precondition, DATABASECHANGELOG, review `rollback-sql`, thử nghiệm rollback và gate CI/CD là cách quản lý phát hành có thể kiểm chứng thay vì thao tác hoàn tác theo cảm tính.
