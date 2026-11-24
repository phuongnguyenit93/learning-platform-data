# Bảo vệ tính toàn vẹn bút toán sổ cái — Ledger entry integrity

## 1. Bài toán bảo mật cần giải quyết

Trong chương **Monetary Rules**, tính toàn vẹn bút toán là khả năng bảo đảm rằng mọi thay đổi tiền được ghi nhận đầy đủ, đúng đối tượng, đúng số tiền, đúng sự kiện và đúng một lần về mặt hiệu ứng nghiệp vụ. Sau khi ghi sổ, lịch sử phải còn đủ bằng chứng để giải thích vì sao số dư thay đổi.

Một API có thể đã xác thực người gọi, kiểm tra JSON và dùng câu lệnh SQL có tham số nhưng vẫn cho phép gian lận nếu nó nhận tài khoản đích từ client, cho ghi sổ trước khi phê duyệt hoặc ghi lại cùng một giao dịch khi nhận yêu cầu trùng. Đây là nhóm lỗi **business logic security**: chương trình chạy đúng từng lệnh nhưng vi phạm quy tắc nghiệp vụ.

Ví dụ, một lần thu tiền 100.000 VND được ghi theo mô hình minh họa sau:

| Tài khoản | Bên Nợ — Debit | Bên Có — Credit |
| --- | ---: | ---: |
| Tiền tại ngân hàng | 100.000 | 0 |
| Doanh thu | 0 | 90.000 |
| Thuế phải nộp | 0 | 10.000 |
| **Tổng** | **100.000** | **100.000** |

Nếu chỉ dòng tiền tại ngân hàng được lưu thành công, sổ bị mất cân đối. Nếu cả ba dòng được lưu hai lần, sổ vẫn cân nhưng doanh thu và tiền đều sai. Nếu các dòng được ghi sang một tài khoản thuộc người khác, sổ cũng có thể cân hoàn toàn.

Vì vậy, **cân bằng Nợ/Có là điều kiện cần, chưa đủ để chứng minh một bút toán hợp lệ**. Ta còn phải kiểm soát nguồn sự kiện, quyền theo đối tượng, trạng thái, giao dịch cơ sở dữ liệu và idempotency.

Các tài khoản và thời điểm ghi nhận trong bài là ví dụ kỹ thuật. Hệ thống thực tế cần một chính sách hạch toán được phê duyệt cho từng loại nghiệp vụ; không suy chính sách đó chỉ từ việc tiền đã đi qua một API.

## 2. Phân biệt sự kiện, bút toán và số dư

Trong bài, các thuật ngữ được dùng như sau:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Sự kiện kinh tế | Sự việc có ý nghĩa tiền tệ được hệ thống xác nhận | Một capture thanh toán thành công |
| Journal | Một chứng từ ghi sổ gồm các dòng liên quan | Chứng từ ghi nhận capture đó |
| Entry hoặc journal line | Một dòng Nợ hoặc Có của journal | Ghi Có doanh thu 90.000 VND |
| Ledger account | Tài khoản sổ cái nhận các dòng ghi sổ | Tiền ngân hàng, doanh thu, công nợ |
| Ledger book | Phạm vi sổ có cùng chính sách và ranh giới hạch toán | Sổ VND của một pháp nhân |
| Balance projection | Số dư tổng hợp để đọc nhanh | Số dư ví được dựng từ các entry |

Một HTTP request không mặc nhiên là một sự kiện kinh tế. Hai webhook có ID giao nhận khác nhau vẫn có thể mô tả cùng một capture. Ngược lại, một đơn hàng có thể có nhiều capture hoặc nhiều lần hoàn tiền hợp lệ.

Do đó, không dùng riêng `request_id`, ID bản tin webhook hoặc `order_id` làm danh tính cho mọi bút toán. Phải xác định đúng đơn vị nghiệp vụ được ghi sổ, chẳng hạn bộ `(provider, merchant_account, capture_id)`, rồi chuẩn hóa nó thành `source_id` do server quản lý.

**Sổ cái và số dư tổng hợp có vai trò khác nhau.** Trong thiết kế của bài, entry đã ghi sổ là nguồn dữ liệu để dựng lại số dư. Một cache số dư không đủ làm bằng chứng cho khoản tiền; một audit log HTTP cũng không thay thế được journal có cấu trúc.

## 3. Các bất biến phải được bảo vệ

Một invariant, hay bất biến nghiệp vụ, là điều kiện phải đúng ở mọi trạng thái đã commit. Trong lúc xây dựng journal bên trong transaction, các dòng có thể chưa đầy đủ; trạng thái dở dang đó không được trở thành kết quả đã commit hoặc được công bố ra bên ngoài.

### 3.1. Bất biến về cấu trúc và tiền

Với một journal `J` trong một book và một loại tiền:

```text
count(lines(J)) >= 2
amount_minor(line) > 0
side(line) ∈ {D, C}
currency(line) = currency(J) = currency(book)
book(line.account) = book(J)
SUM(amount_minor WHERE side = D)
    = SUM(amount_minor WHERE side = C)
```

Số tiền được lưu dương; bên Nợ/Có biểu diễn hướng hạch toán. Không vừa dùng số âm vừa đảo bên nếu chính sách không định nghĩa rõ, vì hai cách biểu diễn có thể làm kiểm tra hạn mức hoặc hoàn tiền bị đảo nghĩa.

