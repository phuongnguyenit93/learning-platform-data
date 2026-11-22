# Lựa chọn HALT, WARN, CONTINUE và MARK_RAN theo phạm vi hỗ trợ

## 1. Mục tiêu và bối cảnh

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Việc thực hành bao gồm migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Bài thuộc chương **Tiền điều kiện**, tập trung vào cách lựa chọn **HALT, WARN, CONTINUE và MARK_RAN** khi một precondition không đạt, đồng thời phân biệt **phạm vi changelog** và **phạm vi changeset**. Chọn sai hành vi có thể khiến pipeline dừng không cần thiết, bỏ qua migration còn phải chạy, hoặc nghiêm trọng hơn: ghi lịch sử “đã chạy” trong khi schema và dữ liệu chưa đúng.

Sau bài học, bạn có thể:

- Phân biệt precondition **failed** với precondition **error** và biết khi nào dùng onFail, onError.
- Giải thích hành vi chính xác của HALT, WARN, CONTINUE và MARK_RAN.
- Biết lựa chọn nào được hỗ trợ ở **changelog-level** và **changeset-level**.
- Dự đoán tác động đến DATABASECHANGELOG, các changeset tiếp theo, lần chạy sau và rollback.
- Thiết kế precondition, mã lỗi và kiểm chứng để không che giấu schema drift.
- Vận dụng quy trình quyết định phù hợp cho môi trường local, staging, production và CI/CD.

## 2. Precondition là gì và chạy ở thời điểm nào?

**Precondition** là phép kiểm tra điều kiện trước khi Liquibase thực hiện một changelog hoặc changeset. Ví dụ: database có đúng loại DBMS không; bảng customer đã tồn tại chưa; cột status đã được thêm chưa; hay một truy vấn SQL trả về số lượng dữ liệu dự kiến.

Có thể mô tả luồng xử lý bằng sơ đồ:

~~~mermaid
flowchart TD
    A["Liquibase đọc changelog"] --> B["Đánh giá precondition phù hợp"]
    B --> C{"Kết quả?"}
    C -->|Đạt| D["Tiếp tục xử lý changeset"]
    C -->|Không đạt| E["Áp dụng onFail"]
    C -->|Lỗi kiểm tra| F["Áp dụng onError"]
    D --> G["Thực hiện change theo lịch sử hiện tại"]
    E --> H["HALT / WARN / CONTINUE / MARK_RAN theo phạm vi hỗ trợ"]
    F --> I["Xử lý lỗi đánh giá, thường ưu tiên HALT"]
~~~

Precondition không thay thế database constraint. Kiểm tra cột tồn tại không bảo đảm kiểu dữ liệu, tính nullability, default và constraint đúng; kiểm tra bảng tồn tại không bảo đảm bảng thuộc đúng schema. Ngoài ra, giữa thời điểm kiểm tra và chạy DDL vẫn có thể xuất hiện thay đổi do tiến trình khác. Vì vậy, precondition là **hàng rào kiểm tra tại thời điểm migration**, không phải bằng chứng tuyệt đối về trạng thái mọi thời điểm.

Một changeset bình thường được Liquibase nhận diện bằng **id, author và đường dẫn changelog** (hoặc đường dẫn logic nếu được cấu hình). Liquibase kiểm tra lịch sử ở **DATABASECHANGELOG** để quyết định changeset cần được xử lý. Precondition được đánh giá trong luồng xử lý đó, cùng các cơ chế lọc và điều khiển thực thi liên quan. Cần thử trên đúng bản Liquibase để xác nhận hành vi với các tuỳ chọn đặc biệt như runAlways hoặc runOnChange.

## 3. Failed khác Error: chọn onFail hay onError

Đây là phân biệt cốt lõi.

**Failed** nghĩa là precondition **được đánh giá bình thường nhưng kết quả không đạt yêu cầu**.

Ví dụ: kiểm tra tableExists cho bảng orders nhưng bảng chưa tồn tại. Liquibase có thể xác định điều kiện là false; nhánh **onFail** sẽ được sử dụng.

**Error** nghĩa là Liquibase **không đánh giá được precondition theo cách dự kiến** do một sự cố.

Ví dụ: truy vấn sqlCheck bị lỗi cú pháp, người dùng database không có quyền đọc metadata, kết nối bị gián đoạn hoặc đối tượng tham chiếu gây ngoại lệ. Nhánh **onError** sẽ được sử dụng.

| Kết quả kiểm tra | Ví dụ | Thuộc tính xử lý |
|---|---|---|
| Đạt | Bảng mong đợi tồn tại | Tiếp tục theo luồng bình thường |
| Failed | Bảng mong đợi không tồn tại | **onFail** |
| Error | Không thể kiểm tra vì SQL lỗi hoặc quyền không đủ | **onError** |

