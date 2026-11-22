# Kiểu định danh đối tượng và tương thích với hạ tầng ACL

## 1. Vì sao định danh object quyết định tính đúng của ACL?

ACL (Access Control List) là cách cấp quyền theo từng đối tượng cụ thể. Để tìm đúng tập quyền, Spring Security phải nhận diện cùng một đối tượng bằng **type** và **identifier** ổn định. Một document có thể có ID số trong database, UUID trên API, hoặc khóa chỉ duy nhất bên trong tenant. Các dạng đó **không tự tương đương** khi đi vào hạ tầng ACL.

Một ví dụ nguy hiểm:

~~~text
tenant north / document 42
tenant south / document 42
~~~

Nếu cả hai đều được đưa vào cùng kho ACL bằng một khóa `("Document", 42L)`, ACL không tự có thông tin tenant để phân biệt. Người được chia sẻ document của tenant north có thể bị áp dụng nhầm danh sách quyền cho document của tenant south nếu ứng dụng còn cho phép truy cập chéo.

Ngược lại, một chương trình Java dùng UUID vẫn có thể tạo `new ObjectIdentityImpl(Document.class, uuid)` bởi constructor nhận `Serializable`, nhưng điều đó **không đủ chứng minh** mọi thành phần JDBC ACL mặc định tạo, lưu, truy vấn và đọc lại UUID đúng.

Bài học này giải thích hợp đồng `ObjectIdentity`, sự tương thích của `Long`/`Integer`/`UUID`/`String`/khóa tổng hợp với Spring Security ACL, cách tạo mapping bền vững khi ID không phải số, tenant isolation, schema, cache, migration và test. Quy tắc xuyên suốt là **khóa ACL phải duy nhất, ổn định, không tái sử dụng và được diễn giải nhất quán ở mọi điểm đọc/ghi**.

## 2. Đừng nhầm các loại ID trong cùng hệ thống

| Loại ID | Ví dụ | Công dụng | Lưu ý |
|---|---|---|---|
| Domain primary key | `documents.id = 42` | Khóa record nghiệp vụ | Có thể làm ACL ID nếu toàn cục, bất biến |
| Public/API identifier | `550e8400-e29b-41d4-a716-446655440000` | Gửi trong URL/event | Không nhất thiết cùng kiểu với ACL |
| ACL object identifier | `ObjectIdentityImpl(Document.class, 42L)` | Tìm ACL cho domain object | Khóa logic gồm type và identifier |
| ACL row primary key | `acl_object_identity.id = 751` | PK nội bộ bảng ACL | Không phải domain ID |
| ACL surrogate ID (tùy thiết kế) | `document_acl_key.acl_key = 1001` | Ánh xạ UUID/khóa ghép sang Long | Bảng ứng dụng bổ sung, khác ACL row PK |

Một bản ghi minh họa:

~~~text
acl_class.id                          = 13
acl_class.class                       = com.example.domain.Document
acl_object_identity.id               = 751
acl_object_identity.object_id_class  = 13
acl_object_identity.object_id_identity = 42
acl_entry.acl_object_identity        = 751
~~~

Giá trị `751` ở đây là khóa hàng ACL mà `acl_entry` tham chiếu; còn giá trị `42` là identifier logic của document. Nếu bạn đem `751` vào `ObjectIdentityImpl(Document.class, 751L)` thay vì `42L`, bạn đang hỏi ACL của object khác.

Trường hợp dùng bảng ánh xạ UUID → Long, `acl_key` là số ổn định để làm **logical ACL identifier**. Nó khác với `acl_object_identity.id` do ACL tự sinh. Phải dùng tên biến rõ như `aclKey`, `publicId` và `aclRowId`.

## 3. Hợp đồng của ObjectIdentity

Interface `org.springframework.security.acls.model.ObjectIdentity` cho phép lấy:

- `getType()`: chuỗi tên loại đối tượng, thường là tên class.
- `getIdentifier()`: đối tượng `Serializable` biểu diễn ID thật của domain object.
- `equals()` và `hashCode()`: cơ sở để so sánh identity, lookup và cache.

Lớp thực thi thông dụng là `ObjectIdentityImpl`:

~~~java
ObjectIdentity first =
        new ObjectIdentityImpl(Document.class, 42L);

ObjectIdentity second =
        new ObjectIdentityImpl("com.example.domain.Document", 42L);

ObjectIdentity fromEntity =
        new ObjectIdentityImpl(document);
~~~

Đây là **snippet tích hợp Spring Security ACL**, phụ thuộc `Document`, `document`, các import và dependency phù hợp.

Hai constructor đầu đặt rõ type và ID. Constructor nhận object sử dụng reflection để xây identity: object phải có `getId()` công khai theo contract. Với record Java như `record Document(UUID id) {}`, accessor là `id()` chứ không phải `getId()`; nếu dùng JPA proxy, runtime class cũng có thể khác class domain chuẩn. **Ưu tiên factory gọi constructor tường minh** khi muốn tránh phụ thuộc reflection và kiểu proxy.

