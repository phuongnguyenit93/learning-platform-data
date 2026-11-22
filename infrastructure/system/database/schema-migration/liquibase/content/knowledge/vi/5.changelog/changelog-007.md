# Quy ước tên tệp và duy trì cấu trúc dễ kiểm tra

Khi dự án dùng Liquibase trong thời gian dài, số lượng changelog và changeset có thể tăng từ vài tệp lên hàng trăm tệp. Nếu tên tệp mơ hồ, thay đổi cũ bị di chuyển tùy tiện hoặc thứ tự include thiếu kiểm soát, một migration vốn đúng về SQL vẫn có thể khó review, khó triển khai lại và khó đối chiếu với lịch sử trong database. Quy ước tên tệp và cấu trúc thư mục là một phần của khả năng vận hành migration, không chỉ là vấn đề thẩm mỹ của repository.

Bài học thuộc chương **Changelog** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Mục tiêu của module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Sau bài học, bạn có thể thiết kế quy ước tên tệp ổn định, tổ chức changelog gốc và changelog con, lựa chọn giữa **include** và **includeAll**, hiểu tác động của việc đổi tên hoặc di chuyển tệp đã triển khai, và xây dựng quy trình review để đội phát triển dễ nhận diện những thay đổi chuẩn bị áp dụng.

## 1. Phân biệt tệp changelog với changeset

Trong Liquibase:

- **Changelog** là tệp mô tả hoặc tham chiếu đến các thay đổi database. Một changelog có thể chứa nhiều changeset hoặc include các changelog khác.
- **Changeset** là đơn vị thay đổi được Liquibase theo dõi. Changeset thường có **id**, **author**, các thao tác thay đổi và có thể khai báo rollback, precondition, context hoặc label.
- **Changelog gốc** là điểm vào của Liquibase khi thực thi; nó có thể điều phối thứ tự đọc changelog con.
- **DATABASECHANGELOG** là bảng lưu lịch sử changeset đã được xử lý trong database đích.

Điều quan trọng là định danh mà Liquibase sử dụng cho changeset dựa vào bộ **id + author + đường dẫn tệp changelog (filename/logicalFilePath)**. Đổi đường dẫn tệp có thể làm Liquibase xem changeset cũ như một changeset khác, ngay cả khi nội dung SQL không thay đổi.

Vì vậy, tên tệp có hai vai trò đồng thời:

1. Giúp người đọc biết migration dùng để làm gì, được thêm vào giai đoạn nào và cần review phần nào.
2. Góp phần duy trì danh tính changeset trong lịch sử triển khai khi đường dẫn tệp được dùng trong định danh.

Không nên xem việc đổi tên hoặc dời tệp đã triển khai là thao tác chỉnh sửa thuần túy.

## 2. Tiêu chí của một quy ước đặt tên tốt

Một quy ước hữu ích cần đáp ứng các tiêu chí:

| Tiêu chí | Ý nghĩa thực tế |
|---|---|
| Dễ tìm kiếm | Có thể tìm migration bằng bảng, nghiệp vụ hoặc loại thay đổi. |
| Dễ sắp xếp | Thứ tự tên dễ nhận biết; tránh thứ tự khó hiểu như 1, 10, 2. |
| Đủ ổn định | Không phải đổi tên chỉ vì chuyển giai đoạn phát hành hoặc thay đổi người phụ trách. |
| Phân biệt được nội dung | Người review nhìn tên biết đây là tạo bảng, thêm cột, cập nhật dữ liệu hay lập chỉ mục. |
| Hạn chế xung đột nhóm | Giảm nguy cơ hai nhánh độc lập cùng đặt một tên hoặc một changeset ID. |
| Phù hợp định dạng | Phần mở rộng phản ánh đúng YAML, XML, JSON hoặc formatted SQL. |
| Hoạt động đa nền tảng | Hạn chế khoảng trắng, ký tự đặc biệt và khác biệt chữ hoa/chữ thường giữa hệ điều hành. |
| Dễ kiểm chứng | Tên, đường dẫn và changelog gốc giúp truy vết từ PR đến lần triển khai. |

Quy ước chỉ phát huy hiệu quả khi mọi người áp dụng nhất quán. Một dự án nhỏ có thể bắt đầu đơn giản; dự án lớn cần thêm kiểm tra tự động và hướng dẫn cộng tác.

### 2.1. Chọn một ngôn ngữ và một kiểu chữ

Đối với tên tệp kỹ thuật, quy ước thông dụng là tiếng Anh, chữ thường và phân tách bằng dấu gạch ngang:

~~~text
001-create-customer-table.yaml
002-add-customer-email-index.yaml
003-backfill-customer-status.sql
~~~

Nên hạn chế:

~~~text
CreateCustomerTable.yaml
create customer table.yaml
new_update_final_v2.yaml
fix.sql
abc123.yaml
~~~

Tên chung như **fix.sql** hoặc **update.yaml** không thể hiện được phạm vi thay đổi. Số phiên bản trong tên kiểu **final-v2** cũng dễ lỗi thời khi tệp đã được triển khai hoặc phát hành qua nhiều môi trường.

### 2.2. Dùng từ mô tả hành động rõ ràng

Một bộ động từ nhất quán thường bao gồm:

| Động từ | Tình huống |
|---|---|
| create | Tạo bảng, view, sequence hoặc đối tượng mới |
| add | Thêm cột, constraint, index |
| alter | Điều chỉnh cấu trúc hoặc thuộc tính |
| rename | Đổi tên đối tượng |
| drop | Xóa đối tượng |
| backfill | Bổ sung dữ liệu cho cột hoặc cấu trúc mới |
| seed | Khởi tạo dữ liệu tham chiếu |
| migrate | Chuyển dữ liệu từ mô hình cũ sang mô hình mới |
| cleanup | Dọn dữ liệu hoặc cấu trúc không còn dùng, với phạm vi rõ |
| reconcile | Hiệu chỉnh dữ liệu hoặc trạng thái có lý do nghiệp vụ |

Nên đặt tên theo tác động chính. Ví dụ **014-add-payment-status-column.yaml** rõ hơn **014-update-payment.yaml**. Khi một migration có nhiều tác động độc lập, nên cân nhắc tách thành các changeset hoặc tệp riêng để review và rollback có phạm vi nhỏ.

## 3. Các chiến lược đánh số và đặt tên

Không có một mẫu tên bắt buộc cho mọi dự án Liquibase. Đội phát triển nên chọn một chiến lược, ghi nhận quy tắc của chiến lược đó và giữ ổn định trong suốt vòng đời module.

### 3.1. Số thứ tự tăng dần

Ví dụ:

~~~text
001-create-customer-table.yaml
002-add-customer-email-column.yaml
003-create-customer-email-index.yaml
~~~

Ưu điểm: dễ đọc thứ tự trong một nhóm nhỏ. Hạn chế: khi nhiều nhánh cùng phát triển, hai người có thể chọn cùng số; số cũng không mang ý nghĩa thời gian hoặc release.

Nếu dùng số thứ tự, hãy thống nhất số chữ số và bổ sung bước phát hiện trùng tên khi tích hợp nhánh. Trong thư mục có hàng trăm migration, dùng tiền tố có độ rộng cố định như **0001**, **0002**, **0100** sẽ dễ sắp xếp hơn.

### 3.2. Ngày hoặc thời điểm tạo và mô tả

Ví dụ:

~~~text
20261119-001-create-customer-table.yaml
20261119-002-add-customer-email-index.yaml
20261120-001-backfill-customer-status.sql
~~~

Ưu điểm: thuận tiện khi xem lịch sử thay đổi theo thời gian. Hạn chế: ngày trên tên tệp chỉ là thông tin tổ chức; nó không bảo đảm Liquibase thực thi vào đúng ngày đó. Hai nhánh có thể cùng chọn một số trong cùng ngày.

Có thể dùng timestamp chi tiết hoặc định danh nhóm phát triển nếu dự án thường xuyên có nhiều nhánh làm việc song song. Tránh dựa duy nhất vào phút/giây để bảo đảm duy nhất, vì thời điểm tạo vẫn có thể trùng và dễ bị thay đổi khi đổi tên tệp.

### 3.3. Theo release hoặc theo miền nghiệp vụ

Ví dụ:

~~~text
releases/2026-11/001-create-customer-table.yaml
releases/2026-11/002-add-customer-email-index.yaml

domains/billing/001-create-invoice-table.yaml
domains/identity/001-add-user-status.yaml
~~~

Tổ chức theo release giúp dễ review tập migration đi cùng một gói phát hành. Tổ chức theo miền nghiệp vụ giúp đội sở hữu từng khu vực database dễ tìm kiếm. Tuy nhiên, đường dẫn theo miền hoặc release cần được xem là đường dẫn ổn định sau khi triển khai; việc đưa tệp vào một release khác hoặc chuyển miền sở hữu có thể làm thay đổi định danh nếu không có chiến lược logicalFilePath.

**Khuyến nghị thực hành:** Với module học tập hoặc dịch vụ vừa, có thể dùng **theo năm/tháng + số thứ tự cố định + mô tả hành động**. Với tổ chức lớn, có thể bổ sung miền nghiệp vụ hoặc release nhưng phải quản lý danh tính lịch sử thật chặt.

## 4. Thiết kế cấu trúc thư mục dễ kiểm tra

Một cấu trúc có thể dùng cho ứng dụng Spring Boot:

~~~text
src/main/resources/
└── db/
    └── changelog/
        ├── db.changelog-master.yaml
        └── releases/
            └── 2026/
                ├── 10/
                │   ├── 001-create-customer-table.yaml
                │   └── 002-add-customer-email-column.yaml
                └── 11/
                    ├── 001-add-customer-email-index.yaml
                    ├── 002-add-customer-status-column.yaml
                    └── 003-backfill-customer-status.sql
~~~

Đây là cấu trúc minh họa, không phải cấu trúc bắt buộc của Liquibase. Các nguyên tắc thiết kế đáng chú ý:

- Có **một điểm vào rõ ràng** cho mỗi dòng triển khai database, thường là changelog gốc.
- Các tệp con được nhóm theo quy tắc dễ dự đoán, chẳng hạn năm/tháng hoặc release.
- Tên tệp mang cả thứ tự dễ đọc lẫn mục đích thay đổi.
- Mỗi tệp con có phạm vi đủ nhỏ để reviewer đọc và đối chiếu với yêu cầu nghiệp vụ.
- Các tệp đã triển khai vẫn giữ nguyên đường dẫn, kể cả khi module đổi cấu trúc code.
- Changelog gốc ghi rõ tệp nào tham gia vào luồng triển khai.

