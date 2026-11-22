# Chọn độ lớn changeset và nguyên tắc mỗi thay đổi có mục đích rõ ràng

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chương **Changeset**, một quyết định thiết kế quan trọng là: **nên đặt bao nhiêu thay đổi cơ sở dữ liệu trong một changeset?** Changeset quá lớn khó kiểm tra, khó khắc phục khi triển khai thất bại; changeset bị chia vụn theo từng câu SQL lại khiến mục đích nghiệp vụ và thứ tự phụ thuộc khó đọc. Đơn vị phù hợp thường là **một thay đổi có mục đích kỹ thuật hoặc nghiệp vụ rõ ràng, có thể được xác minh và theo dõi độc lập**.

Liquibase giúp quản lý thay đổi schema và dữ liệu qua changelog, changeset, precondition, checksum và lịch sử triển khai. Việc chọn đúng ranh giới changeset ảnh hưởng trực tiếp đến độ an toàn khi update, rollback, phối hợp môi trường và tích hợp Spring Boot hoặc CI/CD.

Sau bài học, người học có thể giải thích thế nào là changeset “vừa đủ”, lựa chọn khi nào gộp hoặc tách thay đổi, thiết kế chuỗi migration có phụ thuộc, và đánh giá rủi ro giao dịch, khóa bảng, dữ liệu cùng khả năng rollback.

## 1. Phân biệt changelog, changeset và change

Một **changelog** là tài liệu Liquibase đọc để xác định các thay đổi cần triển khai. Trong changelog có nhiều **changeset**; trong mỗi changeset lại có thể có một hoặc nhiều **change** như thêm cột, tạo bảng, tạo chỉ mục, cập nhật dữ liệu hoặc chạy câu lệnh SQL.

Ví dụ cấu trúc khái niệm:

~~~text
Changelog
├── Changeset A: tạo bảng thông báo
│   ├── createTable
│   └── createIndex
├── Changeset B: bổ sung trạng thái cho khách hàng
│   └── addColumn
└── Changeset C: chuyển dữ liệu trạng thái cũ
    └── update
~~~

Liquibase nhận diện changeset chủ yếu bằng bộ ba **id + author + đường dẫn changelog** (có thể chịu tác động của logicalFilePath), rồi tra lịch sử trong bảng **DATABASECHANGELOG**. Khi changeset được triển khai và ghi nhận, Liquibase lưu thông tin thực thi cùng **checksum**. Ở những lần update tiếp theo, Liquibase dùng lịch sử và checksum để xác định changeset đã chạy có còn khớp định nghĩa hiện tại hay không.

Vì vậy, **changeset là đơn vị lịch sử triển khai**: nó không nhất thiết phải là một câu SQL, một tính năng hoàn chỉnh hay một lần phát hành. Một yêu cầu nghiệp vụ có thể cần nhiều changeset, trong khi một changeset có thể chứa nhiều change cùng phục vụ một mục đích.

Ví dụ: để tạo một bảng mới hoàn chỉnh, nhóm có thể đặt thao tác tạo bảng và tạo chỉ mục cần thiết vào cùng changeset, nếu chúng được triển khai cùng lúc, gắn kết về mục đích, rủi ro thấp và có cách khôi phục rõ ràng. Ngược lại, tăng kích thước cột, sửa dữ liệu và xóa cột cũ thường nên được chia thành các bước có thể kiểm chứng độc lập.

## 2. Nguyên tắc cốt lõi: một changeset, một mục đích

Hãy mô tả changeset bằng một câu chủ động:

> “Bổ sung cột tier có thể null vào bảng customer để chuẩn bị phân loại khách hàng.”

Câu này cho biết **đối tượng**, **tác động** và **mục đích**. Nếu phải nối nhiều mệnh đề không liên quan, chẳng hạn “thêm cột khách hàng, xóa bảng log và đổi dữ liệu khuyến mãi”, changeset có dấu hiệu đang ôm quá nhiều trách nhiệm.

Một changeset tốt nên có các đặc điểm:

1. **Cùng một mục đích**: các change bên trong phục vụ một kết quả rõ ràng.
2. **Ranh giới đánh giá được**: reviewer có thể nói rõ changeset sẽ làm gì và điều gì chứng minh nó thành công.
3. **Phụ thuộc minh bạch**: biết changeset cần điều kiện nào và changeset sau phụ thuộc vào kết quả nào.
4. **Rủi ro tương đồng**: không vô tình trộn một thao tác metadata rất nhanh với một thao tác dữ liệu hàng triệu dòng có thể kéo dài nhiều giờ.
5. **Khôi phục được hoặc có kế hoạch phục hồi**: biết tác động nếu thất bại hoặc phải đảo ngược.
6. **Ổn định sau khi phát hành**: tránh sửa lại nội dung changeset đã được ghi vào lịch sử triển khai.

**“Một mục đích” không đồng nghĩa “một câu SQL”.** Ví dụ, tạo một bảng trống kèm chỉ mục cơ bản có thể là một đơn vị hợp lý. Nhưng sửa schema và thực hiện backfill dữ liệu lớn thường có lịch triển khai, mức khóa và cách kiểm chứng khác nhau, nên cần cân nhắc tách.

## 3. Tiêu chí quyết định nên gộp hay tách

| Câu hỏi thiết kế | Có thể gộp khi | Nên tách khi |
|---|---|---|
| Các thao tác có cùng mục tiêu không? | Chúng cùng tạo ra một cấu trúc hoặc quy tắc nhất quán | Chúng thuộc các nhu cầu nghiệp vụ không liên quan |
| Có cần triển khai cùng thời điểm không? | Không thao tác nào có ý nghĩa độc lập trong kế hoạch phát hành | Cần quan sát hoặc triển khai ứng dụng giữa các bước |
| Có thể xác minh cùng một kết quả không? | Một tập điều kiện kiểm tra đủ chứng minh thành công | Cần kiểm tra dữ liệu và schema riêng |
| Có cùng rủi ro vận hành không? | Thời gian chạy, khóa và phạm vi tác động tương đương | Một bước có thể khóa bảng lớn hoặc chạy lâu |
| Có cùng chính sách rollback không? | Có thể đảo ngược chúng như một đơn vị hợp lý | Một bước tự động rollback, bước khác mất dữ liệu khi đảo |
| Có cùng cơ chế giao dịch không? | DBMS hỗ trợ thực thi nhất quán như dự kiến | Một change cần chạy ngoài transaction hoặc DDL tự commit |
| Có điều kiện thực thi giống nhau không? | Chúng áp dụng cho cùng tập môi trường và điều kiện | Một bước cần context, label, dbms hoặc precondition khác |
| Có đáng giữ lịch sử riêng không? | Nhật ký gộp vẫn dễ giải thích khi điều tra | Cần biết chính xác từng giai đoạn đã chạy ở môi trường nào |

Đây là **bộ tiêu chí**, không phải luật máy móc. Mỗi changeset phát sinh thêm ID, lịch sử, checkpoint và chi phí quản lý. Đừng tạo hàng chục changeset chỉ vì một bảng mới có nhiều cột; cũng đừng gộp hàng chục thao tác vì chúng xuất hiện trong cùng một ticket.

Quy tắc thực dụng: **gộp những thao tác gắn bó về mục đích và cách triển khai; tách khi khác mục đích, mức rủi ro, khả năng kiểm chứng hoặc thời điểm vận hành**.

## 4. Ví dụ phù hợp: tạo một bảng mới cùng chỉ mục của bảng đó

Giả sử hệ thống cần bảng mới **notification_outbox** để lưu thông báo đang chờ xử lý. Vì bảng chưa tồn tại và chưa có dữ liệu, việc tạo bảng kèm chỉ mục tìm theo thời điểm có thể là một changeset có mục đích rõ ràng: “khởi tạo cấu trúc outbox”.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-001-create-notification-outbox
      author: platform
      changes:
        - createTable:
            tableName: notification_outbox
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: created_at
                  type: TIMESTAMP
                  constraints:
                    nullable: false
              - column:
                  name: payload
                  type: VARCHAR(4000)
                  constraints:
                    nullable: false
        - createIndex:
            indexName: idx_notification_outbox_created_at
            tableName: notification_outbox
            columns:
              - column:
                  name: created_at
      rollback:
        - dropTable:
            tableName: notification_outbox