Book trong ví dụ chỉ có một loại tiền. Một giao dịch đổi tiền cần các journal liên kết theo chính sách ngoại hối, với tỷ giá và tài khoản đối ứng được lưu rõ. Không cộng 100 USD với 100 VND để kết luận tổng chênh lệch bằng không.

### 3.2. Bất biến về ý nghĩa nghiệp vụ

- Mỗi journal phải trỏ tới một sự kiện hợp lệ, đã được xác minh.
- Số tiền, tiền tệ và tài khoản phải được server suy ra từ dữ liệu có thẩm quyền và phiên bản chính sách tương ứng.
- Một sự kiện chỉ được ghi nhận một lần cho cùng loại nghiệp vụ trong cùng book.
- Phải thỏa điều kiện trạng thái, quyền sở hữu và phê duyệt tại thời điểm ghi sổ.
- Tổng hoàn tiền đã chấp nhận không vượt số tiền còn được phép hoàn theo chính sách.
- Các hạn mức hoặc điều kiện số dư phải đúng ngay cả khi có nhiều request đồng thời.

### 3.3. Bất biến về lịch sử

- Journal và entry đã ghi sổ không được sửa hoặc xóa bằng luồng nghiệp vụ thông thường.
- Sai sót được điều chỉnh bằng journal mới có liên kết, lý do và người thực hiện.
- Bằng chứng nguồn, phê duyệt và phiên bản quy tắc phải đủ để giải thích kết quả sau này.
- Cùng một thao tác được retry phải dẫn về kết quả đã có, không tạo thêm hiệu ứng tiền.

Tổng Nợ bằng tổng Có không chứng minh tài khoản đúng, giá đúng, thuế đúng hay người gọi có quyền. Cần kiểm tra từng bất biến theo đúng phạm vi của nó.

## 4. Mô hình đe dọa: kẻ tấn công muốn làm sai điều gì?

| Cách lạm dụng | Vì sao kiểm tra thông thường có thể bỏ sót? | Kiểm soát cần có |
| --- | --- | --- |
| Gửi `amount=1` cho đơn hàng 100.000 VND | Giá trị vẫn là số dương hợp lệ | Tính lại từ dữ liệu đã chốt; so khớp bằng chứng thanh toán |
| Thay `creditAccountId` bằng tài khoản của mình | ID tài khoản có tồn tại | Server chọn tài khoản từ chính sách; kiểm tra book và chủ thể |
| Ghi sổ khi hồ sơ chưa được duyệt | Người gọi có quyền gọi API | State machine và ràng buộc phê duyệt tại thời điểm posting |
| Gửi lại callback thành công nhiều lần | Từng callback đều có chữ ký hợp lệ | Chống trùng theo sự kiện kinh tế |
| Đổi idempotency key rồi gửi lại cùng capture | Khóa request khác nhau | Unique nghiệp vụ độc lập với khóa request |
| Gọi hoàn tiền đồng thời | Mỗi request riêng lẻ nằm trong hạn mức | Khóa hoặc cập nhật có điều kiện trên tổng có thẩm quyền |
| Sửa dòng đã ghi sổ để che gian lận | Vai trò ứng dụng có quyền `UPDATE` | Hạn chế quyền DB, bất biến lịch sử, điều chỉnh bằng journal mới |
| Chuyển tiền giữa hai tenant | Các dòng vẫn cân bằng | Quyền theo đối tượng và ràng buộc phạm vi book/account |

Chữ ký webhook chỉ hỗ trợ xác thực nguồn và tính nguyên vẹn thông điệp theo cơ chế của nhà cung cấp. Nó không tự chứng minh thông điệp chưa từng được xử lý, merchant đúng, số tiền khớp đơn hàng hoặc thời điểm ghi sổ phù hợp.

## 5. Thiết kế mô hình dữ liệu có ranh giới rõ

Một cách giảm bề mặt lỗi là chỉ lưu **journal đã ghi sổ** trong bảng ledger chính thức. Yêu cầu nhập nháp hoặc yêu cầu chờ duyệt nằm ở bảng nghiệp vụ riêng. Khi đủ điều kiện, hệ thống tạo journal và toàn bộ entry trong một transaction.

```text
Yêu cầu nghiệp vụ
    DRAFT → PENDING_APPROVAL → APPROVED → POSTED
      └──────────────→ CANCELLED

Ledger chính thức
    Chỉ nhận journal khi thao tác posting commit thành công
    Không chuyển journal đã ghi sổ về DRAFT
```

Sơ đồ là chính sách minh họa: hệ thống có thể cho hủy ở các trạng thái khác nếu định nghĩa rõ điều kiện. Điều cốt lõi là không có đường đi tắt từ dữ liệu chưa đủ điều kiện vào ledger.

Đoạn PostgreSQL sau minh họa khóa và ràng buộc cấu trúc. Nó **chưa phải bộ triển khai ledger hoàn chỉnh**: chưa có hàm posting, ràng buộc cân bằng nhiều dòng, bảng idempotency, kiểm soát quyền hoặc outbox.

