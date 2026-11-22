# Phân biệt thay đổi tệp changelog với changeset mới

Trong chương **Checksum và lịch sử** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, điều quan trọng không chỉ là biết Liquibase đọc một tệp changelog, mà còn phải phân biệt hai sự kiện rất khác nhau:

1. **Tệp changelog trong Git thay đổi**: một hoặc nhiều dòng trong tệp được thêm, xóa, di chuyển hoặc sửa.
2. **Một changeset mới xuất hiện đối với database đích**: Liquibase nhìn thấy một định danh changeset chưa được ghi nhận trong lịch sử của chính database đó.

Hai sự kiện không tương đương. Thêm một changeset vào cuối tệp thường là cách phát triển migration bình thường; sửa nội dung một changeset đã chạy có thể dẫn tới lỗi checksum; đổi đường dẫn tệp có thể khiến Liquibase xem một thay đổi cũ như changeset mới dù câu SQL không đổi.

Bài học này đặt sự phân biệt trên nền tảng quản lý schema và dữ liệu bằng **changelog**, **changeset**, **precondition**, **checksum** và **DATABASECHANGELOG**. Mục tiêu là triển khai có kiểm chứng, bảo toàn lịch sử, chuẩn bị rollback và giữ cùng một artifact có thể dùng ở development, staging, production qua Spring Boot hoặc CI/CD.

## 1. Năm khái niệm phải tách bạch

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Changelog file | Tệp mô tả danh sách changeset, có thể include changelog con | db/changelog/changes/customer.yaml |
| Changeset | Đơn vị thay đổi Liquibase quản lý theo định danh | Tạo bảng customer, thêm cột phone |
| Định danh changeset | Bộ ba ID + AUTHOR + FILENAME (hoặc đường dẫn logic tương ứng) | (20261119-001, team-db, changes/customer.yaml) |
| Checksum | Dấu kiểm tra nội dung changeset theo thuật toán/quy tắc của Liquibase | Giá trị MD5SUM được lưu trong DATABASECHANGELOG |
| Lịch sử của database | Các changeset Liquibase đã ghi nhận tại chính database đích | Bảng DATABASECHANGELOG |

Một tệp có thể chứa nhiều changeset, và một changelog gốc có thể include nhiều tệp. Khi bạn thêm một changeset mới vào cuối tệp, **nội dung toàn tệp đã thay đổi**, nhưng nội dung của những changeset trước đó có thể vẫn giữ nguyên.

Ngược lại, khi bạn sửa một dòng SQL nằm trong changeset đã triển khai, **không có changeset mới về định danh**, nhưng nội dung của changeset cũ đã thay đổi. Đây mới là trường hợp có nguy cơ không khớp checksum.

Cần hiểu điều này từ đầu để không áp dụng các cách xử lý sai như xóa bảng lịch sử, gọi clear-checksums vô điều kiện hoặc sửa lại ID để “qua lỗi”.

## 2. Một ví dụ nguồn ban đầu: hai changeset trong một tệp

Giả sử một changelog YAML chứa:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-001-create-customer"
      author: "team-db"
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: VARCHAR(320)
      rollback:
        - dropTable:
            tableName: customer

  - changeSet:
      id: "20261119-002-add-customer-phone"
      author: "team-db"
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: phone
                  type: VARCHAR(30)
      rollback:
        - dropColumn:
            tableName: customer
            columnName: phone
~~~

Khi chạy update lần đầu trên một database thử nghiệm, Liquibase có thể ghi nhận hai hàng lịch sử:

~~~text
ID                                AUTHOR     FILENAME
20261119-001-create-customer      team-db    db/changelog/customer.yaml
20261119-002-add-customer-phone   team-db    db/changelog/customer.yaml
~~~

FILENAME trên đây chỉ là ví dụ; giá trị thực phụ thuộc đường dẫn changelog mà Liquibase giải quyết hoặc cấu hình logicalFilePath. Khi kiểm tra production, phải dùng **giá trị FILENAME thật** trong DATABASECHANGELOG, không suy ra từ đường dẫn hiển thị trên máy cá nhân.

Sau khi hai changeset được thực thi thành công, chúng thông thường không chạy lại ở lần update sau. Liquibase dùng định danh và lịch sử để biết chúng đã được ghi nhận.

## 3. Tình huống A: thêm một changeset mới vào tệp cũ

Giả sử cần thêm cột registered_at. Thay vì sửa 001 hoặc 002, bạn **nối thêm** một changeset:

~~~yaml
  - changeSet:
      id: "20261120-001-add-customer-registered-at"
      author: "team-db"
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: registered_at
                  type: TIMESTAMP
      rollback:
        - dropColumn:
            tableName: customer
            columnName: registered_at
~~~

Đoạn YAML là một phần tử bổ sung trong danh sách databaseChangeLog của tệp ví dụ ở phần 2, không phải một changelog độc lập.

### Điều gì xảy ra?

- Git thấy tệp customer.yaml đã được chỉnh sửa.
- Nội dung changeset 001 và 002 giữ nguyên.
- Liquibase vẫn nhận diện 001 và 002 bằng bộ ba định danh cũ.
- Với các changeset thông thường không có cơ chế chạy lại, Liquibase sẽ bỏ qua 001 và 002 vì đã ghi nhận.
- Changeset 20261120-001 có định danh chưa xuất hiện trong DATABASECHANGELOG của database đích, nên nó được xem xét để chạy nếu đủ điều kiện.

**Kết luận quan trọng:** **thay đổi tệp changelog không có nghĩa checksum của tất cả changeset trong tệp bị thay đổi**. Liquibase không chỉ lấy một hash cho toàn bộ tệp YAML rồi coi mọi changeset đã chạy là khác; checksum được quản lý ở mức changeset theo quy tắc của phiên bản Liquibase.

