# Phân biệt thay đổi lược đồ, dữ liệu tham chiếu và dữ liệu nghiệp vụ

## 1. Mục tiêu và bối cảnh

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase được dùng để quản lý thay đổi schema và dữ liệu thông qua changelog, changeset, precondition, checksum và lịch sử triển khai. Việc học cũng bao gồm migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Bài thuộc chương **Chuyển đổi dữ liệu** và trả lời một câu hỏi quan trọng: **cùng là thay đổi database, tại sao tạo cột mới, thêm danh mục trạng thái và sửa dữ liệu đơn hàng đang hoạt động lại cần ba chính sách triển khai khác nhau?**

Ba loại công việc này thường xuất hiện trong cùng một lần phát hành nhưng khác nhau về **nguồn sự thật, quyền sở hữu, mức độ phụ thuộc môi trường, rủi ro mất dữ liệu và khả năng rollback**. Nhầm lẫn giữa chúng có thể dẫn đến migration không thể tái tạo, seed dữ liệu lặp lại, ghi đè dữ liệu của khách hàng hoặc database đã nâng cấp nhưng ứng dụng chưa tương thích.

Sau bài học, bạn cần có thể:

- Phân biệt **thay đổi lược đồ (schema migration)**, **dữ liệu tham chiếu (reference data)** và **dữ liệu nghiệp vụ (business/operational data)**.
- Chọn loại thay đổi phù hợp với Liquibase changeset và xác định khi nào cần một job chuyển đổi dữ liệu riêng.
- Giải thích vì sao **insert dữ liệu chuẩn**, **backfill dữ liệu đang tồn tại** và **seed dữ liệu giả để test** không phải cùng một loại thao tác.
- Thiết kế thứ tự migration, precondition, kiểm chứng dữ liệu, quyền sở hữu, rollback và chiến lược triển khai nhiều giai đoạn.
- Đánh giá tác động tới **DATABASECHANGELOG**, checksum, các môi trường triển khai và Spring Boot/CI/CD.

## 2. Ba nhóm thay đổi và câu hỏi phân loại

### 2.1. Thay đổi lược đồ: database có thể lưu gì và bảo vệ dữ liệu như thế nào?

**Lược đồ (schema)** là cấu trúc và các quy tắc của database: bảng, cột, kiểu dữ liệu, khóa chính, khóa ngoại, unique constraint, CHECK, index, view và những đối tượng liên quan.

Ví dụ:

- Tạo bảng **purchase_order**.
- Thêm cột **payment_status_code**.
- Đổi kiểu dữ liệu của cột, thêm khóa ngoại hoặc ràng buộc CHECK.
- Tạo index để hỗ trợ truy vấn.
- Đổi tên cột hoặc chia một bảng thành hai bảng.

Thay đổi lược đồ thường thuộc về **nhóm phát triển và quản trị database**, được review cùng mã ứng dụng và được áp dụng có thứ tự theo phiên bản. Nhưng chỉ vì thao tác là DDL không có nghĩa nó an toàn: DROP COLUMN có thể làm mất dữ liệu, thay kiểu có thể bị lỗi chuyển đổi hoặc gây khóa bảng lâu.

### 2.2. Dữ liệu tham chiếu: các giá trị chuẩn để hệ thống hiểu cùng một khái niệm

**Dữ liệu tham chiếu** là tập giá trị được dùng để phân loại, kiểm soát hoặc diễn giải dữ liệu nghiệp vụ, thường có **mã ổn định**, số lượng tương đối nhỏ và vòng đời được quản lý.

Ví dụ:

- Mã trạng thái đơn hàng: NEW, PAID, CANCELLED.
- Mã loại giao dịch: PURCHASE, REFUND.
- Mã phương thức thanh toán được hệ thống hỗ trợ: BANK_TRANSFER, CARD.
- Mã phân loại nội bộ dùng cho rule engine.

Tập giá trị này có thể được lưu ở bảng danh mục và được các bảng nghiệp vụ tham chiếu bằng khóa ngoại. Nó **không nhất thiết bất biến mãi mãi**: doanh nghiệp có thể thêm trạng thái hoặc đổi ý nghĩa của trạng thái, nhưng mọi thay đổi phải được review vì có thể tác động đến ứng dụng, báo cáo và lịch sử dữ liệu.

**Tín hiệu nhận biết:** giá trị được quản lý như một phần hợp đồng của sản phẩm, cần có mặt để ứng dụng hoạt động đúng và có thể cần đồng bộ giữa các môi trường.

### 2.3. Dữ liệu nghiệp vụ: sự thật phát sinh trong quá trình vận hành

**Dữ liệu nghiệp vụ** là trạng thái được tạo hoặc cập nhật bởi người dùng, nghiệp vụ, giao dịch hay các hệ thống tích hợp. Ví dụ:

- Đơn hàng, hóa đơn, thanh toán và số dư.
- Khách hàng, địa chỉ nhận hàng và lịch sử thay đổi.
- Số lượng hàng tồn kho, giao dịch hoàn tiền.
- Lịch sử phê duyệt, nhật ký sự kiện nghiệp vụ.

Dữ liệu nghiệp vụ thường có số lượng lớn, thay đổi liên tục, khác nhau giữa các môi trường và chịu ràng buộc về **quyền riêng tư, kiểm toán và tính chính xác**.

Không nên xem dữ liệu này như một tập seed cố định để chạy lại từ Git. Nếu cần chuyển đổi dữ liệu nghiệp vụ, phải xác định rõ **quy tắc biến đổi, phạm vi bản ghi, điều kiện an toàn, chiến lược chạy lại, khả năng khôi phục và người chịu trách nhiệm xác nhận kết quả**.

## 3. Bảng so sánh thực tế

