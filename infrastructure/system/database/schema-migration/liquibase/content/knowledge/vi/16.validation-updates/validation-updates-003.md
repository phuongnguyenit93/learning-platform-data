# Xem lịch sử triển khai bằng history trong Liquibase

Một migration thành công trên máy phát triển chưa có nghĩa nó đã chạy trên staging hoặc production. Trong một hệ thống nhiều môi trường, nhóm vận hành thường cần trả lời: **Database này đã áp dụng những changeset nào, khi nào, theo thứ tự nào và lần triển khai nào?** Lệnh **history** của Liquibase giúp quan sát lịch sử changeset đã được ghi nhận trên database đang kết nối, từ đó hỗ trợ đối chiếu phát hành, điều tra lỗi và quyết định bước cập nhật tiếp theo.

Bài học thuộc chương **Kiểm tra và cập nhật** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Phạm vi của module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

**Mục tiêu học tập:** sau bài này, bạn có thể chạy và diễn giải **liquibase history**, hiểu quan hệ của lệnh này với bảng **DATABASECHANGELOG**, phân biệt lịch sử đã triển khai với changeset đang chờ chạy, truy vấn các trường quan trọng để đối soát, và nhận diện giới hạn của history khi xảy ra rollback, rerun, migration thất bại hoặc schema drift.

## 1. Lịch sử triển khai là gì?

Trong Liquibase, mỗi changeset thường được nhận diện bằng bộ **id + author + đường dẫn changelog (filename/logicalFilePath)**. Khi changeset được xử lý theo cách cần ghi nhận lịch sử, Liquibase lưu metadata vào bảng **DATABASECHANGELOG** của database đích.

Lịch sử triển khai giúp biết:

- Changeset nào đã được Liquibase ghi nhận trên database đang kết nối.
- Thời điểm và thứ tự xử lý được lưu trong metadata.
- Kiểu xử lý, chẳng hạn **EXECUTED**, **RERAN** hoặc **MARK_RAN**.
- Đường dẫn changelog, checksum và thông tin liên quan khi cần điều tra.
- Những changeset có thể thuộc cùng một đợt triển khai qua **DEPLOYMENT_ID**, nếu metadata đó có mặt.
- Mốc tag hoặc các thuộc tính như contexts/labels, khi đã được ghi nhận.

**History không phải bản sao của toàn bộ schema.** Nó thể hiện những gì Liquibase biết về quá trình xử lý changeset; không tự chứng minh mọi bảng, cột, index và dữ liệu vẫn giống như sau lần migration.

### 1.1. Ba góc nhìn cần kết hợp

~~~mermaid
flowchart TD
    A[Artifact changelog] --> B[Liquibase update]
    B --> C[DATABASECHANGELOG]
    B --> D[Schema và dữ liệu thực tế]
    C --> E[history / truy vấn lịch sử]
    A --> F[status / validate / update-sql]
    C --> F
    D --> G[Kiểm tra catalog và dữ liệu]
    E --> H[Đối soát triển khai]
    F --> H
    G --> H
~~~

Một buổi điều tra đáng tin cậy cần ít nhất ba nguồn: **changelog/artifact đã phát hành**, **lịch sử Liquibase của đúng database** và **trạng thái schema/dữ liệu thực tế**. Mỗi nguồn phản ánh một phần sự thật khác nhau.

## 2. Phân biệt history, status, validate và update

Những lệnh này bổ sung cho nhau nhưng không thay thế nhau.

| Lệnh | Câu hỏi chính | Thay đổi schema/dữ liệu? |
|---|---|---|
| **history** | Liquibase đã ghi nhận những changeset nào trên database này? | Không nhằm áp dụng migration |
| **status --verbose** | Những changeset nào trong changelog hiện tại còn chờ áp dụng theo cấu hình/filter? | Không |
| **validate** | Changelog hiện tại có vượt qua những kiểm tra cấu trúc và checksum mà Liquibase hỗ trợ không? | Không nhằm áp dụng migration |
| **update-sql** | SQL nào được dự kiến cho lần update tiếp theo? | Chỉ xem trước, không thực thi thay đổi nghiệp vụ |
| **update** | Áp dụng những changeset cần chạy | Có |
| **rollback** | Đảo ngược những changeset theo mục tiêu rollback và khả năng hỗ trợ | Có |

**History nhìn về những thay đổi đã được ghi nhận; status nhìn về phần chưa được áp dụng trong phạm vi changelog được nạp.**

Ví dụ: changelog có A, B, C. Database đã ghi nhận A và B, còn C chưa chạy. Khi đó:

- **history** cung cấp thông tin về A và B.
- **status --verbose** có thể báo C còn pending.
- **update-sql** có thể hiển thị SQL dự kiến cho C.
- **update** áp dụng C nếu đủ điều kiện và ghi nhận kết quả thành công.

Kết quả còn chịu ảnh hưởng của context, label, DBMS, precondition và các thuộc tính chạy lại. Không nên xem history và status là hai danh sách bổ sung nhau tuyệt đối trong mọi hoàn cảnh.

## 3. Lệnh history cơ bản

Khi Liquibase đã có thông tin kết nối an toàn tới database đích, lệnh cơ bản là:

~~~bash
liquibase history
~~~

Tùy cách tổ chức dự án và phiên bản, có thể cung cấp các tham số chung, chẳng hạn:

~~~bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  history
~~~

Hoặc cấu hình URL, driver và tài khoản từ một tệp properties, biến môi trường hay secret manager phù hợp. **History phải đọc đúng database và đúng nơi lưu bảng metadata Liquibase.** Đứng trong repository đúng nhưng kết nối nhầm database vẫn cho lịch sử của database nhầm đó.

### 3.1. Các đầu vào cần xác nhận

| Thành phần | Vì sao quan trọng? |
|---|---|
| **JDBC URL / host / port** | Xác định máy chủ database |
| **Database hoặc service name** | Tránh nhầm database trên cùng một server |
| **Username và quyền đọc** | Cần truy cập metadata Liquibase |
| **Schema/catalog** | Bảng DATABASECHANGELOG có thể nằm ở schema khác schema nghiệp vụ |
| **Liquibase version** | Cú pháp CLI và cách hiển thị output có thể khác |
| **Changelog/artifact** | Cần đối soát lịch sử với đúng bản phát hành |
| **Contexts, labels và DBMS** | Có thể làm tập changeset dự kiến khác nhau giữa các lần update |

**Lưu ý:** tên cờ CLI, cách truyền thông số và hình thức output có thể khác giữa các phiên bản Liquibase. Hãy xác minh với công cụ được dùng trong pipeline thật. Trong bài này, cú pháp dòng lệnh là ví dụ cho mô hình vận hành.

