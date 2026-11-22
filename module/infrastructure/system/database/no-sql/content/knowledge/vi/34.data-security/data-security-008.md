# NoSQL injection qua chuỗi truy vấn, đối tượng lọc hoặc toán tử

Trong một API Java truy cập NoSQL, tham số `email`, `productId`, `status` hoặc `sortBy` thường đến từ HTTP query string, JSON body, GraphQL variables, message queue hoặc một dịch vụ khác. Các giá trị này là **dữ liệu**, không phải chỉ thị cho database. Lỗ hổng **NoSQL injection** xảy ra khi chương trình vô tình đưa dữ liệu không tin cậy vào vị trí quyết định **cấu trúc truy vấn, toán tử, tên trường, logic lọc hoặc lệnh cập nhật**.

Một ví dụ đơn giản: API tra cứu tài khoản dự kiến tìm **đúng một email**. Nhưng backend lấy một object do client gửi và gắn trực tiếp vào MongoDB filter. Nếu object ấy chứa khóa có ý nghĩa toán tử như `$ne`, database có thể hiểu nó thành điều kiện so sánh thay vì chuỗi email. Khi đó cùng một endpoint có thể truy xuất bản ghi ngoài ý định ban đầu. Tương tự, một NoSQL query dạng chuỗi có thể bị thay đổi nghĩa khi nối trực tiếp input; một update object có thể vô tình cho phép `$unset`, `$inc` hoặc sửa trường quyền hạn.

Đặc biệt, câu nói “NoSQL không dùng SQL nên không có SQL injection” là **sai về mô hình bảo mật**. Nhiều hệ NoSQL có ngôn ngữ truy vấn dạng JSON, CQL, SQL++, Cypher, JSON DSL, expression strings hoặc script. Mỗi ngôn ngữ đều có ranh giới giữa **giá trị cần tìm** và **cấu trúc điều khiển thao tác**.

Bài học thuộc chương **Bảo mật dữ liệu** của module **Database No SQL** tập trung vào ba đường tấn công do đề bài nêu: **chuỗi truy vấn**, **đối tượng lọc**, **toán tử**. Từ đó, bài mở rộng tới cập nhật, aggregation, quyền theo tenant, regex, phân trang/sort, thực thi script và phòng vệ cụ thể trong Java với MongoDB, Spring Data, Cassandra, DynamoDB, Cosmos DB và các hệ liên quan.

> **Quy tắc cốt lõi:** Client có thể cung cấp **giá trị** của điều kiện đã được server định nghĩa, nhưng không được tự ý cung cấp **toàn bộ query, operator, field path, pipeline hoặc quyền truy cập**. Hãy tạo cấu trúc lệnh trong code đáng tin cậy, bind giá trị dưới dạng đúng kiểu, xác thực phạm vi truy cập ở server và cấp quyền database tối thiểu.

## 1. Hiểu “injection” qua ranh giới dữ liệu và mã lệnh

Một lệnh truy vấn có hai phần khác vai trò:

~~~text
Trusted structure:
    FIND products WHERE tenantId = ? AND status = ?

Untrusted values:
    tenantId (must come from authenticated server context)
    status   (must be validated against allowed enum)
~~~

Ứng dụng phải quyết định **cấu trúc** trước; dữ liệu đầu vào chỉ điền vào vị trí **giá trị** được phép.

### 1.1. Dữ liệu trở thành cú pháp khi nào?

Khi một string từ client được nối vào source query hoặc một Map/JSON object không được kiểm soát được dùng trực tiếp làm expression tree, dấu ngoặc, toán tử và tên trường của input có thể được giải thích bởi query engine.

### 1.2. NoSQL injection không chỉ là đọc dữ liệu trái phép

Hậu quả có thể gồm bypass login, bỏ qua tenant filter, lấy nhiều records hơn dự kiến, sửa/xóa các trường không được phép, tạo truy vấn tiêu tốn tài nguyên hoặc làm thay đổi search/aggregation semantics.

### 1.3. Input validation không thay authorization

Ngay cả `productId` là UUID hợp lệ cũng không có nghĩa người dùng được phép đọc Product đó. **Xác thực định dạng** và **kiểm tra quyền trên đối tượng** là hai lớp khác nhau.

### 1.4. Câu lệnh hợp lệ vẫn có thể nguy hiểm

Một filter trả tất cả records có thể là cú pháp hoàn toàn hợp lệ với database. Lỗ hổng nằm ở chỗ **client không được quyền yêu cầu filter rộng ấy**.

## 2. Mô hình luồng dữ liệu bị lợi dụng

~~~mermaid
flowchart TD
    IN["Untrusted HTTP / JSON / event input"] --> DEC["Decoder / deserializer"]
    DEC -->|"Raw string concat"| Q1["Query string"]
    DEC -->|"Raw Map / JSON"| Q2["Filter or update object"]
    DEC -->|"Dynamic operators / fields"| Q3["Expression tree"]
    Q1 --> DB["NoSQL query engine"]
    Q2 --> DB
    Q3 --> DB
    DB --> IMP["Unexpected read / write / resource cost"]
~~~

Lỗi có thể xuất hiện ở controller, service, repository, query builder, custom SDK adapter, migration worker hoặc background consumer. Không nên giới hạn threat model vào một endpoint HTTP.

### 2.1. Những nguồn input cần xem là không tin cậy

- JSON body, URL query parameters và route variables.
- HTTP headers chứa sort/filter hoặc tenant metadata do client tự gửi.
- GraphQL arguments và variables, WebSocket messages.
- Dữ liệu đọc từ một database khác hoặc message queue không có provenance chắc chắn.
- Saved search templates hoặc serialized filters do user từng lưu.
- Trường được đưa trở lại hệ qua import CSV/JSON, ETL và CDC.

### 2.2. “Đã parse JSON thành object” chưa làm nó an toàn

Parser chỉ xác nhận syntax JSON hợp lệ. Object `{"$ne":null}` vẫn là object hợp lệ; nếu đặt vào vị trí predicate MongoDB thì `$ne` có thể mang nghĩa toán tử.

### 2.3. ORM/ODM cũng có ranh giới

MongoTemplate, repository framework hoặc fluent query builder có thể hỗ trợ parameter binding an toàn, nhưng nếu code tự đưa raw JSON/pipeline hoặc dynamic field name từ client vào framework thì lỗ hổng vẫn có thể tồn tại.

### 2.4. Trusted source phải được xác định

`tenantId` do một identity provider đã xác thực và ánh xạ vào security context khác với `tenantId` do client gửi trong JSON. Giữ tên field giống nhau không làm chúng có cùng mức tin cậy.

## 3. Ba họ injection chính

| Họ lỗi | Cách xảy ra | Ví dụ thành phần | Phòng vệ trọng tâm |
|---|---|---|---|
| **Query-string injection** | Nối input vào ngôn ngữ truy vấn | CQL, SQL++, Cypher, Cosmos SQL, script expression | Prepared/bound parameters, tránh string interpolation |
| **Filter-object injection** | Chuyển thẳng JSON/Map từ client thành filter | MongoDB BSON filter, Elastic DSL, aggregation stages | DTO có kiểu, server-defined query AST |
| **Operator injection** | Client chọn `$ne`, `$or`, `$regex`, `$where`, update operators hoặc expression functions | MongoDB, query DSL, update pipeline | Cố định operator, allowlist có kiểm soát |

Các họ có thể kết hợp. Ví dụ một API nhận filter JSON string rồi `Document.parse()` chính là điểm giao giữa query-string và filter-object injection.

## 4. Query-string injection: ghép chuỗi truy vấn

Một thiết kế nguy hiểm:

~~~java
// BAD: input from HTTP becomes part of query language.
String cql = "SELECT * FROM users_by_email WHERE email = '"
    + userSuppliedEmail + "'";
~~~

Nếu input có ký tự được ngôn ngữ truy vấn hiểu đặc biệt, cấu trúc biểu thức có thể bị thay đổi. Không nên xây cơ chế escape thủ công rồi coi đó là giải pháp tổng quát.

### 4.1. Parameter binding

Với Cassandra Java Driver:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

public final class UserByEmailReader {
    private final CqlSession session;
    private final PreparedStatement find;

    public UserByEmailReader(CqlSession session) {
        this.session = session;
        this.find = session.prepare(
            "SELECT user_id, email FROM users_by_email "
            + "WHERE email = ?"
        );
    }

    public ResultSet findByEmail(String email) {
        if (email == null || email.isBlank()
                || email.length() > 254) {
            throw new IllegalArgumentException("invalid email");
        }
        BoundStatement bound = find.bind(email);
        return session.execute(bound);
    }
}
~~~

Prepared statement phân biệt **CQL structure** cố định và **giá trị email**. Code cần thêm xác thực business/context, giới hạn timeout và exception handling trước production.

### 4.2. Giá trị bind được không có nghĩa mọi phần bind được

Tên table, cột, sort direction và một số fragment grammar không thể được truyền như string value parameter. Nếu client được chọn field/sort, phải map từ **allowlist server định nghĩa**, không nối tùy ý.

### 4.3. CQL không phải MongoDB BSON

Các hệ đều có thể gọi là NoSQL nhưng biểu thức truy vấn khác nhau. Prepared CQL chống chuỗi injection; typed MongoDB `Filters.eq` chống chuyển JSON thành operator. Không nên áp cơ học cùng một cách escape.

## 5. Filter-object injection trong MongoDB

Giả sử server dự định tra tài khoản bằng email:

~~~javascript
db.users.findOne({
  email: "user@example.test"
});
~~~

Nhưng application lấy trực tiếp một JSON value từ request và gắn vào filter:

~~~java
// BAD: input object is accepted without type validation.
Object untrustedEmail = requestBody.get("email");
org.bson.Document filter =
    new org.bson.Document("email", untrustedEmail);
var user = users.find(filter).first();
~~~

Nếu client gửi `email` dưới dạng object thay vì string:

~~~json
{
  "email": {
    "$ne": null
  }
}
~~~

Khi object trên được giải thích như BSON predicate, `$ne` có nghĩa **không bằng** thay vì một email literal. Đây là ví dụ để hiểu ranh giới kiểu/cú pháp trong môi trường thử nghiệm, không phải một yêu cầu đăng nhập hợp lệ.

### 5.1. Type confusion là điểm cốt lõi