| Tiêu chí | Lược đồ | Dữ liệu tham chiếu | Dữ liệu nghiệp vụ |
|---|---|---|---|
| Ví dụ | Bảng, cột, khóa, index | Trạng thái, loại giao dịch chuẩn | Đơn hàng, thanh toán, khách hàng |
| Bản chất | Định nghĩa cấu trúc và bất biến | Danh mục/mã dùng chung | Sự kiện và trạng thái đang vận hành |
| Nguồn sở hữu thường gặp | Nhóm kỹ thuật, DBA | Nhóm sản phẩm/nghiệp vụ và kỹ thuật | Hệ thống nghiệp vụ và chủ sở hữu dữ liệu |
| Khác biệt giữa môi trường | Nên có chủ đích và được kiểm soát | Thường giống nhau với mã chuẩn bắt buộc | Thường khác đáng kể |
| Quy mô | Số đối tượng schema | Thường nhỏ đến trung bình | Có thể rất lớn |
| Cách triển khai | DDL trong changeset | Insert/update/delete có kiểm soát, loadData nếu phù hợp | Backfill/transform chuyên biệt, có thể dùng job theo lô |
| Có thể chạy lại tùy ý? | Không, phụ thuộc lịch sử | Không nếu thiếu chiến lược idempotent và version | Không; có nguy cơ ghi đè hoặc nhân đôi dữ liệu |
| Rollback | Đảo DDL nếu khả thi | Xem xét tham chiếu từ dữ liệu nghiệp vụ | Thường khó hoặc không thể hoàn tác hoàn toàn |
| Điều kiện nghiệm thu | Đúng cấu trúc, constraint, index | Đúng mã, không trùng, đủ dữ liệu chuẩn | Đúng số bản ghi, giá trị, đối soát, tính toàn vẹn |

**Quan trọng:** loại dữ liệu không chỉ được xác định bởi việc nó nằm trong bảng nào. Một bảng **app_settings** chứa giá trị người dùng tự cấu hình có thể là **dữ liệu nghiệp vụ hoặc cấu hình vận hành** chứ không phải reference data, dù có ít dòng. Ngược lại, một bảng lớn chứa danh sách mã do tiêu chuẩn bên ngoài quản lý có thể vẫn là reference data, nhưng cần cơ chế cập nhật riêng nếu thay đổi thường xuyên.

## 4. Phân loại theo quyền quyết định, không chỉ theo số lượng dòng

Hãy trả lời năm câu hỏi khi chuẩn bị migration:

1. **Ai là nguồn sự thật?** Git/changelog, hệ thống nghiệp vụ, người dùng hay một nguồn danh mục bên ngoài?
2. **Giá trị có cần giống nhau ở mọi môi trường không?** Cùng một mã NEW có cùng ý nghĩa trên staging và production không?
3. **Có được ghi đè hiện trạng không?** Nếu production đã có giá trị khác, cần dừng, cập nhật hay giữ nguyên?
4. **Cách phục hồi là gì?** Có thể đảo ngược bằng DDL/DELETE hay phải có backup và đối soát?
5. **Ai phê duyệt quy tắc biến đổi?** Reviewer kỹ thuật có đủ cơ sở hay cần chủ dữ liệu/nghiệp vụ xác nhận?

Ví dụ một bảng **country_code**: nếu nó được đồng bộ từ tiêu chuẩn quốc tế và ứng dụng chỉ đọc, có thể là reference data. Nhưng nếu nhân viên vận hành được tùy ý cập nhật tên hiển thị và thứ tự ưu tiên cho từng khách hàng, chính các trường tùy chỉnh đó mang tính dữ liệu nghiệp vụ. Cần tách **mã chuẩn** khỏi **giá trị tùy biến** trong thiết kế, hoặc ít nhất phải có chính sách update khác nhau.

Không dùng một câu DELETE rồi INSERT lại toàn bộ bảng danh mục nếu bảng đó đang được dữ liệu nghiệp vụ tham chiếu và có thể tồn tại các chỉnh sửa hợp lệ do người dùng tạo.

## 5. Ranh giới công cụ: Liquibase quản lý thay đổi, không phải thay thế toàn bộ ETL

Liquibase dùng các **changeset** trong **changelog** để áp dụng các thay đổi có thứ tự và lưu lịch sử. Những change type thông dụng có thể bao gồm:

- **createTable, addColumn, modifyDataType, addForeignKeyConstraint, createIndex**: thường phục vụ thay đổi lược đồ.
- **insert, update, delete**: có thể dùng để thêm dữ liệu tham chiếu hoặc biến đổi dữ liệu có phạm vi giới hạn.
- **loadData, loadUpdateData**: hỗ trợ nạp dữ liệu có cấu trúc từ tệp, khi phù hợp với khả năng phiên bản/DBMS và quy tắc triển khai.
- **sql, sqlFile**: thực thi SQL tùy chỉnh khi change type có cấu trúc không diễn đạt được yêu cầu.

Liquibase phù hợp khi **quy tắc thay đổi có thể version hóa và kiểm soát trong quá trình triển khai**. Nhưng khi dữ liệu nghiệp vụ có hàng trăm triệu dòng, biến đổi phức tạp, cần xử lý streaming, checkpoint, chuyển dữ liệu giữa nhiều hệ thống hoặc downtime gần như bằng không, việc cố nhét toàn bộ xử lý vào một changeset SQL dài là lựa chọn rủi ro.

Trong những tình huống đó, một **job ETL/backfill** riêng, có mã phiên bản, khả năng chạy lại và đo tiến độ, thường phù hợp hơn. Changelog có thể vẫn quản lý **các bước schema trước/sau** và các tiền điều kiện cho thời điểm chuyển trạng thái hệ thống; còn job dữ liệu chịu trách nhiệm xử lý nghiệp vụ ở quy mô lớn.

## 6. Minh họa kiến trúc dữ liệu đơn hàng

Giả sử hệ thống ban đầu lưu trạng thái đơn hàng dưới dạng chuỗi tự do:

~~~text
purchase_order
├── id                  BIGINT, primary key
├── status_text         VARCHAR(50)
├── total_amount        DECIMAL(18,2)
└── created_at          TIMESTAMP
~~~

Dữ liệu hiện có có thể chứa giá trị **New**, **NEW**, **Paid**, **PAID**, **Cancelled** hoặc sai chính tả. Mục tiêu là chuyển sang:

~~~text
order_status             (dữ liệu tham chiếu)
├── code                VARCHAR(20), primary key
└── display_name        VARCHAR(100)

purchase_order           (dữ liệu nghiệp vụ)
├── id                  BIGINT, primary key
├── status_text         VARCHAR(50)      # cột cũ, tạm giữ
├── status_code         VARCHAR(20)      # cột mới
├── total_amount        DECIMAL(18,2)
└── created_at          TIMESTAMP
~~~

Sau khi backfill và chuyển ứng dụng, có thể áp dụng khóa ngoại từ **purchase_order.status_code** đến **order_status.code**, thêm NOT NULL nếu dữ liệu và nghiệp vụ cho phép, rồi cuối cùng mới bỏ status_text.

Trong cùng tính năng có **ba loại thay đổi**:

- **Lược đồ:** tạo bảng order_status, thêm cột status_code, thêm FK và sau đó xóa cột cũ.
- **Tham chiếu:** tạo các mã chuẩn NEW, PAID, CANCELLED cùng tên hiển thị.
- **Nghiệp vụ:** chuẩn hóa hàng triệu giá trị status_text đang tồn tại thành status_code mà không làm mất ý nghĩa của mỗi đơn hàng.

Tách chúng giúp thiết kế được thứ tự triển khai, kiểm soát rollback và nghiệm thu từng giai đoạn.

## 7. Thay đổi lược đồ: ưu tiên mô tả cấu trúc bằng change type

Ví dụ tạo bảng danh mục bằng YAML:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-001-create-order-status
      author: data-team
      changes:
        - createTable:
            tableName: order_status
            columns:
              - column:
                  name: code
                  type: VARCHAR(20)
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: display_name
                  type: VARCHAR(100)
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            tableName: order_status
~~~

**Điểm cần lưu ý:**

- Bảng này thuộc **schema**, còn các dòng dữ liệu bên trong là **reference data**.
- Tạo bảng và nạp dữ liệu nên có **changeset riêng** để dễ review và xử lý lỗi.
- Nếu rollback xóa bảng sau khi nó đã được hàng nghiệp vụ tham chiếu, DROP TABLE có thể bị từ chối hoặc phá dữ liệu nếu dùng tùy chọn xóa dây chuyền. Rollback mẫu chỉ là đảo DDL về mặt ý định; phải kiểm chứng với trạng thái database thực tế.
- Với hệ thống đa DBMS, SQL được Liquibase tạo ra phụ thuộc driver và DBMS. Luôn dùng **update-sql** để review trước khi chạy.

Không đổi trực tiếp changeset cũ đã chạy để thêm cột hoặc constraint. Hãy thêm changeset mới; đây là cách giữ lịch sử nâng cấp nhất quán với việc dựng database mới.

## 8. Dữ liệu tham chiếu: mã ổn định, cập nhật có kiểm soát

Sau khi tạo bảng order_status, có thể thêm dữ liệu chuẩn bằng changeset khác:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-002-seed-order-status
      author: data-team
      changes:
        - insert:
            tableName: order_status
            columns:
              - column:
                  name: code
                  value: NEW
              - column:
                  name: display_name
                  value: Đơn hàng mới
        - insert:
            tableName: order_status
            columns:
              - column:
                  name: code
                  value: PAID
              - column:
                  name: display_name
                  value: Đã thanh toán
        - insert:
            tableName: order_status
            columns:
              - column:
                  name: code
                  value: CANCELLED
              - column:
                  name: display_name
                  value: Đã hủy
      rollback:
        - delete:
            tableName: order_status
            where: "code IN ('NEW', 'PAID', 'CANCELLED')"
~~~

Ví dụ này **tự chứa**: không phụ thuộc tệp CSV ngoài. Các mã NEW, PAID, CANCELLED là **khóa nghiệp vụ ổn định**; không dùng số ID tăng tự động nếu bên ngoài cần dựa vào cùng một mã ở mọi môi trường.

### Chính sách quản trị mã tham chiếu

1. **Mã nhận diện không nên tái sử dụng với ý nghĩa khác.** Nếu đã có PAID nghĩa là đã thanh toán, không biến PAID thành “đã nhận hàng”.
2. **Thay đổi tên hiển thị không nhất thiết thay đổi mã.** Có thể dùng changeset update riêng để đổi display_name mà không phải cập nhật tất cả đơn hàng.
3. **Không xóa mã đang được tham chiếu** khi còn dữ liệu nghiệp vụ sử dụng; cân nhắc cột active/is_available để ngừng cho phép lựa chọn mới.
4. **Dữ liệu chuẩn phải có owner và quy trình review.** Nếu một nhóm khác được phép bổ sung mã động ở production, không được seed theo cách xóa sạch dữ liệu của họ.
5. **Rollback DELETE chỉ an toàn khi mã chưa được dữ liệu nghiệp vụ tham chiếu.** Một FK có thể ngăn xóa, và điều đó thường tốt hơn việc phá vỡ lịch sử đơn hàng.

### Có nên dùng loadData hoặc loadUpdateData?

Khi danh mục có nhiều hàng, **loadData** từ CSV có thể thuận tiện. **loadUpdateData** có thể hỗ trợ đồng bộ theo khóa được khai báo như primaryKey theo cơ chế của phiên bản Liquibase, nhưng cần hiểu rõ việc công cụ xử lý insert/update, cách đặt khóa và rollback.

Không sử dụng loadUpdateData như một nút “đồng bộ mọi thứ cho giống file” nếu bảng có dữ liệu do người dùng sở hữu. Những thao tác cập nhật hoặc xóa dòng vắng mặt cần được thiết kế rõ, không mặc định an toàn. Tệp CSV cũng phải được version hóa, đóng gói cùng changelog và kiểm tra encoding, kiểu dữ liệu, NULL và dấu phân cách.

## 9. Dữ liệu nghiệp vụ: chuyển đổi theo quy tắc, không phải seed lại

