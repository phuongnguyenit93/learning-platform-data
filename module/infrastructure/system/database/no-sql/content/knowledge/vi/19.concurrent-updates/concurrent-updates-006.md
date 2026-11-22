# Cạnh tranh khi tạo bản ghi có khóa duy nhất

## 1. Vấn đề: hai yêu cầu cùng muốn tạo một bản ghi “chưa tồn tại”

Một ứng dụng quản lý người dùng đặt quy tắc:

> Trong cùng một tổ chức (tenant), không được có hai tài khoản đang hoạt động sử dụng cùng một địa chỉ email chuẩn hóa.

Hãy xét hai request đăng ký tới cùng lúc:

~~~text
Request A: tenant=T17, email=an@example.com, userId=U101
Request B: tenant=T17, email=an@example.com, userId=U202
~~~

Một đoạn code trông hợp lý:

~~~java
if (repository.findByTenantAndEmail(tenantId, email) == null) {
    repository.insert(newUser);
    return CREATED;
}
return EMAIL_ALREADY_EXISTS;
~~~

Nhưng khi hai request chạy đồng thời:

~~~text
Thời gian    Request A                         Request B
---------------------------------------------------------------------------
t1           SELECT email -> không có
t2                                             SELECT email -> không có
t3           INSERT user U101
t4                                             INSERT user U202
t5           Trả CREATED
t6                                             Trả CREATED
~~~

Nếu cơ sở dữ liệu không thực thi ràng buộc duy nhất tại thời điểm ghi, **cả hai bản ghi có thể được tạo**, phá vỡ quy tắc. Đó là **race condition khi tạo bản ghi có khóa duy nhất**, một dạng điển hình của lỗi *time-of-check to time-of-use* (**TOCTOU**).

Bài học thuộc chương **Cập nhật đồng thời** trong module **Database No SQL**, với trọng tâm không chỉ là phát hiện “đã có email” mà còn là **bảo vệ một bất biến (invariant) khi nhiều tiến trình, replica hoặc Region cùng ghi**.

Sau bài, bạn sẽ hiểu:

1. Vì sao đọc trước rồi ghi sau không bảo đảm tính duy nhất.
2. Khác biệt giữa **primary key**, **unique business key**, **conditional insert**, **unique index**, **transaction** và **distributed lock**.
3. Cách MongoDB, DynamoDB, Cassandra/ScyllaDB, Redis và Elasticsearch/OpenSearch xử lý những trường hợp liên quan.
4. Cách giữ tính duy nhất theo tenant, theo trạng thái ACTIVE, hoặc theo nhiều field.
5. Cách phân biệt xung đột thật với retry của chính request đã thành công.
6. Những vấn đề khi cập nhật/chuyển chủ sở hữu khóa duy nhất, xóa, TTL và nhiều Region.
7. Cách kiểm thử hai writer tranh chấp và quan sát lỗi trong production.

**Quy ước:** Các ví dụ dùng email/username để dễ hiểu, nhưng nguyên lý áp dụng cho mã đơn hàng, mã đặt chỗ, số serial thiết bị, externalId, coupon code, tên nhóm trong tenant và các khóa nghiệp vụ khác. Các chi tiết API cần được kiểm tra theo đúng sản phẩm, phiên bản và topology triển khai.

## 2. “Khóa duy nhất” thực sự có nghĩa gì?

### 2.1. Primary key

**Primary key** định danh bản ghi trong một phạm vi được hệ thống xác định:

~~~text
User:
  userId = U101
~~~

Nếu mỗi user có userId riêng, hai user có cùng email vẫn có thể có primary key khác nhau:

~~~text
User U101: email=an@example.com
User U202: email=an@example.com
~~~

Do đó **primary key duy nhất không tự làm những trường nghiệp vụ khác trở nên duy nhất**.

### 2.2. Natural key và business key

**Natural/business key** là field hoặc tổ hợp field có ý nghĩa nghiệp vụ:

- Username trong một tenant.
- Email chuẩn hóa của tài khoản.
- Mã đơn hàng của một cửa hàng.
- External customer ID do một đối tác cấp.
- (tenantId, courseSlug) trong một nền tảng học tập.

Một business key có thể trùng với primary key, nhưng thường không như vậy. Khi business key có thể thay đổi, việc dùng một surrogate ID ổn định làm primary key và giữ cơ chế unique riêng có thể thuận tiện hơn.

### 2.3. Độc nhất toàn hệ hay theo phạm vi?

Hai quy tắc khác hẳn:

**Duy nhất toàn hệ:**

~~~text
emailCanonical phải duy nhất trong mọi tenant.
~~~

**Duy nhất theo tenant:**

~~~text
(tenantId, emailCanonical) phải duy nhất.

T17 + an@example.com: hợp lệ.
T88 + an@example.com: cũng hợp lệ.
T17 + an@example.com lần thứ hai: xung đột.
~~~

Nếu viết sai phạm vi index/khóa, hệ có thể từ chối những bản ghi đáng lẽ hợp lệ, hoặc cho phép trùng những bản ghi đáng lẽ bị cấm.

### 2.4. Duy nhất theo trạng thái

Một số nghiệp vụ chỉ cấm trùng **trong các bản ghi đang hoạt động**:

~~~text
ACTIVE user U101 có username=an.
DELETED user U099 cũng từng có username=an.
~~~

Nếu chính sách cho phép tái sử dụng username sau khi xóa, điều kiện unique phải phản ánh đúng trạng thái sống/chết. Đổi lại, phải xử lý nguy cơ xóa cũ, sự kiện đến muộn và khôi phục bản ghi DELETED.

### 2.5. Unique không chỉ là số lượng bản ghi cuối cùng

Một bất biến mạnh hơn thường bao gồm:

- **Safety:** Không có hai thực thể hợp lệ sở hữu cùng khóa tại cùng một thời điểm.
- **Ownership:** Hệ xác định chính xác ai đang sở hữu khóa.
- **No lost update:** Người đến sau không vô tình ghi đè người đến trước.
- **Idempotency:** Retry cùng yêu cầu không tạo hai thực thể.
- **Recovery:** Worker chết giữa các bước không làm khóa bị mất hoặc bị giữ mãi vô lý.

Chỉ kiểm tra COUNT cuối cùng trong một lần thử đơn luồng chưa chứng minh những thuộc tính này.

## 3. Tại sao kiểm tra trước khi ghi luôn có cửa sổ cạnh tranh?

### 3.1. Read–check–write gồm nhiều bước độc lập

Mô hình nguy hiểm:

~~~text
READ key K -> ABSENT
CHECK business rules
WRITE K
~~~

Giữa READ và WRITE, một client khác có thể ghi K. Cả hai client đều có thông tin đúng tại lúc đọc nhưng quyết định tổng thể lại sai.

Đây không phải lỗi của cú pháp query. Nó là lỗi **không bảo vệ điều kiện “chưa tồn tại” cùng với thao tác tạo**.

### 3.2. Sơ đồ tranh chấp

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant DB as NoSQL
    participant B as Client B
    A->>DB: GET uniqueKey K
    DB-->>A: Không có
    B->>DB: GET uniqueKey K
    DB-->>B: Không có
    A->>DB: INSERT K -> U101
    DB-->>A: Thành công
    B->>DB: INSERT K -> U202
    DB-->>B: Thành công nếu không có atomic uniqueness
    Note over DB: Invariant bị vi phạm
~~~

### 3.3. Strong read vẫn không đủ

Ngay cả khi cả hai GET đều là **strongly consistent read**, hai GET có thể xảy ra **trước** bất kỳ INSERT nào. Kết quả “chưa tồn tại” là chính xác tại thời điểm đọc, nhưng không được giữ cố định tới khi ghi.

**Strong read giảm đọc stale; nó không thay thế một atomic compare-and-set hoặc unique constraint ở thời điểm ghi.**

### 3.4. Một transaction nhưng không có ràng buộc uniqueness?

Không nên nghĩ chỉ cần bọc đoạn:

~~~text
IF NOT EXISTS email THEN INSERT user
~~~

vào một transaction bất kỳ là tự giải quyết. Kết quả còn phụ thuộc mức isolation, cách bảo vệ **predicate không tồn tại**, index và cơ chế phát hiện xung đột.

Ví dụ, hai transaction cùng đọc “không có user thuộc email K” dưới một mức isolation không bảo vệ phantom/predicate có thể đều quyết định ghi **hai document khác ID**. Ràng buộc unique ở storage hoặc cơ chế đặt chỗ khóa duy nhất vẫn cần thiết.

Transaction hữu ích để giữ nhiều thao tác cùng commit; unique index/conditional insert giúp **chỉ một claimant thắng** cho cùng key. Đây là hai trách nhiệm có thể cần phối hợp.

## 4. Mô hình đúng: quyết định thắng–thua phải diễn ra ở điểm ghi có thẩm quyền

### 4.1. Atomic create-if-absent

Một cách diễn đạt:

~~~text
CREATE key K with owner U101
ONLY IF key K DOES NOT EXIST
~~~

Storage engine phải đánh giá điều kiện **cùng một thao tác nguyên tử** với việc tạo bản ghi.

Nếu A và B tranh cùng K, kết quả mong muốn:

~~~text
Client A -> CREATE_IF_ABSENT(K, U101) -> SUCCESS
Client B -> CREATE_IF_ABSENT(K, U202) -> ALREADY_EXISTS
~~~

hoặc ngược lại. **Thứ tự thắng không cần dự đoán trước**, nhưng phải có một người thắng duy nhất theo phạm vi guarantee.

### 4.2. Unique index

Một cơ sở dữ liệu có thể duy trì index với ràng buộc unique:

~~~text
UNIQUE (tenantId, emailCanonical)
~~~

Khi hai insert cùng giá trị, storage kiểm tra sự xung đột khi ghi; một insert được chấp nhận, insert còn lại nhận lỗi duplicate key (giả sử mọi điều kiện khác bình thường).