### 3.2. History là thao tác quan sát

Lệnh history được dùng để **xem** lịch sử triển khai; không phải lệnh cấp quyền sửa bảng metadata hoặc đánh dấu changeset mới. Tuy nhiên, việc dùng CLI vẫn cần kết nối và quyền phù hợp; không chạy lệnh trên production bằng tài khoản quản trị có quyền quá rộng nếu một tài khoản đọc metadata đã đáp ứng nhu cầu vận hành.

Đừng dùng lệnh update chỉ để “kiểm tra lịch sử”. Nếu mục tiêu là quan sát, ưu tiên history, status và truy vấn SELECT được kiểm soát.

## 4. Đọc kết quả history đúng cách

Hình thức hiển thị của **liquibase history** phụ thuộc phiên bản và cấu hình CLI. Một số phiên bản trình bày danh sách changeset đã triển khai cùng metadata; không nên viết code tự động dựa trên độ rộng cột, số dòng tiêu đề hoặc chuỗi định dạng dành cho người đọc.

Về mặt nghiệp vụ, hãy tìm thông tin:

1. **Changeset identity:** id, author và tệp changelog.
2. **Thời điểm:** khi Liquibase ghi nhận changeset.
3. **Thứ tự:** thứ tự ghi nhận trong lịch sử.
4. **Kiểu xử lý:** chạy thực sự, chạy lại hay đánh dấu đã xử lý.
5. **Đợt triển khai:** deployment identifier hoặc metadata của pipeline nếu có.
6. **Mốc phát hành:** tag hoặc marker tương ứng nếu được quản lý.

Ví dụ bảng **minh họa khái niệm**, không phải bản chép output cố định của một phiên bản CLI:

| Changeset | FILENAME | DATEEXECUTED | EXECTYPE |
|---|---|---|---|
| orders-team:001-create-orders | db/changelog/001-create-orders.yaml | 2026-11-17 09:10 | EXECUTED |
| orders-team:002-add-status | db/changelog/002-add-status.yaml | 2026-11-18 10:40 | EXECUTED |
| reporting-team:003-refresh-view | db/changelog/003-refresh-view.sql | 2026-11-19 08:20 | RERAN |

Bảng minh họa cho thấy các lần ghi nhận có thể diễn ra vào ngày khác nhau. **DATEEXECUTED không cho biết người viết tạo changelog vào ngày nào**, cũng không nhất thiết trùng thời điểm ứng dụng mới bắt đầu nhận lưu lượng.

### 4.1. Một dòng lịch sử không luôn đồng nghĩa “SQL đã chạy”

Nếu **EXECTYPE=MARK_RAN**, changeset có thể đã được ghi nhận là xử lý theo chính sách precondition mà **không thực thi các changes bên trong**. Vì thế:

> Có bản ghi trong history không nhất thiết chứng minh đối tượng được định nghĩa bởi changeset thật sự tồn tại.

Đối với changeset quan trọng, cần truy vấn schema thực tế để xác nhận bảng, cột, index hoặc dữ liệu.

## 5. DATABASECHANGELOG: nguồn dữ liệu lịch sử cốt lõi

Liquibase dùng bảng **DATABASECHANGELOG** để lưu metadata các changeset đã được xử lý. Một số cột thông dụng:

| Cột | Ý nghĩa |
|---|---|
| **ID** | Mã changeset trong changelog |
| **AUTHOR** | Tác giả định danh |
| **FILENAME** | Đường dẫn changelog hoặc logicalFilePath dùng khi nhận diện |
| **DATEEXECUTED** | Thời điểm Liquibase ghi nhận xử lý |
| **ORDEREXECUTED** | Thứ tự chạy/ghi nhận do Liquibase lưu |
| **EXECTYPE** | Kiểu xử lý, ví dụ EXECUTED, RERAN hoặc MARK_RAN |
| **MD5SUM** | Checksum dùng kiểm tra nội dung changeset |
| **DESCRIPTION** | Mô tả change types được ghi nhận |
| **COMMENTS** | Comment hoặc mô tả của changeset nếu có |
| **TAG** | Mốc tag được lưu, nếu sử dụng |
| **LIQUIBASE** | Phiên bản Liquibase ghi nhận theo cơ chế tương ứng |
| **CONTEXTS** | Metadata context được ghi nhận |
| **LABELS** | Metadata labels được ghi nhận |
| **DEPLOYMENT_ID** | Định danh đợt triển khai theo cơ chế Liquibase |

Các cột có thể khác nhau theo phiên bản hoặc lịch sử nâng cấp metadata. Cần xem cấu trúc bảng thực tế của database đang điều tra, không giả định mọi hệ thống đều có chính xác cùng một tập cột.

### 5.1. Định danh changeset không chỉ gồm ID

Liquibase thường dùng bộ ba:

~~~text
ID + AUTHOR + FILENAME (hoặc logicalFilePath)
~~~

Giả sử ID=001 và AUTHOR=orders-team không đổi nhưng tệp được chuyển từ:

~~~text
db/changelog/001-create-orders.yaml
~~~

sang:

~~~text
db/changelog/releases/2026/11/001-create-orders.yaml
~~~

Liquibase có thể coi đó là changeset mới vì thành phần FILENAME thay đổi. Trong history, hai đường dẫn khác nhau không nên được tự động gộp thành một chỉ vì ID giống nhau.

**Quy tắc bảo trì:** giữ ổn định ID, author và đường dẫn logic của changeset đã triển khai. Nếu phải di chuyển file, cần kiểm chứng chính xác logicalFilePath và giá trị FILENAME đã lưu trên các database liên quan.

## 6. Truy vấn SELECT để kiểm chứng lịch sử

Khi cần chi tiết mà output history không hiển thị, có thể thực hiện truy vấn **chỉ đọc** trên database được phép truy cập.

Ví dụ tổng quát:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    DATEEXECUTED,
    ORDEREXECUTED,
    EXECTYPE,
    MD5SUM,
    DEPLOYMENT_ID
FROM DATABASECHANGELOG
ORDER BY DATEEXECUTED, ORDEREXECUTED;
~~~

Nếu bảng nằm trong schema metadata riêng, cần dùng tên đủ điều kiện:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    EXECTYPE,
    DATEEXECUTED
FROM liquibase_meta.DATABASECHANGELOG
ORDER BY DATEEXECUTED, ORDEREXECUTED;
~~~

Tên **liquibase_meta** chỉ là ví dụ; dùng schema/cách quote identifier phù hợp với DBMS thực tế.

### 6.1. Tại sao sắp xếp theo hai trường?

