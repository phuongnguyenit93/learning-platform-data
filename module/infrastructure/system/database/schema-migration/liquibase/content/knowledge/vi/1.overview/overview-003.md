# Phân biệt migration, đồng bộ lược đồ ORM và chạy SQL thủ công

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, mục tiêu là quản lý thay đổi schema và dữ liệu bằng Liquibase, theo dõi mỗi lần triển khai và giữ các môi trường nhất quán. Nội dung này thuộc chương **Tổng quan** và tập trung vào ba cách thường gặp để thay đổi cơ sở dữ liệu: migration có phiên bản, đồng bộ schema từ ORM và chạy SQL trực tiếp.

Điểm cốt lõi là ba cách này khác nhau ở **nguồn mô tả thay đổi, thời điểm thực thi, lịch sử có thể kiểm tra và mức độ kiểm soát**. SQL có thể xuất hiện trong cả ba cách; việc một thay đổi được viết bằng SQL không tự quyết định nó là migration hay thao tác thủ công. Điều quyết định là thay đổi có được quản lý như một bước triển khai có định danh, có thứ tự và có lịch sử hay không.

## 1. Ba cách thay đổi cơ sở dữ liệu

### Migration là gì?

Migration là một thay đổi cơ sở dữ liệu được mô tả rõ ràng, đặt trong lịch sử phiên bản và thực thi theo thứ tự. Một migration có thể tạo bảng, thêm cột, đổi kiểu dữ liệu, thêm chỉ mục, sửa constraint hoặc chuyển đổi dữ liệu hiện có.

Với Liquibase, các thay đổi được khai báo trong **changelog**. Changelog có thể dùng XML, YAML, JSON hoặc SQL. Mỗi **changeset** là một đơn vị thay đổi có định danh gồm **id**, **author** và đường dẫn changelog. Liquibase đối chiếu các changeset với lịch sử trong cơ sở dữ liệu để biết bước nào đã chạy và bước nào còn chờ.

Một migration được quản lý tốt có các đặc điểm:

- Có mã nguồn trong hệ thống quản lý phiên bản cùng với ứng dụng.
- Có định danh ổn định và thứ tự thực thi xác định.
- Được kiểm tra trước khi áp dụng, ví dụ bằng precondition và việc xem SQL dự kiến.
- Có lịch sử triển khai để biết thay đổi nào đã chạy trên từng môi trường.
- Có kế hoạch rollback hoặc kế hoạch sửa tiến về phía trước nếu không thể đảo ngược an toàn.

Migration không nhất thiết phải dùng cú pháp khai báo của Liquibase. Một changeset có thể chứa câu lệnh SQL thuần hoặc gọi một file SQL. Nếu câu SQL đó được đưa vào changelog, được review và được Liquibase quản lý lịch sử, nó vẫn là một migration.

### Đồng bộ schema từ ORM là gì?

ORM ánh xạ mô hình đối tượng trong ứng dụng sang bảng, cột và quan hệ trong cơ sở dữ liệu. Ví dụ, một entity JPA có thể được ánh xạ thành bảng, còn các trường của entity được ánh xạ thành các cột.

Một số ORM có khả năng tạo hoặc cập nhật schema dựa trên metadata của entity khi ứng dụng khởi động. Với Hibernate, cấu hình thường gặp là:

- **create**: tạo schema từ mapping khi khởi động; có thể xóa các đối tượng schema hiện có trước khi tạo lại.
- **create-drop**: tạo schema khi khởi động và xóa schema do Hibernate quản lý khi ứng dụng dừng.
- **update**: cố gắng điều chỉnh schema hiện có cho phù hợp với mapping.
- **validate**: kiểm tra mapping có tương thích với schema hiện tại hay không, không chủ động cập nhật schema.
- **none**: không yêu cầu Hibernate tạo, cập nhật hoặc kiểm tra schema.

Cách đồng bộ này thuận tiện khi thử nghiệm một entity mới trong môi trường cá nhân. Tuy nhiên, mapping hiện tại không mô tả đầy đủ lịch sử biến đổi dữ liệu. ORM cũng không biết chắc một cột cũ có thể xóa hay không, dữ liệu cũ cần chuyển đổi thế nào, hoặc một thay đổi có tương thích với phiên bản ứng dụng đang chạy song song hay không.

