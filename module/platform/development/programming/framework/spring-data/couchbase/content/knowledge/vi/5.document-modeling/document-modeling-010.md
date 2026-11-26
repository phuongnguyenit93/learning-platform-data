# Phân biệt trường thiếu, giá trị null và giá trị mặc định trong Spring Data Couchbase

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **field không tồn tại (MISSING)**, **field có giá trị JSON `null` (NULL)**, **giá trị rỗng hợp lệ** và **giá trị mặc định do ứng dụng áp dụng**.
2. Viết SQL++ kiểm tra `IS MISSING`, `IS NULL`, `IS VALUED`; sử dụng `IFMISSING` và `IFMISSINGORNULL` đúng mục đích.
3. Hiểu giới hạn của các kiểu Java nguyên thủy, wrapper, constructor, record và `@Field` khi dữ liệu Couchbase không đồng nhất schema.
4. Thiết kế quy tắc mặc định ở **tầng đọc, tầng nghiệp vụ hoặc tầng migration**, không đánh đồng ba nơi.
5. Xây dựng PATCH có ngữ nghĩa rõ ràng: giữ nguyên, gán giá trị, gán `null` hoặc xóa field.
6. Kiểm thử dữ liệu cũ, truy vấn chỉ mục, cập nhật đồng thời qua CAS, TTL và các luồng repository/`CouchbaseTemplate`/reactive.

Đây là bài thuộc chương **Mô hình tài liệu** của module **SPRING_DATA_COUCHBASE**. Module xây dựng tầng truy cập Couchbase qua document mapping, repository, `CouchbaseTemplate`, SQL++ và thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, transaction, reactive API. Một nguồn lỗi quan trọng trong hệ thống JSON linh hoạt là **Java có thể không giữ được mọi trạng thái mà Couchbase đang lưu**.

## 1. Bốn document trông giống nhau trong Java nhưng khác nhau ở JSON

Giả sử collection `shop.catalog.products` đang có bốn document sản phẩm, đều chứa tên và trạng thái kho:

| Document key | JSON body rút gọn | Ý nghĩa có thể có |
| --- | --- | --- |
| `product::a` | `{"name":"A"}` | Chưa từng có trường `stock_quantity` |
| `product::b` | `{"name":"B","stock_quantity":null}` | Trường tồn tại, giá trị chưa biết/đang chờ xác nhận |
| `product::c` | `{"name":"C","stock_quantity":0}` | Đã biết số lượng tồn là **0** |
| `product::d` | `{"name":"D","stock_quantity":12}` | Đã biết số lượng tồn là **12** |

Bốn trường hợp **không tương đương**:

- `MISSING`: khóa `stock_quantity` **không tồn tại** trong JSON object.
- `NULL`: khóa tồn tại và giá trị bằng JSON literal `null`.
- `0`: một **số hợp lệ**, có thể mang nghĩa hết hàng.
- `12`: một số hợp lệ khác.

Trong miền nghiệp vụ, mặc định `0` khi thiếu dữ liệu kho có thể là sai: “chưa biết tồn kho” không đồng nghĩa “hết hàng”. Ngược lại, trường `visibility` bị thiếu ở dữ liệu cũ có thể được quy định là `"DRAFT"` sau khi đội nghiệp vụ chấp thuận. **Giá trị mặc định là quyết định của ứng dụng, không phải đặc tính tự phát của JSON.**

~~~mermaid
flowchart LR
    J["JSON field stock_quantity"] --> A{"Có key không?"}
    A -->|"Không"| M["MISSING"]
    A -->|"Có"| B{"Giá trị có phải null?"}
    B -->|"Có"| N["NULL"]
    B -->|"Không"| V["VALUE: 0, 12, ..."]
    M --> P["Chính sách xử lý"]
    N --> P
    V --> P
~~~

**Lưu ý:** SQL++ có giá trị đặc biệt `MISSING` trong biểu thức truy vấn, nhưng **JSON chuẩn không có literal `missing`**. Trong body JSON, muốn biểu diễn field thiếu thì **bỏ hẳn key**; viết `"stock_quantity": missing` không phải JSON hợp lệ.

## 2. Cách SQL++ hiểu MISSING, NULL, VALUE

Couchbase SQL++ phân biệt `MISSING` và `NULL` để truy vấn document không bắt buộc có schema đồng nhất.

| Biểu thức SQL++ | Field thiếu | Field bằng `null` | Field bằng `0` hoặc `false` |
| --- | :---: | :---: | :---: |
| `x IS MISSING` | TRUE | FALSE | FALSE |
| `x IS NOT MISSING` | FALSE | TRUE | TRUE |
| `x IS NULL` | FALSE | TRUE | FALSE |
| `x IS NOT NULL` | **TRUE** | FALSE | TRUE |
| `x IS VALUED` | FALSE | FALSE | TRUE |
| `x IS NOT VALUED` | TRUE | TRUE | FALSE |

Dòng dễ gây hiểu lầm nhất là **`IS NOT NULL`**: trong SQL++ của Couchbase Server, biểu thức này kiểm tra field **không phải NULL**, do đó **field MISSING vẫn thỏa**. Nếu thực sự cần giá trị tồn tại và khác null, dùng **`IS VALUED`**.

Ví dụ SQL++:

~~~sql
-- Field chưa từng xuất hiện trong JSON:
SELECT META(p).id AS productKey
FROM `shop`.`catalog`.`products` AS p
WHERE p.stock_quantity IS MISSING;

-- Key đã tồn tại, nhưng giá trị JSON là null:
SELECT META(p).id AS productKey
FROM `shop`.`catalog`.`products` AS p
WHERE p.stock_quantity IS NULL;

-- Có giá trị khác NULL và MISSING, kể cả 0:
SELECT META(p).id AS productKey
FROM `shop`.`catalog`.`products` AS p
WHERE p.stock_quantity IS VALUED;
~~~

`IS VALUED` chỉ nói rằng giá trị tồn tại, **không bảo đảm hợp lệ về nghiệp vụ**. Ví dụ `stock_quantity: -5`, `stock_quantity: ""` hoặc `stock_quantity: []` đều không phải `NULL`/`MISSING`, nhưng cần bị từ chối bởi quy tắc dữ liệu kho.