**DATEEXECUTED** ghi thời điểm; nhiều changeset có thể cùng một giá trị thời gian do độ chính xác của cột. **ORDEREXECUTED** bổ sung thông tin thứ tự ghi nhận.

Tuy nhiên, đừng dùng thứ tự này làm đồng hồ lịch sử bất biến tuyệt đối: khi rollback, chạy lại, nâng cấp phiên bản hoặc quản lý nhiều lần deployment, cách các trường được duy trì có thể khác. Nếu cần chứng minh thứ tự phát hành chính xác trong một incident, hãy kết hợp deployment log và dữ liệu lịch sử thay vì chỉ dựa vào một cột.

### 6.2. Truy vấn một changeset cụ thể

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    EXECTYPE,
    MD5SUM,
    DATEEXECUTED
FROM DATABASECHANGELOG
WHERE ID = '002-add-status'
  AND AUTHOR = 'orders-team';
~~~

Nếu cùng ID và author có thể xuất hiện trong nhiều tệp, hãy đối chiếu **FILENAME** trước khi kết luận một bản ghi khớp changeset hiện tại.

## 7. Hiểu EXECTYPE trong lịch sử

**EXECTYPE** giúp phân biệt cách Liquibase xử lý changeset. Những giá trị thường gặp:

| Giá trị | Diễn giải | Cần kiểm tra thêm |
|---|---|---|
| **EXECUTED** | Changeset được Liquibase ghi nhận thực thi | Schema và dữ liệu hiện tại còn khớp không? |
| **RERAN** | Changeset được thực thi lại theo cơ chế chạy lại | Vì sao có runOnChange/runAlways? Phiên bản định nghĩa hiện tại là gì? |
| **MARK_RAN** | Changeset được đánh dấu đã xử lý mà không chạy phần thay đổi theo chính sách được hỗ trợ | Database có thật sự ở trạng thái mong muốn không? |

Các giá trị khác có thể xuất hiện tùy phiên bản và trường hợp; không nên viết automation chỉ nhận ba giá trị nếu chưa kiểm tra nguồn dữ liệu thực tế.

### 7.1. EXECTYPE=EXECUTED có nghĩa gì?

Nó nói Liquibase ghi nhận một lần thực thi thành công theo cơ chế của nó. Nó **không phải bằng chứng bất biến** rằng người khác chưa sửa bảng sau đó hoặc dữ liệu chưa bị thay đổi bởi ứng dụng.

Ví dụ CREATE INDEX đã được ghi lịch sử thành công, nhưng sau đó DBA có thể DROP INDEX thủ công. History vẫn có thể cho biết changeset từng chạy. Muốn biết index đang tồn tại, hãy kiểm tra catalog của DBMS.

### 7.2. EXECTYPE=MARK_RAN khác gì?

Một local precondition có thể cấu hình **onFail:MARK_RAN**. Khi điều kiện không đạt, Liquibase có thể bỏ qua SQL thay đổi nhưng vẫn ghi nhận changeset đã được xử lý.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "001-create-legacy-table"
      author: "db-team"
      preConditions:
        - onFail: MARK_RAN
        - onError: HALT
        - not:
            - tableExists:
                tableName: legacy_table
      changes:
        - createTable:
            tableName: legacy_table
            columns:
              - column:
                  name: id
                  type: bigint
~~~

Nếu bảng đã tồn tại, changeset có thể được ghi MARK_RAN. **Chỉ sự tồn tại của bảng không chứng minh cấu trúc, constraint và dữ liệu đúng.** Vì vậy, khi history có MARK_RAN, cần xem lý do precondition và trạng thái thật trước khi tin rằng migration đã hoàn tất.

### 7.3. EXECTYPE=RERAN và lịch sử chạy lại

Changeset dùng **runOnChange** hoặc **runAlways** có thể chạy lại. DATABASECHANGELOG không nhất thiết thêm một dòng bất biến cho từng lần rerun; bản ghi có thể được cập nhật theo cơ chế Liquibase.

Do đó, nếu muốn kiểm toán **mọi lần** một view hoặc procedure được thay thế, không nên chỉ dựa vào history ở thời điểm hiện tại. Cần kết hợp log triển khai, artifact và hệ thống lưu sự kiện bên ngoài.

## 8. DEPLOYMENT_ID: nhóm changeset trong một đợt chạy

**DEPLOYMENT_ID** có thể giúp nhóm các changeset được Liquibase xử lý trong cùng một hoạt động triển khai. Đây là thông tin hữu ích khi cần hỏi:

> Đợt update này đã ghi nhận những changeset nào?

Ví dụ truy vấn:

~~~sql
SELECT
    DEPLOYMENT_ID,
    COUNT(*) AS recorded_changesets,
    MIN(DATEEXECUTED) AS first_recorded_at,
    MAX(DATEEXECUTED) AS last_recorded_at
FROM DATABASECHANGELOG
WHERE DEPLOYMENT_ID IS NOT NULL
GROUP BY DEPLOYMENT_ID
ORDER BY MAX(DATEEXECUTED) DESC;
~~~

Muốn xem chi tiết một đợt:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    EXECTYPE,
    DATEEXECUTED,
    ORDEREXECUTED
FROM DATABASECHANGELOG
WHERE DEPLOYMENT_ID = 'EXAMPLE_DEPLOYMENT_ID'
ORDER BY ORDEREXECUTED;
~~~

**EXAMPLE_DEPLOYMENT_ID** là chỗ giữ chỗ; thay bằng giá trị đã đọc từ database đích.

### 8.1. Không đồng nhất deployment ID với release của ứng dụng

Một release có thể có nhiều lượt Liquibase update: mở rộng schema, triển khai ứng dụng, rồi hoàn thiện ràng buộc. Ngược lại, một lần Liquibase update có thể xử lý nhiều changeset thuộc các tính năng khác nhau.

Do đó, hãy ghi **deployment ID** cùng với **release ID, commit hash, pipeline run ID, môi trường và người phê duyệt** trong nhật ký CI/CD. Đó là cách truy vết từ lịch sử database tới thay đổi ứng dụng.

### 8.2. Hạn chế của DEPLOYMENT_ID

- Bản ghi cũ có thể không có trường hoặc không có giá trị này.
- Những changeset từng chạy lại có thể không để lại danh sách đầy đủ mọi lượt chạy trong bảng hiện tại.
- Những hoạt động thất bại trước khi ghi lịch sử có thể không tạo bản ghi tương ứng.
- Deployment ID tự nó không chứng minh artifact, Git commit hay cấu hình JDBC được sử dụng.

## 9. TAG: mốc lịch sử có chủ đích

Liquibase hỗ trợ **tagging** để đánh dấu một trạng thái triển khai bằng tên dễ nhận biết, chẳng hạn **release_2026_11**. Mốc tag có thể được dùng trong quy trình rollback tới một mốc phù hợp.

