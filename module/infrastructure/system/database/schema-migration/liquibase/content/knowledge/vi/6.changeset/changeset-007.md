# Phối hợp runAlways, runOnChange và checksum trong Liquibase

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, mục tiêu là quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài thuộc chương **Changeset** này giải thích cách Liquibase quyết định có chạy lại một changeset hay không, vai trò của **runAlways**, **runOnChange** và **checksum**, cùng những tình huống cần phối hợp cả hai thuộc tính.

Đây là một quyết định vận hành quan trọng: migration cấu trúc thông thường cần chạy **một lần**, trong khi định nghĩa view hoặc stored procedure đôi khi cần chạy **khi nội dung đổi**, còn một tác vụ có chủ đích như ghi mốc lần cập nhật có thể cần chạy **mỗi lần lệnh cập nhật được thực hiện**. Cấu hình sai có thể làm chạy lại lệnh phá hủy dữ liệu, bỏ qua cập nhật cần thiết hoặc gây lỗi checksum khi triển khai.

## 1. Cơ chế mặc định: Liquibase nhận diện và kiểm tra changeset

Một **changeset** là đơn vị thay đổi nằm trong **changelog**, có ba thành phần định danh chính:

- **id**: mã changeset, cần ổn định trong phạm vi file.
- **author**: định danh tác giả hoặc nhóm, cũng cần ổn định.
- **đường dẫn changelog**: thường là đường dẫn file nơi khai báo changeset; có thể ảnh hưởng bởi cấu hình logical file path.

Khi chạy lệnh **update**, Liquibase nạp changelog, lấy khóa cập nhật từ bảng **DATABASECHANGELOGLOCK**, rồi đối chiếu các changeset được chọn với bảng **DATABASECHANGELOG** trong database đích. Bảng lịch sử này chứa định danh và checksum, cùng metadata về lần thực thi như thời điểm, thứ tự và kiểu thực thi. Định danh giúp Liquibase biết một changeset đã được ghi nhận hay chưa; checksum giúp phát hiện nội dung của một changeset đã ghi nhận có thay đổi không.

Với một changeset bình thường, không đặt hai thuộc tính đặc biệt:

1. Nếu chưa có trong DATABASECHANGELOG, Liquibase sẽ xem xét các điều kiện liên quan và thực thi changeset.
2. Nếu đã được ghi nhận và nội dung tương ứng với checksum hợp lệ, Liquibase thường bỏ qua.
3. Nếu đã được ghi nhận nhưng nội dung bị thay đổi làm checksum không còn hợp lệ, Liquibase thường báo lỗi xác thực, thay vì tự chạy lại lệnh DDL.

Cơ chế này bảo vệ lịch sử migration: một changeset đã triển khai cần giữ nguyên ý nghĩa. Nếu cần sửa cấu trúc bảng, thêm constraint hoặc chuyển đổi dữ liệu, hãy tạo changeset mới thay vì sửa changeset đã chạy trên môi trường dùng chung.

## 2. Checksum kiểm tra điều gì?

**Checksum** là giá trị kiểm tra được Liquibase tính từ định nghĩa changeset theo thuật toán và quy tắc chuẩn hóa của phiên bản Liquibase đang sử dụng. Khi một changeset chạy và được ghi nhận, Liquibase lưu checksum vào cột **MD5SUM** của DATABASECHANGELOG. Định dạng checksum trong bảng có thể có tiền tố phiên bản thuật toán.

Checksum giúp trả lời: *Định nghĩa changeset hiện được đọc có tương ứng với định nghĩa mà Liquibase đã ghi nhận hay không?* Đây là cơ chế kiểm soát thay đổi, không phải chữ ký mật mã hay bằng chứng rằng migration đã cho ra trạng thái dữ liệu đúng. Hai môi trường cùng checksum cũng chưa chắc có dữ liệu nghiệp vụ giống nhau.