Một số dự án chia theo schema, tenant hoặc service. Khi đó, đội vận hành cần làm rõ mỗi changelog gốc tương ứng database nào, có dùng chung DATABASECHANGELOG hay không và quy trình CI/CD chọn điểm vào nào. Tên thư mục đẹp không thay thế việc cấu hình đúng database đích.

## 5. Changelog gốc: nơi thể hiện thứ tự

Một changelog gốc thường giữ vai trò điều phối thay vì chứa hàng trăm thay đổi trực tiếp. Với các dự án yêu cầu tính kiểm soát cao, có thể liệt kê các tệp con bằng **include**.

Ví dụ **db.changelog-master.yaml**:

~~~yaml
databaseChangeLog:
  - include:
      file: releases/2026/10/001-create-customer-table.yaml
      relativeToChangelogFile: true

  - include:
      file: releases/2026/10/002-add-customer-email-column.yaml
      relativeToChangelogFile: true

  - include:
      file: releases/2026/11/001-add-customer-email-index.yaml
      relativeToChangelogFile: true

  - include:
      file: releases/2026/11/002-add-customer-status-column.yaml
      relativeToChangelogFile: true

  - include:
      file: releases/2026/11/003-backfill-customer-status.sql
      relativeToChangelogFile: true
~~~

**relativeToChangelogFile: true** yêu cầu đường dẫn include được giải quyết tương đối với tệp changelog chứa khai báo include. Điều này làm ý nghĩa đường dẫn dễ hiểu hơn khi công cụ được chạy từ thư mục khác nhau; vẫn cần kiểm tra cơ chế classpath và truy cập resource của môi trường thực thi.

Với include tường minh:

- Reviewer nhìn ngay thứ tự Liquibase dự kiến đọc các changelog.
- Việc thêm migration mới trở thành thay đổi có chủ đích trong changelog gốc.
- Có thể phát hiện tệp bị thiếu khỏi luồng triển khai trong code review.
- Các tệp nằm trong repository nhưng chưa được include sẽ không tự động được Liquibase thực thi qua changelog gốc.

Nên phân biệt **thứ tự khai báo include** với **thời điểm changeset thực tế được thực thi**. Context, label, điều kiện DBMS, precondition hoặc các changeset đã có trong DATABASECHANGELOG có thể khiến một số changeset bị bỏ qua hoặc xử lý theo quy tắc khác.

## 6. Dùng includeAll khi nào?

**includeAll** giúp Liquibase nạp các changelog trong một thư mục phù hợp với quy tắc quét, lọc và sắp xếp của phiên bản đang sử dụng. Đây là lựa chọn tiện lợi khi nhiều migration được quản lý bằng quy ước tên chặt chẽ.

Ví dụ ý tưởng bằng YAML:

~~~yaml
databaseChangeLog:
  - includeAll:
      path: releases/2026/11
      relativeToChangelogFile: true
~~~

Khi dùng includeAll, Liquibase có cơ chế sắp xếp tệp, mặc định thường theo tên đường dẫn theo thứ tự chữ cái. Vì vậy, **001**, **002**, **010** có tính dự đoán tốt hơn **1**, **2**, **10**. Tuy nhiên, cơ chế lọc phần mở rộng, quét thư mục con và tùy chọn sắp xếp có thể phụ thuộc phiên bản hoặc cấu hình; cần xác nhận kết quả bằng chính Liquibase đang dùng.

### 6.1. So sánh include và includeAll

| Khía cạnh | include | includeAll |
|---|---|---|
| Chọn tệp | Liệt kê từng tệp | Nạp tệp theo thư mục/quy tắc quét |
| Thứ tự dễ thấy trong PR | Rất rõ tại changelog gốc | Cần hiểu quy tắc sắp xếp |
| Khi thêm tệp | Phải sửa changelog gốc hoặc manifest liên quan | Tệp phù hợp có thể được nạp tự động |
| Phát hiện tệp bị thêm ngoài ý muốn | Dễ review danh sách include | Cần kiểm tra danh sách tệp trong thư mục |
| Rủi ro khi đổi tên tệp | Có, vì đường dẫn định danh có thể đổi | Có, đồng thời thứ tự nạp có thể đổi |
| Phù hợp | Dự án ưu tiên review tường minh | Dự án kiểm soát nghiêm naming, thư mục và cách quét |

Không nên dùng includeAll chỉ vì muốn bỏ qua việc review file gốc. Nếu chọn includeAll, cần có kiểm soát tương đương: quy ước tên chuẩn, lọc định dạng phù hợp và kiểm tra danh sách changeset sắp chạy.

### 6.2. Cẩn thận với thứ tự trong cùng thư mục

Ví dụ:

~~~text
1-create-customer.yaml
10-create-index.yaml
2-add-email.yaml
~~~

Thứ tự chữ cái có thể cho **10** trước **2**, trái với thứ tự mà người viết mong đợi. Đổi thành:

~~~text
001-create-customer.yaml
002-add-email.yaml
010-create-index.yaml
~~~

Dù tên giúp sắp xếp có thứ tự hơn, không được coi tên tệp là cơ chế bảo đảm mọi ràng buộc phụ thuộc. Nếu migration 010 cần cột email được tạo bởi 002, hãy kiểm tra changelog được nạp theo đúng thứ tự và dùng các bước validation, review SQL phù hợp.

