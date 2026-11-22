# text, varchar, ascii và Unicode trong Apache Cassandra

Khi thiết kế bảng **wide-column** trong Apache Cassandra, một cột chuỗi có thể là tên hiển thị, mã định danh, mã ngôn ngữ, dữ liệu nhập từ người dùng hoặc thành phần **partition key / clustering key**. Chọn `text`, `varchar` hay `ascii` không chỉ là quyết định lưu được ký tự nào. Nếu chuỗi tham gia khóa, cách **mã hóa và chuẩn hóa Unicode** quyết định hai yêu cầu tưởng như giống nhau có tìm được cùng một dòng dữ liệu hay không.

Bài thuộc chương **Kiểu dữ liệu** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**. Trong bối cảnh Cassandra phân tán, một lựa chọn kiểu chuỗi đúng phải hỗ trợ **thiết kế bảng theo truy vấn**, khóa phân vùng rõ ràng, thao tác CQL và kết nối từ Java. Mức nhất quán đọc/ghi, replication, compaction, repair hay retry không thể tự sửa lỗi nếu ứng dụng đã tạo hai khóa khác nhau chỉ vì khác chữ hoa, dấu tiếng Việt hoặc dạng biểu diễn Unicode.

## 1. So sánh text, varchar và ascii

| Tiêu chí | `text` | `varchar` | `ascii` |
|---|---|---|---|
| Tập ký tự | Unicode, mã hóa UTF-8 | **Đồng nghĩa với `text`** trong Cassandra | Chỉ ký tự ASCII 7 bit |
| Tiếng Việt có dấu, tiếng Nhật, emoji | Có | Có | Không |
| Chuỗi ASCII như `"SKU-001"` | Có | Có | Có |
| Khai báo giới hạn độ dài `varchar(255)` | Không áp dụng | **Không hỗ trợ kiểu độ dài như SQL truyền thống** | Không áp dụng |
| Java Driver 4.x | `String` | `String` | `String` |
| Cách dùng nên ưu tiên | Nội dung có thể có Unicode | Tương đương `text`, có thể dùng khi đọc schema quen với SQL | Mã được **cam kết chỉ chứa ASCII** |
| Rủi ro thường gặp | Nhầm thứ tự chữ theo ngôn ngữ; khóa chưa chuẩn hóa | Tưởng `varchar` giới hạn số ký tự | Người dùng nhập dấu/emoji gây lỗi dữ liệu không phù hợp kiểu |

**Kết luận kỹ thuật:** `text` và `varchar` là **alias**, tức cùng kiểu chuỗi UTF-8 trong Cassandra. Không có khác biệt về độ chính xác, miền Unicode hay khả năng tìm kiếm giữa hai tên này. `ascii` biểu diễn tập ký tự hẹp hơn và không dùng để lưu họ tên hoặc mô tả tiếng Việt.

Các kiểu chuỗi không làm công việc của **`uuid`**, **`timestamp`**, **`inet`** hoặc **`blob`**. Chẳng hạn, ID nhị phân UUID nên dùng `uuid` nếu các hệ thống thống nhất định dạng; nếu một “ID” là mã `"000127"` có số 0 đầu thì **`text`** hoặc `ascii` mới giữ nguyên ngữ nghĩa.

## 2. Unicode và UTF-8: điều Cassandra thực sự lưu

### 2.1. Ký tự, code point và số byte khác nhau

Unicode là hệ thống mã hóa ký tự trừu tượng; UTF-8 là một cách biểu diễn Unicode thành byte. Cassandra lưu `text`/`varchar` bằng UTF-8, trong đó một Unicode code point hợp lệ được mã hóa thành **1–4 byte**.

| Ví dụ | Ý nghĩa | Kích thước UTF-8 điển hình |
|---|---|---:|
| `A` | Ký tự ASCII U+0041 | 1 byte |
| `é` | U+00E9, chữ Latin có dấu | 2 byte |
| `ệ` | U+1EC7, chữ tiếng Việt | 3 byte |
| `😀` | U+1F600, emoji | 4 byte |
| `e` + dấu kết hợp `◌́` | Hai code point hiển thị thành một chữ có dấu | 1 + 2 = 3 byte trước chuẩn hóa |

Với người dùng, nhiều code point có thể được hiển thị thành **một cụm ký tự** (*grapheme cluster*). Ví dụ một emoji gia đình có thể gồm nhiều code point kết nối với nhau, và một chữ có dấu có thể được biểu diễn bằng chữ gốc cùng dấu kết hợp.