Đặc biệt, **update** không thay thế được một kế hoạch migration có kiểm soát. Kết quả phụ thuộc vào ORM, dialect và trạng thái schema; các thao tác chuyển đổi dữ liệu, đổi tên có chủ đích, backfill, constraint nhiều giai đoạn và triển khai không gián đoạn thường cần được thiết kế riêng.

### Chạy SQL thủ công là gì?

Chạy SQL thủ công là việc một người hoặc một quy trình vận hành kết nối trực tiếp đến cơ sở dữ liệu rồi chạy lệnh như **ALTER TABLE**, **CREATE INDEX**, **UPDATE** hoặc **DELETE**. Cách này có thể cần thiết khi xử lý sự cố, sửa dữ liệu đặc biệt hoặc thực hiện một thao tác DBA.

SQL thủ công có ưu điểm là linh hoạt và cho phép kiểm soát chính xác câu lệnh. Rủi ro xuất hiện khi câu lệnh chỉ được chạy trên một môi trường, không được lưu cùng mã nguồn, không có người review hoặc không được ghi nhận trong lịch sử triển khai. Khi đó, hai môi trường có thể có schema khác nhau dù đang chạy cùng phiên bản ứng dụng.

Cần phân biệt **viết SQL** với **chạy SQL ngoài quy trình migration**. Một câu lệnh SQL nằm trong changeset Liquibase là thay đổi có quản lý. Cùng câu lệnh đó nếu được chạy trực tiếp trên production mà không cập nhật changelog thì có thể tạo ra sai lệch giữa trạng thái thực tế và lịch sử migration.

## 2. So sánh theo cách vận hành

| Tiêu chí | Migration bằng Liquibase | Đồng bộ schema từ ORM | SQL chạy trực tiếp |
|---|---|---|---|
| Nguồn mô tả | Changelog và changeset được lưu trong mã nguồn | Mapping entity và cấu hình ORM | File SQL hoặc câu lệnh do người vận hành cung cấp |
| Thời điểm chạy | Theo lệnh triển khai hoặc lúc ứng dụng khởi động nếu đã cấu hình tích hợp | Thường lúc ứng dụng khởi động | Khi người hoặc job vận hành chủ động chạy |
| Thứ tự thay đổi | Có thứ tự qua changelog và lịch sử changeset | Suy ra từ mapping hiện tại | Phụ thuộc người chạy và runbook |
| Lịch sử | Liquibase ghi nhận trong **DATABASECHANGELOG** | ORM không cung cấp lịch sử migration tương đương | Không có lịch sử tập trung nếu không bổ sung cơ chế ghi nhận |
| Kiểm tra trước khi chạy | Có thể dùng precondition, **validate**, xem SQL dự kiến | Có thể kiểm tra mapping, nhưng không thay thế review migration | Phụ thuộc quy trình review và công cụ vận hành |
| Thay đổi dữ liệu | Có thể mô tả và version hóa trong changeset | Không phải mục tiêu chính của schema synchronization | Làm được, nhưng cần tự quản lý tính lặp lại và lịch sử |
| Phù hợp nhất | Thay đổi có kiểm soát qua nhiều môi trường | Thử nghiệm cục bộ; kiểm tra mapping khi ứng dụng chạy | Sự cố hoặc tác vụ đặc biệt có kiểm soát và được ghi nhận |

Trong một hệ thống cần triển khai lặp lại qua development, test, staging và production, changelog thường là nguồn sự thật cho thay đổi schema. ORM có thể tiếp tục làm nhiệm vụ ánh xạ dữ liệu và kiểm tra tính tương thích. SQL trực tiếp vẫn có thể được dùng trong tình huống vận hành, nhưng cần có quy trình đưa thay đổi đó trở lại lịch sử được quản lý.

## 3. Liquibase biến thay đổi thành lịch sử có thể kiểm tra như thế nào?

