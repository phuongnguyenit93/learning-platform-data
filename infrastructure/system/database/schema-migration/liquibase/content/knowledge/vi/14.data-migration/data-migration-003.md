# Nạp dữ liệu CSV bằng loadData

Dữ liệu trong một hệ thống không chỉ xuất hiện từ thao tác của người dùng. Nhiều ứng dụng cần **dữ liệu tham chiếu** ngay từ lúc khởi tạo database: mã quốc gia, loại trạng thái, danh mục đơn vị đo, bảng cấu hình dùng chung hoặc dữ liệu khởi tạo phục vụ migration. Nếu các môi trường tự nhập dữ liệu bằng tay, cấu trúc và nội dung dễ lệch nhau. Liquibase cung cấp change type **loadData** để đọc dữ liệu từ tệp CSV và đưa các dòng vào một bảng đã tồn tại theo một changeset có lịch sử triển khai.

Bài thuộc chương **Chuyển đổi dữ liệu** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Mục tiêu của module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Ở đây, trọng tâm là cách định dạng CSV, khai báo loadData, ánh xạ cột và kiểu, quản lý đường dẫn/encoding, kiểm thử trên database mới và đã có dữ liệu, đồng thời kiểm soát việc lặp dữ liệu, rollback và vận hành.

## 1. loadData làm gì, và không làm gì?

**loadData** là một change type đọc tệp dữ liệu phân tách theo ký tự, thường là dấu phẩy, rồi thực hiện thao tác nạp các bản ghi vào bảng mục tiêu. Nó thường được đặt trong một changeSet của changelog YAML, XML hoặc JSON. Liquibase xác định changeset có cần chạy hay không dựa trên danh tính và lịch sử thay đổi trên database đích.

Ví dụ bài toán: ứng dụng cần bảng country chứa danh sách quốc gia tối thiểu để hiển thị trong biểu mẫu. Một changeset tạo bảng country, changeset tiếp theo nạp danh sách bằng CSV. Khi triển khai môi trường mới, các bản ghi tham chiếu được tạo cùng phiên bản ứng dụng; khi nâng cấp môi trường cũ, Liquibase dùng lịch sử changeset để không chèn lại một changeset đã hoàn thành trong luồng update thông thường.

Các điều loadData **không** tự bảo đảm:

- Không tự thiết kế hoặc tạo bảng; bảng và các cột phải tồn tại với kiểu/constraint phù hợp trước khi nạp.
- Không mặc định kiểm tra và bỏ qua các dòng đã có khóa trùng. Về bản chất, nó phục vụ **nạp dữ liệu**, không phải một phép upsert tổng quát.
- Không tự làm sạch dữ liệu sai, suy luận mối quan hệ khóa ngoại hoặc giải quyết thứ tự phụ thuộc giữa các bảng.
- Không tự tạo phương án khôi phục dữ liệu an toàn khi rollback.
- Không tự bảo đảm nội dung CSV đã triển khai ở các phiên bản trước là bất biến; nhóm cần kỷ luật quản lý tệp trong source control.

Với nhu cầu cập nhật hoặc chèn theo khóa ổn định, cần cân nhắc **loadUpdateData**, changeset SQL riêng hoặc một quy trình đồng bộ dữ liệu phù hợp. Không chuyển từ loadData sang loadUpdateData một cách máy móc, vì ý nghĩa cập nhật bản ghi hiện hữu hoàn toàn khác với nạp dữ liệu ban đầu.

## 2. CSV là hợp đồng dữ liệu, không chỉ là một tệp văn bản

CSV (comma-separated values) thường gồm một dòng tiêu đề và các dòng dữ liệu. Cách Liquibase phân tách trường phụ thuộc vào dấu phân tách, ký tự bao chuỗi và encoding được cấu hình.

Ví dụ tệp **countries.csv**:

~~~csv
code,name,region,active
VN,Viet Nam,APAC,true
JP,Japan,APAC,true
US,United States,AMER,true
~~~

Tệp này mô tả bốn cột:

| Cột CSV | Ý nghĩa | Kiểu database dự kiến | Ví dụ |
|---|---|---|---|
| code | Mã quốc gia ổn định | VARCHAR(2) / khóa chính | VN |
| name | Tên hiển thị | VARCHAR(120) | Viet Nam |
| region | Nhóm khu vực | VARCHAR(12) | APAC |
| active | Trạng thái sử dụng | BOOLEAN | true |

**Dòng đầu thường là header.** Tên header trong CSV phải khớp với khai báo ánh xạ nếu bạn dùng thuộc tính header. Tránh viết nhầm tên, thừa khoảng trắng hoặc xuất CSV có cột phụ không được xử lý rõ ràng.

Một trường có dấu phẩy cần được bao bằng dấu nháy kép, nếu dấu phân tách đang là dấu phẩy:

~~~csv
code,name,region,active
VN,"Viet Nam",APAC,true
KR,"Korea, Republic of",APAC,true
~~~

Dấu nháy kép bên trong một trường được thể hiện theo quy tắc CSV bằng cách lặp đôi dấu nháy trong trường đã được quote:

~~~csv
code,name,region,active
XX,"Sample ""quoted"" country",TEST,false
~~~

