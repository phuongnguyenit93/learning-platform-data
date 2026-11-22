# Vai trò của changelog gốc và cách tổ chức cây tệp

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase giúp quản lý thay đổi schema và dữ liệu theo lịch sử có thể kiểm chứng: changelog xác định tập thay đổi, changeset định danh từng bước, precondition kiểm tra điều kiện, checksum phát hiện chỉnh sửa ngoài dự kiến, còn các bảng lịch sử cho biết bước nào đã triển khai. Để những cơ chế này vận hành nhất quán trên máy phát triển, môi trường kiểm thử, staging và production, dự án cần một **changelog gốc** và một **cây tệp migration** có quy ước rõ ràng.

Bài học thuộc chương **Changelog** này giải thích changelog gốc làm gì, Liquibase đọc cây tệp ra sao, nên đặt file ở đâu và cách tránh các lỗi thường gặp khi nhóm nhiều người cùng bổ sung migration. Ví dụ dùng YAML và PostgreSQL, song các nguyên tắc về thứ tự, định danh, đường dẫn và lịch sử cũng áp dụng khi changelog dùng XML, JSON hoặc SQL có định dạng Liquibase.

## 1. Changelog gốc là điểm vào của lịch sử migration

**Changelog** là tài liệu hướng dẫn Liquibase tìm và xử lý các thay đổi database. Một changelog có thể chứa trực tiếp các changeset hoặc tham chiếu đến những changelog khác. **Changelog gốc** (*root/master changelog*) là file mà ứng dụng, CLI hoặc pipeline khai báo làm điểm bắt đầu đọc.

Ví dụ, trong ứng dụng Spring Boot:

~~~yaml
spring:
  liquibase:
    change-log: classpath:db/changelog/db.changelog-master.yaml
~~~

Đường dẫn trên cho Spring Boot biết cần tải file nào khi kích hoạt Liquibase. Từ file gốc, Liquibase lần theo các phần tử **include** hoặc **includeAll**, đọc những changeset được tham chiếu rồi quyết định changeset nào cần thực thi trên database hiện tại.

Changelog gốc thường đảm nhiệm bốn việc:

1. **Công bố một điểm vào ổn định.** Ứng dụng và pipeline đều tham chiếu cùng đường dẫn đã được kiểm soát phiên bản.
2. **Xác định phạm vi và thứ tự.** Người review nhìn được các nhóm migration được nạp và quan hệ trước sau của chúng.
3. **Tổ chức lịch sử.** Các file con có thể tách theo giai đoạn, tính năng hoặc domain, giúp tìm và review changeset dễ hơn.
4. **Giữ tính tái tạo.** Từ cùng mã nguồn và một database đáp ứng điều kiện ban đầu, Liquibase có thể áp dụng chuỗi thay đổi theo thứ tự đã khai báo.

Changelog gốc không nhất thiết có tên cố định. Các tên như **db.changelog-master.yaml**, **db.changelog-root.yaml** hoặc **master.xml** đều có thể sử dụng; tên thực tế phải khớp chính xác với cấu hình chạy Liquibase. Changelog gốc cũng không bắt buộc phải chỉ chứa include, nhưng đặt phần lớn changeset trong file con thường giúp dự án mở rộng và review tốt hơn.

### Cây file và lịch sử database là hai đối tượng khác nhau

Cây tệp trong Git mô tả **những thay đổi đã được khai báo**. Database đích chứa lịch sử **những thay đổi thực sự được ghi nhận là đã chạy** trong bảng **DATABASECHANGELOG**. Khi thực thi, Liquibase so sánh changeset tìm thấy trong cây với lịch sử ở database. Những changeset đã chạy bình thường sẽ không tự động chạy lại ở mỗi lần khởi động ứng dụng; các ngoại lệ như **runAlways** hoặc **runOnChange** phải được cấu hình có chủ đích.

Bảng **DATABASECHANGELOGLOCK** hỗ trợ điều phối việc cập nhật để tránh nhiều tiến trình Liquibase cùng sửa schema trên cùng database. Nó không giải quyết lỗi về thứ tự giữa hai file, cũng không thay thế việc review cây changelog.

## 2. Cây tệp tối thiểu cho một ứng dụng

Với ứng dụng Spring Boot, cấu trúc dễ bắt đầu là:

