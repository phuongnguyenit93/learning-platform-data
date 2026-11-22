# Phân biệt phát hiện dữ liệu cũ với tự động giải quyết xung đột

Trong kiểm soát đồng thời lạc quan (*optimistic concurrency control*), nhiều giao dịch được phép đọc dữ liệu mà không giữ khóa độc quyền trong suốt thời gian xử lý. Khi một giao dịch muốn ghi, hệ thống kiểm tra xem dữ liệu có còn ở phiên bản mà giao dịch đã đọc hay không. Nếu phiên bản đã thay đổi, thao tác ghi bị từ chối để tránh ghi đè một cập nhật mới hơn.

Điểm cần phân biệt là: **phát hiện dữ liệu cũ chỉ cho biết giả định của giao dịch không còn đúng; nó không tự quyết định phải kết hợp hai thay đổi như thế nào**. Cơ sở dữ liệu có thể báo xung đột, hủy transaction hoặc trả về số hàng được cập nhật bằng `0`. Việc từ chối, tải lại, gộp, áp dụng lại hay yêu cầu người dùng chọn là chính sách của ứng dụng và nghiệp vụ.

Ví dụ, hai nhân viên cùng mở một tài liệu ở phiên bản `7`. Nhân viên A lưu trước và tạo phiên bản `8`. Khi nhân viên B lưu nội dung dựa trên phiên bản `7`, kiểm tra version phát hiện tài liệu đã thay đổi. Hệ thống có thể từ chối bản lưu của B, nhưng không thể tự biết B muốn giữ đoạn nào, chấp nhận nội dung của A hay kết hợp hai chỉnh sửa.

## 1. Dữ liệu cũ và xung đột ghi là gì?

Một **bản đọc cũ** (*stale read*) là dữ liệu mà ứng dụng đã lấy từ cơ sở dữ liệu nhưng không còn phản ánh phiên bản hiện tại tại thời điểm ứng dụng muốn ghi. Bản đọc có thể trở nên cũ khi một giao dịch khác cập nhật và commit sau lần đọc đó.

Một **xung đột ghi** xảy ra khi giao dịch muốn lưu dựa trên một trạng thái cũ trong khi dữ liệu liên quan đã được thay đổi. Nếu hệ thống chấp nhận ghi mù (*blind overwrite*), thay đổi mới hơn có thể bị ghi đè và gây lost update.

Ví dụ, bảng `documents` có một tài liệu:

| id | title | content | version |
|---:|---|---|---:|
| 42 | Quy trình hoàn tiền | Bản nội dung ban đầu | 7 |

Hai phiên làm việc cùng đọc hàng ở version `7`:

```text
Thời điểm 1:
    A đọc document 42, version = 7
    B đọc document 42, version = 7

Thời điểm 2:
    A sửa nội dung và lưu thành công
    Database lưu version = 8

Thời điểm 3:
    B gửi nội dung được sửa từ version = 7
    Database thấy version hiện tại là 8
    -> bản ghi của B dựa trên dữ liệu cũ
    -> thao tác cập nhật của B bị từ chối
```

Hệ thống đã phát hiện B đang ghi từ phiên bản cũ. Nó chưa giải quyết nội dung mà A và B cùng sửa.

### Bản đọc cũ chưa chắc đã tạo xung đột

Ứng dụng có thể đọc version `7`, sau đó một giao dịch khác tạo version `8`. Nếu ứng dụng chỉ hiển thị dữ liệu và không ghi lại, bản đọc cũ không tạo ra lost update. Vấn đề chỉ cần được xử lý khi ứng dụng định thực hiện hành động phụ thuộc vào dữ liệu cũ, chẳng hạn cập nhật, xác nhận, trừ tồn kho hoặc chuyển trạng thái.

Ngược lại, không phải mọi cập nhật đều xung đột. Hai giao dịch có thể cùng đọc một bảng nhưng ghi các hàng độc lập. Nếu version được quản lý theo từng hàng và các thay đổi không có bất biến liên hàng, cả hai có thể cập nhật thành công.

## 2. Phát hiện dữ liệu cũ bằng cột version

Một cách phổ biến là thêm cột số nguyên `version` hoặc `revision` vào hàng dữ liệu. Mỗi lần cập nhật thành công, version tăng lên.

Ví dụ schema:

```sql
CREATE TABLE documents (
    id BIGINT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);
```