~~~

**Vì sao có thể gộp?** Bảng và chỉ mục liên quan trực tiếp; chỉ mục được tạo khi bảng còn trống; yêu cầu kiểm tra tập trung vào việc cấu trúc outbox tồn tại đúng thiết kế. Nếu chạy ở DBMS có hỗ trợ giao dịch DDL phù hợp, thao tác có thể được xử lý nhất quán trong một changeset.

**Giới hạn cần lưu ý:** Không thể mặc định mọi DBMS đều rollback DDL theo transaction. Ví dụ rollback ở trên xóa toàn bộ bảng và dữ liệu đã phát sinh sau này, nên chỉ phù hợp khi đã xác nhận không cần giữ dữ liệu. Trong môi trường có dữ liệu thật, cần một kế hoạch phục hồi khác thay vì áp dụng lệnh dropTable một cách máy móc.

Nếu yêu cầu là tạo chỉ mục lớn trên bảng đang có hàng trăm triệu dòng, đó lại là một quyết định khác: chỉ mục có thể cần thời gian chạy dài, hạn chế khóa hoặc cú pháp đặc thù DBMS. Khi đó, nên tách thành changeset chuyên biệt, với cách theo dõi và lịch triển khai riêng.

## 5. Ví dụ cần tách: mở rộng schema, chuyển dữ liệu, siết ràng buộc

Giả sử bảng **customer** đã có trong production và đang có dữ liệu. Nhóm muốn thêm cột **tier** để phân loại khách hàng; mọi khách hàng cũ tạm nhận giá trị **STANDARD**, và về lâu dài tier phải khác null.

Nếu gộp thêm cột, cập nhật tất cả dòng và thêm NOT NULL vào một changeset, nhóm có thể gặp các vấn đề:

- Backfill rất lớn, kéo dài thời gian triển khai và tăng nguy cơ khóa hoặc tranh chấp với truy cập ứng dụng.
- Nếu backfill lỗi, việc hiểu trạng thái sau lỗi khó hơn, nhất là với DBMS không hỗ trợ rollback DDL như mong đợi.
- Ứng dụng cũ có thể vẫn tạo bản ghi tier null, khiến bước thêm NOT NULL thất bại.
- Rollback schema và rollback dữ liệu có tính chất khác nhau; dữ liệu phát sinh sau migration có thể bị mất khi đảo bước.

Một kế hoạch có chủ đích rõ ràng gồm ba changeset hoặc ba giai đoạn.

### Giai đoạn A — Expand: thêm cột tương thích ngược

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-010-customer-tier-expand
      author: platform
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: tier
                  type: VARCHAR(20)
~~~

Changeset này chỉ làm một việc: tạo cột **tier** cho phép null. Ứng dụng cũ vẫn có thể chạy. Kiểm chứng là cột đã tồn tại, kiểu dữ liệu đúng và chưa tạo ràng buộc phá vỡ luồng ghi cũ.

### Giai đoạn B — Backfill: điền dữ liệu cũ

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-011-customer-tier-backfill
      author: platform
      changes:
        - update:
            tableName: customer
            columns:
              - column:
                  name: tier
                  value: STANDARD
            where: tier IS NULL
~~~

Changeset này có mục đích riêng: làm đầy dữ liệu còn thiếu. Điều kiện WHERE giới hạn việc cập nhật các dòng đang null; nó không biến thao tác thành rollback an toàn. Khi khối lượng dữ liệu lớn, **không nên dùng một UPDATE khổng lồ chỉ vì nó ngắn gọn**. Có thể chuyển sang job backfill theo lô, kiểm soát tài nguyên và chỉ tiếp tục khi số dòng chưa xử lý về 0. Nếu dùng công cụ ngoài Liquibase cho backfill, hãy ghi rõ ranh giới trách nhiệm và bằng chứng hoàn thành trong quy trình phát hành.

