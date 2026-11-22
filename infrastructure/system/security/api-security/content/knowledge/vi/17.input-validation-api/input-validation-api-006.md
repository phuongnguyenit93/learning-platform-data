# Không dùng regex đơn lẻ để chống injection

## 1. Vì sao regex không thể là hàng rào chống injection?

Injection xảy ra khi dữ liệu do người dùng kiểm soát bị diễn giải như một phần của câu lệnh hoặc biểu thức mà ứng dụng thực thi. Ví dụ, chuỗi nhập vào được nối thẳng vào SQL, lệnh hệ điều hành, LDAP filter, HTML hoặc template. Khi đó, attacker có thể thay đổi ý nghĩa của câu lệnh thay vì chỉ cung cấp một giá trị dữ liệu.

Regular expression (regex) hữu ích để kiểm tra định dạng đầu vào như mã bưu chính, username hoặc mã tham chiếu. Nhưng regex không thể thay thế cơ chế giữ ranh giới giữa **code** và **data**. Một regex tìm từ khóa `SELECT`, dấu nháy hoặc chuỗi `OR 1=1` có thể bị vượt qua bằng cách đổi cách viết, encoding, khoảng trắng, comment, cú pháp lồng nhau hoặc đặc điểm riêng của parser đích.

Ví dụ, quy tắc chặn chuỗi `OR 1=1` không thể đại diện cho toàn bộ ngữ pháp SQL. Attacker có thể dùng biểu thức tương đương, comment, chữ hoa/thường, hàm, kiểu literal khác hoặc payload không cần chứa chuỗi đó. Ngay cả khi regex nhận diện được một số payload, việc lọc chuỗi vẫn có nguy cơ xóa nhầm dữ liệu hợp lệ hoặc bỏ sót biến thể.

Nguyên tắc phòng vệ là dùng cơ chế phù hợp với nơi dữ liệu được đưa vào:

- SQL/JPQL: parameterized query hoặc prepared statement.
- NoSQL: API truy vấn có cấu trúc; không biến JSON tùy ý thành query operator.
- Shell/OS: tránh shell command; truyền executable và arguments riêng, kiểm tra allowlist.
- HTML: encode theo đúng ngữ cảnh đầu ra; dùng template engine auto-escaping.
- LDAP: dùng API filter có escaping đúng chuẩn hoặc parameterization.
- URL/network: kiểm tra đích đến theo policy chống SSRF; regex URL đơn giản không đủ.
- Template: không ghép dữ liệu không tin cậy vào template code hoặc expression được thực thi.

## 2. Validation, sanitization, escaping và parameterization khác nhau thế nào?

Các biện pháp này giải quyết những vấn đề khác nhau, không thể dùng thay thế tùy ý:

| Biện pháp | Mục tiêu | Ví dụ | Giới hạn |
|---|---|---|---|
| Validation | Xác định dữ liệu có phù hợp hợp đồng đầu vào không. | `pageSize` là số nguyên từ 1 đến 100. | Dữ liệu hợp lệ về định dạng vẫn có thể nguy hiểm nếu ghép vào câu lệnh. |
| Canonicalization | Đưa dữ liệu về dạng chuẩn trước khi so sánh/chính sách. | Chuẩn hóa Unicode, decode theo một quy tắc rõ ràng. | Chuẩn hóa sai thứ tự hoặc decode nhiều lần có thể tạo bypass. |
| Sanitization | Loại bỏ hoặc chuyển đổi nội dung theo policy cụ thể. | Loại thẻ HTML không được phép trong rich text bằng parser chuyên dụng. | Có thể phá dữ liệu; không phải giải pháp tổng quát cho SQL/shell. |
| Escaping/encoding | Biểu diễn dữ liệu an toàn trong một ngữ cảnh cụ thể. | HTML attribute encoding hoặc LDAP filter escaping. | Encoding cho ngữ cảnh này không an toàn trong ngữ cảnh khác. |
| Parameterization | Tách cấu trúc câu lệnh khỏi giá trị dữ liệu. | `WHERE email = ?`. | Thường không áp dụng được cho tên bảng, cột hoặc cú pháp động; phần đó cần allowlist. |

Validation trả lời “giá trị có đúng hợp đồng không?”. Parameterization trả lời “giá trị có thể bị parser coi là cú pháp hay không?”. Một API an toàn thường cần cả hai: kiểm tra kiểu/miền giá trị ở biên request, sau đó dùng API truy vấn an toàn ở nơi thực thi.