API mong `email: String`, nhưng code nhận `Object` hoặc `Map<String,Object>` và đưa nguyên dạng vào database. Một JSON object có thể bị hiểu thành expression.

### 5.2. Không chỉ `$ne`

Các key bắt đầu bằng `$` có thể đại diện cho toán tử so sánh, logic, pattern hoặc expression tùy vị trí và phiên bản MongoDB. Không phải mọi vị trí đều chấp nhận mọi operator; **ngữ nghĩa phụ thuộc context query**.

### 5.3. `Document.parse()` không phải sanitization

Hàm parse chuyển chuỗi JSON/BSON extended JSON thành cấu trúc, không chứng minh người gọi được phép quyết định toàn bộ predicate.

### 5.4. Nên kiểm kiểu trước khi query

Input cần được deserialized vào DTO có `String email`, có length/format policy phù hợp, reject array/object và unknown fields. Sau đó application dựng filter bằng `Filters.eq` với trường cố định.

## 6. Một đoạn login tìm bản ghi không nên là xác thực

Giả sử code xấu:

~~~java
// BAD: illustrative anti-pattern; never authenticate this way.
var filter = new org.bson.Document()
    .append("username", rawBody.get("username"))
    .append("password", rawBody.get("password"));
var matched = users.find(filter).first();
~~~

Đây là hai lỗi cùng lúc:

1. JSON object bất kỳ được trao quyền làm query predicate.
2. Password được dùng như dữ liệu lọc trực tiếp, thay vì xác minh mật khẩu theo cơ chế lưu trữ hash an toàn.

### 6.1. Hướng thiết kế đăng nhập đúng

Server nhận `username` và `password` **dưới dạng string có kiểu và giới hạn**, tìm account bằng equality trên username đã canonicalize, rồi xác minh password bằng thuật toán hash chuyên dụng đã được cấu hình. Không lưu plaintext password và không query bằng raw password.

### 6.2. Không trả về account vì có “một record match”

Một query rộng bất ngờ trả record đầu tiên không chứng minh caller sở hữu account đó. Phải kiểm credential, account state, MFA khi áp dụng và audit/rate limiting.

### 6.3. Tham số tài khoản cần canonicalization có chủ đích

Normalize username/email theo chính sách sản phẩm và dữ liệu đã lưu; tránh normalize khác ở create và login hoặc làm hai tài khoản trùng logic. Việc normalize không phải là biện pháp chống operator injection.

### 6.4. Không log mật khẩu hoặc complete request body

Nếu injection bị nghi ngờ, log loại lỗi, requestId, endpoint và field validation failure; không vô tình đưa secrets vào SIEM hoặc error messages.

## 7. Safe MongoDB equality bằng Mongo Java Driver

Một adapter có thể dựng filter hoàn toàn ở server:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Optional;

public final class UserLookup {
    private final MongoCollection<Document> users;

    public UserLookup(MongoCollection<Document> users) {
        this.users = users;
    }

    public Optional<Document> findByUsername(
            String trustedTenantId,
            String normalizedUsername) {
        if (trustedTenantId == null
                || normalizedUsername == null
                || normalizedUsername.isBlank()
                || normalizedUsername.length() > 128) {
            throw new IllegalArgumentException("invalid identity");
        }

        Bson filter = Filters.and(
            Filters.eq("tenantId", trustedTenantId),
            Filters.eq("usernameNormalized", normalizedUsername)
        );

        return Optional.ofNullable(users.find(filter).first());
    }
}
~~~

### 7.1. `tenantId` không lấy từ body của client

Tên tham số `trustedTenantId` nhắc rằng giá trị phải đến từ **security context đã xác thực**, không phải một chuỗi tenantId không được kiểm tra do client gửi.

### 7.2. `Filters.eq` là cấu trúc cố định

Application chọn equality trên hai field có tên cố định. User chỉ cung cấp value dạng String, nên không thể yêu cầu `$ne` hoặc `$or` như một nhánh của predicate.

### 7.3. Dữ liệu về account vẫn nhạy cảm

Không trả nguyên document gồm password hashes, reset tokens, permissions và private metadata. Projection/DTO và authorization policy vẫn bắt buộc.

### 7.4. Type-safe không tự bảo đảm quyền

Một username hợp lệ có thể thuộc tenant khác. Chỉ query equality không đủ nếu ứng dụng dùng user-supplied tenant context hoặc quyền truy cập không được xét.

## 8. Input từ HTTP query string có thể bị parse thành object

Một client gửi:

~~~text
GET /api/products?status=ACTIVE
~~~

Server mong `status` là một enum String. Nhưng một số web frameworks hoặc query parsers có thể nhận syntax dạng bracket:

~~~text
GET /api/products?status[$ne]=ARCHIVED
~~~

Nếu parser chuyển thành nested object và application truyền object ấy vào Mongo filter, operator injection có thể xảy ra. Việc parser diễn giải bracket syntax **phụ thuộc framework và cấu hình**, không phải mọi Java web server đều tự làm như vậy.

### 8.1. Không dựa vào “đây là query parameter nên chắc là string”

Một số layers map nhiều values, array, nested keys hoặc JSON string. Server cần khai báo schema và từ chối cấu trúc ngoài ý định.

### 8.2. `status` là một enum, không phải expression

Cho phép `"ACTIVE"`, `"ARCHIVED"` theo business contract; không cho `{"$ne":"ARCHIVED"}` hoặc raw Mongo predicate.

### 8.3. Duplicate parameter

`?status=ACTIVE&status=ARCHIVED` có thể được framework xử lý theo first/last/list. Định nghĩa hành vi rõ, tránh tầng auth và tầng query nhìn hai giá trị khác nhau.

### 8.4. Normalization ở một chỗ

Nếu gateway decode URL theo cách khác service, có thể phát sinh parser differential. Chỉ normalize/canonicalize theo một hợp đồng, không suy rằng frontend validation đã đủ.

## 9. Operator injection: client được quyền chọn logic

MongoDB có nhiều toán tử có ý nghĩa khác nhau:

| Nhóm | Ví dụ khái niệm | Rủi ro nếu để client chọn tùy ý |
|---|---|---|
| Comparison | `$eq`, `$ne`, `$gt`, `$lt`, `$in` | Từ exact lookup thành truy vấn rộng |
| Logical | `$and`, `$or`, `$nor` | Đảo logic hoặc bỏ điều kiện |
| Pattern | `$regex` | Broad matches, query cost/regex abuse |
| Expression | `$expr`, `$where` tùy phiên bản | Đưa expression/script vào evaluation |
| Array | `$elemMatch`, `$all` | Truy cập nested data ngoài dự kiến |
| Existence/type | `$exists`, `$type` | Dò field/schema, mở rộng filter |
| Update | `$set`, `$unset`, `$inc`, `$rename` | Sửa/xóa field không được phép |
| Pipeline | `$lookup`, `$group`, `$project`… | Query cost, leakage và side effects tùy stages/quyền |

Danh sách chỉ minh họa. Khả năng dùng một operator phụ thuộc vị trí, phiên bản và engine. **Không phải ký hiệu `$` tự nó nguy hiểm ở mọi chỗ**; nguy hiểm là khi untrusted input được hiểu là operator thay vì literal data.

### 9.1. User-defined operator không phải tính năng filter mặc định

Một giao diện filter nên định nghĩa rõ: `status IN enum`, `priceMinor between min/max`, `createdAt after`, không nhận toàn bộ MongoDB expression language.

### 9.2. Nếu cần advanced filters

Tạo **DSL giới hạn** với grammar, depth, allowed fields, allowed operators, type checking và cost budget. Compiler đáng tin cậy chuyển DSL thành BSON/SDK AST.

### 9.3. Không xử lý bằng cách xóa mọi ký tự `$` trong value

Một chuỗi literal có thể chứa ký tự `$` hợp lệ (ví dụ tên sản phẩm), nhưng **giá trị** trong equality không nên được parse như operator. Ranh giới kiểu và query structure quan trọng hơn blacklist ký tự.

### 9.4. Operators phải được quyền hóa theo API

Một endpoint customer không nên được quyền dùng arbitrary admin-only filters, kể cả khi query engine chấp nhận. Query language capability phải được chia nhỏ theo role/use case.

## 10. Injection qua logic tenant và toán tử `$or`

Một yêu cầu an toàn là mọi Product read phải nằm trong tenant đã xác thực.

Thiết kế sai về logic:

~~~javascript
// BAD: conceptual MongoDB predicate.
{
  "$or": [
    {"tenantId": "trusted-tenant"},
    {"status": "ACTIVE"}
  ]
}
~~~

Điều kiện `status=ACTIVE` trở thành một nhánh độc lập, có thể match records của tenant khác. Đây không chỉ là lỗi “escape” mà là lỗi **cấu trúc authorization predicate**.

### 10.1. Server-enforced AND

Filter nên được xây như:

~~~java
Bson filter = Filters.and(
    Filters.eq("tenantId", trustedTenantFromPrincipal),
    Filters.eq("status", validatedStatus)
);
~~~

### 10.2. Không nối raw client filter vào một nhánh OR

Ngay cả khi phía server có một tenant filter hợp lệ, kết hợp sai toán tử làm tenant predicate không còn bảo vệ mọi nhánh.

### 10.3. Không tin client tự chọn `tenantId`

Một request có `"tenantId":"other-tenant"` không được tự định tuyến vào tenant ấy nếu principal không có quyền. Trong hệ có admin cross-tenant access, policy phải kiểm role rõ ràng và audit.

### 10.4. Authz gắn cả object ID

Nếu tìm theo `_id`, luôn dùng filter gắn tenant/owner khi phù hợp. `_id` đủ duy nhất về kỹ thuật không đồng nghĩa bearer có quyền xem bản ghi.

### 10.5. Không xem database filter là lớp bảo mật duy nhất

RBAC DB, IAM, route authorization, ownership policy, audit và response projection tạo defense in depth. Một bug trong application query vẫn có tác động nhỏ hơn nếu DB principal không được đọc mọi collections.

## 11. Injection qua bản cập nhật (update object)

Một endpoint cho đổi tên hiển thị cần **chỉ** sửa `displayName`. Code nguy hiểm:

~~~java
// BAD: untrusted update document controls update operators.
Document rawUpdate = Document.parse(request.getUpdateJson());
users.updateOne(
    Filters.eq("_id", trustedUserId),
    rawUpdate
);
~~~