Khi đọc, ứng dụng lấy cả nội dung và version:

```sql
SELECT id, title, content, version
FROM documents
WHERE id = 42;
```

Giả sử ứng dụng nhận `version = 7`. Khi lưu, ứng dụng gửi lại version mà nó đã đọc:

```sql
UPDATE documents
SET title = :newTitle,
    content = :newContent,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
```

`expectedVersion` là version mà ứng dụng giữ từ lần đọc trước. Câu lệnh chỉ cập nhật khi hàng vẫn có version đó. Phép kiểm tra và tăng version nằm trong cùng một câu lệnh nguyên tử của cơ sở dữ liệu.

### Đọc kết quả cập nhật

Ứng dụng kiểm tra số hàng bị ảnh hưởng:

| Số hàng cập nhật | Diễn giải |
|---:|---|
| `1` | Hàng tồn tại và version khớp. Cập nhật thành công; version tăng một đơn vị. |
| `0` | Không có hàng nào thỏa cả `id` và `version`. Hàng có thể đã bị xóa hoặc version đã thay đổi. |

Nếu câu lệnh cập nhật luôn tăng version như ví dụ, hàng khớp điều kiện sẽ thực sự thay đổi version và thường được tính là một hàng cập nhật. Nếu bỏ điều kiện version, hai lần ghi có thể lần lượt thành công và ghi đè nội dung của nhau.

Một kết quả bằng `0` không tự chứng minh rằng chỉ có xung đột version. Hàng cũng có thể không tồn tại, bị lọc bởi điều kiện bổ sung hoặc không còn thuộc phạm vi mà người dùng được phép sửa. Ứng dụng cần phân biệt các trường hợp theo quy tắc bảo mật và nghiệp vụ, tránh tiết lộ thông tin của hàng mà người dùng không được truy cập.

### Hai giao dịch cùng cập nhật

Giả sử A và B cùng đọc version `7`:

```sql
-- A
UPDATE documents
SET content = 'Nội dung do A sửa',
    version = version + 1
WHERE id = 42 AND version = 7;
-- row count = 1; version trở thành 8

-- B
UPDATE documents
SET content = 'Nội dung do B sửa',
    version = version + 1
WHERE id = 42 AND version = 7;
-- row count = 0; version hiện tại không còn là 7
```

Chỉ một cập nhật dựa trên version `7` có thể thắng. Nếu A và B chạy thực sự đồng thời, database có thể khiến một câu lệnh chờ khóa ghi của câu lệnh kia; sau đó điều kiện version được đánh giá theo trạng thái phù hợp và một câu lệnh không còn khớp. Chi tiết chờ và lỗi phụ thuộc engine, nhưng điều kiện version bảo vệ khỏi việc cả hai ghi mù trên cùng revision.

## 3. Vì sao phát hiện xung đột không tự giải quyết xung đột?

Version chỉ cho biết hàng đã thay đổi kể từ lần đọc mà ứng dụng dựa vào. Nó không chứa thông tin về ý định của người dùng hoặc quy tắc kết hợp các thay đổi.

Giả sử tài liệu có hai trường:

```text
title   = "Quy trình hoàn tiền"
content = "Hoàn tiền trong 7 ngày"
version = 7
```

A đổi `title` thành `"Chính sách hoàn tiền"`. B đổi `content` thành `"Hoàn tiền trong 14 ngày"`. Cả hai cùng đọc version `7`.

Sau khi A lưu thành công, version thành `8`. Khi B lưu theo version `7`, hệ thống từ chối. Đây là phản ứng an toàn, nhưng B không tự động được lưu chỉ vì B sửa một trường khác. Cột version ở cấp hàng phát hiện rằng hàng đã thay đổi; nó không tự xác định rằng hai chỉnh sửa là độc lập và có thể gộp.

Ứng dụng có thể chọn một trong nhiều chính sách:

- Từ chối và yêu cầu B tải lại rồi chỉnh sửa lại.
- Tự động gộp nếu có thể chứng minh các trường hoặc vùng nội dung độc lập.
- Áp dụng lại ý định của B lên phiên bản mới sau khi kiểm tra quy tắc nghiệp vụ.
- Yêu cầu người dùng xem bản khác biệt và chọn nội dung cần giữ.
- Dùng một phép cập nhật nguyên tử hoặc thao tác miền có tính kết hợp nếu nghiệp vụ cho phép.