Một changelog thường có file master để nạp các file con. Ví dụ, file master có thể include các nhóm thay đổi theo chức năng hoặc theo phiên bản. Cách tổ chức cần bảo đảm thứ tự rõ ràng và dễ review; tránh đổi tên hoặc di chuyển file đã được triển khai nếu việc đó làm thay đổi định danh mà Liquibase dùng để nhận diện changeset.

Ví dụ một changeset tạo bảng:

~~~xml
<changeSet id="001-create-customer" author="team">
    <preConditions onFail="HALT">
        <not>
            <tableExists tableName="customer"/>
        </not>
    </preConditions>

    <createTable tableName="customer">
        <column name="id" type="bigint" autoIncrement="true">
            <constraints primaryKey="true" nullable="false"/>
        </column>
        <column name="email" type="varchar(255)">
            <constraints nullable="false"/>
        </column>
        <column name="created_at" type="timestamp"/>
    </createTable>

    <rollback>
        <dropTable tableName="customer"/>
    </rollback>
</changeSet>
~~~

Changeset tiếp theo có thể thêm một cột:

~~~xml
<changeSet id="002-add-customer-status" author="team">
    <preConditions onFail="HALT">
        <tableExists tableName="customer"/>
        <not>
            <columnExists tableName="customer" columnName="status"/>
        </not>
    </preConditions>

    <addColumn tableName="customer">
        <column name="status" type="varchar(30)"/>
    </addColumn>

    <rollback>
        <dropColumn tableName="customer" columnName="status"/>
    </rollback>
</changeSet>
~~~

Đây là các đoạn minh họa cho cấu trúc changeset; kiểu dữ liệu, auto-increment và cú pháp cụ thể cần được kiểm tra với hệ quản trị cơ sở dữ liệu đích. Rollback xóa bảng hoặc cột có thể làm mất dữ liệu được ghi sau migration, vì vậy không được xem rollback là thao tác an toàn mặc định.

Khi chạy **liquibase update**, Liquibase đọc changelog, kiểm tra các changeset đã được ghi nhận và thực thi những changeset còn thiếu. Hai bảng metadata quan trọng là:

- **DATABASECHANGELOG**: ghi nhận changeset đã chạy, bao gồm định danh, tác giả, file, thời điểm, thứ tự thực thi, kiểu thực thi và checksum.
- **DATABASECHANGELOGLOCK**: quản lý khóa để tránh nhiều tiến trình Liquibase cùng cập nhật schema đồng thời trên một database.

**DATABASECHANGELOG** là lịch sử triển khai trong database; changelog được lưu trong hệ thống quản lý phiên bản vẫn là nơi định nghĩa thay đổi mong muốn. Nếu chỉ còn metadata trong database mà mất changelog tương ứng, việc tái tạo và review lịch sử sẽ khó khăn.

### Checksum và nguyên tắc không sửa migration đã chạy

Liquibase tính checksum cho changeset và lưu giá trị đó trong **DATABASECHANGELOG**. Khi một changeset đã triển khai bị sửa nội dung, checksum tính lại có thể khác với checksum đã lưu. Liquibase sẽ phát hiện thay đổi và thường dừng với lỗi checksum để tránh âm thầm thay đổi ý nghĩa của lịch sử.

Quy tắc làm việc an toàn:

1. Nếu changeset chưa chạy ở bất kỳ môi trường dùng chung nào, có thể chỉnh sửa theo quy trình review.
2. Nếu changeset đã chạy ở một môi trường dùng chung, tạo changeset mới để sửa hoặc bổ sung hành vi.
3. Không xóa rồi tạo lại changeset cũ chỉ để làm cho lệnh update chạy qua.
4. Chỉ dùng **validCheckSum**, **clear-checksums** hoặc **runOnChange** khi hiểu rõ tác động và có lý do cụ thể.

**runOnChange** phù hợp với một số đối tượng cần cập nhật định nghĩa như view hoặc stored procedure. Nó không phải cách mặc định để viết lại migration cấu trúc thông thường. Việc xóa checksum hoặc chấp nhận checksum mới cũng không tự chứng minh schema và dữ liệu đang đúng.

## 4. Precondition giúp kiểm tra giả định trước khi thay đổi

Precondition là điều kiện Liquibase đánh giá trước khi chạy changelog hoặc changeset. Chúng giúp phát hiện database không ở trạng thái mà migration mong đợi. Ví dụ:

- **tableExists**: bảng cần thao tác có tồn tại hay không.
- **columnExists**: cột cần thao tác có tồn tại hay không.
- **indexExists**: chỉ mục có tồn tại hay không.
- **sqlCheck**: chạy truy vấn kiểm tra và so sánh kết quả với giá trị mong đợi.
- **dbms**: giới hạn một thay đổi cho hệ quản trị cơ sở dữ liệu cụ thể.

Có thể kết hợp điều kiện với **and**, **or** và **not**. Ví dụ, trước khi thêm cột, kiểm tra bảng đã tồn tại và cột chưa tồn tại. Khi điều kiện sai hoặc không thể đánh giá, Liquibase có thể xử lý theo **onFail** hoặc **onError** như **HALT**, **CONTINUE**, **MARK_RAN** hay **WARN**, tùy cấu hình và loại kết quả.

Cần phân biệt:

- **onFail**: điều kiện precondition được đánh giá thành công nhưng không thỏa mãn.
- **onError**: có lỗi khi đánh giá precondition, chẳng hạn truy vấn không thực thi được.

**HALT** dừng quá trình để người vận hành xử lý. **CONTINUE** bỏ qua changeset trong lần chạy hiện tại để có thể xét lại ở lần sau. **MARK_RAN** ghi nhận changeset như đã chạy dù nội dung thay đổi không được thực thi. Vì vậy, chỉ dùng **MARK_RAN** khi trạng thái database đã được xác minh độc lập là tương đương với kết quả mà changeset cần tạo ra. **WARN** phát cảnh báo theo hành vi của Liquibase nhưng không nên được hiểu là đã sửa được trạng thái sai.

Precondition không thay thế việc kiểm tra dữ liệu và constraint. Ví dụ, **tableExists** chỉ xác nhận bảng có mặt; nó không chứng minh bảng có đủ cột, đúng kiểu dữ liệu, đúng khóa ngoại hoặc đúng dữ liệu.

## 5. ORM nên phối hợp với Liquibase ra sao?

Khi Liquibase là công cụ sở hữu thay đổi schema, cấu hình ORM nên tránh tự ý cập nhật schema. Với Spring Boot và Hibernate, cấu hình thường dùng là **validate** hoặc **none**:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
  liquibase:
    change-log: classpath:db/changelog/db.changelog-master.xml
    enabled: true
~~~

Ở ví dụ này, Liquibase thực thi changelog khi Spring Boot khởi động; Hibernate kiểm tra mapping với schema hiện tại. Có thể dùng **none** nếu việc kiểm tra schema được thực hiện ở bước khác. Cần xác nhận cấu hình thực tế theo phiên bản Spring Boot, Hibernate, database và cách triển khai của dự án.

Không nên để Hibernate **update** và Liquibase cùng thay đổi một schema. Hai cơ chế có thể đưa database đến trạng thái khó giải thích: một phần thay đổi đến từ changelog, phần còn lại đến từ mapping. Khi lỗi xảy ra, lịch sử Liquibase không phản ánh đầy đủ trạng thái thực tế.

Nếu hệ thống có nhiều replica ứng dụng, việc để mọi replica cùng chạy migration khi khởi động có thể làm tăng thời gian chờ và khiến triển khai khó dự đoán. **DATABASECHANGELOGLOCK** giúp tuần tự hóa cập nhật, nhưng pipeline có một bước migration riêng thường dễ quan sát và kiểm soát hơn. Khi pipeline chịu trách nhiệm migration, cấu hình tiến trình ứng dụng cần tránh chạy lại migration ngoài chủ đích, ví dụ tắt **spring.liquibase.enabled** ở profile ứng dụng phù hợp trong khi job migration vẫn được cấu hình để chạy Liquibase.

## 6. Khi nào cần SQL trực tiếp và làm sao tránh lệch môi trường?

Có những thao tác SQL khó biểu đạt bằng change type có sẵn, cần tính năng riêng của database hoặc cần xử lý sự cố. Liquibase cho phép đưa SQL vào changeset:

~~~xml
<changeSet id="003-backfill-customer-status" author="team">
    <preConditions onFail="HALT">
        <tableExists tableName="customer"/>
        <columnExists tableName="customer" columnName="status"/>
    </preConditions>

    <sql>
        UPDATE customer
        SET status = 'PENDING'
        WHERE status IS NULL;
    </sql>
</changeSet>
~~~

Đây vẫn là migration vì câu SQL được định danh, review và ghi nhận trong lịch sử Liquibase. Với câu lệnh phức tạp, có thể dùng **sqlFile** để lưu SQL trong file riêng rồi tham chiếu từ changelog. File đó cũng phải được quản lý cùng mã nguồn và đường dẫn cần ổn định.

Nếu buộc phải chạy SQL trực tiếp trên production để xử lý sự cố, nên ghi lại tối thiểu:

- Database, schema, bảng và phạm vi bản ghi bị tác động.
- Lý do, người thực hiện, thời điểm và ticket hoặc biên bản phê duyệt liên quan.
- Câu lệnh thực tế, số dòng bị ảnh hưởng và kết quả xác minh.
- Cách khôi phục hoặc phương án sửa tiến về phía trước.

Sau thao tác khẩn cấp, cần đối chiếu schema và dữ liệu thực tế với changelog. Nếu thay đổi phải tồn tại lâu dài, hãy tạo changeset phản ánh trạng thái mong muốn và xử lý việc đồng bộ lịch sử theo quy trình được kiểm soát. Không chạy một changeset giả chỉ để đánh dấu đã hoàn thành nếu chưa chứng minh database thật sự ở trạng thái tương ứng.

Với migration dữ liệu lớn, cần xem xét thời gian khóa bảng, dung lượng transaction, tải database và khả năng chạy lại. Một câu **UPDATE** lớn trong changeset có thể tạo transaction dài hoặc ảnh hưởng ứng dụng. Khi cần, chia backfill thành batch hoặc job vận hành có giám sát; ghi nhận rõ cách job tiếp tục sau lỗi và cách kiểm tra số bản ghi còn thiếu.

## 7. Quy trình triển khai qua nhiều môi trường

Để development, test, staging và production đi đến cùng một trạng thái, hãy triển khai cùng một changelog đã review. Các môi trường khác nhau về URL, tài khoản, quyền và dữ liệu; không nên sửa nội dung migration thủ công theo từng môi trường.

Một quy trình thực tế:

1. **Xác định thay đổi và phạm vi tương thích.** Làm rõ bảng/cột/constraint cần thay đổi, dữ liệu hiện tại, phiên bản ứng dụng cũ còn chạy hay không và khả năng khóa bảng.
2. **Tạo changeset mới.** Dùng **id** và **author** ổn định, thêm precondition khi có giả định quan trọng, mô tả rollback nếu có thể đảo ngược an toàn.
3. **Kiểm tra changelog.** Chạy **liquibase validate** để kiểm tra cấu trúc changelog và tham chiếu; dùng **liquibase update-sql** để xem SQL Liquibase dự kiến chạy. Hai bước này không thay thế việc chạy thử trên database tương thích.
4. **Thử trên database dùng một lần hoặc môi trường test.** Chạy migration, kiểm tra schema, dữ liệu, index và constraint; khởi động ứng dụng để kiểm tra mapping và hành vi nghiệp vụ.
5. **Promote cùng artifact qua các môi trường.** Không sửa changeset sau khi đã triển khai lên môi trường đầu tiên. Theo dõi **DATABASECHANGELOG** để xác nhận changeset đã chạy ở đâu.
6. **Triển khai ứng dụng và quan sát.** Kiểm tra log migration, lỗi truy vấn, thời gian chạy, lock, hiệu năng và các luồng nghiệp vụ bị ảnh hưởng.
7. **Ghi nhận mốc phát hành.** Có thể dùng tag hoặc thông tin release để liên hệ trạng thái database với phiên bản ứng dụng và kế hoạch rollback.

Cấu hình kết nối và thông tin xác thực nên được cấp qua biến môi trường hoặc secret store. Không ghi mật khẩu database vào changelog hoặc commit vào repository. Nếu dùng Liquibase trong CI/CD, tài khoản migration cần quyền cần thiết cho thay đổi dự kiến; tài khoản runtime của ứng dụng có thể được cấp quyền hẹp hơn.