Vì thế, có **ít nhất ba cách đo độ dài** khác nhau:

1. **Số byte UTF-8**: liên quan trực tiếp đến kích thước mã hóa và giới hạn payload.
2. **Số Unicode code point**: số đơn vị ký tự trừu tượng.
3. **Số cụm ký tự hiển thị**: liên quan đến giới hạn độ dài mà người dùng cảm nhận.

Ứng dụng phải chọn đúng đơn vị khi validation. `String.length()` trong Java **đếm đơn vị mã hóa UTF-16**, không đếm byte UTF-8 và không luôn bằng số code point.

~~~java
import java.nio.charset.StandardCharsets;

String emoji = "😀";
System.out.println(emoji.length());                     // 2 đơn vị UTF-16
System.out.println(emoji.codePointCount(0, emoji.length())); // 1 code point
System.out.println(emoji.getBytes(StandardCharsets.UTF_8).length); // 4 byte
~~~

Không thể kết luận “100 ký tự Java = 100 byte trên Cassandra”. Với dữ liệu tiếng Việt hoặc emoji, độ dài byte thường lớn hơn độ dài ký tự hiển thị.

### 2.2. text/varchar không phải giới hạn varchar(n) của SQL

Trong một số RDBMS, `VARCHAR(255)` biểu thị cột chuỗi tối đa 255 ký tự. CQL của Cassandra dùng `varchar` như một tên khác của `text`; **không khai báo `varchar(255)`** để ràng buộc độ dài.

~~~cql
CREATE TABLE simple_profiles_by_id (
    user_id uuid PRIMARY KEY,
    display_name text,
    biography varchar,
    language_tag ascii
);
~~~

`display_name` và `biography` đều hỗ trợ Unicode. Nếu muốn tên dài tối đa 80 code point, hoặc tiểu sử tối đa 2.000 byte UTF-8, ứng dụng phải chủ động kiểm tra. Cassandra không kiểm soát giới hạn nghiệp vụ đó dựa vào tên `varchar`.

Về mặt vận hành, một cột không có giới hạn `varchar(n)` **không có nghĩa nên lưu chuỗi dài tùy ý**: cell và partition quá lớn làm tăng chi phí truyền mạng, cấp phát bộ nhớ, đọc/ghi, compaction và repair. Với nội dung dài như tài liệu, file, ảnh hoặc log lớn, cân nhắc lưu đối tượng ở hệ thống chuyên dụng rồi giữ ID/đường dẫn và metadata trong Cassandra.

## 3. ascii là kiểu gì, khi nào có ích?

**ASCII** cơ bản gồm các ký tự từ U+0000 đến U+007F, như chữ Latin không dấu `A-Z`, `a-z`, chữ số `0-9`, dấu câu và một số ký tự điều khiển. Chuỗi `"vi-VN"`, `"USD"`, `"SKU-001"` chỉ dùng ASCII. Các chữ `à`, `ễ`, `đ` hay emoji **không thuộc ASCII**.

Chọn `ascii` khi hợp đồng dữ liệu **chắc chắn chỉ dùng ASCII**, ví dụ:

- Mã loại tiền `USD`, `VND`, `EUR` theo một định dạng chỉ gồm ký tự Latin không dấu.
- Mã phiên bản giao thức hoặc mã trạng thái kỹ thuật chỉ gồm ASCII.
- Mã phân loại hoặc SKU nội bộ khi chính sách xác định tập ký tự ASCII và không dự kiến mở rộng sang Unicode.

Tuy vậy, bản thân `ascii` **không tự kiểm tra cấu trúc nghiệp vụ**. Cột `ascii` không tự bảo đảm mã tiền phải là đúng ba chữ cái viết hoa hoặc SKU chỉ chứa `[A-Z0-9-]`. Cần kiểm tra regex, tập mã hợp lệ và quy tắc phân biệt hoa–thường ở ứng dụng.

~~~cql
CREATE TABLE products_by_store_sku (
    store_id uuid,
    sku ascii,
    title text,
    description varchar,
    PRIMARY KEY ((store_id), sku)
);
~~~

Bảng này thích hợp nếu hệ thống **cam kết SKU là ASCII**. Tên sản phẩm như `"Cà phê sữa đá ☕"` lưu trong `title text`; không thể chuyển tên đó sang `ascii`.