Không có một chính sách đúng cho mọi loại dữ liệu. Ví dụ, tự động cộng số lượng có thể hợp lý cho một bộ đếm, nhưng tự động ghi đè số dư tài khoản hoặc quyết định phê duyệt có thể gây hậu quả nghiêm trọng.

## 4. Các chiến lược xử lý sau khi phát hiện xung đột

### Từ chối và yêu cầu người dùng tải lại

Đây là chiến lược đơn giản và an toàn cho dữ liệu mà con người chỉnh sửa. Khi version không khớp, ứng dụng thông báo rằng bản ghi đã được người khác cập nhật, tải phiên bản mới nhất và cho người dùng xem nội dung hiện tại trước khi quyết định tiếp.

Ví dụ thông báo:

```text
Không thể lưu thay đổi.
Tài liệu đã được cập nhật bởi một phiên làm việc khác.
Hãy tải lại dữ liệu, xem các thay đổi mới và thử lưu lại.
```

Ưu điểm là không tự ý chọn thay đổi của ai. Nhược điểm là người dùng phải làm lại một phần công việc, nhất là khi chỉnh sửa dài.

### Tải lại rồi áp dụng lại ý định

Với một thao tác nghiệp vụ có thể diễn tả rõ, ứng dụng có thể tải dữ liệu mới, kiểm tra điều kiện lại và thực hiện hành động trên trạng thái hiện tại.

Ví dụ, người dùng yêu cầu “tăng số lượng lên 5” có thể được biểu diễn thành một thao tác cộng `5`, thay vì gửi lại con số tuyệt đối mà giao diện tính từ một giá trị cũ. Sau khi xung đột, ứng dụng đọc trạng thái mới rồi áp dụng phép cộng nếu quy tắc vẫn hợp lệ.

Không nên lấy payload cũ và gửi lại nguyên xi mà không kiểm tra. Một giao dịch thất bại vì dữ liệu cũ có thể đã dựa vào giá, hạn mức, trạng thái phê duyệt hoặc quyền truy cập không còn đúng.

### Gộp thay đổi theo trường

Nếu A sửa `title` và B sửa `content`, ứng dụng có thể so sánh ba phiên bản:

1. Bản gốc mà B đã đọc (base version).
2. Bản hiện tại trong database sau khi A commit.
3. Bản B muốn lưu.

Nếu `title` không bị B sửa và `content` không bị A sửa, có thể gộp hai thay đổi:

```text
Bản gốc:
    title   = "Quy trình hoàn tiền"
    content = "Hoàn tiền trong 7 ngày"

Phiên bản hiện tại sau A:
    title   = "Chính sách hoàn tiền"
    content = "Hoàn tiền trong 7 ngày"

Thay đổi B:
    title   = "Quy trình hoàn tiền"       (không đổi so với base)
    content = "Hoàn tiền trong 14 ngày"   (đã sửa)

Kết quả gộp có thể:
    title   = "Chính sách hoàn tiền"
    content = "Hoàn tiền trong 14 ngày"
```

Sau khi gộp, ứng dụng phải cập nhật có điều kiện theo version mới nhất vừa đọc. Nếu một giao dịch khác lại thay đổi hàng trước khi cập nhật, phép kiểm tra version phải phát hiện lần cạnh tranh mới. Không được bỏ kiểm tra version chỉ vì đã gộp thành công trong bộ nhớ.

Gộp theo trường chỉ an toàn khi các trường thực sự độc lập. Hai trường có thể ràng buộc với nhau về nghiệp vụ; ví dụ `currency` và `amount`, hoặc `start_time` và `end_time`. Cũng cần xem xét các cập nhật ở cấp collection, JSON document hoặc văn bản dài, nơi thay đổi tưởng như độc lập vẫn có thể chồng lấn.

### Gộp nội dung bằng thuật toán chuyên biệt

Với văn bản, mã nguồn hoặc cấu trúc cộng tác, có thể dùng diff/merge ba chiều, thuật toán OT (*Operational Transformation*) hoặc CRDT (*Conflict-free Replicated Data Type*) tùy yêu cầu sản phẩm.

Những thuật toán này có thể giúp kết hợp chỉnh sửa đồng thời, nhưng chúng là cơ chế giải quyết xung đột ở tầng ứng dụng hoặc mô hình dữ liệu. Cột version chỉ giúp phát hiện rằng base version đã cũ và kích hoạt quy trình gộp. Nó không tự thực hiện thuật toán merge.

