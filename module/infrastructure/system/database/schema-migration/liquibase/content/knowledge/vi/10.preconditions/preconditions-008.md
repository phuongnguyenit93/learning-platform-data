
# Hệ quả của MARK_RAN đối với lịch sử và việc chạy lại

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase quản lý sự tiến hóa của schema và dữ liệu qua changelog, changeset, precondition, checksum và lịch sử triển khai. Precondition cho phép kiểm tra trạng thái cơ sở dữ liệu trước khi thực hiện thay đổi. Nếu một precondition không đạt, cấu hình **onFail: MARK_RAN** có thể khiến Liquibase **ghi nhận changeset như đã xử lý nhưng không chạy các thay đổi thuộc changeset đó**.

Đây là một cơ chế hữu ích khi đưa một database cũ vào quản lý bằng Liquibase hoặc khi một đối tượng đã tồn tại hợp lệ từ trước. Nhưng MARK_RAN cũng dễ che giấu thiếu sót: migration chưa tạo bảng/cột, trong khi lịch sử lại thể hiện changeset không còn pending. Ở các lần `update` thông thường sau đó, Liquibase dựa vào lịch sử để quyết định có cần chạy changeset hay không. Vì vậy, hiểu rõ **hệ quả đối với DATABASECHANGELOG, trạng thái thực tế và cơ chế chạy lại** là yêu cầu quan trọng trước khi dùng MARK_RAN.

Bài thuộc chương **Tiền điều kiện** này tập trung vào những câu hỏi: MARK_RAN xuất hiện khi nào; nó ghi gì vào lịch sử; vì sao changeset thường không được thử lại ở lần update kế tiếp; checksum, runOnChange/runAlways và rollback có liên quan gì; và làm thế nào kiểm chứng kết quả an toàn trên development, staging, production hoặc trong Spring Boot và CI/CD.

## 1. MARK_RAN là gì?

**MARK_RAN** là một lựa chọn xử lý **precondition không đạt** ở phạm vi changeset. Khi một changeset chưa được ghi nhận chạy, Liquibase đánh giá các điều kiện đủ để quyết định có được thực thi hay không. Nếu precondition cho kết quả **không đạt** và changeset khai báo `onFail: MARK_RAN`, Liquibase có thể **bỏ qua phần changes của changeset đó nhưng tạo bản ghi lịch sử với kiểu thực thi MARK_RAN**.

Nói ngắn gọn:

> MARK_RAN có nghĩa là “đánh dấu changeset là đã được xử lý trong lịch sử”, **không phải** “Liquibase đã thực hiện xong DDL/DML bên trong changeset”.

Cần tách ba sự kiện:

| Sự kiện | Ý nghĩa |
|---|---|
| Changeset được đọc từ changelog | Liquibase nhận diện id, author, đường dẫn và cấu hình |
| Precondition không đạt và onFail=MARK_RAN | Liquibase quyết định không thực hiện phần changes, nhưng ghi nhận changeset theo cơ chế MARK_RAN |
| Changeset được thực thi bình thường | Liquibase thực hiện thay đổi rồi ghi nhận kiểu thực thi tương ứng, thường là EXECUTED |

Sau khi có bản ghi MARK_RAN, bảng lịch sử có thể cho người kiểm tra biết rằng changeset đó **không được thực thi theo đường bình thường**. Tuy nhiên, nhiều lệnh chỉ hỏi còn changeset nào **pending** sẽ không cho thấy vấn đề, vì changeset đã có lịch sử.

## 2. Vì sao nhóm phát triển muốn dùng MARK_RAN?

Một số hoàn cảnh thực tế:

1. **Đưa cơ sở dữ liệu cũ vào Liquibase:** một bảng đã được tạo thủ công trước khi có changelog; nhóm muốn ghi nhận changeset mô tả bảng đó mà không tạo bảng lần nữa.
2. **Đồng bộ một nhóm môi trường có lịch sử khởi tạo khác nhau:** database A được tạo bằng Liquibase, database B đã có sẵn một phần schema tương đương.
3. **Phát hành chuyển tiếp có điều kiện:** một thay đổi đã được áp dụng bằng cơ chế khác và nhóm muốn bảo đảm Liquibase không cố thực hiện lại nó.
4. **Xử lý migration tương thích ngược:** một đối tượng đã tồn tại phù hợp nên bước tạo đối tượng đó có thể được xem là đã hoàn thành, với điều kiện phải xác minh cấu trúc thực.

Đây đều là bài toán **đối chiếu trạng thái trước khi ghi nhận lịch sử**. Nếu một bảng có cùng tên nhưng thiếu cột, sai kiểu dữ liệu hoặc khác constraint, việc đánh dấu MARK_RAN có thể khiến database tiếp tục lệch schema.

Do đó, chỉ nên sử dụng MARK_RAN khi nhóm có một **invariant** hoặc tiêu chí kiểm chứng đủ mạnh để khẳng định rằng bỏ qua thao tác sẽ không làm mất yêu cầu kỹ thuật của release.

## 3. Precondition thất bại khác lỗi đánh giá precondition

Hai đường xử lý cần được phân biệt:

- **onFail:** áp dụng khi precondition được đánh giá thành công nhưng cho kết quả **false/không đạt**. Ví dụ yêu cầu một bảng chưa tồn tại, nhưng bảng đó đã tồn tại.
- **onError:** áp dụng khi việc đánh giá precondition **phát sinh lỗi**. Ví dụ không thể đọc metadata, lệnh SQL kiểm tra bị lỗi cú pháp hoặc tài khoản không có quyền cần thiết.

Một khai báo minh họa:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: schema-team
      preConditions:
        - onFail: MARK_RAN
        - onError: HALT
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
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Ý nghĩa của đoạn này:

- Bảng customer **chưa tồn tại**: `tableExists` trả true/false theo thực tế; toán tử `not` làm điều kiện tổng thể đạt khi bảng **không** tồn tại. Khi đó Liquibase thực hiện `createTable`.
- Bảng customer **đã tồn tại**: `not tableExists` không đạt; `onFail: MARK_RAN` bỏ qua `createTable` và ghi nhận MARK_RAN.
- Liquibase **không thể đánh giá** điều kiện: `onError: HALT` yêu cầu dừng, thay vì coi lỗi kiểm tra là lý do hợp lệ để đánh dấu đã xử lý.

