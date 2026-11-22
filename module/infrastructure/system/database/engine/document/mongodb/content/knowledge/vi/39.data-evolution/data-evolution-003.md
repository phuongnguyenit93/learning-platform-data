# Đọc dữ liệu nhiều phiên bản và chuyển đổi khi đọc trong MongoDB

## 1. Bài toán: một collection, nhiều hình dạng document

Một dịch vụ tìm tin cho thuê nhà dùng MongoDB đã hoạt động nhiều năm. Trong thời gian đó, nhóm phát triển liên tục thay đổi yêu cầu:

- Ban đầu lưu tiền thuê bằng số nguyên VND trong trường **rent_vnd**.
- Sau đó lưu **monthly_rent_vnd** dưới dạng BSON Decimal128 để biểu diễn số thập phân rõ ràng.
- Ở phiên bản mới nhất, giá thuê được nhúng trong **pricing.monthly**, kèm currency.
- Địa chỉ lần lượt đổi từ **city** sang **location.city_code** rồi **address.city_code**.
- Trạng thái active boolean được thay bằng trạng thái xuất bản **PUBLISHED/DRAFT**.

MongoDB cho phép các document trong cùng collection có field names và cấu trúc khác nhau. Bởi vậy sau ba lần triển khai, collection có thể đồng thời chứa:

~~~text
Collection rental_listings_425
  |
  +-- Document A: schema v1 (không có schema_version)
  |      rent_vnd: Int64
  |      city: "HCM"
  |      active: true
  |
  +-- Document B: schema v2
  |      monthly_rent_vnd: Decimal128
  |      location.city_code: "HCM"
  |      status: "PUBLISHED"
  |
  +-- Document C: schema v3
         pricing.monthly.amount: Decimal128
         pricing.monthly.currency: "VND"
         address.city_code: "HCM"
         publication.status: "PUBLISHED"
~~~

API lại muốn trả một DTO thống nhất:

~~~json
{
  "id": "b425-v1",
  "title": "Studio gần công viên",
  "cityCode": "HCM",
  "monthlyRent": {
    "amount": "12500000.00",
    "currency": "VND"
  },
  "status": "PUBLISHED",
  "publishedAt": "2026-01-15T09:00:00Z"
}
~~~

Điểm cốt lõi là **đọc dữ liệu nhiều phiên bản và chuyển đổi khi đọc** (*schema-on-read transformation*). Đọc document cũ, xác định phiên bản, kiểm tra kiểu dữ liệu và chuyển về một mô hình chuẩn mà ứng dụng hiện tại hiểu; không nhất thiết phải viết lại hàng triệu document ngay trong ngày deploy.

~~~text
   MongoDB collection chứa v1 / v2 / v3
                  |
                  v
      Đọc raw BSON document
                  |
                  v
       Xác định schema version
                  |
          +-------+-------+
          |       |       |
         v1      v2      v3
          |       |       |
      Adapter1 Adapter2 Adapter3
          |       |       |
          +-------+-------+
                  |
                  v
          Canonical ListingView
                  |
                  v
             API response
~~~

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **schema version**, **document revision**, **application version** và **MongoDB server version**.
2. Lập hợp đồng cho nhiều dạng BSON document tồn tại song song.
3. Thiết kế **canonical read model** và adapter/upcaster cho từng phiên bản.
4. Xử lý cẩn thận **thiếu field, field null, sai BSON type, Decimal128, ngày giờ, enum và dữ liệu không rõ nghĩa**.
5. Thực hiện đọc đa phiên bản bằng **mongosh**, **Java MongoDB driver** hoặc **Spring Data MongoDB**.
6. Xây query và index đáp ứng các **đường dẫn field khác nhau** khi transition.
7. Phân biệt chuyển đổi **trong ứng dụng**, **trong aggregation pipeline** và **read-repair ghi ngược**.
8. Tránh làm mất update đồng thời khi lazy write-back bằng **compare-and-set** hoặc version guard.
9. Triển khai thay đổi theo **expand–migrate–contract** và rolling deployment.
10. Kiểm thử compatibility, đo lường tỷ lệ version, lỗi đọc và chi phí xử lý lâu dài.

> **Phạm vi và an toàn:** Bài thuộc **Database Engine Document MongoDB → Tiến hóa dữ liệu**. Các ví dụ chỉ dùng database **mongo_evolution_lab_425** và collection **rental_listings_425**, với các _id và labTag cố định. Phần đọc mặc định không thay đổi document; mọi ví dụ write-back được đánh dấu rõ ràng và chỉ nên chạy trên lab cô lập. Hành vi Java/Spring Data, converter và aggregation cần kiểm thử bằng đúng version thực tế.

## 2. Vì sao cùng một collection có nhiều schema?

### 2.1. MongoDB không tự bắt mọi document có cùng fields

MongoDB lưu BSON documents. Nếu không có **server-side schema validation** phù hợp, application có thể ghi:

~~~javascript
{ _id: "x1", rent_vnd: NumberLong("12500000") }
~~~

và:

~~~javascript
{
  _id: "x2",
  pricing: {
    monthly: {
      amount: NumberDecimal("12500000.00"),
      currency: "VND"
    }
  }
}
~~~

vào cùng collection.

Điều này hữu ích khi chuyển đổi schema từng bước, nhưng ứng dụng phải biết cách hiểu dữ liệu. **Schema linh hoạt không có nghĩa dữ liệu không cần hợp đồng.**

### 2.2. Deploy code không tự migrate documents

Giả sử Spring Data entity đổi:

~~~java
// Bản cũ:
@Field("rent_vnd")
private Long monthlyRent;

// Bản mới:
@Field("monthly_rent_vnd")
private BigDecimal monthlyRent;
~~~

Khi deploy class mới, MongoDB **không tự đổi tên trường trong documents cũ**. Nếu converter mới chỉ đọc monthly_rent_vnd, thuộc tính trong Java có thể là null dù document vẫn chứa rent_vnd.

### 2.3. Rolling deployment tạo nhiều phiên bản writer

Trong một deployment gồm nhiều pods:

~~~text
09:00  Pod A đang chạy app v2
09:01  Pod B chuyển sang app v3
09:03  Pod C vẫn chạy app v2
09:05  Tất cả chuyển sang app v3
~~~

Giữa 09:01 và 09:05, có thể đồng thời tồn tại:

- App v2 ghi schema v2.
- App v3 ghi schema v3.
- Các documents cũ v1/v2 chưa được backfill.

Ứng dụng mới phải **đọc được dữ liệu cũ đang còn**, trong khi application cũ cũng phải không bị hỏng vì document do phiên bản mới ghi nếu vẫn có khả năng đọc chúng.

### 2.4. Các nguồn tạo schema khác nhau

Ngoài rolling deployment còn có:

- Import batch từ hệ thống legacy.
- Mobile clients offline gửi lại dữ liệu cũ.
- Message consumers chạy khác phiên bản.
- Replication/migration từ datastore khác.
- Manual scripts hay job vận hành.
- Backfill dang dở sau một lỗi giữa chừng.
- Restore từ bản backup tạo trước migration.

Vì vậy, không nên suy luận rằng “đã deploy app v3” đồng nghĩa mọi document đều thuộc schema v3.

## 3. Bốn khái niệm phiên bản cần tách biệt

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Schema version** | schema_version: 3 | Hình dạng và ý nghĩa fields của document |
| **Document revision** | revision: 17 | Số lần thay đổi hoặc optimistic-lock token của một document |
| **Application version** | listing-service 4.8.2 | Phiên bản chương trình đọc/ghi |
| **MongoDB server version** | MongoDB 8.x | Phiên bản engine/API, khác hợp đồng schema |

### 3.1. schema_version

Ví dụ:

~~~javascript
{
  _id: "b425-v3",
  schema_version: 3,
  pricing: {
    monthly: {
      amount: NumberDecimal("12500000.00"),
      currency: "VND"
    }
  }
}
~~~

schema_version là **metadata do ứng dụng quy định**, không phải một field bắt buộc của MongoDB. Đặt tên cố định và mô tả bằng tài liệu/schema catalog.

### 3.2. revision

~~~javascript
{
  _id: "b425-v3",
  schema_version: 3,
  revision: NumberLong("17")
}
~~~

revision dùng làm **concurrency token** nếu tất cả writers tuân theo quy tắc optimistic locking. Việc chuyển schema v2 → v3 có thể tăng revision một lần, nhưng schema_version **không tự tăng mỗi khi sửa title hoặc giá thuê**.

### 3.3. App version

App v5 vẫn có thể đọc schema v1/v2/v3 trong nhiều năm. Ngược lại, một app v3 không nên mặc nhiên đọc được schema v4 nếu chưa triển khai adapter tương ứng.

### 3.4. Không dùng trường version mơ hồ

Nếu document có:

~~~javascript
{ version: 8 }
~~~

người đọc không biết đó là schema version hay optimistic-lock counter. Nên dùng tên rõ nghĩa như **schema_version** và **revision**, kèm field type và invariants.

## 4. Hợp đồng ba schema dùng xuyên suốt bài

Ta dùng một collection **rental_listings_425** và ba thế hệ hợp đồng.

### 4.1. Schema v1 — legacy không có version marker

~~~javascript
{
  _id: "b425-v1",
  labTag: "evolution425-v1",
  tenant_id: "tenant-001",
  title: "Studio gần công viên",
  rent_vnd: NumberLong("12500000"),
  city: "HCM",
  active: true,
  created_at: ISODate("2026-01-15T09:00:00Z")
}
~~~

Quy ước v1:

- **Không có schema_version**: coi là v1 **chỉ vì có hợp đồng lịch sử đã được chứng minh**.
- rent_vnd là số nguyên VND, không phải triệu VND và không phải cent.
- active=true có nghĩa tin đang xuất bản.
- created_at được hệ thống cũ dùng làm thời điểm xuất bản theo hợp đồng nghiệp vụ của ví dụ.

Nếu hệ thống thật dùng created_at là lúc tạo bản nháp, **không được tự biến nó thành publishedAt** chỉ vì cần một trường cho API mới.

### 4.2. Schema v2 — trường đổi tên, vẫn khá phẳng

~~~javascript
{
  _id: "b425-v2",
  labTag: "evolution425-v1",
  schema_version: 2,
  tenant_id: "tenant-001",
  title: "Căn hộ có ban công",
  monthly_rent_vnd: NumberDecimal("15000000.00"),
  location: {
    city_code: "HCM"
  },
  status: "PUBLISHED",
  published_at: ISODate("2026-01-16T09:00:00Z")
}
~~~

Quy ước v2:

- schema_version là BSON integer 2.
- Giá thuê là BSON Decimal128.
- City nằm trong **location.city_code**.
- status là enum string **PUBLISHED** hoặc **DRAFT**.
- published_at là BSON Date.

### 4.3. Schema v3 — nested pricing và publication

~~~javascript
{
  _id: "b425-v3",
  labTag: "evolution425-v1",
  schema_version: 3,
  tenant_id: "tenant-001",
  title: "Nhà phố ba phòng ngủ",
  pricing: {
    monthly: {
      amount: NumberDecimal("23000000.00"),
      currency: "VND"
    }
  },
  address: {
    city_code: "HN"
  },
  publication: {
    status: "PUBLISHED",
    published_at: ISODate("2026-01-17T09:00:00Z")
  }
}
~~~

Quy ước v3:

- Có explicit currency, ví dụ VND.
- Giá thuê được nhúng.
- City nằm trong **address.city_code**.
- Status và publishedAt nằm trong **publication**.

### 4.4. Bảng so sánh

| Ý nghĩa nghiệp vụ | v1 | v2 | v3 |
| --- | --- | --- | --- |
| Phiên bản | Không có marker | schema_version = 2 | schema_version = 3 |
| ID | _id String | _id String | _id String |
| Tenant | tenant_id | tenant_id | tenant_id |
| Tiêu đề | title | title | title |
| Số tiền | rent_vnd Int64 | monthly_rent_vnd Decimal128 | pricing.monthly.amount Decimal128 |
| Đơn vị tiền | Ngầm định VND | Ngầm định VND | pricing.monthly.currency |
| Thành phố | city | location.city_code | address.city_code |
| Trạng thái | active Boolean | status String | publication.status String |
| Ngày xuất bản | created_at Date | published_at Date | publication.published_at Date |

### 4.5. Quy tắc chuẩn hóa phải có tính nghiệp vụ

Ví dụ những chuyển đổi **đã được phê duyệt**:

~~~text
v1 rent_vnd: Int64 12500000
          -> Money(12500000.00, "VND")

v1 active: true
          -> PublicationStatus.PUBLISHED

v1 active: false
          -> PublicationStatus.DRAFT
          (chỉ khi hợp đồng cũ xác nhận false nghĩa là DRAFT)
~~~

Nếu v1 active=false còn bao gồm “đã xóa” hoặc “bị khóa”, ánh xạ hết thành DRAFT sẽ **làm mất nghĩa**. Cần thêm field lịch sử, một state riêng như UNKNOWN hoặc quy trình xử lý thủ công.

## 5. Canonical read model: một cách hiểu thống nhất

### 5.1. Không ép mọi tầng dùng raw BSON

Nếu business service phải liên tục viết:

~~~java
if (document.containsKey("rent_vnd")) {
    // legacy
} else if (document.containsKey("monthly_rent_vnd")) {
    // v2
} else {
    // v3
}
~~~

ở hàng chục endpoints, logic phiên bản sẽ lặp lại và khó sửa. Tốt hơn là tạo **một compatibility boundary**:

~~~text
MongoDB BSON v1/v2/v3
       |
       v
VersionedListingReader
       |
       v
ListingView (canonical)
       |
       +--> Search API
       +--> Rental pricing view
       +--> Recommendation service
       +--> Reporting
~~~

### 5.2. Read model Java

Giả sử domain dùng Java 17+:

~~~java
package com.example.mongo425.domain;

import java.math.BigDecimal;
import java.time.Instant;

public record Money(
    BigDecimal amount,
    String currency
) {}

public enum PublicationStatus {
    PUBLISHED,
    DRAFT
}

public record ListingView(
    String id,
    String tenantId,
    String title,
    Money monthlyRent,
    String cityCode,
    PublicationStatus status,
    Instant publishedAt
) {}
~~~

Trong Java, mỗi top-level public type phải ở file riêng theo tên type; các khối trên minh họa ba tệp **Money.java**, **PublicationStatus.java** và **ListingView.java**.

### 5.3. Invariants của ListingView

Một ListingView hợp lệ cho API của bài:

- id và tenantId là String không rỗng.
- title không rỗng.
- monthlyRent.amount là BigDecimal không âm.
- currency là **VND** cho cả ba schema của ví dụ.
- cityCode thuộc tập business cho phép (HCM, HN, DN trong lab).
- status thuộc enum đã biết.
- publishedAt là Instant hợp lệ.

Nếu không thể xây canonical view mà không phỏng đoán, reader nên **báo lỗi có kiểm soát**, thay vì trả object sai hoặc ngầm đặt tiền thuê thành 0.

### 5.4. Canonical read model khác canonical stored schema

Read model là **hình thức dữ liệu sau chuyển đổi trong bộ nhớ**. MongoDB vẫn có thể giữ v1/v2/v3:

~~~text
Read transformation:
  BSON v1 -> ListingView
  BSON v2 -> ListingView
  BSON v3 -> ListingView

Không có write:
  MongoDB vẫn giữ nguyên BSON v1/v2/v3
~~~

Chỉ khi ứng dụng thực hiện write-back/migration riêng thì dữ liệu lưu trữ mới thay đổi.

## 6. Xác định phiên bản document

### 6.1. Marker rõ ràng

Đối với v2/v3:

~~~javascript
{ schema_version: 2 }
{ schema_version: 3 }
~~~

Reader có thể dispatch trực tiếp:

~~~text
schema_version == 2 -> V2Adapter
schema_version == 3 -> V3Adapter
~~~

### 6.2. Thiếu marker ở dữ liệu lịch sử

Trong ví dụ, **không có schema_version** nghĩa là schema v1 vì nhóm đã xác nhận toàn bộ document legacy của collection trước ngày migration không có marker và tuân theo v1 contract.

Không dùng quy tắc này một cách mù quáng với dữ liệu import hoặc dữ liệu bị lỗi.

### 6.3. Missing khác null

~~~javascript
{ _id: "a" }                        // field missing
{ _id: "b", schema_version: null }   // explicit null
{ _id: "c", schema_version: "2" }    // string sai kiểu
{ _id: "d", schema_version: 2 }      // hợp lệ
~~~

**Không tự coi null hoặc string "2" là v2.** Nếu muốn hỗ trợ chúng, phải ghi hợp đồng và kiểm thử riêng; mặc định nên báo document malformed.

Trong mongosh:

~~~javascript
db.rental_listings_425.find({
  schema_version: { $exists: false }
});
~~~

tìm missing marker rõ hơn:

~~~javascript
db.rental_listings_425.find({
  schema_version: null
});
~~~

vì equality với null có thể match cả explicit null và missing.

### 6.4. Version tương lai

Nếu document có:

~~~javascript
{ schema_version: 4 }
~~~

mà application mới chỉ biết tới v3:

- **Không** tự chuyển v4 thành v3.
- **Không** tự bỏ qua field mới rồi save như v3.
- Báo **UnsupportedSchemaVersion** với thông tin đã lọc PII.
- Đưa vào metric/alert và xử lý bằng compatibility policy.

Điều này quan trọng khi rolling deploy hoặc khi app cũ vẫn đọc dữ liệu do app mới ghi.

### 6.5. Version là hợp đồng, không chỉ là số

Schema v3 không có nghĩa mọi document v3 đều hợp lệ. Một document có schema_version:3 nhưng thiếu pricing.monthly.amount vẫn có thể sai. Reader cần validate cả **cấu trúc và ý nghĩa** của từng version.

## 7. Các chiến lược chuyển đổi khi đọc

| Chiến lược | Nơi chuyển đổi | Có ghi lại DB không? | Khi nào phù hợp |
| --- | --- | --- | --- |
| **Application adapter** | Java service/repository boundary | Không | Có nhiều business rules, cần validation rõ |
| **Custom Spring converter** | MappingMongoConverter | Không mặc định | Cần tích hợp sâu vào mapping layer |
| **Aggregation projection** | MongoDB query pipeline | Không, nếu không dùng $merge/$out | Reporting/search projection, giảm lượng BSON truyền về |
| **Read-through cache normalize** | Cache/load layer | Thường không ghi source DB | Nhiều readers dùng canonical cache |
| **Lazy read-repair** | Reader đọc và ghi lại dạng mới | Có | Khi cần giảm dữ liệu legacy dần, có guardrails |
| **Offline backfill** | Batch migration job | Có | Cần canonicalize toàn collection độc lập với lượt đọc |

Không có giải pháp nào tốt nhất tuyệt đối. Adapter trong ứng dụng thường rõ ràng nhất khi conversion mang ý nghĩa nghiệp vụ; aggregation hữu ích khi cần lọc/group trên nhiều field paths; offline migration cần khi không muốn duy trì nhiều adapters vô thời hạn.

### 7.1. Adapter theo phiên bản

Ưu điểm:

- Version-specific contract nằm ở một chỗ.
- Dễ unit test với BSON fixtures.
- Có thể báo malformed data chính xác.
- Không vô tình làm thay đổi database khi chỉ đọc.

Nhược điểm:

- Mỗi read chịu chi phí chuyển đổi.
- Cần duy trì code cho nhiều versions.
- Query/index ở tầng MongoDB vẫn phải xử lý các field paths khác nhau.

### 7.2. Upcaster chain

Một cách tổ chức khác:

~~~text
Raw v1 -> upcast v1 to v2 -> upcast v2 to v3
Raw v2 --------------------> upcast v2 to v3
Raw v3 ------------------------------------> canonical
~~~

Ưu điểm là tái sử dụng bước biến đổi. Nhưng cần chú ý:

- Mỗi bước phải có hợp đồng rõ.
- Một bước sai có thể ảnh hưởng mọi phiên bản cũ.
- Version trung gian có thể yêu cầu fields mà schema cũ không có.
- Cần test chain và test từng bước riêng.

Khi chỉ có ba schema rất khác nhau, các adapter trực tiếp v1/v2/v3 → canonical đôi khi đơn giản hơn.

### 7.3. Projection và read model không phải writer schema

Reader có thể chuyển v1 thành ListingView nhưng writer mới nên có **một stored schema chính thức** (ví dụ v3). Đừng cho reader vô tình write back model v3 qua một API save không có kiểm soát.

## 8. Java: đọc raw BSON bằng MongoTemplate

### 8.1. Vì sao dùng raw Document cho lab?

Nếu một Java class chỉ có:

~~~java
@Field("pricing")
private Pricing pricing;
~~~

thì nó không tự biết cách đọc field legacy **rent_vnd** hay **monthly_rent_vnd** nếu không có conversion code. Dùng **org.bson.Document** cho boundary reader giúp nhìn đúng dữ liệu đã lưu.

Ứng dụng có thể:

1. Query bằng MongoTemplate.getCollection hoặc MongoDB driver.
2. Nhận BSON Document.
3. Dispatch theo schema_version.
4. Convert thành canonical read model.
5. Trả ListingView cho service/API.

### 8.2. Reader không thay đổi source

Trong ví dụ sau, reader **chỉ đọc**. Không gọi save/update trong adapter.

~~~java
package com.example.mongo425.read;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Date;

import org.bson.Document;
import org.bson.types.Decimal128;

import com.example.mongo425.domain.ListingView;
import com.example.mongo425.domain.Money;
import com.example.mongo425.domain.PublicationStatus;

public final class VersionedListingReader {

    public ListingView read(Document raw) {
        if (raw == null) {
            throw new IllegalArgumentException(
                "Document không được null"
            );
        }
        int version = detectVersion(raw);

        return switch (version) {
            case 1 -> readV1(raw);
            case 2 -> readV2(raw);
            case 3 -> readV3(raw);
            default -> throw new UnsupportedSchemaVersionException(
                "Không hỗ trợ schema_version=" + version
            );
        };
    }

    private int detectVersion(Document raw) {
        if (!raw.containsKey("schema_version")) {
            // Chỉ hợp lệ vì có contract legacy cho collection này.
            return 1;
        }

        Object value = raw.get("schema_version");
        if (!(value instanceof Integer version)) {
            throw new InvalidListingSchemaException(
                "schema_version phải là BSON Int32"
            );
        }

        if (version < 1) {
            throw new InvalidListingSchemaException(
                "schema_version phải dương"
            );
        }
        return version;
    }

    private ListingView readV1(Document raw) {
        String id = requiredString(raw, "_id");
        String tenant = requiredString(raw, "tenant_id");
        String title = requiredString(raw, "title");
        String city = requiredString(raw, "city");

        Object rent = raw.get("rent_vnd");
        if (!(rent instanceof Integer)
                && !(rent instanceof Long)) {
            throw new InvalidListingSchemaException(
                "v1 rent_vnd phải là Int32 hoặc Int64"
            );
        }
        BigDecimal amount = BigDecimal.valueOf(
            ((Number) rent).longValue()
        );

        Object active = raw.get("active");
        if (!(active instanceof Boolean flag)) {
            throw new InvalidListingSchemaException(
                "v1 active phải là Boolean"
            );
        }

        return canonical(
            id, tenant, title,
            new Money(amount, "VND"),
            city,
            flag ? PublicationStatus.PUBLISHED
                 : PublicationStatus.DRAFT,
            requiredInstant(raw, "created_at")
        );
    }

    private ListingView readV2(Document raw) {
        String id = requiredString(raw, "_id");
        String tenant = requiredString(raw, "tenant_id");
        String title = requiredString(raw, "title");

        Document location = requiredDocument(
            raw, "location"
        );

        return canonical(
            id, tenant, title,
            new Money(
                requiredDecimal128(
                    raw, "monthly_rent_vnd"
                ),
                "VND"
            ),
            requiredString(location, "city_code"),
            requiredStatus(raw, "status"),
            requiredInstant(raw, "published_at")
        );
    }

    private ListingView readV3(Document raw) {
        String id = requiredString(raw, "_id");
        String tenant = requiredString(raw, "tenant_id");
        String title = requiredString(raw, "title");

        Document pricing = requiredDocument(
            raw, "pricing"
        );
        Document monthly = requiredDocument(
            pricing, "monthly"
        );
        Document address = requiredDocument(
            raw, "address"
        );
        Document publication = requiredDocument(
            raw, "publication"
        );

        return canonical(
            id, tenant, title,
            new Money(
                requiredDecimal128(monthly, "amount"),
                requiredString(monthly, "currency")
            ),
            requiredString(address, "city_code"),
            requiredStatus(publication, "status"),
            requiredInstant(publication, "published_at")
        );
    }

    private static ListingView canonical(
            String id,
            String tenant,
            String title,
            Money money,
            String city,
            PublicationStatus status,
            Instant publishedAt) {
        if (money.amount().signum() < 0) {
            throw new InvalidListingSchemaException(
                "Giá thuê âm"
            );
        }
        if (!"VND".equals(money.currency())) {
            throw new InvalidListingSchemaException(
                "Lab chỉ hỗ trợ currency VND"
            );
        }
        return new ListingView(
            id, tenant, title, money, city,
            status, publishedAt
        );
    }

    private static String requiredString(
            Document source,
            String key) {
        Object value = source.get(key);
        if (!(value instanceof String result)
                || result.isBlank()) {
            throw new InvalidListingSchemaException(
                "Thiếu/sai String field: " + key
            );
        }
        return result;
    }

    private static Document requiredDocument(
            Document source,
            String key) {
        Object value = source.get(key);
        if (!(value instanceof Document nested)) {
            throw new InvalidListingSchemaException(
                "Thiếu/sai embedded document: " + key
            );
        }
        return nested;
    }

    private static BigDecimal requiredDecimal128(
            Document source,
            String key) {
        Object value = source.get(key);
        if (!(value instanceof Decimal128 decimal)) {
            throw new InvalidListingSchemaException(
                "Thiếu/sai Decimal128 field: " + key
            );
        }
        return decimal.bigDecimalValue();
    }

    private static Instant requiredInstant(
            Document source,
            String key) {
        Object value = source.get(key);
        if (!(value instanceof Date date)) {
            throw new InvalidListingSchemaException(
                "Thiếu/sai BSON Date field: " + key
            );
        }
        return date.toInstant();
    }