### Giai đoạn C — Contract: áp dụng ràng buộc

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-012-customer-tier-not-null
      author: platform
      preConditions:
        - onFail: HALT
        - sqlCheck:
            expectedResult: "0"
            sql: SELECT COUNT(*) FROM customer WHERE tier IS NULL
      changes:
        - addNotNullConstraint:
            tableName: customer
            columnName: tier
            columnDataType: VARCHAR(20)
      rollback:
        - dropNotNullConstraint:
            tableName: customer
            columnName: tier
            columnDataType: VARCHAR(20)
~~~

Changeset này chỉ có mục đích **cố định quy tắc dữ liệu** sau khi hệ thống đã sẵn sàng. Precondition ở đây kiểm tra không còn dòng tier null; nếu không đạt, **HALT** giúp dừng quy trình thay vì âm thầm ghi nhận thành công. Với bảng lớn, truy vấn đếm có thể tốn tài nguyên; cần chọn cách kiểm tra phù hợp với DBMS, kích thước bảng và thời điểm triển khai.

Quan trọng: ba changeset trong ví dụ được trình bày riêng để nhấn mạnh từng mục đích. **Chỉ chia thành ba changeset trong một changelog không tự tạo khoảng thời gian giữa các giai đoạn.** Nếu cùng được đưa vào một lệnh update, Liquibase có thể chạy chúng liên tiếp. Kế hoạch phát hành thực tế thường cần triển khai ứng dụng mới có khả năng ghi tier hợp lệ, hoàn tất backfill rồi mới chạy bước contract ở một lần phát hành sau. Khi đang có lưu lượng ghi, cần bảo đảm không xuất hiện bản ghi null mới giữa lúc kiểm tra và áp dụng ràng buộc.

### Vì sao rollback phải được nghĩ theo từng giai đoạn?

- **Expand**: xóa cột để đảo ngược có thể xóa cả dữ liệu tier đã phát sinh, nên chỉ làm khi đã đánh giá dữ liệu.
- **Backfill**: không thể an toàn đảo mọi giá trị STANDARD thành null, vì có thể xóa nhầm dữ liệu do ứng dụng cập nhật hợp lệ sau đó. Muốn phục hồi chính xác cần snapshot, log hoặc chiến lược dữ liệu được chuẩn bị trước.
- **Contract**: bỏ ràng buộc NOT NULL có thể là cách rollback cấu trúc, nhưng còn phải kiểm tra tương thích với ứng dụng đang chạy.

Một chuỗi migration tốt tách rõ điều gì có thể hoàn tác tự động, điều gì cần quy trình phục hồi có điều kiện, và điều gì chỉ có thể tiến tiếp bằng migration sửa chữa.

## 6. Độ lớn changeset liên quan thế nào đến transaction?

Liquibase thông thường cố gắng thực thi từng changeset trong một transaction khi cấu hình và DBMS cho phép; thuộc tính **runInTransaction** mặc định là **true**. Điều này giúp các thao tác trong cùng changeset có cơ hội cùng thành công hoặc cùng thất bại.

Tuy nhiên, có ba giới hạn quan trọng:

1. **Khả năng giao dịch phụ thuộc DBMS và loại câu lệnh.** Một số DDL thực hiện implicit commit hoặc không được rollback như DML thông thường.
2. **Transaction của một changeset không bao trùm mặc định toàn bộ changelog.** Nếu changeset A hoàn tất rồi changeset B thất bại, A có thể đã được ghi lịch sử và không tự đảo ngược chỉ vì B lỗi.
3. **runInTransaction: false làm giảm bảo đảm nguyên tử trong changeset.** Nó có thể cần thiết với một số câu lệnh đặc thù, nhưng nếu changeset có nhiều câu lệnh và lỗi giữa chừng, database có thể còn trạng thái dở dang cần phục hồi thủ công.