Sau khi tạo kết quả gộp, ứng dụng vẫn cần lưu có điều kiện theo version hiện tại. Nếu version lại thay đổi, phải tải lại và tính lại phép gộp hoặc yêu cầu người dùng xử lý.

### Retry toàn bộ transaction

Với giao dịch có thể thực hiện lại an toàn, ứng dụng có thể rollback, bắt đầu transaction mới, đọc trạng thái mới và chạy lại logic nghiệp vụ. Đây là retry có làm mới dữ liệu đầu vào.

```text
BEGIN transaction mới
    đọc dữ liệu hiện tại và version mới
    kiểm tra lại quyền và bất biến nghiệp vụ
    tính lại kết quả
    UPDATE ... WHERE version = expectedVersion
COMMIT nếu thành công
```

Nếu version lại không khớp, có thể thử lại theo giới hạn đã cấu hình hoặc trả xung đột cho tầng gọi. Retry không nên chạy vô hạn, vì một hàng nóng có thể khiến giao dịch liên tục thất bại.

### Yêu cầu người dùng giải quyết thủ công

Với quyết định có ý nghĩa pháp lý, tài chính hoặc nghiệp vụ, tự động gộp có thể không phù hợp. Hệ thống có thể hiển thị bản gốc, bản mới nhất và thay đổi người dùng đang muốn lưu để người có thẩm quyền quyết định.

Ví dụ, hai nhân viên cùng phê duyệt hoặc từ chối một yêu cầu. Đây không đơn giản là hai giá trị văn bản có thể gộp; ứng dụng cần một quy tắc trạng thái rõ ràng và thường phải từ chối hành động dựa trên trạng thái cũ.

## 5. Cập nhật lạc quan trong SQL và ý nghĩa của kết quả

Một thao tác cập nhật lạc quan thường có ba phần:

1. Đọc hàng và lấy version.
2. Thực hiện công việc trong ứng dụng dựa trên dữ liệu đã đọc.
3. Cập nhật với điều kiện version vẫn bằng giá trị đã đọc, đồng thời tăng version.

Ví dụ đầy đủ:

```sql
-- Đọc
SELECT id, title, content, version
FROM documents
WHERE id = 42;

-- Giả sử version đọc được là 7.
-- Ứng dụng tính toán nội dung mới.

-- Ghi có điều kiện
UPDATE documents
SET title = :newTitle,
    content = :newContent,
    version = version + 1
WHERE id = 42
  AND version = 7;
```

Nếu cập nhật bằng `0` hàng, ứng dụng phải quyết định đó là bản ghi không còn tồn tại, không còn quyền truy cập hay xung đột version. Nếu cập nhật bằng `1` hàng, thay đổi đã được chấp nhận tại câu lệnh đó; transaction vẫn cần commit thành công để thay đổi trở thành dữ liệu đã commit.

### Vì sao kiểm tra phải nằm trong câu UPDATE?

Một cách làm sai là đọc version, so sánh trong Java, rồi chạy `UPDATE` không có điều kiện version:

```text
SELECT version -> 7
if (version == 7) {
    UPDATE documents SET content = ... WHERE id = 42
}
```

Giữa bước so sánh trong ứng dụng và câu `UPDATE`, một giao dịch khác có thể cập nhật hàng thành version `8`. Khi đó, câu `UPDATE` không điều kiện vẫn ghi đè phiên bản mới. Đây là lỗi *time-of-check to time-of-use* (TOCTOU).

Đặt `version = :expectedVersion` trong điều kiện `WHERE` làm phép kiểm tra và thay đổi thành một thao tác nguyên tử tại database. Không cần khóa độc quyền kéo dài từ lúc đọc ban đầu đến lúc người dùng hoàn tất chỉnh sửa.

### Mỗi writer phải tuân thủ cùng giao thức

Optimistic version chỉ đáng tin cậy khi mọi đường ghi liên quan đều cập nhật và kiểm tra version. Nếu một script, batch job hoặc service khác cập nhật `content` nhưng không tăng `version`, ứng dụng có thể không phát hiện bản đọc cũ.

Hãy kiểm tra:

- Mọi câu `UPDATE` có tăng version không?
- Mọi câu cập nhật có điều kiện version không?
- Batch/native SQL có bỏ qua cơ chế version của ORM không?
- Trigger hoặc stored procedure có thay đổi dữ liệu mà không cập nhật version không?
- Có trường hợp version bị đặt lại, tràn số hoặc tái sử dụng không?

Version là hợp đồng giữa các bên ghi dữ liệu, không chỉ là một cột trang trí trong schema.

## 6. Version số nguyên và timestamp

### Version tăng đơn điệu

Cột số nguyên thường là lựa chọn dễ hiểu:

```text
version 7 -> version 8 -> version 9 -> ...
```

Mỗi cập nhật thành công tăng revision. Giá trị không phụ thuộc đồng hồ của ứng dụng và dễ so sánh bằng phép bằng trong `WHERE`.

### Dùng timestamp làm version

Một số hệ thống dùng `updated_at` để phát hiện dữ liệu cũ:

```sql
UPDATE documents
SET content = :newContent,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :id
  AND updated_at = :expectedUpdatedAt;
```

Cách này có thể hoạt động nếu timestamp được cập nhật cho mọi lần ghi và có độ chính xác đủ cao. Tuy nhiên, có các rủi ro:

- Độ phân giải thời gian có thể khiến hai lần cập nhật rất gần nhau nhận cùng timestamp.
- Đồng hồ giữa nhiều application node có thể lệch nếu timestamp được tạo ở ứng dụng.
- Chuyển đổi múi giờ, định dạng và làm tròn khi serialize/deserialize có thể làm phép so sánh sai.
- Một thay đổi có thể không cập nhật timestamp do đường ghi bỏ qua quy ước.

Nếu timestamp chỉ có độ chính xác đến mili giây hoặc giây, hai cập nhật trong cùng khoảng đó có thể không tạo token khác nhau. Version số nguyên thường rõ ràng và an toàn hơn cho optimistic locking. Nếu dùng timestamp, nên để database sinh giá trị và kiểm chứng độ chính xác của kiểu cột, driver và ứng dụng.

### Token phiên bản khác

Một hệ thống có thể dùng UUID, hash hoặc token opaque làm revision. Yêu cầu cốt lõi vẫn giống nhau: token phải đổi khi nội dung được bảo vệ thay đổi và phải được so sánh nguyên tử khi cập nhật. Hash nội dung có thể hữu ích khi dữ liệu được quản lý ngoài database, nhưng không tự giải quyết tính nhất quán giữa nội dung và token.

## 7. Optimistic locking trong ORM

ORM thường cung cấp cơ chế version hóa để ứng dụng không phải tự viết điều kiện version cho từng câu lệnh cập nhật thông thường.

Ví dụ với JPA:

```java
@Entity
public class Document {
    @Id
    private Long id;

    private String title;

    @Lob
    private String content;

    @Version
    private Long version;
}
```

`@Version` đánh dấu thuộc tính dùng để kiểm tra optimistic locking. Khi entity được đọc, ORM lưu version hiện tại trong persistence context. Khi flush thay đổi, ORM phát câu lệnh cập nhật có điều kiện theo version đã đọc và tăng version nếu cập nhật thành công.

Một câu SQL minh họa mà ORM có thể phát ra:

```sql
UPDATE documents
SET title = ?,
    content = ?,
    version = 8
WHERE id = 42
  AND version = 7;
```

Nếu không có hàng nào khớp, ORM phát hiện optimistic lock failure. Trong JPA, ứng dụng có thể gặp `OptimisticLockException`; với Spring, lỗi có thể được bọc trong một ngoại lệ thuộc nhóm optimistic locking của framework hoặc persistence provider.

### Lỗi có thể xuất hiện ở flush hoặc commit

Không nên giả định lỗi luôn xuất hiện ngay tại lệnh gọi `save()`. Một số ORM trì hoãn SQL cho đến khi flush, trước câu query tiếp theo hoặc khi transaction commit. Vì vậy, test và xử lý lỗi phải bao quanh ranh giới thực sự thực thi cập nhật.

Sau optimistic lock failure, transaction có thể đã ở trạng thái rollback-only hoặc không còn dùng tiếp được. Cách an toàn thường là rollback transaction hiện tại rồi mở transaction mới để đọc lại và xử lý xung đột.

### Bulk update và native SQL