### Thay đổi tương thích khi ứng dụng triển khai cuốn chiếu

Giả sử cần thay cột **full_name** bằng **display_name**. Xóa cột cũ ngay trong cùng thời điểm triển khai ứng dụng mới có thể làm phiên bản ứng dụng cũ đang chạy lỗi. Một cách an toàn hơn là triển khai theo các giai đoạn:

1. **Expand:** thêm **display_name** theo cách tương thích, thường cho phép null hoặc có giá trị mặc định phù hợp. Ứng dụng cũ vẫn hoạt động.
2. **Migrate:** triển khai ứng dụng có thể đọc dữ liệu cũ và mới; ghi dữ liệu mới theo chiến lược đã chọn. Backfill dữ liệu cũ theo batch nếu bảng lớn.
3. **Verify:** kiểm tra số bản ghi chưa có **display_name**, kiểm tra dữ liệu khớp và xác nhận không còn phiên bản ứng dụng nào phụ thuộc vào cột cũ.
4. **Contract:** ở một lần phát hành sau, thêm constraint cần thiết rồi mới xóa **full_name** khi đã chắc chắn không còn consumer sử dụng.

Cách này làm tăng số bước triển khai nhưng giảm nguy cơ một thay đổi schema phá vỡ phiên bản ứng dụng đang chạy. Không phải thay đổi nào cũng cần đủ bốn giai đoạn; hãy chọn mức độ phù hợp với quy mô dữ liệu và chiến lược triển khai.

## 8. Rollback và lựa chọn sửa tiến về phía trước

Rollback đưa database về trạng thái trước một hoặc nhiều changeset, nhưng khả năng rollback phụ thuộc loại thay đổi. Liquibase có thể tạo rollback tự động cho một số change type; với SQL tùy chỉnh hoặc chuyển đổi dữ liệu, cần định nghĩa rollback rõ ràng nếu có thể.

Ví dụ, thêm một cột nullable thường có thể rollback bằng cách xóa cột. Nhưng nếu ứng dụng đã ghi dữ liệu vào cột đó, xóa cột sẽ làm mất dữ liệu. Tương tự, rollback một lệnh backfill bằng cách đặt lại tất cả giá trị về null có thể phá hủy giá trị hợp lệ đã được người dùng cập nhật sau migration.

Trước khi rollback, cần trả lời:

- Changeset đã chạy ở môi trường nào và có thay đổi phát sinh sau đó không?
- Rollback có làm mất dữ liệu hoặc phá vỡ phiên bản ứng dụng đang chạy không?
- Các changeset phía sau có phụ thuộc vào thay đổi này không?
- Đã thử rollback trên bản sao dữ liệu tương đương chưa?
- Có backup, point-in-time recovery hoặc phương án sửa tiến về phía trước không?

Các lệnh Liquibase như **rollback-count**, **rollback**, và chế độ xuất SQL rollback có thể hỗ trợ quy trình, nhưng cú pháp tùy phiên bản CLI và cấu hình dự án. Hãy kiểm tra SQL rollback trước khi thực thi trên môi trường dùng chung. Khi không thể đảo ngược dữ liệu an toàn, một changeset sửa tiến về phía trước thường phù hợp hơn việc cố khôi phục trạng thái cũ.

## 9. Ví dụ tổng hợp: thêm trạng thái cho khách hàng

Giả sử bảng **customer** đang có dữ liệu và ứng dụng cần thêm cột **status**.

- Nếu dùng ORM **update**, Hibernate có thể cố thêm cột theo entity mới, nhưng không tạo ra một lịch sử migration rõ ràng và không giải quyết đầy đủ việc gán trạng thái cho bản ghi cũ.
- Nếu chạy SQL trực tiếp, người vận hành có thể thêm cột và backfill nhanh, nhưng các môi trường khác sẽ không tự biết cần thực hiện hai bước đó nếu câu lệnh không được quản lý.
- Nếu dùng Liquibase, thay đổi được chia thành changeset có thứ tự: thêm cột nullable; backfill dữ liệu; sau khi xác minh mới áp dụng constraint hoặc default cần thiết.