Javadoc yêu cầu ID không null, không tái sử dụng để đại diện một object **khác cùng type**. Vì ACL được coi là tương đối bền vững, số ID kỹ thuật bất biến (sequence/surrogate) thường tốt hơn slug, tên file hay mã nghiệp vụ có thể đổi.

## 4. Long là đường đi ít rủi ro với Spring Security ACL JDBC

Tài liệu chính thức Spring Security nhấn mạnh nhiều phần của ACL module truyền thống dựa trên định danh `long`. Với domain entity đã có `Long id` từ sequence và mỗi ID không bị tái sử dụng, đường đi mặc định thường đơn giản nhất:

~~~java
ObjectIdentity oid = new ObjectIdentityImpl(Document.class, documentId);
Acl acl = aclService.readAclById(oid);
~~~

Trong snippet này, `documentId` là `Long` đã persist, `aclService` là Spring ACL service đã cấu hình. Đây không phải chương trình Java độc lập. Nếu ACL chưa tồn tại, việc đọc có thể ném `NotFoundException`; policy của dữ liệu riêng tư phải từ chối hoặc báo lỗi có kiểm soát, **không cho phép vì không tìm thấy ACL**.

Một điều tưởng như mâu thuẫn:

~~~java
// Constructor chấp nhận Serializable: code này có thể compile.
ObjectIdentity oid = new ObjectIdentityImpl(
        Document.class,
        java.util.UUID.fromString("550e8400-e29b-41d4-a716-446655440000"));
~~~

`UUID` implements `Serializable`, nên constructor Java chấp nhận. Tuy nhiên, **type signature của ObjectIdentity không phải cam kết JDBC implementation hỗ trợ mọi Serializable**. Các đường đọc `BasicLookupStrategy`, ghi `JdbcMutableAclService`, conversion, object generator, SQL schema, batch lookup và cache vẫn cần kiểm thử theo version. Tài liệu về module ACL còn lưu ý những ID không tương thích `long` có thể yêu cầu tùy biến nhiều thành phần.

Kết luận thực hành:
- Với `Long` bất biến và globally unique trong phạm vi type/ACL store: thường dùng trực tiếp.
- Với `Integer` tương thích miền giá trị: chuẩn hóa sang `Long` để tránh lẫn kiểu và tràn số khi chuyển.
- Với `UUID`, `String` hoặc composite: dùng adapter sang Long bền vững hoặc chứng minh cụ thể một hạ tầng ACL tùy chỉnh hỗ trợ end-to-end.
- Không kết luận UUID bị cấm ở mọi hệ thống ACL; hạn chế đang nói là **đường tích hợp Spring Security ACL JDBC mặc định**, không phải UUID trong domain nói chung.

## 5. Schema ACL và ràng buộc phải hiểu đúng

Spring Security ACL JDBC có bốn bảng cốt lõi:

| Bảng | Ý nghĩa |
|---|---|
| `acl_sid` | Chủ thể được cấp quyền: principal hoặc authority |
| `acl_class` | Kiểu domain object, thường lưu chuỗi tên class |
| `acl_object_identity` | Một object được bảo vệ, ID, owner ACL, parent |
| `acl_entry` | ACE: permission mask, SID, grant/deny và thông tin audit |

Theo DDL PostgreSQL trong tài liệu Spring Security, các cột tiêu biểu:

~~~sql
-- Mô tả rút gọn các cột; không phải script migration hoàn chỉnh.
CREATE TABLE acl_object_identity (
    id BIGSERIAL PRIMARY KEY,
    object_id_class BIGINT NOT NULL,
    object_id_identity VARCHAR(36) NOT NULL,
    parent_object BIGINT,
    owner_sid BIGINT,
    entries_inheriting BOOLEAN NOT NULL,
    UNIQUE (object_id_class, object_id_identity)
);
~~~

Đoạn SQL này **lược bỏ foreign keys** để tập trung vào ID; nếu dùng để triển khai cần xem DDL chính thức theo database dialect/version.

Cần nhớ:

1. `acl_object_identity.id` là row PK do ACL database quản lý; `object_id_identity` là ID logic domain object.
2. `object_id_class` tham chiếu bảng `acl_class`, nên identity thực tế dựa vào **cả type và identifier**.
3. `parent_object` tham chiếu **ACL row PK của parent**, không phải ID domain parent trực tiếp.
4. DDL mẫu dùng `VARCHAR(36)`, đủ chiều dài textual UUID chuẩn nhưng **không chứng minh JDBC Java conversion/lookup hỗ trợ UUID**.
5. Schema của MySQL, Oracle, HSQLDB hoặc những version khác có thể dùng kiểu/cấu hình khác. Không tự “sửa cho giống PostgreSQL” nếu production không chạy PostgreSQL.
6. Kiểm tra unique/index theo DB thật; một bảng ACL dùng chung nhiều tenant mà có ID cục bộ có nguy cơ trùng logical identity dù SQL unique constraint vẫn “đúng” về cấu trúc.

Schema phải tương thích với cả SQL do `JdbcMutableAclService` ghi và SQL do `BasicLookupStrategy` đọc. Chỉ thay loại cột không phải một migration ACL hoàn chỉnh.