App có thể đọc trước để trả thông báo thân thiện nhưng **không dùng kết quả đọc trước làm lớp bảo vệ duy nhất**.

### 4.3. Compare-and-set (CAS)

Nếu mỗi key có version hoặc state:

~~~text
SET K = U101 IF K IS ABSENT
~~~

hoặc:

~~~text
SET K = U202 IF version = 7
~~~

CAS bảo vệ quyết định cập nhật dựa trên điều kiện hiện tại theo phạm vi của engine. Nó phù hợp khi cần chỉ một writer giành quyền hoặc ngăn update dựa trên dữ liệu cũ.

### 4.4. Không dùng upsert vô điều kiện

Sai lầm phổ biến:

~~~text
UPSERT userByEmail[K] = newUser
~~~

Nếu cả hai writer đều upsert, người sau có thể **ghi đè** người trước, làm mất ownership hoặc khiến hệ trả thành công cho hai yêu cầu.

**Upsert** chỉ có nghĩa tạo nếu thiếu, cập nhật nếu tồn tại; không đồng nghĩa “chỉ tạo khi thiếu”.

### 4.5. Một khóa duy nhất phải có một điểm quyết định

Nếu các thao tác tạo cùng K được gửi tới nhiều storage/Region độc lập không có cơ chế đồng thuận hoặc uniqueness chung, mỗi nơi có thể tin mình thắng. Muốn có một chủ sở hữu duy nhất trên toàn hệ, phải có **điểm phối hợp/serialize thích hợp** hoặc một mô hình chấp nhận xung đột rồi giải quyết rõ ràng.

## 5. Chuẩn hóa khóa trước khi tranh chấp

### 5.1. “Giống nhau” là một quy tắc nghiệp vụ

Hai chuỗi:

~~~text
An@Example.com
an@example.com
~~~

có được coi là cùng email hay không? Một hệ đăng ký thường mong muốn so khớp theo một quy tắc canonicalization nhất quán.

Tương tự:

~~~text
"alice"
" Alice "
"ALICE"
~~~

Nếu người dùng nhìn chúng là một username nhưng DB xem là ba khóa khác nhau, index unique trên chuỗi gốc **không bảo vệ quy tắc nghiệp vụ**.

### 5.2. Canonicalization

Một pipeline có thể:

1. Kiểm tra dữ liệu đầu vào hợp lệ theo loại identifier.
2. Áp dụng Unicode normalization nếu phù hợp với hợp đồng.
3. Chuẩn hóa chữ hoa/thường theo quy tắc đã chọn.
4. Xử lý khoảng trắng theo quy tắc username, slug hoặc mã nghiệp vụ.
5. Lưu cả bản hiển thị và bản chuẩn hóa.
6. Đặt unique constraint/conditional key trên **giá trị chuẩn hóa**.

Ví dụ:

~~~json
{
  "emailDisplay": "An@Example.com",
  "emailCanonical": "an@example.com"
}
~~~

### 5.3. Không tự áp dụng quy tắc email của một nhà cung cấp cho tất cả

Không nên mặc định bỏ dấu chấm, bỏ phần sau dấu cộng hoặc áp dụng mọi quy tắc dành riêng cho Gmail vào tất cả email. Một địa chỉ email còn có ngữ nghĩa domain/local-part và chính sách sản phẩm; chuẩn hóa quá tay có thể **gộp nhầm hai hộp thư khác nhau**.

Thiết kế cần nêu chính xác “unique theo quy tắc nào” và áp dụng nhất quán ở mọi đường tạo/sửa.

### 5.4. Collation, locale và Unicode

So sánh chuỗi có thể bị ảnh hưởng bởi:

- Case sensitivity.
- Locale.
- Unicode normalization.
- Dấu thanh/dấu phụ.
- Quy tắc so sánh số và chuỗi.

Nếu app chuẩn hóa một cách nhưng unique index dùng collation khác, có thể xuất hiện kết quả không mong muốn. Phải thống nhất chính sách key giữa API, storage và những job import/backfill.

### 5.5. Không đổi quy tắc chuẩn hóa mà không migration

Ví dụ ban đầu username phân biệt chữ hoa/thường, sau đó sản phẩm đổi thành không phân biệt. Hai bản ghi cũ ALICE và alice giờ trở thành xung đột.

Trước khi tạo index unique mới cần:

- Thống kê collision hiện tại.
- Chọn chính sách hợp nhất/đổi tên.
- Migrate dữ liệu.
- Áp dụng ràng buộc mới.
- Đảm bảo không còn writer dùng quy tắc cũ trong thời gian chuyển đổi.

Một unique index có thể **không tạo được** nếu dữ liệu đã tồn tại nhiều khóa trùng theo quy tắc mới.

## 6. Thiết kế khóa duy nhất theo phạm vi tenant

### 6.1. Khóa ghép

Quy tắc:

~~~text
UNIQUE (tenantId, usernameCanonical)
~~~

Cùng username được phép tồn tại ở hai tenant khác nhau.

Với database có compound unique index, sử dụng index ghép. Với key–value store không có unique secondary index tổng quát, có thể mã hóa cặp field thành một khóa định danh:

~~~text
TENANT#T17#USERNAME#alice
TENANT#T88#USERNAME#alice
~~~

**Chú ý:** Nếu dùng chuỗi ghép, cần encoding không mơ hồ. Nếu identifier có thể chứa dấu phân cách, cần escape/length-prefix hoặc cấu trúc key rõ ràng. Tránh collision do ghép chuỗi tùy tiện.

### 6.2. Composite primary key

Nếu PK là (tenantId, emailCanonical), một lệnh create-if-absent trên **đúng cặp khóa đó** có thể bảo vệ tính duy nhất trong tenant.

Nếu PK chỉ là userId ngẫu nhiên và emailCanonical nằm ở attribute thường, conditional insert userId **không ngăn** một request khác với userId khác nhưng email giống nhau.

### 6.3. Quy tắc “chỉ ACTIVE mới unique”

Ví dụ một người xóa tài khoản rồi cho phép đăng ký lại cùng username. Lúc đó unique ownership có vòng đời:

~~~text
ABSENT -> CLAIMED -> ACTIVE -> RELEASED
~~~

Cần bảo vệ cả các transition CLAIM/RELEASE. Nếu sự kiện DELETE cũ tới muộn sau khi username đã cấp cho người mới, một lệnh delete vô điều kiện trên key có thể xóa nhầm quyền sở hữu mới.

### 6.4. Generation hoặc owner token

Một claim có thể chứa:

~~~json
{
  "uniqueKey": "TENANT#T17#USERNAME#alice",
  "ownerUserId": "U101",
  "generation": 12,
  "state": "ACTIVE"
}
~~~

Nếu claimant mới U202 được cấp generation 13, tác vụ cleanup của U101 chỉ được release claim **khi owner=U101 và generation=12**. Đây là mô hình ownership có điều kiện, chống việc một worker cũ xóa nhầm khóa đã tái cấp.

## 7. MongoDB: unique index là công cụ bảo vệ trực tiếp

### 7.1. Tạo compound unique index

Giả sử collection users:

~~~javascript
db.users.createIndex(
  { tenantId: 1, emailCanonical: 1 },
  {
    unique: true,
    name: "ux_tenant_email_canonical"
  }
);
~~~

Index bảo vệ cặp (tenantId, emailCanonical) theo semantics MongoDB, với điều kiện dữ liệu và phạm vi index được định nghĩa phù hợp.

Hai document khác _id nhưng trùng cặp tenant/email không thể cùng tồn tại hợp lệ trong collection với unique index này.

### 7.2. Hai insert cạnh tranh

~~~javascript
db.users.insertOne({
  _id: "U101",
  tenantId: "T17",
  emailCanonical: "an@example.com",
  displayName: "An"
});
~~~

Cùng thời điểm:

~~~javascript
db.users.insertOne({
  _id: "U202",
  tenantId: "T17",
  emailCanonical: "an@example.com",
  displayName: "An khác"
});
~~~

Một insert có thể thành công; insert còn lại nhận lỗi duplicate key, thường với mã **11000 (E11000)**.

Không nên cố dự đoán U101 luôn thắng. Lịch thực thi, contention và failure mode quyết định bên thắng.

### 7.3. Java MongoDB Driver: bắt duplicate key

~~~java
import com.mongodb.ErrorCategory;
import com.mongodb.MongoWriteException;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

public void createUser(
        MongoCollection<Document> users,
        String tenantId,
        String userId,
        String emailCanonical
) {
    Document user = new Document("_id", userId)
            .append("tenantId", tenantId)
            .append("emailCanonical", emailCanonical);

    try {
        users.insertOne(user);
    } catch (MongoWriteException exception) {
        if (exception.getError().getCategory() == ErrorCategory.DUPLICATE_KEY) {
            throw new IllegalStateException(
                    "Unique key is already claimed", exception
            );
        }
        throw exception;
    }
}
~~~

Đây là ví dụ đường xử lý lỗi. Trong ứng dụng thực cần phân biệt **trùng _id** với **trùng emailCanonical**; cùng một loại lỗi duplicate key có thể do những unique index khác nhau gây ra. Nên ánh xạ chính xác loại conflict và có cơ chế idempotency nếu request được retry.

### 7.4. Đọc trước chỉ để cải thiện UX

Có thể kiểm tra trước:

~~~javascript
db.users.findOne({
  tenantId: "T17",
  emailCanonical: "an@example.com"
});
~~~

Điều đó giúp giao diện báo email đã được dùng trong nhiều tình huống, nhưng **unique index mới là lớp chốt** khi hai request cạnh tranh.

### 7.5. Upsert cần được hiểu đúng

~~~javascript
db.users.updateOne(
  {
    tenantId: "T17",
    emailCanonical: "an@example.com"
  },
  {
    $setOnInsert: {
      _id: "U101",
      displayName: "An"
    }
  },
  { upsert: true }
);
~~~