**Không chọn ascii chỉ với kỳ vọng tiết kiệm bộ nhớ:** một chữ ASCII lưu bằng UTF-8 cũng thường tốn 1 byte trong `text`. Khác biệt chính là **phạm vi ký tự hợp lệ**, không phải một lợi ích nén chắc chắn. Nếu dữ liệu có thể đến từ người dùng toàn cầu, `text` thường là quyết định ít rủi ro hơn.

## 4. Unicode normalization: cùng một chữ có thể có hai khóa khác nhau

### 4.1. NFC và NFD là gì?

Trong Unicode, một ký tự hiển thị có thể được biểu diễn bằng nhiều chuỗi code point **tương đương về chuẩn tắc**. Ví dụ chữ `é` có thể là:

- **NFC** (dạng tổ hợp): U+00E9, một code point `é`.
- **NFD** (dạng tách): U+0065 `e` cộng U+0301 (dấu sắc kết hợp).

Hai chuỗi có thể hiển thị giống hệt nhau trên màn hình nhưng **có byte UTF-8 khác nhau**. Khi làm khóa, Cassandra phân biệt các chuỗi khác byte; nó không tự áp dụng NFC trước khi hash partition key hay so sánh clustering key.

~~~java
import java.text.Normalizer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

String composed = "\u00E9";  // U+00E9
String decomposed = "e\u0301"; // U+0065 + U+0301

System.out.println(composed.equals(decomposed)); // false
System.out.println(Arrays.equals(
    composed.getBytes(StandardCharsets.UTF_8),
    decomposed.getBytes(StandardCharsets.UTF_8)
)); // false

String normalized = Normalizer.normalize(decomposed, Normalizer.Form.NFC);
System.out.println(composed.equals(normalized)); // true
~~~

Nếu một ứng dụng ghi username bằng NFC nhưng một ứng dụng khác tìm bằng NFD, truy vấn theo khóa có thể không tìm được dòng. Hệ quả thực tế gồm tài khoản trùng tên hiển thị, cache miss, dữ liệu trong các partition khác nhau và khó đối soát nhiều hệ thống.

**Quy tắc:** với trường **khóa văn bản**, chọn một chính sách chuẩn hóa và áp dụng **giống nhau trước mọi thao tác INSERT, SELECT, UPDATE, DELETE và tạo khóa cache**. NFC là lựa chọn thực dụng cho nhiều trường hợp văn bản; NFKC có thể thay đổi cách biểu diễn của một số ký tự tương thích và chỉ nên dùng khi đó là chủ đích của nghiệp vụ.

### 4.2. Chuẩn hóa Unicode khác với xử lý chữ hoa–thường

NFC **không** làm `"Lan"` và `"lan"` giống nhau. Tương tự, `"Hoa"` và `"Hòa"` vẫn là các chuỗi khác nhau. Nếu username cần **không phân biệt hoa–thường**, ứng dụng cần quy tắc tạo `username_key` chuẩn từ đầu vào.

~~~java
import java.text.Normalizer;
import java.util.Locale;

static String canonicalUsername(String raw) {
    String nfc = Normalizer.normalize(raw, Normalizer.Form.NFC);
    String lower = nfc.toLowerCase(Locale.ROOT);
    return Normalizer.normalize(lower, Normalizer.Form.NFC);
}
~~~

Đây là ví dụ **chính sách lowercase đơn giản**. Việc so khớp không phân biệt chữ hoa đầy đủ cho Unicode có thể cần *Unicode case folding* chuyên dụng, đặc biệt với các trường hợp ngôn ngữ đặc biệt. Hãy định nghĩa tập ký tự username hợp lệ, khoảng trắng đầu/cuối có được phép hay không và điều kiện phân biệt dấu, rồi kiểm thử bằng dữ liệu quốc tế.

Không tự động bỏ dấu tiếng Việt hoặc thay mọi chữ giống hình dạng bằng nhau. **Chuẩn hóa Unicode**, **lowercase**, **transliteration** (chuyển tự) và **lọc ký tự giống hình dạng** là những quy tắc khác nhau, có thể làm mất thông tin nếu áp dụng tùy tiện.

### 4.3. Hiển thị và tra cứu cần hai vai trò dữ liệu

Một thiết kế thường có:

- `username_key text`: giá trị đã chuẩn hóa theo chính sách định danh; dùng tra cứu và tạo khóa.
- `display_name text`: tên hiển thị của người dùng, giữ chữ hoa, dấu và định dạng phù hợp.
- `bio varchar`: phần mô tả Unicode tự do.
- `locale_tag ascii`: mã ngôn ngữ/locale theo tập ký tự ASCII nếu quy ước đầu vào đúng như vậy.

