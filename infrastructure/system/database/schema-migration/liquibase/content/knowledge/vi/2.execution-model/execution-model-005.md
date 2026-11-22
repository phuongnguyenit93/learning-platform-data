# Thứ tự khai báo, thứ tự thực thi và phụ thuộc giữa thay đổi

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, Liquibase quản lý thay đổi schema và dữ liệu thông qua changelog và changeset. Mô tả module nhấn mạnh việc dùng precondition, checksum và lịch sử triển khai, kiểm chứng migration, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Những năng lực này phụ thuộc trực tiếp vào việc kiểm soát đúng thứ tự: bảng phải tồn tại trước khi tạo khóa ngoại, cấu trúc phải sẵn sàng trước khi nạp dữ liệu, và ứng dụng phải tương thích với schema tại từng giai đoạn triển khai.

Liquibase thực thi changelog theo một trình tự xác định. Tuy nhiên, công cụ không tự suy luận toàn bộ quan hệ nghiệp vụ giữa các thay đổi. Người thiết kế migration cần khai báo trình tự hợp lý, biểu diễn điều kiện tiên quyết và bảo đảm các bộ lọc môi trường không làm mất một bước phụ thuộc.

## 1. Phân biệt thứ tự khai báo, điều kiện chạy và thứ tự thực thi

Ba khái niệm này liên quan với nhau nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Thứ tự khai báo | Vị trí của changelog hoặc changeset trong cây changelog | File tạo bảng được include trước file tạo khóa ngoại |
| Điều kiện chạy | Một changeset có đủ điều kiện được thực thi trong lần cập nhật hiện tại hay không | Changeset dành cho PostgreSQL chỉ chạy trên PostgreSQL; changeset có context `test` chỉ chạy khi context đó được chọn |
| Thứ tự thực thi | Trình tự Liquibase xử lý các changeset đủ điều kiện và chưa được ghi nhận trong lịch sử | Tạo bảng khách hàng, tạo bảng đơn hàng, sau đó tạo khóa ngoại |

Một changeset được khai báo trước vẫn có thể không chạy nếu bị loại bởi `dbms`, context, label hoặc precondition. Một changeset đã chạy thành công thường được bỏ qua ở các lần `update` tiếp theo vì Liquibase đã ghi nhận nó trong cơ sở dữ liệu. Do đó, khi đọc changelog cần xem đồng thời vị trí khai báo, bộ lọc áp dụng và lịch sử triển khai.

Liquibase xử lý các changeset theo trình tự changelog, không phải một bộ lập lịch tự xây dựng đồ thị phụ thuộc từ tên bảng, tên cột hay nội dung SQL. Nếu thay đổi B cần kết quả của thay đổi A, người viết phải bảo đảm A được thực thi trước B và phải kiểm tra điều kiện đó khi cần.

## 2. Liquibase xác định trình tự từ cây changelog

### 2.1. Changelog gốc và các file được include

Một changelog gốc thường đóng vai trò điểm vào của migration. Khi gặp các lệnh `include`, Liquibase xử lý các file theo thứ tự chúng xuất hiện trong changelog gốc. Bên trong mỗi file, các changeset tiếp tục được xử lý theo thứ tự khai báo.

Ví dụ, changelog gốc có thể khai báo:

```yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-create-orders.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/003-add-orders-customer-fk.yaml
      relativeToChangelogFile: true
```

Trình tự trên thể hiện rõ ba bước: tạo bảng `customer`, tạo bảng `orders`, rồi tạo khóa ngoại từ `orders.customer_id` đến `customer.id`. Với các phụ thuộc quan trọng, danh sách `include` tường minh giúp người đọc nhận ra thứ tự dự kiến ngay tại changelog gốc.

Nếu dùng `includeAll`, Liquibase mặc định xử lý các file được tìm thấy theo thứ tự chữ cái. Vì vậy, cách đặt tên file có ảnh hưởng đến trình tự. Tiền tố số như `001-`, `002-`, `003-` giúp thứ tự dễ nhìn và ổn định hơn. Không nên dựa vào thời điểm file được tạo hoặc sửa để quyết định thứ tự migration. Khi thứ tự là một phần quan trọng của thiết kế, danh sách `include` tường minh thường dễ kiểm tra hơn `includeAll`.