Không nên cấu hình onError để “bỏ qua” mọi lỗi hạ tầng. Một vấn đề quyền truy cập hoặc SQL lỗi không chứng minh schema đã đạt trạng thái mong muốn. Với migration quan trọng, lựa chọn bảo thủ thường là **onError: HALT**.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-001
      author: database-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: customer
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: note
                  type: VARCHAR(255)
~~~

Ở đây, nếu bảng customer không có, onFail yêu cầu dừng. Nếu việc kiểm tra metadata bị lỗi, onError cũng dừng. Nhờ đó pipeline không tiếp tục khi thiếu điều kiện cần thiết.

## 4. Phạm vi hỗ trợ: changelog-level và changeset-level

Liquibase cho phép khai báo precondition ở hai phạm vi quan trọng:

1. **Global / changelog-level**: precondition áp dụng cho changelog. Phù hợp khi muốn xác nhận điều kiện chung, chẳng hạn toàn bộ changelog này chỉ dành cho PostgreSQL.
2. **Local / changeset-level**: precondition gắn với một changeset. Phù hợp khi cần kiểm tra bảng, cột, index hoặc dữ liệu liên quan đến riêng changeset ấy.

Các giá trị **HALT** và **WARN** được hỗ trợ ở cả hai phạm vi. **CONTINUE** và **MARK_RAN** chỉ hợp lệ khi precondition nằm **bên trong changeset**; ở phạm vi changelog chúng không có đối tượng changeset cụ thể để bỏ qua hoặc đánh dấu đã chạy.

| Giá trị xử lý | Changelog-level | Changeset-level | Ý nghĩa chung |
|---|---|---|---|
| **HALT** | Hỗ trợ | Hỗ trợ | Dừng quá trình xử lý khi precondition không đạt |
| **WARN** | Hỗ trợ | Hỗ trợ | Ghi cảnh báo và tiếp tục xử lý |
| **CONTINUE** | **Không hỗ trợ** | Hỗ trợ | Bỏ qua changeset hiện tại trong lần chạy này |
| **MARK_RAN** | **Không hỗ trợ** | Hỗ trợ | Ghi nhận changeset như đã chạy mà không thi hành các change bên trong |

Quy tắc phạm vi này rất quan trọng cho cả onFail và cách chọn chính sách đối với kết quả precondition. Không sao chép một đoạn cấu hình local sang global mà giữ nguyên CONTINUE hoặc MARK_RAN.

### Ví dụ precondition toàn cục

~~~yaml
databaseChangeLog:
  - preConditions:
      - onFail: HALT
      - onError: HALT
      - dbms:
          type: postgresql

  - changeSet:
      id: 2026-11-19-002
      author: database-team
      changes:
        - createTable:
            tableName: customer_category
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Changelog này yêu cầu PostgreSQL. Nếu kết nối không phải PostgreSQL, **HALT** ngăn các thay đổi được xử lý tiếp trong lần chạy đó. Đặt global onFail: MARK_RAN để “coi tất cả changeset đã chạy” là sai phạm vi hỗ trợ.

### Ví dụ precondition cục bộ

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-003
      author: database-team
      preConditions:
        - onFail: CONTINUE
        - onError: HALT
        - tableExists:
            tableName: optional_feature
      changes:
        - createIndex:
            tableName: optional_feature
            indexName: idx_optional_feature_name
            columns:
              - column:
                  name: name
~~~

Nếu optional_feature chưa tồn tại, changeset này được **bỏ qua trong lần update hiện tại** và vẫn có thể được cân nhắc ở lần update sau. Đây chỉ là lựa chọn đúng khi index thực sự là thay đổi tùy chọn, và những changeset sau không mặc định index đã được tạo.

## 5. HALT: dừng khi điều kiện bắt buộc không đạt

**HALT** là lựa chọn bảo thủ khi tính đúng đắn của migration phụ thuộc vào precondition. Liquibase dừng xử lý thay vì tiếp tục với một trạng thái database không đáp ứng yêu cầu.

Điều đó không có nghĩa Liquibase tự động rollback **các changeset đã commit trước đó** trong cùng một changelog hoặc release. HALT ngăn bước tiếp theo, không biến toàn bộ quá trình triển khai thành một transaction nguyên tử.

**Nên chọn HALT khi:**

- Thiếu bảng hoặc cột làm tiền đề cho DDL tiếp theo.
- Schema không đúng phiên bản hoặc trạng thái dữ liệu không phù hợp để backfill.
- Phát hiện đối tượng có tên trùng nhưng chưa xác định được cấu trúc.
- Thao tác có nguy cơ mất dữ liệu nếu tiếp tục.
- Kết quả kiểm tra mâu thuẫn với giả định được yêu cầu ở production.
- Phép kiểm tra bị lỗi và không thể chứng minh thao tác an toàn.

Ví dụ thêm cột archived_at nhưng chỉ khi bảng có sẵn và cột chưa tồn tại:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-004
      author: database-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - onFailMessage: "Cấu trúc customer không đúng trạng thái mong đợi"
        - tableExists:
            tableName: customer
        - not:
            - columnExists:
                tableName: customer
                columnName: archived_at
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: archived_at
                  type: TIMESTAMP
      rollback:
        - dropColumn:
            tableName: customer
            columnName: archived_at