Không nên dùng tên hiển thị tự do làm ID: người dùng có thể đổi tên, tên có thể trùng và normalization của dấu có thể khác giữa nguồn dữ liệu.

## 5. Thiết kế bảng theo truy vấn với khóa text

Giả sử yêu cầu nghiệp vụ: **“Tìm tài khoản trong một tenant theo username, không phân biệt hoa–thường theo chính sách đã định nghĩa”**. Một schema phù hợp:

~~~cql
CREATE TABLE user_handles_by_tenant (
    tenant_id uuid,
    username_key text,
    user_id uuid,
    display_name text,
    bio varchar,
    locale_tag ascii,
    PRIMARY KEY ((tenant_id, username_key))
);
~~~

Hai cột `tenant_id` và `username_key` tạo thành **partition key tổng hợp**. Cassandra hash giá trị khóa đã được mã hóa để phân phối partition giữa các node; truy vấn định danh phải cung cấp **cả hai thành phần**:

~~~cql
SELECT user_id, display_name, bio, locale_tag
FROM user_handles_by_tenant
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND username_key = 'nguyen.ha';
~~~

Ví dụ thêm dữ liệu có Unicode và dùng lightweight transaction để cố gắng dành tên chưa tồn tại:

~~~cql
INSERT INTO user_handles_by_tenant (
    tenant_id, username_key, user_id, display_name, bio, locale_tag
) VALUES (
    11111111-1111-4111-8111-111111111111,
    'nguyen.ha',
    22222222-2222-4222-8222-222222222222,
    'Nguyễn Thị Hà',
    'Thích cà phê ☕ và sách của O''Reilly',
    'vi-VN'
) IF NOT EXISTS;
~~~

Trong literal CQL, dấu nháy đơn bên trong chuỗi được viết thành **hai dấu nháy đơn**: `O''Reilly`. Khi dùng Java Driver với prepared statements, hãy **bind giá trị** thay vì tự nối và escape chuỗi.

`IF NOT EXISTS` là một thao tác có điều kiện (LWT/Paxos) giúp hai yêu cầu cạnh tranh cùng **khóa đã chuẩn hóa** không cùng lúc tạo hai tài khoản trên đúng khóa đó. Nó **không** tự ngăn được hai khóa khác nhau vì chuẩn hóa không thống nhất, và không làm cho ghi đồng thời sang nhiều bảng khác trở thành một giao dịch phân tán duy nhất. Xử lý kết quả `[applied]` trước khi thông báo username đã được đăng ký.

**Điểm thiết kế quan trọng:** vì partition key gồm cả username, bảng này phục vụ **lookup chính xác**, không hiệu quả cho “liệt kê tất cả người dùng của tenant” khi chỉ biết `tenant_id`. Nhu cầu đó cần bảng đọc khác có partition key/bucket phù hợp. Cassandra thường mô hình hóa nhiều bảng từ các **mẫu truy vấn**; đổi `username_key` từ `text` sang `ascii` không tự tạo ra một đường truy vấn mới.

### 5.1. Khóa case-sensitive và tính phân phối

Nếu hệ thống không chuẩn hóa, các giá trị `"Lan"`, `"lan"`, `"Lân"`, `"La\u0302n"` có thể là các khóa khác nhau dù một số trông tương tự. Cassandra không mặc định xử lý **collation theo ngôn ngữ** hay tìm kiếm không phân biệt dấu cho các khóa `text`.

Do partition key được băm từ **giá trị khóa**, byte khác nhau có thể dẫn đến token khác nhau và phân phối vào các vùng dữ liệu khác nhau. Replication đảm bảo sao chép **mỗi khóa mà ứng dụng đã ghi**, không tự hợp nhất các biến thể mà người dùng xem là cùng tên.

Nếu có yêu cầu đổi username, đừng coi thao tác thay đổi partition key như UPDATE một giá trị cột bình thường. Thực tế thường phải tạo bản ghi với khóa mới, điều phối quá trình chuyển/giữ tham chiếu và xử lý bản ghi cũ theo chính sách nhất quán.

## 6. Unicode, phân loại chuỗi và thứ tự sắp xếp

Một vấn đề thường gặp là muốn trả danh sách theo **thứ tự từ điển tiếng Việt**. Cassandra không mặc định có bộ *locale-aware collation* như cách một số RDBMS cấu hình collation. So sánh chuỗi trong khóa dựa trên kiểu và giá trị được mã hóa, **không phải** quy tắc sắp từ trong từ điển tiếng Việt.