Trong một file changelog, các changeset được xử lý theo thứ tự khai báo. Các change bên trong một changeset cũng được thực hiện theo thứ tự xuất hiện. Thuộc tính `runOrder` với giá trị `first` hoặc `last` có thể điều chỉnh vị trí chạy của một changeset trong những trường hợp đặc biệt. Đây là công cụ điều chỉnh thứ tự, không phải cơ chế mô tả quan hệ phụ thuộc tổng quát; chỉ nên dùng khi lý do và tác động của nó được ghi rõ.

### 2.2. Changeset và lịch sử triển khai

Changeset là đơn vị Liquibase theo dõi trong lịch sử. Danh tính của một changeset được xác định từ tổ hợp:

- `id`: mã changeset do nhóm phát triển đặt.
- `author`: tác giả hoặc định danh nhóm chịu trách nhiệm.
- Đường dẫn changelog: vị trí logic của changeset trong hệ thống changelog.

Liquibase ghi nhận các changeset đã thực thi trong bảng `DATABASECHANGELOG`, bao gồm thông tin nhận diện, checksum, thời điểm và thứ tự thực thi. Khi chạy `update`, Liquibase đối chiếu changelog với lịch sử này để tìm các changeset còn thiếu. Những changeset đã được ghi nhận hợp lệ sẽ được bỏ qua; các changeset mới đủ điều kiện được xử lý theo thứ tự changelog.

Bảng `DATABASECHANGELOGLOCK` giúp điều phối việc cập nhật để tránh nhiều tiến trình Liquibase đồng thời thay đổi cùng một cơ sở dữ liệu. Cơ chế khóa này hữu ích khi nhiều instance ứng dụng khởi động gần như cùng lúc, nhưng pipeline vẫn nên có một bước migration tập trung để trình tự triển khai dễ kiểm soát.

Checksum giúp Liquibase phát hiện nội dung changeset đã thay đổi sau khi được áp dụng. Vì vậy, không nên sửa hoặc sắp xếp lại nội dung của changeset đã triển khai ở môi trường dùng chung hoặc production. Nếu cần thay đổi schema hay dữ liệu, hãy tạo changeset mới có thứ tự tiếp nối. Khi di chuyển hoặc đổi tên file changelog, cần xem xét `logicalFilePath` để duy trì danh tính logic của các changeset đã có lịch sử.

## 3. Biểu diễn quan hệ phụ thuộc giữa các thay đổi

### 3.1. Xác định điều kiện tiên quyết

Một thay đổi phụ thuộc vào thay đổi khác khi nó chỉ hợp lệ sau khi kết quả của thay đổi trước đã tồn tại. Một số ví dụ thường gặp:

| Thay đổi phía sau | Điều kiện tiên quyết | Trình tự phù hợp |
|---|---|---|
| Tạo khóa ngoại | Hai bảng và các cột tham chiếu đã tồn tại | Tạo bảng trước, thêm khóa ngoại sau |
| Nạp dữ liệu tham chiếu | Bảng đích và các cột cần ghi đã tồn tại | Tạo cấu trúc trước, insert dữ liệu sau |
| Tạo index | Bảng và các cột index đã tồn tại | Tạo bảng/cột trước, tạo index sau |
| Đặt cột thành NOT NULL | Dữ liệu hiện tại không còn giá trị NULL | Thêm cột, backfill, kiểm tra dữ liệu, sau đó đặt NOT NULL |
| Xóa bảng hoặc cột cũ | Ứng dụng và các đối tượng phụ thuộc đã ngừng sử dụng | Chuyển ứng dụng, xác nhận an toàn, rồi mới xóa |

Có thể biểu diễn các quan hệ này thành đồ thị có hướng. Nếu B cần A, ta có cạnh A → B. Một trình tự migration hợp lệ phải đặt các nút trước các nút phụ thuộc vào chúng; trong lý thuyết đồ thị, đây là thứ tự topo. Nếu xuất hiện vòng phụ thuộc, cần tách thay đổi thành các giai đoạn nhỏ hơn. Ví dụ, có thể tạo cả hai bảng trước, sau đó mới thêm hai khóa ngoại tham chiếu chéo.

### 3.2. Ví dụ: tạo bảng trước khi thêm khóa ngoại

Changeset thứ nhất tạo bảng khách hàng:

```yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: platform
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
                  name: name
                  type: varchar(200)
                  constraints:
                    nullable: false
```