## 6. So sánh chiến lược định danh

| Domain identifier | Ưu điểm | Vấn đề tương thích ACL cần xử lý |
|---|---|---|
| Long sequence | Bền vững, dễ query, phù hợp hạ tầng mặc định | Đảm bảo không tái sử dụng, không trùng giữa tenant cùng type |
| Integer PK | Nhẹ, phổ biến ở hệ cũ | Chuẩn hóa Long; không cast làm mất dữ liệu |
| UUID | Phân tán, làm public ID, khó đoán | Constructor Serializable không chứng minh JDBC hỗ trợ; có thể cần mapping |
| String business code | Dễ đọc như `INV-2026-007` | Mutable, collation, case, độ dài, Unicode/leading zeros |
| Composite key | Diễn đạt `(tenant, localId)` | ObjectIdentity có một identifier; phải ánh xạ sang một key ổn định |
| UUID + Long nội bộ | API giữ UUID; ACL dùng Long | Thêm mapping, unique, transaction, consistency và migration |
| Temporary ID trước persist | Tiện trên UI | Chưa đủ ổn định để tạo ACE hay cache ACL |
| Email/slug/name | Có nghĩa nghiệp vụ | Thay đổi và tái sử dụng; không lý tưởng cho ACL |

Không có nghĩa mọi hệ thống phải đổi domain primary key sang Long. Nếu hiện có UUID domain, thường có thể giữ UUID nguyên vẹn ở API/database, dùng một ID kỹ thuật khác **chỉ cho ACL**.

## 7. Multi-tenant: vì sao type + id phải phản ánh phạm vi

Ví dụ hai tenant có khóa local giống nhau:

~~~text
tenant north / Document#42
tenant south / Document#42
~~~

Trong cùng ACL store:

~~~text
("com.example.Document", 42L)
("com.example.Document", 42L)
~~~

Hai tuple bằng nhau. ACL không tự xem trường tenant trên bảng `documents`. Nếu lookup chỉ dựa vào tuple đó, không thể xác định danh sách ACE thuộc tenant nào.

Các thiết kế khả thi:

**A. ID Long toàn cục**: domain hoặc bảng mapping cấp ID từ một sequence duy nhất trong ACL store, bảo đảm không trùng giữa tenant. Đây thường là cách ít rủi ro.

**B. Kho ACL riêng per tenant**: tách database/schema/cache và routing bằng tenant identity đáng tin. Thận trọng với cache key, connection routing, sự cố tenant switch.

**C. Custom persistence**: mở rộng type/identifier để bao gồm tenant, đồng bộ các lớp lookup, conversion, schema, cache, write và migration. Đòi hỏi công sức lớn hơn.

Không đủ nếu chỉ tự nối `north:42` thành chuỗi rồi truyền vào `ObjectIdentityImpl`. Chuỗi đó giải quyết phần **duy nhất của khóa**, nhưng chưa chứng minh đường JDBC long-centric có thể lưu và tìm đúng chuỗi. Nếu không muốn triển khai custom JDBC, nên ánh xạ tuple sang Long.

**Tenant scope vẫn phải kiểm tra độc lập trong business query.** Một SID được grant trong ACL không tự là bằng chứng user được vào tenant khác. Định danh không va chạm giúp ACL đúng, nhưng không thay hàng rào isolation.

## 8. Adapter an toàn: (tenant, UUID) → Long ACL ID

Một mô hình thực tế:

~~~text
Business document: (tenant=north, public UUID=550e8400-...)
        |
        v
Mapping: (north, UUID) -> acl_key=1001
        |
        v
ObjectIdentityImpl(Document.class, 1001L)
        |
        v
ACL_CLASS / ACL_OBJECT_IDENTITY / ACL_ENTRY
~~~

Ví dụ PostgreSQL tạo bảng mapping của ứng dụng:

~~~sql
-- Bảng này do ứng dụng thiết kế; KHÔNG phải bảng ACL mặc định.
CREATE TABLE document_acl_key (
    acl_key       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id     VARCHAR(64) NOT NULL,
    document_uuid UUID NOT NULL,
    CONSTRAINT uq_document_acl_key UNIQUE (tenant_id, document_uuid)
);
~~~

Một UUID như `550e8400-e29b-41d4-a716-446655440000` có thể xuất hiện ở hai tenant nếu domain định nghĩa identity theo tenant. Khi đó:

~~~text
("north", UUID) -> 1001L
("south", UUID) -> 1002L

ObjectIdentityImpl(Document.class, 1001L)
ObjectIdentityImpl(Document.class, 1002L)
~~~

Việc cấp phát `acl_key` phải **bền vững** và có unique constraint ở DB. Không tái sinh key sau mỗi request. Tạo mapping idempotent trong transaction với cơ chế retry/upsert phù hợp DB; tránh hai request đồng thời cấp hai mapping cho một object.

### Quy trình giải quyết identity