Những thay đổi có thể làm checksum khác gồm nội dung SQL, thuộc tính change type và một số tham số định nghĩa thay đổi. Liquibase có quy tắc chuẩn hóa riêng; không phải mọi thay đổi khoảng trắng hoặc comment đều gây checksum khác, và hành vi chính xác có thể tùy loại changelog, change type hoặc phiên bản. Vì vậy, không nên dựa vào việc thêm khoảng trắng hay comment để ép **runOnChange** thực thi.

Ví dụ một changeset tạo cột đã chạy trên staging. Nếu sửa tên cột hoặc kiểu dữ liệu ngay trong changeset cũ, checksum có thể lệch. Trên production, changeset đó có thể chưa chạy, nên production sẽ đọc **định nghĩa mới**; trong khi staging đã có **kết quả cũ**. Đây chính là sai lệch lịch sử mà quy tắc không sửa migration đã triển khai giúp tránh.

Các trường như **EXECTYPE**, **DATEEXECUTED**, **ORDEREXECUTED** và **MD5SUM** trong DATABASECHANGELOG có thể giúp chẩn đoán. Tuy vậy, một changeset chạy lại không nhất thiết tạo thêm một dòng lịch sử mới: Liquibase thường cập nhật metadata của dòng changeset đã tồn tại. Vì vậy cần giữ thêm log của pipeline hoặc của quá trình triển khai khi cần nhật ký đầy đủ từng lần chạy.

## 3. runOnChange: chạy lại khi định nghĩa thay đổi

Đặt **runOnChange: true** cho phép Liquibase chạy lại một changeset đã được ghi nhận khi checksum nội dung thay đổi theo quy tắc của Liquibase. Nếu chưa từng chạy, changeset chạy lần đầu. Nếu đã chạy và checksum không đổi, changeset thường được bỏ qua.

**Trường hợp phù hợp** là đối tượng có thể định nghĩa lại an toàn, chẳng hạn view, function hoặc stored procedure. Ví dụ với PostgreSQL, giả sử bảng **customer(id, email, status)** đã được tạo bởi các changeset trước:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: customer-public-view
      author: database-team
      dbms: postgresql
      runOnChange: true
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: customer
      changes:
        - sql:
            sql: |
              CREATE OR REPLACE VIEW customer_public AS
              SELECT id, email
              FROM customer;
~~~

Khi deploy lần đầu, Liquibase tạo view. Nếu sau này cần bổ sung một cột tương thích vào định nghĩa view, bạn có thể thay nội dung SQL của changeset này theo chính sách quản lý đối tượng có thể cập nhật. Khi checksum thay đổi, Liquibase chạy lại câu **CREATE OR REPLACE VIEW**. Nếu không có thay đổi, một lệnh update sau đó sẽ không cố tạo lại view.

Ở PostgreSQL, **CREATE OR REPLACE VIEW** có giới hạn về việc thay đổi tên, thứ tự và kiểu các cột hiện có. Không được mặc định rằng mọi chỉnh sửa view đều có thể thay thế an toàn; có trường hợp cần một migration mới để đổi cấu trúc phụ thuộc.

**Không nên dùng runOnChange cho** changeset thêm cột, xóa bảng, cập nhật dữ liệu một chiều, backfill lớn hoặc thao tác mà mỗi lần chạy có thể tạo tác dụng phụ ngoài mong muốn. Ví dụ, một changeset dùng SQL **UPDATE balance = balance + 100** sẽ cộng tiền thêm lần nữa nếu chạy lại: không thể coi nó là hành vi an toàn chỉ vì có runOnChange.

Một lưu ý khác: nếu thay đổi view đã được thực hiện trực tiếp bên ngoài Liquibase nhưng nội dung changeset không thay đổi, runOnChange không tự phát hiện schema drift đó. Nó so sánh định nghĩa changeset với lịch sử checksum, không kiểm tra mọi đối tượng database có khớp nội dung mong muốn.

## 4. runAlways: chạy trong mỗi lần update phù hợp

Đặt **runAlways: true** yêu cầu Liquibase chạy lại changeset trong mỗi lần **update** mà changeset được chọn và đủ điều kiện thực thi, kể cả khi nội dung không thay đổi. Nó phù hợp với tác vụ cần chạy lặp lại có chủ đích, thường là tác vụ nhỏ và có tính lặp an toàn.

