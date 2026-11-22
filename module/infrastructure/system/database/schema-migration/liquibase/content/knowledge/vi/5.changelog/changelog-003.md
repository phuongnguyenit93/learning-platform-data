
# Khai báo include và kiểm soát thứ tự tệp được nạp trong Liquibase

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, changelog là bản mô tả có phiên bản của những thay đổi schema và dữ liệu cần triển khai. Liquibase đọc changelog để xác định changeset, kiểm tra precondition, đối chiếu checksum và lịch sử trong DATABASECHANGELOG, sau đó áp dụng các thay đổi đang chờ. Để duy trì một dự án có nhiều migration, ta thường chia changelog thành nhiều tệp và dùng **include** hoặc **includeAll** từ một changelog gốc. Việc chia tệp chỉ an toàn khi hiểu rõ **đường dẫn, thứ tự nạp, thứ tự thực thi và định danh changeset**.

Bài thuộc chương **Changelog** này tập trung vào cách khai báo các tệp con, tổ chức thứ tự phụ thuộc, giữ cùng lịch sử migration giữa development, test, staging và production, cũng như kiểm tra kết quả khi chạy qua Spring Boot, Maven, Gradle hoặc CI/CD.

Sau khi học, bạn cần có thể: đọc được cây changelog từ master đến từng changeset; chọn include hay includeAll phù hợp; giải thích tại sao việc chèn một tệp cũ vào giữa danh sách có thể gây khác biệt giữa database mới và database đã nâng cấp; và kiểm chứng thứ tự dự kiến trước khi chạy migration thật.

## 1. Từ một changelog lớn đến cây changelog

Một dự án nhỏ có thể khai báo mọi changeset trong cùng một tệp. Khi dự án phát triển, một tệp quá lớn khiến việc review, chia nhiệm vụ giữa các nhóm và lần theo lịch sử thay đổi trở nên khó khăn. Liquibase cho phép một changelog cha tham chiếu changelog con.

~~~text
db.changelog-master.yaml
    |
    +-- 001-create-customer.yaml
    |
    +-- 002-add-customer-status.yaml
    |
    +-- 003-create-order.yaml
    |
    +-- 004-add-order-customer-fk.yaml
~~~

Trong ví dụ, master chỉ định **thứ tự đọc**. Mỗi tệp con chứa một hoặc nhiều changeset, mỗi changeset chứa các thao tác như createTable, addColumn, addForeignKeyConstraint hoặc update dữ liệu.

Ba khái niệm cần phân biệt:

| Khái niệm | Ý nghĩa |
|---|---|
| Thứ tự nạp tệp | Thứ tự Liquibase đi qua các chỉ thị include/includeAll để đọc tệp con |
| Thứ tự changeset | Thứ tự các changeset xuất hiện sau khi toàn bộ cây changelog được mở rộng |
| Thứ tự thực thi thực tế | Những changeset được phép chạy, còn pending trên **database đích**, được Liquibase thực thi trong lần update hiện tại |

Thứ tự nạp tạo ra thứ tự xét changeset, nhưng **không đồng nghĩa mọi changeset đều được chạy**. Những changeset đã có lịch sử thực thi thường được bỏ qua; context, label, DBMS và precondition có thể ảnh hưởng đến việc một changeset được thực thi, bỏ qua hoặc dừng cập nhật.

Ví dụ, nếu database staging đã chạy 001 và 002 nhưng production mới chạy 001, cùng một changelog có thể tạo ra các tập changeset đang chờ khác nhau. Changelog xác định thứ tự mong muốn; bảng DATABASECHANGELOG của từng môi trường cho biết phần nào của lịch sử đó đã được ghi nhận.

## 2. Tổ chức thư mục có chủ đích

Một cấu trúc dễ theo dõi cho ứng dụng Java và Spring Boot:

~~~text
src/main/resources/
└── db/
    └── changelog/
        ├── db.changelog-master.yaml
        └── changes/
            ├── 2026/
            │   ├── 001-create-customer.yaml
            │   ├── 002-add-customer-status.yaml
            │   ├── 003-create-order.yaml
            │   └── 004-add-order-customer-fk.yaml
            └── 2027/
                ├── 005-add-order-status.yaml
                └── 006-create-order-index.yaml
~~~

Một số nguyên tắc tổ chức:

- **Một điểm vào thống nhất:** ứng dụng và công cụ build cùng trỏ đến db.changelog-master.yaml.
- **Một changeset có mục đích rõ:** tệp có thể chứa một hoặc nhiều changeset liên quan, nhưng cần dễ review và dễ xác định phụ thuộc.
- **Tên phản ánh thứ tự và ý nghĩa:** tiền tố số thứ tự hoặc thời gian kết hợp với tên thay đổi; không dùng tên file làm cơ chế duy nhất để xác định thứ tự nếu đang dùng include tường minh.
- **Thêm mới theo thời gian:** khi changeset đã được triển khai, tránh đổi nội dung hoặc di chuyển tệp tùy tiện.
- **Độc lập môi trường:** tên và đường dẫn changelog không phụ thuộc vào development, staging hay production; cấu hình kết nối được truyền riêng.