Bulk JPQL, native SQL hoặc cập nhật ngoài persistence context có thể bỏ qua cơ chế version tự động của ORM, tùy câu lệnh và provider. Nếu dùng các đường ghi này, cần chủ động thêm điều kiện version và tăng version, đồng thời đồng bộ hoặc làm mới persistence context để tránh entity trong bộ nhớ giữ trạng thái cũ.

Không nên cho rằng chỉ cần khai báo `@Version` là mọi câu lệnh SQL trong ứng dụng tự động được bảo vệ. Cần xem SQL thực tế của từng đường ghi.

## 8. HTTP ETag và If-Match: cùng ý tưởng ở tầng API

Phát hiện dữ liệu cũ không chỉ dùng trong database. API HTTP có thể dùng ETag để đại diện cho một phiên bản tài nguyên. Client nhận ETag khi đọc, rồi gửi lại token trong header `If-Match` khi cập nhật.

Ví dụ:

```http
GET /documents/42
```

Response:

```http
HTTP/1.1 200 OK
ETag: "document-42-v7"
Content-Type: application/json

{
  "id": 42,
  "title": "Quy trình hoàn tiền",
  "content": "Hoàn tiền trong 7 ngày"
}
```

Client cập nhật với điều kiện:

```http
PUT /documents/42
If-Match: "document-42-v7"
Content-Type: application/json

{
  "title": "Quy trình hoàn tiền",
  "content": "Hoàn tiền trong 14 ngày"
}
```

Nếu tài nguyên vẫn mang ETag đó, server có thể chấp nhận cập nhật và tạo ETag mới. Nếu một client khác đã cập nhật tài nguyên, điều kiện `If-Match` không còn đúng và server trả `412 Precondition Failed` theo semantics HTTP.

ETag/If-Match truyền cùng một ý tưởng: “chỉ thực hiện nếu tài nguyên vẫn ở phiên bản tôi đã đọc”. Server vẫn phải quyết định cách xử lý khi điều kiện thất bại. HTTP không tự gộp hai payload hoặc chọn nội dung tốt hơn.

Nếu API dùng `If-Match: *`, điều kiện chỉ yêu cầu tài nguyên tồn tại; nó không kiểm tra đúng revision mà client đã đọc. Để bảo vệ khỏi ghi đè dữ liệu cũ, client cần gửi validator cụ thể mà server đã cung cấp.

## 9. Chọn chiến lược giải quyết theo loại dữ liệu

Không phải xung đột nào cũng nên được xử lý bằng cùng một cách. Hãy xem ý nghĩa của dữ liệu và thao tác:

| Loại dữ liệu/thao tác | Cách xử lý thường phù hợp | Vì sao |
|---|---|---|
| Tài liệu văn bản do người dùng sửa | Hiển thị khác biệt, gộp ba chiều hoặc yêu cầu tải lại | Người dùng cần giữ nội dung có chủ đích. |
| Bộ đếm hoặc số lượng cộng dồn | Dùng phép cộng nguyên tử hoặc thao tác có tính kết hợp | Có thể áp dụng cả hai phép cộng mà không ghi đè giá trị tuyệt đối. |
| Số dư tài khoản | Kiểm tra điều kiện, khóa hoặc thao tác nguyên tử trong transaction | Không được tự động gộp số dư từ các snapshot cũ. |
| Trạng thái phê duyệt | Từ chối chuyển trạng thái cũ và yêu cầu tải lại | Các chuyển trạng thái có ý nghĩa nghiệp vụ, không phải chỉnh sửa văn bản. |
| Hồ sơ cấu hình có nhiều trường liên quan | So sánh và gộp có kiểm tra bất biến | Hai trường riêng biệt có thể ràng buộc với nhau. |
| Job trong hàng đợi | Claim nguyên tử, khóa hoặc lease có token | Cần ngăn nhiều worker cùng nhận một công việc. |

### Thao tác có tính giao hoán hoặc kết hợp

Một số hành động có thể được mô hình hóa thành lệnh thay đổi (*command*) thay vì gửi lại toàn bộ trạng thái. Ví dụ, `increment counter by 1` thường dễ kết hợp hơn `set counter = 10` nếu hai client đều tính `10` từ cùng giá trị cũ.

