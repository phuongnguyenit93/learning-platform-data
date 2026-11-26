# Phân biệt collection mặc định và collection do ứng dụng tạo trong Couchbase

Khi bắt đầu dùng **Spring Data Couchbase**, chúng ta thường cấu hình tên bucket, khai báo một entity `@Document` và lưu dữ liệu qua `CouchbaseRepository`. Cách làm này có thể hoạt động mà không cần chỉ rõ scope hoặc collection. Tuy nhiên, khi hệ thống có nhiều loại dữ liệu hoặc nhiều dịch vụ cùng sử dụng một bucket, cần phân biệt rõ **collection mặc định** với **collection do ứng dụng tạo** để tránh ghi dữ liệu sai nơi, truy vấn sai tập tài liệu hoặc cấp quyền quá rộng.

Sau bài này, bạn có thể:

- Giải thích vị trí của collection mặc định trong cấu trúc bucket–scope–collection.
- Xác định đường dẫn thực tế của document khi dùng Couchbase Java SDK hoặc Spring Data Couchbase.
- Chọn collection phù hợp, tạo chỉ mục và truy vấn SQL++ đúng phạm vi.
- Nhận diện những lưu ý về phân quyền, TTL, CAS và chuyển đổi dữ liệu giữa các collection.

## 1. Nhìn đúng cấu trúc bucket, scope và collection

Trong Couchbase, dữ liệu được tổ chức theo ba tầng:

| Tầng | Vai trò | Ví dụ |
| --- | --- | --- |
| **Bucket** | Không gian lưu trữ cấp cao; là nơi cấu hình tài nguyên và nhiều chính sách lưu trữ. | `shop` |
| **Scope** | Nhóm các collection có liên quan trong một bucket. | `_default`, `commerce` |
| **Collection** | Tập document mà ứng dụng đọc/ghi; document được nhận diện bởi key trong phạm vi collection đó. | `_default`, `orders`, `customers` |

Ví dụ một bucket phục vụ hệ thống bán hàng:

```text
bucket: shop
├── scope: _default
│   ├── collection: _default     ← collection mặc định của bucket
│   └── collection: audit        ← collection do ứng dụng/người quản trị tạo
└── scope: commerce              ← scope do ứng dụng/người quản trị tạo
    ├── collection: orders       ← collection do ứng dụng/người quản trị tạo
    └── collection: customers    ← collection do ứng dụng/người quản trị tạo
```

Mỗi bucket có scope tên **`_default`** và collection mặc định **`_default`** nằm trong scope đó. Vì vậy, tên đầy đủ của collection mặc định trong ví dụ là **`shop`.`_default`.`_default`**. Hai thành phần `_default` khác nhau: thành phần đầu là *scope*, thành phần sau là *collection*.

**Điểm dễ nhầm:** Một collection do ứng dụng tạo vẫn có thể nằm trong scope `_default` (ví dụ `shop._default.audit`). Nó **không** trở thành collection mặc định chỉ vì nằm trong scope mặc định. Collection mặc định là collection đặc biệt có tên `_default` trong scope `_default`.

## 2. Khác nhau ở đâu?

| Tiêu chí | Collection mặc định | Collection do ứng dụng tạo |
| --- | --- | --- |
| **Cách hình thành** | Có sẵn cùng bucket để hỗ trợ cách truy cập bucket truyền thống. | Phải được tạo rõ ràng qua giao diện quản trị, CLI, API hoặc SDK quản trị. |
| **Đường dẫn** | Luôn là `<bucket>._default._default`. | Là `<bucket>.<scope>.<collection>` tùy thiết kế. |
| **Tên gọi** | Sử dụng tên dành riêng `_default`. | Sử dụng tên nghiệp vụ như `orders`, `customers`, `sessions` theo quy tắc đặt tên Couchbase. |
| **Truy cập bằng Java SDK** | `bucket.defaultCollection()`. | `bucket.scope("commerce").collection("orders")`. |
| **Truy cập bằng Spring Data** | Có thể là đích mặc định khi ứng dụng không khai báo scope/collection riêng, tùy cấu hình. | Khai báo rõ đích bằng `@Scope`, `@Collection` hoặc cơ chế chọn scope/collection tương ứng của phiên bản đang dùng. |
| **Truy vấn SQL++** | Truy vấn tới `bucket._default._default`; có thể dùng cú pháp rút gọn tên bucket khi ngữ cảnh cho phép. | Nên dùng đường dẫn đầy đủ `bucket.scope.collection`. |
| **Chỉ mục** | Chỉ mục tạo trên collection mặc định. | Cần chỉ mục phù hợp trên **chính collection mới**; không kế thừa chỉ mục collection mặc định. |
| **Phân quyền** | Có thể cấp quyền theo bucket, scope hoặc collection tùy vai trò. | Có thể giới hạn quyền tới collection nghiệp vụ cụ thể. |
| **Mục đích thực tế** | Ứng dụng cũ, thử nghiệm, khởi đầu đơn giản. | Phân tách miền dữ liệu, dịch vụ và chính sách vận hành rõ ràng. |