    private static PublicationStatus requiredStatus(
            Document source,
            String key) {
        String name = requiredString(source, key);
        try {
            return PublicationStatus.valueOf(name);
        } catch (IllegalArgumentException badStatus) {
            throw new InvalidListingSchemaException(
                "Trạng thái không hỗ trợ: " + name
            );
        }
    }
}
~~~

Các exception được định nghĩa riêng:

~~~java
package com.example.mongo425.read;

public class InvalidListingSchemaException
        extends RuntimeException {
    public InvalidListingSchemaException(String message) {
        super(message);
    }
}
~~~

~~~java
package com.example.mongo425.read;

public class UnsupportedSchemaVersionException
        extends RuntimeException {
    public UnsupportedSchemaVersionException(String message) {
        super(message);
    }
}
~~~

Mỗi public class phải nằm trong file Java đúng tên. Đoạn mẫu sử dụng **Java 17 pattern matching cho instanceof** và **switch expression**.

### 8.3. Tại sao không âm thầm coerce mọi kiểu dữ liệu?

Những trường hợp:

~~~javascript
{ rent_vnd: "12500000" }
{ rent_vnd: 12500000.99 }
{ monthly_rent_vnd: NumberDouble(12500000.5) }
~~~

đều có thể **trông giống một giá thuê** nhưng không đúng hợp đồng ví dụ.

Nếu reader tự:

~~~java
new BigDecimal(raw.get("rent_vnd").toString())
~~~

thì nó có thể biến dữ liệu sai thành dữ liệu hợp lệ giả tạo, che mất lỗi writer/import và gây sai số tiền. Tốt hơn là explicit compatibility rule cho từng kiểu đã được kiểm chứng.

### 8.4. Vì sao BigDecimal.valueOf với v1?

v1 contract là Int32/Int64 **đơn vị VND**. Chuyển thành BigDecimal từ long là phép đổi **không mất đơn vị tiền**.

Không tự nhân hoặc chia 1.000.000 nếu schema cũ không nói rent_vnd là triệu VND.

### 8.5. Decimal128 và Decimal128 vô hạn

MongoDB Decimal128 có những giá trị đặc biệt theo BSON/IEEE 754 Decimal128. Chuyển thành BigDecimal Java có thể không hợp lệ với NaN/Infinity. Reader nên coi chúng là **invalid price**, không dùng làm giá thuê.

Code ví dụ sẽ không chấp nhận chuyển đổi khi Decimal128 không thể tạo BigDecimal hữu hạn. Một production adapter có thể bắt conversion exception và chuyển thành domain-specific error để ghi metrics phù hợp.

### 8.6. Trường không có trong ListingView

Raw document có thể chứa:

~~~javascript
{ legacy_note: "imported-2019" }
~~~

Reader không đưa trường này vào API. Việc **không giữ legacy_note trong read model** không có nghĩa nó đã bị xóa khỏi MongoDB.

Nếu sau khi đọc, ứng dụng lấy ListingView rồi **save thay thế raw document**, unknown fields có thể bị mất. Cần tách rõ **read-only projection** và **write model**.

## 9. Dùng reader cùng Spring Data MongoDB

### 9.1. Read adapter với MongoTemplate

~~~java
package com.example.mongo425.read;

import com.example.mongo425.domain.ListingView;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ListingReadRepository {

    private final MongoTemplate template;
    private final VersionedListingReader reader;

    public ListingReadRepository(
            MongoTemplate template) {
        this.template = template;
        this.reader = new VersionedListingReader();
    }

    public ListingView findForTenant(
            String id,
            String authenticatedTenantId) {
        Document filter = new Document("_id", id)
            .append("tenant_id", authenticatedTenantId);

        Document raw = template
            .getCollection("rental_listings_425")
            .find(filter)
            .first();

        return raw == null ? null : reader.read(raw);
    }
}
~~~

Trong ví dụ:

- **MongoTemplate.getCollection()** trả collection API của MongoDB Java driver với raw Document.
- Filter sử dụng **stored BSON names** như tenant_id.
- Reader chuyển về ListingView.
- Không thực hiện save/update.

### 9.2. Tenant authorization phải trước conversion

Đúng:

~~~javascript
{
  _id: requestedId,
  tenant_id: authenticatedTenantId
}
~~~

Thiếu tenant filter:

~~~javascript
{ _id: requestedId }
~~~

có thể làm service lấy document của tenant khác rồi đưa vào reader, gây lộ dữ liệu hoặc tạo log không phù hợp. **Không lấy tenantId do client tự khai báo mà chưa xác thực**.

Read compatibility không được làm suy yếu authorization, visibility và data residency.

### 9.3. Khi nào dùng Spring custom converter?

Spring Data có **custom conversions** để ánh xạ BSON thành kiểu Java chuyên biệt. Có thể tạo một **@ReadingConverter** để giảm việc gọi adapter thủ công ở nhiều repository.

Nhưng custom converter cần cân nhắc:

- Converter được áp dụng ở điểm nào của mapping lifecycle.
- Có cần type metadata/_class không.
- Có xung đột với built-in conversions không.
- Những types nào được converter nhận diện.
- Query mapping và write conversion có đối xứng không.
- Có vô tình dùng converter để **save** một read model hay không.

Với dữ liệu ba version có rules khác nhau, **explicit boundary reader** thường dễ kiểm soát hơn. Khi dùng custom converter, cần integration tests rõ ràng với MongoDB thật, nhất là trên dữ liệu legacy không có _class.

### 9.4. Read model và persistence entity không bắt buộc là một class

~~~text
Stored documents (heterogeneous)
        |
VersionedListingReader
        |
ListingView (immutable read DTO)

Write API
        |
Validated ListingWriteCommand
        |
CurrentSchemaWriter (schema v3)
        |
MongoDB
~~~

Tách như vậy ngăn nguy cơ business code save một object đã được chuẩn hóa nhưng không chứa đầy đủ raw fields.

## 10. Unit test từng adapter

### 10.1. Lợi ích của raw BSON fixtures

Test không cần MongoDB thật để kiểm tra **chuyển đổi thuần Java Document → ListingView**. Đó là unit test vì adapter không gọi I/O.

Ví dụ với JUnit Jupiter:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Date;

import org.bson.Document;
import org.junit.jupiter.api.Test;

class VersionedListingReaderTest {

    private final VersionedListingReader reader =
        new VersionedListingReader();

    @Test
    void legacyV1WithoutMarkerConvertsToCanonical() {
        Document raw = new Document("_id", "b425-v1")
            .append("tenant_id", "tenant-001")
            .append("title", "Studio")
            .append("rent_vnd", 12500000L)
            .append("city", "HCM")
            .append("active", true)
            .append(
                "created_at",
                Date.from(Instant.parse(
                    "2026-01-15T09:00:00Z"
                ))
            );

        ListingView view = reader.read(raw);

        assertEquals("b425-v1", view.id());
        assertEquals("HCM", view.cityCode());
        assertEquals(
            new BigDecimal("12500000"),
            view.monthlyRent().amount()
        );
        assertEquals("VND", view.monthlyRent().currency());
        assertEquals(
            PublicationStatus.PUBLISHED,
            view.status()
        );
    }

    @Test
    void unknownVersionIsNotSilentlyDowngraded() {
        Document future = new Document("_id", "b425-v4")
            .append("schema_version", 4);

        assertThrows(
            UnsupportedSchemaVersionException.class,
            () -> reader.read(future)
        );
    }

    @Test
    void nullMarkerIsNotLegacyV1() {
        Document invalid = new Document("_id", "b425-null")
            .append("schema_version", null);

        assertThrows(
            InvalidListingSchemaException.class,
            () -> reader.read(invalid)
        );
    }
}
~~~

Thêm imports tới domain/read packages theo project thực tế. Mục tiêu của snippet là mô tả các assertions quan trọng.

### 10.2. Test v2/v3

Unit fixtures cần có:

- v2 với **Decimal128**, location.city_code, status, published_at.
- v3 với pricing.monthly.amount/currency, address và publication.
- Cùng giá trị tiền/city/status cho các versions phải tạo **ListingView tương đương**.
- v3 currency không hỗ trợ bị từ chối, không tự đổi ngoại tệ.

### 10.3. Test malformed BSON

| Tình huống | Kỳ vọng |
| --- | --- |
| Không có schema_version nhưng rent_vnd missing | Invalid schema |
| schema_version: null | Invalid schema |
| schema_version: "3" | Invalid schema |
| schema_version: 99 | Unsupported schema |
| rent_vnd là String | Invalid schema |
| monthly_rent_vnd là Double | Invalid schema |
| pricing.monthly.amount missing | Invalid schema |
| publication.status = "BLOCKED" | Invalid/unsupported status |
| _id không phải String theo contract | Invalid schema |
| tenant_id rỗng | Invalid schema |
| Giá thuê âm | Invalid schema |
| published_at không phải Date | Invalid schema |

Đừng chỉ test ba happy-path fixtures rồi kết luận adapter chịu được toàn bộ dữ liệu legacy.

### 10.4. Property-based tests

Nếu dự án có property-based testing, có thể kiểm tra:

> Với mọi giá nguyên v1 hợp lệ trong miền tiền thuê và currency=VND, chuyển v1 sang canonical không làm đổi giá trị số học.

Nhưng generator phải tôn trọng giới hạn domain; không ngầm chấp nhận negative price, overflow hoặc kiểu dữ liệu sai.

## 11. Integration test với MongoDB thật

### 11.1. Vì sao unit test chưa đủ?

Java unit test dùng **new Document(...)**, nhưng MongoDB server có thể lưu/đọc:

- BSON Int32 hoặc Int64 theo từng thao tác.
- BSON Decimal128.
- BSON Date với precision mili giây.
- Nested Document và Array.
- Fields thiếu/null.

Integration test cần xác nhận các **BSON types thực** thông qua driver và server.

### 11.2. Tạo test collection riêng

Với Spring Boot và Testcontainers MongoDB (version phù hợp):

~~~java
@DataMongoTest
@Testcontainers
class VersionedListingRepositoryIntegrationTest {

    @Container
    static MongoDBContainer mongo =
        new MongoDBContainer(
            DockerImageName.parse("mongo:7.0")
        );

    @DynamicPropertySource
    static void configure(
            DynamicPropertyRegistry registry) {
        registry.add(
            "spring.data.mongodb.uri",
            mongo::getReplicaSetUrl
        );
    }

    @Autowired MongoTemplate template;

    // Seed raw v1/v2/v3 trong container riêng.
    // Đọc qua ListingReadRepository, assert ListingView.
}
~~~

Các imports và Testcontainers module coordinates phải phù hợp với phiên bản Testcontainers/Spring Boot cụ thể. Đây là **khung test**, không phải một file Java hoàn chỉnh có thể compile chỉ bằng copy đoạn này.

### 11.3. Các assertions quan trọng

- Reader nhận document legacy v1 không có marker.
- Reader nhận explicit v2/v3 từ database thật.
- Decimal128 được driver trả đúng kiểu.
- Date đổi thành Instant đúng timestamp.
- Filter tenant_id ngăn cross-tenant lookup.
- Thêm document schema_version=4 gây lỗi có kiểm soát, không làm service ghi dữ liệu.
- Document read **không bị sửa** sau invocation; đọc lại raw BSON để kiểm tra.

### 11.4. Không dùng production để reset fixture

Một test gọi **deleteMany({})** có thể xóa toàn collection nếu URI bị cấu hình sai. Chỉ sử dụng thao tác này khi **đã xác minh MongoDB Testcontainer hoàn toàn cô lập**. Có thể thêm fail-fast guard cho database name, URI, credentials và network policy.

## 12. Query đa phiên bản: đọc được không đồng nghĩa tìm được

### 12.1. Bẫy lớn nhất của adapter

Đọc theo _id:

~~~text
findById -> raw v1 -> adapter -> ListingView
~~~

có thể hoạt động hoàn hảo. Nhưng API tìm kiếm theo city:

~~~javascript
db.rental_listings_425.find({
  "address.city_code": "HCM"
});
~~~

chỉ trả v3; nó **không tìm thấy v1/v2** vì field names khác.

Vì vậy **read compatibility gồm hai vấn đề độc lập**:

1. **Query compatibility**: MongoDB có tìm đúng documents không?
2. **Materialization compatibility**: tìm thấy rồi thì có convert đúng không?

### 12.2. $or theo phiên bản

Trong mongosh:

~~~javascript
db.rental_listings_425.find({
  tenant_id: "tenant-001",
  $or: [
    {
      schema_version: { $exists: false },
      city: "HCM"
    },
    {
      schema_version: 2,
      "location.city_code": "HCM"
    },
    {
      schema_version: 3,
      "address.city_code": "HCM"
    }
  ]
});
~~~

Query chỉ dùng những đường dẫn đã định nghĩa trong hợp đồng. Điều kiện schema_version giúp tránh một document v3 còn giữ legacy field city sai lệch vô tình match nhánh v1.

### 12.3. Phải filter tenant đúng

Với multi-tenant application, thêm tenant_id từ **identity đã xác thực** vào query gốc là bắt buộc. Không nên:

~~~javascript
db.rental_listings_425.find({
  $or: [ /* cities */ ]
});
~~~