~~~text
customer-service/
└── src/
    └── main/
        └── resources/
            ├── application.yml
            └── db/
                └── changelog/
                    ├── db.changelog-master.yaml
                    └── changes/
                        ├── 001-create-customer.yaml
                        ├── 002-create-order.yaml
                        └── 003-add-order-index.yaml
~~~

Trong cấu trúc này:

- **application.yml** cấu hình đường dẫn đến changelog gốc.
- **db.changelog-master.yaml** là điểm vào và nêu thứ tự nạp các file.
- **changes/** chứa nội dung thay đổi thực tế, thường là các changeset.
- Phần số ở đầu tên file giúp người đọc hình dung trình tự; nó chỉ có giá trị sắp xếp tự động nếu cách include được chọn có quy tắc sắp xếp theo tên.

Nếu dùng Liquibase CLI và repository migration riêng, có thể giữ cùng cấu trúc logic dưới **db/changelog/**:

~~~text
database-migrations/
├── liquibase.properties
└── db/
    └── changelog/
        ├── db.changelog-master.yaml
        └── changes/
            ├── 001-create-customer.yaml
            ├── 002-create-order.yaml
            └── 003-add-order-index.yaml
~~~

Điểm khác là CLI dùng đường dẫn tệp trên hệ thống file hoặc đường dẫn tìm kiếm đã cấu hình, trong khi Spring Boot thường nạp changelog từ classpath. Cây migration nên được đóng gói và chạy với cùng phiên bản mã nguồn của ứng dụng liên quan, ngay cả khi migration được thực thi bởi job CI/CD riêng.

## 3. Khai báo changelog gốc bằng include

Tạo **db/changelog/db.changelog-master.yaml** với nội dung:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true

  - include:
      file: changes/002-create-order.yaml
      relativeToChangelogFile: true

  - include:
      file: changes/003-add-order-index.yaml
      relativeToChangelogFile: true
~~~

Mỗi phần tử **include** tham chiếu đến một changelog con. Liquibase đọc các include theo thứ tự xuất hiện trong changelog gốc; changeset trong từng file con cũng được duyệt theo thứ tự đã khai báo. Kết quả là một chuỗi changeset có thứ tự để Liquibase đối chiếu với lịch sử triển khai.

**relativeToChangelogFile: true** có nghĩa là đường dẫn **changes/001-create-customer.yaml** được hiểu tương đối với thư mục chứa **db.changelog-master.yaml**. Cách này giảm phụ thuộc vào thư mục làm việc khi chạy lệnh và thuận tiện khi đóng gói vào JAR. Nếu không dùng đường dẫn tương đối với changelog, Liquibase sẽ phân giải theo cơ chế resource/search path của môi trường đang chạy; điều này cần được cấu hình và kiểm tra rõ.

Để kiểm tra thực tế, hãy đảm bảo:

- File con tồn tại đúng tên, đúng phần mở rộng, đúng chữ hoa/chữ thường.
- File con khai báo định dạng hợp lệ, chẳng hạn YAML bắt đầu bằng **databaseChangeLog**.
- File master không vô tình include trùng file.
- Không có chu trình include dẫn ngược lại một file cha.
- Thứ tự include phản ánh phụ thuộc giữa các đối tượng database.

Không nên sửa tên file đã triển khai chỉ vì muốn các tên được sắp xếp đẹp hơn. Đường dẫn của file là một phần thông tin định danh changeset, sẽ được phân tích kỹ ở phần sau.

## 4. Các file con chứa changeset, không phải chương trình chạy tự do

Một file changelog con có thể chứa một hoặc nhiều changeset. Ví dụ **changes/001-create-customer.yaml**:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "001-create-customer"
      author: "db-team"
      preConditions:
        - onFail: HALT
        - not:
            - tableExists:
                tableName: customer
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
                  type: varchar(255)
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            tableName: customer
~~~

Ví dụ **changes/002-create-order.yaml**:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "002-create-order"
      author: "db-team"
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: customer
        - not:
            - tableExists:
                tableName: purchase_order
      changes:
        - createTable:
            tableName: purchase_order
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: customer_id
                  type: bigint
                  constraints:
                    nullable: false
                    foreignKeyName: fk_order_customer
                    referencedTableName: customer
                    referencedColumnNames: id
      rollback:
        - dropTable:
            tableName: purchase_order
~~~

Các đoạn YAML minh họa cú pháp và quan hệ phụ thuộc, không phải một schema nghiệp vụ hoàn chỉnh. Chi tiết về auto-increment, foreign key, kiểu dữ liệu và rollback phải được kiểm tra trên DBMS đích. Rollback bằng **dropTable** sẽ xóa dữ liệu trong bảng; chỉ thực thi khi đã đánh giá tác động.

Cây changelog ở đây thể hiện một phụ thuộc rõ ràng: bảng **customer** phải tồn tại trước khi tạo khóa ngoại từ **purchase_order**. Nếu hai file bị đảo thứ tự, migration thứ hai có thể thất bại, dù cả hai file đều hợp lệ về cú pháp.

Tệp **003-add-order-index.yaml** có thể chứa changeset bổ sung index phục vụ truy vấn. Theo cách này, mỗi thay đổi nằm trong một file dễ xem xét; khi thêm tính năng, nhóm bổ sung file mới và thêm include vào master.

### Một file có được chứa nhiều changeset?

Có. Ví dụ, một file cho chức năng *đơn hàng* có thể chứa changeset tạo bảng, tạo index và thêm dữ liệu tham chiếu. Tuy nhiên, chỉ nên gom các changeset có quan hệ rõ, vì cần review, định danh, rollback và kiểm tra được từng bước. Tên file không thay thế id của changeset; id và author vẫn phải được khai báo đầy đủ.

## 5. Hiểu đúng thứ tự thực thi

Có ba loại thứ tự mà người học cần phân biệt:

1. **Thứ tự khai báo:** trình tự include trong master và trình tự changeset trong các file con.
2. **Thứ tự lần đầu thực thi:** trên một database mới, Liquibase thường xét các changeset chưa được ghi nhận theo thứ tự khai báo, đồng thời áp dụng các điều kiện lọc hay precondition.
3. **Thứ tự còn pending trên một database đã triển khai:** Liquibase bỏ qua changeset đã được ghi nhận thành công trong DATABASECHANGELOG theo hành vi bình thường và tiếp tục xử lý các changeset chưa chạy.

Chẳng hạn, nếu môi trường staging đã chạy 001 và 002, lần tiếp theo chỉ bổ sung file 003, **update** sẽ xử lý 003. Nếu một lập trình viên chèn file 001b vào phía trước 002 sau khi 002 đã chạy ở staging, việc chèn này không khiến Liquibase quay về và chạy lại 002 để tái hiện đúng thứ tự lịch sử. File 001b vẫn là changeset pending và có thể chạy ở lần update mới, nhưng thứ tự thực tế đã xảy ra khác với thứ tự trên một database tạo mới.

Vì vậy, với thay đổi đã đi tới môi trường dùng chung, hãy **bổ sung migration mới ở cuối chuỗi triển khai** thay vì chèn một thay đổi phụ thuộc vào quá khứ rồi mặc định mọi môi trường sẽ có cùng thứ tự lịch sử.

### Khi cây có nhiều lớp

Một master có thể include changelog nhóm, rồi changelog nhóm tiếp tục include file thay đổi:

~~~text
db.changelog-master.yaml
├── modules/customer/customer-changelog.yaml
│   ├── 001-create-customer.yaml
│   └── 002-add-customer-status.yaml
└── modules/order/order-changelog.yaml
    ├── 001-create-order.yaml
    └── 002-add-order-index.yaml
~~~

Ví dụ file gốc:

~~~yaml
databaseChangeLog:
  - include:
      file: modules/customer/customer-changelog.yaml
      relativeToChangelogFile: true
  - include:
      file: modules/order/order-changelog.yaml
      relativeToChangelogFile: true
~~~

File trung gian **modules/customer/customer-changelog.yaml**:

~~~yaml
databaseChangeLog:
  - include:
      file: 001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: 002-add-customer-status.yaml
      relativeToChangelogFile: true
~~~

Mỗi cấp include được phân giải từ file cha tương ứng khi dùng đường dẫn tương đối. Phân cấp này giúp nhóm phụ trách domain sở hữu file riêng; master vẫn là nơi thể hiện thứ tự giữa các nhóm. Không nên chia tầng chỉ vì muốn có thật nhiều thư mục: với vài migration, một master và một thư mục **changes/** là đủ.

## 6. Include và includeAll khác nhau thế nào?

Liquibase hỗ trợ cả việc tham chiếu từng file bằng **include** và nạp nhiều file trong một thư mục bằng **includeAll**. Ví dụ:

~~~yaml
databaseChangeLog:
  - includeAll:
      path: changes/
      relativeToChangelogFile: true
~~~

Với **includeAll**, Liquibase tìm các changelog trong thư mục được chỉ định và thông thường xử lý chúng theo thứ tự tên file, tuân theo quy tắc của phiên bản và cấu hình Liquibase. Khi thiết kế includeAll, cần kiểm tra cả hành vi duyệt thư mục con, bộ lọc file và cách sắp xếp ở phiên bản đang dùng. Một file mới được đặt sai tên có thể thay đổi thứ tự thực thi dự kiến.

| Tiêu chí | include | includeAll |
|---|---|---|
| Khai báo | Chỉ rõ từng file theo thứ tự mong muốn | Chỉ rõ thư mục, Liquibase tìm các file phù hợp |
| Kiểm soát thứ tự | Tường minh trong master | Phụ thuộc quy tắc sắp xếp và bộ lọc |
| Thêm migration mới | Cần thêm dòng include | File mới có thể được tự động nạp |
| Review pull request | Dễ thấy việc thay đổi thứ tự | Phải kiểm tra cả nội dung và tên file |
| Rủi ro | Quên khai báo file mới, include trùng | Đưa nhầm file hoặc đổi thứ tự do đổi tên |
| Phù hợp | Dự án cần theo dõi chặt chuỗi phụ thuộc | Tập file được đặt tên và kiểm soát theo quy ước thống nhất |

Nếu chọn includeAll, nên dùng tên có tiền tố thứ tự cố định, chẳng hạn **001**, **002**, **010**. Tránh đặt tên **1**, **2**, **10** rồi giả định cách sắp xếp theo số tự nhiên; việc sắp xếp theo chuỗi có thể tạo thứ tự khác mong đợi.

Một số tính năng lọc, sắp xếp tùy chỉnh và điều khiển file của includeAll phụ thuộc phiên bản hoặc gói tính năng Liquibase. Không sao chép cấu hình đó vào dự án mà chưa chạy **validate** và xem thứ tự SQL dự kiến trên phiên bản đang sử dụng.

**Gợi ý:** bắt đầu với include tường minh, chuyển sang includeAll khi đã có quy ước thư mục, tên file và kiểm tra pipeline đủ mạnh. Tính tiện lợi của tự động quét file không bù được việc mất kiểm soát thứ tự trong các thay đổi có quan hệ phụ thuộc phức tạp.

## 7. Đường dẫn file tham gia định danh changeset

Liquibase xác định một changeset bằng tổ hợp thường được mô tả là **id + author + filename** (đường dẫn changelog theo cơ chế nhận diện của Liquibase). Trong DATABASECHANGELOG, các cột như **ID**, **AUTHOR** và **FILENAME** cho phép Liquibase đối chiếu changeset đã chạy. Đây là lý do file path không chỉ là chi tiết tổ chức thư mục.

Giả sử một changeset đã triển khai có:

~~~text
ID:       001-create-customer
AUTHOR:   db-team
FILENAME: db/changelog/changes/001-create-customer.yaml
~~~

Sau đó, nhóm di chuyển file sang **db/changelog/customer/001-create-customer.yaml** mà không quản lý định danh đường dẫn. Liquibase có thể xem changeset ở đường dẫn mới là một changeset khác. Khi đó, lệnh update có thể cố tạo lại bảng đã có hoặc tạo lịch sử không như mong muốn.

Nguyên tắc thực hành:

- Đường dẫn của file đã triển khai nên được giữ ổn định.
- Không sửa id hoặc author của changeset đã chạy ở môi trường dùng chung.
- Không chuyển file giữa các thư mục chỉ vì muốn tái tổ chức repository.
- Nếu buộc phải di chuyển, cần nghiên cứu và kiểm chứng cơ chế **logicalFilePath** phù hợp với phiên bản Liquibase, dùng một giá trị định danh logic ổn định, chạy thử trên database có lịch sử thật và database mới trước khi triển khai.
- Không dùng cách xóa hoặc sửa tay DATABASECHANGELOG để che lỗi nhận diện.

**logicalFilePath** là cách khai báo đường dẫn logic dùng trong nhận diện changeset trong các trường hợp phù hợp. Vị trí khai báo và cách kế thừa trong cây changelog phụ thuộc định dạng và phiên bản Liquibase; cần xác nhận ở môi trường cụ thể trước khi tái cấu trúc. Bài học không khuyến khích chuyển cây changelog đã chạy nếu không có nhu cầu đủ rõ và kế hoạch thử nghiệm.

Checksum giải quyết một câu hỏi khác: **nội dung changeset có thay đổi ngoài dự kiến so với bản đã chạy không?** Định danh bằng id/author/file và checksum là hai cơ chế bổ sung cho nhau. Sửa file đã chạy có thể dẫn đến lỗi checksum; đổi đường dẫn có thể khiến Liquibase nhận diện một changeset khác trước cả khi kiểm tra checksum theo lịch sử cũ.

## 8. Tổ chức theo domain, phiên bản hay môi trường?

Cây tệp không có một cấu trúc đúng cho mọi dự án. Hãy chọn cách tổ chức dựa trên số lượng changeset, mức độ phụ thuộc và cách nhóm review mã nguồn.

### Theo thứ tự thời gian

~~~text
db/changelog/
├── db.changelog-master.yaml
└── changes/
    ├── 2026-11-01-create-customer.yaml
    ├── 2026-11-04-create-order.yaml
    └── 2026-11-10-add-order-index.yaml
~~~

Dễ theo dõi chuỗi thay đổi; phù hợp dự án nhỏ hoặc một nhóm duy nhất. Nếu nhiều người tạo file cùng ngày, cần thêm mã duy nhất hoặc quy ước thứ tự để tránh trùng tên. Ngày trong tên file chỉ là gợi ý, không bảo đảm thứ tự triển khai ngoài thứ tự khai báo trong changelog.

### Theo domain

~~~text
db/changelog/
├── db.changelog-master.yaml
├── customer/
│   ├── customer-changelog.yaml
│   └── changes/
│       ├── 001-create-customer.yaml
│       └── 002-add-customer-status.yaml
└── order/
    ├── order-changelog.yaml
    └── changes/
        ├── 001-create-order.yaml
        └── 002-add-order-index.yaml
~~~

Phù hợp khi nhiều nhóm phụ trách các phần nghiệp vụ khác nhau. Root cần xác định thứ tự giữa các domain, nhất là khi bảng của domain này chứa khóa ngoại tham chiếu sang domain khác. Chỉ tách domain khi điều đó giúp giảm xung đột review; không nên mặc định mọi domain độc lập về migration.

### Theo đợt phát hành

~~~text
db/changelog/
├── db.changelog-master.yaml
├── release-1/
│   ├── 001-create-customer.yaml
│   └── 002-create-order.yaml
└── release-2/
    ├── 003-add-order-index.yaml
    └── 004-add-customer-status.yaml
~~~

Dễ liên hệ thay đổi với phiên bản ứng dụng, nhưng một migration có thể phải triển khai trước hoặc sau một đợt phát hành theo kế hoạch tương thích. Không nên tạo changelog hoàn toàn riêng cho mỗi release rồi mất một điểm vào lịch sử xuyên suốt. Tên folder release là cách tổ chức, không tự động trở thành điều kiện chạy.

### Có nên tạo một changelog gốc cho dev, một cho production?

Thông thường, **nên giữ cùng một cây lịch sử** cho các môi trường. Nếu development chạy root A còn production chạy root B, việc kiểm chứng rằng chúng có cùng các changeset cốt lõi trở nên khó khăn. Khác biệt môi trường thường nên nằm ở kết nối, cấu hình hoặc điều kiện chạy được mô tả có chủ đích.

Liquibase hỗ trợ **context**, **label** và các điều kiện phụ thuộc DBMS để lựa chọn changeset phù hợp. Tuy nhiên, mỗi thay đổi có điều kiện vẫn phải được review và kiểm chứng trên các môi trường đích; không nên dùng context để bỏ qua những schema change cốt lõi một cách tùy tiện. Dữ liệu thử nghiệm và các thao tác chỉ dành cho dev cần được tách bạch, tránh vô tình nạp vào production.

## 9. Khi nào dùng context, label và sqlFile trong cây changelog?

Một changeset có thể mang nhãn hoặc điều kiện để kiểm soát phạm vi chạy. Ví dụ, một changeset chỉ dành cho dữ liệu thử nghiệm có thể sử dụng context theo quy ước của nhóm:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "seed-demo-customer"
      author: "db-team"
      context: "dev"
      changes:
        - insert:
            tableName: customer
            columns:
              - column:
                  name: id
                  valueNumeric: 9999
              - column:
                  name: email
                  value: demo@example.test
~~~

Ví dụ này chỉ nhằm minh họa cấu trúc metadata context. Cách Liquibase diễn giải context và giá trị filter khi chạy còn tùy cấu hình thực thi và phiên bản; nếu muốn bảo đảm dữ liệu chỉ được nạp ở dev, phải thiết lập context filter phù hợp trong lệnh hoặc ứng dụng và thử cả trường hợp không có filter. Không được giả định gắn context tự động chặn changeset ở mọi lần chạy production.

**label** có thể dùng để phân nhóm changeset theo một thuộc tính triển khai, còn các điều kiện **dbms** hoặc precondition có thể giới hạn hành vi theo hệ quản trị database. Chúng làm rõ phạm vi của thay đổi nhưng không thay thế việc kiểm soát root changelog và review từng migration.

Khi nội dung SQL dài, có thể viết **sqlFile** trong changeset để tham chiếu file SQL:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "005-backfill-customer-status"
      author: "db-team"
      changes:
        - sqlFile:
            path: sql/005-backfill-customer-status.sql
            relativeToChangelogFile: true
~~~

Khi đó file SQL vẫn nằm dưới quyền quản lý của changeset: Liquibase biết changeset nào sở hữu thao tác và ghi nhận trong DATABASECHANGELOG. Đường dẫn SQL phải phân giải đúng theo file chứa changeset; tên file nên ổn định sau triển khai. Nếu dùng SQL riêng, cần đánh giá khả năng rollback và tính an toàn của câu SQL trên dữ liệu thật.

## 10. Tích hợp một root changelog với Spring Boot, CLI và CI/CD

### Spring Boot

Khi changelog nằm dưới **src/main/resources/db/changelog/**:

~~~yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USER}
    password: ${DB_PASSWORD}
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Spring Boot tải root changelog qua classpath và Liquibase tiếp tục nạp file con. Đặt Hibernate ở **validate** giúp kiểm tra mapping hiện tại mà không tự sửa schema ngoài lịch sử Liquibase. Không nên đồng thời để Hibernate **update** và Liquibase cùng sở hữu thay đổi schema.

### Liquibase CLI

Với repository migration độc lập:

~~~properties
changeLogFile: db/changelog/db.changelog-master.yaml
url: jdbc:postgresql://localhost:5432/customer_db
username: customer_migrator
driver: org.postgresql.Driver
~~~

Driver PostgreSQL phải có trong classpath của CLI bằng cách cài đặt hoặc cấu hình phù hợp; ví dụ trên chưa mô tả đường dẫn driver. Mật khẩu được cấp qua biến môi trường hoặc secret store, không commit vào repository.

Từ thư mục chứa file cấu hình, có thể dùng:

~~~shell
liquibase --defaults-file=liquibase.properties validate
liquibase --defaults-file=liquibase.properties update-sql
liquibase --defaults-file=liquibase.properties status --verbose
liquibase --defaults-file=liquibase.properties update
~~~

**validate** kiểm tra cấu trúc changelog và các tham chiếu có thể đánh giá; **update-sql** giúp review câu lệnh dự kiến; **status** cho biết những changeset còn pending; chỉ **update** mới chủ động áp dụng thay đổi. Với pipeline production, lệnh thực thi cần được chạy sau các bước kiểm tra và phê duyệt phù hợp.

Nếu chạy bằng CLI và Spring Boot xen kẽ, hãy bảo đảm cả hai tham chiếu **cùng một lịch sử changeset** và có cách phân giải đường dẫn nhất quán. Kiểm tra FILENAME trong DATABASECHANGELOG khi đổi cơ chế chạy; khác biệt giữa đường dẫn classpath và filesystem có thể gây rủi ro nhận diện nếu cấu hình không được thống nhất và kiểm chứng.

### CI/CD

Pipeline nên sử dụng chính bộ changelog đã được review, đóng gói hoặc checkout từ cùng revision nguồn:

~~~text
Pull request
    |
    v
Validate changelog + kiểm tra file include
    |
    v
Chạy migration trên database thử nghiệm
    |
    v
Review schema, SQL dự kiến và kiểm tra ứng dụng
    |
    v
Đưa cùng bộ changelog tới staging/production
    |
    v
Áp dụng migration và xác minh DATABASECHANGELOG
    |
    v
Triển khai phiên bản ứng dụng tương thích
~~~

Nếu CI/CD sở hữu bước migration, một cấu hình Spring Boot runtime thích hợp có thể đặt **spring.liquibase.enabled=false** để tránh nhiều instance tự chạy lại. Dù Liquibase có lock hỗ trợ điều phối, ranh giới trách nhiệm rõ ràng vẫn giúp nhận diện lỗi và kiểm soát thời điểm migration.

## 11. Phát triển cây changelog trong nhóm nhiều người

Khi nhiều pull request cùng sửa master changelog, xung đột merge thường xuất hiện ở phần include. Đây là tín hiệu cần review thứ tự, không phải lý do để tự động lấy một trong hai phiên bản rồi bỏ qua nội dung còn lại.

Một quy trình hữu ích:

1. Mỗi tính năng tạo changeset mới có id và author ổn định.
2. Nhóm bổ sung include vào master hoặc changelog domain theo quy ước đã chọn.
3. Sau merge, kiểm tra không có file bị bỏ sót, include trùng hoặc đảo thứ tự.
4. Chạy validate và thử migration trên database sạch để kiểm tra toàn bộ chuỗi.
5. Chạy thêm trên database đã ở bản phát hành trước để phát hiện lỗi chỉ xảy ra ở đường nâng cấp.
6. Giữ changeset đã chạy trên môi trường dùng chung bất biến; sửa hành vi bằng changeset mới.

**Hai hướng kiểm thử cần có:** database mới kiểm tra khả năng dựng schema từ đầu; database đang ở phiên bản cũ kiểm tra nâng cấp thực tế. Cùng một cây changelog có thể thành công khi dựng mới nhưng thất bại khi nâng cấp vì có dữ liệu không đáp ứng constraint, hoặc vì changeset mới được chèn ngược vào lịch sử trước đó.

Nếu một thay đổi lớn cần triển khai qua nhiều phiên bản ứng dụng, hãy dùng chiến lược **expand → migrate → contract**: thêm cấu trúc tương thích, chuyển dữ liệu, xác nhận không còn phiên bản cũ phụ thuộc rồi mới xóa cấu trúc cũ. Các bước được ghi thành changeset mới ở những thời điểm phù hợp, không viết lại changeset đã triển khai.

## 12. Vấn đề thường gặp và cách kiểm tra

| Vấn đề | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| Không tìm thấy changelog con | Đường dẫn include sai hoặc tính tương đối với thư mục khác | Kiểm tra đường dẫn master, relativeToChangelogFile và vị trí file |
| Cấu hình CLI chạy được nhưng Spring Boot không chạy | File chưa được đóng gói vào classpath, khác root hoặc khác đường dẫn tìm kiếm | Xác minh resource trong artifact và cấu hình change-log |
| Database đã có bảng nhưng vẫn cố tạo | Changeset chưa được nhận diện trong DATABASECHANGELOG hoặc bị di chuyển/đổi định danh | Đối chiếu ID/AUTHOR/FILENAME và trạng thái schema trước khi sửa |
| Chạy file sai thứ tự | IncludeAll xếp theo tên hoặc merge làm đảo include | Dùng include tường minh, quy ước đặt tên và review thứ tự |
| Lỗi checksum | Nội dung changeset đã triển khai bị sửa | Tìm diff, khôi phục định nghĩa đã triển khai hoặc tạo changeset sửa tiếp |
| Hai nhóm cùng tạo index hoặc cột | Thiếu điều phối phụ thuộc, tên thay đổi trùng | Review các file liên quan và thêm precondition thích hợp |
| Chỉ một môi trường thiếu thay đổi | Khác root, context/label filter hoặc lịch sử triển khai | Đối chiếu cấu hình chạy, status và DATABASECHANGELOG |
| Migration chờ lâu | Một tiến trình khác đang giữ DATABASECHANGELOGLOCK | Kiểm tra log và tiến trình sở hữu trước khi dùng thao tác giải phóng lock |

Đặc biệt, không dùng **changelog-sync**, **clear-checksums** hoặc chỉnh tay **DATABASECHANGELOG** để che lỗi về cây file. Changelog-sync chỉ phù hợp cho quy trình baseline có đối chiếu trạng thái database; clear-checksums và các cơ chế chấp nhận checksum cần được đánh giá kỹ khi sửa lịch sử. Chúng không tự bảo đảm schema hiện tại đúng.

## 13. Bài thực hành: mở rộng cây changelog có kiểm chứng

Giả sử nhóm đang quản lý hệ thống cửa hàng với bảng customer và purchase_order, cần bổ sung index cho truy vấn đơn hàng theo khách hàng.

**Bước 1 — Chọn điểm vào.** Xác định file gốc đang được Spring Boot hoặc CLI sử dụng. Trong ví dụ này là **db/changelog/db.changelog-master.yaml**; giữ nguyên đường dẫn.

**Bước 2 — Tạo file mới.** Thêm **changes/003-add-order-index.yaml** với một changeset:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "003-add-order-index"
      author: "db-team"
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: purchase_order
        - not:
            - indexExists:
                tableName: purchase_order
                indexName: idx_order_customer
      changes:
        - createIndex:
            tableName: purchase_order
            indexName: idx_order_customer
            columns:
              - column:
                  name: customer_id
      rollback:
        - dropIndex:
            tableName: purchase_order
            indexName: idx_order_customer
~~~

**Bước 3 — Nối vào master.** Thêm include cho file 003 sau file 002. Nếu includeAll đang được sử dụng, bảo đảm tên mới theo quy ước và kiểm tra thứ tự thực tế của thay đổi.

**Bước 4 — Kiểm tra trước khi chạy.** Dùng **validate**, sau đó tạo **update-sql** để review. Thử trên database đã có customer và purchase_order; xác nhận chỉ index mới được tạo. Nếu database hoàn toàn rỗng, chạy toàn bộ cây để chắc chắn không có thiếu phụ thuộc.

**Bước 5 — Kiểm tra lịch sử.** Sau khi update thành công trên database thử nghiệm, xem DATABASECHANGELOG để xác nhận changeset 003 được ghi nhận đúng id, author và file. Chạy lại **status** để xem thay đổi còn pending hay không.

**Bước 6 — Đánh giá triển khai thật.** Với bảng lớn, việc tạo index có thể gây lock hoặc tăng tải tùy DBMS và cú pháp sử dụng. Cần kiểm tra phương án index online/concurrent nếu có, thời điểm chạy, timeout và cách rollback phù hợp. Không coi ví dụ trên là lệnh production đã tối ưu cho mọi database.

Kết quả cần đạt là thay đổi được tìm thấy qua root, áp dụng theo thứ tự, ghi nhận một lần trong lịch sử và có thể tái tạo trên database mới.

## 14. Checklist thiết kế changelog gốc

Trước khi đưa cây changelog vào quy trình chung, hãy tự kiểm tra:

- [ ] Root changelog nằm ở đường dẫn ổn định, được CLI/Spring Boot/CI sử dụng nhất quán.
- [ ] Cây file có quy tắc tổ chức rõ: theo thời gian, domain hoặc release.
- [ ] Các file con đều có định dạng hợp lệ và được include đúng một lần.
- [ ] Thứ tự include phù hợp với quan hệ phụ thuộc giữa bảng, index, constraint và dữ liệu.
- [ ] Nếu dùng includeAll, đã kiểm tra thứ tự và quy tắc lọc file theo phiên bản Liquibase.
- [ ] Đường dẫn, id, author của changeset đã triển khai được giữ ổn định.
- [ ] Không sửa changeset đã triển khai để chèn lại lịch sử.
- [ ] Có thể chạy validate và xem SQL dự kiến trước khi update.
- [ ] Đã thử chạy cây trên database sạch **và** database đang ở phiên bản cũ.
- [ ] Context, label và cấu hình môi trường được xét đến khi kiểm tra các changeset pending.
- [ ] Có cách đối chiếu DATABASECHANGELOG để kiểm tra thực tế triển khai.
- [ ] Các migration có rủi ro được đánh giá về rollback, thời gian chạy và tương thích ứng dụng.

Trong **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, changelog gốc không chỉ là danh sách tên tệp. Nó là **điểm vào có kiểm soát cho toàn bộ lịch sử thay đổi database**; cách tổ chức cây quyết định khả năng review, tái tạo, bảo trì và phối hợp giữa các môi trường. Đặt root ổn định, giữ định danh changeset bền vững và kiểm chứng thứ tự nạp là nền tảng để áp dụng precondition, checksum, rollback và triển khai Spring Boot hoặc CI/CD một cách đáng tin cậy.