Nếu filter và index được thiết kế phù hợp, upsert có thể hỗ trợ một số tình huống create-if-missing, nhưng:

- Upsert **không mặc định trả conflict** khi bản ghi đã tồn tại.
- Hai upsert tranh chấp có thể gặp duplicate key hoặc hành vi retry tùy tình huống.
- Không có unique index bảo vệ predicate, các upsert đồng thời có thể tạo nhiều document khớp cùng logic nghiệp vụ.
- Một thao tác upsert có thể cập nhật document sẵn có; phải tránh vô tình đổi owner.

Vì vậy, nếu yêu cầu của API là “tạo mới hoặc báo đã tồn tại”, **insertOne dưới unique index** thường dễ diễn đạt hơn upsert tự do.

### 7.6. Partial unique index cho bản ghi ACTIVE

Ví dụ quy tắc: chỉ document **không có deletedAt** được xem là đang hoạt động và cần unique:

~~~javascript
db.users.createIndex(
  { tenantId: 1, emailCanonical: 1 },
  {
    unique: true,
    partialFilterExpression: {
      deletedAt: { $exists: false }
    },
    name: "ux_active_tenant_email"
  }
);
~~~

Khi soft-delete một user bằng cách thêm deletedAt, document có thể rời khỏi tập được index. Điều này cho phép tạo user ACTIVE mới cùng email theo policy.

**Rủi ro cần xem xét:**

1. Khôi phục user cũ có thể bị unique conflict với người mới.
2. Sự kiện xóa đến muộn có thể chạm tới owner không đúng nếu handler chỉ dùng email.
3. Application phải nhất quán về việc thiếu deletedAt khác với deletedAt=null.
4. Mọi đường ghi/import phải tuân thủ cùng điều kiện ACTIVE.

### 7.7. Unique index trong sharded collection

MongoDB có các ràng buộc riêng cho unique indexes trên sharded collections, liên quan shard key và cấu trúc index được hỗ trợ. Không thể lấy kết quả của collection không shard rồi mặc định một unique secondary key bất kỳ được bảo đảm toàn cụm.

Khi triển khai sharding cần xác định:

- Unique key có gắn với shard key theo yêu cầu của MongoDB không?
- Collation và index policy có phù hợp?
- Khóa có được định tuyến tới phạm vi cưỡng chế uniqueness chung?
- Migrations/chunk movement có ảnh hưởng cách vận hành index?

Nếu business key không thể được cưỡng chế toàn cụm bằng index sẵn có, có thể cần thay đổi shard key hoặc thiết kế một nơi quản lý unique claims có quyền quyết định thống nhất.

### 7.8. Multi-document transaction không thay unique index

Một transaction có thể giúp commit đồng thời user và hồ sơ phụ trợ. Nhưng nếu invariant là “email chỉ có một owner”, unique index vẫn là bảo vệ trực tiếp. **Transaction và unique constraint là hai công cụ bổ sung**, không phải lựa chọn loại trừ nhau.

## 8. DynamoDB: conditional PutItem theo khóa chính

### 8.1. Không tự có unique secondary index

DynamoDB có primary key của item. Một GSI giúp query theo field khác nhưng **không cung cấp unique constraint tổng quát** cho field đó.

Nếu bảng Users có:

~~~text
PK = USER#U101
SK = PROFILE
emailCanonical = an@example.com
~~~

thì PutItem với điều kiện item USER#U202 chưa tồn tại **không ngăn** U202 và U101 có cùng emailCanonical.

### 8.2. Conditional PutItem

Muốn “chỉ tạo khi item với chính key này chưa tồn tại”:

~~~text
PutItem(
  Key = (PK, SK),
  ConditionExpression = attribute_not_exists(PK)
)
~~~

Với bảng có partition key PK và sort key SK, điều kiện được kiểm tra trên item có đúng khóa chính của thao tác. Khi item đó đã tồn tại, điều kiện thất bại.

**Điểm then chốt:** Khóa chính được kiểm tra phải chính là khóa đại diện cho tính duy nhất cần bảo vệ.

### 8.3. Thiết kế bảng IdentityClaims

Một cách là tạo bảng riêng giữ quyền sở hữu email:

~~~text
Table: IdentityClaims
Partition key: PK
Sort key: SK

PK = TENANT#T17#EMAIL#an@example.com
SK = CLAIM
ownerUserId = U101
requestId = REQ-778
generation = 1
~~~

Mỗi (tenantId, emailCanonical) ánh xạ đến một item cố định. Hai writer tranh nhau sẽ ghi cùng PK/SK nên có thể dùng conditional write.

### 8.4. Java AWS SDK v2: giành unique claim

~~~java
import java.util.Map;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.ConditionalCheckFailedException;
import software.amazon.awssdk.services.dynamodb.model.PutItemRequest;

public final class UniqueEmailClaim {
    private final DynamoDbClient dynamoDb;

    public UniqueEmailClaim(DynamoDbClient dynamoDb) {
        this.dynamoDb = dynamoDb;
    }

    public boolean tryCreate(
            String tenantId,
            String emailCanonical,
            String userId,
            String requestId
    ) {
        String pk = "TENANT#" + tenantId + "#EMAIL#" + emailCanonical;

        Map<String, AttributeValue> item = Map.of(
                "PK", AttributeValue.fromS(pk),
                "SK", AttributeValue.fromS("CLAIM"),
                "ownerUserId", AttributeValue.fromS(userId),
                "requestId", AttributeValue.fromS(requestId)
        );

        PutItemRequest request = PutItemRequest.builder()
                .tableName("IdentityClaims")
                .item(item)
                .conditionExpression("attribute_not_exists(PK)")
                .build();

        try {
            dynamoDb.putItem(request);
            return true;
        } catch (ConditionalCheckFailedException conflict) {
            return false;
        }
    }
}
~~~

Đây là ví dụ minh họa một claim đơn lẻ. Trong production phải chuẩn hóa key, xử lý timeout/SDK retry/permission, bảo vệ dữ liệu cá nhân trong khóa và chọn cách lưu trạng thái khi người dùng được tạo.

### 8.5. Vì sao conditional put chặn TOCTOU?

Hai request không làm:

~~~text
GET claim
IF missing:
    PUT claim
~~~

Thay vào đó mỗi request trực tiếp yêu cầu:

~~~text
PUT claim IF not exists
~~~

Database kiểm tra và ghi trong cùng thao tác có điều kiện ở phạm vi item. Do đó một writer khác không thể chen vào giữa **kiểm tra và ghi** của chính thao tác ấy.

### 8.6. ConditionalCheckFailed không luôn nghĩa request mới bị từ chối

Nếu client A đã tạo claim nhưng mất response rồi retry cùng requestId, lần retry có thể nhận ConditionalCheckFailed. Nó có thể có nghĩa:

- Một request khác đã giành claim; hoặc
- Chính request A đã thành công ở lần đầu.

Để phân biệt, cần đọc claim hiện có qua đường nhất quán phù hợp rồi so sánh ownerUserId/requestId/payloadHash theo hợp đồng. **Không báo 409 cho retry của cùng một ý định thành công một cách máy móc.**

## 9. DynamoDB: tạo user và claim trong một transaction

### 9.1. Vấn đề khi dùng hai PutItem riêng

Giả sử:

~~~text
1. Put claim TENANT#T17#EMAIL#an@example.com -> SUCCESS.
2. Put user USER#U101                     -> FAILED.
~~~

Hệ có claim nhưng không có user. Lần đăng ký sau bị từ chối dù tài khoản chưa tạo đầy đủ. Đó là **orphan claim**.

Nếu đổi thứ tự:

~~~text
1. Put user U101 -> SUCCESS.
2. Put claim     -> FAILED vì người khác thắng.
~~~

thì hệ có user không sở hữu email hợp lệ.

Đây là nơi cần **atomicity giữa hai item**, nếu chúng nằm trong phạm vi transaction có thể hỗ trợ.

### 9.2. TransactWriteItems

Một giao dịch có thể tạo:

~~~text
Transaction:
  PUT IdentityClaim K -> owner U101
      IF claim chưa tồn tại

  PUT User U101
      IF user chưa tồn tại
~~~

Nếu có conflict ở claim, transaction không commit user một nửa.

Ví dụ ý tưởng theo AWS SDK for Java v2:

~~~java
import java.util.Map;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.Put;
import software.amazon.awssdk.services.dynamodb.model.TransactWriteItem;
import software.amazon.awssdk.services.dynamodb.model.TransactWriteItemsRequest;

public void createUserAndClaim(
        DynamoDbClient db,
        String tenantId,
        String userId,
        String emailCanonical,
        String requestId
) {
    String claimPk =
            "TENANT#" + tenantId + "#EMAIL#" + emailCanonical;

    Put claim = Put.builder()
            .tableName("IdentityClaims")
            .item(Map.of(
                    "PK", AttributeValue.fromS(claimPk),
                    "SK", AttributeValue.fromS("CLAIM"),
                    "ownerUserId", AttributeValue.fromS(userId),
                    "requestId", AttributeValue.fromS(requestId)
            ))
            .conditionExpression("attribute_not_exists(PK)")
            .build();

    Put user = Put.builder()
            .tableName("Users")
            .item(Map.of(
                    "PK", AttributeValue.fromS("USER#" + userId),
                    "SK", AttributeValue.fromS("PROFILE"),
                    "tenantId", AttributeValue.fromS(tenantId),
                    "emailCanonical", AttributeValue.fromS(emailCanonical)
            ))
            .conditionExpression("attribute_not_exists(PK)")
            .build();

    db.transactWriteItems(TransactWriteItemsRequest.builder()
            .transactItems(
                    TransactWriteItem.builder().put(claim).build(),
                    TransactWriteItem.builder().put(user).build()
            )
            .clientRequestToken(requestId)
            .build());
}
~~~