Có thể phân nhóm theo domain, năm hoặc giai đoạn phát hành. Quan trọng là mỗi nhóm hiểu cách đi từ master đến đúng changeset và xác nhận được thứ tự các thao tác phụ thuộc.

## 3. Khai báo include tường minh

Cách kiểm soát thứ tự rõ nhất là viết các chỉ thị **include** theo đúng trình tự mong muốn:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/2026/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/2026/002-add-customer-status.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/2026/003-create-order.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/2026/004-add-order-customer-fk.yaml
      relativeToChangelogFile: true
~~~

Các chỉ thị này nằm trong **db.changelog-master.yaml**. Với relativeToChangelogFile: true, đường dẫn file được giải quyết tương đối với thư mục của changelog đang chứa chỉ thị include. Nhờ đó, tệp master có thể nằm tại db/changelog, còn các file con nằm tại db/changelog/changes/2026.

Liquibase xét các include theo thứ tự khai báo. Trong một tệp con, các changeset cũng được xét theo thứ tự xuất hiện. Vì vậy, nếu 004 tạo khóa ngoại tham chiếu cả customer và order, nó phải được đặt sau các changeset tạo hai bảng tương ứng.

Ví dụ file **001-create-customer.yaml**:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: schema-team
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

Ví dụ file **002-add-customer-status.yaml**:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-add-customer-status
      author: schema-team
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

Nếu đổi vị trí tệp 002 lên trước 001, precondition sẽ phát hiện bảng customer chưa tồn tại và dừng thay đổi trên một database mới. Điều này minh họa vai trò của thứ tự include và precondition: **thứ tự giúp đảm bảo phụ thuộc**, còn **precondition kiểm tra trạng thái thực tế trước khi chạy**. Precondition không tự sắp xếp lại các migration để sửa lỗi thứ tự.

Cú pháp, kiểu dữ liệu và rollback của các thay đổi cần được kiểm tra với phiên bản Liquibase và DBMS của dự án. Các đoạn YAML ở đây minh họa cấu trúc và thứ tự, không phải kịch bản hoàn chỉnh cho mọi cơ sở dữ liệu.

## 4. Đường dẫn trong include: tương đối, classpath và tính ổn định

Hai cấu hình có thể nhìn gần giống nhau nhưng giải quyết đường dẫn khác nhau:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/2026/001-create-customer.yaml
      relativeToChangelogFile: true
~~~

~~~yaml
databaseChangeLog:
  - include:
      file: db/changelog/changes/2026/001-create-customer.yaml
~~~

Ở ví dụ đầu, đường dẫn được giải quyết tương đối với **tệp changelog cha**. Ở ví dụ sau, Liquibase phải tìm tài nguyên theo cơ chế tìm kiếm tài nguyên hoặc search path của cách chạy hiện tại. Cơ chế này có thể chịu ảnh hưởng của classpath, thư mục làm việc hoặc cấu hình Liquibase.

Để hạn chế tình huống chạy được trên máy cá nhân nhưng thất bại khi đóng gói JAR hoặc chạy CI, nên:

1. Dùng relativeToChangelogFile: true cho các include giữa những changelog nằm cùng cây thư mục.
2. Chọn một đường dẫn master nhất quán giữa Spring Boot, Maven/Gradle plugin và Liquibase CLI.
3. Kiểm tra file được đưa vào artifact hoặc classpath cần thiết.
4. Tránh đường dẫn tuyệt đối phụ thuộc vào máy developer.
5. Không di chuyển hoặc đổi tên tệp đã triển khai khi chưa đánh giá ảnh hưởng định danh changeset.

Nếu parent nằm tại db/changelog/db.changelog-master.yaml, chuỗi **changes/2026/001-create-customer.yaml** đúng khi tệp con thật sự nằm dưới thư mục db/changelog/changes/2026. Nếu parent được đặt trong một thư mục khác, đường dẫn tương đối cũng phải thay đổi theo.

Việc Liquibase đọc được tệp chưa đủ để bảo đảm lịch sử migration an toàn. **Đường dẫn changelog** còn tham gia vào định danh changeset, vì vậy việc di chuyển tệp sau khi triển khai có thể khiến changeset bị nhìn nhận là một định danh khác. Phần định danh sẽ được phân tích chi tiết ở dưới.

## 5. Include lồng nhau: mở rộng theo thứ tự từ cha đến con

Không bắt buộc mọi include đều nằm trực tiếp trong master. Một changelog con có thể tiếp tục include các changelog nhỏ hơn:

~~~text
db.changelog-master.yaml
    |
    +-- modules/customer/customer.yaml
    |       +-- changes/001-create-customer.yaml
    |       +-- changes/002-add-customer-status.yaml
    |
    +-- modules/order/order.yaml
            +-- changes/003-create-order.yaml
            +-- changes/004-add-order-customer-fk.yaml
~~~

Nội dung master:

~~~yaml
databaseChangeLog:
  - include:
      file: modules/customer/customer.yaml
      relativeToChangelogFile: true
  - include:
      file: modules/order/order.yaml
      relativeToChangelogFile: true
~~~

Nội dung modules/customer/customer.yaml:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-add-customer-status.yaml
      relativeToChangelogFile: true
~~~

Nội dung modules/order/order.yaml:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/003-create-order.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/004-add-order-customer-fk.yaml
      relativeToChangelogFile: true
~~~

Liquibase mở rộng các tệp theo vị trí include: các changeset thuộc customer được xét trước các changeset thuộc order. Mỗi đường dẫn relativeToChangelogFile được tính theo **tệp cha trực tiếp**, không phải luôn theo master.

Cách này hữu ích khi nhóm phát triển có nhiều domain nhưng vẫn cần một thứ tự phát hành chung. Tuy nhiên, sự phụ thuộc xuyên domain phải được biểu diễn rõ. Nếu order cần bảng customer, master phải đặt customer trước order hoặc nhóm phải thiết kế lại migration để không phụ thuộc vào thứ tự đó.

Tránh include vòng tròn, chẳng hạn master include A, A include B và B lại include A. Tùy hình thức và phiên bản, vòng tham chiếu có thể tạo lỗi xử lý hoặc vấn đề đệ quy. Không nên include cùng một tệp nhiều lần từ các nhánh khác nhau; khi cần tái sử dụng cấu trúc, hãy thiết kế lại cây changelog để mỗi changeset chỉ được định nghĩa và tham chiếu theo một đường đi rõ ràng.

## 6. IncludeAll: nạp cả thư mục changelog

**includeAll** cho phép khai báo một thư mục thay vì liệt kê từng tệp. Ví dụ:

~~~yaml
databaseChangeLog:
  - includeAll:
      path: changes/2026
      relativeToChangelogFile: true
~~~

Nếu changes/2026 chỉ chứa các changelog hợp lệ và được đặt tên như sau:

~~~text
001-create-customer.yaml
002-add-customer-status.yaml
003-create-order.yaml
004-add-order-customer-fk.yaml
~~~

Liquibase thường xử lý tài nguyên được includeAll theo **thứ tự chữ cái/đường dẫn tăng dần**. Do đó, tiền tố số có thể giúp xác định trình tự dễ đọc. Quy tắc cụ thể về đường dẫn, duyệt thư mục con và các tùy chọn lọc phụ thuộc phiên bản Liquibase và cơ chế ResourceAccessor.

Có thể cấu hình thêm một số thuộc tính được phiên bản Liquibase hỗ trợ, ví dụ errorIfMissingOrEmpty để không bỏ qua một thư mục đáng lẽ phải có migration:

~~~yaml
databaseChangeLog:
  - includeAll:
      path: changes/2026
      relativeToChangelogFile: true
      errorIfMissingOrEmpty: true
~~~

**Lưu ý:** includeAll là lựa chọn cần cân nhắc vì nội dung thư mục thay đổi sẽ làm thay đổi tập tệp được nạp mà không nhất thiết phải sửa master. Nếu thư mục có tệp tài liệu, tệp mẫu hoặc changelog chưa sẵn sàng, Liquibase có thể cố gắng đọc chúng tùy bộ lọc và định dạng được hỗ trợ.

Khi dùng includeAll, hãy:

- Dành thư mục đó cho changelog hợp lệ; không trộn tệp nháp hoặc tài liệu tùy ý.
- Dùng quy ước tên cố định có phần số thứ tự được đệm số không, ví dụ 001, 002, 010.
- Kiểm tra quy tắc sắp xếp đối với thư mục lồng nhau trên phiên bản Liquibase đang dùng.
- Review cả danh sách file được thêm/xóa/đổi tên, vì một file mới có thể thay đổi thứ tự nạp.
- Nếu cần lọc theo phần mở rộng, kiểm tra thuộc tính lọc được phiên bản Liquibase hỗ trợ trước khi áp dụng.
- Không coi includeAll là giải pháp tự động giải quyết phụ thuộc giữa các migration.

**Include tường minh** thường tốt hơn với chuỗi migration có phụ thuộc phức tạp hoặc nơi cần review chính xác thứ tự từng tệp. **IncludeAll** phù hợp với những nhóm tệp có quy ước chặt chẽ, phụ thuộc rõ ràng và pipeline kiểm tra được danh sách nạp.