Ví dụ, tạo bảng metadata một lần để lưu thời điểm job migration cập nhật:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: create-migration-marker
      author: database-team
      changes:
        - createTable:
            tableName: migration_marker
            columns:
              - column:
                  name: marker_key
                  type: varchar(80)
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: last_seen_at
                  type: timestamp
                  constraints:
                    nullable: false
~~~

Sau đó thêm một changeset **runAlways** với SQL PostgreSQL:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: refresh-migration-marker
      author: database-team
      dbms: postgresql
      runAlways: true
      changes:
        - sql:
            sql: |
              INSERT INTO migration_marker (marker_key, last_seen_at)
              VALUES ('schema-update', CURRENT_TIMESTAMP)
              ON CONFLICT (marker_key)
              DO UPDATE SET last_seen_at = EXCLUDED.last_seen_at;
~~~

Chạy lần đầu sẽ thêm bản ghi **schema-update**. Những lần update sau chỉ cập nhật timestamp của cùng bản ghi; khóa chính và câu **ON CONFLICT** giúp tránh tạo vô hạn bản ghi. Tác dụng cập nhật timestamp là chủ đích nên có thể chạy nhiều lần. SQL này dành cho PostgreSQL; DBMS khác sẽ cần cú pháp UPSERT tương ứng.

**runAlways không phải lịch chạy định kỳ.** Liquibase không tự thức dậy để chạy changeset; nó chỉ chạy khi ứng dụng hoặc pipeline gọi lệnh update theo cấu hình. Chạy hai lần update liên tiếp có thể thực thi changeset runAlways hai lần, dù không có migration mới. Nếu cần tác vụ theo giờ hoặc theo ngày, hãy dùng scheduler/job chuyên trách và xem xét liệu logic đó có thuộc migration hay không.

**runAlways cũng không bỏ qua bộ lọc thực thi.** Context, label, DBMS, trạng thái precondition và phạm vi changelog vẫn có thể làm changeset không được chọn hoặc không thể chạy. Nếu tác vụ báo cáo chỉ áp dụng cho staging, không nên cho rằng mỗi lần update trên production cũng sẽ thực thi nó.

## 5. Bốn tổ hợp và quyết định chạy lại

Hai thuộc tính **runAlways** và **runOnChange** là hai cờ độc lập về ý định chạy lại. Bảng sau áp dụng cho changeset đã từng được thực thi thành công, được chọn bởi các bộ lọc và không bị chặn bởi precondition:

| runAlways | runOnChange | Không sửa định nghĩa | Có sửa định nghĩa ảnh hưởng checksum | Trường hợp thường dùng |
|---|---|---|---|---|
| false | false | Bỏ qua | Lỗi checksum trong trường hợp thông thường | Migration DDL/DML một lần |
| false | true | Bỏ qua | Chạy lại | View, function, procedure có thể cập nhật |
| true | false | Chạy lại | Có thể gặp lỗi checksum do sửa changeset đã chạy | Tác vụ luôn chạy nhưng định nghĩa ổn định |
| true | true | Chạy lại | Chạy lại theo nội dung đã thay đổi | Tác vụ luôn chạy và được phép chỉnh định nghĩa có kiểm soát |

**Điểm dễ nhầm:** chỉ đặt **runAlways: true** không đồng nghĩa có quyền sửa tùy ý nội dung changeset cũ. Liquibase vẫn thực hiện cơ chế kiểm tra checksum và việc sửa một changeset runAlways đã chạy có thể gây lỗi xác thực. Theo cơ chế được Liquibase hỗ trợ, có thể kết hợp **runAlways: true** với **runOnChange: true** để vừa chạy mỗi lần update vừa chấp nhận việc thay đổi định nghĩa changeset.