Không cần tạo một tệp changelog mới cho mỗi thay đổi. Nhóm có thể thêm changeset vào tệp hiện hữu nếu cấu trúc và quy ước cho phép. Ngược lại, tách theo từng tệp cũng có lợi cho quản lý và review, nhưng bản chất lịch sử vẫn dựa vào định danh changeset.

## 4. Tình huống B: sửa nội dung changeset đã chạy

Giả sử changeset 002 đã chạy với cột phone VARCHAR(30). Sau đó một người sửa ngay changeset ấy:

~~~yaml
# Trích đoạn changeset 002 CŨ
- column:
    name: phone
    type: VARCHAR(30)
~~~

thành:

~~~yaml
# Trích đoạn changeset 002 ĐÃ BỊ SỬA
- column:
    name: phone
    type: VARCHAR(60)
~~~

Cả hai phiên bản đều có cùng ID, AUTHOR và FILENAME. Liquibase nhìn thấy **cùng một changeset đã ghi nhận**, nhưng nội dung change có thể làm checksum tính lại khác checksum đã lưu.

Hệ quả phổ biến với changeset thông thường:

1. Liquibase phát hiện nội dung nguồn không còn khớp lịch sử.
2. Validation có thể báo lỗi checksum khi chạy validate/update.
3. Liquibase **không tự hiểu** rằng cần thay đổi độ dài cột đang có từ 30 thành 60.
4. Tùy giai đoạn validation và quy tắc triển khai, update bị chặn hoặc yêu cầu xử lý có chủ đích.

Cách sửa đúng cho một migration đã phát hành là **khôi phục changeset 002 về phiên bản cũ**, sau đó tạo một changeset mới:

~~~yaml
  - changeSet:
      id: "20261120-002-widen-customer-phone"
      author: "team-db"
      changes:
        - modifyDataType:
            tableName: customer
            columnName: phone
            newDataType: VARCHAR(60)
      rollback:
        - modifyDataType:
            tableName: customer
            columnName: phone
            newDataType: VARCHAR(30)
~~~

Rollback thu hẹp VARCHAR(60) về VARCHAR(30) **có thể thất bại hoặc gây mất dữ liệu** nếu có giá trị dài hơn 30 ký tự. Phải kiểm tra dữ liệu, khả năng chuyển kiểu và quy tắc của DBMS trước khi chấp nhận rollback như ví dụ.

**Không sửa changeset lịch sử để thể hiện trạng thái hiện tại.** Lịch sử cần giữ chính xác thao tác đã từng được phê duyệt và thực thi; sự tiến hóa của schema được thể hiện bằng những changeset tiếp theo.

## 5. Quy tắc cốt lõi: định danh và checksum giải quyết hai câu hỏi khác nhau

Liquibase có thể được hình dung qua hai câu hỏi:

**Câu hỏi 1: Đây là changeset nào?**

~~~text
ID + AUTHOR + FILENAME
~~~

Nếu bộ ba không khớp một hàng lịch sử đã ghi nhận, Liquibase thường xem đây là changeset chưa được ghi nhận, sau khi xét bộ lọc và cơ chế xử lý khác.

**Câu hỏi 2: Nội dung của changeset đã ghi nhận có còn phù hợp lịch sử không?**

~~~text
Checksum tính theo quy tắc Liquibase
        so với
MD5SUM đã lưu trong DATABASECHANGELOG
~~~

Nếu cùng định danh nhưng nội dung thuộc phạm vi tính checksum đã thay đổi, có thể phát sinh lỗi checksum hoặc cơ chế chạy lại có chủ đích như runOnChange.

Do đó, bốn kết hợp có thể xuất hiện:

| Định danh so với lịch sử | Nội dung so với lịch sử | Ý nghĩa |
|---|---|---|
| Chưa được ghi nhận | Nội dung mới | Ứng viên changeset mới, sẽ được xét thực thi |
| Đã ghi nhận | Không thay đổi đáng kể với checksum | Changeset thông thường được bỏ qua ở lần update tiếp theo |
| Đã ghi nhận | Checksum khác | Cần điều tra; có thể lỗi validation hoặc chạy lại theo cấu hình |
| Định danh bị đổi | SQL cũ gần như giữ nguyên | Có nguy cơ bị coi là changeset mới và chạy lại thao tác cũ |

Hai câu hỏi phải được trả lời riêng. Không dùng kết luận “SQL vẫn như cũ” để cho rằng đổi id hoặc đường dẫn tệp chắc chắn an toàn; không dùng kết luận “tệp có thêm dòng mới” để cho rằng checksum cũ chắc chắn sẽ lỗi.

## 6. Những loại chỉnh sửa tệp thường gặp

| Hành động trên changelog trong Git | Tác động điển hình | Cách đánh giá |
|---|---|---|
| Thêm changeset mới, giữ nguyên các changeset đã chạy | Có thêm một định danh chưa ghi nhận | Cách phát triển thông thường; review change mới |
| Sửa SQL/change của changeset đã chạy | Có thể đổi checksum | Khôi phục nguồn cũ và tạo changeset điều chỉnh mới |
| Đổi id của changeset đã chạy | Đổi định danh | Có nguy cơ chạy lại; không đổi tùy tiện |
| Đổi author của changeset đã chạy | Đổi định danh | Không chuẩn hóa author hồi tố khi chưa có kế hoạch |
| Di chuyển/đổi tên tệp đã triển khai | Có thể đổi FILENAME | Kiểm tra logicalFilePath và lịch sử |
| Đổi comment/khoảng trắng/format | Không nhất thiết đổi checksum | Kiểm tra quy tắc theo định dạng/phiên bản; không suy luận tuyệt đối |
| Thêm hoặc sửa rollback của changeset cũ | Có thể không ảnh hưởng checksum theo các quy tắc phổ biến | Vẫn là thay đổi hành vi và cần review riêng |
| Sửa precondition, context hoặc label | Có thể không tác động cùng cách với nội dung change | Có thể đổi quyết định triển khai; không coi là vô hại |
| Sửa nội dung sqlFile được tham chiếu | Có thể ảnh hưởng checksum và SQL thực thi | Kiểm tra loại change, phiên bản và nội dung tham chiếu |
| Thay đổi thứ tự/include changelog | Có thể thay thứ tự và phạm vi chạy | Kiểm tra pending changesets và phụ thuộc |
| Thêm runOnChange/runAlways | Thay chính sách chạy lại | Chỉ dùng với migration có thể chạy lặp an toàn |