Sự khác biệt giữa fail và error quan trọng cho vận hành: **không xác minh được trạng thái** không đồng nghĩa **đã xác minh trạng thái an toàn để bỏ qua thay đổi**.

## 4. Phạm vi hợp lệ của MARK_RAN

Một precondition có thể được đặt ở nhiều phạm vi, đặc biệt là **changelog-level** hoặc **changeset-level**. Các lựa chọn `MARK_RAN` và `CONTINUE` được dùng cho precondition ở **phạm vi changeset**; với precondition cấp changelog, không thể tùy tiện dùng MARK_RAN như cách ghi nhận toàn bộ tệp đã chạy.

Ví dụ đặt trong changeset:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-create-customer-index
      author: schema-team
      preConditions:
        - onFail: MARK_RAN
        - not:
            - indexExists:
                indexName: idx_customer_email
                tableName: customer
      changes:
        - createIndex:
            indexName: idx_customer_email
            tableName: customer
            columns:
              - column:
                  name: email
~~~

Cách hiểu: nếu index đã tồn tại theo điều kiện được kiểm tra, bỏ qua việc tạo và đánh dấu changeset đã xử lý. Nhưng **chỉ kiểm tra tên index vẫn chưa đủ** để khẳng định index có đúng cột, thứ tự cột, tính unique hoặc các tùy chọn DBMS. Với đối tượng quan trọng, cần kiểm tra thêm cấu trúc mong đợi hoặc có bước xác nhận riêng.

Khi một nhóm thay đổi lớn có nhiều điều kiện và thao tác, cân nhắc tách thành các changeset nhỏ. Nếu đánh dấu MARK_RAN cho một changeset chứa ba thao tác, **cả ba thao tác đều bị bỏ qua**, kể cả khi điều kiện chỉ liên quan tới một trong số đó.

## 5. Bảng quyết định: các trạng thái trước và sau update

Xét changeset tạo bảng customer với điều kiện `not tableExists` và `onFail: MARK_RAN`. Giả sử changelog không có bộ lọc khác, định danh changeset chưa có trong lịch sử và không dùng runAlways/runOnChange.

| Tình trạng trước update | Kết quả precondition | Phần changes có chạy? | Kết quả lịch sử thông thường |
|---|---|---|---|
| Bảng customer chưa tồn tại | Đạt | Có, tạo bảng | EXECTYPE=EXECUTED |
| Bảng customer đã tồn tại và đúng cấu trúc | Không đạt | Không | EXECTYPE=MARK_RAN |
| Bảng customer đã tồn tại nhưng sai cấu trúc | Không đạt | Không | EXECTYPE=MARK_RAN, **nguy cơ drift** |
| Không đủ quyền kiểm tra metadata | Lỗi đánh giá | Không, với onError=HALT | Dừng; không coi đó là hoàn thành |
| Changeset đã có lịch sử từ lần trước | Thông thường không xét chạy lại | Không | Giữ trạng thái đã ghi nhận, trừ các trường hợp đặc biệt |

Điểm nguy hiểm nhất là hai hàng “đúng cấu trúc” và “sai cấu trúc” có thể dẫn đến **cùng một kết quả MARK_RAN** nếu precondition chỉ kiểm tra sự tồn tại. Liquibase không thể tự hiểu toàn bộ ý nghĩa nghiệp vụ của đối tượng từ một điều kiện đơn giản.

Vì vậy, **MARK_RAN không chứng minh schema đúng**. Nó chỉ chứng minh rằng luồng xử lý đã lựa chọn đánh dấu changeset theo cấu hình precondition và lịch sử.

## 6. MARK_RAN ghi gì vào DATABASECHANGELOG?

Liquibase sử dụng bảng lịch sử mặc định **DATABASECHANGELOG** trên từng database để ghi nhận những changeset đã chạy hoặc đã được xử lý theo các cơ chế đặc biệt. Một bản ghi thường có các trường như:

| Cột | Dữ liệu cần lưu ý |
|---|---|
| ID | `id` trong changeset |
| AUTHOR | `author` trong changeset |
| FILENAME | Đường dẫn changelog hiệu lực, hoặc định danh logic được cấu hình |
| DATEEXECUTED | Thời điểm Liquibase ghi nhận xử lý changeset |
| ORDEREXECUTED | Thứ tự được Liquibase ghi nhận |
| EXECTYPE | Trạng thái thực thi; **MARK_RAN** cho trường hợp được đánh dấu |
| MD5SUM | Checksum được ghi nhận theo quy tắc phiên bản Liquibase |
| DESCRIPTION / COMMENTS | Mô tả thao tác và comment khi Liquibase ghi nhận |
| LIQUIBASE | Thông tin phiên bản Liquibase được lưu trong lịch sử |
| DEPLOYMENT_ID | Mã nhóm cập nhật do Liquibase tạo trong những phiên bản hỗ trợ |

Tập cột và cách cập nhật một số giá trị phụ thuộc phiên bản Liquibase và cấu hình. Điều cần nhớ là **EXECTYPE=MARK_RAN khác EXECTYPE=EXECUTED**. Cả hai đều có thể làm changeset không còn xuất hiện trong danh sách pending thông thường, nhưng chúng **không chứng minh cùng một quá trình**.

Một truy vấn tham khảo để điều tra:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    DATEEXECUTED,
    ORDEREXECUTED,
    EXECTYPE,
    MD5SUM,
    COMMENTS
FROM DATABASECHANGELOG
WHERE ID = '001-create-customer'
  AND AUTHOR = 'schema-team';
~~~

Vì định danh changeset còn phụ thuộc đường dẫn changelog, khi đối chiếu chính xác cần kiểm tra **FILENAME**. Để thống kê các changeset được đánh dấu trên database đích:

~~~sql
SELECT ID, AUTHOR, FILENAME, DATEEXECUTED, EXECTYPE
FROM DATABASECHANGELOG
WHERE EXECTYPE = 'MARK_RAN'
ORDER BY DATEEXECUTED, ORDEREXECUTED;
~~~