rồi lọc tenant trong Java sau khi đã load toàn bộ documents của các tenants khác. Điều đó tăng nguy cơ lộ dữ liệu và chi phí I/O.

### 12.4. Chỉ filter sau khi convert có ổn không?

Ý tưởng:

~~~text
Load 1.000.000 docs
  -> convert tất cả
  -> filter cityCode="HCM" trong Java
~~~

thường không hợp lý vì:

- Quét và truyền rất nhiều dữ liệu.
- Phân trang/sort/count bị sai semantics.
- Tốn bộ nhớ và CPU của app.
- Có thể làm hỏng bảo mật nếu tenant filter không nằm ở database.

Nếu dataset nhỏ/lab có thể dùng để minh họa, nhưng production cần query strategy và indexes phù hợp.

### 12.5. Sort qua nhiều trường thời gian

v1 dùng **created_at**, v2 dùng **published_at**, v3 dùng **publication.published_at**. Nếu query sort:

~~~javascript
.sort({ "publication.published_at": -1 })
~~~

v1/v2 không có field đó; thứ tự tổng không còn thể hiện thời điểm xuất bản như yêu cầu.

Muốn một **sort canonical** trên mixed versions:

- Normalize field trong aggregation và sort sau đó; hoặc
- Backfill một trường **stable sort key** chung; hoặc
- Tách các queries theo version, merge theo thời gian ở application với cơ chế phân trang chặt chẽ; hoặc
- Migrate trước khi bật chức năng phụ thuộc sort.

Phân trang theo offset trên tập dữ liệu nhiều phiên bản có sorting không nhất quán rất dễ gây duplicates/missing rows.

## 13. Index strategy trong giai đoạn có ba schema

### 13.1. Các field paths khác nhau cần kế hoạch index

Ví dụ query thành phố:

~~~javascript
{
  tenant_id: "tenant-001",
  city: "HCM"
}
~~~

và:

~~~javascript
{
  tenant_id: "tenant-001",
  "location.city_code": "HCM"
}
~~~

và:

~~~javascript
{
  tenant_id: "tenant-001",
  "address.city_code": "HCM"
}
~~~

có thể cần **các compound indexes khác nhau** trong giai đoạn chuyển tiếp.

### 13.2. Ví dụ indexes của lab

~~~javascript
const listings = db
  .getSiblingDB("mongo_evolution_lab_425")
  .getCollection("rental_listings_425");

listings.createIndex(
  { tenant_id: 1, city: 1 },
  { name: "ix425_v1_tenant_city" }
);

listings.createIndex(
  {
    tenant_id: 1,
    schema_version: 1,
    "location.city_code": 1
  },
  { name: "ix425_v2_tenant_city" }
);

listings.createIndex(
  {
    tenant_id: 1,
    schema_version: 1,
    "address.city_code": 1
  },
  { name: "ix425_v3_tenant_city" }
);
~~~

Đây là ví dụ index cho collection **lab**. Không tạo cả ba index trong production chỉ vì có ba schema: phải xem query patterns, selectivity, write overhead, dung lượng và plan thực tế.

### 13.3. $or có nhất thiết dùng indexes?

Không. Optimizer chọn plan dựa trên thống kê, số documents và predicates. Với $or, mỗi nhánh có index phù hợp thường giúp tăng khả năng thực thi hiệu quả, nhưng **không bảo đảm** query sẽ chọn đúng tất cả indexes.

Kiểm tra:

~~~javascript
listings.find({
  tenant_id: "tenant-001",
  $or: [
    {
      schema_version: { $exists: false },
      city: "HCM"
    },
    {
      schema_version: 2,
      "location.city_code": "HCM"
    },
    {
      schema_version: 3,
      "address.city_code": "HCM"
    }
  ]
}).explain("executionStats");
~~~

Đọc **winningPlan**, **totalKeysExamined**, **totalDocsExamined**, **nReturned** và query latency ở môi trường đại diện.

### 13.4. Mức giá phải so theo cùng đơn vị

v1 Int64 VND, v2 Decimal128 VND và v3 Decimal128 VND. MongoDB có cơ chế so sánh numeric BSON types, nhưng việc chuẩn hóa:

- Không cho phép thiếu currency ở v3.
- Không được tự giả định currencies khác VND có cùng giá trị.
- Không được tự đổi tiền theo tỷ giá thời điểm hiện tại nếu hợp đồng muốn lưu giá trị lịch sử.

Nếu schema v1 dùng số tiền theo **triệu VND** thay vì VND, query range trực tiếp trên v1 và v3 không còn so cùng đại lượng.

### 13.5. Tránh duy trì index legacy vô thời hạn

Khi không còn v1/v2 và không còn old writers:

1. Xác minh version distribution.
2. Xác minh queries không dùng legacy fields.
3. So sánh index usage/performance.
4. Gỡ index cũ theo change procedure.

Mỗi index thêm chi phí storage và write maintenance, nên read compatibility có giá vận hành thật.

## 14. Chuyển đổi trong aggregation pipeline

### 14.1. Khi nào dùng aggregation?

Nếu cần:

- Search theo canonical city.
- Sort theo canonical publishedAt.
- Tính tổng thống kê giữa nhiều versions.
- Trả projection nhỏ mà không materialize toàn raw document ở application.

thì aggregation có thể giúp. Ví dụ chỉ là **read-only pipeline**; không có $merge hoặc $out.

### 14.2. Normalize schema version

Với v1 thiếu marker, cần phân biệt missing và explicit null:

~~~javascript
{
  $set: {
    normalized_version: {
      $cond: [
        {
          $eq: [
            { $type: "$schema_version" },
            "missing"
          ]
        },
        1,
        "$schema_version"
      ]
    }
  }
}
~~~

Không dùng **$ifNull** một cách vô thức nếu explicit schema_version:null phải được phân loại malformed thay vì legacy.

### 14.3. Pipeline chuẩn hóa city, rent, ngày

Trong mongosh, trên database lab:

~~~javascript
const lab = db.getSiblingDB("mongo_evolution_lab_425");
const listings = lab.getCollection("rental_listings_425");

const pipeline = [
  {
    $match: {
      labTag: "evolution425-v1",
      tenant_id: "tenant-001"
    }
  },
  {
    $set: {
      normalized_version: {
        $cond: [
          {
            $eq: [
              { $type: "$schema_version" },
              "missing"
            ]
          },
          1,
          "$schema_version"
        ]
      }
    }
  },
  {
    $set: {
      canonical_city: {
        $switch: {
          branches: [
            {
              case: {
                $eq: ["$normalized_version", 1]
              },
              then: "$city"
            },
            {
              case: {
                $eq: ["$normalized_version", 2]
              },
              then: "$location.city_code"
            },
            {
              case: {
                $eq: ["$normalized_version", 3]
              },
              then: "$address.city_code"
            }
          ],
          default: null
        }
      },
      canonical_rent_vnd: {
        $switch: {
          branches: [
            {
              case: {
                $eq: ["$normalized_version", 1]
              },
              then: { $toDecimal: "$rent_vnd" }
            },
            {
              case: {
                $eq: ["$normalized_version", 2]
              },
              then: "$monthly_rent_vnd"
            },
            {
              case: {
                $eq: ["$normalized_version", 3]
              },
              then: "$pricing.monthly.amount"
            }
          ],
          default: null
        }
      },
      canonical_published_at: {
        $switch: {
          branches: [
            {
              case: {
                $eq: ["$normalized_version", 1]
              },
              then: "$created_at"
            },
            {
              case: {
                $eq: ["$normalized_version", 2]
              },
              then: "$published_at"
            },
            {
              case: {
                $eq: ["$normalized_version", 3]
              },
              then: "$publication.published_at"
            }
          ],
          default: null
        }
      }
    }
  },
  {
    $match: {
      normalized_version: { $in: [1, 2, 3] },
      canonical_city: "HCM"
    }
  },
  {
    $project: {
      _id: 1,
      tenant_id: 1,
      title: 1,
      normalized_version: 1,
      canonical_city: 1,
      canonical_rent_vnd: 1,
      canonical_published_at: 1
    }
  },
  {
    $sort: {
      canonical_published_at: -1,
      _id: 1
    }
  }
];

printjson(listings.aggregate(pipeline).toArray());
~~~

**Lưu ý an toàn/ngữ nghĩa:** Pipeline trên minh họa normalization cho dữ liệu **đã được kiểm tra hợp đồng**, không là thay thế đầy đủ cho validation trong Java reader:

- Unknown versions bị loại bởi $match; **không dùng kết quả này để kết luận tất cả documents đã được đọc**.
- Nếu v1 rent_vnd chứa string sai, **$toDecimal** có thể chuyển đổi theo behavior MongoDB hoặc gây lỗi; cần prevalidate input để tránh âm thầm hợp thức hóa dữ liệu xấu.
- Nếu trường thiếu, canonical field có thể null/missing.
- Pipeline không đảm bảo currency VND cho v3.
- Expression-based normalization có thể làm việc tận dụng index của sort/filter phức tạp hơn.

Với production, tách bước **phát hiện invalid/unknown** khỏi pipeline báo cáo để không giấu dữ liệu lỗi.

### 14.4. Sort sau normalize có trade-off

Sort theo **canonical_published_at** được tạo trong pipeline không nhất thiết tận dụng trực tiếp index trên các source fields. Với dữ liệu lớn có thể:

- Tăng CPU/memory.
- Tăng execution time.
- Cần xử lý spill/limits theo deployment.

Nếu API phải phân trang hàng triệu documents, **backfill một field canonical phục vụ sort** có thể phù hợp hơn việc luôn tính toán mỗi lần đọc.

### 14.5. Aggregation không thực hiện magic migration

Chạy:

~~~javascript
listings.aggregate(pipeline);
~~~

không sửa documents trừ khi pipeline chứa những stage có side effects như **$merge** hoặc **$out** (với quyền và điều kiện phù hợp). Các fields canonical_city và canonical_rent_vnd trong ví dụ chỉ nằm ở **kết quả trả về**.

## 15. Tính đúng đắn khi chuyển đổi dữ liệu

### 15.1. Lossless vs lossy

Một phép chuyển đổi **lossless theo hợp đồng** giữ đủ thông tin cần thiết để biểu diễn cùng nghĩa nghiệp vụ.

Ví dụ:

~~~text
rent_vnd Int64 12500000
  -> Decimal128/BigDecimal 12500000.00
~~~

giữ nguyên giá trị số học VND.

Một phép chuyển đổi có thể **lossy**:

~~~text
status = "BANNED"
  -> active = false
~~~

vì không thể khôi phục sự khác nhau giữa BANNED, ARCHIVED và DRAFT từ boolean false.

### 15.2. Invariant cần giữ

- Tiền thuê không đổi đơn vị/giá trị.
- Không bỏ tenantId.
- Không biến trạng thái bị khóa thành trạng thái xuất bản.
- Ngày giờ không bị đổi timezone sai.
- _id giữ nguyên identity.
- Chỉ hiển thị fields mà actor được phép xem.
- Không tự điền PII/default không có căn cứ.

### 15.3. Giá trị mặc định nguy hiểm

Sai:

~~~java
BigDecimal rent = missing
    ? BigDecimal.ZERO
    : parsedRent;
~~~

Nếu tiền thuê không tồn tại, đặt 0 có thể làm tin xuất hiện trong kết quả “giá rẻ”, gây sai nghiệp vụ.

Tùy contract, nên:

- Báo dữ liệu không hợp lệ.
- Trả field null với API contract rõ.
- Ẩn listing khỏi search và đưa vào repair queue.
- Dùng known historical default chỉ khi được phê duyệt.

### 15.4. Null và missing

Ba trạng thái cần xét:

~~~javascript
{ /* field không tồn tại */ }
{ field: null }
{ field: "" }
~~~

Không phải lúc nào cả ba cùng nghĩa. Trong migration, field missing có thể nói “schema cũ”, explicit null có thể nói “người dùng chưa cung cấp”, còn string rỗng có thể là lỗi input.

### 15.5. UTC và Date

MongoDB BSON Date lưu timestamp, trong Java driver thường materialize thành **java.util.Date** và chuyển bằng **toInstant()**.

Không biến thời điểm:

~~~text
2026-01-15T09:00:00Z
~~~

thành local datetime rồi gắn timezone tùy tiện. Nếu nghiệp vụ cần múi giờ của địa điểm (ví dụ lịch hẹn tại Việt Nam), giữ ZoneId riêng theo contract.

### 15.6. Currency phải explicit khi mở rộng thị trường

Trong ví dụ v1/v2 mặc định VND vì legacy contract đã quy định. Nếu sau này có listings USD/SGD, không được chuyển giá v3 thành VND theo tỷ giá “hiện tại” trong reader mà không có thời điểm và nguồn tỷ giá lịch sử rõ.

Schema evolution về currency có thể cần một **version mới** và policy riêng.

## 16. Chiến lược mixed-schema read khi dùng Spring Data Repository

### 16.1. Một @Document class cho v3 có đủ không?

~~~java
@Document("rental_listings_425")
public class ListingEntity {
    @Field("pricing")
    private Pricing pricing;
}
~~~

Class này mô tả **v3**, không tự ánh xạ **rent_vnd** và **monthly_rent_vnd** của v1/v2 thành pricing.