## 3. Regex nên được dùng đúng phạm vi

Regex phù hợp với những định dạng có ngữ pháp nhỏ, ổn định và giới hạn rõ. Ví dụ kiểm tra mã đơn hàng có dạng `ORD-` theo sau bởi 8 chữ số:

```java
private static final Pattern ORDER_CODE =
    Pattern.compile("\\AORD-[0-9]{8}\\z");

boolean isValidOrderCode(String value) {
    return value != null && ORDER_CODE.matcher(value).matches();
}
```

`\A` và `\z` neo vào đầu/cuối toàn bộ input trong Java regex; `matches()` cũng yêu cầu khớp toàn chuỗi. Không nên dùng `find()` khi mục tiêu là xác nhận toàn bộ giá trị vì nó chỉ cần tìm một đoạn khớp.

Ví dụ khác, validation email không nên cố tự viết một regex bao phủ toàn bộ chuẩn email. Hãy dùng thư viện đã được kiểm chứng hoặc xác thực theo hợp đồng sản phẩm, giới hạn độ dài và thực hiện bước xác minh email nếu nghiệp vụ cần chứng minh quyền sở hữu.

Regex có thể kiểm tra allowlist ký tự và độ dài, nhưng đừng dùng regex để “xóa mọi ký tự nguy hiểm” trước khi chạy SQL hoặc shell. Các ký tự có ý nghĩa phụ thuộc parser và ngữ cảnh. Dữ liệu có dấu nháy có thể hợp lệ trong tên người dùng, trong khi một chuỗi chỉ gồm chữ và số vẫn có thể trở thành option nguy hiểm khi truyền cho một chương trình hệ điều hành.

### Cẩn thận với ReDoS

Regex phức tạp có thể gây Regular Expression Denial of Service (ReDoS) nếu mẫu có backtracking lớn và attacker gửi input được thiết kế để khiến matcher mất nhiều thời gian. Các cấu trúc lặp lồng nhau hoặc nhiều nhánh mơ hồ thường cần được xem xét kỹ.

- Giới hạn kích thước input trước khi chạy regex.
- Ưu tiên mẫu đơn giản, ít backtracking; tránh lặp lồng nhau không cần thiết.
- Đặt timeout hoặc dùng engine/mẫu có đặc tính thời gian phù hợp nếu thư viện hỗ trợ.
- Kiểm thử với chuỗi dài và chuỗi gần khớp nhưng thất bại ở cuối.
- Không dùng regex người dùng tự cung cấp làm pattern thực thi trên dữ liệu lớn nếu không có sandbox và quota.

## 4. Thứ tự xử lý đầu vào an toàn

Một pipeline validation nên có thứ tự rõ ràng:

1. **Giới hạn ở tầng giao nhận:** giới hạn request body, số field, độ dài chuỗi, số phần tử mảng, upload size và thời gian xử lý.
2. **Parse bằng parser chuẩn:** JSON/XML/form được phân tích bởi thư viện đúng chuẩn; không tự tách chuỗi bằng regex để mô phỏng parser.
3. **Canonicalize có kiểm soát:** chỉ decode/normalize theo hợp đồng đã xác định; tránh decode nhiều lần ở các tầng khác nhau.
4. **Validate schema và miền giá trị:** kiểu dữ liệu, required field, độ dài, enum, range, format và quan hệ giữa các field.
5. **Authorize:** kiểm tra principal có quyền thao tác trên chức năng, object và tenant tương ứng.
6. **Dùng API an toàn ở sink:** parameterized query, escaping theo ngữ cảnh, process invocation không qua shell hoặc thư viện chuyên dụng.
7. **Giới hạn tác dụng phụ và quan sát:** quota, timeout, audit và log đã loại bỏ dữ liệu nhạy cảm.

Không nên có một hàm `sanitizeInput()` chung áp dụng cho mọi loại dữ liệu. Giá trị dùng trong SQL, HTML, shell, LDAP và URL có quy tắc riêng. Hãy giữ dữ liệu gốc đã parse, áp dụng validation theo domain, rồi encode/parameterize tại điểm sử dụng phù hợp.

## 5. SQL injection: dùng parameterized query

### Cách dễ bị tấn công

```java
String sql = "SELECT id, email FROM account WHERE email = '"
        + email + "'";
Statement statement = connection.createStatement();
ResultSet rows = statement.executeQuery(sql);
```