### 2.1. MISSING trong kết quả SELECT

Xét:

~~~sql
SELECT META(p).id AS productKey,
       p.stock_quantity AS stockQuantity
FROM `shop`.`catalog`.`products` AS p
USE KEYS ["product::a", "product::b", "product::c"];
~~~

Kết quả dạng minh họa:

~~~json
[
  {"productKey":"product::a"},
  {"productKey":"product::b","stockQuantity":null},
  {"productKey":"product::c","stockQuantity":0}
]
~~~

Khi biểu thức chọn ra `MISSING`, thuộc tính tương ứng có thể **bị lược khỏi object kết quả**. Khi là `NULL`, thuộc tính thường có mặt với giá trị `null`. Vì vậy một DTO JSON tạo từ projection có thể có hình dạng khác nhau, dù cùng một câu truy vấn.

Không nên viết test kiểu “ba dòng query luôn có đủ key `stockQuantity`”. Hãy kiểm tra cả **sự tồn tại của field** và giá trị khi có mặt.

### 2.2. NULL, rỗng và mặc định là các trạng thái khác

~~~json
{
  "discount_percent": 0,
  "active": false,
  "note": "",
  "tags": [],
  "attributes": {}
}
~~~

Tất cả các key trên đều **tồn tại** và có giá trị hợp lệ về mặt JSON:

- `0` là number, không phải null.
- `false` là boolean, không phải null.
- `""` là string rỗng, không phải null.
- `[]` là array rỗng.
- `{}` là object rỗng.

Một field `tags: []` có thể nghĩa “đã xác nhận không có nhãn”; trong khi thiếu `tags` có thể nghĩa “document từ schema cũ chưa hỗ trợ nhãn”. Chỉ gộp hai trạng thái khi **quy tắc miền cho phép**.

## 3. Ba hàm chọn giá trị thay thế trong SQL++

Couchbase có các hàm giúp áp dụng giá trị thay thế khi truy vấn.

| Hàm | Bỏ qua điều gì? | Kết quả khi đối số đầu là `MISSING` | Khi đối số đầu là `NULL` |
| --- | --- | --- | --- |
| `IFMISSING(x, fallback)` | Chỉ `MISSING` | `fallback` | Giữ `NULL` |
| `IFNULL(x, fallback)` | Chỉ `NULL` | Giữ `MISSING` | `fallback` |
| `IFMISSINGORNULL(x, fallback)` | Cả hai | `fallback` | `fallback` |

`COALESCE(...)` là alias tương đương với `IFMISSINGORNULL(...)` trong SQL++ Server.

~~~sql
SELECT META(p).id AS productKey,
       IFMISSING(p.stock_quantity, -1) AS missingOnly,
       IFNULL(p.stock_quantity, -2) AS nullOnly,
       IFMISSINGORNULL(p.stock_quantity, -3) AS missingOrNull
FROM `shop`.`catalog`.`products` AS p
USE KEYS ["product::a", "product::b", "product::c"];
~~~

Với dữ liệu đầu bài, kết quả logic:

| Document | `missingOnly` | `nullOnly` | `missingOrNull` |
| --- | --- | --- | --- |
| `product::a` (MISSING) | `-1` | Thuộc tính có thể bị lược (MISSING) | `-3` |
| `product::b` (NULL) | `null` | `-2` | `-3` |
| `product::c` (0) | `0` | `0` | `0` |

Các số `-1`, `-2`, `-3` chỉ là **sentinel minh họa** để nhìn rõ hành vi, không nên dùng làm số lượng tồn kho thực tế. Khi xuất dữ liệu cho API, tốt hơn dùng cấu trúc có trạng thái rõ ràng hoặc `null` với hợp đồng đã công bố.

Ví dụ một quy tắc nghiệp vụ đã được xác nhận: sản phẩm chưa có field `visibility` trong **schema cũ** được coi là `DRAFT`, nhưng field có `null` nghĩa “chưa quyết định” và không được ép về `DRAFT`.

~~~sql
SELECT META(p).id AS productKey,
       IFMISSING(p.visibility, "DRAFT") AS effectiveVisibility
FROM `shop`.`catalog`.`products` AS p;
~~~

Nếu muốn cả `NULL` và `MISSING` trở thành `DRAFT`, phải chọn `IFMISSINGORNULL` một cách **có chủ đích**, không đổi hàm chỉ để truy vấn nhìn đẹp hơn.

## 4. Trường lồng nhau, danh sách và đối tượng rỗng

Với document:

~~~json
{
  "shipping_address": {
    "city": "Hồ Chí Minh"
  },
  "items": [],
  "notes": null
}
~~~

Các trường hợp:

| Đường dẫn SQL++ | Trạng thái | Giải thích |
| --- | --- | --- |
| `p.shipping_address` | Object có giá trị | Object tồn tại |
| `p.shipping_address.city` | String có giá trị | Field con hiện diện |
| `p.shipping_address.postal_code` | MISSING | Field con không có trong object |
| `p.items` | Array rỗng | Không phải NULL/MISSING |
| `p.notes` | NULL | Key `notes` tồn tại với JSON null |
| `p.discount_code` | MISSING | Top-level key chưa tồn tại |

Đường dẫn nhiều cấp cần xem cả trạng thái **parent object**. Nếu `shipping_address` bị thiếu, `shipping_address.city` không thể có giá trị như một object bình thường. Nếu parent là `null`, biểu thức đường dẫn cũng không thể được hiểu như một object hoàn chỉnh. Đừng chỉ kiểm tra leaf property rồi xem mọi trường hợp là “không có địa chỉ”.

Trong Java, phân biệt:

~~~java
List<String> tags = List.of();  // Đã có list, hiện rỗng.
List<String> unknownTags = null; // Chưa có giá trị được ánh xạ.
~~~

Nhưng một `null` Java **không tự nói lên** JSON đã lưu `"tags": null` hay JSON không có key `tags`. Cần đọc JSON gốc hoặc truy vấn phân loại trước khi chuyển đổi nếu sự phân biệt quan trọng.

## 5. Mapping entity Spring Data Couchbase: nơi thông tin dễ bị mất