Tuy vậy, tính giao hoán phụ thuộc quy tắc nghiệp vụ. Cộng số lượng có thể giao hoán về mặt toán học, nhưng vẫn cần giới hạn không âm hoặc hạn mức tối đa. Một lệnh tăng tồn kho và một lệnh bán hàng có thể cần được kiểm tra cùng một bất biến. Không được bỏ qua kiểm tra chỉ vì thao tác có vẻ cộng dồn.

## 10. Phân biệt optimistic locking với tự động merge và retry

Ba hành vi sau có mục tiêu khác nhau:

| Hành vi | Câu hỏi nó trả lời | Ví dụ |
|---|---|---|
| **Phát hiện dữ liệu cũ** | Dữ liệu có còn ở revision mà tôi đã đọc không? | `UPDATE ... WHERE version = 7` cập nhật `0` hàng. |
| **Giải quyết xung đột** | Nếu hai thay đổi cạnh tranh, kết quả nghiệp vụ nào được chấp nhận? | Từ chối, gộp trường, merge ba chiều hoặc yêu cầu người dùng chọn. |
| **Retry** | Có thể thực hiện lại thao tác sau khi lấy dữ liệu mới không? | Rollback, đọc version `8`, kiểm tra lại và thử cập nhật. |

Optimistic locking cung cấp tín hiệu để tầng ứng dụng bắt đầu xử lý xung đột. Nó không tự động thực hiện hai hành vi còn lại. Một framework có thể cung cấp tiện ích retry hoặc một sản phẩm có thể tích hợp merge, nhưng đó là tính năng bổ sung với chính sách riêng, không phải hệ quả tự động của cột version.

### Retry không phải là giải quyết xung đột một cách mù quáng

Ví dụ, một giao dịch đọc giá sản phẩm `100`, kiểm tra người mua có hạn mức, rồi ghi đơn hàng. Trong khi đó giá đổi thành `150`. Nếu giao dịch thất bại do version cũ và ứng dụng chỉ chạy lại câu `INSERT order` với giá `100`, nó đã bỏ qua dữ liệu mới và có thể bán sai giá.

Retry đúng phải:

1. Rollback transaction thất bại.
2. Mở transaction mới và đọc lại dữ liệu cần thiết.
3. Kiểm tra lại quyền, giá, hạn mức và các bất biến liên quan.
4. Tính lại kết quả theo trạng thái mới.
5. Cập nhật có điều kiện theo version vừa đọc.
6. Commit nếu mọi điều kiện vẫn hợp lệ; nếu không, trả lỗi nghiệp vụ hoặc thử lại có giới hạn.

Nếu transaction gửi email hoặc gọi dịch vụ ngoài trước khi commit, retry có thể gửi lặp. Các tác dụng phụ như vậy cần idempotency key, outbox hoặc cơ chế điều phối thích hợp.

## 11. Giới hạn của version ở cấp một hàng

Version trên một hàng bảo vệ những cập nhật có điều kiện trên hàng đó. Nó không tự động bảo vệ mọi dữ liệu mà quyết định nghiệp vụ đã đọc.

Giả sử một quy tắc yêu cầu luôn có ít nhất một bác sĩ trực. `T1` đọc trạng thái bác sĩ 1 và 2, rồi cập nhật hàng bác sĩ 1. `T2` đọc cùng trạng thái, rồi cập nhật hàng bác sĩ 2. Nếu version của từng hàng được kiểm tra riêng, hai giao dịch vẫn có thể ghi thành công vì chúng cập nhật hai hàng khác nhau. Kết quả cuối có thể không còn bác sĩ nào trực.

Đây là dạng *write skew* trong các cơ chế snapshot. Để bảo vệ bất biến liên hàng, cần một cách đồng bộ có phạm vi bao trùm tất cả dữ liệu liên quan, ví dụ:

- Serializable hoặc cơ chế theo dõi phụ thuộc tương đương.
- Một hàng điều phối chung mà mọi giao dịch phải cập nhật có điều kiện.
- Khóa chung lấy trước khi đọc và kiểm tra bất biến, với semantics phù hợp của hệ quản trị.
- Constraint database có thể diễn đạt và thực thi an toàn bất biến đó.

Một cột version đơn lẻ không thay thế cho việc xác định phạm vi của bất biến. Nếu quyết định phụ thuộc nhiều hàng, phải bảo vệ tất cả những phụ thuộc có thể làm quyết định mất hiệu lực.

## 12. Kiểm thử phát hiện dữ liệu cũ