Các truy vấn chỉ đọc dành cho điều tra; phải chạy trên đúng database, schema và tên bảng lịch sử của môi trường. Không chỉnh trực tiếp DATABASECHANGELOG để thay đổi EXECTYPE hoặc làm cho migration trông như đã chạy.

## 7. Điều gì xảy ra ở lần update tiếp theo?

Đây là hệ quả vận hành quan trọng nhất của MARK_RAN.

Giả sử:

1. Ngày thứ nhất, bảng customer đã tồn tại.
2. Changeset `001-create-customer` có precondition `not tableExists` với `onFail: MARK_RAN`.
3. Liquibase chạy update, precondition không đạt, không tạo bảng, nhưng ghi nhận `001-create-customer` với EXECTYPE=MARK_RAN.
4. Ngày thứ hai, bảng customer bị xóa thủ công hoặc phát hiện ra chưa đủ cột.
5. Pipeline tiếp tục chạy `update` với cùng changelog.

**Thông thường changeset 001 sẽ không tự chạy lại**, vì Liquibase đã có lịch sử cho định danh của changeset đó. Việc bảng customer không còn tồn tại **không khiến Liquibase tự đánh giá lại precondition** cho một changeset đã được ghi nhận, trừ khi có cấu hình/chính sách chạy lại đặc biệt.

Vì thế, không nên nghĩ:

> “Ngày mai nếu điều kiện đạt, Liquibase sẽ quay lại chạy changeset từng MARK_RAN.”

Đó không phải hành vi mặc định. `MARK_RAN` là một quyết định có tác động kéo dài tới lịch sử, không phải cơ chế “bỏ qua tạm thời và thử lại” như một hàng đợi.

Nếu hệ thống cần thử lại vào lần cập nhật sau, `onFail: CONTINUE` có ý nghĩa khác: changeset không được đánh dấu hoàn tất khi precondition không đạt và có thể được xem xét vào lần update kế tiếp theo quy tắc Liquibase. Tuy nhiên, CONTINUE chỉ phù hợp khi nhóm **chủ động muốn để thay đổi ở trạng thái pending**, không phải để che giấu việc schema thiếu đối tượng bắt buộc.

## 8. So sánh HALT, WARN, CONTINUE và MARK_RAN

Các giá trị phổ biến cho xử lý **onFail** tại changeset-level có ý nghĩa khác nhau:

| onFail | Hệ quả khái quát khi precondition không đạt | Có ghi changeset như đã xử lý? | Khi nào nên cân nhắc |
|---|---|---|---|
| **HALT** | Dừng migration và báo lỗi | Không coi thay đổi này đã hoàn thành | Điều kiện an toàn bắt buộc; sai trạng thái phải sửa trước |
| **WARN** | Phát cảnh báo và tiếp tục luồng cập nhật; không phải cơ chế “skip” | Không thay thế bằng MARK_RAN; changeset có thể tiếp tục thực thi | Điều kiện mang tính cảnh báo, không bắt buộc |
| **CONTINUE** | Bỏ qua changeset ở lần này, tiếp tục xử lý các changeset khác | Thông thường không ghi nhận changeset như đã chạy | Muốn thử lại ở lần update sau nếu điều kiện có thể thay đổi |
| **MARK_RAN** | Bỏ qua phần changes và đánh dấu changeset đã xử lý | **Có**, với trạng thái MARK_RAN | Đã xác minh đối tượng/trạng thái mong muốn có sẵn một cách hợp lệ |

Bảng chỉ tóm lược hành vi ở mức khái niệm; cách thông báo lỗi và thứ tự xử lý còn phụ thuộc phạm vi precondition và phiên bản Liquibase. Cần kiểm tra chính xác trên phiên bản dự án.

Một cách chọn nhanh:

- **Nếu thiếu điều kiện có thể làm dữ liệu hỏng:** HALT.
- **Nếu điều kiện chỉ hỗ trợ cảnh báo và thao tác vẫn an toàn:** có thể cân nhắc WARN.
- **Nếu cần để changeset chờ đến khi điều kiện sẵn sàng:** CONTINUE.
- **Nếu thao tác đã được đáp ứng hợp lệ từ trước và muốn ghi nhận kết thúc:** MARK_RAN.

Không chọn MARK_RAN chỉ vì mong pipeline trả về kết quả thành công. Một `update` kết thúc không báo lỗi không chứng minh ứng dụng sẽ làm việc được với schema cuối.

## 9. Ví dụ phản diện: viết ngược điều kiện sẽ đánh dấu sai

Giả sử mục tiêu là **tạo bảng customer nếu bảng chưa tồn tại**. Một lỗi phổ biến:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: wrong-create-customer
      author: schema-team
      preConditions:
        - onFail: MARK_RAN
        - tableExists:
            tableName: customer
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

Đoạn này **sai logic**:

- Bảng chưa có: `tableExists` không đạt → changeset bị **MARK_RAN**, bảng **không được tạo**.
- Bảng đã có: `tableExists` đạt → Liquibase cố **CREATE TABLE** lại và có nguy cơ lỗi trùng tên.

Đúng với mục tiêu “tạo nếu chưa có” phải kiểm tra **NOT tableExists**, ví dụ:

~~~yaml
preConditions:
  - onFail: MARK_RAN
  - onError: HALT
  - not:
      - tableExists:
          tableName: customer
~~~

Tuy nhiên, cấu hình đúng về mặt logic vẫn chưa bảo đảm đủ an toàn để dùng MARK_RAN trong production: cần xác thực bảng có sẵn là **tương đương** với bảng do changeset dự kiến tạo. Nếu chưa biết, nên dừng để kiểm tra thay vì đánh dấu.

## 10. Một changeset có nhiều thao tác: vì sao MARK_RAN rủi ro?

Xét changeset chứa hai thay đổi:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 003-customer-extended
      author: schema-team
      preConditions:
        - onFail: MARK_RAN
        - not:
            - columnExists:
                tableName: customer
                columnName: status
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: status
                  type: varchar(20)
        - createIndex:
            tableName: customer
            indexName: idx_customer_status
            columns:
              - column:
                  name: status
~~~

Nếu cột status **đã có**, precondition không đạt và **cả addColumn lẫn createIndex bị bỏ qua**. Giả sử cột đã có nhưng index chưa có, database sẽ thiếu index; lịch sử lại cho thấy changeset đã MARK_RAN.