Hai loại collection vẫn cùng tuân theo mô hình document/key-value của Couchbase. Việc lưu trong collection tự tạo **không làm document tự động có schema cố định**, cũng không làm mỗi collection biến thành một bucket độc lập với dung lượng riêng.

## 3. Ví dụ: cùng một key, hai collection khác nhau

Giả sử hệ thống có bucket `shop`. Ứng dụng cũ ghi đơn hàng vào collection mặc định; phiên bản mới được thiết kế ghi vào collection `commerce.orders`.

Với **Couchbase Java SDK**, hai đường truy cập khác nhau:

```java
import com.couchbase.client.java.Bucket;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;

// cluster là Cluster đã kết nối tới Couchbase.
Bucket bucket = cluster.bucket("shop");

Collection legacy = bucket.defaultCollection();
Collection orders = bucket.scope("commerce").collection("orders");

legacy.upsert("order::1001", JsonObject.create()
    .put("status", "legacy")
    .put("customerId", "C001"));

orders.upsert("order::1001", JsonObject.create()
    .put("status", "confirmed")
    .put("customerId", "C001"));
```

Mặc dù cùng key `order::1001`, đây là **hai document độc lập** vì key chỉ xác định duy nhất document **bên trong một collection**. Lệnh `legacy.get("order::1001")` và `orders.get("order::1001")` sẽ trả về nội dung ở hai nơi khác nhau.

Ví dụ này giả định bucket, scope và collection đã tồn tại và tài khoản được cấp quyền tương ứng. **Gọi `bucket.scope(...).collection(...)` chỉ lấy đối tượng truy cập; không tự tạo scope hoặc collection trên server.**

### Hệ quả quan trọng

- Nếu ứng dụng chuyển từ collection mặc định sang `commerce.orders` mà chưa di chuyển dữ liệu, đọc key cũ tại collection mới có thể nhận lỗi *document not found*.
- Việc ghi cùng key ở hai collection không phải cập nhật cùng một document và không có cơ chế tự đồng bộ dữ liệu.
- Muốn tra cứu `order::1001`, cần xác định **đúng bucket, scope, collection và key**. Chỉ biết key là chưa đủ.

## 4. Mapping collection trong Spring Data Couchbase

Trong Spring Data Couchbase, entity thể hiện kiểu document; repository cung cấp API lưu, lấy và truy vấn document. Tên bucket thường được cấu hình ở mức ứng dụng, còn scope và collection có thể được chỉ rõ ở mức entity.

Ví dụ entity cho collection do ứng dụng tạo:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("commerce")
@Collection("orders")
public class OrderDocument {
    @Id
    private String id;

    private String customerId;
    private String status;

    // Constructor và getter/setter được lược bỏ để tập trung vào mapping.
}
```

Repository tương ứng:

```java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {
}
```

Khi ứng dụng dùng phiên bản Spring Data Couchbase hỗ trợ hai annotation này và không có cấu hình ghi đè vị trí, các thao tác của `OrderRepository` được định tuyến tới `shop.commerce.orders` (với bucket ứng dụng là `shop`).

Ngược lại, entity đơn giản sau **không yêu cầu collection nghiệp vụ riêng**:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;

@Document
public class LegacyOrderDocument {
    @Id
    private String id;
}
```