Đặc biệt, **checksum không phải cơ chế bắt mọi thay đổi source có thể làm đổi hành vi**. Tùy định dạng và phiên bản, có các thuộc tính không tham gia checksum hoặc được chuẩn hóa khi tính. Vì vậy, code review phải kiểm tra cả **diff của changelog** và **tác động vận hành**, không chỉ đợi lỗi checksum.

## 7. Checksum được gắn với changeset, không với commit Git

Một changeset có thể chứa:

- Change type như createTable, addColumn, createIndex.
- SQL hoặc SQL tham chiếu từ tệp ngoài.
- Thuộc tính và nội dung được Liquibase tính vào checksum theo quy tắc của phiên bản.
- Các chỉ thị riêng về rollback, context, label, precondition hoặc cơ chế chạy lại.

Khi Liquibase áp dụng changeset, giá trị checksum phù hợp được ghi vào **MD5SUM** trong DATABASECHANGELOG. Trên một số phiên bản, checksum có thể có tiền tố thể hiện phiên bản thuật toán (ví dụ dạng số phiên bản và dấu hai chấm). Đừng coi tiền tố đó là id changeset hoặc dùng nó để dự đoán số lần triển khai.

**Không phải “đổi một byte trong tệp thì chắc chắn checksum thay đổi”.** Liquibase có thể chuẩn hóa một số dạng trình bày; comment, khoảng trắng, dòng trống hoặc thuộc tính điều khiển có thể được xử lý khác nhau tùy định dạng và version. Đối với SQL trực tiếp hoặc sqlFile, hãy kiểm tra chính xác cách phiên bản dự án phân tích nội dung và tính checksum.

Mặt khác, checksum cũng không chứng minh database thực tế vẫn đúng sau khi triển khai. Nếu một DBA chạy ALTER TABLE bên ngoài Liquibase, checksum lưu trong DATABASECHANGELOG không tự cập nhật. Muốn phát hiện schema drift cần kiểm tra metadata hoặc dùng snapshot/diff và phép kiểm tra dữ liệu.

### Checksum khác không đồng nghĩa SQL đã chạy lại

Một lỗi checksum thường có ý nghĩa “nguồn định nghĩa hiện tại không phù hợp với lịch sử đã ghi nhận”. Nó **không có nghĩa** Liquibase đã áp dụng lại phần SQL bị sửa. Với changeset thông thường, mục tiêu validation chính là ngăn việc âm thầm viết lại lịch sử.

### Chạy lại cũng không đồng nghĩa thêm một định danh mới

Với changeset cấu hình runOnChange hoặc runAlways, Liquibase có thể chạy lại một changeset có **cùng định danh**. Khi đó EXECTYPE và MD5SUM có thể được cập nhật theo quy tắc lịch sử của Liquibase; không nên mặc định có một ID mới chỉ vì changeset được chạy lại.

## 8. Nội dung đã chạy và nội dung còn pending: quy tắc sửa khác nhau

Một changeset đang tồn tại trong Git chưa chắc đã chạy trên tất cả database. Giả sử:

~~~text
                     001      002      003
development          done     done     done
staging              done     done     pending
production           done     pending  pending
~~~

Nếu bạn sửa changeset 003:

- Development đã ghi nhận 003; việc sửa có thể gây lỗi checksum tại đây.
- Staging và production chưa chạy 003; nội dung mới có thể được chạy lần đầu ở những môi trường đó.
- Kết quả là các môi trường không còn cùng lịch sử thực thi cho ID 003.

Vì vậy, quy tắc an toàn theo **toàn bộ vòng đời phát hành**, không chỉ database đang làm việc:

> **Một khi changeset đã chạy ở bất kỳ môi trường dùng chung hoặc đã nằm trong artifact phát hành có khả năng được triển khai, hãy coi nó là bất biến.**

Nếu changeset chỉ mới được tạo trong branch cá nhân, chưa deploy trên database dùng chung và chưa phát hành, có thể chỉnh sửa trước khi merge theo quy trình nhóm. Nhưng cần phân biệt “chưa triển khai ở máy tôi” với “chưa triển khai ở bất kỳ đâu”.

Ngay cả khi sửa changeset pending về mặt kỹ thuật không gây checksum mismatch trên database chưa chạy, việc sửa sau khi đã review/phê duyệt có thể khiến artifact thực tế khác bản đã kiểm thử. CI/CD nên kiểm soát thay đổi theo commit, tag hoặc artifact digest.

## 9. Tên file và logicalFilePath: cùng SQL vẫn có thể trở thành changeset mới

Giả sử Liquibase đã ghi nhận:

~~~text
ID       = 20261119-001-create-customer
AUTHOR   = team-db
FILENAME = db/changelog/2026/customer.yaml
~~~

Bạn chuyển cùng nội dung changeset sang:

~~~text
db/changelog/changes/customer.yaml
~~~

Nếu FILENAME mà Liquibase dùng để nhận diện cũng thay đổi, bộ ba không còn giống lịch sử. Khi đó một thao tác CREATE TABLE từng chạy có thể được xem là changeset mới và cố thực thi thêm lần nữa, dẫn đến lỗi bảng đã tồn tại.

Đây **không nhất thiết là lỗi checksum**: nó có thể là **lỗi định danh**. Liquibase đang so sánh với một khóa khác nên không còn thấy dòng lịch sử tương ứng.