Đừng tự dùng thao tác tách chuỗi tại mọi dấu phẩy để “kiểm tra” CSV: cách đó không hiểu dấu phẩy nằm trong giá trị được quote. Hãy dùng parser CSV có xử lý quoting hoặc chính luồng Liquibase trong môi trường thử nghiệm.

### 2.1. Chọn encoding và ký tự phân tách

Tệp CSV nên được lưu UTF-8 nhất quán, đặc biệt nếu tên chứa dấu tiếng Việt hoặc ký tự ngoài ASCII. Một số công cụ spreadsheet có thể xuất tệp với UTF-8 BOM hoặc encoding khác; cần kiểm tra header sau khi xuất để tránh cột đầu bị nhận diện sai.

Nhiều nguồn xuất CSV sử dụng dấu chấm phẩy thay vì dấu phẩy do cấu hình vùng. Nếu tệp dùng dấu chấm phẩy, phải khai báo separator tương ứng. Không nên dựa vào phần mở rộng .csv để kết luận nội dung luôn dùng dấu phẩy.

Với trường văn bản chứa xuống dòng, cần kiểm tra parser, quoting và format của phiên bản Liquibase cụ thể. CSV không có một quy tắc locale tự động đủ tin cậy cho mọi kiểu số, ngày và Boolean.

## 3. Chuẩn bị bảng đích trước khi nạp

Cấu trúc tham khảo cho ứng dụng Spring Boot:

~~~text
src/main/resources/db/changelog/
├── db.changelog-master.yaml
├── changes/
│   ├── 001-create-country.yaml
│   └── 002-load-country.yaml
└── data/
    └── countries.csv
~~~

Tệp changelog gốc điều phối hai bước theo thứ tự:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/001-create-country.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-load-country.yaml
      relativeToChangelogFile: true
~~~

Bước một tạo bảng đích:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-country
      author: database-team
      changes:
        - createTable:
            tableName: country
            columns:
              - column:
                  name: code
                  type: VARCHAR(2)
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: name
                  type: VARCHAR(120)
                  constraints:
                    nullable: false
              - column:
                  name: region
                  type: VARCHAR(12)
                  constraints:
                    nullable: false
              - column:
                  name: active
                  type: BOOLEAN
                  constraints:
                    nullable: false
~~~

Bảng country dùng **code làm khóa chính ổn định**, giúp các dữ liệu tham chiếu dễ liên kết mà không phải giả định các giá trị ID tự tăng luôn giống nhau giữa local, staging và production.

Trên hệ thống thật, cấu trúc bảng và constraint có thể phức tạp hơn. Điều quan trọng là **changeset tạo bảng phải chạy trước changeset loadData**, và giá trị mỗi cột CSV phải tương thích với kiểu cũng như quy tắc dữ liệu của bảng.

## 4. Viết changeset loadData bằng YAML

Tệp **changes/002-load-country.yaml**:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-load-country
      author: database-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: country
      changes:
        - loadData:
            file: ../data/countries.csv
            relativeToChangelogFile: true
            tableName: country
            encoding: UTF-8
            separator: ","
            quotchar: '"'
            columns:
              - column:
                  header: code
                  name: code
                  type: STRING
              - column:
                  header: name
                  name: name
                  type: STRING
              - column:
                  header: region
                  name: region
                  type: STRING
              - column:
                  header: active
                  name: active
                  type: BOOLEAN
      rollback:
        - delete:
            tableName: country
            where: "code IN ('VN', 'JP', 'US')"
~~~

Đây là một ví dụ **có chủ đích giới hạn**: CSV được thiết kế chứa ba mã VN, JP và US như mục 2. Nếu CSV thay đổi tập mã, phần rollback phải được xem xét và cập nhật tương ứng ở changeset mới, thay vì sửa ngầm changeset đã triển khai.

### 4.1. Ý nghĩa những thuộc tính chính

| Thuộc tính | Vai trò | Điều cần kiểm chứng |
|---|---|---|
| file | Tài nguyên CSV cần nạp | Đúng tên, đúng thư mục và có mặt trong artifact |
| relativeToChangelogFile | Diễn giải file tương đối so với changelog chứa loadData | Đường dẫn hoạt động khi chạy từ CLI lẫn JAR |
| tableName | Bảng sẽ nhận dữ liệu | Đã tồn tại trước khi changeset chạy |
| schemaName | Schema của bảng đích khi cần chỉ định | Không nạp nhầm bảng cùng tên ở schema khác |
| encoding | Cách giải mã ký tự của CSV | Khớp UTF-8 hoặc encoding nguồn thật |
| separator | Ký tự phân tách trường | Khớp file CSV, không làm vỡ giá trị có dấu phẩy |
| quotchar | Ký tự quote các trường CSV | Khớp cách công cụ xuất CSV |
| columns | Ánh xạ header/cột/kiểu | Không lệch tên, thứ tự hoặc kiểu |
| usePreparedStatements | Lựa chọn dùng prepared statements khi được phiên bản hỗ trợ | Cân nhắc kiểu dữ liệu, SQL sinh ra và hiệu năng |

Không phải mọi thuộc tính mở rộng đều có cùng hành vi ở mọi phiên bản Liquibase. Với các tùy chọn nâng cao như lọc dòng comment hoặc quy ước NULL, cần đối chiếu tài liệu và kiểm thử trên chính phiên bản runtime đang chạy.

