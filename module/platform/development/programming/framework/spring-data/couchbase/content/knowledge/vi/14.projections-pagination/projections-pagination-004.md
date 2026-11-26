# Khi nào kết quả cần giữ document ID và CAS

Trong **Spring Data Couchbase**, một danh sách thường chỉ cần vài trường để hiển thị. Nhưng nếu người dùng chọn một hàng để xem chi tiết, chỉnh sửa hoặc xác nhận thay đổi, ứng dụng phải biết **đang làm việc với document nào** và, trong những trường hợp cần tránh ghi đè thay đổi của người khác, **đang dựa trên phiên bản nào của document**.

Hai thông tin này có vai trò khác nhau:

- **Document ID** là khóa của document trong Couchbase, dùng để định danh chính xác bản ghi và thực hiện thao tác theo key.
- **CAS** (*Compare-And-Swap*) là token phiên bản do Couchbase cấp cho một trạng thái của document. Khi mutation kèm CAS, Couchbase chỉ chấp nhận thao tác nếu CAS hiện tại còn khớp với token đã đọc.

Bài thuộc chương **Chiếu và phân trang** của module **SPRING_DATA_COUCHBASE**. Nội dung liên hệ trực tiếp với document mapping, repository, `CouchbaseTemplate`, truy vấn SQL++, bucket/scope/collection, TTL, giao dịch và reactive API. Trọng tâm không chỉ là đưa `id`/`cas` vào projection, mà là **xác định lúc nào cần giữ, giữ ở đâu, và sử dụng thế nào để đúng về nhất quán và an toàn cập nhật**.

Sau bài học, bạn có thể:

1. Chọn luồng chỉ cần dữ liệu hiển thị, luồng cần ID và luồng cần cả ID lẫn CAS.
2. Phân biệt `@Id`, `@Version` của Spring Data với `META().id`, `META().cas` của SQL++.
3. Dùng CAS cho cập nhật có điều kiện bằng KV API, xử lý xung đột mà không vô tình ghi đè dữ liệu.
4. Trả ID và token phiên bản qua API mà không làm mất độ chính xác của CAS.
5. Chọn giữa query projection, KV get, sub-document operation, transaction và reactive API theo yêu cầu nhất quán.
6. Viết checklist kiểm thử cho cạnh tranh ghi, phân trang và document hết hạn TTL.

## 1. Ví dụ xuyên suốt: hai người chỉnh sửa cùng khách hàng

Ứng dụng quản lý khách hàng dùng bucket `shop`, scope `crm`, collection `customers`. Một document có key `customer::42` và body:

~~~json
{
  "fullName": "Trần Minh",
  "email": "minh@example.test",
  "active": true,
  "address": {
    "city": "Đà Nẵng"
  }
}
~~~

Màn hình danh sách chỉ hiển thị tên và email. Khi người dùng nhấn **Chỉnh sửa**, ứng dụng mở màn hình chi tiết. Giả sử:

- 09:00: A đọc hồ sơ khách hàng với CAS giả định `0xA1`.
- 09:01: B cũng đọc cùng hồ sơ với CAS `0xA1`.
- 09:02: B thay đổi email; Couchbase chấp nhận ghi và sinh CAS mới, giả định `0xB7`.
- 09:03: A gửi bản chỉnh sửa cũ, vẫn kèm CAS `0xA1`.

Nếu A ghi không có điều kiện, nội dung cũ của A có thể ghi đè thay đổi mới của B (**lost update**). Nếu A ghi kèm CAS `0xA1`, server so sánh với CAS hiện tại `0xB7` và **từ chối mutation**. A có thể đọc lại, hiển thị xung đột và cho người dùng quyết định cách hợp nhất.

Các giá trị `0xA1` và `0xB7` chỉ để minh họa; CAS thực tế là token do Couchbase sinh, không phải bộ đếm có ý nghĩa nghiệp vụ.

Điều kiện để luồng này hoạt động là ứng dụng giữ đồng thời:

- **ID:** `customer::42` để biết cập nhật document nào.
- **CAS từ đúng lần đọc:** để so sánh với trạng thái hiện tại khi ghi.

CAS không thay thế ID; ID không thay thế CAS.

## 2. Bảng quyết định: khi nào cần ID, khi nào cần CAS?

| Tình huống sử dụng | Document ID | CAS | Vì sao |
| --- | --- | --- | --- |
| Danh sách chỉ hiển thị thông tin, không liên kết đến bản ghi | Không bắt buộc | Không | Chỉ cần field phục vụ hiển thị |
| Danh sách có nút xem chi tiết, chọn/xóa/sửa từng hàng | Cần | Tùy luồng ghi | ID xác định mục tiêu cho thao tác sau |
| Phân trang dùng document key làm khóa phân xử thứ tự | Cần trong logic cursor | Không | Key giúp tạo thứ tự ổn định khi tên trùng |
| Đọc chi tiết rồi gửi bản chỉnh sửa với optimistic locking | Cần | Cần | So CAS khi ghi để phát hiện thay đổi đồng thời |
| Tác vụ ghi đè có chủ ý, không yêu cầu so phiên bản | Cần | Không bắt buộc | Nghiệp vụ chấp nhận chính sách ghi mới nhất thắng |
| Cập nhật có điều kiện với `@Version` trong Spring Data | Cần | Được quản lý qua version của entity | Framework dùng token CAS trong cơ chế optimistic locking |
| Một query báo cáo `COUNT`, `SUM` theo nhóm | Thường không | Không | Báo cáo trả số liệu tổng hợp, không sửa từng document |
| Cập nhật nhiều document cần tính nguyên tử theo nghiệp vụ | Cần định danh các document | CAS riêng lẻ chưa đủ | Cần đánh giá transaction và điều kiện liên document |
| Hiển thị lịch sử chỉnh sửa/audit | Tùy thiết kế | CAS không đủ | CAS không thay audit log hay business version |