Với entity POJO thông thường:

~~~java
package com.example.shop.catalog;

import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("catalog")
@Collection("products")
public class Product {

    @Id
    private String id;

    @Version
    private Long version;

    @Field("display_name")
    private String displayName;

    @Field("stock_quantity")
    private Integer stockQuantity;

    @Field
    private boolean active;

    @Field("review_note")
    private String reviewNote;

    @Field
    private List<String> tags = new ArrayList<>();

    protected Product() {
        // Constructor dùng cho quá trình materialize.
    }

    public Product(String id, String displayName) {
        this.id = id;
        this.displayName = displayName;
        this.active = false;
        this.tags = new ArrayList<>();
    }

    public String getId() { return id; }
    public String getDisplayName() { return displayName; }
    public Integer getStockQuantity() { return stockQuantity; }
    public boolean isActive() { return active; }
    public String getReviewNote() { return reviewNote; }
    public List<String> getTags() { return List.copyOf(tags); }

    public void setStockQuantity(Integer stockQuantity) {
        if (stockQuantity != null && stockQuantity < 0) {
            throw new IllegalArgumentException("Tồn kho không thể âm");
        }
        this.stockQuantity = stockQuantity;
    }
}
~~~

Đây là **một ví dụ thiết kế**, không phải cam kết rằng Java null được converter ghi ra JSON null trong mọi phiên bản/cấu hình.

Điểm mấu chốt:

- `@Id` là **document key** của Couchbase, không phải field JSON `id`.
- `@Version` giữ **CAS metadata**, không phải `schema_version`.
- `@Field("stock_quantity")` ánh xạ property Java `stockQuantity` sang tên JSON `stock_quantity`.
- `Integer stockQuantity` nhận được `null` ở Java, nhưng giá trị này **có thể đại diện cả MISSING lẫn NULL** sau khi materialize. Không khẳng định trạng thái JSON gốc chỉ dựa trên `getStockQuantity() == null`.
- `boolean active` mặc định của Java là `false`. Một document thiếu `active` có thể trông giống document có `active:false` trong code; mất phân biệt có thể gây lỗi nghiệp vụ. Khi “chưa biết” quan trọng, cân nhắc `Boolean`.
- `tags = new ArrayList<>()` là khởi tạo mặc định của lớp Java. Không nên dựa vào việc initializer chắc chắn được giữ hay bị thay bằng null trong **mọi** con đường materialization: constructor, converter và dữ liệu hiện tại phải được kiểm thử trên phiên bản Spring Data đang chạy.
- `reviewNote == null` không chứng minh rằng JSON đã lưu `review_note:null`.

### 5.1. Chọn primitive hay wrapper?

| Yêu cầu | Kiểu Java gợi ý | Vì sao |
| --- | --- | --- |
| Giá trị bắt buộc luôn có, đã được validate trước khi đọc | `int`, `long`, `boolean` | Tránh null trong logic sau khi dữ liệu hợp lệ |
| Cần biểu diễn **chưa có giá trị** | `Integer`, `Long`, `Boolean` | Có trạng thái Java `null`, nhưng chưa phân biệt JSON missing/null |
| Cần phân biệt **MISSING**, **NULL** và **VALUE** | DTO/trạng thái tường minh hoặc xử lý JSON gốc | Một wrapper `Integer` không có đủ ba trạng thái |
| Danh sách luôn hợp lệ và có thể rỗng | `List<T>` với canonical normalization | Cần quy định riêng dữ liệu cũ thiếu/null |

**Không dùng `Optional<T>` như giải pháp mặc định cho mọi field entity.** `Optional` thường phù hợp với API trả về; cách persistence converter xử lý `Optional` như property phụ thuộc phiên bản/configuration và phải kiểm thử. Nếu cần diễn đạt ba trạng thái, một kiểu miền tường minh rõ nghĩa hơn.

## 6. Constructor, record và giá trị mặc định khi đọc lại

Giả sử dùng Java record:

~~~java
import java.util.List;
import java.util.Objects;
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;

@Document
public record CatalogItem(
    @Id String id,
    @Field("display_name") String displayName,
    @Field List<String> tags,
    @Field("stock_quantity") Integer stockQuantity
) {
    public CatalogItem {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(displayName, "displayName");
        tags = tags == null ? List.of() : List.copyOf(tags);
    }
}
~~~

Record dùng canonical constructor để materialize. Khi `tags` bị thiếu hoặc được mapper đọc thành Java `null`, quy tắc `tags == null ? List.of() : ...` có thể tạo danh sách rỗng. Đây là **một chính sách mặc định ở tầng Java**, không sửa JSON gốc. Sau khi object được tạo, bạn không còn biết `tags` ban đầu là MISSING hay NULL chỉ qua `item.tags()`.

Tương tự, nếu constructor bắt buộc `stockQuantity != null` nhưng dữ liệu cũ không có `stock_quantity`, quá trình đọc có thể **thất bại**. Đây không phải lý do để lặng lẽ đổi thành `0`. Hãy quyết định trước ý nghĩa thật sự của dữ liệu cũ.

### 6.1. Không sinh dữ liệu lịch sử trong persistence constructor

~~~java
// Sai nếu constructor này cũng được dùng để đọc tài liệu cũ:
public Order(String id, String status) {
    this.id = id;
    this.status = status;
    this.createdAt = Instant.now();
}
~~~

Nếu `createdAt` MISSING trong dữ liệu cũ, việc dùng `Instant.now()` sẽ khiến mỗi lần đọc “sản sinh” thời gian tạo mới. Đối với thời gian lịch sử, nên có migration hoặc factory riêng cho **lúc tạo mới**, còn constructor persistence khôi phục giá trị đã lưu.

### 6.2. Giá trị mặc định không đồng nghĩa field đã được lưu

Ví dụ API trả ra `"visibility":"DRAFT"` dù document cũ thiếu `visibility`; nếu DTO/service tự gán mặc định, **document trong Couchbase vẫn có thể không có key đó**.

Điều này ảnh hưởng:

- SQL++ query `WHERE visibility = "DRAFT"` có thể không tìm các document cũ, dù API đang hiển thị `DRAFT`.
- Index theo `visibility` không tự coi MISSING như `DRAFT`.
- Service khác đọc trực tiếp SDK vẫn thấy MISSING.
- Lần `save` đầy đủ về sau có thể ghi field mới, khiến document trộn schema nếu không có migration có kiểm soát.

Vì vậy hãy ghi rõ mặc định là **giá trị hiển thị**, **giá trị miền khi xử lý** hay **giá trị vật lý cần lưu**.

## 7. Ba tầng áp dụng default và hậu quả

| Tầng | Ví dụ | Ưu điểm | Rủi ro |
| --- | --- | --- | --- |
| **Read fallback** trong DTO/query | `IFMISSING(p.visibility, "DRAFT")` | Không sửa dữ liệu; dễ triển khai tương thích | JSON gốc vẫn MISSING; filter/index khác có thể cho kết quả khác |
| **Domain default** trong factory/constructor mới | `Product.create(...)` đặt `visibility=DRAFT` | Đảm bảo document mới nhất quán | Document cũ và writer khác vẫn có thể thiếu |
| **Data migration** | `UPDATE ... SET visibility="DRAFT" WHERE ... IS MISSING` | Đồng nhất dữ liệu lưu trữ; dễ query | Cần backup, CAS/ghi đồng thời, đánh giá index và rollback |

Mặc định chỉ hợp lý nếu đáp ứng **quy tắc nghiệp vụ có căn cứ**. Với tồn kho, số tiền, consent, quyền truy cập hoặc trạng thái thanh toán, ép `MISSING`/`NULL` về số hay boolean có thể làm hệ thống đưa ra quyết định sai. Đối với quyền truy cập, nên **fail closed** nếu thông tin thiếu: không tự cấp quyền từ mặc định.

Để lựa chọn có thể kiểm chứng, viết hợp đồng bằng bảng:

| Field | MISSING nghĩa là | NULL nghĩa là | Giá trị hợp lệ |
| --- | --- | --- | --- |
| `visibility` | Document schema cũ, chính sách đọc tạm `DRAFT` | Chưa hoàn tất gán trạng thái; cần xử lý | `DRAFT`, `PUBLIC`, `ARCHIVED` |
| `stock_quantity` | Chưa có dữ liệu kho | Đang chờ kiểm kê | Số nguyên không âm |
| `review_note` | Chưa từng có ghi chú | Ghi chú đã được xóa/không biết, tùy hợp đồng | Chuỗi, kể cả `""` nếu cho phép |
| `tags` | Chưa được migration | Chưa xác nhận | Array, kể cả `[]` |

Đây chỉ là **quy ước mẫu**. Hệ thống khác có thể chọn `NULL` là xóa ghi chú và MISSING là giữ nguyên schema cũ; quan trọng là mọi writer/reader thống nhất, không suy từ cú pháp.

## 8. HTTP PATCH: thiếu field không phải yêu cầu đặt null

Một HTTP PATCH có thể có ba payload:

~~~json
{}
~~~

~~~json
{"reviewNote": null}
~~~

~~~json
{"reviewNote": ""}
~~~

Theo hợp đồng PATCH bạn thiết kế, chúng có thể mang ý nghĩa:

- `{}`: **giữ nguyên** `reviewNote`.
- `{"reviewNote":null}`: **xóa giá trị**, có thể bằng cách lưu JSON null hoặc loại key; phải công bố lựa chọn.
- `{"reviewNote":""}`: **đặt chuỗi rỗng**, nếu nghiệp vụ cho phép.

Không thể dùng DTO:

~~~java
public record ProductPatch(String reviewNote) {}
~~~

rồi dựa vào `patch.reviewNote() == null` để phân biệt “client không gửi field” và “client chủ động gửi null”. Cả hai có thể thành Java null ở lớp DTO.

### 8.1. Dùng JsonNode để giữ thông tin field có mặt hay không

Ví dụ ở tầng controller/service (đã parse request JSON bằng Jackson):

~~~java
import com.fasterxml.jackson.databind.JsonNode;

public void inspectPatch(JsonNode payload) {
    if (!payload.has("reviewNote")) {
        // KEEP: client không đưa field này vào request.
        return;
    }

    JsonNode node = payload.get("reviewNote");
    if (node.isNull()) {
        // CLEAR: client gửi null tường minh.
        return;
    }

    if (!node.isTextual()) {
        throw new IllegalArgumentException("reviewNote phải là chuỗi hoặc null");
    }

    String nextValue = node.textValue(); // Có thể là "".
    // SET_VALUE: chạy validation và cập nhật có CAS.
}
~~~

`JsonNode.has(...)` khác với một phép kiểm tra chỉ xem giá trị Java null. Logic còn phải giới hạn field nào được PATCH, kích thước input, quyền truy cập và cách xử lý trường không biết.

### 8.2. Thiết kế thao tác lưu 4 trạng thái

Khi cập nhật JSON ở Couchbase, nên tách **ý định cập nhật** khỏi **giá trị cuối**:

| Ý định | Ý nghĩa | Cách triển khai phù hợp |
| --- | --- | --- |
| KEEP | Không thay đổi field | Không tạo mutation cho đường dẫn đó |
| SET_VALUE | Gán `"text"`, `0`, `false`, `[]`... | Ghi field với đúng kiểu |
| SET_NULL | Key tồn tại với JSON literal `null` | SQL++ `SET field = NULL` hoặc SDK sub-document phù hợp |
| REMOVE | Key biến mất, trở thành MISSING | SQL++ `UNSET field` hoặc SDK sub-document remove |

`@Field`/POJO setter không tự cung cấp giao diện 4 trạng thái này. Nếu API cần **xóa key** chứ không phải lưu JSON null, đừng chỉ gọi `setReviewNote(null)` rồi tin mọi converter sẽ ghi như mong đợi. Chọn cập nhật sub-document/SQL++ có chủ đích, hoặc mô hình hóa thao tác cập nhật rõ ràng qua service.