### 4.2. header, name và type khác nhau thế nào?

Trong mỗi mục column của loadData:

- **header** là tên trường được đọc từ dòng tiêu đề CSV.
- **name** là tên cột đích của bảng trong database.
- **type** hướng dẫn Liquibase diễn giải giá trị CSV, ví dụ STRING, NUMERIC, DATE hoặc BOOLEAN theo tập kiểu được phiên bản hỗ trợ.

Nếu header CSV là country_code nhưng cột database tên code, có thể ánh xạ:

~~~yaml
columns:
  - column:
      header: country_code
      name: code
      type: STRING
~~~

Ví dụ này chỉ minh họa một mục của danh sách columns trong loadData. Trong changelog đầy đủ, phải khai báo các cột khác theo cấu trúc tương ứng.

Đừng nhầm **type của loadData** với câu khai báo kiểu SQL như VARCHAR(2) của createTable: một bên hướng dẫn chuyển đổi giá trị CSV, bên kia xác định kiểu thật trên database. Cần kiểm chứng cả hai phù hợp với nhau.

## 5. Viết tương đương bằng XML

Nếu dự án sử dụng XML changelog, có thể biểu diễn loadData như sau. Giả định tệp XML này nằm trong thư mục changes giống ví dụ YAML:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      http://www.liquibase.org/xml/ns/dbchangelog
      http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-latest.xsd">

    <changeSet id="002-load-country" author="database-team">
        <preConditions onFail="HALT" onError="HALT">
            <tableExists tableName="country"/>
        </preConditions>

        <loadData
            file="../data/countries.csv"
            relativeToChangelogFile="true"
            tableName="country"
            encoding="UTF-8"
            separator=","
            quotchar="&quot;">
            <column header="code" name="code" type="STRING"/>
            <column header="name" name="name" type="STRING"/>
            <column header="region" name="region" type="STRING"/>
            <column header="active" name="active" type="BOOLEAN"/>
        </loadData>

        <rollback>
            <delete tableName="country">
                <where>code IN ('VN', 'JP', 'US')</where>
            </delete>
        </rollback>
    </changeSet>

</databaseChangeLog>
~~~

Trong thuộc tính XML, dấu nháy kép dùng để bao chuỗi nên giá trị quote character được biểu diễn bằng entity XML **&quot;**. Phải giữ URI namespace và schemaLocation đúng với phiên bản Liquibase được dùng.

XML và YAML có mục tiêu tương đương ở đây. Dự án không cần pha trộn nhiều định dạng cho cùng một migration; hãy chọn cách tổ chức nhất quán, rõ ràng và dễ review.

## 6. Đường dẫn CSV: local, changelog tương đối và classpath

Với cấu trúc:

~~~text
db/changelog/
├── db.changelog-master.yaml
├── changes/
│   └── 002-load-country.yaml
└── data/
    └── countries.csv
~~~

Khi **002-load-country.yaml** chứa:

~~~yaml
file: ../data/countries.csv
relativeToChangelogFile: true
~~~

Liquibase sẽ tìm tài nguyên tương đối so với changelog con chứa loadData, tức là đi từ changes lên một cấp rồi vào data. Nếu thay đổi vị trí changelog con, đường dẫn tương đối cũng phải được đánh giá lại.

Các lỗi phổ biến:

1. Chạy được từ IDE nhưng thất bại trong JAR vì CSV không được đưa vào resources.
2. Tham chiếu đường dẫn tương đối theo thư mục làm việc của terminal thay vì theo changelog đang chứa loadData.
3. Một changelog gốc include nhiều changelog con, nhưng tác giả lại hiểu đường dẫn loadData luôn tương đối theo changelog gốc.
4. Tên tệp khác chữ hoa/chữ thường giữa môi trường Windows và Linux.
5. CSV nằm ngoài package/image triển khai hoặc bị pipeline loại khỏi artifact.

**Nguyên tắc:** Đóng gói changelog và CSV như một bộ tài nguyên version control; kiểm tra nội dung JAR/image thực tế, không chỉ kiểm tra đường dẫn lúc phát triển. Không lưu tệp chứa dữ liệu nhạy cảm hoặc credentials trong resources để phát hành rộng rãi.

## 7. Ánh xạ và chuyển kiểu dữ liệu an toàn

CSV về bản chất là văn bản. Ngay cả khi một trường nhìn giống số hoặc ngày, cần xác định rõ ý nghĩa trước khi ánh xạ.

### 7.1. Mã định danh có số 0 ở đầu

Ví dụ mã bưu chính hoặc mã chi nhánh có thể là 00125. Nếu khai báo NUMERIC, quá trình chuyển kiểu có thể làm mất những số 0 ở đầu. Nếu đó là **mã định danh** chứ không phải đại lượng số học, thường nên dùng STRING trong loadData và VARCHAR/CHAR ở bảng đích.

### 7.2. Số và định dạng vùng

Không tự giả định giá trị 1,234 mang ý nghĩa một nghìn hai trăm ba mươi tư hay số thập phân 1.234 trong mọi locale. Hãy chuẩn hóa định dạng CSV trước khi đưa vào changelog; với dữ liệu tiền tệ, kiểm tra độ chính xác của DECIMAL/NUMERIC trong bảng đích.