1. Nhận public UUID của resource từ API, không coi nó là bằng chứng quyền.
2. Xác thực người gọi và lấy tenant scope **đã xác minh**.
3. Truy vấn resource theo `(tenant, UUID)`; không làm query theo UUID đơn lẻ nếu không globally unique.
4. Tra mapping tương ứng, lấy `acl_key: Long`. Chỉ luồng tạo resource hợp lệ mới được tạo mapping mới; không để endpoint đọc tự tùy tiện sinh ACL key.
5. Tạo `ObjectIdentityImpl(Document.class, aclKey)` qua factory thống nhất.
6. Đọc và đánh giá ACL theo SID và permission đúng; thiếu mapping/ACL → không cấp quyền, kiểm tra vì sao dữ liệu thiếu.
7. Đọc hoặc ghi dữ liệu với tenant scope và quy tắc transaction phù hợp; không thực hiện side effect trước khi cho phép.

**Không dùng** `uuid.hashCode()`, `uuid.getLeastSignificantBits()`, modulo, cast từ long sang int, cắt 8 ký tự UUID hoặc `Long.parseLong(uuidString)` làm adapter. Chúng có thể va chạm, mất thông tin hoặc lỗi parse. Một collision của identity ACL có thể chuyển quyền từ đối tượng này sang đối tượng khác.

## 9. Khi nào không cần mapping?

Nếu domain đã có `Long id`:
- ID được cấp từ DB sequence hoặc nguồn đủ bảo đảm duy nhất.
- ID không được tái sử dụng sau delete.
- Một type + ID không mô tả hai object trong cùng ACL store.
- Type canonical ổn định khi đọc/ghi.
- Các thao tác ACL JDBC mặc định đã qua test.

Thì dùng trực tiếp:

~~~java
ObjectIdentity oi = new ObjectIdentityImpl(
        Document.class, document.getId());
Acl acl = aclService.readAclById(oi);
~~~

Đây là **đoạn tích hợp**, phụ thuộc `Document`/`AclService` và Spring Security ACL. Không tạo ACL cho entity transient có ID null. Không cần thêm bảng UUID → Long nếu nó không giải quyết vấn đề thực tế.

Mapping không miễn phí: phải quản lý transaction, consistency, cleanup, cache, migration và audit. Chọn nó khi public/domain ID không phù hợp hạ tầng ACL hoặc có trùng lặp theo tenant.

## 10. ObjectIdentityImpl(Object): lưu ý về reflection và proxy

Một constructor hữu ích là:

~~~java
ObjectIdentity oi = new ObjectIdentityImpl(document);
~~~

Nó có thể lấy tên class runtime và gọi public `getId()` của object. Các trường hợp phải kiểm thử:

- Java record: accessor `id()` không tương đương `getId()`; có thể không tìm được identity.
- Entity JPA chưa persist: ID null hoặc tạm, không tạo ACL bền vững được.
- Proxy Hibernate/JPA: class runtime có thể khác class domain hoặc bị tạo subclass; type string trích tự động có thể lệch so với type tạo ACL trước đó.
- EmbeddedId/composite ID: trả một object Serializable chưa có nghĩa JDBC ACL mặc định hỗ trợ.
- Business ID mutable: getter thay giá trị nhưng ACL cũ vẫn lưu ID trước đó.
- Class refactor: tên package/type mới khác `acl_class.class` cũ.

Cách giảm rủi ro là **factory identity tường minh**:

~~~java
public final class AclObjectIdentities {
    private AclObjectIdentities() { }

    public static ObjectIdentity document(Long aclKey) {
        if (aclKey == null || aclKey <= 0) {
            throw new IllegalArgumentException("Invalid ACL key");
        }
        return new ObjectIdentityImpl(
                "com.example.domain.Document", aclKey);
    }
}
~~~

Mẫu tích hợp này cần imports của `ObjectIdentity` và `ObjectIdentityImpl`. Type string ở đây **là quy ước ứng dụng**, phải khớp dữ liệu `acl_class` và mọi điểm gọi; đừng đổi nó chỉ vì rename package. Factory giúp không tạo ACL bằng `Document.class` ở một service rồi lookup bằng class proxy khác ở service khác.

## 11. equals/hashCode và key của ACL cache

Javadoc `ObjectIdentityImpl` mô tả equality dựa trên type và identifier. Với numeric identities, `Integer` và `Long` cùng giá trị có thể được coi là bằng nhau; những Serializable khác dùng equality thông thường.

Do đó:
- `42` và `42L` có quy tắc numeric equivalence trong implementation, nhưng vẫn nên chuẩn hóa Long thống nhất.
- `"42"` không tự bằng `42L`.
- `UUID` object không tự bằng chuỗi textual UUID.
- `"com.old.Document"` không tự bằng `"com.new.Document"`.
- Hai tenant có cùng type+id là **cùng khóa** ở tầng ACL nếu không thiết kế isolation.

Một permission cache dùng **chỉ documentId** làm key là không đủ trong hệ nhiều loại object hoặc nhiều tenant. Với cache của ACL engine, identity phải không va chạm; khi thêm tenant vào architecture, chính cache cũng cần ranh giới tương ứng. Sau grant/revoke, đổi owner, chuyển tenant hoặc migration type/id, cần invalidate đúng key; cache ALLOW cũ không được tiếp tục cấp quyền sau khi quyền bị thu hồi.