Client có thể gửi các update operators mà server không dự kiến. Một example chỉ để nhận diện dạng dữ liệu:

~~~json
{
  "$set": {
    "role": "ADMIN"
  }
}
~~~

Nếu endpoint truyền raw update vào database và DB principal có quyền ghi field, có thể dẫn tới **mass assignment / operator injection**. Việc MongoDB chấp nhận hay từ chối chính xác một dạng update còn tùy API/version và update syntax.

### 11.1. Chỉ cập nhật fields từ allowlist

~~~java
import com.mongodb.client.model.Updates;

Bson safeUpdate = Updates.combine(
    Updates.set("displayName", validatedDisplayName),
    Updates.currentDate("updatedAt")
);

users.updateOne(
    Filters.and(
        Filters.eq("_id", trustedUserId),
        Filters.eq("tenantId", trustedTenantId)
    ),
    safeUpdate
);
~~~

### 11.2. Không nhận raw update stage khi chỉ cần patch DTO

API có thể định nghĩa `PATCH /me` body `{ "displayName":"..." }`, chứ không nhận `{"$set":...}`. Mọi field không được phép phải bị reject hoặc xử lý theo hợp đồng rõ.

### 11.3. Fields nhạy cảm

`role`, `tenantId`, `billingStatus`, `balance`, `isAdmin`, `deleted`, `version` và `passwordHash` không được thay qua generic patch endpoint chỉ vì chúng nằm trong cùng document.

### 11.4. Conditional update và idempotency

Nếu update ảnh hưởng nghiệp vụ, thêm expected version/CAS, commandId và authorization. Injection prevention không thay transaction correctness.

## 12. Dynamic field path injection

Ngay cả khi ứng dụng dùng `Updates.set`, cho client chọn **tên trường** vẫn nguy hiểm:

~~~java
// BAD: user controls the field path.
String field = request.getFieldName();
Bson update = Updates.set(field, request.getValue());
~~~

`field` có thể chỉ đến field nested, sensitive hoặc có cú pháp đường dẫn đặc biệt. Không nên nghĩ “SDK builder đã làm mọi thứ an toàn” khi **field path là cú pháp** được truyền vào builder.

### 12.1. Allowlist tên field

~~~java
public enum EditableField {
    DISPLAY_NAME("displayName"),
    PREFERRED_LANGUAGE("preferredLanguage");

    private final String dbPath;

    EditableField(String dbPath) {
        this.dbPath = dbPath;
    }

    public String dbPath() {
        return dbPath;
    }
}
~~~

Server map một enum được phép sang database path cố định. Không lấy raw text làm field path.

### 12.2. Dấu chấm và prefix đặc biệt

Trong nhiều query/update languages, dấu chấm thể hiện nested field path, các ký hiệu đặc biệt có thể mang ngữ nghĩa. Chỉ “escape ký tự” không tương đương xác minh quyền sửa field.

### 12.3. Không chấp nhận `Map<String,Object>` như unrestricted update

Nếu API cần patch nhiều fields, hãy dùng DTO hoặc một patch DSL giới hạn các field/operation. Mỗi field có type/range và quyền ghi riêng.

### 12.4. Paths nội bộ cần được giữ kín

Trường audit/version/tombstone/owner không nên sửa từ public API dù người dùng đoán được tên path.

## 13. Injection qua sort, projection và pagination

Không chỉ filter mới chứa cú pháp. Các tham số như `sortBy`, `order`, `fields`, `groupBy`, `pageSize`, `skip` cũng ảnh hưởng query plan và dữ liệu được trả.

### 13.1. Dynamic sort field

~~~java
// BAD: free-form field name from HTTP.
var sort = com.mongodb.client.model.Sorts.ascending(
    request.getSortBy()
);
~~~

Builder đúng về BSON syntax nhưng cho client chọn trường không giới hạn; nó có thể đòi sort theo field nặng, nhạy cảm hoặc không indexed.

### 13.2. Safe sort mapping

~~~java
private static String allowedSortPath(String sortBy) {
    return switch (sortBy) {
        case "created" -> "createdAt";
        case "price"   -> "priceMinor";
        default -> throw new IllegalArgumentException(
            "unsupported sort"
        );
    };
}
~~~

### 13.3. Projection cũng cần allowlist

Nếu client có thể yêu cầu arbitrary fields, đừng để nó lấy `passwordHash`, `internalNotes`, `resetToken` hoặc tenant data. Server xây response DTO; database projection chỉ là tối ưu giảm data transfer.

### 13.4. Cap limit và skip

`limit=1000000` hoặc deep `skip` có thể gây scan/network/GC lớn dù không có `$` operator. Cho phép phân trang nhưng đặt upper bound; ưu tiên keyset/continuation token nếu phù hợp.

### 13.5. Không trao quyền truy vấn qua cursor token chưa kiểm

Continuation token do client trả lại cần được kiểm cấu trúc/chữ ký/tenant scope nếu dùng như capability; không tin raw bookmark chứa field/query overrides.

## 14. JSON DSL: cấu trúc có thể bị injection dù không có chuỗi

Một endpoint chấp nhận:

~~~json
{
  "filter": {
    "status": "ACTIVE"
  }
}
~~~

và chạy:

~~~java
// BAD: arbitrary JSON is used directly as MongoDB filter.
Document filter = Document.parse(request.getFilterJson());
return collection.find(filter).into(new java.util.ArrayList<>());
~~~

Đây là **query-by-JSON injection**: không cần thoát khỏi chuỗi theo kiểu SQL; chính object là lệnh.

### 14.1. Đừng parse “filter JSON” từ public API

Trừ khi sản phẩm chủ ý cung cấp query language có sandbox và quyền rõ, hãy nhận typed fields như `status`, `minPrice`, `maxPrice`.

### 14.2. Nếu cần saved filters

Lưu AST ở dạng **versioned, validated DSL** chứ không lưu raw vendor query. Khi đọc lại phải validate schema/role vì một filter cũ có thể đã trở nên không hợp lệ với policy mới.

### 14.3. JSON nesting depth

Một filter có hàng nghìn nested `$or`/conditions có thể tốn parse, plan và memory. Giới hạn max depth, max terms, max list lengths và query cost.

### 14.4. Dữ liệu lưu trong DB cũng có thể không tin cậy

Nếu một người dùng lưu report configuration chứa raw query rồi scheduler chạy bằng DB admin credentials, injection có thể xảy ra **ở thời điểm chạy lại**, không chỉ ở HTTP request ban đầu.

## 15. Thiết kế DTO filter an toàn trong Java

Thay vì nhận raw MongoDB query:

~~~json
{
  "status": "ACTIVE",
  "minPriceMinor": 1000,
  "maxPriceMinor": 500000,
  "sortBy": "created",
  "limit": 50
}
~~~

Định nghĩa record có kiểu:

~~~java
public enum ProductStatus {
    ACTIVE, ARCHIVED
}

public enum ProductSort {
    CREATED, PRICE
}

public record ProductSearchRequest(
    ProductStatus status,
    Long minPriceMinor,
    Long maxPriceMinor,
    ProductSort sortBy,
    Integer limit
) {}
~~~

### 15.1. Strict schema binding

JSON `{"status":{"$ne":"ARCHIVED"}}` không thể biểu diễn thành enum `ProductStatus`. API nên trả `400 Bad Request` khi sai kiểu, không âm thầm chuyển object thành Map rồi đưa xuống database.

### 15.2. Unknown fields

Một request có `"includeAllTenants":true` không được tự làm thay đổi truy vấn. Có thể chọn reject unknown fields để phát hiện client sai/attempt injection; lựa chọn compatibility phải rõ.

### 15.3. Numeric range

`minPriceMinor`, `maxPriceMinor`, `limit` cần được kiểm non-negative, max bound và quan hệ min≤max. Kiểm kiểu không thay business validation.

### 15.4. Không tự chọn data authority

DTO chỉ mô tả điều kiện nghiệp vụ cho phép; trusted tenant context/authorization được lấy từ server context, không từ client DTO.

## 16. Java MongoDB: biên dịch DTO thành filter cố định

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.FindIterable;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.ArrayList;
import java.util.List;

public final class ProductSearchRepository {
    private final MongoCollection<Document> products;

    public ProductSearchRepository(
            MongoCollection<Document> products) {
        this.products = products;
    }

    public List<Document> search(
            String tenantIdFromPrincipal,
            ProductSearchRequest req) {

        if (req == null || req.status() == null) {
            throw new IllegalArgumentException(
                "status required"
            );
        }

        long min = req.minPriceMinor() == null
            ? 0 : req.minPriceMinor();
        long max = req.maxPriceMinor() == null
            ? 10_000_000_000L : req.maxPriceMinor();

        if (min < 0 || min > max
                || max > 10_000_000_000L) {
            throw new IllegalArgumentException(
                "invalid price range"
            );
        }

        int limit = req.limit() == null ? 50 : req.limit();
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException(
                "limit out of range"
            );
        }

        Bson filter = Filters.and(
            Filters.eq("tenantId", tenantIdFromPrincipal),
            Filters.eq("status", req.status().name()),
            Filters.gte("priceMinor", min),
            Filters.lte("priceMinor", max)
        );

        Bson sort = req.sortBy() == ProductSort.PRICE
            ? Sorts.ascending("priceMinor", "_id")
            : Sorts.descending("createdAt", "_id");

        FindIterable<Document> cursor = products.find(filter)
            .sort(sort)
            .limit(limit);

        return cursor.into(new ArrayList<>());
    }
}
~~~

### 16.1. Vì sao cấu trúc an toàn hơn?

Operator, field paths, tenant equality, sort fields và limit upper bound đều do server chọn. Client chỉ ảnh hưởng các typed values trong phạm vi contract.

### 16.2. Còn thiếu điều gì cho production?

Authorization principal, response DTO/projection, index design, timeout/maxTimeMS, consistent pagination/cursor, metrics, read concern và lỗi SDK cần được bổ sung theo hệ thống thực.

### 16.3. Query đúng syntax chưa chắc chi phí chấp nhận

Price range rộng có thể scan nhiều rows nếu không có index phù hợp. Validate input và đo query plan/resource usage vẫn cần thiết.

### 16.4. Giá trị numeric cần kiểm loại