~~~

Trong danh sách preConditions, các phép kiểm tra được kết hợp theo logic tương ứng của Liquibase; ở ví dụ này điều kiện tồn tại bảng và chưa tồn tại cột đều cần đạt. Nếu cột đã có sẵn, HALT để người triển khai kiểm tra xem cột đó do migration nào tạo và có đúng kiểu dữ liệu hay không.

**Ưu điểm:** phát hiện sai lệch sớm, giữ nguyên bằng chứng lỗi, tránh bỏ qua một bước bắt buộc. **Chi phí:** pipeline sẽ dừng và cần can thiệp khi môi trường khác trạng thái mong đợi. Đây thường là chi phí chấp nhận được cho thay đổi quan trọng.

## 6. WARN: cảnh báo nhưng tiếp tục

**WARN** ghi nhận việc điều kiện không đạt như một cảnh báo và cho phép quá trình tiếp tục. Ở changeset-level, các change trong changeset vẫn có thể được thực hiện; WARN **không phải** cơ chế bỏ qua changeset.

Chọn WARN khi precondition mang tính **khuyến nghị, quan sát hoặc chẩn đoán**, và việc không đạt điều kiện không phá vỡ tính đúng đắn của thay đổi tiếp theo.

Ví dụ: nhóm muốn biết có dữ liệu thiếu nhãn trước khi tạo index không unique trên cột nhãn, nhưng việc thiếu nhãn **không làm cho index sai**:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-005
      author: database-team
      preConditions:
        - onFail: WARN
        - onError: HALT
        - onFailMessage: "Có dòng chưa có nhãn; vẫn tạo index không unique"
        - sqlCheck:
            expectedResult: "0"
            sql: "SELECT COUNT(*) FROM customer WHERE segment IS NULL"
      changes:
        - createIndex:
            tableName: customer
            indexName: idx_customer_segment
            columns:
              - column:
                  name: segment
~~~

Ví dụ trên chỉ hợp lệ khi bảng customer đã tồn tại, câu SQL chạy được và index mong muốn cho phép các giá trị null theo DBMS đang dùng. Cần kiểm tra giả định đó riêng. WARN trong tình huống này nhằm đưa tín hiệu chất lượng dữ liệu vào log; bước tạo index vẫn được phép chạy.

**Không dùng WARN khi:**

- Câu lệnh kế tiếp chắc chắn lỗi nếu điều kiện không đạt.
- Việc tiếp tục có thể xóa dữ liệu sai hoặc bỏ qua vấn đề schema drift.
- Cần bảo đảm đối tượng đã tồn tại với cấu trúc chính xác.
- Pipeline production cần dừng để điều tra.
- Nhóm mong muốn “không chạy changeset” khi điều kiện thất bại. Trường hợp đó phải đánh giá CONTINUE hoặc MARK_RAN tùy ngữ nghĩa và phạm vi.

Một cảnh báo không được giám sát chỉ là văn bản trong log. Nếu chọn WARN vì quy trình có người theo dõi, CI/CD cần thu thập và phân loại cảnh báo để tránh trở thành cảnh báo không ai xử lý.

## 7. CONTINUE: bỏ qua changeset ở lần chạy hiện tại

**CONTINUE** chỉ dùng với precondition nằm trong changeset. Khi điều kiện không đạt, Liquibase **không thực hiện các change trong changeset này**, tiếp tục xem xét các changeset tiếp theo, và **không ghi nó như đã chạy thành công**. Vì vậy, changeset có thể được đánh giá lại trong một lần chạy Liquibase sau khi điều kiện đã đạt.

Đây là khác biệt căn bản so với MARK_RAN: **CONTINUE vẫn giữ “món nợ migration”**.

### Khi nào CONTINUE có ý nghĩa?

- Changeset thật sự là tùy chọn trong môi trường nhất định.
- Điều kiện để chạy có thể xuất hiện ở một lần triển khai sau.
- Các changeset phía sau không phụ thuộc vào kết quả của changeset đang bị bỏ qua.
- Việc trì hoãn không làm sai mục tiêu release hoặc phá vỡ tương thích ứng dụng.
- Nhóm có cách quan sát danh sách changeset còn chờ.

Một trường hợp có thể chấp nhận là tối ưu hóa index cho một bảng thuộc tính năng tùy chọn đã được triển khai riêng. Nếu bảng chưa tồn tại, index chưa cần tạo. Khi bảng xuất hiện ở lần triển khai tiếp theo, cùng changeset có thể được xét lại.

### Khi nào CONTINUE nguy hiểm?

Giả sử changeset A thêm cột order_status, còn changeset B cập nhật dữ liệu vào cột đó. Nếu A dùng CONTINUE và bị bỏ qua, Liquibase vẫn có thể tiếp tục đến B; B sẽ lỗi hoặc tạo hành vi không mong đợi. CONTINUE **không bảo đảm các dependency phía sau được tự động bỏ qua**.