Do đó, lựa chọn độ lớn không chỉ là chuyện “ít dòng” hay “nhiều dòng”. Cần hiểu **ranh giới transaction thực tế**, thời gian giữ khóa, khả năng quan sát lỗi và kế hoạch phục hồi.

Ví dụ, tạo một chỉ mục bằng cú pháp yêu cầu chạy ngoài transaction trên một DBMS cụ thể thường nên nằm trong changeset riêng, tách khỏi các thay đổi schema khác. Khi lựa chọn **runInTransaction: false**, phải giải thích lý do kỹ thuật, kiểm tra hành vi trên đúng DBMS và tránh xâu nhiều câu lệnh không liên quan vào cùng changeset.

## 7. Precondition: bảo vệ điều kiện của từng mục đích

**Precondition** giúp Liquibase kiểm tra điều kiện cần có trước khi thực thi changeset. Khi mỗi changeset có một mục đích, precondition cũng có thể tập trung vào đúng mục đích đó.

Ví dụ, bước bổ sung ràng buộc chỉ được chạy khi dữ liệu hiện tại đã thỏa mãn quy tắc. Khi chia changeset, nhóm có thể kiểm chứng “cột đã tồn tại”, “dữ liệu đã được backfill”, rồi “được phép siết ràng buộc” tại các điểm khác nhau.

Lưu ý:

- **onFail: HALT** phù hợp khi thiếu điều kiện là tình huống phải điều tra; nó giúp phát hiện thiếu bước hoặc lệch trạng thái.
- **MARK_RAN** có thể ghi nhận một changeset là đã xử lý mà không thực thi phần changes. Chỉ dùng khi semantics của changeset cho phép và đã xác nhận trạng thái mong đợi thực sự tồn tại. Dùng MARK_RAN để bỏ qua lỗi tùy tiện có thể khiến lịch sử nói “đã xong” trong khi schema chưa đúng.
- Precondition không thay thế kiểm thử transaction, không tự làm SQL có thể chạy lại vô hạn, và không bảo đảm logic ứng dụng đang triển khai đã tương thích.
- Nếu điều kiện phụ thuộc môi trường, cần mô tả rõ tính chất đó; tránh giấu các khác biệt lớn giữa môi trường trong một changeset quá tổng quát.

## 8. Checksum, định danh và tính bất biến sau khi triển khai

Lựa chọn độ lớn changeset ảnh hưởng đến **phạm vi bất biến**: sau khi changeset đã chạy, nội dung của nó được gắn với checksum trong **DATABASECHANGELOG**. Nếu chỉnh sửa một thao tác bên trong changeset đã phát hành và làm checksum thay đổi, Liquibase có thể báo lỗi validation ở môi trường đã triển khai.

Một changeset quá lớn làm một chỉnh sửa nhỏ cũng ảnh hưởng đến định nghĩa lịch sử của cả đơn vị. Vì vậy:

- Đặt **id** có ý nghĩa và ổn định, kết hợp **author** cùng đường dẫn changelog nhất quán.
- Không sử dụng lại id để viết lại mục đích cũ. Khi có yêu cầu mới, thông thường hãy tạo changeset mới.
- Giữ thứ tự phụ thuộc rõ ràng. Không đổi thứ tự và sửa nội dung migration đã triển khai theo cách gây sai khác lịch sử.
- Tránh dùng **clear-checksums** hoặc **validCheckSum** như cách thường xuyên để vượt lỗi do sửa changeset cũ. Những cơ chế này cần lý do được kiểm chứng và không tự đồng bộ lại schema.
- Chỉ áp dụng **runOnChange** khi cố ý quản lý một đối tượng cần được tạo lại hoặc thay thế, ví dụ một số view hoặc stored procedure; không coi nó là giải pháp để giữ một changeset schema lớn có thể chỉnh sửa tùy ý.