### 6.3. Không vô tình nạp nhầm tệp

Nếu thư mục includeAll chứa file thử nghiệm, changelog cũ đã sao chép hoặc file SQL chưa theo định dạng dự kiến, việc quét có thể tạo ra kết quả ngoài ý muốn. Hãy giới hạn thư mục chỉ chứa các changelog được phép tham gia triển khai, cấu hình bộ lọc khi cần và xác nhận danh sách changeset trước update.

Không dùng việc “chuyển tệp sang thư mục archive” như cách đơn giản để vô hiệu hóa migration đã chạy. Với changeset đã ghi lịch sử, thao tác này có thể làm mất nguồn định nghĩa dùng để validate hoặc rollback, và khi được include ở đường dẫn mới còn có thể tạo định danh mới.

## 7. Ví dụ một changelog con dễ review

Ví dụ **002-add-customer-status-column.yaml**:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-002"
      author: "db-team"
      comment: "Add status column for customer lifecycle"
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: status
                  type: varchar(24)
                  defaultValue: ACTIVE
                  constraints:
                    nullable: false
      rollback:
        - dropColumn:
            tableName: customer
            columnName: status
~~~

Tệp này thể hiện một mục tiêu chính: thêm cột **status** vào bảng **customer**. Tên file mô tả mục tiêu; **id** và **author** xác định changeset trong tệp; **rollback** mô tả phương án đảo ngược cấu trúc cho ví dụ đơn giản.

Cần lưu ý:

- Không bắt buộc **id** phải trùng số thứ tự trên tên file. Nhưng cả hai nên có quan hệ rõ ràng để dễ truy vết.
- Có thể có nhiều changeset trong một tệp; khi đó mỗi changeset phải có ID rõ ràng và độc lập.
- Trong ví dụ này, rollback xóa cột sẽ làm mất dữ liệu trong cột nếu cột đã có dữ liệu; cần đánh giá rủi ro trước khi dùng rollback trên môi trường thật.
- Việc thêm cột NOT NULL có default vào bảng lớn có thể tạo chi phí đáng kể tùy DBMS; nên phân tích và có thể tách thành nhiều bước triển khai.
- Tên file và comment giúp review, nhưng SQL sinh ra và schema thực tế vẫn cần được kiểm tra.

## 8. Khi changelog con dùng formatted SQL

Liquibase có thể quản lý changeset viết bằng **formatted SQL**. Khi lưu dưới dạng SQL, cần có marker để Liquibase nhận diện changeset theo cú pháp phiên bản đang dùng.

Ví dụ **003-backfill-customer-status.sql**:

~~~sql
--liquibase formatted sql
--changeset db-team:20261119-003
UPDATE customer
SET status = 'ACTIVE'
WHERE status IS NULL;

--rollback UPDATE customer SET status = NULL WHERE status = 'ACTIVE';
~~~

Đây là ví dụ trình bày cú pháp, **không phải** rollback dữ liệu an toàn trong mọi trường hợp. Nếu trước migration đã có những dòng mang trạng thái ACTIVE, câu lệnh rollback minh họa không phân biệt được giá trị vốn có và giá trị được backfill. Trong thực tế, với migration dữ liệu, thường cần thiết kế nhật ký hoặc cách hoàn tác cụ thể, hoặc xác định rằng rollback dữ liệu không khả thi và sử dụng chiến lược forward fix.

Quy ước đặt tên cho SQL nên cho biết đây là **backfill/seed/data-migration**, phân biệt với migration DDL:

~~~text
003-backfill-customer-status.sql
004-seed-country-reference-data.sql
005-reconcile-duplicate-customer-codes.sql
~~~

Không đặt tệp SQL thuần không có cấu trúc formatted SQL vào cùng luồng include và mặc định rằng Liquibase sẽ hiểu mọi câu lệnh dưới dạng changeset độc lập. Cần xác nhận loại changelog, parser và cách nạp file ở phiên bản Liquibase đang dùng.

## 9. Quan hệ giữa tên tệp, id, author và lịch sử

Giả sử một changeset được triển khai lần đầu với:

~~~text
ID       = 20261119-002
AUTHOR   = db-team
FILENAME = db/changelog/releases/2026/11/002-add-customer-status-column.yaml
~~~

Liquibase dùng bộ định danh này để đối chiếu với các bản ghi trong **DATABASECHANGELOG**. Nếu giữ nguyên id và author nhưng đổi đường dẫn file thành:

~~~text
db/changelog/domains/customer/002-add-customer-status-column.yaml
~~~

thì đường dẫn dùng để định danh có thể khác. Liquibase có thể xem changeset ở vị trí mới là một changeset chưa từng được xử lý và tìm cách thực thi lại.

Đây là lý do phải xem đường dẫn tệp như một phần của giao diện tương thích lịch sử. Git có thể nhận diện thao tác rename, nhưng điều đó không tự động bảo đảm Liquibase coi changeset cũ và mới là một.

### 9.1. logicalFilePath giải quyết vấn đề gì?

**logicalFilePath** cho phép xác định đường dẫn logic dùng khi nhận diện changeset, độc lập với vị trí vật lý của tệp trong một số ngữ cảnh. Khi một module cần thay đổi cấu trúc thư mục mà vẫn giữ danh tính lịch sử, đội phát triển có thể thiết kế và duy trì giá trị logicalFilePath ổn định.