Xét bảng:

~~~cql
CREATE TABLE products_by_category_title (
    category_id uuid,
    title_key text,
    product_id uuid,
    display_title text,
    PRIMARY KEY ((category_id), title_key, product_id)
) WITH CLUSTERING ORDER BY (title_key ASC, product_id ASC);
~~~

Bảng có thể đọc sản phẩm theo `category_id` và thứ tự **clustering** trên `title_key`. Tuy nhiên, `title_key` phải được tạo theo một chính sách ổn định; thứ tự của UTF-8 **không đồng nghĩa thứ tự chữ có dấu theo văn phạm tiếng Việt**. Chữ hoa/thường, ký tự kết hợp và dấu có thể cho kết quả khác kỳ vọng người dùng.

Nếu cần hiển thị theo quy tắc sắp xếp tiếng Việt, có thể tạo **sort key** bằng một thuật toán collation được chọn rõ ràng trong ứng dụng, hoặc dùng hệ tra cứu chuyên biệt. Khóa sắp xếp nên được tạo và lưu nhất quán cùng thuật toán/phiên bản; đổi thư viện collation có thể đòi hỏi xây lại dữ liệu đã lưu.

Đồng thời, Cassandra chỉ hỗ trợ các mẫu `ORDER BY` được phép trên **clustering columns** trong một mô hình khóa phù hợp; không thể mặc định viết `ORDER BY display_title` cho một cột dữ liệu bất kỳ giống cơ sở dữ liệu quan hệ.

**Tìm kiếm khác với tra cứu theo khóa:** truy vấn “tên có chứa `cà phê`”, “gần giống một từ gõ sai”, “bỏ dấu để tìm” hoặc “full-text search” cần chiến lược chỉ mục/tìm kiếm phù hợp với phiên bản Cassandra và workload, hoặc một hệ tìm kiếm riêng. Chỉ thay kiểu `varchar` thành `text` sẽ không tạo ra các tính năng đó.

## 7. Java Driver 4.x: ghi/đọc và chuẩn hóa String

Java Driver 4.x thường ánh xạ cả ba kiểu CQL **`text`**, **`varchar`**, **`ascii`** sang Java **`String`**, với các phương thức `setString` và `getString`. Tuy cùng một kiểu Java, **ý nghĩa và giới hạn hợp lệ** vẫn do schema và hợp đồng nghiệp vụ quyết định.

Bên dưới, giả sử `session` là một `CqlSession` đã kết nối tới đúng keyspace:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.Locale;
import java.util.UUID;

UUID tenantId = UUID.fromString("11111111-1111-4111-8111-111111111111");
UUID userId = UUID.fromString("22222222-2222-4222-8222-222222222222");

String rawUsername = "Nguyen.Ha";
String usernameKey = Normalizer.normalize(
    Normalizer.normalize(rawUsername, Normalizer.Form.NFC)
        .toLowerCase(Locale.ROOT),
    Normalizer.Form.NFC
);

// Giới hạn ví dụ: khóa sau chuẩn hóa không được quá 128 byte UTF-8.
if (usernameKey.getBytes(StandardCharsets.UTF_8).length > 128) {
    throw new IllegalArgumentException("Username quá dài");
}

String displayName = "Nguyễn Thị Hà";
String bio = "Thích cà phê ☕ và sách của O'Reilly";
String localeTag = "vi-VN"; // Hợp đồng xác nhận chỉ chứa ASCII.

PreparedStatement insert = session.prepare(
    "INSERT INTO user_handles_by_tenant "
  + "(tenant_id, username_key, user_id, display_name, bio, locale_tag) "
  + "VALUES (?, ?, ?, ?, ?, ?) IF NOT EXISTS");

BoundStatement bound = insert.boundStatementBuilder()
    .setUuid(0, tenantId)
    .setString(1, usernameKey)
    .setUuid(2, userId)
    .setString(3, displayName)
    .setString(4, bio)
    .setString(5, localeTag)
    .build();

Row appliedRow = session.execute(bound).one();
if (appliedRow == null || !appliedRow.getBoolean("[applied]")) {
    throw new IllegalStateException("Username đã tồn tại hoặc chưa được tạo");
}
~~~