Một bài test hữu ích cần dùng hai transaction hoặc hai client độc lập để tạo cạnh tranh thật.

### Test hai client cùng lưu một version

Chuẩn bị tài liệu version `1`. Hai client cùng đọc tài liệu:

```text
Client A: GET document -> version 1
Client B: GET document -> version 1

Client A: UPDATE where version = 1 -> 1 row updated
          database version becomes 2

Client B: UPDATE where version = 1 -> 0 rows updated
```

Test cần xác nhận:

- Chỉ một cập nhật thành công từ version `1`.
- Version tăng đúng một lần.
- Nội dung của giao dịch thắng được giữ lại.
- Giao dịch thua nhận kết quả xung đột rõ ràng.
- Ứng dụng không âm thầm ghi đè hoặc bỏ qua điều kiện version.

### Test cập nhật độc lập

Cho hai giao dịch sửa hai hàng khác nhau với version riêng. Nếu không có bất biến liên hàng, cả hai có thể thành công. Test này giúp tránh cấu hình quá rộng khiến mọi cập nhật không liên quan đều xung đột.

### Test mọi đường ghi

Thực hiện cập nhật bằng ORM, native SQL, batch job, script quản trị và các service khác. Xác nhận tất cả đường ghi đều làm revision thay đổi. Một đường ghi bỏ qua version có thể phá vỡ toàn bộ bảo đảm optimistic locking.

### Test xử lý sau xung đột

Kiểm tra cả ba chính sách có thể có: từ chối, merge và retry. Xác nhận merge luôn dựa trên base version, phiên bản mới nhất và nội dung muốn lưu; xác nhận retry đọc lại và kiểm tra lại nghiệp vụ; xác nhận tác dụng phụ ngoài database không bị lặp.

## 13. Những lỗi thiết kế thường gặp

- **So sánh version ở ứng dụng rồi cập nhật vô điều kiện:** tạo khoảng TOCTOU, vì version có thể đổi giữa lúc kiểm tra và ghi. Đặt version trong điều kiện `WHERE`.
- **Không tăng version ở mọi đường ghi:** một writer bỏ qua version khiến writer khác không phát hiện dữ liệu đã đổi.
- **Dùng timestamp có độ chính xác thấp:** hai cập nhật có thể nhận cùng token, làm mất khả năng phát hiện.
- **Tự động retry payload cũ:** có thể áp dụng lại quyết định dựa trên giá, quyền hoặc trạng thái đã lỗi thời.
- **Cho rằng version mismatch có nghĩa phải lấy bản ghi mới nhất và ghi đè:** điều đó chỉ thay đổi người thắng, không giải quyết ý nghĩa của hai thay đổi.
- **Chỉ version hóa một hàng trong khi quy tắc phụ thuộc nhiều hàng:** write skew vẫn có thể xảy ra.
- **Không xử lý lỗi ở flush/commit:** ngoại lệ có thể phát sinh muộn hơn lệnh `save`, khiến lỗi lọt khỏi phạm vi xử lý.
- **Dùng bulk update nhưng quên version:** cơ chế tự động của ORM có thể bị bỏ qua.

## 14. Kết luận

Optimistic locking dùng revision hoặc token phiên bản để phát hiện rằng dữ liệu ứng dụng đã đọc không còn là phiên bản hiện tại khi nó muốn ghi. Điều kiện version được kiểm tra nguyên tử trong câu cập nhật, giúp ngăn ghi đè mù và báo cho ứng dụng biết có cạnh tranh.

Khi version không khớp, hệ thống mới chỉ biết rằng thao tác dựa trên dữ liệu cũ. Ứng dụng phải chọn chính sách phù hợp: từ chối, tải lại và kiểm tra lại, gộp thay đổi, áp dụng lại một lệnh nghiệp vụ, retry toàn bộ transaction hoặc yêu cầu người dùng quyết định. Mỗi cách cần dựa trên ý nghĩa dữ liệu và bất biến nghiệp vụ. Đặc biệt, retry phải dùng snapshot mới và tính toán lại; version ở cấp một hàng cũng không tự bảo vệ quy tắc phụ thuộc nhiều hàng. **Phát hiện xung đột là cơ chế bảo vệ tính đúng đắn; giải quyết xung đột là quyết định nghiệp vụ và chính sách của ứng dụng.**