Nếu raw JSON gửi `minPriceMinor` là object/array, Jackson phải reject thay vì tự đổi thành cấu trúc BSON.

### 16.5. Tenant scope phải luôn được giữ

Mọi branch tìm kiếm phải đi qua `tenantIdFromPrincipal` và kiểm quyền theo tenant. Không xây một endpoint “generic search” được phép bỏ `tenantId` bằng cờ do client gửi.

## 17. Jackson và validation ở ranh giới HTTP

Một `ObjectMapper` có thể được cấu hình để phát hiện unknown properties:

~~~java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper()
    .configure(
        DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES,
        true
    );

ProductSearchRequest request = mapper.readValue(
    jsonBody,
    ProductSearchRequest.class
);
~~~

### 17.1. Chọn DTO thay `Map<String,Object>`

DTO giúp xác định chính xác `status` là enum, `limit` là integer. Nhưng deserialization config và custom deserializers cũng phải được kiểm soát; không tin “có class Java” là đủ nếu cho polymorphic object bypass.

### 17.2. Không bật default typing bừa bãi

Polymorphic deserialization trên dữ liệu không tin cậy có risk riêng nếu cấu hình thiếu kiểm soát. Dùng các target types cố định, allowlist types và SDK/version an toàn.

### 17.3. Bean Validation là lớp bổ sung

`@NotNull`, `@Min`, `@Max`, `@Size` giúp trả 4xx sớm. Nhưng injection prevention chủ yếu là cấu trúc query được xây bằng code, không chỉ kiểm một regex input.

### 17.4. Parse failure phải dừng trước repository

Nếu type mismatch xảy ra, đừng fallback sang raw `JsonNode` hoặc parse lại thành `Document` để “cố gắng hỗ trợ client cũ”.

### 17.5. Canonicalization không thay binding

Trim, normalize Unicode hoặc lowercase có thể cần cho domain matching; những bước này không thay `Filters.eq`, parameterization và authorization.

## 18. Spring Data MongoDB: an toàn theo query builder

Với Spring Data MongoDB, có thể xây query từ fields cố định:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public final class ProductSearchDao {
    private final MongoTemplate template;

    public ProductSearchDao(MongoTemplate template) {
        this.template = template;
    }

    public java.util.List<ProductDocument> find(
            String trustedTenantId,
            ProductStatus status,
            int limit) {
        if (status == null || limit < 1 || limit > 100) {
            throw new IllegalArgumentException("invalid request");
        }

        Query query = new Query(
            Criteria.where("tenantId").is(trustedTenantId)
                .and("status").is(status.name())
        );
        query.with(
            Sort.by(Sort.Direction.DESC, "createdAt")
        );
        query.limit(limit);
        return template.find(
            query, ProductDocument.class, "products"
        );
    }
}
~~~

`ProductDocument` ở đây là class domain/repository do ứng dụng định nghĩa, không phải class có sẵn trong Spring.

### 18.1. Query builder không bảo vệ raw query escape hatch

Nếu code dùng `BasicQuery` với JSON do client gửi hoặc `Criteria` nhận dynamic field/operator do user chọn, khả năng injection quay lại.

### 18.2. Repository query annotations

Các cơ chế binding parameters của Spring có thể escape/serialize String values theo API, nhưng string interpolation/SpEL/raw JSON query construction phải được review theo version và context. Không khẳng định mọi `@Query` expression tự an toàn.

### 18.3. Không trả entity trực tiếp

`ProductDocument` có thể chứa fields nội bộ; mapping sang response DTO và field-level authorization vẫn cần thiết.

### 18.4. Validate ownership trong write path

Update theo `_id` mà thiếu `tenantId` hoặc expected version có thể sửa record ngoài phạm vi dù input không có operator injection.

## 19. `$regex`: value được escape chưa có nghĩa query rẻ

Một API search name có thể được phép tìm text literal, không phải chạy regex tùy ý.

~~~java
import com.mongodb.client.model.Filters;
import org.bson.conversions.Bson;
import java.util.regex.Pattern;

public Bson nameContainsLiteral(String input) {
    if (input == null || input.length() > 64) {
        throw new IllegalArgumentException("search term too long");
    }
    String quoted = Pattern.quote(input);
    return Filters.regex("nameNormalized", quoted, "i");
}
~~~

### 19.1. Dùng literal regex thay user-defined pattern

`Pattern.quote` thể hiện intent match literal string, không cho user cung cấp các regex operators. Cách MongoDB/PCRE interpret pattern/options cần kiểm theo version/client encoding.

### 19.2. Regex DoS vẫn có thể tồn tại

Nếu cho arbitrary regex, các pattern phức tạp hoặc unbounded fields có thể gây CPU cao. Ngay cả escaped literal regex có thể khiến database scan nếu không dùng được index.

### 19.3. Index design cho search

Text search, autocomplete, prefix index hoặc search engine chuyên dụng có thể phù hợp hơn substring regex trên tập records lớn. Query timeout và limit vẫn cần.

### 19.4. Character blacklist không phải căn cơ

Cấm `$` hay `*` trong tên sản phẩm có thể phá dữ liệu hợp lệ. Xây đúng expression từ literal và kiểm cost tốt hơn tự lọc từng ký tự.

### 19.5. Cross-tenant regex

Regex filter vẫn phải kết hợp với tenant equality từ principal; không dùng search như một đường bypass authz.

## 20. `$where`, expression và server-side script

Một số NoSQL APIs từng hoặc đang hỗ trợ expression/script evaluation như JavaScript, Lua hoặc expression language riêng. Nếu input được nối vào code của biểu thức, ranh giới dữ liệu–mã lệnh bị phá.

### 20.1. Không nhận raw source code từ người dùng

Một API `filterScript` rồi đưa vào `$where`/dynamic code là thiết kế có risk cao. Tính năng có thể đã deprecated/disabled/giới hạn trong một số versions; không nên dựa vào nó để xây query từ public input.

### 20.2. Thay bằng query operators định sẵn

Một rule `price between min and max` có thể dùng typed `$gte`/`$lte`, không cần user-defined JavaScript expression.

### 20.3. Nếu cần rule engine

Xây DSL có grammar giới hạn, interpreter sandbox, timeout, memory/step budget, role permissions và audit. Đây là capability riêng, không phải raw database filter.

### 20.4. DB principal tối thiểu

Tài khoản ứng dụng không nên có quyền script/admin/write ngoài nhu cầu. Khi server-side scripts được dùng nội bộ, phải review code provenance và khả năng truy cập data.

## 21. Aggregation pipeline injection

MongoDB aggregation dùng nhiều stages; một pipeline có thể gồm match, project, lookup, group, sort, merge/write stages tùy API/quyền.

~~~java
// BAD: accepting arbitrary pipeline stages as client input.
java.util.List<org.bson.Document> stagesFromUser =
    request.getPipelineStages();
collection.aggregate(stagesFromUser);
~~~

### 21.1. Pipeline là chương trình truy vấn

Cho phép client thêm `$lookup`, `$group` hoặc stages khác có thể gây fan-out, memory pressure, đọc ngoài dự kiến hoặc mutation với một số stages, nếu quyền cho phép.

### 21.2. Hạn chế stage grammar

Nếu sản phẩm cần report builder, chỉ cho các dimensions/measures được phép, limits, lookup paths cố định và query cost budget. Compiler server build pipeline.

### 21.3. Không “chặn một vài stage nguy hiểm” rồi nhận mọi thứ còn lại

Blacklist khó đầy đủ, đặc biệt khi vendor thêm operators mới. Allowlist capability và typed AST an toàn hơn.

### 21.4. Định nghĩa read-only execution

Application service credential chỉ nên được phép đọc collections cần thiết; không dùng admin DB credentials cho report API.

### 21.5. Giới hạn trả kết quả

Aggregation có thể sinh hàng triệu rows. Cap page size, max execution time, memory/spill, concurrency và response bytes; không chỉ dựa vào filter.

## 22. Query-by-example và mass assignment

Một anti-pattern:

~~~java
// BAD: all fields from request are treated as database predicates.
Document query = new Document(requestBody);
collection.find(query);
~~~

Nếu request có fields mà API không dự kiến, query semantics có thể thay đổi. Tương tự, `save(requestBodyAsEntity)` có thể cho phép set các fields như `role` hoặc `tenantId`.

### 22.1. Chỉ nhận fields được định nghĩa

API tìm kiếm và API cập nhật nên có DTO riêng, không tái sử dụng internal persistence object làm input công khai.

### 22.2. Entity model không phải public API schema

Một field được lưu ở database không đồng nghĩa client có quyền search/update nó. Public contract phải độc lập với internal schema.

### 22.3. Hidden fields không phải bảo mật

Ẩn trường trong frontend form không ngăn client tự gửi field đó. Server phải enforce allowlist.

### 22.4. Unknown properties cần chính sách

Reject unknown fields có thể giúp bắt lỗi hợp đồng và dấu hiệu thử toán tử. Nếu chọn ignore để tương thích, tuyệt đối không đem raw object cũ xuống database.

## 23. DynamoDB: expression strings và placeholders

DynamoDB dùng các expression như `KeyConditionExpression`, `FilterExpression`, `UpdateExpression` và `ConditionExpression`. Các phần **expression syntax** nên do server định nghĩa, còn **giá trị** được truyền qua `ExpressionAttributeValues`.

Ví dụ Java AWS SDK v2:

~~~java
import java.util.Map;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.QueryRequest;

String tenantPartitionKey = "TENANT#" + trustedTenantId;

QueryRequest req = QueryRequest.builder()
    .tableName("OrdersByTenant")
    .keyConditionExpression("#pk = :tenantPk")
    .expressionAttributeNames(Map.of(
        "#pk", "PK"
    ))
    .expressionAttributeValues(Map.of(
        ":tenantPk", AttributeValue.builder()
            .s(tenantPartitionKey)
            .build()
    ))
    .limit(50)
    .build();
~~~

### 23.1. Placeholders bind values

`:tenantPk` không được chèn như một phần expression syntax; SDK gửi nó qua giá trị typed. Tên bảng và attribute names không thể được bảo vệ bằng value placeholder.

### 23.2. `ExpressionAttributeNames` không tự là authorization

Map `#field -> rawUserInput` vẫn có thể cho người dùng chọn attribute path không được phép. Server cần allowlist names từ một tập cố định.

