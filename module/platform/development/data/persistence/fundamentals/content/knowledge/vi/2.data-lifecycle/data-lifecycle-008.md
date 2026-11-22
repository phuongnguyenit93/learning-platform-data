# Phân biệt ghi mới, ghi đè và bổ sung vào nhật ký

Trong vòng đời dữ liệu, ứng dụng không chỉ cần biết **lưu dữ liệu ở đâu** mà còn phải xác định **đang tạo dữ liệu mới, thay đổi trạng thái hiện tại hay ghi thêm dấu vết của một sự kiện**. Ba hành vi đó thường được gọi là **ghi mới (create/insert)**, **ghi đè (overwrite/replace/update trạng thái)** và **bổ sung vào nhật ký (append to log)**.

Bài học thuộc chương **Vòng đời dữ liệu** của module `DATA_PERSISTENCE_FUNDAMENTALS`. Phân biệt ba cách ghi là bước đầu để chọn mô hình dữ liệu và lược đồ, thiết kế truy vấn và chỉ mục, kiểm soát giao dịch và đồng thời trong Java, xử lý lỗi kết nối, tiến hóa schema, bảo mật, sao lưu và tối ưu hiệu năng.

## 1. Một tình huống, ba cách ghi

Giả sử ứng dụng quản lý điểm tích lũy của khách hàng. Khách hàng có mã `101`, mở tài khoản với **100 điểm**, rồi nhận thêm **20 điểm** sau một giao dịch.

Ứng dụng có thể thực hiện ba hành động khác nhau:

1. **Ghi mới:** tạo bản ghi tài khoản `101` với số dư 100 điểm.
2. **Ghi đè/cập nhật:** thay trạng thái số dư hiện tại của tài khoản từ 100 thành 120 điểm.
3. **Bổ sung vào nhật ký:** thêm sự kiện “tài khoản 101 được cộng 20 điểm” vào lịch sử, không sửa lại sự kiện cũ.

| Cách ghi | Dữ liệu xuất hiện sau thao tác | Điều ứng dụng chủ yếu cần |
| --- | --- | --- |
| Ghi mới | Một bản ghi hoặc tài nguyên chưa tồn tại trước đó | Tạo định danh, kiểm soát trùng lặp, thiết lập trạng thái ban đầu |
| Ghi đè | Giá trị hiện hành tại một vị trí/định danh được thay bằng giá trị mới | Duy trì trạng thái mới nhất, ngăn ghi đè nhầm thay đổi của người khác |
| Bổ sung nhật ký | Thêm một mục mới sau các mục đã có; lịch sử trước đó được giữ nguyên về mặt logic | Lưu diễn biến, truy vết hoặc tái dựng trạng thái theo thứ tự sự kiện |

Ba hành động không nhất thiết loại trừ nhau. Trong một giao dịch, ứng dụng có thể **cập nhật bản ghi tài khoản hiện tại và đồng thời chèn một bản ghi lịch sử**. Ngược lại, một hệ thống theo mô hình *event sourcing* có thể giữ nhật ký sự kiện làm nguồn dữ liệu chính rồi tính số dư hiện tại từ các sự kiện đó.

~~~mermaid
flowchart TD
    A["Yêu cầu thay đổi dữ liệu"] --> B{"Mục tiêu là gì?"}
    B -->|"Đối tượng chưa tồn tại"| C["Ghi mới: INSERT / CREATE_NEW"]
    B -->|"Đổi trạng thái hiện tại"| D["Ghi đè: UPDATE / REPLACE"]
    B -->|"Giữ thêm một sự kiện"| E["Append: thêm bản ghi nhật ký"]
    D --> F["Trạng thái hiện tại"]
    C --> F
    E --> G["Lịch sử có thứ tự"]
    G -->|"Có thể tính lại"| F
~~~

Sơ đồ mô tả **ý nghĩa logic của thao tác**. Ở tầng vật lý, hệ quản trị cơ sở dữ liệu có thể dùng nhật ký ghi trước, trang dữ liệu, phiên bản bản ghi hoặc cấu trúc lưu trữ khác ngay cả khi ứng dụng gọi một lệnh `UPDATE`.

## 2. Ghi mới: tạo một bản ghi hoặc tài nguyên chưa có

**Ghi mới** là thao tác tạo dữ liệu với một định danh mới hoặc tạo một tài nguyên ở vị trí chưa tồn tại. Trong cơ sở dữ liệu quan hệ, cách phổ biến là `INSERT`; với tệp, có thể dùng chế độ tạo tệp mới.