### 7.3. Ngày giờ và timezone

Với cột ngày, ưu tiên định dạng rõ ràng, ví dụ ISO 8601 theo khả năng parse của runtime và cấu hình DBMS, thay vì dạng mơ hồ như 03/04/26. Cần phân biệt DATE, TIMESTAMP, TIMESTAMP WITH TIME ZONE và chính sách timezone của ứng dụng. Trên môi trường nhiều vùng giờ, kết quả phải được kiểm thử thay vì giả định cách parse tự động.

### 7.4. Boolean

Các giá trị true/false của ví dụ cần được kiểm tra với kiểu BOOLEAN của loadData và DBMS. Không mặc định 1, Y, Yes và true đều được diễn giải tương đương ở mọi phiên bản Liquibase.

### 7.5. Cột không muốn nhập

Đôi khi CSV có một trường phục vụ ghi chú nội bộ hoặc cột được tạo tự động mà database không cần nhận. Liquibase có các khả năng cấu hình cột để bỏ qua dữ liệu nguồn trong những phiên bản hỗ trợ, nhưng phải xác nhận chính xác cú pháp/kiểu SKIP và kiểm tra kết quả. Phương án đơn giản nhất khi dữ liệu cố định là chuẩn hóa CSV đầu vào chỉ còn các cột thực sự cần nạp.

Không nên dựa vào suy luận kiểu tự động cho các giá trị quan trọng. Khai báo columns rõ ràng giúp reviewer thấy hợp đồng CSV và giảm sai sót khi người khác xuất lại tệp.

## 8. Trường trống, NULL và chuỗi rỗng

**NULL** ở database khác với chuỗi rỗng, và cả hai khác với ký tự văn bản N-U-L-L. Đây là một nguồn lỗi quan trọng của loadData.

CSV có thể chứa:

~~~csv
code,name,region,active
VN,Viet Nam,APAC,true
ZZ,Unknown,,false
~~~

Ô region trống ở hàng ZZ có thể được diễn giải khác nhau tùy phiên bản Liquibase, kiểu cột và cấu hình. Một số phiên bản có hỗ trợ quy ước placeholder cho giá trị NULL; điều kiện và tên thuộc tính phải được đối chiếu tài liệu đúng phiên bản.

Cách thiết kế an toàn:

1. Xác định rõ trường nào cho phép NULL và trường nào bắt buộc.
2. Quy ước cách biểu diễn NULL trong tệp CSV và tài liệu hóa nó.
3. Không giả định ô trống luôn là chuỗi rỗng hoặc luôn là SQL NULL.
4. Kiểm thử bằng một CSV nhỏ bao gồm các tình huống rỗng, có dấu nháy và giá trị NULL mong muốn.
5. Đối chiếu dữ liệu thực tế bằng truy vấn **IS NULL** và so sánh chuỗi rỗng sau loadData.
6. Đặt constraint NOT NULL ở schema khi giá trị bắt buộc và kiểm tra dữ liệu trước khi áp constraint vào bảng đã có dữ liệu.

Nếu một CSV tham chiếu dữ liệu từ bên ngoài, cần thêm bước kiểm tra dữ liệu đầu vào trước khi nạp để tránh ghi sai ý nghĩa các trường rỗng.

## 9. Phụ thuộc giữa bảng, khóa ngoại và thứ tự nạp

Giả sử hệ thống có bảng country và city; city.country_code tham chiếu country.code. Nếu load city trước khi nạp country, foreign key có thể chặn migration.

~~~mermaid
flowchart TD
    A["Tạo bảng country"] --> B["Nạp countries.csv"]
    C["Tạo bảng city"] --> D["Nạp cities.csv"]
    B --> D
    C --> D
    D --> E["Kiểm tra khóa ngoại và số dòng"]
~~~

Sơ đồ minh họa hai loại phụ thuộc: schema phải có trước khi nạp và **dữ liệu cha phải có trước dữ liệu con** nếu constraint yêu cầu. Trong trường hợp dữ liệu cũ cần backfill trước khi thêm khóa ngoại, thứ tự thiết kế có thể khác; phải chọn theo trạng thái database thật.

Nên dùng include tường minh hoặc quy ước tên ổn định để các changeset tạo bảng, load dữ liệu và thêm constraint có thứ tự dễ review. includeAll chỉ nạp tệp theo quy tắc tài nguyên; nó không tự xây dựng đồ thị phụ thuộc nghiệp vụ.

Với data migration dùng ở production, phải phân biệt:

- **Dữ liệu tham chiếu bắt buộc:** cùng một tập mã dùng cho mọi môi trường tương thích.
- **Dữ liệu seed phục vụ phát triển:** chỉ cần ở dev/test, thường không đưa lên production.
- **Dữ liệu khách hàng thực:** không nên coi là seed cố định trong changelog code, và không nhúng trực tiếp PII vào repository.

Nếu dùng context hoặc label để lọc seed dev, kiểm tra rằng các changeset production không phụ thuộc dữ liệu chỉ có ở dev.

## 10. loadData có lặp lại an toàn không?