### 23.3. FilterExpression có chi phí

Trong một số DynamoDB operations, filter được áp sau bước đọc/truy cập, nên scan rộng với filter không biến thành point lookup. Giới hạn query cost, key model và pagination.

### 23.4. Conditional write

`ConditionExpression` để bảo vệ version/quota phải do server xây từ business invariant; không để client chọn điều kiện khiến update vượt ràng buộc.

### 23.5. IAM

DB role cần giới hạn tables/operations và điều kiện access phù hợp; application parameterization không thay IAM.

## 24. Cosmos DB for NoSQL: parameterized SQL query

Cosmos DB for NoSQL có query language dạng SQL và hỗ trợ parameters. Với Azure Cosmos DB Java SDK, có thể dùng `SqlQuerySpec`:

~~~java
import com.azure.cosmos.models.SqlParameter;
import com.azure.cosmos.models.SqlQuerySpec;
import java.util.List;

SqlQuerySpec query = new SqlQuerySpec(
    "SELECT * FROM c "
      + "WHERE c.tenantId = @tenant "
      + "AND c.status = @status",
    List.of(
        new SqlParameter("@tenant", trustedTenantId),
        new SqlParameter("@status", validatedStatus)
    )
);
~~~

### 24.1. Value parameters khác identifiers

Tham số `@status` là value. Nếu muốn dynamic field name, phải map từ allowlist thay vì string interpolation vào `c.<field>`.

### 24.2. Partition key

Nếu query không có partition key hoặc định tuyến rộng, có thể gây fan-out/RU lớn. Security-safe syntax không tự bảo đảm performance-safe query.

### 24.3. Tenant boundary

Không tin `tenantId` do client gửi; enforcement phải dựa trên identity/authorization. Cosmos resource roles, data permissions và query predicates cần phù hợp.

### 24.4. Giới hạn RU và timeout

Even parameterized queries có thể tiêu thụ nhiều request units với dataset lớn. Có max page size, timeout, rate limits và telemetry cho query charges.

## 25. Couchbase SQL++ và tên field động

SQL++/N1QL là query language có expression syntax. Tránh nối input trực tiếp:

~~~java
// BAD conceptual pattern:
String query = "SELECT o.* FROM orders o WHERE o.status = '"
    + suppliedStatus + "'";
~~~

Giải pháp là **parameterized value** theo SDK, ví dụ conceptually:

~~~text
SELECT o.*
FROM `bucket`.`scope`.`orders` AS o
WHERE o.tenantId = $tenant
  AND o.status = $status
LIMIT 50
~~~

`$tenant`, `$status` được binding qua query options thay vì nối chuỗi value.

### 25.1. Tên bucket/scope/collection

Identifiers trong statement cần được chọn bởi server, không phải raw user value. Nếu ứng dụng multi-tenant có mapping collection, phải dùng trusted lookup từ tenant context.

### 25.2. Query service và KV operation khác nhau

KV GET theo key có access path khác SQL++ query. Không giả định parameterized query luôn hiệu quả; index design vẫn cần.

### 25.3. Từ chối `query` tự do

API public không nên nhận SQL++ statement của client dưới một quyền DB rộng, trừ khi thiết kế riêng một read-only analytics sandbox với quotas, allowlist và authorization.

## 26. Neo4j Cypher: bind properties, allowlist labels

Graph database như Neo4j có Cypher query language:

~~~cypher
MATCH (o:Order {tenantId: $tenantId, orderId: $orderId})
RETURN o
LIMIT 1
~~~

Với Java driver hiện đại, truyền values qua named parameters. Ví dụ hướng tư duy:

~~~java
var result = driver.executableQuery(
    "MATCH (o:Order {tenantId: $tenantId, orderId: $orderId}) "
  + "RETURN o LIMIT 1"
).withParameters(Map.of(
    "tenantId", trustedTenantId,
    "orderId", validatedOrderId
)).execute();
~~~

### 26.1. Label, relationship type và property path

Một số vị trí cấu trúc có khả năng parameterization phụ thuộc Cypher/driver version; đừng ghép raw label/relationship name từ client. Dùng allowlist domain concepts và query templates.

### 26.2. Pattern traversal có chi phí

Cho user chọn arbitrary path length và graph relationship patterns có thể dẫn tới query explosion dù parameters hợp lệ. Giới hạn depth, result size và allowed relationships.

### 26.3. Tenant isolation

Một graph traversal có thể đi từ tenant node sang quan hệ vượt scope nếu data model/authorization không được bảo vệ. Bind tenant filter và enforce quyền theo graph semantics.

## 27. Elasticsearch/OpenSearch JSON query DSL

Search engines thường nhận JSON query DSL. Nếu API cho client gửi raw DSL, một request có thể yêu cầu wildcard, expensive regex, script, broad match hoặc fields không được phép tùy engine/permissions.

### 27.1. Query DSL vẫn là mã điều khiển tìm kiếm

Không có dấu nháy đơn như SQL không làm raw JSON query an toàn. JSON có operator names và nesting semantics.

### 27.2. `query_string` và literal search

`query_string` có cú pháp tìm kiếm với operators riêng. Nếu API dự định nhận “từ khóa bình thường”, đưa raw input vào query-string grammar có thể đổi nghĩa tìm kiếm. Cân nhắc `match`, `term`, `simple_query_string` với semantics được hiểu rõ hoặc cơ chế escaping phù hợp; không coi lựa chọn nào tự thay authorization.

### 27.3. Fixed fields

Server chọn index/fields được tìm; không cho client tự chọn `_source` fields nhạy cảm, sort/script fields và wildcard index names.

### 27.4. Query cost budget

Limit size/from, depth, wildcard/regex complexity, script execution, timeouts và multi-tenant quotas. Resource exhaustion cũng là hậu quả của unrestricted query capability.

### 27.5. Search index có thể stale

Một index search không luôn là authority để quyết định quyền hoặc trạng thái tài chính. Authorization và strong business checks phải ở đường dữ liệu đúng.

## 28. Redis: phân biệt key value với command/script construction

Redis protocol truyền commands/arguments có cấu trúc. Gửi một string user qua `GET key` không tự biến nó thành lệnh `DEL` khác. Tuy vậy, **tự xây script Lua hoặc generic command từ input** có thể làm dữ liệu trở thành mã lệnh.

### 28.1. Không ghép code Lua từ user data

~~~java
// BAD conceptual approach: dynamically concatenate user text
// into a Lua script that will later be evaluated.
String script = trustedPrefix + untrustedExpression;
~~~

### 28.2. Script cố định, dữ liệu qua arguments

Một cách dùng Redis Lua an toàn hơn là script **cố định/được review** và chỉ truyền keys, values qua `KEYS`/`ARGV` theo API, với key ownership/capability đã validate.

### 28.3. Key namespace và tenant

Đừng cho client viết tùy ý key của tenant khác vì key là string. Key có thể là dữ liệu ở Redis, nhưng truy cập key nào vẫn là **authorization decision** của application.

### 28.4. Wildcard/key scan

Nếu API cho raw glob pattern hoặc arbitrary key-range scan, query có thể tốn tài nguyên hoặc đi qua dữ liệu ngoài scope. Hãy giới hạn commands/keys được phép.

### 28.5. Redis là cache hay source?

Nếu Redis chỉ là cache, lỗi injection có thể rò dữ liệu cached; nếu Redis là nguồn có thẩm quyền, thao tác delete/update trái phép ảnh hưởng state chính. Phân loại data role khi đánh giá tác động.

## 29. Tại sao blacklist ký tự không đủ?

Một số cách vá sai:

~~~text
Reject requests containing "$"
Remove quotes from text
Replace "[" and "]"
Escape every brace
Delete keys starting with "$"
~~~

### 29.1. Blacklist thiếu ngữ cảnh

`$` có thể là ký tự hợp lệ trong tên sản phẩm và là operator prefix trong BSON object. Không thể đánh giá chỉ dựa trên một ký tự tách khỏi nơi nó được dùng.

### 29.2. Encoding/decoding nhiều tầng

URL percent decoding, JSON escaping, Unicode normalization và framework parsing có thể tạo những biểu diễn khác nhau cho cùng ý định. Blacklist đặt ở tầng này có thể bị bypass ở tầng khác.

### 29.3. Toán tử không chỉ là `$`

CQL/Cypher/SQL++ dùng các cú pháp khác, script có grammar riêng, và dynamic field name không cần ký hiệu đặc biệt. Blacklist tập trung MongoDB `$` bỏ sót các nhóm còn lại.

### 29.4. Nếu cần reject operator-looking objects

Đúng cách là **không nhận raw object tại vị trí chỉ được phép String/enum**, hoặc parse vào DSL grammar rõ ràng. Scan recursively cho `$` trong Map chỉ nên là defense in depth, không thay xây AST tin cậy.

## 30. Regex, sort, range query và sự cố từ truy vấn tốn kém

NoSQL injection đôi khi không rò rỉ dữ liệu mà gây **query-based denial of service**:

- Regex không được giới hạn trên field lớn.
- Nhiều `$or`/`$in` terms tạo planning/execution cost.
- Deep aggregation stages hoặc lookup chains.
- Full table Scan khi thiếu partition key.
- Deep offset pagination hoặc sort không index.
- Query có `limit` lớn gây response/GC pressure.

### 30.1. Bảo vệ bằng complexity limits

Đặt max depth, max terms, max selected fields, max page size, allowed filter combinations và query timeout theo use case.

### 30.2. Bảo vệ bằng query plans/index

Một query syntax an toàn vẫn có thể scan quá nhiều dữ liệu. Cần đo read units, docs scanned/result, RU/RCU, execution time, per-tenant quotas.

### 30.3. Rate limits và concurrency

Giới hạn số truy vấn tốn kém đang chạy đồng thời; tránh cho một user chiếm hết connection pool/shard bandwidth.

### 30.4. Không trả lỗi nội bộ quá chi tiết

Error có stack traces, query plan, index names hoặc raw database response có thể lộ internals. Trả error có mã ổn định; log chi tiết có kiểm soát.

### 30.5. Theo dõi resource abuse

Audit số requests sai schema, timeouts theo query shape và high-cost queries; không lưu full payload chứa credentials/PII khi chưa có policy.

## 31. Authz ở nhiều tầng: giảm tác động khi query sai

### 31.1. Phía HTTP/API