Ở môi trường thực tế, cần xử lý timeout và trường hợp **không biết LWT đã thành công hay chưa**: một lần retry dùng lại `tenantId`, `usernameKey`, `userId`, kiểm tra kết quả theo nghiệp vụ. Không tự coi mọi `[applied] = false` là lỗi mạng hoặc cho rằng `[applied] = true` chứng minh đã ghi xong các bảng liên quan khác.

Truy vấn luôn dùng cùng quy tắc chuẩn hóa:

~~~java
String inputToSearch = "NGUYEN.HA";
String lookupKey = Normalizer.normalize(
    Normalizer.normalize(inputToSearch, Normalizer.Form.NFC)
        .toLowerCase(Locale.ROOT),
    Normalizer.Form.NFC
);

PreparedStatement find = session.prepare(
    "SELECT user_id, display_name, bio "
  + "FROM user_handles_by_tenant "
  + "WHERE tenant_id = ? AND username_key = ?");

Row found = session.execute(find.bind(tenantId, lookupKey)).one();
if (found != null) {
    UUID id = found.getUuid("user_id");
    String name = found.getString("display_name");
    String biography = found.getString("bio");
}
~~~

**Prepared statement** giữ giá trị chuỗi trong tham số được bind: không phải viết logic ghép chuỗi SQL/CQL và thoát dấu nháy bằng tay, đồng thời giảm rủi ro injection. Chính sách **normalization** vẫn do ứng dụng thực hiện trước khi bind.

### 7.1. Kiểm tra ASCII ở Java

Khi cột khai báo `ascii`, có thể kiểm tra chủ động trước khi gọi driver:

~~~java
static boolean isAscii(String value) {
    return value.codePoints().allMatch(cp -> cp <= 0x7F);
}

System.out.println(isAscii("USD"));       // true
System.out.println(isAscii("vi-VN"));     // true
System.out.println(isAscii("Tiếng Việt")); // false
~~~

Đây mới là điều kiện **chỉ sử dụng ký tự ASCII**. Với mã tiền tệ, cần thêm quy tắc như `[A-Z]{3}` và kiểm tra danh mục mã được chấp nhận; không chỉ dựa vào `isAscii`.

### 7.2. Giới hạn byte, code point và số ký tự hiển thị

~~~java
import java.nio.charset.StandardCharsets;

String title = "Học Cassandra 😀";

int utf16Units = title.length();
int codePoints = title.codePointCount(0, title.length());
int utf8Bytes = title.getBytes(StandardCharsets.UTF_8).length;

System.out.printf("UTF-16=%d, code points=%d, UTF-8 bytes=%d%n",
    utf16Units, codePoints, utf8Bytes);
~~~

Khi giới hạn kỹ thuật liên quan tới kích thước lưu trữ, nên dựa trên **byte UTF-8 sau khi đã chuẩn hóa**. Khi giới hạn UX như “tên tối đa 30 ký tự hiển thị”, cần đếm **grapheme clusters** theo quy tắc Unicode phù hợp; `codePointCount` cũng chưa phải đáp án chính xác với mọi emoji/dấu kết hợp.

Ngoài ra, Java `String` là chuỗi UTF-16 và có thể chứa surrogate không ghép cặp do dữ liệu lỗi. Với đầu vào có yêu cầu bảo toàn Unicode nghiêm ngặt, nên kiểm tra hợp lệ **trước khi** mã hóa UTF-8, thay vì mặc định mọi chuỗi UTF-16 đều là chuỗi Unicode scalar value hợp lệ.

## 8. Những lỗi hay gặp khi truy vấn chuỗi

| Tình huống | Vấn đề | Cách xử lý |
|---|---|---|
| Dùng `ascii` cho tên `"Đặng"` | Dữ liệu không thuộc ASCII | Dùng `text`/`varchar` |
| Nghĩ `varchar(255)` là cú pháp CQL | Kiểu `varchar` của Cassandra không khai báo giới hạn độ dài kiểu đó | Dùng `varchar` hoặc `text`, validation độ dài trong ứng dụng |
| Ghi username NFC, tìm username NFD | Khác byte, khác giá trị khóa | Chuẩn hóa giống nhau trước ghi và đọc |
| Ghi `"Lan"`, tìm `"lan"` | Khác hoa–thường | Quy định `username_key` không phân biệt hoa–thường nếu nghiệp vụ cần |
| Giả định `text` tự so sánh theo thứ tự tiếng Việt | Thứ tự không theo collation ngôn ngữ | Xây sort key/công cụ collation theo yêu cầu |
| Đếm `String.length()` để giới hạn byte | UTF-16 unit không bằng byte UTF-8 | Đo `getBytes(UTF_8).length` sau normalization |
| Chọn `text` để hỗ trợ tìm kiếm gần đúng | Kiểu chuỗi không tự tạo full-text search | Thiết kế index/search theo workload |
| Dùng tên hiển thị làm primary key | Người dùng đổi tên, tên trùng và chuẩn hóa phức tạp | Dùng ID ổn định, tách khóa tra cứu chuẩn hóa |
| Ghép giá trị người dùng vào literal CQL | Lỗi escape, nguy cơ injection | Dùng prepared statement và bind |
| Dùng `text` để lưu payload/file rất lớn | Tăng chi phí bộ nhớ, mạng, SSTable, compaction | Tách object storage và lưu metadata/URI khi phù hợp |