Chuyển trạng thái của các đơn hàng đã tồn tại là **business data migration**. Mục tiêu không phải xóa toàn bộ rồi INSERT lại, vì những đơn hàng ấy có lịch sử, tham chiếu, quyền sở hữu và số dư thực tế.

Một quy tắc chuyển đổi ban đầu có thể là:

| status_text cũ | status_code mới | Điều kiện |
|---|---|---|
| New, NEW | NEW | Chấp nhận nếu cùng ngữ nghĩa |
| Paid, PAID | PAID | Kiểm tra sự kiện thanh toán tương ứng |
| Cancelled, CANCELLED | CANCELLED | Kiểm tra chính sách hủy |
| null hoặc chuỗi không biết | Chưa xác định | Dừng để điều tra, không tự gán về NEW |

**Không tự gán mọi giá trị không nhận diện thành NEW**, vì điều đó có thể biến một đơn hàng đã thanh toán thành chưa thanh toán.

### Kiểm tra dữ liệu đầu vào trước khi biến đổi

Ví dụ PostgreSQL hoặc một DBMS hỗ trợ cú pháp tương đương:

~~~sql
SELECT status_text, COUNT(*) AS total
FROM purchase_order
GROUP BY status_text
ORDER BY total DESC;
~~~

Trước khi backfill, cần thống nhất danh sách ánh xạ với chủ sở hữu nghiệp vụ, xác định cách xử lý NULL, giá trị bất thường và dữ liệu đã bị sửa thủ công.

## 10. Ví dụ backfill có điều kiện và khả năng chạy lại

Giả sử changeset schema trước đó đã thêm **purchase_order.status_code** và các mã tham chiếu đã có sẵn. Một thay đổi dữ liệu có thể dùng SQL:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-003-backfill-order-status
      author: data-team
      dbms: postgresql
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: purchase_order
        - columnExists:
            tableName: purchase_order
            columnName: status_code
        - sqlCheck:
            expectedResult: "0"
            sql: >
              SELECT COUNT(*)
              FROM purchase_order
              WHERE status_text IS NULL
                 OR UPPER(TRIM(status_text)) NOT IN
                    ('NEW', 'PAID', 'CANCELLED')
      changes:
        - sql:
            sql: >
              UPDATE purchase_order
              SET status_code = CASE UPPER(TRIM(status_text))
                  WHEN 'NEW' THEN 'NEW'
                  WHEN 'PAID' THEN 'PAID'
                  WHEN 'CANCELLED' THEN 'CANCELLED'
                END
              WHERE status_code IS NULL
~~~

**Giải thích và giới hạn:**

- Precondition dừng nếu dữ liệu cũ có giá trị chưa nằm trong bảng ánh xạ. Đây là kiểm tra bảo thủ để tránh mất ý nghĩa.
- Điều kiện **WHERE status_code IS NULL** giúp không ghi đè các dòng đã được chuyển đổi hoặc cập nhật đúng trong lúc rollout.
- DBMS được giới hạn bằng **dbms: postgresql**; cần kiểm tra cách viết SQL và quan hệ với các changeset dành cho DBMS khác.
- Ví dụ **không khai báo rollback tự động**: không có thao tác đảo ngược dữ liệu nghiệp vụ nào được giả định là an toàn. Muốn hoàn tác, phải có kế hoạch riêng và nguồn dữ liệu đáng tin cậy để xác định giá trị cần phục hồi.
- Ví dụ chỉ phù hợp với **tập dữ liệu đủ nhỏ hoặc cửa sổ triển khai cho phép** chạy một UPDATE. Với bảng lớn đang thay đổi liên tục, cần thiết kế batching, checkpoint và cơ chế đồng bộ thêm.

Vì không có rollback được thiết kế trong changeset SQL này, **không được giả định lệnh rollback của Liquibase có thể tự khôi phục trạng thái nghiệp vụ trước backfill**. Nếu dự án cần hỗ trợ hoàn tác, hãy thiết kế và thử nghiệm riêng phương án lưu giá trị cũ, đối soát, phục hồi hoặc sửa tiến về phía trước (forward fix).

### Idempotent không có nghĩa được chạy tùy tiện

Một UPDATE có điều kiện **WHERE status_code IS NULL** có thể giảm tác hại khi thử lại, nhưng tính **idempotent** còn phụ thuộc toàn bộ quy tắc chuyển đổi, thay đổi đồng thời của ứng dụng và điều kiện chọn dữ liệu. Cần test lặp lại trên cùng dữ liệu; không suy từ một mệnh đề WHERE rồi kết luận an toàn hoàn toàn.

Mặt khác, changeset Liquibase thông thường **không tự chạy lại** sau khi đã được ghi vào DATABASECHANGELOG. Kỹ thuật idempotent vẫn cần thiết khi thiết kế xử lý lỗi một phần, job backfill riêng hoặc thao tác khôi phục có kiểm soát.

## 11. Vì sao nên tách schema migration, seed và backfill?

Một chuỗi phụ thuộc rõ ràng:

~~~mermaid
flowchart TD
    A["1. Tạo bảng order_status"] --> B["2. Seed mã NEW/PAID/CANCELLED"]
    B --> C["3. Thêm cột status_code dạng nullable"]
    C --> D["4. Backfill dữ liệu nghiệp vụ"]
    D --> E["5. Đối soát và xác nhận dữ liệu"]
    E --> F["6. Thêm FK và NOT NULL khi phù hợp"]
    F --> G["7. Chuyển ứng dụng sang cột mới"]
    G --> H["8. Xóa cột cũ sau giai đoạn tương thích"]
~~~

Thứ tự là **một thiết kế triển khai**, không phải công thức bất biến. Với hệ thống đang hoạt động, có thể phải triển khai mã ứng dụng hỗ trợ **dual-read/dual-write** trước hoặc sau backfill; cần làm rõ cách đồng bộ các đơn hàng phát sinh trong thời gian chuyển đổi.

Tách các bước giúp:

- Review SQL và kết quả từng phần.
- Đặt precondition và điều kiện nghiệm thu phù hợp với từng loại thay đổi.
- Khôi phục các lỗi trước khi thêm constraint gây tác động mạnh.
- Ước lượng thời gian chạy và khóa database.
- Dễ đưa backfill quy mô lớn ra job riêng.
- Giữ lịch sử changeset và ranh giới trách nhiệm rõ ràng.

**Không nên** gom việc tạo bảng, nạp mã chuẩn, chuyển hàng triệu đơn hàng và DROP COLUMN cũ vào một changeset khổng lồ. Khi phần cuối thất bại, mức độ đã commit có thể phụ thuộc DBMS và rất khó khôi phục.

## 12. Expand–migrate–contract cho dữ liệu nghiệp vụ

Đối với hệ thống có nhiều phiên bản ứng dụng cùng chạy, mẫu **expand–migrate–contract** thường an toàn hơn thay đổi đồng loạt.

### Giai đoạn Expand: thêm cấu trúc tương thích

- Tạo bảng tham chiếu và dữ liệu chuẩn.
- Thêm cột status_code **cho phép NULL** nếu bảng cũ đang có dữ liệu.
- Bổ sung index thích hợp nếu thực sự cần.
- Triển khai ứng dụng có thể hiểu cả cột cũ và cột mới, hoặc một cơ chế ghi đồng bộ rõ ràng.

### Giai đoạn Migrate: chuyển và đối soát dữ liệu

- Đo số lượng và kiểu dữ liệu hiện có.
- Chạy backfill theo ánh xạ được phê duyệt.
- Đồng bộ dữ liệu mới phát sinh trong quá trình backfill.
- Kiểm tra các hàng chưa chuyển hoặc chuyển sai.
- Chỉ công bố hoàn tất khi có tiêu chí nghiệm thu cụ thể.

### Giai đoạn Contract: siết quy tắc và loại bỏ cấu trúc cũ

- Thêm FK đến bảng order_status.
- Thêm NOT NULL khi dữ liệu và ứng dụng đã đáp ứng.
- Ngừng dùng status_text ở mọi phiên bản ứng dụng và job tích hợp.
- Tạo changeset riêng để xóa status_text trong release sau.
- Chuẩn bị phương án khôi phục nếu hệ thống cũ vẫn cần cột ban đầu.

**Điểm khó nhất thường là dữ liệu ghi đồng thời**, không phải SQL ADD COLUMN. Nếu backfill quét các dòng đến một mốc rồi ứng dụng cũ tiếp tục ghi vào status_text, cần có cách không bỏ sót những thay đổi sau mốc đó.

## 13. Backfill dữ liệu lớn: batching, checkpoint và đối soát

Một UPDATE toàn bảng trong transaction dài có thể gây lock, tăng WAL/redo log, giữ tài nguyên lâu và làm chậm hệ thống. Với dữ liệu lớn, nên thiết kế job theo lô với các yêu cầu:

1. **Phạm vi xác định:** khóa chính hoặc khoảng ID, điều kiện thời gian hay phân vùng ổn định.
2. **Checkpoint:** lưu được lô nào đã xử lý, bao nhiêu dòng thành công/thất bại và lỗi cụ thể.
3. **Idempotency:** chạy lại cùng lô không làm đổi bản ghi đã đúng hoặc nhân đôi bản ghi.
4. **Không ghi đè dữ liệu mới:** kiểm tra version/timestamp hoặc chỉ cập nhật dòng còn ở trạng thái cũ theo quy tắc.
5. **Giới hạn tải:** kích thước lô, mức độ song song, nghỉ giữa lô và ngưỡng dừng khi database quá tải.
6. **Quan sát:** theo dõi thời gian, lock, số dòng còn thiếu, lỗi ánh xạ và tính toàn vẹn tham chiếu.
7. **Điểm dừng an toàn:** xác định lúc nào được tạm dừng hoặc rollback logic chuyển đổi.

Ví dụ một truy vấn **chẩn đoán** sau backfill:

~~~sql
SELECT COUNT(*) AS pending_rows
FROM purchase_order
WHERE status_code IS NULL;
~~~

Một truy vấn kiểm tra sai ánh xạ:

~~~sql
SELECT COUNT(*) AS inconsistent_rows
FROM purchase_order
WHERE status_code IS NOT NULL
  AND status_text IS NOT NULL
  AND UPPER(TRIM(status_text)) <> status_code;
~~~

Hai truy vấn chỉ phù hợp nếu quy tắc ánh xạ là chuẩn hóa trực tiếp như ví dụ. Nếu có trường hợp đặc biệt, alias, trạng thái lịch sử hoặc nhiều mã đích, tiêu chí đối soát phải dựa trên **quy tắc nghiệp vụ đã duyệt**, không chỉ so sánh chuỗi.

Nếu triển khai nhiều môi trường hoặc các đợt backfill không cùng thời điểm, hãy ghi nhận **số bản ghi nguồn, số bản ghi đích, số chưa xử lý và số ngoại lệ** theo từng đợt.

## 14. Dữ liệu tham chiếu không phải dữ liệu mẫu hoặc cấu hình bí mật

Ba nhóm thường bị gọi chung là “seed”, nhưng cách quản lý khác nhau.

| Nhóm | Ví dụ | Chính sách nên dùng |
|---|---|---|
| Reference data bắt buộc | NEW, PAID, CANCELLED | Version hóa và triển khai nhất quán; có owner và mã ổn định |
| Dữ liệu mẫu để thử nghiệm | Khách hàng giả, đơn hàng giả | Giới hạn local/test bằng quy trình hoặc context phù hợp; không chạy vào production |
| Cấu hình theo môi trường | Endpoint, tên bucket, schema đích | Cấp qua config triển khai; không hard-code nếu môi trường khác nhau |
| Secret | Mật khẩu DB, API key | Lấy từ secret store; không đưa vào changelog hoặc CSV |
| Dữ liệu nghiệp vụ thật | Đơn hàng và thanh toán thực tế | Bảo vệ, đối soát và chuyển đổi theo chính sách dữ liệu |