Ví dụ giả định hai bảng cùng nằm trong phạm vi transaction DynamoDB hỗ trợ, khóa của từng bảng được cấu hình đúng và requestId phù hợp giới hạn ClientRequestToken. Mã minh họa đường API, không có toàn bộ xử lý ngoại lệ, retry, phân quyền và bảo vệ thông tin PII.

### 9.3. Vì sao transaction phù hợp hơn hai call?

TransactWriteItems giúp nhóm Put của **claim** và **user** commit hoặc không commit theo mức bảo đảm của DynamoDB ở Region/cấu hình được hỗ trợ.

Nhưng một transaction không có nghĩa:

- GSI đã cập nhật tức thì.
- Redis cache/search đồng thời có bản ghi mới.
- Email xác nhận đã được gửi.
- Một bản sao Global Tables ở Region khác đã có cùng snapshot ngay lập tức.

### 9.4. Không gộp condition và update lên cùng item tùy tiện

DynamoDB TransactWriteItems có ràng buộc đối với việc nhắm **hai hành động tới cùng một item** trong cùng transaction. Khi thiết kế claim và user, mỗi hành động phải xác định key đúng và không vi phạm điều kiện API.

### 9.5. Cần xem xét giới hạn transaction

Số hành động, kích thước dữ liệu, Region, xung đột đồng thời và phí transaction là các giới hạn thực tế. Không nên dùng một transaction khổng lồ để cấp 50.000 username. Một transaction nên có **phạm vi đủ bảo vệ invariant** nhưng không lạm dụng.

## 10. Cassandra/ScyllaDB: INSERT IF NOT EXISTS và lightweight transaction

### 10.1. INSERT thông thường không đủ

Trong Cassandra, INSERT mang tính **upsert**: nếu ghi cùng primary key, dữ liệu có thể được cập nhật/ghi đè theo timestamp và semantics cell, thay vì trả lỗi duplicate key như MongoDB unique index.

Do đó:

~~~sql
INSERT INTO usernames_by_tenant (...)
VALUES (...);
~~~

không tự có ý nghĩa “tạo nếu chưa tồn tại”.

### 10.2. Thiết kế khóa theo trường cần unique

~~~sql
CREATE TABLE usernames_by_tenant (
    tenant_id text,
    username_canonical text,
    user_id uuid,
    request_id text,
    PRIMARY KEY ((tenant_id, username_canonical))
);
~~~

Mỗi cặp (tenantId, usernameCanonical) trở thành một partition key cụ thể. Đây là bảng **ownership claim**, không nhất thiết là bảng user đầy đủ theo userId.

### 10.3. Lightweight transaction (LWT)

~~~sql
INSERT INTO usernames_by_tenant (
    tenant_id, username_canonical, user_id, request_id
) VALUES (
    'T17',
    'alice',
    550e8400-e29b-41d4-a716-446655440001,
    'REQ-778'
) IF NOT EXISTS;
~~~

LWT dùng cơ chế đồng thuận trong phạm vi mà Cassandra/ScyllaDB hỗ trợ để kiểm tra điều kiện và quyết định ghi. Khi điều kiện không thỏa, kết quả CQL có thể cho biết **[applied] = false** cùng thông tin liên quan.

Chỉ một claimant cho cùng khóa được chấp nhận trong phạm vi bảo đảm của LWT khi vận hành đúng consistency và topology.

### 10.4. Vì sao LWT khác GET trước rồi INSERT?

GET trước:

~~~text
GET claim K -> absent
INSERT claim K
~~~

có cửa sổ để client khác ghi K.

LWT:

~~~text
INSERT claim K IF NOT EXISTS
~~~

đưa điều kiện và mutation vào một thủ tục phối hợp có bảo đảm riêng, tránh hai writer đồng thời tự kết luận thành công cho cùng một claim theo phạm vi của LWT.

### 10.5. Chi phí LWT

LWT đắt hơn ghi thông thường trong nhiều workload vì cần các bước phối hợp đồng thuận, thêm round trips và xử lý tranh chấp. Nếu cùng username được hàng nghìn client cố giành, contention có thể làm latency tăng.

Không nên dùng LWT cho mọi log/event độc lập khi không cần ràng buộc; hãy dành nó cho **điểm quyết định quyền sở hữu cần tính đúng đắn**.

### 10.6. SERIAL và LOCAL_SERIAL

Cassandra có những mức **serial consistency** liên quan LWT, như SERIAL và LOCAL_SERIAL, với phạm vi phối hợp khác nhau theo datacenter.

Nếu cần uniqueness xuyên nhiều datacenter, phải kiểm tra cẩn thận phạm vi LWT và chiến lược ghi ở mỗi DC. Không tự suy rằng LOCAL_SERIAL tại hai DC độc lập bảo vệ một business key toàn cầu theo mọi tình huống.

### 10.7. LWT không tự tạo transaction nhiều partition

Giả sử sau khi claim username thành công:

~~~text
LWT claim (T17, alice) -> SUCCESS
INSERT user_by_id(U101)  -> FAILED
~~~

Claim có thể tồn tại nhưng user chưa có. LWT bảo vệ **claim cụ thể** chứ không tự commit nguyên tử claim và một document ở partition khác.

Các lựa chọn thiết kế:

1. Dùng một bảng được keyed theo business key nếu access pattern cho phép.
2. Chọn một workflow có trạng thái PENDING/ACTIVE và retry idempotent.
3. Có reconciliation cho claim mồ côi.
4. Sử dụng một cơ sở dữ liệu/điểm điều phối khác có transaction đúng phạm vi nếu invariant yêu cầu.

Không nên mặc định một LOGGED BATCH CQL sẽ cung cấp serializable transaction nhiều partition giống SQL.

### 10.8. Claim với trạng thái PENDING

Một mô hình:

~~~text
Claim:
  tenantId = T17
  username = alice
  owner = U101
  requestId = REQ-778
  state = PENDING
~~~

Workflow tạo user U101, sau đó đổi claim sang ACTIVE nếu đúng owner/request.

Nếu worker chết giữa chừng, một job reconciliation có thể:

- Kiểm tra user đã được tạo hay chưa.
- Tiếp tục activate nếu request hợp lệ.
- Bù trừ/release claim khi xác nhận thất bại.

**Chú ý:** Không được tự xóa PENDING claim sau timeout mà bỏ qua trường hợp request gốc vẫn đang chạy; cần generation/fencing hoặc điều kiện ownership để tránh hai claimant cùng thắng.

## 11. Redis SET NX: giành quyền trên một key, nhưng không phải unique index bền vững toàn hệ

### 11.1. SET NX

Redis có thao tác:

~~~redis
SET signup:email:T17:an@example.com U101 NX
~~~

NX nghĩa là chỉ SET nếu key chưa tồn tại tại Redis instance xử lý lệnh. Hai client cùng SET cùng key, một lệnh có thể được chấp nhận còn lệnh kia không tạo key.

So với GET rồi SET, đây là **atomic create-if-absent ở phạm vi một Redis key**.

### 11.2. Dùng Redis như lock tạm

~~~redis
SET lock:signup:T17:an@example.com token-A NX PX 30000
~~~

NX xin lock nếu vắng mặt; PX 30000 đặt thời hạn 30 giây.

Một quy trình khái niệm:

~~~text
Acquire lock.
Kiểm tra/ghi tại nguồn.
Release lock nếu còn là chủ sở hữu.
~~~

Nhưng Redis lock **không thay thế unique constraint ở nguồn**. Nếu lock hết TTL trước khi writer hoàn tất, worker khác có thể nhận lock và ghi đè theo logic không bảo vệ. Nếu Redis failover/replication xảy ra, mức bảo đảm về lock/ghi cần được xét riêng.

### 11.3. Không DEL lock vô điều kiện

Sai:

~~~text
Worker A lấy lock token-A.
Lock A hết TTL.
Worker B lấy lock token-B.
Worker A chạy xong muộn và DEL lock.
Worker C lấy lock trong khi B vẫn làm việc.
~~~

Phải kiểm tra token sở hữu trước khi release. Ví dụ Lua trên cùng instance/slot được hỗ trợ:

~~~lua
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
end
return 0
~~~

Token ngẫu nhiên làm giảm nguy cơ xóa lock của chủ khác, nhưng **không ngăn worker A tiếp tục ghi xuống một nguồn bên ngoài sau khi lock hết hạn**.

### 11.4. Fencing token

Với tác vụ có thể chạy quá TTL, một **fencing token tăng đơn điệu** có thể giúp hệ đích từ chối ghi của chủ lock cũ:

~~~text
Worker A nhận fencing=41, chạy chậm.
Worker B nhận fencing=42 sau khi lease A hết hạn.

Nguồn chấp nhận mutation token=42.
Nguồn từ chối mutation token=41 đến muộn.
~~~

Điều quan trọng là **nguồn dữ liệu thật phải kiểm tra token**. Chỉ cấp số token tại lock service nhưng nguồn không dùng nó thì chưa chống được stale writer.

### 11.5. Vì sao không nên coi Redis cache là nguồn uniqueness vĩnh viễn?

Các tình huống:

- Redis được dùng như cache và key bị eviction.
- Redis khởi động lại hoặc phục hồi từ persistence chưa bao phủ mutation.
- Failover và replication lag dẫn tới trạng thái không như kỳ vọng của ứng dụng.
- TTL của claim hết hạn.
- Nhiều Redis cluster/Region không có một điểm quyết định chung.

Nếu tài khoản bắt buộc duy nhất bền vững, cần **unique constraint/conditional insert tại nguồn có thẩm quyền**, còn Redis có thể hỗ trợ giới hạn tranh chấp, throttle hoặc lock tạm theo phạm vi hiểu rõ.

### 11.6. Redis Cluster

Nếu thao tác cần nhiều key, hash slot và cách điều phối của Redis Cluster ảnh hưởng khả năng thực thi script/transaction nguyên tử. Một SET NX trên **một key** không tự bảo vệ quy tắc liên quan đến hai key ở những shard khác nhau.