Ví dụ với tác vụ cập nhật marker ở trên, hai cờ có thể cùng xuất hiện:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: refresh-migration-marker
      author: database-team
      dbms: postgresql
      runAlways: true
      runOnChange: true
      changes:
        - sql:
            sql: |
              INSERT INTO migration_marker (marker_key, last_seen_at)
              VALUES ('schema-update', CURRENT_TIMESTAMP)
              ON CONFLICT (marker_key)
              DO UPDATE SET last_seen_at = EXCLUDED.last_seen_at;
~~~

Với tổ hợp này, **runAlways** quyết định chạy trong mỗi lần update phù hợp; **runOnChange** cho phép cùng changeset tiếp tục được chạy khi định nghĩa bị điều chỉnh. Chỉ sử dụng tổ hợp này nếu từng phiên bản SQL đều có tác dụng lặp lại an toàn và sự thay đổi định nghĩa đã được review. Nếu thay đổi đòi hỏi chuyển trạng thái dữ liệu hoặc schema một lần, vẫn nên tạo changeset mới.

Không nên copy hai cờ vào mọi changeset để tránh lỗi checksum. Làm vậy làm mất ý nghĩa lịch sử một lần, dễ thực hiện lại thao tác phá hủy và khiến tác động triển khai khó dự đoán.

## 6. Dòng thời gian thực thi trên nhiều lần triển khai

Giả sử changelog có bốn changeset:

- **A**: tạo bảng customer, không đặt hai cờ.
- **B**: tạo view customer_public, đặt runOnChange.
- **C**: cập nhật migration_marker, đặt runAlways.
- **D**: chạy một SQL lặp an toàn, đặt cả runAlways và runOnChange.

Khi chạy lệnh update trên database mới, cả bốn changeset được thực thi lần đầu và được ghi nhận. Trên lần update thứ hai, nếu không đổi nội dung, **A** và **B** được bỏ qua; **C** và **D** chạy lại. Nếu sau đó nội dung view trong **B** được thay đổi theo cách hợp lệ, lần update tiếp theo sẽ chạy **B**, **C** và **D**, còn **A** không chạy lại.

Nếu tiếp tục chỉnh SQL của **D**, nó vẫn chạy trong lần update kế tiếp theo nội dung mới. Ngược lại, nếu chỉnh SQL của **C** mà vẫn giữ **runAlways: true** và **runOnChange: false**, quá trình xác thực có thể dừng vì checksum không khớp. Cách xử lý thích hợp phụ thuộc ý nghĩa thay đổi: bổ sung runOnChange nếu tác vụ cần tiếp tục được định nghĩa lại an toàn, hoặc tạo changeset mới nếu đó là một thay đổi độc lập cần lịch sử riêng.

Bảng dưới mô tả các hành vi dự kiến, giả sử không có context/label/precondition chặn thực thi:

| Lần update | A: DDL một lần | B: runOnChange | C: runAlways | D: cả hai |
|---|---|---|---|---|
| 1. Database rỗng | Chạy | Chạy | Chạy | Chạy |
| 2. Không đổi nội dung | Bỏ qua | Bỏ qua | Chạy | Chạy |
| 3. Chỉ sửa SQL của B | Bỏ qua | Chạy | Chạy | Chạy |
| 4. Chỉ sửa SQL của D | Bỏ qua | Bỏ qua | Chạy | Chạy |

Khi một changeset chạy lại, Liquibase ghi nhận trạng thái thực thi lại trong DATABASECHANGELOG, thường với **EXECTYPE=RERAN**, và cập nhật metadata tương ứng. Bảng này không cung cấp một nhật ký đầy đủ mọi lần gọi lệnh update; muốn truy vết từng lần deploy cần lưu log, mã phiên bản ứng dụng, thời điểm và thông tin job CI/CD.

## 7. Tương tác với precondition, context, label và transaction

Một changeset không chỉ phụ thuộc vào hai cờ và checksum. Trước khi kết luận nó sẽ chạy, hãy xét thêm các yếu tố liên quan:

**Precondition:** có thể kiểm tra bảng, cột, DBMS, dữ liệu hoặc kết quả câu truy vấn trước khi thực hiện change. Nếu điều kiện thất bại, hành vi phụ thuộc **onFail**; nếu đánh giá điều kiện bị lỗi, hành vi phụ thuộc **onError**. **HALT** dừng triển khai, còn **MARK_RAN** có thể đánh dấu changeset đã được xử lý dù không thực thi nội dung. Với changeset lặp lại, việc đánh dấu đã chạy có thể che giấu sự không tương thích; cần chọn xử lý failure dựa trên trạng thái thực tế.

**Context và label:** giới hạn changeset nào được xét trong một lệnh update. Ví dụ, một marker chỉ dành cho staging có thể dùng context tương ứng; lần update ở production không tự nhiên thực thi nó. Nếu bộ lọc thay đổi giữa các lần triển khai, số lần chạy có thể khác nhau giữa các môi trường. Đừng đồng nhất **runAlways** với chạy trên mọi database.

**DBMS:** SQL dùng **ON CONFLICT** của PostgreSQL không chạy được nguyên vẹn trên mọi DBMS. Khi dùng SQL riêng của DBMS, đặt **dbms: postgresql** hoặc tổ chức changeset theo DBMS rõ ràng. Các nhánh riêng cần được thử trên từng DBMS thực tế.

**Transaction:** Liquibase thường chạy changeset trong transaction khi DBMS và change type hỗ trợ, nhưng một số lệnh DDL hoặc thao tác đặc biệt có thể tự commit hay yêu cầu chạy ngoài transaction. Nếu một changeset runAlways hoặc runOnChange chạy lại và thất bại giữa chừng, tác động thực tế phụ thuộc cơ chế transaction của DBMS. Không giả định rollback database tự động khôi phục mọi side effect, đặc biệt với lệnh SQL ngoài database hoặc thao tác không hỗ trợ transaction.

**Khóa triển khai:** DATABASECHANGELOGLOCK giúp ngăn hai tiến trình Liquibase thực hiện update đồng thời trên cùng metadata database. Khóa này không làm một câu SQL không có tính lặp an toàn trở thành an toàn; cần thiết kế idempotent ở logic changeset.

## 8. Sửa changeset đã chạy: phương án nào an toàn?

Khi checksum thay đổi, đừng lập tức xóa checksum hoặc dùng runOnChange để bỏ qua lỗi. Hãy xác định changeset thuộc loại nào và tại sao nội dung khác:

| Tình huống | Hướng xử lý |
|---|---|
| Migration một lần đã chạy, cần thêm cột mới | Tạo changeset mới |
| Migration một lần đã chạy, SQL có lỗi cần sửa dữ liệu | Tạo changeset điều chỉnh hoặc kế hoạch phục hồi có kiểm chứng |
| View/procedure được thiết kế runOnChange, muốn sửa định nghĩa | Review khả năng thay thế và để Liquibase chạy lại |
| Changeset runAlways có thay đổi logic lặp an toàn | Cân nhắc runOnChange cùng runAlways; thử nghiệm trước |
| Checksum lệch do file bị đổi tên/di chuyển | Xác minh định danh file, logical path và lịch sử; phục hồi đường dẫn ổn định nếu phù hợp |
| Checksum lệch nhưng không biết nguyên nhân | Dừng, so sánh mã nguồn và lịch sử triển khai trước khi quyết định |

Liquibase có các cơ chế bổ trợ:

- **validCheckSum:** chấp nhận một hoặc một số checksum đã xác định như hợp lệ cho changeset. Nó không có nghĩa Liquibase tự thực thi lại toàn bộ changeset. Phù hợp với trường hợp đặc biệt đã hiểu nguyên nhân và đã review trạng thái database.
- **clear-checksums:** xóa checksum đã lưu để Liquibase tính lại trong các lần cập nhật sau. Đây không phải lệnh rollback hay công cụ sửa schema; dùng bừa bãi sẽ làm yếu khả năng phát hiện chỉnh sửa ngoài dự kiến.
- **runOnChange:** chỉ thích hợp nếu việc chạy lại nội dung là chủ đích và có tính an toàn lặp lại.
- **runAlways:** chỉ thích hợp nếu mỗi lần update đều nên thực hiện tác vụ, kể cả khi không có thay đổi trong mã nguồn.