Changeset thứ hai tạo bảng đơn hàng với cột chứa mã khách hàng:

```yaml
databaseChangeLog:
  - changeSet:
      id: 002-create-orders
      author: platform
      changes:
        - createTable:
            tableName: orders
            columns:
              - column:
                  name: id
                  type: bigint
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: customer_id
                  type: bigint
                  constraints:
                    nullable: false
```

Changeset thứ ba thêm khóa ngoại. Precondition kiểm tra các đối tượng cần thiết và dừng migration nếu điều kiện không thỏa mãn:

```yaml
databaseChangeLog:
  - changeSet:
      id: 003-add-orders-customer-fk
      author: platform
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: customer
        - tableExists:
            tableName: orders
        - columnExists:
            tableName: orders
            columnName: customer_id
      changes:
        - addForeignKeyConstraint:
            baseTableName: orders
            baseColumnNames: customer_id
            referencedTableName: customer
            referencedColumnNames: id
            constraintName: fk_orders_customer
      rollback:
        - dropForeignKeyConstraint:
            baseTableName: orders
            constraintName: fk_orders_customer
```

Ba changeset phải nằm theo đúng thứ tự trong cùng changelog hoặc được include theo thứ tự tương ứng. Precondition ở changeset thứ ba là lớp kiểm tra bổ sung: nó giúp phát hiện trạng thái cơ sở dữ liệu không đáp ứng điều kiện trước khi thêm khóa ngoại.

Precondition không thay thế việc sắp xếp changeset. Nếu changeset tạo bảng khách hàng chưa được khai báo hoặc bị bỏ qua bởi một bộ lọc, precondition không tự tìm và chạy changeset đó. Nó chỉ đánh giá trạng thái hiện tại rồi áp dụng hành vi đã cấu hình.

### 3.3. Chọn hành vi khi precondition không đạt

Precondition có thể đặt ở cấp changelog hoặc changeset. Với changeset, các lựa chọn thường dùng cho `onFail` gồm:

- `HALT`: dừng cập nhật. Phù hợp khi thiếu điều kiện tiên quyết khiến thay đổi tiếp theo không an toàn.
- `CONTINUE`: bỏ qua changeset trong lần cập nhật hiện tại; changeset chưa được đánh dấu là đã chạy nên có thể được thử lại ở lần sau.
- `MARK_RAN`: ghi nhận changeset như đã chạy dù các thay đổi của nó không được thực thi. Chỉ dùng khi trạng thái hiện tại đã tương đương với kết quả mong muốn.
- `WARN`: ghi cảnh báo và tiếp tục theo hành vi được cấu hình.

`onError` xử lý tình huống có lỗi khi đánh giá precondition, còn `onFail` xử lý trường hợp điều kiện được đánh giá nhưng không đạt. Cần chọn hành vi dựa trên ý nghĩa dữ liệu. Ví dụ, nếu bảng khách hàng chưa tồn tại thì dùng `MARK_RAN` cho changeset thêm khóa ngoại sẽ tạo ra lịch sử sai: Liquibase có thể coi bước thêm khóa ngoại đã hoàn tất dù quan hệ đó chưa tồn tại. Với điều kiện tiên quyết bắt buộc, `HALT` thường là lựa chọn an toàn.

## 4. Bộ lọc môi trường có thể làm thay đổi tập changeset được chạy

Liquibase có thể giới hạn changeset theo cơ sở dữ liệu, context hoặc label. Đây là cách chia sẻ changelog giữa các môi trường và tình huống triển khai, nhưng bộ lọc cũng có thể làm mất một mắt xích trong chuỗi phụ thuộc.

Ví dụ, changeset tạo bảng được gắn context `dev`, trong khi changeset thêm khóa ngoại không có context. Khi chạy ở production mà chỉ chọn context production, bước tạo bảng có thể bị bỏ qua nhưng bước thêm khóa ngoại vẫn đủ điều kiện chạy. Kết quả là migration thất bại vì thiếu bảng.

Khi thiết kế bộ lọc, cần bảo đảm:

1. Các changeset tạo điều kiện tiên quyết và changeset sử dụng điều kiện đó có phạm vi môi trường tương thích.
2. Không gắn context hoặc label chỉ vào bước nền tảng nếu các bước phía sau vẫn có thể chạy độc lập.
3. Dùng thuộc tính `dbms` khi thay đổi thực sự dành riêng cho một hệ quản trị cơ sở dữ liệu.
4. Kiểm tra tập changeset được chọn ở từng môi trường bằng cấu hình context, label và database thực tế của môi trường đó.