Không dùng behavior equals đặc biệt của Numeric ID như lời bảo đảm rằng mọi cách bind SQL và deserialize DB đều tự nhất quán. Các tầng Java, JDBC, schema và cache phải được kiểm chứng bằng round-trip thực tế.

## 12. Compatibility checklist cho hạ tầng JDBC ACL

Khi cần hỗ trợ ID non-long, **không chỉ kiểm tra constructor**. Hãy kiểm tra cả vòng đời:

~~~text
ObjectIdentity + getIdentifier()
        |
        v
AclService / MutableAclService
        |
        +--> JdbcMutableAclService create/update/delete
        +--> BasicLookupStrategy read/batch
        +--> SQL parameter binding / ConversionService
        +--> ObjectIdentityGenerator
        +--> AclCache / equals/hashCode
        |
        v
ACL tables + indexes + constraints
~~~

Các câu hỏi kiểm thử:
1. `createAcl(oi)` ghi đúng ID vào `acl_object_identity.object_id_identity` không?
2. `readAclById(oi)` có lấy lại đúng object và cùng loại ID Java không?
3. Một ACE được thêm bằng `updateAcl` có được lấy lại đúng cho SID và permission tương ứng không?
4. `readAclsById` batch nhiều object có trả đúng map key khi String/UUID khác Long không?
5. Lookup cold cache và warm cache có cùng kết quả không?
6. Parent ACL, SID, inheritance và audit vẫn chính xác không?
7. `deleteAcl`, grant/revoke, cache invalidation có không bỏ sót hoặc ảnh hưởng object khác?
8. SQL được chỉnh theo một database dialect có hoạt động giống nhau khi kết nối production không?
9. Có mã nào gọi `hasPermission(#uuid, targetType, 'READ')` trong khi ACL thực tế dùng Long mapping không?
10. Khi resource không có ACL/mapping hoặc database outage, hệ thống **fail closed** hay mở quyền?

Javadoc `BasicLookupStrategy` có một số khả năng tùy biến SQL clause, `ConversionService`, `ObjectIdentityGenerator`, nhưng không nên suy luận chỉ set một converter là xong. Các SQL clauses và result set phải khớp nhau; tài liệu còn lưu ý **không hỗ trợ subclassing** của `BasicLookupStrategy`. Nếu cần một lookup rất khác, đánh giá một custom strategy thực sự hoặc chọn mapping Long.

## 13. hasPermission và public UUID: tránh truyền sai ID

Method Security cung cấp `hasPermission(target, permission)` và `hasPermission(targetId, targetType, permission)` thông qua `PermissionEvaluator`. Với `AclPermissionEvaluator`, type và ID phải mô tả đúng ObjectIdentity đã được tạo.

Nếu ACL lưu chính ID Long của Document:

~~~java
@PreAuthorize(
    "isAuthenticated() and hasAuthority('document:read') " +
    "and #id != null " +
    "and hasPermission(#id, 'com.example.domain.Document', 'READ')")
public DocumentView read(Long id) {
    return readScopedByTenant(id);
}
~~~

Mã trên là **mảnh ghép Spring**, cần `@EnableMethodSecurity`, ACL evaluator, parameter binding và service/repository đầy đủ. Nó không tự đảm bảo tenant isolation.

Nếu method nhận public UUID, nhưng ACL lưu Long surrogate, **không** truyền thẳng UUID vào `hasPermission(#publicId, ...)` rồi giả định framework tự map. Có thể tạo policy bean:

~~~java
@PreAuthorize(
    "isAuthenticated() and hasAuthority('document:read') " +
    "and @documentAclPolicy.canRead(authentication, #publicId)")
public DocumentView readByPublicId(UUID publicId) {
    return documentQuery.readScoped(publicId);
}
~~~

Trong bean `documentAclPolicy.canRead`:
- Lấy actor/tenant tin cậy từ authentication.
- Tìm resource đúng tenant+publicId; nếu không tìm thấy thì không cấp.
- Lấy `aclKey Long` từ mapping đã lưu; không sinh ID mới trên đường read.
- Tạo identity canonical và dùng ACL evaluator/policy để xác định READ.
- Không grant khi thiếu mapping, thiếu ACL hoặc backend không trả lời.
- Giữ guard tenant cả trong query sau authorization, đặc biệt với dữ liệu thay đổi đồng thời.

Lời gọi method security phải đi qua Spring proxy; `this.readByPublicId(...)` nội bộ có thể bypass interceptor ở proxy mode. Đặt policy tại boundary và test các đường gọi HTTP/message/service.

## 14. Một ID ổn định quan trọng hơn một ID có ý nghĩa