## 9. Kích thước phân vùng, consistency và tác động vận hành

### 9.1. Khóa chuỗi có thể làm thay đổi phân phối dữ liệu

Cassandra xác định partition dựa trên **partition key đã được mã hóa và băm**. Nếu hai chuỗi khác byte UTF-8, chúng là hai giá trị khóa khác nhau dù màn hình hiển thị gần như giống nhau. Hậu quả có thể thấy rõ khi:

- Một service Java normalize NFC, service khác không normalize.
- Một service tự `trim()` username, service khác giữ nguyên khoảng trắng.
- Một nguồn dữ liệu coi username là case-insensitive, nguồn khác phân biệt hoa–thường.
- Các hệ thống dùng phiên bản thuật toán xử lý Unicode/case folding khác nhau.

Tất cả client đọc và ghi dữ liệu cùng domain cần dùng **một hợp đồng canonicalization thống nhất**, có phiên bản và khả năng kiểm thử. Với dữ liệu cần tính duy nhất, phải tổ chức đăng ký khóa và kiểm tra cạnh tranh phù hợp, không dựa vào collation mặc định.

### 9.2. Chuỗi dài, partition lớn và thao tác xóa

Số byte UTF-8 của tên người dùng thường nhỏ, nhưng mô tả dài hoặc trường text chứa nhiều JSON có thể làm tăng kích thước row. Với hệ thống có hàng triệu row, kích thước dữ liệu và metadata cell ảnh hưởng đến băng thông, cache, đọc/ghi và compaction. Dữ liệu bị xóa hoặc hết TTL có thể sinh tombstone; kiểu `text` tự nó không ngăn việc đọc phải xử lý nhiều tombstone.

Nếu thiết kế partition key là `tenant_id` đơn lẻ và chứa hàng triệu người dùng trong một partition, mọi tên ngắn vẫn có thể tạo partition quá lớn. Để tránh, hãy tính cách phân phối row theo truy vấn, chia bucket/shard nếu cần và kiểm tra phân bố dữ liệu thực tế. Trong ví dụ `user_handles_by_tenant`, partition key `(tenant_id, username_key)` giúp phân phối lookup nhưng không phục vụ duyệt danh sách toàn tenant.

### 9.3. Replication/repair không thay thế normalization

Replication giữ nhiều bản sao của dữ liệu và consistency level quyết định mức xác nhận khi đọc/ghi. Repair giúp đồng bộ trạng thái replica; compaction tổ chức lại SSTable. Chúng làm việc với **khóa và giá trị đã được ghi**, không tự hợp nhất:

- `"Hà"` với `"Ha\u0300"` khi hai bên chưa được chuẩn hóa đồng nhất;
- `"USER01"` với `"user01"` khi ứng dụng muốn không phân biệt hoa–thường;
- username cũ và username mới sau đổi tên.

Mọi thay đổi chính sách normalized key có thể yêu cầu **migration** dữ liệu: tạo bảng/key mới, backfill từ nguồn đáng tin, điều phối dual-read/dual-write phù hợp và kiểm soát trùng lặp. Đừng tùy tiện đổi kiểu của cột khóa hoặc thay thuật toán chuẩn hóa khi các ứng dụng khác vẫn dùng phiên bản cũ.

## 10. Bài tập thực hành

### Bài 1 — Chọn kiểu dữ liệu

Cho các cột sau: tên khách hàng `"Trần Thị Mỹ"`, mã tiền `"VND"`, mã sản phẩm `"0000185"`, mô tả chứa emoji, và địa chỉ email có ký tự Unicode ở phần local-part.

**Gợi ý:**