```sql
CREATE TABLE ledger_book (
    book_id          uuid PRIMARY KEY,
    tenant_id        uuid NOT NULL,
    legal_entity_id  uuid NOT NULL,
    currency         varchar(3) NOT NULL,
    amount_scale     smallint NOT NULL CHECK (amount_scale >= 0),
    UNIQUE (book_id, currency)
);

CREATE TABLE ledger_account (
    account_id   uuid PRIMARY KEY,
    book_id      uuid NOT NULL,
    currency     varchar(3) NOT NULL,
    account_code text NOT NULL,
    UNIQUE (account_id, book_id, currency),
    UNIQUE (book_id, account_code),
    FOREIGN KEY (book_id, currency)
        REFERENCES ledger_book (book_id, currency)
);

CREATE TABLE ledger_journal (
    journal_id       uuid PRIMARY KEY,
    book_id          uuid NOT NULL,
    currency         varchar(3) NOT NULL,
    operation_type   text NOT NULL,
    source_type      text NOT NULL,
    source_id        text NOT NULL,
    source_fingerprint text NOT NULL,
    policy_version   text NOT NULL,
    created_by       uuid NOT NULL,
    posted_at        timestamptz NOT NULL DEFAULT now(),
    reversal_of      uuid,
    UNIQUE (journal_id, book_id, currency),
    UNIQUE (book_id, operation_type, source_type, source_id),
    FOREIGN KEY (book_id, currency)
        REFERENCES ledger_book (book_id, currency),
    FOREIGN KEY (reversal_of, book_id, currency)
        REFERENCES ledger_journal (journal_id, book_id, currency)
);

CREATE TABLE ledger_line (
    journal_id   uuid NOT NULL,
    line_no      integer NOT NULL CHECK (line_no > 0),
    book_id      uuid NOT NULL,
    currency     varchar(3) NOT NULL,
    account_id   uuid NOT NULL,
    side         char(1) NOT NULL CHECK (side IN ('D', 'C')),
    amount_minor numeric(30, 0) NOT NULL,
    PRIMARY KEY (journal_id, line_no),
    CHECK (
        amount_minor > 0
        AND amount_minor <= 999999999999999999999999999999
    ),
    FOREIGN KEY (journal_id, book_id, currency)
        REFERENCES ledger_journal (journal_id, book_id, currency),
    FOREIGN KEY (account_id, book_id, currency)
        REFERENCES ledger_account (account_id, book_id, currency)
);
```

Các khóa ngoại ghép ngăn một dòng gắn vào journal của book này nhưng lại dùng account của book khác. `tenant_id` và `legal_entity_id` được xác định qua book; API vẫn phải tra book trong phạm vi chủ thể đã xác thực, không chỉ tìm theo một UUID bất kỳ.

`source_fingerprint` biểu diễn các sự kiện nguồn đã chuẩn hóa, chẳng hạn danh tính capture, merchant, số tiền và loại tiền. Nó giúp phát hiện cùng danh tính nguồn nhưng dữ liệu mâu thuẫn; bản thân fingerprint không xác thực nguồn và không thay thế bằng chứng gốc.

Các cột xác định phạm vi và tiền tệ của book/account phải được kiểm soát như cấu hình có ảnh hưởng tài chính. Không cho phép sửa tùy ý `amount_scale` của book đã có dữ liệu: cùng một số nguyên có thể bị diễn giải thành số tiền khác.

### Vì sao không có `CHECK` tổng Nợ bằng tổng Có?