Ví dụ thao tác ở mức khái niệm:

~~~bash
liquibase tag release_2026_11
~~~

Cách lưu tag và cú pháp CLI có thể khác giữa các phiên bản hoặc phương thức như lệnh **tag** và change type **tagDatabase**. Khi đối soát history, có thể kiểm tra cột **TAG** nếu metadata đó có mặt.

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    TAG,
    DATEEXECUTED
FROM DATABASECHANGELOG
WHERE TAG IS NOT NULL
ORDER BY DATEEXECUTED, ORDEREXECUTED;
~~~

**Tag không phải label.** Label là metadata giúp lọc changeset; tag là mốc trong lịch sử triển khai. Đừng dùng một thay cho cái còn lại.

### 9.1. Tag không phải backup

Tag giúp Liquibase xác định mốc rollback theo quy trình, nhưng nó không lưu toàn bộ dữ liệu hoặc schema dưới dạng snapshot. Nếu rollback tới tag dẫn tới DROP TABLE, dữ liệu có thể bị mất. Với thay đổi rủi ro cao, cần backup/restore và kế hoạch phục hồi đã được thử nghiệm.

### 9.2. Tag không chứng minh đồng bộ giữa ứng dụng và database

Một tag tên **release_2026_11** có thể có trên database, nhưng ứng dụng đang chạy có thể ở bản khác. Khi điều tra tương thích, hãy đối chiếu deployment record và phiên bản ứng dụng thực tế.

## 10. History và checksum

**MD5SUM** là trường lưu checksum của changeset theo thuật toán, định dạng và phiên bản Liquibase tương ứng. Nó hỗ trợ phát hiện thay đổi nội dung hoặc cấu hình có liên quan tới checksum sau khi changeset được ghi nhận.

Ví dụ một changeset tạo cột đã chạy:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "002-add-status"
      author: "orders-team"
      changes:
        - addColumn:
            tableName: orders
            columns:
              - column:
                  name: status
                  type: varchar(24)
~~~

Nếu người viết sau đó sửa nội dung changeset cũ thành kiểu hoặc tên cột khác, Liquibase có thể phát hiện mismatch khi validate/update.

**History tự nó không tự kiểm định checksum trên artifact hiện tại.** Cần dùng những lệnh kiểm tra phù hợp, ví dụ **validate**, và so sánh với changelog đã triển khai.

### 10.1. Không dùng checksum như dấu vân tay đầy đủ của schema

Hai database cùng lưu checksum của một changeset không chứng minh schema hiện tại hoàn toàn giống nhau. Sau migration, có thể có:

- Thay đổi DDL thủ công.
- Thay đổi dữ liệu của ứng dụng.
- Tác động của các changeset khác.
- Context, label hoặc precondition làm tập changeset khác nhau.
- Khác biệt DBMS hoặc phiên bản generator SQL.

Checksum giúp bảo vệ **định nghĩa changeset**, không phải chứng thực toàn bộ trạng thái database.

### 10.2. Đừng sửa history để che mismatch

Nếu phát hiện checksum mismatch:

1. Xác định artifact nào đã từng triển khai.
2. So sánh định nghĩa changeset cũ và mới.
3. Kiểm tra ID, AUTHOR, FILENAME/logicalFilePath.
4. Xác minh schema/data thực tế.
5. Thông thường tạo **changeset mới** cho thay đổi bổ sung.
6. Chỉ dùng cơ chế quản lý checksum đặc biệt khi đã hiểu và kiểm chứng hậu quả.

Không xóa hay cập nhật MD5SUM trong DATABASECHANGELOG thủ công chỉ để cho pipeline chạy tiếp.

## 11. Rollback tác động tới lịch sử như thế nào?

**Rollback của Liquibase** khác với rollback transaction của DBMS. Đây là thao tác chủ đích áp dụng thay đổi đảo ngược theo một điểm đích, ví dụ rollback đến tag hoặc số lượng changeset phù hợp.

Khi rollback một changeset, Liquibase thường cập nhật trạng thái quản lý bằng cách **gỡ bản ghi changeset tương ứng khỏi DATABASECHANGELOG** nếu rollback thành công. Vì vậy, lần gọi history sau rollback có thể **không còn hiển thị changeset từng tồn tại trước đó**.

Điều này có hệ quả rất quan trọng:

> **DATABASECHANGELOG không phải một nhật ký append-only lưu vĩnh viễn mọi lần áp dụng và mọi lần rollback.**

Nếu đội vận hành cần biết “changeset X đã chạy ngày thứ Hai, bị rollback thứ Ba, rồi chạy lại thứ Tư”, phải dựa vào log triển khai, sự kiện pipeline hoặc một hệ thống audit riêng ngoài trạng thái hiện tại của DATABASECHANGELOG.

### 11.1. Tình huống minh họa

Changelog có ba changeset:

~~~text
A: create_orders
B: add_status
C: add_status_index
~~~

Sau update, history có thể thể hiện A, B, C. Nếu rollback C thành công, history có thể chỉ còn A, B. Lần update tiếp theo có thể xem C là pending và thực thi lại nếu điều kiện phù hợp.

**Không được suy luận C “chưa từng chạy” chỉ vì nó vắng mặt trong history sau rollback.**

### 11.2. Rollback SQL có thể phá hủy dữ liệu

Nếu rollback dùng DROP COLUMN hoặc DROP TABLE, dữ liệu có thể bị mất. History có thể ghi nhận trạng thái quản lý sau rollback, nhưng không khôi phục dữ liệu đã mất. Phải kiểm tra phương án rollback hoặc forward fix và dữ liệu trước khi thực hiện trên production.

## 12. Migration thất bại có thể không xuất hiện trong history

Đây là giới hạn quan trọng khi điều tra sự cố.

Giả sử changeset chứa:

~~~sql
ALTER TABLE orders ADD COLUMN status VARCHAR(24);
UPDATE orders SET status = 'NEW' WHERE status IS NULL;
ALTER TABLE orders ADD CONSTRAINT chk_status CHECK (status IN ('NEW','DONE'));
~~~

Nếu lệnh cuối thất bại:

- Trên DBMS có transactional DDL trong cùng transaction hợp lệ, các thay đổi chưa commit có thể được rollback.
- Trên DBMS có implicit commit DDL, cột mới có thể đã tồn tại dù changeset chưa được ghi nhận thành công.
- Nếu Liquibase chưa ghi dòng EXECUTED, **history có thể không thể hiện lần thay đổi dở dang ấy**.

Vì vậy, **history trống hoặc không có ID không chứng minh database chưa thay đổi**.