## 12. Elasticsearch/OpenSearch: thao tác create không ghi đè, nhưng phạm vi là document trong index

### 12.1. Index API có thể ghi đè

Một yêu cầu index thông thường:

~~~http
PUT /users/_doc/U101
Content-Type: application/json

{"emailCanonical":"an@example.com"}
~~~

Khi dùng cùng _id, thao tác index có thể thay thế/cập nhật document theo API thay vì báo conflict.

### 12.2. Create-only

Nếu yêu cầu “chỉ tạo document khi _id chưa tồn tại”:

~~~http
PUT /users/_create/U101
Content-Type: application/json

{"emailCanonical":"an@example.com"}
~~~

Khi document _id đó đã tồn tại trong **concrete index tương ứng**, thao tác create-only có thể trả conflict (thường HTTP 409).

### 12.3. Không bảo vệ email duy nhất nếu _id khác

~~~text
_id=U101, email=an@example.com
_id=U202, email=an@example.com
~~~

Hai create-only requests **khác _id** vẫn có thể được chấp nhận dù email trùng. Muốn dùng create-only để tranh một business key, cần ánh xạ business key thành document ID chung cho mọi claimant.

Ngay cả vậy, sự duy nhất theo **mỗi concrete index** không tự kéo dài qua nhiều index theo tenant, alias rollover, search projection khác hoặc hệ nguồn.

### 12.4. Không dùng search-before-insert làm bộ khóa

Một query search trả 0 kết quả có thể do:

- Chưa có document.
- Document đã được index nhưng **chưa refresh**.
- Search ở index/alias khác.
- Event/projection bị lag.

Vì vậy:

~~~text
SEARCH email -> 0 results
INDEX new user
~~~

không phải thuật toán bảo vệ uniqueness. **Search index có thể là projection, không phải nguồn quyết định identity duy nhất**.

### 12.5. Bulk create trả lỗi theo từng item

Bulk API có thể gửi nhiều create actions, nhưng trả kết quả item-level; một item 409 không rollback những item khác. Không nên hiểu một Bulk request là transaction nguyên tử cho danh sách user.

## 13. Nguyên tắc chung: không dùng hệ dẫn xuất để quyết định tính duy nhất

Một hệ có:

~~~text
Nguồn user có thẩm quyền
       |
       +--> Redis cache
       +--> Search index
       +--> Dashboard read model
       +--> Analytics
~~~

Khi kiểm tra email đã dùng chưa, có thể dùng cache/search để **gợi ý** cho UI nhưng không thể coi một kết quả “không có” từ projection eventual là phép cấp quyền tạo bản ghi.

Quyết định cuối phải thực hiện tại **điểm ghi có cơ chế atomic uniqueness phù hợp**.

Ngay cả nếu cache được invalidate nhanh, một race vẫn có thể xảy ra:

~~~text
Client A query cache: absent.
Client B query cache: absent.
Client A create source.
Client B create source.
~~~

Nếu source không cưỡng chế uniqueness, cache không cứu được invariant.

## 14. Idempotency: cùng request retry không phải một người tranh chấp khác

### 14.1. Timeout sau khi tạo thành công

~~~text
Client A gửi CREATE userId=U101, requestId=REQ-778.
Database tạo thành công.
Phản hồi bị mất trên mạng.
Client A retry cùng requestId.
Database trả duplicate key.
~~~

Nếu API trả 409 ngay, client không biết request của mình có thành công trước đó hay không. Trạng thái duplicate có thể đến từ **chính request đã commit**.

### 14.2. Stable request ID

Một request tạo bản ghi nên có:

~~~json
{
  "requestId": "REQ-778",
  "tenantId": "T17",
  "userId": "U101",
  "emailCanonical": "an@example.com"
}
~~~

Khi retry, **giữ nguyên requestId và userId**. Không tạo userId mới mỗi lần thử vì điều đó làm việc đối soát khó hơn và có thể tạo nhiều side effect.

### 14.3. Phân biệt ba kết quả

| Tình trạng | Cách xử lý mong muốn |
|---|---|
| Key chưa tồn tại, CREATE thành công | CREATED |
| Key đã tồn tại do cùng requestId và cùng payload/owner | Trả lại kết quả thành công trước đó nếu xác minh được |
| Key thuộc request/owner khác | BUSINESS_CONFLICT |
| Kết quả không xác định do timeout | Kiểm tra trạng thái, retry theo idempotency contract |

Không nên trả success cho mọi duplicate key; làm vậy có thể che một xung đột thật giữa hai người.

### 14.4. Idempotency ledger

Ví dụ metadata:

~~~text
IdempotencyRecord
  tenantId
  requestId
  operationType = CREATE_USER
  payloadDigest
  createdUserId
  state = PROCESSING | COMMITTED | FAILED
~~~

Nếu cùng requestId nhưng payload khác, trả lỗi conflict để ngăn client vô tình thay đổi ý định qua retry.

Một digest chỉ giúp đối chiếu payload theo thiết kế; không nên coi hash không có khóa hoặc giá trị email được hash đơn giản là đã ẩn danh hoàn toàn.

### 14.5. Thời hạn idempotency

Ledger không nhất thiết lưu mãi, nhưng nếu xóa quá sớm, request cũ có thể được gửi lại khi người dùng hoặc hệ thống retry từ một queue dài ngày.

Cần xác định cửa sổ retry, retention event, khả năng khôi phục snapshot và quy tắc tái sử dụng userId. Khi ledger hết hạn, một nguồn có **unique ownership** vẫn phải bảo vệ invariant.

### 14.6. ClientRequestToken của DynamoDB

DynamoDB TransactWriteItems hỗ trợ ClientRequestToken với giới hạn thời gian/idempotency do dịch vụ định nghĩa. Nó hữu ích để retry trong cửa sổ đó, nhưng không thay thế một **requestId nghiệp vụ được lưu với kết quả** cho các workflow dài ngày.

## 15. Đừng nhầm unique business key với ID ngẫu nhiên

### 15.1. UUID giảm xác suất trùng nhưng không cưỡng chế business uniqueness

Nếu hai client tạo:

~~~text
U101 = UUID ngẫu nhiên
U202 = UUID ngẫu nhiên
emailCanonical = an@example.com cho cả hai
~~~

thì xác suất UUID trùng có thể cực nhỏ, nhưng email vẫn trùng **100% theo hai request giả định**.

Không thể sửa lỗi uniqueness của email chỉ bằng cách dùng UUID/ULID cho userId.

### 15.2. ID được client sinh

Định danh do client sinh giúp retry ổn định nếu giữ cùng ID, nhưng cần bảo vệ quyền ghi và không để client mạo danh ID của đối tượng khác. Có thể dùng requestId riêng với entityId.

### 15.3. Idempotency key khác unique business key

- **Business key:** Đảm bảo tại một thời điểm chỉ một owner hợp lệ có email/username.
- **Idempotency key:** Đảm bảo xử lý lại **cùng một ý định** không nhân đôi tác dụng.

Hai request khác nhau có cùng business key phải cạnh tranh; cùng request được retry phải nhận kết quả nhất quán. Hệ trưởng thành thường cần cả hai cơ chế.

## 16. Cập nhật một khóa duy nhất đã tồn tại

Tình huống không chỉ xảy ra khi CREATE. Người dùng có thể đổi email:

~~~text
User U101:
  oldEmail = an@example.com
  newEmail = an2@example.com
~~~

Quy trình phải:

1. Giành claim email mới.
2. Cập nhật hồ sơ U101.
3. Giải phóng claim email cũ **nếu đúng owner/generation**.
4. Phát sự kiện cập nhật các projection.

Nếu các bước không ở cùng transaction, có thể có trạng thái tạm:

- Giành email mới nhưng profile vẫn email cũ.
- Profile đã đổi nhưng claim mới chưa hoạt động.
- Claim cũ đã giải phóng trước khi profile đổi.
- Cleanup muộn xóa claim của người vừa đăng ký mới.

### 16.1. Có transaction cùng phạm vi

Ví dụ DynamoDB TransactWriteItems có thể:

~~~text
PUT newEmailClaim IF not exists
UPDATE User U101 IF profileVersion=7
DELETE oldEmailClaim IF owner=U101 AND generation=12
~~~

Nếu cả ba item nằm trong phạm vi transaction, không commit một phần theo điều kiện hỗ trợ. Phải chọn chính xác những item/condition, không gửi hai action không được phép cùng một item trong một transaction.

### 16.2. Không có transaction cùng phạm vi

Thiết kế workflow có trạng thái:

~~~text
REQUESTED
  -> CLAIM_NEW_EMAIL
  -> UPDATE_PROFILE
  -> ACTIVATE_NEW_CLAIM
  -> RELEASE_OLD_CLAIM
  -> COMPLETED
~~~

Cần checkpoint, timeout, retry, cleanup và reconciliation. Có thể có một khoảng thời gian cả email cũ lẫn mới đều được giữ để tránh bị chiếm khi quá trình đang diễn ra.

### 16.3. Compare-and-delete

Khi release:

~~~text
DELETE claim oldEmail
IF ownerUserId=U101 AND generation=12
~~~

Không dùng DELETE vô điều kiện chỉ dựa trên email, vì claim có thể đã được tái cấp cho owner khác.

### 16.4. Khôi phục bản ghi soft-deleted

Nếu username đã được tái sử dụng, “undo soft delete” của user cũ phải kiểm tra unique constraint. Không thể mặc định khôi phục status=ACTIVE sẽ thành công khi người mới đang sở hữu username.

Đây là một ví dụ cho thấy **tính duy nhất là bất biến trong toàn vòng đời**, không chỉ tại API tạo mới.

## 17. Xóa, TTL và cấp lại unique key

### 17.1. Claim bền vững và claim tạm

Hai loại không nên lẫn:

**Durable unique claim:**

~~~text
User U101 là chủ sở hữu username alice.
Claim tồn tại khi user còn quyền sở hữu.
~~~

**Temporary reservation/lease:**