Liên hệ với quyết định độ lớn: **các thay đổi có chu kỳ phát triển và chính sách cập nhật khác nhau nên có ranh giới changeset riêng**. Ví dụ định nghĩa view được phép thay thế thường không nên trộn với migration tăng cột hay xóa dữ liệu một lần.

## 9. Độ lớn hợp lý trong các tình huống phổ biến

| Tình huống | Gợi ý thiết kế | Lý do |
|---|---|---|
| Tạo bảng mới kèm khóa và chỉ mục cơ bản | Có thể gộp thành một changeset | Một mục đích khởi tạo cấu trúc, ít dữ liệu ban đầu |
| Thêm hai cột phục vụ cùng một khái niệm mới | Có thể gộp nếu cùng thời điểm và rollback | Cùng một thay đổi mô hình dữ liệu |
| Thêm cột rồi cập nhật hàng triệu bản ghi | Nên tách schema và backfill | Khác thời gian chạy, khóa, cách kiểm tra và rollback |
| Thay đổi kiểu dữ liệu có nguy cơ mất thông tin | Changeset riêng, cần kế hoạch chuyển dữ liệu | Có thể cần kiểm tra tương thích, backup và hướng phục hồi |
| Tạo chỉ mục lớn trên bảng đang hoạt động | Nên tách khỏi thay đổi khác | Có nhu cầu vận hành và DBMS riêng |
| Thay đổi dữ liệu tham chiếu nhỏ, cùng quy tắc | Có thể gộp các dòng liên quan | Một mục đích và kiểm tra đồng nhất |
| Xóa cột cũ sau khi ứng dụng chuyển đổi | Changeset riêng, phát hành sau | Cần xác nhận ứng dụng đã hết phụ thuộc |
| Hai tính năng khác nhau cùng phát hành | Thường tách changeset | Dễ truy vết, kiểm tra và sửa chữa độc lập |
| Cập nhật view bằng runOnChange | Tách khỏi schema migration không chạy lại | Chính sách thực thi khác nhau |

Không có con số chuẩn kiểu “mỗi changeset tối đa 3 change” hoặc “tối đa 50 dòng SQL”. Độ lớn phải được giải thích bằng **ranh giới mục đích và vận hành**.

## 10. Cách thiết kế một nhóm changeset trước khi viết YAML

Với một yêu cầu migration thực tế, có thể làm theo thứ tự sau:

1. **Viết mục tiêu cuối** bằng câu có thể kiểm tra, ví dụ “mọi customer có tier hợp lệ”.
2. **Liệt kê trạng thái trung gian** cần đạt: thêm cột, cập nhật ứng dụng ghi dữ liệu, backfill, kiểm tra null, siết ràng buộc.
3. **Xác định phụ thuộc**: bước siết ràng buộc cần dữ liệu đã chuẩn hóa và ứng dụng không còn ghi null.
4. **Đánh dấu rủi ro** cho từng bước: khóa, lượng dữ liệu, tính mất mát thông tin, thời gian chạy, khả năng rollback.
5. **Chọn ranh giới changeset** tại nơi có thể kiểm chứng độc lập, cần lịch phát hành khác hoặc có chính sách xử lý lỗi khác.
6. **Đặt ID và author ổn định**, viết nội dung changelog theo đúng thứ tự phụ thuộc.
7. **Viết precondition và rollback/phương án phục hồi** cho từng changeset, tránh dùng rollback xóa dữ liệu nếu chưa có bảo vệ.
8. **Kiểm thử đường cài mới và đường nâng cấp** trước khi triển khai nhiều môi trường.

Ví dụ sơ đồ quyết định:

~~~text
Một thay đổi mới
       |
       v
Có cùng mục đích với các change lân cận?
       |
     Không ----> Tách changeset
       |
      Có
       v
Có khác thời điểm triển khai, rủi ro khóa,
transaction hoặc chính sách phục hồi?
       |
      Có -----> Tách changeset
       |
     Không
       v
Có thể xác minh như một đơn vị rõ ràng?
       |
      Có -----> Có thể gộp
       |
     Không ----> Làm rõ ranh giới rồi tách