- Tên khách hàng, mô tả và email quốc tế có thể yêu cầu `text`/`varchar` (việc hệ thống email cụ thể hỗ trợ địa chỉ Unicode còn phụ thuộc tiêu chuẩn và chính sách email).
- Mã tiền có thể dùng `ascii` kèm quy tắc kiểm tra mã hợp lệ; `text` vẫn chứa được cùng giá trị.
- Mã sản phẩm là **chuỗi định danh**, không phải số nguyên; dùng `ascii` nếu chính sách chỉ cho phép ASCII, hoặc `text` nếu có thể mở rộng ký tự.

### Bài 2 — Chuỗi giống nhau nhưng truy vấn không ra

Dữ liệu được ghi với `username_key = "café"` ở dạng NFC. Một client tìm bằng chuỗi `"cafe\u0301"` ở dạng NFD. Vì sao truy vấn theo partition key có thể không tìm thấy row? Viết hàm chuẩn hóa bằng Java.

**Đáp án:** byte UTF-8 của hai chuỗi khác nhau. Trước cả khi ghi lẫn khi query phải gọi:

~~~java
String key = Normalizer.normalize(input, Normalizer.Form.NFC);
~~~

Nếu domain còn yêu cầu case-insensitive, bổ sung chính sách casing thống nhất, không chỉ normalize NFC.

### Bài 3 — Chữ dài bao nhiêu?

Chuỗi `"😀"` có `length() == 2`, `codePointCount(...) == 1`, số byte UTF-8 là 4. Khi giới hạn “tối đa 64 byte trong khóa”, dùng phép đo nào?

**Đáp án:** số byte UTF-8 **sau chuẩn hóa**. Nếu yêu cầu “64 ký tự nhìn thấy”, cần đếm grapheme cluster thay vì chỉ UTF-16 units hoặc code point.

### Bài 4 — Truy vấn mới

Bảng `user_handles_by_tenant` dùng partition key `(tenant_id, username_key)`. Sản phẩm cần liệt kê 50 người dùng mới nhất của tenant. Có thể chỉ đổi `username_key` từ `text` thành `varchar` để giải quyết không?

**Đáp án:** không, vì `text` và `varchar` tương đương. Cần mô hình truy vấn mới, ví dụ bảng phân vùng theo tenant + bucket và clustering key theo thời điểm tạo + user ID, kèm kiểm soát phân vùng tăng trưởng.

## 11. Checklist trước khi triển khai chuỗi trong Cassandra

- [ ] Cột cần Unicode hay được đảm bảo **ASCII** bởi hợp đồng đầu vào?
- [ ] Nhóm phát triển đã hiểu `text` và `varchar` **tương đương**, không có `varchar(n)` như SQL?
- [ ] Với text key, đã xác định **NFC/NFD, case policy, khoảng trắng, dấu và bộ ký tự hợp lệ**?
- [ ] Mọi đường ghi/đọc/xóa/cache có dùng cùng hàm tạo **canonical key**?
- [ ] Đã xác định giới hạn theo **byte UTF-8**, code point hay grapheme cluster cho đúng yêu cầu?
- [ ] Có tách **display text** với **lookup/sort key** để tránh mất dấu hoặc thông tin trình bày?
- [ ] Các truy vấn quan trọng cung cấp đầy đủ partition key, có clustering columns phù hợp nếu cần thứ tự?
- [ ] Nếu yêu cầu tìm kiếm toàn văn/tìm gần đúng, đã chọn chiến lược index/search theo phiên bản và tải thực tế?
- [ ] Java Driver có bind `String` qua prepared statement, kiểm tra ASCII/UTF-8 và null đúng quy tắc?
- [ ] Đã giới hạn trường text lớn, kích thước partition và chiến lược migration khi thay quy tắc chuẩn hóa?
- [ ] Với đăng ký username duy nhất, đã có giải pháp xử lý cạnh tranh, retry và tính nhất quán các bảng liên quan?

**Ghi nhớ:** `text` và `varchar` cùng lưu chuỗi Unicode UTF-8; `ascii` chỉ chấp nhận ASCII. Khi một chuỗi tham gia **partition key hoặc clustering key**, hãy coi **normalization/canonicalization** là một phần của mô hình dữ liệu và hợp đồng ứng dụng Java. Cassandra phân phối và so sánh các khóa thực tế đã mã hóa; replication, repair, compaction hay consistency level không tự diễn giải hai chuỗi nhìn giống nhau thành một định danh.