**Nguyên tắc:** thêm ID khi ứng dụng phải xác định lại document; thêm CAS khi kết quả đọc sẽ là **điểm xuất phát của một thao tác ghi cần phát hiện xung đột**. Không đưa CAS vào mọi danh sách chỉ vì “có thể sẽ hữu ích”.

## 3. Document ID là gì trong Couchbase?

Document được nhận diện bằng tổ hợp keyspace (bucket/scope/collection) và document key. Trong ví dụ này:

~~~text
Bucket:     shop
Scope:      crm
Collection: customers
Document key: customer::42
~~~

`customer::42` là **document ID trong collection đã chọn**. Khi ứng dụng có thể truy cập nhiều collection, chỉ giữ chuỗi key mà không biết collection là chưa đủ để định tuyến thao tác. Đường truy cập cần có ngữ cảnh collection do service/repository xác định.

### 3.1. ID có nhất thiết nằm trong JSON body không?

Không. Couchbase lưu document key độc lập với body JSON. Ví dụ body:

~~~json
{
  "fullName": "Trần Minh",
  "email": "minh@example.test"
}
~~~

Nếu body không có field `id` thì câu SQL++ `c.id` không thể tự lấy document key. Muốn lấy key trong truy vấn SQL++, sử dụng:

~~~sql
SELECT META(c).id AS id,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE;
~~~

Một row có dạng:

~~~json
{
  "id": "customer::42",
  "fullName": "Trần Minh",
  "email": "minh@example.test"
}
~~~

`META(c).id` là metadata key; `AS id` đặt tên trường trong **kết quả truy vấn** để khớp DTO hoặc interface projection. Nếu body cũng chứa field `id`, nó có thể **khác** document key. Không nhầm hai loại ID.

### 3.2. ID trong Spring Data entity

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;

@Document
public class Customer {
    @Id
    private String id;

    private String fullName;
    private String email;

    // Getter/setter hoặc constructor phù hợp với mapping.
}
~~~

`@Id` đánh dấu thuộc tính đại diện cho document key. Với repository:

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface CustomerRepository
        extends CouchbaseRepository<Customer, String> {
}
~~~

Lời gọi `repository.findById("customer::42")` định danh chính xác một document qua key trong collection repository quản lý. Nếu code phải tạo đường dẫn REST `/customers/{id}` hoặc link chi tiết từ một hàng danh sách, cần bảo toàn ID để dùng lại.

## 4. CAS là gì và không phải là gì?

CAS là token của **trạng thái document tại thời điểm đọc**. Mỗi mutation thành công làm Couchbase cấp CAS mới. Giá trị CAS được so sánh theo **bằng/khác**, không nên được suy diễn thành ngày giờ, số lần chỉnh sửa hay thứ tự toàn cục giữa những document.

CAS giúp giải quyết một câu hỏi rất cụ thể:

> “Document này có còn đúng trạng thái mà tôi đã đọc trước khi bắt đầu thay đổi hay không?”

CAS **không** phải:

- Tên định danh document (đó là ID).
- Trường nghiệp vụ như `updatedAt` hay `revisionNumber` tự quản lý.
- Thời điểm cập nhật hoặc bằng chứng lịch sử thay đổi.
- Cơ chế phân quyền người dùng.
- Thay thế cho transaction khi bất biến nghiệp vụ liên quan nhiều document.
- Giá trị có thể so sánh `>`/`<` để kết luận bản nào mới hơn trong ứng dụng.

### 4.1. CAS tồn tại ở metadata

Với Couchbase Java SDK, KV get cung cấp CAS qua `GetResult.cas()`:

~~~java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.GetResult;

Collection customers = bucket.scope("crm").collection("customers");

GetResult result = customers.get("customer::42");
long cas = result.cas();
CustomerBody body = result.contentAs(CustomerBody.class);
~~~

`CustomerBody` là kiểu chứa các field JSON tương ứng với body, không cần chứa CAS. Giá trị `cas` thuộc về result metadata của lần đọc. Ở Java, SDK biểu diễn CAS bằng `long`; hãy xem nó như **token bit**, không áp dụng phép tính số học.

Cũng có thể đọc metadata CAS trong SQL++:

~~~sql
SELECT META(c).id AS id,
       META(c).cas AS cas,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE;
~~~

Tuy nhiên, **kiểu và độ chính xác khi CAS đi qua SQL++, JSON serializer và client** cần được kiểm chứng trên phiên bản Couchbase Server/SDK thực tế. Tránh đọc CAS qua JavaScript `Number` hoặc kiểu số có thể mất độ chính xác rồi dùng làm điều kiện ghi. Với quy trình chỉnh sửa một document, thường dễ kiểm soát hơn khi lấy CAS bằng KV get trực tiếp.