Có thể dùng **context/label** của Liquibase để chọn những changeset chỉ dành cho dữ liệu mẫu, nhưng phải test chính xác bộ lọc trong pipeline. Đừng dùng mặc định mơ hồ khiến production vô tình nạp dữ liệu test. Nếu cần dữ liệu mẫu cho integration test, ưu tiên môi trường bị cô lập hoặc fixture riêng do công cụ test quản lý.

## 15. Tiền điều kiện: xác minh tiền đề, không che giấu dữ liệu sai

Precondition giúp dừng migration khi thiếu bảng/cột, sai DBMS hoặc dữ liệu không đạt điều kiện. Với thay đổi dữ liệu nghiệp vụ, **HALT** thường là lựa chọn an toàn khi phát hiện dữ liệu không khớp quy tắc chuyển đổi.

Ví dụ kiểm tra tồn tại bảng và không có mã lạ có thể dùng **tableExists** cùng **sqlCheck** như ở phần backfill. Tuy nhiên:

- **WARN** vẫn có thể cho phép changeset chạy; không dùng khi dữ liệu bất hợp lệ có thể bị sửa sai.
- **CONTINUE** giữ changeset chờ lần sau; chỉ phù hợp nếu thay đổi thực sự được phép trì hoãn và những changeset sau không phụ thuộc.
- **MARK_RAN** ghi nhận changeset đã chạy mà không thực thi. Không dùng để bỏ qua một backfill chưa hoàn tất.
- **onError** cần được xử lý riêng với **onFail**; lỗi truy vấn kiểm tra không chứng minh dữ liệu an toàn.

Một câu **COUNT(*) = 0** trước UPDATE có thể bị mất tính đúng trong khi ứng dụng vẫn ghi dữ liệu. Precondition không tạo ra phép khóa tuyệt đối giữa bước kiểm tra và bước update; cần kế hoạch về concurrency và transaction phù hợp.

## 16. Transaction, checksum và lịch sử triển khai

### 16.1. Transaction theo changeset, không theo toàn release

Liquibase mặc định chạy **mỗi changeset trong transaction** khi DBMS hỗ trợ; thuộc tính **runInTransaction** có thể điều chỉnh hành vi. Nhưng không nên giả định một loạt changeset hoặc toàn bộ changelog thuộc cùng một transaction.

Một số DDL trên một số DBMS có thể implicit commit hoặc không hỗ trợ rollback như mong đợi. DML rất lớn có thể tạo transaction dài. Với backfill, cần chọn ranh giới giao dịch dựa trên dữ liệu thực tế và DBMS.

**Không đổi runInTransaction thành false chỉ để chữa một migration chậm.** Điều đó có thể để lại dữ liệu đã xử lý một phần trong khi changeset chưa được ghi lịch sử thành công.

### 16.2. DATABASECHANGELOG

Liquibase ghi lịch sử changeset đã thực hiện trong **DATABASECHANGELOG**. Mỗi changeset được nhận diện bởi **id, author và đường dẫn changelog** (hoặc logicalFilePath). Hành vi kiểm tra checksum giúp phát hiện những thay đổi nhất định ở nội dung changeset đã triển khai.

Hệ quả:

- Không chỉnh sửa một changeset đã chạy chỉ để đổi mã tham chiếu hoặc cách backfill.
- Nếu trạng thái nghiệp vụ cần thay đổi, viết changeset mới.
- Không dùng **clear-checksums** để che giấu việc sửa lịch sử.
- Không coi việc một changeset được đánh dấu EXECUTED là bằng chứng tất cả các bất biến nghiệp vụ đã đúng; phải có hậu kiểm dữ liệu.
- Nếu một migration chạy ngoài transaction thất bại giữa chừng, kiểm tra database thực tế và lịch sử trước khi retry.

### 16.3. DATABASECHANGELOGLOCK

**DATABASECHANGELOGLOCK** được Liquibase sử dụng để phối hợp các tiến trình cập nhật schema của Liquibase. Nó không ngăn người dùng hoặc dịch vụ khác tiếp tục ghi dữ liệu nghiệp vụ trong suốt backfill, cũng không thay thế chiến lược đồng bộ dữ liệu khi rolling deployment.

## 17. Rollback: ba nhóm cần ba tư duy khác nhau

| Nhóm thay đổi | Rollback có thể làm gì | Điều phải kiểm tra |
|---|---|---|
| Lược đồ | Drop bảng/cột hoặc thay đổi constraint ngược lại | Có mất dữ liệu, ảnh hưởng FK, index, ứng dụng cũ không? |
| Tham chiếu | Xóa hoặc khôi phục mã/nhãn đã cập nhật | Dữ liệu nghiệp vụ đã tham chiếu mã mới chưa? Có làm đứt FK không? |
| Nghiệp vụ | Phục hồi giá trị cũ từ nguồn xác thực, bảng đối soát hoặc backup | Có biết chính xác giá trị trước, có giao dịch mới phát sinh, có được phép ghi đè không? |

Ví dụ, một changeset thêm mã PAID có thể rollback bằng DELETE theo mã; nhưng sau khi hàng triệu đơn hàng đã tham chiếu PAID, xóa mã đó không còn là thao tác an toàn. Tương tự, rollback một cột mới có thể xóa dữ liệu mới đã được ứng dụng ghi vào cột.

Trong nhiều chuyển đổi dữ liệu nghiệp vụ, **forward fix** (thêm migration sửa tiếp theo) an toàn hơn “đảo ngược toàn bộ”, bởi những giao dịch thực phát sinh sau thời điểm triển khai không thể đơn giản bị xóa.

Cần phân biệt:

- **Transaction rollback:** hoàn tác phần chưa commit trong một giao dịch khi database hỗ trợ.
- **Liquibase rollback:** chạy các thao tác hoàn tác của changeset đã được áp dụng theo mốc triển khai.
- **Phục hồi nghiệp vụ:** đưa dữ liệu thực về trạng thái đúng mà vẫn giữ tính toàn vẹn của giao dịch; có thể cần backup, sự kiện gốc và đối soát độc lập.