Một thiết kế tốt hơn là **tách theo một mục tiêu độc lập trên mỗi changeset**:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 003-add-customer-status
      author: schema-team
      preConditions:
        - onFail: MARK_RAN
        - onError: HALT
        - not:
            - columnExists:
                tableName: customer
                columnName: status
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: status
                  type: varchar(20)

  - changeSet:
      id: 004-create-customer-status-index
      author: schema-team
      preConditions:
        - onFail: MARK_RAN
        - onError: HALT
        - not:
            - indexExists:
                tableName: customer
                indexName: idx_customer_status
      changes:
        - createIndex:
            tableName: customer
            indexName: idx_customer_status
            columns:
              - column:
                  name: status
~~~

Ví dụ tách changeset giúp hai đối tượng có điều kiện độc lập và lịch sử rõ hơn. Tuy nhiên, kiểm tra cột hoặc index chỉ theo tên vẫn phải bổ sung xác nhận kiểu dữ liệu, constraint và định nghĩa index nếu chúng quan trọng.

**Quy tắc:** precondition của một changeset nên chứng minh rằng việc **bỏ qua toàn bộ phần changes** là an toàn, chứ không chỉ chứng minh một thao tác nhỏ trong đó có thể bỏ qua.

## 11. MARK_RAN không giống tính idempotent của SQL

Một thay đổi được gọi là **idempotent** khi chạy lại nhiều lần vẫn đưa database về cùng một trạng thái mong muốn. Ví dụ, một số DBMS hỗ trợ `CREATE TABLE IF NOT EXISTS`. Nhưng “không lỗi khi bảng đã tồn tại” không có nghĩa “bảng tồn tại đúng cấu trúc”. Một bảng sai schema vẫn có thể bị bỏ qua mà không được sửa.

MARK_RAN còn khác idempotency ở chỗ:

- MARK_RAN là **quyết định ghi nhận lịch sử**.
- Idempotency là **tính chất của thao tác** khi chạy một hoặc nhiều lần.
- Một changeset bị MARK_RAN có thể chứa câu lệnh không hề chạy, dù câu lệnh đó được thiết kế idempotent.
- Một migration có SQL idempotent vẫn cần lịch sử, kiểm soát phiên bản, precondition và validation phù hợp.

Các lựa chọn kỹ thuật cần phân biệt:

| Cách làm | Kết quả |
|---|---|
| Dùng change type Liquibase chung | Tạo SQL theo DBMS cho thay đổi được hỗ trợ |
| Dùng precondition + HALT | Không cho phép triển khai nếu trạng thái không đạt |
| Dùng precondition + CONTINUE | Tạm bỏ qua và để changeset còn có thể xét ở lần sau |
| Dùng precondition + MARK_RAN | Đánh dấu changeset đã xử lý mà không chạy phần changes khi điều kiện thất bại |
| Dùng SQL idempotent | Hạn chế lỗi khi thao tác được lặp lại, nhưng không tự ghi nhận quyết định baseline |
| Tạo changeset sửa tiếp | Duy trì lịch sử rõ ràng khi schema/dữ liệu đã triển khai cần thay đổi |

Không dùng MARK_RAN như một lớp bọc mặc định cho mọi `createTable`, `addColumn` hoặc `createIndex`. Nó là công cụ có chủ đích để **hòa giải lịch sử với trạng thái đã xác minh**, không phải phương pháp loại bỏ mọi rủi ro khi chạy migration.

## 12. Kiểm chứng tương đương schema trước khi MARK_RAN

Nếu một bảng đã tồn tại do migration cũ, manual script hoặc quá trình chuyển từ Flyway sang Liquibase, nhóm phải quyết định tiêu chí “tương đương” thay vì chỉ kiểm tra tên.

Với bảng customer, tối thiểu có thể cần kiểm tra:

1. Bảng tồn tại trong đúng schema hoặc catalog.
2. Cột id, email, status tồn tại theo yêu cầu.
3. Kiểu dữ liệu, độ dài, nullable và default value đúng.
4. Khóa chính, unique constraint, foreign key và index đúng.
5. Nếu có dữ liệu, các bất biến nghiệp vụ vẫn được giữ.
6. Quyền trên bảng và khả năng truy cập của ứng dụng phù hợp.
7. Ứng dụng ở revision sắp triển khai tương thích với cấu trúc đã có.

Precondition có thể sử dụng các kiểm tra như `tableExists`, `columnExists`, `indexExists`, `primaryKeyExists`, `sqlCheck` tùy phiên bản Liquibase và DBMS.

Với logic phức tạp, có thể cần bước kiểm tra độc lập chạy truy vấn metadata của DBMS và so sánh snapshot schema. Một precondition đơn giản không thể đảm bảo toàn bộ cấu trúc đúng trong mọi trường hợp.

Nếu thiếu bất kỳ yêu cầu quan trọng nào, **không đánh dấu hoàn thành** chỉ vì bảng/cột trùng tên. Nên HALT để điều tra hoặc tạo changeset bổ sung nhằm đưa schema về trạng thái đích.

## 13. Đưa database cũ vào quản lý mà không đánh dấu nhầm

Đưa một database đã tồn tại vào quy trình Liquibase thường được gọi là **baseline** hoặc **adoption**. MARK_RAN đôi khi được dùng cho một hoặc vài changeset có đối tượng đã hiện hữu. Nhưng với số lượng lớn đối tượng, việc lặp lại `onFail: MARK_RAN` thiếu kiểm soát có thể gây nhiều trạng thái lệch khó thấy.

Một quy trình thực tế:

**Bước 1 — Chốt trạng thái hiện tại.** Ghi rõ DBMS, phiên bản, schema, phiên bản ứng dụng và snapshot cấu trúc; nếu cần khôi phục, có backup đáng tin cậy.

**Bước 2 — Xác định tập thay đổi đã tồn tại.** Đối chiếu schema của database cũ với master changelog và phiên bản code tương ứng.

**Bước 3 — Phân loại từng changeset.** Changeset nào thực sự đã có kết quả tương đương; changeset nào mới; changeset nào cần sửa bằng bước chuyển tiếp.