Nguyên tắc quan trọng:

1. Ưu tiên đặt logicalFilePath ổn định từ sớm nếu dự án có nhu cầu di chuyển file.
2. Với changeset đã triển khai, phải xác định chính xác **FILENAME đang được lưu** trên các database liên quan.
3. Chỉ lựa chọn logicalFilePath mới khi biết nó tương thích với lịch sử cũ hoặc có kế hoạch chuyển đổi được kiểm chứng.
4. Kiểm tra tác động trên bản sao database đại diện cho môi trường đã triển khai.
5. Xác minh Liquibase không bất ngờ coi changeset cũ là pending trước khi áp dụng lên production.

Cú pháp và phạm vi áp dụng logicalFilePath ở mức changelog hoặc changeset phụ thuộc định dạng tệp và phiên bản Liquibase. Hãy sử dụng tài liệu của phiên bản cụ thể và xác nhận kết quả bằng kiểm tra trạng thái, thay vì sao chép một cấu hình không được thử nghiệm.

### 9.2. Những gì không nên làm khi đổi cấu trúc

Không nên:

- Xóa trực tiếp dòng DATABASECHANGELOG để “khớp” với tên file mới.
- Đổi hàng loạt id, author và đường dẫn của changeset đã chạy.
- Copy changeset cũ sang file mới rồi include cả hai vị trí.
- Giả định checksum giống nhau thì Liquibase tự nhận ra hai đường dẫn là cùng một changeset.
- Chỉnh sửa changelog đã triển khai để thay đổi lịch sử cho đẹp mà không đánh giá môi trường hiện tại.

Khi cần sửa hoặc mở rộng schema đã phát hành, thông thường nên thêm changeset mới. Việc tái tổ chức changelog cũ là công việc migration metadata riêng, cần quy trình và kiểm chứng tương xứng.

## 10. Chọn độ lớn hợp lý của mỗi tệp

Có hai cực đoan gây khó bảo trì:

- Một tệp khổng lồ chứa mọi changeset của toàn bộ dự án, khiến PR khó review và khó tìm migration cần điều tra.
- Mỗi câu lệnh SQL là một tệp độc lập dù các câu lệnh thuộc cùng một thao tác nhỏ, khiến cấu trúc thư mục phân mảnh và tốn công điều phối.

Có thể áp dụng quy tắc: **mỗi tệp đại diện một thay đổi hoặc một nhóm thay đổi có mục tiêu, khả năng kiểm thử và kế hoạch rollback rõ ràng**.

Ví dụ việc thêm chức năng quản lý trạng thái khách hàng:

| Tệp | Mục tiêu |
|---|---|
| 001-add-customer-status-column.yaml | Chuẩn bị cấu trúc |
| 002-backfill-customer-status.sql | Chuyển đổi dữ liệu đã có |
| 003-enforce-customer-status-not-null.yaml | Bổ sung ràng buộc sau khi dữ liệu hợp lệ |
| 004-add-customer-status-index.yaml | Tối ưu truy vấn khi có nhu cầu |

Cách chia này cho phép xem xét rủi ro dữ liệu và thời gian khóa bảng theo từng bước, đặc biệt với chiến lược **expand–migrate–contract** trong những hệ thống cần giảm downtime.

Một changeset có thể chứa nhiều change type liên quan, nhưng cần kiểm tra giới hạn transaction theo DBMS. Việc chia thành nhiều changeset không tự động khiến migration an toàn hơn; nó chỉ giúp quản lý phạm vi và điểm xác nhận rõ ràng hơn.

## 11. Tên tệp không thay thế changeset ID

Tên file được đặt tốt vẫn không đủ để bảo đảm changeset không trùng danh tính. Hai người có thể tạo hai files khác nhau và cùng dùng một id; khi tên file khác, danh tính đầy đủ khác nhau, nhưng việc đặt ID mơ hồ khiến kiểm tra thủ công khó hơn.

Một quy ước có thể chọn:

~~~text
Tên file : 20261119-002-add-customer-status-column.yaml
ID       : 20261119-002
AUTHOR   : customer-team
~~~

Hoặc:

~~~text
Tên file : 00042-add-customer-status-column.yaml
ID       : customer-0042
AUTHOR   : customer-team
~~~

Điều quan trọng là thống nhất cách phát sinh ID, nơi tra cứu và xử lý xung đột. Không cần ép ID giống hoàn toàn tên file nếu quy ước khác giúp nhóm làm việc ổn định hơn.

Sau khi đã phát hành, nên coi **id**, **author**, đường dẫn logic và nội dung changeset là bất biến trong điều kiện thông thường. Nếu muốn cập nhật cấu trúc, hãy viết một changeset mới thay vì sửa changeset cũ.

## 12. Phối hợp nhiều nhánh và tránh xung đột

Tình huống phổ biến: hai nhóm cùng phát triển trên các nhánh khác nhau.

~~~text
Nhánh feature/customer-status:
  007-add-customer-status-column.yaml

Nhánh feature/customer-search:
  007-add-customer-email-index.yaml
~~~

Cả hai đều chọn số **007** vì mỗi nhánh được tạo từ cùng trạng thái repository. Khi hợp nhất, số thứ tự trùng có thể gây xung đột trong cách sắp xếp và gây nhầm lẫn khi review, ngay cả khi Liquibase có thể nhận diện changeset theo bộ định danh đầy đủ.