Nếu `email` chứa cú pháp SQL, dữ liệu có thể thay đổi cấu trúc câu lệnh. Chặn dấu nháy bằng regex không phải cách sửa đúng: SQL có nhiều cú pháp, encoding và ngữ cảnh literal khác nhau.

### Dùng PreparedStatement

```java
String sql = "SELECT id, email FROM account WHERE email = ?";
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, email);
    try (ResultSet rows = statement.executeQuery()) {
        while (rows.next()) {
            // Đọc dữ liệu đã truy vấn.
        }
    }
}
```

Driver gửi giá trị bind như dữ liệu riêng, không ghép nó thành cú pháp SQL. Vẫn cần validation độ dài/format, authorization và giới hạn kết quả. Parameterization không tự ngăn truy cập dữ liệu sai tenant nếu câu truy vấn thiếu điều kiện phân quyền.

### Spring JDBC và JPA

```java
List<Account> findByEmail(String email) {
    return jdbcTemplate.query(
        "SELECT id, email FROM account WHERE email = ?",
        accountRowMapper,
        email
    );
}
```

Với JPA, dùng parameter:

```java
TypedQuery<Account> query = entityManager.createQuery(
    "select a from Account a where a.email = :email",
    Account.class
);
query.setParameter("email", email);
List<Account> accounts = query.getResultList();
```

ORM không tự bảo vệ nếu ứng dụng nối chuỗi vào JPQL/HQL hoặc native SQL. Những API như query string động vẫn phải được kiểm tra cách tạo.

### Tên cột và ORDER BY cần allowlist

Parameter placeholder thường chỉ bind được giá trị, không bind tên bảng, tên cột hoặc từ khóa `ASC`/`DESC`. Không làm như sau:

```java
// Không an toàn: sortField bị nối trực tiếp vào SQL.
String sql = "SELECT id, email FROM account ORDER BY " + sortField;
```

Thay bằng allowlist mapping từ lựa chọn công khai sang identifier cố định:

```java
private static final Map<String, String> SORT_COLUMNS = Map.of(
    "email", "email",
    "created", "created_at",
    "name", "display_name"
);

String column = SORT_COLUMNS.get(requestedSort);
if (column == null) {
    throw new IllegalArgumentException("Unsupported sort field");
}

String direction = descending ? "DESC" : "ASC";
String sql = "SELECT id, email FROM account ORDER BY "
        + column + " " + direction;
```

Giá trị được ghép vào câu lệnh chỉ đến từ allowlist do server định nghĩa. `descending` cần được parse thành boolean/enum, không nối nguyên văn chuỗi direction từ client. Nếu có nhiều lựa chọn sort, hãy dùng enum hoặc map tĩnh thay vì regex kiểm tra identifier tùy ý.

## 6. NoSQL injection và query operator

NoSQL không đồng nghĩa với không có injection. Rủi ro xuất hiện khi ứng dụng nhận object JSON do client gửi rồi chuyển thẳng thành filter/query, hoặc ghép chuỗi vào biểu thức query.

Ví dụ một endpoint đăng nhập nhận body:

```json
{
  "username": "alice",
  "password": { "$ne": null }
}
```

Nếu server chuyển object `password` trực tiếp vào MongoDB filter, một operator như `$ne` có thể được diễn giải thành điều kiện truy vấn thay vì giá trị mật khẩu. Regex chỉ chặn một vài tên operator sẽ không bao phủ toàn bộ cú pháp và operator của database.

Hãy thiết kế DTO với kiểu dữ liệu cụ thể và tự tạo query từ field được phép:

```java
public record LoginRequest(
    @NotBlank @Size(max = 100) String username,
    @NotBlank @Size(max = 256) String password) {
}
```

Repository phải nhận `String` đã validate và dùng API query có cấu trúc. Không nhận filter JSON tùy ý từ client trừ khi sản phẩm thật sự cần một query language; khi đó phải xây dựng grammar giới hạn, allowlist field/operator, giới hạn độ sâu/số điều kiện và kiểm thử policy.

Các điểm cần chú ý:

- Không bind trực tiếp request JSON vào query document hoặc object persistence có thể chứa operator.
- Chỉ cho phép các field và operator đã công bố trong API contract.
- Không cho client tự chọn collection, database, aggregation stage hoặc JavaScript expression tùy ý.
- Giới hạn độ sâu filter, số điều kiện, kích thước mảng và chi phí truy vấn.
- Dùng credential database với quyền tối thiểu và giới hạn tenant trong query.