Liquibase có cơ chế **logicalFilePath** để giữ tên logic cho lịch sử trong những trường hợp tổ chức lại đường dẫn vật lý. Tuy nhiên, cú pháp, phạm vi kế thừa khi include/includeAll và mức hỗ trợ có thể phụ thuộc phiên bản Liquibase. Cần kiểm tra tài liệu của bản đang chạy, đặt đường dẫn logic **khớp giá trị FILENAME đã lưu**, rồi validate/status/update-sql trên database thử nghiệm có lịch sử cũ trước khi triển khai.

Không tùy tiện sửa trực tiếp cột FILENAME trong DATABASECHANGELOG như bước dọn cấu trúc thư mục. Nếu cần chuyển đổi lịch sử đã có, phải có kế hoạch, backup, đối chiếu và phê duyệt cụ thể.

## 10. Changelog gốc, include và tổ chức nhiều tệp

Ví dụ changelog gốc:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/order.yaml
      relativeToChangelogFile: true
~~~

Bạn có thể:

- Thêm changeset mới vào customer.yaml.
- Thêm một tệp changes/20261120-customer-index.yaml và include tệp đó.
- Thêm changelog con mới cho một tính năng độc lập.
- Đổi vị trí include để sắp xếp các migration **chưa chạy**, nếu phụ thuộc thực sự cho phép.

Vấn đề cần xem xét:

1. **Tên file và đường dẫn logic** có thể là thành phần định danh; di chuyển tệp đã chạy không giống việc thêm tệp mới.
2. **Thứ tự changeset** do changelog và include xác định, không phải do ID dạng ngày tháng tự động sắp xếp.
3. **Tệp được include nhiều lần** có thể gây trùng định danh hoặc hành vi ngoài dự kiến, tùy cấu trúc và cơ chế include.
4. **includeAll** thường dựa vào cách sắp xếp tệp; việc thêm/đổi tên tệp có thể làm thay đổi thứ tự nạp. Không dùng tên tệp mới để chèn một migration trước những thay đổi đã ghi nhận mà không kiểm tra phụ thuộc.
5. Một thay đổi chưa chạy ở production có thể đã chạy ở staging; đánh giá trên từng database, không chỉ trên Git diff.

Nếu muốn tái cấu trúc hàng loạt changelog đã phát hành, nên coi đó là một dự án migration metadata riêng, không trộn với các thay đổi schema mới và không làm chỉ để cải thiện thẩm mỹ repository.

## 11. Cách đọc DATABASECHANGELOG khi có tranh cãi về lịch sử

Truy vấn cơ bản:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    DATEEXECUTED,
    ORDEREXECUTED,
    EXECTYPE,
    MD5SUM
FROM DATABASECHANGELOG
ORDER BY DATEEXECUTED, ORDEREXECUTED;
~~~

Tùy cấu hình, bảng DATABASECHANGELOG có thể nằm trong schema riêng, vì vậy cần dùng schema phù hợp hoặc cấu hình search path đúng.

Các cột cần đọc cùng nhau:

| Cột | Câu hỏi giúp trả lời |
|---|---|
| ID | Changeset được người viết định danh thế nào? |
| AUTHOR | Ai/nhóm nào được ghi nhận là người tạo changeset? |
| FILENAME | Đường dẫn định danh Liquibase đã lưu là gì? |
| DATEEXECUTED | Liquibase ghi nhận thời điểm nào? |
| ORDEREXECUTED | Thứ tự ghi nhận thực thi theo cách Liquibase quản lý |
| EXECTYPE | Thực thi, chạy lại hay đánh dấu đã chạy? |
| MD5SUM | Checksum Liquibase lưu cho changeset đã ghi nhận |

Trong các tình huống điều tra:

- Nếu ID/AUTHOR trùng nhưng FILENAME khác, nghĩ đến **di chuyển/đổi tên tệp** hoặc logicalFilePath.
- Nếu cả bộ ba trùng nhưng có lỗi checksum, nghĩ đến **thay đổi nội dung** hoặc sự khác biệt quy tắc/version.
- Nếu không có dòng lịch sử nhưng bảng/cột đã tồn tại, nghĩ đến **DDL ngoài Liquibase, baseline, schema drift hoặc changeset bị nhận diện sai**.
- Nếu EXECTYPE=MARK_RAN, không coi đó là bằng chứng phần SQL của changeset đã thật sự chạy.

Không chỉnh MD5SUM, ID, AUTHOR hay FILENAME bằng một câu UPDATE SQL thủ công chỉ để tránh lỗi. Bảng này là lịch sử triển khai và phải được quản lý bằng quy trình chính thức có kiểm chứng.

## 12. Phân biệt “file đã sửa” với “có thay đổi cần update” bằng công cụ

Git diff trả lời câu hỏi **source thay đổi những gì**; Liquibase trả lời câu hỏi **database này còn changeset nào cần xử lý**.

Một quy trình kiểm tra thông thường:

~~~bash
# Đã cấu hình đúng kết nối, changelog gốc và các filter.
liquibase validate
liquibase status --verbose
liquibase update-sql
~~~

Giải thích:

- **validate** phát hiện lỗi định dạng, trùng ID/AUTHOR/FILENAME trong phạm vi nạp và một số sai lệch checksum/lịch sử theo khả năng của phiên bản.
- **status --verbose** hiển thị changeset đang chờ đối với database và bộ lọc hiện tại.
- **update-sql** tạo SQL dự kiến của những thao tác mà update có thể áp dụng, phục vụ review trước khi thay đổi database.

Không coi validate là bằng chứng schema hiện tại đúng về cấu trúc hoặc dữ liệu; không coi status là danh sách mọi khác biệt giữa Git và database; và không coi update-sql là bảo đảm tuyệt đối cho kết quả runtime.

Khi cần điều tra một changeset cụ thể, có thể đối chiếu checksum qua chức năng **calculate-checksum** nếu phiên bản Liquibase có hỗ trợ cú pháp phù hợp. Cần cung cấp chính xác path/ID/author theo cách CLI yêu cầu và không nhầm output với MD5SUM của một changeset khác trùng ID.