Các thuộc tính `runAlways` và `runOnChange` cũng ảnh hưởng đến việc một changeset có được thực thi lại hay không. `runAlways` yêu cầu chạy lại mỗi lần cập nhật; `runOnChange` cho phép chạy lại khi checksum thay đổi. Chúng hữu ích cho một số đối tượng có tính chất lặp lại, chẳng hạn view hoặc stored procedure. Không nên dùng chúng như cách sửa thứ tự cho migration cấu trúc thông thường, vì chúng thay đổi quy tắc thực thi lại và có thể khiến tác động được lặp lại.

## 5. Thiết kế chuỗi migration dễ triển khai và bảo trì

### 5.1. Chia nhỏ theo bước có ý nghĩa

Mỗi changeset nên đại diện cho một thay đổi có thể giải thích, kiểm tra và rollback. Có thể gom các thao tác luôn cần thực hiện cùng nhau, nhưng tránh tạo một changeset quá lớn chứa nhiều bước độc lập. Khi lỗi xảy ra, changeset nhỏ giúp xác định điểm thất bại và đánh giá trạng thái còn lại dễ hơn.

Với thay đổi dữ liệu, trình tự phổ biến là:

1. Thêm cột mới ở trạng thái tương thích với dữ liệu hiện có.
2. Triển khai mã ứng dụng có thể đọc hoặc ghi theo cấu trúc mới.
3. Backfill dữ liệu cũ theo lô nếu khối lượng lớn.
4. Kiểm tra số lượng bản ghi và các bất biến dữ liệu.
5. Áp dụng ràng buộc như NOT NULL hoặc UNIQUE khi dữ liệu đã đạt yêu cầu.
6. Chỉ xóa cột hoặc cấu trúc cũ sau khi ứng dụng không còn phụ thuộc.

Cách triển khai mở rộng rồi thu hẹp này giúp giảm rủi ro khi ứng dụng và schema không được cập nhật cùng một thời điểm.

### 5.2. Giữ changelog ổn định

Một changelog có lịch sử triển khai cần được xem như lịch sử phiên bản. Không đổi thứ tự các changeset đã áp dụng để làm cho file trông gọn hơn; không tái sử dụng `id` cho một mục đích khác; không sửa nội dung đã triển khai chỉ để sửa lỗi. Hãy thêm changeset mới để điều chỉnh kết quả trước đó.

Với `includeAll`, việc thêm file mới có tên đứng trước các file cũ có thể làm thay đổi vị trí khai báo khi đọc toàn bộ changelog. Liquibase vẫn đối chiếu lịch sử để bỏ qua changeset đã chạy, nhưng thay đổi cấu trúc thứ tự làm tài liệu khó hiểu và tăng rủi ro khi có môi trường chưa đồng bộ. Hãy đặt tên có tiền tố thứ tự nhất quán hoặc chuyển sang `include` tường minh khi cần kiểm soát chặt.

Nếu một changeset đã chạy ở môi trường A nhưng chưa chạy ở môi trường B, việc sửa hoặc di chuyển file có thể khiến hai môi trường nhìn thấy danh tính hoặc checksum khác nhau. Trước khi thay đổi cấu trúc changelog, hãy kiểm tra lịch sử triển khai của các môi trường liên quan và giữ ổn định đường dẫn logic.

### 5.3. Chú ý transaction và trạng thái lỗi

Liquibase mặc định cố gắng thực thi changeset trong transaction khi hệ quản trị cơ sở dữ liệu và loại thao tác hỗ trợ. Tuy nhiên, khả năng rollback DDL khác nhau giữa các hệ quản trị cơ sở dữ liệu. Một số lệnh DDL có thể tự commit hoặc không thể rollback như thao tác DML thông thường.

Vì vậy, không nên giả định rằng mọi câu lệnh trong một changeset luôn được hoàn tác nguyên tử trên mọi database. Với thao tác không hỗ trợ transaction, hãy chia nhỏ thay đổi, thiết kế bước chạy lại an toàn và có phương án phục hồi cụ thể. Chỉ đặt `runInTransaction: false` khi có lý do kỹ thuật rõ ràng; changeset gồm nhiều câu lệnh khi chạy ngoài transaction có thể để lại trạng thái một phần nếu câu lệnh giữa chừng thất bại.