## 7. Include và IncludeAll khác nhau ở điểm nào?

| Khía cạnh | include | includeAll |
|---|---|---|
| Mục tiêu | Nạp một changelog con được chỉ định | Nạp các changelog trong một thư mục |
| Kiểm soát thứ tự | Theo thứ tự các lệnh include trong changelog cha | Theo quy tắc sắp xếp tài nguyên, thường theo tên/đường dẫn |
| Thêm migration | Cần thêm chỉ thị include mới | Thường chỉ cần thêm file vào thư mục được quét |
| Kiểm tra pull request | Dễ nhìn thấy thay đổi thứ tự ngay ở master | Phải xem tên, đường dẫn và danh sách file |
| Phụ thuộc xuyên module | Có thể diễn đạt tường minh bằng thứ tự include | Phụ thuộc gián tiếp vào tên và quy tắc sắp xếp |
| Rủi ro chính | Chèn/sắp lại include đã phát hành | Tệp mới bị xếp vào vị trí không mong muốn hoặc bị quét nhầm |
| Tình huống nên ưu tiên | Migration cốt lõi, thứ tự phức tạp, release cần kiểm soát | Thư mục migration có quy ước nhất quán, kiểm soát tự động tốt |

Không có lựa chọn tối ưu tuyệt đối cho mọi nhóm. Nếu repository lớn, có thể kết hợp: master dùng **include tường minh** để xác định thứ tự các gói/domain, còn từng gói dùng **includeAll** cho các migration nội bộ đã có quy ước tên và kiểm tra.

Ví dụ kết hợp:

~~~yaml
databaseChangeLog:
  - include:
      file: modules/customer/customer.yaml
      relativeToChangelogFile: true
  - includeAll:
      path: modules/order/changes
      relativeToChangelogFile: true
~~~

Trong thiết kế này, toàn bộ changeset từ customer được xét trước các tệp được includeAll trong thư mục order/changes. Việc dùng includeAll không thay đổi thứ tự của những nhóm đã khai báo ở master.

## 8. Thứ tự tên file không đồng nghĩa thứ tự theo id changeset

Một nhầm lẫn thường gặp là Liquibase tự sắp xếp changeset theo id, ngày tạo file hoặc thời gian commit Git. **Không phải như vậy**. Tên file chỉ quyết định thứ tự khi cơ chế nạp, chẳng hạn includeAll, sắp xếp các tài nguyên theo tên. Nếu dùng include tường minh, thứ tự chính là thứ tự khai báo.

Xét master:

~~~yaml
databaseChangeLog:
  - include:
      file: 020-add-status.yaml
      relativeToChangelogFile: true
  - include:
      file: 010-create-customer.yaml
      relativeToChangelogFile: true
~~~

Tên bắt đầu bằng 010 không làm tệp đó tự chuyển lên trước 020. Với database mới, Liquibase sẽ xét tệp 020 trước rồi mới đến 010. Nếu 020 yêu cầu bảng customer đã tồn tại, migration sẽ thất bại hoặc có hành vi sai.

Tương tự, một tệp có ba changeset id C, A, B vẫn được xét theo **vị trí khai báo trong tệp**, thay vì sắp lại theo thứ tự chữ cái của id.

Giá trị id dùng để **nhận diện changeset**, không phải để ra lệnh Liquibase sắp xếp changeset. Quy ước đặt tên theo thứ tự giúp con người kiểm tra phụ thuộc nhưng không thay thế cơ chế include.

## 9. Vì sao không nên chèn migration mới vào đầu lịch sử cũ?

Đây là bẫy quan trọng nhất khi quản lý include qua nhiều môi trường.

Giả sử release đầu tiên có:

~~~text
010-create-customer.yaml
030-add-customer-email.yaml
050-create-customer-index.yaml
~~~

Ba changeset đã chạy trên production. Sau đó developer bổ sung file **020-add-customer-status.yaml** vào includeAll. Khi khởi tạo một database mới, thứ tự nạp trở thành:

~~~text
010 -> 020 -> 030 -> 050
~~~

Nhưng trên production đã có lịch sử 010, 030 và 050. Liquibase sẽ nhận ra chỉ còn **020** chưa chạy nên thực thi 020 ở thời điểm hiện tại, tức sau khi production đã hoàn tất 030 và 050.

| Database | Trình tự thực thi theo thời gian |
|---|---|
| Database mới tạo từ changelog hiện tại | 010 → 020 → 030 → 050 |
| Production đã chạy release cũ | 010 → 030 → 050 → 020 |

Hai database có thể kết thúc ở schema giống nhau nếu các thao tác hoàn toàn độc lập. Nhưng nếu 030 phụ thuộc vào dữ liệu hoặc cấu trúc của 020, kết quả có thể khác nhau hoặc migration sẽ thất bại. Việc bổ sung file ở một vị trí nằm giữa lịch sử cũ còn làm khó việc tái hiện chính xác các bước triển khai production.