Câu trả lời cần tách **lịch sử chạy changeset** khỏi **hành vi SQL nạp dữ liệu**.

Trong chế độ update thông thường, Liquibase không chạy lại một changeset đã được ghi nhận là hoàn thành. Điều đó ngăn việc chèn lại cùng CSV từ chính changeset đã chạy khi ứng dụng khởi động lần nữa. Nhưng **bản thân loadData không phải thao tác tự phát hiện mọi bản ghi đã có**.

Nếu changeset chưa từng chạy trên một database mà bảng đích đã có code=VN, việc nạp CSV có thể gặp vi phạm khóa chính. Nếu bảng không có khóa duy nhất, còn có nguy cơ tạo dữ liệu trùng.

Không nên mặc định dùng **runAlways** hoặc **runOnChange** cho loadData. Những lựa chọn này có thể khiến dữ liệu bị nạp lại hoặc gây khác biệt khó dự đoán, đồng thời yêu cầu hiểu rõ checksum của change type trong phiên bản thực tế.

### 10.1. Dữ liệu seed bất biến: cách khuyến nghị

- Gắn một file CSV với một changeset có ID/author/path ổn định.
- Không sửa những file/changelog đã triển khai lên môi trường dùng chung.
- Khi cần thêm mã mới, tạo CSV và changeset mới chỉ cho các dòng mới.
- Khi cần thay đổi tên hoặc trạng thái bản ghi cũ, tạo changeset update riêng với điều kiện rõ ràng.
- Kiểm thử cả database mới và database nâng cấp; hai đường đi phải cho trạng thái cuối cùng hợp lệ.

Tập dữ liệu có thể phát triển qua nhiều phiên bản, nhưng lịch sử từng bước được giữ rõ, có thể review và điều tra.

## 11. loadUpdateData khác loadData thế nào?

Liquibase có change type **loadUpdateData**, thường dùng khi cần áp dụng dữ liệu CSV theo khóa để cập nhật dòng đã tồn tại và chèn dòng chưa có, theo khả năng của DBMS và phiên bản Liquibase.

Ví dụ mô tả ý định upsert danh mục country bằng code làm khóa:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 003-sync-country-labels
      author: database-team
      changes:
        - loadUpdateData:
            file: ../data/country-labels-v2.csv
            relativeToChangelogFile: true
            tableName: country
            primaryKey: code
            encoding: UTF-8
            columns:
              - column:
                  header: code
                  name: code
                  type: STRING
              - column:
                  header: name
                  name: name
                  type: STRING
              - column:
                  header: region
                  name: region
                  type: STRING
              - column:
                  header: active
                  name: active
                  type: BOOLEAN
~~~

Đây là một changeset **mới**, không phải chỉnh changeset loadData đã phát hành. CSV của phiên bản hai cũng cần được đóng gói và version control riêng.

| Tiêu chí | loadData | loadUpdateData |
|---|---|---|
| Ý định chính | Nạp thêm bản ghi | Đồng bộ thêm/cập nhật theo khóa |
| Khi khóa đã tồn tại | Có thể vi phạm unique/PK nếu nạp lại | Có thể cập nhật dòng tương ứng theo cấu hình |
| Yêu cầu khóa nhận diện | Nên có constraint để bảo vệ chất lượng dữ liệu | Cần khai báo khóa phù hợp, thường qua primaryKey |
| Rủi ro | Dòng trùng, dữ liệu chèn ngoài ý muốn | Ghi đè dữ liệu đã bị điều chỉnh ở môi trường đích |
| Kiểm thử | Số dòng và khóa sau insert | Từng cột có bị update đúng chủ đích và có tương thích DBMS không |

**Upsert không tự động là chiến lược đúng.** Nếu người vận hành production đã sửa thủ công name theo một chính sách hợp lệ, loadUpdateData có thể ghi đè. Cần xác định ai là nguồn dữ liệu chuẩn (source of truth), cột nào được phép cập nhật, và có yêu cầu bảo toàn giá trị tại môi trường không.

## 12. Precondition và kiểm chứng số dòng

Đối với CSV tham chiếu cố định, có thể kiểm tra trạng thái trước khi nạp để tránh lỗi khó hiểu. Ví dụ, ở database mới, yêu cầu bảng country tồn tại và chưa có ba mã sắp nạp:

~~~xml
<changeSet id="004-seed-country" author="database-team">
    <preConditions
        onFail="HALT"
        onError="HALT"
        onFailMessage="MIG-COUNTRY-001: Da ton tai mot ma country du kien seed; kiem tra du lieu va lich su truoc khi nap."
        onErrorMessage="MIG-COUNTRY-002: Khong kiem tra duoc country; kiem tra schema, quyen va ket noi.">
        <tableExists tableName="country"/>
        <sqlCheck expectedResult="0"><![CDATA[
            SELECT COUNT(*)
            FROM country
            WHERE code IN ('VN', 'JP', 'US')
        ]]></sqlCheck>
    </preConditions>

    <loadData
        file="../data/countries.csv"
        relativeToChangelogFile="true"
        tableName="country"
        encoding="UTF-8"/>
</changeSet>
~~~