Cẩn thận với **JSON Merge Patch (RFC 7396)**: trong chuẩn đó, null thường mang nghĩa **xóa member**, không phải “lưu literal null”. Nếu API của bạn tuân chuẩn Merge Patch thì không được tự định nghĩa null là SET_NULL mà không ghi rõ sự khác biệt. Cần phân biệt HTTP JSON, cấu trúc update ở service và JSON body trong Couchbase.

## 9. SET NULL và UNSET trong SQL++ khác nhau

Với một document Product:

~~~json
{
  "name": "Cà phê",
  "review_note": "Đang kiểm tra"
}
~~~

Để giữ key nhưng thay giá trị bằng JSON null:

~~~sql
UPDATE `shop`.`catalog`.`products` AS p
USE KEYS "product::coffee250"
SET p.review_note = NULL;
~~~

Kết quả body theo ý định:

~~~json
{
  "name": "Cà phê",
  "review_note": null
}
~~~

Để loại hẳn key khỏi body:

~~~sql
UPDATE `shop`.`catalog`.`products` AS p
USE KEYS "product::coffee250"
UNSET p.review_note;
~~~

Kết quả body theo ý định:

~~~json
{
  "name": "Cà phê"
}
~~~

Sau thao tác đầu, `review_note IS NULL` đúng; sau thao tác thứ hai, `review_note IS MISSING` đúng. Cả hai đều làm document được mutation, vì vậy **CAS thay đổi**. Nếu ứng dụng đã đọc trước bằng Spring Data `@Version`, một lần `save` với CAS cũ có thể báo xung đột.

**Không dùng `SET p.review_note = NULL` và `UNSET p.review_note` thay thế lẫn nhau**. Hệ thống logging, audit, data export, index và business logic có thể phân biệt hai trạng thái.

## 10. Migration document cũ: chỉ đặt default khi đủ bằng chứng

Giả sử trước đây Product chưa có field `visibility`, nhưng từ phiên bản mới mỗi Product phải có `visibility`. Quy tắc được đồng ý: **chỉ document thiếu field mới nhận `"DRAFT"`**, không động đến `visibility:null` vì đó là trạng thái cần xử lý thủ công.

Quy trình:

1. Đếm document `visibility IS MISSING`, `IS NULL`, `IS VALUED` theo loại document và collection.
2. Kiểm tra sample JSON để bảo đảm không vô tình áp default cho dữ liệu không phải Product.
3. Bảo đảm writer mới luôn ghi `visibility` hợp lệ trước khi/đồng thời với migration.
4. Backup và lập phương án rollback hoặc sửa có điều kiện/idempotency.
5. Chạy batch nhỏ, theo dõi lỗi CAS, index lag và tác động lên truy vấn.
6. Đối chiếu tỷ lệ MISSING/NULL/VALUE sau mỗi batch; chỉ mở rộng khi kết quả đúng.

Ví dụ SQL++ giả định body có `entity_kind: "PRODUCT"`:

~~~sql
-- Xác định số document cũ cần migration:
SELECT COUNT(1) AS missingCount
FROM `shop`.`catalog`.`products` AS p
WHERE p.entity_kind = "PRODUCT"
  AND p.visibility IS MISSING;
~~~

Chỉ sau khi thống nhất business default:

~~~sql
UPDATE `shop`.`catalog`.`products` AS p
SET p.visibility = "DRAFT"
WHERE p.entity_kind = "PRODUCT"
  AND p.visibility IS MISSING;
~~~

Nếu JSON thực tế không có `entity_kind`, hãy dùng điều kiện phân loại **thực sự tồn tại** (ví dụ một `_class` đã xác minh), hoặc một quy trình theo document key được xác nhận. **Không tự phát minh một field type filter rồi chạy UPDATE**.

Quan trọng:

- Lệnh chỉ cập nhật **MISSING**. Document có `visibility:null` không bị chuyển thành `DRAFT`.
- Các writer đang hoạt động có thể ghi đồng thời; SQL++ UPDATE không tự bảo đảm không xảy ra conflict nghiệp vụ với service.
- Một batch mutation có thể làm secondary index phải cập nhật; cần đo chi phí và scan consistency.
- Đảm bảo chính sách **preserve expiry** nếu dữ liệu có TTL. Không suy rằng mọi đường cập nhật đều giữ hoặc đặt lại expiry giống nhau; kiểm tra API/options/server version.
- Nếu toàn bộ bộ dữ liệu lớn, cần chia batch có kiểm soát, backup và xác nhận tỷ lệ sai lệch, không chạy UPDATE diện rộng không giám sát.

### 10.1. Không nên tự chuyển NULL thành MISSING

Có thể có yêu cầu xóa trường `review_note:null` khỏi các document để tiết kiệm và thống nhất schema:

~~~sql
UPDATE `shop`.`catalog`.`products` AS p
UNSET p.review_note
WHERE p.review_note IS NULL;
~~~

Đây là **thay đổi ý nghĩa dữ liệu** nếu client trước đây phân biệt “người dùng đã xóa ghi chú” (NULL) với “chưa từng có field ghi chú” (MISSING). Chỉ áp dụng khi mọi reader, API contract và yêu cầu audit chấp nhận gộp hai trạng thái.

## 11. Index và truy vấn dữ liệu chất lượng kém

Một index thông thường được xây dựng dựa trên các giá trị/biểu thức của document. Với field MISSING, **quy tắc index bao gồm hoặc loại document**, nhất là ở leading index key, có thể ảnh hưởng cách optimizer dùng index. Không giả định chỉ cần:

~~~sql
CREATE INDEX ix_products_visibility
ON `shop`.`catalog`.`products`(visibility);
~~~

là mọi truy vấn `visibility IS MISSING` hay `IFMISSING(visibility, ...)` đều sử dụng index tối ưu.

Cần thử:

~~~sql
EXPLAIN
SELECT META(p).id AS productKey
FROM `shop`.`catalog`.`products` AS p
WHERE p.visibility IS MISSING;
~~~

và so với:

~~~sql
EXPLAIN
SELECT META(p).id AS productKey
FROM `shop`.`catalog`.`products` AS p
WHERE p.visibility = "DRAFT";
~~~