**Bước 4 — Chọn chiến lược baseline.** Có thể dùng MARK_RAN có kiểm chứng cho một số changeset, hoặc sử dụng lệnh đồng bộ lịch sử như `changelog-sync` theo quy trình riêng. Hai cơ chế không phải thay thế máy móc cho nhau.

**Bước 5 — Thử trên bản sao.** Chạy validate, xem status, tạo SQL dự kiến, áp dụng migration trên bản sao của database cũ rồi kiểm tra lịch sử và cấu trúc thật.

**Bước 6 — Triển khai có giám sát.** Ghi lại ai phê duyệt baseline, revision changelog, changeset nào được đánh dấu, bằng chứng tương đương và hướng khôi phục.

**Bước 7 — Tiếp tục migration bình thường.** Sau baseline, các changeset mới nên theo lịch sử tăng dần. Không duy trì các quy tắc MARK_RAN tùy tiện để che sự khác biệt giữa các database mãi mãi.

Khi baseline, **không được coi việc status trả về không còn pending là thành công đầy đủ**. Kết quả thành công phải là **schema và dữ liệu phù hợp với ứng dụng**.

## 14. MARK_RAN khác changelog-sync ra sao?

Cả hai đều có thể dẫn đến việc ghi nhận changeset trong lịch sử mà không thực thi phần thay đổi, nhưng mục đích và cách điều khiển khác nhau.

| Tiêu chí | MARK_RAN theo precondition | changelog-sync |
|---|---|---|
| Đơn vị quyết định | Một changeset có precondition, dựa trên kết quả điều kiện | Các changeset mà lệnh đồng bộ lịch sử nhắm tới theo changelog và cấu hình gọi |
| Điều kiện | Khi precondition thất bại theo onFail: MARK_RAN | Theo thao tác đồng bộ được operator/pipeline yêu cầu |
| Mục đích thường gặp | Chấp nhận đối tượng/trạng thái đã tồn tại tương đương | Đồng bộ lịch sử khi adopt/baseline một trạng thái đã xác minh |
| Tác động | Đánh dấu changeset, không chạy phần changes tương ứng | Ghi nhận trạng thái không thực thi phần changes |
| Rủi ro | Điều kiện quá yếu khiến schema sai bị xem là đã xử lý | Đồng bộ cả những changeset thực ra chưa có kết quả trên database |
| Kiểm chứng tối thiểu | Bằng chứng precondition và schema cuối | Bản đối chiếu đầy đủ changelog với schema/dữ liệu đích |

Không chạy `changelog-sync` bừa bãi để “xóa pending” và không thêm MARK_RAN hàng loạt chỉ để pipeline qua bước update. Dù chọn cách nào, cần xác minh những changeset được đánh dấu có thật sự tương ứng với trạng thái thực tế.

Một lưu ý về thuật ngữ: bảng lịch sử có thể ghi các kiểu EXECTYPE như MARK_RAN, nhưng ý nghĩa từng lần ghi cần đọc cùng **log và quy trình phát hành**. Đừng suy ra nguyên nhân chính xác chỉ từ một cột EXECTYPE khi không có ngữ cảnh về câu lệnh đã chạy.

## 15. Tác động đối với checksum và thay đổi changelog về sau

Liquibase sử dụng checksum để nhận biết thay đổi nội dung của changeset đã được ghi nhận. Với một changeset đã có lịch sử MARK_RAN, **không nên coi nó là “chưa chạy nên muốn sửa gì cũng được”**. Liquibase vẫn có thể đối chiếu định danh và checksum của changeset theo quy tắc phiên bản đang dùng.

Ví dụ:

1. Changeset 001 bị MARK_RAN vì bảng customer đã tồn tại.
2. Một developer thấy database ở môi trường khác thiếu cột email.
3. Developer sửa SQL trong chính changeset 001 để thêm cột.
4. Lần chạy tiếp theo có thể gặp vấn đề checksum hoặc thay đổi hành vi kiểm tra lịch sử, tùy phiên bản và thuộc tính của changeset.

Ngay cả khi một chỉnh sửa không tạo lỗi checksum, việc sửa changeset đã ghi nhận vẫn gây ra **lịch sử khó tái hiện**: database cũ được đánh dấu theo nội dung trước, còn database mới có thể áp dụng nội dung khác.

Nguyên tắc an toàn:

- Giữ ổn định **id, author và đường dẫn changelog hiệu lực**.
- Tránh chỉnh sửa changeset đã được ghi nhận ở bất kỳ môi trường chia sẻ nào.
- Khi cần thêm cột, constraint hoặc backfill, **tạo changeset mới**.
- Không dùng `clearCheckSums`, `validCheckSum` hoặc sửa DATABASECHANGELOG để âm thầm hợp thức hóa thay đổi chưa được review.
- Khi nâng cấp Liquibase, kiểm tra cơ chế checksum và lịch sử trên bản sao database trước khi production.

Những thuộc tính đặc biệt như `runOnChange` và `runAlways` cần được thiết kế chủ động; chúng không thay thế quy tắc bất biến cho migration schema thông thường.

## 16. runOnChange và runAlways có làm MARK_RAN chạy lại không?

Ở trạng thái mặc định, changeset đã ghi nhận MARK_RAN thường được Liquibase xem là **đã xử lý** và bỏ qua trong các lần update kế tiếp. Hai thuộc tính có thể tác động đến quy tắc lựa chọn chạy lại:

- **runOnChange:** Changeset có thể được xét chạy lại khi phần nội dung được Liquibase theo dõi checksum thay đổi theo quy tắc của phiên bản đó.
- **runAlways:** Changeset được thiết kế để được xét ở mỗi lần update thích hợp, ngay cả khi đã có lịch sử.

Nếu một changeset vừa có precondition `onFail: MARK_RAN` vừa có cơ chế chạy lại, nó có thể **được đánh giá lại** trong một số lần update sau. Điều này đòi hỏi phân tích và thử nghiệm riêng theo phiên bản Liquibase.

Không nên suy luận rằng thêm `runAlways: true` vào một changeset cũ sẽ sửa chữa được database đã lệch schema:

- Nếu điều kiện vẫn không đạt, changeset có thể lại bị đánh dấu thay vì thực hiện thao tác mong đợi.
- Nếu điều kiện đã đạt, thao tác có thể thực thi trong hoàn cảnh không được thiết kế trước.
- Thao tác không idempotent hoặc có side effect dữ liệu có thể chạy nhiều lần.
- Việc thay đổi thuộc tính của changeset đã được ghi nhận cần kiểm tra lịch sử và checksum.

Do đó, **không dùng runAlways/runOnChange như “nút thử lại” mặc định cho MARK_RAN**. Với schema sai, cách thường rõ ràng hơn là tạo changeset mới để kiểm tra và sửa đúng thiếu sót.

## 17. MARK_RAN và rollback: không thể giả định đã có gì để hoàn tác

Rollback là bước đảo ngược tác động thực tế của migration. Vấn đề của MARK_RAN là **phần changes không được thực thi**, nhưng changeset đã có lịch sử.

Ví dụ một changeset khai báo:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 005-create-customer-legacy
      author: schema-team
      preConditions:
        - onFail: MARK_RAN
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
                  constraints:
                    primaryKey: true
                    nullable: false
      rollback:
        - dropTable:
            tableName: customer
~~~

Nếu bảng customer tồn tại từ trước, changeset có thể bị MARK_RAN. Nhưng rollback khai báo `dropTable` sẽ **xóa bảng có sẵn**, không phân biệt bảng được tạo bởi changeset hay bởi hệ thống cũ, **nếu** câu lệnh đó được thực thi.

Không được giả định rằng Liquibase tự biết bảng “không thuộc” changeset bị MARK_RAN và sẽ luôn bỏ qua rollback tương ứng. Hành vi chọn changeset và tạo/thực thi rollback cần được kiểm chứng bằng lệnh preview và thử trên DBMS thực tế.

Một quy trình rollback an toàn:

1. Xác định các row `EXECTYPE=MARK_RAN` trong phạm vi rollback dự kiến.
2. Đọc phần rollback của những changeset đó và xác định đối tượng/dữ liệu thực sự thuộc về ai.
3. Sinh SQL rollback dự kiến nếu lệnh và phiên bản hỗ trợ.
4. Kiểm tra tác động trên bản sao database có lịch sử tương đương.
5. Nếu rollback có thể xóa dữ liệu của bảng legacy, thiết kế kế hoạch forward fix hoặc phục hồi riêng.
6. Chỉ thực thi sau khi đã xác nhận mốc rollback, backup và khả năng tương thích ứng dụng.

Đặc biệt với lệnh rollback theo số changeset hoặc theo tag, cần hiểu **những thay đổi nào được công cụ chọn**; không suy đoán chỉ dựa vào thứ tự include. Trong những hệ thống đã dùng MARK_RAN để baseline, rollout/rollback cần được thiết kế như quy trình đặc biệt, không giống một database được dựng hoàn toàn từ Liquibase.

## 18. Dữ liệu và quan hệ giữa các changeset sau MARK_RAN

Một changeset bị MARK_RAN có thể khiến những changeset phía sau chạy với giả định không đúng.

Ví dụ:

~~~text
001-create-customer      -> MARK_RAN vì bảng customer đã tồn tại
002-add-customer-status   -> Thực thi addColumn
003-backfill-status       -> Thực thi UPDATE
004-add-status-not-null   -> Thêm constraint
~~~

Nếu bảng customer legacy thiếu cột id hoặc có kiểu email khác dự kiến, changeset 002 có thể chạy nhưng ứng dụng sau đó lỗi. Nếu dữ liệu legacy chứa giá trị không hợp lệ, bước 003 hoặc 004 có thể thất bại.

Quan trọng: **MARK_RAN ở 001 không có nghĩa Liquibase xác nhận mọi invariant của 001**. Các changeset sau không thể chỉ dựa vào lịch sử để suy ra schema nền chính xác.

Nên bổ sung kiểm chứng ở những mốc chuyển tiếp:

- Kiểm tra cột/ràng buộc và dữ liệu thiết yếu trước migration phụ thuộc.
- Thêm precondition HALT cho điều kiện không được bỏ qua.
- Chạy migration trên database sạch **và** bản copy database cũ.
- Đối chiếu schema cuối, dữ liệu backfill và hành vi ứng dụng.
- Ghi kết quả vào release record để giải thích vì sao một số changeset MARK_RAN.

Đây là cách tách **lịch sử Liquibase** khỏi **bằng chứng thực tế rằng dữ liệu đáp ứng yêu cầu nghiệp vụ**.

## 19. Context, label, dbms và MARK_RAN

Một changeset có thể bị loại bởi context, label hoặc dbms trước khi có cơ hội thực thi theo các điều kiện của nó. Không nên nhầm các trạng thái này với MARK_RAN.

| Tình huống | Khái niệm đúng | Có tự động tạo EXECTYPE=MARK_RAN? |
|---|---|---|
| Changeset có dbms: postgresql nhưng đang chạy MySQL | Bị lọc theo DBMS | Không, chỉ vì bộ lọc không khớp |
| Changeset không được chọn do label filter | Bị lọc theo label | Không, chỉ vì nhãn bị loại |
| Changeset không được chọn do context filter | Bị lọc theo context | Không, chỉ vì context bị loại |
| Changeset được xét, precondition false, onFail=CONTINUE | Bỏ qua ở lần này, còn có thể xét lần sau | Không theo cơ chế MARK_RAN |
| Changeset được xét, precondition false, onFail=MARK_RAN | Đánh dấu đã xử lý | **Có** |
| Changeset có lịch sử EXECUTED hoặc MARK_RAN | Đã có bản ghi lịch sử | Bình thường không cần chạy lại |

Đặc biệt, không nên gắn `onFail: MARK_RAN` cho changeset “chỉ dành cho môi trường test” để tự bảo vệ production. Hãy sử dụng cơ chế lọc context/label, kết hợp guard CI/CD và kiểm chứng bộ lọc. Context thông thường có thể vẫn được chọn khi không truyền context filter, nên phải hiểu chính xác semantics của phiên bản Liquibase và cách gọi.

Nếu một bước **không được phép chạy trên sai DBMS**, dùng dbms hoặc precondition có HALT khi cần chủ động từ chối môi trường; đừng để nó bị MARK_RAN rồi bị xem như đã hoàn thành.