## 6. Rollback tuân theo quan hệ ngược của trình tự triển khai

Khi các thay đổi có phụ thuộc, rollback cần gỡ các thành phần phụ thuộc trước. Nếu migration tạo bảng khách hàng, tạo bảng đơn hàng rồi thêm khóa ngoại, trình tự rollback hợp lý là xóa khóa ngoại trước, sau đó mới xóa các bảng. Liquibase rollback theo thứ tự ngược với các changeset được áp dụng trong phạm vi rollback.

Nên khai báo rollback tường minh cho các thay đổi cần hoàn tác, đặc biệt khi Liquibase không thể tự suy ra thao tác ngược hoặc khi thay đổi dữ liệu có ý nghĩa nghiệp vụ. Ví dụ:

```yaml
rollback:
  - delete:
      tableName: feature_flag
      where: key = 'new-checkout'
```

Đoạn rollback trên chỉ phù hợp nếu bản ghi được tạo bởi changeset đó và điều kiện `where` xác định chính xác dữ liệu cần xóa. Với dữ liệu người dùng hoặc thao tác biến đổi không thể đảo ngược, rollback kỹ thuật không thể tự khôi phục thông tin đã mất. Cần cân nhắc backup, bảng lưu tạm, thao tác bù hoặc quy trình phục hồi riêng.

Các lệnh thường dùng để kiểm tra và thực thi gồm:

```bash
liquibase validate
liquibase status --verbose
liquibase update-sql
liquibase update
```

Sau khi đã áp dụng migration, có thể dùng các lệnh rollback phù hợp với chiến lược đã chuẩn bị, chẳng hạn `rollback-count` để hoàn tác một số changeset gần nhất hoặc rollback theo tag. Hãy kiểm tra đúng database, tag và số changeset trước khi thực thi. Rollback theo số lượng dựa trên lịch sử thực tế của database đó; hai môi trường có lịch sử khác nhau có thể cần số bước rollback khác nhau.

## 7. Phối hợp thứ tự migration với Spring Boot và CI/CD

### 7.1. Spring Boot

Khi tích hợp Liquibase vào Spring Boot, dependency `liquibase-core` và cấu hình changelog cho phép ứng dụng khởi chạy migration theo cấu hình. Ví dụ:

```yaml
spring:
  liquibase:
    change-log: classpath:db/changelog/db.changelog-master.yaml
    contexts: production
```

Đường dẫn `change-log` xác định changelog gốc. Context cần được chọn có chủ đích theo môi trường; nếu dùng context để phân loại changeset, hãy kiểm tra rằng các bước phụ thuộc vẫn được chọn đồng bộ. Cấu hình ứng dụng không thay thế việc thiết kế thứ tự trong changelog.

Trong hệ thống có nhiều instance Spring Boot, không nên để mỗi instance trở thành một nơi khó dự đoán để triển khai migration. Liquibase có cơ chế khóa ở database để điều phối cập nhật đồng thời, nhưng một migration job riêng trong pipeline giúp xác định rõ thời điểm schema được cập nhật và giúp kiểm tra kết quả trước khi mở rộng số lượng instance ứng dụng.

### 7.2. CI/CD

Một pipeline triển khai có thể tổ chức theo trình tự:

1. Kiểm tra changelog và cấu hình bằng `liquibase validate`.
2. Chọn đúng thông tin kết nối và bộ lọc của môi trường đích.
3. Xem các changeset còn pending bằng `liquibase status --verbose`.
4. Sinh SQL dự kiến bằng `liquibase update-sql` và review các thao tác có tác động lớn.
5. Chạy migration bằng `liquibase update` trong một bước triển khai được kiểm soát.
6. Xác nhận lịch sử trong `DATABASECHANGELOG` và kiểm tra các đối tượng hoặc dữ liệu quan trọng.
7. Triển khai phiên bản ứng dụng tương thích với schema vừa cập nhật.
8. Theo dõi ứng dụng và chỉ thực hiện giai đoạn thu hẹp schema khi không còn phiên bản cũ phụ thuộc.