Điều quan trọng là **dùng cùng phiên bản Liquibase, extension, changelog revision, cấu hình parameter và database đích** khi đối chiếu. Nếu SQL được tạo từ một artifact nhưng update chạy một artifact khác, kết quả review không còn đáng tin cậy.

## 13. Lưu ý về sửa comment, format, rollback và các thuộc tính điều khiển

Không phải mọi thay đổi trong Git diff đều có cùng mức rủi ro. Có những trường hợp thay đổi comment hoặc khoảng trắng không ảnh hưởng checksum; có những định dạng SQL mà comment/delimiter hoặc văn bản được phân tích lại ảnh hưởng nội dung được thực thi.

Các trường hợp cần thận trọng:

**Sửa comment hoặc thụt lề.** Với nhiều loại changeset, thay đổi trình bày không làm thay đổi ý nghĩa migration; nhưng không nên khẳng định tuyệt đối rằng checksum không đổi. Phải kiểm tra bằng phiên bản Liquibase của dự án khi tệp đã phát hành.

**Sửa rollback của changeset cũ.** Theo các quy tắc checksum thường gặp, rollback không nhất thiết được tính như nội dung change đã thực thi. Nhưng việc sửa rollback thay đổi **khả năng hoàn tác** và phải được review, thử rollback trên database đại diện; không dùng checksum không đổi làm chứng nhận an toàn.

**Sửa context, label hoặc precondition.** Những thông số này có thể thay đổi phạm vi chọn hoặc quyết định chạy một changeset. Một số thuộc tính có thể không tham gia checksum giống SQL của changeset, nên thay đổi chúng có thể tạo ra hành vi khác mà không có lỗi MD5SUM tương ứng.

**Sửa đường dẫn sqlFile.** Nếu changeset tham chiếu SQL ở một tệp khác, bạn phải kiểm tra cả nội dung tệp đó, cách Liquibase phân tích lệnh, splitStatements và endDelimiter. Khả năng checksum thay đổi còn phụ thuộc change type và version.

**Sửa logicalFilePath.** Thay đổi này liên quan trực tiếp tới định danh lịch sử; cần đối chiếu FILENAME, không chỉ checksum.

Thông điệp chung: **checksum là một cơ chế bảo vệ, không phải toàn bộ quy trình review**. Một thay đổi không kích hoạt lỗi checksum vẫn có thể làm hỏng phạm vi triển khai hoặc rollback.

## 14. Ngoại lệ có chủ đích: runOnChange và runAlways

Thông thường, changeset đã ghi nhận không chạy lại. Hai thuộc tính thay đổi hành vi này:

### runOnChange

Một changeset có **runOnChange: true** được thiết kế để Liquibase chạy lại khi phần nội dung khiến checksum thay đổi theo quy tắc của nó. Trường hợp phổ biến là định nghĩa view hoặc stored procedure có thể áp dụng lại.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-050-customer-view"
      author: "team-db"
      runOnChange: true
      changes:
        - createView:
            viewName: v_customer_email
            replaceIfExists: true
            selectQuery: |
              SELECT id, email
              FROM customer
~~~

Khi SELECT thay đổi, changeset có thể được chạy lại để thay thế view. Cần kiểm tra DBMS hỗ trợ replaceIfExists và hành vi của createView. Không bật runOnChange cho một INSERT seed hay addColumn không idempotent chỉ để sửa thay đổi lịch sử mà không tạo changeset mới.

### runAlways

Với **runAlways: true**, changeset được thực thi ở mỗi lần update phù hợp với bộ lọc. Phù hợp với một số tác vụ được thiết kế chạy lặp an toàn, nhưng có nguy cơ tạo dữ liệu trùng hoặc giữ lock nếu dùng sai.

**Hai cơ chế này không có nghĩa tệp changelog “tự động có changeset mới”**. Chúng điều chỉnh quy tắc chạy lại **cùng một định danh**. Nếu muốn một thay đổi schema tiến thêm một bước có lịch sử độc lập, giải pháp thông thường vẫn là tạo changeset mới.

Không sửa nội dung changeset runAlways tùy tiện rồi cho rằng mọi thứ luôn hợp lệ: thay đổi checksum ở changeset loại này có thể cần thêm cấu hình hoặc cơ chế xử lý phù hợp theo version. Cần kiểm chứng với công cụ và DBMS thực tế.

## 15. Các cơ chế xử lý checksum đặc biệt và giới hạn

Khi gặp sai lệch lịch sử, có một số công cụ/tùy chọn dễ bị dùng nhầm:

| Cơ chế | Ý nghĩa chính | Không nên dùng để |
|---|---|---|
| validCheckSum | Chấp nhận checksum cụ thể đã được phê duyệt của một changeset | Che sửa đổi ngoài ý muốn hoặc bỏ qua điều tra |
| clear-checksums | Làm trống các checksum đã lưu để Liquibase tính lại theo quy trình tương ứng | Ép migration cũ thực thi lại hoặc “sửa” schema drift |
| runOnChange | Chạy lại changeset phù hợp khi nội dung thay đổi | Thay thế mọi changeset điều chỉnh dữ liệu/DDL |
| runAlways | Chạy lại changeset theo mỗi lần update phù hợp | Sửa thiếu sót lịch sử bất chấp tính idempotent |
| changelog-sync / mark-ran theo cơ chế phù hợp | Ghi nhận changeset mà không chạy SQL trong những quy trình baseline xác định | Che tình trạng schema thiếu hoặc dữ liệu không đúng |
| rollback/forward fix | Hoàn tác có kiểm soát hoặc tạo changeset sửa tiến | Được thực hiện không cần kiểm tra phụ thuộc, dữ liệu, phiên bản code |

### Vì sao clear-checksums không phải nút “chạy lại toàn bộ”?

Clear-checksums không tự biến mọi changeset cũ thành changeset mới. Liquibase có thể tính lại checksum trong lần triển khai/đọc lịch sử kế tiếp theo quy trình của phiên bản, trong khi ID/AUTHOR/FILENAME vẫn là những định danh đã ghi nhận. Việc gọi clear-checksums không phải một phương án để đưa database về schema đúng.