~~~text
Request REQ-778 được giữ tên alice trong 30 giây
để hoàn thành bước xác minh.
~~~

Lease có TTL không đồng nghĩa owner bền vững. Nếu request A vẫn thực thi sau khi lease hết hạn, B có thể giành lease mới. Phải có bước chốt quyền sở hữu tại nguồn với điều kiện/generation thích hợp.

### 17.2. TTL thường dọn bất đồng bộ

Ở một số hệ NoSQL, TTL hết hạn không bảo đảm item bị xóa vật lý tức thì. Nếu dùng TTL của claim làm thời điểm release chính xác, một request có thể gặp xung đột dù đã quá hạn, hoặc thiết kế xử lý quá hạn khác semantics engine.

Nên định nghĩa trạng thái lease hết hạn **theo thời gian nghiệp vụ và conditional mutation**, không chỉ dựa vào việc item đã biến mất vật lý.

### 17.3. Delayed delete

~~~text
t0: User U101 sở hữu username alice, generation=12.
t1: U101 bị xóa, claim được release.
t2: U202 đăng ký alice, generation=13.
t3: Cleanup event cũ của U101 đến muộn.
~~~

Nếu t3 DELETE claim alice vô điều kiện, U202 mất quyền sở hữu. Giải pháp là conditional delete theo owner và generation, hoặc model event có version đủ ngăn thao tác cũ.

### 17.4. Hàng đợi hoặc backup có thể phát lại thao tác cũ

Sau khôi phục backup, một claim được release có thể xuất hiện lại từ snapshot cũ. Một hệ cần quy trình **replay quyết định xóa/đổi ownership** trước khi phục vụ các yêu cầu mới, tùy chính sách recovery.

## 18. Khi nhiều thực thể liên quan cùng một uniqueness rule

### 18.1. Đặt vé ghế ngồi

Quy tắc:

> Với cùng eventId và seatId, chỉ một booking CONFIRMED được sở hữu ghế.

Business key:

~~~text
(eventId, seatId)
~~~

Không nên chỉ unique bookingId vì mỗi booking đều có ID riêng.

Một conditional claim:

~~~text
SEAT#EVENT101#S101 -> ownerBookingId=B1001
~~~

chặn hai booking cùng giành ghế, nếu claim là điểm quyết định chung.

### 18.2. External id từ đối tác

Một đối tác gửi cùng webhook nhiều lần:

~~~text
partnerId = P77
externalOrderId = X1001
~~~

Unique key nên thường là **(partnerId, externalOrderId)**, không chỉ externalOrderId nếu hai đối tác có thể sử dụng cùng mã.

Đây là trường hợp business key đồng thời giúp dedup ingestion; tuy nhiên webhook có thể được gửi lại với payload thay đổi, nên cần quy tắc version và đối chiếu nội dung.

### 18.3. Voucher code

Voucher duy nhất trên toàn hệ hay theo campaign? Hai campaign khác nhau có được dùng code WELCOME10 không?

Chọn unique key sai sẽ tạo xung đột giả hoặc cho phép trùng ngoài ý muốn.

### 18.4. Mã giao dịch thanh toán

Một payment provider có thể cấp transactionId duy nhất trong phạm vi merchant/account. Thiết kế key theo đúng phạm vi cam kết của provider; đừng tự suy rằng mã duy nhất toàn thế giới nếu hợp đồng chỉ bảo đảm trong merchant.

### 18.5. Unique key có thể phụ thuộc thời gian

Ví dụ:

~~~text
Mỗi phòng chỉ có một booking CONFIRMED cho một khoảng thời gian giao nhau.
~~~

Đây là **exclusion/overlap constraint**, phức tạp hơn unique equality key. Một index unique trên (roomId, startTime) **không cấm** hai khoảng [10:00,11:00] và [10:30,11:30] chồng lắp.

Có thể cần phân đoạn slot rõ ràng, transaction/lock theo resource, thuật toán điều phối hoặc một cơ sở dữ liệu hỗ trợ kiểm tra overlap với isolation phù hợp.

**Đừng dùng unique equality để đại diện một invariant khoảng thời gian nếu nó không đủ mạnh.**

## 19. Multi-region: tính duy nhất toàn cầu khó hơn tính duy nhất tại một Region

### 19.1. Hai Region cùng thấy khóa chưa tồn tại

~~~text
Region A: CREATE_IF_ABSENT(email=an@example.com) -> SUCCESS
Region B: CREATE_IF_ABSENT(email=an@example.com) -> SUCCESS
~~~

Nếu mỗi Region chỉ kiểm tra trạng thái local và replication bất đồng bộ, cả hai có thể giành cùng business key trước khi nhận thay đổi của nhau.

Không thể đạt một quyết định duy nhất toàn cầu chỉ bằng cách hỏi hai nơi độc lập “email có chưa?” rồi để chúng tự ghi.

### 19.2. DynamoDB Global Tables

Các chế độ Global Tables có semantics khác nhau về replication/consistency/transaction. Trong các cấu hình eventual multi-region, condition được kiểm tra tại Region đang ghi; nếu hai Region đồng thời tạo cùng key, phải hiểu cách xung đột được giải quyết và liệu app có thể quan sát hai “thành công” local trước khi hội tụ.

Không nên coi ConditionalCheckFailedException ở một Region là cơ chế uniqueness **toàn cầu** trong mọi cấu hình Global Tables.

### 19.3. Một home Region cho mỗi unique key

Một chiến lược:

~~~text
Hash(tenantId, emailCanonical)
  -> chọn một home Region
  -> mọi CREATE của unique key đó được định tuyến về nơi quyết định.
~~~

Nếu home Region không sẵn sàng, hệ phải có chiến lược failover **không cho hai Region cùng trở thành nguồn quyết định độc lập**. Cần consensus/fencing hoặc quy tắc chuyển quyền an toàn, không chỉ bật hai writer đồng thời.

### 19.4. Global coordination và đánh đổi latency

Tính duy nhất mạnh xuyên Region thường đòi phối hợp giữa các replica hoặc một điểm quyết định duy nhất. Điều này ảnh hưởng latency, availability khi partition mạng và chi phí vận hành.

Một số hệ chọn **eventual conflict resolution** thay cho uniqueness tức thời, nhưng khi đó nghiệp vụ phải chấp nhận:

- Hai request có thể được chấp nhận tạm.
- Một owner phải bị thu hồi/đổi tên sau hội tụ.
- Cần thông báo và bù trừ rõ ràng.

Không gọi cơ chế đó là “bảo đảm unique tuyệt đối ở thời điểm tạo”.

### 19.5. Failover kiểm tra fencing

Nếu khóa được cấp ở leader A, sau failover leader B giành quyền, một request từ A cũ không được tiếp tục commit mutation như leader hiện tại. Fencing epoch/term hoặc cơ chế đồng thuận của hệ giúp ngăn **stale leader**.

Một lock TTL đơn giản không tự giải quyết toàn bộ vấn đề multi-region ownership.

## 20. Transaction không thay thế mọi vấn đề về đăng ký

### 20.1. Một điểm atomicity vẫn chưa đủ nếu quy tắc nằm ngoài database

Ví dụ đăng ký email cần:

1. Giành unique email.
2. Tạo user.
3. Gửi mã xác minh.
4. Xác minh mã.
5. Kích hoạt tài khoản.

Transaction database có thể bảo vệ bước 1 và 2 nếu cùng phạm vi. **Gửi email là side effect bên ngoài**, không được rollback tự động khi database abort.

### 20.2. Transactional outbox

Một thiết kế:

~~~text
BEGIN TRANSACTION
  CREATE unique email claim
  CREATE user state=PENDING_VERIFICATION
  WRITE outbox event SEND_VERIFICATION_EMAIL
COMMIT
~~~

Worker đọc outbox và gửi email. Worker có thể retry, nên email/message cần operationId và cơ chế dedup phù hợp.

### 20.3. Không cần transaction xuyên mọi projection

Search index, analytics và cache có thể cập nhật sau bằng CDC/outbox. Đừng kéo transaction đăng ký vào Elasticsearch/Redis chỉ để hiển thị hồ sơ ngay lập tức nếu nghiệp vụ không yêu cầu sự nhất quán đó.

### 20.4. Saga khi nhiều dịch vụ

Nếu tạo account, cấp quota và kích hoạt subscription ở ba dịch vụ khác nhau mà không có transaction chung, có thể dùng saga:

~~~text
CLAIMED_USERNAME
  -> USER_CREATED
  -> SUBSCRIPTION_CREATED
  -> ACTIVE
~~~

Nếu một bước lỗi, retry hoặc bù trừ theo trạng thái. Bù trừ không tự đảo ngược email đã gửi; cần thiết kế side effect idempotent và thông báo người dùng đúng thực tế.

## 21. Phân loại lỗi tại API tạo bản ghi

### 21.1. Conflict nghiệp vụ

Ví dụ:

~~~text
Unique key email thuộc user khác.
~~~

API có thể trả HTTP 409 Conflict theo thiết kế HTTP, nhưng không nên suy mọi lỗi code 409 từ backend đều giống nhau. Cần ánh xạ domain error rõ ràng.

### 21.2. Retry của cùng request

Nếu unique key đã được claim bởi **cùng requestId/payload**, trả trạng thái của lần xử lý trước khi có đủ bằng chứng. Việc này giúp client không tạo hai người dùng vì retry sau timeout.

### 21.3. Throttling hoặc contention

LWT/transaction/conditional writes có thể gặp throttling hoặc contention. Với lỗi tạm thời, retry có giới hạn, backoff và jitter; không biến mọi conflict thành retry vô hạn.

### 21.4. Kết quả không rõ

Nếu kết nối mất sau khi request được server nhận, app phải xác minh trạng thái theo requestId hoặc business key bằng đường đọc phù hợp.

Không tự suy timeout nghĩa “chưa tạo”, rồi cấp một userId khác để thử lại.

### 21.5. Security: không tiết lộ quá mức