### 4.2. CAS là token riêng cho document

Giá trị CAS phải đi cùng **đúng key và collection** của document mà nó mô tả. Một token của `customer::42` không thể dùng như phiên bản hợp lệ cho `customer::43`. Nếu chuyển sang document khác, hoặc truy vấn lần khác và nhận CAS mới, cần cập nhật cặp (document identity, CAS) trong luồng nghiệp vụ.

## 5. Optimistic locking bằng Couchbase Java SDK

### 5.1. Luồng đọc rồi ghi có điều kiện

Giả sử service trả một form chỉnh sửa gồm `id`, `fullName`, `email`, cùng token phiên bản. Khi người dùng lưu, backend thực hiện thao tác mutation kèm CAS đã đọc.

Ví dụ trực tiếp bằng KV API:

~~~java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.GetResult;
import com.couchbase.client.java.kv.MutationResult;

import static com.couchbase.client.java.kv.ReplaceOptions.replaceOptions;

// Collection đã được lấy từ bucket/scope và quản lý bởi ứng dụng.
public void updateEmail(
        Collection customers,
        String id,
        String newEmail) {

    GetResult current = customers.get(id);

    CustomerBody updated =
            current.contentAs(CustomerBody.class);
    updated.setEmail(newEmail);

    MutationResult saved = customers.replace(
            id,
            updated,
            replaceOptions().cas(current.cas()));

    long nextCas = saved.cas();
    // Trả version token mới nếu client cần tiếp tục chỉnh sửa.
}
~~~

Đây là **ví dụ read-modify-write trong cùng một lời gọi service**. Điểm quan trọng là tham số `replaceOptions().cas(current.cas())`. Nếu một thao tác khác thay document **giữa `get` và `replace`**, Couchbase từ chối `replace` do CAS không khớp.

Đoạn mẫu trên không giải quyết toàn bộ trường hợp “người dùng giữ form trong nhiều phút”, bởi nó vừa **đọc lại CAS mới nhất** ngay khi nhận request. Nếu payload từ form cũ ghi đè toàn bộ body theo CAS vừa đọc, ứng dụng vẫn có thể vô tình ghi giá trị cũ của form. Với biểu mẫu chỉnh sửa kéo dài, CAS cần đến từ **lần đọc ban đầu tạo form**, không phải được thay bằng CAS mới khi submit.

### 5.2. Đúng cách đối với form nhiều request

Lượt đọc ban đầu:

~~~java
public record CustomerEditView(
        String id,
        String fullName,
        String email,
        String versionToken
) {}

public CustomerEditView loadForEdit(
        Collection customers, String id) {

    GetResult result = customers.get(id);
    CustomerBody body = result.contentAs(CustomerBody.class);

    return new CustomerEditView(
            id,
            body.getFullName(),
            body.getEmail(),
            Long.toUnsignedString(result.cas()));
}
~~~

Token được biểu diễn thành **chuỗi thập phân không dấu**. Cách này tránh mất độ chính xác khi đi qua JSON/JavaScript và giữ CAS dưới dạng chuỗi opaque cho client.

Khi gửi form đã chỉnh sửa trở lại:

~~~java
public long saveEditedCustomer(
        Collection customers,
        String id,
        String versionToken,
        CustomerBody editedBody) {

    long expectedCas = Long.parseUnsignedLong(versionToken);

    MutationResult saved = customers.replace(
            id,
            editedBody,
            replaceOptions().cas(expectedCas));

    return saved.cas();
}
~~~

Lưu ý:

- `Long.parseUnsignedLong(...)` giải mã token kiểu thập phân không dấu được tạo bằng `Long.toUnsignedString(...)`. Đầu vào cần được xác thực và bắt lỗi `NumberFormatException`.
- `editedBody` phải được tạo bằng validation nghiệp vụ; không tin tưởng mọi field client gửi, nhất là trường được server quản lý.
- `replace` thay body document. Nếu client chỉ biết một phần field, **không gửi projection thiếu trường như toàn bộ document** vì có thể làm mất dữ liệu khi replace thành công.
- Mọi thao tác có lỗi CAS mismatch cần được xử lý riêng với lỗi không tồn tại document, lỗi quyền và lỗi kết nối.
- `MutationResult.cas()` là token mới sau mutation thành công; nếu client tiếp tục chỉnh sửa, cần cập nhật token mới.

### 5.3. Xử lý khi CAS mismatch

Trong Java SDK, xung đột CAS có thể được báo bằng một lỗi như `CasMismatchException` trên đường mutation phù hợp với SDK. Ứng dụng cần phân biệt lỗi này với:

- `DocumentNotFoundException`: document đã bị xóa hoặc hết hạn.
- Lỗi dữ liệu đầu vào/validation.
- Timeout, kết nối hoặc thiếu quyền.

Khi gặp CAS mismatch, không nên **tự động đọc CAS mới rồi ghi lại cùng payload cũ**. Làm vậy vô hiệu hóa ý nghĩa optimistic locking.

Phản hồi hợp lý cho giao diện:

1. Thông báo document đã được thay đổi trong lúc người dùng chỉnh sửa.
2. Đọc phiên bản hiện tại và hiển thị điểm khác nhau nếu có.
3. Cho người dùng tải lại, hủy hoặc chọn cách hợp nhất.
4. Nếu lưu lại sau khi người dùng xác nhận, dùng CAS **mới gắn với trạng thái đã được xem lại**.

Trong API HTTP, xung đột phiên bản thường có thể biểu diễn bằng `412 Precondition Failed` khi dùng `If-Match` hoặc `409 Conflict` nếu hợp đồng API dùng version field trong body. Quy tắc phải nhất quán và có kiểm thử.

## 6. Optimistic locking bằng Spring Data `@Version`

Khi làm việc qua entity/repository, Spring Data Couchbase hỗ trợ optimistic locking theo cơ chế của Spring Data: một thuộc tính được đánh dấu `@Version` có thể đóng vai trò lưu CAS cho entity.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;

@Document
public class Customer {
    @Id
    private String id;

    @Version
    private Long version;

    private String fullName;
    private String email;

    // Constructor/accessor.
}
~~~

Với cấu hình và phiên bản Spring Data Couchbase hỗ trợ đúng đường lưu này, luồng điển hình là:

~~~java
Customer current = repository.findById("customer::42")
        .orElseThrow();

current.setEmail("new@example.test");

Customer saved = repository.save(current);
// Framework sử dụng version/CAS của entity để kiểm tra cập nhật.
~~~

Giải thích:

- `@Id` định danh document.
- `@Version` cho framework biết property nào dùng để quản lý phiên bản theo CAS.
- Khi đọc entity, framework cần materialize cả ID và metadata CAS phù hợp.
- Khi lưu entity đã đọc, mutation được thực hiện với điều kiện version tương ứng; nếu document đã bị sửa, việc lưu có thể bị từ chối và được biểu diễn thành lỗi optimistic locking của tầng Spring Data.
- Sau khi lưu thành công, giá trị version trên đối tượng/result theo API của framework cần được lấy lại nếu ứng dụng định dùng cho một lần ghi tiếp theo.

**Điều kiện quan trọng:** cách framework gán giá trị version, hành vi `save` đối với entity mới và kiểu exception cụ thể có thể phụ thuộc phiên bản Spring Data Couchbase. Hãy kiểm thử tích hợp trên dependency và Couchbase Server đang sử dụng, thay vì giả định mọi kiểu số hoặc mọi cách materialize đều hợp lệ.

### Không dùng partial entity như một thực thể hoàn chỉnh

Nếu `SELECT` thủ công chỉ lấy `id`, `fullName` và `version` rồi ánh xạ vào `Customer`, các field body khác có thể không được materialize. `repository.save(partialCustomer)` có nguy cơ ghi đè hoặc loại bỏ dữ liệu khác dù CAS hợp lệ.

**Quy tắc thực tế:** với repository `save`, ưu tiên entity đầy đủ được đọc theo đường mapping chính thức; với lệnh cập nhật một số path, cân nhắc custom repository hoặc KV sub-document mutation. Projection danh sách có thể chỉ dùng để định danh hoặc mở form, không nên tự trở thành đối tượng để save.

## 7. SQL++ projection có cần giữ CAS không?

Phân biệt hai loại truy vấn:

### Danh sách chỉ để xem hoặc điều hướng

~~~sql
SELECT META(c).id AS id,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
ORDER BY c.fullName, META(c).id
LIMIT 20;
~~~

Chỉ lấy ID nếu cần nút xem chi tiết/chỉnh sửa. **Không cần CAS** nếu mỗi lần bấm chỉnh sửa sẽ đọc lại document bằng KV get và lấy version token mới.

### Danh sách cho phép cập nhật ngay trên từng hàng

~~~sql
SELECT META(c).id AS id,
       META(c).cas AS cas,
       c.fullName AS fullName,
       c.active AS active
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
ORDER BY c.fullName, META(c).id
LIMIT 20;
~~~

Nếu tính năng hỗ trợ đổi trạng thái `active` ngay từ danh sách và muốn từ chối thay đổi khi hàng đã bị sửa, ứng dụng có thể cần CAS tương ứng với hàng được hiển thị. Nhưng phải kiểm tra kỹ **representation của `META(c).cas` qua SQL++ và JSON** trước khi sử dụng để ghi có điều kiện.

Trong nhiều hệ thống, lựa chọn đơn giản và chặt chẽ hơn là:

1. Query danh sách trả ID và các trường hiển thị.
2. Khi người dùng định sửa, gọi KV get theo ID để lấy CAS chuẩn từ `GetResult.cas()`.
3. Xây payload từ dữ liệu được phép sửa và mutation kèm CAS đó.

Nếu UI chỉnh sửa dựa trên **dữ liệu hiển thị từ trước** và muốn đảm bảo chính trạng thái cũ đó vẫn còn nguyên, bước KV get lúc submit không được tự thay thế token phiên bản của bản đọc ban đầu. Hãy thiết kế rõ hành vi làm mới hoặc từ chối xung đột, thay vì vô tình nới lỏng điều kiện.

## 8. Một mô hình REST API giữ ID và CAS

Giả sử API đọc chi tiết:

~~~http
GET /customers/customer::42 HTTP/1.1
Accept: application/json
~~~