Nếu thực sự cần khôi phục một bản ghi lịch sử sau sự cố, phải xác định trạng thái thực tế, bản changelog đã chạy, mức sai lệch và phương án kiểm toán. Không sửa các cột history bằng tay dựa trên phỏng đoán rằng checksum là vấn đề duy nhất.

### Khi nào validCheckSum có thể được cân nhắc?

Có thể có tình huống lịch sử cũ hợp lệ nhưng cách biểu diễn thay đổi do nâng cấp công cụ hoặc tái cấu trúc có kiểm soát. Khi đó, việc chấp nhận một checksum cụ thể chỉ nên thực hiện sau khi:

1. Biết rõ checksum cũ và checksum mới tương ứng với phiên bản nguồn nào.
2. Chứng minh sự khác biệt không làm sai trạng thái database.
3. Xác nhận các môi trường và đường dẫn định danh liên quan.
4. Có review/phê duyệt và kế hoạch hậu kiểm rõ ràng.

Đây là ngoại lệ; **mặc định thêm changeset mới** cho một thay đổi nghiệp vụ/schema mới.

## 16. Các phiên bản checksum và nâng cấp Liquibase

Giá trị MD5SUM không nên được xem là một chuỗi MD5 thuần độc lập với version Liquibase. Công cụ có thể thay đổi cách chuẩn hóa hoặc version thuật toán checksum, và có cơ chế xử lý checksum lịch sử khi nâng cấp.

Một đợt nâng cấp Liquibase có thể khiến checksum được thể hiện theo phiên bản khác hoặc được tính lại theo cơ chế chính thức. Điều đó **không tự chứng minh changelog đã bị sửa có hại**, nhưng cũng không cho phép bỏ qua mọi lỗi checksum phát sinh sau nâng cấp.

Quy trình nâng cấp an toàn:

1. Ghi nhận version Liquibase/extension cũ và mới.
2. Sao lưu lịch sử hoặc đảm bảo khả năng khôi phục database thử nghiệm.
3. Thử cùng artifact changelog trên bản sao database có DATABASECHANGELOG cũ.
4. Chạy validate/status, kiểm tra MD5SUM và các thông báo nâng cấp.
5. Kiểm tra SQL dự kiến không chứa migration lịch sử ngoài ý muốn.
6. Chỉ sau khi kết quả được giải thích mới tiếp tục staging và production.

Không sửa tay tiền tố version của MD5SUM. Nếu công cụ đưa ra thông báo checksum khác, cần phân biệt **khác nội dung nguồn**, **khác định danh** và **quy tắc checksum của phiên bản**.

## 17. Tác động của việc sửa changelog tới rollback

Rollback thường dựa vào lịch sử changeset đã ghi nhận và phần rollback được khai báo hoặc khả năng rollback tự động của change type. Do đó, thay đổi nguồn có thể tác động đến khả năng khôi phục ngay cả khi không xuất hiện lỗi checksum.

Ví dụ changeset đã thực thi:

~~~yaml
  - changeSet:
      id: "20261119-060-add-customer-region"
      author: "team-db"
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: region_code
                  type: VARCHAR(10)
      rollback:
        - dropColumn:
            tableName: customer
            columnName: region_code
~~~

Nếu ứng dụng đã ghi dữ liệu vào region_code sau triển khai, rollback DROP COLUMN sẽ xóa dữ liệu đó. Việc checksum và lịch sử hoàn toàn đúng không tự biến rollback thành an toàn.

Nếu một người đổi tên tệp changelog hoặc ID trước khi rollback, Liquibase có thể không còn ánh xạ đúng changeset đã ghi nhận với định nghĩa hiện tại. Vì vậy, rollback cần cùng cấu hình đường dẫn định danh và giá trị changelog parameters phù hợp với lịch sử đã thực thi.

Khi cần một thay đổi mới nhằm sửa dữ liệu/schema, thường nên sử dụng **forward fix** bằng changeset bổ sung, có kế hoạch đảo ngược riêng. Không phụ thuộc vào việc sửa bản cũ để “biến rollback thành update” hoặc “đưa history về đúng”.

## 18. Spring Boot: giữ changelog bất biến khi phát hành ứng dụng

Khi tích hợp Liquibase vào Spring Boot:

~~~yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
~~~

Spring Boot có thể gọi Liquibase trong quá trình khởi động ứng dụng. Nếu artifact mới chứa một changeset bổ sung, Liquibase sẽ xét changeset đó theo lịch sử database đích.

Lợi ích: mã ứng dụng và changelog đi cùng bản build. Nhưng có những rủi ro:

- Nếu sửa một changeset đã chạy, ứng dụng có thể không khởi động do lỗi checksum.
- Nếu đổi đường dẫn changelog hoặc cách include, một changeset đã ghi nhận có thể bị xem là mới.
- Nếu nhiều instance khởi động đồng thời, DATABASECHANGELOGLOCK giúp điều phối Liquibase nhưng không làm ứng dụng cũ tự tương thích với schema mới.
- Nếu deployment rollback về artifact cũ nhưng database đã chạy changeset mới, lịch sử/schema có thể đi trước mã ứng dụng; cần thiết kế thay đổi tương thích ngược.
- Chạy cùng build ở dev/prod không có nghĩa hai database có cùng trạng thái history.

Đối với các thay đổi phá tương thích, nên dùng **expand–migrate–contract**: thêm cột/bảng mới trước, triển khai mã tương thích, chuyển dữ liệu/traffic, sau đó loại bỏ cấu trúc cũ bằng changeset riêng. Không sửa changeset addColumn cũ thành dropColumn để cập nhật trực tiếp một trạng thái mong muốn.

Với production, có thể tách job chạy Liquibase khỏi startup ứng dụng để tạo cổng phê duyệt, nhưng cần tránh hai cơ chế migration cùng tranh quyền không có quy tắc ownership.