Nếu Spring Data findById đọc v1 vào entity v3 mà không có converter phù hợp, pricing có thể null và code business gặp lỗi.

### 16.2. Hai lựa chọn

**Lựa chọn A — read adapter riêng:**

~~~text
MongoTemplate raw Document
 -> VersionedListingReader
 -> ListingView
~~~

**Lựa chọn B — mapping custom converters:**

~~~text
MongoRepository / MongoTemplate
 -> MappingMongoConverter + ReadingConverter
 -> ListingView/entity phù hợp
~~~

Lựa chọn B tích hợp sâu hơn nhưng cần kiểm thử:

- Việc tạo query cho từng version.
- Type metadata.
- Write conversion.
- Interaction với nested properties.
- Các trường hợp read-only projection.

### 16.3. Không dùng một entity làm cả ba vai trò

Nếu ListingEntity chứa đồng thời:

~~~java
Long rentVnd;
BigDecimal monthlyRentVnd;
Pricing pricing;
~~~

thì service có thể dùng nhầm field hoặc save một bản v1 với fields v3 chưa đầy đủ. Một **read adapter** cung cấp canonical DTO có thể dễ kiểm soát hơn.

### 16.4. CQRS/read model là lựa chọn kiến trúc

Khi query đa phiên bản quá phức tạp, có thể duy trì **read collection/index riêng** chỉ chứa canonical fields, cập nhật bằng migration/Change Stream consumer. Điều này có chi phí đồng bộ và eventual consistency, không phải “miễn phí”.

Không cần CQRS cho mọi collection; cân nhắc khi truy vấn phức tạp, volume lớn hoặc nhiều consumer cùng cần canonical view.

## 17. Đọc rồi ghi ngược: lazy read-repair là gì?

### 17.1. Chuyển đổi chỉ đọc

~~~text
Read raw v1
    |
Convert to canonical
    |
Return response

Stored document vẫn v1
~~~

### 17.2. Read-repair

~~~text
Read raw v1
    |
Convert to canonical
    |
Return response
    |
Optional background/synchronous repair
    |
Write stored document v3
~~~

Read-repair còn gọi là **lazy migration on read** khi lần đọc tạo cơ hội nâng schema của document.

Ưu điểm:

- Những dữ liệu được đọc thường xuyên dần chuyển về schema mới.
- Tránh phải backfill toàn bộ dữ liệu ngay trước deploy.
- Có thể chia nhỏ migration work theo traffic.

Nhược điểm:

- Read có thể bất ngờ tạo writes.
- Các document “lạnh” có thể không bao giờ được migrate.
- Dễ tranh chấp với writer cập nhật cùng document.
- Có thể làm tăng write latency, index maintenance, oplog/Change Streams traffic.
- Cần quyền ghi cho process vốn chỉ đọc.
- Một lỗi repair có thể làm user-facing read thất bại nếu đặt trong đường đồng bộ không đúng.

### 17.3. Không tự save ListingView để migrate

Sai:

~~~java
ListingView view = reader.read(raw);
repository.save(view);  // nguy cơ sai collection/shape/metadata
~~~

ListingView không chứa mọi field legacy, không phải write entity và không có guarantee để replace cả document. Nó cũng có thể bị mất metadata/tags/fields ngoài read model.

### 17.4. Repair phải có migration policy rõ

Một repair hợp lệ cần:

1. Biết chính xác schema nguồn.
2. Dữ liệu nguồn đủ để tạo schema đích mà không suy đoán.
3. Có optimistic concurrency hoặc revision guard.
4. Không xóa fields không thuộc phạm vi migration.
5. Có idempotency/retry policy.
6. Có metrics success/conflict/error.
7. Có backup/rollback plan.
8. Đã đảm bảo old writers không ghi trở lại schema cũ hoặc có policy giải quyết.

### 17.5. Compare-and-set (CAS)

Giả sử document có revision được mọi writer cập nhật. Read-repair đọc revision=7, rồi viết:

~~~javascript
db.rental_listings_425.updateOne(
  {
    _id: "b425-cas-example",
    tenant_id: "tenant-001",
    schema_version: 2,
    revision: NumberLong("7")
  },
  {
    $set: {
      schema_version: 3,
      pricing: {
        monthly: {
          amount: NumberDecimal("12500000.00"),
          currency: "VND"
        }
      }
    },
    $inc: {
      revision: NumberLong("1")
    }
  }
);
~~~

Nếu một writer khác đã tăng revision thành 8 trước, **matchedCount=0**: repair không ghi đè và có thể đọc lại. Tuy nhiên:

- Ví dụ này **chưa phải migration hoàn chỉnh** vì chỉ thiết lập pricing/schema_version, không di chuyển location/status/date và chưa xóa legacy fields.
- Không chạy trên dữ liệu thật khi chưa có đầy đủ mapping/validation.
- CAS chỉ đáng tin nếu **mọi writers cùng tuân theo revision contract**. Nếu một service cũ update mà không tăng revision, guard có thể không nhận ra concurrent write.
- Một schema upgrade có thể cần atomic update hoặc transaction tùy số documents/collections liên quan.

### 17.6. Không giả định schema_version là CAS token

Nếu filter chỉ có:

~~~javascript
{ _id: id, schema_version: 2 }
~~~

thì hai writers khác nhau vẫn có thể thay rentAmount trong khi schema_version còn 2. Reader repair theo giá đọc trước có thể ghi lại **giá cũ**, dù version không đổi.

Muốn chống lost update cần **revision**, source-field predicates đầy đủ hoặc một mô hình atomic transformation phù hợp. Chỉ khóa theo schema version không giải quyết mọi race.

### 17.7. Repair asynchronous hay synchronous?

**Synchronous**:

- Response đợi write repair.
- Lỗi repair có thể làm tăng latency hoặc lỗi read.
- Dễ bảo đảm read-after-repair nhưng tác động người dùng.

**Asynchronous**:

- Read response không đợi migration.
- Cần queue/idempotency/retry/dead-letter.
- Document có thể tiếp tục ở schema cũ trong một khoảng.
- Phải xét ordering và concurrent update.

Đa số trường hợp dùng **read-only adapter** trước, đưa migration vào **job riêng** khi có thể để giới hạn blast radius.

## 18. Tại sao cần backfill ngay cả khi đã có read-repair?

Read-repair chỉ chạy khi một document được đọc. Những document ít được truy cập:

~~~text
Hot 20% documents:
  được đọc hàng ngày -> có thể được repair

Cold 80% documents:
  hiếm khi đọc -> có thể vẫn là v1 sau nhiều tháng
~~~

Nếu mục tiêu là ngừng hỗ trợ v1 hoặc bỏ index legacy, cần **offline/backfill migration** và kiểm tra hoàn tất.

### 18.1. Backfill có checkpoint và batching

Một job migration nên:

- Duyệt theo keyset/pagination ổn định hoặc thay đổi theo query phù hợp.
- Chỉ chọn documents thuộc version cần migrate.
- Đọc/validate/transform theo adapter đã kiểm chứng.
- Ghi với CAS/idempotency.
- Giới hạn batch size, CPU/IOPS, concurrency.
- Lưu checkpoint và báo tiến độ.
- Có dead-letter/quarantine cho records lỗi.
- Theo dõi dữ liệu còn lại theo version.

Không nên:

~~~text
Đọc 20 triệu docs vào RAM
 -> rewrite cả collection không có rate limit
~~~

trên cluster production mà không có kế hoạch.

### 18.2. Re-run an toàn

Migration idempotent có thể chạy lại sau crash mà không:

- Tăng tiền thuê nhiều lần.
- Nhân đôi nested data.
- Ghi phiên bản ngược.
- Xóa field mới của writer khác.

Một migration “đã nâng lên v3” khi chạy lại nên trả **no-op** hoặc xác nhận đã xử lý, không thay dữ liệu hợp lệ.

### 18.3. Reconciliation

Sau backfill:

- Đếm documents v1/v2/v3.
- So tập ID trước/sau.
- So business totals (tổng tiền thuê khi phù hợp).
- Kiểm missing/null/invalid fields.
- So canonical output của mẫu được chọn.
- Theo dõi newly written old-version documents.

Đếm version=3 không đủ chứng minh tất cả document v3 đều hợp lệ.

## 19. Expand–migrate–contract khi rollout nhiều phiên bản

### 19.1. Phase A — Expand readers

Triển khai reader biết **v1/v2/v3** nhưng **writer chưa đổi**:

~~~text
App release R1:
  Read: v1 + v2 + v3
  Write: v2 (giữ schema hiện hành cũ)
~~~

Trong một rolling deployment, old app vẫn đọc v2 vì không có v3 writer mới. Cần kiểm tra forward/backward compatibility của cả old/new readers.

### 19.2. Phase B — New writer

Sau khi toàn bộ readers cũ không còn hoặc đã được chứng minh hiểu v3:

~~~text
App release R2:
  Read: v1 + v2 + v3
  Write: v3
~~~

Không vội bật v3 writer ngay khi chỉ một instance mới deploy, nếu các instances cũ chưa đọc được v3.

### 19.3. Phase C — Migrate tồn kho

Backfill v1/v2 → v3:

~~~text
Collection:
  v1 count giảm
  v2 count giảm
  v3 count tăng
~~~

Job phải chạy với giới hạn và có reconciliation. Trong suốt thời gian này, reader vẫn xử lý các schema cũ.

### 19.4. Phase D — Contract

Chỉ bỏ adapter v1/v2 và indexes cũ khi:

- Không còn old writers.
- Không còn dữ liệu legacy (hoặc chính sách đọc dữ liệu lạnh đã giải quyết).
- Backup/restore compatibility được xem xét.
- Mobile/offline clients cũ không còn ghi schema cũ.
- Queries/metrics không còn phụ thuộc fields cũ.
- Có rollback policy.

### 19.5. Timeline

~~~text
Time --------------------------------------------------->

Deploy compatible reader
      |
      +----- All instances can read v1/v2/v3
                      |
                      +--- Switch writer to v3
                                 |
                                 +--- Backfill v1/v2
                                            |
                                            +--- Verify
                                                     |
                                                     +--- Remove adapters/indexes
~~~

Điều kiện để đổi writer không phải “đã merge code” mà là **mọi đường đọc có thể chạm document v3 đã tương thích**.

## 20. Compatibility matrix: người đọc và người viết

| Reader / Writer | Writer v1 | Writer v2 | Writer v3 |
| --- | --- | --- | --- |
| **Reader R1 chỉ biết v1** | Có | Không bảo đảm | Không |
| **Reader R2 biết v1+v2** | Có | Có | Không |
| **Reader R3 biết v1+v2+v3** | Có | Có | Có |

Ma trận giả định các contracts và field types như bài; “có” chỉ nói mapping có thể đọc, **chưa chứng minh app business logic, indexes và API behavior đều đúng**.

### 20.1. Forward compatibility có giới hạn

Reader v2 không thể tự hiểu chắc v3 nếu fields thay đổi ngữ nghĩa. Một chiến lược tránh break có thể:

- Dual-write fields cũ/mới tạm thời.
- Deploy expanded reader trước.
- Giữ writer v2 trong giai đoạn overlap.
- Feature flag cho writer v3.

### 20.2. Dual-write có rủi ro

~~~javascript
{
  monthly_rent_vnd: NumberDecimal("12500000"),
  pricing: {
    monthly: {
      amount: NumberDecimal("12500000"),
      currency: "VND"
    }
  }
}
~~~

Nếu hai fields lệch nhau:

- Field nào là source of truth?
- Writer nào cập nhật trước?
- Reader ưu tiên field nào?
- Có migration cleanup không?

Dual-write có thể giúp compatibility ngắn hạn nhưng tạo **double-source-of-truth**; cần rules, metrics và thời điểm kết thúc rõ.

### 20.3. Mixed read vs mixed write

Chấp nhận nhiều version để **đọc** khác với cho phép mọi API **ghi** nhiều version:

~~~text
Read support: v1, v2, v3
Write target: v3 only
~~~

đơn giản hơn và giảm số trạng thái mới. Nếu phải hỗ trợ old writers, cần policy và conversion khi update document legacy mà không làm mất unknown fields.

## 21. Read-repair và vấn đề dữ liệu bị đổi đồng thời

### 21.1. Race condition

~~~text
T0  Reader lấy v1: rent=12.5 triệu
T1  User cập nhật rent=13 triệu qua Writer
T2  Reader repair dựa trên dữ liệu T0
T3  Giá có thể quay về 12.5 triệu nếu ghi sai
~~~

Mục tiêu của CAS là tránh tình huống dữ liệu đang thay đổi bị ghi đè từ một snapshot đọc cũ.

### 21.2. Các biện pháp

1. **Optimistic locking**: revision tăng bởi mọi writers.
2. **Conditional update**: filter cả fields nguồn liên quan hoặc revision.
3. **Atomic update expression**: server tự tính từ giá trị hiện tại trong điều kiện được phép.
4. **Targeted write**: chỉ đặt fields mới, không replace toàn document.
5. **Retry có giới hạn**: matchedCount=0 thì đọc lại, không force overwrite.
6. **Migration queue**: tách việc repair khỏi user-facing requests.

### 21.3. CAS không sửa lỗi stale source nếu contract khác