Không trực tiếp sửa **DATABASECHANGELOG.MD5SUM** để làm mất lỗi. Làm như vậy tạo ra lịch sử khó kiểm chứng và che khuất nguyên nhân sai lệch giữa database với changelog.

## 9. Ví dụ lỗi và cách sửa đúng

### Lỗi 1: đổi changeset tạo bảng thành runOnChange

Giả sử changeset cũ chứa **createTable** đã chạy trên staging. Khi cần thêm cột, người viết sửa chính changeset đó và bật runOnChange. Khi staging chạy lại, Liquibase có thể cố chạy **createTable** một lần nữa và gặp lỗi bảng đã tồn tại.

Cách đúng là giữ changeset tạo bảng ban đầu, rồi thêm changeset **addColumn** mới. Điều này bảo toàn thứ tự lịch sử và cho phép các môi trường đã chạy migration cũ tiến đến schema mới.

### Lỗi 2: dùng runAlways cho câu UPDATE không idempotent

Ví dụ SQL:

~~~sql
UPDATE account
SET reward_points = reward_points + 50
WHERE active = true;
~~~

Nếu đặt **runAlways: true**, mỗi lần update sẽ cộng thêm 50 điểm. Hai môi trường gọi update với tần suất khác nhau có thể tạo ra dữ liệu khác nhau.

Nếu logic thực tế là đặt giá trị xuất phát từ quy tắc xác định, cần thiết kế câu lệnh idempotent hoặc chuyển thành changeset dữ liệu một lần. Không nên đặt runAlways cho một thao tác gia tăng tích lũy trừ khi nghiệp vụ thật sự muốn tác động lặp lại mỗi lần triển khai, điều vốn rất hiếm.

### Lỗi 3: sửa SQL của runAlways nhưng không cho phép thay đổi

Changeset runAlways có định nghĩa ban đầu hợp lệ. Một pull request thay logic SQL nhưng không bật runOnChange. Khi cập nhật database đã từng chạy changeset, Liquibase có thể báo checksum không khớp.

Trước hết cần xác định đó là **sửa định nghĩa cùng một tác vụ luôn chạy** hay **migration nghiệp vụ mới**. Trường hợp đầu có thể dùng cả runAlways và runOnChange sau khi xác minh tính lặp an toàn; trường hợp sau nên tạo changeset riêng. Không tự động sử dụng clear-checksums để bỏ qua review.

### Lỗi 4: nghĩ runOnChange phát hiện mọi thay đổi schema

Một DBA chạy trực tiếp SQL đổi định nghĩa view trong database, nhưng nội dung changelog và checksum không đổi. Lần update sau, runOnChange có thể bỏ qua changeset vì không phát hiện thay đổi trong định nghĩa được quản lý.

Muốn kiểm tra schema drift, cần bổ sung kiểm tra cấu trúc thực tế, truy vấn metadata, diff hoặc quy trình kiểm chứng phù hợp. runOnChange không thay thế công cụ đối chiếu database thực tế với trạng thái kỳ vọng.

## 10. Quy trình kiểm chứng trước khi triển khai

Có thể kiểm tra ba hành vi trên một database thử nghiệm độc lập. Cần dùng phiên bản Liquibase và JDBC driver tương thích, changelog mẫu có đủ đối tượng phụ thuộc và tài khoản có quyền cần thiết.

**Bước 1 — Chạy lần đầu.** Tạo một changeset tạo bảng thông thường, một changeset runOnChange tạo view và một changeset runAlways cập nhật marker. Dùng **validate** để kiểm tra cấu trúc changelog, dùng **update-sql** xem lệnh dự kiến, sau đó mới chạy **update** trên database thử nghiệm.

~~~shell
liquibase validate
liquibase update-sql
liquibase update
~~~

Các lệnh trên giả định cấu hình kết nối, driver và đường dẫn changelog đã được cung cấp qua **liquibase.properties** hoặc tham số tương đương. Dùng cùng file cấu hình trong những lần chạy tiếp theo.