Quy tắc thực hành:

1. Sau khi một chuỗi migration đã phát hành, **bổ sung changeset mới ở cuối thứ tự lịch sử**.
2. Với include tường minh, thêm chỉ thị include mới sau các include đã phát hành.
3. Với includeAll, dùng tên số thứ tự mới lớn hơn các số đã phát hành và kiểm tra thứ tự tài nguyên thực tế.
4. Không đổi tên file cũ chỉ để đưa nó vào vị trí tên mới.
5. Đánh giá phụ thuộc và thứ tự trên cả database sạch lẫn database đang chạy bản cũ.
6. Nếu cần thay đổi cấu trúc đã triển khai, tạo changeset bổ sung thay vì sửa file đã triển khai.

Việc **append-only** về lịch sử giúp các lần nâng cấp đi theo một tiến trình ổn định và giảm khoảng cách hành vi giữa khởi tạo database mới và nâng cấp database đã tồn tại.

## 10. Định danh changeset khi tệp được include

Liquibase nhận diện một changeset chủ yếu bằng bộ ba **id + author + đường dẫn tệp changelog**. Đường dẫn này có thể là đường dẫn logic nếu dự án chủ động cấu hình logicalFilePath theo cơ chế được hỗ trợ.

Giả sử file changes/2026/010-create-customer.yaml chứa:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 010
      author: team-a
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
~~~

Khi được áp dụng, DATABASECHANGELOG ghi nhận các thông tin gồm ID, AUTHOR, FILENAME, MD5SUM, DATEEXECUTED và EXECTYPE. Tên và vị trí của file changelog có thể ảnh hưởng FILENAME được lưu.

Sau một thời gian, nếu đổi đường dẫn từ changes/2026/010-create-customer.yaml sang archive/010-create-customer.yaml mà không duy trì định danh logic phù hợp, Liquibase có thể xem changeset ở vị trí mới là changeset khác chưa được thực thi. Điều này có thể dẫn đến lỗi trùng bảng hoặc áp dụng lại thao tác nguy hiểm.

**logicalFilePath** là cơ chế giúp giữ định danh logic ổn định trong những trường hợp cần thay đổi đường dẫn vật lý. Tuy nhiên, phạm vi khai báo và khả năng kế thừa logicalFilePath có thể thay đổi theo phiên bản Liquibase và định dạng changelog. Trước khi tái cấu trúc tệp đã triển khai, nhóm phải kiểm tra lịch sử FILENAME thực tế, tài liệu của phiên bản đang dùng và thử migration trên bản sao database có lịch sử cũ.

Tương tự, không sửa nội dung changeset đã chạy để thay đổi thứ tự. Liquibase lưu checksum, và thay đổi nội dung có thể gây lỗi xác thực checksum. **Tạo changeset mới** là cách thông thường để điều chỉnh kết quả đã triển khai.

Cũng cần nhớ: xóa một chỉ thị include khỏi master không có nghĩa Liquibase tự rollback changeset cũ. Bảng lịch sử của database vẫn lưu những gì đã thực thi. Việc thay đổi cây include chỉ ảnh hưởng tập changelog được đọc trong các lần chạy tiếp theo.

## 11. Context, label, DBMS và precondition tác động thế nào?

Thứ tự include xác định thứ tự **xét** changeset. Tuy nhiên, một changeset có thể được chọn hoặc bỏ qua bởi các điều kiện riêng.

| Cơ chế | Vai trò | Có tự thay đổi thứ tự include không? |
|---|---|---|
| Context | Lọc changeset theo ngữ cảnh triển khai | Không |
| Label | Lọc changeset theo nhãn do nhóm định nghĩa | Không |
| dbms | Chỉ áp dụng changeset cho loại DBMS được chỉ định | Không |
| preConditions | Kiểm tra trạng thái database trước khi thực hiện | Không |
| DATABASECHANGELOG | Cho biết changeset nào đã được ghi nhận | Không, nhưng làm thay đổi tập changeset pending |
| runOnChange / runAlways | Điều khiển việc chạy lại changeset theo quy tắc Liquibase | Không |

Ví dụ, tệp seed dữ liệu kiểm thử có thể được nạp trong master nhưng được gắn context bắt buộc:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 060-seed-test-customer
      author: schema-team
      context: "@test"
      changes:
        - insert:
            tableName: customer
            columns:
              - column:
                  name: id
                  valueNumeric: 900001
              - column:
                  name: email
                  value: test@example.invalid
~~~

Context bắt buộc có tiền tố @ yêu cầu filter tương ứng khi chạy trong các phiên bản Liquibase hỗ trợ cú pháp đó. Điều này hữu ích vì **nếu không có context filter**, một changeset gắn context thông thường có thể vẫn được Liquibase thực thi. Không nên cho rằng chỉ cần gắn context: test là production tự động bỏ qua changeset.