Một lỗi khác: pipeline báo các changeset tiếp theo chạy xong, nhưng còn một changeset quan trọng vẫn pending. Nếu chỉ nhìn exit code hoặc dòng cuối log, người vận hành có thể hiểu nhầm phát hành đã hoàn tất.

### Quy trình với CONTINUE

1. Ghi rõ vì sao thay đổi được phép trì hoãn.
2. Xác định tập môi trường mà điều kiện có thể không đạt.
3. Kiểm tra dependency của những changeset phía sau.
4. Quan sát pending changesets bằng status/history và kiểm tra schema thực tế.
5. Đặt điều kiện nghiệm thu release phù hợp; nếu changeset bắt buộc cuối cùng vẫn pending thì không được coi release đã đầy đủ.
6. Thử chạy lại sau khi điều kiện được đáp ứng và xác minh thay đổi thực sự được áp dụng.

## 8. MARK_RAN: ghi nhận đã chạy mà không thi hành SQL

**MARK_RAN** cũng chỉ hỗ trợ ở changeset-level. Khi precondition không đạt, Liquibase **bỏ qua các change trong changeset nhưng ghi nhận changeset như đã chạy**. Thông tin lịch sử thường thể hiện loại thực thi **MARK_RAN** trong DATABASECHANGELOG.

MARK_RAN có vẻ tiện để tránh lỗi “bảng đã tồn tại” hoặc “cột đã tồn tại”, nhưng là lựa chọn rất dễ che giấu sai lệch. **“Đối tượng tồn tại” không đồng nghĩa “đối tượng đúng như changeset sẽ tạo ra”.**

### Tình huống có thể dùng có kiểm soát

Một hệ thống legacy đã có cột email_verified được tạo thủ công từ trước. Nhóm muốn đưa lịch sử schema về quản lý Liquibase. Nếu đã xác minh bằng công cụ và truy vấn metadata rằng cột đó **hoàn toàn tương đương** với thay đổi mà changeset dự kiến áp dụng, có thể dùng một local precondition để tránh tạo cột lần thứ hai và ghi nhận trạng thái đã có.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-006
      author: database-team
      comment: Đồng bộ lịch sử cột đã được xác minh ở hệ thống legacy
      preConditions:
        - onFail: MARK_RAN
        - onError: HALT
        - not:
            - columnExists:
                tableName: customer
                columnName: email_verified
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: email_verified
                  type: BOOLEAN
      rollback:
        - dropColumn:
            tableName: customer
            columnName: email_verified
~~~

**Cảnh báo bắt buộc khi dùng ví dụ:** chỉ kiểm tra columnExists là **chưa đủ** để xác minh cột legacy tương đương. Trước khi cho phép MARK_RAN, nhóm phải kiểm tra **bảng đúng schema, kiểu cột, nullability, default, dữ liệu hiện có và constraint liên quan**. Ngoài ra, nếu bảng customer không tồn tại, điều kiện not columnExists cũng có thể dẫn đến nhánh MARK_RAN dù không có đối tượng mong muốn; vì vậy cần một bước kiểm chứng nền tảng với HALT riêng hoặc một quy trình kiểm tra trước triển khai.

Ví dụ trên minh họa cú pháp và ý nghĩa, **không nên dùng nguyên trạng trong production** mà không có các kiểm tra tương đương nêu trên.

### Vì sao MARK_RAN khác CONTINUE?

| Điểm so sánh | CONTINUE | MARK_RAN |
|---|---|---|
| SQL của changeset có chạy khi điều kiện thất bại? | Không | Không |
| Lịch sử được đánh dấu như đã chạy? | Không | Có |
| Có thể tự được xét lại ở lần update sau? | Có, nếu còn pending và được chọn | Thông thường không được xem là thay đổi chưa chạy nữa |
| Dùng để làm gì? | Hoãn một thay đổi tùy chọn | Ghi nhận một thay đổi đã hiện diện tương đương mà không lặp SQL |
| Rủi ro lớn nhất | Migration cần thiết vẫn pending | Che giấu thiếu hoặc sai schema/data bằng lịch sử “đã chạy” |

MARK_RAN là **quyết định quản trị lịch sử**, không phải một cách thay thế cho kiểm chứng schema hoặc cơ chế tự động “idempotent” mọi migration.

### Tác động đến rollback

Một changeset MARK_RAN có bản ghi lịch sử nhưng SQL ban đầu không được thực hiện bởi Liquibase. Không được mặc định rằng rollback của changeset đó là vô hại. Nếu rollback chứa dropColumn hoặc dropTable, việc gọi rollback mà không kiểm tra hiện trạng có thể xóa **đối tượng legacy do hệ thống khác tạo trước đó**. Cần review chính xác kế hoạch rollback trên môi trường có MARK_RAN và quyết định quyền sở hữu đối tượng trước khi chạy.