Xác thực principal, kiểm quyền endpoint, kiểm tenant/owner, schema validation và rate limit.

### 31.2. Phía application service

Xây query AST từ trusted code, deny-by-default cho fields/operations và gắn invariant `tenantId = principalTenant`.

### 31.3. Phía database

Tài khoản ứng dụng chỉ có read/write cần thiết trên collections/tables/indexes thích hợp; không dùng superuser/admin cho public API.

### 31.4. Phía network

Không mở database trực tiếp ra Internet, dùng TLS, authenticated connections, network restrictions và secret rotation.

### 31.5. Phía response

Ánh xạ sang response DTO, loại private fields, áp field-level authorization. Một query lọc đúng record nhưng trả nhầm sensitive property vẫn gây lộ dữ liệu.

## 32. Multi-tenant security: lỗi logic vẫn có thể xảy ra dù đã bind value

Giả sử API sử dụng prepared query với client-supplied tenant:

~~~text
SELECT * FROM orders
WHERE tenantId = @tenant
~~~

`@tenant` được parameterize an toàn, nhưng **nếu giá trị do client tự chọn**, người dùng vẫn có thể yêu cầu dữ liệu của tenant khác. Đây là lỗi authorization chứ không nhất thiết là injection cú pháp.

### 32.1. Từ principal đến repository

Server nên lấy tenant/role từ verified identity và gắn vào repository call; client có thể gửi tenant selector **chỉ** khi principal được phép truy cập tập tenants đó.

### 32.2. Cấp quyền theo record và operation

Đọc Order và update Order có quyền khác nhau. Query `Filter.eq("tenantId", tenant)` không cho phép user sửa `billingStatus`.

### 32.3. Shared collection vs per-tenant collection

Nếu dùng shared collection, mọi query cần tenant/owner constraints. Nếu per-tenant collection, mapping tên collection từ trusted config; không đưa raw user tenantId thành database identifier.

### 32.4. Service account quá rộng

Một injection có thể rò nhiều tenants nếu ứng dụng DB credentials có quyền toàn cluster. Least privilege, row/partition controls nếu được hỗ trợ và tenant isolation architecture giảm blast radius.

### 32.5. Test unauthorized-but-valid values

Một UUID hợp lệ thuộc tenant khác phải bị từ chối. Test chỉ payload chứa `$ne` sẽ không bắt lỗi IDOR/BOLA và sai phạm vi quyền.

## 33. Bảo vệ các lệnh ghi và bulk operations

Các endpoint như `bulkUpdate`, `deleteMany`, `findAndModify`, `upsert` có tác động lớn nếu predicate/fields do client điều khiển.

### 33.1. Tránh dùng raw `deleteMany(filterJson)` từ API

Client có thể làm filter quá rộng. Với public API xóa một entity, nhận ID hợp lệ, gắn tenant/owner trong filter và yêu cầu appropriate authorization.

### 33.2. `upsert` có thể tạo record ngoài ý định

Nếu filter/update được dựng từ raw input, một upsert có thể tạo document với fields không được phép. Dùng canonical key, server-owned defaults, validated patch và unique constraints.

### 33.3. Bulk input giới hạn

Limit batch size, số items, total bytes, transaction scope và retry semantics. Một JSON array hàng triệu elements là resource issue dù không có injection operators.

### 33.4. Audit immutable business actions

Với thay đổi quyền/quota/payment, ghi event/receipt/commandId ở source có thẩm quyền. Không chỉ tin vào logs của request handler.

### 33.5. Unknown commit after timeout

Một delete/update đã commit có thể mất ACK. Retry mù có thể tạo side effects mới; dùng stable commandId, version guards hoặc idempotent operations theo contract.

## 34. Validation và query builder trong Spring Controller

Ví dụ conceptual Spring MVC:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/products")
public class ProductController {
    private final ProductApplicationService service;

    public ProductController(ProductApplicationService service) {
        this.service = service;
    }

    @PostMapping("/search")
    public ResponseEntity<?> search(
            @RequestBody ProductSearchRequest input) {
        // Resolve trusted tenant from authenticated principal
        // inside service/security adapter, not from request body.
        return ResponseEntity.ok(service.search(input));
    }
}
~~~

`ProductApplicationService` là component do project định nghĩa. Ví dụ chỉ minh họa boundary; thực tế cần authentication, `@Valid`/validation, error mapping, request-size limit và permission checks.

### 34.1. Application service giữ business semantics

Controller không nên truyền `input` sang `MongoCollection.find(Document.parse(...))`. Service/repository chuyển DTO thành query AST cố định.

### 34.2. Không tin `@RequestBody` tự validate

Spring tự deserialize nhưng các annotation hoặc policy kiểu/dải giá trị phải được kích hoạt và áp dụng. DTO record không tự validate length/range.

### 34.3. Global exception mapping

Sai kiểu hoặc unsupported filter nên trả 400/422 theo API contract, không 500 với stack trace, và không thử fallback sang raw query.

### 34.4. Test controller đến repository boundary

Chứng minh malicious object bị reject **trước** khi driver nhận request; và query thực luôn chứa trusted tenant predicate.

## 35. Khi nào một DSL filter tùy chỉnh là hợp lý?

Đôi khi sản phẩm cần advanced search:

~~~json
{
  "and": [
    {"field": "status", "op": "eq", "value": "ACTIVE"},
    {"field": "priceMinor", "op": "gte", "value": 1000}
  ]
}
~~~

Đây không phải MongoDB raw BSON. Nó là **domain filter DSL** mà server kiểm schema, depth và field/operator permissions.

### 35.1. Schema của DSL

`field` lấy từ enum `STATUS`, `PRICE`; `op` lấy từ enum `EQ`, `GTE` với relation cho từng field; value có type tương ứng. Không cho arbitrary `$where` hoặc nested vendor AST.

### 35.2. Biên dịch có kiểm soát

Server chuyển `(field=PRICE,op=GTE,value=1000)` thành `Filters.gte("priceMinor",1000L)`; không viết raw string query.

### 35.3. Luôn thêm tenant predicate bên ngoài

Ngay cả nếu DSL hỗ trợ `OR`, server bọc tenant filter bằng `AND`:

~~~text
SERVER_SCOPE AND (VALIDATED_USER_DSL)
~~~

Không bao giờ cho DSL của user chọn hoặc phủ định security predicate.

### 35.4. Complexity và budget

Giới hạn depth ≤ 3, terms ≤ 20, list values ≤ 50, limit ≤ 100 trong một ví dụ policy; ngưỡng thực phải dựa workload, không có giá trị chung.

### 35.5. Versioning

Saved filter DSL cần `schemaVersion` để migration khi business fields thay đổi; không lưu raw Mongo pipeline không có hợp đồng.

## 36. Validation theo field và vai trò

| Field/request | Kiểu/giới hạn | Quyền |
|---|---|---|
| `status` | Enum `ACTIVE/ARCHIVED` | Tìm kiếm công khai trong tenant |
| `minPriceMinor` | Integer ≥0 | Read filter |
| `sortBy` | Enum `CREATED/PRICE` | Tìm kiếm |
| `limit` | 1..100 | Read pagination |
| `displayName` | String length bounded | User sửa chính mình |
| `role` | Không có trong public patch | Admin-controlled workflow |
| `tenantId` | Trusted principal context | Không từ request body |
| `balance` | Không có trong public patch | Ledger authority |
| `version` | Expected condition từ client có validate | Source CAS quyết định |
| `filterDsl` | Typed and bounded grammar | Chỉ role được cấp tính năng |

### 36.1. Quyền và validation riêng biệt

Một role `"ADMIN"` là chuỗi hợp lệ nhưng user thường không được phép tự gán. Kiểm enum không thay security authorization.

### 36.2. Type coercion

Tránh implicit convert object/array thành string “cho tiện”. Nếu endpoint mong scalar, reject nested structure.

### 36.3. Unicode/canonicalization

Chuẩn hóa theo business rule nhất quán, nhất là username/keys/paths. Không dùng normalization làm cớ bỏ prepared parameters.

### 36.4. Numeric overflow

Các toán tử `gt/lt`, pagination offsets, price values có thể overflow nếu parse sai; dùng bounded numeric types và validate trước khi đưa xuống database.

## 37. Tình huống 1: tra cứu account bằng raw JSON

Một API nhận:

~~~json
{
  "email": "alice@example.test"
}
~~~

Backend dùng `Map<String,Object>` rồi gắn trực tiếp `email` vào Mongo predicate.

### 37.1. Dấu hiệu

Các requests đôi lúc được parse thành `Map` thay vì string; query matcher trả nhiều accounts trong khi service dự kiến exact email.

### 37.2. Nguyên nhân

Không có type boundary, raw object mang operator được đưa vào query engine.

### 37.3. Fix

Strict DTO `email: String`, type/length validation, fixed `Filters.eq("emailNormalized", email)`, tenant/authorization checks và password hash verification ở flow đăng nhập.

### 37.4. Test

Input string hợp lệ match đúng một account; input object/array bị trả 4xx; endpoint không trả account khi credentials không hợp lệ.

### 37.5. Không kết luận bằng “lọc `$`”

Giữ boundary data vs expression và query builder server-side; blacklist một ký tự vừa thiếu vừa có thể phá dữ liệu hợp lệ.

## 38. Tình huống 2: API report có filter JSON tự do

Một ứng dụng cho users lưu `filterJson` để dashboard truy cập MongoDB, rồi chạy job định kỳ bằng service account có quyền đọc nhiều collections.

### 38.1. Rủi ro

Saved JSON có thể yêu cầu operator/collection join/filter rộng hơn quyền user; job chạy về sau, dưới credentials mạnh hơn. Đây là một dạng **second-order injection**.

### 38.2. Điều tra

Truy xuất nguồn filter, schema validation ở thời điểm lưu/chạy, effective principal/tenant, query shape và data đã xuất trong reports.

### 38.3. Fix

Versioned allowlisted DSL, validate lại khi chạy, execute-as-user/tenant-scope, read-only narrow database principal, complexity limits và audit.

### 38.4. Không chỉ đổi endpoint input

Nếu lịch sử DB đã chứa saved raw filters, cần migration/quarantine chúng; nếu không, scheduler vẫn có thể tiếp tục thực thi lệnh cũ.

### 38.5. Đo tác động