Điều kiện này phù hợp với **một tập seed đã biết**. Nếu CSV chứa hàng trăm nghìn dòng thay đổi thường xuyên, viết thủ công tất cả khóa vào sqlCheck không phải giải pháp tốt; cần quy trình staging và đối chiếu dữ liệu chuyên biệt.

Sau khi nạp CSV ví dụ, có thể kiểm chứng:

~~~sql
SELECT code, name, region, active
FROM country
WHERE code IN ('VN', 'JP', 'US')
ORDER BY code;
~~~

Và đếm số mã mong đợi:

~~~sql
SELECT COUNT(*) AS loaded_reference_rows
FROM country
WHERE code IN ('VN', 'JP', 'US');
~~~

Đếm đúng ba hàng mới chỉ là một điều kiện cần. Phải kiểm tra thêm tên, region, active, ràng buộc và mọi quy tắc dữ liệu mà ứng dụng phụ thuộc. Có thể tự động hóa bằng test SQL hoặc assertion trong pipeline.

## 13. Rollback dữ liệu CSV: thường nguy hiểm hơn rollback cấu trúc

Với createTable, rollback có thể là dropTable nhưng sẽ xóa dữ liệu. Với loadData, hành vi ngược lại tưởng chừng đơn giản là DELETE những dòng vừa nạp. Vấn đề là sau khi triển khai, các dòng ấy có thể đã được ứng dụng tham chiếu hoặc người dùng chỉnh sửa.

Ví dụ rollback theo mã ổn định:

~~~yaml
rollback:
  - delete:
      tableName: country
      where: "code IN ('VN', 'JP', 'US')"
~~~

Cần xem xét ít nhất bốn nguy cơ:

1. **Dữ liệu phụ thuộc:** city hoặc address có thể đang tham chiếu country.code; DELETE sẽ vi phạm FK hoặc gây mất dữ liệu nếu có quy tắc cascade.
2. **Dữ liệu đã được sửa:** người vận hành có thể đã cập nhật name hoặc region; rollback xóa toàn bộ dòng chứ không khôi phục giá trị trước đó.
3. **Tệp CSV đã đổi:** nếu tập mã thay đổi nhưng rollback không được kiểm tra, có thể xóa thiếu hoặc xóa nhầm.
4. **Khả năng phục hồi dữ liệu:** một thao tác delete thành công không tạo lại được lịch sử của dòng đã bị xóa.

Một phương án thay thế có thể là **forward-fix**: thêm changeset điều chỉnh lại dữ liệu mà không xóa các khóa đang được tham chiếu. Nếu bắt buộc rollback dữ liệu quan trọng, cần backup/restore hoặc snapshot dữ liệu và kiểm thử trong môi trường đại diện.

Đừng khai báo rollback như một chi tiết hình thức; hãy đánh giá nó theo quan hệ khóa ngoại và vòng đời dữ liệu thực tế.

## 14. Transaction, hiệu năng và CSV lớn

Với CSV vài dòng tham chiếu, loadData thường khá đơn giản. Với vài triệu bản ghi, câu chuyện khác nhiều:

- Số lượng INSERT, khả năng dùng prepared statements hoặc batch và cách Liquibase triển khai theo phiên bản ảnh hưởng thời gian.
- Index và constraint trên bảng đích làm tăng chi phí ghi và kiểm tra từng dòng.
- Database transaction dài có thể tăng tải WAL/redo log, thời gian giữ lock và độ trễ replication.
- Dữ liệu sai ở cuối tệp có thể làm changeset thất bại sau khi đã tiêu tốn nhiều tài nguyên.
- Tính nguyên tử khi lỗi phụ thuộc DBMS, loại thao tác, runInTransaction và cấu hình; không được giả định mọi tình huống rollback tự động.

### 14.1. Những lựa chọn cần đánh giá

**Đối với dữ liệu tham chiếu nhỏ:** loadData trong một changeset có version control, constraint phù hợp và kiểm tra sau triển khai là cách rõ ràng.

**Đối với dữ liệu lớn:** cân nhắc chia lô, staging table, cơ chế bulk load native của DBMS, ETL được giám sát hoặc job dữ liệu chuyên biệt. Có thể cần tách schema migration khỏi data migration dài, với checkpoint, thống kê tiến độ, error handling và rollback/forward-fix riêng.

**Đối với dữ liệu nhạy cảm:** hạn chế lưu CSV trong repository; quản lý quyền truy cập, mã hóa và nguồn dữ liệu, không đưa thông tin khách hàng thật vào logs hoặc artifact không phù hợp.

Không nên tăng tốc bằng cách tắt constraint/FK hoặc bỏ kiểm tra dữ liệu mà không có kế hoạch đảm bảo toàn vẹn sau nạp. Một pipeline nhanh nhưng đưa vào dữ liệu sai sẽ tạo chi phí khắc phục lớn hơn nhiều.

## 15. Theo dõi checksum và nội dung CSV đã triển khai

Liquibase nhận diện changeset chủ yếu theo **ID, author và đường dẫn changelog** (hoặc logicalFilePath khi được cấu hình). DATABASECHANGELOG ghi trạng thái thực thi và checksum theo khả năng của change type.

Nhóm cần phân biệt hai loại thay đổi:

1. **Sửa nội dung changelog:** có thể dẫn tới checksum mismatch khi changeset đã triển khai.
2. **Thay đổi tệp CSV được tham chiếu:** tác động đến checksum và việc nạp lại có thể phụ thuộc change type/phiên bản và cấu hình. Không nên suy đoán rằng sửa CSV luôn kích hoạt nạp lại, hoặc luôn được bỏ qua an toàn.

Cách quản lý đáng tin cậy nhất là **không sửa CSV đã phát hành**. Tạo một file và changeset mới cho mỗi thay đổi dữ liệu có ý nghĩa. Trong CI, có thể kiểm tra checksum hoặc hash của CSV ở cấp repository/artifact để phát hiện tệp đã bị chỉnh ngoài dự kiến.

Nếu một CSV cũ bị sửa nhầm, đừng mặc định dùng clear-checksums, runOnChange hoặc xóa DATABASECHANGELOG để bỏ qua lỗi. Hãy xác minh nội dung đã triển khai, dữ liệu thực tế trên môi trường và phương án migration sửa chữa phù hợp.

## 16. Tích hợp Spring Boot, CI/CD và nhiều môi trường

Cấu hình Spring Boot phổ biến khi changelog gốc là YAML:

~~~properties
spring.liquibase.enabled=true
spring.liquibase.change-log=classpath:/db/changelog/db.changelog-master.yaml
~~~

Ứng dụng cần dependency Liquibase, JDBC driver, datasource hoặc cấu hình Liquibase riêng phù hợp. Để loadData hoạt động sau build, phải có cả changelog con lẫn CSV trong artifact được triển khai.

Pipeline CI/CD nên kiểm tra theo thứ tự:

1. **Repository và artifact:** Đúng changelog, CSV được commit có chủ đích, encoding UTF-8, không chứa secrets/PII không được phép.
2. **Schema:** Bảng đích và các cột tồn tại trước changeset loadData, đúng constraint.
3. **Cấu trúc CSV:** Header, số cột, separator, quote, kiểu và biểu diễn NULL đúng quy ước.
4. **Liquibase validate:** Cấu hình và changelog phù hợp runtime đang dùng.
5. **Preview SQL:** Xem trước thay đổi ở mức được hỗ trợ; lưu ý việc sinh SQL có thể làm lộ giá trị seed trong logs.
6. **Fresh install:** Dựng database từ đầu và đối chiếu đầy đủ tập dữ liệu tham chiếu.
7. **Upgrade:** Nâng database có lịch sử phiên bản trước; không chèn trùng hoặc làm mất dữ liệu hiện có.
8. **Kiểm tra sau update:** Đếm dòng, truy vấn mẫu, FK/unique constraints và DATABASECHANGELOG.
9. **Khôi phục:** Kiểm thử rollback/forward-fix trên bản sao có quan hệ dữ liệu đại diện.
10. **Triển khai production:** Chạy migration bằng tiến trình được điều phối, có log, quyền và kế hoạch theo dõi.

Ví dụ CLI khi URL, user, driver và changelog đã được cấu hình:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
liquibase update
~~~

Lệnh update thực thi thay đổi thật, nên xác minh chính xác database đích trước khi chạy. Tên lệnh, tùy chọn và mức kiểm tra khác nhau theo phiên bản Liquibase; một bước validate hay preview thành công không thay thế thử nghiệm nạp dữ liệu trên database đích tương ứng.

Nếu nhiều replica Spring Boot khởi động cùng lúc, cần quyết định rõ tiến trình nào thực hiện migration. DATABASECHANGELOGLOCK giúp điều phối Liquibase nhưng không thay thế kế hoạch giới hạn tải khi nạp CSV lớn.

## 17. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Không tìm thấy CSV | Sai file path/relativeToChangelogFile, thiếu resource trong JAR | Đối chiếu vị trí changelog con, artifact và tên file |
| Header không khớp | CSV bị đổi tên cột, có BOM hoặc khoảng trắng | Kiểm tra encoding/header nguyên bản và mapping |
| Dữ liệu lệch cột | Dấu phẩy trong giá trị không được quote, sai separator | Sửa chuẩn CSV, thử parser trên file mẫu |
| Ký tự tiếng Việt bị lỗi | Tệp nguồn và encoding không thống nhất | Lưu UTF-8, khai báo encoding, kiểm tra giá trị sau nạp |
| Lỗi chuyển kiểu | Giá trị số/ngày/Boolean không phù hợp | Chuẩn hóa CSV và ánh xạ type rõ ràng |
| Vi phạm NOT NULL | Ô trống/NULL không đúng quy tắc | Xác định cách biểu diễn NULL theo runtime và sửa dữ liệu |
| Duplicate key hoặc unique violation | Nạp lại dòng đã có, source trùng khóa | Kiểm tra dữ liệu hiện hữu, khóa chính và ý định INSERT/upsert |
| Vi phạm FOREIGN KEY | Nạp dữ liệu con trước dữ liệu cha | Sửa thứ tự changeset và đối chiếu mã tham chiếu |
| Nạp được ở local nhưng không ở production | Khác schema, user, dữ liệu hoặc phiên bản DBMS | Thử bằng cấu hình và trạng thái production-like |
| CSV cũ bị sửa sau phát hành | Thiếu quy tắc bất biến lịch sử | Khôi phục tệp đã phát hành, tạo changeset mới cho thay đổi |
| Rollback xóa dữ liệu quan trọng | DELETE không xét FK hoặc dữ liệu bị chỉnh sau seed | Kiểm thử rollback và chuẩn bị forward-fix/backup |
| Migration CSV quá chậm | Tệp lớn, index/constraint và transaction nặng | Đo thời gian, cân nhắc staging/bulk load/job riêng |