ACL có vòng đời độc lập với một số thuộc tính nghiệp vụ. Ví dụ:
- Đổi tên document không phải tạo ACL mới.
- Đổi slug từ `draft-alpha` sang `final-alpha` không được mất quyền cũ.
- Chuyển owner là một thao tác permission riêng, không tự làm biến mất ACL object identity.
- Copy document tạo **object mới**, thường phải cấp ACL identity mới; quyền copy-from được quyết định theo policy.
- Xóa rồi khôi phục cần đặc tả có khôi phục ACE cũ hay không; không được tự cấp lại cho object khác trùng ID.

Những ID tốt cho ACL thường là:
- Bất biến.
- Không null.
- Không tái sử dụng trong phạm vi type/store.
- Được lưu bền vững và truy vấn độc lập với business label.
- Có cách xác định nhất quán qua Java/JDBC/cache và các phiên bản deploy.

Dùng email, file path, mã hóa đơn có thể bị sửa như identity ACL thường tạo nghĩa vụ migrate quyền trên mọi lần đổi business value. Một Long surrogate ổn định tránh được phần lớn rủi ro này.

## 15. Tạo ACL sau khi có ID và quản lý vòng đời

Với JPA `@GeneratedValue`, ID có thể được cấp tại thời điểm persist hoặc flush tùy generation strategy. Không tạo ACL trước khi ID thật xuất hiện. Quy trình mẫu:

~~~text
transaction:
  1. validate actor, tenant and create permission
  2. persist document
  3. obtain stable ID
  4. resolve/create stable ACL identity
  5. create initial ACL and owner/ACE
  6. commit business data + ACL consistently
~~~

Tính nguyên tử phụ thuộc việc domain DB và ACL store có dùng cùng transaction boundary hay không. Nếu hai DB/service khác nhau, cần cơ chế đồng bộ/outbox/reconciliation và phải xác định policy khi ACL chưa sẵn sàng. Không mặc định một `@Transactional` trên một datasource sẽ rollback cả hệ ngoài.

Khi xóa resource:
- Thu hồi/xóa ACL và ACE theo API framework được hỗ trợ.
- Xóa hoặc đóng mapping phù hợp, không tái sử dụng `aclKey`.
- Invalidate ACL cache.
- Xử lý parent-child ACL theo chính sách; không để child trỏ vào parent đã xóa.
- Audit actor, object, tenant và hành động grant/revoke/delete bằng dữ liệu được xác minh.

Một ACL mồ côi không nhất thiết mở quyền ngay, nhưng có thể gây sai khi ID được tái sử dụng, khôi phục hoặc import; cần kiểm tra định kỳ theo quy trình an toàn.

## 16. Migration từ ID cũ và đổi class/package

Một lần đổi type hoặc identifier trong ACL là **migration bảo mật**, không chỉ đổi schema domain.

Các bước hợp lý:

1. Inventory mọi loại object, kiểu ID, ACL row, nơi tạo/read/update/delete, cấu hình evaluator/cache.
2. Chốt canonical identity: giữ Long ACL key cũ nếu có thể; thêm public UUID độc lập.
3. Với mapping mới, backfill duy nhất theo tenant/type/externalId, ràng buộc unique chặt.
4. Bảo toàn những ACE hiện có: không sinh ACL Long khác cho cùng object rồi bỏ sót quyền cũ.
5. Xử lý rename từ `com.old.Document` sang `com.new.Document`: migrate `acl_class.class` hoặc giữ canonical type ổn định; không để hai bộ ACL bất đồng.
6. Kiểm tra schema size, collation, SQL bind và converter của database production.
7. Triển khai reader/writer trong một rollout có kiểm soát; không có nhánh “không tìm được ACL mới thì cho phép”.
8. Invalidate/rebuild cache theo keys mới, không cache quyền grant sai tenant.
9. Chạy test trước/sau migration trên dữ liệu có ALLOW, DENY, grant/revoke và inheritance.
10. Theo dõi ACL NotFound, duplicate key, 403 bất thường, permission cache misses và mapping drift.

Nếu domain chuyển từ Long PK sang UUID, có thể **giữ Long cũ chỉ làm ACL identity** và thêm UUID public; điều đó giảm nhu cầu rewrite ACE. Nếu đã có public UUID mà chưa có ACL, mapping bền vững có thể được tạo khi migrate resource đã tồn tại.

Với rolling deployment, code version cũ và mới phải thống nhất một key trong giai đoạn giao nhau. Không cùng lúc ghi ACL bằng class name cũ ở một pod và class name mới ở pod khác khi chưa có thiết kế tương thích.

## 17. Java 17 độc lập: tách hai tenant và hai type cùng public ID

Demo Java thuần không dùng Spring Security nhưng cho thấy lợi ích của registry ánh xạ **(tenant, type, external ID) → Long**. Đây chỉ là minh họa, **không dùng map trong memory làm registry quyền production**.