Nếu nghiệp vụ dùng truy vấn `IFMISSING(p.visibility, "DRAFT")`, hãy kiểm tra xem optimizer có dùng index nào, khi nào cần expression index hoặc nên migration field để có schema thống nhất. Không tạo index theo suy đoán; đo `EXPLAIN`, latency và tác động ghi.

### 11.1. Nhận biết schema sai kiểu dù field có giá trị

`IS VALUED` không kiểm tra dữ liệu có đúng kiểu. Ví dụ:

~~~json
{"stock_quantity": "12"}
~~~

khác về kiểu với:

~~~json
{"stock_quantity": 12}
~~~

Một document chứa string `"12"` có thể vượt kiểm tra `IS VALUED`, nhưng mapper Java `Integer` hoặc biểu thức số học có thể xử lý khác nhau tùy converter. Tách kiểm tra **sự tồn tại** khỏi kiểm tra **kiểu và miền giá trị**.

SQL++ hỗ trợ các hàm kiểm tra kiểu như `ISNUMBER(...)` theo ngữ cảnh phiên bản; ví dụ:

~~~sql
SELECT META(p).id AS productKey
FROM `shop`.`catalog`.`products` AS p
WHERE p.stock_quantity IS VALUED
  AND NOT ISNUMBER(p.stock_quantity);
~~~

Kiểm tra tính tương thích của hàm trên đúng phiên bản Couchbase Server và phân biệt dữ liệu kiểu sai với dữ liệu âm. Khi tính tiền, tồn kho và trạng thái bảo mật, nên **từ chối/đưa vào luồng sửa dữ liệu** thay vì ép kiểu ngầm không kiểm soát.

## 12. Repository, CouchbaseTemplate và SDK: chọn nơi kiểm tra trạng thái

Repository nhận một entity có các kiểu Java đã ánh xạ:

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface ProductRepository extends CouchbaseRepository<Product, String> {
}
~~~

~~~java
Product product = productRepository
    .findById("product::coffee250")
    .orElseThrow();

Integer stock = product.getStockQuantity();
if (stock == null) {
    // Chưa có số lượng tin cậy trong mô hình Java đã materialize.
    // Không kết luận JSON gốc là MISSING hay NULL chỉ từ dòng này.
}
~~~

Đây thường là đường **Key-Value theo document key**, không cần secondary index. `CouchbaseTemplate` cũng dùng thông tin entity mapping:

~~~java
import org.springframework.data.couchbase.core.CouchbaseTemplate;

public Product load(CouchbaseTemplate template, String key) {
    return template.findById(Product.class).one(key);
}
~~~

Nếu cần **phân biệt chính xác MISSING và NULL từ JSON gốc**, hãy đọc phần body qua Couchbase Java SDK hoặc query SQL++ có biểu thức `IS MISSING`/`IS NULL` trước khi converter biến thành property Java:

~~~java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.GetResult;

Collection products = cluster.bucket("shop")
    .scope("catalog")
    .collection("products");

GetResult result = products.get("product::coffee250");
JsonObject body = result.contentAsObject();

boolean hasStockField = body.containsKey("stock_quantity");
Object rawStock = hasStockField ? body.get("stock_quantity") : null;

if (!hasStockField) {
    // MISSING: JSON không có key stock_quantity.
} else if (rawStock == null) {
    // NULL: key tồn tại nhưng JSON value là null.
} else {
    // VALUE: phải kiểm tra kiểu và ràng buộc trước khi sử dụng.
}
~~~

Cách kiểm tra này giữ thông tin tồn tại của **key trong body**, thay vì chỉ đọc một `Integer`. Khi dữ liệu cần tính nhất quán, đọc body một lần và xử lý trên cùng snapshot; đừng gọi repository, sau đó gọi SDK riêng rồi giả định document không thể đổi giữa hai lần đọc.

Bên cạnh đó, kết quả `GetResult` còn có CAS metadata. Nếu cần cập nhật có điều kiện, phối hợp thao tác mutation theo CAS để chống ghi đè đồng thời.

## 13. CAS, transaction, TTL và reactive không loại bỏ sự khác biệt

| Cơ chế | Liên quan đến MISSING/NULL/default như thế nào? |
| --- | --- |
| **CAS / `@Version`** | Hai request cùng đọc rồi cập nhật field có thể xung đột; khi retry phải đọc lại và tính lại policy cho giá trị hiện hành |
| **Transaction** | Khi nhiều document phải cùng được migration/ghi theo bất biến nghiệp vụ, xem xét transaction đa document; một lệnh `save` mỗi document riêng không tự tạo transaction |
| **TTL / expiry** | Metadata hết hạn nằm ngoài JSON body; field JSON `expires_at:null` không tự đặt/xóa TTL |
| **SQL++ index** | Truy vấn MISSING/NULL có hành vi index riêng; `EXPLAIN` và index consistency quan trọng |
| **Reactive API** | `Mono<Product>`/`Flux<Product>` không tự giữ được trạng thái JSON đã mất khi ánh xạ thành `Integer null`; cần DTO/SDK/SQL++ nếu phải phân biệt |
| **Collection** | Cùng tên field có thể có hợp đồng khác nhau ở collections khác; áp dụng migration đúng keyspace và loại entity |

Giả sử service A viết `review_note:null` qua SQL++, còn service B đã đọc Product trước đó với CAS cũ. Lần `save` của B có thể bị từ chối do CAS mismatch. B không nên retry bằng cách ghi lại snapshot cũ: làm vậy có thể **khôi phục ghi chú đã được xóa**. Đọc lại dữ liệu và áp dụng lại ý định PATCH là yêu cầu quan trọng.

Reactive chỉ thay đổi cách điều phối I/O; nó không tạo ràng buộc schema hay quy tắc default mới. Nếu cần đọc document và PATCH với concurrency cao, vẫn phải kiểm tra CAS, giới hạn retry và side effects.

## 14. Test matrix: phân biệt đủ trạng thái trên Couchbase thật

Một bộ test tốt tạo fixture với **đúng JSON body**, rồi đọc/ghi qua các đường ứng dụng dùng thực tế.