## 9. Bảng quyết định chọn hành vi

Để ra quyết định, bắt đầu bằng việc phân loại **precondition có bắt buộc với tính đúng đắn của migration không?**

| Tình huống | onFail được cân nhắc | Lý do |
|---|---|---|
| Thiếu bảng/cột tiền đề cho thay đổi quan trọng | **HALT** | Dừng để tránh lỗi dây chuyền hoặc thay đổi sai |
| Phát hiện dữ liệu không đủ điều kiện để xóa/chuyển đổi | **HALT** | Không bỏ qua kiểm tra an toàn |
| Kiểm tra chất lượng dữ liệu chỉ để quan sát, thay đổi vẫn hợp lệ | **WARN** | Cho phép chạy và ghi cảnh báo |
| Tính năng tùy chọn chưa tồn tại, thay đổi có thể chờ | **CONTINUE** | Giữ changeset pending để xử lý sau |
| Đối tượng đã hiện diện và **được chứng minh tương đương** | **MARK_RAN** | Tránh thực thi lặp, ghi nhận lịch sử có chủ đích |
| Trùng tên đối tượng nhưng không rõ định nghĩa thực tế | **HALT** | Không đủ chứng cứ để MARK_RAN |
| Lỗi truy vấn kiểm tra hoặc thiếu quyền metadata | **onError: HALT** | Lỗi kiểm tra không chứng minh điều kiện đã đạt |
| Changelog phải chạy đúng DBMS | **Global HALT** | Điều kiện cấp changelog, không dùng CONTINUE/MARK_RAN |
| Changelog có cảnh báo môi trường chỉ mang tính thông tin | **Global WARN** | Không ảnh hưởng tính đúng của các thay đổi |

Một mẹo kiểm tra ý định:

- **Không đạt thì phải dừng để sửa?** Chọn HALT.
- **Không đạt nhưng SQL vẫn an toàn và cần chạy?** Có thể chọn WARN.
- **Không đạt thì chưa chạy, có thể xét lại lần sau?** Có thể chọn CONTINUE tại changeset.
- **Không đạt vì kết quả thay đổi đã có sẵn và được xác minh đúng, muốn ghi nhận lịch sử?** Có thể chọn MARK_RAN tại changeset.

Nếu không giải thích được vì sao tiếp tục hoặc đánh dấu đã chạy là an toàn, hãy chọn **HALT** và điều tra.

## 10. onFail và onError nên cấu hình cùng nhau như thế nào?

Cùng một precondition có thể không đạt theo hai cách khác nhau, nên cần xem xét đồng thời cả **onFail** và **onError**.

Ví dụ cho một thay đổi tùy chọn:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-007
      author: database-team
      preConditions:
        - onFail: CONTINUE
        - onError: HALT
        - tableExists:
            tableName: optional_feature
      changes:
        - addColumn:
            tableName: optional_feature
            columns:
              - column:
                  name: last_updated
                  type: TIMESTAMP
~~~

**Không có bảng** là trạng thái được dự kiến: bỏ qua tạm thời bằng CONTINUE. **Không thể kiểm tra bảng** là lỗi hạ tầng hoặc metadata: dừng bằng HALT. Gán onError: CONTINUE cho mọi lỗi có thể khiến một sự cố kết nối bị hiểu như điều kiện tùy chọn chưa đạt.

Tương tự với MARK_RAN: nếu precondition gặp exception, không có cơ sở nào để kết luận đối tượng đã tồn tại tương đương. Giữ **onError: HALT** là cách tránh đánh dấu sai lịch sử.

### Thông điệp tùy chỉnh

Liquibase hỗ trợ các thuộc tính thông điệp cho precondition như **onFailMessage** và **onErrorMessage** trong những định dạng hỗ trợ. Nên viết thông điệp giải thích:

- Trạng thái mong đợi.
- Thay đổi bị ảnh hưởng.
- Cách xác minh thực tế.
- Khi nào được phép chạy lại.

Không đưa mật khẩu, chuỗi kết nối chứa secret hoặc dữ liệu nhạy cảm vào thông điệp sẽ được ghi ở log.

## 11. Logic AND, OR, NOT và điều kiện phức hợp

Phạm vi hỗ trợ của HALT/WARN/CONTINUE/MARK_RAN vẫn tuân theo nơi đặt **preConditions**, bất kể logic bên trong có nhiều điều kiện hay không.

Các toán tử logic thường dùng:

- **and**: tất cả điều kiện con phải đạt.
- **or**: ít nhất một điều kiện con phải đạt.
- **not**: phủ định kết quả điều kiện con.

Ví dụ: chỉ thêm cột khi bảng có sẵn **và** cột chưa tồn tại:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-008
      author: database-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - and:
            - tableExists:
                tableName: customer
            - not:
                - columnExists:
                    tableName: customer
                    columnName: migrated_at
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: migrated_at
                  type: TIMESTAMP
~~~