Với chiến lược triển khai nhiều phiên bản ứng dụng, migration nên ưu tiên tương thích ngược trong giai đoạn đầu. Ví dụ, thêm cột mới trước khi ứng dụng bắt đầu sử dụng; chỉ xóa cột cũ sau khi mọi instance đã chuyển sang cấu trúc mới. Điều này giúp giảm khoảng thời gian mà ứng dụng đọc một schema chưa sẵn sàng hoặc ghi vào một cấu trúc đã bị xóa.

Cùng một bộ changelog nên được kiểm tra và triển khai theo cùng quy trình ở các môi trường. Khác biệt môi trường nên được quản lý bằng cấu hình kết nối và bộ lọc có chủ đích, không bằng cách chỉnh sửa thủ công lịch sử changeset của từng database. Trước khi triển khai production, cần xem SQL dự kiến, đánh giá thời gian khóa bảng, dung lượng dữ liệu, khả năng rollback và ảnh hưởng đến phiên bản ứng dụng đang chạy.

## 8. Chẩn đoán lỗi liên quan đến thứ tự

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Không tìm thấy bảng hoặc cột khi chạy changeset | Changeset tạo đối tượng chưa chạy, bị lọc hoặc đứng sau bước sử dụng nó | Kiểm tra thứ tự include, context, label, dbms và lịch sử |
| Khóa ngoại không tạo được | Bảng/cột tham chiếu chưa tồn tại hoặc dữ liệu vi phạm quan hệ | Kiểm tra schema, dữ liệu và precondition trước khi thêm constraint |
| Một changeset không chạy ở môi trường cụ thể | Changeset đã có trong lịch sử hoặc không thỏa bộ lọc/precondition | Kiểm tra `DATABASECHANGELOG`, context, label, dbms và trạng thái |
| Checksum không khớp | Nội dung changeset đã triển khai bị sửa | Khôi phục nội dung lịch sử hoặc tạo changeset mới; chỉ dùng `runOnChange` khi đó là chủ đích |
| Hai môi trường có trạng thái khác nhau | Lịch sử, bộ lọc hoặc phiên bản changelog khác nhau | So sánh lịch sử và cấu hình của từng môi trường trước khi tiếp tục |
| Migration bị chặn bởi lock | Một tiến trình Liquibase khác đang chạy hoặc lần chạy trước kết thúc bất thường | Xác minh tiến trình đang hoạt động và trạng thái database trước khi xử lý lock |

Khi điều tra, nên xác định changeset cuối cùng đã chạy thành công, changeset đầu tiên bị pending hoặc thất bại, rồi đối chiếu với các điều kiện tiên quyết của nó. Không xóa lịch sử hoặc sửa checksum chỉ để làm cho lệnh `update` chạy tiếp; các thao tác đó có thể che khuất trạng thái thực của schema. Nếu database đã được chỉnh sửa thủ công, cần đánh giá trạng thái hiện tại và tạo một changeset đồng bộ có kiểm chứng.

## 9. Checklist trước khi triển khai

- [ ] Changelog gốc trỏ đến đúng các file và thứ tự include thể hiện rõ phụ thuộc.
- [ ] Các file trong `includeAll` có quy tắc đặt tên ổn định và dễ xác định thứ tự.
- [ ] Mỗi changeset có `id`, `author` và đường dẫn logic ổn định.
- [ ] Thay đổi tạo đối tượng được đặt trước thay đổi sử dụng đối tượng đó.
- [ ] Preconditions kiểm tra đúng điều kiện và có hành vi `onFail` phù hợp.
- [ ] Context, label và dbms không vô tình loại bỏ một bước tiên quyết.
- [ ] Changeset đã triển khai được giữ nguyên; thay đổi mới được bổ sung bằng changeset tiếp theo.
- [ ] Rollback được xem xét theo thứ tự ngược và có phương án cho dữ liệu không thể đảo ngược.
- [ ] SQL dự kiến đã được review bằng `update-sql` ở đúng môi trường.
- [ ] Pipeline chạy migration có kiểm soát và xác nhận lịch sử trước khi triển khai ứng dụng.

Thứ tự changelog là hợp đồng triển khai của hệ thống. Khi thứ tự khai báo, điều kiện chạy, precondition và lịch sử database được thiết kế nhất quán, Liquibase có thể áp dụng migration có thể dự đoán qua nhiều môi trường; khi có phụ thuộc, mỗi bước đều có điều kiện rõ ràng và đường rollback được xem xét cùng với trình tự tiến lên.