| Fixture | JSON | Điều cần xác nhận |
| --- | --- | --- |
| A | `{"name":"A"}` | SQL++ `IS MISSING` đúng; entity nhận gì khi materialize? |
| B | `{"name":"B","stock_quantity":null}` | SQL++ `IS NULL` đúng; Java wrapper có null không? |
| C | `{"name":"C","stock_quantity":0}` | SQL++ `IS VALUED` đúng; Java giữ số 0 |
| D | `{"name":"D","stock_quantity":12}` | Java giữ số 12 |
| E | `{"name":"E","tags":[]}` | List rỗng, không bị coi là thiếu |
| F | `{"name":"F","tags":null}` | Xử lý null có chủ đích |
| G | `{"name":"G","stock_quantity":"12"}` | Sai kiểu; phải phát hiện/chính sách converter rõ |
| H | `{"name":"H","visibility":"DRAFT"}` | Giá trị mặc định đã persist, query/index thấy được |

### 14.1. SQL++ kiểm chứng ba trạng thái

~~~sql
SELECT META(p).id AS productKey,
       p.stock_quantity IS MISSING AS isMissing,
       p.stock_quantity IS NULL AS isNull,
       p.stock_quantity IS VALUED AS isValued,
       IFMISSING(p.stock_quantity, -1) AS missingFallback,
       IFMISSINGORNULL(p.stock_quantity, -2) AS anyFallback
FROM `shop`.`catalog`.`products` AS p
USE KEYS ["product::a", "product::b", "product::c", "product::d"];
~~~

Bài test cần so **field presence** trong kết quả, không chỉ so giá trị string. Nếu dùng DTO record mà mọi field đều bắt buộc, phải tính đến projection `MISSING` có thể làm thiếu component.

### 14.2. Kiểm tra idempotency của migration

Sau migration `visibility IS MISSING` → `DRAFT`, chạy lại migration trên cùng tập dữ liệu:

- Không có document nào bị cập nhật lần hai nếu `visibility` đã có.
- Document `visibility:null` vẫn giữ nguyên theo chính sách.
- Document `visibility:"PUBLIC"` không đổi.
- Writer khác có thể tạo document thiếu mới nếu chưa sửa code; phải kiểm tra luồng ghi đồng thời.
- Cần đo biến động CAS/expiry và index, không chỉ đếm số document.

### 14.3. Kiểm thử PATCH

Đối với `reviewNote`, tạo bốn request: field vắng mặt, `null`, `""`, chuỗi thật. Sau mỗi request, đọc **body JSON gốc** và xác nhận đúng ý nghĩa KEEP, SET_NULL, REMOVE hoặc SET_VALUE theo hợp đồng API. Nếu thay đổi được xác định là REMOVE, field phải **không còn key**, chứ không chỉ có Java `null`.

## 15. Sai lầm thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Java `int stockQuantity` bằng 0 dù dữ liệu cũ chưa có field | Primitive không giữ được trạng thái “chưa biết” | Dùng wrapper/trạng thái miền và kiểm tra dữ liệu cũ |
| API trả `DRAFT` nhưng SQL++ lọc DRAFT không thấy document | Default chỉ được áp dụng khi đọc, JSON vẫn MISSING | Đồng bộ query fallback hoặc migration có chủ đích |
| `IS NOT NULL` trả cả document thiếu field | Hiểu sai semantics SQL++ | Dùng `IS VALUED` để loại cả NULL và MISSING |
| `IFMISSING` không thay `null` | Hàm chỉ xử lý MISSING | Dùng `IFMISSINGORNULL` nếu hợp đồng cho phép gộp |
| PATCH không gửi field nhưng service lại xóa giá trị | DTO không theo dõi field presence | Kiểm tra JsonNode/presence, phân tách KEEP |
| PATCH gửi `null` nhưng DB vẫn không đổi | Mapper/patch handler bỏ qua null | Xác định SET_NULL hay REMOVE và dùng mutation rõ ràng |
| Java `tags` rỗng nhưng Couchbase không có field | Giá trị khởi tạo/constructor che mất MISSING | Kiểm tra JSON gốc và test materialization |
| Document cũ khiến record constructor ném lỗi | Field mới bắt buộc mà JSON cũ thiếu hoặc null | Reader tương thích hoặc migration có kiểm chứng |
| `IS VALUED` vẫn chấp nhận `stock_quantity:"12"` | `VALUED` không kiểm tra kiểu | Kiểm tra kiểu và miền giá trị riêng |
| `SET field=NULL` bị coi là xóa field | Nhầm NULL với MISSING | Dùng `UNSET` khi thực sự cần xóa key |
| Migration làm mất dữ liệu mới hơn | Ghi cạnh tranh, điều kiện WHERE không đủ | Dùng CAS/transaction hoặc batch có điều kiện và đối chiếu |
| Query MISSING chậm dù có index | Index không bao phủ MISSING/biểu thức fallback | Kiểm tra `EXPLAIN`, đổi index/query hoặc chuẩn hóa dữ liệu |
| TTL thay đổi sau migration | Tùy chọn expiry/preserve expiry chưa được thiết kế | Xác minh cách mutation xử lý expiry |
| API HTTP và JSON body Couchbase khác nhau | Jackson/DTO, mapper Couchbase là hai cơ chế | Phân biệt hợp đồng HTTP và persistence |

## 16. Bài thực hành: dữ liệu Order có trường giảm giá mới

**Đề bài:** hệ thống có `Order` trong `shop.sales.orders`. Field `discount_percent` mới được thêm ở schema phiên bản 2, nhưng document cũ của schema 1 chưa có. Quy tắc được đội nghiệp vụ xác nhận:

- **MISSING:** đơn schema cũ không có giảm giá; khi hiển thị có thể coi là `0` và migration sang `0`.
- **NULL:** giảm giá đang chờ kiểm duyệt; **không** tự đổi thành `0`.
- **Số `0`:** không có giảm giá và đã xác nhận.
- **Số dương `1..100`:** phần trăm giảm giá hợp lệ.
- **Số âm hoặc kiểu string:** dữ liệu sai cần đưa vào quy trình sửa.

Document mẫu:

~~~json
{"schema_version":1,"status":"CONFIRMED"}
~~~

~~~json
{"schema_version":2,"discount_percent":null,"status":"REVIEW"}
~~~