Nhóm có thể chọn một trong các cách:

- Cấp số thứ tự sau khi branch được tích hợp, trước khi migration được phát hành và triển khai.
- Dùng tiền tố ngày cộng ID ngắn độc lập với số thứ tự toàn cục.
- Tách namespace hoặc thư mục theo miền nghiệp vụ nếu quyền sở hữu rõ ràng.
- Áp dụng công cụ kiểm tra tên file, ID và thay đổi changelog gốc trong CI.

**Lưu ý giới hạn quan trọng:** Đổi tên migration để giải quyết xung đột chỉ nên thực hiện khi migration đó chưa được triển khai ở môi trường nào. Nếu nhánh đã chạy trên database được giữ lâu dài hoặc môi trường dùng chung, cần đối chiếu lịch sử trước khi rename.

Khi hai migration sửa cùng bảng, người review cần kiểm tra thứ tự phụ thuộc. Tên tệp tăng dần không thể tự giải quyết tranh chấp schema, tình trạng khóa bảng hoặc thứ tự rollout của ứng dụng.

## 13. Quy trình đưa migration mới vào repository

Một quy trình rõ ràng có thể gồm:

### Bước 1: Xác định thay đổi và phạm vi

Ghi nhận bảng, cột hoặc dữ liệu bị tác động; mô tả mục tiêu; quyết định DDL hay data migration; đánh giá phụ thuộc giữa các bước. Nếu thay đổi ảnh hưởng nhiều bảng không liên quan, cân nhắc chia thành nhiều migration.

### Bước 2: Chọn tên tệp theo quy ước

Ví dụ:

~~~text
releases/2026/11/004-add-order-payment-reference.yaml
~~~

Trước khi tạo tên mới, kiểm tra phạm vi số thứ tự và quy tắc đang áp dụng trong repository. Với dự án dùng timestamp, xác định cách tránh tên trùng khi nhiều nhánh hoạt động.

### Bước 3: Khai báo changeset có định danh ổn định

Khai báo ID, author, comment hoặc mô tả đủ rõ. Thiết kế precondition nếu cần kiểm tra giả định trước migration. Đánh giá rollback, đặc biệt với migration dữ liệu và thao tác xóa đối tượng.

### Bước 4: Đăng ký vào changelog gốc

Với include tường minh, thêm một dòng include ở vị trí đúng thứ tự. Với includeAll, xác minh tên và thư mục được bộ quét nhận diện đúng, không kéo theo file không mong muốn.

### Bước 5: Kiểm tra trước update

Trên database thử nghiệm:

- Chạy **validate** với changelog và Liquibase phiên bản dự kiến.
- Chạy **status --verbose** để xem những changeset nào được coi là pending.
- Chạy **update-sql** để review SQL dự kiến được sinh ra.
- Kiểm tra thứ tự changeset, schema đích, context, label và precondition.
- Thực thi migration và xác minh schema, dữ liệu cùng DATABASECHANGELOG.
- Thử rollback hoặc phương án khôi phục đã thiết kế nếu phạm vi bài thực hành cho phép.

### Bước 6: Review và tích hợp

Reviewer xem cả tệp mới lẫn thay đổi trong root changelog. Nếu tệp cũ bị đổi tên, di chuyển hoặc chỉnh sửa, yêu cầu giải thích tác động tới lịch sử và kết quả kiểm chứng trên môi trường đã triển khai.

### Bước 7: Triển khai cùng một artifact

Giữ cùng phiên bản changelog/artifact khi lần lượt đi qua test, staging và production. Khác biệt endpoint, credential, context hoặc label thuộc cấu hình môi trường và chính sách phát hành. Không viết lại migration cũ cho từng môi trường.

## 14. Checklist dành cho code review

Một PR migration nên trả lời được các câu hỏi:

| Câu hỏi | Mục đích |
|---|---|
| Tên tệp có đúng quy ước không? | Dễ tìm và tránh tên mơ hồ. |
| Đường dẫn nằm trong nhóm phù hợp không? | Giữ cấu trúc repository dễ hiểu. |
| Đây là tệp mới hay rename của tệp đã chạy? | Phát hiện nguy cơ đổi danh tính changeset. |
| Changeset ID và author có ổn định, rõ ràng không? | Truy vết lịch sử DATABASECHANGELOG. |
| Changelog gốc có include đúng thứ tự không? | Bảo đảm migration tham gia luồng thực thi. |
| Có tệp nào bị include lặp hoặc includeAll kéo vào ngoài dự kiến không? | Tránh thực thi dư hoặc xung đột. |
| Có quan hệ phụ thuộc giữa các changeset không? | Đảm bảo đối tượng có trước khi được tham chiếu. |
| SQL và precondition có phù hợp DBMS/schema đích không? | Tránh sai khác giữa môi trường. |
| Có rollback hoặc kế hoạch forward fix phù hợp không? | Đánh giá phục hồi khi thất bại. |
| Tệp cũ đã triển khai có bị chỉnh sửa nội dung hoặc checksum không? | Giữ tính nhất quán lịch sử. |
| Đã kiểm tra status, validate và SQL dự kiến chưa? | Bắt lỗi trước khi triển khai. |