Changelog con có thể được nạp vào cây nhưng một số changeset bên trong không chạy ở môi trường nhất định. Điều này không làm Liquibase chuyển những changeset được chọn lên đầu danh sách; chúng vẫn được xét theo vị trí vốn có.

**Precondition không dùng để che giấu một thứ tự include sai.** Nếu migration B cần bảng do A tạo, nên để A trước B, đồng thời có thể dùng precondition để dừng triển khai khi trạng thái thật không đúng. Các lựa chọn như HALT, WARN, CONTINUE hoặc MARK_RAN cần được đánh giá kỹ vì chúng ảnh hưởng đến kết quả và lịch sử triển khai.

## 12. Thiết kế thứ tự an toàn khi nhiều nhóm cùng phát triển

Khi nhiều nhánh feature được phát triển song song, mỗi nhóm có thể thêm file mới. Xung đột không chỉ nằm trong mã nguồn mà còn ở **thứ tự migration**.

Một ví dụ:

- Nhóm Customer tạo bảng customer mới.
- Nhóm Billing tạo bảng invoice chứa customer_id.
- Nhóm Reporting tạo view dựa trên cả customer và invoice.

Thứ tự phụ thuộc hợp lý là tạo customer, tạo invoice với ràng buộc cần thiết, sau đó tạo view. Nếu hai pull request được merge với số thứ tự trùng nhau hoặc master chèn include không đúng vị trí, database trống có thể không khởi tạo được.

Một quy trình nhóm có thể áp dụng:

1. Mỗi pull request khai báo tệp migration và mục đích của các changeset.
2. Reviewer xác định các bảng, cột, constraint và dữ liệu được sử dụng bởi changeset mới.
3. Các migration có phụ thuộc được sắp theo thứ tự rõ ràng trong master hoặc bằng quy ước tên được CI kiểm tra.
4. Sau khi merge một pull request khác, developer chạy lại kiểm tra thứ tự với phiên bản master mới nhất.
5. CI thử migration lên database trống và lên database có lịch sử của release trước.
6. Khi phát hành, promote cùng revision changelog đã được kiểm chứng qua mọi môi trường.

Không nên dùng thời gian tạo file hoặc thời gian commit để suy luận rằng file mới sẽ tự chạy sau. Nếu nhóm dùng includeAll, số thứ tự cần được phối hợp khi merge và tránh tạo file mới có tên được sắp vào giữa phần lịch sử đã phát hành.

Đối với migration phá vỡ tương thích, ví dụ đổi tên hoặc xóa cột đang được code cũ sử dụng, nên thiết kế theo hướng **expand–migrate–contract**: bổ sung cấu trúc mới, chuyển ứng dụng và dữ liệu dần dần, rồi mới xóa cấu trúc cũ ở release sau. Thứ tự include phải phản ánh các giai đoạn đó.

## 13. Tích hợp Spring Boot và công cụ build

Cùng một master changelog có thể được dùng bởi Spring Boot, Maven Liquibase Plugin, Gradle Liquibase Plugin hoặc Liquibase CLI. Điều cần thống nhất là **đường dẫn tài nguyên, revision và bộ tham số lọc**.

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  liquibase:
    change-log: classpath:db/changelog/db.changelog-master.yaml
    enabled: true
~~~

Ở đây Spring Boot tìm master changelog trong classpath của ứng dụng. Khi master sử dụng relativeToChangelogFile: true, các include con được giải quyết tương đối theo vị trí của parent.

Với Maven hoặc Gradle, plugin cần được cấu hình trỏ đến cùng master changelog. Cách gọi lệnh phụ thuộc build tool và phiên bản plugin; ví dụ những bước thường có gồm:

~~~text
validate  ->  status  ->  updateSQL  ->  review  ->  update
~~~

Không chạy update trên production chỉ để kiểm tra thứ tự. **Validate** giúp phát hiện nhiều lỗi cấu trúc hoặc tham chiếu changelog. **Status** cho biết thay đổi nào đang chờ theo database hiện tại. **UpdateSQL** giúp xem SQL được dự kiến thực thi. Để biết liệu thứ tự phụ thuộc có hoạt động đúng, vẫn cần thử chạy trên database kiểm thử có loại DBMS và dữ liệu đại diện.

Lưu ý những khác biệt dễ gây hiểu nhầm:

- Maven plugin có thể sử dụng đường dẫn file hệ thống, trong khi Spring Boot dùng đường dẫn classpath.
- Gradle task Liquibase có classpath riêng và có thể cần đưa resource vào đúng nơi plugin tìm kiếm.
- Bộ lọc context, label hoặc schema mặc định có thể khác giữa pipeline và runtime.
- Nhiều replica Spring Boot cùng khởi động có thể đồng thời cố cập nhật cùng database; DATABASECHANGELOGLOCK hỗ trợ khóa nhưng không thay thế một quy trình điều phối migration rõ ràng.