Thông báo “email này đã tồn tại” có thể giúp kẻ tấn công dò tài khoản. Với endpoint công khai, cân nhắc thông báo trung tính, giới hạn tần suất, CAPTCHA/chống abuse và luồng xác minh email phù hợp.

Vẫn phải giữ **unique enforcement ở storage**; làm mờ thông báo lỗi không thay thế bảo vệ race condition.

## 22. Backoff và hot key khi rất nhiều client cùng tranh

### 22.1. Tranh chấp không phải lỗi phân bố ngẫu nhiên

Trong flash sale, hàng nghìn khách có thể cùng chọn một mã voucher hoặc một ghế. Dù database bảo vệ unique thành công, nhiều request vẫn tranh cùng key gây:

- Conditional failures rất cao.
- Lock/transaction contention.
- LWT rounds hoặc transaction retries tăng.
- Latency p95/p99 tăng.
- Throttling hoặc hot partition.

### 22.2. Đừng retry business conflict

Nếu một user khác đã sở hữu username alice, retry 100 lần không làm username tự trở lại trống trong ngắn hạn. Đây thường là **non-retryable business conflict**.

Ngược lại, throttling hoặc lỗi mạng có thể retry nhưng phải có chính sách:

~~~text
maxAttempts
exponentialBackoff
jitter
overallDeadline
fallback/queue
~~~

### 22.3. Admission control

Ứng dụng có thể:

- Giới hạn concurrency theo unique key trong một instance để giảm tải.
- Gom những request trùng requestId.
- Dùng queue/partition theo business key để serialize workload.
- Rate-limit endpoint signup/reservation.

Những tối ưu này giúp hiệu năng, nhưng **không thay thế điều kiện nguyên tử tại nguồn** nếu vẫn có nhiều instance/worker hoặc failover.

### 22.4. Pre-check cho UX

Một GET kiểm tra username trước khi submit có thể giúp UI phản hồi nhanh. Tuy nhiên trạng thái có thể đổi ngay sau GET. Chỉ thao tác CREATE/CLAIM nguyên tử mới là kết luận cuối.

### 22.5. Sharding và hot key

Nếu một unique claim được đặt trên một partition cụ thể, tất cả request cùng claim tập trung về partition đó. Đây là điều không tránh khỏi ở mức logic nếu muốn một quyền sở hữu duy nhất, nhưng có thể giảm lượng request trực tiếp bằng coalescing/rate limit trước khi đến storage.

Không nên chia cùng một unique key ra nhiều shard độc lập rồi cho tất cả shard cùng cấp quyền; cách đó phá chính mục tiêu duy nhất.

## 23. Đo lường và giám sát

### 23.1. Những chỉ số nên theo dõi

| Metric | Ý nghĩa |
|---|---|
| Create attempts/s | Lượng request yêu cầu tạo |
| Create successes/s | Số thực thể được tạo thật |
| Unique conflicts/s | Số claim thất bại do đã có owner |
| Same-request replays/s | Số retry idempotent được nhận diện |
| Conditional/LWT latency p50/p95/p99 | Chi phí giành khóa khi tranh chấp |
| Transaction abort/conflict rate | Mức cạnh tranh giữa các writer |
| Throttling rate | Tải vượt khả năng dịch vụ |
| Unknown outcome count | Timeout cần xác minh kết quả |
| Orphan claim count | Claim không có entity sở hữu hợp lệ |
| Claim–entity mismatch | Claim và user/profile lệch |
| Stale cleanup rejection | Số release cũ bị từ chối bằng owner/version |
| Replica/Region conflict metrics | Nguy cơ hai nơi cùng quyết định |

### 23.2. Không chỉ đếm HTTP 409

Một tỷ lệ conflict tăng có thể do:

- Nhiều người chọn cùng username.
- Một bot dò email.
- App retry sai cách.
- Nhiều event trùng.
- Đã đổi canonicalization và tạo collision.
- Một job import chạy song song với API.

Phải phân loại conflict theo nguyên nhân thực, không coi mọi trường hợp là lỗi database.

### 23.3. Đối soát định kỳ

Nếu hệ dùng hai cấu trúc:

~~~text
IdentityClaim[K] -> U101
User[U101]      -> email K
~~~

một job có thể kiểm tra:

1. Claim ACTIVE có user tồn tại không?
2. User ACTIVE có claim đúng không?
3. Có hai user đang hoạt động tự nhận cùng business key không?
4. RequestId/generation có đồng bộ không?
5. Claim PENDING quá hạn có đủ điều kiện sửa/bù trừ chưa?

Reconciliation giúp phát hiện lỗi workflow và phục hồi; nó không được dùng làm biện pháp duy nhất để đảm bảo không bao giờ có duplicate trong lúc người dùng đang giao dịch.

## 24. Kiểm thử race condition đúng cách

### 24.1. Test tuần tự không đủ

Test:

~~~text
CREATE K -> success
CREATE K -> duplicate
~~~

chứng minh xử lý bản ghi **đã tồn tại**, nhưng không chứng minh bảo vệ **hai request cùng lúc**.

### 24.2. Barrier để hai writer bắt đầu cùng lúc

Một ý tưởng Java/JUnit:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

ExecutorService pool = Executors.newFixedThreadPool(2);
CyclicBarrier barrier = new CyclicBarrier(2);

Callable<CreateResult> contenderA = () -> {
    barrier.await();
    return service.createUser("T17", "an@example.com", "U101");
};

Callable<CreateResult> contenderB = () -> {
    barrier.await();
    return service.createUser("T17", "an@example.com", "U202");
};

Future<CreateResult> fa = pool.submit(contenderA);
Future<CreateResult> fb = pool.submit(contenderB);

CreateResult a = fa.get();
CreateResult b = fb.get();

// Ý tưởng assertion:
// - Chỉ một request là CREATED.
// - Request còn lại nhận BUSINESS_CONFLICT hoặc kết quả
//   khác được định nghĩa theo hợp đồng.
// - Đọc từ nguồn có thẩm quyền thấy đúng một owner.

pool.shutdown();
~~~

Ví dụ tập trung vào cách tạo tranh chấp, chưa gồm toàn bộ class service/CreateResult, timeout test và xử lý lỗi.

### 24.3. Kiểm tra invariant ở nguồn

Sau khi hai request hoàn tất:

~~~text
Assert owner(K) chỉ có một.
Assert một user hợp lệ sở hữu K.
Assert không có user mồ côi / claim mồ côi.
~~~

Nếu sử dụng DynamoDB, không chỉ Query một GSI eventual ngay lập tức để kết luận; dùng đường đọc nhất quán phù hợp với nguồn.

### 24.4. Chạy nhiều vòng và tăng contention

Race có thể không xuất hiện trong một lần test. Nên thử:

- 2, 10, 100 writer cùng key.
- Nhiều key khác nhau để so throughput không tranh chấp.
- Writer khác Region/instance theo topology hỗ trợ.
- Batch import đồng thời với API.
- Hai writer dùng cùng requestId và hai writer dùng requestId khác.

### 24.5. Fault injection sau commit

Giả lập mất response sau khi database tạo claim thành công. Client retry cùng requestId. Kiểm tra:

- Không tạo user thứ hai.
- Trả lại cùng owner/kết quả nếu đúng cùng ý định.
- Không gửi email/webhook hai lần ngoài ý muốn.
- Không xóa claim vừa tạo vì cleanup của lần thử cũ.

### 24.6. Test cập nhật và xóa

Các tình huống:

~~~text
User A đang đổi email K1 -> K2.
User B cùng lúc đăng ký K2.

User A soft delete và release K1.
User B đăng ký K1.
Cleanup của A đến muộn.
~~~

Kết quả phải tôn trọng owner/generation, không phụ thuộc thứ tự response ở HTTP.

### 24.7. Test multi-region

Với hệ multi-region, test hai writer tới hai Region cùng lúc, ngắt kết nối replication nếu môi trường test cho phép, rồi kiểm tra:

- Có hai success local không?
- Trạng thái sau hội tụ là gì?
- Có chủ bị mất quyền hoặc ghi đè?
- API có tuyên bố bảo đảm mạnh hơn khả năng thực?

Không được giả định test trên một Region chứng minh uniqueness toàn cầu.

## 25. Những thiết kế sai phổ biến

| Thiết kế sai | Tại sao sai | Hướng đúng |
|---|---|---|
| SELECT trước, nếu không thấy thì INSERT | TOCTOU giữa đọc và ghi | Unique index/conditional create |
| Dùng strong GET rồi INSERT thường | Hai GET đều có thể thấy absent | Kiểm tra và ghi phải nguyên tử |
| Tạo userId UUID và coi email tự unique | UUID chỉ unique định danh user | Ràng buộc trên emailCanonical |
| Chỉ unique trên email, quên tenant | Sai phạm vi business key | Compound/scoped unique key |
| Index unique trên email gốc khác quy tắc UI | ALICE/alice hoặc Unicode collision | Canonicalization và collation thống nhất |
| Dùng DynamoDB GSI làm unique constraint | GSI không cưỡng chế tính duy nhất | Claim item với conditional Put/transaction |
| Gửi Cassandra INSERT thường rồi đọc lại | INSERT upsert, có thể ghi đè | LWT IF NOT EXISTS |
| Dùng Redis GET rồi SET | Có race | SET NX cho phạm vi khóa; nguồn durable vẫn phải bảo vệ |
| Coi Redis lock TTL là độc quyền vĩnh viễn | Lease có thể hết, stale writer còn chạy | Fencing và atomic source condition |
| Search trước rồi index sau | Search có refresh lag | Create-only/nguồn có thẩm quyền |
| Dùng Elasticsearch _create với _id khác business key | _id unique không bảo vệ email | Business-key ownership tại nguồn |
| Retry timeout với userId mới | Có thể tạo bản ghi thứ hai | Stable requestId/entityId, reconciliation |
| Báo mọi duplicate là conflict | Có thể là retry của chính request | So owner/requestId/payload |
| Báo mọi duplicate là success | Che xung đột với người khác | Chỉ success nếu xác nhận cùng ý định |
| Claim xong rồi tạo user ở call khác không sửa lỗi | Orphan claim | Transaction cùng phạm vi hoặc saga/checkpoint |
| Xóa claim vô điều kiện sau cleanup trễ | Có thể xóa owner mới | Compare-and-delete theo owner/generation |
| Cho phép hai Region cùng claim local không phối hợp | Hai success trước hội tụ | Home Region/consensus hoặc conflict policy |
| Xem transaction như tự áp dụng cho cache/email | Side effect ngoài phạm vi | Outbox, idempotent workers |
| Thử test tuần tự rồi kết luận không có race | Không có tranh chấp thực | Concurrent barrier/fault injection |
| Coi 409 tăng là lỗi storage duy nhất | Có thể do bot, retry, UX | Phân loại metrics theo nguồn gốc |