Một rollback DDL thành công **không đồng nghĩa** dữ liệu nghiệp vụ được khôi phục hoàn toàn.

## 18. Dựng database mới và nâng cấp database cũ là hai bài kiểm thử

Để kiểm tra migration có thể tái tạo, cần thử hai đường đi:

### Đường A: database mới

- Chạy toàn bộ changelog từ điểm khởi tạo theo thứ tự.
- Xác nhận bảng, cột, khóa, index và dữ liệu tham chiếu chuẩn được tạo.
- Kiểm tra không cần phụ thuộc vào dữ liệu nghiệp vụ của môi trường khác.
- Không tự nạp dữ liệu cá nhân, thông tin khách hàng thật hoặc secret.
- Kiểm tra các bảng tham chiếu có mã/nhãn đúng.

### Đường B: database có lịch sử và dữ liệu

- Tạo bản sao hoặc môi trường thử nghiệm từ phiên bản cũ có **DATABASECHANGELOG** phù hợp.
- Có dữ liệu nghiệp vụ mô phỏng đúng các trường hợp bình thường và ngoại lệ.
- Chạy các changeset nâng cấp, backfill và constraint.
- Kiểm tra dữ liệu cũ không mất, không ghi đè thay đổi hợp lệ, không tăng số lượng dòng bất thường.
- Thử chạy lại quy trình theo cơ chế được thiết kế và đối chiếu kết quả.

Chỉ kiểm thử database mới thường **không phát hiện được** các vấn đề chuyển đổi dữ liệu cũ, vì database rỗng không có bản ghi sai hoặc phát sinh cạnh tranh. Chỉ kiểm thử database cũ có sẵn cũng có thể bỏ sót dependency cần thiết để dựng hệ thống mới từ đầu.

## 19. Spring Boot và CI/CD: phân ranh giới trách nhiệm

Cấu hình Spring Boot sử dụng Liquibase có thể như sau:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
~~~

Nếu ứng dụng chạy nhiều instance hoặc nhiều phiên bản trong rolling deployment, cần thống nhất ai được phép thực thi migration. Một lựa chọn thường dễ kiểm soát là **job CI/CD chuyên trách** áp dụng changelog và đối soát dữ liệu trước khi các phiên bản ứng dụng mới sử dụng cấu trúc mới.

Trình tự kiểm chứng điển hình khi đã cấu hình DB và changelog:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
liquibase update
liquibase history
~~~

Trong đó:

- **validate:** phát hiện những vấn đề Liquibase có thể kiểm tra trước khi chạy.
- **status:** quan sát changeset còn chờ.
- **update-sql:** review SQL dự kiến, nhất là DML có khả năng ảnh hưởng nhiều bản ghi.
- **update:** áp dụng migration theo điều kiện và lịch sử hiện tại.
- **history:** đối chiếu lịch sử Liquibase đã ghi nhận.

**Các lệnh trên không tự xác nhận quy tắc nghiệp vụ.** CI/CD cần bổ sung truy vấn kiểm tra số dòng, danh sách mã tham chiếu, khóa ngoại, số ngoại lệ và kết quả backfill. Đối với dữ liệu lớn, job chuyển đổi riêng cần có health metrics và điều kiện hoàn tất trước khi chạy bước contract.

### Phân quyền đề xuất

- **Schema owner:** review DDL, compatibility, lock, index và constraint.
- **Reference data owner:** review mã, ý nghĩa, quy tắc thêm/ngừng sử dụng mã.
- **Business data owner:** phê duyệt ánh xạ, xử lý ngoại lệ và đối soát.
- **Release owner:** kiểm soát thứ tự, môi trường, cửa sổ triển khai và quyền rollback.
- **CI/CD:** lưu bằng chứng SQL, trạng thái migration và kết quả kiểm chứng.

## 20. Sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách khắc phục |
|---|---|---|
| Gọi mọi INSERT là “seed” | Có thể ghi đè dữ liệu nghiệp vụ thật | Phân loại theo ownership và nguồn sự thật |
| Xóa rồi nạp lại toàn bộ bảng tham chiếu | Có thể phá khóa ngoại hoặc xóa giá trị tùy biến | Mã ổn định, thay đổi theo version, update có điều kiện |
| Trộn DDL và UPDATE hàng triệu dòng trong một changeset | Khó kiểm soát transaction, lock và phục hồi | Tách DDL, data migration, hậu kiểm; batching khi cần |
| Thêm NOT NULL trước backfill | Database cũ có NULL nên lỗi migration | Expand trước, backfill, hậu kiểm, contract sau |
| Tự gán giá trị không nhận diện thành default | Có thể làm sai trạng thái thanh toán/hóa đơn | HALT, báo ngoại lệ và xử lý với chủ dữ liệu |
| Tin rằng status EXECUTED là dữ liệu đã đúng | Lịch sử không thay thế kiểm chứng nghiệp vụ | Đối soát count, mapping và dữ liệu thực |
| Coi rollback DELETE là an toàn | Có thể xóa mã đã được đơn hàng tham chiếu | Xác định phụ thuộc, cân nhắc forward fix |
| Dùng MARK_RAN khi dữ liệu chưa chuyển xong | Che giấu bước migration thiếu | Chỉ ghi nhận khi trạng thái tương đương được chứng minh |
| Backfill không quan tâm ghi đồng thời | Bỏ sót hoặc ghi đè thay đổi mới | Dual-write, checkpoint, điều kiện update, hậu kiểm |
| Seed test vào production | Sinh dữ liệu giả hoặc cấu hình sai | Context/label phù hợp, môi trường test cô lập |
| Sửa changeset đã chạy để “chữa nhanh” | Checksum và lịch sử bị mất nhất quán | Tạo changeset mới, kiểm tra trên DB có lịch sử |

## 21. Bài tập tổng hợp: chuẩn hóa trạng thái đơn hàng

### Đề bài