Nếu CI đã cập nhật database trước khi triển khai ứng dụng, nhóm có thể chọn tắt bước chạy Liquibase tự động trong runtime Spring Boot. Việc chọn một chủ thể chạy migration chính sẽ giúp kiểm soát thứ tự triển khai.

## 14. Kiểm chứng cây include trước khi phát hành

Một quy trình kiểm tra đáng tin cậy cần kiểm tra được cả **cây tệp** lẫn **trạng thái thực tế của database**.

### Bước 1: Review master và các tệp con

Đọc master theo thứ tự từ trên xuống, theo tiếp từng include lồng nhau. Xác định:

- Có file nào bị thiếu hoặc đường dẫn nào bị giải quyết sai không?
- Có include trùng, include vòng hoặc includeAll quét nhầm file không?
- Có thay đổi nào phụ thuộc vào bảng/cột chưa được tạo không?
- File mới có vô tình nằm trước file thuộc release cũ không?
- Có đổi tên hoặc di chuyển file đã triển khai không?

### Bước 2: Chạy validate và sinh SQL dự kiến

Chạy Liquibase validate và updateSQL bằng cấu hình của môi trường thử nghiệm. Đọc đầu ra và xác nhận thứ tự DDL/DML như mong đợi: tạo bảng trước khi thêm cột, tạo khóa ngoại sau bảng tham chiếu, chuyển dữ liệu sau khi schema đích đã sẵn sàng.

Cần nhớ: validate thành công không có nghĩa SQL có thể thực thi trên DBMS thật; updateSQL cũng chỉ sinh SQL, chưa bảo đảm migration chạy thành công hoặc dữ liệu được giữ đúng.

### Bước 3: Thử với database sạch

Tạo database thử nghiệm rỗng và chạy toàn bộ changelog. Thao tác này kiểm tra lịch sử từ đầu tới cuối theo thứ tự nạp hiện tại. Sau đó xác minh schema, dữ liệu mẫu cần thiết và lịch sử DATABASECHANGELOG.

### Bước 4: Thử nâng cấp từ release trước

Dùng bản sao database có lịch sử triển khai của release trước, rồi chạy cùng revision changelog mới. So sánh kết quả với database sạch ở bước 3. Đây là cách phát hiện lỗi do file mới bị chèn vào giữa lịch sử hoặc do dữ liệu cũ không đáp ứng điều kiện migration.

### Bước 5: Kiểm tra sau triển khai

Trong database đích, đối chiếu DATABASECHANGELOG với revision đã được phát hành, kiểm tra những changeset còn pending và kiểm tra schema thật. Không sửa trực tiếp DATABASECHANGELOG để ép thứ tự hay để bỏ qua một lỗi checksum.

Đối với hệ thống production nhiều môi trường, ghi nhận commit hoặc artifact đã phát hành cùng kết quả kiểm tra migration. Điều này giúp tái hiện đúng tập tệp và thứ tự đã được dùng tại thời điểm triển khai.

## 15. Những sai lầm thường gặp với include

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không tìm thấy changelog con | Sai relativeToChangelogFile hoặc sai classpath/search path | Kiểm tra đường dẫn theo vị trí parent và cách chạy Liquibase |
| Tạo khóa ngoại lỗi vì thiếu bảng | Include bị đảo thứ tự hoặc file phụ thuộc được nạp quá sớm | Sắp lại thứ tự trước khi phát hành; thêm kiểm tra phụ thuộc |
| Database mới chạy khác production | File mới được chèn vào giữa phần lịch sử đã triển khai | Bổ sung migration mới ở cuối lịch sử; thử cả hai trạng thái database |
| IncludeAll nạp file không mong muốn | Thư mục chứa file nháp, tài liệu hoặc file không được lọc | Tách thư mục changelog và dùng cơ chế lọc được hỗ trợ |
| Changeset cũ bị hiểu là chưa chạy | File bị đổi tên/di chuyển làm thay đổi đường dẫn định danh | Kiểm tra FILENAME trong DATABASECHANGELOG và chiến lược logicalFilePath |
| Checksum mismatch | Changeset đã triển khai bị chỉnh sửa | So sánh với revision cũ, tạo changeset bổ sung nếu cần |
| Staging chạy được nhưng production lỗi | Khác dữ liệu, quyền, DBMS, context/label hoặc lịch sử | Kiểm tra đúng database, SQL dự kiến và tập changeset pending |
| Một thay đổi bị khai báo nhiều nơi | Include trùng hoặc copy changeset thiếu kiểm soát | Loại bỏ đường nạp thừa và xác định một nơi sở hữu changeset |
| Bỏ include cũ nhưng bảng vẫn còn | Xóa include không tương đương rollback | Tạo migration có chủ đích nếu thật sự cần thay đổi schema |
| Migration chờ hoặc lỗi khóa | Tiến trình khác đang giữ DATABASECHANGELOGLOCK | Xác định tiến trình và trạng thái trước khi xử lý lock |