Ví dụ bảng tài khoản:

~~~sql
CREATE TABLE point_accounts (
    account_id BIGINT PRIMARY KEY,
    points     BIGINT NOT NULL CHECK (points >= 0),
    version    BIGINT NOT NULL DEFAULT 0
);
~~~

Ghi mới tài khoản:

~~~sql
INSERT INTO point_accounts (account_id, points, version)
VALUES (101, 100, 0);
~~~

Nếu bảng chưa có bản ghi `account_id = 101` và ràng buộc đều hợp lệ, lệnh tạo ra một hàng mới. Thực hiện lại cùng lệnh với cùng khóa chính sẽ bị từ chối bởi ràng buộc `PRIMARY KEY`. Đây là cơ chế quan trọng giúp ứng dụng không vô tình tạo hai đối tượng có cùng định danh.

### Tạo mới khác với “ghi nếu chưa có”

Một sai lầm phổ biến là:

1. Đọc dữ liệu để xem `account_id = 101` đã tồn tại chưa.
2. Nếu chưa thấy thì chèn bản ghi.

Giữa hai bước, một yêu cầu đồng thời khác vẫn có thể chèn cùng khóa. Do đó, kiểm tra ở ứng dụng **không thay thế** khóa duy nhất hoặc cơ chế chèn có điều kiện tại kho dữ liệu.

Tùy hệ quản trị, ứng dụng có thể sử dụng `INSERT` cùng ràng buộc duy nhất, hoặc cú pháp *upsert* như `INSERT ... ON CONFLICT`. Tuy nhiên, **upsert là quy tắc “chèn nếu chưa có, xử lý xung đột nếu đã có”**, không hoàn toàn đồng nghĩa với “chỉ tạo mới”. Cần quyết định trường hợp trùng khóa phải báo lỗi, giữ nguyên hay cập nhật.

### Những câu hỏi quan trọng khi ghi mới

- **Định danh do ai tạo?** Ứng dụng, cơ sở dữ liệu hay dịch vụ cấp ID?
- **Giá trị ban đầu hợp lệ chưa?** Kiểu dữ liệu, khóa ngoại, `NOT NULL`, `CHECK` và quy tắc nghiệp vụ có được đáp ứng?
- **Yêu cầu bị gửi lại thì sao?** Lỗi mạng sau khi lệnh thành công có thể khiến client thử lại; cần xử lý khóa duy nhất hoặc idempotency key.
- **Có thao tác khác phải đi kèm?** Tạo tài khoản cùng hồ sơ khách hàng có thể cần một giao dịch nếu cùng nằm trong một cơ sở dữ liệu.

Ghi mới không có nghĩa là mọi dữ liệu đều không thể sửa sau này. Nó chỉ mô tả hành động **tạo một đơn vị dữ liệu mới ở thời điểm thực hiện**.

## 3. Ghi đè: thay giá trị hiện tại của dữ liệu đã tồn tại

**Ghi đè (overwrite)** là thao tác thay nội dung đang được lưu ở một vị trí hoặc định danh bằng nội dung mới. Ở góc nhìn nghiệp vụ, mục tiêu là lấy **trạng thái hiện tại** thay vì giữ tất cả trạng thái cũ ngay trong cùng bản ghi.

Ví dụ cộng 20 điểm và lưu số dư mới:

~~~sql
UPDATE point_accounts
SET points = 120
WHERE account_id = 101;
~~~

Nếu tài khoản tồn tại, giá trị `points` được thay bằng 120. Tuy nhiên, câu lệnh trên **không tự ghi lịch sử thay đổi**, và có thể ghi đè nhầm nếu một giao dịch khác vừa cập nhật tài khoản.

Trong ngôn ngữ SQL cần phân biệt:

- **Thay toàn bộ bản ghi ở cấp nghiệp vụ:** giá trị hiện tại được xây dựng lại từ một đối tượng/phiên bản mới.
- **Cập nhật một số cột:** `UPDATE` chỉ thay những cột được chỉ định; các cột khác vẫn giữ nguyên về mặt logic.
- **Cập nhật theo biến thiên:** `SET points = points + 20` cập nhật từ giá trị hiện tại trong cơ sở dữ liệu; thường phù hợp hơn việc đọc về Java, tự cộng rồi ghi một số cũ.
- **Ghi đè tệp:** thay toàn bộ nội dung tệp hiện có; nếu ghi lỗi giữa chừng, tệp có thể bị cắt ngắn hoặc chứa nội dung chưa hoàn chỉnh nếu không có quy trình thay thế an toàn.