~~~json
{"schema_version":2,"discount_percent":0,"status":"CONFIRMED"}
~~~

### 16.1. Query hiển thị nhưng giữ NULL

~~~sql
SELECT META(o).id AS orderKey,
       o.discount_percent IS MISSING AS missingDiscount,
       o.discount_percent IS NULL AS pendingReview,
       IFMISSING(o.discount_percent, 0) AS effectiveDiscount
FROM `shop`.`sales`.`orders` AS o;
~~~

`effectiveDiscount` nhận `0` nếu MISSING, nhưng giữ `null` nếu đang REVIEW. UI phải hiểu `pendingReview` thay vì luôn in `0%`.

### 16.2. Migration chỉ dành cho schema cũ

~~~sql
UPDATE `shop`.`sales`.`orders` AS o
SET o.discount_percent = 0,
    o.schema_version = 2
WHERE o.schema_version = 1
  AND o.discount_percent IS MISSING;
~~~

Chỉ dùng truy vấn này sau khi backup, kiểm tra schema cũ và writer đồng thời. Khi field `discount_percent` có NULL, lệnh này **không đổi** nó, bất kể version là 1 hay 2. Những document thiếu `schema_version` phải được phân loại riêng.

### 16.3. Java code đọc dữ liệu đã ánh xạ

~~~java
public String discountLabel(Integer discountPercent) {
    if (discountPercent == null) {
        return "Chưa có kết quả giảm giá";
    }
    if (discountPercent < 0 || discountPercent > 100) {
        throw new IllegalArgumentException("Giảm giá không hợp lệ");
    }
    return discountPercent + "%";
}
~~~

Sau mapping, `Integer == null` **không đủ** để phân biệt MISSING với NULL, vì vậy logic áp `0` cho schema 1 phải dựa trên **đặc điểm schema nguồn hoặc giá trị đã được migration**, không tự chọn một trong hai khi chỉ còn `Integer`.

### Câu hỏi tự kiểm tra

1. **`{"x":null}` và `{}` có giống nhau không?** Không. Một cái là NULL, một cái là MISSING.
2. **`x IS NOT NULL` có loại MISSING trong SQL++ không?** Không; phải dùng `IS VALUED` nếu cần loại cả hai.
3. **`IFMISSING(x,0)` biến `null` thành 0 không?** Không.
4. **`IFMISSINGORNULL(x,0)` có biến `null` thành 0 không?** Có; chỉ dùng khi nghiệp vụ cho phép.
5. **Giá trị `false`, `0`, `""`, `[]` có phải MISSING?** Không; chúng là các giá trị JSON có mặt.
6. **`Integer` null có chứng minh JSON gốc có `"x":null` không?** Không; có thể là field MISSING.
7. **Thêm default vào constructor có sửa document cũ không?** Không, trừ khi sau đó ghi lại document hoặc chạy migration.
8. **`SET x=NULL` khác `UNSET x` thế nào?** SET tạo/giữ key với null; UNSET xóa key.
9. **PATCH `{}` có nên xóa một field không được gửi?** Không, nếu hợp đồng dùng thiếu field là KEEP.
10. **Có cần secondary index để `findById(key)` không?** Không, đó là KV theo document key.
11. **Reactive repository có giữ được MISSING/NULL nếu map cùng thành Java null không?** Không; I/O không chặn không tự giữ thông tin đã mất.
12. **CAS có đổi khi mutation field từ MISSING thành NULL không?** Có nếu document được ghi thành công; CAS thuộc metadata mutation.

## 17. Checklist áp dụng

- [ ] Viết hợp đồng nghiệp vụ rõ cho từng field: MISSING, NULL, VALUE và default.
- [ ] Không coi `0`, `false`, `""`, `[]`, `{}` là “không có giá trị”.
- [ ] Dùng `IS MISSING`, `IS NULL`, `IS VALUED` thay vì suy đoán theo so sánh với NULL.
- [ ] Chọn `IFMISSING` hoặc `IFMISSINGORNULL` theo đúng ý nghĩa muốn giữ/bỏ.
- [ ] Khi dùng `Integer`/`Boolean`/record, ghi rõ giới hạn thông tin mất sau mapping.
- [ ] Mọi default phải được đặt ở một tầng cụ thể: read fallback, factory nghiệp vụ hoặc migration.
- [ ] Không dùng constructor persistence để tự tạo dữ liệu lịch sử mới.
- [ ] Định nghĩa rõ hợp đồng PATCH: KEEP, SET_VALUE, SET_NULL, REMOVE.
- [ ] Dùng `UNSET` để xóa key, `SET NULL` để ghi literal null.
- [ ] Trước migration, thống kê MISSING/NULL/VALUE, sai kiểu và schema version cũ.
- [ ] Bảo vệ CAS, expiry và writer đồng thời khi cập nhật document.
- [ ] Kiểm tra `EXPLAIN` nếu truy vấn MISSING/NULL/fallback theo nhiều document.
- [ ] Xác minh hành vi converter với JSON thật, không chỉ unit test một Java constructor.
- [ ] Dùng DTO và policy rõ ràng khi HTTP JSON khác JSON được Spring Data lưu.

## Tài liệu tham khảo chính thức

- [Couchbase Server — SQL++ Data Types](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/datatypes.html): phân biệt MISSING và NULL trong mô hình dữ liệu SQL++.
- [Couchbase Server — Comparison Operators](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/comparisonops.html): `IS MISSING`, `IS NULL`, `IS VALUED` và toán tử so sánh.
- [Couchbase Server — Conditional Functions for Unknowns](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/condfununknown.html): `IFMISSING`, `IFNULL`, `IFMISSINGORNULL` và `COALESCE`.
- [Couchbase Server — UPDATE](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/update.html): `SET`, `UNSET`, điều kiện UPDATE và xử lý các field trong JSON.
- [Spring Data Couchbase — Modeling Entities](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): `@Field`, object creation, constructor, `@Id`/`@Version` và mapping.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): truy cập KV theo key, SQL++ query.
- [Spring Data Commons — Object Mapping Fundamentals](https://docs.spring.io/spring-data/commons/reference/object-mapping.html): constructor, record và property population khi dữ liệu có thể thiếu.