Response có thể có body:

~~~json
{
  "id": "customer::42",
  "fullName": "Trần Minh",
  "email": "minh@example.test"
}
~~~

Và một token phiên bản opaque, chẳng hạn qua header `ETag`:

~~~http
ETag: "18446744073709551600"
~~~

Chuỗi trên chỉ minh họa cách biểu diễn token; không phải CAS thực tế của ví dụ. Nếu dùng CAS để tạo ETag, backend cần thiết kế cách encode/decode đồng nhất và đảm bảo ETag đại diện phù hợp với representation của resource theo hợp đồng HTTP.

Client gửi bản chỉnh sửa cùng precondition:

~~~http
PUT /customers/customer::42 HTTP/1.1
If-Match: "18446744073709551600"
Content-Type: application/json

{"fullName": "Trần Minh", "email": "new@example.test"}
~~~

Backend kiểm tra precondition và gọi mutation với CAS tương ứng, không chỉ so sánh ở Java rồi thực hiện write vô điều kiện. Việc kiểm tra CAS phải diễn ra **ngay trong thao tác ghi** để tránh race condition giữa bước kiểm tra và bước cập nhật.

Nếu CAS thay đổi, trả `412 Precondition Failed` và hướng dẫn client tải bản mới. Không nên tự động chuyển mọi mismatch thành `200 OK` bằng cách ghi đè.

### Vì sao không nên trả CAS dưới dạng số JSON?

CAS là token có độ rộng lớn. Ở Java, SDK thường biểu diễn dưới dạng `long`; trong JavaScript, kiểu `Number` chỉ biểu diễn chính xác mọi số nguyên tới `2^53 - 1`. Nếu biến CAS thành number trong body rồi chuyển qua trình duyệt, token có nguy cơ bị làm tròn và điều kiện ghi bị sai.

Dùng **string opaque** ở ranh giới API, ví dụ `versionToken` hoặc `ETag` đã chuẩn hóa, và giải mã phía backend. Không áp dụng phép toán `versionToken + 1`, không dùng CAS để sắp xếp các revision.

### CAS không phải cơ chế phân quyền

Kẻ không được phép sửa vẫn không được quyền ghi dù biết ID và CAS. Backend phải kiểm tra authorization, xác thực dữ liệu và phạm vi collection/tenant trước khi mutation. Không xem CAS như mật khẩu bí mật hay token bảo mật thay quyền truy cập.

## 9. CAS và KV sub-document: cập nhật một vài field

Một lựa chọn hiệu quả là dùng KV **sub-document mutation** khi chỉ cần sửa một field.

Ví dụ:

~~~java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.MutateInResult;
import com.couchbase.client.java.kv.MutateInSpec;
import java.util.List;

import static com.couchbase.client.java.kv.MutateInOptions.mutateInOptions;

public MutateInResult updateEmailField(
        Collection collection,
        String id,
        String email,
        long expectedCas) {

    return collection.mutateIn(
            id,
            List.of(MutateInSpec.upsert("email", email)),
            mutateInOptions().cas(expectedCas));
}
~~~

Trong luồng này:

- ID cho biết document cần cập nhật.
- CAS ràng buộc toàn bộ trạng thái document mà client đã đọc.
- `MutateInSpec.upsert("email", email)` sửa một path, không cần gửi lại cả body.
- Tác vụ vẫn thất bại nếu CAS cũ không khớp, dù một luồng khác chỉ sửa field không liên quan. Đây là hành vi đúng nếu nghiệp vụ yêu cầu kiểm tra **mọi thay đổi trên document**.

Nếu nghiệp vụ cho phép hai thay đổi độc lập ở các field khác nhau, có thể cân nhắc atomic sub-document operation **không kèm CAS**, nhưng phải có quy tắc xử lý xung đột theo field. Không bỏ CAS chỉ vì muốn giảm lỗi nếu thật ra mọi thay đổi đều phải được người dùng xác nhận.

### Đọc vài trường kèm CAS

Với SDK, `lookupIn` trả cả các path được chọn và metadata CAS:

~~~java
import com.couchbase.client.java.kv.LookupInResult;
import com.couchbase.client.java.kv.LookupInSpec;
import java.util.List;

LookupInResult result = collection.lookupIn(
        "customer::42",
        List.of(
                LookupInSpec.get("fullName"),
                LookupInSpec.get("email")));

String fullName = result.contentAs(0, String.class);
String email = result.contentAs(1, String.class);
long cas = result.cas();
~~~

Đây là lựa chọn hữu ích khi **đã có ID**, chỉ cần một số field và muốn nhận CAS mà không phải chạy SQL++ theo predicate. Cần xử lý trường thiếu, sai kiểu và exception của từng path theo SDK.

## 10. Reactive API có thay đổi yêu cầu giữ CAS không?

Không. Reactive chỉ thay đổi cách sắp xếp và tiêu thụ các lời gọi bất đồng bộ; nguyên tắc **đọc trạng thái + giữ CAS + mutation có điều kiện** vẫn như cũ.

Ví dụ minh họa bằng reactive KV API của Couchbase Java SDK:

~~~java
import com.couchbase.client.java.ReactiveCollection;
import com.couchbase.client.java.kv.ReplaceOptions;
import reactor.core.publisher.Mono;