### 12.1. Quy trình điều tra an toàn

1. Dừng các bước phát hành phụ thuộc.
2. Xác nhận database và schema đã kết nối.
3. Thu thập log lỗi và SQL thực tế đã thực thi, nếu có.
4. Dùng history hoặc SELECT trên DATABASECHANGELOG để biết trạng thái ghi nhận.
5. Kiểm tra bảng, cột, index, constraint và dữ liệu hiện tại bằng catalog/truy vấn phù hợp.
6. Xác định loại DBMS và hành vi transaction/implicit commit.
7. Thiết kế bước sửa chữa hoặc khôi phục được review.
8. Không ép Liquibase chạy lại bằng cách sửa lịch sử trước khi biết trạng thái thật.

## 13. Khác biệt giữa history của development, staging và production

Cùng một changelog có thể cho lịch sử khác nhau trên từng môi trường. Nguyên nhân có thể là:

- Lịch triển khai không giống nhau.
- Context hoặc label filter được chọn khác nhau.
- Changeset có **dbms** chỉ chạy trên một loại DBMS.
- Precondition cho phép MARK_RAN ở môi trường này nhưng EXECUTED ở môi trường khác.
- Một changeset đã rollback hoặc được áp dụng lại.
- Artifact hoặc đường dẫn changelog bị thay đổi qua các đợt phát hành.
- Có thao tác migration thủ công ngoài Liquibase.

Bởi vậy, đừng kết luận “production chậm hơn staging hai bản migration” chỉ bằng cách so sánh **số dòng** trong DATABASECHANGELOG.

### 13.1. So sánh danh tính chứ không chỉ số lượng

Một bảng đối chiếu khái niệm:

| Changeset | Dev | Staging | Production |
|---|---|---|---|
| A — create_orders | EXECUTED | EXECUTED | EXECUTED |
| B — add_status | EXECUTED | EXECUTED | EXECUTED |
| C — backfill_status | EXECUTED | MARK_RAN | Chưa ghi nhận |
| D — add_index | EXECUTED | Chưa ghi nhận | Chưa ghi nhận |

Bảng trên chỉ mô tả **trạng thái ghi nhận**. Cần xem lý do C ở staging là MARK_RAN và kiểm tra dữ liệu trước khi khẳng định staging đã đạt cùng trạng thái schema như development.

### 13.2. Checklist khi đối chiếu hai môi trường

- Xác nhận URL, database, metadata schema và user.
- Dùng cùng artifact changelog hoặc ghi lại khác biệt artifact.
- So sánh theo **ID + AUTHOR + FILENAME/logicalFilePath**.
- So sánh EXECTYPE và ngày ghi nhận.
- Xem contexts/labels và các filter đã dùng.
- Xem tag, deployment ID và log pipeline.
- Kiểm tra sự tồn tại và định nghĩa của các đối tượng quan trọng.
- Không sửa DATABASECHANGELOG để các bảng “trông giống nhau”.

## 14. History khi dùng nhiều schema hoặc tên bảng metadata tùy chỉnh

Một hệ thống có thể đặt bảng Liquibase ở schema riêng thay vì schema nghiệp vụ. Ví dụ:

~~~text
public.orders
public.customer
liquibase_meta.DATABASECHANGELOG
liquibase_meta.DATABASECHANGELOGLOCK
~~~

Nếu cấu hình metadata thay đổi, Liquibase history có thể truy cập bảng khác với bảng mà người vận hành đang xem bằng SQL.

Cần phân biệt:

- **Default schema:** nơi một số thay đổi nghiệp vụ nhắm tới theo cấu hình.
- **Liquibase schema:** nơi lưu các bảng metadata của Liquibase.
- **Database/catalog:** container logic lớn hơn, tùy hệ quản trị.
- **Tên bảng metadata tùy chỉnh:** một số dự án đổi tên DATABASECHANGELOG hoặc DATABASECHANGELOGLOCK.

Không suy đoán rằng thấy bảng DATABASECHANGELOG ở **public** là đủ kết luận đó là bảng Liquibase ứng dụng đang sử dụng. Hãy xác minh cấu hình **liquibaseSchemaName**, databaseChangeLogTableName hoặc các tùy chọn tương ứng của phiên bản đang chạy.

### 14.1. Đừng nhầm hai bảng metadata

**DATABASECHANGELOG** lưu trạng thái changeset.

**DATABASECHANGELOGLOCK** dùng để phối hợp việc chạy migration, ngăn nhiều tiến trình Liquibase cùng cập nhật không kiểm soát.

Một bản ghi lock không phải bản ghi lịch sử changeset và không có nghĩa một DDL đã commit. Nếu cần xử lý lock sau lỗi, phải kiểm tra tiến trình hiện tại; không mở khóa thủ công chỉ vì history chưa có changeset mới.

## 15. History trong Spring Boot

Ứng dụng Spring Boot có thể chạy Liquibase khi khởi động, dựa vào dependency và cấu hình được bật.

Ví dụ:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db-staging.internal:5432/orders
    username: orders_migrator
    password: "<inject-at-runtime>"
    driver-class-name: org.postgresql.Driver

  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    default-schema: public
~~~

Đây là cấu hình minh họa, không dùng password thật. Trong hệ thống cần phân quyền chặt, có thể cấu hình datasource riêng cho Liquibase hoặc chạy migration như một job độc lập.

### 15.1. Khi ứng dụng khởi động không thành công

Giả sử Spring Boot lỗi startup vì một changeset không thực thi được. Đừng chỉ dựa vào stack trace hoặc history để kết luận database chưa đổi:

1. Xác định tên changeset trong lỗi.
2. Chạy history hoặc truy vấn DATABASECHANGELOG bằng kết nối đã được xác nhận.
3. Kiểm tra schema thực tế nếu DBMS có DDL tự commit.
4. Xác định changeset có runInTransaction:false hay cơ chế rollback đặc biệt không.
5. Khắc phục một cách có kiểm soát trước khi cho các instance tự động khởi động lại hàng loạt.

Ứng dụng startup lại không phải là cơ chế phục hồi tự động cho mọi DDL dở dang.

### 15.2. Cấu hình kết nối nhất quán

Đối với history, cần đảm bảo CLI bạn dùng để điều tra đang trỏ vào **cùng database và cùng metadata schema** mà Spring Boot đã dùng. Nếu Spring Boot chạy với một datasource riêng cho Liquibase, việc truy vấn bằng datasource ứng dụng có thể dẫn tới kết quả thiếu hoặc nhầm nguồn.

## 16. History trong CI/CD

Một pipeline tốt cần lưu **bằng chứng của lần triển khai** thay vì chỉ ghi “Liquibase succeeded”.