Không phải PR nào cũng cần đầy đủ mọi loại kiểm thử hoặc rollback tự động; mức độ kiểm tra tùy độ rủi ro. Nhưng việc xác định **tệp nào mới, tệp nào đã phát hành, và tệp nào đã đổi đường dẫn** nên là bước review cố định.

## 15. Tự động hóa các kiểm tra quy ước trong CI/CD

Dù cách tổ chức repo khác nhau, CI/CD có thể kiểm tra các quy tắc cơ bản trước khi Liquibase update:

1. Tệp changelog mới có phần mở rộng hợp lệ và tên theo mẫu đã thống nhất.
2. Không có tên file bị trùng trong cùng thư mục theo cách gây nhập nhằng.
3. Mỗi changeset có id và author hợp lệ; không tạo changeset trùng định danh logic trong tập changelog được nạp.
4. Changelog gốc không tham chiếu tệp không tồn tại hoặc cùng một tệp ngoài ý muốn.
5. Các đường dẫn đã từng phát hành không bị rename hoặc xóa mà thiếu kế hoạch kiểm chứng.
6. Liquibase validate chạy thành công.
7. Danh sách changeset pending và SQL dự kiến được kiểm tra trên database đại diện.
8. Các context/label hoặc precondition được review theo mục tiêu triển khai.

Không cần viết cơ chế regex quá phức tạp ngay từ đầu. Một quy tắc tên dễ hiểu, cộng với validate và review thay đổi trong Git, thường đem lại hiệu quả tốt. Khi thêm tự động hóa, hãy chọn kiểm tra có khả năng bắt lỗi thực sự như rename làm thay đổi định danh hoặc include thiếu tệp.

Các kiểm tra tên file không chứng minh migration an toàn về SQL, transaction hay tính tương thích ngược với ứng dụng. Chúng chỉ giảm lỗi tổ chức và phát hiện thay đổi bất thường trước khi triển khai.

## 16. Quan hệ với checksum, context, label và precondition

Để duy trì cấu trúc dễ kiểm tra, cần hiểu các cơ chế của Liquibase có vai trò khác nhau:

- **Tên và đường dẫn tệp**: giúp tổ chức changelog và góp phần nhận diện changeset.
- **ID và author**: thành phần định danh changeset.
- **Checksum**: phát hiện nội dung changeset đã ghi nhận bị thay đổi theo cơ chế checksum của Liquibase.
- **Context và label**: lọc changeset theo điều kiện triển khai.
- **Precondition**: kiểm tra giả định trước khi áp dụng thay đổi.
- **DATABASECHANGELOG**: lưu lịch sử changeset trên mỗi database đích.

Việc đặt tên **001-create-table.yaml** không bảo đảm changeset luôn chạy đầu tiên trong mọi môi trường. Changeset có thể đã được ghi nhận, bị lọc theo context hoặc bị điều kiện triển khai tác động. Tương tự, đổi tên file không phải cách sửa checksum mismatch: nó có thể khiến Liquibase nhìn nhận changeset là mới, làm vấn đề nghiêm trọng hơn.

Khi thấy checksum mismatch, trước tiên kiểm tra nội dung changeset cũ có bị sửa hay không, artifact nào đã triển khai và schema thực tế đang ở trạng thái nào. Khi cần thay đổi tiếp, giải pháp thông dụng là bổ sung changeset mới.

## 17. Case study: tái cấu trúc thư mục sau khi đã triển khai

Một ứng dụng có ba môi trường development, staging và production. Ban đầu nhóm dùng:

~~~text
db/changelog/
  db.changelog-master.yaml
  001-create-customer.yaml
  002-add-customer-email.yaml
~~~