public Mono<Long> changeEmail(
        ReactiveCollection collection,
        String id,
        String newEmail) {

    return collection.get(id)
            .flatMap(result -> {
                CustomerBody body =
                        result.contentAs(CustomerBody.class);
                body.setEmail(newEmail);

                return collection.replace(
                        id,
                        body,
                        ReplaceOptions.replaceOptions()
                                .cas(result.cas()));
            })
            .map(mutationResult -> mutationResult.cas());
}
~~~

Mẫu chỉ mô tả **thao tác đọc và cập nhật liền nhau**; không đại diện cho form người dùng giữ lâu. Trong hệ thống thực tế cần thêm lỗi/xung đột và kiểm soát timeout.

Không nên dùng `block()` trên event-loop WebFlux. Khi người dùng gửi version token từ một request cũ, reactive mutation vẫn phải dùng **CAS do client giữ hợp lệ từ bản đọc đó**, không lén thay bằng CAS vừa fetch nếu mục tiêu là phát hiện stale form.

## 11. CAS, index và tính mới của dữ liệu

SQL++ qua Query Service có thể dùng secondary index, trong khi KV get theo key đi vào đường truy cập khác. Một truy vấn danh sách có thể:

- Trả một trạng thái đã được index quan sát với chính sách scan consistency hiện tại.
- Kết thúc trước khi một thay đổi mới được index nhìn thấy.
- Cho kết quả không còn mới ngay tại thời điểm người dùng chọn sửa.

Giữ CAS trong kết quả SQL++ **không biến cả danh sách thành snapshot bất biến**. Khi dùng CAS để mutation, server vẫn kiểm tra trên trạng thái document hiện tại: nếu đã thay đổi, CAS mismatch giúp từ chối thao tác stale.

Nếu nghiệp vụ yêu cầu **read-your-own-write** sau khi cập nhật rồi lập tức truy vấn danh sách, cần xem chính sách query consistency của Spring Data/SDK. Đây là vấn đề độc lập với việc projection có ID/CAS hay không.

### Covering index không quyết định tính đúng CAS

Một query chỉ trả `id`, `cas` và vài field có thể cần đọc document hoặc có thể được tối ưu bởi index tùy kế hoạch. Không tự kết luận rằng thêm `META(c).cas` sẽ giúp query rẻ hoặc một secondary index tự cấp version token thích hợp cho mọi mutation.

Dùng `EXPLAIN` để xem index, `Fetch`, `covers`; đo latency, số hàng quét và kích thước response. Với thao tác cần lấy CAS của một document đã biết key, KV get/lookupIn thường là đường truy cập trực tiếp hơn.

## 12. CAS và TTL: document có thể biến mất

Couchbase hỗ trợ **TTL/expiration**. Nếu document hết hạn giữa lúc đọc và lúc ghi:

- ID vẫn là key mà ứng dụng biết, nhưng document có thể đã bị xóa khỏi trạng thái khả dụng.
- CAS đọc trước đó không thể bảo đảm document còn tồn tại.
- Mutation kiểu replace thường phải xử lý trường hợp **not found** ngoài CAS mismatch.

Không coi `DocumentNotFoundException` như một lỗi “CAS sai” đơn thuần. Với form chỉnh sửa tài liệu đã hết hạn, ứng dụng có thể hướng dẫn người dùng tạo bản mới hoặc liên hệ quản trị, tùy nghiệp vụ.

Nếu có cơ chế xóa rồi tạo document mới với cùng key, **cặp ID + CAS cũ** vẫn không được phép mặc nhiên cập nhật bản mới. Điều kiện CAS phục vụ đúng mục đích ngăn ghi dựa trên trạng thái đã lỗi thời.

## 13. CAS không thay thế Couchbase transaction

CAS hữu ích cho **một document mutation** hoặc cho những thao tác mà ứng dụng kiểm soát rõ từng điều kiện.

Ví dụ nghiệp vụ “chuyển 100 điểm từ ví A sang ví B” liên quan hai document. Dù có CAS trên cả A và B, tự thực hiện hai lệnh replace riêng vẫn có thể có tình huống:

1. Trừ điểm ở A thành công.
2. Ghi cộng điểm ở B thất bại do xung đột hoặc mất kết nối.
3. Tổng điểm không còn như yêu cầu nghiệp vụ nếu không có cơ chế điều phối khôi phục.

Với bất biến cần tính nguyên tử trên nhiều document, phải đánh giá **Couchbase Transactions** và API transaction của SDK/Spring Data tương ứng. Transaction có cơ chế quản lý xung đột/rollback/retry riêng; không lấy CAS riêng lẻ làm lời hứa về tính nguyên tử liên document.

CAS cũng không thay thế log sự kiện hay audit trail. Nếu cần biết **ai thay đổi, thay đổi gì, lúc nào**, hãy thiết kế audit/event model riêng.

## 14. ID và CAS trong phân trang

Danh sách thường cần thứ tự ổn định khi nhiều document trùng tên:

~~~sql
SELECT META(c).id AS id,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
ORDER BY c.fullName, META(c).id
LIMIT 20 OFFSET 0;
~~~

Tại đây:

- `id` phục vụ điều hướng và là khóa phụ khi sắp xếp.
- `cas` không tham gia thứ tự trang vì CAS không phải khóa sắp xếp nghiệp vụ ổn định.
- Với **keyset pagination**, token trang sau có thể chứa cặp (`lastFullName`, `lastDocumentId`) được encode phù hợp; không dùng CAS như cursor thứ tự.
- Những lần ghi đồng thời vẫn có thể thay đổi vị trí của document giữa các trang; thứ tự theo ID không tự đảm bảo snapshot trên nhiều request.

Nếu danh sách có chức năng **chỉnh sửa trực tiếp từng dòng**, có thể cần thêm version token cho mỗi hàng; đây là nhu cầu của **tính năng chỉnh sửa**, không phải của phân trang.

## 15. Thiết kế projection cho ba loại màn hình

### 15.1. Danh sách đọc đơn thuần

~~~java
public interface CustomerListView {
    String getId();
    String getFullName();
    String getEmail();
}
~~~

ID có thể được trả để tạo đường dẫn chi tiết; không cần `getVersion()`. Nếu danh sách là thống kê hoàn toàn không tương tác theo document, ngay cả ID cũng có thể bỏ.

### 15.2. Màn hình chỉnh sửa

~~~java
public record CustomerEditDto(
        String id,
        String fullName,
        String email,
        String versionToken
) {}
~~~

Trong mô hình an toàn, backend có thể lấy document và CAS bằng KV get rồi ánh xạ sang DTO. `versionToken` là **chuỗi opaque** để đưa qua HTTP, không nhất thiết trùng với field tên `cas` trong Couchbase.

### 15.3. Endpoint mutation

~~~java
public record CustomerUpdateRequest(
        String fullName,
        String email,
        String versionToken
) {}
~~~

ID có thể lấy từ path `/customers/{id}`; không cần lặp trong body. Backend kiểm tra quyền, validation, version token rồi thực hiện mutation có điều kiện.

Không dùng `CustomerListView` hoặc `CustomerEditDto` như entity đầy đủ cho `save`. Projection là hợp đồng đọc/ghi dữ liệu ở ranh giới ứng dụng; thao tác persistence cần một đường riêng có kiểm soát field và CAS.

## 16. Lỗi thường gặp và cách khắc phục

| Tình huống | Nguyên nhân phổ biến | Cách xử lý |
| --- | --- | --- |
| Query trả `id = null` | Chỉ chọn `c.id` nhưng ID là document key | Dùng `META(c).id AS id` |
| Không biết record nào cần cập nhật | Projection danh sách bỏ ID dù có nút sửa | Bổ sung document ID hoặc đường định danh ổn định |
| CAS bị sai sau khi đi qua frontend | CAS được serialize thành JSON number và mất chính xác | Trả token dạng string, parse an toàn ở backend |
| CAS mismatch bị tự động retry bằng CAS mới | Logic đọc lại rồi ghi payload cũ vô điều kiện | Hiển thị xung đột/merge theo quy tắc nghiệp vụ |
| Thay đổi không liên quan cũng gây mismatch | CAS bảo vệ **toàn document** | Chấp nhận conflict hoặc thiết kế atomic field update phù hợp |
| Partial DTO làm mất dữ liệu | Dùng `replace` với body chỉ chứa vài field | Đọc entity đầy đủ hoặc dùng sub-document mutation |
| Document biến mất giữa hai request | TTL/xóa document | Xử lý riêng `DocumentNotFoundException` |
| Sau ghi vẫn query ra giá trị cũ | Query scan consistency/index chưa phản ánh thay đổi | Cấu hình consistency hoặc KV read theo key |
| Dùng CAS cho lịch sử sửa đổi | CAS không chứa ai/khi nào/lý do | Lưu audit log/version nghiệp vụ riêng |
| Cập nhật hai document bị lệch | Hai mutation CAS riêng không nguyên tử | Transaction hoặc thiết kế nhất quán liên document |

### Hai câu hỏi phải trả lời trước khi đưa CAS vào response

**Ai sẽ dùng CAS?** Nếu không có đường mutation nào dùng token, gửi CAS trong mọi API chỉ làm tăng coupling và công sức bảo trì.

**CAS đến từ lần đọc nào?** Token cần gắn với chính dữ liệu người dùng nhìn thấy/ra quyết định. Nếu mỗi lần submit lại đọc CAS mới rồi ghi payload cũ, ứng dụng có thể không phát hiện được form đã lỗi thời.

## 17. Quy trình thiết kế và kiểm thử tích hợp