## 19. CI/CD: làm sao nhận diện đúng một thay đổi migration?

Pipeline có thể phân tích diff trong Git, nhưng không nên coi “file có thay đổi” là bằng chứng tự động rằng phải chạy lại tất cả changeset trong file đó.

Các bước kiểm soát nên bao gồm:

1. **Đóng băng changelog revision/artifact** được phát hành.
2. **Review diff**: xác định changeset mới, changeset cũ bị sửa, tệp bị đổi tên/di chuyển.
3. **Kiểm tra định danh**: id, author, đường dẫn logic/filename và va chạm.
4. **Kiểm tra tính bất biến**: các changeset đã ghi nhận ở môi trường dùng chung có còn nguyên vẹn không.
5. **Chạy validate** trên bản Liquibase dự kiến dùng.
6. **Chạy status --verbose** với đúng database, context/label và parameter.
7. **Review update-sql** để biết thay đổi thực tế sẽ được chọn trên database đích.
8. **Thử trên database có lịch sử đại diện** rồi mới triển khai staging/production.
9. **Chạy update bằng job có quyền phù hợp**, theo kế hoạch rollback/forward fix.
10. **Đối chiếu DATABASECHANGELOG và schema/dữ liệu** sau cập nhật.

Ví dụ phân loại một pull request:

~~~text
PR #184
  + changeset 20261120-001-add-customer-region
  = changeset 20261119-001-create-customer giữ nguyên
  = changeset 20261119-002-add-customer-phone giữ nguyên

Kết luận:
  - Một thay đổi mới được thêm.
  - Không sửa các changeset đã chạy.
  - Cần xác minh update-sql chỉ chứa tác động mong đợi.
~~~

Ngược lại, nếu PR chỉnh VARCHAR(30) thành VARCHAR(60) trực tiếp trong changeset 002 đã triển khai, pipeline nên chặn để yêu cầu tạo changeset modifyDataType mới.

### Không so sánh chỉ số lượng changeset

Hai database có cùng số hàng trong DATABASECHANGELOG chưa chắc có cùng schema. Chúng có thể khác FILENAME, EXECTYPE, checksum, dữ liệu hoặc từng bị sửa thủ công. Phải đối chiếu định danh, lịch sử, SQL thực tế và trạng thái schema khi điều tra.

## 20. Tình huống lỗi thường gặp

| Triệu chứng | Nguyên nhân cần xem xét | Hướng xử lý |
|---|---|---|
| Sửa một file YAML rồi tất cả migration bị nghi đã thay đổi | Nhầm checksum toàn file với checksum từng changeset | Xác định đúng changeset bị sửa và kiểm tra lịch sử |
| Checksum validation failed | Nội dung changeset đã chạy bị sửa hoặc quy tắc version khác | So sánh Git revision/MD5SUM, phục hồi định nghĩa cũ và thêm changeset mới nếu cần |
| Table already exists sau khi đổi tên file | FILENAME trở thành định danh mới | Đối chiếu FILENAME và logicalFilePath |
| Changeset đã chạy lại xuất hiện trong status | Đổi id, author, filename hoặc bộ lọc/trạng thái khác | Kiểm tra khóa ID/AUTHOR/FILENAME và DATABASECHANGELOG |
| Comment sửa nhưng checksum không đổi | Comment/format không tham gia checksum theo quy tắc hiện hành | Không mặc định đây là lỗi; vẫn review thay đổi source |
| Precondition/context sửa mà không lỗi MD5SUM | Thuộc tính điều khiển không nhất thiết tính như nội dung change | Kiểm tra phạm vi thực thi và chính sách onFail |
| Thêm changeset mới nhưng status không liệt kê | Changelog con chưa được include, filter không chọn hoặc dùng sai database | Kiểm tra include, context/label, JDBC URL và history |
| Chạy update rồi không có SQL mới | Changeset đã ghi nhận hoặc không được chọn | Kiểm tra status, EXECTYPE, runOnChange/runAlways |
| Changeset đánh dấu MARK_RAN nhưng thiếu đối tượng | Precondition bỏ qua thực thi | Kiểm tra schema thực, không dựa duy nhất vào lịch sử |
| Lỗi checksum sau nâng cấp Liquibase | Thuật toán/format checksum hoặc source version thay đổi | Thử trên database có lịch sử, xác nhận migration và version |
| validCheckSum làm pipeline xanh nhưng schema sai | Chấp nhận checksum không xác minh trạng thái | Dừng lại, kiểm tra schema drift và kế hoạch sửa tiến |
| Rollback không tìm thấy changeset cũ | Định danh hoặc đường dẫn changelog thay đổi | Khôi phục ánh xạ history với changelog đã thực thi |
| Cùng changeset chạy ở staging nhưng chưa ở production | Mỗi database có lịch sử riêng | Promote cùng artifact; không sửa source đã chạy |
| SQL cũ được chạy lại dù không đổi nội dung | Định danh bị thay hoặc dùng thuộc tính chạy lại | Kiểm tra ID/AUTHOR/FILENAME, runAlways/runOnChange |

Khi gặp sự cố, hãy phân loại thành ba nhóm trước: **định danh thay đổi**, **checksum nội dung khác** hoặc **trạng thái/schema database khác**. Một thông báo lỗi bề ngoài giống nhau có thể có nguyên nhân khác nhau và cần phương án sửa khác nhau.

## 21. Thực hành có kiểm chứng trên hai database

**Bối cảnh:** có hai database thử nghiệm A và B với schema ban đầu giống nhau. Cùng một changelog customer.yaml chứa changeset 001 và 002. Mục tiêu là thấy sự khác nhau giữa thêm changeset, sửa changeset và đổi đường dẫn changelog.

### Phần A — Ghi nhận lịch sử ban đầu