Cẩn thận khi dùng **or** với MARK_RAN. Nếu điều kiện tổng thất bại, cần hiểu chính xác **tất cả nguyên nhân thất bại** có cho phép đánh dấu đã chạy không. Một nhánh thất bại do thiếu bảng và một nhánh thất bại do đã có cột là hai trạng thái khác nhau, không nên gom vào cùng một lựa chọn MARK_RAN nếu chưa có xác minh độc lập.

Về tối ưu, một số phép kiểm tra có thể tốn chi phí khi truy vấn metadata hoặc dữ liệu lớn. Nên chọn những điều kiện rẻ, rõ và đủ mạnh; với SQL kiểm tra số lượng lớn, cân nhắc index, thời gian chạy và ảnh hưởng database. Không sử dụng precondition như một công cụ kiểm toán dữ liệu tốn hàng giờ trong mỗi lần startup nếu có cách kiểm tra phù hợp hơn.

## 12. Phân biệt điều kiện sai và lỗi thực thi changeset

**onFail/onError thuộc về precondition.** Khi Liquibase đã vượt qua precondition và đang thực hiện DDL/DML, một lệnh SQL có thể thất bại vì constraint, deadlock, lock timeout hoặc lỗi cú pháp. Những lỗi thực thi đó **không được “chuyển thành WARN/CONTINUE/MARK_RAN” đơn giản bằng cách cấu hình onFail**.

Ví dụ: precondition tableExists đạt, nhưng lệnh thêm unique constraint thất bại do có dữ liệu trùng. Đây là lỗi của thao tác thay đổi, không phải kết quả thất bại của tableExists.

Nếu muốn kiểm tra dữ liệu trùng trước khi thêm constraint, có thể tạo một sqlCheck thích hợp với **onFail: HALT**. Nhưng vẫn phải hiểu có race condition: dữ liệu có thể thay đổi giữa kiểm tra và lúc DDL thực hiện. SQL/transaction và quy trình phối hợp triển khai phải xử lý rủi ro đó.

Cũng cần nhớ:

- HALT không tự rollback toàn bộ changeset đã commit trước đó.
- runInTransaction và khả năng hỗ trợ DDL transaction của DBMS mới quyết định mức độ có thể hoàn tác khi SQL lỗi.
- MARK_RAN không chứng minh SQL đã được thực thi và rollback không tự khôi phục dữ liệu lịch sử.

## 13. DATABASECHANGELOG, checksum và lịch sử khi precondition không đạt

Bảng **DATABASECHANGELOG** là nguồn quan trọng để hiểu Liquibase đã ghi nhận changeset như thế nào. Các trạng thái cần phân biệt:

| Tình huống | Thao tác với change | Kỳ vọng về lịch sử |
|---|---|---|
| Điều kiện đạt và changeset chạy thành công | Thực hiện SQL/DDL/DML | Ghi nhận như đã thực thi, thường EXECUTED |
| HALT vì precondition không đạt | Dừng trước khi thi hành change của changeset đó | Không ghi nhận changeset chưa chạy là EXECUTED |
| WARN vì precondition không đạt, SQL tiếp tục chạy thành công | Vẫn thực hiện change | Ghi nhận theo kết quả thực thi thực tế |
| CONTINUE vì precondition không đạt | Bỏ qua change trong lần này | Không ghi nhận changeset đã hoàn tất; có thể còn pending |
| MARK_RAN vì precondition không đạt | Không thực hiện change | Ghi nhận changeset với loại MARK_RAN |
| Error trong precondition và onError: HALT | Dừng để điều tra | Không được giả định change đã chạy |

Các cơ chế runAlways, runOnChange và chính sách xử lý đặc biệt có thể ảnh hưởng luồng đánh giá và lịch sử ở những lần chạy khác; cần kiểm thử nếu dự án sử dụng chúng.

**Checksum** giúp Liquibase xác thực một số thay đổi ở nội dung changeset đã được ghi nhận. Nó **không** bảo đảm rằng một đối tượng được MARK_RAN thực sự có đúng schema mong muốn. Đừng dùng clear-checksums hay sửa tay DATABASECHANGELOG để che giấu migration thiếu hoặc sai.

Khi gặp một row MARK_RAN, câu hỏi đầu tiên không phải “SQL đã chạy chưa?” mà là “**bằng chứng nào cho phép coi trạng thái database tương đương với kết quả mong đợi?**”.

## 14. Trường hợp đa môi trường: DEV, STAGING và PRODUCTION

Cùng một changelog có thể gặp trạng thái schema khác nhau giữa môi trường.

Ví dụ:

- **DEV mới**: bảng customer chưa tồn tại.
- **STAGING**: bảng đã có cột email_verified đúng định nghĩa.
- **PRODUCTION legacy**: có cột email_verified nhưng kiểu hoặc default khác.

Nếu precondition chỉ kiểm tra columnExists và dùng MARK_RAN, STAGING và PRODUCTION có thể cùng bị đánh dấu hoàn tất mặc dù PRODUCTION **không tương đương**. Đây là drift bị che giấu trong lịch sử.