**Bước 2 — Chạy lại khi không đổi file.** Xem SQL dự kiến trước lần update thứ hai, rồi chạy update. Changeset tạo bảng và runOnChange không đổi sẽ được bỏ qua; runAlways sẽ xuất hiện nếu được chọn và đủ điều kiện. Đối chiếu timestamp marker và log để xác nhận.

**Bước 3 — Sửa định nghĩa view.** Thêm một cột tương thích vào SQL view có runOnChange. Chạy validate/update-sql và kiểm tra view được thay thế sau update. Không chỉnh id, author hay đường dẫn file.

**Bước 4 — Thử tình huống checksum lệch.** Trong một bản sao thử nghiệm, sửa nội dung changeset tạo bảng đã chạy và không bật runOnChange. Quan sát lỗi checksum; khôi phục định nghĩa cũ và tạo changeset mới để biểu diễn thay đổi hợp lệ. Không áp dụng phép thử cố ý làm lỗi này trên database dùng chung.

**Bước 5 — Kiểm tra lịch sử.** Với PostgreSQL, có thể đọc bảng metadata như sau:

~~~sql
SELECT id, author, filename, exectype, md5sum, dateexecuted
FROM databasechangelog
ORDER BY orderexecuted;
~~~

Đối chiếu tên changeset, checksum và trạng thái thực thi. Nếu cần chứng minh mỗi lần runAlways đã được gọi, dùng thêm log ứng dụng hoặc job CI/CD vì DATABASECHANGELOG không phải bảng audit append-only cho từng lần gọi.

**Bước 6 — Tập duyệt trên nhiều môi trường.** Đem cùng mã nguồn và changelog qua development, test, staging và production theo đúng quy trình phát hành. Không thay đổi định nghĩa changeset trực tiếp theo từng môi trường. Với Spring Boot, xác định ứng dụng có tự chạy Liquibase khi khởi động hay migration được giao cho job CI/CD; tránh để hai cơ chế cùng chủ động cập nhật mà không có điều phối.

## 11. Nguyên tắc thiết kế để tránh sai lệch lịch sử

Trước khi thêm runAlways hoặc runOnChange, hãy trả lời những câu hỏi sau:

1. **Nếu chạy câu lệnh này lần thứ hai, kết quả có đúng không?** Nếu không, đừng dùng cờ làm changeset chạy lại.
2. **Mục tiêu là chạy khi nội dung thay đổi, hay cứ mỗi lần deploy?** Dùng runOnChange cho nhu cầu đầu; runAlways cho nhu cầu sau.
3. **Nếu đổi nội dung sau khi đã triển khai, đó là sửa một đối tượng có thể thay thế hay là migration mới?** Tạo changeset mới cho migration một lần.
4. **Có dữ liệu hoặc đối tượng phụ thuộc sẽ bị ảnh hưởng khi chạy lại không?** Kiểm tra constraint, lock, transaction, rollback và tương thích phiên bản ứng dụng.
5. **Có cần audit từng lần thực thi không?** Lưu thêm log job hoặc bảng nghiệp vụ được thiết kế riêng; không trông đợi DATABASECHANGELOG ghi mỗi lần chạy thành một bản ghi mới.
6. **Các môi trường có dùng cùng changelog và cùng bộ lọc không?** Khác biệt về context, label, DBMS hoặc tần suất gọi update có thể giải thích khác biệt hành vi.

Với **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, hãy xem checksum là cơ chế bảo vệ lịch sử changeset; **runOnChange** là lựa chọn có chủ đích để cập nhật định nghĩa lặp an toàn khi nội dung đổi; **runAlways** là lựa chọn có chủ đích để thực thi mỗi lần update phù hợp. Khi cần cả hai hành vi, dùng đồng thời hai cờ nhưng chỉ sau khi xác minh logic có thể chạy nhiều lần mà không làm hỏng schema hoặc dữ liệu. Thực hành với precondition, rollback, kiểm tra SQL dự kiến, DATABASECHANGELOG và CI/CD sẽ giúp bạn triển khai nhất quán qua các môi trường.