## 20. Spring Boot và CI/CD: vì sao MARK_RAN dễ bị bỏ qua?

Với Spring Boot, Liquibase có thể chạy tự động khi ứng dụng khởi động. Ví dụ cấu hình:

~~~yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USER}
    password: ${DB_PASSWORD}
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
~~~

Nếu một changeset bị MARK_RAN, việc khởi động có thể tiếp tục nếu không có lỗi khác. Nhưng ứng dụng vẫn có thể lỗi về sau nếu schema bị bỏ qua không thực sự tương đương. Nhiều replica Spring Boot có thể dùng khóa Liquibase để điều phối migration, nhưng **DATABASECHANGELOGLOCK không xác thực cấu trúc schema đúng**.

Với pipeline CI/CD, một quy trình an toàn gồm:

1. **Kiểm soát đầu vào:** sử dụng changelog revision và artifact đã được review.
2. **Định danh database:** xác nhận DBMS, database/schema, environment và tài khoản migration.
3. **Validate:** kiểm tra changelog và precondition có cấu trúc hợp lệ.
4. **Status và preview:** xem changeset pending và sinh SQL dự kiến bằng đúng cấu hình mục tiêu.
5. **Thử trên database đại diện:** gồm database mới và database có lịch sử cũ, ưu tiên cùng DBMS/phiên bản với production.
6. **Thực thi migration:** chạy `update` trong một job được điều phối có chủ đích.
7. **Kiểm tra lịch sử:** truy vấn DATABASECHANGELOG, đặc biệt những row có EXECTYPE=MARK_RAN mới phát sinh.
8. **Kiểm tra schema/dữ liệu:** xác nhận các invariant quan trọng không bị bỏ qua.
9. **Ghi release record:** lưu commit, artifact, job, môi trường, kết quả kiểm chứng và lý do MARK_RAN khi có.
10. **Triển khai ứng dụng tương thích:** chỉ tiếp tục khi những kiểm tra bắt buộc đạt.

Chạy `validate` và nhận exit code 0 không chứng minh precondition sẽ không MARK_RAN trên production. Kết quả precondition phụ thuộc database thật, nên cần test và kiểm tra tại môi trường đích.

Một quy tắc kiểm soát thực tế: nếu release có **MARK_RAN bất ngờ**, coi đó là tín hiệu cần điều tra trước khi triển khai ứng dụng tiếp; không xem nó là dấu hiệu thành công tương đương EXECUTED.

## 21. Bài thực hành: ba database, ba kết quả khác nhau

Mục tiêu: quan sát rõ khác biệt giữa EXECUTED, MARK_RAN và trường hợp MARK_RAN che giấu drift.

### Chuẩn bị

Dùng ba database thử nghiệm độc lập cùng loại DBMS, tất cả chưa có bản ghi cho changeset `001-create-customer`:

- **A — sạch:** chưa có bảng customer.
- **B — legacy hợp lệ:** đã có bảng customer đúng cấu trúc dự kiến.
- **C — legacy sai:** đã có bảng customer nhưng thiếu cột email hoặc email sai kiểu dữ liệu.

Changelog kiểm thử:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: lab-team
      comment: Tạo customer nếu chưa có, đánh dấu lịch sử nếu bảng đã tồn tại
      preConditions:
        - onFail: MARK_RAN
        - onError: HALT
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
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: varchar(320)
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            tableName: customer
~~~

### Chạy thử

Với mỗi database, dùng cấu hình Liquibase tương ứng để:

1. Chạy validate.
2. Xem status trước update.
3. Xem SQL dự kiến khi thích hợp.
4. Chạy update trên database thử nghiệm.
5. Truy vấn DATABASECHANGELOG.
6. Kiểm tra cấu trúc bảng customer.
7. Chạy update lần hai, quan sát việc changeset có được chạy lại hay không.

### Kết quả mong đợi

| Database | Phần changes chạy ở lần đầu? | EXECTYPE dự kiến | Schema cuối có chắc đúng? | Update lần hai |
|---|---|---|---|---|
| A — sạch | Có, tạo bảng | EXECUTED | Cần kiểm tra sau DDL | Thông thường không chạy lại |
| B — legacy đúng | Không | MARK_RAN | Đúng **nếu** đã kiểm chứng tương đương | Thông thường không chạy lại |
| C — legacy sai | Không | MARK_RAN | **Không đúng**, dù lịch sử có bản ghi | Thông thường không tự sửa |

Kết luận của bài thực hành là **A, B và C có thể đều không còn pending sau update**, nhưng chỉ A và B có khả năng đáp ứng cấu trúc mục tiêu; C là ví dụ cho thấy MARK_RAN không tự đảm bảo tính đúng đắn.

### Thử thay đổi trạng thái sau MARK_RAN

Trên database B sau khi đã MARK_RAN, xóa một cột thiết yếu trong database thử nghiệm rồi chạy update lần nữa. Hãy quan sát changeset 001 thông thường không được thực thi lại. Không lặp lại phép thử phá schema trên môi trường chia sẻ hoặc production.

### Thử đối chiếu rollback

Trên bản sao B, xem SQL rollback dự kiến và đánh giá nó có thể tác động đến bảng legacy như thế nào nếu được thực thi. Không chạy rollback phá hủy thật chỉ để “thử cho biết”; nếu muốn kiểm tra hành vi, phải dùng database disposable và xác định lại từ đầu sau mỗi thử nghiệm.

## 22. Runbook khi phát hiện MARK_RAN bất ngờ

Giả sử pipeline báo thành công, nhưng application logs xuất hiện lỗi “column status does not exist”. Truy vấn DATABASECHANGELOG cho thấy một changeset addColumn có EXECTYPE=MARK_RAN.

Nên xử lý theo trình tự:

**Bước 1 — Dừng tiếp tục triển khai.** Không đưa thêm replica/phiên bản ứng dụng phụ thuộc cột đó nếu schema chưa phù hợp.

**Bước 2 — Định danh chính xác.** Ghi nhận database, schema, id, author, FILENAME, DATEEXECUTED, EXECTYPE và revision changelog.