Hai changeset đã chạy thành công trên cả ba môi trường. Sau vài tháng, nhóm muốn chuyển tất cả tệp cũ sang thư mục **releases/2026/11/** để repository gọn hơn.

### Rủi ro

Nếu chỉ di chuyển tệp và sửa dòng include, đường dẫn mà Liquibase dùng để nhận diện changeset có thể thay đổi. Lần update tiếp theo có thể coi các changeset đã chạy là mới. Một lệnh tạo bảng có thể thất bại vì bảng đã tồn tại, hoặc một lệnh cập nhật dữ liệu có thể lặp ngoài ý muốn.

### Cách tiếp cận có kiểm soát

1. Đọc các dòng liên quan trong DATABASECHANGELOG của từng môi trường để ghi nhận ID, AUTHOR, FILENAME và EXECTYPE.
2. Xác định phiên bản Liquibase, cách tính đường dẫn hiện tại và khả năng sử dụng logicalFilePath.
3. Thiết kế cách giữ lại chính xác danh tính đã được ghi nhận trong lịch sử.
4. Thử trên bản sao database có lịch sử triển khai giống production.
5. Chạy validate, status --verbose và update-sql để xác nhận không có changeset cũ bất ngờ trở thành pending.
6. Review kết quả và triển khai cùng artifact đã kiểm chứng qua các môi trường.

Nếu mục đích chỉ là làm thư mục đẹp hơn và việc di chuyển mang rủi ro lớn, lựa chọn thực tế có thể là **giữ nguyên các tệp cũ** tại vị trí đã phát hành, tổ chức thư mục theo quy ước mới chỉ đối với migration mới. Đây thường là cách đơn giản để giữ tương thích lịch sử.

## 18. Những mẫu tổ chức nên tránh

| Mẫu có vấn đề | Vì sao gây khó khăn | Hướng cải thiện |
|---|---|---|
| final.sql, final2.sql, fix-last.sql | Không mô tả phạm vi hoặc lịch sử thay đổi | Dùng tên hành động + đối tượng |
| Thứ tự file 1, 10, 2 trong includeAll | Sắp xếp theo tên không trùng thứ tự số | Dùng số cố định 001, 002, 010 |
| Gộp toàn bộ changeset vào một file cực lớn | Khó review và truy vết mục tiêu | Chia theo thay đổi hoặc nhóm thay đổi liên quan |
| Copy changelog cũ sang thư mục mới nhưng giữ cả hai include | Có thể tạo định danh hoặc luồng thực thi không mong muốn | Chỉ duy trì một nguồn định nghĩa và kiểm tra danh tính |
| Đổi tên file đã triển khai chỉ để đồng nhất naming | Có thể làm thay đổi FILENAME lịch sử | Giữ đường dẫn cũ hoặc dùng quy trình logicalFilePath được kiểm chứng |
| Chèn tệp mới vào includeAll mà không review thứ tự | Có thể thay đổi tập và thứ tự nạp | Kiểm tra danh sách pending và SQL dự kiến |
| Sửa changeset cũ để cập nhật schema | Có nguy cơ checksum mismatch và lịch sử không nhất quán | Tạo changeset mới |
| Dùng tên file để suy ra môi trường đích | Không bảo đảm kết nối tới đúng database | Cấu hình JDBC/endpoint riêng từng môi trường |

## 19. Bài thực hành thiết kế cấu trúc changelog

**Bối cảnh:** Dịch vụ quản lý đơn hàng cần thêm bảng **payment**, cột **payment_status** cho bảng **orders** và backfill dữ liệu cũ. Nhóm dùng PostgreSQL, Spring Boot và Liquibase. Changelog hiện tại đang triển khai ổn định.

**Yêu cầu:** Đề xuất tên file, thứ tự include và cách review để ba thay đổi dễ kiểm tra.

Một cách tổ chức:

~~~text
db/changelog/
  db.changelog-master.yaml
  releases/
    2026/
      11/
        010-create-payment-table.yaml
        011-add-order-payment-status-column.yaml
        012-backfill-order-payment-status.sql
~~~

Trong changelog gốc, include theo đúng thứ tự phụ thuộc: tạo bảng, thêm cột, sau đó cập nhật dữ liệu. Nếu cột cần NOT NULL nhưng dữ liệu cũ phải được backfill trước, tách riêng changeset bổ sung ràng buộc thành tệp sau bước backfill.

Trong mỗi tệp, khai báo ID và author ổn định, mô tả ý định, precondition khi có giả định quan trọng và chiến lược rollback hoặc khôi phục phù hợp. Khi review, kiểm tra danh sách pending, SQL dự kiến và ảnh hưởng lên dữ liệu hiện có. Khi phát hành, giữ nguyên ba tệp qua các môi trường.

**Câu hỏi tự kiểm tra:**

1. Vì sao chỉ dùng tên **012.sql** là chưa đủ? Vì không thể nhận biết mục tiêu dữ liệu nếu không mở tệp; thêm **backfill-order-payment-status** giúp truy vết và review.
2. Vì sao không đổi tên tệp **010** sau khi nó chạy trên staging? Vì đường dẫn trong định danh changeset có thể thay đổi, khiến lần update tiếp theo không nhận ra lịch sử cũ.
3. Nếu dùng includeAll, điều gì cần xác minh? Danh sách tệp thực sự được nạp, thứ tự sắp xếp, định dạng tệp và các changeset pending.
4. Nếu checksum của migration cũ khác sau khi sửa SQL, nên làm gì? Đối chiếu artifact đã phát hành và thay đổi thực tế; thông thường giữ nguyên changeset cũ và tạo changeset bổ sung.

## 20. Checklist áp dụng trong dự án

- [ ] Có một quy ước tên file được cả đội thống nhất.
- [ ] Tên gồm thông tin thứ tự/thời gian và mô tả hành động cụ thể.
- [ ] Dùng chữ thường, dấu gạch ngang và phần mở rộng đúng định dạng.
- [ ] Có cấu trúc thư mục và điểm vào changelog rõ ràng.
- [ ] Dùng include hoặc includeAll có kiểm soát thứ tự.
- [ ] ID, author và đường dẫn logic của changeset đã phát hành được giữ ổn định.
- [ ] Tệp cũ không bị đổi tên, di chuyển hoặc nhân đôi tùy tiện.
- [ ] Changelog gốc được review cùng tệp migration mới.
- [ ] Kiểm tra phụ thuộc giữa các changeset và tác động tới schema/dữ liệu.
- [ ] Chạy validate, status và review SQL dự kiến trên database phù hợp.
- [ ] Cùng artifact changelog đi qua các môi trường, với kết nối được cấu hình riêng.
- [ ] Có thể truy vết từ tên tệp và changeset tới lịch sử DATABASECHANGELOG.

Một cấu trúc changelog dễ kiểm tra giúp người phát triển tìm được thay đổi, reviewer hiểu được thứ tự, và đội vận hành đối chiếu được lịch sử triển khai. Giá trị cốt lõi không nằm ở việc chọn tên nào là “đẹp” nhất, mà ở khả năng giữ nguyên danh tính changeset đã phát hành và nhận diện được những migration sắp chạy trên từng database.