## 7. OS command injection: tránh gọi shell

Nếu API cho phép chuyển đổi file, nén dữ liệu hoặc gọi công cụ hệ thống, không ghép input vào command string rồi chạy qua shell:

```java
// Không an toàn: userInput có thể thay đổi cú pháp shell.
Runtime.getRuntime().exec("convert " + userInput + " output.png");
```

Ưu tiên API thư viện để xử lý file. Nếu buộc phải gọi chương trình ngoài, chỉ định executable cố định và truyền từng argument riêng:

```java
Path input = resolveAllowedInput(uploadId); // Tra từ metadata server-side.
Path output = createServerSideOutputPath();

ProcessBuilder builder = new ProcessBuilder(
    "/usr/bin/convert",
    "--",
    input.toString(),
    output.toString()
);
builder.redirectErrorStream(true);
Process process = builder.start();
```

Ví dụ cần điều chỉnh theo chương trình cụ thể: không phải công cụ nào cũng hỗ trợ `--` để kết thúc option parsing. `ProcessBuilder` truyền argument riêng và không tự gọi shell, nhưng vẫn cần kiểm soát executable, đường dẫn file, option, quyền filesystem, timeout, output size và exit code. Không lấy một đường dẫn tùy ý từ client rồi đưa thẳng vào process.

Nếu ứng dụng thực sự phải hỗ trợ một tùy chọn, ánh xạ lựa chọn của client sang enum/flag cố định. Kiểm tra file nằm trong thư mục cho phép sau khi resolve canonical path, ngăn path traversal và symlink escape theo mô hình triển khai.

## 8. LDAP, HTML, template và các ngữ cảnh khác

### LDAP filter

LDAP filter có ký tự đặc biệt và quy tắc escape riêng. Không nối username/email trực tiếp vào filter và không tự viết regex để xóa dấu `*`, `(`, `)`, `\\` hoặc NUL. Dùng thư viện/API tạo filter có escaping đúng chuẩn, giới hạn field có thể tìm kiếm và không cho client cung cấp cả filter expression.

### HTML và JavaScript

Đầu vào hợp lệ vẫn có thể chứa nội dung cần encode khi hiển thị. Ví dụ tên hiển thị `A&B` là dữ liệu hợp lệ, nhưng khi đưa vào HTML phải được encode theo ngữ cảnh. Dùng template engine có auto-escaping và không tắt cơ chế này khi không cần thiết.

- HTML text node: HTML entity encoding.
- HTML attribute: attribute encoding và đặt giá trị trong dấu nháy.
- URL trong thuộc tính: validate scheme/host theo nghiệp vụ và encode thành phần URL phù hợp.
- JavaScript: tránh chèn dữ liệu vào inline script; truyền qua JSON serialization an toàn hoặc DOM API như `textContent`.
- CSS: tránh ghép dữ liệu tùy ý vào selector/style; dùng API/allowlist giá trị.

HTML encoding không thay thế URL validation, và URL encoding không thay thế JavaScript string encoding. Cần biết dữ liệu đang được đặt vào vị trí nào.

### Template injection

Không cho user cung cấp nội dung template hoặc expression rồi chạy trong engine có quyền truy cập object, file, class hay service. Nếu sản phẩm cho phép template tùy biến, dùng engine/sandbox có giới hạn chức năng, context dữ liệu tối thiểu, timeout và quota. Regex loại `${...}` hoặc `{{...}}` không thể mô phỏng đầy đủ ngữ pháp của mọi template engine.

### XML và parser

Khi nhận XML, cấu hình parser tắt external entity và external DTD nếu nghiệp vụ không cần. Giới hạn kích thước, độ sâu và số node để giảm XML entity expansion hoặc tiêu thụ tài nguyên. Regex xóa `DOCTYPE` không phải biện pháp thay thế cấu hình an toàn của parser.

## 9. URL, SSRF và validation theo cấu trúc

Một API có thể nhận URL để tải ảnh, xem trước link, gọi webhook hoặc import dữ liệu. URL là cấu trúc gồm scheme, authority, hostname, port, path, query và fragment; regex đơn giản thường không xử lý chính xác các biến thể encoding, IPv6, userinfo, redirect hoặc cách parser diễn giải hostname.

Nếu server truy cập URL do người dùng cung cấp:

- Chỉ cho phép scheme cần thiết, thường là `https` (và `http` nếu nghiệp vụ thực sự cần).
- Ưu tiên allowlist hostname/đích đến nếu danh sách có thể xác định.
- Parse URL bằng thư viện chuẩn; từ chối userinfo, hostname rỗng, port không được phép và định dạng không hợp lệ.
- Phân giải DNS và chặn loopback, private, link-local, multicast, reserved và địa chỉ metadata; tính đến IPv4-mapped IPv6 và nhiều bản ghi DNS.
- Kiểm tra lại địa chỉ đích tại thời điểm kết nối để giảm DNS rebinding/TOCTOU; giới hạn outbound bằng network egress policy.
- Tắt redirect hoặc kiểm tra lại từng redirect target; không cho redirect đến mạng nội bộ.
- Đặt timeout, giới hạn response size, số redirect và loại nội dung.

Regex có thể kiểm tra một quy ước URL đơn giản trong sản phẩm, nhưng không thể thay thế URL parser, DNS/IP policy và network egress control. Không dùng một lần kiểm tra hostname rồi để HTTP client tự phân giải/kết nối theo cách khác.

## 10. Validation ở biên API với Spring

DTO nên thể hiện hợp đồng dữ liệu bằng kiểu rõ ràng và constraint phù hợp:

```java
public record CreateTransferRequest(
    @NotNull UUID destinationAccountId,
    @NotNull @DecimalMin("0.01") @Digits(integer = 12, fraction = 2)
        BigDecimal amount,
    @NotBlank @Size(max = 3) @Pattern(regexp = "[A-Z]{3}")
        String currency,
    @Size(max = 140) String description
) {
}
```

Controller kích hoạt Bean Validation:

```java
@PostMapping("/api/transfers")
public ResponseEntity<TransferDto> createTransfer(
        @Valid @RequestBody CreateTransferRequest request,
        Authentication authentication) {
    return ResponseEntity.ok(
        transferService.create(request, authentication.getName()));
}
```

Bean Validation giúp kiểm tra kiểu, độ dài, format và range ở biên API. Nó không chứng minh account đích tồn tại, người gọi có quyền chuyển tiền, số dư đủ hoặc giao dịch hợp lệ theo trạng thái. Những điều kiện này phải được kiểm tra ở service/domain và trong transaction thích hợp.

Với dữ liệu dạng enum, dùng enum type thay vì chuỗi tự do. Với số lượng, page size và độ sâu lồng nhau, đặt giới hạn nhỏ theo nghiệp vụ. Với field không được phép client điều khiển như `tenantId`, `ownerId`, `role`, `balance` hoặc `status`, loại khỏi request DTO thay vì nhận rồi cố xóa bằng regex.

## 11. Lỗi thường gặp khi dùng regex như bộ lọc injection

| Cách làm sai | Vì sao không hiệu quả | Cách thay thế |
|---|---|---|
| Xóa dấu nháy đơn trước khi chạy SQL | SQL có nhiều cú pháp và ngữ cảnh; dữ liệu có thể vẫn thay đổi query. | Prepared statement/parameterized query. |
| Chặn chuỗi `OR 1=1` | Có nhiều biểu thức tương đương và encoding khác. | Tách code/data; parameterize. |
| Chỉ cho phép chữ/số rồi nối vào SQL | Identifier/keyword vẫn có thể nguy hiểm; dữ liệu hợp lệ không đồng nghĩa query an toàn. | Bind giá trị; allowlist identifier. |
| Chặn `;` để chống nhiều câu lệnh | Injection có thể xảy ra trong một câu lệnh duy nhất. | Dùng API truy vấn an toàn. |
| Xóa `$` hoặc `{}` để chống NoSQL/template injection | Không bao phủ grammar/operator; phá dữ liệu hợp lệ. | DTO typed, query builder allowlist, sandbox template. |
| Escape HTML bằng regex | Không biết dữ liệu nằm trong text, attribute, URL hay script context. | Context-aware output encoding và template auto-escaping. |
| Regex hostname để chống SSRF | Bỏ sót DNS, IP notation, redirect, IPv6 và rebinding. | URL parser, DNS/IP validation, redirect policy và egress controls. |
| Dùng regex phức tạp trên chuỗi không giới hạn | Có thể gây ReDoS. | Giới hạn input và pattern đơn giản/hiệu quả. |

## 12. Kiểm thử injection và validation