~~~

Sơ đồ chỉ hỗ trợ quyết định. Reviewer vẫn cần xem kích thước dữ liệu, DBMS thực tế và mức độ ảnh hưởng đến ứng dụng.

## 11. Kiểm chứng trước khi đưa vào CI/CD

Với Liquibase CLI, các bước kiểm tra thường gặp:

~~~bash
liquibase validate
liquibase update-sql
liquibase status --verbose
~~~

**validate** kiểm tra tính hợp lệ của changelog và các quy tắc validation được Liquibase hỗ trợ. **update-sql** giúp xem trước các câu SQL dự kiến chạy, còn **status --verbose** hỗ trợ nhận diện changeset chưa được áp dụng. Các lệnh cần sử dụng cấu hình kết nối, changelog và phiên bản Liquibase phù hợp với môi trường kiểm thử.

Khi thử migration, nên kiểm tra hai trường hợp:

- **Database trống**: chạy toàn bộ changelog để kiểm tra có xây dựng được schema mới từ đầu không.
- **Database có lịch sử cũ**: dùng bản sao trạng thái thực tế từ phiên bản trước để kiểm tra chuỗi nâng cấp có chạy đúng, checksum có khớp và dữ liệu có được bảo toàn không.

Trong CI/CD, nên giữ cùng artifact changelog từ môi trường kiểm thử đến môi trường phát hành. Đối với migration nhiều giai đoạn, pipeline hoặc kế hoạch release phải đặt đúng điểm dừng để triển khai ứng dụng, chạy backfill và kiểm tra điều kiện trước khi siết ràng buộc. Không nên để một lệnh update vô tình chạy tất cả giai đoạn trong khi ứng dụng chưa sẵn sàng.

Với Spring Boot, Liquibase có thể chạy khi ứng dụng khởi động. Nếu nhiều instance cùng được khởi động, cần xác định rõ tiến trình chịu trách nhiệm migration hoặc kiểm soát việc đồng thời, thứ tự và kết quả khởi tạo ứng dụng. Liquibase có cơ chế khóa lịch sử cập nhật, nhưng cơ chế khóa không thay thế kế hoạch phát hành và kiểm tra tính tương thích của ứng dụng.

## 12. Checklist review độ lớn changeset

Trước khi merge migration, reviewer cần trả lời được:

- Mục đích của changeset có diễn đạt trong một câu rõ ràng không?
- Mỗi change bên trong có phục vụ mục đích đó không?
- Có thao tác nào cần lịch triển khai, điều kiện hoặc rollback khác để tách riêng không?
- Nếu changeset chạy một phần rồi lỗi, trạng thái database thực tế có thể là gì trên DBMS đang dùng?
- Có thao tác nào gây khóa lâu, quét bảng lớn, mất dữ liệu hoặc cần job theo lô không?
- Các changeset đã phát hành có được giữ nguyên để tránh lỗi checksum không?
- Tên, id, author, đường dẫn và thứ tự phụ thuộc có ổn định và dễ tra cứu không?
- Precondition có kiểm tra đúng điều kiện; thất bại có làm dừng triển khai khi cần không?
- Rollback có thực sự an toàn với dữ liệu phát sinh sau triển khai; nếu không, kế hoạch phục hồi là gì?
- Đã thử nâng cấp từ database có lịch sử, không chỉ thử xây mới từ database trống chưa?

**Kết luận:** Chọn độ lớn changeset là chọn đơn vị quản lý thay đổi có ý nghĩa. Một changeset nên đủ nhỏ để diễn giải, kiểm tra và xử lý thất bại độc lập, nhưng đủ lớn để các thao tác gắn chặt với cùng một mục đích không bị chia vụn. Khi ranh giới đó phản ánh đúng phụ thuộc dữ liệu, transaction, rollback và nhịp triển khai, lịch sử Liquibase sẽ dễ kiểm chứng hơn và các đợt migration qua Spring Boot hoặc CI/CD sẽ an toàn, dễ truy vết hơn.