Nếu ứng dụng giữ cấu hình scope/collection mặc định, entity này dùng collection `_default` trong scope `_default`. Cần kiểm tra cấu hình, phiên bản Spring Data Couchbase và mọi cơ chế chọn collection đang áp dụng: **không nên suy ra đích lưu chỉ từ việc thiếu annotation** trong một dự án đã tùy biến cấu hình.

### Những điều annotation không thực hiện

`@Scope("commerce")` và `@Collection("orders")` là khai báo **ánh xạ vị trí lưu trữ**, không phải lệnh tạo tài nguyên Couchbase. Trước khi chạy ứng dụng, người vận hành hoặc quy trình triển khai cần tạo `commerce` và `orders`, cấp quyền thích hợp, đồng thời chuẩn bị chỉ mục cho các truy vấn. Cách tạo có thể qua Couchbase Web Console hoặc API/SDK quản trị.

Tương tự, một repository reactive (`ReactiveCouchbaseRepository`) không tự thay đổi đích lưu: chọn reactive ảnh hưởng cách xử lý bất đồng bộ và luồng dữ liệu, còn **scope/collection vẫn phải được ánh xạ đúng**.

## 5. Truy vấn SQL++ phải chỉ rõ collection

SQL++ (trước đây thường được gọi là N1QL) sử dụng *keyspace* để xác định nơi lấy document. Dùng dấu backtick để bao tên bucket, scope và collection khi cần, đặc biệt nếu tên có dấu gạch nối hoặc ký tự cần escape.

Truy vấn trên collection mặc định:

```sql
SELECT META(d).id AS documentId, d.status
FROM `shop`.`_default`.`_default` AS d
WHERE d.customerId = "C001";
```

Truy vấn trên collection nghiệp vụ:

```sql
SELECT META(o).id AS documentId, o.status
FROM `shop`.`commerce`.`orders` AS o
WHERE o.customerId = "C001";
```

Hai câu truy vấn có điều kiện giống nhau nhưng **không đọc cùng tập document**. Đối với collection mặc định, một số câu lệnh/ngữ cảnh cho phép viết rút gọn bằng cách chỉ nêu tên bucket `shop` trong mệnh đề `FROM`; khi dạy, đọc log hoặc xử lý lỗi, dùng đường dẫn đầy đủ thường dễ kiểm chứng hơn.

Với truy vấn có điều kiện, cần tạo chỉ mục trên collection được truy vấn; ví dụ:

```sql
CREATE INDEX ix_orders_customer
ON `shop`.`commerce`.`orders`(customerId);
```

Chỉ mục trên `shop._default._default` **không phục vụ thay cho** chỉ mục trên `shop.commerce.orders`. Thiết kế chỉ mục thực tế phải xem thêm điều kiện lọc, sắp xếp, kiểu truy vấn do repository sinh ra và cấu hình phân biệt loại document của Spring Data. Truy cập trực tiếp bằng KV API (`get`, `upsert`) qua key không đòi hỏi chỉ mục SQL++ thứ cấp.

## 6. Lợi ích và giới hạn của collection do ứng dụng tạo

### Tách miền dữ liệu rõ ràng

Thay vì đưa toàn bộ `orders`, `customers`, `sessions` và `audit` vào một collection, có thể tách các tập document theo nghiệp vụ. Điều này giúp đặt tên rõ ràng, giảm nhầm lẫn khi tìm dữ liệu và dễ tổ chức index, quyền truy cập hoặc vòng đời document theo từng collection.

Tuy nhiên, collection không tự bảo đảm rằng mọi document có cùng cấu trúc. Ứng dụng vẫn cần quy ước schema, versioning và kiểm tra dữ liệu khi cần.

### Phân quyền có phạm vi hẹp

Couchbase hỗ trợ cấp quyền ở những phạm vi thích hợp với vai trò và phiên bản đang sử dụng. Ví dụ, dịch vụ quản lý đơn hàng có thể được cấp quyền cho `commerce.orders` mà không được truy cập `commerce.customers`. Điều này thuận lợi cho phân quyền theo trách nhiệm của từng dịch vụ.