Hệ thống đang có 1,5 triệu đơn hàng trong bảng purchase_order. Cột status_text chứa các giá trị NEW, New, PAID, Paid, CANCELLED và một số giá trị UNKNOWN. Sản phẩm muốn:

1. Có bảng order_status được quản lý như dữ liệu tham chiếu.
2. Mỗi đơn hàng có status_code tham chiếu đúng mã chuẩn.
3. Ứng dụng không bị dừng hoàn toàn trong quá trình backfill.
4. Không tự chuyển UNKNOWN thành NEW.
5. Sau khi chuyển xong, cột status_code phải NOT NULL và có FOREIGN KEY.
6. Có khả năng giải thích và đối soát những gì đã thay đổi.

### Hướng thiết kế

**Phần lược đồ:** tạo order_status, thêm status_code nullable, chuẩn bị index nếu cần, cuối cùng bổ sung FK và NOT NULL sau khi dữ liệu đã hợp lệ.

**Phần tham chiếu:** seed đúng ba mã NEW, PAID, CANCELLED; không tái sử dụng mã với ý nghĩa khác. Nếu cần tên hiển thị đa ngôn ngữ, xem xét cấu trúc dịch riêng thay vì thay mã.

**Phần nghiệp vụ:** thống kê giá trị status_text; ánh xạ các biến thể đã được chủ dữ liệu xác nhận; đưa UNKNOWN vào danh sách ngoại lệ; backfill theo lô; đồng bộ với bản ghi mới phát sinh; đối soát số lượng bản ghi chưa chuyển và sai ánh xạ.

**Phần vận hành:** thử trên bản sao database có dữ liệu tương đương; review SQL; giám sát lock và hiệu năng; dừng bước contract nếu còn ngoại lệ chưa giải quyết.

**Phần rollback:** có kế hoạch giữ status_text trong thời gian tương thích; không tự xóa mã tham chiếu khi đơn hàng đã sử dụng; nếu không thể rollback an toàn, xác định trước cách forward fix.

### Câu hỏi tự kiểm tra

1. Bảng order_status thuộc nhóm nào? **Bảng và constraint thuộc lược đồ; các dòng mã là dữ liệu tham chiếu.**
2. 1,5 triệu trạng thái đơn hàng thuộc nhóm nào? **Dữ liệu nghiệp vụ.**
3. Chỉ dùng loadData để chèn lại toàn bộ đơn hàng có phù hợp không? **Không**, vì đó là dữ liệu thực có ownership và lịch sử.
4. Dùng onFail: MARK_RAN khi còn bản ghi UNKNOWN có đúng không? **Không**, vì chưa đạt trạng thái dữ liệu mong muốn.
5. Có thể thêm NOT NULL trước khi hoàn tất backfill không? **Không nên**, vì dữ liệu cũ hoặc dữ liệu đang được ghi có thể chưa có status_code.
6. Nếu một đơn hàng chuyển thành PAID trong lúc backfill, cần bảo vệ điều gì? **Không ghi đè thay đổi mới bằng snapshot cũ; có chiến lược đồng bộ và đối soát.**
7. Một bản ghi DATABASECHANGELOG chứng minh điều gì? **Liquibase đã ghi nhận kết quả xử lý changeset; không tự chứng minh mọi quy tắc nghiệp vụ đều đạt.**

## 22. Checklist ra quyết định trước migration

- [ ] Đã phân loại rõ thay đổi: schema, reference data hay business data.
- [ ] Đã xác định owner và nguồn sự thật cho từng loại dữ liệu.
- [ ] Đã xem xét dữ liệu tham chiếu có mã ổn định và được phép thay đổi thế nào.
- [ ] Không trộn dữ liệu mẫu, secret hoặc cấu hình vận hành vào dữ liệu chuẩn production.
- [ ] DDL và DML có changeset hoặc bước vận hành riêng phù hợp.
- [ ] Đã xác định thứ tự include/changelog, phụ thuộc giữa bảng tham chiếu và bảng nghiệp vụ.
- [ ] Đã kiểm tra dữ liệu đầu vào, các giá trị bất thường và quy tắc ánh xạ.
- [ ] Đã lựa chọn một trong transaction ngắn, backfill theo lô hoặc job riêng theo quy mô.
- [ ] Đã đánh giá concurrency và cơ chế tránh ghi đè bản ghi mới.
- [ ] Đã có tiêu chí nghiệm thu bằng truy vấn hoặc báo cáo đối soát.
- [ ] Đã kiểm tra trên database mới và database có lịch sử.
- [ ] Đã review validate, status, update-sql và SQL rollback/forward fix.
- [ ] Đã dự phòng rủi ro mất dữ liệu, phụ thuộc FK, lock và downtime.
- [ ] Chỉ bước contract được triển khai khi dữ liệu và ứng dụng đã tương thích.
- [ ] Không sửa changeset cũ để thay đổi lịch sử đã chạy.

## 23. Ghi nhớ

**Lược đồ** định nghĩa cấu trúc và các bất biến của database. **Dữ liệu tham chiếu** là tập mã/giá trị chuẩn được quản lý như hợp đồng của ứng dụng. **Dữ liệu nghiệp vụ** là sự thật phát sinh từ vận hành, thường không thể xóa hoặc dựng lại tùy tiện.

Liquibase phù hợp để quản lý lịch sử thay đổi của cả schema và những cập nhật dữ liệu được version hóa, nhưng **cách thực hiện phải phụ thuộc loại dữ liệu**. Với bảng lớn, dữ liệu đang ghi liên tục và yêu cầu kiểm toán nghiêm ngặt, hãy tách backfill thành quy trình có checkpoint, idempotency và đối soát, thay vì trông chờ một changeset lớn giải quyết tất cả.

Khả năng triển khai an toàn được quyết định bởi **phân loại đúng, ownership rõ, thứ tự migration hợp lý, dữ liệu được kiểm chứng, cách phục hồi khả thi và tương thích giữa các phiên bản ứng dụng** — không chỉ bởi việc Liquibase báo changeset đã thực thi.