### Ghi đè và nguy cơ lost update

Xét hai yêu cầu cùng đọc 100 điểm:

| Thời điểm | Yêu cầu A | Yêu cầu B |
| --- | --- | --- |
| 1 | Đọc 100 điểm | Đọc 100 điểm |
| 2 | Tính 100 + 20 = 120 | Tính 100 + 30 = 130 |
| 3 | Ghi `points = 120` | Chưa ghi |
| 4 | Đã hoàn thành | Ghi `points = 130` |

Nếu cả hai cùng ghi giá trị đã tính từ dữ liệu cũ mà không kiểm soát đồng thời, kết quả cuối có thể là **130**, trong khi nghiệp vụ mong đợi **150**. Đây là hiện tượng *lost update*.

Một cách bảo vệ là **optimistic locking** với cột phiên bản:

~~~sql
UPDATE point_accounts
SET points = points + 20,
    version = version + 1
WHERE account_id = 101
  AND version = 0;
~~~

Ứng dụng phải kiểm tra số hàng được cập nhật:

- **1 hàng:** cập nhật thành công với phiên bản đã kỳ vọng.
- **0 hàng:** tài khoản không tồn tại hoặc phiên bản đã thay đổi; cần đọc lại, báo xung đột hoặc thử lại theo quy tắc nghiệp vụ, không được coi là thành công.

Cách này là một ví dụ; cơ sở dữ liệu còn có khóa hàng và các mức cô lập giao dịch khác nhau. Dù dùng cơ chế nào, mục tiêu vẫn là ngăn trạng thái hiện tại bị một yêu cầu dựa trên dữ liệu cũ ghi đè sai.

### Ghi đè không có nghĩa dữ liệu cũ biến mất hoàn toàn

Sau một lệnh `UPDATE`, người dùng thông thường nhìn thấy giá trị mới theo quy tắc cô lập. Nhưng hệ quản trị có thể vẫn giữ **phiên bản cũ**, **WAL/redo log**, **bản sao lưu** hoặc dữ liệu trên replica trong một thời gian. Vì thế, “ghi đè” trong bài là **thay đổi trạng thái nhìn thấy ở cấp logic**, không phải lời bảo đảm rằng mọi byte của trạng thái cũ đã bị xóa vật lý.

Tương tự, việc ghi đè giá trị nghiệp vụ không tự giải quyết quyền xóa dữ liệu cá nhân, thời hạn lưu giữ và dọn dẹp bản sao lưu.

## 4. Bổ sung vào nhật ký: ghi thêm mà giữ các mục trước

**Bổ sung vào nhật ký (append to log)** là thao tác thêm một mục mới vào cuối một chuỗi mục đã được lưu. Về mặt logic, các mục trước không bị thay đổi khi thêm mục mới. Một nhật ký thường chứa **sự kiện đã xảy ra**, **thời điểm**, **định danh nguồn**, **thứ tự** và **thông tin giúp kiểm tra hoặc tái dựng trạng thái**.

Ví dụ lịch sử tài khoản:

~~~text
Sự kiện 1: ACCOUNT_OPENED      account=101, initialPoints=100
Sự kiện 2: POINTS_ADDED        account=101, delta=+20
Sự kiện 3: POINTS_REDEEMED     account=101, delta=-30
~~~

Nếu diễn giải các sự kiện này theo đúng thứ tự, số dư được tính là:

~~~text
100 + 20 - 30 = 90 điểm
~~~

Không cần sửa sự kiện 1 thành “số dư 90”. Thay vào đó, ứng dụng bổ sung thêm một sự kiện mới. Đây là ý tưởng căn bản của **append-only event log**.

### Nhật ký chỉ bổ sung và sự kiện nghiệp vụ

Một bảng lưu lịch sử có thể được định nghĩa như sau:

~~~sql
CREATE TABLE point_events (
    event_id      VARCHAR(64) PRIMARY KEY,
    account_id    BIGINT NOT NULL REFERENCES point_accounts(account_id),
    delta_points  BIGINT NOT NULL CHECK (delta_points <> 0),
    points_after  BIGINT NOT NULL CHECK (points_after >= 0),
    occurred_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Thêm sự kiện:

~~~sql
INSERT INTO point_events
    (event_id, account_id, delta_points, points_after)
VALUES
    ('earn-101-001', 101, 20, 120);
~~~

Mỗi sự kiện được lưu thành **một bản ghi mới** trong `point_events`. Bảng đó dùng `INSERT` để thực hiện **append ở mức nghiệp vụ**; ứng dụng phải có quy ước hạn chế sửa/xóa những sự kiện đã ghi nếu muốn bảo đảm lịch sử bất biến.

Cần lưu ý: **bảng SQL chỉ có `INSERT` không mặc nhiên bảo đảm thứ tự toàn cục theo thời gian**. Thứ tự truy vấn chỉ xác định khi có `ORDER BY` trên trường thích hợp. Các sự kiện đồng thời còn cần khóa phiên bản, số thứ tự theo tài khoản hoặc cơ chế sắp thứ tự. Mốc `occurred_at` một mình không đủ làm khóa thứ tự đáng tin cậy trong mọi trường hợp.

### Nhật ký có nhiều mục đích khác nhau

Từ “nhật ký” dễ gây nhầm vì ít nhất bốn loại sau có vai trò khác nhau:

| Loại nhật ký | Ai quản lý, chứa gì? | Dùng để làm gì? |
| --- | --- | --- |
| **Nhật ký sự kiện nghiệp vụ (event log)** | Ứng dụng lưu sự kiện như “cộng điểm”, “xác nhận đơn hàng” | Lưu diễn biến nghiệp vụ; có thể dùng để dựng lại trạng thái |
| **Audit log** | Ứng dụng/hệ thống ghi “ai làm gì, lúc nào, với đối tượng nào” | Truy vết, điều tra thay đổi, đáp ứng yêu cầu kiểm soát |
| **Write-ahead log (WAL)/redo log** | Hệ quản trị lưu thông tin phục vụ khôi phục và tính bền vững | Hỗ trợ phục hồi sau lỗi và cơ chế giao dịch; không phải API sự kiện nghiệp vụ |
| **Application/diagnostic log** | Ứng dụng ghi thông báo, cảnh báo, lỗi, thời gian xử lý | Quan sát và chẩn đoán vận hành; thường có chính sách xoay vòng, lưu giữ riêng |

**Không được suy ra** “đã có WAL thì đã có audit log”, hoặc “ghi dòng `logger.info()` là đã persist được giao dịch nghiệp vụ”. Những loại nhật ký này có cấu trúc, vòng đời, quyền truy cập, mức bảo đảm và khả năng truy vấn khác nhau.

## 5. Kết hợp ghi đè trạng thái hiện tại và append lịch sử

Một thiết kế rất phổ biến là duy trì đồng thời:

- Bảng `point_accounts` chứa **số dư hiện tại**, thuận tiện đọc nhanh.
- Bảng `point_events` chứa **lịch sử thay đổi**, thuận tiện đối soát và truy vết.

Với yêu cầu cộng 20 điểm cho tài khoản 101 đang có 100 điểm và `version = 0`, có thể dùng một giao dịch:

~~~sql
BEGIN;

UPDATE point_accounts
SET points = points + 20,
    version = version + 1
WHERE account_id = 101
  AND version = 0;
-- Ứng dụng bắt buộc kiểm tra đúng 1 hàng được cập nhật.

INSERT INTO point_events
    (event_id, account_id, delta_points, points_after)
VALUES
    ('earn-101-001', 101, 20, 120);

COMMIT;
~~~

**Đây là luồng minh họa, không phải script đủ an toàn để chạy mù quáng.** Sau lệnh `UPDATE`, ứng dụng phải xác minh có đúng một hàng bị ảnh hưởng. Nếu không đúng, phải **`ROLLBACK`** và không thực hiện lệnh thêm sự kiện hoặc `COMMIT`. Nếu chèn nhật ký thất bại (ví dụ trùng `event_id`), cũng phải hủy giao dịch. Trạng thái ban đầu, phiên bản kỳ vọng và `points_after` phải được tính đúng theo cùng nghiệp vụ.

Khi **cả cập nhật và ghi lịch sử trong cùng một giao dịch database**, hệ quản trị hỗ trợ atomicity sẽ xác nhận hoặc hủy chúng cùng nhau. Không nên cập nhật bảng hiện tại thành công rồi ghi log ở một kết nối/giao dịch khác nếu nghiệp vụ yêu cầu tính đồng bộ tuyệt đối: hỏng kết nối ở giữa có thể khiến số dư và lịch sử không khớp.

### Giao dịch, retry và idempotency

Có hai điểm dễ bị bỏ sót:

1. Nếu client mất kết nối ngay lúc `COMMIT`, nó có thể **không biết** giao dịch đã được xác nhận hay chưa. Gửi lại yêu cầu cộng 20 điểm có nguy cơ cộng hai lần.
2. Nếu nhật ký được thêm nhiều lần cho cùng yêu cầu, dữ liệu lịch sử có thể lặp dù thao tác ghi append mỗi lần đều thành công.

Một **mã yêu cầu/sự kiện duy nhất**, ví dụ `earn-101-001`, cùng **ràng buộc unique** và luồng kiểm tra trạng thái giúp thiết kế thao tác *idempotent* (thực hiện lặp lại không gây thêm tác dụng nghiệp vụ). Chỉ thêm khóa duy nhất vào bảng log chưa giải quyết trọn vẹn lỗi nếu cập nhật số dư và chèn log diễn ra ngoài cùng giao dịch.

### Cẩn thận khi nói “ghi đè và append luôn đi cùng nhau”

Đây là **một lựa chọn thiết kế**, không phải quy tắc bắt buộc. Một ứng dụng chỉ cần trạng thái mới nhất có thể lưu mỗi bản ghi hiện tại. Một hệ theo event sourcing có thể dùng **sự kiện là nguồn sự thật** và duy trì snapshot/projection được tái tạo từ log. Mỗi mô hình có chi phí truy vấn, phục hồi và nhất quán khác nhau.

## 6. Cùng ba cách ghi dưới góc nhìn tệp trong Java

Không chỉ database, Java NIO cũng cung cấp các chế độ tạo mới, thay thế nội dung và nối thêm nội dung. Ví dụ dưới đây minh họa cú pháp, giả định thư mục hiện tại có quyền ghi và các file ở trạng thái như mô tả:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

class WriteModesDemo {
    public static void main(String[] args) throws Exception {
        Path snapshot = Path.of("account-101.txt");

        // 1. Ghi mới: chỉ tạo nếu file chưa tồn tại.
        Files.writeString(
            snapshot,
            "100",
            StandardCharsets.UTF_8,
            StandardOpenOption.CREATE_NEW
        );

        // 2. Ghi đè: thay nội dung file đã tồn tại bằng "120".
        Files.writeString(
            snapshot,
            "120",
            StandardCharsets.UTF_8,
            StandardOpenOption.WRITE,
            StandardOpenOption.TRUNCATE_EXISTING
        );

        // 3. Bổ sung nhật ký: thêm một dòng JSONL vào cuối file.
        Path journal = Path.of("account-events.jsonl");
        Files.writeString(
            journal,
            "{\"eventId\":\"earn-101-001\",\"delta\":20,\"pointsAfter\":120}\n",
            StandardCharsets.UTF_8,
            StandardOpenOption.CREATE,
            StandardOpenOption.APPEND
        );
    }
}
~~~

Ý nghĩa các option:

| Tùy chọn | Hành vi nổi bật |
| --- | --- |
| `CREATE_NEW` | Tạo tệp mới, thất bại nếu tệp đã tồn tại; tránh ghi đè tệp cũ khi khởi tạo |
| `WRITE` | Mở để ghi |
| `TRUNCATE_EXISTING` | Cắt ngắn tệp hiện có khi mở để ghi, sau đó ghi nội dung mới |
| `CREATE` | Tạo tệp nếu chưa có, nếu có thì sử dụng tệp hiện tại |
| `APPEND` | Đưa dữ liệu được ghi vào cuối tệp theo chế độ mở append |

**Giới hạn quan trọng của ví dụ:** các thao tác NIO độc lập trên hai file **không tạo thành một giao dịch nguyên tử**. Nếu ứng dụng hỏng sau khi ghi snapshot nhưng trước khi append log, hai nguồn có thể lệch nhau. Với nhiều tiến trình ghi đồng thời, không được giả định mỗi lời gọi `writeString` luôn làm một bản ghi JSONL xuất hiện nguyên vẹn, không xen kẽ, theo đúng thứ tự mong muốn. Một lỗi giữa lúc ghi có thể gây dòng nhật ký dở dang.

Khi xây dựng giải pháp lưu tệp thật, cần xem xét khóa/điều phối người ghi, kiểm tra bản ghi dở, flush/sync theo yêu cầu, ghi vào tệp tạm rồi thay thế bằng thao tác chuyển tên nguyên tử nếu nền tảng hỗ trợ, và quy trình khôi phục. `Files.writeString` hoàn thành cũng không mặc nhiên đồng nghĩa với **fsync** đã hoàn tất trên mọi hệ thống tệp.

### Nhật ký JSON Lines và khả năng phát lại

Định dạng JSONL (mỗi dòng là một đối tượng JSON) thuận tiện cho việc append và đọc tuần tự:

~~~json
{"eventId":"open-101","kind":"ACCOUNT_OPENED","initialPoints":100}
{"eventId":"earn-101-001","kind":"POINTS_ADDED","delta":20}
{"eventId":"spend-101-001","kind":"POINTS_REDEEMED","delta":-30}
~~~

Khi phát lại, bộ xử lý phải biết loại sự kiện, kiểm tra tính hợp lệ, loại bỏ trùng lặp và áp dụng theo **thứ tự xác định**. Nếu file hỏng nửa dòng cuối hoặc thiếu một sự kiện, trạng thái tái dựng có thể sai. Do đó, nhật ký để phát lại lâu dài cần thêm quy ước schema, phiên bản, định danh, thứ tự, kiểm tra tính toàn vẹn và phục hồi.

## 7. Nhật ký chỉ bổ sung có phải luôn là nguồn dữ liệu chính?

Không. Có ít nhất ba mô hình:

### Mô hình A — Chỉ lưu trạng thái hiện tại

~~~text
account 101 -> points=120
~~~

Mỗi lần thay đổi, hệ thống cập nhật bản ghi hiện tại. Cách này đơn giản, đọc nhanh, nhưng thông tin về quá trình thay đổi thường bị mất nếu không có nguồn lịch sử khác.

### Mô hình B — Trạng thái hiện tại kèm lịch sử

~~~text
Current state: account 101 -> points=120

History:
  opened at 100
  added 20
~~~

Bảng hiện tại được cập nhật, nhật ký được append trong cùng giao dịch. Phù hợp khi chức năng cần đọc số dư nhanh và vẫn cần truy vết.

### Mô hình C — Event sourcing

~~~text
Event stream:
  ACCOUNT_OPENED(100)
  POINTS_ADDED(+20)

Projection / snapshot:
  points=120
~~~

Chuỗi sự kiện là **nguồn dữ liệu chính**; trạng thái hiện tại là kết quả tính từ các sự kiện. Việc tính lại toàn bộ có thể tốn kém, nên ứng dụng thường xây dựng projection và tạo snapshot định kỳ. Khi có thay đổi logic xử lý sự kiện hoặc schema, phải xem xét khả năng phát lại sự kiện cũ một cách tương thích.

### Snapshot khác append log

**Snapshot** là ảnh chụp trạng thái tại một thời điểm, phục vụ khôi phục hoặc tăng tốc đọc. Snapshot mới thường thay thế hoặc bổ sung phiên bản snapshot trước theo chính sách lưu trữ. **Log** mô tả các thay đổi/sự kiện theo thời gian. Để dựng lại trạng thái, có thể lấy snapshot ở phiên bản `N` rồi phát lại các sự kiện từ `N+1`.

Một bản snapshot **không thay thế** khả năng ghi nhận những thay đổi xảy ra sau thời điểm chụp; cũng không nên xem mọi log là đủ để phục hồi nếu thiếu quy tắc thứ tự, retention, backup và kiểm tra toàn vẹn.

## 8. So sánh tính đúng đắn, đồng thời và thử lại

| Tiêu chí | Ghi mới | Ghi đè | Append nhật ký |
| --- | --- | --- | --- |
| Điều kiện thành công | Tạo đối tượng mới hợp lệ, không vi phạm khóa/ràng buộc | Đúng đối tượng, đúng phiên bản và giá trị mới hợp lệ | Sự kiện mới hợp lệ, có ID riêng và thứ tự phù hợp |
| Xung đột thường gặp | Trùng khóa hoặc tạo đồng thời | Lost update, ghi từ trạng thái cũ | Sự kiện trùng, thứ tự sai hoặc ghi dở |
| Kiểm soát ở database | Primary key, unique, foreign key, transaction | Điều kiện `WHERE`, version, lock, transaction | Unique event ID, transaction, version/sequence |
| Khi retry | Có thể gặp “đã tồn tại”; cần phân biệt đã xử lý với xung đột thật | `SET x = 10` có thể idempotent về trạng thái, nhưng `x = x + 10` thì không | Append cùng một sự kiện hai lần thường không idempotent nếu thiếu chống trùng |
| Truy vấn đặc trưng | Tìm bản ghi vừa tạo | Lấy trạng thái mới nhất | Xem lịch sử, truy vết hoặc phát lại |
| Dữ liệu cũ | Chưa tồn tại tại định danh mới | Không còn là trạng thái hiện tại ở mức logic | Thường được giữ lại theo chính sách nhật ký |
| Chi phí vận hành | Kiểm soát ID, tăng số bản ghi | Đồng bộ thay đổi, index, tranh chấp khóa | Log tăng liên tục, cần lưu giữ, phân vùng và dọn dẹp |

**Idempotency phụ thuộc ngữ nghĩa**, không chỉ tên thao tác. Chẳng hạn, ghi đè `points = 120` nhiều lần có thể cho cùng trạng thái cuối, nhưng vẫn có thể tạo nhiều audit event hoặc gây side effect nếu không thiết kế riêng. Ngược lại, `UPDATE points = points + 20` chạy lại là một thay đổi nghiệp vụ mới.

## 9. Hiệu năng, dung lượng và vòng đời dữ liệu

Ba cách ghi có tác động khác nhau:

**Ghi mới:** thường làm tăng số bản ghi và có thể tăng dung lượng index. Khi dữ liệu phát triển, cần thiết kế khóa, partition hoặc phân trang phù hợp. Việc tạo hàng mới có thể kéo theo ràng buộc khóa ngoại và chi phí index.

**Ghi đè:** thuận tiện cho truy vấn “trạng thái mới nhất”; nhưng cập nhật trên dữ liệu nhiều người cùng sửa dễ tranh chấp. Cập nhật các cột có index có thể làm tăng chi phí duy trì index. Ở hệ thống dùng MVCC, phiên bản cũ cần được dọn dẹp theo cơ chế riêng.

**Append nhật ký:** ghi tuần tự có thể thuận lợi cho throughput và audit, nhưng log tăng theo thời gian. Truy vấn “số dư hiện tại” bằng cách phát lại toàn bộ lịch sử có thể chậm; cần cân nhắc projection, snapshot, partition, index và retention. Append-only ở cấp nghiệp vụ không đồng nghĩa không bao giờ cần compact, archive hoặc xử lý xóa dữ liệu theo chính sách.

Các quyết định vòng đời cần được xác định sớm:

1. **Retention:** giữ trạng thái và nhật ký trong bao lâu, ai được phép xóa/ẩn?
2. **Schema evolution:** sự kiện cũ còn đọc được khi đổi tên trường hoặc quy tắc nghiệp vụ không?
3. **Backup/restore:** khôi phục nhất quán giữa bảng hiện tại, log và projection bằng cách nào?
4. **Quan sát vận hành:** theo dõi số lần ghi, xung đột phiên bản, retry, kích thước log, độ trễ append, sai lệch projection ra sao?
5. **Bảo mật:** dữ liệu nhạy cảm có bị ghi lặp vào log/audit không, ai có quyền truy cập và cách mã hóa/che giấu là gì?

Chọn cách ghi phụ thuộc vào yêu cầu nghiệp vụ và khả năng vận hành. Đừng sử dụng event log chỉ vì muốn “giữ mọi thứ”: cần xác định chính xác sự kiện nào có giá trị, chi phí lưu giữ và cơ chế bảo đảm đúng dữ liệu.

## 10. Những nhầm lẫn thường gặp

- **“`INSERT` là append, nên mọi ghi mới đều là ghi nhật ký.”** Không. `INSERT` tạo một hàng; chỉ khi hàng đó nằm trong cấu trúc có ngữ nghĩa giữ lịch sử/sự kiện thì mới là append nhật ký ở cấp nghiệp vụ.
- **“`UPDATE` luôn xóa dữ liệu cũ vật lý.”** Không. Hệ lưu trữ có thể giữ các phiên bản cũ, transaction log và bản sao lưu.
- **“Có nhật ký thì giao dịch không còn cần thiết.”** Sai. Cập nhật số dư và ghi sự kiện vào hai nơi riêng mà không có cơ chế nhất quán có thể khiến dữ liệu lệch nhau.
- **“Append luôn nhanh và không tranh chấp.”** Sai. Nhiều người ghi cùng luồng, duy trì thứ tự và index, đồng bộ đĩa hoặc replication vẫn có chi phí.
- **“`logger.info()` chính là audit log hoặc event sourcing.”** Không. Diagnostic log phục vụ vận hành, thường không có ràng buộc giao dịch, lược đồ và retention đủ để làm nguồn sự thật nghiệp vụ.
- **“Có thể retry thao tác cộng điểm như ghi đè cùng giá trị.”** Sai. Phép cộng dồn và append sự kiện đều có thể tạo tác dụng lặp; phải kiểm soát idempotency.
- **“Mốc thời gian là đủ để sắp thứ tự toàn bộ event.”** Không. Timestamp có thể trùng, độ chính xác giới hạn và sự kiện có thể đến muộn. Cần định nghĩa rõ thứ tự theo tài khoản/stream hoặc thứ tự cam kết nếu nghiệp vụ yêu cầu.

## 11. Bài tập và câu hỏi tự kiểm tra

**Câu 1.** Ứng dụng chưa có đơn hàng `order-42` và thực hiện `INSERT` tạo đơn hàng. Đây là cách ghi nào?

**Trả lời:** **Ghi mới**. Nếu đồng thời tạo một dòng lịch sử “đơn hàng được tạo”, dòng lịch sử đó là một thao tác append riêng.

**Câu 2.** Một API đọc số dư 100, cộng 20 trong Java rồi `UPDATE points = 120`. Trong khi đó yêu cầu khác vừa cộng 30. Rủi ro là gì?

**Trả lời:** **Lost update**. Cần điều kiện theo phiên bản, cập nhật cộng dồn trong database hoặc cơ chế khóa/giao dịch phù hợp để tránh ghi đè trạng thái mới hơn.

**Câu 3.** Ứng dụng thêm sự kiện `POINTS_ADDED(+20)` vào log. Có thể kết luận số dư hiện tại trong bảng tài khoản đã tăng 20 chưa?

**Trả lời:** Chưa. Nếu log là nguồn sự thật, cần có projection áp dụng sự kiện; nếu log chỉ là lịch sử bên cạnh bảng trạng thái, phải thực hiện cập nhật và append một cách nhất quán theo thiết kế.

**Câu 4.** File `account-events.jsonl` đã có một dòng và `Files.writeString(..., APPEND)` được gọi lần nữa. Thao tác có tự bảo đảm chống trùng event và ghi nguyên tử khi hai tiến trình cùng append không?

**Trả lời:** Không. Chế độ append chỉ mô tả vị trí ghi; ứng dụng vẫn cần chiến lược điều phối, kiểm tra bản ghi dở, xử lý trùng sự kiện và bảo đảm độ bền phù hợp.

**Câu 5.** Tại sao một database có WAL vẫn có thể cần bảng `point_events`?

**Trả lời:** WAL phục vụ cơ chế nội bộ của hệ quản trị và phục hồi giao dịch. Bảng `point_events` thể hiện sự kiện nghiệp vụ có định danh, quyền truy cập, mô hình dữ liệu và thời hạn lưu giữ do ứng dụng chủ động thiết kế.

**Câu 6.** Khách hàng gửi lại yêu cầu cộng 20 điểm sau khi client không nhận được phản hồi. Hãy nêu một thiết kế tối thiểu để tránh cộng lặp.

**Trả lời:** Gắn **request ID duy nhất**, lưu dấu đã xử lý với ràng buộc unique và cập nhật số dư cùng ghi dấu/sự kiện trong **một transaction**. Khi retry, tra lại kết quả của request ID thay vì cộng lại. Cần định nghĩa hành vi khi request ID cũ được gửi với nội dung khác.

**Bài tập thực hành:** Thiết kế chức năng “đổi địa chỉ giao hàng” và “theo dõi lịch sử thay đổi”. Xác định bản ghi tạo mới khi khách hàng lần đầu khai báo địa chỉ, các cột được cập nhật khi sửa địa chỉ, và thông tin cần append vào audit log. Sau đó mô tả ranh giới transaction, quy tắc chống lost update và cách xử lý nếu dịch vụ gửi yêu cầu hai lần. Nếu dùng Java NIO để lưu tệp thay cho database, hãy chỉ ra khả năng mất đồng bộ giữa snapshot và log.

Nhớ rằng **ghi mới** diễn đạt việc tạo đơn vị dữ liệu, **ghi đè** diễn đạt việc thay trạng thái hiện tại, còn **append nhật ký** diễn đạt việc giữ thêm diễn biến theo thời gian. Khi xây dựng persistence trong Java, hãy quyết định rõ cần **trạng thái**, **lịch sử**, hay **cả hai**, rồi chọn giao dịch, kiểm soát đồng thời và cơ chế phục hồi tương ứng.