Nếu old writer không tăng revision, optimistic-lock guard chỉ là ảo giác an toàn. Khi rollout, phải kiểm tra **tất cả writers**: REST API, batch import, CDC consumers, admin scripts và mobile sync.

### 21.4. Transaction có phải luôn cần?

Nếu chỉ thay đổi nhiều fields trong **một document**, MongoDB hỗ trợ atomicity ở mức single-document update. Không cần multi-document transaction chỉ để set nhiều fields cùng một document.

Nếu migration liên quan **nhiều collections/documents** có invariant cần cùng commit, có thể cần transaction hoặc saga/reconciliation theo business semantics.

### 21.5. Read-repair làm thay đổi Change Stream

Một update schema trên document có thể phát ra **Change Stream event** nếu deployment hỗ trợ. Downstream consumers:

- Có thể tưởng đó là business update.
- Có thể re-index hoặc phát thông báo không cần thiết.
- Có thể lặp logic repair.

Cần phân biệt **migration metadata update** với business event bằng fields, origin headers, producer policy hoặc consumer logic phù hợp, tránh tạo vòng lặp.

## 22. Khi nào cần server-side schema validation?

### 22.1. Validation không làm documents cũ biến mất

MongoDB hỗ trợ **$jsonSchema** validation và các chế độ validationAction/validationLevel phù hợp. Khi thay đổi rule để chỉ chấp nhận schema mới, documents cũ **vẫn có thể tồn tại**.

Không nên:

~~~text
1. Đổi validator chỉ cho v3
2. Ứng dụng cũ vẫn ghi v2
3. Không kiểm tra kết quả
~~~

vì old writers có thể bắt đầu gặp validation failures.

### 22.2. Validator đa phiên bản

Trong giai đoạn transition, có thể cân nhắc rule cho phép v1/v2/v3 hợp lệ, hoặc dùng rollout policy phù hợp. Tuy nhiên JSON Schema cho nhiều phiên bản có thể rất phức tạp; phải xác minh performance, trường hợp null/missing và điều kiện validationLevel.

### 22.3. Enforce v3 sau contract

Khi toàn bộ dữ liệu và writers đã là v3, server validation có thể giúp ngăn schema v1/v2 xuất hiện trở lại. Nhưng cần thử migration, restore, background jobs và operational scripts.

### 22.4. Ứng dụng vẫn cần validation

Server validator kiểm tra cấu trúc/BSON types, không thay thế business rules như:

- Giá phải tuân theo currency chính xác.
- Tenant phải được xác thực.
- Publication status phù hợp workflow.
- Người dùng chỉ được sửa listing của mình.

## 23. Caching khi có nhiều schema

### 23.1. Cache raw hay cache canonical?

**Cache raw BSON**:

- Giữ dữ liệu gốc cho adapter.
- Cache consumer vẫn phải hiểu nhiều versions.

**Cache canonical read model**:

- API đọc nhanh và không phải convert lại.
- Cần cache key/version và invalidate đúng.
- Khi adapter logic thay đổi, cached normalized values cũ có thể không còn đúng.

### 23.2. Cache key nên mang contract

Ví dụ:

~~~text
listing-view:v3:tenant-001:b425-v1
~~~

v3 trong cache key ở đây là **phiên bản read-view contract**, không nhất thiết là stored schema_version của source. Cần phân biệt hai loại version.

### 23.3. Cache invalidation

Khi document update hoặc read-repair:

- Invalidate cached ListingView.
- Hoặc update cache theo change event có ordering và idempotency.
- Không để cached v1 normalization tiếp tục sau khi dữ liệu thật đổi giá.

Nếu dùng Change Streams để invalidation, consumer phải xử lý resume, duplicates và race theo quy trình phù hợp.

## 24. Monitoring: biết còn bao nhiêu phiên bản cũ

### 24.1. Metric tối thiểu

Nên đo:

- **read_by_schema_version**: số lần đọc v1/v2/v3.
- **stored_docs_by_schema_version**: lượng dữ liệu theo version (đếm định kỳ).
- **unsupported_schema_version_count**.
- **invalid_schema_count** theo nguyên nhân.
- **adapter_latency_ms** theo version.
- **read_repair_attempts/success/conflicts/failures** nếu có repair.
- **backfill_progress**, remaining docs và ETA ước lượng.
- **old_writer_detected**: số documents schema cũ mới được ghi sau writer cutover.
- Application p50/p95/p99 và read error rate.

### 24.2. Tránh nhãn metric có cardinality cao

Không đặt raw **_id** hoặc **tenantId** làm label của mỗi metric time series nếu có hàng triệu giá trị. Dùng labels hữu hạn như version, adapter result, deployment; đẩy ID vào logs/traces có kiểm soát khi cần điều tra.

### 24.3. Count documents theo version

Một aggregation có thể nhóm version, phân biệt missing/null với:

~~~javascript
db.rental_listings_425.aggregate([
  {
    $project: {
      versionKind: {
        $switch: {
          branches: [
            {
              case: {
                $eq: [
                  { $type: "$schema_version" },
                  "missing"
                ]
              },
              then: "v1_missing_marker"
            },
            {
              case: {
                $eq: ["$schema_version", 2]
              },
              then: "v2"
            },
            {
              case: {
                $eq: ["$schema_version", 3]
              },
              then: "v3"
            }
          ],
          default: "unknown_or_invalid"
        }
      }
    }
  },
  {
    $group: {
      _id: "$versionKind",
      docs: { $sum: 1 }
    }
  }
]);
~~~

Trên collection lớn, aggregation này có chi phí scan; nên chạy qua monitoring/batch theo chính sách thay vì mỗi HTTP request.

### 24.4. Report phải tính cả dữ liệu invalid

Nếu chỉ báo:

~~~text
v3 = 98.5%
~~~

mà không nói **v1/v2/unknown/null**, team có thể bỏ adapter quá sớm. Report đúng phải có tổng denominator và nhóm dữ liệu không phân loại được.

## 25. Lab mongosh: gieo ba schema đồng thời

### 25.1. Quy ước lab

Database:

~~~text
mongo_evolution_lab_425
  rental_listings_425
~~~

Dùng ba documents:

~~~text
b425-v1 -> schema legacy, thiếu marker
b425-v2 -> schema_version 2
b425-v3 -> schema_version 3
~~~

Không xóa database/collection, không chạm documents không có labTag.

### 25.2. Seed dữ liệu có thể chạy lại

~~~javascript
(() => {
  const lab = db.getSiblingDB(
    "mongo_evolution_lab_425"
  );
  const listings = lab.getCollection(
    "rental_listings_425"
  );
  const tag = "evolution425-v1";

  const docs = [
    {
      _id: "b425-v1",
      labTag: tag,
      tenant_id: "tenant-001",
      title: "Studio gần công viên",
      rent_vnd: NumberLong("12500000"),
      city: "HCM",
      active: true,
      created_at: ISODate("2026-01-15T09:00:00Z")
    },
    {
      _id: "b425-v2",
      labTag: tag,
      schema_version: 2,
      tenant_id: "tenant-001",
      title: "Căn hộ có ban công",
      monthly_rent_vnd: NumberDecimal("15000000.00"),
      location: { city_code: "HCM" },
      status: "PUBLISHED",
      published_at: ISODate("2026-01-16T09:00:00Z")
    },
    {
      _id: "b425-v3",
      labTag: tag,
      schema_version: 3,
      tenant_id: "tenant-001",
      title: "Nhà phố ba phòng ngủ",
      pricing: {
        monthly: {
          amount: NumberDecimal("23000000.00"),
          currency: "VND"
        }
      },
      address: { city_code: "HN" },
      publication: {
        status: "PUBLISHED",
        published_at: ISODate("2026-01-17T09:00:00Z")
      }
    }
  ];

  for (const doc of docs) {
    listings.replaceOne(
      { _id: doc._id, labTag: tag },
      doc,
      { upsert: true }
    );
  }

  printjson({
    count: listings.countDocuments({ labTag: tag }),
    ids: listings.find(
      { labTag: tag },
      { _id: 1, schema_version: 1 }
    ).sort({ _id: 1 }).toArray()
  });
})();
~~~

Kết quả dự kiến **count = 3** trong collection lab mới. Với collection đã tồn tại, count có thể lớn hơn nếu bạn đã chủ động tạo các fixtures khác mang cùng labTag.

**Lưu ý:** Filter của replaceOne có cả **_id và labTag**; nếu trùng _id với document không phải của bài, thao tác upsert sẽ gặp duplicate-key thay vì ghi đè document lạ. Không drop collection để “sửa” lỗi đó.

### 25.3. Kiểm tra version bằng $type

~~~javascript
const lab = db.getSiblingDB(
  "mongo_evolution_lab_425"
);
const listings = lab.getCollection(
  "rental_listings_425"
);