1. Cấu hình Liquibase cho database A và chạy validate, status --verbose.
2. Chạy update-sql, xác nhận SQL tạo bảng và thêm cột.
3. Chạy update trên A.
4. Truy vấn DATABASECHANGELOG, ghi nhận ID/AUTHOR/FILENAME/MD5SUM của 001 và 002.
5. Lặp lại với B hoặc giữ B chưa chạy 002 để mô phỏng môi trường khác tiến độ.

### Phần B — Thêm changeset mới

1. Giữ nguyên nội dung 001 và 002; thêm changeset 003 tạo cột registered_at.
2. Dùng lại đúng changelog filename/logicalFilePath.
3. Chạy validate và status trên A, xác minh **003 là changeset mới**.
4. Chạy update-sql; xác nhận không có SQL tạo lại bảng hoặc thêm lại phone.
5. Chạy update và đọc lại DATABASECHANGELOG; 001/002 vẫn được nhận diện như cũ.

### Phần C — Sửa changeset cũ để quan sát checksum

1. **Chỉ trên database thử nghiệm có thể khôi phục**, sửa VARCHAR(30) trong 002 thành VARCHAR(60).
2. Chạy validate hoặc update trong môi trường học tập để quan sát cơ chế kiểm tra checksum của phiên bản đang dùng.
3. Ghi lại thông báo lỗi và so sánh định danh: ID/AUTHOR/FILENAME **không đổi**.
4. Hoàn nguyên 002 về nguồn đã triển khai.
5. Tạo changeset 004 modifyDataType thay vì sửa 002.

### Phần D — Đổi tên/di chuyển changelog

1. Trên bản sao riêng của database A, đổi đường dẫn tệp customer.yaml nhưng giữ nội dung 001/002.
2. Chạy status và đối chiếu FILENAME; **không chạy update** nếu Liquibase xem changeset cũ thành mới.
3. Nghiên cứu logicalFilePath phù hợp với phiên bản Liquibase được sử dụng; kiểm tra rằng tên logic khớp lịch sử.
4. Khôi phục cách định danh cũ hoặc xác nhận cấu hình logicalFilePath đúng trước khi kết thúc.

### Câu hỏi tự kiểm tra

- Nếu thêm changeset 003 vào một tệp đã có 001 và 002, checksum của 001/002 có buộc phải thay đổi không? **Không.** Nếu nội dung các changeset cũ được giữ nguyên, việc thêm 003 thường không đổi checksum của chúng.
- Nếu sửa SQL trong changeset 002 đã chạy nhưng giữ id, author, filename, Liquibase có coi đó là 003 không? **Không.** Đó là cùng định danh với nội dung khác, có thể gây lỗi checksum.
- Nếu đổi tên file của 002 nhưng giữ SQL, tại sao có thể chạy lại? **Vì FILENAME có thể là một phần định danh đã thay đổi.**
- Nếu thêm runOnChange, đó có phải changeset mới không? **Không.** Đây là chính sách chạy lại một định danh hiện có.
- Nếu production chưa chạy 002, có nên sửa 002 chỉ vì production chưa có lịch sử? **Không**, nếu staging hoặc development dùng chung đã chạy 002.
- validCheckSum có sửa cột VARCHAR(30) thành VARCHAR(60) không? **Không.** Nó liên quan đến việc chấp nhận checksum, không tự áp dụng DDL chuyển đổi schema.
- Tại sao cần đọc cả Git diff và DATABASECHANGELOG? **Vì Git thể hiện thay đổi source, còn DATABASECHANGELOG thể hiện những changeset Liquibase đã ghi nhận trên từng database.**

## 22. Checklist review thay đổi changelog và lịch sử

- [ ] Đã phân biệt tệp changelog thay đổi với changeset mới.
- [ ] Đã kiểm tra bộ ba ID/AUTHOR/FILENAME của những changeset đã chạy.
- [ ] Không sửa nội dung changeset đã triển khai; thay đổi schema mới có changeset mới.
- [ ] Đã kiểm tra tệp bị rename/move và tác động tới logicalFilePath.
- [ ] Đã xác nhận thứ tự include/includeAll và phụ thuộc giữa changeset.
- [ ] Đã phân loại comment, rollback, context, label, precondition và thay đổi SQL khi review diff.
- [ ] Không mặc định checksum bắt mọi thay đổi source, cũng không mặc định đổi ký tự nào cũng đổi checksum.
- [ ] Đã đối chiếu MD5SUM/EXECTYPE với lịch sử của database đích.
- [ ] Đã xét tất cả môi trường có thể từng chạy changeset, không chỉ máy dev.
- [ ] Không dùng clear-checksums hoặc validCheckSum như đường tắt để giấu drift.
- [ ] runOnChange/runAlways chỉ được dùng cho thay đổi có thể chạy lại có chủ đích.
- [ ] Đã chạy validate, status --verbose và review update-sql với đúng version và cấu hình.
- [ ] Đã xác minh không có changeset cũ bất ngờ xuất hiện trong danh sách pending.
- [ ] Đã kiểm tra rollback/forward fix cho các changeset mới hoặc được phép chạy lại.
- [ ] Artifact/changelog được giữ nguyên giữa các môi trường phát hành.
- [ ] Đã kiểm chứng DATABASECHANGELOG và schema/dữ liệu thực tế sau update.
- [ ] Đã lưu log và bằng chứng thực thi, không ghi credentials hoặc secret vào repository.

**Kết luận:** thay đổi một tệp changelog là một sự kiện của **mã nguồn**, còn changeset mới là một sự kiện được xác định bằng **định danh Liquibase đối với lịch sử database**. Checksum bảo vệ nội dung của changeset đã ghi nhận, không phải chỉ kiểm tra rằng file có đổi hay không. Giữ nguyên những changeset đã phát hành, thêm changeset mới cho sự tiến hóa schema/dữ liệu, kiểm soát FILENAME và xác minh DATABASECHANGELOG là nền tảng để migration Liquibase an toàn, có thể rollback và tái lập qua Spring Boot hoặc CI/CD.