Quy trình đáng tin cậy:

1. Xác định điều kiện được xem là tương đương: kiểu dữ liệu, khả năng null, default, index, constraint, dữ liệu và tên schema.
2. Kiểm tra từng môi trường; ghi nhận kết quả quan sát được.
3. Nếu trạng thái không tương đương, dùng HALT và tạo changeset sửa sai theo kế hoạch.
4. Chỉ cân nhắc MARK_RAN khi đã có bằng chứng tương đương và được review.
5. Nếu một thay đổi thật sự tùy chọn theo môi trường, ưu tiên xem xét **context/label/dbms filter** hoặc phân tách changeset phù hợp, thay vì lạm dụng CONTINUE ở mọi môi trường.
6. Lưu quyết định cùng log triển khai để những lần kiểm toán sau biết tại sao một changeset mang EXECUTED hay MARK_RAN.

**Context/label** dùng để chọn changeset theo mục đích triển khai. **Precondition** dùng để kiểm tra trạng thái hệ thống trước khi thực hiện thay đổi. Hai cơ chế bổ sung cho nhau nhưng không tương đương.

## 15. Ví dụ tình huống có đầy đủ quyết định

Một ứng dụng triển khai thay đổi sang bảng purchase_order:

- Bảng purchase_order phải tồn tại trước khi thêm constraint.
- Có thể tạo index tối ưu tìm kiếm cho bảng analytics_optional nếu bảng đã có.
- Nhóm muốn cảnh báo nếu order_ref bị null, nhưng việc tạo một index thông thường trên trường khác vẫn hợp lệ.
- Một cột mới đã được một bản release legacy tạo thủ công ở một môi trường, cần đồng bộ quản trị lịch sử.

Chính sách có thể là:

| Bước | Tính chất | Xử lý |
|---|---|---|
| Kiểm tra bảng purchase_order | Bắt buộc | Local **HALT** |
| Kiểm tra chất lượng order_ref trước một index không phụ thuộc null | Thông tin/cảnh báo | Local **WARN**, onError: HALT |
| Index cho analytics_optional | Tùy chọn và độc lập | Local **CONTINUE**, onError: HALT |
| Cột đã tồn tại từ legacy | Có thể tương đương nhưng cần chứng minh | **HALT** để kiểm chứng; chỉ sau đó mới xét **MARK_RAN** |

Trong CI/CD, không đủ chỉ kiểm tra update có exit code 0. Cần xác nhận:

- Những changeset bắt buộc đã thực thi.
- Những changeset CONTINUE còn pending có được phép trì hoãn hay không.
- Những changeset MARK_RAN có biên bản xác nhận tương đương hay không.
- Các WARN đã được thu thập và gửi đúng người phụ trách.
- Không có lỗi đánh giá precondition bị phân loại nhầm thành điều kiện không đạt.
- Schema và dữ liệu sau triển khai đáp ứng tiêu chí nghiệm thu.

## 16. Kiểm chứng qua CLI và pipeline

Một trình tự kiểm tra điển hình khi đã cấu hình kết nối và changelog gốc:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
liquibase update
liquibase history
~~~

Ý nghĩa:

- **validate** kiểm tra changelog và những lỗi được Liquibase hỗ trợ phát hiện trước khi chạy.
- **status --verbose** giúp quan sát changeset còn chờ.
- **update-sql** cung cấp SQL dự kiến để review. Precondition có thể có hành vi riêng khi tạo SQL khô tùy bản Liquibase và cấu hình, do đó kết quả này không thay thế một lần kiểm thử trên database.
- **update** thực thi các thay đổi chưa hoàn tất theo lịch sử và bộ lọc đang có.
- **history** hỗ trợ xem lịch sử triển khai.

Trước production, nên kiểm tra trên **database mới** và **bản sao database đã có lịch sử**. Một changeset có CONTINUE có thể không chạy trong lần đầu vì điều kiện chưa đạt nhưng lại chạy ở lần sau; phải kiểm thử cả quá trình này nếu đó là hành vi mong muốn.

Đối với MARK_RAN, kiểm tra cả **DATABASECHANGELOG** và **schema thực tế**. Bản ghi MARK_RAN không thay thế được việc xác nhận bảng/cột/index đúng cấu trúc.

### Mẫu checklist review precondition

- [ ] Precondition đang ở đúng phạm vi changelog hay changeset.
- [ ] Giá trị onFail thuộc tập được hỗ trợ ở phạm vi đó.
- [ ] onError được xem xét riêng và không che giấu lỗi hạ tầng.
- [ ] Điều kiện thật sự chứng minh những gì changeset cần, không chỉ kiểm tra tên đối tượng.
- [ ] HALT dùng cho thay đổi bắt buộc hoặc có nguy cơ dữ liệu.
- [ ] WARN chỉ dùng khi việc tiếp tục vẫn an toàn.
- [ ] CONTINUE chỉ dùng với changeset trì hoãn được và không phá dependency.
- [ ] MARK_RAN chỉ được dùng khi có bằng chứng tương đương và rollback được review.
- [ ] Kỳ vọng về DATABASECHANGELOG và pending changesets đã được ghi rõ.
- [ ] Đã thử validate, status, update-sql, update và kiểm tra sau triển khai.
- [ ] Có hướng xử lý khi schema drift hoặc lỗi kiểm tra xuất hiện trên production.