**Bước 3 — Tìm precondition đã tạo MARK_RAN.** Đọc changelog ở revision deploy, kiểm tra `onFail`, `onError`, toán tử `not`, phạm vi schema/catalog và biến tham số.

**Bước 4 — Đối chiếu schema và dữ liệu thật.** Xác định cột nào có, kiểu dữ liệu/constraint có đúng không, có drift hoặc thay đổi thủ công nào không.

**Bước 5 — Phân tích ảnh hưởng.** Xác định ứng dụng nào đã triển khai, SQL nào phụ thuộc schema mới, dữ liệu nào có nguy cơ bị ghi sai hoặc bị mất.

**Bước 6 — Chọn hướng sửa.** Tạo changeset mới có kiểm chứng để bổ sung đối tượng thiếu, hoặc xử lý bằng quy trình khôi phục đã duyệt. Tránh sửa changeset cũ và tránh sửa tay EXECTYPE.

**Bước 7 — Thử trên bản sao trước.** Chạy migration sửa trong môi trường tương đương, kiểm tra schema, dữ liệu, ứng dụng và khả năng rollback/forward fix.

**Bước 8 — Triển khai có giám sát và ghi hậu kiểm.** Lưu nguyên nhân gốc, revision, bằng chứng giải quyết và bổ sung kiểm thử để tránh tái diễn.

Có thể gặp một trường hợp khác: MARK_RAN là hoàn toàn chủ đích vì schema legacy tương đương. Khi đó không cần “sửa EXECTYPE thành EXECUTED”; cần lưu chứng cứ giải thích tại sao đó là trạng thái hợp lệ.

## 23. Những hiểu nhầm thường gặp

| Nhận định | Thực tế |
|---|---|
| “MARK_RAN nghĩa là SQL đã thực thi thành công” | Sai. Changes có thể **không chạy** dù lịch sử ghi MARK_RAN. |
| “Nếu dữ liệu/schema thiếu, lần update sau sẽ chạy lại” | Sai ở chế độ thông thường; changeset đã được ghi nhận. |
| “Status không còn pending thì schema chắc đúng” | Sai. MARK_RAN có thể che drift nếu precondition quá yếu. |
| “tableExists là đủ để chấp nhận mọi cấu trúc bảng” | Sai. Tên bảng không bảo đảm cột, constraint hoặc dữ liệu tương đương. |
| “MARK_RAN và CONTINUE giống nhau” | Sai. CONTINUE thường không đánh dấu hoàn tất và có thể xét ở lần sau. |
| “Precondition bị lỗi cũng nên MARK_RAN” | Nguy hiểm. Phân biệt onError với onFail; lỗi kiểm tra nên dừng khi không có bằng chứng an toàn. |
| “Có rollback thì chắc chắn xóa đúng đối tượng do changeset tạo” | Sai. MARK_RAN không chứng minh changeset đã tạo đối tượng đó. |
| “Có thể sửa changeset MARK_RAN vì nó chưa chạy SQL” | Không nên; định danh và lịch sử checksum vẫn có thể bị ảnh hưởng. |
| “Cứ thêm runAlways là giải quyết được” | Không. Có thể làm thao tác thực thi lại sai thời điểm hoặc lặp side effect. |
| “Chạy lại build Spring Boot sẽ tự chữa schema” | Không. Liquibase dựa vào lịch sử changeset, không tự suy luận schema đích đầy đủ. |
| “MARK_RAN là cách tốt nhất để mọi migration không lỗi” | Sai. Ưu tiên migration có kiểm chứng, precondition HALT khi trạng thái không phù hợp, và changeset sửa tiếp. |

## 24. Checklist trước khi cho phép MARK_RAN trong một release

- [ ] Changeset có mục đích rõ ràng và nhóm xác nhận lý do cần MARK_RAN.
- [ ] MARK_RAN được đặt đúng **changeset-level precondition**.
- [ ] Phân biệt và khai báo xử lý **onFail** với **onError** một cách có chủ đích.
- [ ] Điều kiện có đúng chiều logic, đặc biệt khi dùng `not`?
- [ ] Precondition đủ để cho phép bỏ qua **toàn bộ changes**, không chỉ một thao tác.
- [ ] Có bằng chứng cấu trúc và dữ liệu thực tế tương đương với mục tiêu migration.
- [ ] Không dùng điều kiện chỉ kiểm tra tên đối tượng khi cần xác minh kiểu dữ liệu/constraint.
- [ ] Đã đánh giá tác động lên các changeset phụ thuộc ở phía sau.
- [ ] Đã kiểm thử trên **database sạch**, **legacy đúng** và **legacy sai**.
- [ ] Đã xác minh bản ghi DATABASECHANGELOG, đặc biệt **EXECTYPE=MARK_RAN**.
- [ ] Đã chứng minh hành vi của lần update tiếp theo; không kỳ vọng changeset tự chạy lại.
- [ ] Không chỉnh sửa id/author/file hoặc checksum của changeset đã được ghi nhận.
- [ ] Không dùng runAlways/runOnChange để vá tạm lỗi schema thiếu đối tượng.
- [ ] Đã xem xét rollback và nguy cơ làm mất bảng/dữ liệu legacy.
- [ ] Có backup hoặc kế hoạch forward fix cho migration phá hủy.
- [ ] CI/CD kiểm tra trường hợp MARK_RAN bất ngờ và xác minh invariant của schema.
- [ ] Spring Boot và job migration được điều phối thống nhất, không dựa vào log khởi động để kết luận schema đúng.
- [ ] Release record lưu lý do, người review và bằng chứng cho các changeset được MARK_RAN.

**Ghi nhớ:** `onFail: MARK_RAN` là quyết định **ghi nhận lịch sử thay cho thực thi thay đổi khi precondition không đạt**. Hệ quả là changeset thường **không được chạy lại** trong các lần update thông thường, dù trạng thái database thay đổi sau đó. Vì vậy, chỉ dùng MARK_RAN khi đã xác minh đối tượng hoặc dữ liệu tương đương; kiểm tra bằng DATABASECHANGELOG, schema thực tế và các thử nghiệm migration. Đó là cách bảo vệ tính tái lập của changelog và tính nhất quán giữa các môi trường khi vận hành Liquibase qua Spring Boot hoặc CI/CD.