Nếu gặp lỗi, nên ghi lại thông tin không nhạy cảm về phiên bản Liquibase, DBMS, tên database/schema, commit đã deploy và thông tin changeset. Tránh sao chép mật khẩu, token hoặc dữ liệu nhạy cảm vào log.

## 16. Thực hành: thiết kế thứ tự include cho một ứng dụng

Giả sử bạn cần xây dựng schema quản lý đơn hàng gồm hai bảng customer và purchase_order. Bảng purchase_order có khóa ngoại customer_id trỏ tới customer.id.

Tổ chức các tệp:

~~~text
db.changelog-master.yaml
changes/
  001-create-customer.yaml
  002-create-order.yaml
  003-add-order-customer-fk.yaml
  004-add-order-status.yaml
~~~

Master changelog:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-create-order.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/003-add-order-customer-fk.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/004-add-order-status.yaml
      relativeToChangelogFile: true
~~~

Các file con cần bảo đảm:

- 001 tạo bảng customer và khóa chính id.
- 002 tạo bảng purchase_order với id và customer_id có kiểu phù hợp.
- 003 thêm ràng buộc khóa ngoại tới customer.id; nó phụ thuộc vào 001 và 002.
- 004 thêm cột status vào purchase_order.

Một cách tự kiểm tra: nếu đổi include của 003 lên đầu master thì chuyện gì xảy ra trên database sạch? Câu trả lời là thay đổi tạo khóa ngoại có thể thất bại vì các bảng chưa tồn tại. Nếu cần kiểm tra trạng thái trước khi chạy, có thể thêm precondition để yêu cầu các bảng cần thiết tồn tại; điều đó không thay thế việc sắp xếp lại đúng thứ tự.

Bây giờ giả sử cả bốn changeset đã phát hành. Developer cần bổ sung một index cho purchase_order.status. File mới nên được đặt ở cuối danh sách, chẳng hạn **005-create-order-status-index.yaml**, đồng thời thêm include mới sau 004. Không sửa lại 004 hay chèn 005 lên trước các migration đã triển khai.

Hãy thực hành hai lần trên hai database thử nghiệm độc lập: một database trống và một database đã chạy bốn changeset đầu. Sau khi thêm 005, database trống phải thực hiện 001 → 002 → 003 → 004 → 005; database đã nâng cấp chỉ cần thực hiện 005 trong lần update tiếp theo. Cả hai phải có schema cuối và các ràng buộc như dự kiến.

## 17. Checklist quản lý include trước khi merge

- [ ] Chỉ có một master changelog chính cho đường triển khai đã chọn.
- [ ] Mọi include có đường dẫn đúng theo vị trí parent; relativeToChangelogFile được dùng nhất quán.
- [ ] Mỗi changelog con chứa changeset với id và author rõ ràng.
- [ ] Thứ tự include thể hiện được quan hệ phụ thuộc giữa bảng, cột, index, constraint và dữ liệu.
- [ ] Nếu dùng includeAll, tên file và quy tắc sắp xếp đã được kiểm tra.
- [ ] Không có include vòng, include trùng hoặc file không liên quan bị quét vào.
- [ ] File đã triển khai không bị di chuyển hoặc đổi tên khi chưa xử lý định danh logic.
- [ ] Không sửa changeset đã triển khai; thay đổi mới được bổ sung ở cuối lịch sử.
- [ ] Context, label, DBMS và precondition đã được đánh giá đúng với môi trường.
- [ ] Đã chạy validate, status và xem SQL dự kiến bằng cấu hình tương ứng.
- [ ] Đã thử trên database sạch và database có lịch sử release trước.
- [ ] Changelog, dependency, artifact và cấu hình đã được ghim cho CI/CD.
- [ ] Sau update đã kiểm tra DATABASECHANGELOG và schema thực tế.

**Điểm cần ghi nhớ:** include cho phép **chỉ rõ từng tệp và thứ tự của chúng**; includeAll giúp **nạp cả thư mục theo quy tắc sắp xếp tài nguyên**. Liquibase xét changeset theo cây changelog đã mở rộng, rồi đối chiếu với lịch sử của database đích để xác định việc thực thi. Vì thế, muốn quản lý migration bền vững qua nhiều môi trường, nhóm phải giữ ổn định định danh changeset, bổ sung migration theo tiến trình phát hành và kiểm chứng thứ tự trên cả database mới lẫn database đã tồn tại.