## 17. Bài tập và câu hỏi tự kiểm tra

### Bài tập 1: chọn hành vi phù hợp

Một changeset muốn thêm khóa ngoại orders.customer_id tham chiếu customer.id. Trước khi chạy, precondition phát hiện bảng customer không tồn tại.

**Lựa chọn nên dùng:** HALT. Thiếu bảng cha là vi phạm điều kiện bắt buộc; WARN có thể dẫn đến lỗi DDL, CONTINUE có thể để release thiếu constraint, MARK_RAN gây lịch sử sai.

### Bài tập 2: có nên dùng WARN?

Một changeset chỉ tạo index không unique trên cột segment. Precondition dùng sqlCheck kiểm tra có bao nhiêu dòng segment null, nhưng index vẫn hợp lệ nếu có null.

**Lựa chọn có thể chấp nhận:** WARN nếu nhóm cố ý chỉ muốn chẩn đoán và có cơ chế xem cảnh báo. Nếu null thực sự là lỗi nghiệp vụ hoặc index yêu cầu dữ liệu không null, HALT mới phù hợp.

### Bài tập 3: CONTINUE hay MARK_RAN?

Một tính năng tùy chọn chưa triển khai bảng của nó ở môi trường hiện tại. Changeset tạo index cho bảng này là tùy chọn và cần được chạy khi tính năng được bật sau.

**Lựa chọn phù hợp:** CONTINUE tại changeset-level. Nếu dùng MARK_RAN, lần sau có bảng Liquibase có thể coi changeset đã hoàn tất và không tự tạo index.

### Bài tập 4: legacy có cột cùng tên

Production đã có customer.email_verified được tạo thủ công. Precondition chỉ dùng columnExists cho biết cột tồn tại. Nhóm muốn MARK_RAN.

**Chưa đủ căn cứ.** Cần kiểm tra kiểu cột, nullability, default, dữ liệu, constraint và lịch sử nguồn gốc. Nếu khác định nghĩa, HALT rồi dùng migration mới để xử lý. Nếu đã được xác nhận tương đương, mới cân nhắc MARK_RAN theo quy trình được duyệt.

### Bài tập 5: precondition gặp lỗi SQL

sqlCheck viết sai tên schema nên truy vấn trả lỗi, không trả được kết quả false/true. Người viết cấu hình onFail: CONTINUE và kỳ vọng changeset được bỏ qua.

**Phân tích:** Đây là nhánh **onError**, không phải onFail. Đối với lỗi kiểm tra, cách an toàn thường là onError: HALT để sửa SQL và đánh giá lại.

### Bài tập 6: global precondition

Changelog yêu cầu PostgreSQL; người viết muốn onFail: MARK_RAN ở đầu file để đánh dấu bỏ qua toàn bộ changeset trên MySQL.

**Phân tích:** MARK_RAN không được hỗ trợ ở global preconditions. Nên dùng global HALT nếu toàn bộ changelog chỉ hỗ trợ PostgreSQL, hoặc dùng dbms filter và tổ chức changeset phù hợp nếu dự án thật sự hỗ trợ nhiều hệ quản trị.

## 18. Ghi nhớ

Bốn lựa chọn đều trả lời câu hỏi “Liquibase làm gì nếu precondition không đạt?”, nhưng chúng **không thể dùng thay thế cho nhau**:

1. **HALT:** dừng để bảo toàn tính đúng khi điều kiện bắt buộc không đạt.
2. **WARN:** cảnh báo nhưng tiếp tục; các change vẫn có thể được thi hành.
3. **CONTINUE:** bỏ qua changeset trong lần này, giữ khả năng xét lại ở lần sau.
4. **MARK_RAN:** không thi hành change nhưng đánh dấu changeset đã chạy; chỉ dùng sau khi xác minh kết quả đã tồn tại tương đương.

**HALT và WARN** dùng được ở cấp changelog và changeset; **CONTINUE và MARK_RAN** chỉ dành cho precondition trong changeset. Đồng thời, **onFail** xử lý điều kiện trả false, còn **onError** xử lý lỗi đánh giá điều kiện.

Trong hệ thống có lịch sử triển khai và nhiều môi trường, ưu tiên khả năng kiểm chứng hơn việc làm pipeline chạy qua mọi giá. Hãy thiết kế precondition đủ chính xác, chọn hành vi đúng phạm vi, kiểm tra DATABASECHANGELOG và schema thực tế, đồng thời có phương án rollback hoặc forward fix trước khi triển khai thay đổi quan trọng.