1. **Phân loại endpoint:** hiển thị, điều hướng, chỉnh sửa, xóa, tổng hợp hoặc cập nhật nhiều document.
2. **Chọn định danh:** lấy ID từ `@Id` hoặc `META().id`; xác định đúng bucket/scope/collection.
3. **Quyết định chính sách xung đột:** có cần từ chối ghi khi document thay đổi từ lúc đọc không? Nếu có, dùng CAS.
4. **Chọn đường đọc:** repository entity với `@Version` hoặc KV `get`/`lookupIn` cho form chỉnh sửa; SQL++ projection cho list/report khi phù hợp.
5. **Chuyển token qua API:** dùng string/ETag; bảo đảm encode/decode không làm tròn, không suy diễn CAS là số thứ tự.
6. **Chọn đường mutation:** repository save có optimistic locking hoặc SDK replace/mutateIn với CAS; không dùng partial entity để replace toàn bộ.
7. **Xử lý lỗi:** phân biệt CAS mismatch, document not found, validation, quyền truy cập và lỗi mạng.
8. **Thử cạnh tranh thực sự:** hai phiên đọc cùng CAS, B ghi thành công, A phải thất bại theo chính sách; xác minh dữ liệu B không bị ghi đè.
9. **Thử trạng thái biên:** document xóa/TTL, CAS sau mutation, field thiếu/null, cùng ID trong collection khác.
10. **Thử consistency và hiệu năng:** query sau ghi, `EXPLAIN` khi dùng SQL++, độ trễ và khối lượng dữ liệu trả.
11. **Thử frontend:** round-trip token CAS có giá trị lớn qua JSON/browser, xác minh token còn nguyên.

### Kịch bản kiểm thử cạnh tranh tối thiểu

~~~text
Given  document customer::42 tồn tại
When   session A get -> CAS_A
And    session B get -> CAS_B (cùng giá trị CAS_A)
And    B replace với CAS_B -> thành công, tạo CAS_B2
And    A replace với CAS_A -> bị từ chối do mismatch
Then   document cuối giữ thay đổi của B
And    response gửi A thể hiện xung đột phiên bản
~~~

Kiểm thử này phải chạy bằng Couchbase thật trong môi trường tích hợp tương thích; mock repository thường không chứng minh server đã thực hiện so CAS đúng cách.

## 18. Bài tập áp dụng

Thiết kế chức năng **“Đổi email khách hàng”** theo hai hướng:

**Hướng A — Spring Data repository:** entity có `@Id` và `@Version`, đọc entity, thay email, gọi `save`; tạo bài test hai phiên đọc để xác nhận optimistic locking.

**Hướng B — Couchbase Java SDK:** `get(id)` trả `GetResult.cas()`; API trả `versionToken` dạng string; request cập nhật gửi lại token; backend `replace` hoặc `mutateIn` kèm CAS và bắt conflict.

Sau đó thử mở rộng:

- Một bảng danh sách chỉ có nút **Xem chi tiết**: nên trả ID, có cần CAS không?
- Một bảng có nút **Bật/Tắt trạng thái** ngay mỗi dòng: CAS nên lấy từ lúc tải bảng hay đọc lại khi bấm? Hãy chọn một chính sách rõ ràng về phát hiện thay đổi xảy ra từ khi người dùng nhìn thấy trạng thái.
- Hai người cùng chỉnh sửa hai field khác nhau: chính sách CAS toàn document có phù hợp không?
- Document hết hạn TTL trước khi submit: API trả lỗi gì và UI hiển thị thế nào?
- Hai collection có key `customer::42`: ứng dụng định tuyến thế nào để không sửa nhầm document?

### Câu hỏi tự kiểm tra

1. Vì sao projection cho danh sách có link chi tiết thường cần ID dù không cần CAS?
2. CAS dùng phép so sánh nào trong mutation, và vì sao không nên coi CAS là timestamp?
3. Trong SQL++, `META(c).id` khác `c.id` thế nào?
4. Vì sao đọc lại CAS mới ở lúc submit có thể vô hiệu hóa việc phát hiện form stale?
5. Khi nào `@Version` phù hợp hơn tự truyền CAS qua KV SDK?
6. Vì sao không nên dùng DTO chỉ có ba field để `replace` toàn bộ document?
7. CAS từ SQL++ đi qua JavaScript có nguy cơ gì nếu serialize thành JSON number?
8. Vì sao hai mutation CAS thành công từng phần chưa đảm bảo tính nguyên tử cho giao dịch nhiều document?

## 19. Tài liệu chính thức để đối chiếu phiên bản

- [Spring Data Couchbase — Entity Modeling](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): ánh xạ `@Id`, version/CAS và entity metadata.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): cách repository xử lý truy vấn và entity.
- [Couchbase Java SDK — Concurrent Document Mutations](https://docs.couchbase.com/java-sdk/current/howtos/concurrent-document-mutations.html): CAS, optimistic concurrency và retry.
- [Couchbase Java SDK — Sub-Document Operations](https://docs.couchbase.com/java-sdk/current/howtos/subdocument-operations.html): `lookupIn` và `mutateIn`, thao tác theo path.
- [Couchbase Server SQL++ — Metadata Functions](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/metafun.html): ý nghĩa của `META()`.
- [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): query parameters, kiểu kết quả và scan consistency.

Tên API, hành vi converter và kiểu exception cần đối chiếu theo **Couchbase Server, Java SDK và Spring Data Couchbase được khóa trong dự án**; bước Content QA chuyên môn của tài liệu có thể kiểm chứng thêm các trường hợp theo phiên bản.

> **Ghi nhớ:** **ID trả lời “document nào?”; CAS trả lời “có còn đúng trạng thái đã đọc không?”**. Với danh sách chỉ để xem, CAS thường không cần. Với luồng chỉnh sửa đòi hỏi tránh lost update, hãy giữ cả ID và version token từ đúng lần đọc, rồi thực hiện mutation kèm CAS để server kiểm tra xung đột tại thời điểm ghi.