Quy trình điều tra hiệu quả: **đường dẫn tài nguyên → nội dung và encoding CSV → mapping/kiểu → trạng thái bảng/constraint → lịch sử Liquibase → SQL hoặc dữ liệu đã nạp**. Không giải quyết lỗi bằng cách sửa bảng DATABASECHANGELOG thủ công.

## 18. Bài thực hành có kiểm chứng

Trên PostgreSQL lab, tạo database dùng riêng cho bài học và thực hiện:

1. Tạo cấu trúc master/changes/data như mục 3, sử dụng bảng country với code làm khóa chính.
2. Tạo countries.csv với ba dòng VN, JP và US, lưu UTF-8; viết loadData ánh xạ bốn cột.
3. Chạy validate, status và xem trước SQL, sau đó update trên database lab trống.
4. Truy vấn country và DATABASECHANGELOG để xác minh số dòng, nội dung và trạng thái changeset.
5. Chạy lại update cùng changelog, xác nhận những changeset đã hoàn thành không chèn trùng dữ liệu.
6. Trên một database lab riêng, chèn sẵn code=VN rồi chạy changeset loadData chưa từng được ghi nhận; quan sát lỗi khóa trùng và giải thích sự khác nhau giữa lịch sử changeset với tính idempotent của INSERT.
7. Thử một CSV có dấu phẩy bên trong name được quote; sau đó thử CSV sai separator để học cách chẩn đoán.
8. Thử một mã có số 0 ở đầu và giải thích vì sao nên dùng STRING cho mã định danh.
9. Mô phỏng update bản ghi name bằng **một changeset mới**, cân nhắc dùng loadUpdateData với primaryKey phù hợp.
10. Thử rollback trên bản sao chỉ chứa dữ liệu seed, xác minh những dòng được xóa; sau đó giải thích tại sao không nên dùng rollback đó nếu city đã tham chiếu country.
11. Đóng gói một ứng dụng Spring Boot thử nghiệm, kiểm tra CSV thật sự nằm trong JAR và đường dẫn relativeToChangelogFile vẫn đúng.

Điều kiện hoàn thành: người học có thể giải thích cách loadData đọc và ánh xạ CSV; phân biệt loadData với loadUpdateData; thiết kế một changeset có thứ tự, precondition và rollback hợp lý; nhận diện vấn đề encoding, NULL, duplicate key, path và xác minh được trạng thái cuối cùng bằng SQL.

## 19. Checklist trước khi merge migration loadData

| Câu hỏi | Bằng chứng cần có |
|---|---|
| CSV có phải dữ liệu tham chiếu được phép đưa vào repository? | Đánh giá nguồn dữ liệu, quyền truy cập và bảo mật |
| Header, separator, quote và encoding nhất quán? | Kiểm tra CSV thực tế, có test parser |
| Bảng/cột đích tồn tại và có kiểu phù hợp? | Migration tạo schema chạy trước |
| Mapping header/name/type rõ ràng? | Có khai báo columns hoặc quy ước được kiểm chứng |
| Mã định danh có được giữ nguyên? | STRING/VARCHAR cho mã có leading zero |
| Quy tắc NULL và trường rỗng đã được thử? | Test riêng cho các trường hợp trống/NULL |
| Tập dữ liệu có vi phạm PK/unique/FK không? | Kiểm tra khóa trùng và quan hệ dữ liệu |
| Đường dẫn CSV còn đúng sau đóng gói? | Kiểm tra resources trong JAR/image |
| Changeset và CSV đã phát hành được giữ bất biến? | Có quy ước chỉ thêm migration mới |
| Dùng loadData hay loadUpdateData đúng ý định? | Quyết định INSERT và cập nhật được review |
| Có kiểm tra dữ liệu sau load? | SQL/assertion về số dòng và nội dung |
| Fresh install và upgrade đều đạt? | Kết quả CI/CD trên hai trạng thái database |
| Rollback có làm mất dữ liệu đang được tham chiếu? | Bài thử và phương án forward-fix/backup |
| Có phù hợp kích thước/tải triển khai không? | Đã đo tốc độ hoặc có kế hoạch bulk load riêng |

**Nguyên tắc cốt lõi:** loadData là cách đưa **một tập dữ liệu CSV có kiểm soát** vào lịch sử migration của Liquibase. Để dùng an toàn, hãy xem CSV là một hợp đồng dữ liệu có schema, encoding, khóa và phiên bản rõ ràng; giữ các tệp đã phát hành bất biến; kiểm chứng cả database mới lẫn database đã có dữ liệu; và thiết kế rollback/forward-fix theo ràng buộc nghiệp vụ. Khi đó loadData hỗ trợ triển khai nhất quán qua local, CI, staging và production mà không biến dữ liệu tham chiếu thành một thao tác thủ công khó truy vết.