## 26. Bài tập thực hành

### Bài 1. Vẽ lịch chạy gây lỗi TOCTOU

Hai client A/B tạo cùng (tenantId=T17, username=alice), dùng code:

~~~text
if not exists(username):
    insert(user)
~~~

Hãy:

1. Vẽ một interleaving để cả hai thấy username chưa tồn tại.
2. Giải thích vì sao strong consistent read không loại race này.
3. Thay code bằng một primitive atomic create-if-absent.
4. Nêu kết quả được phép của A/B.

**Gợi ý:** Điều kiện và ghi phải nằm trong một thao tác được hệ bảo vệ.

### Bài 2. Unique theo tenant

Một nền tảng có ba request:

~~~text
R1: tenant=T17, username=alice, user=U1
R2: tenant=T88, username=alice, user=U2
R3: tenant=T17, username=alice, user=U3
~~~

1. Những request nào có thể cùng hợp lệ nếu unique theo tenant?
2. Đề xuất compound unique index MongoDB.
3. Đề xuất key trong DynamoDB IdentityClaims.
4. Nêu rủi ro nếu chỉ unique trên username.

### Bài 3. MongoDB duplicate key

Collection users có unique index trên (tenantId, emailCanonical). Hai thread cùng insert document khác _id nhưng cùng email.

1. Cả hai có thể cùng commit thành công không theo ràng buộc index?
2. Vì sao mã E11000 cần phân loại đúng index gây lỗi?
3. Nếu hai request cùng requestId do retry, vì sao không nên trả 409 ngay?
4. Nếu đổi quy tắc canonicalization, phải làm gì với dữ liệu cũ?

### Bài 4. DynamoDB conditional Put

Bảng Users dùng PK=userId; GSI=emailCanonical. Hai yêu cầu dùng userId khác nhau nhưng email giống nhau.

1. Nếu dùng PutItem IF attribute_not_exists(PK) trên Users, tại sao cả hai vẫn có thể thành công?
2. Thiết kế IdentityClaims keyed theo (tenantId, emailCanonical).
3. Viết ConditionExpression cho PutItem claim.
4. Nếu claim thành công nhưng user insert thất bại, làm sao tránh orphan claim?
5. Đề xuất TransactWriteItems và mô tả giới hạn phạm vi.

### Bài 5. Cassandra LWT

Thiết kế:

~~~sql
CREATE TABLE usernames_by_tenant (
    tenant_id text,
    username_canonical text,
    user_id uuid,
    PRIMARY KEY ((tenant_id, username_canonical))
);
~~~

1. Tại sao INSERT thường không phải create-if-absent?
2. Viết INSERT IF NOT EXISTS.
3. Nếu [applied]=false, có chắc request khác thắng không hay có thể chính request đã commit trước timeout?
4. Vì sao LWT claim không tự commit user_by_id ở partition khác?
5. Khi multi-DC, SERIAL/LOCAL_SERIAL cần được xem xét thế nào?

### Bài 6. Redis lock hết hạn

~~~text
t0: A SET lock K token-A NX PX 30000 -> success.
t31s: lock hết hạn, B SET lock K token-B -> success.
t32s: A vẫn chạy, ghi xuống database.
t33s: B cũng ghi xuống database.
~~~

1. Vì sao lock TTL không bảo vệ unique bền vững?
2. Vì sao A không được DEL lock vô điều kiện?
3. Fencing token giúp gì nếu database hỗ trợ so sánh token?
4. Nếu database có unique index, điều đó bổ sung bảo đảm như thế nào?

### Bài 7. Elasticsearch create-only

Hai document:

~~~text
_id=U101, email=alice@example.com
_id=U202, email=alice@example.com
~~~

1. PUT /users/_create/U101 có ngăn U202 được tạo không?
2. Nếu lấy email làm _id, phạm vi uniqueness là gì?
3. Vì sao alias rollover/nhiều concrete indices cần được xem xét?
4. Tại sao search-before-index không an toàn?

### Bài 8. Retry sau timeout

Client tạo user U101 với requestId REQ-778. Database đã commit, phản hồi bị mất. Client retry, nhận duplicate key.

1. Liệt kê ba trạng thái có thể khiến client thấy duplicate key.
2. Thiết kế idempotency record.
3. Khi nào có thể trả lại thành công?
4. Khi nào phải trả conflict?
5. PayloadHash giúp phát hiện vấn đề gì?

### Bài 9. Đổi username và cleanup đến muộn

~~~text
U101 sở hữu alice, generation=12.
U101 đổi tên, release alice.
U202 sở hữu alice, generation=13.
Worker cleanup của U101 đến muộn.
~~~

1. Vì sao DELETE claim alice không điều kiện gây lỗi?
2. Thiết kế điều kiện release dựa trên owner/generation.
3. Đề xuất workflow không có transaction giữa claim và hồ sơ.
4. Khôi phục user U101 cũ có được lấy lại alice tự động không?

### Bài 10. Multi-region

Region A và B đều có bản sao eventual của bảng claims. Hai client cùng tạo email mới tại hai Region trước khi replication đồng bộ.

1. Tại sao mỗi conditional write local có thể không đủ bảo đảm global uniqueness?
2. Đề xuất một home Region có cơ chế failover an toàn.
3. Nếu chấp nhận eventual conflict resolution, người dùng có thể gặp trạng thái gì?
4. Những kiểm thử nào cần thực hiện trước khi tuyên bố global uniqueness?

### Bài 11. Invariant không phải equality unique

Một phòng họp có các booking:

~~~text
B1: 10:00-11:00
B2: 10:30-11:30
~~~

1. Unique(roomId, startTime) có ngăn B1 và B2 cùng tồn tại không?
2. Đề xuất mô hình slot cố định hoặc một cơ chế kiểm tra overlap có isolation phù hợp.
3. Vì sao GET kiểm tra phòng trống rồi INSERT booking có race?
4. Nếu chỉ có distributed lock tạm, điều gì xảy ra khi lease hết hạn?

### Bài 12. Thiết kế kiểm thử tải

Một endpoint create username có 100 client cùng tranh username alice; thêm 10.000 client tạo 10.000 username khác nhau.

Hãy thiết kế benchmark đo:

- Số owner cuối cùng của alice.
- Tỷ lệ create success, business conflict và retry.
- p50/p95/p99 của conditional writes/LWT.
- Hot partition và throttling.
- Số orphan claims.
- Hành vi khi timeout sau commit.
- Hành vi khi failover.

Giải thích vì sao bài test phải kiểm tra **safety invariant** lẫn **khả năng phục hồi**; throughput cao không đủ để chứng minh tính đúng đắn.

## 27. Tổng kết

**Cạnh tranh khi tạo bản ghi có khóa duy nhất** xảy ra khi nhiều writer cùng tin rằng mình có quyền tạo một business key chưa tồn tại. Lỗi điển hình là **TOCTOU**: đọc trước để kiểm tra, rồi ghi sau mà không có bảo vệ nguyên tử.

Các nguyên tắc thiết kế cốt lõi:

1. **Xác định đúng khóa và phạm vi unique:** userId, emailCanonical, (tenantId, username), externalId theo đối tác hay resource/slot.
2. **Đưa quyết định thắng–thua vào thao tác ghi nguyên tử:** MongoDB unique index; DynamoDB conditional PutItem/TransactWriteItems; Cassandra LWT INSERT IF NOT EXISTS; hoặc primitive có bảo đảm tương đương ở nguồn.
3. **Không dùng GET trước làm lớp bảo vệ duy nhất:** Strong read vẫn có thể đọc absent cùng lúc.
4. **Không nhầm upsert với create-if-absent:** Một upsert vô điều kiện có thể ghi đè owner.
5. **Phân biệt một item với nhiều item:** Giành claim có thể nguyên tử nhưng tạo profile/booking ở nơi khác vẫn có nguy cơ commit một phần nếu không có transaction/workflow.
6. **Xử lý retry và timeout:** Cùng requestId/payload có thể đã thành công; duplicate không luôn đồng nghĩa người khác thắng.
7. **Bảo vệ cả UPDATE, DELETE và reuse:** Release phải kiểm tra owner/generation để không xóa claim của người mới.
8. **Nhìn rõ phạm vi Region/replica:** Unique tại một Region không nhất thiết là unique toàn cầu khi có active-active writes bất đồng bộ.
9. **Không dùng cache/search như nguồn quyết định:** Redis lock TTL hoặc search-before-index không thay thế ràng buộc ở datastore có thẩm quyền.
10. **Kiểm thử tranh chấp thật:** Concurrent barrier, fault injection, retry, failover và reconciliation là cần thiết để phát hiện lỗi.

Câu hỏi quyết định không phải “Tôi đã kiểm tra rằng khóa này chưa tồn tại chưa?”, mà là **“Ai có quyền quyết định nguyên tử rằng request này thắng quyền sở hữu khóa — và làm sao mọi lần retry, cập nhật, xóa hoặc failover vẫn tuân thủ quyết định đó?”**