printjson(
  listings.aggregate([
    { $match: { labTag: "evolution425-v1" } },
    {
      $project: {
        versionType: { $type: "$schema_version" },
        rentV1Type: { $type: "$rent_vnd" },
        rentV2Type: {
          $type: "$monthly_rent_vnd"
        },
        rentV3Type: {
          $type: "$pricing.monthly.amount"
        },
        cityV1Type: { $type: "$city" },
        cityV2Type: {
          $type: "$location.city_code"
        },
        cityV3Type: {
          $type: "$address.city_code"
        }
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray()
);
~~~

Đối với v1: versionType = **missing**, rentV1Type = **long**.

Đối với v2: versionType = **int**, rentV2Type = **decimal**.

Đối với v3: versionType = **int**, rentV3Type = **decimal**.

### 25.4. Query chỉ theo v3 bị thiếu kết quả

~~~javascript
printjson(
  listings.find({
    labTag: "evolution425-v1",
    "address.city_code": "HCM"
  }).toArray()
);
~~~

Không thấy v1/v2 vì chúng không lưu thành phố tại address.city_code; v3 của lab lại có city HN nên kết quả có thể là **[]**.

### 25.5. Query đúng cả v1/v2/v3

~~~javascript
printjson(
  listings.find({
    labTag: "evolution425-v1",
    tenant_id: "tenant-001",
    $or: [
      {
        schema_version: { $exists: false },
        city: "HCM"
      },
      {
        schema_version: 2,
        "location.city_code": "HCM"
      },
      {
        schema_version: 3,
        "address.city_code": "HCM"
      }
    ]
  }, {
    _id: 1,
    schema_version: 1,
    title: 1
  }).sort({ _id: 1 }).toArray()
);
~~~

Kết quả dự kiến gồm **b425-v1** và **b425-v2**, không gồm **b425-v3** vì v3 ở HN.

### 25.6. Thống kê version

~~~javascript
printjson(
  listings.aggregate([
    { $match: { labTag: "evolution425-v1" } },
    {
      $project: {
        schemaGroup: {
          $cond: [
            {
              $eq: [
                { $type: "$schema_version" },
                "missing"
              ]
            },
            "v1",
            { $toString: "$schema_version" }
          ]
        }
      }
    },
    {
      $group: {
        _id: "$schemaGroup",
        docs: { $sum: 1 }
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray()
);
~~~

Kết quả kỳ vọng trong lab sạch:

~~~text
v1: 1
2:  1
3:  1
~~~

Ở document có version null, $toString cho null và document có thể vào nhóm lỗi/khác, vì vậy trong production nên phân loại invalid rõ hơn.

### 25.7. Chạy normalization aggregation

Dùng pipeline ở **mục 14** để chuyển các trường city, rent và publishedAt thành canonical fields. Mục 14 lọc **cityCode HCM**, nên chỉ trả v1 và v2 trong lab gốc.

### 25.8. Không thay đổi nguồn sau read-only pipeline

Kiểm chứng:

~~~javascript
printjson(
  listings.find(
    {
      _id: "b425-v1",
      labTag: "evolution425-v1"
    },
    {
      _id: 1,
      rent_vnd: 1,
      city: 1,
      schema_version: 1,
      pricing: 1
    }
  ).toArray()
);
~~~

Document v1 vẫn có rent_vnd và city, không được tạo pricing chỉ từ việc đọc aggregation.

### 25.9. Thêm fixture malformed có chủ đích

**Tùy chọn**, chỉ trên lab:

~~~javascript
listings.replaceOne(
  {
    _id: "b425-invalid",
    labTag: "evolution425-v1"
  },
  {
    _id: "b425-invalid",
    labTag: "evolution425-v1",
    schema_version: 3,
    tenant_id: "tenant-001",
    title: "Dữ liệu lỗi có chủ đích",
    pricing: {
      monthly: {
        amount: "23000000", // String sai BSON type
        currency: "VND"
      }
    },
    address: { city_code: "HN" },
    publication: {
      status: "PUBLISHED",
      published_at: ISODate("2026-01-17T09:00:00Z")
    }
  },
  { upsert: true }
);
~~~

Version marker=3 **không làm document này hợp lệ**. Java reader phải từ chối vì pricing.monthly.amount không phải Decimal128.

### 25.10. Quan sát malformed bằng $type

~~~javascript
printjson(
  listings.aggregate([
    {
      $match: {
        labTag: "evolution425-v1",
        schema_version: 3
      }
    },
    {
      $project: {
        amountType: {
          $type: "$pricing.monthly.amount"
        }
      }
    }
  ]).toArray()
);
~~~

Nếu đã thêm fixture invalid:

~~~text
b425-v3:      amountType = decimal
b425-invalid: amountType = string
~~~

Không nên dùng **$toDecimal** rồi âm thầm coi malformed string là valid v3; đó là thay đổi hợp đồng dữ liệu.

## 26. Read-repair chỉ để thực hành nâng một document lab

### 26.1. Mục tiêu

Giả sử một người học muốn chuyển **b425-v1** thành v3 ngay trong collection lab. Chỉ thực hiện sau khi đã hiểu:

- Đây là **write operation**.
- Có thể thay cấu trúc raw document.
- Cần chặn concurrent writers trong lab hoặc dùng CAS.
- Với production phải dùng migration framework/runbook, không copy nguyên lệnh minh họa.

### 26.2. Nâng v1 sang v3 bằng một update có filter hẹp

**Chỉ chạy trên database lab và khi document b425-v1 chưa bị sửa bởi bài tập khác:**

~~~javascript
const lab = db.getSiblingDB(
  "mongo_evolution_lab_425"
);
const listings = lab.getCollection(
  "rental_listings_425"
);

const result = listings.updateOne(
  {
    _id: "b425-v1",
    labTag: "evolution425-v1",
    tenant_id: "tenant-001",
    schema_version: { $exists: false },
    rent_vnd: NumberLong("12500000"),
    city: "HCM",
    active: true,
    created_at: ISODate("2026-01-15T09:00:00Z")
  },
  {
    $set: {
      schema_version: 3,
      pricing: {
        monthly: {
          amount: NumberDecimal("12500000.00"),
          currency: "VND"
        }
      },
      address: { city_code: "HCM" },
      publication: {
        status: "PUBLISHED",
        published_at: ISODate("2026-01-15T09:00:00Z")
      }
    },
    $unset: {
      rent_vnd: "",
      city: "",
      active: "",
      created_at: ""
    }
  }
);

printjson(result);
~~~

Điều kiện filter gồm giá trị gốc của các fields được chuyển đổi. Nếu document bị thay đổi, **matchedCount có thể bằng 0** và lệnh không ghi. Đây là một demonstration của **conditional migration**, không phải CAS hoàn chỉnh với một **revision** được mọi writer cập nhật.

### 26.3. Vì sao không dùng replaceOne chỉ theo _id?

Một replacement document chỉ chứa các fields của canonical read model có thể làm mất:

- labTag.
- tenant authorization metadata.
- Dữ liệu domain không có trong read model.
- Các field do writer khác mới thêm.
- Type metadata hoặc field đang dùng trong index/query.

**Targeted update** với filter chặt giảm phạm vi thay đổi, nhưng vẫn cần migration review và concurrency strategy cho production.

### 26.4. Chạy lại sẽ ra sao?

Sau migration, b425-v1 đã có schema_version=3 và không có rent_vnd. Lần chạy tiếp theo, filter **schema_version: { $exists:false }** không match.

Đây là **no-op idempotent** ở mức lab. Không có nghĩa mọi migration có điều kiện đơn giản đều idempotent: nếu có phép tính cộng tiền hoặc append mảng, phải chứng minh riêng.

### 26.5. Tự phục hồi dữ liệu lab ban đầu

Để quay về ba fixtures v1/v2/v3, **chạy lại seed ở mục 25.2**. Seed chỉ thay những _id thuộc lab. Đừng thực hiện $unset hay drop trên documents của application thật.

### 26.6. Điều kiện production mạnh hơn

Trong production, nên có:

- Revision/optimistic locking thống nhất.
- Source fields validation.
- Observability của conflicts.
- Idempotency.
- Rate limiting.
- Migrations có checkpoint.
- Rollback/recovery plan.
- Kiểm tra các writers cũ.
- Tách authorization khỏi update control.

## 27. Schema v1 không có marker: khi nào nên giữ, khi nào nâng?

### 27.1. Giữ legacy support

Phù hợp khi:

- Dữ liệu cũ ít được đọc.
- Field semantics v1 còn rõ ràng.
- Chưa có migration window.
- Không có vấn đề nghiêm trọng về query/index.

Nhưng duy trì lâu dài có chi phí:

- Nhiều nhánh code.
- Nhiều index.
- Khó thống kê/sort.
- Trực tiếp đụng unknown values.

### 27.2. Đánh dấu version trước khi đổi shape?

Một migration có thể thêm schema_version:1 vào những documents v1 hợp lệ, giúp phân biệt missing marker do lỗi với legacy. Nhưng:

- Không được tự gắn 1 cho mọi document thiếu field mà không kiểm tra shape.
- Phải xét old writers có tiếp tục tạo documents không có marker.
- Phải cập nhật detection logic nếu v1 cả “missing” và explicit 1 hợp lệ.

### 27.3. Không suy đoán bằng field existence khi đã có marker chuẩn

Sai:

~~~java
if (raw.containsKey("pricing")) {
    return readV3(raw);
}
~~~

nếu một document v2 tạm dual-write pricing để hỗ trợ app v3. Nó sẽ bị nhận diện v3 dù schema_version=2.

Ưu tiên marker rõ ràng; shape detection chỉ là **legacy fallback có hợp đồng**.

## 28. Phân biệt schema upgrade với thay đổi ý nghĩa nghiệp vụ

### 28.1. Rename không đổi nghĩa

~~~text
city -> location.city_code
~~~

có thể là đổi tên/cấu trúc nếu cả hai cùng mã thành phố theo cùng bảng mã.

### 28.2. Split/merge có thể đổi nghĩa

~~~text
address: "123 Nguyen Van A, HCM"
    ->
address: {
  street: "...",
  city_code: "HCM"
}
~~~

Nếu address cũ free text và không có chuẩn, tách thành street/city có thể **không chính xác**. Reader phải có parser được kiểm chứng hoặc trả “unresolved” và đưa vào repair queue.

### 28.3. Enum migration

~~~text
v1 active boolean
   ->
v2 status PUBLISHED/DRAFT
   ->
v3 publication.status
~~~

Nếu v1 false biểu thị nhiều nguyên nhân, mapping boolean→enum có thể mất thông tin. Cần business policy, dữ liệu phụ trợ hoặc migration manual.

### 28.4. Monetary conversion

Chuyển:

~~~text
12500000 VND (Int64)
    ->
12500000.00 VND (Decimal128)
~~~

là đổi biểu diễn số phù hợp. Chuyển VND sang USD là **biến đổi nghiệp vụ** cần tỷ giá/thời điểm, không đơn thuần là schema migration.

## 29. Test matrix cho nhiều versions và nhiều app releases

### 29.1. Document fixtures

| Fixture | Marker | Rent type | City path | Kỳ vọng |
| --- | --- | --- | --- | --- |
| Valid v1 | missing | Int64 | city | Canonical OK |
| Valid v2 | 2 Int32 | Decimal128 | location.city_code | Canonical OK |
| Valid v3 | 3 Int32 | Decimal128 | address.city_code | Canonical OK |
| Null version | null | Bất kỳ | Bất kỳ | Invalid |
| Future version | 4 | Bất kỳ | Bất kỳ | Unsupported |
| String marker | "3" | Bất kỳ | Bất kỳ | Invalid |
| Missing rent | 3 | missing | address.city_code | Invalid |
| Wrong rent type | 3 | String | address.city_code | Invalid |
| Unknown status | 3 | Decimal128 | address.city_code | Invalid |
| Negative price | 3 | Decimal128 | address.city_code | Invalid |
| Currency USD | 3 | Decimal128 | address.city_code | Invalid trong lab contract |
| Missing tenant | 3 | Decimal128 | address.city_code | Invalid |

### 29.2. App compatibility cases

Phải kiểm tra:

- App R2 đọc v1/v2.
- App R3 đọc v1/v2/v3.
- Old reader không gặp v3 khi rollout writer.
- Restored backup chứa v1/v2 được app hiện tại đọc.
- Writer sau cutover chỉ tạo v3.
- Backfill không làm hỏng read path trong lúc cập nhật.

### 29.3. Query cases

- Search HCM trả v1 + v2, không trả v3 HN.
- Search HN trả v3.
- Chỉ thấy tenant hiện tại.
- Sort theo canonical timestamp đúng.
- Pagination ổn định với keyset/sort phù hợp.
- Có indexes đúng cho query shapes đang dùng.
- Query counts không bỏ sót v1/v2.

### 29.4. Read-repair cases

- V1 hợp lệ được repair đúng.
- Repair cùng document hai lần là no-op lần hai.
- CAS conflict không ghi đè writer mới.
- Invalid document không bị repair tùy tiện.
- Không mất field ngoài phạm vi.
- Repair errors không làm phát hành response sai.

## 30. Hiệu năng khi duy trì nhiều adapter

### 30.1. Chi phí CPU của adapter

Chuyển một Document nhỏ bằng Java thường ít tốn hơn quét một collection lớn, nhưng không thể bỏ qua khi traffic cao. Đo:

- Per-version conversion latency.
- Tỷ lệ v1/v2/v3.
- Allocations/GC.
- BSON deserialization overhead.

Nếu v1 chỉ 0,1% traffic, adapter latency của nó có thể không ảnh hưởng nhiều đến p95 tổng nhưng có thể ảnh hưởng p99 riêng cho nhóm người dùng cũ.

### 30.2. Truy vấn mixed path là chi phí lớn hơn

Query $or trên ba đường dẫn và sort theo expression có thể tốn nhiều hơn read adapter. Cần nhìn:

- Documents examined / nReturned.
- Keys examined.
- Execution plan.
- Index footprint.
- CPU/disk.
- p50/p95/p99 theo query type.

### 30.3. Canonical field hỗ trợ search

Khi search phức tạp, có thể bổ sung **một field ổn định** trên mọi stored versions:

~~~javascript
{
  search_city_code: "HCM"
}
~~~

và backfill nó. Nhưng khi đó writers phải duy trì field này đồng bộ với address/location/city; nếu không nó trở thành một nguồn dữ liệu phụ sai lệch.

### 30.4. Không tạo index bừa

Ba versions không đồng nghĩa ba indexes là luôn đủ hoặc tối ưu. Index design dựa vào query selectivity, sort, tenant isolation, write workload, space và migration timeline.

### 30.5. So before/after công bằng

Một read adapter cải thiện CPU nhưng index mới tăng write latency. Benchmark cần cùng dataset/mix/concurrency, warmup, driver configuration và SLO.

## 31. Rollback, restore và dữ liệu từ tương lai

### 31.1. Tại sao rollback code khó sau khi đổi writer?

Nếu app mới đã ghi v3, rollback binary về app cũ chỉ đọc v2 có thể gây lỗi dữ liệu.

~~~text
R1 reader: v1/v2
R2 writer: v3

Deploy R2 -> ghi v3 -> rollback R1
                      |
                      v
                 R1 không hiểu v3
~~~

Vì thế **binary rollback** không tự là **data rollback**.

### 31.2. Giải pháp

- Expand readers trước writer.
- Giữ rollback binary có khả năng đọc v3.
- Dùng feature flag để dừng v3 writes khi cần.
- Không xóa adapters quá sớm.
- Nếu cần down-convert v3→v2, phải chứng minh lossless và có runbook.

### 31.3. Restore backup legacy

Nếu restore snapshot trước migration, collection có thể quay lại chứa v1/v2. Hệ ứng dụng sau restore vẫn cần đọc được chúng, hoặc phải chạy migration/reconciliation phù hợp **trước khi mở traffic**.

### 31.4. Dữ liệu offline

Một offline writer/client có thể gửi document version cũ sau khi backfill đã hoàn tất. Cần validate/transform tại ingest boundary hoặc từ chối bản cũ theo policy, thay vì cho schema cũ xuất hiện trở lại vô thời hạn.

## 32. Runbook production cho schema-on-read

### 32.1. Chuẩn bị

1. Inventory hiện có bao nhiêu schema và kiểu BSON thật.
2. Lập versioned contract cho từng schema, nhất là tiền/enum/date.
3. Xác định stable fields cho tenant/identity/authorization.
4. Chọn canonical read model.
5. Viết adapters với invalid/unsupported handling.
6. Tạo fixtures từ dữ liệu đã được phép và ẩn PII.
7. Xác định query/index migration strategy.
8. Có backup và phương án rollback.

### 32.2. Deploy expanded read support

1. Rollout reader hỗ trợ v1/v2/v3.
2. Giữ writer ở schema cũ cho tới khi readers đã đủ tương thích.
3. Monitor per-version read errors và latency.
4. Kiểm tra query coverage cho legacy data.
5. Kiểm tra tenant isolation.

### 32.3. Writer cutover

1. Xác minh không còn old reader không hiểu v3.
2. Bật feature flag writer v3.
3. Monitor newly written documents bằng version.
4. Chạy canary và so dữ liệu/response.
5. Có khả năng dừng new writes nếu xuất hiện lỗi.

### 32.4. Migration/backfill

1. Dry-run trên staging với dataset đại diện.
2. Backfill theo batches và checkpoint.
3. CAS/idempotency với mọi source updates.
4. Giới hạn IOPS/concurrency.
5. Đo dead-letter/invalid count.
6. Reconcile số lượng/giá trị.
7. Ngăn old writers tạo schema cũ trở lại.

### 32.5. Contract/decommission

1. Stored v1/v2 còn 0 hoặc đã có xử lý ngoại lệ hợp lệ.
2. Unknown/invalid docs được giải quyết.
3. API/tests/backup restore không còn phụ thuộc adapters cũ.
4. Gỡ old indexes có kế hoạch.
5. Bật validation cho schema mới nếu phù hợp.
6. Lưu migration audit và rollback policy.

## 33. Tình huống lỗi và cách phản ứng

| Triệu chứng | Nguyên nhân khả dĩ | Hành động |
| --- | --- | --- |
| V1 load được bằng _id nhưng không có trong search | Query chỉ dùng field v3 | Query đa đường dẫn/backfill search key |
| Document marker v3 nhưng rent null | Sai/thiếu nested field | Invalid schema, không tự đặt giá=0 |
| Read fail sau deploy mới | Converter không hỗ trợ schema cũ | Rollback compatible reader / fix adapter |
| Read fail sau rollback code | New writer đã lưu v3 | Expanded rollback reader / controlled write flag |
| Giá thuê đổi 1.000.000 lần | Nhầm đơn vị VND và triệu VND | Sửa business conversion contract |
| BigDecimal bị sai/overflow | Coercion từ Double/String | Exact Decimal128 conversion và validation |
| publishedAt lệch giờ | Nhầm UTC/timezone | Kiểm tra BSON Date/Instant/ZoneId |
| Unknown enum thành DRAFT | Default không đúng | Explicit unsupported status |
| schema_version:null bị nhận v1 | Dùng $ifNull không phù hợp | Dùng $type để phân biệt missing |
| Reader bỏ qua v4 | Silently default to v3 | Fail closed + alert |
| Mất field legacy sau API save | Replace canonical view | Tách read/write models, targeted Update |
| Read-repair làm mất update của user | Stale document, CAS thiếu | Revision/source guard |
| Version v2 xuất hiện lại sau backfill | Old writer/mobile/offline client | Ingest version policy + monitoring |
| $or query chậm | Index paths không phù hợp | Explain, query redesign/backfill |
| Sort sai thứ tự | Thời gian nằm trên ba paths | Canonical sort projection hoặc backfill |
| Document bị lộ cross-tenant | Query thiếu tenant filter | Authenticated tenant predicate tại DB |
| Read-repair tăng Change Stream traffic | Migration writes phát event | Consumer phân biệt event và throttling |
| Cache trả giá cũ | Không invalidate khi update/repair | Cache key/version & invalidation |
| Migration báo 100% nhưng còn invalid | Chỉ đếm v3 | Reconcile unknown/null/bad schema |
| Xóa adapter xong restore backup lỗi | Backup legacy còn v1/v2 | Restore compatibility drill |
| Validator mới chặn writer cũ | Triển khai sai thứ tự | Expand readers/writers/validation theo phase |
| Metric quá tải | Label có _id, tenantId | Bounded labels |
| Backfill gây disk latency cao | Batch/concurrency quá lớn | Throttle + capacity planning |

## 34. Bài tập thực hành

### Bài 1 — Nhận diện schema

Một collection có documents v1 thiếu schema_version, v2 có schema_version=2, v3 có schema_version=3. Vì sao cần hợp đồng lịch sử trước khi coi missing marker là v1?

### Bài 2 — Các loại version

Phân biệt schema_version=3, revision=17, app release 4.8.2 và MongoDB server version. Khi cập nhật title, trường nào nên thay đổi?

### Bài 3 — Canonical DTO

Thiết kế ListingView có ID, tenant, title, Money, cityCode, status, publishedAt. Tại sao read model không nhất thiết giống stored BSON?

### Bài 4 — V1 mapping

Chuyển rent_vnd NumberLong(12500000) sang BigDecimal VND. Vì sao không nhân/chia 1.000.000 nếu hợp đồng không yêu cầu?

### Bài 5 — V2 mapping

Từ monthly_rent_vnd Decimal128, location.city_code và status, hãy tạo ListingView với các trường canonical tương ứng.

### Bài 6 — V3 mapping

Giải thích đường dẫn pricing.monthly.amount, pricing.monthly.currency, address.city_code và publication.status trong Java adapter.

### Bài 7 — Missing vs null

Làm sao phân biệt schema_version missing và schema_version:null bằng $type/$exists? Vì sao không dùng equality null để xác định v1?

### Bài 8 — Version tương lai

Một document có schema_version=4 trong khi reader chỉ hỗ trợ tới 3. Reader nên làm gì? Vì sao không trả v3 giả định?

### Bài 9 — Sai kiểu BSON

v3 pricing.monthly.amount là String "23000000" thay vì Decimal128. Xử lý thế nào để không che lỗi writer?

### Bài 10 — Currency

V1/V2 mặc định VND, v3 có currency=USD. Adapter của bài nên làm gì và vì sao không đổi sang VND theo tỷ giá hiện tại?

### Bài 11 — Enum

Nếu v1 active=false có thể nghĩa là DRAFT, BLOCKED hoặc ARCHIVED, ánh xạ trực tiếp false→DRAFT có an toàn không? Đề xuất policy.

### Bài 12 — Date

So BSON Date với Instant. Vì sao không dùng LocalDateTime rồi giả định timezone đã được lưu trong BSON?

### Bài 13 — Adapter

Viết switch dispatch v1/v2/v3 và exception cho unknown version. Vì sao chỉ dùng if(has pricing) không đủ khi có dual-write?

### Bài 14 — Unit test v1

Tạo org.bson.Document legacy bằng Java, chạy VersionedListingReader và assert giá thuê, city, status, publishedAt.

### Bài 15 — Unit negative test

Test marker null, marker String, unknown version, missing nested fields và negative price. Cần phân biệt InvalidSchema với UnsupportedVersion như thế nào?

### Bài 16 — Integration

Seed raw BSON v1/v2/v3 vào MongoDB Testcontainer. Vì sao cần đọc raw BSON lại khi unit test Document→DTO đã PASS?

### Bài 17 — Tenant isolation

Một API đọc document bằng _id nhưng không filter tenant_id. Vì sao read adapter đúng vẫn không bảo đảm bảo mật?

### Bài 18 — Query mixed versions

Viết MongoDB query tìm cityCode HCM ở cả v1/v2/v3 với $or và schema markers đúng.

### Bài 19 — Query performance

Nếu query $or quét rất nhiều documents dù nReturned ít, hãy dùng explain và thiết kế indexes thế nào?

### Bài 20 — Sort

v1 dùng created_at, v2 dùng published_at, v3 dùng publication.published_at. Làm sao sort theo canonical publishedAt trước khi pagination?

### Bài 21 — Aggregation

Viết $switch để tạo canonical_city từ ba paths. Khi nào dùng $type để phân biệt missing marker?

### Bài 22 — $toDecimal

Vì sao aggregation $toDecimal có thể làm dữ liệu malformed String trông hợp lệ? Khi nào cần validation chặt thay vì coercion?

### Bài 23 — Read-only

Chạy pipeline chỉ có $match/$set/$project/$sort. Document gốc có tự được sửa thành v3 không? Lệnh nào có thể tạo side effects trong aggregation?

### Bài 24 — Read-repair

So chuyển đổi chỉ trong bộ nhớ với lazy read-repair. Khi nào không nên ghi database từ đường read?

### Bài 25 — CAS

Reader lấy revision=7, writer khác tăng revision=8. Điều kiện update nào giúp read-repair không ghi đè dữ liệu mới?

### Bài 26 — schema_version vs revision

Hai writes cùng schema_version=2 xảy ra liên tiếp. Vì sao chỉ filter schema_version=2 không đủ bảo vệ lost update?

### Bài 27 — Idempotency

Thiết kế read-repair v1→v3 có thể retry sau lỗi mạng mà không tăng tiền thuê hoặc xóa fields không thuộc migration.

### Bài 28 — Cold documents

20% documents được đọc thường xuyên, 80% rất ít đọc. Vì sao read-repair không bảo đảm toàn collection chuyển sang v3?

### Bài 29 — Expand–migrate–contract

Lập thứ tự triển khai reader tương thích, writer mới, backfill, xác nhận không còn schema cũ và gỡ adapter.

### Bài 30 — Rolling deploy

Tại một thời điểm app R2 chỉ đọc v1/v2 và app R3 ghi v3. Hệ thống có thể lỗi ở đâu? Cần sửa trình tự rollout thế nào?

### Bài 31 — Restore rollback

Sau khi mọi writer đã là v3, khôi phục backup chứa v1/v2. Những test/adapter nào phải còn để hệ thống phục vụ được?

### Bài 32 — Unknown fields

Một document v1 có legacy_note và owner_metadata không có trong ListingView. Vì sao không được dùng ListingView làm replacement document?

### Bài 33 — Lab seed

Chạy mục 25.2 trên mongosh. Kiểm tra ba documents, các BSON types và schema_version missing ở b425-v1.

### Bài 34 — Lab query

Chạy query HCM ở mục 25.5. Vì sao trả b425-v1 và b425-v2 mà không trả b425-v3?

### Bài 35 — Fixture sai

Thêm b425-invalid theo mục 25.9. Viết Java unit/integration test bảo đảm reader không biến String rent amount thành giá hợp lệ.

### Bài 36 — Lab write-back

Chỉ trên lab, chạy update v1→v3 ở mục 26.2. Giải thích matchedCount, các predicates nguồn và vì sao lần chạy lại là no-op.

### Bài 37 — Index cleanup

Sau khi 100% stored documents là v3, nên kiểm tra những điều gì trước khi bỏ indexes dành cho v1/v2?

### Bài 38 — Monitoring

Thiết kế dashboard gồm stored-doc counts v1/v2/v3/unknown, read-by-version, invalid/unsupported errors, adapter latency, read-repair conflicts và backfill progress.

### Bài 39 — Schema validation

Trong rolling deploy, validator chỉ chấp nhận v3 nhưng app cũ vẫn ghi v2. Điều gì có thể xảy ra và cần thứ tự thay đổi nào?

### Bài 40 — Tổng hợp

Một ứng dụng có 15 triệu documents qua bốn schema, app chạy rolling deployment, search theo city/price, API multi-tenant và p99 nghiêm ngặt. Hãy thiết kế canonical reader, query/index transition, adapter test matrix, rollout, backfill CAS, observability, rollback và contract phase.

## 35. Tài liệu tham khảo

- MongoDB Manual — [Documents](https://www.mongodb.com/docs/manual/core/document/).
- MongoDB Manual — [BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/).
- MongoDB Manual — [Schema Design Patterns](https://www.mongodb.com/docs/manual/data-modeling/design-patterns/).
- MongoDB Manual — [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/).
- MongoDB Manual — [Specify Validation Level for Existing Documents](https://www.mongodb.com/docs/manual/core/schema-validation/specify-validation-level/).
- MongoDB Manual — [Query for Null or Missing Fields](https://www.mongodb.com/docs/manual/tutorial/query-for-null-fields/).
- MongoDB Manual — [Query Embedded Documents](https://www.mongodb.com/docs/manual/tutorial/query-embedded-documents/).
- MongoDB Manual — [Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/).
- MongoDB Manual — [$switch](https://www.mongodb.com/docs/manual/reference/operator/aggregation/switch/).
- MongoDB Manual — [$type Aggregation Expression](https://www.mongodb.com/docs/manual/reference/operator/aggregation/type/).
- MongoDB Manual — [$convert](https://www.mongodb.com/docs/manual/reference/operator/aggregation/convert/).
- MongoDB Manual — [Update Documents](https://www.mongodb.com/docs/manual/tutorial/update-documents/).
- MongoDB Manual — [Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/).
- MongoDB Manual — [Indexes](https://www.mongodb.com/docs/manual/indexes/).
- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/).
- MongoDB Manual — [Change Streams](https://www.mongodb.com/docs/manual/changeStreams/).
- Spring Data MongoDB Reference — [Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html).
- Spring Data MongoDB Reference — [Custom Conversions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/custom-conversions.html).
- Spring Data MongoDB Reference — [MongoTemplate](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-api.html).
- MongoDB Java Driver — [Work with BSON Documents](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/documents/).

**Kết luận:** Trong MongoDB, một collection có thể chứa **nhiều phiên bản schema cùng lúc** trong quá trình tiến hóa dữ liệu. Để đọc an toàn, ứng dụng cần **phát hiện version theo hợp đồng, chuyển mỗi BSON shape sang canonical read model, kiểm tra kiểu dữ liệu và giữ nguyên ngữ nghĩa nghiệp vụ**. Chuyển đổi khi đọc **không tự sửa document gốc**; muốn nâng dữ liệu lưu trữ cần một quy trình **backfill hoặc read-repair có điều kiện, concurrency guard, monitoring và rollback plan**. Hơn nữa, **đọc được một document theo _id chưa có nghĩa search/sort/index đa phiên bản đã đúng**: queries phải xử lý các paths cũ/mới hoặc dựa trên canonical fields đã được migrate. Chiến lược vận hành bền vững là **expand reader trước, chuyển writer sau, migrate dữ liệu có kiểm soát, xác minh đầy đủ rồi mới contract legacy support**, bảo đảm mọi phiên bản dữ liệu đều được giải thích đúng mà không làm mất cập nhật hay gây sai lệch nghiệp vụ.