Trước update, pipeline có thể:

1. Xác nhận target environment, URL và migration account.
2. Ghi artifact/commit hash, Liquibase version và bộ filter.
3. Chạy validate.
4. Chạy history hoặc truy vấn lịch sử để lấy trạng thái ban đầu.
5. Chạy status --verbose để xem pending.
6. Chạy update-sql để review SQL sắp thực thi.

Sau update:

1. Chạy history lần nữa với cùng kết nối.
2. Đối chiếu tập changeset mới được ghi nhận.
3. Kiểm tra EXECTYPE, thời điểm và deployment ID.
4. Kiểm tra những đối tượng dữ liệu quan trọng.
5. Lưu log đã lọc secret để điều tra về sau.

### 16.1. Bảng đối soát trước/sau triển khai

| Kiểm tra | Trước update | Sau update |
|---|---|---|
| Database và metadata schema | Xác nhận endpoint | Xác nhận không đổi |
| Artifact changelog | Phiên bản được phê duyệt | Chính artifact đã áp dụng |
| History | Danh sách thay đổi đã ghi nhận | Xem những thay đổi mới |
| Status | Các changeset còn pending | Xác nhận tập pending phù hợp |
| EXECTYPE | Trạng thái các changeset cũ | Kiểm tra EXECUTED/MARK_RAN/RERAN |
| SQL dự kiến | Đã review | Đối chiếu với log và schema thật |
| Metadata của đợt chạy | Pipeline run ID, release | Deployment ID và thời gian |
| Dữ liệu/schema thực tế | Baseline | Kiểm tra hậu triển khai |

**Không nên coi số bản ghi tăng lên đúng bằng số changeset dự kiến là tiêu chí duy nhất.** Các changeset có runAlways/runOnChange, MARK_RAN hoặc những trường hợp không được chọn theo filter có thể làm kết quả khác dự đoán.

## 17. Lưu bằng chứng history mà không lộ dữ liệu nhạy cảm

Lịch sử triển khai không thường chứa mật khẩu của database, nhưng có thể chứa:

- Hostname và tên database nội bộ trong log CLI.
- Đường dẫn tệp và tên miền nghiệp vụ.
- Comments của changeset.
- Label/context dùng trong quy trình nội bộ.
- Mã triển khai, người thực hiện hoặc thời điểm.

Khi lưu logs của history vào hệ thống CI/CD:

- Không truyền password trực tiếp trên command line nếu shell history hoặc process list có thể đọc được.
- Dùng secret manager hoặc nguồn cấu hình bảo mật thích hợp.
- Chỉ cấp quyền đọc history cho người cần biết.
- Chỉ lưu trường metadata cần thiết để đối soát.
- Áp dụng retention và phân quyền log theo chính sách.
- Không dùng tên changeset hoặc comments để chứa dữ liệu bí mật.

Nếu cần xuất lịch sử ra định dạng máy đọc được, hãy kiểm tra các tùy chọn output thật của phiên bản Liquibase hoặc dùng truy vấn SELECT có kiểm soát. Không viết parser production dựa vào khoảng trắng trong output CLI dành cho người đọc.

## 18. Khi nào cần truy vấn catalog thay vì chỉ history?

History cho biết Liquibase đã ghi nhận gì. Truy vấn catalog giúp trả lời **schema hiện tại có gì**.

### PostgreSQL: bảng và cột

~~~sql
SELECT
    table_schema,
    table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name = 'orders';
~~~

~~~sql
SELECT
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'orders'
ORDER BY ordinal_position;
~~~

### PostgreSQL: index

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_catalog.pg_indexes
WHERE schemaname = 'public'
  AND tablename = 'orders';
~~~

Đây là truy vấn đọc metadata, không sửa schema. Với MySQL, Oracle, SQL Server hoặc DBMS khác, dùng catalog tương ứng.

**Ví dụ điều tra:** history cho biết changeset **add_index** là EXECUTED, nhưng truy vấn catalog không thấy index. Có thể index bị xóa thủ công, changeset khác đã thay đổi schema hoặc đang xem sai database/schema. Không khắc phục bằng cách xóa bản ghi history trước khi xác định nguyên nhân.

## 19. Khi nào cần xem changelog hiện tại bên cạnh history?

History chỉ ghi nhận **định danh và một số metadata**. Muốn biết SQL/DDL nào được thiết kế, cần xem changelog artifact tương ứng.

Giả sử history có:

~~~text
ID=003-refresh-customer-view
AUTHOR=reporting-team
FILENAME=db/changelog/views/customer-view.sql
EXECTYPE=RERAN
~~~

Người điều tra cần hỏi:

- Tệp view được triển khai ở phiên bản nào?
- Changeset có runOnChange hoặc runAlways không?
- SQL định nghĩa view hiện tại là gì?
- Có lần rerun nào bị mất thông tin khỏi bảng metadata trạng thái không?
- View thực tế trong database có khớp định nghĩa mong đợi không?

Khi artifact đã thay đổi sau lần chạy, chỉ đọc bản HEAD của Git không nhất thiết phản ánh SQL mà production đã nhận. Nên lưu commit hash/artifact trong log phát hành.

## 20. Những trường hợp history dễ gây hiểu nhầm

| Quan sát | Kết luận vội vàng | Cách hiểu đúng |
|---|---|---|
| History có changeset X | X chắc chắn còn nguyên trên schema | Cần kiểm tra catalog; có thể có drift |
| History không có X | X chưa từng tác động database | Có thể đã rollback hoặc chạy dở dang |
| EXECTYPE=MARK_RAN | SQL của X đã chạy thành công | Có thể đã được đánh dấu mà không chạy changes |
| EXECTYPE=RERAN | Có thêm một bản ghi riêng cho mọi lần rerun | Cần log riêng để kiểm toán từng lượt |
| Cùng số lượng dòng giữa hai môi trường | Hai môi trường đồng nhất | Cần so sánh identity, EXECTYPE, filter và schema |
| Thấy TAG=release_2026_11 | Có thể khôi phục toàn bộ dữ liệu release | Tag không phải backup |
| Không thấy changeset mới sau update | Update chắc chắn thất bại | Có thể không có pending hoặc bị filter |
| DATEEXECUTED mới | Đây là thời điểm tạo file | Chỉ là thời điểm Liquibase ghi nhận |
| Cùng checksum | Schema không có khác biệt | Checksum không phải snapshot schema |
| DEPLOYMENT_ID giống nhau | Ứng dụng và database cùng release | Cần mapping pipeline và artifact |
| History trống | Database chưa từng dùng Liquibase | Có thể sai metadata schema/table hoặc history đã được thay đổi |