Trong PostgreSQL, `CHECK` không phải cơ chế bảo đảm điều kiện phụ thuộc các dòng khác trong bảng. Vì thế, không bọc một truy vấn `SUM` vào hàm rồi cho rằng `CHECK` sẽ bảo vệ toàn bộ journal. Xem [tài liệu PostgreSQL về CHECK constraints](https://www.postgresql.org/docs/18/ddl-constraints.html#DDL-CONSTRAINTS-CHECK-CONSTRAINTS).

Có thể tổ chức việc bảo vệ như sau:

1. Vai trò ứng dụng chỉ được thực thi hàm posting có kiểm soát; không có quyền ghi trực tiếp các bảng ledger.
2. Hàm đó tạo đủ journal/line, kiểm tra số dòng và tổng tiền, đồng thời ghi các thay đổi nghiệp vụ trong cùng transaction.
3. Dùng deferred constraint trigger nếu cần một hàng rào kiểm tra cân bằng ở cuối transaction. Trigger phải bao phủ journal mới và mọi thay đổi line có thể ảnh hưởng tổng; kiểm tra cả journal không có line.
4. Các tác vụ import, backfill và quản trị cũng phải đi qua quy tắc tương đương; không tạo một đường ghi bỏ qua invariant.

Nếu dùng hàm `SECURITY DEFINER`, phải giới hạn quyền `EXECUTE`, cố định `search_path` an toàn và kiểm tra phạm vi đối tượng bên trong ranh giới tin cậy. Một hàm đặc quyền cho phép caller đưa tùy ý book, account và số tiền vẫn là lỗ hổng.

## 6. Biểu diễn tiền chính xác trước khi kiểm tra cân bằng

Không dùng `float` hoặc `double` cho số tiền cần chính xác. Trong mô hình trên, `amount_minor` là số nguyên theo đơn vị nhỏ nhất mà book sử dụng:

```text
Book VND, amount_scale = 0:
    100.000 VND → amount_minor = 100000

Book USD, amount_scale = 2:
    12,34 USD → amount_minor = 1234
```

Đơn vị lưu trữ và quy tắc làm tròn phải được cấu hình theo loại tiền, sản phẩm và bộ kết nối thanh toán. Không mặc định mọi loại tiền đều có hai chữ số thập phân.

Khi dùng Java, có thể chuyển số thập phân sang số nguyên một cách tường minh:

```java
// Ví dụ chuyển đổi; currencyScale lấy từ cấu hình có thẩm quyền.
BigInteger toMinorUnits(String decimalAmount, int currencyScale) {
    BigDecimal exact = new BigDecimal(decimalAmount)
        .setScale(currencyScale, RoundingMode.UNNECESSARY);
    return exact.movePointRight(currencyScale).toBigIntegerExact();
}
```

`UNNECESSARY` từ chối đầu vào cần làm tròn ở bước chuyển đổi này. Nếu nghiệp vụ có làm tròn thuế hoặc tỷ giá, phải thực hiện trước theo chính sách rõ ràng và lưu kết quả cùng phiên bản quy tắc. Không âm thầm cắt phần lẻ để làm journal cân.

Lớp validation cần kiểm tra giới hạn độ dài đầu vào, giá trị dương và miền biểu diễn của DB trước khi ghi. Với cột có scale cố định, không dựa vào việc DB tự chuyển kiểu để phát hiện đầu vào có phần lẻ; dữ liệu có thể đã bị làm tròn khi ép kiểu. `BigInteger` tránh tràn số khi cộng trong Java, nhưng vẫn phải kiểm tra từng giá trị có nằm trong giới hạn lưu trữ và hạn mức nghiệp vụ.

Chênh lệch làm tròn chỉ được ghi vào tài khoản và trong ngưỡng đã định nghĩa. Không tự tạo một dòng “bù cân” cho mọi sai lệch: cách đó có thể biến lỗi sửa giá hoặc sai tiền tệ thành journal có vẻ hợp lệ.

## 7. Quy trình posting nguyên tử

API hướng nghiệp vụ nên nhận một lệnh hẹp, ví dụ:

```http
POST /orders/{orderId}/post-capture
Idempotency-Key: client-generated-key
Content-Type: application/json

{
  "captureId": "provider-capture-id",
  "expectedOrderVersion": 7
}
```

Trong ví dụ này, client không gửi các dòng ledger, tài khoản đối ứng, trạng thái đã duyệt hoặc tổng doanh thu. Server truy xuất dữ liệu có thẩm quyền để xây dựng journal. API điều chỉnh kế toán, nếu có, cần quy trình phê duyệt và quyền riêng.

Một luồng xử lý có thể được tổ chức như sau:

```text
Xác thực người gọi; xác định tenant và phạm vi thao tác
Chuẩn hóa command; tạo fingerprint cho idempotency

BEGIN
  1. Claim khóa idempotency bằng ràng buộc unique
     - Đã hoàn tất, cùng fingerprint, caller còn quyền:
       trả về kết quả đã lưu
     - Cùng khóa, khác fingerprint: từ chối
     - Request mới: tiếp tục

  2. Khóa bản ghi nghiệp vụ có thẩm quyền
     - Đơn hàng / yêu cầu hoàn tiền / tài khoản hạn mức
     - Lấy khóa nhiều đối tượng theo một thứ tự nhất quán

  3. Kiểm tra sự kiện đã từng có journal chưa
     - Có và cùng sự kiện hợp lệ: liên kết tới kết quả cũ
     - Có nhưng dữ liệu nguồn mâu thuẫn: từ chối, phát cảnh báo

  4. Với sự kiện chưa ghi sổ, kiểm tra trên dữ liệu hiện tại đã khóa
     - Quyền theo đối tượng và book
     - Trạng thái, phê duyệt, phiên bản và kỳ ghi sổ
     - Bằng chứng capture đã xác minh, đúng merchant
     - Số tiền và loại tiền khớp dữ liệu nghiệp vụ đã chốt

  5. Server lập journal theo chính sách có phiên bản
     - Kiểm tra tài khoản, số dòng, miền giá trị, cân bằng
     - Ghi journal và tất cả line

  6. Cập nhật trạng thái nguồn, hạn mức/số dư có thẩm quyền
     Ghi outbox và kết quả idempotency
     Kiểm tra các invariant cuối transaction
COMMIT

Trả kết quả có journal_id
```

Kết quả cũ phải được nhận diện trước khi áp các điều kiện chỉ dành cho một lần posting mới. Nếu lần đầu đã chuyển đơn hàng sang `POSTED`, một retry hợp lệ cần nhận lại journal cũ thay vì bị hiểu là một yêu cầu ghi mới sai trạng thái. Việc replay vẫn phải kiểm tra quyền đọc kết quả; biết idempotency key không phải là quyền truy cập.

Điểm quyết định thành công là **commit**, không phải lúc `INSERT` dòng đầu tiên. Nếu chèn dòng thứ hai hoặc ghi kết quả idempotency thất bại, phải rollback toàn bộ. Nếu mất kết nối sau commit nhưng trước khi trả HTTP response, client dùng lại cùng khóa để lấy kết quả.

Không gọi dịch vụ thanh toán bên ngoài khi đang giữ khóa DB trong luồng này. Việc xác minh hoặc thực hiện thanh toán bên ngoài cần giao thức riêng; ledger chỉ ghi nhận bằng chứng đã được kiểm tra và lưu. Không có transaction SQL cục bộ nào tự rollback được một khoản thanh toán đã thành công tại nhà cung cấp.

Nếu ledger là một dịch vụ có DB riêng, không thể coi cập nhật đơn hàng ở DB khác là cùng transaction. Khi đó cần giao thức message/outbox/inbox, trạng thái trung gian và đối soát; journal ở ledger vẫn phải được ghi nguyên tử tại chính ledger.

## 8. Idempotency có hai lớp độc lập

### 8.1. Chống trùng request

Một bảng idempotency thường cần các thông tin:

| Trường | Mục đích |
| --- | --- |
| Phạm vi client/tenant và loại thao tác | Ngăn khóa của chủ thể khác va chạm hoặc bị dùng để truy cập chéo |
| Idempotency key | Nhận diện một lần thực hiện command |
| Request fingerprint | Phát hiện tái dùng khóa với command khác |
| Journal ID và kết quả | Trả lại cùng hiệu ứng đã commit |
| Thời điểm và chính sách lưu giữ | Quản lý vận hành và khả năng retry |

Fingerprint phải được tính từ các trường có ý nghĩa nghiệp vụ sau chuẩn hóa, như đối tượng, sự kiện, phiên bản kỳ vọng và loại thao tác. Không băm nguyên JSON thô rồi để thứ tự key quyết định command có giống nhau hay không.

Hai request cùng khóa đến đồng thời phải được phân xử bằng unique constraint hoặc thao tác nguyên tử tương đương. `SELECT` không thấy khóa rồi mới `INSERT` là một khoảng đua. Trong mô hình cùng DB, có thể claim khóa, ghi journal và lưu kết quả trong cùng transaction; transaction thất bại thì claim cũng rollback.

Nếu chọn mô hình lưu `IN_PROGRESS` bằng transaction riêng, phải thiết kế thêm lease, quyền tiếp quản và khôi phục sau crash. Không suy ra rằng một dòng `IN_PROGRESS` đồng nghĩa với việc tiền đã được ghi sổ.

### 8.2. Chống trùng sự kiện kinh tế

Khóa unique trên journal trong ví dụ bảo vệ:

```text
(book_id, operation_type, source_type, source_id)
```

Do đó, cùng một capture gửi với hai idempotency key khác nhau vẫn không tạo hai journal. Với nghiệp vụ cho phép nhiều lần hoàn tiền, mỗi lần hoàn có danh tính riêng; đồng thời phải kiểm tra tổng số tiền đã hoàn trên capture gốc.

Không dùng một ID do caller tùy ý thay đổi làm danh tính sự kiện kinh tế. ID phải gắn với nguồn tin cậy và phạm vi nhà cung cấp/merchant phù hợp. Chỉ làm unique theo `capture_id` cũng có thể sai nếu ID đó không duy nhất giữa các merchant.

Nếu gặp sự kiện đã ghi sổ, so khớp các dữ kiện bất biến với bản đã lưu. Không tự ghi thêm journal theo bảng giá hoặc cấu hình tài khoản mới chỉ vì chính sách hiện tại khác phiên bản dùng lần đầu.

Khi có xung đột unique, code phải xử lý đúng trạng thái transaction. Chẳng hạn, có thể dùng `INSERT ... ON CONFLICT` với luồng đọc kết quả rõ ràng, hoặc rollback rồi truy vấn/retry trong transaction mới; không bắt lỗi SQL rồi tiếp tục tùy ý trong transaction đã lỗi.

Idempotency không làm mạng truyền đúng một lần. Nó giúp nhiều lần giao nhận hoặc retry cùng một thao tác tạo **một hiệu ứng nghiệp vụ** tại phạm vi được bảo vệ. Khi bản ghi idempotency hết hạn, ràng buộc chống trùng sự kiện ở ledger vẫn phải còn hiệu lực.

## 9. Đồng thời: journal cân nhưng số dư vẫn có thể sai

Giả sử một ví có số dư khả dụng 100.000 VND. Hai request rút 80.000 VND cùng đọc số dư cũ:

```text
Request A: đọc 100.000 → đủ tiền
Request B: đọc 100.000 → đủ tiền
Request A: ghi journal rút 80.000 → thành công
Request B: ghi journal rút 80.000 → thành công

Tổng rút = 160.000; cả hai journal vẫn cân Nợ/Có.
```

Đặt mỗi request trong một transaction chưa đủ. Phải bảo vệ điều kiện “còn đủ tiền” trước cạnh tranh trên cùng tài nguyên.

Các cách thường dùng gồm khóa dòng tổng hợp có thẩm quyền bằng `SELECT ... FOR UPDATE`, cập nhật số dư bằng điều kiện nguyên tử hoặc dùng isolation serializable kèm retry toàn transaction. Chọn một thiết kế rõ ràng và buộc mọi luồng chi tiền tuân theo.

Ví dụ cập nhật có điều kiện, với số dư và số tiền cùng đơn vị:

```sql
UPDATE wallet_spending_state
SET available_minor = available_minor - :amount_minor,
    version = version + 1
WHERE wallet_id = :wallet_id
  AND tenant_id = :tenant_id
  AND currency = :currency
  AND available_minor >= :amount_minor;
```

Lệnh chỉ hợp lệ sau khi server đã kiểm tra `amount_minor > 0`, quyền đối tượng và chính sách ví. Phải kiểm tra có đúng một dòng được cập nhật, rồi ghi journal trong **cùng transaction**. Nếu journal không ghi được, việc trừ số dư cũng phải rollback.

Nếu có giữ chỗ tiền, có thể định nghĩa:

```text
available = posted_wallet_balance - active_holds
```

Định nghĩa này chỉ dùng khi posted balance chưa trừ các hold đó. Khi chuyển hold thành khoản chi đã ghi sổ, phải tiêu thụ hold và cập nhật phần đã ghi nhận nguyên tử, tránh trừ hai lần. Cache đọc chậm hoặc replica chưa cập nhật không được dùng để quyết định còn được chi bao nhiêu.

Tương tự, hai lệnh hoàn tiền phải khóa cùng capture hoặc cùng bản ghi hạn mức hoàn. Chỉ khóa hai journal mới tạo không ngăn chúng cùng vượt số tiền của capture gốc.

Nợ/Có không đồng nghĩa với tăng/giảm giống nhau cho mọi loại tài khoản. Không áp một quy tắc “mọi số dư ledger đều không âm” cho tài sản, công nợ và doanh thu. Điều kiện không âm phải gắn với đúng khái niệm nghiệp vụ như số dư khả dụng của ví.

Khi khóa nhiều tài nguyên, cần thống nhất thứ tự, chẳng hạn sắp theo ID trước khi khóa. PostgreSQL khuyến nghị lấy khóa theo thứ tự nhất quán để giảm deadlock; deadlock vẫn cần cơ chế retry có giới hạn. Xem [tài liệu PostgreSQL về explicit locking](https://www.postgresql.org/docs/18/explicit-locking.html).

## 10. Quyền theo đối tượng và phê duyệt

Quyền `LEDGER_POST` chỉ là điểm bắt đầu. Quyết định posting phải ràng buộc với đối tượng cụ thể:

```text
Actor có được thực hiện operation này không?
Đối tượng nguồn thuộc tenant/pháp nhân nào?
Book và account có nằm trong phạm vi được phép không?
Khoản tiền và loại tiền có đúng với phê duyệt không?
Nội dung đã duyệt có bị thay đổi sau khi duyệt không?
Thời điểm hiện tại còn cho phép ghi sổ vào kỳ yêu cầu không?
```

Một phê duyệt chỉ gắn với `order_id` nhưng không gắn với phiên bản nội dung có thể bị lạm dụng: người dùng xin duyệt 100.000 VND rồi sửa thành 1.000.000 VND trước khi posting. Cần khóa hoặc so khớp phiên bản/fingerprint của dữ liệu đã duyệt, và vô hiệu hóa phê duyệt khi các trường quan trọng thay đổi.

Với điều chỉnh thủ công có rủi ro cao, chính sách có thể yêu cầu người tạo khác người duyệt, hạn mức theo vai trò và lý do kèm bằng chứng. Các điều kiện này phải được kiểm tra ở luồng server; ẩn nút “Approve” trên giao diện không bảo vệ API.

Job nền và webhook cũng cần danh tính dịch vụ với phạm vi hữu hạn. Không coi chúng là nguồn được miễn kiểm tra book, tài khoản hoặc trạng thái chỉ vì không có người dùng trực tiếp bấm nút.

## 11. Sửa sai bằng journal mới

Với journal đã ghi sổ, không sửa dòng 90.000 thành 80.000 rồi lưu lại. Hành động đó làm mất cách giải thích số dư và có thể khiến báo cáo đã xuất không còn khớp lịch sử hiện tại.

Một cách sửa sai là đảo đầy đủ journal gốc rồi ghi journal thay thế:

| Journal | Tiền ngân hàng | Doanh thu | Thuế phải nộp |
| --- | --- | --- | --- |
| J1: ghi ban đầu | Nợ 100.000 | Có 90.000 | Có 10.000 |
| J2: đảo J1 | Có 100.000 | Nợ 90.000 | Nợ 10.000 |
| J3: ghi thay thế | Theo số liệu đã duyệt lại | Theo số liệu đã duyệt lại | Theo số liệu đã duyệt lại |

J2 phải liên kết tới J1 bằng `reversal_of`, giữ cùng book và loại tiền, đồng thời đảo đúng các dòng theo chính sách. Chỉ có khóa ngoại không đủ chứng minh đây là một phép đảo hợp lệ.

Nếu chính sách chỉ cho phép đảo đầy đủ một lần, có thể bổ sung unique index trên `reversal_of` khi khác `NULL`, và chỉ tạo journal đảo sau khi kiểm tra journal gốc. Nếu cho phép điều chỉnh một phần, phải theo dõi phần đã điều chỉnh và khóa dữ liệu gốc khi kiểm tra tổng; không dùng ràng buộc “một lần” cho mô hình đó.

**Đảo bút toán không đồng nghĩa với hoàn tiền thực tế.** Hoàn tiền là một nghiệp vụ riêng, có quyền, trạng thái và bằng chứng từ hệ thống thanh toán. Không để người dùng gọi “reverse ledger” để nhận tiền từ nhà cung cấp mà không qua hạn mức hoàn tiền.

Nếu kỳ cũ đã khóa, journal điều chỉnh phải tuân thủ chính sách kỳ hiện hành và quyền mở kỳ. Lưu riêng thời điểm sự kiện, thời điểm ghi sổ và ngày hiệu lực khi cần; không cho caller tùy ý sửa `posted_at` để giấu một thao tác ghi lùi ngày.

## 12. Bất biến lịch sử, audit và giới hạn của hash

Một thiết kế append-only cần được bảo vệ ở nhiều ranh giới:

- Vai trò runtime không có quyền `UPDATE`, `DELETE`, `TRUNCATE` hoặc sửa schema ledger.
- Hàm posting chỉ cho thêm journal mới; không cho thêm line vào journal cũ.
- Vai trò triển khai, bảo trì và khôi phục dữ liệu được tách và có audit phù hợp.
- Bằng chứng gốc, bản sao lưu và quy trình phục hồi được kiểm tra để bảo toàn liên kết nghiệp vụ.

Nếu chỉ cấm `UPDATE` và `DELETE` nhưng vẫn cho chèn thêm line vào journal đã commit, lịch sử vẫn bị thay đổi. Nếu tài khoản ứng dụng là chủ bảng hoặc có thể vô hiệu hóa trigger, một trigger chặn sửa cũng không tạo được ranh giới quyền cần thiết.

Thông tin truy vết nên bao gồm journal ID, nguồn kinh tế, tenant/book, actor hoặc service principal, người duyệt, phiên bản dữ liệu, phiên bản chính sách, thời điểm và liên kết điều chỉnh. Audit không nên chứa token truy cập, khóa bí mật hay dữ liệu thanh toán nhạy cảm không cần thiết.

Hash nội dung có thể giúp phát hiện thay đổi so với một giá trị tin cậy. Tuy nhiên, nếu kẻ tấn công sửa được cả dữ liệu lẫn hash nằm cùng DB, họ có thể tính lại hash. Hash chain cũng cần quy tắc tuần tự hóa, chuẩn hóa nội dung và một điểm neo tin cậy ngoài phạm vi sửa đó nếu mục tiêu là phát hiện can thiệp đặc quyền.

Vì vậy, hash không thay thế kiểm soát quyền, transaction, idempotency hoặc đối soát. Nó cũng không chứng minh một khoản thu là hợp lệ về nghiệp vụ.

## 13. Outbox, số dư tổng hợp và đối soát

### 13.1. Công bố sự kiện sau ghi sổ

Nếu code ghi journal rồi gửi trực tiếp message, có hai cửa sổ lỗi:

```text
Gửi message trước commit → consumer thấy sự kiện nhưng DB rollback.
Commit trước khi gửi → tiến trình chết, journal tồn tại nhưng thiếu message.
```

Transactional outbox lưu journal và bản tin cần gửi trong cùng transaction. Worker phát bản tin từ outbox sau commit và có thể phát lại khi retry. Consumer cần inbox/dedup theo danh tính sự kiện; outbox không biến việc giao nhận thành đúng một lần.

Nếu consumer cập nhật balance projection trong DB riêng, việc ghi nhận “đã xử lý message” và thay đổi projection cần nguyên tử tại DB đó. Nếu projection chỉ phục vụ đọc, phải chấp nhận và hiển thị độ trễ phù hợp. Nếu nó quyết định chi tiền, phải có giao thức nhất quán đủ mạnh cho invariant số dư.

### 13.2. Đối soát cấu trúc

Truy vấn sau phát hiện journal thiếu dòng hoặc lệch Nợ/Có trong mô hình một loại tiền mỗi book:

```sql
SELECT
    j.journal_id,
    COUNT(l.line_no) AS line_count,
    COALESCE(SUM(
        CASE WHEN l.side = 'D'
             THEN l.amount_minor
             ELSE -l.amount_minor
        END
    ), 0) AS net_minor
FROM ledger_journal j
LEFT JOIN ledger_line l ON l.journal_id = j.journal_id
GROUP BY j.journal_id
HAVING COUNT(l.line_no) < 2
    OR COALESCE(SUM(
        CASE WHEN l.side = 'D'
             THEN l.amount_minor
             ELSE -l.amount_minor
        END
    ), 0) <> 0;
```

Đây là kiểm tra phát hiện trên dữ liệu đã lưu, không thay thế hàng rào ngăn commit sai. Một hệ thống chỉ phát hiện journal mất cân đối vào cuối ngày vẫn có thể cho người dùng chi số tiền sai trong cả ngày đó.

### 13.3. Đối soát ý nghĩa nghiệp vụ

Ngoài kiểm tra cân bằng, cần tìm:

- Sự kiện thanh toán thành công chưa có journal tương ứng.
- Journal không có bằng chứng nguồn hợp lệ hoặc gắn nhầm merchant.
- Số tiền/loại tiền giữa nguồn nghiệp vụ, ledger và nhà cung cấp không khớp.
- Tổng hoàn tiền vượt capture hoặc số dư tổng hợp khác kết quả dựng lại từ ledger.
- Journal điều chỉnh thiếu liên kết, lý do hoặc phê duyệt.
- Outbox bị kẹt, consumer bỏ sót hoặc projection bị áp dụng trùng.

Phải đối chiếu tại cùng mốc cắt dữ liệu hoặc cùng watermark; so sánh hai tập dữ liệu ở hai thời điểm khác nhau có thể tạo cảnh báo giả do độ trễ. Phí, giao dịch đang xử lý và thời điểm settlement cần quy tắc đối chiếu riêng.

Khi phát hiện sai lệch, giữ bằng chứng và cô lập luồng gây lỗi theo mức ảnh hưởng. Không tự xóa journal hoặc tạo khoản bù không có phê duyệt chỉ để bảng đối soát trở về số không.

## 14. Kiểm thử các tình huống tấn công logic

Kiểm thử nên xác nhận trạng thái dữ liệu đã commit và hiệu ứng tiền, không chỉ mã HTTP. Những invariant liên quan DB, quyền và cạnh tranh cần được kiểm chứng trên môi trường có cơ chế transaction/constraint tương ứng.

| Tình huống | Kết quả bắt buộc |
| --- | --- |
| Sửa amount hoặc chèn trường account vào request | Không làm thay đổi số tiền/tài khoản do server xác định; trường ngoài hợp đồng bị xử lý rõ ràng |
| Dùng order của tenant khác | Bị từ chối; không có journal và không lộ kết quả idempotency |
| Dùng account của book khác nhưng cùng currency | Bị từ chối bởi chính sách và/hoặc khóa ngoại; không có dữ liệu dở dang |
| Cố ghi sổ hồ sơ chưa duyệt hoặc đã đổi sau duyệt | Bị từ chối dựa trên trạng thái/phiên bản đã khóa |
| Hai request đồng thời, cùng key và cùng command | Cùng một kết quả nghiệp vụ; tối đa một journal |
| Cùng key nhưng command khác | Bị từ chối; không thay kết quả đã lưu |
| Hai key khác nhau, cùng capture hợp lệ | Một journal cho capture đó |
| Webhook ID khác nhau nhưng cùng sự kiện kinh tế | Không ghi sổ trùng |
| Cùng danh tính nguồn nhưng amount/currency khác | Không coi là retry bình thường; từ chối và ghi nhận xung đột |
| Tiến trình lỗi sau một dòng entry | Toàn bộ journal và thay đổi số dư rollback |
| Commit thành công rồi mất HTTP response | Retry trả journal cũ; không ghi lần hai |
| Hai lần rút 80.000 từ 100.000 đồng thời | Không thể cả hai được chấp nhận nếu chính sách cấm thấu chi |
| Hai lần hoàn tiền cùng vượt phần còn lại | Không thể commit tổng hoàn vượt hạn mức |
| Chèn số âm, số không, phần lẻ sai scale hoặc vượt miền | Bị từ chối trước khi tạo hiệu ứng tiền |
| Sửa/xóa/thêm line vào journal cũ bằng vai trò runtime | Bị ngăn; lịch sử cũ không đổi |
| Đảo cùng journal hai lần khi chỉ cho đảo một lần | Chỉ một lần đảo được chấp nhận |
| Outbox phát lại cùng bản tin | Projection hoặc consumer không áp dụng hiệu ứng trùng |
| Ghi sổ vào kỳ đã khóa | Bị từ chối hoặc đi qua đúng quy trình được cấp quyền |

Với kiểm thử đồng thời, dùng điểm đồng bộ để hai luồng cùng đi tới vị trí nhạy cảm, rồi kiểm tra kết quả trong DB sau khi cả hai kết thúc. Gửi hai request nối tiếp không chứng minh được rằng hệ thống chống được race condition.

Có thể bổ sung kiểm thử sinh dữ liệu cho kế hoạch hạch toán: mọi kế hoạch hợp lệ phải cân trong đúng book/currency; phép đảo đầy đủ phải triệt tiêu ảnh hưởng của journal gốc; replay không tăng số journal của cùng sự kiện. Các kiểm thử này hỗ trợ phát hiện lỗi quy tắc nhưng không thay thế kiểm thử quyền và transaction thực tế.

## 15. Những dấu hiệu thiết kế cần xem lại

| Dấu hiệu | Vấn đề cần giải quyết |
| --- | --- |
| API nhận trực tiếp danh sách account và amount từ mọi người dùng | Ranh giới tin cậy quá rộng; cần command nghiệp vụ và quyền chuyên biệt |
| Chỉ kiểm tra tổng debit bằng tổng credit | Chưa bảo vệ nguồn, đối tượng, trạng thái và chống trùng |
| Mỗi entry được `save()` trong transaction riêng | Có thể commit journal một phần |
| Tìm journal trước rồi insert, không có unique nghiệp vụ | Hai request có thể cùng vượt qua kiểm tra |
| Có unique idempotency key nhưng không có unique sự kiện | Đổi key vẫn tạo hiệu ứng trùng |
| Dựa vào cache để kiểm tra đủ tiền | Dữ liệu chậm có thể cho phép chi vượt |
| Dùng request time làm thời điểm ghi sổ | Caller có thể can thiệp kỳ hoặc dấu vết thời gian |
| Sửa số tiền cũ để “khớp đối soát” | Mất lịch sử và che nguyên nhân sai lệch |
| Tự thêm dòng bù cho mọi chênh lệch | Che lỗi tiền tệ, làm tròn hoặc gian lận |
| Cho rằng webhook có chữ ký thì không cần kiểm tra lại | Thiếu chống phát lại và so khớp nghiệp vụ |

Một luồng posting đạt yêu cầu khi có thể giải thích được: **sự kiện nào tạo khoản tiền, ai có quyền thực hiện, chính sách nào tạo các dòng, vì sao thao tác chỉ có một hiệu ứng, và bằng cách nào mọi thay đổi liên quan cùng commit hoặc cùng rollback**. Những bằng chứng này phải tồn tại cả trong thiết kế lẫn dữ liệu đã ghi sổ.