Audit data access theo tenant, kết quả đã xuất, query costs và duration; không log nguyên các private report payloads.

## 39. Tình huống 3: sort field và xóa dữ liệu chéo tenant

Một public API cho client chọn `sortBy` tự do và `deleteMany` bằng filter do UI gửi. Đây là hai ranh giới nguy hiểm khác nhau.

### 39.1. Sort nguy hiểm vì hiệu năng và thông tin

Cho chọn field không indexed có thể tạo sort tốn memory. Nếu projection cho phép arbitrary internal fields, có thể rò metadata.

### 39.2. Delete nguy hiểm vì phạm vi

Một filter client sai hoặc quá rộng có thể xóa hàng loạt records nếu DB credentials cho phép. Tên “NoSQL” không làm câu lệnh xóa nhẹ hơn.

### 39.3. Fix

Map `sortBy` enum sang 2–3 indexed paths; endpoint delete nhận entity ID cụ thể, gắn trusted tenant/owner/version predicate; phân quyền và audit.

### 39.4. Khi cần bulk delete

Đặt workflow riêng có review/preview, bounded selection, approval khi cần, commandId, dry-run report và durable audit, không expose unrestricted filter.

## 40. Tình huống 4: tenant isolation với một điều kiện OR sai

Service lắp tenant condition bằng:

~~~text
tenantIsCurrentUser OR (clientFilter)
~~~

thay vì:

~~~text
tenantIsCurrentUser AND (validatedClientFilter)
~~~

### 40.1. Đây là lỗi logic kể cả khi mọi value được parameterize

Operator `OR` do code server tạo sai có thể làm dữ liệu tenant khác xuất hiện, không cần input chứa `$ne` hay escaping.

### 40.2. Kỹ thuật phòng vệ

Tạo một repository method luôn ép security scope và nhận domain fields cụ thể. Không đưa raw AST mà caller có thể thay security predicate.

### 40.3. Test cross-tenant

Với cùng `status=ACTIVE`, seed Product của tenants A/B; request principal A phải không thấy B. Thử OR, empty filters và bypass flags do client giả mạo.

### 40.4. Least privilege

Giảm blast radius nếu DB role/partition access có thể giới hạn; application authz vẫn phải đúng.

## 41. Kiểm thử tự động chống NoSQL injection

Tạo test dataset **cô lập**, không dùng account thật:

~~~text
tenant-A: alice@example.test (ACTIVE)
tenant-A: bob@example.test   (ARCHIVED)
tenant-B: carol@example.test (ACTIVE)
~~~

Nhóm test:

| Tình huống | Kỳ vọng |
|---|---|
| Email string hợp lệ | Equality đúng record trong tenant |
| Email là JSON object | 400/422 trước DB query |
| Email là array/number/null trái contract | Bị reject |
| Status object có key `$ne` | Bị reject, không trở thành operator |
| Field `sortBy` không thuộc allowlist | Bị reject |
| Update chứa `role` ngoài DTO | Bị reject, source không đổi |
| TenantId giả trong JSON | Không thay authenticated tenant scope |
| Duplicate URL query params | Được xử lý theo hợp đồng rõ |
| Raw filter/pipeline được gửi | Endpoint không chấp nhận |
| Limit rất lớn/deep nested filter | Bị giới hạn, không tạo query nặng |
| Query hợp lệ nhưng tenant khác | Không trả dữ liệu |
| Source timeout | Không chuyển thành “not found” hoặc bỏ authz |

### 41.1. Test ở đúng boundary

Unit test DTO validation là cần nhưng chưa đủ. Integration test cần chứng minh repository/broker/database **không nhận** raw operators từ untrusted input.

### 41.2. Test cả authentication và authorization

Từ chối filter object injection chưa chứng minh user không truy cập ID của tenant khác. Bổ sung kiểm owner/tenant/role và field projection.

### 41.3. Test cả read và write

Các path delete/update/bulk/upsert thường nghiêm trọng hơn read-only search. Kiểm thay đổi audit, version và sensitive fields.

### 41.4. Test tài nguyên

Advanced search DSL nên có tests cho depth, term count, page size và expensive query limits, không chỉ kiểm cú pháp.

### 41.5. Test khi schema thay đổi

Khi thêm field `billingStatus` hoặc `isAdmin`, bảo đảm public DTO/allowlist không tự mở quyền search/update field mới.

## 42. Ví dụ JUnit: reject object thay vì query

Một kiểm thử minh họa Jackson strict DTO:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

final class ProductSearchDeserializationTest {
    private final ObjectMapper mapper = new ObjectMapper()
        .configure(
            DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES,
            true
        );

    @Test
    void rejectsOperatorObjectForStatusEnum() {
        String json = """
            {
              "status": {"$ne": "ARCHIVED"},
              "limit": 10
            }
            """;

        assertThrows(
            com.fasterxml.jackson.core.JsonProcessingException.class,
            () -> mapper.readValue(
                json, ProductSearchRequest.class
            )
        );
    }

    @Test
    void acceptsTypedStatus() throws Exception {
        String json = """
            {
              "status": "ACTIVE",
              "limit": 10
            }
            """;

        ProductSearchRequest req = mapper.readValue(
            json, ProductSearchRequest.class
        );
        assertEquals(ProductStatus.ACTIVE, req.status());
    }
}
~~~

### 42.1. Nội dung test

Mục tiêu là chứng minh JSON object không thể được dùng như enum value. Đây là test **typing boundary**, chưa kiểm database authorization hay filter lắp đúng.

### 42.2. Integration test cần mock/inspect query

Gửi request với tenant A, assert filter thực chứa `tenantId=A`, không chứa raw `$or/$ne` từ request và response không có tenant B. Có thể dùng container/staging database cô lập.

### 42.3. Không chỉ test pattern được biết trước

Property-based/fuzz testing với types khác nhau, nested objects, duplicate fields và Unicode giúp tìm parser/canonicalization differences.

### 42.4. Không tự triển khai scanner vào production traffic

Automated security tests nên chạy trong môi trường có quyền và dữ liệu giả; tránh gây side effects/cost khi chủ động gửi filter phức tạp.

## 43. Logging, monitoring và incident response

### 43.1. Dấu hiệu đáng chú ý

- Nhiều 400 do expected String nhưng nhận object/array.
- Input có trường không thuộc allowlist hoặc nested filter rất sâu.
- Query cost/scanned records tăng bất thường.
- Bulk updates/deletes từ public role không phù hợp.
- Cross-tenant access attempts, 403/404 patterns và API rate spikes.
- Database user có quyền ngoài nhu cầu ứng dụng.

### 43.2. Log có cấu trúc

Ghi requestId, principal ID dạng đã kiểm soát, endpoint, validation category, auth outcome, query shape ID, duration và cost. Tránh log password, tokens, complete JSON body hoặc raw documents nhạy cảm.

### 43.3. Query shape identifiers

Thay log raw query có PII, định danh query template (`product_search_v2`) và loại predicate. Khi phải điều tra raw query, chỉ thu qua quy trình có quyền/redaction.

### 43.4. Nếu phát hiện nghi vấn khai thác

Giới hạn/disable endpoint hoặc feature, thu thập bằng chứng theo policy, rotate credentials nếu cần, kiểm audit data accessed/changed, soát quyền DB và sửa boundary. Không tự xóa logs có giá trị điều tra.

### 43.5. Sửa từ nguồn dữ liệu đã lưu

Nếu có saved filters/jobs cũ, quarantine/migrate dữ liệu ấy. Vá controller mà bỏ scheduler có thể chưa xử lý second-order injection.

## 44. Phương pháp review code tìm NoSQL injection

Tìm các luồng **source → transform → sink**:

~~~text
SOURCE:
    HTTP body / query params / headers / saved JSON / queue
    |
    v
TRANSFORM:
    Map<String,Object>, JsonNode, Document.parse,
    string interpolation, dynamic field name,
    generic query/update DTO
    |
    v
SINK:
    collection.find/update/delete/aggregate,
    CQL/SQL++/Cypher string, DynamoDB expressions,
    search JSON DSL, Redis script/eval
~~~

### 44.1. Câu hỏi cho reviewer

Ở mỗi sink, phần nào do server kiểm soát, phần nào đến từ client? Có input nào được đặt ở vị trí **operator, identifier, expression, statement hoặc script** không?

### 44.2. Các dấu hiệu trong Java

`Document.parse(request...)`, `new Document(requestMap)`, `updateOne(filter, rawUpdate)`, `String.format(query, input)`, dynamic `.and(field)`, `.sort(userField)` và tự dựng JSON query string là nơi cần xem kỹ.

### 44.3. Không kết án mọi raw string

Một chuỗi URL hay tên product có chứa `$` không phải lỗ hổng nếu nó được bind như value literal. Review phải hiểu dataflow, not just grep ký tự.

### 44.4. Review dependency/version

Driver, ODM, framework query binding và database features có thể thay đổi semantics; cần theo dõi security advisories, supported versions và config. Không tự suy framework an toàn trong mọi escape hatch.

### 44.5. Negative security tests

Mỗi endpoint filter/update có tests cho invalid types, unknown fields, cross-tenant access, forbidden paths và resource limits.

## 45. Checklist thiết kế API NoSQL an toàn

1. **Không nhận raw DB query** từ public user trừ khi có sandbox/query language được thiết kế riêng.
2. **Không nối string input** vào CQL, SQL++, Cypher, Cosmos SQL hay script source.
3. **Dùng prepared/bound parameters** cho values trong string-based query languages.
4. **Dùng SDK typed query builders** cho filter/update structures.
5. **Không chuyển raw JSON/Map/JsonNode** thành MongoDB filter hay update document.
6. **DTO có kiểu cụ thể** cho string/enum/numeric/filter fields.
7. **Reject invalid types**, đặc biệt object/array tại scalar fields.
8. **Có chính sách unknown fields** và không fallback raw JSON.
9. **Operator được server chọn**, không từ key `$...` do client gửi.
10. **Field names và paths được allowlist**, kể cả sort/projection/update.
11. **Tenant/owner filter từ principal**, không từ client-provided tenant.
12. **Authorization ở mức object/field/operation** chứ không chỉ route.
13. **Không dùng login query với plaintext password**; dùng password hashing verification.
14. **Chỉ trả response DTO** gồm fields được phép.
15. **Limit query complexity**, depth, terms, page size, result bytes và timeout.
16. **Validate numeric ranges** để tránh unbounded scan hoặc overflow.
17. **Giới hạn expensive regex/scripts/aggregations** theo use case.
18. **DB principal có least privilege**, không dùng admin cho public API.
19. **Network access/TLS/credential management** theo security policy.
20. **Kiểm raw query escape hatches** của ORM/ODM.
21. **Kiểm update/delete/bulk paths** riêng với reads.
22. **Bảo vệ idempotency/CAS** cho writes nghiệp vụ.
23. **Test multi-tenancy**, bao gồm IDs hợp lệ của tenant khác.
24. **Test injection-like typed inputs** và assertions trước database.
25. **Theo dõi query shape/cost và validation failures** mà không log secrets.
26. **Rà soát saved filters/jobs** chống second-order injection.
27. **Kiểm SDK/DB versions** khi dùng query/script features.
28. **Có runbook xử lý nghi vấn khai thác** và audit trail phù hợp.