Một kế hoạch mẫu:

| Giai đoạn | Thay đổi | Kiểm tra |
|---|---|---|
| 1. Expand | Changeset thêm **customer.status** cho phép null | Cột tồn tại, ứng dụng cũ vẫn truy vấn được |
| 2. Migrate | Changeset hoặc job backfill trạng thái cho bản ghi cũ | Không còn bản ghi thuộc phạm vi cần xử lý bị null |
| 3. Application | Ứng dụng đọc và ghi **status** | Luồng tạo và cập nhật khách hàng hoạt động |
| 4. Contract | Changeset thêm **NOT NULL** hoặc constraint phù hợp | Dữ liệu thỏa constraint, không còn consumer cũ |

Precondition ở bước backfill có thể kiểm tra bảng và cột tồn tại. Trước khi thêm **NOT NULL**, cần kiểm tra dữ liệu thật bằng truy vấn phù hợp, ví dụ:

~~~sql
SELECT COUNT(*)
FROM customer
WHERE status IS NULL;
~~~

Chỉ tiến hành bước cuối khi kết quả và các giả định nghiệp vụ đã được xác minh. Với bảng lớn, hãy đánh giá chi phí quét bảng và triển khai backfill theo lô thay vì mặc định chạy một transaction khổng lồ.

## 10. Những lỗi vận hành thường gặp

- **Sửa changeset đã triển khai:** checksum không còn khớp hoặc lịch sử giữa các môi trường mất nhất quán. Tạo changeset mới để diễn tả thay đổi tiếp theo.
- **Dùng ORM update cùng Liquibase:** schema bị thay đổi ngoài changelog. Chọn một nguồn quản lý schema và cấu hình ORM ở chế độ phù hợp.
- **Dùng MARK_RAN để bỏ qua lỗi:** database có thể chưa đạt trạng thái mong muốn nhưng lịch sử lại ghi changeset đã chạy. Chỉ dùng sau khi xác minh trạng thái tương đương.
- **Chạy SQL trực tiếp mà không ghi nhận:** các môi trường có schema khác nhau và lần triển khai tiếp theo có thể thất bại. Đưa thay đổi lâu dài vào changelog hoặc quy trình reconcile có kiểm soát.
- **Rollback không xét dữ liệu phát sinh:** thao tác đảo ngược có thể xóa dữ liệu mới. Đánh giá tác động và thử trên dữ liệu đại diện.
- **Để nhiều replica cùng sở hữu migration:** quá trình khởi động và triển khai khó quan sát. Ưu tiên một bước migration có kiểm soát trong pipeline hoặc cấu hình một tiến trình chịu trách nhiệm rõ ràng.
- **Dùng precondition quá yếu:** điều kiện chỉ kiểm tra bảng tồn tại nhưng không xác nhận cấu trúc hoặc dữ liệu. Bổ sung điều kiện phù hợp và kiểm tra kết quả sau migration.

## 11. Nguyên tắc lựa chọn

Dùng **Liquibase migration** cho thay đổi schema và dữ liệu cần được triển khai lặp lại, review và truy vết qua nhiều môi trường. Dùng **ORM schema synchronization** chủ yếu cho thử nghiệm cục bộ hoặc kiểm tra mapping; khi Liquibase sở hữu schema, đặt Hibernate ở **validate** hoặc **none**. Dùng **SQL trực tiếp** cho tác vụ vận hành đặc biệt khi cần, đồng thời lưu lại bằng chứng và đồng bộ trạng thái lâu dài với changelog.

Trong quy trình của **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, changelog là lịch sử thay đổi có thể review; changeset mô tả từng bước; precondition xác nhận giả định trước khi chạy; checksum giúp phát hiện chỉnh sửa ngoài dự kiến; **DATABASECHANGELOG** cho biết các bước đã triển khai; còn rollback và quy trình sửa tiến về phía trước giúp xử lý khi kết quả không như mong muốn. Kết hợp các yếu tố này với kiểm tra ORM và quy trình CI/CD sẽ giúp schema và dữ liệu được quản lý nhất quán khi ứng dụng phát triển qua nhiều phiên bản.