Tách collection **không tự động tạo ranh giới bảo mật**: nếu tài khoản ứng dụng vẫn có vai trò quá rộng ở cấp bucket thì tài khoản đó vẫn có thể truy cập các collection khác theo quyền đã được cấp.

### Chính sách TTL và nhất quán

Document ở cả hai loại collection có thể dùng TTL/expiry và CAS (*Compare-And-Swap*) theo các API, khả năng của phiên bản Couchbase đang dùng. Với collection tạo riêng, chính sách tuổi thọ tối đa có thể được cấu hình ở cấp collection khi hệ thống hỗ trợ; cần kiểm tra thêm chính sách kế thừa hoặc giới hạn ở cấp bucket.

- **TTL/expiry** điều khiển khi nào document hết hạn; việc chuyển document giữa các collection không tự bảo toàn expiry nếu quy trình sao chép không xử lý thuộc tính này đúng cách.
- **CAS** dùng để phát hiện xung đột khi cập nhật một document; CAS không hợp nhất hai document cùng key nằm ở hai collection khác nhau.
- **Giao dịch** cần được thiết kế bằng tính năng transaction và điều kiện hỗ trợ của Couchbase/Spring Data; chỉ tách thành các collection không tự mang lại tính nguyên tử cho nhiều thao tác.

### Giới hạn vận hành cần nhớ

Các collection trong cùng bucket vẫn chia sẻ hạ tầng và phần lớn tài nguyên cấp bucket. Một collection mới không đương nhiên có quota lưu trữ, tài nguyên cluster, replication hay backup độc lập như một bucket riêng. Chọn tạo collection hay bucket mới cần dựa trên yêu cầu cô lập tài nguyên và vận hành, không chỉ dựa vào tên miền dữ liệu.

## 7. Chọn collection nào cho dự án?

| Tình huống | Gợi ý |
| --- | --- |
| Học API CRUD cơ bản hoặc chạy thử nhanh với một loại document. | Collection mặc định đủ để khởi đầu, miễn là người học biết chính xác document đang nằm ở đâu. |
| Dự án có nhiều loại document với truy vấn và chỉ mục khác nhau. | Tạo collection riêng theo nhóm nghiệp vụ, ví dụ `commerce.orders` và `commerce.customers`. |
| Nhiều dịch vụ sử dụng chung bucket nhưng cần giới hạn quyền. | Chọn scope/collection rõ ràng và cấp quyền đúng phạm vi cần dùng. |
| Cần quy tắc hết hạn khác nhau cho dữ liệu phiên, giỏ hàng và đơn hàng. | Xem xét collection riêng và xác minh khả năng/cấu hình TTL ở bản Couchbase sử dụng. |
| Dữ liệu cũ đã nằm trong `_default._default` và đang đổi kiến trúc. | Lập kế hoạch di chuyển dữ liệu và đổi mapping một cách có kiểm chứng; không chỉ thêm annotation. |

Không có quy tắc “mỗi entity bắt buộc một collection”. Có thể lưu nhiều loại document trong một collection nếu truy vấn, chỉ mục, phân quyền và vòng đời dữ liệu tương đồng. Ngược lại, nếu cần ranh giới vận hành rõ, tách collection sớm thường giúp thiết kế dễ hiểu hơn.

## 8. Chuyển từ collection mặc định sang collection tự tạo

Giả sử `OrderDocument` trước đây được ghi vào `shop._default._default`, sau đó nhóm phát triển quyết định dùng `shop.commerce.orders`. Một trình tự triển khai có thể là:

1. **Kiểm kê:** xác định các document đơn hàng đang nằm ở đâu, key, cấu trúc, expiry và các luồng đang đọc/ghi chúng.
2. **Chuẩn bị đích:** tạo scope `commerce`, collection `orders`; cấp quyền và tạo các chỉ mục phục vụ truy vấn trên collection mới.
3. **Di chuyển có kiểm chứng:** sao chép hoặc chuyển document bằng công cụ/quy trình thích hợp, bảo toàn key và các thuộc tính quan trọng khi cần; kiểm tra số lượng, nội dung và tính nhất quán.
4. **Đổi mapping/đường truy cập:** cập nhật `@Scope`, `@Collection`, các thao tác SDK, câu SQL++ và cấu hình liên quan; lên kế hoạch xử lý ghi phát sinh trong giai đoạn chuyển đổi.
5. **Kiểm thử trước khi dọn nguồn:** xác minh CRUD theo key, query theo index, phân quyền, TTL và các luồng lỗi; chỉ xóa dữ liệu cũ khi đã có phương án quay lại và chắc chắn không còn phụ thuộc.

Đặc biệt, **đổi `@Collection` không phải lệnh migrate**. Nếu vừa đổi mapping vừa chuyển dữ liệu trong hệ thống vẫn phát sinh ghi, cần xử lý bài toán đồng bộ/gián đoạn theo yêu cầu nghiệp vụ; nếu bỏ qua, đơn hàng mới và cũ có thể nằm rải rác ở hai collection.

## 9. Lỗi thường gặp và cách nhận diện

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `get(id)` không thấy document dù Console hiển thị document cùng key. | Ứng dụng đang truy cập collection khác. | So sánh đủ `bucket.scope.collection` ở Console và trong SDK/mapping. |
| Ứng dụng không truy cập được `commerce.orders`. | Scope/collection chưa tồn tại hoặc quyền tài khoản chưa đủ. | Kiểm tra tài nguyên trên server và các role được cấp. |
| KV `get` hoạt động, nhưng truy vấn repository/SQL++ thất bại. | Chưa có chỉ mục phù hợp trên collection đích hoặc truy vấn được sinh ra cần điều kiện/index khác. | Kiểm tra câu SQL++, thông báo lỗi truy vấn và index trên đúng keyspace. |
| Dữ liệu mới nằm trong `orders`, dữ liệu cũ vẫn trong `_default`. | Đổi mapping mà chưa migrate. | Kiểm tra tồn tại của key và số lượng document ở cả hai nơi. |
| Dịch vụ đọc được dữ liệu từ collection ngoài phạm vi mong muốn. | Role được cấp ở phạm vi quá rộng. | Rà soát quyền bucket/scope/collection của tài khoản dịch vụ. |

## 10. Tự kiểm tra kiến thức

**Tình huống 1.** Bucket `shop` có `shop._default._default` và `shop._default.audit`. Collection nào là collection mặc định?

**Đáp án:** Chỉ `shop._default._default`. `audit` là collection do ứng dụng tạo, dù nằm trong scope `_default`.

**Tình huống 2.** Hai collection `shop._default._default` và `shop.commerce.orders` đều có document key `order::1001`. Đây có phải một document không?

**Đáp án:** Không. Key chỉ là duy nhất trong từng collection; mỗi collection chứa document độc lập.

**Tình huống 3.** Thêm `@Scope("commerce")` và `@Collection("orders")` vào entity có tự tạo collection và di chuyển dữ liệu cũ không?

**Đáp án:** Không. Cần tạo tài nguyên ở Couchbase và thực hiện di chuyển dữ liệu bằng quy trình riêng.

**Tình huống 4.** Index `customerId` đã có trên collection mặc định. Truy vấn `commerce.orders` theo `customerId` có tự dùng index đó không?

**Đáp án:** Không. Chỉ mục gắn với collection được tạo. Cần chỉ mục thích hợp trên `commerce.orders` nếu truy vấn yêu cầu.

## Ghi nhớ

**Collection mặc định** là `<bucket>._default._default`, thuận tiện cho cách sử dụng đơn giản và tương thích với ứng dụng cũ. **Collection do ứng dụng tạo** là tập document có tên và vị trí được lựa chọn rõ ràng, giúp tổ chức dữ liệu, chỉ mục, phân quyền và chính sách vận hành theo nghiệp vụ. Trong Spring Data Couchbase, điều quan trọng nhất là xác minh entity/repository thực sự đang thao tác với **collection nào**, bởi cùng một key trong hai collection là hai document khác nhau.