Tạo file `AclIdentityDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;

public class AclIdentityDemo {
    record ExternalKey(String tenant, String type, String externalId) { }

    static final class Registry {
        private final Map<ExternalKey, Long> entries = new HashMap<>();
        private long sequence = 1000L;

        long allocate(ExternalKey key) {
            if (key == null
                    || key.tenant() == null || key.tenant().isBlank()
                    || key.type() == null || key.type().isBlank()
                    || key.externalId() == null || key.externalId().isBlank()) {
                throw new IllegalArgumentException("Invalid key");
            }
            return entries.computeIfAbsent(key, ignored -> ++sequence);
        }

        Long find(ExternalKey key) {
            return entries.get(key);
        }
    }

    public static void main(String[] args) {
        Registry registry = new Registry();
        String publicId = "550e8400-e29b-41d4-a716-446655440000";

        ExternalKey north =
                new ExternalKey("north", "Document", publicId);
        ExternalKey south =
                new ExternalKey("south", "Document", publicId);
        ExternalKey invoice =
                new ExternalKey("north", "Invoice", publicId);

        long northId = registry.allocate(north);
        long northAgain = registry.allocate(north);
        long southId = registry.allocate(south);
        long invoiceId = registry.allocate(invoice);

        System.out.println("north-id=" + northId);
        System.out.println("same-key=" + (northId == northAgain));
        System.out.println("south-id=" + southId);
        System.out.println("different-tenant=" + (northId != southId));
        System.out.println("invoice-id=" + invoiceId);
        System.out.println("different-type=" + (northId != invoiceId));
        System.out.println("missing="
                + registry.find(
                        new ExternalKey("north", "Document", "absent")));
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac AclIdentityDemo.java
java AclIdentityDemo
~~~

Stdout chính xác:

~~~text
north-id=1001
same-key=true
south-id=1002
different-tenant=true
invoice-id=1003
different-type=true
missing=null
~~~

Phân tích:
- Cùng key không tạo số mới.
- Cùng public UUID nhưng khác tenant tạo ID 1002, khác type tạo ID 1003.
- Lookup object không tồn tại trả null; ở policy thật trường hợp này **không được trở thành ALLOW**.
- Demo `Registry` không thread-safe, không persist, không có audit, không xác minh actor. Production phải dùng database unique constraint và transaction, kiểm tra tenant scope từ identity và không để request tùy ý cấp quyền bằng cách tạo mapping.

## 18. Kiểm thử tích hợp phải làm đủ một vòng ACL

Bảng kiểm thử tối thiểu:

| Trường hợp | Điều phải chứng minh |
|---|---|
| Long ID 42 trên Document | Tạo/read/update/delete ACL đúng |
| ID 42 trên Invoice | Không đọc nhầm ACL Document#42 |
| Hai tenant cùng local ID | Identity tách biệt, tenant sai bị DENY |
| UUID domain qua mapping Long | Lookup đúng identity ở tất cả path |
| String ID `"42"` và Long `42L` | Conversion/equality không gây silent mismatch |
| Java record chỉ có `id()` | Factory explicit vẫn hoạt động |
| JPA proxy/entity subclass | Type canonical không bị lệch |
| Resource chưa persist | Không tạo ACL bằng ID null |
| ACL/mapping không tồn tại | Fail closed; không tạo grant mặc định |
| ACL JDBC database unavailable | Không thực hiện thao tác nhạy cảm |
| Object delete/recreate | Không hồi sinh permission cũ ngoài ý muốn |
| Rename package/class | Quyền không bị mất hoặc nhân đôi |
| Parent ACL inheritance | Parent lookup tham chiếu đúng ACL row |
| Cache warm sau revoke | Không trả ALLOW stale |
| Batch read nhiều object | Đúng key và không N+1 quá mức |
| Chuyển tenant/owner | ACL, cache, mapping đồng bộ |
| API list/search/export | Không rò rỉ dữ liệu ngoài quyền |

### Unit test ObjectIdentity cơ bản

~~~java
ObjectIdentity document =
        new ObjectIdentityImpl(Document.class, 42L);
ObjectIdentity same =
        new ObjectIdentityImpl(Document.class, 42L);
ObjectIdentity invoice =
        new ObjectIdentityImpl(Invoice.class, 42L);

assertThat(document).isEqualTo(same);
assertThat(document).isNotEqualTo(invoice);
~~~

Đây là **snippet test Spring Security**, yêu cầu Spring ACL, class fixture và AssertJ/JUnit. Không chỉ dừng ở test equals: hành vi JDBC readback/cache còn tùy schema và version.

### Integration test round-trip

Với datasource và `AclService` thật:

1. Persist document và nhận ID ổn định.
2. Dựng ObjectIdentity qua factory canonical.
3. Gọi `MutableAclService.createAcl(identity)`.
4. Thêm một ACE READ cho SID có kiểm soát; `updateAcl(...)`.
5. Dùng `AclService.readAclById(identity)` để đọc lại.
6. Kiểm tra chủ thể được READ và chủ thể khác bị DENY theo evaluator/policy.
7. Thu hồi ACE, invalidate cache và xác nhận quyết định thay đổi.
8. Xóa ACL/domain object, bảo đảm key không được tái sử dụng và không để orphan.

Nếu chọn UUID/String trực tiếp, phải chạy trọn vòng trên **database dialect và Spring Security version production**, cả batch lookup và cold/warm cache. Một INSERT thành công vào cột `VARCHAR(36)` không đủ chứng minh tương thích.

## 19. Sai lầm thường gặp

**Sai lầm 1 — Thấy Serializable là mặc nhiên hỗ trợ UUID trong ACL JDBC.** Constructor Java chấp nhận UUID nhưng hạ tầng lookup và converter cần kiểm chứng. **Sửa:** dùng mapping Long hoặc POC đầy đủ.

**Sai lầm 2 — Dùng `acl_object_identity.id` làm domain ID.** Nhầm logical identifier với row PK. **Sửa:** phân biệt rõ ID trong factory, schema, log và migration.

**Sai lầm 3 — Dùng local ID 42 của mọi tenant trong một ACL store chung.** Collision key. **Sửa:** global surrogate Long hoặc isolation tenant chuẩn.

**Sai lầm 4 — Dùng `uuid.hashCode()` để ra Long.** Hash có thể va chạm, không phải ánh xạ duy nhất. **Sửa:** database sequence + unique mapping.

**Sai lầm 5 — Tạo identity bằng JPA runtime class/proxy.** Tên type có thể khác. **Sửa:** type canonical qua factory.

**Sai lầm 6 — Dùng slug/mã nghiệp vụ mutable.** Đổi tên gây orphan ACL hoặc lookup sai. **Sửa:** immutable synthetic ID.

**Sai lầm 7 — Đọc ACL bằng public UUID khi writer đã ghi bằng Long mapping.** Hai đường đọc/ghi không cùng identity. **Sửa:** resolver nhất quán.

**Sai lầm 8 — Thiếu ACL thì `permitAll`.** Fail-open. **Sửa:** private resource không có bằng chứng phải bị từ chối.

**Sai lầm 9 — Quên cache invalidation khi grant/revoke/tenant move.** Quyền cũ vẫn hoạt động. **Sửa:** thiết kế vòng đời đồng bộ và test warm cache.

**Sai lầm 10 — Chỉ thay SQL DDL để hỗ trợ ID mới.** Java conversion, batch query, object identity generator có thể chưa tương thích. **Sửa:** test end-to-end.

**Sai lầm 11 — Rename package mà không migrate ACL_CLASS.** Type string trong DB không đổi tự động. **Sửa:** migration có kiểm soát.

**Sai lầm 12 — Tạo ACL cho entity có ID chưa persist.** Null/tạm ID không ổn định. **Sửa:** cấp ACL key sau khi đã có domain identity bền vững.

## 20. Checklist chọn thiết kế

- [ ] Phân biệt domain PK, public ID, ACL identifier, ACL row PK.
- [ ] Identity gồm type + ID và không trùng trong kho ACL thực tế.
- [ ] ID không null, bất biến, không được tái sử dụng cho object khác.
- [ ] Đọc đúng Javadoc/schema `spring-security-acl` theo version.
- [ ] Với Long, đã kiểm tra path JDBC create/read/update/delete.
- [ ] Với UUID/String/composite, có mapping Long hoặc custom strategy đã test.
- [ ] Không cast, hash, truncate hoặc parse ID kiểu gây va chạm.
- [ ] Tenant scope tin cậy, không lấy trực tiếp từ client làm quyết định.
- [ ] Một identity factory chuẩn cho tất cả điểm đọc/ghi.
- [ ] Unique constraint ở mapping và chính sách idempotent khi retry.
- [ ] Chuyển type/package được migrate và invalidate cache.
- [ ] Không nhầm ID trong `acl_object_identity` với domain ID.
- [ ] Policy fail closed khi thiếu ACL/mapping/DB không khả dụng.
- [ ] Vòng đời create/delete/restore/copy/transfer được xử lý rõ.
- [ ] Test permission evaluator, JDBC round-trip, cache và multi-tenant.

**Kết luận:** Tính đúng của ACL phụ thuộc vào identity **ổn định và tương thích toàn tuyến**, không chỉ một kiểu Java compile được. Trong hạ tầng Spring Security ACL JDBC mặc định, dùng `Long` bất biến là hướng ít rủi ro. Với UUID, String hoặc composite ID, giữ kiểu domain khi có lợi, nhưng xây một **adapter bền vững và duy nhất** hoặc triển khai strategy tùy chỉnh được chứng minh bằng test. Luôn giữ tenant isolation và default DENY khi không xác minh được quyền.

## Tài liệu tham khảo

- [Spring Security – Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html): giả định long ID, `ObjectIdentityImpl` và JDBC ACL.
- [Spring Security – ObjectIdentityImpl API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/ObjectIdentityImpl.html): constructors, equality, getIdentifier và type.
- [Spring Security – BasicLookupStrategy API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/jdbc/BasicLookupStrategy.html): JDBC lookup/batch, SQL và conversion.
- [Spring Security – JdbcMutableAclService API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/jdbc/JdbcMutableAclService.html): create/update/delete ACL.
- [Spring Security – Database Schema](https://docs.spring.io/spring-security/reference/servlet/appendix/database-schema.html): ACL table DDL theo database dialect.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): hasPermission, method parameters và proxy.