Kiểm thử nên tập trung vào việc payload có thể thay đổi cấu trúc lệnh hoặc vượt hợp đồng dữ liệu hay không. Dùng môi trường test, dữ liệu giả và tài khoản có quyền thấp.

| Nhóm test | Dữ liệu/thao tác | Kết quả mong đợi |
|---|---|---|
| Schema validation | Thiếu field, sai kiểu, chuỗi quá dài, số ngoài range, enum lạ. | Request bị từ chối rõ ràng trước xử lý nghiệp vụ. |
| SQL injection | Dấu nháy, comment, biểu thức logic và payload SQL trong field tìm kiếm. | Được bind như dữ liệu; không đổi cấu trúc query. |
| Dynamic identifier | Gửi tên cột/table hoặc sort direction ngoài allowlist. | Bị từ chối; không ghép input tùy ý vào SQL. |
| NoSQL operator | Gửi object thay cho scalar, field `$ne`, `$where` hoặc aggregation stage lạ. | DTO/type validation từ chối; query chỉ dùng field/operator cho phép. |
| OS command | Dấu phân tách shell, option prefix, path traversal và tên file bất thường. | Không thực thi shell syntax; chỉ xử lý file/option đã cho phép. |
| LDAP | Dấu ngoặc, wildcard, backslash và NUL trong field tìm kiếm. | Filter được tạo bằng API escaping an toàn; không đổi cấu trúc ngoài ý muốn. |
| XSS/output encoding | Chuỗi chứa markup/script-like input ở text, attribute và URL. | Hiển thị như dữ liệu; không thực thi script. |
| Template/XML | Expression, directive, external entity và cấu trúc lồng sâu. | Không thực thi template ngoài quyền; parser tắt external entity và áp giới hạn. |
| SSRF | Loopback, private IP, IPv6, hostname nhiều bản ghi, redirect và DNS thay đổi. | Request bị từ chối hoặc chỉ đến đích allowlist. |
| ReDoS | Chuỗi dài gần khớp với regex. | Thời gian xử lý bị giới hạn và không làm cạn tài nguyên. |
| Authorization | Giá trị đúng định dạng nhưng trỏ đến account/tenant không có quyền. | Bị từ chối bởi policy; validation không thay thế authorization. |

Ngoài response code, kiểm tra tác dụng phụ: query không đọc thêm bản ghi, không sửa/xóa dữ liệu, không phát lệnh ngoài, không tạo outbound request ngoài allowlist và không phát sinh CPU/time bất thường. Ghi nhận request ID và loại validation thất bại nhưng không log nguyên payload nhạy cảm.

## 13. Checklist cho từng input và sink

- [ ] API có giới hạn body size, độ dài chuỗi, số phần tử và độ sâu dữ liệu?
- [ ] Request được parse bằng parser chuẩn thay vì regex tự mô phỏng grammar?
- [ ] Canonicalization/decoding được thực hiện theo một quy tắc nhất quán, không decode lặp?
- [ ] DTO có kiểu, required field, enum, range và format rõ ràng?
- [ ] Field nhạy cảm hoặc server-owned bị loại khỏi input DTO hoặc được kiểm soát riêng?
- [ ] Mọi giá trị SQL/JPQL được bind bằng parameter; identifier động lấy từ allowlist?
- [ ] NoSQL query được tạo từ field/operator cho phép, không nhận query object tùy ý?
- [ ] Lệnh hệ điều hành tránh shell và dùng executable/argument cố định, đường dẫn được kiểm soát?
- [ ] HTML/template/LDAP/XML dùng parser, encoder hoặc API chuyên dụng đúng ngữ cảnh?
- [ ] URL do người dùng cung cấp được kiểm tra bằng parser, DNS/IP policy, redirect policy và egress control?
- [ ] Regex được giới hạn kích thước và tránh ReDoS?
- [ ] Authorization và tenant/object policy được thực hiện độc lập với validation?
- [ ] Có kiểm thử payload biến thể và kiểm tra tác dụng phụ ở từng sink?

Regex là công cụ hữu ích để nhận diện một định dạng đầu vào có giới hạn. Nó không thể thay thế parser, parameterized query, allowlist, output encoding hay policy mạng. Phòng chống injection hiệu quả bắt đầu bằng việc giữ ranh giới code/data ở đúng nơi thực thi, xác thực đầu vào theo hợp đồng, giới hạn tài nguyên và kiểm thử mọi sink mà dữ liệu không tin cậy có thể đi tới.