### 45.1. Mẫu contract review cho endpoint tìm kiếm

~~~yaml
endpoint: POST /api/products/search

authentication:
  required: true
  tenantSource: "verified principal / authorized tenancy"

requestSchema:
  status: "enum ACTIVE|ARCHIVED"
  minPriceMinor: "integer 0..10000000000"
  maxPriceMinor: "integer 0..10000000000"
  sortBy: "enum CREATED|PRICE"
  limit: "integer 1..100"
  unknownFields: "reject"
  rawFilterJsonAccepted: false

queryConstruction:
  trustedPredicate: "tenantId = principal.tenantId"
  allowedOperators: ["eq", "gte", "lte"]
  allowedSortFields: ["createdAt", "priceMinor"]
  typedDriverBuilder: true
  maxExecutionTime: "<measured policy>"

authorization:
  objectScope: "current tenant"
  responseProjection: "public product fields only"
  databaseRole: "read-only required collection(s)"

testing:
  rejectsObjectInScalarField: required
  rejectsUnknownOperators: required
  rejectsForbiddenFieldNames: required
  preservesTenantIsolation: required
  limitsQueryCost: required
~~~

Mẫu này là tài liệu thiết kế, không phải một file cấu hình bảo mật tự có hiệu lực. Những placeholder cần được triển khai và kiểm chứng trong stack cụ thể.

## 46. Bài tập thực hành

### Bài 1 — Nhận diện ranh giới

Giải thích điểm khác giữa `status = "ACTIVE"` dưới dạng literal value và `{"status":{"$ne":"ARCHIVED"}}` dưới dạng MongoDB predicate. Nguy cơ xuất hiện ở bước nào?

### Bài 2 — Chuỗi CQL

Một DAO nối `email` của người dùng vào CQL string. Viết lại bằng PreparedStatement và bound value, giải thích giới hạn parameterization đối với tên table/column.

### Bài 3 — Raw JSON filter

Một API nhận `{filterJson:"..."}` rồi `Document.parse()` và `collection.find`. Thiết kế DTO/filter builder thay thế.

### Bài 4 — Scalar type

`email` trong request vốn là String nhưng client gửi object hoặc array. Nêu HTTP response policy và test để đảm bảo không truy vấn database.

### Bài 5 — Operator allowlist

Xây DSL chỉ hỗ trợ `status eq`, `price gte/lte` và tối đa ba điều kiện AND. Vì sao không nên nhận mọi toán tử MongoDB?

### Bài 6 — Login

Một endpoint truy vấn bằng `{username: rawBody.username, password: rawBody.password}`. Liệt kê ít nhất bốn sai sót và thiết kế authentication flow phù hợp.

### Bài 7 — Tenant bypass

Một predicate dùng `tenant==A OR status==ACTIVE`. Chứng minh logic có thể trả Product của B và chuyển thành server-enforced AND với filter client đã validate.

### Bài 8 — Trusted context

Client gửi tenantId `T2` nhưng token chỉ có quyền ở `T1`. Kể cả parameterization đúng, kết quả phải thế nào? Thử nghiệm BOLA/IDOR ra sao?

### Bài 9 — Update operator

API đổi `displayName` nhận raw JSON update. Đề xuất endpoint patch DTO và allowlisted `Updates.set` cùng protection cho `role`.

### Bài 10 — Dynamic field

App gọi `Updates.set(request.field, request.value)`. Vì sao typed SDK builder chưa đủ? Viết mapping enum field name sang DB path.

### Bài 11 — Sort field

Client chọn raw `sortBy`. Xây allowlist `CREATED/PRICE`, thêm bound limit và indexed access plan.

### Bài 12 — Projection

API cho user chọn arbitrary fields trong response. Thiết kế response DTO không lộ `passwordHash`, `resetToken`, `internalNotes`.

### Bài 13 — URL nested parameters

Framework có thể parse `status[$ne]=X` thành object. Kiểm schema nào sẽ reject và vì sao behavior phụ thuộc parser configuration?

### Bài 14 — Duplicate query params

Request chứa hai tham số `status`. Định nghĩa single-value contract, first/last/list handling và cách tránh parser differential.

### Bài 15 — Regex

Một tìm kiếm text nhận regex raw dài 1.000 ký tự. Đề xuất literal matching/escaping, max length, query timeout và search index thay thế.

### Bài 16 — Aggregation

Một analytics endpoint cho user gửi raw pipeline. Thiết kế DSL dimensions/measures và giới hạn stages, memory, concurrency và collections.

### Bài 17 — `$where` và script

Giải thích tại sao không cho user gửi source script vào database; đề xuất typed expression operators hoặc sandbox có quyền hạn.

### Bài 18 — Jackson

Tạo `ProductSearchRequest` có enum status và `limit`; cấu hình Jackson reject unknown fields; viết test input object trong `status` bị lỗi deserialization.

### Bài 19 — Spring Data

Viết MongoTemplate Query có tenant equality cố định, status enum và sort whitelist. Những rủi ro nào còn lại ngoài injection?

### Bài 20 — DynamoDB

Dùng ExpressionAttributeValues cho tenant key; giải thích vì sao dynamic attribute name vẫn phải allowlist và Scan+FilterExpression có thể đắt.

### Bài 21 — Cosmos DB

Viết SqlQuerySpec với `@tenant` và `@status`; phân biệt value placeholder với dynamic `c.field` identifier.

### Bài 22 — Couchbase SQL++

Một query SQL++ có `status` nối trực tiếp; chuyển sang named parameter và giữ bucket/scope/collection names server-owned.

### Bài 23 — Neo4j Cypher

Viết Cypher có `$tenantId` và `$orderId`; giải thích vì sao dynamic relationship type/path length vẫn cần hạn chế.

### Bài 24 — Elasticsearch DSL

Một endpoint nhận raw query JSON với arbitrary scripts/wildcards. Thiết kế search DTO và query cost budget an toàn hơn.

### Bài 25 — Redis Lua

Một app ghép user text thành Lua script. Vì sao nguy hiểm? Phân biệt script cố định truyền KEYS/ARGV với quyền truy cập key namespace.

### Bài 26 — Second-order injection

User lưu filter JSON, scheduler chạy lại sau một tuần dưới admin DB role. Chỉ ra trust boundary và kế hoạch migrate/quarantine saved filters.

### Bài 27 — Query DoS

Một filter hợp lệ trả hàng triệu records, p99 và CPU tăng. Xác định complexity/rate/page/timeout guardrails.

### Bài 28 — Authz vs injection

API dùng parameterized query nhưng client tự điền tenantId của người khác. Đây là injection hay authorization failure? Cần những lớp bảo vệ nào?

### Bài 29 — Bulk delete

Một public API nhận raw filter cho `deleteMany`. Thiết kế flow delete by ID, scoped tenant, audit, version guard và bulk-delete riêng nếu cần.

### Bài 30 — Negative tests

Viết test matrix gồm string hợp lệ, object `$ne`, nested `$or`, array, null, unknown field, unauthorized tenant và large limit; mô tả expected outcomes.

### Bài 31 — Incident response

Log cho thấy nhiều object-in-string validation failures, query cost tăng và lệnh đọc ngoài tenant. Lập kế hoạch containment, audit và fix mà không log secrets.

### Bài 32 — Threat modeling

Vẽ dataflow controller → DTO → service → repository → DB; đánh dấu ranh giới tin cậy và quyền kiểm soát operator/field/value ở mỗi bước.

### Bài 33 — Review code

Cho năm đoạn: `Filters.eq` với String; `Document.parse(rawBody)`; `String.format(CQL,input)`; `Updates.set(rawField,val)`; `SqlQuerySpec` với bound parameters. Xếp hạng rủi ro và đưa điều kiện để xác nhận an toàn.

### Bài 34 — Multi-tenant integration test

Seed hai tenants có cùng productId/status, gọi search/lookup theo principal T1; assert không bao giờ trả bản ghi T2, kể cả input cố yêu cầu tenant khác.

### Bài 35 — Thiết kế hoàn chỉnh

Thiết kế `POST /products/search` và `PATCH /products/{id}` trong Java/MongoDB: DTO, validation, server-owned AST, tenant/field authz, giới hạn chi phí, concurrency controls, JUnit tests và metrics không rò PII.

---

**Kết luận:** **NoSQL injection** xuất hiện khi dữ liệu không tin cậy được nâng thành **cú pháp truy vấn hoặc lệnh cập nhật**: nối chuỗi CQL/SQL++/Cypher, chuyển raw JSON/Map thành BSON filter, hoặc để client chọn `$` operators, field paths, aggregation stages và scripts. Chỉ parse JSON hợp lệ, dùng một ORM/ODM, hay cấm vài ký tự đặc biệt **không đủ** để bảo vệ. Trong Java, hãy **định nghĩa DTO có kiểu, xác thực enum/range/size, xây query bằng trusted SDK builders hoặc prepared parameters, allowlist mọi field/operator có thể tùy biến**, gắn tenant/owner scope từ principal đã xác thực và dùng database credentials có quyền tối thiểu. Bổ sung giới hạn chi phí truy vấn, tests cho invalid types/cross-tenant operations, monitoring/audit và quy trình xử lý saved filters. Mục tiêu là giữ **ranh giới dữ liệu–cấu trúc truy vấn–quyền truy cập** rõ ràng trong mọi đường đọc, ghi và xử lý nền.