## 21. Xử lý khi history không hiển thị changeset mong đợi

Thực hiện lần lượt:

**Bước 1 — Xác minh đích kết nối.** Kiểm tra host, database/service, schema và user. Đây là lỗi phổ biến nhất khi history khác kỳ vọng.

**Bước 2 — Xác minh vị trí metadata.** Bảng DATABASECHANGELOG có thể nằm trong schema khác hoặc có tên tùy chỉnh.

**Bước 3 — Xác minh định danh.** So sánh ID, AUTHOR, FILENAME/logicalFilePath. Đổi đường dẫn file có thể làm xuất hiện identity khác.

**Bước 4 — Xác minh tập changelog.** Tệp có được include vào changelog gốc không? Có phải SQL file chỉ được tham chiếu từ một changeset bao ngoài?

**Bước 5 — Xem filter.** Context, label và dbms có khiến changeset chưa được chọn không?

**Bước 6 — Kiểm tra trạng thái thực.** Nếu lỗi xảy ra, database có thể đã thay đổi một phần dù không có bản ghi trong history.

**Bước 7 — Kiểm tra rollback và rerun.** Changeset có bị rollback, chạy lại hoặc được ghi MARK_RAN không?

**Bước 8 — Đối chiếu log phát hành.** Dùng pipeline run ID, deployment ID, artifact và log trước/sau để tái dựng sự kiện.

Không xóa hoặc sửa DATABASECHANGELOG khi chưa có kế hoạch reconciliation đã được kiểm chứng.

## 22. Xử lý khi history khác giữa các môi trường

Giả sử staging có changeset **003-create-report-view** nhưng production không có.

Một quy trình đáng tin cậy:

1. Xác định đúng database, schema metadata và artifact ở hai môi trường.
2. Dùng history hoặc SELECT để so sánh bộ ID/AUTHOR/FILENAME.
3. Xem context/label filter hoặc DBMS-specific changeset.
4. Kiểm tra deployment log xem production đã được lên lịch áp dụng chưa.
5. Xem changeset 003 có phụ thuộc những migration trước không.
6. Chạy status --verbose trên production với filter dự kiến.
7. Chạy update-sql và kiểm tra SQL trước khi triển khai.
8. Kiểm chứng trên môi trường thử nghiệm đại diện.
9. Chỉ thực thi sau khi được phê duyệt.

Không sao chép trực tiếp dòng history từ staging sang production. DATABASECHANGELOG là trạng thái quản lý của chính database đích, không phải file dữ liệu cần đồng bộ thủ công.

## 23. Bài thực hành: quan sát history trước và sau update

**Bối cảnh:** Một database PostgreSQL dành riêng cho học tập, chưa có bảng **training_orders**. Dự án dùng Liquibase để quản lý hai changeset.

Changelog minh họa:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "practice-001-create-orders"
      author: "training-team"
      dbms: postgresql
      changes:
        - createTable:
            tableName: training_orders
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: order_status
                  type: varchar(24)
      rollback:
        - dropTable:
            tableName: training_orders

  - changeSet:
      id: "practice-002-add-order-index"
      author: "training-team"
      dbms: postgresql
      changes:
        - createIndex:
            tableName: training_orders
            indexName: idx_training_orders_status
            columns:
              - column:
                  name: order_status
      rollback:
        - dropIndex:
            tableName: training_orders
            indexName: idx_training_orders_status
~~~

**Điều kiện:** chỉ chạy trên database thử nghiệm được phép thao tác; xác nhận không có đối tượng tên **training_orders**, và có quyền CREATE/INDEX/DROP phù hợp.

### 23.1. Bước 1: xem trạng thái ban đầu

~~~bash
liquibase history
liquibase --changelog-file=db/changelog/training.yaml status --verbose
~~~

Ghi lại:

- Những changeset đã có sẵn trong history.
- Hai changeset thực hành có đang pending không.
- Database và metadata schema đang kết nối.

Nếu database đã dùng Liquibase từ trước, history có thể chứa các changeset khác; không yêu cầu nó phải hoàn toàn trống.

### 23.2. Bước 2: validate và xem SQL trước khi chạy

~~~bash
liquibase --changelog-file=db/changelog/training.yaml validate
liquibase --changelog-file=db/changelog/training.yaml update-sql
~~~

Xác nhận SQL tạo bảng xuất hiện trước SQL tạo index. Nếu có changeset khác xuất hiện ngoài ý muốn, không tiếp tục update.

### 23.3. Bước 3: thực thi trên database thử nghiệm

~~~bash
liquibase --changelog-file=db/changelog/training.yaml update
~~~

Sau khi lệnh hoàn tất, chạy:

~~~bash
liquibase history
liquibase --changelog-file=db/changelog/training.yaml status --verbose
~~~

Kỳ vọng: Liquibase đã ghi nhận hai changeset thực hành; nếu chúng không còn pending thì status tương ứng sẽ phản ánh điều đó.

### 23.4. Bước 4: đối chiếu DATABASECHANGELOG

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    DATEEXECUTED,
    ORDEREXECUTED,
    EXECTYPE,
    DEPLOYMENT_ID
FROM DATABASECHANGELOG
WHERE AUTHOR = 'training-team'
  AND ID IN (
      'practice-001-create-orders',
      'practice-002-add-order-index'
  )
ORDER BY DATEEXECUTED, ORDEREXECUTED;
~~~

Ghi nhận identity, EXECTYPE và DEPLOYMENT_ID. Nếu metadata schema khác, thay tên bảng tương ứng. Sau đó xác minh bảng và index thực sự tồn tại bằng catalog của PostgreSQL.

### 23.5. Bước 5: chạy lại history, không chạy lại SQL tùy tiện

Khi update lần nữa với cùng changelog và điều kiện, hai changeset đã ghi nhận thường không chạy lại. Dùng history và status để quan sát.

Nếu có thời gian trong môi trường thử nghiệm, người học có thể thiết kế bài rollback đến mốc đã kiểm chứng, rồi quan sát sự thay đổi của DATABASECHANGELOG. **Không chạy rollback trên production và không thử với bảng chứa dữ liệu cần giữ.**

### 23.6. Kết quả học tập cần ghi lại

- Trước update: changeset nào pending?
- Sau update: changeset nào được history ghi nhận?
- EXECTYPE có giống kỳ vọng không?
- Có deployment ID để nhóm hai changeset không?
- Changelog artifact, history và schema thật có khớp không?
- Nếu rollback một changeset, history có còn là bản ghi đầy đủ mọi sự kiện quá khứ không?

## 24. Bài thực hành nâng cao: điều tra history gây hiểu nhầm

**Tình huống giả lập:** trên staging, history có:

~~~text
ID       = 004-add-customer-status
AUTHOR   = customer-team
FILENAME = db/changelog/customer/004-status.yaml
EXECTYPE = MARK_RAN
~~~

Trong khi đó, bảng **customer** không có cột **status**.

### Yêu cầu

1. Có thể kết luận migration đã tạo cột thành công không?
2. Cần xem chi tiết gì trong changelog và precondition?
3. Có nên chỉnh EXECTYPE thành EXECUTED hoặc xóa dòng lịch sử không?
4. Cần xử lý thế nào để đưa database về trạng thái đúng?

### Gợi ý giải thích

**Không thể kết luận cột đã được tạo.** MARK_RAN có thể nghĩa là Liquibase đã đánh dấu changeset theo policy mà không chạy phần thay đổi. Cần xem điều kiện nào dẫn tới MARK_RAN và vì sao metadata/schema không tương đương.

Không chỉnh trực tiếp DATABASECHANGELOG. Trước tiên đối chiếu artifact, catalog và các lần triển khai; sau đó thiết kế bước sửa chữa được thử nghiệm trên bản sao database, có phê duyệt phù hợp.

Đây là ví dụ tiêu biểu cho sự khác biệt giữa **lịch sử do Liquibase quản lý** và **trạng thái dữ liệu/schema thực tế**.

## 25. Các câu hỏi tự kiểm tra

**1. history và status --verbose khác nhau thế nào?**

History cho biết những changeset Liquibase đã ghi nhận trên database; status giúp xác định changeset còn chờ áp dụng trong phạm vi changelog và filter hiện tại.

**2. Lệnh history có phải cách để triển khai những changeset đang pending không?**

Không. History là để xem lịch sử; update mới là thao tác áp dụng thay đổi.

**3. Vì sao cần xác nhận JDBC URL trước khi đọc history?**

Vì history phản ánh database đang kết nối. Sai URL có thể khiến kết quả có vẻ đúng định dạng nhưng hoàn toàn không thuộc môi trường cần điều tra.

**4. Một dòng EXECTYPE=MARK_RAN có chứng minh SQL đã chạy không?**

Không. Nó có thể được ghi mà không thực thi các changes bên trong.

**5. Cùng ID và author nhưng khác FILENAME có nhất thiết là cùng một changeset không?**

Không. Liquibase thường dùng cả đường dẫn changelog hoặc logicalFilePath để định danh.

**6. Vì sao DATABASECHANGELOG không phải audit log bất biến?**

Vì rollback có thể gỡ bản ghi, và những changeset chạy lại có thể cập nhật metadata. Nó thể hiện trạng thái do Liquibase đang quản lý, không nhất thiết lưu mọi sự kiện lịch sử.

**7. Changelog có bản ghi EXECUTED nhưng index không còn thì điều gì có thể xảy ra?**

Index có thể đã bị xóa thủ công, bị thay đổi ở migration khác hoặc người vận hành đang xem sai database/schema. Cần kiểm tra catalog và log.

**8. DEPLOYMENT_ID có thay thế release ID của ứng dụng không?**

Không. Deployment ID nhóm một số thay đổi do Liquibase ghi nhận, còn release ứng dụng có thể bao gồm nhiều bước và artifact khác.

**9. History có chứng minh SQL dự kiến sẽ chạy khi update tiếp theo không?**

Không. Cần dùng status và update-sql với changelog và filter phù hợp.

**10. History không có changeset X có chắc chắn X chưa từng tác động database?**

Không. Có thể rollback hoặc thất bại sau khi DDL đã commit một phần.

**11. Tag có phải backup không?**

Không. Tag là mốc lịch sử; khôi phục dữ liệu cần phương án rollback, backup hoặc forward fix phù hợp.

**12. Tại sao cần giữ artifact/commit hash trong báo cáo CI/CD?**

Vì history không chứa toàn bộ định nghĩa SQL đã dùng cho từng lần triển khai; artifact giúp đối chiếu thay đổi chính xác.

## 26. Checklist dùng history trong vận hành thực tế

- [ ] Đã xác nhận host, database, schema và tài khoản kết nối.
- [ ] Đã xác nhận vị trí/tên DATABASECHANGELOG đang được Liquibase sử dụng.
- [ ] Đã dùng history để xem trạng thái đã triển khai, không dùng update để quan sát.
- [ ] Phân biệt rõ history với status, validate và update-sql.
- [ ] Khi truy vấn SQL, dùng SELECT có kiểm soát và không chỉnh metadata thủ công.
- [ ] Đối chiếu ID, AUTHOR và FILENAME/logicalFilePath, không chỉ ID.
- [ ] Đọc đúng ý nghĩa EXECTYPE, đặc biệt MARK_RAN và RERAN.
- [ ] Không coi DATEEXECUTED là ngày tạo changeset hoặc bằng chứng bất biến về mọi lần chạy.
- [ ] Xem DEPLOYMENT_ID cùng pipeline run ID và artifact đã phát hành.
- [ ] Phân biệt TAG với labels và backup.
- [ ] Không coi checksum là ảnh chụp toàn bộ schema.
- [ ] Hiểu rollback có thể thay đổi các dòng DATABASECHANGELOG.
- [ ] Khi history thiếu changeset, kiểm tra khả năng DDL đã chạy dở dang.
- [ ] Khi nhiều môi trường khác nhau, so sánh identity, filter và schema thực tế.
- [ ] Đã chạy status và update-sql trước khi áp dụng migration mới.
- [ ] Đã kiểm tra catalog và dữ liệu sau các changeset quan trọng.
- [ ] Có log CI/CD và artifact được lưu phù hợp để kiểm toán từng lần triển khai.
- [ ] Bảo vệ secret và giới hạn quyền đọc log history.
- [ ] Không sử dụng history để tự ý thay đổi DATABASECHANGELOGLOCK.
- [ ] Bất thường giữa history và schema được điều tra, thử nghiệm sửa chữa rồi mới phê duyệt.

**Kết luận:** Lệnh **liquibase history** là công cụ căn bản để nhìn lại những changeset Liquibase đã ghi nhận trên **đúng database đích**. Khi hiểu **DATABASECHANGELOG**, EXECTYPE, FILENAME, checksum, tag và deployment ID, người vận hành có thể đối soát phát hành và nhận diện sai lệch giữa các môi trường. Tuy vậy, history phản ánh **trạng thái lịch sử do Liquibase quản lý**, không phải audit log bất biến hay bằng chứng đầy đủ về schema. Một quy trình kiểm chứng tin cậy phải kết hợp **history + status/update-sql + artifact changelog + kiểm tra schema/dữ liệu thật**, đặc biệt sau rollback, rerun hoặc migration thất bại.

